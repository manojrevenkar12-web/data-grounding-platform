---
name: triage-feedback
description: Turn wrong-number tickets and customer requests into evidence for existing bets or a new bet proposal; use weekly, or when support escalates.
---

# Triage feedback into the backlog

1. Query `build/telemetry.duckdb` (read only):
   - `tickets`: count by `stat_id` and week
   - for the five most-ticketed statistics: the sessions whose queries fetched them (`sessions`)
2. For each ticketed statistic, classify the likely cause from the queries alone:
   - wrong statistic (the query names another metric or place)
   - stale (an `as_of` or a recent revision)
   - wording (no catalogue word in the query)
3. Map each cause to a bet in `config/product.yaml`. If one fits, add the ticket count as supporting
   evidence in your summary. If none fits, draft a new bet with problem, hypothesis, evidence type
   `demand_signal`, a reach estimate from the ticket and session counts, and a kill criterion.
4. Never quote customer queries verbatim outside the team; summarise them.
