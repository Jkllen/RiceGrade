"""Prototype account endpoints; forgotten-password email delivery is not configured."""
import hashlib
import hmac
import secrets

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from app.core.auth import Credentials, connection, create_session, current_user, hashed_password, normalize_email

router = APIRouter(prefix='/api/auth', tags=['auth'])


@router.post('/sign-up', status_code=201)
def sign_up(payload: Credentials):
    email = normalize_email(payload.email)
    salt = secrets.token_bytes(16)
    with connection() as db:
        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            raise HTTPException(409, 'An account with this email exists')
        from datetime import datetime, timezone
        cur = db.execute('INSERT INTO users(email, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?)',
                         (email, salt.hex(), hashed_password(payload.password, salt), datetime.now(timezone.utc).isoformat()))
        db.commit()
        token = create_session(db, cur.lastrowid)
    return {'access_token': token, 'token_type': 'bearer', 'user': {'id': cur.lastrowid, 'email': email}}


@router.post('/sign-in')
def sign_in(payload: Credentials):
    email = normalize_email(payload.email)
    with connection() as db:
        row = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        # Constant-time comparison even for nonexistent accounts.
        salt = bytes.fromhex(row['password_salt']) if row else b'\x00' * 16
        match = hmac.compare_digest(hashed_password(payload.password, salt),
                                    row['password_hash'] if row else '0' * 64)
        if not row or not match:
            raise HTTPException(401, 'Invalid email or password')
        token = create_session(db, row['id'])
    return {'access_token': token, 'token_type': 'bearer', 'user': {'id': row['id'], 'email': email}}


@router.get('/me')
def me(user: dict = Depends(current_user)):
    return user


@router.post('/logout', status_code=204)
def logout(user: dict = Depends(current_user), authorization: str = Header()):
    token = authorization.removeprefix('Bearer ').strip()
    with connection() as db:
        db.execute('DELETE FROM sessions WHERE token_hash = ?', (hashlib.sha256(token.encode()).hexdigest(),))
        db.commit()


class ResetRequest(BaseModel):
    email: str


@router.post('/forgot-password', status_code=501)
def forgot_password(payload: ResetRequest):
    # Do not pretend an email was sent; no provider has been approved.
    raise HTTPException(501, 'Password reset is not configured for this prototype')
