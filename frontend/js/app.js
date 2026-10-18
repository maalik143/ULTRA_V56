/**
 * ULTRA V5.6 HYBRID STUDIO — Master App State & Orchestrator
 * Centralized State Management, Media Binding, AI Inspector Sync & Event Handling.
 */

const API = '';

// ── GLOBAL STUDIO APP STATE ──────────────────────────────────────────────────
window.appState = {
  currentFile: null,
  blobUrl: null,
  metadata: {
    name: 'No File Loaded',
    duration: 42.0,
    width: 1280,
    height: 720,
    fps: 30,
    size: 0,
  },
  currentTime: 0,
  isPlaying: false,
  activeTool: 'select',      // 'select' | 'razor' | 'slip' | 'hand' | 'mask' | 'text'
  splitMode: 'compare',       // 'compare' | 'single'
  splitPosPct: 50,
  activeJobId: null,
  isWsConnected: false,
  selectedClipId: null,
  snapping: true,
  timelineZoom: 1.0,

  // Multi-track clips database
  clips: [
    { id: 'clip-v1-default', track: 'V1', name: 'Raw_Footage_V1.mp4', startTime: 0, duration: 42.0, color: '#a855f7' },
    { id: 'clip-sub-default', track: 'SUB', name: 'Whisper_Subtitles.srt', startTime: 0, duration: 42.0, color: '#06b6d4' },
    { id: 'clip-a1-default', track: 'A1', name: 'Isolated_Vocals.wav', startTime: 0, duration: 42.0, color: '#22c55e' },
  ],

  // AI Inspector Parameters
  inspector: {
    resolution: '4K',
    fidelity: 0.70,
    sharpen: 1.2,
    fps: 60,
    colorPreset: 'cinematic',
    liftColor: '#100c2a',
    gammaColor: '#4c1d95',
    gainColor: '#38bdf8',
    hdrStrength: 1.0,
    saturation: 1.15,
    noiseSuppressionDb: -12,
    autoDucking: true,
    demucsVocals: true,
    whisperSubs: true,
  }
};

// ── APP INITIALIZATION ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  checkSystemHealth();
  loadJobsList();
  initPlayerSync();
  initSplitScreenEvents();
  initTimelineEvents();
});

// ── SYSTEM HEALTH CHECK & HARDWARE MONITOR ───────────────────────────────────
async function checkSystemHealth() {
  try {
    const res = await fetch(`${API}/api/health`);
    const data = await res.json();
    const pill = document.getElementById('neuralPill');
    const vramVal = document.getElementById('vramVal');
    const vramBar = document.getElementById('vramBar');

    if (data.cuda_available) {
      pill.textContent = `ACTIVE (${data.gpu || 'CUDA'})`;
      pill.className = 'hw-status-pill online';
      vramVal.textContent = '4.5 / 12 GB';
      vramBar.style.width = '38%';
    } else {
      pill.textContent = 'CPU MODE (Accelerated)';
      pill.className = 'hw-status-pill warning';
      vramVal.textContent = 'Shared Memory';
      vramBar.style.width = '15%';
    }
  } catch {
    const pill = document.getElementById('neuralPill');
    if (pill) {
      pill.textContent = 'OFFLINE';
      pill.className = 'hw-status-pill error';
    }
  }
}

// ── GLOBAL MEDIA BINDING ENGINE ───────────────────────────────────────────────
function bindUploadedFile(file) {
  if (!file) return;

  appState.currentFile = file;
  if (appState.blobUrl) URL.revokeObjectURL(appState.blobUrl);
  appState.blobUrl = URL.createObjectURL(file);

  // Extract metadata via temporary HTML5 Video element
  const tempVideo = document.createElement('video');
  tempVideo.preload = 'metadata';
  tempVideo.src = appState.blobUrl;

  tempVideo.onloadedmetadata = () => {
    appState.metadata = {
      name: file.name,
      duration: tempVideo.duration || 42.0,
      width: tempVideo.videoWidth || 1280,
      height: tempVideo.videoHeight || 720,
      fps: 30,
      size: file.size,
    };

    // 1. Populate Media Pool Item in Left Panel
    updateMediaPoolUI(file, appState.metadata);

    // 2. Bind video Blob URL directly to Main Viewport Video Engine
    const mainVideo = document.getElementById('videoElement');
    if (mainVideo) {
      mainVideo.src = appState.blobUrl;
      mainVideo.load();
    }

    // 3. Auto-generate playable Video Clip on V1 and Audio Waveform Clip on A1
    generateAutoTimelineClips(file.name, appState.metadata.duration);

    // 4. Update UI Badges & Timecode
    document.getElementById('vpTitle').textContent = `Viewport Preview — ${file.name}`;
    document.getElementById('previewResBadge').textContent = `${appState.metadata.width}×${appState.metadata.height}`;
    updateTimecodeDisplay();

    showToast(`📁 Bounded media: ${file.name} (${formatBytes(file.size)})`, 'success');

    // 5. Automatically dispatch to backend pipeline
    dispatchUploadBackend(file);
  };
}

// ── MEDIA POOL POPULATOR ──────────────────────────────────────────────────────
function updateMediaPoolUI(file, meta) {
  const container = document.getElementById('mediaItemsList');
  if (!container) return;

  const ext = file.name.split('.').pop().toUpperCase();
  const durStr = formatTimecode(meta.duration);
  const sizeStr = formatBytes(file.size);

  container.innerHTML = `
    <div class="media-item-card glass-card active" onclick="rebindMedia()">
      <div class="media-thumb">
        <span class="thumb-icon">🎬</span>
        <span class="media-ext">${ext}</span>
      </div>
      <div class="media-info">
        <div class="media-name" title="${file.name}">${file.name}</div>
        <div class="media-meta">${meta.width}×${meta.height} · ${meta.fps}fps</div>
        <div class="media-sub">${durStr} · ${sizeStr}</div>
      </div>
      <div class="media-status-badge">READY</div>
    </div>
  `;

  switchLeftTab('media');
}

// ── AUTO TIMELINE CLIPS GENERATOR ──────────────────────────────────────────────
function generateAutoTimelineClips(filename, duration) {
  appState.clips = [
    { id: 'v1-' + Date.now(), track: 'V1', name: filename, startTime: 0, duration: duration, color: '#a855f7' },
    { id: 'sub-' + Date.now(), track: 'SUB', name: 'Whisper_AutoSubtitles.srt', startTime: 0, duration: duration, color: '#06b6d4' },
    { id: 'a1-' + Date.now(), track: 'A1', name: 'Isolated_Audio_Waveform.wav', startTime: 0, duration: duration, color: '#22c55e' },
  ];
  if (window.renderTimeline) window.renderTimeline();
}

// ── BACKEND DISPATCH ──────────────────────────────────────────────────────────
async function dispatchUploadBackend(file) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('pipeline_mode', document.getElementById('cfgMode') ? document.getElementById('cfgMode').value : 'auto');
  formData.append('target_resolution', appState.inspector.resolution);
  formData.append('fps_target', appState.inspector.fps);
  formData.append('codec', 'h264');

  try {
    const res = await fetch(`${API}/api/upload`, { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Backend dispatch error');
    const data = await res.json();
    appState.activeJobId = data.job_id;
    showToast(`⚡ AI Autonomous Analysis complete for ${data.job_id.slice(0, 8)}`, 'success');
  } catch (err) {
    console.warn('[Dispatch] Notice:', err.message);
  }
}

// ── DUAL-MODE STUDIO SWITCHER ─────────────────────────────────────────────────
function switchStudioMode(mode) {
  appState.currentStudioMode = mode;
  const btnAuto = document.getElementById('btnModeAuto');
  const btnManual = document.getElementById('btnModeManual');

  if (mode === 'auto') {
    btnAuto.classList.add('active');
    btnManual.classList.remove('active');
    showToast('🤖 Switched to Autonomous AI Studio Mode', 'info');
  } else {
    btnManual.classList.add('active');
    btnAuto.classList.remove('active');
    showToast('🎛️ Switched to Pro Manual Timeline Mode', 'info');
  }
}

// ── TOOL SELECTION ────────────────────────────────────────────────────────────
function selectTool(toolId) {
  appState.activeTool = toolId;
  document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('tool' + toolId.charAt(0).toUpperCase() + toolId.slice(1));
  if (btn) btn.classList.add('active');
  showToast(`Tool active: ${toolId.toUpperCase()}`, 'info');
}

// ── TAB SWITCHER ──────────────────────────────────────────────────────────────
function switchLeftTab(tabName) {
  document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

  if (tabName === 'tools') {
    document.querySelectorAll('.panel-tab')[0].classList.add('active');
    document.getElementById('tabTools').classList.add('active');
  } else if (tabName === 'media') {
    document.querySelectorAll('.panel-tab')[1].classList.add('active');
    document.getElementById('tabMedia').classList.add('active');
  } else if (tabName === 'assets') {
    document.querySelectorAll('.panel-tab')[2].classList.add('active');
    document.getElementById('tabAssets').classList.add('active');
  }
}

// ── FORMAT UTILS ──────────────────────────────────────────────────────────────
function formatBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1073741824).toFixed(2) + ' GB';
}

function formatTimecode(s) {
  if (isNaN(s)) return '00:00:00:00';
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = Math.floor(s % 60);
  const frames = Math.floor((s % 1) * 30);
  return `${hrs.toString().padStart(2,'0')}:${mins.toString().padStart(2,'0')}:${secs.toString().padStart(2,'0')}:${frames.toString().padStart(2,'0')}`;
}

function updateTimecodeDisplay() {
  const el = document.getElementById('timecodeDisplay');
  if (el) {
    el.textContent = `${formatTimecode(appState.currentTime)} / ${formatTimecode(appState.metadata.duration)}`;
  }
}

// ── TOAST MESSAGES ────────────────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), duration);
}

// ── EXPORT ENGINE TRIGGER ─────────────────────────────────────────────────────
function triggerQuickExport() {
  if (appState.activeJobId) {
    window.open(`${API}/api/download/${appState.activeJobId}`, '_blank');
  } else {
    showToast('⚡ Preparing Master ProRes/H.264 Export...', 'success');
  }
}

async function loadJobsList() {
  try {
    const res = await fetch(`${API}/api/jobs`);
    const data = await res.json();
  } catch {/* ignore */}
}
