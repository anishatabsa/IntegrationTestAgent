# ============================================================
# AITA — One-command setup for Windows (PowerShell)
# Usage: .\setup-windows.ps1
# Run as: PowerShell -ExecutionPolicy Bypass -File setup-windows.ps1
# ============================================================
$ErrorActionPreference = "Stop"

function Info    { param($msg) Write-Host "[AITA] $msg" -ForegroundColor Green }
function Warning { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Error   { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

Info "=== AI Integration Test Agent — Windows Setup ==="

# ── 1. Check Python 3.12+ ─────────────────────────────────────────────────────
try {
    $pyVer = python --version 2>&1
    if ($pyVer -notmatch "Python 3\.(1[2-9]|[2-9]\d)") {
        throw "Version too old"
    }
    Info "Found: $pyVer"
} catch {
    Warning "Python 3.12+ not found. Installing via winget..."
    winget install Python.Python.3.12 --silent
    $env:PATH = "$env:LOCALAPPDATA\Programs\Python\Python312;$env:PATH"
}

# ── 2. Check Docker Desktop ──────────────────────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Warning "Docker Desktop not found. Install from https://www.docker.com/products/docker-desktop"
    Warning "After installing, re-run this script."
}

# ── 3. Virtual environment ────────────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
    Info "Creating virtual environment..."
    python -m venv .venv
}
& ".venv\Scripts\Activate.ps1"

# ── 4. Install AITA ──────────────────────────────────────────────────────────
Info "Installing AITA and dependencies..."
pip install --upgrade pip -q
pip install -e ".[dev]" -q

# ── 5. .env file ─────────────────────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Info ".env created — please update your API keys."
}

# ── 6. Start infrastructure ───────────────────────────────────────────────────
Info "Starting infrastructure containers..."
docker compose up -d aita-redis aita-postgres aita-qdrant aita-ollama aita-allure

# Wait for Postgres
Info "Waiting for Postgres..."
$retries = 30
while ($retries -gt 0) {
    $result = docker compose exec aita-postgres pg_isready -U aita -q 2>&1
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep 2
    $retries--
}
if ($retries -eq 0) { Warning "Postgres may not be ready. Proceeding anyway..." }

# ── 7. Database migrations ────────────────────────────────────────────────────
Info "Running database migrations..."
alembic upgrade head

# ── 8. Pull default Ollama model ─────────────────────────────────────────────
$ollamaModel = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "codellama:13b" }
Info "Pulling Ollama model: $ollamaModel ..."
docker compose exec aita-ollama ollama pull $ollamaModel

Info ""
Info "=== Setup complete! ==="
Info ""
Info "Start the API server:  uvicorn aita.main:app --reload"
Info "Run a pipeline:        aita run <service-name> --branch main"
Info "Start worker:          celery -A aita.worker worker --loglevel=info"
Info ""
Info "API docs:              http://localhost:8080/docs"
Info "Allure:                http://localhost:5050"
