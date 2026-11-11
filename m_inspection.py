# -*- coding: utf-8 -*-
"""v1.27 — Inspection et formation (spécification commune PVS, lot C).

* Visites de classe avec grille APC (10 critères notés de 0 à 4 ; note /20 = moyenne × 5 ; appréciation), compte rendu
  signé (visiteur, enseignant visité, visa du directeur, QR) ; « Créer les recommandations » : une ligne de suivi par
  paragraphe des recommandations ;
* suivi des recommandations (effectifs par statut, recommandations échues non réalisées) ;
* plans de formation ; animations pédagogiques (UP, zone, journées pédagogiques…) avec liste de présence, compte rendu
  signé et attestations de participation (une par participant, QR).

Les visites détaillées des CP et des CCS (modules Visites) restent disponibles ; ce module porte la grille commune aux
applications (Excel identique).
"""
import math
from datetime import date

from flask import flash, g, redirect, render_template, request, url_for

import registres as R

COURS = ["Maternelle", "CI", "CP", "CE1", "CE2", "CM1", "CM2"]
CRITERES = [("c1", "Préparation et fiche pédagogique"), ("c2", "Situation de départ et motivation"), ("c3", "Clarté des consignes"),
            ("c4", "Démarche APC (travail individuel, en groupe, collectif)"), ("c5", "Exploitation des productions des apprenants"),
            ("c6", "Objectivation et retour réflexif"), ("c7", "Évaluation formative et remédiation"), ("c8", "Gestion du temps et de la classe"),
            ("c9", "Tenue des documents (cahier de préparation, registres)"), ("c10", "Climat de classe et inclusion")]
DISCIPLINES = ["Français", "Mathématiques", "Éducation scientifique et technologique", "Éducation sociale", "Éducation artistique",
               "Éducation physique et sportive", "Anglais", "Langue nationale", "Autre"]
STATUTS_REC = ["Non commencée", "En cours", "Réalisée", "Abandonnée"]


def note_grille(x):
    """Note /20 = moyenne des critères renseignés × 5 (arrondie au dixième) ; None si aucun critère."""
    v = []
    for k, _l in CRITERES:
        n = x.get(k)
        if n not in (None, ""):
            try:
                v.append(min(4.0, max(0.0, float(str(n).replace(",", ".")))))
            except ValueError:
                pass
    return round(sum(v) / len(v) * 5 + 1e-9, 1) if v else None


def appreciation(note):
    if note is None:
        return ""
    return "Très bien" if note >= 16 else "Bien" if note >= 14 else "Assez bien" if note >= 12 else "Passable" if note >= 10 else "Insuffisant"


def paragraphes(texte):
    out = []
    for p in (texte or "").replace("\r", "").split("\n"):
        p = p.strip().lstrip("-•*·").strip()
        if p:
            out.append(p)
    return out


def participants(texte):
    """« NOM Prénoms — école / fonction » -> [(nom, complément)]."""
    out = []
    for l in (texte or "").replace("\r", "").split("\n"):
        l = l.strip()
        if not l:
            continue
        for sep in (" — ", " – ", " - ", ";"):
            if sep in l:
                a, b = l.split(sep, 1)
                out.append((a.strip(), b.strip()))
                break
        else:
            out.append((l, ""))
    return out


def libelle_visite(x):
    return f"{x.get('enseignant') or ''} — {R.jjmmaaaa(x.get('date'))}".strip(" —")


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.DROITS["inspection_ped"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent", "enseignant"}
    R.types_documents({"reg_inspection_visites_cr": "Compte rendu de visite de classe",
                       "reg_inspection_animations_cr": "Compte rendu d'animation pédagogique et liste de présence",
                       "reg_inspection_animations_attestations": "Attestation de participation à une formation / animation",
                       "reg_inspection_recommandations": "Suivi des recommandations", "reg_inspection_plans": "Plans de formation"})
    G = R.Groupe(app, H, "inspection", "Inspection et formation", "inspection_ped", ico="inspection",
                 sous_titre="Visites de classe (grille APC), comptes rendus signés, suivi des recommandations, plans de formation, "
                            "animations pédagogiques avec présences et attestations",
                 listes={"cours": COURS, "sexe": ["M", "F"], "disciplines": DISCIPLINES, "statuts_rec": STATUTS_REC,
                         "qualites": ["Directeur / Directrice", "Conseiller pédagogique", "Chef de circonscription", "Inspecteur", "Autre"],
                         "types_visite": ["Visite de classe", "Visite conseil", "Inspection", "Contre-visite"],
                         "publics": ["Directeurs", "Enseignants", "Enseignants du CI / CP", "Enseignants du CE", "Enseignants du CM",
                                     "Éducatrices / éducateurs (maternelle)", "Conseillers pédagogiques", "Tous"],
                         "modalites": ["Présentiel", "À distance", "Mixte"], "statuts_plan": ["Prévue", "En cours", "Réalisée", "Reportée", "Annulée"],
                         "types_anim": ["Animation pédagogique d’UP", "Animation de zone", "Journée pédagogique", "Formation", "Atelier",
                                        "Conférence pédagogique"], "notes04": ["0", "1", "2", "3", "4"]})

    def calc_visite(x):
        n = note_grille(x)
        return {"Note (/20)": "" if n is None else n, "Appréciation": appreciation(n)}

    def doc_cr_visite(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        n = note_grille(x)
        ent = [["Enseignant(e)", f"{x.get('enseignant') or ''}{' (' + x['sexeEns'] + ')' if x.get('sexeEns') else ''}"], ["École", x.get("entite") or ""],
               ["Cours", x.get("cours") or ""], ["Date", R.jjmmaaaa(x.get("date"))],
               ["Visiteur", f"{x.get('visiteur') or ''}{', ' + x['qualiteVisiteur'] if x.get('qualiteVisiteur') else ''}"],
               ["Type de visite", x.get("typeVisite") or ""], ["Discipline", x.get("discipline") or ""], ["Séance / SA", x.get("seance") or ""]]
        corps = [R.tableau(["Rubrique", "Renseignement"], [r for r in ent if r[1]], [1, 3], R.largeur_utile(False)), Spacer(1, 8),
                 Paragraph("Grille d'observation APC", st["h2"]),
                 R.tableau(["N°", "Critère", "Note (/4)"], [[i, l, "" if x.get(k) in (None, "") else x.get(k)] for i, (k, l) in enumerate(CRITERES, 1)],
                           [0.4, 4, 1], R.largeur_utile(False), total=["", "Note sur 20 — appréciation", f"{'' if n is None else n} — {appreciation(n)}"])]
        for k, t in (("pointsForts", "Points forts"), ("insuffisances", "Insuffisances"), ("recommandations", "Recommandations")):
            if (x.get(k) or "").strip():
                corps += [Paragraph(t, st["h2"])] + [Paragraph("– " + R.esc(p), st["p"]) for p in paragraphes(x[k])]
        sigs = [R.signature_vide("Le visiteur", x.get("visiteur") or ""), R.signature_vide("L'enseignant(e) visité(e)", x.get("enseignant") or ""),
                R.signature_autorite("Visa du Directeur / de la Directrice")]
        return "Compte rendu de visite de classe", corps, sigs

    def actions_visite(x):
        return [("post:" + url_for("inspection_creer_recommandations", vid=x["id"]), "Créer les recommandations", "ajouter")] if (x.get("recommandations") or "").strip() else []

    G.registre("visites", "Visites de classe (grille APC)", [
        ("enseignant", "Enseignant(e)", "texte"), ("sexeEns", "Sexe de l’enseignant(e)", "choix:sexe"), ("cours", "Cours", "choix:cours"),
        ("date", "Date de la visite", "date"), ("visiteur", "Visiteur", "texte"), ("qualiteVisiteur", "Qualité du visiteur", "choix:qualites"),
        ("typeVisite", "Type de visite", "choix:types_visite"), ("discipline", "Discipline", "choix:disciplines"),
        ("seance", "Séance / situation d’apprentissage", "texte")] + [(k, l, "decimal") for k, l in CRITERES] + [
        ("pointsForts", "Points forts", "long"), ("insuffisances", "Insuffisances", "long"), ("recommandations", "Recommandations", "long")],
        unite="visite", oblig="enseignant", ordre="date DESC, enseignant", portee="ecole", feuille="Visites de classe (grille APC)",
        onglet="Visites de classe", entite=True, niveaux=["ECOLE"], unique=("enseignant", "date"), calcul=calc_visite,
        colonnes=("enseignant", "cours", "date", "visiteur", "qualiteVisiteur", "typeVisite", "discipline"), filtres=("cours", "discipline"),
        fiches={"cr": ("Compte rendu de visite", "document", doc_cr_visite)}, actions=actions_visite,
        defauts=lambda: {"niveau": "ECOLE", "entite": R.entite_courante()[1], "date": date.today().isoformat(),
                         "qualiteVisiteur": "Conseiller pédagogique", "typeVisite": "Visite de classe"},
        doc="Visites de classe (grille APC)",
        aide="Critères notés de 0 à 4 ; note sur 20 = moyenne des critères renseignés × 5 ; appréciation : ≥ 16 Très bien, ≥ 14 Bien, "
             "≥ 12 Assez bien, ≥ 10 Passable, sinon Insuffisant.")
    G.registre("recommandations", "Suivi des recommandations", [
        ("visite", "Visite de classe", "texte"), ("destinataire", "Destinataire", "texte"), ("recommandation", "Recommandation", "long"),
        ("echeance", "Échéance", "date"), ("responsable", "Responsable du suivi", "texte"), ("statut", "Statut", "choix:statuts_rec"),
        ("dateVerification", "Date de vérification", "date"), ("observations", "Observations", "long")],
        unite="recommandation", oblig="recommandation", ordre="echeance, id", portee="structure", feuille="Suivi des recommandations",
        onglet="Recommandations", entite=True, unique=("recommandation", "destinataire"), filtres=("statut",),
        colonnes=("niveau", "entite", "visite", "destinataire", "recommandation", "echeance", "responsable", "statut", "dateVerification"),
        calcul=lambda x: {"Échue": "Oui" if (x.get("echeance") and x["echeance"] < date.today().isoformat()
                                              and x.get("statut") not in ("Réalisée", "Abandonnée")) else ""},
        defauts=lambda: dict(zip(("niveau", "entite"), R.entite_courante()), statut="Non commencée"), doc="Suivi des recommandations")
    G.registre("plans", "Plans de formation", [
        ("theme", "Thème", "texte"), ("publicCible", "Public cible", "choix:publics"), ("objectifs", "Objectifs", "long"),
        ("dateDebut", "Date de début", "date"), ("dateFin", "Date de fin", "date"), ("formateur", "Formateur(s)", "texte"), ("lieu", "Lieu", "texte"),
        ("modalite", "Modalité", "choix:modalites"), ("participantsPrevus", "Participants prévus", "entier"), ("cout", "Coût prévu (FCFA)", "montant"),
        ("financement", "Financement", "texte"), ("statut", "Statut", "choix:statuts_plan")],
        unite="formation", oblig="theme", ordre="dateDebut, theme", portee="structure", feuille="Plans de formation", entite=True,
        unique=("theme", "dateDebut"), filtres=("statut", "publicCible"), totaux=("participantsPrevus", "cout"),
        defauts=lambda: dict(zip(("niveau", "entite"), R.entite_courante()), publicCible="Enseignants", modalite="Présentiel", statut="Prévue"),
        doc="Plan de formation")

    def doc_cr_animation(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        ent = [["Type", x.get("type") or ""], ["Date", R.jjmmaaaa(x.get("date"))], ["Thème", x.get("theme") or ""],
               ["Animateur / animatrice", x.get("animateur") or ""], ["Lieu", x.get("lieu") or ""],
               ["Présents", f"{(x.get('presentsH') or 0) + (x.get('presentsF') or 0)} (hommes : {x.get('presentsH') or 0}, femmes : {x.get('presentsF') or 0})"]]
        corps = [R.tableau(["Rubrique", "Renseignement"], [r for r in ent if r[1]], [1, 3], R.largeur_utile(False))]
        if (x.get("compteRendu") or "").strip():
            corps += [Paragraph("Compte rendu", st["h2"])] + [Paragraph(R.esc(p), st["p"]) for p in paragraphes(x["compteRendu"])]
        pl = participants(x.get("participants"))
        if pl:
            corps += [Spacer(1, 6), Paragraph("Liste de présence", st["h2"]),
                      R.tableau(["N°", "Nom et prénoms", "École / fonction", "Émargement"], [[i, a, b, ""] for i, (a, b) in enumerate(pl, 1)],
                                [0.4, 2.2, 2.2, 1.4], R.largeur_utile(False))]
        return "Compte rendu d'animation pédagogique et liste de présence", corps, [R.signature_vide("L'animateur / l'animatrice", x.get("animateur") or ""),
                                                                                     R.signature_autorite()]

    def doc_attestations(x):
        from reportlab.platypus import PageBreak, Paragraph, Spacer
        st = R.styles()
        pl = participants(x.get("participants")) or [("……………………………", "")]
        corps = []
        for i, (nom, compl) in enumerate(pl):
            if i:
                corps.append(PageBreak())
            corps += [Spacer(1, 30), Paragraph("ATTESTATION DE PARTICIPATION", st["t"]), Spacer(1, 18),
                      Paragraph(f"Il est attesté que <b>{R.esc(nom)}</b>{' (' + R.esc(compl) + ')' if compl else ''} a participé à "
                                f"l'activité « {R.esc(x.get('type') or 'animation pédagogique')} » sur le thème <b>« {R.esc(x.get('theme') or '')} »</b>, "
                                f"organisée le {R.jjmmaaaa(x.get('date'))}{' à ' + R.esc(x['lieu']) if x.get('lieu') else ''}"
                                f"{', animée par ' + R.esc(x['animateur']) if x.get('animateur') else ''}.", st["p"]), Spacer(1, 8),
                      Paragraph("En foi de quoi la présente attestation lui est délivrée pour servir et valoir ce que de droit.", st["p"])]
        return "Attestations de participation", corps, [R.signature_autorite()]

    G.registre("animations", "Animations pédagogiques", [
        ("type", "Type", "choix:types_anim"), ("date", "Date", "date"), ("theme", "Thème", "texte"), ("animateur", "Animateur / animatrice", "texte"),
        ("lieu", "Lieu", "texte"), ("presentsH", "Présents (hommes)", "entier"), ("presentsF", "Présentes (femmes)", "entier"),
        ("participants", "Liste des participants", "long"), ("compteRendu", "Compte rendu", "long")],
        unite="animation", oblig="theme", ordre="date DESC", portee="structure", feuille="Animations pédagogiques", entite=True,
        unique=("date", "theme"), filtres=("type",), totaux=("presentsH", "presentsF"),
        calcul=lambda x: {"Total présents": (x.get("presentsH") or 0) + (x.get("presentsF") or 0)},
        fiches={"cr": ("Compte rendu et liste de présence", "document", doc_cr_animation),
                "attestations": ("Attestations de participation", "attestation", doc_attestations)},
        defauts=lambda: dict(zip(("niveau", "entite"), R.entite_courante()), type="Animation pédagogique d’UP", date=date.today().isoformat()),
        doc="Animations pédagogiques",
        aide="Liste des participants : une personne par ligne, « NOM Prénoms — école / fonction » (une attestation par ligne).")
    G.page("inspection_suivi", "Bilan du suivi", apres=True)

    @app.route("/inspection/visite/<int:vid>/recommandations", methods=["POST"])
    @H.connexion_requise("inspection_ped")
    def inspection_creer_recommandations(vid):
        rv = G.registres["visites"]
        if not G.peut_ecrire(rv):
            flash("Écriture réservée.", "warning")
            return redirect(url_for("reg_page", gcle="inspection", rcle="visites"))
        x = G.ligne(rv, vid)
        lib = libelle_visite(x)
        n = 0
        for p in paragraphes(x.get("recommandations")):
            if q("SELECT 1 FROM reg_inspection_recommandations WHERE portee=? AND recommandation=? AND destinataire=?",
                 (R.cle_portee("structure"), p, x.get("enseignant") or ""), un=True):
                continue
            ex("INSERT INTO reg_inspection_recommandations (portee, annee, niveau, entite, visite, destinataire, recommandation, responsable, statut, "
               "cree_le, cree_par, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (R.cle_portee("structure"), x.get("annee") or R.annee_active(), "ECOLE", x.get("entite") or R.entite_courante()[1], lib,
                x.get("enseignant") or "", p, x.get("visiteur") or "", "Non commencée", H.maintenant(), g.user["id"],
                H.maintenant()))
            n += 1
        flash(f"{n} recommandation(s) ajoutée(s) au suivi.", "success" if n else "warning")
        return redirect(url_for("reg_page", gcle="inspection", rcle="recommandations", annee=x.get("annee")))

    def suivi(annee):
        rows = [dict(x) for x in q("SELECT * FROM reg_inspection_recommandations WHERE portee=? AND annee=?", (R.cle_portee("structure"), annee))]
        par = {s: 0 for s in STATUTS_REC}
        for x in rows:
            par[x.get("statut") or "Non commencée"] = par.get(x.get("statut") or "Non commencée", 0) + 1
        auj = date.today().isoformat()
        echues = [x for x in rows if x.get("echeance") and x["echeance"] < auj and x.get("statut") not in ("Réalisée", "Abandonnée")]
        vis = [dict(x) for x in q("SELECT * FROM reg_inspection_visites WHERE portee=? AND annee=?", (R.cle_portee("ecole"), annee))] \
            if not (R.juridiction() and not g.get("ecole")) else []
        notes = [n for n in (note_grille(v) for v in vis) if n is not None]
        return {"total": len(rows), "par": par, "echues": echues, "visites": len(vis),
                "moyenne": round(sum(notes) / len(notes), 1) if notes else None,
                "taux": round(100 * par.get("Réalisée", 0) / len(rows)) if rows else None}

    @app.route("/inspection/suivi")
    @H.connexion_requise("inspection_ped")
    def inspection_suivi():
        annee = (request.args.get("annee") or "").strip() or R.annee_active()
        return render_template("inspection_suivi.html", G=G, ep_actif="inspection_suivi", s=suivi(annee), annee=annee, jj=R.jjmmaaaa,
                               appreciation=appreciation)
    _ = math
