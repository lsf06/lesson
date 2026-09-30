# ESP-IDF Build Script for esp32_firmware
$ErrorActionPreference = "Continue"

# === Paths ===
$idfPath = 'D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4'
$toolsPath = 'D:\lesson\Download\esp-idf\Espressif\tools'
$pythonVenv = 'D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env'
$idfPy = "$pythonVenv\Scripts\python.exe"
$projectDir = 'd:\lesson\xiaolin\lesson-main (1)\lesson-main\esp32_firmware'

# === Environment ===
$env:IDF_PATH = $idfPath
$env:IDF_PYTHON_ENV_PATH = $pythonVenv
$env:IDF_TOOLS_PATH = 'D:\lesson\Download\esp-idf\Espressif'

# Add tools to PATH
$env:PATH = "$toolsPath\cmake\3.30.2\bin;$toolsPath\ninja\1.12.1;$toolsPath\xtensa-esp-elf\esp-14.2.0_20241119\xtensa-esp-elf\bin;$toolsPath\openocd-esp32\bin;$toolsPath\idf-exe\1.0.3;$env:PATH"

# === Build ===
Set-Location $projectDir
Write-Host "=== Setting target esp32s3 ==="
$idfScript = "$idfPath\tools\idf.py"
& $idfPy $idfScript set-target esp32s3

Write-Host "=== Building ==="
& $idfPy $idfScript build

Write-Host "=== Build complete ==="