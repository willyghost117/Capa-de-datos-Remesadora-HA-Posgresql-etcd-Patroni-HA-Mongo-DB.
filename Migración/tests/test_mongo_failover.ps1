Write-Host "Estado inicial replica set"
docker exec globalremit-mongo1 mongosh --quiet --eval "rs.status().members.map(m => ({name:m.name,stateStr:m.stateStr,health:m.health}))"

Write-Host "Deteniendo mongo1..."
docker stop globalremit-mongo1
Start-Sleep -Seconds 10

Write-Host "Estado despues de failover"
docker exec globalremit-mongo2 mongosh --quiet --eval "rs.status().members.map(m => ({name:m.name,stateStr:m.stateStr,health:m.health}))"

Write-Host "Validando datos despues del failover"
docker exec -w /workspace globalremit-mongo2 mongosh --quiet "mongodb://globalremit-mongo2:27017,globalremit-mongo3:27017/globalremit_analytics?replicaSet=rsGlobalRemit" --eval "printjson({remittance_lifecycle: db.remittance_lifecycle.countDocuments(), fraud_signals: db.fraud_signals.countDocuments(), primary: db.hello().primary})"

Write-Host "Reiniciando mongo1..."
docker start globalremit-mongo1
Start-Sleep -Seconds 10

Write-Host "Estado final replica set"
docker exec globalremit-mongo2 mongosh --quiet --eval "rs.status().members.map(m => ({name:m.name,stateStr:m.stateStr,health:m.health}))"

