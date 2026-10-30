---
name: review-roadmap
description: Challenge the generated roadmap before a planning meeting — evidence quality, guardrails, prerequisites, what the blind set says; use before quarterly planning or when the roadmap changes.
---

# Review the roadmap

Read `reports/product/ROADMAP.md`, `reports/results.json` and `config/product.yaml`, then report, briefly:

1. **Evidence**: for each Now bet, the evidence type and whether its interval excludes zero. Flag
   any Now bet with only modelled or demand evidence.
2. **Guardrails**: the plan's wrong-number share, p95 latency and cost per verified answer against
   `guardrails`; name any within 10% of its bound.
3. **Does it add up**: `plan.delta.value` against `plan.parts_sum`. A gap above 10% means the bets
   interact; say which.
4. **Blind check**: compare the plan with today on `reports/heldout/*/first_run.json`. If the blind set
   is worse on wrong numbers, recommend the canary and the kill criterion, not a full launch.
5. **What would change the order**: the smallest change in effort or value that would swap a Now
   and a Next bet.

Do not edit `config/product.yaml`. Propose changes as a list for the PM to decide.
