from io import BytesIO
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core import auth


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, 'DB_PATH', tmp_path / 'assessment.sqlite3')
    return TestClient(app)


def signed_in(client, email='user@ricegrade.test'):
    response = client.post('/api/auth/sign-up', json={'email':email,'password':'secure-password-example',
       'full_name':'A Miller','role':'operator'})
    assert response.status_code == 201
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def payload(run='TEST-001'):
    return {'lot_id':'LOT-01','test_run_id':run,'test_date':'2026-10-12',
        'paddy_input_weight':1000,'total_milled_rice_weight':650,
        'brown_rice_weight':810, 'head_rice_weight':485,'moisture_content':13.7,
        'machine_notes':'Test record'}


def test_recovery_draft_lifecycle(client):
    h=signed_in(client)
    created=client.post('/api/evaluations',json=payload(),headers=h)
    assert created.status_code==201
    item=created.json();assert item['total_milling_recovery']==65
    assert item['brown_rice_recovery']==81 and item['head_rice_recovery']==48.5
    assert item['status']=='awaiting_model' and not item['has_image']
    assert client.get('/api/dashboard',headers=h).json()['awaiting_model']==1
    assert client.get('/api/evaluations',headers=h).json()[0]['id']==item['id']
    assert client.post('/api/evaluations',json=payload(),headers=h).status_code==409
    assert client.delete(f"/api/evaluations/{item['id']}",headers=h).status_code==204
    assert client.get(f"/api/evaluations/{item['id']}",headers=h).status_code==404


def test_optional_fields_and_validation(client):
    h=signed_in(client)
    data=payload();data.update(brown_rice_weight=None,head_rice_weight=None,moisture_content=None)
    row=client.post('/api/evaluations',json=data,headers=h)
    assert row.status_code==201
    assert row.json()['head_rice_recovery'] is None
    assert row.json()['brown_rice_recovery'] is None
    for key, bad in [('paddy_input_weight',0),('total_milled_rice_weight',1100),
                     ('brown_rice_weight',600),('head_rice_weight',700),('moisture_content',101)]:
        invalid=payload('DIFFERENT');invalid[key]=bad
        assert client.post('/api/evaluations',json=invalid,headers=h).status_code==422


def test_record_image_and_ownership(client):
    first=signed_in(client,'first@ricegrade.test')
    second=signed_in(client,'second@ricegrade.test')
    created=client.post('/api/evaluations',json=payload(),headers=first).json()
    ident=created['id']
    assert client.get(f'/api/evaluations/{ident}',headers=second).status_code==404
    assert client.get(f'/api/evaluations/{ident}/image',headers=second).status_code==404
    pic=Image.new('RGB',(140,140),'white');buffer=BytesIO();pic.save(buffer,format='PNG')
    uploaded=client.post(f'/api/evaluations/{ident}/image',headers=first,files={'image':('rice.png',buffer.getvalue(),'image/png')})
    assert uploaded.status_code==200 and uploaded.json()['has_image'] is True
    assert client.get(f'/api/evaluations/{ident}',headers=first).json()['has_image']
    assert client.get(f'/api/evaluations/{ident}/image',headers=first).headers['content-type']=='image/png'
    assert client.get(f'/api/evaluations/{ident}/image',headers=second).status_code==404
    invalid=client.post(f'/api/evaluations/{ident}/image',headers=first,files={'image':('bad.png',b'not-an-image','image/png')})
    assert invalid.status_code==422
