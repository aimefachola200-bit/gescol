# -*- coding: utf-8 -*-
"""v2.4 — Établissement secondaire (collège, lycée, enseignement technique et professionnel), public et privé.

GESCOL gérait déjà les classes du secondaire (6ème → Tle : moyenne pondérée, bulletins, en-tête MESTFP). Ce module ajoute
tout le reste de la vie d'un collège ou d'un lycée, avec le moteur commun des registres (registres.py : Excel, modèle,
import, PDF signé avec QR, filtres) — mêmes écrans, mêmes exports que santé, inspection et examens :

* Vie de l'établissement : programme (matières, coefficients et volumes horaires par niveau et par série, avec gabarit à
  ajuster), professeurs (statut public / privé), conseils de classe (calcul des moyennes depuis les notes, procès-verbal
  signé), discipline et sanctions (fiche signée), emplois du temps (conflits de professeur, de salle et de classe, grille) ;
* Examens BEPC / BAC / CAP / BT : centres, candidats, numéros de table, moyennes, mention et décision proposées, décision du
  jury, statistiques (par série, par sexe, par centre), convocation signée ;
* Pilotage et structures : identité de l'établissement (proviseur, censeur, surveillant général, intendant…), tableau
  synoptique chiffré (effectifs par niveau et sexe, classes, professeurs, ratios), PDF et Excel pour la direction
  départementale (DDESTFP) ;
* Enseignement technique et professionnel : filières, ateliers et équipements, stages (attestation de stage signée).

Adresses : /secondaire/… (pages propres) et /reg/sec/… (registres). Aucun fichier existant n'est réécrit : le module
s'ajoute à la liste MODULES d'app.py et au menu (templates/base.html).

Règles de calcul reprises du noyau : secondaire = Σ(note × coefficient) / Σ(coefficient), sans coefficient en 6ème et 5ème
(calcul.NIVEAUX_SANS_COEF) ; admis si moyenne ≥ 10. Mentions : Passable ≥ 10, Assez bien ≥ 12, Bien ≥ 14, Très bien ≥ 16.
Décision d'examen proposée (à confirmer par le jury) : ≥ 10 admis ; au BAC, de 8 à moins de 10 : second tour ; sinon ajourné.
"""
import re
from datetime import date

from flask import flash, g, redirect, render_template, request, url_for

import registres as R
from calcul import NIVEAUX_SANS_COEF, NIVEAUX_SECONDAIRE

SERIES = ["Tronc commun", "A1", "A2", "B", "C", "D", "E", "F1", "F2", "F3", "F4", "G1", "G2", "G3", "H", "Agriculture", "Autre"]
CYCLES = {"6ème": "1er cycle", "5ème": "1er cycle", "4ème": "1er cycle", "3ème": "1er cycle",
          "2nde": "2nd cycle", "1ère": "2nd cycle", "Tle": "2nd cycle"}
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
EXAMENS = ["BEPC", "BAC général", "BAC technique", "CAP", "BT", "DT", "Autre"]
DECISIONS = ["Admis", "Second tour", "Ajourné", "Absent", "Éliminé (fraude)"]
STATUTS_PROF = ["Agent permanent de l'État (APE)", "Agent contractuel de l'État (ACE)", "Vacataire", "Enseignant de l'établissement (privé)", "Autre"]
NATURES = ["Retard", "Absence non justifiée", "Tenue non conforme", "Insolence / indiscipline", "Bavardage / perturbation", "Téléphone en classe",
           "Fraude / tricherie", "Bagarre / violence", "Dégradation de matériel", "Vol", "Autre"]
SANCTIONS = ["Avertissement", "Blâme", "Retenue / travail d'intérêt général", "Exclusion temporaire", "Exclusion définitive", "Conseil de discipline"]
STATUTS_ETABLISSEMENT = ["Public (collège d'enseignement général)", "Public (lycée)", "Public (lycée technique)", "Privé laïc", "Privé confessionnel",
                         "Privé (enseignement technique et professionnel)"]
DOMAINES = ["Industriel (mécanique, électricité, froid…)", "Bâtiment et travaux publics", "Tertiaire (gestion, commerce, secrétariat)",
            "Informatique et numérique", "Agriculture et élevage", "Hôtellerie, restauration et tourisme", "Santé et action sociale",
            "Couture, mode et artisanat", "Autre"]
DIPLOMES_ETP = ["CAP", "BEP", "BT", "DT", "Baccalauréat technique", "Certificat de qualification", "Autre"]
CYCLE_ENT = ["1er cycle", "2nd cycle", "1er et 2nd cycles"]
SEUIL_ADMIS, SEUIL_SECOND_TOUR = 10.0, 8.0


# ------------------------------------------------------------------ calculs purs (testés sans application)
def nombre(v):
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except ValueError:
        return None


def serie_de_classe(nom, niveau=None):
    """« 2nde C » → « C » ; « Tle A1 » → « A1 » ; « 1ère G2 » → « G2 ». Au 1er cycle (6ème → 3ème) la lettre est une section, pas une série :
    « Tronc commun ». Sinon : dernier mot de la forme lettre A-H (+ chiffre éventuel)."""
    if niveau and CYCLES.get(niveau) == "1er cycle":
        return "Tronc commun"
    for mot in reversed(re.split(r"[\s\-_/]+", (nom or "").strip())):
        if re.fullmatch(r"[A-Ha-h][1-4]?", mot):
            return mot.upper()
    return "Tronc commun"


def mention(moyenne):
    m = nombre(moyenne)
    if m is None:
        return ""
    return "Très bien" if m >= 16 else "Bien" if m >= 14 else "Assez bien" if m >= 12 else "Passable" if m >= 10 else ""


def decision_proposee(examen, moyenne, absent=False):
    """Décision proposée au jury (à confirmer) : voir l'en-tête du module."""
    if (absent or "") in (True, "Oui", 1, "1"):
        return "Absent"
    m = nombre(moyenne)
    if m is None:
        return ""
    if m >= SEUIL_ADMIS:
        return "Admis"
    if (examen or "").startswith("BAC") and m >= SEUIL_SECOND_TOUR:
        return "Second tour"
    return "Ajourné"


def decision_retenue(x):
    """Décision du jury si saisie, sinon décision proposée."""
    return (x.get("decisionJury") or "").strip() or decision_proposee(x.get("examen"), x.get("moyenne"), x.get("absent"))


def stats_candidats(lignes):
    """[{examen, serie, G/F: inscrits, presents, admis, second_tour}] regroupé ; + totaux. Les « absents » ne comptent pas parmi les présents."""
    def vide():
        return {"inscrits": {"M": 0, "F": 0}, "presents": {"M": 0, "F": 0}, "admis": {"M": 0, "F": 0}, "second": {"M": 0, "F": 0}}

    def compter(cible, x):
        s = x.get("sexe") if x.get("sexe") in ("M", "F") else "M"
        d = decision_retenue(x)
        cible["inscrits"][s] += 1
        if d not in ("Absent", "Éliminé (fraude)", ""):
            cible["presents"][s] += 1
        if d == "Admis":
            cible["admis"][s] += 1
        if d == "Second tour":
            cible["second"][s] += 1
    groupes, total = {}, vide()
    for x in lignes:
        k = (x.get("examen") or "", x.get("serie") or "")
        compter(groupes.setdefault(k, vide()), x)
        compter(total, x)
    return groupes, total


def taux(a, b):
    return round(100.0 * a / b, 1) if b else None


def resume_stats(c):
    ins, pre, adm = sum(c["inscrits"].values()), sum(c["presents"].values()), sum(c["admis"].values())
    return {"inscrits": ins, "inscrits_g": c["inscrits"]["M"], "inscrits_f": c["inscrits"]["F"], "presents": pre, "admis": adm,
            "admis_g": c["admis"]["M"], "admis_f": c["admis"]["F"], "second": sum(c["second"].values()),
            "taux": taux(adm, pre), "taux_g": taux(c["admis"]["M"], c["presents"]["M"]), "taux_f": taux(c["admis"]["F"], c["presents"]["F"])}


def minutes(h):
    m = re.fullmatch(r"\s*(\d{1,2})\s*[h:]\s*(\d{0,2})\s*", str(h or ""))
    return int(m.group(1)) * 60 + int(m.group(2) or 0) if m else None


def conflits_emploi(lignes):
    """Créneaux qui se chevauchent le même jour pour le même professeur, la même salle ou la même classe.
    -> {id: [motifs]} (chaque ligne en conflit reçoit le motif)."""
    out = {}
    par_jour = {}
    for x in lignes:
        a, b = minutes(x.get("debut")), minutes(x.get("fin"))
        if a is None or b is None or b <= a:
            continue
        par_jour.setdefault(x.get("jour") or "", []).append((a, b, x))
    for _j, L in par_jour.items():
        for i in range(len(L)):
            for k in range(i + 1, len(L)):
                (a1, b1, x1), (a2, b2, x2) = L[i], L[k]
                if a1 < b2 and a2 < b1:
                    for champ, lib in (("professeur", "professeur"), ("salle", "salle"), ("classe", "classe")):
                        v1, v2 = (x1.get(champ) or "").strip().lower(), (x2.get(champ) or "").strip().lower()
                        if v1 and v1 == v2:
                            for x in (x1, x2):
                                motif = f"même {lib} : {x1.get(champ)}"
                                if motif not in out.setdefault(x["id"], []):
                                    out[x["id"]].append(motif)
    return out


def moyenne_eleve(notes, niveau):
    """[(note, coefficient)] -> moyenne /20 ; coefficients ignorés en 6ème et 5ème (règle du noyau)."""
    coef_actifs = niveau not in NIVEAUX_SANS_COEF
    pts = tot = 0.0
    for n, c in notes:
        if n is None:
            continue
        c = (c or 1.0) if coef_actifs else 1.0
        pts += n * c
        tot += c
    return round(pts / tot, 2) if tot else None


def stats_moyennes(moyennes):
    v = [m for m in moyennes if m is not None]
    if not v:
        return {"composes": 0}
    return {"composes": len(v), "moyenne": round(sum(v) / len(v), 2), "max": max(v), "min": min(v),
            "sup10": sum(1 for m in v if m >= 10), "taux": taux(sum(1 for m in v if m >= 10), len(v))}


# ------------------------------------------------------------------ gabarit du programme
def gabarit(matieres, coefs):
    """Lignes (niveau, série, matière, coefficient, heures) d'un programme type, à ajuster selon le programme officiel.
    matieres : liste des noms ; coefs : {nom: coefficient par défaut de la table des matières}.
    6ème-5ème : sans langue vivante 2 ni philosophie ; 4ème-3ème : + espagnol / allemand ; 2nde-Tle : séries A1, A2, B, C, D."""
    def retenir(niveau):
        out = []
        for nm in matieres:
            bas = nm.lower()
            if ("espagnol" in bas or "allemand" in bas) and niveau in ("6ème", "5ème"):
                continue
            if "philosophie" in bas and niveau not in ("1ère", "Tle"):
                continue
            out.append(nm)
        return out
    lignes = []
    for niveau in NIVEAUX_SECONDAIRE:
        series = ["Tronc commun"] if CYCLES[niveau] == "1er cycle" else ["A1", "A2", "B", "C", "D"]
        for s in series:
            for nm in retenir(niveau):
                lignes.append((niveau, s, nm, coefs.get(nm, 1), 0))
    return lignes


# ------------------------------------------------------------------ enregistrement
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.DROITS["secondaire"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent"}
    R.types_documents({"reg_sec_conseils_pv": "Procès-verbal du conseil de classe", "reg_sec_sanctions_fiche": "Fiche de sanction disciplinaire",
                       "reg_sec_candidats_convocation": "Convocation à un examen", "reg_sec_stages_attestation": "Attestation de stage",
                       "sec_synoptique": "Tableau synoptique de l'établissement secondaire",
                       "sec_examens_stats": "Statistiques des examens (établissement secondaire)"})

    def classes_sec():
        try:
            return [r["nom"] for r in q("SELECT nom FROM classes WHERE ecole_id=? AND niveau IN (%s) ORDER BY niveau, nom"
                                        % ",".join("?" * len(NIVEAUX_SECONDAIRE)), (H.eco(),) + tuple(NIVEAUX_SECONDAIRE))]
        except Exception:  # noqa: BLE001
            return []

    def matieres_sec():
        try:
            return [r["nom"] for r in q("SELECT nom FROM matieres WHERE cycle='secondaire' AND actif=1 ORDER BY ordre, nom")]
        except Exception:  # noqa: BLE001
            return []

    def centres():
        try:
            return [x["nom"] for x in q("SELECT nom FROM reg_sec_centres WHERE portee=? ORDER BY nom", (R.cle_portee("ecole"),))]
        except Exception:  # noqa: BLE001
            return []

    def filieres():
        try:
            return [x["intitule"] for x in q("SELECT intitule FROM reg_sec_filieres WHERE portee=? ORDER BY intitule", (R.cle_portee("ecole"),))]
        except Exception:  # noqa: BLE001
            return []

    LISTES = {"niveaux_sec": NIVEAUX_SECONDAIRE, "series": SERIES, "matieres_sec": matieres_sec, "classes_sec": classes_sec,
              "jours": JOURS, "examens": EXAMENS, "decisions": DECISIONS, "statuts_prof": STATUTS_PROF, "natures": NATURES,
              "sanctions": SANCTIONS, "centres": centres, "filieres": filieres, "periodes": lambda: list(H.config.PERIODES),
              "statuts_etab": STATUTS_ETABLISSEMENT, "domaines": DOMAINES, "diplomes_etp": DIPLOMES_ETP, "cycles_ent": CYCLE_ENT,
              "etat": ["Bon", "Moyen", "À réparer", "Hors service"], "sexe": ["M", "F"]}
    G = R.Groupe(app, H, "sec", "Établissement secondaire", "secondaire", ico="ecole",
                 ecriture_roles={"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service"},
                 sous_titre="Programme et coefficients, professeurs, conseils de classe, discipline, emplois du temps, examens BEPC / BAC, "
                            "tableau synoptique, enseignement technique et professionnel",
                 listes=LISTES)

    def ent_ecole():
        return {"niveau": "ECOLE", "entite": R.entite_courante()[1]}

    def sig_directeur(titre_visa="Le Proviseur / Le Directeur"):
        return R.signature_autorite(titre_visa)

    # ================================================================== vie de l'établissement
    G.registre("programme", "Programme et coefficients", [
        ("niveauClasse", "Niveau", "choix:niveaux_sec"), ("serie", "Série", "liste:series"), ("matiere", "Matière", "liste:matieres_sec"),
        ("coefficient", "Coefficient", "decimal"), ("heures", "Heures par semaine", "decimal"), ("optionnelle", "Matière optionnelle", "oui_non"),
        ("observations", "Observations", "long")], unite="matière", oblig="matiere", ordre="niveauClasse, serie, matiere", portee="ecole",
        feuille="Programme", entite=True, niveaux=["ECOLE"], unique=("niveauClasse", "serie", "matiere"), filtres=("niveauClasse", "serie"),
        calcul=lambda x: {"Coef. appliqué": ("sans coefficient" if x.get("niveauClasse") in NIVEAUX_SANS_COEF else x.get("coefficient") or "")},
        colonnes=("niveauClasse", "serie", "matiere", "coefficient", "heures", "optionnelle"),
        defauts=lambda: dict(ent_ecole(), serie="Tronc commun", optionnelle="Non"), doc="Programme, coefficients et volumes horaires",
        aide="« Charger le gabarit » propose les matières de chaque niveau et série avec les coefficients de la table des matières : "
             "à ajuster selon le programme officiel. Les coefficients ne s'appliquent pas en 6ème et 5ème.")

    G.registre("professeurs", "Professeurs", [
        ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"), ("sexe", "Sexe", "choix:sexe"), ("matricule", "Matricule / NIP", "texte"),
        ("statut", "Statut", "choix:statuts_prof"), ("discipline", "Discipline enseignée", "liste:matieres_sec"), ("diplome", "Diplôme professionnel", "texte"),
        ("classes", "Classes tenues", "long"), ("heures", "Heures par semaine", "decimal"), ("telephone", "Téléphone", "texte"),
        ("observations", "Observations", "long")], unite="professeur", oblig="nom", ordre="nom, prenoms", portee="ecole", feuille="Professeurs",
        entite=True, niveaux=["ECOLE"], unique=("nom", "prenoms", "discipline"), filtres=("statut", "discipline"), totaux=("heures",),
        colonnes=("nom", "prenoms", "sexe", "matricule", "statut", "discipline", "heures", "telephone"),
        defauts=lambda: dict(ent_ecole(), statut=STATUTS_PROF[0]), doc="Liste nominative des professeurs",
        aide="Dans un établissement public : APE / ACE. Dans le privé : « Enseignant de l'établissement ». Les carrières détaillées restent dans Personnel et carrière.")

    def doc_conseil(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        r = G.registres["conseils"]
        entete = (f"Le conseil de la classe de <b>{R.esc(x.get('classe') or '')}</b> s'est réuni le {R.jjmmaaaa(x.get('dateConseil'))} "
                  f"({R.esc(x.get('periode') or '')}), sous la présidence de {R.esc(x.get('president') or '………')}.")
        lignes = [[l, G.valeur_affichee(r, x, k)] for k, l, _t in r.champs
                  if k not in ("niveau", "entite", "classe", "dateConseil", "periode", "president", "observations") and x.get(k) not in (None, "")]
        corps = [Paragraph(entete, st["p"]), Spacer(1, 4), R.tableau(["Rubrique", "Valeur"], lignes, [2.2, 1], R.largeur_utile(False))]
        if (x.get("observations") or "").strip():
            corps += [Spacer(1, 5), Paragraph("<b>Observations et décisions :</b> " + R.esc(x["observations"]), st["p"])]
        return "Procès-verbal du conseil de classe", corps, [R.signature_vide("Le / la président(e) du conseil", x.get("president") or ""),
                                                             R.signature_vide("Le professeur principal"), sig_directeur()]

    G.registre("conseils", "Conseils de classe", [
        ("classe", "Classe", "choix:classes_sec"), ("periode", "Période", "choix:periodes"), ("dateConseil", "Date du conseil", "date"),
        ("president", "Président(e)", "texte"), ("professeurPrincipal", "Professeur principal", "texte"), ("effectif", "Effectif", "entier"),
        ("composes", "Élèves ayant composé", "entier"), ("moyenneClasse", "Moyenne de la classe", "decimal"), ("moyenneMax", "Moyenne la plus forte", "decimal"),
        ("moyenneMin", "Moyenne la plus faible", "decimal"), ("sup10", "Moyennes ≥ 10", "entier"), ("honneur", "Tableau d'honneur", "entier"),
        ("felicitations", "Félicitations", "entier"), ("encouragements", "Encouragements", "entier"), ("avertTravail", "Avertissements (travail)", "entier"),
        ("blameTravail", "Blâmes (travail)", "entier"), ("avertConduite", "Avertissements (conduite)", "entier"), ("blameConduite", "Blâmes (conduite)", "entier"),
        ("passage", "Passages / admis", "entier"), ("redoublement", "Redoublements", "entier"), ("exclusions", "Exclusions", "entier"),
        ("observations", "Observations et décisions", "long")], unite="conseil", oblig="classe", ordre="dateConseil DESC, classe", portee="ecole",
        feuille="Conseils de classe", entite=True, niveaux=["ECOLE"], unique=("classe", "periode"), filtres=("classe", "periode"),
        calcul=lambda x: {"Taux ≥ 10 (%)": taux(x.get("sup10") or 0, x.get("composes")) if x.get("composes") else ""},
        colonnes=("classe", "periode", "dateConseil", "effectif", "composes", "moyenneClasse", "sup10", "passage", "redoublement"),
        fiches={"pv": ("Procès-verbal", "valider-cercle", doc_conseil)},
        defauts=lambda: dict(ent_ecole(), dateConseil=date.today().isoformat()), doc="Registre des conseils de classe",
        aide="« Calculer depuis les notes » crée la ligne d'une classe et d'une période avec les moyennes déjà saisies ; "
             "complétez ensuite les décisions du conseil.")

    def doc_sanction(x):
        r = G.registres["sanctions"]
        titre, corps, _s = R.fiche_simple(G, r, x, "Fiche de sanction disciplinaire", exclure=("niveau",))
        return titre, corps, [R.signature_vide("Le surveillant général / l'éducateur"), R.signature_vide("Le parent / tuteur (pris connaissance)"),
                              sig_directeur()]

    G.registre("sanctions", "Discipline et sanctions", [
        ("eleve", "Élève", "eleve"), ("classe", "Classe", "choix:classes_sec"), ("dateFait", "Date des faits", "date"), ("nature", "Nature", "choix:natures"),
        ("sanction", "Sanction", "choix:sanctions"), ("duree", "Durée (jours)", "entier"), ("demandeur", "Signalé par", "texte"),
        ("parentInforme", "Parent informé", "oui_non"), ("faits", "Description des faits", "long"), ("suite", "Suite donnée", "long")],
        unite="sanction", oblig="eleve", ordre="dateFait DESC", portee="ecole", feuille="Discipline", entite=True, niveaux=["ECOLE"],
        filtres=("nature", "sanction", "classe"), fiches={"fiche": ("Fiche de sanction", "alerte", doc_sanction)},
        colonnes=("eleve", "classe", "dateFait", "nature", "sanction", "duree", "parentInforme"),
        defauts=lambda: dict(ent_ecole(), dateFait=date.today().isoformat(), parentInforme="Non"), doc="Registre de discipline",
        aide="Les incidents du registre de l'école (Territoire › Incidents de discipline) restent disponibles ; celui-ci porte les sanctions du secondaire.")

    def conflits_courants(annee=None):
        """Conflits de l'année, calculés une fois par requête."""
        annee = annee or R.annee_active()
        cache = g.setdefault("_sec_conflits", {})
        if annee not in cache:
            cache[annee] = conflits_emploi(G.lignes(G.registres["emploi"], annee))
        return cache[annee]

    def calc_emploi(x):
        return {"Conflit": " ; ".join(conflits_courants(x.get("annee")).get(x.get("id"), []))}

    G.registre("emploi", "Emplois du temps", [
        ("classe", "Classe", "choix:classes_sec"), ("jour", "Jour", "choix:jours"), ("debut", "Début (ex. 8h00)", "heure"), ("fin", "Fin (ex. 10h00)", "heure"),
        ("matiere", "Matière", "liste:matieres_sec"), ("professeur", "Professeur", "texte"), ("salle", "Salle", "texte")],
        unite="créneau", oblig="classe", ordre="classe, jour, debut", portee="ecole", feuille="Emplois du temps", entite=True, niveaux=["ECOLE"],
        unique=("classe", "jour", "debut"), filtres=("classe", "jour", "professeur"), calcul=calc_emploi,
        defauts=lambda: dict(ent_ecole(), jour="Lundi"), doc="Emploi du temps",
        aide="Les créneaux qui se chevauchent pour le même professeur, la même salle ou la même classe sont signalés dans la colonne « Conflit ». "
             "La grille d'une classe est dans l'onglet « Grille ».")

    # ================================================================== examens
    def doc_convocation(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        txt = (f"Le candidat <b>{R.esc((x.get('nom') or '') + ' ' + (x.get('prenoms') or ''))}</b>"
               f"{', né(e) le ' + R.jjmmaaaa(x.get('dateNaissance')) if x.get('dateNaissance') else ''}"
               f"{' à ' + R.esc(x['lieuNaissance']) if x.get('lieuNaissance') else ''}, est convoqué(e) à l'examen du <b>{R.esc(x.get('examen') or '')}</b>"
               f"{' (série ' + R.esc(x['serie']) + ')' if x.get('serie') else ''}, session {R.esc(x.get('annee') or '')}.")
        corps = [Paragraph(txt, st["p"]), Spacer(1, 4),
                 R.tableau(["Numéro de table", "Centre d'examen", "Établissement"], [[x.get("numTable") or "à attribuer", x.get("centre") or "à définir",
                                                                                      x.get("entite") or ""]], [1, 1.6, 1.6], R.largeur_utile(False)),
                 Spacer(1, 5), Paragraph("Le candidat se présente muni de sa convocation et d'une pièce d'identité, 30 minutes avant l'heure.", st["p"])]
        return "Convocation à l'examen", corps, [sig_directeur()]

    G.registre("centres", "Centres d'examen", [
        ("code", "Code", "texte"), ("nom", "Centre d'examen", "texte"), ("examen", "Examen", "choix:examens"), ("commune", "Commune", "texte"),
        ("salles", "Salles de composition", "entier"), ("capacite", "Capacité par salle", "entier"), ("chef", "Chef de centre", "texte"),
        ("observations", "Observations", "long")], unite="centre", oblig="nom", ordre="nom", portee="ecole", feuille="Centres d'examen", entite=True,
        niveaux=["ECOLE"], unique=("nom", "examen"), totaux=("salles",),
        calcul=lambda x: {"Places": (x.get("salles") or 0) * (x.get("capacite") or 0)}, defauts=lambda: dict(ent_ecole(), capacite=30),
        doc="Centres d'examen")

    G.registre("candidats", "Candidats aux examens", [
        ("examen", "Examen", "choix:examens"), ("serie", "Série", "liste:series"), ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"),
        ("sexe", "Sexe", "choix:sexe"), ("dateNaissance", "Date de naissance", "date"), ("lieuNaissance", "Lieu de naissance", "texte"),
        ("classe", "Classe", "choix:classes_sec"), ("centre", "Centre d'examen", "liste:centres"), ("numTable", "N° de table", "texte"),
        ("moyenne", "Moyenne /20", "decimal"), ("absent", "Absent", "oui_non"), ("decisionJury", "Décision du jury", "choix:decisions"),
        ("observations", "Observations", "long")], unite="candidat", oblig="nom", ordre="examen, serie, nom, prenoms", portee="ecole",
        feuille="Candidats", entite=True, niveaux=["ECOLE"], unique=("examen", "nom", "prenoms", "dateNaissance"),
        filtres=("examen", "serie", "centre"),
        calcul=lambda x: {"Mention": mention(x.get("moyenne")) if decision_retenue(x) == "Admis" else "", "Décision retenue": decision_retenue(x)},
        colonnes=("examen", "serie", "nom", "prenoms", "sexe", "centre", "numTable", "moyenne", "absent", "decisionJury"),
        fiches={"convocation": ("Convocation", "valider-cercle", doc_convocation)},
        defauts=lambda: dict(ent_ecole(), examen="BEPC", absent="Non"), doc="Liste des candidats",
        aide="La mention et la décision proposée se calculent à partir de la moyenne (voir l'onglet « Statistiques »). "
             "La décision du jury, si elle est saisie, l'emporte. « Attribuer les numéros de table » numérote par examen et par centre.")

    # ================================================================== enseignement technique et professionnel
    G.registre("filieres", "Filières ETP", [
        ("intitule", "Filière", "texte"), ("domaine", "Domaine", "choix:domaines"), ("diplome", "Diplôme préparé", "choix:diplomes_etp"),
        ("cycle", "Cycle", "choix:cycles_ent"), ("duree", "Durée (années)", "entier"), ("capacite", "Capacité d'accueil", "entier"),
        ("effectif", "Effectif actuel", "entier"), ("chef", "Chef de département", "texte"), ("observations", "Observations", "long")],
        unite="filière", oblig="intitule", ordre="intitule", portee="ecole", feuille="Filières ETP", entite=True, niveaux=["ECOLE"],
        unique=("intitule", "diplome"), totaux=("capacite", "effectif"), defauts=lambda: dict(ent_ecole()), doc="Filières de l'enseignement technique et professionnel")
    G.registre("ateliers", "Ateliers et équipements", [
        ("atelier", "Atelier / laboratoire", "texte"), ("filiere", "Filière", "liste:filieres"), ("capacite", "Places", "entier"),
        ("equipements", "Équipements principaux", "long"), ("etat", "État général", "choix:etat"), ("besoins", "Besoins", "long"),
        ("responsable", "Responsable", "texte")], unite="atelier", oblig="atelier", ordre="filiere, atelier", portee="ecole", feuille="Ateliers",
        entite=True, niveaux=["ECOLE"], unique=("atelier", "filiere"), filtres=("filiere", "etat"), totaux=("capacite",),
        defauts=lambda: dict(ent_ecole(), etat="Bon"), doc="Ateliers et équipements")

    def doc_stage(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        nom = G.nom_eleve(x.get("eleve")) if x.get("eleve") else ""
        txt = (f"Il est attesté que l'élève <b>{R.esc(nom)}</b>, de la filière {R.esc(x.get('filiere') or '………')}, a effectué un stage "
               f"de {R.esc(x.get('duree') or '…')} jour(s), du {R.jjmmaaaa(x.get('dateDebut'))} au {R.jjmmaaaa(x.get('dateFin'))}, "
               f"auprès de <b>{R.esc(x.get('entreprise') or '………')}</b>{', sous la conduite de ' + R.esc(x['tuteur']) if x.get('tuteur') else ''}.")
        corps = [Paragraph(txt, st["p"])]
        if x.get("note") not in (None, ""):
            corps += [Spacer(1, 4), Paragraph(f"Appréciation : <b>{R.esc(G.valeur_affichee(G.registres['stages'], x, 'note'))} / 20</b>. "
                                              f"{R.esc(x.get('appreciation') or '')}", st["p"])]
        return "Attestation de stage", corps, [R.signature_vide("Le tuteur / le responsable de l'entreprise", x.get("tuteur") or ""), sig_directeur()]

    G.registre("stages", "Stages", [
        ("eleve", "Élève", "eleve"), ("filiere", "Filière", "liste:filieres"), ("entreprise", "Entreprise / structure d'accueil", "texte"),
        ("tuteur", "Tuteur", "texte"), ("dateDebut", "Début", "date"), ("dateFin", "Fin", "date"), ("duree", "Durée (jours)", "entier"),
        ("note", "Note /20", "decimal"), ("appreciation", "Appréciation du tuteur", "long")], unite="stage", oblig="eleve", ordre="dateDebut DESC",
        portee="ecole", feuille="Stages", entite=True, niveaux=["ECOLE"], filtres=("filiere",),
        fiches={"attestation": ("Attestation de stage", "valider-cercle", doc_stage)},
        colonnes=("eleve", "filiere", "entreprise", "tuteur", "dateDebut", "dateFin", "duree", "note"),
        defauts=lambda: dict(ent_ecole()), doc="Registre des stages")

    # ================================================================== identité (pilotage et structures)
    G.registre("etablissement", "Identité de l'établissement", [
        ("typeEtab", "Type", "choix:statuts_etab"), ("cycles", "Cycles ouverts", "choix:cycles_ent"), ("code", "Code de l'établissement", "texte"),
        ("ddestfp", "Direction départementale (DDESTFP)", "texte"), ("commune", "Commune", "texte"), ("anneeCreation", "Année de création", "entier"),
        ("autorisation", "Arrêté d'autorisation / d'ouverture", "texte"), ("directeur", "Proviseur / Directeur", "texte"), ("censeur", "Censeur / Directeur des études", "texte"),
        ("surveillantGeneral", "Surveillant général", "texte"), ("intendant", "Intendant / Économe", "texte"), ("secretaire", "Secrétaire", "texte"),
        ("cpe", "Conseiller principal d'éducation", "texte"), ("salles", "Salles de classe", "entier"), ("telephone", "Téléphone", "texte")],
        unite="fiche", oblig="typeEtab", ordre="id DESC", portee="ecole", feuille="Identité", entite=True, niveaux=["ECOLE"],
        defauts=lambda: dict(ent_ecole(), directeur=H.config.ECOLE.get("directeur") or ""), doc="Identité de l'établissement secondaire",
        aide="Une fiche par année : elle alimente l'en-tête du tableau synoptique envoyé à la direction départementale.")

    G.page("sec_synoptique", "Tableau synoptique")
    G.page("sec_examens_stats", "Statistiques des examens")
    G.page("sec_emploi_grille", "Grille d'emploi du temps")

    # ------------------------------------------------------------------ données de l'école
    def eleves_par_niveau():
        """{niveau: {"M": n, "F": n, "classes": n}} pour les classes du secondaire de l'école courante."""
        marque = ",".join("?" * len(NIVEAUX_SECONDAIRE))
        out = {n: {"M": 0, "F": 0, "classes": 0} for n in NIVEAUX_SECONDAIRE}
        try:
            for c in q(f"SELECT niveau, COUNT(*) n FROM classes WHERE ecole_id=? AND niveau IN ({marque}) GROUP BY niveau",
                       (H.eco(),) + tuple(NIVEAUX_SECONDAIRE)):
                out[c["niveau"]]["classes"] = c["n"]
            for c in q(f"""SELECT c.niveau, e.sexe, COUNT(*) n FROM eleves e JOIN classes c ON c.id=e.classe_id
                           WHERE c.ecole_id=? AND e.statut='inscrit' AND c.niveau IN ({marque}) GROUP BY c.niveau, e.sexe""",
                       (H.eco(),) + tuple(NIVEAUX_SECONDAIRE)):
                out[c["niveau"]]["F" if c["sexe"] == "F" else "M"] += c["n"]
        except Exception:  # noqa: BLE001
            pass
        return out

    def professeurs_stats(annee):
        p = R.cle_portee("ecole")
        try:
            rows = q("SELECT sexe, statut, COUNT(*) n FROM reg_sec_professeurs WHERE portee=? AND annee=? GROUP BY sexe, statut", (p, annee))
        except Exception:  # noqa: BLE001
            return {"total": 0, "F": 0, "M": 0, "statuts": {}}
        out = {"total": 0, "F": 0, "M": 0, "statuts": {}}
        for r in rows:
            out["total"] += r["n"]
            out["F" if r["sexe"] == "F" else "M"] += r["n"]
            out["statuts"][r["statut"] or "Non précisé"] = out["statuts"].get(r["statut"] or "Non précisé", 0) + r["n"]
        return out

    def synoptique(annee=None):
        annee = annee or R.annee_active()
        niv = eleves_par_niveau()
        eff_m, eff_f = sum(v["M"] for v in niv.values()), sum(v["F"] for v in niv.values())
        classes = sum(v["classes"] for v in niv.values())
        prof = professeurs_stats(annee)
        ident = q("SELECT * FROM reg_sec_etablissement WHERE portee=? AND annee=? ORDER BY id DESC LIMIT 1", (R.cle_portee("ecole"), annee), un=True)
        c1 = {k: sum(niv[n][k] for n in NIVEAUX_SECONDAIRE if CYCLES[n] == "1er cycle") for k in ("M", "F", "classes")}
        c2 = {k: sum(niv[n][k] for n in NIVEAUX_SECONDAIRE if CYCLES[n] == "2nd cycle") for k in ("M", "F", "classes")}
        return {"annee": annee, "niveaux": niv, "garcons": eff_m, "filles": eff_f, "effectif": eff_m + eff_f, "classes": classes,
                "cycle1": c1, "cycle2": c2, "professeurs": prof, "identite": dict(ident) if ident else {},
                "eleves_par_classe": round((eff_m + eff_f) / classes, 1) if classes else None,
                "eleves_par_professeur": round((eff_m + eff_f) / prof["total"], 1) if prof["total"] else None,
                "pct_filles": taux(eff_f, eff_m + eff_f)}
    H.sec_synoptique = synoptique

    def a_secondaire():
        """Vrai si l'école courante a des classes du secondaire (affiche le menu)."""
        if "a_sec" not in g:
            try:
                g.a_sec = bool(q("SELECT 1 FROM classes WHERE ecole_id=? AND niveau IN (%s) LIMIT 1" % ",".join("?" * len(NIVEAUX_SECONDAIRE)),
                                 (H.eco(),) + tuple(NIVEAUX_SECONDAIRE)))
            except Exception:  # noqa: BLE001
                g.a_sec = False
        return g.a_sec
    app.context_processor(lambda: {"a_secondaire": a_secondaire})

    def lignes_candidats(annee, examen="", centre=""):
        f = {k: v for k, v in (("examen", examen), ("centre", centre)) if v}
        return G.lignes(G.registres["candidats"], annee, None, f)

    def alertes():
        """Nombre d'alertes : créneaux en conflit + candidats sans numéro de table."""
        if R.juridiction() and not g.get("ecole"):
            return 0
        n = 0
        try:
            n += len(conflits_courants())
            n += q("SELECT COUNT(*) n FROM reg_sec_candidats WHERE portee=? AND annee=? AND COALESCE(numTable,'')=''",
                   (R.cle_portee("ecole"), R.annee_active()), un=True)["n"]
        except Exception:  # noqa: BLE001
            return 0
        return n
    G.alertes = lambda: (alertes(), url_for("sec_emploi_grille"))

    # ------------------------------------------------------------------ pages
    def seulement_ecole():
        if R.juridiction() and not g.get("ecole"):
            flash("Ouvrez d'abord une école : ces pages sont tenues par établissement.", "warning")
            return redirect(url_for("jur_ecoles_modules") if "jur_ecoles_modules" in app.view_functions else url_for("accueil"))
        return None

    def annee_req():
        v = (request.values.get("annee") or "").strip()
        return v if re.fullmatch(r"\d{4}-\d{4}", v) else R.annee_active()

    @app.route("/secondaire/synoptique")
    @H.connexion_requise("secondaire")
    def sec_synoptique():
        r = seulement_ecole()
        if r:
            return r
        return render_template("sec_synoptique.html", G=G, ep_actif="sec_synoptique", s=synoptique(annee_req()), niveaux=NIVEAUX_SECONDAIRE, cycles=CYCLES)

    def lignes_synoptique(s):
        out = []
        for n in NIVEAUX_SECONDAIRE:
            v = s["niveaux"][n]
            tot = v["M"] + v["F"]
            out.append([n, CYCLES[n], v["classes"], v["M"], v["F"], tot, taux(v["F"], tot) if tot else "", round(tot / v["classes"], 1) if v["classes"] else ""])
        out.append(["Total", "", s["classes"], s["garcons"], s["filles"], s["effectif"], s["pct_filles"] or "", s["eleves_par_classe"] or ""])
        return out
    ENT_SYN = ["Niveau", "Cycle", "Classes", "Garçons", "Filles", "Total", "% de filles", "Élèves par classe"]

    @app.route("/secondaire/synoptique.xlsx")
    @H.connexion_requise("secondaire")
    def sec_synoptique_xlsx():
        r = seulement_ecole()
        if r:
            return r
        s = synoptique(annee_req())
        p = s["professeurs"]
        extra = [[], ["Professeurs", p["total"], "dont femmes", p["F"]], ["Élèves par professeur", s["eleves_par_professeur"] or ""]]
        return H.xlsx.reponse_classeur(f"synoptique_secondaire_{s['annee']}.xlsx", [("Synoptique", ENT_SYN, lignes_synoptique(s) + extra, {})])

    @app.route("/secondaire/synoptique.pdf")
    @H.connexion_requise("secondaire")
    def sec_synoptique_pdf():
        r = seulement_ecole()
        if r:
            return r
        from reportlab.platypus import Paragraph, Spacer
        s = synoptique(annee_req())
        st, i, p = R.styles(), s["identite"], s["professeurs"]
        corps = []
        if i:
            lig = [[lbl, i.get(k) or ""] for k, lbl in (("typeEtab", "Type"), ("cycles", "Cycles"), ("code", "Code"), ("ddestfp", "Direction départementale"),
                                                       ("commune", "Commune"), ("directeur", "Proviseur / Directeur"), ("censeur", "Censeur"),
                                                       ("surveillantGeneral", "Surveillant général"), ("intendant", "Intendant"), ("cpe", "CPE")) if i.get(k)]
            corps += [R.tableau(["Identité", ""], lig, [1, 2], R.largeur_utile(False)), Spacer(1, 6)]
        corps += [R.tableau(ENT_SYN, lignes_synoptique(s), [1.2, 1.2, 1, 1, 1, 1, 1, 1.2], R.largeur_utile(False)), Spacer(1, 6),
                  Paragraph(f"<b>Professeurs :</b> {p['total']} (dont {p['F']} femme(s)) — <b>élèves par professeur :</b> {s['eleves_par_professeur'] or '—'}. "
                            + (" ; ".join(f"{k} : {v}" for k, v in p["statuts"].items())), st["p"])]
        code = R.code_document("sec_synoptique", f"Synoptique de l'établissement secondaire — {s['annee']}",
                               f"sec:syn:{s['annee']}:{s['effectif']}:{s['classes']}:{p['total']}")
        return H.pdf_reponse(R.pdf_document("TABLEAU SYNOPTIQUE DE L'ÉTABLISSEMENT SECONDAIRE", corps, [sig_directeur()], code, False,
                                            f"{H.config.ECOLE.get('nom', '')} · année scolaire {s['annee']}"), f"synoptique_secondaire_{s['annee']}.pdf")

    def donnees_examens(annee, examen, centre):
        lignes = lignes_candidats(annee, examen, centre)
        groupes, total = stats_candidats(lignes)
        rows = []
        for (ex_, serie), c in sorted(groupes.items()):
            s = resume_stats(c)
            rows.append([ex_, serie or "—", s["inscrits"], s["inscrits_g"], s["inscrits_f"], s["presents"], s["admis"], s["admis_g"], s["admis_f"], s["second"],
                         s["taux"] if s["taux"] is not None else "", s["taux_g"] if s["taux_g"] is not None else "", s["taux_f"] if s["taux_f"] is not None else ""])
        t = resume_stats(total)
        rows.append(["Total", "", t["inscrits"], t["inscrits_g"], t["inscrits_f"], t["presents"], t["admis"], t["admis_g"], t["admis_f"], t["second"],
                     t["taux"] if t["taux"] is not None else "", t["taux_g"] if t["taux_g"] is not None else "", t["taux_f"] if t["taux_f"] is not None else ""])
        return lignes, rows, t
    ENT_EXAM = ["Examen", "Série", "Inscrits", "dont G", "dont F", "Présents", "Admis", "Admis G", "Admis F", "Second tour", "Taux (%)", "Taux G (%)", "Taux F (%)"]

    @app.route("/secondaire/examens/statistiques")
    @H.connexion_requise("secondaire")
    def sec_examens_stats():
        r = seulement_ecole()
        if r:
            return r
        annee, examen, centre = annee_req(), (request.args.get("examen") or "").strip(), (request.args.get("centre") or "").strip()
        lignes, rows, total = donnees_examens(annee, examen, centre)
        par_centre = {}
        for x in lignes:
            c = par_centre.setdefault(x.get("centre") or "(sans centre)", [])
            c.append(x)
        centres_rows = []
        for nom, L in sorted(par_centre.items()):
            _g, tot = stats_candidats(L)
            s = resume_stats(tot)
            centres_rows.append([nom, s["inscrits"], s["presents"], s["admis"], s["taux"] if s["taux"] is not None else ""])
        return render_template("sec_examens_stats.html", G=G, ep_actif="sec_examens_stats", annee=annee, examen=examen, centre=centre, ent=ENT_EXAM, rows=rows,
                               centres_rows=centres_rows, examens=EXAMENS, centres=centres(), total=total, nb=len(lignes),
                               peut_ecrire=G.peut_ecrire(G.registres["candidats"]))

    @app.route("/secondaire/examens/statistiques.xlsx")
    @H.connexion_requise("secondaire")
    def sec_examens_stats_xlsx():
        r = seulement_ecole()
        if r:
            return r
        annee, examen, centre = annee_req(), (request.args.get("examen") or "").strip(), (request.args.get("centre") or "").strip()
        _l, rows, _t = donnees_examens(annee, examen, centre)
        return H.xlsx.reponse_classeur(f"statistiques_examens_{annee}.xlsx", [("Examens", ENT_EXAM, rows, {})])

    @app.route("/secondaire/examens/statistiques.pdf")
    @H.connexion_requise("secondaire")
    def sec_examens_stats_pdf():
        r = seulement_ecole()
        if r:
            return r
        annee, examen, centre = annee_req(), (request.args.get("examen") or "").strip(), (request.args.get("centre") or "").strip()
        lignes, rows, _t = donnees_examens(annee, examen, centre)
        corps = [R.tableau(ENT_EXAM, rows, [1.3, 1, 1, .8, .8, 1, 1, .9, .9, 1, 1, 1, 1], R.largeur_utile(True))]
        sous = f"{H.config.ECOLE.get('nom', '')} · session {annee}" + (f" · {examen}" if examen else "") + (f" · {centre}" if centre else "")
        code = R.code_document("sec_examens_stats", f"Statistiques des examens — {annee} {examen} {centre}".strip(),
                               f"sec:exam:{annee}:{examen}:{centre}:{len(lignes)}:{max([x.get('maj') or '' for x in lignes] or [''])}")
        return H.pdf_reponse(R.pdf_document("STATISTIQUES DES EXAMENS", corps, [sig_directeur()], code, True, sous), f"statistiques_examens_{annee}.pdf")

    @app.route("/secondaire/examens/numeroter", methods=["POST"])
    @H.connexion_requise("secondaire")
    def sec_examens_numeroter():
        r = seulement_ecole()
        if r:
            return r
        reg = G.registres["candidats"]
        if not G.peut_ecrire(reg):
            flash("Écriture réservée à la direction.", "warning")
            return redirect(url_for("sec_examens_stats"))
        annee, examen = annee_req(), (request.form.get("examen") or "").strip()
        lignes = [x for x in G.lignes(reg, annee) if (not examen or x["examen"] == examen)]
        lignes.sort(key=lambda x: (x.get("examen") or "", x.get("centre") or "", R._norm(x.get("nom")), R._norm(x.get("prenoms"))))
        n_par, nb = {}, 0
        for x in lignes:
            if (x.get("numTable") or "").strip():
                continue
            cle = (x.get("examen") or "", x.get("centre") or "")
            n_par[cle] = n_par.get(cle, 0)
            while True:
                n_par[cle] += 1
                prefixe = re.sub(r"[^A-Z]", "", (x.get("examen") or "X").upper())[:4] or "X"
                num = f"{prefixe}-{n_par[cle]:04d}"
                if not q(f"SELECT 1 FROM {reg.table} WHERE portee=? AND annee=? AND examen=? AND COALESCE(centre,'')=? AND numTable=?",
                         (R.cle_portee("ecole"), annee, x.get("examen") or "", x.get("centre") or "", num), un=True):
                    break
            ex(f"UPDATE {reg.table} SET numTable=?, maj=? WHERE id=?", (num, H.maintenant(), x["id"]))
            nb += 1
        H.journal("sec_numeros_table", f"{nb} numéro(s) {examen or 'tous examens'} {annee}")
        flash(f"{nb} numéro(s) de table attribué(s).", "success")
        return redirect(url_for("sec_examens_stats", annee=annee, examen=examen))

    @app.route("/secondaire/programme/gabarit", methods=["POST"])
    @H.connexion_requise("secondaire")
    def sec_programme_gabarit():
        r = seulement_ecole()
        if r:
            return r
        reg = G.registres["programme"]
        if not G.peut_ecrire(reg):
            flash("Écriture réservée à la direction.", "warning")
            return redirect(url_for("reg_page", gcle="sec", rcle="programme"))
        noms = matieres_sec()
        coefs = {m["nom"]: m["coefficient"] for m in q("SELECT nom, coefficient FROM matieres WHERE cycle='secondaire' AND actif=1")}
        annee, nb = R.annee_active(), 0
        for niveau, serie, matiere, coef, heures in gabarit(noms, coefs):
            if q(f"SELECT 1 FROM {reg.table} WHERE portee=? AND annee=? AND niveauClasse=? AND serie=? AND matiere=?",
                 (R.cle_portee("ecole"), annee, niveau, serie, matiere), un=True):
                continue
            ex(f"INSERT INTO {reg.table} (portee, annee, niveau, entite, niveauClasse, serie, matiere, coefficient, heures, optionnelle, cree_le, cree_par, maj) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (R.cle_portee("ecole"), annee, "ECOLE", R.entite_courante()[1], niveau, serie, matiere, coef, heures,
                "Oui" if re.search("espagnol|allemand", matiere, re.I) else "Non", H.maintenant(), g.user["id"], H.maintenant()))
            nb += 1
        H.journal("sec_programme_gabarit", f"{nb} ligne(s)")
        flash(f"Gabarit chargé : {nb} ligne(s) ajoutée(s). Ajustez les coefficients et les heures selon le programme officiel.", "success")
        return redirect(url_for("reg_page", gcle="sec", rcle="programme"))

    def notes_classe(classe_nom, periode, annee):
        """-> (classe, [moyenne par élève]) depuis les notes saisies pour la période (coefficients de la table des matières ; règle du noyau)."""
        cl = q("SELECT * FROM classes WHERE ecole_id=? AND nom=?", (H.eco(), classe_nom), un=True)
        if not cl:
            return None, []
        eleves = q("SELECT id FROM eleves WHERE classe_id=? AND statut='inscrit'", (cl["id"],))
        coefs = {m["id"]: m["coefficient"] for m in q("SELECT id, coefficient FROM matieres WHERE cycle='secondaire'")}
        # coefficients du programme (niveau + série de la classe) quand ils existent
        serie = serie_de_classe(classe_nom, cl["niveau"])
        prog = {x["matiere"]: x["coefficient"] for x in q("SELECT matiere, coefficient FROM reg_sec_programme WHERE portee=? AND annee=? AND niveauClasse=? AND serie=?",
                                                          (R.cle_portee("ecole"), annee, cl["niveau"], serie))}
        noms = {m["id"]: m["nom"] for m in q("SELECT id, nom FROM matieres WHERE cycle='secondaire'")}
        moyennes = []
        for e in eleves:
            # notes.periode = libellé de l'évaluation (« Trimestre 1 », « Devoir 2 – Trimestre 1 »…) : on retient celles qui contiennent la période ;
            # plusieurs notes d'une même matière sont moyennées avant la pondération.
            par_matiere = {}
            for n in q("SELECT matiere_id, valeur FROM notes WHERE eleve_id=? AND annee=? AND dispense=0 AND valeur IS NOT NULL AND periode LIKE ?",
                       (e["id"], annee, "%" + periode + "%")):
                par_matiere.setdefault(n["matiere_id"], []).append(n["valeur"])
            ns = [(sum(v) / len(v), prog.get(noms.get(mid), coefs.get(mid, 1))) for mid, v in par_matiere.items()]
            moyennes.append(moyenne_eleve(ns, cl["niveau"]))
        return cl, moyennes

    @app.route("/secondaire/conseils/calculer", methods=["POST"])
    @H.connexion_requise("secondaire")
    def sec_conseil_calculer():
        r = seulement_ecole()
        if r:
            return r
        reg = G.registres["conseils"]
        if not G.peut_ecrire(reg):
            flash("Écriture réservée à la direction.", "warning")
            return redirect(url_for("reg_page", gcle="sec", rcle="conseils"))
        classe, periode, annee = (request.form.get("classe") or "").strip(), (request.form.get("periode") or "").strip(), R.annee_active()
        cl, moyennes = notes_classe(classe, periode, annee)
        if not cl or periode not in H.config.PERIODES:
            flash("Choisissez une classe du secondaire et une période.", "warning")
            return redirect(url_for("reg_page", gcle="sec", rcle="conseils"))
        s = stats_moyennes(moyennes)
        ligne = q(f"SELECT id FROM {reg.table} WHERE portee=? AND annee=? AND classe=? AND periode=?", (R.cle_portee("ecole"), annee, classe, periode), un=True)
        vals = {"effectif": len(moyennes), "composes": s.get("composes", 0), "moyenneClasse": s.get("moyenne"), "moyenneMax": s.get("max"),
                "moyenneMin": s.get("min"), "sup10": s.get("sup10", 0)}
        if ligne:
            ex(f"UPDATE {reg.table} SET effectif=?, composes=?, moyenneClasse=?, moyenneMax=?, moyenneMin=?, sup10=?, maj=? WHERE id=?",
               (*vals.values(), H.maintenant(), ligne["id"]))
            rid = ligne["id"]
        else:
            rid = ex(f"INSERT INTO {reg.table} (portee, annee, niveau, entite, classe, periode, dateConseil, effectif, composes, moyenneClasse, moyenneMax, "
                     "moyenneMin, sup10, cree_le, cree_par, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (R.cle_portee("ecole"), annee, "ECOLE", R.entite_courante()[1], classe, periode, date.today().isoformat(), *vals.values(),
                      H.maintenant(), g.user["id"], H.maintenant()))
        H.journal("sec_conseil_calcul", f"{classe} {periode}")
        if not s.get("composes"):
            flash("Aucune note trouvée pour cette classe et cette période : la ligne est créée, à compléter.", "warning")
        else:
            flash(f"Calcul fait : {s['composes']} élève(s) ayant composé, moyenne de la classe {str(s['moyenne']).replace('.', ',')}.", "success")
        return redirect(url_for("reg_page", gcle="sec", rcle="conseils", modifier=rid))

    @app.route("/secondaire/emploi/grille")
    @H.connexion_requise("secondaire")
    def sec_emploi_grille():
        r = seulement_ecole()
        if r:
            return r
        classe = (request.args.get("classe") or "").strip()
        lignes = G.lignes(G.registres["emploi"], R.annee_active())
        conf = conflits_emploi(lignes)
        classes = sorted({x["classe"] for x in lignes if x.get("classe")}, key=lambda c: c)
        classe = classe if classe in classes else (classes[0] if classes else "")
        sel = [x for x in lignes if x.get("classe") == classe]
        horaires = sorted({(x.get("debut") or "", x.get("fin") or "") for x in sel}, key=lambda h: (minutes(h[0]) or 0, minutes(h[1]) or 0))
        case = {(x.get("jour"), (x.get("debut") or "", x.get("fin") or "")): x for x in sel}
        return render_template("sec_emploi.html", G=G, ep_actif="sec_emploi_grille", classe=classe, classes=classes, jours=JOURS, horaires=horaires, case=case,
                               conflits=conf, nb_conflits=len(conf))

    # synthèse exposée aux tableaux de bord (pilotage) : mêmes clés simples que santé
    def sec_synthese(annee=None):
        s = synoptique(annee)
        return {"classes": s["classes"], "effectif": s["effectif"], "filles": s["filles"], "professeurs": s["professeurs"]["total"],
                "eleves_par_classe": s["eleves_par_classe"] or 0}
    H.sec_synthese = sec_synthese
