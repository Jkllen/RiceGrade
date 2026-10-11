"""Authenticated test-run drafts, deterministic recovery and image attachments.

No model predictions or finished reports are fabricated by these endpoints.
"""
from datetime import date
import io
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, model_validator

from app.core.auth import connection, current_user, now

router = APIRouter(prefix='/api/evaluations', tags=['evaluations'])
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class EvaluationInput(BaseModel):
    lot_id: str = Field(min_length=1, max_length=80)
    test_run_id: str = Field(min_length=1, max_length=80)
    test_date: date
    paddy_input_weight: float = Field(gt=0)
    total_milled_rice_weight: float = Field(gt=0)
    brown_rice_weight: float | None = Field(default=None, gt=0)
    head_rice_weight: float | None = Field(default=None, gt=0)
    moisture_content: float | None = Field(default=None, gt=0, le=100)
    machine_notes: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def check_weights(self):
        if self.total_milled_rice_weight > self.paddy_input_weight:
            raise ValueError('Total milled-rice weight cannot exceed the original paddy input')
        if self.brown_rice_weight is not None:
            if self.brown_rice_weight > self.paddy_input_weight:
                raise ValueError('Brown-rice weight cannot exceed the original paddy input')
            if self.brown_rice_weight < self.total_milled_rice_weight:
                raise ValueError('Brown-rice weight cannot be smaller than the total milled-rice weight')
        if self.head_rice_weight is not None and self.head_rice_weight > self.total_milled_rice_weight:
            raise ValueError('Head-rice weight cannot exceed total milled-rice weight')
        return self


def serialize(row: sqlite3.Row, has_image=False) -> dict:
    data = dict(row)
    data['has_image'] = bool(has_image)
    return data


def owned(db, assessment_id: int, user_id: int):
    row = db.execute('SELECT * FROM assessments WHERE id=? AND user_id=?', (assessment_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Assessment not found')
    return row


def has_image(db, assessment_id: int) -> bool:
    return bool(db.execute('SELECT 1 FROM assessment_images WHERE assessment_id=?', (assessment_id,)).fetchone())


@router.get('')
def list_evaluations(user: dict = Depends(current_user)):
    with connection() as db:
        rows = db.execute('SELECT * FROM assessments WHERE user_id=? ORDER BY created_at DESC, id DESC',
                          (user['id'],)).fetchall()
        images = {r['assessment_id'] for r in db.execute('''SELECT images.assessment_id FROM assessment_images images
            JOIN assessments a ON a.id=images.assessment_id WHERE a.user_id=?''', (user['id'],))}
    return [serialize(row, row['id'] in images) for row in rows]


@router.post('', status_code=201)
def create_evaluation(payload: EvaluationInput, user: dict = Depends(current_user)):
    values = payload.model_dump(mode='json')
    values['lot_id'] = values['lot_id'].strip()
    values['test_run_id'] = values['test_run_id'].strip()
    if not values['lot_id'] or not values['test_run_id']:
        raise HTTPException(422, 'Lot ID and test-run ID are required')
    values.update({
        'user_id': user['id'],
        'total_milling_recovery': 100 * payload.total_milled_rice_weight / payload.paddy_input_weight,
        'brown_rice_recovery': 100 * payload.brown_rice_weight / payload.paddy_input_weight if payload.brown_rice_weight is not None else None,
        'head_rice_recovery': 100 * payload.head_rice_weight / payload.paddy_input_weight if payload.head_rice_weight is not None else None,
        'created_at': now(), 'updated_at': now(), 'status': 'awaiting_model',
    })
    columns = ','.join(values)
    placeholders = ','.join('?' for _ in values)
    with connection() as db:
        try:
            cur = db.execute(f'INSERT INTO assessments ({columns}) VALUES ({placeholders})', tuple(values.values()))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, 'This test-run ID already exists in your account') from exc
        row = owned(db, cur.lastrowid, user['id'])
    return serialize(row)


@router.get('/{assessment_id}')
def get_evaluation(assessment_id: int, user: dict = Depends(current_user)):
    with connection() as db:
        row = owned(db, assessment_id, user['id'])
        return serialize(row, has_image(db, assessment_id))


@router.delete('/{assessment_id}', status_code=204)
def delete_evaluation(assessment_id: int, user: dict = Depends(current_user)):
    with connection() as db:
        owned(db, assessment_id, user['id'])
        db.execute('DELETE FROM assessments WHERE id=? AND user_id=?', (assessment_id, user['id']))


@router.post('/{assessment_id}/image')
async def upload_image(assessment_id: int, image: UploadFile = File(...), user: dict = Depends(current_user)):
    # The current research prototype stores a small image inside SQLite so deployments
    # can use the same persistent volume as their accounts, without ephemeral files.
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, 'Image must be smaller than 5 MB')
    try:
        picture = Image.open(io.BytesIO(data))
        picture.verify()
        picture = Image.open(io.BytesIO(data))
        if picture.format not in {'JPEG', 'PNG', 'WEBP'} or picture.width < 100 or picture.height < 100:
            raise ValueError('Unsupported format or too-small image')
        if picture.width * picture.height > 20_000_000:
            raise ValueError('Image resolution is too large')
        media_type = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}[picture.format]
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(422, 'Upload a valid JPEG, PNG or WebP image of at least 100×100 pixels') from exc
    with connection() as db:
        owned(db, assessment_id, user['id'])
        db.execute('''INSERT INTO assessment_images(assessment_id, content, media_type, filename, size_bytes, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(assessment_id) DO UPDATE SET
            content=excluded.content,media_type=excluded.media_type,filename=excluded.filename,
            size_bytes=excluded.size_bytes,uploaded_at=excluded.uploaded_at''',
            (assessment_id, data, media_type, (image.filename or 'sample')[:160], len(data), now()))
        db.execute('UPDATE assessments SET updated_at=? WHERE id=?', (now(), assessment_id))
    return {'has_image': True, 'size_bytes': len(data), 'message': 'Image saved. ML screening is not connected yet.'}


@router.get('/{assessment_id}/image')
def get_image(assessment_id: int, user: dict = Depends(current_user)):
    with connection() as db:
        owned(db, assessment_id, user['id'])
        row = db.execute('SELECT content, media_type FROM assessment_images WHERE assessment_id=?',
                         (assessment_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'No image attached')
    return Response(bytes(row['content']), media_type=row['media_type'],
                    headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
