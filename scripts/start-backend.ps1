$ErrorActionPreference = "Stop"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot "..\tmp\uv-python"
Set-Location (Join-Path $PSScriptRoot "..\backend")
uv run --python 3.12 uvicorn synapse.main:app --reload --port 8000

