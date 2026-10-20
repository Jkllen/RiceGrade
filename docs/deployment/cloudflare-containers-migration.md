# RiceGrade — Cloudflare Containers migration (Workers Paid)

This procedure migrates ONLY the Python inference service. **Do not delete the existing Pages project, D1 database, R2 bucket, or previous screening records.**

## Architecture / scope

```
React (`ricegrade.pages.dev`)
  -> Pages Function (`frontend/functions/api/[[path]].ts`)
     -> user auth + D1 + private R2
     -> private service binding `RICEGRADE_MODEL`
        -> Worker `ricegrade-model`
           -> on-demand Cloudflare Container
              -> FastAPI / OpenCV / EfficientNet-B0 / XGBoost
```

- Pages and the container Worker deploy **independently**.
- `workers_dev = false` makes the model Worker private; do **not** publish the model endpoint. The Pages Function is the only intended caller.
- `RICEGRADE_ML_TOKEN` is a server-only secret in **both** projects: Pages (Production) and the model Worker. The model container receives the Worker's copy through `envVars`. Never put it in `wrangler.toml`, frontend React, Git, console screenshots, or a URL.
- `frontend/wrangler.toml` declares the service binding. `model_service/wrangler.toml` controls the Docker container. They are different deployment projects.
- The original `RICEGRADE_ML_ORIGIN` HTTP fallback remains in the Pages API for emergency rollback. **The new Pages config does not set this origin**: once the binding is active, a tunnel or public model address is unnecessary.

## Blocking prerequisite: exact model checkpoint

`model_service/models/final_ricegrade/efficientnet_b0.pth` is **NOT present** in the supplied `RiceGrade-main.zip`. `check_bundle.py` verifies its SHA-256 against `manifest.json`. The model in `RiceGrade-training-model.zip` has a **different SHA-256**; do not rename or substitute it.

Obtain the exact `efficientnet_b0.pth` file that the working local server currently loads from the original teammate's machine or their original model bundle. Copy it to:

```
model_service/models/final_ricegrade/efficientnet_b0.pth
```

It is intentionally ignored by Git. The Docker build context still includes it; do not remove it from the build context. Run this first:

```powershell
python model_service/check_bundle.py
```

Expected: `PASS: verified frozen model artifacts: ...`. If it fails, **stop**. This proves that the weights, class mapping and XGBoost model have not been accidentally mixed between training runs.

## Prerequisites

- Workers Paid active on **the same Cloudflare account** as your `ricegrade` Pages project.
- Docker Desktop with Linux containers: `docker info` should complete, not error.
- Node.js and npm; Cloudflare Wrangler access: `npx wrangler login`.
- Sufficient Cloudflare Containers entitlement, budget, and build resources. The `standard-1` instance is **CPU only**, with 0.5 vCPU and 4 GiB memory; it is *not a GPU training environment*.
- Keep a backup or commit of the working pre-migration source and Cloudflare configuration. Production will continue using the existing tunnel until the Pages patch is deployed.

## Deploy order — prevents breaking production

### A. Verify the model on your computer

At the repository root, after the correct `.pth` file has been copied:

```powershell
python model_service/check_bundle.py
cd model_service
npm install
npx wrangler login
npx wrangler --version
cd ..
```

Ensure `npm install` created `model_service/node_modules/` (ignored by Git). **Do not run `npm run dev` for inference**; the production deployment below builds the Docker image and uploads it to Cloudflare.

### B. Deploy the model Worker and Container first

From the repository root, after applying this patch (but before pushing Pages changes):

```powershell
cd model_service
npx wrangler deploy
npx wrangler containers list
```

First deployment builds the Python Docker image via Docker, pushes it to Cloudflare's registry, and starts provisioning. **Allow several minutes** for the initial rollout; watch Container logs in the Cloudflare dashboard if it doesn't become ready.

Then, still inside `model_service`:

```powershell
npx wrangler secret put RICEGRADE_ML_TOKEN
```

When prompted, provide a newly generated random secret (at least 32 characters). **Copy the exact same value into** Cloudflare dashboard → Workers & Pages → `ricegrade` (Pages project) → Settings → Variables and Secrets → Production secret `RICEGRADE_ML_TOKEN`. The Pages production secret may already exist; if its value cannot be recovered, **replace both secrets with a new matching token**. Never store the token in repository files. Updating the Worker secret creates a new Worker version; if prompted, deploy it.

### C. Deploy the Pages binding **after** the model Worker exists

The patch updates `frontend/wrangler.toml` with:

```toml
[[services]]
binding = "RICEGRADE_MODEL"
service = "ricegrade-model"
```

Commit and push the changes **only after the Worker deployment succeeds**; Cloudflare Pages' existing Git integration will redeploy the site. Confirm the new `RICEGRADE_MODEL` binding is present in the deployed Pages Production bindings. If your Pages build is configured from a dashboard rather than your Wrangler file, add a service binding manually via Pages → Settings → Bindings → Add → Service binding (`RICEGRADE_MODEL` → `ricegrade-model`) and redeploy.

Do **not** delete the D1/R2 bindings or run a fresh database migration. No database schema change is needed.

### D. Verify end to end

1. Confirm Pages build/Functions deployment completed.
2. Open `https://ricegrade.pages.dev`, sign in, and navigate to an assessment **with a compatible image**.
3. Run one image screening. It should use the Cloudflare service binding, start the container on demand, and return the familiar four-class count-based result.
4. If the first request is slow or fails during provisioning, check Workers & Pages → Containers and `ricegrade-model` logs. The Pages API still has its existing **three-attempts-per-image limit**; avoid repeatedly consuming attempts to test container availability. Prefer a fresh disposable assessment for end-to-end tests.
5. Let the container idle for more than five minutes and test another assessment to confirm cold-start recovery. Existing result caching means re-opening an already screened image will not start inference again.
6. Keep old model-local scripts available for debugging but stop the Quick Tunnel once production inference succeeds.

## Rollback

If the container is not available, avoid disabling Pages or deleting any data. Use a previously working Pages deployment/commit with the old tunnel-based origin; the Pages API retains its HTTPS origin fallback for controlled rollback. Restore `RICEGRADE_ML_ORIGIN` and its access token only in server-side configuration, not React/browser code. Do not expose the Worker publicly merely to bypass the binding.

## Troubleshooting

| Symptom | Check |
|---|---|
| `python check_bundle.py` fails | Missing/mismatched `.pth` or mismatched model metadata. Do not deploy until resolved. |
| `docker info` fails | Start Docker Desktop with Linux engine. |
| Image build or push fails | Run deploy from `model_service`, inspect Wrangler/Docker build output and Cloudflare permissions. |
| Pages returns 503 “Model service is not connected” | Confirm the Pages service binding is deployed, named `RICEGRADE_MODEL`, and the Pages token exists. |
| Pages returns 502 after cold start | Container rollout, missing model files, crash, port 8080, or token mismatch; check Cloudflare Container logs. |
| Model returns 401 | Both Worker and Pages must contain the same server-only `RICEGRADE_ML_TOKEN`. |
| Image returns 422 | Existing model segmentation or image-content issue; not a Containers binding failure. |
| Processing takes too long | CPU-only container may be slower than a GPU workstation; try `standard-2` after measuring actual latency and cost. |

## Security and cost

- Cloudflare Containers are billed based on allocated memory and disk while running and active CPU, plus applicable Workers/Durable Object usage. The Workers Paid plan includes a limited allowance, **not unlimited CPU inference**. Review the official current pricing and set billing alerts.
- Keep `workers_dev = false` for the model Worker, use a private service binding, retain secret authentication and owner checks on Pages, and never make R2 source images public.
- Standard Cloudflare Containers have no GPU. Use Colab or a GPU workstation for retraining; deploy the trained, verified weights for CPU inference.

Official references:
- https://developers.cloudflare.com/containers/get-started/
- https://developers.cloudflare.com/containers/platform/pricing/
- https://developers.cloudflare.com/containers/configuration/wrangler/
- https://developers.cloudflare.com/pages/functions/bindings/
