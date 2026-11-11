# -*- coding: utf-8 -*-
"""v1.12 — Mot de passe oublié.

* Lien « Mot de passe oublié ? » sur la page de connexion → /mot-de-passe-oublie :
  1. la personne donne son identifiant ;
  2. si elle a enregistré une QUESTION DE SECOURS (Mon compte), elle y répond et choisit aussitôt un nouveau mot de passe
     (5 essais par quart d'heure et par identifiant, réponse stockée hachée, jamais en clair) ;
  3. sinon (ou en plus) elle envoie une DEMANDE à l'administrateur, visible dans Administration → Utilisateurs avec le
     bouton « Mot de passe provisoire » (le compte devra choisir un nouveau mot de passe à la connexion), et peut
     prévenir l'école par WhatsApp.
* Mon compte : définir / changer sa question de secours (mot de passe actuel exigé).
Tout est journalisé. Les espaces parents / élèves gardent leur procédure (nouveau code remis par l'école).
"""
import re
import secrets
import time
import unicodedata
import urllib.parse

from flask import abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import config
from db import ex, q

QUESTIONS = ["Nom de jeune fille de votre mère", "Ville ou village de naissance", "Nom de votre école primaire",
             "Prénom de votre premier enfant", "Nom de votre meilleur(e) ami(e) d'enfance", "Votre plat préféré"]
_essais = {}   # identifiant → [horodatages des réponses fausses]
_demandes_ip = {}


def normaliser(rep):
    s = unicodedata.normalize("NFD", str(rep or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def enregistrer(app, H):
    H.schema("""
    CREATE TABLE IF NOT EXISTS mdp_secours (user_id INTEGER PRIMARY KEY, question TEXT NOT NULL, reponse_hash TEXT NOT NULL, maj TEXT);
    CREATE TABLE IF NOT EXISTS mdp_demandes (id INTEGER PRIMARY KEY AUTOINCREMENT, identifiant TEXT, user_id INTEGER, nom TEXT,
        contact TEXT, message TEXT, cree_le TEXT, statut TEXT DEFAULT 'attente', traite_par TEXT, traite_le TEXT);
    """)

    def bloque(ident):
        t = time.time()
        l = [x for x in _essais.get(ident, []) if t - x < 900]
        _essais[ident] = l
        return len(l) >= 5

    def tel_ecole():
        t = re.sub(r"\D", "", str((config.ECOLE or {}).get("telephone") or ""))
        if t and len(t) <= 10:
            t = "229" + t
        return t

    def demandes_attente():
        if not g.get("user") or not H.peut("parametres"):
            return []
        return [dict(r) for r in q("SELECT * FROM mdp_demandes WHERE statut='attente' ORDER BY id DESC LIMIT 50")]

    @app.context_processor
    def _ctx():
        return {"mdp_demandes_attente": demandes_attente}

    @app.route("/mot-de-passe-oublie", methods=["GET", "POST"])
    def mdp_oublie():
        etape, u, question = "ident", None, None
        ident = (request.values.get("identifiant") or "").strip().lower()[:80]
        if ident:
            u = q("SELECT * FROM utilisateurs WHERE identifiant=? AND actif=1", (ident,), un=True)
            if u:
                sec = q("SELECT question FROM mdp_secours WHERE user_id=?", (u["id"],), un=True)
                question = sec["question"] if sec else None
            etape = "choix"
        action = request.form.get("action") if request.method == "POST" else None
        if action == "repondre" and u and question:
            if bloque(ident):
                flash("Trop d'essais : réessayez dans un quart d'heure, ou faites une demande à l'administrateur.", "danger")
            else:
                sec = q("SELECT * FROM mdp_secours WHERE user_id=?", (u["id"],), un=True)
                if check_password_hash(sec["reponse_hash"], normaliser(request.form.get("reponse"))):
                    session["mdp_reinit"] = {"uid": u["id"], "exp": time.time() + 600}
                    H.journal("mdp_secours_ok", ident)
                    etape = "nouveau"
                else:
                    _essais.setdefault(ident, []).append(time.time())
                    H.journal("mdp_secours_echec", ident)
                    flash("Réponse incorrecte.", "danger")
        elif action == "nouveau":
            jeton = session.get("mdp_reinit") or {}
            if not u or jeton.get("uid") != u["id"] or jeton.get("exp", 0) < time.time():
                flash("Délai dépassé : recommencez.", "danger")
            else:
                n1, n2 = request.form.get("nouveau", ""), request.form.get("confirmation", "")
                err = __import__("m_securite").erreur_mdp(n1, u["identifiant"])
                if err:
                    flash(err, "danger")
                    etape = "nouveau"
                elif n1 != n2:
                    flash("La confirmation ne correspond pas.", "danger")
                    etape = "nouveau"
                else:
                    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE id=?", (generate_password_hash(n1), u["id"]))
                    session.pop("mdp_reinit", None)
                    _essais.pop(ident, None)
                    H.journal("mdp_reinit_secours", ident)
                    flash("Mot de passe modifié : vous pouvez vous connecter.", "success")
                    return redirect(url_for("login"))
        elif action == "demande" and ident:
            ip = request.remote_addr or "?"
            t = time.time()
            recents = [x for x in _demandes_ip.get(ip, []) if t - x < 3600]
            deja = q("SELECT COUNT(*) n FROM mdp_demandes WHERE identifiant=? AND statut='attente'", (ident,), un=True)["n"]
            if len(recents) >= 5 or deja >= 3:
                flash("Demande déjà enregistrée : l'administrateur va la traiter.", "info")
            else:
                _demandes_ip[ip] = recents + [t]
                ex("INSERT INTO mdp_demandes (identifiant, user_id, nom, contact, message, cree_le) VALUES (?,?,?,?,?,?)",
                   (ident, u["id"] if u else None, (request.form.get("nom") or "")[:120], (request.form.get("contact") or "")[:60],
                    (request.form.get("message") or "")[:500], H.maintenant()))
                H.journal("mdp_demande", ident)
                flash("Demande transmise à l'administrateur : il vous remettra un mot de passe provisoire.", "success")
            etape = "envoyee"
        wa = ""
        tel = tel_ecole()
        if tel and ident:
            wa = "https://wa.me/" + tel + "?text=" + urllib.parse.quote(
                f"Bonjour, j'ai oublié mon mot de passe {(getattr(config, 'NOMS_APPLI', {}).get(config.EDITION) or 'SCOLARIS')}. "
                f"Identifiant : {ident}. Merci de me remettre un mot de passe provisoire.")
        return render_template("mdp_oublie.html", etape=etape, ident=ident, question=question if u else None, wa=wa)

    @app.route("/mon-compte/secours", methods=["POST"])
    @H.connexion_requise()
    def mdp_secours():
        if not check_password_hash(g.user["mdp_hash"], request.form.get("mdp", "")):
            flash("Mot de passe actuel incorrect.", "danger")
            return redirect(url_for("mon_compte"))
        question = (request.form.get("question") or "").strip()[:150]
        if question == "__autre":
            question = (request.form.get("question_autre") or "").strip()[:150]
        rep = normaliser(request.form.get("reponse"))
        if len(question) < 5 or len(rep) < 2:
            flash("Choisissez une question et donnez une réponse (2 caractères au moins).", "danger")
            return redirect(url_for("mon_compte"))
        ex("INSERT INTO mdp_secours (user_id, question, reponse_hash, maj) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
           "question=excluded.question, reponse_hash=excluded.reponse_hash, maj=excluded.maj",
           (g.user["id"], question, generate_password_hash(rep), H.maintenant()))
        H.journal("mdp_secours_defini")
        flash("Question de secours enregistrée : elle vous permettra de choisir un nouveau mot de passe en cas d'oubli.", "success")
        return redirect(url_for("mon_compte"))

    @app.route("/utilisateurs/demandes-mdp/<int:did>", methods=["POST"])
    @H.connexion_requise("parametres")
    def mdp_demande_traiter(did):
        d = q("SELECT * FROM mdp_demandes WHERE id=?", (did,), un=True)
        if not d:
            abort(404)
        action = request.form.get("action")
        if action == "reinit":
            u = q("SELECT * FROM utilisateurs WHERE identifiant=?", (d["identifiant"],), un=True)
            if not u:
                flash(f"Aucun compte « {d['identifiant']} » : demande classée.", "warning")
            else:
                nouveau = secrets.token_urlsafe(6)
                ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=1 WHERE id=?", (generate_password_hash(nouveau), u["id"]))
                H.journal("utilisateur_reinit", f"{u['identifiant']} (demande « mot de passe oublié »)")
                flash(f"Mot de passe provisoire de {u['identifiant']} : {nouveau} — à lui remettre ; il en choisira un nouveau à la connexion.", "info")
        ex("UPDATE mdp_demandes SET statut=?, traite_par=?, traite_le=? WHERE id=?",
           ("traitee" if action == "reinit" else "classee", g.user["identifiant"], H.maintenant(), did))
        return redirect(request.form.get("retour") or url_for("utilisateurs"))

    H.mdp_questions = QUESTIONS

    @app.context_processor
    def _ctx2():
        def ma_question():
            if not g.get("user"):
                return None
            r = q("SELECT question, maj FROM mdp_secours WHERE user_id=?", (g.user["id"],), un=True)
            return dict(r) if r else None
        return {"mdp_ma_question": ma_question, "MDP_QUESTIONS": QUESTIONS}
