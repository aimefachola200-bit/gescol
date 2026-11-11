@echo off
chcp 65001 >nul
REM SCOLARIS - Conception : Maitre Aime FACHOLA
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SCOLARIS.vbs" 2>nul
echo SCOLARIS ne demarrera plus tout seul avec le PC.
timeout /t 5 >nul
