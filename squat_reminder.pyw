import calendar
import ctypes
import datetime
import errno
import logging
import os
import socket
import sys
import threading

import webview

import squat_db

INTERVAL_MINUTES = 60
SQUATS_PER_REMINDER = 10
LOCK_PORT = 47653
WINDOW_WIDTH = 360
WINDOW_HEIGHT = 460
CARD_BACKGROUND = "#131315"
CORNER_RADIUS = 26
PANEL_WIDTH = 900
PANEL_HEIGHT = 720

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# This runs as a windowless .pyw process with no console, so without a log file
# an unhandled exception anywhere just kills the app with zero trace.
logging.basicConfig(
    filename=os.path.join(SCRIPT_DIR, "error.log"),
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_ADDR_IN_USE = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", None)}

# Bound for the lifetime of the process; a second launch fails to bind and exits.
_lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _lock_socket.bind(("127.0.0.1", LOCK_PORT))
except OSError as exc:
    if exc.errno not in _ADDR_IN_USE:
        logger.error("Failed to bind lock port %d: %s", LOCK_PORT, exc)
    sys.exit(0)


POPUP_HTML = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{
    margin: 0; padding: 0; width: 100%; height: 100%;
    background: {CARD_BACKGROUND}; overflow: hidden;
  }}
  .card {{
    width: 100%; height: 100%; box-sizing: border-box;
    border-radius: {CORNER_RADIUS}px;
    background:
      radial-gradient(130% 85% at 50% -8%, rgba(255, 69, 88, 0.32), transparent 55%),
      {CARD_BACKGROUND};
    display: flex; flex-direction: column; align-items: center;
    padding: 40px 32px 22px;
    font-family: -apple-system, "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    color: #f7f7f8;
    -webkit-user-select: none; user-select: none;
  }}
  h1 {{
    font-size: 27px; font-weight: 700; margin: 12px 0 10px;
    letter-spacing: -0.02em; text-align: center;
  }}
  .sub {{ font-size: 14.5px; color: #a2a2a8; margin: 0 0 24px; text-align: center; line-height: 1.5; }}
  .count-block {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 20px; }}
  .count-block .num {{
    font-size: 44px; font-weight: 750; letter-spacing: -0.02em; color: #ffffff;
    font-variant-numeric: tabular-nums; line-height: 1;
  }}
  .count-block .label {{ font-size: 13.5px; font-weight: 500; color: #8f8f96; padding-bottom: 4px; }}
  .actions {{ width: 100%; display: flex; flex-direction: column; gap: 10px; margin-top: auto; }}
  .btn-primary {{
    width: 100%; border: none; padding: 14px; border-radius: 15px;
    background: linear-gradient(120deg, #ff5f6d, #ff375f);
    color: #ffffff; font-size: 15px; font-weight: 650; cursor: pointer;
    box-shadow: 0 10px 22px -8px rgba(255, 55, 95, 0.55);
  }}
  .btn-ghost {{
    border: 1px solid rgba(255, 255, 255, 0.14); background: none; color: #d6d6d9;
    font-size: 13.5px; font-weight: 500; padding: 10px; border-radius: 15px; cursor: pointer;
  }}
  button:focus-visible {{ outline: 2px solid #7ab8ff; outline-offset: 2px; }}
  .btn-primary:hover, .btn-ghost:hover {{ filter: brightness(1.08); }}
  .btn-primary:active, .btn-ghost:active {{ transform: scale(0.98); }}
</style>
</head>
<body>
  <div class="card">
    <h1>Time to move</h1>
    <p class="sub">{SQUATS_PER_REMINDER} squats. Thirty seconds.</p>
    <div class="count-block">
      <span class="num" id="count">{squat_db.todays_total()}</span>
      <span class="label">squats today</span>
    </div>
    <div class="actions">
      <button class="btn-primary" onclick="pywebview.api.done()">Done ✓ (+{SQUATS_PER_REMINDER})</button>
      <button class="btn-ghost" onclick="pywebview.api.skip()">Skip</button>
    </div>
  </div>
<script>
function setCount(n) {{ document.getElementById('count').textContent = n; }}
</script>
</body>
</html>
"""


CONTROL_PANEL_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Squat Reminder — Control Panel</title>
<style>
  :root {
    --page-bg: #0d0d0e;
    --surface: #18181b;
    --surface-2: #1f1f23;
    --ink-primary: #f5f5f7;
    --ink-secondary: #a2a2a8;
    --ink-muted: #6f6f76;
    --border: rgba(255, 255, 255, 0.08);
    --grid-line: rgba(255, 255, 255, 0.07);
    --accent: #ff375f;
    --heat-0: #232326;
    --heat-1: #4a1f28;
    --heat-2: #9c2f45;
    --heat-3: #e8394f;
    --heat-4: #ff5f6d;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; }
  body {
    background: var(--page-bg); color: var(--ink-primary);
    font-family: -apple-system, "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .page { max-width: 820px; margin: 0 auto; padding: 28px 28px 40px; }

  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
  .stat-tile { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 16px 14px; }
  .stat-tile .label {
    font-size: 11.5px; font-weight: 600; color: var(--ink-muted); text-transform: uppercase;
    letter-spacing: 0.04em; margin: 0 0 8px;
  }
  .stat-tile .value { font-size: 26px; font-weight: 750; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
  .stat-tile .value small { font-size: 13px; font-weight: 500; color: var(--ink-muted); margin-left: 3px; }

  .section { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 20px 22px 18px; margin-bottom: 16px; }
  .section-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 14px; flex-wrap: wrap; gap: 10px; }
  .section-head h2 { font-size: 14.5px; font-weight: 650; margin: 0; }

  .chart-wrap { position: relative; }
  #trend-svg { display: block; width: 100%; height: 180px; overflow: visible; }
  .today-label { font-size: 11px; font-weight: 700; fill: var(--ink-primary); font-family: inherit; font-variant-numeric: tabular-nums; }

  .period-controls { display: flex; align-items: center; gap: 14px; }
  .seg { display: flex; background: var(--surface-2); border: 1px solid var(--border); border-radius: 9px; padding: 2px; }
  .seg-btn { border: none; background: none; color: var(--ink-secondary); font-size: 12px; font-weight: 600; padding: 5px 11px; border-radius: 7px; cursor: pointer; font-family: inherit; }
  .seg-btn.active { background: var(--accent); color: #fff; }
  .nav-arrows { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--ink-secondary); }
  .nav-arrows button { background: var(--surface-2); border: 1px solid var(--border); color: var(--ink-secondary); width: 22px; height: 22px; border-radius: 6px; cursor: pointer; font-size: 12px; line-height: 1; }
  .nav-arrows button:disabled { opacity: 0.35; cursor: default; }
  .nav-arrows .range-label { min-width: 130px; text-align: center; font-variant-numeric: tabular-nums; }

  .heatmap-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
  .year-nav { display: flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--ink-secondary); }
  .year-nav button { background: var(--surface-2); border: 1px solid var(--border); color: var(--ink-secondary); width: 22px; height: 22px; border-radius: 6px; cursor: pointer; font-size: 12px; line-height: 1; }
  .year-nav button:disabled { opacity: 0.35; cursor: default; }
  .heatmap-scroll { overflow-x: auto; padding-bottom: 4px; }
  .heatmap-grid { display: grid; grid-template-rows: repeat(7, 11px); grid-auto-flow: column; gap: 3px; width: max-content; margin-top: 8px; }
  .heatmap-cell { width: 11px; height: 11px; border-radius: 3px; }
  .month-labels { display: flex; font-size: 10.5px; color: var(--ink-muted); width: max-content; }
  .legend { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--ink-muted); margin-top: 12px; }
  .legend .swatch { width: 10px; height: 10px; border-radius: 3px; }

  .callouts { display: flex; gap: 10px; margin-top: 14px; }
  .callout { flex: 1; background: var(--surface-2); border-radius: 10px; padding: 10px 12px; font-size: 12.5px; color: var(--ink-secondary); }
  .callout b { display: block; color: var(--ink-primary); font-size: 15px; font-weight: 700; margin-top: 2px; }

  #tooltip {
    position: fixed; pointer-events: none; background: #232327; border: 1px solid var(--border);
    border-radius: 8px; padding: 6px 10px; font-size: 12px; color: var(--ink-primary);
    box-shadow: 0 8px 20px -6px rgba(0,0,0,0.6); opacity: 0; transform: translate(-50%, -130%);
    transition: opacity 0.08s ease; z-index: 10; white-space: nowrap;
  }
  #tooltip.visible { opacity: 1; }
  #tooltip .t-date { color: var(--ink-muted); font-size: 10.5px; }
</style>
</head>
<body>
<div class="page">
  <div class="stats" id="stats"></div>

  <div class="section">
    <div class="section-head">
      <h2>Trend</h2>
      <div class="period-controls">
        <div class="seg" id="periodSeg">
          <button class="seg-btn" data-mode="week">Week</button>
          <button class="seg-btn active" data-mode="month">Month</button>
          <button class="seg-btn" data-mode="year">Year</button>
        </div>
        <div class="nav-arrows">
          <button id="trendPrev" aria-label="Previous period">‹</button>
          <span class="range-label" id="trendRangeLabel">—</span>
          <button id="trendNext" aria-label="Next period" disabled>›</button>
        </div>
      </div>
    </div>
    <div class="chart-wrap">
      <svg id="trend-svg" viewBox="0 0 820 180" preserveAspectRatio="none"></svg>
    </div>
  </div>

  <div class="section">
    <div class="heatmap-head">
      <h2>Year in squats</h2>
      <div class="year-nav">
        <button id="prevYear">‹</button>
        <span id="yearLabel">—</span>
        <button id="nextYear">›</button>
      </div>
    </div>
    <div class="heatmap-scroll">
      <div class="month-labels" id="monthLabels"></div>
      <div class="heatmap-grid" id="heatmap"></div>
    </div>
    <div class="legend">
      <span>Less</span>
      <span class="swatch" style="background:var(--heat-0)"></span>
      <span class="swatch" style="background:var(--heat-1)"></span>
      <span class="swatch" style="background:var(--heat-2)"></span>
      <span class="swatch" style="background:var(--heat-3)"></span>
      <span class="swatch" style="background:var(--heat-4)"></span>
      <span>More</span>
    </div>
    <div class="callouts">
      <div class="callout">Current streak<b id="streakVal">—</b></div>
      <div class="callout">Best day<b id="bestVal">—</b></div>
      <div class="callout">Year total<b id="yearTotalVal">—</b></div>
    </div>
  </div>
</div>

<div id="tooltip"><div class="t-date"></div><div class="t-val"></div></div>

<script>
(function () {
  const tooltip = document.getElementById('tooltip');
  function showTip(x, y, dateStr, valStr) {
    tooltip.querySelector('.t-date').textContent = dateStr;
    tooltip.querySelector('.t-val').textContent = valStr;
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
    tooltip.classList.add('visible');
  }
  function hideTip() { tooltip.classList.remove('visible'); }

  function toISODate(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function parseLocalDate(iso) {
    const parts = iso.split('-').map(Number);
    return new Date(parts[0], parts[1] - 1, parts[2] || 1);
  }
  function isLeapYear(y) { return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0; }

  const svgns = 'http://www.w3.org/2000/svg';
  const svg = document.getElementById('trend-svg');
  const W = 820, H = 180, padL = 8, padR = 8, padT = 18, padB = 20;

  const defs = document.createElementNS(svgns, 'defs');
  defs.innerHTML = `<linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#ff375f" stop-opacity="0.35"/>
    <stop offset="100%" stop-color="#ff375f" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="barFill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#ff5f6d"/>
    <stop offset="100%" stop-color="#ff375f"/>
  </linearGradient>`;
  svg.appendChild(defs);

  async function loadStats() {
    const s = await pywebview.api.get_stats();
    document.getElementById('stats').innerHTML = [
      ['Today', s.today], ['This week', s.week], ['This month (30d)', s.month], ['All time', s.all_time],
    ].map(([label, val]) =>
      `<div class="stat-tile"><p class="label">${label}</p><div class="value">${val.toLocaleString()}<small>squats</small></div></div>`
    ).join('');
  }

  let mode = 'month';
  let offset = 0;

  async function renderTrend() {
    const data = await pywebview.api.get_trend(mode, offset);
    const isCurrent = offset === 0;
    const today = new Date();

    document.getElementById('trendRangeLabel').textContent = data.label;
    document.getElementById('trendNext').disabled = isCurrent;

    svg.querySelectorAll(':scope > :not(defs)').forEach(el => el.remove());

    const values = data.values;
    const dates = data.dates;
    const n = values.length;
    const maxVal = Math.max(...values, 10);

    for (let g = 0; g <= 3; g++) {
      const y = padT + (g / 3) * (H - padT - padB);
      const gl = document.createElementNS(svgns, 'line');
      gl.setAttribute('x1', padL); gl.setAttribute('x2', W - padR);
      gl.setAttribute('y1', y); gl.setAttribute('y2', y);
      gl.setAttribute('stroke', 'var(--grid-line)'); gl.setAttribute('stroke-width', '1');
      svg.appendChild(gl);
    }

    if (mode === 'year') {
      const slot = (W - padL - padR) / n;
      const barW = slot * 0.55;
      values.forEach((v, i) => {
        const bh = (v / maxVal) * (H - padT - padB);
        const bx = padL + i * slot + (slot - barW) / 2;
        const by = H - padB - bh;
        const isThisMonth = isCurrent && i === today.getMonth();

        const rect = document.createElementNS(svgns, 'rect');
        rect.setAttribute('x', bx); rect.setAttribute('y', by);
        rect.setAttribute('width', barW); rect.setAttribute('height', Math.max(bh, 2));
        rect.setAttribute('rx', 4);
        rect.setAttribute('fill', isThisMonth ? 'url(#barFill)' : 'rgba(255,255,255,0.18)');
        svg.appendChild(rect);

        const hit = document.createElementNS(svgns, 'rect');
        hit.setAttribute('x', padL + i * slot); hit.setAttribute('y', padT);
        hit.setAttribute('width', slot); hit.setAttribute('height', H - padT - padB);
        hit.setAttribute('fill', 'transparent'); hit.style.cursor = 'pointer';
        const label = parseLocalDate(dates[i] + '-01').toLocaleDateString(undefined, { month: 'long' });
        hit.addEventListener('mouseenter', () => {
          const r = svg.getBoundingClientRect();
          showTip(r.left + ((padL + i * slot + slot / 2) / W) * r.width, r.top + (by / H) * r.height, label, v + ' squats');
        });
        hit.addEventListener('mouseleave', hideTip);
        svg.appendChild(hit);
      });
      return;
    }

    const xStep = (W - padL - padR) / (n - 1 || 1);
    const yFor = v => H - padB - (v / maxVal) * (H - padT - padB);
    const xFor = i => padL + i * xStep;

    let d = `M ${xFor(0)} ${yFor(values[0])}`;
    for (let i = 1; i < n; i++) d += ` L ${xFor(i)} ${yFor(values[i])}`;
    const areaD = d + ` L ${xFor(n - 1)} ${H - padB} L ${xFor(0)} ${H - padB} Z`;

    const area = document.createElementNS(svgns, 'path');
    area.setAttribute('d', areaD);
    area.setAttribute('fill', 'url(#areaFill)');
    svg.appendChild(area);

    const line = document.createElementNS(svgns, 'path');
    line.setAttribute('d', d);
    line.setAttribute('fill', 'none');
    line.setAttribute('stroke', '#ff5f6d');
    line.setAttribute('stroke-width', '2');
    line.setAttribute('stroke-linecap', 'round');
    line.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(line);

    values.forEach((v, i) => {
      const cx = xFor(i), cy = yFor(v);
      const isLast = isCurrent && i === n - 1;
      const c = document.createElementNS(svgns, 'circle');
      c.setAttribute('cx', cx); c.setAttribute('cy', cy);
      c.setAttribute('r', isLast ? 4.5 : 2.4);
      c.setAttribute('fill', isLast ? '#ff5f6d' : '#a2a2a8');
      c.setAttribute('opacity', isLast ? 1 : 0.55);
      svg.appendChild(c);

      const hit = document.createElementNS(svgns, 'circle');
      hit.setAttribute('cx', cx); hit.setAttribute('cy', cy); hit.setAttribute('r', Math.max(6, xStep / 2));
      hit.setAttribute('fill', 'transparent'); hit.style.cursor = 'pointer';
      const dateStr = parseLocalDate(dates[i]).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      hit.addEventListener('mouseenter', () => {
        const r = svg.getBoundingClientRect();
        showTip(r.left + (cx / W) * r.width, r.top + (cy / H) * r.height, isLast ? 'Today' : dateStr, v + ' squats');
      });
      hit.addEventListener('mouseleave', hideTip);
      svg.appendChild(hit);
    });

    if (isCurrent) {
      const lbl = document.createElementNS(svgns, 'text');
      lbl.setAttribute('x', xFor(n - 1) - 4);
      lbl.setAttribute('y', yFor(values[n - 1]) - 12);
      lbl.setAttribute('text-anchor', 'end');
      lbl.setAttribute('class', 'today-label');
      lbl.textContent = values[n - 1];
      svg.appendChild(lbl);
    }
  }

  document.getElementById('periodSeg').addEventListener('click', e => {
    const btn = e.target.closest('.seg-btn');
    if (!btn) return;
    mode = btn.dataset.mode;
    offset = 0;
    document.querySelectorAll('.seg-btn').forEach(b => b.classList.toggle('active', b === btn));
    renderTrend();
  });
  document.getElementById('trendPrev').addEventListener('click', () => { offset += 1; renderTrend(); });
  document.getElementById('trendNext').addEventListener('click', () => { if (offset > 0) { offset -= 1; renderTrend(); } });

  const heatmap = document.getElementById('heatmap');
  const monthLabels = document.getElementById('monthLabels');
  const heatColors = ['var(--heat-0)', 'var(--heat-1)', 'var(--heat-2)', 'var(--heat-3)', 'var(--heat-4)'];
  const cellPx = 14;
  let heatmapYear = new Date().getFullYear();

  async function renderHeatmap() {
    const data = await pywebview.api.get_heatmap(heatmapYear);
    document.getElementById('yearLabel').textContent = heatmapYear;
    document.getElementById('nextYear').disabled = heatmapYear >= new Date().getFullYear();
    document.getElementById('streakVal').textContent = data.streak + (data.streak === 1 ? ' day' : ' days');
    document.getElementById('bestVal').textContent = data.best ? `${data.best.count} squats` : 'None yet';
    document.getElementById('yearTotalVal').textContent = data.year_total.toLocaleString() + ' squats';

    heatmap.innerHTML = '';
    monthLabels.innerHTML = '';
    const yearStart = new Date(heatmapYear, 0, 1);
    const dayCount = isLeapYear(heatmapYear) ? 366 : 365;
    let lastMonth = -1;
    for (let i = 0; i < dayCount; i++) {
      const d0 = new Date(yearStart); d0.setDate(yearStart.getDate() + i);
      const col = Math.floor(i / 7);
      if (d0.getMonth() !== lastMonth) {
        lastMonth = d0.getMonth();
        const lbl = document.createElement('span');
        lbl.style.width = cellPx * 4 + 'px';
        lbl.style.flex = 'none';
        lbl.textContent = d0.toLocaleDateString(undefined, { month: 'short' });
        monthLabels.appendChild(lbl);
      }
      const iso = toISODate(d0);
      const val = data.totals[iso] || 0;
      const level = val === 0 ? 0 : Math.min(4, Math.ceil(val / 25));
      const cell = document.createElement('div');
      cell.className = 'heatmap-cell';
      cell.style.background = heatColors[level];
      cell.style.gridRow = (d0.getDay() === 0 ? 7 : d0.getDay());
      cell.style.gridColumn = col + 1;
      cell.addEventListener('mouseenter', () => {
        const r2 = cell.getBoundingClientRect();
        showTip(r2.left + r2.width / 2, r2.top, d0.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }), val + ' squats');
      });
      cell.addEventListener('mouseleave', hideTip);
      heatmap.appendChild(cell);
    }
  }

  document.getElementById('prevYear').addEventListener('click', () => { heatmapYear -= 1; renderHeatmap(); });
  document.getElementById('nextYear').addEventListener('click', () => {
    if (heatmapYear < new Date().getFullYear()) { heatmapYear += 1; renderHeatmap(); }
  });

  function boot() {
    loadStats();
    renderTrend();
    renderHeatmap();
  }
  if (window.pywebview && window.pywebview.api) {
    boot();
  } else {
    window.addEventListener('pywebviewready', boot);
  }
})();
</script>
</body>
</html>
"""


class Api:
    def __init__(self, app):
        # Underscore prefix: pywebview recursively introspects public attributes
        # of js_api to build JS bindings, and would otherwise walk into
        # app.window.native (a .NET control tree with circular Accessibility
        # references), which is skipped for names starting with "_".
        self._app = app

    def done(self):
        self._app.on_done()

    def skip(self):
        self._app.on_skip()


class ControlPanelApi:
    def get_stats(self):
        try:
            return squat_db.stats()
        except Exception:
            logger.exception("get_stats failed")
            raise

    def get_trend(self, mode, offset):
        try:
            return self._compute_trend(mode, offset)
        except (ValueError, OverflowError):
            # Clicking "previous period" enough times can walk the computed
            # date past datetime's year-1 floor; fall back to the current period.
            return self._compute_trend(mode, 0)
        except Exception:
            logger.exception("get_trend failed (mode=%s, offset=%s)", mode, offset)
            raise

    def _compute_trend(self, mode, offset):
        today = datetime.date.today()

        if mode == "week":
            end = today - datetime.timedelta(days=7 * offset)
            start = end - datetime.timedelta(days=6)
            dates = [(start + datetime.timedelta(days=i)).isoformat() for i in range(7)]
            label = f"{start.strftime('%b %d')} – {end.strftime('%b %d')}"
            totals = squat_db.daily_totals(dates[0], (end + datetime.timedelta(days=1)).isoformat())
            values = [totals.get(d, 0) for d in dates]

        elif mode == "month":
            total_months = today.year * 12 + (today.month - 1) - offset
            y, m0 = divmod(total_months, 12)
            m = m0 + 1
            n = calendar.monthrange(y, m)[1]
            dates = [f"{y:04d}-{m:02d}-{d:02d}" for d in range(1, n + 1)]
            label = f"{calendar.month_name[m]} {y}"
            next_month_start = (datetime.date(y, m, n) + datetime.timedelta(days=1)).isoformat()
            totals = squat_db.daily_totals(dates[0], next_month_start)
            values = [totals.get(d, 0) for d in dates]

        else:  # year
            y = today.year - offset
            dates = [f"{y:04d}-{mm:02d}" for mm in range(1, 13)]
            label = str(y)
            values = squat_db.monthly_totals(y)

        return {"label": label, "dates": dates, "values": values}

    def get_heatmap(self, year):
        try:
            totals = squat_db.year_daily_totals(int(year))
            return {
                "totals": totals,
                "streak": squat_db.current_streak(),
                "best": squat_db.best_day(),
                "year_total": sum(totals.values()),
            }
        except Exception:
            logger.exception("get_heatmap failed (year=%s)", year)
            raise


def apply_rounded_corners(window, width, height, radius):
    # pywebview's transparent=True doesn't give true desktop-level transparency on
    # Windows (the Form's own background stays opaque white), which showed up as
    # white squares in the corners outside the CSS border-radius. Clipping the
    # actual window shape via SetWindowRgn is the reliable fix.
    hwnd = ctypes.c_void_p(window.native.Handle.ToInt64())
    region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius * 2, radius * 2)
    ctypes.windll.user32.SetWindowRgn(hwnd, region, True)


class SquatApp:
    def __init__(self):
        self.window = None
        self.api = Api(self)
        self.panel_window = None
        self.panel_api = ControlPanelApi()
        self.paused = False
        self.tray_icon = None
        self._stop = threading.Event()
        self._quitting = False

    def start(self):
        screen = webview.screens[0]
        pos_x = (screen.width - WINDOW_WIDTH) // 2
        pos_y = (screen.height - WINDOW_HEIGHT) // 2

        self.window = webview.create_window(
            "Squat Reminder", html=POPUP_HTML, js_api=self.api,
            width=WINDOW_WIDTH, height=WINDOW_HEIGHT, x=pos_x, y=pos_y,
            frameless=True, easy_drag=True, on_top=True, resizable=False,
            hidden=True, shadow=False, background_color=CARD_BACKGROUND,
        )
        self.window.events.closing += self._on_closing
        self.window.events.loaded += self._on_loaded
        webview.start(self._run_background, debug=False)

    def _on_closing(self):
        if self._quitting:
            return True
        self.window.hide()
        return False

    def _on_loaded(self):
        # The native Form handle only exists once content has loaded, even for
        # a hidden window -- can't apply this any earlier.
        apply_rounded_corners(self.window, WINDOW_WIDTH, WINDOW_HEIGHT, CORNER_RADIUS)

    def _run_background(self):
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        self.tray_icon = build_tray_icon(self)
        if self.tray_icon is not None:
            self.tray_icon.run()
        else:
            self._stop.wait()

    def _scheduler_loop(self):
        while not self._stop.is_set():
            timed_out = not self._stop.wait(INTERVAL_MINUTES * 60)
            if not timed_out:
                break
            if not self.paused:
                try:
                    self.show_popup()
                except Exception:
                    logger.exception("Failed to show popup")

    def show_popup(self):
        total = squat_db.todays_total()
        self.window.evaluate_js(f"setCount({total})")
        self.window.show()

    def trigger_now(self):
        self.show_popup()

    def on_done(self):
        try:
            squat_db.log_completion(SQUATS_PER_REMINDER)
        except Exception:
            logger.exception("Failed to log completion")
        self.window.hide()
        self.update_tray_menu()

    def on_skip(self):
        self.window.hide()

    def open_control_panel(self):
        if self.panel_window is not None:
            self.panel_window.show()
            self.panel_window.restore()
            return
        self.panel_window = webview.create_window(
            "Squat Reminder — Control Panel", html=CONTROL_PANEL_HTML, js_api=self.panel_api,
            width=PANEL_WIDTH, height=PANEL_HEIGHT, resizable=True, min_size=(680, 520),
        )
        self.panel_window.events.closed += self._on_panel_closed

    def _on_panel_closed(self):
        self.panel_window = None

    def toggle_pause(self):
        self.paused = not self.paused
        self.update_tray_menu()

    def update_tray_menu(self):
        if self.tray_icon is not None:
            self.tray_icon.update_menu()

    def quit_app(self):
        self._quitting = True
        self._stop.set()
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self.window.destroy()


def build_tray_icon(app):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    def make_image():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((6, 6, 58, 58), fill="#ff375f")
        return img

    def on_control_panel(icon, item):
        try:
            app.open_control_panel()
        except Exception:
            logger.exception("Failed to open control panel")

    def on_toggle_pause(icon, item):
        app.toggle_pause()

    def pause_text(item):
        return "Resume Reminders" if app.paused else "Pause Reminders"

    def today_text(item):
        try:
            return f"Today: {squat_db.todays_total()} squats"
        except Exception:
            logger.exception("Failed to read today's total")
            return "Today: — squats"

    def on_quit(icon, item):
        app.quit_app()

    menu = pystray.Menu(
        pystray.MenuItem("Control Panel", on_control_panel),
        pystray.MenuItem(pause_text, on_toggle_pause),
        pystray.MenuItem(today_text, lambda icon, item: None),
        pystray.MenuItem("Quit", on_quit),
    )

    return pystray.Icon("squat_reminder", make_image(), "Squat Reminder", menu)


def main():
    try:
        squat_db.init_db()
        app = SquatApp()
        app.start()
    except Exception:
        logger.exception("Fatal error, exiting")
        raise


if __name__ == "__main__":
    main()
