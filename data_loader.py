"""Load prepared PNG grain crops without reopening source photos or masks.

First run prepare_grains.py manually to create grain_crops/. This module needs
torch, torchvision, Pillow, and numpy. Example training setup:

    from data_loader import create_data_loaders

    if __name__ == "__main__":
        loaders = create_data_loaders(batch_size=32, num_workers=0)
        for images, labels in loaders["train"]:
            # images: float32 [B, 3, 224, 224]; labels: int64 [B]
            pass

To inspect one train/validation batch manually (does not train a model):
    python data_loader.py

Windows callers must use a main guard before starting worker processes.
"""

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms


ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_DIR = ROOT / "grain_crops"
CLASSES = ("broken_grain", "chalky_grain", "discolored_grain", "whole_grain")
CLASS_TO_ID = {name: index for index, name in enumerate(CLASSES)}
IMAGE_SIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
REQUIRED_COLUMNS = {
    "image_path", "annotation_path", "image_id", "annotation_id", "class_name", "class_id", "crop_path"
}
CROP_PREPROCESSING = {
    "format": "PNG", "mode": "RGB", "crop": "mask_bounds", "background": [0, 0, 0],
    "resize": None, "augmentation": None, "normalization": None,
}


class SquarePad:
    """Resize with aspect ratio preserved and black padding; worker-picklable."""

    def __call__(self, image):
        return ImageOps.pad(
            image, (IMAGE_SIZE, IMAGE_SIZE),
            method=Image.Resampling.BICUBIC, color=(0, 0, 0),
        )


def build_transform(train=False):
    steps = []
    if train:
        # Rotate before final padding and expand to avoid clipping the grain.
        # Preserve color because chalkiness and discoloration depend on it.
        steps.extend([
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomVerticalFlip(p=0.5),
            transforms.RandomRotation(degrees=15, expand=True, fill=0),
        ])
    steps.extend([
        SquarePad(),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])
    return transforms.Compose(steps)


def resolve_record_path(value, manifest_dir):
    """Absolute paths are retained; relative paths are manifest-relative."""
    if not value or not value.strip():
        raise ValueError("Manifest contains an empty crop path")
    path = Path(value)
    return (path if path.is_absolute() else manifest_dir / path).resolve()


class RiceGrainDataset(Dataset):
    """One item is one saved RGB grain crop, transformed, and its class ID."""

    def __init__(self, manifest_path, train=False):
        self.manifest_path = Path(manifest_path).resolve()
        self.transform = build_transform(train=train)
        if not self.manifest_path.is_file():
            raise FileNotFoundError(
                f"Prepared crop manifest not found: {self.manifest_path}. "
                "Run python prepare_grains.py first."
            )
        info_path = self.manifest_path.parent / "crop_info.json"
        if not info_path.is_file():
            raise FileNotFoundError(f"Missing {info_path}. Use manifests created by prepare_grains.py.")
        self.crop_info = json.loads(info_path.read_text(encoding="utf-8"))
        if (self.crop_info.get("schema_version") != 1
                or self.crop_info.get("classes") != list(CLASSES)
                or self.crop_info.get("preprocessing") != CROP_PREPROCESSING):
            raise ValueError(f"Unsupported crop format or preprocessing in {info_path}")
        split_info = self.crop_info.get("splits", {}).get(self.manifest_path.stem)
        digest = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        if not split_info or split_info.get("manifest_sha256") != digest:
            raise ValueError(f"Crop manifest does not match its preparation report: {self.manifest_path}")
        mapping_path = self.manifest_path.parent / "class_mapping.json"
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        if mapping != CLASS_TO_ID:
            raise ValueError(f"Unexpected class mapping in {mapping_path}: {mapping}")

        with self.manifest_path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"Missing crop manifest columns: {sorted(missing)}. Run prepare_grains.py first.")
            self.records = list(reader)
        if not self.records:
            raise ValueError(f"Manifest contains no grains: {self.manifest_path}")
        if (split_info.get("samples") != len(self.records)
                or split_info.get("verified_pngs") != len(self.records)):
            raise ValueError(f"Crop count or PNG verification count disagrees with {self.manifest_path}")

        for row_number, record in enumerate(self.records, start=2):
            for key in ("image_id", "annotation_id", "class_id"):
                record[key] = int(record[key])
            if CLASS_TO_ID.get(record["class_name"]) != record["class_id"]:
                raise ValueError(f"Inconsistent class label at CSV row {row_number}")
            crop_path = resolve_record_path(record["crop_path"], self.manifest_path.parent)
            if not crop_path.is_relative_to(self.manifest_path.parent) or crop_path.suffix.lower() != ".png":
                raise ValueError(f"Invalid PNG crop path at CSV row {row_number}: {crop_path}")
            if not crop_path.is_file():
                raise FileNotFoundError(f"Prepared grain crop is missing: {crop_path}")
            record["crop_path"] = str(crop_path)

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        record = self.records[index]
        with Image.open(record["crop_path"]) as image:
            if image.format != "PNG" or image.mode != "RGB":
                raise ValueError(f"Expected a lossless RGB PNG crop: {record['crop_path']}")
            grain = image.copy()
        return self.transform(grain), record["class_id"]


def seed_worker(worker_id):
    """Seed NumPy/Python using the seed assigned to each PyTorch worker."""
    worker_seed = torch.initial_seed() % (2 ** 32)
    random.seed(worker_seed)
    np.random.seed(worker_seed)


def create_data_loaders(manifest_dir=DEFAULT_MANIFEST_DIR, batch_size=32,
                        num_workers=0, seed=42, include_test=False):
    """Return train/valid loaders, optionally a separate test loader.

    Seeds CPU augmentation and shuffle RNGs when called; call once at training
    startup. CUDA training reproducibility is configured by the training script.
    Validation/test are ordered and unaugmented. Test is excluded by default.
    All samples are kept, including the final incomplete batch.
    Workers are not kept alive across phases, and each worker prefetches only
    one batch to limit RAM usage. Only small prepared crops are decoded.
    """
    if batch_size < 1 or num_workers < 0:
        raise ValueError("batch_size must be positive and num_workers nonnegative")
    if not 0 <= seed < 2 ** 32:
        raise ValueError("seed must be between 0 and 2**32 - 1")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    manifest_dir = Path(manifest_dir).resolve()
    splits = ("train", "valid", "test") if include_test else ("train", "valid")
    loaders = {}
    for split_index, split in enumerate(splits):
        dataset = RiceGrainDataset(manifest_dir / f"{split}.csv", train=(split == "train"))
        options = {
            "batch_size": batch_size,
            "shuffle": split == "train",
            "num_workers": num_workers,
            "pin_memory": torch.cuda.is_available(),
            "drop_last": False,
            "worker_init_fn": seed_worker,
            "generator": torch.Generator().manual_seed(seed + split_index),
        }
        if num_workers > 0:
            # Release training workers before validation starts; do not keep
            # two worker pools resident on memory-constrained laptops.
            options.update(persistent_workers=False, prefetch_factor=1)
        loaders[split] = DataLoader(dataset, **options)
    return loaders


def main():
    parser = argparse.ArgumentParser(description="Inspect training/validation batches from prepared PNG crops.")
    parser.add_argument("--manifests", type=Path, default=DEFAULT_MANIFEST_DIR,
                        help="Directory containing prepared crop CSVs and crop_info.json")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--num-workers", type=int, default=0)
    args = parser.parse_args()
    loaders = create_data_loaders(args.manifests, args.batch_size, args.num_workers)
    for split, loader in loaders.items():
        images, labels = next(iter(loader))
        print(f"{split}: {len(loader.dataset)} grains, {len(loader)} batches")
        print(f"  Images: shape={tuple(images.shape)}, dtype={images.dtype}")
        print(f"  Labels: shape={tuple(labels.shape)}, dtype={labels.dtype}")
        print(f"  Class IDs in batch: {labels.unique().tolist()}")
    print("Batch inspection finished. No model was trained; test data was not loaded.")


if __name__ == "__main__":
    main()
