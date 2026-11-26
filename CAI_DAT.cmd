@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
where ffmpeg >nul 2>nul
if errorlevel 1 winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
echo Cai dat xong. Dong va mo lai terminal neu vua cai FFmpeg.
pause
