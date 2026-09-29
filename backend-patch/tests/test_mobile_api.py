from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)


def mobile_headers():
    r=client.post('/api/mobile/login',json={'username':'admin','password':''})
    assert r.status_code==200
    token=r.json()['token']
    return {'Authorization':f'Bearer {token}'}


def test_mobile_login_and_bootstrap():
    headers=mobile_headers()
    r=client.get('/api/mobile/bootstrap',headers=headers)
    assert r.status_code==200
    data=r.json()
    assert 'alerts' in data and 'candidates' in data and 'positions' in data
    assert data['poll_seconds'] >= 60


def test_mobile_copilot_diagnose():
    headers=mobile_headers()
    r=client.post('/api/mobile/copilot',headers=headers,json={'mode':'DIAGNOSE','message':'Why is the scanner stale?'})
    assert r.status_code==200
    data=r.json()
    assert data['mode']=='DIAGNOSE'
    assert 'diagnostics' in data
    assert 'Database:' in data['reply']


def test_mobile_configure_requires_proposal_then_apply():
    headers=mobile_headers()
    r=client.post('/api/mobile/copilot',headers=headers,json={'mode':'CONFIGURE','message':'Change risk profile to HIGH'})
    assert r.status_code==200
    proposal=r.json()['proposal']
    assert proposal['action']=='SET_RISK_PROFILE'
    assert proposal['value']=='HIGH'
    a=client.post('/api/mobile/copilot/apply',headers=headers,json=proposal)
    assert a.status_code==200
    b=client.get('/api/mobile/bootstrap',headers=headers)
    assert b.json()['risk_profile']=='HIGH'


def test_mobile_fix_never_auto_applies_code_change():
    headers=mobile_headers()
    r=client.post('/api/mobile/copilot',headers=headers,json={'mode':'FIX','message':'Rewrite the buy scoring source code'})
    assert r.status_code==200
    data=r.json()
    assert data['proposal'] is None
    assert data['requires_engineering_connector'] is True


def test_mobile_fix_scan_is_approval_gated():
    headers=mobile_headers()
    r=client.post('/api/mobile/copilot',headers=headers,json={'mode':'FIX','message':'Scanner is not updating'})
    assert r.status_code==200
    assert r.json()['proposal']['action']=='RUN_SCAN_NOW'
