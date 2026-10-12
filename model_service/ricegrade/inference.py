"""Application-facing RiceGrade classifier. Requires supplied grain masks."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torchvision import models
from xgboost import XGBClassifier

from .features import ImageFeatures, OPENCV_FEATURE_NAMES, PREPROCESSING

CLASSES = ["broken_grain", "chalky_grain", "discolored_grain", "whole_grain"]


class ModelLoadError(RuntimeError):
    """The bundle is missing, incompatible, or corrupted."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def feature_names(mode):
    cnn = [f"cnn_{i:04d}" for i in range(1280)]
    if mode == "hybrid":
        return cnn + OPENCV_FEATURE_NAMES
    if mode == "cnn_only":
        return cnn
    if mode == "opencv_only":
        return list(OPENCV_FEATURE_NAMES)
    raise ValueError(f"Unsupported selected configuration: {mode}")


class RiceGradePredictor:
    """Load once at application startup, then call predict(rgb, masks).

    Confidence scores are XGBoost class probabilities, not calibrated certainty.
    This class never starts training or performs automatic segmentation.
    """

    def __init__(self, bundle_dir, *, device="auto", batch_size=32):
        if device not in ("auto", "cpu", "cuda") or batch_size < 1:
            raise ValueError("device must be auto/cpu/cuda and batch_size must be positive")
        self.device = torch.device("cuda" if device == "auto" and torch.cuda.is_available()
                                   else "cpu" if device == "auto" else device)
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise ModelLoadError("CUDA requested but unavailable; select device='cpu'")
        self.batch_size = batch_size
        self.bundle_dir = Path(bundle_dir).resolve()
        try:
            self.manifest = json.loads((self.bundle_dir / "manifest.json").read_text())
            if self.manifest["bundle_version"] != 1:
                raise ValueError("Unsupported bundle version")
            expected_files = {"efficientnet_b0.pth", "xgboost.json", "feature_schema.json",
                              "class_labels.json", "preprocessing.json", "model_selection.json"}
            if set(self.manifest["files"]) != expected_files:
                raise ValueError("Incomplete artifact manifest")
            for name, digest in self.manifest["files"].items():
                if sha256_file(self.bundle_dir / name) != digest:
                    raise ValueError(f"Artifact checksum mismatch: {name}")
            schema = json.loads((self.bundle_dir / "feature_schema.json").read_text())
            labels = json.loads((self.bundle_dir / "class_labels.json").read_text())
            prep = json.loads((self.bundle_dir / "preprocessing.json").read_text())
            selection = json.loads((self.bundle_dir / "model_selection.json").read_text())
            if labels != CLASSES or schema["classes"] != CLASSES:
                raise ValueError("Class indices differ from the trained class order")
            if prep != PREPROCESSING:
                raise ValueError("Preprocessing differs from the supported feature contract")
            if (schema["cnn_architecture"] != "efficientnet_b0" or
                    schema["cnn_feature_count"] != 1280 or schema["opencv_feature_count"] != 16 or
                    schema["opencv_feature_version"] != 3 or schema["mask_decoder"] != "pycocotools" or
                    schema["opencv_feature_names"] != OPENCV_FEATURE_NAMES or
                    schema["cnn_amp"] != prep["cnn_amp"] or
                    schema["checkpoint_sha256"] != self.manifest["files"]["efficientnet_b0.pth"]):
                raise ValueError("Unsupported or inconsistent feature schema")
            self.mode = self.manifest["selected_configuration"]
            self.names = feature_names(self.mode)
            if selection["selected_configuration"] != self.mode:
                raise ValueError("Selection and manifest disagree")
            checkpoint = torch.load(self.bundle_dir / "efficientnet_b0.pth",
                                    map_location="cpu", weights_only=True)
            if checkpoint["classes"] != CLASSES:
                raise ValueError("Checkpoint class order differs from the bundle")
            self.cnn = models.efficientnet_b0(weights=None)
            self.cnn.classifier[1] = nn.Linear(self.cnn.classifier[1].in_features, 4)
            self.cnn.load_state_dict(checkpoint["model_state_dict"], strict=True)
            self.cnn.classifier = nn.Identity()
            self.cnn.requires_grad_(False).eval().to(self.device)
            self.amp = self.device.type == "cuda" and prep["cnn_amp"]
            if self.device.type == "cuda":
                self.cnn.to(memory_format=torch.channels_last)
                torch.backends.cudnn.benchmark = True
            self.xgb = XGBClassifier()
            self.xgb.load_model(self.bundle_dir / "xgboost.json")
            self.xgb.set_params(device="cpu", n_jobs=2)
            if (self.xgb.n_features_in_ != len(self.names) or
                    self.xgb.get_booster().feature_names != self.names or
                    self.xgb.classes_.tolist() != list(range(4)) or
                    self.xgb.best_iteration != self.manifest["best_iteration_zero_based"]):
                raise ValueError("XGBoost feature/class order or best iteration mismatch")
            self.classes = list(CLASSES)
        except Exception as exc:
            raise ModelLoadError(f"Cannot load RiceGrade bundle {self.bundle_dir}: {exc}") from exc

    @torch.inference_mode()
    def encode_tensors(self, tensors):
        """Encode normalized 224px crops; shared by evaluation and RGB/masks API."""
        if len(tensors) == 0:
            raise ValueError("No grain tensors supplied")
        if not isinstance(tensors, torch.Tensor):
            tensors = torch.stack(tensors)
        if tensors.ndim != 4 or tuple(tensors.shape[1:]) != (3, 224, 224):
            raise ValueError("Expected normalized tensors with shape (N,3,224,224)")
        result = []
        for batch in tensors.split(self.batch_size):
            batch = batch.to(self.device)
            if self.device.type == "cuda":
                batch = batch.contiguous(memory_format=torch.channels_last)
            with torch.amp.autocast(device_type=self.device.type, enabled=self.amp):
                values = self.cnn(batch)
            result.append(values.float().cpu().numpy())
        output = np.concatenate(result)
        if output.shape[1] != 1280 or not np.isfinite(output).all():
            raise RuntimeError("CNN returned invalid features")
        return output

    def classify_features(self, cnn_features, opencv_features):
        cnn = np.asarray(cnn_features, dtype=np.float32)
        cv = np.asarray(opencv_features, dtype=np.float32)
        if (cnn.ndim != 2 or cv.ndim != 2 or cnn.shape[1] != 1280 or
                cv.shape[1] != 16 or len(cnn) != len(cv) or len(cnn) < 1 or
                not np.isfinite(cnn).all() or not np.isfinite(cv).all()):
            raise ValueError("Expected finite, aligned (N,1280) CNN and (N,16) OpenCV arrays")
        values = (np.concatenate([cnn, cv], axis=1) if self.mode == "hybrid"
                  else cnn if self.mode == "cnn_only" else cv)
        # The sklearn API automatically applies the saved early-stopping iteration.
        scores = self.xgb.predict_proba(pd.DataFrame(values, columns=self.names))
        if (scores.shape != (len(values), 4) or not np.isfinite(scores).all() or
                np.any(scores < 0) or not np.allclose(scores.sum(axis=1), 1, atol=1e-5)):
            raise RuntimeError("XGBoost returned invalid class probabilities")
        return scores

    def extract_features(self, rgb_image, masks):
        image = ImageFeatures(rgb_image)
        if masks is None:
            raise ValueError("Grain masks are required; automatic segmentation is separate")
        if isinstance(masks, np.ndarray) and masks.ndim == 2:
            masks = [masks]
        tensors, cv_values, boxes, cnn_batches = [], [], [], []
        for mask in masks:
            tensor, values, box = image.prepare(mask)
            tensors.append(tensor)
            cv_values.append(values)
            boxes.append(box)
            if len(tensors) == self.batch_size:
                cnn_batches.append(self.encode_tensors(tensors))
                tensors = []
        if tensors:
            cnn_batches.append(self.encode_tensors(tensors))
        if not cv_values:
            raise ValueError("No grain masks supplied")
        return np.concatenate(cnn_batches), np.asarray(cv_values, dtype=np.float32), boxes

    def predict(self, rgb_image, masks):
        cnn, cv, boxes = self.extract_features(rgb_image, masks)
        scores = self.classify_features(cnn, cv)
        labels = scores.argmax(axis=1)
        counts = {name: int(np.count_nonzero(labels == i)) for i, name in enumerate(self.classes)}
        grains = [{"grain_index": i, "bbox_xywh": boxes[i], "class_id": int(label),
                   "category": self.classes[label], "confidence": float(scores[i, label]),
                   "confidence_scores": {name: float(scores[i, j])
                                         for j, name in enumerate(self.classes)}}
                  for i, label in enumerate(labels)]
        return {"selected_configuration": self.mode, "total_grains": len(grains),
                "grains": grains, "counts": counts,
                "percentages": {name: count * 100.0 / len(grains) for name, count in counts.items()}}
