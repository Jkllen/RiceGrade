# RiceGrade — UI-first implementation

A **responsive React + TypeScript** research web app with a **FastAPI + SQLite** backend. This milestone implements the account experience and saves actual test-mill measurements while the EfficientNet-B0 training and hybrid model integration are pending.

## What works

- Email/password sign-up and sign-in, session validation, sign out, dashboard guards and protected API endpoints
- Operator/QA role labels, profile editor, current-password verification, password changes and revocation of other sessions
- Password-reset tokens and SMTP email sending **when SMTP environment variables are configured** (otherwise a truthful configuration error)
- Mobile-friendly dashboard, navigation, assessment form, assessment history/details, report queue, profile and all account screens
- Authenticated, ownership-protected sample records and original JPEG/PNG/WebP images (max 5 MB) stored in SQLite
- Required paddy input / total milled rice weight, optional brown rice / head rice weight and physically measured moisture
- Server-verified total, brown-rice and head-rice milling-recovery calculations (grams; percentages) and input consistency checks
- Cloudflare Pages build files and a `/api` Pages Function reverse proxy to a separately hosted Python backend

## Not implemented — no placeholder results are fabricated

- Fully integrated OpenCV grain segmentation, trained EfficientNet-B0 + engineered feature fusion, XGBoost four-class inference
- Confidence calibration and quality count percentages, validated DSS thresholds, finished quality-screening reports
- Live Cloudflare deployment, persistent hosting and email credentials (require the owners' infrastructure access)

## Local setup

From the repo root, start the backend in terminal 1:

```bash
python -m venv .venv
# Activate the environment for your OS
python -m pip install -r backend/requirements-dev.txt
cd backend
uvicorn app.main:app --reload
```

The default local SQLite file remains `ricegrade.sqlite3` **at the repository root**, matching the original scaffold so existing local accounts are not lost. To point to another location, set `RICEGRADE_DB_PATH` to an absolute path. No tables need to be created manually: SQLite initialization and additive migration happen automatically. Data survives application restarts.

From terminal 2:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite development server proxies `/api` to `http://127.0.0.1:8000`.

## Verification

```bash
cd backend && python -m pytest -q
cd frontend && npm run build
```

See [Cloudflare deployment instructions](docs/deployment/cloudflare.md), [authentication design](docs/architecture/auth-flow.md) and [flowchart traceability](docs/traceability.md). All ML implementations must be audited independently before enabling screening. The uploaded training ZIP is kept as a separate research artifact, rather than silently merged into production inference.
