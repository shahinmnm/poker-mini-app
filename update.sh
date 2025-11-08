#!/bin/bash
# =============================================================================
# Poker Mini App — Deploy & Clean (Visual, Minimal, Space-Aware)
# =============================================================================
# - Pulls target branch from https://github.com/shahinmnm/poker-mini-app
# - Preserves local .env
# - Aggressive Docker cleanup before/after build
# - Compact, readable status UI + quick commands
#
# Usage:
#   ./update.sh                 # default branch = main
#   ./update.sh -b staging      # deploy another branch
#   BRANCH=prod ./update.sh     # env override
#   KEEP_VOLUMES=1 ./update.sh  # keep volumes (DB data)
#   ./update.sh -h              # help
# =============================================================================

set -euo pipefail

# ---------- Config ----------
REPO_URL="https://github.com/shahinmnm/poker-mini-app.git"
PROJECT_DIR="/Poker-Bot"                 # adjust if needed
BRANCH="${BRANCH:-main}"                 # default target branch
KEEP_VOLUMES="${KEEP_VOLUMES:-0}"        # 1 = keep volumes

# ---------- UI ----------
C_RESET='\033[0m'
C_BLUE='\033[1;34m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[1;33m'
C_RED='\033[0;31m'
BOLD='\033[1m'

box() {  # fancy section header
  local msg="$1"
  echo -e "\n${C_BLUE}╔════════════════════════════════════════════════════════════╗${C_RESET}"
  printf   "${C_BLUE}║${C_RESET} %-58s ${C_BLUE}║${C_RESET}\n" "$msg"
  echo -e   "${C_BLUE}╚════════════════════════════════════════════════════════════╝${C_RESET}\n"
}
ok()    { echo -e "${C_GREEN}✓${C_RESET} $*"; }
warn()  { echo -e "${C_YELLOW}⚠${C_RESET} $*"; }
err()   { echo -e "${C_RED}✗${C_RESET} $*"; }
say()   { echo -e "${C_BLUE}${BOLD}$*${C_RESET}"; }
hr()    { echo -e "${C_BLUE}────────────────────────────────────────────────────────────${C_RESET}"; }

disk()  { df -h / | awk 'NR==2{printf "%s used of %s (%s full)\n",$3,$2,$5}'; }

help() {
  cat <<EOF
Usage:
  ./update.sh                 # deploy main
  ./update.sh -b <branch>     # deploy selected branch
  BRANCH=<branch> ./update.sh # env override
  KEEP_VOLUMES=1 ./update.sh  # keep volumes during cleanup
  ./update.sh -h              # help
EOF
}

# ---------- Args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -b|--branch) shift; BRANCH="${1:?branch name required}"; shift;;
    -h|--help) help; exit 0;;
    *) err "Unknown arg: $1"; exit 2;;
  esac
done

# ---------- Helpers ----------
dc() { if docker compose version >/dev/null 2>&1; then docker compose "$@"; else docker-compose "$@"; fi; }

# ---------- Preflight ----------
box "Preflight"
command -v docker >/dev/null || { err "Docker missing"; exit 1; }
(docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null) || { err "Docker Compose missing"; exit 1; }
ok "Docker and Compose available"
say "Disk: $(disk)"

# ---------- Repo sync ----------
box "Source Sync • repo=$REPO_URL • branch=$BRANCH"
if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  warn "Repo not found at $PROJECT_DIR → fresh clone"
  rm -rf "$PROJECT_DIR" || true
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
else
  cd "$PROJECT_DIR"
  git remote set-url origin "$REPO_URL"
  [[ -f .env ]] && cp -f .env .env.local.keep
  git fetch --prune --tags --depth=1 origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git switch "$BRANCH"
  else
    git switch -c "$BRANCH" --track "origin/$BRANCH"
  fi
  git reset --hard "origin/$BRANCH"
  if [[ -f .env.local.keep ]]; then cp -f .env.local.keep .env; rm -f .env.local.keep; fi
fi
cd "$PROJECT_DIR"
ok "Code at $(git rev-parse --short HEAD)"

# ---------- Validate ----------
box "Validation"
for f in docker-compose.yml webapp-backend/Dockerfile webapp-frontend/Dockerfile; do
  [[ -f "$f" ]] || { err "Missing $f"; exit 1; }
done
[[ -f .env ]] || { err ".env missing. Create it before deploy."; exit 1; }
ok "Compose + Dockerfiles present"
ok ".env present"

# ---------- Pre-build cleanup ----------
box "Pre-Build Cleanup (aggressive)"
dc down --remove-orphans || true
docker image prune -af  >/dev/null 2>&1 || true
docker builder prune -af >/dev/null 2>&1 || true
docker network prune -f  >/dev/null 2>&1 || true
if [[ "$KEEP_VOLUMES" -ne 1 ]]; then docker volume prune -f >/dev/null 2>&1 || true; else warn "KEEP_VOLUMES=1 → skipping volume prune"; fi

LOG_DIR="/var/lib/docker/containers"
if [[ -d "$LOG_DIR" ]]; then
  sudo find "$LOG_DIR" -name "*.log" -size +50M -exec truncate -s 0 {} + 2>/dev/null || true
fi
find . -type d -name node_modules -prune -exec rm -rf {} + 2>/dev/null || true
find . -type d \( -name dist -o -name build -o -name .next -o -name .cache \) -prune -exec rm -rf {} + 2>/dev/null || true
find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} + 2>/dev/null || true
npm  cache clean --force >/dev/null 2>&1 || true
yarn cache clean        >/dev/null 2>&1 || true
pnpm store prune        >/dev/null 2>&1 || true
pip  cache purge        >/dev/null 2>&1 || true
ok "Workspace and Docker caches purged"
say "Disk now: $(disk)"

# ---------- Build & Run ----------
box "Build"
dc build --no-cache --parallel
ok "Images built"

box "Start"
dc up -d
warn "Warm-up 10s..."
sleep 10
ok "Compose up"

# ---------- Health checks ----------
box "Health Checks"
if dc exec -T redis redis-cli ping >/dev/null 2>&1; then ok "Redis: healthy"; else warn "Redis: not ready"; fi

# API: Check via docker exec since port 8000 is not exposed to host
if dc exec -T webapp-api python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=5)" >/dev/null 2>&1; then 
  ok "API: healthy"; 
else 
  warn "API: not ready"; 
fi

# Frontend: Check on port 8080 (default) with /nginx-health endpoint
FRONTEND_PORT="${WEBAPP_FRONTEND_PORT:-8080}"
if curl -fsS "http://localhost:${FRONTEND_PORT}/nginx-health" >/dev/null 2>&1; then 
  ok "Frontend: healthy"; 
else 
  warn "Frontend: not ready"; 
fi

# ---------- Post-build cleanup ----------
box "Post-Build Cleanup"
docker image prune -af  >/dev/null 2>&1 || true
docker builder prune -af >/dev/null 2>&1 || true
docker network prune -f  >/dev/null 2>&1 || true
if [[ "$KEEP_VOLUMES" -ne 1 ]]; then docker volume prune -f >/dev/null 2>&1 || true; fi
ok "Residuals purged"
say "Disk final: $(disk)"

# ---------- Status ----------
box "Service Status"
dc ps
hr

# ---------- Useful commands ----------
box "Useful Commands"
cat <<'EOC'
# --- Logs ---
docker compose logs -f                      # all services
docker compose logs -f webapp-api           # API logs
docker compose logs -f webapp-frontend      # Frontend logs

# --- Rebuild / Restart ---
docker compose build --no-cache --parallel  # full rebuild
docker compose up -d --no-deps webapp-api   # start/recreate single service
docker compose restart webapp-frontend      # quick restart

# --- Shell inside containers ---
docker compose exec webapp-api sh           # or bash if present
docker compose exec webapp-frontend sh

# --- Health & ports ---
docker compose exec webapp-api python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=5)" && echo OK
curl -fsS http://localhost:8080/nginx-health && echo OK
ss -tulpn | grep -E ":(8080|6379)"         # listen ports check

# --- Space recovery (manual) ---
docker image prune -af
docker builder prune -af
docker volume prune -f        # WARNING: deletes unused volumes
docker system df              # disk usage summary

# --- Git branch switch (no backup; .env preserved by script) ---
./update.sh -b main
./update.sh -b staging
EOC

ok "Done."
