# Architecture decisions

1. Backend: a single FastAPI deployment organized in layers (routes/schemas → application services → domain rules → OpenCV/ML/SQLite adapters). No queue, microservices or Clean Architecture scaffolding.
2. Frontend: React feature folders and plain hooks/state; no MVVM framework or global store until complexity warrants it.
3. Inference: synchronous initially, with timings (capture not included unless explicitly defined). Consider background processing only when actual timeouts/latency or concurrent workloads make synchronous requests unsuitable.
4. ML experiments and final evaluation are offline and separated from application code. Image crops from one lot may not cross train/validation/test partitions.
5. SQLite stores metadata and safe relative file references. Image bytes stay in private local storage, not publicly served static folders.
6. First implementation slice includes API connectivity only. It does not imply that models, data, authentication or scientifically validated thresholds already exist.
