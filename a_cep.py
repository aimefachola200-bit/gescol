# -*- coding: utf-8 -*-
"""Examens (CEP) des applications « GESCOL Circonscription » (CS) et « GESCOL DDEMP ».

Source des chiffres : la section « cep » des paquets de transmission des écoles (jur_sections), lue avec
jur_calc.cep pour que tous les écrans donnent les mêmes résultats. La CS (ou la DDEMP) peut CORRIGER les
candidats / admis / effectifs de CM1 d'une école, ou importer les résultats officiels depuis Excel :
* la correction est conservée dans jur_cep_saisies (avec les chiffres d'origine transmis par l'école) ;
* elle est aussi recopiée dans la section « cep » de l'école (source « saisie », liste nominative conservée),
  pour qu'elle parte dans le paquet envoyé à la DDEMP.
Tant qu'une correction existe, elle prime sur les chiffres transmis (même après une nouvelle transmission).

Pages : jur_cep (tableau des candidats et résultats), jur_cep_ecole (détail / correction d'une école),
jur_cep_import (résultats officiels Excel), jur_cep_prevision (candidats de l'année suivante = élèves de CM1),
jur_cep_frais (frais de relevés : barème par année, montant dû, versements, reste à payer).
Fonction exposée : H.jur_cep_stats(annee, cs_id=None, ...) → dict (par école, par zone, par CS, global).
"""
import json
import re
from collections import OrderedDict
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether
from reportlab.platypus.flowables import Flowable

import config
import jur_calc as JC
import m_juridiction as J
from db import ex, q

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_cep_saisies (
    ecole_id INTEGER NOT NULL, annee TEXT NOT NULL,
    candidats_g INTEGER, candidats_f INTEGER,
    admis_g INTEGER, admis_f INTEGER,          -- NULL = résultats inconnus
    cm1_g INTEGER, cm1_f INTEGER,              -- NULL = garder les chiffres transmis
    origine TEXT,                              -- JSON : chiffres transmis par l'école avant la 1re correction
    source TEXT,                               -- saisie | import
    observation TEXT, maj TEXT, maj_par TEXT,
    PRIMARY KEY (ecole_id, annee));
CREATE TABLE IF NOT EXISTS jur_cep_baremes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, annee TEXT NOT NULL,
    montant_candidat INTEGER NOT NULL DEFAULT 0,   -- FCFA par candidat (relevé de notes)
    forfait_ecole INTEGER NOT NULL DEFAULT 0,      -- FCFA par école ayant présenté des candidats
    reference TEXT, observation TEXT, cree_le TEXT, cree_par TEXT);
CREATE TABLE IF NOT EXISTS jur_cep_versements (
    ecole_id INTEGER NOT NULL, annee TEXT NOT NULL, montant INTEGER NOT NULL DEFAULT 0,
    date_versement TEXT, reference TEXT, observation TEXT, maj TEXT, maj_par TEXT,
    PRIMARY KEY (ecole_id, annee));
"""

NUM = ("candidats_g", "candidats_f", "admis_g", "admis_f", "cm1_g", "cm1_f")
SEUIL_ELEVE = 80          # taux « élevé » par défaut (modifiable dans les filtres)
EFFECTIF_MIN = 35         # « plus de 35 candidats »
SEUIL_FAIBLE = 50         # écoles ayant moins de 50 %


# ======================================================================== utilitaires
def annee_suivante(a):
    try:
        y = int(str(a)[:4])
    except ValueError:
        return a
    return f"{y + 1}-{y + 2}"


def session_de(a):
    """« 2026-2027 » → « 2027 » (session du CEP passée en fin d'année scolaire)."""
    m = re.match(r"^\d{4}-(\d{4})$", str(a or ""))
    return m.group(1) if m else str(a or "")


def pct(v):
    """Pourcentage à la française : 75,4 % (— si non calculable)."""
    return "—" if v is None else f"{v:.1f}".replace(".", ",") + " %"


def nb(v):
    """Entier lisible (— si inconnu)."""
    return "—" if v is None else f"{int(v):,}".replace(",", " ")


def esc(t):
    """Texte sûr pour un Paragraph ReportLab."""
    return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def lire_entier(v, vide_ok=True):
    """Valeur saisie → (entier | None, message d'erreur | None). Entiers ≥ 0 uniquement."""
    if v is None or str(v).strip() == "":
        return None, (None if vide_ok else "valeur obligatoire")
    s = str(v).strip().replace(" ", "").replace(" ", "")
    try:
        f = float(s.replace(",", "."))
    except ValueError:
        return None, f"« {v} » n'est pas un nombre"
    if f != int(f):
        return None, f"« {v} » n'est pas un nombre entier"
    if f < 0:
        return None, f"« {v} » est négatif"
    if f > 100000:
        return None, f"« {v} » est trop grand"
    return int(f), None


def _section_brute(ecole_id, a):
    r = q("SELECT donnees, source, maj FROM jur_sections WHERE ecole_id=? AND annee=? AND section='cep'", (ecole_id, a), un=True)
    return (json.loads(r["donnees"]), r["source"], r["maj"]) if r else (None, None, None)


def _cm1_effectifs(eff):
    """Élèves de CM1 d'après la section « effectifs » (si la section « cep » ne les donne pas)."""
    if not eff:
        return None
    n = JC.effectifs(eff)["par_niveau"].get("CM1")
    return (n[0], n[1]) if n else (0, 0)


def effectif(sec, corr=None, eff=None):
    """Section « cep » effective : chiffres transmis, puis correction de la CS / DDEMP par-dessus."""
    d = dict(sec or {})
    if "cm1_g" not in d and "cm1_f" not in d:
        c = _cm1_effectifs(eff)
        if c:
            d["cm1_g"], d["cm1_f"] = c
    if corr:
        d["candidats_g"], d["candidats_f"] = corr["candidats_g"], corr["candidats_f"]
        d["admis_g"], d["admis_f"] = corr["admis_g"], corr["admis_f"]
        if corr["cm1_g"] is not None or corr["cm1_f"] is not None:
            d["cm1_g"], d["cm1_f"] = corr["cm1_g"] or 0, corr["cm1_f"] or 0
    return d


# ======================================================================== regroupements
def _cle_zone(l):
    return f"{l['cs_id'] or 0}:{l['zone_id'] or 0}"


def grouper(lignes, agreger):
    """Regroupe des lignes d'école (ordonnées CS → zone → école) : (zones, cs, global).
    zones / cs = listes de dict (cs_id, cs_nom, zone_id, zone_nom, nb_lignes + agrégats)."""
    zs, css = OrderedDict(), OrderedDict()
    for l in lignes:
        zs.setdefault(_cle_zone(l), []).append(l)
        css.setdefault(l["cs_id"] or 0, []).append(l)
    zones = []
    for k, ls in zs.items():
        zones.append(dict(agreger(ls), cle=k, cs_id=ls[0]["cs_id"], cs_nom=ls[0]["cs_nom"] or "",
                          zone_id=ls[0]["zone_id"], zone_nom=ls[0]["zone_nom"] or "Sans zone pédagogique"))
    cs = [dict(agreger(ls), cs_id=k or None, cs_nom=ls[0]["cs_nom"] or "Sans circonscription") for k, ls in css.items()]
    return zones, cs, agreger(lignes)


def rangees(lignes, zones, cs, glob, vue="ecoles", ddemp=False):
    """Lignes d'affichage du tableau : écoles, sous-total de zone, (DDEMP) total de CS, total général."""
    par_z = {z["cle"]: z for z in zones}
    par_cs = {c["cs_id"] or 0: c for c in cs}
    out, n, zone_cour, cs_cour = [], 0, None, None

    def fermer_zone():
        if zone_cour is not None:
            z = par_z[zone_cour]
            lib = f"Sous-total {z['zone_nom']}" + (f" – CS {z['cs_nom']}" if ddemp else "")
            out.append({"genre": "zone", "libelle": lib, "d": z})

    def fermer_cs():
        if ddemp and cs_cour is not None:
            c = par_cs[cs_cour]
            out.append({"genre": "cs", "libelle": f"Total CS {c['cs_nom']}", "d": c})

    for l in lignes:
        k, kc = _cle_zone(l), l["cs_id"] or 0
        if k != zone_cour:
            fermer_zone()
            if kc != cs_cour:
                fermer_cs()
                cs_cour = kc
            zone_cour = k
        if vue == "ecoles":
            n += 1
            out.append({"genre": "ecole", "n": n, "libelle": l["nom"], "d": l})
    fermer_zone()
    fermer_cs()
    if lignes:
        out.append({"genre": "total", "libelle": "TOTAL GÉNÉRAL", "d": glob})
    return out


# ======================================================================== statistiques CEP
def _agreger_cep(lignes):
    """Agrégat d'un groupe d'écoles. Les taux ne portent que sur les écoles dont les résultats sont connus."""
    res = [l for l in lignes if l["admis"] is not None]
    o = {"nb_ecoles": len(lignes), "nb_donnees": sum(1 for l in lignes if l["donnees"]),
         "nb_presentes": sum(1 for l in lignes if l["presente"]),
         "nb_resultats": sum(1 for l in res if l["presente"])}
    for k in ("candidats_g", "candidats_f", "cm1_g", "cm1_f"):
        o[k] = sum(l[k] for l in lignes)
    o["candidats"] = o["candidats_g"] + o["candidats_f"]
    o["cm1"] = o["cm1_g"] + o["cm1_f"]
    o["candidats_res_g"] = sum(l["candidats_g"] for l in res)
    o["candidats_res_f"] = sum(l["candidats_f"] for l in res)
    o["candidats_res"] = o["candidats_res_g"] + o["candidats_res_f"]
    if res:
        o["admis_g"] = sum(l["admis_g"] for l in res)
        o["admis_f"] = sum(l["admis_f"] for l in res)
        o["admis"] = o["admis_g"] + o["admis_f"]
    else:
        o["admis_g"] = o["admis_f"] = o["admis"] = None
    o["taux_g"] = JC.taux(o["admis_g"], o["candidats_res_g"]) if res else None
    o["taux_f"] = JC.taux(o["admis_f"], o["candidats_res_f"]) if res else None
    o["taux"] = JC.taux(o["admis"], o["candidats_res"]) if res else None
    o["pct_presentes"] = JC.taux(o["nb_presentes"], o["nb_ecoles"])
    o["resultats_incomplets"] = o["nb_resultats"] < o["nb_presentes"]
    return o


def stats(annee=None, cs_id=None, zone_id=None, secteur=None, seuil_eleve=SEUIL_ELEVE, effectif_min=EFFECTIF_MIN):
    """Statistiques du CEP pour le tableau de bord et les écrans CEP.

    Renvoie {"annee", "session", "ecoles": [ligne par école], "zones": [...], "cs": [...], "global": {...},
    "par_ecole": {ecole_id: ligne}, "par_zone": {zone_id: agrégat}, "par_cs": {cs_id: agrégat},
    "eleves": [écoles à taux élevé (> effectif_min candidats)], "faibles": [écoles < 50 %], ...}.
    Ligne d'école : ecole_id, code, nom, type, secteur, cs_id, cs_nom, zone_id, zone_nom, candidats_g/f, candidats,
    admis_g/f, admis (None = résultats inconnus), taux_g/f, taux, cm1_g/f, cm1, presente, donnees, corrige, source.
    Agrégat : nb_ecoles (écoles primaires), nb_presentes, pct_presentes, candidats_g/f, candidats, admis_g/f, admis,
    taux_g/f, taux (sur les écoles dont les résultats sont connus), candidats_res*, nb_resultats, cm1_g/f, cm1."""
    a = annee or J.annee()
    secs = J.sections("cep", a)
    effs = J.sections("effectifs", a)
    corrs = {r["ecole_id"]: dict(r) for r in q("SELECT * FROM jur_cep_saisies WHERE annee=?", (a,))}
    sources = {r["ecole_id"]: r["source"] for r in
               q("SELECT ecole_id, source FROM jur_sections WHERE annee=? AND section='cep'", (a,))}
    lignes = []
    for e in J.ecoles(cs_id=cs_id, zone_id=zone_id, secteur=secteur):
        sec, corr = secs.get(e["id"]), corrs.get(e["id"])
        if e["type"] != "EP" and not sec and not corr:
            continue                       # maternelles / espaces enfance : pas de CEP
        d = effectif(sec, corr, effs.get(e["id"]))
        c = JC.cep(d)
        lignes.append({
            "ecole_id": e["id"], "code": e["code"], "nom": e["nom"], "type": e["type"], "secteur": e["secteur"],
            "cs_id": e["cs_id"], "cs_nom": e["cs_nom"] or "", "zone_id": e["zone_id"], "zone_nom": e["zone_nom"] or "",
            "candidats_g": c["candidats_g"], "candidats_f": c["candidats_f"], "candidats": c["candidats"],
            "admis_g": c["admis_g"], "admis_f": c["admis_f"], "admis": c["admis"],
            "taux_g": c["taux_g"], "taux_f": c["taux_f"], "taux": c["taux"],
            "cm1_g": c["cm1_g"], "cm1_f": c["cm1_f"], "cm1": c["cm1"],
            "presente": c["candidats"] > 0, "donnees": bool(sec or corr), "corrige": bool(corr),
            "source": (corr["source"] if corr else sources.get(e["id"])) or "",
            "session": str((d or {}).get("session") or session_de(a))})
    zones, cs, glob = grouper(lignes, _agreger_cep)
    eleves = sorted([l for l in lignes if l["taux"] is not None and l["candidats"] > effectif_min
                     and l["taux"] >= seuil_eleve], key=lambda l: (-l["taux"], -l["candidats"]))
    faibles = sorted([l for l in lignes if l["taux"] is not None and l["candidats"] > 0 and l["taux"] < SEUIL_FAIBLE],
                     key=lambda l: (l["taux"], l["nom"]))
    return {"annee": a, "session": session_de(a), "ecoles": lignes, "zones": zones, "cs": cs, "global": glob,
            "par_ecole": {l["ecole_id"]: l for l in lignes},
            "par_zone": {z["zone_id"]: z for z in zones if z["zone_id"]},
            "par_cs": {c["cs_id"]: c for c in cs if c["cs_id"]},
            "eleves": eleves, "faibles": faibles, "seuil_eleve": seuil_eleve, "effectif_min": effectif_min,
            "seuil_faible": SEUIL_FAIBLE}


# ======================================================================== prévision
def _agreger_prev(lignes):
    o = {"nb_ecoles": len(lignes), "nb_cm1": sum(1 for l in lignes if l["cm1"] > 0),
         "nb_presentes": sum(1 for l in lignes if l["candidats"] > 0)}
    for k in ("cm1_g", "cm1_f", "cm1", "candidats_g", "candidats_f", "candidats"):
        o[k] = sum(l[k] for l in lignes)
    o["ecart"] = o["cm1"] - o["candidats"]
    o["evolution"] = JC.taux(o["ecart"], o["candidats"])
    return o


def prevision(annee=None, cs_id=None, zone_id=None, secteur=None):
    """Candidats prévus au CEP de l'année suivante = élèves de CM1 de cette année (passage automatique au CM2)."""
    st = stats(annee, cs_id, zone_id, secteur)
    lignes = []
    for l in st["ecoles"]:
        if l["cm1"] <= 0 and l["candidats"] <= 0:
            continue
        lignes.append(dict(l, ecart=l["cm1"] - l["candidats"], evolution=JC.taux(l["cm1"] - l["candidats"], l["candidats"])))
    zones, cs, glob = grouper(lignes, _agreger_prev)
    sans = [l for l in lignes if l["cm1"] == 0]
    return {"annee": st["annee"], "annee_suivante": annee_suivante(st["annee"]), "session": st["session"],
            "session_suivante": session_de(annee_suivante(st["annee"])), "ecoles": lignes, "zones": zones,
            "cs": cs, "global": glob, "sans_cm1": sans}


# ======================================================================== frais de relevés
def bareme(a):
    """Barème en vigueur pour l'année (dernier enregistré) ou None."""
    r = q("SELECT * FROM jur_cep_baremes WHERE annee=? ORDER BY id DESC LIMIT 1", (a,), un=True)
    return dict(r) if r else None


def _bareme_cs(cs_id, a):
    """(DDEMP) Barème transmis par une CS dans sa section « frais_releves »."""
    s = J.cs_section(cs_id, "frais_releves", a) if cs_id else None
    b = (s or {}).get("bareme")
    if not b:
        return None
    return {"montant_candidat": JC.entier(b.get("montant_candidat")), "forfait_ecole": JC.entier(b.get("forfait_ecole")),
            "reference": b.get("reference") or "", "origine": "cs"}


def _agreger_frais(lignes):
    o = {"nb_ecoles": len(lignes), "nb_soldees": sum(1 for l in lignes if l["du"] > 0 and l["reste"] <= 0)}
    for k in ("candidats", "du", "verse", "reste"):
        o[k] = sum(l[k] for l in lignes)
    o["taux_recouvrement"] = JC.taux(o["verse"], o["du"])
    return o


def frais(annee=None, cs_id=None, zone_id=None, secteur=None):
    """Montant dû par école = candidats × montant par candidat + forfait (écoles ayant présenté des candidats)."""
    st = stats(annee, cs_id, zone_id, secteur)
    a = st["annee"]
    b_local = bareme(a)
    vers = {r["ecole_id"]: dict(r) for r in q("SELECT * FROM jur_cep_versements WHERE annee=?", (a,))}
    ddemp = config.EDITION == "ddemp"
    cache_cs = {}
    lignes, sans_bareme = [], 0
    for l in st["ecoles"]:
        b = b_local
        v = vers.get(l["ecole_id"])
        if ddemp and (b is None or v is None):
            if l["cs_id"] not in cache_cs:
                cache_cs[l["cs_id"]] = (_bareme_cs(l["cs_id"], a),
                                        (J.cs_section(l["cs_id"], "frais_releves", a) or {}).get("versements") or {})
            b_cs, v_cs = cache_cs[l["cs_id"]]
            b = b or b_cs
            if v is None and l["code"] in v_cs:
                x = v_cs[l["code"]]
                v = {"montant": JC.entier(x.get("montant")), "date_versement": x.get("date_versement") or "",
                     "reference": x.get("reference") or "", "observation": x.get("observation") or "", "origine": "cs"}
        if l["candidats"] <= 0 and not v:
            continue
        if b is None and l["candidats"] > 0:
            sans_bareme += 1
        unit = (b or {}).get("montant_candidat", 0)
        forfait = (b or {}).get("forfait_ecole", 0) if l["candidats"] > 0 else 0
        du = l["candidats"] * unit + forfait
        verse = (v or {}).get("montant", 0) or 0
        lignes.append(dict(l, unitaire=unit, forfait=forfait, du=du, verse=verse, reste=du - verse,
                           date_versement=(v or {}).get("date_versement") or "", reference=(v or {}).get("reference") or "",
                           observation=(v or {}).get("observation") or "", versement_cs=(v or {}).get("origine") == "cs",
                           bareme_cs=(b or {}).get("origine") == "cs"))
    zones, cs, glob = grouper(lignes, _agreger_frais)
    return {"annee": a, "session": st["session"], "bareme": b_local, "ecoles": lignes, "zones": zones, "cs": cs,
            "global": glob, "sans_bareme": sans_bareme}


def statut_frais(l):
    if l["du"] <= 0 and l["verse"] <= 0:
        return "—"
    if l["reste"] <= 0:
        return "Soldé" if l["reste"] == 0 else "Trop-perçu"
    return "Partiel" if l["verse"] > 0 else "Non versé"


# ======================================================================== corrections
def enregistrer_correction(ecole_id, a, valeurs, source="saisie", observation="", par=""):
    """Enregistre une correction (valeurs = dict NUM ; admis None = résultats inconnus ; cm1 None = inchangé)
    et la recopie dans la section « cep » de l'école (liste nominative et autres clés conservées)."""
    sec, src, _ = _section_brute(ecole_id, a)
    ancienne = q("SELECT origine FROM jur_cep_saisies WHERE ecole_id=? AND annee=?", (ecole_id, a), un=True)
    if ancienne:
        origine = ancienne["origine"]
    else:
        origine = json.dumps({k: (sec or {}).get(k) for k in NUM + ("session",)} if sec else None, ensure_ascii=False)
    ex("INSERT INTO jur_cep_saisies (ecole_id, annee, candidats_g, candidats_f, admis_g, admis_f, cm1_g, cm1_f, origine, "
       "source, observation, maj, maj_par) VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'),?) "
       "ON CONFLICT(ecole_id, annee) DO UPDATE SET candidats_g=excluded.candidats_g, candidats_f=excluded.candidats_f, "
       "admis_g=excluded.admis_g, admis_f=excluded.admis_f, cm1_g=COALESCE(excluded.cm1_g, jur_cep_saisies.cm1_g), "
       "cm1_f=COALESCE(excluded.cm1_f, jur_cep_saisies.cm1_f), source=excluded.source, "
       "observation=COALESCE(NULLIF(excluded.observation,''), jur_cep_saisies.observation), maj=excluded.maj, maj_par=excluded.maj_par",
       (ecole_id, a, valeurs["candidats_g"], valeurs["candidats_f"], valeurs["admis_g"], valeurs["admis_f"],
        valeurs.get("cm1_g"), valeurs.get("cm1_f"), origine, source, observation or "", par))
    corr = dict(q("SELECT * FROM jur_cep_saisies WHERE ecole_id=? AND annee=?", (ecole_id, a), un=True))
    nouv = dict(sec or {})
    nouv.setdefault("session", session_de(a))
    nouv.setdefault("liste", [])
    for k in ("candidats_g", "candidats_f", "admis_g", "admis_f"):
        nouv[k] = corr[k]
    for k in ("cm1_g", "cm1_f"):
        if corr[k] is not None:
            nouv[k] = corr[k]
    J.ecrire_section(ecole_id, "cep", nouv, a, source="saisie")


def annuler_correction(ecole_id, a):
    """Supprime la correction ; remet dans la section « cep » les chiffres transmis par l'école."""
    corr = q("SELECT * FROM jur_cep_saisies WHERE ecole_id=? AND annee=?", (ecole_id, a), un=True)
    if not corr:
        return False
    sec, src, _ = _section_brute(ecole_id, a)
    origine = json.loads(corr["origine"] or "null")
    if src == "saisie":                       # la section porte encore la correction : on la défait
        if origine:
            nouv = dict(sec or {})
            for k in NUM:
                if k in origine:
                    nouv[k] = origine[k]
                else:
                    nouv.pop(k, None)
            J.ecrire_section(ecole_id, "cep", nouv, a, source="transmission")
        elif not (sec or {}).get("liste"):    # section créée par la saisie : on l'efface
            ex("DELETE FROM jur_sections WHERE ecole_id=? AND annee=? AND section='cep'", (ecole_id, a))
    ex("DELETE FROM jur_cep_saisies WHERE ecole_id=? AND annee=?", (ecole_id, a))
    return True


def controler(valeurs):
    """Contrôles métier : admis ≤ candidats ; admis G et F renseignés ensemble. Liste de messages."""
    err = []
    if (valeurs["admis_g"] is None) != (valeurs["admis_f"] is None):
        err.append("Renseignez les admis garçons ET filles (ou laissez les deux vides si les résultats ne sont pas connus).")
    if valeurs["admis_g"] is not None and valeurs["candidats_g"] is not None and valeurs["admis_g"] > valeurs["candidats_g"]:
        err.append(f"Admis garçons ({valeurs['admis_g']}) supérieurs aux candidats garçons ({valeurs['candidats_g']}).")
    if valeurs["admis_f"] is not None and valeurs["candidats_f"] is not None and valeurs["admis_f"] > valeurs["candidats_f"]:
        err.append(f"Admis filles ({valeurs['admis_f']}) supérieures aux candidates filles ({valeurs['candidats_f']}).")
    return err


# ======================================================================== PDF : signature du responsable
def cachet_structure():
    """Cachet de la structure (service de direction défini dans « Cachets et signatures ») ou None."""
    try:
        r = q("SELECT cachet_sup, cachet_inf, cachet_centre, cachet_couleur FROM jur_services "
              "WHERE actif=1 AND (COALESCE(cachet_sup,'')<>'' OR COALESCE(cachet_centre,'')<>'') "
              "ORDER BY CASE WHEN niveau=? THEN 0 ELSE 1 END, "
              "CASE WHEN code IN ('direction','ccs','responsable','dd','ddemp') THEN 0 ELSE 1 END, ordre, id LIMIT 1",
              (config.EDITION,), un=True)
    except Exception:  # noqa: BLE001  (table absente)
        return None
    if not r:
        return None
    return (r["cachet_sup"] or "", r["cachet_inf"] or "", r["cachet_centre"] or "", r["cachet_couleur"] or "bleu")


class SignatureResponsable(Flowable):
    """Bloc « Lieu, le … / titre / cachet + signature digitale / nom » du responsable de la structure."""

    def __init__(self, largeur, ville, titre, nom, image=None, cachet_=None):
        super().__init__()
        self.largeur, self.ville, self.titre, self.nom = largeur, ville, titre, nom
        self.image, self.cachet = image, cachet_
        self.height = 42 * mm

    def wrap(self, *_):
        return self.largeur, self.height

    def draw(self):
        import cachet as _cachet
        c = self.canv
        x = self.largeur * 0.78
        y = self.height - 8
        c.setFont("Helvetica", 8.5)
        c.drawCentredString(x, y, f"{self.ville or '……………'}, le {date.today().strftime('%d/%m/%Y')}")
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(x, y - 12, self.titre or "Le Responsable")
        if self.cachet:
            _cachet.dessiner(c, x - 14 * mm, y - 12 - 15 * mm, 12 * mm, *self.cachet)
        if self.image is not None:
            c.drawImage(self.image, x - 22 * mm, y - 12 - 24 * mm, 44 * mm, 17 * mm, preserveAspectRatio=True, mask="auto")
        if self.nom:
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(x, y - 12 - 30 * mm, self.nom)


# ======================================================================== Flask
def enregistrer(app, H):
    H.schema(SCHEMA)
    H.jur_cep_stats = stats
    H.jur_cep_prevision = prevision
    H.jur_cep_frais = frais

    def garde():
        if not config.juridiction():
            abort(404)

    def ecrire_requis():
        if not H.peut("jur_cep"):
            abort(403)

    def ddemp():
        return config.EDITION == "ddemp"

    def filtres():
        """Filtres communs (GET) : année, CS (DDEMP), zone, secteur, vue."""
        f = request.args
        a = f.get("annee") or J.annee()
        if not re.match(r"^\d{4}-\d{4}$", a):
            a = J.annee()
        cs_id = (int(f.get("cs")) if (f.get("cs") or "").isdigit() else None) if ddemp() else None
        zone_id = int(f.get("zone")) if (f.get("zone") or "").isdigit() else None
        secteur = f.get("secteur") if f.get("secteur") in J.SECTEURS else None
        vue = "synthese" if f.get("vue") == "synthese" else "ecoles"
        try:
            seuil = max(0.0, min(100.0, float((f.get("seuil") or str(SEUIL_ELEVE)).replace(",", "."))))
        except ValueError:
            seuil = float(SEUIL_ELEVE)
        return {"annee": a, "cs_id": cs_id, "zone_id": zone_id, "secteur": secteur, "vue": vue, "seuil": seuil}

    def args_url(fl, **extra):
        """Paramètres d'URL des filtres (pour les liens d'export)."""
        d = {"annee": fl["annee"], "cs": fl["cs_id"] or "", "zone": fl["zone_id"] or "", "secteur": fl["secteur"] or "",
             "vue": fl["vue"], "seuil": f"{fl['seuil']:g}"}
        d.update(extra)
        return {k: v for k, v in d.items() if v not in ("", None)}

    def contexte_filtres(fl):
        annees = sorted(set(J.annees()) | {fl["annee"]}, reverse=True)
        return dict(fl=fl, annees=annees, cs_liste=J.cs_liste(), zones=J.zones(fl["cs_id"]) if fl["cs_id"] else J.zones(),
                    args_url=args_url, pct=pct, nb=nb, DDEMP=ddemp())

    def libelle_filtres(fl):
        """Infos d'en-tête des PDF / Excel décrivant les filtres appliqués."""
        infos = [("Année scolaire", fl["annee"])]
        if fl["cs_id"]:
            c = J.cs_par_id(fl["cs_id"])
            infos.append(("Circonscription", c["nom"] if c else "?"))
        if fl["zone_id"]:
            z = q("SELECT nom FROM jur_zones WHERE id=?", (fl["zone_id"],), un=True)
            infos.append(("Zone pédagogique", z["nom"] if z else "?"))
        if fl["secteur"]:
            infos.append(("Secteur", J.SECTEURS[fl["secteur"]]))
        return infos

    def entete_pdf():
        s = J.structure() or {}
        if ddemp():
            return [("DDEMP", s.get("departement") or "")]
        return [("DDEMP", s.get("departement") or ""), ("CS", s.get("cs") or "")]

    def signature_pdf(largeur):
        s = J.structure() or {}
        titre = s.get("responsable_titre") or ("Le Directeur Départemental" if ddemp() else "Le Chef de la Circonscription Scolaire")
        img = H.pdfs.image_data_url(H.signature("jur:structure:responsable"))
        return SignatureResponsable(largeur, s.get("ville") or "", titre, s.get("responsable_nom") or "", img, cachet_structure())

    def titre_haut(titre, fl):
        s = J.structure() or {}
        return [s.get("nom") or config.NOMS_APPLI.get(config.EDITION, "GESCOL"), titre] + \
            [" · ".join(f"{a} : {b}" for a, b in libelle_filtres(fl))]

    from reportlab.lib.pagesizes import A4, landscape
    LARGEUR_PAYSAGE = landscape(A4)[0] - 24 * mm

    # ------------------------------------------------------------------ tableau des candidats et résultats
    @app.route("/juridiction/cep")
    @H.connexion_requise()
    def jur_cep():
        garde()
        fl = filtres()
        st = stats(fl["annee"], fl["cs_id"], fl["zone_id"], fl["secteur"], seuil_eleve=fl["seuil"])
        lignes = rangees(st["ecoles"], st["zones"], st["cs"], st["global"], fl["vue"], ddemp())
        export = request.args.get("export")
        if export == "xlsx":
            return export_cep_xlsx(st, lignes, fl)
        if export == "pdf":
            return export_cep_pdf(st, lignes, fl)
        return render_template("jur_cep.html", st=st, lignes=lignes, **contexte_filtres(fl))

    def cellules_cep(r):
        d = r["d"]
        if r["genre"] == "ecole":
            ecoles_txt = "Oui" if d["presente"] else ("Non" if d["donnees"] else "Non reçu")
        else:
            ecoles_txt = f"{d['nb_presentes']}/{d['nb_ecoles']} ({pct(d['pct_presentes'])})"
        return [r.get("n", ""), r["libelle"] + (" *" if r["genre"] == "ecole" and d["corrige"] else ""),
                (J.SECTEURS.get(d["secteur"], "") if r["genre"] == "ecole" else ""), ecoles_txt,
                d["candidats_g"], d["candidats_f"], d["candidats"],
                nb(d["admis_g"]), nb(d["admis_f"]), nb(d["admis"]), pct(d["taux_g"]), pct(d["taux_f"]), pct(d["taux"])]

    def export_cep_pdf(st, lignes, fl):
        cols = [["N°", "École", "Secteur", "Écoles ayant présenté", "Candidats présentés", None, None, "Admis", None, None,
                 "Taux de réussite", None, None],
                ["^", "^", "^", "^", "G", "F", "T", "G", "F", "T", "G", "F", "T"]]
        corps = [cellules_cep(r) for r in lignes[:-1]] if lignes else []
        total = cellules_cep(lignes[-1]) if lignes else None
        surl = {i: ("#D9E4F2" if r["genre"] == "cs" else "#EEF3FA") for i, r in enumerate(lignes[:-1]) if r["genre"] != "ecole"}
        P = H.pdfs.paragraphe
        g_ = st["global"]
        apres = [P("", 4),
                 P(f"<b>Écoles ayant présenté des candidats :</b> {g_['nb_presentes']} sur {g_['nb_ecoles']} écoles primaires "
                   f"({pct(g_['pct_presentes'])}). <b>Taux de réussite global :</b> {pct(g_['taux'])} "
                   f"(garçons {pct(g_['taux_g'])}, filles {pct(g_['taux_f'])}).", 8.5)]
        groupes = st["cs"] if ddemp() else st["zones"]
        if groupes:
            nomg = "CS" if ddemp() else "Zone pédagogique"
            data = [[nomg, "Écoles", "Ayant présenté", "%", "Candidats", "Admis", "Taux G", "Taux F", "Taux"]]
            for z in groupes:
                data.append([esc(z["cs_nom"] if ddemp() else z["zone_nom"]), z["nb_ecoles"], z["nb_presentes"],
                             pct(z["pct_presentes"]), z["candidats"], nb(z["admis"]), pct(z["taux_g"]), pct(z["taux_f"]),
                             pct(z["taux"])])
            apres += [P(f"<b>Taux de réussite par {'circonscription' if ddemp() else 'zone pédagogique'}</b>", 9),
                      H.pdfs.mini_tableau(data, [x * mm for x in (60, 18, 22, 18, 20, 18, 18, 18, 18)])]
        for titre_l, lst in ((f"Écoles ayant un taux de réussite d'au moins {fl['seuil']:g} % avec plus de "
                              f"{st['effectif_min']} candidats", st["eleves"]),
                             (f"Écoles ayant moins de {SEUIL_FAIBLE} % de réussite", st["faibles"])):
            bloc = [P(f"<b>{titre_l}</b> ({len(lst)})", 9)]
            if lst:
                data = [["N°", "École"] + (["CS"] if ddemp() else []) + ["Zone", "Candidats", "Admis", "Taux"]]
                for i, l in enumerate(lst, 1):
                    data.append([i, esc(l["nom"])] + ([esc(l["cs_nom"])] if ddemp() else []) +
                                [esc(l["zone_nom"]), l["candidats"], nb(l["admis"]), pct(l["taux"])])
                bloc.append(H.pdfs.mini_tableau(data, [x * mm for x in [8, 70] + ([30] if ddemp() else []) + [40, 20, 18, 18]]))
            else:
                bloc.append(P("Aucune école.", 8))
            apres.append(KeepTogether(bloc))   # titre et tableau sur la même page
        apres.append(signature_pdf(LARGEUR_PAYSAGE))
        notes = ["Taux = admis / candidats des écoles dont les résultats sont connus. « * » : chiffres corrigés par "
                 + ("la DDEMP ou la CS." if ddemp() else "la circonscription.")]
        if g_["resultats_incomplets"]:
            notes.append(f"Résultats connus pour {g_['nb_resultats']} des {g_['nb_presentes']} écoles ayant présenté des candidats.")
        pdf = H.pdfs.document_tableau(
            f"EFFECTIFS DES CANDIDATS ET RÉSULTATS AU CEP – SESSION {st['session']}", cols, corps,
            sous_titre=("Tableau par circonscription et zone pédagogique" if ddemp() else "Tableau par zone pédagogique"),
            infos=libelle_filtres(fl), largeurs=[7, 62, 14, 24, 11, 11, 12, 11, 11, 12, 14, 14, 14], paysage=True,
            infos_haut=entete_pdf(), total=total, taille=7, apres=apres, notes_bas=notes, surlignes=surl,
            alignements=None)
        H.journal("jur_cep_pdf", fl["annee"])
        return H.pdf_reponse(pdf, f"cep_{st['session']}.pdf")

    def export_cep_xlsx(st, lignes, fl):
        ent = ["N°", "Niveau"] + (["CS"] if ddemp() else []) + ["Zone pédagogique", "Code", "École", "Secteur",
               "Écoles (total)", "Écoles ayant présenté", "% écoles ayant présenté", "Candidats G", "Candidats F",
               "Candidats T", "Admis G", "Admis F", "Admis T", "Taux G (%)", "Taux F (%)", "Taux T (%)", "Corrigé"]
        genres = {"ecole": "École", "zone": "Sous-total zone", "cs": "Total CS", "total": "Total général"}
        rows = []
        for r in lignes:
            d = r["d"]
            e = r["genre"] == "ecole"
            rows.append([r.get("n", ""), genres[r["genre"]]] + ([d.get("cs_nom", "")] if ddemp() else []) +
                        [d.get("zone_nom", "") if r["genre"] != "cs" and r["genre"] != "total" else "",
                         d["code"] if e else "", r["libelle"], J.SECTEURS.get(d.get("secteur"), "") if e else "",
                         1 if e else d["nb_ecoles"], (1 if d["presente"] else 0) if e else d["nb_presentes"],
                         None if e else d["pct_presentes"], d["candidats_g"], d["candidats_f"], d["candidats"],
                         d["admis_g"], d["admis_f"], d["admis"], d["taux_g"], d["taux_f"], d["taux"],
                         ("oui" if d["corrige"] else "") if e else ""])
        grp = st["cs"] if ddemp() else st["zones"]
        synth = [[(z["cs_nom"] if ddemp() else z["zone_nom"]), z["nb_ecoles"], z["nb_presentes"], z["pct_presentes"],
                  z["candidats_g"], z["candidats_f"], z["candidats"], z["admis_g"], z["admis_f"], z["admis"],
                  z["taux_g"], z["taux_f"], z["taux"]] for z in grp]
        g_ = st["global"]
        synth.append(["TOTAL", g_["nb_ecoles"], g_["nb_presentes"], g_["pct_presentes"], g_["candidats_g"], g_["candidats_f"],
                      g_["candidats"], g_["admis_g"], g_["admis_f"], g_["admis"], g_["taux_g"], g_["taux_f"], g_["taux"]])
        ent_s = ["CS" if ddemp() else "Zone pédagogique", "Écoles", "Ayant présenté", "% ayant présenté", "Candidats G",
                 "Candidats F", "Candidats T", "Admis G", "Admis F", "Admis T", "Taux G (%)", "Taux F (%)", "Taux T (%)"]
        feuilles = [("Candidats et résultats", ent, rows, {"titre_haut": titre_haut(f"Candidats et résultats au CEP – session {st['session']}", fl)}),
                    ("Synthèse", ent_s, synth, {"titre_haut": titre_haut("Taux de réussite par " + ("CS" if ddemp() else "zone"), fl)})]
        if ddemp():
            synth_z = [[z["cs_nom"], z["zone_nom"], z["nb_ecoles"], z["nb_presentes"], z["pct_presentes"], z["candidats"],
                        z["admis"], z["taux_g"], z["taux_f"], z["taux"]] for z in st["zones"]]
            feuilles.append(("Par zone", ["CS", "Zone pédagogique", "Écoles", "Ayant présenté", "% ayant présenté",
                                          "Candidats", "Admis", "Taux G (%)", "Taux F (%)", "Taux T (%)"], synth_z, {}))
        for nom_f, lst in (("Taux élevé", st["eleves"]), ("Moins de 50 %", st["faibles"])):
            feuilles.append((nom_f, ["N°", "Code", "École"] + (["CS"] if ddemp() else []) + ["Zone", "Candidats", "Admis", "Taux (%)"],
                             [[i, l["code"], l["nom"]] + ([l["cs_nom"]] if ddemp() else []) +
                              [l["zone_nom"], l["candidats"], l["admis"], l["taux"]] for i, l in enumerate(lst, 1)], {}))
        return H.xlsx.reponse_classeur(f"cep_{st['session']}.xlsx", feuilles)

    # ------------------------------------------------------------------ détail / correction d'une école
    @app.route("/juridiction/cep/ecole/<int:eid>", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_cep_ecole(eid):
        garde()
        e = J.ecole(eid)
        if not e:
            abort(404)
        a = request.values.get("annee") or J.annee()
        if not re.match(r"^\d{4}-\d{4}$", a):
            a = J.annee()
        sec, src, maj_sec = _section_brute(eid, a)
        corr = q("SELECT * FROM jur_cep_saisies WHERE ecole_id=? AND annee=?", (eid, a), un=True)
        corr = dict(corr) if corr else None
        saisie = None
        if request.method == "POST":
            ecrire_requis()
            if request.form.get("action") == "annuler":
                if annuler_correction(eid, a):
                    H.journal("jur_cep_correction_annulee", f"{e['nom']} {a}")
                    flash("Correction supprimée : les chiffres transmis par l'école sont rétablis.", "success")
                return redirect(url_for("jur_cep_ecole", eid=eid, annee=a))
            vals, erreurs = {}, []
            noms = {"candidats_g": "Candidats garçons", "candidats_f": "Candidates filles", "admis_g": "Admis garçons",
                    "admis_f": "Admises filles", "cm1_g": "CM1 garçons", "cm1_f": "CM1 filles"}
            for k in NUM:
                v, err = lire_entier(request.form.get(k), vide_ok=k not in ("candidats_g", "candidats_f"))
                if err:
                    erreurs.append(f"{noms[k]} : {err}.")
                vals[k] = v
            if not erreurs:
                erreurs += controler(vals)
            if erreurs:
                for m in erreurs:
                    flash(m, "danger")
                saisie = dict(request.form)
            else:
                enregistrer_correction(eid, a, vals, "saisie", request.form.get("observation", "").strip()[:300],
                                       g.user["identifiant"] if g.get("user") else "")
                H.journal("jur_cep_correction", f"{e['nom']} {a} : {vals}")
                flash("Chiffres du CEP enregistrés.", "success")
                return redirect(url_for("jur_cep_ecole", eid=eid, annee=a))
        effs = J.section(eid, "effectifs", a)
        eff_d = effectif(sec, corr, effs)
        c = JC.cep(eff_d)
        # chiffres transmis par l'école (avant correction)
        if src == "transmission" or not corr:
            transmis = JC.cep(effectif(sec, None, effs)) if sec else None
        else:
            orig = json.loads(corr["origine"] or "null")
            transmis = JC.cep(effectif(orig, None, effs)) if orig else None
        liste = (sec or {}).get("liste") or []
        if request.args.get("export") == "xlsx" and liste:
            ent = ["N°", "Nom", "Prénoms", "Sexe", "Date de naissance", "Lieu de naissance", "N° de table", "Résultat"]
            rows = [[i, p.get("nom", ""), p.get("prenoms", ""), p.get("sexe", ""), p.get("date_naissance", ""),
                     p.get("lieu_naissance", ""), p.get("numero_table", ""),
                     {True: "Admis", False: "Ajourné"}.get(p.get("admis"), "")] for i, p in enumerate(liste, 1)]
            return H.xlsx.reponse_xlsx(f"cep_{e['code']}_{session_de(a)}.xlsx", ent, rows, "Candidats",
                                       [e["nom"], f"Liste des candidats au CEP – session {session_de(a)}"])
        if saisie is None:
            saisie = {k: ("" if eff_d.get(k) is None else JC.entier(eff_d.get(k))) for k in NUM}
            if eff_d.get("admis_g") is None and eff_d.get("admis_f") is None:
                saisie["admis_g"] = saisie["admis_f"] = ""
            saisie["observation"] = (corr or {}).get("observation") or ""
        annees = sorted(set(J.annees()) | {a}, reverse=True)
        return render_template("jur_cep_ecole.html", e=e, a=a, annees=annees, c=c, transmis=transmis, corr=corr,
                               src=src, maj_sec=maj_sec, liste=liste, saisie=saisie, pct=pct, nb=nb,
                               session=str((sec or {}).get("session") or session_de(a)),
                               peut_ecrire=H.peut("jur_cep")), (400 if request.method == "POST" else 200)

    # ------------------------------------------------------------------ import des résultats officiels (Excel)
    def colonnes_import(entetes):
        """Repère les colonnes : code, école, CS, candidats G/F, admis G/F (intitulés souples)."""
        idx = {}
        for i, h in enumerate(entetes):
            t = H.xlsx.normaliser(h)
            mots = t.split()
            if not t:
                continue
            if "code" in mots and "code" not in idx:
                idx["code"] = i
                continue
            cat = None
            if any(m.startswith(p) for m in mots for p in ("admi", "reussi", "recu")):
                cat = "admis"
            elif any(m.startswith(p) for m in mots for p in ("candidat", "present", "inscrit")):
                cat = "candidats"
            if cat:
                sexe = None
                if any(m in ("g", "m", "garcon", "garcons", "masculin", "h") for m in mots):
                    sexe = "g"
                elif any(m in ("f", "fille", "filles", "feminin") for m in mots):
                    sexe = "f"
                if sexe and f"{cat}_{sexe}" not in idx:
                    idx[f"{cat}_{sexe}"] = i
                continue
            if any(m.startswith("circonscription") for m in mots) or mots == ["cs"]:
                idx.setdefault("cs", i)
            elif any(m in ("ecole", "etablissement", "nom") for m in mots) or t.startswith("nom de l ecole"):
                idx.setdefault("ecole", i)
        return idx

    @app.route("/juridiction/cep/import", methods=["GET", "POST"])
    @H.connexion_requise("jur_cep")
    def jur_cep_import():
        garde()
        a = request.values.get("annee") or J.annee()
        if not re.match(r"^\d{4}-\d{4}$", a):
            a = J.annee()
        if request.args.get("modele"):
            st = stats(a)
            ent = ["Code", "École"] + (["Circonscription"] if ddemp() else []) + \
                  ["Zone pédagogique", "Candidats G", "Candidats F", "Admis G", "Admis F"]
            rows = [[l["code"], l["nom"]] + ([l["cs_nom"]] if ddemp() else []) +
                    [l["zone_nom"], l["candidats_g"], l["candidats_f"], l["admis_g"], l["admis_f"]] for l in st["ecoles"]]
            return H.xlsx.reponse_xlsx(f"modele_resultats_cep_{session_de(a)}.xlsx", ent, rows, "Résultats CEP",
                                       [(J.structure() or {}).get("nom", ""), f"Résultats officiels du CEP – session {session_de(a)}",
                                        "Complétez les colonnes Candidats et Admis (G = garçons, F = filles)."])
        rapport = None
        if request.method == "POST":
            fic = request.files.get("fichier")
            if not fic or not fic.filename or not fic.filename.lower().endswith((".xlsx", ".csv")):
                flash("Choisissez un fichier Excel (.xlsx) ou CSV.", "danger")
                return redirect(url_for("jur_cep_import", annee=a))
            try:
                ent, lignes = H.xlsx.lire_tableau(fic, ("code", "ecole", "école", "etablissement", "candidats", "admis"))
            except H.xlsx.ExcelIndisponible as e_:
                flash(str(e_), "danger")
                return redirect(url_for("jur_cep_import", annee=a))
            except Exception:  # noqa: BLE001
                flash("Fichier Excel illisible : enregistrez-le au format .xlsx.", "danger")
                return redirect(url_for("jur_cep_import", annee=a))
            idx = colonnes_import(ent)
            manque = [lib for k, lib in (("candidats_g", "Candidats G"), ("candidats_f", "Candidats F"),
                                         ("admis_g", "Admis G"), ("admis_f", "Admis F")) if k not in idx]
            if "code" not in idx and "ecole" not in idx:
                manque.insert(0, "Code ou École")
            if manque:
                flash("Colonnes introuvables : " + ", ".join(manque) + ". Utilisez le modèle proposé.", "danger")
                return redirect(url_for("jur_cep_import", annee=a))
            toutes = J.ecoles()
            par_code = {(x["code"] or "").upper(): x for x in toutes}
            par_nom = {}
            for x in toutes:
                par_nom.setdefault(J.norm(x["nom"]), []).append(x)
            rapport = {"ok": [], "erreurs": [], "ignorees": 0}
            vu = set()
            for n, l in enumerate(lignes, start=2):
                v = lambda k: H.xlsx.valeur(l, idx.get(k))  # noqa: E731
                code, nom = str(v("code") or "").strip().upper(), str(v("ecole") or "").strip()
                if not code and not nom:
                    rapport["ignorees"] += 1
                    continue
                if J.norm(nom).startswith(("TOTAL", "SOUS TOTAL")):
                    rapport["ignorees"] += 1
                    continue
                e = par_code.get(code) if code else None
                if not e and nom:
                    cands = par_nom.get(J.norm(nom), [])
                    if len(cands) > 1 and "cs" in idx:
                        cands = [x for x in cands if J.norm(x["cs_nom"]) == J.norm(v("cs"))]
                    if len(cands) > 1:
                        rapport["erreurs"].append(f"Ligne {n} : plusieurs écoles « {nom} » ; indiquez le code de l'école.")
                        continue
                    e = cands[0] if cands else None
                if not e:
                    rapport["erreurs"].append(f"Ligne {n} : école « {code or nom} » introuvable dans la juridiction.")
                    continue
                if e["id"] in vu:
                    rapport["erreurs"].append(f"Ligne {n} : « {e['nom']} » figure deux fois dans le fichier (ligne ignorée).")
                    continue
                vals, errs = {"cm1_g": None, "cm1_f": None}, []
                for k in ("candidats_g", "candidats_f", "admis_g", "admis_f"):
                    x, err = lire_entier(v(k), vide_ok=k.startswith("admis"))
                    if err:
                        errs.append(f"{k.replace('_', ' ').replace(' g', ' G').replace(' f', ' F')} : {err}")
                    vals[k] = x
                if not errs:
                    errs = controler(vals)
                if errs:
                    rapport["erreurs"].append(f"Ligne {n} ({e['nom']}) : " + " ; ".join(errs))
                    continue
                enregistrer_correction(e["id"], a, vals, "import", "Résultats officiels importés",
                                       g.user["identifiant"] if g.get("user") else "")
                vu.add(e["id"])
                rapport["ok"].append(e["nom"])
            H.journal("jur_cep_import", f"{a} : {len(rapport['ok'])} école(s)")
            if rapport["ok"]:
                flash(f"{len(rapport['ok'])} école(s) mise(s) à jour pour la session {session_de(a)}.", "success")
            else:
                flash("Aucune école mise à jour.", "warning")
        annees = sorted(set(J.annees()) | {a}, reverse=True)
        return render_template("jur_cep_import.html", a=a, annees=annees, rapport=rapport, session=session_de(a))

    # ------------------------------------------------------------------ prévision de l'année suivante
    @app.route("/juridiction/cep/prevision")
    @H.connexion_requise()
    def jur_cep_prevision():
        garde()
        fl = filtres()
        pv = prevision(fl["annee"], fl["cs_id"], fl["zone_id"], fl["secteur"])
        lignes = rangees(pv["ecoles"], pv["zones"], pv["cs"], pv["global"], fl["vue"], ddemp())
        export = request.args.get("export")
        if export in ("xlsx", "pdf"):
            def cel(r, xlsx=False):
                d = r["d"]
                if r["genre"] == "ecole":
                    ec = "Oui" if d["cm1"] > 0 else "Non"
                else:
                    ec = d["nb_cm1"] if xlsx else f"{d['nb_cm1']}/{d['nb_ecoles']}"
                evo = d["evolution"] if xlsx else pct(d["evolution"])
                return [r.get("n", ""), r["libelle"], ec, d["cm1_g"], d["cm1_f"], d["cm1"],
                        d["candidats_g"], d["candidats_f"], d["candidats"], d["ecart"], evo]
            titre = f"PRÉVISION DES CANDIDATS AU CEP – SESSION {pv['session_suivante']} ({pv['annee_suivante']})"
            if export == "xlsx":
                ent = ["N°", "École / regroupement", "Aura des candidats (CM1)", "Prévus G (CM1)", "Prévus F (CM1)",
                       "Prévus T", f"Candidats {pv['session']} G", f"Candidats {pv['session']} F",
                       f"Candidats {pv['session']} T", "Écart", "Évolution (%)"]
                return H.xlsx.reponse_xlsx(f"prevision_cep_{pv['session_suivante']}.xlsx", ent,
                                           [cel(r, True) for r in lignes], "Prévision CEP", titre_haut(titre.capitalize(), fl))
            cols = [["N°", "École", "Écoles ayant le CM1", f"Candidats prévus {pv['session_suivante']} (élèves de CM1)", None, None,
                     f"Candidats {pv['session']} (année en cours)", None, None, "Écart", "Évolution"],
                    ["^", "^", "^", "G", "F", "T", "G", "F", "T", "^", "^"]]
            corps = [cel(r) for r in lignes[:-1]]
            surl = {i: ("#D9E4F2" if r["genre"] == "cs" else "#EEF3FA") for i, r in enumerate(lignes[:-1]) if r["genre"] != "ecole"}
            g_ = pv["global"]
            apres = [H.pdfs.paragraphe(
                f"<b>{g_['nb_cm1']}</b> école(s) ont des élèves de CM1 en {pv['annee']} et présenteront donc des candidats "
                f"en {pv['session_suivante']} (passage automatique au CM2, sans redoublement) : <b>{nb(g_['cm1'])}</b> candidats "
                f"prévus ({nb(g_['cm1_g'])} G, {nb(g_['cm1_f'])} F), contre {nb(g_['candidats'])} en {pv['session']}.", 8.5),
                signature_pdf(LARGEUR_PAYSAGE)]
            pdf = H.pdfs.document_tableau(titre, cols, corps, sous_titre="Écoles ayant des classes de CM1 cette année",
                                          infos=libelle_filtres(fl), largeurs=[7, 70, 18, 13, 13, 14, 13, 13, 14, 14, 16],
                                          paysage=True, infos_haut=entete_pdf(), total=cel(lignes[-1]) if lignes else None,
                                          taille=7, apres=apres, surlignes=surl)
            return H.pdf_reponse(pdf, f"prevision_cep_{pv['session_suivante']}.pdf")
        return render_template("jur_cep_prevision.html", pv=pv, lignes=lignes, **contexte_filtres(fl))

    # ------------------------------------------------------------------ frais de relevés
    def ecrire_section_frais_cs(a):
        """(CS) Recopie barème + versements dans la section « frais_releves » transmise à la DDEMP."""
        if ddemp():
            return
        c = J.cs_courante()
        if not c:
            return
        b = bareme(a)
        hist = [dict(r) for r in q("SELECT annee, montant_candidat, forfait_ecole, reference, observation, cree_le "
                                   "FROM jur_cep_baremes WHERE annee=? ORDER BY id", (a,))]
        vers = {r["code"]: {"montant": r["montant"], "date_versement": r["date_versement"] or "",
                            "reference": r["reference"] or "", "observation": r["observation"] or ""}
                for r in q("SELECT v.*, e.code FROM jur_cep_versements v JOIN jur_ecoles e ON e.id=v.ecole_id WHERE v.annee=?", (a,))}
        J.ecrire_cs_section(c["id"], "frais_releves", {
            "bareme": {k: b[k] for k in ("montant_candidat", "forfait_ecole", "reference", "observation")} if b else None,
            "historique": hist, "versements": vers}, a, source="saisie")

    @app.route("/juridiction/cep/frais", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_cep_frais():
        garde()
        fl = filtres()
        onglet = "bareme" if request.args.get("onglet") == "bareme" else "tableau"
        a = fl["annee"]
        if request.method == "POST":
            ecrire_requis()
            act = request.form.get("action")
            a = request.form.get("annee") or a
            if not re.match(r"^\d{4}-\d{4}$", a):
                abort(400)
            par = g.user["identifiant"] if g.get("user") else ""
            if act == "bareme":
                mc, e1 = lire_entier(request.form.get("montant_candidat"), vide_ok=False)
                fe, e2 = lire_entier(request.form.get("forfait_ecole"))
                if e1 or e2:
                    flash("Montants invalides : saisissez des nombres entiers positifs (FCFA)." +
                          (f" Montant par candidat : {e1}." if e1 else "") + (f" Forfait : {e2}." if e2 else ""), "danger")
                else:
                    ex("INSERT INTO jur_cep_baremes (annee, montant_candidat, forfait_ecole, reference, observation, cree_le, cree_par) "
                       "VALUES (?,?,?,?,?,datetime('now','localtime'),?)",
                       (a, mc, fe or 0, request.form.get("reference", "").strip()[:200],
                        request.form.get("observation", "").strip()[:300], par))
                    ecrire_section_frais_cs(a)
                    H.journal("jur_cep_bareme", f"{a} : {mc} FCFA/candidat, forfait {fe or 0}")
                    flash(f"Barème {a} enregistré : {H.fcfa(mc)} par candidat"
                          + (f" + {H.fcfa(fe)} par école." if fe else "."), "success")
                return redirect(url_for("jur_cep_frais", annee=a, onglet="bareme"))
            if act == "versements":
                ids = {e["id"] for e in J.ecoles()}
                nbm, erreurs = 0, []
                for cle in request.form:
                    m = re.match(r"^verse_(\d+)$", cle)
                    if not m or int(m.group(1)) not in ids:
                        continue
                    eid = int(m.group(1))
                    brut = request.form.get(cle, "")
                    montant, err = lire_entier(brut)
                    dt = request.form.get(f"date_{eid}", "").strip()
                    if dt and not re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
                        err = err or f"date « {dt} » invalide"
                    if err:
                        e = J.ecole(eid)
                        erreurs.append(f"{e['nom'] if e else eid} : {err}.")
                        continue
                    ref = request.form.get(f"ref_{eid}", "").strip()[:100]
                    anc = q("SELECT montant, date_versement, reference FROM jur_cep_versements WHERE ecole_id=? AND annee=?",
                            (eid, a), un=True)
                    if montant is None and not anc:
                        continue
                    if anc and anc["montant"] == (montant or 0) and (anc["date_versement"] or "") == dt \
                            and (anc["reference"] or "") == ref:
                        continue
                    if montant is None and anc:
                        ex("DELETE FROM jur_cep_versements WHERE ecole_id=? AND annee=?", (eid, a))
                    else:
                        ex("INSERT INTO jur_cep_versements (ecole_id, annee, montant, date_versement, reference, maj, maj_par) "
                           "VALUES (?,?,?,?,?,datetime('now','localtime'),?) ON CONFLICT(ecole_id, annee) DO UPDATE SET "
                           "montant=excluded.montant, date_versement=excluded.date_versement, reference=excluded.reference, "
                           "maj=excluded.maj, maj_par=excluded.maj_par", (eid, a, montant, dt, ref, par))
                    nbm += 1
                for m_ in erreurs[:15]:
                    flash(m_, "danger")
                if nbm:
                    ecrire_section_frais_cs(a)
                    H.journal("jur_cep_versements", f"{a} : {nbm} école(s)")
                flash(f"{nbm} versement(s) enregistré(s).", "success" if nbm else "info")
                return redirect(url_for("jur_cep_frais", **args_url(dict(fl, annee=a))))
            abort(400)
        fr = frais(a, fl["cs_id"], fl["zone_id"], fl["secteur"])
        lignes = rangees(fr["ecoles"], fr["zones"], fr["cs"], fr["global"], fl["vue"], ddemp())
        export = request.args.get("export")
        if export in ("xlsx", "pdf"):
            return export_frais(fr, lignes, fl, export)
        historique = q("SELECT * FROM jur_cep_baremes ORDER BY annee DESC, id DESC")
        return render_template("jur_cep_frais.html", fr=fr, lignes=lignes, onglet=onglet, historique=historique,
                               statut=statut_frais, fcfa=H.fcfa, peut_ecrire=H.peut("jur_cep"), **contexte_filtres(fl))

    def export_frais(fr, lignes, fl, export):
        b = fr["bareme"]
        bar_txt = (f"{H.fcfa(b['montant_candidat'])} par candidat" + (f" + {H.fcfa(b['forfait_ecole'])} par école" if b["forfait_ecole"] else "")
                   if b else "non défini")
        titre = f"FRAIS DE RELEVÉS DU CEP – SESSION {fr['session']}"

        def cel(r, xlsx=False):
            d = r["d"]
            e = r["genre"] == "ecole"
            m = (lambda v: v) if xlsx else H.fcfa
            return [r.get("n", ""), r["libelle"], d["candidats"], (m(d["unitaire"]) if e else ""),
                    (m(d["forfait"]) if e else ""), m(d["du"]), m(d["verse"]), m(d["reste"]),
                    statut_frais(d) if e else f"{d['nb_soldees']}/{d['nb_ecoles']} soldée(s)"] + \
                ([d["date_versement"], d["reference"]] if xlsx and e else ([] if not xlsx else ["", ""]))
        if export == "xlsx":
            ent = ["N°", "École / regroupement", "Candidats", "Montant par candidat", "Forfait école", "Montant dû",
                   "Montant versé", "Reste à payer", "Situation", "Date du versement", "Référence"]
            th = titre_haut(titre.capitalize(), fl) + [f"Barème : {bar_txt}"]
            hist = [[r["annee"], r["montant_candidat"], r["forfait_ecole"], r["reference"] or "", r["observation"] or "",
                     r["cree_le"] or "", r["cree_par"] or ""]
                    for r in q("SELECT * FROM jur_cep_baremes ORDER BY annee DESC, id DESC")]
            return H.xlsx.reponse_classeur(f"frais_releves_cep_{fr['session']}.xlsx", [
                ("Frais de relevés", ent, [cel(r, True) for r in lignes], {"titre_haut": th}),
                ("Barèmes", ["Année", "Montant par candidat", "Forfait par école", "Référence", "Observation",
                             "Enregistré le", "Par"], hist, {})])
        cols = ["N°", "École", "Candidats", "Montant / candidat", "Forfait", "Montant dû", "Versé", "Reste à payer", "Situation"]
        surl = {i: ("#D9E4F2" if r["genre"] == "cs" else "#EEF3FA") for i, r in enumerate(lignes[:-1]) if r["genre"] != "ecole"}
        g_ = fr["global"]
        apres = [H.pdfs.paragraphe(f"<b>Barème {fr['annee']} :</b> {bar_txt}. <b>Total dû :</b> {H.fcfa(g_['du'])} · "
                                   f"<b>versé :</b> {H.fcfa(g_['verse'])} · <b>reste à payer :</b> {H.fcfa(g_['reste'])} "
                                   f"(recouvrement {pct(g_['taux_recouvrement'])}).", 8.5),
                 signature_pdf(LARGEUR_PAYSAGE)]
        pdf = H.pdfs.document_tableau(titre, cols, [cel(r) for r in lignes[:-1]], sous_titre="Montant dû = candidats × montant par candidat (+ forfait par école)",
                                      infos=libelle_filtres(fl) + [("Barème", bar_txt)],
                                      largeurs=[7, 75, 14, 20, 16, 22, 22, 22, 22], paysage=True, infos_haut=entete_pdf(),
                                      total=cel(lignes[-1]) if lignes else None, taille=7.5, apres=apres, surlignes=surl)
        return H.pdf_reponse(pdf, f"frais_releves_cep_{fr['session']}.pdf")
