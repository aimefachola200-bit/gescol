# -*- coding: utf-8 -*-
"""v2.8 : choix du périmètre de l'enseignant dans l'application personnelle (GESCOL / Scolaris Enseignant).

Chaque enseignant choisit son mode :
- « titulaire »  : titulaire d'une classe de la maternelle ou du primaire (toutes les matières) ;
- « professeur » : professeur d'une ou plusieurs matières dans plusieurs classes (collège, lycée, enseignement technique et agricole) :
  cours par classe et par matière, bibliothèque de fiches, devoirs, TP, exposés, épreuves APC ;
- « les_deux »   : les deux à la fois.
Dans les éditions du secondaire, le périmètre professeur est toujours actif (affectations classe × matière faites par l'administration).
"""
from flask import g

import config
from db import ex, q

MODES = (("titulaire", "Titulaire de classe (maternelle, primaire) : toutes les matières de ma classe"),
         ("professeur", "Professeur (collège, lycée, technique, agricole) : mes matières dans plusieurs classes"),
         ("les_deux", "Les deux : titulaire d'une classe et professeur de matières"))


def mode(uid=None):
    uid = uid or (g.user["id"] if getattr(g, "user", None) else None)
    if not uid:
        return "titulaire"
    try:
        r = q("SELECT mode FROM ens_mode WHERE user_id=?", (uid,), un=True)
    except Exception:  # noqa: BLE001 — table pas encore créée
        return "titulaire"
    if r and r["mode"] in dict(MODES):
        return r["mode"]
    # v2.7.1 : pas encore de choix enregistré -> déduit des classes de l'enseignant (6e à Tle = professeur)
    try:
        from calcul import NIVEAUX_SECONDAIRE
        niv = [x["niveau"] for x in q("SELECT DISTINCT c.niveau FROM classes c JOIN affectations a ON a.classe_id=c.id "
                                      "WHERE a.user_id=?", (uid,))]
        sec = [n for n in niv if n in NIVEAUX_SECONDAIRE]
        if sec:
            return "professeur" if len(sec) == len(niv) else "les_deux"
    except Exception:  # noqa: BLE001
        pass
    return "titulaire"


def bibliotheque_ouverte():
    """La bibliothèque pédagogique du secondaire (épreuves, fiches, exposés, TP) est ouverte à tout enseignant de l'application
    personnelle et à toutes les éditions du secondaire ; les cours par classe et matière demandent le périmètre professeur."""
    return config.secondaire() or (config.enseignant() and getattr(g, "user", None) is not None)


def definir(uid, m):
    if m not in dict(MODES):
        m = "titulaire"
    ex("INSERT INTO ens_mode (user_id, mode) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode", (uid, m))


def prof_actif():
    """Périmètre « professeur » ouvert pour la requête courante."""
    if config.secondaire():
        return True
    return config.enseignant() and getattr(g, "user", None) is not None and mode() in ("professeur", "les_deux")


def titulaire_actif():
    return not (config.enseignant() and mode() == "professeur")
