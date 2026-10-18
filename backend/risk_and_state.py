"""
ULTRA V5.6 Enterprise Engine — Risk Management, SL/TP Engine & State Persistence
=================================================================================
Module: backend/risk_and_state.py

Provides four production-grade subsystems:
  1. RiskEngine       — Position sizing, max-risk enforcement, circuit breaker
  2. SLTPEngine       — ATR/percentage SL/TP + trailing stop tracker
  3. BinanceGuard     — Async rate-limit / HTTP 429 / 418 resilience wrapper
  4. StateManager     — SQLite-backed persistence with crash recovery

All classes are designed for direct integration with market_agent.py and
the autopilot_worker loop in main.py.
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import httpx

from .config import logger, DATA_DIR

# ── SQLite import with graceful fallback to JSON file store ───────────────────
try:
    import aiosqlite
    _SQLITE_AVAILABLE = True
except ImportError:
    _SQLITE_AVAILABLE = False
    logger.warning("aiosqlite not found — falling back to JSON file state store")


# ── Constants ─────────────────────────────────────────────────────────────────
DB_PATH         = DATA_DIR / "ultra_v56_state.db"
JSON_STATE_PATH = DATA_DIR / "ultra_v56_state.json"

DEFAULT_RISK_PCT        = 0.01   # 1% of account per trade
MAX_RISK_PCT            = 0.02   # Hard ceiling: 2%
CIRCUIT_BREAKER_PCT     = 0.05   # 5% daily equity drawdown → pause auto-pilot
TRAILING_ACTIVATION_PCT = 0.01   # Trailing stop activates after 1% profit


# ══════════════════════════════════════════════════════════════════════════════
#  1. RISK ENGINE — Position Sizing & Circuit Breaker
# ══════════════════════════════════════════════════════════════════════════════
class RiskEngine:
    """
    Manages per-trade position sizing based on account balance and SL distance,
    enforces a max daily drawdown circuit breaker, and tracks daily equity.
    """

    def __init__(self, initial_balance: float, risk_pct: float = DEFAULT_RISK_PCT):
        self._initial_balance = initial_balance
        self._risk_pct        = min(risk_pct, MAX_RISK_PCT)  # never exceed 2%
        self._day_start_equity: float = initial_balance
        self._current_day: date       = date.today()
        self._tripped: bool           = False   # circuit breaker state

    # ── Core position-sizing formula ──────────────────────────────────────────
    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        risk_pct: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Calculates the optimal position size (quantity) using fixed fractional
        risk management.

        Formula:
            risk_amount  = account_balance × risk_pct
            risk_per_unit= |entry_price - stop_loss_price|
            quantity     = risk_amount / risk_per_unit

        Returns:
            (quantity, risk_amount_usdt)

        Raises:
            ValueError if stop_loss is on wrong side of entry or too close.
        """
        pct = min(risk_pct or self._risk_pct, MAX_RISK_PCT)

        if entry_price <= 0 or stop_loss_price <= 0:
            raise ValueError("Prices must be positive")

        risk_per_unit = abs(entry_price - stop_loss_price)
        if risk_per_unit < entry_price * 0.001:  # SL within 0.1% of entry
            raise ValueError(
                f"Stop-loss too tight: {risk_per_unit:.6f} USDT per unit "
                f"(entry={entry_price}, sl={stop_loss_price})"
            )

        risk_amount = account_balance * pct
        quantity    = risk_amount / risk_per_unit

        # Safety: cap position to 25% of balance regardless
        max_quantity     = (account_balance * 0.25) / entry_price
        quantity         = min(quantity, max_quantity)
        actual_risk_usdt = quantity * risk_per_unit

        logger.info(
            f"[RiskEngine] Sizing: balance=${account_balance:,.2f} | "
            f"risk={pct*100:.1f}% (${actual_risk_usdt:.2f}) | "
            f"entry={entry_price} | sl={stop_loss_price} | qty={quantity:.6f}"
        )
        return round(quantity, 6), round(actual_risk_usdt, 4)

    # ── Max-spend sizing (fallback when SL unknown) ───────────────────────────
    def size_by_spend(
        self,
        account_balance: float,
        entry_price: float,
        risk_pct: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Simple risk-based spend sizing when a precise SL price is unavailable.
        Spends risk_pct% of balance and returns (quantity, spend_usdt).
        """
        pct       = min(risk_pct or self._risk_pct, MAX_RISK_PCT)
        spend     = account_balance * pct
        quantity  = spend / entry_price
        return round(quantity, 6), round(spend, 4)

    # ── Circuit Breaker: Daily Drawdown Guard ─────────────────────────────────
    def refresh_day(self, current_equity: float):
        """Call once per autopilot cycle to reset daily baseline at day rollover."""
        today = date.today()
        if today != self._current_day:
            logger.info(f"[CircuitBreaker] New trading day — resetting baseline to ${current_equity:,.2f}")
            self._current_day     = today
            self._day_start_equity = current_equity
            self._tripped         = False

    def check_circuit_breaker(self, current_equity: float) -> bool:
        """
        Returns True if trading should be HALTED (circuit breaker tripped).
        Trips if today's equity drawdown exceeds CIRCUIT_BREAKER_PCT (default 5%).
        """
        if self._tripped:
            return True  # already tripped

        drawdown = (self._day_start_equity - current_equity) / self._day_start_equity
        if drawdown >= CIRCUIT_BREAKER_PCT:
            self._tripped = True
            logger.critical(
                f"[CircuitBreaker] TRIPPED — Daily drawdown {drawdown*100:.2f}% "
                f"exceeds {CIRCUIT_BREAKER_PCT*100:.0f}% limit! "
                f"Start={self._day_start_equity:.2f}, Now={current_equity:.2f}"
            )
        return self._tripped

    def reset_circuit_breaker(self):
        """Manual reset (admin action via API endpoint)."""
        self._tripped = False
        logger.warning("[CircuitBreaker] Manually RESET by operator")

    @property
    def is_tripped(self) -> bool:
        return self._tripped


# ══════════════════════════════════════════════════════════════════════════════
#  2. SL/TP ENGINE — Dynamic Stop-Loss & Take-Profit
# ══════════════════════════════════════════════════════════════════════════════
class SLTPEngine:
    """
    Calculates entry-time Stop-Loss and Take-Profit levels using:
      - ATR-based method (primary, requires kline data)
      - Percentage-based method (fallback)

    Also implements a TrailingStop tracker per position.
    """

    def __init__(self, rr_ratio: float = 2.0, atr_multiplier: float = 1.5):
        """
        Args:
            rr_ratio       : Risk:Reward ratio (default 1:2 → TP = 2× the SL distance)
            atr_multiplier : SL = entry ± (ATR × multiplier)
        """
        self.rr_ratio       = rr_ratio
        self.atr_multiplier = atr_multiplier

    # ── ATR calculation ───────────────────────────────────────────────────────
    @staticmethod
    def calculate_atr(high_prices: List[float], low_prices: List[float],
                      close_prices: List[float], period: int = 14) -> float:
        """
        Wilder's ATR (Average True Range).
        Requires at least `period+1` candles of high/low/close data.
        Falls back to simple high-low range if data is insufficient.
        """
        n = min(len(high_prices), len(low_prices), len(close_prices))
        if n < 2:
            return close_prices[-1] * 0.015 if close_prices else 0.0  # 1.5% fallback

        true_ranges = []
        for i in range(1, n):
            tr = max(
                high_prices[i]  - low_prices[i],
                abs(high_prices[i]  - close_prices[i - 1]),
                abs(low_prices[i]   - close_prices[i - 1]),
            )
            true_ranges.append(tr)

        if len(true_ranges) < period:
            return sum(true_ranges) / len(true_ranges)

        # Wilder's smoothing
        atr = sum(true_ranges[:period]) / period
        for tr in true_ranges[period:]:
            atr = (atr * (period - 1) + tr) / period
        return round(atr, 8)

    # ── Primary: ATR-based SL/TP ──────────────────────────────────────────────
    def calculate_atr_sltp(
        self,
        side: str,  # "BUY" or "SELL"
        entry_price: float,
        atr: float,
    ) -> Tuple[float, float]:
        """
        BUY:   SL = entry - (atr * multiplier)   | TP = entry + SL_distance * rr_ratio
        SELL:  SL = entry + (atr * multiplier)   | TP = entry - SL_distance * rr_ratio
        Returns (stop_loss_price, take_profit_price).
        """
        sl_distance = atr * self.atr_multiplier

        if side.upper() == "BUY":
            sl = entry_price - sl_distance
            tp = entry_price + sl_distance * self.rr_ratio
        else:  # SELL / SHORT
            sl = entry_price + sl_distance
            tp = entry_price - sl_distance * self.rr_ratio

        logger.debug(
            f"[SLTP-ATR] {side} @ {entry_price:.4f} | "
            f"ATR={atr:.4f} | SL={sl:.4f} | TP={tp:.4f}"
        )
        return round(sl, 6), round(tp, 6)

    # ── Fallback: Percentage-based SL/TP ─────────────────────────────────────
    def calculate_pct_sltp(
        self,
        side: str,
        entry_price: float,
        sl_pct: float = 0.02,   # 2% stop-loss
    ) -> Tuple[float, float]:
        """
        Percentage-based SL/TP using fixed risk-reward ratio.
        Returns (stop_loss_price, take_profit_price).
        """
        if side.upper() == "BUY":
            sl = entry_price * (1 - sl_pct)
            tp = entry_price * (1 + sl_pct * self.rr_ratio)
        else:
            sl = entry_price * (1 + sl_pct)
            tp = entry_price * (1 - sl_pct * self.rr_ratio)

        return round(sl, 6), round(tp, 6)

    # ── Best-effort: Auto-select ATR or fallback ──────────────────────────────
    def calculate(
        self,
        side: str,
        entry_price: float,
        highs: Optional[List[float]] = None,
        lows: Optional[List[float]] = None,
        closes: Optional[List[float]] = None,
        sl_pct_fallback: float = 0.02,
    ) -> Tuple[float, float]:
        """
        Master SL/TP calculator. Uses ATR if candle data is available,
        otherwise falls back to percentage method.
        Returns (stop_loss_price, take_profit_price).
        """
        if highs and lows and closes and len(closes) >= 15:
            atr = self.calculate_atr(highs, lows, closes)
            if atr > 0:
                return self.calculate_atr_sltp(side, entry_price, atr)

        logger.debug(f"[SLTP] Insufficient OHLC data — using {sl_pct_fallback*100:.1f}% fallback")
        return self.calculate_pct_sltp(side, entry_price, sl_pct_fallback)


class TrailingStop:
    """
    Per-position trailing stop tracker.
    Maintains the highest/lowest favorable price seen since entry and
    ratchets the SL level upward (for longs) or downward (for shorts).
    """

    def __init__(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        initial_sl: float,
        trail_pct: float = 0.015,          # trail 1.5% behind best price
        activation_pct: float = TRAILING_ACTIVATION_PCT,
    ):
        self.symbol         = symbol
        self.side           = side.upper()
        self.entry_price    = entry_price
        self.initial_sl     = initial_sl
        self.current_sl     = initial_sl
        self.trail_pct      = trail_pct
        self.activation_pct = activation_pct
        self._best_price    = entry_price
        self._activated     = False

    def update(self, current_price: float) -> Tuple[float, bool]:
        """
        Update with latest price. Returns (new_sl, sl_was_moved).
        Call this on every price tick for the position.
        """
        moved = False

        if self.side == "BUY":
            # Activate only after price moves activation_pct above entry
            if not self._activated:
                if current_price >= self.entry_price * (1 + self.activation_pct):
                    self._activated = True
                    logger.debug(f"[TrailingStop] {self.symbol} LONG — trailing activated at {current_price:.4f}")

            if self._activated and current_price > self._best_price:
                self._best_price = current_price
                new_sl = round(current_price * (1 - self.trail_pct), 6)
                if new_sl > self.current_sl:
                    self.current_sl = new_sl
                    moved = True
                    logger.info(
                        f"[TrailingStop] {self.symbol} LONG SL moved → {new_sl:.4f} "
                        f"(best={current_price:.4f})"
                    )
        else:  # SELL / SHORT
            if not self._activated:
                if current_price <= self.entry_price * (1 - self.activation_pct):
                    self._activated = True

            if self._activated and current_price < self._best_price:
                self._best_price = current_price
                new_sl = round(current_price * (1 + self.trail_pct), 6)
                if new_sl < self.current_sl:
                    self.current_sl = new_sl
                    moved = True
                    logger.info(
                        f"[TrailingStop] {self.symbol} SHORT SL moved → {new_sl:.4f}"
                    )

        return self.current_sl, moved

    def is_stopped_out(self, current_price: float) -> bool:
        """Returns True if price has crossed the trailing SL."""
        if self.side == "BUY":
            return current_price <= self.current_sl
        return current_price >= self.current_sl


# ══════════════════════════════════════════════════════════════════════════════
#  3. BINANCE GUARD — Rate-Limit & 429/418 Resilience
# ══════════════════════════════════════════════════════════════════════════════
class BinanceGuard:
    """
    Async HTTP wrapper around the Binance REST API with:
      - Exponential backoff + full jitter on any transient error
      - Explicit HTTP 429 (Too Many Requests) handler respecting Retry-After
      - HTTP 418 (IP ban) handler with extended cool-down
      - Request-level semaphore to prevent concurrent burst overload
    """

    MAX_RETRIES  = 6
    BASE_DELAY   = 0.5    # seconds
    MAX_DELAY    = 60.0   # cap jitter ceiling
    CONCURRENCY  = 3      # max simultaneous Binance requests

    def __init__(self):
        self._semaphore = asyncio.Semaphore(self.CONCURRENCY)
        self._client: Optional[httpx.AsyncClient] = None
        self._banned_until: float = 0.0   # epoch time when ban lifts

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                headers={"User-Agent": "ULTRA-V56-TradeEngine/5.6"},
            )
        return self._client

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Rate-limit–resilient GET request with exponential backoff."""
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Rate-limit–resilient POST request."""
        return await self._request("POST", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        attempt = 0
        while attempt < self.MAX_RETRIES:
            # Respect active IP ban period
            ban_wait = self._banned_until - time.time()
            if ban_wait > 0:
                logger.warning(f"[BinanceGuard] IP ban active — waiting {ban_wait:.1f}s before retrying")
                await asyncio.sleep(ban_wait)

            async with self._semaphore:
                try:
                    client = await self._get_client()
                    resp   = await client.request(method, url, **kwargs)

                    # ── 429: Too Many Requests ─────────────────────────────
                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get("Retry-After", 10))
                        logger.warning(
                            f"[BinanceGuard] HTTP 429 — rate limited. "
                            f"Sleeping {retry_after:.0f}s (attempt {attempt+1}/{self.MAX_RETRIES})"
                        )
                        await asyncio.sleep(retry_after)
                        attempt += 1
                        continue

                    # ── 418: IP banned ─────────────────────────────────────
                    if resp.status_code == 418:
                        ban_seconds = float(resp.headers.get("Retry-After", 120))
                        self._banned_until = time.time() + ban_seconds
                        logger.critical(
                            f"[BinanceGuard] HTTP 418 — IP banned for {ban_seconds:.0f}s! "
                            f"All requests paused."
                        )
                        await asyncio.sleep(ban_seconds)
                        attempt += 1
                        continue

                    return resp

                except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                    delay = self._backoff_delay(attempt)
                    logger.warning(
                        f"[BinanceGuard] Network error on attempt {attempt+1}: {e} "
                        f"— retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    attempt += 1

        raise RuntimeError(
            f"[BinanceGuard] All {self.MAX_RETRIES} retries exhausted for {url}"
        )

    def _backoff_delay(self, attempt: int) -> float:
        """Full jitter exponential backoff: random(0, min(cap, base * 2^attempt))"""
        import random
        cap   = min(self.MAX_DELAY, self.BASE_DELAY * (2 ** attempt))
        jitter = random.uniform(0, cap)
        return jitter

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ══════════════════════════════════════════════════════════════════════════════
#  4. STATE MANAGER — SQLite Persistence with JSON Fallback
# ══════════════════════════════════════════════════════════════════════════════
class StateManager:
    """
    Persistent trade state storage using SQLite (aiosqlite) when available,
    with a thread-safe JSON file fallback.

    Persists:
      - Active positions (entry, quantity, SL, TP, trailing stop, direction)
      - Paper account balance
      - Order history (last 500 orders)

    On startup, call `load()` to recover all active positions and balance
    from the previous session automatically.
    """

    def __init__(self):
        self._use_sqlite = _SQLITE_AVAILABLE
        self._lock       = asyncio.Lock()
        self._db_path    = str(DB_PATH)
        self._json_path  = JSON_STATE_PATH

    # ── Initialisation ────────────────────────────────────────────────────────
    async def init(self):
        """Create tables or JSON file on first run."""
        if self._use_sqlite:
            await self._init_sqlite()
        else:
            await self._init_json()
        logger.info(f"[StateManager] Initialized ({'SQLite' if self._use_sqlite else 'JSON'} backend)")

    async def _init_sqlite(self):
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol       TEXT PRIMARY KEY,
                    side         TEXT NOT NULL,
                    quantity     REAL NOT NULL,
                    entry_price  REAL NOT NULL,
                    current_price REAL NOT NULL,
                    stop_loss    REAL,
                    take_profit  REAL,
                    trail_pct    REAL,
                    unrealized_pnl REAL DEFAULT 0,
                    pnl_pct      REAL DEFAULT 0,
                    opened_at    TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS balance (
                    id           INTEGER PRIMARY KEY CHECK (id = 1),
                    available    REAL NOT NULL,
                    initial      REAL NOT NULL,
                    updated_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id           TEXT PRIMARY KEY,
                    symbol       TEXT NOT NULL,
                    side         TEXT NOT NULL,
                    order_type   TEXT NOT NULL,
                    quantity     REAL NOT NULL,
                    filled_price REAL,
                    stop_loss    REAL,
                    take_profit  REAL,
                    pnl          REAL,
                    status       TEXT NOT NULL,
                    paper        INTEGER DEFAULT 1,
                    created_at   TEXT NOT NULL,
                    filled_at    TEXT
                );

                CREATE TABLE IF NOT EXISTS daily_state (
                    trade_date   TEXT PRIMARY KEY,
                    start_equity REAL NOT NULL,
                    cb_tripped   INTEGER DEFAULT 0
                );
            """)
            await db.commit()

    async def _init_json(self):
        async with self._lock:
            if not self._json_path.exists():
                self._json_path.write_text(json.dumps({
                    "positions": {},
                    "balance": {"available": 0.0, "initial": 0.0, "updated_at": ""},
                    "orders": [],
                    "daily_state": {}
                }, indent=2))

    # ── BALANCE ───────────────────────────────────────────────────────────────
    async def save_balance(self, available: float, initial: float):
        ts = datetime.utcnow().isoformat()
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO balance (id, available, initial, updated_at) VALUES (1,?,?,?)",
                    (available, initial, ts)
                )
                await db.commit()
        else:
            await self._json_update(lambda d: d.update({
                "balance": {"available": available, "initial": initial, "updated_at": ts}
            }))

    async def load_balance(self) -> Optional[Tuple[float, float]]:
        """Returns (available_balance, initial_balance) or None if no record."""
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                async with db.execute("SELECT available, initial FROM balance WHERE id=1") as cur:
                    row = await cur.fetchone()
                    return (row[0], row[1]) if row else None
        else:
            data = await self._json_read()
            b = data.get("balance", {})
            return (b["available"], b["initial"]) if b.get("available") else None

    # ── POSITIONS ─────────────────────────────────────────────────────────────
    async def save_position(self, pos: Dict[str, Any]):
        """
        Upsert a position record. pos dict must contain:
            symbol, side, quantity, entry_price, current_price,
            stop_loss, take_profit, trail_pct, unrealized_pnl, pnl_pct, opened_at
        """
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO positions
                    (symbol, side, quantity, entry_price, current_price,
                     stop_loss, take_profit, trail_pct, unrealized_pnl, pnl_pct, opened_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    pos["symbol"], pos["side"], pos["quantity"],
                    pos["entry_price"], pos.get("current_price", pos["entry_price"]),
                    pos.get("stop_loss"), pos.get("take_profit"), pos.get("trail_pct"),
                    pos.get("unrealized_pnl", 0.0), pos.get("pnl_pct", 0.0),
                    pos.get("opened_at", datetime.utcnow().isoformat())
                ))
                await db.commit()
        else:
            await self._json_update(
                lambda d: d["positions"].update({pos["symbol"]: pos})
            )

    async def load_positions(self) -> List[Dict[str, Any]]:
        """Returns all persisted active positions."""
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM positions") as cur:
                    rows = await cur.fetchall()
                    return [dict(r) for r in rows]
        else:
            data = await self._json_read()
            return list(data.get("positions", {}).values())

    async def delete_position(self, symbol: str):
        """Remove a closed position from the store."""
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
                await db.commit()
        else:
            await self._json_update(
                lambda d: d["positions"].pop(symbol, None)
            )

    async def update_position_price(self, symbol: str, current_price: float,
                                     unrealized_pnl: float, pnl_pct: float,
                                     current_sl: Optional[float] = None):
        """Lightweight price-only update (no full upsert needed on every tick)."""
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                if current_sl is not None:
                    await db.execute(
                        "UPDATE positions SET current_price=?, unrealized_pnl=?, pnl_pct=?, stop_loss=? WHERE symbol=?",
                        (current_price, unrealized_pnl, pnl_pct, current_sl, symbol)
                    )
                else:
                    await db.execute(
                        "UPDATE positions SET current_price=?, unrealized_pnl=?, pnl_pct=? WHERE symbol=?",
                        (current_price, unrealized_pnl, pnl_pct, symbol)
                    )
                await db.commit()
        else:
            async with self._lock:
                data = await self._json_read()
                if symbol in data["positions"]:
                    data["positions"][symbol].update({
                        "current_price": current_price,
                        "unrealized_pnl": unrealized_pnl,
                        "pnl_pct": pnl_pct,
                    })
                    if current_sl is not None:
                        data["positions"][symbol]["stop_loss"] = current_sl
                    self._json_path.write_text(json.dumps(data, indent=2, default=str))

    # ── ORDER HISTORY ─────────────────────────────────────────────────────────
    async def save_order(self, order: Dict[str, Any]):
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("""
                    INSERT OR IGNORE INTO orders
                    (id, symbol, side, order_type, quantity, filled_price,
                     stop_loss, take_profit, pnl, status, paper, created_at, filled_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    order.get("id", ""), order["symbol"], order["side"],
                    order.get("order_type", "MARKET"), order["quantity"],
                    order.get("filled_price"), order.get("stop_loss"),
                    order.get("take_profit"), order.get("pnl"),
                    order.get("status", "FILLED"), int(order.get("paper", True)),
                    order.get("created_at", datetime.utcnow().isoformat()),
                    order.get("filled_at")
                ))
                await db.commit()
        else:
            await self._json_update(lambda d: (
                d["orders"].append(order),
                d["orders"].__setitem__(slice(None), d["orders"][-500:])  # keep last 500
            ))

    async def get_order_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
                ) as cur:
                    return [dict(r) for r in await cur.fetchall()]
        else:
            data = await self._json_read()
            return list(reversed(data.get("orders", [])))[:limit]

    # ── DAILY STATE (Circuit Breaker Persistence) ─────────────────────────────
    async def save_daily_state(self, trade_date: str, start_equity: float, cb_tripped: bool):
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO daily_state (trade_date, start_equity, cb_tripped) VALUES (?,?,?)",
                    (trade_date, start_equity, int(cb_tripped))
                )
                await db.commit()
        else:
            await self._json_update(lambda d: d["daily_state"].update({
                trade_date: {"start_equity": start_equity, "cb_tripped": int(cb_tripped)}
            }))

    async def load_daily_state(self, trade_date: str) -> Optional[Dict[str, Any]]:
        if self._use_sqlite:
            async with aiosqlite.connect(self._db_path) as db:
                async with db.execute(
                    "SELECT * FROM daily_state WHERE trade_date=?", (trade_date,)
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        return {"start_equity": row[1], "cb_tripped": bool(row[2])}
                    return None
        else:
            data = await self._json_read()
            return data.get("daily_state", {}).get(trade_date)

    # ── JSON helpers ──────────────────────────────────────────────────────────
    async def _json_read(self) -> dict:
        async with self._lock:
            try:
                return json.loads(self._json_path.read_text())
            except Exception:
                return {"positions": {}, "balance": {}, "orders": [], "daily_state": {}}

    async def _json_update(self, mutator):
        async with self._lock:
            data = json.loads(self._json_path.read_text())
            mutator(data)
            self._json_path.write_text(json.dumps(data, indent=2, default=str))


# ── Module-level singletons ───────────────────────────────────────────────────
_risk_engine:   Optional[RiskEngine]   = None
_sltp_engine:   Optional[SLTPEngine]   = None
_state_manager: Optional[StateManager] = None
_binance_guard: Optional[BinanceGuard] = None


def get_risk_engine(initial_balance: float = 10000.0) -> RiskEngine:
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskEngine(initial_balance)
    return _risk_engine


def get_sltp_engine() -> SLTPEngine:
    global _sltp_engine
    if _sltp_engine is None:
        _sltp_engine = SLTPEngine()
    return _sltp_engine


def get_state_manager() -> StateManager:
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


def get_binance_guard() -> BinanceGuard:
    global _binance_guard
    if _binance_guard is None:
        _binance_guard = BinanceGuard()
    return _binance_guard
