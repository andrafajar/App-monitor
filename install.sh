#!/usr/bin/env bash
# NetPulse one-shot installer (Ubuntu/Debian). Installs Docker if missing, generates secrets, builds and starts everything.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\033[1;36m[netpulse]\033[0m %s\n' "$*"; }
rand() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "$1"; }

if ! command -v docker >/dev/null 2>&1; then
  say "Docker not found — installing via get.docker.com"
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER" || true
fi
if ! docker compose version >/dev/null 2>&1; then
  say "Installing docker compose plugin"
  sudo apt-get update -y && sudo apt-get install -y docker-compose-plugin
fi

if [ ! -f .env ]; then
  say "Generating .env with fresh secrets"
  FERNET=$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())" 2>/dev/null || docker run --rm python:3.11-slim python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  ADMIN_PW="Np-$(rand 12)"
  cat > .env <<EOF
DB_NAME=netpulse
CORS_ORIGINS=*
NETPULSE_PORT=${NETPULSE_PORT:-8080}
CREDENTIALS_FERNET_KEY=${FERNET}
JWT_SECRET=$(rand 64)
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@netpulse.local}
ADMIN_PASSWORD=${ADMIN_PW}
EMERGENT_LLM_KEY=${EMERGENT_LLM_KEY:-}
EOF
  say "Super Admin login → ${ADMIN_EMAIL:-admin@netpulse.local} / ${ADMIN_PW}  (saved in .env, change it after first login)"
else
  say "Using existing .env"
fi

say "Building images and starting services (first run takes a few minutes)"
docker compose up -d --build

PORT=$(grep -E '^NETPULSE_PORT=' .env | cut -d= -f2)
say "Waiting for backend health..."
for _ in $(seq 1 40); do
  if curl -fsS "http://localhost:${PORT:-8080}/api/health" >/dev/null 2>&1; then break; fi
  sleep 3
done
say "NetPulse is up: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT:-8080}"
say "Logs: docker compose logs -f   ·   Update: git pull && docker compose up -d --build"
