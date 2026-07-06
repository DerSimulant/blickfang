@echo off
chcp 65001 >nul
title blickfang — Update
color 0B

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Aktualisierung                     ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

git --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Git nicht installiert — manuelles Update nötig.
    echo Bitte INSTALL.bat erneut ausführen.
    pause
    exit /b 1
)

echo Lade neueste Version...
git pull origin main

echo.
echo Aktualisiere Abhängigkeiten...
pip install -e ".[dev]"

echo.
echo [✓] Update abgeschlossen!
pause
