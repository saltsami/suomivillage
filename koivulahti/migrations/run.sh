#!/usr/bin/env bash
set -Eeuo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"

export PGPASSWORD
PSQL=(psql --no-psqlrc --set=ON_ERROR_STOP=1 --host="$PGHOST" --username="$PGUSER" --dbname="$PGDATABASE")

for attempt in $(seq 1 60); do
  if "${PSQL[@]}" --quiet --command="SELECT 1" >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == "60" ]]; then
    echo "[migrations] PostgreSQL did not become ready" >&2
    exit 1
  fi
  sleep 1
done

"${PSQL[@]}" --quiet <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  checksum TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
SQL

shopt -s nullglob
migration_files=(/migrations/[0-9][0-9][0-9]_*.sql)
if (( ${#migration_files[@]} == 0 )); then
  echo "[migrations] no migration files found" >&2
  exit 1
fi

for file in "${migration_files[@]}"; do
  version=$(basename "$file" .sql)
  if [[ ! "$version" =~ ^[0-9]{3}_[a-zA-Z0-9_]+$ ]]; then
    echo "[migrations] invalid migration filename: $file" >&2
    exit 1
  fi

  checksum=$(sha256sum "$file" | cut -d' ' -f1)
  stored_checksum=$("${PSQL[@]}" --tuples-only --no-align \
    --command="SELECT checksum FROM schema_migrations WHERE version = '$version';")

  if [[ -n "$stored_checksum" ]]; then
    if [[ "$stored_checksum" != "$checksum" ]]; then
      echo "[migrations] checksum mismatch for $version" >&2
      exit 1
    fi
    echo "[migrations] already applied: $version"
    continue
  fi

  transaction=$(mktemp)
  trap 'rm -f "$transaction"' EXIT
  {
    echo '\set ON_ERROR_STOP on'
    echo 'BEGIN;'
    cat "$file"
    echo
    echo "INSERT INTO schema_migrations (version, checksum) VALUES ('$version', '$checksum');"
    echo 'COMMIT;'
  } >"$transaction"

  echo "[migrations] applying: $version"
  "${PSQL[@]}" --quiet --file="$transaction"
  rm -f "$transaction"
  trap - EXIT
done

echo "[migrations] schema is current"
