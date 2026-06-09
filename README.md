# 🏨 Travel Mitra

An AI-powered travel assistant for **US hotels**. Chat with it to find hotels by
location, price, and rating; browse results as cards; pick one and ask what guests
actually say about it — answered from **real reviews** via hybrid (vector +
metadata) retrieval.

Built as a production-grade MVP with three subsystems:

1. **ETL pipeline** (Apache Airflow) — populates a single Postgres + pgvector DB from public data sources.
2. **LangGraph agent** (Gemini) — constrained, typed tools + RAG over reviews, with durable conversation state.
3. **FastAPI + Streamlit** — streaming chat API and a step-by-step chat UI.

---

## ✨ Features

- **Conversational hotel search** — "hotels in NYC under $300, 4+ stars" → ranked results.
- **Dynamic slot-filling** — asks for a location when it's missing; applies price/rating filters when given.
- **Pick & drill in** — select a hotel and ask follow-ups ("is it quiet?", "good for families?"); context persists across turns.
- **Review-grounded answers** — sentiment/aspect Q&A from real guest reviews (hybrid pgvector search), never fabricated.
- **Step-by-step chat UX** — the agent emits messages as actions (`say` / `show_hotels`); the UI streams a loader → cards carousel → answer.
- **Production-grade ETL** — idempotent upserts, raw-payload staging, a monthly API-budget guardrail, and runtime-configurable params.
- **Observability** — LangSmith tracing of every tool call and token.

---

## 🏗️ Architecture

```
                ┌──────────────────────────────┐
                │  Streamlit UI  (:8501)         │  chat, hotel-card carousel
                └───────────────┬───────────────┘
                                │ SSE
                ┌───────────────▼───────────────┐
                │  FastAPI  (:8000)  /chat /health│
                │   └─ LangGraph ReAct agent      │  gemini-2.5-flash
                │        tools: search_locations, │
                │        search_hotels, get_hotel_│
                │        details, search_reviews, │
                │        say, show_hotels         │
                │   └─ Postgres checkpointer       │  durable per-thread state
                └───────────────┬───────────────┘
                                │ psycopg3
                ┌───────────────▼───────────────┐
                │  PostgreSQL 16 + pgvector       │  cities, locations, hotels,
                │  (data DB, host :5433)          │  reviews, review_embeddings
                └───────────────▲───────────────┘
                                │ idempotent upserts
                ┌───────────────┴───────────────┐
                │  Airflow 3 DAG `travel_mitra_etl`│
                │  load_cities → resolve_locations │
                │  → fetch_hotels → fetch_reviews  │
                │  → embed_reviews                 │
                │  (UI :8080, own metadata DB)     │
                └────────────────────────────────┘
```

### Data flow
- **simplemaps CSV** → `cities` (no API).
- **TripAdvisor Content API** (`category=geos`) → `locations` (city → geo id), and `/reviews` → review text.
- **Xotelo API** (free) → `hotels` per location (price range, rating, mentions, image, URL).
- **Gemini `gemini-embedding-001`** (768-dim) → `review_embeddings` for hybrid RAG.

---

## 🧰 Tech stack

| Layer | Tech |
|---|---|
| UI | Streamlit |
| API | FastAPI + SSE (`sse-starlette`) |
| Agent | LangGraph (prebuilt ReAct) + `langchain-google-genai` (**gemini-2.5-flash**) |
| Conversation state | `langgraph-checkpoint-postgres` (AsyncPostgresSaver) |
| Embeddings | Gemini `gemini-embedding-001` (768-dim, via REST) |
| Data layer | **psycopg3** + `pgvector` (no ORM — "code owns the SQL") |
| DB | PostgreSQL 16 + pgvector |
| ETL | Apache Airflow 3 (LocalExecutor) |
| Observability | LangSmith |
| Infra | Docker Compose |

---

## 📁 Repository layout

```
Travel-mitra-2.0/
├─ docker-compose.yml          # full stack: postgres x2, airflow x4, api, ui
├─ .env.example                # required secrets/config
├─ requirements-api.txt        # API image deps
├─ requirements-ui.txt         # UI image deps
├─ requirements-agent.txt      # local venv (notebook + api + ui)
├─ db/migrations/              # 0001_init, 0002_api_tables, 0003_embedding_model (auto-applied)
├─ data/                       # simplemaps uscities CSV (seed)
├─ etl/                        # ETL package (sources, transforms, load, embed, budget)
├─ airflow/
│  ├─ Dockerfile               # Airflow 3 + ETL deps
│  └─ dags/travel_mitra_dag.py # the staged, idempotent DAG
├─ agent/                      # LangGraph agent (tools, queries, graph, prompts, llm)
├─ app/                        # FastAPI app (main, runtime, schemas) + Dockerfile
├─ ui/                         # Streamlit app + Dockerfile
└─ notebooks/01_agent_prototype.ipynb
```

---

## 🚀 Quickstart (Docker)

### Prerequisites
- Docker + Docker Compose
- A **Gemini API key** (https://aistudio.google.com/apikey)
- A **TripAdvisor Content API key** (only needed to *run the ETL*; the demo works on already-loaded data)

### 1. Configure secrets
```bash
cp .env.example .env
```
Fill in `.env`:
```ini
GEMINI_API_KEY=your_gemini_key
TRIPADVISOR_API_KEY=your_tripadvisor_key      # for ETL only
TRIPADVISOR_REFERER=https://your-allowlisted-domain.com   # must match the key's domain restriction
# Optional tracing:
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
```
A Fernet key and an Airflow JWT secret are pre-filled for local dev — rotate for anything non-local.

### 2. Initialize Airflow (first run only)
```bash
docker compose up airflow-init
```

### 3. Bring up the stack
```bash
docker compose up -d
docker compose ps
```

| Service | URL | Notes |
|---|---|---|
| Chat UI | http://localhost:8501 | Streamlit |
| Chat API | http://localhost:8000/health | FastAPI |
| Airflow | http://localhost:8080 | `admin` / `admin` |
| Data DB | `localhost:5433` | `app` / `app` / `travelmitra` |

The data DB schema auto-applies on first volume init (via `docker-entrypoint-initdb.d`).

---

## 🛢️ Running the ETL

1. Open Airflow at http://localhost:8080.
2. Enable & trigger **`travel_mitra_etl`** (▶ *Trigger DAG w/ config*).
3. Tune runtime **params** (all defaulted) — e.g. start small:
   - `top_n_cities = 5`
   - `review_hotels_per_location = 20`

**Stages:** `load_cities → resolve_locations → fetch_hotels → fetch_reviews → embed_reviews`.

Everything is **idempotent** (`ON CONFLICT` upserts) and **budget-aware** (a monthly
TripAdvisor call cap, tracked in `api_call_log`) — re-running never duplicates rows or
re-spends API calls.

> The free TripAdvisor reviews endpoint returns ~5 reviews/hotel; reviews are fetched
> for a price-stratified top-K per city to keep coverage across budget/mid/luxury tiers.

---

## 💬 Using the chat

Open http://localhost:8501 and try:
- *"Hotels in New York under $300, 4+ stars"* → a lead-in + a scrollable card carousel.
- Click **💬 Ask** on a card (or "tell me about the second one") → drills into that hotel.
- *"Is it quiet and good for families?"* → a review-grounded answer.
- Use the sidebar to start a **New chat** or switch between previous conversations (each keeps its own context).

---

## 🧑‍💻 Local development (agent / notebook)

Run the agent or notebook against the containerized DB without rebuilding images:

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements-agent.txt

# Notebook prototype
jupyter notebook notebooks/01_agent_prototype.ipynb

# Or run the API locally (DB at localhost:5433)
uvicorn app.main:app --reload --port 8000

# Or the UI locally
streamlit run ui/streamlit_app.py
```
The agent reads `DATABASE_URL` (default `localhost:5433` on the host) and `GEMINI_API_KEY`
from the environment / `.env`.

---

## ⚙️ Configuration

| Variable | Used by | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | agent, ETL embed | Gemini LLM + embeddings |
| `TRIPADVISOR_API_KEY` | ETL | locations + reviews |
| `TRIPADVISOR_REFERER` | ETL | must match the key's domain allowlist (sent as `Referer`) |
| `DATABASE_URL` | agent/API | data DB DSN (psycopg3) |
| `AGENT_MODEL` | agent | defaults to `gemini-2.5-flash` |
| `LANGSMITH_*` | agent/ETL | optional tracing |
| `TRIPADVISOR_MONTHLY_BUDGET` | ETL (Airflow Variable) | hard call cap (default 4500) |

ETL operational knobs (`top_n_cities`, `review_hotels_per_location`, price tiers, …) are
**DAG params**, overridable per run with sensible defaults.

---

## 🧭 Key design decisions

- **Constrained, typed tools — not a free-form SQL agent.** The LLM picks a tool and fills args; our code owns the SQL. Safe, deterministic, testable.
- **psycopg3, no ORM.** Hybrid vector+metadata queries are clean in raw SQL; same driver as the LangGraph checkpointer.
- **Hybrid review search.** `review_embeddings` denormalizes `location_id / city_id / price / hotel_rating / accommodation_type`, so vector similarity + structured filters run in one query.
- **"Talking is an action."** The agent communicates only via `say()` / `show_hotels()`, emitting messages step by step and stopping at success — the app renders each as its own bubble.
- **Embedding model tracked per row** (`review_embeddings.model`) so a model change can re-embed only stale rows.

---

## 🗺️ Roadmap

- Live date-based pricing via Xotelo `/rates` (an `estimate_stay` tool — schema already supports it).
- Evals (golden Q&A: tool-selection accuracy + answer relevance).
- Test suite (pytest, unit + integration) toward 80% coverage.
- Containerized UI live-reload / CI.

---

## 📝 Notes

- US hotels only, for the cities loaded into the catalog. No booking, availability, or date-specific pricing in v1.
- Secrets live in `.env` (gitignored). Never commit real keys; rotate anything exposed.
