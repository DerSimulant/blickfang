@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title blickfang — Kommunikation
color 0F

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Kommunikation starten              ║
echo ║   JA / NEIN / PASSE                                    ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: Prüfe ob Profile vorhanden sind
set PROFILE_COUNT=0
for %%F in (config\profiles\*.yaml) do set /a PROFILE_COUNT+=1

if %PROFILE_COUNT%==0 (
    echo [!] Noch kein Profil vorhanden.
    echo.
    echo Optionen:
    echo   [1] Kalibrierung starten (empfohlen)
    echo   [2] Nur mit Tastatur testen (ohne Kamera)
    echo.
    set /p WAHL="Auswahl (1/2): "
    
    if "!WAHL!"=="2" (
        echo.
        echo Starte im Tastatur-Modus...
        echo Leertaste = Signal auslösen
        echo.
        blickfang-run --key-only
        goto :end
    ) else (
        echo.
        echo Starte Kalibrierung...
        blickfang-calibrate
    )
)

:: Zeige verfügbare Profile
echo Verfügbare Profile:
echo ──────────────────────────────────────────────────────────
echo.

set IDX=0
for %%F in (config\profiles\*.yaml) do (
    set /a IDX+=1
    echo   %%~nF
)

echo.
set /p PERSON="Name der Person (oder Enter für neuestes Profil): "

echo.
echo ──────────────────────────────────────────────────────────
echo Starte Kommunikation...
echo.
echo   Signal geben = JA / NEIN / PASSE wird gescannt
echo   Sprachausgabe bestätigt die Auswahl
echo   Jede Auswahl ist abbrechbar (2.5s Countdown)
echo.
echo   Fenster schließen oder Strg+C = Beenden
echo ──────────────────────────────────────────────────────────
echo.

if "%PERSON%"=="" (
    blickfang-run
) else (
    blickfang-run --person %PERSON%
)

:end
echo.
echo [Beendet]
pause
