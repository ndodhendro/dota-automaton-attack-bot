@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Dota Automaton Attack Bot
set PYTHONUNBUFFERED=1

rem Double-click starts cmd /c, which closes the window as soon as this file exits.
rem Open a window that stays up, then leave the temporary one.
echo %cmdcmdline% | find /i " /c " >nul
if not errorlevel 1 (
  if not defined BOT_KEEP (
    set BOT_KEEP=1
    start "Dota Automaton Attack Bot" cmd /k "%~f0" %*
    exit /b 0
  )
)

echo Dota Automaton Attack Bot
echo Folder: %cd%
echo.

set "PY="
where py >nul 2>&1
if not errorlevel 1 (
  py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)" >nul 2>&1
  if not errorlevel 1 set "PY=py -3.12"
  if not defined PY (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
  )
)
if not defined PY (
  where python >nul 2>&1
  if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python"
  )
)
if not defined PY goto :no_python

if not exist ".venv\Scripts\python.exe" (
  echo Creating the virtual environment...
  call %PY% -m venv .venv
  if errorlevel 1 goto :venv_fail
)
if not exist ".venv\Scripts\python.exe" goto :venv_fail

".venv\Scripts\python.exe" -c "import cv2, mss, rapidocr, rapidfuzz" >nul 2>&1
if errorlevel 1 (
  echo Installing dependencies. The first run takes a few minutes.
  echo Do not close this window.
  echo.
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :pip_fail
  ".venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 goto :pip_fail
)

echo Running the Dota Automaton Attack bot...
echo.
".venv\Scripts\python.exe" -m automaton_bot %*
if errorlevel 1 goto :bot_fail
echo.
echo Bot finished.
pause
exit /b 0

:no_python
echo Python 3.11 or newer was not found on this PC.
echo.
echo 1. Open https://www.python.org/downloads/release/python-31210/
echo 2. Run the 64-bit Windows installer
echo 3. Check "Add python.exe to PATH" and "py launcher"
echo 4. Close this window, then run run.bat again
echo.
pause
exit /b 1

:venv_fail
echo.
echo Failed to create the .venv folder.
echo Python was found, but the virtual environment was not created.
echo.
pause
exit /b 1

:pip_fail
echo.
echo Dependency installation failed.
echo Check your internet connection, then run run.bat again.
echo If the message mentions a DLL or onnxruntime, install the
echo Microsoft Visual C++ Redistributable x64, then try again.
echo.
pause
exit /b 1

:bot_fail
echo.
echo The bot stopped. The error is above.
echo.
pause
exit /b 1
