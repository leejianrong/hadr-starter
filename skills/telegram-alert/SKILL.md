---
name: telegram-alert
description: Rewrite the wording of a HADR Telegram alert from a deterministic brief.json and the already-composed message.txt, into message.refined.txt. Invoked by the ~hourly alert workflow only when the deterministic loud-gate has decided to fire; it decides nothing and invents no number.
---

# /telegram-alert — refine the alert wording

A deterministic step has already decided **what** to send and written a correct,
honest message. Your only job is to make that message read a little more like a
person wrote it — same facts, same figures, same severity, same link. You write
**prose only**. You do **not** decide whether to alert, compute severity, or
introduce any number, place, or event not already present (ADR-0002 / ADR-0005).
A deterministic step re-checks your output and discards it if it added a figure.

**Model:** Haiku 4.5 (`claude-haiku-4-5-20251001`) — short, factual prose; the
cheap fast model is the right tool. Do not escalate.

## Input (in the working directory)

- `alert_out/message.txt` — the deterministic message actually built. This is the
  source of truth and the fallback; if you do nothing useful, it is what gets sent.
- `alert_out/brief.json` — the honest facts, one entry per event:

```json
{
  "count": 1,
  "publish_utc": "…",
  "events": [
    {"title": "Earthquake — M6.5", "place": "10 km W of Town",
     "iso3": ["CRI"], "impact": "Impact: Red", "sources": ["USGS"],
     "when": "…", "link": "https://earthquake.usgs.gov/…"}
  ]
}
```

## Output

Write **`alert_out/message.refined.txt`** — the refined message, ready to send as a
Telegram HTML message. Keep it compact (it goes to a phone). Preserve the
`<b>…</b>` bolding, the severity emoji (🔴/🟠/⚪), and the `<a href="…">…</a>` link
exactly. Nothing else; no commentary, no code fences.

## Rules

1. **Only facts from the input.** Never introduce a magnitude, count, place, time,
   or event not in `brief.json` / `message.txt`. Do not round or restate figures
   (write the magnitude as given). If you add a number that isn't already there, a
   deterministic check throws your version away and sends the default instead.
2. **Keep the severity honest.** "not yet scored for impact" (⚪) must stay that —
   never imply an impact rating for an unscored event.
3. **Preliminary and attributed.** These are automatic solutions that may be revised
   — phrase them as provisional (e.g. "preliminary").
4. **Keep the link and the structure.** Every event keeps its report link; keep the
   message scannable.
5. **No drama, no false precision.** Calm, factual register. If you can't improve on
   the default, copy it verbatim — that is a valid, good outcome.
