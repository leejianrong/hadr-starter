"""Deterministic HTML renderer for the morning sitrep (Shape A, part A6).

Pure: takes a Report, returns an HTML string — no model, no clock of its own (the
Report carries all times), so a quiet morning renders byte-identically except for
the timestamps it is handed. Fixed four-section anatomy (CONTEXT / ADR-0003).
"""
from __future__ import annotations

import html
from datetime import datetime

from .model import (
    GLIDE_HAZARD,
    SGT,
    Cluster,
    FeedHealth,
    GdacsEvent,
    Quake,
    Report,
    ReportItem,
    Retraction,
    ScanSummary,
)

_HAZARD_LABEL = {
    "EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood",
    "WF": "Wildfire", "VO": "Volcano", "DR": "Drought", "TS": "Tsunami",
}

_ALERT_COLOURS = {
    "red": "#e04b3a",
    "orange": "#f0872e",
    "yellow": "#e8c14a",
    "green": "#35c46b",
}
# Severity rank -> colour for the activity chart (0 none/green ... 3 red).
_RANK_COLOURS = {0: "#35c46b", 1: "#e8c14a", 2: "#f0872e", 3: "#e04b3a"}


def _sgt(dt: datetime) -> str:
    return dt.astimezone(SGT).strftime("%Y-%m-%d %H:%M SGT")


def _age(as_of: datetime, now: datetime) -> str:
    secs = (now - as_of).total_seconds()
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _chip(alert: str | None) -> str:
    if alert:
        colour = _ALERT_COLOURS.get(alert, "#7f8c8d")
        return f'<span class="chip" style="background:{colour}">{alert.upper()}</span>'
    # PAGER did not run — a neutral marker, never dressed up as a severity colour.
    return '<span class="chip chip-none">NO PAGER</span>'


def _where(q: Quake) -> str:
    if q.iso3:
        return html.escape(f"{q.place} [{', '.join(q.iso3)}]")
    tag = "offshore" if q.is_offshore else q.place
    marker = ' <span class="muted">(offshore)</span>' if q.is_offshore else ""
    return html.escape(q.place or tag) + marker


def _eq_where(item: ReportItem) -> str:
    """Where-label for an earthquake line. Our onshore test uses coarse (110m)
    country polygons, so a genuinely-onshore quake near a coast can read as
    offshore; if a merged GDACS record supplies the country, prefer it (attributed)
    rather than a bare '(offshore)'."""
    q = item.eq.mainshock
    if not q.iso3 and item.gdacs is not None and item.gdacs.iso3:
        return (html.escape(f"{q.place} [{', '.join(item.gdacs.iso3)}]")
                + ' <span class="muted">(country via GDACS)</span>')
    return _where(q)


def _mag(q: Quake) -> str:
    if q.mag is None:
        return "M?"
    mt = f" {html.escape(q.mag_type)}" if q.mag_type else ""
    return f"M{q.mag:.1f}<span class='muted'>{mt}</span>"


def _sequence(c: Cluster) -> str:
    la = c.largest_aftershock
    if c.is_swarm:
        largest = f", largest M{la.mag:.1f}" if la and la.mag is not None else ""
        return f'<span class="muted"> — swarm, no dominant event ({c.count} events{largest})</span>'
    if la is not None:
        largest = f", largest M{la.mag:.1f}" if la.mag is not None else ""
        return f'<span class="muted"> + {len(c.aftershocks)} aftershocks{largest}</span>'
    return ""


def _flag(change: str | None, reason: str) -> str:
    if change == "NEW":
        return '<span class="flag flag-new">NEW</span>'
    if change == "REVISED":
        title = f' title="{html.escape(reason)}"' if reason else ""
        arrow = " ↑" if "escalated" in reason else ""
        return f'<span class="flag flag-rev"{title}>REVISED{arrow}</span>'
    return ""


def _hazard(kind: str) -> str:
    return _HAZARD_LABEL.get(kind, kind)


def _gdacs_where(g: GdacsEvent) -> str:
    if g.iso3:
        return html.escape(f"{g.name or _hazard(g.eventtype)} [{', '.join(g.iso3)}]")
    return html.escape(g.name or g.country or _hazard(g.eventtype))


def _gdacs_severity(g: GdacsEvent) -> str:
    """Per-hazard descriptor — value+unit, never compared across types (ADR-0002)."""
    txt = g.severity_text or (
        f"{g.severity_value:g} {g.severity_unit}".strip()
        if g.severity_value is not None else ""
    )
    return html.escape(txt)


def _provenance(item: ReportItem) -> str:
    """Sources + the confidence/independence note (ADR-0001 / ADR-0002 / ADR-0008)."""
    bits: list[str] = []
    if item.sources:
        bits.append("sources: " + html.escape(" + ".join(item.sources)))
    # A merged earthquake is one NEIC reading arriving from two feeds — say so, so a
    # reader never reads feed-agreement as corroboration (and it's never summed).
    if item.eq is not None and item.gdacs is not None and not item.independent:
        bits.append("same NEIC reading — not independent corroboration, not double-counted")
    if item.confidence == "medium":
        bits.append("likely the same event (medium confidence)")
    lines = ""
    if bits:
        lines += f'<span class="prov">{" · ".join(bits)}</span>'
    # ReliefWeb stacked onto a sudden-onset line: an INDEPENDENT curated confirmation
    # (unlike EQ↔NEIC). Attributed, shown alongside — figures are never summed across
    # feeds (ADR-0008). On RSS we stack the confirmation + GLIDE, not casualty numbers.
    if item.reliefweb is not None:
        d = item.reliefweb
        curated = f" (curated {_sgt(d.pub_date)})" if d.pub_date else ""
        glide = f" · GLIDE {html.escape(d.glide)}" if d.glide else ""
        lines += (f'<span class="prov stack">＋ ReliefWeb{curated}: '
                  f'{html.escape(d.title)}{glide} — independent confirmation; '
                  f'figures attributed, never summed</span>')
    for note in item.cross_links:
        lines += f'<span class="prov xlink">↔ {html.escape(note)}</span>'
    return lines


def _reliefweb_line(item: ReportItem, now: datetime) -> str:
    """A slow-onset / curated line (U3) — window-exempt. ReliefWeb carries no alert
    colour (severity there is 'a human made a page'), so the chip states the floor."""
    d = item.reliefweb
    hazard = GLIDE_HAZARD.get(d.hazard_code, d.hazard_code) if d.hazard_code else ""
    where = f" [{', '.join(d.iso3)}]" if d.iso3 else ""
    curated = f"curated {_sgt(d.pub_date)} ({_age(d.pub_date, now)})" if d.pub_date else "curated —"
    glide = f' · GLIDE {html.escape(d.glide)}' if d.glide else ""
    hz = f'<span class="muted">{hazard}</span> · ' if hazard else ""
    summary = ""
    if d.summary:
        snippet = d.summary if len(d.summary) <= 220 else d.summary[:217].rstrip() + "…"
        summary = f'<span class="prov">{html.escape(snippet)}</span>'
    reason = ""
    if item.change_reason:
        reason = f' <span class="muted">— {html.escape(item.change_reason)}</span>'
    url = html.escape(d.url)
    return (
        '<li class="event">'
        f'{_flag(item.change, item.change_reason)}'
        '<span class="chip chip-rw">REACHED RELIEFWEB</span>'
        f'<span class="what">{html.escape(d.title)}{html.escape(where)}</span>'
        f'<span class="meta">{hz}{curated}{glide}{reason}</span>'
        f'{summary}'
        f'<span class="prov"><a class="url" href="{url}">{url}</a></span>'
        "</li>"
    )


def _eq_line(item: ReportItem, now: datetime) -> str:
    c = item.eq
    q = c.mainshock
    # Severity is the max colour across the merged sources; show the loudest chip.
    reason = ""
    if item.change_reason:
        reason = f' <span class="muted">— {html.escape(item.change_reason)}</span>'
    return (
        '<li class="event">'
        f"{_flag(item.change, item.change_reason)}{_chip(item.alert)}"
        f'<span class="what">{_eq_where(item)}</span>'
        f'<span class="meta">{_mag(q)}{_sequence(c)} · depth {q.depth_km:.0f} km'
        f' · {_sgt(q.time)} ({_age(q.time, now)}){reason}</span>'
        f"{_provenance(item)}"
        "</li>"
    )


def _gdacs_line(item: ReportItem, now: datetime) -> str:
    g = item.gdacs
    when = f" · {_sgt(g.from_date)} ({_age(g.from_date, now)})" if g.from_date else ""
    glide = f' · GLIDE {html.escape(g.glide)}' if g.glide else ""
    reason = ""
    if item.change_reason:
        reason = f' <span class="muted">— {html.escape(item.change_reason)}</span>'
    return (
        '<li class="event">'
        f"{_flag(item.change, item.change_reason)}{_chip(item.alert)}"
        f'<span class="what">{_hazard(g.eventtype)}: {_gdacs_where(g)}</span>'
        f'<span class="meta">{_gdacs_severity(g)}{when}{glide}{reason}</span>'
        f"{_provenance(item)}"
        "</li>"
    )


def _item_line(item: ReportItem, now: datetime) -> str:
    return _eq_line(item, now) if item.eq is not None else _gdacs_line(item, now)


def _retraction_line(r: Retraction) -> str:
    mag = f" M{r.last_mag:.1f}" if r.last_mag is not None else ""
    colour = f" ({r.last_alert})" if r.last_alert else ""
    return (
        '<li class="corr"><span class="flag flag-corr">CORRECTED</span>'
        f"{html.escape(r.place)}{mag}{colour} — {html.escape(r.reason)}</li>"
    )


def _feed_line(f: FeedHealth, now: datetime) -> str:
    if f.ok:
        status = '<span class="ok">● up</span>'
        asof = f"as of {_sgt(f.as_of)} ({_age(f.as_of, now)})" if f.as_of else "as of —"
    else:
        status = '<span class="down">● UNREACHABLE</span>'
        asof = f"last good {_sgt(f.as_of)}" if f.as_of else "no data"
    note = f' — {html.escape(f.note)}' if f.note else ""
    return (
        f'<li>{status} <strong>{html.escape(f.name)}</strong> · {asof}{note}'
        f'<br><span class="url">{html.escape(f.url)}</span></li>'
    )


def _items(report: Report) -> list[ReportItem]:
    """Render list. Falls back to wrapping bare EQ clusters so a Report built the
    V1–V3 way (clusters only, no join) still renders."""
    if report.items:
        return report.items
    return [
        ReportItem(kind="EQ", eq=c, sources=["USGS"],
                   change=c.change, change_reason=c.change_reason)
        for c in report.clusters
    ]


def _scan_line(scan: ScanSummary) -> str:
    """Honest 'scanned vs shown' summary. Never hides the filter (ADR-0004)."""
    parts = []
    if scan.usgs_scanned:
        parts.append(f"{scan.usgs_scanned} USGS")
    if scan.gdacs_scanned:
        parts.append(f"{scan.gdacs_scanned} GDACS")
    if scan.reliefweb_scanned:
        parts.append(f"{scan.reliefweb_scanned} ReliefWeb")
    feeds = " + ".join(parts) if parts else "0"
    return (
        f'<p class="scan">Scanned <b>{scan.total_scanned}</b> records ({html.escape(feeds)}). '
        f'Cleared the bar: <b>{scan.shown_today}</b> in the last 24h, '
        f'<b>{scan.shown_week}</b> earlier this week, '
        f'<b>{scan.ongoing}</b> ongoing.</p>'
    )


def _activity_chart(scan: ScanSummary) -> str:
    """Deterministic inline-SVG stacked bar chart: significant events per SGT day
    over the last 7 days, coloured by severity (green/yellow/orange/red)."""
    days = scan.activity
    if not days:
        return ""
    maxt = max((d.total for d in days), default=0) or 1
    w, h, gap = 560.0, 104.0, 12.0
    n = len(days)
    bw = (w - gap * (n - 1)) / n
    barmax = h - 26.0
    base = h - 20.0
    segs = ""
    for i, d in enumerate(days):
        x = i * (bw + gap)
        top = base
        for rank in (0, 1, 2, 3):     # stack green (bottom) up to red (top)
            c = d.counts.get(rank, 0)
            if not c:
                continue
            bh = c / maxt * barmax
            top -= bh
            segs += (f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                     f'fill="{_RANK_COLOURS[rank]}" rx="1.5"/>')
        if d.total:
            segs += (f'<text x="{x + bw / 2:.1f}" y="{top - 4:.1f}" text-anchor="middle" '
                     f'class="axn">{d.total}</text>')
        else:
            segs += (f'<line x1="{x:.1f}" y1="{base:.1f}" x2="{x + bw:.1f}" y2="{base:.1f}" '
                     f'class="axbase"/>')
        segs += (f'<text x="{x + bw / 2:.1f}" y="{h - 4:.1f}" text-anchor="middle" '
                 f'class="axl">{html.escape(d.label)}</text>')
    return (
        '<figure class="activity">'
        '<figcaption>Significant events per day, last 7 days, by severity</figcaption>'
        f'<svg viewBox="0 0 {w:.0f} {h:.0f}" role="img" '
        'aria-label="Significant events per day over the last seven days, by severity">'
        f'{segs}</svg></figure>'
    )


def _section(title: str, items: list[ReportItem], now: datetime, empty: str,
             line=_item_line) -> str:
    if items:
        body = "\n".join(line(it, now) for it in items)
        body = f'<ul class="events">\n{body}\n</ul>'
    else:
        body = f'<p class="nothing">{empty}</p>'
    return f"<h2>{html.escape(title)}</h2>\n{body}"


def render(report: Report) -> str:
    now = report.publish_utc
    window = f"last 24h ending {_sgt(report.window_end_utc)}"
    render_items = _items(report)

    if render_items:
        events = "\n".join(_item_line(it, now) for it in render_items)
        sudden = f'<ul class="events">\n{events}\n</ul>'
    else:
        sudden = ('<p class="nothing">No new sudden-onset events crossed threshold '
                  f'in the {html.escape(window)}.</p>')

    corrections = ""
    if report.retractions:
        lines = "\n".join(_retraction_line(r) for r in report.retractions)
        corrections = f'<ul class="events">\n{lines}\n</ul>'

    recent = _section(
        "Past 7 days", report.recent, now,
        "Nothing else above threshold in the past 7 days.")

    ongoing = _section(
        "Slow-onset / ongoing", report.ongoing, now,
        "No curated slow-onset crises in view (ReliefWeb active; nothing curated, "
        "or feed not fetched this run).", line=_reliefweb_line)

    scan_line = _scan_line(report.scan) if report.scan else ""
    chart = _activity_chart(report.scan) if report.scan else ""

    n_changes = (sum(1 for it in render_items if it.change)
                 + sum(1 for it in report.ongoing if it.change)
                 + len(report.retractions))
    heartbeat = (f"{n_changes} update(s) since last run" if report.is_loud
                 else "no changes since last run")

    feeds = "\n".join(_feed_line(f, now) for f in report.feeds)
    sub = (f"Published {_sgt(report.publish_utc)} &middot; "
           f"window: {html.escape(window)} &middot; {heartbeat}")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HADR situation report &middot; {_sgt(report.publish_utc)}</title>
<style>
  :root {{
    --ink:#0b0f14; --panel:#121820; --line:rgba(222,232,242,.10);
    --paper:#e8eef4; --muted:#8a97a5; --faint:#5d6875; --signal:#79b8d1;
    --font-mono:ui-monospace,"SF Mono","Cascadia Code","JetBrains Mono",Menlo,Consolas,monospace;
    --font-sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
  }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:var(--font-sans); font-size:15px; line-height:1.6; color:var(--paper);
         background:var(--ink); max-width:860px; margin:0 auto; padding:2.2rem 1.1rem 3rem; }}
  a {{ color:var(--signal); }}
  h1 {{ font-family:var(--font-mono); font-size:1.5rem; font-weight:700; letter-spacing:-.01em;
        margin:0 0 .3rem; }}
  h2 {{ font-family:var(--font-mono); font-size:.82rem; text-transform:uppercase;
        letter-spacing:.14em; color:var(--muted); border-bottom:1px solid var(--line);
        padding-bottom:.35rem; margin:2.2rem 0 .8rem; }}
  .sub {{ font-family:var(--font-mono); color:var(--muted); font-size:.8rem; margin:0 0 1rem; }}
  .banner {{ background:rgba(240,135,46,.08); border-left:3px solid #f0872e; padding:.6rem .85rem;
             margin:1rem 0; font-size:.9rem; color:#f0c9a3; border-radius:0 4px 4px 0; }}
  .scan {{ font-family:var(--font-mono); font-size:.82rem; color:var(--muted);
           margin:.4rem 0 1.2rem; }}
  .scan b {{ color:var(--paper); font-variant-numeric:tabular-nums; }}
  .activity {{ margin:0 0 1.6rem; }}
  .activity figcaption {{ font-family:var(--font-mono); font-size:.68rem; letter-spacing:.08em;
             text-transform:uppercase; color:var(--faint); margin-bottom:.4rem; }}
  .activity svg {{ width:100%; height:auto; max-width:560px; display:block; }}
  .axl {{ fill:var(--faint); font-family:var(--font-mono); font-size:11px; }}
  .axn {{ fill:var(--muted); font-family:var(--font-mono); font-size:11px; font-weight:700; }}
  .axbase {{ stroke:var(--line); stroke-width:1.5; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  .events li {{ padding:.6rem 0; border-bottom:1px solid var(--line); }}
  .chip {{ display:inline-block; color:#08121a; font-size:.68rem; font-weight:700;
           font-family:var(--font-mono); padding:.12rem .45rem; border-radius:3px;
           margin-right:.5rem; vertical-align:1px; letter-spacing:.04em; }}
  .chip-none {{ background:#3a4552; color:var(--muted); }}
  .flag {{ display:inline-block; font-family:var(--font-mono); font-size:.6rem; font-weight:700;
           padding:.1rem .38rem; border-radius:3px; margin-right:.4rem; letter-spacing:.06em;
           color:#08121a; }}
  .flag-new {{ background:var(--signal); }}
  .flag-rev {{ background:#c58be0; }}
  .flag-corr {{ background:#e04b3a; color:#fff; }}
  .corr {{ padding:.5rem 0; border-bottom:1px solid var(--line); }}
  .narrative {{ background:rgba(121,184,209,.07); border-left:3px solid var(--signal);
                padding:.6rem 1rem; margin:1.2rem 0; border-radius:0 4px 4px 0; }}
  .narrative h2 {{ border:0; margin:.1rem 0 .35rem; color:var(--signal); }}
  .narrative p {{ margin:.35rem 0; }}
  .what {{ font-weight:600; }}
  .meta {{ display:block; font-family:var(--font-mono); color:var(--muted); font-size:.8rem;
           margin-top:.2rem; }}
  .prov {{ display:block; color:var(--faint); font-size:.78rem; margin-top:.12rem; }}
  .prov a.url {{ color:var(--faint); }}
  .xlink {{ color:#c58be0; }}
  .stack {{ color:#35c46b; }}
  .chip-rw {{ background:#35c46b; color:#08121a; }}
  .muted {{ color:var(--faint); }}
  .nothing {{ color:var(--muted); font-style:italic; }}
  .ok {{ color:#35c46b; }} .down {{ color:#e04b3a; font-weight:700; }}
  .url {{ color:var(--faint); font-size:.74rem; word-break:break-all; }}
  footer {{ color:var(--faint); font-size:.76rem; font-family:var(--font-mono); margin-top:2.4rem;
            border-top:1px solid var(--line); padding-top:1rem; line-height:1.8; }}
  footer a {{ color:var(--muted); }}
</style>
</head>
<body>
<h1>HADR situation report</h1>
<p class="sub">{sub}</p>
<div class="banner">{html.escape(report.coverage_note)}</div>
<!--NARRATIVE-->
{scan_line}
{chart}
<h2>Sudden-onset &middot; {html.escape(window)}</h2>
{sudden}
{corrections}

{recent}

{ongoing}

<h2>Feed health</h2>
<ul class="feeds">
{feeds}
</ul>

<footer>
Severity is impact (PAGER / GDACS), shown as a colour; magnitude is a descriptor only.
Automatic solutions are preliminary and may be revised or withdrawn. Generated
deterministically; no figures are summed across sources.
<br><a href="./index.html">About HADR Monitor</a> &middot;
<a href="https://github.com/leejianrong/hadr-starter">Source</a>
</footer>
</body>
</html>
"""
