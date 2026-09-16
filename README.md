# DocQuery

LLM-powered document extraction and chat. Upload a PDF, Excel, or CSV file — DocQuery invents a structured schema, extracts the data into it, and lets you ask free-form questions about the document afterward using retrieval-augmented generation (RAG).

Live demo: https://docquery-weld.vercel.app
Backend API: https://docquery-9kma.onrender.com

---

## Overview

Most extraction tools need a schema defined up front. DocQuery does the opposite: hand it a PDF and an LLM (Groq / Llama 3.1) reads the document and proposes a schema that fits what's actually in it, then extracts the data into that schema — no manual field mapping. Excel/CSV files skip the LLM step entirely, since their structure is already known, and go straight through pandas.

Every chunk (PDF) or row (Excel/CSV) is embedded locally with `sentence-transformers` and stored in Postgres via `pgvector`. That same index powers two things afterward: **re-extraction**, where editing the schema re-runs extraction only against the most relevant chunks/rows instead of the whole document again, and **chat**, where questions about the file are answered from retrieved context rather than the model's general knowledge. Every upload and re-extraction is logged, so a file's full history is queryable later.

## Architecture

```
┌───────────────┐      HTTPS (REST/JSON)      ┌───────────────────┐
│   Frontend     │ ───────────────────────────► │     Backend       │
│  React + Vite  │ ◄─────────────────────────── │     FastAPI       │
│    (Vercel)    │                               │     (Render)      │
└───────────────┘                               └─────────┬─────────┘
                                                            │
                                ┌───────────────────────────┼───────────────────────────┐
                                ▼                            ▼                           ▼
                        extractor_service            embedding_service              llm_service
                       (pandas · pdfplumber)       (sentence-transformers,        (Groq · Llama 3.1)
                                                       local, no API cost)
                                │                            │                           │
                                └────────────────────────────┼───────────────────────────┘
                                                              ▼
                                                  PostgreSQL + pgvector
                                          (extractions · PDF chunks/rows · chat history)
```

| Layer | Responsibility |
|---|---|
| `routers/` | HTTP layer only — parse the request, call a service, return the response |
| `services/extractor_service.py` | Routes a file to the LLM path (PDF) or the pandas path (Excel/CSV) |
| `services/llm_service.py` | All Groq calls: schema invention, custom-schema re-extraction, RAG chat answers |
| `services/embedding_service.py` | Local embeddings via `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) |
| `services/chat_service.py` | Retrieves top-k relevant chunks/rows and persists the conversation per file |
| `core/database.py` | Postgres + pgvector connection, similarity queries, extraction/chat persistence |

Routers stay thin and services don't know anything about HTTP — this keeps FastAPI-specific code out of the business logic and makes each piece testable on its own.

## Tech stack

**Backend:** FastAPI, Groq API (LLM inference), pdfplumber (PDF text extraction), pandas + openpyxl (direct Excel/CSV parsing), sentence-transformers (local embeddings), psycopg2 + pgvector (Postgres vector search)
**Frontend:** React 19, Vite, Axios, react-syntax-highlighter
**Testing:** Vitest + React Testing Library (frontend)
**Orchestration:** Docker Compose (local), Render + Vercel (hosted)

## Features

- Automatic schema invention for PDFs — the LLM proposes a schema from the document's own content, no manual field mapping
- Direct structured parsing for Excel/CSV — skips the LLM entirely since the structure is already known
- Editable schema with cheap re-extraction — pgvector cosine similarity pulls only the relevant chunks/rows instead of reprocessing the whole file
- RAG-based chat over any uploaded file, with conversation history persisted per file so follow-ups have context
- Full upload/re-extraction history, browsable from the sidebar
- Local embeddings via `sentence-transformers` — no per-embedding API cost

## Security & production readiness

- **CORS is locked to an explicit allowlist** — no wildcard origin. The deployed Vercel frontend is allowed by default, extendable via the `ALLOWED_ORIGINS` env var (comma-separated) without a code change.
- **No secrets in git** — `.env.example` documents every variable; real keys stay in `.env` / the host's environment dashboard.
- **Groq key required at startup** — a missing `GROQ_API_KEY` fails fast instead of erroring on the first request.

## Testing

```bash
# backend (28 tests: routers, chat_service, excel_parser — Postgres/Groq are mocked, no live services needed)
cd backend && pip install -r requirements-dev.txt && pytest -q

# frontend
cd frontend && npm install && npm test
```

Both suites run automatically on every push via GitHub Actions (`.github/workflows/ci.yml`), including a full `npm run build` to catch build-breaking changes before merge.

## Project structure

```
backend/
  app/
    main.py             # FastAPI app factory — wiring only
    core/
      config.py          # all env vars, read once, imported everywhere
      database.py        # postgres + pgvector connection & queries
    routers/              # HTTP layer — request/response only
      extract.py
      reextract.py
      extractions.py
      chat.py
    services/              # business logic, no HTTP awareness
      extractor_service.py
      llm_service.py
      embedding_service.py
      chat_service.py
    schemas/               # pydantic request/response models
      extraction.py
    utils/
      pdf_parser.py
      excel_parser.py
  tests/                   # pytest suite (routers, chat_service, excel_parser)
  requirements.txt
  requirements-dev.txt
frontend/                  # React SPA (Vite)
  src/
    main.jsx
    App.jsx
    components/
      Upload.jsx
      SchemaEditor.jsx
      Result.jsx
      Chat.jsx
      Sidebar.jsx
.github/workflows/ci.yml
docker-compose.yml
```

## Installation (local development)

### 1. Clone the repository

```bash
git clone https://github.com/anagha-m01/docquery.git
cd docquery
```

### 2. Quick start (Docker Compose — recommended)

```bash
cp .env.example .env       # then add your GROQ_API_KEY
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8001
- API docs (Swagger): http://localhost:8001/docs

### 3. Manual local development (optional)

Useful if you want fast reload on the backend without rebuilding a container each time.

Start just the database via Docker:

```bash
docker compose up db
```

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
cp ../.env.example .env
```

Edit `.env` — since Postgres is reached at `localhost` now instead of the Docker service name `db`, override:

```
POSTGRES_HOST=localhost
GROQ_API_KEY=your_key_here
```

Run it:

```bash
uvicorn app.main:app --reload
```

API is now live at `http://127.0.0.1:8000` — Swagger docs at `http://127.0.0.1:8000/docs`.

Frontend:

```bash
cd frontend
npm install
npm run dev
```

App is now live at `http://localhost:3000`, calling the backend at `http://localhost:8000` by default (set `VITE_API_URL` to override).

## Environment variables

**Backend (`.env`, or `backend/.env` for manual dev)**

| Variable | Required | Default | Notes |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ | — | Needed for PDF schema invention, re-extraction, and chat |
| `LLM_MODEL` | | `groq/compound-mini` | Any current Groq-supported model |
| `POSTGRES_HOST` | | `db` | Set to `localhost` for manual (non-Docker) backend dev |
| `POSTGRES_PORT` | | `5432` | |
| `POSTGRES_DB` | | `docquery_db` | |
| `POSTGRES_USER` | | `postgres` | |
| `POSTGRES_PASSWORD` | | `postgres` | |
| `EMBEDDING_MODEL` | | `all-MiniLM-L6-v2` | Not in `.env.example`, but overridable |
| `TOP_K_PDF` / `TOP_K_EXCEL` / `TOP_K_CHAT` | | `4` / `100` / `5` | Chunks/rows retrieved per re-extraction or chat turn |
| `ALLOWED_ORIGINS` | production only | `https://docquery-weld.vercel.app` + localhost | Comma-separated; must exactly match your deployed frontend URL |

**Frontend (`frontend/.env`, or via Docker Compose)**

| Variable | Required | Default | Notes |
|---|---|---|---|
| `VITE_API_URL` | production only | `http://localhost:8000` | Base URL of the deployed backend API |

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/extract` | Upload a file, get structured data back |
| POST | `/reextract` | Re-extract with an edited schema |
| GET | `/extractions` | List upload history |
| GET | `/extractions/{id}` | Get one extraction |
| POST | `/chat` | Ask a question about an uploaded file |
| GET | `/chat/{extraction_id}` | Get chat history for a file |

## Usage

1. Upload a PDF, Excel, or CSV file.
2. Review the schema DocQuery invented (PDFs) or inferred from the columns (Excel/CSV).
3. Edit the schema and re-extract if the first pass missed or mis-typed a field.
4. Ask questions about the file in the chat panel — answers are grounded in retrieved content, not guesses.
5. Revisit any past upload from the history sidebar; its data and chat thread pick back up where you left off.

## Deployment

This is a two-part deploy: **backend + Postgres/pgvector on Render**, **frontend on Vercel**.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/anagha-m01/docquery)
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/anagha-m01/docquery&root-directory=frontend)

**Backend (Render, free tier):**

1. Push this repo to GitHub.
2. Create a Postgres database on Render, then enable pgvector on it (`CREATE EXTENSION IF NOT EXISTS vector;` via psql).
3. Create a new Web Service pointing at this repo, root directory `backend`.
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables in Render's dashboard: `GROQ_API_KEY`, `POSTGRES_HOST`/`PORT`/`DB`/`USER`/`PASSWORD` (from the database's Connections panel), and (once you know it) `ALLOWED_ORIGINS=https://your-app.vercel.app`. The rest have working defaults — see the table above.
7. Deploy, then confirm `https://<your-render-url>/` returns `{"status": "ok", "service": "DocQuery API"}`.

**Frontend (Vercel, free tier):**

1. Import this repo, root directory `frontend`.
2. Framework preset: Vite.
3. Add environment variable `VITE_API_URL` set to your deployed Render backend URL (e.g. `https://docquery-9kma.onrender.com`).
4. Deploy.
5. Go back to Render and set `ALLOWED_ORIGINS` to your new Vercel URL (exact match, no trailing slash), then redeploy the backend — CORS will reject the frontend until this matches.

**Why this order matters:** the frontend needs the backend's URL to call it, and the backend needs the frontend's URL to allow it through CORS — so the backend gets redeployed once at the end with the real Vercel URL filled in.

**Known limitation:** Render's free Postgres tier expires after 30 days and the web service spins down on idle (cold start on the first request after inactivity). Fine for a demo; a production deploy would move to a paid Postgres plan and an always-on web service tier.

## Known limitations / possible next steps

- **No auth** — extractions aren't scoped per user; anyone with API access sees everything
- Store original uploaded file bytes (currently only extracted data is kept)
- Postgres full-text search (`tsvector`) combined with pgvector cosine similarity for hybrid keyword + semantic search
- Alembic migrations instead of `CREATE TABLE IF NOT EXISTS`
