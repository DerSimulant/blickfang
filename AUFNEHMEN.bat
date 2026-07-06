@echo off
chcp 65001 >nul
title blickfang — Aufnahme
color 0E

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Video aufnehmen                    ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: Name abfragen
set /p PERSON="Name der Person: "
if "%PERSON%"=="" (
    echo [FEHLER] Bitte einen Namen eingeben.
    pause
    exit /b 1
)

echo.
echo Was soll aufgenommen werden?
echo.
echo   [1] SIGNAL   — Person erzeugt bewusst ihr Signal
echo   [2] RUHE     — Person ruht (inkl. unwillkürlicher Bewegungen)
echo   [3] UNRUHE   — Chorea/Tremor/Spastik-Phase
echo.
set /p WAHL="Auswahl (1/2/3): "

if "%WAHL%"=="1" set LABEL=signal
if "%WAHL%"=="2" set LABEL=ruhe
if "%WAHL%"=="3" set LABEL=unruhe

if "%LABEL%"=="" (
    echo [FEHLER] Ungültige Auswahl.
    pause
    exit /b 1
)

echo.
set /p DAUER="Aufnahmedauer in Sekunden (Standard: 60): "
if "%DAUER%"=="" set DAUER=60

echo.
echo ──────────────────────────────────────────────────────────
echo Starte Aufnahme:
echo   Person:  %PERSON%
echo   Label:   %LABEL%
echo   Dauer:   %DAUER%s
echo ──────────────────────────────────────────────────────────
echo.
echo Drücke Q oder ESC zum vorzeitigen Beenden.
echo.

blickfang-record --person %PERSON% --label %LABEL% --duration %DAUER%

echo.
echo ──────────────────────────────────────────────────────────
echo [✓] Aufnahme beendet!
echo.
echo Die Aufnahme liegt im Ordner "recordings/".
echo Nächster Schritt: ANNOTIEREN.bat oder direkt KALIBRIEREN.bat
echo.
pause
