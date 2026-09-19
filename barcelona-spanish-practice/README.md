# Sobremesa · Language conversation practice

A personal, local-first voice conversation prototype for Spanish, Italian, Russian, and Mandarin learners at beginner, intermediate, and advanced levels. Python/FastAPI manages transcription and structured AI coaching; a small vanilla JavaScript interface handles browser audio.

## AI tools and APIs used

- **OpenAI Codex:** helped plan, write, debug, test, and document the Python backend and browser interface through iterative prompts and feedback.
- **Groq API + `openai/gpt-oss-120b`:** generates conversation replies, translations, corrections, and natural phrasing suggestions. The model runs through Groq; the app does not call the OpenAI API.
- **Groq Whisper (`whisper-large-v3`):** transcribes microphone recordings and supplies the Russian transcript used for phrase matching.
- **Lingolix API:** scores Spanish and Italian pronunciation and provides word/syllable feedback.
- **Browser APIs:** `getUserMedia` and `MediaRecorder` capture speech, Web Audio prepares recordings, and Speech Synthesis reads replies aloud. These are browser capabilities, not separate AI subscriptions.

Gemini and Azure were explored during setup but are not used by the current app. Russian phrase-match percentages are calculated locally from word differences, not generated as AI pronunciation scores.

## Critical prompts that shaped the project

The following are condensed paraphrases of the project requests, not verbatim quotes:

- **Core goal:** Build a Python web app where users choose a language and location, speak with a bot, receive explanations of mistakes, and learn natural regional conversation instead of only textbook language.
- **Initial scope:** Start with a personal prototype for an advanced Spanish learner practicing in Barcelona, Spain.
- **Voice and accent practice:** Slow the voice to conversational speed, add expressive phrasing, and introduce spoken exercises with feedback to help learners sound more natural.
- **Broader access:** Add Italian, Russian, and Mandarin, then beginner and intermediate levels alongside advanced.
- **Practice progression:** Change the practice phrase when the learner scores above 95%, so they can keep practicing with different material.
- **Russian fallback:** Use phrase matching when Russian pronunciation scoring is unavailable, clearly distinguishing recognized-word similarity from pronunciation accuracy.
- **Visual direction:** Use the peach, lavender, and navy palette (`#f1dac4`, `#a69cac`, `#474973`, `#161b33`, `#0d0c1d`), then lighten the background.

## Run locally

Python 3.9 or newer. From this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` locally:

- `GROQ_API_KEY`: create a key at https://console.groq.com/keys for both conversation/coaching and microphone transcription.
- `GROQ_CHAT_MODEL`: defaults to `openai/gpt-oss-120b`, hosted by Groq. No OpenAI or Gemini key is needed. Choose a Groq model supporting structured JSON schemas if changing it. Free-tier quotas apply; check your Groq console.

Do not paste keys into chat, frontend code, or Git commits. `.env` is ignored. Both text and voice practice use the same Groq key. Without keys, the interface and authored starter prompts work, but no simulated AI answers are presented.

```sh
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Restart the server and refresh after editing keys. If port 8000 is busy, use `--port 8001`.

## Practice

Choose a scene, then tap **Speak**. Allow microphone access; tap **Stop recording** when finished (automatic stop after 60 seconds). Review and edit the transcript before sending. Or type a response; Cmd/Ctrl+Enter sends. Replies have replay and optional English translation. Choose English or Spanish coaching and focused or detailed feedback. Changing scenes or starting fresh clears the session after confirmation.

Conversation is Spanish for an advanced learner. Corrections are distinct from optional natural alternatives. The app does not assess pronunciation from transcripts. Select a Spain Spanish voice if your device offers one; there is no promise of a Barcelona accent. Install a Spanish system voice if none appears. Use a current Chrome, Safari, or Firefox browser; microphone recording needs localhost or HTTPS.

## Regional scope

`references.json` contains a deliberately small initial reference library: RAE's Spain-wide colloquial **guay**, and Barcelona City Council's Spanish/Catalan language context. It is not a comprehensive city dialect database. The prompt limits regional notes to those entries, and the server removes unknown reference IDs. A valid ID does not prove every generated claim is correct: generated explanations still need judgment. Expand the library with sourced entries and fluent regional review before claiming broader coverage. Spanish and Catalan are distinct languages. Valid dialect forms should not be treated as errors.

## Data and limits

- No accounts, database, local storage, conversation files, or persistently saved audio. Accent practice keeps one take in browser memory for replay. History exists in the tab and is sent with each chat request; refresh clears it.
- Recordings are sent to Groq. Transcripts, conversation history, and coaching settings are sent to Groq. Provider retention and data-use policies still apply; check Groq’s current data policies. Browser speech voices may use remote services.
- Uploads are limited to 10 MB; UI recordings to 60 seconds. Up to 20 learner turns per conversation and 20 provider requests per minute per server process. Provider limits may be lower.
- Failed chat requests preserve the typed draft. Recording transcription must be reviewed before submission. Provider errors are displayed without exposing API keys.
- Run on loopback for personal use. This is not ready for public deployment: add authentication, total request-body limits at a proxy, multi-user isolation, durable rate limits, and a deployment privacy review first. GitHub Pages cannot run this Python backend.

## Development and tests

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests mock providers: no keys or paid calls are needed. They cover output validation, reference filtering, audio forwarding/limits, missing keys, upstream failures, and local-origin protection. Real microphone/voice behavior and live provider calls require your device permissions and API keys.

Files: `app.py` (server), `references.json` (regional sources), `static/` (interface), `tests/` (API tests). No build step or JavaScript package manager is needed.

## GitHub

This folder already sits inside your portfolio repository. Review and commit it with your usual Git client. `.env`, `.venv`, and caches are excluded. No commit or push is performed automatically. A GitHub API integration is unnecessary for the running app.

## Provider documentation

- https://console.groq.com/docs/speech-to-text
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/billing-faqs
- https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder
- https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis

### Voice pace and phrasing

Playback defaults to a relaxed 0.82× rate. Use Speaking pace to adjust it and Replay to hear the change. Expressive phrasing preserves sentence punctuation and adds subtle sentence-level pitch variation for questions and exclamations. This is a browser-voice approximation, not semantic emotion detection or word-level emphasis; results depend on the installed voice. Mónica or an enhanced Spain Spanish voice is preferred when available. Uncheck Expressive phrasing to use a continuous neutral delivery.

## Accent practice (Lingolix)

Choose a phrase, hear a synthetic Spanish example, record up to 20 seconds, replay it, and select **Get feedback**. Recording and self-comparison work without a key. Automatic feedback uses Lingolix; Groq continues to handle conversation.

### Setup

Create a free account and API key from https://lingolix.com/en, then set `LINGOLIX_API_KEY=your_key` in your existing `.env`. Restart the server and refresh the app. Keep the key private. Azure keys and regions are no longer used; any old Azure or Gemini entries can remain unused in .env.

Lingolix's published Free plan includes 15 audio minutes monthly, no credit card, non-commercial use only. Requests are rejected after the quota is exhausted; no automatic paid fallback is implemented. Current terms: https://lingolix.com/en/pricing

### Feedback and limits

Audio is sent to Lingolix with the known practice text and language `es`. The server converts scores from 0–1 to 0–100, highlights lower-scoring words, exposes expected/detected syllable IPA, and selects authored drills. Missing scores are unavailable, not zero. Missing/extra syllables are reading or recognition differences rather than automatic accent diagnoses. The service's known-text response is not presented as an independent transcript.

Lingolix documents general Spanish, without a Spain/Barcelona dialect selector. We do not claim region-specific pronunciation, fluency, or intonation assessment. The selected browser voice can still be Spain Spanish. IPA estimates and drills need judgment; Spanish accent accuracy has not yet been validated with real learner recordings.

Recordings stay in browser memory until replaced, discarded, or the page closes. Choosing Get feedback sends the audio and phrase to Lingolix. The app does not retain audio; provider policies apply. Browser audio conversion produces mono 16 kHz PCM WAV; the backend validates size, duration, and format. Tests mock the API. Live validation requires a Lingolix key.

API documentation: https://lingolix.com/en/api-portal/docs

## Language selection

Choose Spanish (Spain), Italian (Italy), Russian (Russia), or Mandarin (China) and a city at the top of the app. Choose Beginner, Intermediate, or Advanced. The level changes conversation starters, vocabulary, reply length, and coaching depth; Advanced remains the default. Accent assessment uses the same pronunciation standard at every level. Changing the language or location starts a fresh conversation, clears any local accent recording, and updates the transcription language, voice choices, starters, and explanation-language option. Mandarin uses simplified Chinese. Voices depend on the device; no city-specific voice is guaranteed.

Lingolix assessment is enabled for Spanish and Italian. Russian provides transcript-based phrase matching; Mandarin provides sample playback and local recording/comparison only. Neither receives automatic pronunciation or tone scores. Current provider support: https://lingolix.com/en. Sourced regional notes currently exist only for the original Barcelona profile. Other locations guide conversation context but have no curated regional reference library yet.

Accent practice has ten phrases each for Spanish and Italian. A pronunciation accuracy score strictly above 95/100 automatically selects the next unfinished phrase and clears the old recording while retaining its labeled feedback. Exactly 95 does not advance. Finishing the library starts a new round with a different phrase. Progress is in memory and resets on refresh or practice-setting changes. Russian also advances through its phrase library using its separate phrase-match score. Mandarin retains manual selection without scores.
Run progression checks with `node --test tests/test_accent_progression.cjs`.

Russian phrase match uses Groq Whisper transcription without a target-text hint. Word edit distance produces a 0–100 match percentage; it is not pronunciation assessment. Missing, extra and substituted words are shown. Punctuation, case, stress marks and е/ё differences are ignored, but й remains distinct. Scores above 95 advance through ten Russian phrases. Mandarin still has recording comparison only.
