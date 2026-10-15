"""Extract frozen CNN and OpenCV features for train/validation grains.

Run manually: python extract_features.py
Outputs train.npz, valid.npz, matching metadata CSVs, and feature_schema.json.
CNN extraction uses evaluation transforms and float32, with no augmentation.
OpenCV uses original-resolution PNGs and true COCO masks, one mask at a time.
This script does not train models or load the test split.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
import torch
import torch.nn as nn
import torchvision
from PIL import Image
from pycocotools import mask as mask_utils
from pycocotools.coco import COCO
from torch.utils.data import DataLoader
from torchvision import models
from tqdm import tqdm

from data_loader import (
    CLASSES, CROP_PREPROCESSING, DEFAULT_MANIFEST_DIR, IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD,
    ROOT, RiceGrainDataset, resolve_record_path,
)
from grain_features import OPENCV_FEATURE_NAMES, extract_opencv_features


DEFAULT_CHECKPOINT = ROOT / "models/efficientnet_20261015_114701_799602/best_efficientnet_b0.pth"
CNN_FEATURE_COUNT = 1280


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_model(checkpoint_path, manifests, device):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint["architecture"] != "efficientnet_b0" or checkpoint["classes"] != list(CLASSES):
        raise ValueError("Checkpoint architecture or class order does not match this project")
    config = checkpoint["run_config"]
    if (config["image_size"] != IMAGE_SIZE
            or config["normalization_mean"] != list(IMAGENET_MEAN)
            or config["normalization_std"] != list(IMAGENET_STD)
            or config["crop_preprocessing"] != CROP_PREPROCESSING):
        raise ValueError("Checkpoint preprocessing does not match the data loader")
    trained_hashes = {Path(path).name: value for path, value in config["source_sha256"].items()}
    for split in ("train", "valid"):
        if sha256_file(manifests / f"{split}.csv") != trained_hashes.get(f"{split}.csv"):
            raise ValueError(f"{split} manifest differs from the dataset used to train this checkpoint")

    model = models.efficientnet_b0(weights=None)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASSES))
    model.load_state_dict(checkpoint["model_state_dict"])
    model.classifier = nn.Identity()  # Return pooled features instead of class scores.
    model.requires_grad_(False)
    return model.to(device).eval(), checkpoint["epoch"]


def grain_mask(coco, record):
    annotation = coco.anns[record["annotation_id"]]
    if (annotation["image_id"] != record["image_id"]
            or coco.cats[annotation["category_id"]]["name"] != record["class_name"]):
        raise ValueError(f"COCO annotation disagrees with manifest: {record['annotation_id']}")
    rle = coco.annToRLE(annotation)
    x, y, width, height = mask_utils.toBbox(rle).astype(np.int64)
    full_mask = mask_utils.decode(rle)
    metadata = coco.imgs[record["image_id"]]
    if full_mask.shape != (metadata["height"], metadata["width"]):
        raise ValueError(f"Mask dimensions disagree with COCO image: {record['annotation_id']}")
    if (width <= 0 or height <= 0 or x < 0 or y < 0
            or x + width > full_mask.shape[1] or y + height > full_mask.shape[0]):
        raise ValueError(f"Invalid mask bounds: {record['annotation_id']}")
    mask = full_mask[y:y + height, x:x + width].astype(bool, copy=True)
    del full_mask
    return mask


def extract_split(split, manifests, output, model, device, batch_size, num_workers):
    dataset = RiceGrainDataset(manifests / f"{split}.csv", train=False)
    options = {"prefetch_factor": 1} if num_workers > 0 else {}
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False,
                        num_workers=num_workers, pin_memory=device.type == "cuda", **options)
    count = len(dataset)
    cnn = np.empty((count, CNN_FEATURE_COUNT), dtype=np.float32)
    labels = np.empty(count, dtype=np.int64)
    offset = 0
    with torch.inference_mode():
        for images, batch_labels in tqdm(loader, desc=f"{split} CNN", unit="batch", dynamic_ncols=True):
            features = model(images.to(device, non_blocking=True)).cpu().numpy()
            if features.shape != (len(batch_labels), CNN_FEATURE_COUNT):
                raise ValueError(f"Unexpected CNN feature shape: {features.shape}")
            end = offset + len(batch_labels)
            cnn[offset:end] = features
            labels[offset:end] = batch_labels.numpy()
            offset = end
    expected_labels = np.array([row["class_id"] for row in dataset.records], dtype=np.int64)
    if offset != count or not np.array_equal(labels, expected_labels):
        raise ValueError(f"CNN features and manifest labels are misaligned: {split}")

    opencv = np.empty((count, len(OPENCV_FEATURE_NAMES)), dtype=np.float32)
    source_hashes = dataset.crop_info["splits"][split]["source_annotation_sha256"]
    source_dir = Path(dataset.crop_info["source_manifest_dir"])
    coco_files = {}
    for index, record in enumerate(tqdm(dataset.records, desc=f"{split} OpenCV", unit="grain", dynamic_ncols=True)):
        annotation_path = resolve_record_path(record["annotation_path"], source_dir)
        if annotation_path not in coco_files:
            if sha256_file(annotation_path) != source_hashes.get(str(annotation_path)):
                raise ValueError(f"Annotations changed since grain preparation: {annotation_path}")
            coco_files[annotation_path] = COCO(str(annotation_path))
        mask = grain_mask(coco_files[annotation_path], record)
        with Image.open(record["crop_path"]) as image:
            rgb = np.array(image)
        opencv[index] = extract_opencv_features(rgb, mask)

    if not np.isfinite(cnn).all() or not np.isfinite(opencv).all():
        raise ValueError(f"Non-finite features found in {split}")
    sample_ids = np.array([
        Path(row["crop_path"]).relative_to(manifests).as_posix() for row in dataset.records
    ])
    np.savez_compressed(output / f"{split}.npz", cnn_features=cnn, opencv_features=opencv,
                        y=labels, sample_ids=sample_ids)
    with (output / f"{split}_metadata.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["sample_id", *dataset.records[0]])
        writer.writeheader()
        writer.writerows({"sample_id": sample_id, **row}
                         for sample_id, row in zip(sample_ids, dataset.records))
    print(f"Saved {split}: {count} grains, {CNN_FEATURE_COUNT} CNN + {len(OPENCV_FEATURE_NAMES)} OpenCV features")
    return {"samples": count, "manifest_sha256": sha256_file(manifests / f"{split}.csv"),
            "annotation_sha256": source_hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--manifests", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()
    if args.batch_size < 1 or args.num_workers < 0:
        parser.error("batch-size must be positive and num-workers nonnegative")
    checkpoint_path, manifests = args.checkpoint.resolve(), args.manifests.resolve()
    output = (args.output or ROOT / "results" / checkpoint_path.parent.name / "features").resolve()
    if output.exists():
        raise FileExistsError(f"Use a new --output folder; already exists: {output}")
    device_name = args.device
    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; check your installation or choose --device cpu")
    device = torch.device(device_name)
    model, epoch = load_model(checkpoint_path, manifests, device)
    print(f"Checkpoint: {checkpoint_path}\nSelected epoch: {epoch}\nDevice: {device}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".features-", dir=output.parent) as temporary:
        staging = Path(temporary) / "features"
        staging.mkdir()
        splits = {split: extract_split(split, manifests, staging, model, device,
                                       args.batch_size, args.num_workers)
                  for split in ("train", "valid")}
        schema = {
            "schema_version": 1, "classes": list(CLASSES),
            "cnn_feature_count": CNN_FEATURE_COUNT,
            "opencv_feature_names": list(OPENCV_FEATURE_NAMES),
            "hybrid_feature_count": CNN_FEATURE_COUNT + len(OPENCV_FEATURE_NAMES),
            "hybrid_feature_order": "CNN features followed by OpenCV features",
            "cnn_precision": "float32", "cnn_layer": "EfficientNet-B0 pooled features, classifier removed",
            "cnn_preprocessing": {"image_size": IMAGE_SIZE, "mean": list(IMAGENET_MEAN),
                                  "std": list(IMAGENET_STD), "augmentation": False},
            "opencv_input": "Original-resolution RGB grain crop and true COCO foreground mask",
            "checkpoint": str(checkpoint_path), "checkpoint_sha256": sha256_file(checkpoint_path),
            "checkpoint_epoch": epoch, "splits": splits,
            "source_sha256": {str(path): sha256_file(path) for path in (
                Path(__file__).resolve(), ROOT / "grain_features.py", ROOT / "data_loader.py",
                manifests / "crop_info.json", manifests / "class_mapping.json",
            )},
            "versions": {"torch": str(torch.__version__), "torchvision": str(torchvision.__version__),
                         "numpy": np.__version__, "opencv": cv2.__version__},
            "test_data_used": False,
        }
        (staging / "feature_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
        if output.exists():
            raise FileExistsError(f"Refusing to replace existing output: {output}")
        staging.rename(output)
    print(f"Features saved to: {output}")


if __name__ == "__main__":
    main()
