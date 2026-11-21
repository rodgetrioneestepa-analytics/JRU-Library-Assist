@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if %errorlevel% equ 0 (
  node server.mjs
) else (
  for /d %%D in ("C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.*") do (
    if exist "%%~D\dependencies\node\bin\node.exe" (
      "%%~D\dependencies\node\bin\node.exe" server.mjs
      exit /b
    )
  )
  echo Install Node.js 22 or later, then run this file again.
  pause
)
