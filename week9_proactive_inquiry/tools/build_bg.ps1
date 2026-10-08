# Auto-generated background build script
$ErrorActionPreference = "Stop"
$logFile = "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week3_key_feedback\esp32_firmware\build_log.txt"
$projectDir = "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week3_key_feedback\esp32_firmware"

# Source ESP-IDF environment
. "D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\export.ps1" *>$null

Set-Location $projectDir

"=== BUILD START $(Get-Date) ===" | Out-File -FilePath $logFile

$result = idf.py build 2>&1
$result | Out-File -FilePath $logFile -Append

if ($LASTEXITCODE -eq 0) {
    "=== BUILD SUCCESS $(Get-Date) ===" | Out-File -FilePath $logFile -Append
} else {
    "=== BUILD FAILED $(Get-Date) ===" | Out-File -FilePath $logFile -Append
}