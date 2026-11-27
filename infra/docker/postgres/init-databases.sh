#!/bin/sh
set -eu
# Official postgres entrypoint invokes .sh with sh, including Windows checkouts.
# SQL identifier/value quoting is delegated to psql, never string concatenation.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=agent_db="$AGENT_DB" <<'SQL'
SELECT format('CREATE DATABASE %I', :'agent_db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'agent_db')\gexec
SQL
