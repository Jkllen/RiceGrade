"""Service-level tests against the *real saved classifier* on synthetic shapes.
Passing these tests does NOT validate segmentation or rice-grain accuracy.
"""
import io
import os
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from server import app


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = 'inference-test-token-longer-than-32-characters'
        cls.environ = patch.dict(os.environ, {'RICEGRADE_ML_TOKEN': cls.key})
        cls.environ.start()
        cls.client = TestClient(app)
        cls.client.__enter__()
        rgb = np.zeros((260, 320, 3), dtype=np.uint8)
        cv2.ellipse(rgb, (72, 80), (9, 24), 10, 0, 360, (235, 220, 210), -1)
        cv2.ellipse(rgb, (160, 140), (12, 29), -12, 0, 360, (222, 218, 215), -1)
        cv2.ellipse(rgb, (240, 78), (11, 23), 6, 0, 360, (243, 230, 215), -1)
        file = io.BytesIO()
        Image.fromarray(rgb).save(file, format='PNG')
        cls.image = file.getvalue()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.environ.stop()

    def test_no_public_inference(self):
        result = self.client.post('/predict/image', content=self.image, headers={'Content-Type':'image/png'})
        self.assertEqual(result.status_code, 401)

    def test_invalid_content_type(self):
        result = self.client.post('/predict/image', content=b'not an image',
                                  headers={'X-RiceGrade-Service-Key':self.key,'Content-Type':'text/plain'})
        self.assertEqual(result.status_code, 415)

    def test_synthetic_inference_works(self):
        result = self.client.post('/predict/image', content=self.image,
                                  headers={'X-RiceGrade-Service-Key':self.key,'Content-Type':'image/png'})
        self.assertEqual(result.status_code, 200, result.text)
        preview=result.json()
        self.assertEqual(preview['status'], 'experimental_unvalidated_segmentation')
        self.assertEqual(preview['total_grains'], 3)
        self.assertEqual(sum(preview['counts'].values()), 3)
        self.assertTrue(preview['manual_verification_required'])
        self.assertIsNone(preview['official_grade'])
        self.assertIsNone(preview['dss_result'])


if __name__ == '__main__':
    unittest.main()
