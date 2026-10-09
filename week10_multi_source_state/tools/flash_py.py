import subprocess, os
os.chdir(r'd:\lesson\xiaolin\lesson-main (1)\lesson-main\esp32_firmware')
env = os.environ.copy()
env['IDF_PATH'] = r'D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4'
env['IDF_TOOLS_PATH'] = r'D:\lesson\Download\esp-idf\Espressif'
env['IDF_PYTHON_ENV_PATH'] = r'D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env'
env['PATH'] = r'D:\lesson\Download\esp-idf\Espressif\tools\cmake\3.30.2\bin;D:\lesson\Download\esp-idf\Espressif\tools\ninja\1.12.1;D:\lesson\Download\esp-idf\Espressif\tools\xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin;' + env['PATH']
cmd = [
    r'D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env\Scripts\python.exe',
    r'D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\tools\idf.py',
    '-p', 'COM4', 'flash'
]
with open('flash_py_log.txt','w') as log:
    p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
    log.write('\nEXIT_CODE=' + str(p.returncode) + '\n')
print('Flash done, exit=' + str(p.returncode))
