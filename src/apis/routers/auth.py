import sqlite3
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
import uuid
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from src.security import auth_store as store
from src.infrastructure.db.connection import SessionLocal
from src.infrastructure.db.models import ProfileTable, DEFAULT_PROFILE_ID

router = APIRouter(tags=['accounts'])
_attempts = defaultdict(deque)
_lock = threading.Lock()
_dummy = store.password_hash('dummy-password-never-used')
ROOT = Path(__file__).resolve().parents[3]

class Login(BaseModel):
    username: str = Field(min_length=1,max_length=80)
    password: str = Field(min_length=1,max_length=128)
class Setup(Login):
    setup_key: str = Field(min_length=1,max_length=100)
class Account(Login):
    profile_id: str | None = None
    name: str | None = Field(default=None,min_length=1,max_length=80)
class ChangePassword(BaseModel):
    old_password: str = Field(min_length=1,max_length=128)
    password: str = Field(min_length=12,max_length=128)

def throttle(request):
    key = request.client.host if request.client else 'unknown'
    now = time.monotonic()
    with _lock:
        for ip in list(_attempts):
            if not _attempts[ip] or now-_attempts[ip][-1] > 300:
                del _attempts[ip]
        if key not in _attempts and len(_attempts)>=2048:
            raise HTTPException(429,'Too many login attempts; retry later')
        queue = _attempts[key]
        while queue and now-queue[0]>300:
            queue.popleft()
        if len(queue)>=8:
            raise HTTPException(429,'Too many login attempts; retry in five minutes',headers={'Retry-After':'300'})
        queue.append(now)

def require_account(request, admin=False):
    account = getattr(request.state,'auth',None)
    if not account:
        raise HTTPException(401,'Sign in required')
    if admin and not account['is_admin']:
        raise HTTPException(403,'Administrator access required')
    return account

def signed_in(response, profile_id):
    token, csrf = store.new_session(profile_id)
    response.set_cookie('mygym_session',token,max_age=store.TTL,httponly=True,secure=True,samesite='strict',path='/')
    response.set_cookie('mygym_csrf',csrf,max_age=store.TTL,httponly=False,secure=True,samesite='strict',path='/')
    response.headers['Cache-Control']='no-store'
    return {'profile_id':profile_id,'csrf':csrf}

@router.get('/login',include_in_schema=False)
def login_page():
    return FileResponse(ROOT/'templates/login.html',headers={'Cache-Control':'no-store'})

@router.get('/accounts',include_in_schema=False)
def account_page(request: Request):
    require_account(request,admin=True)
    return FileResponse(ROOT/'templates/accounts.html',headers={'Cache-Control':'no-store'})

@router.get('/api/auth/status')
def auth_status():
    return {'setup_required':not store.has_accounts()}

@router.post('/api/auth/setup')
def setup(payload: Setup,request: Request,response: Response):
    throttle(request)
    # The key is generated on the server and never returned over HTTP.
    try:
        with SessionLocal() as db:
            if not db.get(ProfileTable,DEFAULT_PROFILE_ID):
                db.add(ProfileTable(id=DEFAULT_PROFILE_ID,name='Owner'))
                db.commit()
        store.save_account(DEFAULT_PROFILE_ID,payload.username,payload.password,bootstrap=payload.setup_key)
    except (ValueError,sqlite3.IntegrityError) as exc:
        raise HTTPException(400,str(exc))
    return signed_in(response,DEFAULT_PROFILE_ID)

@router.post('/api/auth/login')
def login(payload: Login,request: Request,response: Response):
    throttle(request)
    row = store.account_for_username(payload.username)
    valid = store.verify(payload.password,row['password_hash'] if row else _dummy)
    if not row or not valid:
        raise HTTPException(401,'Incorrect username or password')
    return signed_in(response,row['profile_id'])

@router.get('/api/auth/me')
def me(request: Request):
    account = require_account(request)
    return {key:account[key] for key in ['profile_id','username','is_admin']}

@router.post('/api/auth/logout')
def logout(request: Request,response: Response):
    store.revoke(request.cookies.get('mygym_session'))
    response.delete_cookie('mygym_session',path='/',secure=True,samesite='strict')
    response.delete_cookie('mygym_csrf',path='/',secure=True,samesite='strict')
    return {'ok':True}

@router.get('/api/auth/accounts')
def accounts(request: Request):
    require_account(request,admin=True)
    with store.connect() as auth:
        credentials={row['profile_id']:dict(row) for row in auth.execute('SELECT profile_id,username,is_admin FROM accounts')}
    with SessionLocal() as db:
        return [{'profile_id':p.id,'name':p.name,'username':credentials.get(p.id,{}).get('username'),'is_admin':bool(credentials.get(p.id,{}).get('is_admin'))} for p in db.query(ProfileTable).order_by(ProfileTable.created_at).all()]

@router.post('/api/auth/accounts')
def save_account(payload: Account,request: Request):
    current = require_account(request,admin=True)
    if len(payload.password)<12:
        raise HTTPException(422,'Password must contain at least 12 characters')
    with SessionLocal() as db:
        if payload.profile_id:
            profile=db.get(ProfileTable,payload.profile_id)
            if profile is None:
                raise HTTPException(404,'Profile not found')
        else:
            name=(payload.name or '').strip()
            if not name:
                raise HTTPException(422,'Name is required for a new account')
            profile=ProfileTable(id=str(uuid.uuid4()),name=name)
            db.add(profile)
            db.flush()
        try:
            store.save_account(profile.id,payload.username,payload.password)
            db.commit()
        except (ValueError,sqlite3.IntegrityError) as exc:
            db.rollback()
            raise HTTPException(400,'Username is unavailable or account details are invalid')
        return {'profile_id':profile.id,'reauthenticate':profile.id==current['profile_id']}

@router.post('/api/auth/password')
def change_password(payload: ChangePassword,request: Request,response: Response):
    account=require_account(request)
    throttle(request)
    row=store.account_for_username(account['username'])
    if not store.verify(payload.old_password,row['password_hash']):
        raise HTTPException(400,'Current password is incorrect')
    store.save_account(account['profile_id'],account['username'],payload.password)
    return signed_in(response,account['profile_id'])

@router.get('/account',include_in_schema=False)
def own_account_page(request: Request):
    require_account(request)
    return FileResponse(ROOT/'templates/account.html',headers={'Cache-Control':'no-store'})
