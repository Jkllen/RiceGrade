"""One held-out COCO-mask classification evaluation of an already frozen bundle."""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             precision_recall_fscore_support, ConfusionMatrixDisplay)
from tqdm import tqdm

from ricegrade import RiceGradePredictor
from ricegrade.features import ImageFeatures, instance_mask
from ricegrade.inference import sha256_file


def resolve_path(raw, project, manifest_dir):
    path = Path(str(raw))
    for candidate in ([path] if path.is_absolute() else [manifest_dir / path, project / path]):
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Dataset file not found: {raw}")


def evaluate(project, bundle, output, device="auto", batch_size=32):
    project, bundle, output = map(lambda p: Path(p).resolve(), (project, bundle, output))
    if output.exists():
        raise FileExistsError(f"Evaluation output already exists: {output}; preserve completed test results")
    predictor = RiceGradePredictor(bundle, device=device, batch_size=batch_size)
    if predictor.manifest["automatic_segmentation_implemented"]:
        raise ValueError("This evaluator measures supplied COCO-mask classification only")
    data_dir = project / "full_manifests"
    test_file = data_dir / "test.csv"
    frame = pd.read_csv(test_file, keep_default_na=False)
    required = {"image_path", "annotation_path", "image_id", "annotation_id", "class_id", "label", "source_id"}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError("Incomplete or empty held-out manifest")
    for split in ["train", "valid"]:
        other = pd.read_csv(data_dir / f"{split}.csv", keep_default_na=False)
        test_paths = {str(resolve_path(p, project, data_dir)).casefold() for p in frame.image_path}
        other_paths = {str(resolve_path(p, project, data_dir)).casefold() for p in other.image_path}
        if test_paths.intersection(other_paths) or set(frame.source_id).intersection(other.source_id):
            raise ValueError(f"Held-out test source/image overlap with {split}")
    rows = frame.to_dict("records")
    sample_ids = np.asarray([f"{r['image_id']}:{r['annotation_id']}" for r in rows])
    if len(set(sample_ids)) != len(rows):
        raise ValueError("Duplicate test grain identifiers")
    for row in rows:
        class_id = int(row["class_id"])
        if class_id not in range(4) or predictor.classes[class_id] != row["label"]:
            raise ValueError("Test class indices differ from the trained class order")
    output.mkdir(parents=True)
    start = time.perf_counter()
    cnn_parts, cv_values, tensors = [], [], []
    annotation_cache, current_path, image = {}, None, None
    for row in tqdm(rows, desc="Held-out grain features", unit="grain"):
        image_file = resolve_path(row["image_path"], project, data_dir)
        annotation_file = resolve_path(row["annotation_path"], project, data_dir)
        if image_file != current_path:
            with Image.open(image_file) as pil:
                rgb = np.array(pil.convert("RGB"))
            bgr = cv2.imread(str(image_file), cv2.IMREAD_COLOR)
            if bgr is None or not np.array_equal(rgb, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)):
                raise ValueError(f"PIL/OpenCV RGB decoding differs: {image_file}; cannot guarantee feature parity")
            image = ImageFeatures(rgb)
            current_path = image_file
            del bgr, rgb
        if annotation_file not in annotation_cache:
            coco = json.loads(annotation_file.read_text())
            annotation_cache[annotation_file] = {int(a["id"]): a for a in coco["annotations"]}
        annotation = annotation_cache[annotation_file].get(int(row["annotation_id"]))
        if annotation is None or int(annotation["image_id"]) != int(row["image_id"]):
            raise ValueError(f"COCO annotation/image mismatch: {row}")
        mask = instance_mask(annotation, *image.rgb.shape[:2])
        tensor, cv_features, _ = image.prepare(mask)
        del mask
        tensors.append(tensor)
        cv_values.append(cv_features)
        if len(tensors) == batch_size:
            cnn_parts.append(predictor.encode_tensors(tensors))
            tensors = []
    if tensors:
        cnn_parts.append(predictor.encode_tensors(tensors))
    cnn = np.concatenate(cnn_parts)
    cv = np.asarray(cv_values, dtype=np.float32)
    y = frame.class_id.to_numpy(dtype=np.int64)
    if len(cnn) != len(y):
        raise RuntimeError("Test feature row count mismatch")
    scores = predictor.classify_features(cnn, cv)
    predicted = scores.argmax(axis=1)
    labels = list(range(4))
    precision, recall, f1, _ = precision_recall_fscore_support(y, predicted, labels=labels,
                                                           average="macro", zero_division=0)
    report = classification_report(y, predicted, labels=labels, target_names=predictor.classes,
                                   output_dict=True, zero_division=0)
    matrix = confusion_matrix(y, predicted, labels=labels)
    np.savez_compressed(output / "test_features.npz", cnn_features=cnn, opencv_features=cv,
                        y=y, sample_ids=sample_ids)
    frame.to_csv(output / "test_metadata.csv", index=False)
    predictions = frame.copy()
    predictions["predicted_class_id"] = predicted
    predictions["predicted_category"] = [predictor.classes[i] for i in predicted]
    predictions["confidence"] = scores.max(axis=1)
    for i, name in enumerate(predictor.classes):
        predictions[f"probability_{name}"] = scores[:, i]
    predictions.to_csv(output / "predictions.csv", index=False)
    (output / "classification_report.txt").write_text(
        classification_report(y, predicted, labels=labels, target_names=predictor.classes,
                              digits=4, zero_division=0), encoding="utf-8")
    report_rows = [{"category": name, **report[name]} for name in predictor.classes]
    report_rows.append({"category": "accuracy", "precision": None, "recall": None,
                        "f1-score": report["accuracy"], "support": len(y)})
    report_rows += [{"category": name, **report[name]} for name in ["macro avg", "weighted avg"]]
    pd.DataFrame(report_rows).to_csv(output / "classification_report.csv", index=False)
    pd.DataFrame(matrix, index=predictor.classes, columns=predictor.classes).to_csv(output / "confusion_matrix.csv")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 7))
    ConfusionMatrixDisplay(matrix, display_labels=predictor.classes).plot(
        ax=ax, cmap="Blues", xticks_rotation=35, colorbar=False)
    ax.set_title("RiceGrade held-out test: supplied COCO masks")
    fig.tight_layout()
    fig.savefig(output / "confusion_matrix.png", dpi=180)
    plt.close(fig)
    metrics = {
        "selected_configuration": predictor.mode, "samples": len(y),
        "source_images": int(frame.image_path.nunique()), "accuracy": float(accuracy_score(y, predicted)),
        "macro_precision": float(precision), "macro_recall": float(recall), "macro_f1": float(f1),
        "per_class": {name: report[name] for name in predictor.classes},
        "confusion_matrix": matrix.tolist(), "classes": predictor.classes,
        "device": str(predictor.device), "cnn_amp": predictor.amp, "batch_size": batch_size,
        "scope": "grain classification using supplied ground-truth COCO instance masks; segmentation not evaluated",
        "parameter_selection_uses_test": False, "retrained": False,
        "test_manifest_sha256": sha256_file(test_file),
        "bundle_manifest_sha256": sha256_file(bundle / "manifest.json"),
        "artifact_sha256": predictor.manifest["files"],
        "all_test_images_pil_opencv_rgb_equal": True,
        "elapsed_seconds": time.perf_counter() - start,
        "timing_scope": "image decode, COCO masks, features, classification, and report writing; not deployment latency",
    }
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ["samples", "accuracy", "macro_precision", "macro_recall", "macro_f1"]}, indent=2))
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--batch", type=int, default=32)
    args = parser.parse_args()
    evaluate(args.project, args.bundle or args.project / "models/final_ricegrade",
             args.output or args.project / "results/final_ricegrade_test", args.device, args.batch)


if __name__ == "__main__":
    main()
