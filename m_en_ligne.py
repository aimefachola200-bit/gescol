# -*- coding: utf-8 -*-
"""Fonctionnement en ligne (hébergement Internet) : GESCOL accessible partout, sans le Wi-Fi de l'école.

* détection de l'hébergement (PythonAnywhere, Render, VPS derrière un proxy https) et réglages adaptés :
  adresses en https, cookies sécurisés, en-têtes de sécurité ;
* protection de la connexion contre les essais de mots de passe en série ;
* sauvegarde automatique quotidienne (14 dernières conservées, nombre réglable), copiée aussi dans un dossier de secours
  (clé USB, disque externe) quand il est indiqué et branché ; manifeste SHA-256 dans chaque archive (v1.33) ;
* rappel (bandeau) quand aucune sauvegarde n'a été copiée hors de l'appareil depuis 7 jours ; téléchargement en un clic ;
* vérification d'une sauvegarde (empreintes, contrôle de la base) avant restauration ;
* restauration d'une sauvegarde .zip (passer les données du PC de l'école vers le serveur en ligne ou l'inverse) ;
* page d'état /sante pour les hébergeurs.
"""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import date, datetime

from flask import abort, flash, g, redirect, render_template, request, send_file, session, url_for

import config

SOUS_DOSSIERS = ("photos", "ecole", "archives")
GARDER_AUTO = 14                    # sauvegardes automatiques conservées (paramètre « sauvegarde_garder »)
RAPPEL_JOURS = 7                    # rappel quand aucune copie hors de l'appareil depuis ce délai
ESSAIS_MAX, FENETRE = 10, 15 * 60   # 10 échecs de connexion en 15 min -> blocage 15 min
ENDPOINTS_CONNEXION = {"login", "parent_login", "eleve_login"}


def en_ligne():
    """Vrai si GESCOL tourne chez un hébergeur (derrière un proxy https)."""
    return bool(os.environ.get("GESCOL_EN_LIGNE") or os.environ.get("RENDER")
                or os.environ.get("PYTHONANYWHERE_DOMAIN") or os.environ.get("PYTHONANYWHERE_SITE"))


def hebergeur():
    if os.environ.get("RENDER"):
        return "Render"
    if os.environ.get("PYTHONANYWHERE_DOMAIN") or os.environ.get("PYTHONANYWHERE_SITE"):
        return "PythonAnywhere"
    if os.environ.get("GESCOL_EN_LIGNE"):
        return "Serveur en ligne (VPS)"
    return "PC de l'école (réseau local)"


def dossier_sauvegardes():
    d = os.path.join(config.INSTANCE_DIR, "sauvegardes")
    os.makedirs(d, exist_ok=True)
    return d


def creer_sauvegarde(chemin_db, destination, note=""):
    """Écrit une archive ZIP cohérente (base copiée par l'API de sauvegarde SQLite + photos, logo, archives)."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(chemin_db)
        dst = sqlite3.connect(tmp)
        src.backup(dst)
        dst.close()
        src.close()
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "gescol.db")
            for sous in SOUS_DOSSIERS:
                dossier = os.path.join(config.INSTANCE_DIR, sous)
                if os.path.isdir(dossier):
                    for nom in os.listdir(dossier):
                        p = os.path.join(dossier, nom)
                        if os.path.isfile(p):
                            z.write(p, f"{sous}/{nom}")
            z.writestr("LISEZ-MOI.txt",
                       f"Sauvegarde GESCOL {config.VERSION} du {datetime.now():%d/%m/%Y %H:%M}. {note}\r\n"
                       "Pour restaurer : Administration > Mise en ligne et sauvegardes > Restaurer une sauvegarde.\r\n")
            # v1.33 : manifeste (empreinte SHA-256 de chaque fichier) pour vérifier l'archive avant une restauration
            empreintes = {i.filename: hashlib.sha256(z.read(i.filename)).hexdigest() for i in z.infolist()}
            z.writestr("manifeste.json", json.dumps({"application": config.NOMS_APPLI.get(config.EDITION, "GESCOL"),
                                                     "version": config.VERSION, "edition": config.EDITION,
                                                     "date": datetime.now().isoformat(timespec="seconds"), "note": note,
                                                     "fichiers": empreintes}, ensure_ascii=False, indent=1))
    finally:
        os.remove(tmp)


def verifier_archive(source):
    """Contrôle d'une sauvegarde (.zip : chemin ou octets). Renvoie (ok, messages, infos du manifeste)."""
    msgs, infos = [], {}
    try:
        z = zipfile.ZipFile(io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source)
    except (zipfile.BadZipFile, OSError):
        return False, ["Fichier illisible : ce n'est pas une archive .zip valide."], infos
    noms = z.namelist()
    if "gescol.db" not in noms:
        return False, ["La base de données (gescol.db) est absente de l'archive."], infos
    if sum(i.file_size for i in z.infolist()) > 800 * 1024 * 1024:
        return False, ["Archive trop grosse (plus de 800 Mo une fois décompressée)."], infos
    ok = True
    if "manifeste.json" in noms:
        try:
            infos = json.loads(z.read("manifeste.json").decode("utf-8"))
        except ValueError:
            return False, ["Manifeste illisible : l'archive a été modifiée ou abîmée."], infos
        for nom, emp in (infos.get("fichiers") or {}).items():
            if nom not in noms:
                ok = False
                msgs.append(f"Fichier manquant : {nom}.")
            elif hashlib.sha256(z.read(nom)).hexdigest() != emp:
                ok = False
                msgs.append(f"Fichier altéré : {nom} (empreinte différente).")
        if ok:
            msgs.append(f"Empreintes vérifiées : {len(infos.get('fichiers') or {})} fichier(s) intacts.")
    else:
        msgs.append("Sauvegarde d'une version antérieure (sans manifeste) : seule la base est contrôlée.")
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with open(tmp, "wb") as out:
            out.write(z.read("gescol.db"))
        with open(tmp, "rb") as t:
            if t.read(16) != b"SQLite format 3\x00":
                return False, msgs + ["La base n'est pas une base SQLite."], infos
        c = sqlite3.connect(tmp)
        try:
            try:
                tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            except sqlite3.DatabaseError as e:   # schéma illisible : base abîmée ou modifiée
                return False, msgs + [f"Base endommagée ({e})."], infos
            if not {"utilisateurs", "eleves", "classes"} <= tables:
                return False, msgs + ["Ce n'est pas une base GESCOL."], infos
            res = c.execute("PRAGMA integrity_check").fetchone()[0]
            if res != "ok":
                return False, msgs + [f"Base endommagée ({res})."], infos
            infos["eleves"] = c.execute("SELECT COUNT(*) FROM eleves").fetchone()[0]
            infos["utilisateurs"] = c.execute("SELECT COUNT(*) FROM utilisateurs").fetchone()[0]
        finally:
            c.close()
        msgs.append(f"Base contrôlée : intacte ({infos['eleves']} élève(s), {infos['utilisateurs']} compte(s)).")
    finally:
        os.remove(tmp)
    return ok, msgs, infos


def _fichier_suivi():
    return os.path.join(config.INSTANCE_DIR, "sauvegarde_suivi.json")


def lire_suivi():
    try:
        with open(_fichier_suivi(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def noter_suivi(**k):
    d = lire_suivi()
    d.update(k)
    try:
        with open(_fichier_suivi(), "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def jours_depuis_copie_externe():
    """Jours écoulés depuis la dernière copie hors de l'appareil (téléchargement ou dossier de secours) ; None = jamais."""
    t = lire_suivi().get("externe")
    if not t:
        return None
    try:
        return (datetime.now() - datetime.fromisoformat(t)).days
    except ValueError:
        return None


def enregistrer(app, H):
    from db import chemin_db, initialiser

    # ------------------------------------------------------------ réglages quand GESCOL est en ligne
    if en_ligne():
        from werkzeug.middleware.proxy_fix import ProxyFix
        # l'hébergeur reçoit le https et transmet la requête : on lui fait confiance pour l'adresse et le protocole
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        if os.environ.get("GESCOL_HTTPS", "1") != "0":
            app.config.update(SESSION_COOKIE_SECURE=True, PREFERRED_URL_SCHEME="https")

    @app.after_request
    def entetes_securite(r):
        r.headers.setdefault("X-Content-Type-Options", "nosniff")
        r.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        r.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.is_secure:
            r.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return r

    # ------------------------------------------------------------ connexion : blocage des essais en série
    echecs = {}
    verrou = threading.Lock()

    def _recents(ip):
        limite = time.time() - FENETRE
        lst = [t for t in echecs.get(ip, []) if t > limite]
        echecs[ip] = lst
        return lst

    @app.before_request
    def limiter_connexions():
        if request.method == "POST" and request.endpoint in ENDPOINTS_CONNEXION:
            with verrou:
                if len(_recents(request.remote_addr or "?")) >= ESSAIS_MAX:
                    return render_template("erreur.html", titre="Trop de tentatives",
                                           message="Trop d'essais de connexion incorrects. Réessayez dans 15 minutes "
                                                   "ou demandez à l'administrateur de réinitialiser le mot de passe."), 429

    @app.after_request
    def compter_echecs(r):
        if request.method == "POST" and request.endpoint in ENDPOINTS_CONNEXION:
            ip = request.remote_addr or "?"
            with verrou:
                if r.status_code == 200:          # formulaire réaffiché = échec
                    _recents(ip).append(time.time())
                elif r.status_code in (301, 302, 303):  # connexion réussie
                    echecs.pop(ip, None)
        return r

    # ------------------------------------------------------------ sauvegarde automatique quotidienne
    etat = {"jour": None}
    verrou_sauv = threading.Lock()

    def sauvegarde_auto():
        jour = date.today().isoformat()
        if etat["jour"] == jour:
            return
        with verrou_sauv:
            if etat["jour"] == jour:
                return
            etat["jour"] = jour
            d = dossier_sauvegardes()
            cible = os.path.join(d, f"auto_{jour}.zip")
            if os.path.exists(cible) or not os.path.exists(chemin_db()):
                return
            try:
                creer_sauvegarde(chemin_db(), cible, "(sauvegarde automatique)")
                ok, _m, _i = verifier_archive(cible)
                noter_suivi(auto=datetime.now().isoformat(timespec="seconds"), auto_ok=ok, auto_nom=os.path.basename(cible))
                garder = garder_auto()
                autos = sorted(f for f in os.listdir(d) if f.startswith("auto_") and f.endswith(".zip"))
                for ancien in autos[:-garder]:
                    os.remove(os.path.join(d, ancien))
                copier_secours(cible)
            except Exception:  # noqa: BLE001 — une sauvegarde ratée ne doit jamais bloquer l'école
                app.logger.exception("Sauvegarde automatique impossible")

    def param(cle, defaut=""):
        try:
            r = H.q("SELECT valeur FROM parametres WHERE cle=?", (cle,), un=True)
            return r["valeur"] if r and r["valeur"] is not None else defaut
        except Exception:  # noqa: BLE001
            return defaut

    def garder_auto():
        try:
            return max(3, min(int(param("sauvegarde_garder", GARDER_AUTO)), 90))
        except ValueError:
            return GARDER_AUTO

    def dossier_secours():
        return (param("sauvegarde_dossier_secours") or "").strip()

    def copier_secours(chemin):
        """Copie l'archive dans le dossier de secours (clé USB, disque externe) s'il est indiqué et accessible."""
        dest = dossier_secours()
        if not dest or not os.path.isdir(dest):
            return False
        try:
            shutil.copy2(chemin, os.path.join(dest, os.path.basename(chemin)))
            noter_suivi(externe=datetime.now().isoformat(timespec="seconds"), externe_mode="dossier", externe_dest=dest)
            return True
        except OSError:
            app.logger.exception("Copie de secours impossible")
            return False

    @app.context_processor
    def ctx_rappel_sauvegarde():
        def rappel():
            if not g.get("user") or not H.peut("parametres") or app.config.get("TESTING") and not app.config.get("RAPPEL_TEST"):
                return None
            j = jours_depuis_copie_externe()
            if j is not None and j < RAPPEL_JOURS:
                return None
            return {"jours": j}
        return {"rappel_sauvegarde": rappel}

    @app.before_request
    def declencher_sauvegarde():
        if not app.config.get("TESTING") or app.config.get("SAUVEGARDE_AUTO_TEST"):
            sauvegarde_auto()

    # ------------------------------------------------------------ page d'état pour l'hébergeur
    @app.route("/sante")
    def sante():
        try:
            H.q("SELECT 1", un=True)
            return {"statut": "ok", "version": config.VERSION}
        except Exception:  # noqa: BLE001
            return {"statut": "erreur"}, 503

    # ------------------------------------------------------------ page d'administration
    def liste_sauvegardes():
        d = dossier_sauvegardes()
        out = []
        for f in sorted(os.listdir(d), reverse=True):
            if f.endswith(".zip"):
                st = os.stat(os.path.join(d, f))
                out.append({"nom": f, "taille": st.st_size,
                            "date": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")})
        return out

    @app.route("/administration/en-ligne", methods=["GET", "POST"])
    @H.connexion_requise("parametres")
    def en_ligne_page():
        if request.method == "POST":
            garder = request.form.get("garder", type=int) or GARDER_AUTO
            dest = (request.form.get("dossier_secours") or "").strip()[:300]
            if dest and not os.path.isdir(dest):
                flash(f"Dossier de secours introuvable pour le moment : « {dest} ». Il sera utilisé dès qu'il sera branché.", "warning")
            for cle, val in (("sauvegarde_garder", str(max(3, min(garder, 90)))), ("sauvegarde_dossier_secours", dest)):
                H.ex("INSERT INTO parametres (cle, valeur) VALUES (?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", (cle, val))
            H.journal("sauvegarde_reglages", f"garder={garder} dossier={dest}")
            flash("Réglages des sauvegardes enregistrés.", "success")
            return redirect(url_for("en_ligne_page"))
        suivi = lire_suivi()
        return render_template("en_ligne.html", en_ligne=en_ligne(), hebergeur=hebergeur(),
                               adresse=(config.URL_PUBLIQUE or request.host_url.rstrip("/")),
                               https=request.is_secure, sauvegardes=liste_sauvegardes(),
                               dossier=config.INSTANCE_DIR, suivi=suivi, garder=garder_auto(), dossier_secours=dossier_secours(),
                               jours_externe=jours_depuis_copie_externe(), verif=None)

    @app.route("/administration/sauvegardes/telecharger-maintenant", methods=["GET", "POST"])
    @H.connexion_requise("parametres")
    def sauvegarde_un_clic():
        """v1.33 : crée une sauvegarde à jour et la télécharge aussitôt (copie hors de l'appareil)."""
        nom = f"sauvegarde_{datetime.now():%Y-%m-%d_%H%M%S}.zip"
        chemin = os.path.join(dossier_sauvegardes(), nom)
        creer_sauvegarde(chemin_db(), chemin, "(téléchargée)")
        noter_suivi(externe=datetime.now().isoformat(timespec="seconds"), externe_mode="telechargement")
        copier_secours(chemin)
        H.journal("sauvegarde_telechargee", nom)
        return send_file(chemin, mimetype="application/zip", as_attachment=True, download_name=nom)

    @app.route("/administration/sauvegardes/verifier", methods=["POST"])
    @H.connexion_requise("parametres")
    def sauvegarde_verifier():
        f = request.files.get("fichier")
        nom = request.form.get("nom") or ""
        if f and f.filename:
            ok, msgs, infos = verifier_archive(f.read())
            titre = f.filename
        elif nom and "/" not in nom and "\\" not in nom and nom.endswith(".zip") and os.path.isfile(os.path.join(dossier_sauvegardes(), nom)):
            ok, msgs, infos = verifier_archive(os.path.join(dossier_sauvegardes(), nom))
            titre = nom
        else:
            flash("Choisissez une sauvegarde à vérifier.", "danger")
            return redirect(url_for("en_ligne_page"))
        H.journal("sauvegarde_verifiee", f"{titre} : {'ok' if ok else 'ECHEC'}")
        return render_template("en_ligne.html", en_ligne=en_ligne(), hebergeur=hebergeur(),
                               adresse=(config.URL_PUBLIQUE or request.host_url.rstrip("/")),
                               https=request.is_secure, sauvegardes=liste_sauvegardes(),
                               dossier=config.INSTANCE_DIR, suivi=lire_suivi(), garder=garder_auto(), dossier_secours=dossier_secours(),
                               jours_externe=jours_depuis_copie_externe(), verif={"ok": ok, "msgs": msgs, "titre": titre, "infos": infos})

    @app.route("/administration/sauvegardes/<nom>")
    @H.connexion_requise("parametres")
    def sauvegarde_telecharger(nom):
        if "/" in nom or "\\" in nom or not nom.endswith(".zip"):
            abort(404)
        p = os.path.join(dossier_sauvegardes(), nom)
        if not os.path.isfile(p):
            abort(404)
        noter_suivi(externe=datetime.now().isoformat(timespec="seconds"), externe_mode="telechargement")
        return send_file(p, mimetype="application/zip", as_attachment=True, download_name=nom)

    @app.route("/administration/sauvegardes/maintenant", methods=["POST"])
    @H.connexion_requise("parametres")
    def sauvegarde_maintenant():
        nom = f"manuelle_{datetime.now():%Y-%m-%d_%H%M%S}.zip"
        creer_sauvegarde(chemin_db(), os.path.join(dossier_sauvegardes(), nom), "(sauvegarde manuelle)")
        H.journal("sauvegarde", nom)
        flash(f"Sauvegarde créée : {nom}.", "success")
        return redirect(url_for("en_ligne_page"))

    # ------------------------------------------------------------ restauration
    @app.route("/administration/restaurer", methods=["POST"])
    @H.connexion_requise("parametres")
    def restaurer():
        f = request.files.get("fichier")
        if not f or not f.filename.lower().endswith(".zip"):
            flash("Choisissez le fichier .zip téléchargé par « Télécharger une sauvegarde ».", "danger")
            return redirect(url_for("en_ligne_page"))
        if request.form.get("confirmation", "").strip().upper() != "RESTAURER":
            flash("Tapez RESTAURER pour confirmer : toutes les données actuelles seront remplacées.", "danger")
            return redirect(url_for("en_ligne_page"))
        donnees = f.read()
        ok, msgs, _infos = verifier_archive(donnees)
        if not ok:
            flash("Restauration refusée : " + " ".join(msgs), "danger")
            return redirect(url_for("en_ligne_page"))
        try:
            z = zipfile.ZipFile(io.BytesIO(donnees))
        except zipfile.BadZipFile:
            flash("Ce fichier n'est pas une sauvegarde GESCOL valide (zip illisible).", "danger")
            return redirect(url_for("en_ligne_page"))
        noms = z.namelist()
        if "gescol.db" not in noms or sum(i.file_size for i in z.infolist()) > 800 * 1024 * 1024:
            flash("Sauvegarde invalide : le fichier gescol.db est absent (ou l'archive est trop grosse).", "danger")
            return redirect(url_for("en_ligne_page"))
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with open(tmp, "wb") as out:
                out.write(z.read("gescol.db"))
            with open(tmp, "rb") as t:
                if t.read(16) != b"SQLite format 3\x00":
                    raise ValueError("pas une base SQLite")
            src = sqlite3.connect(tmp)
            tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"utilisateurs", "eleves", "classes"} <= tables:
                src.close()
                raise ValueError("ce n'est pas une base GESCOL")
            if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                src.close()
                raise ValueError("base endommagée")
            # filet de sécurité : sauvegarde de l'état actuel avant de le remplacer
            creer_sauvegarde(chemin_db(), os.path.join(
                dossier_sauvegardes(), f"avant_restauration_{datetime.now():%Y-%m-%d_%H%M%S}.zip"),
                "(état avant restauration)")
            db = g.pop("db", None)
            if db is not None:
                db.close()
            dst = sqlite3.connect(chemin_db())
            src.backup(dst)          # remplace le contenu de la base en place (sûr même si elle est ouverte)
            dst.close()
            src.close()
        except (ValueError, sqlite3.DatabaseError) as e:
            flash(f"Restauration refusée : {e}.", "danger")
            return redirect(url_for("en_ligne_page"))
        finally:
            os.remove(tmp)
        # fichiers (photos, logo, cachet, archives) : noms simples uniquement, jamais de chemin
        for info in z.infolist():
            parties = info.filename.split("/")
            if len(parties) == 2 and parties[0] in SOUS_DOSSIERS and parties[1] and not info.is_dir():
                nom = os.path.basename(parties[1])
                if nom in ("", ".", "..") or nom.startswith("."):
                    continue
                dossier = os.path.join(config.INSTANCE_DIR, parties[0])
                os.makedirs(dossier, exist_ok=True)
                with open(os.path.join(dossier, nom), "wb") as out:
                    out.write(z.read(info.filename))
        initialiser()  # met la base restaurée au niveau de cette version (migration)
        session.clear()
        flash("Sauvegarde restaurée. Reconnectez-vous avec les comptes de la sauvegarde.", "success")
        return redirect(url_for("login"))

    H.en_ligne = en_ligne
    H.creer_sauvegarde = creer_sauvegarde
    H.verifier_archive = verifier_archive
