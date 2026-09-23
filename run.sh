#!/usr/bin/env bash
# Menjalankan seluruh stack Agentic RAG: database, backend, frontend.
#
#   ./run.sh          jalankan semuanya
#   ./run.sh stop     hentikan semuanya
#   ./run.sh status   cek kondisi tiap service
#   ./run.sh logs     ikuti log backend
#   ./run.sh test     jalankan test backend
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BACKEND_PORT=8001
FRONTEND_PORT=5173
DB_CONTAINER=agentic-rag-ai-db
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.12}"
VENV="$ROOT/backend/.venv"
RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
ok()   { echo "${GREEN}✓${OFF} $*"; }
info() { echo "${DIM}·${OFF} $*"; }
warn() { echo "${YELLOW}!${OFF} $*"; }
die()  { echo "${RED}✗${OFF} $*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "'$1' tidak ditemukan. $2"; }

# --- dependensi host ------------------------------------------------------

check_prereqs() {
  need docker "Install Docker Desktop."
  need ollama "Install dari https://ollama.com"
  need npm    "Install Node.js."
  docker info >/dev/null 2>&1 || die "Docker tidak berjalan. Jalankan Docker Desktop dulu."
  [ -x "$PYTHON_BIN" ] || die "Python 3.12 tidak ada di $PYTHON_BIN. Set PYTHON_BIN=/path/ke/python3.12"
  [ -f .env ] || { cp .env.example .env; ok ".env dibuat dari .env.example"; }
}

# --- database -------------------------------------------------------------

start_db() {
  if docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
    ok "Database sudah berjalan"
  else
    info "Menjalankan PostgreSQL + pgvector..."
    docker compose up -d postgres >/dev/null
  fi

  info "Menunggu database siap..."
  for _ in $(seq 1 30); do
    if docker exec "$DB_CONTAINER" pg_isready -U postgres -d agentic_rag >/dev/null 2>&1; then
      ok "Database siap (port 5433)"
      return
    fi
    sleep 1
  done
  die "Database tidak siap setelah 30 detik. Cek: docker logs $DB_CONTAINER"
}

# --- ollama ---------------------------------------------------------------

LLM_MODEL=$(grep -E '^OLLAMA_LLM_MODEL=' .env | cut -d= -f2-)
EMBED_MODEL=$(grep -E '^OLLAMA_EMBEDDING_MODEL=' .env | cut -d= -f2-)

start_ollama() {
  if ! curl -sf -m 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
    info "Menjalankan Ollama..."
    nohup ollama serve >"$RUN_DIR/ollama.log" 2>&1 &
    for _ in $(seq 1 20); do
      curl -sf -m 2 http://localhost:11434/api/tags >/dev/null 2>&1 && break
      sleep 1
    done
  fi
  curl -sf -m 3 http://localhost:11434/api/tags >/dev/null 2>&1 \
    || die "Ollama tidak merespons di :11434"
  ok "Ollama berjalan"

  for model in "$LLM_MODEL" "$EMBED_MODEL"; do
    if ollama list | awk '{print $1}' | grep -qx "$model"; then
      ok "Model $model tersedia"
    else
      warn "Model $model belum ada, mengunduh (bisa beberapa GB)..."
      ollama pull "$model" || die "Gagal mengunduh $model"
    fi
  done
}

# --- backend --------------------------------------------------------------

setup_venv() {
  if [ ! -x "$VENV/bin/python" ]; then
    info "Membuat virtualenv Python 3.12..."
    "$PYTHON_BIN" -m venv "$VENV"
  fi
  # Reinstall hanya jika requirements.txt lebih baru dari penanda terakhir.
  local stamp="$VENV/.req-installed"
  if [ ! -f "$stamp" ] || [ backend/requirements.txt -nt "$stamp" ]; then
    info "Menginstall dependensi backend (unduhan pertama beberapa menit)..."
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q -r backend/requirements.txt || die "Install dependensi gagal"
    touch "$stamp"
  fi
  ok "Dependensi backend siap"
}

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

start_backend() {
  if port_busy "$BACKEND_PORT"; then
    if curl -sf -m 3 "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1; then
      ok "Backend sudah berjalan (port $BACKEND_PORT)"
      return
    fi
    die "Port $BACKEND_PORT dipakai proses lain. Hentikan dulu, atau ubah BACKEND_PORT di run.sh"
  fi

  info "Menjalankan FastAPI..."
  ( cd backend && nohup "$VENV/bin/uvicorn" main:app --port "$BACKEND_PORT" \
      >"$RUN_DIR/backend.log" 2>&1 & echo $! >"$RUN_DIR/backend.pid" )

  for _ in $(seq 1 30); do
    curl -sf -m 2 "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1 && {
      ok "Backend siap — http://localhost:$BACKEND_PORT/docs"
      return
    }
    sleep 1
  done
  die "Backend gagal start. Log: $RUN_DIR/backend.log"
}

# --- frontend -------------------------------------------------------------

start_frontend() {
  [ -d frontend/node_modules ] || { info "Menginstall dependensi frontend..."; ( cd frontend && npm install ); }
  [ -f frontend/.env ] || echo "VITE_API_URL=http://localhost:$BACKEND_PORT" > frontend/.env

  if port_busy "$FRONTEND_PORT"; then
    ok "Frontend sudah berjalan (port $FRONTEND_PORT)"
    return
  fi

  info "Menjalankan Vite..."
  ( cd frontend && nohup npm run dev -- --port "$FRONTEND_PORT" \
      >"$RUN_DIR/frontend.log" 2>&1 & echo $! >"$RUN_DIR/frontend.pid" )

  for _ in $(seq 1 30); do
    port_busy "$FRONTEND_PORT" && { ok "Frontend siap — http://localhost:$FRONTEND_PORT"; return; }
    sleep 1
  done
  die "Frontend gagal start. Log: $RUN_DIR/frontend.log"
}

# --- perintah -------------------------------------------------------------

cmd_start() {
  check_prereqs
  start_db
  start_ollama
  setup_venv
  start_backend
  start_frontend
  echo
  ok "Semua service berjalan."
  echo "   Aplikasi : http://localhost:$FRONTEND_PORT"
  echo "   API docs : http://localhost:$BACKEND_PORT/docs"
  echo "   Log      : ./run.sh logs     Hentikan: ./run.sh stop"
}

# Hentikan apa pun yang mendengarkan di port tsb. Pidfile saja tidak cukup:
# uvicorn/vite memfork anak, dan service bisa saja distart di luar skrip ini.
stop_port() {
  local name="$1" port="$2"
  local pids; pids=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  rm -f "$RUN_DIR/$name.pid"
  [ -n "$pids" ] || return 0

  kill $pids 2>/dev/null || true
  for _ in $(seq 1 10); do
    port_busy "$port" || { ok "$name dihentikan"; return; }
    sleep 1
  done
  kill -9 $(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null) 2>/dev/null || true
  port_busy "$port" && warn "$name masih hidup di port $port" || ok "$name dihentikan"
}

cmd_stop() {
  stop_port frontend "$FRONTEND_PORT"
  stop_port backend "$BACKEND_PORT"
  docker compose stop postgres >/dev/null 2>&1 && ok "Database dihentikan" || true
  info "Ollama dibiarkan berjalan (dipakai aplikasi lain). Hentikan manual bila perlu."
}

cmd_status() {
  docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER" \
    && ok "Database  : berjalan (5433)" || warn "Database  : mati"
  curl -sf -m 3 http://localhost:11434/api/tags >/dev/null 2>&1 \
    && ok "Ollama    : berjalan (11434)" || warn "Ollama    : mati"
  curl -sf -m 3 "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1 \
    && ok "Backend   : berjalan ($BACKEND_PORT)" || warn "Backend   : mati"
  port_busy "$FRONTEND_PORT" \
    && ok "Frontend  : berjalan ($FRONTEND_PORT)" || warn "Frontend  : mati"
  echo "${DIM}Model LLM: $LLM_MODEL · Embedding: $EMBED_MODEL${OFF}"
}

cmd_logs() { tail -f "$RUN_DIR/backend.log"; }

cmd_test() {
  setup_venv
  ( cd backend && "$VENV/bin/python" -m pytest tests -q )
}

case "${1:-start}" in
  start|"") cmd_start ;;
  stop)     cmd_stop ;;
  restart)  cmd_stop; sleep 2; cmd_start ;;
  status)   cmd_status ;;
  logs)     cmd_logs ;;
  test)     cmd_test ;;
  *)        die "Perintah tidak dikenal: $1 (pakai: start|stop|restart|status|logs|test)" ;;
esac
