"""RiceGrade Step 3: Train XGBoost on saved EfficientNet-B0 + OpenCV features.

Run from the RiceGrade_Model_Training project root:
    python train_xgboost.py
    python train_xgboost.py --compare
    python train_xgboost.py --device cuda   # optional; CPU is the default

Input: results/version_1/features_v3/{train,valid}.npz + feature_schema.json
No CNN fine-tuning, no COCO decoding, and no use of the test split.
"""

import argparse
import json
import os
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    ConfusionMatrixDisplay, accuracy_score, classification_report,
    confusion_matrix, f1_score, precision_score, recall_score,
)
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parent


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train RiceGrade hybrid XGBoost from saved CNN + OpenCV features"
    )
    parser.add_argument("--features", type=Path,
                        default=ROOT / "results" / "version_1" / "features_v3",
                        help="Folder with train.npz, valid.npz and feature_schema.json")
    parser.add_argument("--results", type=Path,
                        default=ROOT / "results" / "version_1" / "xgboost_v3")
    parser.add_argument("--models", type=Path,
                        default=ROOT / "models" / "version_1" / "xgboost_v3")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu",
                        help="XGBoost training device. CPU is a reliable default.")
    parser.add_argument("--estimators", type=int, default=600)
    parser.add_argument("--early-stopping-rounds", type=int, default=40)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--n-jobs", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--compare", action="store_true",
                        help="Also train CNN-only and OpenCV-only XGBoost baselines")
    parser.add_argument("--overwrite", action="store_true",
                        help="Explicitly replace existing XGBoost outputs")
    args = parser.parse_args()
    if args.estimators < 1 or args.early_stopping_rounds < 1 or args.n_jobs < 1:
        parser.error("estimators, early-stopping-rounds, and n-jobs must be positive")
    if not 0 < args.learning_rate <= 1 or args.max_depth < 1:
        parser.error("learning-rate must be in (0, 1], max-depth must be positive")
    return args


def load_npz(path, expected_cnn, expected_cv):
    if not path.is_file():
        raise FileNotFoundError(f"Feature file not found: {path}")
    with np.load(path, allow_pickle=False) as data:
        required = {"cnn_features", "opencv_features", "y", "sample_ids"}
        if not required.issubset(data.files):
            raise ValueError(f"{path.name} missing keys: {sorted(required - set(data.files))}")
        cnn = np.asarray(data["cnn_features"], dtype=np.float32)
        cv = np.asarray(data["opencv_features"], dtype=np.float32)
        labels = np.asarray(data["y"], dtype=np.int64)
        sample_ids = np.asarray(data["sample_ids"]).astype(str)
    if cnn.ndim != 2 or cv.ndim != 2 or cnn.shape[1] != expected_cnn or cv.shape[1] != expected_cv:
        raise ValueError(f"Unexpected feature dimensions in {path}: CNN={cnn.shape}, CV={cv.shape}")
    if len(cnn) == 0 or not (len(cnn) == len(cv) == len(labels) == len(sample_ids)):
        raise ValueError(f"Feature/label/sample ID counts don't match in {path}")
    if not np.isfinite(cnn).all() or not np.isfinite(cv).all():
        raise ValueError(f"Non-finite features in {path}")
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError(f"Repeated sample IDs inside {path}")
    return cnn, cv, labels, sample_ids


def validate_metadata(feature_dir, train_y, valid_y):
    """Check row alignment and potential image/source leakage across splits.

    COCO image_id and annotation_id can restart in each split, so we do NOT
    compare the NPZ sample_ids between train and validation.
    """
    metadata = {}
    for split, labels in (("train", train_y), ("valid", valid_y)):
        path = feature_dir / f"{split}_metadata.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Expected feature metadata file: {path}")
        frame = pd.read_csv(path, keep_default_na=False)
        if len(frame) != len(labels):
            raise ValueError(f"{split} metadata rows ({len(frame)}) != features ({len(labels)})")
        if "class_id" not in frame:
            raise ValueError(f"class_id missing in {path}")
        ids = pd.to_numeric(frame["class_id"], errors="raise").to_numpy()
        if not np.array_equal(ids, labels):
            raise ValueError(f"{split} labels don't match metadata row order")
        metadata[split] = frame

    for field in ("image_path", "source_id"):
        if field not in metadata["train"] or field not in metadata["valid"]:
            continue
        def as_set(frame):
            values = frame[field].astype(str).str.strip()
            if field == "image_path":
                values = values.map(lambda v: os.path.normcase(os.path.normpath(v)))
            else:
                values = values.str.casefold()
            return {v for v in values if v and v.lower() != "nan"}
        shared = as_set(metadata["train"]) & as_set(metadata["valid"])
        if shared:
            examples = sorted(shared)[:3]
            raise ValueError(
                f"Possible train/validation leakage: {len(shared)} shared {field} values, "
                f"for example: {examples}. Verify dataset splits before continuing."
            )
    return metadata


def save_confusion_matrix(actual, predicted, classes, path):
    matrix = confusion_matrix(actual, predicted, labels=np.arange(len(classes)))
    fig, ax = plt.subplots(figsize=(9, 7))
    disp = ConfusionMatrixDisplay(confusion_matrix=matrix, display_labels=classes)
    disp.plot(ax=ax, cmap="Blues", values_format="d", xticks_rotation=25,
              colorbar=False)
    ax.set_title("RiceGrade Hybrid XGBoost — Validation Confusion Matrix")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def save_loss_curve(model, path):
    results = model.evals_result()
    losses = results.get("validation_0", {}).get("mlogloss")
    if losses is None:
        return
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(range(1, len(losses) + 1), losses, label="Validation log loss")
    best_iteration = getattr(model, "best_iteration", None)
    if best_iteration is not None:
        ax.axvline(best_iteration + 1, linestyle="--", label=f"Best iteration: {best_iteration + 1}")
    ax.set_xlabel("Boosting round")
    ax.set_ylabel("Multiclass log loss")
    ax.set_title("XGBoost validation learning curve")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def train_one(feature_mode, cnn_train, cv_train, y_train, cnn_valid, cv_valid,
              y_valid, classes, cv_names, args):
    if feature_mode == "hybrid":
        x_train = np.concatenate((cnn_train, cv_train), axis=1)
        x_valid = np.concatenate((cnn_valid, cv_valid), axis=1)
        names = [f"cnn_{i:04d}" for i in range(cnn_train.shape[1])] + cv_names
    elif feature_mode == "cnn_only":
        x_train, x_valid = cnn_train, cnn_valid
        names = [f"cnn_{i:04d}" for i in range(cnn_train.shape[1])]
    elif feature_mode == "opencv_only":
        x_train, x_valid = cv_train, cv_valid
        names = cv_names
    else:
        raise ValueError(feature_mode)

    # Explicit column names are preserved in the saved XGBoost JSON model.
    train_frame = pd.DataFrame(x_train, columns=names)
    valid_frame = pd.DataFrame(x_valid, columns=names)

    model = XGBClassifier(
        objective="multi:softprob", num_class=len(classes),
        n_estimators=args.estimators, learning_rate=args.learning_rate,
        max_depth=args.max_depth, subsample=0.8, colsample_bytree=0.8,
        reg_lambda=1.0, tree_method="hist", device=args.device,
        n_jobs=args.n_jobs, random_state=args.seed,
        eval_metric="mlogloss", early_stopping_rounds=args.early_stopping_rounds,
    )
    started = time.perf_counter()
    model.fit(train_frame, y_train, eval_set=[(valid_frame, y_valid)], verbose=False)
    elapsed = time.perf_counter() - started
    pred = model.predict(valid_frame).astype(np.int64)
    probs = model.predict_proba(valid_frame)
    labels = np.arange(len(classes))
    metrics = {
        "mode": feature_mode,
        "samples_train": int(len(y_train)),
        "samples_valid": int(len(y_valid)),
        "feature_count": int(x_train.shape[1]),
        "accuracy": float(accuracy_score(y_valid, pred)),
        "macro_precision": float(precision_score(y_valid, pred, labels=labels, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_valid, pred, labels=labels, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_valid, pred, labels=labels, average="macro", zero_division=0)),
        "best_iteration": int(model.best_iteration) + 1,
        "train_seconds": round(elapsed, 2),
        "device": args.device,
    }
    report = classification_report(y_valid, pred, labels=labels,
                                   target_names=classes, digits=4, zero_division=0)
    return model, metrics, report, pred, probs


def main():
    args = parse_args()
    feature_dir = args.features.resolve()
    schema_path = feature_dir / "feature_schema.json"
    if not schema_path.is_file():
        raise FileNotFoundError(f"Missing feature schema: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    classes = schema["classes"]
    cv_names = schema["opencv_feature_names"]
    cnn_count = int(schema["cnn_feature_count"])
    cv_count = int(schema["opencv_feature_count"])
    if len(classes) != 4 or cnn_count != 1280 or cv_count != 16 or len(cv_names) != cv_count:
        raise ValueError("Expected 4 classes, 1280 CNN features and 16 OpenCV features")
    if len(set(classes)) != len(classes) or len(set(cv_names)) != len(cv_names):
        raise ValueError("Duplicate class names or OpenCV feature names")

    cnn_train, cv_train, y_train, _ = load_npz(feature_dir / "train.npz", cnn_count, cv_count)
    cnn_valid, cv_valid, y_valid, valid_ids = load_npz(feature_dir / "valid.npz", cnn_count, cv_count)
    if not (np.all((0 <= y_train) & (y_train < len(classes))) and
            np.all((0 <= y_valid) & (y_valid < len(classes)))):
        raise ValueError("Invalid class IDs found in train or validation labels")
    if set(y_train.tolist()) != set(range(len(classes))):
        raise ValueError("Training data does not include all four classes")
    metadata = validate_metadata(feature_dir, y_train, y_valid)

    results_dir, models_dir = args.results.resolve(), args.models.resolve()
    modes = ["hybrid", "cnn_only", "opencv_only"] if args.compare else ["hybrid"]
    outputs = [models_dir / f"{mode}_xgboost.json" for mode in modes]
    outputs += [results_dir / f"{mode}_validation_metrics.json" for mode in modes]
    if not args.overwrite:
        existing = [p for p in outputs if p.exists()]
        if existing:
            raise FileExistsError(f"Outputs already exist: {existing}. Use --overwrite to replace them.")
    results_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    print("RiceGrade hybrid XGBoost training (NO CNN retraining)")
    print("Features:", feature_dir)
    print(f"Train: {len(y_train):,} grains; validation: {len(y_valid):,} grains")
    print(f"CNN: {cnn_count}; OpenCV: {cv_count}; classes: {classes}")
    print("XGBoost device:", args.device)
    all_metrics = []
    for mode in modes:
        print(f"\n--- {mode.upper()} ---", flush=True)
        model, metrics, report, predicted, probabilities = train_one(
            mode, cnn_train, cv_train, y_train, cnn_valid, cv_valid,
            y_valid, classes, cv_names, args,
        )
        model_path = models_dir / f"{mode}_xgboost.json"
        model.save_model(str(model_path))
        (results_dir / f"{mode}_validation_metrics.json").write_text(
            json.dumps({**metrics, "classes": classes,
                        "feature_schema_path": str(schema_path),
                        "cnn_checkpoint_sha256": schema.get("checkpoint_sha256"),
                        "parameters": {"estimators": args.estimators,
                                       "early_stopping_rounds": args.early_stopping_rounds,
                                       "learning_rate": args.learning_rate,
                                       "max_depth": args.max_depth, "seed": args.seed,
                                       "subsample": 0.8, "colsample_bytree": 0.8}}, indent=2),
            encoding="utf-8",
        )
        (results_dir / f"{mode}_classification_report.txt").write_text(
            f"RiceGrade {mode} XGBoost — VALIDATION only\n\n{report}", encoding="utf-8"
        )
        if mode == "hybrid":
            save_confusion_matrix(y_valid, predicted, classes,
                                  results_dir / "hybrid_confusion_matrix.png")
            save_loss_curve(model, results_dir / "hybrid_learning_curve.png")
            results = pd.DataFrame({
                "sample_id": valid_ids,
                "actual_class_id": y_valid,
                "actual_class": [classes[i] for i in y_valid],
                "predicted_class_id": predicted,
                "predicted_class": [classes[i] for i in predicted],
                "confidence": probabilities.max(axis=1),
                "correct": predicted == y_valid,
            })
            if "source_id" in metadata["valid"].columns:
                results.insert(1, "source_id", metadata["valid"]["source_id"].to_numpy())
            results.to_csv(results_dir / "hybrid_validation_predictions.csv", index=False)
        all_metrics.append(metrics)
        print(f"Best boosting round: {metrics['best_iteration']}")
        print(f"Validation accuracy: {metrics['accuracy'] * 100:.2f}%")
        print(f"Validation macro F1: {metrics['macro_f1'] * 100:.2f}%")
        print(f"Training time: {metrics['train_seconds']:.1f}s")
        print("Saved model:", model_path)

    if args.compare:
        pd.DataFrame(all_metrics).to_csv(results_dir / "comparison.csv", index=False)
    print("\nFinished. Next: review validation metrics, then freeze the model before testing.")
    print("Reminder: source features came from annotated COCO masks, not automatic segmentation.")


if __name__ == "__main__":
    main()
