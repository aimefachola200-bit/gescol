# -*- coding: utf-8 -*-
"""v2.4.9 -> v2.9.2 : téléchargement automatique des mises à jour du code (voir amorcage.py).

Tous les jours (et à chaque lancement), l'application regarde sur GitHub si une version plus récente existe.
Si oui, elle la prépare puis la contrôle (empreinte SHA-256 de CHAQUE fichier, chemins, syntaxe). Elle s'active au
prochain lancement ; un bandeau l'indique. Rien n'est téléchargé sans Internet : l'essai est simplement repris plus tard.

v2.9.2 : mise à jour par fichiers. L'archive complète pèse plus de 30 Mo (PDF, images) : sur une connexion lente elle
n'aboutissait jamais. Maintenant l'application compare la liste des fichiers de la nouvelle version (MAJ-MANIFESTE.json) avec
ceux qu'elle possède déjà et ne télécharge que ceux qui ont changé (en général quelques centaines de Ko). Ce qui est déjà
téléchargé est gardé : après une coupure, on reprend là où l'on s'était arrêté, même après un redémarrage. L'archive
complète (reprise possible, elle aussi) ne sert plus que de secours. L'avancement est visible (« 40 % … »)."""
import concurrent.futures
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
import urllib.parse
import urllib.request
import zipfile

import amorcage
import config

TAILLE_MAX = 80 * 1024 * 1024
SEUIL_DIFF = 30 * 1024 * 1024        # au-delà, l'archive complète est plus raisonnable
INTERVALLE = 6 * 3600
REPRISE = 600                        # après un échec (réseau coupé…) : nouvel essai dans 10 minutes
_verrou = threading.Lock()
_pl = threading.Lock()
_prog = {"phase": "", "fait": 0, "total": 0}


class _PasDiff(Exception):
    """La mise à jour par fichiers n'est pas possible (liste absente, fichier absent du dépôt...) : archive complète."""


def _url(fichier):
    return f"https://github.com/{config.DEPOT_MAJ}/releases/latest/download/{fichier}"


def _url_brut(version, rel):
    return "https://raw.githubusercontent.com/%s/v%s/%s" % (config.DEPOT_MAJ, version, urllib.parse.quote(rel))


def _http(url, tmax=20, plus=None):
    if not url.startswith(("https://github.com/", "https://raw.githubusercontent.com/")):
        raise ValueError("adresse refusée")
    req = urllib.request.Request(url, headers={"User-Agent": amorcage.MARQUE + "-maj/" + str(config.VERSION)})
    for k, v in (plus or {}).items():
        req.add_header(k, v)
    return urllib.request.urlopen(req, timeout=tmax)


def _avance(phase=None, fait=None, total=None, plus=0):
    with _pl:
        if phase is not None:
            _prog["phase"] = phase
        if fait is not None:
            _prog["fait"] = fait
        if total is not None:
            _prog["total"] = total
        _prog["fait"] += plus


def _mo(n):
    return ("%.1f" % (n / 1048576.0)).replace(".", ",") + " Mo"


def progres_texte():
    p = dict(_prog)
    if not p["phase"]:
        return ""
    if p["total"]:
        return "%s : %d %% (%s sur %s)" % (p["phase"], min(100, 100 * p["fait"] // p["total"]), _mo(p["fait"]), _mo(p["total"]))
    return p["phase"]


def racine():
    return amorcage.dossier_maj(config.INSTANCE_DIR)


def etat():
    """{'pret': version téléchargée à activer au prochain lancement, 'active': version du code mis à jour en cours}."""
    r = racine()
    a = amorcage._lire(os.path.join(r, "actif.json"))
    pret = a.get("version") if a.get("version") and amorcage.plus_recente(a["version"], config.VERSION) else None
    return {"pret": pret, "active": amorcage.version_active(), "version": config.VERSION,
            "verifie": amorcage._lire(os.path.join(r, "etat.json")).get("verifie"),
            "encours": _verrou.locked(), "progres": progres_texte()}


def _noter(r, **k):
    os.makedirs(r, exist_ok=True)
    p = os.path.join(r, "etat.json")
    d = amorcage._lire(p)
    d.update(k)
    amorcage._ecrire(p, d)


def menage(r, garder):
    """Supprime les anciennes versions téléchargées. v2.7.4 : JAMAIS la version en cours d'utilisation (ses pages et ses fichiers
    servent encore l'application ouverte : la supprimer provoquait « TemplateNotFound » jusqu'au redémarrage) ni celle qui
    est marquée active ; elle disparaît au nettoyage suivant, une fois l'application relancée sur la nouvelle version."""
    protegees = {str(garder), str(amorcage.version_active() or ""), str(config.VERSION),
                 str(amorcage._lire(os.path.join(r, "actif.json")).get("version") or "")}
    for d in os.listdir(r):
        if os.path.isdir(os.path.join(r, d)) and d not in protegees and not d.startswith(("tmp", "dl-")):
            shutil.rmtree(os.path.join(r, d), ignore_errors=True)


def _nettoyer(r):
    """Efface les restes d'essais abandonnés (dossiers temporaires, archives partielles, fichiers déjà reçus) devenus trop vieux."""
    maintenant = time.time()
    for d in os.listdir(r):
        p = os.path.join(r, d)
        age = 1 if d.startswith("tmp") else 7 if d.startswith(("dl-", "partiel-")) else None
        try:
            if age and os.path.getmtime(p) < maintenant - age * 86400:
                shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
        except OSError:
            pass


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def _telecharger(zf, sha):
    """Archive complète (secours) vers zf : jusqu'à 4 essais ; le début déjà reçu est gardé et complété (même après un
    redémarrage) ; départ à zéro si l'empreinte ne correspond pas (fichier abîmé en route)."""
    derniere = ValueError("téléchargement impossible")
    pause = 0
    for essai in range(4):
        if pause:
            time.sleep(pause * essai)
        pause = 0
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
                        _avance(fait=n)
            if _sha(zf) == sha:
                return
            os.remove(zf)                                               # abîmé : on recommence de zéro
            derniere = ValueError("empreinte différente : téléchargement rejeté (après " + str(essai + 1) + " essai(s))")
        except urllib.error.HTTPError as e:
            if e.code == 416 and os.path.isfile(zf):
                os.remove(zf)
            derniere, pause = e, 2
        except (OSError, http.client.HTTPException) as e:              # coupure réseau : on garde le début et on reprend
            derniere, pause = e, 2
    raise derniere


def _prendre(version, rel, sha, dest):
    """Un fichier du dépôt (à l'étiquette de la version) : 3 essais, vérifié, rangé de façon atomique."""
    derniere = OSError("téléchargement impossible : " + rel)
    for essai in range(3):
        if essai:
            time.sleep(2 * essai)
        try:
            with _http(_url_brut(version, rel), 40) as rep:
                corps = rep.read(TAILLE_MAX)
            if hashlib.sha256(corps).hexdigest() != sha:
                derniere = _PasDiff("différent de l'archive : " + rel)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest + ".part", "wb") as f:
                f.write(corps)
            os.replace(dest + ".part", dest)
            _avance(plus=len(corps))
            return
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise _PasDiff("absent du dépôt : " + rel)
            derniere = e
        except (OSError, http.client.HTTPException) as e:
            derniere = e
    raise derniere


def _locales(r):
    """Dossiers où chercher des fichiers déjà présents : l'installation et la version mise à jour déjà reçue."""
    base = os.path.dirname(os.path.abspath(amorcage.__file__))
    ici = os.path.dirname(os.path.abspath(__file__))
    code, web = [ici, base], [getattr(config, "WEB_DIR", base), base]
    for v in {str(amorcage._lire(os.path.join(r, "actif.json")).get("version") or ""), str(amorcage.version_active() or "")}:
        if v:
            code.append(os.path.join(r, v, "code"))
            web.append(os.path.join(r, v, "web"))
    return {"code": code, "web": web}


def _differentiel(r, v, info, dest):
    """Prépare dest (code/ et web/) en ne téléchargeant que les fichiers que l'application n'a pas déjà."""
    m = str(info.get("manifeste", "")).lower()
    if not m:
        raise _PasDiff("pas de liste de fichiers")
    brut = _http(_url("MAJ-MANIFESTE.json"), 30).read(3000000)
    if hashlib.sha256(brut).hexdigest() != m:
        raise _PasDiff("liste de fichiers différente de celle annoncée")
    man = json.loads(brut.decode("utf-8"))
    if str(man.get("version")) != v:
        raise _PasDiff("liste d'une autre version")
    racines = _locales(r)
    cache = os.path.join(r, "dl-" + v)
    prises, manque = {}, []
    _avance("analyse des fichiers déjà présents", 0, 0)
    for e, (sha, taille) in sorted(man["fichiers"].items()):
        p = os.path.normpath(e)
        tete, _, sous = e.partition("/")
        if p.startswith(("..", "/", "\\")) or os.path.isabs(p) or ":" in p or tete not in racines or not sous:
            raise _PasDiff("chemin refusé : " + e)
        loc = None
        for d in racines[tete]:
            c = os.path.join(d, *sous.split("/"))
            try:
                if os.path.getsize(c) == taille and _sha(c) == sha:
                    loc = c
                    break
            except OSError:
                pass
        if loc is None:                                                 # déjà reçu lors d'un essai précédent ?
            c = os.path.join(cache, *e.split("/"))
            try:
                if os.path.getsize(c) == taille and _sha(c) == sha:
                    loc = c
            except OSError:
                pass
        if loc:
            prises[e] = loc
        else:
            manque.append((e, sha, taille))
    besoin = sum(t for _, _, t in manque)
    if besoin > SEUIL_DIFF:
        raise _PasDiff("trop de fichiers modifiés")
    if manque:
        _avance("téléchargement des fichiers modifiés (" + str(len(manque)) + ")", 0, besoin)
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            futs = [ex.submit(_prendre, v, e.partition("/")[2], sha, os.path.join(cache, *e.split("/"))) for e, sha, _ in manque]
            for f in futs:
                f.result()
        for e, _, _ in manque:
            prises[e] = os.path.join(cache, *e.split("/"))
    _avance("préparation", 0, 0)
    for e, src in prises.items():
        cible = os.path.join(dest, *e.split("/"))
        os.makedirs(os.path.dirname(cible), exist_ok=True)
        shutil.copyfile(src, cible)


def verifier(attendre=0):
    """Une vérification complète. Retourne un texte d'état (utile pour les tests et le bouton « Vérifier »)."""
    if not _verrou.acquire(blocking=attendre > 0, timeout=attendre if attendre > 0 else -1):
        t = progres_texte()
        return ("téléchargement en cours, " + t + " (il continue seul, patientez)") if t else "vérification en cours, patientez un instant"
    try:
        _avance("vérification", 0, 0)
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
        _nettoyer(r)
        tmp = tempfile.mkdtemp(dir=r)
        try:
            dest = os.path.join(tmp, "x")
            try:
                _differentiel(r, v, info, dest)
            except _PasDiff:                                            # secours : archive complète (avec reprise)
                shutil.rmtree(dest, ignore_errors=True)
                sha = str(info.get("sha256", "")).lower()
                zf = os.path.join(r, "partiel-" + sha[:16] + ".zip")
                _avance("téléchargement complet", 0, int(info.get("taille") or 0))
                _telecharger(zf, sha)
                with zipfile.ZipFile(zf) as z:
                    for m in z.namelist():
                        p = os.path.normpath(m)
                        if p.startswith(("..", "/", "\\")) or os.path.isabs(p) or ":" in p:
                            raise ValueError("chemin dangereux dans l'archive")
                    z.extractall(dest)
                os.remove(zf)
            _avance("contrôle", 0, 0)
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
            shutil.rmtree(os.path.join(r, "dl-" + v), ignore_errors=True)
            return "prête"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    finally:
        _avance("", 0, 0)
        _verrou.release()


def _boucle():
    time.sleep(20)                       # laisse l'application démarrer tranquillement
    while True:
        pause = INTERVALLE
        try:
            verifier()
        except Exception:  # noqa: BLE001  — pas d'Internet, dépôt injoignable… : nouvel essai bientôt (le reçu est conservé)
            pause = REPRISE
        time.sleep(pause)


def enregistrer(app, H):
    from flask import jsonify, request

    # Vérification automatique : applications installées uniquement (jamais pendant les tests ni en développement),
    # sauf <MARQUE>_MAJ_AUTO=0 pour la désactiver.
    voulu = os.environ.get(amorcage.MARQUE + "_MAJ_AUTO")
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
            res = verifier(attendre=15)      # v2.9.2 : si un téléchargement est en cours, on indique son avancement
        except Exception as e:  # noqa: BLE001
            res = "Impossible de vérifier (" + e.__class__.__name__ + " : " + str(e)[:100] + ") : connexion Internet nécessaire."
        return jsonify(dict(etat(), resultat=res))
