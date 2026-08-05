Write-Host "Validando API Gateway"
Invoke-RestMethod -Uri "http://localhost:8080/health" | ConvertTo-Json -Compress

Write-Host "Validando descripcion de arquitectura"
Invoke-RestMethod -Uri "http://localhost:8080/api/v1/architecture" | ConvertTo-Json -Compress

Write-Host "Validando rutas publicadas"
Invoke-RestMethod -Uri "http://localhost:8080/api/v1/routes" | ConvertTo-Json -Compress
