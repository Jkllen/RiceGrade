# RiceGrade classification integration

This delivery freezes the existing classifier selected by validation macro F1. It never retrains EfficientNet-B0 or XGBoost. The application must supply an RGB image **and one binary instance mask per grain**. Automatic segmentation is a separate development task; this pipeline is not yet fully automatic. The four categories do not establish an official rice quality grade.

## Frozen model selection

| Configuration | Validation accuracy | Macro precision | Macro recall | Macro F1 |
|---|---:|---:|---:|---:|
| Hybrid (1280 CNN + 16 OpenCV) | 90.2844% | 89.2394% | 88.4983% | 88.8257% |
| CNN-only XGBoost | 90.1264% | 89.1628% | 88.2554% | 88.6444% |
| OpenCV-only XGBoost | 88.6256% | 86.7370% | 87.0145% | 86.8662% |

The existing hybrid model wins by validation macro F1. Its margin over CNN-only is 0.1813 percentage points; this small difference does not prove statistical superiority. Selection is recorded in `models/final_ricegrade/model_selection.json` before any new test inference. The saved comparison model uses XGBoost best iteration 87 (zero-based), reported as boosting round 88 in the comparison CSV. Prediction uses the sklearn interface, which [automatically honors best_iteration](https://xgboost.readthedocs.io/en/stable/python/sklearn_estimator.html).

## Files to deploy

Copy the `ricegrade/` package and the complete `models/final_ricegrade/` folder into the application. The bundle contains:

- `efficientnet_b0.pth`: unchanged copy of the trained epoch-18 checkpoint.
- `xgboost.json`: unchanged copy of the selected comparison model.
- `feature_schema.json`: unchanged training schema; its historical absolute checkpoint path is provenance only. Runtime loading uses bundle-relative filenames.
- `class_labels.json`: ordered class names, with indices 0 through 3.
- `preprocessing.json`: complete input, crop, normalization, precision, and feature-order contract.
- `model_selection.json`: validation comparison, selection rule, and original file hashes.
- `manifest.json`: relative filenames, artifact checksums, runtime versions, and selected configuration.

Initialize the predictor once at application startup. Loading checks model hashes, class order, feature order, schema, and the saved early-stopping iteration. Missing or incompatible models raise `ModelLoadError`.

## Dependencies

The existing project `.venv` already contains the required dependencies and was used for verification. Do not reinstall packages there to run this delivery. A clean Python 3.11 integration environment can use the tested versions:

```powershell
python -m venv .venv-inference
.\.venv-inference\Scripts\Activate.ps1
python -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu118
python -m pip install -r requirements-inference.txt
```

For a CPU-only deployment, replace the Torch index with `https://download.pytorch.org/whl/cpu`. These wheel commands follow the [official PyTorch previous-version installation instructions](https://pytorch.org/get-started/previous-versions/). In a clean environment install only the pinned headless OpenCV distribution; multiple OpenCV distributions can share and overwrite the same `cv2` module.

Evaluation and the COCO smoke check additionally need:

```powershell
python -m pip install -r requirements-evaluation.txt
```

Inference does not need the original training scripts, training images, COCO JSON files, or evaluation libraries when masks are already available.

## Application API

Run the application with the project root on its Python import path, or vendor `ricegrade/` beside your application module.

```python
from pathlib import Path
import numpy as np
from PIL import Image
from ricegrade import RiceGradePredictor, ModelLoadError

predictor = RiceGradePredictor(Path("models/final_ricegrade"), device="auto")
with Image.open("rice_photo.jpg") as image:
    rgb = np.array(image.convert("RGB"))

# The segmentation component must return one mask per individual grain.
# masks: iterable of boolean/uint8 arrays, each shape (image_height, image_width).
result = predictor.predict(rgb, masks)
print(result["counts"])
print(result["percentages"])
for grain in result["grains"]:
    print(grain["category"], grain["confidence"], grain["confidence_scores"])
```

Input RGB pixels must be uint8, shape `(H,W,3)`; an RGB PIL image is also accepted. Convert OpenCV BGR images to RGB explicitly. Each instance mask must match the original image dimensions, have at least one foreground pixel, and contain boolean values, 0/1, or 0/255. A single 2D mask is accepted; a stack `(N,H,W)` or a generator supports multiple grains. Missing, empty, wrong-size, nonbinary masks and invalid images raise `ValueError`. Do not pass one mask containing several independent grains unless they intentionally represent one instance.

The result is JSON-serializable and contains:

- `grains`: grain index, original pixel bounding box `[x,y,width,height]`, class ID, category, top confidence, and a score for every class.
- `counts`: counts for all four categories, including zero counts.
- `percentages`: percentages by **grain count**, not rice weight or volume.
- `total_grains` and `selected_configuration`.

Class order is fixed: `broken_grain`, `chalky_grain`, `discolored_grain`, `whole_grain`. Confidence values are model probabilities; they have not been calibrated as guaranteed correctness.

Each mask is cropped using its exact bounds, background pixels are blackened, and PIL bicubic padding preserves aspect ratio at 224 x 224. No augmentation is performed. Inputs use ImageNet mean `[0.485,0.456,0.406]` and standard deviation `[0.229,0.224,0.225]`. The entire EfficientNet classifier is removed to expose 1,280 pooled features. CUDA extraction uses FP16 autocast, matching the original feature schema, and emits float32 features. CPU uses FP32; numerical differences can affect samples close to tree thresholds, so compare deployment validation behavior before changing precision or batch settings.

The 16 OpenCV features retain original pixel geometry, all connected components and hole boundaries, and the original thin-mask fallback. Hybrid input order is `cnn_0000` through `cnn_1279`, followed by the schema's 16 OpenCV columns. Colors, shape, grayscale texture, entropy, feature units, and ordering match extraction version 3. Grain pixel size and image capture conditions affect these features; changing photo scale/background requires separate deployment validation.

## Example and smoke check

The command-line example consumes a saved NPZ containing binary `masks` with shape `(N,H,W)`:

```powershell
python examples/predict_with_masks.py rice_photo.jpg supplied_masks.npz --bundle models/final_ricegrade
python smoke_test_ricegrade.py
```

The smoke script uses 32 validation grains and two thin training masks. It checks exact crop and OpenCV feature parity against the original extractor and saved features, CNN feature agreement, prediction agreement, probability/count output, invalid inputs, and missing/corrupt model errors. It does not read the held-out test set or train models. It intentionally imports the original extractor as a verification reference; the application package never imports it.

## Held-out evaluation and reproducibility

The frozen hybrid model was evaluated once on **1,211 grains from 95 held-out source images**, using CUDA AMP and batch size 32:

| Test metric | Result |
|---|---:|
| Accuracy | 90.9992% |
| Macro precision | 90.9381% |
| Macro recall | 89.0077% |
| Macro F1 | 89.6901% |

These scores did not change the selected model or its parameters. The complete per-class results are in the saved classification report.

`results/final_ricegrade_test/` contains `metrics.json`, a text/CSV classification report, a confusion matrix CSV/PNG, per-grain predictions with class probabilities, aligned test feature arrays, and original-order metadata. These are independent of training/validation outputs. Test features use ground-truth COCO masks rasterized by pycocotools, including fractional polygon coordinates and RLE support. Every test image is checked for identical PIL/OpenCV RGB decoding. The evaluator checks source/image separation from train and validation and retains row identifiers.

The dedicated scripts are reproducibility tools, not prerequisites for application inference:

```powershell
python finalize_ricegrade.py --output models/a_new_frozen_bundle
python evaluate_ricegrade.py --bundle models/a_new_frozen_bundle --output results/a_new_test_evaluation
```

Both commands refuse to replace an existing output directory. Use the delivered completed test results; do not repeatedly evaluate while tuning or select configurations using test scores. The evaluator performs only forward inference. Evaluation timing includes mask decoding and report writing, and is not an application latency benchmark.

## Separate segmentation task

Ordinary uploaded photographs do not contain COCO annotations. A future OpenCV component must detect and isolate individual grains and pass its binary masks to the same `predict` function. It needs its own segmentation accuracy, touching-grain, missed-grain, and image-condition tests, followed by evaluation of the combined segmentation/classification pipeline on new images. Until then, this delivery supports **classification with supplied masks**. Any screening recommendations or official grading rules require separately defined and validated criteria.
