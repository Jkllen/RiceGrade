"""Research-only local grain classification. Never writes official grades or DSS outputs.

Usage with annotated masks (NPZ masks: N,H,W):
  python predict_photo.py --image rice.jpg --masks supplied_masks.npz --output trial.json

Experimental OpenCV mode for high-contrast separated white rice (NOT validated):
  python predict_photo.py --image rice.jpg --experimental-opencv --output trial.json --overlay overlay.png
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from check_bundle import verify
from ricegrade import RiceGradePredictor
from segment_opencv import extract_masks, overlay_mask_boundaries


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image',type=Path,required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--masks',type=Path,help='NPZ with masks array of shape (N,H,W)')
    mode.add_argument('--experimental-opencv',action='store_true',help='UNVALIDATED automatic mask isolation')
    ap.add_argument('--bundle',type=Path,default=Path(__file__).parent/'models'/'final_ricegrade')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--overlay',type=Path,help='Optional local QA image showing mask boundaries')
    ap.add_argument('--device',choices=['cpu','cuda','auto'],default='auto')
    args = ap.parse_args()
    verify(args.bundle)
    with Image.open(args.image) as im:
        rgb = np.array(im.convert('RGB'),dtype=np.uint8)
    if args.masks:
        with np.load(args.masks,allow_pickle=False) as data:
            if 'masks' not in data:
                raise ValueError('NPZ requires a masks array')
            array=data['masks']
        if array.ndim != 3 or array.shape[1:] != rgb.shape[:2]:
            raise ValueError('Masks must have shape (N,image_height,image_width)')
        masks = [array[i] for i in range(len(array))]
        provenance='supplied_instance_masks'
        warnings=['Instance-mask quality must be independently verified']
    else:
        sample=extract_masks(rgb)
        masks=sample.masks
        provenance='experimental_opencv_unvalidated'
        warnings=sample.warnings
        if not masks:
            raise ValueError('No usable grain instances isolated; try a controlled recapture')
    predictor=RiceGradePredictor(args.bundle,device=args.device)
    prediction=predictor.predict(rgb,masks)
    result={
        'status':'research_only_not_an_official_rice_grade',
        'segmentation_source':provenance,
        'segmentation_warnings':warnings,
        'model_validation_scope':'ground_truth_COCO_masks_on_held_out_data',
        'model_test_accuracy_from_bundle':0.9099917423616846,
        'visual_count_percentages_only':True,
        'dss_result':None,
        'result':prediction,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    if args.overlay:
        args.overlay.parent.mkdir(parents=True,exist_ok=True)
        cv2.imwrite(str(args.overlay),overlay_mask_boundaries(rgb,masks))
    print(f'Research-only prediction saved: {args.output}; grains={prediction["total_grains"]}; masks={provenance}')


if __name__=='__main__':
    run()
