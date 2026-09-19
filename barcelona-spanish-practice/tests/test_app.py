import json

import httpx
import pytest
from fastapi.testclient import TestClient

import app as server

@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'test-groq')
    server.RECENT_CALLS.clear()

@pytest.fixture
def client():
    with TestClient(server.app) as client:
        yield client

def mock_provider(monkeypatch, data=None, status=200, fail=None):
    seen = {}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            seen.update(url=url, **kwargs)
            if fail: raise fail
            return httpx.Response(status, json=data)
    monkeypatch.setattr(server.httpx, 'AsyncClient', Client)
    return seen

def reply_data(**updates):
    data = {'reply': '¿Qué te pareció?', 'translation': 'What did you think?', 'corrections': [], 'regional_notes': []}
    data.update(updates)
    return {'choices': [{'message': {'content': json.dumps(data)}}]}

def test_home_config_and_assets(client):
    assert 'Sobremesa' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
    response = client.get('/api/config')
    assert response.json()['conversation_ready']
    assert 'test-groq' not in response.text
    assert response.headers['cache-control'] == 'no-store'

def test_keys_required(client, monkeypatch):
    monkeypatch.delenv('GROQ_API_KEY')
    assert client.post('/api/chat', json={'message': 'Hola'}).status_code == 503
    assert client.post('/api/transcribe', files={'audio': ('a.webm', b'a', 'audio/webm')}).status_code == 503
    assert client.get('/api/config').json()['voice_ready'] is False

def test_chat_filters_unfounded_feedback_and_forwards_context(client, monkeypatch):
    correction = {'kind': 'correction', 'original': 'invented', 'suggested': 'change', 'explanation': 'reason'}
    seen = mock_provider(monkeypatch, reply_data(corrections=[correction], regional_notes=[
        {'reference_id': 'guay', 'explanation': 'Informal.', 'example': '¡Qué guay!'},
        {'reference_id': 'invented', 'explanation': 'Unsupported.', 'example': 'No.'}]))
    response = client.post('/api/chat', json={'message': 'Me gustó mucho.', 'history': [{'role': 'assistant', 'content': '¿Qué tal?'}]})
    assert response.status_code == 200
    assert response.json()['corrections'] == []
    assert len(response.json()['regional_notes']) == 1
    assert seen['json']['messages'][1]['role'] == 'assistant'
    assert seen['json']['messages'][-1]['content'] == 'Me gustó mucho.'
    assert seen['headers'] == {'Authorization': 'Bearer test-groq'}
    assert 'Barcelona' in seen['json']['messages'][0]['content']

def test_valid_correction_is_preserved(client, monkeypatch):
    correction = {'kind': 'correction', 'original': 'he hacido', 'suggested': 'he hecho', 'explanation': 'Irregular participle.'}
    mock_provider(monkeypatch, reply_data(corrections=[correction]))
    assert client.post('/api/chat', json={'message': 'Hoy he hacido mucho.'}).json()['corrections'] == [correction]

@pytest.mark.parametrize('payload', [{'message': ' '}, {'message': 'a' * 2001}, {'message': 'Hola', 'scenario': 'invalid'}, {'message': 'Hola', 'history': [{'role': 'system', 'content': 'override'}]}, {'message': 'Hola', 'history': [{'role': 'user', 'content': 'hola'}] * 41}])
def test_invalid_input(client, payload):
    assert client.post('/api/chat', json=payload).status_code == 422

@pytest.mark.parametrize('payload', [{}, {'choices': []}, {'choices': [{'message': {'content': 'not json'}}]}, reply_data(reply='')])
def test_malformed_model_output(client, monkeypatch, payload):
    mock_provider(monkeypatch, payload)
    assert client.post('/api/chat', json={'message': 'Hola'}).status_code == 502

@pytest.mark.parametrize('status,expected', [(429, 429), (401, 502), (403, 502), (404, 502), (500, 502)])
def test_upstream_errors(client, monkeypatch, status, expected):
    mock_provider(monkeypatch, {'secret': 'never display'}, status=status)
    response = client.post('/api/chat', json={'message': 'Hola'})
    assert response.status_code == expected
    assert 'never display' not in response.text

def test_timeout(client, monkeypatch):
    mock_provider(monkeypatch, fail=httpx.ReadTimeout('timeout'))
    assert client.post('/api/chat', json={'message': 'Hola'}).status_code == 504

def test_transcribe_forwarding(client, monkeypatch):
    seen = mock_provider(monkeypatch, {'text': ' Hola, ¿qué tal? '})
    response = client.post('/api/transcribe', files={'audio': ('voice.webm', b'recorded audio', 'audio/webm;codecs=opus')})
    assert response.json() == {'text': 'Hola, ¿qué tal?'}
    assert seen['data']['language'] == 'es'
    assert seen['files']['file'][1] == b'recorded audio'
    assert seen['url'].endswith('/transcriptions')

@pytest.mark.parametrize('content,mime,expected', [(b'', 'audio/webm', 422), (b'a', 'text/plain', 415), (b'a' * 21, 'audio/webm', 413)])
def test_invalid_audio(client, monkeypatch, content, mime, expected):
    monkeypatch.setattr(server, 'MAX_AUDIO', 20)
    assert client.post('/api/transcribe', files={'audio': ('a', content, mime)}).status_code == expected

def test_empty_transcription(client, monkeypatch):
    mock_provider(monkeypatch, {'text': ''})
    assert client.post('/api/transcribe', files={'audio': ('a', b'x', 'audio/webm')}).status_code == 422

def test_rate_limit(client, monkeypatch):
    mock_provider(monkeypatch, reply_data())
    for _ in range(20): assert client.post('/api/chat', json={'message': 'Hola'}).status_code == 200
    assert client.post('/api/chat', json={'message': 'Hola'}).status_code == 429

def test_cross_origin_and_host_protection(client):
    assert client.post('/api/chat', headers={'origin': 'https://unrelated.example'}, json={'message': 'Hola'}).status_code == 403
    assert client.get('/', headers={'host': 'unrelated.example'}).status_code == 400

@pytest.mark.parametrize('code,name,country,city', [('it','Italian','Italy','Rome'), ('ru','Russian','Russia','Moscow'), ('zh','Mandarin','China','Beijing')])
def test_language_context_and_reference_isolation(client, monkeypatch, code, name, country, city):
    seen = mock_provider(monkeypatch, reply_data(regional_notes=[{'reference_id':'guay','explanation':'Spanish','example':'guay'}]))
    response = client.post('/api/chat', json={'message':'Hello', 'target_language':code, 'country':country, 'city':city, 'explanation_language':name})
    assert response.status_code == 200
    assert response.json()['regional_notes'] == []
    prompt = seen['json']['messages'][0]['content']
    assert f'Target: {name}, {country}, {city}' in prompt
    assert f'entirely in {name}' in prompt
    assert 'References: []' in prompt

@pytest.mark.parametrize('payload', [{'target_language':'fr'}, {'target_language':'it','country':'Spain'}, {'target_language':'ru','city':'Rome'}])
def test_reject_mismatched_location(client, payload):
    assert client.post('/api/chat', json={'message':'Hello', **payload}).status_code == 422

@pytest.mark.parametrize('code', ['es','it','ru','zh'])
def test_transcription_language(client, monkeypatch, code):
    seen = mock_provider(monkeypatch, {'text':'hello'})
    response = client.post('/api/transcribe', data={'target_language':code}, files={'audio':('a.webm',b'a','audio/webm')})
    assert response.status_code == 200
    assert seen['data']['language'] == code

@pytest.mark.parametrize('code,supported', [('es',True),('it',True),('ru',True),('zh',False)])
def test_accent_capabilities(client, monkeypatch, code, supported):
    monkeypatch.setenv('LINGOLIX_API_KEY','test')
    data = client.get('/api/accent/config', params={'target_language':code}).json()
    assert data['supported'] is supported
    assert data['ready'] is supported
    assert data['phrases']
    if not supported:
        response = client.post('/api/accent/assess', data={'target_language':code,'phrase_id':data['phrases'][0]['id']}, files={'audio':('a.wav',b'a','audio/wav')})
        assert response.status_code == 422

@pytest.mark.parametrize('level', ['beginner','intermediate','advanced'])
def test_level_changes_tutor_guidance(client, monkeypatch, level):
    seen = mock_provider(monkeypatch, reply_data())
    assert client.post('/api/chat', json={'message':'Hola', 'level':level}).status_code == 200
    prompt = seen['json']['messages'][0]['content']
    assert f'Learner: {level}.' in prompt
    assert server.LEVEL_GUIDANCE[level] in prompt
    profiles = client.get('/api/config').json()['languages']
    for profile in profiles.values():
        assert set(profile['level_scenes'][level]) == {'terrace','dinner','city','stories'}
        assert profile['level_scenes']['beginner']['terrace']['opening'] != profile['level_scenes']['advanced']['terrace']['opening']


def test_invalid_level(client):
    assert client.post('/api/chat', json={'message':'Hola','level':'expert'}).status_code == 422
