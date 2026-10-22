@echo off
cd /d "%~dp0"
if exist "dist\DeviceViewer\DeviceViewer.exe" (
    start "" "dist\DeviceViewer\DeviceViewer.exe"
) else (
    start "" ".venv\Scripts\pythonw.exe" "main.py"
)
