# -*- coding: utf-8 -*-
"""Référentiel des unités administratives locales du Bénin : 12 départements, 77 communes, 546 arrondissements,
5 290 villages et quartiers de ville (static/referentiel_villages.json). Utilisé par les listes en cascade des
formulaires (static/scolaris.js, champs data-geo) et par les modules qui ont besoin des noms officiels."""
import json
import os
import unicodedata

_DATA = None


def _chemin():
    try:
        import pdfs
        p = pdfs.fichier_static("referentiel_villages.json")
        if p:
            return p
    except Exception:  # noqa: BLE001
        pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "referentiel_villages.json")


def _donnees():
    global _DATA
    if _DATA is None:
        with open(_chemin(), encoding="utf-8") as f:
            _DATA = json.load(f)["d"]
    return _DATA


def cle(s):
    s = "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn")
    return "".join(ch for ch in s.upper() if ch.isalnum())


def departements():
    return [d for d, _ in _donnees()]


def communes(departement=None):
    k = cle(departement) if departement else None
    return [c for d, cs in _donnees() if not k or cle(d) == k for c, _ in cs]


def departement_de(commune):
    k = cle(commune)
    for d, cs in _donnees():
        if any(cle(c) == k for c, _ in cs):
            return d
    return None


def arrondissements(commune):
    k = cle(commune)
    return [a for _, cs in _donnees() for c, ars in cs if cle(c) == k for a, _ in ars]


def villages(commune, arrondissement=None):
    kc, ka = cle(commune), cle(arrondissement) if arrondissement else None
    return [v for _, cs in _donnees() for c, ars in cs if cle(c) == kc
            for a, vs in ars if not ka or cle(a) == ka for v in vs]


def nom_officiel_commune(saisie):
    k = cle(saisie)
    return next((c for c in communes() if cle(c) == k), saisie)


def totaux():
    d = _donnees()
    return {"departements": len(d), "communes": sum(len(cs) for _, cs in d),
            "arrondissements": sum(len(ars) for _, cs in d for _, ars in cs),
            "villages": sum(len(vs) for _, cs in d for _, ars in cs for _, vs in ars)}
