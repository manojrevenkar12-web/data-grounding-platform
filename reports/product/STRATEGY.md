# Platform strategy: grounding AI answers in verified statistics

*Generated from `reports/results.json`; the judgement is in `config/product.yaml`.*

## Where we are

Customers increasingly reach our statistics through AI clients rather than our site. Today the
platform delivers about **18,581 verified answers a week**: the right
number, from the live version, with a citation. But **19.4%** of the answers it
helps give are wrong numbers; 34% of those come from questions worded unlike our catalogue. A wrong
number carrying our citation costs more trust than a refusal. That is why the value of every bet below
counts a wrong number as 3 lost answers.

## North Star

**Verified answers delivered**: Questions from AI clients answered with the right number, from the version that was live, with a citation; counted per week. Estimated in production from analysts' audit of a random sample of answers; measured exactly in the simulation.

Drivers: questions asked → searches that find the right statistic → fetches that return a value →
right version and citation. Guardrails: wrong-number share ≤ 20%,
p95 latency ≤ 250 ms, cost per verified answer ≤ EUR
0.004, and no premium value reaching a plan without premium.

## This quarter

Now: understand where and when a question is about, learn the words customers use, cache statistics by version. Together they move the North Star value by **15,170 a week** and cut
wrong numbers to **3.5%** of answers. That is measured on the same
questions, not estimated.

## What we will not do yet, and why

- **Contract checks in producers' own CI**: no capacity left in north star
- **Agent-to-agent (A2A) endpoint**: one week of discovery this quarter: Do not build unless three paying accounts commit to a pilot.
- **Charts in AI answers**: one week of discovery this quarter: Do not build if a prototype with five customers does not change how often they come back.

## The risk we are watching

On 53 questions written blind (questions-1), the plan gave 4 more right answers and 2 more wrong numbers than today: by our own trust weighting it does not hold up yet: it answers more questions but also gives more wrong numbers. The simulated customers' vocabulary flatters the glossary. So the glossary ships only behind analyst review and a two-week canary with its kill criterion, and the blind set is not studied: if its failures are, it becomes a regression set and a new one is written.

## How we decide

A bet is scored as value × confidence ÷ effort within its investment bucket
(north star 8 eng-weeks, efficiency 4 eng-weeks, discovery 2 eng-weeks). Confidence comes from
the kind of evidence: measured offline 0.9, modelled 0.6, demand signal 0.3.
Every bet has a kill criterion before it starts, and the Now column is run together before we commit,
in case the parts do not add up.
