@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0\..\frontend"

if not exist "node_modules\" (
    echo [init] installing dependencies...
    npm install
    if errorlevel 1 (
        echo [error] failed to install dependencies
        pause
        exit /b 1
    )
)

echo [start] frontend dev server -> http://localhost:5173
npm run dev

endlocal
