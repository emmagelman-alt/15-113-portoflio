// Accent recordings stay in memory; explicit assessment sends only the selected take.
let accentPhrases = [], accentReady = false, accentSupported = false, accentRecorder = null, accentStream = null;
let completedAccentPhrases = [];
let accentMode = 'pronunciation';
function accentScoreLabel() { return accentMode === 'phrase_match' ? 'phrase match' : 'pronunciation'; }
let accentTimer = null, accentBlob = null, accentObjectURL = null, accentDuration = 0;
function accentStatus(text, error = false) { $('accent-status').textContent = text; $('accent-status').classList.toggle('error', error); }
function syncAccentControls() {
  const other = busy || recording;
  $('accent-record').disabled = other || accentBusy || !accentPhrases.length || !navigator.mediaDevices || !window.MediaRecorder;
  $('accent-assess').disabled = other || accentBusy || accentRecording || !accentBlob || !accentReady;
  $('accent-listen').disabled = other || accentBusy || accentRecording || !accentPhrases.length;
  $('accent-phrase').disabled = other || accentBusy || accentRecording;
  $('accent-clear').disabled = accentBusy || accentRecording;
}
function clearAccentRecording() {
  $('accent-audio').pause(); $('accent-audio').removeAttribute('src'); $('accent-audio').load();
  if (accentObjectURL) URL.revokeObjectURL(accentObjectURL);
  accentObjectURL = null; accentBlob = null; accentDuration = 0;
  $('accent-audio').hidden = true; $('accent-clear').hidden = true; syncAccentControls();
}
function releaseAccentMic() { clearTimeout(accentTimer); if (accentStream) accentStream.getTracks().forEach(t => t.stop()); accentStream = null; }
function selectAccentPhrase(preserveFeedback = false) {
  clearAccentRecording(); if (window.speechSynthesis) speechSynthesis.cancel();
  const phrase = accentPhrases.find(p => p.id === $('accent-phrase').value);
  if (!phrase) return;
  $('accent-text').textContent = phrase.text; $('accent-focus').textContent = phrase.focus;
  if (!preserveFeedback) $('accent-results').replaceChildren(el('p', accentMode === 'phrase_match' ? 'Record the phrase to compare recognized words. This does not assess pronunciation, stress, or accent.' : accentSupported ? 'Record this phrase naturally. Feedback will focus on a few words to practice, not on eliminating your identity.' : 'Listen to the sample, record the phrase, and compare your recording by ear. Automatic pronunciation feedback is unavailable.', 'muted'));
  accentStatus('Read the whole phrase once. Tap Stop when you finish.');
}
$('accent-phrase').onchange = () => selectAccentPhrase();
$('accent-clear').onclick = () => { clearAccentRecording(); accentStatus('Recording discarded. Ready for a new attempt.'); };
$('accent-listen').onclick = () => { $('accent-audio').pause(); const phrase = accentPhrases.find(p => p.id === $('accent-phrase').value); if (phrase) speak(phrase.text); };
$('accent-audio').onplay = () => { if (window.speechSynthesis) speechSynthesis.cancel(); };
$('accent-record').onclick = async () => {
  if (accentRecording) { if (accentRecorder.state === 'recording') accentRecorder.stop(); return; }
  if (busy || recording || accentBusy) return;
  accentBusy = true; syncControls(); accentStatus('Waiting for microphone permission…');
  try {
    if (window.speechSynthesis) speechSynthesis.cancel();
    $('accent-audio').pause();
    accentStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(t => MediaRecorder.isTypeSupported(t));
    accentRecorder = new MediaRecorder(accentStream, mime ? { mimeType: mime } : undefined);
    const chunks = []; let failed = false; const started = performance.now();
    accentRecorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    accentRecorder.onerror = () => { failed = true; releaseAccentMic(); accentRecording = false; accentBusy = false; $('accent-record').textContent = '● Record my attempt'; syncControls(); accentStatus('Could not record. Check your microphone and try again.', true); };
    accentRecorder.onstop = () => {
      const duration = (performance.now() - started) / 1000;
      releaseAccentMic(); accentRecording = false; accentBusy = false; $('accent-record').textContent = '● Record my attempt';
      if (!failed) {
        clearAccentRecording(); accentDuration = duration;
        $('accent-results').replaceChildren(el('p', accentSupported ? 'New recording ready. Choose Get feedback to assess this attempt.' : 'New recording ready. Play it back and compare it with the sample phrase.', 'muted'));
        accentBlob = new Blob(chunks, { type: accentRecorder.mimeType || mime || 'audio/webm' });
        accentObjectURL = URL.createObjectURL(accentBlob); $('accent-audio').src = accentObjectURL; $('accent-audio').hidden = false; $('accent-clear').hidden = false;
        accentStatus(accentReady ? 'Listen to your attempt, then choose Get feedback or record again.' : accentSupported ? 'You can listen and compare now. Automatic feedback needs the assessment service configured below.' : 'Play your recording and compare it with the sample. Automatic assessment is unavailable for this language.');
      }
      syncControls();
    };
    accentRecorder.start(); accentRecording = true; accentBusy = false; syncControls();
    $('accent-record').textContent = '■ Stop recording'; accentStatus('Recording… read the whole phrase. Maximum 20 seconds.');
    accentTimer = setTimeout(() => { if (accentRecorder.state === 'recording') accentRecorder.stop(); }, 20000);
  } catch (error) {
    releaseAccentMic(); accentRecording = false; accentBusy = false; syncControls();
    accentStatus(error.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow it in your browser settings to practice.' : 'The microphone could not start. Try another browser or check your device.', true);
  }
};
async function accentWav(blob) {
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!Context || !window.OfflineAudioContext) throw new Error('Audio conversion is unavailable. Try a current Chrome or Safari browser.');
  const context = new Context(); let decoded;
  try { decoded = await context.decodeAudioData(await blob.arrayBuffer()); } finally { await context.close(); }
  if (decoded.duration < 0.5 || decoded.duration > 25) throw new Error('Record between half a second and 20 seconds of speech.');
  const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
  const source = offline.createBufferSource(); source.buffer = decoded; source.connect(offline.destination); source.start();
  const rendered = await offline.startRendering(); const samples = rendered.getChannelData(0);
  const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
  const text = (offset, value) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
  text(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); text(8, 'WAVE'); text(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, 'data'); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) { const sample = Math.max(-1, Math.min(1, samples[i])); view.setInt16(44 + i * 2, sample < 0 ? sample * 32768 : sample * 32767, true); }
  return new Blob([buffer], { type: 'audio/wav' });
}
function renderAccentFeedback(data) {
  if (data.mode === 'phrase_match') { renderPhraseMatch(data); return; }
  const panel = $('accent-results'); panel.replaceChildren();
  const scores = el('div', '', 'accent-scores');
  for (const [key, label] of [['accuracy', 'Pronunciation'], ['completeness', 'Sound coverage']]) {
    const score = el('div', '', 'accent-score'); score.append(el('strong', data.scores[key] === null ? '—' : `${data.scores[key]}`), el('span', label)); scores.append(score);
  }
  panel.append(scores, el('p', 'Provider estimates out of 100. Compare your own attempts; these are not a native-speaker rating.', 'small muted'));
  const words = el('div');
  for (const word of data.words) {
    const flagged = word.error !== 'None' || (word.accuracy !== null && word.accuracy < 80);
    const tag = el('span', `${word.word} · ${word.accuracy === null ? 'unscored' : Math.round(word.accuracy)}`, `accent-word${flagged ? ' review' : ''}`);
    tag.title = word.error === 'None' ? 'Pronunciation estimate' : word.error; words.append(tag);
  }
  panel.append(words);
  for (const tip of data.tips) { const card = el('div', '', 'accent-tip'); card.append(el('h4', tip.title), el('p', tip.text)); panel.append(card); }
  const details = el('details'); details.append(el('summary', 'Explore syllable feedback'));
  details.append(el('p', 'Expected and detected IPA are the service’s sound estimates, not a definitive diagnosis. Regional pronunciation differences can affect the comparison.', 'small muted'));
  for (const word of data.words) {
    details.append(el('h4', word.word));
    for (const syllable of word.syllables || []) {
      const label = syllable.missing ? ' · possibly missed' : syllable.extra ? ' · extra sound detected' : '';
      details.append(el('p', `${syllable.text}: expected /${syllable.expected_ipa || '—'}/ → detected /${syllable.detected_ipa || '—'}/${label}`));
    }
  }
  panel.append(details);
  panel.append(el('p', 'Noise or a misheard word can affect scores. Practice the highlighted words at a comfortable pace.', 'small muted'));
}
$('accent-assess').onclick = async () => {
  if (!accentBlob || !accentReady || accentBusy || accentRecording || busy || recording) return;
  accentBusy = true; syncControls(); $('accent-audio').pause(); if (window.speechSynthesis) speechSynthesis.cancel();
  accentStatus('Preparing your audio and checking this attempt…');
  try {
    if (accentDuration > 25) throw new Error('That recording is too long. Please make a new attempt under 20 seconds.');
    const wav = await accentWav(accentBlob); const form = new FormData(); form.append('audio', wav, 'practice.wav'); form.append('target_language', targetLanguage); form.append('phrase_id', $('accent-phrase').value);
    const data = await api('/api/accent/assess', { method: 'POST', body: form }); renderAccentFeedback(data); advanceAccentPhrase(data.mode === 'phrase_match' ? data.match_score : data.scores.accuracy);
  } catch (error) { accentStatus(error.message || 'Assessment failed. Your recording is still here so you can retry.', true); }
  finally { accentBusy = false; syncControls(); }
};
window.addEventListener('pagehide', () => { releaseAccentMic(); if (accentObjectURL) URL.revokeObjectURL(accentObjectURL); });
let accentLoadVersion = 0;
async function loadAccentLanguage() {
  const version = ++accentLoadVersion;
  completedAccentPhrases = [];
  accentReady = false; accentSupported = false; accentPhrases = []; clearAccentRecording();
  $('accent-phrase').replaceChildren(); $('accent-text').textContent = ''; $('accent-focus').textContent = '';
  $('accent-results').replaceChildren(); $('accent-setup').hidden = true;
  $('accent-language-tag').textContent = `${targetProfile().name} pronunciation`;
  $('accent-text').lang = targetProfile().locale;
  accentStatus('Loading practice phrases…'); syncControls();
  try {
    const data = await api(`/api/accent/config?target_language=${targetLanguage}`);
    if (version !== accentLoadVersion) return;
    accentMode = data.mode || 'pronunciation';
    $('accent-assess').textContent = accentMode === 'phrase_match' ? 'Get phrase match ↗' : 'Get feedback ↗';
    $('accent-language-tag').textContent = `${targetProfile().name} ${accentScoreLabel()}`;
    accentPhrases = data.phrases; accentReady = data.ready; accentSupported = data.supported;
    accentPhrases.forEach(phrase => { const option = el('option', phrase.title); option.value = phrase.id; $('accent-phrase').append(option); });
    $('accent-privacy').textContent = data.supported ? data.privacy : 'Your recording stays in this tab for playback. Automatic assessment is unavailable for this language. Discard or refresh to clear it.';
    $('assessment-scope').textContent = accentMode === 'phrase_match' ? 'Phrase match compares recognized words, not pronunciation. A 100% match does not mean perfect pronunciation. Transcription errors can affect the score.' : data.supported ? `Assessment: general ${targetProfile().name}. City-specific accent, fluency and intonation are not scored. Noise and recognition errors can affect results.` : 'Listening and recording practice only. Automatic pronunciation scores' + (targetLanguage === 'zh' ? ' and Mandarin tone scores' : '') + ' are unavailable.';
    if (!accentReady) { $('accent-setup').hidden = false; $('accent-setup').textContent = data.setup_message; }
    selectAccentPhrase(); updateAccentProgress(); syncControls();
  } catch (error) { if (version === accentLoadVersion) { accentStatus('Accent practice could not load. Try changing the language again or refresh.', true); syncControls(); } }
}

function updateAccentProgress() {
  $('accent-progress').textContent = accentSupported
    ? `${completedAccentPhrases.length} of ${accentPhrases.length} phrases above 95% this round. A ${accentScoreLabel()} score above 95% loads the next phrase automatically. Progress resets when you change practice settings or refresh.`
    : 'Choose any phrase to listen, record, and compare.';
}
function advanceAccentPhrase(accuracy) {
  const current = accentPhrases.find(p => p.id === $('accent-phrase').value);
  const result = accentProgression(accentPhrases, current?.id, accuracy, completedAccentPhrases);
  if (!result) { accentStatus(`Feedback is ready. Try this phrase again; score above 95% in ${accentScoreLabel()} to advance.`); return; }
  completedAccentPhrases = result.completed;
  $('accent-results').prepend(el('p', `Completed: “${current.text}” · ${accuracy}% ${accentScoreLabel()}.`, 'suggested'));
  if (result.nextId) {
    $('accent-phrase').value = result.nextId;
    selectAccentPhrase(true);
    if (result.roundComplete) completedAccentPhrases = [];
    accentStatus(result.roundComplete ? 'You completed every phrase! A new round is ready. Your last feedback is still shown.' : 'Above 95%—your next phrase is ready! Your previous feedback is still shown.');
  } else { clearAccentRecording(); accentStatus('You completed all available phrases. Choose a phrase to practice again.'); }
  updateAccentProgress();
}

function renderPhraseMatch(data) {
  const panel = $('accent-results'); panel.replaceChildren();
  const score = el('div', '', 'accent-score');
  score.append(el('strong', `${data.match_score}%`), el('span', 'Phrase match · not pronunciation'));
  panel.append(score, el('p', `Target: ${data.target}`), el('p', `Heard: ${data.transcript}`));
  panel.append(el('p', 'The score deducts word substitutions, omissions, and additions relative to the target length. Capitalization, punctuation, stress marks and е/ё differences are ignored. Speech recognition may correct pronunciation mistakes automatically.', 'small muted'));
  for (const item of data.differences) {
    panel.append(el('p', item.kind === 'missing' ? `Not heard: ${item.expected}` : item.kind === 'added' ? `Extra word heard: ${item.heard}` : `Expected “${item.expected}”; heard “${item.heard}”.`));
  }
  if (!data.differences.length) panel.append(el('p', 'All recognized words match the target.'));
  panel.append(el('p', 'These are transcript differences, not a diagnosis of sound errors. Listen to your recording before deciding what to practice.', 'small muted'));
}
