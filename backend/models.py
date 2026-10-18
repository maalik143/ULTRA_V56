"""
ULTRA V5.6 Enterprise Engine — Pydantic Data Models
Shared across all backend modules.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────
class SignalType(str, Enum):
    STRONG_BUY  = "STRONG_BUY"
    BUY         = "BUY"
    NEUTRAL     = "NEUTRAL"
    SELL        = "SELL"
    STRONG_SELL = "STRONG_SELL"


class OrderSide(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT  = "LIMIT"


class OrderStatus(str, Enum):
    PENDING  = "PENDING"
    OPEN     = "OPEN"
    FILLED   = "FILLED"
    CANCELED = "CANCELED"
    FAILED   = "FAILED"


class TaskStatus(str, Enum):
    PENDING  = "PENDING"
    RUNNING  = "RUNNING"
    SUCCESS  = "SUCCESS"
    FAILED   = "FAILED"
    TIMEOUT  = "TIMEOUT"


# ── Market Models ──────────────────────────────────────────────────────────────
class MarketTick(BaseModel):
    symbol:           str
    name:             str
    price:            float
    price_change_24h: float
    price_change_pct: float
    volume_24h:       float
    market_cap:       Optional[float] = None
    high_24h:         Optional[float] = None
    low_24h:          Optional[float] = None
    timestamp:        datetime = Field(default_factory=datetime.utcnow)


class TechnicalIndicators(BaseModel):
    symbol:        str
    rsi:           Optional[float] = None
    ema_20:        Optional[float] = None
    ema_50:        Optional[float] = None
    ema_200:       Optional[float] = None
    macd:          Optional[float] = None
    macd_signal:   Optional[float] = None
    macd_hist:     Optional[float] = None
    volume_avg:    Optional[float] = None
    volume_ratio:  Optional[float] = None   # current / avg
    timestamp:     datetime = Field(default_factory=datetime.utcnow)


class OpportunitySignal(BaseModel):
    symbol:      str
    signal:      SignalType
    score:       float                        # 0–100 confidence
    reasons:     List[str] = []
    entry_price: Optional[float] = None
    stop_loss:   Optional[float] = None
    take_profit: Optional[float] = None
    indicators:  Optional[TechnicalIndicators] = None
    timestamp:   datetime = Field(default_factory=datetime.utcnow)


class MarketReport(BaseModel):
    generated_at:    datetime = Field(default_factory=datetime.utcnow)
    summary:         str
    top_opportunities: List[OpportunitySignal] = []
    macro_risks:     List[str] = []
    market_mood:     str = "NEUTRAL"   # BULLISH | BEARISH | NEUTRAL


# ── Trade Models ───────────────────────────────────────────────────────────────
class TradeOrder(BaseModel):
    id:            Optional[str] = None
    symbol:        str
    side:          OrderSide
    order_type:    OrderType = OrderType.MARKET
    quantity:      float
    price:         Optional[float] = None
    stop_loss:     Optional[float] = None
    take_profit:   Optional[float] = None
    trailing_stop: Optional[float] = None
    status:        OrderStatus = OrderStatus.PENDING
    exchange:      str = "binance"
    paper:         bool = True
    filled_price:  Optional[float] = None
    filled_at:     Optional[datetime] = None
    pnl:           Optional[float] = None
    created_at:    datetime = Field(default_factory=datetime.utcnow)


class TradeRequest(BaseModel):
    symbol:        str
    side:          OrderSide
    amount_usdt:   float                     # spend this many USDT
    order_type:    OrderType = OrderType.MARKET
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None


class Position(BaseModel):
    symbol:        str
    side:          OrderSide
    quantity:      float
    entry_price:   float
    current_price: float
    stop_loss:     Optional[float] = None
    take_profit:   Optional[float] = None
    unrealized_pnl: float = 0.0
    pnl_pct:       float = 0.0
    opened_at:     datetime = Field(default_factory=datetime.utcnow)


class PortfolioSnapshot(BaseModel):
    timestamp:         datetime = Field(default_factory=datetime.utcnow)
    total_value_usdt:  float
    available_balance: float
    invested_value:    float
    total_pnl:         float
    total_pnl_pct:     float
    positions:         List[Position] = []
    paper_mode:        bool = True


# ── Task Models ────────────────────────────────────────────────────────────────
class TaskJob(BaseModel):
    id:          Optional[int] = None
    name:        str
    script_path: str
    status:      TaskStatus = TaskStatus.PENDING
    scheduled:   Optional[str] = None      # cron expression or None
    stdout:      Optional[str] = None
    stderr:      Optional[str] = None
    exit_code:   Optional[int] = None
    duration_ms: Optional[int] = None
    started_at:  Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at:  datetime = Field(default_factory=datetime.utcnow)


class RunTaskRequest(BaseModel):
    script_name: str                        # file in tasks/ directory
    args:        List[str] = []
    timeout_sec: int = 60


# ── System Models ──────────────────────────────────────────────────────────────
class SystemHealth(BaseModel):
    timestamp:    datetime = Field(default_factory=datetime.utcnow)
    cpu_pct:      float
    ram_pct:      float
    ram_used_gb:  float
    ram_total_gb: float
    disk_pct:     float
    disk_free_gb: float
    uptime_sec:   float
    processes:    int
    python_version: str
    trading_mode: str


# ── Alert Models ───────────────────────────────────────────────────────────────
class AlertMessage(BaseModel):
    level:     str = "INFO"   # INFO | WARNING | SUCCESS | DANGER
    title:     str
    body:      str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── API Response Wrappers ──────────────────────────────────────────────────────
class APIResponse(BaseModel):
    success: bool = True
    data:    Optional[Any] = None
    message: str = "OK"
    error:   Optional[str] = None
