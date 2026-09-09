"""
doc_generator — LangGraph node #7 (final node).

Uses a LangChain call to turn the approved transformation_rules.json into a
human-readable target data dictionary: column definitions, lineage back to
the source column, the transformation logic applied, and any human
overrides. This becomes the canonical documentation for the migrated
schema and is written to docs/target_data_dictionary.md (also copied to
artifacts/ for consistency with the other pipeline outputs).
"""
import json
import os
import sys
import time
import uuid

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from google.api_core.exceptions import ResourceExhausted

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings, RULES_PATH, DATA_DICTIONARY_PATH, ARTIFACT_DIR  # noqa: E402
from audit.audit_logger import log_event  # noqa: E402
from agents.tracing import get_langfuse_handler  # noqa: E402

SYSTEM_PROMPT = """You write clear, precise data dictionary documentation for a \
data engineering team. Given a list of approved transformation rules (source \
column, target column, transformation logic, null handling, edge cases, \
confidence, whether a human reviewed it), produce a Markdown data dictionary. \
For each target column: name, source lineage, transformation logic in plain \
English, null handling, edge cases, and whether it required human review \
(and why, if an override note is present). Group by source table. Be concise \
and factual — do not invent information not present in the rules."""

llm = ChatGoogleGenerativeAI(model=settings.llm_model, google_api_key=settings.llm_api_key, temperature=0)
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "Transformation rules (JSON):\n\n{rules_json}\n\nWrite the data dictionary now."),
    ]
)


def generate_documentation(run_id: str | None = None, rules_path: str = RULES_PATH) -> str:
    run_id = run_id or f"run-{uuid.uuid4()}"
    with open(rules_path) as f:
        rules = json.load(f)

    handler = get_langfuse_handler()
    chain = prompt | llm
    config = {"callbacks": [handler]} if handler else {}
    config["run_name"] = "doc_generator"

    response = None
    for attempt in range(1, 6):
        try:
            response = chain.invoke({"rules_json": json.dumps(rules, indent=2)}, config=config)
            break
        except ResourceExhausted:
            wait = 15 * attempt
            print(f"  rate limited (attempt {attempt}/5); waiting {wait}s...")
            time.sleep(wait)
    if response is None:
        raise RuntimeError("Gemini rate limit persisted after 5 retries in doc_generator.")
    markdown = response.content

    os.makedirs(os.path.dirname(DATA_DICTIONARY_PATH), exist_ok=True)
    os.makedirs("docs", exist_ok=True)
    with open(DATA_DICTIONARY_PATH, "w") as f:
        f.write(markdown)
    with open("docs/target_data_dictionary.md", "w") as f:
        f.write(markdown)

    log_event("doc_generated", {"rule_count": len(rules), "output_path": DATA_DICTIONARY_PATH}, run_id=run_id)
    return markdown


if __name__ == "__main__":
    doc = generate_documentation()
    print(f"Data dictionary written to {DATA_DICTIONARY_PATH} and docs/target_data_dictionary.md")
