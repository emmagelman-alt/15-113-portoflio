const $ = id => document.getElementById(id);
let scenes = {
  terrace: { title: 'En una terraza', opening: 'Hacía tiempo que no nos sentábamos a charlar sin mirar el reloj. ¿Qué te ha tenido más entretenido últimamente: algo que disfrutas o algo de lo que necesitas desconectar?', translation: 'It’s been a while since we sat down to talk without watching the clock. What has been keeping you busy lately: something you enjoy, or something you need a break from?' },
  dinner: { title: 'Una cena entre amigos', opening: 'Tenemos que organizar la cena del viernes y cada uno propone algo distinto. Yo preferiría un sitio donde se pueda hablar tranquilamente. ¿Qué plan defenderías tú y cómo convencerías al resto?', translation: 'We need to organize Friday’s dinner and everyone has a different suggestion. I’d prefer somewhere we can talk comfortably. What plan would you argue for, and how would you persuade everyone else?' },
  city: { title: 'La ciudad que compartimos', opening: 'El otro día hablábamos de lo difícil que es equilibrar una ciudad abierta a los visitantes con una ciudad cómoda para quienes viven en ella. ¿Dónde pondrías tú el límite?', translation: 'The other day we were talking about how hard it is to balance a city that welcomes visitors with one that is comfortable for its residents. Where would you draw the line?' },
  stories: { title: 'Cuéntame una historia', opening: 'A veces los planes que salen mal acaban siendo las mejores anécdotas. ¿Te ha pasado algo últimamente que en su momento te diera rabia y ahora te haga gracia?', translation: 'Sometimes plans that go wrong make the best stories. Has anything happened to you lately that annoyed you at the time but now makes you laugh?' }
};
let scene = 'terrace', history = [], busy = false, config = {}, recorder = null, timer = null, stream = null, recording = false, pendingScene = null, voices = [];
let accentBusy = false, accentRecording = false;
let targetLanguage = 'es', targetCountry = 'Spain', targetCity = 'Barcelona', pendingTarget = null, practiceLevel = 'advanced';
function targetProfile() { return config.languages?.[targetLanguage] || {name:'Spanish', native:'Español', locale:'es-ES'}; }
const emptyCoaching = $('feedback-cards').innerHTML;
function status(text, error = false) { $('status').textContent = text; $('status').classList.toggle('error', error); }
function syncControls() {
  ['target-language', 'target-country', 'target-city', 'practice-level'].forEach(id => $(id).disabled = !config.languages || busy || recording || accentBusy || accentRecording);
  $('send').disabled = busy || recording || accentBusy || accentRecording;
  $('record').disabled = busy || accentBusy || accentRecording || !config.voice_ready || !navigator.mediaDevices || !window.MediaRecorder;
  $('reset').disabled = busy || recording || accentBusy || accentRecording;
  document.querySelectorAll('.scene').forEach(b => { b.disabled = busy || recording || accentBusy || accentRecording; });
  $('message').disabled = busy || recording || accentBusy || accentRecording;
  $('language').disabled = busy || recording || accentBusy || accentRecording;
  $('feedback').disabled = busy || recording || accentBusy || accentRecording;
  if (typeof syncAccentControls === 'function') syncAccentControls();
}
function setBusy(value) { busy = value; syncControls(); }
function el(tag, text, className) { const node = document.createElement(tag); node.textContent = text; if (className) node.className = className; return node; }
function speak(text) {
  if (busy || recording || accentBusy || accentRecording) return;
  if (!window.speechSynthesis || !voices.length) { status(`No ${targetProfile().name} voice is available on this device. You can still read every reply.`, true); return; }
  speechSynthesis.cancel();
  if ($('accent-audio')) $('accent-audio').pause();
  const voice = voices.find(v => v.voiceURI === $('voice').value) || voices[0];
  const rate = Number($('pace').value) || 0.82;
  const expressive = $('expressive').checked;
  // Keep full sentences intact so the voice can interpret their punctuation.
  // Segmenter avoids splitting abbreviations and decimal numbers as a simple regex would.
  const sentences = expressive && typeof Intl.Segmenter === 'function'
    ? Array.from(new Intl.Segmenter(targetLanguage, { granularity: 'sentence' }).segment(text), item => item.segment)
    : [text];
  for (const sentence of sentences) {
    if (!sentence.trim()) continue;
    const utterance = new SpeechSynthesisUtterance(sentence);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = rate;
    // Subtle sentence-level variation, not emotion detection or word-level prosody.
    utterance.pitch = expressive ? (/[¡!！]/.test(sentence) ? 1.08 : /[¿?？]/.test(sentence) ? 1.04 : 1) : 1;
    utterance.onerror = event => {
      if (!['interrupted', 'canceled'].includes(event.error)) {
        speechSynthesis.cancel();
        status('Playback was unavailable. Try Replay or another voice.', true);
      }
    };
    speechSynthesis.speak(utterance);
  }
}
function addMessage(role, text, translation = '', starter = false) {
  const article = el('article', '', `message ${role}`);
  article.append(el('div', role === 'user' ? 'YOU' : starter ? 'SOBREMESA · CONVERSATION STARTER' : 'SOBREMESA', 'speaker'));
  const bubble = el('div', text, 'bubble'); bubble.lang = targetProfile().locale; article.append(bubble);
  if (role === 'assistant') {
    const actions = el('div', '', 'message-actions');
    const replay = el('button', '▷ Replay', 'text-button'); replay.type = 'button'; replay.onclick = () => speak(text); actions.append(replay);
    if (translation) {
      const translated = el('div', translation, 'translation'); translated.hidden = true;
      const toggle = el('button', 'Show translation', 'text-button'); toggle.type = 'button'; toggle.setAttribute('aria-expanded', 'false');
      toggle.onclick = () => { translated.hidden = !translated.hidden; toggle.textContent = translated.hidden ? 'Show translation' : 'Hide translation'; toggle.setAttribute('aria-expanded', String(!translated.hidden)); };
      actions.append(toggle); article.append(actions, translated);
    } else article.append(actions);
  }
  $('messages').append(article); $('messages').scrollTop = $('messages').scrollHeight;
}
function showFeedback(data) {
  const panel = $('feedback-cards'); panel.replaceChildren();
  data.corrections.forEach(c => {
    const card = el('div', '', 'feedback-card'); card.append(el('span', c.kind === 'correction' ? 'A small correction' : 'Another natural option', 'tag'));
    card.append(el('p', c.original, c.kind === 'correction' ? 'original' : ''), el('p', `→ ${c.suggested}`, 'suggested'), el('p', c.explanation)); panel.append(card);
  });
  data.regional_notes.forEach(n => {
    const reference = (config.references || []).find(r => r.id === n.reference_id); if (!reference) return;
    const card = el('div', '', 'feedback-card'); card.append(el('span', reference.scope, 'tag'), el('h3', reference.term), el('p', n.explanation), el('p', n.example, 'suggested'));
    const link = el('a', reference.source_label + ' ↗'); link.href = reference.source; link.target = '_blank'; link.rel = 'noopener noreferrer'; card.append(link); panel.append(card);
  });
  if (!panel.children.length) { const card = el('div', '', 'feedback-card'); card.append(el('span', 'KEEP YOUR FLOW', 'tag'), el('h3', 'Nothing to flag this turn.'), el('p', 'Keep the conversation going. There’s no need to rewrite every sentence.')); panel.append(card); }
}
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'That request could not be completed. Check your input and try again.');
  return data;
}
function startScene(next) {
  if (window.speechSynthesis) speechSynthesis.cancel();
  scene = next; const starter = scenes[scene]; history = [{ role: 'assistant', content: starter.opening }];
  $('messages').replaceChildren(); $('feedback-cards').innerHTML = emptyCoaching; $('message').value = ''; $('scene-title').textContent = starter.title;
  document.querySelectorAll('.scene').forEach(b => { const active = b.dataset.scene === scene; b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active)); });
  addMessage('assistant', starter.opening, starter.translation, true); status('Take your time. This is practice.');
}
function requestReset(next) {
  if (history.length > 1 || $('message').value.trim()) { pendingScene = next; $('reset-dialog').showModal(); }
  else startScene(next);
}
$('cancel-reset').onclick = () => { pendingTarget = null; $('reset-dialog').close(); };
$('reset-dialog').addEventListener('cancel', () => { pendingTarget = null; });
$('confirm-reset').onclick = () => { $('reset-dialog').close(); if (pendingTarget) { const next = pendingTarget; pendingTarget = null; applyTarget(...next); } else startScene(pendingScene || scene); };
$('reset').onclick = () => requestReset(scene);
document.querySelectorAll('.scene').forEach(b => b.onclick = () => { if (b.dataset.scene !== scene) requestReset(b.dataset.scene); });
$('chat-form').onsubmit = async event => {
  event.preventDefault(); if (busy || recording || accentBusy || accentRecording) return;
  const message = $('message').value.trim(); if (!message) { status('Say or type something first.'); $('message').focus(); return; }
  if (!config.conversation_ready) { status('Add GROQ_API_KEY to .env and restart the app to begin live conversations.', true); return; }
  if (history.length >= 40) { status('You’ve reached the 20-turn practice limit. Start fresh for a new conversation.'); return; }
  setBusy(true); if (window.speechSynthesis) speechSynthesis.cancel(); status('Listening to your ideas…');
  try {
    const data = await api('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, history, target_language: targetLanguage, level: practiceLevel, country: targetCountry, city: targetCity, scenario: scene, explanation_language: $('language').value, feedback: $('feedback').value }) });
    history.push({ role: 'user', content: message }, { role: 'assistant', content: data.reply });
    addMessage('user', message); addMessage('assistant', data.reply, data.translation); showFeedback(data); $('message').value = '';
    setBusy(false); status('Your turn. Follow the conversation wherever it goes.'); if ($('autoplay').checked) speak(data.reply);
  } catch (error) { status(error.message || 'Connection lost. Please try again.', true); }
  finally { setBusy(false); $('message').focus(); }
};
$('message').onkeydown = event => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); $('chat-form').requestSubmit(); } };
function releaseMic() { clearTimeout(timer); if (stream) stream.getTracks().forEach(track => track.stop()); stream = null; }
function stopRecording() { if (recorder && recorder.state === 'recording') recorder.stop(); }
$('record').onclick = async () => {
  if (recording) { stopRecording(); return; }
  if (busy || accentBusy || accentRecording) return;
  if ($('message').value.trim()) { status('Send or clear your current draft before recording another response.'); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) { status('This browser cannot record audio. Use a current browser on localhost, or type your response.', true); return; }
  setBusy(true); if ($('accent-audio')) $('accent-audio').pause(); status('Waiting for microphone permission…');
  try {
    if (window.speechSynthesis) speechSynthesis.cancel();
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks = []; let failed = false;
    recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    recorder.onerror = () => { failed = true; releaseMic(); recording = false; $('record').classList.remove('recording'); $('record-label').textContent = 'Speak'; setBusy(false); status('Recording failed. Try again or type your response.', true); };
    recorder.onstop = async () => {
      const type = recorder.mimeType || mime || 'audio/webm'; releaseMic(); recording = false;
      $('record').classList.remove('recording'); $('record-label').textContent = 'Speak'; if (failed) return;
      setBusy(true); status('Turning your speech into text…');
      try { const form = new FormData(); form.append('target_language', targetLanguage); form.append('audio', new Blob(chunks, { type }), 'recording'); const data = await api('/api/transcribe', { method: 'POST', body: form }); $('message').value = data.text; status('Review what we heard, then send. Fix any misheard words first.'); }
      catch (error) { status(error.message || 'Transcription failed. Please try again.', true); }
      finally { setBusy(false); $('message').focus(); }
    };
    recorder.start(); recording = true; busy = false; syncControls(); $('record').classList.add('recording'); $('record-label').textContent = 'Stop recording'; status('Listening… tap Stop when you’re ready. Up to 60 seconds.');
    timer = setTimeout(stopRecording, 60000);
  } catch (error) { releaseMic(); recording = false; setBusy(false); status(error.name === 'NotAllowedError' ? 'Microphone access was denied. Allow it in browser settings, or type your response.' : 'Could not start the microphone. Check your device or type your response.', true); }
};
function loadVoices() {
  if (!window.speechSynthesis) { $('voice-note').textContent = 'Speech playback is unavailable in this browser.'; return; }
  const previous = $('voice').value;
  voices = speechSynthesis.getVoices().filter(v => (targetLanguage === 'zh' ? /^(zh(?:[-_](?:CN|TW|SG|Hans|Hant))?|cmn(?:[-_].*)?)$/i.test(v.lang) : v.lang.toLowerCase().split(/[-_]/)[0] === targetLanguage)).sort((a, b) => Number(b.lang.replace('_','-') === targetProfile().locale) - Number(a.lang.replace('_','-') === targetProfile().locale));
  $('voice').replaceChildren();
  voices.forEach(v => { const option = el('option', `${v.name} (${v.lang})`); option.value = v.voiceURI; $('voice').append(option); });
  if (voices.some(v => v.voiceURI === previous)) $('voice').value = previous;
  else {
    const preferred = voices.find(v => v.lang.replace('_','-') === targetProfile().locale && /m[oó]nica|enhanced|premium|natural/i.test(v.name));
    if (preferred) $('voice').value = preferred.voiceURI;
  }
  if (!voices.length) { $('voice').append(el('option', `No ${targetProfile().name} voice available`)); $('voice-note').textContent = `Install a ${targetProfile().name} system voice to enable playback. Text practice still works.`; }
  else $('voice-note').textContent = 'Pace and phrasing apply on the next playback. Expression varies by voice; a city-specific accent is not guaranteed. Your device may use an online voice service.';
}
window.addEventListener('pagehide', () => { releaseMic(); if (window.speechSynthesis) speechSynthesis.cancel(); });
startScene('terrace'); loadVoices(); if (window.speechSynthesis) speechSynthesis.onvoiceschanged = loadVoices;
api('/api/config').then(data => {
  config = data;
  $('target-language').replaceChildren();
  Object.entries(config.languages).forEach(([code, profile]) => { const option = el('option', `${profile.name} · ${profile.native}`); option.value = code; $('target-language').append(option); });
  applyTarget('es', 'Spain', 'Barcelona');
  const missing = []; if (!data.conversation_ready) missing.push('GROQ_API_KEY for conversation'); if (!data.voice_ready) missing.push('GROQ_API_KEY for microphone transcription');
  if (missing.length) { $('setup').hidden = false; $('setup').textContent = `Your space is ready. To connect live practice, add ${missing.join(' and ')} to the local .env file, then restart the server. Instructions are in README.md. The opening prompts are written examples.`; }
  syncControls();
}).catch(() => { status('Could not reach the local server. Restart it and refresh this page.', true); syncControls(); });

function setOptions(id, values, selected) {
  $(id).replaceChildren(); values.forEach(value => { const option = el('option', value); option.value = value; $(id).append(option); }); $(id).value = selected;
}
function applyTarget(code, country, city, level = practiceLevel) {
  practiceLevel = level;
  $('practice-level').value = level;
  $('level-tag').textContent = level.charAt(0).toUpperCase() + level.slice(1);
  targetLanguage = code; targetCountry = country; targetCity = city;
  const profile = targetProfile(); scenes = profile.level_scenes[practiceLevel];
  $('target-language').value = code;
  setOptions('target-country', Object.keys(profile.countries), country);
  setOptions('target-city', profile.countries[country], city);
  $('destination-title').textContent = city;
  $('target-tag').textContent = profile.name;
  $('local-context').textContent = profile.note;
  $('regional-context').textContent = code === 'es' && city === 'Barcelona' ? 'Regional tips link to reference material. Spain-wide expressions are not unique to Barcelona.' : 'City selection guides conversation topics. Sourced regional tips are not available yet for this location; the tutor will avoid unsupported local claims.';
  $('voice-label').textContent = `${profile.name} voice`;
  setOptions('language', ['English', profile.name], 'English');
  $('message').placeholder = {es:'Escribe aquí, o cuéntamelo en voz alta…',it:'Scrivi qui, oppure parla…',ru:'Напиши здесь или ответь вслух…',zh:'在这里输入，或者直接说出来……'}[code];
  $('message').lang = profile.locale;
  startScene(scene); loadVoices();
  if (typeof loadAccentLanguage === 'function') loadAccentLanguage();
  syncControls();
}
function requestTarget(code, country, city, level = practiceLevel) {
  $('practice-level').value = practiceLevel;
  const profile = config.languages[code];
  country = country || Object.keys(profile.countries)[0]; city = city || profile.countries[country][0];
  $('target-language').value = targetLanguage; $('target-country').value = targetCountry; $('target-city').value = targetCity;
  if (history.length > 1 || $('message').value.trim() || (typeof accentBlob !== 'undefined' && accentBlob)) {
    pendingTarget = [code, country, city, level]; $('reset-dialog').showModal();
  } else applyTarget(code, country, city, level);
}
$('target-language').onchange = () => requestTarget($('target-language').value);
$('target-country').onchange = () => requestTarget(targetLanguage, $('target-country').value);
$('target-city').onchange = () => requestTarget(targetLanguage, targetCountry, $('target-city').value);

$('practice-level').onchange = () => requestTarget(targetLanguage, targetCountry, targetCity, $('practice-level').value);
