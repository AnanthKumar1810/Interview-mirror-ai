'use strict';

const $ = (id) => document.getElementById(id);

const state = {
  live: false,
  session: null,
  question: null,
  nextQuestion: null,
  completed: false,
  answered: 0,
  language: 'en-IN',
  track: 'agentic',
  sttModel: 'prisma-v2.5',
  audio: null,
  objectUrl: null,
  mediaRecorder: null,
  stream: null,
  chunks: [],
  startedAt: 0,
  ticker: null,
  busy: false,
  recording: false,
  authRequired: false,
  accessToken: null,
  nextKind: 'core',
  nextReason: '',
  recordingWav: null,
  recordingUrl: null,

  // Hands-free realtime client
  realtimeClient: null,
  isHandsFree: false,
  providerTranscript: '',
  editedTranscript: '',
};

const SAMPLE = {
  agentic: 'I built a code-repair agent with Python and Docker. The problem was unreliable automated edits. I used restricted file tools, wrote regression tests and added human approval before publishing changes. In one local fixture, the updated code passed the maintained test. Broader repair reliability still needs more evaluation.',
  ai: 'I built a classification project with Python and PyTorch. I split the dataset into training and validation sets, checked class imbalance and evaluated recall and precision. I compared my model against a baseline and documented the results. I would next measure performance on new real-world data.',
  software: 'I fixed a bug that calculated the wrong invoice total. First I reproduced the failure in a unit test. Then I traced the calculation order, updated the smallest affected function and ran the complete test suite. The regression test passed and helped prevent the bug from returning.'
};

function toast(message, ok = false) {
  const el = $('toast');
  if (!el) return;
  el.textContent = message;
  el.className = `toast ${ok ? 'ok' : ''}`;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.hidden = true; }, 6500);
}

async function api(path, options = {}) {
  let res;
  try {
    const headers = new Headers(options.headers || {});
    if (state.accessToken) headers.set('Authorization', `Bearer ${state.accessToken}`);
    res = await fetch(path, { ...options, headers });
  } catch {
    throw new Error('Cannot reach the backend. Check that the server is running.');
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try {
      const obj = await res.json();
      detail = typeof obj.detail === 'string' ? obj.detail : detail;
    } catch {}
    throw new Error(detail);
  }
  return res;
}

const jsonOptions = (obj) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(obj)
});

function busy(on) {
  state.busy = on;
  if ($('start-btn')) $('start-btn').disabled = on || (state.authRequired && !state.accessToken);
  if ($('submit-btn')) $('submit-btn').disabled = on;
  if ($('record-btn')) $('record-btn').disabled = on && !state.recording;
}

function updateStepper(stage) {
  const stepper = $('interview-stepper');
  if (!stepper) return;
  const steps = stepper.children;
  for (let i = 0; i < steps.length; i++) {
    steps[i].classList.toggle('current', i === stage);
    steps[i].classList.toggle('done', i < stage);
    if (i === stage) steps[i].setAttribute('aria-current', 'step');
    else steps[i].removeAttribute('aria-current');
  }
}

function showView(name) {
  const progress = name === 'progress';
  $('studio-view').hidden = progress;
  $('progress-view').hidden = !progress;
  $('studio-nav').classList.toggle('active', !progress);
  $('progress-nav').classList.toggle('active', progress);
  $('studio-nav').toggleAttribute('aria-current', !progress);
  $('progress-nav').toggleAttribute('aria-current', progress);
  const breadcrumb = document.querySelector('.breadcrumb');
  if (breadcrumb) {
    breadcrumb.textContent = progress ? 'Workspace / Progress review' : 'Workspace / Hands-free interview';
  }
}

function appendText(parent, tag, value, className) {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  parent.appendChild(element);
  return element;
}

function setOrbStatus(statusText, stateClass) {
  const orb = $('orb');
  const caption = $('orb-caption');
  if (!orb || !caption) return;

  orb.className = 'orb';
  if (stateClass) orb.classList.add(stateClass);
  caption.textContent = statusText;
}

function setQuestion(question, number, kind = 'core', reason = '') {
  updateStepper(1);
  state.question = question;
  state.nextQuestion = null;

  if ($('question-text')) $('question-text').textContent = question;
  if ($('question-count')) $('question-count').textContent = `QUESTION ${String(number).padStart(2, '0')} / 03`;

  const tracks = { agentic: 'AGENTIC AI', ai: 'MACHINE LEARNING', software: 'SOFTWARE ENGINEERING' };
  if ($('question-track')) {
    $('question-track').textContent = kind === 'adaptive' ? `ADAPTIVE FOLLOW-UP · ${tracks[state.track] || state.track}` : (tracks[state.track] || state.track);
  }
  if ($('question-hint')) {
    $('question-hint').textContent = reason || 'Speak naturally. When you finish, the coach will pause and evaluate your answer.';
  }
  if ($('session-pill')) {
    $('session-pill').classList.add('active');
    $('session-pill').innerHTML = '<span></span> In progress';
  }
  if ($('live-transcript')) {
    $('live-transcript').innerHTML = '<em>Listening… your spoken answer will appear here in real time.</em>';
  }
  if ($('answer-counter')) $('answer-counter').textContent = '0 words';
}

// ── Hands-Free Realtime Pipeline ──────────────────────────────────────

async function startHandsFreeInterview() {
  if (state.isHandsFree) return;

  const consentBox = $('audio-consent');
  if (!consentBox || !consentBox.checked) {
    toast('Audio consent is required. Please check the consent box to begin.');
    consentBox?.focus();
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    toast('Microphone access requires HTTPS or localhost. Try Chrome or Firefox.');
    return;
  }

  stopPlayback();
  state.track = $('track').value;
  state.language = $('language').value;
  state.sttModel = $('stt-model') ? $('stt-model').value : 'prisma-v2.5';
  state.isHandsFree = true;
  busy(true);

  if ($('start-btn')) $('start-btn').textContent = 'Connecting…';

  try {
    // Unlock browser audio during the Start click, before network awaits.
    if (!state.realtimeClient && typeof RealtimeInterviewClient !== 'undefined') {
      state.realtimeClient = new RealtimeInterviewClient();
      _wireRealtimeEvents(state.realtimeClient);
    }
    state.realtimeClient.preparePlayback();

    // 1. Establish persistent session in backend SQLiteStore
    const githubRepo = $('github-repo') ? $('github-repo').value.trim() : null;
    const resumeText = $('resume-text') ? $('resume-text').value.trim() : null;
    const res = await api('/api/session', jsonOptions({
      track: state.track,
      language: state.language,
      github_repo: githubRepo || null,
      resume_text: resumeText || null
    }));
    const data = await res.json();
    state.session = data.session_id;
    state.answered = 0;
    state.completed = false;

    // 2. Connect WebSocket with authoritative session_id
    await state.realtimeClient.connect({
      track: state.track,
      language: state.language,
      stt_model: state.sttModel,
      consent: true,
      session_id: state.session,
      token: state.accessToken || null,
      endpointing_policy: 'adaptive',
      github_repo: githubRepo || null,
      resume_text: resumeText || null
    });

    // 3. Initialize AudioWorklet continuous microphone streaming
    await state.realtimeClient.startCapture();

    // 5. Update UI for active hands-free interview
    if ($('setup-card')) $('setup-card').hidden = true;
    if ($('end-interview-btn')) $('end-interview-btn').hidden = false;
    if ($('feedback-panel')) $('feedback-panel').hidden = true;
    if ($('report-summary')) $('report-summary').hidden = true;
    if ($('report-btn')) $('report-btn').hidden = true;
    if ($('restart-interview-btn')) $('restart-interview-btn').hidden = true;

    setQuestion(data.question, 1);
    setOrbStatus('Coach speaking question…', 'asking');
    toast('Interview started! Listen to the question, then speak your answer naturally.', true);

  } catch (err) {
    state.isHandsFree = false;
    if ($('setup-card')) $('setup-card').hidden = false;
    if ($('end-interview-btn')) $('end-interview-btn').hidden = true;
    toast(`Could not start hands-free interview: ${err.message}`);
    if (state.realtimeClient) {
      state.realtimeClient.disconnect();
    }
  } finally {
    busy(false);
    if ($('start-btn')) $('start-btn').innerHTML = 'Start interview <span>↗</span>';
  }
}

function _wireRealtimeEvents(client) {
  client.addEventListener('turn_state', (ev) => {
    const data = ev.detail || {};
    const stateName = data.state || '';
    const rawState = data.raw_state || '';

    if (rawState === 'asking') {
      setOrbStatus('Interviewer speaking…', 'asking');
      if (data.question) {
        setQuestion(data.question, data.question_number || (state.answered + 1));
      }
    } else if (rawState === 'listening') {
      setOrbStatus('Listening… (speak naturally)', 'listening');
      $('orb').classList.add('recording');
    } else if (rawState === 'transcribing' || rawState === 'review') {
      setOrbStatus('Processing answer…', 'thinking');
      $('orb').classList.remove('recording');
    } else if (rawState === 'feedback') {
      setOrbStatus('Feedback evaluated', '');
      $('orb').classList.remove('recording');
      if (data.feedback) {
        showFeedback(data.feedback);
      }
    } else if (rawState === 'completed' || stateName === 'Complete') {
      onInterviewComplete();
    }
  });

  client.addEventListener('transcript', (ev) => {
    const data = ev.detail || {};
    const text = data.text || '';
    if (!text) return;

    state.providerTranscript = text;
    const box = $('live-transcript');
    if (box) {
      box.textContent = text;
    }
    const words = text.trim().split(/\s+/).filter(Boolean).length;
    if ($('answer-counter')) {
      $('answer-counter').textContent = `${words} words (${text.length} chars)`;
    }
    if ($('answer-input')) {
      $('answer-input').value = text;
    }
  });

  client.addEventListener('reprompt', (ev) => {
    const data = ev.detail || {};
    toast(data.text || "Whenever you're ready, feel free to answer.", true);
  });

  client.addEventListener('barge_in', () => {
    toast('Coach paused. Listening to your answer…', true);
    setOrbStatus('Listening… (candidate speaking)', 'listening');
  });

  client.addEventListener('error', (ev) => {
    const err = ev.detail || {};
    toast(`Streaming error: ${err.message || 'Connection lost'}`);
  });

  client.addEventListener('disconnected', () => {
    if (state.isHandsFree && !state.completed) {
      toast('Streaming connection closed.');
    }
  });
}

async function onInterviewComplete() {
  state.completed = true;
  state.isHandsFree = false;

  if (state.realtimeClient) {
    state.realtimeClient.stopCapture();
    state.realtimeClient.stopTTS();
  }

  updateStepper(2);
  setOrbStatus('Practice interview complete!', '');
  if ($('orb')) $('orb').classList.remove('recording');
  if ($('session-pill')) $('session-pill').innerHTML = '<span></span> Completed';
  if ($('end-interview-btn')) $('end-interview-btn').hidden = true;
  if ($('report-btn')) $('report-btn').hidden = false;
  if ($('restart-interview-btn')) $('restart-interview-btn').hidden = false;

  try {
    await renderReportSummary();
    await populateCorrectionReview();
  } catch (err) {
    toast(`Could not load report summary: ${err.message}`);
  }

  toast('Interview complete! Review your practice report and transcripts below.', true);
}

function endInterviewEarly() {
  if (confirm('Are you sure you want to end the interview early? Your answers so far will be saved.')) {
    if (state.realtimeClient) {
      state.realtimeClient.endInterview();
    }
    onInterviewComplete();
  }
}

// ── Transcript Correction & Re-evaluation ─────────────────────────────

async function populateCorrectionReview() {
  const list = $('correction-answers-list');
  if (!list || !state.session) return;
  list.replaceChildren();

  try {
    const res = await api(`/api/report/${encodeURIComponent(state.session)}`);
    const data = await res.json();
    const answers = data.results || [];

    if (!answers.length) {
      appendText(list, 'p', 'No answers recorded for this session.');
      return;
    }

    answers.forEach((ans, idx) => {
      const container = document.createElement('div');
      container.className = 'correction-card';
      container.style.cssText = 'margin-bottom: 14px; padding: 10px; background: rgba(15, 23, 42, 0.6); border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);';

      appendText(container, 'strong', `Question ${idx + 1}: ${ans.question}`, 'd-block');

      const origText = ans.provider_transcript || ans.transcript || '';
      const origP = document.createElement('p');
      origP.style.cssText = 'font-size: 13px; color: #94a3b8; margin: 4px 0;';
      appendText(origP, 'strong', 'Original transcript:');
      origP.appendChild(document.createTextNode(` ${origText}`));
      container.appendChild(origP);

      const label = document.createElement('label');
      label.textContent = 'Corrected text (edit and re-score):';
      label.style.cssText = 'font-size: 12px; color: #cbd5e1; display: block; margin-top: 6px;';
      const textarea = document.createElement('textarea');
      textarea.rows = 2;
      textarea.style.cssText = 'width: 100%; font-size: 13px; margin: 4px 0 8px 0; padding: 6px; border-radius: 4px;';
      textarea.value = ans.edited_transcript || origText;

      const recomputeBtn = document.createElement('button');
      recomputeBtn.type = 'button';
      recomputeBtn.className = 'btn btn-secondary';
      recomputeBtn.style.cssText = 'font-size: 12px; padding: 4px 10px;';
      recomputeBtn.textContent = '↻ Recompute score for this answer';

      recomputeBtn.addEventListener('click', async () => {
        const corrected = textarea.value.trim();
        if (corrected.length < 3) {
          toast('Enter at least a short answer.');
          return;
        }
        try {
          recomputeBtn.disabled = true;
          recomputeBtn.textContent = 'Scoring…';
          const updateRes = await api(`/api/sessions/${encodeURIComponent(state.session)}/correct`, jsonOptions({
            question_index: idx,
            corrected_text: corrected
          }));
          await updateRes.json();
          await renderReportSummary();
          await populateCorrectionReview();
          toast(`Question ${idx + 1} re-evaluated successfully!`, true);
        } catch (err) {
          toast(`Correction failed: ${err.message}`);
        } finally {
          recomputeBtn.disabled = false;
          recomputeBtn.textContent = '↻ Recompute score for this answer';
        }
      });

      container.appendChild(label);
      container.appendChild(textarea);
      container.appendChild(recomputeBtn);
      list.appendChild(container);
    });
  } catch (err) {
    appendText(list, 'p', `Could not load answers: ${err.message}`);
  }
}

// ── Feedback & Report Rendering ───────────────────────────────────────

function buildItems(list, destination) {
  destination.replaceChildren();
  for (const item of list) {
    const li = document.createElement('li');
    li.textContent = item;
    destination.appendChild(li);
  }
}

function showFeedback(feedback) {
  if (!$('feedback-panel')) return;
  $('feedback-panel').hidden = false;
  $('coach-headline').textContent = 'Here is how you did.';
  $('coach-subtitle').textContent = 'Uncalibrated practice guidance based on transcript signals.';
  $('score-value').textContent = String(feedback.score);
  $('score-dial-label').textContent = String(feedback.score);
  $('score-dial').style.background = `conic-gradient(#7668e8 ${feedback.score}%, #eeeefe 0)`;

  const maxes = feedback.dimension_max || { relevance: 25, technical_coverage: 35, clarity: 20, evidence: 20 };
  const labels = {
    relevance: 'Relevance',
    technical_coverage: 'Concept coverage',
    clarity: 'Explanation clarity',
    evidence: 'Supporting detail'
  };

  $('rubric').replaceChildren();
  for (const [name, maximum] of Object.entries(maxes)) {
    const value = feedback.dimensions?.[name] || 0;
    const row = document.createElement('div');
    row.className = 'rubric-row';
    const label = document.createElement('span');
    label.className = 'rubric-name';
    label.textContent = labels[name] || name;
    const bar = document.createElement('div');
    bar.className = 'rubric-bar';
    const fill = document.createElement('div');
    fill.style.width = `${Math.min(100, (value / maximum) * 100)}%`;
    bar.appendChild(fill);
    const score = document.createElement('span');
    score.className = 'rubric-score';
    score.textContent = `${value}/${maximum}`;
    row.append(label, bar, score);
    $('rubric').append(row);
  }

  buildItems(feedback.strengths || [], $('strengths'));
  buildItems(feedback.improvements || [], $('improvements'));
  buildItems((feedback.risk_flags || []).map((f) => `${f.code}: ${f.explanation}`), $('risk-list'));
  $('risk-block').hidden = !(feedback.risk_flags || []).length;

  $('evidence-list').replaceChildren();
  for (const item of feedback.evidence_items || []) {
    const li = document.createElement('li');
    li.className = 'evidence-entry';
    const quote = document.createElement('blockquote');
    quote.textContent = `“${item.quote}”`;
    const reason = document.createElement('small');
    reason.textContent = item.observation;
    li.append(quote, reason);
    $('evidence-list').appendChild(li);
  }
  $('evidence-block').hidden = !(feedback.evidence_items || []).length;

  $('coverage-list').replaceChildren();
  for (const item of feedback.coverage || []) {
    const li = document.createElement('li');
    li.textContent = `${item.mentioned ? '✓ Mentioned' : '○ Not detected'}: ${item.concept}`;
    $('coverage-list').appendChild(li);
  }

  $('followup-text').textContent = feedback.follow_up || '';
  $('score-disclaimer').textContent = feedback.disclaimer || 'Uncalibrated practice guidance. Scores are heuristic indicators, not hiring assessments.';
  $('coach-method').textContent = 'Coach: uncalibrated practice guidance';
}

async function renderReportSummary() {
  if (!state.session) return;
  const res = await api(`/api/report/${encodeURIComponent(state.session)}`);
  const report = await res.json();

  $('report-summary').hidden = false;
  $('summary-score').textContent = `${report.average_score ?? '—'}/100`;
  $('stat-score').textContent = `${report.average_score ?? '—'}/100`;
  $('stat-answered').innerHTML = `${report.answered} <small>/ ${report.total_questions}</small>`;

  $('summary-metrics').replaceChildren();
  for (const [key, cap] of Object.entries(report.dimension_max || {})) {
    const mean = report.dimension_averages?.[key] ?? 0;
    const label = { relevance: 'Relevance', technical_coverage: 'Concept coverage', clarity: 'Clarity', evidence: 'Evidence' }[key] || key;
    const row = document.createElement('div');
    row.className = 'summary-metric';
    const top = document.createElement('div');
    top.className = 'summary-metric-label';
    const name = document.createElement('span');
    name.textContent = label;
    const value = document.createElement('strong');
    value.textContent = `${mean}/${cap}`;
    top.append(name, value);
    const track = document.createElement('div');
    track.className = 'summary-bar';
    const fill = document.createElement('div');
    fill.style.width = `${Math.max(0, Math.min(100, (100 * mean) / cap))}%`;
    track.appendChild(fill);
    row.append(top, track);
    $('summary-metrics').appendChild(row);
  }

  buildItems(
    report.review_priorities?.length ? report.review_priorities : ['All core concepts covered! Practice explaining design trade-offs and metrics.'],
    $('report-priorities')
  );

  // Render candidate profile & evaluated achievements if present
  const profileCard = $('report-candidate-profile');
  const profileContent = $('report-profile-content');
  if (profileCard && profileContent) {
    const prof = report.candidate_profile || {};
    const achs = report.achievements_evaluated || prof.achievements || [];
    const repo = report.github_repository_evaluated || prof.github_project || '';
    const edu = prof.education || [];
    const skills = prof.skills || [];

    if (achs.length || repo || edu.length || skills.length) {
      profileCard.hidden = false;
      profileContent.replaceChildren();

      if (repo) {
        const p = document.createElement('p');
        p.style.margin = '4px 0';
        appendText(p, 'strong', 'Tailored GitHub Project:');
        appendText(p, 'code', repo);
        profileContent.appendChild(p);
      }
      if (edu.length) {
        const p = document.createElement('p');
        p.style.margin = '4px 0';
        appendText(p, 'strong', 'Background & Education:');
        p.appendChild(document.createTextNode(` ${edu.join(' · ')}`));
        profileContent.appendChild(p);
      }
      if (skills.length) {
        const p = document.createElement('p');
        p.style.margin = '4px 0';
        appendText(p, 'strong', 'Demonstrated Skills:');
        p.appendChild(document.createTextNode(` ${skills.slice(0, 8).join(', ')}`));
        profileContent.appendChild(p);
      }
      if (achs.length) {
        const div = document.createElement('div');
        div.style.marginTop = '6px';
        div.innerHTML = `<strong>Evaluated Achievements &amp; Milestones:</strong>`;
        const ul = document.createElement('ul');
        ul.style.paddingLeft = '18px';
        ul.style.margin = '4px 0';
        achs.forEach(a => {
          const li = document.createElement('li');
          li.textContent = a;
          ul.appendChild(li);
        });
        div.appendChild(ul);
        profileContent.appendChild(div);
      }
    } else {
      profileCard.hidden = true;
    }
  }
}

async function downloadReport() {
  if (!state.session) return;
  try {
    const res = await api(`/api/report/${encodeURIComponent(state.session)}`);
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `interviewmirror-report-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (err) {
    toast(`Cannot download report: ${err.message}`);
  }
}

// ── REST Diagnostic & Fallback Operations ─────────────────────────────

function stopPlayback() {
  if (state.audio) { state.audio.pause(); state.audio = null; }
  if (state.objectUrl) { URL.revokeObjectURL(state.objectUrl); state.objectUrl = null; }
  if (state.realtimeClient) { state.realtimeClient.stopTTS(); }
}

async function listenRest() {
  if (!state.live || !state.question || state.busy) return;
  stopPlayback();
  busy(true);
  $('listen-btn').textContent = 'Generating…';
  try {
    const res = await api('/api/speak', jsonOptions({ text: state.question, language: state.language }));
    const blob = await res.blob();
    state.objectUrl = URL.createObjectURL(blob);
    state.audio = new Audio(state.objectUrl);
    await state.audio.play();
  } catch (err) {
    toast(err.message);
  } finally {
    $('listen-btn').textContent = '▷ Listen (REST)';
    busy(false);
  }
}

async function submitRestAnswer() {
  if (!state.session || !state.question || state.busy) return;
  const text = $('answer-input').value.trim();
  if (text.length < 3) {
    toast('Write at least a short answer.');
    return;
  }
  busy(true);
  $('submit-btn').textContent = 'Evaluating…';
  try {
    const res = await api('/api/answer', jsonOptions({ session_id: state.session, text }));
    const data = await res.json();
    state.answered = data.answered;
    state.completed = data.completed;
    state.nextQuestion = data.next_question;
    state.nextKind = data.next_question_kind || 'core';
    state.nextReason = data.next_question_reason || '';
    state.question = null;

    showFeedback(data.feedback);
    $('stat-answered').innerHTML = `${data.answered} <small>/ 3</small>`;
    $('stat-score').textContent = `${data.average_score}/100`;

    if (data.completed) {
      onInterviewComplete();
    } else {
      setQuestion(state.nextQuestion, state.answered + 1, state.nextKind, state.nextReason);
      toast('Feedback ready. Proceed to next question.', true);
    }
  } catch (err) {
    toast(err.message);
  } finally {
    $('submit-btn').innerHTML = 'Submit via REST <span>↗</span>';
    busy(false);
  }
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

function clearRecording() {
  if (state.recordingUrl) URL.revokeObjectURL(state.recordingUrl);
  state.recordingUrl = null;
  state.recordingWav = null;
  if ($('preview-btn')) $('preview-btn').disabled = true;
  if ($('save-record-btn')) $('save-record-btn').disabled = true;
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

async function toggleRestRecording() {
  if (state.recording) {
    if (state.mediaRecorder?.state === 'recording') state.mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    toast('Microphone recording requires a recent browser and localhost or HTTPS.');
    return;
  }
  stopPlayback();
  clearRecording();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
    state.stream = stream;
    state.chunks = [];
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(m => MediaRecorder.isTypeSupported(m));
    state.mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    state.mediaRecorder.ondataavailable = (e) => { if (e.data.size) state.chunks.push(e.data); };
    state.mediaRecorder.onerror = () => toast('The browser could not record audio.');
    state.mediaRecorder.onstop = async () => {
      clearInterval(state.ticker);
      state.recording = false;
      state.stream?.getTracks().forEach(t => t.stop());
      state.stream = null;
      if ($('record-btn')) {
        $('record-btn').classList.remove('recording');
        $('record-btn').innerHTML = '● Record (REST) <span id="record-counter">00:00</span>';
      }
      busy(true);
      try {
        if (!state.chunks.length) throw new Error('No audio captured.');
        const wav = await convertToWav(new Blob(state.chunks, { type: state.mediaRecorder.mimeType }));
        state.recordingWav = wav;
        state.recordingUrl = URL.createObjectURL(wav);
        if ($('preview-btn')) $('preview-btn').disabled = false;
        if ($('save-record-btn')) $('save-record-btn').disabled = false;

        const check = new FormData();
        check.append('audio', wav, 'candidate.wav');
        const checkResponse = await api('/api/audio/check', { method: 'POST', body: check });
        const result = await checkResponse.json();
        const diagEl = $('record-diagnostics');
        if (diagEl) {
          diagEl.hidden = false;
          diagEl.textContent = `Local audio check: ${result.duration_seconds}s · 16 kHz mono WAV · ${result.message}`;
        }
        if (result.possibly_silent) {
          toast('Microphone test detected very low input. Play it back before attempting transcription.');
        } else if (!state.live) {
          toast('Recording validated locally. No Gnani key: type the transcript for feedback.', true);
        } else {
          toast('Audio preflight check passed. Ready for REST or streaming.', true);
        }
      } catch (err) {
        toast(err.message);
      } finally {
        busy(false);
      }
    };
    state.mediaRecorder.start(250);
    state.recording = true;
    state.startedAt = Date.now();
    if ($('record-btn')) {
      $('record-btn').classList.add('recording');
      $('record-btn').innerHTML = '■ Stop recording <span id="record-counter">00:00</span>';
    }
    const tick = () => {
      const elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
      if ($('record-counter')) $('record-counter').textContent = `00:${String(elapsed).padStart(2, '0')}`;
      if (elapsed >= 28 && state.mediaRecorder?.state === 'recording') state.mediaRecorder.stop();
    };
    tick();
    state.ticker = setInterval(tick, 300);
  } catch (err) {
    state.recording = false;
    toast(`Microphone unavailable: ${err.message}`);
  }
}

// ── Initialization & Navigation ───────────────────────────────────────

async function init() {
  updateStepper(0);

  $('studio-nav').addEventListener('click', () => showView('studio'));
  $('progress-nav').addEventListener('click', () => { showView('progress'); loadProgress(); });
  $('progress-refresh').addEventListener('click', loadProgress);

  // Hands-free controls
  $('start-btn').addEventListener('click', startHandsFreeInterview);
  if ($('end-interview-btn')) $('end-interview-btn').addEventListener('click', endInterviewEarly);
  if ($('restart-interview-btn')) $('restart-interview-btn').addEventListener('click', () => location.reload());
  $('report-btn').addEventListener('click', downloadReport);

  // REST fallback controls
  $('listen-btn').addEventListener('click', listenRest);
  $('submit-btn').addEventListener('click', submitRestAnswer);
  $('example-btn').addEventListener('click', () => {
    $('answer-input').value = SAMPLE[state.track];
    toast('Synthetic answer inserted.');
  });
  if ($('record-btn')) $('record-btn').addEventListener('click', toggleRestRecording);
  if ($('preview-btn')) $('preview-btn').addEventListener('click', previewRecording);
  if ($('save-record-btn')) $('save-record-btn').addEventListener('click', downloadRecording);

  // Consent checkbox controls start button state
  const consentBox = $('audio-consent');
  if (consentBox) {
    consentBox.addEventListener('change', () => {
      $('start-btn').disabled = !consentBox.checked;
    });
    $('start-btn').disabled = !consentBox.checked;
  }

  // Load status
  try {
    const res = await api('/api/status');
    const data = await res.json();
    state.live = data.gnani_live;
    state.authRequired = !!data.auth_required;
    $('auth-panel').hidden = !state.authRequired;

    $('side-status').textContent = state.live ? 'Gnani API key active' : 'Local demo mode';
    $('side-mode').textContent = state.live ? 'Prisma STT + Timbre TTS streaming' : 'Local practice with diagnostic feedback';
    $('side-dot').classList.toggle('live', state.live);

    $('mode-banner').classList.toggle('live', state.live);
    $('mode-heading').textContent = state.live ? 'Voice streaming active — click Start to practice' : 'Local practice mode · microphone test available';
    $('mode-description').textContent = state.live
      ? 'Hands-free mode speaks questions and listens automatically using Gnani realtime streaming.'
      : 'Connect your GNANI_API_KEY for live streaming. Practice room works with simulated speech in demo mode.';
    $('mode-tag').textContent = state.live ? 'GNANI STREAMING' : 'DEMO MODE';
  } catch (err) {
    $('mode-heading').textContent = 'Backend is offline';
    $('mode-description').textContent = err.message;
  }
}

async function loadProgress() {
  const list = $('progress-list');
  list.replaceChildren();
  $('progress-detail').hidden = true;
  if (!state.authRequired || !state.accessToken) {
    $('progress-status').textContent = state.authRequired ? 'Sign in to see saved interviews.' : 'Account history is available when authentication is enabled.';
    return;
  }
  try {
    const data = await (await api('/api/my/sessions')).json();
    $('progress-status').textContent = data.sessions.length ? `${data.sessions.length} saved interviews.` : 'No saved interviews yet.';
  } catch (err) {
    $('progress-status').textContent = `Could not load: ${err.message}`;
  }
}

init();
