# -*- coding: utf-8 -*-
"""Conseillers pédagogiques (CP) — applications « SCOLARIS Circonscription » (CS) et « SCOLARIS DDEMP » (v1.7).

Le module suit le travail du réseau d'animation pédagogique (RAP : le CCS et les CP des zones) et produit le
BILAN TRIMESTRIEL ET ANNUEL DES ACTIVITÉS PÉDAGOGIQUES, au niveau de la zone (un CP) ou de la CS (CCS + CP),
selon le canevas en usage dans les circonscriptions :

  1. Données statistiques sur le réseau d'animation pédagogique (écoles, sections/classes, enseignants H/F, UP)
  2. Activités pédagogiques menées : 2.1 visites/inspections de classes, 2.2 visites d'écoles, 2.3 suivis /
     encadrements D/EP et D/EM, 2.4 séances d'unité pédagogique, 2.5 formations groupées / conférences
  3. Activités du trimestre (suite) : 3.1 concertations, 3.2 autres activités menées
  4. Résultats / impact : taux de couverture
  5. Résultats de l'évaluation d'étape (inscrits, ont composé, maîtrise partielle / minimale, réussite, à renforcer)
  6. Analyse des résultats (quantitative, qualitative, genre, champs de formation, UP, conclusion)
     et problèmes majeurs identifiés / en voie de résolution
  7. Commentaires / analyse — signature du CCS (niveau CS) ou du CP (niveau zone)

Les chiffres sont CALCULÉS à partir des données de l'application :
  * écoles, classes, enseignants : fiches et paquets transmis par les écoles (a_tableau) ;
  * visites de classe / d'école / d'inspection du CCS et des CP : module « Visites d'école et de classe »
    (saisies de la CS, visites déclarées par les écoles, visites transmises à la DDEMP) ;
  * séances d'UP : module « Unités pédagogiques » ;
  * suivis des directeurs, formations, concertations, autres activités : journal des activités de ce module ;
  * activités programmées : programmation trimestrielle de ce module.
Tous les chiffres restent modifiables dans le bilan avant enregistrement (les pourcentages et totaux sont
recalculés). Boutons du bilan : Enregistrer, Charger (Excel), Télécharger (PDF, Excel), Réinitialiser, Supprimer.

Application CS : chaque bilan enregistré est recopié dans la section « cp_bilans » du paquet envoyé à la DDEMP,
qui les retrouve (lecture seule) dans sa liste des bilans.
"""
import io
import json
import re
import unicodedata
from datetime import date, datetime

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

import config
from db import ex, q

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_cp_conseillers (
    zone_id INTEGER PRIMARY KEY,           -- jur_zones.id (le nom et le téléphone du CP restent dans jur_zones)
    sexe TEXT, grade TEXT, nip TEXT, email TEXT, prise_service TEXT, observations TEXT, maj TEXT);
CREATE TABLE IF NOT EXISTS jur_cp_activites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cs_id INTEGER, zone_id INTEGER,       -- zone_id NULL : activité du CCS (C/CS)
    commune INTEGER DEFAULT 0,             -- 1 : activité commune à toute la CS (C/CS et tous les CP)
    annee TEXT NOT NULL, categorie TEXT NOT NULL, cycle TEXT, ecole_id INTEGER, lieu TEXT,
    date_debut TEXT, date_fin TEXT, designation TEXT, participants TEXT, nb INTEGER DEFAULT 1,
    beneficiaires_em INTEGER, beneficiaires_ep INTEGER,
    statut TEXT DEFAULT 'realisee', observations TEXT, cree_par INTEGER, cree_le TEXT, maj TEXT);
CREATE INDEX IF NOT EXISTS i_jur_cp_act ON jur_cp_activites(cs_id, annee, date_debut);
CREATE TABLE IF NOT EXISTS jur_cp_programmes (
    cs_id INTEGER NOT NULL, annee TEXT NOT NULL, periode TEXT NOT NULL, acteur TEXT NOT NULL,
    indicateur TEXT NOT NULL, valeur INTEGER, maj TEXT,
    PRIMARY KEY (cs_id, annee, periode, acteur, indicateur));
CREATE TABLE IF NOT EXISTS jur_cp_bilans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cs_id INTEGER NOT NULL, annee TEXT NOT NULL, periode TEXT NOT NULL,
    niveau TEXT NOT NULL DEFAULT 'cs',     -- cs | zone
    zone_id INTEGER NOT NULL DEFAULT 0,
    donnees TEXT NOT NULL, etat TEXT DEFAULT 'brouillon', source TEXT DEFAULT 'saisie',
    cree_par INTEGER, cree_le TEXT, maj TEXT,
    UNIQUE(cs_id, annee, periode, niveau, zone_id));
"""

RE_ANNEE = re.compile(r"^\d{4}-\d{4}$")
PERIODES = {
    "T1": ("Trimestre 1", "Septembre-Octobre-Novembre-Décembre"),
    "T2": ("Trimestre 2", "Janvier-Février-Mars"),
    "T3": ("Trimestre 3", "Avril-Mai-Juin"),
    "AN": ("Bilan annuel", "Septembre à juin"),
}
CATEGORIES = {
    "visite_classe": "Visite / inspection de classe",
    "visite_ecole": "Visite d'école",
    "suivi": "Suivi / encadrement de directeur (D/EP, D/EM)",
    "up": "Séance d'unité pédagogique (UP)",
    "formation": "Formation groupée / conférence pédagogique",
    "concertation": "Concertation",
    "autre": "Autre activité",
}
STATUTS = {"programmee": "Programmée", "preparee": "Préparée", "realisee": "Réalisée", "reportee": "Reportée / annulée"}
COURS = ["CP", "CE1", "CE2", "CM1", "CM2"]

# indicateurs de la programmation (2.x et 3.1) : (clé, libellé)
PROG = [("vc_em", "Visites/inspections de classes – EM"), ("vc_t", "Visites/inspections de classes – total (EM+EP)"),
        ("ve_em", "Visites d'écoles – EM"), ("ve_t", "Visites d'écoles – total (EM+EP)"),
        ("su_em", "Suivis / encadrements D/EM"), ("su_t", "Suivis / encadrements – total (D/EP + D/EM)"),
        ("up", "Séances d'UP programmées"), ("up_prep", "Séances d'UP préparées"),
        ("fo", "Formations groupées / conférences programmées"), ("co", "Concertations programmées")]
CLES_PROG = [k for k, _ in PROG]

# champs numériques du bilan par acteur
S1 = ["em_ecoles", "em_sections", "ep_ecoles", "ep_classes", "ens_em_h", "ens_em_f", "ens_ep_h", "ens_ep_f", "up_ep", "up_em"]
S2 = ["vc_prog_em", "vc_prog_t", "vc_real_em", "vc_real_t", "ve_prog_em", "ve_prog_t", "ve_real_em", "ve_real_t",
      "su_prog_em", "su_prog_t", "su_real_em", "su_real_t", "up_prog", "up_prep", "up_real", "fo_prog", "fo_real"]
S3 = ["co_prog", "co_real"]
S4 = ["vc_cible_em", "vc_cible_t", "ve_cible_em", "ve_cible_t", "su_cible_em", "su_cible_t",
      "fo_benef_em", "fo_benef_t", "fo_cible_em", "fo_cible_t"]
# indicateurs « événements communs » : le total n'est pas une somme (une même séance d'UP ou formation réunit tout le RAP)
COMMUNS = {"up_prog", "up_prep", "up_real", "fo_prog", "fo_real", "co_prog", "co_real"}
FORMATION = ("fo_benef_em", "fo_benef_t", "fo_cible_em", "fo_cible_t")
S5 = ["ins_g", "ins_f", "comp_g", "comp_f", "part_g", "part_f", "min_g", "min_f", "renf_math", "renf_fr"]
TEXTES = [("quantitative", "Analyse quantitative"), ("qualitative", "Analyse qualitative"),
          ("genre", "Analyse des écarts de genre"), ("disciplines", "Analyse des champs de formation / disciplines"),
          ("up", "Analyse selon les unités pédagogiques"), ("conclusion", "Conclusion")]


# ======================================================================== outils purs
def entier(v):
    s = str(v if v is not None else "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    try:
        return max(0, int(round(float(s.replace(",", ".")))))
    except ValueError:
        return None


def n0(v):
    return v or 0


def taux(a, b):
    return round(100.0 * a / b, 2) if b else None


def pct_txt(v):
    return "" if v is None else (f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " %")


def bornes(annee, periode):
    """Dates de début et de fin (ISO) d'une période de l'année scolaire « 2026-2027 »."""
    a1, a2 = (int(x) for x in annee.split("-"))
    return {"T1": (f"{a1}-09-01", f"{a1}-12-31"), "T2": (f"{a2}-01-01", f"{a2}-03-31"),
            "T3": (f"{a2}-04-01", f"{a2}-08-31"), "AN": (f"{a1}-08-15", f"{a2}-08-31")}[periode]


def annee_de(d):
    """Année scolaire d'une date ISO (de septembre à août)."""
    try:
        x = date.fromisoformat(str(d)[:10])
    except ValueError:
        return None
    return f"{x.year}-{x.year + 1}" if x.month >= 9 else f"{x.year - 1}-{x.year}"


def lire_date(v):
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            pass
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    return None


def date_fr(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return ""


def periode_txt(d1, d2):
    if d1 and d2 and d2 != d1:
        return f"Du {date_fr(d1)} au {date_fr(d2)}"
    return date_fr(d1)


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", t).split())


def lib_zone(nom):
    s = str(nom or "").strip()
    return f"CP Zone {s}" if s.isdigit() else ("CP " + s if s else "CP")


def em_de(typ):
    """Maternelle : écoles maternelles (EM) et espaces enfance (EE)."""
    return (typ or "").upper() in ("EM", "EE")


# ------------------------------------------------------------------ totaux et pourcentages (purs, testés)
def totaux(b):
    """Ajoute au bilan (dict) les lignes TOTAL CP et TOTAL CS et les pourcentages. Renvoie b."""
    act = b["acteurs"]
    cps = [a for a in act if a["cle"] != "ccs"]
    for sec, champs in (("s1", S1), ("s2", S2), ("s3", S3), ("s4", S4)):
        val = b.setdefault(sec, {})
        for a in act:
            val.setdefault(a["cle"], {})
            for c in champs:
                val[a["cle"]].setdefault(c, None)

        def cumul(lst, c):
            xs = [n0(val[a["cle"]].get(c)) for a in lst]
            if c in COMMUNS:
                return max(xs) if xs else 0
            return sum(xs)
        if sec == "s1":
            # C/CS = la circonscription entière : TOTAL CS = ligne C/CS si elle existe, sinon somme des zones
            tot = {c: (n0(val["ccs"].get(c)) if "ccs" in val and any(a["cle"] == "ccs" for a in act) else cumul(cps, c))
                   for c in champs}
            val["_tcp"] = {c: cumul(cps, c) for c in champs}
            val["_tcs"] = tot
        else:
            val["_tcp"] = {c: cumul(cps, c) for c in champs}
            val["_tcs"] = {c: cumul(act, c) for c in champs}
            if sec == "s4":
                # formation commune à toute la CS (mêmes bénéficiaires sur chaque ligne) : comptée une seule fois
                for cle_t, lst in (("_tcp", cps), ("_tcs", act)):
                    benef = {(n0(val[a["cle"]].get("fo_benef_em")), n0(val[a["cle"]].get("fo_benef_t"))) for a in lst}
                    if len(lst) > 1 and len(benef) == 1 and max(next(iter(benef))) > 0:
                        for c in FORMATION:
                            val[cle_t][c] = max(n0(val[a["cle"]].get(c)) for a in lst)
    # dérivés par ligne
    lignes = [a["cle"] for a in act] + ["_tcp", "_tcs"]
    s1, s2, s3, s4 = b["s1"], b["s2"], b["s3"], b["s4"]
    for k in lignes:
        r1 = s1.get(k) or {}
        r1["t_ecoles"] = n0(r1.get("em_ecoles")) + n0(r1.get("ep_ecoles"))
        r1["t_classes"] = n0(r1.get("em_sections")) + n0(r1.get("ep_classes"))
        r1["ens_em_t"] = n0(r1.get("ens_em_h")) + n0(r1.get("ens_em_f"))
        r1["ens_ep_t"] = n0(r1.get("ens_ep_h")) + n0(r1.get("ens_ep_f"))
        r1["ens_h"] = n0(r1.get("ens_em_h")) + n0(r1.get("ens_ep_h"))
        r1["ens_f"] = n0(r1.get("ens_em_f")) + n0(r1.get("ens_ep_f"))
        r1["ens_t"] = r1["ens_h"] + r1["ens_f"]
        r1["up_t"] = n0(r1.get("up_ep")) + n0(r1.get("up_em"))
        s1[k] = r1
        r2 = s2.get(k) or {}
        for p in ("vc", "ve", "su"):
            r2[f"{p}_pct_em"] = taux(n0(r2.get(f"{p}_real_em")), n0(r2.get(f"{p}_prog_em")))
            r2[f"{p}_pct_t"] = taux(n0(r2.get(f"{p}_real_t")), n0(r2.get(f"{p}_prog_t")))
        r2["up_pct"] = taux(n0(r2.get("up_real")), n0(r2.get("up_prog")))
        r2["fo_pct"] = taux(n0(r2.get("fo_real")), n0(r2.get("fo_prog")))
        s2[k] = r2
        r3 = s3.get(k) or {}
        r3["co_pct"] = taux(n0(r3.get("co_real")), n0(r3.get("co_prog")))
        s3[k] = r3
        r4 = s4.get(k) or {}
        r4["vc_cov_em"] = taux(n0(r2.get("vc_real_em")), n0(r4.get("vc_cible_em")))
        r4["vc_cov_t"] = taux(n0(r2.get("vc_real_t")), n0(r4.get("vc_cible_t")))
        r4["ve_cov_em"] = taux(n0(r2.get("ve_real_em")), n0(r4.get("ve_cible_em")))
        r4["ve_cov_t"] = taux(n0(r2.get("ve_real_t")), n0(r4.get("ve_cible_t")))
        r4["su_cov_em"] = taux(n0(r2.get("su_real_em")), n0(r4.get("su_cible_em")))
        r4["su_cov_t"] = taux(n0(r2.get("su_real_t")), n0(r4.get("su_cible_t")))
        r4["up_cov"] = r2["up_pct"]
        r4["fo_cov_em"] = taux(n0(r4.get("fo_benef_em")), n0(r4.get("fo_cible_em")))
        r4["fo_cov_t"] = taux(n0(r4.get("fo_benef_t")), n0(r4.get("fo_cible_t")))
        s4[k] = r4
    # 5. évaluation
    ev = b.setdefault("s5", {})
    lg = ev.setdefault("lignes", {})
    tot = {c: 0 for c in S5}
    for co in COURS:
        r = lg.setdefault(co, {})
        for c in S5:
            r.setdefault(c, None)
            tot[c] += n0(r.get(c))
    lg["TOTAL"] = {**{c: tot[c] for c in S5}, **{k: v for k, v in (lg.get("TOTAL") or {}).items() if k not in S5}}
    for co in COURS + ["TOTAL"]:
        r = lg[co]
        for x in ("ins", "comp", "part", "min"):
            r[f"{x}_t"] = n0(r.get(f"{x}_g")) + n0(r.get(f"{x}_f"))
        r["reu_g"] = taux(n0(r.get("min_g")), n0(r.get("comp_g")))
        r["reu_f"] = taux(n0(r.get("min_f")), n0(r.get("comp_f")))
        r["reu_t"] = taux(r["min_t"], r["comp_t"])
    return b


def analyse_auto(b):
    """Proposition de rédaction (6. Analyse des résultats) à partir des chiffres du bilan."""
    t = b["s5"]["lignes"]["TOTAL"]
    out = {}
    if t["ins_t"]:
        out["quantitative"] = (
            f"L'effectif total des élèves inscrits pour l'évaluation s'élève à {t['ins_t']} apprenants. "
            f"{t['comp_t']} élèves ont effectivement composé (Garçons : {t['comp_g']} ; Filles : {t['comp_f']}). "
            f"En termes de performance, {t['min_t']} apprenants ont atteint la maîtrise minimale, soit un taux global "
            f"de réussite de {pct_txt(t['reu_t'])} (Garçons : {pct_txt(t['reu_g'])} ; Filles : {pct_txt(t['reu_f'])})."
            + (f" De plus, {t['renf_fr']} apprenants sont à renforcer en Français et {t['renf_math']} en Mathématiques."
               if (t.get("renf_fr") or t.get("renf_math")) else ""))
        if t["reu_g"] is not None and t["reu_f"] is not None:
            ecart = round(abs(t["reu_f"] - t["reu_g"]), 2)
            if ecart < 0.5:
                out["genre"] = (f"Les performances des filles ({pct_txt(t['reu_f'])}) et des garçons "
                                f"({pct_txt(t['reu_g'])}) sont équivalentes.")
            else:
                plus, moins = (("les filles", "les garçons") if t["reu_f"] > t["reu_g"] else ("les garçons", "les filles"))
                out["genre"] = (f"Dans l'ensemble, {plus} sont plus performant(e)s que {moins} "
                                f"({pct_txt(max(t['reu_f'], t['reu_g']))} contre {pct_txt(min(t['reu_f'], t['reu_g']))}), "
                                f"soit un écart de {pct_txt(ecart).replace(' %', '')} point(s).")
        faibles = [co for co in COURS if b["s5"]["lignes"][co]["reu_t"] is not None and b["s5"]["lignes"][co]["reu_t"] < 50]
        if faibles:
            out["qualitative"] = ("Les cours suivants n'atteignent pas 50 % de réussite et appellent un renforcement : "
                                  + ", ".join(faibles) + ".")
    tc = b["s2"]["_tcs"]
    if tc.get("vc_prog_t"):
        out.setdefault("conclusion", (
            f"Au cours de la période, le RAP a réalisé {tc['vc_real_t'] or 0} visite(s)/inspection(s) de classe sur "
            f"{tc['vc_prog_t']} programmée(s) ({pct_txt(tc['vc_pct_t'])}), {tc['ve_real_t'] or 0} visite(s) d'école et "
            f"{tc['su_real_t'] or 0} suivi(s) de directeurs."))
    return out


# ======================================================================== module Flask
def enregistrer(app, H):
    H.schema(SCHEMA)

    def juridiction_ou_404():
        if not config.juridiction():
            abort(404)

    def saisie():
        return H.peut("jur_cp_bilan")

    def exiger_saisie():
        if not saisie():
            abort(403)

    def cs_courante_id():
        c = H.jur_cs_courante() if config.EDITION == "cs" else None
        return c["id"] if c else None

    def annee_demandee(args):
        a = (args.get("annee") or "").strip()
        return a if RE_ANNEE.match(a) else H.jur_annee()

    def periode_demandee(args):
        p = (args.get("periode") or "").strip().upper()
        if p in PERIODES:
            return p
        m = date.today().month
        return "T1" if m >= 9 or m < 1 else ("T2" if m <= 3 else "T3")

    def annees_dispo():
        a = set(H.jur_annees()) | {H.jur_annee()}
        a |= {r["annee"] for r in q("SELECT DISTINCT annee FROM jur_cp_bilans")}
        a |= {r["annee"] for r in q("SELECT DISTINCT annee FROM jur_cp_activites")}
        return sorted(a, reverse=True)

    def cs_demandee(args):
        """CS : la sienne ; DDEMP : celle choisie (paramètre cs), sinon la première."""
        if config.EDITION == "cs":
            return cs_courante_id()
        cid = args.get("cs", type=int)
        lst = H.jur_cs_liste()
        if cid and any(c["id"] == cid for c in lst):
            return cid
        return lst[0]["id"] if lst else None

    def zones_cs(cs_id):
        return [dict(z) for z in H.jur_zones(cs_id)] if cs_id else []

    def acteurs_de(cs_id, zone_id=None):
        """Lignes du bilan : C/CS puis un CP par zone (ou la seule zone demandée)."""
        cs = H.jur_cs(cs_id) if cs_id else None
        out = [] if zone_id else [{"cle": "ccs", "lib": "C/CS", "nom": (cs["ccs_nom"] if cs and cs["ccs_nom"] else "")
                                   or (H.jur_structure() or {}).get("responsable_nom") or "", "zone_id": None}]
        for z in zones_cs(cs_id):
            if zone_id and z["id"] != zone_id:
                continue
            out.append({"cle": f"z{z['id']}", "lib": lib_zone(z["nom"]), "nom": z["cp_nom"] or "", "zone_id": z["id"],
                        "zone": z["nom"], "telephone": z["cp_telephone"] or ""})
        return out

    def ecoles_cs(cs_id):
        return {e["id"]: dict(e) for e in H.jur_ecoles(cs_id=cs_id)} if cs_id else {}

    def acteur_de_zone(zone_id, zones_ok):
        return f"z{zone_id}" if zone_id and zone_id in zones_ok else None

    # ------------------------------------------------------------------ calcul
    def calculer(annee, periode, cs_id, zone_id=None):
        d1, d2 = bornes(annee, periode)
        act = acteurs_de(cs_id, zone_id)
        cles = {a["cle"] for a in act}
        zones_ok = {a["zone_id"] for a in act if a["zone_id"]}
        ecs = ecoles_cs(cs_id)
        b = {"annee": annee, "periode": periode, "cs_id": cs_id, "niveau": "zone" if zone_id else "cs",
             "zone_id": zone_id or 0, "acteurs": act, "s1": {}, "s2": {}, "s3": {}, "s4": {},
             "autres": [], "s5": {"etape": "1", "lignes": {}}, "textes": {}, "problemes": [], "commentaires": ""}
        s1 = {a["cle"]: {c: 0 for c in S1} for a in act}
        s2 = {a["cle"]: {c: 0 for c in S2} for a in act}
        s3 = {a["cle"]: {c: 0 for c in S3} for a in act}
        s4 = {a["cle"]: {c: 0 for c in S4} for a in act}

        def cibles_de(e_zone):
            out = ["ccs"] if "ccs" in cles else []
            k = acteur_de_zone(e_zone, zones_ok)
            if k:
                out.append(k)
            return out

        # 1. réseau : écoles, sections / classes, enseignants (paquets des écoles), UP
        try:
            import a_tableau
            lignes = a_tableau.donnees(annee, cs_id=cs_id)
        except Exception:  # noqa: BLE001 — module absent ou données incomplètes : on garde les écoles seules
            lignes = [{"id": e["id"], "type": e["type"], "zone_id": e["zone_id"], "eff": {"classes": 0},
                       "ens": {"h": 0, "f": 0}} for e in ecs.values()]
        inscrits = {co: [0, 0] for co in COURS}
        for l in lignes:
            em = em_de(l["type"])
            for k in cibles_de(l["zone_id"]):
                r = s1[k]
                r["em_ecoles" if em else "ep_ecoles"] += 1
                r["em_sections" if em else "ep_classes"] += n0((l.get("eff") or {}).get("classes"))
                r["ens_em_h" if em else "ens_ep_h"] += n0((l.get("ens") or {}).get("h"))
                r["ens_em_f" if em else "ens_ep_f"] += n0((l.get("ens") or {}).get("f"))
            if not em and (not zone_id or l["zone_id"] == zone_id):
                for cl in ((l.get("_sec_eff") or {}).get("classes") or []):
                    niv = norm(cl.get("niveau")).replace(" ", "")
                    if niv in inscrits:
                        inscrits[niv][0] += n0(entier(cl.get("garcons")))
                        inscrits[niv][1] += n0(entier(cl.get("filles")))
        try:
            ups = q("SELECT u.*, e.type ecole_type FROM jur_up u LEFT JOIN jur_ecoles e ON e.id=u.ecole_id "
                    "WHERE u.actif=1 AND u.cs_id=?", (cs_id,))
        except Exception:  # noqa: BLE001
            ups = []
        for u in ups:
            for k in cibles_de(u["zone_id"]):
                s1[k]["up_em" if em_de(u["ecole_type"]) else "up_ep"] += 1

        # 2.1 / 2.2 visites (CCS → C/CS ; CP → zone de l'école visitée, ou zone dont il est le CP)
        cp_zone = {norm(a["nom"]): a["cle"] for a in act if a["zone_id"] and a["nom"]}
        visites = []
        if getattr(H, "jur_visites_collecter", None):
            try:
                visites = H.jur_visites_collecter(annee, cs_id)
            except Exception:  # noqa: BLE001
                visites = []
        for v in visites:
            if not (d1 <= (v.get("date") or "") <= d2) or v.get("qualite") not in ("CP", "CCS"):
                continue
            e = ecs.get(v.get("ecole_id"))
            em = em_de(e["type"]) if e else False
            if v["qualite"] == "CCS":
                k = "ccs" if "ccs" in cles else None
            else:
                k = acteur_de_zone(v.get("zone_id") or (e or {}).get("zone_id"), zones_ok) or cp_zone.get(norm(v.get("visiteur")))
            if not k or k not in s2:
                continue
            p = "ve" if v.get("type") == "ecole" else "vc"
            s2[k][f"{p}_real_t"] += 1
            if em:
                s2[k][f"{p}_real_em"] += 1

        # activités du journal
        acts = q("SELECT a.*, e.type ecole_type FROM jur_cp_activites a LEFT JOIN jur_ecoles e ON e.id=a.ecole_id "
                 "WHERE a.cs_id=? AND a.annee=? AND a.date_debut BETWEEN ? AND ? ORDER BY a.date_debut, a.id",
                 (cs_id, annee, d1, d2))
        prevus = {a["cle"]: {c: 0 for c in CLES_PROG} for a in act}
        fo_communes = set()                               # lignes dont les bénéficiaires viennent d'une formation de toute la CS
        distincts = {}                                    # événements communs : séances distinctes par acteur

        def lignes_de(a):
            if a["commune"]:
                return list(cles)
            if a["zone_id"]:
                k = acteur_de_zone(a["zone_id"], zones_ok)
                return [k] if k else []
            return ["ccs"] if "ccs" in cles else []

        for a in acts:
            nb = max(1, n0(a["nb"]))
            em = (a["cycle"] or "").upper() == "EM" or em_de(a["ecole_type"])
            cat, st = a["categorie"], a["statut"] or "realisee"
            for k in lignes_de(a):
                if cat in ("visite_classe", "visite_ecole", "suivi"):
                    p = {"visite_classe": "vc", "visite_ecole": "ve", "suivi": "su"}[cat]
                    if st != "reportee":
                        prevus[k][f"{p}_t"] += nb
                        if em:
                            prevus[k][f"{p}_em"] += nb
                    if st == "realisee":
                        s2[k][f"{p}_real_t"] += nb
                        if em:
                            s2[k][f"{p}_real_em"] += nb
                elif cat in ("up", "formation", "concertation"):
                    p = {"up": "up", "formation": "fo", "concertation": "co"}[cat]
                    ev = (a["date_debut"], norm(a["designation"]), a["id"] if not a["commune"] else 0)
                    dd = distincts.setdefault(k, {}).setdefault(p, {"prog": set(), "prep": set(), "real": set()})
                    if st != "reportee":
                        dd["prog"].add(ev)
                    if st in ("preparee", "realisee"):
                        dd["prep"].add(ev)
                    if st == "realisee":
                        dd["real"].add(ev)
                        if cat == "formation":
                            s4[k]["fo_benef_em"] += n0(a["beneficiaires_em"])
                            s4[k]["fo_benef_t"] += n0(a["beneficiaires_em"]) + n0(a["beneficiaires_ep"])
                            if a["commune"]:
                                fo_communes.add(k)
            if a["categorie"] == "autre" and a["statut"] == "realisee" and (not zone_id or lignes_de(a)):
                b["autres"].append({"lieu": a["lieu"] or "", "periode": periode_txt(a["date_debut"], a["date_fin"]),
                                    "designation": a["designation"] or "", "participants": a["participants"] or ""})
        # séances d'UP du module « Unités pédagogiques »
        try:
            seances = q("SELECT x.*, u.zone_id FROM jur_up_activites x JOIN jur_up u ON u.id=x.up_id "
                        "WHERE u.cs_id=? AND u.actif=1 AND x.date BETWEEN ? AND ?", (cs_id, d1, d2))
        except Exception:  # noqa: BLE001
            seances = []
        for x in seances:
            ev = (x["date"], norm(x["theme"]))
            for k in cibles_de(x["zone_id"]):
                dd = distincts.setdefault(k, {}).setdefault("up", {"prog": set(), "prep": set(), "real": set()})
                if x["prevue"]:
                    dd["prog"].add(ev)
                if x["executee"]:
                    dd["prep"].add(ev)
                    dd["real"].add(ev)
        for k, par in distincts.items():
            for p, dd in par.items():
                prevus[k][p] = len(dd["prog"])
                if p == "up":
                    prevus[k]["up_prep"] = len(dd["prep"])
                    s2[k]["up_real"] = len(dd["real"])
                elif p == "fo":
                    s2[k]["fo_real"] = len(dd["real"])
                else:
                    s3[k]["co_real"] = len(dd["real"])

        # programmation saisie (prioritaire) : trimestre, ou somme des trois trimestres pour le bilan annuel
        prog = {}
        pers = ("T1", "T2", "T3") if periode == "AN" else (periode,)
        for r in q("SELECT * FROM jur_cp_programmes WHERE cs_id=? AND annee=? AND periode IN (%s)"
                   % ",".join("?" * len(pers)), (cs_id, annee, *pers)):
            if r["valeur"] is not None and r["acteur"] in prevus:
                prog.setdefault(r["acteur"], {}).setdefault(r["indicateur"], 0)
                prog[r["acteur"]][r["indicateur"]] += r["valeur"]
        for k in prevus:
            pv = {**prevus[k], **prog.get(k, {})}
            r = s2[k]
            r["vc_prog_em"], r["vc_prog_t"] = pv["vc_em"], pv["vc_t"]
            r["ve_prog_em"], r["ve_prog_t"] = pv["ve_em"], pv["ve_t"]
            r["su_prog_em"], r["su_prog_t"] = pv["su_em"], pv["su_t"]
            r["up_prog"], r["up_prep"], r["fo_prog"] = pv["up"], pv["up_prep"], pv["fo"]
            s3[k]["co_prog"] = pv["co"]
            # 4. bases de calcul des taux de couverture
            x = s1[k]
            s4[k]["vc_cible_em"] = x["em_sections"]
            s4[k]["vc_cible_t"] = x["em_sections"] + x["ep_classes"]
            s4[k]["ve_cible_em"] = s4[k]["su_cible_em"] = x["em_ecoles"]
            s4[k]["ve_cible_t"] = s4[k]["su_cible_t"] = x["em_ecoles"] + x["ep_ecoles"]
            # formation commune à toute la CS : les bénéficiaires se rapportent aux enseignants de toute la CS
            base = s1["ccs"] if (k in fo_communes and "ccs" in s1) else x
            s4[k]["fo_cible_em"] = base["ens_em_h"] + base["ens_em_f"]
            s4[k]["fo_cible_t"] = base["ens_em_h"] + base["ens_em_f"] + base["ens_ep_h"] + base["ens_ep_f"]
        b["s1"], b["s2"], b["s3"], b["s4"] = s1, s2, s3, s4
        b["s5"]["lignes"] = {co: {**{c: None for c in S5}, "ins_g": inscrits[co][0] or None, "ins_f": inscrits[co][1] or None}
                             for co in COURS}
        totaux(b)
        b["textes"] = analyse_auto(b)
        s = H.jur_structure() or {}
        cs = H.jur_cs(cs_id) if cs_id else None
        b["entete"] = {"departement": s.get("departement") or (cs["departement"] if cs else ""),
                       "cs": (cs["nom"] if cs else "") or s.get("cs") or "", "lieu_date": "",
                       "titre_sig": ("Le Conseiller Pédagogique" if zone_id else (s.get("responsable_titre") or "Le CCS")),
                       "nom_sig": (act[0]["nom"] if zone_id and act else ((cs["ccs_nom"] if cs else "") or s.get("responsable_nom") or ""))}
        return b

    # ------------------------------------------------------------------ lecture / écriture des bilans
    def bilan_ligne(cs_id, annee, periode, zone_id):
        return q("SELECT * FROM jur_cp_bilans WHERE cs_id=? AND annee=? AND periode=? AND niveau=? AND zone_id=?",
                 (cs_id, annee, periode, "zone" if zone_id else "cs", zone_id or 0), un=True)

    def fusionner(calc, enr):
        """Bilan enregistré (saisies) appliqué sur le bilan calculé, puis totaux recalculés."""
        b = json.loads(json.dumps(calc))
        if not enr:
            return b
        for sec in ("s1", "s2", "s3", "s4"):
            for k, vals in (enr.get(sec) or {}).items():
                if k in b[sec] and not k.startswith("_"):
                    for c, v in vals.items():
                        if c in b[sec][k] and c in (S1 + S2 + S3 + S4):
                            b[sec][k][c] = v
        for co, vals in ((enr.get("s5") or {}).get("lignes") or {}).items():
            if co in b["s5"]["lignes"]:
                for c, v in vals.items():
                    if c in S5:
                        b["s5"]["lignes"][co][c] = v
        if (enr.get("s5") or {}).get("etape"):
            b["s5"]["etape"] = enr["s5"]["etape"]
        for cle in ("autres", "problemes"):
            if cle in enr:
                b[cle] = enr[cle]
        if "commentaires" in enr:
            b["commentaires"] = enr["commentaires"]
        b["textes"].update({k: v for k, v in (enr.get("textes") or {}).items() if k in dict(TEXTES)})
        b["entete"].update({k: v for k, v in (enr.get("entete") or {}).items() if k in b["entete"]})
        return totaux(b)

    def lire_formulaire(f, b):
        """Formulaire du bilan → dict des saisies (même forme que le bilan)."""
        out = {"s1": {}, "s2": {}, "s3": {}, "s4": {}, "s5": {"etape": (f.get("s5_etape") or "1").strip()[:10], "lignes": {}},
               "textes": {}, "entete": {}}
        for sec, champs in (("s1", S1), ("s2", S2), ("s3", S3), ("s4", S4)):
            for a in b["acteurs"]:
                out[sec][a["cle"]] = {c: entier(f.get(f"{sec}_{a['cle']}_{c}")) for c in champs}
        for co in COURS:
            out["s5"]["lignes"][co] = {c: entier(f.get(f"s5_{co}_{c}")) for c in S5}
        out["autres"] = [{"lieu": (lieu or "").strip()[:120], "periode": (per or "").strip()[:80],
                          "designation": (des or "").strip()[:500], "participants": (par or "").strip()[:200]}
                         for lieu, per, des, par in zip(f.getlist("au_lieu"), f.getlist("au_periode"),
                                                        f.getlist("au_designation"), f.getlist("au_participants"))
                         if (des or "").strip() or (lieu or "").strip()]
        out["problemes"] = [{"designation": (d or "").strip()[:500], "ampleur": (a or "").strip()[:20],
                             "observations": (o or "").strip()[:1000]}
                            for d, a, o in zip(f.getlist("pb_designation"), f.getlist("pb_ampleur"), f.getlist("pb_observations"))
                            if (d or "").strip()]
        out["textes"] = {k: (f.get(f"tx_{k}") or "").strip()[:4000] for k, _ in TEXTES}
        out["commentaires"] = (f.get("commentaires") or "").strip()[:4000]
        out["entete"] = {k: (f.get(f"en_{k}") or "").strip()[:150] for k in ("lieu_date", "titre_sig", "nom_sig")}
        return out

    def synchroniser(cs_id, annee):
        """CS : les bilans de l'année vont dans la section « cp_bilans » du paquet envoyé à la DDEMP."""
        if config.EDITION != "cs" or not cs_id:
            return
        rows = q("SELECT * FROM jur_cp_bilans WHERE cs_id=? AND annee=? AND source='saisie' ORDER BY periode, niveau, zone_id",
                 (cs_id, annee))
        lst = []
        for r in rows:
            try:
                d, _ = bilan_complet(annee, r["periode"], cs_id, r["zone_id"] or None)   # bilan complet (calcul + saisies)
            except Exception:  # noqa: BLE001 — zone supprimée depuis, données illisibles
                continue
            lst.append({"periode": r["periode"], "niveau": r["niveau"], "zone": next(
                (a.get("zone") for a in d.get("acteurs", []) if a.get("zone_id") == r["zone_id"]), ""),
                "etat": r["etat"], "maj": r["maj"], "bilan": d})
        H.jur_ecrire_cs_section(cs_id, "cp_bilans", lst, annee)

    def recus_ddemp(annee, cs_id=None):
        """DDEMP : bilans transmis par les CS (section « cp_bilans » de leurs paquets)."""
        if config.EDITION != "ddemp":
            return []
        out = []
        for c in H.jur_cs_liste():
            if cs_id and c["id"] != cs_id:
                continue
            for i, it in enumerate(H.jur_cs_section(c["id"], "cp_bilans", annee) or []):
                if isinstance(it, dict) and isinstance(it.get("bilan"), dict):
                    out.append({"cs_id": c["id"], "cs_nom": c["nom"], "index": i, **{k: it.get(k) for k in
                                                                                     ("periode", "niveau", "zone", "etat", "maj")}})
        return out

    def bilan_recu(cs_id, annee, index):
        lst = H.jur_cs_section(cs_id, "cp_bilans", annee) or []
        if not (0 <= index < len(lst)) or not isinstance(lst[index], dict):
            abort(404)
        return totaux(lst[index]["bilan"])

    # ------------------------------------------------------------------ accueil du module
    @app.route("/juridiction/conseillers")
    @H.connexion_requise()
    def jur_cp_accueil():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        cs_id = cs_demandee(request.args)
        zones = zones_cs(cs_id)
        fiches = {r["zone_id"]: dict(r) for r in q("SELECT * FROM jur_cp_conseillers")}
        ecs = ecoles_cs(cs_id)
        par_zone = {}
        for e in ecs.values():
            par_zone.setdefault(e["zone_id"], {"EP": 0, "EM": 0})
            par_zone[e["zone_id"]]["EM" if em_de(e["type"]) else "EP"] += 1
        for z in zones:
            z["fiche"] = fiches.get(z["id"], {})
            z["ecoles"] = par_zone.get(z["id"], {"EP": 0, "EM": 0})
        bilans = q("SELECT * FROM jur_cp_bilans WHERE cs_id=? AND annee=? ORDER BY periode, niveau, zone_id",
                   (cs_id, annee)) if cs_id else []
        nb_act = q("SELECT COUNT(*) n FROM jur_cp_activites WHERE cs_id=? AND annee=?", (cs_id, annee), un=True)["n"] if cs_id else 0
        return render_template("jur_cp_accueil.html", annee=annee, annees=annees_dispo(), cs=H.jur_cs_liste(), cs_id=cs_id,
                               zones=zones, bilans=bilans, nb_act=nb_act, saisie=saisie(), PERIODES=PERIODES,
                               recus=recus_ddemp(annee, cs_id), lib_zone=lib_zone, periode=periode_demandee(request.args))

    @app.route("/juridiction/conseillers/<int:zid>", methods=["POST"])
    @H.connexion_requise("jur_cp_bilan")
    def jur_cp_conseiller(zid):
        juridiction_ou_404()
        z = q("SELECT * FROM jur_zones WHERE id=?", (zid,), un=True)
        if not z:
            abort(404)
        if config.EDITION == "cs" and z["cs_id"] != cs_courante_id():
            abort(403)
        f = request.form
        ex("UPDATE jur_zones SET cp_nom=?, cp_telephone=? WHERE id=?",
           ((f.get("cp_nom") or "").strip()[:150], (f.get("cp_telephone") or "").strip()[:40], zid))
        ex("""INSERT INTO jur_cp_conseillers (zone_id, sexe, grade, nip, email, prise_service, observations, maj)
              VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(zone_id) DO UPDATE SET sexe=excluded.sexe, grade=excluded.grade,
              nip=excluded.nip, email=excluded.email, prise_service=excluded.prise_service,
              observations=excluded.observations, maj=excluded.maj""",
           (zid, (f.get("sexe") or "")[:1], (f.get("grade") or "").strip()[:60], (f.get("nip") or "").strip()[:30],
            (f.get("email") or "").strip()[:120], lire_date(f.get("prise_service")) or "",
            (f.get("observations") or "").strip()[:500], H.maintenant()))
        H.journal("jur_cp_conseiller", f"zone {zid}")
        flash(f"Conseiller pédagogique de la zone « {z['nom']} » enregistré.", "success")
        return redirect(url_for("jur_cp_accueil", annee=request.args.get("annee"), cs=z["cs_id"] if config.EDITION == "ddemp" else None))

    # ------------------------------------------------------------------ programmation trimestrielle
    @app.route("/juridiction/conseillers/programmation", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_cp_programmation():
        juridiction_ou_404()
        annee = annee_demandee(request.values)
        periode = periode_demandee(request.values)
        if periode == "AN":
            periode = "T1"
        cs_id = cs_demandee(request.values)
        if not cs_id:
            flash("Configurez d'abord la circonscription et ses zones pédagogiques.", "warning")
            return redirect(url_for("jur_cp_accueil"))
        act = acteurs_de(cs_id)
        if request.method == "POST":
            exiger_saisie()
            action = request.form.get("action")
            if action == "reinitialiser":
                ex("DELETE FROM jur_cp_programmes WHERE cs_id=? AND annee=? AND periode=?", (cs_id, annee, periode))
                flash(f"Programmation du {PERIODES[periode][0].lower()} réinitialisée.", "success")
            else:
                for a in act:
                    for k in CLES_PROG:
                        v = entier(request.form.get(f"p_{a['cle']}_{k}"))
                        ex("""INSERT INTO jur_cp_programmes (cs_id, annee, periode, acteur, indicateur, valeur, maj)
                              VALUES (?,?,?,?,?,?,?) ON CONFLICT(cs_id, annee, periode, acteur, indicateur)
                              DO UPDATE SET valeur=excluded.valeur, maj=excluded.maj""",
                           (cs_id, annee, periode, a["cle"], k, v, H.maintenant()))
                flash("Programmation enregistrée.", "success")
            H.journal("jur_cp_programmation", f"{annee} {periode} {action or 'enregistrer'}")
            return redirect(url_for("jur_cp_programmation", annee=annee, periode=periode,
                                    cs=cs_id if config.EDITION == "ddemp" else None))
        vals = {}
        for r in q("SELECT * FROM jur_cp_programmes WHERE cs_id=? AND annee=? AND periode=?", (cs_id, annee, periode)):
            vals.setdefault(r["acteur"], {})[r["indicateur"]] = r["valeur"]
        return render_template("jur_cp_programmation.html", annee=annee, annees=annees_dispo(), periode=periode,
                               PERIODES={k: v for k, v in PERIODES.items() if k != "AN"}, cs=H.jur_cs_liste(), cs_id=cs_id,
                               acteurs=act, vals=vals, PROG=PROG, saisie=saisie())

    @app.route("/juridiction/conseillers/programmation.xlsx")
    @H.connexion_requise()
    def jur_cp_programmation_xlsx():
        juridiction_ou_404()
        annee, periode, cs_id = annee_demandee(request.args), periode_demandee(request.args), cs_demandee(request.args)
        if periode == "AN":
            periode = "T1"
        act = acteurs_de(cs_id)
        vals = {}
        for r in q("SELECT * FROM jur_cp_programmes WHERE cs_id=? AND annee=? AND periode=?", (cs_id, annee, periode)):
            vals.setdefault(r["acteur"], {})[r["indicateur"]] = r["valeur"]
        X = Excel()
        ws = X.feuille("Programmation", f"PROGRAMMATION DES ACTIVITÉS PÉDAGOGIQUES – {PERIODES[periode][0].upper()} "
                                        f"({PERIODES[periode][1]}) – {annee}", entete_doc())
        X.tableau(ws, ["Acteurs du RAP"] + [lib for _, lib in PROG], ["acteur"] + CLES_PROG,
                  [[a["cle"], a["lib"] + (f" ({a['nom']})" if a["nom"] else "")] + [vals.get(a["cle"], {}).get(k) for k in CLES_PROG]
                   for a in act], editable=set(CLES_PROG))
        return X.reponse(f"programmation_cp_{annee}_{periode}.xlsx")

    @app.route("/juridiction/conseillers/programmation/import", methods=["POST"])
    @H.connexion_requise("jur_cp_bilan")
    def jur_cp_programmation_import():
        juridiction_ou_404()
        annee, periode, cs_id = annee_demandee(request.form), periode_demandee(request.form), cs_demandee(request.form)
        if periode == "AN":
            periode = "T1"
        lignes = lire_classeur(request.files.get("fichier"), "Programmation")
        if lignes is None:
            flash("Fichier illisible : utilisez le modèle « Télécharger (Excel) » de cette page.", "danger")
        else:
            cles = {a["cle"] for a in acteurs_de(cs_id)}
            n = 0
            for r in lignes:
                k = r.get("acteur")
                if k not in cles:
                    continue
                for ind in CLES_PROG:
                    if ind in r:
                        ex("""INSERT INTO jur_cp_programmes (cs_id, annee, periode, acteur, indicateur, valeur, maj)
                              VALUES (?,?,?,?,?,?,?) ON CONFLICT(cs_id, annee, periode, acteur, indicateur)
                              DO UPDATE SET valeur=excluded.valeur, maj=excluded.maj""",
                           (cs_id, annee, periode, k, ind, entier(r[ind]), H.maintenant()))
                n += 1
            flash(f"Programmation chargée : {n} acteur(s).", "success" if n else "warning")
        return redirect(url_for("jur_cp_programmation", annee=annee, periode=periode, cs=cs_id if config.EDITION == "ddemp" else None))

    # ------------------------------------------------------------------ journal des activités
    def activite_ou_404(aid):
        a = q("SELECT * FROM jur_cp_activites WHERE id=?", (aid,), un=True)
        if not a or (config.EDITION == "cs" and a["cs_id"] != cs_courante_id()):
            abort(404)
        return a

    @app.route("/juridiction/conseillers/activites")
    @H.connexion_requise()
    def jur_cp_activites():
        juridiction_ou_404()
        annee, periode, cs_id = annee_demandee(request.args), periode_demandee(request.args), cs_demandee(request.args)
        d1, d2 = bornes(annee, periode)
        cat = request.args.get("categorie") or ""
        sql = ("SELECT a.*, z.nom zone_nom, z.cp_nom, e.nom ecole_nom FROM jur_cp_activites a LEFT JOIN jur_zones z ON z.id=a.zone_id "
               "LEFT JOIN jur_ecoles e ON e.id=a.ecole_id WHERE a.cs_id=? AND a.annee=? AND a.date_debut BETWEEN ? AND ?")
        args = [cs_id, annee, d1, d2]
        if cat in CATEGORIES:
            sql += " AND a.categorie=?"
            args.append(cat)
        acts = q(sql + " ORDER BY a.date_debut DESC, a.id DESC", tuple(args)) if cs_id else []
        return render_template("jur_cp_activites.html", annee=annee, annees=annees_dispo(), periode=periode, PERIODES=PERIODES,
                               cs=H.jur_cs_liste(), cs_id=cs_id, acts=acts, CATEGORIES=CATEGORIES, STATUTS=STATUTS,
                               categorie=cat, saisie=saisie(), date_fr=date_fr, lib_zone=lib_zone)

    @app.route("/juridiction/conseillers/activites/nouvelle", methods=["GET", "POST"])
    @app.route("/juridiction/conseillers/activites/<int:aid>", methods=["GET", "POST"])
    @H.connexion_requise("jur_cp_bilan")
    def jur_cp_activite_form(aid=None):
        juridiction_ou_404()
        a = activite_ou_404(aid) if aid else None
        cs_id = a["cs_id"] if a else cs_demandee(request.values)
        if not cs_id:
            abort(404)
        if request.method == "POST":
            f = request.form
            err = []
            d = {"categorie": f.get("categorie"), "statut": f.get("statut") or "realisee",
                 "cycle": (f.get("cycle") or "").upper() if (f.get("cycle") or "").upper() in ("EM", "EP") else "",
                 "lieu": (f.get("lieu") or "").strip()[:150], "designation": (f.get("designation") or "").strip()[:600],
                 "participants": (f.get("participants") or "").strip()[:300], "nb": max(1, entier(f.get("nb")) or 1),
                 "beneficiaires_em": entier(f.get("beneficiaires_em")), "beneficiaires_ep": entier(f.get("beneficiaires_ep")),
                 "observations": (f.get("observations") or "").strip()[:2000],
                 "date_debut": lire_date(f.get("date_debut")), "date_fin": lire_date(f.get("date_fin")) or None,
                 "commune": 1 if f.get("acteur") == "commune" else 0}
            act = f.get("acteur") or "ccs"
            d["zone_id"] = int(act[1:]) if act.startswith("z") and act[1:].isdigit() else None
            if d["zone_id"] and not q("SELECT 1 FROM jur_zones WHERE id=? AND cs_id=?", (d["zone_id"], cs_id), un=True):
                err.append("Zone pédagogique inconnue dans cette circonscription.")
            if d["categorie"] not in CATEGORIES:
                err.append("Choisissez la nature de l'activité.")
            if d["statut"] not in STATUTS:
                err.append("Statut inconnu.")
            if not d["date_debut"]:
                err.append("Date (ou date de début) obligatoire : JJ/MM/AAAA.")
            if d["date_fin"] and d["date_debut"] and d["date_fin"] < d["date_debut"]:
                err.append("La date de fin précède la date de début.")
            eid = f.get("ecole_id", type=int)
            d["ecole_id"] = eid if eid and eid in ecoles_cs(cs_id) else None
            if d["ecole_id"] and not d["lieu"]:
                d["lieu"] = ecoles_cs(cs_id)[d["ecole_id"]]["nom"]
            if not err:
                d["annee"] = annee_de(d["date_debut"])
                cols = list(d)
                if a:
                    ex("UPDATE jur_cp_activites SET " + ", ".join(f"{c}=?" for c in cols) + ", maj=? WHERE id=?",
                       (*[d[c] for c in cols], H.maintenant(), a["id"]))
                else:
                    ex("INSERT INTO jur_cp_activites (cs_id, " + ", ".join(cols) + ", cree_par, cree_le, maj) VALUES ("
                       + ",".join("?" * (len(cols) + 4)) + ")",
                       (cs_id, *[d[c] for c in cols], g.user["id"], H.maintenant(), H.maintenant()))
                H.journal("jur_cp_activite", f"{d['categorie']} {d['date_debut']}")
                flash("Activité enregistrée.", "success")
                if f.get("suite") == "nouvelle":
                    return redirect(url_for("jur_cp_activite_form", cs=cs_id if config.EDITION == "ddemp" else None,
                                            categorie=d["categorie"], acteur=act))
                return redirect(url_for("jur_cp_activites", annee=d["annee"], periode=periode_de(d["date_debut"]),
                                        cs=cs_id if config.EDITION == "ddemp" else None))
            for e in err:
                flash(e, "danger")
            v = dict(f.items())
        else:
            v = dict(a) if a else {"categorie": request.args.get("categorie") or "suivi", "statut": "realisee",
                                   "date_debut": date.today().isoformat(), "nb": 1}
            if a:
                v["acteur"] = "commune" if a["commune"] else (f"z{a['zone_id']}" if a["zone_id"] else "ccs")
            else:
                v["acteur"] = request.args.get("acteur") or ""
        return render_template("jur_cp_activite_form.html", a=a, v=v, acteurs=acteurs_de(cs_id), cs_id=cs_id,
                               ecoles=sorted(ecoles_cs(cs_id).values(), key=lambda e: e["nom"]),
                               CATEGORIES=CATEGORIES, STATUTS=STATUTS)

    def periode_de(iso):
        m = int(str(iso)[5:7])
        return "T1" if m >= 9 else ("T2" if m <= 3 else "T3")

    @app.route("/juridiction/conseillers/activites/<int:aid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_cp_bilan")
    def jur_cp_activite_supprimer(aid):
        juridiction_ou_404()
        a = activite_ou_404(aid)
        ex("DELETE FROM jur_cp_activites WHERE id=?", (aid,))
        H.journal("jur_cp_activite_suppr", str(aid))
        flash("Activité supprimée.", "success")
        return redirect(url_for("jur_cp_activites", annee=a["annee"], periode=periode_de(a["date_debut"]),
                                cs=a["cs_id"] if config.EDITION == "ddemp" else None))

    @app.route("/juridiction/conseillers/activites.xlsx")
    @H.connexion_requise()
    def jur_cp_activites_xlsx():
        juridiction_ou_404()
        annee, periode, cs_id = annee_demandee(request.args), periode_demandee(request.args), cs_demandee(request.args)
        d1, d2 = bornes(annee, periode)
        acts = q("SELECT a.*, z.nom zone_nom FROM jur_cp_activites a LEFT JOIN jur_zones z ON z.id=a.zone_id "
                 "WHERE a.cs_id=? AND a.annee=? AND a.date_debut BETWEEN ? AND ? ORDER BY a.date_debut", (cs_id, annee, d1, d2))
        X = Excel()
        ws = X.feuille("Activites", f"JOURNAL DES ACTIVITÉS DU RÉSEAU D'ANIMATION PÉDAGOGIQUE – {PERIODES[periode][0].upper()} – {annee}",
                       entete_doc())
        cles = ["acteur", "categorie", "statut", "cycle", "date_debut", "date_fin", "lieu", "designation", "participants",
                "nb", "beneficiaires_em", "beneficiaires_ep", "observations"]
        libs = ["Acteur (C/CS, zone ou « commune »)", "Nature", "Statut", "Cycle (EM/EP)", "Date début", "Date fin", "Lieu",
                "Désignation de l'activité", "Participants", "Nombre", "Bénéficiaires EM", "Bénéficiaires EP", "Observations"]
        X.tableau(ws, libs, cles, [["", "commune" if a["commune"] else (lib_zone(a["zone_nom"]) if a["zone_id"] else "C/CS"),
                                    CATEGORIES.get(a["categorie"], a["categorie"]), STATUTS.get(a["statut"], a["statut"]),
                                    a["cycle"] or "", date_fr(a["date_debut"]), date_fr(a["date_fin"]), a["lieu"] or "",
                                    a["designation"] or "", a["participants"] or "", a["nb"], a["beneficiaires_em"],
                                    a["beneficiaires_ep"], a["observations"] or ""] for a in acts],
                  editable=set(cles), cle_ligne=False)
        return X.reponse(f"activites_cp_{annee}_{periode}.xlsx")

    @app.route("/juridiction/conseillers/activites/import", methods=["POST"])
    @H.connexion_requise("jur_cp_bilan")
    def jur_cp_activites_import():
        juridiction_ou_404()
        cs_id = cs_demandee(request.form)
        lignes = lire_classeur(request.files.get("fichier"), "Activites")
        if lignes is None:
            flash("Fichier illisible : utilisez le modèle « Télécharger (Excel) » du journal.", "danger")
            return redirect(url_for("jur_cp_activites"))
        zones = {norm(lib_zone(z["nom"])): z["id"] for z in zones_cs(cs_id)}
        zones.update({norm(z["nom"]): z["id"] for z in zones_cs(cs_id)})
        cats = {norm(v): k for k, v in CATEGORIES.items()} | {norm(k): k for k in CATEGORIES}
        stats = {norm(v): k for k, v in STATUTS.items()} | {norm(k): k for k in STATUTS}
        n, ign = 0, 0
        for r in lignes:
            dd = lire_date(r.get("date_debut"))
            cat = cats.get(norm(r.get("categorie")))
            if not dd or not cat:
                ign += 1
                continue
            acteur = norm(r.get("_lib") or r.get("acteur"))
            zone_id = zones.get(acteur)
            commune = 1 if acteur == "COMMUNE" else 0
            ex("""INSERT INTO jur_cp_activites (cs_id, zone_id, commune, annee, categorie, cycle, lieu, date_debut, date_fin,
                  designation, participants, nb, beneficiaires_em, beneficiaires_ep, statut, observations, cree_par, cree_le, maj)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (cs_id, zone_id, commune, annee_de(dd), cat, (str(r.get("cycle") or "").upper()[:2] if str(r.get("cycle") or "").upper()[:2] in ("EM", "EP") else ""),
                str(r.get("lieu") or "")[:150], dd, lire_date(r.get("date_fin")), str(r.get("designation") or "")[:600],
                str(r.get("participants") or "")[:300], max(1, entier(r.get("nb")) or 1), entier(r.get("beneficiaires_em")),
                entier(r.get("beneficiaires_ep")), stats.get(norm(r.get("statut")), "realisee"), str(r.get("observations") or "")[:2000],
                g.user["id"], H.maintenant(), H.maintenant()))
            n += 1
        flash(f"{n} activité(s) chargée(s)" + (f", {ign} ligne(s) ignorée(s) (date ou nature manquante)" if ign else "") + ".",
              "success" if n else "warning")
        return redirect(url_for("jur_cp_activites", cs=cs_id if config.EDITION == "ddemp" else None))

    # ------------------------------------------------------------------ bilan
    def contexte_bilan(args):
        annee, periode, cs_id = annee_demandee(args), periode_demandee(args), cs_demandee(args)
        zone_id = args.get("zone", type=int) or None
        if zone_id and zone_id not in {z["id"] for z in zones_cs(cs_id)}:
            abort(404)
        if not cs_id:
            abort(404)
        return annee, periode, cs_id, zone_id

    def bilan_complet(annee, periode, cs_id, zone_id):
        calc = calculer(annee, periode, cs_id, zone_id)
        r = bilan_ligne(cs_id, annee, periode, zone_id)
        enr = json.loads(r["donnees"]) if r else None
        return fusionner(calc, enr), r

    @app.route("/juridiction/conseillers/bilan", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_cp_bilan():
        juridiction_ou_404()
        annee, periode, cs_id, zone_id = contexte_bilan(request.values)
        retour = dict(annee=annee, periode=periode, zone=zone_id, cs=cs_id if config.EDITION == "ddemp" else None)
        if request.method == "POST":
            exiger_saisie()
            action = request.form.get("action") or "enregistrer"
            r = bilan_ligne(cs_id, annee, periode, zone_id)
            if action == "supprimer":
                if r:
                    ex("DELETE FROM jur_cp_bilans WHERE id=?", (r["id"],))
                    flash("Bilan supprimé.", "success")
            elif action == "reinitialiser":
                if r:
                    ex("DELETE FROM jur_cp_bilans WHERE id=?", (r["id"],))
                flash("Bilan réinitialisé : tous les chiffres sont recalculés à partir des données de l'application.", "success")
            elif action == "recalculer":
                # garde les textes, les autres activités et les problèmes ; les chiffres reviennent au calcul
                if r:
                    old = json.loads(r["donnees"])
                    garde = {k: old[k] for k in ("textes", "autres", "problemes", "commentaires", "entete") if k in old}
                    if (old.get("s5") or {}).get("lignes"):
                        garde["s5"] = old["s5"]
                    ex("UPDATE jur_cp_bilans SET donnees=?, maj=? WHERE id=?",
                       (json.dumps(garde, ensure_ascii=False), H.maintenant(), r["id"]))
                flash("Chiffres recalculés (textes, autres activités, problèmes et évaluation conservés).", "success")
            else:
                calc = calculer(annee, periode, cs_id, zone_id)
                enr = lire_formulaire(request.form, calc)
                etat = "valide" if action == "valider" else "brouillon"
                donnees = json.dumps(enr, ensure_ascii=False)
                if r:
                    ex("UPDATE jur_cp_bilans SET donnees=?, etat=?, maj=? WHERE id=?", (donnees, etat, H.maintenant(), r["id"]))
                else:
                    ex("""INSERT INTO jur_cp_bilans (cs_id, annee, periode, niveau, zone_id, donnees, etat, cree_par, cree_le, maj)
                          VALUES (?,?,?,?,?,?,?,?,?,?)""", (cs_id, annee, periode, "zone" if zone_id else "cs", zone_id or 0,
                                                            donnees, etat, g.user["id"], H.maintenant(), H.maintenant()))
                flash("Bilan validé." if etat == "valide" else "Bilan enregistré.", "success")
            H.journal("jur_cp_bilan", f"{action} {annee} {periode} zone={zone_id or '-'}")
            synchroniser(cs_id, annee)
            if action == "pdf":
                return redirect(url_for("jur_cp_bilan_pdf", **retour))
            return redirect(url_for("jur_cp_bilan", **retour))
        b, r = bilan_complet(annee, periode, cs_id, zone_id)
        return render_template("jur_cp_bilan.html", b=b, r=r, annee=annee, annees=annees_dispo(), periode=periode,
                               PERIODES=PERIODES, cs=H.jur_cs_liste(), cs_id=cs_id, zone_id=zone_id, zones=zones_cs(cs_id),
                               saisie=saisie(), COURS=COURS, TEXTES=TEXTES, pct=pct_txt, retour=retour, lib_zone=lib_zone)

    @app.route("/juridiction/conseillers/bilan.pdf")
    @H.connexion_requise()
    def jur_cp_bilan_pdf():
        juridiction_ou_404()
        if request.args.get("recu") is not None:
            cs_id, annee = request.args.get("cs", type=int), annee_demandee(request.args)
            b = bilan_recu(cs_id, annee, request.args.get("recu", type=int))
        else:
            annee, periode, cs_id, zone_id = contexte_bilan(request.args)
            b, _ = bilan_complet(annee, periode, cs_id, zone_id)
        nom = f"bilan_cp_{b['annee']}_{b['periode']}_{'zone' if b.get('zone_id') else 'cs'}.pdf"
        return H.pdf_reponse(pdf_bilan(b), nom)

    @app.route("/juridiction/conseillers/bilan.xlsx")
    @H.connexion_requise()
    def jur_cp_bilan_xlsx():
        juridiction_ou_404()
        if request.args.get("recu") is not None:
            cs_id, annee = request.args.get("cs", type=int), annee_demandee(request.args)
            b = bilan_recu(cs_id, annee, request.args.get("recu", type=int))
        else:
            annee, periode, cs_id, zone_id = contexte_bilan(request.args)
            b, _ = bilan_complet(annee, periode, cs_id, zone_id)
        return excel_bilan(b).reponse(f"bilan_cp_{b['annee']}_{b['periode']}_{'zone' if b.get('zone_id') else 'cs'}.xlsx")

    @app.route("/juridiction/conseillers/bilan/import", methods=["POST"])
    @H.connexion_requise("jur_cp_bilan")
    def jur_cp_bilan_import():
        """Charger : classeur « Télécharger (Excel) » du bilan, complété ou corrigé hors ligne."""
        juridiction_ou_404()
        annee, periode, cs_id, zone_id = contexte_bilan(request.form)
        retour = dict(annee=annee, periode=periode, zone=zone_id, cs=cs_id if config.EDITION == "ddemp" else None)
        fichier = request.files.get("fichier")
        feuilles = {}
        for nom in ("1-Reseau", "2-Activites", "3-Concertations", "3-Autres", "4-Couverture", "5-Evaluation", "6-Problemes", "7-Textes"):
            feuilles[nom] = lire_classeur(fichier, nom)
            if fichier:
                fichier.stream.seek(0)
        if all(v is None for v in feuilles.values()):
            flash("Fichier illisible : utilisez le classeur « Télécharger (Excel) » de ce bilan.", "danger")
            return redirect(url_for("jur_cp_bilan", **retour))
        b, r = bilan_complet(annee, periode, cs_id, zone_id)
        enr = json.loads(r["donnees"]) if r else {}
        cles = {a["cle"] for a in b["acteurs"]}
        for sec, nom, champs in (("s1", "1-Reseau", S1), ("s2", "2-Activites", S2), ("s3", "3-Concertations", S3),
                                 ("s4", "4-Couverture", S4)):
            for ligne in feuilles.get(nom) or []:
                k = ligne.get("acteur")
                if k in cles:
                    enr.setdefault(sec, {}).setdefault(k, {}).update({c: entier(ligne[c]) for c in champs if c in ligne})
        for ligne in feuilles.get("5-Evaluation") or []:
            co = str(ligne.get("acteur") or "").upper()
            if co in COURS:
                enr.setdefault("s5", {}).setdefault("lignes", {}).setdefault(co, {}).update(
                    {c: entier(ligne[c]) for c in S5 if c in ligne})
        if feuilles.get("3-Autres") is not None:
            enr["autres"] = [{k: str(l.get(k) or "") for k in ("lieu", "periode", "designation", "participants")}
                             for l in feuilles["3-Autres"] if str(l.get("designation") or "").strip()]
        if feuilles.get("6-Problemes") is not None:
            enr["problemes"] = [{k: str(l.get(k) or "") for k in ("designation", "ampleur", "observations")}
                                for l in feuilles["6-Problemes"] if str(l.get("designation") or "").strip()]
        for l in feuilles.get("7-Textes") or []:
            k = l.get("acteur")
            if k in dict(TEXTES):
                enr.setdefault("textes", {})[k] = str(l.get("texte") or "")
            elif k == "commentaires":
                enr["commentaires"] = str(l.get("texte") or "")
        donnees = json.dumps(enr, ensure_ascii=False)
        if r:
            ex("UPDATE jur_cp_bilans SET donnees=?, maj=? WHERE id=?", (donnees, H.maintenant(), r["id"]))
        else:
            ex("""INSERT INTO jur_cp_bilans (cs_id, annee, periode, niveau, zone_id, donnees, etat, cree_par, cree_le, maj)
                  VALUES (?,?,?,?,?,?,?,?,?,?)""", (cs_id, annee, periode, "zone" if zone_id else "cs", zone_id or 0, donnees,
                                                    "brouillon", g.user["id"], H.maintenant(), H.maintenant()))
        synchroniser(cs_id, annee)
        H.journal("jur_cp_bilan_import", f"{annee} {periode}")
        flash("Bilan chargé depuis le classeur Excel.", "success")
        return redirect(url_for("jur_cp_bilan", **retour))

    # ------------------------------------------------------------------ Excel
    def excel_bilan(b):
        X = Excel()
        tit = titre_bilan(b)
        act = b["acteurs"]
        lignes_tot = [("_tcp", "TOTAL CP")] if b["niveau"] == "cs" else []
        lignes_tot.append(("_tcs", "TOTAL CS" if b["niveau"] == "cs" else "TOTAL ZONE"))

        def rows(sec, champs, derives=()):
            out = [[a["cle"], a["lib"] + (f" ({a['nom']})" if a.get("nom") else "")] + [b[sec][a["cle"]].get(c) for c in champs]
                   + [b[sec][a["cle"]].get(c) for c in derives] for a in act]
            for k, lib in lignes_tot:
                out.append([k, lib] + [b[sec][k].get(c) for c in champs] + [b[sec][k].get(c) for c in derives])
            return out
        ws = X.feuille("1-Reseau", tit + " – 1. DONNÉES STATISTIQUES SUR LE RÉSEAU D'ANIMATION PÉDAGOGIQUE", entete_doc(b))
        X.tableau(ws, ["Acteurs du RAP", "EM écoles", "EM sections", "EP écoles", "EP classes", "Ens. EM H", "Ens. EM F",
                       "Ens. EP H", "Ens. EP F", "UP EP", "UP EM", "Total écoles", "Total classes", "Ens. EM T", "Ens. EP T",
                       "Ens. H", "Ens. F", "Ens. T", "UP T"],
                  ["acteur"] + S1 + ["t_ecoles", "t_classes", "ens_em_t", "ens_ep_t", "ens_h", "ens_f", "ens_t", "up_t"],
                  rows("s1", S1, ["t_ecoles", "t_classes", "ens_em_t", "ens_ep_t", "ens_h", "ens_f", "ens_t", "up_t"]),
                  editable=set(S1))
        ws = X.feuille("2-Activites", tit + " – 2. ACTIVITÉS PÉDAGOGIQUES MENÉES", entete_doc(b))
        X.tableau(ws, ["Acteurs du RAP", "2.1 Visites cl. prog. EM", "2.1 prog. Tot", "2.1 réal. EM", "2.1 réal. Tot",
                       "2.2 Visites éc. prog. EM", "2.2 prog. Tot", "2.2 réal. EM", "2.2 réal. Tot",
                       "2.3 Suivis prog. EM", "2.3 prog. Tot", "2.3 réal. EM", "2.3 réal. Tot",
                       "2.4 UP prog.", "2.4 UP prép.", "2.4 UP réal.", "2.5 Form. prog.", "2.5 Form. réal.",
                       "2.1 % EM", "2.1 % Tot", "2.2 % EM", "2.2 % Tot", "2.3 % EM", "2.3 % Tot", "2.4 %", "2.5 %"],
                  ["acteur"] + S2 + ["vc_pct_em", "vc_pct_t", "ve_pct_em", "ve_pct_t", "su_pct_em", "su_pct_t", "up_pct", "fo_pct"],
                  rows("s2", S2, ["vc_pct_em", "vc_pct_t", "ve_pct_em", "ve_pct_t", "su_pct_em", "su_pct_t", "up_pct", "fo_pct"]),
                  editable=set(S2), pourcent={"vc_pct_em", "vc_pct_t", "ve_pct_em", "ve_pct_t", "su_pct_em", "su_pct_t", "up_pct", "fo_pct"})
        ws = X.feuille("3-Concertations", tit + " – 3.1 CONCERTATIONS", entete_doc(b))
        X.tableau(ws, ["Acteurs du RAP", "Programmées", "Réalisées", "%"], ["acteur"] + S3 + ["co_pct"],
                  rows("s3", S3, ["co_pct"]), editable=set(S3), pourcent={"co_pct"})
        ws = X.feuille("3-Autres", tit + " – 3.2 AUTRES ACTIVITÉS MENÉES AU COURS DE LA PÉRIODE", entete_doc(b))
        X.tableau(ws, ["N°", "Lieux", "Périodes", "Désignation des activités menées", "Participants"],
                  ["acteur", "lieu", "periode", "designation", "participants"],
                  [[str(i), str(i), x["lieu"], x["periode"], x["designation"], x["participants"]] for i, x in enumerate(b["autres"], 1)],
                  editable={"lieu", "periode", "designation", "participants"})
        ws = X.feuille("4-Couverture", tit + " – 4. RÉSULTATS / IMPACT : TAUX DE COUVERTURE", entete_doc(b))
        X.tableau(ws, ["Acteurs du RAP", "Base 4.1 EM (sections)", "Base 4.1 EM+EP (classes)", "Base 4.2 EM (écoles)",
                       "Base 4.2 EM+EP", "Base 4.3 EM (directeurs)", "Base 4.3 EM+EP", "4.5 Bénéficiaires EM",
                       "4.5 Bénéficiaires EM+EP", "Base 4.5 EM (enseignants)", "Base 4.5 EM+EP",
                       "4.1 % EM", "4.1 % EM+EP", "4.2 % EM", "4.2 % EM+EP", "4.3 % EM", "4.3 % EM+EP", "4.4 % UP",
                       "4.5 % EM", "4.5 % EM+EP"],
                  ["acteur"] + S4 + ["vc_cov_em", "vc_cov_t", "ve_cov_em", "ve_cov_t", "su_cov_em", "su_cov_t", "up_cov",
                                     "fo_cov_em", "fo_cov_t"],
                  rows("s4", S4, ["vc_cov_em", "vc_cov_t", "ve_cov_em", "ve_cov_t", "su_cov_em", "su_cov_t", "up_cov",
                                  "fo_cov_em", "fo_cov_t"]),
                  editable=set(S4), pourcent={"vc_cov_em", "vc_cov_t", "ve_cov_em", "ve_cov_t", "su_cov_em", "su_cov_t",
                                              "up_cov", "fo_cov_em", "fo_cov_t"})
        ws = X.feuille("5-Evaluation", tit + f" – 5. RÉSULTATS DE L'ÉVALUATION D'ÉTAPE N°{b['s5'].get('etape') or '1'}", entete_doc(b))
        lg = b["s5"]["lignes"]
        X.tableau(ws, ["Cours", "Inscrits G", "Inscrits F", "Ont composé G", "Ont composé F", "Maîtrise partielle G",
                       "Maîtrise partielle F", "Maîtrise minimale G", "Maîtrise minimale F", "À renforcer Maths",
                       "À renforcer Français", "Inscrits T", "Composé T", "Partielle T", "Minimale T", "Réussite G",
                       "Réussite F", "Réussite T"],
                  ["acteur"] + S5 + ["ins_t", "comp_t", "part_t", "min_t", "reu_g", "reu_f", "reu_t"],
                  [[co, co] + [lg[co].get(c) for c in S5] + [lg[co].get(c) for c in ("ins_t", "comp_t", "part_t", "min_t", "reu_g", "reu_f", "reu_t")]
                   for co in COURS + ["TOTAL"]], editable=set(S5), pourcent={"reu_g", "reu_f", "reu_t"})
        ws = X.feuille("6-Problemes", tit + " – PROBLÈMES MAJEURS IDENTIFIÉS ET CEUX EN VOIE DE RÉSOLUTION", entete_doc(b))
        X.tableau(ws, ["Ordre", "Désignation des problèmes majeurs identifiés", "Ampleur (%)",
                       "Observations (approches et stratégies appliquées ou envisagées)"],
                  ["acteur", "designation", "ampleur", "observations"],
                  [[str(i), str(i), p["designation"], p["ampleur"], p["observations"]] for i, p in enumerate(b["problemes"], 1)],
                  editable={"designation", "ampleur", "observations"})
        ws = X.feuille("7-Textes", tit + " – 6. ANALYSE DES RÉSULTATS ET 7. COMMENTAIRES", entete_doc(b))
        X.tableau(ws, ["Rubrique", "Texte"], ["acteur", "texte"],
                  [[k, lib, b["textes"].get(k, "")] for k, lib in TEXTES] + [["commentaires", "7. Commentaires / analyse",
                                                                              b.get("commentaires", "")]],
                  editable={"texte"}, larges={"texte": 120})
        return X

    def entete_doc(b=None):
        s = H.jur_structure() or {}
        dep = (b or {}).get("entete", {}).get("departement") if b else None
        cs = (b or {}).get("entete", {}).get("cs") if b else None
        lignes = ["RÉPUBLIQUE DU BÉNIN – MINISTÈRE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE"]
        dep = dep or s.get("departement")
        cs = cs or s.get("cs")
        if dep:
            lignes.append(f"DIRECTION DÉPARTEMENTALE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE – {dep.upper()}")
        if cs:
            lignes.append(f"CIRCONSCRIPTION SCOLAIRE DE {cs.upper()}")
        return lignes

    def titre_bilan(b):
        p = PERIODES.get(b["periode"], ("", ""))
        quoi = "BILAN ANNUEL" if b["periode"] == "AN" else "BILAN TRIMESTRIEL"
        niv = "NIVEAU ZONE" if b.get("niveau") == "zone" else "NIVEAU CS"
        return f"{quoi} DES ACTIVITÉS PÉDAGOGIQUES / {niv} – {b['annee']}" + (f" – {p[0]}" if b["periode"] != "AN" else "")

    # ------------------------------------------------------------------ PDF
    def pdf_bilan(b):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        P = H.pdfs
        W, Hh = landscape(A4)
        BLEU = colors.HexColor("#1F4E79")
        st = ParagraphStyle("c", fontName="Helvetica", fontSize=7, leading=8.4)
        stc = ParagraphStyle("cc", parent=st, alignment=TA_CENTER)
        stb = ParagraphStyle("b", parent=stc, fontName="Helvetica-Bold")
        h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=9.5, leading=12, spaceBefore=6, spaceAfter=3,
                            textColor=BLEU, alignment=TA_CENTER)
        h3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, spaceBefore=4, spaceAfter=1,
                            alignment=TA_CENTER)
        corps = ParagraphStyle("corps", fontName="Helvetica", fontSize=8.5, leading=11.5)
        ent = b.get("entete") or {}
        act = b["acteurs"]
        zone = b.get("niveau") == "zone"
        tot = [("_tcp", "TOTAL CP")] if not zone else []
        tot.append(("_tcs", "TOTAL CS" if not zone else "TOTAL ZONE"))

        def v(x):
            return "" if x is None else str(x)

        stp = ParagraphStyle("pc", parent=stc, fontSize=6.2, leading=7)

        def pc(x):
            return Paragraph(pct_txt(x).replace(" %", "%"), stp)

        def P_(t, s=stc):
            return Paragraph(str(t), s)

        def lib(a):
            return P_(f"<b>{a['lib']}</b>" + (f"<br/><font size=6>{a['nom']}</font>" if a.get("nom") else ""), st)

        def style(n_ent, n_lignes, spans=()):
            cmds = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5B6B7F")),
                    ("BACKGROUND", (0, 0), (-1, n_ent - 1), colors.HexColor("#E4ECF5")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
            for i in range(len(tot)):
                cmds.append(("BACKGROUND", (0, n_ent + n_lignes - len(tot) + i), (-1, n_ent + n_lignes - len(tot) + i),
                             colors.HexColor("#F2F6FB")))
            cmds += [("SPAN",) + sp for sp in spans]
            return TableStyle(cmds)

        el = []
        # ---- 1. réseau
        s1 = b["s1"]
        ent1 = [[P_("<b>ACTEURS DU RÉSEAU D'ANIMATION PÉDAGOGIQUE (C/CS et CP)</b>"),
                 P_("<b>TAILLE PHYSIQUE DU RÉSEAU D'ANIMATION PÉDAGOGIQUE<br/>NOMBRE D'ÉCOLES ET DE CLASSES/SECTIONS</b>"), "", "", "", "", "",
                 P_("<b>EFFECTIF DES ENSEIGNANTS</b>"), "", "", "", "", "", "", "", "",
                 P_("<b>NOMBRE D'UNITÉS PÉDAGOGIQUES (UP)</b>"), "", ""],
                ["", P_("<b>Écoles maternelles</b>"), "", P_("<b>Écoles primaires</b>"), "", P_("<b>TOTAL</b>"), "",
                 P_("<b>Écoles maternelles</b>"), "", "", P_("<b>Écoles primaires</b>"), "", "", P_("<b>TOTAL EM + EP</b>"), "", "",
                 P_("<b>EP</b>"), P_("<b>EM</b>"), P_("<b>T</b>")],
                ["", "Écoles", "Sections", "Écoles", "Classes", "Écoles", "Classes", "H", "F", "Total", "H", "F", "Total",
                 "H", "F", "Total", "", "", ""]]
        data = []
        for k, a in [(a["cle"], a) for a in act] + [(k, {"lib": l}) for k, l in tot]:
            r = s1[k]
            data.append([lib(a) if k in s1 and not k.startswith("_") else P_(f"<b>{a['lib']}</b>", st)] + [v(r.get(c)) for c in (
                "em_ecoles", "em_sections", "ep_ecoles", "ep_classes", "t_ecoles", "t_classes", "ens_em_h", "ens_em_f", "ens_em_t",
                "ens_ep_h", "ens_ep_f", "ens_ep_t", "ens_h", "ens_f", "ens_t", "up_ep", "up_em", "up_t")])
        t = Table(ent1 + data, colWidths=[44 * mm] + [12.5 * mm] * 18, repeatRows=3)
        t.setStyle(style(3, len(data), [((0, 0), (0, 2)), ((1, 0), (6, 0)), ((7, 0), (15, 0)), ((16, 0), (18, 1)),
                                        ((1, 1), (2, 1)), ((3, 1), (4, 1)), ((5, 1), (6, 1)), ((7, 1), (9, 1)),
                                        ((10, 1), (12, 1)), ((13, 1), (15, 1))]))
        el += [Paragraph("1. DONNÉES STATISTIQUES SUR LE RÉSEAU D'ANIMATION PÉDAGOGIQUE", h2), t]

        # ---- 2. activités
        s2 = b["s2"]
        ent2 = [[P_("<b>ACTEURS DU RAP (C/CS + CP)</b>"), P_("<b>2.1 VISITES / INSPECTIONS DE CLASSES</b>"), "", "", "", "", "",
                 P_("<b>2.2 VISITES D'ÉCOLES</b>"), "", "", "", "", "",
                 P_("<b>2.3 SUIVIS / ENCADREMENTS D/EP D/EM</b>"), "", "", "", "", "",
                 P_("<b>2.4 SÉANCES D'UNITÉ PÉDAGOGIQUE</b>"), "", "", "", P_("<b>2.5 FORMATIONS GROUPÉES / CONFÉRENCES</b>"), "", ""],
                ["", "Program.", "", "Réalisées", "", "%", "", "Program.", "", "Réalisées", "", "%", "",
                 "Program.", "", "Réalisées", "", "%", "", "Progr.", "Prép.", "Réal.", "%", "Progr.", "Réal.", "%"],
                [""] + ["EM", "Tot"] * 9 + ["", "", "", "", "", "", ""]]
        data = []
        for k, a in [(a["cle"], a) for a in act] + [(k, {"lib": l}) for k, l in tot]:
            r = s2[k]
            row = [lib(a) if not k.startswith("_") else P_(f"<b>{a['lib']}</b>", st)]
            for p in ("vc", "ve", "su"):
                row += [v(r.get(f"{p}_prog_em")), v(r.get(f"{p}_prog_t")), v(r.get(f"{p}_real_em")), v(r.get(f"{p}_real_t")),
                        pc(r.get(f"{p}_pct_em")), pc(r.get(f"{p}_pct_t"))]
            row += [v(r.get("up_prog")), v(r.get("up_prep")), v(r.get("up_real")), pc(r.get("up_pct")),
                    v(r.get("fo_prog")), v(r.get("fo_real")), pc(r.get("fo_pct"))]
            data.append(row)
        t = Table(ent2 + data, colWidths=[36 * mm] + [9.2 * mm] * 25, repeatRows=3)
        spans = [((0, 0), (0, 2)), ((1, 0), (6, 0)), ((7, 0), (12, 0)), ((13, 0), (18, 0)), ((19, 0), (22, 0)), ((23, 0), (25, 0))]
        for g0 in (1, 7, 13):
            spans += [((g0, 1), (g0 + 1, 1)), ((g0 + 2, 1), (g0 + 3, 1)), ((g0 + 4, 1), (g0 + 5, 1))]
        spans += [((c, 1), (c, 2)) for c in range(19, 26)]
        t.setStyle(style(3, len(data), spans))
        el += [Paragraph("2. ACTIVITÉS PÉDAGOGIQUES MENÉES — SYNTHÈSE DES ACTIVITÉS PÉDAGOGIQUES DE LA PÉRIODE", h2), t]

        # ---- 3. concertations et autres activités
        s3 = b["s3"]
        d3 = [[P_("<b>ACTEURS DU RAP</b>"), P_("<b>3.1 CONCERTATIONS</b>"), "", ""], ["", "Program.", "Réalisées", "%"]]
        for k, a in [(a["cle"], a) for a in act] + [(k, {"lib": l}) for k, l in tot]:
            r = s3[k]
            d3.append([lib(a) if not k.startswith("_") else P_(f"<b>{a['lib']}</b>", st), v(r.get("co_prog")),
                       v(r.get("co_real")), pc(r.get("co_pct"))])
        t31 = Table(d3, colWidths=[40 * mm, 15 * mm, 15 * mm, 15 * mm], repeatRows=2)
        t31.setStyle(style(2, len(d3) - 2, [((0, 0), (0, 1)), ((1, 0), (3, 0))]))
        d32 = [[P_("<b>3.2 AUTRES ACTIVITÉS MENÉES AU COURS DE LA PÉRIODE</b>"), "", "", "", ""],
               [P_("<b>N°</b>"), P_("<b>LIEUX</b>"), P_("<b>PÉRIODES</b>"), P_("<b>DÉSIGNATION DES ACTIVITÉS MENÉES</b>"),
                P_("<b>PARTICIPANTS</b>")]]
        for i, x in enumerate(b["autres"], 1):
            d32.append([str(i), P_(x["lieu"], st), P_(x["periode"], st), P_(x["designation"], st), P_(x["participants"], st)])
        if len(d32) == 2:
            d32.append(["", "", "", P_("<i>Aucune autre activité enregistrée.</i>", st), ""])
        t32 = Table(d32, colWidths=[8 * mm, 30 * mm, 28 * mm, 82 * mm, 42 * mm], repeatRows=2)
        t32.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5B6B7F")),
                                 ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#E4ECF5")), ("SPAN", (0, 0), (-1, 0)),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("FONTSIZE", (0, 0), (-1, -1), 7),
                                 ("ALIGN", (0, 0), (0, -1), "CENTER")]))
        el += [Paragraph("3. ACTIVITÉS DE LA PÉRIODE (suite)", h2),
               Table([[t31, t32]], colWidths=[88 * mm, 192 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                                                                        ("LEFTPADDING", (0, 0), (-1, -1), 0)])]

        # ---- 4. couverture (4.1 à 4.5 dans un seul tableau)
        s4 = b["s4"]
        d4 = [[P_("<b>ACTEURS DU RAP (C/CS + CP)</b>"), P_("<b>TAUX DE COUVERTURE DES ACTIVITÉS PÉDAGOGIQUES DE LA PÉRIODE</b>")] + [""] * 16,
              ["", P_("<b>4.1 VISITES / INSPECTIONS DE CLASSES</b>"), "", "", "", P_("<b>4.2 VISITES D'ÉCOLE</b>"), "", "", "",
               P_("<b>4.3 SUIVIS / ENCADREMENTS D/EP D/EM</b>"), "", "", "", P_("<b>4.4 UP tenues</b>"),
               P_("<b>4.5 FORMATIONS GROUPÉES / CONFÉRENCES PÉDAGOGIQUES</b>"), "", "", ""],
              ["", "Total réalisé", "", "% couverture", "", "Total réalisé", "", "% couverture", "", "Total réalisé", "",
               "% couverture", "", P_("% couverture"), "Bénéficiaires", "", "% couverture", ""],
              [""] + ["EM", "EM+EP"] * 6 + [""] + ["EM", "EM+EP"] * 2]
        for k, a in [(a["cle"], a) for a in act] + [(k, {"lib": l}) for k, l in tot]:
            r2, r4 = s2[k], s4[k]
            d4.append([lib(a) if not k.startswith("_") else P_(f"<b>{a['lib']}</b>", st),
                       v(r2.get("vc_real_em")), v(r2.get("vc_real_t")), pc(r4.get("vc_cov_em")), pc(r4.get("vc_cov_t")),
                       v(r2.get("ve_real_em")), v(r2.get("ve_real_t")), pc(r4.get("ve_cov_em")), pc(r4.get("ve_cov_t")),
                       v(r2.get("su_real_em")), v(r2.get("su_real_t")), pc(r4.get("su_cov_em")), pc(r4.get("su_cov_t")),
                       pc(r4.get("up_cov")), v(r4.get("fo_benef_em")), v(r4.get("fo_benef_t")), pc(r4.get("fo_cov_em")),
                       pc(r4.get("fo_cov_t"))])
        t4 = Table(d4, colWidths=[36 * mm] + [13.4 * mm] * 12 + [16 * mm] + [13.4 * mm] * 4, repeatRows=4)
        sp4 = [((0, 0), (0, 3)), ((1, 0), (17, 0)), ((1, 1), (4, 1)), ((5, 1), (8, 1)), ((9, 1), (12, 1)), ((13, 1), (13, 3)),
               ((14, 1), (17, 1))]
        for g0 in (1, 5, 9, 14):
            sp4 += [((g0, 2), (g0 + 1, 2)), ((g0 + 2, 2), (g0 + 3, 2))]
        t4.setStyle(style(4, len(d4) - 4, sp4))
        el += [Paragraph("4. RÉSULTATS / IMPACT DES ACTIVITÉS DE LA PÉRIODE", h2), t4]

        # ---- 5. évaluation
        lg = b["s5"]["lignes"]
        d5 = [[P_("<b>COURS</b>"), P_("<b>INSCRITS</b>"), "", "", P_("<b>ONT COMPOSÉ</b>"), "", "",
               P_("<b>Ont la maîtrise partielle / n'ont pas atteint le seuil de réussite</b>"), "", "",
               P_("<b>Ont atteint la maîtrise minimale / le seuil de réussite</b>"), "", "",
               P_("<b>POURCENTAGE DE RÉUSSITE</b>"), "", "", P_("<b>À RENFORCER</b>"), ""],
              ["", "G", "F", "T", "G", "F", "T", "G", "F", "T", "G", "F", "T", "G", "F", "T", "Maths", "Français"]]
        for co in COURS + ["TOTAL"]:
            r = lg[co]
            d5.append([P_(f"<b>{co}</b>", st)] + [v(r.get(c)) for c in ("ins_g", "ins_f", "ins_t", "comp_g", "comp_f", "comp_t",
                                                                          "part_g", "part_f", "part_t", "min_g", "min_f", "min_t")]
                      + [pc(r.get("reu_g")), pc(r.get("reu_f")), pc(r.get("reu_t")), v(r.get("renf_math")), v(r.get("renf_fr"))])
        t5 = Table(d5, colWidths=[22 * mm] + [14.2 * mm] * 17, repeatRows=2)
        t5.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5B6B7F")),
                                ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#E4ECF5")),
                                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F6FB")),
                                ("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (3, 0)), ("SPAN", (4, 0), (6, 0)), ("SPAN", (7, 0), (9, 0)),
                                ("SPAN", (10, 0), (12, 0)), ("SPAN", (13, 0), (15, 0)), ("SPAN", (16, 0), (17, 0)),
                                ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("FONTSIZE", (0, 0), (-1, -1), 7)]))
        el += [Paragraph(f"5. RÉSULTATS DE L'ÉVALUATION D'ÉTAPE N°{b['s5'].get('etape') or '1'} : point de l'évaluation", h2), t5]

        # ---- 6. analyse
        el.append(Paragraph("6. ANALYSE DES RÉSULTATS", h2))
        for k, l in TEXTES:
            if (b["textes"].get(k) or "").strip():
                el += [Paragraph(l, h3), Paragraph(b["textes"][k].replace("\n", "<br/>"), corps)]
        # problèmes
        d6 = [[P_("<b>Ordre</b>"), P_("<b>DÉSIGNATION DES PROBLÈMES MAJEURS IDENTIFIÉS</b>"),
               P_("<b>AMPLEUR DES PROBLÈMES (%)</b>"),
               P_("<b>OBSERVATIONS (approches et stratégies appliquées ou envisagées)</b>")]]
        for i, p in enumerate(b["problemes"], 1):
            d6.append([str(i), P_(p["designation"], st), P_(p["ampleur"]), P_(p["observations"], st)])
        if len(d6) == 1:
            d6.append(["", P_("<i>À renseigner.</i>", st), "", ""])
        t6 = Table(d6, colWidths=[14 * mm, 100 * mm, 30 * mm, 136 * mm], repeatRows=1)
        t6.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5B6B7F")),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E4ECF5")),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, -1), "CENTER"),
                                ("FONTSIZE", (0, 0), (-1, -1), 7.5)]))
        el += [Paragraph("PROBLÈMES MAJEURS IDENTIFIÉS ET CEUX EN VOIE DE RÉSOLUTION "
                         "<font size=7.5>(énumérer par ordre décroissant d'importance)</font>", h2), t6]
        # 7. commentaires + signature
        titre_sig, nom_sig, img_sig = (ent.get("titre_sig") or ("Le Conseiller Pédagogique" if zone else "Le CCS")), \
            ent.get("nom_sig") or "", None
        if not zone:
            try:
                _t, _n, img_sig = H.jur_signataire(None)
                nom_sig = nom_sig or _n
            except Exception:  # noqa: BLE001
                img_sig = None
        sig_img = P.image_data_url(img_sig) if img_sig else None
        bloc = [Paragraph("7. COMMENTAIRES / ANALYSE", ParagraphStyle("h", parent=h2, alignment=0)),
                Paragraph((b.get("commentaires") or "—").replace("\n", "<br/>"), corps), Spacer(1, 6)]
        el.append(KeepTogether(bloc))

        def premiere_page(c, doc):
            c.saveState()
            P.bloc_memp(c, 14 * mm, Hh - 9 * mm, 15 * mm)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 7.6)
            y = Hh - 28 * mm
            if ent.get("departement"):
                c.drawString(14 * mm, y, "DIRECTION DÉPARTEMENTALE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE")
                c.drawString(14 * mm, y - 9, f"DU {ent['departement'].upper()}")
                y -= 20
            if ent.get("cs"):
                c.drawString(14 * mm, y, f"CIRCONSCRIPTION SCOLAIRE DE {ent['cs'].upper()}")
                y -= 10
            if zone and act:
                c.drawString(14 * mm, y, f"{act[0]['lib'].upper()}" + (f" : {act[0]['nom']}" if act[0].get("nom") else ""))
            # cadre du titre (à droite), comme sur le canevas
            quoi = "BILAN ANNUEL" if b["periode"] == "AN" else "BILAN TRIMESTRIEL"
            t1 = f"{quoi} DES ACTIVITÉS PÉDAGOGIQUES /"
            t2 = "NIVEAU ZONE" if zone else "NIVEAU CS"
            c.setFont("Helvetica-Bold", 10.5)
            w = max(c.stringWidth(t1, "Helvetica-Bold", 10.5), c.stringWidth(t2, "Helvetica-Bold", 10.5)) + 16
            x0 = W - 14 * mm - w
            c.setStrokeColor(BLEU)
            c.setLineWidth(1.1)
            c.rect(x0, Hh - 22 * mm, w, 13 * mm)
            c.setFillColor(BLEU)
            c.drawCentredString(x0 + w / 2, Hh - 14 * mm, t1)
            c.drawCentredString(x0 + w / 2, Hh - 19.5 * mm, t2)
            c.setFillColor(colors.black)
            per = PERIODES.get(b["periode"], ("", ""))
            c.setFont("Helvetica-Bold", 8.5)
            c.drawRightString(W - 14 * mm, Hh - 28 * mm, f"Année scolaire : {b['annee']} – {per[0]} ({per[1]})")
            if ent.get("lieu_date"):
                c.setFont("Helvetica", 8)
                c.drawRightString(W - 14 * mm, Hh - 33 * mm, ent["lieu_date"])
            c.restoreState()
            pied(c, doc)

        def pied(c, doc):
            c.saveState()
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.HexColor("#667085"))
            c.drawString(14 * mm, 7 * mm, f"SCOLARIS – {titre_bilan(b)}")
            c.drawRightString(W - 14 * mm, 7 * mm, f"Page {doc.page}")
            c.restoreState()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=(W, Hh), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm,
                                bottomMargin=13 * mm, title=titre_bilan(b), author="SCOLARIS")

        cachet_vals = None
        if not zone:
            try:
                cachet_vals = H.jur_cachet(None)
            except Exception:  # noqa: BLE001
                cachet_vals = None

        from reportlab.platypus import Flowable

        class BlocSignature(Flowable):
            """« Le CCS, » + signature digitale (+ cachet de la structure) + nom, à droite de la page."""
            def __init__(self):
                super().__init__()
                self.width, self.height = W - 28 * mm, 34 * mm

            def draw(self):
                c = self.canv
                cx = self.width - 45 * mm
                c.setFont("Helvetica-Bold", 9.5)
                c.drawCentredString(cx, self.height - 10, f"{titre_sig},")
                if cachet_vals and any(cachet_vals[:3]):
                    import cachet as CA
                    CA.dessiner(c, cx - 30 * mm, self.height / 2 - 2, 13 * mm, *cachet_vals[:4])
                if sig_img:
                    iw, ih = sig_img.getSize()
                    hh = 16 * mm
                    ww = min(48 * mm, hh * iw / ih) if ih else 40 * mm
                    c.drawImage(sig_img, cx - ww / 2, 9 * mm, ww, hh, mask="auto", preserveAspectRatio=True)
                c.setFont("Helvetica-Bold", 9.5)
                c.drawCentredString(cx, 3, nom_sig)

        el.append(BlocSignature())
        doc.build([Spacer(1, 26 * mm)] + el, onFirstPage=premiere_page, onLaterPages=pied)
        return buf.getvalue()

    H.jur_cp_calculer = calculer        # pour les tests et les autres modules

    # ------------------------------------------------------------------ v1.10 : tableau de bord (CCS puis CP)
    INDIC_RAP = [("vc", "Visites de classes", "s2", "vc_prog_t", "vc_real_t"),
                 ("ve", "Visites d'écoles", "s2", "ve_prog_t", "ve_real_t"),
                 ("su", "Suivis de directeurs", "s2", "su_prog_t", "su_real_t"),
                 ("up", "Séances d'UP", "s2", "up_prog", "up_real"),
                 ("fo", "Formations / conférences", "s2", "fo_prog", "fo_real"),
                 ("co", "Concertations", "s3", "co_prog", "co_real")]

    def ligne_rap(b, a):
        vals = {}
        for k, _lib, sec, kp, kr in INDIC_RAP:
            r = (b.get(sec) or {}).get(a["cle"]) or {}
            prog, real = n0(r.get(kp)), n0(r.get(kr))
            vals[k] = {"prog": prog, "real": real, "taux": round(100.0 * real / prog, 1) if prog else None}
        tp = sum(v["prog"] for v in vals.values())
        tr = sum(v["real"] for v in vals.values())
        return {"lib": a.get("lib") or "", "nom": a.get("nom") or "", "zone": a.get("zone") or "", "vals": vals,
                "prog": tp, "real": tr, "taux": round(100.0 * tr / tp, 1) if tp else None}

    def tableau_rap(annee, periode, cs_id=None):
        """Programmation et réalisation des activités pédagogiques, CCS d'abord puis CP, par circonscription.
        DDEMP : bilan transmis par la CS (niveau CS, même période) s'il existe, sinon calcul sur les données reçues."""
        out = []
        for c in H.jur_cs_liste():
            if cs_id and c["id"] != cs_id:
                continue
            if config.EDITION == "cs" and H.jur_cs_courante() and c["id"] != H.jur_cs_courante()["id"]:
                continue
            b, source = None, "calcul"
            if config.EDITION == "ddemp":
                for it in reversed(H.jur_cs_section(c["id"], "cp_bilans", annee) or []):
                    if isinstance(it, dict) and it.get("periode") == periode and it.get("niveau") == "cs" \
                            and isinstance(it.get("bilan"), dict):
                        try:
                            b, source = totaux(json.loads(json.dumps(it["bilan"]))), "transmis"
                        except Exception:  # noqa: BLE001 — bilan transmis illisible : calcul
                            b = None
                        break
            if b is None:
                try:
                    b, _ = bilan_complet(annee, periode, c["id"], None)
                except Exception:  # noqa: BLE001 — CS sans zones ni données
                    continue
            acts = b.get("acteurs") or []
            ccs = next((a for a in acts if a["cle"] == "ccs"), None)
            out.append({"cs_id": c["id"], "cs_nom": c["nom"], "source": source,
                        "ccs": ligne_rap(b, ccs) if ccs else None,
                        "cps": [ligne_rap(b, a) for a in acts if a["cle"] != "ccs"]})
        return out

    H.jur_cp_tableau_rap = tableau_rap
    H.jur_cp_indicateurs_rap = [(k, lib) for k, lib, *_ in INDIC_RAP]


# ======================================================================== Excel (openpyxl)
class Excel:
    """Classeur des bilans : une feuille par tableau ; ligne 1 masquée = clés (pour « Charger »),
    colonne A masquée = clé de la ligne (acteur ou cours). Totaux et pourcentages en formules."""

    def __init__(self):
        from openpyxl import Workbook
        self.wb = Workbook()
        self.wb.remove(self.wb.active)

    def feuille(self, nom, titre, entete):
        from openpyxl.styles import Alignment, Font
        ws = self.wb.create_sheet(nom[:31])
        ws.sheet_properties.tabColor = "1F4E79"
        r = 2
        for ligne in entete:
            ws.cell(row=r, column=2, value=ligne).font = Font(bold=True, size=9)
            r += 1
        c = ws.cell(row=r + 1, column=2, value=titre)
        c.font = Font(bold=True, size=11, color="1F4E79")
        c.alignment = Alignment(wrap_text=False)
        ws._debut = r + 3
        return ws

    def tableau(self, ws, libelles, cles, lignes, editable=(), pourcent=(), cle_ligne=True, larges=None):
        """libelles[0] : intitulé de la colonne des lignes ; cles[0] = « acteur » (clé de ligne en colonne A)."""
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
        fin = Side(style="thin", color="7F8C9D")
        bord = Border(left=fin, right=fin, top=fin, bottom=fin)
        ent = PatternFill("solid", fgColor="E4ECF5")
        saisi = PatternFill("solid", fgColor="FFFFFF")
        calc = PatternFill("solid", fgColor="F2F4F7")
        r0 = ws._debut
        cols = [cles[0], "_lib"] + list(cles[1:])
        for j, k in enumerate(cols, start=1):
            ws.cell(row=1, column=j, value=k)
        ws.row_dimensions[1].hidden = True
        ws.column_dimensions["A"].hidden = True
        for j, lib in enumerate(libelles, start=2):
            c = ws.cell(row=r0, column=j, value=lib)
            c.font, c.fill, c.border = Font(bold=True, size=9), ent, bord
            c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
        ws.row_dimensions[r0].height = 42
        for i, ligne in enumerate(lignes, start=r0 + 1):
            ws.cell(row=i, column=1, value=ligne[0])
            for j, val in enumerate(ligne[1:], start=2):
                k = cols[j - 1] if j - 1 < len(cols) else ""
                c = ws.cell(row=i, column=j, value=val)
                c.border = bord
                if j == 2:
                    c.font = Font(bold=True, size=9)
                    c.alignment = Alignment(wrap_text=True, vertical="center")
                    continue
                c.fill = saisi if k in editable else calc
                c.alignment = Alignment(horizontal="center" if k not in ("designation", "observations", "texte", "lieu",
                                                                         "participants", "periode") else "left",
                                        vertical="center", wrap_text=True)
                if k in pourcent and isinstance(val, (int, float)):
                    c.value = val / 100.0
                    c.number_format = "0.00%"
        ws.column_dimensions["B"].width = 34
        for j in range(3, len(libelles) + 2):
            k = cols[j - 1] if j - 1 < len(cols) else ""
            ws.column_dimensions[get_column_letter(j)].width = (larges or {}).get(k) or (
                60 if k in ("designation", "observations") else 13)
        ws.freeze_panes = ws.cell(row=r0 + 1, column=3)
        ws.cell(row=r0 + len(lignes) + 2, column=2,
                value="Cases blanches : saisies (modifiables, rechargées par « Charger ») ; cases grises : calculées.").font = Font(
            italic=True, size=8, color="667085")

    def reponse(self, nom):
        buf = io.BytesIO()
        self.wb.save(buf)
        return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{nom}"'})


def lire_classeur(fichier, feuille):
    """Feuille produite par Excel.tableau → liste de dict {clé: valeur} (clé de ligne dans « acteur »).
    None si le fichier ou la feuille est illisible."""
    if not fichier or not getattr(fichier, "filename", ""):
        return None
    try:
        from openpyxl import load_workbook
        fichier.stream.seek(0)
        wb = load_workbook(io.BytesIO(fichier.read()), data_only=True, read_only=True)
    except Exception:  # noqa: BLE001
        return None
    if feuille not in wb.sheetnames:
        return None
    lignes = list(wb[feuille].iter_rows(values_only=True))
    if not lignes:
        return None
    cles = [str(c or "").strip() for c in lignes[0]]
    if not cles or cles[0] != "acteur":
        return None
    out = []
    debut = False
    for r in lignes[1:]:
        if not debut:
            # en-tête du tableau : la ligne dont la 2e cellule est l'intitulé de la colonne des lignes
            if r and len(r) > 1 and r[0] is None and r[1] not in (None, "") and any(x not in (None, "") for x in r[2:]):
                debut = True
            continue
        if r is None or all(x in (None, "") for x in r):
            continue
        d = {}
        for k, val in zip(cles, r):
            if not k:
                continue
            if k == "acteur":
                d[k] = str(val).strip() if val not in (None, "") else ""
            else:
                d[k] = val
        if d.get("acteur") == "" and "acteur" in cles and feuille not in ("Activites",):
            continue
        out.append(d)
    return out
