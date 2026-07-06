@echo off
chcp 65001 >nul
title blickfang — Annotieren
color 0D

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Aufnahmen annotieren               ║
echo ║   Markiere Signal-/Ruhe-/Unruhe-Abschnitte             ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: Zeige verfügbare Aufnahmen
echo Verfügbare Aufnahmen:
echo ──────────────────────────────────────────────────────────
echo.

set COUNT=0
for /d %%D in (recordings\*) do (
    set /a COUNT+=1
    echo   %%~nxD
)

if %COUNT%==0 (
    echo   [Keine Aufnahmen gefunden]
    echo.
    echo   Bitte zuerst AUFNEHMEN.bat ausführen.
    pause
    exit /b 1
)

echo.
echo ──────────────────────────────────────────────────────────
echo.
set /p SESSION="Ordnername der Aufnahme (kopieren von oben): "

if "%SESSION%"=="" (
    echo [FEHLER] Bitte einen Ordnernamen eingeben.
    pause
    exit /b 1
)

echo.
echo Starte Annotations-Tool...
echo.
echo Tasten:
echo   S = Signal markieren    R = Ruhe markieren
echo   U = Unruhe markieren    A = Artefakt markieren
echo   Leertaste = Play/Pause  Strg+Z = Rückgängig
echo   ESC = Beenden (speichert automatisch)
echo.

blickfang-annotate recordings\%SESSION%

echo.
echo [✓] Annotationen gespeichert.
pause
