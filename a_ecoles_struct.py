# -*- coding: utf-8 -*-
"""v1.10.6 — Module « Écoles : nombre, structure pédagogique et équipements » (applications CS et DDEMP).

Page /juridiction/ecoles-structure, d'après la fiche de recensement, le rapport de rentrée ou la fiche de fin d'année
(au choix), par circonscription (DDEMP), par zone pédagogique ou par école, SECTEUR PUBLIC et SECTEUR PRIVÉ À PART :
  1. nombre d'écoles (primaires, maternelles, espaces enfance) et fiches reçues ;
  2. classes (sections) autorisées et ouvertes, salles existantes et utilisées ;
  3. structure pédagogique : classes simples, jumelées, multigrades (et part des multigrades) ;
  4. statistiques par école : moyenne, ÉCART TYPE, minimum et maximum des classes ouvertes, des élèves par école et
     des élèves par classe ;
  5. équipements et commodités : eau potable et sa source (SONEB, forage, adduction villageoise, PUITS, citerne,
     autre), électricité et sa source (SBEE, groupe électrogène, solaire, autre), cantine, latrines, lavage des mains,
     clôture, domaine délimité, cour ombragée, jardin, bibliothèque, boîte à pharmacie, terrain de sport, aire de jeu,
     titre de propriété — en nombre et en pourcentage des écoles ayant répondu.
Une courbe par tableau ; export Excel.
"""
import math
import unicodedata

from flask import abort, render_template, request

import config
import m_juridiction as J
from a_infra import SOURCES, _DOCS, n, oui_non

NIV_EP = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
STRUCT = [("simple", "Simples"), ("jumelee", "Jumelées"), ("multi", "Multigrades")]
EAU = [("soneb", "SONEB"), ("forage", "Forage"), ("aev", "Adduction d'eau villageoise"), ("puits", "Puits"),
       ("citerne", "Citerne"), ("autre", "Autre source")]
ELEC = [("sbee", "SBEE"), ("groupe", "Groupe électrogène"), ("solaire", "Énergie solaire"), ("autre", "Autre source")]
EQUIP = [("eau", "Eau potable"), ("elec", "Électricité"), ("cantine", "Cantine"), ("latrines", "Latrines"),
         ("lavage", "Lavage des mains"), ("cloture", "Clôture"), ("domaine", "Domaine délimité"),
         ("ombre", "Cour ombragée"), ("jardin", "Jardin / champ scolaire"), ("biblio", "Bibliothèque"),
         ("pharmacie", "Boîte à pharmacie"), ("sport", "Terrain de sport / aire de jeu"),
         ("titre", "Titre de propriété (acte)")]
STATS = [("classes", "Classes ouvertes par école"), ("eleves", "Élèves par école"), ("taille", "Élèves par classe")]
PALETTE = ["#2a78d6", "#eb6834", "#1b7f3b", "#8e44ad", "#c99a06", "#d6336c", "#0f766e", "#64748b"]


def _sa(s):
    return unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()


def sources_choisies(v, table):
    """Valeur d'une case à cocher multiple (liste ou texte « a;b ») → ensemble de clés de la table."""
    items = v if isinstance(v, list) else [x for x in str(v or "").split(";") if x.strip()]
    out = set()
    for it in items:
        t = _sa(it)
        for k, _l in table:
            if (k == "aev" and "adduction" in t) or (k == "groupe" and "groupe" in t) or (k == "solaire" and "solaire" in t) \
                    or (k == "autre" and "autre" in t) or (k not in ("aev", "groupe", "solaire", "autre") and k in t):
                out.add(k)
                break
    return out


def moy_ecart(vals):
    """(moyenne, écart type de la population, minimum, maximum) ; None si la liste est vide."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "moy": None, "et": None, "min": None, "max": None}
    m = sum(vals) / len(vals)
    return {"n": len(vals), "moy": round(m, 2), "et": round(math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)), 2),
            "min": min(vals), "max": max(vals)}


# ======================================================================== lecture d'une école
def lire_ecole(l, source):
    """{fiche, aut, ouv, s_exist, s_util, struct{simple,jumelee,multi}, equip{k: bool|None}, eau_src, elec_src}."""
    em = l.get("type") in ("EM", "EE")
    d = {"fiche": False, "aut": 0, "ouv": 0, "s_exist": 0, "s_util": 0, "struct": {k: 0 for k, _ in STRUCT},
         "equip": {k: None for k, _ in EQUIP}, "eau_src": set(), "elec_src": set()}
    if source == "recensement":
        val = (((l.get("_rec") or {}).get("maternelle" if em else "primaire") or {}).get("valeurs") or {})
    else:
        val = (((l.get("_rap") or {}).get(_DOCS[source]["EM" if em else "EP"]) or {}).get("valeurs") or {})
    if not val:
        return d
    d["fiche"] = True
    d["s_exist"], d["s_util"] = n(val.get("salles_existantes")), n(val.get("salles_utilisees"))
    if em:
        d["aut"], d["ouv"] = n(val.get("sections_autorisees")), n(val.get("sections_existantes") or val.get("sections_ouvertes"))
    else:
        d["aut"], d["ouv"] = n(val.get("classes_autorisees")), n(val.get("classes_existantes") or val.get("classes_ouvertes"))
    st = d["struct"]
    if source == "recensement" and not em:          # tableau 3.14 : simples / jumelés / multigrades × cours + salles
        for row, k in (("simples", "simple"), ("jumeles", "jumelee"), ("multi", "multi")):
            par_niv = [n(val.get(f"t314.{row}.{x.lower()}")) for x in NIV_EP]
            salles = n(val.get(f"t314.{row}.salles"))
            st[k] = sum(par_niv) if k == "simple" else (salles or (sum(par_niv) + 1) // 2 if k == "jumelee" else salles or max(par_niv))
    elif source == "recensement":                   # tableau 4 (maternelle) : simple / jumelée / multigrade
        for row in ("simple", "jumelee", "multi"):
            pe, gr, salles = n(val.get(f"t4.{row}.pe")), n(val.get(f"t4.{row}.gr")), n(val.get(f"t4.{row}.salles"))
            st[row] = pe + gr if row == "simple" else (salles or max(pe, gr))
    elif not em:                                    # rapports du primaire : bloc « structure pédagogique »
        st["simple"] = sum(n(val.get(f"sp.simple.{x}")) for x in NIV_EP)
        st["jumelee"] = n(val.get("sp.jumelee.salles")) or sum(n(v) for k, v in val.items()
                                                                if k.startswith("sp.jumelee.") and k != "sp.jumelee.salles")
        st["multi"] = n(val.get("sp.multi.salles")) or max([n(val.get(f"sp.multi.{x}")) for x in NIV_EP] or [0])
    else:                                           # rapports de la maternelle
        for row in ("simple", "jumelee", "multi"):
            pe, gr, salles = n(val.get(f"sp.{row}.pet")), n(val.get(f"sp.{row}.gra")), n(val.get(f"sp.{row}.salles"))
            st[row] = pe + gr if row == "simple" else (salles or max(pe, gr))
    e = d["equip"]
    if source == "recensement":
        if em:
            e.update(eau=oui_non(val.get("eau")), elec=oui_non(val.get("electricite")), cantine=oui_non(val.get("cantine")),
                     latrines=oui_non(val.get("latrines")), lavage=oui_non(val.get("lavage")), cloture=oui_non(val.get("cloture")),
                     pharmacie=oui_non(val.get("pharmacie")), sport=oui_non(val.get("aire_jeu")), titre=oui_non(val.get("titre")))
            d["eau_src"] = sources_choisies(val.get("eau_src"), EAU)
        else:
            tp = _sa(val.get("titre_propriete"))
            e.update(eau=oui_non(val.get("point_eau")), elec=oui_non(val.get("electricite")), cantine=oui_non(val.get("cantine")),
                     latrines=oui_non(val.get("latrines")), lavage=oui_non(val.get("lavage_mains")),
                     cloture=oui_non(val.get("cloture")), domaine=oui_non(val.get("domaine_delimite")),
                     ombre=oui_non(val.get("cour_ombragee")), jardin=oui_non(val.get("jardin")),
                     biblio=oui_non(val.get("bibliotheque")), pharmacie=oui_non(val.get("pharmacie")),
                     sport=oui_non(val.get("sport_trace")), titre=(None if not tp else "aucun" not in tp))
            d["eau_src"] = sources_choisies(val.get("point_eau_src"), EAU)
        d["elec_src"] = sources_choisies(val.get("electricite_src"), ELEC)
        if d["eau_src"] and e["eau"] is None:
            e["eau"] = True
        if d["elec_src"] and e["elec"] is None:
            e["elec"] = True
    else:
        e.update(cantine=oui_non(val.get("cantine")), lavage=oui_non(val.get("lavage")))
    return d


# ======================================================================== agrégation
def nouveau():
    return {"ecoles": 0, "EP": 0, "EM": 0, "EE": 0, "fiches": 0, "aut": 0, "ouv": 0, "s_exist": 0, "s_util": 0,
            "struct": {k: 0 for k, _ in STRUCT}, "equip": {k: [0, 0] for k, _ in EQUIP},
            "eau_src": {k: 0 for k, _ in EAU}, "elec_src": {k: 0 for k, _ in ELEC},
            "_classes": [], "_eleves": [], "_taille": []}


def cumuler(x, d, l):
    x["ecoles"] += 1
    x[l.get("type") if l.get("type") in ("EP", "EM", "EE") else "EP"] += 1
    eff = l.get("eff") or {}
    if n(eff.get("t")):
        x["_eleves"].append(n(eff.get("t")))
    x["_taille"] += [t for t in (eff.get("tailles") or []) if t]
    if not d["fiche"]:
        if n(eff.get("classes")):
            x["_classes"].append(n(eff.get("classes")))
        return
    x["fiches"] += 1
    for k in ("aut", "ouv", "s_exist", "s_util"):
        x[k] += d[k]
    for k in x["struct"]:
        x["struct"][k] += d["struct"][k]
    ouv = d["ouv"] or sum(d["struct"].values()) or n(eff.get("classes"))
    if ouv:
        x["_classes"].append(ouv)
    for k, v in d["equip"].items():
        if v is not None:
            x["equip"][k][1] += 1
            x["equip"][k][0] += 1 if v else 0
    for k in d["eau_src"]:
        x["eau_src"][k] += 1
    for k in d["elec_src"]:
        x["elec_src"][k] += 1


def indicateurs(x):
    tot = sum(x["struct"].values())
    x["struct_tot"] = tot
    x["p_multi"] = round(100.0 * x["struct"]["multi"] / tot, 1) if tot else None
    x["p_jum"] = round(100.0 * x["struct"]["jumelee"] / tot, 1) if tot else None
    x["p_equip"] = {k: (round(100.0 * v[0] / v[1], 1) if v[1] else None) for k, v in x["equip"].items()}
    rep_eau = x["equip"]["eau"][1]
    x["p_eau_src"] = {k: (round(100.0 * v / rep_eau, 1) if rep_eau else None) for k, v in x["eau_src"].items()}
    rep_el = x["equip"]["elec"][1]
    x["p_elec_src"] = {k: (round(100.0 * v / rep_el, 1) if rep_el else None) for k, v in x["elec_src"].items()}
    x["stats"] = {"classes": moy_ecart(x["_classes"]), "eleves": moy_ecart(x["_eleves"]), "taille": moy_ecart(x["_taille"])}
    x["taux_ouv"] = round(100.0 * x["ouv"] / x["aut"], 1) if x["aut"] else None
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
        k, nom = cle_nom(l)
        g = grp.setdefault(k, {"nom": nom, "pub": nouveau(), "prv": nouveau()})
        d = lire_ecole(l, source)
        s = "prv" if l.get("secteur") == "prive" else "pub"
        cumuler(g[s], d, l)
        cumuler(tot[s], d, l)
    for x in list(grp.values()) + [tot]:
        indicateurs(x["pub"])
        indicateurs(x["prv"])
    return list(grp.values()), tot


# ======================================================================== page
def enregistrer(app, H):
    import a_effectifs as E
    import a_tableau as T

    @app.route("/juridiction/ecoles-structure")
    @H.connexion_requise()
    def jur_ecoles_struct():
        if not config.juridiction():
            abort(404)
        flt = T.lire_filtres()
        par = request.args.get("par") if request.args.get("par") in ("cs", "zone", "ecole") else flt["par"]
        if par == "cs" and config.EDITION == "cs":
            par = "zone"
        source = request.args.get("source") if request.args.get("source") in SOURCES else "recensement"
        lignes = T.donnees(flt["annee"], flt["cs_id"], flt["zone_id"], flt["type"], flt["secteur"], flt["q"])
        s_rap = J.sections("rapports", flt["annee"], [l["id"] for l in lignes])
        for l in lignes:
            l["_rap"] = s_rap.get(l["id"]) or {}
        grp, tot = calculer(lignes, source, par)
        lib = {"cs": "Circonscription", "zone": "Zone pédagogique", "ecole": "École"}[par]
        noms = [g["nom"] for g in grp]
        courbes = {}
        for s in ("pub", "prv"):
            courbes[s] = {
                "ecoles": E.svg_courbes(noms, [("Primaires", PALETTE[0], [g[s]["EP"] for g in grp]),
                                               ("Maternelles", PALETTE[1], [g[s]["EM"] for g in grp]),
                                               ("Fiches reçues", PALETTE[2], [g[s]["fiches"] for g in grp])], "Écoles"),
                "classes": E.svg_courbes(noms, [("Autorisées", PALETTE[3], [g[s]["aut"] for g in grp]),
                                                ("Ouvertes", PALETTE[0], [g[s]["ouv"] for g in grp]),
                                                ("Salles utilisées", PALETTE[2], [g[s]["s_util"] for g in grp])], "Classes et salles"),
                "struct": E.svg_courbes(noms, [(l_, PALETTE[i], [g[s]["struct"][k] for g in grp]) for i, (k, l_) in enumerate(STRUCT)],
                                        "Structure pédagogique"),
                "stats": E.svg_courbes(noms, [("Élèves par classe – moyenne", PALETTE[0], [g[s]["stats"]["taille"]["moy"] for g in grp]),
                                              ("Élèves par classe – écart type", PALETTE[1], [g[s]["stats"]["taille"]["et"] for g in grp]),
                                              ("Classes par école – moyenne", PALETTE[2], [g[s]["stats"]["classes"]["moy"] for g in grp])],
                                       "Moyennes et écarts types"),
                "equip": E.svg_courbes(noms, [(l_, PALETTE[i % len(PALETTE)], [g[s]["p_equip"][k] for g in grp])
                                              for i, (k, l_) in enumerate(EQUIP[:6])], "Équipements (% des écoles)"),
                "eau": E.svg_courbes(noms, [(l_, PALETTE[i], [g[s]["eau_src"][k] for g in grp]) for i, (k, l_) in enumerate(EAU)],
                                     "Sources d'eau (nombre d'écoles)"),
            }
        if request.args.get("export") == "xlsx":
            haut = [config.ECOLE.get("nom", ""), f"Écoles : nombre, structure et équipements – {SOURCES[source]} – année {flt['annee']} – par {lib.lower()}"]
            feuilles = []
            for s, sl in (("pub", "public"), ("prv", "privé")):
                lst = grp + [tot]

                def f(nom, ent, vals):
                    feuilles.append((f"{nom} ({sl})"[:31], [lib] + ent, [[g["nom"]] + vals(g[s]) for g in lst if g[s]["ecoles"]],
                                     {"titre_haut": haut}))
                f("Écoles et classes", ["Écoles primaires", "Écoles maternelles", "Espaces enfance", "Total écoles", "Fiches reçues",
                                        "Classes / sections autorisées", "Ouvertes", "Taux d'ouverture (%)", "Salles existantes",
                                        "Salles utilisées"],
                  lambda x: [x["EP"], x["EM"], x["EE"], x["ecoles"], x["fiches"], x["aut"], x["ouv"], x["taux_ouv"], x["s_exist"], x["s_util"]])
                f("Structure", [l_ for _k, l_ in STRUCT] + ["Total", "% jumelées", "% multigrades"],
                  lambda x: [x["struct"][k] for k, _ in STRUCT] + [x["struct_tot"], x["p_jum"], x["p_multi"]])
                f("Moyennes et écarts types", [f"{l_} – {c}" for _k, l_ in STATS for c in ("moyenne", "écart type", "min", "max", "écoles/classes")],
                  lambda x: [x["stats"][k][c] for k, _ in STATS for c in ("moy", "et", "min", "max", "n")])
                f("Équipements", [f"{l_} – oui" for _k, l_ in EQUIP] + [f"{l_} – %" for _k, l_ in EQUIP]
                  + [f"Eau : {l_}" for _k, l_ in EAU] + [f"Électricité : {l_}" for _k, l_ in ELEC],
                  lambda x: [x["equip"][k][0] for k, _ in EQUIP] + [x["p_equip"][k] for k, _ in EQUIP]
                  + [x["eau_src"][k] for k, _ in EAU] + [x["elec_src"][k] for k, _ in ELEC])
            H.journal("jur_ecoles_struct", f"{flt['annee']} {source} xlsx")
            return H.xlsx.reponse_classeur(f"ecoles_structure_{source}_{flt['annee']}_par_{par}.xlsx", feuilles)
        return render_template("jur_ecoles_struct.html", flt=flt, par=par, lib=lib, grp=grp, tot=tot, source=source,
                               SOURCES=SOURCES, STRUCT=STRUCT, EAU=EAU, ELEC=ELEC, EQUIP=EQUIP, STATS=STATS, courbes=courbes,
                               args=T.args_filtres(flt, par=par, source=source), args0=T.args_filtres(flt, source=source),
                               args1=T.args_filtres(flt, par=par))
