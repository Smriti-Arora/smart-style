@echo off
cd /d "%~dp0"
set VIRTUAL_ENV=%~dp0myenv
set PATH=%~dp0myenv\Scripts;%PATH%
set TRANSFORMERS_NO_TF=1
set USE_TF=0
set TF_CPP_MIN_LOG_LEVEL=3
set TF_ENABLE_ONEDNN_OPTS=0

echo Stopping old servers...
for %%P in (8501 8502 8503 8000) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%A >nul 2>&1
  )
)

if not exist "%~dp0frontend\dist\index.html" (
  echo Building React UI...
  pushd "%~dp0frontend"
  call npm install
  call npm run build
  popd
)

echo Starting Smart Style on http://127.0.0.1:8000
echo First boot loads CLIP — wait about a minute.
"%~dp0myenv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000
