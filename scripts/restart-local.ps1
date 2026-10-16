param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runtimePath = Join-Path $projectRoot '.runtime'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Install the project virtual environment first.' }
if ([string]::IsNullOrWhiteSpace($env:ACCESS_TOKEN)) { throw 'Set ACCESS_TOKEN in this PowerShell session before starting RapidOCR.' }
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
$pidPath = Join-Path $runtimePath 'server.pid'
if (Test-Path -LiteralPath $pidPath) {
    $previousId = [int](Get-Content -LiteralPath $pidPath)
    $previous = Get-CimInstance Win32_Process -Filter "ProcessId=$previousId" -ErrorAction SilentlyContinue
    if ($previous -and $previous.ExecutablePath -eq $pythonPath -and $previous.CommandLine -match 'deployment\.app:app') {
        Stop-Process -Id $previousId
        Wait-Process -Id $previousId -Timeout 15 -ErrorAction SilentlyContinue
    }
}
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listener) { throw "Port $Port is occupied by another process." }
$env:PYTHONUNBUFFERED = '1'
$env:OCR_THREADS = '2'
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
$server = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','deployment.app:app','--host','127.0.0.1','--port',"$Port",'--workers','1','--limit-concurrency','16') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath 'server.out.log') -RedirectStandardError (Join-Path $runtimePath 'server.err.log')
$server.Id | Set-Content -LiteralPath $pidPath
Write-Output "RapidOCR starting at http://127.0.0.1:$Port (PID $($server.Id))"
