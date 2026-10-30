---
name: write-prd
description: Draft a PRD for one platform bet from the measured evidence in reports/results.json and the judgement in config/product.yaml; use when a bet moves to Now or someone asks for its spec.
---

# Write a PRD for a platform bet

1. Run `uv run dgp run` if `reports/results.json` is older than the last change to `config/` or `src/`.
2. Read the bet in `config/product.yaml: bets.<id>` (problem, hypothesis, kill criterion, effort, needs).
3. Read its evidence in `reports/results.json`:
   - `scored[]` with that id: value, interval, confidence, evidence type
   - `evaluation.variants.<id>`: before/after on wrong-number share, missed share and verified answers
   - `evaluation.variants.<id>.measured_against`: what it was measured on top of
4. Read `reports/heldout/*/first_run.json`. If the blind set disagrees with the simulation, say so
   in the PRD's risks. Do not open the held-out questions themselves.
5. Write the PRD with these sections: Problem, Evidence (a table of numbers copied from the results,
   never rounded differently), Users, Requirements (numbered, testable), Acceptance criteria
   (each one a metric and a threshold that `dgp run` or a canary can check), Rollout, Kill criterion,
   Open questions.
6. Every number must come from a file you read; if a number you need does not exist, write
   "not measured" and propose how to measure it.
