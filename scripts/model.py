"""Common data model for the HADR monitor.

Deterministic value objects shared across the pipeline. No I/O, no model calls.
`event_time` is nullable in spirit (slow-onset events have none) — for the USGS
earthquake slice every event has a time, but the model keeps the shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# Singapore is UTC+8, no DST — the report's publish clock (ADR-0003).
SGT = timezone(timedelta(hours=8), name="SGT")

# PAGER/GDACS alert colours, ranked. None and "green" both rank 0: PAGER either
# did not run (the majority — USGS #2) or rated the event low-impact. The colour
# is the MAX of independent fatalities-OR-economic ladders (ADR-0002), never
# "many dead". GDACS uses the same colours minus yellow (Green/Orange/Red).
ALERT_RANK = {None: 0, "green": 0, "yellow": 1, "orange": 2, "red": 3}


def from_ms(ms: int) -> datetime:
    """USGS times are epoch milliseconds UTC (13 digits) — attach UTC (USGS #4)."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def from_gdacs_naive(s: str | None) -> datetime | None:
    """GDACS JSON dates have NO timezone designator ("2026-07-08T09:50:23") but
    ARE UTC (GDACS blindspot). `fromisoformat` yields a naive value libs then
    treat as local — so attach UTC ourselves."""
    if not s:
        return None
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def from_rfc822(s: str | None) -> datetime | None:
    """GDACS RSS uses RFC-822 GMT ("Wed, 08 Jul 2026 09:50:23 GMT") — a *different*
    format from the JSON feed (two parsers, per the blindspot)."""
    if not s:
        return None
    dt = parsedate_to_datetime(s.strip())
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Quake:
    """One normalized USGS earthquake — a physical event."""

    id: str                      # top-level id; can change (USGS #1) — track by `ids`
    ids: frozenset[str]          # full id set (leading/trailing commas stripped)
    mag: float | None
    mag_type: str | None         # ml/md/mb/mww… NOT comparable across types (USGS)
    place: str
    time: datetime               # UTC
    updated: datetime            # UTC
    depth_km: float              # can be negative or a fixed default (0/10/33)
    lon: float
    lat: float
    alert: str | None            # green/yellow/orange/red or None
    status: str                  # automatic / reviewed
    sig: int | None
    tsunami: int                 # "eligible region", NOT "a tsunami occurred" (USGS)
    felt: int | None
    title: str
    iso3: tuple[str, ...] = ()   # reverse-geocoded; empty = offshore (nullable + list)
    onshore: bool = False

    @property
    def is_offshore(self) -> bool:
        return not self.onshore


@dataclass
class Cluster:
    """A declustered earthquake sequence: one mainshock + its aftershocks."""

    mainshock: Quake
    aftershocks: list[Quake] = field(default_factory=list)
    is_swarm: bool = False       # no dominant mainshock (set by declusterer)
    change: str | None = None    # None (quiet) | "NEW" | "REVISED" (set by change detection)
    change_reason: str = ""      # human note, e.g. "escalated to orange; reviewed"

    @property
    def count(self) -> int:
        return 1 + len(self.aftershocks)

    @property
    def largest_aftershock(self) -> Quake | None:
        if not self.aftershocks:
            return None
        return max(self.aftershocks, key=lambda q: (q.mag or 0.0))


@dataclass(frozen=True)
class GdacsEvent:
    """One normalized GDACS alert — an *automated impact alert*, versioned over the
    event's life (blindspot: not a physical event like USGS). Multi-hazard.

    Severity axis is the alert **colour** (`peak_level`), which is consistent across
    the JSON and RSS feeds. The numeric `peak_score`/`episode_score` are kept but are
    NATIVE to `score_format` — the JSON and RSS `alertscore` fields are NOT
    interchangeable (GDACS blindspot: "roughly swapped conventions"), so never
    compare a raw score across formats; rank on the colour.
    """

    eventtype: str               # EQ / TC / FL / WF / VO / DR
    eventid: int
    episodeid: int | None        # semantics differ by hazard — do not compare across types
    name: str
    glide: str                   # "" when absent (routinely empty — low recall)
    source: str                  # EQ=NEIC, TC=JTWC, FL=GLOFAS, WF=GWIS…
    source_id: str               # embedded upstream id (e.g. the USGS id); "" when absent
    lat: float
    lon: float
    from_date: datetime | None   # UTC attached
    to_date: datetime | None
    date_modified: datetime | None
    peak_level: str              # canonical severity colour: green/orange/red
    episode_level: str           # current-episode colour (can differ from peak)
    peak_score: float            # NATIVE numeric — see score_format
    episode_score: float
    score_format: str            # "json" | "rss" — raw scores not comparable across these
    is_current: bool             # parsed from the string "true"/"false" (blindspot)
    is_temporary: bool
    iso3: tuple[str, ...]        # from affectedcountries[] (a list — spans borders)
    country: str
    severity_value: float | None # per-hazard, unit-heterogeneous — NOT comparable across types
    severity_unit: str           # M / km/h / ha / "" (FL often 0)
    severity_text: str
    report_url: str

    @property
    def key(self) -> str:
        """Stable cross-run key (ADR-0001: GDACS keyed on (eventtype, eventid))."""
        return f"{self.eventtype}{self.eventid}"

    @property
    def alert(self) -> str | None:
        """Colour for the chip/threshold; None only if the feed gave no level."""
        return (self.peak_level or "").lower() or None


@dataclass
class ReportItem:
    """A unified sudden-onset report line — one resolved cross-feed cluster (ADR-0001).

    Holds the contributing domain objects (an EQ `Cluster` and/or a `GdacsEvent`) plus
    the join outcome. A merged earthquake carries BOTH `eq` and `gdacs` on one line,
    with `independent=False` because a GDACS-EQ is *built from* USGS/NEIC — the two are
    one reading, never corroboration (ADR-0002 / blindspot #2).
    """

    kind: str                       # EQ / TC / FL / WF
    eq: Cluster | None = None       # present for earthquakes (aftershock sequence lives here)
    gdacs: GdacsEvent | None = None # present when GDACS contributed
    sources: list[str] = field(default_factory=list)   # provenance, e.g. ["USGS", "GDACS·NEIC"]
    confidence: str | None = None   # set when a cross-feed merge/link was made
    independent: bool = True        # False when two sources are the SAME reading (EQ↔NEIC)
    cross_links: list[str] = field(default_factory=list)  # low-confidence "possibly related"
    change: str | None = None       # NEW / REVISED (from change detection)
    change_reason: str = ""

    @property
    def alert(self) -> str | None:
        ranks = []
        if self.eq is not None:
            ranks.append((ALERT_RANK.get(self.eq.mainshock.alert, 0), self.eq.mainshock.alert))
        if self.gdacs is not None:
            ranks.append((ALERT_RANK.get(self.gdacs.alert, 0), self.gdacs.alert))
        return max(ranks, key=lambda t: t[0])[1] if ranks else None

    @property
    def rank(self) -> int:
        return ALERT_RANK.get(self.alert, 0)

    @property
    def when(self) -> datetime | None:
        if self.eq is not None:
            return self.eq.mainshock.time
        if self.gdacs is not None:
            return self.gdacs.from_date
        return None


@dataclass
class FeedHealth:
    """One feed's liveness line — always shown, degrade loud (ADR-0007)."""

    name: str
    url: str                     # the FINAL url actually fetched (CLAUDE.md #2)
    ok: bool
    as_of: datetime | None       # UTC of the data (feed 'generated' or fetch time)
    note: str = ""


@dataclass
class Retraction:
    """A previously-published event that vanished or fell below threshold.

    Surfaced as an explicit correction (ADR-0009) — never a silent drop.
    """

    place: str
    last_alert: str | None
    last_mag: float | None
    reason: str                  # e.g. "no longer listed" / "fell below threshold"


@dataclass
class Report:
    """Everything the renderer needs for one morning page."""

    publish_utc: datetime
    window_start_utc: datetime
    window_end_utc: datetime
    clusters: list[Cluster]      # EQ clusters (state/change path + the model brief)
    feeds: list[FeedHealth]
    coverage_note: str
    items: list[ReportItem] = field(default_factory=list)  # unified render list, ranked
    retractions: list[Retraction] = field(default_factory=list)
    is_loud: bool = False        # any NEW/REVISED/retraction since last run (ADR-0005)
