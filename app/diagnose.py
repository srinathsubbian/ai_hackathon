"""Step-by-step check of your LLM connection:  python -m app.diagnose"""
import httpx

from . import config
from .llm import LLMClient, normalize_base_url

OK, BAD = "[ OK ]", "[FAIL]"

TOOL = [{"type": "function", "function": {
    "name": "ping", "description": "Returns pong.",
    "parameters": {"type": "object", "properties": {}}}}]


def explain(e: Exception) -> str:
    name = type(e).__name__
    status = getattr(e, "status_code", None)
    body = getattr(e, "body", None) or getattr(e, "response", None) and getattr(e.response, "text", "")
    text = f"{name}: {e}"
    if status:
        text += f"  (HTTP {status})"
    if body:
        text += f"\n         response body: {str(body)[:500]}"
    hint = ""
    if status in (401, 403):
        hint = "API key rejected. Check LLM_API_KEY; some gateways need a custom header (see LLM_EXTRA_HEADERS)."
    elif status == 404:
        hint = "Wrong URL path or model name. Check LLM_BASE_URL (usually ends in /v1) and LLM_MODEL."
    elif status == 400:
        hint = "Request rejected. Read the response body: bad model name, or the gateway rejects a parameter."
    elif status == 429:
        hint = "Rate limited or out of quota on the provider side."
    elif status and status >= 500:
        hint = "The gateway itself errored. Retry, or ask its admin."
    elif "ssl" in text.lower() or "certificate" in text.lower():
        hint = "SSL problem (common with internal gateways). Try LLM_VERIFY_SSL=false."
    elif "connect" in text.lower() or "timeout" in text.lower() or "name or service" in text.lower():
        hint = "Cannot reach the gateway: check LLM_BASE_URL, VPN/proxy/firewall, and that this machine can open it."
    return text + (f"\n         hint: {hint}" if hint else "")


def main():
    base = normalize_base_url(config.LLM_BASE_URL)
    key = config.LLM_API_KEY
    print(f"Base URL : {base}")
    print(f"Model    : {config.LLM_MODEL}")
    print(f"API key  : {key[:4] + '...' + key[-2:] if len(key) > 8 else ('(set)' if key else '(empty)')}")
    print(f"SSL check: {config.LLM_VERIFY_SSL}   Tool mode: {config.TOOL_MODE}\n")

    problems = config.problems()
    for p in problems:
        print(BAD, p)
    if problems:
        return

    headers = {"Authorization": f"Bearer {key}", **config.LLM_EXTRA_HEADERS}
    try:
        r = httpx.get(f"{base}/models", headers=headers, verify=config.LLM_VERIFY_SSL, timeout=20)
        ok = r.status_code < 400
        print(OK if ok else BAD, f"GET {base}/models -> HTTP {r.status_code}")
        if ok:
            ids = [m.get("id") for m in r.json().get("data", [])][:15]
            if ids:
                print("         models available:", ", ".join(map(str, ids)))
        else:
            print("         ", r.text[:300])
            print("         (some gateways do not expose /models; the chat tests below matter more)")
    except Exception as e:
        print(BAD, "reach gateway:", explain(e))

    client = LLMClient().client
    try:
        resp = client.chat.completions.create(
            model=config.LLM_MODEL, max_tokens=30,
            messages=[{"role": "user", "content": "Reply with the single word: pong"}])
        print(OK, "plain chat ->", (resp.choices[0].message.content or "").strip()[:80])
    except Exception as e:
        print(BAD, "plain chat:", explain(e))
        print("\nFix the error above first; tool calling cannot work until plain chat does.")
        return

    try:
        resp = client.chat.completions.create(
            model=config.LLM_MODEL, max_tokens=60, tools=TOOL,
            messages=[{"role": "user", "content": "Call the ping tool."}])
        calls = resp.choices[0].message.tool_calls
        if calls:
            print(OK, "tool calling works -> keep TOOL_MODE=native")
        else:
            print(BAD, "model answered without calling the tool -> use TOOL_MODE=rag")
    except Exception as e:
        print(BAD, "chat with tools:", explain(e))
        print("         -> if plain chat worked but this failed, set TOOL_MODE=rag")


if __name__ == "__main__":
    main()
