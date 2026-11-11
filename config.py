# -*- coding: utf-8 -*-
"""Paramètres par défaut. Une fois l'application installée, ils se règlent dans
l'application elle-même (menu Administration > Paramètres) : les valeurs saisies
là-bas remplacent celles-ci."""
import os

import sys

VERSION = "2.4.7"
# v1.8 : vérification des nouvelles versions (page « Releases » du dépôt GitHub) et fichiers à proposer par édition
DEPOT_MAJ = os.environ.get("SCOLARIS_DEPOT_MAJ", "aimefachola200-bit/scolaris")
FICHIERS_MAJ = {"privee": ("SCOLARIS-Installation.exe", "SCOLARIS-Autonome.apk"),
                "publique": ("SCOLARIS-Public-Installation.exe", "SCOLARIS-Public.apk"),
                "cs": ("SCOLARIS-Circonscription-Installation.exe", "SCOLARIS-Circonscription.apk"),
                "ddemp": ("SCOLARIS-DDEMP-Installation.exe", "SCOLARIS-DDEMP.apk"),
                "enseignant": ("SCOLARIS-Enseignant-Installation.exe", "SCOLARIS-Enseignant.apk")}
APK_CLIENT = "SCOLARIS.apk"
CONCEPTEUR = "Maître Aimé FACHOLA"   # mention « Conception » en bas de chaque écran et document
CONCEPTEUR_TEL = "+229 01 96 51 03 33"   # v1.32 : en bas des fiches de préparation, résumés, épreuves et cahiers

# Dossier du programme (templates, static). Dans l'exécutable Windows, PyInstaller
# décompresse les fichiers dans sys._MEIPASS.
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Gabarits et fichiers statiques : dans l'application Android autonome, ils sont recopiés sur le téléphone
# (les fichiers de l'APK ne sont pas des fichiers ordinaires) et leur dossier est indiqué par SCOLARIS_WEB_DIR.
WEB_DIR = os.environ.get("SCOLARIS_WEB_DIR") or BASE_DIR
# Édition : « privee » (écoles privées : scolarité, paie…) ou « publique » (écoles publiques : cantine,
# subventions, gestion de carrière, recensement…). Fixée par SCOLARIS_EDITION, par un fichier edition.txt
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


EDITION_IMPOSEE = (os.environ.get("SCOLARIS_EDITION") or _edition_fichier() or "").lower()
# v2.4.7 : applications jumelles du secondaire (collèges, lycées, ETP) : éditions « sec_privee » et « sec_publique ».
# Le secteur (privé / public) reste « privee » / « publique » pour tout le code existant ; SECONDAIRE ajoute le périmètre.
_SEC_ALIAS = {"sec_privee": "privee", "sec_publique": "publique", "sec_cs": "cs", "sec_ddestfp": "ddemp"}
SECONDAIRE = EDITION_IMPOSEE in _SEC_ALIAS
if SECONDAIRE:
    EDITION_IMPOSEE = _SEC_ALIAS[EDITION_IMPOSEE]
EDITIONS = {"privee": "École privée", "publique": "École publique",
            "cs": "Circonscription scolaire (CS)", "ddemp": "Direction départementale (DDEMP)",
            # v1.14 : application personnelle de l'enseignant (son profil, ses classes, ses documents)
            "enseignant": "Enseignant (application personnelle)"}
# éditions choisies dans Administration → Paramètres (l'application de l'enseignant est fixée par l'installation)
EDITIONS_PARAMETRES = {k: v for k, v in EDITIONS.items() if k != "enseignant"}
EDITION = EDITION_IMPOSEE if EDITION_IMPOSEE in EDITIONS else "privee"
# applications d'administration : la CS rassemble les écoles de sa juridiction, la DDEMP les CS du département
NOMS_APPLI = {"privee": "SCOLARIS", "publique": "SCOLARIS Public", "cs": "SCOLARIS Circonscription", "ddemp": "SCOLARIS DDEMP",
              "enseignant": "SCOLARIS Enseignant"}
DOSSIERS = {"privee": "SCOLARIS", "publique": "SCOLARIS_Public", "cs": "SCOLARIS_CS", "ddemp": "SCOLARIS_DDEMP",
            "enseignant": "SCOLARIS_Enseignant"}
PORTS = {"privee": 5100, "publique": 5101, "cs": 5102, "ddemp": 5103, "enseignant": 5104}
if SECONDAIRE:   # nom, dossier de données, port et fichiers de mise à jour propres : s'installe à côté de l'application de base
    _marque = NOMS_APPLI["privee"]
    _suffixe, _decal = {"privee": (" Secondaire", 5), "publique": (" Secondaire Public", 6),
                        "cs": (" Inspection Secondaire", 7), "ddemp": (" DDESTFP", 8)}[EDITION_IMPOSEE]
    NOMS_APPLI[EDITION] = _marque + _suffixe
    DOSSIERS[EDITION_IMPOSEE] = (_marque + _suffixe).replace(" ", "_")
    PORTS[EDITION_IMPOSEE] = PORTS["privee"] + _decal
    _fichier = (_marque + _suffixe).replace(" ", "-")
    FICHIERS_MAJ[EDITION] = (_fichier + "-Installation.exe", _fichier + ".apk")
NOM_PORTAIL_ENSEIGNANT = "SCOLARIS Enseignant"
# application de l'enseignant : secteur de SON école (« publique » ou « privee »), choisi au premier lancement
SECTEUR_ENSEIGNANT = "publique"


def publique():
    return EDITION == "publique" or (EDITION == "enseignant" and SECTEUR_ENSEIGNANT == "publique")


def enseignant():
    """Vrai pour l'application personnelle de l'enseignant (SCOLARIS Enseignant)."""
    return EDITION == "enseignant"


def secondaire():
    """Vrai pour les applications jumelles du secondaire (collèges, lycées, ETP)."""
    return SECONDAIRE


def juridiction():
    """Vrai pour les applications de la Circonscription scolaire et de la DDEMP."""
    return EDITION in ("cs", "ddemp")


# Mode autonome : SCOLARIS tourne sur l'appareil lui-même (application Android autonome)
AUTONOME = bool(os.environ.get("SCOLARIS_AUTONOME"))


def _dossier_donnees():
    """Où vivent la base, les photos et le logo. Jamais dans le dossier du programme
    installé (Program Files n'est pas modifiable)."""
    if os.environ.get("SCOLARIS_DATA"):
        return os.environ["SCOLARIS_DATA"]
    if getattr(sys, "frozen", False):
        racine = os.environ.get("APPDATA") or os.path.expanduser("~")
        # chaque application jumelle (SCOLARIS Public, Circonscription, DDEMP) garde ses données à part
        # SCOLARIS est indépendant de GESCOL : il ne lit jamais les dossiers de données de GESCOL.
        return os.path.join(racine, DOSSIERS.get(EDITION_IMPOSEE, "SCOLARIS"))
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
URL_PUBLIQUE = os.environ.get("SCOLARIS_URL", "")

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
