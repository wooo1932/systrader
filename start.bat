@echo off
REM Launches SysTrader under external supervisor (auto-restart on crash).
REM Elevates to admin (CYBOS COM requires admin). Hidden console.
REM Logs: %TEMP%\systrader_stdout.log, %TEMP%\systrader_stderr.log
REM Web UI: http://localhost:8000
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0supervise.bat' -WorkingDirectory '%~dp0' -Verb RunAs -WindowStyle Hidden"
echo SysTrader started (supervised, admin-elevated).
echo Web UI:  http://localhost:8000
echo Stop:    run stop.bat
timeout /t 2 >nul
