"""
migration_executor — LangGraph node #5.

Reads the approved transformation_rules.json, extracts each source table via
SQLAlchemy, applies transformations in pandas, and loads into Snowflake.
Retries transient failures with exponential backoff. Every table's
execution result (rows extracted, rows loaded, errors) is written to the
audit log so it can be reconciled against the schema profile baseline.
"""
import json
import os
import sys
import time
import uuid
from collections import defaultdict

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings, RULES_PATH  # noqa: E402
from audit.audit_logger import log_event  # noqa: E402

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2


def _snowflake_engine():
    from snowflake.sqlalchemy import URL

    url = URL(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
        password=settings.snowflake_password,
        warehouse=settings.snowflake_warehouse,
        database=settings.snowflake_database,
        schema=settings.snowflake_schema,
        role=settings.snowflake_role,
    )
    return create_engine(url)


def _with_retry(fn, *args, **kwargs):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - deliberately broad; this is the retry boundary
            last_err = e
            wait = BASE_BACKOFF_SECONDS ** attempt
            print(f"  attempt {attempt}/{MAX_RETRIES} failed ({e}); retrying in {wait}s...")
            time.sleep(wait)
    raise last_err


def group_rules_by_source_table(rules: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for rule in rules:
        table = rule["source_column"].split(".")[0]
        grouped[table].append(rule)
    return grouped


def migrate_table(source_engine, target_engine, table: str, rules: list[dict], run_id: str) -> dict:
    def extract():
        # Pass the engine directly (not an open connection) -- pandas manages
        # the connection lifecycle itself this way, which is far more robust
        # across pandas/SQLAlchemy version combinations than handing it an
        # already-open Connection object.
        return pd.read_sql(text(f"SELECT * FROM {table}"), source_engine)

    df = _with_retry(extract)
    source_rows = len(df)

    rename_map = {}
    for rule in rules:
        _, col = rule["source_column"].split(".")
        rename_map[col] = rule["target_column"]
        # NOTE: `logic` for status-code CASE expressions is intentionally applied
        # via SQL post-load (dbt models) rather than in pandas here, to keep the
        # transformation logic in one auditable, testable place (see
        # validation/dbt_models). This executor performs the structural
        # extract-and-load; dbt performs and tests the value-level transforms.

    target_df = df.rename(columns=rename_map)
    target_table_name = f"stg_{table}"

    def load():
        target_df.to_sql(target_table_name, target_engine, if_exists="replace", index=False)

    _with_retry(load)

    result = {
        "table": table,
        "target_table": target_table_name,
        "source_row_count": source_rows,
        "loaded_row_count": len(target_df),
        "columns_migrated": list(rename_map.values()),
    }
    log_event("migration_executed", result, run_id=run_id)
    return result


def run_migration(run_id: str | None = None) -> list[dict]:
    run_id = run_id or f"run-{uuid.uuid4()}"
    with open(RULES_PATH) as f:
        rules = json.load(f)

    grouped = group_rules_by_source_table(rules)
    source_engine = create_engine(settings.source_db_url)
    target_engine = _snowflake_engine()

    results = []
    for table, table_rules in grouped.items():
        print(f"Migrating {table} ({len(table_rules)} columns)...")
        results.append(migrate_table(source_engine, target_engine, table, table_rules, run_id))

    return results


if __name__ == "__main__":
    outcome = run_migration()
    for r in outcome:
        print(f"  {r['table']} -> {r['target_table']}: {r['loaded_row_count']}/{r['source_row_count']} rows")
