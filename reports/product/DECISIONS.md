# Decision log

*Generated from `reports/results.json`; reversible decisions are revisited every quarter.*

| Decision | Column | Evidence | Reason | Revisit / kill when |
|---|---|---|---|---|
| Understand where and when a question is about | now | measured offline, 1,035/week, confidence 0.9 | needed by: Learn the words customers use | Roll back if, after two weeks on 10% of accounts, wrong-number share has not fallen by a fifth or verified answers fell. |
| Learn the words customers use | now | measured offline, 14,135/week, confidence 0.9 | highest score that fits | Stop if analysts reject more than half of the proposed synonyms, or verified answers do not rise in the canary. |
| Cache statistics by version | now | measured offline, EUR 7.89/week, confidence 0.9 | highest score that fits | Roll back on any stale answer traced to the cache. |
| Contract checks in producers' own CI | next | modelled, 30/week, confidence 0.6 | no capacity left in north star | Stop if producer teams do not adopt it within a month (fewer than half of deliveries checked in CI). |
| Agent-to-agent (A2A) endpoint | discovery | demand signal, 200/week, confidence 0.3 | one week of discovery this quarter: Do not build unless three paying accounts commit to a pilot. | Do not build unless three paying accounts commit to a pilot. |
| Charts in AI answers | discovery | demand signal, 120/week, confidence 0.3 | one week of discovery this quarter: Do not build if a prototype with five customers does not change how often they come back. | Do not build if a prototype with five customers does not change how often they come back. |
