"""Shared original-resolution grain features for training and inference."""

import cv2
import numpy as np


OPENCV_FEATURE_NAMES = (
    "area_pixels", "perimeter_pixels", "major_length_pixels", "minor_length_pixels",
    "aspect_ratio", "extent", "solidity", "circularity",
    "red_mean", "green_mean", "blue_mean", "red_std", "green_std", "blue_std",
    "gray_std", "gray_entropy",
)


def extract_opencv_features(rgb, mask):
    """Return 16 finite float32 features from an RGB uint8 crop and its mask.

    Area counts foreground pixels; extent divides that count by crop area.
    Perimeter, rotated rectangle, solidity, and circularity use all external
    contours together, so holes are excluded from their contour geometry.
    Lengths use original pixel coordinates. Zero denominators yield zero,
    including for single-pixel and thin masks. Color statistics use only true
    foreground, values 0..255, and population standard deviations. Grayscale
    entropy uses a 256-bin histogram and log base 2.
    """
    rgb = np.asarray(rgb)
    mask = np.asarray(mask)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("Expected an RGB uint8 array with shape (height, width, 3)")
    if mask.shape != rgb.shape[:2]:
        raise ValueError("Mask dimensions must match the RGB crop")
    foreground = mask.astype(bool, copy=False)
    area = int(np.count_nonzero(foreground))
    if area == 0:
        raise ValueError("Cannot extract features from an empty grain mask")

    contours, _ = cv2.findContours(
        foreground.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
    )
    points = np.concatenate(contours, axis=0)
    perimeter = sum(cv2.arcLength(contour, True) for contour in contours)
    contour_area = sum(cv2.contourArea(contour) for contour in contours)
    _, sides, _ = cv2.minAreaRect(points)
    major, minor = sorted(sides, reverse=True)
    hull_area = cv2.contourArea(cv2.convexHull(points))
    aspect_ratio = major / minor if minor > 0 else 0.0
    solidity = contour_area / hull_area if hull_area > 0 else 0.0
    circularity = 4 * np.pi * contour_area / perimeter ** 2 if perimeter > 0 else 0.0

    pixels = rgb[foreground]
    means, standard_deviations = pixels.mean(axis=0), pixels.std(axis=0)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)[foreground]
    histogram = np.bincount(gray, minlength=256)
    probabilities = histogram[histogram > 0] / area
    entropy = float(-(probabilities * np.log2(probabilities)).sum())
    features = np.asarray((
        area, perimeter, major, minor, aspect_ratio, area / foreground.size,
        solidity, circularity, *means, *standard_deviations, gray.std(), entropy,
    ), dtype=np.float32)
    if not np.isfinite(features).all():
        raise ValueError("Grain features contain a non-finite value")
    return features
