Write-Host "Validando PostgreSQL Patroni por HAProxy"
docker exec globalremit-patroni-pg1 bash -lc "PGPASSWORD='GlobalRemitPg2026!' psql -h globalremit-patroni-haproxy -U postgres -d globalremit -c 'SELECT COUNT(1) AS remesas FROM remittance.remittance_order;'"

Write-Host "Validando estado del cluster Patroni"
docker exec globalremit-patroni-pg1 bash -lc "/opt/patroni/bin/patronictl -c /tmp/patroni.yml list"

Write-Host "Validando que el endpoint de escritura apunta al lider"
docker exec globalremit-patroni-pg1 bash -lc "PGPASSWORD='GlobalRemitPg2026!' psql -h globalremit-patroni-haproxy -U postgres -d globalremit -c 'SELECT pg_is_in_recovery() AS is_replica;'"
