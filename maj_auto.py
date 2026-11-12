# -*- coding: utf-8 -*-
"""v2.4.9 : téléchargement automatique des mises à jour du code (voir amorcage.py).

Tous les jours (et à chaque lancement), l'application regarde sur GitHub si une version plus récente existe.
Si oui, elle la télécharge, la contrôle (empreinte SHA-256, chemins, syntaxe) et la prépare. Elle s'active au
prochain lancement ; un bandeau l'indique. Rien n'est téléchargé sans Internet : l'essai est simplement repris plus tard."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

import amorcage
import config

TAILLE_MAX = 80 * 1024 * 1024
INTERVALLE = 6 * 3600
_verrou = threading.Lock()


def _url(fichier):
    return f"https://github.com/{config.DEPOT_MAJ}/releases/latest/download/{fichier}"


def _http(url, tmax=20):
    if not url.startswith("https://github.com/"):
        raise ValueError("adresse refusée")
    req = urllib.request.Request(url, headers={"User-Agent": config.VERSION and "GESCOL-maj/" + config.VERSION})
    return urllib.request.urlopen(req, timeout=tmax)


def racine():
    return amorcage.dossier_maj(config.INSTANCE_DIR)


def etat():
    """{'pret': version téléchargée à activer au prochain lancement, 'active': version du code mis à jour en cours}."""
    r = racine()
    a = amorcage._lire(os.path.join(r, "actif.json"))
    pret = a.get("version") if a.get("version") and amorcage.plus_recente(a["version"], config.VERSION) else None
    return {"pret": pret, "active": amorcage.version_active(), "version": config.VERSION,
            "verifie": amorcage._lire(os.path.join(r, "etat.json")).get("verifie")}


def _noter(r, **k):
    os.makedirs(r, exist_ok=True)
    e = amorcage._lire(os.path.join(r, "etat.json"))
    e.update(k)
    amorcage._ecrire(os.path.join(r, "etat.json"), e)


def verifier():
    """Une vérification complète. Retourne un texte d'état (utile pour les tests et le bouton « Vérifier »)."""
    if not _verrou.acquire(blocking=False):
        return "déjà en cours"
    try:
        r = racine()
        info = json.loads(_http(_url("MAJ-CODE.json")).read(100000).decode("utf-8"))
        v = str(info["version"])
        _noter(r, verifie=time.time())
        if not amorcage.plus_recente(v, config.VERSION):
            return "à jour"
        if os.path.isfile(os.path.join(r, v, "code", "app.py")):
            a = amorcage._lire(os.path.join(r, "actif.json"))
            if a.get("version") != v:
                amorcage._ecrire(os.path.join(r, "actif.json"), {"version": v, "essais": 0})
            return "prête"
        if amorcage._lire(os.path.join(r, "echec.json")).get("version") == v:
            return "abandonnée (ne démarre pas)"
        os.makedirs(r, exist_ok=True)
        tmp = tempfile.mkdtemp(dir=r)
        try:
            zf = os.path.join(tmp, "maj.zip")
            h, n = hashlib.sha256(), 0
            with _http(_url("MAJ-CODE.zip"), 60) as rep, open(zf, "wb") as f:
                while True:
                    b = rep.read(65536)
                    if not b:
                        break
                    n += len(b)
                    if n > TAILLE_MAX:
                        raise ValueError("fichier trop gros")
                    h.update(b)
                    f.write(b)
            if h.hexdigest() != str(info.get("sha256", "")).lower():
                raise ValueError("empreinte différente : téléchargement rejeté")
            dest = os.path.join(tmp, "x")
            with zipfile.ZipFile(zf) as z:
                for m in z.namelist():
                    p = os.path.normpath(m)
                    if p.startswith(("..", "/", "\\")) or os.path.isabs(p) or ":" in p:
                        raise ValueError("chemin dangereux dans l'archive")
                z.extractall(dest)
            code = os.path.join(dest, "code")
            if not os.path.isfile(os.path.join(code, "app.py")) or not os.path.isdir(os.path.join(dest, "web", "templates")):
                raise ValueError("archive incomplète")
            for f in os.listdir(code):                                   # syntaxe valide pour CE Python
                if f.endswith(".py"):
                    with open(os.path.join(code, f), "rb") as fh:
                        compile(fh.read(), f, "exec")
            final = os.path.join(r, v)
            shutil.rmtree(final, ignore_errors=True)
            os.replace(dest, final)
            amorcage._ecrire(os.path.join(r, "actif.json"), {"version": v, "essais": 0})
            for d in os.listdir(r):                                      # ménage : anciennes versions
                if os.path.isdir(os.path.join(r, d)) and d not in (v,) and not d.startswith("tmp"):
                    shutil.rmtree(os.path.join(r, d), ignore_errors=True)
            return "prête"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    finally:
        _verrou.release()


def _boucle():
    time.sleep(20)                       # laisse l'application démarrer tranquillement
    while True:
        try:
            verifier()
        except Exception:  # noqa: BLE001  — pas d'Internet, dépôt injoignable… : on réessaiera
            pass
        time.sleep(INTERVALLE)


def enregistrer(app, H):
    from flask import jsonify, request

    # Vérification automatique : applications installées uniquement (jamais pendant les tests ni en développement),
    # sauf GESCOL_MAJ_AUTO=0 pour la désactiver.
    voulu = os.environ.get("GESCOL_MAJ_AUTO")
    if voulu != "0" and (voulu == "1" or getattr(sys, "frozen", False) or config.AUTONOME):
        if not getattr(sys.modules[__name__], "_lance", False):
            sys.modules[__name__]._lance = True
            threading.Thread(target=_boucle, name="maj-auto", daemon=True).start()

    @app.route("/maj/etat")
    def maj_etat():
        return jsonify(etat())

    @app.route("/maj/verifier", methods=["POST"])
    @H.connexion_requise()
    def maj_verifier():
        try:
            res = verifier()
        except Exception as e:  # noqa: BLE001
            res = "Impossible de vérifier (" + e.__class__.__name__ + ") : connexion Internet nécessaire."
        return jsonify(dict(etat(), resultat=res))
