# -*- coding: utf-8 -*-
"""Tableaux de bord et statistiques des applications « GESCOL Circonscription » (CS) et « GESCOL DDEMP ».

Pages (lecture : tout utilisateur connecté ; uniquement en édition cs / ddemp) :
    jur_tableau             /juridiction/tableau-de-bord
    jur_stats_ecoles        /juridiction/statistiques/ecoles
    jur_stats_effectifs     /juridiction/statistiques/effectifs
    jur_stats_enseignants   /juridiction/statistiques/enseignants
    jur_classes             /juridiction/classes          classes par cours (niveau) et par zone / CS (v1.6)
    jur_classes_xlsx        /juridiction/classes.xlsx     export Excel du même tableau
    jur_classes_pdf         /juridiction/classes.pdf      export PDF (paysage, en-tête officiel)
et les fonctions H.jur_stats(annee, cs_id=None) → dict de synthèse et H.jur_classes_par_niveau(annee, cs_id=None)
→ tableau des classes par cours (pour les autres modules).

Classes par cours (v1.6) : on compte le NOMBRE DE CLASSES (groupes pédagogiques) de chaque niveau — CI, CP, CE1, CE2,
CM1, CM2, Maternelle 1, Maternelle 2, Espace enfance (+ niveaux inattendus, en fin de tableau).
Source principale : la section « effectifs » des paquets transmis par les écoles (clé « classes » : une entrée par
classe, avec son « niveau »). Replis, dans l'ordre : (a) un dictionnaire « par_niveau » / « niveaux » de la section
(une classe par niveau renseigné) ; (b) la table locale « classes » (via « ecoles ») lorsque l'école est aussi gérée
dans cette installation (même nom ou même code) ; (c) sinon l'école compte 0 classe (elle est listée comme « sans
données »). Une classe multigrade compte pour une classe, au niveau indiqué.

Tous les calculs de base passent par jur_calc (effectifs, enseignants, besoin_enseignants, cep, taux, ecart_type,
moyenne, cumul) afin que tous les écrans de la juridiction donnent les mêmes chiffres.
Regroupement : une CS regroupe par zone pédagogique ; la DDEMP par circonscription (et par zone quand une CS est
choisie dans le filtre).
"""
import re
from datetime import date

from flask import abort, render_template, request
from markupsafe import Markup, escape

import config
import jur_calc as C
import m_juridiction as J

# ------------------------------------------------------------------ règles (constantes documentées)
# Classe pléthorique : effectif strictement supérieur au seuil (par type d'école).
SEUIL_PLETHORE = {"EP": 60, "EM": 40, "EE": 40}
# CEP : « fort taux » = au moins SEUIL_CEP_FORT % d'admis avec plus de SEUIL_CEP_CANDIDATS candidats ;
# « faible » = moins de SEUIL_CEP_FAIBLE % d'admis.
SEUIL_CEP_FORT, SEUIL_CEP_CANDIDATS, SEUIL_CEP_FAIBLE = 80.0, 35, 50.0
# Âge de départ à la retraite selon la lettre du grade (départ au 31/12 de l'année des N ans).
AGE_RETRAITE = {"A": 60, "B": 58, "C": 55}
HORIZON_RETRAITE = 2      # alerte : départs dans les 2 ans (années civiles de la rentrée et suivante)

NIVEAUX_EP = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
NIVEAUX_MAT = ["Maternelle 1", "Maternelle 2", "Espace enfance"]
NIVEAUX = NIVEAUX_EP + NIVEAUX_MAT
CATEGORIES = [("FE", "FE"), ("ACDPE", "ACDPE"), ("ACDPCTD", "ACDPCTD (AME)"), ("PRIVE", "Privé"), ("AUTRE", "Autre")]
COLONNES_ECOLES = [("EP", "public", "Primaires publiques"), ("EP", "prive", "Primaires privées"),
                   ("EM", "public", "Maternelles publiques"), ("EM", "prive", "Maternelles privées"),
                   ("EE", None, "Espaces enfance")]
# 7.2 / 7.3 de la fiche de recensement (primaire) ; tableau équivalent pour la maternelle
LIGNES_72 = [("m45", "Moins de 4 ans et demi"), ("a45", "4 ans et demi"), ("a5", "5 ans"), ("a6", "6 ans"),
             ("a7", "7 ans"), ("a8", "8 ans"), ("a9", "9 ans et plus")]
COULEUR_G, COULEUR_F, COULEUR_1 = "#2a78d6", "#eb6834", "#2a78d6"

_H = None   # objet H (helpers), fixé par enregistrer()


# ======================================================================== outils
def _niveau_canonique(n):
    """« ce1 », « Maternelle 1 », « Espace Enfance »… → libellé de NIVEAUX (sinon le texte tel quel)."""
    nn = J.norm(n)
    for ref in NIVEAUX:
        if J.norm(ref) == nn:
            return ref
    if nn.startswith("MATERNELLE") or nn in ("MS", "GS", "PS"):
        return {"PS": "Maternelle 1", "MS": "Maternelle 1", "GS": "Maternelle 2"}.get(nn, n)
    return (n or "?").strip() or "?"


def _ordre_niveaux(niveaux):
    connus = [n for n in NIVEAUX if n in niveaux]
    return connus + sorted(n for n in niveaux if n not in NIVEAUX)


def _annee_naissance(v):
    m = re.search(r"(19|20)\d\d", str(v or ""))
    return int(m.group(0)) if m else None


def _ip(f, g):
    """Indice de parité filles / garçons."""
    return round(f / g, 2) if g else None


def nb_fr(v, dec=None):
    """Nombre au format français (espace fine des milliers, virgule décimale) ; « — » si inconnu."""
    if v is None or v == "":
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if dec is None:
        dec = 0 if x == int(x) else (2 if abs(x) < 10 else 1)
    s = f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def pct_fr(v):
    return "—" if v is None else nb_fr(v, 1) + " %"


# ======================================================================== filtres
def lire_filtres(args=None):
    """Lit et contrôle les filtres (année, CS, zone, type, secteur, recherche) de la requête."""
    f = args if args is not None else request.args
    annees = J.annees()
    a = f.get("annee") or J.annee()
    if a not in annees:
        a = J.annee()
    if config.EDITION == "cs":
        c = J.cs_courante()
        cs_id = c["id"] if c else None
    else:
        try:
            cs_id = int(f.get("cs") or 0) or None
        except ValueError:
            cs_id = None
        if cs_id and not J.cs_par_id(cs_id):
            cs_id = None
    try:
        zone_id = int(f.get("zone") or 0) or None
    except ValueError:
        zone_id = None
    zones = J.zones(cs_id) if cs_id else (J.zones() if config.EDITION == "ddemp" else [])
    if zone_id and zone_id not in {z["id"] for z in zones}:
        zone_id = None
    type_ = f.get("type") if f.get("type") in J.TYPES else None
    secteur = f.get("secteur") if f.get("secteur") in J.SECTEURS else None
    return {"annee": a, "annees": annees, "cs_id": cs_id, "zone_id": zone_id, "type": type_, "secteur": secteur,
            "q": (f.get("q") or "").strip()[:60], "zones": zones, "cs": J.cs_liste(),
            "par": "cs" if (config.EDITION == "ddemp" and not cs_id) else "zone"}


def args_filtres(flt, **extra):
    """Paramètres d'URL reproduisant les filtres (liens d'export)."""
    d = {"annee": flt["annee"]}
    for k_url, k in (("cs", "cs_id"), ("zone", "zone_id"), ("type", "type"), ("secteur", "secteur"), ("q", "q")):
        if flt.get(k) and not (k == "cs_id" and config.EDITION == "cs"):
            d[k_url] = flt[k]
    d.update({k: v for k, v in extra.items() if v not in (None, "")})
    return d


# ======================================================================== données par école
def donnees(annee, cs_id=None, zone_id=None, type_=None, secteur=None, recherche=None):
    """Une ligne par école active de la juridiction (filtrée), avec les calculs jur_calc."""
    ecs = J.ecoles(cs_id=cs_id, zone_id=zone_id, type_=type_, secteur=secteur, recherche=recherche or None)
    ids = [e["id"] for e in ecs]
    s_eff = J.sections("effectifs", annee, ids)
    s_pers = J.sections("personnel", annee, ids)
    s_cep = J.sections("cep", annee, ids)
    s_rec = J.sections("recensement", annee, ids)
    transmis = {r["ecole_id"] for r in _H.q("SELECT DISTINCT ecole_id FROM jur_sections WHERE annee=?", (annee,))}
    lignes = []
    for e in ecs:
        eid = e["id"]
        sec = s_eff.get(eid)
        pers = s_pers.get(eid)
        eff = C.effectifs(sec)
        ens = C.enseignants(pers)
        bes = C.besoin_enseignants(sec, pers)
        cep = C.cep(s_cep[eid]) if s_cep.get(eid) else None
        seuil = SEUIL_PLETHORE.get(e["type"], 60)
        lignes.append({
            "id": eid, "code": e["code"], "nom": e["nom"], "type": e["type"], "secteur": e["secteur"],
            "cs_id": e["cs_id"], "cs_nom": e["cs_nom"] or "", "zone_id": e["zone_id"], "zone_nom": e["zone_nom"] or "",
            "localite": e["localite"] or "", "directeur_nom": e["directeur_nom"] or "",
            "transmis": eid in transmis, "a_effectifs": sec is not None, "a_personnel": pers is not None,
            "eff": eff, "ens": {k: ens[k] for k in ("t", "h", "f", "par_categorie")}, "besoin": bes, "cep": cep,
            "moy_classe": C.moyenne(eff["tailles"]),
            "ratio": round(eff["t"] / bes["enseignants"], 1) if bes["enseignants"] else None,
            "plethoriques": sum(1 for t in eff["tailles"] if t > seuil), "seuil": seuil,
            "_sec_eff": sec or {}, "_rec": s_rec.get(eid) or {},
        })
    return lignes


def agreger(lignes):
    """Synthèse d'un ensemble d'écoles (mêmes règles partout)."""
    effs = [l["eff"] for l in lignes]
    s = {k: (v or 0) for k, v in C.cumul(effs, ("g", "f", "t", "classes", "redoublants")).items()}
    tailles = [t for e in effs for t in e["tailles"]]
    avec_eff = [l for l in lignes if l["a_effectifs"]]
    out = {
        "ecoles": len(lignes), "transmis": sum(1 for l in lignes if l["transmis"]),
        "par_type": {}, "g": s["g"], "f": s["f"], "t": s["t"], "classes": s["classes"], "redoublants": s["redoublants"],
        "pct_f": C.taux(s["f"], s["t"]), "pct_g": C.taux(s["g"], s["t"]), "ip": _ip(s["f"], s["g"]),
        "moy_classe": C.moyenne(tailles), "et_classes": C.ecart_type(tailles),
        "et_ecoles": C.ecart_type([l["eff"]["t"] for l in avec_eff]),
        "moy_ecole": C.moyenne([l["eff"]["t"] for l in avec_eff]),
        "plethoriques": sum(l["plethoriques"] for l in lignes),
        "taux_redoublement": C.taux(s["redoublants"], s["t"]),
    }
    for (t, sc, _lib) in COLONNES_ECOLES:
        out["par_type"][f"{t}_{sc or 'tous'}"] = sum(1 for l in lignes if l["type"] == t and (sc is None or l["secteur"] == sc))
    # enseignants
    e = C.cumul([l["ens"] for l in lignes], ("t", "h", "f"))
    b = C.cumul([l["besoin"] for l in lignes], ("classes", "enseignants", "manque", "surplus"))
    et, eh, ef = e["t"] or 0, e["h"] or 0, e["f"] or 0
    cats = {}
    for l in lignes:
        for k, v in l["ens"]["par_categorie"].items():
            cats[k] = cats.get(k, 0) + v
    out["ens"] = {"t": et, "h": eh, "f": ef, "pct_h": C.taux(eh, et), "pct_f": C.taux(ef, et), "ecart": eh - ef,
                  "ecart_pts": round(C.taux(eh, et) - C.taux(ef, et), 1) if et else None,
                  "par_categorie": cats, "besoin": b["classes"] or 0, "disponibles": b["enseignants"] or 0,
                  "manque": b["manque"] or 0, "surplus": b["surplus"] or 0,
                  "ratio": round(s["t"] / b["enseignants"], 1) if b["enseignants"] else None,
                  "ecoles_manque": sum(1 for l in lignes if l["besoin"]["manque"]),
                  "ecoles_surplus": sum(1 for l in lignes if l["besoin"]["surplus"])}
    # CEP (taux calculés sur les seules écoles dont les résultats sont connus)
    ceps = [l["cep"] for l in lignes if l["cep"] and l["cep"]["candidats"]]
    connus = [c for c in ceps if c["admis"] is not None]
    cg = sum(c["candidats_g"] for c in ceps)
    cf = sum(c["candidats_f"] for c in ceps)
    kg = sum(c["candidats_g"] for c in connus)
    kf = sum(c["candidats_f"] for c in connus)
    ag = sum(c["admis_g"] for c in connus)
    af = sum(c["admis_f"] for c in connus)
    out["cep"] = {"ecoles": len(ceps), "ecoles_resultats": len(connus), "candidats_g": cg, "candidats_f": cf,
                  "candidats": cg + cf, "candidats_connus": kg + kf,
                  "admis_g": ag if connus else None, "admis_f": af if connus else None,
                  "admis": (ag + af) if connus else None,
                  "taux": C.taux(ag + af, kg + kf) if connus else None,
                  "taux_g": C.taux(ag, kg) if connus else None, "taux_f": C.taux(af, kf) if connus else None}
    return out


def groupes(lignes, par):
    """[(clé, nom, lignes)] dans l'ordre de la juridiction (CS par numéro, zones par ordre)."""
    out = {}
    for l in lignes:
        if par == "cs":
            k, nom = l["cs_id"], l["cs_nom"] or "Sans circonscription"
        else:
            k, nom = l["zone_id"], l["zone_nom"] or "Sans zone pédagogique"
        out.setdefault(k, [k, nom, []])[2].append(l)
    return [tuple(v) for v in out.values()]


def par_secteur_type(lignes):
    """Lignes « secteur × type » + sous-totaux secteur + ensemble (tableau des effectifs)."""
    res = []
    for sc, sl in J.SECTEURS.items():
        sous = [l for l in lignes if l["secteur"] == sc]
        for t, tl in J.TYPES.items():
            ll = [l for l in sous if l["type"] == t]
            if ll:
                res.append({"lib": f"{tl} – {sl.lower()}", "secteur": sc, "type": t, "agg": agreger(ll), "st": ""})
        if sous:
            res.append({"lib": f"Sous-total {sl.lower()}", "secteur": sc, "type": None, "agg": agreger(sous), "st": "b"})
    return res


# ======================================================================== bilan des visites, retraites, alertes
FONCTIONS_VISITEUR = {"CP": "Conseiller pédagogique", "CCS": "Chef de circonscription scolaire"}


def bilan_visites(annee, cs_id, lignes):
    """Bilan des activités des CP et CCS. Utilise H.jur_bilan_visites (module des visites) s'il existe ;
    sinon calcule depuis les sections « visites » transmises par les écoles."""
    f = getattr(_H, "jur_bilan_visites", None)
    if callable(f):
        try:
            r = f(annee, cs_id)
            if isinstance(r, list):
                return [dict(x) for x in r], "module"
        except Exception:  # noqa: BLE001 — repli sur le calcul local
            pass
    ids = {l["id"]: l for l in lignes}
    acc = {}
    for eid, vis in J.sections("visites", annee, list(ids)).items():
        l = ids[eid]
        for v in vis or []:
            typ = (v.get("type") or "").upper()
            if typ not in FONCTIONS_VISITEUR:
                continue
            nom = (v.get("visiteur") or "").strip() or "(visiteur non indiqué)"
            k = (J.norm(nom), typ, l["cs_nom"])
            a = acc.setdefault(k, {"visiteur": nom, "fonction": FONCTIONS_VISITEUR[typ], "cs_nom": l["cs_nom"],
                                   "_cl": 0, "_ec": set(), "_ecoles": set(), "_ens": set(), "_notes": []})
            a["_cl"] += 1
            a["_ec"].add((eid, v.get("date") or ""))
            a["_ecoles"].add(eid)
            ens = (v.get("enseignant_nip") or "").strip() or J.norm(v.get("enseignant"))
            if ens:
                a["_ens"].add((eid, ens))
            try:
                if v.get("note") not in (None, ""):
                    a["_notes"].append(float(v["note"]))
            except (TypeError, ValueError):
                pass
    out = [{"visiteur": a["visiteur"], "fonction": a["fonction"], "cs_nom": a["cs_nom"], "visites_classe": a["_cl"],
            "visites_ecole": len(a["_ec"]), "ecoles": len(a["_ecoles"]), "enseignants": len(a["_ens"]),
            "note_moyenne": C.moyenne(a["_notes"])} for a in acc.values()]
    out.sort(key=lambda x: (x["cs_nom"], x["fonction"] != "Chef de circonscription scolaire", x["visiteur"]))
    return out, "ecoles"


def retraites(annee, cs_id=None, zone_id=None):
    """Départs à la retraite proches. Utilise H.jur_retraites_proches s'il existe ; sinon règle :
    lettre du grade A → 60 ans, B → 58, C → 55 ; départ au 31/12 de l'année des N ans ; on signale les départs
    des années civiles de la rentrée et de la suivante (et les âges dépassés encore en poste)."""
    f = getattr(_H, "jur_retraites_proches", None)
    if callable(f) and not zone_id:
        try:
            r = f(annee, cs_id)
            if isinstance(r, list):
                out = []
                for x in r:
                    x = dict(x)
                    d = x.get("retraite") or x.get("date_depart") or x.get("date_retraite") or ""
                    an = d.year if hasattr(d, "year") else _annee_naissance(d)
                    txt = x.get("retraite_txt") or (d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d))
                    out.append({"nom": x.get("nom_complet") or " ".join(p for p in (x.get("nom"), x.get("prenoms")) if p),
                                "grade": x.get("grade") or "",
                                "ecole": x.get("ecole_service") or x.get("ecole_nom") or x.get("poste") or "",
                                "cs_nom": x.get("cs_nom") or "", "date_naissance": x.get("date_naissance") or "",
                                "depart": txt, "annee_depart": an, "restant": x.get("restant_txt") or "",
                                "depasse": bool(x.get("retraite_atteinte")), "cle": x.get("cle")})
                return out
        except Exception:  # noqa: BLE001
            pass
    a0 = int(str(annee)[:4]) if str(annee)[:4].isdigit() else date.today().year
    out = []
    for p in J.personnel(annee, cs_id, zone_id, inclure_agents=not zone_id):
        if p.get("actif") is False:
            continue
        lettre = (p.get("grade") or "").strip()[:1].upper()
        an = _annee_naissance(p.get("date_naissance"))
        if lettre not in AGE_RETRAITE or not an:
            continue
        dep = an + AGE_RETRAITE[lettre]
        if dep <= a0 + HORIZON_RETRAITE - 1:
            out.append({"nom": f"{p.get('nom', '')} {p.get('prenoms', '')}".strip(), "grade": p.get("grade") or "",
                        "ecole": p.get("ecole_nom") or p.get("poste") or "", "cs_nom": p.get("cs_nom") or "",
                        "date_naissance": p.get("date_naissance") or "", "depart": f"31/12/{dep}", "annee_depart": dep,
                        "depasse": dep < a0})
    out.sort(key=lambda x: (x["annee_depart"] or 0, x["nom"]))
    return out


# ======================================================================== graphiques SVG (côté serveur)
def _t(x):
    return escape(str(x))


def svg_barres(categories, series, unite="", ref=None, ref_lib="", max_=None, aria="Graphique"):
    """Barres horizontales groupées. series = [(nom, couleur, [valeurs])] ; ref = ligne de référence (ex. taux
    global). Chaque barre porte une info-bulle (<title>)."""
    if not categories:
        return Markup("")
    ns = len(series)
    hb, gap = 13, 2
    hl = ns * hb + (ns - 1) * gap + 12
    x0, x1 = 178, 560
    vals = [v for _, _, vs in series for v in vs if v is not None]
    m = max_ or max(vals + [ref or 0, 1])
    haut = 22 + hl * len(categories) + 8
    p = [f'<svg viewBox="0 0 640 {haut}" width="100%" role="img" aria-label="{_t(aria)}" class="jsvg">']
    # légende (≥ 2 séries) ou rien (1 série : le titre de la carte la nomme)
    if ns > 1:
        x = x0
        for nom, coul, _ in series:
            p.append(f'<rect x="{x}" y="4" width="11" height="11" rx="2" fill="{coul}"/>'
                     f'<text x="{x + 15}" y="13.5" class="lg">{_t(nom)}</text>')
            x += 26 + 7 * len(nom)
    for j in range(0, 5):   # quadrillage discret
        gx = x0 + (x1 - x0) * j / 4
        p.append(f'<line x1="{gx:.1f}" y1="20" x2="{gx:.1f}" y2="{haut - 6}" class="gr"/>')
    for i, cat in enumerate(categories):
        y = 22 + i * hl
        p.append(f'<text x="{x0 - 8}" y="{y + hl / 2 + 1:.1f}" text-anchor="end" class="lb">{_t(str(cat)[:30])}</text>')
        for k, (nom, coul, vs) in enumerate(series):
            v = vs[i]
            yy = y + 6 + k * (hb + gap)
            if v is None:
                p.append(f'<text x="{x0 + 4}" y="{yy + 10}" class="vl">—</text>')
                continue
            w = max(0.0, (x1 - x0) * v / m)
            p.append(f'<g><title>{_t(cat)} – {_t(nom)} : {_t(nb_fr(v))}{_t(unite)}</title>'
                     f'<rect x="{x0}" y="{yy}" width="{max(w, 1.5):.1f}" height="{hb}" rx="3" fill="{coul}"/>'
                     f'<text x="{x0 + w + 4:.1f}" y="{yy + 10}" class="vl">{_t(nb_fr(v))}{_t(unite)}</text></g>')
    if ref is not None:
        rx = x0 + (x1 - x0) * ref / m
        p.append(f'<line x1="{rx:.1f}" y1="18" x2="{rx:.1f}" y2="{haut - 4}" class="ref"/>'
                 f'<text x="{rx + 3:.1f}" y="14" class="lg">{_t(ref_lib)} {_t(nb_fr(ref))}{_t(unite)}</text>')
    p.append("</svg>")
    return Markup("".join(p))


def svg_repartition(g, f, aria="Répartition filles / garçons"):
    """Barre 100 % garçons / filles avec libellés directs."""
    t = (g or 0) + (f or 0)
    if not t:
        return Markup("")
    wg = 600 * g / t
    pg, pf = C.taux(g, t), C.taux(f, t)
    p = [f'<svg viewBox="0 0 640 58" width="100%" role="img" aria-label="{_t(aria)}" class="jsvg">',
         f'<g><title>Garçons : {_t(nb_fr(g))} ({_t(pct_fr(pg))})</title>'
         f'<rect x="20" y="8" width="{max(wg - 1, 0):.1f}" height="22" rx="4" fill="{COULEUR_G}"/></g>',
         f'<g><title>Filles : {_t(nb_fr(f))} ({_t(pct_fr(pf))})</title>'
         f'<rect x="{20 + wg + 1:.1f}" y="8" width="{max(600 - wg - 1, 0):.1f}" height="22" rx="4" fill="{COULEUR_F}"/></g>',
         f'<text x="20" y="48" class="lb2">Garçons {_t(nb_fr(g))} · {_t(pct_fr(pg))}</text>',
         f'<text x="620" y="48" text-anchor="end" class="lb2">Filles {_t(nb_fr(f))} · {_t(pct_fr(pf))}</text>',
         "</svg>"]
    return Markup("".join(p))


def svg_pyramide(ages, aria="Pyramide des âges"):
    """ages = {âge(int): [g, f]} → pyramide (garçons à gauche, filles à droite)."""
    if not ages:
        return Markup("")
    lst = sorted(ages)
    m = max(max(v) for v in ages.values()) or 1
    hl, cx, demi = 17, 320, 250
    haut = 30 + hl * len(lst)
    p = [f'<svg viewBox="0 0 640 {haut}" width="100%" role="img" aria-label="{_t(aria)}" class="jsvg">',
         f'<text x="{cx - 14}" y="12" text-anchor="end" class="lg">◀ Garçons</text>',
         f'<text x="{cx + 14}" y="12" class="lg">Filles ▶</text>']
    for i, a in enumerate(reversed(lst)):
        g, f = ages[a]
        y = 20 + i * hl
        wg, wf = demi * g / m, demi * f / m
        p.append(f'<g><title>{a} ans – garçons : {g}</title><rect x="{cx - 13 - wg:.1f}" y="{y}" width="{max(wg, 1):.1f}" '
                 f'height="{hl - 3}" rx="3" fill="{COULEUR_G}"/></g>'
                 f'<g><title>{a} ans – filles : {f}</title><rect x="{cx + 13:.1f}" y="{y}" width="{max(wf, 1):.1f}" '
                 f'height="{hl - 3}" rx="3" fill="{COULEUR_F}"/></g>'
                 f'<text x="{cx}" y="{y + 11}" text-anchor="middle" class="lb">{a}</text>'
                 f'<text x="{cx - 17 - wg:.1f}" y="{y + 11}" text-anchor="end" class="vl">{g}</text>'
                 f'<text x="{cx + 17 + wf:.1f}" y="{y + 11}" class="vl">{f}</text>')
    p.append("</svg>")
    return Markup("".join(p))


# ======================================================================== détails des effectifs
def effectifs_par_niveau(lignes):
    """{niveau: {"public": [g, f], "prive": [g, f], "red": [g, f]}} à partir des classes (mêmes données que
    jur_calc.effectifs, détaillées par sexe pour les redoublants)."""
    out = {}
    for l in lignes:
        for c in (l["_sec_eff"].get("classes") or []):
            n = _niveau_canonique(c.get("niveau"))
            d = out.setdefault(n, {"public": [0, 0], "prive": [0, 0], "red": [0, 0]})
            d[l["secteur"]][0] += C.entier(c.get("garcons"))
            d[l["secteur"]][1] += C.entier(c.get("filles"))
            d["red"][0] += C.entier(c.get("redoublants_g"))
            d["red"][1] += C.entier(c.get("redoublants_f"))
    return {n: out[n] for n in _ordre_niveaux(out)}


def lignes_niveaux(par_niv):
    """Lignes affichables du tableau des effectifs par niveau (+ ensemble)."""
    res = []
    tot = {"public": [0, 0], "prive": [0, 0], "red": [0, 0]}
    for n, d in par_niv.items():
        for k in tot:
            tot[k][0] += d[k][0]
            tot[k][1] += d[k][1]
        res.append(_ligne_niv(n, d))
    return res, (_ligne_niv("Ensemble", tot) if res else None)


def _ligne_niv(nom, d):
    g = d["public"][0] + d["prive"][0]
    f = d["public"][1] + d["prive"][1]
    rg, rf = d["red"]
    return {"niveau": nom, "pub": d["public"] + [sum(d["public"])], "pri": d["prive"] + [sum(d["prive"])],
            "ens": [g, f, g + f], "pct_f": C.taux(f, g + f), "pct_g": C.taux(g, g + f), "ip": _ip(f, g),
            "red": [rg, rf, rg + rf], "t_red": C.taux(rg + rf, g + f), "t_red_g": C.taux(rg, g), "t_red_f": C.taux(rf, f)}


def niveaux_par_groupe(lignes, par):
    """Effectifs par groupe (zone / CS) × niveau : {"niveaux": [...], "lignes": [(nom, {niveau: [g, f]}, [G, F, T])]}."""
    tous = set()
    res = []
    for _k, nom, ll in groupes(lignes, par):
        d = {}
        for n, v in effectifs_par_niveau(ll).items():
            d[n] = [v["public"][0] + v["prive"][0], v["public"][1] + v["prive"][1]]
            tous.add(n)
        a = agreger(ll)
        res.append((nom, d, [a["g"], a["f"], a["t"]]))
    return {"niveaux": _ordre_niveaux(tous), "lignes": res}


# ======================================================================== classes par cours (v1.6)
def _classes_locales(e):
    """Repli : classes de la table locale « classes » si l'école est aussi gérée dans cette installation.
    Correspondance par code (ecoles.code s'il existe) ou par nom normalisé. {niveau: nb} ou {}."""
    try:
        cols = {r[1] for r in _H.get_db().execute("PRAGMA table_info(ecoles)")}
        if "nom" not in cols:
            return {}
        loc = None
        if "code" in cols and e.get("code"):
            loc = _H.q("SELECT id FROM ecoles WHERE code=? AND actif=1", (e["code"],), un=True)
        if not loc:
            for r in _H.q("SELECT id, nom FROM ecoles WHERE actif=1"):
                if J.norm(r["nom"]) == J.norm(e.get("nom")):
                    loc = r
                    break
        if not loc:
            return {}
        cols_cl = {r[1] for r in _H.get_db().execute("PRAGMA table_info(classes)")}
        if "ecole_id" not in cols_cl:
            return {}
        out = {}
        for r in _H.q("SELECT niveau FROM classes WHERE ecole_id=?", (loc["id"],)):
            n = _niveau_canonique(r["niveau"])
            out[n] = out.get(n, 0) + 1
        return out
    except Exception:  # noqa: BLE001 — la table locale peut ne pas exister dans cette édition
        return {}


def classes_ecole(sec, e=None):
    """Nombre de classes par niveau canonique pour une école. sec = section « effectifs » (ou None).
    Renvoie ({niveau: nb}, source) avec source ∈ {"classes", "niveaux", "locale", "aucune"}."""
    sec = sec or {}
    cl = sec.get("classes")
    if isinstance(cl, list) and cl:
        out = {}
        for c in cl:
            if not isinstance(c, dict):
                continue
            n = _niveau_canonique(c.get("niveau") or c.get("nom"))
            out[n] = out.get(n, 0) + 1
        return out, "classes"
    for cle in ("par_niveau", "niveaux"):
        d = sec.get(cle)
        if isinstance(d, dict) and d:
            out = {}
            for niv, v in d.items():
                nb = 0
                if isinstance(v, dict):
                    nb = C.entier(v.get("classes")) or (1 if (C.entier(v.get("garcons")) + C.entier(v.get("filles"))
                                                            + C.entier(v.get("t"))) else 0)
                elif isinstance(v, (list, tuple)):
                    nb = 1 if sum(C.entier(x) for x in v) else 0
                else:
                    nb = 1 if C.entier(v) else 0
                if nb:
                    n = _niveau_canonique(niv)
                    out[n] = out.get(n, 0) + nb
            if out:
                return out, "niveaux"
    if e is not None:
        loc = _classes_locales(e)
        if loc:
            return loc, "locale"
    return {}, "aucune"


def classes_par_niveau(lignes):
    """Tableau « classes par cours » pour un ensemble d'écoles (lignes de donnees()) :
    {"niveaux": [...], "par_niveau": {niveau: nb}, "total": nb, "ecoles": n, "sans_donnees": n, "sources": {src: n}}."""
    par, sources, sans = {}, {}, 0
    for l in lignes:
        d, src = classes_ecole(l["_sec_eff"], {"code": l["code"], "nom": l["nom"]})
        sources[src] = sources.get(src, 0) + 1
        if not d:
            sans += 1
        for n, nb in d.items():
            par[n] = par.get(n, 0) + nb
    niveaux = _ordre_niveaux(par)
    return {"niveaux": niveaux, "par_niveau": {n: par[n] for n in niveaux}, "total": sum(par.values()),
            "ecoles": len(lignes), "sans_donnees": sans, "sources": sources}


def tableau_classes(lignes, par):
    """Lignes du tableau « classes par cours et par zone » : CS → par zone ; DDEMP → par circonscription (sous-total)
    avec le détail des zones de chaque CS. Renvoie {"niveaux", "lignes": [{"nom", "niveau": "zone"|"cs"|"total",
    "cs_id", "zone_id", "par_niveau", "total", "ecoles", "sans_donnees"}], "total": {...}}."""
    tous = set()
    rows = []

    def ligne(nom, lvl, ll, **ids):
        c = classes_par_niveau(ll)
        tous.update(c["niveaux"])
        rows.append(dict(nom=nom, niveau=lvl, par_niveau=c["par_niveau"], total=c["total"], ecoles=c["ecoles"],
                         sans_donnees=c["sans_donnees"], **ids))

    if par == "cs":
        for k, nom, ll in groupes(lignes, "cs"):
            ligne(nom, "cs", ll, cs_id=k, zone_id=None)
            for kz, nz, lz in groupes(ll, "zone"):
                ligne(nz, "zone", lz, cs_id=k, zone_id=kz)
    else:
        for kz, nz, lz in groupes(lignes, "zone"):
            ligne(nz, "zone", lz, cs_id=None, zone_id=kz)
    tot = classes_par_niveau(lignes)
    tous.update(tot["niveaux"])
    niveaux = _ordre_niveaux(tous)
    for r in rows:
        r["par_niveau"] = {n: r["par_niveau"].get(n, 0) for n in niveaux}
    tot["par_niveau"] = {n: tot["par_niveau"].get(n, 0) for n in niveaux}
    return {"niveaux": niveaux, "lignes": rows, "total": tot}


def jur_classes_par_niveau(annee=None, cs_id=None, zone_id=None):
    """Interface pour les autres modules : tableau_classes() de la juridiction (ou d'une CS / zone)."""
    annee = annee or J.annee()
    lignes = donnees(annee, cs_id, zone_id)
    par = "cs" if (config.EDITION == "ddemp" and not cs_id) else "zone"
    return tableau_classes(lignes, par)


def _ligne_age_ep(a):
    return "m5" if a < 5 else ("a16" if a >= 16 else f"a{a}")


LIGNES_73 = [("m5", "Moins de 5 ans")] + [(f"a{i}", f"{i} ans") for i in range(5, 16)] + [("a16", "16 ans et plus")]
LIGNES_73M = [("m3", "Moins de 3 ans"), ("a3", "3 ans"), ("a4", "4 ans"), ("a5", "5 ans"), ("a6", "6 ans et plus")]


def _ligne_age_mat(a):
    return "m3" if a < 3 else ("a6" if a >= 6 else f"a{a}")


def tableau_ages(lignes, niveaux, lignes_age, fct_ligne):
    """Tableau type « 7.3 » : âge × niveau × sexe à partir des sections effectifs (« ages » + classes).
    La ligne « Âge non précisé » reprend l'écart entre le total des classes et les âges déclarés."""
    cells = {k: {n: [0, 0] for n in niveaux} for k, _ in lignes_age}
    tot = {n: [0, 0] for n in niveaux}
    red = {n: [0, 0] for n in niveaux}
    eh = [0, 0]
    for l in lignes:
        sec = l["_sec_eff"]
        for c in sec.get("classes") or []:
            n = _niveau_canonique(c.get("niveau"))
            if n in tot:
                tot[n][0] += C.entier(c.get("garcons"))
                tot[n][1] += C.entier(c.get("filles"))
                red[n][0] += C.entier(c.get("redoublants_g"))
                red[n][1] += C.entier(c.get("redoublants_f"))
        concerne = any(_niveau_canonique(c.get("niveau")) in tot for c in sec.get("classes") or [])
        if concerne:
            h = sec.get("handicapes") or [0, 0]
            eh[0] += C.entier(h[0] if len(h) > 0 else 0)
            eh[1] += C.entier(h[1] if len(h) > 1 else 0)
        for niv, dist in (sec.get("ages") or {}).items():
            n = _niveau_canonique(niv)
            if n not in tot or not isinstance(dist, dict):
                continue
            for age, gf in dist.items():
                try:
                    a = int(float(age))
                except (TypeError, ValueError):
                    continue
                k = fct_ligne(a)
                if k in cells and isinstance(gf, (list, tuple)) and len(gf) >= 2:
                    cells[k][n][0] += C.entier(gf[0])
                    cells[k][n][1] += C.entier(gf[1])
    rows = []

    def ligne(lib, d, st="", eh_=None):
        cols = []
        sg = sf = 0
        for n in niveaux:
            g, f = d[n]
            sg, sf = sg + g, sf + f
            cols += [g, f, g + f]
        cols += [sg, sf, sg + sf]
        cols += (list(eh_) + [eh_[0] + eh_[1]]) if eh_ else ["", "", ""]
        rows.append({"lib": lib, "cols": cols, "st": st})

    for k, lib in lignes_age:
        ligne(lib, cells[k])
    # écart entre l'effectif des classes et les âges déclarés, par niveau et par sexe
    ecart = {n: [tot[n][i] - sum(cells[k][n][i] for k, _ in lignes_age) for i in (0, 1)] for n in niveaux}
    np_ = {n: [max(0, v) for v in ecart[n]] for n in niveaux}
    trop = {n: [max(0, -v) for v in ecart[n]] for n in niveaux}
    if any(sum(v) for v in np_.values()):
        ligne("Âge non précisé", np_, "np")
    incoherent = any(sum(v) for v in trop.values())
    if incoherent:
        ligne("Âges déclarés en trop (à corriger, à retrancher)", trop, "trop")
    ligne("Total", tot, "b", eh)
    ligne("Total des redoublants", red)
    return {"niveaux": niveaux, "lignes": rows, "vide": not any(sum(v) for v in tot.values()), "incoherent": incoherent}


def recensement_7(lignes):
    """7.1 effectif global, 7.2 nouveaux inscrits au CI (par âge si les fiches de recensement le donnent),
    7.3 répartition par âge × année d'étude (écoles primaires)."""
    ep = [l for l in lignes if l["type"] == "EP"]
    a = agreger(ep)
    t72 = {k: [0, 0] for k, _ in LIGNES_72}
    t72b = [0, 0]
    nouveaux = [0, 0]
    for l in ep:
        n = l["_sec_eff"].get("nouveaux_ci") or [0, 0]
        nouveaux[0] += C.entier(n[0] if len(n) > 0 else 0)
        nouveaux[1] += C.entier(n[1] if len(n) > 1 else 0)
        val = ((l["_rec"].get("primaire") or {}).get("valeurs") or {})
        for k, _ in LIGNES_72:
            t72[k][0] += C.entier(val.get(f"t72.{k}.g"))
            t72[k][1] += C.entier(val.get(f"t72.{k}.f"))
        t72b[0] += C.entier(val.get("t72b.n.g"))
        t72b[1] += C.entier(val.get("t72b.n.f"))
    lignes72 = [{"lib": lib, "g": t72[k][0], "f": t72[k][1], "t": sum(t72[k])} for k, lib in LIGNES_72]
    sg, sf = sum(t72[k][0] for k in t72), sum(t72[k][1] for k in t72)
    tg, tf = max(nouveaux[0], sg), max(nouveaux[1], sf)
    if tg - sg or tf - sf:
        lignes72.append({"lib": "Âge non précisé", "g": tg - sg, "f": tf - sf, "t": tg - sg + tf - sf})
    lignes72.append({"lib": "Total", "g": tg, "f": tf, "t": tg + tf, "st": "b"})
    return {"t71": [a["g"], a["f"], a["t"]], "t72": lignes72, "t72b": [t72b[0], t72b[1], sum(t72b)],
            "t73": tableau_ages(ep, NIVEAUX_EP, LIGNES_73, _ligne_age_ep), "ecoles": len(ep)}


def pyramide_ages(lignes):
    out = {}
    for l in lignes:
        for _niv, dist in (l["_sec_eff"].get("ages") or {}).items():
            if not isinstance(dist, dict):
                continue
            for age, gf in dist.items():
                try:
                    a = int(float(age))
                except (TypeError, ValueError):
                    continue
                if 0 < a < 30 and isinstance(gf, (list, tuple)) and len(gf) >= 2:
                    d = out.setdefault(a, [0, 0])
                    d[0] += C.entier(gf[0])
                    d[1] += C.entier(gf[1])
    return out


# ======================================================================== synthèse exposée (H.jur_stats)
def calculer(annee=None, cs_id=None, zone_id=None, type_=None, secteur=None, par=None):
    annee = annee or J.annee()
    lignes = donnees(annee, cs_id, zone_id, type_, secteur)
    if par is None:
        par = "cs" if (config.EDITION == "ddemp" and not cs_id) else "zone"
    return lignes, agreger(lignes), [(k, nom, ll, agreger(ll)) for k, nom, ll in groupes(lignes, par)], par


def jur_stats(annee=None, cs_id=None):
    """Synthèse chiffrée de la juridiction (ou d'une CS) pour une année : dict sérialisable JSON.
    {"annee", "niveau", "regroupement": "zone"|"cs", "total": {...agrégat...}, "groupes": [{"id", "nom", ...}],
     "ecoles": [{"id", "nom", "type", "secteur", "cs_nom", "zone_nom", "transmis", "g", "f", "t", "classes",
                 "enseignants", "manque", "surplus", "ratio", "cep_candidats", "cep_admis", "cep_taux"}]}"""
    lignes, tot, grp, par = calculer(annee, cs_id)
    return {
        "annee": annee or J.annee(), "niveau": config.EDITION, "regroupement": par, "total": tot,
        "groupes": [dict(agg, id=k, nom=nom) for k, nom, _ll, agg in grp],
        "ecoles": [{"id": l["id"], "code": l["code"], "nom": l["nom"], "type": l["type"], "secteur": l["secteur"],
                    "cs_nom": l["cs_nom"], "zone_nom": l["zone_nom"], "transmis": l["transmis"],
                    "g": l["eff"]["g"], "f": l["eff"]["f"], "t": l["eff"]["t"], "classes": l["eff"]["classes"],
                    "enseignants": l["ens"]["t"], "manque": l["besoin"]["manque"], "surplus": l["besoin"]["surplus"],
                    "ratio": l["ratio"], "cep_candidats": (l["cep"] or {}).get("candidats"),
                    "cep_admis": (l["cep"] or {}).get("admis"), "cep_taux": (l["cep"] or {}).get("taux")}
                   for l in lignes]}


# ======================================================================== exports (PDF / Excel)
def _infos_haut(flt):
    s = J.structure() or {}
    lst = [("DDEMP", s.get("departement") or "")]
    if config.EDITION == "cs":
        lst.append(("CS", s.get("cs") or ""))
    elif flt.get("cs_id"):
        c = J.cs_par_id(flt["cs_id"])
        lst.append(("CS", c["nom"] if c else ""))
    return lst


def _titre_haut(flt, titre):
    s = J.structure() or {}
    return [s.get("nom") or config.NOMS_APPLI.get(config.EDITION, "GESCOL"), f"{titre} – année scolaire {flt['annee']}",
            _libelle_filtres(flt)]


def _libelle_filtres(flt):
    parts = []
    if flt.get("cs_id") and config.EDITION == "ddemp":
        c = J.cs_par_id(flt["cs_id"])
        parts.append(f"CS : {c['nom']}" if c else "")
    if flt.get("zone_id"):
        z = next((z for z in flt["zones"] if z["id"] == flt["zone_id"]), None)
        if z:
            parts.append(z["nom"])
    if flt.get("type"):
        parts.append(J.TYPES[flt["type"]])
    if flt.get("secteur"):
        parts.append("Secteur " + J.SECTEURS[flt["secteur"]].lower())
    if flt.get("q"):
        parts.append(f"Recherche : « {flt['q']} »")
    return " · ".join(p for p in parts if p) or "Toute la juridiction"


def _signatures():
    s = J.structure() or {}
    if not s.get("responsable_nom") and not s.get("responsable_titre"):
        return None
    img = None
    try:
        du = _H.signature("jur:structure:responsable") if hasattr(_H, "signature") else None
        img = _H.pdfs.image_data_url(du) if du else None
    except Exception:  # noqa: BLE001
        img = None
    titre = s.get("responsable_titre") or ("Le Chef de la Circonscription Scolaire" if config.EDITION == "cs"
                                           else "Le Directeur Départemental")
    return [(titre, s.get("responsable_nom") or "", img, False)]


def _pdf(titre, colonnes, lignes_, flt, nom, **kw):
    from reportlab.lib.units import mm  # noqa: F401  (import paresseux de ReportLab)
    s = J.structure() or {}
    infos = [("Structure", s.get("nom") or ""), ("Année scolaire", flt["annee"]), ("Périmètre", _libelle_filtres(flt))]
    kw.setdefault("signatures", _signatures())
    pdf = _H.pdfs.document_tableau(titre, colonnes, lignes_, infos=infos, paysage=True, infos_haut=_infos_haut(flt),
                                   cycle="primaire", **kw)
    return _H.pdf_reponse(pdf, nom)


def _sous_titre(txt):
    return _H.pdfs.paragraphe(f"<b>{escape(txt)}</b>", 9, espace=5)


ABREV_PDF = {"Maternelle 1": "Mat. 1", "Maternelle 2": "Mat. 2", "Espace enfance": "Esp. enf.", "ENSEMBLE": "Ens.",
             "DONT E.H": "E.H"}


def _abr(txt):
    """Intitulé court pour les colonnes étroites des PDF (« Maternelle 1 G » → « Mat. 1 G »)."""
    for long_, court in ABREV_PDF.items():
        txt = txt.replace(long_, court)
    return txt


def _mini(entetes, lignes_, largeurs_mm=None, taille=7):
    from reportlab.lib.units import mm
    from reportlab.platypus import TableStyle
    data = [list(entetes)] + [["" if v is None else v for v in l] for l in lignes_]
    larg = [w * mm for w in largeurs_mm] if largeurs_mm else None
    t = _H.pdfs.mini_tableau(data, larg, taille=taille)
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    return t


# ======================================================================== enregistrement Flask
def enregistrer(app, H):
    global _H
    _H = H
    H.jur_stats = jur_stats
    H.jur_classes_par_niveau = jur_classes_par_niveau

    @app.template_filter("jur_nb")
    def _f_nb(v, dec=None):
        return nb_fr(v, dec)

    @app.template_filter("jur_pct")
    def _f_pct(v):
        return pct_fr(v)

    def _garde():
        if not config.juridiction():
            abort(404)

    def _lib_groupe(par):
        return "Circonscription" if par == "cs" else "Zone pédagogique"

    # ------------------------------------------------------------------ 1. tableau de bord
    @app.route("/juridiction/tableau-de-bord")
    @H.connexion_requise()
    def jur_tableau():
        _garde()
        flt = lire_filtres()
        lignes, tot, grp, par = calculer(flt["annee"], flt["cs_id"], par=flt["par"])
        noms = [g[1] for g in grp]
        graph_eff = svg_barres(noms, [("Garçons", COULEUR_G, [g[3]["g"] for g in grp]),
                                      ("Filles", COULEUR_F, [g[3]["f"] for g in grp])],
                               aria=f"Effectifs garçons et filles par {_lib_groupe(par).lower()}")
        graph_ratio = svg_barres(noms, [("Élèves par enseignant", COULEUR_1, [g[3]["ens"]["ratio"] for g in grp])],
                                 ref=tot["ens"]["ratio"], ref_lib="Ensemble :",
                                 aria="Ratio élèves par enseignant")
        graph_cep = svg_barres(noms, [("Taux de réussite", COULEUR_1, [g[3]["cep"]["taux"] for g in grp])], unite=" %",
                               ref=tot["cep"]["taux"], ref_lib="Global :", max_=100, aria="Taux de réussite au CEP")
        # CEP : écoles remarquables
        avec = [l for l in lignes if l["cep"] and l["cep"]["candidats"] and l["cep"]["taux"] is not None]
        cep_forts = sorted([l for l in avec if l["cep"]["candidats"] > SEUIL_CEP_CANDIDATS
                            and l["cep"]["taux"] >= SEUIL_CEP_FORT], key=lambda l: (-l["cep"]["taux"], -l["cep"]["candidats"]))
        cep_faibles = sorted([l for l in avec if l["cep"]["taux"] < SEUIL_CEP_FAIBLE], key=lambda l: l["cep"]["taux"])
        bilan, source_bilan = bilan_visites(flt["annee"], flt["cs_id"], lignes)
        tot_bilan = {k: sum(C.entier(b.get(k)) for b in bilan) for k in ("visites_classe", "visites_ecole", "enseignants")}
        alertes = {"sans_transmission": [l for l in lignes if not l["transmis"]],
                   "sans_enseignant": [l for l in lignes if l["besoin"]["manque"]],
                   "plethoriques": [l for l in lignes if l["plethoriques"]],
                   "retraites": retraites(flt["annee"], flt["cs_id"])}
        return render_template("jur_tableau.html", flt=flt, lignes=lignes, tot=tot, grp=grp, par=par,
                               lib_groupe=_lib_groupe(par), graph_eff=graph_eff, graph_rep=svg_repartition(tot["g"], tot["f"]),
                               graph_ratio=graph_ratio, graph_cep=graph_cep, cep_forts=cep_forts, cep_faibles=cep_faibles,
                               bilan=bilan, source_bilan=source_bilan, tot_bilan=tot_bilan, alertes=alertes,
                               secteurs=par_secteur_type(lignes), COLONNES_ECOLES=COLONNES_ECOLES, CATEGORIES=CATEGORIES,
                               SEUILS={"fort": SEUIL_CEP_FORT, "cand": SEUIL_CEP_CANDIDATS, "faible": SEUIL_CEP_FAIBLE,
                                       "plethore": SEUIL_PLETHORE},
                               classes=tableau_classes(lignes, par), ABREV=ABREV_PDF,
                               args=args_filtres(flt), page="jur_tableau")

    # ------------------------------------------------------------------ 1 bis. classes par cours et par zone (v1.6)
    def _classes_contexte():
        flt = lire_filtres()
        lignes = donnees(flt["annee"], flt["cs_id"], flt["zone_id"], flt["type"], flt["secteur"], flt["q"])
        par = flt["par"]
        return flt, lignes, par, tableau_classes(lignes, par)

    def _classes_entetes(tc, par):
        lib = "Circonscription / zone pédagogique" if par == "cs" else "Zone pédagogique"
        return [lib] + [_abr(n) for n in tc["niveaux"]] + ["Total classes", "Écoles", "Sans données"]

    def _classes_lignes(tc):
        rows = []
        for r in tc["lignes"]:
            nom = r["nom"] if r["niveau"] != "zone" or not any(x["niveau"] == "cs" for x in tc["lignes"]) else "    " + r["nom"]
            rows.append([nom] + [r["par_niveau"][n] for n in tc["niveaux"]] + [r["total"], r["ecoles"], r["sans_donnees"]])
        t = tc["total"]
        total = ["Total"] + [t["par_niveau"][n] for n in tc["niveaux"]] + [t["total"], t["ecoles"], t["sans_donnees"]]
        return rows, total

    @app.route("/juridiction/classes")
    @H.connexion_requise()
    def jur_classes():
        _garde()
        flt, lignes, par, tc = _classes_contexte()
        # détail par école (pour vérification : écoles sans données en tête)
        detail = []
        for l in sorted(lignes, key=lambda l: (l["cs_nom"], l["zone_nom"], l["nom"])):
            d, src = classes_ecole(l["_sec_eff"], {"code": l["code"], "nom": l["nom"]})
            detail.append({"l": l, "par_niveau": {n: d.get(n, 0) for n in tc["niveaux"]}, "total": sum(d.values()), "source": src})
        return render_template("jur_tableau_classes.html", flt=flt, tc=tc, par=par, lib_groupe=_lib_groupe(par),
                               detail=detail, ABREV=ABREV_PDF, args=args_filtres(flt), page="jur_classes",
                               SOURCES_CLASSES={"classes": "liste des classes transmise", "niveaux": "effectifs par niveau",
                                                "locale": "école gérée localement", "aucune": "aucune donnée"})

    @app.route("/juridiction/classes.xlsx")
    @H.connexion_requise()
    def jur_classes_xlsx():
        _garde()
        flt, lignes, par, tc = _classes_contexte()
        ent = [_classes_entetes(tc, par)[0]] + tc["niveaux"] + ["Total classes", "Écoles", "Sans données"]
        rows, total = _classes_lignes(tc)
        th = _titre_haut(flt, "Classes par cours et par " + ("circonscription et zone" if par == "cs" else "zone pédagogique"))
        ent_e = ["École", "Code", "Type", "Secteur", "CS", "Zone pédagogique"] + tc["niveaux"] + ["Total classes", "Source"]
        rows_e = []
        for l in sorted(lignes, key=lambda l: (l["cs_nom"], l["zone_nom"], l["nom"])):
            d, src = classes_ecole(l["_sec_eff"], {"code": l["code"], "nom": l["nom"]})
            rows_e.append([l["nom"], l["code"], l["type"], J.SECTEURS[l["secteur"]], l["cs_nom"], l["zone_nom"]]
                          + [d.get(n, 0) for n in tc["niveaux"]] + [sum(d.values()), src])
        H.journal("jur_classes_xlsx", flt["annee"])
        return H.xlsx.reponse_classeur("classes_par_cours.xlsx", [
            ("Classes par cours", ent, rows + [total], {"titre_haut": th}),
            ("Par école", ent_e, rows_e, {"titre_haut": th})])

    @app.route("/juridiction/classes.pdf")
    @H.connexion_requise()
    def jur_classes_pdf():
        _garde()
        flt, lignes, par, tc = _classes_contexte()
        ent = _classes_entetes(tc, par)
        rows, total = _classes_lignes(tc)
        n = len(tc["niveaux"])
        larg = [max(40, 240 - 12 * n - 50)] + [max(9, (240 - 50 - max(40, 240 - 12 * n - 50)) / max(n, 1))] * n + [16, 14, 16]
        if not rows:
            rows = [["Aucune école pour ces critères."] + [""] * (len(ent) - 1)]
        H.journal("jur_classes_pdf", flt["annee"])
        return _pdf("CLASSES PAR COURS ET PAR " + ("CIRCONSCRIPTION ET ZONE PÉDAGOGIQUE" if par == "cs" else "ZONE PÉDAGOGIQUE"),
                    ent, rows, flt, "classes_par_cours.pdf", total=total, taille=7.5, largeurs=larg,
                    sous_titre="Nombre de classes (groupes pédagogiques) par niveau, d'après les effectifs transmis par les écoles",
                    notes_bas=["Source : section « effectifs » des fichiers de transmission des écoles (une entrée par classe). "
                               "« Sans données » : écoles n'ayant pas encore transmis leurs effectifs."])

    # ------------------------------------------------------------------ 2. statistiques des écoles
    TRIS = {"nom": "Nom", "effectif": "Effectif", "cep": "Taux de réussite au CEP", "ratio": "Ratio élèves/enseignant"}

    def _trier(lignes, tri):
        if tri == "effectif":
            return sorted(lignes, key=lambda l: (-l["eff"]["t"], l["nom"]))
        if tri == "cep":
            return sorted(lignes, key=lambda l: (l["cep"] is None or l["cep"]["taux"] is None,
                                                 -((l["cep"] or {}).get("taux") or 0), l["nom"]))
        if tri == "ratio":
            return sorted(lignes, key=lambda l: (l["ratio"] is None, -(l["ratio"] or 0), l["nom"]))
        return sorted(lignes, key=lambda l: (l["cs_nom"], l["zone_nom"], l["nom"]))

    @app.route("/juridiction/statistiques/ecoles")
    @H.connexion_requise()
    def jur_stats_ecoles():
        _garde()
        flt = lire_filtres()
        tri = request.args.get("tri") if request.args.get("tri") in TRIS else "effectif"
        lignes = donnees(flt["annee"], flt["cs_id"], flt["zone_id"], flt["type"], flt["secteur"], flt["q"])
        par = flt["par"]
        grp = [(k, nom, ll, agreger(ll)) for k, nom, ll in groupes(lignes, par)]
        tot = agreger(lignes)
        classes_ = _trier(lignes, tri)
        lib = _lib_groupe(par)
        cols_nb = [c[2] for c in COLONNES_ECOLES]
        cles_nb = [f"{t}_{sc or 'tous'}" for t, sc, _ in COLONNES_ECOLES]
        exp = request.args.get("export")
        if exp in ("xlsx", "pdf"):
            ent_nb = [lib] + cols_nb + ["Total", "Ayant transmis"]
            l_nb = [[nom] + [agg["par_type"][k] for k in cles_nb] + [agg["ecoles"], agg["transmis"]] for _k, nom, _l, agg in grp]
            t_nb = ["Total"] + [tot["par_type"][k] for k in cles_nb] + [tot["ecoles"], tot["transmis"]]
            ent = ["Rang", "École", "Code", "Type", "Secteur", "CS" if config.EDITION == "ddemp" else "Zone",
                   "Zone" if config.EDITION == "ddemp" else "Localité", "G", "F", "Total", "Classes", "Enseignants",
                   "Élèves/ens.", "CEP candidats", "CEP admis", "Taux CEP (%)", "Données"]
            rows = [[i, l["nom"], l["code"], l["type"], J.SECTEURS[l["secteur"]],
                     l["cs_nom"] if config.EDITION == "ddemp" else l["zone_nom"],
                     l["zone_nom"] if config.EDITION == "ddemp" else l["localite"],
                     l["eff"]["g"], l["eff"]["f"], l["eff"]["t"], l["eff"]["classes"], l["ens"]["t"], l["ratio"],
                     (l["cep"] or {}).get("candidats"), (l["cep"] or {}).get("admis"), (l["cep"] or {}).get("taux"),
                     "reçues" if l["transmis"] else "non reçues"] for i, l in enumerate(classes_, 1)]
            if exp == "xlsx":
                th = _titre_haut(flt, "Statistiques des écoles")
                return H.xlsx.reponse_classeur("statistiques_ecoles.xlsx", [
                    ("Nombre d'écoles", ent_nb, l_nb + [t_nb], {"titre_haut": th}),
                    ("Classement", ent, rows, {"titre_haut": th + [f"Classement par : {TRIS[tri].lower()}"]})])
            rows_pdf = [[("" if v is None else (nb_fr(v) if isinstance(v, float) else v)) for v in r] for r in rows]
            larg_nb = [60] + [28] * len(cols_nb) + [20, 25]
            return _pdf("STATISTIQUES DES ÉCOLES", ent, rows_pdf, flt, "statistiques_ecoles.pdf",
                        largeurs=[7, 42, 18, 8, 10, 22, 22, 8, 8, 10, 9, 11, 10, 11, 10, 10, 13], taille=6.8,
                        sous_titre=f"Classement par : {TRIS[tri].lower()}",
                        avant=[_sous_titre(f"1. Nombre d'écoles par type, secteur et {lib.lower()}"),
                               _mini(ent_nb, l_nb + [t_nb], larg_nb), _sous_titre("2. Classement des écoles")])
        return render_template("jur_stats_ecoles.html", flt=flt, lignes=classes_, grp=grp, tot=tot, par=par, lib_groupe=lib,
                               tri=tri, TRIS=TRIS, COLONNES_ECOLES=COLONNES_ECOLES, cles_nb=cles_nb,
                               args=args_filtres(flt, tri=tri), page="jur_stats_ecoles")

    # ------------------------------------------------------------------ 3. statistiques des effectifs
    @app.route("/juridiction/statistiques/effectifs")
    @H.connexion_requise()
    def jur_stats_effectifs():
        _garde()
        flt = lire_filtres()
        lignes = donnees(flt["annee"], flt["cs_id"], flt["zone_id"], flt["type"], flt["secteur"])
        par = flt["par"]
        lib = _lib_groupe(par)
        tot = agreger(lignes)
        niv, niv_tot = lignes_niveaux(effectifs_par_niveau(lignes))
        grp = []
        for _k, nom, ll in groupes(lignes, par):
            for sc, sl in J.SECTEURS.items():
                sous = [l for l in ll if l["secteur"] == sc]
                if sous:
                    grp.append({"nom": nom, "secteur": sl, "agg": agreger(sous)})
            grp.append({"nom": nom, "secteur": "Ensemble", "agg": agreger(ll), "st": "b"})
        npg = niveaux_par_groupe(lignes, par)
        rec = recensement_7(lignes)
        mat = tableau_ages([l for l in lignes if l["type"] in ("EM", "EE")], NIVEAUX_MAT, LIGNES_73M, _ligne_age_mat)
        pyr = pyramide_ages(lignes)
        exp = request.args.get("export")
        # --- tableaux communs (écran / Excel / PDF)
        ent_niv = ["Niveau", "Public G", "Public F", "Public T", "Privé G", "Privé F", "Privé T", "Ensemble G",
                   "Ensemble F", "Ensemble T", "% filles", "% garçons", "Indice de parité F/G", "Redoublants G",
                   "Redoublants F", "Redoublants T", "Taux de redoublement (%)"]

        def r_niv(n):
            return [n["niveau"]] + n["pub"] + n["pri"] + n["ens"] + [n["pct_f"], n["pct_g"], n["ip"]] + n["red"] + [n["t_red"]]

        ent_grp = [lib, "Secteur", "Écoles", "Classes", "G", "F", "Total", "% filles", "% garçons", "Indice de parité",
                   "Moyenne par classe", "Écart-type par classe", "Écart-type par école", "Classes pléthoriques",
                   "Redoublants", "Taux de redoublement (%)"]

        def r_grp(x):
            a = x["agg"]
            return [x["nom"], x["secteur"], a["ecoles"], a["classes"], a["g"], a["f"], a["t"], a["pct_f"], a["pct_g"],
                    a["ip"], a["moy_classe"], a["et_classes"], a["et_ecoles"], a["plethoriques"], a["redoublants"],
                    a["taux_redoublement"]]

        ent_npg = [lib] + [f"{n} {s}" for n in npg["niveaux"] for s in ("G", "F", "T")] + ["Total G", "Total F", "Total T"]
        rows_npg = [[nom] + [v for n in npg["niveaux"] for v in (d.get(n, [0, 0]) + [sum(d.get(n, [0, 0]))])] + t
                    for nom, d, t in npg["lignes"]]
        ent_73 = ["Âge"] + [f"{n} {s}" for n in NIVEAUX_EP + ["ENSEMBLE", "DONT E.H"] for s in ("G", "F", "T")]
        rows_73 = [[r["lib"]] + r["cols"] for r in rec["t73"]["lignes"]]
        ent_m = ["Âge"] + [f"{n} {s}" for n in NIVEAUX_MAT + ["ENSEMBLE", "DONT E.H"] for s in ("G", "F", "T")]
        rows_m = [[r["lib"]] + r["cols"] for r in mat["lignes"]]
        if exp == "xlsx":
            th = _titre_haut(flt, "Effectifs des apprenants")
            rec_rows = ([["7.1 Effectif global", "Masculin", rec["t71"][0]], ["", "Féminin", rec["t71"][1]],
                         ["", "Total", rec["t71"][2]], ["", "", ""], ["7.2 Nouveaux inscrits au CI", "G", "F", "T"]]
                        + [[r["lib"], r["g"], r["f"], r["t"]] for r in rec["t72"]]
                        + [["dont ayant suivi l'enseignement maternel", *rec["t72b"]]])
            feuilles = [("Par niveau", ent_niv, [r_niv(n) for n in niv] + ([r_niv(niv_tot)] if niv_tot else []), {"titre_haut": th}),
                        (f"Par {lib.lower()}", ent_grp, [r_grp(x) for x in grp] +
                         [r_grp({"nom": "Total", "secteur": "Ensemble", "agg": tot})], {"titre_haut": th}),
                        (f"Niveaux par {lib.lower()}", ent_npg, rows_npg, {"titre_haut": th}),
                        ("Recensement 7.1-7.2", ["Rubrique", "Valeur / G", "F", "T"], rec_rows,
                         {"titre_haut": th + ["Écoles primaires – tableau agrégé de la fiche de recensement"]}),
                        ("Recensement 7.3", ent_73, rows_73,
                         {"titre_haut": th + ["7.3 Répartition des élèves par âge, selon le genre et par année d'étude"]}),
                        ("Maternelle par âge", ent_m, rows_m, {"titre_haut": th + ["Maternelle et espaces enfance"]})]
            if pyr:
                feuilles.append(("Pyramide des âges", ["Âge", "Garçons", "Filles", "Total"],
                                 [[a, v[0], v[1], v[0] + v[1]] for a, v in sorted(pyr.items())], {"titre_haut": th}))
            return H.xlsx.reponse_classeur("effectifs_apprenants.xlsx", feuilles)
        if exp == "pdf":
            def f_(r):
                return ["" if v is None else (nb_fr(v) if isinstance(v, float) else v) for v in r]
            rows_n = [f_(r_niv(n)) for n in niv]
            l_grp = [f_(r_grp(x)) for x in grp]
            apres = [_sous_titre(f"2. Effectifs par {lib.lower()} et par secteur"),
                     _mini(ent_grp, l_grp + [f_(r_grp({"nom": "Total", "secteur": "Ensemble", "agg": tot}))],
                           [40, 18] + [15.3] * 14)]
            if rows_npg:
                n_n = len(npg["niveaux"])
                apres += [_sous_titre(f"3. Effectifs par niveau et par {lib.lower()}"),
                          _mini([_abr(x) for x in ent_npg], rows_npg, [36] + [237 / (3 * n_n + 3)] * (3 * n_n + 3), taille=6.3)]
            apres += [_sous_titre("4. Tableau des effectifs tel que la fiche de recensement (écoles primaires)"),
                      _mini(["7.1 Effectif global", "Masculin", "Féminin", "Total"], [["", *rec["t71"]]], [60, 30, 30, 30]),
                      _mini(["7.2 Nouveaux inscrits au CI – âge", "G", "F", "T"],
                            [[r["lib"], r["g"], r["f"], r["t"]] for r in rec["t72"]] +
                            [["ii. ayant suivi l'enseignement maternel", *rec["t72b"]]], [60, 30, 30, 30]),
                      _sous_titre("7.3 Répartition des élèves par âge, selon le genre et par année d'étude"),
                      _mini([_abr(x) for x in ent_73], rows_73, [33] + [10] * 24),
                      _sous_titre("5. Maternelle et espaces enfance : répartition par âge"),
                      _mini([_abr(x) for x in ent_m], rows_m, [33] + [16] * 15)]
            return _pdf("EFFECTIFS DES APPRENANTS", ent_niv, rows_n, flt, "effectifs_apprenants.pdf",
                        total=f_(r_niv(niv_tot)) if niv_tot else None, taille=7,
                        largeurs=[24] + [14] * 9 + [13, 13, 14, 14, 14, 14, 18],
                        avant=[_sous_titre("1. Effectifs par niveau, sexe et secteur")], apres=apres)
        return render_template("jur_stats_effectifs.html", flt=flt, tot=tot, niv=niv, niv_tot=niv_tot, grp=grp, npg=npg,
                               rec=rec, mat=mat, NIVEAUX_EP=NIVEAUX_EP, NIVEAUX_MAT=NIVEAUX_MAT, par=par, lib_groupe=lib,
                               graph_rep=svg_repartition(tot["g"], tot["f"]), graph_pyr=svg_pyramide(pyr),
                               graph_niv=svg_barres([n["niveau"] for n in niv],
                                                    [("Garçons", COULEUR_G, [n["ens"][0] for n in niv]),
                                                     ("Filles", COULEUR_F, [n["ens"][1] for n in niv])],
                                                    aria="Effectifs par niveau et par sexe"),
                               args=args_filtres(flt), page="jur_stats_effectifs")

    # ------------------------------------------------------------------ 4. statistiques des enseignants
    @app.route("/juridiction/statistiques/enseignants")
    @H.connexion_requise()
    def jur_stats_enseignants():
        _garde()
        flt = lire_filtres()
        lignes = donnees(flt["annee"], flt["cs_id"], flt["zone_id"], flt["type"], flt["secteur"], flt["q"])
        par = flt["par"]
        lib = _lib_groupe(par)
        tot = agreger(lignes)
        grp = [(k, nom, ll, agreger(ll)) for k, nom, ll in groupes(lignes, par)]
        manque = sorted([l for l in lignes if l["besoin"]["manque"]], key=lambda l: (-l["besoin"]["manque"], l["nom"]))
        surplus = sorted([l for l in lignes if l["besoin"]["surplus"]], key=lambda l: (-l["besoin"]["surplus"], l["nom"]))
        ent_g = [lib, "Écoles", "Enseignants", "Hommes", "Femmes", "% hommes", "% femmes", "Écart H-F"] + \
                [c[1] for c in CATEGORIES] + ["Besoin (groupes péd.)", "Tenant une classe", "Manque", "Surplus",
                                              "Élèves", "Élèves / enseignant"]

        def r_g(nom, a):
            e = a["ens"]
            return [nom, a["ecoles"], e["t"], e["h"], e["f"], e["pct_h"], e["pct_f"], e["ecart"]] + \
                   [e["par_categorie"].get(k, 0) for k, _ in CATEGORIES] + \
                   [e["besoin"], e["disponibles"], e["manque"], e["surplus"], a["t"], e["ratio"]]

        ent_e = ["École", "Type", "Secteur", "CS" if config.EDITION == "ddemp" else "Zone", "Enseignants", "H", "F"] + \
                [c[1] for c in CATEGORIES] + ["Besoin", "Tenant une classe", "Manque", "Surplus", "Élèves", "Élèves / ens."]

        def r_e(l):
            return [l["nom"], l["type"], J.SECTEURS[l["secteur"]], l["cs_nom"] if config.EDITION == "ddemp" else l["zone_nom"],
                    l["ens"]["t"], l["ens"]["h"], l["ens"]["f"]] + \
                   [l["ens"]["par_categorie"].get(k, 0) for k, _ in CATEGORIES] + \
                   [l["besoin"]["classes"], l["besoin"]["enseignants"], l["besoin"]["manque"], l["besoin"]["surplus"],
                    l["eff"]["t"], l["ratio"]]

        ent_m = ["École", "Type", "Secteur", "CS / zone", "Classes", "Tenant une classe", "Manque", "Surplus", "Directeur"]

        def r_m(l):
            return [l["nom"], l["type"], J.SECTEURS[l["secteur"]], " – ".join(x for x in (l["cs_nom"] if config.EDITION == "ddemp" else "", l["zone_nom"]) if x),
                    l["besoin"]["classes"], l["besoin"]["enseignants"], l["besoin"]["manque"], l["besoin"]["surplus"], l["directeur_nom"]]

        lignes_tri = sorted(lignes, key=lambda l: (l["cs_nom"], l["zone_nom"], l["nom"]))
        exp = request.args.get("export")
        if exp == "xlsx":
            th = _titre_haut(flt, "Enseignants : effectifs, besoins et écarts")
            return H.xlsx.reponse_classeur("statistiques_enseignants.xlsx", [
                (f"Par {lib.lower()}", ent_g, [r_g(nom, a) for _k, nom, _l, a in grp] + [r_g("Total", tot)], {"titre_haut": th}),
                ("Par école", ent_e, [r_e(l) for l in lignes_tri], {"titre_haut": th}),
                ("Écoles en manque", ent_m, [r_m(l) for l in manque], {"titre_haut": th}),
                ("Écoles en surplus", ent_m, [r_m(l) for l in surplus], {"titre_haut": th})])
        if exp == "pdf":
            def f_(r):
                return ["" if v is None else (nb_fr(v) if isinstance(v, float) else v) for v in r]
            apres = [_sous_titre("2. Effectifs d'enseignants par école"),
                     _mini(ent_e, [f_(r_e(l)) for l in lignes_tri], [52, 9, 12, 30] + [12] * 3 + [13] * 5 + [13] * 6)]
            if manque:
                apres += [_sous_titre(f"3. Écoles en manque d'enseignants ({len(manque)})"),
                          _mini(ent_m, [r_m(l) for l in manque], [60, 12, 15, 50, 16, 22, 16, 16, 66])]
            if surplus:
                apres += [_sous_titre(f"4. Écoles en surplus d'enseignants ({len(surplus)})"),
                          _mini(ent_m, [r_m(l) for l in surplus], [60, 12, 15, 50, 16, 22, 16, 16, 66])]
            return _pdf("ENSEIGNANTS : EFFECTIFS, BESOINS ET ÉCARTS", ent_g, [f_(r_g(nom, a)) for _k, nom, _l, a in grp], flt,
                        "statistiques_enseignants.pdf", total=f_(r_g("Total", tot)), taille=7,
                        largeurs=[34, 11, 14, 12, 12, 12, 12, 12] + [12] * 5 + [17, 15, 12, 12, 13, 15],
                        avant=[_sous_titre(f"1. Enseignants par {lib.lower()}")], apres=apres)
        return render_template("jur_stats_enseignants.html", flt=flt, tot=tot, grp=grp, lignes=lignes_tri, manque=manque,
                               surplus=surplus, par=par, lib_groupe=lib, CATEGORIES=CATEGORIES,
                               graph_ratio=svg_barres([g[1] for g in grp],
                                                      [("Élèves par enseignant", COULEUR_1, [g[3]["ens"]["ratio"] for g in grp])],
                                                      ref=tot["ens"]["ratio"], ref_lib="Ensemble :", aria="Élèves par enseignant"),
                               graph_hf=svg_barres([g[1] for g in grp],
                                                   [("Hommes", COULEUR_G, [g[3]["ens"]["h"] for g in grp]),
                                                    ("Femmes", COULEUR_F, [g[3]["ens"]["f"] for g in grp])],
                                                   aria="Enseignants hommes et femmes"),
                               args=args_filtres(flt), page="jur_stats_enseignants")
