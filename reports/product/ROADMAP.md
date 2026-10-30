# Roadmap

*Generated from `reports/results.json`.*

## Now (this quarter)

### Understand where and when a question is about

- **Problem**: Searches ignore the geography and year in the question, so "EV sales in Germany 2023" can return France, and a place we do not cover gets a neighbour's number.
- **Hypothesis**: Parsing geography and year as filters, and answering "not covered" for places outside the catalogue, cuts wrong numbers without losing right ones.
- **Evidence**: measured offline: 1,035 trust-weighted answers/week (772 to 1,312); confidence 0.9
- **Effort**: 3 engineer-weeks (north star)
- **Kill criterion**: Roll back if, after two weeks on 10% of accounts, wrong-number share has not fallen by a fifth or verified answers fell.
- **Why here**: needed by learn the words customers use

### Learn the words customers use

- **Problem**: People ask in their own words ("e-car registrations", "Deutschland"); the catalogue only knows the analysts' words, so the search misses or picks the wrong statistic.
- **Hypothesis**: Synonyms mined from rephrased questions in the MCP session logs, reviewed by analysts, recover most of those misses.
- **Evidence**: measured offline: 14,135 trust-weighted answers/week (12,472 to 16,093); confidence 0.9
- **Effort**: 4 engineer-weeks (north star)
- **Kill criterion**: Stop if analysts reject more than half of the proposed synonyms, or verified answers do not rise in the canary.

### Cache statistics by version

- **Problem**: Popular statistics are fetched from the warehouse thousands of times a week.
- **Hypothesis**: A cache keyed by statistic and version (invalidated by the revision stream) cuts warehouse cost and latency with no staleness.
- **Evidence**: measured offline: 7.89 EUR saved a week; confidence 0.9
- **Effort**: 2 engineer-weeks (efficiency)
- **Kill criterion**: Roll back on any stale answer traced to the cache.

## Next

### Contract checks in producers' own CI

- **Problem**: A delivery that breaks its contract is refused at the door and waits days for a platform engineer's review; meanwhile customers get the old number.
- **Hypothesis**: Running the same contract checks in the producers' pipelines catches most breaks before delivery and gets the fix live the same day.
- **Evidence**: modelled: 30 trust-weighted answers/week (10 to 60); confidence 0.6
- **Effort**: 3 engineer-weeks (north star)
- **Kill criterion**: Stop if producer teams do not adopt it within a month (fewer than half of deliveries checked in CI).
- **Why here**: no capacity left in north star

## Discovery

### Agent-to-agent (A2A) endpoint

- **Problem**: Some enterprise customers build multi-agent systems and ask for A2A alongside MCP.
- **Hypothesis**: An A2A endpoint over the same grounding service opens accounts that do not use MCP clients.
- **Evidence**: demand signal: 200 verified answers/week (stated, not measured); confidence 0.3
- **Effort**: 5 engineer-weeks (discovery)
- **Kill criterion**: Do not build unless three paying accounts commit to a pilot.
- **Why here**: one week of discovery this quarter: Do not build unless three paying accounts commit to a pilot.

### Charts in AI answers

- **Problem**: Users copy numbers into slides; the research assistant cannot return a chart.
- **Hypothesis**: Returning a chart specification with the citation increases repeat use.
- **Evidence**: demand signal: 120 verified answers/week (stated, not measured); confidence 0.3
- **Effort**: 4 engineer-weeks (discovery)
- **Kill criterion**: Do not build if a prototype with five customers does not change how often they come back.
- **Why here**: one week of discovery this quarter: Do not build if a prototype with five customers does not change how often they come back.

## Not now

Nothing.
