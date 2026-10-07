@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv (
  echo Premiere installation : creation de l'environnement Python...
  python -m venv venv || (echo Python introuvable. Installez Python 3.10+ depuis python.org en cochant "Add to PATH". & pause & exit /b 1)
  venv\Scripts\python -m pip install --upgrade pip
  venv\Scripts\pip install -r requirements.txt || (echo Echec de l'installation. Verifiez la connexion Internet. & pause & exit /b 1)
)
REM Mise a jour : installe les composants ajoutes par une nouvelle version (Excel, conversion PDF)
if not exist venv\composants-1.3.ok (
  echo Installation des composants de la version 1.3 ^(Excel, PDF^)...
  venv\Scripts\pip install -r requirements.txt && echo ok> venv\composants-1.3.ok
)
REM La fenetre "GESCOL Serveur" s'ouvre et lance le navigateur.
venv\Scripts\python gescol_serveur.py
pause
