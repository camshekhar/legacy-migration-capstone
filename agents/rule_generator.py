"""
rule_generator — LangGraph node #4.

Consumes the (now human-reviewed) mappings and emits the final
transformation_rules.json, conforming exactly to the schema required by the
brief:

{
  "source_column", "target_column", "logic", "null_handling",
  "edge_cases", "confidence", "prompt_id", "human_reviewed", "override_note"
}

Enforcement (this is the part that "blocks the pipeline"):
  Any mapping with confidence < threshold that does NOT have
  human_reviewed=True and a non-null override_note is REJECTED here and
  will not be written into the rule set migration_executor consumes.
"""
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings, MAPPINGS_PATH, RULES_PATH, ARTIFACT_DIR  # noqa: E402
from audit.audit_logger import log_event  # noqa: E402


class UnapprovedMappingError(Exception):
    pass


def build_rule(mapping: dict) -> dict:
    return {
        "source_column": f"{mapping['source_table']}.{mapping['source_column']}",
        "target_column": mapping["target_column"],
        "logic": mapping["transformation_rule"],
        "null_handling": mapping["null_handling"],
        "edge_cases": mapping["edge_cases"],
        "confidence": mapping["confidence"],
        "prompt_id": mapping["prompt_id"],
        "human_reviewed": mapping["human_reviewed"],
        "override_note": mapping["override_note"],
    }


def generate_rules(run_id: str, mappings_path: str = MAPPINGS_PATH) -> list[dict]:
    with open(mappings_path) as f:
        mappings = json.load(f)

    rules = []
    blocked = []
    for mapping in mappings:
        below_threshold = mapping["confidence"] < settings.confidence_threshold
        if below_threshold and not (mapping["human_reviewed"] and mapping["override_note"]):
            blocked.append(mapping)
            continue
        rules.append(build_rule(mapping))

    if blocked:
        log_event(
            "pipeline_error",
            {
                "reason": "unapproved_low_confidence_mappings",
                "blocked_columns": [f"{m['source_table']}.{m['source_column']}" for m in blocked],
            },
            run_id=run_id,
        )
        blocked_names = [f"{m['source_table']}.{m['source_column']}" for m in blocked]
        raise UnapprovedMappingError(
            f"{len(blocked)} low-confidence mapping(s) lack human review + override_note: "
            f"{blocked_names}. Run review/cli_review.py before generating rules."
        )

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    with open(RULES_PATH, "w") as f:
        json.dump(rules, f, indent=2, default=str)

    log_event("rule_generated", {"rule_count": len(rules), "output_path": RULES_PATH}, run_id=run_id)
    return rules


if __name__ == "__main__":
    import uuid

    result = generate_rules(run_id=f"run-{uuid.uuid4()}")
    print(f"Generated {len(result)} approved transformation rules → {RULES_PATH}")
