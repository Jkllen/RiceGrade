"""EXPERIMENTAL grain isolation for high-contrast single-layer white rice photographs.

No segmentation accuracy has been established. This is NOT a validated grading pipeline.
The trained classifier expects *one accurate binary mask per grain*; poor masks degrade
both the 16 handcrafted OpenCV features and the deep CNN feature crops.
"""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class SegmentationPreview:
    masks: list[np.ndarray]
    rejected_regions: int
    threshold: float
    foreground_fraction: float
    warnings: list[str]


def extract_masks(rgb: np.ndarray, *, min_area_px: int = 60, max_area_fraction: float = 0.15) -> SegmentationPreview:
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Expected an RGB uint8 image of shape (height,width,3)')
    height, width = rgb.shape[:2]
    if height < 32 or width < 32:
        raise ValueError('Photo is too small for this experimental segmentation')
    if not 1 <= min_area_px <= height * width or not 0 < max_area_fraction <= 1:
        raise ValueError('Invalid segmentation filter settings')
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    border = np.concatenate((gray[0], gray[-1], gray[:, 0], gray[:, -1]))
    # This first prototype assumes separated light rice against a DARK background.
    if float(np.median(border)) > 130:
        raise ValueError('Experimental OpenCV isolation requires a dark, uniform background')
    thresh, foreground = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN,
                                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3)))
    fraction = float(np.count_nonzero(foreground) / (height * width))
    warnings: list[str] = []
    if fraction < 0.001 or fraction > 0.75:
        warnings.append('Foreground coverage is suspicious; recapture/review this photograph')
    label_count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, connectivity=8)
    selected: list[np.ndarray] = []
    rejected = 0
    for label in range(1, label_count):
        x, y, w, h, area = map(int, stats[label])
        touches_border = x == 0 or y == 0 or (x+w) >= width or (y+h) >= height
        if area < min_area_px or area > max_area_fraction * height * width or touches_border:
            rejected += 1
            continue
        mask = (labels == label).astype(np.uint8)
        selected.append(mask)
        # Connected components may merge touching kernels; never claim this is per-grain truth.
        if w / max(h, 1) > 6.0 or h / max(w,1) > 6.0:
            warnings.append('Unusually elongated region; check for merged/cut kernels')
    if rejected:
        warnings.append(f'{rejected} regions rejected by provisional size/border rules')
    if not selected:
        warnings.append('No isolated grain regions passed provisional rules')
    warnings.append('Automatic segmentation has NOT been validated against expert masks')
    return SegmentationPreview(selected, rejected, float(thresh), fraction, warnings)


def overlay_mask_boundaries(rgb: np.ndarray, masks: list[np.ndarray]) -> np.ndarray:
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    for i, mask in enumerate(masks, 1):
        contours, _ = cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(bgr,contours,-1,(0,220,80),1)
        ys,xs=np.nonzero(mask)
        if len(xs):
            cv2.putText(bgr,str(i),(int(xs.min()),int(ys.min())),cv2.FONT_HERSHEY_SIMPLEX,0.35,(0,100,255),1)
    return bgr
