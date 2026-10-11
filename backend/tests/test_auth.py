import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core import auth
from app.api.routes import auth as auth_routes


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, 'DB_PATH', tmp_path / 'test.sqlite3')
    monkeypatch.delenv('SMTP_HOST', raising=False)
    monkeypatch.delenv('SMTP_FROM', raising=False)
    return TestClient(app)


def sign_up(client, email='Example@Ricegrade.test', password='secure-example-password'):
    return client.post('/api/auth/sign-up', json={'email': email, 'password': password,
                  'full_name': 'Test Operator', 'role': 'operator'})


def headers(reply):
    return {'Authorization': f"Bearer {reply.json()['access_token']}"}


def test_dashboard_requires_authentication(client):
    assert client.get('/api/dashboard').status_code == 401
    assert client.get('/api/auth/me').status_code == 401
    assert client.get('/api/evaluations').status_code == 401


def test_signup_login_logout(client):
    created = sign_up(client)
    assert created.status_code == 201
    token_header = headers(created)
    assert client.get('/api/dashboard', headers=token_header).status_code == 200
    me = client.get('/api/auth/me', headers=token_header).json()
    assert me['email'] == 'example@ricegrade.test'
    assert me['full_name'] == 'Test Operator'
    assert sign_up(client).status_code == 409
    assert client.post('/api/auth/sign-in', json={'email':'example@ricegrade.test','password':'wrong-password!'}).status_code == 401
    logged_in = client.post('/api/auth/sign-in', json={'email':'example@ricegrade.test','password':'secure-example-password'})
    assert logged_in.status_code == 200
    assert client.post('/api/auth/logout', headers=token_header).status_code == 204
    assert client.get('/api/dashboard', headers=token_header).status_code == 401
    assert client.get('/api/dashboard', headers=headers(logged_in)).status_code == 200


def test_password_reset_without_smtp_not_falsely_confirmed(client):
    response = client.post('/api/auth/forgot-password', json={'email':'a@b.com'})
    assert response.status_code == 503
    assert 'not configured' in response.json()['detail']


def test_password_reset_with_smtp_and_one_time_token(client, monkeypatch):
    created = sign_up(client)
    messages = []
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    monkeypatch.setenv('SMTP_FROM', 'no-reply@example.test')
    monkeypatch.setenv('RICEGRADE_PUBLIC_URL', 'https://ricegrade.example.test')
    monkeypatch.setattr(auth_routes, 'send_reset_email', lambda recipient, link: messages.append((recipient, link)))
    unknown = client.post('/api/auth/forgot-password', json={'email':'none@example.test'})
    assert unknown.status_code == 200 and messages == []
    requested = client.post('/api/auth/forgot-password', json={'email':'example@ricegrade.test'})
    assert requested.status_code == 200 and len(messages) == 1
    token = messages[0][1].split('reset_token=')[1]
    bad = client.post('/api/auth/reset-password', json={'token':'x'*35, 'new_password':'next-password-secure'})
    assert bad.status_code == 400
    changed = client.post('/api/auth/reset-password', json={'token':token,'new_password':'next-password-secure'})
    assert changed.status_code == 200
    assert client.get('/api/auth/me', headers=headers(created)).status_code == 401
    assert client.post('/api/auth/reset-password', json={'token':token,'new_password':'any-other-long-pass'}).status_code == 400
    assert client.post('/api/auth/sign-in', json={'email':'example@ricegrade.test','password':'secure-example-password'}).status_code == 401
    assert client.post('/api/auth/sign-in', json={'email':'example@ricegrade.test','password':'next-password-secure'}).status_code == 200


def test_profile_and_change_password_revoke_other_sessions(client):
    created = sign_up(client)
    second = client.post('/api/auth/sign-in', json={'email':'example@ricegrade.test','password':'secure-example-password'})
    update = client.patch('/api/auth/profile', headers=headers(created), json={'full_name':'Updated Operator', 'role':'qa'})
    assert update.status_code == 200 and update.json()['role'] == 'qa'
    assert client.patch('/api/auth/profile', headers=headers(created), json={'full_name':'Updated', 'role':'admin'}).status_code == 422
    fail = client.post('/api/auth/change-password', headers=headers(created),
             json={'current_password':'wrong','new_password':'new-password-example'})
    assert fail.status_code == 400
    success = client.post('/api/auth/change-password', headers=headers(created),
                json={'current_password':'secure-example-password','new_password':'new-password-example'})
    assert success.status_code == 200
    assert client.get('/api/auth/me', headers=headers(created)).status_code == 200
    assert client.get('/api/auth/me', headers=headers(second)).status_code == 401


def test_legacy_user_schema_is_migrated_without_data_loss(client):
    from app.core import auth
    import sqlite3
    import secrets
    salt=secrets.token_bytes(16)
    with sqlite3.connect(auth.DB_PATH) as db:
        db.execute('''CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
                     password_salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)''')
        db.execute('INSERT INTO users(email,password_salt,password_hash,created_at) VALUES(?,?,?,?)',
            ('legacy@ricegrade.test',salt.hex(),auth.hashed_password('legacy-password-123',salt),auth.now()))
    login = client.post('/api/auth/sign-in',json={'email':'legacy@ricegrade.test','password':'legacy-password-123'})
    assert login.status_code == 200
    assert login.json()['user']['role'] == 'operator'
    assert client.patch('/api/auth/profile',headers=headers(login),
        json={'full_name':'Legacy Migrated','role':'qa'}).status_code == 200
