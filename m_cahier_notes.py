# -*- coding: utf-8 -*-
"""v2.9 — Cahier de notes de l'enseignant : toutes les notes de la classe sur une seule page.

Une ligne par élève, une colonne par évaluation de l'année (diagnostique, formative, sommative, certificative) pour la matière
choisie, ou la moyenne de chaque évaluation (« Toutes matières »). Moyenne de l'élève, rang, puis moyenne de la classe et taux
de notes à 10 et plus au bas de chaque colonne. Les notes viennent de la saisie par évaluation : rien n'est ressaisi.
L'enseignant le consulte dans sa classe ; le directeur, le conseiller pédagogique et la CS dans l'école ouverte.
Export Excel pour le cahier papier ou le classeur de la classe.
"""
import re

from flask import flash, redirect, render_template, request, url_for

import evaluations_core as EC
from calcul import classer, cycle_du_niveau


def enregistrer(app, H):
    H.DROITS["cahier_notes"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent", "enseignant"}

    def virgule(v, nd=2):
        return "" if v is None else (f"{v:.{nd}f}").rstrip("0").rstrip(".").replace(".", ",") if nd else str(v)

    def donnees(cid, mid):
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        cycle = cycle_du_niveau(cl["niveau"])
        matieres = list(EC.matieres_cycle(cycle))
        evs = EC.evaluations_classe(cid)
        eleves = list(EC.eleves_classe(cid))
        matiere = next((m for m in matieres if m["id"] == mid), None)
        colonnes, par_ev = [], []
        for ev in evs:
            mats, lignes = EC.resultats(ev, cl, eleves)
            if matiere is not None and matiere["id"] not in {m["id"] for m in mats}:
                continue                                         # matière non évaluée à cette occasion
            colonnes.append(ev)
            par_ev.append({l["eleve"]["id"]: l for l in lignes})
        rows = []
        for e in eleves:
            cells = []
            for ev, idx in zip(colonnes, par_ev):
                l = idx.get(e["id"])
                if not l:
                    cells.append(None)
                elif matiere is None:
                    cells.append(l["moyenne"])
                elif matiere["id"] in l["dispenses"]:
                    cells.append("D")
                else:
                    cells.append(l["notes"].get(matiere["id"]))
            nums = [c for c in cells if isinstance(c, (int, float))]
            rows.append({"eleve": e, "cells": cells, "moy": round(sum(nums) / len(nums), 2) if nums else None, "nb": len(nums)})
        rangs = classer({r["eleve"]["id"]: r["moy"] for r in rows})
        for r in rows:
            r["rang"], r["ex"] = rangs[r["eleve"]["id"]]
            r["rang_txt"] = "" if r["rang"] is None else f"{r['rang']}{'er' if r['rang'] == 1 else 'e'}{' ex æquo' if r['ex'] else ''}"
        stats = []
        for k in range(len(colonnes)):
            v = [r["cells"][k] for r in rows if isinstance(r["cells"][k], (int, float))]
            stats.append({"n": len(v), "moy": round(sum(v) / len(v), 2) if v else None,
                          "taux": round(100.0 * sum(1 for x in v if x >= 10) / len(v), 1) if v else None})
        mm = [r["moy"] for r in rows if r["moy"] is not None]
        return dict(cl=cl, cycle=cycle, matieres=matieres, matiere=matiere, colonnes=colonnes, rows=rows, stats=stats,
                    moy_classe=round(sum(mm) / len(mm), 2) if mm else None,
                    taux_classe=round(100.0 * sum(1 for x in mm if x >= 10) / len(mm), 1) if mm else None)

    def fiche(cid, evid):
        """Fiche d'évaluation d'UNE évaluation (même présentation que la saisie et l'Excel des évaluations) :
        une colonne par matière, puis moyenne, matières à 10 et plus, décision (maîtrise / admis) et rang."""
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        ev = EC.evaluation(evid)
        if not ev or ev["classe_id"] != cid:
            return None
        mats, lignes = EC.resultats(ev, cl, list(EC.eleves_classe(cid)))
        stats = []
        for m in mats:
            v = [l["notes"][m["id"]] for l in lignes if isinstance(l["notes"].get(m["id"]), (int, float))]
            stats.append({"moy": round(sum(v) / len(v), 2) if v else None,
                          "taux": round(100.0 * sum(1 for x in v if x >= 10) / len(v), 1) if v else None})
        composes = [l for l in lignes if l["compose"]]
        maitrise = sum(1 for l in composes if l["maitrise"])
        return dict(ev=ev, mats=mats, lignes=lignes, fstats=stats, seuil=EC.seuil_de(ev, len(mats)), nb_composes=len(composes),
                    taux_maitrise=round(100.0 * maitrise / len(composes), 1) if composes else None)

    @app.route("/cahier-notes")
    @H.connexion_requise("cahier_notes")
    def cnotes_accueil():
        classes = H.classes_autorisees()
        cid = request.args.get("classe", type=int)
        if cid is None and len(classes) == 1:
            cid = classes[0]["id"]
        mid = request.args.get("matiere", type=int) or 0
        evid = request.args.get("evaluation", type=int) or 0
        d = donnees(cid, mid) if cid else {}
        f = (fiche(cid, evid) if cid and evid else None) or {}
        return render_template("cahier_notes.html", evaluations=(EC.evaluations_classe(cid) if cid else []), classes=classes, cid=cid, mid=mid, evid=evid if f else 0, virgule=virgule, f=f, **d)

    @app.route("/cahier-notes/export.xlsx")
    @H.connexion_requise("cahier_notes")
    def cnotes_export():
        cid = request.args.get("classe", type=int)
        if not cid:
            return redirect(url_for("cnotes_accueil"))
        mid = request.args.get("matiere", type=int) or 0
        evid = request.args.get("evaluation", type=int) or 0
        f = fiche(cid, evid) if evid else None
        if f:
            return export_fiche(cid, f)
        d = donnees(cid, mid)
        cl = d["cl"]
        ent = ["N°", "Matricule", "Nom", "Prénoms", "Sexe"] + [ev["libelle"] for ev in d["colonnes"]] + ["Moyenne", "Rang"]
        rows = []
        for i, r in enumerate(d["rows"], 1):
            e = r["eleve"]
            rows.append([i, e["matricule"], e["nom"], e["prenoms"], e["sexe"]] + [c for c in r["cells"]] + [r["moy"], r["rang_txt"]])
        rows.append(["", "", "Moyenne de la classe", "", ""] + [s["moy"] for s in d["stats"]] + [d["moy_classe"], ""])
        rows.append(["", "", "Notes à 10 et plus (%)", "", ""] + [s["taux"] for s in d["stats"]] + [d["taux_classe"], ""])
        mat = d["matiere"]["nom"] if d["matiere"] else "Toutes matières"
        base = re.sub(r"[^A-Za-z0-9]+", "_", H.xlsx.normaliser(f"{cl['nom']} {mat}")).strip("_")
        try:
            return H.xlsx.reponse_xlsx(f"Cahier_de_notes_{base}.xlsx", ent, rows, titre="Cahier de notes",
                                       titre_haut=[f"Cahier de notes — {cl['nom']} ({cl['niveau']})",
                                                   f"Année scolaire : {EC.config.ANNEE_ACTIVE}    Matière : {mat}",
                                                   "Notes sur 20 ; D = dispensé ; case vide = pas de note"])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("cnotes_accueil", classe=cid, matiere=mid))

    def export_fiche(cid, f):
        cl, ev, mats = H.classe_ou_404(cid), f["ev"], f["mats"]
        ent = ["N°", "Matricule", "Nom", "Prénoms", "Sexe"] + [m["nom"] for m in mats] + ["Moyenne", f"Matières ≥ 10 (seuil {f['seuil']})", "Décision", "Rang"]
        rows = []
        for i, l in enumerate(f["lignes"], 1):
            e = l["eleve"]
            rows.append([i, e["matricule"], e["nom"], e["prenoms"], e["sexe"]] + ["D" if m["id"] in l["dispenses"] else l["notes"].get(m["id"]) for m in mats]
                        + [l["moyenne"], l["reussies"] if l["compose"] else None, l["decision"], l["rang_texte"]])
        rows.append(["", "", "Moyenne de la matière", "", ""] + [s["moy"] for s in f["fstats"]] + ["", "", "", ""])
        rows.append(["", "", "Notes à 10 et plus (%)", "", ""] + [s["taux"] for s in f["fstats"]] + ["", "", f["taux_maitrise"], ""])
        base = re.sub(r"[^A-Za-z0-9]+", "_", H.xlsx.normaliser(f"{cl['nom']} {ev['libelle']}")).strip("_")
        try:
            return H.xlsx.reponse_xlsx(f"Cahier_de_notes_{base}.xlsx", ent, rows, titre=ev["libelle"],
                                       titre_haut=[f"Cahier de notes — {ev['titre']} — {cl['nom']} ({cl['niveau']})",
                                                   f"Année scolaire : {ev['annee']}    Seuil de maîtrise : {f['seuil']}/{len(mats)}",
                                                   "Notes sur 20 ; D = dispensé ; case vide = pas de note"])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("cnotes_accueil", classe=cid, evaluation=ev["id"]))
