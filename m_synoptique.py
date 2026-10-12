# -*- coding: utf-8 -*-
"""
Tableau synoptique de l'école (toutes éditions : GESCOL, GESCOL Public ; consultable aussi depuis les
applications CS / DDEMP pour l'école courante).

Le tableau synoptique précède le tableau de bord : il rassemble, pour une école, les rubriques demandées
par le MEMP et les directions départementales :

* **Identité** (table `synoptique_identite`, une ligne par école) : MEMP, DDEMP, CCS, EPP, CP de zone,
  zone pédagogique n°, UP, RUP, Co-RUP, année de création, « dirigé par », grade et nom du directeur.
  Les valeurs connues de la fiche école (`ecoles`) sont proposées par défaut et les champs communs
  (ccs_nom, up, zone, directeur_nom, directeur_titre) y sont recopiés à l'enregistrement.
* **Personnel enseignant** : tableau synoptique du personnel (tables `personnel` + `personnel_carriere`
  de m_carriere, complétées ici des colonnes `promotion`, `cours_tenus`, `date_derniere_formation`,
  `visites_directeur`). Les anciennetés et la date de départ à la retraite sont CALCULÉES par
  m_carriere (jamais saisies) :
  - anciennetés : de la date de prise de service dans chaque lieu jusqu'au 31 décembre de la première
    année de l'année scolaire active (« 2026-2027 » → 31/12/2026), jour inclus ;
  - retraite : 60 ans (grade A), 58 ans (B), 55 ans (C), départ le 1er jour du trimestre qui suit le
    trimestre de naissance (janv.–mars → 1er avril ; avril–juin → 1er juillet ; juil.–sept. → 1er octobre ;
    oct.–déc. → 1er janvier suivant).
* **Comités** (table `synoptique_membres`) : comité de santé, bureau de l'APE, comité de direction,
  comités de classe (un par classe de l'école).
* **Emplois du temps** (table `synoptique_edt`, un par cours) préremplis avec les emplois du temps
  officiels du MEMP (CI-CP, CE1-CE2, CM1-CM2 : « nouveaux emplois du temps portant réhabilitation de la
  dictée », septembre 2016 ; maternelle : section des petits, DEM septembre 2012), modifiables case par case.
* **Planification annuelle** (table `synoptique_planification`, une par cours) : mêmes colonnes que la
  planification annuelle officielle (Trimestres, Mois, Français, Maths, Éducation sociale (Morale, Civisme,
  Histoire, Géographie), EST, EPS, Éducation artistique (Chant, Poésie, Conte, Dessin, Couture)), préremplie
  pour le CI → CM2 avec la planification de référence (DDEMP Donga, CS Djougou II, 2023-2024).
* **Planification mensuelle (CE-CM)** (table `synoptique_planification_mensuelle`, une par classe et par mois
  « AAAA-MM ») : reproduction du modèle officiel « PLANIFICATION (CE-CM) DU MOIS DE … » (1 page paysage) :
  champs de formation (Français avec ses séquences de 1re / 2e semaine, Dictée, Mathématiques, Éducation sociale,
  EST, Éducation artistique, EPS) × 5 semaines (« Du … au … »). Les semaines sont proposées automatiquement
  (lundi → vendredi, 5 au plus, un mois commençant le week-end démarre au lundi suivant) et la grille est
  préremplie avec les gabarits du modèle (« U…SA…S…Étape… », « U..SA..S..E..Texte n°.. », « SA…Séq… »…).
  Classes CE1 → CM2 (CI et CP acceptés avec la même grille) ; un enseignant n'accède qu'à ses classes affectées
  (`H.classes_autorisees()`) et peut y écrire sans le droit `synoptique`. Ajouter / modifier / supprimer un mois,
  dupliquer le mois précédent, réinitialiser (gabarits), PDF au modèle officiel (signatures du titulaire
  `classe:<id>:titulaire` et du directeur avec cachet / griffe), Excel, import Excel (modèle).
  Les autres modules lisent `H.planification_mensuelle(ecole_id, annee, classe_id)`.
* **Règlement intérieur** (table `synoptique_reglement`) prérempli avec le règlement intérieur des écoles
  primaires révisé (MEMP, N°0548/MEMP/DC/SGM/DEP/SP, Porto-Novo, 26 mars 2018) : préambule, titres, articles.
* Import / export Excel (classeur multi-feuilles, modèle à télécharger) et PDF complet (paysage).

Droits : lecture pour tout utilisateur connecté de l'école ; écriture avec le droit `synoptique`.
Les autres modules lisent `H.synoptique_identite(ecole_id)` et `H.synoptique_personnel(ecole_id)`.
"""
import io
import json
import re
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

import m_carriere as MC

# ---------------------------------------------------------------- référentiels
NIVEAUX = [("maternelle1", "Maternelle 1"), ("maternelle2", "Maternelle 2"), ("ci", "CI"), ("cp", "CP"),
           ("ce1", "CE1"), ("ce2", "CE2"), ("cm1", "CM1"), ("cm2", "CM2")]
NIVEAUX_LIB = dict(NIVEAUX)
GROUPE_EDT = {"maternelle1": "maternelle", "maternelle2": "maternelle", "ci": "ci_cp", "cp": "ci_cp",
              "ce1": "ce1_ce2", "ce2": "ce1_ce2", "cm1": "cm1_cm2", "cm2": "cm1_cm2"}
JOURS = [("lundi", "Lundi"), ("mardi", "Mardi"), ("mercredi", "Mercredi"), ("jeudi", "Jeudi"), ("vendredi", "Vendredi")]
COMITES = {"sante": "Comité de santé", "ape": "Bureau de l'APE", "direction": "Comité de direction",
           "classe": "Comité de classe"}
QUALITES = ["Président(e)", "Vice-président(e)", "Secrétaire", "Secrétaire adjoint(e)", "Trésorier(ère)",
            "Trésorier(ère) adjoint(e)", "Commissaire aux comptes", "Responsable", "Membre"]
ORIGINES = ["Parent d'élève", "Enseignant(e)", "Directeur / directrice", "Agent de santé", "Élève", "Élu local",
            "Vendeuse / restauratrice", "Partenaire", "Autre"]
TITRES_DIRECTION = ["Directeur", "Directrice"]
MOIS_SCOLAIRES = [("I", "Septembre"), ("I", "Octobre"), ("I", "Novembre"), ("I", "Décembre"), ("II", "Janvier"),
                  ("II", "Février"), ("II", "Mars"), ("III", "Avril"), ("III", "Mai"), ("III", "Juin")]
# colonnes de la planification (clé, libellé court, groupe)
COLS_PLAN = [("trimestre", "Trimestre", ""), ("mois", "Mois", ""), ("francais", "Français", ""), ("maths", "Maths", ""),
             ("es_morale", "Morale", "Éducation sociale"), ("es_civisme", "Civisme", "Éducation sociale"),
             ("es_histoire", "Histoire", "Éducation sociale"), ("es_geographie", "Géographie", "Éducation sociale"),
             ("est", "EST", ""), ("eps", "EPS", ""),
             ("ea_chant", "Chant", "Éducation artistique"), ("ea_poesie", "Poésie", "Éducation artistique"),
             ("ea_conte", "Conte", "Éducation artistique"), ("ea_dessin", "Dessin", "Éducation artistique"),
             ("ea_couture", "Couture", "Éducation artistique"), ("observations", "Observations", "")]
CLES_PLAN = [c for c, _l, _g in COLS_PLAN]

# ---- planification mensuelle (CE-CM) : modèle officiel docs_reference/planification_mensuelle_CE1_CM2.pdf
# Une ligne par discipline ; pour le français, deux libellés (séquence de la 1re semaine / de la 2e semaine).
# (code, champ de formation, libellé 1re semaine, libellé 2e semaine, gabarit de la case)
GAB_ETAPE = "U…SA…S…Étape…"
GAB_TEXTE = "U..SA..S..E..Texte n°.."
GAB_SEQ = "SA…Séq…"
LIGNES_PM = [
    ("fr_1", "FRANÇAIS", "1-C.O/Voc thémat", "1-Communication orale", GAB_ETAPE),
    ("fr_2", "FRANÇAIS", "2-Lecture", "2-Lecture", GAB_TEXTE),
    ("fr_3", "FRANÇAIS", "3-Exp écrite imprég", "3-Vocab systématique", GAB_ETAPE),
    ("fr_4", "FRANÇAIS", "4-Exp écrite 1er jet", "4-Grammaire", GAB_ETAPE),
    ("fr_5", "FRANÇAIS", "5-Vocab fonct", "5-Conjugaison", GAB_ETAPE),
    ("fr_6", "FRANÇAIS", "6-Grammaire", "6-Orthographe (Dictée)", GAB_ETAPE),
    ("fr_7", "FRANÇAIS", "7-Conjugaison", "7-Exp écrite amélioration", GAB_ETAPE),
    ("fr_8", "FRANÇAIS", "8-Orthographe", "8-Écriture", GAB_ETAPE),
    ("fr_9", "FRANÇAIS", "9-Écriture", "9-Lecture", GAB_TEXTE),
    ("fr_10", "FRANÇAIS", "10-Lecture", "10-Exp écrite n° 4 / Écriture", GAB_ETAPE),
    ("fr_11", "FRANÇAIS", "11-Écriture", "11-Lecture renforcement", GAB_TEXTE),
    ("fr_12", "FRANÇAIS", "", "12-Exp écrite compte rendu", GAB_ETAPE),
    ("fr_dictee", "FRANÇAIS", "Dictée", None, ""),
    ("maths", "MATHÉMATIQUES", None, None, "D…SA…SÉANCES N°s…"),
    ("es_langue", "ÉDUCATION SOCIALE", "LANGUE", None, ""),
    ("es_morale", "ÉDUCATION SOCIALE", "MORALE", None, GAB_SEQ),
    ("es_civisme", "ÉDUCATION SOCIALE", "CIVISME", None, GAB_SEQ),
    ("es_histoire", "ÉDUCATION SOCIALE", "HISTOIRE", None, GAB_SEQ),
    ("es_geographie", "ÉDUCATION SOCIALE", "GÉOGRAPHIE", None, GAB_SEQ),
    ("est", "ÉDUCATION SCIENTIFIQUE ET TECHNOLOGIQUE", None, None, GAB_SEQ),
    ("ea_chant", "ÉDUCATION ARTISTIQUE", "CHANT", None, "SA…Titre…"),
    ("ea_poesie", "ÉDUCATION ARTISTIQUE", "POÉSIE", None, GAB_SEQ),
    ("ea_dessin", "ÉDUCATION ARTISTIQUE", "DESSIN", None, GAB_SEQ),
    ("ea_contes", "ÉDUCATION ARTISTIQUE", "CONTES", None, GAB_SEQ),
    ("ea_couture", "ÉDUCATION ARTISTIQUE", "COUTURE", None, GAB_SEQ),
    ("eps", "ÉDUCATION PHYSIQUE ET SPORTIVE", None, None, GAB_SEQ),
]
CODES_PM = [l[0] for l in LIGNES_PM]
NB_SEMAINES_PM = 5
SEMAINES_PM = ["1ère Semaine", "2ème Semaine", "3ème Semaine", "4ème Semaine", "5ème Semaine"]
NIVEAUX_PM = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]            # CE1-CM2 (modèle) ; CI-CP acceptés avec la même grille
MOIS_LIB = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
TYPES_REGLEMENT = {"preambule": "Préambule", "titre": "Titre", "article": "Article"}

# champs de l'identité : (clé, libellé, valeur par défaut depuis la fiche école ou constante)
CHAMPS_IDENTITE = [
    ("memp", "Nom du MEMP (ministère)"), ("ddemp", "Nom du DDEMP"), ("ccs", "Nom du CCS"), ("epp", "Nom de l'EPP (école)"),
    ("cp_zone", "Nom du CP de zone"), ("zone_numero", "Zone pédagogique n°"), ("up", "UP (unité pédagogique)"),
    ("rup_nom", "Nom du RUP"), ("corup_nom", "Nom du Co-RUP"), ("annee_creation", "Année de création de l'école"),
    ("dirige_par", "Dirigée par"), ("directeur_grade", "Grade du directeur / de la directrice"),
    ("directeur_nom", "Nom et prénoms du directeur / de la directrice"),
]
MEMP_DEFAUT = "Ministère des Enseignements Maternel et Primaire"

SCHEMA = """
CREATE TABLE IF NOT EXISTS synoptique_identite (
    ecole_id INTEGER PRIMARY KEY,
    memp TEXT, ddemp TEXT, ccs TEXT, epp TEXT, cp_zone TEXT, zone_numero TEXT, up TEXT,
    rup_nom TEXT, corup_nom TEXT, annee_creation TEXT, dirige_par TEXT, directeur_grade TEXT, directeur_nom TEXT,
    maj TEXT, maj_par INTEGER
);
CREATE TABLE IF NOT EXISTS synoptique_membres (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL,
    annee TEXT,
    comite TEXT NOT NULL,                 -- sante | ape | direction | classe
    classe_id INTEGER,                    -- comité de classe : classe concernée
    ordre INTEGER DEFAULT 0,
    nom_prenoms TEXT NOT NULL,
    qualite TEXT,                         -- président, secrétaire, trésorier, membre…
    origine TEXT,                         -- parent, enseignant, agent de santé, élève…
    contact TEXT,
    observations TEXT,
    maj TEXT, maj_par INTEGER
);
CREATE INDEX IF NOT EXISTS idx_synoptique_membres ON synoptique_membres (ecole_id, comite, classe_id);
CREATE TABLE IF NOT EXISTS synoptique_edt (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL,
    niveau TEXT NOT NULL,                 -- maternelle1 … cm2
    classe_id INTEGER,
    contenu TEXT NOT NULL,                -- JSON {lignes: [{horaire, lundi, mardi, mercredi, jeudi, vendredi}], remarques: []}
    maj TEXT, maj_par INTEGER,
    UNIQUE (ecole_id, niveau)
);
CREATE TABLE IF NOT EXISTS synoptique_planification (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL,
    annee TEXT,
    niveau TEXT NOT NULL,
    classe_id INTEGER,
    contenu TEXT NOT NULL,                -- JSON [{trimestre, mois, francais, maths, …, observations}]
    maj TEXT, maj_par INTEGER,
    UNIQUE (ecole_id, niveau)
);
CREATE TABLE IF NOT EXISTS synoptique_planification_mensuelle (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL,
    annee TEXT,
    classe_id INTEGER NOT NULL,
    mois TEXT NOT NULL,                   -- « 2026-10 » (année-mois)
    semaines TEXT NOT NULL,               -- JSON [{du, au}] (dates ISO, 5 semaines au plus)
    contenu TEXT NOT NULL,                -- JSON {code_ligne: [case semaine 1 … case semaine 5]}
    titulaire_visa TEXT,
    directeur_visa TEXT,
    maj TEXT, maj_par INTEGER,
    UNIQUE (ecole_id, classe_id, mois)
);
CREATE TABLE IF NOT EXISTS synoptique_reglement (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL,
    ordre INTEGER DEFAULT 0,
    type TEXT NOT NULL,                   -- preambule | titre | article
    numero TEXT,
    titre TEXT,
    texte TEXT,
    maj TEXT, maj_par INTEGER
);
"""

# ================================================================ emplois du temps officiels
RECRE = "RÉCRÉATION"
INTERCLASSE = "INTERCLASSE"


def _edt(lignes, remarques, source):
    return {"lignes": [dict(zip(["horaire"] + [j for j, _ in JOURS], l)) for l in lignes],
            "remarques": remarques, "source": source}


EDT_OFFICIELS = {
    # Emploi du temps CI-CP (MEMP, septembre 2016)
    "ci_cp": _edt([
        ["08h à 10h15",
         "Cérémonial des couleurs 15 min\nES/Morale 30 min\nFrançais 45 min\nFrançais 45 min",
         "Français 45 min\nFrançais 45 min\nFrançais 45 min",
         "Français 45 min\nES Compétences 2 et 3 30 min\nFrançais 45 min",
         "Français 45 min\nEST 45 min\nFrançais 45 min",
         "Français 45 min\nFrançais 45 min\nFrançais 45 min"],
        ["10h15 à 10h30"] + [RECRE] * 5,
        ["10h30 à 12h"] + ["Math 45 min\nFrançais 45 min"] * 5,
        ["12h à 15h"] + [INTERCLASSE] * 5,
        ["15h à 16h", "EA Poésie/Chant 30 min\nES Civisme 30 min", "Français 30 min\nEA/Dessin 30 min", "",
         "EA/TM 30 min\nEA Poésie/Chant 30 min", "EST 30 min\nFrançais 30 min"],
        ["16h à 16h10", RECRE, RECRE, "", RECRE, RECRE],
        ["16h10 à 17h", "Français 50 min", "EPS 50 min", "", "Dictée 20 min\nEPS 30 min",
         "EA/Conte 40 min\nCérémonial des couleurs 10 min"],
    ], [
        "La 6ème étape d'une unité de français prévoit déjà une activité dénommée « j'écris sous la dictée » qu'il "
        "faut continuer d'exécuter en temps convenable.",
        "La dictée à trous ou la dictée muette sont à alterner pour la séance de dictée du jeudi soir.",
        "En tout état de cause, l'activité de dictée au CI s'effectue à partir de l'apprentissage systématique du français.",
    ], "Emploi du temps officiel CI-CP — MEMP, nouveaux emplois du temps portant réhabilitation de la dictée, "
       "Porto-Novo, septembre 2016"),
    # Emploi du temps CE1-CE2
    "ce1_ce2": _edt([
        ["08h à 10h15",
         "Cérémonial des couleurs 15 min\nES/Morale 30 min\nFrançais 45 min\nFrançais 45 min",
         "Français 45 min\nEST 45 min\nFrançais 45 min",
         "Dictée 45 min\nES compétences 2 et 3 (histoire et géographie) 45 min\nFrançais 45 min",
         "Français 45 min\nEST 45 min\nFrançais 45 min",
         "Français 45 min\nFrançais 45 min\nEA Couture 45 min"],
        ["10h15 à 10h30"] + [RECRE] * 5,
        ["10h30 à 12h", "Math 60 min\nES/Chant 30 min", "Math 60 min\nES Dessin 30 min", "Math 45 min\nFrançais 45 min",
         "Math 60 min\nES/Chant 30 min", "Math 60 min\nES Civisme 30 min"],
        ["12h à 15h"] + [INTERCLASSE] * 5,
        ["15h à 16h", "Français 60 min", "Français 30 min\nPoésie 30 min", "", "Français 60 min", "Dictée 60 min"],
        ["16h à 16h10", RECRE, RECRE, "", RECRE, RECRE],
        ["16h10 à 17h", "EA/TM 50 min", "EPS 50 min", "", "EPS 50 min", "EA/Conte 50 min\nCérémonial des couleurs 10 min"],
    ], [
        "Faire la dictée préparée par conclusion (elle se prépare le mercredi et s'exécute le vendredi de la même semaine).",
        "Faire les autres types de dictées de façon alternée.",
        "Exécuter obligatoirement la séance de dictée prévue à la deuxième semaine de mise en œuvre d'une unité de français.",
    ], "Emploi du temps officiel CE1-CE2 — MEMP, nouveaux emplois du temps portant réhabilitation de la dictée, "
       "Porto-Novo, septembre 2016"),
    # Emploi du temps CM1-CM2
    "cm1_cm2": _edt([
        ["08h à 10h15", "Cérémonial des couleurs 15 min\nFrançais 60 min\nFrançais 60 min",
         "Français 60 min\nFrançais 75 min", "Français 60 min\nFrançais 75 min", "Français 60 min\nFrançais 75 min",
         "Français 60 min\nFrançais 75 min"],
        ["10h15 à 10h30"] + [RECRE] * 5,
        ["10h30 à 12h", "Math 60 min\nES/Morale 30 min", "Math 60 min\nES Civisme 30 min", "Math 60 min\nEA/Dessin 30 min",
         "Math 60 min\nES/Civisme 30 min", "Math 60 min\nEA/Chant/Poésie 30 min"],
        ["12h à 15h"] + [INTERCLASSE] * 5,
        ["15h à 16h", "Dictée 60 min", "EST 60 min", "", "ES Compétences 2 et 3 60 min", "EST 60 min"],
        ["16h à 16h10", RECRE, RECRE, "", RECRE, RECRE],
        ["16h10 à 17h", "ES Compétences 2 et 3 60 min", "EPS ou EA Couture 50 min", "", "EPS 50 min",
         "EA/Conte ou EA Couture 50 min\nCérémonial des couleurs 10 min"],
    ], [
        "Alterner systématiquement les types de dictées recommandées pour la séance de dictée du lundi soir (15 à 16 h).",
        "Exécuter obligatoirement la séance de dictée de contrôle initialement prévue à la 2ème semaine de mise en œuvre "
        "d'une unité de français.",
    ], "Emploi du temps officiel CM1-CM2 — MEMP, nouveaux emplois du temps portant réhabilitation de la dictée, "
       "Porto-Novo, septembre 2016"),
    # Maternelle : section des petits (Direction de l'enseignement maternel, septembre 2012)
    "maternelle": _edt([
        ["7h45 – 8h30"] + ["D1 : Accueil, activités de vie pratique (balayage, époussetage, arrosage…)"] * 5,
        ["8h30 – 9h00", "D5 : Cérémonial des couleurs"] + ["D1 : Passage aux toilettes – Lavage des mains"] * 4,
        ["9h00 – 9h20", "D1 : Passage aux toilettes – Lavage des mains", "D2 : Expression corporelle (Éducation du mouvement)",
         "D2 : Expression corporelle (Éducation du mouvement)", "D4 : Expression émotionnelle", "D3 : Pré-lecture"],
        ["9h20 – 10h00", "D1 : Goûter"] + ["D1 : Passage aux toilettes – Lavage des mains – Goûter"] * 4,
        ["10h00 – 10h15"] + [RECRE] * 5,
        ["10h15 – 10h30"] + ["D5 : Poésie ou chant ou comptine ou devinette"] * 5,
        ["10h30 – 10h50", "D1 : Éducation pour la santé", "D3 : Observation ou éducation sensorielle",
         "D5 : Communication orale (langage)", "D3 : Pré-mathématique", "D5 : Expression orale (conte)"],
        ["10h50 – 11h20", "D3 : Pré-écriture"] + ["D5 : Activités libres (jeux libres dans les coins de vie et travaux en atelier)"] * 4,
        ["11h20 – 11h30"] + ["Mise en ordre du local – Animation – Sortie"] * 5,
        ["11h30 – 14h45"] + [INTERCLASSE] * 5,
        ["14h45 – 15h15", "D1 : Accueil – Passage aux toilettes – Lavage des mains", "D1 : Accueil – Passage aux toilettes – Lavage des mains",
         "", "D1 : Accueil – Passage aux toilettes – Lavage des mains", "D1 : Accueil – Passage aux toilettes – Lavage des mains"],
        ["15h15 – 15h50", "D1 : Repos – Activités calmes pour les non dormeurs", "D1 : Repos – Activités calmes pour les non dormeurs",
         "", "D1 : Repos – Activités calmes pour les non dormeurs", "D1 : Repos – Activités calmes pour les non dormeurs"],
        ["15h50 – 16h20", "D1 : Réveil – Passage aux toilettes – Lavage des mains – Goûter",
         "D1 : Réveil – Passage aux toilettes – Lavage des mains – Goûter", "",
         "D1 : Réveil – Passage aux toilettes – Lavage des mains – Goûter", "D1 : Réveil – Passage aux toilettes – Lavage des mains – Goûter"],
        ["16h20 – 16h40", "D4 : Expression plastique ou activités manuelles à dominante technologique",
         "D4 : Expression plastique ou activités manuelles à dominante technologique", "",
         "D4 : Expression plastique ou activités manuelles à dominante technologique",
         "D4 : Expression plastique ou activités manuelles à dominante technologique"],
        ["16h40 – 16h50", "D5 : Poésie ou chant ou comptine ou devinette", "D5 : Poésie ou chant ou comptine ou devinette", "",
         "D5 : Poésie ou chant ou comptine ou devinette", "D5 : Poésie ou chant ou comptine ou devinette"],
        ["16h50 – 17h00", "Mise en ordre du local – Animation – Sortie", "Mise en ordre du local – Animation – Sortie", "",
         "Mise en ordre du local – Animation – Sortie", "Mise en ordre du local – Animation – Sortie"],
    ], [
        "Le maître de semaine est tenu d'être à l'école à 7 heures 30 minutes.",
        "D1 à D5 : domaines d'activités de la maternelle.",
    ], "Emploi du temps officiel de la section des petits — Direction de l'enseignement maternel, septembre 2012 "
       "(appliqué à défaut aux deux sections)"),
}

# ================================================================ règlement intérieur officiel (MEMP, 26 mars 2018)
REGLEMENT_SOURCE = ("Règlement intérieur des écoles primaires révisé — République du Bénin, Ministère des Enseignements "
                    "Maternel et Primaire, N°0548/MEMP/DC/SGM/DEP/SP, fait à Porto-Novo le 26 mars 2018, "
                    "le Ministre des Enseignements Maternel et Primaire, Salimane KARIMOU")
_A = "article"
REGLEMENT_OFFICIEL = [
    ("preambule", "", "Préambule",
     "Les écoliers sont à l'école pour être instruits et préparés à devenir des citoyens accomplis aux plans physique, "
     "mental, intellectuel, moral et spirituel. Ainsi, ils deviendront des hommes et des femmes aimant leur patrie, "
     "attachés à l'intégration africaine, ouverts à l'humanité, respectueux de leurs prochains, tant du bien public que "
     "privé, de l'environnement, des règles d'hygiène et ayant le goût de l'effort, disciplinés et aimant le travail en "
     "vue d'un développement durable.\n"
     "Les enseignant(e)s et autres personnels, parents et autres acteurs sont tenus de travailler à l'atteinte de ces "
     "objectifs en traitant les écoliers en bon père de famille. Ils constituent de par leurs comportements, "
     "présentation et valeurs morales, des modèles pour leurs apprenants.\n"
     "Ils doivent travailler à instaurer dans leur école une ambiance aussi conviviale que celle de leur cadre familial "
     "afin de maintenir leurs apprenants sur les bancs jusqu'à la fin de leur cursus scolaire.\n"
     "Tous les écolier(e)s ont le droit d'être traités de façon égale, sans distinction de race, de groupe ethnique, de "
     "couleur, de sexe, de langue, de handicap, de religion, d'appartenance politique ou autre opinion de leurs parents, "
     "d'origine nationale et sociale, de fortune, de naissance ou autre statut et sans distinction du même ordre pour "
     "leurs parents ou leurs tuteurs.\n"
     "Les termes écoliers, apprenants, instituteurs, enseignants, vendeurs, citoyens, ceux utilisés dans le présent "
     "règlement intérieur désignent les deux sexes."),
    ("titre", "I", "Entrée – Sortie – Horaire – Discipline", ""),
    (_A, "1", "", "L'école ouvre ses portes les jours et heures prévus par les textes en vigueur."),
    (_A, "2", "", "Les écoliers doivent arriver 30 mn avant le début des cours et rester dans l'école pour en assurer le nettoyage."),
    (_A, "3", "", "Dès le coup de cloche, les jeux et les cris cessent immédiatement. Les écoliers se mettent en rangs sans "
     "perte de temps. Toute sortie collective doit s'effectuer sous la conduite effective de l'instituteur."),
    (_A, "4", "", "Aucun enfant ne doit être retenu par son instituteur ou autre personne dans l'école au-delà des heures "
     "réglementaires pendant plus de 30 mn. Les enfants obligés de rester à l'école à midi, pour des raisons diverses, "
     "doivent être encadrés."),
    (_A, "5", "", "Les Associations des Parents d'Élèves doivent prendre des dispositions en collaboration avec les dirigeants "
     "de l'école pour assurer la sécurité de ces enfants jusqu'à la réouverture de l'école."),
    (_A, "6", "", "Les membres de l'Association des Parents d'Élèves passent périodiquement dans l'établissement pour "
     "s'enquérir de la bonne marche des activités scolaires.\nLeur passage ne peut se faire qu'avant le démarrage des "
     "cours, pendant la récréation et à la fin des cours."),
    (_A, "7", "", "Il est formellement interdit aux écoliers de former des attroupements aux abords de l'école et d'en sortir "
     "sans autorisation.\nLes écoliers sont sous la supervision de l'instituteur de semaine qui est présent à son poste "
     "bien avant sept (7) heures trente (30) minutes."),
    (_A, "8", "", "Les écoliers sont tenus de communiquer les résultats des évaluations périodiques des apprentissages aux "
     "parents pour une action conjuguée entre ceux-ci et l'instituteur."),
    ("titre", "II", "De la protection des écoliers en situation de handicap", ""),
    (_A, "9", "", "Les écoliers handicapés doivent être particulièrement aidés et encouragés.\nLes enfants handicapés doivent "
     "être effectivement inscrits dans les registres de l'école, avec mention de leur handicap.\nCeux ayant des troubles "
     "de vision et d'audition sont disposés de manière à mieux entendre l'instituteur et bien voir au tableau."),
    (_A, "10", "", "Les écoliers handicapés désireux d'exercer des activités physiques et sportives à la hauteur de leurs "
     "conditions physiques, après avis médical, ne doivent pas être en empêchés.\nL'école prend des dispositions spéciales "
     "pour répondre à leurs besoins."),
    (_A, "11", "", "Il doit être prévu des moyens d'accessibilité aux classes pour les écoliers ayant des problèmes de "
     "mobilité.\nÀ cet effet, les dirigeants de l'école et les Associations des Parents d'Élèves veillent à ce que les "
     "nouvelles constructions de classes soient adaptées aux normes d'accessibilité et les anciennes réaménagées dans ce sens."),
    ("titre", "III", "De la protection contre les atteintes sexuelles", ""),
    (_A, "12", "", "Le Directeur et les instituteurs prennent des mesures pour protéger les enfants, en particulier, les filles "
     "contre les atteintes sexuelles.\nIl est mis un accent particulier sur les filles handicapées."),
    (_A, "13", "", "Tout instituteur ou toute personne, auteur de ces agissements doit être dénoncé simultanément aux autorités "
     "administratives et judiciaires."),
    (_A, "14", "", "Il est institué dans chaque école des mécanismes pour apprendre aux écolier(e)s, en particulier les filles "
     "à détecter et à dénoncer les atteintes sexuelles.\nÀ cet effet, les directeurs d'école, de concert avec l'Association "
     "des Parents d'Élèves mettent en place des dispositifs, y compris anonymes, de dénonciation et de protection des "
     "filles victimes d'abus sexuels."),
    (_A, "15", "", "Aucune sanction ne peut être prononcée contre l'écolier, l'enseignant ou toute autre personne dénonciateur "
     "desdits abus."),
    ("titre", "IV", "De la gratuité des enseignements maternel et primaire publics", ""),
    (_A, "16", "", "Tout établissement scolaire public, maternel ou primaire, a l'obligation d'accueillir gratuitement tout "
     "enfant remplissant les conditions d'inscription prévues par les textes en vigueur."),
    (_A, "17", "", "Il est interdit à tout responsable d'école maternelle, primaire publique d'exiger des enfants des frais de "
     "scolarité et des contributions au fonctionnement de ladite école."),
    (_A, "18", "", "Les frais relatifs à l'organisation des activités récréatives, sportives ou culturelles sont facultatifs et "
     "ne doivent donner lieu à aucun renvoi."),
    ("titre", "V", "Du décrochage et de l'orientation professionnelle", ""),
    (_A, "19", "", "Aucun écolier, à l'exception de celui présentant une déficience intellectuelle ou autre, ne peut être retiré "
     "ni exclu de l'école s'il n'a obtenu le Certificat d'Études Primaires ou s'il n'a atteint le niveau du Cours Moyen "
     "Deuxième Année."),
    (_A, "20", "", "L'écolier présentant une déficience intellectuelle ou autre, doit être orienté avec le concours de ses "
     "parents ou tuteurs et l'Association des Parents d'Élèves vers les centres spécialisés ou professionnels adaptés à "
     "sa situation."),
    (_A, "21", "", "Aucune écolière ne peut être exclue de l'école pour cause de grossesse."),
    ("titre", "VI", "De l'interdiction des châtiments corporels et traitements inhumains ou dégradants", ""),
    (_A, "22", "", "Les châtiments corporels sont formellement interdits."),
    (_A, "23", "", "Il est formellement interdit de soumettre les apprenants aux traitements inhumains et dégradants."),
    (_A, "24", "", "Les punitions autorisées dans les écoles maternelles et primaires sont :\n"
     "– la mise en garde ;\n– échanges avec l'écolier ;\n– changement de place ;\n– présentation d'excuses par le coupable ;\n"
     "– la privation partielle de récréation ;\n– recours aux parents ;\n– restitution de l'objet volé ou de la vérité ;\n"
     "– la retenue d'au plus d'une demi-heure après la classe sous la surveillance de l'instituteur ;\n"
     "– le nettoyage de la salle de classe ;\n– la copie en plusieurs exemplaires de l'exercice mal fait ;\n"
     "– la suspension temporaire prononcée par le directeur et le Bureau de l'Association des Parents d'Élèves après avis "
     "conforme du Directeur Départemental en charge des Enseignements maternel et primaire. Cette suspension ne peut "
     "dépasser trois jours ; avis en est donné aux parents de l'écolier et suivi d'explication à tous les écoliers lors du "
     "cérémonial des couleurs afin de discipliner ses pairs."),
    (_A, "25", "", "À l'exception de la suspension temporaire, aucune punition ne peut empêcher l'apprenant de suivre les "
     "cours.\nLes punitions sont exécutées aux heures creuses."),
    ("titre", "VII", "Des récompenses", ""),
    (_A, "26", "", "Les écoliers méritants peuvent recevoir les récompenses suivantes :\na) les bons points ;\n"
     "b) l'inscription au tableau d'honneur ;\nc) les félicitations de l'instituteur ;\n"
     "d) l'attribution d'une responsabilité de confiance."),
    ("titre", "VIII", "De la protection de l'environnement de l'école", ""),
    (_A, "27", "", "À l'exception des vendeurs de nourriture et de matériels didactiques agréés par le Directeur en accord avec "
     "l'Association des Parents d'Élèves, il est interdit à toute autre personne de s'installer dans l'enceinte ou aux "
     "alentours de l'école.\nToute installation non autorisée est passible de sanction."),
    (_A, "28", "", "L'Association des Parents d'Élèves veille à ce qu'il ne soit installé aux abords immédiats de l'école, des "
     "débits de boissons et de tabac, des salles de jeux, des vidéoclubs, des salles de machines à sous, des boutiques de "
     "vente de supports électroniques à caractères pornographiques, des publications, des illustrations, des récits, des "
     "chroniques, des rubriques, des insertions présentant sous un jour favorable le banditisme, le mensonge, le vol, la "
     "paresse, la lâcheté, la haine, la débauche ou tout autre actes qualifiés de crimes ou délits ou de nature à "
     "démoraliser l'enfance ou la jeunesse ou à inspirer ou à entretenir des préjugés ethiques."),
    ("titre", "IX", "Tenue vestimentaire des écolier(e)s et des restauratrices", ""),
    (_A, "29", "", "La tenue des écoliers doit être conforme à la règlementation en vigueur.\nLes restauratrices sont en "
     "uniforme et doivent protéger leurs cheveux."),
    (_A, "30", "", "Les cheveux sont modestement coiffés. Les écolières peuvent se tresser les cheveux sans extravagance."),
    ("titre", "X", "De la propreté, de l'hygiène et de l'ordre", ""),
    (_A, "31", "", "Les tenues uniformes doivent être maintenues propres. Les parents et les enseignants veillent à l'hygiène "
     "corporelle et bucco-dentaire des enfants."),
    (_A, "32", "", "L'instituteur doit servir de modèle aux écoliers de par sa tenue vestimentaire, sa coiffure, son "
     "comportement et son langage."),
    (_A, "33", "", "Il est formellement interdit de détériorer le matériel d'enseignement, les installations d'eau et "
     "d'électricité, les infrastructures, d'écrire sur les murs, de grimper sur les arbres, de cracher partout, de détruire "
     "le parterre ou d'y jeter des objets qui pourraient salir le sol. Tout objet retrouvé dans l'enceinte et aux abords "
     "immédiats de l'école doit être remis à l'instituteur."),
    (_A, "34", "", "L'enlèvement des ordures doit être soumis à une structure spécialisée en la matière ou enfouies dans un "
     "trou à ordures creusé selon les normes environnementales."),
    (_A, "35", "", "Au début de chaque année, l'instituteur est tenu d'élaborer la charte de sa classe en collaboration avec "
     "ses écoliers/écolières. Cette charte élaborée est affichée à divers endroits de la classe pour exploitation."),
    (_A, "36", "", "Tout matériel didactique appartenant à l'école doit être entretenu avec grand soin. En cas de "
     "détérioration volontaire, il est remboursé ou réparé par le parent ou le tuteur de l'écolier."),
    (_A, "37", "", "L'usage du téléphone portable aux heures de cours est formellement interdit tant aux instituteurs qu'aux "
     "écoliers."),
    (_A, "38", "", "Les sonneries et la surveillance des écolier(e)s pendant la récréation sont assurées par l'instituteur de "
     "semaine aidé des autres instituteurs de l'école et des écoliers responsables."),
    (_A, "39", "", "L'instituteur responsable de la santé et de la nutrition veille à l'animation des comités de santé de classe."),
    ("titre", "XI", "De la santé de l'écolier et des absences", ""),
    (_A, "40", "", "Tout écolier malade doit s'inscrire dans un cahier de visite médicale et se faire conduire au centre de "
     "santé. Lorsqu'un écolier se trouve dans l'impossibilité de venir à l'école en raison de maladie, de décès d'un membre "
     "de famille ou autres cas éventuels, il doit le faire savoir à son instituteur le plus tôt possible par un parent."),
    (_A, "41", "", "Chaque école doit disposer d'une trousse de premiers soins conformément aux dispositions de la politique "
     "nationale de santé scolaire et universitaire. La trousse de premiers soins doit être régulièrement approvisionnée "
     "sous le contrôle du comité de santé."),
    (_A, "42", "", "L'instituteur, les écoliers et le personnel de soutien doivent être formés sur les gestes de secourisme."),
    (_A, "43", "", "Tout enfant souffrant d'une maladie contagieuse est confié à ses parents jusqu'à la guérison totale."),
    (_A, "44", "", "La liste des écoliers absents aux cours sera transmise de façon périodique par l'administration de "
     "l'école au bureau de l'Association des Parents d'Élèves pour prise de contact avec leurs parents. Un total de cinq "
     "jours successifs d'absence sans motif valable donne lieu à un avertissement. En cas de récidive, l'écolier s'expose "
     "à l'une quelconque des sanctions prévues à l'article 24."),
    ("titre", "XII", "De la cérémonie du salut des couleurs", ""),
    (_A, "45", "", "Le salut des couleurs est obligatoire pour tous les écoliers et les usagers de l'école présents lors du "
     "cérémonial."),
    (_A, "46", "", "L'ordre, le silence, une attitude digne et révérencieuse sont observés au cours de ces cérémonies. Chaque "
     "participant met un point d'honneur à exécuter avec conviction et patriotisme l'hymne national."),
    (_A, "47", "", "Tout désordre, toute nonchalance, tout comportement tendant à perturber la cérémonie des couleurs est "
     "sanctionné."),
    ("titre", "XIII", "Des vendeuses dans l'école", ""),
    (_A, "48", "", "Sur autorisation du Directeur d'école et du bureau de l'Association des Parents d'Élèves, une ou plusieurs "
     "personnes peuvent acquérir la qualité de vendeur de mets dans l'établissement."),
    (_A, "49", "", "Toute vendeuse de mets à l'école doit se soumettre au préalable aux conditions d'hygiène et de visite "
     "médicale qu'exige la protection de la santé de l'écolier."),
    (_A, "50", "", "L'instituteur responsable des questions de santé et de nutrition en collaboration avec l'instituteur de "
     "semaine, veillent à la bonne qualité des mets, de l'eau, de boisson, de lavage des mains et des ustensiles de "
     "cuisines utilisées.\nLa stérilisation du couvert est recommandée. Cette mesure s'étend aux écoles à cantine et à "
     "l'internat."),
    (_A, "51", "", "En dehors de la bonne moralité qui est exigée avant le recrutement de vendeuse de mets dans les "
     "établissements scolaires, celles-ci doivent bénéficier d'une visite médicale annuelle et de formations périodiques "
     "en hygiène alimentaire, vestimentaire et environnementale."),
    (_A, "52", "", "Sur initiative du Chef de Circonscription Scolaire, des visites de contrôle "
     "inopiné sont organisées dans les établissements scolaires avec l'appui technique des agents de santé et d'hygiène "
     "du milieu puis le Bureau de l'Association des Parents d'Élèves et les Organisations Non Gouvernementales."),
    ("titre", "XIV", "De l'utilisation des latrines", ""),
    (_A, "53", "", "Chaque école dispose de latrines conformément aux normes École de Qualité Fondamentale et accessibles aux "
     "écoliers handicapés."),
    (_A, "54", "", "Chaque écolier fille ou garçon surpris dans les latrines du sexe opposé peut être puni."),
    ("titre", "XV", "De la solidarité et de l'esprit de groupe", ""),
    (_A, "55", "", "Tous les acteurs de l'école, doivent accorder une attention particulière aux écoliers handicapés et leur "
     "porter assistance."),
    (_A, "56", "", "L'instituteur doit encourager le soutien par les pairs et le mentorat. La solidarité entre écoliers doit "
     "être cultivée."),
    ("titre", "XVI", "Du gardien de l'école et d'autres personnels de soutien", ""),
    (_A, "57", "", "Le gardien de l'école doit être de bonne moralité et avoir une tenue vestimentaire irréprochable."),
    (_A, "58", "", "Le gardien et les autres personnels de soutien sont régulièrement informés des enjeux de la "
     "scolarisation des enfants, de la convention relative aux droits de l'enfant et de la convention relative aux droits "
     "des personnes handicapées."),
    # le texte officiel passe du titre XVI au titre XVIII (numérotation d'origine conservée)
    ("titre", "XVIII", "De l'utilisation des langues nationales", ""),
    (_A, "59", "", "L'école doit assurer la promotion et l'utilisation de nos langues nationales, de la langue des signes, de "
     "l'écriture braille."),
    ("titre", "XIX", "Des dispositions diverses", ""),
    (_A, "60", "", "Tout manquement au présent règlement intérieur est sanctionné."),
    (_A, "61", "", "Tous les cas non envisagés dans le présent règlement intérieur sont laissés à l'appréciation des "
     "autorités administratives de l'école."),
    (_A, "62", "", "Le présent règlement intérieur est lu et commenté tous les premiers mois de l'année scolaire, et chaque "
     "fois que le besoin se fait sentir.\nIl sera affiché dans les classes et porté à la connaissance des parents et autres "
     "usagers de l'école."),
    (_A, "63", "", "À l'exception de la gratuité de l'enseignement, les autres dispositions du présent règlement intérieur "
     "s'appliquent aux écoles maternelles, primaires tant du public que du privé."),
]


# ================================================================ personnel : colonnes du tableau synoptique
# (clé, libellé complet, libellé PDF abrégé, largeur PDF)
COLS_PERSONNEL = [
    ("matricule", "N° matricule", "Matri-\ncule", 9), ("nip", "NIP", "NIP", 9), ("nom_complet", "Nom et prénoms", "Nom et prénoms", 17),
    ("promotion", "Promotion", "Promo-\ntion", 7), ("categorie", "Catégorie (FE, ACDPE, ACDPCTD)", "Caté-\ngorie", 8),
    ("fonction", "Fonction (adjoint, directeur)", "Fonction", 10), ("grade", "Grade (A, B, C1-1 à 15)", "Grade", 7),
    ("indice_reel", "Indice réel", "Ind.\nréel", 6), ("indice_paye", "Indice payé", "Ind.\npayé", 6),
    ("cours_tenus", "Cours tenus", "Cours\ntenus", 8), ("anc_generale", "Ancienneté générale", "Anc.\ngén.", 8),
    ("anc_departement", "Ancienneté dans le département", "Anc.\ndép.", 8), ("anc_ecole", "Ancienneté dans l'école", "Anc.\nécole", 8),
    ("date_prise_service", "Date de première prise de service", "1re prise\nde service", 11.5),
    ("date_service_dep", "Date de prise de service dans le département", "PS dépar-\ntement", 11.5),
    ("date_service_ecole", "Date de prise de service dans l'école", "PS école", 11.5),
    ("retraite_txt", "Date de départ à la retraite", "Retraite", 11.5),
    ("date_derniere_formation", "Date de la dernière formation", "Dernière\nformation", 11.5),
    ("diplome_academique_txt", "Diplôme académique le plus élevé (année)", "Dipl.\nacad.", 11),
    ("diplome_pro_txt", "Diplôme professionnel CEAP / CAP (année)", "CEAP /\nCAP", 11),
    ("visite_aptitude", "Visite d'aptitude (oui/non)", "Apti-\ntude", 6), ("visite_aptitude_note", "Note", "Note", 6),
    ("visites_cp_ccs", "Nombre de visites CP / CCS", "Vis.\nCP/CCS", 7), ("visites_directeur", "Nombre de visites du directeur", "Vis.\ndir.", 6),
    ("participation_up", "Participation à l'UP (%)", "UP\n%", 6), ("gestion_collegiale", "Gestion collégiale", "Gestion\ncollégiale", 10),
    ("telephone", "Contact", "Contact", 11),
]
ENTETES_PERSONNEL = ["N°"] + [lib for _k, lib, _p, _w in COLS_PERSONNEL]
ENTETES_PERSONNEL_PDF = ["N°"] + [p for _k, _l, p, _w in COLS_PERSONNEL]
LARGEURS_PERSONNEL_PDF = [4] + [w for _k, _l, _p, w in COLS_PERSONNEL]
# colonnes propres au synoptique ajoutées à personnel_carriere
COLS_SYNO = ["promotion", "cours_tenus", "date_derniere_formation", "visites_directeur"]
LIB_SYNO = {"promotion": "Promotion", "cours_tenus": "Cours tenus", "date_derniere_formation": "Date de la dernière formation",
            "visites_directeur": "Nombre de visites du directeur"}
FONCTIONS = ["Directeur / directrice", "Adjoint(e)", "Enseignant(e)", "Maître de semaine", "Secrétaire", "Comptable",
             "Gardien(ne)", "Restauratrice", "Autre"]


def valeurs_personnel(f):
    """Fiche calculée (m_carriere.calculer_fiche) -> dict des valeurs texte du tableau synoptique."""
    anc = lambda k: MC.fmt_duree(f["anc"][k], True) if f["anc"].get(k) else ""   # noqa: E731
    dip = f.get("diplome_academique") or ""
    if dip and f.get("diplome_academique_annee"):
        dip += f" ({f['diplome_academique_annee']})"
    pro = " / ".join(x for x in (("CEAP " + MC.diplome_pro(f, "ceap")) if f.get("ceap") else "",
                                 ("CAP " + MC.diplome_pro(f, "cap")) if f.get("cap") else "") if x)
    vis = "" if f.get("visites_cp") is None and f.get("visites_ccs") is None else \
        f"{MC.fmt_nombre(f.get('visites_cp')) or '—'} / {MC.fmt_nombre(f.get('visites_ccs')) or '—'}"
    v = {k: (f.get(k) or "") for k, _l, _p, _w in COLS_PERSONNEL}
    v.update({
        "nom_complet": f["nom_complet"], "categorie": f.get("categorie") or "",
        "indice_reel": MC.fmt_nombre(f.get("indice_reel")), "indice_paye": MC.fmt_nombre(f.get("indice_paye")),
        "anc_generale": anc("generale"), "anc_departement": anc("departement"), "anc_ecole": anc("ecole"),
        "date_prise_service": MC.fmt_date(f.get("date_prise_service")), "date_service_dep": MC.fmt_date(f.get("date_service_dep")),
        "date_service_ecole": MC.fmt_date(f.get("date_service_ecole")), "retraite_txt": f["retraite_txt"],
        "date_derniere_formation": MC.fmt_date(f.get("date_derniere_formation")), "diplome_academique_txt": dip,
        "diplome_pro_txt": pro, "visite_aptitude_note": MC.fmt_nombre(f.get("visite_aptitude_note")),
        "visites_cp_ccs": vis, "visites_directeur": MC.fmt_nombre(f.get("visites_directeur")),
        "participation_up": MC.fmt_nombre(f.get("participation_up")),
    })
    return v


def ligne_personnel(i, f):
    v = valeurs_personnel(f)
    return [i] + [v[k] for k, _l, _p, _w in COLS_PERSONNEL]


def lignes_edt_vides(n=8):
    return [{"horaire": "", **{j: "" for j, _ in JOURS}} for _ in range(n)]


def planification_defaut(niveau):
    """Planification officielle du cours (CI → CM2) ou lignes vides par mois (maternelle)."""
    lib = NIVEAUX_LIB.get(niveau, niveau)
    if lib in PLANIFICATION_OFFICIELLE:
        return [dict(l) for l in PLANIFICATION_OFFICIELLE[lib]]
    return [{**{k: "" for k in CLES_PLAN}, "trimestre": t, "mois": m} for t, m in MOIS_SCOLAIRES]


def edt_defaut(niveau):
    return json.loads(json.dumps(EDT_OFFICIELS[GROUPE_EDT[niveau]]))


# ---------------------------------------------------------------- planification mensuelle : outils purs
def mois_valide(mois):
    """« 2026-10 » -> (2026, 10) ; None si le format est invalide."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", mois or "")
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return int(m.group(1)), int(m.group(2))


def mois_libelle(mois, majuscule=True):
    v = mois_valide(mois)
    if not v:
        return mois or ""
    lib = MOIS_LIB[v[1] - 1]
    return f"{lib.capitalize() if majuscule else lib} {v[0]}"


def mois_annee_scolaire(annee):
    """Mois de l'année scolaire « 2026-2027 » : septembre 2026 → juillet 2027, [(« 2026-09 », « Septembre 2026 »), …]."""
    m = re.match(r"(\d{4})", annee or "")
    a = int(m.group(1)) if m else date.today().year
    out = [(f"{a}-{n:02d}", mois_libelle(f"{a}-{n:02d}")) for n in range(9, 13)]
    out += [(f"{a + 1}-{n:02d}", mois_libelle(f"{a + 1}-{n:02d}")) for n in range(1, 8)]
    return out


def mois_precedent(mois):
    a, n = mois_valide(mois)
    return f"{a - 1}-12" if n == 1 else f"{a}-{n - 1:02d}"


def semaines_du_mois(mois):
    """Semaines de classe (lundi → vendredi) du mois, 5 au plus : [{du, au}] en dates ISO.
    Un mois qui commence un samedi ou un dimanche démarre au lundi suivant ; la dernière semaine s'arrête
    au dernier jour ouvré du mois."""
    from datetime import timedelta
    a, n = mois_valide(mois)
    d = date(a, n, 1)
    fin = date(a + (n == 12), (n % 12) + 1, 1) - timedelta(days=1)
    if d.weekday() >= 5:
        d += timedelta(days=7 - d.weekday())
    out = []
    while d <= fin and len(out) < NB_SEMAINES_PM:
        vendredi = d + timedelta(days=4 - d.weekday())
        out.append({"du": d.isoformat(), "au": min(vendredi, fin).isoformat()})
        d += timedelta(days=7 - d.weekday())
    while len(out) < NB_SEMAINES_PM:
        out.append({"du": "", "au": ""})
    return out


def contenu_pm_defaut():
    """Grille préremplie avec les gabarits du modèle officiel (« U…SA…S…Étape… », « SA…Séq… »…)."""
    return {code: [gab] * NB_SEMAINES_PM for code, _ch, _l1, _l2, gab in LIGNES_PM}


def normaliser_contenu_pm(contenu):
    """Toute ligne connue est présente avec exactement 5 cases (chaînes)."""
    out = {}
    for code in CODES_PM:
        cases = contenu.get(code) if isinstance(contenu, dict) else None
        cases = [str(c or "")[:300] for c in (cases or [])][:NB_SEMAINES_PM] if isinstance(cases, list) else []
        out[code] = cases + [""] * (NB_SEMAINES_PM - len(cases))
    return out


def fmt_jma(iso):
    """« 2026-10-05 » -> « 05/10/2026 » (chaîne inchangée si ce n'est pas une date ISO)."""
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""


def lire_date_iso(texte):
    """« 05/10/2026 », « 2026-10-05 » ou objet date -> ISO ; chaîne vide sinon."""
    if hasattr(texte, "strftime"):
        return texte.strftime("%Y-%m-%d")
    t = (texte or "").strip()
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", t)
    if m:
        t = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    try:
        return date.fromisoformat(t).isoformat()
    except ValueError:
        return ""


def groupes_pm():
    """Lignes regroupées par champ de formation : [(champ, [lignes])], dans l'ordre du modèle."""
    out = []
    for l in LIGNES_PM:
        if out and out[-1][0] == l[1]:
            out[-1][1].append(l)
        else:
            out.append((l[1], [l]))
    return out


# ================================================================ module Flask
_H = None


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config

    H.schema(SCHEMA)
    H.ajouter_colonne("personnel_carriere", "promotion", "TEXT")
    H.ajouter_colonne("personnel_carriere", "cours_tenus", "TEXT")
    H.ajouter_colonne("personnel_carriere", "date_derniere_formation", "TEXT")
    H.ajouter_colonne("personnel_carriere", "visites_directeur", "INTEGER")

    def uid():
        return g.user["id"] if g.get("user") else None

    def ecriture():
        if not H.peut("synoptique"):
            abort(403)

    def peut_ecrire():
        return H.peut("synoptique")

    # ------------------------------------------------------------ données : identité
    def ecole_row(ecole_id):
        r = q("SELECT * FROM ecoles WHERE id=?", (ecole_id,), un=True)
        return dict(r) if r else {}

    def identite(ecole_id=None):
        """Identité du synoptique (valeurs enregistrées, complétées par la fiche école)."""
        ecole_id = ecole_id or H.eco()
        e = ecole_row(ecole_id)
        defaut = {
            "memp": MEMP_DEFAUT, "ddemp": e.get("departement") or "", "ccs": e.get("ccs_nom") or "", "epp": e.get("nom") or "",
            "cp_zone": "", "zone_numero": e.get("zone") or "", "up": e.get("up") or "", "rup_nom": "", "corup_nom": "",
            "annee_creation": "", "dirige_par": e.get("directeur_titre") or "Directeur", "directeur_grade": "",
            "directeur_nom": e.get("directeur_nom") or "",
        }
        r = q("SELECT * FROM synoptique_identite WHERE ecole_id=?", (ecole_id,), un=True)
        d = dict(defaut)
        if r:
            for k, _lib in CHAMPS_IDENTITE:
                if r[k] not in (None, ""):
                    d[k] = r[k]
            d["maj"] = r["maj"]
        else:
            d["maj"] = None
        d["ecole_id"] = ecole_id
        d["departement"] = e.get("departement") or ""
        d["cs"] = e.get("cs") or ""
        d["commune"] = e.get("commune") or ""
        return d

    def enregistrer_identite(form):
        v = {k: (form.get(k) or "").strip()[:200] for k, _lib in CHAMPS_IDENTITE}
        err = []
        if v["annee_creation"] and not re.fullmatch(r"\d{4}", v["annee_creation"]):
            err.append("Année de création invalide (quatre chiffres).")
        if v["dirige_par"] and v["dirige_par"] not in TITRES_DIRECTION:
            err.append("« Dirigée par » : choisissez Directeur ou Directrice.")
        if err:
            return err
        cols = [k for k, _lib in CHAMPS_IDENTITE]
        ex(f"INSERT INTO synoptique_identite (ecole_id, {', '.join(cols)}, maj, maj_par) VALUES (?, {', '.join('?' * len(cols))}, ?, ?) "
           f"ON CONFLICT(ecole_id) DO UPDATE SET " + ", ".join(f"{k}=excluded.{k}" for k in cols) + ", maj=excluded.maj, maj_par=excluded.maj_par",
           [H.eco()] + [v[k] for k in cols] + [H.maintenant(), uid()])
        # cohérence avec la fiche école
        ex("UPDATE ecoles SET ccs_nom=COALESCE(NULLIF(?, ''), ccs_nom), up=COALESCE(NULLIF(?, ''), up), "
           "zone=COALESCE(NULLIF(?, ''), zone), directeur_nom=COALESCE(NULLIF(?, ''), directeur_nom), "
           "directeur_titre=COALESCE(NULLIF(?, ''), directeur_titre), nom=COALESCE(NULLIF(?, ''), nom) WHERE id=?",
           (v["ccs"], v["up"], v["zone_numero"], v["directeur_nom"], v["dirige_par"], v["epp"], H.eco()))
        H.journal("synoptique", "identité modifiée")
        return []

    # ------------------------------------------------------------ données : personnel
    def personnel(ecole_id=None, tous=False, pid=None):
        """Agents de l'école (fiches calculées par m_carriere)."""
        sql = ("SELECT p.*, c.* FROM personnel p LEFT JOIN personnel_carriere c ON c.personnel_id=p.id WHERE p.ecole_id=?")
        args = [ecole_id or H.eco()]
        if pid is not None:
            sql += " AND p.id=?"
            args.append(pid)
        elif not tous:
            sql += " AND p.actif=1"
        sql += " ORDER BY CASE WHEN p.fonction LIKE 'Direct%' THEN 0 ELSE 1 END, p.nom, p.prenoms"
        return [MC.calculer_fiche(r) for r in q(sql, args)]

    def agent_ou_404(pid):
        lst = personnel(pid=pid)
        if not lst:
            abort(404)
        return lst[0]

    def lire_agent(form, pid=None):
        """Formulaire du synoptique -> (identité, carrière, extras, erreurs)."""
        err = []
        ident = {k: (form.get(k) or "").strip() for k in ("nom", "prenoms", "sexe", "fonction", "telephone", "matricule", "email")}
        ident["nom"] = ident["nom"][:80].upper()
        ident["prenoms"] = ident["prenoms"][:120]
        ident["fonction"] = ident["fonction"][:60]
        if not ident["nom"] or not ident["prenoms"]:
            err.append("Le nom et les prénoms sont obligatoires.")
        if not ident["fonction"]:
            err.append("La fonction est obligatoire.")
        if ident["sexe"] not in ("", "M", "F"):
            err.append("Sexe invalide.")
        if ident["matricule"]:
            autre = q("SELECT id FROM personnel WHERE matricule=? AND id<>?", (ident["matricule"], pid or 0), un=True)
            if autre:
                err.append("Ce numéro matricule est déjà attribué à un autre agent.")
        car, err_car = MC.lire_formulaire(form)
        err += err_car
        extra = {"promotion": (form.get("promotion") or "").strip()[:40], "cours_tenus": (form.get("cours_tenus") or "").strip()[:60]}
        try:
            extra["date_derniere_formation"] = MC.lire_date((form.get("date_derniere_formation") or "").strip()[:20])
        except ValueError:
            extra["date_derniere_formation"] = None
            err.append("Date de la dernière formation invalide.")
        brut = (form.get("visites_directeur") or "").strip()
        extra["visites_directeur"] = None
        if brut:
            try:
                extra["visites_directeur"] = int(brut)
                if not 0 <= extra["visites_directeur"] <= 99:
                    raise ValueError
            except ValueError:
                err.append("Nombre de visites du directeur invalide (0 à 99).")
        return ident, car, extra, err

    def enregistrer_agent(pid, ident, car, extra):
        if pid:
            ex("UPDATE personnel SET nom=?, prenoms=?, sexe=?, fonction=?, telephone=?, matricule=?, email=? WHERE id=?",
               (ident["nom"], ident["prenoms"], ident["sexe"] or None, ident["fonction"], ident["telephone"] or None,
                ident["matricule"] or None, ident["email"] or None, pid))
        else:
            pid = ex("INSERT INTO personnel (nom, prenoms, sexe, fonction, telephone, matricule, email, ecole_id, actif) "
                     "VALUES (?,?,?,?,?,?,?,?,1)",
                     (ident["nom"], ident["prenoms"], ident["sexe"] or None, ident["fonction"], ident["telephone"] or None,
                      ident["matricule"] or None, ident["email"] or None, H.eco()))
        H.carriere.enregistrer(pid, car)
        ex("UPDATE personnel_carriere SET promotion=?, cours_tenus=?, date_derniere_formation=?, visites_directeur=? WHERE personnel_id=?",
           (extra["promotion"] or None, extra["cours_tenus"] or None, extra["date_derniere_formation"], extra["visites_directeur"], pid))
        return pid

    # ------------------------------------------------------------ données : comités, EDT, planification, règlement
    def classes_ecole(ecole_id=None):
        return [dict(c) for c in q("SELECT * FROM classes WHERE ecole_id=? ORDER BY nom", (ecole_id or H.eco(),))]

    def membres(comite, classe_id=None, ecole_id=None):
        sql = "SELECT * FROM synoptique_membres WHERE ecole_id=? AND comite=?"
        args = [ecole_id or H.eco(), comite]
        if comite == "classe":
            sql += " AND classe_id=?"
            args.append(classe_id)
        return [dict(m) for m in q(sql + " ORDER BY ordre, id", args)]

    def lire_membre(form):
        v = {"nom_prenoms": (form.get("nom_prenoms") or "").strip()[:120], "qualite": (form.get("qualite") or "").strip()[:60],
             "origine": (form.get("origine") or "").strip()[:60], "contact": (form.get("contact") or "").strip()[:60],
             "observations": (form.get("observations") or "").strip()[:300]}
        brut = (form.get("ordre") or "").strip()
        v["ordre"] = int(brut) if brut.isdigit() else 0
        err = [] if v["nom_prenoms"] else ["Le nom et les prénoms du membre sont obligatoires."]
        return v, err

    def edt(niveau, ecole_id=None):
        """Emploi du temps du cours (créé à la première ouverture à partir de l'emploi du temps officiel)."""
        ecole_id = ecole_id or H.eco()
        r = q("SELECT * FROM synoptique_edt WHERE ecole_id=? AND niveau=?", (ecole_id, niveau), un=True)
        if r:
            d = json.loads(r["contenu"])
            d["maj"] = r["maj"]
            d["officiel"] = False
            return d
        d = edt_defaut(niveau)
        d["maj"] = None
        d["officiel"] = True
        return d

    def enregistrer_edt(niveau, contenu, detail="emploi du temps modifié"):
        ex("INSERT INTO synoptique_edt (ecole_id, niveau, contenu, maj, maj_par) VALUES (?,?,?,?,?) "
           "ON CONFLICT(ecole_id, niveau) DO UPDATE SET contenu=excluded.contenu, maj=excluded.maj, maj_par=excluded.maj_par",
           (H.eco(), niveau, json.dumps(contenu, ensure_ascii=False), H.maintenant(), uid()))
        H.journal("synoptique", f"{detail} ({NIVEAUX_LIB[niveau]})")

    def lire_edt(form):
        lignes, remarques = [], []
        n = int(form.get("nb_lignes") or 0)
        for i in range(n):
            l = {"horaire": (form.get(f"h_{i}") or "").strip()[:40]}
            for j, _lib in JOURS:
                l[j] = (form.get(f"c_{i}_{j}") or "").strip()[:400]
            if l["horaire"] or any(l[j] for j, _ in JOURS):
                lignes.append(l)
        for ligne in (form.get("remarques") or "").splitlines():
            if ligne.strip():
                remarques.append(ligne.strip()[:400])
        return {"lignes": lignes, "remarques": remarques, "source": (form.get("source") or "").strip()[:300]}

    def planification(niveau, ecole_id=None):
        ecole_id = ecole_id or H.eco()
        r = q("SELECT * FROM synoptique_planification WHERE ecole_id=? AND niveau=?", (ecole_id, niveau), un=True)
        if r:
            return {"lignes": json.loads(r["contenu"]), "maj": r["maj"], "officiel": False}
        return {"lignes": planification_defaut(niveau), "maj": None, "officiel": NIVEAUX_LIB[niveau] in PLANIFICATION_OFFICIELLE}

    def enregistrer_planification(niveau, lignes, detail="planification modifiée"):
        ex("INSERT INTO synoptique_planification (ecole_id, annee, niveau, contenu, maj, maj_par) VALUES (?,?,?,?,?,?) "
           "ON CONFLICT(ecole_id, niveau) DO UPDATE SET contenu=excluded.contenu, annee=excluded.annee, maj=excluded.maj, maj_par=excluded.maj_par",
           (H.eco(), config.ANNEE_ACTIVE, niveau, json.dumps(lignes, ensure_ascii=False), H.maintenant(), uid()))
        H.journal("synoptique", f"{detail} ({NIVEAUX_LIB[niveau]})")

    def lire_planification(form):
        lignes = []
        n = int(form.get("nb_lignes") or 0)
        for i in range(n):
            l = {k: (form.get(f"p_{i}_{k}") or "").strip()[:500] for k in CLES_PLAN}
            if any(l[k] for k in CLES_PLAN if k != "trimestre"):
                lignes.append(l)
        return lignes

    def reglement(ecole_id=None):
        """Articles du règlement de l'école ; le règlement officiel est inséré à la première ouverture."""
        ecole_id = ecole_id or H.eco()
        lst = q("SELECT * FROM synoptique_reglement WHERE ecole_id=? ORDER BY ordre, id", (ecole_id,))
        if not lst and ecole_id == H.eco():
            retablir_reglement(journal=False)
            lst = q("SELECT * FROM synoptique_reglement WHERE ecole_id=? ORDER BY ordre, id", (ecole_id,))
        return [dict(r) for r in lst]

    def retablir_reglement(journal=True):
        ex("DELETE FROM synoptique_reglement WHERE ecole_id=?", (H.eco(),))
        for i, (typ, num, titre, texte) in enumerate(REGLEMENT_OFFICIEL, 1):
            ex("INSERT INTO synoptique_reglement (ecole_id, ordre, type, numero, titre, texte, maj, maj_par) VALUES (?,?,?,?,?,?,?,?)",
               (H.eco(), i * 10, typ, num, titre, texte, H.maintenant(), uid()))
        if journal:
            H.journal("synoptique", "règlement intérieur officiel rétabli")

    def lire_article(form):
        v = {"type": form.get("type") if form.get("type") in TYPES_REGLEMENT else "article",
             "numero": (form.get("numero") or "").strip()[:10], "titre": (form.get("titre") or "").strip()[:200],
             "texte": (form.get("texte") or "").strip()[:6000]}
        brut = (form.get("ordre") or "").strip()
        v["ordre"] = int(brut) if brut.isdigit() else 0
        err = []
        if v["type"] == "titre" and not v["titre"]:
            err.append("Un titre doit avoir un intitulé.")
        if v["type"] != "titre" and not v["texte"]:
            err.append("Le texte est obligatoire.")
        return v, err

    # ------------------------------------------------------------ données : planification mensuelle (CE-CM)
    def classes_pm(ecole_id=None):
        """Classes du primaire (CI → CM2) de l'école ; un enseignant ne voit que ses classes affectées."""
        if ecole_id in (None, H.eco()) and g.get("user") and g.user["role"] == "enseignant":
            cls = [dict(c) for c in H.classes_autorisees()]
        else:
            cls = classes_ecole(ecole_id)
        return [c for c in cls if (c.get("niveau") or "").upper() in NIVEAUX_PM]

    def classe_pm_ou_404(cid):
        c = next((c for c in classes_pm() if c["id"] == cid), None)
        if not c:
            abort(404)
        return c

    def peut_ecrire_pm(cl):
        """Droit `synoptique`, ou enseignant titulaire (classe affectée)."""
        if H.peut("synoptique"):
            return True
        return bool(cl and g.get("user") and g.user["role"] == "enseignant"
                    and cl["id"] in {c["id"] for c in H.classes_autorisees()})

    def ecriture_pm(cl):
        if not peut_ecrire_pm(cl):
            abort(403)

    def mois_pm_ou_404(mois):
        if not mois_valide(mois):
            abort(404)
        return mois

    def pm_dict(r):
        d = dict(r)
        try:
            sem = json.loads(d.get("semaines") or "[]")
        except ValueError:
            sem = []
        sem = [{"du": s.get("du") or "", "au": s.get("au") or ""} for s in sem if isinstance(s, dict)][:NB_SEMAINES_PM]
        d["semaines"] = sem + [{"du": "", "au": ""}] * (NB_SEMAINES_PM - len(sem))
        try:
            d["contenu"] = normaliser_contenu_pm(json.loads(d.get("contenu") or "{}"))
        except ValueError:
            d["contenu"] = normaliser_contenu_pm({})
        d["mois_lib"] = mois_libelle(d["mois"])
        d["titulaire_visa"] = d.get("titulaire_visa") or ""
        d["directeur_visa"] = d.get("directeur_visa") or ""
        return d

    def pm_row(cid, mois, ecole_id=None):
        r = q("SELECT * FROM synoptique_planification_mensuelle WHERE ecole_id=? AND classe_id=? AND mois=?",
              (ecole_id or H.eco(), cid, mois), un=True)
        return pm_dict(r) if r else None

    def pm_vierge(mois):
        return {"id": None, "mois": mois, "mois_lib": mois_libelle(mois), "semaines": semaines_du_mois(mois),
                "contenu": contenu_pm_defaut(), "titulaire_visa": "", "directeur_visa": "", "maj": None}

    def enregistrer_pm(cl, mois, d, detail="planification mensuelle modifiée"):
        ex("INSERT INTO synoptique_planification_mensuelle (ecole_id, annee, classe_id, mois, semaines, contenu, titulaire_visa, "
           "directeur_visa, maj, maj_par) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ecole_id, classe_id, mois) DO UPDATE SET "
           "annee=excluded.annee, semaines=excluded.semaines, contenu=excluded.contenu, titulaire_visa=excluded.titulaire_visa, "
           "directeur_visa=excluded.directeur_visa, maj=excluded.maj, maj_par=excluded.maj_par",
           (H.eco(), config.ANNEE_ACTIVE, cl["id"], mois, json.dumps(d["semaines"], ensure_ascii=False),
            json.dumps(normaliser_contenu_pm(d["contenu"]), ensure_ascii=False), (d.get("titulaire_visa") or "")[:120],
            (d.get("directeur_visa") or "")[:120], H.maintenant(), uid()))
        H.journal("synoptique", f"{detail} ({cl['nom']}, {mois_libelle(mois)})")

    def lire_pm(form):
        """Formulaire de la grille -> (données, erreurs)."""
        err = []
        semaines = []
        for i in range(NB_SEMAINES_PM):
            du, au = lire_date_iso(form.get(f"du_{i}")), lire_date_iso(form.get(f"au_{i}"))
            if (form.get(f"du_{i}") or "").strip() and not du:
                err.append(f"Semaine {i + 1} : date de début invalide.")
            if (form.get(f"au_{i}") or "").strip() and not au:
                err.append(f"Semaine {i + 1} : date de fin invalide.")
            if du and au and au < du:
                err.append(f"Semaine {i + 1} : la fin précède le début.")
            semaines.append({"du": du, "au": au})
        contenu = {code: [(form.get(f"c_{code}_{i}") or "").strip()[:300] for i in range(NB_SEMAINES_PM)] for code in CODES_PM}
        d = {"semaines": semaines, "contenu": contenu, "titulaire_visa": (form.get("titulaire_visa") or "").strip()[:120],
             "directeur_visa": (form.get("directeur_visa") or "").strip()[:120]}
        return d, err

    def mois_courant():
        """Mois du jour s'il appartient à l'année scolaire active, sinon son premier mois."""
        lst = [m for m, _l in mois_annee_scolaire(config.ANNEE_ACTIVE)]
        auj = date.today().strftime("%Y-%m")
        return auj if auj in lst else lst[0]

    def planification_mensuelle(ecole_id, annee, classe_id):
        """Planifications mensuelles d'une classe pour une année scolaire (liste de dicts, par mois croissant)."""
        return [pm_dict(r) for r in q("SELECT * FROM synoptique_planification_mensuelle WHERE ecole_id=? AND annee=? AND classe_id=? ORDER BY mois",
                                      (ecole_id, annee, classe_id))]

    H.planification_mensuelle = planification_mensuelle

    # ---- interface pour les autres modules (transmission à la CS…)
    def synoptique_identite(ecole_id):
        d = identite(ecole_id)
        return [{"cle": k, "libelle": lib, "valeur": d.get(k) or ""} for k, lib in CHAMPS_IDENTITE]

    def synoptique_personnel(ecole_id):
        return [valeurs_personnel(f) for f in personnel(ecole_id)]

    H.synoptique_identite = synoptique_identite
    H.synoptique_personnel = synoptique_personnel
    global _H
    _H = H          # référence pour les tests et les scripts (H.synoptique_identite / H.synoptique_personnel)

    # ------------------------------------------------------------ contexte commun aux gabarits
    def ctx(onglet, **extra):
        return dict(onglet=onglet, ecrire=peut_ecrire(), NIVEAUX=NIVEAUX, NIVEAUX_LIB=NIVEAUX_LIB, COMITES=COMITES,
                    JOURS=JOURS, ident=identite(), fmt_date=MC.fmt_date, **extra)

    # ============================================================ identité
    @app.route("/synoptique")
    @H.connexion_requise()
    def synoptique_accueil():
        d = identite()
        stats = {"personnel": len(personnel()), "classes": len(classes_ecole()),
                 "comites": {c: q("SELECT COUNT(*) n FROM synoptique_membres WHERE ecole_id=? AND comite=?", (H.eco(), c), un=True)["n"]
                             for c in COMITES}}
        return render_template("synoptique_identite.html", **ctx("identite", d=d, champs=CHAMPS_IDENTITE, stats=stats,
                                                                  titres=TITRES_DIRECTION, grades=MC.GRADES, reference=MC.date_reference()))

    @app.route("/synoptique/identite", methods=["POST"])
    @H.connexion_requise("synoptique")
    def synoptique_identite_post():
        err = enregistrer_identite(request.form)
        for m in err:
            flash(m, "danger")
        if not err:
            flash("Identité de l'école enregistrée.", "success")
        return redirect(url_for("synoptique_accueil"))

    # ============================================================ personnel
    @app.route("/synoptique/personnel")
    @H.connexion_requise()
    def synoptique_personnel_liste():
        tous = request.args.get("tous") == "1"
        lst = personnel(tous=tous)
        return render_template("synoptique_personnel.html", **ctx("personnel", lst=lst, lignes=[(f, valeurs_personnel(f)) for f in lst],
                                                                  cols=COLS_PERSONNEL, tous=tous, reference=MC.date_reference(),
                                                                  ages=MC.AGES_RETRAITE))

    @app.route("/synoptique/personnel/<int:pid>", methods=["GET", "POST"])
    @H.connexion_requise("synoptique")
    def synoptique_personnel_form(pid):
        f = agent_ou_404(pid) if pid else None
        if request.method == "POST":
            ident, car, extra, err = lire_agent(request.form, pid or None)
            if err:
                for m in err:
                    flash(m, "danger")
                v = dict(request.form)
            else:
                nouveau = enregistrer_agent(pid or None, ident, car, extra)
                H.journal("synoptique", f"personnel {'modifié' if pid else 'ajouté'} : {ident['nom']} {ident['prenoms']}")
                flash("Agent enregistré.", "success")
                if request.form.get("suivant"):
                    return redirect(url_for("synoptique_personnel_form", pid=0))
                return redirect(url_for("synoptique_personnel_liste", _anchor=f"agent-{nouveau}"))
        else:
            v = dict(f) if f else {}
            if v.get("date_naissance") and "-" in str(v["date_naissance"]):
                v["date_naissance"] = MC.fmt_date(v["date_naissance"])
        return render_template("synoptique_personnel_form.html",
                               **ctx("personnel", f=f, v=v, fonctions=FONCTIONS, categories=MC.CATEGORIES, grades=MC.GRADES,
                                     diplomes=MC.DIPLOMES, departements=MC.DEPARTEMENTS, lib=MC.LIBELLES, lib_syno=LIB_SYNO,
                                     reference=MC.date_reference(), ages=MC.AGES_RETRAITE)), (400 if request.method == "POST" else 200)

    @app.route("/synoptique/personnel/<int:pid>/retirer", methods=["POST"])
    @H.connexion_requise("synoptique")
    def synoptique_personnel_retirer(pid):
        f = agent_ou_404(pid)
        ex("UPDATE personnel SET actif=0 WHERE id=?", (pid,))
        H.journal("synoptique", f"personnel retiré du tableau : {f['nom_complet']}")
        flash(f"{f['nom_complet']} retiré(e) du tableau du personnel (la fiche est conservée, désactivée).", "warning")
        return redirect(url_for("synoptique_personnel_liste"))

    @app.route("/synoptique/personnel/<int:pid>/reactiver", methods=["POST"])
    @H.connexion_requise("synoptique")
    def synoptique_personnel_reactiver(pid):
        f = agent_ou_404(pid)
        ex("UPDATE personnel SET actif=1 WHERE id=?", (pid,))
        H.journal("synoptique", f"personnel réactivé : {f['nom_complet']}")
        flash(f"{f['nom_complet']} de nouveau dans le tableau du personnel.", "success")
        return redirect(url_for("synoptique_personnel_liste", tous=1))

    # ============================================================ comités
    def comite_ou_404(comite):
        if comite not in COMITES:
            abort(404)
        return COMITES[comite]

    def classe_courante(comite):
        if comite != "classe":
            return None
        cls = classes_ecole()
        brut = request.args.get("classe_id") or request.form.get("classe_id") or ""
        cid = int(brut) if brut.isdigit() else (cls[0]["id"] if cls else None)
        c = next((x for x in cls if x["id"] == cid), None)
        if cid and not c:
            abort(404)
        return c

    @app.route("/synoptique/comites")
    @app.route("/synoptique/comites/<comite>")
    @H.connexion_requise()
    def synoptique_comites(comite="sante"):
        lib = comite_ou_404(comite)
        cl = classe_courante(comite)
        lst = membres(comite, cl["id"] if cl else None)
        return render_template("synoptique_comites.html", **ctx("comites", comite=comite, lib=lib, lst=lst, cl=cl, cls=classes_ecole()))

    @app.route("/synoptique/comites/<comite>/membre/<int:mid>", methods=["GET", "POST"])
    @H.connexion_requise("synoptique")
    def synoptique_membre_form(comite, mid):
        lib = comite_ou_404(comite)
        cl = classe_courante(comite)
        if comite == "classe" and not cl:
            flash("Créez d'abord une classe pour y constituer un comité de classe.", "warning")
            return redirect(url_for("synoptique_comites", comite=comite))
        m = None
        if mid:
            m = q("SELECT * FROM synoptique_membres WHERE id=? AND ecole_id=? AND comite=?", (mid, H.eco(), comite), un=True)
            if not m:
                abort(404)
            m = dict(m)
        if request.method == "POST":
            v, err = lire_membre(request.form)
            if err:
                for e_ in err:
                    flash(e_, "danger")
                return render_template("synoptique_membre_form.html", **ctx("comites", comite=comite, lib=lib, m=m, v=v, cl=cl,
                                                                             qualites=QUALITES, origines=ORIGINES)), 400
            if mid:
                ex("UPDATE synoptique_membres SET nom_prenoms=?, qualite=?, origine=?, contact=?, observations=?, ordre=?, maj=?, maj_par=? WHERE id=?",
                   (v["nom_prenoms"], v["qualite"], v["origine"], v["contact"], v["observations"], v["ordre"], H.maintenant(), uid(), mid))
            else:
                ex("INSERT INTO synoptique_membres (ecole_id, annee, comite, classe_id, ordre, nom_prenoms, qualite, origine, contact, observations, maj, maj_par) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (H.eco(), config.ANNEE_ACTIVE, comite, cl["id"] if cl else None, v["ordre"], v["nom_prenoms"], v["qualite"],
                    v["origine"], v["contact"], v["observations"], H.maintenant(), uid()))
            H.journal("synoptique", f"{lib} : membre {'modifié' if mid else 'ajouté'} ({v['nom_prenoms']})")
            flash("Membre enregistré.", "success")
            return redirect(url_for("synoptique_comites", comite=comite, classe_id=cl["id"] if cl else None))
        return render_template("synoptique_membre_form.html", **ctx("comites", comite=comite, lib=lib, m=m, v=m or {}, cl=cl,
                                                                     qualites=QUALITES, origines=ORIGINES))

    @app.route("/synoptique/comites/<comite>/membre/<int:mid>/supprimer", methods=["POST"])
    @H.connexion_requise("synoptique")
    def synoptique_membre_supprimer(comite, mid):
        lib = comite_ou_404(comite)
        m = q("SELECT * FROM synoptique_membres WHERE id=? AND ecole_id=? AND comite=?", (mid, H.eco(), comite), un=True)
        if not m:
            abort(404)
        ex("DELETE FROM synoptique_membres WHERE id=?", (mid,))
        H.journal("synoptique", f"{lib} : membre supprimé ({m['nom_prenoms']})")
        flash("Membre supprimé.", "warning")
        return redirect(url_for("synoptique_comites", comite=comite, classe_id=m["classe_id"]))

    # ============================================================ emplois du temps
    def niveau_ou_404(niveau):
        if niveau not in NIVEAUX_LIB:
            abort(404)
        return NIVEAUX_LIB[niveau]

    @app.route("/synoptique/edt")
    @app.route("/synoptique/edt/<niveau>")
    @H.connexion_requise()
    def synoptique_edt(niveau="ci"):
        lib = niveau_ou_404(niveau)
        d = edt(niveau)
        return render_template("synoptique_edt.html", **ctx("edt", niveau=niveau, lib=lib, d=d, RECRE=RECRE, INTERCLASSE=INTERCLASSE))

    @app.route("/synoptique/edt/<niveau>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("synoptique")
    def synoptique_edt_form(niveau):
        lib = niveau_ou_404(niveau)
        if request.method == "POST":
            d = lire_edt(request.form)
            if not d["lignes"]:
                flash("L'emploi du temps ne contient aucune ligne.", "danger")
                return redirect(url_for("synoptique_edt_form", niveau=niveau))
            enregistrer_edt(niveau, d)
            flash(f"Emploi du temps {lib} enregistré.", "success")
            return redirect(url_for("synoptique_edt", niveau=niveau))
        d = edt(niveau)
        d["lignes"] = d["lignes"] + lignes_edt_vides(2)
        return render_template("synoptique_edt_form.html", **ctx("edt", niveau=niveau, lib=lib, d=d))

    @app.route("/synoptique/edt/<niveau>/reinitialiser", methods=["POST"])
    @H.connexion_requise("synoptique")
    def synoptique_edt_reinit(niveau):
        lib = niveau_ou_404(niveau)
        enregistrer_edt(niveau, edt_defaut(niveau), "emploi du temps officiel rétabli")
        flash(f"Emploi du temps officiel {lib} rétabli.", "success")
        return redirect(url_for("synoptique_edt", niveau=niveau))

    # ============================================================ planification
    @app.route("/synoptique/planification")
    @app.route("/synoptique/planification/<niveau>")
    @H.connexion_requise()
    def synoptique_planification(niveau="ci"):
        lib = niveau_ou_404(niveau)
        d = planification(niveau)
        return render_template("synoptique_planification.html", **ctx("planification", niveau=niveau, lib=lib, d=d, cols=COLS_PLAN))

    @app.route("/synoptique/planification/<niveau>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("synoptique")
    def synoptique_planification_form(niveau):
        lib = niveau_ou_404(niveau)
        if request.method == "POST":
            lignes = lire_planification(request.form)
            if request.form.get("action") == "ajouter":
                lignes.append({k: "" for k in CLES_PLAN})
                enregistrer_planification(niveau, lignes, "ligne de planification ajoutée")
                return redirect(url_for("synoptique_planification_form", niveau=niveau, _anchor="fin"))
            enregistrer_planification(niveau, lignes)
            flash(f"Planification {lib} enregistrée.", "success")
            return redirect(url_for("synoptique_planification", niveau=niveau))
        d = planification(niveau)
        return render_template("synoptique_planification_form.html", **ctx("planification", niveau=niveau, lib=lib, d=d, cols=COLS_PLAN,
                                                                           CLES=CLES_PLAN))

    @app.route("/synoptique/planification/<niveau>/reinitialiser", methods=["POST"])
    @H.connexion_requise("synoptique")
    def synoptique_planification_reinit(niveau):
        lib = niveau_ou_404(niveau)
        enregistrer_planification(niveau, planification_defaut(niveau), "planification officielle rétablie")
        flash(f"Planification de référence {lib} rétablie.", "success")
        return redirect(url_for("synoptique_planification", niveau=niveau))

    @app.route("/synoptique/planification/<niveau>/import", methods=["POST"])
    @H.connexion_requise("synoptique")
    def synoptique_planification_import(niveau):
        lib = niveau_ou_404(niveau)
        fichier = request.files.get("fichier")
        if not fichier or not fichier.filename:
            flash("Choisissez un fichier Excel.", "danger")
            return redirect(url_for("synoptique_planification", niveau=niveau))
        try:
            entetes, lignes = H.xlsx.lire_tableau(fichier, mots_entete=("mois",))
        except (ValueError, H.xlsx.ExcelIndisponible) as e_:
            flash(str(e_), "danger")
            return redirect(url_for("synoptique_planification", niveau=niveau))
        idx = {k: H.xlsx.colonne(entetes, lib_, k) for k, lib_, _g in COLS_PLAN}
        if idx["mois"] is None:
            flash("Colonne « Mois » introuvable dans le fichier.", "danger")
            return redirect(url_for("synoptique_planification", niveau=niveau))
        out = []
        for l in lignes:
            d = {k: H.xlsx.valeur(l, idx[k])[:500] for k in CLES_PLAN}
            if any(d[k] for k in CLES_PLAN if k != "trimestre"):
                out.append(d)
        if not out:
            flash("Aucune ligne de planification trouvée dans le fichier.", "danger")
            return redirect(url_for("synoptique_planification", niveau=niveau))
        enregistrer_planification(niveau, out, "planification importée")
        flash(f"Planification {lib} importée : {len(out)} ligne(s).", "success")
        return redirect(url_for("synoptique_planification", niveau=niveau))

    # ============================================================ planification mensuelle (CE-CM)
    PM = "/synoptique/planification-mensuelle"

    def retour_pm(cl, mois):
        return redirect(url_for("synoptique_planification_mensuelle", classe=cl["id"] if cl else None, mois=mois))

    def ctx_pm(cl, mois, **extra):
        return ctx("planification_mensuelle", cl=cl, cls=classes_pm(), mois=mois, mois_lib=mois_libelle(mois),
                   MOIS=mois_annee_scolaire(config.ANNEE_ACTIVE), GROUPES=groupes_pm(), SEMAINES=SEMAINES_PM, NB=NB_SEMAINES_PM,
                   fmt_jma=fmt_jma, ecrire_pm=peut_ecrire_pm(cl), **extra)

    @app.route(PM)
    @H.connexion_requise()
    def synoptique_planification_mensuelle():
        cls = classes_pm()
        mois = mois_pm_ou_404(request.args.get("mois") or mois_courant())
        cid = request.args.get("classe", type=int)
        cl = next((c for c in cls if c["id"] == cid), None) or (cls[0] if cls else None)
        d = pm_row(cl["id"], mois) if cl else None
        existe = d is not None
        if cl and not d:
            d = pm_vierge(mois)
        precedent = pm_row(cl["id"], mois_precedent(mois)) if cl else None
        faits = {r["mois"] for r in q("SELECT mois FROM synoptique_planification_mensuelle WHERE ecole_id=? AND classe_id=?",
                                      (H.eco(), cl["id"] if cl else 0))}
        return render_template("synoptique_planification_mensuelle.html",
                               **ctx_pm(cl, mois, d=d, existe=existe, precedent=precedent, faits=faits))

    @app.route(PM + "/<int:cid>/<mois>/modifier", methods=["GET", "POST"])
    @H.connexion_requise()
    def synoptique_planification_mensuelle_form(cid, mois):
        cl = classe_pm_ou_404(cid)
        mois_pm_ou_404(mois)
        ecriture_pm(cl)
        existant = pm_row(cid, mois)
        if request.method == "POST":
            d, err = lire_pm(request.form)
            if err:
                for e_ in err:
                    flash(e_, "danger")
                d.update(id=existant["id"] if existant else None, mois=mois, mois_lib=mois_libelle(mois), maj=None)
                return render_template("synoptique_planification_mensuelle_form.html", **ctx_pm(cl, mois, d=d, existe=existant is not None)), 400
            enregistrer_pm(cl, mois, d, "planification mensuelle modifiée" if existant else "planification mensuelle créée")
            flash(f"Planification mensuelle {cl['nom']} — {mois_libelle(mois)} enregistrée.", "success")
            return retour_pm(cl, mois)
        d = existant or pm_vierge(mois)
        return render_template("synoptique_planification_mensuelle_form.html", **ctx_pm(cl, mois, d=d, existe=existant is not None))

    @app.route(PM + "/<int:cid>/<mois>/supprimer", methods=["POST"])
    @H.connexion_requise()
    def synoptique_planification_mensuelle_supprimer(cid, mois):
        cl = classe_pm_ou_404(cid)
        mois_pm_ou_404(mois)
        ecriture_pm(cl)
        ex("DELETE FROM synoptique_planification_mensuelle WHERE ecole_id=? AND classe_id=? AND mois=?", (H.eco(), cid, mois))
        H.journal("synoptique", f"planification mensuelle supprimée ({cl['nom']}, {mois_libelle(mois)})")
        flash(f"Planification mensuelle {cl['nom']} — {mois_libelle(mois)} supprimée.", "success")
        return retour_pm(cl, mois)

    @app.route(PM + "/<int:cid>/<mois>/dupliquer", methods=["POST"])
    @H.connexion_requise()
    def synoptique_planification_mensuelle_dupliquer(cid, mois):
        """Copie la grille du mois précédent (cases et visas) ; les semaines sont celles du mois cible."""
        cl = classe_pm_ou_404(cid)
        mois_pm_ou_404(mois)
        ecriture_pm(cl)
        prec = pm_row(cid, mois_precedent(mois))
        if not prec:
            flash(f"Aucune planification enregistrée pour {mois_libelle(mois_precedent(mois))} ({cl['nom']}).", "danger")
            return retour_pm(cl, mois)
        d = {"semaines": semaines_du_mois(mois), "contenu": prec["contenu"], "titulaire_visa": prec["titulaire_visa"],
             "directeur_visa": prec["directeur_visa"]}
        enregistrer_pm(cl, mois, d, f"planification mensuelle dupliquée depuis {mois_libelle(mois_precedent(mois))}")
        flash(f"Planification de {mois_libelle(mois_precedent(mois))} copiée vers {mois_libelle(mois)} : adaptez les cases.", "success")
        return redirect(url_for("synoptique_planification_mensuelle_form", cid=cid, mois=mois))

    @app.route(PM + "/<int:cid>/<mois>/reinitialiser", methods=["POST"])
    @H.connexion_requise()
    def synoptique_planification_mensuelle_reinit(cid, mois):
        cl = classe_pm_ou_404(cid)
        mois_pm_ou_404(mois)
        ecriture_pm(cl)
        enregistrer_pm(cl, mois, pm_vierge(mois), "planification mensuelle réinitialisée (gabarits)")
        flash(f"Grille {cl['nom']} — {mois_libelle(mois)} réinitialisée avec les gabarits du modèle officiel.", "success")
        return retour_pm(cl, mois)

    # ---- PDF (modèle officiel, 1 page paysage)
    def pdf_pm(cl, d):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        W, Hh = landscape(A4)
        marge = 10 * mm
        utile = W - 2 * marge
        ident = identite()
        idc = H.identification(cl)
        st = ParagraphStyle("pm", fontName="Helvetica", fontSize=7, leading=8.4)
        st_g = ParagraphStyle("pmg", parent=st, fontName="Helvetica-Bold")
        st_c = ParagraphStyle("pmc", parent=st_g, alignment=1)
        st_t = ParagraphStyle("pmt", fontName="Helvetica-Bold", fontSize=9, leading=12)
        st_gab = ParagraphStyle("pmv", parent=st, textColor=colors.HexColor("#667085"))
        gabarits = {gab for _c, _ch, _l1, _l2, gab in LIGNES_PM if gab}

        def esc(v):
            return ("" if v is None else str(v)).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")

        def cell(v, s=st):
            return Paragraph(esc(v), s)

        def pts(t):
            return t if t else "…………………"

        tete = Table([[cell(f"CIRCONSCRIPTION SCOLAIRE DE {pts(ident['cs'])}", st_t),
                       cell(f"PLANIFICATION (CE-CM) DU MOIS DE : {d['mois_lib'].upper()}", st_t)],
                      [cell(f"ÉCOLE PRIMAIRE {pts(ident['epp'])}", st_t), cell(f"COURS : {cl['niveau']} — {cl['nom']}", st_t)]],
                     colWidths=[utile * 0.6, utile * 0.4])
        tete.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        largeurs = [22 * mm, 33 * mm, 40 * mm] + [(utile - 95 * mm) / NB_SEMAINES_PM] * NB_SEMAINES_PM
        data = [[cell("CHAMPS DE FORMATION", st_c), "", ""] + [cell(s, st_c) for s in SEMAINES_PM],
                ["", cell("1ère semaine", st_c), cell("2ème semaine", st_c)]
                + [cell(f"Du {fmt_jma(s['du']) or '………'} au {fmt_jma(s['au']) or '………'}", st_g) for s in d["semaines"]]]
        style = [("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("BOX", (0, 0), (-1, -1), 0.9, colors.black),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
                 ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
                 ("SPAN", (0, 0), (2, 0)), ("SPAN", (0, 1), (0, 1))]
        r = 2
        for champ, lignes in groupes_pm():
            debut = r
            for code, _ch, l1, l2, _gab in lignes:
                cases = d["contenu"].get(code, [""] * NB_SEMAINES_PM)
                ligne = [cell(champ, st_c) if r == debut else ""]
                if l1 is None:                       # champ sur une seule ligne (maths, EST, EPS)
                    ligne += ["", ""]
                    style.append(("SPAN", (0, r), (2, r)))
                elif l2 is None:                     # sous-discipline sur les deux colonnes
                    ligne += [cell(l1, st_c), ""]
                    style.append(("SPAN", (1, r), (2, r)))
                else:
                    ligne += [cell(l1), cell(l2)]
                ligne += [cell(v, st_gab if v in gabarits else st) for v in cases]
                data.append(ligne)
                r += 1
            if r - debut > 1:
                style.append(("SPAN", (0, debut), (0, r - 1)))
        grille = Table(data, colWidths=largeurs, repeatRows=2)
        grille.setStyle(TableStyle(style))

        class Signatures(Flowable):
            def __init__(self):
                super().__init__()
                self.height = 34 * mm

            def wrap(self, *_):
                return utile, self.height

            def draw(self):
                c = self.canv
                y = self.height - 10
                titre_t = (idc.get("titulaire_titre") or "Le titulaire").upper()
                nom_t = d.get("titulaire_visa") or idc.get("titulaire_nom") or ""
                P.bloc_signature(c, utile * 0.18, y, titre_t, nom_t, P.image_data_url((H.signature_titulaire(cl['id']) if getattr(H, "signature_titulaire", None) else None) or H.signature(f"classe:{cl['id']}:titulaire")),
                                 cachet=False, lieu_date=False, largeur=40 * mm)
                titre_d = f"{'LA' if (idc.get('directeur_titre') or '').startswith('Directrice') else 'LE'} {(idc.get('directeur_titre') or 'Directeur').upper()}"
                sig_d = P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")) or P.signature_directeur()
                P.bloc_signature(c, utile * 0.52, y, titre_d, idc.get("directeur_nom") or "", sig_d, cachet=True, lieu_date=False, largeur=40 * mm)
                if d.get("directeur_visa"):
                    c.setFont("Helvetica-Oblique", 7.5)
                    c.drawCentredString(utile * 0.52, y - 10, d["directeur_visa"][:60])
                c.setFont("Helvetica-Bold", 9)
                ville = config.ECOLE.get("ville") or ""
                c.drawCentredString(utile * 0.86, y, f"{ville + ', le ' if ville else 'Le '}{date.today().strftime('%d/%m/%Y')}")

        def deco(c, doc):
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.grey)
            c.drawString(marge, 6 * mm, f"GESCOL · {ident['epp'] or config.ECOLE.get('nom', '')} · {config.ANNEE_ACTIVE} · planification mensuelle {cl['nom']}")
            c.drawRightString(W - marge, 6 * mm, f"Page {doc.page} · imprimé le {date.today().strftime('%d/%m/%Y')}")
            c.setFillColor(colors.black)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=marge, rightMargin=marge, topMargin=marge, bottomMargin=9 * mm,
                                title=f"Planification mensuelle {cl['nom']} — {d['mois_lib']}", author="GESCOL")
        doc.build([tete, Spacer(1, 4), grille, Spacer(1, 3), Signatures()], onFirstPage=deco, onLaterPages=deco, canvasmaker=P.GCanvas)
        return buf.getvalue()

    @app.route(PM + "/<int:cid>/<mois>.pdf")
    @H.connexion_requise()
    def synoptique_planification_mensuelle_pdf(cid, mois):
        cl = classe_pm_ou_404(cid)
        mois_pm_ou_404(mois)
        d = pm_row(cid, mois) or pm_vierge(mois)
        return H.pdf_reponse(pdf_pm(cl, d), f"planification_mensuelle_{cl['nom'].replace(' ', '_')}_{mois}.pdf")

    # ---- Excel : export (sert de modèle d'import), modèle vierge, import
    ENT_PM_FIXES = ["Code", "Champ de formation", "Discipline (1re sem.)", "Discipline (2e sem.)"]

    def entetes_pm(semaines):
        return ENT_PM_FIXES + [f"Semaine {i + 1} (du {fmt_jma(s['du'])} au {fmt_jma(s['au'])})" for i, s in enumerate(semaines)]

    def lignes_pm_xlsx(d):
        return [[code, champ, l1 or "", l2 or ""] + list(d["contenu"].get(code, [""] * NB_SEMAINES_PM))
                for code, champ, l1, l2, _gab in LIGNES_PM]

    def xlsx_pm(nom, cl, d, titre):
        th = [titre, f"École {identite()['epp']} · année scolaire {config.ANNEE_ACTIVE}",
              "Modifiez les cases des colonnes Semaine 1 à 5 (et les dates dans leur en-tête) puis importez ce fichier ; "
              "ne changez pas la colonne Code."]
        return H.xlsx.reponse_xlsx(nom, entetes_pm(d["semaines"]), lignes_pm_xlsx(d), titre="Planification mensuelle", titre_haut=th)

    @app.route(PM + "/<int:cid>/<mois>.xlsx")
    @H.connexion_requise()
    def synoptique_planification_mensuelle_xlsx(cid, mois):
        cl = classe_pm_ou_404(cid)
        mois_pm_ou_404(mois)
        d = pm_row(cid, mois) or pm_vierge(mois)
        return xlsx_pm(f"planification_mensuelle_{cl['nom'].replace(' ', '_')}_{mois}.xlsx", cl, d,
                       f"Planification mensuelle (CE-CM) — {cl['nom']} ({cl['niveau']}) — {mois_libelle(mois)}")

    @app.route(PM + "/modele.xlsx")
    @H.connexion_requise()
    def synoptique_planification_mensuelle_modele():
        mois = request.args.get("mois") or mois_courant()
        if not mois_valide(mois):
            mois = mois_courant()
        return xlsx_pm("modele_planification_mensuelle.xlsx", None, pm_vierge(mois), f"Modèle de planification mensuelle (CE-CM) — {mois_libelle(mois)}")

    @app.route(PM + "/<int:cid>/<mois>/import", methods=["POST"])
    @H.connexion_requise()
    def synoptique_planification_mensuelle_import(cid, mois):
        cl = classe_pm_ou_404(cid)
        mois_pm_ou_404(mois)
        ecriture_pm(cl)
        fichier = request.files.get("fichier")
        if not fichier or not fichier.filename:
            flash("Choisissez un fichier Excel.", "danger")
            return retour_pm(cl, mois)
        try:
            entetes, lignes = H.xlsx.lire_tableau(fichier, mots_entete=("champ de formation",))
        except (ValueError, H.xlsx.ExcelIndisponible) as e_:
            flash(str(e_), "danger")
            return retour_pm(cl, mois)
        i_code = H.xlsx.colonne(entetes, "Code")
        i_l1 = H.xlsx.colonne(entetes, "Discipline (1re sem.)", "discipline 1re sem", "1re semaine")
        i_l2 = H.xlsx.colonne(entetes, "Discipline (2e sem.)", "discipline 2e sem", "2e semaine")
        i_champ = H.xlsx.colonne(entetes, "Champ de formation", "champ")
        i_sem = [H.xlsx.colonne(entetes, f"Semaine {i + 1}") for i in range(NB_SEMAINES_PM)]
        if all(i is None for i in i_sem):
            flash("Colonnes « Semaine 1 » à « Semaine 5 » introuvables dans le fichier (téléchargez le modèle).", "danger")
            return retour_pm(cl, mois)
        actuel = pm_row(cid, mois) or pm_vierge(mois)
        semaines = [dict(s) for s in actuel["semaines"]]
        for i, ic in enumerate(i_sem):           # dates des semaines lues dans l'en-tête « Semaine n (du … au …) »
            if ic is not None:
                dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}", entetes[ic])
                if len(dates) >= 2 and lire_date_iso(dates[0]) and lire_date_iso(dates[1]):
                    semaines[i] = {"du": lire_date_iso(dates[0]), "au": lire_date_iso(dates[1])}
        par_lib = {}
        for code, champ, l1, l2, _gab in LIGNES_PM:
            par_lib[(H.xlsx.normaliser(champ), H.xlsx.normaliser(l1 or ""), H.xlsx.normaliser(l2 or ""))] = code
        contenu = dict(actuel["contenu"])
        n = 0
        for l in lignes:
            code = H.xlsx.valeur(l, i_code).lower() if i_code is not None else ""
            if code not in contenu:
                cle = (H.xlsx.normaliser(H.xlsx.valeur(l, i_champ)), H.xlsx.normaliser(H.xlsx.valeur(l, i_l1)), H.xlsx.normaliser(H.xlsx.valeur(l, i_l2)))
                code = par_lib.get(cle, "")
            if code not in contenu:
                continue
            contenu[code] = [H.xlsx.valeur(l, ic)[:300] if ic is not None else contenu[code][i] for i, ic in enumerate(i_sem)]
            n += 1
        if not n:
            flash("Aucune ligne reconnue : conservez la colonne « Code » du modèle.", "danger")
            return retour_pm(cl, mois)
        enregistrer_pm(cl, mois, {"semaines": semaines, "contenu": contenu, "titulaire_visa": actuel["titulaire_visa"],
                                  "directeur_visa": actuel["directeur_visa"]}, "planification mensuelle importée")
        flash(f"Planification mensuelle {cl['nom']} — {mois_libelle(mois)} importée : {n} ligne(s).", "success")
        return retour_pm(cl, mois)

    # ============================================================ règlement intérieur
    @app.route("/synoptique/reglement")
    @H.connexion_requise()
    def synoptique_reglement():
        return render_template("synoptique_reglement.html", **ctx("reglement", lst=reglement(), TYPES=TYPES_REGLEMENT, source=REGLEMENT_SOURCE))

    @app.route("/synoptique/reglement/<int:rid>", methods=["GET", "POST"])
    @H.connexion_requise("synoptique")
    def synoptique_article_form(rid):
        a = None
        if rid:
            a = q("SELECT * FROM synoptique_reglement WHERE id=? AND ecole_id=?", (rid, H.eco()), un=True)
            if not a:
                abort(404)
            a = dict(a)
        if request.method == "POST":
            v, err = lire_article(request.form)
            if err:
                for e_ in err:
                    flash(e_, "danger")
                return render_template("synoptique_article_form.html", **ctx("reglement", a=a, v=v, TYPES=TYPES_REGLEMENT)), 400
            if rid:
                ex("UPDATE synoptique_reglement SET type=?, numero=?, titre=?, texte=?, ordre=?, maj=?, maj_par=? WHERE id=?",
                   (v["type"], v["numero"], v["titre"], v["texte"], v["ordre"], H.maintenant(), uid(), rid))
            else:
                if not v["ordre"]:
                    v["ordre"] = (q("SELECT COALESCE(MAX(ordre),0) m FROM synoptique_reglement WHERE ecole_id=?", (H.eco(),), un=True)["m"] or 0) + 10
                rid = ex("INSERT INTO synoptique_reglement (ecole_id, ordre, type, numero, titre, texte, maj, maj_par) VALUES (?,?,?,?,?,?,?,?)",
                         (H.eco(), v["ordre"], v["type"], v["numero"], v["titre"], v["texte"], H.maintenant(), uid()))
            H.journal("synoptique", f"règlement : {TYPES_REGLEMENT[v['type']]} {v['numero']} {'modifié' if a else 'ajouté'}")
            flash("Règlement intérieur mis à jour.", "success")
            return redirect(url_for("synoptique_reglement", _anchor=f"art-{rid}"))
        if not a:
            a_ = {"ordre": (q("SELECT COALESCE(MAX(ordre),0) m FROM synoptique_reglement WHERE ecole_id=?", (H.eco(),), un=True)["m"] or 0) + 10}
        return render_template("synoptique_article_form.html", **ctx("reglement", a=a, v=a or a_, TYPES=TYPES_REGLEMENT))

    @app.route("/synoptique/reglement/<int:rid>/supprimer", methods=["POST"])
    @H.connexion_requise("synoptique")
    def synoptique_article_supprimer(rid):
        a = q("SELECT * FROM synoptique_reglement WHERE id=? AND ecole_id=?", (rid, H.eco()), un=True)
        if not a:
            abort(404)
        ex("DELETE FROM synoptique_reglement WHERE id=?", (rid,))
        H.journal("synoptique", f"règlement : {TYPES_REGLEMENT.get(a['type'], a['type'])} {a['numero'] or ''} supprimé")
        flash("Élément supprimé du règlement intérieur.", "warning")
        return redirect(url_for("synoptique_reglement"))

    @app.route("/synoptique/reglement/retablir", methods=["POST"])
    @H.connexion_requise("synoptique")
    def synoptique_reglement_retablir():
        retablir_reglement()
        flash("Règlement intérieur officiel rétabli (vos modifications ont été remplacées).", "success")
        return redirect(url_for("synoptique_reglement"))

    # ============================================================ PDF
    P = H.pdfs

    def infos_haut():
        d = identite()
        return [("DDEMP", d["ddemp"] or d["departement"] or "—"), ("CS", d["cs"] or "—"), ("ÉCOLE", d["epp"] or "—")]

    def signatures():
        d = identite()
        titre = d["dirige_par"] or "Directeur"
        return [(f"{'La' if titre.startswith('Directrice') else 'Le'} {titre}".upper(), d["directeur_nom"],
                 P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)]

    def construire_pdf(titre, sections, paysage=True, taille=7, signer=True):
        """Document multi-sections : sections = [(titre_section, [flowables])] ; une section par page."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
        taille_page = landscape(A4) if paysage else A4
        W, Hh = taille_page
        marge = 12 * mm
        buf = io.BytesIO()
        st_titre = ParagraphStyle("ti", fontName="Helvetica-Bold", fontSize=13, leading=16, alignment=1, textColor=P.BLEU, spaceAfter=2)
        st_sec = ParagraphStyle("se", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=P.BLEU, spaceBefore=4, spaceAfter=4)
        st_st = ParagraphStyle("st", fontName="Helvetica", fontSize=9, leading=11, alignment=1, spaceAfter=6)
        histoire = []
        for i, (ts, flows) in enumerate(sections):
            if i:
                histoire.append(PageBreak())
            histoire.append(Paragraph(titre, st_titre))
            histoire.append(Paragraph(f"Année scolaire {config.ANNEE_ACTIVE} — édité le {date.today().strftime('%d/%m/%Y')}", st_st))
            if ts:
                histoire.append(Paragraph(ts, st_sec))
            histoire += list(flows)
        if signer:
            histoire.append(Spacer(1, 8))
            histoire.append(P._BlocSignatures(signatures(), W - 2 * marge))

        def deco(c, doc):
            P._entete_primaire(c, W, Hh, marge, infos_haut())
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.grey)
            c.drawString(marge, 7 * mm, f"GESCOL · {config.ECOLE.get('nom', '')} · {config.ANNEE_ACTIVE} · tableau synoptique")
            c.drawRightString(W - marge, 7 * mm, f"Page {doc.page} · imprimé le {date.today().strftime('%d/%m/%Y')}")
            c.setFillColor(colors.black)

        doc = SimpleDocTemplate(buf, pagesize=taille_page, leftMargin=marge, rightMargin=marge, topMargin=marge + 30 * mm,
                                bottomMargin=13 * mm, title=titre, author="GESCOL")
        doc.build(histoire, onFirstPage=deco, onLaterPages=deco, canvasmaker=P.GCanvas)
        return buf.getvalue()

    def tableau(entetes, lignes, largeurs=None, taille=7, paysage=True, surlignes=None):
        """Table ReportLab (en-tête répété) sur la largeur utile de la page."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Table, TableStyle
        W = (landscape(A4) if paysage else A4)[0]
        utile = W - 24 * mm
        st_c = ParagraphStyle("c", fontName="Helvetica", fontSize=taille, leading=taille + 1.6)
        st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=taille, leading=taille + 1.6, alignment=1, textColor=colors.white)

        def cell(v, st=st_c):
            return Paragraph("" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>"), st)

        data = [[cell(h, st_h) for h in entetes]] + [[cell(v) for v in l] for l in lignes]
        if not largeurs:
            largeurs = [1] * len(entetes)
        s = sum(largeurs)
        t = Table(data, colWidths=[utile * x / s for x in largeurs], repeatRows=1)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#667085")), ("BACKGROUND", (0, 0), (-1, 0), P.BLEU),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")])]
        for i, coul in (surlignes or {}).items():
            style.append(("BACKGROUND", (0, 1 + i), (-1, 1 + i), colors.HexColor(coul)))
        t.setStyle(TableStyle(style))
        return t

    def section_identite():
        d = identite()
        lignes = [[lib, d.get(k) or "—"] for k, lib in CHAMPS_IDENTITE]
        return [tableau(["Rubrique", "Renseignement"], lignes, [1, 2], taille=9)]

    def section_personnel(lst):
        corps = [ligne_personnel(i, f) for i, f in enumerate(lst, 1)] or [["", "Aucun agent"] + [""] * (len(COLS_PERSONNEL) - 1)]
        surl = {i: "#FDEAD7" for i, f in enumerate(lst) if f["alerte_retraite"]}
        notes = P.paragraphe(
            f"Anciennetés au {MC.date_reference().strftime('%d/%m/%Y')} (31/12 de la première année de l'année scolaire, jour "
            "inclus), en années (a) et mois (m), à partir de la prise de service dans chaque lieu. Retraite : 60 ans (grade A), "
            "58 ans (B), 55 ans (C), départ le 1er jour du trimestre qui suit le trimestre de naissance. Lignes orangées : départ "
            "dans 2 ans ou moins. PS = prise de service.", 6.5)
        return [tableau(ENTETES_PERSONNEL_PDF, corps, LARGEURS_PERSONNEL_PDF, taille=5.6, surlignes=surl), notes]

    def section_comite(comite, cl=None):
        lst = membres(comite, cl["id"] if cl else None)
        corps = [[i, m["nom_prenoms"], m["qualite"] or "", m["origine"] or "", m["contact"] or "", m["observations"] or ""]
                 for i, m in enumerate(lst, 1)] or [["", "Aucun membre enregistré", "", "", "", ""]]
        return [tableau(["N°", "Nom et prénoms", "Qualité / fonction", "Structure d'origine", "Contact", "Observations"], corps,
                        [1, 6, 4, 4, 3, 5], taille=8)]

    def section_edt(niveau):
        d = edt(niveau)
        corps = [[l["horaire"]] + [l[j] for j, _ in JOURS] for l in d["lignes"]]
        flows = [tableau(["Horaires"] + [lib for _j, lib in JOURS], corps, [2, 3, 3, 3, 3, 3], taille=7.5)]
        if d.get("remarques"):
            flows.append(P.paragraphe("Remarques : " + " ".join(f"{i}. {r}" for i, r in enumerate(d["remarques"], 1)), 7))
        if d.get("source"):
            flows.append(P.paragraphe(f"Source : {d['source']}", 6.5))
        return flows

    def section_planification(niveau):
        d = planification(niveau)
        ent = ["Trim."] + [lib for _k, lib, _g in COLS_PLAN[1:]]
        corps = [[l.get(k, "") for k in CLES_PLAN] for l in d["lignes"]]
        larg = [3, 4, 7, 7, 4, 4, 4, 4, 5, 5, 4, 4, 4, 4, 4, 6]
        return [P.paragraphe("Éducation sociale : Morale, Civisme, Histoire, Géographie · Éducation artistique : Chant, Poésie, "
                             "Conte, Dessin, Couture", 7), tableau(ent, corps, larg, taille=5.8)]

    def section_reglement():
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph
        st_t = ParagraphStyle("rt", fontName="Helvetica-Bold", fontSize=9.5, leading=12, spaceBefore=8, spaceAfter=3, textColor=P.BLEU)
        st_a = ParagraphStyle("ra", fontName="Helvetica", fontSize=8.5, leading=11, spaceAfter=4, alignment=4)
        flows = []

        def esc(t):
            return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")

        for a in reglement():
            if a["type"] == "titre":
                flows.append(Paragraph(f"TITRE {esc(a['numero'])} : {esc(a['titre']).upper()}", st_t))
            elif a["type"] == "preambule":
                flows.append(Paragraph(esc(a["titre"] or "PRÉAMBULE").upper(), st_t))
                flows.append(Paragraph(esc(a["texte"]), st_a))
            else:
                flows.append(Paragraph(f"<b>Article {esc(a['numero'])} :</b> {esc(a['texte'])}", st_a))
        flows.append(P.paragraphe(REGLEMENT_SOURCE, 6.5))
        return flows

    @app.route("/synoptique/synoptique.pdf")
    @H.connexion_requise()
    def synoptique_pdf():
        d = identite()
        sections = [("1. Identité de l'école", section_identite()),
                    ("2. Tableau synoptique du personnel enseignant", section_personnel(personnel()))]
        for c in ("sante", "ape", "direction"):
            sections.append((f"3. {COMITES[c]}", section_comite(c)))
        for cl in classes_ecole():
            sections.append((f"3. Comité de classe — {cl['nom']} ({cl['niveau']})", section_comite("classe", cl)))
        for k, lib in NIVEAUX:
            sections.append((f"4. Emploi du temps — {lib}", section_edt(k)))
        for k, lib in NIVEAUX:
            sections.append((f"5. Planification annuelle — {lib}", section_planification(k)))
        sections.append(("6. Règlement intérieur", section_reglement()))
        pdf = construire_pdf(f"TABLEAU SYNOPTIQUE DE L'ÉCOLE — {d['epp'] or ''}".strip(" —"), sections)
        return H.pdf_reponse(pdf, "tableau_synoptique.pdf")

    @app.route("/synoptique/personnel.pdf")
    @H.connexion_requise()
    def synoptique_personnel_pdf():
        pdf = construire_pdf("TABLEAU SYNOPTIQUE DU PERSONNEL ENSEIGNANT", [("", section_personnel(personnel(tous=request.args.get("tous") == "1")))])
        return H.pdf_reponse(pdf, "synoptique_personnel.pdf")

    @app.route("/synoptique/comites/<comite>.pdf")
    @H.connexion_requise()
    def synoptique_comite_pdf(comite):
        lib = comite_ou_404(comite)
        cl = classe_courante(comite)
        titre = lib.upper() + (f" — {cl['nom']}" if cl else "")
        pdf = construire_pdf(titre, [("", section_comite(comite, cl))], paysage=False)
        return H.pdf_reponse(pdf, f"comite_{comite}.pdf")

    @app.route("/synoptique/edt/<niveau>.pdf")
    @H.connexion_requise()
    def synoptique_edt_pdf(niveau):
        lib = niveau_ou_404(niveau)
        pdf = construire_pdf(f"EMPLOI DU TEMPS — {lib.upper()}", [("", section_edt(niveau))])
        return H.pdf_reponse(pdf, f"emploi_du_temps_{niveau}.pdf")

    @app.route("/synoptique/planification/<niveau>.pdf")
    @H.connexion_requise()
    def synoptique_planification_pdf(niveau):
        lib = niveau_ou_404(niveau)
        pdf = construire_pdf(f"PLANIFICATION ANNUELLE DES ACTIVITÉS PÉDAGOGIQUES — {lib.upper()}", [("", section_planification(niveau))])
        return H.pdf_reponse(pdf, f"planification_{niveau}.pdf")

    @app.route("/synoptique/reglement.pdf")
    @H.connexion_requise()
    def synoptique_reglement_pdf():
        pdf = construire_pdf("RÈGLEMENT INTÉRIEUR DE L'ÉCOLE", [("", section_reglement())], paysage=False)
        return H.pdf_reponse(pdf, "reglement_interieur.pdf")

    # ============================================================ Excel : export, modèle, import
    ENT_MEMBRES = ["N°", "Nom et prénoms", "Qualité / fonction", "Structure d'origine", "Contact", "Observations", "Classe"]
    ENT_EDT = ["Cours", "Horaires"] + [lib for _j, lib in JOURS]
    ENT_PLAN = ["Cours"] + [lib for _k, lib, _g in COLS_PLAN]
    ENT_REGLEMENT = ["Ordre", "Type", "Numéro", "Titre", "Texte"]

    def feuilles_export():
        th = [f"{identite()['epp']} — Tableau synoptique", f"Année scolaire {config.ANNEE_ACTIVE} · extrait le {date.today().strftime('%d/%m/%Y')}"]
        d = identite()
        f = [("Identité", ["Rubrique", "Renseignement"], [[lib, d.get(k) or ""] for k, lib in CHAMPS_IDENTITE], {"titre_haut": th}),
             ("Personnel", ENTETES_PERSONNEL, [ligne_personnel(i, x) for i, x in enumerate(personnel(), 1)], {"titre_haut": th})]
        for c in ("sante", "ape", "direction"):
            f.append((COMITES[c], ENT_MEMBRES[:-1], [[i, m["nom_prenoms"], m["qualite"], m["origine"], m["contact"], m["observations"]]
                                                   for i, m in enumerate(membres(c), 1)], {"titre_haut": th}))
        lignes = []
        for cl in classes_ecole():
            lignes += [[i, m["nom_prenoms"], m["qualite"], m["origine"], m["contact"], m["observations"], cl["nom"]]
                       for i, m in enumerate(membres("classe", cl["id"]), 1)]
        f.append(("Comités de classe", ENT_MEMBRES, lignes, {"titre_haut": th}))
        lignes = []
        for k, lib in NIVEAUX:
            lignes += [[lib, l["horaire"]] + [l[j] for j, _ in JOURS] for l in edt(k)["lignes"]]
        f.append(("Emplois du temps", ENT_EDT, lignes, {"titre_haut": th}))
        lignes = []
        for k, lib in NIVEAUX:
            lignes += [[lib] + [l.get(c, "") for c in CLES_PLAN] for l in planification(k)["lignes"]]
        f.append(("Planification", ENT_PLAN, lignes, {"titre_haut": th}))
        f.append(("Règlement", ENT_REGLEMENT, [[a["ordre"], TYPES_REGLEMENT.get(a["type"], a["type"]), a["numero"], a["titre"], a["texte"]]
                                              for a in reglement()], {"titre_haut": th}))
        return f

    @app.route("/synoptique/export.xlsx")
    @H.connexion_requise()
    def synoptique_xlsx():
        try:
            return H.xlsx.reponse_classeur("tableau_synoptique.xlsx", feuilles_export())
        except H.xlsx.ExcelIndisponible:
            flash("Export Excel indisponible (module openpyxl absent).", "danger")
            return redirect(url_for("synoptique_accueil"))

    @app.route("/synoptique/planification/<niveau>.xlsx")
    @H.connexion_requise()
    def synoptique_planification_xlsx(niveau):
        lib = niveau_ou_404(niveau)
        lignes = [[l.get(c, "") for c in CLES_PLAN] for l in planification(niveau)["lignes"]]
        return H.xlsx.reponse_xlsx(f"planification_{niveau}.xlsx", [x for x in ENT_PLAN[1:]], lignes, titre=f"Planification {lib}",
                                   titre_haut=[f"Planification annuelle — {lib}", f"Année scolaire {config.ANNEE_ACTIVE}"])

    @app.route("/synoptique/edt/<niveau>.xlsx")
    @H.connexion_requise()
    def synoptique_edt_xlsx(niveau):
        lib = niveau_ou_404(niveau)
        lignes = [[l["horaire"]] + [l[j] for j, _ in JOURS] for l in edt(niveau)["lignes"]]
        return H.xlsx.reponse_xlsx(f"emploi_du_temps_{niveau}.xlsx", ENT_EDT[1:], lignes, titre=f"EDT {lib}",
                                   titre_haut=[f"Emploi du temps — {lib}", f"Année scolaire {config.ANNEE_ACTIVE}"])

    # colonnes reconnues à l'import du personnel : clé -> intitulés possibles
    IMPORT_PERSONNEL = {
        "matricule": ("N° matricule", "matricule"), "nip": ("NIP",), "nom": ("Nom",), "prenoms": ("Prénoms", "prenom"),
        "nom_complet": ("Nom et prénoms", "nom et prenoms"), "sexe": ("Sexe",), "promotion": ("Promotion",),
        "categorie": ("Catégorie", "categorie"), "fonction": ("Fonction",), "grade": ("Grade",), "indice_reel": ("Indice réel",),
        "indice_paye": ("Indice payé",), "cours_tenus": ("Cours tenus",), "date_naissance": ("Date de naissance", "naissance"),
        "date_prise_service": ("Date de première prise de service", "premiere prise de service", "1re prise de service"),
        "date_service_dep": ("Date de prise de service dans le département", "prise de service departement", "PS departement"),
        "date_service_commune": ("Prise de service dans la commune",),
        "date_service_ecole": ("Date de prise de service dans l'école", "prise de service ecole", "PS ecole"),
        "date_derniere_formation": ("Date de la dernière formation", "derniere formation"),
        "diplome_academique": ("Diplôme académique le plus élevé", "diplome academique"),
        "diplome_academique_annee": ("Année du diplôme académique", "annee diplome"),
        "ceap": ("CEAP",), "ceap_annee": ("Année du CEAP",), "cap": ("CAP",), "cap_annee": ("Année du CAP",),
        "visite_aptitude": ("Visite d'aptitude",), "visite_aptitude_note": ("Note",), "visites_cp": ("Visites CP",),
        "visites_ccs": ("Visites CCS",), "visites_cp_ccs": ("Nombre de visites CP / CCS", "visites CP/CCS"),
        "visites_directeur": ("Nombre de visites du directeur", "visites directeur"), "participation_up": ("Participation à l'UP", "UP"),
        "gestion_collegiale": ("Gestion collégiale",), "telephone": ("Contact", "Téléphone"),
    }

    def lire_feuilles(fichier):
        """Classeur -> {nom de feuille normalisé: (entetes, lignes)} (ligne d'en-tête = première contenant « nom »)."""
        openpyxl = H.xlsx._openpyxl()
        try:
            wb = openpyxl.load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        except Exception as e_:  # noqa: BLE001
            raise ValueError("Fichier Excel illisible : enregistrez-le au format .xlsx.") from e_
        out = {}
        for ws in wb.worksheets:
            brutes = [list(r) for r in ws.iter_rows(values_only=True)][:5000]
            idx = next((i for i, r in enumerate(brutes[:40]) if any("nom" in H.xlsx.normaliser(v).split(" ") for v in r if v)), None)
            if idx is None:
                continue
            entetes = [str(v).strip() if v is not None else "" for v in brutes[idx]]
            lignes = [r for r in brutes[idx + 1:] if any(v not in (None, "") for v in r)]
            out[H.xlsx.normaliser(ws.title)] = (entetes, lignes)
        return out

    def importer_personnel(entetes, lignes):
        """Lignes Excel du personnel -> agents créés / mis à jour (rapprochement par matricule, NIP puis nom et prénoms)."""
        idx = {k: H.xlsx.colonne(entetes, *cands) for k, cands in IMPORT_PERSONNEL.items()}
        if idx["nom"] is None and idx["nom_complet"] is None:
            raise ValueError("Colonne « Nom » (ou « Nom et prénoms ») introuvable dans la feuille Personnel.")
        crees = modifies = 0
        erreurs = []

        def annee_dans(txt):
            m = re.search(r"(19|20)\d{2}", txt or "")
            return m.group(0) if m else ""

        for n, l in enumerate(lignes, 1):
            val = lambda k: H.xlsx.valeur(l, idx[k])   # noqa: E731
            nom, prenoms = val("nom"), val("prenoms")
            if not nom and idx["nom_complet"] is not None:
                morceaux = val("nom_complet").split(" ", 1)
                nom, prenoms = morceaux[0], (morceaux[1] if len(morceaux) > 1 else prenoms)
            if not nom:
                continue
            form = {
                "nom": nom, "prenoms": prenoms or "—", "sexe": H.xlsx.sexe(val("sexe")), "fonction": val("fonction") or "Enseignant(e)",
                "telephone": val("telephone"), "matricule": val("matricule"), "nip": val("nip"), "categorie": val("categorie").upper().replace(" (AME)", ""),
                "grade": val("grade"), "indice_reel": val("indice_reel"), "indice_paye": val("indice_paye"),
                "date_naissance": val("date_naissance") if not H.xlsx.date_iso(val("date_naissance")) else H.xlsx.date_iso(val("date_naissance")),
                "diplome_academique": val("diplome_academique"), "diplome_academique_annee": val("diplome_academique_annee"),
                "ceap": "oui" if val("ceap").lower().startswith("oui") else ("non" if val("ceap").lower().startswith("non") else ""),
                "ceap_annee": val("ceap_annee") or annee_dans(val("ceap")),
                "cap": "oui" if val("cap").lower().startswith("oui") else ("non" if val("cap").lower().startswith("non") else ""),
                "cap_annee": val("cap_annee") or annee_dans(val("cap")),
                "visite_aptitude": val("visite_aptitude").lower()[:3], "visite_aptitude_note": val("visite_aptitude_note"),
                "visites_cp": val("visites_cp"), "visites_ccs": val("visites_ccs"), "visites_directeur": val("visites_directeur"),
                "participation_up": val("participation_up"), "gestion_collegiale": val("gestion_collegiale"),
                "promotion": val("promotion"), "cours_tenus": val("cours_tenus"),
                "date_derniere_formation": H.xlsx.date_iso(val("date_derniere_formation")),
            }
            for k in ("date_prise_service", "date_service_dep", "date_service_commune", "date_service_ecole"):
                form[k] = H.xlsx.date_iso(val(k))
            if idx["visites_cp_ccs"] is not None and not form["visites_cp"]:
                m = re.findall(r"\d+", val("visites_cp_ccs"))
                if m:
                    form["visites_cp"] = m[0]
                    form["visites_ccs"] = m[1] if len(m) > 1 else ""
            # rapprochement avec un agent existant de l'école
            pid = None
            if form["matricule"]:
                r = q("SELECT id FROM personnel WHERE matricule=? AND ecole_id=?", (form["matricule"], H.eco()), un=True)
                pid = r["id"] if r else None
            if not pid and form["nip"]:
                r = q("SELECT id FROM personnel WHERE nip=? AND ecole_id=?", (form["nip"], H.eco()), un=True)
                pid = r["id"] if r else None
            if not pid:
                r = q("SELECT id FROM personnel WHERE UPPER(nom)=? AND LOWER(prenoms)=? AND ecole_id=?",
                      (form["nom"].upper(), form["prenoms"].lower(), H.eco()), un=True)
                pid = r["id"] if r else None
            ident, car, extra, err = lire_agent(form, pid)
            if err:
                erreurs.append(f"Ligne {n} ({nom}) : " + " ".join(err))
                continue
            enregistrer_agent(pid, ident, car, extra)
            if pid:
                modifies += 1
            else:
                crees += 1
        return crees, modifies, erreurs

    def importer_membres(comite, entetes, lignes, cls):
        idx = {"nom": H.xlsx.colonne(entetes, "Nom et prénoms", "nom"), "qualite": H.xlsx.colonne(entetes, "Qualité / fonction", "qualite", "fonction"),
               "origine": H.xlsx.colonne(entetes, "Structure d'origine", "origine", "structure"), "contact": H.xlsx.colonne(entetes, "Contact", "telephone"),
               "observations": H.xlsx.colonne(entetes, "Observations"), "classe": H.xlsx.colonne(entetes, "Classe")}
        if idx["nom"] is None:
            return 0
        n = 0
        for l in lignes:
            nom = H.xlsx.valeur(l, idx["nom"])
            if not nom:
                continue
            cid = None
            if comite == "classe":
                nom_cl = H.xlsx.normaliser(H.xlsx.valeur(l, idx["classe"]))
                c = next((x for x in cls if H.xlsx.normaliser(x["nom"]) == nom_cl), None)
                if not c:
                    continue
                cid = c["id"]
            v = {"nom_prenoms": nom[:120], "qualite": H.xlsx.valeur(l, idx["qualite"])[:60], "origine": H.xlsx.valeur(l, idx["origine"])[:60],
                 "contact": H.xlsx.valeur(l, idx["contact"])[:60], "observations": H.xlsx.valeur(l, idx["observations"])[:300]}
            existant = q("SELECT id FROM synoptique_membres WHERE ecole_id=? AND comite=? AND COALESCE(classe_id,0)=? AND nom_prenoms=?",
                         (H.eco(), comite, cid or 0, v["nom_prenoms"]), un=True)
            if existant:
                ex("UPDATE synoptique_membres SET qualite=?, origine=?, contact=?, observations=?, maj=?, maj_par=? WHERE id=?",
                   (v["qualite"], v["origine"], v["contact"], v["observations"], H.maintenant(), uid(), existant["id"]))
            else:
                ex("INSERT INTO synoptique_membres (ecole_id, annee, comite, classe_id, ordre, nom_prenoms, qualite, origine, contact, observations, maj, maj_par) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (H.eco(), config.ANNEE_ACTIVE, comite, cid, n, v["nom_prenoms"], v["qualite"], v["origine"],
                                                        v["contact"], v["observations"], H.maintenant(), uid()))
            n += 1
        return n

    FEUILLES_COMITES = {"comite de sante": "sante", "bureau de l ape": "ape", "ape": "ape", "comite de direction": "direction",
                        "comites de classe": "classe", "comite de classe": "classe"}

    @app.route("/synoptique/import", methods=["GET", "POST"])
    @H.connexion_requise("synoptique")
    def synoptique_import():
        if request.method == "POST":
            fichier = request.files.get("fichier")
            if not fichier or not fichier.filename:
                flash("Choisissez un fichier Excel (.xlsx).", "danger")
                return redirect(url_for("synoptique_import"))
            try:
                feuilles = lire_feuilles(fichier)
            except (ValueError, H.xlsx.ExcelIndisponible) as e_:
                flash(str(e_), "danger")
                return redirect(url_for("synoptique_import"))
            if not feuilles:
                flash("Aucune feuille exploitable : la ligne d'en-tête doit contenir une colonne « Nom ».", "danger")
                return redirect(url_for("synoptique_import"))
            bilan = []
            cles = list(feuilles)
            feuille_perso = next((k for k in cles if k.startswith("personnel")), None)
            if feuille_perso is None and not any(k in FEUILLES_COMITES for k in cles):
                feuille_perso = cles[0]        # un classeur d'une seule feuille = le personnel
            if feuille_perso is not None:
                try:
                    crees, modifies, erreurs = importer_personnel(*feuilles[feuille_perso])
                except ValueError as e_:
                    flash(str(e_), "danger")
                    return redirect(url_for("synoptique_import"))
                bilan.append(f"Personnel : {crees} agent(s) ajouté(s), {modifies} mis à jour.")
                for e_ in erreurs[:15]:
                    flash(e_, "warning")
            cls = classes_ecole()
            for k, comite in FEUILLES_COMITES.items():
                if k in feuilles:
                    n = importer_membres(comite, *feuilles[k], cls)
                    bilan.append(f"{COMITES[comite]} : {n} membre(s) importé(s).")
            H.journal("synoptique", "import Excel : " + " ".join(bilan))
            flash("Import terminé. " + " ".join(bilan), "success")
            return redirect(url_for("synoptique_accueil"))
        return render_template("synoptique_import.html", **ctx("import", entetes=ENTETES_PERSONNEL, ent_membres=ENT_MEMBRES))

    @app.route("/synoptique/modele.xlsx")
    @H.connexion_requise()
    def synoptique_modele_xlsx():
        ex_ = [1, "12345", "1234567", "AKPO Jean", "2005", "ACDPE", "Enseignant(e)", "B1-12", 500, 480, "CM2 A", "", "", "",
               "01/10/2005", "01/10/2010", "16/09/2019", "", "15/03/2024", "BAC (2003)", "CEAP oui (2008) / CAP oui (2012)", "oui", 15,
               "2 / 1", 3, 80, "Responsable de la cantine", "97 00 00 00"]
        feuilles = [("Personnel", ENTETES_PERSONNEL, [ex_], {"titre_haut": ["Modèle d'import du personnel — les anciennetés et la retraite sont calculées, laissez-les vides"]}),
                    ("Comité de santé", ENT_MEMBRES[:-1], [[1, "HOUNSOU Marie", "Présidente", "Agent de santé", "", ""]]),
                    ("Bureau de l'APE", ENT_MEMBRES[:-1], [[1, "DOSSOU Paul", "Président", "Parent d'élève", "", ""]]),
                    ("Comité de direction", ENT_MEMBRES[:-1], [[1, "", "Directeur / directrice", "Directeur / directrice", "", ""]]),
                    ("Comités de classe", ENT_MEMBRES, [[1, "", "Président", "Parent d'élève", "", "", "CM2 A"]])]
        try:
            return H.xlsx.reponse_classeur("modele_synoptique.xlsx", feuilles)
        except H.xlsx.ExcelIndisponible:
            flash("Modèle Excel indisponible (module openpyxl absent).", "danger")
            return redirect(url_for("synoptique_import"))


# ================================================================ planification annuelle officielle (CI → CM2)
# Extraite de docs_reference/planification_annuelle_CI_CM2.pdf (DDEMP Donga, CS Djougou II, 2023-2024) :
# une ligne par mois ; « SA » = situation d'apprentissage, « Séq » = séquence, « U » = unité, « D » = domaine.
PLANIFICATION_OFFICIELLE = {'CI': [{'trimestre': 'I',
         'mois': 'Septembre',
         'francais': 'Semaines 1 -2',
         'maths': 'Jours 1-10 : SA1',
         'es_morale': 'initiation',
         'es_civisme': 'Initiation',
         'es_histoire': 'initiation',
         'es_geographie': 'initiation',
         'est': 'SA1 Séq1-4',
         'eps': 'SA1 Séq 1-4',
         'ea_chant': 'SA1 Séq1-8',
         'ea_poesie': '-',
         'ea_conte': 'SA1 Séq1-4',
         'ea_dessin': 'SA11 Séq1-4',
         'ea_couture': 'SA20 Séq1-2',
         'observations': ''},
        {'trimestre': 'I',
         'mois': 'Octobre',
         'francais': 'Semaines 3 -7',
         'maths': 'J : 11-20- : SA1 (suite) J : 26-30 : SA2 J : 31-32 : SA2',
         'es_morale': 'initiation',
         'es_civisme': 'initiation',
         'es_histoire': 'initiation',
         'es_geographie': 'initiation',
         'est': 'SA2 Séq1 SA3 Séq4',
         'eps': 'SA2 -3 Séq 1-9',
         'ea_chant': 'SA2-3 Séq1-17',
         'ea_poesie': '- Écoute/apprentissage de comptines',
         'ea_conte': 'SA1 Séq5 SA2 Séq7',
         'ea_dessin': 'SA11 Séq5-13',
         'ea_couture': 'SA20 Séq1-2',
         'observations': ''},
        {'trimestre': 'I',
         'mois': 'Novembre',
         'francais': 'Semaines 8-12',
         'maths': 'J : 33-34 : SA2 J : 36-39 : SA2 J : 40-44 : SA2 J : 45 : SA2 J : 46-49 (intégration2) Jours 50 : '
                  '(intitulé fin) J : 51-53 : SA2',
         'es_morale': 'initiation',
         'es_civisme': 'initiation',
         'es_histoire': 'initiation',
         'es_geographie': 'initiation',
         'est': 'SA3 Séq5 SA5 Séq2',
         'eps': 'SA2-3 Séq10 SA3-4 Séq6',
         'ea_chant': 'SA2-3 Séq18 SA4-5 Séq12',
         'ea_poesie': '- Écoute/apprentissage de comptines',
         'ea_conte': 'SA2 Séq8 SA3 Séq47',
         'ea_dessin': 'SA11 Séq13-21',
         'ea_couture': 'SA20 Séq1-2',
         'observations': ''},
        {'trimestre': 'I',
         'mois': 'Décembre',
         'francais': 'PM',
         'maths': 'J : 54-58 : SA2 J : 59-60 : SA2 fin.',
         'es_morale': 'initiation',
         'es_civisme': 'initiation',
         'es_histoire': 'initiation',
         'es_geographie': 'initiation',
         'est': 'SA6 Séq3 SA6 Séq2',
         'eps': 'SA6 Séq1 à SA7 Séq1',
         'ea_chant': 'SA2-3 Séq18 SA4-5 Séq12',
         'ea_poesie': 'Écoute/apprentissage de comptines',
         'ea_conte': 'SA2 Séq8 SA3 Séq47',
         'ea_dessin': 'SA11 Séq13-21',
         'ea_couture': 'SA20 Séq1-2',
         'observations': ''},
        {'trimestre': 'II',
         'mois': 'Janvier',
         'francais': 'Semaines 13à16 leçon 1-7',
         'maths': 'J : 61-62 :SA3 J : 63-66 : SA3 J :67-70 : SA3 J : 71-75 intégration3 J : 76-81 : SA3 J : 82-84 : '
                  'SA3',
         'es_morale': 'SA1 Séq1 SA2 Séq7',
         'es_civisme': 'SA9 Séq1-4',
         'es_histoire': 'SA4',
         'es_geographie': 'SA4',
         'est': 'SA1 Séq1 à SA2 Séq1',
         'eps': 'SA1 Séq1 SA2 Séq4',
         'ea_chant': 'SA1 -2-3 13',
         'ea_poesie': 'SA12 Séq1-3',
         'ea_conte': 'SA3 Séq1-3',
         'ea_dessin': 'SA3 Séq1-3',
         'ea_couture': 'SA14 Séq1',
         'observations': ''},
        {'trimestre': 'II',
         'mois': 'Février',
         'francais': 'Semaine 17 intégration Semaine 18 leçon 9',
         'maths': 'J :85 : SA3-86 SA4 J :87-91 : SA4 J :92-95 : SA4 j : 96-100 intégration4',
         'es_morale': 'SA2 Séq2 -7',
         'es_civisme': 'SA2 Séq5-7',
         'es_histoire': 'SA4',
         'es_geographie': 'SA4',
         'est': 'SA2 Séq2 SA3 Séq1',
         'eps': 'SA2 -3 Séq5-9',
         'ea_chant': 'SA17-18-21',
         'ea_poesie': 'SA12 Séq4-6',
         'ea_conte': 'SA3 Séq4-6',
         'ea_dessin': 'SA15-19-11',
         'ea_couture': 'SA14 Séq1',
         'observations': ''},
        {'trimestre': 'II',
         'mois': 'Mars',
         'francais': 'Semaines 18-19-20-21 leçon 11-12-14-15-17-18',
         'maths': 'J : 101-105 : SA4 J : 106-110 :SA4 J : 111-115 : SA4 J : 116-120 : SA5 J : 121-125 intégration5',
         'es_morale': 'SA3 Séq1-4',
         'es_civisme': 'SA2 Séq8-9 SA10 Séq1-12',
         'es_histoire': 'SA5',
         'es_geographie': 'SA5',
         'est': 'SA3 Séq2 SA4 Séq1',
         'eps': 'SA2-3 Séq10 SA4-5 Séq4',
         'ea_chant': 'SA25-29-33',
         'ea_poesie': 'SA12 Séq15-20',
         'ea_conte': 'SA24-28-36-11',
         'ea_dessin': 'SA27-31-35',
         'ea_couture': 'SA14 Séq1',
         'observations': "Évaluation sommative d'étape"},
        {'trimestre': 'III',
         'mois': 'Avril',
         'francais': 'Semaines 21 leçon semaine 23 leçons 20 à 23',
         'maths': 'J : 126 (SA6) - 127 J : 128-132 J : 133-134 (SA6)',
         'es_morale': 'révision',
         'es_civisme': 'SA10 Séq3-5',
         'es_histoire': 'SA5-7',
         'es_geographie': 'SA5-7',
         'est': 'SA4 Séq2 SA5 Séq3',
         'eps': 'SA6 Séq1 SA7 Séq2',
         'ea_chant': 'SA41',
         'ea_poesie': 'SA21',
         'ea_conte': 'SA36',
         'ea_dessin': 'SA34-39-43',
         'ea_couture': 'SA42',
         'observations': ''},
        {'trimestre': 'III',
         'mois': 'Mai',
         'francais': 'Semaines 24 à 26 26 (suite) Semaine 27 intégration et 27 suite semaine 28 leçon28-29 suite '
                     'semaine 28 leçon 31-32 Semaine 29 leçon 33 Semaine 29 leçon 34',
         'maths': 'J : 135-136 : SA6 J : 137 140 :SA6 J : 141 (SA7) -145 J : 146-149 (SI6) J : 151-155 : SA7',
         'es_morale': 'Révision',
         'es_civisme': 'SA11 Séq1-3',
         'es_histoire': 'SA8',
         'es_geographie': 'SA8',
         'est': 'SA5 Séq4 SA7 séq3',
         'eps': 'SA7 Séq3 SA9 Séq9',
         'ea_chant': 'SA41',
         'ea_poesie': 'SA21',
         'ea_conte': 'SA36',
         'ea_dessin': 'SA44',
         'ea_couture': 'SA42',
         'observations': ''},
        {'trimestre': 'III',
         'mois': 'Juin',
         'francais': 'Semaine 30 leçon 34 (suite) Semaine 31 leçon 35-37 Semaine 32 leçon 38-40-41 et 42',
         'maths': 'J : 156-160 : SA7',
         'es_morale': 'révision',
         'es_civisme': 'SA11 Séq4-6',
         'es_histoire': 'Renforcement intégration +évaluation',
         'es_geographie': 'Renforcement intégration +évaluation',
         'est': 'Révision',
         'eps': 'SA10 Séq1 SA11-12 Séq2 + révision',
         'ea_chant': 'SA41',
         'ea_poesie': 'SA21',
         'ea_conte': 'SA36',
         'ea_dessin': 'SA44',
         'ea_couture': 'SA42',
         'observations': "Évaluation sommative d'étape"}],
 'CP': [{'trimestre': 'I',
         'mois': 'Septembre',
         'francais': 'Évaluation diagnostique CO : L : 1-3',
         'maths': 'Évaluation diagnostique SA1 fiche 1 à5',
         'es_morale': 'SA1-1 Séq1 et2',
         'es_civisme': 'SA5-1 Séq1-2',
         'es_histoire': 'SA8 Séq1',
         'es_geographie': 'SA10 Séq1',
         'est': 'SA1 Séq1-2',
         'eps': 'SA1-2',
         'ea_chant': 'SA1',
         'ea_poesie': 'SA4',
         'ea_conte': 'SA4',
         'ea_dessin': 'SA3',
         'ea_couture': 'SA2',
         'observations': ''},
        {'trimestre': 'I',
         'mois': 'Octobre',
         'francais': 'CO : L4-12 Intégration L :13 -15',
         'maths': 'SA1 fiche 6 à 20 +intégration fiche 21 à 27',
         'es_morale': 'SA1 Séq3 SA1-2 Séq3',
         'es_civisme': 'SA5-1 Séq3 SA5-3- Séq1',
         'es_histoire': 'SA8 Séq2-4',
         'es_geographie': 'SA10 Séq2-3',
         'est': 'SA1 Séq3 à SA2 Séq4',
         'eps': 'SA1-2 et Séq 3-6 et 1-5',
         'ea_chant': 'SA1',
         'ea_poesie': 'SA4',
         'ea_conte': 'SA4',
         'ea_dessin': 'SA3',
         'ea_couture': 'SA2',
         'observations': ''},
        {'trimestre': 'I',
         'mois': 'Novembre',
         'francais': 'L : 16-26 + intégration L : 27 -28',
         'maths': 'SA1 fiche 28 à 45 + intégration fiche 46-50',
         'es_morale': 'SA1-2 Séq4 SA2 Séq4 SA6-1 Séq1-2',
         'es_civisme': 'SA5-3 Séq2 SA6-1 Séq2',
         'es_histoire': 'SA8 Séq5 SA9 Séq1',
         'es_geographie': 'SA10 Séq4 SA11 Séq2',
         'est': 'SA3 Séq1 à SA4 Séq3',
         'eps': 'SA3 Séq6 SA4-5 Séq4',
         'ea_chant': 'SA5',
         'ea_poesie': 'SA4',
         'ea_conte': 'SA4',
         'ea_dessin': 'SA3',
         'ea_couture': 'SA8',
         'observations': ''},
        {'trimestre': 'I',
         'mois': 'Décembre',
         'francais': 'L : 29-31',
         'maths': 'SA1 fiche51 -55',
         'es_morale': 'SA6-2 Séq1',
         'es_civisme': 'SA6-2 Séq1',
         'es_histoire': 'SA9 Séq2',
         'es_geographie': 'Renforcement',
         'est': 'SA4 Séq à SA5 Séq4',
         'eps': 'SA6-7 Séq1-4',
         'ea_chant': 'SA5',
         'ea_poesie': 'SA4',
         'ea_conte': 'SA4',
         'ea_dessin': 'SA6',
         'ea_couture': 'SA8',
         'observations': "Évaluation sommative d'étape 1"},
        {'trimestre': 'II',
         'mois': 'Janvier',
         'francais': 'L : 32-40+ intégration L : 41-42',
         'maths': 'SA1 fiche56-70 SA2 intégration fiche 71-75',
         'es_morale': 'SA6 -2 Séq2 SA7-1 Séq1',
         'es_civisme': 'SA6-2 Séq2 SA7-1 Séq1',
         'es_histoire': 'SA9 Séq3-4',
         'es_geographie': 'SA11 Séq3',
         'est': 'SA6 Séq1 à SA7 Séq5',
         'eps': 'SA7-8 Séq5-6 et 1-4',
         'ea_chant': 'SA7',
         'ea_poesie': 'SA4',
         'ea_conte': 'SA4',
         'ea_dessin': 'SA6',
         'ea_couture': 'SA10',
         'observations': ''},
        {'trimestre': 'II',
         'mois': 'Février',
         'francais': 'L :43-51',
         'maths': 'SA2 fiche 76 SA3 fiche 90',
         'es_morale': 'SA7-1 Séq2-4',
         'es_civisme': 'SA7-1 Séq2-4',
         'es_histoire': 'SA9',
         'es_geographie': 'SA11',
         'est': 'SA1 Séq 1 à 5',
         'eps': 'SA9-10 Séq1-4',
         'ea_chant': 'SA7',
         'ea_poesie': 'SA4',
         'ea_conte': 'SA4',
         'ea_dessin': 'SA6',
         'ea_couture': 'SA10',
         'observations': ''},
        {'trimestre': 'II',
         'mois': 'Mars',
         'francais': 'L : 52-54 + intégration L : 55-56',
         'maths': 'SA4 Fiche 91-95 + intég fiche 96-100 évaluation',
         'es_morale': 'SA7-1 Séq5 SA7-2 Séq1',
         'es_civisme': 'SA7-1 Séq5 SA7-2 Séq1 évaluation',
         'es_histoire': 'SA9',
         'es_geographie': 'SA11',
         'est': 'SA2 Séq1 à SA3 Séq4',
         'eps': 'SA10 Séq1 SA12-13 Séq4',
         'ea_chant': 'SA9',
         'ea_poesie': 'SA4',
         'ea_conte': 'SA4',
         'ea_dessin': 'SA11',
         'ea_couture': 'SA12',
         'observations': "Évaluation sommative d'étape 2"},
        {'trimestre': 'III',
         'mois': 'Avril',
         'francais': 'L :57-65',
         'maths': 'SA4 fiche 106 SA5 fiche 115',
         'es_morale': 'SA7-2 Séq2 SA7-3 Séq1',
         'es_civisme': 'SA7-2 Séq2 SA7-3 Séq1',
         'es_histoire': 'SA10',
         'es_geographie': 'SA11',
         'est': 'SA3 Séq5 SA6 Séq4',
         'eps': 'SA12-13 Séq5 SA3 Séq5',
         'ea_chant': 'SA9 SA13',
         'ea_poesie': 'SA4',
         'ea_conte': 'SA11-15',
         'ea_dessin': 'SA11',
         'ea_couture': 'SA12-14',
         'observations': ''},
        {'trimestre': 'III',
         'mois': 'Mai',
         'francais': 'L :66-68+ intégration L : 69-70 +lecture des textes 1 à4',
         'maths': 'SA5 fiche 116 -120 + intégration fiche 121 à SA6 fiche 135',
         'es_morale': 'SA7-3 Séq2 SA7-4 Séq2',
         'es_civisme': 'SA7-3 Séq2 SA7-4 Séq2',
         'es_histoire': 'SA10',
         'es_geographie': 'SA11',
         'est': 'SA7 Séq1-7',
         'eps': 'SA3 Séq6 SA4 séq4',
         'ea_chant': 'SA16',
         'ea_poesie': 'SA4',
         'ea_conte': 'SA4',
         'ea_dessin': 'SA15',
         'ea_couture': 'SA14',
         'observations': ''},
        {'trimestre': 'III',
         'mois': 'Juin',
         'francais': 'Lecture des textes 5 et 6',
         'maths': 'SA6 fiche 136-140',
         'es_morale': 'SA7-4 Séq3',
         'es_civisme': 'SA7-4 Séq3',
         'es_histoire': 'Renforcement intégration',
         'es_geographie': 'Renforcement intégration',
         'est': 'Renforcement intégration',
         'eps': 'Intégration',
         'ea_chant': 'SA16+ intégration',
         'ea_poesie': 'SA4 + intégration',
         'ea_conte': 'SA4 + intégration',
         'ea_dessin': 'SA15+ intégration',
         'ea_couture': 'SA14+ intégration',
         'observations': "Évaluation sommative d'étape 3"}],
 'CE1': [{'trimestre': 'I',
          'mois': 'Septembre',
          'francais': 'Diphtongue',
          'maths': 'D1 SA1 séq 1 à 2',
          'es_morale': 'SA1 Séq 1',
          'es_civisme': 'SA1 Séq1',
          'es_histoire': 'SA6 Séq1',
          'es_geographie': 'SA2 Séq1',
          'est': 'SA1 Séq1-3',
          'eps': 'SA1 Séq1 et2',
          'ea_chant': 'SA7 Séq1',
          'ea_poesie': 'SA9 Séq1',
          'ea_conte': 'SA11 Séq1',
          'ea_dessin': 'SA4 Séq1',
          'ea_couture': 'SA2 Séq2',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Octobre',
          'francais': 'Diphtongue',
          'maths': 'D1 SA2 séq1 à D2 SA1 séq 14',
          'es_morale': 'SA1 Séq1-2',
          'es_civisme': 'SA1 Séq1-4',
          'es_histoire': 'SA6 Séq2-3',
          'es_geographie': 'SA2 Séq2-4',
          'est': 'SA1 Séq4 SA2 Séq3',
          'eps': 'SA1 Séq3 SA2 séq4',
          'ea_chant': 'SA7 séq2-5',
          'ea_poesie': 'SA9 Séq2-5',
          'ea_conte': 'SA11 Séq2-5',
          'ea_dessin': 'SA4 Séq2-5',
          'ea_couture': 'SA2 Séq2-5',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Novembre',
          'francais': 'U1 et2',
          'maths': 'D2 SA1 Séq1 à D2 SA3 Séq1',
          'es_morale': 'SA1 Séq1-4',
          'es_civisme': 'SA1 Séq1-4',
          'es_histoire': 'SA6 Séq4-6',
          'es_geographie': 'SA2-5-9',
          'est': 'SA2 Séq4 SA3 Séq6',
          'eps': 'SA2 Séq5 SA3 Séq1',
          'ea_chant': 'SA7 Séq6-13',
          'ea_poesie': 'SA9 Séq6-9',
          'ea_conte': 'SA11 Séq6-9',
          'ea_dessin': 'SA4 Séq6-9',
          'ea_couture': 'SA2 Séq6-9',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Décembre',
          'francais': 'U3',
          'maths': 'D3 SA2 Séq1 à 5 Intégration',
          'es_morale': 'SA1 Séq4 suite',
          'es_civisme': 'Sa1 Séq5-6',
          'es_histoire': 'Renforcement',
          'es_geographie': 'SA2 Séq10-11',
          'est': 'SA3 Séq7 SA4 Séq2',
          'eps': 'SA3 Séq2-5',
          'ea_chant': 'SA7 Séq14-17',
          'ea_poesie': 'SA9 Séq10-11',
          'ea_conte': 'SA11 Séq10-11',
          'ea_dessin': 'SA4 Séq10-11',
          'ea_couture': 'SA2 Séq10-11',
          'observations': "Évaluation sommative d'étape 3"},
         {'trimestre': 'II',
          'mois': 'Janvier',
          'francais': 'U4 et 5 semaine 1',
          'maths': 'D3 SA2 Séq7 à D4 SA2 séq13',
          'es_morale': 'SA1 Séq5-6',
          'es_civisme': 'SA1 Séq7-11',
          'es_histoire': 'SA6 Séq7',
          'es_geographie': 'SA2 Séq12-16',
          'est': 'SA4 séq3 SA5 Séq5',
          'eps': 'SA3 Séq6 SA4 séq1',
          'ea_chant': 'SA7 Séq18-25',
          'ea_poesie': 'SA9 Séq12-15',
          'ea_conte': 'SA11 Séq12-15',
          'ea_dessin': 'SA4 Séq12-15',
          'ea_couture': 'SA2 Séq12-15',
          'observations': ''},
         {'trimestre': 'II',
          'mois': 'Février',
          'francais': 'U5 semaine2 U6',
          'maths': 'D4 SA3 Séq1 D5 SA1 Séq11',
          'es_morale': 'Renforcement',
          'es_civisme': 'SA3 Séq1-3',
          'es_histoire': 'Renforcement',
          'es_geographie': 'SA2 Séq17-20',
          'est': 'SA6 Séq1 SA7 Séq1',
          'eps': 'SA4 Séq2-5',
          'ea_chant': 'SA7 Séq26-29',
          'ea_poesie': 'SA9 Séq16-17',
          'ea_conte': 'SA11 Séq16-17',
          'ea_dessin': 'SA4 Séq16-17',
          'ea_couture': 'SA2 Séq16-17',
          'observations': ''},
         {'trimestre': 'II',
          'mois': 'Mars',
          'francais': 'U7 & 8',
          'maths': 'D5 SA2 séq1 à D5 SA3 Séq4 Intégration',
          'es_morale': 'renforcement',
          'es_civisme': 'SA3 Séq1-8',
          'es_histoire': 'SA6 Séq8',
          'es_geographie': 'SA2 Séq 21-25',
          'est': 'SA7 Séq2 SA8 Séq3',
          'eps': 'SA4 Séq6 SA5 séq3',
          'ea_chant': 'Sa7 séq30-36',
          'ea_poesie': 'SA9 Séq18-21',
          'ea_conte': 'SA11 Séq18-21',
          'ea_dessin': 'SA4 Séq18-21',
          'ea_couture': 'SA2 Séq18-21',
          'observations': "Évaluation sommative d'étape 2"},
         {'trimestre': 'III',
          'mois': 'Avril',
          'francais': 'Unité 9',
          'maths': 'D8 SA2 à D8 SA3 Séq3',
          'es_morale': 'Renforcement',
          'es_civisme': 'SA3 Séq9-14',
          'es_histoire': 'SA6 Séq9',
          'es_geographie': 'SA2 Séq26-27',
          'est': 'SA8 séq4-5',
          'eps': 'SA5 Séq4-9',
          'ea_chant': 'SA7 Séq37-42',
          'ea_poesie': 'SA9 Séq22-24',
          'ea_conte': 'SA11 Séq22-24',
          'ea_dessin': 'SA4 Séq22-24',
          'ea_couture': 'SA2 Séq22-24',
          'observations': ''},
         {'trimestre': 'III',
          'mois': 'Mai',
          'francais': 'Unité 11',
          'maths': 'D7 SA2 Séq1 à D8 Séq12',
          'es_morale': 'renforcement',
          'es_civisme': 'SA3 Séq15-16',
          'es_histoire': 'Sa6 séq9',
          'es_geographie': 'SA2 Séq28-32',
          'est': 'Intégration',
          'eps': 'SA5 Séq10 SA6 Séq6',
          'ea_chant': 'SA7 Séq43-50',
          'ea_poesie': 'SA9 Séq25-29',
          'ea_conte': 'SA11 Séq25-28',
          'ea_dessin': 'SA4 Séq25-28',
          'ea_couture': 'SA2 Séq25-28',
          'observations': ''},
         {'trimestre': 'III',
          'mois': 'Juin',
          'francais': 'Renforcement intégration',
          'maths': 'D8 SA2 Séq1 à D8 SA3 Séq1. Renforcement +intégration',
          'es_morale': 'Renforcement +intégration',
          'es_civisme': 'Renforcement +intégration +évaluation',
          'es_histoire': 'Renforcement +intégration +évaluation',
          'es_geographie': 'Renforcement',
          'est': 'Intégration',
          'eps': 'SA6 Séq7 et8',
          'ea_chant': 'SA7 Séq51-55',
          'ea_poesie': 'Renforcement +intégration +évaluation',
          'ea_conte': 'Intégration',
          'ea_dessin': 'Intégration',
          'ea_couture': 'Intégration',
          'observations': "Évaluation sommative d'étape 3"}],
 'CE2': [{'trimestre': 'I',
          'mois': 'Septembre',
          'francais': 'U1',
          'maths': 'D1 SA1 à D1 SA2 Séq5',
          'es_morale': 'SA1 Séq1',
          'es_civisme': 'SA2 Séq1',
          'es_histoire': 'SA3 Séq1',
          'es_geographie': 'SA4 Séq1',
          'est': 'SA1 Séq 1 à 3',
          'eps': 'SA1 Séq1-3',
          'ea_chant': 'SA22 Séq1-2',
          'ea_poesie': 'SA9 Séq1',
          'ea_conte': 'SA1 Séq1-2',
          'ea_dessin': 'SA20 Séq1-2',
          'ea_couture': 'SA23 Séq1-2',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Octobre',
          'francais': 'U2 à 3',
          'maths': 'D1 SA2 à D2 SA2 Séq5',
          'es_morale': 'SA1 Séq2-5',
          'es_civisme': 'SA2 Séq2-5',
          'es_histoire': 'SA3 Séq2 SA5 Séq1',
          'es_geographie': 'SA6 Séq1 SA4 Séq2',
          'est': 'SA1 : Séq4 SA2 Séq7',
          'eps': 'SA1 Séq4 SA2 Séq1',
          'ea_chant': 'SA22 Séq3-6',
          'ea_poesie': 'SA9 Séq2-3',
          'ea_conte': 'SA1 Séq3-6',
          'ea_dessin': 'SA20 Séq3-6',
          'ea_couture': 'SA23 Séq2-6',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Novembre',
          'francais': 'U4 à5',
          'maths': 'D2 SA3 à D3 SA3 Séq5',
          'es_morale': 'SA1 Séq6-9',
          'es_civisme': 'SA2 Séq6-9',
          'es_histoire': 'SA3 Séq3 SA5 Séq2',
          'es_geographie': 'SA6 Séq2 SA4 Séq3 SA5 Séq3',
          'est': 'SA3 Séq 1 SA4 Séq3',
          'eps': 'SA2 Séq2-9',
          'ea_chant': 'SA22 Séq7-9',
          'ea_poesie': 'SA9 Séq 4-5',
          'ea_conte': 'SA1 Séq7-10',
          'ea_dessin': 'SA20 Séq7-10',
          'ea_couture': 'SA23 Séq7-9',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Décembre',
          'francais': 'U5 fin',
          'maths': 'D4 SA1 Séq1 à5',
          'es_morale': 'SA1 Séq10',
          'es_civisme': 'SA2 Séq10',
          'es_histoire': 'SA6 Séq3',
          'es_geographie': 'SA3 Séq3',
          'est': 'SA4 Séq4 SA5 Séq2',
          'eps': 'SA2 Séq10 SA3 Séq3',
          'ea_chant': 'SA22 Séq10',
          'ea_poesie': 'SA9 Séq 6',
          'ea_conte': 'SA1 Séq11',
          'ea_dessin': 'SA20 Séq11',
          'ea_couture': 'SA23 Séq10',
          'observations': "Évaluation sommative d'étape 1"},
         {'trimestre': 'II',
          'mois': 'Janvier',
          'francais': 'U6 à 7',
          'maths': 'D4 SA2 à D5 SA2 Séq5',
          'es_morale': 'SA1 Séq11-12',
          'es_civisme': 'SA2 Séq11-12',
          'es_histoire': 'SA4 Séq4 et SA6 Séq4',
          'es_geographie': 'SA5 Séq4 SA3 Séq5',
          'est': 'SA5 Séq3 SA5 Séq10',
          'eps': 'SA3 Séq4 SA4 Séq4',
          'ea_chant': 'SA22 Séq11',
          'ea_poesie': 'SA9 Séq7',
          'ea_conte': 'SA1 Séq12',
          'ea_dessin': 'SA20 Séq12',
          'ea_couture': 'SA24 Séq11',
          'observations': ''},
         {'trimestre': 'II',
          'mois': 'Février',
          'francais': 'U8',
          'maths': 'D5 SA3 à D6 SA1 Séq5',
          'es_morale': 'SA1 Séq13-14',
          'es_civisme': 'SA2 Séq13-14',
          'es_histoire': 'SA4',
          'es_geographie': 'SA5 Séq5',
          'est': 'SA5 Séq11 SA6 Séq 6',
          'eps': 'SA4 Séq5 SA5 Séq4',
          'ea_chant': 'SA22 Séq12',
          'ea_poesie': 'SA9 Séq8',
          'ea_conte': 'SA1 Séq13',
          'ea_dessin': 'SA20 Séq13',
          'ea_couture': 'SA24 Séq12',
          'observations': ''},
         {'trimestre': 'II',
          'mois': 'Mars',
          'francais': 'U9',
          'maths': 'D6 SA2 à D6 SA3 Séq5',
          'es_morale': 'SA1 Séq15-17',
          'es_civisme': 'SA2 Séq15-17',
          'es_histoire': 'SA4 Séq6 SA6 Séq6',
          'es_geographie': 'SA3 Séq6',
          'est': 'SA6 Séq6 à SA8 Séq 8',
          'eps': 'SA5 Séq5- + Activité de renforcement',
          'ea_chant': 'SA22 Séq13-14',
          'ea_poesie': 'SA9 Séq9-10',
          'ea_conte': 'SA25 Séq14-15',
          'ea_dessin': 'SA20 Séq14-15',
          'ea_couture': 'SA24 Séq13-14',
          'observations': "Évaluation sommative d'étape 2"},
         {'trimestre': 'III',
          'mois': 'Avril',
          'francais': 'U10',
          'maths': 'D7 SA1 Séq 1 à 7',
          'es_morale': 'SA1 Séq18-19',
          'es_civisme': 'SA2 Séq18',
          'es_histoire': 'SA6 Séq6 SA3 Séq7',
          'es_geographie': 'SA5 Séq6',
          'est': 'SA8 Séq3 à SA9 Séq2',
          'eps': '',
          'ea_chant': 'SA22 Séq 15-16',
          'ea_poesie': 'SA9 Séq11-12',
          'ea_conte': 'SA25 Séq16-17',
          'ea_dessin': 'SA20 Séq16-17',
          'ea_couture': 'SA24 Séq15-16',
          'observations': ''},
         {'trimestre': 'III',
          'mois': 'Mai',
          'francais': 'U11 à 12',
          'maths': 'D7-2 D8-1 Séq1-5',
          'es_morale': 'SA1 Séq20-23',
          'es_civisme': 'SA2 Séq19-23',
          'es_histoire': 'SA4 Séq SA6 Séq7',
          'es_geographie': 'SA5 Séq7',
          'est': 'SA9 Séq3 à 5',
          'eps': '',
          'ea_chant': 'SA22 Séq17-20',
          'ea_poesie': 'SA9 Séq13-16',
          'ea_conte': 'SA25 Séq18-21',
          'ea_dessin': 'SA20 Séq18-21',
          'ea_couture': 'SA24 Séq17-20',
          'observations': ''},
         {'trimestre': 'III',
          'mois': 'Juin',
          'francais': 'Intégration',
          'maths': 'D8-2 à D9-1 intégration',
          'es_morale': 'SA1 Séq 24-25 intégration',
          'es_civisme': 'SA2 Séq24-25 intégration',
          'es_histoire': 'SA6 Séq7 intégration',
          'es_geographie': 'Renforcement +intégration',
          'est': 'Intégration',
          'eps': 'Intégration',
          'ea_chant': 'SA22 Séq21-22 +intégration',
          'ea_poesie': 'SA9 Séq 17-18 intégration',
          'ea_conte': 'SA9 Séq17-18 intégration',
          'ea_dessin': 'SA20 Séq22-23 intégration',
          'ea_couture': 'SA24 Séq21-22 intégration',
          'observations': "Évaluation sommative d'étape 3"}],
 'CM1': [{'trimestre': 'I',
          'mois': 'Septembre',
          'francais': 'Évaluation diagnostique U1 Semaine 1',
          'maths': 'Évaluation diagnostique D1 SA1-1 à 7',
          'es_morale': 'SA8 Séq1',
          'es_civisme': 'SA1 Séq 1 et 2',
          'es_histoire': 'SA2 Séq1',
          'es_geographie': 'SA6 Séq 6',
          'est': 'SA1 Séq 1-3',
          'eps': 'SA1 Séq 1 à 3',
          'ea_chant': 'SA11 Séq 1',
          'ea_poesie': 'SA7 Séq 1',
          'ea_conte': 'SA 10 Séq1',
          'ea_dessin': 'SA8 Séq1',
          'ea_couture': 'SA6 Séq1',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Octobre',
          'francais': 'U1 semaine2 à U3 semaine 1',
          'maths': 'D1 SA1 Séq 8 à 15 SA2 et 3',
          'es_morale': 'SA8 Séq2-5',
          'es_civisme': 'SA1 Séq 3 à10',
          'es_histoire': 'SA2 Séq2-4',
          'es_geographie': 'SA6 Séq2-4',
          'est': 'SA1 Séq 4 à SA2 Séq2',
          'eps': 'SA1 Séq3-8',
          'ea_chant': 'SA11 Séq 2-3',
          'ea_poesie': 'SA7 Séq2-3',
          'ea_conte': 'SA10 Séq2',
          'ea_dessin': 'SA8 Séq2-5',
          'ea_couture': 'SA6 Séq2 à 3',
          'observations': 'Langue et culture : SA5 Séq1-2'},
         {'trimestre': 'I',
          'mois': 'Novembre',
          'francais': 'Intégration + U3 semaine 2 à U4',
          'maths': 'Intégration + D2 SA1 à SA3',
          'es_morale': 'SA8 Séq 6-9',
          'es_civisme': 'SA1 Séq 11 à 18',
          'es_histoire': 'SA2 Séq5-7',
          'es_geographie': 'SA6 Séq 5-7',
          'est': 'SA2 Séq3 à SA3 Séq2',
          'eps': 'SA1 Séq9 à SA2 Séq1',
          'ea_chant': 'SA11 Séq4-5',
          'ea_poesie': 'SA7 Séq4-5',
          'ea_conte': 'SA10 Séq3-4',
          'ea_dessin': 'SA8 Séq6-7',
          'ea_couture': 'SA6 Séq4-5',
          'observations': 'Langue et culture : SA5 Séq 3-4'},
         {'trimestre': 'I',
          'mois': 'Décembre',
          'francais': 'U5 1ère et 2ème semaine + révision',
          'maths': 'D3 SA1 à SA2',
          'es_morale': 'SA8 Séq10-11',
          'es_civisme': 'SA1 Séq19-22',
          'es_histoire': 'SA2 Séq8-9',
          'es_geographie': 'SA6 Séq8-9',
          'est': 'SA3 Séq3-6',
          'eps': 'SA2 Séq2-5',
          'ea_chant': 'SA11 Séq6',
          'ea_poesie': 'SA7 Séq6',
          'ea_conte': 'SA10 Séq5',
          'ea_dessin': 'SA8 Séq11',
          'ea_couture': 'SA6 Séq6',
          'observations': "Évaluation sommative d'étape 1"},
         {'trimestre': 'II',
          'mois': 'Janvier',
          'francais': 'U6 à U7',
          'maths': 'D3 SA2 à SA3',
          'es_morale': 'Sa8 Séq12-15',
          'es_civisme': 'SA1 Séq23-27',
          'es_histoire': 'SA2 Séq10-12',
          'es_geographie': 'SA6 Séq10-12',
          'est': 'SA4 Séq4 à6',
          'eps': 'SA2 Séq6 à13',
          'ea_chant': 'SA11 Séq7',
          'ea_poesie': 'SA7 Séq7',
          'ea_conte': 'SA10 Séq 10',
          'ea_dessin': 'SA8 Séq15',
          'ea_couture': 'SA6 Séq7',
          'observations': 'Langue et culture : SA5 Séq5-6'},
         {'trimestre': 'II',
          'mois': 'Février',
          'francais': 'U8',
          'maths': 'D4 SA1 à SA2',
          'es_morale': 'SA8 Séq16-17',
          'es_civisme': 'SA1 Séq21 à23',
          'es_histoire': 'SA2 Séq10-11',
          'es_geographie': 'SA6 Séq13',
          'est': 'SA5 Séq1 à SA6 Séq2',
          'eps': 'SA2 Séq14 à SA3 Séq4',
          'ea_chant': 'SA11 Séq8',
          'ea_poesie': 'SA7 Séq8',
          'ea_conte': 'SA10 Séq7',
          'ea_dessin': 'SA8 Séq19',
          'ea_couture': 'SA6 Séq8',
          'observations': 'Langue et culture : SA7 Séq1'},
         {'trimestre': 'II',
          'mois': 'Mars',
          'francais': 'U9 à U10',
          'maths': 'D5',
          'es_morale': 'Révision',
          'es_civisme': 'SA1 Séq 24 à 25',
          'es_histoire': 'SA2 Séq 12 à 13',
          'es_geographie': 'Révision',
          'est': 'SA6 (suite) à SA7 Séq2',
          'eps': 'SA3 Séq 5 à 10',
          'ea_chant': 'SA10 Séq9',
          'ea_poesie': 'SA10 Séq8',
          'ea_conte': 'SA10 Séq 8',
          'ea_dessin': 'SA8 Séq 19 à 22',
          'ea_couture': 'SA6 Séq9',
          'observations': "Langue et culture : SA7 Séq2 ; Évaluation sommative d'étape 2"},
         {'trimestre': 'III',
          'mois': 'Avril',
          'francais': 'U11',
          'maths': 'D5',
          'es_morale': 'Révision',
          'es_civisme': 'Révision',
          'es_histoire': 'SA2 Séq14-15',
          'es_geographie': 'Révision',
          'est': 'SA7 Séq3-8',
          'eps': 'SA3 Séq11 à 17',
          'ea_chant': 'SA11 Séq12',
          'ea_poesie': 'SA7 Séq10',
          'ea_conte': 'SA10 Séq9',
          'ea_dessin': 'SA2 Séq23-27',
          'ea_couture': 'SA6 Séq10',
          'observations': 'Langue et culture : SA7 Séq3+ révision'},
         {'trimestre': 'III',
          'mois': 'Mai',
          'francais': 'U12',
          'maths': 'D5',
          'es_morale': 'Révision',
          'es_civisme': 'Révision',
          'es_histoire': 'Révision',
          'es_geographie': 'Révision',
          'est': 'Révision',
          'eps': 'SA3 Séq18 à 20',
          'ea_chant': 'SA11 Séq11',
          'ea_poesie': 'SA7 Séq11',
          'ea_conte': 'SA10 Séq10',
          'ea_dessin': 'SA8 Séq28 à31',
          'ea_couture': 'SA6 Séq11',
          'observations': 'Langue et culture : Révision'},
         {'trimestre': 'III',
          'mois': 'Juin',
          'francais': 'Révision',
          'maths': 'D5 + Révision',
          'es_morale': 'Révision',
          'es_civisme': 'Révision',
          'es_histoire': 'Révision',
          'es_geographie': 'Révision',
          'est': 'Révision',
          'eps': 'Révision',
          'ea_chant': 'SA11 Séq12',
          'ea_poesie': 'SA7 Séq12',
          'ea_conte': 'SA10 Séq11',
          'ea_dessin': 'SA8 Séq32 à 35',
          'ea_couture': 'SA6 Séq12',
          'observations': "Langue et culture : Révision ; Évaluation sommative d'étape 3"}],
 'CM2': [{'trimestre': 'I',
          'mois': 'Septembre',
          'francais': 'U1 :1ère semaine U1 SA1 à SA4 (10ème séance)',
          'maths': 'D1 SA1 séq 1 - 5',
          'es_morale': 'SA1 P94 à 96',
          'es_civisme': 'SA1 P14 à 24',
          'es_histoire': 'SA3',
          'es_geographie': 'SA2 P158 à 159',
          'est': 'Évaluation diagnostique SA1 Séq 1et2',
          'eps': 'Nettoyage + traçage du terrain',
          'ea_chant': 'Évaluation diagnostique',
          'ea_poesie': 'Évaluation diagnostique',
          'ea_conte': 'Évaluation diagnostique',
          'ea_dessin': 'Évaluation diagnostique',
          'ea_couture': 'Évaluation diagnostique',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Octobre',
          'francais': 'U1 SA5 à U3 SA7',
          'maths': 'D1-1 Séq 6 à D1-3 Séq5',
          'es_morale': 'SA 1 p 98 à 100',
          'es_civisme': 'SA1 P26 à 40',
          'es_histoire': 'SA3',
          'es_geographie': 'SA2 P159 à 171',
          'est': 'SA1 séq3 à 9 SA2 Séq 1',
          'eps': 'SA 1 Séq 1 à 7',
          'ea_chant': 'SA6',
          'ea_poesie': 'SA6 Séq 1-2',
          'ea_conte': 'SA6 Séq 1',
          'ea_dessin': 'SA3 Séq 1',
          'ea_couture': 'SA5séq1-2',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Novembre',
          'francais': 'U3 SA6 à U5 SA6 ( 3ème séance)',
          'maths': 'D1 SA2 et 3 séance 6à D2 SA1 séance10',
          'es_morale': 'SA1 P107 à p 110',
          'es_civisme': 'SA1 P48 à 56',
          'es_histoire': 'SA3 Séq 1 à 3',
          'es_geographie': 'SA2 P 174 à 178',
          'est': 'SA 2 Séq 2 à SA3 Séq2',
          'eps': 'Sa1 Séq 8 à 15',
          'ea_chant': 'Activité rythmique et vocale',
          'ea_poesie': 'SA6 Séq 3-4',
          'ea_conte': 'SA6séq 2-3',
          'ea_dessin': 'SA3 séq 2-5',
          'ea_couture': 'SA5 séq3-4',
          'observations': ''},
         {'trimestre': 'I',
          'mois': 'Décembre',
          'francais': 'U5 SA6 3è à séance à U 6 SA7 1ère séance',
          'maths': 'D2 SA1 et 2 séance11 à D2 SA1 et 2 séance 3',
          'es_morale': 'SA1 P 112 à 114',
          'es_civisme': 'SA1 P 58 à P60',
          'es_histoire': 'SA3',
          'es_geographie': 'SA2 P 180 à 182',
          'est': 'SA3 Séq 3 à 5',
          'eps': 'SA2 Séq 1 à 3',
          'ea_chant': 'SA6 et SA9',
          'ea_poesie': 'SA6 Séq 5',
          'ea_conte': 'SA6 séq4-5',
          'ea_dessin': 'SA3 séq 6-9',
          'ea_couture': 'SA5 séq5',
          'observations': "Évaluation sommative d'étape 1"},
         {'trimestre': 'II',
          'mois': 'Janvier',
          'francais': 'U7 SA1 à U8 SA8 1ère séance',
          'maths': 'D2 SA 2 et3 Séance 4 à D3 SA 1 et 2 séance3',
          'es_morale': 'SA1 p115 à P116',
          'es_civisme': 'SA1 P 64 à P70',
          'es_histoire': 'SA3',
          'es_geographie': 'SA2 P 184 à P190',
          'est': 'SA3 Séq 6 à SA4 Séq5',
          'eps': 'SA Séq4 à 12',
          'ea_chant': 'SA6 et SA9',
          'ea_poesie': 'SA6Séq 6-7',
          'ea_conte': 'SA6séq 6-7',
          'ea_dessin': 'SA3séq10-14',
          'ea_couture': 'SA5séq6-7',
          'observations': ''},
         {'trimestre': 'II',
          'mois': 'Février',
          'francais': 'U9 SA1 à U10 SA5',
          'maths': 'D3 SA1 et 2 séance4 à D4 SA1 séance1 à 10',
          'es_morale': 'SA1 P120 à P124',
          'es_civisme': 'SA1 P 72 à p140',
          'es_histoire': 'SA3',
          'es_geographie': 'SA2 P 192 à p194',
          'est': 'SA4 Séq6 à SA5 Séq5',
          'eps': 'SA2 Séq13 à SA3 Séq1',
          'ea_chant': 'SA9',
          'ea_poesie': 'SA6 séq8',
          'ea_conte': 'SA6 séq8',
          'ea_dessin': 'SA3 séq14-16',
          'ea_couture': 'SA5 séq8',
          'observations': ''},
         {'trimestre': 'II',
          'mois': 'Mars',
          'francais': 'U10 SA6 2ème séanceàU12 SA4 1ère Séance',
          'maths': 'D4 SA1 Séance1 à D4 sa2 séance7 + intégration',
          'es_morale': 'SA1 P126',
          'es_civisme': 'SA1 P144 à p151',
          'es_histoire': 'SA3',
          'es_geographie': 'SA2',
          'est': 'Bilan',
          'eps': 'SA3 Séq 2à 7',
          'ea_chant': 'Évaluation sommative',
          'ea_poesie': 'Évaluation sommative',
          'ea_conte': 'Évaluation sommative',
          'ea_dessin': 'SA3séq17-20',
          'ea_couture': 'SA5 séq9-11',
          'observations': "Évaluation sommative d'étape 2"},
         {'trimestre': 'III',
          'mois': 'Avril',
          'francais': 'Intégration U12 SA5 à7 révision',
          'maths': 'D5 intégration + évaluation',
          'es_morale': 'renforcement',
          'es_civisme': 'renforcement',
          'es_histoire': 'renforcement',
          'es_geographie': 'renforcement',
          'est': 'renforcement',
          'eps': 'renforcement',
          'ea_chant': 'SA4 Séq4-6',
          'ea_poesie': 'SA6 Séq11-13',
          'ea_conte': 'SA6 Séq11',
          'ea_dessin': 'SA3 Séq21-24',
          'ea_couture': 'SA5 Séq12 et 13',
          'observations': ''},
         {'trimestre': 'III',
          'mois': 'Mai',
          'francais': 'U 12 révision',
          'maths': 'Renforcement',
          'es_morale': 'renforcement',
          'es_civisme': 'Renforcement',
          'es_histoire': 'Renforcement',
          'es_geographie': 'renforcement',
          'est': 'Renforcement',
          'eps': 'renforcement',
          'ea_chant': '',
          'ea_poesie': '',
          'ea_conte': '',
          'ea_dessin': 'SA3 Séq 24-28',
          'ea_couture': '',
          'observations': ''},
         {'trimestre': 'III',
          'mois': 'Juin',
          'francais': 'CEP',
          'maths': '',
          'es_morale': '',
          'es_civisme': '',
          'es_histoire': '',
          'es_geographie': '',
          'est': '',
          'eps': '',
          'ea_chant': '',
          'ea_poesie': '',
          'ea_conte': '',
          'ea_dessin': '',
          'ea_couture': '',
          'observations': 'Examen du CEP'}]}
