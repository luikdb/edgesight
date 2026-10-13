/* EdgeSight web client: camera, mic and speakers live in the browser; all AI runs on the local server. */
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const S = { hazards: false, find: null, history: [], last: '', busy: false, hfov: 70, pathHalf: 18, fps: 0, started: false, demo: null };
const BUDGET = { detector: 50, stt: 2000, ocr: 1500, vlm: 2000, tts: 600 }; // our own targets, in ms

/* ---------------- preferences ---------------- */
const CHECKS = ['rot', 'mir', 'sonar', 'earcons', 'caps', 'boxes'];
function loadPrefs() {
  let p = {};
  try { p = JSON.parse(localStorage.getItem('edgesight') || '{}'); } catch (e) {}
  $('rot').checked = p.rot ?? true; // the demo webcam is mounted upside down
  CHECKS.filter(k => k !== 'rot' && k in p).forEach(k => $(k).checked = p[k]);
  if (p.model) $('model').value = p.model;
  S.voicePref = p.voice;
  S.focusPref = p.focus || null;
  S.hazardsPref = !!p.hazards; // off unless the user turned it on
  document.body.classList.toggle('details', !!p.details);
}
function savePrefs() {
  const p = { focus: S.focusPref, hazards: S.hazards, model: $('model').value, voice: $('voice').value || S.voicePref, details: document.body.classList.contains('details') };
  CHECKS.forEach(k => p[k] = $(k).checked);
  try { localStorage.setItem('edgesight', JSON.stringify(p)); } catch (e) {}
}

/* ---------------- camera ---------------- */
const cam = $('cam'), ov = $('overlay'), octx = ov.getContext('2d'), grabC = document.createElement('canvas');
const demoName = new URLSearchParams(location.search).get('demo'); // ?demo=bus.jpg uses a still image as the camera
async function startCam(id) {
  if (demoName) {
    const im = new Image(); im.className = 'demoimg';
    await new Promise(res => { im.onload = im.onerror = res; im.src = '/demo/' + encodeURIComponent(demoName); });
    cam.hidden = true; cam.after(im); S.demo = im;
    return;
  }
  try {
    if (cam.srcObject) cam.srcObject.getTracks().forEach(t => t.stop());
    const size = { width: { ideal: 1280 }, height: { ideal: 720 } };
    cam.srcObject = await navigator.mediaDevices.getUserMedia({ video: id ? { deviceId: { exact: id }, ...size } : size });
    await cam.play().catch(() => {});
    const devs = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput');
    const cur = cam.srcObject.getVideoTracks()[0].getSettings().deviceId;
    $('camsel').innerHTML = devs.map((d, i) => `<option value="${d.deviceId}" ${d.deviceId === cur ? 'selected' : ''}>${esc(d.label || 'Camera ' + (i + 1))}</option>`).join('');
    $('nocam').hidden = true;
  } catch (e) {
    $('nocam').hidden = false;
    $('nocamtxt').textContent = `${e.name}. Plug in a camera, allow access and reload.`;
  }
}
function applyXf() { cam.style.transform = `scale(${$('mir').checked ? -1 : 1},1) rotate(${$('rot').checked ? 180 : 0}deg)`; }
function grab(maxW) {
  const src = S.demo || cam, vw = src.naturalWidth || src.videoWidth, vh = src.naturalHeight || src.videoHeight;
  if (!vw) return null;
  const s = Math.min(1, maxW / vw);
  grabC.width = Math.round(vw * s); grabC.height = Math.round(vh * s);
  const c = grabC.getContext('2d');
  c.save(); c.translate(grabC.width / 2, grabC.height / 2);
  if (!S.demo && $('rot').checked) c.rotate(Math.PI);
  if (!S.demo && $('mir').checked) c.scale(-1, 1);
  c.drawImage(src, -grabC.width / 2, -grabC.height / 2, grabC.width, grabC.height);
  c.restore();
  return grabC;
}
const toBlob = (cv, q) => new Promise(r => cv.toBlob(r, 'image/jpeg', q));
const toB64 = (cv, q) => cv.toDataURL('image/jpeg', q).split(',')[1];

/* ---------------- live detection loop (only runs when something needs it) ---------------- */
async function detectLoop() {
  let frames = 0, t0 = performance.now();
  for (;;) {
    if (!S.hazards && !S.find && !$('boxes').checked) {
      octx.clearRect(0, 0, ov.width, ov.height); S.fps = 0; $('fps').textContent = 'idle'; $('m-fps').textContent = 'idle';
      await sleep(400); continue;
    }
    const cv = grab(512); // the detector works at 416 px, so a larger upload only costs encode time
    if (!cv) { await sleep(300); continue; }
    try {
      const r = await fetch(`/api/detect?hazards=${S.hazards ? 1 : 0}`, { method: 'POST', body: await toBlob(cv, 0.65) });
      const j = await r.json();
      if (j.error) throw new Error(j.error);
      onDetect(j);
    } catch (e) { await sleep(600); }
    frames++;
    const now = performance.now();
    if (now - t0 >= 1000) {
      S.fps = frames * 1000 / (now - t0); frames = 0; t0 = now;
      $('fps').textContent = `${S.fps.toFixed(0)} fps`; $('m-fps').textContent = `${S.fps.toFixed(0)} fps`;
    }
    await sleep(document.hidden ? 500 : 10);
  }
}
function onDetect(j) {
  $('detms').textContent = `${j.ms.toFixed(0)} ms`;
  $('objcount').textContent = `${j.dets.length} object${j.dets.length === 1 ? '' : 's'}`;
  pulse('detector');
  draw(j);
  if (j.alert && S.hazards) onAlert(j.alert);
  if (j.guide) { speech.say(j.guide, 'guide'); banner(j.guide, 2200); feedNote('find', j.guide); }
  if (j.find !== S.find) { S.find = j.find; updateFindUI(); }
  sonar.target = j.target;
}
function onAlert(a) {
  earcon(a.level, a.angle);
  speech.say(a.text, a.level);
  banner(a.text, 2400);
  feedNote('alert', a.text);
  $('srlive').textContent = a.text;
}

/* ---------------- overlay: tape labels stuck to objects ---------------- */
const dirWord = a => Math.abs(a) <= 8 ? 'ahead' : a < 0 ? 'left' : 'right';
function draw(j) {
  const dpr = devicePixelRatio || 1, W = ov.clientWidth, H = ov.clientHeight;
  if (ov.width !== Math.round(W * dpr) || ov.height !== Math.round(H * dpr)) { ov.width = Math.round(W * dpr); ov.height = Math.round(H * dpr); }
  octx.setTransform(dpr, 0, 0, dpr, 0, 0);
  octx.clearRect(0, 0, W, H);
  const showBoxes = $('boxes').checked;
  if (!showBoxes && !j.find) return;
  const [fw, fh] = j.frame, s = Math.min(W / fw, H / fh), ox = (W - fw * s) / 2, oy = (H - fh * s) / 2;

  octx.font = '600 12.5px "Hanken Grotesk", system-ui, sans-serif';
  for (const d of (showBoxes ? j.dets : [])) {
    const x1 = ox + d.box[0] * s, y1 = oy + d.box[1] * s, x2 = ox + d.box[2] * s, y2 = oy + d.box[3] * s;
    const lvl = S.hazards ? d.level : 'info';
    const dot = lvl === 'danger' ? '#ff5d5d' : lvl === 'warn' ? '#ffc24a' : '#ffffff';
    octx.strokeStyle = lvl === 'info' ? 'rgba(255,255,255,.7)' : dot; octx.lineWidth = 1.5;
    rrect(x1, y1, x2 - x1, y2 - y1, 9); octx.stroke();
    const text = `${d.cls}  ·  ${dirWord(d.angle)}`;
    const w = octx.measureText(text).width + 30, h = 24, y = y1 > h + 8 ? y1 - h - 6 : y1 + 6, x = Math.max(4, x1);
    octx.fillStyle = 'rgba(10,11,14,.88)'; rrect(x, y, w, h, 12); octx.fill();
    octx.fillStyle = dot; octx.beginPath(); octx.arc(x + 12, y + h / 2, 3.5, 0, Math.PI * 2); octx.fill();
    octx.fillStyle = '#eceef2'; octx.fillText(text, x + 22, y + 16);
  }
  if (j.target) { // find mode: ring on the target
    const t = j.target, cx = ox + (t.box[0] + t.box[2]) / 2 * s, cy = oy + (t.box[1] + t.box[3]) / 2 * s;
    octx.strokeStyle = 'rgba(255,255,255,.9)'; octx.lineWidth = 3;
    octx.beginPath(); octx.arc(cx, cy, 22, 0, Math.PI * 2); octx.stroke();
    octx.strokeStyle = '#6ea2ff'; octx.lineWidth = 2;
    octx.beginPath(); octx.arc(cx, cy, 27, 0, Math.PI * 2); octx.stroke();
  }
}
function rrect(x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  octx.beginPath(); octx.moveTo(x + r, y); octx.arcTo(x + w, y, x + w, y + h, r); octx.arcTo(x + w, y + h, x, y + h, r);
  octx.arcTo(x, y + h, x, y, r); octx.arcTo(x, y, x + w, y, r); octx.closePath();
}

/* ---------------- audio: tones + find sonar ---------------- */
let actx = null;
function ac() {
  if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
  if (actx.state === 'suspended') actx.resume();
  return actx;
}
function tone(freq, dur, { pan = 0, type = 'sine', gain = 0.16, when = 0 } = {}) {
  if (!actx) return;
  const a = actx, t = a.currentTime + when, o = a.createOscillator(), g = a.createGain(), p = a.createStereoPanner();
  o.type = type; o.frequency.value = freq; p.pan.value = Math.max(-1, Math.min(1, pan));
  g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(gain, t + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(p).connect(a.destination); o.start(t); o.stop(t + dur + 0.03);
}
function earcon(level, angle) {
  if (!$('earcons').checked) return;
  const pan = angle / 35;
  if (level === 'danger') [0, .13, .26].forEach(w => tone(1250, .08, { pan, type: 'square', gain: .1, when: w }));
  else tone(760, .14, { pan, gain: .15 });
}
const sonar = {
  target: null, next: 0,
  tick() {
    requestAnimationFrame(() => this.tick());
    if (!S.find || !$('sonar').checked || !actx) return;
    const now = performance.now();
    if (now < this.next) return;
    const t = this.target;
    if (!t) { tone(300, .05, { gain: .05 }); this.next = now + 1300; return; }
    const centered = Math.abs(t.angle) < 6, d = t.distance ?? 1.5;
    tone(centered ? 1320 : 480 + 520 * (1 - Math.min(1, Math.abs(t.angle) / 35)), .06, { pan: t.angle / 30, gain: .13 });
    if (centered) tone(1760, .05, { gain: .09, when: .08 });
    this.next = now + Math.max(120, Math.min(900, d * 320)); // closer target, faster ticks (distance is never shown)
  },
};

/* ---------------- speech output: priority queue ---------------- */
const speech = (() => {
  const audio = new Audio(), cache = new Map();
  let queue = [], playing = null;
  const rank = k => ({ danger: 3, warn: 2, guide: 1 }[k] || 0);
  function wav(text) {
    const voice = $('voice').value, key = voice + '|' + text;
    if (cache.has(key)) return cache.get(key);
    const p = fetch('/api/tts', { method: 'POST', body: JSON.stringify({ text, voice: voice || undefined }) })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).error); return URL.createObjectURL(await r.blob()); });
    if (text.length < 90) { cache.set(key, p); p.catch(() => cache.delete(key)); } // short phrases repeat; keep them instant
    return p;
  }
  function say(text, kind = 'answer') {
    if (!text) return;
    const item = { text, kind, t: performance.now(), url: wav(text) };
    if (kind === 'danger') { queue = queue.filter(q => q.kind === 'answer'); stopCurrent(); queue.unshift(item); }
    else if (rank(kind)) {
      if (queue.some(q => q.text === text) || playing?.text === text) return;
      const i = queue.findIndex(q => rank(q.kind) < rank(kind));
      i < 0 ? queue.push(item) : queue.splice(i, 0, item);
    } else queue.push(item);
    pump();
  }
  async function pump() {
    if (playing || !queue.length) return;
    const item = queue.shift();
    if (item.kind !== 'answer' && performance.now() - item.t > 4000) return pump(); // stale alert
    playing = item;
    try {
      audio.src = await item.url;
      if (playing !== item) return;
      pulse('tts', 600);
      await audio.play();
      await new Promise(res => { audio.onended = audio.onpause = res; });
    } catch (e) { console.warn('tts', e); }
    if (playing === item) playing = null;
    pump();
  }
  function stopCurrent() { if (playing) { playing = null; audio.pause(); } }
  function stopAll() { queue = []; stopCurrent(); }
  return { say, stopAll };
})();

/* ---------------- voice input: hold to talk ---------------- */
let rec = null, chunks = [], recStream = null, downAt = 0, meterOn = false;
function meter(stream) {
  const src = ac().createMediaStreamSource(stream), an = ac().createAnalyser(); an.fftSize = 512; src.connect(an);
  const buf = new Uint8Array(an.fftSize); meterOn = true; let lvl = 0;
  (function loop() {
    if (!meterOn) { $('talk').style.setProperty('--lvl', 0); src.disconnect(); return; }
    an.getByteTimeDomainData(buf); let sum = 0;
    for (const v of buf) sum += (v - 128) * (v - 128);
    lvl += (Math.min(1, Math.sqrt(sum / buf.length) / 40) - lvl) * 0.3;
    $('talk').style.setProperty('--lvl', lvl.toFixed(3)); requestAnimationFrame(loop);
  })();
}
async function startTalk() {
  if (rec || S.busy) return;
  ac(); speech.stopAll();
  try { recStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
  catch (e) { feedNote('alert', `Microphone unavailable (${e.name})`); return; }
  chunks = []; rec = new MediaRecorder(recStream); meter(recStream);
  rec.ondataavailable = e => e.data.size && chunks.push(e.data);
  rec.onstop = onRecStop;
  rec.start();
  tone(880, .06, { gain: .07 });
  $('talk').classList.add('rec'); $('talk').querySelector('.lbl').textContent = 'Listening';
  $('listenpill').hidden = false; activate('stt', true);
}
function stopTalk() {
  if (rec && rec.state === 'recording') { rec.stop(); tone(620, .06, { gain: .07 }); }
}
async function onRecStop() {
  meterOn = false;
  recStream.getTracks().forEach(t => t.stop());
  const blob = new Blob(chunks, { type: rec.mimeType });
  rec = null;
  $('talk').classList.remove('rec'); $('talk').querySelector('.lbl').textContent = 'Hold to talk';
  $('listenpill').hidden = true;
  if (blob.size < 1500) { activate('stt', false); return; }
  try {
    const j = await (await fetch('/api/stt', { method: 'POST', body: blob })).json();
    activate('stt', false);
    if (j.error) throw new Error(j.error);
    if (!j.text) { speech.say("I didn't catch that."); showCaption('es', "I didn't catch that."); return; }
    command(j.text, { stt: j.ms });
  } catch (e) { activate('stt', false); feedNote('alert', 'Speech-to-text error: ' + e.message); }
}

/* ---------------- commands ---------------- */
async function command(text, extra = {}) {
  text = text.trim();
  if (!text || S.busy) return;
  ac();
  S.busy = true; setBusy(true);
  showCaption('you', text);
  const card = addCard(text);
  const cv = grab(1280), image = cv ? toB64(cv, 0.85) : '';
  try {
    const r = await fetch('/api/command', { method: 'POST', body: JSON.stringify({ text, image, model: $('model').value, history: S.history, hazards: S.hazards }) });
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    onResult(j, card, extra);
  } catch (e) {
    fillCard(card, { intent: 'error', say: 'Sorry, something went wrong: ' + e.message });
    speech.say('Sorry, something went wrong.');
  }
  S.busy = false; setBusy(false);
}
function onResult(j, card, extra) {
  if (j.intent === 'repeat') { fillCard(card, { intent: 'repeat', say: S.last || 'Nothing to repeat yet.' }); speech.say(S.last || 'Nothing to repeat yet.'); return; }
  if ('hazards' in j) setHazards(j.hazards);
  if ('find' in j) { S.find = j.find; updateFindUI(); }
  if (j.ocr_ms != null) pulse('ocr', 1200);
  if (j.vlm_ms != null) pulse('vlm', 1200);
  fillCard(card, { ...j, stt: extra.stt });
  if (['ask', 'describe'].includes(j.intent) || (j.intent === 'find' && !j.find)) {
    S.history.push({ role: 'user', content: j.heard }, { role: 'assistant', content: j.say });
    S.history = S.history.slice(-12);
  }
  if (j.say) { S.last = j.say; showCaption('es', j.say); speech.say(j.say); $('srlive').textContent = j.say; }
}

/* ---------------- conversation ---------------- */
const LABEL = { ask: 'Ask', describe: 'Describe', read: 'Read', read_label: 'Label', find: 'Find', stop: 'Stop', help: 'Help',
  safety: 'Safety', hazards: 'Hazards', repeat: 'Repeat', none: 'Heard', error: 'Error' };
const TAPE = { read: '', read_label: '', find: 'blue', error: 'red', alert: 'red' };
function addCard(text) {
  $('empty')?.remove();
  const c = document.createElement('div');
  c.className = 'card';
  c.innerHTML = `<div class="you">${esc(text)}</div><div class="meta"><span class="tape sm">…</span><span class="lat"></span></div><div class="ans"><div class="thinking">Thinking…</div></div>`;
  $('feed').appendChild(c); $('feed').scrollTop = 1e9;
  return c;
}
function fillCard(c, j) {
  const parts = [];
  if (j.stt != null) parts.push(`speech ${(j.stt / 1000).toFixed(1)} s`);
  if (j.ocr_ms != null) parts.push(`text ${(j.ocr_ms / 1000).toFixed(1)} s`);
  if (j.vlm_ms != null) parts.push(`model ${(j.vlm_ms / 1000).toFixed(1)} s`);
  if (j.total_ms != null) parts.push(`total ${(j.total_ms / 1000).toFixed(1)} s`);
  const tag = c.querySelector('.tape');
  tag.textContent = LABEL[j.intent] || j.intent;
  tag.className = 'tape sm ' + (TAPE[j.intent] || '');
  c.querySelector('.lat').textContent = parts.join(' · ');
  const ans = c.querySelector('.ans');
  ans.innerHTML = '';
  if (j.say) {
    const b = document.createElement('button'); b.className = 'replay'; b.type = 'button'; b.title = 'Play again'; b.setAttribute('aria-label', 'Play again');
    b.innerHTML = '<svg class="ic"><use href="#i-speaker"/></svg>'; b.onclick = () => speech.say(j.say); ans.appendChild(b);
    ans.appendChild(document.createTextNode(j.say));
  }
  if (j.ocr?.length && document.body.classList.contains('details')) {
    const o = document.createElement('div'); o.className = 'ocr';
    o.textContent = j.ocr.map(l => `${l.text}  (${Math.round(l.conf * 100)}%)`).join('\n'); ans.appendChild(o);
  }
  $('feed').scrollTop = 1e9;
}
function feedNote(kind, text) {
  $('empty')?.remove();
  const c = document.createElement('div');
  c.className = 'card alert';
  c.innerHTML = `<div class="meta"><span class="tape sm ${kind === 'find' ? 'blue' : 'red'}">${kind === 'find' ? 'Find' : 'Alert'}</span><span class="lat">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span></div><div class="ans">${esc(text)}</div>`;
  $('feed').appendChild(c);
  const notes = [...$('feed').querySelectorAll('.card.alert')];
  if (notes.length > 6) notes[0].remove();
  $('feed').scrollTop = 1e9;
}

/* ---------------- UI helpers ---------------- */
const capTimers = {};
function showCaption(who, text) {
  if (!$('caps').checked) return;
  const el = $(who === 'you' ? 'capyou' : 'capes');
  el.textContent = text; el.classList.add('show');
  clearTimeout(capTimers[who]);
  capTimers[who] = setTimeout(() => el.classList.remove('show'), who === 'you' ? 6000 : Math.min(14000, 3500 + text.length * 60));
}
let bannerT;
function banner(text, ms) {
  const b = $('alertbar');
  $('alerttxt').textContent = text; b.classList.add('show');
  clearTimeout(bannerT); bannerT = setTimeout(() => b.classList.remove('show'), ms);
}
function pulse(m, ms = 300) {
  const n = document.querySelector(`tr[data-m="${m}"]`); if (!n) return;
  n.classList.add('active'); clearTimeout(n._t); n._t = setTimeout(() => n.classList.remove('active'), ms);
}
function activate(m, on) { const n = document.querySelector(`tr[data-m="${m}"]`); if (n) { clearTimeout(n._t); n.classList.toggle('active', on); } }
function setBusy(on) { document.querySelectorAll('.act[data-cmd]').forEach(b => b.classList.toggle('busy', on)); }
function setToggle(btn, on) { btn.classList.toggle('on', on); btn.setAttribute('aria-pressed', on); }
function setHazards(on) {
  S.hazards = on; savePrefs();
  setToggle($('guardbtn'), on);
  $('guardpill').hidden = !on; $('guardpill').textContent = 'Hazards on';
}
function setBoxes(on) {
  $('boxes').checked = on; savePrefs();
  setToggle($('boxbtn'), on);
  $('hud').hidden = !on;
  if (!on) octx.clearRect(0, 0, ov.width, ov.height);
}
const pinFeed = () => requestAnimationFrame(() => { $('feed').style.scrollBehavior = 'auto'; $('feed').scrollTop = $('feed').scrollHeight; $('feed').style.scrollBehavior = ''; });
addEventListener('resize', pinFeed);
function setDetails(on) {
  document.body.classList.toggle('details', on); savePrefs(); pinFeed();
  $('viewbtn').setAttribute('aria-pressed', on);
  $('viewtxt').textContent = on ? 'Hide details' : 'Details';
}
function updateFindUI() {
  $('findpill').hidden = !S.find; $('findname').textContent = (S.find || '');
  $('findbtn').querySelector('.lbl').textContent = S.find ? 'Stop finding' : 'Find…';
}
function stopEverything() { speech.stopAll(); if (S.find) command('stop'); }

/* ---------------- camera focus (Settings) ---------------- */
const F = { info: null, timer: null };
async function loadFocus() {
  try { F.info = await (await fetch('/api/focus')).json(); } catch (e) { F.info = { available: false }; }
  const i = F.info;
  $('focusbox').hidden = !i.available || !!S.demo;
  if (!i.available) return false;
  $('focusval').min = i.min; $('focusval').max = i.max; $('focusval').step = i.step;
  renderFocus();
  return true;
}
function renderFocus() {
  const i = F.info;
  $('focuscam').textContent = (i.camera || '').replace(/:.*/, '');
  $('fauto').setAttribute('aria-pressed', i.auto); $('fman').setAttribute('aria-pressed', !i.auto);
  $('focusval').disabled = i.auto; $('focusval').value = i.value;
  $('focusnum').textContent = i.auto ? 'Auto' : i.value;
}
async function setFocus(body, remember = true) {
  try {
    const j = await (await fetch('/api/focus', { method: 'POST', body: JSON.stringify(body) })).json();
    if (j.error) throw new Error(j.error);
    F.info = j; renderFocus();
    if (remember) { S.focusPref = { auto: j.auto, value: j.value }; savePrefs(); }
    $('focusmsg').textContent = '';
    return j;
  } catch (e) { $('focusmsg').textContent = e.message; }
}
function sharpness() { // variance of the Laplacian over the centre of the frame: higher means sharper
  const cv = grab(320); if (!cv) return 0;
  const w = cv.width, h = cv.height, x0 = Math.round(w * .2), x1 = Math.round(w * .8), y0 = Math.round(h * .2), y1 = Math.round(h * .8);
  const d = cv.getContext('2d').getImageData(0, 0, w, h).data, g = new Float32Array(w * h);
  for (let k = 0; k < w * h; k++) g[k] = .299 * d[k * 4] + .587 * d[k * 4 + 1] + .114 * d[k * 4 + 2];
  let sum = 0, sq = 0, n = 0;
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
    const v = 4 * g[y * w + x] - g[y * w + x - 1] - g[y * w + x + 1] - g[(y - 1) * w + x] - g[(y + 1) * w + x];
    sum += v; sq += v * v; n++;
  }
  return sq / n - (sum / n) ** 2;
}
async function tuneFocus() {
  const i = F.info, btn = $('focustune');
  if (!i?.available || S.demo || !cam.videoWidth) { $('focusmsg').textContent = 'Needs the live camera.'; return; }
  btn.disabled = true;
  const measure = async v => {
    await setFocus({ value: v }, false); await sleep(480);
    const a = sharpness(); await sleep(120); return (a + sharpness()) / 2;
  };
  let best = { v: i.value, s: -1 };
  const sweep = async (lo, hi, steps) => {
    for (let k = 0; k <= steps; k++) {
      const v = Math.round(lo + (hi - lo) * k / steps);
      $('focusmsg').textContent = `Tuning… ${k + 1}/${steps + 1}`;
      const s = await measure(v);
      if (s > best.s) best = { v, s };
    }
  };
  await sweep(i.min, i.max, 12);                                          // coarse pass over the whole range
  const span = (i.max - i.min) / 12;
  await sweep(Math.max(i.min, best.v - span), Math.min(i.max, best.v + span), 6); // fine pass around the best
  await setFocus({ value: best.v });
  $('focusmsg').textContent = `Tuned to ${best.v}`;
  btn.disabled = false;
}
function bindFocus() {
  $('fauto').onclick = () => setFocus({ auto: true });
  $('fman').onclick = () => setFocus({ auto: false });
  $('focusval').oninput = () => {
    $('focusnum').textContent = $('focusval').value;
    clearTimeout(F.timer); F.timer = setTimeout(() => setFocus({ value: +$('focusval').value }), 100);
  };
  $('focustune').onclick = tuneFocus;
}

/* ---------------- status polling ---------------- */
async function pollMetrics() {
  try {
    const m = await (await fetch('/api/metrics')).json();
    for (const k of Object.keys(BUDGET)) {
      const el = $('m-' + k), bar = $('b-' + k);
      if (!m[k]) continue;
      const v = m[k].p50;
      el.textContent = v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`;
      bar.style.width = Math.min(100, v / BUDGET[k] * 100) + '%';
      bar.classList.toggle('over', v > BUDGET[k]);
    }
  } catch (e) {}
  setTimeout(pollMetrics, 1500);
}
async function pollHealth(first) {
  try {
    const h = await (await fetch('/api/health')).json();
    S.hfov = h.hfov; S.pathHalf = h.path_half_angle;
    $('netchip').className = 'tape sm ' + (h.internet ? 'yellow' : 'green');
    $('nettxt').textContent = h.internet ? 'Online, not used' : 'Offline';
    const mode = $('model').value, name = h.vlm[mode];
    $('vlmname').textContent = `${name}${h.vlm_available[mode] ? '' : ' (not installed)'}`;
    if (first) {
      const by = {};
      h.voices.forEach(v => (by[v.split('-')[0].slice(3)] ??= []).push(v));
      const pretty = s => s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).replace(/^Hfc /, 'HFC ');
      const G = { US: 'American English', GB: 'British English' };
      $('voice').innerHTML = Object.entries(by).map(([loc, vs]) => `<optgroup label="${G[loc] || loc}">`
        + vs.map(v => `<option value="${v}">${pretty(v.split('-')[1])} (${v.split('-')[2]})</option>`).join('') + '</optgroup>').join('');
      $('voice').value = h.voices.includes(S.voicePref) ? S.voicePref : h.default_voice;
    }
  } catch (e) { $('nettxt').textContent = 'Server off'; }
  setTimeout(pollHealth, 10000);
}

/* ---------------- wiring ---------------- */
function startApp() {
  if (S.started) return;
  S.started = true; ac();
  document.getElementById('splash')?.remove();
}
function bind() {
  document.querySelectorAll('.act[data-cmd]').forEach(b => b.onclick = () => command(b.dataset.cmd));
  const talk = $('talk');
  talk.onpointerdown = e => { e.preventDefault(); startApp(); if (rec) return stopTalk(); downAt = performance.now(); startTalk(); };
  talk.onpointerup = talk.onpointerleave = () => { if (rec && performance.now() - downAt > 400) stopTalk(); };
  $('guardbtn').onclick = () => { setHazards(!S.hazards); speech.say(`Hazard alerts ${S.hazards ? 'on' : 'off'}.`); };
  $('boxbtn').onclick = () => setBoxes(!$('boxes').checked);
  $('stopbtn').onclick = stopEverything;
  $('findbtn').onclick = () => { if (S.find) command('stop'); else { $('asktext').value = 'find my '; $('asktext').focus(); } };
  $('askform').onsubmit = e => { e.preventDefault(); const t = $('asktext').value; $('asktext').value = ''; $('asktext').blur(); command(t); };
  $('clear').onclick = () => { S.history = []; $('feed').innerHTML = ''; };
  $('setbtn').onclick = () => { $('drawer').hidden = false; loadFocus(); };
  bindFocus();
  $('closeset').onclick = () => $('drawer').hidden = true;
  $('drawer').onclick = e => { if (e.target === $('drawer')) $('drawer').hidden = true; };
  $('viewbtn').onclick = () => setDetails(!document.body.classList.contains('details'));
  $('camsel').onchange = e => startCam(e.target.value);
  $('rot').onchange = $('mir').onchange = () => { applyXf(); savePrefs(); };
  ['sonar', 'earcons', 'caps', 'model'].forEach(k => $(k).onchange = () => { savePrefs(); pollHealth(); });
  $('boxes').onchange = () => setBoxes($('boxes').checked);
  $('voice').onchange = () => { savePrefs(); speech.say('This is my new voice.'); };

  addEventListener('keydown', e => {
    startApp();
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (e.key === 'Escape') { stopEverything(); $('drawer').hidden = true; document.activeElement.blur(); return; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.code === 'Space') { e.preventDefault(); if (!e.repeat) startTalk(); return; }
    const k = e.key.toLowerCase();
    const map = { r: 'read this', l: 'read the medicine label', d: "what's in front of me?" };
    if (map[k]) command(map[k]);
    else if (k === 'h') $('guardbtn').click();
    else if (k === 'b') $('boxbtn').click();
    else if (k === 'f') { e.preventDefault(); $('findbtn').click(); }
    else if (k === 'v') $('viewbtn').click();
  });
  addEventListener('keyup', e => { if (e.code === 'Space' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) stopTalk(); });
  addEventListener('pointerdown', startApp, { once: true });
}

function splash() {
  const s = document.createElement('div');
  s.id = 'splash';
  s.innerHTML = `<div><div class="brand"><svg class="logo"><use href="#i-logo"/></svg><span>EdgeSight</span></div><p>Press any key or click to start</p></div>`;
  s.onclick = startApp;
  document.body.appendChild(s);
}

loadPrefs(); applyXf(); bind(); splash();
setHazards(!!S.hazardsPref); setBoxes($('boxes').checked); setDetails(document.body.classList.contains('details'));
pollHealth(true); pollMetrics();
// a fresh page never inherits the previous session's find target (it lives in the server's memory)
fetch('/api/command', { method: 'POST', body: JSON.stringify({ text: 'stop' }) }).catch(() => {});
startCam().then(async () => {
  detectLoop();
  if (await loadFocus() && S.focusPref) setFocus(S.focusPref.auto ? { auto: true } : { value: S.focusPref.value }, false); // re-apply last choice
});
sonar.tick();
