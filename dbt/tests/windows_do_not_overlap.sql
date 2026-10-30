-- a superseded version ended when the next one was published, never before it began
select stat_id, version from {{ ref('fct_statistic_versions') }}
where superseded_at is not null and superseded_at < published_at
