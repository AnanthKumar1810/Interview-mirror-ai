param(
    [Parameter(Mandatory = $true)]
    [string] $KeyFile,
    [string] $GeminiKeyFile
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $KeyFile -PathType Leaf)) {
    throw 'Gnani key file was not found.'
}
$keyValue = (Get-Content -LiteralPath $KeyFile -Raw).Trim()
if (-not $keyValue) { throw 'Gnani key file is empty.' }
$env:GNANI_API_KEY = $keyValue
if ($GeminiKeyFile) {
    if (-not (Test-Path -LiteralPath $GeminiKeyFile -PathType Leaf)) { throw 'Gemini key file was not found.' }
    $env:GEMINI_API_KEY = (Get-Content -LiteralPath $GeminiKeyFile -Raw).Trim()
    if (-not $env:GEMINI_API_KEY) { throw 'Gemini key file is empty.' }
}
$env:IM_SEMANTIC_JUDGE = 'off'
Set-Location -LiteralPath $PSScriptRoot
python -m uvicorn main:app --host 127.0.0.1 --port 8002
