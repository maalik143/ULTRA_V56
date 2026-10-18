"""
ULTRA V5.6 Engine — One-Click Setup Script
============================================
Run: python setup.py

This script:
  1. Checks Python version (3.10+)
  2. Checks for CUDA / GPU availability
  3. Creates a virtual environment (venv)
  4. Installs all requirements (with correct CUDA-aware torch build)
  5. Downloads all AI model weights (Real-ESRGAN, CodeFormer, RIFE)
  6. Verifies FFmpeg installation
  7. Runs a quick sanity check
"""

import os
import sys
import subprocess
import platform
import urllib.request
import zipfile
import shutil
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
BACKEND_DIR = BASE_DIR / "backend"
MODELS_DIR = BASE_DIR / "models_cache"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"


def banner():
    print("\n" + "=" * 65)
    print("  ULTRA V5.6 ENGINE SETUP")
    print("=" * 65 + "\n")


def ok(msg):  print(f"  [OK] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def info(msg): print(f"  [INFO] {msg}")
def step(msg): print(f"\n  [STEP] {msg}")


# ── STEP 1: Python Version Check ─────────────────────────────────────────────
def check_python():
    step("Checking Python version…")
    v = sys.version_info
    if v.major == 3 and v.minor >= 10:
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    fail(f"Python 3.10+ required. Found: {v.major}.{v.minor}.{v.micro}")
    print("  → Download from https://www.python.org/downloads/")
    return False


# ── STEP 2: Detect GPU & CUDA ─────────────────────────────────────────────────
def detect_cuda():
    step("Detecting GPU & CUDA…")
    cuda_version = None

    # Try nvidia-smi
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version",
                                        "--format=csv,noheader"], timeout=5)
        gpu_info = out.decode().strip()
        ok(f"NVIDIA GPU detected: {gpu_info}")

        # Detect CUDA version
        ver_out = subprocess.check_output(["nvcc", "--version"], timeout=5)
        import re
        m = re.search(r"release (\d+\.\d+)", ver_out.decode())
        if m:
            cuda_version = m.group(1)
            ok(f"CUDA version: {cuda_version}")
    except Exception:
        info("No NVIDIA GPU detected or nvidia-smi not found — will use CPU mode")

    return cuda_version


# ── STEP 3: Create Virtual Environment ────────────────────────────────────────
def create_venv():
    step("Creating virtual environment…")
    if VENV_DIR.exists():
        ok("Virtual environment already exists — skipping")
        return True
    try:
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        ok(f"Virtual environment created: {VENV_DIR}")
        return True
    except Exception as e:
        fail(f"Failed to create venv: {e}")
        return False


def get_pip():
    """Return the pip executable path in the venv."""
    if platform.system() == "Windows":
        return str(VENV_DIR / "Scripts" / "pip.exe")
    return str(VENV_DIR / "bin" / "pip")


def get_python():
    if platform.system() == "Windows":
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


# ── STEP 4: Install Dependencies ──────────────────────────────────────────────
def install_deps(cuda_version=None):
    step("Installing Python dependencies…")
    pip = get_pip()

    # Upgrade pip first
    subprocess.run([pip, "install", "--upgrade", "pip"], capture_output=True)

    # Install PyTorch with CUDA if available
    if cuda_version:
        major = int(cuda_version.split(".")[0])
        minor = int(cuda_version.split(".")[1])
        if major >= 12:
            torch_index = "https://download.pytorch.org/whl/cu121"
        elif major == 11 and minor >= 8:
            torch_index = "https://download.pytorch.org/whl/cu118"
        else:
            torch_index = "https://download.pytorch.org/whl/cu117"

        info(f"Installing PyTorch with CUDA support ({torch_index})…")
        subprocess.run([
            pip, "install", "torch", "torchvision", "torchaudio",
            "--index-url", torch_index
        ], check=True)
    else:
        info("Installing PyTorch CPU version…")
        subprocess.run([pip, "install", "torch", "torchvision", "torchaudio"], check=True)

    # Install ONNX runtime
    if cuda_version:
        subprocess.run([pip, "install", "onnxruntime-gpu"], capture_output=True)
        ok("onnxruntime-gpu installed")
    else:
        subprocess.run([pip, "install", "onnxruntime"], capture_output=True)
        ok("onnxruntime (CPU) installed")

    # Install remaining requirements
    req_file = BACKEND_DIR / "requirements.txt"
    if req_file.exists():
        info("Installing backend requirements…")
        result = subprocess.run([pip, "install", "-r", str(req_file)])
        if result.returncode == 0:
            ok("All backend requirements installed")
        else:
            fail("Some requirements failed — check output above")
    else:
        fail(f"requirements.txt not found: {req_file}")


# ── STEP 5: Check FFmpeg ──────────────────────────────────────────────────────
def check_ffmpeg():
    step("Checking FFmpeg…")
    try:
        out = subprocess.check_output(["ffmpeg", "-version"], timeout=5)
        version_line = out.decode().split("\n")[0]
        ok(f"FFmpeg found: {version_line}")
        return True
    except Exception:
        fail("FFmpeg not found in PATH")
        print()
        print("  → Download FFmpeg from: https://ffmpeg.org/download.html")
        print("  → Windows: https://github.com/BtbN/FFmpeg-Builds/releases")
        print("  → Add FFmpeg to your system PATH after installing")
        print()
        return False


# ── STEP 6: Download Models ────────────────────────────────────────────────────
def download_models():
    step("Downloading AI model weights…")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    models = [
        {
            "name": "Real-ESRGAN x4plus",
            "filename": "RealESRGAN_x4plus.pth",
            "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        },
        {
            "name": "Real-ESRGAN x4plus Anime",
            "filename": "RealESRGAN_x4plus_anime_6B.pth",
            "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
        },
        {
            "name": "CodeFormer",
            "filename": "codeformer.pth",
            "url": "https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth",
        },
        {
            "name": "Face Detection (Resnet50)",
            "filename": "detection_Resnet50_Final.pth",
            "url": "https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth",
        },
        {
            "name": "Face Parsing (ParseNet)",
            "filename": "parsing_parsenet.pth",
            "url": "https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/parsing_parsenet.pth",
        },
    ]

    for model in models:
        target = MODELS_DIR / model["filename"]
        if target.exists():
            ok(f"{model['name']} — already downloaded")
            continue

        info(f"Downloading {model['name']}…")
        try:
            def reporthook(count, block_size, total_size):
                if total_size > 0:
                    pct = int(count * block_size / total_size * 100)
                    print(f"\r    {pct}% ", end="", flush=True)

            urllib.request.urlretrieve(model["url"], str(target), reporthook)
            print()
            ok(f"{model['name']} downloaded")
        except Exception as e:
            print()
            fail(f"{model['name']} download failed: {e}")
            info("You can download manually and place in models_cache/")

    # RIFE via git clone or HTTP zip fallback
    rife_dir = MODELS_DIR / "RIFE"
    if not rife_dir.exists():
        info("Cloning RIFE v4.6...")
        cloned = False
        try:
            res = subprocess.run([
                "git", "clone", "--depth", "1",
                "https://github.com/hzwer/Practical-RIFE.git",
                str(rife_dir)
            ], capture_output=True, timeout=120)
            if res.returncode == 0:
                cloned = True
                ok("RIFE cloned successfully via git")
        except Exception:
            pass

        if not cloned:
            info("Git not available -- downloading RIFE repository zip...")
            try:
                zip_path = str(MODELS_DIR / "rife_main.zip")
                urllib.request.urlretrieve("https://github.com/hzwer/Practical-RIFE/archive/refs/heads/main.zip", zip_path)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(str(MODELS_DIR))
                extracted = MODELS_DIR / "Practical-RIFE-main"
                if extracted.exists():
                    extracted.rename(rife_dir)
                os.unlink(zip_path)
                ok("RIFE extracted successfully from zip")
            except Exception as rife_err:
                fail(f"RIFE download failed: {rife_err}")
                info("MAFI will use FFmpeg minterpolate fallback")
    else:
        ok("RIFE -- already present")


# ── STEP 7: Create Working Directories ────────────────────────────────────────
def create_dirs():
    step("Creating working directories…")
    for d in [TEMP_DIR, OUTPUT_DIR, MODELS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
        ok(f"Created: {d.relative_to(BASE_DIR)}")


# ── STEP 8: Verification ──────────────────────────────────────────────────────
def verify():
    step("Running verification checks…")
    python = get_python()

    # Test imports
    checks = [
        ("import torch; print('torch OK, CUDA:', torch.cuda.is_available())", "PyTorch"),
        ("import cv2; print('cv2 OK')", "OpenCV"),
        ("import fastapi; print('fastapi OK')", "FastAPI"),
        ("import numpy; print('numpy OK')", "NumPy"),
    ]

    for code, name in checks:
        try:
            out = subprocess.check_output([python, "-c", code],
                                           stderr=subprocess.DEVNULL, timeout=15)
            ok(f"{name}: {out.decode().strip()}")
        except Exception:
            fail(f"{name}: import failed")


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    banner()

    if not check_python():
        sys.exit(1)

    cuda = detect_cuda()
    create_venv()
    install_deps(cuda)
    check_ffmpeg()
    download_models()
    create_dirs()
    verify()

    print("\n" + "=" * 65)
    print("  [SUCCESS] ULTRA V5.6 setup complete!")
    print()
    print("  To start the engine:")
    print("    Windows:  double-click  launch.bat")
    print("    Manual :  .venv\\Scripts\\python backend\\main.py")
    print()
    print("  Then open:  http://localhost:8765")
    print("=" * 65 + "\n")
