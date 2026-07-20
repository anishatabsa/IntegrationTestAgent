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
# Strategy: search known Homebrew locations directly — avoids symlink/permission
# issues that occur when `brew link` requires writing to /usr/local/Frameworks.
find_python312() {
  local candidates=(
    # Homebrew opt symlink (Intel Mac)
    "/usr/local/opt/python@3.12/bin/python3.12"
    # Homebrew opt symlink (Apple Silicon)
    "/opt/homebrew/opt/python@3.12/bin/python3.12"
    # Cellar direct paths — covers unlinked installs
    /usr/local/Cellar/python@3.12/*/bin/python3.12
    /opt/homebrew/Cellar/python@3.12/*/bin/python3.12
    # pyenv
    "$HOME/.pyenv/versions/3.12"*/bin/python3.12
  )
  for p in "${candidates[@]}"; do
    # glob expansion may yield no matches — skip non-executable entries
    [ -x "$p" ] && echo "$p" && return 0
  done
  return 1
}

PYTHON=""
# 1. Check if active python3 is already 3.12+
if python3 -c "import sys; assert sys.version_info >= (3, 12)" 2>/dev/null; then
  PYTHON="python3"
  info "System python3 is 3.12+: $(python3 --version)"
# 2. Search known Homebrew/pyenv locations
elif PYTHON=$(find_python312); then
  info "Found Python 3.12: $PYTHON ($($PYTHON --version))"
# 3. Install via Homebrew as last resort
else
  info "Python 3.12 not found — installing via Homebrew..."
  brew install python@3.12
  if PYTHON=$(find_python312); then
    info "Installed: $($PYTHON --version)"
  else
    error "Could not locate python3.12 after install.\nTry: sudo chmod -R a+rX /usr/local/Frameworks && brew link python@3.12"
  fi
fi
info "Using Python: $($PYTHON --version) at $PYTHON"

# ── 3. Docker ────────────────────────────────────────────────────────────────
# Prefer Docker Desktop; fall back to Colima if Docker is missing or broken.
ensure_docker() {
  # Quick sanity-check: can the docker binary run at all?
  if command -v docker &>/dev/null && docker --version &>/dev/null 2>&1; then
    # Binary works — check daemon
    if docker info &>/dev/null 2>&1; then
      info "Docker is running."
      return 0
    fi

    # Daemon not running — try Docker Desktop first
    if [ -d "/Applications/Docker.app" ]; then
      info "Launching Docker Desktop..."
      open -a Docker
      local wait=0
      until docker info &>/dev/null 2>&1; do
        sleep 3; wait=$((wait+3)); echo -n "."
        [ "$wait" -ge 90 ] && break
      done
      echo ""
      docker info &>/dev/null 2>&1 && { info "Docker Desktop ready."; return 0; }
    fi

    # Docker Desktop failed or killed — offer Colima
    warning "Docker Desktop appears broken (binary is killed or daemon won't start)."
  else
    warning "No docker binary found on PATH."
  fi

  # ── Colima fallback ──────────────────────────────────────────────────────
  # Helper: find a binary in Homebrew Cellar/opt when brew link fails
  # (brew link often fails on macOS because /usr/local/share/fish is not writable)
  symlink_brew_bin() {
    local formula="$1"
    # Try opt symlink first (more stable), then glob Cellar
    local opt_bin="/usr/local/opt/${formula}/bin"
    local arm_opt_bin="/opt/homebrew/opt/${formula}/bin"
    local src_dir=""
    if [ -d "$opt_bin" ]; then
      src_dir="$opt_bin"
    elif [ -d "$arm_opt_bin" ]; then
      src_dir="$arm_opt_bin"
    else
      # Fall back to newest Cellar version
      local cellar_glob="/usr/local/Cellar/${formula}/*/bin"
      for d in $cellar_glob; do
        [ -d "$d" ] && src_dir="$d" && break
      done
      local arm_cellar_glob="/opt/homebrew/Cellar/${formula}/*/bin"
      for d in $arm_cellar_glob; do
        [ -d "$d" ] && src_dir="$d" && break
      done
    fi
    if [ -n "$src_dir" ] && [ -d "$src_dir" ]; then
      for f in "$src_dir"/*; do
        [ -x "$f" ] || continue
        local target="/usr/local/bin/$(basename "$f")"
        [ -e "$target" ] || ln -sf "$f" "$target" && true
      done
    fi
  }

  if command -v colima &>/dev/null && colima status 2>/dev/null | grep -q "Running"; then
    info "Colima is already running — using it as Docker host."
    return 0
  fi

  info "Attempting to install/start Colima (lightweight Docker for macOS)..."
  brew install colima lima docker docker-compose docker-credential-helper 2>/dev/null || true

  # brew link often fails due to fish completions dir permissions.
  # Auto-symlink the binaries from the Cellar so they're on PATH.
  for formula in colima lima docker docker-compose; do
    if ! command -v "$formula" &>/dev/null; then
      symlink_brew_bin "$formula"
    fi
  done
  # lima ships multiple binaries (limactl, lima, etc.) — symlink all of them
  symlink_brew_bin "lima"

  # Replace Docker Desktop's docker-credential-osxkeychain (gets SIGKILL'd) with
  # the Homebrew version. The Docker Desktop binary may already be symlinked at
  # /usr/local/bin/docker-credential-osxkeychain — overwrite it.
  symlink_brew_bin "docker-credential-helper"
  local CREDHELPER_CELLAR
  CREDHELPER_CELLAR="$(ls -d /usr/local/Cellar/docker-credential-helper/*/bin/docker-credential-osxkeychain 2>/dev/null | tail -1)"
  if [ -n "$CREDHELPER_CELLAR" ] && [ -x "$CREDHELPER_CELLAR" ]; then
    ln -sf "$CREDHELPER_CELLAR" /usr/local/bin/docker-credential-osxkeychain
    info "Replaced Docker Desktop credential helper with Homebrew version."
  fi

  # Find colima regardless of whether brew link worked
  local COLIMA_BIN
  COLIMA_BIN="$(command -v colima 2>/dev/null \
    || echo /usr/local/opt/colima/bin/colima \
    || echo /opt/homebrew/opt/colima/bin/colima)"

  if [ -x "$COLIMA_BIN" ]; then
    info "Starting Colima VM (cpu=4, mem=8GB, disk=60GB)..."
    "$COLIMA_BIN" start --cpu 4 --memory 8 --disk 60 2>/dev/null \
      || "$COLIMA_BIN" start 2>/dev/null \
      || error "Colima failed to start.\nTry manually: colima start --cpu 4 --memory 8 --disk 60\nOr install Docker Desktop: https://www.docker.com/products/docker-desktop"
    info "Colima started."
  else
    error "Could not install Colima via Homebrew.\nInstall Docker Desktop manually:\nhttps://www.docker.com/products/docker-desktop\nThen re-run: bash setup-mac.sh"
  fi
}

ensure_docker

# ── 3b. Fix Docker credential helper ─────────────────────────────────────────
# Docker Desktop installs a credential helper (docker-credential-desktop) that
# gets SIGKILL'd on machines where Docker Desktop itself is broken or removed.
# Strip credsStore/credHelpers from ~/.docker/config.json so docker pull works.
DOCKER_CFG="$HOME/.docker/config.json"
mkdir -p "$HOME/.docker"
if [ ! -f "$DOCKER_CFG" ]; then
  echo '{}' > "$DOCKER_CFG"
fi
python3 - <<'PYEOF'
import json, os, sys
cfg = os.path.expanduser("~/.docker/config.json")
try:
    with open(cfg) as f:
        data = json.load(f)
except Exception:
    data = {}
changed = False
for key in ("credsStore", "credHelpers"):
    if key in data:
        del data[key]
        changed = True
if changed:
    with open(cfg, "w") as f:
        json.dump(data, f, indent=2)
    print("[AITA] Removed broken Docker credential helper from config.")
PYEOF

# ── 4. Virtual environment ────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  info "Creating virtual environment with Python 3.12..."
  "$PYTHON" -m venv .venv
elif ! .venv/bin/python -c "import sys; assert sys.version_info >= (3, 12)" 2>/dev/null; then
  warning "Existing .venv is not Python 3.12 — recreating..."
  rm -rf .venv
  "$PYTHON" -m venv .venv
fi
source .venv/bin/activate
info "venv Python: $(python --version)"

# ── 5. Install AITA ───────────────────────────────────────────────────────────
info "Installing AITA and dependencies..."

# Upgrade pip + install build tools first
pip install --upgrade pip setuptools wheel -q

# Pre-install cryptography from a binary wheel.
# cryptography's build system (maturin) tries to download Rust if no wheel is
# available — this fails in restricted network environments. Forcing --only-binary
# ensures pip uses the pre-compiled wheel that ships on PyPI for macOS/Python 3.12.
info "Installing cryptography binary wheel (avoids Rust build)..."
pip install --only-binary=:all: cryptography -q

# Install AITA + all dependencies
pip install -e ".[dev]" -q

# ── 6. .env file ─────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  info ".env created from .env.example — please update your API keys."
fi

# ── 7. Docker Compose plugin setup ───────────────────────────────────────────
# Wire docker-compose as a Docker CLI plugin so both `docker compose` and
# `docker-compose` work. Homebrew installs the binary but doesn't register it
# as a plugin automatically.
COMPOSE_PLUGIN_DIR="$HOME/.docker/cli-plugins"
mkdir -p "$COMPOSE_PLUGIN_DIR"
COMPOSE_BIN="$(command -v docker-compose 2>/dev/null || echo '')"
if [ -n "$COMPOSE_BIN" ] && [ ! -f "$COMPOSE_PLUGIN_DIR/docker-compose" ]; then
  ln -sf "$COMPOSE_BIN" "$COMPOSE_PLUGIN_DIR/docker-compose"
  info "Registered docker-compose as Docker CLI plugin."
fi

# Choose compose command: prefer plugin, fall back to standalone
if docker compose version &>/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose &>/dev/null; then
  DC="docker-compose"
else
  error "Neither 'docker compose' nor 'docker-compose' is available."
fi
info "Using compose: $DC"

# ── 8. Start infrastructure ───────────────────────────────────────────────────
# Ollama is skipped by default — it's large and optional (uses Anthropic API).
# To enable: add aita-ollama to the list below or run it separately.
info "Starting infrastructure containers (Redis, Postgres, Qdrant, Allure)..."
$DC up -d aita-redis aita-postgres aita-qdrant aita-allure

# Wait for Postgres
info "Waiting for Postgres..."
until $DC exec aita-postgres pg_isready -U aita -q 2>/dev/null; do
  sleep 2
done

# ── 9. Database migrations ────────────────────────────────────────────────────
info "Running database migrations..."
alembic upgrade head

# ── 10. Pull default Ollama model ────────────────────────────────────────────
OLLAMA_MODEL="${OLLAMA_MODEL:-codellama:13b}"
info "Ollama container is not started by default (saves memory)."
info "To use local LLMs: $DC up -d aita-ollama && $DC exec aita-ollama ollama pull $OLLAMA_MODEL"
info "Or set LLM_PROVIDER=anthropic in .env to use the Anthropic API instead."

info ""
info "=== Setup complete! ==="
info ""
info "Start the API server:  uvicorn aita.main:app --reload"
info "Run a pipeline:        aita run <service-name> --branch main"
info "Start worker:          celery -A aita.worker worker --loglevel=info"
info ""
info "API docs:              http://localhost:8080/docs"
info "Allure:                http://localhost:5050"
