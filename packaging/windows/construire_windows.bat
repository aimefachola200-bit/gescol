@echo off
chcp 65001 >nul
REM Fabrique l'installateur Windows sur ce PC (Python 3.11+ et Inno Setup 6 requis).
cd /d "%~dp0\..\.."
python -m venv venv-build || goto erreur
venv-build\Scripts\python -m pip install --upgrade pip
venv-build\Scripts\pip install -r requirements.txt pyinstaller || goto erreur
venv-build\Scripts\pyinstaller packaging\windows\gescol.spec --noconfirm --distpath dist --workpath build || goto erreur
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (echo Inno Setup 6 introuvable : installez-le depuis jrsoftware.org & goto erreur)
%ISCC% packaging\windows\gescol.iss || goto erreur
echo.
echo Termine : l'installateur est dans le dossier dist
pause
exit /b 0
:erreur
echo La fabrication a echoue.
pause
exit /b 1
