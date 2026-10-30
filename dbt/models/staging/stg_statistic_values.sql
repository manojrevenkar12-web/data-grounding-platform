-- one row per statistic, year and version; a re-delivered version keeps its first copy
select stat_id, metric, geo, topic, title, keywords, unit, premium, source, year, value, is_forecast,
       version, published_at
from (
  select *, row_number() over (partition by stat_id, year, version order by ingested_at) as n
  from {{ source('raw', 'raw_statistic_values') }}
) where n = 1
