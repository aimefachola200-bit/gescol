# -*- coding: utf-8 -*-
"""Paramètres par défaut. Une fois l'application installée, ils se règlent dans
l'application elle-même (menu Administration > Paramètres) : les valeurs saisies
là-bas remplacent celles-ci."""
import os
import sys

VERSION = "1.6.0"
CONCEPTEUR = "Maître Aimé FACHE"   # mention « Conception » en bas de chaque écran et document

# Dossier du programme (templates, static). Dans l'exécutable Windows, PyInstaller
# décompresse les fichiers dans sys._MEIPASS.
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Gabarits et fichiers statiques : dans l'application Android autonome, ils sont recopiés sur le téléphone
# (les fichiers de l'APK ne sont pas des fichiers ordinaires) et leur dossier est indiqué par GESCOL_WEB_DIR.
WEB_DIR = os.environ.get("GESCOL_WEB_DIR") or BASE_DIR
# Édition : « privee » (écoles privées : scolarité, paie…) ou « publique » (écoles publiques : cantine,
# subventions, gestion de carrière, recensement…). Fixée par GESCOL_EDITION, par un fichier edition.txt
# à côté du programme (installateurs), ou dans Administration → Paramètres.
def _edition_fichier():
    for d in (BASE_DIR, os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR):
        p = os.path.join(d, "edition.txt")
        if os.path.exists(p):
            try:
                return open(p, encoding="utf-8").read().strip().lower()
            except OSError:
                pass
    return ""


EDITION_IMPOSEE = (os.environ.get("GESCOL_EDITION") or _edition_fichier() or "").lower()
EDITIONS = {"privee": "École privée", "publique": "École publique",
            "cs": "Circonscription scolaire (CS)", "ddemp": "Direction départementale (DDEMP)"}
EDITION = EDITION_IMPOSEE if EDITION_IMPOSEE in EDITIONS else "privee"
# applications d'administration : la CS rassemble les écoles de sa juridiction, la DDEMP les CS du département
NOMS_APPLI = {"privee": "GESCOL", "publique": "GESCOL Public", "cs": "GESCOL Circonscription", "ddemp": "GESCOL DDEMP"}
DOSSIERS = {"privee": "GESCOL", "publique": "GESCOL_Public", "cs": "GESCOL_CS", "ddemp": "GESCOL_DDEMP"}
PORTS = {"privee": 5000, "publique": 5001, "cs": 5002, "ddemp": 5003}


def publique():
    return EDITION == "publique"


def juridiction():
    """Vrai pour les applications de la Circonscription scolaire et de la DDEMP."""
    return EDITION in ("cs", "ddemp")


# Mode autonome : GESCOL tourne sur l'appareil lui-même (application Android autonome)
AUTONOME = bool(os.environ.get("GESCOL_AUTONOME"))


def _dossier_donnees():
    """Où vivent la base, les photos et le logo. Jamais dans le dossier du programme
    installé (Program Files n'est pas modifiable)."""
    if os.environ.get("GESCOL_DATA"):
        return os.environ["GESCOL_DATA"]
    if getattr(sys, "frozen", False):
        racine = os.environ.get("APPDATA") or os.path.expanduser("~")
        # chaque application jumelle (GESCOL Public, Circonscription, DDEMP) garde ses données à part
        return os.path.join(racine, DOSSIERS.get(EDITION_IMPOSEE, "GESCOL"))
    return os.path.join(BASE_DIR, "instance")


INSTANCE_DIR = _dossier_donnees()
ECOLE_DIR = os.path.join(INSTANCE_DIR, "ecole")   # logo.png, cachet.png, signature.png

ECOLE = {
    "nom": "Établissement Scolaire CPFA",
    "sigle": "CPFA",
    "adresse": "Cotonou, Bénin",
    "telephone": "",
    "email": "",
    "directeur": "",
    "ville": "Cotonou",
}

DEVISE = "FCFA"
ANNEE_ACTIVE = "2026-2027"
PERIODES = ["Trimestre 1", "Trimestre 2", "Trimestre 3"]

# Adresse encodée dans les QR codes. Vide = adresse par laquelle on consulte
# l'application (détectée automatiquement).
URL_PUBLIQUE = os.environ.get("GESCOL_URL", "")

MODES_PAIEMENT = {
    "especes": "Espèces",
    "mtn_momo": "MTN Mobile Money",
    "moov_money": "Moov Money",
    "celtiis_cash": "Celtiis Cash",
    "virement": "Virement / chèque",
}
MODES_MOBILE = {"mtn_momo", "moov_money", "celtiis_cash"}

# Valeurs par défaut, gardées pour pouvoir y revenir
DEFAUTS = {
    "ecole_nom": ECOLE["nom"], "ecole_sigle": ECOLE["sigle"], "ecole_adresse": ECOLE["adresse"],
    "ecole_telephone": "", "ecole_email": "", "ecole_directeur": "", "ecole_ville": ECOLE["ville"],
    "annee_active": ANNEE_ACTIVE, "periodes": "trimestres", "url_publique": URL_PUBLIQUE,
}
