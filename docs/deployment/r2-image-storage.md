# RiceGrade R2 storage configuration

Cloudflare Pages project: `ricegrade`, production: `https://ricegrade.pages.dev`.
D1: `DB` → `ricegrade_db` (already configured).
R2: `IMAGES` → `ricegrade-images` (new, private).

R2 must be created **before deploying** the uncommented binding in `frontend/wrangler.toml`. Binding configuration is managed through Wrangler, not the Pages dashboard Add control.

Image API behavior in the D1 Pages Function (already implemented):

- Authenticated `POST /api/evaluations/:id/image`: JPEG, PNG or WebP upload, max 5 MB; owns the assessment; image bytes to R2 under a private per-user assessment key; metadata to D1.
- Authenticated `GET /api/evaluations/:id/image`: verify ownership before retrieving R2 object.
- Authenticated `DELETE /api/evaluations/:id`: removes R2 photo (when present) and D1 assessment.
- No public direct R2 URL is needed. Don't enable bucket public access.

Keep original D1 schema. No R2 access keys are necessary for a Pages Function with an R2 bucket binding.

The model files are deliberately kept **out of `frontend/`**. The trained PyTorch/XGBoost model must execute in a separate Python runtime later. Model inference is not enabled merely by attaching R2 storage.

References:
- https://developers.cloudflare.com/pages/functions/bindings/
- https://developers.cloudflare.com/pages/functions/wrangler-configuration/
- https://developers.cloudflare.com/r2/get-started/
