Write-Host "Estado inicial del cluster Patroni"
docker exec globalremit-patroni-pg1 bash -lc "/opt/patroni/bin/patronictl -c /tmp/patroni.yml list"

Write-Host "Identificando lider actual"
$leader = docker exec globalremit-patroni-pg1 bash -lc "/opt/patroni/bin/patronictl -c /tmp/patroni.yml list | awk '/Leader/ {print `$2; exit}'"
$leader = $leader.Trim()
Write-Host "Lider detectado: $leader"

Write-Host "Limpiando eventos anteriores de prueba"
$sqlCleanup = @"
DELETE FROM integration.outbox_event
WHERE aggregate_type = 'FAILOVER_TEST';
"@
$sqlCleanup | docker exec -i globalremit-patroni-pg1 bash -lc "PGPASSWORD='GlobalRemitPg2026!' psql -h globalremit-patroni-haproxy -U postgres -d globalremit"
if ($LASTEXITCODE -ne 0) { throw "No se pudo limpiar eventos previos de failover." }

Write-Host "Insertando transaccion antes del failover por HAProxy"
$sqlBefore = @"
INSERT INTO integration.outbox_event(aggregate_type, aggregate_id, event_type, payload, occurred_at, publication_status)
VALUES ('FAILOVER_TEST', 1, 'BEFORE_FAILOVER', '{"source":"patroni-test"}'::jsonb, now(), 'PENDING');
"@
$sqlBefore | docker exec -i globalremit-patroni-pg1 bash -lc "PGPASSWORD='GlobalRemitPg2026!' psql -h globalremit-patroni-haproxy -U postgres -d globalremit"
if ($LASTEXITCODE -ne 0) { throw "No se pudo insertar evento antes del failover." }

Write-Host "Deteniendo lider actual: $leader"
docker stop $leader
Start-Sleep -Seconds 45

Write-Host "Estado posterior al failover"
$available = @("globalremit-patroni-pg1", "globalremit-patroni-pg2", "globalremit-patroni-pg3") | Where-Object { $_ -ne $leader } | Select-Object -First 1
docker exec $available bash -lc "/opt/patroni/bin/patronictl -c /tmp/patroni.yml list"

Write-Host "Insertando transaccion despues del failover por el mismo HAProxy"
$sqlAfter = @"
INSERT INTO integration.outbox_event(aggregate_type, aggregate_id, event_type, payload, occurred_at, publication_status)
VALUES ('FAILOVER_TEST', 2, 'AFTER_FAILOVER', '{"source":"patroni-test"}'::jsonb, now(), 'PENDING');
"@
$sqlAfter | docker exec -i $available bash -lc "PGPASSWORD='GlobalRemitPg2026!' psql -h globalremit-patroni-haproxy -U postgres -d globalremit"
if ($LASTEXITCODE -ne 0) { throw "No se pudo insertar evento despues del failover." }

Write-Host "Validando eventos de prueba"
$sqlValidate = @"
SELECT event_type, COUNT(*)
FROM integration.outbox_event
WHERE aggregate_type = 'FAILOVER_TEST'
GROUP BY event_type
ORDER BY event_type;
"@
$sqlValidate | docker exec -i $available bash -lc "PGPASSWORD='GlobalRemitPg2026!' psql -h globalremit-patroni-haproxy -U postgres -d globalremit"
if ($LASTEXITCODE -ne 0) { throw "No se pudo validar eventos de failover." }

Write-Host "Reiniciando nodo anterior"
docker start $leader
Start-Sleep -Seconds 20

Write-Host "Estado final del cluster"
docker exec $available bash -lc "/opt/patroni/bin/patronictl -c /tmp/patroni.yml list"
