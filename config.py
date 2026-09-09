"""Central config loader. Every module imports settings from here so
there's exactly one place that reads the .env file."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    llm_api_key: str = os.environ.get("LLM_API_KEY", "")
    llm_model: str = os.environ.get("LLM_MODEL", "gemini-2.0-flash")

    source_db_url: str = os.environ.get("SOURCE_DB_URL", "")

    snowflake_account: str = os.environ.get("SNOWFLAKE_ACCOUNT", "")
    snowflake_user: str = os.environ.get("SNOWFLAKE_USER", "")
    snowflake_password: str = os.environ.get("SNOWFLAKE_PASSWORD", "")
    snowflake_warehouse: str = os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
    snowflake_database: str = os.environ.get("SNOWFLAKE_DATABASE", "MIGRATION_TARGET")
    snowflake_schema: str = os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC")
    snowflake_role: str = os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN")

    langfuse_public_key: str = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.environ.get("LANGFUSE_SECRET_KEY", "")
    langfuse_host: str = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    confidence_threshold: float = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.80"))
    table_filter: str = os.environ.get("TABLE_FILTER", "all")


settings = Settings()

# Root paths used across the pipeline
ARTIFACT_DIR = "artifacts"
SCHEMA_PROFILE_PATH = f"{ARTIFACT_DIR}/schema_profile.json"
MAPPINGS_PATH = f"{ARTIFACT_DIR}/mappings.json"
RULES_PATH = f"{ARTIFACT_DIR}/transformation_rules.json"
RECONCILIATION_PATH = f"{ARTIFACT_DIR}/reconciliation_report.json"
DATA_DICTIONARY_PATH = f"{ARTIFACT_DIR}/target_data_dictionary.md"
AUDIT_LOG_PATH = "audit/migration_audit_log.json"
