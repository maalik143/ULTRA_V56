"""
Unit test suite for ULTRA V5.6 backend modules
"""
import pytest
import asyncio
from backend.config import get_settings
from backend.models import MarketTick, TradeRequest, OrderSide
from backend.market_agent import TechnicalAnalyzer, OpportunityDetector
import pandas as pd

def test_config_loader():
    cfg = get_settings()
    assert cfg.base_currency == "USDT"
    assert cfg.paper_trading is True

def test_technical_analyzer():
    # Generate dummy prices
    dates = pd.date_range(start="2026-01-01", periods=60, freq="1h")
    df = pd.DataFrame({
        "close": [100 + i * 0.5 for i in range(60)],
        "volume": [1000 for _ in range(60)]
    }, index=dates)
    
    ind = TechnicalAnalyzer.compute(df, "TEST")
    assert ind is not None
    assert ind.rsi is not None
    assert ind.ema_20 is not None

def test_opportunity_detector():
    tick = MarketTick(symbol="BTC", name="Bitcoin", price=65000.0, price_change_24h=500.0, price_change_pct=2.5, volume_24h=100000.0)
    detector = OpportunityDetector()
    signal = detector.score(tick, None)
    assert signal.symbol == "BTC"
    assert 0 <= signal.score <= 100
