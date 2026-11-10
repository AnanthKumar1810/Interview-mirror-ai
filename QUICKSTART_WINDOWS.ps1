# Run this from the extracted InterviewMirrorAI-GitHub-Ready folder.
# It does not contact Gnani unless you explicitly test live voice in the app.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path '.venv\Scripts\python.exe')) {
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create virtual environment.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (!(Test-Path '.env')) { Copy-Item .env.example .env }
& '.\.venv\Scripts\python.exe' -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Offline tests failed. Check the output.' }
Write-Host 'Open http://127.0.0.1:8001 after Uvicorn starts.'
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --port 8001
