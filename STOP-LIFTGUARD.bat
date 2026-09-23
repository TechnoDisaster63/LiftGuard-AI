@echo off
rem Stops the LiftGuard backend and dashboard started by START-LIFTGUARD.bat.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-liftguard.ps1"
timeout /t 3 >nul
