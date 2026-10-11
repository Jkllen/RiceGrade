# Architecture decisions — UI-first milestone

1. Keep a single FastAPI backend: accounts, measurements, image records and future ML inference share a Python service. SQLite uses a persistent disk path, foreign keys, and WAL.
2. Cloudflare Pages serves the React + TypeScript + Vite frontend. Pages Functions proxy same-origin `/api` requests to a separately hosted FastAPI HTTPS origin. **Cloudflare does not run the local SQLite file or FastAPI process.**
3. Store small, authenticated rice sample images as SQLite BLOBs for the prototype; use private object storage if future image volume grows.
4. Account API implements session validation, sign-up/in/out, profile editing, password change, and reset tokens/email when SMTP is configured. Production requires additional anti-abuse hardening.
5. Separate image-quality classification from physically measured milling recovery. Total recovery uses actual paddy input and total white rice mass; optional brown/head recovery only if measured. All weight entries use grams.
6. Support all major UI routes now; save assessments as `awaiting_model` and do not create fictitious class percentages, quality grades, DSS recommendations or final quality reports.
7. Keep the teammate's EfficientNet-B0 checkpoint and training scripts outside the deployment app until the deep-feature and XGBoost integration is verified.
8. Authentication screen hiding is not authorization: every account-owned API resource checks user session and ownership independently.
