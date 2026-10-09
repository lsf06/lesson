import subprocess, os, sys

project_dir = r"D:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware"
idf_path = r"D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4"
export_bat = os.path.join(idf_path, "export.bat")
log_file = os.path.join(project_dir, "build_log.txt")

# Clean
for d in ["build", "managed_components"]:
    dp = os.path.join(project_dir, d)
    if os.path.exists(dp):
        import shutil; shutil.rmtree(dp, ignore_errors=True)
for f in ["sdkconfig"]:
    fp = os.path.join(project_dir, f)
    if os.path.exists(fp):
        os.remove(fp)

# Build command: run export.bat then idf.py build
cmd = f'call "{export_bat}" >nul 2>&1 && cd /d "{project_dir}" && idf.py build'
full_cmd = f'cmd.exe /c "{cmd} > "{log_file}" 2>&1"'

print(f"Running: {full_cmd[:120]}...")
print(f"Log: {log_file}")

# Use CREATE_NO_WINDOW flag (0x08000000)
CREATE_NO_WINDOW = 0x08000000
proc = subprocess.Popen(
    full_cmd,
    shell=False,
    creationflags=CREATE_NO_WINDOW,
    close_fds=True
)

print(f"Build PID: {proc.pid}")
print("Build started in background")