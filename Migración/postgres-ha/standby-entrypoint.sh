#!/usr/bin/env bash
set -euo pipefail

PGDATA="/var/lib/postgresql/18/docker"
PRIMARY_CONN="host=${PRIMARY_HOST} port=${PRIMARY_PORT} user=${POSTGRES_REPLICATION_USER} password=${POSTGRES_REPLICATION_PASSWORD} application_name=globalremit_standby"

echo "Waiting for primary ${PRIMARY_HOST}:${PRIMARY_PORT}..."
until pg_isready -h "${PRIMARY_HOST}" -p "${PRIMARY_PORT}" -U postgres >/dev/null 2>&1; do
  sleep 2
done

if [ ! -s "${PGDATA}/PG_VERSION" ]; then
  echo "Initializing standby from primary with pg_basebackup..."
  rm -rf "${PGDATA}"
  mkdir -p "${PGDATA}"
  chown -R postgres:postgres /var/lib/postgresql

  export PGPASSWORD="${POSTGRES_REPLICATION_PASSWORD}"
  gosu postgres pg_basebackup \
    -h "${PRIMARY_HOST}" \
    -p "${PRIMARY_PORT}" \
    -D "${PGDATA}" \
    -U "${POSTGRES_REPLICATION_USER}" \
    -Fp -Xs -P -R

  echo "primary_conninfo = '${PRIMARY_CONN}'" >> "${PGDATA}/postgresql.auto.conf"
  echo "hot_standby = on" >> "${PGDATA}/postgresql.auto.conf"
  chmod 700 "${PGDATA}"
  chown -R postgres:postgres "${PGDATA}"
fi

exec gosu postgres postgres -D "${PGDATA}" -c listen_addresses='*'
