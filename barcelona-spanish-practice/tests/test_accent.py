import base64
import io
import json
import wave

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import accent
import app


def wav(seconds=1, rate=16000, channels=1):
    out = io.BytesIO()
    with wave.open(out, 'wb') as file:
        file.setnchannels(channels)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(b'\x00\x01' * int(rate * seconds) * channels)
    return out.getvalue()


def sample():
    return {'text': accent.PHRASES[0]['text'], 'accuracy': 0.72, 'completeness': 1,
            'words': [{'text': 'café', 'accuracy': 0.55, 'syllables': [
                {'text': 'fé', 'expected_ipa': 'fe', 'detected_ipa': 'fi', 'accuracy': 0.55,
                 'is_missing': False, 'is_extra': False}]}]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('LINGOLIX_API_KEY', 'test-lingolix')
    app.RECENT_CALLS.clear()
    with TestClient(app.app) as client:
        yield client


def test_config_does_not_expose_secrets(client):
    response = client.get('/api/accent/config')
    assert response.json()['ready']
    assert len(response.json()['phrases']) == 10
    assert 'test-lingolix' not in response.text
    assert 'cues' not in response.json()['phrases'][0]


def test_missing_setup_keeps_recording_phrases_available(client, monkeypatch):
    monkeypatch.delenv('LINGOLIX_API_KEY')
    assert not client.get('/api/accent/config').json()['ready']
    assert client.get('/api/accent/config').json()['phrases']
    assert client.post('/api/accent/assess', data={'phrase_id': 'terrace'}, files={'audio': ('a.wav', wav(), 'audio/wav')}).status_code == 503


def test_audio_forwarding_and_real_score_driven_drills(client, monkeypatch):
    seen = {}
    async def request(url, **kwargs):
        seen.update(url=url, **kwargs)
        return sample()
    monkeypatch.setattr(app, 'provider_request', request)
    recording = wav()
    response = client.post('/api/accent/assess', data={'phrase_id': 'terrace'}, files={'audio': ('a.wav', recording, 'audio/wav')})
    assert response.status_code == 200
    assert seen['files']['speechdata'][1] == recording
    assert seen['data'] == {'language_code': 'es', 'sentence': accent.PHRASES[0]['text']}
    assert seen['url'] == 'https://api.lingolix.com/api/pronunciation/v3/check'
    assert seen['headers'] == {'Authorization': 'Bearer test-lingolix'}
    assert response.json()['scores']['accuracy'] == 72
    assert 'fluency' not in response.json()['scores']
    assert 'transcript' not in response.json()
    assert 'ca-FÉ' in response.json()['tips'][0]['text']
    assert response.json()['words'][0]['syllables'][0]['detected_ipa'] == 'fi'


def test_unknown_phrase_does_not_call_provider(client, monkeypatch):
    assert client.post('/api/accent/assess', data={'phrase_id': 'invented'}, files={'audio': ('a.wav', wav(), 'audio/wav')}).status_code == 422


@pytest.mark.parametrize('data,status', [(b'bad', 415), (wav(0.1), 422), (wav(26), 422), (wav(rate=8000), 415), (wav(channels=2), 415), (b'x' * 850001, 413), (wav()[:-20], 422)])
def test_audio_validation(client, data, status):
    response = client.post('/api/accent/assess', data={'phrase_id': 'terrace'}, files={'audio': ('a.wav', data, 'audio/wav')})
    assert response.status_code == status


def test_omissions_are_not_accent_diagnoses():
    data = sample()
    data['words'][0]['syllables'][0]['is_missing'] = True
    result = accent.summarize_result(data, accent.PHRASES[0])
    assert result['tips'][0]['title'] == 'Match the phrase first'
    assert not any('another try' in t['title'] for t in result['tips'])


def test_missing_scores_are_not_zero():
    data = sample()
    del data['completeness']
    assert accent.summarize_result(data, accent.PHRASES[0])['scores']['completeness'] is None


@pytest.mark.parametrize('data,status', [({}, 502), ({'accuracy': 0.5, 'words': []}, 502), ({'accuracy': 72, 'words': [{}]}, 502), (None, 502)])
def test_unusable_results(data, status):
    with pytest.raises(HTTPException) as error:
        accent.summarize_result(data, accent.PHRASES[0])
    assert error.value.status_code == status


def test_upstream_error_preserved(client, monkeypatch):
    async def request(*args, **kwargs):
        raise HTTPException(429, 'Quota reached')
    monkeypatch.setattr(app, 'provider_request', request)
    response = client.post('/api/accent/assess', data={'phrase_id': 'terrace'}, files={'audio': ('a.wav', wav(), 'audio/wav')})
    assert response.status_code == 429


@pytest.mark.parametrize('value', [True, float('nan'), -0.1, 1.1, '0.5', None])
def test_invalid_score_not_fabricated(value):
    assert accent.score(value) is None


def test_zero_is_valid():
    assert accent.score(0) == 0
    assert accent.score(1) == 100


def test_italian_assessment_forwards_language_and_phrase(client, monkeypatch):
    seen = {}
    async def request(url, **kwargs):
        seen.update(kwargs)
        return sample()
    monkeypatch.setattr(app, 'provider_request', request)
    phrase = accent.PHRASES_BY_LANGUAGE['it'][0]
    response = client.post('/api/accent/assess', data={'target_language':'it','phrase_id':phrase['id']}, files={'audio':('a.wav',wav(),'audio/wav')})
    assert response.status_code == 200
    assert seen['data'] == {'language_code':'it','sentence':phrase['text']}
    assert response.json()['locale'] == 'it'
    response = client.post('/api/accent/assess', data={'target_language':'it','phrase_id':'terrace'}, files={'audio':('a.wav',wav(),'audio/wav')})
    assert response.status_code == 422


def test_russian_phrase_match_routes_audio_without_target_hint(client, monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','test-groq')
    seen = {}
    phrase = accent.PHRASES_BY_LANGUAGE['ru'][0]
    async def request(url, **kwargs):
        seen.update(url=url, **kwargs)
        return {'text':phrase['text']}
    monkeypatch.setattr(app,'provider_request',request)
    response = client.post('/api/accent/assess', data={'target_language':'ru','phrase_id':phrase['id']}, files={'audio':('a.wav',wav(),'audio/wav')})
    assert response.status_code == 200
    assert response.json()['match_score'] == 100
    assert response.json()['mode'] == 'phrase_match'
    assert 'scores' not in response.json()
    assert seen['url'].startswith('https://api.groq.com/')
    assert seen['data']['language'] == 'ru'
    assert 'prompt' not in seen['data'] and 'sentence' not in seen['data']
    assert len(client.get('/api/accent/config?target_language=ru').json()['phrases']) == 10


def test_russian_empty_transcription_and_missing_key(client, monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','test-groq')
    async def request(*args, **kwargs): return {'text':'...'}
    monkeypatch.setattr(app,'provider_request',request)
    data = {'target_language':'ru','phrase_id':'ru-0'}
    assert client.post('/api/accent/assess',data=data,files={'audio':('a.wav',wav(),'audio/wav')}).status_code == 422
    monkeypatch.delenv('GROQ_API_KEY')
    assert not client.get('/api/accent/config?target_language=ru').json()['ready']
    assert client.post('/api/accent/assess',data=data,files={'audio':('a.wav',wav(),'audio/wav')}).status_code == 503
