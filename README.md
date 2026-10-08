# RiceGrade — Authentication & dashboard scaffold

Research prototype using **React + TypeScript + Vite + Tailwind CSS**, **FastAPI + Uvicorn**, and **SQLite**. Current workflow follows test-mill evaluation; ML modules and scientific thresholds are **not implemented**.

## Start from repository root

Backend (in one terminal):

```bash
python -m venv .venv
# Activate .venv on your OS
python -m pip install -r backend/requirements-dev.txt
cd backend
uvicorn app.main:app --reload
```

Frontend (in a different terminal):

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173/ . Sign up with an email address and a password of at least 12 characters, then you can use the protected dashboard.

Run backend tests from `backend/`: `python -m pytest -q` (after installing requirements). Run frontend build from `frontend/`: `npm run build`.

## Implemented

- Public sign in, sign up, forgot-password and reset-password placeholder screens
- Securely salted password hashes and revocable opaque sessions in local SQLite
- Backend checks of sessions for `/api/auth/me` and `/api/dashboard`
- Authenticated-user dashboard with four action cards plus log out
- Explicit placeholders for New Rice Analysis, Screening Report, Assessment History and Profile Management

## Not yet implemented

- Password-reset email link delivery; its API deliberately responds `501`, without saying an email was sent
- Email verification, rate limiting, production cookie/session hardening and deployment security review
- Production-ready account roles, ownership permissions for future resources
- Actual lots, physical measurements, image segmentation, models, recommendations, saved reports

See `docs/architecture/auth-flow.md`, `docs/decisions.md`, and `docs/traceability.md`.

Research images/data, local SQLite DBs, secrets, and ML artifacts are ignored by Git. Use synthetic deterministic test fixtures for unit tests, never fake classification outcomes in real reports.
