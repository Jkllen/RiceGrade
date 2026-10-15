# RiceGrade Model Training

Trained EfficientNet-B0 and XGBoost models for classifying rice grains. This repository provides the models, evaluation results, and sample code for testing new photos.

Classes: `broken_grain`, `chalky_grain`, `discolored_grain`, and `whole_grain`.

## Features

- Separate grains from plain black, white, or light gray backgrounds.
- Classify each detected grain using black-masked crops.
- Save labeled photos, grain counts, and class probabilities.

## Technologies

Python, PyTorch, Torchvision, XGBoost, OpenCV, NumPy, Pillow, and scikit-learn. Shared prediction modules also require pycocotools and tqdm.

## Setup

Run these commands from the project folder in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install `torch` and `torchvision` using the [official PyTorch installer](https://pytorch.org/get-started/locally/) for your CPU or CUDA hardware. Then install the remaining dependencies:

```powershell
python -m pip install numpy pillow opencv-python pycocotools tqdm xgboost scikit-learn
```

On another computer, update these saved paths to point to the included model files. Paths relative to the project root are supported.

| File | Field to update |
| --- | --- |
| `results/xgboost/model_selection.json` | `model`: selected XGBoost model |
| `results/xgboost/feature_schema.json` | `checkpoint`: matching EfficientNet checkpoint |

These instructions use Windows. Other operating systems may require adapting the Windows paths in the metadata readers.

## Test an Image

Set your actual photo path near the top of `predict_image.py`:

```python
IMAGE_PATH = r"C:\path\to\your_photo.jpg"
```

Run:

```powershell
python predict_image.py
```

Background selection is automatic. Add `--background light` for white or gray surfaces, or `--background black` for black surfaces.

Results are saved in `results/image_prediction/`:

- `annotated.png`: detected grains, labels, and confidence scores.
- `masked_grains.png`: separated grains on black for checking the masks.
- `predictions.json`: counts, percentages by count, and individual predictions.

Each successful run replaces these three files. Use separate grains on a plain, evenly lit surface and check both output images. Touching grains, shadows, and low contrast can cause incorrect detection. Keep the original photo resolution because shape features use pixel measurements.

## Evaluation Results

The saved hybrid model achieved **90.42% accuracy** and **0.8908 macro F1** on **1,211 test grains using ground-truth masks**. Automatic photo segmentation needs separate checking.

See the [classification report](results/test_evaluation/classification_report.txt) and [confusion matrix](results/test_evaluation/confusion_matrix.png).
