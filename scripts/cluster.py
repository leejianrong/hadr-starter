"""Cross-feed cluster resolver — the confidence ladder (A3 / R3).

Turns the "GLIDE-then-tolerance-box" join (ADR-0001) into a deterministic
`confidence(...) -> level` and merges GDACS alerts into the USGS earthquake
clusters, producing the unified `ReportItem` list the renderer shows. From
`docs/planning/SPIKE-cross-feed-confidence.md`:

- The **earthquake identity link is checked first** and is *definitional, not
  probabilistic*: a GDACS-EQ is built from USGS/NEIC (blindspot #2), so a
  `source == "NEIC"` GDACS-EQ whose embedded `sourceid` is one of a USGS event's
  `ids` is the SAME reading — merged to one line, `certain`, and explicitly **not**
  independent corroboration (never double-counted, ADR-0002).
- When no id is embedded, fall back to a **space + time + magnitude tolerance box**
  with two tiers (tight / loose) → high / medium; a partial match → low.
- Report behaviour per level (A3-Q5): `certain`/`high` merge silently; `medium`
  merges with a "likely the same event" label; `low` does **not** merge — the two
  stay separate and are **cross-linked** ("possibly related"). A wrong merge hides
  an event, which the reader forgives least (ADR-0004).

Pure and deterministic (CLAUDE.md #1); constants named at module top.
"""
from __future__ import annotations

from .decluster import haversine_km
from .model import Cluster, GdacsEvent, Quake, ReliefWebDisaster, ReportItem
from .severity import is_mww_family

# --- tolerance box constants (SPIKE-cross-feed-confidence A3-Q3) ---
SPACE_TIGHT_KM = 50.0
SPACE_LOOSE_KM = 100.0
TIME_TIGHT_MIN = 2.0
TIME_LOOSE_MIN = 60.0
MAG_TIGHT_M = 0.3
MAG_LOOSE_M = 1.0

_LEVEL_ORDER = {"low": 1, "medium": 2, "high": 3, "certain": 4}


def eq_identity_link(g: GdacsEvent, q: Quake) -> bool:
    """The definitional GDACS-EQ ⊂ USGS/NEIC link (A3-Q2): a NEIC-sourced GDACS
    earthquake whose embedded upstream id is in this USGS event's `ids` set.

    This is an identity, not a fuzzy guess — and it must never count as independent
    corroboration (the two records are one NEIC reading)."""
    if g.eventtype != "EQ" or g.source != "NEIC" or not g.source_id:
        return False
    sid = g.source_id.strip().lower()
    return sid in {i.lower() for i in q.ids} or sid == (q.id or "").lower()


def _tolerance_level(dist_km: float, dt_min: float, dmag: float | None) -> str | None:
    """Ladder over the space/time/magnitude box. None = not even loosely related."""
    checks_tight = [dist_km <= SPACE_TIGHT_KM, dt_min <= TIME_TIGHT_MIN]
    checks_loose = [dist_km <= SPACE_LOOSE_KM, dt_min <= TIME_LOOSE_MIN]
    if dmag is not None:  # magnitude only enters when comparable (mww-family)
        checks_tight.append(dmag <= MAG_TIGHT_M)
        checks_loose.append(dmag <= MAG_LOOSE_M)
    if all(checks_tight):
        return "high"
    if all(checks_loose):
        return "medium"
    if any(checks_loose):
        return "low"
    return None


def confidence(g: GdacsEvent, c: Cluster) -> str | None:
    """Confidence that GDACS event `g` is the same event as USGS cluster `c`.

    EQ identity link first, then the tolerance box. Returns a ladder label or None.
    Only earthquakes join a USGS cluster — a flood/cyclone/wildfire is a different
    hazard and never merges with an earthquake sequence.
    """
    if g.eventtype != "EQ":
        return None
    # 1) Identity link (checked first) — against any event in the sequence.
    if eq_identity_link(g, c.mainshock) or any(eq_identity_link(g, a) for a in c.aftershocks):
        return "certain"
    # 2) Tolerance box vs the mainshock.
    m = c.mainshock
    dist_km = haversine_km(m.lat, m.lon, g.lat, g.lon)
    dt_min = abs((m.time - g.from_date).total_seconds()) / 60.0 if g.from_date else 1e9
    dmag = None
    if (g.severity_unit or "").upper() == "M" and g.severity_value is not None \
            and m.mag is not None and is_mww_family(m.mag_type):
        dmag = abs(g.severity_value - m.mag)
    return _tolerance_level(dist_km, dt_min, dmag)


def _gdacs_source_label(g: GdacsEvent) -> str:
    return f"GDACS·{g.source}" if g.source else "GDACS"


def _cross_link_note(other: str, level: str) -> str:
    return f"possibly related to {other} (cross-feed confidence: {level})"


def join(clusters: list[Cluster], gdacs_events: list[GdacsEvent]) -> list[ReportItem]:
    """Resolve USGS clusters + GDACS alerts into one ranked-elsewhere ReportItem list.

    - Each GDACS-EQ is matched to its best USGS cluster: certain/high → merge silently;
      medium → merge + "likely the same event"; low → keep separate + cross-link.
    - Non-EQ GDACS hazards (TC/FL/WF) become their own items.
    - Every EQ merge is flagged `independent=False` (same NEIC reading — no corroboration).
    """
    items: list[ReportItem] = [
        ReportItem(kind="EQ", eq=c, sources=["USGS"]) for c in clusters
    ]

    for g in gdacs_events:
        best_item: ReportItem | None = None
        best_level: str | None = None
        if g.eventtype == "EQ":
            for it in items:
                if it.eq is None or it.gdacs is not None:  # one GDACS-EQ per cluster
                    continue
                level = confidence(g, it.eq)
                if level and (best_level is None
                              or _LEVEL_ORDER[level] > _LEVEL_ORDER[best_level]):
                    best_item, best_level = it, level

        if best_item is not None and best_level in ("certain", "high", "medium"):
            # Merge onto the existing USGS earthquake line — one cluster (ADR-0001).
            best_item.gdacs = g
            best_item.confidence = best_level
            best_item.independent = False  # GDACS-EQ is a NEIC reading — not corroboration
            if _gdacs_source_label(g) not in best_item.sources:
                best_item.sources.append(_gdacs_source_label(g))
            continue

        # Standalone GDACS item (non-EQ hazard, or an EQ with no confident USGS match).
        item = ReportItem(kind=g.eventtype, gdacs=g, sources=[_gdacs_source_label(g)])
        if best_item is not None and best_level == "low":
            # Low confidence → never a silent merge; cross-link both directions.
            other_place = best_item.eq.mainshock.place if best_item.eq else "a USGS event"
            item.confidence = "low"
            item.cross_links.append(_cross_link_note(other_place, "low"))
            best_item.cross_links.append(
                _cross_link_note(g.name or f"GDACS {g.eventtype}{g.eventid}", "low")
            )
        items.append(item)

    return items


def attach_reliefweb(items: list[ReportItem], disasters: list[ReliefWebDisaster]
                     ) -> list[ReportItem]:
    """Fold ReliefWeb disasters into the resolved clusters, returning the *ongoing*
    (slow-onset/curated) items — the ones not tied to a sudden-onset line.

    ReliefWeb's join key is **GLIDE** — its actual strength (ADR-0001). A disaster
    whose GLIDE equals a sudden-onset item's GDACS GLIDE stacks onto that line as an
    attributed source (provenance stacking on U2.1). Unlike the EQ↔NEIC link, GDACS
    and ReliefWeb are genuinely independent organisations, so this **does** corroborate
    (`independent` stays True) — but figures are still shown stacked, never summed
    (ADR-0008). Everything else becomes a window-exempt ongoing item; every ReliefWeb
    disaster appears somewhere (the "reached ReliefWeb" floor — ADR-0004 branch 3)."""
    ongoing: list[ReportItem] = []
    for d in disasters:
        stacked = False
        if d.glide:
            for it in items:
                if (it.reliefweb is None and it.gdacs is not None
                        and it.gdacs.glide and it.gdacs.glide == d.glide):
                    it.reliefweb = d
                    if "ReliefWeb" not in it.sources:
                        it.sources.append("ReliefWeb")
                    it.confidence = it.confidence or "certain"  # exact GLIDE match
                    stacked = True
                    break
        if not stacked:
            ongoing.append(
                ReportItem(kind=d.hazard_code or "OT", reliefweb=d, sources=["ReliefWeb"])
            )
    return ongoing
