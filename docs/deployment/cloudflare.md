# Cloudflare deployment — frontend and same-origin API proxy

**What is already in the repository:** the React/Vite site is configured for Cloudflare Pages, and `frontend/functions/api/[[path]].ts` forwards `/api/*` to a separately hosted FastAPI backend. The SQLite database is stored and managed by that Python backend.

**What is not automatically complete:** uploading the code ZIP does not authenticate to your Cloudflare account, create a Pages project, attach a domain, supply an API origin, procure persistent backend hosting, or configure SMTP. Do not claim a live deployment until those steps have been completed and tested.

## 1. Python API with persistent SQLite

Deploy `backend/` to a Python-capable HTTPS host (for example, a VM or a container platform with a **persistent mounted disk**). Run:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set `RICEGRADE_DB_PATH` to an **absolute path on your persistent volume**, e.g. `/data/ricegrade.sqlite3`. Mount/backup that volume; never rely on ephemeral filesystem storage for user accounts or images. Use an HTTPS reverse proxy, appropriate access controls, regular backups, and monitoring. The web app stores test sample images (up to 5 MB each) as SQLite BLOBs; monitor disk usage. For larger production workloads, consider moving image bytes into an object store.

Set SMTP credentials and `RICEGRADE_PUBLIC_URL` to enable password-reset email. Without these, forgot-password explicitly reports it is not configured; sign-up, sign-in, profile and password change still work.

Cloudflare Pages Functions/Workers cannot directly run the existing FastAPI process or access a traditional mounted SQLite file. Cloudflare D1 is SQLite-compatible but would require its own API implementation and migration; this project deliberately keeps **one FastAPI + SQLite backend** to remain compatible with the planned Python ML pipeline.

## 2. Cloudflare Pages

Create a Pages project for the RiceGrade repository. The build settings are:

- **Root directory:** `frontend`
- **Build command:** `npm ci && npm run build`
- **Output directory:** `dist`
- **Framework:** Vite / React
- **Functions directory:** `frontend/functions` (auto-discovered by Pages)

In Pages **Settings → Environment variables and secrets**, configure:

```
RICEGRADE_API_ORIGIN=https://YOUR-PYTHON-BACKEND-HOST
```

This must be a hostname with HTTPS and no trailing path (e.g. `https://api.example.com`); the function appends `/api/...`. Do not put private credentials in `VITE_*` variables; those are embedded in public frontend bundles. Ensure the backend accepts authenticated requests from the Pages proxy. The proxy preserves the Bearer token and avoids cross-origin browser requests.

You can also deploy from `frontend/` using Wrangler after authenticating to Cloudflare:

```bash
npm run build
npx wrangler login
npx wrangler pages deploy dist --project-name ricegrade-web
```

The Pages project and any environment variables still need to exist/be configured. Replace the project name if you use a different name.

## 3. Verify before using with actual users

- Open the Pages URL on desktop and mobile widths; verify menus and forms.
- Check `https://YOUR-PAGES-DOMAIN/api/health` returns `{"status":"ok","service":"ricegrade-api"}`.
- Register, sign in, reload, log out, change password and sign in again.
- Save a test run with paddy and total milled-rice weights; confirm the record is still present after **restarting the backend host**.
- Upload and retrieve a rice image while authenticated; verify a second account cannot retrieve that image.
- Test an actual email reset link through configured SMTP.
- Check HTTP security, backend process supervision, persistent disk backups, and real production TLS.

The visual classifier, XGBoost fusion, DSS recommendations, and finalized quality reports are *not* connected in this UI-first milestone. The report queue explicitly displays that status.
