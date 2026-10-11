
import csv
import json
from pathlib import Path
from collections import Counter

import numpy as np
from pycocotools.coco import COCO

# =====================================
# 1. CONFIGURATION
# =====================================

BASE = Path(__file__).resolve().parent

DATASET = BASE / "datasets" / "version_1"

OUTPUT = BASE / "full_manifests"
OUTPUT.mkdir(parents=True, exist_ok=True)

SPLITS = ["train", "valid", "test"]

CLASSES = [
    "broken_grain",
    "chalky_grain",
    "discolored_grain",
    "whole_grain"
]

CLASS_TO_ID = {
    name: index
    for index, name in enumerate(CLASSES)
}

# =====================================
# 2. DATASET VERIFICATION
# =====================================

if not DATASET.is_dir():
    raise FileNotFoundError(
        f"Dataset not found: {DATASET}"
    )

split_sources = {}
statistics = {}

for split in SPLITS:

    folder = DATASET / split
    annotation_file = (
        folder / "_annotations.coco.json"
    )

    coco = COCO(str(annotation_file))

    rows = []
    counts = Counter()
    skipped = Counter()
    sources = set()

    for image_id in coco.getImgIds():

        image_info = coco.imgs[image_id]

        image_path = (
            folder / image_info["file_name"]
        )

        if not image_path.is_file():
            raise FileNotFoundError(image_path)

        source_id = (
            Path(image_info["file_name"])
            .name.split(".rf.")[0]
        )

        sources.add(source_id)

        annotations = coco.imgToAnns.get(
            image_id, []
        )

        for ann in annotations:

            category = coco.cats[
                ann["category_id"]
            ]["name"]

            if category not in CLASS_TO_ID:
                skipped["other_category"] += 1
                continue

            if ann.get("iscrowd", 0):
                skipped["crowd"] += 1
                continue

            try:
                mask = coco.annToMask(ann)
            except Exception:
                skipped["invalid_mask"] += 1
                continue

            if (
                mask.shape != (
                    image_info["height"],
                    image_info["width"]
                )
                or not np.any(mask)
            ):
                skipped["empty_or_wrong_mask"] += 1
                continue

            rows.append({
                "image_path": str(image_path.resolve()),
                "annotation_path": str(
                    annotation_file.resolve()
                ),
                "image_id": image_id,
                "annotation_id": ann["id"],
                "source_id": source_id,
                "label": category,
                "class_id": CLASS_TO_ID[category]
            })

            counts[category] += 1

    # Save grain-level manifest
    output_file = OUTPUT / f"{split}.csv"

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "image_path",
                "annotation_path",
                "image_id",
                "annotation_id",
                "source_id",
                "label",
                "class_id"
            ]
        )

        writer.writeheader()
        writer.writerows(rows)

    split_sources[split] = sources

    statistics[split] = {
        "images": len(coco.getImgIds()),
        "grain_objects": len(rows),
        "classes": dict(counts),
        "skipped": dict(skipped)
    }

    print(f"\n{'=' * 40}")
    print(split.upper())
    print(f"{'=' * 40}")

    print("Images:", len(coco.getImgIds()))
    print("Valid grain objects:", len(rows))

    for label in CLASSES:
        print(f"{label}: {counts[label]}")

    print("Skipped:", dict(skipped))

    if any(counts[label] == 0 for label in CLASSES):
        raise RuntimeError(
            f"Missing required class in {split}"
        )

# =====================================
# 3. CHECK DATA LEAKAGE
# =====================================

print("\nDATASET LEAKAGE CHECK")

for a, b in [
    ("train", "valid"),
    ("train", "test"),
    ("valid", "test")
]:

    overlap = split_sources[a] & split_sources[b]

    print(f"{a} vs {b}: {len(overlap)} overlaps")

    if overlap:
        raise RuntimeError(
            f"Data leakage detected: {a} vs {b}"
        )

# =====================================
# 4. SAVE METADATA
# =====================================

with open(
    OUTPUT / "class_mapping.json",
    "w",
    encoding="utf-8"
) as file:
    json.dump(CLASS_TO_ID, file, indent=4)

with open(
    OUTPUT / "dataset_statistics.json",
    "w",
    encoding="utf-8"
) as file:
    json.dump(statistics, file, indent=4)

print("\nFULL DATASET PREPARATION COMPLETED!")
print("Saved to:", OUTPUT)
