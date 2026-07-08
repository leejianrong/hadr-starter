"""Common data model for the HADR monitor.

Deterministic value objects shared across the pipeline. No I/O, no model calls.
`event_time` is nullable in spirit (slow-onset events have none) — for the USGS
earthquake slice every event has a time, but the model keeps the shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Singapore is UTC+8, no DST — the report's publish clock (ADR-0003).
SGT = timezone(timedelta(hours=8), name="SGT")

# PAGER/GDACS alert colours, ranked. None and "green" both rank 0: PAGER either
# did not run (the majority — USGS #2) or rated the event low-impact. The colour
# is the MAX of independent fatalities-OR-economic ladders (ADR-0002), never
# "many dead".
ALERT_RANK = {None: 0, "green": 0, "yellow": 1, "orange": 2, "red": 3}


def from_ms(ms: int) -> datetime:
    """USGS times are epoch milliseconds UTC (13 digits) — attach UTC (USGS #4)."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


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

    @property
    def count(self) -> int:
        return 1 + len(self.aftershocks)

    @property
    def largest_aftershock(self) -> Quake | None:
        if not self.aftershocks:
            return None
        return max(self.aftershocks, key=lambda q: (q.mag or 0.0))


@dataclass
class FeedHealth:
    """One feed's liveness line — always shown, degrade loud (ADR-0007)."""

    name: str
    url: str                     # the FINAL url actually fetched (CLAUDE.md #2)
    ok: bool
    as_of: datetime | None       # UTC of the data (feed 'generated' or fetch time)
    note: str = ""


@dataclass
class Report:
    """Everything the renderer needs for one morning page."""

    publish_utc: datetime
    window_start_utc: datetime
    window_end_utc: datetime
    clusters: list[Cluster]      # thresholded + ranked, most severe first
    feeds: list[FeedHealth]
    coverage_note: str
