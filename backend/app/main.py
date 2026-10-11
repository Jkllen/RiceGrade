"""FastAPI entry point for RiceGrade: accounts, draft assessments and recovery."""
import os
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.auth import current_user, connection
from app.api.routes.auth import router as auth_router
from app.api.routes.evaluations import router as evaluation_router

app = FastAPI(title='RiceGrade API', version='0.2.0')
allowed = [s.strip() for s in os.environ.get('RICEGRADE_CORS_ORIGINS',
    'http://localhost:5173,http://127.0.0.1:5173').split(',') if s.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed, allow_credentials=False,
                   allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
                   allow_headers=['Content-Type', 'Authorization'])
app.include_router(auth_router)
app.include_router(evaluation_router)


@app.get('/api/health')
def health() -> dict[str, str]:
    return {'status': 'ok', 'service': 'ricegrade-api'}


@app.get('/api/dashboard')
def dashboard(user: dict = Depends(current_user)) -> dict:
    with connection() as db:
        count = db.execute('SELECT COUNT(*) FROM assessments WHERE user_id=?', (user['id'],)).fetchone()[0]
        awaiting = db.execute("SELECT COUNT(*) FROM assessments WHERE user_id=? AND status='awaiting_model'",
                              (user['id'],)).fetchone()[0]
    return {'user': user, 'total_evaluations': count, 'awaiting_model': awaiting,
            'completed_reports': 0, 'model_status': 'not_connected'}
