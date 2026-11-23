# -*- coding: utf-8 -*-
"""v2.4.9 : téléchargement automatique des mises à jour du code (voir amorcage.py).

Tous les jours (et à chaque lancement), l'application regarde sur GitHub si une version plus récente existe.
Si oui, elle la télécharge, la contrôle (empreinte SHA-256, chemins, syntaxe) et la prépare. Elle s'active au
prochain lancement ; un bandeau l'indique. Rien n'est téléchargé sans Internet : l'essai est simplement repris plus tard."""
import hashlib
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile

import amorcage
import config

TAILLE_MAX = 80 * 1024 * 1024
INTERVALLE = 6 * 3600
_verrou = threading.Lock()


def _url(fichier):
    return f"https://github.com/{config.DEPOT_MAJ}/releases/latest/download/{fichier}"


def _http(url, tmax=20, plus=None):
    if not url.startswith("https://github.com/"):
        raise ValueError("adresse refusée")
    req = urllib.request.Request(url, headers={"User-Agent": config.VERSION and "GESCOL-maj/" + config.VERSION})
    for k, v in (plus or {}).items():
        req.add_header(k, v)
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


def menage(r, garder):
    """Supprime les anciennes versions téléchargées. v2.7.4 : JAMAIS la version en cours d'utilisation (ses pages et ses fichiers
    servent encore l'application ouverte : la supprimer provoquait « TemplateNotFound » jusqu'au redémarrage) ni celle qui
    est marquée active ; elle disparaît au nettoyage suivant, une fois l'application relancée sur la nouvelle version."""
    protegees = {str(garder), str(amorcage.version_active() or ""), str(config.VERSION),
                 str(amorcage._lire(os.path.join(r, "actif.json")).get("version") or "")}
    for d in os.listdir(r):
        if os.path.isdir(os.path.join(r, d)) and d not in protegees and not d.startswith("tmp"):
            shutil.rmtree(os.path.join(r, d), ignore_errors=True)


def _telecharger(zf, sha):
    """Télécharge MAJ-CODE.zip vers zf : jusqu'à 4 essais, reprise là où le téléchargement s'est arrêté,
    départ à zéro si l'empreinte SHA-256 ne correspond pas (fichier abîmé en route)."""
    derniere = ValueError("téléchargement impossible")
    for essai in range(4):
        if essai:
            time.sleep(3 * essai)
        try:
            n0 = os.path.getsize(zf) if os.path.isfile(zf) else 0
            rep = _http(_url("MAJ-CODE.zip"), 60, {"Range": "bytes=%d-" % n0}) if n0 else _http(_url("MAJ-CODE.zip"), 60)
            with rep:
                if n0 and getattr(rep, "status", 200) != 206:
                    n0 = 0                                              # le serveur n'a pas accepté la reprise
                n = n0
                with open(zf, "ab" if n0 else "wb") as f:
                    while True:
                        b = rep.read(65536)
                        if not b:
                            break
                        n += len(b)
                        if n > TAILLE_MAX:
                            raise ValueError("fichier trop gros")
                        f.write(b)
            h = hashlib.sha256()
            with open(zf, "rb") as f:
                for b in iter(lambda: f.read(65536), b""):
                    h.update(b)
            if h.hexdigest() == sha:
                return
            os.remove(zf)                                               # abîmé : on recommence de zéro
            derniere = ValueError("empreinte différente : téléchargement rejeté (après " + str(essai + 1) + " essai(s))")
        except urllib.error.HTTPError as e:
            if e.code == 416 and os.path.isfile(zf):
                os.remove(zf)
            derniere = e
        except (OSError, http.client.HTTPException) as e:              # coupure réseau : on garde le début et on reprend
            derniere = e
    raise derniere


def verifier(attendre=0):
    """Une vérification complète. Retourne un texte d'état (utile pour les tests et le bouton « Vérifier »)."""
    if not _verrou.acquire(blocking=attendre > 0, timeout=attendre if attendre > 0 else -1):
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
            _telecharger(zf, str(info.get("sha256", "")).lower())
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
            menage(r, v)
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

    @app.route("/maj/appliquer", methods=["POST"])
    @H.connexion_requise()
    def maj_appliquer():
        """v2.7.2 : sur Android on ne ferme pas une application comme sur PC. Ce bouton ferme le processus (la mise à jour prête
        s'active à la réouverture). Uniquement pour une application installée et une mise à jour déjà téléchargée."""
        e = etat()
        if not e["pret"] or not (getattr(sys, "frozen", False) or config.AUTONOME):
            return jsonify(ok=False, message="Aucune mise à jour prête à appliquer."), 400
        threading.Timer(1.5, lambda: os._exit(0)).start()
        return jsonify(ok=True, message="L'application se ferme : rouvrez-la.")

    @app.route("/maj/verifier", methods=["POST"])
    @H.connexion_requise()
    def maj_verifier():
        try:
            res = verifier(attendre=90)      # v2.7.5 : attend la vérification de fond au lieu de renoncer
        except Exception as e:  # noqa: BLE001
            res = "Impossible de vérifier (" + e.__class__.__name__ + " : " + str(e)[:100] + ") : connexion Internet nécessaire."
        return jsonify(dict(etat(), resultat=res))
