"""Account registration, sessions, profile, password changes and token-based reset."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hmac
import logging
import os
import secrets
import smtplib

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import (
    Credentials, connection, create_session, current_user, hash_token,
    hashed_password, normalize_email, now, user_dict,
)

router = APIRouter(prefix='/api/auth', tags=['auth'])
logger = logging.getLogger(__name__)


class SignUp(Credentials):
    full_name: str = Field(default='', max_length=120)
    role: str = 'operator'


class SignIn(BaseModel):
    email: str
    password: str


class ForgotPassword(BaseModel):
    email: str


class ResetPassword(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class UpdateProfile(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    role: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=256)


def check_role(role: str) -> str:
    if role not in {'operator', 'qa'}:
        raise HTTPException(422, 'Select Milling Operator or QA/QC Personnel')
    return role


def verify_password(password: str, row) -> bool:
    salt = bytes.fromhex(row['password_salt']) if row else b'\x00' * 16
    expected = row['password_hash'] if row else '0' * 64
    return hmac.compare_digest(hashed_password(password, salt), expected)


def send_reset_email(recipient: str, link: str) -> None:
    """Configure SMTP_* variables; no silent success when sending is unavailable."""
    host = os.environ.get('SMTP_HOST')
    sender = os.environ.get('SMTP_FROM')
    if not host or not sender:
        raise RuntimeError('Password-reset email delivery is not configured')
    message = EmailMessage()
    message['Subject'] = 'RiceGrade password reset'
    message['From'] = sender
    message['To'] = recipient
    message.set_content('A password reset was requested for your RiceGrade account.\n\n'
                        f'Open this link within 30 minutes:\n{link}\n\n'
                        'If you did not request this, you can ignore this message.')
    with smtplib.SMTP(host, int(os.environ.get('SMTP_PORT', '587')), timeout=15) as smtp:
        if os.environ.get('SMTP_STARTTLS', 'true').lower() == 'true':
            smtp.starttls()
        if os.environ.get('SMTP_USERNAME'):
            smtp.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
        smtp.send_message(message)


@router.post('/sign-up', status_code=201)
def sign_up(payload: SignUp):
    email = normalize_email(payload.email)
    name = payload.full_name.strip() or email.split('@')[0]
    if len(name) < 2:
        raise HTTPException(422, 'Enter your full name')
    role = check_role(payload.role)
    salt = secrets.token_bytes(16)
    with connection() as db:
        if db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
            raise HTTPException(409, 'An account with this email already exists')
        cur = db.execute('''INSERT INTO users(email, password_salt, password_hash, created_at,
                full_name, role, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (email, salt.hex(), hashed_password(payload.password, salt), now(), name, role, now()))
        user_id = cur.lastrowid
        token = create_session(db, user_id)
        row = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    return {'access_token': token, 'token_type': 'bearer', 'user': user_dict(row)}


@router.post('/sign-in')
def sign_in(payload: SignIn):
    email = normalize_email(payload.email)
    with connection() as db:
        row = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if not verify_password(payload.password, row) or row is None:
            raise HTTPException(401, 'Invalid email or password')
        token = create_session(db, row['id'])
        user = user_dict(row)
    return {'access_token': token, 'token_type': 'bearer', 'user': user}


@router.get('/me')
def me(user: dict = Depends(current_user)):
    return user


@router.post('/logout', status_code=204)
def logout(user: dict = Depends(current_user), authorization: str = Header()):
    token = authorization.removeprefix('Bearer ').strip()
    with connection() as db:
        db.execute('DELETE FROM sessions WHERE token_hash = ?', (hash_token(token),))


@router.patch('/profile')
def update_profile(payload: UpdateProfile, user: dict = Depends(current_user)):
    name = payload.full_name.strip()
    if len(name) < 2:
        raise HTTPException(422, 'Full name must contain at least 2 characters')
    role = check_role(payload.role)
    with connection() as db:
        db.execute('UPDATE users SET full_name = ?, role = ?, updated_at = ? WHERE id = ?',
                   (name, role, now(), user['id']))
        row = db.execute('SELECT * FROM users WHERE id = ?', (user['id'],)).fetchone()
    return user_dict(row)


@router.post('/change-password')
def change_password(payload: ChangePassword, user: dict = Depends(current_user), authorization: str = Header()):
    with connection() as db:
        row = db.execute('SELECT * FROM users WHERE id = ?', (user['id'],)).fetchone()
        if not verify_password(payload.current_password, row):
            raise HTTPException(400, 'Current password is incorrect')
        if payload.current_password == payload.new_password:
            raise HTTPException(422, 'Choose a different new password')
        salt = secrets.token_bytes(16)
        db.execute('UPDATE users SET password_salt=?, password_hash=?, updated_at=? WHERE id=?',
                   (salt.hex(), hashed_password(payload.new_password, salt), now(), user['id']))
        # Protect other signed-in devices; keep the current session only.
        db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash != ?',
                   (user['id'], hash_token(authorization.removeprefix('Bearer ').strip())))
    return {'message': 'Password updated. Other sessions have been signed out.'}


@router.post('/forgot-password')
def forgot_password(payload: ForgotPassword):
    email = normalize_email(payload.email)
    if not (os.environ.get('SMTP_HOST') and os.environ.get('SMTP_FROM')):
        raise HTTPException(503, 'Password reset email is not configured. Contact your system administrator.')
    with connection() as db:
        row = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if row:
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM password_resets WHERE user_id = ?', (row['id'],))
            db.execute('INSERT INTO password_resets(token_hash, user_id, expires_at) VALUES (?, ?, ?)',
                       (hash_token(token), row['id'], (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()))
            base = os.environ.get('RICEGRADE_PUBLIC_URL', 'http://localhost:5173').rstrip('/')
            link = f'{base}/?reset_token={token}'
            try:
                send_reset_email(email, link)
            except Exception as exc:
                logger.exception('Reset email delivery failed')
                raise HTTPException(503, 'Unable to send reset email. Please try again later.') from exc
    # Uniform response: do not reveal whether this email has an account.
    return {'message': 'If an account exists, a password-reset link will be sent to that address.'}


@router.post('/reset-password')
def reset_password(payload: ResetPassword):
    with connection() as db:
        row = db.execute('SELECT * FROM password_resets WHERE token_hash = ?',
                         (hash_token(payload.token),)).fetchone()
        if not row or row['used_at'] or datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc):
            raise HTTPException(400, 'This password-reset link is invalid or expired')
        salt = secrets.token_bytes(16)
        db.execute('UPDATE users SET password_salt=?, password_hash=?, updated_at=? WHERE id=?',
                   (salt.hex(), hashed_password(payload.new_password, salt), now(), row['user_id']))
        db.execute('UPDATE password_resets SET used_at=? WHERE token_hash=?', (now(), row['token_hash']))
        db.execute('DELETE FROM sessions WHERE user_id=?', (row['user_id'],))
    return {'message': 'Password reset successful. Sign in with your new password.'}
