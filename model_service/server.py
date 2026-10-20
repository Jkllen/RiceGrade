"""Private RiceGrade research-preview inference endpoint.

Receives original R2 image bytes *through* the authenticated Pages Function; never
makes private R2 objects or the frozen model files publicly accessible. The
OpenCV segmentation stage is deliberately labeled experimental/unvalidated.
"""
from __future__ import annotations

import hmac
import io
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import cv2
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError

from ricegrade import RiceGradePredictor
from segment_opencv import extract_masks

MODEL_DIR = Path(os.environ.get('RICEGRADE_MODEL_DIR', str(Path(__file__).parent / 'models' / 'final_ricegrade')))
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 1_500_000
MAX_SOURCE_PIXELS = 24_000_000
MAX_GRAINS = 160
predict_lock = threading.Lock()


def authorize(supplied: str | None) -> None:
    configured = os.environ.get('RICEGRADE_ML_TOKEN', '')
    if not configured or len(configured) < 32:
        raise HTTPException(503, 'Inference authentication is not configured')
    if not supplied or not hmac.compare_digest(configured.encode(), supplied.encode()):
        raise HTTPException(401, 'Unauthorized model request')


def decode_image(raw: bytes) -> tuple[np.ndarray, str | None]:
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('Supply an image up to 5 MB')
    try:
        with Image.open(io.BytesIO(raw)) as file:
            if file.format not in ('JPEG', 'PNG', 'WEBP'):
                raise ValueError('Image must be JPEG, PNG, or WebP')
            width, height = file.size
            if width < 64 or height < 64 or width * height > MAX_SOURCE_PIXELS:
                raise ValueError('Image must be at least 64×64 and no more than 24 megapixels')
            image = ImageOps.exif_transpose(file).convert('RGB')
            note = None
            if image.width * image.height > MAX_PIXELS:
                scale = (MAX_PIXELS / (image.width * image.height)) ** 0.5
                resized = (max(64, int(image.width * scale)), max(64, int(image.height * scale)))
                image = image.resize(resized, Image.Resampling.LANCZOS)
                note = 'Image was downscaled for the experimental preview; morphology-in-pixels may differ from training images'
            return np.asarray(image, dtype=np.uint8), note
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Unreadable or unsafe image') from exc


def infer(rgb: np.ndarray, predictor: RiceGradePredictor, resize_warning: str | None = None) -> dict:
    segmentation = extract_masks(rgb)
    if resize_warning:
        segmentation.warnings.append(resize_warning)
    if not segmentation.masks:
        raise ValueError('No usable grains found. Use separated white rice on a dark uniform background')
    if len(segmentation.masks) > MAX_GRAINS:
        raise ValueError(f'Too many isolated regions ({len(segmentation.masks)}); use fewer separated grains in the image')
    values = predictor.predict(rgb, segmentation.masks)
    # Keep response size bounded; D1 stores only a count-based research preview.
    # A simplified largest external contour helps the operator inspect what OpenCV actually isolated.
    # Grain order matches the corresponding segmentation mask order.
    def outline(mask: np.ndarray) -> list[list[int]]:
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        contour = max(contours, key=cv2.contourArea)
        epsilon = max(1.0, cv2.arcLength(contour, True) * 0.012)
        approx = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        if len(approx) > 64:
            approx = approx[np.linspace(0, len(approx) - 1, 64).astype(int)]
        return [[int(x), int(y)] for x, y in approx] if len(approx) >= 3 else []

    grains = [{
        'grain_index': grain['grain_index'],
        'bbox_xywh': grain['bbox_xywh'],
        'outline_xy': outline(segmentation.masks[index]),
        'category': grain['category'],
        'score': round(grain['confidence'], 5),
    } for index, grain in enumerate(values['grains'])]
    return {
        'status': 'experimental_unvalidated_segmentation',
        'segmentation_source': 'experimental_opencv_unvalidated',
        'segmentation_warnings': segmentation.warnings,
        'model_configuration': values['selected_configuration'],
        'classes': list(predictor.classes),
        'total_grains': values['total_grains'],
        'image_width': int(rgb.shape[1]),
        'image_height': int(rgb.shape[0]),
        'counts': values['counts'],
        'count_percentages': values['percentages'],
        'grains': grains,
        'confidence_note': 'XGBoost top-class scores are uncalibrated; no acceptance threshold has been validated',
        'measurement_basis': 'grain_count_not_weight',
        'model_validation_scope': 'held_out_annotated_masks_only',
        'dss_result': None,
        'official_grade': None,
        'manual_verification_required': True,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast on corrupted/missing frozen model weights and metadata.
    app.state.predictor = RiceGradePredictor(MODEL_DIR, device='cpu', batch_size=16)
    yield


app = FastAPI(title='RiceGrade Private Model Service', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get('/health')
def health():
    return {'status': 'ok', 'model': 'loaded' if hasattr(app.state, 'predictor') else 'not_loaded'}


@app.post('/predict/image')
async def classify_private_image(request: Request, x_ricegrade_service_key: str | None = Header(default=None)):
    authorize(x_ricegrade_service_key)
    if request.headers.get('content-type', '').split(';')[0].strip().lower() not in ('image/jpeg', 'image/png', 'image/webp'):
        raise HTTPException(415, 'Unsupported image content type')
    if int(request.headers.get('content-length', '0') or '0') > MAX_BYTES:
        raise HTTPException(413, 'Image exceeds 5 MB')
    # Stream with a hard cap; never blindly buffer an unbounded request body.
    buffer = bytearray()
    async for chunk in request.stream():
        buffer.extend(chunk)
        if len(buffer) > MAX_BYTES:
            raise HTTPException(413, 'Image exceeds 5 MB')
    try:
        rgb, resize_warning = decode_image(bytes(buffer))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not predict_lock.acquire(blocking=False):
        raise HTTPException(429, 'Model is processing another request. Retry shortly')
    try:
        try:
            return await run_in_threadpool(infer, rgb, app.state.predictor, resize_warning)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    finally:
        predict_lock.release()
