"""v2.4.2 — « Par classe » : entrée unique du module Préparation de classe, de la maternelle au CM2.

Pour chaque cours, une page regroupe par matière : les fiches de préparation (rangées par unité / SA / séance),
les résumés, les évaluations et épreuves, les guides pédagogiques et les programmes / progressions. Une seule
recherche interroge toutes ces rubriques à la fois.

* /preparation/classes             prep_classes     les 7 cours (maternelle, CI … CM2) avec les effectifs de contenus
* /preparation/classes/<cours>     prep_classe      le dossier d'un cours ; filtres : matiere, q
"""
import banque_epreuves as B
import m_preparation as MP
from flask import abort, g, render_template, request

RUBRIQUES = [("fiches", "Fiches de préparation"), ("resumes", "Résumés"), ("evaluations", "Évaluations et épreuves"),
             ("guides", "Guides pédagogiques"), ("programmes", "Programmes et progressions")]


def _ordre_mat(m):
    return MP.ORDRE_MAT.index(m) if m in MP.ORDRE_MAT else 9


def _trouve(texte, *champs):
    """Tous les mots de la recherche figurent (sans accent ni casse) dans l'un des champs."""
    if not texte:
        return True
    h = MP._sans_accent(" ".join(str(c or "") for c in champs))
    return all(MP._sans_accent(m) in h for m in texte.split())


def contenus_du_cours(cours, matiere="", texte=""):
    """Dictionnaire {rubrique: [éléments]} d'un cours, filtré par matière et par texte."""
    C = MP.corpus()
    fiches = [f for f in C["fiches"] if f["cours"] == cours and (not matiere or f["matiere"] == matiere)
              and _trouve(texte, f.get("titre"), f.get("intitule"), f.get("sous_matiere"), f.get("contenus"), f.get("unite"))]
    fiches.sort(key=lambda f: (_ordre_mat(f["matiere"]), MP.num_unite(f) or 0, f.get("sa") or 0, f.get("seance") or 0, f.get("titre") or ""))
    resumes = [r for r in (C.get("resumes") or []) if r["cours"] == cours and (not matiere or r["matiere"] == matiere)
               and _trouve(texte, r.get("titre"), r.get("domaine"), r.get("etape"))]
    resumes.sort(key=lambda r: (_ordre_mat(r["matiere"]), MP.ordre_resume(r)))
    guides = [x for x in C["guides"] if cours in (x.get("cours") or []) and (not matiere or x["matiere"] == matiere)
              and _trouve(texte, x.get("titre"), x.get("groupe"))]
    guides.sort(key=lambda x: (_ordre_mat(x["matiere"]), x.get("groupe") or "", x["titre"]))
    progs = [p for p in C["programmes"] if p["cours"] == cours and (not matiere or p["matiere"] == matiere) and _trouve(texte, p.get("titre"))]
    progs.sort(key=lambda p: (_ordre_mat(p["matiere"]), p.get("dossier") or 0, p.get("num") or 0))
    evals = []
    if cours in B.COURS:
        for p in B.periodes_du_cours(cours):
            for e in B.organigramme(cours, p[2]):
                if matiere and e["matiere"] != matiere:
                    continue
                if not _trouve(texte, e["discipline"], p[1]):
                    continue
                evals.append({"cle": f"{cours}-{p[0]}-{e['code']}", "periode": p[1], "type": B.TYPES[p[2]], "discipline": e["discipline"],
                              "matiere": e["matiere"], "duree": e["duree"], "per": p[0]})
    return {"fiches": fiches, "resumes": resumes, "evaluations": evals, "guides": guides, "programmes": progs}


def matieres_du_cours(cours):
    """Matières ayant au moins un contenu pour le cours, dans l'ordre officiel, avec leurs effectifs."""
    tout = contenus_du_cours(cours)
    comptes = {}
    for rub, elts in tout.items():
        for e in elts:
            comptes.setdefault(e["matiere"], dict.fromkeys(tout, 0))[rub] += 1
    return [(m, comptes[m]) for m in sorted(comptes, key=_ordre_mat)]


def grouper_fiches(fiches):
    """[(unité/SA, [fiches])] dans l'ordre des fiches."""
    out, vus = [], {}
    for f in fiches:
        if f.get("unite"):
            k = f["unite"]
        elif f.get("sa"):
            k = f"SA {f['sa']}"
        else:
            k = f.get("sous_matiere") or "Fiches"
        if k not in vus:
            vus[k] = []
            out.append((k, vus[k]))
        vus[k].append(f)
    return out


def enregistrer(app, H):
    @app.route("/preparation/classes")
    @H.connexion_requise("preparation")
    def prep_classes():
        mes = set()
        if g.user["role"] == "enseignant":
            mes = {MP.NIVEAU_COURS.get(c["niveau"]) for c in H.classes_autorisees()}
        cartes = []
        for c in MP.COURS:
            t = contenus_du_cours(c)
            cartes.append({"cours": c, "lib": MP.COURS_LIB[c], "n": {k: len(v) for k, v in t.items()}, "mat": len(matieres_du_cours(c)),
                           "mienne": c in mes})
        return render_template("prep_classes.html", cartes=cartes, RUBRIQUES=RUBRIQUES)

    @app.route("/preparation/classes/<cours>")
    @H.connexion_requise("preparation")
    def prep_classe(cours):
        if cours not in MP.COURS:
            abort(404)
        mat = request.args.get("matiere") or ""
        texte = (request.args.get("q") or "").strip()
        mats = matieres_du_cours(cours)
        if mat and mat not in [m for m, _n in mats]:
            mat = ""
        t = contenus_du_cours(cours, mat, texte)
        return render_template("prep_classe.html", cours=cours, lib=MP.COURS_LIB[cours], mat=mat, q=texte, mats=mats, t=t,
                               fiches_groupes=grouper_fiches(t["fiches"]), RUBRIQUES=RUBRIQUES, COURS=MP.COURS,
                               total=sum(len(v) for v in t.values()))
