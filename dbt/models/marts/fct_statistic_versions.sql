-- each version of a statistic and when it stopped being the live one
with v as (
  select stat_id, version, min(published_at) as published_at
  from {{ ref('stg_statistic_values') }}
  group by 1, 2
)
select stat_id, version, published_at,
       lead(published_at) over (partition by stat_id order by version) as superseded_at,
       lead(published_at) over (partition by stat_id order by version) is null as is_live
from v
