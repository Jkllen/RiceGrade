"""Minimal local prototype authentication; no email or external providers."""
import hashlib
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(os.environ.get('RICEGRADE_DB_PATH', str(Path(__file__).resolve().parents[3] / 'ricegrade.sqlite3')))
ITERATIONS = 310_000


def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_salt TEXT NOT NULL,
      password_hash TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
      token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      expires_at TEXT NOT NULL
    );
    ''')
    return db


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(422, 'Enter a valid email address')
    return email


def hashed_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS).hex()


def create_session(db: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    db.execute('INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)',
               (hashlib.sha256(token.encode()).hexdigest(), user_id, expires))
    db.commit()
    return token


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Bearer'})
    token = authorization.removeprefix('Bearer ').strip()
    with connection() as db:
        row = db.execute('''SELECT users.id, users.email, sessions.expires_at FROM sessions
            JOIN users ON users.id = sessions.user_id WHERE sessions.token_hash = ?''',
            (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if row is None or datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc):
        raise HTTPException(401, 'Session expired or invalid', headers={'WWW-Authenticate': 'Bearer'})
    return {'id': row['id'], 'email': row['email']}
