@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0\..\backend-hk"

if not exist ".venv\" (
    echo [init] creating virtual environment...
    py -3.11 -m venv .venv
    if errorlevel 1 (
        echo [error] failed to create virtual environment
        pause
        exit /b 1
    )
    echo [init] installing dependencies...
    .venv\Scripts\python.exe -m pip install -q -r requirements.txt
    if errorlevel 1 (
        echo [error] failed to install dependencies
        pause
        exit /b 1
    )
)

if not exist ".env" (
    if exist ".env.example" (
        echo [init] copying .env.example to .env
        copy .env.example .env
        echo [warn] please edit .env and fill in OPENAI_API_KEY and other configs
        pause
        exit /b 0
    ) else (
        echo [warn] .env not found, copy .env.example to .env and fill in configs
        pause
        exit /b 1
    )
)

echo [start] backend-hk -> http://127.0.0.1:9000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload

endlocal
