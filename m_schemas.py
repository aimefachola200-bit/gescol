# -*- coding: utf-8 -*-
"""v2.5.1 : bibliothèque de schémas et de cartes du Bénin (primaire et secondaire), à projeter ou à imprimer."""
import config
import schemas as S
from flask import abort, render_template, request


def _visibles():
    cycle = "Secondaire" if config.secondaire() else "Primaire"
    return [x for x in S.SCHEMAS if cycle.lower() in x[2].lower()]


def enregistrer(app, H):
    @app.route("/schemas")
    @H.connexion_requise("epreuves")
    def schemas_accueil():
        mat, qs = request.args.get("matiere", ""), (request.args.get("q") or "").strip().lower()
        liste = _visibles()
        mats = sorted({x[3] for x in liste})
        liste = [x for x in liste if (not mat or x[3] == mat) and (not qs or qs in (x[1] + x[3] + x[4]).lower())]
        return render_template("schemas.html", liste=liste, mats=mats, mat=mat, q=qs)

    @app.route("/schemas/<sid>")
    @H.connexion_requise("epreuves")
    def schemas_voir(sid):
        x = next((y for y in _visibles() if y[0] == sid), None)
        if not x:
            abort(404)
        return render_template("schemas_voir.html", x=x, svg=x[5]())
