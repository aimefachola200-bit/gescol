# -*- coding: utf-8 -*-
"""Thèmes d'unité pédagogique (UP), de conférence pédagogique (CP) et de formation groupée (FG) — toutes éditions
(GESCOL, GESCOL Public, CS, DDEMP) — v1.6.

Le client demande « le thème de l'UP dans les 4 applications comme le PDF » de la Direction de l'Inspection et de
l'Innovation Pédagogiques (DIIP) : « Planning d'exécution des thèmes d'unité pédagogique au titre de l'année
scolaire 2026-2027 » (N°, Thèmes, Axes de réflexion indicatifs, Dates de déroulement : Préparation / Interprétation /
Administration, Observations : animation libre / mixte) et « Planning d'exécution des thèmes de conférence
pédagogique et de formation groupée » (N°, Thèmes, Contenus indicatifs, Dates de déroulement, Observations).
NB du texte : conformément à l'arrêté n° 003/MEMP/DC/SGM/DPAF/DEM/DEP/DIIP/SP 041 SGG25 du 17 février 2026, dérouler
par trimestre un thème de conférence pédagogique et un thème de formation groupée.

* Table ``themes_up`` : une ligne par thème (id, ecole_id, annee, categorie, numero, theme, axes (multi-lignes),
  date_preparation, date_interpretation, date_administration, date_deroulement, observations, officiel 1/0,
  execute 0/1, date_execution, lieu, participants, compte_rendu, maj, maj_par).
  ``ecole_id`` = école courante (``H.eco()``) ; 0 = planning commun de la structure (CS / DDEMP sans école ouverte,
  onglet du synoptique de la structure, ou ``?portee=structure``).
  Table ``themes_up_meta`` (ecole_id, annee, reference, source, maj) : référence du texte.
* Catégories : up_maternelle, up_primaire (dates : préparation, interprétation, administration = date de l'UP),
  conference, formation_groupee (date de déroulement). Les dates sont enregistrées en ISO (aaaa-mm-jj) quand elles
  sont connues, sinon telles quelles (« PM » = pour mémoire, « - ») ; une date ISO est affichée « Vendredi 23/10/2026 ».
* Préremplissage : à la première ouverture d'une année connue (``THEMES_OFFICIELS`` : 2026-2027, transcription
  fidèle du PDF de la DIIP : 12 thèmes d'UP maternelle, 12 d'UP primaire, 5 conférences, 5 formations groupées),
  les thèmes officiels (``officiel = 1``) sont insérés.
* Boutons : Ajouter / Modifier / Supprimer, Recharger (remet seulement les thèmes officiels, garde les ajouts),
  Réinitialiser (supprime tout pour l'année puis remet l'officiel), Préparer l'année suivante (copie décalée d'un
  an, à corriger), Export Excel, Import (modèle ; l'import REMPLACE les thèmes de l'année pour les catégories
  présentes dans le fichier), PDF (paysage, proche du PDF officiel, en-tête école ou CS / DDEMP).
* Onglet « Suivi » : pour chaque catégorie, thèmes exécutés / à venir / en retard, taux d'exécution, et par
  trimestre (I : septembre → décembre, II : janvier → mars, III : avril → août) nombre de thèmes programmés et
  exécutés ; contrôle de la règle « un thème de CP et un de FG par trimestre ».

Règles de calcul (fonctions pures) :
* date de référence d'un thème = date d'exécution si elle est renseignée, sinon date d'administration (UP) ou de
  déroulement (CP / FG) quand elle est une vraie date ;
* trimestre d'un thème = trimestre de sa date de référence ; sans date : « à planifier » ;
* taux d'exécution (%) = 100 × exécutés ÷ total, arrondi à l'unité ; « — » sans thème ;
* à venir = non exécuté et date ≥ aujourd'hui ; en retard = non exécuté et date < aujourd'hui.

Exposé : ``H.themes_up(annee, categorie=None, ecole_id=None)`` (liste de dicts ; à défaut de saisie pour l'école,
le planning de la structure, puis la liste officielle). Droits : lecture pour tout utilisateur connecté (le rôle
enseignant consulte seulement) ; écriture avec le droit ``themes_up``. Journal sur chaque écriture.
Avec ``?retour=synoptique`` (école) ou ``?retour=jur_synoptique`` (CS / DDEMP), la page s'affiche dans les onglets
du tableau synoptique correspondant.
"""
import io
import re
from datetime import date, datetime

from flask import abort, flash, g, redirect, render_template, request, url_for

import config

CATEGORIES = [("up_maternelle", "UP maternelle"), ("up_primaire", "UP primaire"),
              ("conference", "Conférences pédagogiques"), ("formation_groupee", "Formations groupées")]
CATEGORIES_LIB = dict(CATEGORIES)
CATEGORIES_UP = ("up_maternelle", "up_primaire")
ONGLETS = CATEGORIES + [("suivi", "Suivi")]
TRIMESTRES = [("I", "1er trimestre"), ("II", "2e trimestre"), ("III", "3e trimestre")]
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
RE_ANNEE = re.compile(r"^(\d{4})-(\d{4})$")
PM = "PM"

ENTETES_XLSX = ["Catégorie", "N°", "Thème", "Axes de réflexion / contenus indicatifs", "Préparation", "Interprétation",
                "Administration / date de déroulement", "Observations", "Officiel", "Exécuté", "Date d'exécution", "Lieu",
                "Participants", "Compte rendu"]

REFERENCE_2026 = ("Planning d'exécution des thèmes d'unité pédagogique, de conférence pédagogique et de formation groupée "
                  "au titre de l'année scolaire 2026-2027 — MEMP, Direction de l'Inspection et de l'Innovation Pédagogiques "
                  "(DIIP) ; arrêté n° 003/MEMP/DC/SGM/DPAF/DEM/DEP/DIIP/SP 041 SGG25 du 17 février 2026")
SOURCE_2026 = "MEMP / DIIP, année scolaire 2026-2027"
NB_ARRETE = ("NB : Conformément à l'arrêté N°003/MEMP/DC/SGM/DPAF/DEM/DEP/DIIP/SP 041 SGG25 du 17 février 2026, dérouler "
             "par trimestre, un thème de conférence pédagogique et un thème de formation groupée.")

SCHEMA = """
CREATE TABLE IF NOT EXISTS themes_up (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL DEFAULT 0,
    annee TEXT NOT NULL,
    categorie TEXT NOT NULL,              -- up_maternelle | up_primaire | conference | formation_groupee
    numero INTEGER DEFAULT 0,
    theme TEXT NOT NULL,
    axes TEXT,                            -- axes de réflexion / contenus indicatifs (une ligne par axe)
    date_preparation TEXT,                -- UP : « PM » ou date ISO
    date_interpretation TEXT,             -- UP : « PM » ou date ISO
    date_administration TEXT,             -- UP : date ISO (vendredi) ou texte
    date_deroulement TEXT,                -- CP / FG : « PM » ou date ISO
    observations TEXT,                    -- animation libre / mixte, « ce thème est à développer… »
    officiel INTEGER DEFAULT 0,
    execute INTEGER DEFAULT 0,
    date_execution TEXT,
    lieu TEXT,
    participants INTEGER,
    compte_rendu TEXT,
    maj TEXT, maj_par INTEGER
);
CREATE INDEX IF NOT EXISTS idx_themes_up ON themes_up (ecole_id, annee, categorie, numero);
CREATE TABLE IF NOT EXISTS themes_up_meta (
    ecole_id INTEGER NOT NULL DEFAULT 0,
    annee TEXT NOT NULL,
    reference TEXT, source TEXT, maj TEXT,
    PRIMARY KEY (ecole_id, annee)
);
"""


# ================================================================ thèmes officiels 2026-2027 (DIIP)
# Transcription du document docs_reference/themes_UP_CP_FG_2026-2027.pdf (9 pages).
# UP : (numéro, thème, axes, préparation, interprétation, administration (date ISO), observations)
_CHRONOPHAGES = ("Chasser les facteurs chronophages à l'école : stratégies organisationnelles et pédagogiques au service "
                 "de la réussite scolaire")
_AXES_CHRONOPHAGES = ("Clarification conceptuelle\nTypologie des ''voleurs de temps''\nDiagnostic des facteurs chronophages\n"
                      "Leviers organisationnels, pédagogiques, institutionnels et recommandations pratiques")
_DIFFERENCIEE = "La pédagogie différenciée et l'adaptation des pratiques en classe inclusive"
_AXES_DIFFERENCIEE = ("Clarification conceptuelle\nPrincipes de la pédagogie différenciée\nStratégies d'adaptation pédagogique "
                      "(méthodes actives, supports variés, évaluation adaptée)\nTechnologies d'assistance (tablettes, logiciels "
                      "spécialisés, etc.)\nGestion de la diversité et valorisation des talents de tous")
LIBRE, MIXTE = "Animation libre", "Animation mixte"

UP_MATERNELLE_2026 = [
    (1, "Renouvellement des bureaux", "-", "-", "-", "2026-10-09", ""),
    (2, _CHRONOPHAGES, _AXES_CHRONOPHAGES, PM, PM, "2026-10-23", LIBRE),
    (3, "Le projet pédagogique à l'enseignement maternel : élaboration et mise en œuvre",
     "Clarification conceptuelle\nIntérêt du projet pédagogique à l'EM\nÉtapes d'élaboration d'un projet pédagogique\n"
     "Démarche de mise en œuvre\nImplications pédagogiques", PM, PM, "2026-11-06", LIBRE),
    (4, _DIFFERENCIEE, _AXES_DIFFERENCIEE, PM, PM, "2026-11-20", LIBRE),
    (5, "Impact de l'utilisation du coin bibliothèque sur le développement cognitif de l'enfant",
     "Clarification conceptuelle\nImportance de l'exploitation du coin bibliothèque\nAménagement et accessibilité du coin "
     "bibliothèque\nRôle de l'enseignant dans l'animation du coin bibliothèque\nImpact du coin bibliothèque dans le "
     "développement socio-cognitif de l'enfant", PM, PM, "2026-12-04", MIXTE),
    (6, "La place du matériel dans la mise en œuvre de l'Observation à l'EM",
     "Clarification conceptuelle\nImportance du matériel dans la mise en œuvre de l'Observation\nChoix et préparation du "
     "matériel en fonction des objectifs de l'activité\nUtilisation du matériel par l'enfant au cours de l'activité\n"
     "Rôle de l'enseignant dans l'exploitation du matériel", PM, PM, "2027-01-15", LIBRE),
    (7, "Les activités de vie pratique à l'EM : fondements et démarche de mise en œuvre",
     "Clarification conceptuelle\nFondements et objectifs des activités de vie pratique\nTypologie des activités de vie "
     "pratique\nDémarche de mise en œuvre\nImplications pédagogiques", PM, PM, "2027-01-29", MIXTE),
    (8, "La satisfaction des besoins de l'enfant à l'EM : enjeux, difficultés et approches de solution",
     "Clarification conceptuelle\nBesoins fondamentaux de l'enfant à la maternelle\nNécessité de la prise en compte des "
     "besoins fondamentaux de l'enfant\nDifficultés liées à la satisfaction des besoins de l'enfant\nApproches de solution "
     "pour une prise en charge efficace des besoins fondamentaux de l'enfant", PM, PM, "2027-02-12", LIBRE),
    (9, "La dramatisation du conte à l'EM : démarche de mise en œuvre",
     "Clarification conceptuelle\nImportance de la dramatisation dans le développement du langage et de l'imaginaire de "
     "l'enfant\nÉtapes de la dramatisation d'un conte\nDémarche de mise en œuvre\nImplications pédagogiques",
     PM, PM, "2027-03-05", MIXTE),
    (10, "Le jeu comme levier d'apprentissage à l'école maternelle : apports des sciences cognitives et pratiques pédagogiques",
     "Clarification conceptuelle\nJeu et exploration de l'environnement\nApports des sciences cognitives et apprentissage "
     "par le jeu\nJeu et intentions pédagogiques\nPosture de l'animateur et accompagnement de l'enfant\nImplications "
     "pédagogiques", PM, PM, "2027-03-19", LIBRE),
    (11, "La poésie à l'EM : démarche de mise en œuvre",
     "Clarification conceptuelle\nImportance de la poésie dans le développement du langage de l'enfant\nCritères de choix "
     "d'une poésie adaptée à l'EM\nDémarche de mise en œuvre\nImplications pédagogiques", PM, PM, "2027-04-23", MIXTE),
    (12, "Bilan", "-", PM, PM, "2027-05-07", ""),
]

UP_PRIMAIRE_2026 = [
    (1, "Renouvellement des bureaux", "-", "-", "-", "2026-10-09", ""),
    (2, _CHRONOPHAGES, _AXES_CHRONOPHAGES, PM, PM, "2026-10-23", LIBRE),
    (3, "Construction des figures symétriques par rapport à un point, à une droite et par glissement",
     "Compréhension des notions de symétrie axiale, symétrie centrale et symétrie par glissement\nIdentification et utilité "
     "des instruments géométriques\nConstruction des figures symétriques par les enseignants (exercices pratiques)",
     PM, PM, "2026-11-06", LIBRE),
    (4, _DIFFERENCIEE, _AXES_DIFFERENCIEE, PM, PM, "2026-11-20", LIBRE),
    (5, "L'enseignement-apprentissage-évaluation de la géométrie au CM",
     "Clarification conceptuelle\nExplicitation de la compétence disciplinaire concernée\nDémarche disciplinaire de la "
     "géométrie\nImplications pédagogiques", PM, PM, "2026-12-04", MIXTE),
    (6, "La mise en œuvre de la lecture individuelle au niveau 1 à l'EP : démarche pratique",
     "Clarification conceptuelle\nObjectifs de la lecture individuelle au niveau 1\nDémarche de mise en œuvre\nImplications "
     "pédagogiques", PM, PM, "2027-01-15", MIXTE),
    (7, "Le vocabulaire fonctionnel au CE1 : importance et démarche d'enseignement",
     "Clarification conceptuelle\nImportance du vocabulaire fonctionnel dans les apprentissages\nCritères de sélection du "
     "vocabulaire fonctionnel\nDémarche d'enseignement-apprentissage-évaluation\nImplications pédagogiques",
     PM, PM, "2027-01-29", MIXTE),
    (8, "Le tâtonnement scientifique dans l'enseignement de la mesure au CM : démarche de mise en œuvre",
     "Clarification conceptuelle\nPrincipes du tâtonnement scientifique\nÉtapes de la démarche au CM\nImplications "
     "pédagogiques", PM, PM, "2027-02-12", MIXTE),
    (9, "La dictée préparée : importance et démarche de mise en œuvre",
     "Clarification conceptuelle\nImportance de la dictée préparée dans l'apprentissage de l'orthographe\nÉtapes de "
     "préparation\nDémarche de mise en œuvre\nImplications pédagogiques", PM, PM, "2027-03-05", MIXTE),
    (10, "L'enseignement-apprentissage de l'EPS au niveau 1 : spécificités au CE1",
     "Clarification conceptuelle\nObjectifs et importance\nOrganisation de la classe et de l'espace au CE1\nImplications "
     "pédagogiques", PM, PM, "2027-03-19", MIXTE),
    (11, "La poésie au CM : préparation et mise en œuvre",
     "Clarification conceptuelle\nCritères de choix d'une poésie au CM\nÉtapes de préparation d'une séance de poésie\n"
     "Démarche de mise en œuvre\nImplications pédagogiques", PM, PM, "2027-04-23", MIXTE),
    (12, "Bilan", "-", PM, PM, "2027-05-07", "-"),
]

# CP / FG : (numéro, thème, contenus indicatifs, date de déroulement, observations)
CONFERENCES_2026 = [
    (1, "La place des ressources numériques dans la réussite de l'acte pédagogique",
     "Clarification conceptuelle\nTypologie des ressources numériques mobilisables en classe\nApports et limites des "
     "ressources numériques dans l'acte pédagogique\nImplications pédagogiques", PM, ""),
    (2, "Des déchets aux ressources : apprendre à transformer les déchets en ressources pour protéger l'environnement",
     "Clarification conceptuelle\nTypes de déchets\nGestion des déchets et leur transformation pour l'environnement\n"
     "Impacts des déchets aux ressources dans l'environnement\nImplications pédagogiques", PM, ""),
    (3, "Le leadership du directeur d'école : enjeux et responsabilités pour une gestion réussie",
     "Clarification conceptuelle\nEnjeux du leadership pédagogique et administratif du directeur\nDocuments administratifs "
     "et outils de gestion de l'école\nResponsabilités du directeur pour une gestion réussie", PM, ""),
    (4, "La gestion des erreurs des apprenants dans le processus enseignement-apprentissage-évaluation",
     "Clarification conceptuelle\nTypologie des erreurs des apprenants\nStratégies de gestion et de remédiation des "
     "erreurs\nImplications pédagogiques", PM, ""),
    (5, "L'utilisation pédagogique de l'intelligence artificielle par l'enseignant",
     "Clarification conceptuelle\nPotentialités de l'IA pour la préparation et l'animation des enseignements\nPrécautions "
     "et limites d'usage\nImplications pédagogiques", PM, ""),
]

FORMATIONS_GROUPEES_2026 = [
    (1, "La Pédagogie Explicite en français et en mathématiques au CI – CP : fondements cognitifs et démarche de mise en "
        "œuvre en classe",
     "Apport des sciences cognitives et les quatre piliers de l'apprentissage\nÉtapes du processus d'enseignement – "
     "apprentissage en français au CI – CP\nDémarche disciplinaire des mathématiques au CI – CP\nArticulation des piliers de "
     "l'apprentissage avec les étapes du français et la démarche des mathématiques au CI – CP", PM,
     "Ce thème est à développer obligatoirement au cours du premier trimestre de l'année scolaire 2026-2027"),
    (2, "La pédagogie de l'intégration : approches et mise en œuvre",
     "Clarification conceptuelle\nFondements de la pédagogie de l'intégration\nDémarche de mise en œuvre en classe\n"
     "Implications pédagogiques", PM, ""),
    (3, "La gestion de la remédiation en évaluation formative",
     "Clarification conceptuelle\nÉtapes de l'évaluation formative\nStratégies de remédiation adaptées aux besoins des "
     "apprenants\nImplications pédagogiques", PM, ""),
    (4, "La différenciation pédagogique : focus sur les groupes de besoins",
     "Clarification conceptuelle\nCritères de constitution des groupes de besoins\nDémarche de mise en œuvre de la "
     "différenciation pédagogique\nImplications pédagogiques", PM, ""),
    (5, "L'accord du participe passé employé avec l'auxiliaire avoir et des verbes pronominaux",
     "Rappel des règles de base\nCas particuliers d'accord\nDémarche d'enseignement-apprentissage-évaluation\nExercices "
     "d'application", PM, ""),
]


def _up(t):
    n, theme, axes, prep, interp, admin, obs = t
    return {"numero": n, "theme": theme, "axes": axes, "date_preparation": prep, "date_interpretation": interp,
            "date_administration": admin, "date_deroulement": "", "observations": obs}


def _cpfg(t):
    n, theme, axes, der, obs = t
    return {"numero": n, "theme": theme, "axes": axes, "date_preparation": "", "date_interpretation": "",
            "date_administration": "", "date_deroulement": der, "observations": obs}


THEMES_OFFICIELS_2026_2027 = {
    "up_maternelle": [_up(t) for t in UP_MATERNELLE_2026],
    "up_primaire": [_up(t) for t in UP_PRIMAIRE_2026],
    "conference": [_cpfg(t) for t in CONFERENCES_2026],
    "formation_groupee": [_cpfg(t) for t in FORMATIONS_GROUPEES_2026],
}
# année → (référence, source, {catégorie: [thèmes]})
THEMES_OFFICIELS = {"2026-2027": (REFERENCE_2026, SOURCE_2026, THEMES_OFFICIELS_2026_2027)}


def themes_officiels(annee, categorie=None):
    """Copies des thèmes officiels de l'année (toutes catégories ou une seule) ; [] si l'année est inconnue."""
    if annee not in THEMES_OFFICIELS:
        return []
    d = THEMES_OFFICIELS[annee][2]
    cats = [categorie] if categorie else [c for c, _l in CATEGORIES]
    return [dict(t, categorie=c, officiel=1) for c in cats for t in d.get(c, [])]


# ================================================================ fonctions pures
def annee_valide(a, defaut=None):
    m = RE_ANNEE.match((a or "").strip())
    return a.strip() if m and int(m.group(2)) == int(m.group(1)) + 1 else defaut


def annee_suivante(annee):
    a = int(annee[:4])
    return f"{a + 1}-{a + 2}"


def lire_date(s):
    """Date depuis « aaaa-mm-jj », « jj/mm/aaaa », « Vendredi 23/10/2026 »… ; None si ce n'est pas une date."""
    s = str(s or "").strip()
    if not s:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s) or re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s)
    if not m:
        return None
    try:
        if len(m.group(1)) == 4:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def normaliser_date(s):
    """Texte de date saisi → ISO si c'est une date, sinon le texte nettoyé (« PM », « - »…)."""
    d = lire_date(s)
    return d.isoformat() if d else str(s or "").strip()[:40]


def date_affichee(v):
    """ISO → « Vendredi 23/10/2026 » ; autre texte inchangé."""
    d = lire_date(v) if v and re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)) else None
    return f"{JOURS[d.weekday()]} {d.strftime('%d/%m/%Y')}" if d else (v or "")


def date_courte(v):
    d = lire_date(v) if v and re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)) else None
    return d.strftime("%d/%m/%Y") if d else (v or "")


def decaler_un_an(v):
    """Date ISO → même jour un an plus tard (29 février → 28 février) ; autre texte inchangé."""
    d = lire_date(v) if v and re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)) else None
    if not d:
        return v or ""
    try:
        return d.replace(year=d.year + 1).isoformat()
    except ValueError:
        return d.replace(year=d.year + 1, day=28).isoformat()


def date_reference(t):
    """Date de référence du thème (date d'exécution, sinon date d'administration / de déroulement) ; None sans date."""
    for k in ("date_execution", "date_administration", "date_deroulement"):
        v = t.get(k)
        if v and re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)):
            return lire_date(v)
    return None


def trimestre_de(d):
    """Trimestre scolaire d'une date : I (septembre → décembre), II (janvier → mars), III (avril → août)."""
    if not d:
        return ""
    if d.month >= 9:
        return "I"
    return "II" if d.month <= 3 else "III"


def taux(n, total):
    return round(100 * n / total) if total else None


def suivi(lst, aujourdhui=None):
    """Statistiques de suivi : par catégorie (total, exécutés, à venir, en retard, taux) et par trimestre."""
    auj = aujourdhui or date.today()
    out = {}
    for c, lib in CATEGORIES:
        ts = [t for t in lst if t["categorie"] == c]
        exe = [t for t in ts if t.get("execute")]
        a_venir = [t for t in ts if not t.get("execute") and date_reference(t) and date_reference(t) >= auj]
        retard = [t for t in ts if not t.get("execute") and date_reference(t) and date_reference(t) < auj]
        sans_date = [t for t in ts if not t.get("execute") and not date_reference(t)]
        trims = []
        for code, tl in TRIMESTRES:
            tt = [t for t in ts if trimestre_de(date_reference(t)) == code]
            te = [t for t in tt if t.get("execute")]
            trims.append({"code": code, "libelle": tl, "programmes": len(tt), "executes": len(te), "taux": taux(len(te), len(tt)),
                          "themes": tt})
        out[c] = {"libelle": lib, "total": len(ts), "executes": len(exe), "a_venir": len(a_venir), "retard": len(retard),
                  "sans_date": len(sans_date), "taux": taux(len(exe), len(ts)), "trimestres": trims,
                  "prochain": min(a_venir, key=date_reference) if a_venir else None,
                  "liste_retard": sorted(retard, key=date_reference), "liste_a_venir": sorted(a_venir, key=date_reference)}
    return out


def lire_theme(form):
    """Contrôle d'un thème (formulaire ou import). Retourne (valeurs, erreurs)."""
    cat = form.get("categorie") if form.get("categorie") in CATEGORIES_LIB else "up_primaire"
    v = {"categorie": cat, "theme": (form.get("theme") or "").strip()[:400],
         "axes": "\n".join(l.strip().lstrip("-–• ").strip() for l in (form.get("axes") or "").splitlines() if l.strip())[:3000],
         "date_preparation": normaliser_date(form.get("date_preparation")),
         "date_interpretation": normaliser_date(form.get("date_interpretation")),
         "date_administration": normaliser_date(form.get("date_administration")),
         "date_deroulement": normaliser_date(form.get("date_deroulement")),
         "observations": (form.get("observations") or "").strip()[:1000],
         "execute": 1 if str(form.get("execute") or "").strip().lower() in ("1", "oui", "x", "o", "on", "true") else 0,
         "lieu": (form.get("lieu") or "").strip()[:200], "compte_rendu": (form.get("compte_rendu") or "").strip()[:4000]}
    brut = str(form.get("numero") or "").strip()
    v["numero"] = int(brut) if brut.isdigit() else 0
    err = []
    if not v["theme"]:
        err.append("L'intitulé du thème est obligatoire.")
    de = str(form.get("date_execution") or "").strip()
    v["date_execution"] = ""
    if de:
        d = lire_date(de)
        if not d:
            err.append("Date d'exécution invalide (jj/mm/aaaa).")
        else:
            v["date_execution"] = d.isoformat()
    p = str(form.get("participants") or "").strip()
    if p and not p.isdigit():
        err.append("Participants : nombre entier attendu.")
    v["participants"] = int(p) if p.isdigit() else None
    if cat in CATEGORIES_UP:
        v["date_deroulement"] = ""
    else:
        v["date_preparation"] = v["date_interpretation"] = v["date_administration"] = ""
    return v, err


def categorie_depuis_texte(s):
    """« UP maternelle », « conférence », « FG »… → code de catégorie (None si inconnu)."""
    t = (s or "").strip().lower()
    t = t.replace("é", "e").replace("è", "e").replace("ê", "e")
    if not t:
        return None
    if t in CATEGORIES_LIB:
        return t
    if "matern" in t:
        return "up_maternelle"
    if "primaire" in t or t in ("up", "ep"):
        return "up_primaire"
    if "conf" in t or t == "cp":
        return "conference"
    if "formation" in t or "group" in t or t == "fg":
        return "formation_groupee"
    return None


_H = None


def _H_themes(annee, categorie=None, ecole_id=None):
    """Accès direct à H.themes_up (tests et scripts)."""
    return _H.themes_up(annee, categorie, ecole_id)


# ================================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)
    global _H
    _H = H

    def uid():
        return g.user["id"] if g.get("user") else None

    def peut_modifier():
        return H.peut("themes_up")

    def retour_choisi():
        r = request.values.get("retour") or ""
        return r if r in ("synoptique", "jur_synoptique") else ""

    def ecole_cible():
        """École dont on affiche les thèmes ; 0 = planning commun de la structure (CS / DDEMP sans école ouverte,
        onglet du synoptique de la structure, ou ?portee=structure)."""
        if config.juridiction():
            if retour_choisi() == "jur_synoptique" or request.values.get("portee") == "structure" or not g.get("ecole"):
                return 0
        return H.eco()

    def annee_choisie():
        return annee_valide(request.values.get("annee"), config.ANNEE_ACTIVE)

    def cat_choisie():
        c = request.values.get("cat") or ""
        return c if c in dict(ONGLETS) else "up_maternelle"

    def params_retour(**extra):
        p = {"annee": annee_choisie()}
        if retour_choisi():
            p["retour"] = retour_choisi()
        if request.values.get("portee") == "structure":
            p["portee"] = "structure"
        if request.values.get("cat"):
            p["cat"] = cat_choisie()
        p.update(extra)
        return p

    def url_liste(**extra):
        return url_for("themes_up", **params_retour(**extra))

    # ------------------------------------------------------------ données
    CHAMPS = ("categorie", "numero", "theme", "axes", "date_preparation", "date_interpretation", "date_administration",
              "date_deroulement", "observations", "execute", "date_execution", "lieu", "participants", "compte_rendu")

    def lignes(annee, ecole_id, categorie=None):
        sql = "SELECT * FROM themes_up WHERE ecole_id=? AND annee=?"
        args = [ecole_id, annee]
        if categorie:
            sql += " AND categorie=?"
            args.append(categorie)
        return [dict(r) for r in q(sql + " ORDER BY categorie, numero, id", args)]

    def inserer(ecole_id, annee, t, officiel=None):
        return ex("INSERT INTO themes_up (ecole_id, annee, " + ", ".join(CHAMPS) + ", officiel, maj, maj_par) VALUES (?,?," +
                  ",".join("?" * len(CHAMPS)) + ",?,?,?)",
                  (ecole_id, annee) + tuple(valeur_colonne(t, k) for k in CHAMPS) +
                  (int(t.get("officiel") or 0) if officiel is None else officiel, H.maintenant(), uid()))

    def valeur_colonne(t, k):
        if k == "participants":
            return t.get(k) if t.get(k) not in ("", None) else None
        if k in ("numero", "execute"):
            return int(t.get(k) or 0)
        return "" if t.get(k) is None else t.get(k)

    def ecrire_meta(ecole_id, annee, reference, source):
        ex("INSERT INTO themes_up_meta (ecole_id, annee, reference, source, maj) VALUES (?,?,?,?,?) "
           "ON CONFLICT(ecole_id, annee) DO UPDATE SET reference=excluded.reference, source=excluded.source, maj=excluded.maj",
           (ecole_id, annee, reference, source, H.maintenant()))

    def meta(ecole_id, annee):
        r = q("SELECT * FROM themes_up_meta WHERE ecole_id=? AND annee=?", (ecole_id, annee), un=True)
        return dict(r) if r else {"reference": "", "source": ""}

    def remettre_officiel(ecole_id, annee):
        """Insère les thèmes officiels de l'année (si connue) ; retourne le nombre inséré."""
        offi = themes_officiels(annee)
        for t in offi:
            inserer(ecole_id, annee, t, officiel=1)
        if offi:
            ref = THEMES_OFFICIELS[annee]
            ecrire_meta(ecole_id, annee, ref[0], ref[1])
        return len(offi)

    def lignes_preremplies(annee, ecole_id):
        """Thèmes de l'année ; les thèmes officiels sont insérés à la première ouverture d'une année connue."""
        lst = lignes(annee, ecole_id)
        if not lst and annee in THEMES_OFFICIELS and g.get("user"):
            remettre_officiel(ecole_id, annee)
            lst = lignes(annee, ecole_id)
        return lst

    def annees_disponibles(ecole_id):
        pres = {r["annee"] for r in q("SELECT DISTINCT annee FROM themes_up WHERE ecole_id=?", (ecole_id,))}
        pres |= {config.ANNEE_ACTIVE, annee_suivante(config.ANNEE_ACTIVE)} | set(THEMES_OFFICIELS)
        return sorted(pres)

    def theme_ou_404(tid, annee, ecole_id):
        r = q("SELECT * FROM themes_up WHERE id=? AND ecole_id=? AND annee=?", (tid, ecole_id, annee), un=True)
        if not r:
            abort(404)
        return dict(r)

    # ---- exposé aux autres modules
    def themes_up_api(annee, categorie=None, ecole_id=None):
        """Thèmes de l'année pour l'école (ou la structure) ; à défaut, planning de la structure puis liste officielle."""
        annee = annee_valide(annee, config.ANNEE_ACTIVE)
        if ecole_id is None:
            try:
                ecole_id = ecole_cible()
            except RuntimeError:        # hors requête
                ecole_id = 0
        lst = lignes(annee, ecole_id, categorie)
        if not lst and ecole_id != 0:
            lst = lignes(annee, 0, categorie)
        if not lst:
            lst = themes_officiels(annee, categorie)
        return lst

    H.themes_up = themes_up_api

    # ------------------------------------------------------------ contexte des gabarits
    def identite_synoptique(ecole_id):
        f = getattr(H, "synoptique_identite", None)
        d = {x["cle"]: x["valeur"] for x in f(ecole_id)} if f else {}
        e = q("SELECT * FROM ecoles WHERE id=?", (ecole_id,), un=True)
        d.setdefault("epp", (e["nom"] if e else "") or "")
        d["cs"] = (e["cs"] if e else "") or ""
        d.setdefault("ddemp", (e["departement"] if e else "") or "")
        return d

    def nom_cible(ecole_id):
        if ecole_id == 0:
            s = H.jur_structure() if getattr(H, "jur_structure", None) and config.juridiction() else None
            return (s or {}).get("nom") or ("DDEMP" if config.EDITION == "ddemp" else "Circonscription scolaire")
        e = q("SELECT nom FROM ecoles WHERE id=?", (ecole_id,), un=True)
        return (e["nom"] if e else "") or config.ECOLE.get("nom", "")

    def ctx(annee, ecole_id, **extra):
        retour = retour_choisi()
        d = dict(annee=annee, ecole_id=ecole_id, retour=retour, portee=request.values.get("portee") or "",
                 modifiable=peut_modifier(), CATEGORIES=CATEGORIES, CATEGORIES_LIB=CATEGORIES_LIB, ONGLETS=ONGLETS,
                 CATEGORIES_UP=CATEGORIES_UP, TRIMESTRES=TRIMESTRES, date_affichee=date_affichee, date_courte=date_courte,
                 nom_cible=nom_cible(ecole_id), structure=(ecole_id == 0), ecole_ouverte=bool(g.get("ecole")),
                 juridiction=config.juridiction(), annees=annees_disponibles(ecole_id), annee_suiv=annee_suivante(annee),
                 officiel_connu=annee in THEMES_OFFICIELS, meta=meta(ecole_id, annee), params=params_retour(),
                 cat=cat_choisie(), aujourdhui=date.today().isoformat(), NB_ARRETE=NB_ARRETE)
        if retour == "synoptique":
            d.update(onglet="themes", ident=identite_synoptique(ecole_id), ecrire=H.peut("synoptique"))
        elif retour == "jur_synoptique" and getattr(H, "jur_synoptique_identite", None):
            d.update(onglet="themes", ident=H.jur_synoptique_identite(), ecrire=H.peut("jur_synoptique"),
                     ddemp=config.EDITION == "ddemp")
        else:
            d["retour"] = ""
        d.update(extra)
        return d

    # adresses : préfixe « /juridiction » d'abord dans les applications CS / DDEMP (adresse de la structure, accessible
    # sans école ouverte : a_integration n'exige une école que hors de ce préfixe) ; les deux adresses existent partout
    def routes(suffixe, **k):
        chemins = ["/themes-up" + suffixe, "/juridiction/themes-up" + suffixe]
        if config.juridiction():
            chemins.reverse()

        def deco(f):
            for c in chemins:
                f = app.route(c, **k)(f)
            return f
        return deco

    # ============================================================ pages
    @routes("")
    @H.connexion_requise()
    def themes_up():
        annee, eid = annee_choisie(), ecole_cible()
        lst = lignes_preremplies(annee, eid)
        cat = cat_choisie()
        return render_template("themes_up.html", **ctx(annee, eid, lst=[t for t in lst if t["categorie"] == cat], tous=lst,
                                                       stats=suivi(lst), nb={c: sum(1 for t in lst if t["categorie"] == c) for c, _l in CATEGORIES}))

    @routes("/theme/<int:tid>", methods=["GET", "POST"])
    @H.connexion_requise("themes_up")
    def themes_up_form(tid):
        annee, eid = annee_choisie(), ecole_cible()
        t = theme_ou_404(tid, annee, eid) if tid else None
        if request.method == "POST":
            v, err = lire_theme(request.form)
            if err:
                for e in err:
                    flash(e, "danger")
                return render_template("themes_up_form.html", **ctx(annee, eid, t=t, v=v, cat=v["categorie"])), 400
            if t:
                ex("UPDATE themes_up SET " + ", ".join(f"{k}=?" for k in CHAMPS) + ", maj=?, maj_par=? WHERE id=?",
                   tuple(v[k] for k in CHAMPS) + (H.maintenant(), uid(), t["id"]))
                H.journal("themes_up", f"{annee} : thème modifié « {v['theme'][:80]} » ({CATEGORIES_LIB[v['categorie']]})")
                flash("Thème modifié.", "success")
            else:
                if not v["numero"]:
                    v["numero"] = (q("SELECT COALESCE(MAX(numero),0) m FROM themes_up WHERE ecole_id=? AND annee=? AND categorie=?",
                                     (eid, annee, v["categorie"]), un=True)["m"] or 0) + 1
                inserer(eid, annee, v, officiel=0)
                H.journal("themes_up", f"{annee} : thème ajouté « {v['theme'][:80]} » ({CATEGORIES_LIB[v['categorie']]})")
                flash("Thème ajouté.", "success")
            return redirect(url_liste(cat=v["categorie"]))
        if t:
            v = dict(t)
        else:
            cat = cat_choisie() if cat_choisie() in CATEGORIES_LIB else "up_primaire"
            v = {"categorie": cat, "numero": "", "theme": "", "axes": "", "date_preparation": PM if cat in CATEGORIES_UP else "",
                 "date_interpretation": PM if cat in CATEGORIES_UP else "", "date_administration": "", "date_deroulement": PM,
                 "observations": "", "execute": 0, "date_execution": "", "lieu": "", "participants": None, "compte_rendu": ""}
        return render_template("themes_up_form.html", **ctx(annee, eid, t=t, v=v, cat=v["categorie"]))

    @routes("/theme/<int:tid>/supprimer", methods=["POST"])
    @H.connexion_requise("themes_up")
    def themes_up_supprimer(tid):
        annee, eid = annee_choisie(), ecole_cible()
        t = theme_ou_404(tid, annee, eid)
        ex("DELETE FROM themes_up WHERE id=?", (t["id"],))
        H.journal("themes_up", f"{annee} : thème supprimé « {t['theme'][:80]} »")
        flash("Thème supprimé.", "warning")
        return redirect(url_liste(cat=t["categorie"]))

    @routes("/theme/<int:tid>/executer", methods=["POST"])
    @H.connexion_requise("themes_up")
    def themes_up_executer(tid):
        """Bascule rapide « exécuté » (date d'exécution = date du thème ou du jour)."""
        annee, eid = annee_choisie(), ecole_cible()
        t = theme_ou_404(tid, annee, eid)
        if t.get("execute"):
            ex("UPDATE themes_up SET execute=0, maj=?, maj_par=? WHERE id=?", (H.maintenant(), uid(), t["id"]))
            H.journal("themes_up", f"{annee} : « {t['theme'][:80]} » remis à « à exécuter »")
            flash("Thème remis « à exécuter ».", "warning")
        else:
            d = date_reference(t)
            de = t.get("date_execution") or (d.isoformat() if d and d <= date.today() else date.today().isoformat())
            ex("UPDATE themes_up SET execute=1, date_execution=?, maj=?, maj_par=? WHERE id=?", (de, H.maintenant(), uid(), t["id"]))
            H.journal("themes_up", f"{annee} : « {t['theme'][:80]} » exécuté le {de}")
            flash(f"Thème marqué exécuté le {date_courte(de)}.", "success")
        return redirect(url_liste(cat=t["categorie"]))

    @routes("/recharger", methods=["POST"])
    @H.connexion_requise("themes_up")
    def themes_up_recharger():
        """Remet les thèmes officiels de l'année (les thèmes ajoutés par l'utilisateur sont conservés)."""
        annee, eid = annee_choisie(), ecole_cible()
        if annee not in THEMES_OFFICIELS:
            flash(f"Les thèmes officiels {annee} ne sont pas connus de GESCOL : saisissez-les ou importez-les.", "danger")
            return redirect(url_liste())
        ex("DELETE FROM themes_up WHERE ecole_id=? AND annee=? AND officiel=1", (eid, annee))
        n = remettre_officiel(eid, annee)
        H.journal("themes_up", f"{annee} : thèmes officiels rechargés ({n})")
        flash(f"Thèmes officiels {annee} rechargés ({n} thèmes ; vos ajouts sont conservés).", "success")
        return redirect(url_liste())

    @routes("/reinitialiser", methods=["POST"])
    @H.connexion_requise("themes_up")
    def themes_up_reinitialiser():
        """Supprime tous les thèmes de l'année puis remet les thèmes officiels (s'ils sont connus)."""
        annee, eid = annee_choisie(), ecole_cible()
        ex("DELETE FROM themes_up WHERE ecole_id=? AND annee=?", (eid, annee))
        n = remettre_officiel(eid, annee)
        if not n:
            ex("DELETE FROM themes_up_meta WHERE ecole_id=? AND annee=?", (eid, annee))
        H.journal("themes_up", f"{annee} : thèmes réinitialisés ({n} officiels)")
        flash(f"Thèmes {annee} réinitialisés" + (f" : {n} thèmes officiels remis." if n else " (année sans thèmes officiels connus : vide)."),
              "success")
        return redirect(url_liste())

    @routes("/preparer", methods=["POST"])
    @H.connexion_requise("themes_up")
    def themes_up_preparer():
        """Prépare l'année suivante : copie des thèmes de l'année affichée, dates décalées d'un an, suivi remis à zéro."""
        annee, eid = annee_choisie(), ecole_cible()
        suiv = annee_suivante(annee)
        if lignes(suiv, eid):
            flash(f"L'année {suiv} contient déjà des thèmes : réinitialisez-la d'abord si vous voulez la refaire.", "danger")
            return redirect(url_liste(annee=suiv))
        src = lignes(annee, eid)
        for t in src:
            c = dict(t, execute=0, date_execution="", lieu="", participants=None, compte_rendu="",
                     date_preparation=decaler_un_an(t["date_preparation"]), date_interpretation=decaler_un_an(t["date_interpretation"]),
                     date_administration=decaler_un_an(t["date_administration"]), date_deroulement=decaler_un_an(t["date_deroulement"]),
                     observations=re.sub(r"\b(20\d\d)-(20\d\d)\b", lambda m: f"{int(m.group(1)) + 1}-{int(m.group(2)) + 1}", t["observations"] or ""))
            inserer(eid, suiv, c, officiel=0)
        ecrire_meta(eid, suiv, f"À compléter : thèmes {suiv} préparés à partir de {annee} (dates décalées d'un an)", "")
        H.journal("themes_up", f"{suiv} préparé à partir de {annee} ({len(src)} thèmes)")
        flash(f"Année {suiv} préparée à partir de {annee} ({len(src)} thèmes, dates décalées d'un an) : corrigez les thèmes "
              "et les dates dès la parution du planning officiel.", "success")
        return redirect(url_liste(annee=suiv))

    @routes("/meta", methods=["POST"])
    @H.connexion_requise("themes_up")
    def themes_up_meta():
        annee, eid = annee_choisie(), ecole_cible()
        ecrire_meta(eid, annee, (request.form.get("reference") or "").strip()[:500], (request.form.get("source") or "").strip()[:200])
        H.journal("themes_up", f"{annee} : référence du texte modifiée")
        flash("Référence enregistrée.", "success")
        return redirect(url_liste())

    # ============================================================ Excel
    def ligne_xlsx(t):
        return [CATEGORIES_LIB.get(t["categorie"], t["categorie"]), t["numero"], t["theme"], t.get("axes") or "",
                date_courte(t.get("date_preparation")), date_courte(t.get("date_interpretation")),
                date_courte(t.get("date_administration") if t["categorie"] in CATEGORIES_UP else t.get("date_deroulement")),
                t.get("observations") or "", "Oui" if t.get("officiel") else "Non", "Oui" if t.get("execute") else "Non",
                date_courte(t.get("date_execution")), t.get("lieu") or "", t.get("participants") if t.get("participants") is not None else "",
                t.get("compte_rendu") or ""]

    def feuilles_export(annee, eid, lst):
        th = [f"Thèmes d'UP, de conférence pédagogique et de formation groupée {annee} — {nom_cible(eid)}",
              meta(eid, annee).get("reference") or ""]
        f = []
        for c, lib in CATEGORIES:
            f.append((lib, ENTETES_XLSX, [ligne_xlsx(t) for t in lst if t["categorie"] == c], {"titre_haut": th}))
        return f

    @routes("/export.xlsx")
    @H.connexion_requise()
    def themes_up_xlsx():
        import outils_xlsx as X
        annee, eid = annee_choisie(), ecole_cible()
        lst = lignes_preremplies(annee, eid)
        try:
            return X.reponse_classeur(f"themes_up_{annee}.xlsx", feuilles_export(annee, eid, lst))
        except X.ExcelIndisponible:
            flash("Export Excel indisponible (module openpyxl absent).", "danger")
            return redirect(url_liste())

    @routes("/modele.xlsx")
    @H.connexion_requise()
    def themes_up_modele_xlsx():
        import outils_xlsx as X
        annee = annee_choisie()
        offi = themes_officiels("2026-2027")
        exemples = [t for t in offi if t["categorie"] == "up_primaire"][:3] + [t for t in offi if t["categorie"] == "conference"][:1] + \
                   [t for t in offi if t["categorie"] == "formation_groupee"][:1]
        try:
            return X.reponse_xlsx("modele_themes_up.xlsx", ENTETES_XLSX, [ligne_xlsx(t) for t in exemples], titre="Thèmes",
                                  titre_haut=[f"Modèle d'import des thèmes d'UP, CP et FG ({annee})",
                                              "Catégories : " + ", ".join(l for _c, l in CATEGORIES) +
                                              " — dates au format jj/mm/aaaa (ou « PM » pour mémoire) — un axe par ligne dans la cellule"])
        except X.ExcelIndisponible:
            flash("Modèle Excel indisponible (module openpyxl absent).", "danger")
            return redirect(url_liste())

    def lire_classeur(fichier):
        """Classeur → [(nom de feuille, entêtes, lignes)] pour toutes les feuilles contenant une colonne « Thème »."""
        import outils_xlsx as X
        openpyxl = X._openpyxl()
        try:
            wb = openpyxl.load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        except Exception as e_:  # noqa: BLE001
            raise ValueError("Fichier Excel illisible : enregistrez-le au format .xlsx.") from e_
        out = []
        for ws in wb.worksheets:
            brutes = [list(r) for r in ws.iter_rows(values_only=True)][:5000]
            idx = next((i for i, r in enumerate(brutes[:40]) if any(X.normaliser(v).startswith("theme") for v in r if v)), None)
            if idx is None:
                continue
            entetes = [str(v).strip() if v is not None else "" for v in brutes[idx]]
            lignes_ = [r for r in brutes[idx + 1:] if any(v not in (None, "") for v in r)]
            out.append((ws.title, entetes, lignes_))
        return out

    @routes("/import", methods=["GET", "POST"])
    @H.connexion_requise("themes_up")
    def themes_up_import():
        import outils_xlsx as X
        annee, eid = annee_choisie(), ecole_cible()
        if request.method == "POST":
            f = request.files.get("fichier")
            if not f or not f.filename:
                flash("Choisissez un fichier Excel.", "danger")
                return redirect(url_for("themes_up_import", **params_retour()))
            try:
                feuilles = lire_classeur(f)
            except (ValueError, X.ExcelIndisponible) as e:
                flash(str(e), "danger")
                return redirect(url_for("themes_up_import", **params_retour()))
            if not feuilles:
                flash("Aucune feuille exploitable : la ligne d'en-tête doit contenir une colonne « Thème ».", "danger")
                return redirect(url_for("themes_up_import", **params_retour()))
            nouvelles, erreurs = [], []
            for nom_f, entetes, brutes in feuilles:
                c = {k: X.colonne(entetes, *cands) for k, cands in {
                    "categorie": ("categorie", "catégorie"), "numero": ("n°", "numero", "numéro", "n"), "theme": ("theme", "thème"),
                    "axes": ("axes", "contenus", "axes de reflexion"), "prep": ("preparation", "préparation"),
                    "interp": ("interpretation", "interprétation"), "admin": ("administration", "date de deroulement", "deroulement", "date"),
                    "observations": ("observations", "observation", "obs"), "officiel": ("officiel",), "execute": ("execute", "exécuté"),
                    "date_execution": ("date d'execution", "date d'exécution", "execution"), "lieu": ("lieu",),
                    "participants": ("participants",), "compte_rendu": ("compte rendu", "compte-rendu")}.items()}
                cat_feuille = categorie_depuis_texte(nom_f)
                for i, r in enumerate(brutes, 1):
                    cat = categorie_depuis_texte(X.valeur(r, c["categorie"])) or cat_feuille
                    if not cat:
                        erreurs.append(f"{nom_f}, ligne {i} : catégorie inconnue (UP maternelle, UP primaire, Conférences pédagogiques, Formations groupées).")
                        continue
                    dl = X.valeur(r, c["admin"])
                    v, err = lire_theme({
                        "categorie": cat, "numero": X.valeur(r, c["numero"]), "theme": X.valeur(r, c["theme"]), "axes": X.valeur(r, c["axes"]),
                        "date_preparation": X.valeur(r, c["prep"]), "date_interpretation": X.valeur(r, c["interp"]),
                        "date_administration": dl, "date_deroulement": dl, "observations": X.valeur(r, c["observations"]),
                        "execute": X.valeur(r, c["execute"]), "date_execution": X.valeur(r, c["date_execution"]), "lieu": X.valeur(r, c["lieu"]),
                        "participants": X.valeur(r, c["participants"]), "compte_rendu": X.valeur(r, c["compte_rendu"])})
                    if err:
                        erreurs.append(f"{nom_f}, ligne {i} ({v['theme'][:40] or '?'}) : {' '.join(err)}")
                        continue
                    v["officiel"] = 1 if X.valeur(r, c["officiel"]).strip().lower() in ("oui", "1", "x", "o") else 0
                    nouvelles.append(v)
            if erreurs:
                for e in erreurs[:10]:
                    flash(e, "danger")
                flash("Import annulé : corrigez le fichier.", "danger")
                return redirect(url_for("themes_up_import", **params_retour()))
            if not nouvelles:
                flash("Aucun thème à importer.", "danger")
                return redirect(url_for("themes_up_import", **params_retour()))
            cats = sorted({v["categorie"] for v in nouvelles})
            for cat in cats:
                ex("DELETE FROM themes_up WHERE ecole_id=? AND annee=? AND categorie=?", (eid, annee, cat))
            for v in nouvelles:
                inserer(eid, annee, v)
            ref = (request.form.get("reference") or "").strip()[:500]
            if ref:
                ecrire_meta(eid, annee, ref, (request.form.get("source") or "").strip()[:200])
            H.journal("themes_up", f"{annee} : import Excel ({len(nouvelles)} thèmes ; {', '.join(CATEGORIES_LIB[c] for c in cats)})")
            flash(f"{len(nouvelles)} thème(s) importé(s) pour {annee} ({', '.join(CATEGORIES_LIB[c] for c in cats)} : les thèmes "
                  "précédents de ces catégories ont été remplacés).", "success")
            return redirect(url_liste(cat=cats[0]))
        return render_template("themes_up_import.html", **ctx(annee, eid, entetes=ENTETES_XLSX))

    # ============================================================ PDF
    P = H.pdfs

    def infos_haut(eid):
        if eid == 0 and config.juridiction():
            s = H.jur_structure() or {}
            return [("DDEMP", s.get("departement") or "—")] + ([] if config.EDITION == "ddemp" else [("CS", s.get("cs") or "—")])
        d = identite_synoptique(eid)
        return [("DDEMP", d.get("ddemp") or "—"), ("CS", d.get("cs") or d.get("ccs") or "—"), ("ÉCOLE", d.get("epp") or "—")]

    def tableau_pdf(entetes, corps, largeurs, taille=7):
        """Table ReportLab (en-tête sur 1 ou 2 lignes, répété) sur la largeur utile de la page paysage."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Table, TableStyle
        utile = landscape(A4)[0] - 24 * mm
        st_c = ParagraphStyle("c", fontName="Helvetica", fontSize=taille, leading=taille + 1.6)
        st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=taille, leading=taille + 1.6, alignment=1, textColor=colors.white)

        def cell(v, st=st_c):
            return Paragraph("" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>"), st)

        rows = entetes if isinstance(entetes[0], (list, tuple)) else [entetes]
        nh = len(rows)
        data = [[cell(h, st_h) if h not in (None, "^") else "" for h in row] for row in rows] + [[cell(v) for v in l] for l in corps]
        s = sum(largeurs)
        t = Table(data, colWidths=[utile * x / s for x in largeurs], repeatRows=nh)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#667085")), ("BACKGROUND", (0, 0), (-1, nh - 1), P.BLEU),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                 ("ROWBACKGROUNDS", (0, nh), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")])]
        for r, row in enumerate(rows):
            debut = None
            for j, h in enumerate(list(row) + ["__fin__"]):
                if h is None and debut is not None:
                    continue
                if debut is not None and j - 1 > debut:
                    style.append(("SPAN", (debut, r), (j - 1, r)))
                debut = j
            for j, h in enumerate(row):
                if h == "^":
                    style.append(("SPAN", (j, r - 1), (j, r)))
        t.setStyle(TableStyle(style))
        return t

    ENT_UP = [["N°", "THÈMES", "AXES DE RÉFLEXION INDICATIFS", "DATES DE DÉROULEMENT", None, None, "OBS"],
              ["^", "^", "^", "PRÉPARATION", "INTERPRÉTATION", "ADMINISTRATION", "^"]]
    LARG_UP = [3, 20, 36, 10, 10, 14, 9]
    ENT_CPFG = ["N°", "DATES DE DÉROULEMENT", "THÈMES", "CONTENUS INDICATIFS", "OBSERVATIONS"]
    LARG_CPFG = [3, 12, 30, 40, 15]

    def axes_pdf(t):
        return "\n".join(f"- {a}" for a in (t.get("axes") or "").splitlines() if a.strip() and a.strip() != "-") or (t.get("axes") or "")

    def corps_up(ts):
        return [[t["numero"] or "", t["theme"], axes_pdf(t), date_affichee(t.get("date_preparation")), date_affichee(t.get("date_interpretation")),
                 date_affichee(t.get("date_administration")), (t.get("observations") or "") + ("\n[exécuté]" if t.get("execute") else "")]
                for t in ts] or [["", "Aucun thème", "", "", "", "", ""]]

    def corps_cpfg(ts):
        return [[t["numero"] or "", date_affichee(t.get("date_deroulement")), t["theme"], axes_pdf(t),
                 (t.get("observations") or "") + ("\n[exécuté]" if t.get("execute") else "")] for t in ts] or [["", "", "Aucun thème", "", ""]]

    def section_titre(txt):
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph, Spacer
        return [Spacer(1, 6), Paragraph(txt, ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=10, leading=13, alignment=1,
                                                             textColor=P.BLEU, spaceAfter=4))]

    @routes("/themes.pdf")
    @H.connexion_requise()
    def themes_up_pdf():
        """PDF paysage : partie=up (UP maternelle + primaire, défaut), cp_fg (conférences + formations) ou complet."""
        from reportlab.platypus import PageBreak
        annee, eid = annee_choisie(), ecole_cible()
        lst = lignes_preremplies(annee, eid)
        partie = request.args.get("partie") or "up"
        par = {c: [t for t in lst if t["categorie"] == c] for c, _l in CATEGORIES}
        m = meta(eid, annee)
        sous = f"Direction de l'Inspection et de l'Innovation Pédagogiques — {nom_cible(eid)} — édité le {date.today().strftime('%d/%m/%Y')}"
        titre_up = f"PLANNING D'EXÉCUTION DES THÈMES D'UNITÉ PÉDAGOGIQUE AU TITRE DE L'ANNÉE SCOLAIRE {annee}"
        titre_cp = f"PLANNING D'EXÉCUTION DES THÈMES DE CONFÉRENCE PÉDAGOGIQUE ET DE FORMATION GROUPÉE AU TITRE DE L'ANNÉE SCOLAIRE {annee}"
        notes = [f"Référence : {m['reference']}" if m.get("reference") else "Référence du texte : à compléter.",
                 "PM = pour mémoire (date à fixer par l'UP / la circonscription). [exécuté] = thème déjà déroulé."]
        bloc_fg = section_titre("FORMATIONS GROUPÉES") + [tableau_pdf(ENT_CPFG, corps_cpfg(par["formation_groupee"]), LARG_CPFG),
                                                          P.paragraphe(NB_ARRETE, 7.5, gras=True, espace=6)]
        if partie == "cp_fg":
            pdf = P.document_tableau(titre_cp, ENT_CPFG, corps_cpfg(par["conference"]), sous_titre=sous, largeurs=LARG_CPFG, paysage=True,
                                     taille=7, avant=section_titre("CONFÉRENCES PÉDAGOGIQUES"), apres=bloc_fg,
                                     notes_bas=notes, infos_haut=infos_haut(eid))
            nom = f"themes_cp_fg_{annee}.pdf"
        else:
            apres = section_titre("PRIMAIRE") + [tableau_pdf(ENT_UP, corps_up(par["up_primaire"]), LARG_UP)]
            if partie == "complet":
                apres += [PageBreak()] + section_titre(titre_cp) + section_titre("CONFÉRENCES PÉDAGOGIQUES") + \
                    [tableau_pdf(ENT_CPFG, corps_cpfg(par["conference"]), LARG_CPFG)] + bloc_fg
            pdf = P.document_tableau(titre_up, ENT_UP, corps_up(par["up_maternelle"]), sous_titre=sous, largeurs=LARG_UP, paysage=True,
                                     taille=7, avant=section_titre("MATERNELLE"), apres=apres, notes_bas=notes, infos_haut=infos_haut(eid))
            nom = f"themes_up_{annee}.pdf" if partie != "complet" else f"themes_up_cp_fg_{annee}.pdf"
        H.journal("themes_up", f"{annee} : PDF ({partie})")
        return H.pdf_reponse(pdf, nom)
