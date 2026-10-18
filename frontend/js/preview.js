/**
 * ULTRA V5.6 — Interactive Dual-Split Screen Viewport Engine
 * Synchronizes HTML5 Video player with dual WebGL/Canvas comparison layers.
 */

let animFrameId = null;

function initPlayerSync() {
  const video = document.getElementById('videoElement');
  if (!video) return;

  // Video timeupdate sync
  video.ontimeupdate = () => {
    appState.currentTime = video.currentTime;
    updateTimecodeDisplay();
    if (window.syncTimelinePlayhead) window.syncTimelinePlayhead();
  };

  video.onplay = () => {
    appState.isPlaying = true;
    const btn = document.getElementById('btnPlayPause');
    if (btn) btn.textContent = '⏸';
    startCanvasRenderLoop();
  };

  video.onpause = () => {
    appState.isPlaying = false;
    const btn = document.getElementById('btnPlayPause');
    if (btn) btn.textContent = '▶';
    if (animFrameId) cancelAnimationFrame(animFrameId);
  };

  // Resize canvases to container
  window.addEventListener('resize', resizeViewports);
  resizeViewports();
}

function resizeViewports() {
  const cRaw = document.getElementById('canvasRaw');
  const cEnh = document.getElementById('canvasEnhanced');
  if (!cRaw || !cEnh) return;

  const parent = cRaw.parentElement;
  if (parent) {
    cRaw.width = parent.clientWidth;
    cRaw.height = parent.clientHeight;
    cEnh.width = parent.clientWidth;
    cEnh.height = parent.clientHeight;
    renderCanvasFrame();
  }
}

function startCanvasRenderLoop() {
  function loop() {
    renderCanvasFrame();
    if (appState.isPlaying) {
      animFrameId = requestAnimationFrame(loop);
    }
  }
  loop();
}

function renderCanvasFrame() {
  const video = document.getElementById('videoElement');
  const cRaw = document.getElementById('canvasRaw');
  const cEnh = document.getElementById('canvasEnhanced');
  if (!cRaw || !cEnh) return;

  const ctxRaw = cRaw.getContext('2d');
  const ctxEnh = cEnh.getContext('2d');

  const W = cRaw.width;
  const H = cRaw.height;

  if (video && video.readyState >= 2 && video.videoWidth > 0) {
    // 1. RAW CANVAS LAYER (Original video frame)
    ctxRaw.drawImage(video, 0, 0, W, H);

    // 2. ENHANCED CANVAS LAYER (Draw video frame with AI color/contrast filters)
    ctxEnh.filter = buildAIFilterString();
    ctxEnh.drawImage(video, 0, 0, W, H);
    ctxEnh.filter = 'none';

  } else {
    // FALLBACK CANVAS RENDER (When no video file loaded yet)
    ctxRaw.fillStyle = '#0f1020';
    ctxRaw.fillRect(0, 0, W, H);
    ctxRaw.fillStyle = '#475569';
    ctxRaw.font = '14px "JetBrains Mono"';
    ctxRaw.fillText('📹 ORIGINAL RAW VIEWPORT (720P 30FPS)', 30, H / 2);

    const grad = ctxEnh.createLinearGradient(0, 0, W, H);
    grad.addColorStop(0, '#2e1065');
    grad.addColorStop(1, '#065f46');
    ctxEnh.fillStyle = grad;
    ctxEnh.fillRect(0, 0, W, H);

    ctxEnh.fillStyle = '#a855f7';
    ctxEnh.font = 'bold 18px "Inter"';
    ctxEnh.fillText('✨ ULTRA V5.6 AI MASTER (4K 60FPS REAL-ESRGAN)', 30, H / 2);
  }
}

function buildAIFilterString() {
  const sat = appState.inspector.saturation || 1.15;
  const contrast = 1.1;
  const brightness = 1.05;
  return `saturate(${sat}) contrast(${contrast}) brightness(${brightness})`;
}

// ── PLAYBACK CONTROLS ─────────────────────────────────────────────────────────
function togglePlayPause() {
  const video = document.getElementById('videoElement');
  if (video && video.src && video.src !== location.href) {
    if (video.paused) {
      video.play();
    } else {
      video.pause();
    }
  } else {
    // Simulated playback for demo
    appState.isPlaying = !appState.isPlaying;
    const btn = document.getElementById('btnPlayPause');
    if (btn) btn.textContent = appState.isPlaying ? '⏸' : '▶';
    if (appState.isPlaying) {
      startCanvasRenderLoop();
    }
  }
}

function stepFrame(dir) {
  const video = document.getElementById('videoElement');
  const step = 1 / 30; // 1 frame @ 30fps
  if (video && video.src) {
    video.currentTime = Math.max(0, Math.min(video.duration || 42, video.currentTime + dir * step));
  } else {
    appState.currentTime = Math.max(0, Math.min(appState.metadata.duration, appState.currentTime + dir * step));
    updateTimecodeDisplay();
    renderCanvasFrame();
    if (window.syncTimelinePlayhead) window.syncTimelinePlayhead();
  }
}

function toggleFullscreen() {
  const elem = document.getElementById('playerContainer');
  if (!elem) return;
  if (!document.fullscreenElement) {
    elem.requestFullscreen().catch(err => console.warn(err));
  } else {
    document.exitFullscreen();
  }
}

// ── SPLIT SCREEN DRAGGER ──────────────────────────────────────────────────────
function initSplitScreenEvents() {
  const wrapper = document.getElementById('splitWrapper');
  const handle = document.getElementById('splitHandle');
  const layerRaw = document.getElementById('layerRaw');
  let isDragging = false;

  if (!wrapper || !handle || !layerRaw) return;

  function updatePos(x) {
    const rect = wrapper.getBoundingClientRect();
    let pct = ((x - rect.left) / rect.width) * 100;
    pct = Math.max(2, Math.min(98, pct));
    appState.splitPosPct = pct;
    handle.style.left = `${pct}%`;
    layerRaw.style.width = `${pct}%`;
  }

  handle.addEventListener('mousedown', (e) => {
    isDragging = true;
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e) => {
    if (isDragging) updatePos(e.clientX);
  });

  window.addEventListener('mouseup', () => { isDragging = false; });
}

function setSplitMode(mode) {
  appState.splitMode = mode;
  const btnCompare = document.getElementById('btnSplitCompare');
  const btnSingle = document.getElementById('btnSplitSingle');
  const layerRaw = document.getElementById('layerRaw');
  const handle = document.getElementById('splitHandle');

  if (mode === 'single') {
    btnSingle.classList.add('active');
    btnCompare.classList.remove('active');
    layerRaw.style.display = 'none';
    handle.style.display = 'none';
  } else {
    btnCompare.classList.add('active');
    btnSingle.classList.remove('active');
    layerRaw.style.display = 'block';
    handle.style.display = 'flex';
    layerRaw.style.width = '50%';
    handle.style.left = '50%';
  }
}
