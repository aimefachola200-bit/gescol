# -*- coding: utf-8 -*-
"""v2.7.1 : « Documents pédagogiques » — cahiers de l'apprenant, fichiers de résumés / d'exercices / d'évaluations,
cahier d'écriture et cahiers de révision de Terminale (PDF), rangés par niveau et par matière.

Les fichiers sont dans static/documents_pedagogiques/ : ils s'ouvrent et se téléchargent hors connexion dans les
applications installées. Page : /documents-pedagogiques (filtres : cycle, niveau, matière, famille, recherche)."""
import os

from flask import render_template, request

import config

DOSSIER = "documents_pedagogiques"
PRIM = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
SEC = ["4e", "3e", "Tle A", "Tle B"]

FAM_APPR = "Cahier de l'apprenant"
FAM_FICHIER = "Fichier de résumés, d'exercices et d'évaluations"
FAM_ECRIT = "Cahier d'écriture"
FAM_REV = "Cahier de révision (Terminale)"
FAM_REV_COLL = "Fichier de révision (4e et 3e, préparation au BEPC)"
FAM_REV_CEP = "Fiches de révision (CEP)"
FAMILLES = [FAM_APPR, FAM_FICHIER, FAM_ECRIT, FAM_REV_CEP, FAM_REV_COLL, FAM_REV]

# (fichier, titre, cycle, niveaux, matière, famille, pages, description)
DOCS = [
    ("ecriture_ci_cp.pdf", "Mon cahier d'écriture — CI et CP", "primaire", ["CI", "CP"], "Écriture", FAM_ECRIT, 60,
     "Toutes les lettres et tous les sons, en script et en cursive, minuscules et majuscules. Édition 2026."),
    ("apprenant_lecture_ci.pdf", "Mon cahier d'activités de lecture — CI (IPAM 1)", "primaire", ["CI"], "Français (lecture)", FAM_APPR, 76,
     "Lecture globale, voyelles, consonnes, sons composés ; six étapes."),
    ("apprenant_francais_cm1.pdf", "Mon cahier de réussite — Français CM1", "primaire", ["CM1"], "Français", FAM_APPR, 87,
     "Grammaire, conjugaison, orthographe, vocabulaire, expression écrite ; six étapes."),
    ("apprenant_maths_cm1.pdf", "Mon cahier de réussite — Mathématiques CM1", "primaire", ["CM1"], "Mathématiques", FAM_APPR, 88,
     "Nombres et calcul, mesures, géométrie, données ; quatre étapes."),
    ("apprenant_civisme_cm1.pdf", "Mon cahier de réussite — Éducation civique CM1", "primaire", ["CM1"], "ES (éducation sociale)", FAM_APPR, 45,
     "Vie démocratique, sécurité routière, règles de vie en société ; six étapes."),
    ("apprenant_es_est_ce1.pdf", "Mon cahier d'activités — ES et EST CE1", "primaire", ["CE1"], "ES / EST", FAM_APPR, 90,
     "Morale, civisme, géographie, histoire, sciences ; six étapes."),
    ("fichier_francais_ce1_cm2.pdf", "Fichier de Français — CE1 au CM2", "primaire", ["CE1", "CE2", "CM1", "CM2"], "Français", FAM_FICHIER, 27,
     "Lecture et vocabulaire, grammaire, conjugaison, orthographe, expression écrite. Édition actualisée 2026."),
    ("fichier_maths_ce1_cm2.pdf", "Fichier de Mathématiques — CE1 au CM2", "primaire", ["CE1", "CE2", "CM1", "CM2"], "Mathématiques", FAM_FICHIER, 33,
     "Numération et calcul, mesures, géométrie, organisation des données. Édition actualisée 2026."),
    ("fichier_es_est_cp_cm2.pdf", "Fichier ES et EST — CP au CM2", "primaire", ["CP", "CE1", "CE2", "CM1", "CM2"], "ES / EST", FAM_FICHIER, 47,
     "Morale, civisme, histoire, culture, géographie, éducation scientifique et technologique. Édition actualisée 2026."),
    ("fiches_revision_cep.pdf", "Fiches de révision et d'évaluations — préparation au CEP", "primaire", ["CM2"], "Préparation au CEP", FAM_REV_CEP, 117,
     "Fiches de révision et évaluations type pour préparer le Certificat d'Études Primaires (CEP)."),
    ("revision_eps_4e_3e.pdf", "Fichier de révision d'EPS — 4e et 3e", "secondaire", ["4e", "3e"], "EPS", FAM_REV_COLL, 110, ""),
    ("revision_francais_4e_3e.pdf", "Fichier de révision de Français — 4e et 3e", "secondaire", ["4e", "3e"], "Français", FAM_REV_COLL, 185, ""),
    ("revision_histgeo_4e_3e.pdf", "Fichier de révision d'Histoire-Géographie — 4e et 3e", "secondaire", ["4e", "3e"], "Histoire-Géographie", FAM_REV_COLL, 124, ""),
    ("revision_pct_4e_3e.pdf", "Fichier de révision de Physique-Chimie-Technologie — 4e et 3e", "secondaire", ["4e", "3e"], "PCT", FAM_REV_COLL, 105, ""),
    ("revision_anglais_4e_3e.pdf", "Fichier de révision d'Anglais — 4e et 3e", "secondaire", ["4e", "3e"], "Anglais", FAM_REV_COLL, 86, ""),
    ("revision_svt_4e_3e.pdf", "Fichier de révision de SVT — 4e et 3e", "secondaire", ["4e", "3e"], "SVT", FAM_REV_COLL, 95, ""),
    ("revision_francais_tle_ab.pdf", "Français — Terminales A et B", "secondaire", ["Tle A", "Tle B"], "Français", FAM_REV, 76, ""),
    ("revision_philosophie_tle_ab.pdf", "Philosophie — Terminales A et B", "secondaire", ["Tle A", "Tle B"], "Philosophie", FAM_REV, 71, ""),
    ("revision_histgeo_tle_ab.pdf", "Histoire-Géographie — Terminales A et B", "secondaire", ["Tle A", "Tle B"], "Histoire-Géographie", FAM_REV, 66, ""),
    ("revision_anglais_tle_ab.pdf", "Anglais — Terminales A et B", "secondaire", ["Tle A", "Tle B"], "Anglais", FAM_REV, 76, ""),
    ("revision_allemand_tle_ab.pdf", "Allemand — Terminales A et B", "secondaire", ["Tle A", "Tle B"], "Allemand", FAM_REV, 87, ""),
    ("revision_espagnol_tle_ab.pdf", "Espagnol — Terminales A et B", "secondaire", ["Tle A", "Tle B"], "Espagnol", FAM_REV, 63, ""),
    ("revision_maths_tle_ab.pdf", "Mathématiques — Terminales A et B", "secondaire", ["Tle A", "Tle B"], "Mathématiques", FAM_REV, 94, ""),
    ("revision_svt_tle_ab.pdf", "Sciences de la Vie et de la Terre — Terminales A et B", "secondaire", ["Tle A", "Tle B"], "SVT", FAM_REV, 72, ""),
    ("revision_economie_tle_b.pdf", "Économie — Terminale B", "secondaire", ["Tle B"], "Économie", FAM_REV, 66, ""),
]
_DESC_REV = ("Résumé du cours chapitre par chapitre, l'essentiel à retenir, méthode, exemple corrigé, exercices et devoir surveillé type, "
             "selon les situations d'apprentissage (SA) du programme.")


def liste():
    out = []
    for f, titre, cycle, niv, mat, fam, pages, desc in DOCS:
        out.append(dict(fichier=f, titre=titre, cycle=cycle, niveaux=niv, matiere=mat, famille=fam, pages=pages,
                        desc=desc or _DESC_REV, chemin=f"{DOSSIER}/{f}"))
    return out


def cycles_visibles():
    """Cycles montrés selon l'édition : primaire, secondaire ; l'application de l'enseignant montre les deux."""
    if config.secondaire():
        return ["secondaire"]
    if config.enseignant():
        return ["primaire", "secondaire"]
    return ["primaire"]


def enregistrer(app, H):
    @app.route("/documents-pedagogiques")
    @H.connexion_requise()
    def docs_peda():
        a = request.args
        cyc = cycles_visibles()
        docs = [d for d in liste() if d["cycle"] in cyc]
        niv, mat, fam, qs = a.get("niveau", ""), a.get("matiere", ""), a.get("famille", ""), (a.get("q") or "").strip().lower()
        niveaux = sorted({n for d in docs for n in d["niveaux"]}, key=lambda n: (PRIM + SEC).index(n) if n in PRIM + SEC else 99)
        matieres = sorted({d["matiere"] for d in docs})
        filtres = [d for d in docs if (not niv or niv in d["niveaux"]) and (not mat or d["matiere"] == mat)
                   and (not fam or d["famille"] == fam) and (not qs or qs in (d["titre"] + " " + d["matiere"]).lower())]
        ordre = {n: i for i, n in enumerate(PRIM + SEC)}
        filtres.sort(key=lambda d: (min(ordre.get(n, 99) for n in d["niveaux"]), FAMILLES.index(d["famille"]), d["matiere"]))
        # regroupement par niveau (le niveau le plus bas du document)
        groupes = []
        for d in filtres:
            cle = d["niveaux"][0] if len(d["niveaux"]) == 1 else d["niveaux"][0] + " → " + d["niveaux"][-1]
            if not groupes or groupes[-1][0] != cle:
                groupes.append((cle, []))
            groupes[-1][1].append(d)
        return render_template("docs_peda.html", groupes=groupes, total=len(filtres), niveaux=niveaux, matieres=matieres,
                               familles=[f for f in FAMILLES if any(d["famille"] == f for d in docs)],
                               niv=niv, mat=mat, fam=fam, q=qs, dossier=DOSSIER)

    app.jinja_env.globals["docs_peda_ouvert"] = lambda: True
