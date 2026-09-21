"""Server-side shared-password gate for an HTTPS private demo."""
import base64
import os
import secrets
import time
from collections import deque
from starlette.responses import JSONResponse

attempts = deque()

def check_access(request):
    hosted = os.getenv('DEMO_AUTH_REQUIRED') == '1' or os.getenv('RENDER') == 'true'
    password = os.getenv('DEMO_PASSWORD', '')
    if not hosted and not password:
        return None
    if len(password) < 20:
        return JSONResponse({'detail':'Private demo is not configured.'}, status_code=503)
    if request.url.path == '/healthz' and request.method in ('GET','HEAD'):
        return None
    if hosted and request.url.scheme != 'https':
        return JSONResponse({'detail':'Use the HTTPS demo URL.'}, status_code=403)
    user = supplied = ''
    try:
        scheme, encoded = request.headers.get('authorization','').split(' ',1)
        if scheme.lower() == 'basic' and len(encoded) < 2048:
            user, supplied = base64.b64decode(encoded,validate=True).decode().split(':',1)
    except (ValueError, UnicodeError):
        pass
    valid_user = secrets.compare_digest(user.encode(),b'demo')
    valid_password = secrets.compare_digest(supplied.encode(),password.encode())
    if valid_user and valid_password:
        return None
    now = time.monotonic()
    while attempts and attempts[0] < now - 60: attempts.popleft()
    if len(attempts) >= 30:
        return JSONResponse({'detail':'Try again in a minute.'},status_code=429,headers={'Retry-After':'60'})
    attempts.append(now)
    return JSONResponse({'detail':'Enter the demo username and shared password.'},status_code=401,
        headers={'WWW-Authenticate':'Basic realm="Sobremesa private demo", charset="UTF-8"','Cache-Control':'no-store'})
