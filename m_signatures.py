# -*- coding: utf-8 -*-
"""v2.7 : signatures et cachets à tous les niveaux de l'établissement.

Page « Signatures et cachets » : chaque fonction (directeur / proviseur, censeur, surveillant général, intendant / économe, secrétaire,
comptable, chef des travaux, chef d'exploitation) dépose sa signature numérique et son nom ; la griffe (cachet rectangulaire du nom) se
compose automatiquement. L'enseignant gère sa propre signature et celle de la classe dont il est professeur principal. Le visa d'un
devoir (signature + griffe de la fonction choisie) est inséré dans l'écran, le PDF et le Word.
Rappel : jamais de cachet sur les fiches de préparation ; le nom du concepteur n'apparaît pas sur les épreuves."""
import config
from flask import flash, g, redirect, render_template, request, url_for

# (code, titre dans la griffe, libellé de la fonction)
FONCTIONS = [
    ("directeur", "Le Directeur", "Directeur / Proviseur / Principal"),
    ("censeur", "Le Censeur", "Censeur / Directeur des études"),
    ("surveillant", "Le Surveillant général", "Surveillant général"),
    ("econome", "L'Intendant", "Intendant / Économe"),
    ("secretaire", "Le Secrétaire", "Secrétaire"),
    ("comptable", "Le Comptable", "Comptable / Régisseur"),
    ("chef_travaux", "Le Chef des travaux", "Chef des travaux (enseignement technique)"),
    ("chef_exploitation", "Le Chef d'exploitation", "Chef d'exploitation agricole (lycée agricole)"),
]
TITRES = {c: t for c, t, _l in FONCTIONS}
ROLES_DIRECTION = ("admin", "fondateur", "directeur", "responsable", "chef_service")


def enregistrer(app, H):
    from db import ex, q

    def noms(eid):
        return {r["fonction"]: r["nom"] for r in q("SELECT fonction, nom FROM signataires WHERE ecole_id=?", (eid,))}

    def griffe_fonction(code, eid=None):
        """{'titre','nom','ligne3'} de la griffe d'une fonction, ou None si le nom n'est pas renseigné."""
        eid = eid or H.eco()
        if code == "directeur":
            lg = H.griffe_ecole(eid)
            return {"titre": lg[0][0], "nom": lg[0][1], "ligne3": lg[0][2]} if lg else None
        nom = (noms(eid).get(code) or "").strip()
        return {"titre": TITRES[code], "nom": nom, "ligne3": ""} if code in TITRES and nom else None

    H.griffe_fonction = griffe_fonction

    @app.route("/signatures-cachets", methods=["GET", "POST"])
    @H.connexion_requise()
    def signatures_cachets():
        eid = H.eco()
        direction = g.user["role"] in ROLES_DIRECTION
        if request.method == "POST":
            if not direction:
                from flask import abort
                abort(403)
            for code, _t, _l in FONCTIONS:
                if code == "directeur":
                    continue
                nom = (request.form.get(f"nom_{code}") or "").strip()[:80]
                if nom:
                    ex("INSERT INTO signataires (ecole_id, fonction, nom) VALUES (?,?,?) ON CONFLICT(ecole_id, fonction) DO UPDATE SET nom=excluded.nom", (eid, code, nom))
                else:
                    ex("DELETE FROM signataires WHERE ecole_id=? AND fonction=?", (eid, code))
            H.journal("signataires", str(eid))
            flash("Noms des signataires enregistrés.", "success")
            return redirect(url_for("signatures_cachets"))
        enc = noms(eid)
        lignes = []
        for code, titre, lib in FONCTIONS:
            gr = griffe_fonction(code, eid)
            lignes.append({"code": code, "titre": titre, "lib": lib, "nom": enc.get(code, ""), "griffe": gr,
                           "cle": f"ecole:{eid}:{code}"})
        classes = []
        if g.user["role"] == "enseignant" or direction:
            classes = [c for c in (H.classes_autorisees() or [])][:40] if g.user["role"] == "enseignant" else []
        return render_template("signatures_cachets.html", lignes=lignes, direction=direction, classes=classes,
                               cle_moi=f"enseignant:{g.user['id']}", moi=g.user["nom"], secondaire=config.secondaire())
