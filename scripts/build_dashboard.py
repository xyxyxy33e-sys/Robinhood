#!/usr/bin/env python3
"""Regenerate dashboard/index.html from portfolio state.

Usage: python3 scripts/build_dashboard.py

Reads holdings.json, history.csv, trades.csv and the latest price snapshot;
embeds them as JSON and renders a self-contained page (no external JS).
"""
import glob
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import check_drift

OUT = os.path.join(lib.ROOT, "dashboard", "index.html")


def build():
    h = lib.load_holdings()
    hist = lib.read_history()
    trades = lib.read_trades()
    latest = os.path.basename(sorted(glob.glob(os.path.join(lib.PRICES, "*.json")))[-1])[:-5]
    closes = lib.load_prices(latest)["closes"]
    equity, nav, detail = lib.valuation(h, closes)

    spy0 = float(hist[0]["spy_close"])
    nav0 = float(hist[0]["nav"])
    series = [{
        "date": r["date"],
        "nav": float(r["nav"]),
        "port": float(r["nav"]) / nav0 * 100,
        "spy": float(r["spy_close"]) / spy0 * 100,
        "day": float(r["day_return_pct"]),
    } for r in hist]

    last = series[-1]
    cum = last["port"] - 100
    spy_cum = last["spy"] - 100
    _, _, _, _, _, _, proposals, reviews = check_drift.analyse(latest)

    sectors = {}
    for d in detail.values():
        sectors[d["sector"]] = sectors.get(d["sector"], 0) + d["weight"]

    holdings = []
    for sym, d in sorted(detail.items(), key=lambda kv: -kv[1]["weight"]):
        breached = (abs(d["drift_rel"]) > check_drift.REL_BAND
                    or abs(d["drift_pp"]) > check_drift.ABS_BAND)
        holdings.append({
            "symbol": sym, "sector": d["sector"], "shares": d["shares"],
            "price": d["price"], "value": d["value"], "weight": d["weight"] * 100,
            "target": d["target_weight"] * 100, "drift_pp": d["drift_pp"],
            "drift_rel": d["drift_rel"], "pl": d["unrealized_pct"],
            "vs_spy": d["unrealized_pct"] - spy_cum, "cost": d["cost_basis"],
            "flag": "review" if any(s == sym for s, _ in reviews)
                    else "drift" if breached else "ok",
            "thesis": next(p["thesis"] for p in h["positions"] if p["symbol"] == sym),
        })

    data = {
        "name": h["portfolio_name"], "asof": latest, "built": date.today().isoformat(),
        "inception": h["inception_date"], "capital": h["inception_capital"],
        "nav": nav, "cash": h["cash"], "equity": equity,
        "cum": cum, "spy_cum": spy_cum, "excess": cum - spy_cum,
        "day": last["day"], "days": len(series),
        "series": series, "holdings": holdings,
        "sectors": sorted(((k, v * 100) for k, v in sectors.items()), key=lambda x: -x[1]),
        "trades": trades[-20:][::-1], "proposals": proposals,
        "reviews": [{"symbol": s, "why": w} for s, w in reviews],
        "bands": {"rel": check_drift.REL_BAND, "abs": check_drift.ABS_BAND,
                  "min_trade": check_drift.MIN_TRADE, "cap": check_drift.MAX_POS_MKT * 100},
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(html)
    print(f"wrote {os.path.relpath(OUT, lib.ROOT)}  ({len(series)} sessions, as of {latest})")


TEMPLATE = r"""<title>Model Alpha-12</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  color-scheme: light;
  --page: #f1f3f6; --surface: #ffffff; --surface-2: #f6f7f9;
  --ink: #0e1420; --ink-2: #4a5468; --muted: #8590a2;
  --line: #e2e5ea; --line-2: #cfd4dc; --ring: rgba(14,20,32,.10);
  --port: #2a78d6; --port-soft: rgba(42,120,214,.12);
  --bench: #8a8f99; --bench-soft: rgba(138,143,153,.14);
  --good: #0a7a2f; --good-soft: rgba(12,163,12,.12);
  --bad: #c43535; --bad-soft: rgba(208,59,59,.12);
  --warn: #b9770e; --warn-soft: rgba(250,178,25,.18);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0f1115; --surface: #171a20; --surface-2: #1e222a;
    --ink: #f3f4f6; --ink-2: #b9bfcb; --muted: #7d8595;
    --line: #262b34; --line-2: #343a45; --ring: rgba(255,255,255,.10);
    --port: #4a92ea; --port-soft: rgba(74,146,234,.16);
    --bench: #8a8f99; --bench-soft: rgba(138,143,153,.18);
    --good: #3ec26a; --good-soft: rgba(62,194,106,.14);
    --bad: #ef6b6b; --bad-soft: rgba(239,107,107,.14);
    --warn: #f0b64a; --warn-soft: rgba(240,182,74,.16);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0f1115; --surface: #171a20; --surface-2: #1e222a;
  --ink: #f3f4f6; --ink-2: #b9bfcb; --muted: #7d8595;
  --line: #262b34; --line-2: #343a45; --ring: rgba(255,255,255,.10);
  --port: #4a92ea; --port-soft: rgba(74,146,234,.16);
  --bench: #8a8f99; --bench-soft: rgba(138,143,153,.18);
  --good: #3ec26a; --good-soft: rgba(62,194,106,.14);
  --bad: #ef6b6b; --bad-soft: rgba(239,107,107,.14);
  --warn: #f0b64a; --warn-soft: rgba(240,182,74,.16);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 14px/1.5 "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif; }
.mono { font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace; font-variant-numeric: tabular-nums; }
.wrap { max-width: 1120px; margin: 0 auto; padding: 28px 24px 56px; display: grid; gap: 20px; }
header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 18px; }
h1 { margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -.01em; }
.eyebrow { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); font-weight: 500; }
.badge { font-size: 11px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase;
  padding: 3px 8px; border-radius: 3px; border: 1px solid var(--line-2); color: var(--ink-2); }
.badge.paper { background: var(--warn-soft); border-color: transparent; color: var(--warn); }
header .asof { margin-left: auto; color: var(--ink-2); }
section { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
section > h2 { margin: 0; padding: 14px 18px; font-size: 13px; font-weight: 600; border-bottom: 1px solid var(--line);
  display: flex; align-items: center; gap: 10px; }
section > h2 .sub { font-weight: 400; color: var(--muted); margin-left: auto; font-size: 12px; }

.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0; background: var(--surface);
  border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.stat { padding: 16px 18px; border-right: 1px solid var(--line); min-width: 0; }
.stat:last-child { border-right: 0; }
.stat .v { font-size: 26px; font-weight: 500; line-height: 1.15; margin-top: 6px; letter-spacing: -.01em; }
.stat .d { font-size: 12px; color: var(--ink-2); margin-top: 4px; }
.stat.hero { background: var(--port-soft); }
.up { color: var(--good); } .down { color: var(--bad); }

.chart { padding: 16px 18px 8px; }
.chart svg { width: 100%; height: auto; display: block; }
.chart text { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11px; fill: var(--muted); }
.chart .grid { stroke: var(--line); stroke-width: 1; }
.chart .base { stroke: var(--line-2); stroke-width: 1; }
.chart .l-port { stroke: var(--port); stroke-width: 2; fill: none; stroke-linejoin: round; }
.chart .a-port { fill: var(--port-soft); }
.chart .l-spy { stroke: var(--bench); stroke-width: 2; fill: none; stroke-dasharray: 5 4; stroke-linejoin: round; }
.chart .end { stroke: var(--surface); stroke-width: 2; }
.chart .xh { stroke: var(--line-2); stroke-width: 1; stroke-dasharray: 2 3; }
.legend { display: flex; gap: 18px; padding: 6px 18px 14px; font-size: 12px; color: var(--ink-2); flex-wrap: wrap; align-items: center; }
.legend i { display: inline-block; width: 18px; height: 0; border-top: 2px solid var(--port); vertical-align: middle; margin-right: 6px; }
.legend i.spy { border-top-style: dashed; border-color: var(--bench); }
.legend .note { margin-left: auto; color: var(--muted); }
.tip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--line-2);
  border-radius: 4px; padding: 8px 10px; font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,.10); display: none; min-width: 150px; }
.tip b { display: block; margin-bottom: 4px; }
.tip .row { display: flex; justify-content: space-between; gap: 14px; }
.chartwrap { position: relative; }

table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px 12px; text-align: right; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 500; }
th:first-child, td:first-child, th.l, td.l { text-align: left; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover td { background: var(--surface-2); }
td.sym { font-weight: 500; }
td .sec { display: block; font-size: 11px; color: var(--muted); font-family: "IBM Plex Sans", sans-serif; font-weight: 400; }
.wbar { display: inline-block; width: 90px; height: 6px; background: var(--surface-2); border: 1px solid var(--line); border-radius: 2px;
  position: relative; vertical-align: middle; margin-right: 8px; }
.wbar span { position: absolute; left: 0; top: 0; bottom: 0; background: var(--port); border-radius: 1px; }
.wbar em { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--ink-2); }
.pill { display: inline-block; font-size: 11px; padding: 2px 7px; border-radius: 3px; font-weight: 500; }
.pill.ok { background: var(--good-soft); color: var(--good); }
.pill.drift { background: var(--warn-soft); color: var(--warn); }
.pill.review { background: var(--bad-soft); color: var(--bad); }
.tscroll { overflow-x: auto; }
tfoot td { color: var(--ink-2); font-size: 12px; border-top: 1px solid var(--line-2); }

.two { display: grid; grid-template-columns: 1.1fr .9fr; gap: 20px; }
@media (max-width: 800px) { .two { grid-template-columns: 1fr; } }
.rules { padding: 14px 18px; display: grid; gap: 10px; font-size: 13px; color: var(--ink-2); }
.rules dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; }
.rules dt { color: var(--muted); }
.rules dd { margin: 0; }
.sectors { padding: 8px 18px 14px; display: grid; gap: 6px; }
.srow { display: grid; grid-template-columns: 150px 1fr 56px; align-items: center; gap: 10px; font-size: 12px; }
.srow .bar { height: 8px; background: var(--surface-2); border-radius: 2px; overflow: hidden; }
.srow .bar span { display: block; height: 100%; background: var(--port); }
.empty { padding: 18px; color: var(--muted); font-size: 13px; }
.alert { margin: 14px 18px 0; padding: 10px 12px; border-radius: 4px; font-size: 13px; }
.alert.warn { background: var(--warn-soft); color: var(--warn); }
.alert.bad { background: var(--bad-soft); color: var(--bad); }
details { padding: 0 18px 12px; color: var(--ink-2); font-size: 13px; }
summary { cursor: pointer; padding: 10px 0; color: var(--ink); font-weight: 500; }
.thesis { display: grid; gap: 8px; }
.thesis div b { font-family: "IBM Plex Mono", monospace; font-weight: 500; margin-right: 8px; }
footer { color: var(--muted); font-size: 12px; line-height: 1.6; }
</style>

<div class="wrap">
<header>
  <div>
    <div class="eyebrow">Paper portfolio · $10,000 · vs SPY</div>
    <h1 id="name"></h1>
  </div>
  <span class="badge paper">Paper · no live orders</span>
  <div class="asof">As of close <b class="mono" id="asof"></b> · <span id="days"></span></div>
</header>

<div class="stats" id="stats"></div>

<section>
  <h2>Growth of $10,000 <span class="sub">Indexed to 100 at inception · daily closes</span></h2>
  <div class="chartwrap"><div class="chart" id="chart"></div><div class="tip" id="tip"></div></div>
  <div class="legend"><span><i></i>Model Alpha-12</span><span><i class="spy"></i>SPY</span><span class="note" id="cnote"></span></div>
</section>

<section>
  <h2>Holdings <span class="sub" id="hsub"></span></h2>
  <div id="alerts"></div>
  <div class="tscroll"><table id="holdings">
    <thead><tr>
      <th class="l">Symbol</th><th>Shares</th><th>Price</th><th>Value</th>
      <th class="l">Weight vs target</th><th>Drift</th><th>P/L</th><th>vs SPY</th><th class="l">Band</th>
    </tr></thead><tbody></tbody><tfoot></tfoot>
  </table></div>
  <details><summary>Position theses</summary><div class="thesis" id="thesis"></div></details>
</section>

<div class="two">
  <section>
    <h2>Rebalancing rules <span class="sub">checked after every close</span></h2>
    <div class="rules" id="rules"></div>
    <div class="sectors" id="sectors"></div>
  </section>
  <section>
    <h2>Trade log <span class="sub">most recent first</span></h2>
    <div id="trades"></div>
  </section>
</div>

<footer>Model portfolio for research only, not investment advice. Prices are regular-session last trades from Robinhood market data;
NAV is marked at those closes with no commissions, slippage or dividends. Rules are in <span class="mono">portfolio/strategy.md</span>;
every close and trade is logged in <span class="mono">portfolio/history.csv</span> and <span class="mono">portfolio/trades.csv</span>.
Page built <span id="built" class="mono"></span>.</footer>
</div>

<script>
const D = __DATA__;
const $ = s => document.querySelector(s);
const usd = n => n.toLocaleString("en-US", {style:"currency", currency:"USD"});
const pct = n => { if (Math.abs(n) < 0.005) n = 0; return (n > 0 ? "+" : "") + n.toFixed(2) + "%"; };
const pp = n => { if (Math.abs(n) < 0.005) n = 0; return (n > 0 ? "+" : "") + n.toFixed(2) + " pp"; };
const cls = n => n > 0.0001 ? "up" : n < -0.0001 ? "down" : "";

$("#name").textContent = D.name;
$("#asof").textContent = D.asof;
$("#days").textContent = D.days === 1 ? "inception" : D.days + " sessions since " + D.inception;
$("#built").textContent = D.built;

$("#stats").innerHTML = [
  ["Account value", usd(D.nav), `Cash ${usd(D.cash)} (${(D.cash/D.nav*100).toFixed(1)}%)`, "", "mono"],
  ["Total return", pct(D.cum), `From ${usd(D.capital)} on ${D.inception}`, cls(D.cum), "mono"],
  ["SPY, same period", pct(D.spy_cum), "Price return, indexed to inception close", cls(D.spy_cum), "mono"],
  ["Excess vs SPY", pp(D.excess), D.excess >= 0 ? "Ahead of benchmark" : "Behind benchmark", cls(D.excess), "mono hero"],
  ["Last session", pct(D.day), D.days === 1 ? "Inception — no prior close" : "Portfolio day change", cls(D.day), "mono"],
].map(([l,v,d,c,x]) => `<div class="stat ${x.includes("hero")?"hero":""}"><div class="eyebrow">${l}</div>
  <div class="v mono ${c}">${v}</div><div class="d">${d}</div></div>`).join("");

// ---- chart ----------------------------------------------------------------
(function chart(){
  const S = D.series, W = 1000, H = 320, m = {t:16, r:52, b:28, l:12};
  const n = S.length;
  const vals = S.flatMap(p => [p.port, p.spy]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (hi - lo < 4) { const c = (hi+lo)/2; lo = c - 2; hi = c + 2; }
  const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
  const x = i => n === 1 ? W/2 : m.l + (i/(n-1)) * (W - m.l - m.r);
  const y = v => m.t + (1 - (v - lo)/(hi - lo)) * (H - m.t - m.b);

  const ticks = []; const step = (hi-lo) > 30 ? 10 : (hi-lo) > 12 ? 5 : (hi-lo) > 6 ? 2 : 1;
  for (let v = Math.ceil(lo/step)*step; v <= hi; v += step) ticks.push(v);
  let g = ticks.map(v => `<line class="${v===100?'base':'grid'}" x1="${m.l}" x2="${W-m.r}" y1="${y(v)}" y2="${y(v)}"/>
    <text x="${W-m.r+8}" y="${y(v)+4}">${v}</text>`).join("");

  const path = k => S.map((p,i) => (i?"L":"M") + x(i).toFixed(1) + " " + y(p[k]).toFixed(1)).join(" ");
  if (n > 1) {
    g += `<path class="a-port" d="${path('port')} L${x(n-1).toFixed(1)} ${y(lo)} L${x(0)} ${y(lo)} Z"/>`;
    g += `<path class="l-spy" d="${path('spy')}"/><path class="l-port" d="${path('port')}"/>`;
    // x labels: first, last, and up to 4 between
    const k = Math.max(1, Math.floor((n-1)/5));
    for (let i = 0; i < n; i += k) g += `<text x="${x(i)}" y="${H-8}" text-anchor="${i===0?'start':'middle'}">${S[i].date.slice(5)}</text>`;
    if ((n-1) % k) g += `<text x="${x(n-1)}" y="${H-8}" text-anchor="end">${S[n-1].date.slice(5)}</text>`;
  } else {
    g += `<text x="${W/2}" y="${H-8}" text-anchor="middle">${S[0].date}</text>`;
  }
  const e = S[n-1];
  g += `<circle class="end" cx="${x(n-1)}" cy="${y(e.spy)}" r="4" fill="var(--bench)"/>
        <circle class="end" cx="${x(n-1)}" cy="${y(e.port)}" r="4.5" fill="var(--port)"/>
        <line id="xh" class="xh" y1="${m.t}" y2="${H-m.b}" x1="-10" x2="-10"/>`;
  $("#chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" id="svg" aria-label="Portfolio vs SPY, indexed">${g}</svg>`;
  $("#cnote").textContent = n === 1 ? "Track record begins here — the next close adds the first data point."
    : `Portfolio ${e.port.toFixed(1)} · SPY ${e.spy.toFixed(1)}`;

  const svg = $("#svg"), tip = $("#tip"), xh = $("#xh"), wrap = $(".chartwrap");
  svg.addEventListener("mousemove", ev => {
    const r = svg.getBoundingClientRect(); const px = (ev.clientX - r.left) / r.width * W;
    let i = n === 1 ? 0 : Math.round((px - m.l) / (W - m.l - m.r) * (n-1)); i = Math.max(0, Math.min(n-1, i));
    const p = S[i]; xh.setAttribute("x1", x(i)); xh.setAttribute("x2", x(i));
    tip.innerHTML = `<b class="mono">${p.date}</b>
      <div class="row"><span>Portfolio</span><span class="mono ${cls(p.port-100)}">${pct(p.port-100)}</span></div>
      <div class="row"><span>SPY</span><span class="mono ${cls(p.spy-100)}">${pct(p.spy-100)}</span></div>
      <div class="row"><span>Excess</span><span class="mono ${cls(p.port-p.spy)}">${pp(p.port-p.spy)}</span></div>
      <div class="row"><span>NAV</span><span class="mono">${usd(p.nav)}</span></div>`;
    tip.style.display = "block";
    const wr = wrap.getBoundingClientRect(); let tx = ev.clientX - wr.left + 14;
    if (tx + 170 > wr.width) tx = ev.clientX - wr.left - 184;
    tip.style.left = tx + "px"; tip.style.top = (ev.clientY - wr.top - 10) + "px";
  });
  svg.addEventListener("mouseleave", () => { tip.style.display = "none"; xh.setAttribute("x1", -10); xh.setAttribute("x2", -10); });
})();

// ---- holdings ---------------------------------------------------------------
$("#hsub").textContent = `${D.holdings.length} positions · equity ${usd(D.equity)}`;
const maxW = Math.max(...D.holdings.map(h => Math.max(h.weight, h.target))) * 1.15;
$("#holdings tbody").innerHTML = D.holdings.map(h => `<tr>
  <td class="sym mono">${h.symbol}<span class="sec">${h.sector}</span></td>
  <td class="mono">${h.shares.toFixed(4)}</td>
  <td class="mono">${h.price.toFixed(2)}</td>
  <td class="mono">${usd(h.value)}</td>
  <td class="l"><span class="wbar"><span style="width:${h.weight/maxW*100}%"></span><em style="left:${h.target/maxW*100}%"></em></span>
      <span class="mono">${h.weight.toFixed(2)}%</span> <span class="mono" style="color:var(--muted)">/ ${h.target.toFixed(0)}%</span></td>
  <td class="mono ${Math.abs(h.drift_pp) > D.bands.abs ? 'down' : ''}">${pp(h.drift_pp)}</td>
  <td class="mono ${cls(h.pl)}">${pct(h.pl)}</td>
  <td class="mono ${cls(h.vs_spy)}">${pp(h.vs_spy)}</td>
  <td class="l"><span class="pill ${h.flag}">${h.flag === 'ok' ? 'in band' : h.flag === 'drift' ? 'drifted' : 'thesis review'}</span></td>
</tr>`).join("");
$("#holdings tfoot").innerHTML = `<tr><td class="l">Cash</td><td></td><td></td><td class="mono">${usd(D.cash)}</td>
  <td class="l mono">${(D.cash/D.nav*100).toFixed(2)}% <span style="color:var(--muted)">/ 3%</span></td><td colspan="4"></td></tr>`;
$("#thesis").innerHTML = D.holdings.map(h => `<div><b>${h.symbol}</b>${h.thesis}</div>`).join("");

let al = "";
if (D.reviews.length) al += `<div class="alert bad">Thesis review required: ${D.reviews.map(r => `<b class="mono">${r.symbol}</b> (${r.why})`).join(", ")}</div>`;
if (D.proposals.length) al += `<div class="alert warn">Rebalance proposed: ${D.proposals.map(p => `${p.side} ${usd(p.notional)} ${p.symbol}`).join(" · ")}</div>`;
$("#alerts").innerHTML = al;

// ---- rules + sectors ----------------------------------------------------------
$("#rules").innerHTML = `<dl>
  <dt>Drift band</dt><dd>±${D.bands.rel}% of target <em>or</em> ±${D.bands.abs} pp absolute — whichever trips first</dd>
  <dt>Churn floor</dt><dd>No trade under ${usd(D.bands.min_trade)}; drift below that is logged, not traded</dd>
  <dt>Position cap</dt><dd>${D.bands.cap}% at market forces a trim regardless of band</dd>
  <dt>Thesis review</dt><dd>−20% from cost, or −15 pp vs SPY since entry</dd>
  <dt>Frequency</dt><dd>Max 4 trades per 5 sessions; 10-session cooldown before re-buying a sold name</dd>
</dl>`;
const maxS = D.sectors[0][1];
$("#sectors").innerHTML = `<div class="eyebrow" style="margin:6px 0 4px">Sector exposure</div>` +
  D.sectors.map(([s,w]) => `<div class="srow"><span>${s}</span><span class="bar"><span style="width:${w/maxS*100}%"></span></span>
  <span class="mono" style="text-align:right">${w.toFixed(1)}%</span></div>`).join("");

// ---- trades ---------------------------------------------------------------------
$("#trades").innerHTML = D.trades.length
  ? `<div class="tscroll"><table><thead><tr><th class="l">Date</th><th class="l">Side</th><th class="l">Symbol</th><th>Shares</th><th>Price</th><th>Notional</th><th class="l">Reason</th></tr></thead>
     <tbody>${D.trades.map(t => `<tr><td class="l mono">${t.date}</td><td class="l">${t.side}</td><td class="l mono">${t.symbol}</td>
     <td class="mono">${(+t.shares).toFixed(4)}</td><td class="mono">${(+t.price).toFixed(2)}</td><td class="mono">${usd(+t.notional)}</td><td class="l">${t.reason}</td></tr>`).join("")}</tbody></table></div>`
  : `<div class="empty">No rebalancing trades yet. The inception basket was bought at the ${D.inception} close.</div>`;
</script>
"""

if __name__ == "__main__":
    build()
