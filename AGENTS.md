# Working in this repository

For people and coding agents alike.

## Fast feedback

| What | Command | Time |
|---|---|---|
| Fast tests | `uv run pytest -q -m "not slow"` | ~5 s |
| Everything | `uv run pytest -q` | ~70 s |
| Lint | `uv run ruff check src tests && uv run ruff format --check src tests` | 1 s |
| The whole run and the gate | `uv run dgp run` | ~60 s |
| Contracts | `uv run dgp contract lint` | 1 s |
| Dashboard | `uv run dgp export-web && cd web && npm test && npx playwright test` | ~20 s |

## Invariants (each has a test or a gate check)

1. **The platform never reads the world.** `platform/`, `service/`, `product/telemetry.py` and
   `product/scoring.py` decide from what they record. Only `dgp.sim`, `dgp.evals` and the pipeline
   read `config/world.yaml` or `build/truth` (`tests/test_isolation.py`).
2. **Nothing reaches a consumer without passing its contract.** A refused delivery is logged with its
   reasons. A revision is announced through the outbox if and only if it was stored.
3. **No number without a citation, and no premium number for a plan without premium.** If the
   platform cannot answer, it says why ("not covered", "no such year", "not in your plan").
4. **Business settings live in `config/`**: plans, budgets, metering, retrieval, features, the North
   Star, guardrails, bets, capacity, the release gate.
5. **Product documents are generated** (`reports/`), and every number in them comes from
   `reports/results.json`. Judgement (problems, hypotheses, kill criteria) lives in
   `config/product.yaml`.
6. **A bet is measured before it is planned**, on weeks its own learning never saw, and the Now
   column is run together before it is committed.

## Held-out questions

`heldout/<set>/questions.yaml` are written blind, from `heldout/WRITING_QUESTIONS.md` and
`heldout/CATALOGUE.md` only. Run a set once (`dgp heldout <set>`); its first run in
`reports/heldout/<set>/first_run.json` is never rewritten. Never change the platform to pass a
set. If you study a set's failures, write `regression` to its STATUS and have a new set written blind.

## Product skills for Claude Code

`.claude/skills/` has `write-prd`, `review-roadmap` and `triage-feedback`: how the product manager uses
an agent on this repository's evidence. `.mcp.json` connects Claude Code to the grounding MCP server.
