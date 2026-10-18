/**
 * ULTRA V5.6 — Comprehensive Drag & Drop & Upload Event Listener
 * Binds dropped/selected video files to Global State, HTML5 Video Engine,
 * Viewport Canvas, NLE Timeline Clips, and sends POST /api/upload request.
 */

document.addEventListener('DOMContentLoaded', () => {
  const fileInput = document.getElementById('fileInput');

  // 1. GLOBAL WINDOW DRAG & DROP LISTENERS (Drop video anywhere in browser!)
  ['dragenter', 'dragover'].forEach(evtName => {
    window.addEventListener(evtName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      document.body.classList.add('global-drag-active');
    });
  });

  ['dragleave', 'drop'].forEach(evtName => {
    window.addEventListener(evtName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      document.body.classList.remove('global-drag-active');
    });
  });

  window.addEventListener('drop', (e) => {
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
      handleSelectedFile(e.dataTransfer.files[0]);
    }
  });

  // 2. MANUAL FILE INPUT CHANGE LISTENER
  if (fileInput) {
    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length) {
        handleSelectedFile(e.target.files[0]);
      }
    });
  }

  // 3. MINI UPLOAD BOX CLICK LISTENER
  const uploadBoxes = document.querySelectorAll('.upload-mini-box, #dropZone');
  uploadBoxes.forEach(box => {
    box.addEventListener('click', (e) => {
      if (fileInput) fileInput.click();
    });
  });
});

function handleSelectedFile(file) {
  if (!file) return;

  const allowed = ['mp4', 'mov', 'avi', 'webm', 'mkv', 'm4v', 'flv'];
  const ext = file.name.split('.').pop().toLowerCase();

  if (!allowed.includes(ext)) {
    if (window.showToast) window.showToast(`❌ Unsupported format: .${ext}`, 'error');
    return;
  }

  console.log('[Upload] File selected:', file.name, file.size, 'bytes');

  // Trigger master binding in app.js
  if (window.bindUploadedFile) {
    window.bindUploadedFile(file);
  }
}
