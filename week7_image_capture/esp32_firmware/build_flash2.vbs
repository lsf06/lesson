Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
logFile = "D:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware\build_log_vbs.txt"
Set ts = fso.CreateTextFile(logFile, True)
ts.WriteLine "VBS_STARTED: " & Now
ts.Close
cmd = "cmd.exe /c call D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\export.bat > nul 2>&1 && "
cmd = cmd + "cd /d D:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware && "
cmd = cmd + "idf.py build >> " + Chr(34) + logFile + Chr(34) + " 2>&1 && "
cmd = cmd + "idf.py -p COM4 flash >> " + Chr(34) + logFile + Chr(34) + " 2>&1"
WshShell.Run cmd, 0, True
Set ts = fso.OpenTextFile(logFile, 8)
ts.WriteLine "VBS_FINISHED: " & Now
ts.Close