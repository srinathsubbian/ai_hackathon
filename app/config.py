import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
TOOL_MODE = os.getenv("TOOL_MODE", "native").lower()  # native | rag
LLM_VERIFY_SSL = os.getenv("LLM_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}
LLM_USE_SYSTEM_CERTS = os.getenv("LLM_USE_SYSTEM_CERTS", "false").lower() in {"1", "true", "yes"}
LLM_CA_BUNDLE = os.getenv("LLM_CA_BUNDLE", "").strip()  # path to your company CA .pem file
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
    """Human-readable configuration problems, logged at startup and by app.diagnose."""
    out = []
    url = LLM_BASE_URL.lower()
    local = any(h in url for h in ("localhost", "127.0.0.1", "host.docker.internal"))
    if not LLM_MODEL:
        out.append("LLM_MODEL is not set")
    if not LLM_BASE_URL:
        out.append("LLM_BASE_URL is not set (set it to your gateway URL, usually ending in /v1)")
    elif "your-" in url or "your_" in url:
        out.append("LLM_BASE_URL is still the placeholder from .env.example: put your real gateway URL")
    if not LLM_API_KEY and not local:
        out.append("LLM_API_KEY is empty (only local servers can run without a key)")
    if "api.openai.com" in url and LLM_MODEL and not re.match(r"(gpt|o\d|chatgpt|ft:|text-)", LLM_MODEL.lower()):
        out.append(f"LLM_BASE_URL points at api.openai.com but model '{LLM_MODEL}' is not an OpenAI model: "
                   "set LLM_BASE_URL to the gateway that serves this model")
    if TOOL_MODE not in {"native", "rag"}:
        out.append("TOOL_MODE must be 'native' or 'rag'")
    return out
