@echo off
REM Launches SysTrader under external supervisor (auto-restart on crash).
REM Elevates to admin (CYBOS COM requires admin). Hidden console.
REM Logs: %TEMP%\systrader_stdout.log, %TEMP%\systrader_stderr.log
REM Web UI: http://localhost:8000

REM Guard: refuse to launch if server already responding on port 8000.
REM (Double-clicking start.bat twice would otherwise spawn a second supervisor
REM whose main.py crashes on bind conflict → harmless but restart-loop noise.)
powershell -NoProfile -Command "try { $r = (Invoke-WebRequest -Uri 'http://localhost:8000/api/status' -TimeoutSec 2 -UseBasicParsing).StatusCode } catch { $r = 0 }; if ($r -eq 200) { exit 1 } else { exit 0 }"
if %errorlevel% == 1 (
  echo.
  echo SysTrader is already running ^(port 8000 responding^).
  echo Run stop.bat first if you want to restart.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -Command "Start-Process -FilePath '%~dp0supervise.bat' -WorkingDirectory '%~dp0' -Verb RunAs -WindowStyle Hidden"
echo SysTrader started (supervised, admin-elevated).
echo Web UI:  http://localhost:8000
echo Stop:    run stop.bat
timeout /t 2 >nul
