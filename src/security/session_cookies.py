def set_session_cookies(response, token, csrf, max_age):
    # Allow a top-level GET launch from an installed app/external shortcut.
    # Mutations still require a same-origin request and the session CSRF token.
    options = dict(max_age=max(1, int(max_age)), secure=True, samesite='lax', path='/')
    response.set_cookie('mygym_session', token, httponly=True, **options)
    response.set_cookie('mygym_csrf', csrf, httponly=False, **options)
