$env:IDF_PATH = "D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4"
$env:IDF_PYTHON_ENV_PATH = "D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env"
$env:PATH = "$env:IDF_PYTHON_ENV_PATH\Scripts;$env:IDF_PATH\tools;$env:PATH"

Set-Location "D:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware"

# First run cmake to generate ninja build
& cmake --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    # cmake not in path, try adding more paths
    $tools_paths = @(
        "D:\lesson\Download\esp-idf\Espressif\tools\cmake\3.30.2\bin",
        "D:\lesson\Download\esp-idf\Espressif\tools\ninja\1.12.1"
    )
    foreach($tp in $tools_paths) {
        if (Test-Path $tp) {
            $env:PATH = "$tp;$env:PATH"
        }
    }
}

Write-Output "===== BUILD STARTED ===== $(Get-Date -Format 'HH:mm:ss')" 
& python "$env:IDF_PATH\tools\idf.py" build 2>&1
$exitCode = $LASTEXITCODE
Write-Output "===== BUILD FINISHED ===== exit=$exitCode $(Get-Date -Format 'HH:mm:ss')"
exit $exitCode