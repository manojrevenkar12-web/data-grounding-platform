-- every value of every version, with the window in which it was the published number
select s.stat_id, s.year, s.version, s.value, s.is_forecast, v.published_at, v.superseded_at, v.is_live
from {{ ref('stg_statistic_values') }} s
join {{ ref('fct_statistic_versions') }} v using (stat_id, version)
