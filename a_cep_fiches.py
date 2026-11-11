# -*- coding: utf-8 -*-
"""v1.10.7 — Module « CEP : candidats et réussite selon les rubriques des fiches » (applications CS et DDEMP).

Page /juridiction/cep/fiches. Source au choix :
  * fiche de recensement, rubrique 9 « Résultats aux examens de la dernière session » : CEP, CEP Vie active, Ensemble,
    dont enfants handicapés × Inscrits / Ont composé / Admis, par sexe ;
  * fiche de fin d'année (EP), annexe « résultats au CEP » : candidats inscrits / présents / admis, par sexe ;
  * module CEP (candidats et admis transmis par les écoles).
Par circonscription (DDEMP), par zone pédagogique ou par école ; SECTEUR PUBLIC ET PRIVÉ À PART :
  1. candidats (inscrits) par sexe et pourcentage (part des garçons, des filles, indice de parité F/G), candidats ayant
     composé et taux de présence ;
  2. réussite : admis par sexe, taux de réussite garçons / filles / ensemble, écart filles − garçons ;
  3. tableau de la rubrique 9 complète (CEP, CEP Vie active, Ensemble, dont enfants handicapés) ;
  4. dispersion des taux de réussite des écoles : moyenne, ÉCART TYPE, minimum, maximum, écoles à 100 % et sous 50 %.
Graphiques au choix ; export Excel.
"""
import math

from flask import abort, render_template, request

import config
import m_juridiction as J

SOURCES = {"recensement": "Fiche de recensement (rubrique 9)", "fin": "Fiche de fin d'année (annexe CEP)",
           "module": "Module CEP (résultats transmis)"}
EXAMENS = [("cep", "CEP"), ("cva", "CEP Vie active"), ("ens", "Ensemble"), ("eh", "Dont enfants handicapés")]
ETAPES = [("insc", "Inscrits"), ("comp", "Ont composé"), ("adm", "Admis")]
_R9 = {"insc": "inscrits", "comp": "composes", "adm": "admis"}
PALETTE = ["#2a78d6", "#eb6834", "#1b7f3b", "#8e44ad", "#c99a06", "#d6336c"]


def n(v):
    try:
        return max(0, int(round(float(str(v).replace(",", ".").replace(" ", "")))))
    except (TypeError, ValueError):
        return 0


def _vide_ex():
    return {e: {k: [0, 0] for k, _ in ETAPES} for e, _ in EXAMENS}


def lire_ecole(l, source):
    """{fiche: bool, ex: {examen: {étape: [g, f]}}} pour une école primaire."""
    d = {"fiche": False, "ex": _vide_ex()}
    if source == "recensement":
        val = (((l.get("_rec") or {}).get("primaire") or {}).get("valeurs") or {})
        for e, _l in EXAMENS:
            for k, _lk in ETAPES:
                g, f = n(val.get(f"t9.{_R9[k]}.{e}_g")), n(val.get(f"t9.{_R9[k]}.{e}_f"))
                if e == "ens" and not (g or f):          # Ensemble = CEP + CEP Vie active si non transmis
                    g = d["ex"]["cep"][k][0] + d["ex"]["cva"][k][0]
                    f = d["ex"]["cep"][k][1] + d["ex"]["cva"][k][1]
                d["ex"][e][k] = [g, f]
        d["fiche"] = any(n(v) for k, v in val.items() if k.startswith("t9."))
    elif source == "fin":
        val = ((((l.get("_rap") or {}).get("fin-ep")) or {}).get("valeurs") or {})
        for k, kk in (("insc", "insc"), ("comp", "pres"), ("adm", "adm")):
            d["ex"]["cep"][k] = [n(val.get(f"cep.{kk}.G")), n(val.get(f"cep.{kk}.F"))]
        d["ex"]["ens"] = {k: list(v) for k, v in d["ex"]["cep"].items()}
        d["fiche"] = any(sum(v) for v in d["ex"]["cep"].values())
    else:
        c = l.get("cep") or {}
        if c.get("candidats"):
            d["ex"]["cep"]["insc"] = [n(c.get("candidats_g")), n(c.get("candidats_f"))]
            d["ex"]["cep"]["comp"] = list(d["ex"]["cep"]["insc"])
            if c.get("admis") is not None:
                d["ex"]["cep"]["adm"] = [n(c.get("admis_g")), n(c.get("admis_f"))]
            d["ex"]["ens"] = {k: list(v) for k, v in d["ex"]["cep"].items()}
            d["fiche"] = True
    return d


def taux(a, b):
    return round(100.0 * a / b, 1) if b else None


def nouveau():
    return {"ecoles": 0, "fiches": 0, "ex": _vide_ex(), "_taux": [], "_taux_g": [], "_taux_f": []}


def cumuler(x, d):
    x["ecoles"] += 1
    if not d["fiche"]:
        return
    x["fiches"] += 1
    for e in x["ex"]:
        for k in x["ex"][e]:
            x["ex"][e][k][0] += d["ex"][e][k][0]
            x["ex"][e][k][1] += d["ex"][e][k][1]
    c = d["ex"]["cep"]
    base = c["comp"] if sum(c["comp"]) else c["insc"]
    if sum(base) and (sum(c["adm"]) or sum(c["comp"])):
        x["_taux"].append(100.0 * sum(c["adm"]) / sum(base))
        if base[0]:
            x["_taux_g"].append(100.0 * c["adm"][0] / base[0])
        if base[1]:
            x["_taux_f"].append(100.0 * c["adm"][1] / base[1])


def disp(vals):
    if not vals:
        return {"n": 0, "moy": None, "et": None, "min": None, "max": None, "cent": 0, "sous50": 0}
    m = sum(vals) / len(vals)
    return {"n": len(vals), "moy": round(m, 1), "et": round(math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)), 1),
            "min": round(min(vals), 1), "max": round(max(vals), 1), "cent": sum(1 for v in vals if v >= 99.95),
            "sous50": sum(1 for v in vals if v < 50)}


def indicateurs(x):
    """Pour chaque examen : totaux G/F/T, parts, présence, réussite, parité, écart F − G ; dispersion des écoles."""
    x["ind"] = {}
    for e in x["ex"]:
        r = {k: [v[0], v[1], v[0] + v[1]] for k, v in x["ex"][e].items()}
        ins, comp, adm = r["insc"], r["comp"], r["adm"]
        base = comp if comp[2] else ins
        i = {"r": r, "p_g": taux(ins[0], ins[2]), "p_f": taux(ins[1], ins[2]),
             "parite": round(ins[1] / ins[0], 2) if ins[0] else None,
             "presence": [taux(comp[j], ins[j]) for j in range(3)] if comp[2] else [None, None, None],
             "reussite": [taux(adm[j], base[j]) for j in range(3)] if adm[2] or comp[2] else [None, None, None]}
        rg, rf = i["reussite"][0], i["reussite"][1]
        i["ecart"] = round(rf - rg, 1) if rg is not None and rf is not None else None
        i["parite_r"] = round(rf / rg, 2) if rg and rf is not None else None
        x["ind"][e] = i
    x["disp"] = {"T": disp(x["_taux"]), "G": disp(x["_taux_g"]), "F": disp(x["_taux_f"])}
    return x


def calculer(lignes, source, par):
    def cle_nom(l):
        if par == "cs":
            return l["cs_id"], l["cs_nom"] or "Sans circonscription"
        if par == "ecole":
            return l["id"], l["nom"]
        return l["zone_id"], l["zone_nom"] or "Sans zone pédagogique"

    grp, tot = {}, {"nom": "Total", "pub": nouveau(), "prv": nouveau()}
    for l in lignes:
        if l.get("type") != "EP":
            continue
        k, nom = cle_nom(l)
        g = grp.setdefault(k, {"nom": nom, "pub": nouveau(), "prv": nouveau()})
        d = lire_ecole(l, source)
        s = "prv" if l.get("secteur") == "prive" else "pub"
        cumuler(g[s], d)
        cumuler(tot[s], d)
    for x in list(grp.values()) + [tot]:
        indicateurs(x["pub"])
        indicateurs(x["prv"])
    return list(grp.values()), tot


def enregistrer(app, H):
    import a_effectifs as E
    import a_tableau as T

    @app.route("/juridiction/cep/fiches")
    @H.connexion_requise()
    def jur_cep_fiches():
        if not config.juridiction():
            abort(404)
        flt = T.lire_filtres()
        par = request.args.get("par") if request.args.get("par") in ("cs", "zone", "ecole") else flt["par"]
        if par == "cs" and config.EDITION == "cs":
            par = "zone"
        source = request.args.get("source") if request.args.get("source") in SOURCES else "recensement"
        lignes = T.donnees(flt["annee"], flt["cs_id"], flt["zone_id"], "EP", flt["secteur"], flt["q"])
        if source == "fin":
            s_rap = J.sections("rapports", flt["annee"], [l["id"] for l in lignes])
            for l in lignes:
                l["_rap"] = s_rap.get(l["id"]) or {}
        grp, tot = calculer(lignes, source, par)
        lib = {"cs": "Circonscription", "zone": "Zone pédagogique", "ecole": "École"}[par]
        noms = [g["nom"] for g in grp]
        courbes = {}
        for s in ("pub", "prv"):
            ind = lambda g: g[s]["ind"]["cep"]  # noqa: E731
            courbes[s] = {
                "cand": E.svg_courbes(noms, [("Garçons", PALETTE[0], [ind(g)["r"]["insc"][0] for g in grp]),
                                             ("Filles", PALETTE[1], [ind(g)["r"]["insc"][1] for g in grp]),
                                             ("Ont composé", PALETTE[3], [ind(g)["r"]["comp"][2] for g in grp])], "Candidats au CEP"),
                "taux": E.svg_courbes(noms, [("Réussite – garçons (%)", PALETTE[0], [ind(g)["reussite"][0] for g in grp]),
                                             ("Réussite – filles (%)", PALETTE[1], [ind(g)["reussite"][1] for g in grp]),
                                             ("Réussite – ensemble (%)", PALETTE[2], [ind(g)["reussite"][2] for g in grp])], "Taux de réussite au CEP"),
                "disp": E.svg_courbes(noms, [("Moyenne des écoles (%)", PALETTE[2], [g[s]["disp"]["T"]["moy"] for g in grp]),
                                             ("Écart type", PALETTE[3], [g[s]["disp"]["T"]["et"] for g in grp])], "Dispersion des taux des écoles"),
            }
        if request.args.get("export") == "xlsx":
            haut = [config.ECOLE.get("nom", ""), f"CEP : candidats et réussite – {SOURCES[source]} – année {flt['annee']} – par {lib.lower()}"]
            feuilles = []
            for s, sl in (("pub", "public"), ("prv", "privé")):
                lst = [g for g in grp + [tot] if g[s]["ecoles"]]
                c = lambda g: g[s]["ind"]["cep"]  # noqa: E731
                feuilles.append((f"Candidats ({sl})", [lib, "Écoles", "Fiches", "Inscrits G", "Inscrits F", "Inscrits", "% garçons",
                                                       "% filles", "Parité F/G", "Ont composé G", "Ont composé F", "Ont composé",
                                                       "Présence G %", "Présence F %", "Présence %"],
                                 [[g["nom"], g[s]["ecoles"], g[s]["fiches"]] + c(g)["r"]["insc"] + [c(g)["p_g"], c(g)["p_f"], c(g)["parite"]]
                                  + c(g)["r"]["comp"] + c(g)["presence"] for g in lst], {"titre_haut": haut}))
                feuilles.append((f"Réussite ({sl})", [lib, "Admis G", "Admis F", "Admis", "Réussite G %", "Réussite F %", "Réussite %",
                                                      "Écart F − G (points)", "Parité F/G", "Moyenne des écoles %", "Écart type",
                                                      "Min %", "Max %", "Écoles à 100 %", "Écoles sous 50 %"],
                                 [[g["nom"]] + c(g)["r"]["adm"] + c(g)["reussite"] + [c(g)["ecart"], c(g)["parite_r"]]
                                  + [g[s]["disp"]["T"][k] for k in ("moy", "et", "min", "max", "cent", "sous50")] for g in lst],
                                 {"titre_haut": haut}))
                feuilles.append((f"Rubrique 9 ({sl})", ["Examen", "Étape", "G", "F", "Total", "Taux (%)"],
                                 [[le, lk] + tot[s]["ind"][e]["r"][k] + [tot[s]["ind"][e]["reussite"][2] if k == "adm" else
                                                                         (tot[s]["ind"][e]["presence"][2] if k == "comp" else None)]
                                  for e, le in EXAMENS for k, lk in ETAPES], {"titre_haut": haut + ["Total de la juridiction"]}))
            H.journal("jur_cep_fiches", f"{flt['annee']} {source} xlsx")
            return H.xlsx.reponse_classeur(f"cep_fiches_{source}_{flt['annee']}_par_{par}.xlsx", feuilles)
        return render_template("jur_cep_fiches.html", flt=flt, par=par, lib=lib, grp=grp, tot=tot, source=source,
                               SOURCES=SOURCES, EXAMENS=EXAMENS, ETAPES=ETAPES, courbes=courbes,
                               args=T.args_filtres(flt, par=par, source=source), args0=T.args_filtres(flt, source=source),
                               args1=T.args_filtres(flt, par=par))
