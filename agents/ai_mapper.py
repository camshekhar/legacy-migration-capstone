"""
ai_mapper — LangGraph node #2.

For every column in the schema profile, a LangChain agent (backed by Claude)
infers semantic meaning and proposes a target-schema mapping, with a
confidence score and reasoning trace. Every call is:
  - traced to LangFuse (tracing.get_langfuse_handler)
  - tagged with a prompt_id so the mapping is traceable back to the exact
    LLM call that produced it (audit requirement)

This module does NOT decide what happens with low-confidence mappings --
that's human_review_gate's job (workflow/langgraph_orchestrator.py). This
module's only responsibility is: given a column, produce a structured,
confidence-scored guess.
"""
import json
import os
import sys
import time
import uuid

from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from google.api_core.exceptions import ResourceExhausted

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings, SCHEMA_PROFILE_PATH, MAPPINGS_PATH, ARTIFACT_DIR  # noqa: E402
from audit.audit_logger import log_event  # noqa: E402
from agents.tracing import get_langfuse_handler  # noqa: E402

# Free-tier Gemini caps requests per minute (10-30 depending on model). This
# pipeline calls the LLM once per non-PK column, so we pace calls and retry
# with backoff on 429s rather than assume unlimited throughput.
SECONDS_BETWEEN_CALLS = float(os.environ.get("LLM_CALL_DELAY_SECONDS", "4.5"))
MAX_RATE_LIMIT_RETRIES = 5


class ColumnMapping(BaseModel):
    inferred_meaning: str = Field(description="Plain-English guess at what this column represents")
    target_column: str = Field(description="Proposed snake_case column name in the target schema")
    transformation_rule: str = Field(
        description="SQL-like CASE/expression describing how to transform source values to target values"
    )
    null_handling: str = Field(description="How NULLs or missing values should be handled")
    edge_cases: list[str] = Field(description="Known or suspected edge cases in the data")
    confidence: float = Field(description="0.0 to 1.0 confidence in this mapping", ge=0.0, le=1.0)
    reasoning: str = Field(description="Why the agent reached this conclusion")


SYSTEM_PROMPT = """You are a data migration assistant helping migrate a legacy \
OLTP database to a modern cloud warehouse. Given column metadata (name, type, \
sample values, null rate, table, related columns), infer the semantic meaning \
of the column, propose a target column name and transformation rule, and \
return a confidence score with reasoning.

Rules:
- Do NOT guess on values with no clear pattern. If sample values are inconsistent, \
sparse, or ambiguous, give a LOW confidence score (below 0.6) rather than inventing \
a confident-sounding answer.
- Flag anything that looks like sensitive data (SSNs, encrypted blobs, financial \
account numbers) in your reasoning even if you can still propose a mapping.
- Base your inference on the sample values, not just the column name -- codes are \
often undocumented and the name alone is not reliable.
"""

llm = ChatGoogleGenerativeAI(
    model=settings.llm_model,
    google_api_key=settings.llm_api_key,
    temperature=0,
).with_structured_output(ColumnMapping)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        (
            "human",
            "Table: {table}\n"
            "Column: {column}\n"
            "Type: {col_type}\n"
            "Nullable: {nullable}\n"
            "Null rate: {null_rate}\n"
            "Cardinality: {cardinality}\n"
            "Sample values: {sample_values}\n"
            "Is primary key: {is_pk}\n"
            "Is foreign key: {is_fk}\n"
            "Related columns in table: {related_columns}\n\n"
            "Infer the semantic meaning, propose a transformation rule, and return "
            "confidence + reasoning.",
        ),
    ]
)


def map_column(table_name: str, column: dict, related_columns: list[str], run_id: str) -> dict:
    prompt_id = f"prompt-{uuid.uuid4()}"
    handler = get_langfuse_handler()
    chain = prompt | llm

    config = {"callbacks": [handler]} if handler else {}
    config["metadata"] = {"prompt_id": prompt_id, "table": table_name, "column": column["name"]}
    config["run_name"] = f"ai_mapper:{table_name}.{column['name']}"

    invoke_args = {
        "table": table_name,
        "column": column["name"],
        "col_type": column["type"],
        "nullable": column["nullable"],
        "null_rate": column["null_rate"],
        "cardinality": column["cardinality"],
        "sample_values": column["sample_values"],
        "is_pk": column["is_primary_key"],
        "is_fk": column["is_foreign_key"],
        "related_columns": related_columns,
    }

    result: ColumnMapping = None
    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        try:
            result = chain.invoke(invoke_args, config=config)
            break
        except ResourceExhausted as e:
            wait = 15 * attempt  # 15s, 30s, 45s... — free tier resets on a rolling window
            print(f"    rate limited (attempt {attempt}/{MAX_RATE_LIMIT_RETRIES}); "
                  f"waiting {wait}s before retrying {table_name}.{column['name']}...")
            time.sleep(wait)
    if result is None:
        raise RuntimeError(
            f"Gemini rate limit persisted after {MAX_RATE_LIMIT_RETRIES} retries for "
            f"{table_name}.{column['name']}. Wait a minute and re-run, or switch LLM_MODEL "
            f"to a higher-RPM model in .env (e.g. gemini-2.0-flash-lite)."
        )

    mapping = {
        "source_table": table_name,
        "source_column": column["name"],
        "target_column": result.target_column,
        "inferred_meaning": result.inferred_meaning,
        "transformation_rule": result.transformation_rule,
        "null_handling": result.null_handling,
        "edge_cases": result.edge_cases,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "prompt_id": prompt_id,
        "human_reviewed": False,
        "review_decision": None,
        "override_note": None,
    }

    log_event(
        "ai_mapping_generated",
        {"prompt_id": prompt_id, "table": table_name, "column": column["name"], "confidence": result.confidence},
        run_id=run_id,
    )

    return mapping


def generate_all_mappings(run_id: str, schema_profile: dict | None = None) -> list[dict]:
    if schema_profile is None:
        with open(SCHEMA_PROFILE_PATH) as f:
            schema_profile = json.load(f)

    mappings = []
    for table_name, table_info in schema_profile["tables"].items():
        related = [c["name"] for c in table_info["columns"]]
        for column in table_info["columns"]:
            if column["is_primary_key"]:
                # PKs map 1:1 by convention; still log it, but skip the LLM call
                mappings.append(
                    {
                        "source_table": table_name,
                        "source_column": column["name"],
                        "target_column": column["name"],
                        "inferred_meaning": "Primary key — mapped 1:1 by convention",
                        "transformation_rule": "IDENTITY",
                        "null_handling": "N/A (primary key, non-null)",
                        "edge_cases": [],
                        "confidence": 1.0,
                        "reasoning": "Primary keys are structural, not semantic; no inference needed.",
                        "prompt_id": None,
                        "human_reviewed": False,
                        "review_decision": None,
                        "override_note": None,
                    }
                )
                continue
            print(f"  mapping {table_name}.{column['name']}...")
            mappings.append(map_column(table_name, column, related, run_id))
            time.sleep(SECONDS_BETWEEN_CALLS)  # stay under free-tier RPM

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    with open(MAPPINGS_PATH, "w") as f:
        json.dump(mappings, f, indent=2, default=str)

    return mappings


if __name__ == "__main__":
    run_id = f"run-{uuid.uuid4()}"
    print(f"Generating AI mappings (run_id={run_id})...")
    result = generate_all_mappings(run_id)
    low_conf = [m for m in result if m["confidence"] < settings.confidence_threshold]
    print(f"\nDone. {len(result)} mappings generated, {len(low_conf)} below confidence threshold "
          f"({settings.confidence_threshold}) and will need human review.")
