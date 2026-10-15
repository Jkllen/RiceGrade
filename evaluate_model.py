"""Evaluate the validation-selected XGBoost classifier on held-out test grains.

Run manually after preparing test crops: python evaluate_model.py
Reuses the frozen CNN/OpenCV feature extractor. No model is trained or selected.
"""

import argparse
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
import sklearn
import torch
import torchvision
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
    precision_recall_fscore_support,
)

from data_loader import (
    CLASSES, DEFAULT_MANIFEST_DIR, IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD,
    ROOT, RiceGrainDataset, resolve_record_path,
)
from extract_features import CNN_FEATURE_COUNT, extract_split, load_model, sha256_file
from grain_features import OPENCV_FEATURE_NAMES
from train_xgboost import feature_matrix, load_split, write_json


LABELS = list(range(len(CLASSES)))
DEFAULT_SELECTION = ROOT / "results/xgboost/model_selection.json"


def load_selection(selection_path, training_manifests):
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    schema_path = selection_path.parent / "feature_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    mode = selection["selected_mode"]
    feature_counts = {"hybrid": CNN_FEATURE_COUNT + len(OPENCV_FEATURE_NAMES),
                      "cnn_only": CNN_FEATURE_COUNT, "opencv_only": len(OPENCV_FEATURE_NAMES)}
    if (mode not in feature_counts or selection["classes"] != list(CLASSES)
            or selection["test_data_used"] is not False or schema["test_data_used"] is not False):
        raise ValueError("Expected a model selected using train/validation data only")
    if (schema["schema_version"] != 1 or schema["classes"] != list(CLASSES)
            or schema["cnn_feature_count"] != CNN_FEATURE_COUNT
            or schema["opencv_feature_names"] != list(OPENCV_FEATURE_NAMES)
            or schema["hybrid_feature_count"] != feature_counts["hybrid"]
            or schema["hybrid_feature_order"] != "CNN features followed by OpenCV features"
            or schema["cnn_precision"] != "float32"
            or schema["cnn_preprocessing"] != {
                "image_size": IMAGE_SIZE, "mean": list(IMAGENET_MEAN),
                "std": list(IMAGENET_STD), "augmentation": False,
            }):
        raise ValueError("Saved feature schema differs from the current feature extractor")

    model_path = resolve_record_path(selection["model"], ROOT)
    checkpoint_path = resolve_record_path(schema["checkpoint"], ROOT)
    if sha256_file(model_path) != selection["model_sha256"]:
        raise ValueError("Selected XGBoost model has changed since validation")
    if not (sha256_file(checkpoint_path) == schema["checkpoint_sha256"]
            == selection["cnn_checkpoint_sha256"]):
        raise ValueError("CNN checkpoint does not match the selected classifier's features")

    source_hashes = {Path(path).name: value for path, value in schema["source_sha256"].items()}
    for path in (ROOT / "extract_features.py", ROOT / "grain_features.py", ROOT / "data_loader.py",
                 training_manifests / "crop_info.json", training_manifests / "class_mapping.json"):
        if sha256_file(path) != source_hashes.get(path.name):
            raise ValueError(f"Feature source changed since extraction: {path}")
    for split in ("train", "valid"):
        if sha256_file(training_manifests / f"{split}.csv") != schema["splits"][split]["manifest_sha256"]:
            raise ValueError(f"{split} manifest differs from the saved training features")

    classifier = xgb.XGBClassifier()
    classifier.load_model(model_path)
    classifier.set_params(device="cpu", n_jobs=4)
    scores = selection["validation_scores"]
    if (scores["mode"] != mode or scores["feature_count"] != feature_counts[mode]
            or classifier.n_features_in_ != feature_counts[mode]
            or not np.array_equal(classifier.classes_, LABELS)
            or classifier.best_iteration != scores["best_iteration"]
            or scores["best_rounds"] != classifier.best_iteration + 1
            or selection["prediction_iteration_range"] != [0, scores["best_rounds"]]):
        raise ValueError("Saved classifier differs from the recorded validation selection")
    return selection, schema, classifier


def check_test_sources(test_manifests, training_manifests):
    dataset = RiceGrainDataset(test_manifests / "test.csv", train=False)
    training_info = json.loads((training_manifests / "crop_info.json").read_text(encoding="utf-8"))
    test_sources = dataset.crop_info["splits"]["test"]["source_image_sha256"]
    test_paths = {Path(path).resolve() for path in test_sources}
    if not test_sources:
        raise ValueError("Test crop provenance contains no source images")
    for split in ("train", "valid"):
        used_sources = training_info["splits"][split]["source_image_sha256"]
        used_paths = {Path(path).resolve() for path in used_sources}
        if test_paths & used_paths or set(test_sources.values()) & set(used_sources.values()):
            raise ValueError(f"Test source images overlap with {split}; check the dataset split")
    return len(test_sources)


def save_confusion_matrix(matrix, output):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from sklearn.metrics import ConfusionMatrixDisplay

    figure = Figure(figsize=(8, 7))
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    names = [name.replace("_", " ").title() for name in CLASSES]
    display = ConfusionMatrixDisplay(matrix, display_labels=names)
    display.plot(ax=axis, cmap="Blues", values_format="d", xticks_rotation=30)
    axis.set(title="Test confusion matrix", xlabel="Predicted class", ylabel="True class")
    figure.savefig(output / "confusion_matrix.png", dpi=300, bbox_inches="tight")


def save_reports(output, data, probabilities, mode):
    if (probabilities.shape != (len(data["y"]), len(CLASSES))
            or not np.isfinite(probabilities).all()
            or np.any(probabilities < 0) or np.any(probabilities > 1)
            or not np.allclose(probabilities.sum(axis=1), 1, atol=1e-5)):
        raise ValueError("Classifier returned invalid class probabilities")
    predictions = probabilities.argmax(axis=1)
    precision, recall, f1, _ = precision_recall_fscore_support(
        data["y"], predictions, labels=LABELS, average="macro", zero_division=0,
    )
    matrix = confusion_matrix(data["y"], predictions, labels=LABELS)
    report_options = {"labels": LABELS, "target_names": CLASSES, "zero_division": 0}
    metrics = {
        "split": "test", "mode": mode, "samples": len(predictions), "classes": list(CLASSES),
        "accuracy": float(accuracy_score(data["y"], predictions)),
        "macro_precision": float(precision), "macro_recall": float(recall), "macro_f1": float(f1),
        "classification_report": classification_report(data["y"], predictions, output_dict=True, **report_options),
        "confusion_matrix": matrix.tolist(),
        "confusion_matrix_axes": "rows = true class; columns = predicted class",
        "evaluation_scope": "Grain classification using ground-truth COCO segmentation masks",
    }
    write_json(output / "test_metrics.json", metrics)
    (output / "classification_report.txt").write_text(
        classification_report(data["y"], predictions, digits=4, **report_options), encoding="utf-8",
    )
    with (output / "confusion_matrix.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["true_class / predicted_class", *CLASSES])
        writer.writerows((name, *row) for name, row in zip(CLASSES, matrix))
    save_confusion_matrix(matrix, output)
    with (output / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "true_class", "predicted_class", "confidence",
                         *(f"probability_{name}" for name in CLASSES)])
        writer.writerows(
            (sample_id, CLASSES[int(label)], CLASSES[int(prediction)], float(probability.max()),
             *(float(value) for value in probability))
            for sample_id, label, prediction, probability in zip(
                data["sample_ids"], data["y"], predictions, probabilities)
        )
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--test-manifests", type=Path, default=ROOT / "grain_crops_test")
    parser.add_argument("--training-manifests", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--output", type=Path, default=ROOT / "results/test_evaluation")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()
    if args.batch_size < 1 or args.num_workers < 0:
        parser.error("batch-size must be positive and num-workers nonnegative")
    output, selection_path = args.output.resolve(), args.selection.resolve()
    test_manifests, training_manifests = args.test_manifests.resolve(), args.training_manifests.resolve()
    if output.exists():
        raise FileExistsError(f"Use a fresh --output folder; already exists: {output}")

    # Verify the validation decision and its dependencies before opening test data.
    selection, schema, classifier = load_selection(selection_path, training_manifests)
    device_name = args.device
    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; check your installation or choose --device cpu")
    device = torch.device(device_name)
    checkpoint_path = resolve_record_path(schema["checkpoint"], ROOT)
    model, epoch = load_model(checkpoint_path, training_manifests, device)
    if epoch != schema["checkpoint_epoch"]:
        raise ValueError("CNN checkpoint epoch differs from the saved feature schema")
    image_count = check_test_sources(test_manifests, training_manifests)
    print(f"Selected model: {selection['selected_mode']}\nCNN device: {device}\nTest source images: {image_count}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".evaluation-", dir=output.parent) as temporary:
        staging = Path(temporary) / "reports"
        staging.mkdir()
        write_json(staging / "model_selection.json", selection)
        write_json(staging / "feature_schema.json", schema)
        split_info = extract_split("test", test_manifests, staging, model, device,
                                   args.batch_size, args.num_workers)
        data = load_split(staging, "test", {**schema, "splits": {"test": split_info}})
        probabilities = classifier.predict_proba(
            feature_matrix(data, selection["selected_mode"]),
            iteration_range=tuple(selection["prediction_iteration_range"]),
        )
        metrics = save_reports(staging, data, probabilities, selection["selected_mode"])
        write_json(staging / "run_config.json", {
            "selection": str(selection_path), "model": selection["model"],
            "model_sha256": selection["model_sha256"], "checkpoint": str(checkpoint_path),
            "checkpoint_sha256": schema["checkpoint_sha256"],
            "prediction_iteration_range": selection["prediction_iteration_range"],
            "test_manifests": str(test_manifests), "test_source_images": image_count,
            "test_split": split_info, "cnn_device": str(device), "cnn_precision": "float32",
            "batch_size": args.batch_size, "num_workers": args.num_workers,
            "xgboost_device": "cpu", "xgboost_threads": 4,
            "versions": {"torch": str(torch.__version__), "torchvision": str(torchvision.__version__),
                         "opencv": cv2.__version__, "xgboost": xgb.__version__,
                         "sklearn": sklearn.__version__, "numpy": np.__version__},
            "source_sha256": {str(path): sha256_file(path) for path in (
                Path(__file__).resolve(), ROOT / "train_xgboost.py", selection_path,
                selection_path.parent / "feature_schema.json", test_manifests / "test.csv",
                test_manifests / "crop_info.json", test_manifests / "class_mapping.json",
            )},
            "test_data_used": True, "model_retrained": False,
        })
        if output.exists():
            raise FileExistsError(f"Refusing to replace existing evaluation: {output}")
        staging.rename(output)
    print(f"\nTest accuracy: {metrics['accuracy']:.2%}; macro F1: {metrics['macro_f1']:.4f}")
    print(f"Reports: {output}")
    print(f"Confusion matrix image: {output / 'confusion_matrix.png'}")


if __name__ == "__main__":
    main()
