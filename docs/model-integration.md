# Model training snapshot — integration postponed

This UI-first milestone deliberately keeps model inference inactive. The provided `RiceGrade-training-model.zip` contains a PyTorch EfficientNet-B0 training script, dataset preparation/dataloader scripts, a checkpoint, and per-grain CSV manifests. None of these are exposed as a finished four-class prediction service.

## Inspected training snapshot

- `train_efficientnet.py`: starts from ImageNet-pretrained `torchvision.models.efficientnet_b0` and **replaces its classifier with a four-output linear head**; trains the whole network with CrossEntropyLoss.
- `full_manifests/class_mapping.json`: `broken_grain:0`, `chalky_grain:1`, `discolored_grain:2`, `whole_grain:3`.
- `rice_dataset.py`: extracts grain crops using COCO annotations, black background masking, square padding to 224×224, ImageNet normalization, plus flip/rotation augmentations **in the PyTorch training loader**. Roboflow having no augmentation is consistent with this script performing it later.
- `full_manifests/dataset_statistics.json`: 15,024 train, 1,266 validation and 1,211 test annotated grain instances; these are counts reported by the file, not independently validated benchmark metrics.
- `results/version_1/training_history.csv`: contains **one epoch's row** in the uploaded snapshot. Do not interpret that as proof that all 50 epochs finished or claim validation has been completed.
- `models/version_1/best_efficientnet_b0.pth`: a checkpoint was included, but not installed as a production model.
- The manifest's `image_path` and `annotation_path` values are absolute **Windows-specific paths**. They must be regenerated or resolved to current dataset locations before rerunning on another machine.

## Planned integration milestones

1. Wait for the final trained checkpoint and reproducible final evaluation. Preserve dataset split boundaries by source image/lot.
2. Validate the OpenCV operational segmentation on local test-mill images (separate from COCO ground-truth masks used to prepare training crops).
3. Decide whether to reuse EfficientNet-B0 as a **deep feature extractor**, extracting embeddings from the appropriate intermediate layer; this is different from simply returning its four-class classifier output.
4. Extract validated OpenCV morphological, color, and texture features; align by grain ID and concatenate with deep embeddings.
5. Train/validate the **separate XGBoost four-class final classifier** using fused features; evaluate independent holdouts and comparisons against baselines.
6. Connect the inference API to the draft assessment workflow. Only then enable sample-level class counts, confidence handling, DSS interpretations and final reports. Do not invent interim ML scores.

Note: these observations refer to the uploaded snapshot only. They do not establish the current state of the teammate's actively running training job.
