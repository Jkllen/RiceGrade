# RiceGrade production deployment — Pages Functions + D1 (+ optional R2)

This is the **Cloudflare-native** version of RiceGrade. Do not set `RICEGRADE_API_ORIGIN`: `frontend/functions/api/[[path]].ts` now directly handles accounts and assessment records against D1. The older `backend/` FastAPI/SQLite code remains for local/reference use and future Python-based ML experiments; it is **not** used by the Cloudflare website.

**Currently deployed Pages URL:** https://ricegrade.pages.dev
**Pages project:** `ricegrade`
**D1 binding:** `DB` → `ricegrade_db` (database ID set in `frontend/wrangler.toml`)
**Repository:** `Jkllen/RiceGrade`, branch `main`

The R2 image feature is optional until the `IMAGES` bucket binding exists; API explicitly returns 503 for image uploads and does NOT lose saved physical measurements.

## Step 1 — merge source code into your GitHub main branch

Extract this ZIP. Carefully **merge** its `frontend/` and documentation files into your actual existing Git repository. The archive has a `RiceGrade/` top-level folder; do not accidentally create `RiceGrade/RiceGrade/frontend` in GitHub. Preserve the `.git` folder and teammates' latest edits. Back up, review the diff, commit and push to `main`. Pages builds use **root directory `frontend`**, `npm ci && npm run build`, output `dist`.

In `frontend/wrangler.toml`, the existing Pages project is `ricegrade`, and `DB` points to `ricegrade_db`. The code does not access the unused original standalone Worker.

## Step 2 — apply D1 migration (required; DO NOT skip)

The dashboard currently shows zero tables. Binding D1 is **not** enough to create tables. The repo includes `frontend/migrations/0001_initial.sql` with `users`, `sessions`, `password_resets`, `login_attempts`, `assessments`, `assessment_images` and `reports`.

From the local repo root in a terminal:

```bash
cd frontend
npm ci
npx wrangler login
npx wrangler d1 migrations apply ricegrade_db --remote
```

Approve the migration when prompted. `--remote` is essential: without it, Wrangler defaults to a local database instead of your deployed D1 instance. You can verify 7 application tables (plus Wrangler's migration bookkeeping table and SQLite internals) under Cloudflare → D1 → `ricegrade_db` → Console/Explore Data. Avoid rerunning a manual SQL paste on top of a tracked migration.

You can migrate **before pushing** the new source code, provided your local copy contains the correct `wrangler.toml` binding; this avoids briefly deploying new API code against an empty DB.

**Safer ordering:** apply migration → commit and push code → confirm Pages deployment successful → visit `https://ricegrade.pages.dev/api/health` (expected `status:ok`, `service:ricegrade-cloudflare-api`, `database:ready`). The endpoint will return 503 with `schema_missing` if the new code is deployed before migration.

## Step 3 — test accounts online

Use a temporary test account (do not reuse a real password):

- Sign up, navigate the dashboard, sign out; sign in again.
- Edit profile; change password; verify older sessions are revoked.
- Create a test run with paddy weight 1000 g and milled rice weight 670 g; expected total recovery is **67%**, independent of ML.
- Verify assessment history survives refreshing the browser and using a second device/account.
- Verify the second account cannot retrieve the first account's assessment.

## Step 4 — add R2 for private sample images (separate setup)

Cloudflare dashboard → R2 → Create bucket `ricegrade-images`. R2 may require subscription/billing setup even while within free usage allowances. Review pricing with the account owner before activating it. **Do not configure public R2 bucket access.**

In `frontend/wrangler.toml`, uncomment:

```toml
[[r2_buckets]]
binding = "IMAGES"
bucket_name = "ricegrade-images"
```

Commit and push. The Pages Function stores images at private R2 object keys and checks assessment ownership through D1 before it allows viewing them. Maximum attachment 5 MB, JPEG/PNG/WebP signature checked. The application reports classification as pending. Test upload, retrieval, replacement and deletion after R2 is bound.

## Step 5 — optional real password-reset emails

The API implements single-use reset tokens expiring after 30 minutes, but **sending email needs a provider**. This package supports Resend's HTTPS API; do not attempt direct SMTP in Workers. Verify a sending domain in that provider and configure the following **server-side Pages secrets** in Cloudflare (never `VITE_...`, never put API keys in `wrangler.toml` or GitHub):

- `RESEND_API_KEY` — service API key
- `RESET_FROM_EMAIL` — sender address on the verified domain
- `RICEGRADE_PUBLIC_URL` — `https://ricegrade.pages.dev` (nonsecret variable)

Since this Pages project uses `wrangler.toml`, verify in the Cloudflare Pages Settings that secrets/variables have been deployed to the right production environment; keep secret values outside source. Redeploy if needed. Before configuration, forgot-password returns a truthful `503` error instead of pretending an email was sent. Reset emails can contain sensitive links, so never share reset URLs or credentials.

## Development, tests, and limitations

```bash
cd frontend
npm ci
npm run build
# Node 22+ for the local, in-memory API smoke test:
npm run cf:test-api
```

Production D1 and R2 bindings should be tested through Pages; the Node smoke test uses a local SQLite-backed D1 adapter and does not authenticate to Cloudflare.

The existing `npm run dev` Vite proxy still points to the local FastAPI reference backend on `127.0.0.1:8000`. For end-to-end **Cloudflare API** local development, build and run `npx wrangler pages dev dist` with local D1 migration; this is separate from Vite's Python-backend development mode.

Account tokens in the current React prototype live in **sessionStorage**, are revocable in D1, and are sent in Bearer headers. Use Cloudflare's access and rate-limiting controls and review logging/security before admitting real participant data. The authentication code includes password hashing and per-address login/reset quotas but is not a third-party security audit.

Classification, DSS recommendations and finalized quality screening reports remain pending until validated models and rules exist; no synthetic quality percentages are generated.
