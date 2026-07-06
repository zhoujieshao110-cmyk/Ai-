@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "PID_FILE=%ROOT%server.pid"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$pidFile = '%PID_FILE%'; if (Test-Path $pidFile) { $pidText = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1; if ($pidText -match '^\d+$') { Stop-Process -Id ([int]$pidText) -Force -ErrorAction SilentlyContinue } }; $conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($conn) { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue }; Remove-Item $pidFile -Force -ErrorAction SilentlyContinue"

echo Backend stopped.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1"
exit /b 0
