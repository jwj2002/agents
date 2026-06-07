"""Tier-A static HTML usage report (fleet-usage-monitor §7, §8 step 6).

Pure RENDERER: reads the aggregator's JSON (#266) and emits a SELF-CONTAINED HTML page (inline data +
Chart.js from CDN, no server — Tier B FastAPI is the P2 #268 item). Six sections (§7): cost-by-project +
$/PR trend, model mix + right-sizing callout, cache efficiency trend, by-account/by-computer,
cost-by-task-tier, concurrency/utilization.

billing_type invariant (§6): subscription `cost_usd` is NOTIONAL API-equivalent value, never cash —
every subscription figure is marked `*` and a footnote explains; `mixed` figures are shown broken out,
never as one unlabeled number; `metered` figures are plain dollars.

Time-bucketed trends need the raw records (the aggregate summary collapses time); pass `records=` for
trends, else those sections show a no-data state. Changing this renderer never touches the collectors
or aggregator (clean data-layer separation, §7).
"""

from __future__ import annotations

import html
import json
from datetime import datetime

CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4"
SECTIONS = [
    ("cost_by_project", "Cost by Project & $/PR Trend"),
    ("model_mix", "Model Mix & Right-Sizing"),
    ("cache", "Cache Efficiency"),
    ("by_account", "By Account & Computer"),
    ("by_tier", "Cost by Task Tier"),
    ("concurrency", "Concurrency & Utilization"),
    ("recommendations", "Right-Sizing Recommendations"),
]
_NOTIONAL_FOOTNOTE = (
    "* notional API-equivalent value (subscription billing) — NOT cash paid"
)


def _safe_json(obj) -> str:
    """JSON safe to embed in a <script> block: escapes the `</` sequence, HTML-comment openers, and
    the U+2028/U+2029 line separators so a value can never break out of the script element (XSS guard)."""
    return (
        json.dumps(obj, default=str)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _money(v) -> str:
    """`$X.XX` for a numeric value, else `n/a` — never crashes on a malformed cost field (Codex #267).
    Returns PLAIN TEXT (no HTML); `_table` escapes cells, so callers must not pre-escape."""
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _pct(v) -> str:
    """`X.X%` for a numeric fraction, else `n/a` — crash-safe (Codex #267)."""
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fnum(v) -> float:
    """Numeric value or 0.0 — crash-safe coercion for chart/trend math (Codex #267)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# Cost charts plot API-EQUIVALENT value; subscription is notional (not cash) — labeled in the chart
# title since a per-bar `*` isn't possible on a canvas (Codex #267, §6).
_COST_AXIS_TITLE = "API-equivalent $ (subscription = notional, not cash)"


def _fmt_cost(grp: dict) -> str:
    """A billing-aware cost cell (PLAIN TEXT). subscription → `$X *` (notional); mixed → each bucket
    broken out with the subscription bucket ALSO marked `*`; metered → `$X`. Crash-safe via _money."""
    if not isinstance(grp, dict):
        return "n/a"
    bt = grp.get("billing_type")
    if bt == "mixed":
        parts = ", ".join(
            f"{b}: {_money(v)}" + (" *" if b == "subscription" else "")
            for b, v in (grp.get("cost_by_billing") or {}).items()
        )
        return f"mixed ({parts})"
    c = grp.get("cost_usd")
    if not isinstance(c, (int, float)):
        return "n/a"
    return _money(c) + (" *" if bt == "subscription" else "")


def _period_key(ts, period: str) -> str | None:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if period == "month":
        return dt.strftime("%Y-%m")
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def trends(records: list, *, period: str = "week") -> dict:
    """Time-bucketed series from raw records (the aggregate summary has no time axis): per project per
    bucket → cost (by billing), cache_read %. Used by the $/PR and cache-efficiency trend charts."""
    out: dict = {}
    for r in records or []:
        bucket = _period_key(r.get("ts"), period)
        if bucket is None:
            continue
        proj = r.get("project") or "unknown"
        cell = out.setdefault(proj, {}).setdefault(
            bucket, {"cost": 0.0, "input": 0, "cache_read": 0}
        )
        cell["cost"] += _fnum(r.get("cost_usd"))
        cell["input"] += int(_fnum(r.get("input")))
        cell["cache_read"] += int(_fnum(r.get("cache_read")))
    for proj, buckets in out.items():
        for b, c in buckets.items():
            denom = c["input"] + c["cache_read"]
            c["cache_pct"] = round(c["cache_read"] / denom, 4) if denom else 0.0
            c["cost"] = round(c["cost"], 6)
    return out


def _render_recommendations(agg: dict, records: list | None) -> str:
    """Render the Recommendations section HTML.

    Imports usage_recommend lazily (same pattern as _dim_rows imports usage_aggregator) to
    avoid circular deps. Each recommendation finding is rendered as an <li> with finding,
    impact, and action. estimated_impact is pre-formatted with the correct billing framing
    so this renderer never branches on billing_type.
    """
    from importlib import import_module

    rec_mod = import_module("usage_recommend")
    recs = rec_mod.recommend(agg, records or [])
    if not recs:
        return '<p class="nodata">No recommendations — data looks well-optimized.</p>'
    parts = []
    for r in recs:
        impact = (
            r.get("estimated_impact")
            or "impact not computable (mixed billing or insufficient data)"
        )
        proj_label = f" — {html.escape(str(r['project']))}" if r.get("project") else ""
        parts.append(
            f"<li><strong>{html.escape(r['type'])}</strong>"
            f"{proj_label}: "
            f"{html.escape(r['finding'])} "
            f"<em>Impact: {html.escape(impact)}</em> "
            f"<strong>Action:</strong> {html.escape(r['action'])}</li>"
        )
    return "<ul>" + "".join(parts) + "</ul>"


def _table(headers: list, rows: list) -> str:
    """Render a table. EVERY cell + header is html.escaped here (single, consistent escaping layer,
    Codex #267) — callers pass RAW values (incl. _fmt_cost plain text); no caller pre-escaping."""
    if not rows:
        return '<p class="nodata">no data</p>'
    th = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def render_html(
    agg: dict,
    *,
    records: list | None = None,
    period: str = "week",
    title: str = "Fleet Usage Report",
) -> str:
    agg = agg or {}
    tr = trends(records or [], period=period)
    totals = agg.get("totals") or {}
    has_subscription = "subscription" in json.dumps(agg)

    # Section 1: cost by project (table) — $/PR trend chart fed by `tr`. _table escapes cells (raw in).
    proj_rows = [[p, _fmt_cost(_proj_group(agg, p))] for p in _projects(agg)]
    s1 = (
        f"<h2 id='cost_by_project'>{SECTIONS[0][1]}</h2>"
        + _table(["Project", "Cost"], proj_rows)
        + "<canvas id='c_pr_trend'></canvas>"
    )
    # Section 2: model mix
    mm_rows = [
        [p, m, _fmt_cost(g)]
        for p, models in (agg.get("model_mix") or {}).items()
        for m, g in models.items()
    ]
    s2 = f"<h2 id='model_mix'>{SECTIONS[1][1]}</h2>" + _table(
        ["Project", "Model", "Cost"], mm_rows
    )
    # Section 3: cache efficiency (table + trend chart). _pct/_money are crash-safe on malformed data.
    cache_rows = [
        [
            p,
            _pct(c.get("cache_pct")),
            (
                "n/a"
                if c.get("cache_saved_usd") is None
                else _money(c.get("cache_saved_usd"))
            ),
        ]
        for p, c in (agg.get("cache_by_project") or {}).items()
    ]
    s3 = (
        f"<h2 id='cache'>{SECTIONS[2][1]}</h2>"
        + _table(["Project", "cache %", "$ saved"], cache_rows)
        + "<canvas id='c_cache_trend'></canvas>"
    )
    # Section 4: by account / by computer
    s4 = (
        f"<h2 id='by_account'>{SECTIONS[3][1]}</h2>"
        + "<h3>By account</h3>"
        + _table(["Account", "Cost"], _dim_rows(records, "account"))
        + "<h3>By inference host</h3>"
        + _table(["Host", "Cost"], _dim_rows(records, "inference_host"))
        + "<h3>By work host</h3>"
        + _table(["Host", "Cost"], _dim_rows(records, "work_host"))
    )
    # Section 5: cost by tier (raw cells; _table escapes)
    tier_rows = [[t, _fmt_cost(g)] for t, g in (agg.get("by_tier") or {}).items()]
    s5 = (
        f"<h2 id='by_tier'>{SECTIONS[4][1]}</h2>"
        + _table(["Tier", "Cost"], tier_rows)
        + "<canvas id='c_tier'></canvas>"
    )
    # Section 6: concurrency
    conc_rows = [
        [h, c.get("peak_concurrent_sessions", 0), c.get("burn_rate_usd_per_hour")]
        for h, c in (agg.get("concurrency") or {}).items()
    ]
    s6 = (
        f"<h2 id='concurrency'>{SECTIONS[5][1]}</h2>"
        + _table(["Host", "peak concurrent", "burn $/hr"], conc_rows)
        + "<canvas id='c_conc'></canvas>"
    )
    # Section 7: right-sizing recommendations (usage_recommend loaded lazily)
    s7 = f"<h2 id='recommendations'>{SECTIONS[6][1]}</h2>" + _render_recommendations(
        agg, records
    )

    footnote = (
        f"<p class='footnote'>{_NOTIONAL_FOOTNOTE}</p>" if has_subscription else ""
    )
    data_blob = _safe_json(
        {
            "trends": tr,
            "by_tier": agg.get("by_tier") or {},
            "concurrency": agg.get("concurrency") or {},
        }
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<script src="{CHARTJS_CDN}"></script>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px}}
table{{border-collapse:collapse;margin:.5rem 0}}th,td{{border:1px solid #ccc;padding:.3rem .6rem}}
.nodata{{color:#999;font-style:italic}}.footnote{{color:#666;font-size:.85rem;margin-top:2rem}}
.callout{{background:#f5f7ff;padding:.6rem;border-left:3px solid #36c}}canvas{{max-height:320px}}</style>
</head><body>
<h1>{html.escape(title)}</h1>
<p>Total: {html.escape(_fmt_cost(totals))} &middot; {html.escape(str(totals.get("records", 0)))} records</p>
{s1}{s2}{s3}{s4}{s5}{s6}{s7}
{footnote}
<!-- Chart labels are data-derived strings, but Chart.js renders them on the CANVAS as text (no
     innerHTML / DOM-injection path; no HTML-tooltip plugin is used), and the embedded blob is
     breakout-escaped by _safe_json — so a malicious project/host/tier name cannot execute (Codex #267 B2). -->
<script>const D=JSON.parse({json.dumps(data_blob)});
const COST_T={json.dumps(_COST_AXIS_TITLE)};
function titleOpt(t){{return {{plugins:{{title:{{display:true,text:t}}}}}};}}
function line(id,series,title){{const el=document.getElementById(id);if(!el)return;
 const labels=[...new Set([].concat(...Object.values(series).map(b=>Object.keys(b))))].sort();
 const ds=Object.entries(series).map(([k,b])=>({{label:k,data:labels.map(l=>(b[l]||{{}}).cost||0)}}));
 if(ds.length)new Chart(el,{{type:'line',data:{{labels,datasets:ds}},options:titleOpt(title)}});}}
try{{line('c_pr_trend',D.trends,COST_T);
 const ct={{}};for(const[p,b]of Object.entries(D.trends)){{ct[p]={{}};for(const[k,v]of Object.entries(b))ct[p][k]={{cost:v.cache_pct}};}}
 line('c_cache_trend',ct,'cache read %');
 const te=document.getElementById('c_tier');if(te){{const t=D.by_tier;new Chart(te,{{type:'bar',
  data:{{labels:Object.keys(t),datasets:[{{label:'cost',data:Object.values(t).map(g=>g.cost_usd||0)}}]}},options:titleOpt(COST_T)}});}}
 const ce=document.getElementById('c_conc');if(ce){{const c=D.concurrency;new Chart(ce,{{type:'bar',
  data:{{labels:Object.keys(c),datasets:[{{label:'peak concurrent',data:Object.values(c).map(h=>h.peak_concurrent_sessions||0)}}]}},options:titleOpt('peak concurrent sessions')}});}}
}}catch(e){{console.error(e);}}</script>
</body></html>"""


def _projects(agg: dict) -> list:
    s = set((agg.get("model_mix") or {})) | set((agg.get("cache_by_project") or {}))
    return sorted(str(p) for p in s)


def _proj_group(agg: dict, project: str) -> dict:
    return (agg.get("cache_by_project") or {}).get(project, {})


def _dim_rows(records: list | None, field: str) -> list:
    from collections import defaultdict

    groups = defaultdict(list)
    for r in records or []:
        groups[r.get(field)].append(r)
    from importlib import import_module

    agg_mod = import_module("usage_aggregator")
    rows = []
    for key, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        rows.append(
            [key, _fmt_cost(agg_mod._cost_group(rs))]
        )  # raw; _table escapes cells
    return rows


def write_report(
    agg: dict, out_path, *, records: list | None = None, period: str = "week"
) -> str:
    from pathlib import Path

    html_str = render_html(agg, records=records, period=period)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html_str, encoding="utf-8")
    return str(p)
