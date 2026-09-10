# DocQuery

LLM-powered document extraction and chat. Upload a PDF, Excel, or CSV file —
DocQuery invents a structured schema, extracts the data into it, and lets you
ask free-form questions about the document afterward using retrieval-augmented
generation (RAG).

## How it works

1. **Upload** (`POST /extract`) — a PDF is chunked and sent to an LLM (Groq /
   Llama 3.1) which invents a schema and extracts structured data from it.
   Excel/CSV files are parsed directly with pandas (no LLM needed — the
   structure is already known). Every chunk (PDF) or row (Excel) is embedded
   with `sentence-transformers` and stored in Postgres via `pgvector`.
2. **Re-extract** (`POST /reextract`) — edit the schema after the fact.
   DocQuery embeds your new schema, uses `pgvector` cosine similarity to pull
   only the most relevant chunks/rows, and re-runs extraction against just
   those — cheaper and more accurate than reprocessing the whole document.
3. **Chat** (`POST /chat`) — ask a question about an uploaded file in plain
   English. The question is embedded, the most relevant chunks/rows are
   retrieved from `pgvector` (same mechanism as re-extract), and the LLM
   answers using only that retrieved context. Conversation history is
   persisted per file so follow-up questions work.
4. **History** (`GET /extractions`) — every upload and re-extraction is
   logged in Postgres with its schema, data, and timestamp.

## Architecture

```
backend/
  app/
    main.py            # FastAPI app factory — wiring only
    core/
      config.py         # all env vars, read once, imported everywhere
      database.py        # postgres + pgvector connection & queries
    routers/            # HTTP layer — request/response only
      extract.py
      reextract.py
      extractions.py
      chat.py
    services/            # business logic, no HTTP awareness
      extractor_service.py
      llm_service.py
      embedding_service.py
      chat_service.py
    schemas/             # pydantic request/response models
      extraction.py
    utils/
      pdf_parser.py
      excel_parser.py
frontend/                # React SPA (upload, schema editor, results)
docker-compose.yml
```

Routers stay thin (parse the request, call a service, return the response).
Services hold the actual logic and don't know anything about HTTP. This keeps
the FastAPI-specific code out of the business logic, and makes each piece
testable on its own.

## Stack

- **FastAPI** — API
- **PostgreSQL + pgvector** — persistence and vector similarity search
- **Groq (Llama 3.1)** — schema invention, extraction, chat
- **sentence-transformers** (`all-MiniLM-L6-v2`) — local embeddings, no API cost
- **React** — frontend
- **Docker Compose** — local orchestration

## Running locally

```bash
cp .env.example .env       # then add your GROQ_API_KEY
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000
- API docs (Swagger): http://localhost:8000/docs

## API

| Method | Path                      | Purpose                                  |
|--------|---------------------------|-------------------------------------------|
| POST   | `/extract`                | Upload a file, get structured data back  |
| POST   | `/reextract`               | Re-extract with an edited schema         |
| GET    | `/extractions`             | List upload history                      |
| GET    | `/extractions/{id}`        | Get one extraction                       |
| POST   | `/chat`                    | Ask a question about an uploaded file    |
| GET    | `/chat/{extraction_id}`    | Get chat history for a file              |

## Possible next steps

- Store original uploaded file bytes (currently only extracted data is kept)
- Postgres full-text search (`tsvector`) combined with pgvector cosine
  similarity for hybrid keyword + semantic search
- Auth, so extractions are scoped per user
- Alembic migrations instead of `CREATE TABLE IF NOT EXISTS`
