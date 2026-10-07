# -*- coding: utf-8 -*-
"""Démarrage de GESCOL à l'intérieur de l'application Android autonome.

Le serveur web tourne sur l'appareil (http://127.0.0.1:PORT) et l'écran de l'application l'affiche.
Données : dossier privé de l'application (base, photos, sauvegardes)."""
import os
import socket
import threading

PORT_FIXE = 8765          # port fixe : la session et les réglages de l'écran sont conservés d'un lancement à l'autre
_serveur = {"url": None}


def _port_libre(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _metadonnees_tolerantes():
    """Sur Android, les informations de version des bibliothèques recopiées peuvent manquer :
    Werkzeug et Flask ne les utilisent que pour afficher un numéro de version."""
    import importlib.metadata as md
    origine = md.version

    def version(nom):
        try:
            return origine(nom)
        except md.PackageNotFoundError:
            return "0"

    md.version = version


def demarrer(dossier_donnees, dossier_web):
    """Lance GESCOL une seule fois par processus ; retourne l'adresse locale."""
    if _serveur["url"]:
        return _serveur["url"]
    os.environ["GESCOL_DATA"] = dossier_donnees
    os.environ["GESCOL_WEB_DIR"] = dossier_web
    os.environ["GESCOL_AUTONOME"] = "1"
    os.makedirs(dossier_donnees, exist_ok=True)
    try:  # application jumelle « GESCOL Public » : édition écrite par preparer.py --edition publique
        import gescol_edition
        if gescol_edition.EDITION:
            os.environ["GESCOL_EDITION"] = gescol_edition.EDITION
    except ImportError:
        pass

    _metadonnees_tolerantes()
    from werkzeug.serving import make_server
    from app import app

    port = PORT_FIXE if _port_libre(PORT_FIXE) else 0
    serveur = make_server("127.0.0.1", port, app, threaded=True)
    port = serveur.server_port
    threading.Thread(target=serveur.serve_forever, name="gescol", daemon=True).start()
    _serveur["url"] = f"http://127.0.0.1:{port}"
    return _serveur["url"]
