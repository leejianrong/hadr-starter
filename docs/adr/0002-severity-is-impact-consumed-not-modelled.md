# ADR-0002 — Severity is impact, consumed from PAGER/GDACS — never modelled

Status: Accepted (2026-07-08)

## Context

A M7 in the deep ocean can be harmless; a M6 shallow under a poor, dense city is
catastrophic. Magnitude is not severity. People who model population exposure ×
vulnerability × coping capacity already publish severity: USGS **PAGER** `alert`
(green/yellow/orange/red) and GDACS **`alertscore`** (0–3). The single most
tempting scope creep (per the grill) is to recompute this ourselves.

## Decision

Rank on **PAGER `alert` / GDACS `alertscore`**, with magnitude as a **descriptor
only**. We **consume** severity judgement; we **never model** exposure or
forecast casualties. Key facts the code and prose must honour:

- The colour is the **max of two independent ladders — fatalities OR economic
  loss**. A rich-country quake can go orange/red on **dollars** with near-zero
  deaths; a poor-country quake goes red on **deaths** with low dollars.
  (Fatalities: yellow ≥1, orange ≥100, red ≥1000. Economic: yellow ≥$1M,
  orange ≥$100M, red ≥$1B.) **Never collapse "red" to "many dead."**
- Both are **probabilistic ranges**, never point estimates. Never publish
  "≈240 deaths"; publish the colour and the range.

## Consequences

- No exposure/fatality model in the codebase. Severity is a lookup + threshold.
- The renderer refuses a bare casualty integer (must carry source + range +
  prelim flag).
- For earthquakes, GDACS `alertscore` and PAGER are **not independent** (GDACS EQ
  is built from USGS/NEIC) — don't treat their agreement as corroboration.

## Alternatives rejected

- **Estimate severity from magnitude + depth + population** — false precision,
  duplicates PAGER worse, and is the exact scope creep the domain expert flagged.
- **Lead with magnitude** — magnitude is the descriptor, not the decision driver.
