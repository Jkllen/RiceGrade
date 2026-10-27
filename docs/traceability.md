# RiceGrade implementation traceability

This milestone is UI/account/recovery first. Completed software features are distinguished from unconnected ML research components.

| Requirement | Code location | Verification | Current status |
|---|---|---|---|
| Responsive React + TypeScript UI | `frontend/src/` | TypeScript source check; production npm build to verify in networked environment | Built source; runtime build not verified here |
| Sign up / sign in / sign out | `backend/app/api/routes/auth.py` | `test_auth.py` | Backend complete for prototype |
| Authenticated profile, role label and password change | `backend/app/api/routes/auth.py` | `test_auth.py` | Backend and UI complete |
| Forgot/reset password | `backend/app/api/routes/auth.py` | Token, one-use, expiry patterns and mocked SMTP tests | Works once SMTP is configured |
| SQLite persistence and assessment ownership | `backend/app/core/auth.py`; `backend/app/api/routes/evaluations.py` | `test_evaluations.py` | Backend complete for prototype |
| Original paddy and milled-rice weights | `frontend/src/features/analysis/`; evaluations API | Invalid mass and missing optional field tests | Implemented |
| Calculated total / optional brown / head recovery | evaluations API | Known-value tests | Implemented |
| Sample image upload / private retrieval | evaluations API, history UI | Image format, size and ownership tests | Implemented |
| Evaluation history and details | history UI, evaluations API | Backend retrieval/ownership tests | Implemented |
| Report queue/preview | reports UI | Source type-check; manual responsive review pending | UI ready, final ML report unavailable |
| Cloudflare Pages same-origin API proxy | `frontend/functions/api/[[path]].ts`, `frontend/wrangler.toml` | Requires actual deployment with configured backend origin | Prepared, not deployed |
| Grain isolation (OpenCV) | `backend/app/vision/` (future) | Local annotated data, per-instance metrics | Not implemented |
| EfficientNet-B0 feature extraction | `backend/app/ml/` (future) | Verify final training checkpoint/config | Pending model integration |
| Feature fusion / XGBoost final classification | `backend/app/ml/` (future) | Independent held-out comparisons and macro-F1 | Pending |
| Visual counts and proportions | assessment inference service (future) | Ground-truth sample comparisons | Pending |
| DSS reference rules and recommendations (R1–R11) | `frontend/src/lib/dss.ts`, `frontend/src/components/ui/AssessmentInsights.tsx`, `docs/decision-support/knowledge-base.md` | `npm run test:dss` boundary tests; expert review pending | Implemented (client-side, deterministic) |
| Final evaluation report with DSS | report service (future) | Data and threshold traceability tests | Pending |

**Scientific boundary:** never equate image-derived grain-count percentages with PNS/BAFS mass-based quality thresholds; never derive actual recovery from those image counts.
