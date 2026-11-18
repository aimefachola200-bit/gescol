# -*- coding: utf-8 -*-
"""Exporte les contenus pédagogiques du secondaire de GESCOL / Scolaris vers les applications web ÉduGestion Pro et ÉduGestion Pro Master
(dossier data/secondaire/ : index.json, fiches.json, epreuves.json, banque.json, langues.json, reperes.json).

    python3 outils/exporter_secondaire.py <dossier_de_sortie>
"""
import hashlib
import json
import os
import sys
from datetime import date

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import agri_sec as AG  # noqa: E402
import cahier_cp_progression as CP  # noqa: E402
import cahiers_langues as CL  # noqa: E402
import epreuves_apc as EA  # noqa: E402
import fiches_sec as FS  # noqa: E402
import lectures as LE  # noqa: E402
import m_textes as MT  # noqa: E402
import poesies as PO  # noqa: E402
import reperes as RE  # noqa: E402

NIVEAUX = [("6e", "6e", "1er cycle"), ("5e", "5e", "1er cycle"), ("4e", "4e", "1er cycle"), ("3e", "3e", "1er cycle"),
           ("2nde", "2nde", "2nd cycle"), ("1ère", "1ère", "2nd cycle"), ("Tle", "Terminale", "2nd cycle")]
MATIERES = ["Français", "Mathématiques", "Anglais", "Allemand", "Espagnol", "Physique-Chimie-Technologie", "SVT", "Histoire-Géographie", "Philosophie"] + [m[1] for m in AG.MATIERES_AGRI]


def _ecrire(dossier, nom, objet):
    chemin = os.path.join(dossier, nom)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(objet, f, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(chemin), hashlib.sha1(open(chemin, "rb").read()).hexdigest()[:12]


def main(sortie):
    AG.integrer()   # lycée agricole : épreuves, interrogations, devoirs et fiches ajoutés aux bibliothèques
    os.makedirs(sortie, exist_ok=True)
    fiches = [dict(f, id=f"sec-f{i + 1:03d}") for i, f in enumerate(FS.FICHES)]
    epreuves = []
    for i, e in enumerate(EA.EPREUVES):
        total = sum(it["points"] for it in e["items"])
        epreuves.append(dict(e, id=f"sec-e{i + 1:03d}", total=total))
    banque = json.load(open(os.path.join(RACINE, "static", "banque_secondaire.json"), encoding="utf-8"))
    banque_l = [dict(b, id=f"sec-b{i + 1:03d}") for i, b in enumerate(banque["epreuves"])]
    langues = {l: {n: {"situations": [{"titre": t, "consigne": c, "exercices": [{"q": q, "r": r} for q, r in items]} for t, c, items in d[0]],
                       "evaluation": [{"q": q, "r": r} for q, r in d[1]]} for n, d in niv.items()} for l, niv in CL.DATA.items()}
    reperes = {
        "auteurs": [{"nom": a[0], "idee": a[1], "pratique": a[2]} for a in RE.AUTEURS],
        "art": [{"titre": a[0], "texte": a[1]} for a in RE.ART],
        "lecture_cp": [{"titre": a[0], "texte": a[1]} for a in RE.LECTURE_CP],
        "lectures": LE.LECTURES,
        "poemes": [{"titre": p[0], "niveau": p[1], "vers": p[2], "theme": p[3]} for p in PO.POEMES],
        "poemes_conseils": PO.CONSEILS, "poemes_grille": PO.GRILLE,
        "acteurs": [{"titre": a[0], "role": a[1]} for a in MT.ACTEURS_SEC],
        "textes_officiels": [{k: t.get(k) for k in ("tutelle", "cycle", "titre", "points")} for t in MT.TEXTES],
        "cahier_cp": [{"n": n, "contenu": t, "page": p} for n, t, p in CP.LECONS],
    }
    fichiers = {}
    for nom, obj in (("fiches.json", fiches), ("epreuves.json", epreuves), ("banque.json", banque_l), ("langues.json", langues), ("reperes.json", reperes)):
        o, h = _ecrire(sortie, nom, obj)
        fichiers[nom] = {"octets": o, "empreinte": h}
    index = {
        "version": hashlib.sha1("".join(v["empreinte"] for v in fichiers.values()).encode()).hexdigest()[:12],
        "genere": date.today().isoformat(), "source": "GESCOL / Scolaris (contenus originaux et banque du secondaire)",
        "niveaux": [{"code": c, "libelle": l, "cycle": cy} for c, l, cy in NIVEAUX], "matieres": MATIERES, "fichiers": fichiers,
        "nb": {"fiches": len(fiches), "epreuves": len(epreuves), "banque": len(banque_l),
               "langues": sum(len(v) for v in langues.values()), "textes": len(reperes["textes_officiels"])},
        "mention": "Fiches et épreuves conçues selon l'APC, à valider par le conseiller pédagogique ou le chef de département.",
    }
    _ecrire(sortie, "index.json", index)
    return index


if __name__ == "__main__":
    idx = main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(RACINE, "data_secondaire"))
    print(json.dumps(idx["nb"]), idx["version"])
