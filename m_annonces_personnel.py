# -*- coding: utf-8 -*-
"""v2.4.4 — Annonces au personnel : la direction écrit aux enseignants (ou à tout le personnel) ; chacun les lit dans « Annonces ».

* /annonces                     annonces_accueil      liste (marque les annonces comme lues) ; la direction y publie
* /annonces/nouvelle  POST      annonces_nouvelle     publication (direction, secrétariat : droit « communication »)
* /annonces/<id>/supprimer POST annonces_supprimer
Depuis Communication → Écrire, le destinataire « Enseignants (annonce interne) » publie ici.
Fonction de gabarit : ``annonces_non_lues()`` (pastille du menu).
"""
from flask import abort, flash, g, redirect, render_template, request, url_for

CIBLES = {"enseignants": "Enseignants", "tous": "Tout le personnel"}


def lisible_par(role, cible):
    """Un enseignant lit les annonces « enseignants » et « tout le personnel » ; les autres rôles lisent tout."""
    return True if role != "enseignant" else cible in ("enseignants", "tous")


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema("""
        CREATE TABLE IF NOT EXISTS annonces_personnel (
            id INTEGER PRIMARY KEY,
            ecole_id INTEGER,
            sujet TEXT NOT NULL,
            texte TEXT NOT NULL,
            cible TEXT NOT NULL DEFAULT 'enseignants',
            auteur_id INTEGER,
            cree_le TEXT
        );
        CREATE TABLE IF NOT EXISTS annonces_lues (
            annonce_id INTEGER NOT NULL REFERENCES annonces_personnel(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (annonce_id, user_id)
        );
    """)

    def visibles():
        role = g.user["role"]
        sql = "SELECT a.*, u.nom auteur FROM annonces_personnel a LEFT JOIN utilisateurs u ON u.id=a.auteur_id WHERE a.ecole_id=?"
        args = [H.eco()]
        if role == "enseignant":
            sql += " AND a.cible IN ('enseignants','tous')"
        return q(sql + " ORDER BY a.id DESC LIMIT 200", args)

    def publier(sujet, texte, cible):
        sujet, texte = (sujet or "").strip()[:150], (texte or "").strip()[:1000]
        if not sujet or not texte or cible not in CIBLES:
            return False
        ex("INSERT INTO annonces_personnel (ecole_id, sujet, texte, cible, auteur_id, cree_le) VALUES (?,?,?,?,?,?)",
           (H.eco(), sujet, texte, cible, g.user["id"], H.maintenant()))
        H.journal("annonce_personnel", f"{cible} : {sujet}")
        return True

    H.publier_annonce_personnel = publier

    def non_lues():
        try:
            if not g.get("user"):
                return 0
            ids = [a["id"] for a in visibles()]
            if not ids:
                return 0
            lues = {r["annonce_id"] for r in q("SELECT annonce_id FROM annonces_lues WHERE user_id=?", (g.user["id"],))}
            return len([i for i in ids if i not in lues])
        except Exception:  # noqa: BLE001 - une pastille ne doit jamais casser une page
            return 0

    app.jinja_env.globals["annonces_non_lues"] = non_lues

    def peut_publier():
        return g.user["role"] != "enseignant" and H.peut("communication")

    @app.route("/annonces")
    @H.connexion_requise()
    def annonces_accueil():
        lst = visibles()
        lues = {r["annonce_id"] for r in q("SELECT annonce_id FROM annonces_lues WHERE user_id=?", (g.user["id"],))}
        nouvelles = {a["id"] for a in lst if a["id"] not in lues}
        for i in nouvelles:
            ex("INSERT OR IGNORE INTO annonces_lues (annonce_id, user_id) VALUES (?,?)", (i, g.user["id"]))
        return render_template("annonces.html", annonces=lst, nouvelles=nouvelles, CIBLES=CIBLES, peut_publier=peut_publier())

    @app.route("/annonces/nouvelle", methods=["POST"])
    @H.connexion_requise("communication")
    def annonces_nouvelle():
        if not peut_publier():
            abort(403)
        if publier(request.form.get("sujet"), request.form.get("texte"), request.form.get("cible", "enseignants")):
            flash("Annonce publiée : les enseignants la verront dans « Annonces ».", "success")
        else:
            flash("Indiquez un sujet et un message.", "danger")
        return redirect(url_for("annonces_accueil"))

    @app.route("/annonces/<int:aid>/supprimer", methods=["POST"])
    @H.connexion_requise("communication")
    def annonces_supprimer(aid):
        if not peut_publier():
            abort(403)
        ex("DELETE FROM annonces_lues WHERE annonce_id=?", (aid,))
        ex("DELETE FROM annonces_personnel WHERE id=? AND ecole_id=?", (aid, H.eco()))
        H.journal("annonce_personnel_suppr", str(aid))
        flash("Annonce supprimée.", "success")
        return redirect(url_for("annonces_accueil"))
