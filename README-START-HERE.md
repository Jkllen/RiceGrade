# RiceGrade — activate Cloudflare R2 and clarify model status

This is a **small PATCH for your existing `main` branch**, not a replacement repository.

## First: create the bucket

1. Cloudflare Dashboard → **Storage & databases → R2 Object Storage**.
2. If Cloudflare asks you to activate an R2 subscription or enter payment details, review its billing terms with the account owner before proceeding; R2 includes a free allowance but exceeding it can incur charges.
3. Create a bucket with the **exact name** `ricegrade-images`.
4. **Leave public access disabled**. Sample photographs may contain sensitive context. Avoid public `r2.dev` URLs.

## Then: merge the patch

Merge the `frontend/` and `docs/` folders from this ZIP with your existing repository. Do not delete `.git`, do not replace the whole repository, and don't overwrite the sign-up hotfix in `frontend/functions/api/[[path]].ts`.

The patch enables this **existing** block in `frontend/wrangler.toml`:

```toml
[[r2_buckets]]
binding = "IMAGES"
bucket_name = "ricegrade-images"
```

The D1 binding (`DB`) remains unchanged. The Pages API **already** supports authenticated R2 uploads and downloads, so no D1 migration or new API rewrite is needed. The other patched files merely update the UI's wording: the model is trained but live automatic grain isolation/inference remains unintegrated.

From repo root:

```bash
git status
git add frontend/wrangler.toml frontend/src/features docs/deployment/r2-image-storage.md
git commit -m "Connect private R2 image storage"
git push origin main
```

Wait for Cloudflare Pages → `ricegrade` → Deployments to show a successful new production deploy. Check Settings → Bindings for `DB` (D1) and `IMAGES` (R2).

## Verify using your account

1. Open `https://ricegrade.pages.dev`, sign in.
2. Create a test assessment with realistic **test** weights, and attach a small JPEG or PNG (<= 5 MB).
3. Open Assessment History; select the saved assessment and confirm its photo loads.
4. Confirm the R2 bucket has a private object and D1 `assessment_images` table has a reference.
5. Sign out and ensure protected assessment/image endpoints do not reveal the file without authentication.
6. Delete the test assessment and confirm the related object is removed.

The web app will continue to show **Awaiting integration** for ML/DSS. That is correct until automatic grain segmentation and the full inference-to-DSS workflow have been validated and connected.

No Cloudflare account changes, subscription, deployment, or D1 changes were performed by ChatGPT. You must create the bucket and commit the patch yourself.
