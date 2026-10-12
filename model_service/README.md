# RiceGrade — corrected frozen ML bundle and local inference trial

## What is verified

The teammate's updated ZIP includes a **completed hybrid** XGBoost classifier with 1,280 EfficientNet-B0 features + 16 OpenCV features per isolated grain. Label order is **broken, chalky, discolored, whole**. The saved held-out test results report **90.9992% accuracy**, **89.6901% macro F1** on **1,211 masked grains from 95 held-out source images**. Metrics were recorded by the teammate's evaluation; they are not an independent retraining or a clinical/official product-grade validation. The hybrid model beat CNN-only XGBoost by ~0.1813 percentage points in validation macro F1, a very small difference.

The submitted ZIP itself has an **artifact packaging problem**. Four human-readable JSON metadata files have LF line endings even though their frozen `manifest.json` contains SHA256 hashes for their CRLF versions. Consequently, the teammate's strict model loader **fails immediately** with `Artifact checksum mismatch: class_labels.json` when reading the original ZIP. Both binary model files (`efficientnet_b0.pth` and `xgboost.json`) were already correct.

The copies in `models/final_ricegrade/` in **this** package restore CRLF on those four JSON metadata files **only where this makes their original manifest hash match**. None of the model parameters, training algorithms, class mapping, or model contents were changed. Every manifest checksum now passes. The original uploaded ZIP has not been modified.

For protection against future line-ending conversion, `.gitattributes` marks frozen JSON artifacts `-text`. Keep them byte-for-byte identical. Check with:

```bash
python check_bundle.py
```

## First: install and run a local inference

Use Python 3.11 and the teammate's pinned `requirements-inference.txt`; install a PyTorch/Torchvision pair matching your CPU/GPU environment (see teammate's `RICEGRADE_INTEGRATION.md`). `check_bundle.py` can run without Torch.

**With manually supplied instance masks** in `.npz` format (key `masks`, shape `(N,H,W)`, 1 separate binary mask per rice grain):

```bash
python predict_photo.py --image path/to/sample.jpg --masks path/to/grain_masks.npz --output prediction.json --device cpu
```

**Experimental OpenCV grain isolation** for separated white rice on a dark, uniform background:

```bash
python predict_photo.py --image path/to/sample.jpg --experimental-opencv --output research_trial.json --overlay outline.png --device cpu
```

This optional experimental segmentation uses Otsu thresholding, basic noise filtering, and connected components. It does **not** implement or verify a validated watershed treatment for touching grains, and can merge multiple grains. The size and image conditions are provisional. The output is explicitly marked research-only, not an official rice grade or DSS recommendation. Inspect each overlay and compare against manually annotated local test-mill images before relying on results.

The Python inference script and test fixture were exercised in this environment on **synthetic images**, not on local real-rice photographs. These tests verify execution, NOT rice sample accuracy. The frozen model has not been independently retrained.

## Integration sequence

1. Cloudflare Pages + D1 accounts remain online. Enable private R2 first (separate patch).
2. Collect standardized new test-milled white rice photos and hand-annotated instance masks under the actual capture conditions.
3. Validate OpenCV grain isolation on the local photographs, especially touching grains, false masks, missed grains, and cut-off grains. Revise the module if needed.
4. Evaluate the **full predicted-mask → 16+1280 features → XGBoost** chain on held-out local test-mill images, not just ground-truth COCO masks.
5. Only after that, add an authenticated image-analysis service. It must run in a secure Python environment capable of PyTorch/OpenCV/XGBoost, not inside Pages Functions. Keep model files server-side and private. The Cloudflare worker should authorize the job and mediate access to its private R2 input, using protected service-to-service authentication.
6. Save count-based predictions/reliability, not invented grain weights. Add validated DSS rules and mark report complete only once both the visual and recovery evidence satisfy the adopted criteria.

**Do not push model weights or inference code into `frontend/public/`, `frontend/dist/`, or any public R2 URL.**

## Test locally

```bash
python -m unittest discover -s tests -v
python check_bundle.py
```

Source: user's teammate training ZIP; Python predictor and `features.py` copied without modifications from its `ricegrade/` package. The two runner scripts and the **experimental** OpenCV segmenter are additional integration scaffolding.
