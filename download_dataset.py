
from pathlib import Path
from roboflow import Roboflow

# =====================================
# 1. CONFIGURATION
# =====================================

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "datasets" / "version_1"

# =====================================
# 2. CHECK EXISTING DATASET
# =====================================

required_files = [
    DATASET_DIR / split / "_annotations.coco.json"
    for split in ["train", "valid", "test"]
]

if all(file.exists() for file in required_files):
    print("Dataset already exists. Download skipped.")

else:
    if DATASET_DIR.exists() and any(DATASET_DIR.iterdir()):
        raise RuntimeError(
            "Dataset folder is not empty. "
            "Check its contents before downloading again."
        )

    # =====================================
    # 3. CONNECT TO ROBOFLOW
    # =====================================

    rf = Roboflow(api_key="CVAdxSjRdwkbYgDpBhG1")

    project = rf.workspace(
        "augustine-barredo"
    ).project(
        "grainalyze-zuuf6"
    )

    # =====================================
    # 4. DOWNLOAD VERSION 1
    # =====================================

    print("\nDownloading Grainalyze Version 1...")

    dataset = project.version(1).download(
        "coco-segmentation",
        location=str(DATASET_DIR)
    )

    print("\nDownload completed!")
    print("Dataset location:", dataset.location)

# =====================================
# 5. VERIFY DATASET STRUCTURE
# =====================================

for split in ["train", "valid", "test"]:
    annotation_file = (
        DATASET_DIR / split / "_annotations.coco.json"
    )

    print(
        split,
        "FOUND" if annotation_file.exists() else "MISSING"
    )

print("\nDataset verification finished!")
