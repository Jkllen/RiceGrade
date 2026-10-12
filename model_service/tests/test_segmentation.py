import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from segment_opencv import extract_masks

class TestSegmentationPreview(unittest.TestCase):
    def test_isolated_ellipses(self):
        rgb=np.zeros((250,350,3),dtype=np.uint8)
        for center in [(60,80),(170,80),(280,80),(110,178),(240,178)]:
            cv2.ellipse(rgb,center,(10,24),17,0,360,(218,220,230),-1)
        res=extract_masks(rgb)
        self.assertEqual(len(res.masks),5)
        self.assertIn('NOT been validated',res.warnings[-1])
    def test_no_light_background(self):
        rgb=np.full((70,70,3),255,dtype=np.uint8)
        with self.assertRaisesRegex(ValueError,'dark'):
            extract_masks(rgb)

if __name__=='__main__': unittest.main()
