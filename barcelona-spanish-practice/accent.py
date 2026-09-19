"""Read-aloud pronunciation assessment; never infer pronunciation from transcripts."""
import io
import math
import os
import wave
from phrase_match import compare, tokens

from fastapi import HTTPException

MAX_WAV_BYTES = 850_000
PHRASES = [
    {'id': 'terrace', 'title': 'A café order · vowels and stress',
     'text': 'Quería un café con leche y una tostada, por favor.',
     'focus': 'Keep the vowels clear and let the sentence flow at a comfortable pace.',
     'cues': {'café': 'Try ca-FÉ, with the stress on the final syllable. Then put it back into “un café con leche”.',
              'quería': 'Try que-RÍ-a slowly, then return to “Quería un café” without rushing.'}},
    {'id': 'reservation', 'title': 'A dinner reservation · clear syllables',
     'text': 'He reservado una mesa para cuatro personas en la terraza.',
     'focus': 'Listen for the different r sounds in the phrase; aim for clear words before adding speed.',
     'cues': {'terraza': 'Practice “terraza” slowly with the sample voice, then “en la terraza”. The written rr is a useful sound to isolate; this score alone does not identify how you produced it.',
              'reservado': 'Try re-ser-VA-do, then “he reservado”. Keep the stressed syllable clear without separating every syllable in the full sentence.'}},
    {'id': 'plans', 'title': 'Making plans · connected speech',
     'text': 'Si te apetece, podemos dar una vuelta antes de cenar.',
     'focus': 'Practice the sentence in two thought groups: the invitation, then the plan.',
     'cues': {'apetece': 'Try a-pe-TE-ce, then “si te apetece”. Listen to your chosen Spain Spanish voice and compare the whole word.',
              'podemos': 'Try po-DE-mos, then link it into “podemos dar una vuelta”.'}},
    {'id': 'opinion', 'title': 'Sharing an opinion · a longer phrase',
     'text': 'Aunque entiendo tu punto de vista, no estoy del todo de acuerdo.',
     'focus': 'Take a small breath at the comma and keep each thought group connected.',
     'cues': {'entiendo': 'Try en-TIEN-do, then “entiendo tu punto de vista”. Listen, repeat slowly, and return to your normal pace.',
              'acuerdo': 'Try a-CUER-do, then “de acuerdo”. Compare the recording rather than forcing a faster pace.'}},
]


PHRASES_BY_LANGUAGE = {'es': PHRASES}
for code, entries in {
    'it': [('Un caffè', 'Vorrei un caffè e un bicchiere d’acqua, per favore.'), ('Una cena', 'Ho prenotato un tavolo per quattro persone sulla terrazza.'), ('Un’opinione', 'Capisco il tuo punto di vista, ma non sono del tutto d’accordo.')],
    'ru': [('В кафе', 'Можно мне чашку кофе и стакан воды, пожалуйста?'), ('Ужин с друзьями', 'Давай пригласим друзей на ужин в эту пятницу.')],
    'zh': [('在咖啡馆', '请给我一杯咖啡和一杯水，谢谢。'), ('一起吃晚饭', '这个星期五我们一起去吃晚饭，好吗？')],
}.items():
    PHRASES_BY_LANGUAGE[code] = [dict(id=f'{code}-{i}', title=title, text=text,
        focus='Listen to the whole phrase, record yourself, and compare at a comfortable pace.', cues={})
        for i, (title, text) in enumerate(entries)]


# A varied, finite library; completed rounds can be repeated for consistency.
for language, entries in {
    'es': [
        ('At the market', '¿Cuánto cuestan estos tomates y de dónde vienen?'),
        ('Finding the station', 'Perdona, ¿sabes cómo llegar a la estación de tren?'),
        ('An invitation', '¿Te gustaría tomar algo después del trabajo?'),
        ('A change of plans', 'Al final no puedo ir hoy, pero mañana tengo tiempo.'),
        ('A recommendation', 'Busco un sitio tranquilo donde podamos hablar un rato.'),
        ('A weekend story', 'El sábado fuimos a pasear y acabamos descubriendo una librería.'),
    ],
    'it': [
        ('Al mercato', 'Quanto costano questi pomodori e da dove vengono?'),
        ('La stazione', 'Scusa, sai come arrivare alla stazione dei treni?'),
        ('Un invito', 'Ti va di prendere qualcosa da bere dopo il lavoro?'),
        ('Cambiare programma', 'Oggi non riesco a venire, ma domani ho tempo.'),
        ('Un consiglio', "Cerco un posto tranquillo dove possiamo parlare un po’."),
        ('Il fine settimana', 'Sabato siamo andati a fare una passeggiata e abbiamo scoperto una libreria.'),
        ('In viaggio', 'Vorrei un biglietto di andata e ritorno per domani mattina.'),
    ],
}.items():
    PHRASES_BY_LANGUAGE[language].extend(
        dict(id=f'{language}-extra-{i}', title=title, text=text,
             focus='Listen for word stress and connected speech. Keep a comfortable pace.', cues={})
        for i, (title, text) in enumerate(entries))


PHRASES_BY_LANGUAGE['ru'].extend(
    dict(id=f'ru-extra-{i}', title=title, text=text, focus='Read the words naturally, then check what the transcription service heard.', cues={})
    for i, (title, text) in enumerate([
        ('На рынке', 'Сколько стоят эти яблоки?'),
        ('На вокзале', 'Мне нужен билет на завтра утром.'),
        ('Прогулка', 'Давай погуляем в парке после работы.'),
        ('Новые планы', 'Сегодня я занят, но завтра у меня будет время.'),
        ('В ресторане', 'Мы хотели бы заказать столик на двоих.'),
        ('В городе', 'Подскажите, пожалуйста, как пройти к станции метро?'),
        ('Выходные', 'На выходных мы с друзьями ходили в музей.'),
        ('Мнение', 'Я понимаю твою точку зрения, но не совсем согласен.'),
    ]))


def config(language='es'):
    if language == 'ru':
        return {
            'ready': bool(os.getenv('GROQ_API_KEY', '').strip()), 'supported': True, 'mode': 'phrase_match',
            'phrases': [{k:v for k,v in p.items() if k != 'cues'} for p in PHRASES_BY_LANGUAGE['ru']],
            'setup_message': 'Add GROQ_API_KEY to .env and restart to enable phrase matching.',
            'privacy': 'Get phrase match sends your recording to Groq for transcription. The app compares the transcript with the target phrase locally and does not save your audio. This measures recognized words, not pronunciation.',
        }
    return {
        'ready': language in ('es', 'it') and bool(os.getenv('LINGOLIX_API_KEY', '').strip()),
        'supported': language in ('es', 'it'),
        'phrases': [{k: v for k, v in p.items() if k != 'cues'} for p in PHRASES_BY_LANGUAGE[language]],
        'setup_message': 'Automatic assessment is not available for this language with Lingolix. You can still listen, record, and compare your attempt.' if language not in ('es', 'it') else 'Add LINGOLIX_API_KEY to your local .env and restart. Get a free key at lingolix.com. The free plan includes 15 audio minutes monthly for non-commercial use. Recording and replay work without a key.',
        'privacy': 'Recording stays in this tab until you choose Get feedback, which sends audio and the practice phrase to Lingolix. The app does not save your audio; Lingolix service policies apply. Discard or refresh to clear your local recording.',
    }


def validate_wav(data):
    if len(data) > MAX_WAV_BYTES:
        raise HTTPException(413, 'The recording is too large. Please record a shorter attempt.')
    try:
        with wave.open(io.BytesIO(data), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise HTTPException(415, 'Assessment needs mono 16 kHz PCM WAV audio. Please record again using the app.')
            frames = wav.getnframes()
            if not 0.5 <= frames / 16000 <= 25:
                raise HTTPException(422, 'Please record between half a second and 20 seconds of speech.')
            if len(wav.readframes(frames)) != frames * 2:
                raise HTTPException(422, 'The recording is incomplete. Please record again.')
    except (wave.Error, EOFError):
        raise HTTPException(415, 'The recording could not be read as WAV audio. Please record again.')


def score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return round(value * 100, 1)


def summarize_result(result, phrase):
    if not isinstance(result, dict):
        raise HTTPException(502, 'The assessment service returned an unreadable result. Please retry.')
    try:
        scores = {'accuracy': score(result.get('accuracy')), 'completeness': score(result.get('completeness'))}
        if scores['accuracy'] is None or not isinstance(result.get('words'), list) or not result['words']:
            raise ValueError('Missing assessment')
        words = []
        for word in result['words'][:100]:
            if not isinstance(word.get('text'), str):
                raise ValueError('Missing word')
            syllables = []
            for syllable in word.get('syllables', [])[:30]:
                syllables.append({
                    'text': str(syllable.get('text', ''))[:100],
                    'expected_ipa': str(syllable.get('expected_ipa', ''))[:200],
                    'detected_ipa': str(syllable.get('detected_ipa', ''))[:200],
                    'accuracy': score(syllable.get('accuracy')),
                    'missing': syllable.get('is_missing') is True,
                    'extra': syllable.get('is_extra') is True})
            error = 'Insertion' if any(x['extra'] for x in syllables) else 'Omission' if any(x['missing'] for x in syllables) else 'None'
            words.append({'word': word['text'][:100], 'accuracy': score(word.get('accuracy')),
                          'error': error, 'syllables': syllables})
        # In known-text mode, "text" may be the reference, not an independent transcript.
        assessed_text = result.get('text', phrase['text'])
        if not isinstance(assessed_text, str):
            assessed_text = phrase['text']
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        raise HTTPException(502, 'Lingolix did not return usable pronunciation scores. Please try again.')
    tips = []
    # Reading differences must not be described as pronunciation defects.
    if any(w['error'] in ('Omission', 'Insertion') for w in words) or (scores['completeness'] is not None and scores['completeness'] < 80):
        tips.append({'title': 'Match the phrase first', 'text': 'The service detected a reading difference or missed words. Check what it heard, then read the exact phrase again. A skipped or misheard word is not proof of an accent problem.'})
    candidates = sorted([w for w in words if w['error'] not in ('Omission', 'Insertion') and
                         (w['error'] == 'Mispronunciation' or (w['accuracy'] is not None and w['accuracy'] < 80))],
                        key=lambda w: w['accuracy'] if w['accuracy'] is not None else 100)
    seen = set()
    for word in candidates:
        normalized = word['word'].lower().strip('.,!?¿¡:;')
        if normalized in seen:
            continue
        seen.add(normalized)
        cue = phrase['cues'].get(normalized, f'Listen to “{word["word"]}” in the sample phrase. Repeat the word slowly, then reconnect it to the words around it. Compare your recording and try again at a comfortable pace.')
        tips.append({'title': f'Give “{word["word"]}” another try', 'text': 'The audio assessment flagged this word for review. ' + cue + ' This is a practice suggestion, not a diagnosis of a specific sound error.'})
        if len(seen) == 2:
            break
    if not tips:
        tips.append({'title': 'Build consistency', 'text': 'No high-priority word issue was flagged in this take. Repeat the phrase once more at a comfortable conversational pace, then compare both attempts by ear.'})
    return {'scores': scores, 'words': words, 'tips': tips, 'assessed_text': assessed_text[:3000],
            'locale': 'es', 'provider': 'Lingolix'}


async def assess(audio, phrase_id, request_provider, limit_calls, language='es'):
    try:
        if language not in ('es', 'it', 'ru'):
            raise HTTPException(422, 'Automatic assessment is not supported for this language. Use listening and recording practice.')
        phrase = next((p for p in PHRASES_BY_LANGUAGE[language] if p['id'] == phrase_id), None)
        if phrase is None:
            raise HTTPException(422, 'Choose one of the available practice phrases.')
        key_name = 'GROQ_API_KEY' if language == 'ru' else 'LINGOLIX_API_KEY'
        key = os.getenv(key_name, '').strip()
        if not key:
            raise HTTPException(503, f'Add {key_name} to .env and restart the app.')
        data = await audio.read(MAX_WAV_BYTES + 1)
        validate_wav(data)
        limit_calls()
        if language == 'ru':
            result = await request_provider('https://api.groq.com/openai/v1/audio/transcriptions',
                headers={'Authorization': f'Bearer {key}'},
                files={'file': ('practice.wav', data, 'audio/wav')},
                data={'model': 'whisper-large-v3', 'language': 'ru', 'response_format': 'json', 'temperature': '0'})
            transcript = result.get('text') if isinstance(result, dict) else None
            if not isinstance(transcript, str) or not tokens(transcript):
                raise HTTPException(422, 'No words were detected. Please record the phrase again.')
            if len(transcript) > 3000:
                raise HTTPException(422, 'The transcript is too long. Please record a shorter attempt.')
            return compare(phrase['text'], transcript.strip())
        result = await request_provider(
            'https://api.lingolix.com/api/pronunciation/v3/check',
            headers={'Authorization': f'Bearer {key}'},
            files={'speechdata': ('practice.wav', data, 'audio/wav')},
            data={'sentence': phrase['text'], 'language_code': language})
        summary = summarize_result(result, phrase)
        summary['locale'] = language
        return summary
    finally:
        await audio.close()
