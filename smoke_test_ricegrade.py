"""Validation-only parity and input handling checks; never trains or reads test data."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import shutil

import numpy as np
import pandas as pd
from PIL import Image
import torch

from ricegrade import RiceGradePredictor, ModelLoadError
from ricegrade.features import ImageFeatures, instance_mask


def smoke_test(project, bundle):
    project = Path(project).resolve()
    sys.path.insert(0, str(project))
    # Reference imports are confined to this verification script, not the runtime package.
    from extract_features import GrainFeatureDataset, read_coco_annotations, opencv_features
    predictor = RiceGradePredictor(bundle)
    original = GrainFeatureDataset(project / "full_manifests/valid.csv", predictor.classes, limit=32)
    tensors, cv_values = [], []
    for index, row in enumerate(original.rows):
        image_file, annotation_file = original.paths[index]
        with Image.open(image_file) as pil:
            rgb = np.array(pil.convert("RGB"))
        annotation = read_coco_annotations(str(annotation_file))[str(row["annotation_id"])]
        mask = instance_mask(annotation, *rgb.shape[:2])
        tensor, cv, _ = ImageFeatures(rgb).prepare(mask)
        reference_tensor, reference_label, reference_cv = original[index]
        assert torch.equal(tensor, reference_tensor), f"CNN preprocessing changed: row {index}"
        np.testing.assert_array_equal(cv, reference_cv.numpy(), err_msg=f"CV mismatch: row {index}")
        tensors.append(tensor)
        cv_values.append(cv)
    with np.load(project / "results/version_1/features_v3/valid.npz", allow_pickle=False) as saved:
        np.testing.assert_array_equal(saved["sample_ids"][:32],
                                      [f"{r['image_id']}:{r['annotation_id']}" for r in original.rows])
        np.testing.assert_array_equal(saved["opencv_features"][:32], cv_values)
        deep = predictor.encode_tensors(tensors)
        max_error = float(np.max(np.abs(deep - saved["cnn_features"][:32])))
        # CUDA half-precision convolution algorithms can vary across environments.
        if predictor.amp:
            np.testing.assert_allclose(deep, saved["cnn_features"][:32], rtol=0.003, atol=0.005)
        scores = predictor.classify_features(deep, cv_values)
        old_scores = predictor.classify_features(saved["cnn_features"][:32], saved["opencv_features"][:32])
        assert np.array_equal(scores.argmax(1), old_scores.argmax(1)), "Validation smoke predictions changed"
    # Exercise actual thin training annotations that originally crashed extraction.
    train = pd.read_csv(project / "full_manifests/train.csv")
    for annotation_id in [3857, 6940]:
        row = train.loc[train.annotation_id == annotation_id].iloc[0]
        with Image.open(row.image_path) as pil:
            rgb_thin = np.array(pil.convert("RGB"))
        annotation = read_coco_annotations(row.annotation_path)[str(annotation_id)]
        mask_thin = instance_mask(annotation, *rgb_thin.shape[:2])
        _, values, _ = ImageFeatures(rgb_thin).prepare(mask_thin)
        reference = opencv_features(row.image_path, row.annotation_path, annotation_id, row.image_id)
        np.testing.assert_array_equal(values, reference)
    # Future supplied masks must retain thin grains, holes, and disconnected parts.
    synthetic = np.zeros((20, 25), dtype=np.uint8)
    synthetic[2:12, 3:15] = 1
    synthetic[5:8, 6:9] = 0
    synthetic[16, 20] = 1
    from pycocotools import mask as coco_mask
    rle = coco_mask.encode(np.asfortranarray(synthetic))
    np.testing.assert_array_equal(instance_mask({"segmentation": rle}, 20, 25), synthetic)
    pixels = synthetic.reshape(-1, order="F")
    counts, previous, count = [], 0, 0
    for pixel in pixels:
        if pixel == previous:
            count += 1
        else:
            counts.append(count)
            count, previous = 1, pixel
    counts.append(count)
    np.testing.assert_array_equal(instance_mask({"segmentation": {"size": [20, 25], "counts": counts}},
                                              20, 25), synthetic)
    result = predictor.predict(rgb, [mask])
    assert result["total_grains"] == sum(result["counts"].values()) == 1
    assert abs(sum(result["percentages"].values()) - 100) < 1e-6
    assert list(result["grains"][0]["confidence_scores"]) == predictor.classes
    json.dumps(result)
    invalid_cases = [(None, [mask]), (rgb.astype(float), [mask]), (rgb, None),
                     (rgb, []), (rgb, [np.zeros_like(mask)]), (rgb, [mask[:1]]),
                     (rgb, [np.full_like(mask, 2)])]
    for image, masks in invalid_cases:
        try:
            predictor.predict(image, masks)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError("Invalid input was accepted")
    try:
        RiceGradePredictor(Path(bundle) / "missing")
    except ModelLoadError:
        pass
    else:
        raise AssertionError("Missing model accepted")
    with tempfile.TemporaryDirectory() as temp:
        corrupt = Path(temp) / "bundle"
        shutil.copytree(bundle, corrupt)
        (corrupt / "class_labels.json").write_text("[]")
        try:
            RiceGradePredictor(corrupt)
        except ModelLoadError:
            pass
        else:
            raise AssertionError("Corrupted bundle accepted")
    report = {"validation_grains_checked": 32, "opencv_saved_feature_parity": "exact",
              "cnn_crop_parity": "exact", "cnn_max_abs_error_vs_saved": max_error,
              "prediction_parity": True, "thin_mask_annotations_checked": [3857, 6940],
              "invalid_input_and_model_error_checks": "passed", "device": str(predictor.device),
              "automatic_segmentation_tested": False}
    print(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    smoke_test(args.project, args.bundle or args.project / "models/final_ricegrade")


if __name__ == "__main__":
    main()
