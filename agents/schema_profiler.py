"""
schema_profiler — LangGraph node #1.

Pure Python + SQLAlchemy. No LLM calls here on purpose: this module's job is
to produce ground truth about the source database that every downstream AI
agent (and every Great Expectations baseline) will trust. Garbage in here
means garbage decisions everywhere else.

Output: a JSON document (config.SCHEMA_PROFILE_PATH) shaped like:

{
  "generated_at": "...",
  "tables": {
    "patient_records": {
      "row_count": 12000,
      "columns": [
        {
          "name": "pat_st_cd",
          "type": "VARCHAR(2)",
          "nullable": false,
          "null_rate": 0.0,
          "cardinality": 6,
          "sample_values": ["A", "D", "I", "S", "?", ""],
          "is_primary_key": false,
          "is_foreign_key": false
        },
        ...
      ],
      "foreign_keys": [
        {"column": "plan_id", "references_table": "insurance_plans", "references_column": "plan_id"}
      ]
    },
    ...
  },
  "fk_graph": [ {"from_table": "...", "from_column": "...", "to_table": "...", "to_column": "..."} ]
}
"""
import json
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, func, select, MetaData, Table

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings, SCHEMA_PROFILE_PATH, ARTIFACT_DIR  # noqa: E402
from audit.audit_logger import log_event  # noqa: E402

SAMPLE_SIZE = 8


def _column_profile(conn, table: Table, column, pk_cols: set, fk_cols: set) -> dict:
    col_name = column.name
    total = conn.execute(select(func.count()).select_from(table)).scalar() or 0
    non_null = conn.execute(
        select(func.count()).select_from(table).where(column.isnot(None))
    ).scalar() or 0
    null_rate = round(1 - (non_null / total), 4) if total else 0.0

    distinct_count = conn.execute(
        select(func.count(func.distinct(column))).select_from(table)
    ).scalar() or 0

    samples = conn.execute(
        select(func.distinct(column)).where(column.isnot(None)).limit(SAMPLE_SIZE)
    ).fetchall()
    sample_values = [row[0] for row in samples]

    return {
        "name": col_name,
        "type": str(column.type),
        "nullable": column.nullable,
        "null_rate": null_rate,
        "cardinality": distinct_count,
        "sample_values": sample_values,
        "is_primary_key": col_name in pk_cols,
        "is_foreign_key": col_name in fk_cols,
    }


def profile_database(db_url: str | None = None, table_filter: list[str] | None = None) -> dict:
    db_url = db_url or settings.source_db_url
    engine = create_engine(db_url)
    inspector = inspect(engine)
    metadata = MetaData()

    table_names = inspector.get_table_names()
    if table_filter:
        table_names = [t for t in table_names if t in table_filter]

    profile = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_db_url_redacted": db_url.split("@")[-1] if "@" in db_url else "local",
        "tables": {},
        "fk_graph": [],
    }

    with engine.connect() as conn:
        for table_name in table_names:
            table = Table(table_name, metadata, autoload_with=engine)
            pk_cols = {c.name for c in table.primary_key.columns}
            fks = inspector.get_foreign_keys(table_name)
            fk_cols = {fk["constrained_columns"][0] for fk in fks if fk.get("constrained_columns")}

            row_count = conn.execute(select(func.count()).select_from(table)).scalar() or 0

            columns_profile = [
                _column_profile(conn, table, col, pk_cols, fk_cols) for col in table.columns
            ]

            table_fks = []
            for fk in fks:
                if fk.get("constrained_columns") and fk.get("referred_table"):
                    entry = {
                        "column": fk["constrained_columns"][0],
                        "references_table": fk["referred_table"],
                        "references_column": fk["referred_columns"][0],
                    }
                    table_fks.append(entry)
                    profile["fk_graph"].append(
                        {
                            "from_table": table_name,
                            "from_column": entry["column"],
                            "to_table": entry["references_table"],
                            "to_column": entry["references_column"],
                        }
                    )

            profile["tables"][table_name] = {
                "row_count": row_count,
                "columns": columns_profile,
                "foreign_keys": table_fks,
            }
            print(f"  profiled {table_name}: {row_count} rows, {len(columns_profile)} columns")

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    with open(SCHEMA_PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2, default=str)

    log_event(
        "schema_profiled",
        {
            "tables_profiled": list(profile["tables"].keys()),
            "total_row_count": sum(t["row_count"] for t in profile["tables"].values()),
            "output_path": SCHEMA_PROFILE_PATH,
        },
    )

    return profile


if __name__ == "__main__":
    print("Profiling source database...")
    result = profile_database()
    print(f"\nDone. Profile written to {SCHEMA_PROFILE_PATH}")
    print(f"Tables profiled: {list(result['tables'].keys())}")
