import json
import os

from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
TOOL_MODE = os.getenv("TOOL_MODE", "native").lower()  # native | rag
LLM_VERIFY_SSL = os.getenv("LLM_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}
DEBUG_ERRORS = os.getenv("DEBUG_ERRORS", "false").lower() in {"1", "true", "yes"}


def _headers() -> dict:
    raw = os.getenv("LLM_EXTRA_HEADERS", "").strip()
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


LLM_EXTRA_HEADERS = _headers()  # e.g. {"x-api-key": "..."} if your gateway needs custom headers

MAX_STEPS = int(os.getenv("MAX_STEPS", "8"))
CATALOG_PATH = os.getenv("CATALOG_PATH", "data/products.csv")
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

MAX_MESSAGE_CHARS = 1000
MAX_HISTORY_MESSAGES = 40
SESSION_TTL_SECONDS = 60 * 60
MAX_SESSIONS = 1000


def problems() -> list[str]:
    """Human-readable configuration problems, logged at startup."""
    out = []
    if not LLM_MODEL:
        out.append("LLM_MODEL is not set")
    if not LLM_API_KEY and not LLM_BASE_URL:
        out.append("LLM_API_KEY is not set (or set LLM_BASE_URL for a local server)")
    if TOOL_MODE not in {"native", "rag"}:
        out.append("TOOL_MODE must be 'native' or 'rag'")
    return out
