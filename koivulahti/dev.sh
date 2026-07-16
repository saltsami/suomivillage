#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$ROOT_DIR"

ENV_FILE=${ENV_FILE:-infra/.env.example}
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

BASE=(docker compose --env-file "$ENV_FILE" -f infra/docker-compose.yml)
DEV=(docker compose --env-file "$ENV_FILE" -f infra/docker-compose.yml -f infra/docker-compose.dev.yml)

usage() {
  cat <<'EOF'
Usage: ./dev.sh COMMAND

  up             Start the safe fake-provider stack
  up-dev         Start it with loopback DB/Redis/gateway ports for diagnostics
  up-cpu         Start with local llama.cpp CPU inference
  up-gpu         Start with local llama.cpp GPU inference
  up-decision    Start the opt-in Gemini decision service
  down           Stop the stack without deleting data
  logs           Follow application logs
  ps             Show service status
  config         Validate the resolved Compose configuration
  build          Build all six application images
  test-unit      Run tests that need no services
  test-e2e       Build a disposable fake-provider stack and run integration tests
  reset          Delete local stack data (requires CONFIRM_RESET=1)

Use a private environment file explicitly when needed:
  ENV_FILE=infra/.env ./dev.sh up-decision
EOF
}

require_uv() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required for tests: https://docs.astral.sh/uv/" >&2
    exit 1
  fi
}

command=${1:-}
case "$command" in
  up)
    "${BASE[@]}" up --detach --build --wait
    ;;
  up-dev)
    "${DEV[@]}" up --detach --build --wait
    ;;
  up-cpu)
    LLM_PROVIDER=llama_cpp LLM_SERVER_URL=http://llm-server-cpu:8080 \
      "${BASE[@]}" --profile cpu up --detach --build --wait
    ;;
  up-gpu)
    LLM_PROVIDER=llama_cpp LLM_SERVER_URL=http://llm-server-gpu:8080 \
      "${BASE[@]}" --profile gpu up --detach --build --wait
    ;;
  up-decision)
    gemini_key=$(awk -F= '/^GEMINI_API_KEY=/{sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE")
    if [[ -z "$gemini_key" ]]; then
      echo "GEMINI_API_KEY is empty in $ENV_FILE" >&2
      exit 1
    fi
    DECISION_SERVICE_ENABLED=true "${BASE[@]}" --profile decision up --detach --build --wait
    ;;
  down)
    "${BASE[@]}" --profile cpu --profile gpu --profile decision --profile ambient \
      down --remove-orphans
    ;;
  logs)
    "${BASE[@]}" logs --follow api engine workers llm-gateway
    ;;
  ps)
    "${BASE[@]}" --profile cpu --profile gpu --profile decision --profile ambient ps
    ;;
  config)
    "${BASE[@]}" --profile cpu --profile gpu --profile decision --profile ambient \
      config --quiet
    echo "Compose configuration is valid ($ENV_FILE)"
    ;;
  build)
    "${BASE[@]}" --profile decision --profile ambient build \
      api engine workers llm-gateway decision-service ambient-worker
    ;;
  test-unit)
    require_uv
    uv run pytest -m "not integration"
    ;;
  test-e2e)
    require_uv
    E2E=(docker compose -p koivulahti-e2e --env-file infra/.env.example \
      -f infra/docker-compose.yml -f infra/docker-compose.dev.yml)
    cleanup() {
      "${E2E[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
    }
    trap cleanup EXIT
    cleanup
    if ! "${E2E[@]}" up --detach --build --wait; then
      "${E2E[@]}" logs --no-color
      exit 1
    fi
    if ! uv run pytest -m integration; then
      "${E2E[@]}" logs --no-color
      exit 1
    fi
    ;;
  reset)
    if [[ ${CONFIRM_RESET:-0} != 1 ]]; then
      echo "Refusing to delete data. Re-run with CONFIRM_RESET=1." >&2
      exit 1
    fi
    "${BASE[@]}" --profile cpu --profile gpu --profile decision --profile ambient \
      down --volumes --remove-orphans
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
