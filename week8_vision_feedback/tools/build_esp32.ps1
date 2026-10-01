# ESP-IDF Build Script for week3_key_feedback/esp32_firmware
$ErrorActionPreference = "Continue"

# === Paths ===
$idfPath = 'D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4'
$toolsPath = 'D:\lesson\Download\esp-idf\Espressif\tools'
$pythonVenv = 'D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env'
$idfPy = "$pythonVenv\Scripts\python.exe"
$projectDir = 'd:\lesson\xiaolin\lesson-main (1)\lesson-main\week3_key_feedback\esp32_firmware'

# === Environment ===
$env:IDF_PATH = $idfPath
$env:IDF_PYTHON_ENV_PATH = $pythonVenv
$env:IDF_TOOLS_PATH = 'D:\lesson\Download\esp-idf\Espressif'
$env:PATH = "$toolsPath\cmake\3.30.2\bin;$toolsPath\ninja\1.12.1;$toolsPath\xtensa-esp-elf\esp-14.2.0_20241119\xtensa-esp-elf\bin;$env:PATH"

# === Build ===
Set-Location $projectDir
$idfScript = "$idfPath\tools\idf.py"
Write-Host "=== Setting target esp32s3 ==="
& $idfPy $idfScript set-target esp32s3
if ($LASTEXITCODE -ne 0) { Write-Host "set-target failed!"; exit 1 }
Write-Host "=== Building ==="
& $idfPy $idfScript build
Write-Host "=== Build complete ==="