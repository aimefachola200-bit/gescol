# -*- coding: utf-8 -*-
"""v2.3.1 — Classes ouvertes : une classe jumelée ou multigrade compte pour UNE classe.

Règle (correction de l'utilisateur, 02/11/2026) : une classe physique = une salle, un maître. Elle réunit un cours (classe
simple), deux cours (classe jumelée, ex. CI-CP) ou trois cours et plus (classe multigrade, ex. CI-CE2-CM1).
Classes ouvertes = simples + jumelées + multigrades (ex. CI-CP, CE1-CE2, CM1-CM2 = 3 classes ; CI + CE2 + CM1 en
multigrade = 1 classe). Les effectifs restent comptés par cours ; le nombre de classes et tous les indicateurs qui en
dépendent (élèves / classe, classes / salle, enseignants / classe, besoin en enseignants, tables-bancs par classe…)
utilisent les classes OUVERTES. Les classes autorisées sont un chiffre à part, qui peut être inférieur : l'écart est montré.

Données : chaque ligne de la table ``classes`` est un cours (effectifs par cours) ; les lignes d'une même classe physique
portent la même clé ``groupe_classe`` (vide = classe simple). Paquet de transmission (section « effectifs », jur_format) :
chaque classe porte ``groupe`` (« simple » | « jumele » | « multigrade »), ``groupe_id`` (clé commune, "" si simple) et
``cours_groupe`` (« CI-CP »). Une ligne « jumele » / « multigrade » sans ``groupe_id`` (ancien format, un cours par ligne
inconnu) compte pour une classe.
"""
import re

ORDRE_COURS = ["Maternelle 1", "Maternelle 2", "Maternelle 3", "CI", "CP", "CE1", "CE2", "CM1", "CM2",
               "6e", "5e", "4e", "3e", "2nde", "1ère", "Tle"]
ORG_LIB = {"simple": "Simple", "jumelee": "Jumelée", "multigrade": "Multigrade"}
ORG_TRANSMISSION = {"simple": "simple", "jumelee": "jumele", "multigrade": "multigrade"}


def rang(niveau):
    try:
        return ORDRE_COURS.index(niveau)
    except ValueError:
        return 99


def organisation(cours):
    n = len(set(c for c in cours if c))
    return "simple" if n <= 1 else ("jumelee" if n == 2 else "multigrade")


def physiques(classes):
    """Lignes de classes (dict : id, nom, niveau, groupe_classe) -> classes physiques
    [{"cle", "classes": [lignes], "cours": [niveaux triés], "organisation", "libelle"}] (ordre des cours)."""
    groupes, seules = {}, []
    for c in classes:
        k = str(c.get("groupe_classe") or "").strip()
        if k:
            groupes.setdefault(k, []).append(c)
        else:
            seules.append([c])
    out = []
    for k, membres in [(None, m) for m in seules] + list(groupes.items()):
        cours = sorted({m.get("niveau") or "" for m in membres}, key=rang)
        org = organisation(cours)
        out.append({"cle": k or "", "classes": membres, "cours": cours, "organisation": org,
                    "libelle": "-".join(cours) if org != "simple" else (membres[0].get("nom") or cours[0] if cours else ""),
                    "noms": " + ".join(m.get("nom") or "" for m in membres)})
    out.sort(key=lambda p: (min(rang(c) for c in p["cours"]) if p["cours"] else 99, p["noms"]))
    return out


def compter(classes):
    """{"simples", "jumelees", "multigrades", "total"} (classes ouvertes)."""
    ps = physiques(classes)
    d = {"simples": sum(1 for p in ps if p["organisation"] == "simple"),
         "jumelees": sum(1 for p in ps if p["organisation"] == "jumelee"),
         "multigrades": sum(1 for p in ps if p["organisation"] == "multigrade")}
    d["total"] = d["ouvertes"] = d["simples"] + d["jumelees"] + d["multigrades"]
    return d


def compter_transmises(lst):
    """Classes d'une section « effectifs » transmise -> (compte, [effectif de chaque classe physique])."""
    groupes, tailles = {}, []
    d = {"simples": 0, "jumelees": 0, "multigrades": 0}
    for c in lst or []:
        k = str(c.get("groupe_id") or "").strip()
        eff = _entier(c.get("garcons")) + _entier(c.get("filles"))
        if k:
            gr = groupes.setdefault(k, {"cours": set(), "eff": 0})
            gr["cours"].add(c.get("niveau") or "")
            gr["eff"] += eff
            continue
        g = (c.get("groupe") or "simple").lower()
        d["jumelees" if g.startswith("jumel") else ("multigrades" if g.startswith("multi") else "simples")] += 1
        tailles.append(eff)
    for gr in groupes.values():
        d[{"simple": "simples", "jumelee": "jumelees", "multigrade": "multigrades"}[organisation(gr["cours"])]] += 1
        tailles.append(gr["eff"])
    d["total"] = d["ouvertes"] = d["simples"] + d["jumelees"] + d["multigrades"]
    return d, tailles


def _entier(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def code_paire(cours):
    """["CI", "CP"] -> "CI_CP" (cases « jumelée » des rapports officiels)."""
    return "_".join(cours)


def ecart_autorisees(ouvertes, autorisees):
    """État de l'écart ouvertes − autorisées (information seulement ; mêmes libellés que outils/lots/classes.js)."""
    try:
        a = int(re.sub(r"[^\d-]", "", str(autorisees)))
    except ValueError:
        return "Autorisées non renseignées"
    o = int(ouvertes or 0)
    if o > a:
        return f"Au-delà des classes autorisées (+{o - a})"
    if o < a:
        return f"En deçà des classes autorisées ({o - a})"
    return "Conforme"


ENTETES = ["Classes simples", "Classes jumelées", "Classes multigrades", "Total classes ouvertes", "Classes autorisées",
           "Écart (ouvertes − autorisées)"]


def enregistrer(app, H):
    from flask import abort, flash, g, redirect, request, url_for
    q, ex = H.q, H.ex
    H.ajouter_colonne("classes", "groupe_classe", "TEXT")

    def classes_ecole(eco=None):
        return [dict(c) for c in q("SELECT * FROM classes WHERE ecole_id=? ORDER BY nom", (eco or H.eco(),))]

    def classes_ouvertes(eco=None, niveaux=None):
        cl = classes_ecole(eco)
        if niveaux is not None:
            cl = [c for c in cl if c["niveau"] in niveaux]
        return compter(cl)

    def organisation_classes(eco=None):
        ps = physiques(classes_ecole(eco))
        par_id = {}
        for p in ps:
            for c in p["classes"]:
                par_id[c["id"]] = p
        d = compter(classes_ecole(eco))
        return {"physiques": ps, "par_id": par_id, "compte": d, "lib": ORG_LIB}

    H.classes_ouvertes = classes_ouvertes
    H.classes_physiques = lambda eco=None: physiques(classes_ecole(eco))
    H.organisation_classes = organisation_classes

    @app.context_processor
    def _ctx_classes_org():
        return {"organisation_classes": organisation_classes}

    @app.route("/classes/regrouper", methods=["POST"])
    @H.connexion_requise("classes")
    def classes_regrouper():
        ids = sorted({int(x) for x in request.form.getlist("ids") if str(x).isdigit()})
        mes = {c["id"]: c for c in classes_ecole()}
        ids = [i for i in ids if i in mes]
        if len(ids) < 2:
            flash("Cochez au moins deux cours de la même classe (même salle, même maître).", "warning")
            return redirect(url_for("classes"))
        anciens = {mes[i]["groupe_classe"] for i in ids if mes[i].get("groupe_classe")}
        cle = sorted(anciens)[0] if anciens else f"g{min(ids)}"
        for i in ids:
            ex("UPDATE classes SET groupe_classe=? WHERE id=?", (cle, i))
        for a in anciens - {cle}:                      # deux groupes réunis
            ex("UPDATE classes SET groupe_classe=? WHERE groupe_classe=? AND ecole_id=?", (cle, a, H.eco()))
        cours = sorted({mes[i]["niveau"] for i in ids}, key=rang)
        H.journal("classes_regroupees", " + ".join(mes[i]["nom"] for i in ids))
        flash(f"Classe {ORG_LIB[organisation(cours)].lower()} {'-'.join(cours)} : elle compte pour une classe ouverte.", "success")
        return redirect(url_for("classes"))

    @app.route("/classes/separer/<cle>", methods=["POST"])
    @H.connexion_requise("classes")
    def classes_separer(cle):
        if not re.fullmatch(r"[\w-]{1,40}", cle or ""):
            abort(404)
        n = ex("UPDATE classes SET groupe_classe=NULL WHERE groupe_classe=? AND ecole_id=?", (cle, H.eco()))
        H.journal("classes_separees", cle)
        flash("Cours séparés : chacun redevient une classe simple.", "success")
        return redirect(url_for("classes"))
