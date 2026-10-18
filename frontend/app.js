/* ══════════════════════════════════════════════════════════════════════════════
   ULTRA V5.6 ENTERPRISE ENGINE — Live Frontend JavaScript
   ▸ NL Query Engine with Rich AI Response Card
   ▸ Auto-Pilot Trading Toggle
   ▸ SSE Live Log Stream
   ▸ WebSocket Market Data
   ══════════════════════════════════════════════════════════════════════════════ */

const API_BASE = window.location.origin;
const WS_BASE  = `ws://${window.location.host}/ws/tickers`;

let activeChartSymbol = 'BTC';
let tvWidget          = null;
let donutChart        = null;
let ws                = null;
let sseSource         = null;
let autoPilotEnabled  = false;
let isAIQueryRunning  = false;

// ── DOM Ready Initializer ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initClock();
  initTradingViewWidget(activeChartSymbol);
  initDonut();
  setupEventListeners();

  // Initial Fetch & Polling
  fetchMarketData();
  fetchPortfolio();
  fetchSystemHealth();
  fetchTasksAndScripts();
  fetchAlerts();
  fetchAutoPilotStatus();

  initWebSocket();
  initSSELogStream();

  setInterval(fetchMarketData,   8000);
  setInterval(fetchPortfolio,    4000);
  setInterval(fetchSystemHealth, 4000);
  setInterval(fetchAlerts,       8000);
});

// ── Real-Time Clock ────────────────────────────────────────────────────────────
function initClock() {
  const el = document.getElementById('clock-display');
  setInterval(() => {
    const now = new Date();
    el.textContent = now.toUTCString().split(' ')[4] + ' UTC';
  }, 1000);
}

// ── TradingView Embed Widget ───────────────────────────────────────────────────
function initTradingViewWidget(symbolKey) {
  const container = document.getElementById('tradingview_chart_container');
  if (!container) return;
  container.innerHTML = '';

  const symbolMap = {
    'BTC': 'BINANCE:BTCUSDT',
    'ETH': 'BINANCE:ETHUSDT',
    'SOL': 'BINANCE:SOLUSDT',
    'BNB': 'BINANCE:BNBUSDT',
    'GOLD': 'OANDA:XAUUSD',
  };
  const tvSymbol = symbolMap[symbolKey.toUpperCase()] || 'BINANCE:BTCUSDT';

  if (typeof TradingView !== 'undefined') {
    tvWidget = new TradingView.widget({
      autosize: true, symbol: tvSymbol, interval: '60',
      timezone: 'Etc/UTC', theme: 'dark', style: '1',
      locale: 'en', toolbar_bg: '#080f1e',
      enable_publishing: false, hide_side_toolbar: false,
      allow_symbol_change: true,
      container_id: 'tradingview_chart_container'
    });
  } else {
    container.innerHTML = `
      <iframe src="https://s.tradingview.com/widgetembed/?frameElementId=tv_embed&symbol=${encodeURIComponent(tvSymbol)}&interval=60&hidesidetoolbar=0&symboledit=1&theme=dark&style=1&timezone=Etc%2FUTC"
        style="width:100%;height:100%;border:none;"></iframe>`;
  }
}

function switchChartSymbol(sym) {
  activeChartSymbol = sym;
  document.getElementById('active-chart-title').textContent = `TradingView Live Interactive Chart — ${sym}/USDT`;
  document.querySelectorAll('.chart-tab').forEach(t =>
    t.classList.toggle('active', t.textContent.trim().toUpperCase() === sym.toUpperCase()));
  initTradingViewWidget(sym);
}

// ── WebSocket Handler ─────────────────────────────────────────────────────────
function initWebSocket() {
  try {
    ws = new WebSocket(WS_BASE);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'tickers') { renderTickerBar(msg.data); updateMarketCards(msg.data); }
      if (msg.type === 'signals') updateTopConviction(msg.data);
    };
    ws.onclose = () => setTimeout(initWebSocket, 5000);
  } catch (e) { console.warn('WebSocket fallback:', e); }
}

// ── SSE Live Log Stream ───────────────────────────────────────────────────────
function initSSELogStream() {
  const console_el = document.getElementById('sse-log-console');
  const dot = document.getElementById('sse-status-dot');
  if (!console_el) return;

  try {
    sseSource = new EventSource(`${API_BASE}/api/system/stream_logs`);

    sseSource.onopen = () => {
      if (dot) { dot.classList.add('connected'); dot.title = 'SSE Connected'; }
      appendSSELine('[SSE] Live log stream connected', 'info');
    };

    sseSource.onmessage = (event) => {
      try {
        const { line } = JSON.parse(event.data);
        if (line && line.trim()) appendSSELine(line, detectLogType(line));
      } catch (_) {}
    };

    sseSource.onerror = () => {
      if (dot) dot.classList.remove('connected');
      appendSSELine('[SSE] Reconnecting...', 'warn');
      sseSource.close();
      setTimeout(initSSELogStream, 6000);
    };
  } catch (e) {
    appendSSELine(`[SSE] Not available: ${e.message}`, 'warn');
  }
}

function detectLogType(line) {
  const l = line.toLowerCase();
  if (l.includes('error') || l.includes('failed')) return 'error';
  if (l.includes('warn'))  return 'warn';
  if (l.includes('success') || l.includes('✅')) return 'success';
  if (l.includes('info'))  return 'info';
  return 'line';
}

function appendSSELine(text, type = 'line') {
  const el = document.getElementById('sse-log-console');
  if (!el) return;
  const div = document.createElement('div');
  div.className = `console-line ${type}`;
  div.textContent = `${new Date().toTimeString().slice(0,8)} ${text}`;
  el.appendChild(div);
  // Keep last 120 lines max
  while (el.children.length > 120) el.removeChild(el.firstChild);
  el.scrollTop = el.scrollHeight;
}

// ── API Data Fetching ─────────────────────────────────────────────────────────
async function fetchMarketData() {
  try {
    const [tRes, sRes] = await Promise.all([
      fetch(`${API_BASE}/api/market/tickers`),
      fetch(`${API_BASE}/api/market/signals`)
    ]);
    const tickers = (await tRes.json()).data || [];
    const signals = (await sRes.json()).data || [];
    renderTickerBar(tickers);
    renderMarketCards(tickers, signals);
    updateTopConviction(signals);
  } catch (e) { console.error('Market data fetch error:', e); }
}

async function fetchPortfolio() {
  try {
    const res = await fetch(`${API_BASE}/api/portfolio`);
    const p = (await res.json()).data;
    if (!p) return;

    document.getElementById('stat-total-val').textContent = `$${p.total_value_usdt.toLocaleString(undefined, {minimumFractionDigits:2})}`;
    document.getElementById('stat-avail-bal').textContent = `$${p.available_balance.toLocaleString(undefined, {minimumFractionDigits:2})}`;
    const pnlEl = document.getElementById('stat-pnl');
    pnlEl.textContent = `PnL: ${p.total_pnl >= 0 ? '+' : ''}$${p.total_pnl.toFixed(2)} (${p.total_pnl_pct.toFixed(2)}%)`;
    pnlEl.className = `stat-sub ${p.total_pnl >= 0 ? 'up' : 'down'}`;
    document.getElementById('stat-positions-cnt').textContent = p.positions.length;
    document.getElementById('stat-invested-val').textContent = `Invested: $${p.invested_value.toLocaleString(undefined, {minimumFractionDigits:2})}`;

    const badge = document.getElementById('trading-mode-badge');
    badge.textContent = p.paper_mode ? '📄 PAPER MODE' : '🔴 LIVE MODE';
    badge.className = `mode-badge ${p.paper_mode ? 'paper' : 'live'}`;

    renderPositionsTable(p.positions);
    updateDonutChart(p);
  } catch (e) { console.error('Portfolio fetch error:', e); }
}

async function fetchSystemHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/system/health`);
    const h = (await res.json()).data;
    if (!h) return;
    document.getElementById('gauge-cpu-val').textContent  = `${h.cpu_pct.toFixed(1)}%`;
    document.getElementById('gauge-cpu-fill').style.width = `${Math.min(100, h.cpu_pct)}%`;
    document.getElementById('gauge-ram-val').textContent  = `${h.ram_pct.toFixed(1)}%`;
    document.getElementById('gauge-ram-fill').style.width = `${Math.min(100, h.ram_pct)}%`;
    document.getElementById('gauge-disk-val').textContent  = `${h.disk_pct.toFixed(1)}%`;
    document.getElementById('gauge-disk-fill').style.width = `${Math.min(100, h.disk_pct)}%`;
  } catch (e) { console.error('System health fetch error:', e); }
}

async function fetchTasksAndScripts() {
  try {
    const sRes = await fetch(`${API_BASE}/api/tasks/scripts`);
    const scripts = (await sRes.json()).data || [];
    const sel = document.getElementById('script-selector');
    sel.innerHTML = '<option value="">Select Pre-defined Script from tasks/...</option>';
    scripts.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      sel.appendChild(opt);
    });
  } catch (e) { console.error('Task scripts fetch error:', e); }
}

async function fetchAlerts() {
  try {
    const res = await fetch(`${API_BASE}/api/market/alerts`);
    const alerts = (await res.json()).data || [];
    renderAlerts(alerts);
  } catch (e) { console.error('Alerts fetch error:', e); }
}

async function fetchAutoPilotStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/autopilot/status`);
    const d = (await res.json()).data;
    setAutoPilotUI(d.enabled);
  } catch (_) {}
}

// ══════════════════════════════════════════════════════════════════════════════
//  NATURAL LANGUAGE QUERY ENGINE — Rich Response Renderer
// ══════════════════════════════════════════════════════════════════════════════
async function runNLQuery() {
  if (isAIQueryRunning) return;
  const input = document.getElementById('ai-command-input');
  const prompt = input.value.trim();
  if (!prompt) { showToast('Enter a prompt first!', 'error'); return; }

  isAIQueryRunning = true;
  const btn = document.getElementById('btn-run-ai-command');
  const btnText = document.getElementById('ai-btn-text');
  btn.disabled = true;
  btnText.innerHTML = '⏳ Fetching...';
  showAIResponseLoading(prompt);
  appendConsoleLine(`[AI Query] Executing: "${prompt}"`, 'info');

  try {
    const res = await fetch(`${API_BASE}/api/nl_query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt })
    });
    const result = await res.json();
    const data = result.data;

    if (res.ok && data) {
      renderAIResponseCard(data);
      appendConsoleLine(`[AI Query] ✅ Response: ${data.title}`, 'success');
      showToast(data.title, 'success');
    } else {
      showAIResponseError(result.detail || 'Query failed');
      appendConsoleLine(`[AI Query Error] ${result.detail || 'Unknown error'}`, 'error');
    }
  } catch (e) {
    showAIResponseError(e.message);
    appendConsoleLine(`[AI Query Error] ${e.message}`, 'error');
    showToast(`Query error: ${e.message}`, 'error');
  } finally {
    isAIQueryRunning = false;
    btn.disabled = false;
    btnText.innerHTML = '▶ Execute';
    input.value = '';
  }
}

function setPromptAndRun(text) {
  document.getElementById('ai-command-input').value = text;
  runNLQuery();
}

function showAIResponseLoading(prompt) {
  const panel = document.getElementById('ai-response-panel');
  panel.innerHTML = `
    <div class="ai-loading">
      <div class="ai-spinner"></div>
      <div>Querying live APIs for: <strong>"${escHtml(prompt)}"</strong></div>
    </div>`;
}

function showAIResponseError(msg) {
  const panel = document.getElementById('ai-response-panel');
  panel.innerHTML = `
    <div class="ai-response-error">
      <div style="font-size:2rem;">❌</div>
      <div><strong>Query Failed</strong></div>
      <div style="font-size:12px; color:var(--text-muted);">${escHtml(msg)}</div>
    </div>`;
}

function renderAIResponseCard(data) {
  const panel = document.getElementById('ai-response-panel');
  const typeColors = { table: '#3b82f6', detail: '#8b5cf6', error: '#ef4444' };
  const color = typeColors[data.type] || '#3b82f6';

  // Build table rows
  let tableHTML = '';
  if (data.columns && data.rows) {
    const headers = data.columns.map(c => `<th>${escHtml(c)}</th>`).join('');
    const rows = data.rows.map(row => {
      const cells = row.map((cell, idx) => {
        let cls = '';
        const val = String(cell);
        if (idx > 0 && val.includes('%')) {
          cls = val.startsWith('+') ? 'td-green' : val.startsWith('-') ? 'td-red' : '';
        }
        return `<td class="${cls}">${escHtml(val)}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');
    tableHTML = `
      <div class="ai-table-wrapper">
        <table class="ai-table">
          <thead><tr>${headers}</tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  panel.innerHTML = `
    <div class="ai-response-card" style="--card-accent:${color};">
      <div class="ai-response-header">
        <div class="ai-response-icon">${data.icon || '📊'}</div>
        <div>
          <div class="ai-response-title">${escHtml(data.title)}</div>
          <div class="ai-response-ts">Live data · ${new Date().toUTCString().split(' ')[4]} UTC</div>
        </div>
        <div class="ai-response-badge" style="background:${color}20;color:${color};">LIVE</div>
      </div>
      ${tableHTML}
      ${data.summary ? `<div class="ai-response-summary">${escHtml(data.summary)}</div>` : ''}
    </div>`;
}

// ══════════════════════════════════════════════════════════════════════════════
//  AUTO-PILOT TOGGLE
// ══════════════════════════════════════════════════════════════════════════════
async function onAutoPilotToggle(checkbox) {
  const enabled = checkbox.checked;
  try {
    const res = await fetch(`${API_BASE}/api/autopilot/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    });
    const d = await res.json();
    if (res.ok) {
      autoPilotEnabled = enabled;
      setAutoPilotUI(enabled);
      showToast(
        enabled ? '🤖 Auto-Pilot ACTIVATED — scanning every 30s' : '⏹️ Auto-Pilot DISABLED',
        enabled ? 'success' : 'info'
      );
      appendConsoleLine(`[Auto-Pilot] ${d.data.status}`, enabled ? 'success' : 'info');
    }
  } catch (e) {
    checkbox.checked = !enabled;  // revert
    showToast(`Auto-Pilot toggle failed: ${e.message}`, 'error');
  }
}

function setAutoPilotUI(enabled) {
  autoPilotEnabled = enabled;
  const toggle  = document.getElementById('autopilot-toggle');
  const label   = document.getElementById('autopilot-status-text');
  const banner  = document.getElementById('autopilot-banner');
  const control = document.getElementById('autopilot-control');

  if (toggle) toggle.checked = enabled;
  if (label)  { label.textContent = enabled ? 'ACTIVE' : 'OFF'; label.className = `autopilot-status ${enabled ? 'active' : ''}`; }
  if (banner) banner.style.display = enabled ? 'flex' : 'none';
  if (control) control.classList.toggle('ap-active', enabled);
}

// ── Rendering Functions ───────────────────────────────────────────────────────
function renderTickerBar(tickers) {
  const track = document.getElementById('ticker-track');
  if (!tickers || tickers.length === 0) return;
  const html = tickers.concat(tickers).map(t => {
    const changeClass = t.price_change_pct >= 0 ? 'up' : 'down';
    const sign = t.price_change_pct >= 0 ? '+' : '';
    return `
      <div class="ticker-item">
        <span class="ticker-symbol">${t.symbol}</span>
        <span class="ticker-price">$${t.price < 10 ? t.price.toFixed(4) : t.price.toLocaleString(undefined, {minimumFractionDigits:2})}</span>
        <span class="ticker-change ${changeClass}">${sign}${t.price_change_pct.toFixed(2)}%</span>
      </div>`;
  }).join('');
  track.innerHTML = html;
}

function renderMarketCards(tickers, signals) {
  const container = document.getElementById('market-cards-container');
  const sigMap = {};
  signals.forEach(s => sigMap[s.symbol] = s);
  container.innerHTML = tickers.slice(0, 4).map(t => {
    const sig = sigMap[t.symbol] || { score: 50, signal: 'NEUTRAL' };
    const changeClass = t.price_change_pct >= 0 ? 'up' : 'down';
    const fillClass = sig.score >= 60 ? 'buy' : (sig.score <= 40 ? 'sell' : 'neutral');
    const apTag = autoPilotEnabled && sig.score >= 75
      ? '<span class="ap-tag">🤖 AP WATCHING</span>'
      : '';
    return `
      <div class="card asset-card" onclick="switchChartSymbol('${t.symbol}')">
        <div class="asset-header">
          <div class="asset-icon">${getSymbolIcon(t.symbol)}</div>
          <div>
            <div class="asset-name">${t.symbol} ${apTag}</div>
            <div class="asset-pair">${t.name}</div>
          </div>
        </div>
        <div class="asset-price">$${t.price < 10 ? t.price.toFixed(4) : t.price.toLocaleString(undefined, {minimumFractionDigits:2})}</div>
        <div class="asset-change ${changeClass}">${t.price_change_pct >= 0 ? '+' : ''}${t.price_change_pct.toFixed(2)}% 24h</div>
        <div class="signal-bar"><div class="signal-fill ${fillClass}" style="width: ${sig.score}%"></div></div>
        <div class="signal-label">
          <span>Signal Score</span><span>${sig.score}/100 (${sig.signal})</span>
        </div>
      </div>`;
  }).join('');
}

function updateMarketCards(tickers) {
  tickers.forEach(t => {
    const card = document.querySelector(`.asset-card[onclick*="${t.symbol}"]`);
    if (!card) return;
    const priceEl = card.querySelector('.asset-price');
    if (priceEl) priceEl.textContent = `$${t.price < 10 ? t.price.toFixed(4) : t.price.toLocaleString(undefined, {minimumFractionDigits:2})}`;
  });
}

function updateTopConviction(signals) {
  if (!signals || signals.length === 0) return;
  const top = signals.reduce((max, s) => s.score > max.score ? s : max, signals[0]);
  document.getElementById('stat-top-symbol').textContent = top.symbol;
  document.getElementById('stat-top-score').textContent = `Score: ${top.score}/100 (${top.signal})`;
}

function renderPositionsTable(positions) {
  const tbody = document.getElementById('positions-table-body');
  if (!positions || positions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="td-muted" style="text-align:center;">No open positions</td></tr>';
    return;
  }
  tbody.innerHTML = positions.map(p => `
    <tr>
      <td class="td-symbol">${p.symbol}</td>
      <td class="td-muted">$${p.entry_price.toFixed(2)}</td>
      <td class="${p.unrealized_pnl >= 0 ? 'td-green' : 'td-red'}">${p.unrealized_pnl >= 0 ? '+' : ''}$${p.unrealized_pnl.toFixed(2)}</td>
    </tr>`).join('');
}

function renderAlerts(alerts) {
  const feed = document.getElementById('alert-feed');
  if (!alerts || alerts.length === 0) return;
  const icons = { INFO:'ℹ️', SUCCESS:'✅', WARNING:'⚠️', DANGER:'🚨' };
  feed.innerHTML = alerts.slice(0, 5).map(a => `
    <div class="alert-item ${a.level}">
      <div class="alert-icon">${icons[a.level] || '📢'}</div>
      <div class="alert-content">
        <div class="alert-title">${escHtml(a.title)}</div>
        <div class="alert-body">${escHtml(a.body)}</div>
      </div>
    </div>`).join('');
}

function initDonut() {
  const ctx = document.getElementById('allocation-chart').getContext('2d');
  donutChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['USDT', 'BTC', 'ETH', 'Other'],
      datasets: [{ data: [10000, 0, 0, 0], backgroundColor: ['#3b82f6','#f59e0b','#8b5cf6','#10b981'], borderWidth: 0 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } }, cutout: '70%'
    }
  });
}

function updateDonutChart(portfolio) {
  if (!donutChart) return;
  const labels = ['USDT (Cash)'];
  const values = [portfolio.available_balance];
  portfolio.positions.forEach(p => { labels.push(p.symbol); values.push(p.quantity * p.current_price); });
  donutChart.data.labels = labels;
  donutChart.data.datasets[0].data = values;
  donutChart.update();
}

// ── Interactive Actions ───────────────────────────────────────────────────────
function setupEventListeners() {
  document.getElementById('btn-trade-buy').addEventListener('click', () => executeTrade('BUY'));
  document.getElementById('btn-trade-sell').addEventListener('click', () => executeTrade('SELL'));
}

async function executeTrade(side) {
  const symbol   = document.getElementById('trade-symbol').value;
  const amount   = parseFloat(document.getElementById('trade-amount').value);
  const orderType = document.getElementById('trade-order-type').value;
  if (!amount || amount <= 0) { showToast('Please enter a valid amount', 'error'); return; }

  try {
    const endpoint = side === 'BUY' ? '/api/trade/buy' : '/api/trade/sell';
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, side, amount_usdt: amount, order_type: orderType })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`${side} order for ${symbol} executed!`, 'success');
      fetchPortfolio(); fetchAlerts();
    } else {
      showToast(`Trade failed: ${data.detail || data.message}`, 'error');
    }
  } catch (e) { showToast(`Trade error: ${e.message}`, 'error'); }
}

async function runSelectedScript() {
  const script = document.getElementById('script-selector').value;
  if (!script) { showToast('Select a script first!', 'error'); return; }
  appendConsoleLine(`[Execution] Starting script: ${script}...`, 'info');
  try {
    const res = await fetch(`${API_BASE}/api/tasks/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script_name: script })
    });
    const result = await res.json();
    const job = result.data;
    if (job && job.status === 'SUCCESS') {
      appendConsoleLine(`[Success] ${script} completed in ${job.duration_ms}ms`, 'success');
      if (job.stdout) appendConsoleLine(job.stdout, 'line');
      showToast(`Task ${script} completed!`, 'success');
      fetchAlerts();
    } else {
      appendConsoleLine(`[Failed] ${script}: ${job ? job.status : 'ERROR'}`, 'error');
      if (job && job.stderr) appendConsoleLine(job.stderr, 'error');
      showToast(`Task ${script} failed!`, 'error');
    }
  } catch (e) {
    appendConsoleLine(`[Error] ${e.message}`, 'error');
    showToast(`Execution error: ${e.message}`, 'error');
  }
}

function appendConsoleLine(text, type = 'line') {
  const el = document.getElementById('task-console');
  const div = document.createElement('div');
  div.className = `console-line ${type}`;
  div.textContent = text;
  el.appendChild(div);
  while (el.children.length > 80) el.removeChild(el.firstChild);
  el.scrollTop = el.scrollHeight;
}

// ── Toast System ──────────────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'info' ? 'ℹ️' : '📢';
  toast.innerHTML = `<span>${icon}</span> <span>${escHtml(message)}</span>`;
  container.appendChild(toast);
  setTimeout(() => toast.classList.add('fade-out'), 3400);
  setTimeout(() => toast.remove(), 4000);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function getSymbolIcon(sym) {
  const icons = { BTC: '₿', ETH: 'Ξ', SOL: '◎', BNB: '🔶', XRP: '✕', GOLD: '🥇' };
  return icons[sym] || '🪙';
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
