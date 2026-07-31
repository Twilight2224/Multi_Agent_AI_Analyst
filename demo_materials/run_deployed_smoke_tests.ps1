param(
    [Parameter(Mandatory = $true)]
    [string]$ApiUrl
)

$ErrorActionPreference = "Stop"
$baseUrl = $ApiUrl.TrimEnd("/")
$materialsDirectory = Split-Path -Parent $PSCommandPath
$handbook = Get-Content -Raw -LiteralPath (Join-Path $materialsDirectory "company_operations_handbook.md")
$tests = Get-Content -Raw -LiteralPath (Join-Path $materialsDirectory "test_questions.json") | ConvertFrom-Json

Write-Host "Checking health: $baseUrl/health" -ForegroundColor Cyan
$health = Invoke-RestMethod -Uri "$baseUrl/health" -Method Get
$health | ConvertTo-Json -Depth 5
if (-not $health.gemini_key_configured) {
    throw "GEMINI_API_KEY is not configured on the deployed backend."
}

Write-Host "Ingesting test handbook..." -ForegroundColor Cyan
$ingestBody = @{ source = "company_operations_handbook.md"; text = $handbook } | ConvertTo-Json
$ingest = Invoke-RestMethod -Uri "$baseUrl/ingest" -Method Post -ContentType "application/json" -Body $ingestBody
$ingest | ConvertTo-Json -Depth 5

$coreTests = $tests | Where-Object { $_.id -in @("T01", "T02", "T04", "T05", "T06", "T09") }
foreach ($test in $coreTests) {
    Write-Host "`n$($test.id): $($test.question)" -ForegroundColor Yellow
    $body = @{ question = $test.question; session_id = "deployed-smoke-test" } | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$baseUrl/chat" -Method Post -ContentType "application/json" -Body $body
    [PSCustomObject]@{
        Expected = $test.expected
        Answer = $response.answer
        Steps = $response.steps -join " -> "
        Approved = $response.approved
        Sources = $response.sources -join "; "
    } | Format-List
}

Write-Host "Smoke test finished. Compare each answer with the Expected field above." -ForegroundColor Green
