# -*- coding: utf-8 -*-
"""Calculs communs des applications CS / DDEMP (fonctions pures sur les sections des paquets).

Utilisés par a_tableau, a_cep, a_personnel… pour que tous les écrans donnent les mêmes chiffres.
"""
import math

ROLES_ENSEIGNANTS = ("directeur", "adjoint", "enseignant")


def entier(v):
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def taux(n, d, decimales=1):
    """Pourcentage n/d (None si d = 0)."""
    return round(100.0 * n / d, decimales) if d else None


def ecart_type(valeurs):
    """Écart-type (population) d'une liste de nombres ; 0 si moins de 2 valeurs."""
    v = [float(x) for x in valeurs if x is not None]
    if len(v) < 2:
        return 0.0
    m = sum(v) / len(v)
    return round(math.sqrt(sum((x - m) ** 2 for x in v) / len(v)), 2)


def moyenne(valeurs):
    v = [float(x) for x in valeurs if x is not None]
    return round(sum(v) / len(v), 2) if v else None


def effectifs(sec):
    """Section « effectifs » → {"g", "f", "t", "classes": n, "redoublants": n, "par_niveau": {niveau: [g, f]},
    "tailles": [effectif de chaque classe]}."""
    sec = sec or {}
    out = {"g": 0, "f": 0, "t": 0, "classes": 0, "redoublants": 0, "par_niveau": {}, "tailles": []}
    for c in sec.get("classes") or []:
        g, f = entier(c.get("garcons")), entier(c.get("filles"))
        out["g"] += g
        out["f"] += f
        out["classes"] += 1
        out["redoublants"] += entier(c.get("redoublants_g")) + entier(c.get("redoublants_f"))
        n = out["par_niveau"].setdefault(c.get("niveau") or "?", [0, 0])
        n[0] += g
        n[1] += f
        out["tailles"].append(g + f)
    out["t"] = out["g"] + out["f"]
    return out


def enseignants(pers):
    """Section « personnel » → enseignants en poste (directeurs, adjoints, enseignants actifs) :
    {"t", "h", "f", "liste": [...], "par_categorie": {cat: n}}."""
    out = {"t": 0, "h": 0, "f": 0, "liste": [], "par_categorie": {}}
    for p in pers or []:
        if p.get("role") not in ROLES_ENSEIGNANTS or p.get("actif") is False:
            continue
        out["liste"].append(p)
        out["t"] += 1
        out["f" if p.get("sexe") == "F" else "h"] += 1
        cat = p.get("categorie") or "AUTRE"
        out["par_categorie"][cat] = out["par_categorie"].get(cat, 0) + 1
    return out


def besoin_enseignants(sec_effectifs, pers):
    """Besoin = nombre de groupes pédagogiques (classes) ; disponible = enseignants tenant une classe
    (directeur compris s'il a une classe). Renvoie {"classes", "enseignants", "manque", "surplus"}."""
    e = effectifs(sec_effectifs)
    ens = enseignants(pers)
    tenant = sum(1 for p in ens["liste"] if (p.get("classe") or p.get("role") == "enseignant"))
    d = e["classes"] - tenant
    return {"classes": e["classes"], "enseignants": tenant, "manque": max(0, d), "surplus": max(0, -d)}


def cep(sec):
    """Section « cep » → {"candidats_g", "candidats_f", "candidats", "admis_g", "admis_f", "admis" (None si
    résultats inconnus), "taux", "taux_g", "taux_f", "cm1", "cm2"}."""
    sec = sec or {}
    cg, cf = entier(sec.get("candidats_g")), entier(sec.get("candidats_f"))
    connu = sec.get("admis_g") is not None or sec.get("admis_f") is not None
    ag, af = (entier(sec.get("admis_g")), entier(sec.get("admis_f"))) if connu else (None, None)
    adm = (ag + af) if connu else None
    return {"candidats_g": cg, "candidats_f": cf, "candidats": cg + cf, "admis_g": ag, "admis_f": af, "admis": adm,
            "taux": taux(adm, cg + cf) if connu else None, "taux_g": taux(ag, cg) if connu else None,
            "taux_f": taux(af, cf) if connu else None,
            "cm1": entier(sec.get("cm1_g")) + entier(sec.get("cm1_f")), "cm1_g": entier(sec.get("cm1_g")),
            "cm1_f": entier(sec.get("cm1_f")), "cm2": entier(sec.get("cm2_g")) + entier(sec.get("cm2_f"))}


def cumul(dicts, cles):
    """Somme clé par clé (None ignorés ; None si toutes les valeurs sont None)."""
    out = {}
    for k in cles:
        vals = [d.get(k) for d in dicts if d.get(k) is not None]
        out[k] = sum(vals) if vals else None
    return out
