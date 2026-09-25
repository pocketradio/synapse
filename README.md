# synapse

Synapse is a local, provenance-first knowledge engineering platform for building evidence-grounded answers from technical sources.

## stack

- fastapi backend
- postgresql with pgvector
- ollama with a chat model and an embedding model

## prerequisites

- docker desktop
- node.js 22+
- uv
- ollama

## start

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

Open `http://localhost:3000`.

## api

- `GET /api/health`
- `GET /api/knowledge/summary`
- `GET /api/knowledge/chunks/{id}`

## verify

```powershell
Set-Location backend
uv sync --python 3.12 --group dev
uv run pytest
uv run ruff check .
```
