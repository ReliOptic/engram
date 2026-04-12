@echo off
chcp 65001 >nul
title Engram DB Builder - Setup
echo ============================================
echo  Engram DB Builder - Initial Setup
echo ============================================
echo.
echo  This will create a virtual environment and
echo  install all dependencies. Run once only.
echo.

cd /d "%~dp0"

:: Check Python
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3 not found. Install from python.org
    pause
    exit /b 1
)

echo [1/3] Creating virtual environment...
if exist ".venv" (
    echo  .venv already exists, skipping...
) else (
    py -3 -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv.
        pause
        exit /b 1
    )
)

echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
pip install -e .
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/3] Creating data directories...
mkdir data\raw\manuals 2>nul
mkdir data\raw\weekly_reports 2>nul
mkdir data\raw\sops 2>nul
mkdir data\raw\images 2>nul
mkdir data\raw\misc 2>nul

echo.
echo ============================================
echo  SETUP COMPLETE!
echo.
echo  To run:  double-click "run.bat"
echo  Config:  edit ".env" (copy from .env.example)
echo ============================================
echo.

if not exist ".env" (
    copy .env.example .env >nul 2>&1
    echo  Created .env from .env.example
    echo  Edit .env to set your OPENROUTER_API_KEY
    echo.
)

pause
