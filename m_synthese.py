# -*- coding: utf-8 -*-
"""Synthèse de l'évaluation — École / UP / CS.

* /synthese            : choix de l'évaluation (type, numéro, classe ou toutes les classes), en-tête
                         (Zone, UP, École, DDEMP, Année, Directeur(trice), CCS, Titulaire), fiches de saisie par
                         classe (pré-remplies depuis les évaluations de GESCOL, modifiables, et fiches libres pour
                         les autres écoles de l'UP / CS), synthèse générale par niveau et analyse des résultats.
* /synthese/pdf        : PDF paysage (signatures + cachet) de la synthèse enregistrée
* /synthese/excel      : classeur Excel (une feuille par fiche + synthèse + écarts de genre + analyse)

Définitions (vocabulaire du primaire) :
* maîtrise maximale d'une matière  = élèves ayant obtenu au moins 10/20 dans la matière ;
* maîtrise partielle d'une matière = élèves ayant composé sans atteindre 10/20 (= ont composé − maîtrise maximale) ;
* % de réussite d'une matière       = maîtrise maximale / ont composé ; « à renforcer » si < 50 % ;
* réussite de la classe             = élèves ayant atteint le SEUIL de maîtrise de l'évaluation (règle officielle,
                                      voir evaluations_core.py) ; taux = ont atteint le seuil / ont composé.
Les données sont enregistrées (JSON) dans documents_modules sous la clé « e<école>:synthese:<année>:<type><n°> ».
"""
import re

from flask import flash, g, redirect, render_template, request, url_for

import evaluations_core as EC
from calcul import NIVEAUX_MATERNELLE, NIVEAUX_PRIMAIRE, NIVEAUX_SECONDAIRE, cycle_du_niveau

NIVEAUX = NIVEAUX_PRIMAIRE + NIVEAUX_SECONDAIRE + NIVEAUX_MATERNELLE
SEXES = ("g", "f")
# champs saisis d'une ligne « matière » : inscrits, ont composé, maîtrise maximale (≥ 10/20) — par sexe
CHAMPS_MATIERE = ("ig", "if", "cg", "cf", "mg", "mf")
# champs saisis du bloc « participation & réussite au seuil » : inscrits, ont composé, ont atteint le seuil
CHAMPS_SEUIL = ("ig", "if", "cg", "cf", "rg", "rf")
CHAMPS_ENTETE = ("ddemp", "cs", "zone", "up", "ecole", "annee", "directeur_titre", "directeur_nom",
                 "ccs_titre", "ccs_nom", "titulaire_titre", "titulaire_nom")
TAUX_REFERENCE = 50  # % en dessous duquel une matière / un niveau est « à renforcer »
MAX_FICHES = 60
MAX_MATIERES = 25


# ============================================================ calculs (fonctions pures, testables)
def pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def entier(v):
    """Texte saisi -> entier >= 0, ou None si vide. ValueError si invalide."""
    if v is None:
        return None
    s = str(v).strip().replace(" ", "")
    if s == "":
        return None
    n = float(s.replace(",", "."))
    if n < 0 or n != int(n) or n > 100000:
        raise ValueError(s)
    return int(n)


def appreciation(taux):
    """Appréciation globale d'un taux de réussite au seuil."""
    if taux is None:
        return "Données insuffisantes"
    if taux >= 80:
        return "Très satisfaisant"
    if taux >= 60:
        return "Satisfaisant"
    if taux >= TAUX_REFERENCE:
        return "Passable"
    if taux >= 30:
        return "Insuffisant"
    return "Très insuffisant"


def observation_auto(taux):
    if taux is None:
        return "Pas de données"
    if taux >= 75:
        return "Très bons résultats"
    if taux >= TAUX_REFERENCE:
        return "Résultats satisfaisants"
    if taux >= 25:
        return "Résultats insuffisants : remédiation nécessaire"
    return "Résultats très faibles : remédiation urgente"


def _trio(g_, f_):
    return {"g": g_, "f": f_, "t": g_ + f_}


def calculer_fiche(fiche):
    """Fiche saisie -> lignes calculées par matière, ligne ENSEMBLE, bloc seuil, matières à renforcer, alertes.
    Une case « inscrits » ou « ont composé » vide dans une matière reprend la valeur du bloc seuil de la classe."""
    s = fiche.get("seuil") or {}
    sv = {k: int(s.get(k) or 0) for k in CHAMPS_SEUIL}
    alertes = []
    ins, comp, reu = _trio(sv["ig"], sv["if"]), _trio(sv["cg"], sv["cf"]), _trio(sv["rg"], sv["rf"])
    for k in SEXES:
        lib = "garçons" if k == "g" else "filles"
        if comp[k] > ins[k]:
            alertes.append(f"Participation : plus de {lib} ayant composé ({comp[k]}) que d'inscrits ({ins[k]}).")
        if reu[k] > comp[k]:
            alertes.append(f"Seuil : plus de {lib} ayant atteint le seuil ({reu[k]}) que de {lib} ayant composé ({comp[k]}).")
    seuil = {"inscrits": ins, "composes": comp, "reussis": reu,
             "echecs": {k: max(0, comp[k] - reu[k]) for k in "gft"},
             "taux": {k: pct(reu[k], comp[k]) for k in "gft"},
             "participation": {k: pct(comp[k], ins[k]) for k in "gft"}}
    lignes = []
    tot = {"p": {"g": 0, "f": 0}, "m": {"g": 0, "f": 0}, "c": {"g": 0, "f": 0}}
    for m in fiche.get("matieres") or []:
        nom = (m.get("nom") or "").strip()
        if not nom:
            continue
        v = {}
        for k in SEXES:
            i_ = m.get("i" + k)
            c_ = m.get("c" + k)
            v["i" + k] = int(i_) if i_ not in (None, "") else sv["i" + k]
            v["c" + k] = int(c_) if c_ not in (None, "") else sv["c" + k]
            v["m" + k] = int(m.get("m" + k) or 0)
            if v["m" + k] > v["c" + k]:
                alertes.append(f"{nom} : maîtrise maximale ({v['m' + k]}) supérieure au nombre de "
                               f"{'garçons' if k == 'g' else 'filles'} ayant composé ({v['c' + k]}).")
            if v["c" + k] > v["i" + k]:
                alertes.append(f"{nom} : plus de {'garçons' if k == 'g' else 'filles'} ayant composé que d'inscrits.")
        l = {"nom": nom,
             "inscrits": _trio(v["ig"], v["if"]), "composes": _trio(v["cg"], v["cf"]),
             "maximale": _trio(v["mg"], v["mf"]),
             "partielle": _trio(max(0, v["cg"] - v["mg"]), max(0, v["cf"] - v["mf"]))}
        l["taux"] = {k: pct(l["maximale"][k], l["composes"][k]) for k in "gft"}
        l["renforcer"] = l["taux"]["t"] is not None and l["taux"]["t"] < TAUX_REFERENCE
        for k in SEXES:
            tot["p"][k] += l["partielle"][k]
            tot["m"][k] += l["maximale"][k]
            tot["c"][k] += l["composes"][k]
        lignes.append(l)
    # ENSEMBLE : effectifs de la classe ; maîtrises = cumul des copies de toutes les matières
    ens = {"nom": "ENSEMBLE", "inscrits": ins, "composes": comp,
           "partielle": _trio(tot["p"]["g"], tot["p"]["f"]), "maximale": _trio(tot["m"]["g"], tot["m"]["f"])}
    copies = _trio(tot["c"]["g"], tot["c"]["f"])
    ens["taux"] = {k: pct(ens["maximale"][k], copies[k]) for k in "gft"}
    renforcer = [l["nom"] for l in lignes if l["renforcer"]]
    return {"fiche": fiche, "lignes": lignes, "par_nom": {l["nom"]: l for l in lignes}, "ensemble": ens, "seuil": seuil, "renforcer": renforcer,
            "alertes": alertes, "vide": comp["t"] == 0}


def ordre_niveau(niv):
    return (NIVEAUX.index(niv), "") if niv in NIVEAUX else (len(NIVEAUX), niv or "")


def synthese_niveaux(calculs, observations=None):
    """Regroupe les fiches calculées par niveau de classe (et total général)."""
    observations = observations or {}
    groupes = {}
    for c in calculs:
        niv = (c["fiche"].get("niveau") or c["fiche"].get("classe") or "?").strip()
        groupes.setdefault(niv, []).append(c)
    lignes = []

    def agreger(liste, niveau):
        d = {"niveau": niveau, "classes": [c["fiche"].get("classe") or "" for c in liste],
             "ecoles": sorted({(c["fiche"].get("ecole") or "").strip() for c in liste} - {""})}
        for cle in ("inscrits", "composes", "reussis"):
            d[cle] = {k: sum(c["seuil"][cle][k] for c in liste) for k in "gft"}
        d["taux"] = {k: pct(d["reussis"][k], d["composes"][k]) for k in "gft"}
        d["participation"] = {k: pct(d["composes"][k], d["inscrits"][k]) for k in "gft"}
        mats = {}
        for c in liste:
            for l in c["lignes"]:
                x = mats.setdefault(l["nom"].strip().lower(), {"nom": l["nom"], "m": 0, "c": 0})
                x["m"] += l["maximale"]["t"]
                x["c"] += l["composes"]["t"]
        d["matieres"] = [{"nom": x["nom"], "taux": pct(x["m"], x["c"])} for x in mats.values()]
        d["renforcer"] = [x["nom"] for x in d["matieres"] if x["taux"] is not None and x["taux"] < TAUX_REFERENCE]
        return d

    for niv in sorted(groupes, key=ordre_niveau):
        d = agreger(groupes[niv], niv)
        d["observation"] = (observations.get(niv) or "").strip() or observation_auto(d["taux"]["t"])
        d["observation_auto"] = not (observations.get(niv) or "").strip()
        lignes.append(d)
    total = agreger(calculs, "TOTAL") if calculs else None
    if total:
        total["observation"] = observation_auto(total["taux"]["t"])
    return lignes, total


def _fr(v, dec=2):
    """12.5 -> « 12,5 » ; None -> « — »."""
    if v is None:
        return "—"
    return (f"{v:.{dec}f}".rstrip("0").rstrip(".") or "0").replace(".", ",")


def _liste(noms):
    noms = [n for n in noms if n]
    if not noms:
        return "aucune classe"
    return ", ".join(noms)


def analyse(niveaux, total, calculs):
    """Textes de l'analyse : 1. quantitative ; 2. qualitative ; 3. écarts de genre."""
    a = {"quantitative": [], "qualitative": [], "genre": [], "genre_lignes": []}
    if not total or total["composes"]["t"] == 0:
        msg = "Données insuffisantes : aucun élève n'a composé (ou les fiches ne sont pas encore renseignées)."
        a["quantitative"].append(msg)
        a["qualitative"].append(msg)
    else:
        I, C, R, T = total["inscrits"], total["composes"], total["reussis"], total["taux"]
        a["quantitative"] += [
            f"Effectif inscrit : {I['t']} élève(s) ({I['g']} garçon(s), {I['f']} fille(s)), réparti(s) dans "
            f"{len(calculs)} classe(s) de {len(niveaux)} niveau(x)"
            + (f" et {len(total['ecoles'])} école(s)" if len(total["ecoles"]) > 1 else "") + ".",
            f"Ont composé : {C['t']} élève(s) ({C['g']} G, {C['f']} F), soit un taux de participation de "
            f"{_fr(total['participation']['t'])} %.",
            f"Ont atteint le seuil de maîtrise : {R['t']} élève(s) ({R['g']} G, {R['f']} F), soit un taux de réussite de "
            f"{_fr(T['t'])} % (garçons : {_fr(T['g'])} % ; filles : {_fr(T['f'])} %).",
            f"N'ont pas atteint le seuil : {C['t'] - R['t']} élève(s).",
        ]
        avec = [n for n in niveaux if n["taux"]["t"] is not None]
        if len(avec) > 1:
            mx = max(avec, key=lambda n: n["taux"]["t"])
            mn = min(avec, key=lambda n: n["taux"]["t"])
            a["quantitative"].append(f"Meilleur taux : {mx['niveau']} ({_fr(mx['taux']['t'])} %) ; "
                                     f"taux le plus faible : {mn['niveau']} ({_fr(mn['taux']['t'])} %).")
        app_ = appreciation(T["t"])
        pos = "supérieur ou égal" if T["t"] >= TAUX_REFERENCE else "inférieur"
        a["qualitative"].append(
            f"Appréciation globale : {app_.upper()}. Le taux de réussite au seuil ({_fr(T['t'])} %) est {pos} au "
            f"taux de référence de {TAUX_REFERENCE} % : "
            + ("plus de la moitié des élèves ayant composé maîtrisent les compétences évaluées."
               if T["t"] >= TAUX_REFERENCE else
               "moins de la moitié des élèves ayant composé maîtrisent les compétences évaluées."))
        sous = [n["niveau"] for n in niveaux if n["taux"]["t"] is not None and n["taux"]["t"] < TAUX_REFERENCE]
        a["qualitative"].append("Niveau(x) sous le taux de référence : " + (", ".join(sous) if sous else "aucun") + ".")
        a["qualitative"].append("Matières à renforcer sur l'ensemble (moins de 50 % de réussite) : "
                                + (", ".join(total["renforcer"]) if total["renforcer"] else "aucune") + ".")
    # 3. écarts de genre par classe (niveau)
    insuffisant, garcons, filles, egal = [], [], [], []
    for n in niveaux:
        tg, tf = n["taux"]["g"], n["taux"]["f"]
        ecart = round(tf - tg, 2) if tg is not None and tf is not None else None
        a["genre_lignes"].append({"niveau": n["niveau"], "g": tg, "f": tf, "ecart": ecart})
        if ecart is None:
            insuffisant.append(n["niveau"])
        elif ecart > 0:
            filles.append(n["niveau"])
        elif ecart < 0:
            garcons.append(n["niveau"])
        else:
            egal.append(n["niveau"])
    if insuffisant:
        a["genre"].append("Données insuffisantes pour comparer garçons et filles en : " + ", ".join(insuffisant)
                          + " (aucun garçon ou aucune fille n'a composé).")
    a["genre"].append("Les garçons sont en avance en : " + _liste(garcons) + ".")
    a["genre"].append("Les filles sont en avance en : " + _liste(filles) + ".")
    if egal:
        a["genre"].append("Égalité parfaite en : " + ", ".join(egal) + ".")
    if total and total["taux"]["g"] is not None and total["taux"]["f"] is not None:
        e = round(total["taux"]["f"] - total["taux"]["g"], 2)
        a["genre"].append("Sur l'ensemble : " + ("égalité entre garçons et filles." if e == 0 else
                          f"écart de {_fr(abs(e))} point(s) en faveur des {'filles' if e > 0 else 'garçons'}."))
    return a


# ============================================================ module
def enregistrer(app, H):
    q = H.q

    def cle_doc(annee, type_, numero):
        return f"e{H.eco()}:synthese:{annee}:{type_}{numero}"

    def selection():
        """Paramètres de sélection (GET ou POST) validés."""
        v = request.values
        type_ = v.get("type") if v.get("type") in EC.TYPES else "sommative"
        try:
            numero = min(50, max(1, int(v.get("numero") or 1)))
        except ValueError:
            numero = 1
        cid = v.get("classe", type=int)
        if cid:
            H.verifier_classe(cid)
        return type_, numero, cid

    def classes_synthese():
        """Classes de l'école prises en compte (primaire et secondaire ; la maternelle n'a pas de seuil)."""
        return [c for c in H.classes_autorisees() if cycle_du_niveau(c["niveau"]) != "maternelle"]

    def evaluation_de(cl, type_, numero):
        lib = EC.libelle(type_, numero)
        ev = q("SELECT id FROM evaluations WHERE classe_id=? AND annee=? AND libelle=?",
               (cl["id"], H.config.ANNEE_ACTIVE, lib), un=True)
        return EC.evaluation(ev["id"]) if ev else None

    def fiche_gescol(cl, type_, numero, ecole):
        """Fiche pré-remplie depuis les notes GESCOL de l'évaluation choisie (vide si l'évaluation n'existe pas)."""
        cl = dict(cl)
        cl["cycle"] = cycle_du_niveau(cl["niveau"])
        ev = evaluation_de(cl, type_, numero)
        f = {"id": f"c{cl['id']}", "classe_id": cl["id"], "ecole": ecole, "classe": cl["nom"], "niveau": cl["niveau"],
             "source": "gescol", "evaluation": bool(ev)}
        if ev:
            matieres, lignes = EC.resultats(ev, cl)
            st = EC.statistiques(matieres, lignes)
            f["seuil"] = {"ig": st["inscrits"]["G"], "if": st["inscrits"]["F"], "cg": st["composes"]["G"],
                          "cf": st["composes"]["F"], "rg": st["reussis"]["G"], "rf": st["reussis"]["F"]}
            f["matieres"] = [{"nom": d["matiere"]["nom"], "ig": st["inscrits"]["G"], "if": st["inscrits"]["F"],
                              "cg": d["G"]["composes"], "cf": d["F"]["composes"],
                              "mg": d["G"]["reussis"], "mf": d["F"]["reussis"]} for d in st["par_matiere"]]
        else:
            eleves = EC.eleves_classe(cl["id"])
            ng = sum(1 for e in eleves if e["sexe"] == "M")
            nf = sum(1 for e in eleves if e["sexe"] == "F")
            f["seuil"] = {"ig": ng, "if": nf, "cg": 0, "cf": 0, "rg": 0, "rf": 0}
            f["matieres"] = [{"nom": m["nom"], "ig": None, "if": None, "cg": None, "cf": None, "mg": 0, "mf": 0}
                             for m in EC.matieres_cycle(cl["cycle"])]
        return f

    def classes_prefill(type_, numero, cid):
        """Classes à pré-remplir : la classe choisie, ou toutes les classes du primaire + les classes du
        secondaire qui ont l'évaluation."""
        out = []
        for c in classes_synthese():
            if cid and c["id"] != cid:
                continue
            if cid or cycle_du_niveau(c["niveau"]) == "primaire" or evaluation_de(c, type_, numero):
                out.append(c)
        return out

    def entete_defaut(cid):
        cl = H.classe_ou_404(cid) if cid else None
        return H.identification(cl)

    def lire_doc(type_, numero, annee=None):
        return H.doc_lire(cle_doc(annee or H.config.ANNEE_ACTIVE, type_, numero), None)

    def document(type_, numero, cid, forcer_prefill=False):
        """Document de synthèse : enregistré s'il existe, sinon pré-rempli depuis GESCOL."""
        doc = lire_doc(type_, numero)
        neuf = doc is None
        if neuf:
            doc = {"entete": {}, "fiches": [], "observations": {}}
        ent = entete_defaut(cid)
        ent.update({k: v for k, v in (doc.get("entete") or {}).items() if v})
        if cid:  # titulaire de la classe choisie
            cl = H.classe_ou_404(cid)
            if not (doc.get("titulaires") or {}).get(str(cid)):
                ent["titulaire_titre"] = cl["titulaire_titre"] or ent.get("titulaire_titre") or "Le titulaire"
                ent["titulaire_nom"] = cl["titulaire_nom"] or ""
            else:
                ent.update(doc["titulaires"][str(cid)])
        doc["entete"] = ent
        if neuf or forcer_prefill:
            existantes = {f["id"]: f for f in doc["fiches"]}
            for c in classes_prefill(type_, numero, cid):
                f = fiche_gescol(c, type_, numero, ent.get("ecole") or "")
                existantes[f["id"]] = f
            doc["fiches"] = trier(list(existantes.values()))
        return doc, neuf

    def trier(fiches):
        return sorted(fiches, key=lambda f: (f.get("source") != "gescol", (f.get("ecole") or "").lower(),
                                            ordre_niveau(f.get("niveau")), (f.get("classe") or "").lower()))

    def visibles(doc, cid):
        if cid:
            return [f for f in doc["fiches"] if f.get("classe_id") == cid]
        return doc["fiches"]

    def lire_formulaire(doc, cid):
        """Relit les fiches, l'en-tête et les observations postés ; renvoie (doc, erreurs)."""
        f = request.form
        erreurs = []
        ent = {k: (f.get(k) or "").strip()[:150] for k in CHAMPS_ENTETE}
        titulaires = dict(doc.get("titulaires") or {})
        if cid:
            titulaires[str(cid)] = {"titulaire_titre": ent["titulaire_titre"], "titulaire_nom": ent["titulaire_nom"]}
        doc["titulaires"] = titulaires
        doc["entete"] = ent
        idx = sorted({int(m.group(1)) for k in f for m in [re.match(r"^f(\d+)_id$", k)] if m})
        postees = {}
        for i in idx[:MAX_FICHES]:
            p = f"f{i}_"
            fid = (f.get(p + "id") or "").strip()[:20]
            if not re.match(r"^[cx]\d+$", fid):
                continue
            ancienne = next((x for x in doc["fiches"] if x["id"] == fid), {})
            if cid and ancienne.get("classe_id") != cid:
                continue  # vue d'une classe : on ne modifie que sa fiche
            if f.get(p + "suppr"):
                postees[fid] = None
                continue
            fiche = {"id": fid, "classe_id": ancienne.get("classe_id"), "source": ancienne.get("source", "libre"),
                     "evaluation": ancienne.get("evaluation"),
                     "ecole": (f.get(p + "ecole") or "").strip()[:120],
                     "classe": (f.get(p + "classe") or "").strip()[:60] or ancienne.get("classe") or "Classe",
                     "niveau": (f.get(p + "niveau") or "").strip()[:30]}
            nom_c = fiche["classe"]
            seuil = {}
            for k in CHAMPS_SEUIL:
                try:
                    seuil[k] = entier(f.get(p + "s_" + k)) or 0
                except ValueError:
                    erreurs.append(f"{nom_c} – participation : « {f.get(p + 's_' + k)} » n'est pas un nombre entier.")
                    seuil[k] = 0
            fiche["seuil"] = seuil
            mats = []
            jdx = sorted({int(m.group(1)) for k in f for m in [re.match(rf"^{p}m(\d+)_nom$", k)] if m})
            for j in jdx[:MAX_MATIERES]:
                pm = f"{p}m{j}_"
                nom = (f.get(pm + "nom") or "").strip()[:80]
                ligne = {"nom": nom}
                for k in CHAMPS_MATIERE:
                    try:
                        ligne[k] = entier(f.get(pm + k))
                    except ValueError:
                        erreurs.append(f"{nom_c} – {nom or 'matière'} : « {f.get(pm + k)} » n'est pas un nombre entier.")
                        ligne[k] = None
                if nom:
                    mats.append(ligne)
                elif any(ligne[k] for k in CHAMPS_MATIERE):
                    erreurs.append(f"{nom_c} : une ligne sans nom de matière a été ignorée.")
            fiche["matieres"] = mats
            postees[fid] = fiche
        fiches = []
        for x in doc["fiches"]:
            if x["id"] in postees:
                if postees[x["id"]] is not None:
                    fiches.append(postees.pop(x["id"]))
                else:
                    postees.pop(x["id"])
            else:
                fiches.append(x)
        fiches += [x for x in postees.values() if x is not None]
        doc["fiches"] = trier(fiches)
        obs = dict(doc.get("observations") or {})
        for k, v in f.items():
            if k.startswith("obs_"):
                obs[k[4:][:30]] = v.strip()[:200]
        doc["observations"] = obs
        return doc, erreurs

    def nouvelle_fiche(doc, ecole):
        n = 1 + max([int(x["id"][1:]) for x in doc["fiches"] if x["id"].startswith("x")] or [0])
        mats = [{"nom": m["nom"], "ig": None, "if": None, "cg": None, "cf": None, "mg": 0, "mf": 0}
                for m in EC.matieres_cycle("primaire")]
        doc["fiches"].append({"id": f"x{n}", "classe_id": None, "source": "libre", "ecole": ecole, "classe": "",
                              "niveau": "", "seuil": {k: 0 for k in CHAMPS_SEUIL}, "matieres": mats})
        return f"x{n}"

    def rapport(doc, cid):
        fiches = visibles(doc, cid)
        calculs = [calculer_fiche(f) for f in fiches]
        niveaux, total = synthese_niveaux(calculs, doc.get("observations"))
        return {"calculs": calculs, "niveaux": niveaux, "total": total, "analyse": analyse(niveaux, total, calculs)}

    def sauver(type_, numero, doc):
        doc["maj"] = H.maintenant()
        doc["maj_par"] = g.user["nom"] if g.get("user") else ""
        H.doc_ecrire(cle_doc(H.config.ANNEE_ACTIVE, type_, numero), doc)

    def nom_fichier(type_, numero, cid, ext):
        base = f"synthese_{EC.libelle(type_, numero)}"
        if cid:
            base += "_" + H.classe_ou_404(cid)["nom"]
        return re.sub(r"[^A-Za-z0-9]+", "_", H.xlsx.normaliser(base)).strip("_") + "." + ext

    # ------------------------------------------------------------------ page
    @app.route("/synthese", methods=["GET", "POST"])
    @H.connexion_requise("synthese")
    def synthese_accueil():
        type_, numero, cid = selection()
        classes = classes_synthese()
        if request.method == "POST":
            action = request.form.get("action", "sauver")
            if action == "prefill":
                doc, _ = document(type_, numero, cid)
                doc, _ = lire_formulaire(doc, cid)  # garde l'en-tête et les fiches libres non sauvegardés
                ids = set()
                for c in classes_prefill(type_, numero, cid):
                    fg = fiche_gescol(c, type_, numero, doc["entete"].get("ecole") or "")
                    ids.add(fg["id"])
                    doc["fiches"] = [x for x in doc["fiches"] if x["id"] != fg["id"]] + [fg]
                doc["fiches"] = trier(doc["fiches"])
                sauver(type_, numero, doc)
                H.journal("synthese_prefill", f"{EC.libelle(type_, numero)} : {len(ids)} classe(s)")
                flash(f"{len(ids)} fiche(s) de classe recalculée(s) à partir des notes de GESCOL "
                      "(les fiches des autres écoles sont conservées).", "success")
                return redirect(url_for("synthese_accueil", type=type_, numero=numero, classe=cid or None))
            doc, _ = document(type_, numero, cid)
            doc, erreurs = lire_formulaire(doc, cid)
            for m in erreurs[:12]:
                flash(m, "danger")
            if action == "ajouter":
                if cid:
                    flash("Choisissez « Toutes les classes » pour ajouter la fiche d'une autre école.", "warning")
                elif len(doc["fiches"]) >= MAX_FICHES:
                    flash(f"Nombre maximal de fiches atteint ({MAX_FICHES}).", "warning")
                else:
                    fid = nouvelle_fiche(doc, "")
                    sauver(type_, numero, doc)
                    flash("Nouvelle fiche ajoutée en bas de page : renseignez l'école, la classe et les effectifs.", "success")
                    return redirect(url_for("synthese_accueil", type=type_, numero=numero) + f"#fiche-{fid}")
            sauver(type_, numero, doc)
            H.journal("synthese_sauvegarde", f"{EC.libelle(type_, numero)} ({len(doc['fiches'])} fiche(s))")
            if action == "pdf":
                return reponse_pdf(type_, numero, cid, doc)
            if action == "excel":
                return reponse_excel(type_, numero, cid, doc)
            flash("Synthèse sauvegardée." + (f" {len(erreurs)} valeur(s) invalide(s) remplacée(s) par 0 : corrigez-les."
                                              if erreurs else ""), "warning" if erreurs else "success")
            return redirect(url_for("synthese_accueil", type=type_, numero=numero, classe=cid or None))
        doc, neuf = document(type_, numero, cid)
        if cid and not visibles(doc, cid):  # classe ajoutée après la première sauvegarde
            c = H.classe_ou_404(cid)
            doc["fiches"] = trier(doc["fiches"] + [fiche_gescol(c, type_, numero, doc["entete"].get("ecole") or "")])
        r = rapport(doc, cid)
        return render_template("synthese_accueil.html", doc=doc, neuf=neuf, r=r, type_=type_, numero=numero, cid=cid,
                               classes=classes, TYPES=EC.TYPES, NIVEAUX=NIVEAUX, fr=_fr, TAUX_REFERENCE=TAUX_REFERENCE,
                               fiches=visibles(doc, cid), titre_ev=f"{EC.TYPES[type_]} N° {numero}")

    # ------------------------------------------------------------------ PDF
    def _titre_signataire(titre, defaut):
        t = (titre or defaut).strip()
        if t.lower().startswith(("le ", "la ", "l'", "l’")):
            return t
        if t[:1].upper() in "AEIOUÉÈ":
            return "L'" + t
        return ("La " if t.endswith(("trice", "rice", "e")) and not t.endswith("eur") else "Le ") + t

    def pdf_bytes(type_, numero, cid, doc):
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle
        pdfs = H.pdfs
        r = rapport(doc, cid)
        v = doc["entete"]
        BLEU = pdfs.BLEU

        def grille(data, largeurs, nh, spans=(), gras_derniere=False, rouges=()):
            t = Table(data, colWidths=[x * mm for x in largeurs], repeatRows=nh)
            s = [("FONT", (0, 0), (-1, -1), "Helvetica", 7), ("FONT", (0, 0), (-1, nh - 1), "Helvetica-Bold", 7),
                 ("BACKGROUND", (0, 0), (-1, nh - 1), BLEU), ("TEXTCOLOR", (0, 0), (-1, nh - 1), colors.white),
                 ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#667085")), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("LEFTPADDING", (0, 0), (-1, -1), 2),
                 ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                 ("ROWBACKGROUNDS", (0, nh), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")])]
            s += [("SPAN", a, b) for a, b in spans]
            if gras_derniere:
                s += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 7),
                      ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E4ECF5"))]
            for (cc, rr) in rouges:
                s.append(("TEXTCOLOR", (cc, rr), (cc, rr), pdfs.ROUGE))
            t.setStyle(TableStyle(s))
            return t

        def gft(d):
            return [d["g"], d["f"], d["t"]]

        def tx(d):
            return [_fr(d["g"]), _fr(d["f"]), _fr(d["t"])]

        avant = []
        for c in r["calculs"]:
            fi = c["fiche"]
            titre_f = f"<b>{fi.get('classe') or '—'}</b>" + (f" ({fi['niveau']})" if fi.get("niveau") else "") \
                + (f" — École : {fi['ecole']}" if fi.get("ecole") else "")
            entetes = [["Matière", "Inscrits", "", "", "Ont composé", "", "", "Maîtrise partielle (< 10)", "", "",
                        "Maîtrise maximale (≥ 10)", "", "", "% de réussite", "", "", "À renforcer"],
                       ["", "G", "F", "T", "G", "F", "T", "G", "F", "T", "G", "F", "T", "G", "F", "T", ""]]
            data = list(entetes)
            rouges = []
            for l in c["lignes"] + [c["ensemble"]]:
                row = [l["nom"]] + gft(l["inscrits"]) + gft(l["composes"]) + gft(l["partielle"]) + gft(l["maximale"]) \
                    + tx(l["taux"]) + (["OUI" if l.get("renforcer") else ""] if l["nom"] != "ENSEMBLE"
                                       else [", ".join(c["renforcer"]) or "—"])
                data.append(row)
                if l.get("renforcer"):
                    rouges += [(15, len(data) - 1), (16, len(data) - 1)]
            spans = [((0, 0), (0, 1)), ((16, 0), (16, 1))] + [((j, 0), (j + 2, 0)) for j in (1, 4, 7, 10, 13)]
            larg = [48] + [12.5] * 15 + [30]
            t1 = grille(data, larg, 2, spans, gras_derniere=True, rouges=rouges)
            S = c["seuil"]
            d2 = [["Participation & réussite au seuil", "Inscrits", "", "", "Ont composé", "", "",
                   "Ont atteint le seuil", "", "", "Taux de réussite (%)", "", "", "Participation (%)"],
                  ["", "G", "F", "T", "G", "F", "T", "G", "F", "T", "G", "F", "T", "T"],
                  ["Résultat officiel de la classe"] + gft(S["inscrits"]) + gft(S["composes"]) + gft(S["reussis"])
                  + tx(S["taux"]) + [_fr(S["participation"]["t"])]]
            spans2 = [((0, 0), (0, 1)), ((13, 0), (13, 1))] + [((j, 0), (j + 2, 0)) for j in (1, 4, 7, 10)]
            t2 = grille(d2, [48] + [12.5] * 12 + [25], 2, spans2)
            bloc = [pdfs.paragraphe("FICHE DE LA CLASSE : " + titre_f, 8.5, espace=4), t1, Spacer(1, 3), t2]
            if c["alertes"]:
                bloc.append(pdfs.paragraphe("<font color='#B42318'>À vérifier : " + " ; ".join(c["alertes"][:4]) + "</font>", 7))
            avant.append(KeepTogether(bloc))
            avant.append(Spacer(1, 8))
        avant.append(pdfs.paragraphe("<b>SYNTHÈSE GÉNÉRALE PAR NIVEAU DE CLASSE</b>", 9, espace=4))
        # tableau principal : synthèse par niveau
        colonnes = [["Niveau", "Classe(s)", "Inscrits", None, None, "Ont composé", None, None, "Ont réussi (seuil)", None,
                     None, "Taux de réussite (%)", None, None, "À renforcer", "Observation"],
                    ["^", "^", "G", "F", "T", "G", "F", "T", "G", "F", "T", "G", "F", "T", "^", "^"]]
        lignes = []
        for n in r["niveaux"]:
            lignes.append([n["niveau"], ", ".join(n["classes"])] + gft(n["inscrits"]) + gft(n["composes"])
                          + gft(n["reussis"]) + tx(n["taux"]) + [", ".join(n["renforcer"]) or "—", n["observation"]])
        total = None
        if r["total"]:
            T = r["total"]
            total = ["TOTAL", f"{len(r['calculs'])} classe(s)"] + gft(T["inscrits"]) + gft(T["composes"]) \
                + gft(T["reussis"]) + tx(T["taux"]) + [", ".join(T["renforcer"]) or "—", T["observation"]]
        # analyse
        A = r["analyse"]
        apres = [Spacer(1, 6), pdfs.paragraphe("<b>ANALYSE DES RÉSULTATS</b>", 9.5, espace=4),
                 pdfs.paragraphe("<b>1. Analyse quantitative</b>", 8.5)]
        apres += [pdfs.paragraphe("• " + x, 8) for x in A["quantitative"]]
        apres += [pdfs.paragraphe("<b>2. Analyse qualitative (appréciation globale par rapport au seuil)</b>", 8.5)]
        apres += [pdfs.paragraphe("• " + x, 8) for x in A["qualitative"]]
        apres += [pdfs.paragraphe("<b>3. Écarts de genre</b>", 8.5)]
        if A["genre_lignes"]:
            dg = [["Classe / niveau", "Garçons (%)", "Filles (%)", "Écart (F − G, points)"]]
            dg += [[x["niveau"], _fr(x["g"]), _fr(x["f"]),
                    "—" if x["ecart"] is None else (("+" if x["ecart"] > 0 else "") + _fr(x["ecart"]))]
                   for x in A["genre_lignes"]]
            apres.append(pdfs.mini_tableau(dg, [40 * mm, 28 * mm, 28 * mm, 40 * mm]))
        apres += [pdfs.paragraphe("• " + x, 8) for x in A["genre"]]
        eid = H.eco()
        s_dir = pdfs.image_data_url(H.signature(f"ecole:{eid}:directeur")) or pdfs.signature_directeur()
        s_ccs = pdfs.image_data_url(H.signature(f"ecole:{eid}:ccs"))
        sigs = []
        if cid:
            s_tit = pdfs.image_data_url(H.signature(f"classe:{cid}:titulaire"))
            sigs.append((v.get("titulaire_titre") or "Le titulaire", v.get("titulaire_nom") or "", s_tit, False))
        sigs.append((_titre_signataire(v.get("directeur_titre"), "Directeur"), v.get("directeur_nom") or "", s_dir, True))
        sigs.append((v.get("ccs_titre") or "Le CCS", v.get("ccs_nom") or "", s_ccs, False))
        infos = [("Zone pédagogique", v.get("zone")), ("Unité pédagogique", v.get("up")), ("École", v.get("ecole")),
                 ("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("Année scolaire", v.get("annee")),
                 ("Évaluation", f"{EC.TYPES[type_]} N° {numero}"),
                 ("Classe(s)", H.classe_ou_404(cid)["nom"] if cid else "Toutes les classes"),
                 ("Fiches", len(r["calculs"]))]
        notes_bas = ["<b>Définitions :</b> maîtrise maximale = élèves ayant obtenu au moins 10/20 dans la matière ; "
                     "maîtrise partielle = élèves ayant composé sans atteindre 10/20 ; % de réussite = maîtrise maximale / "
                     f"ont composé ; « à renforcer » = moins de {TAUX_REFERENCE} % de réussite. La réussite de la classe "
                     "correspond au SEUIL de maîtrise de l'évaluation (nombre de matières à 10/20 exigé). "
                     "ENSEMBLE : cumul des copies de toutes les matières."]
        return pdfs.document_tableau(
            f"SYNTHÈSE DE L'{EC.TYPES[type_].upper()} N° {numero}", colonnes, lignes,
            sous_titre=f"École / UP / CS – Année scolaire {v.get('annee') or H.config.ANNEE_ACTIVE}",
            infos=infos, largeurs=[16, 30, 9, 9, 9, 9, 9, 9, 9, 9, 9, 11, 11, 11, 35, 40], paysage=True,
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            taille=7, avant=avant, apres=apres, total=total, notes_bas=notes_bas, signatures=sigs)

    def reponse_pdf(type_, numero, cid, doc):
        H.journal("synthese_pdf", EC.libelle(type_, numero))
        return H.pdf_reponse(pdf_bytes(type_, numero, cid, doc), nom_fichier(type_, numero, cid, "pdf"))

    def doc_enregistre(type_, numero, cid):
        doc, _ = document(type_, numero, cid)
        return doc

    @app.route("/synthese/pdf")
    @H.connexion_requise("synthese")
    def synthese_pdf():
        type_, numero, cid = selection()
        return reponse_pdf(type_, numero, cid, doc_enregistre(type_, numero, cid))

    # ------------------------------------------------------------------ Excel
    def reponse_excel(type_, numero, cid, doc):
        r = rapport(doc, cid)
        v = doc["entete"]
        haut = [f"SYNTHÈSE DE L'{EC.TYPES[type_].upper()} N° {numero}",
                f"Zone : {v.get('zone') or '—'}    UP : {v.get('up') or '—'}    École : {v.get('ecole') or '—'}",
                f"DDEMP : {v.get('ddemp') or '—'}    CS : {v.get('cs') or '—'}    Année scolaire : {v.get('annee') or '—'}",
                f"{v.get('directeur_titre') or 'Directeur'} : {v.get('directeur_nom') or '—'}    "
                f"CCS : {v.get('ccs_nom') or '—'}"]
        feuilles = []
        ent_f = ["Matière"] + [f"{a} {s}" for a in ("Inscrits", "Ont composé", "Maîtrise partielle",
                                                     "Maîtrise maximale", "% réussite") for s in "GFT"] + ["À renforcer"]
        noms_vus = set()
        for c in r["calculs"]:
            fi = c["fiche"]
            lignes = []
            for l in c["lignes"] + [c["ensemble"]]:
                lignes.append([l["nom"]] + [l[k][s] for k in ("inscrits", "composes", "partielle", "maximale", "taux")
                                            for s in "gft"]
                              + (["OUI" if l.get("renforcer") else ""] if l["nom"] != "ENSEMBLE" else [", ".join(c["renforcer"])]))
            S = c["seuil"]
            lignes += [[], ["PARTICIPATION & RÉUSSITE AU SEUIL", "G", "F", "T"],
                       ["Inscrits"] + [S["inscrits"][s] for s in "gft"],
                       ["Ont composé"] + [S["composes"][s] for s in "gft"],
                       ["Ont atteint le seuil"] + [S["reussis"][s] for s in "gft"],
                       ["Taux de réussite (%)"] + [S["taux"][s] for s in "gft"],
                       ["Participation (%)"] + [S["participation"][s] for s in "gft"]]
            nom = re.sub(r"[\[\]:*?/\\]", "-", f"{fi.get('classe') or 'Fiche'}")[:25]
            base, k = nom, 2
            while nom.lower() in noms_vus:
                nom = f"{base[:22]} ({k})"
                k += 1
            noms_vus.add(nom.lower())
            feuilles.append((nom, ent_f, lignes, {"titre_haut": haut + [f"Classe : {fi.get('classe') or '—'} ({fi.get('niveau') or '—'})"
                                                                     f"    École : {fi.get('ecole') or '—'}"]}))
        ent_n = ["Niveau", "Classe(s)"] + [f"{a} {s}" for a in ("Inscrits", "Ont composé", "Ont réussi", "Taux %")
                                           for s in "GFT"] + ["À renforcer", "Observation"]
        ln = []
        for n in r["niveaux"] + ([r["total"]] if r["total"] else []):
            ln.append([n["niveau"], ", ".join(n["classes"]) if n["niveau"] != "TOTAL" else f"{len(r['calculs'])} classe(s)"]
                      + [n[k][s] for k in ("inscrits", "composes", "reussis", "taux") for s in "gft"]
                      + [", ".join(n["renforcer"]), n["observation"]])
        feuilles.insert(0, ("Synthèse par niveau", ent_n, ln, {"titre_haut": haut}))
        A = r["analyse"]
        feuilles.append(("Écarts de genre", ["Classe / niveau", "Garçons (%)", "Filles (%)", "Écart F − G (points)"],
                         [[x["niveau"], x["g"], x["f"], x["ecart"]] for x in A["genre_lignes"]] + [[]]
                         + [[t] for t in A["genre"]], {"titre_haut": haut}))
        feuilles.append(("Analyse", ["Analyse des résultats"],
                         [["1. Analyse quantitative"]] + [[t] for t in A["quantitative"]] + [[""], ["2. Analyse qualitative"]]
                         + [[t] for t in A["qualitative"]] + [[""], ["3. Écarts de genre"]] + [[t] for t in A["genre"]],
                         {"titre_haut": haut}))
        H.journal("synthese_excel", EC.libelle(type_, numero))
        try:
            return H.xlsx.reponse_classeur(nom_fichier(type_, numero, cid, "xlsx"), feuilles)
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("synthese_accueil", type=type_, numero=numero, classe=cid or None))

    @app.route("/synthese/excel")
    @H.connexion_requise("synthese")
    def synthese_excel():
        type_, numero, cid = selection()
        return reponse_excel(type_, numero, cid, doc_enregistre(type_, numero, cid))

    @app.route("/synthese/supprimer", methods=["POST"])
    @H.connexion_requise("synthese")
    def synthese_supprimer():
        """Supprime la synthèse enregistrée (elle sera de nouveau pré-remplie depuis GESCOL)."""
        type_, numero, cid = selection()
        db = H.get_db()
        db.execute("DELETE FROM documents_modules WHERE cle=?", (cle_doc(H.config.ANNEE_ACTIVE, type_, numero),))
        db.commit()
        H.journal("synthese_supprimee", EC.libelle(type_, numero))
        flash("Synthèse enregistrée supprimée : les fiches sont de nouveau pré-remplies depuis GESCOL.", "success")
        return redirect(url_for("synthese_accueil", type=type_, numero=numero, classe=cid or None))
