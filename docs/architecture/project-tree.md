# Planned project boundaries (scaffold)

- `frontend/src/components/layout/`: shared navigation and layout.
- `frontend/src/components/ui/`: reusable visual components, including clearly labelled empty states.
- `frontend/src/features/{dashboard,lots,samples,measurements,analysis,reports,history,auth}/`: feature pages; **no workflow logic implemented**.
- `frontend/src/lib/`, `types/`: reserved for API client and shared frontend types.
- `backend/app/api/routes/`, `schemas/`: HTTP routes and input/output validation.
- `backend/app/services/`: workflow orchestration.
- `backend/app/domain/`: deterministic calculations and validated decision rules.
- `backend/app/vision/`: image checks, segmentation adapter, engineered feature extraction.
- `backend/app/ml/`: versioned EfficientNet-B0 and XGBoost inference adapters.
- `backend/app/db/`, `repositories/`: SQLite configuration and persistence boundaries.
- `backend/app/core/`: application configuration.
- `backend/tests/{unit,integration}/`: isolated tests and end-to-end boundary tests.
- `experiments/{datasets,segmentation,features,classification,evaluation,splits}/`: offline reproducible research workflow.
- `data/{raw,annotations,measurements,processed}/`: **local research data, not in Git**.
- `artifacts/{segmentation,efficientnet,xgboost,manifests}/`: **local model files, not in Git by default**.
- `docs/{api,research,architecture}/`: contracts, provenance documentation and design decisions.

No instance-segmentation model, thresholds, quality labels beyond the draft four classes, authentication scheme, or dataset are assumed to be available. Navigation is local component state (no router dependency); routes can be introduced when deep links are required.
