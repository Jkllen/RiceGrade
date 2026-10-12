"""Frozen version-3 feature contract; no training dependencies."""
import cv2
import numpy as np
from PIL import Image, ImageOps
from torchvision import transforms

OPENCV_FEATURE_NAMES = [
    "area_px", "perimeter_px", "major_axis_px", "minor_axis_px",
    "aspect_ratio", "eccentricity", "solidity", "extent", "circularity",
    "mean_r", "mean_g", "mean_b", "gray_std", "mean_saturation",
    "mean_value", "gray_entropy",
]
PREPROCESSING = {
    "input_color": "RGB", "input_dtype": "uint8", "input_size": [224, 224],
    "mask_background": [0, 0, 0], "resize": "PIL.ImageOps.pad",
    "interpolation": "BICUBIC", "centering": [0.5, 0.5],
    "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225],
    "augmentation": False, "opencv_feature_version": 3,
    "geometry": "original image pixels, all components and hole boundaries",
    "cnn_feature_count": 1280, "opencv_feature_count": 16,
    "cnn_amp": True, "cuda_autocast_dtype": "float16",
    "cpu_precision": "float32; may differ slightly from training CUDA AMP features",
    "combined_order": "cnn_0000..cnn_1279, then the 16 opencv_feature_names",
}
_TRANSFORM = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(PREPROCESSING["mean"], PREPROCESSING["std"]),
])


def validate_image(image):
    if isinstance(image, Image.Image):
        if image.mode != "RGB":
            raise ValueError("PIL image must be RGB; convert explicitly before prediction")
        image = np.array(image)
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
        raise ValueError("Image must be an RGB uint8 array or RGB PIL image")
    if image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 1:
        raise ValueError("Image must have nonempty shape (height, width, 3)")
    return np.ascontiguousarray(image)


def validate_mask(mask, shape):
    mask = np.asarray(mask)
    if mask.ndim != 2 or mask.shape != tuple(shape):
        raise ValueError("Each mask must have the same height and width as the image")
    if mask.dtype.kind not in "bui" or not np.isin(mask, [0, 1, 255]).all():
        raise ValueError("Masks must be binary boolean/integer arrays (0/1 or 0/255)")
    mask = np.ascontiguousarray(mask != 0, dtype=np.uint8)
    if not np.any(mask):
        raise ValueError("Empty grain mask: supply one nonempty instance mask per grain")
    return mask


def instance_mask(annotation, image_height, image_width):
    # Optional COCO adapter used for evaluation, not needed by the RGB/masks API.
    from pycocotools import mask as coco_mask
    """Decode polygons/RLE with the same COCO rasterizer as the CNN loader."""
    segmentation = annotation.get("segmentation")
    if not segmentation:
        raise ValueError(f"Annotation {annotation.get('id')} has no segmentation")

    if isinstance(segmentation, list):
        polygons = ([segmentation] if isinstance(segmentation[0], (int, float))
                    else segmentation)
        for polygon in polygons:
            if len(polygon) < 6 or len(polygon) % 2 or not np.isfinite(polygon).all():
                raise ValueError(f"Invalid polygon for annotation {annotation.get('id')}")
        # Preserve fractional vertices; rounding/fillPoly changes COCO boundaries.
        rles = coco_mask.frPyObjects(polygons, image_height, image_width)
        rle = coco_mask.merge(rles)
    elif isinstance(segmentation, dict):
        rle = (coco_mask.frPyObjects(segmentation, image_height, image_width)
               if isinstance(segmentation.get("counts"), list) else segmentation)
    else:
        raise ValueError(f"Unsupported mask format for annotation {annotation.get('id')}")

    mask = coco_mask.decode(rle)
    if mask.ndim == 3:
        mask = np.any(mask, axis=2)
    mask = np.asarray(mask, dtype=np.uint8)
    if mask.shape != (image_height, image_width):
        raise ValueError(f"Incorrectly sized mask: annotation {annotation.get('id')}")
    return mask

def mask_geometry(mask, annotation_id=None):
    """Return nine shape features, including valid thin/single-pixel masks.

    Ordinary masks retain contour-based measurements. Zero-area contours use
    pixel-cell area, exposed pixel-edge perimeter, and pixel-corner geometry.
    """
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if not contours or hierarchy is None:
        raise ValueError(f"No contour: annotation {annotation_id}")
    # Shape, moments and color all describe the complete annotated instance.
    # Include disconnected components and subtract hole areas from geometry.
    outer = [contour for contour, entry in zip(contours, hierarchy[0]) if entry[3] < 0]
    boundary_points = np.concatenate(outer, axis=0)
    _, _, bounding_width, bounding_height = cv2.boundingRect(boundary_points)
    area = float(sum(cv2.contourArea(contour) * (1 if entry[3] < 0 else -1)
                     for contour, entry in zip(contours, hierarchy[0])))
    if area <= 0:
        # A nonempty one-pixel-wide line or isolated pixel has zero contour
        # area. Measure its occupied pixel cells instead of rejecting the row.
        area = float(cv2.countNonZero(mask))
        x, y, width, height = cv2.boundingRect(boundary_points)
        padded = np.pad(mask[y:y + height, x:x + width], 1)
        perimeter = float(np.count_nonzero(padded[1:, :] != padded[:-1, :])
                          + np.count_nonzero(padded[:, 1:] != padded[:, :-1]))
        corners = np.asarray([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.int32)
        boundary_points = (boundary_points + corners).reshape(-1, 1, 2)
    else:
        perimeter = float(sum(cv2.arcLength(contour, True) for contour in contours))
    (_, _), (side_a, side_b), _ = cv2.minAreaRect(boundary_points)
    major, minor = sorted((float(side_a), float(side_b)), reverse=True)
    aspect_ratio = major / minor if minor > 0 else 0.0

    moments = cv2.moments(mask, binaryImage=True)
    if moments["m00"] > 0:
        covariance = np.array([
            [moments["mu20"], moments["mu11"]],
            [moments["mu11"], moments["mu02"]],
        ], dtype=np.float64) / moments["m00"]
        eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0.0)
        eccentricity = float(np.sqrt(max(0.0, 1.0 - eigenvalues[0] / eigenvalues[1]))) \
            if eigenvalues[1] > 0 else 0.0
    else:
        eccentricity = 0.0

    hull_area = float(cv2.contourArea(cv2.convexHull(boundary_points)))
    solidity = area / hull_area if hull_area > 0 else 0.0
    bounding_area = bounding_width * bounding_height
    extent = area / bounding_area if bounding_area > 0 else 0.0
    circularity = (4.0 * np.pi * area / (perimeter * perimeter)) if perimeter > 0 else 0.0

    return (area, perimeter, major, minor, aspect_ratio, eccentricity,
            solidity, extent, circularity)

class ImageFeatures:
    """Reuse decoded image/color channels while measuring individual masks."""

    def __init__(self, image):
        self.rgb = validate_image(image)
        bgr = cv2.cvtColor(self.rgb, cv2.COLOR_RGB2BGR)
        self.hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        self.gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    def prepare(self, mask):
        mask = validate_mask(mask, self.rgb.shape[:2])
        x, y, width, height = cv2.boundingRect(mask)
        crop = self.rgb[y:y + height, x:x + width].copy()
        crop[mask[y:y + height, x:x + width] == 0] = 0
        grain = ImageOps.pad(Image.fromarray(crop), (224, 224),
                             method=Image.Resampling.BICUBIC, color=(0, 0, 0))
        tensor = _TRANSFORM(grain)
        shape_values = mask_geometry(mask)
        selected = mask != 0
        mean_r, mean_g, mean_b = self.rgb[selected].mean(axis=0)
        mean_saturation = float(self.hsv[:, :, 1][selected].mean())
        mean_value = float(self.hsv[:, :, 2][selected].mean())
        gray_pixels = self.gray[selected]
        gray_std = float(gray_pixels.std())
        hist = np.bincount(gray_pixels, minlength=256).astype(np.float64)
        probabilities = hist[hist > 0] / hist.sum()
        gray_entropy = float(-(probabilities * np.log2(probabilities)).sum())
        values = np.asarray([*shape_values, mean_r, mean_g, mean_b,
                             gray_std, mean_saturation, mean_value, gray_entropy],
                            dtype=np.float32)
        if not np.isfinite(values).all():
            raise ValueError("Mask produced invalid OpenCV features")
        return tensor, values, [x, y, width, height]
