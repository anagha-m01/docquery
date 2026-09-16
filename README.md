# DocQuery

LLM-powered document extraction and chat. Upload a PDF, Excel, or CSV file — DocQuery invents a structured schema, extracts the data into it, and lets you ask free-form questions about the document afterward using retrieval-augmented generation (RAG).

---

## Overview

Most extraction tools need a schema defined up front. DocQuery does the opposite: hand it a PDF and an LLM (Groq / Llama 3.1) reads the document and proposes a schema that fits what's actually in it, then extracts the data into that schema — no manual field mapping. Excel/CSV files skip the LLM step entirely, since their structure is already known, and go straight through pandas.

Every chunk (PDF) or row (Excel/CSV) is embedded locally with `sentence-transformers` and stored in Postgres via `pgvector`. That same index powers two things afterward: **re-extraction**, where editing the schema re-runs extraction only against the most relevant chunks/rows instead of the whole document again, and **chat**, where questions about the file are answered from retrieved context rather than the model's general knowledge. Every upload and re-extraction is logged, so a file's full history is queryable later.

## Architecture

```
┌───────────────┐      HTTP (REST/JSON)       ┌───────────────────┐
│   Frontend     │ ───────────────────────────► │     Backend       │
│  React + Vite  │ ◄─────────────────────────── │     FastAPI       │
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
**Orchestration:** Docker Compose

## Features

- Automatic schema invention for PDFs — the LLM proposes a schema from the document's own content, no manual field mapping
- Direct structured parsing for Excel/CSV — skips the LLM entirely since the structure is already known
- Editable schema with cheap re-extraction — pgvector cosine similarity pulls only the relevant chunks/rows instead of reprocessing the whole file
- RAG-based chat over any uploaded file, with conversation history persisted per file so follow-ups have context
- Full upload/re-extraction history, browsable from the sidebar
- Local embeddings via `sentence-transformers` — no per-embedding API cost

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

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/docquery.git
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

**Frontend (`frontend/.env`, or via Docker Compose)**

| Variable | Required | Default | Notes |
|---|---|---|---|
| `VITE_API_URL` | | `http://localhost:8000` | Base URL of the backend API. Docker Compose sets this to `http://localhost:8001` to match the mapped host port |

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

## Known limitations / possible next steps

- **CORS is wide open** (`allow_origins=["*"]`) — fine for local dev, not for a public deploy
- **No auth** — extractions aren't scoped per user; anyone with API access sees everything
- Store original uploaded file bytes (currently only extracted data is kept)
- Postgres full-text search (`tsvector`) combined with pgvector cosine similarity for hybrid keyword + semantic search
- Alembic migrations instead of `CREATE TABLE IF NOT EXISTS`
