# RiceGrade Model Training and Inference

RiceGrade classifies individual rice grains using **EfficientNet-B0, OpenCV, and XGBoost**. EfficientNet-B0 supplies 1,280 learned features and OpenCV supplies 16 engineered features. The selected hybrid XGBoost model uses all 1,296 features to predict one of four grain categories.

**Current status:** training, feature extraction, model comparison, final model packaging, and held-out classification evaluation are complete. The reusable prediction module is ready for application integration **with supplied grain masks**. Automatic grain segmentation and a photo-upload application are separate development tasks.

## Classes

Class indices are fixed across the checkpoint, feature files, and XGBoost model:

| Class ID | Category |
|---|---|
| 0 | `broken_grain` |
| 1 | `chalky_grain` |
| 2 | `discolored_grain` |
| 3 | `whole_grain` |

These categories support rice screening. They do not independently establish an official rice quality grade.

## How prediction works

```text
RGB image + individual grain masks
                 |
        Masked grain extraction
                 |
       +---------+----------+
       |                    |
EfficientNet-B0         OpenCV measurements
1,280 features         16 features
       |                    |
       +---------+----------+
                 |
          Hybrid XGBoost
                 |
     Grain categories and confidence scores
                 |
       Counts and percentages
```

A grain mask is a binary image identifying the pixels belonging to one grain. Ordinary rice photos do not already contain these masks. Current dataset processing decodes masks from COCO annotations; application callers can supply masks from any separately validated segmentation component.

## Project structure

```text
RiceGrade_Model_Training/
|-- datasets/version_1/             # Source images and COCO annotations
|-- full_manifests/                 # Train/validation/test CSVs and dataset statistics
|-- models/
|   |-- version_1/                  # Original trained checkpoints and experiments
|   `-- final_ricegrade/            # Frozen deployment bundle
|-- results/
|   |-- version_1/                  # Training history, features, and validation comparisons
|   |-- final_ricegrade_test/       # Separate held-out test results
|   `-- final_ricegrade_checks/     # Smoke checks and file-preservation evidence
|-- ricegrade/
|   |-- features.py                 # Frozen preprocessing and OpenCV feature calculations
|   `-- inference.py                # Reusable prediction API
|-- examples/predict_with_masks.py  # Command-line prediction example
|-- train_efficientnet.py
|-- extract_features.py
|-- train_xgboost.py
|-- finalize_ricegrade.py
|-- evaluate_ricegrade.py
|-- smoke_test_ricegrade.py
|-- requirements-inference.txt
|-- requirements-evaluation.txt
`-- RICEGRADE_INTEGRATION.md
```

Dataset files are excluded from Git by `.gitignore`. Training and dataset tools need locally available source images and COCO annotations. Runtime inference needs the `ricegrade/` package and the complete finalized model bundle.

## Setup

Use Python 3.11. Run commands from the project root.

If the existing project virtual environment is available, activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

For a clean inference environment, follow the CUDA or CPU installation commands in [RICEGRADE_INTEGRATION.md](RICEGRADE_INTEGRATION.md#dependencies). The tested dependencies are listed in [requirements-inference.txt](requirements-inference.txt). Evaluation and COCO smoke checks also need [requirements-evaluation.txt](requirements-evaluation.txt).

The existing trained models can be used immediately; starting a training script is not required for prediction.

## Run prediction with supplied masks

Prepare an RGB image and a matching NPZ file containing an array named `masks` with shape `(N, H, W)`. Each of the `N` masks identifies one grain in the original image, whose dimensions are `H` by `W`.

Replace the example paths with your image and mask file:

```powershell
python examples/predict_with_masks.py rice_photo.jpg grain_masks.npz --bundle models/final_ricegrade
```

The default device is `auto`: CUDA when available, otherwise CPU. To request CPU explicitly:

```powershell
python examples/predict_with_masks.py rice_photo.jpg grain_masks.npz --bundle models/final_ricegrade --device cpu
```

This command prints JSON containing each grain's category, bounding box, confidence scores, and the overall counts and percentages. It does not create masks from the uploaded image.

## Use the Python API

Load the predictor once at application startup, then reuse it for subsequent images:

```python
import numpy as np
from PIL import Image
from ricegrade import RiceGradePredictor

predictor = RiceGradePredictor("models/final_ricegrade", device="auto")

with Image.open("rice_photo.jpg") as image:
    rgb = np.array(image.convert("RGB"))
with np.load("grain_masks.npz", allow_pickle=False) as data:
    masks = data["masks"]

result = predictor.predict(rgb, masks)
print(result["counts"])
print(result["percentages"])

for grain in result["grains"]:
    print(grain["category"], grain["confidence"])
```

Input requirements:

- Image: RGB `uint8` array with shape `(H, W, 3)`, or an RGB PIL image. Convert OpenCV BGR input to RGB before prediction.
- Masks: one nonempty binary mask per grain, each matching the original image dimensions. Boolean, 0/1, and 0/255 masks are supported.
- A stack of masks, a list, or a generator can be passed to the API; a single 2D mask is also accepted. The command-line example requires a 3D mask stack.

Invalid inputs raise `ValueError`. Missing, corrupted, or incompatible model artifacts raise `ModelLoadError`. Confidence values are model probabilities rather than calibrated guarantees. Percentages are calculated by grain count, not by weight or volume.

See [the integration guide](RICEGRADE_INTEGRATION.md#application-api) for the output structure, preprocessing contract, deployment files, and numerical precision notes.

## Finalized model bundle

The [models/final_ricegrade](models/final_ricegrade/) directory contains:

| File | Purpose |
|---|---|
| `efficientnet_b0.pth` | Trained EfficientNet-B0 checkpoint, selected at epoch 18 |
| `xgboost.json` | Selected saved hybrid XGBoost model |
| `feature_schema.json` | Training feature definitions and ordering |
| `class_labels.json` | Ordered class names |
| `preprocessing.json` | Input preparation and precision configuration |
| `model_selection.json` | Validation-based selection and source artifact hashes |
| `manifest.json` | Bundle checksums and configuration |

Deploy the entire bundle together with `ricegrade/`. The model loader checks artifact hashes, feature order, and class indices. Original experiment files in `models/version_1/` and `results/version_1/` remain separate from deployment artifacts.

## Dataset

The saved [dataset statistics](full_manifests/dataset_statistics.json) describe the usable grain records:

| Split | Source images | Grain instances |
|---|---:|---:|
| Training | 1,610 | 15,024 |
| Validation | 95 | 1,266 |
| Held-out test | 95 | 1,211 |
| Total | 1,800 | 17,501 |

Source image counts and grain instance counts are different: one image can contain several grains. Three annotations with empty or incorrect masks were excluded during manifest preparation. The CSV manifests contain dataset file paths; moving the source dataset requires resolving or regenerating those paths for dataset-dependent scripts.

## Validation-based model selection

The selected configuration was chosen using **validation macro F1**, before final test inference:

| Configuration | Accuracy | Macro precision | Macro recall | Macro F1 |
|---|---:|---:|---:|---:|
| Hybrid | 90.28% | 89.24% | 88.50% | **88.83%** |
| CNN-only XGBoost | 90.13% | 89.16% | 88.26% | 88.64% |
| OpenCV-only XGBoost | 88.63% | 86.74% | 87.01% | 86.87% |

The hybrid's macro F1 advantage over CNN-only is approximately 0.18 percentage points. This small difference does not establish statistical superiority. See the [original comparison](results/version_1/xgboost_v3_compare/comparison.csv) and [frozen selection record](models/final_ricegrade/model_selection.json).

## Held-out test results

The frozen hybrid model was evaluated on **1,211 grains from 95 held-out images** using ground-truth COCO masks, CUDA mixed precision, and batch size 32. No model was retrained or selected using these test results.

| Metric | Result |
|---|---:|
| Accuracy | **91.00%** |
| Macro precision | 90.94% |
| Macro recall | 89.01% |
| Macro F1 | 89.69% |

Chalky-grain recall is 74.73%, the weakest per-class recall in this evaluation. These results measure classification with supplied masks; they do not measure automatic segmentation or performance on arbitrary uploaded photos.

Saved outputs:

- [Metrics and evaluation provenance](results/final_ricegrade_test/metrics.json)
- [Per-class classification report](results/final_ricegrade_test/classification_report.txt)
- [Confusion matrix](results/final_ricegrade_test/confusion_matrix.png)
- [Per-grain predictions](results/final_ricegrade_test/predictions.csv)
- `results/final_ricegrade_test/test_features.npz` and `test_metadata.csv`, preserving feature/label row alignment

## Verification and development scripts

To check the existing pipeline with validation grains and thin-mask examples:

```powershell
python smoke_test_ricegrade.py
```

The smoke test checks preprocessing and feature parity, predicted labels, input validation, missing/corrupt models, and COCO RLE decoding. It needs the original validation/training data and saved validation features, and does not train models or read the test split. Saved verification evidence is in [results/final_ricegrade_checks](results/final_ricegrade_checks/).

| Script | Purpose |
|---|---|
| `download_dataset.py` | Retrieve the configured source dataset when unavailable |
| `prepare_dataset.py` | Build grain manifests, class mapping, and dataset statistics |
| `rice_dataset.py` | COCO-backed grain crops and training/evaluation transforms |
| `check_dataloader.py` | Inspect dataset batches |
| `train_efficientnet.py` | Train the EfficientNet-B0 classifier |
| `evaluate_efficientnet.py` | Evaluate the saved CNN classifier separately |
| `extract_features.py` | Extract CNN and OpenCV features using COCO masks |
| `train_xgboost.py` | Train and compare classifiers using saved training/validation features |
| `finalize_ricegrade.py` | Select existing models using validation results and create a new bundle |
| `evaluate_ricegrade.py` | Evaluate an already frozen bundle on held-out COCO-masked grains |
| `smoke_test_ricegrade.py` | Verify feature parity and runtime behavior |

Training and evaluation have already been completed. Use the saved reports for the finalized experiment. The finalization and hybrid evaluation scripts refuse to replace existing output directories. Reproducibility commands with fresh output paths are documented in [RICEGRADE_INTEGRATION.md](RICEGRADE_INTEGRATION.md#held-out-evaluation-and-reproducibility); keep test results separate from model tuning and preserve existing artifacts.

## Remaining system work

1. Implement and evaluate automatic grain segmentation as a separate component.
2. Pass its individual grain masks to `RiceGradePredictor.predict`.
3. Test the combined segmentation/classification pipeline on new photos, including missed grains and touching grains.
4. Integrate image capture/upload and result display into the application.
5. Define and validate any screening recommendations or grading rules separately.

A plain dark background with separated grains is the planned capture setup for future segmentation. This setup has not yet been validated as an automatic system.
