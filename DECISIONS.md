# Migration Decisions Log

This document records the design decisions behind this migration platform,
the rationale for thresholds and overrides, and the acknowledgments required
by the project brief. Fill in the bracketed sections after you run the
pipeline against your own data — this is a template, not a finished record.

## 1. Confidence Threshold

**Threshold: 0.80** (configurable via `CONFIDENCE_THRESHOLD` in `.env`).

Rationale: mappings below this threshold are exactly the cases the brief
calls out as genuinely ambiguous — undocumented status codes with no
lookup table, columns whose sample values don't cleanly cluster, or fields
where naming and data disagree. 0.80 was chosen because [explain, after
your first real run, how many columns landed below threshold and whether
that felt like the right number of false positives vs. missed ambiguity].

## 2. Sensitive Data Acknowledgment

The source schema contains at least one column that should be treated as
sensitive: `patient_records.ssn_enc`. This platform:
- does not decrypt or expose this value in any prompt sent to the LLM beyond
  a redacted sample (see `agents/schema_profiler.py` sample_values — [confirm
  whether you added redaction here; the scaffold currently samples raw
  values, which you should tighten before using real PII])
- [document here what encryption-at-rest and access control exists on the
  target Snowflake table for this column, per the brief's regulatory
  constraints]

## 3. Human Overrides

Every mapping with confidence < threshold requires human review before
`rule_generator` will include it in `transformation_rules.json`
(`agents/rule_generator.py` raises `UnapprovedMappingError` otherwise).

Overrides made during this run: [after running `review/cli_review.py`,
summarize each override decision and the reviewer's stated rationale here —
these are also captured verbatim in `audit/migration_audit_log.json`].

## 4. Rollback Strategy

If `validator` fails a checkpoint or `migration_executor` fails partway
through a table:
- Target staging tables are written with `if_exists="replace"`
  (`workflow/migration_executor.py`), so a failed table load can simply be
  re-run from scratch without manual cleanup — it does not partially
  accumulate rows across retries.
- The **source baseline** Great Expectations checkpoint (`validator.source_baseline`)
  is the rollback reference point: because it runs before any data moves, a
  failed migration can always be diffed against a known-good pre-migration
  state.
- No destructive operation is ever run against the source database — this
  pipeline is read-only on the source side by design, which is itself the
  simplest possible rollback guarantee.
- [If you add Airflow, document DAG-level retry/rollback behavior here.]

## 5. Where AI Was Not Trusted

Per the brief's guidance on where AI falls short, this pipeline treats the
following as **out of scope for full automation**, even when the LLM
returns a high-confidence answer:
- Status code meanings that could plausibly map to more than one
  business-critical outcome (e.g., a code that could mean "Discharged" or
  "Deceased") are always routed to the review queue in practice, because
  [explain any additional manual constraint you added beyond the raw
  confidence score, if any].
- Business rule correctness is not considered verified by this pipeline —
  approved rules should still be reviewed by the application team that owns
  the source system before being treated as production-ready.
