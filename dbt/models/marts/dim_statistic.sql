-- what a statistic is, as of its latest version
with latest as (
  select *, row_number() over (partition by stat_id order by version desc, year) as n
  from {{ ref('stg_statistic_values') }}
),
span as (
  select stat_id, min(published_at) as first_published_at, max(published_at) as last_published_at,
         max(version) as live_version, min(year) as first_year, max(year) as last_year,
         min(case when is_forecast then year end) as forecast_from
  from {{ ref('stg_statistic_values') }}
  group by 1
)
select l.stat_id, l.metric, l.geo, l.topic, l.title, l.keywords, l.unit, l.premium, l.source,
       s.live_version, s.first_published_at, s.last_published_at, s.first_year, s.last_year, s.forecast_from
from latest l join span s using (stat_id)
where l.n = 1
