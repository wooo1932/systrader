@echo off
REM supervise.bat — auto-restart loop for SysTrader.
REM CYBOS COM can hit native access violations we cannot prevent in-process
REM (BUY BlockRequest, PumpWaitingMessages under disclosure flood). On any exit,
REM this script restarts main.py with a small backoff. Stop via stop.bat.

setlocal
cd /d "%~dp0"
set "STOP_FILE=%TEMP%\systrader_stop"
set "OUT_LOG=%TEMP%\systrader_stdout.log"
set "ERR_LOG=%TEMP%\systrader_stderr.log"
if exist "%STOP_FILE%" del /q "%STOP_FILE%"

:loop
echo [%date% %time%] starting systrader >> "%OUT_LOG%"
.venv\Scripts\python.exe -u main.py >> "%OUT_LOG%" 2>> "%ERR_LOG%"
echo [%date% %time%] exited code=%errorlevel% >> "%OUT_LOG%"
if exist "%STOP_FILE%" (
  del /q "%STOP_FILE%"
  echo [%date% %time%] stop requested, exiting supervisor >> "%OUT_LOG%"
  goto end
)
timeout /t 3 /nobreak >nul
goto loop

:end
endlocal
