@echo off
REM Stops SysTrader supervised run:
REM 1) Write stop-file so supervisor exits after current process dies
REM 2) Kill main.py python process (supervisor sees exit + stop-file, exits cleanly)
REM 3) Also kill any stray supervise.bat if still looping
echo. > "%TEMP%\systrader_stop"
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' -and $_.Name -like 'python*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*supervise.bat*' -and $_.Name -eq 'cmd.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo SysTrader stopped.
timeout /t 2 >nul
