@echo off
rem Double-click to run LiftGuard on Windows: installs what's missing, starts
rem the backend and the dashboard, and opens the app in your browser.
rem Stop it with STOP-LIFTGUARD.bat (or press Enter in this window).
title LiftGuard
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-liftguard.ps1" %*
if errorlevel 1 (
  echo.
  echo LiftGuard did not start. The message above says why.
  pause
)
