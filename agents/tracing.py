"""Shared LangFuse setup. Every agent module imports `get_langfuse_handler()`
and passes it as a callback to its LangChain calls, so every LLM call in the
pipeline is traced -- this satisfies the "LangFuse traces for every LLM call"
requirement without duplicating setup code in each agent."""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings  # noqa: E402

_handler = None


def get_langfuse_handler():
    """Returns a CallbackHandler configured from .env, or None if LangFuse
    keys aren't set (so the pipeline still runs locally without them, just
    without traces -- but this should always be configured for submission)."""
    global _handler
    if _handler is not None:
        return _handler

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        print("[tracing] WARNING: LangFuse keys not set — LLM calls will not be traced.")
        return None

    from langfuse.callback import CallbackHandler

    _handler = CallbackHandler(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    return _handler
