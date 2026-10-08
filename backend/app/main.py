"""FastAPI entry point for the RiceGrade research prototype."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="RiceGrade API", version="0.1.0")

# Development-only origin; deployment settings will need deliberate review.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Report API process availability, not the availability of ML artifacts."""
    return {"status": "ok", "service": "ricegrade-api"}
