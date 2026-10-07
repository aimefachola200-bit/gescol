@echo off
chcp 65001 >nul
REM GESCOL - Conception : Maitre Aime FACHE
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\GESCOL.vbs" 2>nul
echo GESCOL ne demarrera plus tout seul avec le PC.
timeout /t 5 >nul
