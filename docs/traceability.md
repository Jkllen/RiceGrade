# Methodology traceability (provisional)

Source: revised RiceGrade Chapter 3 supplied by the team. No scientific thresholds or dataset facts are assumed.

| Requirement | Planned component | Verification | Status |
|---|---|---|---|
| React + TypeScript / Vite / Tailwind | frontend/ | Type check + build | Scaffolded |
| FastAPI / Uvicorn | backend/app/main.py | GET /api/health test | Implemented |
| SQLite accounts, lots, samples, measurements, reports | backend/app/persistence/ (future) | DB round-trip and access tests | Pending |
| Instance segmentation | backend/app/vision/ (future) | IoU/mAP evaluation, degraded capture tests | Pending model choice |
| OpenCV descriptors | backend/app/vision/ (future) | Deterministic synthetic-image tests | Pending |
| EfficientNet-B0 + XGBoost quality classifier | backend/app/ml/ (future) | adapter contract + lot-held-out metrics | Pending artifacts |
| Physical weights → calculated recovery | backend/app/domain/recovery.py (future) | known-value, zero/negative and unit tests | Pending measurement contract |
| DSS rules with traceable evidence | backend/app/domain/rules.py (future) | threshold boundary + uncertainty cases | Pending validated thresholds |
| Saved reports and history | backend/app/repositories/ (future) | retrieval and permissions tests | Pending |
| 50-person ISO/IEC 25010 evaluation | docs/evaluation/ (future) | questionnaire/scoring evidence | Pending |

**Scientific gates:** confirm unit and numerator/denominator measurement definitions; classification labels and dataset rights; segmentation model; image acquisition/quality checks; source-backed thresholds and operator validation; confidence policy. A non-ML fallback must never be labeled a predicted result.

## Approved authentication/navigation flow (October scaffold revision)

| Requirement | Component | Verification |
|---|---|---|
| Sign in / sign up | `frontend/src/features/auth/pages/AuthPage.tsx`; `backend/app/api/routes/auth.py` | `backend/tests/test_auth.py` |
| Verify session before dashboard | `frontend/src/App.tsx`; `/api/auth/me` | `test_dashboard_requires_authentication`, `test_signup_login_logout` |
| Reject unauthorized protected API requests | `backend/app/core/auth.py` dependency; `/api/dashboard` | `test_dashboard_requires_authentication` |
| Dashboard links: analysis, reports, history, profile | `frontend/src/components/layout/AppShell.tsx`, DashboardPage | Frontend navigation manual review; automated UI test pending |
| Log out revokes session | `/api/auth/logout` and `App.tsx` | `test_signup_login_logout` |
| Forgot password email validation and reset flow | UI scaffold, API deliberately unavailable | `test_password_reset_not_implemented`; full email/reset tests pending |
