@echo off
chcp 65001 >nul
title blickfang — Kalibrierung
color 0A

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Kalibrierung                       ║
echo ║   Findet das beste Signal der Person                    ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo Die Kalibrierung läuft interaktiv:
echo   1. Person erzeugt ihr Signal mehrfach (selbst getaktet)
echo   2. Ruhephase (3 Minuten, inkl. unwillkürlicher Bewegungen)
echo   3. Validierungsrunde (10 Signale + 2 min Ruhe)
echo.
echo Das System findet automatisch den besten Kanal.
echo.
echo ──────────────────────────────────────────────────────────
echo.

blickfang-calibrate

echo.
echo ──────────────────────────────────────────────────────────
echo [✓] Kalibrierung abgeschlossen!
echo.
echo Das Profil liegt unter config/profiles/
echo Nächster Schritt: START.bat
echo.
pause
