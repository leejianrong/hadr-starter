"""ReliefWeb disaster feed adapter — ingestion + normalization (RSS-first).

ReliefWeb is UN OCHA's curated humanitarian service: a "disaster" appears only once
humans decide it matters — the slowest feed (days-latent) but the widest scope
(adds epidemics + conflict) and a free, high-quality severity signal (ADR-0004
branch 3: "reached ReliefWeb"). One record is a *coordination object*, not a
physical event.

Built **RSS-first** (ADR-0008); the API is a drop-in once the `appname` is approved
(see implementation-notes). The RSS traps from `docs/feed-blindspots.md`:

- The RSS feed 403s a default `requests` User-Agent (AWS WAF) — we send a
  browser-like UA (the RSS analog of the API's appname wall).
- GLIDE and countries live in **double-escaped HTML inside `<description>`** — there
  is no dedicated `<glide>`/`<country>` element, and `type` isn't in RSS at all
  (inferred from the GLIDE prefix). ISO3 is taken from the GLIDE **suffix** (a clean
  ISO3) rather than string-matching country names (blindspot #10).
- RSS shows only the latest ~20 items, unpaginated — a burst can be silently
  dropped; only the API backfills. The caller flags this on the page.
- `status` (alert/current/past) and `date.event` are API-only — flagged, not faked.

Casualty figures are deliberately **not** scraped from the prose: numbers are
consumed from structured sources, never modelled or regex'd out of narrative
(ADR-0002). Provenance stacking of real figures lands with the API upgrade.

Live fetch lazy-imports `requests` so parsing stays offline-testable.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

from .geo import Geo
from .model import ReliefWebDisaster, from_rfc822, parse_glide

FEED_URL_RSS = "https://reliefweb.int/disasters/rss.xml"

# The RSS feed rejects a default requests UA (AWS WAF, verified). A browser-like UA
# is required — the RSS analog of the API's appname wall.
_BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_COUNTRY_RE = re.compile(r"Affected country:\s*([^<]+?)\s*<", re.I)
_PARA_RE = re.compile(r"<p>(.*?)</p>", re.S | re.I)


def fetch_rss(url: str = FEED_URL_RSS, timeout: float = 30.0) -> tuple[str, str]:
    """Fetch the disasters RSS. Returns (xml_text, final_url_actually_fetched)."""
    import requests

    resp = requests.get(url, headers={"User-Agent": _BROWSER_UA,
                                      "Accept-Encoding": "gzip"}, timeout=timeout)
    resp.raise_for_status()
    return resp.text, resp.url


def _first_paragraph(description_html: str) -> str:
    """First <p> of the (unescaped) description, as plain text."""
    for m in _PARA_RE.finditer(description_html):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = html.unescape(text).strip()
        if text:
            return text
    return ""


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


def parse_rss(xml_text: str, geo: Geo | None = None) -> list[ReliefWebDisaster]:
    """Normalize the ReliefWeb disasters RSS into ReliefWebDisasters."""
    root = ET.fromstring(xml_text.lstrip("﻿"))
    out: list[ReliefWebDisaster] = []
    for item in root.iter("item"):
        title = _text(item, "title")
        url = _text(item, "link") or _text(item, "guid")
        # ET already un-escapes the XML entities, so description text is HTML.
        desc = _text(item, "description")

        # GLIDE can appear in the description tag or the URL slug — check both.
        parsed = parse_glide(desc) or parse_glide((url or "").upper())
        if parsed:
            code, year, seq, iso3 = parsed
            glide = f"{code}-{year}-{seq}-{iso3}"
            hazard_code, iso3s = code, (iso3,)
        else:
            glide, hazard_code, iso3s = "", "", ()

        country_names = tuple(c.strip() for c in _COUNTRY_RE.findall(desc))

        out.append(
            ReliefWebDisaster(
                title=title,
                url=url,
                glide=glide,
                hazard_code=hazard_code,
                iso3=iso3s,
                country_names=country_names,
                pub_date=from_rfc822(_text(item, "pubDate")),
                summary=_first_paragraph(desc),
            )
        )
    return out


def item_count(xml_text: str) -> int:
    """How many items the RSS carried — for the pagination-limit note (~20 max)."""
    return len(re.findall(r"<item>", xml_text))
