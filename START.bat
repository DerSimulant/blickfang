@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title blickfang — Sprachcomputer
color 0F

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Sprachcomputer                     ║
echo ║   Phrasen · Buchstabieren · Ja/Nein · Notruf           ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo Die Kommunikations-Oberfläche öffnet sich im Browser.
echo.
echo ──────────────────────────────────────────────────────────
echo.
echo Steuerung:
echo   [1] Nur Tastatur (Leertaste = Signal) — zum Testen
echo   [2] Mit Kamera (Profil einer Person laden)
echo.
set /p MODUS="Auswahl (1/2): "

echo.
echo Scan-Geschwindigkeit (Sekunden pro Schritt):
echo   Standard: 1.5 — Langsamer = sicherer, Schneller = effizienter
set /p SPEED="Geschwindigkeit [1.5]: "
if "%SPEED%"=="" set SPEED=1.5

if "%MODUS%"=="2" (
    echo.
    echo Verfügbare Profile:
    if exist config\profiles\*.yaml (
        for %%F in (config\profiles\*.yaml) do echo   %%~nF
    ) else (
        echo   (keine Profile gefunden — bitte erst KALIBRIEREN.bat ausführen)
    )
    echo.
    set /p PERSON="Name der Person: "
    echo.
    echo ──────────────────────────────────────────────────────────
    echo Starte Server mit Kamera-Erkennung...
    echo Browser öffnet sich automatisch auf http://localhost:8000
    echo.
    echo   Im Browser: Leertaste/Enter = Signal
    echo   F11 = Vollbild (empfohlen!)
    echo   Hier: Strg+C = Server beenden
    echo ──────────────────────────────────────────────────────────
    echo.
    blickfang-server --person !PERSON! --camera --speed %SPEED%
) else (
    echo.
    echo ──────────────────────────────────────────────────────────
    echo Starte Server im Tastatur-Modus...
    echo Browser öffnet sich automatisch auf http://localhost:8000
    echo.
    echo   Im Browser: Leertaste/Enter = Signal
    echo   F11 = Vollbild (empfohlen!)
    echo   Hier: Strg+C = Server beenden
    echo ──────────────────────────────────────────────────────────
    echo.
    blickfang-server --key-only --speed %SPEED%
)

echo.
echo [Server beendet]
pause
