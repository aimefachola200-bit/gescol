# -*- coding: utf-8 -*-
"""v2.5.2 — Onglet « Téléchargements » : budget prévisionnel, compte rendu d'exécution et autres documents administratifs,
chacun en PDF et en Word (.docx). Les fichiers sont produits par la barre d'export existante (/exporter.pdf, /exporter.docx),
donc avec les droits de la personne connectée."""
from flask import render_template, url_for

import config

# (groupe, titre, adresse de la page, explication) — n'apparaissent que les pages que l'édition possède
CATALOGUE = [
    ("Finances de l'établissement", "Budget prévisionnel", "/budget-previsionnel?vue=previsionnel",
     "État des recettes, état des dépenses et récapitulation de l'année."),
    ("Finances de l'établissement", "Compte rendu d'exécution du budget", "/budget-previsionnel?vue=compte-rendu",
     "Prévu, exécuté et écarts pour chaque ligne du budget."),
    ("Rapports et bilans", "Rapports de rentrée et de fin d'année", "/rapports", "Fiches et rapports officiels de l'établissement."),
    ("Rapports et bilans", "Bilan annuel", "/bilan-annuel", "Résultats et statistiques de l'année."),
    ("Rapports et bilans", "Tableau d'honneur", "/tableau-honneur", "Élèves distingués de la période."),
    ("Rapports et bilans", "Synthèse de l'établissement", "/synthese", "Vue d'ensemble : effectifs, résultats, personnel."),
    ("Documents administratifs", "Documents de l'enseignant", "/docs-enseignant", "Attestations, certificats de prise de service et de présence au poste."),
    ("Documents administratifs", "Calendrier scolaire officiel", "/calendrier-scolaire", "Dates de l'année scolaire et jours fériés."),
    ("Documents administratifs", "Textes officiels", "/textes-officiels", "Arrêtés et documents de référence."),
    ("Documents administratifs", "Courriers et secrétariat", "/secretariat/courrier", "Registre du courrier et modèles."),
]


def enregistrer(app, H):
    regles = {r.rule for r in app.url_map.iter_rules() if "GET" in r.methods}

    @app.route("/telechargements")
    @H.connexion_requise()
    def telechargements():
        groupes = {}
        for groupe, titre, adresse, aide in CATALOGUE:
            chemin = adresse.split("?")[0]
            if chemin not in regles or (chemin == "/budget-previsionnel" and (config.secondaire() or config.juridiction())):
                continue     # le budget prévisionnel (subventions reçues) est propre aux écoles maternelles et primaires
            groupes.setdefault(groupe, []).append({
                "titre": titre, "aide": aide, "page": adresse,
                "pdf": url_for("exporter_page", fmt="pdf", page=adresse),
                "word": url_for("exporter_page", fmt="docx", page=adresse),
                "excel": url_for("exporter_page", fmt="xlsx", page=adresse)})
        return render_template("telechargements.html", groupes=groupes, annee=config.ANNEE_ACTIVE)
