@echo off
REM Engram Windows Build Script
REM Run this on Windows with Python 3.12+ installed
REM Creates: dist/engram/engram.exe (one-folder mode)

echo === Engram Windows Build ===
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.12+ from python.org
    pause
    exit /b 1
)

REM Create build venv
if not exist .venv_build (
    echo Creating build venv...
    python -m venv .venv_build
)

echo Installing dependencies...
.venv_build\Scripts\pip install -e ".[dev]" pyinstaller 2>&1

echo.
echo Building Engram...
.venv_build\Scripts\pyinstaller ^
    --name engram ^
    --onedir ^
    --noconfirm ^
    --add-data "frontend/dist;frontend/dist" ^
    --add-data "data/config;data/config" ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import chromadb ^
    --hidden-import chromadb.api ^
    --hidden-import chromadb.config ^
    --hidden-import backend ^
    --hidden-import backend.main ^
    --hidden-import backend.config ^
    --hidden-import backend.agents ^
    --hidden-import backend.knowledge ^
    --hidden-import backend.memory ^
    --hidden-import backend.utils ^
    --hidden-import backend.sync ^
    --collect-all chromadb ^
    scripts\run_server.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED. Check errors above.
    pause
    exit /b 1
)

echo.
echo === Build Complete ===
echo Output: dist\engram\engram.exe
echo.
echo To run: dist\engram\engram.exe
echo Then open: http://localhost:8000
echo.
pause
