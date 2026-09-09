# AI-Assisted Legacy Migration Platform

FDE Capstone — legacy MySQL → Snowflake migration, with LangChain agents for
schema understanding and rule generation, LangGraph orchestrating the
end-to-end workflow with a human-in-the-loop confidence gate, LangFuse
tracing every LLM call, and Great Expectations + dbt validating the result.

## Project Overview

Legacy databases accumulate undocumented status codes, inconsistent naming,
and business rules buried in application code rather than the schema. This
platform automates the *mechanical* parts of a migration (profiling,
extraction, load, validation) while keeping a human in the loop for every
*semantic* decision an LLM isn't confident about — so nothing ships silently
wrong the way a prior manual migration attempt did (see `DECISIONS.md`).

The pipeline: `schema_profiler → ai_mapper → human_review_gate →
rule_generator → migration_executor → validator → doc_generator`, implemented
as a LangGraph state graph in `workflow/langgraph_orchestrator.py`.

## Architecture Description

```
                 ┌────────────────────┐
                 │  Legacy MySQL (src) │
                 └─────────┬──────────┘
                            │ SQLAlchemy reflection
                            ▼
                 ┌────────────────────┐
                 │  schema_profiler    │  agents/schema_profiler.py
                 │  (no LLM calls)     │  → artifacts/schema_profile.json
                 └─────────┬──────────┘
                            ▼
                 ┌────────────────────┐
                 │  ai_mapper          │  agents/ai_mapper.py (Claude + LangChain)
                 │  per-column mapping │  → artifacts/mappings.json
                 │  + confidence score │  (traced to LangFuse, prompt_id logged)
                 └─────────┬──────────┘
                            ▼
                 ┌────────────────────┐
        ┌───────▶│  human_review_gate  │  workflow/langgraph_orchestrator.py
        │        │  (LangGraph node,   │  pauses (NodeInterrupt) if any mapping
        │        │  pause/resume)      │  < CONFIDENCE_THRESHOLD is unreviewed
        │        └─────────┬──────────┘
        │                   │ all reviewed
        │  review/cli_review.py           ▼
        │  (human approves/rejects/  ┌────────────────────┐
        └──overrides, writes audit)  │  rule_generator      │  agents/rule_generator.py
                             │  blocks unapproved   │  → artifacts/transformation_rules.json
                             └─────────┬──────────┘
                                        ▼
                             ┌────────────────────┐
                             │  migration_executor  │  workflow/migration_executor.py
                             │  extract→load, retry │  → Snowflake stg_<table>
                             │  w/ exponential backoff│
                             └─────────┬──────────┘
                                        ▼
                             ┌────────────────────┐
                             │  validator           │  validation/validator.py
                             │  GE checkpoints x3 + │  + validation/dbt_models/
                             │  reconciliation report│ → artifacts/reconciliation_report.json
                             └─────────┬──────────┘
                                        ▼
                             ┌────────────────────┐
                             │  doc_generator        │  agents/doc_generator.py
                             │  target data dictionary│ → docs/target_data_dictionary.md
                             └────────────────────┘

Every node writes to audit/migration_audit_log.json (audit/audit_logger.py),
and every LLM call is traced to LangFuse (agents/tracing.py).
```

Great Expectations runs at three checkpoints as required:
1. **Source baseline** — `validator.source_baseline()`, before anything moves.
2. **Post-extraction** — implicitly covered by the same DataFrame validated
   at load time in `migration_executor` (see Known Limitations — currently
   folded into checkpoint 3 rather than a fully separate pass).
3. **Post-load** — `validator.post_load_validation()`, against Snowflake.

## Setup Instructions

### Prerequisites
- Python 3.10+
- Docker Desktop (for the local MySQL source DB)
- A Google AI Studio API key (free, no card — aistudio.google.com)
- A free Snowflake trial account (https://signup.snowflake.com)
- A free LangFuse Cloud account (https://cloud.langfuse.com)

### Steps

```bash
# 1. Clone/unzip and enter the project
cd legacy-migration

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# edit .env with your Google AI Studio key, Snowflake credentials, LangFuse keys

# 5. Start the legacy source database
docker compose up -d
# wait ~15s for MySQL to initialize, then seed it:
python seed_db/seed_data.py

# 6. In Snowflake, create the target database (matches SNOWFLAKE_DATABASE in .env)
#    e.g. in a Snowflake worksheet: CREATE DATABASE MIGRATION_TARGET;

# 7. Run the pipeline
python main.py run
```

## Environment Variables

Copy `.env.example` to `.env` and fill in your own values. **Never commit `.env`** — it's already excluded via `.gitignore`.

#### LLM (Google Gemini)

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | Yes | — | Google AI Studio API key, used by `agents/ai_mapper.py` and `agents/doc_generator.py`. Free, no card required — get one at [aistudio.google.com](https://aistudio.google.com) ("Get API key"). |
| `LLM_MODEL` | No | `gemini-3.5-flash-lite` | Which Gemini model to call. `gemini-3.5-flash-lite` is recommended over the base Flash model — it has a higher free-tier rate limit (~30 RPM vs ~10-15 RPM), which matters because `ai_mapper` makes one call per column (~25-30 calls per run). |
| `LLM_CALL_DELAY_SECONDS` | No | `4.5` | Seconds to wait between successive `ai_mapper` LLM calls, to stay under Gemini's free-tier requests-per-minute limit. Raise this (e.g. to `6`) if you still hit rate limits on a stricter model/tier. |

#### Source database (legacy MySQL)

| Variable | Required | Default | Description |
|---|---|---|---|
| `SOURCE_DB_URL` | Yes | `mysql+pymysql://legacy_user:legacy_pass@localhost:3306/legacy_db` | SQLAlchemy connection URL for the legacy MySQL instance started via `docker-compose.yml`. Only change this if you altered the Docker Compose credentials or are pointing at a different MySQL instance entirely. |

#### Target warehouse (Snowflake)

| Variable | Required | Default | Description |
|---|---|---|---|
| `SNOWFLAKE_ACCOUNT` | Yes | — | Your account identifier, found in the Snowsight URL (e.g. `xy12345.us-east-1`). |
| `SNOWFLAKE_USER` | Yes | — | Snowflake login username. |
| `SNOWFLAKE_PASSWORD` | Yes | — | Snowflake login password. Avoid special characters like `@`, `:`, `/` in this password — they can break URL parsing in `workflow/migration_executor.py`'s connection string construction. |
| `SNOWFLAKE_WAREHOUSE` | No | `COMPUTE_WH` | The compute warehouse to run queries against. |
| `SNOWFLAKE_DATABASE` | No | `MIGRATION_TARGET` | Target database name — must already exist (`CREATE DATABASE MIGRATION_TARGET;` in a Snowsight worksheet before your first run). |
| `SNOWFLAKE_SCHEMA` | No | `PUBLIC` | Target schema within that database. |
| `SNOWFLAKE_ROLE` | No | `ACCOUNTADMIN` | Snowflake role used for the connection. |

#### Observability (LangFuse)

| Variable | Required | Default | Description |
|---|---|---|---|
| `LANGFUSE_PUBLIC_KEY` | No* | — | Public key from your LangFuse Cloud project settings. |
| `LANGFUSE_SECRET_KEY` | No* | — | Secret key from the same project. |
| `LANGFUSE_HOST` | No | `https://cloud.langfuse.com` | LangFuse host — only change this if you're self-hosting LangFuse. |

*Technically optional — `agents/tracing.py` will print a warning and run without tracing if these are unset — but the brief requires every LLM call to be traced, so treat these as required for a real submission. Get free keys at [cloud.langfuse.com](https://cloud.langfuse.com).

#### Pipeline behavior

| Variable | Required | Default | Description |
|---|---|---|---|
| `CONFIDENCE_THRESHOLD` | No | `0.80` | Mappings scoring below this trigger the `human_review_gate` pause. Lower it to force fewer reviews, raise it to catch more borderline cases. |
| `TABLE_FILTER` | No | `all` | Reserved for limiting `schema_profiler` to a subset of tables. Currently accepts `all`; pass a comma-separated table list here if you extend `agents/schema_profiler.py`'s `profile_database()` call to use it. |

## How to Run the Migration Pipeline

```bash
python main.py run
```

This runs `schema_profiler → ai_mapper → human_review_gate`. If any
mapping's confidence is below `CONFIDENCE_THRESHOLD`, the pipeline **pauses**
and prints a `run_id` (thread_id). At that point:

```bash
python main.py review        # interactively approve/reject/override each
                              # flagged mapping; writes decisions + audit log
python main.py resume <run_id>   # continues rule_generator → ... → doc_generator
```

If no mappings are flagged, the pipeline runs straight through to
`doc_generator` in one call.

Outputs land in `artifacts/` (`schema_profile.json`, `mappings.json`,
`transformation_rules.json`, `reconciliation_report.json`) and
`docs/target_data_dictionary.md`.

## How to Rollback a Failed Migration

This pipeline is **read-only against the source database** by design — no
step ever writes back to MySQL — so there is nothing to undo on the source
side.

On the target side:
- `migration_executor` loads each table with `if_exists="replace"`, so a
  failed or partial load can simply be re-run (`python main.py resume
  <run_id>` after fixing the underlying issue, or `python main.py run` for a
  fresh attempt) without manual cleanup of duplicate/partial rows.
- Because the **source baseline** Great Expectations checkpoint runs before
  any data moves, you always have a known-good reference to diff a failed
  target load against — see `validation/great_expectations/results/01_source_baseline_*.json`.
- See `DECISIONS.md` section 4 for the full rollback rationale.

## How to Inspect AI Decisions (Audit Log + LangFuse)

- **Audit log**: `audit/migration_audit_log.json` is an append-only record
  of every schema profile, AI mapping, human decision, rule, migration
  execution, and validation result, each with a UTC timestamp and `run_id`.
  Filter by `run_id` to replay one migration run end-to-end.
- **LangFuse**: log into your LangFuse Cloud project
  (`LANGFUSE_HOST` in `.env`) to see a per-agent trace view — every
  `ai_mapper` and `doc_generator` call is tagged with its `prompt_id` and
  table/column metadata, so you can trace any transformation rule back to
  the exact prompt and model response that produced it.
- **Rule-level lineage**: every entry in `artifacts/transformation_rules.json`
  carries its own `prompt_id`, `confidence`, `human_reviewed`, and
  `override_note` — cross-reference `prompt_id` against LangFuse to see the
  full input/output for that specific decision.

## Known Limitations

- **Checkpointer choice**: `SqliteSaver` persists LangGraph state to
  `artifacts/checkpoints.sqlite` so `run`/`review`/`resume` can be separate
  CLI invocations. It is fine for a single-operator capstone; a real
  deployment would want a proper Postgres-backed checkpointer.
- **Post-extraction checkpoint**: the brief calls for three *distinct* GE
  checkpoints (baseline / post-extraction / post-load). This scaffold
  currently validates the extracted DataFrame implicitly through the
  post-load checkpoint rather than as a fully separate pass — worth
  splitting out if you want the extra rigor.
- **Value-level transformation logic**: `migration_executor` currently
  performs structural extract/rename/load; the `logic` field's CASE-style
  value transformations (e.g. `'A' → 'Active'`) are intended to be applied
  and tested via the dbt models in `validation/dbt_models/`, which ship as a
  starter template — extend them per your actual generated mappings.
- **PII handling**: `schema_profiler` currently samples raw column values
  (including `ssn_enc`) into the JSON profile that gets sent to the LLM.
  For real sensitive data, redact or hash sensitive columns before they
  reach `ai_mapper` — see `DECISIONS.md` section 2.
- **Airflow scheduling**: not implemented; called out in the brief as an
  optional bonus extension.
- **Seed data is synthetic**: `seed_db/seed_data.py` generates fictional
  healthcare/billing data via Faker for demonstration purposes only.

## Project Structure

```
legacy-migration/
├── README.md
├── DECISIONS.md
├── .env.example
├── requirements.txt
├── config.py
├── main.py
├── docker-compose.yml
├── seed_db/
│   ├── 01_schema.sql
│   └── seed_data.py
├── agents/
│   ├── schema_profiler.py
│   ├── ai_mapper.py
│   ├── rule_generator.py
│   ├── doc_generator.py
│   └── tracing.py
├── workflow/
│   ├── langgraph_orchestrator.py
│   └── migration_executor.py
├── review/
│   └── cli_review.py
├── validation/
│   ├── validator.py
│   └── dbt_models/
├── audit/
│   ├── audit_logger.py
│   └── migration_audit_log.json   (generated at runtime)
└── docs/
    └── target_data_dictionary.md  (generated at runtime)
```
