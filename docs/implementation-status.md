# RiceGrade Cloudflare backend milestone — 2026-10-12

**Implemented in this repository, not yet confirmed running in the user's Cloudflare deployment until they apply migration and push:**

- Pages Functions endpoint `/api/*` replaces the earlier FastAPI reverse proxy.
- D1 schema for users, sessions, password resets, throttling records, assessments, private image metadata and planned report metadata.
- Sign-up/in/out, profile edits, password changes, account ownership checks and persisted recovery calculations.
- Optional R2 private image upload/retrieval; unavailable with a truthful 503 until `IMAGES` is bound.
- Password-reset flow with expiring one-use tokens; email delivery requires Resend credentials and verified sending domain.
- TypeScript compilation succeeded (`tsc -p frontend/cloudflare-tests/tsconfig.json`).
- Local migration applied to in-memory SQLite; account, ownership and recovery test suite (`frontend/cloudflare-tests/api-smoke.mjs`) passed.

The ML / DSS inference path is **not implemented**. `reports` is a future metadata table, not a claim of finalized screening reports.

The earlier milestone's Python backend remains separate, and its previous 10 pytest cases related to that reference backend—not production Cloudflare.

Frontend source syntax and responsive layout were checked earlier, but a full npm production build and an authenticated **live Cloudflare D1 deployment** must still be verified after merging/pushing the new source.
