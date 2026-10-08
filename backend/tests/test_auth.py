import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core import auth


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, 'DB_PATH', tmp_path / 'test.sqlite3')
    return TestClient(app)


def test_dashboard_requires_authentication(client):
    assert client.get('/api/dashboard').status_code == 401
    assert client.get('/api/auth/me').status_code == 401


def test_signup_login_logout(client):
    data = {'email': 'Example@Ricegrade.test', 'password': 'secure-example-password'}
    created = client.post('/api/auth/sign-up', json=data)
    assert created.status_code == 201
    token = created.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    assert client.get('/api/dashboard', headers=headers).status_code == 200
    assert client.get('/api/auth/me', headers=headers).json()['email'] == 'example@ricegrade.test'
    assert client.post('/api/auth/sign-up', json=data).status_code == 409
    assert client.post('/api/auth/sign-in', json={**data, 'password': 'wrong-password!'}).status_code == 401
    logged_in = client.post('/api/auth/sign-in', json=data)
    assert logged_in.status_code == 200
    assert client.post('/api/auth/logout', headers=headers).status_code == 204
    assert client.get('/api/dashboard', headers=headers).status_code == 401
    assert client.get('/api/dashboard', headers={'Authorization': f"Bearer {logged_in.json()['access_token']}"}).status_code == 200


def test_password_reset_not_implemented(client):
    assert client.post('/api/auth/forgot-password', json={'email': 'a@b.com'}).status_code == 501
