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
    return r["mode"] if r and r["mode"] in dict(MODES) else "titulaire"


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
