#!/bin/bash
# Docker-entrypoint hook. Runs before init.sql (alphabetical order) and passes
# the read-only role's password in as a psql variable, so no credential is ever
# written into a file tracked by Git.
set -euo pipefail

: "${RAG_READONLY_PASSWORD:?RAG_READONLY_PASSWORD must be set (see .env.example)}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v ro_password="$RAG_READONLY_PASSWORD" \
     -f /docker-entrypoint-initdb.d/init.sql
