param(
    [Parameter(Mandatory = $true)]
    [string] $KeyFile
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $KeyFile -PathType Leaf)) {
    throw 'Gnani key file was not found.'
}
$keyValue = (Get-Content -LiteralPath $KeyFile -Raw).Trim()
if (-not $keyValue) { throw 'Gnani key file is empty.' }
$env:GNANI_API_KEY = $keyValue
$env:IM_SEMANTIC_JUDGE = 'off'
Set-Location -LiteralPath $PSScriptRoot
python -m uvicorn main:app --host 127.0.0.1 --port 8002
