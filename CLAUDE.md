# CLAUDE.md

## Language & tooling

Python 3.11+. Standard library first; add a dependency only when it earns its
place. `requests` for HTTP, `pytest` for tests.

## Test command

`pytest` (run from the repo root).

## Conventions

1. Deterministic logic lives in `scripts/` and never calls a model.
2. Log the final URL actually fetched, not the one requested.
3. One learning per file in `docs/solutions/` when something costs more than
   ten minutes.

## Deviations policy

Any departure from the PRD or this file is recorded in
`implementation-notes.md` with its reason. An undocumented deviation is a bug.
