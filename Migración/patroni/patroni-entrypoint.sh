#!/usr/bin/env bash
set -euo pipefail

: "${PATRONI_NAME:?PATRONI_NAME is required}"
: "${PATRONI_SCOPE:=globalremit}"
: "${PATRONI_ETCD_HOST:=patroni-etcd:2379}"
: "${PATRONI_SUPERUSER_PASSWORD:=GlobalRemitPg2026!}"
: "${PATRONI_REPLICATION_PASSWORD:=GlobalRemitRepl2026!}"
: "${PATRONI_REWIND_PASSWORD:=GlobalRemitRewind2026!}"

mkdir -p /var/lib/postgresql/data/pgdata
chmod 700 /var/lib/postgresql/data/pgdata

cat > /tmp/patroni.yml <<EOF
scope: ${PATRONI_SCOPE}
namespace: /service/
name: ${PATRONI_NAME}

restapi:
  listen: 0.0.0.0:8008
  connect_address: ${PATRONI_NAME}:8008

etcd3:
  hosts: ${PATRONI_ETCD_HOST}

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576
    postgresql:
      use_pg_rewind: true
      use_slots: true
      parameters:
        wal_level: replica
        hot_standby: "on"
        max_wal_senders: 10
        max_replication_slots: 10
        wal_keep_size: 512MB
  initdb:
    - encoding: UTF8
    - data-checksums
  pg_hba:
    - host replication replicator 0.0.0.0/0 md5
    - host replication replicator ::0/0 md5
    - host all all 0.0.0.0/0 md5
    - host all all ::0/0 md5
  users:
    admin:
      password: ${PATRONI_SUPERUSER_PASSWORD}
      options:
        - createrole
        - createdb

postgresql:
  listen: 0.0.0.0:5432
  connect_address: ${PATRONI_NAME}:5432
  data_dir: /var/lib/postgresql/data/pgdata
  bin_dir: /usr/lib/postgresql/18/bin
  authentication:
    superuser:
      username: postgres
      password: ${PATRONI_SUPERUSER_PASSWORD}
    replication:
      username: replicator
      password: ${PATRONI_REPLICATION_PASSWORD}
    rewind:
      username: rewind_user
      password: ${PATRONI_REWIND_PASSWORD}
  parameters:
    unix_socket_directories: /tmp

tags:
  nofailover: false
  noloadbalance: false
  clonefrom: false
  nosync: false
EOF

exec /opt/patroni/bin/patroni /tmp/patroni.yml
