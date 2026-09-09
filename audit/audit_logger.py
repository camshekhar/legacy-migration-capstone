"""
Append-only migration audit log.

Design: every event is appended as a new JSON object to a JSON-lines-style
list on disk. We never rewrite or delete existing entries -- only append --
so the file is a durable, chronological record of every AI suggestion,
confidence score, and human decision made during a migration run.

Each entry gets a monotonically increasing `seq` and a UTC timestamp so the
log can be replayed in order, which is what "auditable and reproducible"
means in practice for this capstone.
"""
import json
import os
import uuid
from datetime import datetime, timezone

AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "migration_audit_log.json")


def _load() -> list:
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    with open(AUDIT_LOG_PATH, "r") as f:
        content = f.read().strip()
        return json.loads(content) if content else []


def log_event(event_type: str, payload: dict, run_id: str | None = None) -> dict:
    """Append one immutable audit event. Returns the event that was written.

    event_type examples used across the pipeline:
      'schema_profiled', 'ai_mapping_generated', 'human_review_decision',
      'rule_generated', 'migration_executed', 'validation_result',
      'doc_generated', 'pipeline_error'
    """
    entries = _load()
    event = {
        "event_id": str(uuid.uuid4()),
        "seq": len(entries) + 1,
        "run_id": run_id or "unknown-run",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": payload,
    }
    entries.append(event)
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "w") as f:
        json.dump(entries, f, indent=2, default=str)
    return event


def get_log() -> list:
    return _load()
