# RiceGrade model integration — PRIVATE research-preview service

## What is ready

- `server.py` loads the frozen trained EfficientNet-B0 (1280 features), extracts 16 OpenCV descriptors for each provisional mask, and runs the saved XGBoost hybrid classifier.
- `src/index.js` and `wrangler.toml` optionally deploy the Python service as a **Cloudflare Container** behind a service-secret-authenticated Worker. No raw R2 object is published.
- The existing Pages Function authenticates the user, checks assessment ownership, retrieves the original image from private R2, sends it to the service, and stores a research preview in D1.
- The React History/Report pages show class **counts and percentages by grain count only**. No official grade, calibrated confidence, machine-setting claim, or DSS recommendation is generated.

**Important research limitation:** the automatic isolation uses provisional Otsu thresholding and connected components on separated white grains against a dark, uniform backdrop; it has not been measured against local expert masks. Touching grains may merge. Your teammate's original reported classification metrics used ground-truth segmentation masks and do not establish full photographic screening accuracy. Model scores are uncalibrated; do not present this as a production QA pass/fail system.

## Architecture

`ricegrade.pages.dev` React → authenticated `/api/evaluations/{id}/screening` Pages Function → private R2 image → secret-authenticated `ricegrade-model` Worker → Python/PyTorch container → returned model counts → stored `screening_trials` in D1 → authenticated History/Reports UI.

Existing D1 accounts and R2 images continue to work. The original `frontend/wrangler.toml` with its `DB` and `IMAGES` bindings is **not replaced** by the model service's own `wrangler.toml`.

## Prerequisites and billing

Cloudflare Containers require the **Workers Paid** plan. Docker must be installed on the developer computer for Wrangler to build and push the model image. The `standard-1` instance uses 0.5 vCPU and 4 GiB provisioned RAM; on-demand usage can incur costs beyond the included paid-plan allowance. A group member responsible for billing must review costs and approve the plan manually. **No new subscription is created by these files.**

Official Cloudflare guidance: https://developers.cloudflare.com/containers/get-started/ and https://developers.cloudflare.com/containers/platform/pricing/

## Deployment sequence (use these in order)

1. Merge only the frontend files from `RiceGrade_Model_Frontend_Patch.zip` into your current Git repo. Review with `git diff`. Preserve all current team changes, the 100,000 PBKDF2 registration hotfix, and your D1/R2 bindings.
2. On your computer, from the repo root: `cd frontend` then `npx wrangler d1 migrations apply ricegrade_db --remote`. Confirm the new `screening_trials` table exists in your production D1 database. Apply this migration **before** deploying the new API source.
3. Copy `model_service/` from the model service ZIP under the repo root. The model checkpoint `model_service/models/final_ricegrade/efficientnet_b0.pth` is ~16 MB. If the repo is public, get explicit consent from the model authors before publishing the weights. Keep secret tokens out of Git entirely.
4. Generate ONE random token locally (example: `python -c "import secrets; print(secrets.token_hex(32))"`). Save it securely as `RICEGRADE_ML_TOKEN` in *two* places: the new `ricegrade-model` Worker secret and the existing RiceGrade Pages Production secret. It must be **identical in both places**, at least 32 characters, and never committed. If you suspect disclosure, rotate both.
5. Activate Workers Paid if your group's billing administrator approves. Ensure Docker Desktop (or a working Docker daemon) is running. From `model_service/` run `npm install`, `npx wrangler login`, `npx wrangler deploy`, then `npx wrangler secret put RICEGRADE_ML_TOKEN` and paste the generated token. The second operation updates the deployed Worker; deploy again if prompted. Cloudflare Containers may take several minutes to provision after first deployment.
6. Copy the deployed Worker **origin**, for example `https://ricegrade-model.<your-workers-subdomain>.workers.dev`. Under **Pages project ricegrade → Settings → Variables and Secrets**, set Production variable `RICEGRADE_ML_ORIGIN` to that HTTPS origin (no `/predict/image` path), and add Production secret `RICEGRADE_ML_TOKEN` with the same token. Trigger a new production Pages deployment. Keep the existing `DB` and `IMAGES` bindings.
7. Verify the gateway at `https://ricegrade-model.<subdomain>.workers.dev/health`. It should respond with `ricegrade-model-gateway`. Requests to `/predict/image` without the service token must return 401. For privacy, do NOT paste tokens into the browser or expose them in frontend code.
8. Sign in at https://ricegrade.pages.dev, open History → select your own assessment with an image → **Run experimental grain screening**. The first request may take extra time while the container starts. You will see **Research preview / Manual review required** and the four class counts if the photo meets the provisional segmentation conditions.

To validate without paying yet, you can test `model_service/server.py` locally with a private test image and the local `RICEGRADE_ML_TOKEN`; the UI bridge requires an HTTPS model origin to run from the production Pages project.

## Local model service test

Use Python 3.11, with compatible CPU PyTorch/TorchVision and dependencies:

```sh
cd model_service
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 torchvision==0.22.1
pip install -r requirements-server.txt
python check_bundle.py
python -m unittest discover -s tests -v
```

Test locally with a private HTTP client only (no sensitive credential in terminal history). `server.py` expects `RICEGRADE_ML_TOKEN` in its environment, and runs with `uvicorn server:app --port 8080`.

## API contract and correct interpretation

- `POST /api/evaluations/{id}/screening` → authenticated, expensive, up to three attempts per uploaded image; result is cached in D1.
- `GET /api/evaluations/{id}/screening` → authenticated, owner-only retrieval; research preview persists across sessions.
- Replacing the image removes the old result so stale predictions cannot be reused.
- On backend timeout or failure, a structured error is stored; after a stale processing lease, a retry is possible.
- The preview is a **single-label** four-class model: whole, broken, chalky, discolored. A grain can physically have two attributes, but this trained model does not report both.
- Count percentages **cannot** be compared directly with PNS/BAFS grade limits that use percentage by mass.

## Pre-production validation still needed

Annotate real local photos with grain-instance masks, calculate segmentation precision/recall/IoU and the true number of isolated grains, then evaluate end-to-end *predicted-mask* classification on held-out test-mill samples. Establish screening thresholds and class-score calibration before enabling a DSS recommendation. Verify performance on phone images and background/camera conditions actually used at local mills.

## Notes / known limits

- Image upload accepts up to 5 MB. Inference downsamples originals over 1.5 megapixels (up to 24 megapixels input) for an *experimental preview*, with a warning that pixel-size morphology may shift; raw R2 images remain unchanged.
- One inference job per container at a time; high volume requires a properly queued and monitored architecture.
- The front-end production build was not executed in this assistant environment because a dependency was unavailable offline; Cloudflare Pages CI should run `npm ci && npm run build` and reveal any build errors before production activation.
- The Docker image was not built or pushed here because this environment has no Docker daemon and no access to your Cloudflare account.
