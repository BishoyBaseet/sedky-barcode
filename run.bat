@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 app_server.py
    if not errorlevel 1 goto finished
)

where python >nul 2>nul
if not errorlevel 1 (
    python app_server.py
    if not errorlevel 1 goto finished
)

echo Python 3 is required to run the local database app.
echo Install Python from https://www.python.org/downloads/windows/ and select "Add python.exe to PATH" during setup.
echo Then double-click this file again.
start "" "https://www.python.org/downloads/windows/"
pause

:finished
endlocal
