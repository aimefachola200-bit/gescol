# -*- coding: utf-8 -*-
"""v2.5.0 : liste des écoles maternelles et primaires du Bénin (9 217 écoles, source : liste des subventions 2023-2024).

Chaque école est rangée dans son département, sa commune et son arrondissement ; sa circonscription scolaire (CS) est déduite
des arrondissements de chaque CS (référentiel officiel). Quand une commune compte plusieurs CS et que l'arrondissement n'est pas
attribué à l'une d'elles, la CS est « à confirmer » : l'école est proposée à toutes les CS de la commune.
Fichier : static/referentiel_ecoles.json  {"cs": [noms], "co": {"Département|Commune": [index CS]}, "d": [[dép, [[commune, [[arr, [[nom, M|P, année, index CS ou -1]]]]]]]]}"""
import hashlib
import json
import os

import referentiel_villages as RV

_DATA = None


def _chemin():
    try:
        import pdfs
        p = pdfs.fichier_static("referentiel_ecoles.json")
        if p:
            return p
    except Exception:  # noqa: BLE001
        pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "referentiel_ecoles.json")


def donnees():
    global _DATA
    if _DATA is None:
        with open(_chemin(), encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA


def ecoles_de_cs(cs_nom, departement=None, a_confirmer=False):
    """Écoles de la CS (par son nom). Avec a_confirmer=True : on ajoute celles dont la CS est incertaine dans sa commune.
    Retourne des dict : nom, type (EP/EM), annee, departement, commune, arrondissement, sure (bool)."""
    D = donnees()
    cle_cs = RV.cle(cs_nom)
    idx = [i for i, n in enumerate(D["cs"]) if RV.cle(n) == cle_cs]
    if not idx:
        return []
    i0 = idx[0]
    out = []
    for dep, communes in D["d"]:
        if departement and RV.cle(dep) != RV.cle(departement):
            continue
        for com, arrs in communes:
            candidates = D["co"].get(dep + "|" + com, [])
            for arr, lst in arrs:
                for nom, t, an, ics in lst:
                    if ics == i0 or (a_confirmer and ics == -1 and i0 in candidates):
                        out.append({"nom": nom, "type": "EM" if t == "M" else "EP", "annee": an, "departement": dep,
                                    "commune": com, "arrondissement": arr, "sure": ics == i0})
    return out


def code(e, cs_nom=""):
    h = hashlib.sha1("|".join((e["departement"], e["commune"], e["arrondissement"], e["nom"], e["type"])).encode("utf-8")).hexdigest()[:7].upper()
    return "REF-" + h


def compter(cs_nom, departement=None):
    s = ecoles_de_cs(cs_nom, departement, a_confirmer=True)
    return {"sures": sum(1 for e in s if e["sure"]), "a_confirmer": sum(1 for e in s if not e["sure"])}
