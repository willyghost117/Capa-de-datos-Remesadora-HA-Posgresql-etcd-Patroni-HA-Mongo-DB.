#!/usr/bin/env bash
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${POSTGRES_REPLICATION_USER}') THEN
        CREATE ROLE ${POSTGRES_REPLICATION_USER} WITH REPLICATION LOGIN PASSWORD '${POSTGRES_REPLICATION_PASSWORD}';
    END IF;
END
\$\$;
SQL

cat >> "$PGDATA/pg_hba.conf" <<-EOF

# GlobalRemit Docker HA replication
host replication ${POSTGRES_REPLICATION_USER} all scram-sha-256
host all all all scram-sha-256
EOF
