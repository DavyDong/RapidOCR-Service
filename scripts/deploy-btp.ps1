param(
    [string]$AppName = 'rapidocr',
    [string]$Manifest = 'manifest.yml'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) { throw 'The deployment manifest does not exist.' }
    $appGuid = (cf app $AppName --guid).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Select the BTP organization and space containing rapidocr first.' }
    $appVariables = cf curl "/v3/apps/$appGuid/environment_variables" | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Could not read RapidOCR environment configuration.' }
    $configuredToken = $appVariables.var.ACCESS_TOKEN
    if ([string]::IsNullOrWhiteSpace($configuredToken)) { throw 'Configure ACCESS_TOKEN in the BTP application environment first.' }
    # The CF manifest diff can display existing user variables. Redact the token.
    cf push $AppName -f $Manifest 2>&1 | ForEach-Object { ([string]$_).Replace($configuredToken, '[REDACTED]') }
    if ($LASTEXITCODE -ne 0) { throw 'Cloud Foundry deployment failed.' }
} finally {
    Pop-Location
}
