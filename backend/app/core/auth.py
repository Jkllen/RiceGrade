"""SQLite-backed accounts and revocable bearer sessions for the RiceGrade prototype.

Passwords use PBKDF2-HMAC-SHA256; reset tokens and session tokens are stored only as
SHA-256 digests. RICEGRADE_DB_PATH must be on persistent storage in production.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import secrets
import sqlite3

from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(os.environ.get('RICEGRADE_DB_PATH', str(Path(__file__).resolve().parents[3] / 'ricegrade.sqlite3')))
ITERATIONS = 310_000


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize(db: sqlite3.Connection) -> None:
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY,
      email TEXT NOT NULL UNIQUE,
      password_salt TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
      token_hash TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      expires_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS password_resets (
      token_hash TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      expires_at TEXT NOT NULL,
      used_at TEXT
    );
    CREATE TABLE IF NOT EXISTS assessments (
      id INTEGER PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      lot_id TEXT NOT NULL,
      test_run_id TEXT NOT NULL,
      test_date TEXT NOT NULL,
      paddy_input_weight REAL NOT NULL,
      total_milled_rice_weight REAL NOT NULL,
      brown_rice_weight REAL,
      head_rice_weight REAL,
      moisture_content REAL,
      machine_notes TEXT NOT NULL DEFAULT '',
      total_milling_recovery REAL NOT NULL,
      brown_rice_recovery REAL,
      head_rice_recovery REAL,
      status TEXT NOT NULL DEFAULT 'awaiting_model',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(user_id, test_run_id)
    );
    CREATE TABLE IF NOT EXISTS assessment_images (
      assessment_id INTEGER PRIMARY KEY REFERENCES assessments(id) ON DELETE CASCADE,
      content BLOB NOT NULL,
      media_type TEXT NOT NULL,
      filename TEXT NOT NULL,
      size_bytes INTEGER NOT NULL,
      uploaded_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_assessment_user ON assessments(user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    ''')
    # Upgrade the original scaffold database without destroying existing accounts.
    columns = {row['name'] for row in db.execute('PRAGMA table_info(users)')}
    for name, definition in {
        'full_name': "TEXT NOT NULL DEFAULT ''",
        'role': "TEXT NOT NULL DEFAULT 'operator'",
        'updated_at': 'TEXT',
    }.items():
        if name not in columns:
            db.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
    db.commit()


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA busy_timeout = 15000')
    db.execute('PRAGMA journal_mode = WAL')
    initialize(db)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


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


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    db.execute('INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)',
               (hash_token(token), user_id, expires))
    return token


def user_dict(row: sqlite3.Row) -> dict:
    return {'id': row['id'], 'email': row['email'],
            'full_name': row['full_name'] or '', 'role': row['role'] or 'operator'}


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Bearer'})
    token = authorization.removeprefix('Bearer ').strip()
    with connection() as db:
        row = db.execute('''SELECT users.*, sessions.expires_at FROM sessions
            JOIN users ON users.id = sessions.user_id WHERE sessions.token_hash = ?''',
            (hash_token(token),)).fetchone()
    if row is None or datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc):
        raise HTTPException(401, 'Session expired or invalid', headers={'WWW-Authenticate': 'Bearer'})
    return user_dict(row)
