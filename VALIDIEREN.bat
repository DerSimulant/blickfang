@echo off
chcp 65001 >nul
title blickfang — Validierung
color 0C

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Detektor validieren                ║
echo ║   Testet wie gut das Profil die Signale erkennt         ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: Zeige verfügbare Profile
echo Verfügbare Profile:
echo ──────────────────────────────────────────────────────────
for %%F in (config\profiles\*.yaml) do echo   %%~nF
echo.

set /p PROFIL="Profilname (ohne .yaml): "
if "%PROFIL%"=="" (
    echo [FEHLER] Bitte ein Profil angeben.
    pause
    exit /b 1
)

echo.
echo Optionen:
echo   [1] Standard-Validierung (TP/FP/Latenz anzeigen)
echo   [2] Schwellwert-Sweep (optimalen Schwellwert finden)
echo.
set /p MODUS="Auswahl (1/2): "

echo.
echo ──────────────────────────────────────────────────────────
echo.

if "%MODUS%"=="2" (
    blickfang-validate --profile config\profiles\%PROFIL%.yaml --sessions recordings --sweep
) else (
    blickfang-validate --profile config\profiles\%PROFIL%.yaml --sessions recordings
)

echo.
pause
