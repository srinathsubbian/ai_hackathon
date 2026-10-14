"""Product recommendation agent (provider-agnostic).

Two modes (TOOL_MODE):
  native - the model calls search tools itself (needs function-calling support)
  rag    - the app searches the catalog first and puts results in the prompt
           (works with any chat model, including ones without tool calling)
"""
import json
import logging
import re

from . import config
from .catalog import Catalog
from .llm import LLMClient

log = logging.getLogger("agent")

BASE_RULES = """You are a friendly shopping assistant for an online store.

Rules:
- Only recommend products from the catalog data you are given. Never invent products, prices, or specs.
- If the customer has not given enough information (use case or budget), ask ONE short
  clarifying question first.
- Recommend 3-5 products. For each: name, product_id, price, and one sentence on why it
  fits THIS customer's stated preferences.
- Never recommend out-of-stock items.
- If nothing matches, say so and suggest how to broaden the search.
- Stay on topic: shopping help for this store only."""

SYSTEM_PROMPT_NATIVE = BASE_RULES + """
- Use the search_products tool with short keyword queries (e.g. "waterproof hiking") and
  filters for budget/category before recommending."""

SYSTEM_PROMPT_RAG = BASE_RULES + """

CATALOG MATCHES for the customer's request (JSON). This is the ONLY data you may recommend from.
An empty list means nothing matched:
{matches}"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the product catalog by keywords with optional filters. "
                           "Returns matching products ranked by relevance and rating.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords, e.g. 'cozy winter warm'."},
                    "category": {"type": "string", "description": "Optional category filter."},
                    "max_price": {"type": "number", "description": "Optional maximum price."},
                    "min_price": {"type": "number", "description": "Optional minimum price."},
                    "in_stock_only": {"type": "boolean", "description": "Defaults to true."},
                    "limit": {"type": "integer", "description": "Max results (default 5, max 10)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Get the full record for one product by product_id.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string", "description": "e.g. P001"}},
                "required": ["product_id"],
            },
        },
    },
]

_BUDGET_RE = re.compile(
    r"(?:under|below|less than|up to|upto|max(?:imum)?|within|budget(?: of)?|<=?)\s*"
    r"(?:rs\.?|inr|usd|[$₹€£])?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def extract_budget(text: str) -> float | None:
    """Pull the most recent 'under $200'-style budget out of free text."""
    matches = _BUDGET_RE.findall(text)
    if not matches:
        return None
    return float(matches[-1].replace(",", ""))


class RecommenderAgent:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.llm = LLMClient()

    # ---- tools ----
    def _run_tool(self, name: str, args) -> str:
        try:
            if not isinstance(args, dict):
                raise ValueError("Tool arguments must be a JSON object")
            if name == "search_products":
                result = self.catalog.search(**args)
            elif name == "get_product_details":
                result = self.catalog.get(args["product_id"]) or {"error": "Product not found"}
            else:
                result = {"error": f"Unknown tool {name}"}
        except Exception as e:  # return errors to the model so it can recover
            log.exception("Tool %s failed", name)
            result = {"error": str(e)}
        return json.dumps(result, default=str)

    # ---- modes ----
    def run_turn(self, messages: list) -> str:
        if config.TOOL_MODE == "rag":
            return self._run_rag(messages)
        return self._run_native(messages)

    def _run_native(self, messages: list) -> str:
        system = [{"role": "system", "content": SYSTEM_PROMPT_NATIVE}]
        for _ in range(config.MAX_STEPS):
            msg = self.llm.complete(system + messages, TOOLS)
            tool_calls = msg.tool_calls or []
            entry = {"role": "assistant", "content": msg.content or ""}
            if tool_calls:
                entry["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                    for tc in tool_calls
                ]
            messages.append(entry)
            if not tool_calls:
                return (msg.content or "").strip()

            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = None
                log.info("tool=%s args=%s", tc.function.name, tc.function.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": self._run_tool(tc.function.name, args),
                })
        return "Sorry, I couldn't finish that request. Could you rephrase it?"

    def _run_rag(self, messages: list) -> str:
        user_text = " ".join(m["content"] for m in messages if m["role"] == "user")
        matches = self.catalog.search(user_text, max_price=extract_budget(user_text), limit=8)
        log.info("rag matches=%d", len(matches))
        system = SYSTEM_PROMPT_RAG.format(matches=json.dumps(matches, default=str))
        msg = self.llm.complete([{"role": "system", "content": system}] + messages)
        reply = (msg.content or "").strip()
        messages.append({"role": "assistant", "content": reply})
        return reply
