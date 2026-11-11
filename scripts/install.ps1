param([ValidateSet('codex','claude','generic')][string]$Client = 'codex')
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoPath
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        py -3 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
    & '.\.venv\Scripts\epn.exe' --root $repoPath install --client $Client
    if ($LASTEXITCODE -ne 0) { throw 'Client configuration was not installed; inspect the message above.' }
    Write-Host 'Installed project skills and MCP. Restart your agent client to load them.'
} finally { Pop-Location }
