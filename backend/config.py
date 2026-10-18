"""
ULTRA V5.6 Enterprise Engine — Configuration Module
Handles encrypted key storage and application settings.
Zero-crash fallback for all environments.
"""
import os
import json
import base64
from pathlib import Path
from typing import Optional
from functools import lru_cache

from dotenv import load_dotenv

# ── Load .env from project root ────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
ENV_FILE = ROOT_DIR / ".env"
DATA_DIR = ROOT_DIR / "data"
TASKS_DIR = ROOT_DIR / "tasks"
KEY_FILE = DATA_DIR / ".keystore"

DATA_DIR.mkdir(exist_ok=True)
TASKS_DIR.mkdir(exist_ok=True)
load_dotenv(ENV_FILE)

# ── Logger Fallback ─────────────────────────────────────────────────────────────
try:
    from loguru import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger = logging.getLogger("ULTRA_V56")
    logger.success = logger.info  # type: ignore

# ── Encryption Key Management ──────────────────────────────────────────────────
try:
    from cryptography.fernet import Fernet
    def _get_or_create_fernet_key() -> bytes:
        if KEY_FILE.exists():
            return KEY_FILE.read_bytes()
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        return key
    _FERNET = Fernet(_get_or_create_fernet_key())
    def encrypt_value(plaintext: str) -> str:
        return _FERNET.encrypt(plaintext.encode()).decode()
    def decrypt_value(token: str) -> str:
        return _FERNET.decrypt(token.encode()).decode()
except Exception:
    # Pure Python XOR + Base64 fallback if cryptography is unavailable
    _KEY = b"ULTRA_V56_DEFAULT_SECRET_KEY_32"
    def encrypt_value(plaintext: str) -> str:
        encoded = bytes([b ^ _KEY[i % len(_KEY)] for i, b in enumerate(plaintext.encode())])
        return base64.urlsafe_b64encode(encoded).decode()
    def decrypt_value(token: str) -> str:
        raw = base64.urlsafe_b64decode(token.encode())
        return bytes([b ^ _KEY[i % len(_KEY)] for i, b in enumerate(raw)]).decode()


# ── Application Settings ───────────────────────────────────────────────────────
class Settings:
    def __init__(self):
        self.binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
        self.binance_secret_key: str = os.getenv("BINANCE_SECRET_KEY", "")
        self.bybit_api_key: str = os.getenv("BYBIT_API_KEY", "")
        self.bybit_secret_key: str = os.getenv("BYBIT_SECRET_KEY", "")
        self.kucoin_api_key: str = os.getenv("KUCOIN_API_KEY", "")
        self.kucoin_secret_key: str = os.getenv("KUCOIN_SECRET_KEY", "")
        self.kucoin_passphrase: str = os.getenv("KUCOIN_PASSPHRASE", "")

        self.alpha_vantage_key: str = os.getenv("ALPHA_VANTAGE_KEY", "")
        self.coingecko_api_key: str = os.getenv("COINGECKO_API_KEY", "")

        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

        self.paper_trading: bool = os.getenv("PAPER_TRADING", "true").lower() in ("true", "1", "yes")
        self.max_risk_percent: float = float(os.getenv("MAX_RISK_PERCENT", "1.0"))
        self.default_exchange: str = os.getenv("DEFAULT_EXCHANGE", "binance")
        self.base_currency: str = os.getenv("BASE_CURRENCY", "USDT")
        self.initial_paper_balance: float = float(os.getenv("INITIAL_PAPER_BALANCE", "10000.0"))

        self.app_host: str = os.getenv("APP_HOST", "0.0.0.0")
        self.app_port: int = int(os.getenv("APP_PORT", "8000"))
        self.secret_key: str = os.getenv("SECRET_KEY", "ultra_v56_secret")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")

        # Gemini AI
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.gemini_fallback_model: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash-lite")

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    mode = "📄 PAPER" if s.paper_trading else "🔴 LIVE"
    logger.info(f"ULTRA V5.6 settings loaded | Trading Mode: {mode} | Exchange: {s.default_exchange.upper()}")
    return s


# ── Tracked Assets ─────────────────────────────────────────────────────────────
CRYPTO_SYMBOLS = [
    {"id": "bitcoin",       "symbol": "BTC",  "pair": "BTCUSDT"},
    {"id": "ethereum",      "symbol": "ETH",  "pair": "ETHUSDT"},
    {"id": "solana",        "symbol": "SOL",  "pair": "SOLUSDT"},
    {"id": "binancecoin",   "symbol": "BNB",  "pair": "BNBUSDT"},
    {"id": "ripple",        "symbol": "XRP",  "pair": "XRPUSDT"},
    {"id": "cardano",       "symbol": "ADA",  "pair": "ADAUSDT"},
    {"id": "avalanche-2",   "symbol": "AVAX", "pair": "AVAXUSDT"},
    {"id": "dogecoin",      "symbol": "DOGE", "pair": "DOGEUSDT"},
]

COMMODITY_SYMBOLS = [
    {"id": "XAUUSD", "symbol": "GOLD", "name": "Gold / USD"},
    {"id": "EURUSD", "symbol": "EUR",  "name": "EUR / USD"},
    {"id": "AAPL",   "symbol": "AAPL", "name": "Apple Inc."},
    {"id": "NVDA",   "symbol": "NVDA", "name": "NVIDIA Corp."},
]

# ── Trading Strategy Defaults ──────────────────────────────────────────────────
STRATEGY_CONFIG = {
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "ema_fast": 20,
    "ema_slow": 50,
    "ema_long": 200,
    "volume_spike_multiplier": 2.0,
    "stop_loss_percent": 2.0,
    "take_profit_percent": 4.0,
    "trailing_stop_percent": 1.5,
    "signal_score_threshold": 65,
}

DB_PATH = DATA_DIR / "ultra_v56.db"
LOG_PATH = DATA_DIR / "ultra_v56.log"
