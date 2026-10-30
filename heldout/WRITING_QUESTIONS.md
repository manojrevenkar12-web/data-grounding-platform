# Writing held-out questions

This guide and `heldout/CATALOGUE.md` (the public listing of every statistic) are all a writer of a
held-out set may read. Do not read `src/`, `tests/`, `config/`, `dbt/`, `build/`, `reports/` or other
sets: the point is to find out how the platform does on questions written by someone who has not
seen how it searches.

## What the platform is

A business-statistics publisher serves verified statistics to AI assistants (Claude, Copilot, the
publisher's own research assistant, n8n workflows) through an API and an MCP server. A customer
asks an assistant a question in their own words. The assistant searches, fetches one statistic for
one year, and answers with the number and a citation. Customers are on one of three plans:
`enterprise` (every statistic, including premium ones), `team` and `api_starter` (no premium
statistics).

The right answer to a question is one of:

- **value**: the statistic and year the question is about (and, if the question names a
  publication date, the version that was live on that date);
- **no_data**: the catalogue has no statistic for that place, or not for that year;
- **not_entitled**: the statistic is premium and the customer's plan is not `enterprise`.

## A case

Write each case as one item of a YAML list in `heldout/<set>/questions.yaml`:

```yaml
- id: ev-germany-2023-plain        # short, unique
  question: How many electric cars were sold in Germany in 2023?
  plan: team                       # enterprise | team | api_starter
  expect: value                    # value | no_data | not_entitled
  stat_id: ev_sales-DE             # for value and not_entitled: the statistic meant (from CATALOGUE.md)
  year: 2023                       # for value
  as_of: null                      # an ISO date if the question asks for the figure "as published on" a date
  why: plain wording, covered statistic and year
```

## What makes a good set

- **Ask the way real people ask**, not in the catalogue's words. Mix plain questions with
  colloquial ones, abbreviations, country names in other languages or forms, typos, very short
  keyword queries and long chatty ones.
- **Cover every kind of right answer.** About 60% value, 15% no_data (places the catalogue does
  not cover, years before the series starts), 15% not_entitled (premium statistics asked on
  `team` or `api_starter`), and 10% as-of questions on statistics that have a second version, with
  a date between the two versions.
- **Use only statistics, years and dates from CATALOGUE.md**, and check each expected answer
  against it.
- About 50 cases, with at least ten you would call hard: ambiguous wording, two places in one
  question, a forecast year, a year just outside the series.
