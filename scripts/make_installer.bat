@echo off
chcp 65001 >nul
title Engram — Build Installer
cd /d "%~dp0\.."

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║     Engram Installer Builder             ║
echo  ║  Builds EXEs + creates Setup.exe         ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── Step 1: Check prerequisites ─────────────────────────
echo [1/4] Checking prerequisites...

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12+ from python.org
    pause
    exit /b 1
)
echo   Python: OK

REM Check Inno Setup
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo   Inno Setup: NOT FOUND
    echo.
    echo   Inno Setup 6 is required to build the installer.
    echo   Download from: https://jrsoftware.org/isdl.php
    echo   Or run: winget install JRSoftware.InnoSetup
    echo.
    echo   After installing, run this script again.
    echo   (PyInstaller builds will still proceed without it)
    echo.
) else (
    echo   Inno Setup: OK
)

REM ── Step 2: Build both apps ─────────────────────────────
echo.
echo [2/4] Setting up build environment...

if not exist .venv_build (
    python -m venv .venv_build
)

.venv_build\Scripts\pip install --quiet -e ".[dev]" pyinstaller 2>&1
.venv_build\Scripts\pip install --quiet -e "dbbuilder[dev]" 2>&1

echo.
echo [3/4] Building applications with PyInstaller...
echo.
echo   Building Engram server...
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
    scripts\run_server.py >nul 2>&1

if errorlevel 1 (
    echo   [ERROR] Engram build failed.
    pause
    exit /b 1
)
echo   Engram: OK

echo   Building DB Builder...
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
    dbbuilder\src\db_builder\__main__.py >nul 2>&1

if errorlevel 1 (
    echo   [ERROR] DB Builder build failed.
    pause
    exit /b 1
)
echo   DB Builder: OK

REM ── Step 3: Create portable ZIP ─────────────────────────
echo.
echo [4/4] Creating distribution packages...

if exist dist\installer rmdir /s /q dist\installer
mkdir dist\installer 2>nul
xcopy /E /I /Q dist\engram dist\installer\engram >nul
xcopy /E /I /Q dist\engram-db-builder dist\installer\engram-db-builder >nul
copy LICENSE dist\installer\ >nul
copy README.md dist\installer\ >nul
copy .env.example dist\installer\ >nul
xcopy /E /I /Q data\config dist\installer\data\config >nul

REM Create portable ZIP
powershell -Command "Compress-Archive -Path 'dist\installer\*' -DestinationPath 'dist\Engram-0.1.0-portable.zip' -Force"
echo   Portable ZIP: dist\Engram-0.1.0-portable.zip

REM ── Step 4: Create installer if Inno Setup available ────
if defined ISCC (
    echo   Building installer with Inno Setup...
    "%ISCC%" /Q scripts\engram-setup.iss
    if errorlevel 1 (
        echo   [WARNING] Installer build failed. Portable ZIP is still available.
    ) else (
        echo   Installer: dist\Engram-Setup-0.1.0.exe
    )
) else (
    echo   [SKIP] Installer — Inno Setup not found
)

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║           BUILD COMPLETE!                ║
echo  ╠══════════════════════════════════════════╣
echo  ║                                          ║
echo  ║  Portable ZIP:                           ║
echo  ║    dist\Engram-0.1.0-portable.zip        ║
echo  ║                                          ║
if defined ISCC (
echo  ║  Installer:                              ║
echo  ║    dist\Engram-Setup-0.1.0.exe           ║
echo  ║                                          ║
)
echo  ╚══════════════════════════════════════════╝
echo.
pause
