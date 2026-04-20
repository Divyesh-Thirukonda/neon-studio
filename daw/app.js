const BPM = 142;
const BEATS_PER_BAR = 4;
const TOTAL_BARS = 72;
const TOTAL_BEATS = TOTAL_BARS * BEATS_PER_BAR;
const SECONDS_PER_BEAT = 60 / BPM;

const tracks = [
  {
    id: "drums",
    name: "Drums",
    file: "../exports/neon_solitude_drums.wav",
    color: "#ff8d5c",
    gain: 0.82,
    pan: 0,
    steps: [0, 4, 8, 12, 14],
  },
  {
    id: "bass",
    name: "Bass",
    file: "../exports/neon_solitude_bass.wav",
    color: "#45d18e",
    gain: 0.9,
    pan: 0,
    steps: [0, 6, 8, 12],
  },
  {
    id: "chords",
    name: "Chords",
    file: "../exports/neon_solitude_chords.wav",
    color: "#ffcd5a",
    gain: 1,
    pan: -0.04,
    steps: [0, 5, 8, 12],
  },
  {
    id: "lead",
    name: "Lead",
    file: "../exports/neon_solitude_lead_and_plucks.wav",
    color: "#60c8f8",
    gain: 1,
    pan: 0.06,
    steps: [0, 2, 4, 7, 9, 11, 14],
  },
  {
    id: "fx",
    name: "FX",
    file: "../exports/neon_solitude_fx.wav",
    color: "#d885ff",
    gain: 0.72,
    pan: 0.08,
    steps: [0, 15],
  },
];

const els = {
  body: document.body,
  play: document.getElementById("playBtn"),
  pause: document.getElementById("pauseBtn"),
  stop: document.getElementById("stopBtn"),
  rewind: document.getElementById("rewindBtn"),
  reload: document.getElementById("reloadBtn"),
  barReadout: document.getElementById("barReadout"),
  timeReadout: document.getElementById("timeReadout"),
  loadStatus: document.getElementById("loadStatus"),
  stepsHeader: document.getElementById("stepsHeader"),
  stepGrid: document.getElementById("stepGrid"),
  stepReadout: document.getElementById("stepReadout"),
  trackLabels: document.getElementById("trackLabels"),
  timelineScroll: document.getElementById("timelineScroll"),
  waveformLanes: document.getElementById("waveformLanes"),
  playhead: document.getElementById("playhead"),
  ruler: document.getElementById("rulerCanvas"),
  piano: document.getElementById("pianoCanvas"),
  scope: document.getElementById("scopeCanvas"),
  mixer: document.getElementById("mixer"),
  zoomIn: document.getElementById("zoomInBtn"),
  zoomOut: document.getElementById("zoomOutBtn"),
};

const state = {
  context: null,
  masterGain: null,
  masterAnalyser: null,
  buffers: new Map(),
  sources: new Map(),
  channelNodes: new Map(),
  controls: new Map(),
  stepButtons: [],
  isLoaded: false,
  isPlaying: false,
  startTime: 0,
  offset: 0,
  duration: 0,
  pixelsPerBar: 48,
  animationFrame: 0,
  scopePhase: 0,
};

function setStatus(text) {
  els.loadStatus.textContent = text;
}

function formatTime(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  const secs = whole % 60;
  const tenths = Math.floor((seconds - whole) * 10);
  return `${minutes}:${String(secs).padStart(2, "0")}.${tenths}`;
}

function positionSeconds() {
  if (!state.isPlaying || !state.context) return state.offset;
  return Math.min(state.duration, state.offset + state.context.currentTime - state.startTime);
}

function setOffset(seconds) {
  state.offset = Math.max(0, Math.min(seconds, state.duration || Number.MAX_SAFE_INTEGER));
  renderTransport();
}

function trackGain(track) {
  const control = state.controls.get(track.id);
  if (!control) return track.gain;

  const soloActive = [...state.controls.values()].some((item) => item.solo);
  if (control.mute) return 0;
  if (soloActive && !control.solo) return 0;
  return control.gain;
}

function updateGains() {
  tracks.forEach((track) => {
    const nodes = state.channelNodes.get(track.id);
    if (!nodes) return;
    nodes.gain.gain.setTargetAtTime(trackGain(track), state.context.currentTime, 0.015);
    if (nodes.pan) nodes.pan.pan.setTargetAtTime(state.controls.get(track.id).pan, state.context.currentTime, 0.02);
  });
}

function createAudioGraph() {
  if (state.context) return;
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  state.context = new AudioContext();
  state.masterGain = state.context.createGain();
  state.masterGain.gain.value = 0.86;
  state.masterAnalyser = state.context.createAnalyser();
  state.masterAnalyser.fftSize = 2048;
  state.masterAnalyser.smoothingTimeConstant = 0.78;
  state.masterGain.connect(state.masterAnalyser);
  state.masterAnalyser.connect(state.context.destination);
}

async function loadStems() {
  els.body.classList.add("is-loading");
  createAudioGraph();
  stopPlayback();
  state.buffers.clear();
  state.duration = 0;
  state.isLoaded = false;
  setStatus("Loading 0/5");

  for (let index = 0; index < tracks.length; index += 1) {
    const track = tracks[index];
    const response = await fetch(track.file, { cache: "no-store" });
    if (!response.ok) throw new Error(`Could not load ${track.file}`);
    const data = await response.arrayBuffer();
    const buffer = await state.context.decodeAudioData(data);
    state.buffers.set(track.id, buffer);
    state.duration = Math.max(state.duration, buffer.duration);
    setStatus(`Loading ${index + 1}/5`);
  }

  state.isLoaded = true;
  els.body.classList.remove("is-loading");
  setStatus("Ready");
  drawAllWaveforms();
  drawPianoRoll();
  drawScope();
  renderTransport();
}

function startPlayback() {
  if (!state.isLoaded) return;
  createAudioGraph();
  if (state.context.state === "suspended") state.context.resume();
  if (state.isPlaying) return;
  if (state.offset >= state.duration - 0.02) state.offset = 0;

  state.sources.clear();
  state.channelNodes.clear();
  tracks.forEach((track) => {
    const source = state.context.createBufferSource();
    source.buffer = state.buffers.get(track.id);

    const gain = state.context.createGain();
    gain.gain.value = trackGain(track);

    const analyser = state.context.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.68;

    let pan = null;
    if (state.context.createStereoPanner) {
      pan = state.context.createStereoPanner();
      pan.pan.value = state.controls.get(track.id).pan;
      source.connect(gain);
      gain.connect(pan);
      pan.connect(analyser);
    } else {
      source.connect(gain);
      gain.connect(analyser);
    }

    analyser.connect(state.masterGain);
    source.start(0, state.offset);
    source.onended = () => {
      if (positionSeconds() >= state.duration - 0.1) stopPlayback();
    };

    state.sources.set(track.id, source);
    state.channelNodes.set(track.id, { gain, pan, analyser });
  });

  state.startTime = state.context.currentTime;
  state.isPlaying = true;
  updateGains();
  animate();
}

function pausePlayback() {
  if (!state.isPlaying) return;
  state.offset = positionSeconds();
  stopSourcesOnly();
  state.isPlaying = false;
  renderTransport();
}

function stopSourcesOnly() {
  state.sources.forEach((source) => {
    try {
      source.onended = null;
      source.stop();
    } catch {
      return;
    }
  });
  state.sources.clear();
  state.channelNodes.clear();
}

function stopPlayback() {
  stopSourcesOnly();
  state.isPlaying = false;
  state.offset = 0;
  renderTransport();
}

function renderTransport() {
  const seconds = positionSeconds();
  const beat = seconds / SECONDS_PER_BEAT;
  const bar = Math.floor(beat / BEATS_PER_BAR) + 1;
  const beatInBar = Math.floor(beat % BEATS_PER_BAR) + 1;
  els.barReadout.textContent = `${String(bar).padStart(3, "0")}.${beatInBar}`;
  els.timeReadout.textContent = formatTime(seconds);

  const timelineWidth = timelineWidthPixels();
  const x = state.duration ? (seconds / state.duration) * timelineWidth : 0;
  els.playhead.style.transform = `translateX(${x}px)`;

  const step = Math.floor((beat * 4) % 16);
  els.stepReadout.textContent = String(step + 1).padStart(2, "0");
  state.stepButtons.forEach((button) => {
    button.classList.toggle("playing", Number(button.dataset.step) === step);
  });
}

function animate() {
  renderTransport();
  updateMeters();
  drawScope();
  if (state.isPlaying) {
    state.animationFrame = requestAnimationFrame(animate);
  }
}

function updateMeters() {
  tracks.forEach((track) => {
    const control = state.controls.get(track.id);
    const nodes = state.channelNodes.get(track.id);
    if (!control || !nodes) {
      if (control) control.fill.style.height = "0%";
      return;
    }
    const data = new Uint8Array(nodes.analyser.frequencyBinCount);
    nodes.analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const value of data) {
      const centered = (value - 128) / 128;
      sum += centered * centered;
    }
    const rms = Math.sqrt(sum / data.length);
    const level = Math.min(100, Math.pow(rms * 3.3, 0.74) * 100);
    control.fill.style.height = `${level}%`;
  });
}

function timelineWidthPixels() {
  return TOTAL_BARS * state.pixelsPerBar;
}

function setTimelineWidth() {
  const width = `${timelineWidthPixels()}px`;
  document.documentElement.style.setProperty("--timeline-width", width);
  drawRuler();
  drawAllWaveforms();
}

function drawRuler() {
  const canvas = els.ruler;
  const width = timelineWidthPixels();
  const height = 30;
  setupCanvas(canvas, width, height);
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#1b1c1e";
  ctx.fillRect(0, 0, width, height);
  ctx.font = "11px system-ui, sans-serif";
  ctx.textBaseline = "middle";

  for (let bar = 0; bar <= TOTAL_BARS; bar += 1) {
    const x = Math.round(bar * state.pixelsPerBar) + 0.5;
    const major = bar % 4 === 0;
    ctx.strokeStyle = major ? "#6d7076" : "#3a3d42";
    ctx.beginPath();
    ctx.moveTo(x, major ? 0 : 13);
    ctx.lineTo(x, 30);
    ctx.stroke();
    if (major && bar < TOTAL_BARS) {
      ctx.fillStyle = "#b8b0a5";
      ctx.fillText(String(bar + 1), x + 5, 13);
    }
  }
}

function setupCanvas(canvas, cssWidth, cssHeight) {
  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.max(1, Math.floor(cssWidth * dpr));
  canvas.height = Math.max(1, Math.floor(cssHeight * dpr));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function drawWaveform(canvas, buffer, color) {
  const width = timelineWidthPixels();
  const height = 88;
  setupCanvas(canvas, width, height);
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, width, height);

  ctx.fillStyle = "#191a1c";
  ctx.fillRect(0, 0, width, height);
  for (let bar = 0; bar <= TOTAL_BARS; bar += 1) {
    ctx.strokeStyle = bar % 4 === 0 ? "#35383d" : "#272a2f";
    ctx.beginPath();
    ctx.moveTo(bar * state.pixelsPerBar + 0.5, 0);
    ctx.lineTo(bar * state.pixelsPerBar + 0.5, height);
    ctx.stroke();
  }

  if (!buffer) return;
  const data = buffer.getChannelData(0);
  const samplesPerPixel = Math.max(1, Math.floor(data.length / width));
  const mid = height / 2;

  ctx.fillStyle = `${color}33`;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 0; x < width; x += 1) {
    const start = x * samplesPerPixel;
    const end = Math.min(start + samplesPerPixel, data.length);
    let min = 1;
    let max = -1;
    for (let index = start; index < end; index += Math.max(1, Math.floor(samplesPerPixel / 24))) {
      const value = data[index] || 0;
      if (value < min) min = value;
      if (value > max) max = value;
    }
    const y1 = mid + min * mid * 0.82;
    const y2 = mid + max * mid * 0.82;
    ctx.moveTo(x + 0.5, y1);
    ctx.lineTo(x + 0.5, y2);
  }
  ctx.stroke();
}

function drawAllWaveforms() {
  document.querySelectorAll(".wave-canvas").forEach((canvas) => {
    const track = tracks.find((item) => item.id === canvas.dataset.track);
    drawWaveform(canvas, state.buffers.get(track.id), track.color);
  });
}

function drawPianoRoll() {
  const canvas = els.piano;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, rect.width);
  const height = Math.max(180, rect.height);
  setupCanvas(canvas, width, height);
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#171819";
  ctx.fillRect(0, 0, width, height);

  const left = 42;
  const top = 12;
  const noteHeight = 10;
  const rows = Math.floor((height - top - 10) / noteHeight);
  const highNote = 90;
  const beatsVisible = 32;
  const beatWidth = (width - left - 10) / beatsVisible;

  ctx.font = "10px system-ui, sans-serif";
  ctx.textBaseline = "middle";
  for (let row = 0; row < rows; row += 1) {
    const note = highNote - row;
    const y = top + row * noteHeight;
    const isSharp = [1, 3, 6, 8, 10].includes(note % 12);
    ctx.fillStyle = isSharp ? "#202225" : "#191b1e";
    ctx.fillRect(left, y, width - left, noteHeight);
    if (note % 12 === 0) {
      ctx.fillStyle = "#a9a39a";
      ctx.fillText(`C${Math.floor(note / 12) - 1}`, 7, y + noteHeight / 2);
    }
  }

  for (let beat = 0; beat <= beatsVisible; beat += 1) {
    const x = left + beat * beatWidth;
    ctx.strokeStyle = beat % 4 === 0 ? "#42454a" : "#2b2d30";
    ctx.beginPath();
    ctx.moveTo(x + 0.5, top);
    ctx.lineTo(x + 0.5, height - 8);
    ctx.stroke();
  }

  const notes = [
    [0, 0.46, 76], [0.52, 0.42, 79], [1.05, 0.7, 83], [2, 0.42, 86], [2.52, 0.38, 83], [3.04, 0.68, 79],
    [4, 0.42, 84], [4.5, 0.44, 83], [5.02, 0.54, 79], [5.72, 0.38, 76], [6.18, 0.42, 81], [6.72, 0.68, 79],
    [8, 0.4, 83], [8.46, 0.42, 86], [8.98, 0.74, 88], [10, 0.4, 86], [10.48, 0.42, 83], [11, 0.7, 81],
    [12, 0.44, 79], [12.55, 0.38, 83], [13.04, 0.38, 81], [13.54, 0.38, 79], [14.12, 0.78, 76], [15.08, 0.4, 74], [15.55, 0.34, 76],
  ];
  const looped = [...notes, ...notes.map(([start, dur, note]) => [start + 16, dur, note + 2])];

  looped.forEach(([start, dur, note]) => {
    const y = top + (highNote - note) * noteHeight;
    if (y < top || y > height - noteHeight) return;
    const x = left + start * beatWidth;
    const w = Math.max(8, dur * beatWidth - 2);
    ctx.fillStyle = "#60c8f8";
    ctx.strokeStyle = "#c6efff";
    roundRect(ctx, x, y + 1, w, noteHeight - 2, 4);
    ctx.fill();
    ctx.stroke();
  });
}

function drawScope() {
  const canvas = els.scope;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(220, rect.width);
  const height = Math.max(160, rect.height);
  setupCanvas(canvas, width, height);
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#171819";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "#2f3237";
  for (let y = 0; y < height; y += 24) {
    ctx.beginPath();
    ctx.moveTo(0, y + 0.5);
    ctx.lineTo(width, y + 0.5);
    ctx.stroke();
  }

  if (!state.masterAnalyser || !state.isPlaying) {
    ctx.strokeStyle = "#5a5d63";
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
    return;
  }

  const data = new Uint8Array(state.masterAnalyser.fftSize);
  state.masterAnalyser.getByteTimeDomainData(data);
  ctx.strokeStyle = "#ffe083";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let x = 0; x < width; x += 1) {
    const index = Math.floor((x / width) * data.length);
    const value = (data[index] - 128) / 128;
    const y = height / 2 + value * height * 0.42;
    if (x === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}

function buildRack() {
  els.stepsHeader.innerHTML = "<span></span>";
  for (let step = 0; step < 16; step += 1) {
    const label = document.createElement("span");
    label.textContent = String(step + 1);
    els.stepsHeader.appendChild(label);
  }

  els.stepGrid.innerHTML = "";
  state.stepButtons = [];
  tracks.forEach((track) => {
    const row = document.createElement("div");
    row.className = "step-row";

    const name = document.createElement("div");
    name.className = "step-name";
    name.textContent = track.name;
    row.appendChild(name);

    for (let step = 0; step < 16; step += 1) {
      const button = document.createElement("button");
      button.className = "step";
      button.style.color = track.color;
      button.dataset.track = track.id;
      button.dataset.step = String(step);
      button.title = `${track.name} step ${step + 1}`;
      button.setAttribute("aria-label", `${track.name} step ${step + 1}`);
      button.classList.toggle("on", track.steps.includes(step));
      button.addEventListener("click", () => button.classList.toggle("on"));
      row.appendChild(button);
      state.stepButtons.push(button);
    }
    els.stepGrid.appendChild(row);
  });
}

function buildPlaylist() {
  els.trackLabels.innerHTML = "";
  els.waveformLanes.innerHTML = "";

  tracks.forEach((track) => {
    const label = document.createElement("div");
    label.className = "track-label";
    label.innerHTML = `<span>${track.name}</span><span style="color:${track.color}">&#9632;</span>`;
    els.trackLabels.appendChild(label);

    const lane = document.createElement("div");
    lane.className = "lane";
    lane.style.color = track.color;
    const clip = document.createElement("div");
    clip.className = "clip-block";
    lane.appendChild(clip);
    const canvas = document.createElement("canvas");
    canvas.className = "wave-canvas";
    canvas.dataset.track = track.id;
    lane.appendChild(canvas);
    els.waveformLanes.appendChild(lane);
  });
  setTimelineWidth();
}

function buildMixer() {
  els.mixer.innerHTML = "";
  tracks.forEach((track) => {
    state.controls.set(track.id, {
      gain: track.gain,
      pan: track.pan,
      mute: false,
      solo: false,
      fill: null,
    });

    const strip = document.createElement("div");
    strip.className = "strip";

    const name = document.createElement("div");
    name.className = "strip-name";
    name.textContent = track.name;
    name.style.borderTop = `3px solid ${track.color}`;
    strip.appendChild(name);

    const meter = document.createElement("div");
    meter.className = "meter";
    const fill = document.createElement("div");
    fill.className = "meter-fill";
    meter.appendChild(fill);
    strip.appendChild(meter);
    state.controls.get(track.id).fill = fill;

    const controls = document.createElement("div");
    controls.className = "strip-controls";
    const mute = document.createElement("button");
    mute.textContent = "M";
    mute.title = `Mute ${track.name}`;
    mute.style.color = track.color;
    const solo = document.createElement("button");
    solo.textContent = "S";
    solo.title = `Solo ${track.name}`;
    solo.style.color = track.color;
    mute.addEventListener("click", () => {
      const item = state.controls.get(track.id);
      item.mute = !item.mute;
      mute.classList.toggle("active", item.mute);
      updateGains();
    });
    solo.addEventListener("click", () => {
      const item = state.controls.get(track.id);
      item.solo = !item.solo;
      solo.classList.toggle("active", item.solo);
      updateGains();
    });
    controls.append(mute, solo);
    strip.appendChild(controls);

    const faderWrap = document.createElement("div");
    faderWrap.className = "fader-wrap";
    const fader = document.createElement("input");
    fader.className = "fader";
    fader.type = "range";
    fader.min = "0";
    fader.max = "1.4";
    fader.step = "0.01";
    fader.value = String(track.gain);
    fader.title = `${track.name} volume`;
    fader.style.accentColor = track.color;
    fader.addEventListener("input", () => {
      state.controls.get(track.id).gain = Number(fader.value);
      updateGains();
    });
    faderWrap.appendChild(fader);
    strip.appendChild(faderWrap);

    const panWrap = document.createElement("div");
    panWrap.className = "pan-wrap";
    panWrap.innerHTML = "<span>L</span>";
    const pan = document.createElement("input");
    pan.className = "pan";
    pan.type = "range";
    pan.min = "-1";
    pan.max = "1";
    pan.step = "0.01";
    pan.value = String(track.pan);
    pan.title = `${track.name} pan`;
    pan.addEventListener("input", () => {
      state.controls.get(track.id).pan = Number(pan.value);
      updateGains();
    });
    const right = document.createElement("span");
    right.textContent = "R";
    panWrap.append(pan, right);
    strip.appendChild(panWrap);

    els.mixer.appendChild(strip);
  });
}

function bindEvents() {
  els.play.addEventListener("click", async () => {
    if (!state.isLoaded) await loadStems();
    startPlayback();
  });
  els.pause.addEventListener("click", pausePlayback);
  els.stop.addEventListener("click", stopPlayback);
  els.rewind.addEventListener("click", () => {
    const resume = state.isPlaying;
    stopSourcesOnly();
    state.isPlaying = false;
    setOffset(0);
    if (resume) startPlayback();
  });
  els.reload.addEventListener("click", () => loadStems().catch((error) => setStatus(error.message)));
  els.zoomIn.addEventListener("click", () => {
    state.pixelsPerBar = Math.min(90, state.pixelsPerBar + 8);
    setTimelineWidth();
  });
  els.zoomOut.addEventListener("click", () => {
    state.pixelsPerBar = Math.max(28, state.pixelsPerBar - 8);
    setTimelineWidth();
  });
  els.timelineScroll.addEventListener("click", (event) => {
    const rect = els.timelineScroll.getBoundingClientRect();
    const x = event.clientX - rect.left + els.timelineScroll.scrollLeft;
    const seconds = (x / timelineWidthPixels()) * state.duration;
    const resume = state.isPlaying;
    stopSourcesOnly();
    state.isPlaying = false;
    setOffset(seconds);
    if (resume) startPlayback();
  });
  window.addEventListener("resize", () => {
    drawPianoRoll();
    drawScope();
  });
}

function init() {
  buildRack();
  buildPlaylist();
  buildMixer();
  bindEvents();
  drawPianoRoll();
  drawScope();
  setStatus("Ready to load");
}

init();
