# -*- coding: utf-8 -*-
"""v2.4.9 : mise à jour automatique du code, SANS réinstaller l'application (Windows et Android autonome).

L'application télécharge elle-même, en arrière-plan, la dernière version publiée sur GitHub (fichier
MAJ-CODE.zip) et la range dans  <dossier des données>/maj_code/<version>/.  Au lancement suivant, ce module
(le tout premier à s'exécuter) place ce code AVANT celui de l'installation : l'application démarre directement
dans la nouvelle version. Les données (base, photos, cachets) ne sont jamais touchées.

Sécurité de fonctionnement :
  * une mise à jour n'est utilisée que si elle est PLUS RÉCENTE que l'installation (réinstaller un .exe/.apk plus
    récent reprend la main) ;
  * si la nouvelle version ne démarre pas 4 fois de suite, elle est abandonnée et l'installation d'origine reprend ;
  * module en bibliothèque standard uniquement : il ne dépend d'aucun autre module de l'application.
"""
import importlib.abc
import importlib.util
import json
import os
import sys
import threading
import time

MARQUE = "GESCOL"
BASE_VERSION = "2.5.1"          # version contenue dans cette installation (tests : égale à config.VERSION)
ESSAIS_MAX = 4
_etat = {"actif": None}


def num(v):
    out = []
    for x in str(v or "").lstrip("vV").split("."):
        try:
            out.append(int(x))
        except ValueError:
            out.append(0)
    return out


def plus_recente(a, b):
    x, y = num(a), num(b)
    n = max(len(x), len(y))
    return x + [0] * (n - len(x)) > y + [0] * (n - len(y))


def dossier_donnees():
    d = os.environ.get(MARQUE + "_DATA")
    if d:
        return d
    if getattr(sys, "frozen", False):
        racine = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(racine, MARQUE if MARQUE == "GESCOL" else MARQUE.title())
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance")


def dossier_maj(donnees=None):
    return os.path.join(donnees or _donnees_reelles(), "maj_code")


def _donnees_reelles():
    """Même dossier que config.INSTANCE_DIR (lu dans la configuration de l'installation, une seule fois)."""
    try:
        import config
        d = config.INSTANCE_DIR
        sys.modules.pop("config", None)           # sera relu depuis le code mis à jour
        return d
    except Exception:  # noqa: BLE001
        return dossier_donnees()


def _lire(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _ecrire(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, p)


class _Chercheur(importlib.abc.MetaPathFinder):
    """Sert en priorité les modules présents dans le dossier de mise à jour ; les autres restent ceux de l'installation."""

    def __init__(self, dossier):
        self.dossier = dossier
        self.noms = {os.path.splitext(f)[0] for f in os.listdir(dossier) if f.endswith(".py")}

    def find_spec(self, nom, chemin=None, cible=None):
        if chemin is None and nom in self.noms:
            return importlib.util.spec_from_file_location(nom, os.path.join(self.dossier, nom + ".py"))
        return None


def appliquer():
    """À appeler tout au début du lancement. Retourne la version utilisée si une mise à jour est active."""
    if _etat["actif"]:
        return _etat["actif"]
    if os.environ.get(MARQUE + "_SANS_MAJ_CODE") == "1":
        return None
    try:
        racine = dossier_maj()
        actif_f = os.path.join(racine, "actif.json")
        actif = _lire(actif_f)
        v = actif.get("version")
        if not v or not plus_recente(v, BASE_VERSION):
            return None
        code = os.path.join(racine, v, "code")
        web = os.path.join(racine, v, "web")
        if not os.path.isfile(os.path.join(code, "app.py")):
            return None
        if actif.get("essais", 0) >= ESSAIS_MAX:                     # ne démarre pas : on revient à l'installation
            actif["abandonnee"] = True
            _ecrire(os.path.join(racine, "echec.json"), {"version": v, "quand": time.time()})
            os.remove(actif_f)
            return None
        actif["essais"] = actif.get("essais", 0) + 1
        _ecrire(actif_f, actif)

        def valider():                                                # démarrage réussi : compteur remis à zéro
            time.sleep(25)
            actif["essais"] = 0
            try:
                _ecrire(actif_f, actif)
            except OSError:
                pass
        threading.Thread(target=valider, daemon=True).start()

        sys.meta_path.insert(0, _Chercheur(code))
        if os.path.isdir(os.path.join(web, "templates")):
            os.environ[MARQUE + "_WEB_DIR"] = web
        for m in list(sys.modules):                                   # modules déjà chargés depuis l'installation
            if m in _Chercheur(code).noms:
                sys.modules.pop(m, None)
        _etat["actif"] = v
        return v
    except Exception:  # noqa: BLE001  — en cas de doute, l'installation d'origine démarre
        return None


def version_active():
    return _etat["actif"]
