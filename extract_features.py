
import argparse
import hashlib
import json
import multiprocessing
import os
import time
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models
from pycocotools import mask as coco_mask
from tqdm import tqdm

from rice_dataset import RiceGrainDataset

ROOT = Path(__file__).resolve().parent
OPENCV_FEATURE_VERSION = 3

# These 16 definitions are fixed for this extraction and must also be used
# in production inference. They need not be identical to previous proxy features.
OPENCV_FEATURE_NAMES = [
    "area_px", "perimeter_px", "major_axis_px", "minor_axis_px",
    "aspect_ratio", "eccentricity", "solidity", "extent", "circularity",
    "mean_r", "mean_g", "mean_b", "gray_std", "mean_saturation",
    "mean_value", "gray_entropy",
]

# Keep OpenCV from spawning large internal thread pools inside DataLoader workers.
cv2.setNumThreads(0)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract RiceGrade EfficientNet-B0 (1280) + OpenCV (16) features"
    )
    parser.add_argument("--checkpoint", type=Path,
                        default=ROOT / "models" / "version_1" / "best_efficientnet_b0.pth")
    parser.add_argument("--data", type=Path, default=ROOT / "full_manifests",
                        help="Folder with train.csv, valid.csv and test.csv")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results" / "version_1" / f"features_v{OPENCV_FEATURE_VERSION}")
    parser.add_argument("--splits", nargs="+", choices=["train", "valid", "test"],
                        default=["train", "valid"],
                        help="Default: train valid. Add test when ready; do not tune on test.")
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument("--no-amp", action="store_true", help="Disable CUDA mixed precision")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only first N grains per split for a preview; never saves over full files")
    parser.add_argument("--overwrite", action="store_true",
                        help="Allow replacing existing feature files")
    args = parser.parse_args()
    if args.batch < 1 or args.num_workers < 0 or (args.limit is not None and args.limit < 1):
        parser.error("--batch and --limit must be positive; --num-workers cannot be negative")
    if len(set(args.splits)) != len(args.splits):
        parser.error("Do not repeat a split in --splits")
    return args


def resolve_dataset_path(raw, manifest_dir):
    """Resolve absolute, manifest-relative or project-relative dataset paths."""
    path = Path(str(raw))
    candidates = [path] if path.is_absolute() else [manifest_dir / path, ROOT / path, path]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Could not locate dataset file: {raw} (manifest: {manifest_dir})")


@lru_cache(maxsize=12)
def read_coco_annotations(path_string):
    """Parse an annotations JSON once per DataLoader worker and cache by path."""
    with Path(path_string).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "annotations" not in data:
        raise ValueError(f"Not a COCO annotation JSON (no 'annotations'): {path_string}")
    return {str(ann["id"]): ann for ann in data["annotations"]}


def instance_mask(annotation, image_height, image_width):
    """Decode polygons/RLE with the same COCO rasterizer as the CNN loader."""
    segmentation = annotation.get("segmentation")
    if not segmentation:
        raise ValueError(f"Annotation {annotation.get('id')} has no segmentation")

    if isinstance(segmentation, list):
        polygons = ([segmentation] if isinstance(segmentation[0], (int, float))
                    else segmentation)
        for polygon in polygons:
            if len(polygon) < 6 or len(polygon) % 2 or not np.isfinite(polygon).all():
                raise ValueError(f"Invalid polygon for annotation {annotation.get('id')}")
        # Preserve fractional vertices; rounding/fillPoly changes COCO boundaries.
        rles = coco_mask.frPyObjects(polygons, image_height, image_width)
        rle = coco_mask.merge(rles)
    elif isinstance(segmentation, dict):
        rle = (coco_mask.frPyObjects(segmentation, image_height, image_width)
               if isinstance(segmentation.get("counts"), list) else segmentation)
    else:
        raise ValueError(f"Unsupported mask format for annotation {annotation.get('id')}")

    mask = coco_mask.decode(rle)
    if mask.ndim == 3:
        mask = np.any(mask, axis=2)
    mask = np.asarray(mask, dtype=np.uint8)
    if mask.shape != (image_height, image_width):
        raise ValueError(f"Incorrectly sized mask: annotation {annotation.get('id')}")
    return mask


def mask_geometry(mask, annotation_id=None):
    """Return nine shape features, including valid thin/single-pixel masks.

    Ordinary masks retain contour-based measurements. Zero-area contours use
    pixel-cell area, exposed pixel-edge perimeter, and pixel-corner geometry.
    """
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if not contours or hierarchy is None:
        raise ValueError(f"No contour: annotation {annotation_id}")
    # Shape, moments and color all describe the complete annotated instance.
    # Include disconnected components and subtract hole areas from geometry.
    outer = [contour for contour, entry in zip(contours, hierarchy[0]) if entry[3] < 0]
    boundary_points = np.concatenate(outer, axis=0)
    _, _, bounding_width, bounding_height = cv2.boundingRect(boundary_points)
    area = float(sum(cv2.contourArea(contour) * (1 if entry[3] < 0 else -1)
                     for contour, entry in zip(contours, hierarchy[0])))
    if area <= 0:
        # A nonempty one-pixel-wide line or isolated pixel has zero contour
        # area. Measure its occupied pixel cells instead of rejecting the row.
        area = float(cv2.countNonZero(mask))
        x, y, width, height = cv2.boundingRect(boundary_points)
        padded = np.pad(mask[y:y + height, x:x + width], 1)
        perimeter = float(np.count_nonzero(padded[1:, :] != padded[:-1, :])
                          + np.count_nonzero(padded[:, 1:] != padded[:, :-1]))
        corners = np.asarray([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.int32)
        boundary_points = (boundary_points + corners).reshape(-1, 1, 2)
    else:
        perimeter = float(sum(cv2.arcLength(contour, True) for contour in contours))
    (_, _), (side_a, side_b), _ = cv2.minAreaRect(boundary_points)
    major, minor = sorted((float(side_a), float(side_b)), reverse=True)
    aspect_ratio = major / minor if minor > 0 else 0.0

    moments = cv2.moments(mask, binaryImage=True)
    if moments["m00"] > 0:
        covariance = np.array([
            [moments["mu20"], moments["mu11"]],
            [moments["mu11"], moments["mu02"]],
        ], dtype=np.float64) / moments["m00"]
        eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0.0)
        eccentricity = float(np.sqrt(max(0.0, 1.0 - eigenvalues[0] / eigenvalues[1]))) \
            if eigenvalues[1] > 0 else 0.0
    else:
        eccentricity = 0.0

    hull_area = float(cv2.contourArea(cv2.convexHull(boundary_points)))
    solidity = area / hull_area if hull_area > 0 else 0.0
    bounding_area = bounding_width * bounding_height
    extent = area / bounding_area if bounding_area > 0 else 0.0
    circularity = (4.0 * np.pi * area / (perimeter * perimeter)) if perimeter > 0 else 0.0

    return (area, perimeter, major, minor, aspect_ratio, eccentricity,
            solidity, extent, circularity)


def opencv_features(image_path, annotation_path, annotation_id, expected_image_id=None):
    """Measure shape/size in ORIGINAL pixels, and color/texture inside mask."""
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Unable to read image: {image_path}")
    height, width = image.shape[:2]
    annotation = read_coco_annotations(str(annotation_path)).get(str(annotation_id))
    if annotation is None:
        raise KeyError(f"Annotation ID {annotation_id} missing from {annotation_path}")
    if expected_image_id is not None and str(annotation.get("image_id")) != str(expected_image_id):
        raise ValueError(
            f"Annotation {annotation_id}: image_id={annotation.get('image_id')} "
            f"does not match manifest image_id={expected_image_id}"
        )

    mask = instance_mask(annotation, height, width)
    if mask.shape != (height, width) or not np.any(mask):
        raise ValueError(f"Empty or incorrectly sized mask: annotation {annotation_id}")

    shape_values = mask_geometry(mask, annotation_id)

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    selected = mask != 0
    mean_r, mean_g, mean_b = rgb[selected].mean(axis=0)
    mean_saturation = float(hsv[:, :, 1][selected].mean())
    mean_value = float(hsv[:, :, 2][selected].mean())
    gray_pixels = gray[selected]
    gray_std = float(gray_pixels.std())
    hist = np.bincount(gray_pixels, minlength=256).astype(np.float64)
    probabilities = hist[hist > 0] / hist.sum()
    gray_entropy = float(-(probabilities * np.log2(probabilities)).sum())

    values = np.asarray([
        *shape_values, mean_r, mean_g, mean_b,
        gray_std, mean_saturation, mean_value, gray_entropy,
    ], dtype=np.float32)
    if not np.all(np.isfinite(values)):
        raise ValueError(f"Invalid OpenCV features for annotation {annotation_id}")
    return values


class GrainFeatureDataset(Dataset):
    """Reuses CNN crop preprocessing and adds mask-based OpenCV features."""

    def __init__(self, csv_path, class_names, limit=None):
        csv_path = Path(csv_path).resolve()
        self.csv_path = csv_path
        frame = pd.read_csv(csv_path, keep_default_na=False)
        required = {"image_path", "annotation_path", "annotation_id", "image_id", "label", "class_id"}
        if not required.issubset(frame.columns):
            raise ValueError(f"{csv_path} missing columns: {sorted(required - set(frame.columns))}")
        if frame.empty:
            raise ValueError(f"Manifest is empty: {csv_path}")
        if frame["annotation_id"].isna().any():
            raise ValueError("Missing annotation_id values")
        n = min(len(frame), limit) if limit is not None else len(frame)
        self.frame = frame.iloc[:n].copy().reset_index(drop=True)
        self.rows = self.frame.to_dict(orient="records")
        self.class_names = class_names
        self.paths = [(
            resolve_dataset_path(row["image_path"], csv_path.parent),
            resolve_dataset_path(row["annotation_path"], csv_path.parent),
        ) for row in self.rows]
        for idx, row in enumerate(self.rows):
            name = str(row["label"])
            label = int(row["class_id"])
            valid_label = 0 <= label < len(class_names) and class_names[label] == name
            if not valid_label:
                raise ValueError(f"Row {idx} has class_id={label}, label={name}, "
                                 f"but checkpoint classes are {class_names}")

        # Feed identical absolute paths to both branches, without rewriting
        # the source manifest or changing the original metadata rows.
        resolved_records = [
            {**row, "image_path": str(image_file), "annotation_path": str(annotation_file)}
            for row, (image_file, annotation_file) in zip(self.rows, self.paths)
        ]
        self.data = RiceGrainDataset(csv_path, train=False, records=resolved_records)
        if len(self.data) != len(self.rows):
            raise ValueError("RiceGrainDataset row count does not match selected manifest rows")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        image_tensor, target = self.data[index]
        row = self.rows[index]
        expected = int(row["class_id"])
        actual = int(target.item()) if isinstance(target, torch.Tensor) else int(target)
        if actual != expected:
            raise ValueError(f"Dataset/class ordering mismatch at row {index}: {actual} vs {expected}")
        image_file, annotation_file = self.paths[index]
        features = opencv_features(
            image_file, annotation_file, row["annotation_id"], row["image_id"]
        )
        return image_tensor, actual, torch.from_numpy(features)


def load_feature_extractor(checkpoint_path, device):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint.get("architecture", "efficientnet_b0") != "efficientnet_b0":
        raise ValueError("Checkpoint architecture is not EfficientNet-B0")
    classes = checkpoint["classes"]
    if not isinstance(classes, (list, tuple)) or len(classes) != 4:
        raise ValueError("Expected 4 ordered rice grain class names in checkpoint")
    model = models.efficientnet_b0(weights=None)  # Never download ImageNet weights
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(classes))
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    # EfficientNet forward already does feature extraction + global average pool
    # + flatten BEFORE classifier. Removing classifier exposes 1280 features.
    model.classifier = nn.Identity()
    model = model.to(device)
    if device.type == "cuda":
        model = model.to(memory_format=torch.channels_last)
    model.requires_grad_(False)
    model.eval()
    return model, list(classes), checkpoint


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_npz_atomically(path, *, cnn_features, opencv_features, y, sample_ids):
    temp_path = path.with_name("." + path.name + ".incomplete.npz")
    try:
        np.savez_compressed(
            temp_path,
            cnn_features=cnn_features,
            opencv_features=opencv_features,
            y=y,
            sample_ids=sample_ids,
        )
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main():
    args = parse_args()
    checkpoint_path = args.checkpoint.resolve()
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Trained checkpoint not found: {checkpoint_path}")
    device = torch.device("cuda" if args.device == "auto" and torch.cuda.is_available()
                          else "cpu" if args.device == "auto" else args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but PyTorch cannot see your NVIDIA GPU")

    amp = device.type == "cuda" and not args.no_amp
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
    model, classes, checkpoint = load_feature_extractor(checkpoint_path, device)
    data_dir = args.data.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_hash = sha256_file(checkpoint_path)
    print("RiceGrade hybrid feature extraction (NO TRAINING)")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Best epoch: {checkpoint.get('epoch', 'unknown')}; device: {device}; AMP: {amp}")
    print(f"Class order: {classes}")
    print(f"OpenCV features: {len(OPENCV_FEATURE_NAMES)}; CNN features: 1280")

    schema_path = output_dir / "feature_schema.json"
    schema = {
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": checkpoint_hash,
        "checkpoint_epoch": checkpoint.get("epoch"),
        "classes": classes,
        "cnn_architecture": "efficientnet_b0",
        "cnn_feature_count": 1280,
        "opencv_feature_version": OPENCV_FEATURE_VERSION,
        "mask_decoder": "pycocotools",
        "degenerate_geometry_policy": "occupied pixel cells for nonempty zero-area contours",
        "opencv_region_policy": "complete instance: all components, with hole boundaries",
        "opencv_feature_names": OPENCV_FEATURE_NAMES,
        "opencv_feature_count": len(OPENCV_FEATURE_NAMES),
        "mask_source": "ground-truth COCO instance segmentation polygons / RLE",
        "preprocessing": "RiceGrainDataset(..., train=False) for all splits",
        "cnn_amp": bool(amp),
        "output_npz_keys": ["cnn_features", "opencv_features", "y", "sample_ids"],
    }
    if schema_path.exists():
        old = json.loads(schema_path.read_text(encoding="utf-8"))
        fields_to_match = ["checkpoint_sha256", "classes", "cnn_feature_count",
                           "opencv_feature_names", "opencv_feature_version", "mask_decoder", "cnn_amp"]
        mismatched = [field for field in fields_to_match if old.get(field) != schema.get(field)]
        if mismatched:
            raise ValueError(
                f"Existing feature_schema.json has different settings: {mismatched}. "
                "Use a new --output folder for a different experiment."
            )

    for split in args.splits:
        csv_path = data_dir / f"{split}.csv"
        if not csv_path.is_file():
            raise FileNotFoundError(f"Required manifest not found: {csv_path}")
        basename = f"{split}_preview_{args.limit}" if args.limit is not None else split
        feature_path = output_dir / f"{basename}.npz"
        metadata_path = output_dir / f"{basename}_metadata.csv"
        if not args.overwrite and (feature_path.exists() or metadata_path.exists()):
            raise FileExistsError(
                f"Feature output already exists for {split}: {feature_path}. "
                "Use --overwrite only if you intend to replace it."
            )

        print(f"\n--- {split.upper()} ---")
        start = time.perf_counter()
        dataset = GrainFeatureDataset(csv_path, classes, limit=args.limit)
        loader_options = dict(
            dataset=dataset, batch_size=args.batch, shuffle=False,
            num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
        )
        if args.num_workers > 0:
            loader_options["prefetch_factor"] = 2
        loader = DataLoader(**loader_options)
        count = len(dataset)
        cnn_all = np.empty((count, 1280), dtype=np.float32)
        cv_all = np.empty((count, len(OPENCV_FEATURE_NAMES)), dtype=np.float32)
        y_all = np.empty(count, dtype=np.int64)
        offset = 0

        with torch.inference_mode():
            for images, labels, cv_batch in tqdm(loader, desc=split, unit="batch", dynamic_ncols=True):
                images = images.to(device, non_blocking=device.type == "cuda")
                if device.type == "cuda":
                    images = images.contiguous(memory_format=torch.channels_last)
                with torch.amp.autocast(device_type=device.type, enabled=amp):
                    deep_features = model(images)
                deep_features = deep_features.float().cpu().numpy()
                opencv_batch = cv_batch.numpy()
                label_batch = labels.numpy()
                if deep_features.shape[1] != 1280:
                    raise RuntimeError(f"Expected 1280 CNN features; got {deep_features.shape}")
                n = len(label_batch)
                cnn_all[offset:offset + n] = deep_features
                cv_all[offset:offset + n] = opencv_batch
                y_all[offset:offset + n] = label_batch
                offset += n

        if offset != count or not np.isfinite(cnn_all).all() or not np.isfinite(cv_all).all():
            raise RuntimeError("Feature count mismatch or invalid feature values; no result saved")
        sample_ids = np.asarray([
            f"{row['image_id']}:{row['annotation_id']}" for row in dataset.rows
        ], dtype=np.str_)
        if len(np.unique(sample_ids)) != count:
            raise ValueError(f"Duplicate image/annotation pairs in {split} manifest")
        save_npz_atomically(feature_path, cnn_features=cnn_all,
                            opencv_features=cv_all, y=y_all, sample_ids=sample_ids)
        dataset.frame.to_csv(metadata_path, index=False)
        if not schema_path.exists():
            schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        print(f"Grains: {count}; CNN: {cnn_all.shape}; OpenCV: {cv_all.shape}")
        print(f"Saved: {feature_path}")
        print(f"Metadata: {metadata_path}")
        print(f"Elapsed: {time.perf_counter() - start:.1f} seconds")

    print("\nDone. Next: combine both feature arrays to train XGBoost.")
    print("Reminder: these features use labeled COCO masks, not automatic segmentation.")


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required for Windows workers.
    main()
