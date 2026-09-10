#!/usr/bin/env bash
# R178 local-only evidence runner. No ambient DATABASE_URL or provider credentials.
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT=$(pwd -P)
BIN="$ROOT/.venv/pg_root/usr/lib/postgresql/17/bin"
if [[ ! -x "$BIN/postgres" ]]; then
  echo 'Missing PostgreSQL 17 workspace binaries. Run from repository root:' >&2
  echo 'mkdir -p .venv/pg_packages .venv/pg_root' >&2
  echo '(cd .venv/pg_packages && apt-get download postgresql-17 postgresql-client-17 && for p in *.deb; do dpkg-deb -x "$p" ../pg_root; done)' >&2
  exit 2
fi
[[ -x "$ROOT/.venv/bin/python" ]] || { echo 'Missing .venv Python' >&2; exit 2; }
mkdir -p "$ROOT/.venv/r178_tmp"
RUN=$(mktemp -d "$ROOT/.venv/r178_pg_XXXXXX")
mkdir -m 700 "$RUN/socket"
cleanup() {
  "$BIN/pg_ctl" -D "$RUN/data" -m fast -w stop >/dev/null 2>&1 || :
}
trap cleanup EXIT
"$BIN/initdb" -D "$RUN/data" --auth-local=trust --auth-host=reject --no-locale -E UTF8 > "$RUN/init.log"
# Private 0700 socket + no TCP listener. Durability is ON (no fsync shortcuts).
"$BIN/pg_ctl" -D "$RUN/data" -l "$RUN/server.log" -o "-h '' -k $RUN/socket -p 55478" -w start
URL="postgresql+asyncpg://$(id -un)@/postgres?host=$RUN/socket&port=55478"
echo "PostgreSQL version: $("$BIN/postgres" --version)"
echo "Scope: disposable local cluster; metadata dependency closure; no migration/production claim"
env -i PATH="$ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin" HOME="$ROOT/.venv" \
  TMPDIR="$ROOT/.venv/r178_tmp" PYTHONPATH="$ROOT" LANG=C.UTF-8 \
  R178_TEST_DATABASE_URL="$URL" \
  "$ROOT/.venv/bin/python" -m pytest tests_live/r178/test_external_ingestion_postgres.py \
  -o addopts='' -q --tb=short -p no:cacheprovider "$@"
