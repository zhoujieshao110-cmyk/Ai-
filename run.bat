@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "PYTHON=%ROOT%..\.venv\Scripts\python.exe"
set "HEALTH_URL=http://127.0.0.1:8765/"
set "APP_URL=http://127.0.0.1:8765/studio/"
set "OUT_LOG=%ROOT%server.out.log"
set "ERR_LOG=%ROOT%server.err.log"
set "PID_FILE=%ROOT%server.pid"

if not exist "%PYTHON%" (
  echo [ERROR] Python virtual environment not found:
  echo %PYTHON%
  echo.
  echo Please create .venv first.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [void](Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 2); exit 0 } catch { exit 1 }"
if %errorlevel%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; if ($p) { Set-Content -Encoding ascii '%PID_FILE%' $p }"
  echo Backend is already running. Opening the app...
  explorer "%APP_URL%" >nul 2>nul
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1"
  exit /b 0
)

echo Starting Short Video Studio backend...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath '%PYTHON%' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8765' -WorkingDirectory '%ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%OUT_LOG%' -RedirectStandardError '%ERR_LOG%' -PassThru; Set-Content -Encoding ascii '%PID_FILE%' $p.Id"
if errorlevel 1 (
  echo [ERROR] Failed to spawn backend process.
  pause
  exit /b 1
)

for /l %%i in (1,1,20) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [void](Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 2); exit 0 } catch { exit 1 }"
  if not errorlevel 1 goto open_app
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1"
)

echo [ERROR] Backend did not become ready.
if exist "%ERR_LOG%" (
  echo.
  echo ---- server.err.log ----
  type "%ERR_LOG%"
)
if exist "%OUT_LOG%" (
  echo.
  echo ---- server.out.log ----
  type "%OUT_LOG%"
)
pause
exit /b 1

:open_app
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; if ($p) { Set-Content -Encoding ascii '%PID_FILE%' $p }"
echo Backend is ready. Opening the app...
explorer "%APP_URL%" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1"
exit /b 0
