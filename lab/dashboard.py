"""Build the public dashboard (site/index.html) from the ledger only.

Read-only with respect to trading: it imports nothing from strategy, risk or
execution code, and it never writes to the ledger.
"""
from __future__ import annotations

import html
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "ledger" / "events.jsonl"
STATE_DIR = ROOT / "ledger" / "state"
OUT = ROOT / "site" / "index.html"
REPO_URL = "https://github.com/athompson82/ai-trading-lab"

# Pre-registered schedule (docs/STATUS.md). Changing these does not change scoring.
SHAKEDOWN_END = date(2026, 12, 13)
SCORED_START = date(2026, 12, 14)
INTERIM = date(2027, 2, 12)
SCORED_END = date(2027, 3, 14)

SLEEVES = {
    "etf": {"title": "ETF sleeve", "arms": ["etf_trend", "etf_trend_ai", "etf_bench_spy", "etf_bench_60_40", "etf_ai_trader"]},
    "crypto": {"title": "Crypto sleeve", "arms": ["crypto_trend", "crypto_trend_ai", "crypto_bench_btc",
                                                  "crypto_bench_btc_eth_50_50", "crypto_ai_trader"]},
}
LABELS = {
    "etf_trend": "Trend strategy", "etf_trend_ai": "Trend + AI overlay", "etf_bench_spy": "S&P 500 (SPY)",
    "etf_bench_60_40": "60/40 stocks/bonds", "crypto_trend": "Trend strategy", "crypto_trend_ai": "Trend + AI overlay",
    "crypto_bench_btc": "Bitcoin", "crypto_bench_btc_eth_50_50": "50/50 BTC/ETH",
    "etf_ai_trader": "AI trader (news + trends)", "crypto_ai_trader": "AI trader (news + trends)",
}


def _verify_chain(events: list[dict]) -> tuple[bool, str]:
    import hashlib
    prev = "0" * 64
    for i, ev in enumerate(events, start=1):
        body = {k: v for k, v in ev.items() if k != "hash"}
        h = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        if ev.get("seq") != i or ev.get("prev_hash") != prev or h != ev.get("hash"):
            return False, f"problem at entry {i}"
        prev = ev["hash"]
    return True, f"{len(events)} entries verified"


def collect() -> dict:
    events = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()] if LEDGER.exists() else []
    ok, msg = _verify_chain(events)
    series, positions = {}, {}
    for f in sorted(STATE_DIR.glob("*.json")) if STATE_DIR.exists() else []:
        st = json.loads(f.read_text())
        series[st["arm"]] = st["equity"]
        positions[st["arm"]] = {"pending": st.get("pending"), "cash": st["portfolio"]["cash"],
                                "start": st.get("start")}
    marks = {}
    for e in events:
        if e["type"] == "mark":
            marks[e["data"]["arm"]] = e["data"]
    fills = [e["data"] | {"seq": e["seq"]} for e in events if e["type"] == "fill"]
    decisions = [e["data"] | {"seq": e["seq"]} for e in events if e["type"] == "decision"]
    runs = [e for e in events if e["type"] in ("run_start", "run_end", "data_error")]
    holdout = next((e["data"] for e in reversed(events) if e["type"] == "holdout_evaluation"), None)
    start = os.environ.get("FORWARD_START") or next(
        (e["data"].get("start") for e in events if e["type"] == "run_start"), None)
    return {"events": events, "chain_ok": ok, "chain_msg": msg, "series": series, "positions": positions,
            "marks": marks, "fills": fills, "decisions": decisions, "runs": runs, "holdout": holdout,
            "start": start}


def reliability(runs: list[dict], start: str | None) -> dict:
    """Expected one completed run per UTC day from the day after the forward start."""
    if not start:
        return {"expected": 0, "completed": 0, "missed": [], "errors": 0}
    first = date.fromisoformat(start) + timedelta(days=1)
    today = datetime.now(timezone.utc).date()
    done = {e["ts"][:10] for e in runs if e["type"] == "run_end"}
    expected = [first + timedelta(days=i) for i in range((today - first).days + 1)] if today >= first else []
    # Today's run counts as expected only once its scheduled time (01:17 UTC) has passed.
    if expected and expected[-1] == today and datetime.now(timezone.utc).hour < 2 and str(today) not in done:
        expected = expected[:-1]
    missed = [str(d) for d in expected if str(d) not in done]
    return {"expected": len(expected), "completed": len(expected) - len(missed), "missed": missed,
            "errors": sum(1 for e in runs if e["type"] == "data_error")}


def phase(today: date, start: str | None) -> tuple[str, str]:
    if not start:
        return "Not started", "The forward test has not started."
    s = date.fromisoformat(start)
    if today <= SHAKEDOWN_END:
        return "Shakedown (not scored)", f"Day {(today - s).days + 1} of shakedown. Scoring begins {SCORED_START:%-d %B %Y}."
    if today <= SCORED_END:
        d = (today - SCORED_START).days + 1
        return "Scored window", f"Day {d} of 90. Interim report {INTERIM:%-d %B %Y}; final {SCORED_END:%-d %B %Y}."
    return "Scored window complete", "Final evaluation due (or optional extension to 6 months)."


def _esc(x) -> str:
    return html.escape(str(x))


def build() -> str:
    d = collect()
    today = datetime.now(timezone.utc).date()
    ph, ph_detail = phase(today, d["start"])
    rel = reliability(d["runs"], d["start"])
    last_run = next((e["ts"] for e in reversed(d["runs"]) if e["type"] == "run_end"), None)

    # ---- summary table rows
    rows = []
    for key, sl in SLEEVES.items():
        for arm in sl["arms"]:
            eq = d["series"].get(arm, [])
            vals = [v for _, v in eq]
            if vals:
                peak, mdd = vals[0], 0.0
                for v in vals:
                    peak = max(peak, v)
                    mdd = min(mdd, v / peak - 1)
                ret = vals[-1] / 5000.0 - 1
            cost = sum(f.get("cost_usd", 0) for f in d["fills"] if f["arm"] == arm)
            ntr = sum(1 for f in d["fills"] if f["arm"] == arm)
            rows.append(
                f"<tr><td>{_esc(sl['title'])}</td><td>{_esc(LABELS[arm])}</td>"
                + (f"<td class=num>${vals[-1]:,.2f}</td><td class=num>{ret:+.2%}</td><td class=num>{mdd:.1%}</td>"
                   if vals else "<td class=num>$5,000.00</td><td class=num>—</td><td class=num>—</td>")
                + f"<td class=num>{ntr}</td><td class=num>${cost:,.2f}</td></tr>")

    # ---- positions
    pos_html = []
    for arm in ("etf_trend", "etf_trend_ai", "etf_ai_trader", "crypto_trend", "crypto_trend_ai", "crypto_ai_trader"):
        m = d["marks"].get(arm)
        p = d["positions"].get(arm, {})
        held = {k: v for k, v in (m or {}).get("weights", {}).items() if abs(v) > 1e-4}
        tgt = {k: v for k, v in (p.get("pending") or {}).items() if v}
        assets = sorted(set(held) | set(tgt))
        body = "".join(f"<tr><td>{_esc(a)}</td><td class=num>{held.get(a, 0):.1%}</td>"
                       f"<td class=num>{'' if tgt.get(a) is None else f'{tgt[a]:.1%}'}</td></tr>" for a in assets)
        cash_w = 1 - sum(held.values()) if m else 1.0
        pos_html.append(
            f"<div class=card><h3>{_esc(LABELS[arm])} <span class=muted>· {_esc(arm.split('_')[0].upper())}</span></h3>"
            f"<table><thead><tr><th>Asset</th><th class=num>Held now</th><th class=num>Next target</th></tr></thead>"
            f"<tbody>{body or '<tr><td colspan=3 class=muted>No positions yet</td></tr>'}"
            f"<tr><td class=muted>Cash</td><td class=num>{cash_w:.1%}</td><td></td></tr></tbody></table>"
            f"<p class=muted small>As of {_esc((m or {}).get('date', '—'))}</p></div>")

    # ---- trades
    trade_rows = "".join(
        f"<tr><td>{_esc(str(f['date'])[:10])}</td><td>{_esc(LABELS.get(f['arm'], f['arm']))} "
        f"<span class=muted>({_esc(f['arm'].split('_')[0].upper())})</span></td><td>{_esc(f['asset'])}</td>"
        f"<td>{'Buy' if f['units'] > 0 else 'Sell'}</td><td class=num>{abs(f['units']):,.6g}</td>"
        f"<td class=num>${f['price']:,.2f}</td><td class=num>${abs(f['units']) * f['fill_price']:,.2f}</td>"
        f"<td class=num>${f['cost_usd']:,.2f}</td></tr>"
        for f in reversed(d["fills"][-200:]))

    # ---- decisions with risk notes
    dec_rows = "".join(
        f"<tr><td>{_esc(x['date'])}</td><td>{_esc(LABELS.get(x['arm'], x['arm']))} "
        f"<span class=muted>({_esc(x['arm'].split('_')[0].upper())})</span></td>"
        f"<td>{_esc(', '.join(f'{k} {v:.0%}' for k, v in (x.get('target') or {}).items() if v) or 'All cash')}</td>"
        f"<td>{_esc('; '.join(x.get('risk_notes') or []) or '—')}</td>"
        f"<td>{_esc((x.get('overlay_meta') or {}).get('status', '—')) if x['arm'].endswith('_ai') else ''}</td></tr>"
        for x in list(reversed([y for y in d["decisions"] if "_bench" not in y["arm"]]))[:60])

    # ---- holdout verdicts
    ho_html = ""
    if d["holdout"]:
        for name, s in sorted(d["holdout"]["sleeves"].items(), key=lambda kv: kv[0] != "etf_trend"):
            items = "".join(
                f"<li><span class='badge {'ok' if v['met'] else 'no'}'>{'✓ Met' if v['met'] else '✗ Not met'}</span> "
                f"{_esc(k)} <span class=muted>{_esc(v['detail'])}</span></li>"
                for k, v in s["verdict"].items())
            ho_html += f"<div class=card><h3>{'ETF sleeve' if name.startswith('etf') else 'Crypto sleeve'}</h3><ul class=verdicts>{items}</ul></div>"

    rel_ok = rel["expected"] == 0 or (rel["completed"] / rel["expected"] >= 0.99)
    chart_data = {k: {"title": v["title"], "series": [
        {"id": a, "label": LABELS[a], "points": d["series"].get(a, [])} for a in v["arms"]]}
        for k, v in SLEEVES.items()}

    page = TEMPLATE
    for k, v in {
        "{{GENERATED}}": f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        "{{PHASE}}": _esc(ph), "{{PHASE_DETAIL}}": _esc(ph_detail),
        "{{LAST_RUN}}": _esc(last_run[:16].replace("T", " ") + " UTC" if last_run else "No runs yet"),
        "{{RUNS}}": f"{rel['completed']} of {rel['expected']}",
        "{{RUNS_CLASS}}": "ok" if rel_ok else "no",
        "{{MISSED}}": _esc(", ".join(rel["missed"][-10:]) or "none"),
        "{{DATA_ERRORS}}": str(rel["errors"]),
        "{{CHAIN}}": ("✓ " if d["chain_ok"] else "✗ ") + _esc(d["chain_msg"]),
        "{{CHAIN_CLASS}}": "ok" if d["chain_ok"] else "no",
        "{{SUMMARY_ROWS}}": "".join(rows),
        "{{POSITIONS}}": "".join(pos_html),
        "{{TRADES}}": trade_rows or "<tr><td colspan=8 class=muted>No trades yet. The first fills happen at the "
                                    "open after the first decision.</td></tr>",
        "{{DECISIONS}}": dec_rows or "<tr><td colspan=5 class=muted>No decisions yet.</td></tr>",
        "{{HOLDOUT}}": ho_html or "<p class=muted>Not yet evaluated.</p>",
        "{{START}}": _esc(d["start"] or "not set"),
        "{{REPO}}": REPO_URL,
        "{{DATA}}": json.dumps(chart_data).replace("</", "<\\/"),
    }.items():
        page = page.replace(k, v)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page)
    return str(OUT)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Trading Lab</title>
<meta name="description" content="Live dashboard for a pre-registered paper-trading experiment. Simulated money only.">
<style>
:root{color-scheme:light;--bg:#f7f7f5;--surface:#fcfcfb;--border:#e4e3df;--text:#0b0b0b;--text2:#52514e;--muted:#7a7974;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--grid:#ecebe7;--good:#006300;--goodbg:#e3f3e3;--bad:#b02a2a;--badbg:#fbe6e6}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--bg:#111110;--surface:#1a1a19;--border:#2e2e2b;
--text:#f0efec;--text2:#c3c2b7;--muted:#8f8e86;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--grid:#262624;--good:#5fd35f;--goodbg:#173017;--bad:#ff8a8a;--badbg:#3a1a1a}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#111110;--surface:#1a1a19;--border:#2e2e2b;--text:#f0efec;--text2:#c3c2b7;--muted:#8f8e86;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--grid:#262624;--good:#5fd35f;--goodbg:#173017;--bad:#ff8a8a;--badbg:#3a1a1a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 12px}
h3{font-size:15px;margin:0 0 10px}.muted{color:var(--muted)}.small{font-size:13px}p{margin:6px 0}
.banner{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 16px;margin:16px 0;color:var(--text2)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px;min-width:0}
.tile .k{font-size:13px;color:var(--text2)}.tile .v{font-size:20px;font-weight:600;margin-top:2px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}th{color:var(--text2);font-weight:600}
.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600}
.ok{color:var(--good);background:var(--goodbg)}.no{color:var(--bad);background:var(--badbg)}
ul.verdicts{list-style:none;padding:0;margin:0}ul.verdicts li{padding:5px 0;border-bottom:1px solid var(--border)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--text2);margin:4px 0 8px}
.legend span{display:inline-flex;align-items:center;gap:6px}.legend i{width:14px;height:3px;border-radius:2px;display:inline-block}
.chart{position:relative}.chart svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px 10px;
font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;white-space:nowrap;z-index:2}
.empty{padding:40px 8px;text-align:center;color:var(--muted)}
details summary{cursor:pointer;color:var(--text2)}footer{margin-top:40px;font-size:13px;color:var(--muted)}a{color:var(--s1)}
</style></head><body><main>
<h1>AI Trading Lab</h1>
<p class=muted>Pre-registered paper-trading experiment · <strong>simulated money only</strong> · updated {{GENERATED}}</p>
<div class=banner><strong>{{PHASE}}.</strong> {{PHASE_DETAIL}} Short-term results are dominated by luck: over 90 days a Sharpe ratio is uncertain by about ±2, so judge this test mainly on reliability and on consistency with the backtest.</div>

<div class=tiles>
 <div class="card tile"><div class=k>Last nightly run</div><div class=v>{{LAST_RUN}}</div></div>
 <div class="card tile"><div class=k>Nightly runs completed</div><div class=v><span class="badge {{RUNS_CLASS}}">{{RUNS}}</span></div><div class="muted small">Missed: {{MISSED}} · data errors: {{DATA_ERRORS}}</div></div>
 <div class="card tile"><div class=k>Ledger tamper check</div><div class=v><span class="badge {{CHAIN_CLASS}}">{{CHAIN}}</span></div></div>
 <div class="card tile"><div class=k>Forward test start</div><div class=v>{{START}}</div><div class="muted small">US$5,000 per portfolio</div></div>
</div>

<h2>Portfolio value</h2>
<p class="muted small">Each portfolio started with US$5,000 (dotted line). The "Trend + AI overlay" portfolios behave identically to the plain trend portfolios until the AI overlay is switched on; that period is excluded from the AI comparison.</p>
<div class=grid2 id=charts></div>

<h2>Summary</h2>
<div class="card scroll"><table><thead><tr><th>Sleeve</th><th>Portfolio</th><th class=num>Value</th><th class=num>Return</th><th class=num>Worst drop</th><th class=num>Trades</th><th class=num>Costs paid</th></tr></thead>
<tbody>{{SUMMARY_ROWS}}</tbody></table></div>

<h2>Current positions</h2>
<div class=grid2>{{POSITIONS}}</div>

<h2>Recent decisions</h2>
<p class="muted small">Decisions are made after the close and filled at the next open. Risk-manager actions appear in the notes column.</p>
<div class="card scroll"><table><thead><tr><th>Date</th><th>Portfolio</th><th>Target</th><th>Risk notes</th><th>AI overlay</th></tr></thead><tbody>{{DECISIONS}}</tbody></table></div>

<h2>Trades</h2>
<div class="card scroll"><table><thead><tr><th>Date</th><th>Portfolio</th><th>Asset</th><th>Side</th><th class=num>Units</th><th class=num>Market price</th><th class=num>Amount</th><th class=num>Cost</th></tr></thead><tbody>{{TRADES}}</tbody></table></div>

<h2>Locked holdout test (one-time, Nov 2023 – Nov 2026)</h2>
<div class=grid2>{{HOLDOUT}}</div>

<footer>Source, plan and full audit trail: <a href="{{REPO}}">{{REPO}}</a> ·
<a href="{{REPO}}/blob/main/docs/PREREGISTRATION.md">Pre-registered plan</a> ·
<a href="{{REPO}}/blob/main/docs/DECISIONS.md">Decisions log</a> ·
<a href="{{REPO}}/blob/main/reports/holdout.md">Holdout report</a></footer>
</main>
<script>
const DATA={{DATA}};
const COLORS=["--s1","--s2","--s3","--s4","--s5"], DASH=["", "6 4", "", "", ""];
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt=v=>"$"+v.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
function draw(){
 const host=document.getElementById("charts"); host.innerHTML="";
 for(const key of Object.keys(DATA)){
  const sl=DATA[key], card=document.createElement("div"); card.className="card";
  card.innerHTML=`<h3>${sl.title}</h3><div class=legend>${sl.series.map((s,i)=>`<span><i style="background:var(${COLORS[i]});${i==1?'background:repeating-linear-gradient(90deg,var('+COLORS[i]+') 0 5px,transparent 5px 8px)':''}"></i>${s.label}</span>`).join("")}</div>`;
  const box=document.createElement("div"); box.className="chart"; card.appendChild(box); host.appendChild(card);
  const all=sl.series.flatMap(s=>s.points);
  if(all.length<2){box.innerHTML=`<div class=empty>No forward data yet: the chart fills in after the first nightly runs.</div>`;continue;}
  const W=520,H=260,L=64,R=12,T=10,B=28;
  const dates=[...new Set(all.map(p=>p[0]))].sort(), x0=Date.parse(dates[0]), x1=Date.parse(dates[dates.length-1])||x0+1;
  let lo=Math.min(...all.map(p=>p[1])), hi=Math.max(...all.map(p=>p[1])); const pad=(hi-lo)*0.08||50; lo-=pad; hi+=pad;
  const X=t=>L+(W-L-R)*((Date.parse(t)-x0)/((x1-x0)||1)), Y=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo));
  let g=""; for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4,y=Y(v);g+=`<line x1=${L} x2=${W-R} y1=${y} y2=${y} stroke="${css('--grid')}"/><text x=${L-6} y=${y+4} text-anchor=end font-size=11 fill="${css('--muted')}">${"$"+Math.round(v).toLocaleString()}</text>`;}
  const ticks=[dates[0],dates[Math.floor(dates.length/2)],dates[dates.length-1]];
  ticks.forEach((t,i)=>g+=`<text x=${X(t)} y=${H-8} font-size=11 text-anchor=${["start","middle","end"][i]} fill="${css('--muted')}">${t}</text>`);
  g+=`<line x1=${L} x2=${W-R} y1=${Y(5000)} y2=${Y(5000)} stroke="${css('--muted')}" stroke-dasharray="2 3" opacity="0.6"/>`;
  const lines=sl.series.map((s,i)=>s.points.length?`<path fill=none stroke="${css(COLORS[i])}" stroke-width=2 stroke-linejoin=round stroke-linecap=round ${DASH[i]?`stroke-dasharray="${DASH[i]}"`:""} d="${s.points.map((p,j)=>(j?"L":"M")+X(p[0]).toFixed(1)+" "+Y(p[1]).toFixed(1)).join(" ")}"/>`:"").join("");
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role=img aria-label="${sl.title} portfolio values">${g}${lines}<line class=xh y1=${T} y2=${H-B} stroke="${css('--muted')}" visibility=hidden/><rect x=${L} y=${T} width=${W-L-R} height=${H-T-B} fill=transparent /></svg><div class=tip></div>`;
  const svg=box.querySelector("svg"), tip=box.querySelector(".tip"), xh=box.querySelector(".xh");
  svg.addEventListener("pointermove",e=>{const r=svg.getBoundingClientRect(), px=(e.clientX-r.left)*W/r.width;
   let best=dates[0],bd=1e9; for(const t of dates){const dd=Math.abs(X(t)-px); if(dd<bd){bd=dd;best=t;}}
   xh.setAttribute("x1",X(best));xh.setAttribute("x2",X(best));xh.setAttribute("visibility","visible");
   tip.innerHTML=`<strong>${best}</strong><br>`+sl.series.map((s,i)=>{const p=s.points.find(q=>q[0]==best);return p?`<span style="color:var(${COLORS[i]})">■</span> ${s.label}: ${fmt(p[1])}`:"";}).filter(Boolean).join("<br>");
   tip.style.display="block"; const tx=X(best)*r.width/W; tip.style.left=Math.min(Math.max(tx+12,0),r.width-tip.offsetWidth)+"px"; tip.style.top="8px";});
  svg.addEventListener("pointerleave",()=>{tip.style.display="none";xh.setAttribute("visibility","hidden");});
 }
}
draw(); matchMedia("(prefers-color-scheme: dark)").addEventListener("change",draw);
</script></body></html>
"""

if __name__ == "__main__":
    print(build())
