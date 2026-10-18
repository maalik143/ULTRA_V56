"""
ULTRA V5.6 Enterprise Engine — Telegram Bot Controller
Direct HTTP REST Polling API — Zero framework dependency, 100% reliable.
"""
from __future__ import annotations

import asyncio
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
import httpx

from .config import get_settings, logger
from .models import OrderSide, OrderType, TradeRequest, RunTaskRequest, AlertMessage

if TYPE_CHECKING:
    from .market_agent import MarketAgent
    from .task_runner import TaskRunner


class TelegramBotController:
    """Direct HTTP REST implementation for Telegram Bot API."""

    def __init__(self, market_agent: "MarketAgent", task_runner: "TaskRunner"):
        self._cfg = get_settings()
        self._market = market_agent
        self._tasks = task_runner
        self._token = self._cfg.telegram_bot_token
        self._chat_id = self._cfg.telegram_chat_id
        self._offset = 0
        self._running = False
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def start(self):
        if not self._token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot remote control disabled")
            return
        self._running = True
        logger.success("🤖 Telegram bot active — monitoring commands")
        
        while self._running:
            try:
                await self._poll_updates()
            except Exception as e:
                logger.warning(f"Telegram polling update error: {e}")
            await asyncio.sleep(2)

    async def _poll_updates(self):
        client = await self._get_client()
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        params = {"offset": self._offset, "timeout": 5}
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return
        data = resp.json()
        if not data.get("ok"):
            return

        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            message = update.get("message")
            if message and "text" in message:
                await self._handle_message(message)

    async def _handle_message(self, message: Dict[str, Any]):
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()

        if not text.startswith("/"):
            return

        parts = text.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("/start", "/help"):
            reply = (
                "🚀 *ULTRA V5.6 ENTERPRISE ENGINE*\n\n"
                "📊 *Commands:*\n"
                "• `/status` — System Health (CPU/RAM/Disk)\n"
                "• `/market` — Real-time Crypto & Gold Prices\n"
                "• `/signals` — Technical Analysis Conviction Scores\n"
                "• `/portfolio` — Open Positions & PnL\n"
                "• `/buy <SYM> <USDT>` — Autonomous Buy Order\n"
                "• `/sell <SYM> <USDT>` — Autonomous Sell Order\n"
                "• `/report` — Market Briefing\n"
                "• `/run <script.py>` — Execute Laptop Task\n"
                "• `/tasks` — Task Execution History"
            )
            await self._send_reply(chat_id, reply)

        elif cmd == "/status":
            h = self._tasks.get_system_health()
            reply = (
                f"🖥 *System Health*\n\n"
                f"CPU: {h.cpu_pct:.1f}%\n"
                f"RAM: {h.ram_pct:.1f}% ({h.ram_used_gb:.1f}/{h.ram_total_gb:.1f} GB)\n"
                f"Disk: {h.disk_pct:.1f}% ({h.disk_free_gb:.1f} GB free)\n"
                f"Trading Mode: `{h.trading_mode}`"
            )
            await self._send_reply(chat_id, reply)

        elif cmd == "/market":
            ticks = self._market.get_ticks()
            if not ticks:
                await self._send_reply(chat_id, "⏳ Market data loading...")
                return
            lines = ["💹 *Live Market Prices*\n"]
            for t in ticks:
                arrow = "🟢" if t.price_change_pct >= 0 else "🔴"
                lines.append(f"{arrow} *{t.symbol}* ${t.price:,.4f} ({t.price_change_pct:+.2f}%)")
            await self._send_reply(chat_id, "\n".join(lines))

        elif cmd == "/signals":
            sigs = sorted(self._market.get_signals(), key=lambda s: s.score, reverse=True)
            lines = ["📡 *Technical Signal Scores*\n"]
            for s in sigs:
                lines.append(f"*{s.symbol}* Score: {s.score:.0f}/100 — `{s.signal.value}`")
            await self._send_reply(chat_id, "\n".join(lines))

        elif cmd == "/portfolio":
            p = self._market.get_portfolio()
            pnl_icon = "🟢" if p.total_pnl >= 0 else "🔴"
            reply = (
                f"💼 *Portfolio Snapshot* [{ 'PAPER' if p.paper_mode else 'LIVE' }]\n\n"
                f"Total Value: ${p.total_value_usdt:,.2f}\n"
                f"Available Cash: ${p.available_balance:,.2f}\n"
                f"Total PnL: {pnl_icon} ${p.total_pnl:+,.2f} ({p.total_pnl_pct:+.2f}%)\n\n"
                f"*Active Positions:* {len(p.positions)}"
            )
            await self._send_reply(chat_id, reply)

        elif cmd in ("/buy", "/sell"):
            if len(args) < 2:
                await self._send_reply(chat_id, f"Usage: `{cmd} <SYMBOL> <USDT_AMOUNT>`")
                return
            symbol = args[0].upper()
            try:
                amount = float(args[1])
                side = OrderSide.BUY if cmd == "/buy" else OrderSide.SELL
                req = TradeRequest(symbol=symbol, side=side, amount_usdt=amount)
                order = await self._market.execute_trade(req)
                await self._send_reply(
                    chat_id,
                    f"✅ {cmd.upper()[1:]} order executed!\n"
                    f"{order.quantity:.6f} {symbol} | Status: `{order.status.value}`"
                )
            except Exception as e:
                await self._send_reply(chat_id, f"❌ Trade error: {e}")

        elif cmd == "/run":
            if not args:
                scripts = self._tasks.list_available_scripts()
                await self._send_reply(chat_id, "Usage: `/run <script.py>`\n\nAvailable:\n" + "\n".join(f"• {s}" for s in scripts))
                return
            script = args[0]
            await self._send_reply(chat_id, f"▶ Executing `{script}`...")
            try:
                job = await self._tasks.run_task(RunTaskRequest(script_name=script))
                icon = "✅" if job.status.value == "SUCCESS" else "❌"
                await self._send_reply(chat_id, f"{icon} `{script}` finished with status: `{job.status.value}` ({job.duration_ms}ms)")
            except Exception as e:
                await self._send_reply(chat_id, f"❌ Execution error: {e}")

        elif cmd == "/tasks":
            jobs = await self._tasks.list_jobs(limit=5)
            lines = ["⚙️ *Recent Task History*\n"]
            for j in jobs:
                lines.append(f"• `{j.name}` — {j.status.value} ({j.duration_ms or 0}ms)")
            await self._send_reply(chat_id, "\n".join(lines))

    async def _send_reply(self, chat_id: str, text: str):
        try:
            client = await self._get_client()
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
        except Exception as e:
            logger.warning(f"Telegram reply failed: {e}")

    async def push_alert(self, alert: AlertMessage):
        if not self._token or not self._chat_id:
            return
        emoji = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "DANGER": "🚨"}.get(alert.level, "📢")
        msg = f"{emoji} *{alert.title}*\n{alert.body}"
        await self._send_reply(self._chat_id, msg)

    async def stop(self):
        self._running = False
        if self._client and not self._client.is_closed:
            await self._client.aclose()


_bot: Optional[TelegramBotController] = None

def get_bot() -> Optional[TelegramBotController]:
    return _bot

def init_bot(market_agent, task_runner) -> TelegramBotController:
    global _bot
    _bot = TelegramBotController(market_agent, task_runner)
    return _bot
