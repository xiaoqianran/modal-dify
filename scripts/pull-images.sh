#!/usr/bin/env bash
# Pull only active Dify Compose services, with bounded concurrency and logging.
set -Eeuo pipefail
COMPOSE_DIR="${1:-}"
PARALLEL="${2:-4}"
if [[ -z "$COMPOSE_DIR" || ! -f "$COMPOSE_DIR/docker-compose.yaml" ]]; then
  echo "Usage: $0 /path/to/dify/docker [parallel=4]" >&2
  exit 2
fi
if ! [[ "$PARALLEL" =~ ^[1-9][0-9]*$ ]] || (( PARALLEL > 16 )); then
  echo "parallel must be 1..16" >&2
  exit 2
fi
command -v docker >/dev/null
docker info >/dev/null
cd "$COMPOSE_DIR"
if [[ ! -f .env ]]; then
  echo "Missing .env; copy and configure the official Dify env before pulling" >&2
  exit 2
fi
docker compose config --quiet
mkdir -p pull-logs
LOG="pull-logs/pull-$(date -u +%Y%m%dT%H%M%SZ)-p${PARALLEL}.log"
echo "Active image references:"
docker compose config --images | sort -u
echo "Starting parallel pull: $PARALLEL; log: $LOG"
start=$(date +%s)
set +e
docker compose --parallel "$PARALLEL" --progress plain pull --policy missing 2>&1 | tee "$LOG"
status=${PIPESTATUS[0]}
set -e
elapsed=$(( $(date +%s) - start ))
echo "pull exit=$status elapsed_seconds=$elapsed log=$LOG"
exit "$status"
