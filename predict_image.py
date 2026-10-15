"""Find and classify separate rice grains on black, white, or light gray surfaces.

Set IMAGE_PATH below, then run manually: python predict_image.py
You can also supply --image "path/to/photo.jpg" to override IMAGE_PATH.
Saves the latest annotated photo, black-masked preview, and predictions in
results/image_prediction/. Use --background light for white or gray photos.
Touching grains, strong shadows, and textured surfaces need further checking.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from data_loader import CLASSES, DEFAULT_MANIFEST_DIR, ROOT
from predict_grain import DEFAULT_SELECTION, GrainPredictor
from segment_grains import segment_grains


# Paste your photo path between the quotes. Keep the r prefix for Windows paths.
IMAGE_PATH = r"C:\Users\lawrence\Downloads\IMG_20260129_224124_257.jpg"

COLORS = dict(zip(CLASSES, ("orange", "deepskyblue", "hotpink", "limegreen")))


def annotate_image(rgb, grains):
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)
    font_size = max(12, min(image.size) // 100)
    font = ImageFont.load_default(size=font_size)
    padding = max(2, font_size // 5)
    line_width = max(2, font_size // 8)
    for grain in grains:
        x, y, width, height = grain["bbox_xywh"]
        color = COLORS[grain["class_name"]]
        draw.rectangle((x, y, x + width - 1, y + height - 1),
                       outline=color, width=line_width)
        name = grain["class_name"].replace("_grain", "").title()
        label = f"{grain['grain_id']}: {name} {grain['confidence']:.0%}"
        _, _, text_width, text_height = draw.textbbox((0, 0), label, font=font, anchor="lt")
        left = max(0, min(x, image.width - text_width - 2 * padding))
        top = max(0, y - text_height - 2 * padding)
        draw.rectangle((left, top, left + text_width + 2 * padding,
                        top + text_height + 2 * padding), fill=color)
        draw.text((left + padding, top + padding), label, font=font, fill="black", anchor="lt")
    return image


def predict_image(image_path, predictor, min_area=None, threshold=None, background="auto"):
    """Return predictions, an annotated photo, and a black-masked grain preview."""
    image_path = Path(image_path).resolve()
    with Image.open(image_path) as source:
        ImageOps.exif_transpose(source, in_place=True)
        rgb = np.array(source.convert("RGB"))

    regions, segmentation = segment_grains(rgb, min_area, threshold, background)
    foreground = np.zeros(rgb.shape[:2], dtype=bool)
    grains = []
    for grain_id, (bounds, mask) in enumerate(regions, start=1):
        x, y, width, height = bounds
        prediction = predictor.predict_arrays(rgb[y:y + height, x:x + width], mask)
        foreground[y:y + height, x:x + width] |= mask
        grains.append({
            "grain_id": grain_id, "bbox_xywh": [int(value) for value in bounds],
            "mask_area_pixels": int(np.count_nonzero(mask)), **prediction,
        })
    if not grains:
        raise ValueError("No complete grains detected. Check --background (black or light), "
                         "--min-area, and --threshold. Use a plain, evenly lit surface.")

    counts = {name: sum(grain["class_name"] == name for grain in grains) for name in CLASSES}
    result = {
        "image": str(image_path),
        "image_size": {"width": int(rgb.shape[1]), "height": int(rgb.shape[0])},
        "coordinates": "EXIF-oriented image, original resolution; bbox = [x, y, width, height]",
        "total_grains": len(grains), "counts": counts,
        "percentages_by_count": {name: round(count * 100 / len(grains), 2)
                                 for name, count in counts.items()},
        "segmentation": {**segmentation, "classifier_background": "black"},
        "selected_mode": predictor.selection["selected_mode"],
        "model": predictor.selection["model"],
        "model_sha256": predictor.selection["model_sha256"],
        "cnn_checkpoint_sha256": predictor.selection["cnn_checkpoint_sha256"],
        "grains": grains,
    }
    annotated = annotate_image(rgb, grains)
    masked = Image.fromarray(rgb)
    masked.paste((0, 0, 0), mask=Image.fromarray(~foreground))
    return result, annotated, masked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="Photo path (overrides IMAGE_PATH above)")
    parser.add_argument("--output", type=Path, default=ROOT / "results/image_prediction",
                        help="Folder for the latest annotated photo, masked preview, and JSON predictions")
    parser.add_argument("--background", choices=("auto", "black", "light"), default="auto",
                        help="Photo background: light for white/gray, or auto to estimate from the border")
    parser.add_argument("--min-area", type=int, default=None,
                        help="Minimum grain mask area in pixels (default: adapts to photo size in light mode)")
    parser.add_argument("--threshold", type=int, default=None,
                        help="0..255: brightness for black mode, RGB difference for light (default: automatic)")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--training-manifests", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()
    image_path = args.image or IMAGE_PATH
    if not image_path:
        parser.error("Set IMAGE_PATH near the top of predict_image.py, or supply --image with a photo path")
    image_path, output = Path(image_path).resolve(), args.output.resolve()
    if not image_path.is_file():
        parser.error(f"Image does not exist: {image_path}. Supply the path to your actual photo.")
    if output.exists() and not output.is_dir():
        parser.error(f"Output must be a folder: {output}")
    if ((args.min_area is not None and args.min_area < 1)
            or (args.threshold is not None and not 0 <= args.threshold <= 255)):
        parser.error("min-area must be positive and threshold must be between 0 and 255")
    if image_path in tuple((output / name).resolve() for name in
                           ("annotated.png", "masked_grains.png", "predictions.json")):
        parser.error("Choose an output folder that will not overwrite the input photo")

    print("Loading the trained models...")
    predictor = GrainPredictor(args.selection, args.training_manifests, args.device)
    print("Finding and classifying grains...")
    try:
        result, annotated, masked = predict_image(
            image_path, predictor, args.min_area, args.threshold, args.background,
        )
    except ValueError as error:
        parser.exit(2, f"Prediction stopped: {error}\n")
    text = json.dumps(result, indent=2, allow_nan=False)
    output.mkdir(parents=True, exist_ok=True)
    annotated.save(output / "annotated.png")
    masked.save(output / "masked_grains.png")
    (output / "predictions.json").write_text(text + "\n", encoding="utf-8")
    print(f"\nDetected grains: {result['total_grains']}")
    print(f"Background mode: {result['segmentation']['background']}")
    for name, count in result["counts"].items():
        print(f"  {name}: {count} ({result['percentages_by_count'][name]:.2f}%)")
    print(f"Annotated photo: {output / 'annotated.png'}")
    print(f"Black-masked grains: {output / 'masked_grains.png'}")
    print(f"Predictions: {output / 'predictions.json'}")


if __name__ == "__main__":
    main()
