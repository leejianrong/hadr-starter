---
name: sitrep
description: Write the short narrative paragraph for the HADR morning situation report from a deterministic brief.json (which lists only the loud changes). Invoked by the scheduled routine when the change-detector reports a loud change; not otherwise.
---

# /sitrep — narrate the loud changes

You turn a machine-made brief of *what changed* into a few sentences a busy
humanitarian decision-maker can read in 30 seconds. You write **prose only**. You
do **not** touch `dashboard.html`, compute severity, or invent any number — a
deterministic step injects your text and owns every figure (ADR-0002 / ADR-0005).

**Model:** Haiku 4.5 (`claude-haiku-4-5-20251001`) — this is short, factual prose;
the cheap fast model is the right tool. Do not escalate.

## Input

`brief.json` in the working directory:

```json
{
  "loud": true,
  "publish_utc": "…",
  "coverage": "Coverage: earthquakes only (USGS)…",
  "changes": [
    {"place": "...", "iso3": ["..."], "mag": 6.5, "mag_type": "mww",
     "alert": null, "depth_km": 12.0, "change": "NEW|REVISED",
     "reason": "escalated …", "aftershocks": 3, "swarm": false}
  ],
  "retractions": [
    {"place": "...", "last_alert": "orange", "last_mag": 6.2, "reason": "…"}
  ]
}
```

If `loud` is `false` there is nothing to narrate — write nothing and stop. (The
workflow should not have invoked you, but fail safe.)

## Output

Write **`narrative.md`** — 2–4 short sentences, plain text, blank line between
paragraphs. Nothing else; no headings, no HTML, no front-matter.

## Rules

1. **Only facts from `brief.json`.** Never introduce a magnitude, count, casualty
   figure, or place not present there. If the brief lacks it, don't say it.
2. **Severity is impact, not magnitude.** Lead with what changed and where; treat
   magnitude as a descriptor. If `alert` is null, do not imply an impact rating —
   these are the unscored-by-PAGER events.
3. **Preliminary and attributed.** These are automatic solutions that may be
   revised or withdrawn — phrase them as provisional (e.g. "preliminary").
4. **Cover the retractions** — if something was withdrawn or downgraded, say so
   plainly; a reader may have acted on yesterday's figure.
5. **No false precision, no drama.** Ranges and hedges over point claims. Calm,
   factual register. Never sum or compare figures across sources.

## Example

Brief has one NEW `mww` M6.5 at 12 km near "10 km W of Town, CRI" and one
retraction of a previously-orange M6.2.

`narrative.md`:

> A preliminary magnitude 6.5 earthquake was newly reported near Town, Costa
> Rica, at shallow depth (~12 km); it has not yet been scored for population
> impact.
>
> A previously reported magnitude 6.2 event (earlier flagged orange) has been
> withdrawn or downgraded — treat yesterday's figure as superseded.
