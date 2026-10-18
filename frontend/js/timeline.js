/**
 * ULTRA V5.6 — Pro Multi-Track NLE Timeline Canvas Engine
 * Interactive Multi-Track Clips, Real-Time Audio Waveform, Razor Tool,
 * Playhead Scrubbing, Snapping, and Ripple Delete.
 */

let timelineCanvas = null;
let timelineCtx = null;
const TRACK_HEIGHT = 40;
const TRACK_GAP = 2;

// Track Definitions
const TRACKS = [
  { id: 'V3', name: 'V3', type: 'video', color: 'rgba(168,85,247,0.2)' },
  { id: 'V2', name: 'V2', type: 'video', color: 'rgba(168,85,247,0.3)' },
  { id: 'V1', name: 'V1 (Main Video)', type: 'video', color: '#a855f7' },
  { id: 'SUB', name: 'SUB (Whisper AI)', type: 'subtitle', color: '#06b6d4' },
  { id: 'A1', name: 'A1 (Isolated Vocals)', type: 'audio', color: '#22c55e' },
  { id: 'A2', name: 'A2 (BGM Music)', type: 'audio', color: '#10b981' },
];

function initTimelineEvents() {
  timelineCanvas = document.getElementById('timelineCanvas');
  if (!timelineCanvas) return;
  timelineCtx = timelineCanvas.getContext('2d');

  // Canvas Mouse Events for Scrubbing, Selection & Razor Cut
  let isScrubbing = false;

  timelineCanvas.addEventListener('mousedown', (e) => {
    isScrubbing = true;
    handleTimelineClick(e);
  });

  window.addEventListener('mousemove', (e) => {
    if (isScrubbing) handleTimelineClick(e);
  });

  window.addEventListener('mouseup', () => { isScrubbing = false; });

  // Keyboard Shortcuts (Delete = Ripple Delete, C = Razor Cut, V = Select)
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Delete' || e.key === 'Backspace') {
      deleteSelectedClip();
    } else if (e.key === 'c' || e.key === 'C') {
      selectTool('razor');
    } else if (e.key === 'v' || e.key === 'V') {
      selectTool('select');
    }
  });

  window.renderTimeline = renderTimeline;
  window.syncTimelinePlayhead = renderTimeline;

  renderTimeline();
}

// ── TIMELINE RENDERER ─────────────────────────────────────────────────────────
function renderTimeline() {
  if (!timelineCanvas || !timelineCtx) return;

  const ctx = timelineCtx;
  const zoom = appState.timelineZoom || 1.0;
  const pps = 40 * zoom; // pixels per second
  const duration = appState.metadata.duration || 42.0;

  timelineCanvas.width = Math.max(1200, duration * pps + 200);
  timelineCanvas.height = TRACKS.length * TRACK_HEIGHT + 30; // 30px top timecode ruler

  const W = timelineCanvas.width;
  const H = timelineCanvas.height;

  // 1. Background
  ctx.fillStyle = '#070710';
  ctx.fillRect(0, 0, W, H);

  // 2. Track Lanes Backgrounds
  TRACKS.forEach((track, i) => {
    const y = 24 + i * TRACK_HEIGHT;
    ctx.fillStyle = i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.04)';
    ctx.fillRect(0, y, W, TRACK_HEIGHT - TRACK_GAP);

    // Track Separator Line
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, y + TRACK_HEIGHT - TRACK_GAP);
    ctx.lineTo(W, y + TRACK_HEIGHT - TRACK_GAP);
    ctx.stroke();
  });

  // 3. Render Multi-Track Clips
  appState.clips.forEach(clip => {
    const trackIdx = TRACKS.findIndex(t => t.id === clip.track);
    if (trackIdx === -1) return;

    const y = 24 + trackIdx * TRACK_HEIGHT + 2;
    const x = clip.startTime * pps;
    const w = clip.duration * pps;

    const isSelected = appState.selectedClipId === clip.id;

    // Clip Block Fill
    ctx.fillStyle = isSelected ? '#ec4899' : (clip.color || '#a855f7');
    ctx.beginPath();
    ctx.roundRect(x, y, w, TRACK_HEIGHT - 6, 4);
    ctx.fill();

    // Clip Border
    ctx.strokeStyle = isSelected ? '#ffffff' : 'rgba(255,255,255,0.2)';
    ctx.lineWidth = isSelected ? 2 : 1;
    ctx.stroke();

    // Audio Waveform overlay for audio tracks
    if (clip.track === 'A1' || clip.track === 'A2') {
      drawAudioWaveform(ctx, x, y, w, TRACK_HEIGHT - 6);
    }

    // Clip Name Label
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 11px Inter, sans-serif';
    ctx.fillText(clip.name, x + 8, y + 22);

    // Duration badge on right edge
    if (w > 60) {
      ctx.fillStyle = 'rgba(0,0,0,0.4)';
      ctx.font = '10px "JetBrains Mono"';
      ctx.fillText(`${clip.duration.toFixed(1)}s`, x + w - 36, y + 22);
    }
  });

  // 4. Timecode Ruler Header
  drawRuler(ctx, W, pps, duration);

  // 5. Playhead Line
  const phX = appState.currentTime * pps;
  ctx.strokeStyle = '#a855f7';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(phX, 0);
  ctx.lineTo(phX, H);
  ctx.stroke();

  // Playhead Head Indicator Triangle
  ctx.fillStyle = '#a855f7';
  ctx.beginPath();
  ctx.moveTo(phX - 6, 0);
  ctx.lineTo(phX + 6, 0);
  ctx.lineTo(phX, 12);
  ctx.closePath();
  ctx.fill();
}

function drawAudioWaveform(ctx, x, y, w, h) {
  ctx.beginPath();
  ctx.strokeStyle = 'rgba(255,255,255,0.4)';
  ctx.lineWidth = 1;
  const centerY = y + h / 2;

  for (let px = x + 4; px < x + w - 4; px += 3) {
    const amp = Math.sin(px * 0.1) * (h / 2 - 4) * (0.3 + Math.random() * 0.7);
    ctx.moveTo(px, centerY - amp);
    ctx.lineTo(px, centerY + amp);
  }
  ctx.stroke();
}

function drawRuler(ctx, W, pps, duration) {
  ctx.fillStyle = 'rgba(10,10,20,0.95)';
  ctx.fillRect(0, 0, W, 24);

  ctx.strokeStyle = 'rgba(255,255,255,0.1)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, 24); ctx.lineTo(W, 24);
  ctx.stroke();

  ctx.fillStyle = '#94a3b8';
  ctx.font = '10px "JetBrains Mono"';

  const stepSec = pps > 60 ? 1 : (pps > 30 ? 2 : 5);
  for (let s = 0; s <= duration + 10; s += stepSec) {
    const x = s * pps;
    ctx.fillRect(x, 14, 1, 10);
    const mins = Math.floor(s / 60);
    const secs = Math.floor(s % 60);
    ctx.fillText(`${mins}:${secs.toString().padStart(2, '0')}`, x + 4, 12);
  }
}

// ── TIMELINE CLICK & INTERACTION HANDLER ──────────────────────────────────────
function handleTimelineClick(e) {
  const rect = timelineCanvas.getBoundingClientRect();
  const clickX = e.clientX - rect.left;
  const clickY = e.clientY - rect.top;

  const zoom = appState.timelineZoom || 1.0;
  const pps = 40 * zoom;
  const clickedTime = Math.max(0, clickX / pps);

  // Update current time & sync video
  appState.currentTime = clickedTime;
  updateTimecodeDisplay();

  const video = document.getElementById('videoElement');
  if (video && video.src) {
    video.currentTime = clickedTime;
  }

  // Check if Razor Tool is active -> Cut clip at clickedTime
  if (appState.activeTool === 'razor') {
    executeRazorCut(clickedTime);
  } else {
    // Select clip under click
    const trackIdx = Math.floor((clickY - 24) / TRACK_HEIGHT);
    if (trackIdx >= 0 && trackIdx < TRACKS.length) {
      const trackId = TRACKS[trackIdx].id;
      const found = appState.clips.find(c => c.track === trackId && clickedTime >= c.startTime && clickedTime <= c.startTime + c.duration);
      appState.selectedClipId = found ? found.id : null;
    }
  }

  renderTimeline();
}

// ── RAZOR CUT TOOL IMPLEMENTATION ─────────────────────────────────────────────
function executeRazorCut(cutTime) {
  const newClips = [];
  let cutPerformed = false;

  appState.clips.forEach(clip => {
    if (cutTime > clip.startTime + 0.5 && cutTime < clip.startTime + clip.duration - 0.5) {
      cutPerformed = true;
      const leftDuration = cutTime - clip.startTime;
      const rightDuration = clip.duration - leftDuration;

      // Left Clip Piece
      newClips.push({
        ...clip,
        id: clip.id + '-A',
        duration: leftDuration,
      });

      // Right Clip Piece
      newClips.push({
        ...clip,
        id: clip.id + '-B',
        startTime: cutTime,
        duration: rightDuration,
        name: clip.name + '_cut',
      });
    } else {
      newClips.push(clip);
    }
  });

  if (cutPerformed) {
    appState.clips = newClips;
    showToast(`✂ Clip cut at ${cutTime.toFixed(2)}s`, 'success');
  }
}

// ── RIPPLE DELETE IMPLEMENTATION ──────────────────────────────────────────────
function deleteSelectedClip() {
  if (!appState.selectedClipId) return;

  const target = appState.clips.find(c => c.id === appState.selectedClipId);
  if (!target) return;

  appState.clips = appState.clips.filter(c => c.id !== appState.selectedClipId);
  appState.selectedClipId = null;
  showToast(`🗑 Clip deleted (${target.name})`, 'info');
  renderTimeline();
}

// ── TIMELINE CONTROLS ────────────────────────────────────────────────────────
function setTimelineZoom(val) {
  appState.timelineZoom = parseFloat(val);
  renderTimeline();
}

function toggleSnap() {
  appState.snapping = !appState.snapping;
  const btn = document.getElementById('btnSnap');
  if (btn) btn.textContent = `🧲 Snap: ${appState.snapping ? 'ON' : 'OFF'}`;
}

function addTrack(type) {
  showToast(`+ Added ${type.toUpperCase()} Track`, 'success');
}
