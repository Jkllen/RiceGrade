"""Train and compare hybrid, CNN-only, and OpenCV-only XGBoost classifiers.

Run manually: python train_xgboost.py
Requires numpy, xgboost, and scikit-learn. Only train/validation features are
loaded. Early stopping monitors validation log loss; configuration selection
uses validation macro F1. Parameters below are an untuned starting baseline.
"""

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import sklearn
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
    precision_recall_fscore_support,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_FEATURES = ROOT / "results/efficientnet_20261015_114701_799602/features"
CLASSES = ("broken_grain", "chalky_grain", "discolored_grain", "whole_grain")
LABELS = list(range(len(CLASSES)))
PARAMETERS = {
    "objective": "multi:softprob", "num_class": len(CLASSES),
    "tree_method": "hist", "eval_metric": "mlogloss",
    "n_estimators": 600, "learning_rate": 0.05, "max_depth": 5,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "early_stopping_rounds": 40, "random_state": 42,
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_split(directory, split, schema):
    with np.load(directory / f"{split}.npz", allow_pickle=False) as archive:
        data = {key: archive[key] for key in ("cnn_features", "opencv_features", "y", "sample_ids")}
    count = schema["splits"][split]["samples"]
    shapes = {"cnn_features": (count, schema["cnn_feature_count"]),
              "opencv_features": (count, len(schema["opencv_feature_names"])),
              "y": (count,), "sample_ids": (count,)}
    if count < 1 or any(data[key].shape != shape for key, shape in shapes.items()):
        raise ValueError(f"Unexpected feature shapes in {split}")
    for key in ("cnn_features", "opencv_features"):
        if data[key].dtype != np.float32 or not np.isfinite(data[key]).all():
            raise ValueError(f"Expected finite float32 values in {split}/{key}")
    if data["y"].dtype.kind not in "iu" or not np.isin(data["y"], LABELS).all():
        raise ValueError(f"Invalid class IDs in {split}")
    if split == "train" and np.unique(data["y"]).tolist() != LABELS:
        raise ValueError("Training features must include all four classes")
    if data["sample_ids"].dtype.kind != "U" or len(set(data["sample_ids"])) != count:
        raise ValueError(f"Expected unique string sample IDs in {split}")

    with (directory / f"{split}_metadata.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if (len(rows) != count
            or not np.array_equal(data["sample_ids"], [row["sample_id"] for row in rows])
            or not np.array_equal(data["y"], [int(row["class_id"]) for row in rows])):
        raise ValueError(f"Feature rows and metadata are misaligned in {split}")
    if any(row["class_name"] != CLASSES[int(row["class_id"])] for row in rows):
        raise ValueError(f"Metadata class names disagree with class IDs in {split}")
    return data


def feature_matrix(data, mode):
    if mode == "hybrid":
        return np.concatenate((data["cnn_features"], data["opencv_features"]), axis=1)
    return data["cnn_features"] if mode == "cnn_only" else data["opencv_features"]


def train_model(mode, train, valid, model_dir, result_dir, parameters):
    x_train, x_valid = feature_matrix(train, mode), feature_matrix(valid, mode)
    print(f"\nTraining {mode}: {x_train.shape[1]} features", flush=True)
    model = xgb.XGBClassifier(**parameters)
    model.fit(x_train, train["y"], eval_set=[(x_valid, valid["y"])], verbose=25)
    probabilities = model.predict_proba(x_valid)  # Automatically uses best_iteration.
    predictions = probabilities.argmax(axis=1)
    precision, recall, f1, _ = precision_recall_fscore_support(
        valid["y"], predictions, labels=LABELS, average="macro", zero_division=0,
    )
    scores = {
        "mode": mode, "feature_count": x_train.shape[1],
        "accuracy": float(accuracy_score(valid["y"], predictions)),
        "macro_precision": float(precision), "macro_recall": float(recall), "macro_f1": float(f1),
        "best_iteration": int(model.best_iteration), "best_rounds": int(model.best_iteration) + 1,
    }
    model_path = model_dir / f"{mode}_xgboost.json"
    model.save_model(model_path)
    write_json(result_dir / f"{mode}_validation_metrics.json", {
        **scores, "classes": list(CLASSES), "model_sha256": sha256_file(model_path),
        "classification_report": classification_report(
            valid["y"], predictions, labels=LABELS, target_names=CLASSES,
            output_dict=True, zero_division=0,
        ),
        "confusion_matrix": confusion_matrix(valid["y"], predictions, labels=LABELS).tolist(),
    })
    with (result_dir / f"{mode}_predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "true_class", "predicted_class", "confidence"])
        writer.writerows((sample_id, CLASSES[int(label)], CLASSES[int(prediction)], float(confidence))
                         for sample_id, label, prediction, confidence in zip(
                             valid["sample_ids"], valid["y"], predictions, probabilities.max(axis=1)))
    with (result_dir / f"{mode}_history.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["round", "validation_log_loss"])
        writer.writerows(enumerate(model.evals_result()["validation_0"]["mlogloss"], start=1))
    print(f"{mode}: accuracy {scores['accuracy']:.2%}, macro F1 {scores['macro_f1']:.4f}", flush=True)
    return scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--models", type=Path, default=None, help="Model output directory (default: models/xgboost)")
    parser.add_argument("--results", type=Path, default=None, help="Report output directory (default: results/xgboost)")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--n-jobs", type=int, default=4, help="CPU threads; not data-loader workers")
    args = parser.parse_args()
    if args.n_jobs < 1:
        parser.error("n-jobs must be positive")
    features = args.features.resolve()
    model_dir = (args.models or ROOT / "models" / "xgboost").resolve()
    result_dir = (args.results or ROOT / "results" / "xgboost").resolve()
    if model_dir == result_dir or model_dir in result_dir.parents or result_dir in model_dir.parents:
        raise ValueError("Model and result directories must be separate")
    for directory in (model_dir, result_dir):
        if directory.exists():
            raise FileExistsError(f"Use fresh --models and --results folders; already exists: {directory}")
    schema_path = features / "feature_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if (schema["schema_version"] != 1 or schema["classes"] != list(CLASSES)
            or schema["cnn_feature_count"] != 1280 or len(schema["opencv_feature_names"]) != 16
            or schema["hybrid_feature_count"] != 1296
            or schema["hybrid_feature_order"] != "CNN features followed by OpenCV features"
            or schema["test_data_used"]):
        raise ValueError("Feature schema does not match the expected train/validation pipeline")
    train, valid = load_split(features, "train", schema), load_split(features, "valid", schema)
    if set(train["sample_ids"]) & set(valid["sample_ids"]):
        raise ValueError("Training and validation sample IDs overlap")
    parameters = {**PARAMETERS, "device": args.device, "n_jobs": args.n_jobs}
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    result_dir.parent.mkdir(parents=True, exist_ok=True)
    with (TemporaryDirectory(prefix=".xgboost-", dir=model_dir.parent) as model_temp,
          TemporaryDirectory(prefix=".xgboost-", dir=result_dir.parent) as result_temp):
        staging_models, staging_results = Path(model_temp) / "models", Path(result_temp) / "results"
        staging_models.mkdir()
        staging_results.mkdir()
        scores = [train_model(mode, train, valid, staging_models, staging_results, parameters)
                  for mode in ("hybrid", "cnn_only", "opencv_only")]
        scores.sort(key=lambda row: (-row["macro_f1"], -row["accuracy"], row["mode"]))
        with (staging_results / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(scores[0]))
            writer.writeheader()
            writer.writerows(scores)
        winner = scores[0]
        write_json(staging_results / "model_selection.json", {
            "selected_mode": winner["mode"], "validation_scores": winner,
            "selection_rule": "highest validation macro F1; accuracy then mode name break ties",
            "model": str(model_dir / f"{winner['mode']}_xgboost.json"),
            "model_sha256": sha256_file(staging_models / f"{winner['mode']}_xgboost.json"),
            "classes": list(CLASSES), "cnn_checkpoint_sha256": schema["checkpoint_sha256"],
            "prediction_iteration_range": [0, winner["best_rounds"]],
            "test_data_used": False,
        })
        shutil.copyfile(schema_path, staging_results / "feature_schema.json")
        write_json(staging_results / "run_config.json", {
            "parameters": parameters, "features": str(features), "classes": list(CLASSES),
            "versions": {"xgboost": xgb.__version__, "sklearn": sklearn.__version__, "numpy": np.__version__},
            "source_sha256": {str(path): sha256_file(path) for path in (
                Path(__file__).resolve(), schema_path, features / "train.npz", features / "valid.npz",
                features / "train_metadata.csv", features / "valid_metadata.csv",
            )},
            "prediction_loader": "XGBClassifier.load_model uses best_iteration automatically",
            "test_data_used": False,
        })
        if model_dir.exists() or result_dir.exists():
            raise FileExistsError("Output appeared during training; refusing to replace it")
        staging_models.rename(model_dir)
        try:
            staging_results.rename(result_dir)
        except BaseException:
            model_dir.rename(staging_models)  # Roll back if reports cannot be published.
            raise
    print(f"\nSelected {winner['mode']}: validation macro F1 {winner['macro_f1']:.4f}")
    print(f"Models: {model_dir}\nReports: {result_dir}")


if __name__ == "__main__":
    main()
