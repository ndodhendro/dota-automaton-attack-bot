@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
if not exist ".venv\Scripts\python.exe" (
  echo Membuat virtual environment...
  py -3.12 -m venv .venv
  if errorlevel 1 py -3 -m venv .venv
)
".venv\Scripts\python.exe" -c "import cv2, mss, rapidocr, rapidfuzz" 1>nul 2>nul
if errorlevel 1 (
  echo Menginstal dependency. Pertama kali butuh beberapa menit...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m automaton_bot %*
