# -*- coding: utf-8 -*-
"""v2.8 — Cahier de matériel : de la classe à la DDEMP, un même module relié aux quatre niveaux.

* Cahier de l'enseignant : matériel prévu pour chaque leçon ou fiche (classe, discipline, SA / séance), disponible ou non,
  à renouveler — l'enseignant l'écrit lui-même, y compris dans GESCOL Enseignant.
* Cahier de matériel de l'école : inventaire du matériel didactique, sportif, scientifique, informatique et du mobilier
  (quantité, état, source, valeur, localisation, responsable) avec totaux.
* Mouvements : entrées, sorties, prêts, retours, décharges aux enseignants, réformes — pour garder la trace de chaque objet.
* Besoins et dotations : ce que l'école demande, ce que la circonscription (CS) ou la DDEMP accorde et livre ; à la CS et à la
  DDEMP, une ligne par école de la juridiction (la CS suit ses écoles, la DDEMP ses circonscriptions et écoles).
Toutes les listes (Excel, PDF signé avec QR, import / export) viennent du moteur commun des registres (registres.py).
"""
from datetime import date

from flask import redirect, url_for

import registres as R

CATEGORIES = ["Matériel didactique (manuels, guides, cartes, affiches)", "Matériel de mathématiques (compas, équerres, boulier, solides)",
              "Matériel scientifique (ES, EST)", "Matériel sportif (EPS)", "Matériel d'éducation artistique", "Matériel informatique et numérique",
              "Mobilier (tables-bancs, chaises, armoires)", "Fournitures de bureau et de classe", "Matériel de cantine", "Autre"]
ETATS = ["Neuf", "Bon", "Usé", "À réparer", "Hors service"]
SOURCES = ["État (MEMP)", "Commune", "APE", "Partenaire / ONG", "Don", "Achat de l'école", "Autre"]
MOUVEMENTS = ["Entrée", "Sortie", "Prêt", "Retour de prêt", "Décharge à un enseignant", "Retour de décharge", "Réforme (mise au rebut)"]
DISPO = ["Disponible", "Partiellement disponible", "Indisponible", "À fabriquer (matériel local)"]
STATUTS = ["Besoin exprimé", "Demande transmise", "Accordé", "Livré en partie", "Livré", "Refusé"]
DISCIPLINES = ["Français", "Mathématiques", "ES", "EST", "EPS", "EA", "ECM", "Anglais", "Autre"]
COURS = ["Maternelle", "CI", "CP", "CE1", "CE2", "CM1", "CM2", "6e", "5e", "4e", "3e", "2nde", "1ère", "Tle"]


def enregistrer(app, H):
    H.DROITS["materiel_cahier"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent", "enseignant"}
    R.types_documents({"reg_materiel_inventaire": "Cahier de matériel de l'école", "reg_materiel_mouvements": "Registre des mouvements de matériel",
                       "reg_materiel_enseignant": "Cahier de matériel de l'enseignant", "reg_materiel_dotations": "Besoins et dotations en matériel"})
    LISTES = {"categories_mat": CATEGORIES, "etats_mat": ETATS, "sources_mat": SOURCES, "mouvements_mat": MOUVEMENTS, "dispo_mat": DISPO,
              "statuts_mat": STATUTS, "disciplines_mat": DISCIPLINES, "cours_mat": COURS}
    G = R.Groupe(app, H, "materiel", "Cahier de matériel", "materiel_cahier", ico="patrimoine",
                 ecriture_roles={"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp"},
                 sous_titre="Cahier de l'enseignant, matériel de l'école, mouvements, besoins et dotations (école, circonscription, DDEMP)",
                 listes=LISTES)

    def ent():
        return {"niveau": "ECOLE", "entite": R.entite_courante()[1]}

    def sig(titre="Le responsable du matériel"):
        return [R.signature_vide(titre), R.signature_autorite("Visa du Directeur / de la Directrice")]

    def ecrit_enseignant():
        from flask import g
        return bool(g.get("user"))

    G.registre("enseignant", "Cahier de l'enseignant", [
        ("date", "Date de la leçon", "date"), ("classe", "Classe / cours", "choix:cours_mat"), ("discipline", "Discipline", "choix:disciplines_mat"),
        ("sa", "SA n°", "texte"), ("seance", "Séance / séquence / projet", "texte"), ("lecon", "Leçon ou activité", "texte"),
        ("materiel", "Matériel prévu", "long"), ("dispo", "Disponibilité", "choix:dispo_mat"), ("renouveler", "À renouveler ou à demander", "long"),
        ("observations", "Observations", "long")],
        unite="leçon", oblig="lecon", ordre="date DESC", portee="ecole", feuille="Cahier de l'enseignant", entite=True, niveaux=["ECOLE"],
        filtres=("classe", "discipline", "dispo"), colonnes=("date", "classe", "discipline", "sa", "seance", "lecon", "materiel", "dispo", "renouveler"),
        ecriture=ecrit_enseignant, defauts=lambda: dict(ent(), date=date.today().isoformat()),
        signataires=lambda _l: sig("L'enseignant(e)"), doc="Cahier de matériel de l'enseignant",
        aide="Notez, pour chaque leçon ou fiche, le matériel à prévoir : ce qui manque se retrouve dans « À renouveler » et peut être repris dans Besoins et dotations.")
    G.registre("inventaire", "Cahier de matériel de l'école", [
        ("dateEntree", "Date d'entrée", "date"), ("designation", "Désignation", "texte"), ("categorie", "Catégorie", "choix:categories_mat"),
        ("quantite", "Quantité", "entier"), ("etat", "État", "choix:etats_mat"), ("source", "Source", "choix:sources_mat"), ("valeur", "Valeur (FCFA)", "montant"),
        ("localisation", "Localisation (salle, classe, magasin)", "texte"), ("responsable", "Responsable", "texte"), ("observations", "Observations", "long")],
        unite="article", oblig="designation", ordre="categorie, designation", portee="ecole", feuille="Cahier de matériel", entite=True, niveaux=["ECOLE"],
        unique=("designation", "localisation"), totaux=("quantite", "valeur"), filtres=("categorie", "etat", "source"),
        colonnes=("designation", "categorie", "quantite", "etat", "source", "valeur", "localisation", "responsable"),
        defauts=lambda: dict(ent(), dateEntree=date.today().isoformat(), etat="Bon"), signataires=lambda _l: sig(), doc="Cahier de matériel de l'école",
        aide="Une ligne par type d'article et par lieu. Les entrées et sorties se notent dans l'onglet Mouvements ; ici, la quantité est celle d'aujourd'hui.")
    G.registre("mouvements", "Mouvements de matériel", [
        ("date", "Date", "date"), ("designation", "Désignation", "texte"), ("mouvement", "Mouvement", "choix:mouvements_mat"), ("quantite", "Quantité", "entier"),
        ("beneficiaire", "Enseignant, classe ou structure", "texte"), ("etat", "État", "choix:etats_mat"), ("observations", "Observations", "long")],
        unite="mouvement", oblig="designation", ordre="date DESC, id DESC", portee="ecole", feuille="Mouvements", entite=True, niveaux=["ECOLE"],
        filtres=("mouvement",), totaux=("quantite",), defauts=lambda: dict(ent(), date=date.today().isoformat()),
        signataires=lambda _l: sig(), doc="Registre des mouvements de matériel")
    G.registre("dotations", "Besoins et dotations", [
        ("date", "Date", "date"), ("ecole", "École concernée", "ecole"), ("designation", "Matériel", "texte"), ("categorie", "Catégorie", "choix:categories_mat"),
        ("demande", "Quantité demandée", "entier"), ("recue", "Quantité accordée ou livrée", "entier"), ("statut", "Statut", "choix:statuts_mat"),
        ("origine", "Accordé par", "choix:sources_mat"), ("observations", "Observations", "long")],
        unite="besoin", oblig="designation", ordre="date DESC", portee="structure", feuille="Besoins et dotations", entite=True,
        niveaux=["ECOLE", "UP", "ZONE", "CS", "DDEMP"], totaux=("demande", "recue"), filtres=("statut", "categorie"),
        calcul=lambda x: {"Reste à livrer": max(0, (x.get("demande") or 0) - (x.get("recue") or 0))},
        defauts=lambda: dict(ent(), date=date.today().isoformat(), statut="Besoin exprimé"),
        signataires=lambda _l: sig("Le responsable"), doc="Besoins et dotations en matériel",
        aide="À l'école : ce que vous demandez et recevez. À la CS et à la DDEMP : une ligne par école ou par structure (rubrique « École concernée »).")

    @app.route("/cahier-materiel")
    @H.connexion_requise("materiel_cahier")
    def materiel_accueil():
        return redirect(url_for("reg_page", gcle="materiel", rcle="inventaire"))
