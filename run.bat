@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Automaton Attack Bot
set PYTHONUNBUFFERED=1

rem Double-click starts cmd /c, which closes the window as soon as this file exits.
rem Open a window that stays up, then leave the temporary one.
echo %cmdcmdline% | find /i " /c " >nul
if not errorlevel 1 (
  if not defined BOT_KEEP (
    set BOT_KEEP=1
    start "Automaton Attack Bot" cmd /k "%~f0" %*
    exit /b 0
  )
)

echo Automaton Attack Bot
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
  echo Membuat virtual environment...
  call %PY% -m venv .venv
  if errorlevel 1 goto :venv_fail
)
if not exist ".venv\Scripts\python.exe" goto :venv_fail

".venv\Scripts\python.exe" -c "import cv2, mss, rapidocr, rapidfuzz" >nul 2>&1
if errorlevel 1 (
  echo Menginstal dependency. Pertama kali butuh beberapa menit.
  echo Jangan ditutup.
  echo.
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :pip_fail
  ".venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 goto :pip_fail
)

echo Menjalankan bot...
echo.
".venv\Scripts\python.exe" -m automaton_bot %*
if errorlevel 1 goto :bot_fail
echo.
echo Bot selesai.
pause
exit /b 0

:no_python
echo Python 3.11 atau yang lebih baru tidak ditemukan di PC ini.
echo.
echo 1. Buka https://www.python.org/downloads/release/python-31210/
echo 2. Jalankan Windows installer 64-bit
echo 3. Centang "Add python.exe to PATH" dan "py launcher"
echo 4. Tutup jendela ini, lalu jalankan run.bat lagi
echo.
pause
exit /b 1

:venv_fail
echo.
echo Gagal membuat folder .venv.
echo Python ketemu, tetapi virtual environment tidak terbuat.
echo.
pause
exit /b 1

:pip_fail
echo.
echo Instal dependency gagal.
echo Cek koneksi internet, lalu jalankan run.bat lagi.
echo Kalau pesannya menyebut DLL atau onnxruntime, install
echo Microsoft Visual C++ Redistributable x64, lalu ulangi.
echo.
pause
exit /b 1

:bot_fail
echo.
echo Bot berhenti. Pesan error ada di atas.
echo.
pause
exit /b 1
