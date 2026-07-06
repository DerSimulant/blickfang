@echo off
chcp 65001 >nul
title blickfang — Installation
color 0A

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Erstinstallation                   ║
echo ║   Kommunikationshilfe für Menschen mit Behinderung      ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: Prüfe ob Python installiert ist
python --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Python wurde nicht gefunden!
    echo.
    echo Bitte installiere Python 3.10+ von:
    echo   https://www.python.org/downloads/
    echo.
    echo WICHTIG: Bei der Installation "Add Python to PATH" ankreuzen!
    echo.
    pause
    exit /b 1
)

echo [✓] Python gefunden:
python --version
echo.

:: Prüfe ob Git installiert ist
git --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Git nicht gefunden — lade Repository als ZIP...
    echo.
    
    :: Ohne Git: pip install direkt von GitHub
    echo Installiere blickfang von GitHub...
    pip install git+https://github.com/DerSimulant/blickfang.git
    if errorlevel 1 (
        echo [FEHLER] Installation fehlgeschlagen.
        pause
        exit /b 1
    )
) else (
    echo [✓] Git gefunden:
    git --version
    echo.

    :: Repository klonen falls nicht vorhanden
    if not exist "%~dp0src" (
        echo Klone Repository...
        git clone https://github.com/DerSimulant/blickfang.git "%~dp0repo_temp"
        xcopy /E /I /Y "%~dp0repo_temp\*" "%~dp0" >nul 2>&1
        rmdir /S /Q "%~dp0repo_temp" >nul 2>&1
    ) else (
        echo [✓] Repository bereits vorhanden — aktualisiere...
        cd /d "%~dp0"
        git pull origin main
    )
    
    echo.
    echo Installiere Python-Abhängigkeiten...
    cd /d "%~dp0"
    pip install -e ".[dev]"
)

if errorlevel 1 (
    echo.
    echo [FEHLER] Installation fehlgeschlagen. Siehe Fehler oben.
    pause
    exit /b 1
)

:: Frontend-Build prüfen
echo.
echo Prüfe Frontend...
if exist "%~dp0frontend\dist\index.html" (
    echo [✓] Frontend bereits gebaut.
) else (
    echo [INFO] Frontend muss gebaut werden.
    node --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [HINWEIS] Node.js nicht gefunden.
        echo Das Frontend wird beim nächsten Update mitgeliefert.
        echo Oder installiere Node.js von https://nodejs.org
    ) else (
        echo Baue Frontend (React + Vite)...
        cd /d "%~dp0frontend"
        call npm install
        call npm run build
        cd /d "%~dp0"
        echo [✓] Frontend gebaut.
    )
)

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  [✓] Installation erfolgreich!                          ║
echo ╠══════════════════════════════════════════════════════════╣
echo ║                                                          ║
echo ║  Nächste Schritte:                                       ║
echo ║    1. Doppelklick auf SELFTEST.bat (prüft alles)         ║
echo ║    2. Doppelklick auf START.bat (Kommunikation starten)  ║
echo ║                                                          ║
echo ║  Die Oberfläche öffnet sich im Browser (localhost:8000)  ║
echo ║  Leertaste = Signal | F11 = Vollbild                     ║
echo ║                                                          ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
pause
