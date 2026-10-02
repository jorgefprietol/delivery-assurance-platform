$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root '.env'
$existing = if (Test-Path -LiteralPath $envPath) { [IO.File]::ReadAllText($envPath) } else { '' }
if ($existing -match '(?m)^ENGINEER_API_KEY=' -and $existing -match '(?m)^REVIEWER_API_KEY=') {
    Write-Host '.env already has individual credentials; keeping them.'
    exit 0
}
function New-OperatorKey {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
$engineerKey = if ($existing -match '(?m)^API_KEY=([^\r\n]{32,})') { $Matches[1] } else { New-OperatorKey }
$reviewerKey = New-OperatorKey
$content = "ENGINEER_ID=jorge-prieto`nENGINEER_API_KEY=$engineerKey`nREVIEWER_ID=release-reviewer`nREVIEWER_API_KEY=$reviewerKey`nAPP_PORT=18140`nDELIVERY_SUBNET=10.254.120.0/28`n"
[IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
Write-Host 'Individual engineer and reviewer credentials saved in .env. No keys were printed.'
