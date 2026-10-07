# -*- coding: utf-8 -*-
"""Moteur commun des évaluations (formatives, sommatives d'étape, diagnostiques, certificatives).

Modèle de données
-----------------
* table ``evaluations`` : une ligne par évaluation d'une classe (type, numéro, libellé, matières cochées, seuil).
* les notes sont dans la table ``notes`` avec ``periode = evaluations.libelle`` (même mécanisme que les trimestres).

Règles
------
* Primaire : un élève a la MAÎTRISE s'il obtient au moins 10/20 dans ``seuil`` matières ; ``seuil`` est fixé
  par l'évaluation (ex. 6) ou, à défaut, 2/3 des matières évaluées (arrondi supérieur). C'est la SEULE condition
  de réussite ; la moyenne simple ne sert qu'au classement (ordre de mérite).
* Secondaire : moyenne pondérée par les coefficients (sans coefficient en 6ème/5ème) ; réussite si moyenne >= 10.
* Maternelle : appréciations A / ECA / NA (pas de moyenne).
* Un élève sans aucune note dans l'évaluation est compté « absent » (n'a pas composé).
* Bilan annuel : M = (M_O + E_D) / 2, M_O = moyenne des évaluations précédentes, E_D = dernière évaluation ;
  l'élève est admis s'il a validé (maîtrise) au moins les 2/3 des évaluations qu'il a composées.
"""
import json
import math
from statistics import pstdev

import config
from calcul import APPRECIATIONS, NIVEAUX_SANS_COEF, classer, cycle_du_niveau, mention, seuil_deux_tiers
from db import q

TYPES = {
    "diagnostique": "Évaluation diagnostique",
    "formative": "Évaluation formative",
    "sommative": "Évaluation sommative d'étape",
    "certificative": "Évaluation certificative",
}
ABREV = {"diagnostique": "Diagnostique", "formative": "Formative", "sommative": "Sommative", "certificative": "Certificative"}
TRANCHES = [("≥ 15", 15, 99), ("12 à 14,99", 12, 15), ("10 à 11,99", 10, 12), ("< 10", -1, 10), ("dont < 8", -1, 8)]


def libelle(type_, numero):
    """Clé des notes : « Formative 1 », « Sommative 2 »… (distincte de « Trimestre 1 »)."""
    return f"{ABREV.get(type_, type_.capitalize())} {int(numero)}"


def titre(ev):
    return f"{TYPES.get(ev['type'], ev['type'])} N° {ev['numero']}"


def _dict(ev):
    d = dict(ev)
    try:
        d["matieres_ids"] = [int(x) for x in json.loads(ev["matieres"] or "[]")]
    except (ValueError, TypeError):
        d["matieres_ids"] = []
    d["titre"] = titre(d)
    return d


def evaluation(ev_id):
    ev = q("SELECT * FROM evaluations WHERE id=?", (ev_id,), un=True)
    return _dict(ev) if ev else None


def evaluations_classe(classe_id, annee=None):
    rows = q("SELECT * FROM evaluations WHERE classe_id=? AND annee=? ORDER BY COALESCE(date,''), type, numero, id",
             (classe_id, annee or config.ANNEE_ACTIVE))
    return [_dict(r) for r in rows]


def matieres_cycle(cycle):
    return q("SELECT * FROM matieres WHERE cycle=? AND actif=1 ORDER BY ordre, nom", (cycle,))


def matieres_de(ev, classe):
    """Matières cochées de l'évaluation (dans l'ordre officiel) ; toutes celles du cycle si aucune n'est cochée."""
    toutes = matieres_cycle(cycle_du_niveau(classe["niveau"]))
    ids = ev["matieres_ids"] if ev else []
    return [m for m in toutes if m["id"] in ids] if ids else list(toutes)


def eleves_classe(classe_id):
    return q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (classe_id,))


def seuil_de(ev, nb_matieres):
    if ev and ev.get("seuil"):
        return max(1, min(int(ev["seuil"]), nb_matieres or int(ev["seuil"])))
    return seuil_deux_tiers(nb_matieres) if nb_matieres else 0


def resultats(ev, classe, eleves=None):
    """Résultats d'une évaluation. Retourne (matieres, lignes) ; lignes = liste de dict par élève inscrit :
    eleve, notes {matiere_id: valeur|None}, dispenses {matiere_id}, appreciations {matiere_id: A/ECA/NA},
    compose, nb_notes, reussies, seuil, maitrise (bool|None), moyenne, decision, mention, rang, ex_aequo."""
    cycle = cycle_du_niveau(classe["niveau"])
    matieres = matieres_de(ev, classe)
    eleves = list(eleves if eleves is not None else eleves_classe(classe["id"]))
    notes = {}
    if eleves:
        ids = [e["id"] for e in eleves]
        marque = ",".join("?" * len(ids))
        for n in q(f"SELECT * FROM notes WHERE periode=? AND annee=? AND eleve_id IN ({marque})",
                   [ev["libelle"], ev["annee"]] + ids):
            notes[(n["eleve_id"], n["matiere_id"])] = n
    coef_actifs = cycle == "secondaire" and classe["niveau"] not in NIVEAUX_SANS_COEF
    lignes = []
    for e in eleves:
        l = {"eleve": e, "notes": {}, "dispenses": set(), "appreciations": {}}
        pts = coefs = 0.0
        vals = []
        for m in matieres:
            n = notes.get((e["id"], m["id"]))
            if not n:
                l["notes"][m["id"]] = None
                continue
            if n["dispense"]:
                l["dispenses"].add(m["id"])
                l["notes"][m["id"]] = None
                continue
            if cycle == "maternelle":
                if n["appreciation"] in APPRECIATIONS:
                    l["appreciations"][m["id"]] = n["appreciation"]
                l["notes"][m["id"]] = None
                continue
            l["notes"][m["id"]] = n["valeur"]
            if n["valeur"] is not None:
                vals.append(n["valeur"])
                c = m["coefficient"] if coef_actifs else 1.0
                pts += n["valeur"] * c
                coefs += c
        nb_evaluees = len(matieres) - len(l["dispenses"])
        l["nb_notes"] = len(vals) if cycle != "maternelle" else len(l["appreciations"])
        l["compose"] = l["nb_notes"] > 0
        l["reussies"] = sum(1 for v in vals if v >= 10)
        l["seuil"] = seuil_de(ev, nb_evaluees)
        l["moyenne"] = None
        l["maitrise"] = None
        if cycle == "maternelle":
            a = list(l["appreciations"].values())
            if a:
                score = (2 * a.count("A") + a.count("ECA")) / (2 * len(a))
                l["decision"] = ("Progrès très satisfaisants" if score >= .75 else
                                 "Progrès satisfaisants" if score >= .5 else "Progrès à renforcer")
                l["maitrise"] = score >= .5
            else:
                l["decision"] = "ABSENT"
        elif not vals:
            l["decision"] = "ABSENT"
        else:
            l["moyenne"] = round(pts / coefs if cycle == "secondaire" else sum(vals) / len(vals), 2)
            if cycle == "primaire":
                l["maitrise"] = l["reussies"] >= l["seuil"]
                l["decision"] = "MAÎTRISE" if l["maitrise"] else "NON MAÎTRISE"
            else:
                l["maitrise"] = l["moyenne"] >= 10
                l["decision"] = "ADMIS" if l["maitrise"] else "NON ADMIS"
        l["mention"] = mention(l["moyenne"]) if l["moyenne"] is not None else "—"
        lignes.append(l)
    rangs = classer({l["eleve"]["id"]: l["moyenne"] for l in lignes})
    effectif = sum(1 for l in lignes if l["compose"])
    for l in lignes:
        l["rang"], l["ex_aequo"] = rangs[l["eleve"]["id"]]
        l["effectif"] = effectif
        l["rang_texte"] = ("—" if l["rang"] is None else
                           f"{l['rang']}{'er' if l['rang'] == 1 else 'e'}{' ex æquo' if l['ex_aequo'] else ''}")
    return matieres, lignes


def ordre_de_merite(lignes):
    """Élèves ayant composé, du 1er au dernier (maîtrise d'abord n'intervient pas : le rang suit la moyenne)."""
    return sorted([l for l in lignes if l["moyenne"] is not None], key=lambda l: (l["rang"], l["eleve"]["nom"]))


# ------------------------------------------------------------------ statistiques
def _pct(a, b):
    return round(100 * a / b, 2) if b else 0.0


def _moy(v):
    return round(sum(v) / len(v), 2) if v else None


def _ecart(v):
    return round(pstdev(v), 2) if len(v) > 1 else (0.0 if v else None)


def statistiques(matieres, lignes):
    """Statistiques complètes d'une évaluation (par sexe : G = garçons, F = filles, T = total)."""
    S = {"G": "M", "F": "F"}

    def par_sexe(filtre):
        d = {k: sum(1 for l in lignes if l["eleve"]["sexe"] == s and filtre(l)) for k, s in S.items()}
        d["T"] = d["G"] + d["F"]
        return d

    inscrits = par_sexe(lambda l: True)
    composes = par_sexe(lambda l: l["compose"])
    absents = {k: inscrits[k] - composes[k] for k in inscrits}
    reussis = par_sexe(lambda l: l["compose"] and l["maitrise"])
    echecs = {k: composes[k] - reussis[k] for k in composes}
    taux_reussite = {k: _pct(reussis[k], composes[k]) for k in composes}
    taux_echec = {k: _pct(echecs[k], composes[k]) for k in composes}
    moys = {k: [l["moyenne"] for l in lignes if l["moyenne"] is not None and (k == "T" or l["eleve"]["sexe"] == S[k])]
            for k in ("G", "F", "T")}
    moyenne = {k: _moy(v) for k, v in moys.items()}
    ecart = {k: _ecart(v) for k, v in moys.items()}
    tranches = []
    for lib, bas, haut in TRANCHES:
        d = {k: sum(1 for m in moys[k] if bas <= m < haut) for k in moys}
        d.update(libelle=lib, pct={k: _pct(d[k], len(moys[k])) for k in moys})
        tranches.append(d)
    par_matiere = []
    for m in matieres:
        d = {"matiere": m}
        for k in ("G", "F", "T"):
            notes_k = [l["notes"].get(m["id"]) for l in lignes if (k == "T" or l["eleve"]["sexe"] == S[k])]
            notes_k = [n for n in notes_k if n is not None]
            d[k] = {"composes": len(notes_k), "reussis": sum(1 for n in notes_k if n >= 10),
                    "moyenne": _moy(notes_k)}
            d[k]["echecs"] = d[k]["composes"] - d[k]["reussis"]
            d[k]["taux"] = _pct(d[k]["reussis"], d[k]["composes"])
        par_matiere.append(d)

    def extreme(k, fort):
        cand = [d for d in par_matiere if d[k]["moyenne"] is not None]
        if not cand:
            return None
        d = (max if fort else min)(cand, key=lambda x: x[k]["moyenne"])
        return {"matiere": d["matiere"]["nom"], "moyenne": d[k]["moyenne"], "taux": d[k]["taux"]}

    forte = {k: extreme(k, True) for k in ("T", "G", "F")}
    faible = {k: extreme(k, False) for k in ("T", "G", "F")}
    return {"inscrits": inscrits, "composes": composes, "absents": absents, "reussis": reussis, "echecs": echecs,
            "taux_reussite": taux_reussite, "taux_echec": taux_echec, "moyenne": moyenne, "ecart_type": ecart,
            "tranches": tranches, "par_matiere": par_matiere, "forte": forte, "faible": faible,
            "plus_forte_moyenne": max(moys["T"]) if moys["T"] else None,
            "plus_faible_moyenne": min(moys["T"]) if moys["T"] else None,
            "participation": {k: _pct(composes[k], inscrits[k]) for k in inscrits}}


def a_renforcer(stats, seuil_pct=50):
    """Matières dont le taux de réussite (total) est inférieur à seuil_pct %."""
    return [d["matiere"]["nom"] for d in stats["par_matiere"] if d["T"]["composes"] and d["T"]["taux"] < seuil_pct]


# ------------------------------------------------------------------ bilan annuel
def bilan_annuel(classe, evaluations, eleves=None):
    """evaluations : liste ordonnée (la dernière = E_D). Retourne liste de dict par élève :
    eleve, moyennes [par évaluation], M_O, E_D, M, validees, composees, requis, admis, decision, rang."""
    eleves = list(eleves if eleves is not None else eleves_classe(classe["id"]))
    par_ev = []
    for ev in evaluations:
        _, lignes = resultats(ev, classe, eleves)
        par_ev.append({l["eleve"]["id"]: l for l in lignes})
    out = []
    for e in eleves:
        ls = [p.get(e["id"]) for p in par_ev]
        moys = [l["moyenne"] if l else None for l in ls]
        composees = sum(1 for l in ls if l and l["compose"])
        validees = sum(1 for l in ls if l and l["compose"] and l["maitrise"])
        anterieures = [m for m in moys[:-1] if m is not None]
        m_o = _moy(anterieures)
        e_d = moys[-1] if moys else None
        if m_o is not None and e_d is not None:
            m = round((m_o + e_d) / 2, 2)
        else:
            m = e_d if e_d is not None else m_o
        requis = math.ceil(2 * composees / 3) if composees else 0
        admis = composees > 0 and validees >= requis
        out.append({"eleve": e, "moyennes": moys, "lignes": ls, "M_O": m_o, "E_D": e_d, "M": m,
                    "composees": composees, "validees": validees, "requis": requis, "admis": admis,
                    "decision": ("ADMIS(E)" if admis else ("NON ADMIS(E)" if composees else "ABSENT(E)"))})
    rangs = classer({o["eleve"]["id"]: o["M"] for o in out})
    for o in out:
        o["rang"], o["ex_aequo"] = rangs[o["eleve"]["id"]]
    return out
