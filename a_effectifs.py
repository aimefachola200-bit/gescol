# -*- coding: utf-8 -*-
"""v1.10 — Module « Effectifs » des applications Circonscription scolaire et DDEMP.

Une seule page (/juridiction/effectifs) qui rassemble, par sexe, d'après les fiches et paquets transmis par les écoles
(effectifs de la fiche de recensement, personnel de l'état nominatif) :
  1. les apprenants : primaire (EP) et maternelle (EM, espaces enfance), garçons / filles ;
  2. le personnel enseignant : enseignants (adjoints compris) et directeurs, hommes / femmes ;
  3. les catégories : FE, ACDPE, ACDPCTD (AME), Éducateur, Privé, Autre ;
  4. les diplômes professionnels : CAP (EP, EM) et CEAP (EP, EM) ;
  5. les diplômes académiques et universitaires (CEP … Doctorat) ;
  6. le SECTEUR PRIVÉ À PART : écoles, apprenants, enseignants, directeurs, CAP / CEAP des écoles privées ;
  7. (v1.10.3) les CATÉGORIES D'ÂGE des apprenants du primaire, de « moins de 5 ans » à « 16 ans et plus » (tableau
     7.3 de la fiche de recensement), par sexe et par cours (CI … CM2), avec pourcentages, âge moyen et écart type ;
     secteur public, et secteur privé à part ;
  8. (v1.10.4) les ÉCOLES MATERNELLES PAR SECTION (section des petits SP, section des grands SG), par sexe : tableau 3
     de la fiche de recensement (catégories d'âge « moins de 2 ans ½ » … « plus de 5 ans », pourcentages, âge moyen,
     écart type), rapport de rentrée EM (effectif de début d'année, enfants à besoin spécifique) et fiche de fin
     d'année EM (début, fin, besoin spécifique, abandons) ; secteur public, et secteur privé à part.
Les rubriques 1 à 5 ne comptent que le secteur public.
Chaque tableau est ventilé par circonscription (DDEMP), par zone pédagogique (CS ou CS choisie à la DDEMP) ou par
école (au choix), avec une COURBE par tableau ; export Excel. La page est rattachée aux divisions chargées des
statistiques (CDOSP / DOSP, statistiques) et des ressources humaines (RH / SRH) — voir a_divisions.
"""
import math
import unicodedata

from flask import abort, render_template, request
from markupsafe import Markup, escape

import config
import m_juridiction as J

CATS = [("FE", "FE"), ("ACDPE", "ACDPE"), ("ACDPCTD", "ACDPCTD (AME)"), ("EDUCATEUR", "Éducateur"),
        ("PRIVE", "Privé"), ("AUTRE", "Autre")]
DIPLOMES = [("cap_ep", "CAP – EP"), ("cap_em", "CAP – EM"), ("ceap_ep", "CEAP – EP"), ("ceap_em", "CEAP – EM")]
# diplômes académiques et universitaires (diplôme le plus élevé déclaré sur la fiche de l'agent)
ACADEMIQUES = [("cep", "CEP"), ("bepc", "BEPC"), ("bac", "BAC"), ("bac2", "BAC + 2 (DEUG, DUT, BTS)"),
               ("licence", "Licence"), ("maitrise", "Maîtrise"), ("master", "Master / DEA / DESS"),
               ("doctorat", "Doctorat"), ("autre", "Autre"), ("nr", "Non renseigné")]
PRIVE = [("ens", "Enseignants"), ("dir", "Directeurs"), ("ep", "Personnel EP"), ("em", "Personnel EM"),
         ("cap", "CAP"), ("ceap", "CEAP")]
PALETTE = ["#2a78d6", "#eb6834", "#1b7f3b", "#8e44ad", "#c99a06", "#d6336c", "#0f766e", "#64748b"]


def _sans_accent(s):
    return unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()


def categorie(p):
    """Catégorie du personnel : FE, ACDPE, ACDPCTD (AME), Éducateur, Privé, Autre."""
    c = str(p.get("categorie") or "").upper().replace("-", "").replace(" ", "")
    if c.startswith("ACDPCTD") or c == "AME":
        return "ACDPCTD"
    if c in ("FE", "ACDPE", "PRIVE"):
        return c
    if c.startswith("EDUC") or "educat" in _sans_accent(p.get("fonction")):
        return "EDUCATEUR"
    return "AUTRE"


def diplome_academique(v):
    """Libellé libre (« Licence en sociologie », « BAC D », « Maîtrise »…) → clé de ACADEMIQUES."""
    d = _sans_accent(v).replace(".", "").replace("-", " ")
    if not d.strip():
        return "nr"
    for cle, motifs in (("doctorat", ("doctorat", "phd", "doctor")), ("master", ("master", "dea", "dess", "mba")),
                        ("maitrise", ("maitrise",)), ("licence", ("licence", "license", "bachelor")),
                        ("bac2", ("deug", "dut", "bts", "duel", "bac + 2", "bac+2", "bac 2", "dues")),
                        ("bac", ("bac", "baccalaureat")), ("bepc", ("bepc", "brevet")), ("cep", ("cep",))):
        if any(m in d for m in motifs):
            return cle
    return "autre"


def oui(v):
    return v is True or str(v or "").strip().lower() in ("1", "oui", "true", "o", "x", "yes")


def sexe(p):
    s = str(p.get("sexe") or "").strip().upper()[:1]
    return "h" if s in ("M", "H", "G") else ("f" if s == "F" else None)


def vide_hf():
    return {"h": 0, "f": 0, "t": 0}


def ajouter(d, sx):
    d["t"] += 1
    if sx:
        d[sx] += 1


def nouveau_groupe(nom):
    """Rubriques 1 à 5 : secteur PUBLIC seulement ; le secteur privé est compté à part (rubrique 6, « prive »)."""
    return {"nom": nom, "ecoles": 0,
            "app": {"ep": {"g": 0, "f": 0, "t": 0}, "em": {"g": 0, "f": 0, "t": 0}, "t": {"g": 0, "f": 0, "t": 0}},
            "ens": vide_hf(), "dir": vide_hf(), "tous": vide_hf(),
            "cat": {k: vide_hf() for k, _ in CATS}, "dip": {k: vide_hf() for k, _ in DIPLOMES},
            "aca": {k: vide_hf() for k, _ in ACADEMIQUES}, "ages": nouvelle_repartition(), "mat": nouveau_mat(),
            "prive": {"ecoles": 0, "app": {"ep": {"g": 0, "f": 0, "t": 0}, "em": {"g": 0, "f": 0, "t": 0},
                                           "t": {"g": 0, "f": 0, "t": 0}},
                      "cap": vide_hf(), "ceap": vide_hf(), "ages": nouvelle_repartition(), "mat": nouveau_mat(),
                      **{k: vide_hf() for k, _ in PRIVE}}}


def calculer(lignes, personnel, par):
    """lignes : écoles (a_tableau.donnees) ; personnel : J.personnel(...). Renvoie (groupes, total).
    Les écoles privées et leur personnel ne sont comptés QUE dans la rubrique « prive » (secteur privé à part)."""
    def cle_nom(l):
        if par == "cs":
            return l["cs_id"], l["cs_nom"] or "Sans circonscription"
        if par == "ecole":
            return l["id"], l["nom"]
        return l["zone_id"], l["zone_nom"] or "Sans zone pédagogique"

    grp, de_ecole = {}, {}
    tot = nouveau_groupe("Total")
    for l in lignes:
        k, nom = cle_nom(l)
        g = grp.setdefault(k, nouveau_groupe(nom))
        prive = l.get("secteur") == "prive"
        de_ecole[l["id"]] = (g, l["type"], prive)
        em = l["type"] in ("EM", "EE")
        e = l.get("eff") or {}
        rep = ages_ecole(l) if l.get("type") == "EP" else None
        mat = mat_ecole(l) if em else None
        for x in (g, tot):
            cible = x["prive"] if prive else x
            cible["ecoles"] += 1
            for niv in ("em" if em else "ep", "t"):
                for s_ in ("g", "f", "t"):
                    cible["app"][niv][s_] += int(e.get(s_) or 0)
            if rep:
                cumuler(cible["ages"], rep)
            if mat:
                cumuler_mat(cible["mat"], mat)
    for p in personnel:
        if p.get("actif") is False:
            continue
        g_t = de_ecole.get(p.get("ecole_id"))
        if not g_t:
            continue
        g, typ, prive = g_t
        role = p.get("role") or ""
        if role not in ("enseignant", "adjoint", "directeur"):
            continue
        sx = sexe(p)
        em = (p.get("ecole_type") or typ) in ("EM", "EE")
        for x in (g, tot):
            if prive:
                pv = x["prive"]
                ajouter(pv["dir" if role == "directeur" else "ens"], sx)
                ajouter(pv["em" if em else "ep"], sx)
                if oui(p.get("cap")):
                    ajouter(pv["cap"], sx)
                if oui(p.get("ceap")):
                    ajouter(pv["ceap"], sx)
                continue
            ajouter(x["dir" if role == "directeur" else "ens"], sx)
            ajouter(x["tous"], sx)
            ajouter(x["cat"][categorie(p)], sx)
            if oui(p.get("cap")):
                t_cap = str(p.get("type_cap") or "").upper()
                ajouter(x["dip"]["cap_em" if (t_cap == "EM" or (not t_cap and em)) else "cap_ep"], sx)
            if oui(p.get("ceap")):
                ajouter(x["dip"]["ceap_em" if em else "ceap_ep"], sx)
            ajouter(x["aca"][diplome_academique(p.get("diplome_academique"))], sx)
    return list(grp.values()), tot


# ======================================================================== 7. catégories d'âge (primaire)
COURS = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
# (clé, libellé, âge retenu pour l'âge moyen et l'écart type : 4 ans pour « moins de 5 ans », 16 pour « 16 et plus »)
AGES = [("m5", "Moins de 5 ans", 4)] + [(f"a{i}", f"{i} ans", i) for i in range(5, 16)] + [("a16", "16 ans et plus", 16)]


def cle_age(a):
    return "m5" if a < 5 else ("a16" if a >= 16 else f"a{a}")


def _ent(v):
    try:
        return max(0, int(round(float(str(v).replace(",", ".").replace(" ", "")))))
    except (TypeError, ValueError):
        return 0


def _cours(n):
    nn = _sans_accent(n).upper().replace(" ", "")
    return nn if nn in COURS else None


def ages_ecole(l):
    """Répartition âge × cours × sexe d'une école primaire : {cle_age: {cours: [g, f]}}.
    Source : les âges des élèves (section effectifs, âge au 31 décembre) ; à défaut, le tableau 7.3 de la fiche de
    recensement (t73.<âge>.<cours>_g / _f)."""
    d = {k: {c: [0, 0] for c in COURS} for k, _l, _a in AGES}
    vu = False
    for niv, dist in ((l.get("_sec_eff") or {}).get("ages") or {}).items():
        c = _cours(niv)
        if not c or not isinstance(dist, dict):
            continue
        for age, gf in dist.items():
            try:
                a = int(float(age))
            except (TypeError, ValueError):
                continue
            if isinstance(gf, (list, tuple)) and len(gf) >= 2:
                d[cle_age(a)][c][0] += _ent(gf[0])
                d[cle_age(a)][c][1] += _ent(gf[1])
                vu = vu or bool(_ent(gf[0]) or _ent(gf[1]))
    if not vu:
        val = (((l.get("_rec") or {}).get("primaire") or {}).get("valeurs") or {})
        for k, _l, _a in AGES:
            kr = "a4" if k == "m5" else k                       # « moins de 5 ans » = ligne a4 de la fiche
            for c in COURS:
                d[k][c][0] += _ent(val.get(f"t73.{kr}.{c.lower()}_g"))
                d[k][c][1] += _ent(val.get(f"t73.{kr}.{c.lower()}_f"))
    return d


def nouvelle_repartition(cols=None, ages=None):
    return {k: {c: [0, 0] for c in (cols or COURS)} for k, _l, _a in (ages or AGES)}


def cumuler(dest, d):
    for k in dest:
        for c in dest[k]:
            dest[k][c][0] += d[k][c][0]
            dest[k][c][1] += d[k][c][1]


def moyenne_ecart(effectifs):
    """effectifs : [(âge, nombre)] → (moyenne, écart type de la population) ; (None, None) si vide."""
    n = sum(x for _a, x in effectifs)
    if not n:
        return None, None
    m = sum(a * x for a, x in effectifs) / n
    v = sum(x * (a - m) ** 2 for a, x in effectifs) / n
    return round(m, 2), round(math.sqrt(v), 2)


def tableau_ages(rep, cours=None, ages=None):
    """Tableau final : lignes par catégorie d'âge, colonnes par cours (ou section) puis ENSEMBLE, chaque fois G / F / T
    avec le pourcentage de la colonne ; lignes Total, Âge moyen, Écart type."""
    cours = cours or COURS
    AGES = ages or globals()["AGES"]
    cols = cours + ["ENS"]

    def val(k, c, i):           # i : 0 = G, 1 = F, 2 = T
        cs = cours if c == "ENS" else [c]
        g = sum(rep[k][x][0] for x in cs)
        f = sum(rep[k][x][1] for x in cs)
        return (g, f, g + f)[i]

    tot = {c: [sum(val(k, c, i) for k, _l, _a in AGES) for i in range(3)] for c in cols}
    lignes = []
    for k, lib, _a in AGES:
        cells = {c: [(val(k, c, i), round(100.0 * val(k, c, i) / tot[c][i], 1) if tot[c][i] else None)
                     for i in range(3)] for c in cols}
        lignes.append({"cle": k, "lib": lib, "cells": cells})
    stats = {c: [moyenne_ecart([(a, val(k, c, i)) for k, _l, a in AGES]) for i in range(3)] for c in cols}
    return {"cols": cols, "lignes": lignes, "tot": tot, "stats": stats, "vide": not tot["ENS"][2]}


# ======================================================================== 8. maternelles par section (SP / SG)
SECTIONS = [("SP", "Section des petits"), ("SG", "Section des grands")]
SECS = [k for k, _ in SECTIONS]
# tableau 3 de la fiche de recensement des écoles maternelles (âge retenu pour la moyenne et l'écart type)
AGES_M = [("m25", "Moins de 2 ans ½", 2.0), ("a25", "2 ans ½ à 3 ans", 2.75), ("a3", "3 ans", 3.0), ("a4", "4 ans", 4.0),
          ("a5", "5 ans", 5.0), ("p5", "Plus de 5 ans", 6.0)]
NOTE_AGES_M = ("Tableau 3 de la fiche de recensement ; âge moyen et écart type : « moins de 2 ans ½ » compté 2 ans, "
               "« 2 ans ½ à 3 ans » 2,75 ans, « plus de 5 ans » 6 ans")
_SEC_FICHE = {"SP": "pe", "SG": "gr"}          # colonnes du tableau 3 (recensement)
_SEC_RAP = {"SP": "pet", "SG": "gra"}          # colonnes du tableau « Répartition des enfants par section » (rapports)
# lignes des rapports de rentrée et de fin d'année des écoles maternelles
LIGNES_RENTREE = [("debut", "Effectif au début de l'année"), ("besoin", "Dont enfants à besoin spécifique")]
LIGNES_FIN = [("debut", "Effectif au début de l'année"), ("fin", "Effectif en fin d'année"),
              ("besoin", "Dont enfants à besoin spécifique"), ("aband", "Abandons")]


def cle_age_m(a):
    """Âge en années révolues (au 31 décembre) → ligne du tableau 3 (« 2 ans » est compté « 2 ans ½ à 3 ans »)."""
    return "m25" if a < 2 else ("p5" if a > 5 else ("a25" if a == 2 else f"a{a}"))


def section_de(niveau):
    n = _sans_accent(niveau).upper().replace(" ", "")
    if n in ("MATERNELLE1", "SP", "PS", "MS", "PETITS", "SECTIONDESPETITS"):
        return "SP"
    if n in ("MATERNELLE2", "SG", "GS", "GRANDS", "SECTIONDESGRANDS"):
        return "SG"
    return None


def nouveau_mat():
    return {"ecoles": 0, "ages": nouvelle_repartition(SECS, AGES_M), "rec": {c: [0, 0] for c in SECS},
            "rentree": {k: {c: [0, 0] for c in SECS} for k, _ in LIGNES_RENTREE},
            "fin": {k: {c: [0, 0] for c in SECS} for k, _ in LIGNES_FIN}, "n_rec": 0, "n_rentree": 0, "n_fin": 0}


def mat_ecole(l):
    """Une école maternelle : âges par section (âges des enfants, sinon tableau 3 de la fiche), effectif du
    recensement par section (somme des âges, sinon classes), rapports de rentrée et de fin d'année."""
    m = nouveau_mat()
    m["ecoles"] = 1
    sec = l.get("_sec_eff") or {}
    vu = False
    for niv, dist in (sec.get("ages") or {}).items():
        c = section_de(niv)
        if not c or not isinstance(dist, dict):
            continue
        for age, gf in dist.items():
            try:
                a = int(float(age))
            except (TypeError, ValueError):
                continue
            if isinstance(gf, (list, tuple)) and len(gf) >= 2:
                m["ages"][cle_age_m(a)][c][0] += _ent(gf[0])
                m["ages"][cle_age_m(a)][c][1] += _ent(gf[1])
                vu = vu or bool(_ent(gf[0]) or _ent(gf[1]))
    if not vu:
        val = (((l.get("_rec") or {}).get("maternelle") or {}).get("valeurs") or {})
        for k, _l, _a in AGES_M:
            for c in SECS:
                m["ages"][k][c][0] += _ent(val.get(f"t3.{k}.{_SEC_FICHE[c]}_g"))
                m["ages"][k][c][1] += _ent(val.get(f"t3.{k}.{_SEC_FICHE[c]}_f"))
    for c in SECS:
        for i in (0, 1):
            m["rec"][c][i] = sum(m["ages"][k][c][i] for k, _l, _a in AGES_M)
    if not any(sum(v) for v in m["rec"].values()):
        for cl in sec.get("classes") or []:
            c = section_de(cl.get("niveau"))
            if c:
                m["rec"][c][0] += _ent(cl.get("garcons"))
                m["rec"][c][1] += _ent(cl.get("filles"))
    m["n_rec"] = 1 if any(sum(v) for v in m["rec"].values()) else 0
    rap = l.get("_rap") or {}
    for doc, cle, lignes_ in (("rentree-em", "rentree", LIGNES_RENTREE), ("fin-em", "fin", LIGNES_FIN)):
        val = ((rap.get(doc) or {}).get("valeurs") or {})
        n = 0
        for k, _l in lignes_:
            for c in SECS:
                g, f = _ent(val.get(f"rep.{k}.{_SEC_RAP[c]}_G")), _ent(val.get(f"rep.{k}.{_SEC_RAP[c]}_F"))
                m[cle][k][c][0] += g
                m[cle][k][c][1] += f
                n += g + f
        m["n_" + cle] = 1 if n else 0
    return m


def cumuler_mat(dest, m):
    dest["ecoles"] += m["ecoles"]
    cumuler(dest["ages"], m["ages"])
    for c in SECS:
        for i in (0, 1):
            dest["rec"][c][i] += m["rec"][c][i]
    for cle in ("rentree", "fin"):
        cumuler(dest[cle], m[cle])
        dest["n_" + cle] += m["n_" + cle]
    dest["n_rec"] += m["n_rec"]


def gft_sec(d):
    """{SP: [g, f], SG: [g, f]} → {SP: [g, f, t], SG: [...], T: [...]}"""
    o = {c: [d[c][0], d[c][1], d[c][0] + d[c][1]] for c in SECS}
    o["T"] = [sum(o[c][i] for c in SECS) for i in range(3)]
    return o


def tableau_mat(mat):
    """Synthèse prête à afficher d'un regroupement : âges (tableau 3), recensement, rentrée et fin d'année."""
    return {"ages": tableau_ages(mat["ages"], SECS, AGES_M), "rec": gft_sec(mat["rec"]),
            "rentree": [(k, l_, gft_sec(mat["rentree"][k])) for k, l_ in LIGNES_RENTREE],
            "fin": [(k, l_, gft_sec(mat["fin"][k])) for k, l_ in LIGNES_FIN],
            "ecoles": mat["ecoles"], "n_rec": mat["n_rec"], "n_rentree": mat["n_rentree"], "n_fin": mat["n_fin"],
            "deb": gft_sec(mat["rentree"]["debut"]), "finf": gft_sec(mat["fin"]["fin"])}


def _t(s):
    return str(escape(str(s)))


TYPES_GRAPHIQUE = [("ligne", "Courbe"), ("barres", "Histogramme"), ("empilees", "▤ Barres empilées"),
                   ("aire", "◭ Aires"), ("points", "⁘ Points")]


def _svg_graphique(categories, series, aria, kind):
    """Un graphique SVG d'un type donné : ligne, barres (groupées), empilees, aire, points."""
    n = len(categories)
    larg = max(640, 70 * n + 90)
    leg, x, yl = [], 56, 15.5
    for nom, coul, _ in series:
        w = 28 + 6.6 * len(nom)
        if x + w > larg - 10 and x > 56:
            x, yl = 56, yl + 18
        leg.append((x, yl, nom, coul))
        x += w
    dy = yl - 15.5
    x0, x1, y0, y1 = 56, larg - 20, 34 + dy, 236 + dy
    if kind == "empilees":
        vals = [sum(max(0, vs[i] or 0) for _, _, vs in series) for i in range(n)]
    else:
        vals = [v for _, _, vs in series for v in vs if v is not None]
    brut = max(vals + [1]) / 4
    puiss = 10 ** (len(str(int(brut))) - 1) if brut >= 1 else 1
    pas = next(k * puiss for k in (1, 2, 2.5, 5, 10) if k * puiss >= brut)
    m = pas * 4

    def X(i):
        return x0 + (x1 - x0) * (i + .5) / n

    def Y(v):
        return y1 - (y1 - y0) * v / m
    bande = (x1 - x0) / n
    p = [f'<svg viewBox="0 0 {larg} {300 + dy:.0f}" width="100%" role="img" aria-label="{_t(aria)}" class="jsvg" '
         f'style="min-width:{min(larg, 900)}px">']
    for x, yl_, nom, coul in leg:
        p.append(f'<rect x="{x:.0f}" y="{yl_ - 9.5:.1f}" width="11" height="11" rx="2" fill="{coul}"/>'
                 f'<text x="{x + 15:.0f}" y="{yl_:.1f}" class="lg">{_t(nom)}</text>')
    for j in range(5):
        v = pas * j
        yy = Y(v)
        p.append(f'<line x1="{x0}" y1="{yy:.1f}" x2="{x1}" y2="{yy:.1f}" class="gr"/>'
                 f'<text x="{x0 - 6}" y="{yy + 4:.1f}" text-anchor="end" class="vl">{v:g}</text>')
    for i, c in enumerate(categories):
        lib = str(c)
        lib = lib if len(lib) <= 16 else lib[:15] + "…"
        p.append(f'<text x="{X(i):.1f}" y="{y1 + 16}" text-anchor="end" transform="rotate(-30 {X(i):.1f} {y1 + 16})" class="lb">{_t(lib)}</text>')
    etiq = n <= 14

    def fv(v):
        return (f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)).replace(".", ",")

    def info(i, nom, v):
        return f'<title>{_t(categories[i])} – {_t(nom)} : {v}</title>'
    if kind == "barres":
        ns = len(series)
        lb = min(26, bande * .8 / max(1, ns))
        for k, (nom, coul, vs) in enumerate(series):
            for i, v in enumerate(vs):
                if v is None:
                    continue
                xx = X(i) - lb * ns / 2 + k * lb
                p.append(f'<g>{info(i, nom, v)}<rect x="{xx:.1f}" y="{Y(max(v, 0)):.1f}" width="{lb - 1:.1f}" '
                         f'height="{max(0.5, y1 - Y(max(v, 0))):.1f}" fill="{coul}" rx="1.5"/>'
                         + (f'<text x="{xx + lb / 2:.1f}" y="{Y(max(v, 0)) - 3:.1f}" text-anchor="middle" class="vl">{fv(v)}</text>'
                            if etiq and ns <= 4 else "") + "</g>")
    elif kind == "empilees":
        lb = min(40, bande * .6)
        base = [0.0] * n
        for nom, coul, vs in series:
            for i, v in enumerate(vs):
                if not v or v <= 0:
                    continue
                ya, yb = Y(base[i] + v), Y(base[i])
                p.append(f'<g>{info(i, nom, v)}<rect x="{X(i) - lb / 2:.1f}" y="{ya:.1f}" width="{lb:.1f}" height="{max(0.5, yb - ya):.1f}" '
                         f'fill="{coul}"/>' + (f'<text x="{X(i):.1f}" y="{(ya + yb) / 2 + 3:.1f}" text-anchor="middle" '
                                                f'class="vl" style="fill:#fff">{fv(v)}</text>' if etiq and yb - ya > 11 else "") + "</g>")
                base[i] += v
        if etiq:
            for i in range(n):
                if base[i]:
                    p.append(f'<text x="{X(i):.1f}" y="{Y(base[i]) - 4:.1f}" text-anchor="middle" class="vl"><tspan font-weight="700">'
                             f'{fv(round(base[i], 2))}</tspan></text>')
    else:
        for nom, coul, vs in series:
            pts = [(X(i), Y(v)) for i, v in enumerate(vs) if v is not None]
            if kind == "aire" and len(pts) > 1:
                p.append(f'<polygon fill="{coul}" fill-opacity=".18" stroke="none" points="{pts[0][0]:.1f},{y1} '
                         + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + f' {pts[-1][0]:.1f},{y1}"/>')
            if kind in ("ligne", "aire") and len(pts) > 1:
                p.append(f'<polyline fill="none" stroke="{coul}" stroke-width="2.4" stroke-linejoin="round" '
                         f'points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}"/>')
            for i, v in enumerate(vs):
                if v is None:
                    continue
                p.append(f'<g>{info(i, nom, v)}<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{5 if kind == "points" else 3.6}" '
                         f'fill="{coul}"/>' + (f'<text x="{X(i):.1f}" y="{Y(v) - 7:.1f}" text-anchor="middle" class="vl">{fv(v)}</text>'
                                               if etiq else "") + "</g>")
    p.append("</svg>")
    return "".join(p)


_JS_GRAPHIQUE = ("<script>(function(){if(window.__jgraph)return;window.__jgraph=1;"
                 "window.jgChoix=function(b){var w=b.closest('.jgraph'),k=b.dataset.k;"
                 "w.querySelectorAll('.jg-v').forEach(function(s){s.hidden=s.dataset.k!==k});"
                 "w.querySelectorAll('.jg-b').forEach(function(x){x.classList.toggle('on',x===b)});"
                 "if(w.querySelector('.jg-tous').checked){try{localStorage.setItem('jgraph-type',k)}catch(e){}"
                 "document.querySelectorAll('.jgraph').forEach(function(o){if(o!==w){var bb=o.querySelector('.jg-b[data-k=\"'+k+'\"]');"
                 "if(bb){o.querySelectorAll('.jg-v').forEach(function(s){s.hidden=s.dataset.k!==k});"
                 "o.querySelectorAll('.jg-b').forEach(function(x){x.classList.toggle('on',x===bb)})}}})}};"
                 "document.addEventListener('DOMContentLoaded',function(){var k=null;try{k=localStorage.getItem('jgraph-type')}catch(e){}"
                 "if(k)document.querySelectorAll('.jgraph .jg-b[data-k=\"'+k+'\"]').forEach(function(b){var w=b.closest('.jgraph');"
                 "w.querySelectorAll('.jg-v').forEach(function(s){s.hidden=s.dataset.k!==k});"
                 "w.querySelectorAll('.jg-b').forEach(function(x){x.classList.toggle('on',x===b)})})})})();</script>"
                 "<style>.jgraph .jg-bar{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin:4px 0;font-size:.82em}"
                 ".jgraph .jg-b{border:1px solid #cbd5e1;background:#fff;border-radius:14px;padding:2px 9px;cursor:pointer}"
                 ".jgraph .jg-b.on{background:#1f4e79;color:#fff;border-color:#1f4e79}.jgraph label{margin-left:8px;color:#6b7280}"
                 "@media print{.jgraph .jg-bar{display:none}}</style>")


def svg_courbes(categories, series, aria="Courbes", defaut="ligne"):
    """Graphique au choix (courbe, histogramme, barres empilées, aires, points) : boutons au-dessus du graphique ;
    « pour tous » applique le choix à tous les graphiques de la page et le retient."""
    if not categories or not series:
        return Markup("")
    boutons = "".join(f'<button type="button" class="jg-b{" on" if k == defaut else ""}" data-k="{k}" onclick="jgChoix(this)">{lib}</button>'
                      for k, lib in TYPES_GRAPHIQUE)
    vues = "".join(f'<div class="jg-v" data-k="{k}"{"" if k == defaut else " hidden"}>{_svg_graphique(categories, series, aria, k)}</div>'
                   for k, _l in TYPES_GRAPHIQUE)
    return Markup(f'<div class="jgraph">{_JS_GRAPHIQUE}<div class="jg-bar noprint">Type de graphique : {boutons}'
                  f'<label><input type="checkbox" class="jg-tous" checked> pour tous les graphiques</label></div>{vues}</div>')


def enregistrer(app, H):
    import a_tableau as T

    def garde():
        if not config.juridiction():
            abort(404)

    @app.route("/juridiction/effectifs")
    @H.connexion_requise()
    def jur_effectifs():
        garde()
        flt = T.lire_filtres()
        par = request.args.get("par") if request.args.get("par") in ("cs", "zone", "ecole") else flt["par"]
        if par == "cs" and config.EDITION == "cs":
            par = "zone"
        lignes = T.donnees(flt["annee"], flt["cs_id"], flt["zone_id"], flt["type"], flt["secteur"], flt["q"])
        pers = J.personnel(flt["annee"], cs_id=flt["cs_id"], zone_id=flt["zone_id"], inclure_agents=False)
        s_rap = J.sections("rapports", flt["annee"], [l["id"] for l in lignes])
        for l in lignes:
            l["_rap"] = s_rap.get(l["id"]) or {}
        grp, tot = calculer(lignes, pers, par)
        lib = {"cs": "Circonscription", "zone": "Zone pédagogique", "ecole": "École"}[par]
        noms = [g["nom"] for g in grp]
        courbes = {
            "app": svg_courbes(noms, [("Garçons", PALETTE[0], [g["app"]["t"]["g"] for g in grp]),
                                      ("Filles", PALETTE[1], [g["app"]["t"]["f"] for g in grp]),
                                      ("Total", PALETTE[2], [g["app"]["t"]["t"] for g in grp])], "Apprenants"),
            "pers": svg_courbes(noms, [("Enseignants – H", PALETTE[0], [g["ens"]["h"] for g in grp]),
                                       ("Enseignants – F", PALETTE[1], [g["ens"]["f"] for g in grp]),
                                       ("Directeurs – H", PALETTE[3], [g["dir"]["h"] for g in grp]),
                                       ("Directeurs – F", PALETTE[4], [g["dir"]["f"] for g in grp])], "Personnel enseignant"),
            "cat": svg_courbes(noms, [(l, PALETTE[i], [g["cat"][k]["t"] for g in grp]) for i, (k, l) in enumerate(CATS)],
                               "Catégories"),
            "dip": svg_courbes(noms, [(l, PALETTE[i], [g["dip"][k]["t"] for g in grp]) for i, (k, l) in enumerate(DIPLOMES)],
                               "CAP et CEAP"),
            "aca": svg_courbes(noms, [(l, PALETTE[i % len(PALETTE)], [g["aca"][k]["t"] for g in grp])
                                      for i, (k, l) in enumerate(ACADEMIQUES[:8])], "Diplômes académiques"),
            "prive_app": svg_courbes(noms, [("Garçons", PALETTE[0], [g["prive"]["app"]["t"]["g"] for g in grp]),
                                            ("Filles", PALETTE[1], [g["prive"]["app"]["t"]["f"] for g in grp]),
                                            ("Total", PALETTE[2], [g["prive"]["app"]["t"]["t"] for g in grp])],
                                     "Apprenants du privé"),
            "prive": svg_courbes(noms, [("Enseignants – H", PALETTE[0], [g["prive"]["ens"]["h"] for g in grp]),
                                        ("Enseignants – F", PALETTE[1], [g["prive"]["ens"]["f"] for g in grp]),
                                        ("Directeurs", PALETTE[3], [g["prive"]["dir"]["t"] for g in grp])],
                                 "Secteur privé"),
        }
        # 7. catégories d'âge : tableau global (public / privé à part) et âge moyen ± écart type par regroupement
        ages = {"pub": tableau_ages(tot["ages"]), "prv": tableau_ages(tot["prive"]["ages"])}
        for g in grp:
            t_ = tableau_ages(g["ages"])
            g["age_stats"] = t_["stats"]["ENS"]
            g["age_eff"] = t_["tot"]["ENS"]
        lib_ages = [lib_ for _k, lib_, _a in AGES]
        lib_ages_c = ["< 5"] + [str(i) for i in range(5, 16)] + ["16 +"]
        ta = ages["pub"]
        courbes["ages"] = svg_courbes(lib_ages_c, [("Garçons", PALETTE[0], [x["cells"]["ENS"][0][0] for x in ta["lignes"]]),
                                                   ("Filles", PALETTE[1], [x["cells"]["ENS"][1][0] for x in ta["lignes"]]),
                                                   ("Total", PALETTE[2], [x["cells"]["ENS"][2][0] for x in ta["lignes"]])],
                                      "Apprenants du primaire par âge")
        courbes["ages_cours"] = svg_courbes(lib_ages_c, [(c, PALETTE[i], [x["cells"][c][2][0] for x in ta["lignes"]])
                                                         for i, c in enumerate(COURS)], "Âges par cours")
        courbes["ages_grp"] = svg_courbes(noms, [("Âge moyen – G", PALETTE[0], [g["age_stats"][0][0] for g in grp]),
                                                 ("Âge moyen – F", PALETTE[1], [g["age_stats"][1][0] for g in grp]),
                                                 ("Écart type", PALETTE[3], [g["age_stats"][2][1] for g in grp])],
                                          "Âge moyen et écart type")
        # 8. maternelles par section
        mats = {"pub": tableau_mat(tot["mat"]), "prv": tableau_mat(tot["prive"]["mat"])}
        for g in grp:
            g["mat_t"] = tableau_mat(g["mat"])
            g["mat_tp"] = tableau_mat(g["prive"]["mat"])
        courbes["mat"] = svg_courbes(noms, [("Recensement – SP", PALETTE[0], [g["mat_t"]["rec"]["SP"][2] for g in grp]),
                                            ("Recensement – SG", PALETTE[1], [g["mat_t"]["rec"]["SG"][2] for g in grp]),
                                            ("Rentrée (début)", PALETTE[2], [g["mat_t"]["deb"]["T"][2] for g in grp]),
                                            ("Fin d'année", PALETTE[3], [g["mat_t"]["finf"]["T"][2] for g in grp])],
                                     "Maternelles par section")
        tm = mats["pub"]["ages"]
        courbes["mat_ages"] = svg_courbes([l_ for _k, l_, _a in AGES_M],
                                          [("SP", PALETTE[0], [x["cells"]["SP"][2][0] for x in tm["lignes"]]),
                                           ("SG", PALETTE[1], [x["cells"]["SG"][2][0] for x in tm["lignes"]]),
                                           ("Ensemble", PALETTE[2], [x["cells"]["ENS"][2][0] for x in tm["lignes"]])],
                                          "Âges en maternelle")
        if request.args.get("export") == "xlsx":
            haut = [config.ECOLE.get("nom", ""), f"Effectifs – année {flt['annee']} – par {lib.lower()}"]
            lst = grp + [tot]

            def feuille(nom, colonnes, valeurs):
                return (nom, [lib, "Écoles"] + colonnes, [[g["nom"], g["ecoles"]] + valeurs(g) for g in lst], {"titre_haut": haut})
            feuilles = [
                feuille("Apprenants (public)", ["EP – G", "EP – F", "EP – T", "EM – G", "EM – F", "EM – T", "Total – G", "Total – F", "Total"],
                        lambda g: [g["app"][n][s] for n in ("ep", "em", "t") for s in ("g", "f", "t")]),
                feuille("Personnel", ["Enseignants – H", "Enseignants – F", "Enseignants", "Directeurs – H", "Directeurs – F",
                                      "Directeurs", "Ensemble – H", "Ensemble – F", "Ensemble"],
                        lambda g: [g[n][s] for n in ("ens", "dir", "tous") for s in ("h", "f", "t")]),
                feuille("Catégories", [f"{l} – {s.upper()}" if s != "t" else l for _k, l in CATS for s in ("h", "f", "t")],
                        lambda g: [g["cat"][k][s] for k, _l in CATS for s in ("h", "f", "t")]),
                feuille("CAP et CEAP", [f"{l} – {s.upper()}" if s != "t" else l for _k, l in DIPLOMES for s in ("h", "f", "t")],
                        lambda g: [g["dip"][k][s] for k, _l in DIPLOMES for s in ("h", "f", "t")]),
                feuille("Diplômes académiques", [f"{l} – {s.upper()}" if s != "t" else l for _k, l in ACADEMIQUES for s in ("h", "f", "t")],
                        lambda g: [g["aca"][k][s] for k, _l in ACADEMIQUES for s in ("h", "f", "t")]),
                feuille("Secteur privé", ["Écoles privées", "Apprenants EP – G", "Apprenants EP – F", "Apprenants EP",
                                          "Apprenants EM – G", "Apprenants EM – F", "Apprenants EM", "Apprenants – G",
                                          "Apprenants – F", "Apprenants"]
                        + [f"{l} – {s.upper()}" if s != "t" else l for _k, l in PRIVE for s in ("h", "f", "t")],
                        lambda g: [g["prive"]["ecoles"]] + [g["prive"]["app"][n][s] for n in ("ep", "em", "t") for s in ("g", "f", "t")]
                        + [g["prive"][k][s] for k, _l in PRIVE for s in ("h", "f", "t")]),
            ]
            def feuille_ages(nom, t_, note="Âge au 31 décembre ; « moins de 5 ans » compté 4 ans et « 16 ans et plus » 16 ans pour l'âge moyen et l'écart type"):
                ent = ["Catégorie d'âge"] + [f"{c if c != 'ENS' else 'Ensemble'} – {s_}{' %' if p_ else ''}"
                                             for c in t_["cols"] for s_ in ("G", "F", "T") for p_ in (0, 1)]
                rows = [[x["lib"]] + [x["cells"][c][i][p_] for c in t_["cols"] for i in range(3) for p_ in (0, 1)]
                        for x in t_["lignes"]]
                rows.append(["Total"] + [v for c in t_["cols"] for i in range(3) for v in (t_["tot"][c][i], 100.0 if t_["tot"][c][i] else None)])
                rows.append(["Âge moyen (ans)"] + [v for c in t_["cols"] for i in range(3) for v in (t_["stats"][c][i][0], None)])
                rows.append(["Écart type (ans)"] + [v for c in t_["cols"] for i in range(3) for v in (t_["stats"][c][i][1], None)])
                return (nom, ent, rows, {"titre_haut": haut + [note]})
            feuilles += [feuille_ages("Âges (public)", ages["pub"]), feuille_ages("Âges (privé)", ages["prv"]),
                         (f"Âges par {lib.lower()}"[:31], [lib, "Élèves – G", "Élèves – F", "Élèves", "Âge moyen – G", "Âge moyen – F",
                                                    "Âge moyen", "Écart type – G", "Écart type – F", "Écart type"],
                          [[g["nom"]] + list(g["age_eff"]) + [g["age_stats"][i][0] for i in range(3)] + [g["age_stats"][i][1] for i in range(3)]
                           for g in grp] + [["Total"] + list(ages["pub"]["tot"]["ENS"]) + [ages["pub"]["stats"]["ENS"][i][0] for i in range(3)]
                                            + [ages["pub"]["stats"]["ENS"][i][1] for i in range(3)]], {"titre_haut": haut})]
            def lignes_sec(d):
                return [d[c][i] for c in ("SP", "SG", "T") for i in range(3)]
            ent_sec = [f"{c} – {x}" for c in ("SP", "SG", "Total") for x in ("G", "F", "T")]
            for cle_, nom_ in (("mat_t", "Maternelles par section"), ("mat_tp", "Maternelles privées")):
                tt = mats["pub" if cle_ == "mat_t" else "prv"]
                feuilles.append((nom_[:31], [lib, "Source"] + ent_sec,
                                 [[g["nom"], src] + lignes_sec(g[cle_][k]) for g in grp
                                  for src, k in (("Recensement (tableau 3)", "rec"), ("Rentrée : début d'année", "deb"),
                                                 ("Fin d'année : effectif de fin", "finf"))]
                                 + [["Total", src] + lignes_sec(tt[k]) for src, k in (("Recensement (tableau 3)", "rec"),
                                                                                       ("Rentrée : début d'année", "deb"),
                                                                                       ("Fin d'année : effectif de fin", "finf"))]
                                 + [["Total", f"Rentrée : {l_}"] + lignes_sec(d) for _k, l_, d in tt["rentree"]]
                                 + [["Total", f"Fin d'année : {l_}"] + lignes_sec(d) for _k, l_, d in tt["fin"]],
                                 {"titre_haut": haut + ["Section des petits (SP), section des grands (SG) ; secteur "
                                                        + ("public" if cle_ == "mat_t" else "privé")]}))
            feuilles += [feuille_ages("Âges maternelle (public)", mats["pub"]["ages"], NOTE_AGES_M),
                         feuille_ages("Âges maternelle (privé)", mats["prv"]["ages"], NOTE_AGES_M)]
            H.journal("jur_effectifs", f"{flt['annee']} xlsx")
            return H.xlsx.reponse_classeur(f"effectifs_{flt['annee']}_par_{par}.xlsx", feuilles)
        return render_template("jur_effectifs.html", flt=flt, par=par, lib=lib, grp=grp, tot=tot, CATS=CATS,
                               DIPLOMES=DIPLOMES, ACADEMIQUES=ACADEMIQUES, PRIVE=PRIVE, courbes=courbes, ages=ages, mats=mats, AGES_M=AGES_M, NOTE_AGES_M=NOTE_AGES_M, SECTIONS=SECTIONS, args=T.args_filtres(flt, par=par),
                               args0=T.args_filtres(flt))
