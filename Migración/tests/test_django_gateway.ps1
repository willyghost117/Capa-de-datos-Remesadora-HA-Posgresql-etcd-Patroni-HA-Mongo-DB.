Write-Host "Validando consola Django y endpoint HAProxy"
Invoke-RestMethod -Uri "http://localhost:8080/health" |
    ConvertTo-Json -Depth 5

Write-Host "Consultando topología PostgreSQL y MongoDB"
$topologia = Invoke-RestMethod -Uri "http://localhost:8080/api/topology/"
$topologia | ConvertTo-Json -Depth 8

if ($topologia.overall -eq "critical") {
    throw "La topología completa se encuentra en estado crítico."
}
if (-not $topologia.postgres.leader) {
    throw "No se detectó un líder PostgreSQL."
}
if (-not $topologia.mongodb.primary) {
    throw "No se detectó un PRIMARY MongoDB."
}

Write-Host "Insertando remesa completa aleatoria por Django y HAProxy"
$resultado = Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8080/api/generator/insert-remittance/" `
    -ContentType "application/json" `
    -Body "{}" `
    -TimeoutSec 100
$resultado | ConvertTo-Json -Depth 8

if ($resultado.status -ne "completed") {
    throw "La remesa no fue confirmada."
}

Write-Host "Consultando últimas remesas"
$recientes = Invoke-RestMethod -Uri "http://localhost:8080/api/events/"
$recientes | ConvertTo-Json -Depth 6

if (-not $recientes.remittances) {
    throw "No se recuperaron remesas recientes."
}

Write-Host "Prueba Django finalizada correctamente" -ForegroundColor Green
