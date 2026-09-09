"""
langgraph_orchestrator — wires the 7 required nodes into a single stateful
graph with a genuine pause-and-resume human review gate:

    schema_profiler -> ai_mapper -> human_review_gate -> rule_generator
        -> migration_executor -> validator -> doc_generator

How the human-in-the-loop pause works
--------------------------------------
LangGraph lets a node raise `NodeInterrupt` to pause the graph mid-run. Our
`human_review_gate` node checks the mappings produced by ai_mapper: if any
column is below CONFIDENCE_THRESHOLD and hasn't been human_reviewed yet, it
raises NodeInterrupt and the graph halts *before* rule_generator ever runs.

A checkpointer (MemorySaver here; swap for a persistent one like SqliteSaver
in production) keeps the graph's state alive across that pause, keyed by
`thread_id`. The operator then runs `review/cli_review.py`, which writes
approve/reject/override decisions back into mappings.json. Re-invoking the
graph with the same thread_id re-enters human_review_gate, which re-checks
the mappings; if everything is now reviewed, it lets the graph continue.

This is what "no mapping bypasses this gate" means in code: rule_generator
is structurally unreachable until human_review_gate stops raising.
"""
import json
import os
import sys
import uuid
from typing import TypedDict

from langgraph.errors import NodeInterrupt
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings, MAPPINGS_PATH, RULES_PATH  # noqa: E402
from audit.audit_logger import log_event  # noqa: E402
from agents import schema_profiler, ai_mapper, rule_generator, doc_generator  # noqa: E402
from workflow import migration_executor  # noqa: E402
from validation import validator  # noqa: E402


class MigrationState(TypedDict, total=False):
    run_id: str
    schema_profile: dict
    mappings: list[dict]
    rules: list[dict]
    migration_result: list[dict]
    reconciliation: dict
    documentation: str
    error: str


def node_schema_profiler(state: MigrationState) -> MigrationState:
    print("\n[1/7] schema_profiler")
    profile = schema_profiler.profile_database()
    return {"schema_profile": profile}


def node_ai_mapper(state: MigrationState) -> MigrationState:
    print("[2/7] ai_mapper")
    mappings = ai_mapper.generate_all_mappings(state["run_id"], state["schema_profile"])
    return {"mappings": mappings}


def node_human_review_gate(state: MigrationState) -> MigrationState:
    print("[3/7] human_review_gate")
    with open(MAPPINGS_PATH) as f:
        mappings = json.load(f)

    unresolved = [
        m for m in mappings
        if m["confidence"] < settings.confidence_threshold
        and not (m["human_reviewed"] and m["override_note"])
    ]

    if unresolved:
        log_event(
            "pipeline_error",
            {"reason": "awaiting_human_review", "pending_count": len(unresolved)},
            run_id=state["run_id"],
        )
        raise NodeInterrupt(
            f"{len(unresolved)} mapping(s) need human review before continuing. "
            f"Run: python review/cli_review.py -- then re-invoke the graph with the same thread_id."
        )

    print("  all low-confidence mappings have been human-reviewed. Proceeding.")
    return {"mappings": mappings}


def node_rule_generator(state: MigrationState) -> MigrationState:
    print("[4/7] rule_generator")
    rules = rule_generator.generate_rules(state["run_id"])
    return {"rules": rules}


def node_migration_executor(state: MigrationState) -> MigrationState:
    print("[5/7] migration_executor")
    result = migration_executor.run_migration(state["run_id"])
    return {"migration_result": result}


def node_validator(state: MigrationState) -> MigrationState:
    print("[6/7] validator")
    validator.post_load_validation(state["run_id"])
    report = validator.build_reconciliation_report(state["run_id"])
    return {"reconciliation": report}


def node_doc_generator(state: MigrationState) -> MigrationState:
    print("[7/7] doc_generator")
    doc = doc_generator.generate_documentation(state["run_id"])
    return {"documentation": doc}


CHECKPOINT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts", "checkpoints.sqlite")


def _build_graph(checkpointer):
    graph = StateGraph(MigrationState)
    graph.add_node("schema_profiler", node_schema_profiler)
    graph.add_node("ai_mapper", node_ai_mapper)
    graph.add_node("human_review_gate", node_human_review_gate)
    graph.add_node("rule_generator", node_rule_generator)
    graph.add_node("migration_executor", node_migration_executor)
    graph.add_node("validator", node_validator)
    graph.add_node("doc_generator", node_doc_generator)

    graph.set_entry_point("schema_profiler")
    graph.add_edge("schema_profiler", "ai_mapper")
    graph.add_edge("ai_mapper", "human_review_gate")
    graph.add_edge("human_review_gate", "rule_generator")
    graph.add_edge("rule_generator", "migration_executor")
    graph.add_edge("migration_executor", "validator")
    graph.add_edge("validator", "doc_generator")
    graph.add_edge("doc_generator", END)

    return graph.compile(checkpointer=checkpointer)


# NOTE on persistence: SqliteSaver keeps checkpoint state in a file
# (artifacts/checkpoints.sqlite) rather than in memory, specifically so that
# `run_pipeline()` and `resume_pipeline()` can be two SEPARATE CLI invocations
# (e.g. run today, review tomorrow, resume after) and still share state via
# the same thread_id. This is what makes "pause, run cli_review.py, resume"
# actually work across process restarts rather than just within one script.

def run_pipeline(run_id: str | None = None):
    run_id = run_id or f"run-{uuid.uuid4()}"
    os.makedirs(os.path.dirname(CHECKPOINT_DB), exist_ok=True)
    config = {"configurable": {"thread_id": run_id}}

    print(f"Starting migration run: {run_id}")
    with SqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        app = _build_graph(checkpointer)
        for event in app.stream({"run_id": run_id}, config=config):
            pass

    return _report_status(run_id)


def resume_pipeline(run_id: str):
    """Call after review/cli_review.py has updated mappings.json for this run."""
    config = {"configurable": {"thread_id": run_id}}
    with SqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        app = _build_graph(checkpointer)
        for event in app.stream(None, config=config):
            pass

    return _report_status(run_id)


def _report_status(run_id: str) -> dict:
    """Determine whether the pipeline actually finished by checking for the
    final artifact (doc_generator's output), NOT by trusting LangGraph's
    internal interrupt/state bookkeeping -- that turned out to behave
    inconsistently across LangGraph versions and silently under-reported
    pauses as completions. Checking for the real output file is unambiguous:
    doc_generator is the last node, so its output existing (and being fresh)
    means every prior node, including human_review_gate, actually passed.
    """
    from config import DATA_DICTIONARY_PATH, MAPPINGS_PATH

    if os.path.exists(DATA_DICTIONARY_PATH):
        print("\n✅ Pipeline completed. See docs/target_data_dictionary.md and artifacts/reconciliation_report.json.")
        return {"status": "completed", "run_id": run_id}

    # Not completed -- figure out why, using the same check human_review_gate uses.
    pending = 0
    if os.path.exists(MAPPINGS_PATH):
        with open(MAPPINGS_PATH) as f:
            mappings = json.load(f)
        pending = len([
            m for m in mappings
            if m["confidence"] < settings.confidence_threshold
            and not (m["human_reviewed"] and m["override_note"])
        ])

    if pending:
        print(f"\n⏸  Pipeline paused: {pending} mapping(s) still need human review.")
        print(f"    Run: python main.py review")
        print(f"    Then: python main.py resume {run_id}")
    else:
        print("\n⚠ Pipeline did not complete and no mappings are pending review — "
              "check the console output above for an error (likely in migration_executor "
              "or validator, e.g. a Snowflake connection issue).")
    return {"status": "paused", "run_id": run_id}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", help="thread_id of a paused run to resume")
    args = parser.parse_args()

    if args.resume:
        resume_pipeline(args.resume)
    else:
        run_pipeline()
