# -*- coding: utf-8 -*-
"""v1.10.5 — Module « Infrastructures et mobilier » des applications Circonscription scolaire et DDEMP.

Une page (/juridiction/infrastructures) qui consolide, d'après les fiches transmises par les écoles :
  * la FICHE DE RECENSEMENT (primaire : 3.3 à 3.15, 4 « Locaux », 5 « Mobilier », 6.3 « Manuels » ;
    maternelle : renseignements généraux, 8 « Infrastructures », 9 « Mobilier ») ;
  * le RAPPORT DE RENTRÉE et la FICHE DE FIN D'ANNÉE (infrastructures, mobilier, manuels) ;
au choix de la source, par circonscription (DDEMP), par zone pédagogique ou par école :
  1. salles de classe : matériaux définitifs (bon / mauvais état), mixtes, provisoires, sans mur ni toit, en construction ;
     salles existantes et utilisées, élèves par salle, part des salles en matériaux définitifs et en mauvais état ;
  2. commodités : point d'eau potable, électricité, latrines (blocs, cabines), dispositif de lavage des mains, clôture ;
  3. mobilier du primaire : tables + chaises, table-bancs à 2 places, à 3 places et plus, bureaux du maître, tableaux ;
     PLACES ASSISES, DÉFICIT de places, élèves par place ;
  4. mobilier de la maternelle : tables et chaises pour enfants, tabourets, nattes, tables de jeux, bureaux, armoires ;
  5. manuels du primaire (français, mathématiques) : nombre et manuels par élève.
Le secteur public et le secteur privé sont toujours présentés à part. Une courbe par tableau ; export Excel.
"""
from flask import abort, render_template, request

import config
import m_juridiction as J

SOURCES = {"recensement": "Fiche de recensement", "rentree": "Rapport de rentrée", "fin": "Fiche de fin d'année"}
_DOCS = {"rentree": {"EP": "rentree-ep", "EM": "rentree-em"}, "fin": {"EP": "fin-ep", "EM": "fin-em"}}
NIV_EP = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]

SALLES = [("def_b", "Définitifs – bon état"), ("def_m", "Définitifs – mauvais état"),
          ("def_n", "Définitifs – état non précisé"), ("mix", "Murs provisoires, toit définitif"),
          ("prov", "Provisoires"), ("sans", "Sans mur ni toit"), ("cons", "En construction")]
COMMODITES = [("eau", "Point d'eau potable"), ("elec", "Électricité"), ("latrines", "Latrines fonctionnelles"),
              ("lavage", "Lavage des mains"), ("cloture", "Clôture")]
MOB_EP = [("t1", "Tables + chaises (1 place)"), ("t2", "Table-bancs 2 places"), ("t3", "Table-bancs 3 places et +"),
          ("bureau", "Bureaux du maître"), ("tableau", "Tableaux"), ("armoire", "Armoires / placards"),
          ("adapt", "Mobilier adapté")]
MOB_EM = [("tables_enf", "Tables pour enfants"), ("chaises_enf", "Chaises pour enfants"), ("tabourets", "Tabourets"),
          ("nattes", "Nattes"), ("tables_jeux", "Tables de jeux"), ("bureaux", "Bureaux enseignant"),
          ("chaises_ens", "Chaises enseignant"), ("armoires", "Armoires / placards"), ("tableaux", "Tableaux"),
          ("mauvais", "dont en mauvais état")]
MANUELS = [("fr", "Manuels de français"), ("ma", "Manuels de mathématiques")]
PALETTE = ["#2a78d6", "#eb6834", "#1b7f3b", "#8e44ad", "#c99a06", "#d6336c", "#0f766e", "#64748b"]


# ======================================================================== lecture des fiches
def n(v):
    try:
        return max(0, int(round(float(str(v).replace(",", ".").replace(" ", "").replace(" ", "")))))
    except (TypeError, ValueError):
        return 0


def coche(v):
    return str(v or "").strip().lower() in ("1", "x", "oui", "o", "true", "vrai", "on")


def oui_non(v):
    """« Oui » → True, « Non » → False, vide → None."""
    s = str(v or "").strip().lower()
    if s in ("oui", "o", "1", "true", "x"):
        return True
    if s in ("non", "n", "0", "false"):
        return False
    return None


def vide_ecole():
    return {"salles": {k: 0 for k, _ in SALLES}, "exist": 0, "util": 0, "com": {k: None for k, _ in COMMODITES},
            "lat_blocs": 0, "lat_cabines": 0, "mob_ep": {k: 0 for k, _ in MOB_EP}, "mob_em": {k: 0 for k, _ in MOB_EM},
            "man": {k: 0 for k, _ in MANUELS}, "fiche": False}


def _rec_primaire(val, d):
    for i in range(1, 13):
        r = {k[len(f"t4.s{i}."):]: v for k, v in val.items() if k.startswith(f"t4.s{i}.")}
        if not any(str(v).strip() not in ("", "0") for v in r.values()):
            continue
        if coche(r.get("m_sans")) or coche(r.get("t_sans")):
            d["salles"]["sans"] += 1
            continue
        toit_def = coche(r.get("t_toles")) or coche(r.get("t_tuiles"))
        if coche(r.get("m_dur")) and (toit_def or not any(coche(r.get(t)) for t in ("t_banco", "t_paille"))):
            mauv = coche(r.get("em_mauv")) or coche(r.get("et_mauv"))
            bon = coche(r.get("em_bon")) or coche(r.get("et_bon"))
            d["salles"]["def_m" if mauv else ("def_b" if bon else "def_n")] += 1
        elif toit_def:
            d["salles"]["mix"] += 1
        else:
            d["salles"]["prov"] += 1
    lignes_mob = [f"s{i}" for i in range(1, 13)] + ["magasin", "bureau", "biblio", "info"]
    for k_src, k in (("t1", "t1"), ("t2", "t2"), ("t3", "t3"), ("bureau", "bureau"), ("tableau", "tableau"),
                     ("armoire", "armoire"), ("adapt", "adapt")):
        d["mob_ep"][k] += sum(n(val.get(f"t5.{r}.{k_src}")) for r in lignes_mob)
    for m_, _l in MANUELS:
        d["man"][m_] += sum(n(val.get(f"t631.{m_}.{x.lower()}")) for x in NIV_EP)
    d["lat_blocs"] += n(val.get("latrines_blocs"))
    d["lat_cabines"] += n(val.get("latrines_cabines"))
    d["com"].update({"eau": oui_non(val.get("point_eau")), "elec": oui_non(val.get("electricite")),
                     "latrines": oui_non(val.get("latrines")), "lavage": oui_non(val.get("lavage_mains")),
                     "cloture": oui_non(val.get("cloture"))})


def _rec_maternelle(val, d):
    g = lambda c: n(val.get(f"t8.salle.{c}"))  # noqa: E731
    d["salles"]["def_b"] += g("def_b")
    d["salles"]["def_m"] += g("def_m")
    d["salles"]["mix"] += g("mix_b") + g("mix_m")
    d["salles"]["prov"] += g("prov") + g("apatam")
    d["salles"]["sans"] += g("sans")
    d["salles"]["cons"] += g("cours")
    for k_src, k in (("tables_enf", "tables_enf"), ("chaises_enf", "chaises_enf"), ("tabourets", "tabourets"),
                     ("nattes", "nattes"), ("tables_jeux", "tables_jeux"), ("bureaux", "bureaux"),
                     ("chaises_ens", "chaises_ens"), ("armoires", "armoires")):
        d["mob_em"][k] += n(val.get(f"t9.bon.{k_src}")) + n(val.get(f"t9.mauv.{k_src}"))
    d["mob_em"]["tableaux"] += sum(n(val.get(f"t9.{e}.{c}")) for e in ("bon", "mauv") for c in ("tab_chevalet", "tab_muraux"))
    d["mob_em"]["mauvais"] += sum(n(v) for k, v in val.items() if k.startswith("t9.mauv."))
    d["lat_blocs"] += n(val.get("latrines_modules"))
    d["lat_cabines"] += n(val.get("latrines_isoloirs"))
    d["com"].update({"eau": oui_non(val.get("eau")), "elec": oui_non(val.get("electricite")),
                     "latrines": oui_non(val.get("latrines")), "lavage": oui_non(val.get("lavage")),
                     "cloture": oui_non(val.get("cloture"))})


def _rapport(val, d, em):
    d["salles"]["def_n"] += n(val.get("infra.salles.def"))
    d["salles"]["prov"] += n(val.get("infra.salles.prov"))
    d["salles"]["sans"] += n(val.get("infra.salles.sans"))
    d["salles"]["cons"] += n(val.get("infra.salles.cons"))
    if em:
        for k_src, k in (("bur_ens", "bureaux"), ("ch_ens", "chaises_ens"), ("armoires", "armoires"),
                         ("tables_jeux", "tables_jeux"), ("ch_enf", "chaises_enf"), ("tables_enf", "tables_enf"),
                         ("nattes", "nattes")):
            d["mob_em"][k] += n(val.get(f"mob.nb.{k_src}"))
        d["mob_em"]["tableaux"] += n(val.get("int.nb.chevalet")) + n(val.get("int.nb.muraux"))
    else:
        for k_src, k in (("table_chaise", "t1"), ("tb2", "t2"), ("tb3", "t3"), ("bureau", "bureau")):
            d["mob_ep"][k] += sum(n(val.get(f"mob.{k_src}.{x}")) for x in NIV_EP)
        for k_src, k in (("fr", "fr"), ("math", "ma")):
            d["man"][k] += sum(n(val.get(f"man.{k_src}.{x}")) for x in NIV_EP)
    d["com"]["lavage"] = oui_non(val.get("lavage"))


def lire_ecole(l, source):
    """Infrastructures et mobilier d'une école (ligne de a_tableau.donnees + « _rap ») pour la source choisie."""
    d = vide_ecole()
    em = l.get("type") in ("EM", "EE")
    if source == "recensement":
        val = (((l.get("_rec") or {}).get("maternelle" if em else "primaire") or {}).get("valeurs") or {})
        if val:
            (_rec_maternelle if em else _rec_primaire)(val, d)
    else:
        doc = _DOCS[source]["EM" if em else "EP"]
        val = (((l.get("_rap") or {}).get(doc) or {}).get("valeurs") or {})
        if val:
            _rapport(val, d, em)
    if val:
        d["fiche"] = True
        d["exist"] = n(val.get("salles_existantes"))
        d["util"] = n(val.get("salles_utilisees"))
    return d


# ======================================================================== agrégation
def nouveau():
    return {"ecoles": 0, "ep": 0, "em": 0, "fiches": 0, "eleves_ep": 0, "eleves_em": 0, "eleves": 0,
            "salles": {k: 0 for k, _ in SALLES}, "exist": 0, "util": 0,
            "com": {k: [0, 0] for k, _ in COMMODITES},          # [oui, renseigné]
            "lat_blocs": 0, "lat_cabines": 0, "mob_ep": {k: 0 for k, _ in MOB_EP}, "mob_em": {k: 0 for k, _ in MOB_EM},
            "man": {k: 0 for k, _ in MANUELS}}


def cumuler(x, d, l):
    em = l.get("type") in ("EM", "EE")
    x["ecoles"] += 1
    x["em" if em else "ep"] += 1
    if not d["fiche"]:
        return
    x["fiches"] += 1
    t = n((l.get("eff") or {}).get("t"))
    x["eleves_em" if em else "eleves_ep"] += t
    x["eleves"] += t
    for k in x["salles"]:
        x["salles"][k] += d["salles"][k]
    for k in ("exist", "util", "lat_blocs", "lat_cabines"):
        x[k] += d[k]
    for k, v in d["com"].items():
        if v is not None:
            x["com"][k][1] += 1
            x["com"][k][0] += 1 if v else 0
    for k in ("mob_ep", "mob_em", "man"):
        for kk in x[k]:
            x[k][kk] += d[k][kk]


def _ratio(a, b, dec=1):
    return round(a / b, dec) if b else None


def indicateurs(x):
    """Indicateurs dérivés d'un agrégat (en place) : total des salles, parts, places assises, déficit, ratios."""
    s = x["salles"]
    tot = sum(s.values()) - s["cons"]
    deff = s["def_b"] + s["def_m"] + s["def_n"]
    x["salles_tot"] = tot
    x["p_def"] = _ratio(100.0 * deff, tot)
    x["p_mauv"] = _ratio(100.0 * (s["def_m"] + s["prov"] + s["sans"]), tot)
    x["el_salle"] = _ratio(x["eleves"], x["util"] or tot)
    m = x["mob_ep"]
    x["places_ep"] = m["t1"] + 2 * m["t2"] + 3 * m["t3"]
    x["deficit_ep"] = max(0, x["eleves_ep"] - x["places_ep"]) if x["places_ep"] or x["eleves_ep"] else 0
    x["el_place_ep"] = _ratio(x["eleves_ep"], x["places_ep"], 2)
    e = x["mob_em"]
    x["places_em"] = e["chaises_enf"] + e["tabourets"]
    x["deficit_em"] = max(0, x["eleves_em"] - x["places_em"]) if x["places_em"] or x["eleves_em"] else 0
    x["el_place_em"] = _ratio(x["eleves_em"], x["places_em"], 2)
    x["man_el"] = {k: _ratio(x["man"][k], x["eleves_ep"], 2) for k, _ in MANUELS}
    x["p_com"] = {k: _ratio(100.0 * v[0], v[1]) for k, v in x["com"].items()}
    return x


def calculer(lignes, source, par):
    """Renvoie (groupes, total) ; chaque élément porte « pub » et « prv » (secteur privé à part)."""
    def cle_nom(l):
        if par == "cs":
            return l["cs_id"], l["cs_nom"] or "Sans circonscription"
        if par == "ecole":
            return l["id"], l["nom"]
        return l["zone_id"], l["zone_nom"] or "Sans zone pédagogique"

    grp = {}
    tot = {"nom": "Total", "pub": nouveau(), "prv": nouveau()}
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

    def garde():
        if not config.juridiction():
            abort(404)

    @app.route("/juridiction/infrastructures")
    @H.connexion_requise()
    def jur_infra():
        garde()
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
                "salles": E.svg_courbes(noms, [("Définitifs", PALETTE[2], [g[s]["salles"]["def_b"] + g[s]["salles"]["def_m"] + g[s]["salles"]["def_n"] for g in grp]),
                                               ("Provisoires / mixtes", PALETTE[1], [g[s]["salles"]["prov"] + g[s]["salles"]["mix"] for g in grp]),
                                               ("Sans mur ni toit", PALETTE[5], [g[s]["salles"]["sans"] for g in grp]),
                                               ("Élèves par salle", PALETTE[0], [g[s]["el_salle"] for g in grp])], "Salles de classe"),
                "com": E.svg_courbes(noms, [(l_, PALETTE[i], [g[s]["p_com"][k] for g in grp]) for i, (k, l_) in enumerate(COMMODITES)],
                                     "Commodités (% des écoles)"),
                "places": E.svg_courbes(noms, [("Élèves du primaire", PALETTE[0], [g[s]["eleves_ep"] for g in grp]),
                                               ("Places assises", PALETTE[2], [g[s]["places_ep"] for g in grp]),
                                               ("Déficit de places", PALETTE[5], [g[s]["deficit_ep"] for g in grp])], "Places assises (primaire)"),
                "mat": E.svg_courbes(noms, [("Enfants", PALETTE[0], [g[s]["eleves_em"] for g in grp]),
                                            ("Chaises + tabourets", PALETTE[2], [g[s]["places_em"] for g in grp]),
                                            ("Tables pour enfants", PALETTE[4], [g[s]["mob_em"]["tables_enf"] for g in grp])], "Mobilier (maternelle)"),
                "man": E.svg_courbes(noms, [(l_ + " par élève", PALETTE[i], [g[s]["man_el"][k] for g in grp]) for i, (k, l_) in enumerate(MANUELS)],
                                     "Manuels par élève"),
            }
        if request.args.get("export") == "xlsx":
            haut = [config.ECOLE.get("nom", ""), f"Infrastructures et mobilier – {SOURCES[source]} – année {flt['annee']} – par {lib.lower()}"]
            feuilles = []
            for s, sl in (("pub", "public"), ("prv", "privé")):
                lst = grp + [tot]

                def f(nom, ent, vals):
                    feuilles.append((f"{nom} ({sl})"[:31], [lib, "Écoles", "Fiches"] + ent,
                                     [[g["nom"], g[s]["ecoles"], g[s]["fiches"]] + vals(g[s]) for g in lst], {"titre_haut": haut}))
                f("Salles", [l_ for _k, l_ in SALLES] + ["Total (hors construction)", "Existantes", "Utilisées", "% définitifs",
                                                        "% mauvais état ou précaires", "Élèves", "Élèves par salle"],
                  lambda x: [x["salles"][k] for k, _ in SALLES] + [x["salles_tot"], x["exist"], x["util"], x["p_def"], x["p_mauv"],
                                                                   x["eleves"], x["el_salle"]])
                f("Commodités", [f"{l_} – oui" for _k, l_ in COMMODITES] + [f"{l_} – %" for _k, l_ in COMMODITES]
                  + ["Blocs / modules de latrines", "Cabines / isoloirs"],
                  lambda x: [x["com"][k][0] for k, _ in COMMODITES] + [x["p_com"][k] for k, _ in COMMODITES]
                  + [x["lat_blocs"], x["lat_cabines"]])
                f("Mobilier EP", [l_ for _k, l_ in MOB_EP] + ["Places assises", "Élèves", "Déficit de places", "Élèves par place"],
                  lambda x: [x["mob_ep"][k] for k, _ in MOB_EP] + [x["places_ep"], x["eleves_ep"], x["deficit_ep"], x["el_place_ep"]])
                f("Mobilier EM", [l_ for _k, l_ in MOB_EM] + ["Places (chaises + tabourets)", "Enfants", "Déficit", "Enfants par place"],
                  lambda x: [x["mob_em"][k] for k, _ in MOB_EM] + [x["places_em"], x["eleves_em"], x["deficit_em"], x["el_place_em"]])
                f("Manuels", [l_ for _k, l_ in MANUELS] + ["Élèves du primaire"] + [f"{l_} par élève" for _k, l_ in MANUELS],
                  lambda x: [x["man"][k] for k, _ in MANUELS] + [x["eleves_ep"]] + [x["man_el"][k] for k, _ in MANUELS])
            H.journal("jur_infra", f"{flt['annee']} {source} xlsx")
            return H.xlsx.reponse_classeur(f"infrastructures_{source}_{flt['annee']}_par_{par}.xlsx", feuilles)
        return render_template("jur_infra.html", flt=flt, par=par, lib=lib, grp=grp, tot=tot, source=source,
                               SOURCES=SOURCES, SALLES=SALLES, COMMODITES=COMMODITES, MOB_EP=MOB_EP, MOB_EM=MOB_EM,
                               MANUELS=MANUELS, courbes=courbes, args=T.args_filtres(flt, par=par, source=source),
                               args0=T.args_filtres(flt, source=source), args1=T.args_filtres(flt, par=par))
