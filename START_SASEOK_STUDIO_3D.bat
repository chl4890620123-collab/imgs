@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PY_CMD=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.11 or newer is required. Install from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set "PY_CMD=python"
)

%PY_CMD% -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo Installing Studio Python dependencies...
  %PY_CMD% -m pip install -r studio\requirements.txt
  if errorlevel 1 goto :failed
)

if not exist saseok_studio_project.json (
  %PY_CMD% studio\bootstrap.py
  if errorlevel 1 goto :failed
)

echo Starting Saseok Studio with native Blender 3D editing...
%PY_CMD% studio\app.py saseok_studio_project.json
if errorlevel 1 goto :failed
exit /b 0

:failed
echo Studio could not start. Check the error text above.
pause
exit /b 1
