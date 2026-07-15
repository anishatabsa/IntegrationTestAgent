#!/usr/bin/env bash
# ============================================================
# AITA — One-command setup for macOS
# Usage: bash setup-mac.sh
# ============================================================
set -euo pipefail

PYTHON_MIN="3.12"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()    { echo -e "${GREEN}[AITA]${NC} $*"; }
warning() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

info "=== AI Integration Test Agent — macOS Setup ==="

# ── 1. Homebrew ──────────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
  info "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# ── 2. Python 3.12+ ──────────────────────────────────────────────────────────
if ! python3 -c "import sys; assert sys.version_info >= (3, 12)" 2>/dev/null; then
  info "Installing Python 3.12..."
  brew install python@3.12
  export PATH="$(brew --prefix)/opt/python@3.12/bin:$PATH"
fi
info "Python: $(python3 --version)"

# ── 3. Docker Desktop ────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  warning "Docker Desktop not found. Please install from https://www.docker.com/products/docker-desktop"
  warning "After installing Docker, re-run this script."
fi

# ── 4. Virtual environment ────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  info "Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate

# ── 5. Install AITA ───────────────────────────────────────────────────────────
info "Installing AITA and dependencies..."
pip install --upgrade pip -q
pip install -e ".[dev]" -q

# ── 6. .env file ─────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  info ".env created from .env.example — please update your API keys."
fi

# ── 7. Start infrastructure ───────────────────────────────────────────────────
info "Starting infrastructure containers (Redis, Postgres, Qdrant, Ollama, Allure)..."
docker compose up -d aita-redis aita-postgres aita-qdrant aita-ollama aita-allure

# Wait for Postgres
info "Waiting for Postgres..."
until docker compose exec aita-postgres pg_isready -U aita -q 2>/dev/null; do
  sleep 2
done

# ── 8. Database migrations ────────────────────────────────────────────────────
info "Running database migrations..."
alembic upgrade head

# ── 9. Pull default Ollama model ─────────────────────────────────────────────
OLLAMA_MODEL="${OLLAMA_MODEL:-codellama:13b}"
info "Pulling Ollama model: $OLLAMA_MODEL (this may take a while)..."
docker compose exec aita-ollama ollama pull "$OLLAMA_MODEL" || warning "Ollama pull failed — you can retry with: docker compose exec aita-ollama ollama pull $OLLAMA_MODEL"

info ""
info "=== Setup complete! ==="
info ""
info "Start the API server:  uvicorn aita.main:app --reload"
info "Run a pipeline:        aita run <service-name> --branch main"
info "Start worker:          celery -A aita.worker worker --loglevel=info"
info ""
info "API docs:              http://localhost:8080/docs"
info "Allure:                http://localhost:5050"
