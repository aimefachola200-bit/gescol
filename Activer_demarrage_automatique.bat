@echo off
chcp 65001 >nul
REM SCOLARIS - Conception : Maitre Aime FACHOLA
REM Fait demarrer SCOLARIS tout seul a chaque allumage du PC (a lancer une seule fois).
cd /d "%~dp0"
if not exist "venv\Scripts\pythonw.exe" (
  echo SCOLARIS n'est pas encore installe : lancez d'abord lancer.bat une fois.
  pause
  exit /b 1
)
set "CIBLE=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SCOLARIS.vbs"
(
echo Set sh = CreateObject^("WScript.Shell"^)
echo sh.CurrentDirectory = "%~dp0"
echo sh.Run """%~dp0venv\Scripts\pythonw.exe"" ""%~dp0scolaris_serveur.py"" --sans-navigateur", 0, False
) > "%CIBLE%"
if not exist "%CIBLE%" (
  echo Echec : impossible d'ecrire dans le dossier Demarrage de Windows.
  pause
  exit /b 1
)
echo.
echo  OK : SCOLARIS demarrera tout seul a chaque allumage du PC.
echo  Il demarre aussi maintenant.
echo.
wscript "%CIBLE%"
timeout /t 8 >nul
