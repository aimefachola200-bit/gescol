# -*- coding: utf-8 -*-
"""Patrimoine et ressources de l'école : infrastructures (bâtiments, salles, latrines, point d'eau, clôture,
électricité, cuisine, logements, terrain de sport…), mobilier (tables-bancs, bureaux, armoires…), matériel
didactique (manuels, guides, cartes, globes, matériel scientifique…), mouvements (entrées / sorties / réformes),
inventaire annuel (PDF, Excel) et tableau de bord.

* /patrimoine                                 patrimoine_accueil          tableau de bord (synthèse)
* /patrimoine/infrastructures                 patrimoine_locaux           liste des locaux et ouvrages
* /patrimoine/infrastructures/<id> GET/POST   patrimoine_local            fiche (id 0 = nouveau)
* /patrimoine/mobilier                        patrimoine_mobilier         mobilier + places assises / déficit par classe
* /patrimoine/mobilier/<id>        GET/POST   patrimoine_meuble
* /patrimoine/didactique                      patrimoine_didactique       matériel didactique + ratio manuels / élèves
* /patrimoine/didactique/<id>      GET/POST   patrimoine_materiel
* /patrimoine/<table>/<id>/supprimer   POST   patrimoine_supprimer
* /patrimoine/mouvements           GET/POST   patrimoine_mouvements       entrées, sorties, réformes
* /patrimoine/mouvements/<id>/annuler  POST   patrimoine_mouvement_annuler
* /patrimoine/equipements          GET/POST   patrimoine_equipements      équipements et services (questionnaire)
* /patrimoine/inventaire.pdf                  patrimoine_inventaire_pdf   inventaire annuel
* /patrimoine/inventaire.xlsx                 patrimoine_inventaire_xlsx

Interface pour les autres modules (fiche de recensement) : H.patrimoine_synthese(ecole_id) -> dict
(clés documentées dans la fonction patrimoine_synthese ci-dessous).

Droits : « patrimoine » (admin, directeur, secrétaire).

Règles de calcul :
* places assises d'une classe = Σ quantité × places par unité du mobilier élèves (tables-bancs, tables avec chaise,
  mobilier adapté) en état bon ou passable, rattaché à la classe ou à une salle occupée par la classe ;
  déficit = max(0, effectif inscrit − places assises) ; tables-bancs à 2 places manquantes = ⌈déficit / 2⌉ ;
* ratio manuels / élèves (par niveau et discipline) = manuels de l'élève en état bon ou passable ÷ effectif inscrit
  du niveau (« Tous niveaux » : effectif total de l'école) ; manuels manquants = max(0, effectif − manuels).
"""
import math
import re
from datetime import date, datetime

from flask import abort, flash, g, redirect, render_template, request, url_for

ETATS = {"bon": "Bon", "passable": "Passable", "mauvais": "Mauvais"}
UTILISABLE = ("bon", "passable")
TYPES_LOCAUX = {
    "salle_classe": "Salle de classe", "bureau": "Bureau", "magasin": "Magasin", "latrines": "Latrines",
    "cuisine": "Cuisine / cantine", "bibliotheque": "Bibliothèque", "salle_informatique": "Salle informatique",
    "logement": "Logement", "point_eau": "Point d'eau", "cloture": "Clôture", "electricite": "Électricité (installation)",
    "terrain_sport": "Terrain de sport", "autre": "Autre ouvrage"}
MURS = {"dur": "En dur", "semi_dur": "Semi-dur", "banco": "Banco", "planche": "Planche / bambou",
        "paillote": "Paillote", "sans_mur": "Sans mur", "autre": "Autre"}
TOITS = {"tole": "Tôles", "dalle": "Dalle / fibrociment / tuiles", "paille": "Paille", "sans_toit": "Sans toit"}
PORTES = {"metallique": "Métalliques", "tole_bois": "Tôle / bois", "non_installees": "Non installées"}
FENETRES = {"persiennes": "Persiennes", "claustras": "Claustras", "vitrees": "Vitrées", "non_installees": "Non installées"}
FINANCEMENTS = {"etat": "État", "collectivites": "Collectivités locales", "ape": "APE",
                "aide_ext": "Aide extérieure (ONG, PTF)", "autres": "Autres / non déterminé"}
SOURCES = ["SONEB", "Forage", "Adduction d'eau villageoise", "Puits", "Citerne", "SBEE", "Groupe électrogène",
           "Énergie solaire"]
# code : (libellé, places assises par unité, famille)
CAT_MOBILIER = {
    "tb1": ("Table avec chaise (1 place)", 1, "eleves"), "tb2": ("Table-banc 2 places", 2, "eleves"),
    "tb3": ("Table-banc 3 places et plus", 3, "eleves"), "adapte": ("Mobilier adapté (handicap)", 1, "eleves"),
    "bureau_maitre": ("Bureau du maître avec chaise", 0, "maitre"), "armoire": ("Armoire / placard", 0, "maitre"),
    "tableau": ("Tableau noir", 0, "maitre"), "table": ("Table", 0, "autre"), "chaise": ("Chaise", 0, "autre"),
    "bureau": ("Bureau", 0, "autre"), "etagere": ("Étagère / rayonnage", 0, "autre"), "autre": ("Autre mobilier", 0, "autre")}
CAT_DIDACTIQUE = {
    "manuel": "Manuel de l'élève", "manuel_adapte": "Manuel adapté (braille…)", "guide": "Guide du maître",
    "programme": "Programme d'études", "ouvrage": "Autre ouvrage pédagogique", "carte": "Carte murale",
    "globe": "Globe terrestre", "scientifique": "Matériel scientifique (compendium, planches…)",
    "geometrie": "Matériel de géométrie / métrique", "malette": "Malette pédagogique / boîte à images",
    "informatique": "Matériel informatique", "sport": "Matériel sportif", "adapte": "Équipement adapté (handicap)",
    "autre": "Autre matériel"}
DISCIPLINES = ["Français", "Mathématiques", "Éducation scientifique et technologique (EST)",
               "Éducation sociale (ES)", "Éducation artistique (EA)", "Éducation physique et sportive (EPS)",
               "Anglais", "Informatique", "Lecture", "Toutes disciplines"]
TOUS_NIVEAUX = "Tous niveaux"
SENS = {"entree": "Entrée", "sortie": "Sortie", "reforme": "Réforme"}
EQUIPEMENTS = [  # questionnaire complémentaire (repris de la fiche de recensement)
    ("domaine_delimite", "Le domaine scolaire est délimité"), ("cour_ombragee", "La cour de récréation est ombragée"),
    ("lavage_mains", "Dispositif de lavage des mains"), ("cantine_fonctionnelle", "Cantine fonctionnelle"),
    ("equipement_cuisine", "Équipement de cuisine"), ("magasin_vivres", "Magasin de vivres en bon état"),
    ("jardin", "Jardin ou champ scolaire"), ("bibliotheque_fonctionnelle", "Bibliothèque fonctionnelle"),
    ("boite_pharmacie", "Boîte à pharmacie"), ("urinoir", "Urinoir aménagé"),
    ("terrain_trace", "Terrain de sport tracé"), ("terrain_equipe", "Terrain de sport équipé"),
    ("amenagements_handicap", "Aménagements adaptés aux enfants handicapés")]

# ------------------------------------------------------------------ description des formulaires
F_LOCAL = [
    {"k": "type", "lib": "Nature du local / de l'ouvrage", "type": "choix", "opts": TYPES_LOCAUX, "req": True},
    {"k": "designation", "lib": "Désignation", "type": "texte", "max": 120, "req": True, "aide": "ex. Salle 1 – bâtiment A"},
    {"k": "classe_id", "lib": "Classe qui occupe la salle", "type": "classe", "pour": ["salle_classe"]},
    {"k": "utilisee", "lib": "Salle utilisée", "type": "bool", "pour": ["salle_classe"], "defaut": 1},
    {"k": "annee_service", "lib": "Année de construction / mise en service", "type": "annee"},
    {"k": "superficie", "lib": "Superficie (m²)", "type": "reel", "max": 100000},
    {"k": "murs", "lib": "Matériau (nature des murs)", "type": "choix", "opts": MURS},
    {"k": "etat_murs", "lib": "État des murs", "type": "choix", "opts": ETATS},
    {"k": "toit", "lib": "Nature du toit", "type": "choix", "opts": TOITS},
    {"k": "etat_toit", "lib": "État du toit", "type": "choix", "opts": ETATS},
    {"k": "portes", "lib": "Nature des portes", "type": "choix", "opts": PORTES},
    {"k": "fenetres", "lib": "Nature des fenêtres", "type": "choix", "opts": FENETRES},
    {"k": "financement", "lib": "Qui a financé la construction", "type": "choix", "opts": FINANCEMENTS},
    {"k": "rampe", "lib": "Rampe d'accès (personnes handicapées)", "type": "bool"},
    {"k": "etat", "lib": "État général", "type": "choix", "opts": ETATS, "req": True},
    {"k": "blocs", "lib": "Nombre de blocs", "type": "entier", "max": 100, "pour": ["latrines"]},
    {"k": "cabines_g", "lib": "Cabines garçons", "type": "entier", "max": 500, "pour": ["latrines"]},
    {"k": "cabines_f", "lib": "Cabines filles", "type": "entier", "max": 500, "pour": ["latrines"]},
    {"k": "cabines_ens", "lib": "Cabines enseignants", "type": "entier", "max": 500, "pour": ["latrines"]},
    {"k": "separees", "lib": "Séparées filles / garçons", "type": "bool", "pour": ["latrines"]},
    {"k": "source", "lib": "Source / type", "type": "texte", "max": 120, "liste": SOURCES,
     "pour": ["point_eau", "electricite"], "aide": "SONEB, forage, puits… ; SBEE, solaire…"},
    {"k": "besoins", "lib": "Besoins de réhabilitation", "type": "long", "max": 1000},
    {"k": "observations", "lib": "Observations", "type": "long", "max": 1000},
]
F_MOBILIER = [
    {"k": "categorie", "lib": "Catégorie", "type": "choix", "opts": {k: v[0] for k, v in CAT_MOBILIER.items()}, "req": True},
    {"k": "designation", "lib": "Désignation (précision)", "type": "texte", "max": 120},
    {"k": "classe_id", "lib": "Classe", "type": "classe", "aide": "mobilier d'une classe"},
    {"k": "local_id", "lib": "ou autre local", "type": "local", "aide": "bureau, magasin, bibliothèque…"},
    {"k": "quantite", "lib": "Quantité", "type": "entier", "max": 100000, "req": True},
    {"k": "places", "lib": "Places assises par unité", "type": "entier", "max": 10,
     "aide": "vide = valeur de la catégorie (1, 2 ou 3)"},
    {"k": "etat", "lib": "État", "type": "choix", "opts": ETATS, "req": True},
    {"k": "annee_acquisition", "lib": "Année d'acquisition", "type": "annee"},
    {"k": "financement", "lib": "Financement / provenance", "type": "choix", "opts": FINANCEMENTS},
    {"k": "observations", "lib": "Observations", "type": "long", "max": 1000},
]
F_DIDACTIQUE = [
    {"k": "categorie", "lib": "Catégorie", "type": "choix", "opts": CAT_DIDACTIQUE, "req": True},
    {"k": "designation", "lib": "Désignation", "type": "texte", "max": 150, "req": True,
     "aide": "ex. Manuel de français CE1, globe terrestre"},
    {"k": "discipline", "lib": "Discipline", "type": "texte", "max": 80, "liste": DISCIPLINES},
    {"k": "niveau", "lib": "Niveau", "type": "niveau"},
    {"k": "quantite", "lib": "Quantité", "type": "entier", "max": 100000, "req": True},
    {"k": "etat", "lib": "État", "type": "choix", "opts": ETATS, "req": True},
    {"k": "annee_acquisition", "lib": "Année d'acquisition", "type": "annee"},
    {"k": "financement", "lib": "Financement / provenance", "type": "choix", "opts": FINANCEMENTS},
    {"k": "observations", "lib": "Observations", "type": "long", "max": 1000},
]
TABLES = {  # code d'URL -> (table SQL, formulaire, titre, endpoint de liste)
    "infrastructures": ("pat_locaux", F_LOCAL, "Infrastructure", "patrimoine_locaux"),
    "mobilier": ("pat_mobilier", F_MOBILIER, "Mobilier", "patrimoine_mobilier"),
    "didactique": ("pat_didactique", F_DIDACTIQUE, "Matériel didactique", "patrimoine_didactique"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS pat_locaux (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL,
    type TEXT NOT NULL, designation TEXT NOT NULL, classe_id INTEGER, utilisee INTEGER DEFAULT 1,
    annee_service INTEGER, superficie REAL, murs TEXT, etat_murs TEXT, toit TEXT, etat_toit TEXT,
    portes TEXT, fenetres TEXT, financement TEXT, rampe INTEGER DEFAULT 0, etat TEXT,
    blocs INTEGER, cabines_g INTEGER, cabines_f INTEGER, cabines_ens INTEGER, separees INTEGER DEFAULT 0,
    source TEXT, besoins TEXT, observations TEXT, cree_le TEXT, maj TEXT
);
CREATE TABLE IF NOT EXISTS pat_mobilier (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL,
    categorie TEXT NOT NULL, designation TEXT, classe_id INTEGER, local_id INTEGER,
    quantite INTEGER NOT NULL DEFAULT 0, places INTEGER, etat TEXT, annee_acquisition INTEGER,
    financement TEXT, observations TEXT, cree_le TEXT, maj TEXT
);
CREATE TABLE IF NOT EXISTS pat_didactique (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL,
    categorie TEXT NOT NULL, designation TEXT NOT NULL, discipline TEXT, niveau TEXT,
    quantite INTEGER NOT NULL DEFAULT 0, etat TEXT, annee_acquisition INTEGER, financement TEXT,
    observations TEXT, cree_le TEXT, maj TEXT
);
CREATE TABLE IF NOT EXISTS pat_mouvements (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL,
    date TEXT NOT NULL, sens TEXT NOT NULL,          -- entree | sortie | reforme
    objet TEXT NOT NULL, objet_id INTEGER,            -- mobilier | didactique
    designation TEXT, quantite INTEGER NOT NULL, motif TEXT, reference TEXT,
    saisi_par INTEGER, cree_le TEXT
);
"""


# ============================================================ outils purs
def lire_date(v):
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def lire_champs(spec, f, classes_ids=(), locaux_ids=()):
    """Valeurs contrôlées d'un formulaire décrit par spec -> (valeurs, erreurs)."""
    vals, err = {}, []
    for c in spec:
        k, t = c["k"], c["type"]
        brut = (f.get(k) or "").strip()
        v = None
        if t == "choix":
            v = brut if brut in c["opts"] else None
            if brut and v is None:
                err.append(f"« {c['lib']} » : valeur non reconnue.")
        elif t in ("texte", "long", "niveau"):
            v = brut[:c.get("max", 80)]
        elif t == "bool":
            v = 1 if f.get(k) else 0
        elif t in ("entier", "annee"):
            if brut:
                if not brut.isdigit():
                    err.append(f"« {c['lib']} » doit être un nombre entier positif.")
                else:
                    v = int(brut)
                    if t == "annee" and not 1900 <= v <= date.today().year + 1:
                        err.append(f"« {c['lib']} » : année invalide.")
                        v = None
                    elif t == "entier" and v > c.get("max", 10 ** 6):
                        err.append(f"« {c['lib']} » : valeur trop grande (maximum {c.get('max')}).")
                        v = None
        elif t == "reel":
            if brut:
                try:
                    v = float(brut.replace(",", ".").replace(" ", ""))
                    if not 0 <= v <= c.get("max", 10 ** 6):
                        raise ValueError
                except ValueError:
                    err.append(f"« {c['lib']} » : nombre invalide.")
                    v = None
        elif t == "classe":
            v = int(brut) if brut.isdigit() and int(brut) in classes_ids else None
        elif t == "local":
            v = int(brut) if brut.isdigit() and int(brut) in locaux_ids else None
        if c.get("req") and v in (None, ""):
            err.append(f"« {c['lib']} » est obligatoire.")
        vals[k] = v
    return vals, err


def places_unite(m):
    """Places assises par unité d'un mobilier (valeur saisie, sinon celle de la catégorie)."""
    if m["places"] is not None:
        return m["places"]
    return CAT_MOBILIER.get(m["categorie"], ("", 0, ""))[1]


def places_classes(classes, mobilier, locaux, effectifs):
    """Places assises et déficit par classe.
    classes : [{id, nom, niveau}] ; mobilier : lignes pat_mobilier ; locaux : {id: classe_id} ;
    effectifs : {classe_id: {"g", "f", "t"}}."""
    res = []
    for c in classes:
        places = total = 0
        for m in mobilier:
            if CAT_MOBILIER.get(m["categorie"], ("", 0, ""))[2] != "eleves":
                continue
            cid = m["classe_id"] or locaux.get(m["local_id"])
            if cid != c["id"]:
                continue
            p = (m["quantite"] or 0) * places_unite(m)
            total += p
            if m["etat"] in UTILISABLE:
                places += p
        eff = effectifs.get(c["id"], {"g": 0, "f": 0, "t": 0})
        deficit = max(0, eff["t"] - places)
        res.append({"classe_id": c["id"], "classe": c["nom"], "niveau": c["niveau"], "g": eff["g"], "f": eff["f"],
                    "effectif": eff["t"], "places": places, "places_total": total, "deficit": deficit,
                    "excedent": max(0, places - eff["t"]), "tables_bancs_manquantes": math.ceil(deficit / 2)})
    return res


def ratios_manuels(didactique, eff_niveaux, eff_total):
    """Ratio manuels de l'élève / élèves par niveau et discipline."""
    groupes = {}
    for d in didactique:
        if d["categorie"] != "manuel":
            continue
        cle = (d["niveau"] or TOUS_NIVEAUX, d["discipline"] or "—")
        gr = groupes.setdefault(cle, {"quantite": 0, "utilisables": 0})
        gr["quantite"] += d["quantite"] or 0
        if d["etat"] in UTILISABLE:
            gr["utilisables"] += d["quantite"] or 0
    res = []
    for (niv, disc), gr in sorted(groupes.items()):
        eff = eff_total if niv == TOUS_NIVEAUX else eff_niveaux.get(niv, 0)
        res.append({"niveau": niv, "discipline": disc, "quantite": gr["quantite"], "utilisables": gr["utilisables"],
                    "effectif": eff, "ratio": round(gr["utilisables"] / eff, 2) if eff else None,
                    "manquants": max(0, eff - gr["utilisables"])})
    return res


def ratio_txt(r):
    return "—" if r is None else f"{r:.2f}".replace(".", ",")


def esc(t):
    return str("" if t is None else t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    # -------------------------------------------------------------- données
    def classes_ecole(eid):
        return q("SELECT * FROM classes WHERE ecole_id=? ORDER BY niveau, nom", (eid,))

    def effectifs_ecole(eid):
        """{classe_id: {"g", "f", "t"}} des élèves inscrits des classes de l'école."""
        res = {}
        for r in q("""SELECT e.classe_id, SUM(e.sexe='F') f, SUM(e.sexe<>'F') gg, COUNT(*) t FROM eleves e
                      JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=? AND e.statut='inscrit'
                      GROUP BY e.classe_id""", (eid,)):
            res[r["classe_id"]] = {"g": r["gg"] or 0, "f": r["f"] or 0, "t": r["t"] or 0}
        return res

    def equipements(eid):
        return H.doc_lire(f"e{eid}:patrimoine:equipements", {}) or {}

    # -------------------------------------------------------------- synthèse (exposée)
    def patrimoine_synthese(ecole_id):
        """Synthèse du patrimoine d'une école (pour la fiche de recensement et le tableau de bord).

        Clés du dict renvoyé :
        * effectifs : {"g", "f", "t"} élèves inscrits de l'école
        * salles_classe : {"total", "utilisees", "non_utilisees", "bon", "passable", "mauvais",
                           "par_materiau": {code MURS: n}, "par_toit": {code TOITS: n}, "a_rehabiliter"}
        * locaux : {type TYPES_LOCAUX: {"libelle", "nombre", "bon", "passable", "mauvais"}} (tous les ouvrages)
        * latrines : {"blocs", "cabines_g", "cabines_f", "cabines_ens", "cabines_total", "separees" (bool), "existe"}
        * equipements : booléens/valeurs : "cloture", "point_eau", "point_eau_source", "electricite",
                        "electricite_source", "cuisine", "logements" (nombre), "terrain_sport", "bibliotheque",
                        "salle_informatique", "magasin", "bureau" + réponses du questionnaire complémentaire
                        (clés de EQUIPEMENTS : domaine_delimite, cour_ombragee, lavage_mains, cantine_fonctionnelle,
                        equipement_cuisine, magasin_vivres, jardin, bibliotheque_fonctionnelle, boite_pharmacie,
                        urinoir, terrain_trace, terrain_equipe, amenagements_handicap), "superficie_ha", "nb_ouvrages"
        * mobilier : {"par_categorie": {code CAT_MOBILIER: {"libelle", "quantite", "bon", "passable", "mauvais"}},
                      "places_assises" (utilisables), "places_total", "deficit_places" (somme des déficits par classe),
                      "tables_bancs_manquantes", "par_classe": [{classe_id, classe, niveau, g, f, effectif, places,
                      places_total, deficit, excedent, tables_bancs_manquantes}],
                      "maitre": {"bureaux", "armoires", "tableaux"}}
        * didactique : {"par_categorie": {code CAT_DIDACTIQUE: {"libelle", "quantite", "bon", "passable", "mauvais"}},
                        "manuels": [{niveau, discipline, quantite, utilisables, effectif, ratio, manquants}],
                        "manuels_total", "ratio_global" (manuels utilisables / élève, ou None)}
        * besoins : [{"designation", "type", "etat", "besoins"}] ouvrages à réhabiliter (mauvais état ou besoin saisi)
        * mouvements_annee : {"entree", "sortie", "reforme"} quantités de l'année scolaire active
        """
        cls = classes_ecole(ecole_id)
        eff = effectifs_ecole(ecole_id)
        tot = {"g": sum(e["g"] for e in eff.values()), "f": sum(e["f"] for e in eff.values())}
        tot["t"] = tot["g"] + tot["f"]
        locaux = q("SELECT * FROM pat_locaux WHERE ecole_id=?", (ecole_id,))
        mob = q("SELECT * FROM pat_mobilier WHERE ecole_id=?", (ecole_id,))
        did = q("SELECT * FROM pat_didactique WHERE ecole_id=?", (ecole_id,))
        par_type = {k: {"libelle": v, "nombre": 0, "bon": 0, "passable": 0, "mauvais": 0} for k, v in TYPES_LOCAUX.items()}
        for l in locaux:
            t = par_type.setdefault(l["type"], {"libelle": l["type"], "nombre": 0, "bon": 0, "passable": 0, "mauvais": 0})
            t["nombre"] += 1
            if l["etat"] in ETATS:
                t[l["etat"]] += 1
        salles = [l for l in locaux if l["type"] == "salle_classe"]
        sc = {"total": len(salles), "utilisees": sum(1 for s in salles if s["utilisee"]),
              "par_materiau": {}, "par_toit": {},
              "a_rehabiliter": sum(1 for s in salles if s["etat"] == "mauvais" or (s["besoins"] or "").strip())}
        sc["non_utilisees"] = sc["total"] - sc["utilisees"]
        for e in ETATS:
            sc[e] = sum(1 for s in salles if s["etat"] == e)
        for s in salles:
            if s["murs"]:
                sc["par_materiau"][s["murs"]] = sc["par_materiau"].get(s["murs"], 0) + 1
            if s["toit"]:
                sc["par_toit"][s["toit"]] = sc["par_toit"].get(s["toit"], 0) + 1
        lat = [l for l in locaux if l["type"] == "latrines"]
        latrines = {"existe": bool(lat), "blocs": sum(l["blocs"] or 0 for l in lat) or len(lat),
                    "cabines_g": sum(l["cabines_g"] or 0 for l in lat), "cabines_f": sum(l["cabines_f"] or 0 for l in lat),
                    "cabines_ens": sum(l["cabines_ens"] or 0 for l in lat), "separees": any(l["separees"] for l in lat)}
        latrines["cabines_total"] = latrines["cabines_g"] + latrines["cabines_f"] + latrines["cabines_ens"]

        def source(typ):
            return ", ".join(sorted({l["source"] for l in locaux if l["type"] == typ and l["source"]}))

        comp = equipements(ecole_id)
        eq = {"cloture": any(l["type"] == "cloture" for l in locaux),
              "point_eau": any(l["type"] == "point_eau" for l in locaux), "point_eau_source": source("point_eau"),
              "electricite": any(l["type"] == "electricite" for l in locaux), "electricite_source": source("electricite"),
              "cuisine": any(l["type"] == "cuisine" for l in locaux),
              "logements": sum(1 for l in locaux if l["type"] == "logement"),
              "terrain_sport": any(l["type"] == "terrain_sport" for l in locaux),
              "bibliotheque": any(l["type"] == "bibliotheque" for l in locaux),
              "salle_informatique": any(l["type"] == "salle_informatique" for l in locaux),
              "magasin": any(l["type"] == "magasin" for l in locaux), "bureau": any(l["type"] == "bureau" for l in locaux)}
        for k, _lib in EQUIPEMENTS:
            eq[k] = bool(comp.get(k))
        eq["superficie_ha"] = comp.get("superficie_ha") or None
        eq["nb_ouvrages"] = comp.get("nb_ouvrages") or None
        # mobilier
        pc = {k: {"libelle": v[0], "quantite": 0, "bon": 0, "passable": 0, "mauvais": 0} for k, v in CAT_MOBILIER.items()}
        for m in mob:
            c = pc.setdefault(m["categorie"], {"libelle": m["categorie"], "quantite": 0, "bon": 0, "passable": 0, "mauvais": 0})
            c["quantite"] += m["quantite"] or 0
            if m["etat"] in ETATS:
                c[m["etat"]] += m["quantite"] or 0
        loc_classe = {l["id"]: l["classe_id"] for l in locaux if l["classe_id"]}
        par_classe = places_classes(cls, mob, loc_classe, eff)
        mobilier = {"par_categorie": pc, "par_classe": par_classe,
                    "places_assises": sum(x["places"] for x in par_classe),
                    "places_total": sum(x["places_total"] for x in par_classe),
                    "deficit_places": sum(x["deficit"] for x in par_classe),
                    "tables_bancs_manquantes": sum(x["tables_bancs_manquantes"] for x in par_classe),
                    "maitre": {"bureaux": pc["bureau_maitre"]["quantite"], "armoires": pc["armoire"]["quantite"],
                               "tableaux": pc["tableau"]["quantite"]}}
        # didactique
        pd = {k: {"libelle": v, "quantite": 0, "bon": 0, "passable": 0, "mauvais": 0} for k, v in CAT_DIDACTIQUE.items()}
        for d in did:
            c = pd.setdefault(d["categorie"], {"libelle": d["categorie"], "quantite": 0, "bon": 0, "passable": 0, "mauvais": 0})
            c["quantite"] += d["quantite"] or 0
            if d["etat"] in ETATS:
                c[d["etat"]] += d["quantite"] or 0
        eff_niv = {}
        for c in cls:
            eff_niv[c["niveau"]] = eff_niv.get(c["niveau"], 0) + eff.get(c["id"], {"t": 0})["t"]
        manuels = ratios_manuels(did, eff_niv, tot["t"])
        util = sum(d["quantite"] or 0 for d in did if d["categorie"] == "manuel" and d["etat"] in UTILISABLE)
        didactique = {"par_categorie": pd, "manuels": manuels, "manuels_total": pd["manuel"]["quantite"],
                      "ratio_global": round(util / tot["t"], 2) if tot["t"] else None}
        besoins = [{"designation": l["designation"], "type": TYPES_LOCAUX.get(l["type"], l["type"]),
                    "etat": ETATS.get(l["etat"], ""), "besoins": l["besoins"] or ""}
                   for l in locaux if l["etat"] == "mauvais" or (l["besoins"] or "").strip()]
        d1, d2 = H.bornes_annee()
        mv = {k: 0 for k in SENS}
        for r in q("""SELECT sens, SUM(quantite) n FROM pat_mouvements WHERE ecole_id=? AND date BETWEEN ? AND ?
                      GROUP BY sens""", (ecole_id, d1, d2)):
            mv[r["sens"]] = r["n"] or 0
        return {"effectifs": tot, "salles_classe": sc, "locaux": par_type, "latrines": latrines, "equipements": eq,
                "mobilier": mobilier, "didactique": didactique, "besoins": besoins, "mouvements_annee": mv}

    H.patrimoine_synthese = patrimoine_synthese

    # -------------------------------------------------------------- tableau de bord
    @app.route("/patrimoine")
    @H.connexion_requise("patrimoine")
    def patrimoine_accueil():
        s = patrimoine_synthese(H.eco())
        mouvements = q("SELECT * FROM pat_mouvements WHERE ecole_id=? ORDER BY date DESC, id DESC LIMIT 6", (H.eco(),))
        vide = not any(q(f"SELECT 1 FROM {t} WHERE ecole_id=? LIMIT 1", (H.eco(),), un=True)
                       for t in ("pat_locaux", "pat_mobilier", "pat_didactique"))
        return render_template("patrimoine_accueil.html", s=s, onglet="accueil", mouvements=mouvements, vide=vide,
                               ETATS=ETATS, MURS=MURS, TOITS=TOITS, SENS=SENS, ratio_txt=ratio_txt,
                               EQUIPEMENTS=EQUIPEMENTS)

    # -------------------------------------------------------------- listes
    @app.route("/patrimoine/infrastructures")
    @H.connexion_requise("patrimoine")
    def patrimoine_locaux():
        typ = request.args.get("type", "")
        sql, params = "SELECT l.*, c.nom classe_nom FROM pat_locaux l LEFT JOIN classes c ON c.id=l.classe_id WHERE l.ecole_id=?", [H.eco()]
        if typ in TYPES_LOCAUX:
            sql += " AND l.type=?"
            params.append(typ)
        liste = q(sql + " ORDER BY l.type, l.designation", params)
        s = patrimoine_synthese(H.eco())
        return render_template("patrimoine_locaux.html", liste=liste, s=s, onglet="locaux", typ=typ,
                               TYPES=TYPES_LOCAUX, ETATS=ETATS, MURS=MURS, TOITS=TOITS, FIN=FINANCEMENTS)

    @app.route("/patrimoine/mobilier")
    @H.connexion_requise("patrimoine")
    def patrimoine_mobilier():
        liste = q("""SELECT m.*, c.nom classe_nom, l.designation local_nom FROM pat_mobilier m
                     LEFT JOIN classes c ON c.id=m.classe_id LEFT JOIN pat_locaux l ON l.id=m.local_id
                     WHERE m.ecole_id=? ORDER BY COALESCE(c.nom, l.designation, 'zzz'), m.categorie""", (H.eco(),))
        s = patrimoine_synthese(H.eco())
        return render_template("patrimoine_mobilier.html", liste=liste, s=s, onglet="mobilier", CAT=CAT_MOBILIER,
                               ETATS=ETATS, places_unite=places_unite)

    @app.route("/patrimoine/didactique")
    @H.connexion_requise("patrimoine")
    def patrimoine_didactique():
        cat = request.args.get("categorie", "")
        sql, params = "SELECT * FROM pat_didactique WHERE ecole_id=?", [H.eco()]
        if cat in CAT_DIDACTIQUE:
            sql += " AND categorie=?"
            params.append(cat)
        liste = q(sql + " ORDER BY categorie, niveau, discipline, designation", params)
        s = patrimoine_synthese(H.eco())
        return render_template("patrimoine_didactique.html", liste=liste, s=s, onglet="didactique", CAT=CAT_DIDACTIQUE,
                               ETATS=ETATS, cat=cat, ratio_txt=ratio_txt)

    # -------------------------------------------------------------- fiches (ajout / modification)
    def fiche(code, oid):
        table, spec, titre, liste_ep = TABLES[code]
        obj = None
        if oid:
            obj = q(f"SELECT * FROM {table} WHERE id=? AND ecole_id=?", (oid, H.eco()), un=True)
            if not obj:
                abort(404)
        cls = classes_ecole(H.eco())
        locaux = q("SELECT id, designation, type FROM pat_locaux WHERE ecole_id=? ORDER BY designation", (H.eco(),))
        if request.method == "POST":
            vals, err = lire_champs(spec, request.form, {c["id"] for c in cls},
                                    {l["id"] for l in locaux if not obj or code != "infrastructures" or l["id"] != oid})
            if err:
                for e in err:
                    flash(e, "danger")
                v = dict(request.form.items())
            else:
                cles = [c["k"] for c in spec]
                if obj:
                    ex(f"UPDATE {table} SET {', '.join(k + '=?' for k in cles)}, maj=? WHERE id=?",
                       [vals[k] for k in cles] + [H.maintenant(), oid])
                    flash(f"{titre} mis à jour.", "success")
                else:
                    oid = ex(f"INSERT INTO {table} (ecole_id, {', '.join(cles)}, cree_le, maj) "
                             f"VALUES ({', '.join('?' * (len(cles) + 3))})",
                             [H.eco()] + [vals[k] for k in cles] + [H.maintenant(), H.maintenant()])
                    flash(f"{titre} enregistré.", "success")
                H.journal(f"patrimoine_{code}", f"{oid} {vals.get('designation') or vals.get('categorie')}")
                if request.form.get("suivant"):
                    return redirect(request.path.rsplit("/", 1)[0] + "/0")
                return redirect(url_for(liste_ep))
        else:
            v = dict(obj) if obj else {c["k"]: c.get("defaut") for c in spec}
            if not obj:
                for k in ("type", "categorie", "classe_id", "niveau"):
                    if request.args.get(k):
                        v[k] = request.args.get(k)
        niveaux = sorted({c["niveau"] for c in cls}) + [TOUS_NIVEAUX]
        return render_template("patrimoine_fiche.html", spec=spec, v=v, obj=obj, titre=titre, code=code,
                               onglet={"infrastructures": "locaux"}.get(code, code), cls=cls,
                               locaux=[l for l in locaux if not (obj and code == "infrastructures" and l["id"] == oid)],
                               niveaux=niveaux, liste_ep=liste_ep, TYPES=TYPES_LOCAUX, CAT_MOBILIER=CAT_MOBILIER)

    @app.route("/patrimoine/infrastructures/<int:oid>", methods=["GET", "POST"])
    @H.connexion_requise("patrimoine")
    def patrimoine_local(oid):
        return fiche("infrastructures", oid)

    @app.route("/patrimoine/mobilier/<int:oid>", methods=["GET", "POST"])
    @H.connexion_requise("patrimoine")
    def patrimoine_meuble(oid):
        return fiche("mobilier", oid)

    @app.route("/patrimoine/didactique/<int:oid>", methods=["GET", "POST"])
    @H.connexion_requise("patrimoine")
    def patrimoine_materiel(oid):
        return fiche("didactique", oid)

    @app.route("/patrimoine/<code>/<int:oid>/supprimer", methods=["POST"])
    @H.connexion_requise("patrimoine")
    def patrimoine_supprimer(code, oid):
        if code not in TABLES:
            abort(404)
        table, _spec, titre, liste_ep = TABLES[code]
        obj = q(f"SELECT * FROM {table} WHERE id=? AND ecole_id=?", (oid, H.eco()), un=True)
        if not obj:
            abort(404)
        ex(f"DELETE FROM {table} WHERE id=?", (oid,))
        if code == "infrastructures":  # le mobilier rangé dans ce local n'y est plus rattaché
            ex("UPDATE pat_mobilier SET local_id=NULL WHERE local_id=? AND ecole_id=?", (oid, H.eco()))
        H.journal(f"patrimoine_{code}_suppression", str(oid))
        flash(f"{titre} supprimé.", "warning")
        return redirect(url_for(liste_ep))

    # -------------------------------------------------------------- mouvements
    def objets_mouvement():
        mob = q("""SELECT m.*, c.nom classe_nom, l.designation local_nom FROM pat_mobilier m
                   LEFT JOIN classes c ON c.id=m.classe_id LEFT JOIN pat_locaux l ON l.id=m.local_id
                   WHERE m.ecole_id=? ORDER BY m.categorie""", (H.eco(),))
        did = q("SELECT * FROM pat_didactique WHERE ecole_id=? ORDER BY categorie, designation", (H.eco(),))
        res = []
        for m in mob:
            lib = CAT_MOBILIER.get(m["categorie"], (m["categorie"],))[0] + (f" – {m['designation']}" if m["designation"] else "")
            lieu = m["classe_nom"] or m["local_nom"] or "sans emplacement"
            res.append({"val": f"mobilier:{m['id']}", "lib": f"{lib} ({lieu}, {ETATS.get(m['etat'], '')})",
                        "quantite": m["quantite"], "groupe": "Mobilier"})
        for d in did:
            lib = d["designation"] + (f" – {d['niveau']}" if d["niveau"] else "")
            res.append({"val": f"didactique:{d['id']}", "lib": f"{lib} ({ETATS.get(d['etat'], '')})",
                        "quantite": d["quantite"], "groupe": "Matériel didactique"})
        return res

    @app.route("/patrimoine/mouvements", methods=["GET", "POST"])
    @H.connexion_requise("patrimoine")
    def patrimoine_mouvements():
        if request.method == "POST":
            f = request.form
            d = lire_date(f.get("date"))
            sens = f.get("sens") if f.get("sens") in SENS else None
            objet, _, oid = (f.get("objet") or "").partition(":")
            qte = f.get("quantite", "").strip()
            erreurs = []
            if not d or d > date.today():
                erreurs.append("Date invalide (elle ne peut pas être dans le futur).")
            if not sens:
                erreurs.append("Choisissez le sens du mouvement.")
            if not qte.isdigit() or not 0 < int(qte) <= 100000:
                erreurs.append("Quantité invalide (entier de 1 à 100 000).")
            table = {"mobilier": "pat_mobilier", "didactique": "pat_didactique"}.get(objet)
            obj = q(f"SELECT * FROM {table} WHERE id=? AND ecole_id=?", (int(oid), H.eco()), un=True) \
                if table and oid.isdigit() else None
            if not obj:
                erreurs.append("Choisissez l'article concerné.")
            if not erreurs and sens != "entree" and int(qte) > (obj["quantite"] or 0):
                erreurs.append(f"Quantité supérieure au stock de l'article ({obj['quantite']}).")
            if erreurs:
                for e in erreurs:
                    flash(e, "danger")
                return redirect(url_for("patrimoine_mouvements"))
            n = int(qte)
            nouveau = (obj["quantite"] or 0) + (n if sens == "entree" else -n)
            ex(f"UPDATE {table} SET quantite=?, maj=? WHERE id=?", (nouveau, H.maintenant(), obj["id"]))
            if objet == "mobilier":
                design = CAT_MOBILIER.get(obj["categorie"], (obj["categorie"],))[0] + \
                    (f" – {obj['designation']}" if obj["designation"] else "")
            else:
                design = obj["designation"]
            ex("""INSERT INTO pat_mouvements (ecole_id, date, sens, objet, objet_id, designation, quantite, motif,
                  reference, saisi_par, cree_le) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
               (H.eco(), d.isoformat(), sens, objet, obj["id"], design, n, (f.get("motif") or "").strip()[:300],
                (f.get("reference") or "").strip()[:120], g.user["id"], H.maintenant()))
            H.journal("patrimoine_mouvement", f"{sens} {n} {design}")
            flash(f"{SENS[sens]} enregistrée : {design} — stock {obj['quantite']} → {nouveau}.", "success")
            return redirect(url_for("patrimoine_mouvements"))
        a = request.args
        sql, params = "SELECT m.*, u.nom saisi_nom FROM pat_mouvements m LEFT JOIN utilisateurs u ON u.id=m.saisi_par WHERE m.ecole_id=?", [H.eco()]
        f = {"sens": a.get("sens", ""), "du": a.get("du", ""), "au": a.get("au", "")}
        if f["sens"] in SENS:
            sql += " AND m.sens=?"
            params.append(f["sens"])
        if lire_date(f["du"]):
            sql += " AND m.date>=?"
            params.append(lire_date(f["du"]).isoformat())
        if lire_date(f["au"]):
            sql += " AND m.date<=?"
            params.append(lire_date(f["au"]).isoformat())
        liste = q(sql + " ORDER BY m.date DESC, m.id DESC LIMIT 500", params)
        return render_template("patrimoine_mouvements.html", liste=liste, objets=objets_mouvement(), f=f,
                               onglet="mouvements", SENS=SENS, aujourdhui=date.today().isoformat(),
                               pre=a.get("objet", ""))

    @app.route("/patrimoine/mouvements/<int:mid>/annuler", methods=["POST"])
    @H.connexion_requise("patrimoine")
    def patrimoine_mouvement_annuler(mid):
        m = q("SELECT * FROM pat_mouvements WHERE id=? AND ecole_id=?", (mid, H.eco()), un=True)
        if not m:
            abort(404)
        table = {"mobilier": "pat_mobilier", "didactique": "pat_didactique"}[m["objet"]]
        obj = q(f"SELECT * FROM {table} WHERE id=? AND ecole_id=?", (m["objet_id"], H.eco()), un=True)
        if obj:
            nouveau = (obj["quantite"] or 0) + (-m["quantite"] if m["sens"] == "entree" else m["quantite"])
            if nouveau < 0:
                flash("Annulation impossible : le stock actuel est inférieur à la quantité entrée.", "danger")
                return redirect(url_for("patrimoine_mouvements"))
            ex(f"UPDATE {table} SET quantite=?, maj=? WHERE id=?", (nouveau, H.maintenant(), obj["id"]))
        ex("DELETE FROM pat_mouvements WHERE id=?", (mid,))
        H.journal("patrimoine_mouvement_annule", f"{mid} {m['designation']}")
        flash("Mouvement annulé" + (" et stock rétabli." if obj else " (l'article n'existe plus)."), "warning")
        return redirect(url_for("patrimoine_mouvements"))

    # -------------------------------------------------------------- équipements et services
    @app.route("/patrimoine/equipements", methods=["GET", "POST"])
    @H.connexion_requise("patrimoine")
    def patrimoine_equipements():
        cle = f"e{H.eco()}:patrimoine:equipements"
        if request.method == "POST":
            f = request.form
            d = {k: 1 if f.get(k) else 0 for k, _l in EQUIPEMENTS}
            sup = (f.get("superficie_ha") or "").strip().replace(",", ".")
            nb = (f.get("nb_ouvrages") or "").strip()
            try:
                d["superficie_ha"] = round(float(sup), 2) if sup else None
                if d["superficie_ha"] is not None and not 0 <= d["superficie_ha"] <= 10000:
                    raise ValueError
            except ValueError:
                flash("Superficie du domaine invalide (en hectares, ex. 1,5).", "danger")
                return redirect(url_for("patrimoine_equipements"))
            if nb and (not nb.isdigit() or int(nb) > 10 ** 6):
                flash("Nombre d'ouvrages de la bibliothèque invalide.", "danger")
                return redirect(url_for("patrimoine_equipements"))
            d["nb_ouvrages"] = int(nb) if nb else None
            d["cantine_soutien"] = (f.get("cantine_soutien") or "").strip()[:120]
            d["observations"] = (f.get("observations") or "").strip()[:1000]
            H.doc_ecrire(cle, d)
            H.journal("patrimoine_equipements")
            flash("Équipements et services enregistrés.", "success")
            return redirect(url_for("patrimoine_equipements"))
        return render_template("patrimoine_equipements.html", v=equipements(H.eco()), s=patrimoine_synthese(H.eco()),
                               onglet="equipements", EQUIPEMENTS=EQUIPEMENTS)

    # -------------------------------------------------------------- inventaire annuel
    def donnees_inventaire():
        eid = H.eco()
        s = patrimoine_synthese(eid)
        locaux = q("""SELECT l.*, c.nom classe_nom FROM pat_locaux l LEFT JOIN classes c ON c.id=l.classe_id
                      WHERE l.ecole_id=? ORDER BY l.type, l.designation""", (eid,))
        mob = q("""SELECT m.*, c.nom classe_nom, l.designation local_nom FROM pat_mobilier m
                   LEFT JOIN classes c ON c.id=m.classe_id LEFT JOIN pat_locaux l ON l.id=m.local_id
                   WHERE m.ecole_id=? ORDER BY COALESCE(c.nom, l.designation, 'zzz'), m.categorie""", (eid,))
        did = q("SELECT * FROM pat_didactique WHERE ecole_id=? ORDER BY categorie, niveau, discipline, designation", (eid,))
        d1, d2 = H.bornes_annee()
        mvts = q("SELECT * FROM pat_mouvements WHERE ecole_id=? AND date BETWEEN ? AND ? ORDER BY date", (eid, d1, d2))
        return s, locaux, mob, did, mvts

    def lignes_locaux(locaux):
        res = []
        for i, l in enumerate(locaux, 1):
            det = []
            if l["type"] == "latrines":
                det.append(f"Cabines G {l['cabines_g'] or 0} / F {l['cabines_f'] or 0} / ens. {l['cabines_ens'] or 0}")
            if l["source"]:
                det.append(l["source"])
            if l["type"] == "salle_classe" and not l["utilisee"]:
                det.append("non utilisée")
            res.append([i, TYPES_LOCAUX.get(l["type"], l["type"]), l["designation"], l["classe_nom"] or "",
                        l["annee_service"] or "", (f"{l['superficie']:g}" if l["superficie"] else ""),
                        MURS.get(l["murs"], ""), TOITS.get(l["toit"], ""), FINANCEMENTS.get(l["financement"], ""),
                        ETATS.get(l["etat"], ""), "; ".join(x for x in [", ".join(det), l["besoins"] or ""] if x)])
        return res

    def lignes_mobilier(mob):
        return [[i, CAT_MOBILIER.get(m["categorie"], (m["categorie"],))[0], m["designation"] or "",
                 m["classe_nom"] or m["local_nom"] or "", m["quantite"] or 0, places_unite(m) or "",
                 ETATS.get(m["etat"], ""), m["annee_acquisition"] or "", FINANCEMENTS.get(m["financement"], "")]
                for i, m in enumerate(mob, 1)]

    def lignes_didactique(did):
        return [[i, CAT_DIDACTIQUE.get(d["categorie"], d["categorie"]), d["designation"], d["discipline"] or "",
                 d["niveau"] or "", d["quantite"] or 0, ETATS.get(d["etat"], ""), d["annee_acquisition"] or "",
                 FINANCEMENTS.get(d["financement"], "")] for i, d in enumerate(did, 1)]

    @app.route("/patrimoine/inventaire.pdf")
    @H.connexion_requise("patrimoine")
    def patrimoine_inventaire_pdf():
        s, locaux, mob, did, mvts = donnees_inventaire()
        P = H.pdfs
        v = H.identification()
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Spacer

        def tab(titre, entetes, lignes, largeurs, vide):
            data = [entetes] + ([[esc(x) for x in l] for l in lignes] or [[vide] + [""] * (len(entetes) - 1)])
            return [Spacer(1, 6), P.paragraphe(titre, 9.5, True),
                    P.mini_tableau(data, largeurs=[x * mm for x in largeurs], taille=7)]

        sc, mb, dd, lt, eq = s["salles_classe"], s["mobilier"], s["didactique"], s["latrines"], s["equipements"]
        synth = [["Indicateur", "Valeur"],
                 ["Élèves inscrits (G / F / total)", f"{s['effectifs']['g']} / {s['effectifs']['f']} / {s['effectifs']['t']}"],
                 ["Salles de classe (bon / passable / mauvais)", f"{sc['total']} ({sc['bon']} / {sc['passable']} / {sc['mauvais']})"],
                 ["Salles à réhabiliter", sc["a_rehabiliter"]],
                 ["Latrines : cabines G / F / enseignants", f"{lt['cabines_g']} / {lt['cabines_f']} / {lt['cabines_ens']}"],
                 ["Point d'eau · électricité · clôture", " · ".join(
                     ("oui" if eq[k] else "non") for k in ("point_eau", "electricite", "cloture"))],
                 ["Places assises utilisables / effectif", f"{mb['places_assises']} / {s['effectifs']['t']}"],
                 ["Déficit en places assises", f"{mb['deficit_places']} (≈ {mb['tables_bancs_manquantes']} tables-bancs de 2 places)"],
                 ["Manuels de l'élève (ratio manuels / élève)", f"{dd['manuels_total']} ({ratio_txt(dd['ratio_global'])})"],
                 ["Mouvements de l'année (entrées / sorties / réformes)",
                  f"{s['mouvements_annee']['entree']} / {s['mouvements_annee']['sortie']} / {s['mouvements_annee']['reforme']}"]]
        avant = [KeepTogether([P.paragraphe("SYNTHÈSE", 9.5, True),
                               P.mini_tableau([[esc(x) for x in l] for l in synth], largeurs=[95 * mm, 90 * mm], taille=7.5)]),
                 Spacer(1, 6), P.paragraphe("1. INFRASTRUCTURES (LOCAUX ET OUVRAGES)", 9.5, True)]
        places = [[p["classe"], p["niveau"], p["g"], p["f"], p["effectif"], p["places"], p["deficit"],
                   p["tables_bancs_manquantes"]] for p in mb["par_classe"]]
        manuels = [[m["niveau"], m["discipline"], m["quantite"], m["utilisables"], m["effectif"], ratio_txt(m["ratio"]),
                    m["manquants"]] for m in dd["manuels"]]
        mv = [[P.date_fr(m["date"]), SENS.get(m["sens"], m["sens"]), m["designation"], m["quantite"], m["motif"] or "",
               m["reference"] or ""] for m in mvts]
        apres = (tab("2. MOBILIER", ["N°", "Catégorie", "Désignation", "Emplacement", "Qté", "Places/u", "État",
                                     "Acquis en", "Financement"], lignes_mobilier(mob),
                     [8, 48, 38, 36, 12, 14, 18, 16, 30], "Aucun mobilier enregistré")
                 + tab("3. PLACES ASSISES PAR CLASSE", ["Classe", "Niveau", "G", "F", "Effectif", "Places", "Déficit",
                                                        "Tables-bancs manquantes"], places,
                       [40, 28, 14, 14, 20, 20, 20, 36], "Aucune classe")
                 + tab("4. MATÉRIEL DIDACTIQUE", ["N°", "Catégorie", "Désignation", "Discipline", "Niveau", "Qté", "État",
                                                  "Acquis en", "Financement"], lignes_didactique(did),
                       [8, 40, 44, 34, 20, 12, 16, 16, 30], "Aucun matériel enregistré")
                 + tab("5. MANUELS DE L'ÉLÈVE : RATIO MANUELS / ÉLÈVES", ["Niveau", "Discipline", "Manuels",
                       "Utilisables", "Effectif", "Ratio", "Manquants"], manuels, [30, 60, 20, 22, 20, 20, 22],
                       "Aucun manuel enregistré")
                 + tab("6. MOUVEMENTS DE L'ANNÉE", ["Date", "Sens", "Article", "Qté", "Motif", "Référence"], mv,
                       [22, 20, 70, 14, 60, 34], "Aucun mouvement cette année"))
        if s["besoins"]:
            apres += tab("7. BESOINS DE RÉHABILITATION", ["Ouvrage", "Nature", "État", "Besoins"],
                         [[b["designation"], b["type"], b["etat"], b["besoins"]] for b in s["besoins"]],
                         [50, 40, 20, 110], "")
        titre_dir = v.get("directeur_titre") or "Directeur"
        titre_dir = f"{'LA' if titre_dir.lower().startswith('directrice') else 'LE'} {titre_dir.upper()}"
        pdf = P.document_tableau(
            "INVENTAIRE ANNUEL DU PATRIMOINE", ["N°", "Nature", "Désignation", "Classe", "Année", "m²", "Murs",
                                                "Toit", "Financement", "État", "Détails / besoins"],
            lignes_locaux(locaux) or [["", "Aucune infrastructure enregistrée", "", "", "", "", "", "", "", "", ""]],
            sous_titre=f"Année scolaire {H.config.ANNEE_ACTIVE} — situation au {date.today().strftime('%d/%m/%Y')}",
            infos=[("École", v.get("ecole")), ("Commune", v.get("commune")), ("Année scolaire", v.get("annee")),
                   ("Directeur", v.get("directeur_nom"))],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[7, 25, 38, 18, 12, 10, 16, 20, 22, 15, 50], paysage=True, taille=7, avant=avant, apres=apres,
            signatures=[("LE GESTIONNAIRE / SECRÉTAIRE", "", None, False),
                        (titre_dir, v.get("directeur_nom") or "",
                         P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)],
            notes_bas=["Places assises : mobilier élèves en état bon ou passable. Ratio = manuels utilisables ÷ "
                       "effectif inscrit du niveau."])
        H.journal("patrimoine_inventaire_pdf", H.config.ANNEE_ACTIVE)
        return H.pdf_reponse(pdf, f"inventaire_patrimoine_{H.config.ANNEE_ACTIVE}.pdf")

    @app.route("/patrimoine/inventaire.xlsx")
    @H.connexion_requise("patrimoine")
    def patrimoine_inventaire_xlsx():
        s, locaux, mob, did, mvts = donnees_inventaire()
        v = H.identification()
        haut = [f"{v.get('ecole') or ''} — Inventaire du patrimoine — année scolaire {H.config.ANNEE_ACTIVE}",
                f"DDEMP {v.get('ddemp') or ''} — CS {v.get('cs') or ''} — situation au {date.today().strftime('%d/%m/%Y')}"]
        sc, mb, dd, lt, eq = s["salles_classe"], s["mobilier"], s["didactique"], s["latrines"], s["equipements"]
        synth = [["Élèves inscrits", s["effectifs"]["t"]], ["dont filles", s["effectifs"]["f"]],
                 ["Salles de classe", sc["total"]], ["Salles en bon état", sc["bon"]], ["Salles passables", sc["passable"]],
                 ["Salles en mauvais état", sc["mauvais"]], ["Salles à réhabiliter", sc["a_rehabiliter"]],
                 ["Cabines de latrines garçons", lt["cabines_g"]], ["Cabines de latrines filles", lt["cabines_f"]],
                 ["Cabines de latrines enseignants", lt["cabines_ens"]],
                 ["Point d'eau", "Oui" if eq["point_eau"] else "Non"], ["Électricité", "Oui" if eq["electricite"] else "Non"],
                 ["Clôture", "Oui" if eq["cloture"] else "Non"], ["Places assises utilisables", mb["places_assises"]],
                 ["Déficit en places assises", mb["deficit_places"]], ["Tables-bancs (2 places) manquantes", mb["tables_bancs_manquantes"]],
                 ["Manuels de l'élève", dd["manuels_total"]], ["Ratio manuels / élève", dd["ratio_global"]],
                 ["Entrées de l'année", s["mouvements_annee"]["entree"]], ["Sorties de l'année", s["mouvements_annee"]["sortie"]],
                 ["Réformes de l'année", s["mouvements_annee"]["reforme"]]]
        feuilles = [
            ("Synthèse", ["Indicateur", "Valeur"], synth, {"titre_haut": haut}),
            ("Infrastructures", ["N°", "Nature", "Désignation", "Classe", "Année", "Superficie (m²)", "Murs", "Toit",
                                 "Financement", "État", "Détails / besoins"], lignes_locaux(locaux), {"titre_haut": haut}),
            ("Mobilier", ["N°", "Catégorie", "Désignation", "Emplacement", "Quantité", "Places / unité", "État",
                          "Année d'acquisition", "Financement"], lignes_mobilier(mob), {"titre_haut": haut}),
            ("Places assises", ["Classe", "Niveau", "Garçons", "Filles", "Effectif", "Places utilisables", "Déficit",
                                "Tables-bancs manquantes"],
             [[p["classe"], p["niveau"], p["g"], p["f"], p["effectif"], p["places"], p["deficit"],
               p["tables_bancs_manquantes"]] for p in mb["par_classe"]], {"titre_haut": haut}),
            ("Matériel didactique", ["N°", "Catégorie", "Désignation", "Discipline", "Niveau", "Quantité", "État",
                                     "Année d'acquisition", "Financement"], lignes_didactique(did), {"titre_haut": haut}),
            ("Manuels", ["Niveau", "Discipline", "Manuels", "Utilisables", "Effectif", "Ratio manuels/élève", "Manquants"],
             [[m["niveau"], m["discipline"], m["quantite"], m["utilisables"], m["effectif"], m["ratio"], m["manquants"]]
              for m in dd["manuels"]], {"titre_haut": haut}),
            ("Mouvements", ["Date", "Sens", "Article", "Quantité", "Motif", "Référence"],
             [[H.pdfs.date_fr(m["date"]), SENS.get(m["sens"], m["sens"]), m["designation"], m["quantite"],
               m["motif"] or "", m["reference"] or ""] for m in mvts], {"titre_haut": haut}),
        ]
        H.journal("patrimoine_inventaire_xlsx", H.config.ANNEE_ACTIVE)
        try:
            return H.xlsx.reponse_classeur(f"inventaire_patrimoine_{H.config.ANNEE_ACTIVE}.xlsx", feuilles)
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("patrimoine_accueil"))
