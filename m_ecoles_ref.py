# -*- coding: utf-8 -*-
"""v2.5.0 : chargement des écoles du Bénin dans l'application CS / DDEMP (jur_ecoles) — « comme si toutes les circonscriptions
étaient dans la base ». Menu Juridiction → Écoles → « Charger les écoles de la liste officielle »."""
import config
import referentiel_ecoles as RE
from flask import abort, flash, redirect, render_template, request, url_for


def enregistrer(app, H):
    import m_juridiction as J
    q, ex = H.q, H.ex

    @app.route("/juridiction/ecoles/liste-officielle", methods=["GET", "POST"])
    @H.connexion_requise("jur_ecoles")
    def jur_ecoles_liste_officielle():
        if not config.juridiction() or config.secondaire():
            abort(404)
        s = J.structure()
        if not s:
            flash("Configurez d'abord la structure (Paramètres de la juridiction).", "warning")
            return redirect(url_for("jur_ecoles"))
        cs_liste = [J.cs_courante()] if s["niveau"] == "cs" else J.cs_liste()
        cs_liste = [c for c in cs_liste if c]
        if request.method == "POST":
            voulus = {int(x) for x in request.form.getlist("cs") if x.isdigit()}
            confirmer = request.form.get("a_confirmer") == "1"
            nb_c = nb_m = 0
            for c in cs_liste:
                if c["id"] not in voulus:
                    continue
                for e in RE.ecoles_de_cs(c["nom"], c["departement"], a_confirmer=confirmer):
                    ident = {"code": RE.code(e), "nom": e["nom"], "type": e["type"], "secteur": "public",
                             "commune": e["commune"], "arrondissement": e["arrondissement"], "annee_creation": e["annee"],
                             "directeur_titre": "Directeur"}
                    deja = q("SELECT id FROM jur_ecoles WHERE cs_id=? AND (code=? OR UPPER(nom)=UPPER(?))", (c["id"], ident["code"], e["nom"]), un=True)
                    if deja:
                        nb_m += 1
                        continue
                    J.enregistrer_ecole(ident, c["id"], None)
                    nb_c += 1
            H.journal("jur_ecoles_liste_officielle", f"{nb_c} créées")
            flash(f"{nb_c} école(s) ajoutée(s) à leur circonscription ; {nb_m} étaient déjà présentes.", "success" if nb_c else "info")
            return redirect(url_for("jur_ecoles"))
        lignes = [dict(c=c, **RE.compter(c["nom"], c["departement"]),
                       deja=q("SELECT COUNT(*) n FROM jur_ecoles WHERE cs_id=?", (c["id"],), un=True)["n"]) for c in cs_liste]
        return render_template("jur_ecoles_liste_officielle.html", lignes=lignes, unique=s["niveau"] == "cs")
