"""FastAPI app: chat API + static web UI."""
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

import openai
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .agent import RecommenderAgent
from .catalog import Catalog
from .llm import LLMConfigError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

for _problem in config.problems():
    log.warning("Config: %s (/chat will fail until fixed)", _problem)

catalog = Catalog(str(BASE_DIR / config.CATALOG_PATH))
agent = RecommenderAgent(catalog)

app = FastAPI(title="Product Recommender", version="1.0.0")
if config.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_methods=["POST", "GET"],
        allow_headers=["Content-Type"],
    )

# --- In-memory sessions (use Redis if you run more than one instance) ---------------
_sessions: "OrderedDict[str, dict]" = OrderedDict()
_lock = threading.Lock()


def _get_session(session_id: str | None) -> tuple[str, dict]:
    now = time.time()
    with _lock:
        for sid in [s for s, d in _sessions.items() if now - d["ts"] > config.SESSION_TTL_SECONDS]:
            _sessions.pop(sid, None)
        if session_id and session_id in _sessions:
            _sessions.move_to_end(session_id)
            session = _sessions[session_id]
        else:
            session_id = uuid.uuid4().hex
            session = {"messages": [], "ts": now, "lock": threading.Lock()}
            _sessions[session_id] = session
            while len(_sessions) > config.MAX_SESSIONS:
                _sessions.popitem(last=False)
        session["ts"] = now
    return session_id, session


def _trim(messages: list) -> None:
    """Drop old turns, always cutting at a plain user message so tool pairs stay intact."""
    if len(messages) <= config.MAX_HISTORY_MESSAGES:
        return
    for i in range(len(messages) - config.MAX_HISTORY_MESSAGES, len(messages)):
        m = messages[i]
        if m["role"] == "user" and isinstance(m["content"], str):
            del messages[:i]
            return


# --- Simple per-IP rate limit -----------------------------------------------------
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    with _hits_lock:
        q = _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= config.RATE_LIMIT_PER_MINUTE:
            raise HTTPException(429, "Too many requests. Please wait a minute.")
        q.append(now)


# --- Routes -----------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=config.MAX_MESSAGE_CHARS)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@app.get("/health")
def health():
    return {"status": "ok", "products": len(catalog.df)}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    _check_rate_limit(request.client.host if request.client else "unknown")
    session_id, session = _get_session(req.session_id)

    with session["lock"]:  # one in-flight turn per session
        messages = session["messages"]
        checkpoint = len(messages)
        messages.append({"role": "user", "content": req.message.strip()})
        try:
            reply = agent.run_turn(messages)
        except LLMConfigError as e:
            del messages[checkpoint:]
            log.error("LLM not configured: %s", e)
            raise HTTPException(500, "Server is not configured correctly.")
        except openai.AuthenticationError:
            del messages[checkpoint:]
            log.error("LLM provider rejected the API key")
            raise HTTPException(500, "Server is not configured correctly.")
        except openai.RateLimitError:
            del messages[checkpoint:]
            raise HTTPException(503, "The assistant is busy. Please try again shortly.")
        except openai.APIError as e:  # includes connection errors and timeouts
            del messages[checkpoint:]
            log.error("LLM API error: %s", e)
            raise HTTPException(502, "The assistant is unavailable. Please try again.")
        except Exception:
            del messages[checkpoint:]
            log.exception("Unexpected error while running the agent")
            raise HTTPException(500, "Server is not configured correctly.")
        _trim(messages)

    return ChatResponse(session_id=session_id, reply=reply)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
