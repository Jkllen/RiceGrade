
import csv
from pathlib import Path

import numpy as np
import torch

from PIL import Image, ImageOps
from torch.utils.data import Dataset
from torchvision import transforms
from pycocotools.coco import COCO
from pycocotools import mask as mask_utils


class RiceGrainDataset(Dataset):

    def __init__(self, manifest_path, train=False):

        self.train = train

        with open(
            manifest_path,
            newline="",
            encoding="utf-8"
        ) as file:

            self.records = list(
                csv.DictReader(file)
            )

        # Cache COCO metadata, not cropped images.
        annotation_paths = {
            record["annotation_path"]
            for record in self.records
        }

        self.coco_cache = {
            path: COCO(path)
            for path in annotation_paths
        }

        if train:
            self.transform = transforms.Compose([
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.RandomVerticalFlip(p=0.5),
                transforms.RandomRotation(15),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225]
                )
            ])
        else:
            self.transform = transforms.Compose([
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225]
                )
            ])

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):

        record = self.records[index]

        image_path = record["image_path"]
        annotation_path = record["annotation_path"]
        annotation_id = int(record["annotation_id"])

        coco = self.coco_cache[annotation_path]
        annotation = coco.anns[annotation_id]

        # Find exact mask bounds from compressed COCO data instead of
        # allocating coordinates for every foreground pixel in the image.
        rle = coco.annToRLE(annotation)
        x1, y1, width, height = mask_utils.toBbox(rle).astype(np.int64)
        if width <= 0 or height <= 0:
            raise ValueError(
                f"Empty mask: annotation {annotation_id}"
            )
        x2, y2 = x1 + width, y1 + height
        mask = mask_utils.decode(rle)

        with Image.open(image_path) as img:
            if mask.shape != (img.height, img.width):
                raise ValueError(
                    f"Mask and image mismatch: {image_path}"
                )
            # JPEG decoding still reads the source image, but only the grain
            # region needs RGB conversion and a NumPy array.
            crop = np.array(img.crop((x1, y1, x2, y2)).convert("RGB"))

        crop_mask = mask[y1:y2, x1:x2].astype(bool)

        # Remove background pixels.
        crop[~crop_mask] = 0

        grain = Image.fromarray(crop)

        # Preserve aspect ratio with square padding.
        grain = ImageOps.pad(
            grain,
            (224, 224),
            method=Image.Resampling.BICUBIC,
            color=(0, 0, 0)
        )

        tensor = self.transform(grain)

        label = int(record["class_id"])

        return tensor, label
