@echo off
chcp 65001 >nul
title blickfang — Selbsttest
color 0B

echo ╔══════════════════════════════════════════════════════════╗
echo ║          blickfang — Selbsttest                         ║
echo ║   Prüft: Python, Kamera, TTS, MediaPipe-Modell         ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

blickfang-selftest

echo.
echo ──────────────────────────────────────────────────────────
echo Wenn alles grün ist: Weiter mit AUFNEHMEN.bat oder KALIBRIEREN.bat
echo.
pause
