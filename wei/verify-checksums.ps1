# verify-checksums.ps1
# Verify every file listed in CHECKSUMS.txt (SHA-256), using Windows PowerShell 5.1 or PowerShell 7.
# ASCII only on purpose: safe to run in any console code page.
#
# usage:  cd C:\esp\lesson\wei
#         powershell -ExecutionPolicy Bypass -File .\verify-checksums.ps1
#
# exit code: 0 = all files verified, 1 = mismatch/missing found, 2 = CHECKSUMS.txt not found

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$list = Join-Path $root 'CHECKSUMS.txt'
if (-not (Test-Path $list)) { Write-Host "CHECKSUMS.txt not found next to this script."; exit 2 }

$ok = 0; $bad = 0; $miss = 0
foreach ($line in [System.IO.File]::ReadAllLines($list)) {
    if (-not $line -or $line.StartsWith('#')) { continue }
    $m = [regex]::Match($line, '^([0-9a-fA-F]{64}) \*(.+?)\s*(?:#.*)?$')
    if (-not $m.Success) { continue }
    $want = $m.Groups[1].Value.ToLower()
    $rel  = $m.Groups[2].Value.Trim()
    $path = Join-Path $root ($rel -replace '/', '\')
    if (-not (Test-Path -LiteralPath $path)) { $miss++; Write-Host ("MISSING  " + $rel); continue }
    $got = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
    if ($got -eq $want) {
        $ok++
    } else {
        $bad++
        Write-Host ("MISMATCH " + $rel)
        Write-Host ("         expected " + $want)
        Write-Host ("         actual   " + $got)
    }
}

Write-Host ""
Write-Host ("checked OK : " + $ok)
Write-Host ("mismatched : " + $bad)
Write-Host ("missing    : " + $miss)
if ($bad -eq 0 -and $miss -eq 0) {
    Write-Host "RESULT: ALL FILES VERIFIED"
    exit 0
} else {
    Write-Host "RESULT: PROBLEMS FOUND"
    exit 1
}