"""Freeze model selection using existing validation results; never retrain."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone

import pandas as pd
import cv2
from xgboost import XGBClassifier
from ricegrade.features import PREPROCESSING, OPENCV_FEATURE_NAMES
from ricegrade.inference import CLASSES, feature_names, sha256_file


def finalize(project, output):
    project, output = Path(project).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to replace an existing bundle: {output}")
    comparison = project / "results/version_1/xgboost_v3_compare/comparison.csv"
    schema_file = project / "results/version_1/features_v3/feature_schema.json"
    checkpoint = project / "models/version_1/best_efficientnet_b0.pth"
    schema = json.loads(schema_file.read_text())
    if (schema["classes"] != CLASSES or schema["opencv_feature_names"] != OPENCV_FEATURE_NAMES
            or schema["opencv_feature_version"] != 3 or not schema["cnn_amp"]
            or schema["checkpoint_sha256"] != sha256_file(checkpoint)):
        raise ValueError("Feature schema does not match the saved checkpoint/contract")
    frame = pd.read_csv(comparison)
    if set(frame["mode"]) != {"hybrid", "cnn_only", "opencv_only"} or len(frame) != 3:
        raise ValueError("Expected exactly the three existing comparison configurations")
    metrics = ["accuracy", "macro_precision", "macro_recall", "macro_f1"]
    if frame[metrics].isna().any().any() or not ((frame[metrics] >= 0) & (frame[metrics] <= 1)).all().all():
        raise ValueError("Invalid validation metrics")
    provenance = {str(p.relative_to(project)): sha256_file(p)
                  for p in [comparison, schema_file, checkpoint]}
    for row in frame.to_dict("records"):
        mode = row["mode"]
        metric_file = comparison.parent / f"{mode}_validation_metrics.json"
        model_file = project / f"models/version_1/xgboost_v3_compare/{mode}_xgboost.json"
        saved = json.loads(metric_file.read_text())
        if any(abs(saved[key] - row[key]) > 1e-12 for key in metrics):
            raise ValueError(f"Comparison disagrees with {mode} validation metrics")
        if saved["classes"] != CLASSES or saved["cnn_checkpoint_sha256"] != schema["checkpoint_sha256"]:
            raise ValueError(f"Incompatible {mode} model provenance")
        model = XGBClassifier()
        model.load_model(model_file)
        if (model.get_booster().feature_names != feature_names(mode) or
                model.classes_.tolist() != list(range(4)) or
                model.n_features_in_ != row["feature_count"] or
                model.best_iteration + 1 != row["best_iteration"]):
            raise ValueError(f"Incompatible saved {mode} feature/class order or iteration")
        provenance[str(model_file.relative_to(project))] = sha256_file(model_file)
        provenance[str(metric_file.relative_to(project))] = sha256_file(metric_file)
    ranked = frame.sort_values(["macro_f1", "accuracy", "mode"], ascending=[False, False, True])
    winner = ranked.iloc[0].to_dict()
    mode = winner["mode"]
    selected_file = project / f"models/version_1/xgboost_v3_compare/{mode}_xgboost.json"
    selection = {
        "selected_configuration": mode,
        "selection_rule": "highest validation macro F1; accuracy then mode name break exact ties",
        "selected_validation_performance": winner,
        "validation_comparison": ranked.to_dict("records"),
        "hybrid_is_best": mode == "hybrid",
        "macro_f1_margin_over_runner_up": float(ranked.iloc[0]["macro_f1"] - ranked.iloc[1]["macro_f1"]),
        "selection_uses_test_results": False, "retrained": False,
        "source_artifacts_sha256": provenance,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Small validation differences do not establish statistical superiority.",
    }
    output.mkdir(parents=True)
    shutil.copy2(checkpoint, output / "efficientnet_b0.pth")
    shutil.copy2(selected_file, output / "xgboost.json")
    # Exact original schema retained as provenance; runtime paths are bundle-relative.
    shutil.copy2(schema_file, output / "feature_schema.json")
    for name, value in [("class_labels.json", CLASSES), ("preprocessing.json", PREPROCESSING),
                        ("model_selection.json", selection)]:
        (output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    manifest = {
        "bundle_version": 1, "selected_configuration": mode,
        "best_iteration_zero_based": int(winner["best_iteration"]) - 1,
        "files": {p.name: sha256_file(p) for p in sorted(output.iterdir())},
        "requires_instance_masks": True, "automatic_segmentation_implemented": False,
        "runtime_versions": {p: importlib.metadata.version(p) for p in
                             ["torch", "torchvision", "numpy", "pandas", "Pillow", "xgboost"]},
    }
    manifest["runtime_versions"]["cv2_runtime"] = cv2.__version__
    manifest["runtime_versions"]["opencv-python-headless"] = importlib.metadata.version("opencv-python-headless")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Selected {mode}: validation macro F1={winner['macro_f1']:.6f}; accuracy={winner['accuracy']:.6f}")
    print(f"Saved existing models and selection to {output}; no training performed")
    return selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    finalize(args.project, args.output or args.project / "models/final_ricegrade")


if __name__ == "__main__":
    main()
