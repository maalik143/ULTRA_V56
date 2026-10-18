# 🚀 ULTRA V5.6 ENTERPRISE ENGINE — Complete System Guide

Welcome to **ULTRA V5.6 ENTERPRISE ENGINE**, a production-ready, fully autonomous financial intelligence, crypto/commodity trading, laptop automation, and remote command platform.

---

## 🏗️ Architecture Overview

The system consists of 5 modular components designed for high efficiency and enterprise reliability:

1. **`backend/market_agent.py`**: Market Intelligence Engine (CoinGecko/Binance/AlphaVantage price streams, RSI/EMA/MACD signals, paper & live trading execution).
2. **`backend/task_runner.py`**: Laptop Automation Agent (apscheduler cron runner, sandboxed subprocess executor, psutil hardware monitor, SQLite job history).
3. **`backend/bot_control.py`**: Mobile Remote Controller (Telegram Bot API wrapper for push notifications and remote mobile execution).
4. **`backend/main.py`**: FastAPI Enterprise Server (REST API endpoints, WebSockets, static file server, coordinated lifespan).
5. **`frontend/`**: Enterprise Glassmorphism Dashboard (Live tickers, TradingView charts, instant trade panel, system gauges, and task console).

---

## 📦 Quick Setup & Installation

### 1. Prerequisites
Ensure you have Python 3.9+ installed on your system.

### 2. Environment Setup & Key Configuration
Navigate to the project root:
```bash
cd C:\Users\hp\Desktop\ULTRA_V56
```

Copy the `.env.example` file to create your local `.env`:
```bash
copy .env.example .env
```

Edit `.env` to insert your API credentials:
* **`TELEGRAM_BOT_TOKEN`**: Obtain from [@BotFather](https://t.me/BotFather) on Telegram.
* **`TELEGRAM_CHAT_ID`**: Your personal Telegram Chat ID for alerts.
* **`PAPER_TRADING`**: Set to `true` for paper trading simulation (default), or `false` for real exchange orders.

### 3. Install Dependencies
Install all required libraries via `pip`:
```bash
pip install -r requirements.txt
```

---

## ⚡ Running the Engine

Start the FastAPI Enterprise Engine:
```bash
python -m backend.main
```
or using Uvicorn:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📱 Mobile Remote Command via Telegram

Once your Telegram bot token is configured in `.env`, interact with your laptop engine directly from your phone:

| Command | Description |
|---|---|
| `/status` | View real-time CPU, RAM, Disk utilization, and system health |
| `/market` | Get real-time prices for BTC, ETH, SOL, BNB, XRP, Gold |
| `/signals` | View technical analysis opportunity scores (0–100) |
| `/portfolio` | Check open trading positions, cash balance, and total PnL |
| `/buy BTC 100` | Execute an autonomous buy order for $100 USDT |
| `/sell BTC 100` | Execute an autonomous sell order for $100 USDT |
| `/report` | Generate a comprehensive daily market briefing |
| `/run sample_cleanup.py` | Execute a local laptop script remotely |
| `/tasks` | View recent laptop task runner execution logs |

---

## 💻 Enterprise Web Dashboard

Access the real-time dark-mode dashboard at:
👉 **`http://localhost:8000`**

### Dashboard Features:
* **Live Ticker Strip**: Continuous streaming price bar across top assets.
* **Global Market Scanner**: Real-time opportunity cards with dynamic signal meters.
* **TradingView Candlestick Charts**: Embedded interactive charting engine.
* **Instant Order Execution**: Execute paper or live trades with a single click.
* **Asset Allocation & Positions**: Real-time portfolio donut chart & positions PnL table.
* **Task Console**: Execute scripts directly from `tasks/` directory and stream logs live.
* **System Gauges**: Hardware resource monitor for CPU, RAM, and Disk.
