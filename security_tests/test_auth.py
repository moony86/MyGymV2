import hashlib
import os
from pathlib import Path
import tempfile
import time
import uuid
import pytest

private=Path(tempfile.mkdtemp(prefix='mygym-auth-test-'))
os.environ.update(MYGYM_AUTH_ENABLED='1',DB_PATH=str(private/'gym.sqlite3'),MYGYM_AUTH_DB=str(private/'auth.sqlite3'),MYGYM_BOOTSTRAP_FILE=str(private/'bootstrap.txt'),PYTEST_CURRENT_TEST='auth-audit')
from fastapi.testclient import TestClient
from src.apis.main import app
from src.security import auth_store as store
from src.apis.routers import auth
from src.infrastructure.db.connection import engine
from src.infrastructure.db.models import Base
Base.metadata.create_all(engine)
BASE='https://testserver'
PASSWORD='audit-secret-password-123'
owner=TestClient(app,base_url=BASE,raise_server_exceptions=False)
setup_key=store.BOOTSTRAP.read_text().strip()
setup_response=owner.post('/api/auth/setup',json={'username':'owner','password':PASSWORD,'setup_key':setup_key})
assert setup_response.status_code==200,setup_response.text
owner.headers['X-CSRF-Token']=owner.cookies.get('mygym_csrf')

@pytest.fixture(autouse=True)
def reset_attempts():
    auth._attempts.clear()

def member():
    username='user-'+uuid.uuid4().hex[:12]
    r=owner.post('/api/auth/accounts',json={'username':username,'password':PASSWORD,'name':'Test member'})
    assert r.status_code==200,r.text
    c=TestClient(app,base_url=BASE,raise_server_exceptions=False)
    r=c.post('/api/auth/login',json={'username':username,'password':PASSWORD})
    assert r.status_code==200,r.text
    c.headers['X-CSRF-Token']=c.cookies.get('mygym_csrf')
    return c,r.json()['profile_id'],username

def test_anonymous_cannot_read_data_or_profiles():
    c=TestClient(app,base_url=BASE)
    for path in ['/api/profiles','/api/profile','/api/workouts/history','/api/planner/plans','/api/auth/accounts']:
        assert c.get(path).status_code==401
    assert c.get('/',follow_redirects=False).status_code==303
    assert c.get('/login').status_code==200

def test_setup_is_one_time_and_key_removed():
    assert not store.BOOTSTRAP.exists()
    assert owner.post('/api/auth/setup',json={'username':'intruder','password':PASSWORD,'setup_key':setup_key}).status_code==400
    assert owner.get('/api/auth/status').json()['setup_required'] is False

def test_password_is_hashed_and_cookie_is_protected():
    row=store.account_for_username('owner')
    assert PASSWORD not in row['password_hash']
    assert store.verify(PASSWORD,row['password_hash'])
    cookies=setup_response.headers.get_list('set-cookie')
    session_cookie=next(c for c in cookies if c.startswith('mygym_session='))
    assert 'HttpOnly' in session_cookie and 'Secure' in session_cookie and 'SameSite=strict' in session_cookie

def test_profile_spoofing_rejected():
    c,profile,_=member()
    response=c.get('/api/workouts/history',headers={'X-Profile-Id':'00000000-0000-0000-0000-000000000001'})
    assert response.status_code==403
    assert [p['id'] for p in c.get('/api/profiles').json()]==[profile]

def test_authenticated_context_uses_cookie_identity():
    first,a,_=member();second,b,_=member()
    sid=first.post('/api/workouts/start',json={}).json()['id']
    assert first.get('/api/workouts/active').json()['session']['id']==sid
    assert second.get('/api/workouts/active').json()['session'] is None
    assert second.get('/api/workouts/'+sid).status_code==404

def test_csrf_and_cross_origin_rejected():
    c,_,_=member()
    assert c.post('/api/workouts/start',json={},headers={'X-CSRF-Token':''}).status_code==403
    assert c.post('/api/workouts/start',json={},headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post('/api/workouts/start',json={},headers={'Origin':BASE}).status_code==200

def test_normal_account_cannot_administer():
    c,_,_=member()
    assert c.get('/api/auth/accounts').status_code==403
    assert c.post('/api/profiles',json={'name':'Unauthorized'}).status_code==403
    assert c.get('/accounts').status_code==403
    assert c.get('/manage').status_code==403

def test_logout_revokes_session():
    c,_,_=member()
    old=c.cookies.get('mygym_session')
    assert c.post('/api/auth/logout').status_code==200
    assert store.session(old) is None
    assert c.get('/api/workouts/history').status_code==401

def test_password_reset_revokes_existing_sessions():
    c,profile,username=member()
    new='replacement-password-123'
    assert owner.post('/api/auth/accounts',json={'profile_id':profile,'username':username,'password':new}).status_code==200
    assert c.get('/api/auth/me').status_code==401
    assert c.post('/api/auth/login',json={'username':username,'password':PASSWORD}).status_code==401
    assert c.post('/api/auth/login',json={'username':username,'password':new}).status_code==200

def test_password_change_requires_old_password():
    c,_,username=member()
    assert c.post('/api/auth/password',json={'old_password':'incorrect','password':'changed-password-123'}).status_code==400
    assert c.post('/api/auth/password',json={'old_password':PASSWORD,'password':'changed-password-123'}).status_code==200
    assert c.get('/api/auth/me').status_code==200

def test_expired_session_rejected():
    c,_,_=member()
    digest=hashlib.sha256(c.cookies.get('mygym_session').encode()).hexdigest()
    with store.connect() as db: db.execute('UPDATE sessions SET expires=? WHERE token_hash=?',(time.time()-1,digest))
    assert c.get('/api/auth/me').status_code==401

def test_login_rate_limit():
    c=TestClient(app,base_url=BASE)
    for _ in range(8):
        assert c.post('/api/auth/login',json={'username':'missing','password':'incorrect'}).status_code==401
    assert c.post('/api/auth/login',json={'username':'missing','password':'incorrect'}).status_code==429

def test_plan_listing_and_mutations_are_per_authenticated_account():
    first,a,_=member();second,b,_=member()
    p1=first.post('/api/planner/plans',json={'name':'First private plan','exercises':[]})
    p2=second.post('/api/planner/plans',json={'name':'Second private plan','exercises':[]})
    assert p1.status_code==200,p1.text
    assert p2.status_code==200,p2.text
    id1=p1.json()['id'];id2=p2.json()['id']
    assert [p['id'] for p in first.get('/api/planner/plans').json()]==[id1]
    assert [p['id'] for p in second.get('/api/planner/plans').json()]==[id2]
    assert second.get('/api/planner/plans/'+id1).status_code==404
    assert second.put('/api/planner/plans/'+id1,json={'name':'Wrong owner','exercises':[]}).status_code==404
    assert second.put('/api/planner/plans/'+id1+'/toggle?enabled=false').status_code==404
    assert second.post('/api/planner/plans/'+id1+'/start').status_code in (400,404)
    assert second.post('/api/planner/plans/'+id1+'/schedule',json={'schedule_type':'manual'}).status_code in (400,404)
    assert second.delete('/api/planner/plans/'+id1).status_code==404
    response=first.get('/api/planner/plans/'+id1)
    assert response.status_code==200
    assert response.json()['name']=='First private plan'
    assert response.json()['enabled'] is True

def test_analytics_template_does_not_pin_default_profile():
    page=owner.get('/analytics')
    assert page.status_code==200
    assert "return { 'X-Profile-Id': PROFILE_ID };" not in page.text

def test_coaching_cookie_scope_csrf_and_admin_feedback():
    first,a,_=member();second,b,_=member()
    sid=first.post('/api/workouts/start',json={}).json()['id']
    assert first.post('/api/coaching/sessions/'+sid+'/begin',headers={'X-CSRF-Token':''}).status_code==403
    assert first.post('/api/coaching/sessions/'+sid+'/begin').status_code==200
    assert second.get('/api/coaching/sessions/'+sid).status_code==404
    assert second.post('/api/coaching/sessions/'+sid+'/begin').status_code==404
    assert first.get('/api/coaching/preferences',headers={'X-Profile-Id':b}).status_code==403
    assert second.get('/api/coaching/evaluation').status_code==403
    assert owner.get('/api/coaching/evaluation').status_code==200
    anonymous=TestClient(app,base_url=BASE)
    assert anonymous.get('/api/coaching/preferences').status_code==401
    assert anonymous.get('/coach',follow_redirects=False).status_code==303
