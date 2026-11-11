# -*- coding: utf-8 -*-
"""v1.33 — Sécurité des comptes.

* Mot de passe : au moins 8 caractères, au moins une lettre et un chiffre, différent de l'identifiant et absent de la
  liste des mots de passe trop connus (admin123, 12345678, motdepasse…) — règle appliquée partout où l'on choisit
  un mot de passe (Mon compte, mot de passe oublié, premier lancement).
* Changement obligatoire : un compte qui se connecte avec un mot de passe de départ ou trop faible doit en choisir
  un nouveau aussitôt (``doit_changer_mdp``).
* Blocage par compte : 5 échecs en 15 minutes sur un même identifiant -> connexion refusée 15 minutes (en plus du
  blocage par adresse de m_en_ligne). Les échecs sont gardés dans la base (ils survivent à un redémarrage).
* Fin de session : sans activité pendant ``config.SESSION_INACTIVITE_MIN`` minutes (120 par défaut, 480 sur
  l'application autonome du téléphone), la session se ferme ; durée maximale d'une session : 12 heures.
"""
import re
import time
import unicodedata
from datetime import datetime, timedelta

from flask import flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import config

FAIBLES = {
    "admin", "admin123", "admin1234", "administrateur", "password", "password1", "motdepasse", "azerty",
    "azerty123", "azertyuiop", "qwerty", "qwerty123", "123456", "1234567", "12345678", "123456789", "1234567890",
    "00000000", "11111111", "demo", "demo1234", "scolaris", "scolaris1", "gescol", "gescol1", "ecole123", "ecole1234",
    "bonjour1", "benin123", "benin2026", "abc12345", "abcd1234", "directeur", "directeur1", "enseignant", "enseignant1",
}
ECHECS_MAX, FENETRE_S = 5, 15 * 60
ENDPOINTS = {"login"}


def _norm(t):
    return unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower()


def erreur_mdp(mdp, identifiant=""):
    """Message d'erreur si le mot de passe ne respecte pas la règle, sinon None."""
    m = str(mdp or "")
    if len(m) < 8:
        return "Le mot de passe doit faire au moins 8 caractères."
    if not re.search(r"[A-Za-zÀ-ÿ]", m) or not re.search(r"\d", m):
        return "Le mot de passe doit contenir au moins une lettre et un chiffre."
    n = _norm(m)
    if n in FAIBLES or len(set(n)) <= 2:
        return "Ce mot de passe est trop connu ou trop simple : choisissez-en un autre."
    ident = _norm(identifiant).strip()
    if ident and len(ident) >= 3 and ident in n:
        return "Le mot de passe ne doit pas contenir l'identifiant."
    return None


def est_faible(mdp, identifiant=""):
    return erreur_mdp(mdp, identifiant) is not None


def inactivite_min():
    v = getattr(config, "SESSION_INACTIVITE_MIN", None)
    if v is None:
        v = 480 if config.AUTONOME else 120
    return int(v)


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema("""CREATE TABLE IF NOT EXISTS connexion_echecs (id INTEGER PRIMARY KEY, identifiant TEXT NOT NULL, ip TEXT, ts REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_connexion_echecs ON connexion_echecs(identifiant, ts);""")
    app.permanent_session_lifetime = timedelta(hours=12)
    H.erreur_mdp = erreur_mdp
    H.est_faible = est_faible

    def actif_en_test():
        return not app.config.get("TESTING") or app.config.get("SECURITE_TEST")

    def echecs_recents(ident):
        return q("SELECT COUNT(*) n FROM connexion_echecs WHERE identifiant=? AND ts>?", (ident, time.time() - FENETRE_S), un=True)["n"]

    @app.before_request
    def securite_avant():
        # 1) blocage par compte
        if request.method == "POST" and request.endpoint in ENDPOINTS:
            ident = (request.form.get("identifiant") or "").strip().lower()[:80]
            if ident and echecs_recents(ident) >= ECHECS_MAX:
                g.connexion_bloquee = True
                H.journal("connexion_bloquee", ident)
                return render_template("erreur.html", titre="Compte bloqué pour 15 minutes",
                                         message="Trop d'essais de mot de passe incorrects pour ce compte. Réessayez dans "
                                                 "15 minutes, ou utilisez « Mot de passe oublié ? »."), 429
            return None
        # 2) fin de session après inactivité
        if g.get("user") and not request.path.startswith("/static/"):
            maintenant = time.time()
            vu = session.get("vu")
            limite = inactivite_min() * 60
            debut = session.get("debut") or maintenant
            if limite > 0 and ((vu and maintenant - vu > limite) or maintenant - debut > 12 * 3600):
                session.pop("uid", None)
                session.pop("vu", None)
                session.pop("debut", None)
                g.user = None
                if request.method == "GET":
                    flash("Session fermée après une longue inactivité : reconnectez-vous.", "warning")
                    return redirect(url_for("login", suivant=request.full_path.rstrip("?")))
                return render_template("erreur.html", titre="Session expirée", message="Reconnectez-vous."), 401
            session["vu"] = maintenant
            session.setdefault("debut", maintenant)
            session.permanent = True
        return None

    @app.after_request
    def securite_apres(r):
        if request.method != "POST" or request.endpoint not in ENDPOINTS or g.get("connexion_bloquee"):
            return r
        ident = (request.form.get("identifiant") or "").strip().lower()[:80]
        if not ident:
            return r
        try:
            if r.status_code == 200:                          # formulaire réaffiché = échec
                ex("INSERT INTO connexion_echecs (identifiant, ip, ts) VALUES (?,?,?)", (ident, request.remote_addr or "?", time.time()))
                ex("DELETE FROM connexion_echecs WHERE ts<?", (time.time() - 86400,))
            elif r.status_code in (301, 302, 303) and session.get("uid"):
                ex("DELETE FROM connexion_echecs WHERE identifiant=?", (ident,))
                session["vu"] = session["debut"] = time.time()
                session.permanent = True
                # mot de passe de départ ou trop faible : changement obligatoire
                if actif_en_test():
                    u = q("SELECT * FROM utilisateurs WHERE id=?", (session["uid"],), un=True)
                    mdp = request.form.get("mdp", "")
                    if u and not u["doit_changer_mdp"] and check_password_hash(u["mdp_hash"], mdp) and est_faible(mdp, u["identifiant"]):
                        ex("UPDATE utilisateurs SET doit_changer_mdp=1 WHERE id=?", (u["id"],))
                        H.journal("mdp_faible_changement_impose", u["identifiant"])
        except Exception:  # noqa: BLE001 — la sécurité ne doit jamais casser la connexion
            app.logger.exception("Contrôle de sécurité de la connexion")
        return r
