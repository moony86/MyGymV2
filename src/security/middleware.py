import hmac
from urllib.parse import urlsplit
from starlette.responses import JSONResponse, RedirectResponse
from src.security import auth_store as store
from src.security.session_cookies import set_session_cookies
import time

PUBLIC = {'/login','/api/auth/status','/api/auth/login','/api/auth/setup'}
SAFE = {'GET','HEAD','OPTIONS'}

def install(app):
    @app.middleware('http')
    async def authenticate(request, call_next):
        if not store.ENABLED:
            return await call_next(request)
        path=request.url.path
        if path.startswith('/static/'):
            return await call_next(request)
        if request.method not in SAFE:
            origin=request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Cross-origin request rejected'},status_code=403)
        if path in PUBLIC:
            response=await call_next(request)
            response.headers['Cache-Control']='no-store'
            return response
        account=store.session(request.cookies.get('mygym_session'))
        if not account:
            if path.startswith('/api/'):
                return JSONResponse({'detail':'Sign in required'},status_code=401,headers={'Cache-Control':'no-store'})
            return RedirectResponse('/login',status_code=303,headers={'Cache-Control':'no-store'})
        supplied=request.headers.get('X-Profile-Id')
        if supplied and supplied != account['profile_id']:
            return JSONResponse({'detail':'Profile does not belong to this session'},status_code=403)
        if request.method not in SAFE:
            csrf=request.headers.get('X-CSRF-Token','')
            if not hmac.compare_digest(csrf,account['csrf']):
                return JSONResponse({'detail':'Invalid request verification token'},status_code=403)
        if path=='/api/profiles' and request.method!='GET' and not account['is_admin']:
            return JSONResponse({'detail':'Administrator access required'},status_code=403)
        if (path in {'/manage','/manage.html'} or (path.startswith('/api/exercises') and request.method not in SAFE)) and not account['is_admin']:
            return JSONResponse({'detail':'Administrator access required'},status_code=403)
        # Replace the untrusted selector before any existing profile middleware/dependency runs.
        headers=[(key,value) for key,value in request.scope['headers'] if key.lower()!=b'x-profile-id']
        headers.append((b'x-profile-id',account['profile_id'].encode()))
        request.scope['headers']=headers
        request.state.auth=account
        response=await call_next(request)
        expiry=store.renew_remembered(request.cookies.get('mygym_session'),account)
        if expiry is not None:
            set_session_cookies(response,request.cookies.get('mygym_session'),account['csrf'],expiry-time.time())
        response.headers['Cache-Control']='no-store'
        return response
