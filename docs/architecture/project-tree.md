# Current module boundaries

- `frontend/src/components/layout/`: desktop sidebar, mobile navigation and responsive app shell.
- `frontend/src/components/ui/`: shared UI elements, notices, navigation icons, loading and status.
- `frontend/src/features/{auth,dashboard,analysis,reports,history,profile}/`: complete UI screens with real account/measurement APIs or explicitly pending research outputs.
- `frontend/src/lib/`: typed API client and assessment models.
- `frontend/functions/api/`: Cloudflare Pages Function proxying `/api` to the Python backend.
- `backend/app/api/routes/auth.py`: account lifecycle and mail-delivered reset tokens.
- `backend/app/api/routes/evaluations.py`: authenticated record creation, deterministic recovery, retrieval, deletion and image attachment.
- `backend/app/core/auth.py`: SQLite initialization, minimal additive migration, session verification, password hashing.
- `backend/app/vision/`, `backend/app/ml/`, `backend/app/domain/`: future validated analysis and DSS logic (currently no fake outputs).
- `backend/tests/`: isolated API and SQLite tests.
- `experiments/`, `data/`, `artifacts/`: reserved offline research and model output directories; data and trained weights are excluded from Git.
- `docs/deployment/`: Cloudflare and persistent Python hosting instructions.

The UI uses a small hash-based navigation scheme to avoid extra routing dependencies. Always validate access in FastAPI regardless of client navigation.
