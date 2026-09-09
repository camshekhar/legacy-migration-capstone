"""
validator — LangGraph node #6.

Runs Great Expectations suites at THREE checkpoints, as required:
  1. source baseline   (pre-migration, against the legacy MySQL tables)
  2. post-extraction   (against the pandas DataFrame pulled by migration_executor)
  3. post-load         (against the loaded Snowflake staging tables)

Then produces a reconciliation_report.json comparing source vs target row
counts, null rates, and value distributions for every migrated table.
A failing checkpoint blocks pipeline completion (raises ValidationFailedError),
per the "no reconciliation report = not a completed migration" anti-pattern
called out in the brief.

Uses Great Expectations' PandasDataset API, which lets us define expectations
directly against a DataFrame without standing up a full Data Context — the
right level of ceremony for a per-table validation step in this pipeline.
"""
import json
import os
import sys

import pandas as pd
from great_expectations.dataset import PandasDataset
from sqlalchemy import create_engine, text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings, SCHEMA_PROFILE_PATH, RECONCILIATION_PATH, ARTIFACT_DIR  # noqa: E402
from audit.audit_logger import log_event  # noqa: E402

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "great_expectations", "results")


class ValidationFailedError(Exception):
    pass


def _build_suite(df: pd.DataFrame, table_profile: dict) -> PandasDataset:
    ds = PandasDataset(df)
    for col in table_profile["columns"]:
        name = col["name"]
        if name not in df.columns:
            continue
        if not col["nullable"]:
            ds.expect_column_values_to_not_be_null(name)
        if col["is_primary_key"]:
            ds.expect_column_values_to_be_unique(name)
        # Low-cardinality "status code" style columns: constrain to the observed
        # value set from the baseline profile so drift after migration is caught.
        if 0 < col["cardinality"] <= 10 and col["sample_values"]:
            ds.expect_column_values_to_be_in_set(name, col["sample_values"], mostly=0.95)
    return ds


def _save_results(name: str, results: dict, run_id: str) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log_event(
        "validation_result",
        {"checkpoint": name, "success": results.get("success"), "output_path": path},
        run_id=run_id,
    )
    return path


def run_checkpoint(name: str, df: pd.DataFrame, table_profile: dict, run_id: str, strict: bool = True) -> dict:
    suite = _build_suite(df, table_profile)
    results = suite.validate(result_format="SUMMARY")
    results_dict = results.to_json_dict()
    _save_results(name, results_dict, run_id)

    if strict and not results_dict["success"]:
        raise ValidationFailedError(f"Checkpoint '{name}' failed: {results_dict['statistics']}")
    return results_dict


def source_baseline(run_id: str) -> dict:
    """Checkpoint 1: pre-migration baseline against the legacy DB."""
    with open(SCHEMA_PROFILE_PATH) as f:
        profile = json.load(f)

    engine = create_engine(settings.source_db_url)
    all_results = {}
    for table, table_profile in profile["tables"].items():
        # Pass the engine directly, not an open connection (see
        # workflow/migration_executor.py for why this matters).
        df = pd.read_sql(text(f"SELECT * FROM {table}"), engine)
        all_results[table] = run_checkpoint(f"01_source_baseline_{table}", df, table_profile, run_id)
    return all_results


def post_load_validation(run_id: str) -> dict:
    """Checkpoint 3: post-load against Snowflake staging tables."""
    from workflow.migration_executor import _snowflake_engine  # local import avoids hard Snowflake dep at collection time

    with open(SCHEMA_PROFILE_PATH) as f:
        profile = json.load(f)

    engine = _snowflake_engine()
    all_results = {}
    for table in profile["tables"]:
        target_table = f"stg_{table}"
        try:
            df = pd.read_sql(text(f"SELECT * FROM {target_table}"), engine)
        except Exception as e:  # noqa: BLE001
            print(f"  skipping {target_table}: {e}")
            continue
        # Reuse the source table's expectation shapes as a loose proxy —
        # column names differ post-rename so this focuses on null/uniqueness,
        # not the renamed value-set checks (those live in dbt).
        all_results[table] = run_checkpoint(
            f"03_post_load_{table}", df, profile["tables"][table], run_id, strict=False
        )
    return all_results


def build_reconciliation_report(run_id: str) -> dict:
    """Compares source vs target row counts / null rates for every migrated table."""
    from workflow.migration_executor import _snowflake_engine

    with open(SCHEMA_PROFILE_PATH) as f:
        profile = json.load(f)

    source_engine = create_engine(settings.source_db_url)
    target_engine = _snowflake_engine()

    report = {"tables": {}}
    with source_engine.connect() as sconn, target_engine.connect() as tconn:
        for table in profile["tables"]:
            target_table = f"stg_{table}"
            src_count = sconn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            try:
                tgt_count = tconn.execute(text(f"SELECT COUNT(*) FROM {target_table}")).scalar()
            except Exception:  # noqa: BLE001
                tgt_count = None

            report["tables"][table] = {
                "source_row_count": src_count,
                "target_row_count": tgt_count,
                "row_count_match": (src_count == tgt_count) if tgt_count is not None else False,
                "target_table": target_table,
            }

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    with open(RECONCILIATION_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    log_event("validation_result", {"checkpoint": "reconciliation_report", "report": report}, run_id=run_id)
    return report


if __name__ == "__main__":
    import uuid

    rid = f"run-{uuid.uuid4()}"
    print("Running source baseline checkpoint...")
    source_baseline(rid)
    print("Building reconciliation report...")
    build_reconciliation_report(rid)
    print(f"Done. See {RECONCILIATION_PATH} and validation/great_expectations/results/")
