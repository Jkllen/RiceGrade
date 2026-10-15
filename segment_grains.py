"""Find separate rice grains on black, white, or light-gray backgrounds.

This baseline needs a plain background, visible gaps, and adequate contrast.
Uneven lighting, shadows, and touching grains can produce incorrect masks.
Check the segmentation preview before trusting full-photo predictions.
"""

import cv2
import numpy as np


def segment_grains(rgb, min_area=None, threshold=None, background="auto"):
    """Return ``(regions, settings)`` without changing the original image.

    Regions yield ``((x, y, width, height), tight_boolean_mask)`` in image order.
    Coordinates and mask areas retain the original resolution, without resizing.

    Auto assumes the image border contains background: median border brightness
    below 80 selects black; otherwise it selects light. Override this heuristic
    when necessary. Black mode thresholds grayscale brightness. Light mode uses
    RGB distance from a local background estimate, detecting darker or brighter grains.
    Only the background estimate is resized; grain pixels and masks stay full size.
    Otsu selects a threshold unless supplied; automatic light thresholds have a
    noise floor of 10. Internal holes are filled and edge regions are excluded.
    Unless overridden, minimum area is 100 pixels for black mode and at least
    0.01% of photo area for light mode. Lower it explicitly for very small grains.
    """
    rgb = np.asarray(rgb)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("Expected an RGB uint8 array with shape (height, width, 3)")
    height, width = rgb.shape[:2]
    if height == 0 or width == 0:
        raise ValueError("Image dimensions must be positive")
    if min_area is not None and (not np.isfinite(min_area) or min_area < 1):
        raise ValueError("min_area must be at least 1 pixel")
    if threshold is not None and not 0 <= threshold <= 255:
        raise ValueError("threshold must be between 0 and 255")
    if background not in ("auto", "black", "light"):
        raise ValueError("background must be auto, black, or light")

    border = np.concatenate((rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]))
    border_rgb = np.rint(np.median(border, axis=0)).astype(np.uint8)
    resolved = background
    if background == "auto":
        brightness = float(np.dot(border_rgb, (0.299, 0.587, 0.114)))
        resolved = "black" if brightness < 80 else "light"
    automatic_min_area = min_area is None
    if min_area is None:
        min_area = max(100, round(height * width * 0.0001)) if resolved == "light" else 100
    if resolved == "black":
        score = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        method = "grayscale brightness threshold with filled external contours"
    else:
        # Estimate gradual lighting changes without keeping the small grain regions.
        scale = min(1.0, 512 / max(height, width))
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        small = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        window = max(15, int(min(size) * 0.15) | 1)
        local_background = cv2.medianBlur(small, window)
        local_background = cv2.GaussianBlur(local_background, (5, 5), 0)
        score = np.zeros((height, width), dtype=np.uint8)
        for channel in range(3):
            estimated = cv2.resize(local_background[:, :, channel], (width, height),
                                   interpolation=cv2.INTER_LINEAR)
            observed = cv2.GaussianBlur(rgb[:, :, channel], (5, 5), 0)
            difference = cv2.absdiff(observed, estimated)
            cv2.max(score, difference, dst=score)
            del estimated, observed, difference
        method = "local median background RGB distance with filled external contours"
    if threshold is None:
        used_threshold, binary = cv2.threshold(score, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        if resolved == "light" and used_threshold < 10:
            used_threshold, binary = cv2.threshold(score, 10, 255, cv2.THRESH_BINARY)
    else:
        used_threshold, binary = cv2.threshold(score, float(threshold), 255, cv2.THRESH_BINARY)
    if resolved == "light":
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((9, 9), dtype=np.uint8))
    settings = {
        "method": method, "background_requested": background, "background": resolved,
        "median_border_rgb": border_rgb.tolist(), "threshold": float(used_threshold),
        "automatic_threshold": threshold is None, "min_area_pixels": min_area,
        "automatic_min_area": automatic_min_area,
        "edge_regions": "excluded",
    }
    if resolved == "light":
        settings["background_estimate_size"] = list(size)
        settings["background_median_window"] = window
        settings["mask_cleanup"] = {"opening": 3, "closing": 9, "region_closing": 15}
    return _grain_regions(binary, min_area, repair_gaps=resolved == "light"), settings


def _grain_regions(binary, min_area, repair_gaps=False):
    """Yield filled grain masks, allocating each mask only inside its bounding box."""
    height, width = binary.shape
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    del binary

    regions = [(cv2.boundingRect(contour), contour) for contour in contours]
    regions.sort(key=lambda item: (item[0][1], item[0][0], item[0][2], item[0][3]))
    for bounds, contour in regions:
        x, y, grain_width, grain_height = bounds
        if grain_width < 2 or grain_height < 2:
            continue
        if x == 0 or y == 0 or x + grain_width == width or y + grain_height == height:
            continue
        if grain_width * grain_height < min_area:
            continue

        # Draw only this contour, so overlapping bounding boxes stay separate.
        mask = np.zeros((grain_height, grain_width), dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 1, thickness=cv2.FILLED, offset=(-x, -y))
        if np.count_nonzero(mask) < min_area:
            continue
        if repair_gaps:
            # Repair each accepted grain separately, keeping nearby specks separate.
            padded = np.pad(mask, 15)
            padded = cv2.morphologyEx(padded, cv2.MORPH_CLOSE, np.ones((15, 15), dtype=np.uint8))
            outlines, _ = cv2.findContours(padded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(padded, outlines, -1, 1, thickness=cv2.FILLED)
            mask = padded[15:-15, 15:-15]
        yield bounds, mask.astype(bool)
