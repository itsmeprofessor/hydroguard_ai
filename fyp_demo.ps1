# =========================
# HYDROGUARD AI - FYP DEMO MODE
# =========================

$baseUrl = "http://localhost:8000"

Write-Host "`n=== STEP 1: LOGIN ===`n" -ForegroundColor Cyan

$loginBody = @{
    email = "zain@gmail.com"
    password = "zain1234"
} | ConvertTo-Json

$loginResponse = Invoke-RestMethod `
    -Uri "$baseUrl/auth/login" `
    -Method POST `
    -ContentType "application/json" `
    -Body $loginBody

$token = $loginResponse.access_token

Write-Host "Token acquired for user: $($loginResponse.username)" -ForegroundColor Green


# =========================
# STEP 2: WEATHER FETCH
# =========================

Write-Host "`n=== STEP 2: WEATHER (GILGIT) ===`n" -ForegroundColor Cyan

$weather = Invoke-RestMethod `
    -Uri "$baseUrl/weather/gilgit/current" `
    -Method GET

$weather | ConvertTo-Json -Depth 10


# =========================
# STEP 3: PREDICTION
# =========================

Write-Host "`n=== STEP 3: PREDICTION (GILGIT) ===`n" -ForegroundColor Cyan

$predictBody = @{
    city = "gilgit"
    prcp = $weather.prcp
    humidity = $weather.humidity
    pressure = $weather.pressure
    tmax = $weather.tmax
    tmin = $weather.tmin
} | ConvertTo-Json

$prediction = Invoke-RestMethod `
    -Uri "$baseUrl/api/v2/cities/gilgit/predict" `
    -Method POST `
    -ContentType "application/json" `
    -Body $predictBody

$prediction | ConvertTo-Json -Depth 10


# =========================
# STEP 4: RISK MAP
# =========================

Write-Host "`n=== STEP 4: RISK MAP ===`n" -ForegroundColor Cyan

$riskMap = Invoke-RestMethod `
    -Uri "$baseUrl/risk-map" `
    -Method GET

$riskMap | ConvertTo-Json -Depth 10


# =========================
# STEP 5: DRIFT CHECK
# =========================

Write-Host "`n=== STEP 5: DRIFT (ALL CITIES) ===`n" -ForegroundColor Cyan

$drift = Invoke-RestMethod `
    -Uri "$baseUrl/api/v2/drift" `
    -Method GET

$drift | ConvertTo-Json -Depth 10


# =========================
# STEP 6: CITY STATUS SNAPSHOT
# =========================

Write-Host "`n=== STEP 6: CITY OVERVIEW ===`n" -ForegroundColor Cyan

$cities = Invoke-RestMethod `
    -Uri "$baseUrl/cities/overview" `
    -Method GET

$cities | ConvertTo-Json -Depth 10


# =========================
# STEP 7: FINAL REPORT
# =========================

Write-Host "`n=== FINAL REPORT ===`n" -ForegroundColor Yellow

$report = @{
    timestamp = (Get-Date).ToString("s")
    user = $loginResponse.username
    city = "gilgit"
    weather = $weather
    prediction = $prediction
    risk_map_summary = $riskMap.entries.Count
    drift_status = "checked"
    system_status = "HydroGuard AI running normally"
}

$report | ConvertTo-Json -Depth 10

Write-Host "`n=== DEMO COMPLETE ===`n" -ForegroundColor Green