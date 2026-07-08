# ADR-0001 — The reader-facing unit is a resolved cross-feed cluster

Status: Accepted (2026-07-08)

## Context

The three feeds carry different object types at different atomicity (see
`docs/planning/CONTEXT.md`). A ReliefWeb "disaster" (one GLIDE) can cover a mainshock plus its
whole aftershock sequence — dozens of USGS `id`s and a multi-episode GDACS chain.
"Deduplication" is entity resolution across three ontologies, not row-matching.

## Decision

The unit a reader sees as one line is the **resolved cross-feed cluster** — the
humanitarian situation. A physical rupture is too atomic (floods the report); a
raw GDACS alert is too feed-parochial. Model the cluster as:

- many USGS events (keyed on the **full `ids` set**, comma-delimited with leading/
  trailing commas — strip empties), plus
- one GDACS event-chain (keyed on `(eventtype, eventid)`), plus
- one ReliefWeb disaster (numeric `id`),

carrying a **confidence score**. Join on **GLIDE when present** (high-precision,
low-recall — absent on USGS, ~2% of GDACS), else a **space + time + magnitude
tolerance box** (~100 km, minutes, ±0.5–1.0 M). ISO3 alone is both too coarse
(border quakes) and too fine (offshore = no country).

## Consequences

- The internal schema is a cluster table with a confidence score, not a 1:1 row.
- The join confidence is shown to the reader for low-confidence clusters, not hidden.
- Slice 1 (USGS-only) still builds the cluster abstraction — with one feed, a
  cluster is just the declustered earthquake sequence — so later feeds slot in.

## Alternatives rejected

- **1:1 row-matching / fuzzy dedup** — collapses the ontology differences and
  double-counts (a GDACS quake and its USGS source are the same reading).
- **Report each physical event** — turns an aftershock swarm into report noise.
