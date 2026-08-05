param(
    [string]$BaseUrl = "http://localhost:8080",
    [int]$TimeoutSeconds = 35
)

$ErrorActionPreference = "Stop"

Write-Host "Insertando remesa completa mediante Django..." -ForegroundColor Cyan
$operation = Invoke-RestMethod `
    -Method Post `
    -Uri "$BaseUrl/api/generator/insert-remittance/" `
    -ContentType "application/json" `
    -Body "{}"

if ($operation.status -ne "completed" -or -not $operation.parsed.event_id) {
    throw "La API no confirmó una remesa correlacionable."
}

$result = $operation.parsed
$eventId = $result.event_id
$encodedLsn = [uri]::EscapeDataString($result.commit_lsn)
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$trace = $null

Write-Host "Remesa:  $($result.remittance_code)" -ForegroundColor White
Write-Host "event_id: $eventId" -ForegroundColor White
Write-Host "LSN:      $($result.commit_lsn)" -ForegroundColor White

do {
    $trace = Invoke-RestMethod `
        -Uri "$BaseUrl/api/remittance-trace/$eventId/?commit_lsn=$encodedLsn"

    Clear-Host
    Write-Host "GlobalRemit - traza distribuida verificable" -ForegroundColor Cyan
    Write-Host "Remesa:  $($trace.event.remittance_code)"
    Write-Host "event_id: $($trace.event.event_id)"
    Write-Host "LSN:      $($trace.commit_lsn)"
    Write-Host ""
    $trace.stages |
        Select-Object id, status, detail |
        Format-Table -AutoSize

    if ($trace.complete) {
        break
    }
    Start-Sleep -Milliseconds 700
} while ((Get-Date) -lt $deadline)

if (-not $trace.complete) {
    throw "La traza no quedó completa dentro de $TimeoutSeconds segundos."
}

Write-Host "Traza completa confirmada." -ForegroundColor Green
Write-Host "PostgreSQL: $((@($trace.postgres_nodes | Where-Object caught_up)).Count)/3 nodos alcanzaron el LSN."
Write-Host "MongoDB:    $((@($trace.mongodb_nodes | Where-Object document_found)).Count)/3 nodos contienen el evento."

