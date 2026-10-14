# Product Recommendation Agent

A generative AI shopping assistant that works with **your own LLM API**. Customers describe what
they want in plain language; the agent searches your product catalog (CSV) and recommends
matching, in-stock products with reasons.

```
Browser UI ──► FastAPI /chat ──► Agent ──► YOUR LLM API (OpenAI-compatible)
                                   │
                          search_products / get_product_details
                                   │
                             data/products.csv
```

## Project structure

```
product-recommender/
├── app/
│   ├── main.py      # FastAPI app: /chat, /health, sessions, rate limit
│   ├── agent.py     # prompts, tools, native + rag modes
│   ├── llm.py       # the ONLY file that talks to your LLM provider
│   ├── catalog.py   # CSV loading + keyword search
│   ├── config.py    # environment settings
│   └── cli.py       # terminal chat:  python -m app.cli
├── static/index.html  # chat web UI
├── data/products.csv  # sample catalog (30 products)
├── tests/             # pytest suite (no API key needed)
├── Dockerfile  docker-compose.yml  render.yaml
└── requirements.txt  requirements-dev.txt  .env.example
```

## 1. Connect your LLM API

The app speaks the OpenAI-compatible `/chat/completions` format, which most providers and
self-hosted servers support (OpenAI, Azure OpenAI, Groq, Together, OpenRouter, Mistral,
Ollama, vLLM, LM Studio, and many in-house gateways). Set three variables in `.env`:

| Variable | Example |
|---|---|
| `LLM_API_KEY` | your key (can be blank for local servers) |
| `LLM_BASE_URL` | `https://api.openai.com/v1`, `http://localhost:11434/v1` (Ollama), `https://your-gateway/v1` |
| `LLM_MODEL` | `genailab-maas-sonnet-4.6` (the model name your API expects) |

**Pick a mode with `TOOL_MODE`:**

- `native` (default): the model decides when to call the catalog search tool. Needs a model
  with function/tool-calling support.
- `rag`: the app searches the catalog first and puts the matches into the prompt. Works with
  **any** chat model, including ones without tool calling. If tool calls misbehave, switch to this.

**If your API is not OpenAI-compatible**, edit only `LLMClient.complete()` in `app/llm.py`.
It must return an object with `.content` (text) and, for native mode, `.tool_calls`.
In `rag` mode only `.content` is needed, so a plain "send messages, get text" adapter is enough.

## 2. Run locally

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                   # fill in the three LLM_ values
uvicorn app.main:app --reload
```

Open http://localhost:8000. Terminal chat: `python -m app.cli`. Tests: `pytest`.

```bash
curl -s localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "waterproof boots for hiking under $150"}'
```

## 3. Use your own catalog

Replace `data/products.csv`, keeping these columns:

| Column | Notes |
|---|---|
| product_id | unique ID |
| name, category, brand | text |
| price, rating | numbers |
| stock | integer (0 = out of stock, never recommended) |
| tags | semicolon-separated keywords, e.g. `winter;warm;waterproof` |
| description | one or two sentences |

Good tags matter most: search weights tag matches double. Startup fails with a clear
error if a column is missing.

## 4. Deploy

Set `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` (and optionally `TOOL_MODE`) on the host as
environment variables or secrets. **Never commit `.env`.** Your LLM endpoint must be reachable
from where the app runs (a `localhost` Ollama will not be reachable from a cloud host).

### Option A: Docker (any server or VPS)

```bash
docker build -t product-recommender .
docker run -d --name recommender -p 8000:8000 --env-file .env --restart unless-stopped product-recommender
# or: docker compose up -d --build
```

If your LLM server runs on the same machine, use `LLM_BASE_URL=http://host.docker.internal:PORT/v1`
(add `--add-host=host.docker.internal:host-gateway` on Linux) instead of `localhost`.

Put Caddy or Nginx in front for HTTPS. Caddy example (auto-HTTPS):

```
shop-assistant.example.com {
    reverse_proxy localhost:8000
}
```

### Option B: Render (easiest, git push to deploy)

1. Push this folder to a GitHub repo.
2. Render dashboard → New → Blueprint → select the repo (it reads `render.yaml`).
3. Enter `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` when prompted. Deploy.
4. Health check is `/health`. Your URL looks like `https://product-recommender.onrender.com`.

### Option C: Google Cloud Run

```bash
gcloud auth login && gcloud config set project YOUR_PROJECT_ID
printf '%s' "YOUR_LLM_API_KEY" | gcloud secrets create llm-api-key --data-file=-

gcloud run deploy product-recommender \
  --source . --region us-central1 --allow-unauthenticated \
  --set-secrets LLM_API_KEY=llm-api-key:latest \
  --set-env-vars LLM_BASE_URL=https://your-api/v1,LLM_MODEL=genailab-maas-sonnet-4.6 \
  --max-instances 1
```

(You may need to grant the Cloud Run service account the Secret Accessor role on the secret.)

### Option D: Railway / Fly.io

Both detect the `Dockerfile`. Add the three `LLM_` variables as secrets and deploy.
The app listens on `$PORT`.

## 5. Embed in your store

- **Link or iframe:** `<iframe src="https://YOUR-URL" style="width:100%;height:600px;border:0"></iframe>`
- **Your own frontend:** call `POST /chat` with `{message, session_id}` and reuse the returned
  `session_id` to keep the conversation. If the frontend is on another domain, set
  `ALLOWED_ORIGINS=https://your-store.com`.

## 6. Production checklist

- [ ] **Sessions are in memory.** Fine for one instance (`--max-instances 1`). For several
      instances or restarts without losing chats, move `_sessions` in `app/main.py` to Redis.
- [ ] **Cost and abuse control.** Set a spend limit with your LLM provider. The app caps message
      length (1000 chars), history (40 messages), agent steps (8) and requests per IP
      (`RATE_LIMIT_PER_MINUTE`, per instance, in memory).
- [ ] **Model quality.** Small models may ignore rules or skip tool calls. If recommendations look
      off, try `TOOL_MODE=rag` or a stronger model.
- [ ] **Large catalogs.** Past a few thousand products, replace the keyword search in `catalog.py`
      with embeddings (pgvector, Chroma, or a managed vector DB) behind the same `search()` method.
- [ ] **Catalog freshness.** Stock and prices load at startup. Redeploy or add a reload step when
      the CSV changes, or point `Catalog` at your database or API.
- [ ] **Logging and monitoring.** Logs go to stdout. Add uptime checks on `/health`.
- [ ] **Privacy.** Chats are held in memory for one hour and not written to disk. Messages are sent
      to your LLM provider, so check its data policy. If you store transcripts, disclose it.
- [ ] **HTTPS.** Required on any public deployment. Render and Cloud Run provide it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Server is not configured correctly." | `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL` missing or wrong; check startup logs |
| 502 "assistant is unavailable" | LLM endpoint unreachable, wrong base URL, or provider error; check logs |
| 503 "assistant is busy" | Provider rate limit; retry or raise your quota |
| 429 "Too many requests" | Raise `RATE_LIMIT_PER_MINUTE` |
| Model never searches or returns odd output | Set `TOOL_MODE=rag` |
| Bot recommends nothing | Add better `tags`, or check the item is in stock |
| Startup error "missing columns" | CSV headers don't match the table above |
