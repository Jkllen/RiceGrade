"""Classify a prepared dataset grain, or an image with a supplied mask.

Run manually: python predict_grain.py
By default, predicts the first grain in grain_crops_test/test.csv using its COCO mask.
For new images, supply --image and --mask with actual file paths.
This script does not detect or segment grains automatically.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from pycocotools.coco import COCO

from data_loader import (
    CLASSES, DEFAULT_MANIFEST_DIR, ROOT, RiceGrainDataset, build_transform, resolve_record_path,
)
from evaluate_model import DEFAULT_SELECTION, load_selection
from extract_features import CNN_FEATURE_COUNT, grain_mask, load_model, sha256_file
from grain_features import extract_opencv_features
from train_xgboost import feature_matrix


def prepare_grain(image_path, mask_path):
    """Make the original-resolution black-background crop used during training."""
    with Image.open(image_path) as image, Image.open(mask_path) as mask_image:
        if mask_image.mode not in ("1", "L"):
            raise ValueError("Mask must be a binary or grayscale image; save it as a lossless PNG")
        if image.size != mask_image.size:
            raise ValueError("Image and mask must have the same dimensions")
        values = {value for value, count in enumerate(mask_image.histogram()) if count}
        if not (values <= {0, 1} or values <= {0, 255}):
            raise ValueError("Mask must contain only 0/1 or 0/255: background is 0")
        bounds = mask_image.getbbox()
        if bounds is None:
            raise ValueError("Mask contains no foreground grain pixels")
        rgb = np.array(image.crop(bounds).convert("RGB"))
        mask = np.array(mask_image.crop(bounds), dtype=np.uint8) != 0
    rgb[~mask] = 0
    return rgb, mask


def load_sample(manifest_path, index):
    """Load one cached grain and its true mask from the original COCO annotations."""
    dataset = RiceGrainDataset(manifest_path, train=False)
    if not 0 <= index < len(dataset):
        raise ValueError(f"Sample index must be between 0 and {len(dataset) - 1}")
    record = dataset.records[index]
    source_dir = Path(dataset.crop_info["source_manifest_dir"])
    annotation_path = resolve_record_path(record["annotation_path"], source_dir)
    split = dataset.manifest_path.stem
    hashes = dataset.crop_info["splits"][split]["source_annotation_sha256"]
    if sha256_file(annotation_path) != hashes.get(str(annotation_path)):
        raise ValueError(f"Annotations changed since grain preparation: {annotation_path}")
    mask = grain_mask(COCO(str(annotation_path)), record)
    with Image.open(record["crop_path"]) as image:
        if image.format != "PNG" or image.mode != "RGB":
            raise ValueError(f"Expected an RGB PNG grain crop: {record['crop_path']}")
        rgb = np.array(image)
    return rgb, mask, {
        "image": record["crop_path"], "sample_index": index,
        "annotation_id": record["annotation_id"], "expected_class": record["class_name"],
    }


class GrainPredictor:
    """Load the selected models once, then reuse them for individual grains."""

    def __init__(self, selection_path=DEFAULT_SELECTION,
                 training_manifests=DEFAULT_MANIFEST_DIR, device="auto"):
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; choose --device cpu")
        training_manifests = Path(training_manifests).resolve()
        self.selection, self.schema, self.classifier = load_selection(
            Path(selection_path).resolve(), training_manifests,
        )
        checkpoint = resolve_record_path(self.schema["checkpoint"], ROOT)
        self.model, epoch = load_model(checkpoint, training_manifests, self.device)
        if epoch != self.schema["checkpoint_epoch"]:
            raise ValueError("CNN checkpoint epoch differs from the saved feature schema")
        self.transform = build_transform(train=False)

    def predict(self, image_path, mask_path):
        rgb, mask = prepare_grain(image_path, mask_path)
        return self.predict_arrays(rgb, mask)

    def predict_arrays(self, rgb, mask):
        """Classify a tight, original-resolution RGB grain crop and its foreground mask."""
        rgb, mask = np.asarray(rgb), np.asarray(mask, dtype=bool)
        opencv = extract_opencv_features(rgb, mask)[None, :]
        rgb = rgb.copy()
        rgb[~mask] = 0
        tensor = self.transform(Image.fromarray(rgb)).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            cnn = self.model(tensor).cpu().numpy()
        if cnn.shape != (1, CNN_FEATURE_COUNT) or not np.isfinite(cnn).all():
            raise ValueError("CNN returned invalid grain features")
        features = feature_matrix({"cnn_features": cnn, "opencv_features": opencv},
                                  self.selection["selected_mode"])
        probabilities = self.classifier.predict_proba(
            features, iteration_range=tuple(self.selection["prediction_iteration_range"]),
        )
        if (probabilities.shape != (1, len(CLASSES)) or not np.isfinite(probabilities).all()
                or np.any(probabilities < 0) or np.any(probabilities > 1)
                or not np.allclose(probabilities.sum(axis=1), 1, atol=1e-5)):
            raise ValueError("Classifier returned invalid class probabilities")
        scores = probabilities[0]
        index = int(scores.argmax())
        return {
            "class_name": CLASSES[index], "confidence": float(scores[index]),
            "probabilities": {name: float(value) for name, value in zip(CLASSES, scores)},
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=None, help="New grain image or original photo")
    parser.add_argument("--mask", type=Path, default=None,
                        help="Same-size binary mask selecting ONE grain; 0 background, 1 or 255 foreground")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="Prepared grain CSV (default: grain_crops_test/test.csv)")
    parser.add_argument("--index", type=int, default=None, help="Dataset row to predict, starting at 0 (default: 0)")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--training-manifests", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--output", type=Path, default=None, help="Optional new JSON output file")
    args = parser.parse_args()
    if (args.image is None) != (args.mask is None):
        parser.error("Supply both --image and --mask, or neither to use a dataset sample")
    if args.image is not None and (args.manifest is not None or args.index is not None):
        parser.error("Choose image/mask files or a dataset sample; do not combine them")
    if args.index is not None and args.index < 0:
        parser.error("index must be nonnegative")
    if args.output is not None and args.output.exists():
        raise FileExistsError(f"Use a new output file; already exists: {args.output}")

    if args.image is not None:
        image_path, mask_path = args.image.resolve(), args.mask.resolve()
        for path in (image_path, mask_path):
            if not path.is_file():
                parser.error(f"Input file does not exist: {path}. To try an existing grain, run python predict_grain.py")
        rgb, mask = prepare_grain(image_path, mask_path)
        details = {"image": str(image_path), "mask": str(mask_path)}
    else:
        manifest = (args.manifest or ROOT / "grain_crops_test/test.csv").resolve()
        if not manifest.is_file():
            parser.error("Prepared sample manifest not found. Run python prepare_grains.py --splits test "
                         "--output grain_crops_test, or supply real --image and --mask files")
        rgb, mask, details = load_sample(manifest, args.index if args.index is not None else 0)

    predictor = GrainPredictor(args.selection, args.training_manifests, args.device)
    result = {**details, **predictor.predict_arrays(rgb, mask)}
    text = json.dumps(result, indent=2, allow_nan=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
