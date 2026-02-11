@echo off
title SubMerge Pro Launcher
echo Starting SubMerge Pro...
echo.

:: Check if uv is installed
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] uv is not installed or not in PATH.
    echo Please install it first: https://astral.sh/uv/install.ps1
    pause
    exit /b
)

:: Run the streamlit app using uv
uv run streamlit run app.py --server.headless false

pause