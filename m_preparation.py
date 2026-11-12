# -*- coding: utf-8 -*-
"""v1.18 — Préparation de classe de l'enseignant : programmes et progressions, guides pédagogiques, fiches de
préparation (bibliothèque APC et fiches personnelles), fiches et guides manquants.

Corpus : static/pedafiche_corpus.json.gz, construit par outils/pedafiche (construire_corpus.py + concues.py) à partir
des deux applications PédaFiche Pro fournies par l'utilisateur (1 012 fiches APC CI → CM2 et maternelle, programmes
de Français CE1 / CM1, Mathématiques CE2, EST CI → CM2, Éducation sociale CM1, démarches et guides) ; les fiches et
guides ajoutés pour combler les manques portent la mention « Conçue selon l'APC — à valider par le conseiller
pédagogique » et ne sont jamais présentés comme officiels.

* ``/preparation`` : « Cette semaine » pour chacune de SES classes : ce que prévoient la planification mensuelle de la
  classe (semaine en cours) ou, à défaut, la planification annuelle du cours (mois en cours) — m_synoptique — et les
  fiches de la bibliothèque correspondantes (SA / unité / dossier cités), téléchargeables d'un coup (« fiches de la
  semaine », un PDF).
* ``/preparation/programmes`` : programmes et progressions par cours et matière (unités, dossiers, SA, semaines).
* ``/preparation/guides`` : guides méthodologiques et démarches par matière, lisibles et en PDF.
* ``/preparation/fiches`` : bibliothèque filtrable (cours, matière, sous-matière, SA, séance, texte, « de la semaine »),
  fiche affichée, PDF A4 au format APC (en-tête officiel, école, classe, date, effectif, CD, CT, contenus, stratégies,
  matériel, déroulement phases × activités × résultats, évaluation, signatures et QR de vérification), Word (.doc).
* ``/preparation/preparer`` : préparer une fiche (vierge, d'après un modèle ou en adaptant une fiche de la
  bibliothèque), pour une de SES classes ; ``/preparation/mes-fiches`` : ses fiches (modifier, dupliquer, supprimer,
  PDF, Word). Le directeur consulte les fiches de son école.
* ``/preparation/manquants`` : matrice cours × matière (fiches, guides, SA prévues par la planification sans fiche),
  avant et après les fiches conçues ; v1.19 : état de l'inventaire CM1 (séances de référence, présentes, conçues), lot 2
  (fiches transmises par la CS importées, recueils de référence, guide officiel CP) et doublons fusionnés.
* v1.19 — ``/preparation/resumes`` : « Résumés — l'essentiel à retenir » (Mathématiques CE1 → CM2, Français CM1,
  révision CEP : règle, méthode, exemple, 3 exercices corrigés), version enseignant (corrigé) et version élève
  imprimable (sans les réponses), PDF à l'unité ou par lot (collection / cours / matière).
* v1.23 — résumés pour chaque cours (CI → CM2) dans chaque matière (Français, Mathématiques, Éducation sociale, EST,
  EPS, Éducation artistique), rattachés aux SA / unités : tableau cours × matière dans l'onglet Résumés et « Résumés de la
  semaine » à côté des fiches dans la planification (vue semaine).
Droit « preparation » (app.DROITS) : enseignant, directeur, administrateur, conseillers et responsables (CS / DDEMP,
lecture). L'enseignant n'écrit que pour ses classes (H.classes_autorisees()).
"""
import gzip
import html as _html
import io
import json
import os
import re
import threading
import zipfile
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

COURS = ["MAT", "CI", "CP", "CE1", "CE2", "CM1", "CM2"]
COURS_LIB = {"MAT": "Maternelle", "CI": "CI", "CP": "CP", "CE1": "CE1", "CE2": "CE2", "CM1": "CM1", "CM2": "CM2"}
NIVEAU_COURS = {"Maternelle 1": "MAT", "Maternelle 2": "MAT", "CI": "CI", "CP": "CP", "CE1": "CE1", "CE2": "CE2", "CM1": "CM1", "CM2": "CM2"}
NIVEAU_SYNO = {"Maternelle 1": "maternelle1", "Maternelle 2": "maternelle2", "CI": "ci", "CP": "cp", "CE1": "ce1", "CE2": "ce2",
               "CM1": "cm1", "CM2": "cm2"}
MOIS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
# colonnes de la planification annuelle / lignes de la planification mensuelle (m_synoptique) -> matière du corpus
COL_MATIERE = {"francais": "francais", "maths": "maths", "es_morale": "es", "es_civisme": "es", "es_histoire": "es",
               "es_geographie": "es", "est": "est", "eps": "eps", "ea_chant": "ea", "ea_poesie": "ea", "ea_conte": "ea",
               "ea_dessin": "ea", "ea_couture": "ea"}
ORDRE_MAT = ["francais", "maths", "es", "est", "eps", "ea", "dg"]
CHAMPS = [("titre", "Titre de la séance"), ("intitule", "Intitulé / thème"), ("sous_matiere", "Sous-matière / activité"),
          ("unite", "Unité / dossier / SA"), ("duree", "Durée"), ("cd", "Compétence disciplinaire"),
          ("ct", "Compétences transversales / transdisciplinaires"), ("contenus", "Contenus de formation (connaissances et techniques)"),
          ("objectifs", "Objectifs"), ("strategies", "Stratégies objet d'apprentissage / d'enseignement"),
          ("materiel", "Matériel"), ("evaluation", "Évaluation"), ("projection", "Projection / réinvestissement"),
          ("je_retiens", "Je retiens"), ("observations", "Observations de l'enseignant")]
CLES_TEXTE = [c for c, _l in CHAMPS]
MAX_LIGNES = 20
PAR_PAGE = 30
PAR_MATIERE = 6      # fiches proposées par matière pour la semaine (la liste complète reste filtrable)

SCHEMA = """
CREATE TABLE IF NOT EXISTS prep_fiches (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    classe_id INTEGER,
    date_seance TEXT,
    cours TEXT, matiere TEXT, sa INTEGER, seance INTEGER,
    titre TEXT NOT NULL,
    donnees TEXT NOT NULL,                -- JSON : champs APC + deroulement [[phase, activités, résultats]]
    source_id TEXT,                       -- fiche de la bibliothèque adaptée (id du corpus), modèle « modele:<id> »
    cree_le TEXT, maj_le TEXT
);
CREATE INDEX IF NOT EXISTS idx_prep_fiches ON prep_fiches (ecole_id, user_id, classe_id);
"""

_CORPUS = {}
FICHES_DEBORDANTES = set()   # v2.2 : fiches qui dépassent encore deux pages (suivi)
_VERROU_CORPUS = threading.Lock()


def corpus():
    """Corpus pédagogique (chargé une fois) + index. v1.31.1 : un seul chargement même si plusieurs pages le demandent
    en même temps (serveur à plusieurs fils) ; préchargé en arrière-plan au démarrage de l'application autonome."""
    if _CORPUS:
        return _CORPUS
    with _VERROU_CORPUS:
        return _charger_corpus()



def _lire_fichier_corpus(pdfs):
    """v2.1.1 : sur Android, la fabrication de l'APK retire l'extension « .gz » des fichiers de l'application
    (static/pedafiche_corpus.json, non compressé) ; on accepte les deux formes, et un corpus absent ou illisible
    ne doit jamais empêcher l'application de s'ouvrir (page de connexion comprise)."""
    for nom in ("pedafiche_corpus.json.gz", "pedafiche_corpus.json"):
        p = pdfs.fichier_static(nom)
        if not p:
            continue
        try:
            with open(p, "rb") as f:
                gz = f.read(2) == b"\x1f\x8b"
            if gz:
                with gzip.open(p, "rt", encoding="utf-8") as f:
                    return json.load(f)
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001 - fichier abîmé : essayer l'autre forme, sinon corpus vide
            continue
    vide = {k: [] for k in ("cours", "programmes", "guides", "modeles", "fiches", "resumes", "doublons", "manuels",
                            "mesures_correctives", "revisions")}
    vide.update({k: {} for k in ("matieres", "manquants", "inventaire_cm1", "lots", "programme_en_vigueur", "maternelle")})
    vide.update(version=0, source="", version_contenu="", _absent=True)
    return vide

# v2.2 — textes coupés dans les fiches importées (fin de ligne perdue à l'extraction) et fautes de frappe répétées
_COMPLETIONS = [
    ("maîtrise de l’intonation du débit et de", "maîtrise de l’intonation, du débit et de la prononciation"),
    ("maîtrise de l'intonation du débit et de", "maîtrise de l'intonation, du débit et de la prononciation"),
    ("(lecture de texte/ narration des faits du", "(lecture de texte / narration des faits du texte)"),
    ("Elaborer une explication à un phénomène, à un objet de", "Élaborer une explication à un phénomène, à un objet de son environnement"),
    ("Elaborer une explication à un phénomène, à un objet, de", "Élaborer une explication à un phénomène, à un objet de son environnement"),
    ("Construire une représentation correcte des", "Construire une représentation correcte des phénomènes et des objets de son environnement"),
    ("Apprécier l’apport de la science et de la technologie à l’activité humaine et",
     "Apprécier l’apport de la science et de la technologie à l’activité humaine et à la qualité de la vie"),
]
_FAUTES = [("sufflet", "sifflet"), ("feuille, de resultas", "feuille de résultats"), ("resultas", "résultats"),
           ("planchette, centre,", "planchette, cendre,"), ("croyon", "crayon"), ("BBalle", "Balle"), ("cercle de un pied", "cercle d’un pied")]
_MOTS_SUSPENDUS = re.compile(r"(?:\s(?:et de|de|du|des|et|la|le|les|à|au|aux|en|l’|l'|d’|d'|pour|par|avec|sur|un|une))\s*$")


def _reparer_texte(v):
    if not isinstance(v, str) or not v.strip():
        return v
    t = v
    for a, b in _FAUTES:
        t = t.replace(a, b)
    for a, b in _COMPLETIONS:
        if t.rstrip().endswith(a):
            return t.rstrip()[: -len(a)] + b
    t2 = t.rstrip()
    if t2.endswith((",", ";")):
        return t2[:-1].rstrip() + "."
    if _MOTS_SUSPENDUS.search(t2):
        return t2 + " […]"        # texte incomplet dans la fiche d'origine : on le signale au lieu d'une phrase coupée
    return t


# v2.2 — filigrane d'un auteur tiers resté dans le texte des fiches importées : ses lettres, lues verticalement à
# l'extraction, forment des lignes de 1 à 3 lettres (« GO / ITO / Ma / thi / as », « TO / G / C / OF / F / IL »…)
_FILIGRANE_JETONS = {"GO", "G", "ITO", "TO", "HI", "Ma", "thi", "as", "C", "OF", "F", "FF", "IL", "N", "US", "GA", "CO", "O", "H",
                     "I", "T", "M", "A", "L", "S", "U"}
_FILIGRANE_NOMS = re.compile(r"\b(?:go\s*hi\s*to|gohito)\b(?:\s+mathias)?|\bmathias\s+gohito\b", re.I)
# entête brute de la fiche suivante collée dans une case du déroulement (extraction PDF)
_DEBORDEMENT = re.compile(r"(?:(?<=\n)|^)\s*(?:\d{1,4}\s*\n+\s*)?(?:TH[ÈE]ME\s*:|UNIT[ÉE]\s*N\s*°\s*\d|FICHE DE (?:PR[ÉE]PARATION|FRAN[CÇ]AIS|MATH|"
                          r"L.[ÉE]DUCATION|EPS|EST|ES)\b|Fn°)", re.I)
_RESIDU_ENTETE = re.compile(r"^\s*(?:CONSIGNES|R[ÉE]SULTATS\s*\n?\s*ATTENDUS)\s*\n", re.I)
REPARATIONS = {"filigrane": 0, "debordement": 0, "residu": 0, "coupe": 0}


_FILIGRANE_FORTS = {"GO", "GOIT", "GOH", "GOHI", "ITO", "HITO", "OM", "Ma", "thi", "as", "TO", "OF", "FF", "IL"}
_FILIGRANE_LIGNE = re.compile(r"^(?:[A-Za-z]{1,2}(?:\s[A-Za-z]{1,2}){1,6}|s\s?\d{2}|\d{2}(?:\s\d{2}){0,3}|GOIT|GOH|GOHI|HITO|OM)$")


def _fragment(l):
    l = l.strip()
    return bool(l) and (l in _FILIGRANE_JETONS or bool(_FILIGRANE_LIGNE.match(l)))


def _sans_filigrane(t):
    """Retire les suites d'au moins deux lignes faites seulement de fragments du filigrane (lettres isolées ou espacées,
    morceaux de numéro de téléphone), quand la suite contient au moins un morceau caractéristique du nom."""
    if not isinstance(t, str) or "\n" not in t:
        return t
    lignes = t.split("\n")
    garder = [True] * len(lignes)
    i = 0
    while i < len(lignes):
        j, nb, idx = i, 0, []
        while j < len(lignes) and (lignes[j].strip() == "" or _fragment(lignes[j])):
            if lignes[j].strip():
                nb += 1
                idx.append(j)
            j += 1
        fort = any(lignes[k].strip() in _FILIGRANE_FORTS or re.match(r"^a\s?t\s?h\s?i\s?a", lignes[k].strip()) for k in idx)
        if nb >= 2 and fort:
            for k in range(i, j):
                garder[k] = k not in idx and garder[k]
            REPARATIONS["filigrane"] += 1
            i = j
        else:
            i += 1
    out = "\n".join(l for l, g_ in zip(lignes, garder) if g_)
    # morceaux isolés du nom (« at h i a ») et en-têtes de tableau restés dans le texte (« CONSIGNES », « RÉSULTATS ATTENDUS »)
    out2 = re.sub(r"(?m)^[ \t]*(?:a\s?t\s?h\s?i\s?a(?:\s?s)?|GOIT|GOHITO|G\s?O\s?H\s?I\s?T\s?O|CONSIGNES|R[ÉE]SULTATS\s+ATTENDUS|"
                  r"TO|GA|FF|IL|GO|ITO|OM|Ma|thi)[ \t]*$\n?", "", out)
    if out2 != out:
        REPARATIONS["filigrane"] += 1
        out = out2
    out = re.sub(r"\n{3,}", "\n\n", out)
    return _FILIGRANE_NOMS.sub("", out)


_SOUS_TITRES = re.compile(r"(?m)^[ \t]*(INTRODUCTION|MISE EN SITUATION|R[ÉE]ALISATION|RETOUR ET PROJECTION|"
                          r"[ÉE]mergence des acquis ant[ée]rieurs|Proposition de nouvelles acquisitions|Rappel|PHASE INTRODUCTIVE|"
                          r"Phase introductive|EXERCICE STRUCTURAL[^\n]*|EXERCICE MENTAL|LEÇON DU JOUR[^\n]*|Activit[ée] \d+[^\n]{0,40})[ \t]*$")


_SECTIONS_BRUTES = re.compile(r"(?m)^\s*(?:\*\*)?(INTRODUCTION|MISE EN SITUATION|R[ÉE]ALISATION|Titre\b|CONSIGNES|R[ÉE]SULTATS ATTENDUS|"
                             r"[ÉE]mergence des acquis)", re.I)
_MOTS_COLLES = re.compile(r"[a-zàâçéèêëîïôûù]{3,}[A-ZÉÈÀ][a-zàâçéèêëîïôûù]{2,}")
_DIALOGUE = re.compile(r"^(?:[ÉE]l[èe]ve|Ma[iî]tre|Enseignant|Apprenant|Tous|Groupe|Question|R[ée]ponse)", re.I)


def case_illisible(t):
    """v2.2.1 — case de déroulement abîmée à l'extraction : deux colonnes du PDF mêlées ligne à ligne (sous-titres répétés,
    mots collés d'une colonne à l'autre)."""
    if not isinstance(t, str):
        return False
    secs = [x.upper() for x in _SECTIONS_BRUTES.findall(t)]
    return bool(_MOTS_COLLES.search(t)) or (len(secs) >= 2 and len(set(secs)) < len(secs))


def fin_coupee(t):
    t = (t or "").strip()
    return len(t) > 200 and bool(re.search(r"[a-zàâçéèêëîïôûù]{2,}$", t)) and not re.search(r"[.!?:;»)\]…]$", t)


def lignes_doublees(t):
    lignes = [x.strip() for x in str(t or "").split("\n") if x.strip()]
    return sum(1 for a, b in zip(lignes, lignes[1:]) if a == b and len(a) > 8 and not _DIALOGUE.match(a))


def activite_apc(phase, titre):
    p = (phase or "").lower()
    t = (titre or "la séance").strip().rstrip(".")
    if "introduction" in p or "situation" in p:
        return (f"\u25aa Présentation de la situation de départ liée à « {t} ».\n\u25aa Dis ce que tu sais déjà sur le sujet "
                "(émergence des acquis antérieurs).\n\u25aa Formule ce que tu vas apprendre aujourd'hui.")
    if "retour" in p or "projection" in p or "objectivation" in p:
        return ("\u25aa Dis ce que tu as appris.\n\u25aa Dis comment tu l'as appris.\n\u25aa Dis les difficultés rencontrées.\n"
                "\u25aa Dis à quelles occasions tu vas utiliser ce que tu as appris.")
    return (f"\u25aa Observe / lis le support de la séance (« {t} ») et réponds individuellement aux questions.\n"
            "\u25aa Échange en groupe et mets-toi d'accord sur les réponses.\n"
            "\u25aa Présente les résultats de ton groupe ; mise en commun et synthèse avec l'enseignant(e).\n"
            "(Activité reconstituée selon l'APC : le texte d'origine était illisible.)")


def _case_deroulement(t, phase, titre=None):
    t = _sans_filigrane(t)
    if not isinstance(t, str):
        return t
    if case_illisible(t):                       # v2.2.1 : colonnes mêlées -> activité APC propre
        REPARATIONS["illisible"] = REPARATIONS.get("illisible", 0) + 1
        return activite_apc(phase, titre)
    if lignes_doublees(t):                      # lignes répétées par l'extraction
        REPARATIONS["doublons"] = REPARATIONS.get("doublons", 0) + 1
        out, precedente = [], None
        for l in t.split("\n"):
            ls = l.strip()
            if ls and ls == precedente and len(ls) > 8 and not _DIALOGUE.match(ls):
                continue
            if ls:
                precedente = ls
            out.append(l)
        t = "\n".join(out)
    if fin_coupee(t):                           # texte coupé net en fin de case
        REPARATIONS["fin"] = REPARATIONS.get("fin", 0) + 1
        lignes = t.rstrip().split("\n")
        if len(lignes) > 1 and len(lignes[-1].strip()) < 45:
            t = "\n".join(lignes[:-1]).rstrip()
        if fin_coupee(t) or not re.search(r"[.!?:;»)\]…]$", t.strip()):
            t = t.rstrip() + " […]"
    # bloc brut d'une fiche extraite d'un PDF (plusieurs étapes dans une case) : sous-titres en gras, lisibles
    if len(_SOUS_TITRES.findall(t)) >= 2 and "**" not in t:
        REPARATIONS["residu"] += 1
        t = _SOUS_TITRES.sub(lambda m: "**" + m.group(1).strip() + "**", t)
    m = _DEBORDEMENT.search(t)
    if m:
        REPARATIONS["debordement"] += 1
        t = t[:m.start()].rstrip()
        if not t:
            p = (phase or "").lower()
            if "réalisation" in p or "activit" in p or "realisation" in p:
                t = ("\u25aa Activités de la séance d'après le guide pédagogique et le manuel : lecture et exploitation du support, "
                     "travail individuel puis en groupe, mise en commun.")
            else:
                t = "\u25aa Voir le guide pédagogique (étape de la séance)."
    while _RESIDU_ENTETE.match(t or ""):
        REPARATIONS["residu"] += 1
        t = _RESIDU_ENTETE.sub("", t, count=1).lstrip("\n")
    return t


_DEROULEMENT_COLLE = re.compile(r"\s(?:1\.\s*Calcul mental|STRAT[ÉE]GIES\s+DESCRIPTION|3\.1\.\s*INTRODUCTION|D[ÉE]ROULEMENT\b)")


# v2.2.2 — fiches du guide CP 2022 abîmées à l'extraction : allégées pour tenir sur une feuille recto verso
_CHAMP_POLLUE = re.compile(r"(?:^|\s)(?:(?:\d\.\s*)?Objectifs de la s[ée]quence|\d\.\s*Mat[ée]riel\b|Support\s*:|T[âa]che\s*:|"
                           r"« Aujourd.hui|\*{0,2}(?:Je fais|Nous faisons|Tu fais)\*{0,2}\s*[|\[A-ZÉÀ«]|\d\.\d\.\s*R[ÉE]ALISATION|I[lI1]\.\s*COMP[ÉE]TENCES)")
_ETIQUETTE = re.compile(r"^\s*\*\*(?:Je fais|Nous faisons|Tu fais)\*\*\s*$")
_PLANIF_DEBUT = re.compile(r"^\s*(?:SA\s*\d|FICHE\s+N|.*[ÉE]L[ÉE]MENTS DE PLANIFICATION|\d\.\s*Dur[ée]e\b)", re.I)
_PLANIF_FIN = re.compile(r"^\s*\d\.\s*(?:Calcul mental|Rappel|R[ée]vision|V[ée]rification)", re.I)
_INTEGRATION_SUIVANTE = re.compile(r"\n\s*(?:Situation d.int[ée]gration\s*\n\s*)?SA couvertes\s*:")
_TABLEAU_INTEGRATION = re.compile(r"(?:Situations?\s+SA couvertes|I[lI1]\.\s*COMP[ÉE]TENCES ET CONTENUS)")
CD_ILLISIBLE = "Compétences disciplinaires n° 1, 2 et 3 (voir le guide de l'enseignant)."


def _alleger_case(t, premiere=False, derniere=False):
    if not isinstance(t, str):
        return t
    t = re.sub(r"(\*\*(?:Je fais|Nous faisons|Tu fais)\*\*)\s*[|\[]\s*", r"\1 ", t)
    t = re.sub(r"(?m)^(\s*)[|\[]\s*", r"\1", t)
    lignes = t.split("\n")
    if premiere:                                   # bloc « éléments de planification » recopié dans les préliminaires
        i = next((k for k, l in enumerate(lignes) if _PLANIF_DEBUT.match(l)), None)
        j = next((k for k in range(i + 1, len(lignes)) if _PLANIF_FIN.match(lignes[k])), None) if i is not None else None
        if j is not None:
            lignes = lignes[:i] + lignes[j:]
    # tableau d'intégration mêlé (deux colonnes du PDF) jusqu'à « Fiches N° … » / « Titre : »
    t = "\n".join(lignes)
    m = _TABLEAU_INTEGRATION.search(t)
    if m:
        f_ = re.search(r"(?m)^\s*(?:Fiches?\s*N\s*°|Titre\s*:)", t[m.end():])
        if f_:
            t = t[:m.start()] + t[m.end() + f_.start():]
    if derniere:                                   # début de la semaine d'intégration suivante recopié en fin de fiche
        m = _INTEGRATION_SUIVANTE.search(t)
        if m and m.start() > 150:
            t = t[:m.start()]
    out = []
    for l in t.split("\n"):                        # étiquettes orphelines successives (colonnes séparées) : la dernière reste
        if out and _ETIQUETTE.match(l) and _ETIQUETTE.match(out[-1]):
            out[-1] = l
        else:
            out.append(l)
    t = "\n".join(out)
    t = re.sub(r"(?<![.:;!?»\n*])\n(?=[a-zàâçéèêëîïôûùœ])", " ", t)     # retours à la ligne de l'OCR au milieu d'une phrase
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def _alleger_resultats(t):
    if not isinstance(t, str) or "\n" not in t:
        return t
    vus, out = set(), []
    for l in t.split("\n"):
        c = re.sub(r"\W+", " ", l).strip().lower()
        if not c or c in vus or re.match(r"^\s*\u25aa\s*\u2022", l) or re.match(r"^\s*\u25aa\s*L.enseignant\b", l):
            continue
        vus.add(c)
        out.append(l)
    return "\n".join(out) or t


def _alleger_fiche(f):
    avant = len(json.dumps(f, ensure_ascii=False))
    for k in ("strategies", "objectifs", "materiel", "cd", "contenus", "ct"):
        v = f.get(k)
        if isinstance(v, str) and len(v) > 120:
            m = _CHAMP_POLLUE.search(v)
            if m:
                f[k] = v[:m.start()].rstrip(" ;,.") + ("." if v[:m.start()].strip() else "")
                f[k] = "" if f[k] == "." else f[k]
    if f.get("strategies") and f.get("materiel") and f["strategies"].rstrip(". ") == f["materiel"].rstrip(". "):
        f["strategies"] = ""
    elif f.get("strategies") and not f.get("materiel") and re.match(r"^[^.;:]*(?:bâtonnets|cailloux|étiquettes|pipettes|ardoise|craie)", f["strategies"]) \
            and not re.search(r"travail|résolution|démarche", f["strategies"], re.I):
        f["materiel"], f["strategies"] = f["strategies"], ""          # liste du matériel rangée dans « stratégies »
    if isinstance(f.get("cd"), str) and len(f["cd"]) > 600 and (case_illisible(f["cd"]) or re.search(
            r"Comp[ée]tences? disciplinaires? n° ?\d\s+Comp[ée]tences? disciplinaires? n° ?\d", f["cd"])):
        f["cd"] = CD_ILLISIBLE
    d = f.get("deroulement")
    if isinstance(d, list):
        n = len(d)
        f["deroulement"] = [[(_alleger_case(x, i == 0, i == n - 1) if k == 1 else _alleger_resultats(x) if k == 2 else x)
                             for k, x in enumerate(l)] if isinstance(l, list) else l for i, l in enumerate(d)]
    if len(json.dumps(f, ensure_ascii=False)) < avant:
        REPARATIONS["allegees"] = REPARATIONS.get("allegees", 0) + 1


def _reparer_fiches(c):
    for f in c.get("fiches") or []:
        # v2.2 : déroulement entier recopié dans « stratégies » / « objectifs » à l'extraction (guide CP 2022…) : coupé
        for k in ("strategies", "objectifs", "cd", "contenus", "ct", "materiel"):
            v = f.get(k)
            if isinstance(v, str) and len(v) > 700:
                m = _DEROULEMENT_COLLE.search(v)
                if m:
                    REPARATIONS["debordement"] += 1
                    f[k] = v[:m.start()].rstrip(" ;,") or ""
        if f.get("strategies") and f.get("strategies") == f.get("objectifs"):
            f["strategies"] = "Travail individuel — travail en groupe — travail collectif."
        for k in ("titre", "intitule"):              # « NationsUnies » -> « Nations Unies »
            if isinstance(f.get(k), str) and _MOTS_COLLES.search(f[k]):
                f[k] = re.sub(r"([a-zàâçéèêëîïôûù]{3,})([A-ZÉÈÀ][a-zàâçéèêëîïôûù]{2,})", r"\1 \2", f[k])
        for k in ("contenus", "cd", "ct", "objectifs", "materiel", "strategies", "evaluation", "projection", "titre",
                  "je_retiens", "observations", "intitule"):
            if isinstance(f.get(k), str):
                v = _sans_filigrane(f[k])
                v2 = _reparer_texte(v)
                if v2 != v:
                    REPARATIONS["coupe"] += 1
                f[k] = v2
        if isinstance(f.get("deroulement"), list):
            f["deroulement"] = [[(_case_deroulement(x, (ligne or [""])[0], f.get("titre")) if k else _sans_filigrane(x)) if isinstance(x, str) else x
                                 for k, x in enumerate(ligne)]
                                if isinstance(ligne, list) else ligne for ligne in f["deroulement"]]
        _alleger_fiche(f)
    for cle in ("guides", "modeles", "resumes", "programmes", "manuels", "mesures_correctives", "revisions"):
        for x in c.get(cle) or []:
            if isinstance(x, dict):
                for k, v in list(x.items()):
                    if isinstance(v, str) and _FILIGRANE_NOMS.search(v):
                        x[k] = _FILIGRANE_NOMS.sub("", v)


def _charger_corpus():
    if not _CORPUS:
        import pdfs
        c = _lire_fichier_corpus(pdfs)
        _reparer_fiches(c)
        for x in c["fiches"] + c["programmes"]:
            for k in ("sa", "seance", "num", "dossier"):
                v = x.get(k)
                if isinstance(v, str):
                    x[k] = int(v) if v.strip().isdigit() else None
        c["fiche_par_id"] = {x["id"]: x for x in c["fiches"]}
        c["guide_par_id"] = {x["id"]: x for x in c["guides"]}
        c["prog_par_id"] = {x["id"]: x for x in c["programmes"]}
        c["modele_par_id"] = {x["id"]: x for x in c["modeles"]}
        rpf = {}                                    # v1.29 : résumé(s) de chaque séance (fiche) de la progression
        for r in c.get("resumes") or []:
            for fid in r.get("fiches") or []:
                rpf.setdefault(fid, []).append(r)
        c["resumes_par_fiche"] = rpf
        c["manuel_par_id"] = {x["id"]: x for x in c.get("manuels") or []}             # v1.31
        c["revision_par_id"] = {x["id"]: x for x in c.get("revisions") or []}
        _CORPUS.update(c)
    return _CORPUS


def nom_matiere(m):
    return corpus()["matieres"].get(m, m)


def references(texte):
    """« U1 semaine2 à U3 semaine 1 », « D1 SA1 Séq 8 à 15 SA2 et 3 », « SA2 Séq3 à SA3 » -> numéros cités."""
    t = str(texte or "")
    sa = set()
    for m in re.finditer(r"SA\s*(\d+)((?:\s*(?:,|et|à|-)\s*\d+)*)", t, re.I):
        sa.add(int(m.group(1)))
        nums = [int(x) for x in re.findall(r"\d+", m.group(2) or "")]
        if re.search(r"à|-", m.group(2) or "") and nums:
            sa.update(range(int(m.group(1)), max(nums) + 1) if max(nums) - int(m.group(1)) < 12 else nums)
        else:
            sa.update(nums)
    u = {int(x) for x in re.findall(r"\bU\s*(\d+)", t)}
    dd = {int(x) for x in re.findall(r"\bD\s*(\d+)", t)}
    plages = re.findall(r"\bU\s*(\d+)[^U]*?à\s*U\s*(\d+)", t)
    for a, b in plages:
        if 0 <= int(b) - int(a) < 12:
            u.update(range(int(a), int(b) + 1))
    return {"sa": sorted(sa), "u": sorted(u), "d": sorted(dd)}


def num_unite(f):
    m = re.search(r"(\d+)", f.get("unite") or "")
    return int(m.group(1)) if m else None


def fiches_filtrees(cours=None, matiere=None, smat=None, sa=None, seance=None, texte=None, statut=None):
    out = corpus()["fiches"]
    if cours:
        out = [f for f in out if f["cours"] == cours]
    if matiere:
        out = [f for f in out if f["matiere"] == matiere]
    if smat:
        out = [f for f in out if (f.get("sous_matiere") or "") == smat]
    if sa:
        out = [f for f in out if f.get("sa") == sa]
    if seance:
        out = [f for f in out if f.get("seance") == seance]
    if statut in ("source", "concue"):
        out = [f for f in out if f.get("statut") == statut]
    if texte:
        mots = [_sans_accent(m) for m in texte.split() if m.strip()]

        def ok(f):
            h = _sans_accent(" ".join(str(f.get(k) or "") for k in ("titre", "intitule", "sous_matiere", "contenus", "unite", "source")))
            return all(m in h for m in mots)
        out = [f for f in out if ok(f)]
    return sorted(out, key=lambda f: (COURS.index(f["cours"]) if f["cours"] in COURS else 9,
                                      ORDRE_MAT.index(f["matiere"]) if f["matiere"] in ORDRE_MAT else 9,
                                      num_unite(f) or 0, f.get("sa") or 0, f.get("seance") or 0, f.get("titre") or ""))


def _sans_accent(t):
    import unicodedata
    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()


def correspondances(cours, matiere, refs):
    """Fiches de la bibliothèque qui correspondent aux numéros cités par la planification (unités en français,
    dossiers puis SA en mathématiques, SA ailleurs)."""
    if not (refs["sa"] or refs["u"] or refs["d"]):
        return []
    out = []
    for f in fiches_filtrees(cours=cours, matiere=matiere):
        nu = num_unite(f)
        if matiere == "francais" and refs["u"]:
            ok = nu in refs["u"]
        elif matiere == "maths" and refs["d"]:
            ok = nu in refs["d"]          # les SA des fiches de mathématiques recommencent à chaque dossier
        else:
            ok = bool(refs["sa"]) and f.get("sa") in refs["sa"]
        if ok:
            out.append(f)
    return out


def refs_de_la_semaine(refs, matiere, jour):
    """Planification annuelle (un mois) : ne garder que l'unité / la SA de la semaine du mois en cours."""
    cle = "u" if matiere == "francais" and refs["u"] else "sa" if refs["sa"] else None
    if not cle or len(refs[cle]) < 2:
        return refs
    k = min(3, (jour.day - 1) // 7)
    liste = refs[cle]
    return dict(refs, **{cle: [liste[min(len(liste) - 1, k * len(liste) // 4)]]})


# ---------------------------------------------------------------- texte : HTML et PDF
def txt_html(t):
    """Texte de fiche (« **gras** », sauts de ligne, puces) -> HTML échappé."""
    s = _html.escape(str(t or ""))
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    return s.replace("\n", "<br>")


def txt_pdf(t):
    s = str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("\u25aa", "•").replace("\u2610", "□")   # glyphes absents de Helvetica
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    return s.replace("\n", "<br/>")


def _equilibrer(t):
    """v1.31.1 — balises en ligne (<b> <i> <u>) équilibrées : une balise ouverte dans un bloc et refermée dans le suivant
    (HTML des guides extraits) faisait échouer le PDF (« Parse error: saw </b> instead of expected </para> »)."""
    pile, out = [], []
    for m in re.split(r"(</?(?:b|i|u)>)", t):
        g = re.fullmatch(r"<(/?)(b|i|u)>", m)
        if not g:
            out.append(m)
        elif not g.group(1):
            pile.append(g.group(2)); out.append(m)
        elif g.group(2) in pile:
            while pile:
                x = pile.pop(); out.append(f"</{x}>")
                if x == g.group(2):
                    break
    out += [f"</{x}>" for x in reversed(pile)]
    return "".join(out)


def _paragraphe_sur(t, style):
    """Paragraph reportlab ; en cas de balisage invalide, le texte brut (jamais d'erreur 500)."""
    from reportlab.platypus import Paragraph
    try:
        return Paragraph(_equilibrer(t), style)
    except ValueError:
        return Paragraph(_html.escape(re.sub(r"<[^>]+>", " ", t)), style)


class _GuideVersPdf(HTMLParser):
    """HTML nettoyé d'un guide -> flowables reportlab (titres, paragraphes, listes, tableaux)."""

    def __init__(self, styles, largeur):
        super().__init__(convert_charrefs=True)
        self.st, self.largeur, self.out = styles, largeur, []
        self.tampon, self.bloc, self.liste, self.table, self.ligne, self.cellule = [], None, 0, None, None, None

    def _vider(self):
        t = "".join(self.tampon).strip()
        self.tampon = []
        if not t:
            return
        from reportlab.platypus import Paragraph
        st = {"h2": self.st["h2"], "h3": self.st["h3"], "h4": self.st["h4"]}.get(self.bloc, self.st["p"])
        if self.liste and self.bloc == "li":
            self.out.append(_paragraphe_sur("• " + t, self.st["li"]))
        else:
            self.out.append(_paragraphe_sur(t, st))

    def handle_starttag(self, tag, attrs):
        if tag in ("b", "strong", "i", "em", "u"):
            self.tampon.append({"strong": "<b>", "em": "<i>"}.get(tag, f"<{tag}>"))
        elif tag == "br":
            self.tampon.append("<br/>")
        elif tag == "table":
            self._vider()
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.ligne = []
        elif tag in ("td", "th") and self.ligne is not None:
            self.cellule = []
        elif tag in ("ul", "ol"):
            self._vider()
            self.liste += 1
        elif tag in ("h2", "h3", "h4", "p", "li"):
            self._vider()
            self.bloc = tag

    def handle_endtag(self, tag):
        if tag in ("b", "strong", "i", "em", "u"):
            t = {"strong": "</b>", "em": "</i>"}.get(tag, f"</{tag}>")
            (self.cellule if self.cellule is not None else self.tampon).append(t)
        elif tag in ("td", "th") and self.cellule is not None:
            self.ligne.append("".join(self.cellule).strip())
            self.cellule = None
        elif tag == "tr" and self.ligne is not None:
            self.table.append(self.ligne)
            self.ligne = None
        elif tag == "table" and self.table is not None:
            from reportlab.lib import colors
            from reportlab.platypus import Paragraph, Table, TableStyle
            n = max((len(r) for r in self.table), default=0)
            if n:
                data = [[_paragraphe_sur(c, self.st["td"]) for c in r] + [""] * (n - len(r)) for r in self.table]
                t = Table(data, colWidths=[self.largeur / n] * n, repeatRows=1)
                t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#667085")),
                                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E4ECF5")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                self.out.append(t)
            self.table = None
        elif tag in ("ul", "ol"):
            self._vider()
            self.liste = max(0, self.liste - 1)
        elif tag in ("h2", "h3", "h4", "p", "li"):
            self._vider()
            self.bloc = None

    def handle_data(self, data):
        d = data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if self.cellule is not None:
            self.cellule.append(d)
        elif self.table is None:
            self.tampon.append(d)


# ---------------------------------------------------------------- v1.19 : résumés (PDF enseignant / élève)
COLLECTIONS_RES = [("maths", "Mathématiques CI → CM2"), ("francais", "Français CI → CM2"), ("francais-cm1", "Français CM1 (par unité)"),
                   ("es", "Éducation sociale CI → CM2"), ("est", "Éducation scientifique et technologique CI → CM2"),
                   ("eps", "Éducation physique et sportive CI → CM2"), ("ea", "Éducation artistique CI → CM2"), ("cep", "Révision CEP")]
COLLECTION_DE = {"Mathématiques": "maths", "Français": "francais", "Français CM1": "francais-cm1", "Éducation sociale": "es",
                 "Éducation scientifique et technologique": "est", "Éducation physique et sportive": "eps",
                 "Éducation artistique": "ea", "Révision CEP": "cep"}
COURS_RES = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
MATS_RES = ["francais", "maths", "es", "est", "eps", "ea"]


def table_resumes(rs):
    """v1.23 — nombre de résumés par cours × matière (toutes collections confondues)."""
    t = {(c, m): 0 for c in COURS_RES for m in MATS_RES}
    for r in rs:
        if (r["cours"], r["matiere"]) in t:
            t[(r["cours"], r["matiere"])] += 1
    return t


def _num_fiche(f):
    """Numéro de SA / unité / dossier d'une fiche (Français : numéro d'unité)."""
    if f.get("matiere") == "francais":
        m = re.search(r"(\d+)", str(f.get("unite") or ""))
        if m:
            return int(m.group(1))
    for k in ("sa", "dossier"):
        if isinstance(f.get(k), int):
            return f[k]
    m = re.search(r"(?:SA|DOSSIER|UNIT[EÉ])\s*N?°?\s*(\d+)", str(f.get("unite") or ""), re.I)
    return int(m.group(1)) if m else None


OUTILS_FR = ["Sons et graphies", "Structures de la langue", "Grammaire", "Conjugaison", "Orthographe", "Vocabulaire", "Lecture",
             "Expression écrite", "Écriture", "Communication orale"]
DOMAINES_MA = ["Numération et arithmétique", "Mesures", "Géométrie", "Résolution de problèmes"]
MOIS_SCO = ["Septembre", "Octobre", "Novembre", "Décembre", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin"]


MATS_PROG = ("francais", "maths", "es", "est", "eps", "ea")     # v1.27.1 / v1.29 : matières placées dans la progression annuelle


def table_seances():
    """v1.29 — couverture des séances de la progression par un résumé de séance (cours -> matière -> {résumés, séances, couvertes})."""
    return ((corpus().get("lots") or {}).get("v129-resumes-seances") or {}).get("table") or {}


def resumes_de_fiche(fid):
    """v1.29 — résumés rattachés à une séance (fiche) : résumé de la séance d'abord, puis résumés de SA rattachés."""
    return sorted(corpus().get("resumes_par_fiche", {}).get(fid) or [], key=lambda r: (not r.get("seance_resume"), r["titre"]))


def table_es_est():
    """v1.27.1 — couverture des SA d'Éducation sociale (dont morale et civisme) et d'EST par cours (lot v127-es-est du corpus)."""
    return ((corpus().get("lots") or {}).get("v127-es-est") or {}).get("table") or {}


def table_domaines(rs):
    """v1.25 — nombre de résumés par cours × matière × domaine (Français : outils de la langue ; Mathématiques : domaines)."""
    t = {}
    for r in rs:
        if r["matiere"] in ("francais", "maths"):
            k = (r["cours"], r["matiere"], r["domaine"])
            t[k] = t.get(k, 0) + 1
    return t


def ordre_resume(r):
    """Clé d'ordre de la progression : mois scolaire, puis unité / dossier / SA / leçon, puis séance."""
    o = r.get("ordre") or [99]
    return (list(o) + [0, 0, 0])[:3] + [r["matiere"], (OUTILS_FR + DOMAINES_MA).index(r["domaine"]) if r["domaine"] in OUTILS_FR + DOMAINES_MA else 99, r["titre"]]


def _cles_fiche(f):
    """Repères d'une fiche pour la retrouver dans les ancres des résumés."""
    u = str(f.get("unite") or "")
    out = set()
    m = re.search(r"(\d+)", u)
    n = int(m.group(1)) if m else None
    if f.get("matiere") == "francais":
        if re.match(r"(?i)le[çc]on", u) and n:
            out.add(("lecon", n))
        elif n:
            out.add(("unite", n))
    elif f.get("matiere") in ("es", "est") and str(f.get("sa") or "").isdigit():
        out.add(("sa", int(f["sa"])))                 # v1.27.1 : SA d'Éducation sociale et d'EST
    elif f.get("matiere") == "maths":
        sa = f.get("sa") if isinstance(f.get("sa"), int) else None
        if "DOSSIER" in u.upper() and n:
            out.add(("dossier", n, sa) if sa else ("dossier", n))
        elif sa:
            out.add(("sa", sa))
        elif n and "SA" in u.upper():
            out.add(("sa", n))
    num = _num_fiche(f)
    if num and not out:
        out.add(("num", num))
    return out


def _cles_resume(r):
    out = set()
    for a in r.get("ancres") or []:
        t = a.get("type")
        if t == "unite":
            out.add(("unite", a["unite"]))
        elif t == "lecon":
            out.add(("lecon", a["lecon"]))
        elif t == "dossier":
            out.add(("dossier", a["dossier"], a["sa"]))
            out.add(("dossier", a["dossier"]))
        elif t == "sa":
            out.add(("sa", a["sa"]))
    for n in r.get("sa") or []:
        out.add(("num", n))
    return out


def resumes_semaine(cours, fiches_par_mat):
    """v1.23 / v1.25 — résumés « l'essentiel à retenir » qui accompagnent les fiches d'une semaine (ou d'un jour) : même cours,
    même matière, même repère de progression (unité, leçon, dossier et SA, SA) ; en français, l'outil de la langue du résumé
    doit correspondre à une sous-matière des fiches (grammaire, conjugaison…) quand les fiches en indiquent une."""
    out = {}
    rs = [r for r in corpus().get("resumes") or [] if r["cours"] == cours and r.get("collection") != "Révision CEP"]
    for mat, fiches in fiches_par_mat.items():
        if not fiches:
            continue
        cles = set()
        fids = set()
        for f in fiches:
            cles |= _cles_fiche(f)
            fids.add(f.get("id") or f.get("source_id"))
        sous = " | ".join((f.get("sous_matiere") or "").lower() for f in fiches).strip(" |")
        liste = []
        for r in rs:
            if r["matiere"] != mat:
                continue
            if r.get("fiches") and fids & set(r["fiches"]):       # v1.29 : résumé de la séance même
                liste.append(r)
                continue
            if r.get("seance_resume"):
                continue
            rc = _cles_resume(r)
            if not rc:
                mc = r.get("mots_cles") or []
                if mc and any(k in sous for k in mc):
                    liste.append(r)
                continue
            if not rc & cles:
                continue
            outil = (r.get("outil") or "").lower()
            if mat == "francais" and outil and sous and outil.split()[0][:6] not in sous and outil not in ("sons et graphies",):
                if any(o.lower().split()[0][:6] in sous for o in OUTILS_FR):
                    continue
            liste.append(r)
        if liste:
            out[mat] = sorted(liste, key=ordre_resume)
    return out


def resumes_mois(cours, mois_lib):
    """v1.25 — résumés de Français et de Mathématiques placés dans un mois de la progression annuelle du cours."""
    out = {}
    for r in corpus().get("resumes") or []:
        if r["cours"] == cours and r["matiere"] in MATS_PROG and _sans_accent(r.get("mois") or "").lower() == _sans_accent(mois_lib).lower():
            out.setdefault(r["matiere"], []).append(r)
    return {m: sorted(v, key=ordre_resume) for m, v in out.items()}


def progression_resumes(rs):
    """v1.25 — [(trimestre, [(mois, [(repère, [résumés])])])] dans l'ordre de l'année."""
    arb = {}
    for r in sorted(rs, key=ordre_resume):
        tri = r.get("trimestre") or "—"
        mois = r.get("mois") or "—"
        rep = ((r.get("ancres") or [{}])[0]).get("libelle") or "—"
        arb.setdefault(tri, {}).setdefault(mois, {}).setdefault(rep, []).append(r)
    ordre_t = ["I", "II", "III", "—"]
    return [(t, [(m, list(v.items())) for m, v in sorted(arb[t].items(), key=lambda x: MOIS_SCO.index(x[0]) if x[0] in MOIS_SCO else 99)])
            for t in sorted(arb, key=lambda x: ordre_t.index(x) if x in ordre_t else 9)]


_GLYPHES = {"→": "->", "−": "-", "ᵉ": "e", "ɔ": "o", "≈": "~", "≤": "<=", "≥": ">="}


def _res_txt(t):
    s = txt_pdf(t)
    for a, b in _GLYPHES.items():
        s = s.replace(a, b.replace("<", "&lt;").replace(">", "&gt;"))
    return s


def pdf_resumes(rs, eleve=False, titre_lot=None):
    """Résumés -> PDF A4 : règle, méthode, exemple, exercices ; corrigé (enseignant) ou lignes de réponse (élève)."""
    import pdfs
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    W, Hh = A4
    marge = 15 * mm
    larg = W - 2 * marge
    # v2.2 : même style que les fiches (v1.32) — Times New Roman 14 pt (Liberation Serif incorporée), bandeau, mention
    ps = pdfs.police_serif()
    FN, FB, FI = ps["normal"], ps["gras"], ps["italique"]
    P = lambda n, **k: ParagraphStyle(n, **{"fontName": FN, "fontSize": 14, "leading": 17.5, **k})  # noqa: E731
    st = {"t": P("t", fontName=FB, fontSize=16, leading=19, textColor=colors.white),
          "s": P("s", fontSize=11, leading=13.5, textColor=colors.HexColor("#475467")),
          "h": P("h", fontName=FB, fontSize=14.5, textColor=pdfs.BLEU, spaceBefore=5, spaceAfter=1),
          "p": P("p"), "q": P("q", leftIndent=14, firstLineIndent=-14),
          "r": P("r", fontName=FI, textColor=colors.HexColor("#067647"), leftIndent=14),
          "l": P("l", textColor=colors.HexColor("#98A2B3"), leftIndent=14),
          "m": P("m", fontName=FI, fontSize=10, leading=12, textColor=colors.grey)}
    histoire = []
    if titre_lot:
        histoire += [Paragraph(("FICHES DE RÉVISION — " if eleve else "RÉSUMÉS — L'ESSENTIEL À RETENIR — ") + _html.escape(titre_lot.upper()),
                               P("lot", fontName=FB, fontSize=16, alignment=1, textColor=pdfs.BLEU, leading=20)),
                     Paragraph(f"{len(rs)} résumé(s)" + (" — version élève (sans les réponses)" if eleve else " — version enseignant (avec corrigé)"),
                               P("lot2", fontSize=11, leading=14, alignment=1)), Spacer(1, 6)]
    for i, r in enumerate(rs):
        bandeau = Table([[Paragraph(_res_txt(r["titre"]), st["t"])]], colWidths=[larg])
        bandeau.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), pdfs.BLEU), ("TOPPADDING", (0, 0), (-1, -1), 4),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
        regle = Table([[Paragraph("<b>Je retiens</b><br/>" + _res_txt(r["regle"]), st["p"])]], colWidths=[larg])
        regle.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF4FB")), ("BOX", (0, 0), (-1, -1), 0.6, pdfs.BLEU),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
        seances = r.get("ancres") if r.get("seance_resume") else []
        tete = [bandeau, Paragraph(_html.escape(f"{r['collection']} · {r['cours']} · {r['domaine']}" + (f" · {r['etape']}" if r.get("etape") else "")
                                                + (f" · trimestre {r['trimestre']} · {r['mois']}" if r.get("seance_resume") and r.get("trimestre") else "")), st["s"])]
        if seances:
            tete.append(Paragraph(_html.escape("Séance(s) : " + " ; ".join(a["libelle"] + (f" — « {a['seance_titre']} »" if a.get("seance_titre") and a["seance_titre"] != r["titre"] else "") for a in seances)), st["s"]))
        if r.get("a_verifier"):
            tete.append(Paragraph("Titre de séance / de SA à vérifier avec le programme officiel.", st["s"]))
        tete.append(Spacer(1, 3))
        if r.get("lecture"):           # v1.31 : résumé d'un texte de lecture du manuel officiel
            idee = Table([[Paragraph("<b>Ce que dit le texte</b><br/>" + _res_txt(r["regle"]), st["p"])]], colWidths=[larg])
            idee.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF4FB")), ("BOX", (0, 0), (-1, -1), 0.6, pdfs.BLEU),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
            bloc = tete + ([Paragraph(_html.escape(r["manuel_note"]), st["s"])] if r.get("manuel_note") else []) + [idee,
                Paragraph("Personnages et informations clés", st["h"]), Paragraph(_res_txt(r["methode"]), st["p"])]
            if r.get("vocabulaire"):
                bloc += [Paragraph("Vocabulaire", st["h"]), Paragraph(_res_txt(" — ".join(r["vocabulaire"])), st["p"])]
            bloc += [Paragraph("Le message du texte", st["h"]), Paragraph(_res_txt(r["exemple"]), st["p"])]
            if r.get("actualisation"):
                bloc += [Paragraph("Et aujourd'hui ?", st["h"]), Paragraph(_res_txt(r["actualisation"]), st["p"])]
            bloc.append(Paragraph("Questions de compréhension", st["h"]))
        elif r.get("je_retiens"):      # v1.27.1 : Éducation sociale (dont morale et civisme) et EST
            regle = Table([[Paragraph("<b>Je retiens</b><br/>" + _res_txt(r["je_retiens"]), st["p"])]], colWidths=[larg])
            regle.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF4FB")), ("BOX", (0, 0), (-1, -1), 0.6, pdfs.BLEU),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
            bloc = tete + ([Paragraph("Situation de la vie courante", st["h"]), Paragraph(_res_txt(r["situation"]), st["p"])] if r.get("situation") else []) + [
                Paragraph("Valeur ou règle de vie" if r.get("emc") else "Notions essentielles", st["h"]), Paragraph(_res_txt(r["regle"]), st["p"])]
            if r.get("vocabulaire"):
                bloc += [Paragraph("Vocabulaire", st["h"])] + [Paragraph("– " + _res_txt(v), st["p"]) for v in r["vocabulaire"]]
            bloc += [Spacer(1, 3), regle]
            if r.get("engagement"):
                bloc += [Paragraph("Je m'engage", st["h"]), Paragraph(_res_txt(r["engagement"]), st["p"])]
            bloc += [Paragraph("Méthode", st["h"]), Paragraph(_res_txt(r["methode"]), st["p"]), Paragraph("Exemple", st["h"]),
                     Paragraph(_res_txt(r["exemple"]), st["p"]), Paragraph("Exercices — petite évaluation", st["h"])]
        else:
            bloc = tete + [regle] + ([Paragraph("Méthode", st["h"]), Paragraph(_res_txt(r["methode"]), st["p"])] if r.get("methode") else []) + [
                Paragraph("Exemple", st["h"]), Paragraph(_res_txt(r["exemple"]), st["p"])]
            if r.get("vocabulaire"):
                bloc += [Paragraph("Vocabulaire", st["h"]), Paragraph(_res_txt(" — ".join(r["vocabulaire"])), st["p"])]
            bloc.append(Paragraph("Exercices", st["h"]))
        for j, e in enumerate(r["exercices"], 1):
            bloc.append(Paragraph(f"{j}. " + _res_txt(e["q"]), st["q"]))
            bloc += ([Paragraph("…" * 30, st["l"])] if eleve else [Paragraph("Réponse : " + _res_txt(e["r"]), st["r"])])
        if not eleve:
            if r.get("sources"):
                bloc.append(Paragraph(_html.escape("Sources : " + " ; ".join(r["sources"])), st["m"]))
            bloc.append(Paragraph(_html.escape(r.get("mention", "")), st["m"]))
        bloc.append(Spacer(1, 10))
        histoire.append(KeepTogether(bloc))
        if eleve and len(rs) > 1 and i % 2 == 1 and i + 1 < len(rs):
            histoire.append(PageBreak())

    def deco(c, doc):
        pdfs._entete_primaire(c, W, Hh, marge, None, None)
        c.setFont(FN, 9)
        c.setFillColor(colors.grey)
        if eleve:
            c.drawString(marge, 7 * mm, "Nom : ………………………………………   Classe : ……………   Date : ……………")
        c.drawRightString(W - marge, 7 * mm, f"Page {doc.page}")
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=marge, rightMargin=marge, topMargin=marge + 30 * mm, bottomMargin=13 * mm,
                      title=titre_lot or rs[0]["titre"], author="GESCOL").build(histoire, onFirstPage=deco, onLaterPages=deco, canvasmaker=pdfs.GCanvasPeda)
    return buf.getvalue()


def html_resumes(rs, eleve=False, titre_lot=None):
    """v2.2 — mêmes résumés que pdf_resumes, en HTML simple pour le document Word (.docx)."""
    e = lambda t: _html.escape(str(t or ""))  # noqa: E731
    br = lambda t: e(t).replace("\n", "<br>")  # noqa: E731
    out = []
    if titre_lot:
        out.append(f"<h1>{'FICHES DE RÉVISION' if eleve else 'RÉSUMÉS — L’ESSENTIEL À RETENIR'} — {e(titre_lot.upper())}</h1>"
                   f"<p>{len(rs)} résumé(s) — {'version élève (sans les réponses)' if eleve else 'version enseignant (avec corrigé)'}</p>")
    for k, r in enumerate(rs):
        saut = " style='page-break-before:always'" if k and (eleve or len(rs) > 1) and k % 2 == 0 else ""
        out.append(f"<h2{saut}>{e(r.get('titre'))}</h2>")
        info = f"{r.get('collection', '')} · {r.get('cours', '')} · {r.get('domaine', '')}" + (f" · {r['etape']}" if r.get("etape") else "")
        if r.get("seance_resume") and r.get("trimestre"):
            info += f" · trimestre {r['trimestre']} · {r.get('mois', '')}"
        out.append(f"<p><i>{e(info)}</i></p>")
        seances = r.get("ancres") if r.get("seance_resume") else []
        if seances:
            out.append("<p><i>Séance(s) : " + e(" ; ".join(a.get("libelle", "") for a in seances)) + "</i></p>")
        if r.get("lecture"):
            if r.get("manuel_note"):
                out.append(f"<p><i>{e(r['manuel_note'])}</i></p>")
            out.append(f"<table><tr><td><b>Ce que dit le texte</b><br>{br(r.get('regle'))}</td></tr></table>")
            out.append(f"<h3>Personnages et informations clés</h3><p>{br(r.get('methode'))}</p>")
            if r.get("vocabulaire"):
                out.append(f"<h3>Vocabulaire</h3><p>{e(' — '.join(r['vocabulaire']))}</p>")
            out.append(f"<h3>Le message du texte</h3><p>{br(r.get('exemple'))}</p>")
            if r.get("actualisation"):
                out.append(f"<h3>Et aujourd'hui ?</h3><p>{br(r['actualisation'])}</p>")
            out.append("<h3>Questions de compréhension</h3>")
        elif r.get("je_retiens"):
            if r.get("situation"):
                out.append(f"<h3>Situation de la vie courante</h3><p>{br(r['situation'])}</p>")
            out.append(f"<h3>{'Valeur ou règle de vie' if r.get('emc') else 'Notions essentielles'}</h3><p>{br(r.get('regle'))}</p>")
            if r.get("vocabulaire"):
                out.append("<ul>" + "".join(f"<li>{e(v)}</li>" for v in r["vocabulaire"]) + "</ul>")
            out.append(f"<table><tr><td><b>Je retiens</b><br>{br(r['je_retiens'])}</td></tr></table>")
            if r.get("engagement"):
                out.append(f"<h3>Je m'engage</h3><p>{br(r['engagement'])}</p>")
            out.append(f"<h3>Méthode</h3><p>{br(r.get('methode'))}</p><h3>Exemple</h3><p>{br(r.get('exemple'))}</p><h3>Exercices — petite évaluation</h3>")
        else:
            out.append(f"<table><tr><td><b>Je retiens</b><br>{br(r.get('regle'))}</td></tr></table>")
            if r.get("methode"):
                out.append(f"<h3>Méthode</h3><p>{br(r['methode'])}</p>")
            out.append(f"<h3>Exemple</h3><p>{br(r.get('exemple'))}</p>")
            if r.get("vocabulaire"):
                out.append(f"<h3>Vocabulaire</h3><p>{e(' — '.join(r['vocabulaire']))}</p>")
            out.append("<h3>Exercices</h3>")
        for j, x in enumerate(r.get("exercices") or [], 1):
            out.append(f"<p>{j}. {br(x.get('q'))}</p>")
            out.append("<p>" + ("…" * 30) + "</p>" if eleve else f"<p><i>Réponse : {br(x.get('r'))}</i></p>")
        if not eleve:
            if r.get("sources"):
                out.append(f"<p><i>Sources : {e(' ; '.join(r['sources']))}</i></p>")
            if r.get("mention"):
                out.append(f"<p><i>{e(r['mention'])}</i></p>")
    return "<html><body>" + "".join(out) + "</body></html>"

def pdf_revision(rv, eleve=False, partie=None, sujet=None):
    """v1.31 — Cahier de révision des disciplines d'éveil (CM1 / CM2) -> PDF A4 en Times New Roman 14 pt (Liberation Serif
    incorporée), mise en page compacte : sections de la progression (je retiens, questions-réponses, schéma, exercices) puis
    sujets type CEP (consignes, barème, corrigé). eleve=True : réponses masquées (lignes à compléter).
    partie : None (tout), "es" ou "est" ; sujet : indice d'un seul sujet (1…n)."""
    import pdfs
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    ps = pdfs.police_serif()
    FN, FB, FI = ps["normal"], ps["gras"], ps["italique"]
    W, Hh = A4
    marge = 14 * mm
    larg = W - 2 * marge
    P = lambda n, **k: ParagraphStyle(n, **{"fontName": FN, "fontSize": 14, "leading": 17, **k})  # noqa: E731
    st = {"titre": P("ti", fontName=FB, fontSize=16, leading=19, alignment=1, textColor=pdfs.BLEU),
          "s": P("s", fontSize=11, leading=13.5, textColor=colors.HexColor("#475467")),
          "h": P("h", fontName=FB, fontSize=15, leading=18, textColor=colors.white),
          "h2": P("h2", fontName=FB, spaceBefore=4, spaceAfter=1, textColor=pdfs.BLEU),
          "p": P("p"), "q": P("q", leftIndent=14, firstLineIndent=-14),
          "r": P("r", fontName=FI, textColor=colors.HexColor("#067647"), leftIndent=14),
          "l": P("l", textColor=colors.HexColor("#98A2B3"), leftIndent=14),
          "m": P("m", fontName=FI, fontSize=10, leading=12, textColor=colors.grey)}
    e = lambda t: _html.escape(str(t or ""))  # noqa: E731
    LIB = {"es": "Éducation sociale", "est": "Éducation scientifique et technologique"}

    def bandeau(t):
        b = Table([[Paragraph(e(t), st["h"])]], colWidths=[larg])
        b.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), pdfs.BLEU), ("TOPPADDING", (0, 0), (-1, -1), 3),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
        return b

    def encadre(titre, t):
        b = Table([[Paragraph(f"<b>{e(titre)}</b><br/>" + e(t), st["p"])]], colWidths=[larg])
        b.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF4FB")), ("BOX", (0, 0), (-1, -1), 0.6, pdfs.BLEU),
                               ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
        return b

    H_ = []
    if sujet is None:
        H_ += [Paragraph(e(rv["titre"]), st["titre"]), Spacer(1, 3),
               Paragraph(e(rv["intro"]) + (" — Version élève (sans les réponses)." if eleve else " — Version enseignant (avec corrigé)."), st["s"]), Spacer(1, 6)]
        for m in ("es", "est"):
            if partie and m != partie:
                continue
            secs = [x for x in rv["sections"] if x["matiere"] == m]
            if not secs:
                continue
            H_.append(Paragraph(e(LIB[m]).upper(), P("part", fontName=FB, fontSize=15, leading=18, textColor=pdfs.BLEU, spaceBefore=6)))
            for x in secs:
                bloc = [bandeau(f"SA {x['sa']} — {x['titre']}"), Spacer(1, 3), encadre("Je retiens", x["je_retiens"]),
                        Paragraph("Questions-réponses du type CEP", st["h2"])]
                for j, qr in enumerate(x["qr"], 1):
                    bloc.append(Paragraph(f"{j}. " + e(qr["q"]), st["q"]))
                    bloc.append(Paragraph("…" * 38, st["l"]) if eleve else Paragraph("→ " + e(qr["r"]), st["r"]))
                bloc += [Paragraph("Schéma à savoir reproduire", st["h2"]), Paragraph(e(x["schema"]), st["p"]), Paragraph("Exercices", st["h2"])]
                for j, ex_ in enumerate(x["exercices"], 1):
                    bloc.append(Paragraph(f"{j}. " + e(ex_["q"]), st["q"]))
                    bloc.append(Paragraph("…" * 38, st["l"]) if eleve else Paragraph("Corrigé : " + e(ex_["r"]), st["r"]))
                bloc.append(Spacer(1, 8))
                H_ += [CondPageBreak(60 * mm)] + bloc        # sections courtes regroupées sur une même page
    sujets = rv["sujets"] if sujet is None else [rv["sujets"][sujet - 1]]
    for k, sj in enumerate(sujets, 1):
        if partie and sj["matiere"] != partie:
            continue
        H_ += [PageBreak()] if (H_ or k > 1) else []
        H_ += [bandeau(sj["titre"] + f" — /{sj['total']}"), Spacer(1, 4), Paragraph("<b>Contexte.</b> " + e(sj["contexte"]), st["p"]),
               Paragraph("<b>Tâche.</b> " + e(sj["tache"]), st["p"]), Spacer(1, 4)]
        for c in sj["consignes"]:
            pts = sum(q_["pts"] for q_ in c["questions"])
            if c["titre"] == "Présentation":
                H_.append(Paragraph(f"<b>Présentation de la copie ({pts} pts)</b> : soin, lisibilité, propreté.", st["p"]))
                continue
            bloc = [Paragraph(f"{e(c['titre'])} ({pts} pts)", st["h2"])]
            for j, q_ in enumerate(c["questions"], 1):
                bloc.append(Paragraph(f"{j}. " + e(q_["q"]) + f" <i>({q_['pts']} pt{'s' if q_['pts'] > 1 else ''})</i>", st["q"]))
                bloc.append(Paragraph("…" * 38, st["l"]) if eleve else Paragraph("Corrigé : " + e(q_["r"]), st["r"]))
            H_.append(KeepTogether(bloc))
        if not eleve:
            H_.append(Paragraph("Barème : " + " ; ".join(f"{c['titre']} = {sum(q_['pts'] for q_ in c['questions'])} pts" for c in sj["consignes"])
                                + f" — total {sj['total']} points.", st["m"]))
    if not eleve:
        H_ += [Spacer(1, 6), Paragraph(e("Sources : " + " ; ".join(rv.get("sources") or [])), st["m"]), Paragraph(e(rv.get("mention", "")), st["m"])]

    def deco(c, doc):
        pdfs._entete_primaire(c, W, Hh, marge, None, None)
        c.setFont(FN, 9)
        c.setFillColor(colors.grey)
        if eleve:
            c.drawString(marge, 7 * mm, "Nom : ………………………………   Classe : …………   Date : …………")
        c.drawRightString(W - marge, 7 * mm, f"{rv['cours']} — révision d'éveil — page {doc.page}")
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=marge, rightMargin=marge, topMargin=marge + 30 * mm, bottomMargin=13 * mm,
                      title=rv["titre"], author="GESCOL").build(H_, onFirstPage=deco, onLaterPages=deco, canvasmaker=pdfs.GCanvasPeda)
    return buf.getvalue()


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config
    H.schema(SCHEMA)
    H.ajouter_colonne("prep_fiches", "partagee", "INTEGER NOT NULL DEFAULT 0")     # v1.33 : fiche partagée avec l'école
    H.schema("""CREATE TABLE IF NOT EXISTS prep_resumes_locaux (ecole_id INTEGER NOT NULL, rid TEXT NOT NULL, donnees TEXT NOT NULL,
                maj TEXT, maj_par INTEGER, PRIMARY KEY (ecole_id, rid));""")
    # v1.31.1 : téléphone / tablette ; v1.33 : toutes les installations (la première page de la préparation ne paie plus
    # le chargement du corpus) — sauf pendant les tests, où l'on mesure aussi le premier chargement
    if config.AUTONOME or not (app.config.get("TESTING") or os.environ.get("GESCOL_SANS_PRECHARGEMENT")):
        threading.Thread(target=corpus, name="corpus-pedagogique", daemon=True).start()

    @app.template_filter("prep_txt")
    def _f_txt(t):
        from markupsafe import Markup
        return Markup(txt_html(t))

    @app.context_processor
    def _ctx():
        return {"PREP_COURS_LIB": COURS_LIB, "prep_nom_matiere": nom_matiere, "PREP_REVISIONS": True}

    # ------------------------------------------------------------ outils
    def classes():
        return [c for c in H.classes_autorisees() if c["niveau"] in NIVEAU_COURS]

    def peut_ecrire(cid):
        return g.user["role"] in ("enseignant", "directeur", "admin", "fondateur") and cid in {c["id"] for c in classes()}

    def effectif(cid):
        r = q("SELECT SUM(CASE WHEN sexe='M' THEN 1 ELSE 0 END) g, SUM(CASE WHEN sexe='F' THEN 1 ELSE 0 END) f, COUNT(*) t "
              "FROM eleves WHERE classe_id=? AND statut='inscrit'", (cid,), un=True)
        return {"g": r["g"] or 0, "f": r["f"] or 0, "t": r["t"] or 0}

    def mois_courant(auj=None):
        auj = auj or date.today()
        return auj if auj.month not in (7, 8) else date(auj.year, 9, 1)

    def plan_annuel(niveau_syno, mois_lib):
        import m_synoptique as S
        r = q("SELECT contenu FROM synoptique_planification WHERE ecole_id=? AND niveau=?", (H.eco(), niveau_syno), un=True)
        lignes = json.loads(r["contenu"]) if r else S.planification_defaut(niveau_syno)
        return next((l for l in lignes if _sans_accent(l.get("mois", "")) == _sans_accent(mois_lib)), None)

    def plan_semaine(cl, auj):
        """Cases de la planification mensuelle de la classe pour la semaine en cours : {matière: texte}, (du, au)."""
        try:
            liste = H.planification_mensuelle(H.eco(), config.ANNEE_ACTIVE, cl["id"])
        except Exception:  # noqa: BLE001
            return {}, None
        mois = f"{auj.year}-{auj.month:02d}"
        pm = next((p for p in liste if p.get("mois") == mois), None)
        if not pm:
            return {}, None
        iso = auj.isoformat()
        k = next((i for i, s in enumerate(pm["semaines"]) if s.get("du") and s.get("au") and s["du"] <= iso <= s["au"]), None)
        if k is None:
            return {}, None
        out = {}
        for code, cases in (pm.get("contenu") or {}).items():
            m = "francais" if code.startswith("fr_") else COL_MATIERE.get(code) or ("ea" if code.startswith("ea_") else
                                                                                   "es" if code.startswith("es_") else None)
            v = (cases[k] if k < len(cases) else "").strip()
            if m and v and re.search(r"\d", v):      # une case citant une SA / unité / dossier (pas un gabarit vide)
                out[m] = (out.get(m, "") + " ; " + v).strip(" ;")
        return out, (pm["semaines"][k]["du"], pm["semaines"][k]["au"])

    def cette_semaine(cl, auj=None):
        auj = auj or date.today()
        cours = NIVEAU_COURS.get(cl["niveau"])
        if cours == "MAT" and getattr(H, "mat_semaine", None):      # v2.1 : progression de la maternelle par défaut
            s = H.mat_semaine(cl, auj)
            if s is not None:
                return s
        niv = NIVEAU_SYNO.get(cl["niveau"])
        mc = mois_courant(auj)
        ligne = plan_annuel(niv, MOIS_FR[mc.month - 1]) if niv else None
        semaine, bornes = plan_semaine(cl, auj)
        mats = []
        for m in ORDRE_MAT:
            ann = "; ".join(str(ligne.get(k) or "") for k, mm in COL_MATIERE.items() if mm == m and (ligne or {}).get(k)) if ligne else ""
            sem = semaine.get(m, "")
            if not (ann or sem):
                continue
            refs = references(sem or ann)
            if not sem:
                refs_mois = refs
                refs = refs_de_la_semaine(refs, m, auj)
            toutes = correspondances(cours, m, refs)
            if not sem and not toutes and refs is not refs_mois:
                # v2.4.8 : la SA / l'unité de la semaine n'a aucune fiche dans la bibliothèque (ex. éducation artistique du CM1 : SA7 et SA8)
                # -> on propose celle du mois qui en a, la plus proche de la semaine, au lieu d'une semaine vide
                cle = "u" if m == "francais" and refs_mois["u"] else "sa"
                voulu = refs[cle][0] if refs.get(cle) else None
                ordre = refs_mois.get(cle) or []
                dispo = [x for x in ordre if correspondances(cours, m, dict(refs_mois, **{cle: [x]}))]
                if dispo and voulu in ordre:
                    x = min(dispo, key=lambda v: abs(ordre.index(v) - ordre.index(voulu)))
                    refs = dict(refs_mois, **{cle: [x]})
                    toutes = correspondances(cours, m, refs)
            mats.append({"matiere": m, "nom": nom_matiere(m), "annuel": ann, "semaine": sem, "refs": refs,
                         "fiches": toutes[:PAR_MATIERE], "total": len(toutes), "ids": [f["id"] for f in toutes]})
        return {"classe": cl, "cours": cours, "mois": MOIS_FR[mc.month - 1], "bornes": bornes, "matieres": mats}

    def fiche_corpus(fid):
        f = corpus()["fiche_par_id"].get(fid)
        if not f:
            abort(404)
        return f

    def ma_fiche(mid, ecrire=False):
        r = q("SELECT * FROM prep_fiches WHERE id=? AND ecole_id=?", (mid, H.eco()), un=True)
        if not r:
            abort(404)
        if g.user["role"] == "enseignant" and r["user_id"] != g.user["id"] and not (r["partagee"] if "partagee" in r.keys() else 0):
            abort(403)
        if ecrire and r["user_id"] != g.user["id"]:
            abort(403)
        d = json.loads(r["donnees"])
        d.update({"id": r["id"], "classe_id": r["classe_id"], "date_seance": r["date_seance"], "cours": r["cours"],
                  "matiere": r["matiere"], "sa": r["sa"], "seance": r["seance"], "titre": r["titre"], "source_id": r["source_id"],
                  "user_id": r["user_id"], "maj_le": r["maj_le"], "partagee": r["partagee"] if "partagee" in r.keys() else 0})
        return d

    def noter_fiche(mid, titre, donnees, note):
        if hasattr(H, "partage_noter"):
            H.partage_noter("fiche", str(mid), titre, donnees, note)

    def restaurer_fiche(cle, d):
        mid = int(cle)
        r = q("SELECT * FROM prep_fiches WHERE id=? AND ecole_id=?", (mid, H.eco()), un=True)
        if not r:
            abort(404)
        if r["user_id"] != g.user["id"] and g.user["role"] not in ("directeur", "admin", "fondateur"):
            abort(403)
        titre = d.pop("_titre", None) or r["titre"]
        ex("UPDATE prep_fiches SET titre=?, donnees=?, maj_le=? WHERE id=?",
           (titre[:300], json.dumps({k: d.get(k, "") for k in CLES_TEXTE + ["deroulement"]}, ensure_ascii=False), H.maintenant(), mid))

    if hasattr(H, "partage_type"):
        H.partage_type("fiche", "Fiche de préparation", lambda cle: url_for("prep_ma_fiche", mid=int(cle)), restaurer_fiche)

    def lire_formulaire(f):
        d = {k: (f.get(k) or "").strip()[:4000] for k in CLES_TEXTE}
        d["matiere"] = f.get("matiere") if f.get("matiere") in corpus()["matieres"] else "francais"
        for k in ("sa", "seance"):
            v = (f.get(k) or "").strip()
            d[k] = int(v) if v.isdigit() and int(v) < 1000 else None
        lignes = []
        for i in range(MAX_LIGNES):
            ph, ac, re_ = (f.get(f"ph_{i}") or "").strip()[:500], (f.get(f"ac_{i}") or "").strip()[:6000], (f.get(f"re_{i}") or "").strip()[:2000]
            if ph or ac or re_:
                lignes.append([ph, ac, re_])
        d["deroulement"] = lignes
        ds = (f.get("date_seance") or "").strip()
        try:
            d["date_seance"] = datetime.strptime(ds, "%Y-%m-%d").date().isoformat() if ds else None
        except ValueError:
            d["date_seance"] = None
        try:
            d["classe_id"] = int(f.get("classe") or 0) or None
        except ValueError:
            d["classe_id"] = None
        return d

    def fiche_vierge(cl=None, matiere="francais"):
        return {"matiere": matiere, "cours": NIVEAU_COURS.get(cl["niveau"]) if cl else "", "titre": "", "duree": "45 min",
                "strategies": "Travail individuel — travail en groupe — travail collectif",
                "deroulement": [["**INTRODUCTION**\n\nMise en situation", "• Rappel / prérequis.\n• Situation de départ.\n• Proposition : aujourd'hui, tu vas apprendre …", "Réponses variables."],
                                ["**RÉALISATION**", "• Tâche / consignes.\n• Travail individuel, en groupe, mise en commun.\n• Synthèse.", ""],
                                ["**RETOUR ET PROJECTION**", "• Objectivation : dis ce que tu as appris et comment.\n• Évaluation.\n• Projection.", ""]]}

    def depuis_modele(m, cl):
        d = fiche_vierge(cl, m.get("matiere") or "francais")
        d.update({"titre": m.get("libelle", ""), "cd": m.get("cd", ""), "contenus": m.get("contenus", ""),
                  "strategies": m.get("strategies") or d["strategies"], "materiel": m.get("materiel", ""),
                  "deroulement": [["**INTRODUCTION**", m.get("introduction", ""), ""], ["**RÉALISATION**", m.get("realisation", ""), ""],
                                  ["**RETOUR ET PROJECTION**", m.get("retour", ""), ""]]})
        return d

    def entete_classe(d):
        cl = q("SELECT * FROM classes WHERE id=?", (d.get("classe_id"),), un=True) if d.get("classe_id") else None
        return cl, (effectif(cl["id"]) if cl else None)

    # ------------------------------------------------------------ PDF et Word
    def titulaire_de(d, cl):
        """Nom imprimé en filigrane sur la fiche : titulaire de la classe, sinon auteur de la fiche, sinon enseignant connecté."""
        if cl is not None and "titulaire_nom" in cl.keys() and cl["titulaire_nom"]:
            return cl["titulaire_nom"]
        if d.get("user_id"):
            u = q("SELECT nom FROM utilisateurs WHERE id=?", (d["user_id"],), un=True)
            if u and u["nom"]:
                return u["nom"]
        if g.get("user") is not None and g.user["role"] == "enseignant":
            return g.user["nom"]
        if cl is not None:
            t = q("SELECT u.nom FROM affectations a JOIN utilisateurs u ON u.id=a.user_id WHERE a.classe_id=? AND u.role='enseignant' "
                  "ORDER BY a.matiere_id IS NOT NULL, a.id LIMIT 1", (cl["id"],), un=True)
            if t:
                return t["nom"]
        # v2.2 : jamais sans filigrane — la classe, sinon la personne connectée, sinon le cours
        if cl is not None and cl["nom"]:
            return f"Classe {cl['nom']}"
        if g.get("user") is not None and g.user["nom"] and g.user["role"] not in ("admin", "fondateur"):
            return g.user["nom"]
        return COURS_LIB.get(d.get("cours"), d.get("cours") or "") or ""

    def pdf_une_fiche(d, titre_doc, s_dir):
        """v1.32 — Une fiche : Times New Roman 14 pt (tableaux 13 pt), bandeau de la couleur de la matière avec son dessin,
        rubriques illustrées, filigrane oblique du titulaire, marges alternées pour l'impression recto verso, « Page x / y »,
        mention du concepteur en bas de page. Renvoie (octets du PDF, nombre de pages)."""
        import pdfs
        import dessins_pdf as DS
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                        Table, TableStyle)
        W, Hh = A4
        SER = pdfs.police_serif()
        coul_hex = DS.couleur_matiere(d.get("matiere"))
        coul = colors.HexColor(coul_hex)
        clair = colors.Color(coul.red, coul.green, coul.blue, alpha=0.10)
        cl, eff = entete_classe(d)
        filigrane = titulaire_de(d, cl)
        mat = nom_matiere(d.get("matiere"))
        bande = " · ".join(x for x in [COURS_LIB.get(d.get("cours"), d.get("cours") or ""), mat, d.get("sous_matiere") or "",
                                        f"SA {d['sa']}" if d.get("sa") else "", f"séance {d['seance']}" if d.get("seance") else "",
                                        d.get("duree") or ""] if x)
        lignes = d.get("deroulement") or []
        u = q("SELECT * FROM utilisateurs WHERE id=?", (d.get("user_id"),), un=True) if d.get("user_id") else None
        s_ens = pdfs.image_data_url(H.signature_enseignant(u["id"]) if u else (H.signature_titulaire(cl["id"]) if cl else None))
        sigs = [("L'enseignant(e)", (u["nom"] if u else filigrane), s_ens, False), ("Visa du directeur / de la directrice", "", s_dir, True)]
        code = pdfs.code_tableau(titre_doc, d.get("titre"), [("Classe", cl["nom"] if cl else d.get("cours")), ("Matière", mat)],
                                 lignes, None, ("fiche_preparation", f"Fiche de préparation – {d.get('titre', '')[:120]} – {cl['nom'] if cl else d.get('cours', '')}"))
        utile = W - 25 * mm

        def resserrer(t):
            """Lignes courtes successives réunies sur une ligne (« 16 ; 23 ; 2 × 6 + 4 ») et retours à la ligne au milieu d'une
            phrase (coupures de l'extraction PDF) supprimés : même contenu, moins de hauteur."""
            t = re.sub(r"(?<![.:;!?»\n])\n(?=[a-zàâçéèêëîïôûùüÿœ(«0-9])", " ", str(t or ""))
            t = re.sub(r"\n{2,}", "\n", t)
            out, tampon = [], []
            for l in t.split("\n"):
                ls = l.strip()
                if ls and len(ls) <= 28 and not ls.startswith(("**", "\u25aa", "-", "\u2022")):
                    tampon.append(ls.rstrip(";"))
                    continue
                if tampon:
                    out.append(" ; ".join(tampon))
                    tampon = []
                if ls:
                    out.append(l)
            if tampon:
                out.append(" ; ".join(tampon))
            return "\n".join(out)

        def histoire(B, rupture, compact, dense=False, colonnes=False, fusion=False):
            """B : taille du corps (14 pt, réduite jusqu'à 12 pt seulement s'il le faut pour tenir sur deux pages) ;
            rupture : le déroulement commence la page 2 ; compact : espacements et tableau resserrés."""
            T = B - 1                                  # tableaux : un point de moins que le texte
            esp = 0.6 if compact else 1.0
            st = ParagraphStyle("c", fontName=SER["normal"], fontSize=T, leading=T * 1.23)
            stb = ParagraphStyle("b", parent=st, fontName=SER["gras"])
            sth = ParagraphStyle("h", parent=stb, textColor=colors.white, alignment=1)
            stc = ParagraphStyle("corps", fontName=SER["normal"], fontSize=B, leading=B * (1.22 if compact else 1.29))
            stt = ParagraphStyle("rub", fontName=SER["gras"], fontSize=B, leading=B * 1.25, textColor=coul)
            sti = ParagraphStyle("ti", fontName=SER["gras"], fontSize=B + 2, leading=(B + 2) * 1.25, alignment=1, textColor=coul)
            sts = ParagraphStyle("st", fontName=SER["normal"], fontSize=T, leading=T * 1.23, alignment=1, spaceAfter=4 * esp)
            stm = ParagraphStyle("m", parent=st, fontName=SER["italique"], fontSize=min(11, T), leading=min(11, T) * 1.27, textColor=colors.HexColor("#B54708"))

            def rubrique(k, lib):
                nom = DS.RUBRIQUES.get(k, "document")
                t = Table([[DS.flowable(nom, B - 1, coul_hex), Paragraph(lib.upper(), stt)]], colWidths=[18, None])
                t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                                       ("LINEBELOW", (1, 0), (1, 0), 0.8, coul)]))
                return t

            h = [Paragraph(titre_doc, sti), Paragraph(txt_pdf(bande), sts), NextPageTemplate("suite")]
            infos = [("École", config.ECOLE.get("nom", "")), ("Classe", cl["nom"] if cl else (d.get("cours") or "")),
                     ("Date", datetime.strptime(d["date_seance"], "%Y-%m-%d").strftime("%d/%m/%Y") if d.get("date_seance") else "…… / …… / ……"),
                     ("Effectif", f"G : {eff['g']}   F : {eff['f']}   T : {eff['t']}" if eff else "G : ……  F : ……  T : ……"),
                     ("Unité / SA", " · ".join(x for x in [d.get("unite") or "", f"SA n°{d['sa']}" if d.get("sa") else "",
                                                           f"Séance n°{d['seance']}" if d.get("seance") else ""] if x) or "—"),
                     ("Durée", d.get("duree") or "—")]
            grille = []
            for i in range(0, len(infos), 2):
                ligne = []
                for lab, val in infos[i:i + 2]:
                    ligne += [Paragraph(f"<b>{lab}</b>", st), Paragraph(txt_pdf(val), st)]
                grille.append(ligne + [""] * (4 - len(ligne)))
            lw = 26 * mm
            ti = Table(grille, colWidths=[lw, utile / 2 - lw] * 2)
            ti.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, coul), ("BACKGROUND", (0, 0), (-1, -1), clair),
                                    ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
            h += [ti, Spacer(1, 6 * esp)]
            h.append(Paragraph(f"<b>Titre :</b> {txt_pdf(d.get('titre'))}" + (f" — <i>{txt_pdf(d.get('intitule'))}</i>" if d.get("intitule") and d.get("intitule") != d.get("titre") else ""), stc))
            h.append(Spacer(1, 5 * esp))
            for k, lib in CHAMPS:
                if k in ("cd", "ct", "contenus", "objectifs", "strategies", "materiel") and d.get(k):
                    texte = resserrer(d[k]) if dense else d[k]
                    corps_ = st if dense and len(str(d[k])) > 600 else stc
                    h.append(KeepTogether([rubrique(k, lib), Spacer(1, 2), Paragraph(txt_pdf(texte), corps_)]))
                    h.append(Spacer(1, 6 * esp))
            data = [[Paragraph("Phases / étapes", sth), Paragraph("Activités de l'enseignant(e) et des apprenant(e)s", sth),
                     Paragraph("Résultats attendus / évaluation", sth)]]
            # v2.2 : première colonne plus large, sans couper les mots (« PRÉLIMINAIRES » restait coupé en deux)
            stp = ParagraphStyle("phase", parent=stb, fontSize=min(10 if dense else 12, T), leading=min(10 if dense else 12, T) * 1.2,
                                 splitLongWords=0)
            R_ = resserrer if dense else (lambda x: x)
            data += [[Paragraph(txt_pdf(a_), stp), Paragraph(txt_pdf(R_(b_)), st), Paragraph(txt_pdf(R_(c_)), st)] for a_, b_, c_ in [(l + ["", "", ""])[:3] for l in lignes]]
            l1, l3 = (32 * mm, 38 * mm) if dense else (43 * mm, 44 * mm)
            if fusion:
                # v2.2.2 — déroulement resserré : colonne des phases étroite, résultats attendus sous les activités
                stp2 = ParagraphStyle("phf", parent=stp, fontSize=min(9, T), leading=min(9, T) * 1.15)
                stre2 = ParagraphStyle("ref", parent=st, fontName=SER["italique"])
                data = [[Paragraph("Phases", sth), Paragraph("Activités de l'enseignant(e) et des apprenant(e)s — <i>résultats attendus</i>", sth)]]
                for a_, b_, c_ in [(l + ["", "", ""])[:3] for l in lignes]:
                    cel = [Paragraph(txt_pdf(resserrer(b_)), st)]
                    if (c_ or "").strip():
                        cel.append(Paragraph("<i>Résultats attendus :</i> " + txt_pdf(resserrer(c_).replace("\n", " ")), stre2))
                    data.append([Paragraph(txt_pdf(a_), stp2), cel])
                from reportlab.pdfbase.pdfmetrics import stringWidth
                mots = [m_ for a_ in lignes for m_ in re.sub(r"<[^>]+>|\*\*", " ", str((a_ or [""])[0])).split()]
                l1 = max(24 * mm, min(36 * mm, max([stringWidth(m_, SER["gras"], stp2.fontSize) for m_ in mots] or [0]) + 8))
                td = Table(data, colWidths=[l1, utile - l1], repeatRows=1, splitByRow=1, splitInRow=1)
            else:
                td = Table(data, colWidths=[l1, utile - l1 - l3, l3], repeatRows=1, splitByRow=1, splitInRow=1)
            pad = 1.5 if compact else 3
            td.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#667085")), ("BACKGROUND", (0, 0), (-1, 0), coul),
                                    ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, clair]),
                                    ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad)]))
            if colonnes:
                # dernier recours (fiches très longues) : déroulement sur deux colonnes en page 2, sans tableau
                h += [NextPageTemplate("deux"), PageBreak(), rubrique("deroulement", "Déroulement"), Spacer(1, 2)]
                stph = ParagraphStyle("ph2", parent=stb, fontSize=B, leading=B * 1.2, textColor=coul, spaceBefore=3)
                stre = ParagraphStyle("re2", parent=st, fontName=SER["italique"])
                for a_, b_, c_ in [(l + ["", "", ""])[:3] for l in lignes]:
                    if a_:
                        h.append(Paragraph(txt_pdf(a_), stph))
                    if b_:
                        h.append(Paragraph(txt_pdf(resserrer(b_)), st))
                    if c_:
                        h.append(Paragraph("<i>Résultats attendus :</i> " + txt_pdf(resserrer(c_)), stre))
                h.append(Spacer(1, 4))
            else:
                if rupture:
                    h.append(PageBreak())
                h += [rubrique("deroulement", "Déroulement"), Spacer(1, 3 * esp), td, Spacer(1, 6 * esp)]
            for k in ("evaluation", "projection", "je_retiens", "observations"):
                if d.get(k):
                    h.append(KeepTogether([rubrique(k, dict(CHAMPS)[k]), Spacer(1, 2), Paragraph(txt_pdf(d[k]), stc)]))
                    h.append(Spacer(1, 5 * esp))
            if d.get("mention"):
                h.append(Paragraph(txt_pdf(d["mention"]), stm))
            if d.get("source"):
                h.append(Paragraph(f"Source : {txt_pdf(d['source'])}", ParagraphStyle("so", parent=st, fontSize=9, leading=11, textColor=colors.grey)))
            h += [Spacer(1, 4 * esp), KeepTogether([pdfs._BlocSignatures(sigs, utile, code=code)])]
            return h

        def bandeau(c, doc):
            """Bandeau de la matière (chaque page), filigrane du titulaire, pied de page."""
            c.saveState()
            gauche = doc.leftMargin
            y = Hh - (10 * mm if doc.page > 1 else 8 * mm)
            if doc.page > 1:
                c.setFillColor(coul)
                c.roundRect(gauche, y - 9 * mm, W - doc.leftMargin - doc.rightMargin, 9 * mm, 2 * mm, stroke=0, fill=1)
                DS.dessiner(c, DS.dessin_matiere(d.get("matiere")), gauche + 2.5 * mm, y - 7.6 * mm, 6.2 * mm, "#FFFFFF", 2)
                c.setFillColor(colors.white)
                c.setFont(SER["gras"], 12)
                c.drawString(gauche + 11 * mm, y - 5.6 * mm, f"Fiche de préparation — {mat}")
                c.setFont(SER["normal"], 10)
                gauche_t = f"Fiche de préparation — {mat}"
                place = W - doc.leftMargin - doc.rightMargin - 17 * mm - c.stringWidth(gauche_t, SER["gras"], 12)
                tt = d.get("titre") or ""
                while tt and c.stringWidth(tt, SER["normal"], 10) > place:
                    tt = tt[:-2].rstrip() + "…" if len(tt) > 2 else ""
                    tt = tt.replace("……", "…")
                c.drawRightString(W - doc.rightMargin - 3 * mm, y - 5.6 * mm, tt)
            else:
                pdfs._entete_primaire(c, W, Hh, doc.leftMargin, None, "maternelle" if d.get("cours") == "MAT" else None)
                c.setFillColor(coul)
                c.rect(gauche, Hh - 43 * mm, W - doc.leftMargin - doc.rightMargin, 1.6 * mm, stroke=0, fill=1)
                DS.dessiner(c, DS.dessin_matiere(d.get("matiere")), W / 2 - 6 * mm, Hh - 40 * mm, 12 * mm, coul_hex, 1.8)
            if filigrane:
                c.saveState()
                c.setFillColor(colors.Color(coul.red, coul.green, coul.blue, alpha=0.11))
                c.translate(W / 2, Hh / 2)
                c.rotate(35)
                taille = 54
                while taille > 24 and c.stringWidth(filigrane, SER["gras"], taille) > Hh * 0.8:
                    taille -= 2
                c.setFont(SER["gras"], taille)
                c.drawCentredString(0, 0, filigrane)
                c.restoreState()
            c.setFillColor(colors.HexColor("#667085"))
            c.setFont(SER["normal"], 9)
            c.drawString(doc.leftMargin, 8 * mm, f"{config.ECOLE.get('nom', '')} · {config.ANNEE_ACTIVE}")
            c.drawRightString(W - doc.rightMargin, 8 * mm, f"imprimé le {date.today().strftime('%d/%m/%Y')}")
            c.restoreState()

        class Doc(BaseDocTemplate):
            def afterPage(self):                      # recto verso : marges alternées (reliure à gauche du recto)
                self.handle_nextPageTemplate("suite_g" if (self.page + 1) % 2 == 0 else "suite")

        def cadre(g_, d_, haut):
            return Frame(g_, 16 * mm, W - g_ - d_, Hh - haut - 16 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

        def construire(B, rupture, compact, dense=False, colonnes=False, fusion=False):
            buf = io.BytesIO()
            doc = Doc(buf, pagesize=A4, title=titre_doc, author="GESCOL", leftMargin=15 * mm, rightMargin=10 * mm)
            doc.addPageTemplates([
                PageTemplate("premiere", [cadre(15 * mm, 10 * mm, 50 * mm)], onPageEnd=bandeau),
                PageTemplate("suite", [cadre(15 * mm, 10 * mm, 22 * mm)], onPageEnd=bandeau),
                PageTemplate("suite_g", [cadre(10 * mm, 15 * mm, 22 * mm)], onPageEnd=bandeau),
                PageTemplate("deux", [Frame(12 * mm, 16 * mm, (W - 30 * mm) / 2, Hh - 38 * mm, id="g", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
                                      Frame(18 * mm + (W - 30 * mm) / 2, 16 * mm, (W - 30 * mm) / 2, Hh - 38 * mm, id="d", leftPadding=0, rightPadding=0,
                                            topPadding=0, bottomPadding=0)], onPageEnd=bandeau)])
            doc.build(histoire(B, rupture, compact, dense, colonnes, fusion), canvasmaker=pdfs.GCanvasPedaNum)
            return buf.getvalue(), doc.page

        # v2.2 — une fiche = une feuille recto verso : page 1 en-tête et éléments de planification, page 2 déroulement et
        # évaluation ; 14 pt, réduit pas à pas jusqu'à 12 pt seulement s'il le faut ; une fiche courte garde une seule page.
        # v2.2.2 — cascade : 1 page à 14 pt ; planification p. 1 / déroulement p. 2 de 14 à 12 pt (normal puis resserré) ;
        # déroulement dès la page 1 de 12 à 10 pt ; lignes courtes réunies ; déroulement resserré (phases étroites, résultats
        # sous les activités) jusqu'à 9 pt ; déroulement sur deux colonnes en dernier recours.
        # (taille, rupture, compact, pages maxi, dense, colonnes, fusion)
        essais = [(14, False, False, 1, False, False, False)] + \
                 [(t, True, False, 2, False, False, False) for t in (14, 13.5, 13, 12.5, 12)] + \
                 [(t, True, True, 2, False, False, False) for t in (13, 12.5, 12)] + \
                 [(t, False, True, 2, False, False, False) for t in (12, 11.5, 11, 10.5, 10)] + \
                 [(t, False, True, 2, True, False, False) for t in (11, 10.5, 10)] + \
                 [(t, r_, True, 2, True, False, True) for t in (11, 10.5, 10, 9.5, 9) for r_ in (True, False)] + \
                 [(t, True, True, 2, True, True, False) for t in (10, 9.5, 9)] + \
                 [(t, False, True, 2, True, False, True) for t in (8.5, 8)]
        dernier = None
        for B, rupture, compact, maxi, dense, col, fus in essais:
            out, n = construire(B, rupture, compact, dense, col, fus)
            if os.environ.get("FICHE_DEBUG"):
                print("ESSAI", B, rupture, compact, dense, col, fus, n)
            if n <= maxi:
                return out, n
            if dernier is None or n < dernier[1]:
                dernier = (out, n)
        FICHES_DEBORDANTES.add(d.get("source_id") or d.get("id") or d.get("titre"))
        return dernier or (out, n)

    def pdf_fiches(fiches, titre_doc="FICHE DE PRÉPARATION"):
        """Une ou plusieurs fiches ; chaque fiche commence sur un recto (page blanche ajoutée après une fiche d'un nombre
        impair de pages quand plusieurs fiches sont réunies) ; document vérifiable (QR)."""
        import pdfs
        import pypdf
        eid = H.eco()
        s_dir = pdfs.image_data_url(H.signature(f"ecole:{eid}:directeur")) or pdfs.signature_directeur()
        if len(fiches) == 1:
            return pdf_une_fiche(fiches[0], titre_doc, s_dir)[0]
        w = pypdf.PdfWriter()
        for n, d in enumerate(fiches):
            octets, nb = pdf_une_fiche(d, titre_doc, s_dir)
            for pg in pypdf.PdfReader(io.BytesIO(octets)).pages:
                w.add_page(pg)
            if nb % 2 and n < len(fiches) - 1:
                w.add_blank_page()
        sortie = io.BytesIO()
        w.add_metadata({"/Title": titre_doc, "/Author": "GESCOL"})
        if hasattr(w, "compress_identical_objects"):   # v2.2 : images (armoiries, logo, dessins) communes une seule fois
            try:
                w.compress_identical_objects(remove_identicals=True, remove_orphans=True)
            except Exception:  # noqa: BLE001
                pass
        w.write(sortie)
        return sortie.getvalue()

    def doc_word(fiches, titre_doc="FICHE DE PRÉPARATION"):
        parts = []
        for d in fiches:
            cl, eff = entete_classe(d)
            lignes = "".join(f"<tr><td><b>{txt_html(a)}</b></td><td>{txt_html(b)}</td><td>{txt_html(c)}</td></tr>"
                             for a, b, c in [(l + ['', '', ''])[:3] for l in d.get("deroulement") or []])
            blocs = "".join(f"<tr><th>{lib}</th><td>{txt_html(d.get(k))}</td></tr>" for k, lib in CHAMPS
                            if k in ("cd", "ct", "contenus", "objectifs", "strategies", "materiel") and d.get(k))
            fin = "".join(f"<p><b>{dict(CHAMPS)[k]} :</b><br>{txt_html(d[k])}</p>" for k in ("evaluation", "projection", "je_retiens", "observations") if d.get(k))
            parts.append(f"""<h1>{titre_doc}</h1><p class=c>{_html.escape(nom_matiere(d.get('matiere')))} — {_html.escape(COURS_LIB.get(d.get('cours'), d.get('cours') or ''))}
<br>{_html.escape(config.ECOLE.get('nom', ''))} · Classe : {_html.escape(cl['nom'] if cl else '')} · Date : {_html.escape(d.get('date_seance') or '……')}
· Effectif : {('G ' + str(eff['g']) + ' / F ' + str(eff['f']) + ' / T ' + str(eff['t'])) if eff else '……'}</p>
<p><b>Titre :</b> {txt_html(d.get('titre'))} · {txt_html(d.get('unite'))} {('SA n°' + str(d['sa'])) if d.get('sa') else ''} {('Séance n°' + str(d['seance'])) if d.get('seance') else ''} · Durée : {txt_html(d.get('duree'))}</p>
<table>{blocs}</table><h2{" style='page-break-before:always'" if len(d.get('deroulement') or []) >= 3 else ""}>Déroulement</h2><table><tr><th>Phases / étapes</th><th>Activités de l'enseignant(e) et des apprenant(e)s</th><th>Résultats attendus / évaluation</th></tr>{lignes}</table>
{fin}{('<p><i>' + txt_html(d['mention']) + '</i></p>') if d.get('mention') else ''}""")
        corps = "<br style='page-break-before:always'>".join(parts)
        h = ("<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word'><head><meta charset='utf-8'>"
             f"<title>{titre_doc}</title><style>body{{font-family:Calibri,Arial;font-size:11pt}}table{{border-collapse:collapse;width:100%}}"
             "td,th{border:1px solid #666;padding:4px;vertical-align:top}th{background:#E4ECF5;text-align:left}h1{text-align:center;color:#1F4E79;font-size:16pt}"
             f".c{{text-align:center}}</style></head><body>{corps}</body></html>")
        return h

    def reponse_doc(contenu, nom):
        """v2.2 : vrai document Word (.docx, Times New Roman 14 pt), lisible par Word, WPS et LibreOffice, sur ordinateur
        comme sur téléphone (avant : page HTML nommée « .doc »)."""
        return H.reponse_docx(contenu, nom, "Fiche de préparation")

    def nom_fichier(d, ext):
        base = re.sub(r"[^A-Za-z0-9]+", "_", _sans_accent(f"fiche_{d.get('cours', '')}_{d.get('matiere', '')}_{d.get('titre', '')}"))[:80].strip("_")
        return f"{base or 'fiche'}.{ext}"

    # ------------------------------------------------------------ pages
    @app.route("/preparation")
    @H.connexion_requise("preparation")
    def prep_accueil():
        semaines = [cette_semaine(c) for c in classes()]
        nb = q("SELECT COUNT(*) n FROM prep_fiches WHERE ecole_id=? AND user_id=?", (H.eco(), g.user["id"]), un=True)["n"]
        C = corpus()
        return render_template("prep_accueil.html", semaines=semaines, nb_mes=nb, nb_fiches=len(C["fiches"]),
                               nb_guides=len(C["guides"]), nb_prog=len(C["programmes"]), aujourd=date.today())

    @app.route("/preparation/programmes")
    @H.connexion_requise("preparation")
    def prep_programmes():
        C = corpus()
        cours = request.args.get("cours") or ""
        mat = request.args.get("matiere") or ""
        progs = [p for p in C["programmes"] if (not cours or p["cours"] == cours) and (not mat or p["matiere"] == mat)]
        progs.sort(key=lambda p: (COURS.index(p["cours"]) if p["cours"] in COURS else 9, ORDRE_MAT.index(p["matiere"]) if p["matiere"] in ORDRE_MAT else 9,
                                  p.get("dossier") or 0, p.get("num") or 0))
        dispo = sorted({(p["cours"], p["matiere"]) for p in C["programmes"]},
                       key=lambda x: (COURS.index(x[0]) if x[0] in COURS else 9, ORDRE_MAT.index(x[1]) if x[1] in ORDRE_MAT else 9))
        # planification annuelle officielle du cours (toutes matières) en complément
        import m_synoptique as S
        niv = {v: k for k, v in NIVEAU_COURS.items() if v != "MAT"}.get(cours)
        plan = None
        if niv:
            r = q("SELECT contenu FROM synoptique_planification WHERE ecole_id=? AND niveau=?", (H.eco(), NIVEAU_SYNO[niv]), un=True)
            plan = json.loads(r["contenu"]) if r else S.planification_defaut(NIVEAU_SYNO[niv])
        return render_template("prep_programmes.html", progs=progs, cours=cours, mat=mat, dispo=dispo, COURS=COURS,
                               MATS=[m for m in ORDRE_MAT], plan=plan, cols=S.COLS_PLAN, vigueur=C.get("programme_en_vigueur"))

    @app.route("/preparation/programmes/<pid>")
    @H.connexion_requise("preparation")
    def prep_programme(pid):
        p = corpus()["prog_par_id"].get(pid)
        if not p:
            abort(404)
        nums = [p.get("num")] if p.get("num") else []
        fiches = [f for f in fiches_filtrees(cours=p["cours"], matiere=p["matiere"])
                  if (p.get("type") == "unite" and num_unite(f) == p.get("num")) or (p.get("type") == "sa" and f.get("sa") in nums)]
        return render_template("prep_programme.html", p=p, fiches=fiches[:60])

    @app.route("/preparation/guides")
    @H.connexion_requise("preparation")
    def prep_guides():
        C = corpus()
        mat = request.args.get("matiere") or ""
        cours = request.args.get("cours") or ""
        gs = [x for x in C["guides"] if (not mat or x["matiere"] == mat) and (not cours or cours in (x.get("cours") or []))]
        groupes = {}
        for x in sorted(gs, key=lambda x: (ORDRE_MAT.index(x["matiere"]) if x["matiere"] in ORDRE_MAT else 9, x.get("groupe", ""), x["titre"])):
            groupes.setdefault(nom_matiere(x["matiere"]), []).append(x)
        return render_template("prep_guides.html", groupes=groupes, mat=mat, cours=cours, MATS=ORDRE_MAT, COURS=COURS)

    # ------------------------------------------------------------ v1.32 : barèmes EPS proposés (CI → CM2)
    @app.route("/preparation/baremes-eps")
    @app.route("/preparation/baremes-eps.pdf", endpoint="prep_baremes_eps_pdf")
    @H.connexion_requise("preparation")
    def prep_baremes_eps():
        import banque_ea_eps as BEE
        cours = request.args.get("cours") or ""
        liste = [c for c in COURS if c in BEE.COURSE and (not cours or c == cours)]
        refs = [(c, BEE.AGE[c], BEE.referentiel(c)) for c in liste]
        if not request.path.endswith(".pdf"):
            return render_template("prep_baremes_eps.html", refs=refs, cours=cours, COURS=[c for c in COURS if c in BEE.COURSE],
                                   mention=BEE.MENTION_BAREME, adaptations=BEE.ADAPTATIONS)
        import pdfs
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        S = pdfs.police_serif()
        rose = colors.HexColor("#C11574")
        st = ParagraphStyle("p", fontName=S["normal"], fontSize=14, leading=18, spaceAfter=3)
        sc = ParagraphStyle("c", fontName=S["normal"], fontSize=12, leading=14)
        sh = ParagraphStyle("h", fontName=S["gras"], fontSize=16, leading=20, textColor=rose, spaceBefore=6, spaceAfter=4)
        sm = ParagraphStyle("m", fontName=S["italique"], fontSize=12, leading=15, textColor=colors.HexColor("#B54708"))
        W = A4[0] - 30 * mm
        h = [Paragraph("BARÈMES D'ÉDUCATION PHYSIQUE ET SPORTIVE", ParagraphStyle("t", parent=sh, fontSize=18, alignment=1)),
             Paragraph(_html.escape(BEE.MENTION_BAREME), sm), Spacer(1, 6)]
        for n, (c, age, ref) in enumerate(refs):
            if n:
                h.append(PageBreak())
            h.append(Paragraph(f"{COURS_LIB.get(c, c)} — âge normal : {age} ans", sh))
            for epreuve, consigne, bm in ref:
                if bm.get("observation"):
                    data = [[Paragraph("<b>Critère observé</b>", sc), Paragraph("<b>Points</b>", sc)]] + [[Paragraph(_html.escape(l[0]), sc), Paragraph(l[1], sc)] for l in bm["lignes"]]
                    cw = [W * 0.8, W * 0.2]
                else:
                    data = [[Paragraph(f"<b>{x}</b>", sc) for x in ("Note /10", f"Garçons {age} ans", f"Garçons {age + 2} ans et +", f"Filles {age} ans", f"Filles {age + 2} ans et +")]]
                    data += [[Paragraph(str(l[0]), sc)] + [Paragraph(_html.escape(x), sc) for x in l[1:]] for l in bm["lignes"]]
                    cw = [W * 0.12] + [W * 0.22] * 4
                tb = Table(data, colWidths=cw, repeatRows=1)
                tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#667085")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FCE7F6")),
                                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
                h.append(KeepTogether([Paragraph(f"<b>{_html.escape(epreuve)}</b> — {_html.escape(consigne)}", st), tb, Spacer(1, 6)]))
        h += [PageBreak(), Paragraph("Dispenses, adaptations et sécurité", sh)] + [Paragraph("• " + _html.escape(a), st) for a in BEE.ADAPTATIONS]
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=16 * mm,
                          title="Barèmes EPS", author="GESCOL").build(h, canvasmaker=pdfs.GCanvasPeda)
        return H.pdf_reponse(buf.getvalue(), "baremes_eps" + (f"_{cours}" if cours else "") + ".pdf")

    @app.route("/preparation/guides/<gid>")
    @H.connexion_requise("preparation")
    def prep_guide(gid):
        x = corpus()["guide_par_id"].get(gid)
        if not x:
            abort(404)
        from markupsafe import Markup
        return render_template("prep_guide.html", x=x, contenu=Markup(x["html"]))   # HTML nettoyé à la construction du corpus

    @app.route("/preparation/guides/<gid>.pdf")
    @H.connexion_requise("preparation")
    def prep_guide_pdf(gid):
        x = corpus()["guide_par_id"].get(gid)
        if not x:
            abort(404)
        import pdfs
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        W, Hh = A4
        marge = 15 * mm
        st = {"p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=12.5, spaceAfter=4),
              "li": ParagraphStyle("li", fontName="Helvetica", fontSize=9.5, leading=12.5, leftIndent=10, spaceAfter=2),
              "td": ParagraphStyle("td", fontName="Helvetica", fontSize=7.8, leading=9.5),
              "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=pdfs.BLEU, spaceBefore=6, spaceAfter=6),
              "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=pdfs.BLEU, spaceBefore=6, spaceAfter=3),
              "h4": ParagraphStyle("h4", fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=4, spaceAfter=2)}
        conv = _GuideVersPdf(st, W - 2 * marge)
        conv.feed(x["html"])
        conv.close()
        conv._vider()
        histoire = [Paragraph(f"GUIDE PÉDAGOGIQUE — {nom_matiere(x['matiere']).upper()}", ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=14, alignment=1, textColor=pdfs.BLEU, leading=18)),
                    Paragraph(f"{_html.escape(x['titre'])} · {', '.join(COURS_LIB.get(c, c) for c in x.get('cours') or [])}", ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, alignment=1, leading=12)),
                    Spacer(1, 6)] + conv.out
        if x.get("mention"):
            histoire += [Spacer(1, 6), Paragraph(_html.escape(x["mention"]), ParagraphStyle("m", fontName="Helvetica-Oblique", fontSize=9, textColor=colors.HexColor("#B54708")))]
        histoire.append(Paragraph(f"Source : {_html.escape(x.get('source', ''))}", ParagraphStyle("so", fontName="Helvetica", fontSize=7, textColor=colors.grey)))

        def deco(c, doc):
            pdfs._entete_primaire(c, W, Hh, marge, None, None)
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.grey)
            c.drawRightString(W - marge, 7 * mm, f"Page {doc.page}")
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=A4, leftMargin=marge, rightMargin=marge, topMargin=marge + 30 * mm, bottomMargin=13 * mm,
                          title=x["titre"], author="GESCOL").build(histoire, onFirstPage=deco, onLaterPages=deco, canvasmaker=pdfs.GCanvasPeda)
        return H.pdf_reponse(buf.getvalue(), re.sub(r"[^A-Za-z0-9]+", "_", _sans_accent("guide_" + x["titre"]))[:70] + ".pdf")

    def fiches_demandees(a):
        """Fiches de la liste selon les filtres (cours, matière, SA, séance, recherche, semaine d'une classe)."""
        cours, mat, smat = a.get("cours") or "", a.get("matiere") or "", a.get("smat") or ""
        sa = a.get("sa", type=int)
        seance = a.get("seance", type=int)
        texte = (a.get("q") or "").strip()
        statut = a.get("statut") or ""
        cid = a.get("classe", type=int)
        semaine = None
        if a.get("semaine") and cid:
            cl = next((c for c in classes() if c["id"] == cid), None)
            if cl:
                semaine = cette_semaine(cl)
                ids = []
                for m in semaine["matieres"]:
                    if not mat or m["matiere"] == mat:
                        ids += m.get("ids") or [f["id"] for f in m["fiches"]]   # v1.19 : toutes les fiches de la semaine
                liste = [corpus()["fiche_par_id"][i] for i in ids]
            else:
                liste = []
        else:
            liste = fiches_filtrees(cours or None, mat or None, smat or None, sa, seance, texte or None, statut or None)
        return liste, semaine

    LOT_MAX = 120

    @app.route("/preparation/fiches-lot.<fmt>")
    @H.connexion_requise("preparation")
    def prep_fiches_lot(fmt):
        """v2.2 — téléchargement groupé : fiches cochées (« ids ») ou toutes celles du filtre ; un seul PDF (livret), un seul
        document Word, ou un ZIP d'un document Word par fiche."""
        if fmt not in ("pdf", "docx", "zip"):
            abort(404)
        ids = [i for i in (request.args.get("ids") or "").split(",") if i]
        if ids:
            fp = corpus()["fiche_par_id"]
            liste = [fp[i] for i in ids if i in fp]
        else:
            liste, _s = fiches_demandees(request.args)
        if not liste:
            flash("Aucune fiche à télécharger : cochez des fiches ou choisissez un filtre.", "warning")
            return redirect(url_for("prep_fiches", **{k: v for k, v in request.args.items() if k != "ids"}))
        if len(liste) > LOT_MAX:
            flash(f"{len(liste)} fiches : le téléchargement groupé est limité à {LOT_MAX}. Précisez le filtre (cours, matière, SA).", "warning")
            return redirect(url_for("prep_fiches", **{k: v for k, v in request.args.items() if k != "ids"}))
        cid = request.args.get("classe", type=int)
        fiches = []
        for f in liste:
            d = dict(f)
            if cid and any(c["id"] == cid and NIVEAU_COURS.get(c["niveau"]) == d.get("cours") for c in classes()):
                d["classe_id"] = cid
            d["source_id"] = f["id"]
            fiches.append(d)
        base = re.sub(r"[^A-Za-z0-9]+", "_", _sans_accent("fiches_" + "_".join(x for x in (request.args.get("cours"), request.args.get("matiere"),
                      ("SA" + request.args["sa"]) if request.args.get("sa") else "") if x)))[:70].strip("_") or "fiches"
        H.journal("prep_fiches_lot", f"{fmt} : {len(fiches)} fiche(s)")
        if fmt == "pdf":
            return H.pdf_reponse(pdf_fiches(fiches), base + ".pdf")
        if fmt == "docx":
            return H.reponse_docx(doc_word(fiches), base + ".docx", "Fiches de préparation")
        import export_doc as E
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            vus = set()
            for k, d in enumerate(fiches, 1):
                n = f"{k:03d}_{nom_fichier(d, 'docx')}"
                if n in vus:
                    continue
                vus.add(n)
                z.writestr(n, E.html_vers_docx(doc_word([d]), d.get("titre") or "Fiche"))
        return H.reponse_fichier(out.getvalue(), base + "_word.zip", "application/zip")

    @app.route("/preparation/fiches")
    @H.connexion_requise("preparation")
    def prep_fiches():
        a = request.args
        cours, mat, smat = a.get("cours") or "", a.get("matiere") or "", a.get("smat") or ""
        sa = a.get("sa", type=int)
        seance = a.get("seance", type=int)
        texte = (a.get("q") or "").strip()
        statut = a.get("statut") or ""
        cid = a.get("classe", type=int)
        liste, semaine = fiches_demandees(a)
        page = max(1, a.get("page", 1, type=int))
        total = len(liste)
        smats = sorted({f.get("sous_matiere") for f in fiches_filtrees(cours or None, mat or None) if f.get("sous_matiere")})
        return render_template("prep_fiches.html", fiches=liste[(page - 1) * PAR_PAGE: page * PAR_PAGE], total=total, page=page,
                               pages=(total + PAR_PAGE - 1) // PAR_PAGE, cours=cours, mat=mat, smat=smat, sa=sa, seance=seance, q=texte,
                               statut=statut, smats=smats, COURS=COURS, MATS=ORDRE_MAT, classes=classes(), cid=cid, semaine=semaine)

    @app.route("/preparation/fiches/<fid>")
    @H.connexion_requise("preparation")
    def prep_fiche(fid):
        f = fiche_corpus(fid)
        return render_template("prep_fiche.html", f=f, classes=classes(), propre=False, CHAMPS=CHAMPS, resumes=resumes_de_fiche(fid))

    @app.route("/preparation/fiches/<fid>.pdf")
    @H.connexion_requise("preparation")
    def prep_fiche_pdf(fid):
        f = dict(fiche_corpus(fid))
        cid = request.args.get("classe", type=int)
        if cid and any(c["id"] == cid and NIVEAU_COURS.get(c["niveau"]) == f.get("cours") for c in classes()):
            f["classe_id"] = cid
        f["source_id"] = fid
        H.journal("prep_fiche_pdf", f["titre"][:120])
        return H.pdf_reponse(pdf_fiches([f]), nom_fichier(f, "pdf"))

    @app.route("/preparation/fiches/<fid>.doc")
    def prep_fiche_doc_ancien(fid):              # v2.2.1 : anciens liens « .doc » -> « .docx » (Word 2007 et plus)
        return redirect(url_for("prep_fiche_doc", fid=fid, **request.args.to_dict()), 301)

    @app.route("/preparation/fiches/<fid>.docx")
    @H.connexion_requise("preparation")
    def prep_fiche_doc(fid):
        f = dict(fiche_corpus(fid))
        cid = request.args.get("classe", type=int)
        if cid and any(c["id"] == cid and NIVEAU_COURS.get(c["niveau"]) == f.get("cours") for c in classes()):
            f["classe_id"] = cid
        return reponse_doc(doc_word([f]), nom_fichier(f, "docx"))

    @app.route("/preparation/semaine.pdf")
    @H.connexion_requise("preparation")
    def prep_semaine_pdf():
        cid = request.args.get("classe", type=int)
        cl = next((c for c in classes() if c["id"] == cid), None)
        if not cl:
            abort(404)
        s = cette_semaine(cl)
        fiches = [dict(f, classe_id=cid, source_id=f["id"]) for m in s["matieres"] for f in m["fiches"]]
        du, au = s["bornes"] or (None, None)
        mes = q("SELECT id FROM prep_fiches WHERE ecole_id=? AND user_id=? AND classe_id=? AND date_seance BETWEEN ? AND ? ORDER BY date_seance",
                (H.eco(), g.user["id"], cid, du or "0000", au or "9999")) if du else []
        fiches = [ma_fiche(r["id"]) for r in mes] + fiches
        if not fiches:
            flash("Aucune fiche pour cette semaine : la planification de la classe ne cite pas encore de SA, d'unité ou de dossier.", "warning")
            return redirect(url_for("prep_accueil"))
        H.journal("prep_semaine_pdf", f"{cl['nom']} : {len(fiches)} fiche(s)")
        return H.pdf_reponse(pdf_fiches(fiches), f"fiches_semaine_{re.sub(r'[^A-Za-z0-9]+', '_', cl['nom'])}.pdf")

    @app.route("/preparation/preparer", methods=["GET", "POST"])
    @H.connexion_requise("preparation")
    def prep_preparer():
        cls = classes()
        if not cls:
            flash("Aucune classe : la préparation d'une fiche se fait pour une de vos classes.", "warning")
            return redirect(url_for("prep_accueil"))
        if request.method == "POST":
            d = lire_formulaire(request.form)
            if not d["classe_id"] or not peut_ecrire(d["classe_id"]):
                abort(403)
            if not d["titre"]:
                flash("Le titre de la séance est obligatoire.", "danger")
                return render_template("prep_form.html", d=d, classes=cls, CHAMPS=CHAMPS, MATS=ORDRE_MAT, nouveau=True, MAX=MAX_LIGNES), 400
            cl = next(c for c in cls if c["id"] == d["classe_id"])
            maint = H.maintenant()
            mid = ex("INSERT INTO prep_fiches (ecole_id, user_id, classe_id, date_seance, cours, matiere, sa, seance, titre, donnees, source_id, cree_le, maj_le) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (H.eco(), g.user["id"], cl["id"], d["date_seance"], NIVEAU_COURS.get(cl["niveau"]), d["matiere"], d["sa"], d["seance"],
                      d["titre"][:300], json.dumps({k: d[k] for k in CLES_TEXTE + ["deroulement"]}, ensure_ascii=False),
                      (request.form.get("source_id") or "")[:80] or None, maint, maint))
            H.journal("prep_fiche_creee", f"{cl['nom']} : {d['titre'][:120]}")
            noter_fiche(mid, d["titre"], dict({k: d[k] for k in CLES_TEXTE + ["deroulement"]}, _titre=d["titre"]), "création")
            flash("Fiche enregistrée dans « Mes fiches ».", "success")
            return redirect(url_for("prep_ma_fiche", mid=mid))
        cid = request.args.get("classe", type=int)
        cl = next((c for c in cls if c["id"] == cid), cls[0])
        src = request.args.get("depuis") or ""
        mod = request.args.get("modele") or ""
        if src:
            f = fiche_corpus(src)
            d = {k: f.get(k, "") for k in CLES_TEXTE}
            d.update({"matiere": f["matiere"], "sa": f.get("sa"), "seance": f.get("seance"), "deroulement": [list(l) for l in f.get("deroulement") or []],
                      "source_id": src})
            if f.get("cours") != NIVEAU_COURS.get(cl["niveau"]):
                cl = next((c for c in cls if NIVEAU_COURS.get(c["niveau"]) == f.get("cours")), cl)
        elif mod and mod in corpus()["modele_par_id"]:
            d = depuis_modele(corpus()["modele_par_id"][mod], cl)
            d["source_id"] = "modele:" + mod
        else:
            d = fiche_vierge(cl, request.args.get("matiere") if request.args.get("matiere") in corpus()["matieres"] else "francais")
        d["classe_id"] = cl["id"]
        d["date_seance"] = request.args.get("date") or date.today().isoformat()
        modeles = sorted(corpus()["modeles"], key=lambda m: (ORDRE_MAT.index(m["matiere"]) if m["matiere"] in ORDRE_MAT else 9, m["libelle"]))
        return render_template("prep_form.html", d=d, classes=cls, CHAMPS=CHAMPS, MATS=ORDRE_MAT, nouveau=True, MAX=MAX_LIGNES, modeles=modeles)

    @app.route("/preparation/mes-fiches")
    @H.connexion_requise("preparation")
    def prep_mes_fiches():
        partagees = []
        if g.user["role"] == "enseignant":
            rows = q("SELECT p.*, c.nom classe_nom FROM prep_fiches p LEFT JOIN classes c ON c.id=p.classe_id WHERE p.ecole_id=? AND p.user_id=? "
                     "ORDER BY COALESCE(p.date_seance, p.maj_le) DESC", (H.eco(), g.user["id"]))
            partagees = q("SELECT p.*, c.nom classe_nom, u.nom auteur FROM prep_fiches p LEFT JOIN classes c ON c.id=p.classe_id "
                          "LEFT JOIN utilisateurs u ON u.id=p.user_id WHERE p.ecole_id=? AND p.user_id<>? AND p.partagee=1 "
                          "ORDER BY p.maj_le DESC LIMIT 300", (H.eco(), g.user["id"]))
        else:
            rows = q("SELECT p.*, c.nom classe_nom, u.nom auteur FROM prep_fiches p LEFT JOIN classes c ON c.id=p.classe_id "
                     "LEFT JOIN utilisateurs u ON u.id=p.user_id WHERE p.ecole_id=? ORDER BY COALESCE(p.date_seance, p.maj_le) DESC", (H.eco(),))
        return render_template("prep_mes_fiches.html", rows=rows, partagees=partagees)

    @app.route("/preparation/mes-fiches/<int:mid>/partager", methods=["POST"])
    @H.connexion_requise("preparation")
    def prep_ma_fiche_partager(mid):
        """v1.33 : partager (ou ne plus partager) une fiche avec les collègues de l'école."""
        d = ma_fiche(mid, ecrire=True)
        v = 0 if d.get("partagee") else 1
        ex("UPDATE prep_fiches SET partagee=? WHERE id=?", (v, mid))
        if v:
            noter_fiche(mid, d["titre"], dict({k: d.get(k, "") for k in CLES_TEXTE + ["deroulement"]}, _titre=d["titre"]), "partagée avec l'école")
        H.journal("prep_fiche_partagee" if v else "prep_fiche_non_partagee", d["titre"][:120])
        flash("Fiche partagée : vos collègues de l'école peuvent la lire et la copier." if v else "La fiche n'est plus partagée.", "success")
        return redirect(url_for("prep_ma_fiche", mid=mid))

    @app.route("/preparation/mes-fiches/<int:mid>/copier", methods=["POST"])
    @H.connexion_requise("preparation")
    def prep_ma_fiche_copier(mid):
        """v1.33 : copier la fiche partagée d'un collègue dans ses propres fiches (une de ses classes du même cours)."""
        d = ma_fiche(mid)
        cls = classes()
        cl = next((c for c in cls if NIVEAU_COURS.get(c["niveau"]) == d.get("cours")), cls[0] if cls else None)
        if not cl or not peut_ecrire(cl["id"]):
            abort(403)
        maint = H.maintenant()
        nid = ex("INSERT INTO prep_fiches (ecole_id, user_id, classe_id, date_seance, cours, matiere, sa, seance, titre, donnees, source_id, cree_le, maj_le) "
                 "SELECT ecole_id, ?, ?, NULL, cours, matiere, sa, seance, titre, donnees, source_id, ?, ? FROM prep_fiches WHERE id=?",
                 (g.user["id"], cl["id"], maint, maint, mid))
        H.journal("prep_fiche_copiee", f"{mid} -> {nid}")
        flash("Fiche copiée dans vos fiches : choisissez la date de la séance.", "success")
        return redirect(url_for("prep_ma_fiche", mid=nid, modifier=1))

    @app.route("/preparation/mes-fiches/<int:mid>", methods=["GET", "POST"])
    @H.connexion_requise("preparation")
    def prep_ma_fiche(mid):
        d = ma_fiche(mid)
        modif = request.args.get("modifier") or request.method == "POST"
        if request.method == "POST":
            ma_fiche(mid, ecrire=True)
            n = lire_formulaire(request.form)
            if not n["classe_id"] or not peut_ecrire(n["classe_id"]):
                abort(403)
            if not n["titre"]:
                flash("Le titre de la séance est obligatoire.", "danger")
                return render_template("prep_form.html", d={**d, **n}, classes=classes(), CHAMPS=CHAMPS, MATS=ORDRE_MAT, nouveau=False, MAX=MAX_LIGNES), 400
            cl = next(c for c in classes() if c["id"] == n["classe_id"])
            ex("UPDATE prep_fiches SET classe_id=?, date_seance=?, cours=?, matiere=?, sa=?, seance=?, titre=?, donnees=?, maj_le=? WHERE id=?",
               (cl["id"], n["date_seance"], NIVEAU_COURS.get(cl["niveau"]), n["matiere"], n["sa"], n["seance"], n["titre"][:300],
                json.dumps({k: n[k] for k in CLES_TEXTE + ["deroulement"]}, ensure_ascii=False), H.maintenant(), mid))
            H.journal("prep_fiche_modifiee", n["titre"][:120])
            noter_fiche(mid, n["titre"], dict({k: n[k] for k in CLES_TEXTE + ["deroulement"]}, _titre=n["titre"]), "modification")
            flash("Fiche modifiée.", "success")
            return redirect(url_for("prep_ma_fiche", mid=mid))
        if modif and d["user_id"] == g.user["id"]:
            return render_template("prep_form.html", d=d, classes=classes(), CHAMPS=CHAMPS, MATS=ORDRE_MAT, nouveau=False, MAX=MAX_LIGNES)
        return render_template("prep_fiche.html", f=d, classes=classes(), propre=True, CHAMPS=CHAMPS,
                               auteur=d["user_id"] == g.user["id"])

    @app.route("/preparation/mes-fiches/<int:mid>/dupliquer", methods=["POST"])
    @H.connexion_requise("preparation")
    def prep_ma_fiche_dupliquer(mid):
        ma_fiche(mid, ecrire=True)
        maint = H.maintenant()
        nid = ex("INSERT INTO prep_fiches (ecole_id, user_id, classe_id, date_seance, cours, matiere, sa, seance, titre, donnees, source_id, cree_le, maj_le) "
                 "SELECT ecole_id, user_id, classe_id, NULL, cours, matiere, sa, seance, titre || ' (copie)', donnees, source_id, ?, ? FROM prep_fiches WHERE id=?",
                 (maint, maint, mid))
        flash("Fiche dupliquée : choisissez la date de la nouvelle séance.", "success")
        return redirect(url_for("prep_ma_fiche", mid=nid, modifier=1))

    @app.route("/preparation/mes-fiches/<int:mid>/supprimer", methods=["POST"])
    @H.connexion_requise("preparation")
    def prep_ma_fiche_supprimer(mid):
        d = ma_fiche(mid, ecrire=True)
        ex("DELETE FROM prep_fiches WHERE id=?", (mid,))
        H.journal("prep_fiche_supprimee", d["titre"][:120])
        flash("Fiche supprimée.", "success")
        return redirect(url_for("prep_mes_fiches"))

    @app.route("/preparation/mes-fiches/<int:mid>.pdf")
    @H.connexion_requise("preparation")
    def prep_ma_fiche_pdf(mid):
        d = ma_fiche(mid)
        return H.pdf_reponse(pdf_fiches([d]), nom_fichier(d, "pdf"))

    @app.route("/preparation/mes-fiches/<int:mid>.doc")
    def prep_ma_fiche_doc_ancien(mid):
        return redirect(url_for("prep_ma_fiche_doc", mid=mid, **request.args.to_dict()), 301)

    @app.route("/preparation/mes-fiches/<int:mid>.docx")
    @H.connexion_requise("preparation")
    def prep_ma_fiche_doc(mid):
        d = ma_fiche(mid)
        return reponse_doc(doc_word([d]), nom_fichier(d, "docx"))

    # ------------------------------------------------------------ v1.31 : révisions d'éveil, manuels, mesures correctives
    @app.route("/preparation/revisions")
    @H.connexion_requise("preparation")
    def prep_revisions():
        return render_template("prep_revisions.html", revisions=corpus().get("revisions") or [], rv=None)

    @app.route("/preparation/revisions/<rid>")
    @H.connexion_requise("preparation")
    def prep_revision(rid):
        rv = corpus()["revision_par_id"].get(rid) or abort(404)
        return render_template("prep_revisions.html", revisions=corpus().get("revisions") or [], rv=rv, eleve=bool(request.args.get("eleve")))

    @app.route("/preparation/revisions/<rid>.pdf")
    @H.connexion_requise("preparation")
    def prep_revision_pdf(rid):
        rv = corpus()["revision_par_id"].get(rid) or abort(404)
        a = request.args
        partie = a.get("partie") if a.get("partie") in ("es", "est") else None
        sujet = a.get("sujet", type=int)
        if sujet is not None and not 1 <= sujet <= len(rv["sujets"]):
            abort(404)
        eleve = bool(a.get("eleve"))
        nom = f"revision_eveil_{rv['cours']}" + (f"_{partie}" if partie else "") + (f"_sujet{sujet}" if sujet else "") + ("_eleve" if eleve else "") + ".pdf"
        return H.pdf_reponse(pdf_revision(rv, eleve, partie, sujet), nom)

    @app.route("/preparation/manuels")
    @H.connexion_requise("preparation")
    def prep_manuels():
        C = corpus()
        lect = {}
        for r in C.get("resumes") or []:
            if r.get("lecture") and r.get("manuel"):
                lect[(r["manuel"]["id"], r["manuel"]["texte"])] = r
        seances = {}
        for f in C["fiches"]:
            m = f.get("manuel")
            if m and m.get("texte"):
                seances.setdefault((m["id"], m["texte"]), []).append(f)
        return render_template("prep_manuels.html", manuels=C.get("manuels") or [], lect=lect, seances=seances,
                               mesures=C.get("mesures_correctives") or [])

    @app.route("/preparation/manquants")
    @H.connexion_requise("preparation")
    def prep_manquants():
        C = corpus()
        m = C.get("manquants") or {}
        concues = [f for f in C["fiches"] if f.get("statut") == "concue"]
        par = {}
        for f in concues:
            if not f["id"].startswith(("cm1i-", "l2c-", "cp22-", "lot3-")):      # inventaires (CM1, lot 2, CP, lot 3) : résumés dans leurs tableaux
                par.setdefault((f["cours"], f["matiere"]), []).append(f)
        guides_c = [x for x in C["guides"] if x.get("statut") == "concu"]
        return render_template("prep_manquants.html", avant=m.get("avant", []), apres=m.get("apres", []), par=par,
                               guides_c=guides_c, mention=m.get("mention", ""), inv=C.get("inventaire_cm1"),
                               nb_resumes=len(C.get("resumes") or []), lots=C.get("lots") or {}, doublons=C.get("doublons") or [])


    # ------------------------------------------------------------ v1.19 : résumés « l'essentiel à retenir »
    def resumes_filtres(col="", cours="", mat="", dom="", sa=None):
        rs = corpus().get("resumes") or []
        if sa:                                      # v1.29 : livret d'une SA
            rs = [r for r in rs if sa in (r.get("sa") or [])]
        emc = mat == "emc"                          # v1.27.1 : Éducation morale et civique (sous-matière de l'Éducation sociale)
        return [r for r in rs if (not col or COLLECTION_DE.get(r["collection"]) == col) and (not cours or r["cours"] == cours)
                and (not mat or r["matiere"] == mat or (emc and r["matiere"] == "es" and r.get("emc"))) and (not dom or r["domaine"] == dom)]

    @app.route("/preparation/resumes")
    @H.connexion_requise("preparation")
    def prep_resumes():
        a = request.args
        col, cours, mat, dom = a.get("col") or "", a.get("cours") or "", a.get("matiere") or "", a.get("domaine") or ""
        tous = corpus().get("resumes") or []
        rs = resumes_filtres(col, cours, mat, dom)
        seul = bool(a.get("seances"))
        if seul:                                    # v1.29 : uniquement les résumés de séance
            rs = [r for r in rs if r.get("seance_resume")]
        groupes = {}
        for r in sorted(rs, key=ordre_resume):
            groupes.setdefault((r["collection"], r["cours"]), {}).setdefault(r["domaine"], []).append(r)
        vue = a.get("vue") if a.get("vue") in ("progression", "domaines") else ("progression" if cours and mat in MATS_PROG + ("emc",) else "domaines")
        ordre = sorted(groupes, key=lambda k: ([c for c, _l in COLLECTIONS_RES].index(COLLECTION_DE[k[0]]), COURS.index(k[1])))
        return render_template("prep_resumes.html", groupes=groupes, ordre=ordre, col=col, cours=cours, mat=mat, dom=dom, n=len(rs),
                               table=table_resumes(tous), COURS_RES=COURS_RES, MATS_RES=MATS_RES, COLLECTIONS=COLLECTIONS_RES, COURS=[c for c in COURS if any(r["cours"] == c for r in tous)],
                               MATS=[m for m in ORDRE_MAT if any(r["matiere"] == m for r in tous)],
                               DOMS=sorted({r["domaine"] for r in tous}), vue=vue,
                               progression=progression_resumes([r for r in rs if r["matiere"] in MATS_PROG]) if vue == "progression" else [],
                               tsa=table_es_est(), tse=table_seances(), seul=seul,
                               sas=sorted({n for r in rs for n in (r.get("sa") or [])}) if cours and mat else [],
                               tdom=table_domaines(tous), OUTILS_FR=OUTILS_FR, DOMAINES_MA=DOMAINES_MA)

    # ---------------------------------------------------------------- v1.33 : résumé adapté par l'école (version partagée)
    CHAMPS_RESUME = [("titre", "Titre"), ("regle", "Je retiens (règle / notions essentielles)"), ("methode", "Méthode"),
                     ("exemple", "Exemple"), ("actualisation", "Et aujourd'hui ?")]

    def resume_local(rid):
        r = q("SELECT * FROM prep_resumes_locaux WHERE ecole_id=? AND rid=?", (H.eco(), rid), un=True)
        if not r:
            return None
        try:
            d = json.loads(r["donnees"])
        except ValueError:
            return None
        d["_maj"] = r["maj"]
        return d

    def locaux_resumes():
        out = {}
        for x in q("SELECT rid, donnees, maj FROM prep_resumes_locaux WHERE ecole_id=?", (H.eco(),)):
            try:
                d = json.loads(x["donnees"])
            except ValueError:
                continue
            d["_maj"] = x["maj"]
            out[x["rid"]] = d
        return out

    def resume_ecole(r, original=False, cache=None):
        """Le résumé du corpus, avec la version de l'école par-dessus quand elle existe."""
        if original:
            return r
        loc = cache.get(r["id"]) if cache is not None else resume_local(r["id"])
        if not loc:
            return r
        d = dict(r)
        d.update({k: v for k, v in loc.items() if not k.startswith("_")})
        d["_local"], d["_maj"] = True, loc.get("_maj")
        return d

    def sauver_resume(rid, d, note):
        ex("INSERT INTO prep_resumes_locaux (ecole_id, rid, donnees, maj, maj_par) VALUES (?,?,?,?,?) "
           "ON CONFLICT(ecole_id, rid) DO UPDATE SET donnees=excluded.donnees, maj=excluded.maj, maj_par=excluded.maj_par",
           (H.eco(), rid, json.dumps(d, ensure_ascii=False), H.maintenant(), g.user["id"]))
        if hasattr(H, "partage_noter") and note != "rétablie":
            H.partage_noter("resume", rid, d.get("titre") or rid, d, note)

    def resume_corpus(rid):
        r = next((x for x in corpus().get("resumes") or [] if x["id"] == rid), None)
        if not r:
            abort(404)
        return r

    if hasattr(H, "partage_type"):
        H.partage_type("resume", "Résumé", lambda cle: url_for("prep_resume", rid=cle),
                       lambda cle, d: (resume_corpus(cle), sauver_resume(cle, d, "rétablie")))

    def peut_adapter_resume():
        return g.user["role"] in ("enseignant", "directeur", "admin", "fondateur", "cp")

    @app.route("/preparation/resumes/<rid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("preparation")
    def prep_resume_modifier(rid):
        r = resume_corpus(rid)
        if not peut_adapter_resume():
            abort(403)
        if request.method == "POST":
            d = {k: (request.form.get(k) or "").strip()[:4000] for k, _l in CHAMPS_RESUME}
            if not d["titre"]:
                flash("Le titre est obligatoire.", "danger")
                return redirect(url_for("prep_resume_modifier", rid=rid))
            exos = []
            for i in range(1, 9):
                qq, rr = (request.form.get(f"q{i}") or "").strip()[:600], (request.form.get(f"r{i}") or "").strip()[:600]
                if qq:
                    exos.append({"q": qq, "r": rr})
            d["exercices"] = exos
            voc = [v.strip() for v in (request.form.get("vocabulaire") or "").split(";") if v.strip()][:30]
            if voc:
                d["vocabulaire"] = voc
            sauver_resume(rid, d, "adaptation de l'école")
            H.journal("prep_resume_adapte", rid)
            flash("Résumé adapté enregistré pour toute l'école (l'original reste consultable).", "success")
            return redirect(url_for("prep_resume", rid=rid))
        return render_template("prep_resume_form.html", r=resume_ecole(r), CHAMPS=CHAMPS_RESUME)

    @app.route("/preparation/resumes/<rid>/original", methods=["POST"])
    @H.connexion_requise("preparation")
    def prep_resume_original(rid):
        resume_corpus(rid)
        if not peut_adapter_resume():
            abort(403)
        ex("DELETE FROM prep_resumes_locaux WHERE ecole_id=? AND rid=?", (H.eco(), rid))
        H.journal("prep_resume_original", rid)
        flash("Résumé d'origine rétabli (la version de l'école reste dans l'historique).", "success")
        return redirect(url_for("prep_resume", rid=rid))

    @app.route("/preparation/resumes/<rid>")
    @H.connexion_requise("preparation")
    def prep_resume(rid):
        r = next((x for x in corpus().get("resumes") or [] if x["id"] == rid), None)
        if not r:
            abort(404)
        meme = sorted(resumes_filtres(COLLECTION_DE[r["collection"]], r["cours"], r["matiere"]), key=ordre_resume)
        i = meme.index(r)
        r = resume_ecole(r, bool(request.args.get("original")))
        return render_template("prep_resume.html", r=r, eleve=bool(request.args.get("eleve")), peut_adapter=peut_adapter_resume(),
                               original=bool(request.args.get("original")),
                               prec=meme[i - 1] if i > 0 else None, suiv=meme[i + 1] if i + 1 < len(meme) else None)

    @app.route("/preparation/resumes/<rid>.pdf")
    @H.connexion_requise("preparation")
    def prep_resume_pdf(rid):
        r = next((x for x in corpus().get("resumes") or [] if x["id"] == rid), None)
        if not r:
            abort(404)
        eleve = bool(request.args.get("eleve"))
        r = resume_ecole(r, bool(request.args.get("original")))
        nom = re.sub(r"[^A-Za-z0-9]+", "_", _sans_accent(("eleve_" if eleve else "resume_") + r["titre"]))[:70] + ".pdf"
        return H.pdf_reponse(pdf_resumes([r], eleve), nom)

    @app.route("/preparation/resumes.pdf")
    @H.connexion_requise("preparation")
    def prep_resumes_pdf():
        a = request.args
        sa = a.get("sa", type=int)
        rs = resumes_filtres(a.get("col") or "", a.get("cours") or "", a.get("matiere") or "", a.get("domaine") or "", sa)
        if a.get("seances"):                        # v1.29 : uniquement les résumés de séance (cahier de résumés)
            rs = [r for r in rs if r.get("seance_resume")]
        if not rs:
            abort(404)
        _loc = locaux_resumes()
        rs = [resume_ecole(r, cache=_loc) for r in sorted(rs, key=ordre_resume)]
        eleve = bool(a.get("eleve"))
        lib = " ".join(x for x in [dict(COLLECTIONS_RES).get(a.get("col") or "", ""), a.get("cours") or "",
                                    nom_matiere(a["matiere"]) if a.get("matiere") else "", a.get("domaine") or "",
                                    f"SA {sa}" if sa else ""] if x) or "tous"
        if sa:
            lib = "Livret de la " + lib
        elif a.get("cours") and a.get("matiere") and not a.get("domaine"):
            lib = "Cahier de résumés " + lib
        nom = re.sub(r"[^A-Za-z0-9]+", "_", _sans_accent(("eleve_" if eleve else "resumes_") + lib))[:70] + ".pdf"
        return H.pdf_reponse(pdf_resumes(rs, eleve, lib), nom)

    @app.route("/preparation/resumes/<rid>.docx")
    @H.connexion_requise("preparation")
    def prep_resume_docx(rid):
        r = next((x for x in corpus().get("resumes") or [] if x["id"] == rid), None)
        if not r:
            abort(404)
        r = resume_ecole(r, bool(request.args.get("original")))
        eleve = bool(request.args.get("eleve"))
        nom = re.sub(r"[^A-Za-z0-9]+", "_", _sans_accent(("eleve_" if eleve else "resume_") + r["titre"]))[:70] + ".docx"
        return H.reponse_docx(html_resumes([r], eleve), nom, r["titre"])

    @app.route("/preparation/resumes-lot.<fmt>")
    @H.connexion_requise("preparation")
    def prep_resumes_lot(fmt):
        """v2.2 — résumés cochés (« ids ») ou du filtre : un PDF, un document Word ou un ZIP (un Word par résumé)."""
        if fmt not in ("pdf", "docx", "zip"):
            abort(404)
        a = request.args
        ids = [i for i in (a.get("ids") or "").split(",") if i]
        if ids:
            par_id = {r["id"]: r for r in corpus().get("resumes") or []}
            rs = [par_id[i] for i in ids if i in par_id]
        else:
            rs = resumes_filtres(a.get("col") or "", a.get("cours") or "", a.get("matiere") or "", a.get("domaine") or "", a.get("sa", type=int))
            if a.get("seances"):
                rs = [r for r in rs if r.get("seance_resume")]
        if not rs:
            flash("Aucun résumé à télécharger : cochez des résumés ou choisissez un filtre.", "warning")
            return redirect(url_for("prep_resumes", **{k: v for k, v in a.items() if k not in ("ids", "eleve")}))
        if len(rs) > 300:
            flash(f"{len(rs)} résumés : le téléchargement groupé est limité à 300. Précisez le cours ou la matière.", "warning")
            return redirect(url_for("prep_resumes", **{k: v for k, v in a.items() if k not in ("ids", "eleve")}))
        _loc = locaux_resumes()
        rs = [resume_ecole(r, cache=_loc) for r in sorted(rs, key=ordre_resume)]
        eleve = bool(a.get("eleve"))
        lib = " ".join(x for x in [a.get("cours") or "", nom_matiere(a["matiere"]) if a.get("matiere") else "", a.get("domaine") or ""] if x) or "choisis"
        base = re.sub(r"[^A-Za-z0-9]+", "_", _sans_accent(("eleve_" if eleve else "resumes_") + lib))[:70].strip("_")
        H.journal("prep_resumes_lot", f"{fmt} : {len(rs)} résumé(s)")
        if fmt == "pdf":
            return H.pdf_reponse(pdf_resumes(rs, eleve, lib), base + ".pdf")
        if fmt == "docx":
            return H.reponse_docx(html_resumes(rs, eleve, lib), base + ".docx", "Résumés " + lib)
        import export_doc as E
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for k, r in enumerate(rs, 1):
                n = f"{k:03d}_" + re.sub(r"[^A-Za-z0-9]+", "_", _sans_accent(r["titre"]))[:60].strip("_") + ".docx"
                z.writestr(n, E.html_vers_docx(html_resumes([r], eleve), r["titre"]))
        return H.reponse_fichier(out.getvalue(), base + "_word.zip", "application/zip")

    @app.route("/preparation/resumes.docx")
    @H.connexion_requise("preparation")
    def prep_resumes_docx():
        return prep_resumes_lot("docx")

    H.prep_cette_semaine = cette_semaine
    H.prep_pdf_fiches = pdf_fiches          # v1.21 : classeurs de fiches (m_evalprep)
    H.prep_doc_word = doc_word
    H.prep_classes = classes
    H.prep_plan_annuel = plan_annuel
    H.prep_ma_fiche = ma_fiche
