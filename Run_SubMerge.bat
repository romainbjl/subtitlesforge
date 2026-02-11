@echo off
title SubMerge Pro Launcher
echo Starting SubMerge Pro...
echo.

:: Move to the directory where this .bat file lives
cd /d "%~dp0"

:: Check if uv is installed
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] uv is not installed or not in PATH.
    echo Please install it first: https://astral.sh/uv/install.ps1
    pause
    exit /b
)

:: Run the streamlit app using uv
:: We use "%~dp0app.py" to give uv the absolute, un-renameable path
uv run streamlit run "%~dp0app.py" --server.headless false

pause