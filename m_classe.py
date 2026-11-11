# -*- coding: utf-8 -*-
"""v1.8 — l'école au quotidien : accueil par rôle, « Ma classe », groupes de remédiation, état des sauvegardes.

* Raccourcis de l'accueil selon le rôle (enseignant, directeur, secrétaire, comptable, fondateur ; CCS, CP, chefs de
  service dans les applications de circonscription) : fonction de gabarit ``raccourcis()``.
* /ma-classe, /ma-classe/<cid> : tableau de bord d'une classe pour son enseignant — effectifs, appel du jour, absences
  de la semaine, élèves absents à répétition, dernière évaluation (maîtrise, saisie incomplète), prochaines évaluations,
  élèves à suivre, boutons « Faire l'appel », « Saisir les notes », « Groupes de remédiation ». « / » y conduit
  l'enseignant (m_perimetre_enseignant).
* /evaluations/<ev_id>/remediation (+ .pdf, .xlsx) : après chaque évaluation, groupes de besoin par matière
  (soutien intensif, consolidation, maîtrise, approfondissement / tuteurs), élèves en non-maîtrise, matières à
  renforcer, activités proposées par discipline.
* ``etat_sauvegarde()`` : date de la dernière sauvegarde (automatique quotidienne ou manuelle) pour l'accueil.
"""
import io
import os
import unicodedata
from datetime import date, datetime, timedelta

from flask import Response, abort, g, redirect, render_template, url_for

import config
from db import q

GROUPES = [  # (clé, intitulé, borne basse incluse, borne haute exclue, conseil)
    ("g1", "Groupe 1 – Soutien intensif", 0, 7, "Reprendre les notions de base en petit groupe, avec du matériel concret, "
                                                 "des consignes courtes et une vérification à chaque étape."),
    ("g2", "Groupe 2 – Consolidation", 7, 10, "Exercices ciblés sur les erreurs fréquentes, travail en binôme, nouvelle "
                                              "évaluation courte après quelques séances."),
    ("g3", "Groupe 3 – Maîtrise", 10, 15, "Exercices d'entraînement et de transfert pour stabiliser les acquis."),
    ("g4", "Groupe 4 – Approfondissement / tuteurs", 15, 21, "Situations complexes et défis ; ces élèves peuvent "
                                                             "accompagner un camarade du groupe 1 ou 2 (tutorat)."),
]
APPRECIATION_GROUPE = {"NA": "g1", "ECA": "g2", "A": "g3"}

# activités de remédiation proposées par discipline (mots-clés sur le nom de la matière, sans accents)
ACTIVITES = [
    (("LECTURE", "LIRE"), "Lecture à haute voix guidée en petits groupes, syllabation, lecture répétée d'un même court texte, "
                          "questions de compréhension orales avant l'écrit."),
    (("DICTEE", "ORTHOGRAPHE"), "Dictées préparées courtes, étude de mots du texte, auto-correction avec un modèle, "
                                "banque de mots de la classe."),
    (("EXPRESSION", "REDACTION", "PRODUCTION", "COMMUNICATION ECRITE"), "Production guidée avec un canevas (qui, quoi, où, "
                                                                       "quand), phrases à compléter, relecture en binôme."),
    (("FRANCAIS", "LANGUE", "GRAMMAIRE", "CONJUGAISON", "VOCABULAIRE"), "Manipulation de phrases (étiquettes), exercices "
                                                                       "courts quotidiens, jeux de mots, rappel des règles avec exemples."),
    (("MATH", "CALCUL", "NUMERATION", "GEOMETRIE", "MESURE"), "Calcul mental quotidien (10 min), manipulation (bâtonnets, "
                                                               "monnaie, mesures), résolution de problèmes en étapes : lire, "
                                                               "représenter, calculer, vérifier."),
    (("SCIENCE", "EST", "TECHNOLOGIE"), "Observation et petites expériences, schémas légendés, questions guidées et "
                                        "vocabulaire scientifique illustré."),
    (("SOCIALE", "HISTOIRE", "GEOGRAPHIE", "CIVI", "MORALE", "ES "), "Cartes et images commentées, récits, jeux de rôle, "
                                                                     "questions guidées sur des situations de la vie courante."),
    (("EPS", "SPORT", "PHYSIQUE"), "Ateliers par niveau, gestes décomposés, démonstration par un camarade."),
    (("ART", "DESSIN", "CHANT", "MUSIQUE", "POESIE", "CONTE", "COUTURE"), "Pratique guidée par étapes, imitation d'un modèle, "
                                                                          "présentation au groupe."),
]
ACTIVITE_DEFAUT = "Reprise des notions non acquises en petit groupe, exercices courts et progressifs, évaluation rapide."


def sans_accents(t):
    return "".join(ch for ch in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(ch) != "Mn").upper()


def activites_pour(matiere):
    n = " " + sans_accents(matiere) + " "
    for cles, txt in ACTIVITES:
        if any(c in n for c in cles):
            return txt
    return ACTIVITE_DEFAUT


def groupe_de_note(v):
    if v is None:
        return None
    for cle, _lib, bas, haut, _c in GROUPES:
        if bas <= v < haut:
            return cle
    return "g4" if v >= 20 else "g1"


def groupes_remediation(matieres, lignes):
    """Groupes de besoin par matière. lignes : resultats() d'evaluations_core.
    Renvoie {"matieres": [{matiere, groupes: {g1..g4: [eleve…]}, absents, taux}], "non_maitrise": [...],
    "a_renforcer": [noms], "tuteurs": [...]}."""
    out = []
    for m in matieres:
        grp = {k: [] for k, *_ in GROUPES}
        absents = []
        for l in lignes:
            e = l["eleve"]
            if m["id"] in l["dispenses"]:
                continue
            if l["appreciations"]:
                k = APPRECIATION_GROUPE.get(l["appreciations"].get(m["id"]))
            else:
                k = groupe_de_note(l["notes"].get(m["id"]))
            (grp[k] if k else absents).append(e)
        evalues = sum(len(v) for v in grp.values())
        reussis = len(grp["g3"]) + len(grp["g4"])
        out.append({"matiere": m, "groupes": grp, "absents": absents, "evalues": evalues,
                    "taux": round(100.0 * reussis / evalues, 1) if evalues else None,
                    "besoin": len(grp["g1"]) + len(grp["g2"]), "activites": activites_pour(m["nom"])})
    non_maitrise = []
    for l in lignes:
        if l["compose"] and l["maitrise"] is False:
            faibles = [m["nom"] for m in matieres if (l["notes"].get(m["id"]) is not None and l["notes"][m["id"]] < 10)
                       or l["appreciations"].get(m["id"]) in ("NA", "ECA")]
            non_maitrise.append({"eleve": l["eleve"], "moyenne": l["moyenne"], "reussies": l["reussies"],
                                 "seuil": l["seuil"], "matieres": faibles})
    non_maitrise.sort(key=lambda x: (x["moyenne"] if x["moyenne"] is not None else 99, x["eleve"]["nom"]))
    a_renforcer = [d["matiere"]["nom"] for d in out if d["taux"] is not None and d["taux"] < 50]
    return {"matieres": out, "non_maitrise": non_maitrise, "a_renforcer": a_renforcer}


def enregistrer(app, H):
    import evaluations_core as E

    def nom_eleve(e):
        return f"{e['nom']} {e['prenoms'] or ''}".strip()

    # ------------------------------------------------------------------ sauvegardes
    def etat_sauvegarde():
        """{"date": datetime|None, "jours": int|None, "nom": str} de la sauvegarde la plus récente."""
        try:
            import m_en_ligne
            d = m_en_ligne.dossier_sauvegardes()
            fichiers = [f for f in os.listdir(d) if f.endswith(".zip")]
        except Exception:  # noqa: BLE001
            return {"date": None, "jours": None, "nom": ""}
        if not fichiers:
            return {"date": None, "jours": None, "nom": ""}
        f = max(fichiers, key=lambda x: os.path.getmtime(os.path.join(d, x)))
        dt = datetime.fromtimestamp(os.path.getmtime(os.path.join(d, f)))
        return {"date": dt, "jours": (date.today() - dt.date()).days, "nom": f}

    # ------------------------------------------------------------------ raccourcis de l'accueil
    def raccourcis():
        """Actions principales du rôle connecté (5 à 8 grandes tuiles)."""
        if not g.get("user"):
            return []
        r = g.user["role"]
        vf = app.view_functions
        out = []

        def ajout(ep, titre, d, ico, module=None, alerte=False, **args):
            if ep in vf and (module is None or H.peut(module)):
                out.append({"url": url_for(ep, **args), "titre": titre, "d": d, "ico": ico, "alerte": alerte})

        if config.juridiction() and r not in ("directeur", "enseignant"):
            if any(H.peut(m) for m in ("jur_ecoles", "jur_visites", "jur_cp_bilan", "jur_transmission")):
                ajout("jur_alertes", "Alertes de pilotage", "Ce qui demande une action", "alerte")
            ajout("jur_cp_accueil", "Conseillers pédagogiques", "Programmation et bilans", "enseignant", "jur_cp_bilan")
            ajout("jur_cp_bilan", "Bilan trimestriel", "Activités pédagogiques", "classeur", "jur_cp_bilan")
            ajout("jur_visites", "Visites", "Écoles et classes", "rechercher", "jur_visites")
            ajout("jur_transmissions", "Transmissions", "Recevoir les écoles", "⇅", "jur_transmission")
            ajout("jur_stats_ecoles", "Statistiques", "Écoles, effectifs, enseignants", "graphique", "jur_ecoles")
            if r != "observateur":
                ajout("listes_classe", "Listes de classe", "École, cours, classe", "liste")
        else:
            mes = H.classes_autorisees() if "ma_classe" in vf and r == "enseignant" else []
            if mes:
                ajout("ma_classe", "Ma classe" if len(mes) == 1 else "Mes classes",
                      mes[0]["nom"] if len(mes) == 1 else f"{len(mes)} classes", "ecole")
            ajout("listes_classe", "Listes de classe", "Par cours : PDF, Excel, impression", "liste")   # v2.3.3 : accès rapide
            ajout("appel_accueil", "Faire l'appel", "Présents, absents, retards", "valider", "appel")
            ajout("eval_accueil", "Saisir des notes", "Évaluations et bulletins", "note", "evaluations")
            if r != "enseignant":
                ajout("eleve_form", "Inscrire un élève", "Nouvelle inscription", "ajouter", "eleves")
            else:
                ajout("espace_enseignant", "Mon espace", "Fiches, documents, emploi du temps", "personne")
            if config.publique():
                ajout("cantine_accueil", "Cantine", "Paiements et effectifs", "cantine", "cantine")
            else:
                ajout("paiement_nouveau", "Encaisser", "Paiement de scolarité", "argent", "paiements")
                ajout("impayes", "Impayés", "Relances aux parents", "annonce", "paiements")
            ajout("communication", "Messages aux parents", "SMS / WhatsApp", "message", "communication")
            if not config.secondaire(): ajout("cep_accueil", "CEP", "Fiches d'inscription", "diplome", "cep")
            if r in ("admin", "fondateur", "directeur") and "en_ligne_page" in vf and H.peut("parametres"):
                s = etat_sauvegarde()
                if s["date"] is None:
                    ajout("en_ligne_page", "Sauvegardes", "Aucune sauvegarde : à faire", "enregistrer", alerte=True)
                else:
                    quand = "aujourd'hui" if s["jours"] == 0 else ("hier" if s["jours"] == 1 else f"il y a {s['jours']} jours")
                    ajout("en_ligne_page", "Sauvegardes", f"Dernière : {quand}", "enregistrer", alerte=s["jours"] > 2)
        return out[:9]   # v2.3.3 : 9 tuiles (listes de classe ajoutées)

    app.jinja_env.globals.update(raccourcis=raccourcis, etat_sauvegarde=etat_sauvegarde)
    H.etat_sauvegarde = etat_sauvegarde

    # ------------------------------------------------------------------ Ma classe
    def tableau_classe(cl):
        cid = cl["id"]
        auj = date.today()
        eleves = E.eleves_classe(cid)
        ids = [e["id"] for e in eleves]
        t = {"effectif": len(eleves), "filles": sum(1 for e in eleves if e["sexe"] == "F")}
        t["garcons"] = t["effectif"] - t["filles"]
        t["appel_fait"] = q("SELECT fait_le FROM appels WHERE classe_id=? AND date=?", (cid, auj.isoformat()), un=True)
        pres = []
        if ids:
            marque = ",".join("?" * len(ids))
            pres = q(f"SELECT * FROM presences WHERE eleve_id IN ({marque}) AND date>=?",
                     ids + [(auj - timedelta(days=30)).isoformat()])
        t["absents_jour"] = sum(1 for p in pres if p["date"] == auj.isoformat() and p["statut"] == "absent")
        t["retards_jour"] = sum(1 for p in pres if p["date"] == auj.isoformat() and p["statut"] == "retard")
        lundi = (auj - timedelta(days=auj.weekday())).isoformat()
        t["absences_semaine"] = sum(1 for p in pres if p["date"] >= lundi and p["statut"] == "absent")
        par_eleve = {}
        for p in pres:
            if p["statut"] == "absent" and not p["justifie"]:
                par_eleve[p["eleve_id"]] = par_eleve.get(p["eleve_id"], 0) + 1
        par_id = {e["id"]: e for e in eleves}
        suivre = {}
        for eid, n in par_eleve.items():
            if n >= 3 and eid in par_id:
                suivre.setdefault(eid, {"eleve": par_id[eid], "motifs": []})["motifs"].append(
                    f"{n} absence(s) non justifiée(s) en 30 jours")
        evs = E.evaluations_classe(cid)
        passees = [ev for ev in evs if not ev.get("date") or ev["date"] <= auj.isoformat()]
        t["prochaines"] = [ev for ev in evs if ev.get("date") and ev["date"] > auj.isoformat()][:3]
        t["derniere"] = None
        if passees:
            ev = passees[-1]
            mats, lignes = E.resultats(ev, cl, eleves)
            comp = [l for l in lignes if l["compose"]]
            reussis = sum(1 for l in comp if l["maitrise"])
            manquantes = sum(1 for l in lignes for m in mats
                             if l["notes"].get(m["id"]) is None and m["id"] not in l["dispenses"]
                             and m["id"] not in l["appreciations"])
            moys = [l["moyenne"] for l in comp if l["moyenne"] is not None]
            t["derniere"] = {"ev": ev, "composes": len(comp), "reussis": reussis,
                             "taux": round(100.0 * reussis / len(comp), 1) if comp else None,
                             "moyenne": round(sum(moys) / len(moys), 2) if moys else None, "manquantes": manquantes,
                             "a_renforcer": groupes_remediation(mats, lignes)["a_renforcer"]}
            for l in comp:
                if l["maitrise"] is False:
                    suivre.setdefault(l["eleve"]["id"], {"eleve": l["eleve"], "motifs": []})["motifs"].append(
                        f"non-maîtrise à « {ev['titre']} »" + (f" (moyenne {l['moyenne']:.2f})".replace(".", ",")
                                                               if l["moyenne"] is not None else ""))
        t["suivre"] = sorted(suivre.values(), key=lambda x: (-len(x["motifs"]), x["eleve"]["nom"]))
        return t

    @app.route("/ma-classe")
    @H.connexion_requise()
    def ma_classe():
        mes = H.classes_autorisees()
        if not mes:
            return render_template("ma_classe.html", cartes=[], cl=None)
        if len(mes) == 1:
            return redirect(url_for("ma_classe_detail", cid=mes[0]["id"]))
        cartes = [{"cl": c, "t": tableau_classe(c)} for c in mes]
        return render_template("ma_classe.html", cartes=cartes, cl=None, auj=date.today().isoformat())

    @app.route("/ma-classe/<int:cid>")
    @H.connexion_requise()
    def ma_classe_detail(cid):
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        mes = H.classes_autorisees()
        return render_template("ma_classe.html", cl=cl, t=tableau_classe(cl), autres=[c for c in mes if c["id"] != cid],
                               auj=date.today().isoformat(), nom_eleve=nom_eleve)

    # ------------------------------------------------------------------ remédiation
    def contexte_rem(ev_id):
        ev = E.evaluation(ev_id)
        if not ev:
            abort(404)
        H.verifier_classe(ev["classe_id"])
        cl = H.classe_ou_404(ev["classe_id"])
        mats, lignes = E.resultats(ev, cl)
        return ev, cl, groupes_remediation(mats, lignes), lignes

    @app.route("/evaluations/<int:ev_id>/remediation")
    @H.connexion_requise()
    def eval_remediation(ev_id):
        ev, cl, rem, lignes = contexte_rem(ev_id)
        return render_template("eval_remediation.html", ev=ev, cl=cl, rem=rem, GROUPES=GROUPES, nom_eleve=nom_eleve,
                               composes=sum(1 for l in lignes if l["compose"]))

    @app.route("/evaluations/<int:ev_id>/remediation.pdf")
    @H.connexion_requise()
    def eval_remediation_pdf(ev_id):
        ev, cl, rem, _ = contexte_rem(ev_id)
        libs = {k: lib for k, lib, *_ in GROUPES}
        lignes = []
        for d in rem["matieres"]:
            for k, lib, *_r in GROUPES:
                el = d["groupes"][k]
                if not el:
                    continue
                lignes.append([d["matiere"]["nom"], libs[k], len(el), ", ".join(nom_eleve(e) for e in el),
                               d["activites"] if k in ("g1", "g2") else next(c for kk, _l, _b, _h, c in GROUPES if kk == k)])
        avant = []
        if rem["a_renforcer"]:
            avant.append(H.pdfs.paragraphe("<b>Matières à renforcer en priorité (moins de 50 % de réussite) :</b> "
                                           + ", ".join(rem["a_renforcer"]), 9))
        apres = []
        if rem["non_maitrise"]:
            apres.append(H.pdfs.paragraphe("<b>Élèves en non-maîtrise :</b> " + " ; ".join(
                f"{nom_eleve(x['eleve'])} ({x['reussies']}/{x['seuil']} matière(s) réussie(s))" for x in rem["non_maitrise"]), 8.5))
        titre = f"GROUPES DE REMÉDIATION – {ev['titre'].upper()}"
        pdf = H.pdfs.document_tableau(titre, ["Matière", "Groupe", "Nb", "Élèves", "Activités proposées"], lignes,
                                      sous_titre=f"Classe : {cl['nom']} · année scolaire {ev['annee']}", paysage=True,
                                      largeurs=[30, 42, 10, 110, 88], taille=7.5, avant=avant or None, apres=apres or None,
                                      signatures=[("L'enseignant(e)", "", None, False)],
                                      cycle=E.cycle_du_niveau(cl["niveau"]) if hasattr(E, "cycle_du_niveau") else None)
        return H.pdf_reponse(pdf, f"remediation_{cl['nom']}_{ev['libelle']}.pdf".replace(" ", "_"))

    @app.route("/evaluations/<int:ev_id>/remediation.xlsx")
    @H.connexion_requise()
    def eval_remediation_xlsx(ev_id):
        ev, cl, rem, _ = contexte_rem(ev_id)
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Remediation"
        ws.append([f"Groupes de remédiation – {ev['titre']} – {cl['nom']} – {ev['annee']}"])
        ws["A1"].font = Font(bold=True, size=12)
        ws.append([])
        ws.append(["Matière", "Groupe", "Élève", "Note / appréciation", "Activités proposées"])
        for c in ws[3]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="E4ECF5")
        libs = {k: lib for k, lib, *_ in GROUPES}
        _, lignes = E.resultats(ev, cl)
        notes = {l["eleve"]["id"]: l for l in lignes}
        for d in rem["matieres"]:
            for k, *_r in GROUPES:
                for e in d["groupes"][k]:
                    l = notes.get(e["id"]) or {"notes": {}, "appreciations": {}}
                    val = l["notes"].get(d["matiere"]["id"])
                    if val is None:
                        val = l["appreciations"].get(d["matiere"]["id"], "")
                    ws.append([d["matiere"]["nom"], libs[k], nom_eleve(e), val,
                               d["activites"] if k in ("g1", "g2") else ""])
        for col, w in zip("ABCDE", (24, 36, 30, 18, 90)):
            ws.column_dimensions[col].width = w
        buf = io.BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="remediation_{ev_id}.xlsx"'})
