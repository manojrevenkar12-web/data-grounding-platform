# PRD: Learn the words customers use

*Generated from `reports/results.json`. Owner: platform product. Status: proposed for this quarter.*

## Problem
People ask in their own words ("e-car registrations", "Deutschland"); the catalogue only knows the analysts' words, so the search misses or picks the wrong statistic.

## Evidence
Run on the questions of weeks 9 to 12, on top of facets:

| | Before | With the glossary |
|---|---|---|
| Wrong numbers, share of answers | 18.1% | 3.5% |
| Questions missed (answerable, not answered) | 1.8% | 0.2% |
| Verified answers a week | 18,430 | 20,925 |

Value: **14,135 trust-weighted answers a week** (12,472 to 16,093); confidence 0.9.

## Hypothesis
Synonyms mined from rephrased questions in the MCP session logs, reviewed by analysts, recover most of those misses.

## Users
- **Customers' AI clients** (Claude, Copilot, Langdock, n8n): get the statistic the user meant.
- **Analysts**: review proposed synonyms; nothing is served without their approval.
- **Platform engineers**: run the weekly mining job; own the serving index.

## Requirements
1. Mine candidate synonyms weekly from MCP session logs: rephrased queries that ended in a fetch.
2. Never propose a word the catalogue already uses, a fragment shorter than three letters, or a
   word without at least three sessions behind it. A geography name must point at one geography
   across at least three metrics.
3. Analysts approve or reject each candidate in a review queue. The approved list is versioned,
   and every change is audited.
4. Serving uses only approved words. Rolling back to the previous list takes one command.
5. No change to entitlements, citations or as-of answers.

## Acceptance criteria
- On the last four weeks, wrong-number share falls by at least a half against the current list, and
  verified answers do not fall (`dgp run`: the gate).
- p95 latency stays within 250 ms.
- Every served synonym has an approving analyst and a date.

## Proposed this run (for review, not yet served)

| Metric | Words |
|---|---|
| air_passengers | flight, flying, traffic |
| beer_sales | consumed |
| bike_sales | bikes, e-bike, sold |
| cinema_admissions | attendance, movie, tickets, visits |
| coffee_consumption | demand, intake |
| electricity_price | bill, cost, energy, homes, kwh, residential |
| ev_sales | e-car, registrations |
| fintech_users | cashless, e-wallet, paying |
| gaming_revenue | games, industry |
| gdp | economic, economy, national, output, size |

| Geography | Names |
|---|---|
| BR | brasil |
| DE | deutschland |
| GB | britain, drunk, great |
| NL | holland |
| US | america |
| WW | globally |

Some proposals are wrong (a word that co-occurred by chance). That is why analysts review them.

## Rollout
Two weeks on 10% of accounts, compared with the rest on the same metrics. Then everyone.

## Kill criterion
Stop if analysts reject more than half of the proposed synonyms, or verified answers do not rise in the canary.
