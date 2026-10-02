$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root '.env'
if (Test-Path -LiteralPath $envPath) {
    Write-Host '.env already exists; keeping the current credential.'
    exit 0
}
$bytes = New-Object byte[] 32
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
$key = ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
"API_KEY=$key`nAPP_PORT=18130" | Set-Content -LiteralPath $envPath -Encoding utf8
Write-Host 'Local configuration created in .env. Use its API_KEY to connect the workspace.'
