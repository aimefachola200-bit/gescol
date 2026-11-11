# -*- coding: utf-8 -*-
"""v1.10.6 — Module « Rubriques des fiches » (applications CS et DDEMP) : TOUTES les rubriques des fiches, dans
l'ordre des fiches officielles, consolidées par circonscription, par zone pédagogique ou par école.

Fiches : recensement (primaire, maternelle), rapport de rentrée (EP, EM), fiche de fin d'année (EP, EM).
Pour chaque rubrique (hors identification, état nominatif du personnel et visas) et chaque question :
  * question Oui / Non : nombre d'écoles « Oui », écoles ayant répondu, pourcentage ;
  * case à cocher : nombre d'écoles qui l'ont cochée ;
  * choix (unique ou multiple) : nombre d'écoles par option et pourcentage ;
  * nombre, montant, cellule de tableau : somme, et sur l'ensemble des écoles moyenne, ÉCART TYPE, minimum, maximum.
Secteur public et secteur privé présentés à part (onglets) ; export Excel de toutes les rubriques.
"""
import math
import re
import unicodedata
from collections import OrderedDict

from flask import abort, render_template, request

import config
import m_juridiction as J
import m_rapports as MRA
import m_recensement as MRE

FICHES = OrderedDict([
    ("recensement-primaire", ("recensement", "primaire", ("EP",), "Fiche de recensement – primaire")),
    ("recensement-maternelle", ("recensement", "maternelle", ("EM", "EE"), "Fiche de recensement – maternelle")),
    ("rentree-ep", ("rapports", "rentree-ep", ("EP",), "Rapport de rentrée – EP")),
    ("fin-ep", ("rapports", "fin-ep", ("EP",), "Fiche de fin d'année – EP")),
    ("rentree-em", ("rapports", "rentree-em", ("EM", "EE"), "Rapport de rentrée – EM")),
    ("fin-em", ("rapports", "fin-em", ("EM", "EE"), "Fiche de fin d'année – EM")),
])
_EXCLUS = ("identification", "etat nominatif", "visa", "signature", "personnel enseignant", "personnel de soutien")
_CACHE = {}


def _sa(t):
    return unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower()


def _net(t):
    return re.sub(r"\s+", " ", str(t or "")).strip(" :")


# ======================================================================== questions de chaque fiche
def _questions_recensement(typ):
    sch = MRE.SCHEMAS[typ]
    rubs = []
    for s in MRE.sections(sch):
        titre = _net(f"{s.get('num', '')}. {s['titre']}")
        if any(m in _sa(titre) for m in _EXCLUS):
            continue
        qs = []
        for it in s["items"]:
            for x in MRE._aplatir(it):
                if x["i"] in ("L", "G"):
                    for ch in x["champs"]:
                        if not isinstance(ch, dict) or ch["t"] in ("tx",):
                            continue
                        lib = MRE.libelle_champ(s, x, ch)
                        if ch["t"] == "on":
                            qs.append({"k": ch["k"], "lib": lib, "type": "on"})
                        elif ch["t"] == "case":
                            qs.append({"k": ch["k"], "lib": lib, "type": "case"})
                        elif ch["t"] == "ch":
                            qs.append({"k": ch["k"], "lib": lib, "type": "multi" if ch.get("multi") else "ch",
                                       "opts": list(ch["opts"])})
                        elif ch["t"] in ("nb", "mt"):
                            qs.append({"k": ch["k"], "lib": lib, "type": "nb"})
                elif x["i"] == "T" and not x.get("dyn"):
                    noms = MRE.chemins(x["cols"])
                    ttl = _net(x.get("titre") or "") or titre
                    for r in MRE.lignes_tableau(x):
                        for c in MRE.feuilles(x["cols"]):
                            if c["t"] in ("t", "an") or c["k"] in r.get("grise", ()) or c["k"] in ((r.get("fusion") or ((),))[0]):
                                continue
                            qs.append({"k": f"{x['k']}.{r['k']}.{c['k']}", "lib": f"{_net(r['lib'])} – {noms.get(c['k'], c['lib'])}",
                                       "type": "case" if c["t"] == "c" else "nb", "tab": ttl})
        if qs:
            rubs.append({"titre": titre, "qs": qs})
    return rubs


def _questions_rapport(doc):
    rubs = []
    for s in MRA.schema(doc):
        titre = _net(s["titre"])
        if any(m in _sa(titre) for m in _EXCLUS):
            continue
        qs = []
        for b in s["blocs"]:
            if b["t"] in ("champ", "choix") and b.get("type") != "titre":
                lib = _net(f"{b.get('num', '')} {b.get('lib', '')}")
                if b.get("type") == "choix" or b["t"] == "choix":
                    opts = list(b.get("options") or [])
                    if sorted(o.lower() for o in opts) == ["non", "oui"]:
                        qs.append({"k": b["k"], "lib": lib, "type": "on"})
                    else:
                        qs.append({"k": b["k"], "lib": lib, "type": "ch", "opts": opts})
                elif b.get("type") in ("nombre", "montant", "entier", "decimal"):
                    qs.append({"k": b["k"], "lib": lib, "type": "nb"})
            elif b["t"] == "tableau":
                for k, lib in MRA.cles_tableau(b):
                    qs.append({"k": k, "lib": _net(lib), "type": "nb", "tab": _net(b.get("titre") or titre)})
            elif b["t"] == "structure_ep":
                for k, lib in MRA.cles_structure(b):
                    qs.append({"k": k, "lib": _net(lib), "type": "nb", "tab": _net(b.get("titre") or "Structure pédagogique")})
        if qs:
            rubs.append({"titre": titre, "qs": qs})
    return rubs


def questions(code):
    """Rubriques et questions d'une fiche, dans l'ordre de la fiche officielle (mises en cache)."""
    if code not in _CACHE:
        sec, cle = FICHES[code][0], FICHES[code][1]
        _CACHE[code] = _questions_recensement(cle) if sec == "recensement" else _questions_rapport(cle)
    return _CACHE[code]


# ======================================================================== agrégation
def _nombre(v):
    if v is None or isinstance(v, (list, dict)):
        return None
    x = MRE.nombre(v)
    return float(x) if x is not None else None


def _oui(v):
    s = _sa(v).strip()
    return True if s in ("oui", "o", "1", "x", "true") else (False if s in ("non", "n", "0", "false") else None)


def _coche(v):
    return _sa(v).strip() in ("1", "x", "oui", "true", "on")


def _choisis(v):
    return v if isinstance(v, list) else [x.strip() for x in str(v or "").split(";") if x.strip()]


def nouvel_agregat(rubs):
    return {"ecoles": 0, "fiches": 0, "q": {q["k"]: {"oui": 0, "rep": 0, "opts": {}, "vals": []} for r in rubs for q in r["qs"]}}


def cumuler(x, rubs, val):
    x["ecoles"] += 1
    if not val:
        return
    x["fiches"] += 1
    for r in rubs:
        for q in r["qs"]:
            a, v = x["q"][q["k"]], val.get(q["k"])
            t = q["type"]
            if t == "on":
                o = _oui(v)
                if o is not None:
                    a["rep"] += 1
                    a["oui"] += 1 if o else 0
            elif t == "case":
                a["rep"] += 1
                a["oui"] += 1 if _coche(v) else 0
            elif t in ("ch", "multi"):
                ch = _choisis(v) if t == "multi" else ([str(v).strip()] if str(v or "").strip() else [])
                if ch:
                    a["rep"] += 1
                    for c in ch:
                        a["opts"][c] = a["opts"].get(c, 0) + 1
            else:
                n = _nombre(v)
                if n is not None:
                    a["vals"].append(n)


def stat(vals):
    if not vals:
        return {"n": 0, "somme": None, "moy": None, "et": None, "min": None, "max": None}
    m = sum(vals) / len(vals)
    return {"n": len(vals), "somme": round(sum(vals), 2), "moy": round(m, 2),
            "et": round(math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)), 2), "min": min(vals), "max": max(vals)}


def lignes_rubrique(rub, groupes, total):
    """Lignes affichables d'une rubrique : [{lib, tab, type, cells: [texte par groupe], total, stat}]."""
    out = []
    for q in rub["qs"]:
        t = q["type"]
        if t in ("on", "case"):
            def fmt(a):
                if not a["rep"]:
                    return None
                return (a["oui"], a["rep"], round(100.0 * a["oui"] / a["rep"], 1))
            cells = [fmt(g["q"][q["k"]]) for g in groupes]
            tot = fmt(total["q"][q["k"]])
            if tot is None and not any(cells):
                continue
            out.append({"lib": q["lib"], "tab": q.get("tab", ""), "type": "oui", "cells": cells, "total": tot,
                        "suffixe": "Oui" if t == "on" else "cochée"})
        elif t in ("ch", "multi"):
            opts = list(q.get("opts") or [])
            for o in total["q"][q["k"]]["opts"]:
                if o not in opts:
                    opts.append(o)
            if not total["q"][q["k"]]["rep"]:
                continue
            for o in opts:
                def fmt(a, o=o):
                    if not a["rep"]:
                        return None
                    n_ = a["opts"].get(o, 0)
                    return (n_, a["rep"], round(100.0 * n_ / a["rep"], 1))
                out.append({"lib": f"{q['lib']} → {o}", "tab": q.get("tab", ""), "type": "oui",
                            "cells": [fmt(g["q"][q["k"]]) for g in groupes], "total": fmt(total["q"][q["k"]]), "suffixe": ""})
        else:
            st = stat(total["q"][q["k"]]["vals"])
            if not st["n"]:
                continue
            out.append({"lib": q["lib"], "tab": q.get("tab", ""), "type": "nb",
                        "cells": [stat(g["q"][q["k"]]["vals"])["somme"] for g in groupes], "total": st["somme"], "stat": st})
    return out


# ======================================================================== page
def enregistrer(app, H):
    import a_tableau as T

    @app.route("/juridiction/fiches/rubriques")
    @H.connexion_requise()
    def jur_rubriques():
        if not config.juridiction():
            abort(404)
        flt = T.lire_filtres()
        par = request.args.get("par") if request.args.get("par") in ("cs", "zone", "ecole") else flt["par"]
        if par == "cs" and config.EDITION == "cs":
            par = "zone"
        fiche = request.args.get("fiche") if request.args.get("fiche") in FICHES else "recensement-primaire"
        sect = request.args.get("sect") if request.args.get("sect") in ("public", "prive") else "public"
        sec, cle, types, titre_f = FICHES[fiche]
        rubs = questions(fiche)
        lignes = [l for l in T.donnees(flt["annee"], flt["cs_id"], flt["zone_id"], flt["type"], None, flt["q"])
                  if l["type"] in types]
        nb_sect = {"public": sum(1 for l in lignes if l.get("secteur") != "prive"),
                   "prive": sum(1 for l in lignes if l.get("secteur") == "prive")}
        lignes = [l for l in lignes if (l.get("secteur") == "prive") == (sect == "prive")]
        s_rap = J.sections("rapports", flt["annee"], [l["id"] for l in lignes]) if sec == "rapports" else {}

        def valeurs(l):
            src = (l.get("_rec") or {}) if sec == "recensement" else (s_rap.get(l["id"]) or {})
            return ((src.get(cle) or {}).get("valeurs")) or None

        grp, tot = OrderedDict(), nouvel_agregat(rubs)
        for l in lignes:
            k, nom = ((l["cs_id"], l["cs_nom"] or "Sans circonscription") if par == "cs" else
                      (l["id"], l["nom"]) if par == "ecole" else (l["zone_id"], l["zone_nom"] or "Sans zone pédagogique"))
            if k not in grp:
                grp[k] = dict(nouvel_agregat(rubs), nom=nom)
            v = valeurs(l)
            cumuler(grp[k], rubs, v)
            cumuler(tot, rubs, v)
        groupes = list(grp.values())
        tables = [{"titre": r["titre"], "lignes": lignes_rubrique(r, groupes, tot)} for r in rubs]
        lib = {"cs": "Circonscription", "zone": "Zone pédagogique", "ecole": "École"}[par]
        if request.args.get("export") == "xlsx":
            haut = [config.ECOLE.get("nom", ""), f"{titre_f} – rubriques consolidées – secteur {'privé' if sect == 'prive' else 'public'} – "
                                                 f"année {flt['annee']} – par {lib.lower()}"]
            noms = [g["nom"] for g in groupes]
            vus, feuilles = set(), []
            for tb in tables:
                if not tb["lignes"]:
                    continue
                nom = re.sub(r"[\[\]:*?/\\]", " ", tb["titre"])[:28].strip() or "Rubrique"
                while nom.lower() in vus:
                    nom = nom[:25] + f" {len(vus)}"
                vus.add(nom.lower())
                rows = []
                for x in tb["lignes"]:
                    if x["type"] == "oui":
                        rows.append([x["tab"], x["lib"]] + [("" if c is None else f"{c[0]}/{c[1]}") for c in x["cells"]]
                                    + ["" if x["total"] is None else f"{x['total'][0]}/{x['total'][1]}",
                                       "" if x["total"] is None else x["total"][2], "", "", "", ""])
                    else:
                        s = x["stat"]
                        rows.append([x["tab"], x["lib"]] + ["" if c is None else c for c in x["cells"]]
                                    + [s["somme"], "", s["moy"], s["et"], s["min"], s["max"]])
                feuilles.append((nom, ["Tableau", "Question / case"] + noms + ["Total", "% (Oui)", "Moyenne par école",
                                                                                "Écart type", "Min", "Max"],
                                 rows, {"titre_haut": haut + [tb["titre"]]}))
            feuilles.append(("Écoles", [lib, "Écoles", "Fiches reçues"],
                             [[g["nom"], g["ecoles"], g["fiches"]] for g in groupes] + [["Total", tot["ecoles"], tot["fiches"]]],
                             {"titre_haut": haut}))
            H.journal("jur_rubriques", f"{fiche} {sect} {flt['annee']} xlsx")
            return H.xlsx.reponse_classeur(f"rubriques_{fiche}_{sect}_{flt['annee']}.xlsx", feuilles)
        return render_template("jur_rubriques.html", flt=flt, par=par, lib=lib, fiche=fiche, FICHES=FICHES, sect=sect,
                               nb_sect=nb_sect, groupes=groupes, tot=tot, tables=tables,
                               args=T.args_filtres(flt, par=par, fiche=fiche, sect=sect),
                               args_f=T.args_filtres(flt, par=par, sect=sect), args_s=T.args_filtres(flt, par=par, fiche=fiche),
                               args_p=T.args_filtres(flt, fiche=fiche, sect=sect))
