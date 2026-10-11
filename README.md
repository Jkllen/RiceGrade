# RiceGrade — Cloudflare-native application milestone

A **responsive React + TypeScript** research web app with **Cloudflare Pages Functions + D1** for deployed authentication and persistent test-mill assessments. The independent Python FastAPI/SQLite prototype is kept in `backend/` for local/reference use and potential Python ML inference development; **the Cloudflare site no longer proxies its API to FastAPI**.

## Features ready in code

- Real registration, sign-in, session revocation, sign-out, profile edit and password change using D1.
- Password-reset token flow; real email delivery needs provider secrets (see deployment guide).
- Responsive dashboard, navigation, history, test-mill evaluation, report queue and account screens.
- Protected records: lot ID, test-run ID, measurements, recovery calculations, dates and optional notes.
- Recovery: `100 × total_milled_rice_weight / paddy_input_weight`; optional brown/head recovery when weights exist.
- Private sample images supported through **optional R2 binding** after bucket creation.
- Explicit `awaiting_model` status: no fictional model predictions, DSS results or official rice grades.

## Deploy to Cloudflare

Read [docs/deployment/cloudflare.md](docs/deployment/cloudflare.md). **Important:** apply `frontend/migrations/0001_initial.sql` using Wrangler's D1 migration command `--remote` before trying to sign up. The D1 binding `DB` is already configured for `ricegrade_db` in `frontend/wrangler.toml`. The Pages project remains `ricegrade` at https://ricegrade.pages.dev .

From `frontend/`:

```bash
npm ci
npx wrangler login
npx wrangler d1 migrations apply ricegrade_db --remote
npm run build
npm run cf:test-api
```

Then commit/push the updated source to `main` to trigger the Pages build. The Cloudflare app becomes functional **after migration and successful deployment**, not by downloading this ZIP alone.

## Project notes

- `frontend/functions/api/[[path]].ts` — Cloudflare API handlers (Web Crypto password hashing, D1-backed sessions and records, optional private R2 image API).
- `frontend/migrations/0001_initial.sql` — persistent database schema.
- `frontend/cloudflare-tests/api-smoke.mjs` — local API integration smoke test with Node 22 built-in SQLite.
- `frontend/wrangler.toml` — Cloudflare Pages/D1 bindings. Uncomment optional R2 binding after creating the bucket.
- `backend/` — prior Python development implementation; not production Cloudflare API.
- `docs/model-integration.md` — ML handoff and unvalidated items.

Never commit `.env`, keys, tokens, user data, or research images to GitHub. Existing local SQLite accounts are **not automatically migrated** into Cloudflare D1; production D1 begins with no users unless separately imported via an approved migration.
