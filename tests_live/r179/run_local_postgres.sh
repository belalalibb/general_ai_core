#!/usr/bin/env bash
# R179 local-only evidence runner. Disposable workspace PostgreSQL 17 cluster with
# pgvector (needed by the REAL alembic 0007 step). No ambient DATABASE_URL, no provider
# credentials. Durability is ON (no fsync shortcuts). Never a production claim.
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT=$(pwd -P)
BIN="$ROOT/.venv/pg_root/usr/lib/postgresql/17/bin"
if [[ ! -x "$BIN/postgres" || ! -f "$ROOT/.venv/pg_root/usr/lib/postgresql/17/lib/vector.so" ]]; then
  echo 'Missing PostgreSQL 17 (+pgvector) workspace binaries. From repository root:' >&2
  echo 'mkdir -p .venv/pg_packages .venv/pg_root' >&2
  echo '(cd .venv/pg_packages && apt-get download postgresql-17 postgresql-client-17 postgresql-17-pgvector && for p in *.deb; do dpkg-deb -x "$p" ../pg_root; done)' >&2
  exit 2
fi
[[ -x "$ROOT/.venv/bin/python" ]] || { echo 'Missing .venv Python' >&2; exit 2; }
mkdir -p "$ROOT/.venv/r179_tmp"
RUN=$(mktemp -d "$ROOT/.venv/r179_pg_XXXXXX")
mkdir -m 700 "$RUN/socket"
cleanup() { "$BIN/pg_ctl" -D "$RUN/data" -m fast -w stop >/dev/null 2>&1 || :; }
trap cleanup EXIT
"$BIN/initdb" -D "$RUN/data" --auth-local=trust --auth-host=reject --no-locale -E UTF8 > "$RUN/init.log"
"$BIN/pg_ctl" -D "$RUN/data" -l "$RUN/server.log" \
  -o "-h '' -k $RUN/socket -p 55479 -c dynamic_library_path=$ROOT/.venv/pg_root/usr/lib/postgresql/17/lib" -w start
URL="postgresql+asyncpg://$(id -un)@/postgres?host=$RUN/socket&port=55479"
echo "PostgreSQL version: $("$BIN/postgres" --version)"
echo "Scope: disposable local cluster; real alembic; single node; no production claim"
env -i PATH="$ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin" HOME="$ROOT/.venv" \
  TMPDIR="$ROOT/.venv/r179_tmp" PYTHONPATH="$ROOT" LANG=C.UTF-8 \
  R179_TEST_DATABASE_URL="$URL" \
  "$ROOT/.venv/bin/python" -m pytest tests_live/r179 \
  -o addopts='' -q --tb=short -p no:cacheprovider "$@"
