# -*- coding: utf-8 -*-
"""v1.22 — Bureaux de l'UASCEP (Union des associations scolaires et culturelles des écoles primaires) : membres et
responsables par école, unité pédagogique, zone pédagogique, circonscription scolaire et DDEMP.

Spécification commune à toutes les applications (outils/uascep/spec.md) : mêmes rubriques, même fichier Excel
(feuilles « Membres UASCEP » et « Bureaux »), pour qu'un bureau saisi dans une application s'importe dans une autre.

Périmètres
* éditions école (privée / publique) : le bureau de l'école (écriture : administrateur, fondateur, directeur) ;
  bureaux de son UP et de sa zone en lecture (importés) ;
* édition CS : bureaux des écoles, des UP, des zones et de la circonscription (responsable, chef de service, CP) ;
* édition DDEMP : tous les niveaux du département ;
* enseignant (portail /enseignant, application Enseignant) : lecture seule.

Routes
* /uascep                              uascep            onglets École · UP · Zone · CS · DDEMP · Synthèse · Anciens
* /uascep/bureau/<bid>                 uascep_bureau     GET/POST : bureau (0 = nouveau, ?niveau=&entite=)
* /uascep/membre/<mid>                 uascep_membre     GET/POST : membre (0 = ajouter, ?bureau=)
* /uascep/membre/<mid>/supprimer       POST
* /uascep/bureau/<bid>/reinitialiser   POST : vide le bureau (archive=1 : l'archive dans « Anciens bureaux »)
* /uascep/reinitialiser                POST : tous les bureaux d'un niveau
* /uascep/bureau/<bid>/renouveler      POST : copie du bureau sur un nouveau mandat (l'ancien est archivé)
* /uascep.pdf · /uascep.xlsx · /uascep/import (POST) · /uascep/modele.xlsx
v1.24 — cachet et signature digitale de chaque responsable (tous niveaux) et documents signés (cachets, visa de l'autorité
hiérarchique, code de vérification et QR) :
* /uascep/membre/<mid>/cachet           uascep_cachet     GET/POST : cachet généré (rond « UASCEP » + niveau + entité autour,
                                                           fonction au centre ; ou griffe rectangulaire) ou image importée ;
                                                           signature dessinée ou importée ; aperçu
* /uascep/membre/<mid>/cachet/reinitialiser             POST
* /uascep/bureau/<bid>/composition.pdf · /uascep/bureau/<bid>/pv.pdf[?type=installation] · /uascep/membre/<mid>/attestation.pdf
* /uascep/liste.pdf                     liste des bureaux (président, SG, trésorier, mandat)
"""
import io
import re
from datetime import date, datetime, timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

SCHEMA = """
CREATE TABLE IF NOT EXISTS uascep_bureaux (
    id INTEGER PRIMARY KEY, ecole_id INTEGER, niveau TEXT NOT NULL, entite TEXT NOT NULL, entite_lib TEXT,
    date_election TEXT, duree INTEGER DEFAULT 2, date_fin TEXT, date_installation TEXT, ag_date TEXT, ag_lieu TEXT,
    pv TEXT, observations TEXT, statut TEXT NOT NULL DEFAULT 'actif', archive_le TEXT, cree_le TEXT, maj TEXT
);
CREATE INDEX IF NOT EXISTS ix_uascep_b ON uascep_bureaux(ecole_id, niveau, entite, statut);
CREATE TABLE IF NOT EXISTS uascep_membres (
    id INTEGER PRIMARY KEY, bureau_id INTEGER NOT NULL REFERENCES uascep_bureaux(id) ON DELETE CASCADE,
    ordre INTEGER DEFAULT 1, nom TEXT NOT NULL, prenoms TEXT, sexe TEXT, ecole TEXT, up TEXT, zone TEXT, rup TEXT,
    fonction TEXT, qualite TEXT, contact TEXT, email TEXT, date_election TEXT, duree INTEGER, date_fin TEXT,
    date_installation TEXT, observations TEXT, maj TEXT
);
CREATE INDEX IF NOT EXISTS ix_uascep_m ON uascep_membres(bureau_id, ordre);
"""
NIVEAUX = [("ECOLE", "École"), ("UP", "Unité pédagogique"), ("ZONE", "Zone pédagogique"), ("CS", "Circonscription scolaire"),
           ("DDEMP", "Département (DDEMP)")]
NIV_LIB = dict(NIVEAUX)
FONCTIONS = ["Président", "Vice-président", "Secrétaire général", "Secrétaire général adjoint", "Trésorier général",
             "Trésorier général adjoint", "Rapporteur", "Commissaire aux comptes", "Responsable sport", "Responsable culture",
             "Responsable matériel", "Responsable santé / hygiène", "Responsable genre", "Conseiller", "Membre"]
QUALITES = ["Directeur", "Directrice", "Enseignant", "Enseignante", "CP", "CCS", "Parent d'élève", "Élève", "Autre"]
ENT_MEMBRES = ["Niveau", "Entité", "N° d'ordre", "Nom", "Prénoms", "Sexe", "École", "UP", "Zone pédagogique", "Nom du RUP", "Fonction",
               "Qualité", "Contact", "E-mail", "Date d'élection", "Durée du mandat (ans)", "Date de fin de mandat", "Statut du mandat",
               "Date d'installation", "Observations"]
ENT_BUREAUX = ["Niveau", "Entité", "Date d'élection", "Durée du mandat (ans)", "Date de fin de mandat", "Date d'installation",
               "Date de l'assemblée générale", "Lieu de l'assemblée générale", "PV", "Observations", "Statut"]
CHAMPS_M = ["ordre", "nom", "prenoms", "sexe", "ecole", "up", "zone", "rup", "fonction", "qualite", "contact", "email",
            "date_election", "duree", "date_fin", "date_installation", "observations"]
# v1.24 : cachet et signature digitale de chaque responsable (stockés avec le membre)
CHAMPS_SIG = ["cachet_mode", "cachet_forme", "cachet_couleur", "cachet_sup", "cachet_inf", "cachet_centre", "cachet_image", "signature"]
CHAMPS_B = ["entite_lib", "date_election", "duree", "date_fin", "date_installation", "ag_date", "ag_lieu", "pv", "observations"]

# v1.24 — vie du bureau par saison (année scolaire) : mêmes listes que le module commun (outils/uascep/uascep.js)
DISCIPLINES = ["Football", "Handball", "Volleyball", "Basketball", "Athlétisme", "Pétanque", "Tennis de table", "Judo", "Lutte traditionnelle",
               "Jeux traditionnels", "Jeux de société (awalé, dames…)", "Course en sac", "Chant / chorale", "Danse", "Théâtre / sketch",
               "Poésie / récitation", "Dessin", "Quiz / culture générale"]
CATEGORIES = ["Minimes", "Cadets", "Benjamins", "Poussins", "Toutes catégories"]
CAT_FIN = {"Recette": ["Cotisations des écoles", "Subventions", "Dons et parrainages", "Droits d’engagement", "Recettes des manifestations",
                       "Report de la saison précédente", "Divers"],
           "Dépense": ["Transport", "Restauration", "Équipements et matériel", "Arbitrage", "Récompenses (coupes, médailles, prix)", "Soins et secours",
                       "Communication", "Fournitures", "Organisation (sites, sonorisation)", "Divers"]}
LISTES = {"discipline": DISCIPLINES, "categorie": CATEGORIES, "categorie_fin": CAT_FIN["Recette"] + CAT_FIN["Dépense"],
          "statut": ["Réalisée", "Prévue", "Reportée", "Annulée"], "nature": ["Recette", "Dépense"], "genre": ["Garçons", "Filles", "Mixte"],
          "phase": ["Éliminatoires", "Poules", "Quarts de finale", "Demi-finales", "Finale", "Rencontre amicale", "Festival / démonstration",
                    "Compétition culturelle"],
          "type": ["Réunion ordinaire du bureau", "Réunion extraordinaire", "Assemblée générale", "Réunion technique (commission)",
                   "Réunion avec les directeurs", "Réunion de bilan"],
          "etat": ["Bon", "Usagé", "À réparer", "Hors d’usage"], "origine": ["Achat", "Don", "Dotation", "Prêt"], "oui_non": ["Oui", "Non"]}
# (clé, libellé, type) ; types : texte, long, date, entier, montant, choix:<liste>, liste:<liste> (saisie libre proposée)
# v1.25 : clés, libellés et ordre des colonnes identiques au module commun (outils/uascep/uascep.js, SPEC) ; colonnes calculées
# (CALC) insérées dans l'Excel à la même place ; rubriques propres à SCOLARIS en fin de feuille (EXTRA).
COLL = {
    "activites": {"titre": "Calendrier, compétitions et résultats", "feuille": "Activités", "unite": "activité", "oblig": "discipline", "champs": [
        ("date", "Date", "date"), ("discipline", "Discipline", "liste:discipline"), ("categorie", "Catégorie", "liste:categorie"),
        ("genre", "Genre", "choix:genre"), ("phase", "Phase", "liste:phase"), ("lieu", "Lieu / site", "texte"), ("ecoles", "Écoles", "entier"),
        ("equipes", "Équipes", "entier"), ("pg", "Participants G", "entier"), ("pf", "Participants F", "entier"),
        ("encadreurs", "Encadreurs", "entier"), ("resultats", "Résultats / classement", "long"), ("qualifies", "Qualifiés au niveau supérieur", "long"),
        ("observations", "Observations", "long"),
        ("intitule", "Activité / compétition", "texte"), ("statut", "Statut", "choix:statut"), ("date_fin", "Fin (plusieurs jours)", "date"),
        ("distinctions", "Distinctions et récompenses", "long")]},
    "engagements": {"titre": "Fiches d’engagement des équipes", "feuille": "Engagements", "unite": "engagement", "oblig": "ecole", "champs": [
        ("ecole", "École", "texte"), ("discipline", "Discipline", "liste:discipline"), ("categorie", "Catégorie", "liste:categorie"),
        ("genre", "Genre", "choix:genre"), ("equipe", "Nom de l’équipe", "texte"), ("jg", "Joueurs G", "entier"), ("jf", "Joueuses F", "entier"),
        ("encadreur", "Encadreur", "texte"), ("contact", "Contact", "texte"), ("droit", "Droit d’engagement (F)", "montant"),
        ("paye", "Payé", "choix:oui_non"), ("date", "Date d’engagement", "date"), ("observations", "Observations", "long")]},
    "reunions": {"titre": "Réunions et comptes rendus (rapporteur)", "feuille": "Réunions", "unite": "réunion", "oblig": "date", "champs": [
        ("date", "Date", "date"), ("heure", "Heure", "texte"), ("type", "Nature", "liste:type"), ("lieu", "Lieu", "texte"),
        ("ordre", "Ordre du jour", "long"), ("presents", "Membres présents", "long"), ("invites", "Invités / autres participants", "long"),
        ("deroulement", "Déroulement / échanges", "long"), ("decisions", "Décisions", "long"), ("recommandations", "Recommandations", "long"),
        ("prochaine", "Prochaine réunion", "date"), ("redacteur", "Rapporteur (rédacteur)", "texte"),
        ("absents", "Absents (excusés / non excusés)", "long")]},
    "caisse": {"titre": "Journal de caisse (trésorier)", "feuille": "Caisse", "unite": "opération", "oblig": "montant", "champs": [
        ("date", "Date", "date"), ("nature", "Nature", "choix:nature"), ("categorie", "Catégorie", "liste:categorie_fin"), ("libelle", "Libellé", "texte"),
        ("ecole", "École (cotisation)", "texte"), ("piece", "Pièce justificative n°", "texte"), ("montant", "Montant (F)", "montant"),
        ("observations", "Observations", "long")]},
    "budget": {"titre": "Budget prévisionnel et réalisé", "feuille": "Budget", "unite": "ligne de budget", "oblig": "categorie", "champs": [
        ("nature", "Nature", "choix:nature"), ("categorie", "Catégorie", "liste:categorie_fin"), ("libelle", "Précision", "texte"),
        ("prevu", "Prévu (F)", "montant")]},
    "materiel": {"titre": "Inventaire du matériel sportif", "feuille": "Matériel", "unite": "article", "oblig": "designation", "champs": [
        ("designation", "Désignation", "texte"), ("discipline", "Discipline", "liste:discipline"), ("quantite", "Quantité", "entier"),
        ("etat", "État", "choix:etat"), ("origine", "Origine", "liste:origine"), ("date", "Date d’acquisition", "date"),
        ("valeur", "Valeur (F)", "montant"), ("detenteur", "Détenteur / lieu de garde", "texte"), ("observations", "Observations", "long")]},
}
# colonnes du fichier Excel commun (ordre du module JS) : (clé ou calcul, libellé) ; « = » : colonne calculée
EXCEL = {
    "activites": ["date", "discipline", "categorie", "genre", "phase", "lieu", "ecoles", "equipes", "pg", "pf", ("=pt", "Total"), "encadreurs",
                  "resultats", "qualifies", "observations", "intitule", "statut", "date_fin", "distinctions"],
    "engagements": ["ecole", "discipline", "categorie", "genre", "equipe", "jg", "jf", ("=jt", "Total"), "encadreur", "contact", "droit", "paye", "date",
                    "observations"],
    "reunions": [k for k, _l, _t in COLL["reunions"]["champs"]],
    "caisse": ["date", "nature", "categorie", "libelle", "ecole", "piece", ("=recette", "Recette (F)"), ("=depense", "Dépense (F)"), ("=solde", "Solde (F)"),
               "observations"],
    "budget": ["nature", "categorie", "libelle", "prevu", ("=realise", "Réalisé (F)"), ("=ecart", "Écart (F)"), ("=taux", "Taux")],
    "materiel": [k for k, _l, _t in COLL["materiel"]["champs"]],
}
# v1.25 : anciennes colonnes (1.24) renommées
RENOMMER = {"activites": {"participants_g": "pg", "participants_f": "pf"},
            "engagements": {"effectif_g": "jg", "effectif_f": "jf", "responsable": "encadreur"},
            "reunions": {"ordre_du_jour": "ordre"}, "caisse": {"sens": "nature"}, "budget": {"sens": "nature"}, "materiel": {"provenance": "origine"}}
RAPPORT_TEXTES = [("titre", "Titre du rapport"), ("contexte", "Contexte"), ("organisation", "Organisation"),
                  ("resultats", "Résultats et distinctions"), ("difficultes", "Difficultés rencontrées"), ("recommandations", "Recommandations"),
                  ("conclusion", "Conclusion")]
# documents de la saison : (titre, signataires, type de document vérifiable) ; R rapporteur, SG, T trésorier, CC commissaire aux comptes,
# P président, V visa de l'autorité hiérarchique
DOCS_SAISON = {"journal": ("Calendrier, résultats et journal des activités", ["R", "SG", "P", "V"], "uascep_journal"),
               "engagements": ("Fiches d'engagement des équipes", ["SG", "P", "V"], "uascep_engagements"),
               "finances": ("État financier et journal de caisse", ["T", "CC", "P"], "uascep_finances"),
               "inventaire": ("Inventaire du matériel sportif", ["T", "P", "V"], "uascep_inventaire")}
DOCS_RUB = {"activites": "journal", "engagements": "engagements", "caisse": "finances", "budget": "finances", "materiel": "inventaire"}


def fcfa(n):
    return f"{int(n or 0):,}".replace(",", " ") + " FCFA"


def fin_mandat(election, duree):
    try:
        d = datetime.strptime(election, "%Y-%m-%d").date()
        return d.replace(year=d.year + int(duree or 2)).isoformat()
    except (ValueError, TypeError):
        return ""


def statut_mandat(fin, auj=None):
    auj = auj or date.today()
    if not fin:
        return "Date de fin non renseignée"
    try:
        f = datetime.strptime(fin, "%Y-%m-%d").date()
    except ValueError:
        return "Date de fin non renseignée"
    if f < auj:
        return "Expiré"
    if f <= auj + timedelta(days=90):
        return "À renouveler"
    return "En cours"


def jjmmaaaa(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return ""


def iso(v):
    import outils_xlsx as X
    return X.date_iso(v)


def niveau_de(v):
    t = re.sub(r"[^a-z]", "", __import__("unicodedata").normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower())
    for code, lib in NIVEAUX:
        l = re.sub(r"[^a-z]", "", __import__("unicodedata").normalize("NFKD", lib).encode("ascii", "ignore").decode().lower())
        if t in (code.lower(), l) or (t and l.startswith(t)):
            return code
    return {"circonscription": "CS", "departement": "DDEMP", "unitepedagogique": "UP", "zone": "ZONE", "ecole": "ECOLE"}.get(t)


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config
    H.schema(SCHEMA)
    for col in CHAMPS_SIG:
        H.ajouter_colonne("uascep_membres", col, "TEXT")

    # ------------------------------------------------------------------ périmètre
    def juridiction():
        return config.EDITION in ("cs", "ddemp")

    def niveaux_visibles():
        if config.EDITION == "ddemp":
            return [c for c, _ in NIVEAUX]
        if config.EDITION == "cs":
            return ["ECOLE", "UP", "ZONE", "CS"]
        return ["ECOLE", "UP", "ZONE"]

    def niveaux_ecriture():
        role = g.get("role_reel") or g.user["role"]     # v1.28 : rôle réel (CP, chef de service…) même sur une page d'école
        if config.EDITION == "enseignant" or role == "enseignant":
            return []
        if juridiction():
            if role in ("admin", "fondateur", "responsable", "chef_service"):
                return niveaux_visibles()
            if role == "cp":
                return ["ECOLE", "UP", "ZONE"]
            if role == "directeur":                     # v1.28 : directeur d'une école de la juridiction
                return ["ECOLE"]
            return []
        return ["ECOLE"] if role in ("admin", "fondateur", "directeur") else []

    def cle_ecole():
        return None if juridiction() else H.eco()

    def ident():
        try:
            return {x["cle"]: x["valeur"] for x in H.synoptique_identite(H.eco())}
        except Exception:  # noqa: BLE001
            return {}

    def entites(niveau):
        """[(clé, libellé, {zone, up, rup})] des entités du niveau dans le périmètre."""
        if not juridiction():
            i = ident()
            nom_e = config.ECOLE.get("nom") or i.get("epp") or "École"
            if niveau == "ECOLE":
                return [(str(H.eco()), nom_e, {"ecole": nom_e, "up": i.get("up", ""), "zone": i.get("zone_numero", ""), "rup": i.get("rup_nom", "")})]
            if niveau == "UP":
                return [(i["up"], i["up"], {"up": i["up"], "zone": i.get("zone_numero", ""), "rup": i.get("rup_nom", "")})] if i.get("up") else []
            if niveau == "ZONE":
                return [(i["zone_numero"], f"Zone {i['zone_numero']}", {"zone": i["zone_numero"]})] if i.get("zone_numero") else []
            return []
        try:
            if niveau == "ECOLE":
                return [(str(r["id"]), r["nom"], {"ecole": r["nom"], "zone": r["zone"] or "", "up": "", "rup": ""})
                        for r in q("SELECT e.id, e.nom, z.nom zone FROM jur_ecoles e LEFT JOIN jur_zones z ON z.id=e.zone_id WHERE COALESCE(e.actif,1)=1 ORDER BY z.ordre, e.nom")]
            if niveau == "UP":
                return [(r["nom"], r["nom"], {"up": r["nom"], "zone": r["zone"] or "", "rup": r["rup_nom"] or ""})
                        for r in q("SELECT u.nom, u.rup_nom, z.nom zone FROM jur_up u LEFT JOIN jur_zones z ON z.id=u.zone_id WHERE COALESCE(u.actif,1)=1 ORDER BY z.ordre, u.nom")]
            if niveau == "ZONE":
                return [(r["nom"], r["nom"], {"zone": r["nom"]}) for r in q("SELECT nom FROM jur_zones ORDER BY cs_id, ordre, nom")]
            if niveau == "CS":
                s = q("SELECT * FROM jur_structure WHERE id=1", un=True)
                if config.EDITION == "cs":
                    nom_cs = (s["cs"] or s["nom"]) if s else "Circonscription scolaire"
                    return [(nom_cs, nom_cs, {})]
                return [(r["nom"], r["nom"], {}) for r in q("SELECT nom FROM jur_cs WHERE COALESCE(actif,1)=1 ORDER BY nom")]
            if niveau == "DDEMP":
                s = q("SELECT * FROM jur_structure WHERE id=1", un=True)
                dep = (s["departement"] or s["nom"]) if s else "Département"
                return [(dep, f"DDEMP — {dep}", {})]
        except Exception:  # noqa: BLE001
            return []
        return []

    def bureau(bid):
        r = q("SELECT * FROM uascep_bureaux WHERE id=?", (bid,), un=True)
        if not r or r["niveau"] not in niveaux_visibles() or (r["ecole_id"] or None) != cle_ecole():
            abort(404)
        g.uascep_logo_bureau = dict(r)      # v1.25 : bandeau « logo UASCEP » des documents du bureau
        return r

    def exiger_ecriture(niveau):
        if niveau not in niveaux_ecriture():
            abort(403)

    def bureau_actif(niveau, entite, creer=False, lib=""):
        r = q("SELECT * FROM uascep_bureaux WHERE COALESCE(ecole_id,0)=COALESCE(?,0) AND niveau=? AND entite=? AND statut='actif' ORDER BY id DESC",
              (cle_ecole(), niveau, entite), un=True)
        if r or not creer:
            return r
        bid = ex("INSERT INTO uascep_bureaux (ecole_id, niveau, entite, entite_lib, duree, statut, cree_le, maj) VALUES (?,?,?,?,2,'actif',?,?)",
                 (cle_ecole(), niveau, entite, lib, H.maintenant(), H.maintenant()))
        return q("SELECT * FROM uascep_bureaux WHERE id=?", (bid,), un=True)

    def membres(bid):
        return [dict(m, statut=statut_mandat(m["date_fin"])) for m in q("SELECT * FROM uascep_membres WHERE bureau_id=? ORDER BY ordre, id", (bid,))]

    def lignes_niveau(niveau, filtres=None, statut="actif"):
        f = filtres or {}
        out = []
        for b in q("SELECT * FROM uascep_bureaux WHERE COALESCE(ecole_id,0)=COALESCE(?,0) AND niveau=? AND statut=? ORDER BY entite_lib, entite, id",
                   (cle_ecole(), niveau, statut)):
            for m in membres(b["id"]):
                if any(v and (str(m.get(k) or "") != v) for k, v in f.items()):
                    continue
                out.append((b, m))
        return out

    # ------------------------------------------------------------------ v1.28 : onglets « Ajouter un membre », Bureaux, Vie du bureau…
    QUI_ECRIT = {"ECOLE": "le directeur / la directrice de l'école ou l'administrateur",
                 "UP": "le conseiller pédagogique (CP / RUP) ou l'administrateur de l'application de la circonscription",
                 "ZONE": "le conseiller pédagogique (CP) ou l'administrateur de l'application de la circonscription",
                 "CS": "le chef de la circonscription scolaire ou l'administrateur de l'application CS",
                 "DDEMP": "le directeur départemental ou l'administrateur de l'application DDEMP"}

    def contexte_onglets(actif):
        return {"u_onglet": actif, "ecrire": niveaux_ecriture(), "NIV_LIB": NIV_LIB, "QUI_ECRIT": QUI_ECRIT,
                "NIVEAUX": [(c, l) for c, l in NIVEAUX if c in niveaux_visibles()], "role_lib": g.get("role_reel") or g.user["role"]}

    def resoudre_entite(niveau, texte):
        """Entité saisie (clé, libellé, ou saisie libre) -> (clé, libellé, infos)."""
        t = (texte or "").strip()
        if not juridiction() and niveau == "ECOLE" and entites("ECOLE"):
            return entites("ECOLE")[0]                  # édition école : l'école elle-même
        n = re.sub(r"\s+", " ", t).lower()
        for k, l, i in entites(niveau):
            if n in (str(k).lower(), (l or "").lower()):
                return k, l, i
        return t, t, {}

    @app.route("/uascep/ajouter", methods=["GET", "POST"])
    @H.connexion_requise("uascep")
    def uascep_ajouter():
        ecr = niveaux_ecriture()
        niveau = (request.values.get("niveau") or (ecr[0] if ecr else "")).strip()
        entite_txt = (request.values.get("entite") or "").strip()
        if not entite_txt and niveau in ecr and not juridiction():
            ents = entites(niveau)
            entite_txt = ents[0][1] if ents else (config.ECOLE.get("nom") or "" if niveau == "ECOLE" else "")
        m = {"ordre": "", "duree": 2}
        if request.method == "POST":
            if niveau not in ecr:
                abort(403)
            f = request.form
            d = {k: (f.get(k) or "").strip()[:300] for k in CHAMPS_M}
            err = []
            if not entite_txt:
                err.append("Indiquez l'entité (école, UP, zone, CS ou DDEMP) : choisissez-la dans la liste ou saisissez son nom.")
            if not d["nom"]:
                err.append("Le nom est obligatoire.")
            d["sexe"] = d["sexe"] if d["sexe"] in ("M", "F") else ""
            for k in ("date_election", "date_fin", "date_installation"):
                d[k] = iso(d[k]) if d[k] else ""
            try:
                d["duree"] = int(d["duree"] or 2)
                d["ordre"] = int(d["ordre"]) if d["ordre"] else None
            except ValueError:
                err.append("N° d'ordre et durée du mandat : nombres entiers.")
            if d["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", d["email"]):
                err.append("Adresse e-mail invalide.")
            if err:
                for e in err:
                    flash(e, "danger")
                return render_template("uascep_ajouter.html", m=dict(m, **d), niveau=niveau, entite=entite_txt, FONCTIONS=FONCTIONS, QUALITES=QUALITES,
                                       entites_par={c: entites(c) for c in ecr}, **contexte_onglets("ajouter")), 400
            cle, lib, info = resoudre_entite(niveau, entite_txt)
            b = bureau_actif(niveau, cle, creer=True, lib=lib)
            if not b["date_election"] and d["date_election"]:
                ex("UPDATE uascep_bureaux SET date_election=?, duree=?, date_fin=?, maj=? WHERE id=?",
                   (d["date_election"], d["duree"], d["date_fin"] or fin_mandat(d["date_election"], d["duree"]), H.maintenant(), b["id"]))
            for k in ("ecole", "up", "zone", "rup"):
                d[k] = d[k] or info.get(k, "")
            if d["ordre"] is None:
                d["ordre"] = q("SELECT COALESCE(MAX(ordre),0)+1 n FROM uascep_membres WHERE bureau_id=?", (b["id"],), un=True)["n"]
            if d["date_election"] and not d["date_fin"]:
                d["date_fin"] = fin_mandat(d["date_election"], d["duree"])
            mid = ex("INSERT INTO uascep_membres (bureau_id, " + ", ".join(CHAMPS_M) + ", maj) VALUES (?," + ",".join("?" * len(CHAMPS_M)) + ",?)",
                     (b["id"],) + tuple(d[k] for k in CHAMPS_M) + (H.maintenant(),))
            H.journal("uascep_membre", f"{NIV_LIB[niveau]} {cle} : {d['nom']} {d['prenoms']}")
            flash(f"Membre enregistré dans le bureau {NIV_LIB[niveau]} — {lib}. Vous pouvez maintenant créer son cachet et sa signature.", "success")
            if f.get("suite") == "autre":
                return redirect(url_for("uascep_ajouter", niveau=niveau, entite=lib))
            if f.get("suite") == "cachet":
                return redirect(url_for("uascep_cachet", mid=mid))
            return redirect(url_for("uascep", onglet=niveau, entite=cle))
        return render_template("uascep_ajouter.html", m=m, niveau=niveau, entite=entite_txt, FONCTIONS=FONCTIONS, QUALITES=QUALITES,
                               entites_par={c: entites(c) for c in ecr}, **contexte_onglets("ajouter"))

    def bureaux_visibles(statut="actif"):
        vis = niveaux_visibles()
        return [dict(b, n=q("SELECT COUNT(*) n FROM uascep_membres WHERE bureau_id=?", (b["id"],), un=True)["n"], mandat=statut_mandat(b["date_fin"]))
                for b in q("SELECT * FROM uascep_bureaux WHERE COALESCE(ecole_id,0)=COALESCE(?,0) AND statut=? AND niveau IN ({}) ORDER BY niveau, entite_lib, entite"
                           .format(",".join("?" * len(vis))), (cle_ecole(), statut, *vis))]

    @app.route("/uascep/onglet/<quoi>")
    @H.connexion_requise("uascep")
    def uascep_onglet(quoi):
        if quoi not in ("bureaux", "vie", "documents", "logo", "importer", "aide"):
            abort(404)
        return render_template("uascep_onglet.html", quoi=quoi, bureaux=bureaux_visibles(), jjmmaaaa=jjmmaaaa, ENT_MEMBRES=ENT_MEMBRES,
                               **contexte_onglets(quoi))

    # ------------------------------------------------------------------ pages
    @app.route("/uascep")
    @H.connexion_requise("uascep")
    def uascep():
        vis = niveaux_visibles()
        onglet = request.args.get("onglet") or vis[0]
        if onglet not in vis + ["SYNTHESE", "ANCIENS"]:
            abort(404)
        ctx = dict(contexte_onglets("membres"), onglet=onglet, FONCTIONS=FONCTIONS, jjmmaaaa=jjmmaaaa, statut_mandat=statut_mandat)
        if onglet in vis:
            ents = entites(onglet)
            f = {k: (request.args.get(k) or "").strip() for k in ("zone", "up", "ecole") if request.args.get(k)}
            entite = request.args.get("entite") or ""
            if not juridiction() and ents:
                entite = entite or ents[0][0]
            b = bureau_actif(onglet, entite) if entite else None
            ctx.update(entites=ents, entite=entite, bureau=b, membres=membres(b["id"]) if b else [], filtres=f,
                       toutes=lignes_niveau(onglet, f) if not entite else [],
                       zones=sorted({e[2].get("zone", "") for e in entites("ECOLE") + entites("UP") if e[2].get("zone")}),
                       ups=sorted({e[2].get("up", "") for e in entites("UP") if e[2].get("up")}))
        elif onglet == "SYNTHESE":
            syn = []
            par_fonction, par_sexe = {}, {"M": 0, "F": 0, "": 0}
            alertes = []
            for c in vis:
                bs = q("SELECT * FROM uascep_bureaux WHERE COALESCE(ecole_id,0)=COALESCE(?,0) AND niveau=? AND statut='actif'", (cle_ecole(), c))
                nm = 0
                for b in bs:
                    ms = membres(b["id"])
                    nm += len(ms)
                    for m in ms:
                        par_fonction[m["fonction"] or "—"] = par_fonction.get(m["fonction"] or "—", 0) + 1
                        par_sexe[m["sexe"] if m["sexe"] in ("M", "F") else ""] += 1
                    st = statut_mandat(b["date_fin"])
                    if st in ("Expiré", "À renouveler"):
                        alertes.append((NIV_LIB[c], b["entite_lib"] or b["entite"], st, jjmmaaaa(b["date_fin"])))
                syn.append((NIV_LIB[c], len(bs), nm))
            ctx.update(syn=syn, par_fonction=sorted(par_fonction.items(), key=lambda x: FONCTIONS.index(x[0]) if x[0] in FONCTIONS else 99),
                       par_sexe=par_sexe, alertes=alertes)
        else:
            ctx["anciens"] = [(b, membres(b["id"])) for b in q("SELECT * FROM uascep_bureaux WHERE COALESCE(ecole_id,0)=COALESCE(?,0) AND statut='archive' AND niveau IN ({}) ORDER BY archive_le DESC, id DESC".format(",".join("?" * len(vis))), (cle_ecole(), *vis))]
        return render_template("uascep.html", **ctx)

    def lire_bureau(f, b=None):
        d = {k: (f.get(k) or "").strip()[:300] for k in CHAMPS_B}
        for k in ("date_election", "date_fin", "date_installation", "ag_date"):
            d[k] = iso(d[k]) if d[k] else ""
        try:
            d["duree"] = max(1, min(10, int(d["duree"] or 2)))
        except ValueError:
            d["duree"] = 2
        if d["date_election"] and not d["date_fin"]:
            d["date_fin"] = fin_mandat(d["date_election"], d["duree"])
        return d

    @app.route("/uascep/bureau/<int:bid>", methods=["GET", "POST"])
    @H.connexion_requise("uascep")
    def uascep_bureau(bid):
        if bid:
            b = dict(bureau(bid))
            niveau, entite = b["niveau"], b["entite"]
        else:
            niveau, entite = request.values.get("niveau") or "", request.values.get("entite") or ""
            if niveau not in niveaux_visibles():
                abort(404)
            lib = next((e[1] for e in entites(niveau) if e[0] == entite), entite)
            if not entite:
                abort(400)
            b = {"id": 0, "niveau": niveau, "entite": entite, "entite_lib": lib, "duree": 2}
        exiger_ecriture(niveau)
        if request.method == "POST":
            d = lire_bureau(request.form)
            if not bid:
                bb = bureau_actif(niveau, entite, creer=True, lib=d["entite_lib"] or b["entite_lib"])
                bid = bb["id"]
            ex("UPDATE uascep_bureaux SET " + ", ".join(f"{k}=?" for k in CHAMPS_B) + ", maj=? WHERE id=?",
               tuple(d[k] for k in CHAMPS_B) + (H.maintenant(), bid))
            H.journal("uascep_bureau", f"{NIV_LIB[niveau]} {entite}")
            flash("Bureau enregistré.", "success")
            return redirect(url_for("uascep", onglet=niveau, entite=entite))
        return render_template("uascep_bureau.html", b=b, NIV_LIB=NIV_LIB)

    @app.route("/uascep/membre/<int:mid>", methods=["GET", "POST"])
    @H.connexion_requise("uascep")
    def uascep_membre(mid):
        if mid:
            m = q("SELECT * FROM uascep_membres WHERE id=?", (mid,), un=True)
            if not m:
                abort(404)
            b = bureau(m["bureau_id"])
            m = dict(m)
        else:
            bid = request.values.get("bureau", type=int)
            if bid:
                b = bureau(bid)
            else:
                niveau, entite = request.values.get("niveau") or "", request.values.get("entite") or ""
                if niveau not in niveaux_visibles() or not entite:
                    abort(404)
                exiger_ecriture(niveau)
                b = bureau_actif(niveau, entite, creer=True, lib=next((e[1] for e in entites(niveau) if e[0] == entite), entite))
            info = next((e[2] for e in entites(b["niveau"]) if e[0] == b["entite"]), {})
            n = q("SELECT COALESCE(MAX(ordre),0)+1 n FROM uascep_membres WHERE bureau_id=?", (b["id"],), un=True)["n"]
            m = {"id": 0, "ordre": n, "ecole": info.get("ecole", ""), "up": info.get("up", ""), "zone": info.get("zone", ""), "rup": info.get("rup", ""),
                 "date_election": b["date_election"] or "", "duree": b["duree"] or 2, "date_fin": b["date_fin"] or "", "date_installation": b["date_installation"] or ""}
        exiger_ecriture(b["niveau"])
        if request.method == "POST":
            f = request.form
            d = {k: (f.get(k) or "").strip()[:300] for k in CHAMPS_M}
            err = []
            if not d["nom"]:
                err.append("Le nom est obligatoire.")
            d["sexe"] = d["sexe"] if d["sexe"] in ("M", "F") else ""
            for k in ("date_election", "date_fin", "date_installation"):
                d[k] = iso(d[k]) if d[k] else ""
            try:
                d["ordre"] = int(d["ordre"] or 1)
                d["duree"] = int(d["duree"] or (b["duree"] or 2))
            except ValueError:
                err.append("N° d'ordre et durée du mandat : nombres entiers.")
            if d["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", d["email"]):
                err.append("Adresse e-mail invalide.")
            if d["date_election"] and not d["date_fin"]:
                d["date_fin"] = fin_mandat(d["date_election"], d["duree"])
            if err:
                for e in err:
                    flash(e, "danger")
                return render_template("uascep_membre.html", m=dict(m, **d), b=b, FONCTIONS=FONCTIONS, QUALITES=QUALITES, NIV_LIB=NIV_LIB), 400
            if mid:
                ex("UPDATE uascep_membres SET " + ", ".join(f"{k}=?" for k in CHAMPS_M) + ", maj=? WHERE id=?", tuple(d[k] for k in CHAMPS_M) + (H.maintenant(), mid))
            else:
                ex("INSERT INTO uascep_membres (bureau_id, " + ", ".join(CHAMPS_M) + ", maj) VALUES (?," + ",".join("?" * len(CHAMPS_M)) + ",?)",
                   (b["id"],) + tuple(d[k] for k in CHAMPS_M) + (H.maintenant(),))
            H.journal("uascep_membre", f"{NIV_LIB[b['niveau']]} {b['entite']} : {d['nom']} {d['prenoms']}")
            flash("Membre enregistré.", "success")
            return redirect(url_for("uascep", onglet=b["niveau"], entite=b["entite"]))
        return render_template("uascep_membre.html", m=m, b=b, FONCTIONS=FONCTIONS, QUALITES=QUALITES, NIV_LIB=NIV_LIB)

    @app.route("/uascep/membre/<int:mid>/supprimer", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_membre_supprimer(mid):
        m = q("SELECT * FROM uascep_membres WHERE id=?", (mid,), un=True)
        if not m:
            abort(404)
        b = bureau(m["bureau_id"])
        exiger_ecriture(b["niveau"])
        ex("DELETE FROM uascep_membres WHERE id=?", (mid,))
        H.journal("uascep_membre_supprime", f"{m['nom']} {m['prenoms'] or ''}")
        flash("Membre supprimé.", "success")
        return redirect(url_for("uascep", onglet=b["niveau"], entite=b["entite"]))

    def archiver(b):
        ex("UPDATE uascep_bureaux SET statut='archive', archive_le=?, maj=? WHERE id=?", (H.maintenant(), H.maintenant(), b["id"]))

    def reinitialiser(b, archive):
        if archive and q("SELECT 1 FROM uascep_membres WHERE bureau_id=? LIMIT 1", (b["id"],), un=True):
            archiver(b)
        else:
            ex("DELETE FROM uascep_membres WHERE bureau_id=?", (b["id"],))
            ex("DELETE FROM uascep_bureaux WHERE id=?", (b["id"],))

    @app.route("/uascep/bureau/<int:bid>/reinitialiser", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_reinitialiser(bid):
        b = bureau(bid)
        exiger_ecriture(b["niveau"])
        reinitialiser(b, bool(request.form.get("archive")))
        H.journal("uascep_reinitialise", f"{NIV_LIB[b['niveau']]} {b['entite']}")
        flash("Bureau réinitialisé" + (" (ancien bureau archivé)." if request.form.get("archive") else "."), "success")
        return redirect(url_for("uascep", onglet=b["niveau"], entite=b["entite"]))

    @app.route("/uascep/reinitialiser", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_reinitialiser_tous():
        niveau = request.form.get("niveau") or ""
        if niveau not in niveaux_visibles():
            abort(404)
        exiger_ecriture(niveau)
        bs = q("SELECT * FROM uascep_bureaux WHERE COALESCE(ecole_id,0)=COALESCE(?,0) AND niveau=? AND statut='actif'", (cle_ecole(), niveau))
        for b in bs:
            reinitialiser(b, bool(request.form.get("archive")))
        H.journal("uascep_reinitialise_tous", f"{NIV_LIB[niveau]} : {len(bs)} bureau(x)")
        flash(f"{len(bs)} bureau(x) réinitialisé(s).", "success")
        return redirect(url_for("uascep", onglet=niveau))

    @app.route("/uascep/bureau/<int:bid>/renouveler", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_renouveler(bid):
        b = bureau(bid)
        exiger_ecriture(b["niveau"])
        el = iso(request.form.get("date_election") or "") or date.today().isoformat()
        duree = b["duree"] or 2
        fin = fin_mandat(el, duree)
        archiver(b)
        nid = ex("INSERT INTO uascep_bureaux (ecole_id, niveau, entite, entite_lib, date_election, duree, date_fin, statut, observations, cree_le, maj) "
                 "VALUES (?,?,?,?,?,?,?,'actif',?,?,?)", (b["ecole_id"], b["niveau"], b["entite"], b["entite_lib"], el, duree, fin,
                                                         "Renouvellement du bureau", H.maintenant(), H.maintenant()))
        for m in membres(bid):   # v1.24 : cachet et signature suivent le membre reconduit
            ex("INSERT INTO uascep_membres (bureau_id, " + ", ".join(CHAMPS_M + CHAMPS_SIG) + ", maj) VALUES (?," + ",".join("?" * len(CHAMPS_M + CHAMPS_SIG)) + ",?)",
               (nid,) + tuple({**m, "date_election": el, "duree": duree, "date_fin": fin, "date_installation": ""}.get(k) for k in CHAMPS_M + CHAMPS_SIG) + (H.maintenant(),))
        H.journal("uascep_renouvele", f"{NIV_LIB[b['niveau']]} {b['entite']}")
        flash("Bureau renouvelé sur un nouveau mandat (l'ancien est dans « Anciens bureaux »).", "success")
        return redirect(url_for("uascep", onglet=b["niveau"], entite=b["entite"]))

    # ------------------------------------------------------------------ Excel (spécification commune) et PDF
    def lignes_export(niveaux):
        lm, lb = [], []
        for c in niveaux:
            for b in q("SELECT * FROM uascep_bureaux WHERE COALESCE(ecole_id,0)=COALESCE(?,0) AND niveau=? AND statut='actif' ORDER BY entite", (cle_ecole(), c)):
                lb.append([c, b["entite_lib"] or b["entite"], jjmmaaaa(b["date_election"]), b["duree"] or "", jjmmaaaa(b["date_fin"]), jjmmaaaa(b["date_installation"]),
                           jjmmaaaa(b["ag_date"]), b["ag_lieu"] or "", b["pv"] or "", b["observations"] or "", b["statut"]])
                for m in membres(b["id"]):
                    lm.append([c, b["entite_lib"] or b["entite"], m["ordre"], m["nom"], m["prenoms"] or "", m["sexe"] or "", m["ecole"] or "", m["up"] or "",
                               m["zone"] or "", m["rup"] or "", m["fonction"] or "", m["qualite"] or "", m["contact"] or "", m["email"] or "",
                               jjmmaaaa(m["date_election"]), m["duree"] or "", jjmmaaaa(m["date_fin"]), m["statut"], jjmmaaaa(m["date_installation"]), m["observations"] or ""])
        return lm, lb

    @app.route("/uascep.xlsx")
    @H.connexion_requise("uascep")
    def uascep_xlsx():
        vis = niveaux_visibles()
        niv = [request.args["niveau"]] if request.args.get("niveau") in vis else vis
        lm, lb = lignes_export(niv)
        return H.xlsx.reponse_classeur("bureaux_uascep.xlsx", [("Membres UASCEP", ENT_MEMBRES, lm, {}), ("Bureaux", ENT_BUREAUX, lb, {})])

    @app.route("/uascep/modele.xlsx")
    @H.connexion_requise("uascep")
    def uascep_modele():
        ex_ = ["École", "EPP Exemple", 1, "NOM", "Prénoms", "F", "EPP Exemple", "UP 1", "Zone 1", "", "Présidente", "Enseignante", "", "",
               "15/10/2026", 2, "15/10/2028", "", "", ""]
        lignes = [] if request.args.get("vide") else [ex_]       # v1.28 : modèle vierge (en-têtes seuls)
        return H.xlsx.reponse_classeur("modele_uascep.xlsx", [("Membres UASCEP", ENT_MEMBRES, lignes, {}), ("Bureaux", ENT_BUREAUX, [], {})])

    @app.route("/uascep/import", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_import():
        import outils_xlsx as X
        fichier = request.files.get("fichier")
        if not fichier or not fichier.filename:
            flash("Choisissez un fichier Excel.", "danger")
            return redirect(url_for("uascep"))
        try:
            wb = X._openpyxl().load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            flash("Fichier Excel illisible : enregistrez-le au format .xlsx.", "danger")
            return redirect(url_for("uascep"))
        feuilles = {X.normaliser(ws.title): ws for ws in wb.worksheets}
        ws_m = feuilles.get(X.normaliser("Membres UASCEP")) or wb.worksheets[0]
        ws_b = feuilles.get(X.normaliser("Bureaux"))
        refus, nb_m, nb_b = [], 0, 0
        ecrire = niveaux_ecriture()
        lib_ent = {}
        for c in niveaux_visibles():
            for k, lib, _i in entites(c):
                lib_ent[(c, X.normaliser(lib))] = k
                lib_ent[(c, X.normaliser(k))] = k

        def cle_entite(niv, v):
            if not juridiction() and niv == "ECOLE":
                return str(H.eco())
            return lib_ent.get((niv, X.normaliser(v)), str(v).strip())

        def lignes(ws):
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            i = next((k for k, r in enumerate(rows[:20]) if r and X.normaliser(r[0]) == "niveau"), 0)
            return [str(v or "").strip() for v in rows[i]], [r for r in rows[i + 1:] if any(v not in (None, "") for v in r)], i

        if ws_b is not None:
            ent, rows, i0 = lignes(ws_b)
            ci = {h: X.colonne(ent, h) for h in ENT_BUREAUX}
            for n, r in enumerate(rows, i0 + 2):
                v = {h: X.valeur(r, ci[h]) for h in ENT_BUREAUX}
                niv = niveau_de(v["Niveau"])
                if niv not in ecrire:
                    refus.append(f"Bureaux, ligne {n} : niveau « {v['Niveau']} » hors de votre périmètre.")
                    continue
                k = cle_entite(niv, v["Entité"])
                b = bureau_actif(niv, k, creer=True, lib=v["Entité"])
                el = iso(v["Date d'élection"])
                du = int(v["Durée du mandat (ans)"]) if str(v["Durée du mandat (ans)"]).isdigit() else 2
                ex("UPDATE uascep_bureaux SET date_election=?, duree=?, date_fin=?, date_installation=?, ag_date=?, ag_lieu=?, pv=?, observations=?, maj=? WHERE id=?",
                   (el, du, iso(v["Date de fin de mandat"]) or fin_mandat(el, du), iso(v["Date d'installation"]), iso(v["Date de l'assemblée générale"]),
                    v["Lieu de l'assemblée générale"], v["PV"], v["Observations"], H.maintenant(), b["id"]))
                nb_b += 1
        ent, rows, i0 = lignes(ws_m)
        ci = {h: X.colonne(ent, h) for h in ENT_MEMBRES}
        if ci["Nom"] is None or ci["Niveau"] is None:
            flash("En-têtes introuvables : utilisez le modèle (feuille « Membres UASCEP »).", "danger")
            return redirect(url_for("uascep"))
        for n, r in enumerate(rows, i0 + 2):
            v = {h: X.valeur(r, ci[h]) for h in ENT_MEMBRES}
            niv = niveau_de(v["Niveau"])
            if niv not in ecrire:
                refus.append(f"Membres, ligne {n} : niveau « {v['Niveau']} » hors de votre périmètre.")
                continue
            if not v["Nom"]:
                refus.append(f"Membres, ligne {n} : nom manquant.")
                continue
            k = cle_entite(niv, v["Entité"])
            b = bureau_actif(niv, k, creer=True, lib=v["Entité"])
            el = iso(v["Date d'élection"])
            du = int(v["Durée du mandat (ans)"]) if str(v["Durée du mandat (ans)"]).isdigit() else (b["duree"] or 2)
            d = {"ordre": int(v["N° d'ordre"]) if str(v["N° d'ordre"]).isdigit() else 1, "nom": v["Nom"], "prenoms": v["Prénoms"], "sexe": X.sexe(v["Sexe"]),
                 "ecole": v["École"], "up": v["UP"], "zone": v["Zone pédagogique"], "rup": v["Nom du RUP"], "fonction": v["Fonction"], "qualite": v["Qualité"],
                 "contact": v["Contact"], "email": v["E-mail"], "date_election": el, "duree": du, "date_fin": iso(v["Date de fin de mandat"]) or fin_mandat(el, du),
                 "date_installation": iso(v["Date d'installation"]), "observations": v["Observations"]}
            ex_m = q("SELECT id FROM uascep_membres WHERE bureau_id=? AND lower(nom)=lower(?) AND lower(COALESCE(prenoms,''))=lower(?)", (b["id"], d["nom"], d["prenoms"] or ""), un=True)
            if ex_m:
                ex("UPDATE uascep_membres SET " + ", ".join(f"{c}=?" for c in CHAMPS_M) + ", maj=? WHERE id=?", tuple(d[c] for c in CHAMPS_M) + (H.maintenant(), ex_m["id"]))
            else:
                ex("INSERT INTO uascep_membres (bureau_id, " + ", ".join(CHAMPS_M) + ", maj) VALUES (?," + ",".join("?" * len(CHAMPS_M)) + ",?)",
                   (b["id"],) + tuple(d[c] for c in CHAMPS_M) + (H.maintenant(),))
            nb_m += 1
        H.journal("uascep_import", f"{nb_m} membre(s), {nb_b} bureau(x), {len(refus)} refus")
        flash(f"Import : {nb_m} membre(s) et {nb_b} bureau(x) enregistrés ; {len(refus)} ligne(s) refusée(s).", "success" if not refus else "warning")
        for x in refus[:15]:
            flash(x, "warning")
        return redirect(url_for("uascep"))

    # ------------------------------------------------------------------ v1.24 : cachets, signatures, documents signés
    def defaut_cachet(m, b):
        return {"sup": f"UASCEP — {NIV_LIB[b['niveau']]}".upper(), "inf": (b["entite_lib"] or b["entite"] or "")[:60],
                "centre": (m.get("fonction") or "Membre")[:40]}

    def cachet_de(m, b):
        """Description du cachet d'un membre : ('rond', sup, inf, centre, couleur) | ('rect', lignes, couleur) |
        ('image', data URL) | None."""
        mode = m.get("cachet_mode") or "genere"
        if mode == "aucun":
            return None
        if mode == "image":
            return ("image", m["cachet_image"]) if m.get("cachet_image") else None
        d = defaut_cachet(m, b)
        coul = m.get("cachet_couleur") or "bleu"
        if (m.get("cachet_forme") or "rond") == "rect":
            nom = f"{(m.get('nom') or '').upper()} {m.get('prenoms') or ''}".strip()
            return ("rect", [(m.get("cachet_centre") or d["centre"]).upper(), nom, (m.get("cachet_inf") or d["inf"]).upper()], coul)
        return ("rond", m.get("cachet_sup") or d["sup"], m.get("cachet_inf") or d["inf"], m.get("cachet_centre") or d["centre"], coul)

    def svg_cachet(m, b):
        import cachet as K
        ca = cachet_de(m, b)
        if not ca or ca[0] == "image":
            return ""
        if ca[0] == "rect":
            return K.svg_nom(ca[1], ca[2], 240)
        return K.svg(ca[1], ca[2], ca[3], ca[4], 170)

    def lire_image(fichier):
        """Fichier importé -> data URL (PNG / JPEG, 400 Ko au plus) ; None si absent ; ValueError si refusé."""
        import base64
        if not fichier or not fichier.filename:
            return None
        brut = fichier.read(400 * 1024 + 1)
        if len(brut) > 400 * 1024:
            raise ValueError("Image trop lourde (400 Ko au plus).")
        if brut[:8] == b"\x89PNG\r\n\x1a\n":
            typ = "png"
        elif brut[:3] == b"\xff\xd8\xff":
            typ = "jpeg"
        else:
            raise ValueError("Format refusé : PNG ou JPEG uniquement.")
        return f"data:image/{typ};base64," + base64.b64encode(brut).decode()

    def membre_et_bureau(mid):
        m = q("SELECT * FROM uascep_membres WHERE id=?", (mid,), un=True)
        if not m:
            abort(404)
        return dict(m), dict(bureau(m["bureau_id"]))

    @app.route("/uascep/membre/<int:mid>/cachet", methods=["GET", "POST"])
    @H.connexion_requise("uascep")
    def uascep_cachet(mid):
        m, b = membre_et_bureau(mid)
        peut = b["niveau"] in niveaux_ecriture() and b["statut"] == "actif"
        if request.method == "POST":
            exiger_ecriture(b["niveau"])
            f = request.form
            d = {"cachet_mode": f.get("cachet_mode") if f.get("cachet_mode") in ("genere", "image", "aucun") else "genere",
                 "cachet_forme": "rect" if f.get("cachet_forme") == "rect" else "rond",
                 "cachet_couleur": f.get("cachet_couleur") if f.get("cachet_couleur") in ("bleu", "rouge", "vert", "noir") else "bleu",
                 "cachet_sup": (f.get("cachet_sup") or "").strip()[:60], "cachet_inf": (f.get("cachet_inf") or "").strip()[:60],
                 "cachet_centre": (f.get("cachet_centre") or "").strip()[:40],
                 "cachet_image": m.get("cachet_image"), "signature": m.get("signature")}
            try:
                img = lire_image(request.files.get("cachet_fichier"))
                if img:
                    d["cachet_image"], d["cachet_mode"] = img, "image"
                sig = lire_image(request.files.get("signature_fichier"))
            except ValueError as e:
                flash(str(e), "danger")
                return redirect(url_for("uascep_cachet", mid=mid))
            dessin = (f.get("signature_dessin") or "").strip()
            if sig:
                d["signature"] = sig
            elif dessin.startswith("data:image/png;base64,") and len(dessin) < 600_000:
                d["signature"] = dessin
            if f.get("effacer_signature"):
                d["signature"] = None
            if d["cachet_mode"] == "image" and not d["cachet_image"]:
                flash("Importez l'image du cachet (ou choisissez le cachet généré).", "warning")
                d["cachet_mode"] = "genere"
            ex("UPDATE uascep_membres SET " + ", ".join(f"{k}=?" for k in CHAMPS_SIG) + ", maj=? WHERE id=?",
               tuple(d[k] for k in CHAMPS_SIG) + (H.maintenant(), mid))
            H.journal("uascep_cachet", f"{NIV_LIB[b['niveau']]} {b['entite']} : {m['nom']} {m['prenoms'] or ''}")
            flash("Cachet et signature enregistrés.", "success")
            return redirect(url_for("uascep_cachet", mid=mid))
        return render_template("uascep_cachet.html", m=m, b=b, NIV_LIB=NIV_LIB, peut_ecrire=peut, defaut=defaut_cachet(m, b),
                               apercu_cachet=svg_cachet(m, b))

    @app.route("/uascep/membre/<int:mid>/cachet/reinitialiser", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_cachet_reinitialiser(mid):
        m, b = membre_et_bureau(mid)
        exiger_ecriture(b["niveau"])
        ex("UPDATE uascep_membres SET cachet_mode='genere', cachet_forme='rond', cachet_couleur='bleu', cachet_sup=NULL, cachet_inf=NULL, "
           "cachet_centre=NULL, cachet_image=NULL, signature=NULL, maj=? WHERE id=?", (H.maintenant(), mid))
        H.journal("uascep_cachet_reinitialise", f"{m['nom']} {m['prenoms'] or ''}")
        flash("Cachet et signature réinitialisés.", "success")
        return redirect(url_for("uascep_cachet", mid=mid))

    # ---- signataires et visa
    def signataire(m, b, titre=None):
        import pdfs
        return {"titre": titre or f"Le / La {m.get('fonction') or 'Membre'}", "nom": f"{m['nom']} {m.get('prenoms') or ''}".strip(),
                "image": pdfs.image_data_url(m.get("signature")), "cachet": cachet_de(m, b)}

    def par_fonction(ms, *prefixes):
        for p in prefixes:
            x = next((m for m in ms if (m.get("fonction") or "").lower().startswith(p)), None)
            if x:
                return x
        return None

    def visa(b):
        """Visa de l'autorité hiérarchique (signature et cachet de la structure quand ils sont enregistrés)."""
        import pdfs
        titres = {"ECOLE": "Visa du Directeur / de la Directrice", "UP": "Visa du RUP", "ZONE": "Visa du CP de zone",
                  "CS": "Visa du Chef de la circonscription scolaire", "DDEMP": "Visa du Directeur départemental"}
        v = {"titre": titres[b["niveau"]], "nom": "", "image": None, "cachet": None, "visa": True}
        try:
            if juridiction() and getattr(H, "jur_signataire", None):
                t, nom, sig = H.jur_signataire()
                v.update(nom=nom or "", image=pdfs.image_data_url(sig))
                if getattr(H, "jur_cachet", None):
                    ca = H.jur_cachet()
                    if ca:
                        v["cachet"] = ("rond",) + tuple(ca)
            elif b["niveau"] == "ECOLE":
                v.update(nom=config.ECOLE.get("directeur") or "", image=pdfs.signature_directeur(), cachet=("ecole",))
        except Exception:  # noqa: BLE001
            pass
        return v

    def signataires_bureau(b, ms, tresorier=False):
        out = []
        pres = par_fonction(ms, "président", "presid")
        sg = par_fonction(ms, "secrétaire général", "secretaire general", "secrétaire")
        tr = par_fonction(ms, "trésorier général", "tresorier general", "trésorier") if tresorier else None
        if sg:
            out.append(signataire(sg, b, "Le / La Secrétaire général(e)"))
        if tr:
            out.append(signataire(tr, b, "Le / La Trésorier(ère) général(e)"))
        out.append(signataire(pres, b, "Le / La Président(e)") if pres else {"titre": "Le / La Président(e)", "nom": "", "image": None, "cachet": None})
        out.append(visa(b))
        return out

    def code_doc(type_doc, libelle, cle):
        try:
            return H.enregistrer_document(type_doc, None, libelle, cle=cle)
        except Exception:  # noqa: BLE001
            return None

    # ---- PDF communs
    def _pdf(h, titre, paysage=False):
        import pdfs
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate
        W, Hh = landscape(A4) if paysage else A4
        marge = 12 * mm if paysage else 15 * mm

        def deco(cv, doc):
            pdfs._entete_primaire(cv, W, Hh, marge, None, None)
        b = g.get("uascep_logo_bureau")
        if b and not g.get("uascep_sans_bandeau"):
            h = [bandeau_logo(b["niveau"], b["entite"], b.get("entite_lib"), W - 2 * marge)] + list(h)
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=(W, Hh), leftMargin=marge, rightMargin=marge, topMargin=marge + 30 * mm, bottomMargin=12 * mm,
                          title=titre, author="SCOLARIS").build(h, onFirstPage=deco, onLaterPages=deco, canvasmaker=pdfs.GCanvas)
        return buf.getvalue()

    def _largeur(paysage=False):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import mm
        W = landscape(A4)[0] if paysage else A4[0]
        return W - 2 * (12 * mm if paysage else 15 * mm)

    def _styles():
        import pdfs
        from reportlab.lib.styles import ParagraphStyle
        st = ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13.5, spaceAfter=4)
        return {"p": st, "petit": ParagraphStyle("pp", parent=st, fontSize=7.6, leading=9.4, spaceAfter=0),
                "t": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=13, alignment=1, textColor=pdfs.BLEU, leading=16, spaceAfter=4),
                "s": ParagraphStyle("s", parent=st, alignment=1, fontSize=9)}

    def _grille(data, larg, largeur):
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import Table, TableStyle
        larg = list(larg)
        i0 = larg.index(0)
        larg[i0] = largeur / mm - sum(larg)
        tb = Table(data, colWidths=[x * mm for x in larg], repeatRows=1)
        tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E4ECF5")),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
        return tb

    def _table_membres(ms, largeur, complet=True):
        from reportlab.platypus import Paragraph
        st = _styles()["petit"]
        if complet:
            ent = ["N°", "Nom et prénoms", "Sexe", "École", "UP", "Zone", "Nom du RUP", "Fonction", "Qualité", "Contact", "Élection", "Fin de mandat", "Statut"]
            larg = [8, 38, 9, 30, 18, 16, 26, 28, 20, 22, 17, 18, 0]
            rows = [[m["ordre"], f"{m['nom']} {m['prenoms'] or ''}", m["sexe"] or "", m["ecole"] or "", m["up"] or "", m["zone"] or "", m["rup"] or "",
                     m["fonction"] or "", m["qualite"] or "", m["contact"] or "", jjmmaaaa(m["date_election"]), jjmmaaaa(m["date_fin"]), m["statut"]] for m in ms]
        else:
            ent = ["N°", "Fonction", "Nom et prénoms", "Sexe", "Qualité", "École", "Contact"]
            larg = [10, 40, 48, 11, 26, 0, 26]
            rows = [[m["ordre"], m["fonction"] or "", f"{m['nom']} {m['prenoms'] or ''}", m["sexe"] or "", m["qualite"] or "", m["ecole"] or "", m["contact"] or ""] for m in ms]
        data = [[Paragraph(f"<b>{x}</b>", st) for x in ent]] + [[Paragraph(MPtxt(x), st) for x in r] for r in rows]
        return _grille(data, larg, largeur)

    def _pied(sigs, largeur, code):
        from reportlab.platypus import KeepTogether
        return KeepTogether([bloc_signatures(sigs, largeur, code)])

    TYPES = {"uascep_composition": "Bureau de l'UASCEP : composition", "uascep_pv_election": "Bureau de l'UASCEP : PV d'élection",
             "uascep_pv_installation": "Bureau de l'UASCEP : PV d'installation", "uascep_attestation": "Bureau de l'UASCEP : attestation de fonction",
             "uascep_liste": "Bureaux de l'UASCEP : liste", "uascep_rapport": "Bureau de l'UASCEP : rapport de fin de saison sportive",
             "uascep_cr": "Bureau de l'UASCEP : compte rendu de réunion", "uascep_journal": "Bureau de l'UASCEP : calendrier, résultats et journal",
             "uascep_engagements": "Bureau de l'UASCEP : fiches d'engagement", "uascep_finances": "Bureau de l'UASCEP : état financier et journal de caisse",
             "uascep_inventaire": "Bureau de l'UASCEP : inventaire du matériel"}
    try:  # libellés de la page /verifier
        import sys
        for nom_mod in ("app", "__main__"):
            td = getattr(sys.modules.get(nom_mod), "TYPES_DOCS", None)
            if isinstance(td, dict):
                for k, v in TYPES.items():
                    td.setdefault(k, v)
    except Exception:  # noqa: BLE001
        pass

    def h_composition(b, ms, largeur):
        from reportlab.platypus import Paragraph, Spacer
        S = _styles()
        lib = b["entite_lib"] or b["entite"]
        code = code_doc("uascep_composition", f"Composition du bureau UASCEP — {NIV_LIB[b['niveau']]} : {lib} ({len(ms)} membre(s))",
                        f"uascep:composition:{b['id']}:{b['maj'] or ''}:{len(ms)}")
        return [Paragraph(f"COMPOSITION DU BUREAU DE L'UASCEP — {NIV_LIB[b['niveau']].upper()}", S["t"]),
                Paragraph(f"{MPtxt(lib)} · élu le {jjmmaaaa(b['date_election']) or '……'} · installé le {jjmmaaaa(b['date_installation']) or '……'} · "
                          f"fin de mandat {jjmmaaaa(b['date_fin']) or '……'} · {statut_mandat(b['date_fin'])}", S["s"]), Spacer(1, 5),
                _table_membres(ms, largeur), Spacer(1, 6), _pied(signataires_bureau(b, ms, tresorier=True), largeur, code)]

    @app.route("/uascep/bureau/<int:bid>/composition.pdf")
    @H.connexion_requise("uascep")
    def uascep_composition_pdf(bid):
        b = dict(bureau(bid))
        ms = membres(bid)
        return H.pdf_reponse(_pdf(h_composition(b, ms, _largeur(True)), "Composition du bureau UASCEP", True), f"uascep_composition_{bid}.pdf")

    @app.route("/uascep/bureau/<int:bid>/pv.pdf")
    @H.connexion_requise("uascep")
    def uascep_pv_pdf(bid):
        from reportlab.platypus import Paragraph, Spacer
        b = dict(bureau(bid))
        ms = membres(bid)
        typ = "installation" if request.args.get("type") == "installation" else "election"
        S = _styles()
        L = _largeur()
        lib = MPtxt(b["entite_lib"] or b["entite"])
        niv = NIV_LIB[b["niveau"]].lower()
        lieu = MPtxt(b["ag_lieu"] or "……………………")
        if typ == "election":
            dt = jjmmaaaa(b["ag_date"] or b["date_election"]) or "……/……/……"
            titre = "PROCÈS-VERBAL D'ÉLECTION DU BUREAU DE L'UASCEP"
            texte = (f"Le {dt}, à {lieu}, s'est tenue l'assemblée générale de l'Union des associations scolaires et culturelles des écoles "
                     f"primaires (UASCEP) — niveau {niv} : <b>{lib}</b>, en vue de l'élection de son bureau pour un mandat de "
                     f"{b['duree'] or 2} an(s){', soit jusqu’au ' + jjmmaaaa(b['date_fin']) if b['date_fin'] else ''}. "
                     f"À l'issue du vote, les {len(ms)} membre(s) suivant(s) ont été élu(s) :")
            fin = "Le présent procès-verbal est établi pour servir et valoir ce que de droit."
        else:
            dt = jjmmaaaa(b["date_installation"]) or "……/……/……"
            titre = "PROCÈS-VERBAL D'INSTALLATION DU BUREAU DE L'UASCEP"
            texte = (f"Le {dt}, à {lieu}, le bureau de l'UASCEP — niveau {niv} : <b>{lib}</b>, élu le "
                     f"{jjmmaaaa(b['date_election']) or '……/……/……'}, a été officiellement installé dans ses fonctions en présence de "
                     f"l'autorité hiérarchique. Le bureau installé se compose comme suit :")
            fin = "Les membres installés s'engagent à servir l'UASCEP dans le respect de ses statuts. En foi de quoi le présent procès-verbal est établi."
        code = code_doc(f"uascep_pv_{typ}", f"PV d'{'élection' if typ == 'election' else 'installation'} — bureau UASCEP {NIV_LIB[b['niveau']]} : {b['entite_lib'] or b['entite']}",
                        f"uascep:pv{typ}:{b['id']}:{b['maj'] or ''}:{len(ms)}")
        h = [Paragraph(titre, S["t"]), Paragraph(f"{NIV_LIB[b['niveau']]} : {lib}", S["s"]), Spacer(1, 8), Paragraph(texte, S["p"]), Spacer(1, 4),
             _table_membres(ms, L, complet=False), Spacer(1, 8), Paragraph(fin, S["p"]),
             Paragraph(f"Fait à {lieu}, le {dt}.", S["p"]), Spacer(1, 4), _pied(signataires_bureau(b, ms), L, code)]
        return H.pdf_reponse(_pdf(h, titre.title()), f"uascep_pv_{typ}_{bid}.pdf")

    @app.route("/uascep/membre/<int:mid>/attestation.pdf")
    @H.connexion_requise("uascep")
    def uascep_attestation_pdf(mid):
        from reportlab.platypus import Paragraph, Spacer
        m, b = membre_et_bureau(mid)
        ms = membres(b["id"])
        S = _styles()
        L = _largeur()
        pres = par_fonction(ms, "président", "presid")
        signe = pres if pres and pres["id"] != m["id"] else par_fonction([x for x in ms if x["id"] != m["id"]], "vice", "secrétaire général", "secrétaire")
        civ = "Madame" if m.get("sexe") == "F" else ("Monsieur" if m.get("sexe") == "M" else "Madame / Monsieur")
        lib = MPtxt(b["entite_lib"] or b["entite"])
        qui = (f"Je soussigné(e), <b>{MPtxt(signe['nom'])} {MPtxt(signe['prenoms'] or '')}</b>, {MPtxt(signe['fonction'] or '')} du bureau de l'UASCEP"
               if signe else "Le bureau de l'UASCEP")
        fin_m = m.get("date_fin") or b.get("date_fin")
        texte = (f"{qui} — niveau {NIV_LIB[b['niveau']].lower()} : <b>{lib}</b>, atteste que <b>{civ} {MPtxt(m['nom'])} {MPtxt(m['prenoms'] or '')}</b>"
                 f"{', ' + MPtxt(m['qualite']) if m.get('qualite') else ''}{' (' + MPtxt(m['ecole']) + ')' if m.get('ecole') else ''}, est membre de ce bureau "
                 f"en qualité de <b>{MPtxt(m['fonction'] or 'membre')}</b>, élu(e) le {jjmmaaaa(m.get('date_election') or b.get('date_election')) or '……/……/……'} "
                 f"pour un mandat de {m.get('duree') or b.get('duree') or 2} an(s) prenant fin le {jjmmaaaa(fin_m) or '……/……/……'} "
                 f"(mandat : {statut_mandat(fin_m).lower()}).")
        code = code_doc("uascep_attestation", f"Attestation de fonction UASCEP — {m['nom']} {m['prenoms'] or ''}, {m['fonction'] or 'membre'} "
                        f"({NIV_LIB[b['niveau']]} : {b['entite_lib'] or b['entite']})", f"uascep:attestation:{m['id']}:{m['maj'] or ''}")
        sigs = [signataire(m, b, "Spécimen de signature du titulaire")]
        sigs.append(signataire(signe, b, f"Le / La {signe['fonction']}") if signe else {"titre": "Le / La Président(e)", "nom": "", "image": None, "cachet": None})
        sigs.append(visa(b))
        h = [Paragraph("ATTESTATION DE FONCTION", S["t"]), Paragraph(f"Bureau de l'UASCEP — {NIV_LIB[b['niveau']]} : {lib}", S["s"]), Spacer(1, 14),
             Paragraph(texte, S["p"]), Spacer(1, 6), Paragraph("En foi de quoi la présente attestation lui est délivrée pour servir et valoir ce que de droit.", S["p"]),
             Spacer(1, 10), _pied(sigs, L, code)]
        return H.pdf_reponse(_pdf(h, "Attestation de fonction UASCEP"), f"uascep_attestation_{mid}.pdf")

    def logo_autorite():
        """Bandeau des documents de synthèse : logo de l'entité du compte (école, CS ou DDEMP)."""
        if not juridiction():
            g.uascep_logo_bureau = {"niveau": "ECOLE", "entite": str(H.eco()), "entite_lib": None}
            return
        niv = "DDEMP" if config.EDITION == "ddemp" else "CS"
        e = entites(niv)
        if e:
            g.uascep_logo_bureau = {"niveau": niv, "entite": e[0][0], "entite_lib": e[0][1]}

    @app.route("/uascep/liste.pdf")
    @H.connexion_requise("uascep")
    def uascep_liste_pdf():
        from reportlab.platypus import Paragraph, Spacer
        logo_autorite()
        vis = niveaux_visibles()
        niv = [request.args["niveau"]] if request.args.get("niveau") in vis else vis
        S = _styles()
        L = _largeur(True)
        st = S["petit"]
        ent = ["Niveau", "Entité", "Président(e)", "Secrétaire général(e)", "Trésorier(ère) général(e)", "Membres", "Élection", "Installation", "Fin de mandat", "Statut"]
        data = [[Paragraph(f"<b>{x}</b>", st) for x in ent]]

        def nm(m):
            if not m:
                return "—"
            return f"{m['nom']} {m['prenoms'] or ''}".strip() + (f" ({m['contact']})" if m.get("contact") else "")
        n = 0
        for c in niv:
            for b in q("SELECT * FROM uascep_bureaux WHERE COALESCE(ecole_id,0)=COALESCE(?,0) AND niveau=? AND statut='actif' ORDER BY entite_lib, entite", (cle_ecole(), c)):
                ms = membres(b["id"])
                data.append([Paragraph(MPtxt(x), st) for x in [NIV_LIB[c], b["entite_lib"] or b["entite"], nm(par_fonction(ms, "président", "presid")),
                                                                 nm(par_fonction(ms, "secrétaire général", "secrétaire")), nm(par_fonction(ms, "trésorier général", "trésorier")),
                                                                 len(ms), jjmmaaaa(b["date_election"]), jjmmaaaa(b["date_installation"]), jjmmaaaa(b["date_fin"]),
                                                                 statut_mandat(b["date_fin"])]])
                n += 1
        if not n:
            flash("Aucun bureau à imprimer.", "warning")
            return redirect(url_for("uascep"))
        tb = _grille(data, [22, 44, 40, 40, 40, 13, 17, 17, 18, 0], L)
        code = code_doc("uascep_liste", f"Liste des bureaux de l'UASCEP ({', '.join(NIV_LIB[c] for c in niv)}) : {n} bureau(x)",
                        f"uascep:liste:{','.join(niv)}:{n}:{date.today().isoformat()}")
        sigs = []
        if not juridiction():
            be = bureau_actif("ECOLE", str(H.eco()))
            pres = par_fonction(membres(be["id"]), "président", "presid") if be else None
            if pres:
                sigs.append(signataire(pres, dict(be), "Le / La Président(e) du bureau de l'école"))
            pseudo = {"niveau": "ECOLE"}
        else:
            pseudo = {"niveau": "DDEMP" if config.EDITION == "ddemp" else "CS"}
        v = visa(pseudo)
        v["titre"] = {"ECOLE": "Le Directeur / La Directrice", "CS": "Le Chef de la circonscription scolaire", "DDEMP": "Le Directeur départemental"}[pseudo["niveau"]]
        sigs.append(v)
        h = [Paragraph("LISTE DES BUREAUX DE L'UASCEP", S["t"]),
             Paragraph(f"{n} bureau(x) actif(s) · " + ", ".join(NIV_LIB[c] for c in niv) + f" · édité le {date.today().strftime('%d/%m/%Y')}", S["s"]),
             Spacer(1, 5), tb, Spacer(1, 8), _pied(sigs, L, code)]
        return H.pdf_reponse(_pdf(h, "Liste des bureaux UASCEP", True), "uascep_liste_bureaux.pdf")

    # ------------------------------------------------------------------ v1.24 : vie du bureau par saison (rapporteur, trésorier,
    # calendrier, engagements, matériel) et rapport de fin de saison sportive
    for coll, d in COLL.items():
        cols = ", ".join(f"{k} {'INTEGER' if t in ('entier', 'montant') else 'TEXT'}" for k, _l, t in d["champs"])
        H.schema(f"CREATE TABLE IF NOT EXISTS uascep_{coll} (id INTEGER PRIMARY KEY, bureau_id INTEGER NOT NULL REFERENCES uascep_bureaux(id) "
                 f"ON DELETE CASCADE, saison TEXT NOT NULL, {cols}, maj TEXT);\n"
                 f"CREATE INDEX IF NOT EXISTS ix_uascep_{coll} ON uascep_{coll}(bureau_id, saison);")
        H.renommer_colonnes(f"uascep_{coll}", RENOMMER.get(coll, {}))
        for k, _l, t in d["champs"]:
            H.ajouter_colonne(f"uascep_{coll}", k, "INTEGER" if t in ("entier", "montant") else "TEXT")
    H.schema("CREATE TABLE IF NOT EXISTS uascep_rapports (id INTEGER PRIMARY KEY, bureau_id INTEGER NOT NULL REFERENCES uascep_bureaux(id) "
             "ON DELETE CASCADE, saison TEXT NOT NULL, " + ", ".join(f"{k} TEXT" for k, _l in RAPPORT_TEXTES) + ", maj TEXT, UNIQUE(bureau_id, saison));")

    def saison_de(v=None):
        v = (v or request.values.get("saison") or "").strip()
        return v if re.fullmatch(r"\d{4}-\d{4}", v) else config.ANNEE_ACTIVE

    def lignes_coll(coll, bid, saison):
        ordre = {"activites": "date, id", "reunions": "date, id", "caisse": "date, id", "engagements": "ecole, discipline, id",
                 "budget": "nature DESC, categorie, id", "materiel": "designation, id"}[coll]
        return [dict(r) for r in q(f"SELECT * FROM uascep_{coll} WHERE bureau_id=? AND saison=? ORDER BY {ordre}", (bid, saison))]

    def lire_ligne(coll, f):
        d = {}
        for k, _l, t in COLL[coll]["champs"]:
            v = (f.get(k) or "").strip()
            if t in ("entier", "montant"):
                v = re.sub(r"[\s  .]", "", v)
                d[k] = int(v) if re.fullmatch(r"-?\d+", v or "") else (0 if t == "montant" else None)
            elif t == "date":
                d[k] = iso(v) if v else ""
            else:
                d[k] = v[:4000 if t == "long" else 300]
        return d

    def finances(bid, saison):
        """Journal de caisse (solde cumulé), totaux par catégorie, cotisations par école, budget prévu / réalisé."""
        caisse = lignes_coll("caisse", bid, saison)
        solde, journal = 0, []
        for r in caisse:
            solde += (r["montant"] or 0) * (1 if r["nature"] == "Recette" else -1)
            journal.append(dict(r, solde=solde))
        rec = sum(r["montant"] or 0 for r in caisse if r["nature"] == "Recette")
        dep = sum(r["montant"] or 0 for r in caisse if r["nature"] != "Recette")
        par_cat = {}
        for r in caisse:
            k = (r["nature"] or "Dépense", r["categorie"] or "Divers")
            par_cat[k] = par_cat.get(k, 0) + (r["montant"] or 0)
        cotis = {}
        for r in caisse:
            if r["nature"] == "Recette" and "cotisation" in (r["categorie"] or "").lower():
                e = r["ecole"] or r["libelle"] or "—"
                cotis[e] = cotis.get(e, 0) + (r["montant"] or 0)
        budget = []
        for b in lignes_coll("budget", bid, saison):
            real = par_cat.get((b["nature"] or "Dépense", b["categorie"] or "Divers"), 0)
            budget.append(dict(b, realise=real, ecart=real - (b["prevu"] or 0), taux=round(100 * real / b["prevu"]) if b["prevu"] else None))
        return {"journal": journal, "recettes": rec, "depenses": dep, "solde": rec - dep, "par_cat": sorted(par_cat.items()),
                "cotisations": sorted(cotis.items()), "budget": budget}

    def participation(bid, saison):
        acts = [a for a in lignes_coll("activites", bid, saison) if a["statut"] != "Annulée"]
        real = [a for a in acts if (a["statut"] or "Réalisée") == "Réalisée"]
        g = sum(a["pg"] or 0 for a in real)
        f = sum(a["pf"] or 0 for a in real)
        par_disc = {}
        for a in real:
            x = par_disc.setdefault(a["discipline"] or "—", [0, 0, 0])
            x[0] += 1
            x[1] += a["pg"] or 0
            x[2] += a["pf"] or 0
        return {"activites": acts, "realisees": real, "g": g, "f": f, "t": g + f, "par_discipline": sorted(par_disc.items()),
                "prevues": [a for a in acts if a["statut"] in ("Prévue", "Reportée")]}

    def textes_defaut(b, saison, ms):
        lib = b["entite_lib"] or b["entite"]
        p = participation(b["id"], saison)
        fi = finances(b["id"], saison)
        nr = len(lignes_coll("reunions", b["id"], saison))
        pres = par_fonction(ms, "président", "presid")
        return {
            "titre": f"Rapport de fin de saison sportive {saison}",
            "contexte": (f"Le présent rapport rend compte des activités sportives et culturelles conduites par le bureau de l'UASCEP — "
                         f"{NIV_LIB[b['niveau']].lower()} : {lib}, au cours de la saison {saison}, conformément au programme adopté en début de saison."),
            "organisation": (f"Le bureau{', présidé par ' + pres['nom'] + ' ' + (pres['prenoms'] or '') if pres else ''}, compte {len(ms)} membre(s). "
                             f"Il a tenu {nr} réunion(s) au cours de la saison et a organisé {len(p['realisees'])} activité(s) "
                             f"(sur {len(p['activites'])} programmée(s)), avec le concours des écoles, des enseignants et des parents d'élèves."),
            "resultats": "\n".join(f"{a['intitule'] or a['discipline']} ({jjmmaaaa(a['date'])}) : {a['resultats'] or ''} {a['distinctions'] or ''}".strip()
                                   for a in p["realisees"] if a["resultats"] or a["distinctions"]),
            "difficultes": "",
            "recommandations": "",
            "conclusion": (f"La saison {saison} a mobilisé {p['t']} participant(s) ({p['g']} garçons, {p['f']} filles). Le solde de la caisse "
                           f"en fin de saison s'élève à {fcfa(fi['solde'])}. Le bureau remercie tous les acteurs pour leur engagement."),
        }

    def rapport(b, saison, ms):
        r = q("SELECT * FROM uascep_rapports WHERE bureau_id=? AND saison=?", (b["id"], saison), un=True)
        d = textes_defaut(b, saison, ms)
        if r:
            d.update({k: r[k] for k, _l in RAPPORT_TEXTES if r[k]})
        return d, bool(r)

    def bureau_ecrit(bid):
        b = dict(bureau(bid))
        exiger_ecriture(b["niveau"])
        return b

    @app.route("/uascep/bureau/<int:bid>/saison")
    @H.connexion_requise("uascep")
    def uascep_saison(bid):
        b = dict(bureau(bid))
        saison = saison_de()
        rub = request.args.get("rub") if request.args.get("rub") in COLL else "activites"
        edit = None
        if request.args.get("modifier", type=int):
            edit = q(f"SELECT * FROM uascep_{rub} WHERE id=? AND bureau_id=?", (request.args.get("modifier", type=int), bid), un=True)
        saisons = [r["saison"] for r in q(" UNION ".join(f"SELECT saison FROM uascep_{c} WHERE bureau_id=?" for c in COLL) + " UNION SELECT saison FROM uascep_rapports WHERE bureau_id=?",
                                          (bid,) * (len(COLL) + 1))]
        return render_template("uascep_saison.html", b=b, saison=saison, saisons=sorted(set(saisons + [config.ANNEE_ACTIVE, saison]), reverse=True),
                               rub=rub, COLL=COLL, LISTES=LISTES, lignes=lignes_coll(rub, bid, saison), edit=dict(edit) if edit else None,
                               peut_ecrire=b["niveau"] in niveaux_ecriture() and b["statut"] == "actif", NIV_LIB=NIV_LIB, jjmmaaaa=jjmmaaaa, fcfa=fcfa,
                               fi=finances(bid, saison) if rub in ("caisse", "budget") else None,
                               part=participation(bid, saison) if rub == "activites" else None, DOCS_RUB=DOCS_RUB)

    @app.route("/uascep/bureau/<int:bid>/saison/<coll>/<int:rid>", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_saison_ligne(bid, coll, rid):
        if coll not in COLL:
            abort(404)
        b = bureau_ecrit(bid)
        saison = saison_de()
        d = lire_ligne(coll, request.form)
        oblig = COLL[coll]["oblig"]
        if not d.get(oblig) and d.get(oblig) != 0:
            flash(f"« {dict((k, l) for k, l, _t in COLL[coll]['champs'])[oblig]} » est obligatoire.", "danger")
            return redirect(url_for("uascep_saison", bid=bid, saison=saison, rub=coll, modifier=rid or None))
        ks = list(d)
        if rid:
            if not q(f"SELECT 1 FROM uascep_{coll} WHERE id=? AND bureau_id=?", (rid, bid), un=True):
                abort(404)
            ex(f"UPDATE uascep_{coll} SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), rid))
        else:
            ex(f"INSERT INTO uascep_{coll} (bureau_id, saison, " + ", ".join(ks) + ", maj) VALUES (?,?," + ",".join("?" * len(ks)) + ",?)",
               (bid, saison) + tuple(d[k] for k in ks) + (H.maintenant(),))
        ex("UPDATE uascep_bureaux SET maj=? WHERE id=?", (H.maintenant(), bid))
        H.journal(f"uascep_{coll}", f"{NIV_LIB[b['niveau']]} {b['entite']} — {saison}")
        flash(f"{COLL[coll]['unite'].capitalize()} enregistré(e).", "success")
        return redirect(url_for("uascep_saison", bid=bid, saison=saison, rub=coll))

    @app.route("/uascep/bureau/<int:bid>/saison/<coll>/<int:rid>/supprimer", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_saison_supprimer(bid, coll, rid):
        if coll not in COLL:
            abort(404)
        bureau_ecrit(bid)
        ex(f"DELETE FROM uascep_{coll} WHERE id=? AND bureau_id=?", (rid, bid))
        flash(f"{COLL[coll]['unite'].capitalize()} supprimé(e).", "success")
        return redirect(url_for("uascep_saison", bid=bid, saison=saison_de(), rub=coll))

    @app.route("/uascep/bureau/<int:bid>/saison/<coll>/reinitialiser", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_saison_reinitialiser(bid, coll):
        if coll not in COLL and coll != "tout":
            abort(404)
        b = bureau_ecrit(bid)
        saison = saison_de()
        for c in (COLL if coll == "tout" else [coll]):
            ex(f"DELETE FROM uascep_{c} WHERE bureau_id=? AND saison=?", (bid, saison))
        if coll == "tout":
            ex("DELETE FROM uascep_rapports WHERE bureau_id=? AND saison=?", (bid, saison))
        H.journal("uascep_saison_reinitialisee", f"{NIV_LIB[b['niveau']]} {b['entite']} — {saison} : {coll}")
        flash("Rubrique réinitialisée pour la saison " + saison + ".", "success")
        return redirect(url_for("uascep_saison", bid=bid, saison=saison, rub=coll if coll in COLL else None))

    @app.route("/uascep/bureau/<int:bid>/rapport", methods=["GET", "POST"])
    @H.connexion_requise("uascep")
    def uascep_rapport(bid):
        b = dict(bureau(bid))
        saison = saison_de()
        ms = membres(bid)
        if request.method == "POST":
            exiger_ecriture(b["niveau"])
            if request.form.get("reinitialiser"):
                ex("DELETE FROM uascep_rapports WHERE bureau_id=? AND saison=?", (bid, saison))
                flash("Rapport réinitialisé : les textes sont de nouveau proposés d'après les données de la saison.", "success")
            else:
                d = {k: (request.form.get(k) or "").strip()[:8000] for k, _l in RAPPORT_TEXTES}
                ex("INSERT INTO uascep_rapports (bureau_id, saison, " + ", ".join(d) + ", maj) VALUES (?,?," + ",".join("?" * len(d)) + ",?) "
                   "ON CONFLICT(bureau_id, saison) DO UPDATE SET " + ", ".join(f"{k}=excluded.{k}" for k in d) + ", maj=excluded.maj",
                   (bid, saison) + tuple(d.values()) + (H.maintenant(),))
                H.journal("uascep_rapport", f"{NIV_LIB[b['niveau']]} {b['entite']} — {saison}")
                flash("Rapport enregistré.", "success")
            return redirect(url_for("uascep_rapport", bid=bid, saison=saison))
        r, enregistre = rapport(b, saison, ms)
        return render_template("uascep_rapport.html", b=b, saison=saison, r=r, enregistre=enregistre, TEXTES=RAPPORT_TEXTES, NIV_LIB=NIV_LIB,
                               part=participation(bid, saison), fi=finances(bid, saison), fcfa=fcfa, jjmmaaaa=jjmmaaaa,
                               peut_ecrire=b["niveau"] in niveaux_ecriture() and b["statut"] == "actif",
                               manque=[t for t, f in (("Rapporteur", ("rapporteur",)), ("Secrétaire général", ("secrétaire général", "secrétaire")),
                                                      ("Trésorier général", ("trésorier",)), ("Président", ("président",)))
                                       if not par_fonction(ms, *f)])

    # ---- documents de la saison (PDF signés + Excel)
    def sigs_saison(b, ms, roles):
        out = []
        lib = {"R": ("Le / La Rapporteur(e)", ("rapporteur",)), "SG": ("Le / La Secrétaire général(e)", ("secrétaire général", "secretaire general", "secrétaire")),
               "T": ("Le / La Trésorier(ère) général(e)", ("trésorier général", "tresorier general", "trésorier")),
               "CC": ("Visa du commissaire aux comptes", ("commissaire aux comptes",)), "P": ("Le / La Président(e)", ("président", "presid"))}
        for r in roles:
            if r == "V":
                out.append(visa(b))
                continue
            t, pref = lib[r]
            m = par_fonction(ms, *pref)
            out.append(signataire(m, b, t) if m else {"titre": t, "nom": "", "image": None, "cachet": None})
        return out

    def para_multi(t, st):
        from reportlab.platypus import Paragraph
        return [Paragraph(MPtxt(x), st) for x in (t or "").split("\n") if x.strip()] or [Paragraph("—", st)]

    def table_simple(ent, rows, larg, L, total=None):
        from reportlab.platypus import Paragraph
        st = _styles()["petit"]
        data = [[Paragraph(f"<b>{x}</b>", st) for x in ent]] + [[Paragraph(MPtxt(x), st) for x in r] for r in rows]
        if total:
            data.append([Paragraph(f"<b>{MPtxt(x)}</b>", st) for x in total])
        if len(data) == 1:
            data.append([Paragraph("—", st)] + [Paragraph("", st) for _ in ent[1:]])
        return _grille(data, larg, L)

    def flow_activites(p, L, resultats=True):
        rows = [[jjmmaaaa(a["date"]) + (" → " + jjmmaaaa(a["date_fin"]) if a["date_fin"] else ""), a["intitule"] or "", a["discipline"] or "", a["categorie"] or "",
                 a["lieu"] or "", a["statut"] or "", a["pg"] or 0, a["pf"] or 0, (a["pg"] or 0) + (a["pf"] or 0)]
                + ([((a["resultats"] or "") + (" — " + a["distinctions"] if a["distinctions"] else ""))] if resultats else []) for a in p["activites"]]
        ent = ["Date", "Activité / compétition", "Discipline", "Catégorie", "Lieu", "Statut", "G", "F", "T"] + (["Résultats et distinctions"] if resultats else [])
        larg = [17, 0, 20, 16, 20, 14, 8, 8, 9] + ([36] if resultats else [])
        tot = ["Total (réalisées)", "", "", "", "", f"{len(p['realisees'])}", p["g"], p["f"], p["t"]] + ([""] if resultats else [])
        return table_simple(ent, rows, larg, L, tot)

    def flow_finances(fi, L):
        from reportlab.platypus import Paragraph, Spacer
        S = _styles()
        out = [Paragraph("<b>Journal de caisse</b>", S["p"]),
               table_simple(["Date", "Pièce n°", "Libellé", "Catégorie", "École", "Recette", "Dépense", "Solde"],
                            [[jjmmaaaa(r["date"]), r["piece"] or "", r["libelle"] or "", r["categorie"] or "", r["ecole"] or "",
                              fcfa(r["montant"]) if r["nature"] == "Recette" else "", fcfa(r["montant"]) if r["nature"] != "Recette" else "", fcfa(r["solde"])] for r in fi["journal"]],
                            [18, 16, 0, 34, 28, 22, 22, 22], L, ["Totaux", "", "", "", "", fcfa(fi["recettes"]), fcfa(fi["depenses"]), fcfa(fi["solde"])]),
               Spacer(1, 4), Paragraph("<b>Budget prévisionnel et réalisé</b>", S["p"]),
               table_simple(["Sens", "Catégorie", "Libellé", "Prévu", "Réalisé", "Écart", "Taux"],
                            [[x["nature"] or "", x["categorie"] or "", x["libelle"] or "", fcfa(x["prevu"]), fcfa(x["realise"]), fcfa(x["ecart"]),
                              f"{x['taux']} %" if x["taux"] is not None else "—"] for x in fi["budget"]], [18, 40, 0, 24, 24, 24, 14], L),
               Spacer(1, 4), Paragraph("<b>Cotisations par école</b>", S["p"]),
               table_simple(["École", "Montant versé"], [[e, fcfa(v)] for e, v in fi["cotisations"]], [0, 40], L,
                            ["Total", fcfa(sum(v for _e, v in fi["cotisations"]))] if fi["cotisations"] else None),
               Spacer(1, 4), Paragraph(f"<b>Situation financière de fin de saison</b> : recettes {fcfa(fi['recettes'])} · dépenses {fcfa(fi['depenses'])} · "
                                       f"<b>solde {fcfa(fi['solde'])}</b>.", S["p"])]
        return out

    def entete_doc(titre, b, saison):
        from reportlab.platypus import Paragraph, Spacer
        S = _styles()
        return [Paragraph(titre, S["t"]), Paragraph(f"Bureau de l'UASCEP — {NIV_LIB[b['niveau']]} : {MPtxt(b['entite_lib'] or b['entite'])} · saison {saison}", S["s"]),
                Spacer(1, 6)]

    @app.route("/uascep/bureau/<int:bid>/rapport.pdf")
    @H.connexion_requise("uascep")
    def uascep_rapport_pdf(bid):
        from reportlab.platypus import PageBreak, Paragraph, Spacer
        b = dict(bureau(bid))
        saison = saison_de()
        ms = membres(bid)
        r, _e = rapport(b, saison, ms)
        p, fi = participation(bid, saison), finances(bid, saison)
        S = _styles()
        L = _largeur()
        code = code_doc("uascep_rapport", f"Rapport de fin de saison sportive {saison} — bureau UASCEP {NIV_LIB[b['niveau']]} : {b['entite_lib'] or b['entite']}",
                        f"uascep:rapport:{bid}:{saison}:{b['maj'] or ''}:{len(p['activites'])}:{fi['solde']}")
        lib = MPtxt(b["entite_lib"] or b["entite"])
        from reportlab.platypus import Table
        grand = Table([[logo_flowable(b["niveau"], b["entite"], b["entite_lib"], 170)]], colWidths=[L])
        grand.setStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")])
        garde = [Spacer(1, 10), grand, Spacer(1, 12), Paragraph("UNION DES ASSOCIATIONS SPORTIVES ET CULTURELLES DES ÉCOLES PRIMAIRES (UASCEP)", S["s"]), Spacer(1, 14),
                 Paragraph(MPtxt(r["titre"]).upper(), S["t"]), Spacer(1, 10), Paragraph(f"Bureau — {NIV_LIB[b['niveau']]} : <b>{lib}</b>", S["s"]),
                 Paragraph(f"Saison {saison}", S["s"]), Spacer(1, 30),
                 table_simple(["Fonction", "Nom et prénoms", "Contact"], [[m["fonction"] or "", f"{m['nom']} {m['prenoms'] or ''}", m["contact"] or ""] for m in ms], [55, 0, 40], L),
                 Spacer(1, 20), Paragraph(f"Édité le {date.today().strftime('%d/%m/%Y')} · document vérifiable (code {code or '—'})", S["s"]), PageBreak()]
        sec = lambda n, t: Paragraph(f"<b>{n}. {t}</b>", S["p"])  # noqa: E731
        h = garde + [sec(1, "Contexte")] + para_multi(r["contexte"], S["p"]) + [sec(2, "Organisation")] + para_multi(r["organisation"], S["p"])
        h += [sec(3, "Activités réalisées"), flow_activites(p, L), Spacer(1, 4), sec(4, "Participation")]
        h += [table_simple(["Discipline", "Activités", "Garçons", "Filles", "Total"], [[d, x[0], x[1], x[2], x[1] + x[2]] for d, x in p["par_discipline"]],
                           [0, 22, 22, 22, 22], L, ["Total", len(p["realisees"]), p["g"], p["f"], p["t"]])]
        h += [sec(5, "Résultats et distinctions")] + para_multi(r["resultats"], S["p"])
        h += [sec(6, "Bilan financier (module du trésorier)")] + flow_finances(fi, L)
        h += [sec(7, "Difficultés rencontrées")] + para_multi(r["difficultes"], S["p"]) + [sec(8, "Recommandations")] + para_multi(r["recommandations"], S["p"])
        h += [sec(9, "Conclusion")] + para_multi(r["conclusion"], S["p"]) + [Spacer(1, 6), _pied(sigs_saison(b, ms, ["R", "SG", "T", "P"]), L, None),
                                                                             _pied(sigs_saison(b, ms, ["V"]), L, code)]
        return H.pdf_reponse(_pdf(h, f"Rapport de fin de saison {saison}"), f"uascep_rapport_saison_{saison}_{bid}.pdf")

    @app.route("/uascep/bureau/<int:bid>/saison/<doc>.pdf")
    @H.connexion_requise("uascep")
    def uascep_saison_pdf(bid, doc):
        from reportlab.platypus import Spacer
        if doc not in DOCS_SAISON:
            abort(404)
        b = dict(bureau(bid))
        saison = saison_de()
        ms = membres(bid)
        titre, roles, typ = DOCS_SAISON[doc]
        paysage = doc in ("journal", "finances", "engagements")
        L = _largeur(paysage)
        h = entete_doc(titre.upper(), b, saison)
        if doc == "journal":
            p = participation(bid, saison)
            h += [flow_activites(p, L)]
            n = len(p["activites"])
        elif doc == "finances":
            fi = finances(bid, saison)
            h += flow_finances(fi, L)
            n = len(fi["journal"])
        elif doc == "engagements":
            ls = lignes_coll("engagements", bid, saison)
            h += [table_simple(["École", "Discipline", "Catégorie", "Équipe", "Encadreur", "Contact", "G", "F", "Droit d'engagement", "Date"],
                               [[e["ecole"] or "", e["discipline"] or "", e["categorie"] or "", e["equipe"] or "", e["encadreur"] or "", e["contact"] or "",
                                 e["jg"] or 0, e["jf"] or 0, fcfa(e["droit"]), jjmmaaaa(e["date"])] for e in ls],
                               [0, 26, 20, 30, 36, 24, 9, 9, 24, 18], L,
                               ["Total", "", "", f"{len(ls)} équipe(s)", "", "", sum(e["jg"] or 0 for e in ls), sum(e["jf"] or 0 for e in ls),
                                fcfa(sum(e["droit"] or 0 for e in ls)), ""])]
            n = len(ls)
        else:
            ls = lignes_coll("materiel", bid, saison)
            h += [table_simple(["Désignation", "Discipline", "Qté", "État", "Origine", "Acquis le", "Valeur", "Détenteur / stockage"],
                               [[x["designation"] or "", x["discipline"] or "", x["quantite"] or 0, x["etat"] or "", x["origine"] or "", jjmmaaaa(x["date"]),
                                 fcfa(x["valeur"]), x["detenteur"] or ""] for x in ls], [0, 24, 10, 18, 24, 18, 22, 30], L,
                               ["Total", "", sum(x["quantite"] or 0 for x in ls), "", "", "", fcfa(sum(x["valeur"] or 0 for x in ls)), ""])]
            n = len(ls)
        code = code_doc(typ, f"{titre} {saison} — bureau UASCEP {NIV_LIB[b['niveau']]} : {b['entite_lib'] or b['entite']} ({n} ligne(s))",
                        f"uascep:{doc}:{bid}:{saison}:{b['maj'] or ''}:{n}")
        h += [Spacer(1, 8), _pied(sigs_saison(b, ms, roles), L, code)]
        return H.pdf_reponse(_pdf(h, titre, paysage), f"uascep_{doc}_{saison}_{bid}.pdf")

    @app.route("/uascep/bureau/<int:bid>/reunion/<int:rid>.pdf")
    @H.connexion_requise("uascep")
    def uascep_reunion_pdf(bid, rid):
        from reportlab.platypus import Paragraph, Spacer
        b = dict(bureau(bid))
        r = q("SELECT * FROM uascep_reunions WHERE id=? AND bureau_id=?", (rid, bid), un=True)
        if not r:
            abort(404)
        r = dict(r)
        ms = membres(bid)
        S = _styles()
        L = _largeur()
        code = code_doc("uascep_cr", f"Compte rendu de réunion du {jjmmaaaa(r['date'])} — bureau UASCEP {NIV_LIB[b['niveau']]} : {b['entite_lib'] or b['entite']}",
                        f"uascep:cr:{rid}:{r['maj'] or ''}")
        h = entete_doc("COMPTE RENDU DE RÉUNION", b, r["saison"])
        h += [Paragraph(f"<b>{MPtxt(r['type'] or 'Réunion')}</b> du {jjmmaaaa(r['date']) or '……'}{' à ' + MPtxt(r['heure']) if r['heure'] else ''}"
                        f"{', ' + MPtxt(r['lieu']) if r['lieu'] else ''}.", S["p"])]
        for k, t in (("ordre", "Ordre du jour"), ("presents", "Présents"), ("absents", "Absents"), ("deroulement", "Déroulement et échanges"),
                     ("decisions", "Décisions et recommandations")):
            h += [Paragraph(f"<b>{t}</b>", S["p"])] + para_multi(r[k], S["p"])
        if r["prochaine"]:
            h.append(Paragraph(f"<b>Prochaine réunion</b> : {jjmmaaaa(r['prochaine'])}.", S["p"]))
        h += [Paragraph("L'ordre du jour étant épuisé, la séance a été levée.", S["p"]), Spacer(1, 6), _pied(sigs_saison(b, ms, ["R", "SG", "P"]), L, code)]
        return H.pdf_reponse(_pdf(h, "Compte rendu de réunion UASCEP"), f"uascep_cr_{rid}.pdf")

    def colonnes_excel(coll):
        lib = {k: l for k, l, _t in COLL[coll]["champs"]}
        return [(c[0], c[1]) if isinstance(c, tuple) else (c, lib[c]) for c in EXCEL[coll]]

    def lignes_excel(coll, bid, saison):
        """Lignes d'un registre pour l'Excel commun (colonnes calculées comprises) et ligne de totaux."""
        typ = {k: t for k, _l, t in COLL[coll]["champs"]}
        if coll == "caisse":
            ls = finances(bid, saison)["journal"]
        elif coll == "budget":
            ls = finances(bid, saison)["budget"]
        else:
            ls = lignes_coll(coll, bid, saison)
        def val(x, k):
            if k == "=pt":
                return (x["pg"] or 0) + (x["pf"] or 0)
            if k == "=jt":
                return (x["jg"] or 0) + (x["jf"] or 0)
            if k == "=recette":
                return (x["montant"] or 0) if x["nature"] == "Recette" else ""
            if k == "=depense":
                return (x["montant"] or 0) if x["nature"] != "Recette" else ""
            if k == "=solde":
                return x["solde"]
            if k == "=realise":
                return x["realise"]
            if k == "=ecart":
                return x["ecart"]
            if k == "=taux":
                return f"{x['taux']} %" if x["taux"] is not None else "—"
            return jjmmaaaa(x[k]) if typ.get(k) == "date" else (x[k] if x[k] is not None else "")
        cols = colonnes_excel(coll)
        rows = [[val(x, k) for k, _l in cols] for x in ls]
        somme = {"ecoles", "equipes", "pg", "pf", "=pt", "encadreurs", "jg", "jf", "=jt", "droit", "=recette", "=depense", "prevu", "=realise", "=ecart",
                 "quantite", "valeur"}
        if ls and any(k in somme for k, _l in cols):
            rows.append(["Total" if i == 0 else (sum(r[i] or 0 for r in rows if isinstance(r[i], int)) if k in somme else "") for i, (k, _l) in enumerate(cols)])
        return [l for _k, l in cols], rows

    @app.route("/uascep/bureau/<int:bid>/saison.xlsx")
    @H.connexion_requise("uascep")
    def uascep_saison_xlsx(bid):
        """v1.25 : une feuille par registre, mêmes noms de feuilles et mêmes colonnes que le module commun (JS)."""
        b = dict(bureau(bid))
        saison = saison_de()
        ms = membres(bid)
        f = []
        for coll, d in COLL.items():
            ent, rows = lignes_excel(coll, bid, saison)
            f.append((d["feuille"], ent, rows, {}))
        fi = finances(bid, saison)
        f.append(("État financier", ["Rubrique", "Montant (F)"], [["Recettes", fi["recettes"]], ["Dépenses", fi["depenses"]], ["Solde", fi["solde"]]]
                  + [[f"{s} — {c}", v] for (s, c), v in fi["par_cat"]] + [[f"Cotisation — {e}", v] for e, v in fi["cotisations"]], {}))
        r, _e = rapport(b, saison, ms)
        f.append(("Rapport", ["Rubrique", "Texte"], [[l, r[k]] for k, l in RAPPORT_TEXTES], {}))
        nom = "rapport" if request.args.get("rapport") else "saison"
        return H.xlsx.reponse_classeur(f"uascep_{nom}_{saison}.xlsx", f)

    @app.route("/uascep/bureau/<int:bid>/saison/import", methods=["POST"])
    @H.connexion_requise("uascep")
    def uascep_saison_import(bid):
        """v1.25 : import du classeur de la saison (fichier d'une autre application : mêmes feuilles et colonnes).
        Les lignes importées s'ajoutent à la saison choisie ; les colonnes calculées et la ligne « Total » sont ignorées."""
        import outils_xlsx as X
        b = bureau_ecrit(bid)
        saison = saison_de()
        fichier = request.files.get("fichier")
        if not fichier or not fichier.filename:
            flash("Choisissez le fichier Excel de la saison.", "warning")
            return redirect(url_for("uascep_saison", bid=bid, saison=saison))
        try:
            wb = X._openpyxl().load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            flash("Fichier illisible : utilisez un classeur Excel (.xlsx).", "danger")
            return redirect(url_for("uascep_saison", bid=bid, saison=saison))
        feuilles = {X.normaliser(ws.title): ws for ws in wb.worksheets}
        bilan = []
        for coll, d in COLL.items():
            ws = feuilles.get(X.normaliser(d["feuille"])) or feuilles.get(X.normaliser(d["titre"]))
            if ws is None:
                continue
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            i0 = next((i for i, r in enumerate(rows[:15]) if r and any(X.normaliser(v) in {X.normaliser(l) for _k, l, _t in d["champs"]} for v in r if v)), None)
            if i0 is None:
                continue
            ent = [X.normaliser(v) for v in rows[i0]]
            idx = {k: (ent.index(X.normaliser(l)) if X.normaliser(l) in ent else None) for k, l, _t in d["champs"]}
            n = 0
            for r in rows[i0 + 1:]:
                if not r or not any(v not in (None, "") for v in r) or X.normaliser(r[0]) == "total":
                    continue
                brut = {k: X.valeur(r, i) for k, i in idx.items()}
                if coll == "caisse" and not brut.get("montant"):
                    ir, idp = (ent.index("recette f") if "recette f" in ent else None), (ent.index("depense f") if "depense f" in ent else None)
                    rec, dep = X.valeur(r, ir), X.valeur(r, idp)
                    brut["montant"] = rec or dep
                    if not brut.get("nature"):
                        brut["nature"] = "Recette" if rec else "Dépense"
                for k, _l, t in d["champs"]:
                    if t == "date" and brut.get(k):
                        brut[k] = iso(brut[k]) or brut[k]
                v = lire_ligne(coll, brut)
                if not v.get(d["oblig"]) and v.get(d["oblig"]) != 0:
                    continue
                ks = list(v)
                ex(f"INSERT INTO uascep_{coll} (bureau_id, saison, " + ", ".join(ks) + ", maj) VALUES (?,?," + ",".join("?" * len(ks)) + ",?)",
                   (bid, saison) + tuple(v[k] for k in ks) + (H.maintenant(),))
                n += 1
            if n:
                bilan.append(f"{d['feuille']} : {n}")
        H.journal("uascep_saison_import", f"{NIV_LIB[b['niveau']]} {b['entite']} — {saison} : " + ", ".join(bilan))
        flash(("Import de la saison " + saison + " — " + ", ".join(bilan)) if bilan else "Aucune ligne reconnue dans le fichier.",
              "success" if bilan else "warning")
        return redirect(url_for("uascep_saison", bid=bid, saison=saison))

    @app.route("/uascep.pdf")
    @H.connexion_requise("uascep")
    def uascep_pdf():
        from reportlab.platypus import PageBreak
        logo_autorite()
        vis = niveaux_visibles()
        niv = [request.args["niveau"]] if request.args.get("niveau") in vis else vis
        entite = request.args.get("entite") or ""
        L = _largeur(True)
        h = []
        for c in niv:
            for b in q("SELECT * FROM uascep_bureaux WHERE COALESCE(ecole_id,0)=COALESCE(?,0) AND niveau=? AND statut='actif'" + (" AND entite=?" if entite else "") + " ORDER BY entite",
                       (cle_ecole(), c) + ((entite,) if entite else ())):
                if h:
                    h.append(PageBreak())
                h += h_composition(dict(b), membres(b["id"]), L)   # v1.24 : signatures, cachets, visa, QR
        if not h:
            flash("Aucun bureau à imprimer.", "warning")
            return redirect(url_for("uascep"))
        return H.pdf_reponse(_pdf(h, "Bureaux UASCEP", True), "bureaux_uascep.pdf")

    def MPtxt(t):
        return str(t if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ------------------------------------------------------------------ v1.25 : logo de l'UASCEP (par bureau / entité)
    for col in ("logo_haut", "logo_definition", "logo_bas", "logo_c1", "logo_c2", "logo_c3", "logo_image"):
        H.ajouter_colonne("uascep_bureaux", col, "TEXT")

    def logo_de(niveau, entite, lib=None):
        """(paramètres du logo, image importée (data URL) ou None) de l'entité : bureau actif, sinon valeurs par défaut."""
        import logo_uascep as LG
        b = bureau_actif(niveau, entite) if niveau in NIV_LIB else None
        lib = lib or (b["entite_lib"] if b else None) or next((l for k, l, _i in entites(niveau) if k == entite), entite)
        d = {"bas": LG.texte_bas(niveau, lib)}
        img = None
        if b:
            b = dict(b)
            for k in ("haut", "definition", "bas", "c1", "c2", "c3"):
                if b.get("logo_" + k):
                    d[k] = b["logo_" + k]
            img = b.get("logo_image") or None
        return LG.params(d), img

    def logo_flowable(niveau, entite, lib=None, taille=60):
        import logo_uascep as LG
        import pdfs
        p, img = logo_de(niveau, entite, lib)
        return LG.flowable(p, taille, pdfs.image_data_url(img) if img else None)

    def bandeau_logo(niveau, entite, lib, largeur, taille=46):
        """Bandeau « logo + Union des associations… — UASCEP — niveau : entité » placé sous l'en-tête officiel."""
        import logo_uascep as LG
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph, Table, TableStyle
        p, _img = logo_de(niveau, entite, lib)
        lib = lib or next((l for k, l, _i in entites(niveau) if k == entite), entite)
        st = ParagraphStyle("bl", fontName="Helvetica-Bold", fontSize=9.5, leading=12)
        txt = Paragraph(f"{MPtxt(p['definition'].upper())} — {MPtxt(p['haut'])}<br/><font size='8.5' color='#475467'>"
                        f"{MPtxt(NIV_LIB.get(niveau, niveau))} : {MPtxt(lib)}</font>", st)
        t = Table([[logo_flowable(niveau, entite, lib, taille), txt]], colWidths=[taille + 8, largeur - taille - 8])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        _ = LG
        return t

    @app.route("/uascep/logo/<niveau>/<path:entite>", methods=["GET", "POST"])
    @H.connexion_requise("uascep")
    def uascep_logo(niveau, entite):
        """Réglage du logo de l'entité (texte du haut, définition, texte du bas, couleurs) ou logo importé ; aperçu ; SVG / PNG."""
        import logo_uascep as LG
        if niveau not in niveaux_visibles():
            abort(404)
        lib = next((l for k, l, _i in entites(niveau) if k == entite), entite)
        if request.method == "POST":
            exiger_ecriture(niveau)
            b = bureau_actif(niveau, entite, creer=True, lib=lib)
            f = request.form
            if f.get("reinitialiser"):
                ex("UPDATE uascep_bureaux SET logo_haut=NULL, logo_definition=NULL, logo_bas=NULL, logo_c1=NULL, logo_c2=NULL, logo_c3=NULL, "
                   "logo_image=NULL, maj=? WHERE id=?", (H.maintenant(), b["id"]))
                flash("Logo réinitialisé (dessin par défaut).", "success")
                return redirect(url_for("uascep_logo", niveau=niveau, entite=entite))
            d = {k: (f.get(k) or "").strip()[:200] for k in ("haut", "definition", "bas")}
            for k in ("c1", "c2", "c3"):
                v = (f.get(k) or "").strip()
                d[k] = v if re.fullmatch(r"#[0-9A-Fa-f]{6}", v) else ""
            img = b["logo_image"] if "logo_image" in b.keys() else None
            try:
                nouv = lire_image(request.files.get("logo_fichier"))
            except ValueError as e:
                flash(str(e), "danger")
                return redirect(url_for("uascep_logo", niveau=niveau, entite=entite))
            if nouv:
                img = nouv
            if f.get("retirer_image"):
                img = None
            ex("UPDATE uascep_bureaux SET logo_haut=?, logo_definition=?, logo_bas=?, logo_c1=?, logo_c2=?, logo_c3=?, logo_image=?, maj=? WHERE id=?",
               (d["haut"] or None, d["definition"] or None, d["bas"] or None, d["c1"] or None, d["c2"] or None, d["c3"] or None, img,
                H.maintenant(), b["id"]))
            H.journal("uascep_logo", f"{NIV_LIB[niveau]} {entite}")
            flash("Logo enregistré.", "success")
            return redirect(url_for("uascep_logo", niveau=niveau, entite=entite))
        p, img = logo_de(niveau, entite, lib)
        return render_template("uascep_logo.html", niveau=niveau, entite=entite, lib=lib, p=p, img=img, NIV_LIB=NIV_LIB, svg=LG.svg(p, 260),
                               peut_ecrire=niveau in niveaux_ecriture(), defaut=LG.DEFAUT, bas_defaut=LG.texte_bas(niveau, lib))

    @app.route("/uascep/logo/<niveau>/<path:entite>.<fmt>")
    @H.connexion_requise("uascep")
    def uascep_logo_fichier(niveau, entite, fmt):
        import logo_uascep as LG
        from flask import Response
        if niveau not in niveaux_visibles() or fmt not in ("svg", "png"):
            abort(404)
        p, img = logo_de(niveau, entite)
        nom = re.sub(r"[^A-Za-z0-9]+", "_", f"logo_uascep_{niveau}_{entite}")
        if fmt == "svg":
            return Response(LG.svg(p, 800), mimetype="image/svg+xml", headers={"Content-Disposition": f"attachment; filename={nom}.svg"})
        if img and request.args.get("importe"):
            import base64
            return Response(base64.b64decode(img.split(",", 1)[1]), mimetype=img[5:img.index(";")])
        taille = max(64, min(1600, request.args.get("taille", type=int) or 800))
        return Response(LG.png(p, taille), mimetype="image/png", headers={"Content-Disposition": f"attachment; filename={nom}.png"})

    # ------------------------------------------------------------------ v1.25 : services offerts aux autres modules
    # (sport scolaire : entités, bureaux, signataires ; les résultats des compétitions alimentent le journal de la saison)
    H.ajouter_colonne("uascep_activites", "source", "TEXT")

    def publier_activite(niveau, entite, lib, source, d, saison=None):
        """Crée ou met à jour la ligne du journal de la saison du bureau actif (créé au besoin) ; d : rubriques de COLL['activites']."""
        b = bureau_actif(niveau, entite, creer=True, lib=lib)
        saison = saison or config.ANNEE_ACTIVE
        d = {k: v for k, v in d.items() if k in {c for c, _l, _t in COLL["activites"]["champs"]}}
        r = q("SELECT id FROM uascep_activites WHERE bureau_id=? AND saison=? AND source=?", (b["id"], saison, source), un=True)
        ks = list(d)
        if r:
            ex("UPDATE uascep_activites SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), r["id"]))
            return r["id"]
        return ex("INSERT INTO uascep_activites (bureau_id, saison, source, " + ", ".join(ks) + ", maj) VALUES (?,?,?," + ",".join("?" * len(ks)) + ",?)",
                  (b["id"], saison, source) + tuple(d[k] for k in ks) + (H.maintenant(),))

    def signataires_entite(niveau, entite, roles=("P",)):
        """Signatures (cachets) des responsables du bureau actif de l'entité : P, SG, T, R, CC, S (responsable sport), V (visa)."""
        b = bureau_actif(niveau, entite)
        if not b:
            pseudo = {"niveau": niveau, "entite": entite}
            return [visa(pseudo)] if "V" in roles else []
        b = dict(b)
        ms = membres(b["id"])
        out = []
        for r in roles:
            if r == "S":
                m = par_fonction(ms, "responsable sport")
                if m:
                    out.append(signataire(m, b, "Le / La Responsable sport"))
            else:
                out += sigs_saison(b, ms, [r])
        return out

    import types as _types
    H.uascep = _types.SimpleNamespace(NIVEAUX=NIVEAUX, NIV_LIB=NIV_LIB, DISCIPLINES=DISCIPLINES, CATEGORIES=CATEGORIES, entites=entites,
                                      niveaux_visibles=niveaux_visibles, niveaux_ecriture=niveaux_ecriture, bureau_actif=bureau_actif,
                                      membres=membres, publier_activite=publier_activite, signataires_entite=signataires_entite,
                                      visa=visa, juridiction=juridiction, logo_de=logo_de, logo_flowable=logo_flowable,
                                      bandeau_logo=bandeau_logo)


def dessiner_cachet(c, ca, cx, cy, rayon):
    """Dessine un cachet décrit par cachet_de() (ou ('ecole',) : cachet de l'école) centré en (cx, cy)."""
    import cachet as K
    import pdfs
    if not ca:
        return
    if ca[0] == "rond":
        K.dessiner(c, cx, cy, rayon, ca[1], ca[2], ca[3], ca[4] if len(ca) > 4 else "bleu")
    elif ca[0] == "rect":
        K.dessiner_nom(c, cx, cy, ca[1], ca[2], 2.9 * rayon)
    elif ca[0] == "image":
        img = pdfs.image_data_url(ca[1])
        if img is not None:
            c.drawImage(img, cx - rayon, cy - rayon, 2 * rayon, 2 * rayon, preserveAspectRatio=True, mask="auto")
    elif ca[0] == "ecole":
        pdfs.cachet_ecole(c, cx, cy, rayon)


def bloc_signatures(sigs, largeur, code=None):
    """v1.24 — signatures côte à côte avec cachet (rond, griffe ou image) et code QR de vérification à gauche.
    sigs : [{titre, nom, image (ImageReader | None), cachet}]"""
    import pdfs
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Flowable

    class _Bloc(Flowable):
        def __init__(self):
            super().__init__()
            self.height = 46 * mm

        def wrap(self, *_):
            return largeur, self.height

        def draw(self):
            c = self.canv
            x0 = 0
            if code:
                t = 20 * mm
                pdfs._qr(c, code, 0, 9 * mm, taille=t, legende=False)
                c.setFont("Helvetica", 6.3)
                c.setFillColor(colors.black)
                c.drawString(0, 6 * mm, f"Document vérifiable · code {code}")
                c.drawString(0, 3 * mm, pdfs.texte_verif(code)[:58])
                x0 = 46 * mm
            n = max(1, len(sigs))
            w = (largeur - x0) / n
            for i, s in enumerate(sigs):
                x = x0 + w * (i + 0.5)
                y = self.height - 8
                c.setFillColor(colors.black)
                from reportlab.pdfbase.pdfmetrics import stringWidth
                titre, fs = (s.get("titre") or "")[:70], 8.3 if w >= 48 * mm else 7.4
                c.setFont("Helvetica-Bold", fs)
                if stringWidth(titre, "Helvetica-Bold", fs) > w - 2 * mm and " " in titre:   # titre sur deux lignes
                    mots = titre.split(" ")
                    k = max(1, len(mots) // 2)
                    c.drawCentredString(x, y + fs * 0.6, " ".join(mots[:k]))
                    c.drawCentredString(x, y - fs * 0.6, " ".join(mots[k:]))
                else:
                    c.drawCentredString(x, y, titre)
                ca = s.get("cachet")
                if ca:
                    if ca[0] == "rect":
                        dessiner_cachet(c, ca, x + 3 * mm, y - 30 * mm, 12 * mm)
                    else:
                        dessiner_cachet(c, ca, x - 10 * mm, y - 17 * mm, 12 * mm)
                if s.get("image") is not None:
                    c.drawImage(s["image"], x - 20 * mm, y - 26 * mm, 40 * mm, 17 * mm, preserveAspectRatio=True, mask="auto")
                elif not ca:
                    c.setStrokeColor(colors.HexColor("#98A2B3"))
                    c.setLineWidth(0.4)
                    c.line(x - 20 * mm, y - 24 * mm, x + 20 * mm, y - 24 * mm)
                if s.get("nom") and not (ca and ca[0] == "rect"):
                    c.setFillColor(colors.black)
                    c.setFont("Helvetica", 8.3)
                    c.drawCentredString(x, y - 33 * mm, s["nom"][:48])
    return _Bloc()
