# synapse

synapse is a provenance-first agentic rag system for evidence-grounded answers from technical sources.

it combines lexical, vector, and graph retrieval with citations, validation, caching, and bounded verification for reliable answers from technical knowledge.

## start

```powershell
copy-item .env.example .env
docker compose up -d postgres redis
./scripts/start-backend.ps1
```

in a second terminal:

```powershell
set-location frontend
npm.cmd run dev
```

open `http://localhost:5173`.

## verify

```powershell
set-location backend
uv run pytest
uv run ruff check .
```
