@echo off
chcp 65001 >nul
title Engram — Windows Build
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║       Engram Windows Build Script        ║
echo  ║  Builds both Engram + DB Builder as EXE  ║
echo  ╚══════════════════════════════════════════╝
echo.

REM Require Python 3.12+
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12+ from python.org
    pause
    exit /b 1
)

REM ── Build venv ──────────────────────────────────────────
if not exist .venv_build (
    echo [1/5] Creating build venv...
    python -m venv .venv_build
) else (
    echo [1/5] Build venv exists, reusing...
)

echo [2/5] Installing main app dependencies + PyInstaller...
.venv_build\Scripts\pip install --quiet -e ".[dev]" pyinstaller 2>&1

echo [3/5] Installing DB Builder dependencies...
.venv_build\Scripts\pip install --quiet -e "dbbuilder[dev]" 2>&1

REM ── Build Engram (main web app) ─────────────────────────
echo.
echo [4/5] Building Engram server...
.venv_build\Scripts\pyinstaller ^
    --name engram ^
    --onedir ^
    --noconfirm ^
    --icon scripts\engram.ico ^
    --add-data "frontend/dist;frontend/dist" ^
    --add-data "data/config;data/config" ^
    --add-data ".env.example;." ^
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
    echo [ERROR] Engram build failed.
    pause
    exit /b 1
)

REM ── Build DB Builder (PySide6 GUI app) ──────────────────
echo.
echo [5/5] Building Engram DB Builder...
.venv_build\Scripts\pyinstaller ^
    --name engram-db-builder ^
    --onedir ^
    --noconfirm ^
    --windowed ^
    --icon scripts\engram-db-builder.ico ^
    --add-data "dbbuilder/.env.example;." ^
    --hidden-import db_builder ^
    --hidden-import db_builder.app ^
    --hidden-import db_builder.config ^
    --hidden-import db_builder.enrichment ^
    --hidden-import db_builder.store ^
    --hidden-import db_builder.store.chromadb_writer ^
    --hidden-import db_builder.embedding ^
    --hidden-import db_builder.embedding.client ^
    --hidden-import db_builder.ui ^
    --hidden-import db_builder.ui.main_window ^
    --hidden-import db_builder.ui.build_panel ^
    --hidden-import db_builder.ui.file_panel ^
    --hidden-import db_builder.ui.settings_dialog ^
    --collect-all chromadb ^
    --collect-all PySide6 ^
    dbbuilder\src\db_builder\__main__.py

if errorlevel 1 (
    echo [ERROR] DB Builder build failed.
    pause
    exit /b 1
)

REM ── Organize output ─────────────────────────────────────
echo.
echo Organizing installer files...
if exist dist\installer rmdir /s /q dist\installer
mkdir dist\installer 2>nul
xcopy /E /I /Q dist\engram dist\installer\engram >nul
xcopy /E /I /Q dist\engram-db-builder dist\installer\engram-db-builder >nul
copy scripts\engram.ico dist\installer\ >nul 2>&1
copy LICENSE dist\installer\ >nul

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║           BUILD COMPLETE!                ║
echo  ╠══════════════════════════════════════════╣
echo  ║  dist\installer\engram\engram.exe        ║
echo  ║  dist\installer\engram-db-builder\       ║
echo  ║        engram-db-builder.exe             ║
echo  ╠══════════════════════════════════════════╣
echo  ║  Next: run Inno Setup on                 ║
echo  ║  scripts\engram-setup.iss                ║
echo  ╚══════════════════════════════════════════╝
echo.
pause
