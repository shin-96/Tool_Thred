@echo off
cd /d "%~dp0"
if exist "dist\ThreadsStudioPro21\READY" (
  start "" "dist\ThreadsStudioPro21\ThreadsStudioPro.exe"
  exit /b
)
if exist "dist\ThreadsStudioPro\READY" (
  start "" "dist\ThreadsStudioPro\ThreadsStudioPro.exe"
  exit /b
)
python pro.py
if errorlevel 1 pause
