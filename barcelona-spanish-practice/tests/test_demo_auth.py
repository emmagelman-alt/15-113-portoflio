from fastapi.testclient import TestClient
import app
import demo_auth

def test_private_demo(monkeypatch):
    monkeypatch.setenv('DEMO_AUTH_REQUIRED','1')
    monkeypatch.setenv('DEMO_PASSWORD','test-password-with-25-characters')
    demo_auth.attempts.clear()
    with TestClient(app.app,base_url='https://testserver') as c:
        for path in ['/', '/static/index.html','/api/config','/docs','/openapi.json']:
            assert c.get(path).status_code == 401
        assert c.post('/api/chat',json={'message':'Hola'}).status_code == 401
        assert c.get('/',auth=('demo','test-password-with-25-characters')).status_code == 200
        assert c.get('/',headers={'Authorization':'Basic !!!!'}).status_code == 401
        assert c.get('/healthz').status_code == 200
        assert c.get('http://testserver/').status_code == 403
        monkeypatch.delenv('DEMO_PASSWORD')
        assert c.get('/').status_code == 503
        assert c.get('/healthz').status_code == 503

def test_login_limit(monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD','test-password-with-25-characters')
    demo_auth.attempts.clear()
    with TestClient(app.app) as c:
        for _ in range(30): assert c.get('/').status_code == 401
        assert c.get('/').status_code == 429
        assert c.get('/',auth=('demo','test-password-with-25-characters')).status_code == 200
