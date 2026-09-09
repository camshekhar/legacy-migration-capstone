"""
Human review interface (CLI) — satisfies the human_review_gate requirement.

Presents every mapping below CONFIDENCE_THRESHOLD to a human operator one at
a time. For each, the operator must choose approve / reject / override.
Every decision is written to the audit log BEFORE the pipeline is allowed to
resume, and is stamped back onto the mapping record itself so
rule_generator can enforce: no mapping proceeds to migration_executor
without human_reviewed=true and a non-null override_note when confidence
was below threshold.
"""
import json
import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings, MAPPINGS_PATH  # noqa: E402
from audit.audit_logger import log_event  # noqa: E402

console = Console()


def review_mapping(mapping: dict) -> dict:
    console.print(
        Panel(
            f"[bold]{mapping['source_table']}.{mapping['source_column']}[/bold] "
            f"→ [bold cyan]{mapping['target_column']}[/bold cyan]\n\n"
            f"Meaning: {mapping['inferred_meaning']}\n"
            f"Rule:    {mapping['transformation_rule']}\n"
            f"Null handling: {mapping['null_handling']}\n"
            f"Edge cases: {mapping['edge_cases']}\n"
            f"Reasoning: {mapping['reasoning']}\n\n"
            f"[yellow]Confidence: {mapping['confidence']}[/yellow] "
            f"(threshold: {settings.confidence_threshold})",
            title="⚠ Low-confidence mapping needs review",
            border_style="yellow",
        )
    )
    decision = Prompt.ask("Decision", choices=["approve", "reject", "override"], default="approve")
    note = Prompt.ask("Reviewer note (required — rationale for the audit trail)")

    mapping["human_reviewed"] = True
    mapping["review_decision"] = decision
    mapping["override_note"] = note

    if decision == "override":
        new_rule = Prompt.ask("Enter corrected transformation_rule", default=mapping["transformation_rule"])
        mapping["transformation_rule"] = new_rule

    return mapping


def run_review_queue(mappings_path: str = MAPPINGS_PATH, run_id: str = "manual-review") -> list[dict]:
    with open(mappings_path) as f:
        mappings = json.load(f)

    flagged = [m for m in mappings if m["confidence"] < settings.confidence_threshold]
    console.print(f"[bold]{len(flagged)} mapping(s) flagged for human review "
                  f"(confidence < {settings.confidence_threshold}).[/bold]\n")

    for mapping in flagged:
        reviewed = review_mapping(mapping)
        log_event(
            "human_review_decision",
            {
                "table": reviewed["source_table"],
                "column": reviewed["source_column"],
                "prompt_id": reviewed["prompt_id"],
                "decision": reviewed["review_decision"],
                "override_note": reviewed["override_note"],
                "confidence": reviewed["confidence"],
            },
            run_id=run_id,
        )

    with open(mappings_path, "w") as f:
        json.dump(mappings, f, indent=2, default=str)

    console.print("\n[green]Review complete. Mappings updated and audit log written.[/green]")
    return mappings


if __name__ == "__main__":
    run_review_queue()
