# Executive brief

*Generated from `reports/results.json`.*

- We deliver about **18,581 verified answers a week** to AI clients
  (audited estimate). Without the platform, an assistant's numbers are wrong
  91% of the time.
- **The problem**: 19% of answers through the platform are still
  wrong numbers, 34% of them from questions worded unlike our catalogue. Support sees about
  195 wrong-number tickets a week.
- **This quarter**: understand where and when a question is about, learn the words customers use, cache statistics by version. Measured together:
  wrong numbers fall to 3.5% and verified answers rise by
  2,495 a week.
- **Not yet**: contract checks in producers' own CI, agent-to-agent (A2A) endpoint, charts in AI answers.
  Each has a kill criterion and a cheap test first.
- **Caution**: On 53 questions written blind (questions-1), the plan gave 4 more right answers and 2 more wrong numbers than today: by our own trust weighting it does not hold up yet: it answers more questions but also gives more wrong numbers. The simulated customers' vocabulary flatters the glossary. So the glossary ships only behind analyst review and a two-week canary with its kill criterion, and the blind set is not studied: if its failures are, it becomes a regression set and a new one is written.
- **Safety held**: no premium value reached a plan without it. The contract gate refused all
  8 deliveries that would have broken consumers.
