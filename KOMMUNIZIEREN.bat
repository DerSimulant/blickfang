@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title blickfang — Kommunikation (Vollversion)
color 0F

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Kommunikation                      ║
echo ║   Phrasen · Buchstabieren · Ja/Nein · Notruf           ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo Modi:
echo   Hauptmenü → Schnell-Phrasen (Bedürfnisse, Schmerzen, ...)
echo              → Buchstabieren (Frequenz-Layout, Wortvorschläge)
echo              → Ja / Nein / Passe
echo              → HILFE! (Notruf-Alarm)
echo.
echo ──────────────────────────────────────────────────────────
echo.
echo Steuerung:
echo   [1] Nur Tastatur (Leertaste = Signal) — zum Testen
echo   [2] Mit Kamera (Profil einer Person laden)
echo.
set /p MODUS="Auswahl (1/2): "

if "%MODUS%"=="2" (
    echo.
    echo Verfügbare Profile:
    for %%F in (config\profiles\*.yaml) do echo   %%~nF
    echo.
    set /p PERSON="Name der Person: "
    echo.
    echo Starte mit Kamera...
    blickfang-comm --person !PERSON!
) else (
    echo.
    echo ──────────────────────────────────────────────────────────
    echo Starte im Tastatur-Modus...
    echo.
    echo   Leertaste / Enter = Signal geben
    echo   F1 = Hauptmenü
    echo   F2 = Phrasen
    echo   F3 = Buchstabieren
    echo   F4 = Ja/Nein
    echo   ESC = Beenden
    echo ──────────────────────────────────────────────────────────
    echo.
    blickfang-comm --key-only --windowed
)

echo.
echo [Beendet]
pause
