param(
    [string]$HostName = "0.0.0.0",
    [int]$Port = 8765,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"

if (-not (Test-Path -LiteralPath (Join-Path $Frontend "package.json"))) {
    throw "Frontend package.json not found at $Frontend"
}

if (-not $SkipBuild) {
    Push-Location $Frontend
    try {
        if (-not (Test-Path -LiteralPath "node_modules")) {
            npm install
        }
        npm run build
    }
    finally {
        Pop-Location
    }
}

Write-Host "Novel Translator running at http://$HostName`:$Port"
python (Join-Path $Root "app.py") --host $HostName --port $Port
