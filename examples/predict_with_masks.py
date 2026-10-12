"""Usage: python examples/predict_with_masks.py image.jpg masks.npz --bundle models/final_ricegrade"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PIL import Image
from ricegrade import RiceGradePredictor


def main():
    parser = argparse.ArgumentParser(description="Predict supplied masks; no automatic segmentation")
    parser.add_argument("image", type=Path)
    parser.add_argument("masks", type=Path, help="NPZ containing binary 'masks' of shape (N,H,W)")
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parents[1] / "models/final_ricegrade")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args()
    with Image.open(args.image) as source:
        rgb = np.array(source.convert("RGB"))
    with np.load(args.masks, allow_pickle=False) as data:
        masks = data["masks"]
    if masks.ndim != 3:
        parser.error("masks must have shape (N,H,W)")
    predictor = RiceGradePredictor(args.bundle, device=args.device)
    print(json.dumps(predictor.predict(rgb, masks), indent=2))


if __name__ == "__main__":
    main()
