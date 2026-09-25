# Synapse

Synapse is a local, provenance-first agentic knowledge engineering platform. The project is being built in eight reviewable steps; the current implementation is **Step 1: system boundaries and health**.

## What exists now

- FastAPI health API
- Next.js system health screen
- PostgreSQL 17 with pgvector through Docker Compose
- Ollama runtime and required-model checks
- Local environment configuration and boundary tests

No ingestion, retrieval, knowledge graph, or agent workflow has been implemented yet.

Synapse exposes its Docker PostgreSQL instance on host port `55432` so it does not conflict with an existing Windows PostgreSQL service on port `5432`.

## Prerequisites

- Docker Desktop
- Node.js 22+
- `uv`
- Ollama with `qwen3.5:9b` and `qwen3-embedding:0.6b`

## Start locally

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
ollama pull qwen3.5:9b
ollama pull qwen3-embedding:0.6b
./scripts/start-backend.ps1
```

In a second terminal:

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:3000`. The API documentation is available at `http://localhost:8000/docs`.

## Verify

```powershell
Set-Location backend
uv sync --python 3.12 --group dev
uv run pytest
uv run ruff check .
```
