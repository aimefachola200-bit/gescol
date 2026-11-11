# -*- coding: utf-8 -*-
"""v1.25 — Sport scolaire (UASCEP) : licences des élèves, compétitions de l'école à la DDEMP, tirage au sort, calendrier,
feuilles de match, classements automatiques, athlétisme et concours (performances, records), jeux traditionnels et
culturels, palmarès, qualifiés pour le niveau supérieur, diplômes signés (cachets, QR).

Périmètres (comme les bureaux de l'UASCEP, m_uascep) :
* éditions école : compétitions de l'école (inter-classes) ; licences des élèves de l'école ;
* édition CS : école, UP, zone pédagogique, circonscription ; DDEMP : tous les niveaux ;
* enseignant : lecture.

Les résultats d'une compétition terminée alimentent le journal de la saison du bureau UASCEP de l'entité
(« Calendrier, compétitions et résultats »), donc le rapport de fin de saison sportive.

Routes
* /sport                                   accueil (saison, chiffres, compétitions, derniers résultats)
* /sport/competitions                      liste +  (formulaire), /sport/competition/<cid> (onglets : équipes, calendrier,
                                           matchs, classement, performances, résultats, documents)
* /sport/records · /sport/palmares[.pdf] · /sport/parametres (catégories d'âge)
* /reg/sport/licences · /reg/sport/officiels · /reg/sport/sites (moteur des registres)
* PDF : calendrier, feuille de match, classement, résultats, palmarès, diplômes (participation, lauréats), carte de licence
"""
import random
import re
import secrets
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

import registres as R

FORMULES = [("championnat", "Championnat (tous contre tous, match simple)"), ("championnat_ar", "Championnat aller-retour"),
            ("poules", "Poules puis phase finale (élimination)"), ("elimination", "Élimination directe (coupe)"),
            ("performances", "Classement par performances (athlétisme, course, sauts, lancers)"),
            ("jury", "Concours notés par un jury (jeux traditionnels et culturels, chant, danse, dessin, quiz…)")]
FORMULE_LIB = dict(FORMULES)
STATUTS = ["Programmée", "En cours", "Terminée", "Annulée"]
GENRES = ["Garçons", "Filles", "Mixte"]
# épreuves individuelles : (unité, sens : 'asc' = plus petit meilleur (temps), 'desc' = plus grand meilleur)
EPREUVES = {"50 m": ("s", "asc"), "60 m": ("s", "asc"), "80 m": ("s", "asc"), "100 m": ("s", "asc"), "200 m": ("s", "asc"),
            "400 m": ("s", "asc"), "600 m": ("s", "asc"), "800 m": ("s", "asc"), "1 000 m": ("s", "asc"), "Relais 4 × 60 m": ("s", "asc"),
            "Relais 4 × 100 m": ("s", "asc"), "Course en sac": ("s", "asc"), "Saut en longueur": ("m", "desc"), "Saut en hauteur": ("m", "desc"),
            "Triple saut": ("m", "desc"), "Lancer de balle": ("m", "desc"), "Lancer de poids": ("m", "desc"), "Lancer de vortex": ("m", "desc"),
            "Awalé": ("pts", "desc"), "Dames": ("pts", "desc"), "Tir à la corde": ("pts", "desc"), "Chant / chorale": ("pts", "desc"),
            "Danse": ("pts", "desc"), "Théâtre / sketch": ("pts", "desc"), "Poésie / récitation": ("pts", "desc"), "Dessin": ("pts", "desc"),
            "Quiz / culture générale": ("pts", "desc"), "Génies en herbe": ("pts", "desc")}
TOURS_ELIM = {2: "Finale", 4: "Demi-finales", 8: "Quarts de finale", 16: "Huitièmes de finale", 32: "Seizièmes de finale"}
# spécification commune (outils/lots/spec.md) : âge atteint au 31 décembre de la 1re année de la saison
CATEGORIES_DEF = [("Poussins", 0, 8), ("Benjamins", 9, 10), ("Minimes", 11, 12), ("Cadets", 13, 99)]
NIVEAU_SUP = {"ECOLE": "UP", "UP": "ZONE", "ZONE": "CS", "CS": "DDEMP"}
APTITUDES = ["Apte", "Apte avec réserve", "Inapte", "Non examiné"]
COURS = ["Maternelle", "CI", "CP", "CE1", "CE2", "CM1", "CM2"]
# libellés de la formule dans l'Excel commun (spec) ; « performances » et « jury » = classement sans matchs
FORMULE_EXCEL = {"poules": "Poules puis élimination directe", "championnat": "Championnat (matchs simples)", "championnat_ar": "Championnat aller-retour",
                 "elimination": "Élimination directe", "performances": "Classement individuel ou par équipe (sans matchs)",
                 "jury": "Classement individuel ou par équipe (sans matchs)"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS sport_competitions (
    id INTEGER PRIMARY KEY, portee INTEGER NOT NULL DEFAULT 0, saison TEXT NOT NULL, niveau TEXT NOT NULL, entite TEXT NOT NULL,
    entite_lib TEXT, intitule TEXT NOT NULL, discipline TEXT, categorie TEXT, genre TEXT, formule TEXT NOT NULL DEFAULT 'championnat',
    nb_poules INTEGER DEFAULT 1, qualifies_poule INTEGER DEFAULT 2, qualifies_sup INTEGER DEFAULT 1, pts_victoire INTEGER DEFAULT 3,
    pts_nul INTEGER DEFAULT 1, pts_defaite INTEGER DEFAULT 0, score_forfait INTEGER DEFAULT 3, date_debut TEXT, date_fin TEXT,
    lieu TEXT, organisateur TEXT, statut TEXT DEFAULT 'Programmée', origine_id INTEGER, reglement TEXT, observations TEXT, cree_le TEXT, maj TEXT
);
CREATE INDEX IF NOT EXISTS ix_sport_c ON sport_competitions(portee, saison, niveau);
CREATE TABLE IF NOT EXISTS sport_equipes (
    id INTEGER PRIMARY KEY, competition_id INTEGER NOT NULL REFERENCES sport_competitions(id) ON DELETE CASCADE,
    nom TEXT NOT NULL, ecole TEXT, poule TEXT, tete_serie INTEGER DEFAULT 0, encadreur TEXT, contact TEXT, joueurs TEXT,
    effectif_g INTEGER, effectif_f INTEGER, origine TEXT, forfait_general INTEGER DEFAULT 0, capitaine TEXT, maj TEXT
);
CREATE INDEX IF NOT EXISTS ix_sport_e ON sport_equipes(competition_id);
CREATE TABLE IF NOT EXISTS sport_matchs (
    id INTEGER PRIMARY KEY, competition_id INTEGER NOT NULL REFERENCES sport_competitions(id) ON DELETE CASCADE,
    phase TEXT, tour TEXT, poule TEXT, ordre INTEGER DEFAULT 0, date TEXT, heure TEXT, terrain TEXT,
    equipe_a INTEGER, equipe_b INTEGER, score_a INTEGER, score_b INTEGER, tab_a INTEGER, tab_b INTEGER, forfait TEXT,
    buteurs_a TEXT, buteurs_b TEXT, jaunes_a INTEGER, jaunes_b INTEGER, rouges_a INTEGER, rouges_b INTEGER,
    arbitre TEXT, assesseurs TEXT, delegue TEXT, observations TEXT, maj TEXT
);
CREATE INDEX IF NOT EXISTS ix_sport_m ON sport_matchs(competition_id, phase, tour);
CREATE TABLE IF NOT EXISTS sport_perfs (
    id INTEGER PRIMARY KEY, competition_id INTEGER NOT NULL REFERENCES sport_competitions(id) ON DELETE CASCADE,
    epreuve TEXT NOT NULL, serie TEXT, nom TEXT NOT NULL, prenoms TEXT, sexe TEXT, categorie TEXT, ecole TEXT, licence TEXT,
    performance TEXT, valeur REAL, observations TEXT, maj TEXT
);
CREATE INDEX IF NOT EXISTS ix_sport_p ON sport_perfs(competition_id, epreuve);
CREATE TABLE IF NOT EXISTS sport_tirages (
    id INTEGER PRIMARY KEY, competition_id INTEGER NOT NULL REFERENCES sport_competitions(id) ON DELETE CASCADE,
    fait_le TEXT, fait_par TEXT, resultat TEXT
);
CREATE TABLE IF NOT EXISTS sport_parametres (cle TEXT PRIMARY KEY, valeur TEXT);
"""


# ------------------------------------------------------------------ calculs purs (testables)
def valeur_perf(texte, unite="s"):
    """« 9''8 », « 9.8 », « 1'12''5 », « 3,45 m », « 3 m 45 », « 14 pts » -> nombre (secondes, mètres ou points)."""
    t = str(texte or "").strip().lower().replace(",", ".")
    if not t:
        return None
    m = re.fullmatch(r"(?:(\d+)\s*['’]\s*)?(\d+(?:\.\d+)?)\s*(?:''|\"|”|s|sec)?\s*(\d+)?", t)
    if unite == "s" and m:
        mn = int(m.group(1) or 0)
        sec = float(m.group(2))
        if m.group(3):                                   # 9''8 -> 9,8
            sec = float(f"{int(sec)}.{m.group(3)}")
        return round(mn * 60 + sec, 3)
    m = re.fullmatch(r"(\d+)\s*m\s*(\d{1,2})", t)        # 3 m 45
    if m:
        return float(f"{m.group(1)}.{m.group(2).zfill(2)}")
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    return float(m.group(0)) if m else None


def categorie_age(annee_naissance, saison, bornes=None):
    """Catégorie d'après l'âge atteint dans l'année civile du début de saison (2026-2027, né en 2016 -> 10 ans)."""
    try:
        age = int(str(saison)[:4]) - int(str(annee_naissance)[:4])
    except (TypeError, ValueError):
        return ""
    for nom, a, b in (bornes or CATEGORIES_DEF):
        if a <= age <= b:
            return nom
    return ""


def tour_robin(ids, aller_retour=False):
    """Calendrier « tous contre tous » (méthode du cercle) : [(journée, a, b)]."""
    eq = list(ids)
    if len(eq) < 2:
        return []
    if len(eq) % 2:
        eq.append(None)
    n = len(eq)
    out = []
    for j in range(n - 1):
        for i in range(n // 2):
            a, b = eq[i], eq[n - 1 - i]
            if a is not None and b is not None:
                out.append((j + 1, a, b) if (j % 2 == 0 or i) else (j + 1, b, a))
        eq = [eq[0]] + [eq[-1]] + eq[1:-1]
    if aller_retour:
        k = n - 1
        out += [(j + k, b, a) for j, a, b in list(out)]
    return out


def resultat_match(m, forfait_score=3):
    """(sa, sb, joue) en tenant compte du forfait (A, B ou AB)."""
    f = (m.get("forfait") or "").upper()
    if f == "A":
        return 0, forfait_score, True
    if f == "B":
        return forfait_score, 0, True
    if f == "AB":
        return 0, 0, True
    if m.get("score_a") is None or m.get("score_b") is None:
        return None, None, False
    return m["score_a"], m["score_b"], True


def vainqueur(m, forfait_score=3):
    """Équipe qualifiée d'un match à élimination (tirs au but si égalité) ; None si non joué ou indécis."""
    sa, sb, joue = resultat_match(m, forfait_score)
    if not joue:
        return None
    if (m.get("forfait") or "").upper() == "AB":
        return None
    if sa != sb:
        return m["equipe_a"] if sa > sb else m["equipe_b"]
    if m.get("tab_a") is not None and m.get("tab_b") is not None and m["tab_a"] != m["tab_b"]:
        return m["equipe_a"] if m["tab_a"] > m["tab_b"] else m["equipe_b"]
    return None


def classement(equipes, matchs, pts=(3, 1, 0), forfait_score=3):
    """Classement d'une poule / d'un championnat. Départage : points, confrontations directes (points, différence, buts
    marqués) entre ex aequo, différence générale, buts marqués, fair-play (jaunes + 3 × rouges), nom."""
    st = {e["id"]: {"id": e["id"], "nom": e["nom"], "ecole": e.get("ecole") or "", "j": 0, "g": 0, "n": 0, "p": 0, "bp": 0, "bc": 0,
                    "pts": 0, "fp": 0} for e in equipes}
    joues = []
    for m in matchs:
        a, b = m.get("equipe_a"), m.get("equipe_b")
        if a not in st or b not in st:
            continue
        sa, sb, joue = resultat_match(m, forfait_score)
        if not joue:
            continue
        joues.append((a, b, sa, sb, (m.get("forfait") or "").upper()))
        for x, y, bx, by, cote in ((a, b, sa, sb, "A"), (b, a, sb, sa, "B")):
            s = st[x]
            s["j"] += 1
            s["bp"] += bx
            s["bc"] += by
            s["fp"] += (m.get("jaunes_" + cote.lower()) or 0) + 3 * (m.get("rouges_" + cote.lower()) or 0)
            forf = (m.get("forfait") or "").upper()
            if forf in (cote, "AB"):
                s["p"] += 1
                s["pts"] += min(pts[2], 0) if forf == cote else 0
            elif bx > by:
                s["g"] += 1
                s["pts"] += pts[0]
            elif bx == by:
                s["n"] += 1
                s["pts"] += pts[1]
            else:
                s["p"] += 1
                s["pts"] += pts[2]
    for s in st.values():
        s["diff"] = s["bp"] - s["bc"]

    def h2h(groupe):
        ids = {s["id"] for s in groupe}
        d = {i: [0, 0, 0] for i in ids}
        for a, b, sa, sb, _f in joues:
            if a in ids and b in ids:
                for x, bx, by in ((a, sa, sb), (b, sb, sa)):
                    d[x][0] += pts[0] if bx > by else pts[1] if bx == by else pts[2]
                    d[x][1] += bx - by
                    d[x][2] += bx
        return d
    ordre = sorted(st.values(), key=lambda s: -s["pts"])
    out, i = [], 0
    while i < len(ordre):
        j = i
        while j < len(ordre) and ordre[j]["pts"] == ordre[i]["pts"]:
            j += 1
        grp = ordre[i:j]
        if len(grp) > 1:
            d = h2h(grp)
            grp.sort(key=lambda s: (-d[s["id"]][0], -d[s["id"]][1], -d[s["id"]][2], -s["diff"], -s["bp"], s["fp"], s["nom"]))
        out += grp
        i = j
    for k, s in enumerate(out, 1):
        s["rang"] = k
    return out


def classer_perfs(perfs, sens="asc"):
    """Rang par épreuve (valeurs égales = même rang ; sans valeur : non classé)."""
    avec = sorted([p for p in perfs if p.get("valeur") is not None], key=lambda p: p["valeur"] if sens == "asc" else -p["valeur"])
    rang, prec = 0, None
    for k, p in enumerate(avec, 1):
        if p["valeur"] != prec:
            rang, prec = k, p["valeur"]
        p["rang"] = rang
    for p in perfs:
        p.setdefault("rang", None)
    return avec + [p for p in perfs if p.get("valeur") is None]


def repartir_poules(equipes, nb_poules, rng=None):
    """Tirage : têtes de série réparties une par poule, puis les autres équipes au hasard (serpentin équilibré)."""
    rng = rng or random.SystemRandom()
    nb = max(1, min(nb_poules, max(1, len(equipes))))
    noms = [chr(65 + i) for i in range(nb)]
    tetes = [e for e in equipes if e.get("tete_serie")]
    autres = [e for e in equipes if not e.get("tete_serie")]
    rng.shuffle(tetes)
    rng.shuffle(autres)
    out = {}
    tailles = {p: 0 for p in noms}
    for k, e in enumerate(tetes):
        p = noms[k % nb]
        out[e["id"]] = p
        tailles[p] += 1
    for e in autres:
        p = min(noms, key=lambda x: (tailles[x], rng.random()))
        out[e["id"]] = p
        tailles[p] += 1
    return out


def tableau_elimination(ids_ordre):
    """Premier tour d'une coupe : [(a, b|None)] ; exempts (None) donnés aux premiers (têtes de série)."""
    n = len(ids_ordre)
    if n < 2:
        return []
    taille = 2
    while taille < n:
        taille *= 2
    exempts = taille - n
    eq = list(ids_ordre)
    paires = []
    for e in eq[:exempts]:
        paires.append((e, None))
    reste = eq[exempts:]
    for i in range(0, len(reste), 2):
        paires.append((reste[i], reste[i + 1]))
    return paires


def nom_tour(nb_equipes):
    return TOURS_ELIM.get(nb_equipes, f"Tour à {nb_equipes} équipes")


# ------------------------------------------------------------------ module
def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config
    H.schema(SCHEMA)
    H.DROITS["sport"] = {"admin", "directeur", "secretaire", "enseignant", "responsable", "chef_service", "cp", "agent"}
    U = getattr(H, "uascep", None)
    TYPES = {"sport_calendrier": "Sport scolaire : calendrier des rencontres", "sport_feuille_match": "Sport scolaire : feuille de match",
             "sport_classement": "Sport scolaire : classement", "sport_resultats": "Sport scolaire : résultats et qualifiés",
             "sport_palmares": "Sport scolaire : palmarès de la saison", "sport_diplome": "Sport scolaire : diplôme",
             "sport_licence": "Sport scolaire : carte de licence", "reg_sport_licences": "Sport scolaire : registre des licences",
             "reg_sport_officiels": "Sport scolaire : arbitres et officiels", "reg_sport_sites": "Sport scolaire : sites et terrains",
             "reg_sport_licences_fiche": "Sport scolaire : carte de licence"}
    R.types_documents(TYPES)

    def parametres():
        p = {r["cle"]: r["valeur"] for r in q("SELECT * FROM sport_parametres")}
        bornes = []
        for nom, a, b in CATEGORIES_DEF:
            try:
                a2, b2 = (int(x) for x in (p.get("cat_" + nom) or f"{a}-{b}").split("-"))
            except ValueError:
                a2, b2 = a, b
            bornes.append((nom, a2, b2))
        return {"bornes": bornes}

    def saison_de():
        v = (request.values.get("saison") or "").strip()
        return v if re.fullmatch(r"\d{4}-\d{4}", v) else config.ANNEE_ACTIVE

    def portee():
        return R.cle_portee("structure")

    def niveaux_vis():
        return U.niveaux_visibles() if U else ["ECOLE"]

    def niveaux_ecr():
        if not g.get("user"):
            return []
        return U.niveaux_ecriture() if U else (["ECOLE"] if g.user["role"] in ("admin", "fondateur", "directeur") else [])

    def entites(niveau):
        return U.entites(niveau) if U else [(str(H.eco()), config.ECOLE.get("nom") or "École", {})]

    NIV_LIB = U.NIV_LIB if U else {"ECOLE": "École"}
    DISCIPLINES = U.DISCIPLINES if U else ["Football"]
    CATEGORIES = (U.CATEGORIES if U else []) or ["Toutes catégories"]

    # ---- groupe (onglets) et registres communs
    G = R.Groupe(app, H, "sport", "Sport scolaire (UASCEP)", "sport", ico="trophee",
                 ecriture_roles={"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp"},
                 sous_titre="Licences, compétitions de l'école à la DDEMP, calendriers, feuilles de match, classements, performances, records, palmarès et diplômes",
                 listes={"disciplines": DISCIPLINES, "categories": [c for c, _a, _b in CATEGORIES_DEF] + ["Toutes catégories"],
                         "aptitudes": APTITUDES, "sexe": ["M", "F"], "cours": COURS,
                         "qualifs": ["Arbitre", "Arbitre assistant", "Juge", "Chronométreur", "Commissaire", "Délégué", "Membre du jury", "Secouriste"],
                         "types_site": ["Terrain de football", "Terrain de handball", "Terrain de volleyball", "Terrain de basketball", "Piste d'athlétisme",
                                        "Aire de saut", "Salle", "Espace polyvalent", "Autre"],
                         "etat_site": ["Bon", "Moyen", "Mauvais", "À aménager"]},
                 onglets_avant=[("sport_accueil", "Accueil", {}), ("sport_competitions", "Compétitions", {})])

    def apres_licence(rid):
        x = q("SELECT * FROM reg_sport_licences WHERE id=?", (rid,), un=True)
        if not x:
            return
        maj = {}
        if not (x["categorie"] or "").strip() and x["date_naissance"]:
            maj["categorie"] = categorie_age(x["date_naissance"][:4], x["annee"] or config.ANNEE_ACTIVE, parametres()["bornes"])
        if not (x["numero"] or "").strip():
            # spec commune : LIC-<AA>-<5 derniers caractères de la clé de l'école>-<n° d'ordre sur 4 chiffres>
            cle = (str(H.eco()) if not R.juridiction() else (x["ecole"] or "CS"))
            cle = re.sub(r"[^A-Za-z0-9]", "", cle)[-5:].upper() or "X"
            n = q("SELECT COUNT(*) n FROM reg_sport_licences WHERE portee=? AND annee=? AND COALESCE(ecole,'')=COALESCE(?, '') AND id<=?",
                  (x["portee"], x["annee"], x["ecole"], rid), un=True)["n"]
            maj["numero"] = f"LIC-{(x['annee'] or config.ANNEE_ACTIVE)[2:4]}-{cle}-{n:04d}"
        if maj:
            ex("UPDATE reg_sport_licences SET " + ", ".join(f"{k}=?" for k in maj) + " WHERE id=?", tuple(maj.values()) + (rid,))

    def age_licence(x):
        a = (x.get("date_naissance") or "")[:4]
        return {"Âge (saison)": (int((x.get("annee") or config.ANNEE_ACTIVE)[:4]) - int(a)) if a.isdigit() else ""}

    def fiche_licence(x):
        r = G.registres["licences"]
        titre, corps, _s = R.fiche_simple(G, r, x, "Carte de licence sportive scolaire")
        return titre, corps, sigs_ecole(["S", "P"]) + [R.signature_autorite("Visa du Directeur / de l'autorité")]

    def entite_licence(x):
        return ("ECOLE", x.get("ecole") or config.ECOLE.get("nom") or "")

    G.registre("licences", "Licences", [
        ("numero", "N° de licence", "texte"), ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"), ("sexe", "Sexe", "choix:sexe"),
        ("date_naissance", "Date de naissance", "date"), ("lieu_naissance", "Lieu de naissance", "texte"), ("cours", "Cours", "choix:cours"),
        ("categorie", "Catégorie", "liste:categories"), ("disciplines", "Disciplines", "multi:disciplines"), ("aptitude", "Aptitude médicale", "choix:aptitudes"),
        ("date_visite", "Date de la visite médicale", "date"), ("parent", "Parent / tuteur", "texte"), ("contact", "Contact du parent", "texte"),
        ("observations", "Observations", "long"), ("ecole", "École", "ecole"), ("classe", "Classe", "classe"), ("medecin", "Médecin / infirmier", "texte")],
        unite="licence", oblig="nom", ordre="ecole, classe, nom, prenoms", portee="structure", feuille="Licences", onglet="Licences des élèves",
        doc="Registre des licences sportives scolaires", calcul=age_licence, apres_enregistrer=apres_licence, fiche=fiche_licence, prefixe=entite_licence,
        filtres=("categorie", "aptitude"), colonnes=("numero", "nom", "prenoms", "sexe", "date_naissance", "cours", "categorie", "ecole", "classe",
                                                   "disciplines", "aptitude"),
        aide="N° et catégorie calculés automatiquement s'ils sont laissés vides (catégorie d'après l'âge au 31 décembre de la 1re année de la saison, "
             "voir Paramètres). L'aptitude médicale est reprise des visites médicales (module Santé).")
    G.registre("officiels", "Arbitres, juges et officiels", [
        ("nom", "Nom et prénoms", "texte"), ("qualite", "Qualité", "liste:qualifs"), ("discipline", "Discipline", "liste:disciplines"),
        ("ecole", "École / structure", "texte"), ("contact", "Contact", "texte"), ("niveau", "Niveau d'intervention", "texte"),
        ("observations", "Observations", "long")], unite="officiel", oblig="nom", ordre="discipline, nom", portee="structure",
        feuille="Officiels", doc="Liste des arbitres, juges et officiels", par_annee=True)
    G.registre("sites", "Sites et terrains", [
        ("nom", "Site / terrain", "texte"), ("type", "Type", "liste:types_site"), ("lieu", "Localité", "texte"), ("ecole", "École de rattachement", "texte"),
        ("etat", "État", "choix:etat_site"), ("capacite", "Capacité (spectateurs)", "entier"), ("equipements", "Équipements (buts, filets, vestiaires…)", "long"),
        ("contact", "Personne à contacter", "texte"), ("observations", "Observations", "long")], unite="site", oblig="nom", ordre="nom",
        portee="structure", feuille="Sites", doc="Sites et terrains de sport", par_annee=False)
    G.page("sport_records", "Records")
    G.page("sport_palmares", "Palmarès")
    G.page("sport_parametres", "Paramètres")

    def sigs_ecole(roles):
        if not U:
            return []
        try:
            if R.juridiction() and not g.get("ecole"):
                return []
            return U.signataires_entite("ECOLE", str(H.eco()), roles)
        except Exception:  # noqa: BLE001
            return []

    # ---- compétitions
    def competition(cid):
        c = q("SELECT * FROM sport_competitions WHERE id=? AND portee=?", (cid, portee()), un=True)
        if not c or c["niveau"] not in niveaux_vis():
            abort(404)
        return dict(c)

    def peut_ecrire_c(c):
        return c["niveau"] in niveaux_ecr()

    def exiger_c(c):
        if not peut_ecrire_c(c):
            abort(403)

    def equipes(cid):
        return [dict(e) for e in q("SELECT * FROM sport_equipes WHERE competition_id=? ORDER BY poule, nom", (cid,))]

    def matchs(cid):
        return [dict(m) for m in q("SELECT * FROM sport_matchs WHERE competition_id=? ORDER BY CASE phase WHEN 'poule' THEN 0 ELSE 1 END, ordre, date, heure, id", (cid,))]

    def perfs(cid):
        return [dict(p) for p in q("SELECT * FROM sport_perfs WHERE competition_id=? ORDER BY epreuve, sexe, categorie, id", (cid,))]

    def pts_c(c):
        return (c["pts_victoire"] if c["pts_victoire"] is not None else 3, c["pts_nul"] if c["pts_nul"] is not None else 1,
                c["pts_defaite"] or 0)

    def classements(c):
        """{poule: [lignes]} (championnat : une seule poule « » )."""
        eqs, ms = equipes(c["id"]), [m for m in matchs(c["id"]) if (m["phase"] or "poule") == "poule"]
        out = {}
        poules = sorted({e["poule"] or "" for e in eqs})
        for p in poules:
            out[p] = classement([e for e in eqs if (e["poule"] or "") == p], [m for m in ms if (m["poule"] or "") == p], pts_c(c), c["score_forfait"] or 3)
        return out

    def phase_finale(c):
        """Tours de la phase à élimination : [(tour, [matchs])] dans l'ordre."""
        ms = [m for m in matchs(c["id"]) if m["phase"] == "elimination"]
        tours = []
        for m in ms:
            if not tours or tours[-1][0] != m["tour"]:
                if m["tour"] in [t for t, _ in tours]:
                    next(x for t, x in tours if t == m["tour"]).append(m)
                    continue
                tours.append((m["tour"], [m]))
            else:
                tours[-1][1].append(m)
        return tours

    def classement_final(c):
        """[(rang, nom équipe / athlète, école, détail)] du podium et au-delà selon la formule."""
        eqs = {e["id"]: e for e in equipes(c["id"])}
        f = c["formule"]
        if f in ("championnat", "championnat_ar"):
            cl = classements(c)
            lignes = next(iter(cl.values()), []) if cl else []
            return [(l["rang"], l["nom"], l["ecole"], f"{l['pts']} pts · {l['g']} V {l['n']} N {l['p']} D · {l['bp']}-{l['bc']}") for l in lignes]
        if f in ("poules", "elimination"):
            tours = phase_finale(c)
            fin = next((ms for t, ms in tours if t == "Finale"), [])
            petite = next((ms for t, ms in tours if t == "Match pour la 3e place"), [])
            out = []
            if fin:
                m = fin[0]
                w = vainqueur(m, c["score_forfait"] or 3)
                if w:
                    l = m["equipe_b"] if w == m["equipe_a"] else m["equipe_a"]
                    sa, sb, _j = resultat_match(m, c["score_forfait"] or 3)
                    sc = f"Finale : {sa}-{sb}" + (f" (t.a.b. {m['tab_a']}-{m['tab_b']})" if m["tab_a"] is not None and sa == sb else "")
                    out += [(1, eqs[w]["nom"], eqs[w]["ecole"] or "", sc), (2, eqs[l]["nom"], eqs[l]["ecole"] or "", sc)]
            if petite:
                m = petite[0]
                w = vainqueur(m, c["score_forfait"] or 3)
                if w:
                    l = m["equipe_b"] if w == m["equipe_a"] else m["equipe_a"]
                    out += [(3, eqs[w]["nom"], eqs[w]["ecole"] or "", "Match pour la 3e place"), (4, eqs[l]["nom"], eqs[l]["ecole"] or "", "")]
            elif out:
                demi = next((ms for t, ms in tours if t == "Demi-finales"), [])
                for m in demi:
                    w = vainqueur(m, c["score_forfait"] or 3)
                    if w:
                        l = m["equipe_b"] if w == m["equipe_a"] else m["equipe_a"]
                        if l in eqs:
                            out.append((3, eqs[l]["nom"], eqs[l]["ecole"] or "", "Demi-finaliste"))
            return out
        # performances / jury : par épreuve, voir resultats_perfs
        return []

    def resultats_perfs(c):
        """{(épreuve, sexe, catégorie): [perfs classées]}"""
        out = {}
        for p in perfs(c["id"]):
            out.setdefault((p["epreuve"], p["sexe"] or "", p["categorie"] or ""), []).append(p)
        return {k: classer_perfs(v, EPREUVES.get(k[0], ("pts", "asc" if c["formule"] == "performances" else "desc"))[1]) for k, v in sorted(out.items())}

    def records():
        """Meilleure performance par épreuve / sexe / catégorie, toutes saisons (portée du compte)."""
        best = {}
        for p in q("SELECT p.*, c.saison, c.intitule, c.niveau, c.entite_lib FROM sport_perfs p JOIN sport_competitions c ON c.id=p.competition_id "
                   "WHERE c.portee=? AND p.valeur IS NOT NULL", (portee(),)):
            p = dict(p)
            k = (p["epreuve"], p["sexe"] or "", p["categorie"] or "")
            sens = EPREUVES.get(p["epreuve"], ("", "desc"))[1]
            b = best.get(k)
            if b is None or (p["valeur"] < b["valeur"] if sens == "asc" else p["valeur"] > b["valeur"]):
                best[k] = p
        return dict(sorted(best.items()))

    def est_record(p, rec):
        b = rec.get((p["epreuve"], p["sexe"] or "", p["categorie"] or ""))
        return b is not None and b["id"] == p["id"]

    def lib_eq(eqs, i):
        e = eqs.get(i)
        return e["nom"] if e else "Exempt"

    def podium(c):
        if c["formule"] in ("performances", "jury"):
            out = []
            for (ep, sx, ca), ps in resultats_perfs(c).items():
                for p in ps:
                    if p["rang"] and p["rang"] <= 3:
                        out.append((p["rang"], f"{p['nom']} {p['prenoms'] or ''}".strip(), p["ecole"] or "", f"{ep} {sx} {ca} — {p['performance'] or ''}".strip()))
            return out
        return [x for x in classement_final(c) if x[0] <= 3]

    def qualifies(c):
        n = c["qualifies_sup"] or 0
        if c["formule"] in ("performances", "jury"):
            out = []
            for (ep, sx, ca), ps in resultats_perfs(c).items():
                out += [(p["rang"], f"{p['nom']} {p['prenoms'] or ''}".strip(), p["ecole"] or "", f"{ep} {sx} {ca}") for p in ps if p["rang"] and p["rang"] <= n]
            return out
        return [x for x in classement_final(c) if x[0] <= n]

    def publier_uascep(c):
        """Résultats de la compétition -> journal de la saison du bureau UASCEP de l'entité (rapport de fin de saison)."""
        if not U:
            return False
        eqs = equipes(c["id"])
        ecoles = len({e["ecole"] or e["nom"] for e in eqs}) if eqs else len({p["ecole"] for p in perfs(c["id"]) if p["ecole"]})
        pg = sum(e["effectif_g"] or 0 for e in eqs)
        pf = sum(e["effectif_f"] or 0 for e in eqs)
        if c["formule"] in ("performances", "jury"):
            ps = perfs(c["id"])
            pg = pg or sum(1 for p in ps if (p["sexe"] or "") == "M")
            pf = pf or sum(1 for p in ps if (p["sexe"] or "") == "F")
        res = "; ".join(f"{r}e {n}" + (f" ({e})" if e and e != n else "") + (f" — {d}" if d and c["formule"] in ("performances", "jury") else "")
                        for r, n, e, d in podium(c))
        qual = "; ".join(f"{n}" + (f" ({e})" if e and e != n else "") for _r, n, e, _d in qualifies(c))
        U.publier_activite(c["niveau"], c["entite"], c["entite_lib"] or c["entite"], f"sport:{c['id']}", {
            "date": c["date_debut"] or "", "date_fin": c["date_fin"] or "", "discipline": c["discipline"] or "", "categorie": c["categorie"] or "",
            "genre": c["genre"] or "", "phase": "Finale" if c["formule"] in ("poules", "elimination") else "Compétition culturelle" if c["formule"] == "jury" else "Poules",
            "lieu": c["lieu"] or "", "ecoles": ecoles, "equipes": len(eqs), "pg": pg, "pf": pf, "resultats": res, "qualifies": qual,
            "intitule": c["intitule"], "statut": "Réalisée" if c["statut"] == "Terminée" else "Prévue",
            "distinctions": ""}, c["saison"])
        return True

    # ---- pages
    @app.route("/sport")
    @H.connexion_requise("sport")
    def sport_accueil():
        saison = saison_de()
        cs = [dict(x) for x in q("SELECT * FROM sport_competitions WHERE portee=? AND saison=? ORDER BY date_debut, intitule", (portee(), saison))
              if x["niveau"] in niveaux_vis()]
        lic = q("SELECT COUNT(*) n, SUM(sexe='M') g, SUM(sexe='F') f, SUM(aptitude='Apte' OR aptitude='Apte avec réserve') aptes FROM reg_sport_licences "
                "WHERE portee=? AND annee=?", (portee(), saison), un=True)
        par_cat = q("SELECT COALESCE(categorie,'—') cat, COUNT(*) n, SUM(sexe='F') f FROM reg_sport_licences WHERE portee=? AND annee=? GROUP BY cat", (portee(), saison))
        par_disc = {}
        for x in q("SELECT disciplines FROM reg_sport_licences WHERE portee=? AND annee=?", (portee(), saison)):
            for d in (x["disciplines"] or "").split(", "):
                if d:
                    par_disc[d] = par_disc.get(d, 0) + 1
        nb_m = q("SELECT COUNT(*) n, SUM(score_a IS NOT NULL OR COALESCE(forfait,'')<>'') joues FROM sport_matchs WHERE competition_id IN "
                 "(SELECT id FROM sport_competitions WHERE portee=? AND saison=?)", (portee(), saison), un=True)
        return render_template("sport.html", vue="accueil", G=G, saison=saison, saisons=R.annees_proposees([saison]), cs=cs, lic=lic,
                               par_cat=par_cat, par_disc=sorted(par_disc.items(), key=lambda x: -x[1]), nb_m=nb_m, NIV_LIB=NIV_LIB,
                               FORMULE_LIB=FORMULE_LIB, podium=podium, jj=R.jjmmaaaa)

    @app.route("/sport/competitions", methods=["GET", "POST"])
    @H.connexion_requise("sport")
    def sport_competitions():
        saison = saison_de()
        if request.method == "POST":
            f = request.form
            cid = f.get("id", type=int) or 0
            niveau = f.get("niveau") or "ECOLE"
            if niveau not in niveaux_ecr():
                abort(403)
            ents = {k: l for k, l, _i in entites(niveau)}
            entite = f.get("entite") or (next(iter(ents)) if ents else "")
            d = {"niveau": niveau, "entite": entite, "entite_lib": ents.get(entite, entite), "intitule": (f.get("intitule") or "").strip()[:200],
                 "discipline": (f.get("discipline") or "").strip()[:80], "categorie": (f.get("categorie") or "").strip()[:60],
                 "genre": f.get("genre") if f.get("genre") in GENRES else "", "formule": f.get("formule") if f.get("formule") in FORMULE_LIB else "championnat",
                 "nb_poules": max(1, min(16, f.get("nb_poules", type=int) or 1)), "qualifies_poule": max(1, min(8, f.get("qualifies_poule", type=int) or 2)),
                 "qualifies_sup": max(0, min(16, f.get("qualifies_sup", type=int) or 0)),
                 "pts_victoire": f.get("pts_victoire", type=int) if f.get("pts_victoire") not in (None, "") else 3,
                 "pts_nul": f.get("pts_nul", type=int) if f.get("pts_nul") not in (None, "") else 1,
                 "pts_defaite": f.get("pts_defaite", type=int) or 0, "score_forfait": f.get("score_forfait", type=int) or 3,
                 "date_debut": R.iso(f.get("date_debut")), "date_fin": R.iso(f.get("date_fin")), "lieu": (f.get("lieu") or "").strip()[:200],
                 "organisateur": (f.get("organisateur") or "").strip()[:200], "statut": f.get("statut") if f.get("statut") in STATUTS else "Programmée", "reglement": (f.get("reglement") or "").strip()[:4000],
                 "observations": (f.get("observations") or "").strip()[:2000]}
            if not d["intitule"]:
                d["intitule"] = " ".join(x for x in (d["discipline"], d["categorie"], d["genre"]) if x) or "Compétition"
            if not d["discipline"]:
                flash("Choisissez la discipline.", "danger")
                return redirect(url_for("sport_competitions", saison=saison))
            ks = list(d)
            if cid:
                c = competition(cid)
                exiger_c(c)
                ex("UPDATE sport_competitions SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), cid))
            else:
                cid = ex("INSERT INTO sport_competitions (portee, saison, " + ", ".join(ks) + ", cree_le, maj) VALUES (?,?," + ",".join("?" * len(ks)) + ",?,?)",
                         (portee(), saison) + tuple(d[k] for k in ks) + (H.maintenant(), H.maintenant()))
            c = competition(cid)
            if c["statut"] == "Terminée":
                publier_uascep(c)
            H.journal("sport_competition", f"{cid} {d['intitule']}")
            flash("Compétition enregistrée.", "success")
            return redirect(url_for("sport_competition", cid=cid))
        niveau = request.args.get("niveau") or ""
        cs = [dict(x) for x in q("SELECT * FROM sport_competitions WHERE portee=? AND saison=? ORDER BY niveau, date_debut, intitule", (portee(), saison))
              if x["niveau"] in niveaux_vis() and (not niveau or x["niveau"] == niveau)]
        edit = competition(request.args.get("modifier", type=int)) if request.args.get("modifier", type=int) else None
        nivs = [(n, NIV_LIB[n]) for n in niveaux_vis()]
        return render_template("sport.html", vue="competitions", G=G, saison=saison, saisons=R.annees_proposees([saison]), cs=cs, edit=edit,
                               niveaux=nivs, niveaux_ecr=niveaux_ecr(), ents={n: entites(n) for n, _l in nivs}, FORMULES=FORMULES, STATUTS=STATUTS,
                               GENRES=GENRES, DISCIPLINES=DISCIPLINES, CATEGORIES=[c for c, _a, _b in CATEGORIES_DEF] + ["Toutes catégories"],
                               NIV_LIB=NIV_LIB, FORMULE_LIB=FORMULE_LIB, niveau=niveau, jj=R.jjmmaaaa)

    @app.route("/sport/competition/<int:cid>/supprimer", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_competition_supprimer(cid):
        c = competition(cid)
        exiger_c(c)
        ex("DELETE FROM sport_competitions WHERE id=?", (cid,))
        H.journal("sport_competition_supprimee", c["intitule"])
        flash("Compétition supprimée.", "success")
        return redirect(url_for("sport_competitions", saison=c["saison"]))

    @app.route("/sport/competition/<int:cid>")
    @H.connexion_requise("sport")
    def sport_competition(cid):
        c = competition(cid)
        f = c["formule"]
        ind = f in ("performances", "jury")
        onglet = request.args.get("onglet") or ("perfs" if ind else "equipes")
        eqs = equipes(cid)
        ms = matchs(cid)
        eqd = {e["id"]: e for e in eqs}
        edit_m = next((m for m in ms if m["id"] == request.args.get("match", type=int)), None)
        edit_e = next((e for e in eqs if e["id"] == request.args.get("equipe", type=int)), None)
        edit_p = None
        if request.args.get("perf", type=int):
            edit_p = q("SELECT * FROM sport_perfs WHERE id=? AND competition_id=?", (request.args.get("perf", type=int), cid), un=True)
        rec = records() if ind else {}
        sup = NIVEAU_SUP.get(c["niveau"])
        cibles = [dict(x) for x in q("SELECT * FROM sport_competitions WHERE portee=? AND saison=? AND niveau=? AND id<>?",
                                     (portee(), c["saison"], sup or "", cid))] if sup and sup in niveaux_vis() else []
        bas = [dict(x) for x in q("SELECT * FROM sport_competitions WHERE portee=? AND saison=? AND niveau=? AND discipline=? AND id<>?",
                                  (portee(), c["saison"], next((k for k, v in NIVEAU_SUP.items() if v == c["niveau"]), ""), c["discipline"] or "", cid))]
        engagements = []
        if U and not ind:
            b = U.bureau_actif(c["niveau"], c["entite"])
            if b:
                engagements = [dict(x) for x in q("SELECT * FROM uascep_engagements WHERE bureau_id=? AND saison=? AND (discipline=? OR ?='')",
                                                  (b["id"], c["saison"], c["discipline"] or "", c["discipline"] or ""))]
        return render_template("sport.html", vue="competition", G=G, c=c, onglet=onglet, eqs=eqs, eqd=eqd, ms=ms, edit_m=edit_m, edit_e=edit_e,
                               edit_p=dict(edit_p) if edit_p else None, cl=classements(c) if not ind else {}, tours=phase_finale(c) if not ind else [],
                               final=classement_final(c) if not ind else [], rp=resultats_perfs(c) if ind else {}, rec=rec, est_record=est_record,
                               podium=podium(c), qual=qualifies(c), peut_c=peut_ecrire_c(c), NIV_LIB=NIV_LIB, FORMULE_LIB=FORMULE_LIB, STATUTS=STATUTS,
                               EPREUVES=EPREUVES, lib_eq=lambda i: lib_eq(eqd, i), res=lambda m: resultat_match(m, c["score_forfait"] or 3),
                               cibles=cibles, bas=bas, engagements=engagements, ind=ind, jj=R.jjmmaaaa,
                               tirages=q("SELECT * FROM sport_tirages WHERE competition_id=? ORDER BY id DESC LIMIT 5", (cid,)),
                               CATEGORIES=[x for x, _a, _b in CATEGORIES_DEF])

    # ---- équipes
    @app.route("/sport/competition/<int:cid>/equipe/<int:eid>", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_equipe(cid, eid):
        c = competition(cid)
        exiger_c(c)
        f = request.form
        d = {"nom": (f.get("nom") or "").strip()[:150], "ecole": (f.get("ecole") or "").strip()[:150], "poule": (f.get("poule") or "").strip().upper()[:3],
             "tete_serie": 1 if f.get("tete_serie") else 0, "encadreur": (f.get("encadreur") or "").strip()[:150], "contact": (f.get("contact") or "").strip()[:60],
             "joueurs": (f.get("joueurs") or "").strip()[:4000], "effectif_g": R.nombre(f.get("effectif_g")), "effectif_f": R.nombre(f.get("effectif_f")),
             "capitaine": (f.get("capitaine") or "").strip()[:150], "origine": (f.get("origine") or "").strip()[:150]}
        if not d["nom"]:
            d["nom"] = d["ecole"]
        if not d["nom"]:
            flash("Nom de l'équipe obligatoire.", "danger")
            return redirect(url_for("sport_competition", cid=cid, onglet="equipes"))
        ks = list(d)
        if eid:
            ex("UPDATE sport_equipes SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=? AND competition_id=?", tuple(d[k] for k in ks) + (H.maintenant(), eid, cid))
        else:
            ex("INSERT INTO sport_equipes (competition_id, " + ", ".join(ks) + ", maj) VALUES (?," + ",".join("?" * len(ks)) + ",?)", (cid,) + tuple(d[k] for k in ks) + (H.maintenant(),))
        flash("Équipe enregistrée.", "success")
        return redirect(url_for("sport_competition", cid=cid, onglet="equipes"))

    @app.route("/sport/competition/<int:cid>/equipe/<int:eid>/supprimer", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_equipe_supprimer(cid, eid):
        c = competition(cid)
        exiger_c(c)
        ex("DELETE FROM sport_matchs WHERE competition_id=? AND (equipe_a=? OR equipe_b=?)", (cid, eid, eid))
        ex("DELETE FROM sport_equipes WHERE id=? AND competition_id=?", (eid, cid))
        flash("Équipe supprimée (et ses matchs).", "success")
        return redirect(url_for("sport_competition", cid=cid, onglet="equipes"))

    @app.route("/sport/competition/<int:cid>/equipes/importer", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_equipes_importer(cid):
        """Équipes depuis les fiches d'engagement de l'UASCEP, ou les qualifiés d'une compétition du niveau inférieur."""
        c = competition(cid)
        exiger_c(c)
        n = 0
        deja = {(e["nom"] or "").lower() for e in equipes(cid)}
        src = request.form.get("source") or ""
        if src == "engagements" and U:
            b = U.bureau_actif(c["niveau"], c["entite"])
            for x in (q("SELECT * FROM uascep_engagements WHERE bureau_id=? AND saison=?", (b["id"], c["saison"])) if b else []):
                if c["discipline"] and x["discipline"] and x["discipline"] != c["discipline"]:
                    continue
                nom = x["equipe"] or x["ecole"]
                if not nom or nom.lower() in deja:
                    continue
                ex("INSERT INTO sport_equipes (competition_id, nom, ecole, encadreur, contact, effectif_g, effectif_f, origine, maj) VALUES (?,?,?,?,?,?,?,?,?)",
                   (cid, nom, x["ecole"], x["encadreur"], x["contact"], x["jg"], x["jf"], "Fiche d'engagement", H.maintenant()))
                deja.add(nom.lower())
                n += 1
        elif src.startswith("competition:"):
            c2 = competition(int(src.split(":")[1]))
            noms = {nm for _r, nm, _e, _d in qualifies(c2)}
            for e in equipes(c2["id"]):
                if e["nom"] in noms and e["nom"].lower() not in deja:
                    ex("INSERT INTO sport_equipes (competition_id, nom, ecole, encadreur, contact, joueurs, effectif_g, effectif_f, origine, maj) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (cid, e["nom"], e["ecole"], e["encadreur"], e["contact"], e["joueurs"], e["effectif_g"], e["effectif_f"], f"Qualifié : {c2['intitule']}", H.maintenant()))
                    deja.add(e["nom"].lower())
                    n += 1
        flash(f"{n} équipe(s) ajoutée(s).", "success" if n else "warning")
        return redirect(url_for("sport_competition", cid=cid, onglet="equipes"))

    @app.route("/sport/competition/<int:cid>/qualifier", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_qualifier(cid):
        """Inscrit les qualifiés dans une compétition du niveau supérieur (équipes ou athlètes)."""
        c = competition(cid)
        cible = competition(request.form.get("cible", type=int) or 0)
        exiger_c(cible)
        n = 0
        if c["formule"] in ("performances", "jury"):
            for (ep, sx, ca), ps in resultats_perfs(c).items():
                for p in ps:
                    if p["rang"] and p["rang"] <= (c["qualifies_sup"] or 0):
                        if not q("SELECT 1 FROM sport_perfs WHERE competition_id=? AND epreuve=? AND nom=? AND COALESCE(prenoms,'')=?",
                                 (cible["id"], ep, p["nom"], p["prenoms"] or ""), un=True):
                            ex("INSERT INTO sport_perfs (competition_id, epreuve, nom, prenoms, sexe, categorie, ecole, licence, observations, maj) VALUES (?,?,?,?,?,?,?,?,?,?)",
                               (cible["id"], ep, p["nom"], p["prenoms"], p["sexe"], p["categorie"], p["ecole"], p["licence"], f"Qualifié(e) : {c['intitule']}", H.maintenant()))
                            n += 1
        else:
            noms = {nm for _r, nm, _e, _d in qualifies(c)}
            deja = {(e["nom"] or "").lower() for e in equipes(cible["id"])}
            for e in equipes(cid):
                if e["nom"] in noms and e["nom"].lower() not in deja:
                    ex("INSERT INTO sport_equipes (competition_id, nom, ecole, encadreur, contact, joueurs, effectif_g, effectif_f, origine, maj) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (cible["id"], e["nom"], e["ecole"], e["encadreur"], e["contact"], e["joueurs"], e["effectif_g"], e["effectif_f"], f"Qualifié : {c['intitule']}", H.maintenant()))
                    n += 1
        H.journal("sport_qualifies", f"{c['intitule']} -> {cible['intitule']} : {n}")
        flash(f"{n} qualifié(s) inscrit(s) dans « {cible['intitule']} ».", "success" if n else "warning")
        return redirect(url_for("sport_competition", cid=cible["id"]))

    # ---- tirage au sort et calendrier
    @app.route("/sport/competition/<int:cid>/tirage", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_tirage(cid):
        c = competition(cid)
        exiger_c(c)
        eqs = [e for e in equipes(cid) if not e["forfait_general"]]
        if len(eqs) < 2:
            flash("Il faut au moins deux équipes.", "warning")
            return redirect(url_for("sport_competition", cid=cid, onglet="equipes"))
        if q("SELECT 1 FROM sport_matchs WHERE competition_id=? AND (score_a IS NOT NULL OR COALESCE(forfait,'')<>'')", (cid,), un=True) and not request.form.get("forcer"):
            flash("Des résultats sont déjà saisis : cochez « refaire » pour recommencer le tirage (les matchs seront effacés).", "warning")
            return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))
        rng = random.Random(secrets.randbits(64))
        ex("DELETE FROM sport_matchs WHERE competition_id=?", (cid,))
        f = c["formule"]
        dd = c["date_debut"] or ""
        lignes = []
        if f in ("championnat", "championnat_ar", "poules"):
            nbp = 1 if f != "poules" else (c["nb_poules"] or 1)
            rep = repartir_poules(eqs, nbp, rng) if f == "poules" else {e["id"]: "" for e in eqs}
            for e in eqs:
                ex("UPDATE sport_equipes SET poule=? WHERE id=?", (rep[e["id"]], e["id"]))
            for p in sorted(set(rep.values())):
                ids = [e["id"] for e in eqs if rep[e["id"]] == p]
                rng.shuffle(ids)
                for k, (j, a, b) in enumerate(tour_robin(ids, f == "championnat_ar")):
                    ex("INSERT INTO sport_matchs (competition_id, phase, tour, poule, ordre, date, equipe_a, equipe_b, maj) VALUES (?,?,?,?,?,?,?,?,?)",
                       (cid, "poule", f"Journée {j}", p, j * 100 + k, dd, a, b, H.maintenant()))
            lignes = [f"{e['nom']} → poule {rep[e['id']]}" for e in eqs] if f == "poules" else [f"{len(eqs)} équipes, {len(eqs) - 1 + (len(eqs) % 2)} journée(s)"]
        else:
            tetes = [e["id"] for e in eqs if e["tete_serie"]]
            autres = [e["id"] for e in eqs if not e["tete_serie"]]
            rng.shuffle(tetes)
            rng.shuffle(autres)
            ordre = tetes + autres
            paires = tableau_elimination(ordre)
            nb = 2
            while nb < len(ordre):
                nb *= 2
            tour = nom_tour(nb)
            for k, (a, b) in enumerate(paires):
                ex("INSERT INTO sport_matchs (competition_id, phase, tour, ordre, date, equipe_a, equipe_b, forfait, maj) VALUES (?,?,?,?,?,?,?,?,?)",
                   (cid, "elimination", tour, 1000 + k, dd, a, b, "B" if b is None else None, H.maintenant()))
            nomd = {e["id"]: e["nom"] for e in eqs}
            lignes = [f"{nomd[a]} – {nomd.get(b, 'exempt')}" for a, b in paires]
        ex("INSERT INTO sport_tirages (competition_id, fait_le, fait_par, resultat) VALUES (?,?,?,?)",
           (cid, H.maintenant(), f"{g.user['nom'] if 'nom' in g.user.keys() else g.user['identifiant']}", "\n".join(lignes)))
        if c["statut"] == "Programmée":
            ex("UPDATE sport_competitions SET statut='En cours', maj=? WHERE id=?", (H.maintenant(), cid))
        H.journal("sport_tirage", c["intitule"])
        flash("Tirage au sort effectué et calendrier généré.", "success")
        return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))

    @app.route("/sport/competition/<int:cid>/phase-finale", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_phase_suivante(cid):
        """Poules terminées -> phase finale (1A-2B, 1B-2A…) ; tour d'élimination terminé -> tour suivant (+ match pour la 3e place)."""
        c = competition(cid)
        exiger_c(c)
        fs = c["score_forfait"] or 3
        tours = phase_finale(c)
        if not tours:
            if c["formule"] != "poules":
                flash("Faites d'abord le tirage au sort.", "warning")
                return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))
            ms = [m for m in matchs(cid) if m["phase"] == "poule"]
            if not ms or any(not resultat_match(m, fs)[2] for m in ms):
                flash("Tous les matchs de poule doivent être joués.", "warning")
                return redirect(url_for("sport_competition", cid=cid, onglet="classement"))
            cl = classements(c)
            k = c["qualifies_poule"] or 2
            poules = sorted(cl)
            qual = [[l["id"] for l in cl[p][:k]] for p in poules]
            paires = []
            if len(poules) == 1:
                lst = qual[0]
                paires = [(lst[i], lst[len(lst) - 1 - i]) for i in range(len(lst) // 2)]
            else:
                for i in range(0, len(poules) - 1, 2):
                    a, b = qual[i], qual[i + 1]
                    for r in range(k):
                        if r < len(a) and k - 1 - r < len(b):
                            paires.append((a[r], b[k - 1 - r]))
                if len(poules) % 2:
                    paires.append((qual[-1][0], qual[-1][1] if len(qual[-1]) > 1 else None))
            tour = nom_tour(2 * len(paires))
            for j, (a, b) in enumerate(paires):
                ex("INSERT INTO sport_matchs (competition_id, phase, tour, ordre, equipe_a, equipe_b, forfait, maj) VALUES (?,?,?,?,?,?,?,?)",
                   (cid, "elimination", tour, 2000 + j, a, b, "B" if b is None else None, H.maintenant()))
            flash(f"Phase finale créée : {tour}.", "success")
            return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))
        dernier, ms = tours[-1]
        if dernier in ("Finale", "Match pour la 3e place"):
            flash("La finale est déjà programmée.", "info")
            return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))
        gagnants = []
        for m in ms:
            w = vainqueur(m, fs)
            if w is None:
                flash("Tous les matchs du tour doivent avoir un vainqueur (saisissez les tirs au but en cas d'égalité).", "warning")
                return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))
            gagnants.append(w)
        base = max(m["ordre"] or 0 for m in ms) + 100
        tour = nom_tour(len(gagnants))
        for j in range(0, len(gagnants) - 1, 2):
            ex("INSERT INTO sport_matchs (competition_id, phase, tour, ordre, equipe_a, equipe_b, maj) VALUES (?,?,?,?,?,?,?)",
               (cid, "elimination", tour, base + j, gagnants[j], gagnants[j + 1], H.maintenant()))
        if tour == "Finale" and dernier == "Demi-finales":
            perdants = [m["equipe_b"] if vainqueur(m, fs) == m["equipe_a"] else m["equipe_a"] for m in ms]
            if len(perdants) == 2 and None not in perdants:
                ex("INSERT INTO sport_matchs (competition_id, phase, tour, ordre, equipe_a, equipe_b, maj) VALUES (?,?,?,?,?,?,?)",
                   (cid, "elimination", "Match pour la 3e place", base + 50, perdants[0], perdants[1], H.maintenant()))
        flash(f"{tour} programmé(e).", "success")
        return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))

    @app.route("/sport/competition/<int:cid>/match/<int:mid>", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_match(cid, mid):
        c = competition(cid)
        exiger_c(c)
        f = request.form
        ids = {e["id"] for e in equipes(cid)}
        d = {"date": R.iso(f.get("date")), "heure": (f.get("heure") or "")[:10], "terrain": (f.get("terrain") or "").strip()[:150],
             "score_a": R.nombre(f.get("score_a")), "score_b": R.nombre(f.get("score_b")), "tab_a": R.nombre(f.get("tab_a")), "tab_b": R.nombre(f.get("tab_b")),
             "forfait": f.get("forfait") if f.get("forfait") in ("A", "B", "AB") else None,
             "buteurs_a": (f.get("buteurs_a") or "").strip()[:1000], "buteurs_b": (f.get("buteurs_b") or "").strip()[:1000],
             "jaunes_a": R.nombre(f.get("jaunes_a")), "jaunes_b": R.nombre(f.get("jaunes_b")), "rouges_a": R.nombre(f.get("rouges_a")),
             "rouges_b": R.nombre(f.get("rouges_b")), "arbitre": (f.get("arbitre") or "").strip()[:150], "assesseurs": (f.get("assesseurs") or "").strip()[:300],
             "delegue": (f.get("delegue") or "").strip()[:150],
             "observations": (f.get("observations") or "").strip()[:2000]}
        if mid:
            m = q("SELECT * FROM sport_matchs WHERE id=? AND competition_id=?", (mid, cid), un=True)
            if not m:
                abort(404)
            ks = list(d)
            ex("UPDATE sport_matchs SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), mid))
        else:
            a, b = f.get("equipe_a", type=int), f.get("equipe_b", type=int)
            if a not in ids or b not in ids or a == b:
                flash("Choisissez deux équipes différentes.", "danger")
                return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))
            d.update(equipe_a=a, equipe_b=b, phase=f.get("phase") if f.get("phase") in ("poule", "elimination") else "poule",
                     tour=(f.get("tour") or "Rencontre").strip()[:60], poule=(f.get("poule") or "").strip().upper()[:3], ordre=9000)
            ks = list(d)
            ex("INSERT INTO sport_matchs (competition_id, " + ", ".join(ks) + ", maj) VALUES (?," + ",".join("?" * len(ks)) + ",?)", (cid,) + tuple(d[k] for k in ks) + (H.maintenant(),))
        if c["statut"] == "Programmée":
            ex("UPDATE sport_competitions SET statut='En cours', maj=? WHERE id=?", (H.maintenant(), cid))
        flash("Feuille de match enregistrée.", "success")
        return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))

    @app.route("/sport/competition/<int:cid>/match/<int:mid>/supprimer", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_match_supprimer(cid, mid):
        c = competition(cid)
        exiger_c(c)
        ex("DELETE FROM sport_matchs WHERE id=? AND competition_id=?", (mid, cid))
        flash("Match supprimé.", "success")
        return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))

    @app.route("/sport/competition/<int:cid>/calendrier/reinitialiser", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_calendrier_reinitialiser(cid):
        c = competition(cid)
        exiger_c(c)
        ex("DELETE FROM sport_matchs WHERE competition_id=?", (cid,))
        ex("UPDATE sport_equipes SET poule='' WHERE competition_id=?", (cid,))
        flash("Calendrier et résultats effacés.", "success")
        return redirect(url_for("sport_competition", cid=cid, onglet="calendrier"))

    # ---- performances (athlétisme, jeux, concours)
    @app.route("/sport/competition/<int:cid>/perf/<int:pid>", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_perf(cid, pid):
        c = competition(cid)
        exiger_c(c)
        f = request.form
        ep = (f.get("epreuve") or "").strip()[:80]
        unite = EPREUVES.get(ep, ("pts" if c["formule"] == "jury" else "s", ""))[0]
        d = {"epreuve": ep, "serie": (f.get("serie") or "").strip()[:30], "nom": (f.get("nom") or "").strip()[:120], "prenoms": (f.get("prenoms") or "").strip()[:120],
             "sexe": f.get("sexe") if f.get("sexe") in ("M", "F") else "", "categorie": (f.get("categorie") or c["categorie"] or "").strip()[:40],
             "ecole": (f.get("ecole") or "").strip()[:150], "licence": (f.get("licence") or "").strip()[:40], "performance": (f.get("performance") or "").strip()[:40],
             "observations": (f.get("observations") or "").strip()[:500]}
        d["valeur"] = valeur_perf(d["performance"], unite)
        if not d["epreuve"] or not d["nom"]:
            flash("Épreuve et nom obligatoires.", "danger")
            return redirect(url_for("sport_competition", cid=cid, onglet="perfs"))
        ks = list(d)
        if pid:
            ex("UPDATE sport_perfs SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=? AND competition_id=?", tuple(d[k] for k in ks) + (H.maintenant(), pid, cid))
        else:
            ex("INSERT INTO sport_perfs (competition_id, " + ", ".join(ks) + ", maj) VALUES (?," + ",".join("?" * len(ks)) + ",?)", (cid,) + tuple(d[k] for k in ks) + (H.maintenant(),))
        flash("Performance enregistrée.", "success")
        return redirect(url_for("sport_competition", cid=cid, onglet="perfs"))

    @app.route("/sport/competition/<int:cid>/perf/<int:pid>/supprimer", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_perf_supprimer(cid, pid):
        c = competition(cid)
        exiger_c(c)
        ex("DELETE FROM sport_perfs WHERE id=? AND competition_id=?", (pid, cid))
        flash("Performance supprimée.", "success")
        return redirect(url_for("sport_competition", cid=cid, onglet="perfs"))

    @app.route("/sport/competition/<int:cid>/perfs/licencies", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_perfs_licencies(cid):
        """Inscrit les licenciés (aptes) de la catégorie / du genre à une épreuve."""
        c = competition(cid)
        exiger_c(c)
        ep = (request.form.get("epreuve") or "").strip()[:80]
        if not ep:
            flash("Choisissez l'épreuve.", "warning")
            return redirect(url_for("sport_competition", cid=cid, onglet="perfs"))
        sx = {"Garçons": "M", "Filles": "F"}.get(c["genre"] or "")
        n = 0
        for x in q("SELECT * FROM reg_sport_licences WHERE portee=? AND annee=?", (portee(), c["saison"])):
            if sx and x["sexe"] != sx:
                continue
            if c["categorie"] and c["categorie"] != "Toutes catégories" and x["categorie"] and x["categorie"] != c["categorie"]:
                continue
            if (x["aptitude"] or "") in ("Inapte", "Inapte temporaire"):
                continue
            if q("SELECT 1 FROM sport_perfs WHERE competition_id=? AND epreuve=? AND licence=?", (cid, ep, x["numero"]), un=True):
                continue
            ex("INSERT INTO sport_perfs (competition_id, epreuve, nom, prenoms, sexe, categorie, ecole, licence, maj) VALUES (?,?,?,?,?,?,?,?,?)",
               (cid, ep, x["nom"], x["prenoms"], x["sexe"], x["categorie"], x["ecole"], x["numero"], H.maintenant()))
            n += 1
        flash(f"{n} licencié(e)(s) inscrit(e)(s) à l'épreuve « {ep} ».", "success" if n else "warning")
        return redirect(url_for("sport_competition", cid=cid, onglet="perfs"))

    @app.route("/sport/competition/<int:cid>/publier", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_publier(cid):
        c = competition(cid)
        exiger_c(c)
        if request.form.get("terminer"):
            ex("UPDATE sport_competitions SET statut='Terminée', maj=? WHERE id=?", (H.maintenant(), cid))
            c = competition(cid)
        ok = publier_uascep(c)
        flash("Résultats publiés dans le journal de la saison du bureau UASCEP (rapport de fin de saison)." if ok else "Module UASCEP indisponible.",
              "success" if ok else "warning")
        return redirect(url_for("sport_competition", cid=cid, onglet="resultats"))

    # ---- records, palmarès, paramètres
    @app.route("/sport/records")
    @H.connexion_requise("sport")
    def sport_records():
        return render_template("sport.html", vue="records", G=G, rec=records(), EPREUVES=EPREUVES, NIV_LIB=NIV_LIB, saison=saison_de(),
                               saisons=R.annees_proposees([saison_de()]))

    def palmares(saison):
        out = []
        for c in q("SELECT * FROM sport_competitions WHERE portee=? AND saison=? AND statut<>'Annulée' ORDER BY niveau, discipline, intitule", (portee(), saison)):
            c = dict(c)
            if c["niveau"] not in niveaux_vis():
                continue
            out.append((c, podium(c), qualifies(c)))
        return out

    @app.route("/sport/palmares")
    @H.connexion_requise("sport")
    def sport_palmares():
        saison = saison_de()
        return render_template("sport.html", vue="palmares", G=G, saison=saison, saisons=R.annees_proposees([saison]), pal=palmares(saison),
                               NIV_LIB=NIV_LIB, jj=R.jjmmaaaa)

    @app.route("/sport/parametres", methods=["GET", "POST"])
    @H.connexion_requise("sport")
    def sport_parametres():
        if request.method == "POST":
            if not G.peut_ecrire():
                abort(403)
            for nom, a, b in CATEGORIES_DEF:
                v = (request.form.get("cat_" + nom) or "").strip()
                if request.form.get("reinitialiser") or not re.fullmatch(r"\d{1,2}-\d{1,2}", v):
                    v = f"{a}-{b}"
                ex("INSERT INTO sport_parametres (cle, valeur) VALUES (?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", ("cat_" + nom, v))
            if request.form.get("recalculer"):
                for x in q("SELECT id, date_naissance, annee FROM reg_sport_licences WHERE portee=?", (portee(),)):
                    if x["date_naissance"]:
                        ex("UPDATE reg_sport_licences SET categorie=? WHERE id=?",
                           (categorie_age(x["date_naissance"][:4], x["annee"] or config.ANNEE_ACTIVE, parametres()["bornes"]), x["id"]))
            flash("Paramètres enregistrés.", "success")
            return redirect(url_for("sport_parametres"))
        return render_template("sport.html", vue="parametres", G=G, bornes=parametres()["bornes"], peut_c=G.peut_ecrire(), saison=saison_de(),
                               saisons=R.annees_proposees([saison_de()]))

    @app.route("/sport/licences/eleves", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_licences_eleves():
        """Crée les licences des élèves de l'école (classes choisies) ; catégories et numéros automatiques."""
        if not G.peut_ecrire() or (R.juridiction() and not g.get("ecole")):
            abort(403)
        saison = (request.form.get("annee") or config.ANNEE_ACTIVE)
        classes = request.form.getlist("classes")
        rows = q("SELECT e.*, c.nom classe, c.niveau FROM eleves e JOIN classes c ON c.id=e.classe_id AND c.ecole_id=? WHERE e.statut='inscrit'"
                 + (" AND c.nom IN (" + ",".join("?" * len(classes)) + ")" if classes else "") + " ORDER BY c.niveau, c.nom, e.nom",
                 (H.eco(),) + tuple(classes))
        n = 0
        ecole = config.ECOLE.get("nom") or ""
        for e in rows:
            if q("SELECT 1 FROM reg_sport_licences WHERE portee=? AND annee=? AND nom=? AND prenoms=? AND COALESCE(date_naissance,'')=COALESCE(?, '')",
                 (portee(), saison, e["nom"], e["prenoms"], e["date_naissance"]), un=True):
                continue
            rid = ex("INSERT INTO reg_sport_licences (portee, annee, nom, prenoms, sexe, date_naissance, lieu_naissance, cours, ecole, classe, parent, contact, "
                     "aptitude, cree_le, cree_par, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (portee(), saison, e["nom"], e["prenoms"], (e["sexe"] or "").upper()[:1], e["date_naissance"], e["lieu_naissance"] or "",
                      e["niveau"] if e["niveau"] in COURS else ("Maternelle" if "atern" in (e["niveau"] or "") else ""), ecole, e["classe"],
                      e["parent_nom"] or "", e["parent_telephone"] or "", "Non examiné", H.maintenant(), g.user["id"], H.maintenant()))
            apres_licence(rid)
            n += 1
        flash(f"{n} licence(s) créée(s).", "success" if n else "warning")
        return redirect(url_for("reg_page", gcle="sport", rcle="licences", annee=saison))

    def aptitude_depuis_sante(nom, prenoms, aptitude, date_v, medecin="", ecole="", saison=""):
        """Appelé par le module Santé : reporte l'aptitude sportive sur la licence de l'élève (même école, même saison,
        mêmes nom et prénoms sans accents ni casse)."""
        if aptitude not in APTITUDES:
            return 0
        n = 0
        sql, args = "SELECT id, nom, prenoms, ecole FROM reg_sport_licences WHERE portee=?", [portee()]
        if saison:
            sql += " AND annee=?"
            args.append(saison)
        for x in q(sql, tuple(args)):
            if R._norm(x["nom"]).strip() != R._norm(nom).strip() or R._norm(x["prenoms"]).strip() != R._norm(prenoms).strip():
                continue
            if ecole and R.juridiction() and x["ecole"] and R._norm(x["ecole"]).strip() != R._norm(ecole).strip():
                continue
            ex("UPDATE reg_sport_licences SET aptitude=?, date_visite=?, medecin=COALESCE(NULLIF(?, ''), medecin), maj=? WHERE id=?",
               (aptitude, date_v or "", medecin or "", H.maintenant(), x["id"]))
            n += 1
        return n
    H.sport_aptitude = aptitude_depuis_sante

    # ---- documents PDF
    def sigs_c(c, roles=("S", "P", "V")):
        if not U:
            return [R.signature_autorite()]
        try:
            s = U.signataires_entite(c["niveau"], c["entite"], roles)
        except Exception:  # noqa: BLE001
            s = []
        return s or [R.signature_autorite()]

    def code_c(typ, c, extra, cle):
        return R.code_document(typ, f"{TYPES[typ]} — {c['intitule']} ({NIV_LIB.get(c['niveau'], c['niveau'])} : {c['entite_lib'] or c['entite']}, {c['saison']}){extra}", cle)

    def bandeau_c(c):
        return (c["niveau"], c["entite"], c["entite_lib"])

    def bandeau_compte():
        if not R.juridiction() or g.get("ecole"):
            return ("ECOLE", str(H.eco()), None)
        niv = "DDEMP" if config.EDITION == "ddemp" else "CS"
        e = entites(niv)
        return (niv, e[0][0], e[0][1]) if e else None

    G.bandeau = bandeau_compte

    def entete_c(c):
        return (f"{NIV_LIB.get(c['niveau'], c['niveau'])} : {c['entite_lib'] or c['entite']} · {c['discipline'] or ''} {c['categorie'] or ''} {c['genre'] or ''}"
                f" · {FORMULE_LIB.get(c['formule'], '')} · saison {c['saison']}").replace("  ", " ")

    @app.route("/sport/competition/<int:cid>/<doc>.pdf")
    @H.connexion_requise("sport")
    def sport_doc(cid, doc):
        from reportlab.platypus import Paragraph, Spacer
        c = competition(cid)
        st = R.styles()
        eqd = {e["id"]: e for e in equipes(cid)}
        L = R.largeur_utile(True)
        corps = []
        if doc == "calendrier":
            ms = matchs(cid)
            rows = [[m["tour"] or "", m["poule"] or "", R.jjmmaaaa(m["date"]), m["heure"] or "", m["terrain"] or "", lib_eq(eqd, m["equipe_a"]),
                     "–".join(str(x) for x in resultat_match(m, c["score_forfait"] or 3)[:2]) if resultat_match(m, c["score_forfait"] or 3)[2] else "… – …",
                     lib_eq(eqd, m["equipe_b"]), m["arbitre"] or ""] for m in ms]
            corps.append(R.tableau(["Tour", "Poule", "Date", "Heure", "Terrain", "Équipe A", "Score", "Équipe B", "Arbitre"], rows,
                                   [16, 7, 12, 8, 18, 28, 9, 28, 18], L))
            typ, titre, n = "sport_calendrier", "Calendrier des rencontres", len(ms)
            sigs = sigs_c(c, ("S", "P"))
        elif doc == "classement":
            for p, lignes in classements(c).items():
                if p:
                    corps.append(Paragraph(f"<b>Poule {R.esc(p)}</b>", st["h2"]))
                corps.append(R.tableau(["Rang", "Équipe", "École", "J", "G", "N", "P", "BP", "BC", "Diff.", "Pts", "Fair-play"],
                                       [[l["rang"], l["nom"], l["ecole"], l["j"], l["g"], l["n"], l["p"], l["bp"], l["bc"], l["diff"], l["pts"], l["fp"]] for l in lignes],
                                       [7, 30, 30, 6, 6, 6, 6, 7, 7, 7, 7, 9], L))
            for t, ms in phase_finale(c):
                corps.append(Paragraph(f"<b>{R.esc(t)}</b>", st["h2"]))
                corps.append(R.tableau(["Équipe A", "Score", "Équipe B", "Qualifié"],
                                       [[lib_eq(eqd, m["equipe_a"]), ("–".join(str(x) for x in resultat_match(m, c["score_forfait"] or 3)[:2])
                                         + (f" (t.a.b. {m['tab_a']}–{m['tab_b']})" if m["tab_a"] is not None else "")) if resultat_match(m, c["score_forfait"] or 3)[2] else "",
                                         lib_eq(eqd, m["equipe_b"]), lib_eq(eqd, vainqueur(m, c["score_forfait"] or 3)) if vainqueur(m, c["score_forfait"] or 3) else ""] for m in ms],
                                       [30, 14, 30, 30], L))
            for (ep, sx, ca), ps in resultats_perfs(c).items():
                corps.append(Paragraph(f"<b>{R.esc(ep)} {R.esc(sx)} {R.esc(ca)}</b>", st["h2"]))
                corps.append(R.tableau(["Rang", "Nom et prénoms", "École", "Série", "Performance", "Licence"],
                                       [[p["rang"] or "NC", f"{p['nom']} {p['prenoms'] or ''}", p["ecole"] or "", p["serie"] or "", p["performance"] or "", p["licence"] or ""] for p in ps],
                                       [8, 40, 34, 10, 16, 16], L))
            typ, titre, n = "sport_classement", "Classement", len(eqd)
            sigs = sigs_c(c, ("S", "P", "V"))
        elif doc == "resultats":
            pod = podium(c)
            corps.append(Paragraph("<b>Podium</b>", st["h2"]))
            corps.append(R.tableau(["Rang", "Équipe / athlète", "École", "Détail"], [list(x) for x in pod], [8, 40, 40, 50], L))
            corps.append(Paragraph(f"<b>Qualifié(s) pour le niveau supérieur</b> ({c['qualifies_sup'] or 0} par {'épreuve' if c['formule'] in ('performances', 'jury') else 'compétition'})", st["h2"]))
            corps.append(R.tableau(["Rang", "Équipe / athlète", "École", "Épreuve / détail"], [list(x) for x in qualifies(c)], [8, 40, 40, 50], L))
            typ, titre, n = "sport_resultats", "Résultats officiels et qualifiés", len(pod)
            sigs = sigs_c(c, ("S", "SG", "P", "V"))
        else:
            abort(404)
        code = code_c(typ, c, f" ({n} ligne(s))", f"sport:{doc}:{cid}:{c['maj'] or ''}:{n}:{max([m['maj'] or '' for m in matchs(cid)] or [''])}")
        return H.pdf_reponse(R.pdf_document(f"{titre.upper()} — {c['intitule']}", corps, sigs, code, True, entete_c(c), bandeau=bandeau_c(c)),
                             f"sport_{doc}_{cid}.pdf")

    @app.route("/sport/competition/<int:cid>/match/<int:mid>.pdf")
    @H.connexion_requise("sport")
    def sport_feuille_pdf(cid, mid):
        from reportlab.platypus import Paragraph, Spacer
        c = competition(cid)
        m = q("SELECT * FROM sport_matchs WHERE id=? AND competition_id=?", (mid, cid), un=True)
        if not m:
            abort(404)
        m = dict(m)
        eqd = {e["id"]: e for e in equipes(cid)}
        st = R.styles()
        L = R.largeur_utile(False)
        a, b = eqd.get(m["equipe_a"]) or {}, eqd.get(m["equipe_b"]) or {}
        sa, sb, joue = resultat_match(m, c["score_forfait"] or 3)
        corps = [R.tableau(["Rubrique", "Équipe A", "Équipe B"], [
            ["Équipe", a.get("nom", ""), b.get("nom", "Exempt")], ["École", a.get("ecole") or "", b.get("ecole") or ""],
            ["Encadreur", a.get("encadreur") or "", b.get("encadreur") or ""], ["Capitaine", a.get("capitaine") or "", b.get("capitaine") or ""],
            ["Score", sa if joue else "", sb if joue else ""], ["Tirs au but", m["tab_a"] if m["tab_a"] is not None else "", m["tab_b"] if m["tab_b"] is not None else ""],
            ["Buteurs / marqueurs", m["buteurs_a"] or "", m["buteurs_b"] or ""], ["Avertissements (jaunes)", m["jaunes_a"] or "", m["jaunes_b"] or ""],
            ["Exclusions (rouges)", m["rouges_a"] or "", m["rouges_b"] or ""], ["Joueurs", a.get("joueurs") or "", b.get("joueurs") or ""]], [1.3, 2, 2], L),
            Spacer(1, 4),
            Paragraph(f"<b>{R.esc(m['tour'] or '')}</b>{' · poule ' + R.esc(m['poule']) if m['poule'] else ''} · date : {R.jjmmaaaa(m['date']) or '……'} · "
                      f"heure : {R.esc(m['heure'] or '……')} · terrain : {R.esc(m['terrain'] or '……')} · arbitre : {R.esc(m['arbitre'] or '……')}"
                      f"{' · assistants : ' + R.esc(m['assesseurs']) if m['assesseurs'] else ''}{' · délégué : ' + R.esc(m['delegue']) if m['delegue'] else ''}", st["p"])]
        if m["forfait"]:
            corps.append(Paragraph(f"<b>Forfait</b> : {'équipe A' if m['forfait'] == 'A' else 'équipe B' if m['forfait'] == 'B' else 'les deux équipes'}.", st["p"]))
        if m["observations"]:
            corps.append(Paragraph(f"<b>Observations</b> : {R.esc(m['observations'])}", st["p"]))
        sigs = [R.signature_vide("L'arbitre central", m["arbitre"] or ""), R.signature_vide("Le délégué / commissaire", m["delegue"] or ""),
                R.signature_vide("Capitaine équipe A", a.get("capitaine") or ""), R.signature_vide("Capitaine équipe B", b.get("capitaine") or "")] + sigs_c(c, ("P",))[:1]
        code = code_c("sport_feuille_match", c, f" : {a.get('nom', '')} – {b.get('nom', '')}", f"sport:match:{mid}:{m['maj'] or ''}")
        return H.pdf_reponse(R.pdf_document(f"FEUILLE DE MATCH — {c['intitule']}", corps, sigs, code, False, entete_c(c), bandeau=bandeau_c(c)),
                             f"feuille_match_{mid}.pdf")

    @app.route("/sport/palmares.pdf")
    @H.connexion_requise("sport")
    def sport_palmares_pdf():
        from reportlab.platypus import Paragraph
        saison = saison_de()
        st = R.styles()
        L = R.largeur_utile(True)
        corps = []
        n = 0
        for c, pod, qual in palmares(saison):
            corps.append(Paragraph(f"<b>{R.esc(c['intitule'])}</b> — {R.esc(NIV_LIB.get(c['niveau'], ''))} : {R.esc(c['entite_lib'] or c['entite'])} · "
                                   f"{R.esc(c['statut'])}", st["h2"]))
            corps.append(R.tableau(["Rang", "Équipe / athlète", "École", "Détail"], [list(x) for x in pod], [8, 40, 40, 50], L))
            if qual:
                corps.append(Paragraph("Qualifiés : " + R.esc("; ".join(f"{nm} ({e})" if e and e != nm else nm for _r, nm, e, _d in qual)), st["p"]))
            n += 1
        if not corps:
            corps.append(Paragraph("Aucune compétition pour la saison.", st["p"]))
        code = R.code_document("sport_palmares", f"{TYPES['sport_palmares']} {saison} ({n} compétition(s))", f"sport:palmares:{portee()}:{saison}:{n}")
        return H.pdf_reponse(R.pdf_document(f"PALMARÈS DU SPORT SCOLAIRE — SAISON {saison}", corps, [R.signature_autorite()], code, True, bandeau=bandeau_compte()),
                             f"palmares_{saison}.pdf")

    @app.route("/sport/competition/<int:cid>/diplomes.pdf")
    @H.connexion_requise("sport")
    def sport_diplomes(cid):
        """Diplômes : ?type=laureats (podium) | participation (toutes les équipes / tous les athlètes) ; ?equipe= / ?perf= pour un seul."""
        c = competition(cid)
        typ = request.args.get("type") or "laureats"
        cibles = []
        if c["formule"] in ("performances", "jury"):
            for (ep, sx, ca), ps in resultats_perfs(c).items():
                for p in ps:
                    if request.args.get("perf", type=int) and p["id"] != request.args.get("perf", type=int):
                        continue
                    if typ == "laureats" and not (p["rang"] and p["rang"] <= 3):
                        continue
                    cibles.append((f"{p['nom']} {p['prenoms'] or ''}".strip(), p["ecole"] or "", p["rang"] if typ == "laureats" else None,
                                   f"{ep} ({ {'M': 'garçons', 'F': 'filles'}.get(p['sexe'] or '', '') } {ca}) : {p['performance'] or ''}".replace("(  ", "(").replace(" )", ")")))
        else:
            pod = {nm: r for r, nm, _e, _d in classement_final(c)}
            for e in equipes(cid):
                if request.args.get("equipe", type=int) and e["id"] != request.args.get("equipe", type=int):
                    continue
                r = pod.get(e["nom"])
                if typ == "laureats" and not (r and r <= 3):
                    continue
                cibles.append((e["nom"], e["ecole"] or "", r if typ == "laureats" else None, ""))
        if not cibles:
            flash("Aucun diplôme à éditer (résultats non saisis ?).", "warning")
            return redirect(url_for("sport_competition", cid=cid, onglet="resultats"))
        sigs = sigs_c(c, ("S", "P", "V"))
        code = code_c("sport_diplome", c, f" — {typ} ({len(cibles)})", f"sport:diplomes:{cid}:{typ}:{request.args.get('equipe') or request.args.get('perf') or ''}:{c['maj'] or ''}")
        return H.pdf_reponse(diplomes_pdf(c, cibles, sigs, code, typ), f"diplomes_{typ}_{cid}.pdf")

    def diplomes_pdf(c, cibles, sigs, code, typ):
        import io
        import pdfs
        from m_uascep import bloc_signatures
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
        W, Hh = landscape(A4)
        marge = 16 * mm
        rangs = {1: "1er", 2: "2e", 3: "3e"}
        mention = {1: "CHAMPION", 2: "VICE-CHAMPION", 3: "TROISIÈME"}
        st_t = ParagraphStyle("dt", fontName="Helvetica-Bold", fontSize=26, leading=30, alignment=1, textColor=pdfs.BLEU)
        st_n = ParagraphStyle("dn", fontName="Helvetica-Bold", fontSize=22, leading=26, alignment=1)
        st_p = ParagraphStyle("dp", fontName="Helvetica", fontSize=12.5, leading=17, alignment=1)
        h = []
        for i, (nom, ecole, rang, detail) in enumerate(cibles):
            if i:
                h.append(PageBreak())
            if U:
                from reportlab.platypus import Table
                lg = Table([[U.logo_flowable(c["niveau"], c["entite"], c["entite_lib"], 96)]], colWidths=[W - 2 * marge])
                lg.setStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")])
                h.append(lg)
            h += [Spacer(1, 2), Paragraph("UNION DES ASSOCIATIONS SPORTIVES ET CULTURELLES DES ÉCOLES PRIMAIRES (UASCEP)", st_p), Spacer(1, 4),
                  Paragraph("DIPLÔME " + ("D'HONNEUR" if rang else "DE PARTICIPATION"), st_t), Spacer(1, 8),
                  Paragraph("décerné à", st_p), Paragraph(R.esc(nom), st_n)]
            if ecole and ecole != nom:
                h.append(Paragraph(f"École : {R.esc(ecole)}", st_p))
            h += [Spacer(1, 6), Paragraph((f"<b>{mention[rang]}</b> — classé(e) <b>{rangs[rang]}</b>" if rang else "pour sa participation")
                                          + f" à la compétition « <b>{R.esc(c['intitule'])}</b> »", st_p),
                  Paragraph(R.esc(f"{c['discipline'] or ''} {c['categorie'] or ''} {c['genre'] or ''}".strip()) + (f" — {R.esc(detail)}" if detail else ""), st_p),
                  Paragraph(f"{R.esc(NIV_LIB.get(c['niveau'], ''))} : {R.esc(c['entite_lib'] or c['entite'])} · saison {R.esc(c['saison'])}"
                            + (f" · {R.esc(c['lieu'])}" if c["lieu"] else "") + (f", le {R.jjmmaaaa(c['date_fin'] or c['date_debut'])}" if (c['date_fin'] or c['date_debut']) else ""), st_p),
                  Spacer(1, 8), bloc_signatures(sigs, W - 2 * marge, code)]

        def deco(cv, doc):
            cv.saveState()
            cv.setStrokeColor(pdfs.BLEU)
            cv.setLineWidth(3)
            cv.rect(8 * mm, 8 * mm, W - 16 * mm, Hh - 16 * mm)
            cv.setStrokeColor(colors.HexColor("#C9A227"))
            cv.setLineWidth(1.2)
            cv.rect(11 * mm, 11 * mm, W - 22 * mm, Hh - 22 * mm)
            try:
                pdfs.armoiries(cv, 14 * mm, Hh - 14 * mm, 18 * mm)
            except Exception:  # noqa: BLE001
                pass
            cv.setFont("Helvetica", 6.5)
            cv.setFillColor(colors.grey)
            if code:
                cv.drawCentredString(W / 2, 12.5 * mm, f"Document vérifiable · code {code}")
            cv.restoreState()
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=(W, Hh), leftMargin=marge, rightMargin=marge, topMargin=16 * mm, bottomMargin=16 * mm,
                          title="Diplômes", author="SCOLARIS").build(h, onFirstPage=deco, onLaterPages=deco)
        return buf.getvalue()

    # ---- Excel commun (spécification outils/lots/spec.md) : une feuille par rubrique, colonnes Niveau · Entité · Saison + champs
    PHASES_EXCEL = ["Poule", "Journée de championnat", "Seizièmes de finale", "Huitièmes de finale", "Quarts de finale", "Demi-finales",
                    "Match pour la 3e place", "Finale"]
    ENT_SPORT = {
        "Compétitions": ["Niveau", "Entité", "Saison", "Intitulé", "Discipline", "Catégorie", "Genre", "Formule", "Nombre de poules", "Qualifiés par poule",
                         "Qualifiés pour le niveau supérieur", "Date de début", "Date de fin", "Lieu / site", "Comité d’organisation", "Règlement particulier", "Statut"],
        "Équipes engagées": ["Niveau", "Entité", "Saison", "Compétition", "Équipe", "École", "Provenance", "Poule", "Capitaine", "Encadreur", "Contact",
                             "Joueurs (G)", "Joueuses (F)", "Effectif", "Liste des joueurs"],
        "Calendrier et feuilles de match": ["Niveau", "Entité", "Saison", "Compétition", "Phase", "Poule", "Journée / tour", "Date", "Heure", "Terrain",
                                            "Équipe A", "Équipe B", "Score A", "Score B", "Tirs au but (A-B)", "Forfait", "Buteurs / marqueurs A",
                                            "Buteurs / marqueurs B", "Avertissements et exclusions", "Arbitre central", "Arbitres assistants",
                                            "Délégué / commissaire", "Statut", "Observations"],
        "Athlétisme (performances)": ["Niveau", "Entité", "Saison", "Compétition", "Épreuve", "Nom", "Prénoms", "Sexe", "École", "Catégorie", "N° de licence",
                                      "Tour", "Performance", "Unité", "Date", "Observations"],
        "Jeux et concours (résultats)": ["Niveau", "Entité", "Saison", "Compétition", "Participant (élève ou équipe)", "Sexe", "École", "Points / note", "Rang",
                                         "Observations"],
        "Palmarès et qualifiés": ["Niveau", "Entité", "Saison", "Compétition", "Rang", "Lauréat (équipe ou élève)", "Sexe", "École", "Distinction",
                                  "Performance / score", "Qualifié(e) au niveau supérieur", "Compétition du niveau supérieur"],
    }
    FORFAIT_X = {"A": "Équipe A", "B": "Équipe B", "AB": "Les deux"}
    DISTINCTION = {1: "Médaille d’or", 2: "Médaille d’argent", 3: "Médaille de bronze"}

    def phase_excel(c, m):
        if (m["phase"] or "poule") == "poule":
            return "Poule" if c["formule"] == "poules" else "Journée de championnat"
        return m["tour"] if m["tour"] in PHASES_EXCEL else "Finale" if "inale" in (m["tour"] or "") else m["tour"] or ""

    def journee(m):
        x = re.search(r"\d+", m["tour"] or "")
        return int(x.group(0)) if x and (m["phase"] or "poule") == "poule" else ""

    def feuilles_sport(saison):
        cs = [dict(x) for x in q("SELECT * FROM sport_competitions WHERE portee=? AND saison=? ORDER BY niveau, intitule", (portee(), saison))
              if x["niveau"] in niveaux_vis()]
        f = {k: [] for k in ENT_SPORT}
        for c in cs:
            pre = [c["niveau"], c["entite_lib"] or c["entite"], c["saison"]]
            f["Compétitions"].append(pre + [c["intitule"], c["discipline"] or "", c["categorie"] or "", c["genre"] or "", FORMULE_EXCEL.get(c["formule"], ""),
                                             c["nb_poules"] or "", c["qualifies_poule"] or "", c["qualifies_sup"] if c["qualifies_sup"] is not None else "",
                                             R.jjmmaaaa(c["date_debut"]), R.jjmmaaaa(c["date_fin"]), c["lieu"] or "", c["organisateur"] or "",
                                             c["reglement"] or "", c["statut"] or ""])
            eqs = equipes(c["id"])
            eqd = {e["id"]: e for e in eqs}
            for e in eqs:
                f["Équipes engagées"].append(pre + [c["intitule"], e["nom"], e["ecole"] or "", e["origine"] or "", e["poule"] or "", e["capitaine"] or "",
                                                     e["encadreur"] or "", e["contact"] or "", e["effectif_g"] if e["effectif_g"] is not None else "",
                                                     e["effectif_f"] if e["effectif_f"] is not None else "", (e["effectif_g"] or 0) + (e["effectif_f"] or 0), e["joueurs"] or ""])
            for m in matchs(c["id"]):
                sa, sb, joue = resultat_match(m, c["score_forfait"] or 3)
                cart = []
                for cote, lib in (("a", "A"), ("b", "B")):
                    if m["jaunes_" + cote] or m["rouges_" + cote]:
                        cart.append(f"{lib} : {m['jaunes_' + cote] or 0} jaune(s), {m['rouges_' + cote] or 0} rouge(s)")
                f["Calendrier et feuilles de match"].append(pre + [
                    c["intitule"], phase_excel(c, m), m["poule"] or "", journee(m), R.jjmmaaaa(m["date"]), m["heure"] or "", m["terrain"] or "",
                    lib_eq(eqd, m["equipe_a"]), lib_eq(eqd, m["equipe_b"]), m["score_a"] if m["score_a"] is not None else "", m["score_b"] if m["score_b"] is not None else "",
                    f"{m['tab_a']}-{m['tab_b']}" if m["tab_a"] is not None and m["tab_b"] is not None else "", FORFAIT_X.get(m["forfait"] or "", ""),
                    m["buteurs_a"] or "", m["buteurs_b"] or "", "; ".join(cart), m["arbitre"] or "", m["assesseurs"] or "", m["delegue"] or "",
                    "Joué" if joue else "Programmé", m["observations"] or ""])
            if c["formule"] in ("performances", "jury"):
                for (ep, sx, ca), ps in resultats_perfs(c).items():
                    for p in ps:
                        if c["formule"] == "performances" or EPREUVES.get(ep, ("", ""))[0] in ("s", "m"):
                            f["Athlétisme (performances)"].append(pre + [c["intitule"], ep, p["nom"], p["prenoms"] or "", p["sexe"] or "", p["ecole"] or "",
                                                                         p["categorie"] or "", p["licence"] or "", p["serie"] or "Finale",
                                                                         p["valeur"] if p["valeur"] is not None else "", EPREUVES.get(ep, ("pts", ""))[0], "", p["observations"] or ""])
                        else:
                            f["Jeux et concours (résultats)"].append(pre + [c["intitule"], f"{p['nom']} {p['prenoms'] or ''}".strip(), p["sexe"] or "", p["ecole"] or "",
                                                                            p["valeur"] if p["valeur"] is not None else "", p["rang"] or "", (ep + " " + (p["observations"] or "")).strip()])
            nq = c["qualifies_sup"] or 0
            for r, nm, ec, det in podium(c):
                f["Palmarès et qualifiés"].append(pre + [c["intitule"], r, nm, "", ec, DISTINCTION.get(r, "Mention"), det, "Oui" if r <= nq else "Non", ""])
        return f

    @app.route("/sport/saison.xlsx")
    @H.connexion_requise("sport")
    def sport_xlsx():
        saison = saison_de()
        f = feuilles_sport(saison)
        lic = G.registres["licences"]
        ent_l, rows_l = None, None
        try:
            lignes = G.lignes(lic, saison)
            pre = ["Niveau", "Entité", "Saison"]
            ent_l = pre + [l for _k, l, _t in lic.champs]
            rows_l = [list(entite_licence(x)) + [x["annee"]] + [R.jjmmaaaa(x[k]) if t == "date" else (x[k] if x[k] is not None else "") for k, _l, t in lic.champs]
                      for x in lignes]
        except Exception:  # noqa: BLE001
            pass
        feuilles = ([("Licences", ent_l, rows_l, {})] if ent_l else []) + [(k, ENT_SPORT[k], v, {}) for k, v in f.items()]
        return H.xlsx.reponse_classeur(f"sport_scolaire_{saison}.xlsx", feuilles)

    @app.route("/sport/import", methods=["POST"])
    @H.connexion_requise("sport")
    def sport_import():
        """Import du classeur commun : compétitions, équipes engagées, matchs, performances, résultats des concours
        (mise à jour si la clé d'unicité existe, sinon ajout ; colonnes calculées ignorées)."""
        import io
        import outils_xlsx as X
        saison = saison_de()
        fichier = request.files.get("fichier")
        if not fichier or not fichier.filename:
            flash("Choisissez le classeur Excel du sport scolaire.", "warning")
            return redirect(url_for("sport_competitions", saison=saison))
        try:
            wb = X._openpyxl().load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            flash("Fichier illisible (.xlsx attendu).", "danger")
            return redirect(url_for("sport_competitions", saison=saison))
        ws = {X.normaliser(w.title): w for w in wb.worksheets}
        nivcode = {X.normaliser(v): k for k, v in NIV_LIB.items()} | {X.normaliser(k): k for k in NIV_LIB}
        bilan, refus = {}, []

        def lignes(nom):
            w = ws.get(X.normaliser(nom))
            if w is None:
                return []
            rows = [list(r) for r in w.iter_rows(values_only=True)]
            i0 = next((i for i, r in enumerate(rows[:10]) if r and X.normaliser(r[0]) == "niveau"), None)
            if i0 is None:
                return []
            ent = [X.normaliser(v) for v in rows[i0]]
            out = []
            for n, r in enumerate(rows[i0 + 1:], i0 + 2):
                if r and any(v not in (None, "") for v in r):
                    out.append((n, {e: X.valeur(r, j) for j, e in enumerate(ent) if e}))
            return out

        def entite(niv, lib):
            for k, l, _i in entites(niv):
                if X.normaliser(l) == X.normaliser(lib) or X.normaliser(k) == X.normaliser(lib):
                    return k, l
            return None

        comp_id = {}
        formules = {X.normaliser(v): k for k, v in FORMULE_EXCEL.items() if k != "jury"}
        for n, v in lignes("Compétitions"):
            niv = nivcode.get(X.normaliser(v.get("niveau")))
            if niv not in niveaux_ecr():
                refus.append(f"Compétitions, ligne {n} : niveau hors de votre périmètre.")
                continue
            en = entite(niv, v.get("entite"))
            if not en or not v.get("intitule"):
                refus.append(f"Compétitions, ligne {n} : entité inconnue ou intitulé vide.")
                continue
            sa = v.get("saison") if re.fullmatch(r"\d{4}-\d{4}", v.get("saison") or "") else saison
            fo = formules.get(X.normaliser(v.get("formule")), "poules")
            if fo == "performances" and "athle" not in X.normaliser(v.get("discipline")):
                fo = "jury"
            d = {"niveau": niv, "entite": en[0], "entite_lib": en[1], "intitule": v["intitule"][:200], "discipline": v.get("discipline", "")[:80],
                 "categorie": v.get("categorie", "")[:60], "genre": v.get("genre") if v.get("genre") in GENRES else "", "formule": fo,
                 "nb_poules": R.nombre(v.get("nombre de poules")) or 2, "qualifies_poule": R.nombre(v.get("qualifies par poule")) or 2,
                 "qualifies_sup": R.nombre(v.get("qualifies pour le niveau superieur")) if v.get("qualifies pour le niveau superieur") not in (None, "") else 1,
                 "date_debut": R.iso(v.get("date de debut")), "date_fin": R.iso(v.get("date de fin")), "lieu": v.get("lieu site", ""),
                 "organisateur": v.get("comite d organisation", ""), "reglement": v.get("reglement particulier", ""),
                 "statut": v.get("statut") if v.get("statut") in STATUTS else "Programmée"}
            ex_ = q("SELECT id FROM sport_competitions WHERE portee=? AND saison=? AND intitule=? AND niveau=? AND entite=?",
                    (portee(), sa, d["intitule"], niv, en[0]), un=True)
            ks = list(d)
            if ex_:
                ex("UPDATE sport_competitions SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), ex_["id"]))
                cid = ex_["id"]
            else:
                cid = ex("INSERT INTO sport_competitions (portee, saison, " + ", ".join(ks) + ", cree_le, maj) VALUES (?,?," + ",".join("?" * len(ks)) + ",?,?)",
                         (portee(), sa) + tuple(d[k] for k in ks) + (H.maintenant(), H.maintenant()))
            comp_id[X.normaliser(d["intitule"])] = cid
            bilan["Compétitions"] = bilan.get("Compétitions", 0) + 1

        def comp_de(v, n, feuille):
            nom = X.normaliser(v.get("competition"))
            cid = comp_id.get(nom)
            if not cid:
                r = q("SELECT id, niveau FROM sport_competitions WHERE portee=? AND saison=? AND lower(intitule)=lower(?)", (portee(), v.get("saison") or saison, v.get("competition") or ""), un=True)
                cid = r["id"] if r and r["niveau"] in niveaux_ecr() else None
            if not cid:
                refus.append(f"{feuille}, ligne {n} : compétition « {v.get('competition')} » inconnue.")
            return cid

        for n, v in lignes("Équipes engagées"):
            cid = comp_de(v, n, "Équipes engagées")
            if not cid or not v.get("equipe"):
                continue
            d = {"nom": v["equipe"][:150], "ecole": v.get("ecole", ""), "origine": v.get("provenance", ""), "poule": (v.get("poule") or "").upper()[:3],
                 "capitaine": v.get("capitaine", ""), "encadreur": v.get("encadreur", ""), "contact": v.get("contact", ""),
                 "effectif_g": R.nombre(v.get("joueurs g")), "effectif_f": R.nombre(v.get("joueuses f")), "joueurs": v.get("liste des joueurs", "")}
            ex_ = q("SELECT id FROM sport_equipes WHERE competition_id=? AND lower(nom)=lower(?)", (cid, d["nom"]), un=True)
            ks = list(d)
            if ex_:
                ex("UPDATE sport_equipes SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), ex_["id"]))
            else:
                ex("INSERT INTO sport_equipes (competition_id, " + ", ".join(ks) + ", maj) VALUES (?," + ",".join("?" * len(ks)) + ",?)", (cid,) + tuple(d[k] for k in ks) + (H.maintenant(),))
            bilan["Équipes"] = bilan.get("Équipes", 0) + 1
        forf = {X.normaliser(v): k for k, v in FORFAIT_X.items()}
        for n, v in lignes("Calendrier et feuilles de match"):
            cid = comp_de(v, n, "Matchs")
            if not cid:
                continue
            ids = {X.normaliser(e["nom"]): e["id"] for e in equipes(cid)}
            a, b = ids.get(X.normaliser(v.get("equipe a"))), ids.get(X.normaliser(v.get("equipe b")))
            if not a or not b:
                refus.append(f"Matchs, ligne {n} : équipe inconnue.")
                continue
            ph = v.get("phase") or "Poule"
            poule_ph = ph in ("Poule", "Journée de championnat")
            tour = f"Journée {v.get('journee tour') or 1}" if poule_ph else ph
            tab = re.fullmatch(r"\s*(\d+)\s*[-–]\s*(\d+)\s*", v.get("tirs au but a b") or "")
            d = {"phase": "poule" if poule_ph else "elimination", "tour": tour, "poule": (v.get("poule") or "").upper()[:3], "date": R.iso(v.get("date")),
                 "heure": v.get("heure", "")[:10], "terrain": v.get("terrain", ""), "score_a": R.nombre(v.get("score a")), "score_b": R.nombre(v.get("score b")),
                 "tab_a": int(tab.group(1)) if tab else None, "tab_b": int(tab.group(2)) if tab else None, "forfait": forf.get(X.normaliser(v.get("forfait"))),
                 "buteurs_a": v.get("buteurs marqueurs a", ""), "buteurs_b": v.get("buteurs marqueurs b", ""), "arbitre": v.get("arbitre central", ""),
                 "assesseurs": v.get("arbitres assistants", ""), "delegue": v.get("delegue commissaire", ""),
                 "observations": " ".join(x for x in (v.get("avertissements et exclusions", ""), v.get("observations", "")) if x)}
            ex_ = q("SELECT id FROM sport_matchs WHERE competition_id=? AND equipe_a=? AND equipe_b=? AND tour=?", (cid, a, b, tour), un=True)
            ks = list(d)
            if ex_:
                ex("UPDATE sport_matchs SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), ex_["id"]))
            else:
                ex("INSERT INTO sport_matchs (competition_id, equipe_a, equipe_b, ordre, " + ", ".join(ks) + ", maj) VALUES (?,?,?,?," + ",".join("?" * len(ks)) + ",?)",
                   (cid, a, b, (R.nombre(v.get("journee tour")) or 1) * 100) + tuple(d[k] for k in ks) + (H.maintenant(),))
            bilan["Matchs"] = bilan.get("Matchs", 0) + 1
        for feuille, cle_nom in (("Athlétisme (performances)", "nom"), ("Jeux et concours (résultats)", "participant eleve ou equipe")):
            for n, v in lignes(feuille):
                cid = comp_de(v, n, feuille)
                if not cid or not v.get(cle_nom):
                    continue
                cc = competition(cid)
                if feuille.startswith("Athl"):
                    ep, perf, val = v.get("epreuve", ""), v.get("performance", ""), R.nombre(v.get("performance"), "decimal")
                    nom, pre = v["nom"], v.get("prenoms", "")
                else:
                    ep, perf, val = cc["discipline"] or "Concours", v.get("points note", ""), R.nombre(v.get("points note"), "decimal")
                    nom, pre = v[cle_nom], ""
                d = {"epreuve": ep[:80], "nom": nom[:120], "prenoms": pre[:120], "sexe": v.get("sexe") if v.get("sexe") in ("M", "F") else "",
                     "ecole": v.get("ecole", ""), "categorie": v.get("categorie", ""), "licence": v.get("n de licence", ""), "serie": v.get("tour", ""),
                     "performance": str(perf).replace(".", ",") if perf not in (None, "") else "", "valeur": val, "observations": v.get("observations", "")}
                ex_ = q("SELECT id FROM sport_perfs WHERE competition_id=? AND epreuve=? AND nom=? AND COALESCE(prenoms,'')=? "
                        "AND COALESCE(NULLIF(serie,''),'Finale')=COALESCE(NULLIF(?,''),'Finale')",
                        (cid, d["epreuve"], d["nom"], d["prenoms"], d["serie"]), un=True)
                ks = list(d)
                if ex_:
                    ex("UPDATE sport_perfs SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), ex_["id"]))
                else:
                    ex("INSERT INTO sport_perfs (competition_id, " + ", ".join(ks) + ", maj) VALUES (?," + ",".join("?" * len(ks)) + ",?)", (cid,) + tuple(d[k] for k in ks) + (H.maintenant(),))
                bilan["Performances"] = bilan.get("Performances", 0) + 1
        H.journal("sport_import", str(bilan))
        flash("Import : " + (", ".join(f"{k} {v}" for k, v in bilan.items()) or "aucune ligne") + (f" ; {len(refus)} ligne(s) refusée(s)." if refus else "."),
              "success" if bilan and not refus else "warning")
        for x in refus[:12]:
            flash(x, "warning")
        return redirect(url_for("sport_competitions", saison=saison))

    H.sport = __import__("types").SimpleNamespace(records=records, palmares=palmares, portee=portee, classement=classement)
