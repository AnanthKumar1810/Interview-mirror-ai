'use strict';

const $ = (id) => document.getElementById(id);
const state = { live: false, session: null, question: null, nextQuestion: null, completed: false,
  answered: 0, language: 'en-IN', track: 'agentic', audio: null, objectUrl: null,
  mediaRecorder: null, stream: null, chunks: [], startedAt: 0, ticker: null,
  busy: false, recording: false, authRequired: false, accessToken: null, nextKind: "core", nextReason: "", recordingWav: null, recordingUrl: null };
const SAMPLE = {
  agentic: 'I built a code-repair agent with Python and Docker. The problem was unreliable automated edits. I used restricted file tools, wrote regression tests and added human approval before publishing changes. In one local fixture, the updated code passed the maintained test. Broader repair reliability still needs more evaluation.',
  ai: 'I built a classification project with Python and PyTorch. I split the dataset into training and validation sets, checked class imbalance and evaluated recall and precision. I compared my model against a baseline and documented the results. I would next measure performance on new real-world data.',
  software: 'I fixed a bug that calculated the wrong invoice total. First I reproduced the failure in a unit test. Then I traced the calculation order, updated the smallest affected function and ran the complete test suite. The regression test passed and helped prevent the bug from returning.'
};

function toast(message, ok = false) {
  const el = $('toast');
  el.textContent = message; el.className = `toast ${ok ? 'ok' : ''}`; el.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.hidden = true; }, 6500);
}

async function api(path, options = {}) {
  let res;
  try {
    const headers = new Headers(options.headers || {});
    if (state.accessToken) headers.set('Authorization', `Bearer ${state.accessToken}`);
    res = await fetch(path, {...options, headers});
  }
  catch { throw new Error('Cannot reach the local backend. Check that uvicorn is running.'); }
  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try { const obj = await res.json(); detail = typeof obj.detail === 'string' ? obj.detail : detail; } catch {}
    throw new Error(detail);
  }
  return res;
}
const jsonOptions = (obj) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj) });
function busy(on) {
  state.busy = on;
  $('start-btn').disabled = on || state.recording || (state.authRequired && !state.accessToken);
  $('submit-btn').disabled = on || !state.session || !state.question || state.completed || state.recording;
  $('listen-btn').disabled = on || !state.live || !state.question || state.recording;
  $('record-btn').disabled = (on && !state.recording) || !state.question || state.completed;
  $('example-btn').disabled = on || !state.question || state.completed || state.recording;
  $('preview-btn').disabled = on || !state.recordingWav || state.recording;
  $('save-record-btn').disabled = on || !state.recordingWav || state.recording;
}
function updateStepper(stage) {
  const steps = $('interview-stepper').children;
  for (let i = 0; i < steps.length; i++) {
    steps[i].classList.toggle('current', i === stage);
    steps[i].classList.toggle('done', i < stage);
    if (i === stage) steps[i].setAttribute('aria-current', 'step');
    else steps[i].removeAttribute('aria-current');
  }
}
function showView(name) {
  const progress = name === 'progress';
  $('studio-view').hidden = progress; $('progress-view').hidden = !progress;
  $('studio-nav').classList.toggle('active', !progress);
  $('progress-nav').classList.toggle('active', progress);
  $('studio-nav').toggleAttribute('aria-current', !progress);
  $('progress-nav').toggleAttribute('aria-current', progress);
  document.querySelector('.breadcrumb').textContent = progress ? 'Workspace / Progress review' : 'Workspace / Interview studio';
}
function appendText(parent, tag, value, className) {
  const element = document.createElement(tag); element.textContent = value;
  if (className) element.className = className;
  parent.appendChild(element); return element;
}
async function showProgressReport(sessionId) {
  $('progress-detail').hidden = false;
  $('progress-detail').replaceChildren();
  appendText($('progress-detail'), 'p', 'Loading interview report…');
  try {
    const report = await (await api(`/api/report/${encodeURIComponent(sessionId)}`)).json();
    const detail = $('progress-detail'); detail.replaceChildren();
    appendText(detail, 'h3', `${report.track} · ${report.language}`);
    appendText(detail, 'p', `${report.answered} of ${report.total_questions} answers · Average practice score: ${report.average_score ?? '—'}/100`);
    appendText(detail, 'p', report.note, 'progress-note');
    for (const [index, item] of report.results.entries()) {
      const section = document.createElement('section'); section.className = 'progress-answer';
      appendText(section, 'h4', `Question ${index + 1}: ${item.question}`);
      appendText(section, 'p', item.transcript, 'progress-transcript');
      appendText(section, 'p', `Practice score: ${item.feedback.score}/100`);
      const list = document.createElement('ul');
      for (const tip of item.feedback.improvements || []) appendText(list, 'li', tip);
      section.appendChild(list); detail.appendChild(section);
    }
  } catch (error) {
    $('progress-detail').replaceChildren();
    appendText($('progress-detail'), 'p', `Could not load report: ${error.message}`);
  }
}
async function loadProgress() {
  const list = $('progress-list'); list.replaceChildren(); $('progress-detail').hidden = true;
  if (!state.authRequired || !state.accessToken) {
    $('progress-status').textContent = state.authRequired ? 'Sign in to see your saved interviews.' : 'Account history is available when authentication is enabled by the server operator.';
    return;
  }
  $('progress-status').textContent = 'Loading your saved interviews…';
  try {
    const data = await (await api('/api/my/sessions')).json();
    $('progress-status').textContent = data.sessions.length ? `${data.sessions.length} saved interview${data.sessions.length === 1 ? '' : 's'}. Select one to review its transcript and feedback.` : 'No saved interviews yet. Start a practice session in the studio.';
    for (const session of data.sessions) {
      const card = document.createElement('button'); card.type = 'button'; card.className = 'progress-card';
      appendText(card, 'strong', ({ai:'Machine Learning', agentic:'Agentic AI', software:'Software Engineering'}[session.track] || session.track));
      appendText(card, 'span', `${session.language} · ${session.answered}/3 answers · ${session.completed ? 'Completed' : 'In progress'}`);
      appendText(card, 'span', `Average practice score: ${session.average_score ?? '—'}/100`);
      card.addEventListener('click', () => showProgressReport(session.session_id));
      list.appendChild(card);
    }
  } catch (error) { $('progress-status').textContent = `Could not load history: ${error.message}`; }
}
function setQuestion(question, number, kind = "core", reason = "") {
  updateStepper(1);
  clearRecording();
  state.question = question; state.nextQuestion = null;
  $('question-text').textContent = question;
  $('question-count').textContent = `QUESTION ${String(number).padStart(2, '0')} / 03`;
  const tracks = { agentic: 'AGENTIC AI', ai: 'MACHINE LEARNING', software: 'SOFTWARE ENGINEERING' };
  $('question-track').textContent = kind === 'adaptive' ? `ADAPTIVE FOLLOW-UP · ${tracks[state.track]}` : tracks[state.track];
  $('question-hint').textContent = reason || 'Take a moment to think. Then explain your approach, what you did and what happened.';
  $('answer-input').value = ''; $('answer-input').disabled = false;
  $('answer-counter').textContent = '0 characters';
  $('session-pill').classList.add('active'); $('session-pill').innerHTML = '<span></span> In progress';
  $('orb-caption').textContent = 'Your answer starts here';
  $('orb-icon').textContent = '◉';
  $('record-diagnostics').textContent = '';
  $('record-diagnostics').hidden = true;
  $('next-btn').hidden = true;
  busy(false);
}
// Keep the start logic explicit: we only show the question returned by the API.
async function startInterview() {
  if (state.recording) return;
  stopPlayback();
  state.track = $('track').value; state.language = $('language').value;
  busy(true); $('start-btn').textContent = 'Starting…';
  try {
    const res = await api('/api/session', jsonOptions({ track: state.track, language: state.language }));
    const data = await res.json();
    state.session = data.session_id; state.answered = 0; state.completed = false;
    showView('studio');
    $('stat-answered').innerHTML = '0 <small>/ 3</small>'; $('stat-score').textContent = '—';
    $('feedback-panel').hidden = true; $('coach-headline').textContent = 'Your coach is ready.';
    $('coach-subtitle').textContent = 'Give your answer, then see evidence-based feedback.';
    $('report-btn').hidden = true; $('report-summary').hidden = true;
    setQuestion(data.question, 1);
    toast('Interview started. You can type an answer or use your microphone in live mode.', true);
  } catch (err) { toast(err.message); }
  finally { $('start-btn').innerHTML = 'Restart interview <span>↗</span>'; busy(false); }
}
function clearRecording() {
  if (state.recordingUrl) URL.revokeObjectURL(state.recordingUrl);
  state.recordingUrl = null;
  state.recordingWav = null;
  $('preview-btn').disabled = true;
  $('save-record-btn').disabled = true;
}
function previewRecording() {
  if (!state.recordingUrl) return;
  stopPlayback();
  state.audio = new Audio(state.recordingUrl);
  state.audio.play().catch(() => toast('Playback blocked by your browser. Try downloading the WAV.'));
}
function downloadRecording() {
  if (!state.recordingUrl) return;
  const a = document.createElement('a');
  a.href = state.recordingUrl;
  a.download = `interviewmirror-${state.language}-${new Date().toISOString().replace(/[:.]/g,'-')}.wav`;
  document.body.appendChild(a); a.click(); a.remove();
}
function stopPlayback() {
  if (state.audio) { state.audio.pause(); state.audio = null; }
  if (state.objectUrl) { URL.revokeObjectURL(state.objectUrl); state.objectUrl = null; }
}
async function listen() {
  if (!state.live || !state.question || state.busy || state.recording) return;
  stopPlayback(); busy(true); $('listen-btn').textContent = 'Generating voice…';
  try {
    const res = await api('/api/speak', jsonOptions({ text: state.question, language: state.language }));
    const blob = await res.blob();
    state.objectUrl = URL.createObjectURL(blob);
    state.audio = new Audio(state.objectUrl);
    await state.audio.play();
  } catch (err) { toast(err.message); }
  finally { $('listen-btn').textContent = '▷ Listen to question'; busy(false); }
}
function writeWav(samples, rate = 16000) {
  const bytes = new ArrayBuffer(44 + samples.length * 2), view = new DataView(bytes);
  const put = (at, str) => [...str].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  put(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); put(8, 'WAVE');
  put(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); put(36, 'data'); view.setUint32(40, samples.length * 2, true);
  samples.forEach((n, i) => { const s = Math.max(-1, Math.min(1, n)); view.setInt16(44 + i * 2, s < 0 ? s * 32768 : s * 32767, true); });
  return new Blob([bytes], { type: 'audio/wav' });
}
async function convertToWav(blob) {
  const context = new (window.AudioContext || window.webkitAudioContext)();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    const frames = decoded.length, channels = decoded.numberOfChannels;
    const mono = new Float32Array(frames);
    for (let c = 0; c < channels; c++) {
      const arr = decoded.getChannelData(c);
      for (let i = 0; i < frames; i++) mono[i] += arr[i] / channels;
    }
    const targetRate = 16000, length = Math.round(frames * targetRate / decoded.sampleRate);
    const sampled = new Float32Array(length);
    for (let i = 0; i < length; i++) {
      const x = i * decoded.sampleRate / targetRate, a = Math.floor(x), b = Math.min(a + 1, frames - 1), t = x - a;
      sampled[i] = mono[a] * (1 - t) + mono[b] * t;
    }
    return writeWav(sampled);
  } finally { await context.close(); }
}
async function toggleRecording() {
  if (state.recording) {
    if (state.mediaRecorder?.state === 'recording') state.mediaRecorder.stop();
    return;
  }
  if (!state.question || state.busy) return;
  if (!navigator.mediaDevices || !window.MediaRecorder) { toast('Microphone recording requires a recent browser and localhost or HTTPS.'); return; }
  stopPlayback(); clearRecording();
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
    state.stream = stream; state.chunks = [];
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(m => MediaRecorder.isTypeSupported(m));
    state.mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    state.mediaRecorder.ondataavailable = (e) => { if (e.data.size) state.chunks.push(e.data); };
    state.mediaRecorder.onerror = () => toast('The browser could not record audio. Try typing your answer.');
    state.mediaRecorder.onstop = async () => {
      clearInterval(state.ticker); state.recording = false;
      state.stream?.getTracks().forEach(t => t.stop()); state.stream = null;
      $('orb').classList.remove('recording'); $('record-btn').classList.remove('recording');
      $('orb-caption').textContent = 'Checking the recorded audio locally…';
      $('record-btn').innerHTML = '● Record answer <span id="record-counter">00:00</span>';
      busy(true);
      try {
        if (!state.chunks.length) throw new Error('The browser captured no audio. Check microphone permission and retry.');
        const wav = await convertToWav(new Blob(state.chunks, { type: state.mediaRecorder.mimeType }));
        if (wav.size > 4_000_000) throw new Error('Audio too large. Record a shorter answer.');
        state.recordingWav = wav;
        state.recordingUrl = URL.createObjectURL(wav);
        const check = new FormData(); check.append('audio', wav, 'candidate.wav');
        const checkResponse = await api('/api/audio/check', { method: 'POST', body: check });
        const result = await checkResponse.json();
        $('record-diagnostics').hidden = false;
        $('record-diagnostics').textContent = `Local audio check: ${result.duration_seconds}s · 16 kHz mono WAV · ${result.message}`;
        if (result.possibly_silent) {
          $('orb-caption').textContent = 'The recording is very quiet. Play it and check your microphone.';
          toast('Microphone test detected very low input. Play it back before attempting transcription.');
        } else if (state.live && !$('audio-consent').checked) {
          $('orb-caption').textContent = 'Recording saved locally. Consent required for provider transcription; type your answer instead.';
          toast('Gnani transcription skipped. Check audio consent if you wish to send the recording.');
        } else if (state.live) {
          $('orb-caption').textContent = 'Audio checked. Requesting Gnani Prisma transcription…';
          const form = new FormData(); form.append('audio', wav, 'candidate.wav'); form.append('language', $('stt-model').value === 'prisma-v3.0' ? 'indic-auto' : state.language); form.append('stt_model', $('stt-model').value); form.append('track', state.track); form.append('enhancement', $('noise-policy').value); form.append('consent', 'true');
          const transcriptResponse = await api('/api/transcribe', { method: 'POST', body: form });
          const data = await transcriptResponse.json();
          $('answer-input').value = data.transcript;
          $('answer-counter').textContent = `${data.transcript.length} characters`;
          $('orb-caption').textContent = `Gnani transcript ready (${data.audio_processing?.enhancement || 'off'} processing). Review before submitting.`;
          toast('Transcribed with Gnani Prisma. Review the text before submitting.', true);
        } else {
          $('orb-caption').textContent = 'Microphone test passed. Play the audio, then type your answer.';
          toast('Recording validated locally. No Gnani key: type the transcript for feedback.', true);
        }
      } catch (err) {
        $('orb-caption').textContent = 'Audio check or transcription failed. You can replay or type your answer.';
        toast(err.message);
      }
      finally { busy(false); }
    };
    state.mediaRecorder.start(250); state.recording = true; state.startedAt = Date.now();
    $('orb').classList.add('recording'); $('record-btn').classList.add('recording');
    $('orb-caption').textContent = 'Recording… speak naturally (max 28 seconds)';
    $('record-btn').innerHTML = '■ Stop recording <span id="record-counter">00:00</span>';
    busy(false);
    const tick = () => {
      const elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
      $('record-counter').textContent = `00:${String(elapsed).padStart(2, '0')}`;
      if (elapsed >= 28 && state.mediaRecorder?.state === 'recording') state.mediaRecorder.stop();
    };
    tick(); state.ticker = setInterval(tick, 300);
  } catch (err) { stream?.getTracks().forEach(t => t.stop()); state.recording = false; toast(`Microphone unavailable: ${err.message}`); busy(false); }
}
function buildItems(list, destination) {
  destination.replaceChildren();
  for (const item of list) { const li = document.createElement('li'); li.textContent = item; destination.appendChild(li); }
}
function showFeedback(feedback) {
  $('feedback-panel').hidden = false;
  $('coach-headline').textContent = 'Here is how you did.';
  $('coach-subtitle').textContent = 'Evidence-linked practice feedback from your submitted transcript.';
  $('score-value').textContent = String(feedback.score);
  $('score-dial-label').textContent = String(feedback.score);
  $('score-dial').style.background = `conic-gradient(#7668e8 ${feedback.score}%, #eeeefe 0)`;
  const maxes = feedback.dimension_max || { relevance: 25, technical_coverage: 35, clarity: 20, evidence: 20 };
  const labels = { relevance: 'Relevance', technical_coverage: 'Concept coverage', clarity: 'Explanation clarity', evidence: 'Supporting detail' };
  $('rubric').replaceChildren();
  for (const [name, maximum] of Object.entries(maxes)) {
    const value = feedback.dimensions[name] || 0;
    const row = document.createElement('div'); row.className = 'rubric-row';
    const label = document.createElement('span'); label.className = 'rubric-name'; label.textContent = labels[name] || name;
    const bar = document.createElement('div'); bar.className = 'rubric-bar';
    const fill = document.createElement('div'); fill.style.width = `${Math.min(100, value / maximum * 100)}%`; bar.appendChild(fill);
    const score = document.createElement('span'); score.className = 'rubric-score'; score.textContent = `${value}/${maximum}`;
    row.append(label, bar, score); $('rubric').append(row);
  }
  buildItems(feedback.strengths, $('strengths')); buildItems(feedback.improvements, $('improvements'));
  buildItems((feedback.risk_flags || []).map(flag => `${flag.code}: ${flag.explanation}`), $('risk-list'));
  $('risk-block').hidden = !(feedback.risk_flags || []).length;
  $('evidence-list').replaceChildren();
  for (const item of feedback.evidence_items || []) {
    const li = document.createElement('li'); li.className = 'evidence-entry';
    const quote = document.createElement('blockquote'); quote.textContent = `“${item.quote}”`;
    const reason = document.createElement('small'); reason.textContent = item.observation;
    li.append(quote, reason); $('evidence-list').appendChild(li);
  }
  $('evidence-block').hidden = !(feedback.evidence_items || []).length;
  $('coverage-list').replaceChildren();
  for (const item of feedback.coverage || []) {
    const li = document.createElement('li');
    li.textContent = `${item.mentioned ? '✓ Mentioned' : '○ Not detected'}: ${item.concept}`;
    $('coverage-list').appendChild(li);
  }
  $('followup-text').textContent = feedback.follow_up;
  $('score-disclaimer').textContent = feedback.disclaimer;
  $('coach-method').textContent = 'Coach: uncalibrated text-based practice rubric';
}

async function renderReportSummary() {
  const res = await api(`/api/report/${encodeURIComponent(state.session)}`);
  const report = await res.json();
  $('report-summary').hidden = false;
  $('summary-score').textContent = `${report.average_score ?? '—'}/100`;
  $('summary-metrics').replaceChildren();
  for (const [key, cap] of Object.entries(report.dimension_max || {})) {
    const mean = report.dimension_averages?.[key] ?? 0;
    const label = {relevance: 'Relevance', technical_coverage: 'Concept coverage', clarity: 'Clarity', evidence: 'Evidence'}[key] || key;
    const row = document.createElement('div'); row.className = 'summary-metric';
    const top = document.createElement('div'); top.className = 'summary-metric-label';
    const name = document.createElement('span'); name.textContent = label;
    const value = document.createElement('strong'); value.textContent = `${mean}/${cap}`;
    top.append(name, value);
    const track = document.createElement('div'); track.className = 'summary-bar';
    const fill = document.createElement('div'); fill.style.width = `${Math.max(0, Math.min(100, 100 * mean / cap))}%`;
    track.appendChild(fill); row.append(top, track); $('summary-metrics').appendChild(row);
  }
  buildItems(report.review_priorities?.length ? report.review_priorities : ['No obvious missing concepts flagged. Practice explaining trade-offs and results.'], $('report-priorities'));
}

async function submitAnswer() {
  if (!state.session || !state.question || state.busy || state.recording) return;
  const text = $('answer-input').value.trim();
  if (text.length < 3) { toast('Write at least a short answer before requesting feedback.'); return; }
  busy(true); $('submit-btn').textContent = 'Evaluating…';
  try {
    const res = await api('/api/answer', jsonOptions({ session_id: state.session, text }));
    const data = await res.json();
    state.answered = data.answered; state.completed = data.completed; state.nextQuestion = data.next_question;
    state.nextKind = data.next_question_kind || 'core'; state.nextReason = data.next_question_reason || '';
    state.question = null;
    updateStepper(2);
    showFeedback(data.feedback);
    $('stat-answered').innerHTML = `${data.answered} <small>/ 3</small>`;
    $('stat-score').textContent = `${data.average_score}/100`;
    $('answer-input').disabled = true;
    $('record-guidance').textContent = 'Answer saved locally for this session. Audio is not stored by the backend; save your WAV before moving to the next question if needed.';
    $('orb-caption').textContent = data.completed ? 'Practice complete — great work!' : 'Ready for the next question';
    $('next-btn').hidden = data.completed; $('report-btn').hidden = !data.completed; $('delete-session-btn').hidden = !data.completed;
    if (data.completed) {
      $('session-pill').innerHTML = '<span></span> Completed';
      $('question-hint').textContent = 'Three answers complete. Download your review to track your progress.';
      try { await renderReportSummary(); } catch (err) { toast('Interview complete, but the summary could not load: ' + err.message); }
      toast('Session complete! Your report is ready.', true);
    } else {
      toast('Feedback ready. Review it, then continue.', true);
    }
  } catch (err) { toast(err.message); }
  finally { $('submit-btn').innerHTML = 'Get feedback <span>↗</span>'; busy(false); }
}
function nextQuestion() { if (state.nextQuestion) setQuestion(state.nextQuestion, state.answered + 1, state.nextKind, state.nextReason); }
async function downloadReport() {
  if (!state.session) return;
  try {
    const res = await api(`/api/report/${encodeURIComponent(state.session)}`);
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href = url; a.download = `interviewmirror-report-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (err) { toast(err.message); }
}
async function signIn(action) {
  const email = $('auth-email').value.trim(), password = $('auth-password').value;
  if (!email || password.length < 12) { toast('Enter your email and password (at least 12 characters).'); return; }
  try {
    const response = await api(`/api/auth/${action}`, jsonOptions({email, password}));
    const result = await response.json();
    state.accessToken = result.access_token;
    $('auth-password').value = '';
    $('auth-fields').hidden = true; $('auth-signed-in').hidden = false;
    $('auth-status-text').textContent = `Signed in as ${email}. Sessions are saved on the server.`;
    busy(false); toast('Signed in. You can start or resume an interview.', true);
    if (!$('progress-view').hidden) await loadProgress();
  } catch (error) { toast(error.message); }
}
async function restoreSession() {
  try {
    const res = await api('/api/my/sessions'); const history = await res.json();
    if (!history.sessions?.length) { toast('No saved sessions to resume.'); return; }
    const latest = history.sessions[0];
    const info = await (await api(`/api/sessions/${encodeURIComponent(latest.session_id)}`)).json();
    state.session = latest.session_id; state.track = info.track; state.language = info.language;
    state.answered = info.answered; state.completed = info.completed;
    $('track').value = info.track; $('language').value = info.language;
    $('stat-answered').innerHTML = `${info.answered} <small>/ 3</small>`;
    state.nextQuestion = null;
    if (info.completed) {
      state.question = null;
      updateStepper(2);
      $('question-text').textContent = 'Interview completed';
      $('report-btn').hidden = false; $('delete-session-btn').hidden = false;
      await renderReportSummary();
      $('stat-score').textContent = $('summary-score').textContent;
      busy(false);
    } else {
      setQuestion(info.current_question, info.answered + 1);
      $('feedback-panel').hidden = true;
    }
    toast('Saved session restored from SQLite.', true);
  } catch (error) { toast('Could not restore session: ' + error.message); }
}
async function init() {
  updateStepper(0);
  $('studio-nav').addEventListener('click', () => showView('studio'));
  $('progress-nav').addEventListener('click', () => { showView('progress'); loadProgress(); });
  $('progress-refresh').addEventListener('click', loadProgress);
  $('auth-login-btn').addEventListener('click', () => signIn('login'));
  $('auth-register-btn').addEventListener('click', () => signIn('register'));
  $('auth-restore-btn').addEventListener('click', restoreSession);
  $('auth-logout-btn').addEventListener('click', async () => {
    try { await api('/api/auth/logout', {method:'POST'}); }
    catch (error) { toast(error.message); return; }
    state.accessToken = null; state.session = null; state.question = null;
    $('auth-fields').hidden = false; $('auth-signed-in').hidden = true;
    $('auth-status-text').textContent = 'Signed out. Sign in to access your saved sessions.';
    if (!$('progress-view').hidden) loadProgress();
    busy(false); toast('Signed out.', true);
  });
  $('start-btn').addEventListener('click', startInterview);
  $('listen-btn').addEventListener('click', listen);
  $('record-btn').addEventListener('click', toggleRecording);
  $('preview-btn').addEventListener('click', previewRecording);
  $('save-record-btn').addEventListener('click', downloadRecording);
  $('submit-btn').addEventListener('click', submitAnswer);
  $('next-btn').addEventListener('click', nextQuestion);
  $('report-btn').addEventListener('click', downloadReport);
  $('delete-session-btn').addEventListener('click', async () => {
    if (!state.session) return;
    try { await api(`/api/session/${encodeURIComponent(state.session)}`, {method: 'DELETE'}); location.reload(); }
    catch (err) { toast('Cannot delete session: ' + err.message); }
  });
  $('answer-input').addEventListener('input', () => { $('answer-counter').textContent = `${$('answer-input').value.length} characters`; });
  $('example-btn').addEventListener('click', () => { $('answer-input').value = SAMPLE[state.track]; $('answer-counter').textContent = `${$('answer-input').value.length} characters`; toast('Synthetic example inserted; replace it with your own answer for real practice.'); });
  try {
    const res = await api('/api/status'), data = await res.json(); state.live = data.gnani_live;
    state.authRequired = !!data.auth_required;
    $('auth-panel').hidden = !state.authRequired;
    busy(false);
    const neural = $('noise-policy').querySelector('option[value=deepfilter3]');
    if (neural && data.neural_enhancement_dependency_present) { neural.hidden = false; neural.disabled = false; }
    $('side-status').textContent = state.live ? 'Gnani API key configured' : 'Local demo mode';
    $('side-mode').textContent = state.live ? 'Try Prisma + Timbre with a live API call' : 'Local recording and interview practice';
    $('side-dot').classList.toggle('live', state.live);
    $('mode-banner').classList.toggle('live', state.live);
    $('mode-heading').textContent = state.live ? 'Voice API key configured — test a live call' : 'Local practice · microphone test available';
    $('mode-description').textContent = state.live ? 'Your key is loaded, but access is not yet verified. Record a short answer or listen to a question to test the live provider. Calls use Gnani credits.' : 'Record and replay a short answer locally without credits; type its transcript for feedback. Add your GNANI_API_KEY in .env to enable real Gnani STT and TTS.';
    $('mode-tag').textContent = state.live ? 'KEY LOADED (UNVERIFIED)' : 'NO API KEY';
    $('record-guidance').textContent = state.live ? 'Record up to 28 seconds. Audio format is checked locally before a paid Prisma call.' : 'Record up to 28 seconds to test your microphone. Replay/save WAV; manually type your answer until Gnani is configured.';
  } catch (err) { $('mode-heading').textContent = 'Backend is offline'; $('mode-description').textContent = err.message; }
}
init();


