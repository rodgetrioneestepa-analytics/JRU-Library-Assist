@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create the project environment first. See rag_backend\README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m rag_backend
pause
