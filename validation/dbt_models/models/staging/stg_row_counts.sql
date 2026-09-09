-- Post-migration validation model.
-- Produces one row per staged table with its current row count in the
-- target warehouse, so it can be diffed against
-- artifacts/reconciliation_report.json (which holds the source-side counts
-- captured at migration time) to confirm nothing was lost in transit.

{% set staged_tables = [
    'stg_insurance_plans',
    'stg_providers',
    'stg_patient_records',
    'stg_encounters',
    'stg_billing_transactions'
] %}

{% for table in staged_tables %}
select
    '{{ table }}' as table_name,
    count(*) as row_count
from {{ source('staging', table) }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
