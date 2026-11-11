# -*- coding: utf-8 -*-
"""v1.9 — Autorisation d'utiliser l'application : code d'accès personnel délivré par le concepteur.

* Chaque compte doit saisir, une fois, son code d'accès personnel (page /acces) ; sans code valide, l'application
  n'ouvre que cette page (et la déconnexion).
* Le code est lié au compte ET à l'installation : il ne sert à rien sur un autre compte ou un autre appareil / serveur.
* Pour l'obtenir : la page affiche la « demande » (application | installation | compte) et l'envoie en un toucher
  par WhatsApp au concepteur, qui produit le code avec son générateur (clé privée, jamais publiée) et le renvoie.
* L'administrateur (ou le directeur, le responsable de la CS / DDEMP) voit l'état de tous les comptes
  (/acces/comptes), envoie toutes les demandes d'un coup et colle tous les codes reçus en une fois.
* Délai de grâce : 15 jours à partir de la première ouverture de cette version (bandeau d'avertissement), puis blocage.
* Les espaces parents / élèves, les API de transmission et les fichiers statiques ne sont pas concernés.
"""
import os
import re
import urllib.parse
from datetime import date, timedelta

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for

import acces as A
import config
from db import ex, q

LIBRES = {"login", "logout", "static", "acces_page", "acces_comptes", "mon_compte", "service_worker", "manifeste",
          "hors_ligne", "sante", "installer", "diagnostic", "referentiel_js", "interdit", "introuvable", "image_ecole"}
ROLES_GESTION = ("admin", "fondateur", "directeur", "responsable")


def nom_appli():
    return (config.NOMS_APPLI.get(config.EDITION) or "SCOLARIS").split()[0].upper()


def enregistrer(app, H):
    H.ajouter_colonne("utilisateurs", "code_acces", "TEXT")

    def parametre(cle, defaut=None):
        r = q("SELECT valeur FROM parametres WHERE cle=?", (cle,), un=True)
        return r["valeur"] if r and r["valeur"] else defaut

    def ecrire(cle, valeur):
        ex("INSERT INTO parametres (cle, valeur) VALUES (?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", (cle, valeur))

    def installation():
        i = parametre("acces_installation")
        if not i:
            i = A.nouvel_identifiant_installation()
            ecrire("acces_installation", i)
        return i

    def debut():
        d = parametre("acces_debut")
        if not d:
            d = date.today().isoformat()
            ecrire("acces_debut", d)
        return date.fromisoformat(d)

    def jours_restants():
        return (debut() + timedelta(days=A.DELAI_GRACE_JOURS) - date.today()).days

    def autorise(u):
        code = u["code_acces"] if "code_acces" in u.keys() else None
        return bool(code) and A.code_valide(nom_appli(), installation(), u["identifiant"], code)

    def controle_actif():
        if current_app.config.get("ACCES_CONTROLE"):
            return True
        actif = A.ACTIF or os.environ.get("CODES_ACCES") == "1"
        return actif and not current_app.config.get("TESTING")

    def demande_de(u):
        return A.demande(nom_appli(), installation(), u["identifiant"])

    def lien_whatsapp(lignes, qui):
        texte = (f"Bonjour Maître Aimé FACHOLA. {qui} demande le(s) code(s) d'accès personnel(s) pour {nom_appli()} "
                 f"(installation {installation()}) :\n" + "\n".join(lignes))
        return f"https://wa.me/{A.TEL_CONCEPTEUR}?text={urllib.parse.quote(texte)}"

    with app.app_context():
        installation()
        debut()

    @app.before_request
    def controle_acces():
        if not g.get("user") or not controle_actif():
            return None
        ep = request.endpoint or ""
        if ep in LIBRES or ep.startswith("acces_"):
            return None
        u = g.user
        if autorise(u):
            return None
        reste = jours_restants()
        if reste > 0:
            g.acces_grace = reste
            return None
        return redirect(url_for("acces_page", suivant=request.path))

    @app.context_processor
    def ctx_acces():
        def bandeau():
            u = g.get("user")
            if not u or not controle_actif() or request.endpoint in ("acces_page", "acces_comptes") or autorise(u):
                return None
            return max(0, jours_restants())
        return {"acces_bandeau": bandeau, "acces_gestion": lambda: controle_actif() and bool(g.get("user")) and
                ((g.get("role_reel") or g.user["role"]) in ROLES_GESTION)}

    @app.route("/acces", methods=["GET", "POST"])
    @H.connexion_requise()
    def acces_page():
        u = g.user
        if request.method == "POST":
            code = request.form.get("code", "")
            if A.code_valide(nom_appli(), installation(), u["identifiant"], code):
                ex("UPDATE utilisateurs SET code_acces=? WHERE id=?", (A.normaliser_code(code), u["id"]))
                H.journal("acces_code", f"Code d'accès enregistré pour {u['identifiant']}")
                flash("Code d'accès valide : l'application est autorisée pour votre compte. Merci !", "success")
                suivant = request.args.get("suivant", "")
                return redirect(suivant if suivant.startswith("/") and not suivant.startswith("//") else url_for("accueil"))
            flash("Ce code ne correspond pas à votre compte sur cette installation. Vérifiez qu'il a été copié en entier.", "danger")
        ok = autorise(u)
        dem = demande_de(u)
        return render_template("acces.html", ok=ok, demande=dem, installation=installation(), appli=nom_appli(),
                               reste=jours_restants(), lien_wa=lien_whatsapp([dem], f"{u['nom'] if 'nom' in u.keys() and u['nom'] else u['identifiant']}"),
                               gestion=(g.get("role_reel") or u["role"]) in ROLES_GESTION)

    @app.route("/acces/comptes", methods=["GET", "POST"])
    @H.connexion_requise()
    def acces_comptes():
        if (g.get("role_reel") or g.user["role"]) not in ROLES_GESTION:
            abort(403)
        comptes = q("SELECT * FROM utilisateurs WHERE actif=1 ORDER BY role, identifiant")
        if request.method == "POST":
            texte = request.form.get("codes", "")
            par_id = {c["identifiant"].lower(): c for c in comptes}
            poses, refus = 0, []
            for ligne in texte.splitlines():
                m = re.match(r"^\s*(?:[A-Z]+\|[A-Z0-9-]+\|)?([^:|\s]+)\s*[:|=]\s*([A-Za-z2-7\- ]{100,})\s*$", ligne)
                if not m:
                    continue
                ident, code = m.group(1).lower(), m.group(2)
                c = par_id.get(ident)
                if c and A.code_valide(nom_appli(), installation(), c["identifiant"], code):
                    ex("UPDATE utilisateurs SET code_acces=? WHERE id=?", (A.normaliser_code(code), c["id"]))
                    poses += 1
                else:
                    refus.append(ident)
            if poses:
                H.journal("acces_codes", f"{poses} code(s) d'accès enregistrés")
            flash(f"{poses} code(s) enregistré(s)." + (f" Refusé(s) : {', '.join(refus[:20])}." if refus else ""),
                  "success" if poses and not refus else "warning")
            return redirect(url_for("acces_comptes"))
        lignes = [{"c": c, "ok": autorise(c), "demande": demande_de(c)} for c in comptes]
        manquants = [x["demande"] for x in lignes if not x["ok"]]
        return render_template("acces_comptes.html", lignes=lignes, manquants=manquants, installation=installation(),
                               appli=nom_appli(), reste=jours_restants(),
                               lien_wa=lien_whatsapp(manquants, config.ECOLE.get("nom") or nom_appli()) if manquants else None)
