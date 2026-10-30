-- a statistic has exactly one live version
select stat_id from {{ ref('fct_statistic_versions') }}
group by stat_id having sum(case when is_live then 1 else 0 end) <> 1
