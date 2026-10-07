# -*- coding: utf-8 -*-
"""
GESCOL – Gestion d'établissement scolaire (CPFA, Bénin)
Lancement : python app.py   puis ouvrir http://localhost:5000
Compte initial : admin / admin123 (changement demandé à la première connexion)
"""
import csv
import hashlib
import io
import os
import secrets
import sys
from datetime import date, datetime
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_file, session, url_for, Response)
from werkzeug.security import check_password_hash, generate_password_hash

import config
import pdfs
from calcul import (APPRECIATIONS, LigneNote, MODES_CALCUL, NIVEAUX_MATERNELLE, NIVEAUX_PRIMAIRE,
                    NIVEAUX_SECONDAIRE, calculer, classer, cycle_du_niveau, statistiques)
from db import ex, fermer_db, get_db, initialiser, q

ROLES = {
    "fondateur": "Fondateur / promoteur",
    "admin": "Administrateur",
    "directeur": "Directeur",
    "secretaire": "Secrétaire",
    "comptable": "Comptable",
    "enseignant": "Enseignant",
    # applications de la Circonscription scolaire et de la DDEMP
    "responsable": "Responsable (CCS / Directeur départemental)",
    "cp": "Conseiller pédagogique",
    "chef_service": "Chef de division / de service",
    "agent": "Agent",
}
# rôles proposés selon l'application
ROLES_ECOLE = ("fondateur", "admin", "directeur", "secretaire", "comptable", "enseignant")
ROLES_JURIDICTION = ("admin", "responsable", "cp", "chef_service", "agent")
# module -> rôles autorisés en écriture
DROITS = {
    "eleves": {"admin", "directeur", "secretaire"},
    "classes": {"admin", "directeur", "secretaire"},
    "notes": {"admin", "directeur", "enseignant"},
    "paiements": {"admin", "directeur", "comptable"},
    "documents": {"admin", "directeur", "secretaire"},
    "parametres": {"admin"},
    "parents": {"admin", "directeur", "secretaire"},
    "communication": {"admin", "directeur", "secretaire"},
    "appel": {"admin", "directeur", "secretaire", "enseignant"},
    "paie": {"admin", "directeur", "comptable"},
    "tresorerie": {"admin", "directeur", "comptable"},
    "secretariat": {"admin", "directeur", "secretaire"},
    # v1.3
    "evaluations": {"admin", "directeur", "enseignant"},
    "registre": {"admin", "directeur", "secretaire", "enseignant"},
    "affichage": {"admin", "directeur", "secretaire", "enseignant"},
    "cep": {"admin", "directeur", "secretaire"},
    "synthese": {"admin", "directeur"},
    "cantine": {"admin", "directeur", "comptable", "secretaire"},
    "donnees": {"admin", "directeur", "secretaire"},
    "ecoles": {"admin", "directeur"},
    # applications Circonscription scolaire / DDEMP
    "jur_structure": {"admin", "responsable"},
    "jur_ecoles": {"admin", "responsable", "chef_service"},
    "jur_transmission": {"admin", "responsable", "chef_service", "agent"},
    "jur_personnel": {"admin", "responsable", "chef_service"},
    "jur_visites": {"admin", "responsable", "cp"},
    "jur_documents": {"admin", "responsable", "chef_service", "agent"},
    "jur_cep": {"admin", "responsable", "chef_service"},
    "jur_fiches": {"admin", "responsable", "chef_service", "cp"},
    # édition publique
    "carriere": {"admin", "directeur"},
    "depenses": {"admin", "directeur", "comptable"},
    "maitre_semaine": {"admin", "directeur", "secretaire", "enseignant"},
    "visites": {"admin", "directeur", "enseignant"},
    "patrimoine": {"admin", "directeur", "secretaire"},
    "recensement": {"admin", "directeur", "secretaire"},
    "docs_enseignant": {"admin", "directeur", "secretaire", "enseignant"},
}
TYPES_DOCS = {
    "carte": "Carte d'élève",
    "certificat_frequentation": "Certificat de fréquentation",
    "attestation_inscription": "Attestation d'inscription",
    "certificat_transfert": "Certificat de transfert",
    "fiche_cep": "Fiche CEP",
    "bulletin": "Bulletin de notes",
    "recu": "Reçu de paiement",
    "bulletin_paie": "Bulletin de paie",
    "carte_candidat": "Carte scolaire du candidat (CEP)",
}
EXT_PHOTO = {".jpg", ".jpeg", ".png"}

# Formulaire public « Inscrire mon école »
DEPARTEMENTS = ["Alibori", "Atacora", "Atlantique", "Borgou", "Collines", "Couffo", "Donga", "Littoral",
                "Mono", "Ouémé", "Plateau", "Zou"]
ORDRES = ["Maternelle et primaire", "Primaire", "Secondaire (collège)", "Secondaire (collège et lycée)",
          "Complexe (primaire + secondaire)", "Enseignement technique"]
STATUTS_ETAB = ["Privé laïc", "Privé confessionnel", "Public", "Communautaire"]
FONCTIONS = ["Fondateur / promoteur", "Directeur / directrice", "Censeur", "Secrétaire", "Comptable / économe", "Autre"]
MODULES = ["Notes et bulletins", "Élèves et inscriptions", "Paiements et reçus", "Documents officiels",
           "SMS / WhatsApp parents", "Paie du personnel"]
DEMARRAGES = ["Dès que possible", "2e trimestre 2026-2027", "3e trimestre 2026-2027", "Rentrée 2027-2028"]
OUTILS = ["Cahiers / registres papier", "Excel", "Un autre logiciel"]
SUIVIS = {"nouvelle": "Nouvelle", "contactee": "Contactée", "demo": "Démo planifiée",
          "cliente": "Cliente", "sans_suite": "Sans suite"}
_envois_ip = {}  # anti-abus simple : horodatages des envois récents par adresse IP


# ================================================================ utilitaires
def maintenant():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def journal(action, details=""):
    uid = g.user["id"] if g.get("user") else None
    ex("INSERT INTO journal (user_id, action, details, cree_le) VALUES (?,?,?,?)", (uid, action, details, maintenant()))


def peut(module):
    if not g.get("user"):
        return False
    role = "admin" if g.user["role"] == "fondateur" else g.user["role"]
    return role in DROITS[module]


def eco():
    """Identifiant de l'école courante."""
    return g.ecole["id"] if g.get("ecole") else 1


def connexion_requise(module=None):
    def deco(f):
        @wraps(f)
        def wrap(*a, **k):
            if not g.user:
                return redirect(url_for("login", suivant=request.path))
            if g.user["doit_changer_mdp"] and request.endpoint not in ("mon_compte", "logout"):
                flash("Veuillez choisir un nouveau mot de passe.", "warning")
                return redirect(url_for("mon_compte"))
            if module and not peut(module):
                abort(403)
            return f(*a, **k)
        return wrap
    return deco


def periode_de(p):
    if not 1 <= p <= len(config.PERIODES):
        abort(404)
    return config.PERIODES[p - 1]


def classe_ou_404(cid):
    c = q("SELECT * FROM classes WHERE id=?", (cid,), un=True)
    if not c:
        abort(404)
    c = dict(c)
    c["cycle"] = cycle_du_niveau(c["niveau"])
    return c


def eleve_ou_404(eid):
    e = q("SELECT * FROM eleves WHERE id=?", (eid,), un=True)
    if not e:
        abort(404)
    return e


def classe_de(eleve):
    return classe_ou_404(eleve["classe_id"]) if eleve["classe_id"] else None


def chemin_photo(eleve):
    if eleve["photo"]:
        p = os.path.join(config.INSTANCE_DIR, "photos", eleve["photo"])
        if os.path.exists(p):
            return p
    return None


CHAMPS_CARTE = ("matricule_educmaster", "nip", "numero_table", "centre_examen", "annees_scolarite")


def enregistrer_photo_data(eid, data_url):
    """Photo prise avec la caméra (ou recadrée dans le navigateur) : image JPEG en data URL."""
    if not data_url or not data_url.startswith("data:image/") or len(data_url) > 3_000_000:
        return False
    import base64
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1])))
        img = img.convert("RGB")
        img.thumbnail((600, 750))
        nom_fichier = f"{eid}.jpg"
        for ancien in (f"{eid}.png", f"{eid}.jpeg"):
            chemin = os.path.join(config.INSTANCE_DIR, "photos", ancien)
            if os.path.exists(chemin):
                os.remove(chemin)
        img.save(os.path.join(config.INSTANCE_DIR, "photos", nom_fichier), "JPEG", quality=88)
    except Exception:  # noqa: BLE001
        return False
    ex("UPDATE eleves SET photo=? WHERE id=?", (nom_fichier, eid))
    return True


def situation(eleve):
    """(total dû, total payé, reste) pour l'année active."""
    cl = classe_de(eleve)
    du = cl["frais_scolarite"] if cl else 0
    paye = q("SELECT COALESCE(SUM(montant),0) s FROM paiements WHERE eleve_id=? AND annee=? AND annule=0",
             (eleve["id"], config.ANNEE_ACTIVE), un=True)["s"]
    return du, paye, max(du - paye, 0)


def enregistrer_document(type_doc, eleve_id, libelle, cle=None):
    """Enregistre un document pour vérification. Un même bulletin / reçu garde son code."""
    if cle:
        d = q("SELECT * FROM documents WHERE type=? AND cle=?", (type_doc, cle), un=True)
        if d:
            return d["code"]
    code = secrets.token_hex(5).upper()
    horodatage = maintenant()
    empreinte = hashlib.sha256(f"{type_doc}|{eleve_id}|{libelle}|{code}|{horodatage}".encode()).hexdigest()
    ex("INSERT INTO documents (code, type, cle, eleve_id, libelle, empreinte, cree_le, cree_par) "
       "VALUES (?,?,?,?,?,?,?,?)",
       (code, type_doc, cle, eleve_id, libelle, empreinte, horodatage, g.user["id"] if g.user else None))
    return code


def pdf_reponse(contenu, nom):
    return send_file(io.BytesIO(contenu), mimetype="application/pdf", download_name=nom, as_attachment=False)


def fcfa(n):
    return f"{int(n or 0):,}".replace(",", " ") + " " + config.DEVISE


def bornes_annee(annee=None):
    """Année scolaire 2026-2027 -> ('2026-09-01', '2027-08-31')."""
    a = (annee or config.ANNEE_ACTIVE)[:4]
    return f"{a}-09-01", f"{int(a) + 1}-08-31"


def absences_eleve(eid):
    d1, d2 = bornes_annee()
    r = q("""SELECT SUM(statut='absent') absent, SUM(statut='absent' AND justifie=1) justifie,
                    SUM(statut='retard') retard FROM presences WHERE eleve_id=? AND date BETWEEN ? AND ?""",
          (eid, d1, d2), un=True)
    return {"absent": r["absent"] or 0, "justifie": r["justifie"] or 0, "retard": r["retard"] or 0}


def lire_note(brut):
    """'' -> (None, False) ; 'D' -> dispensé ; '12,5' -> 12.5. Lève ValueError si invalide."""
    brut = (brut or "").strip().replace(",", ".")
    if brut == "":
        return None, False
    if brut.upper() == "D":
        return None, True
    v = float(brut)
    if not 0 <= v <= 20:
        raise ValueError
    return round(v, 2), False


# ================================================================ calcul classe
def resultats_classe(classe, periode):
    matieres = q("SELECT * FROM matieres WHERE cycle=? AND actif=1 ORDER BY ordre, nom", (classe["cycle"],))
    eleves = q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (classe["id"],))
    notes = {}
    if eleves:
        ids = [e["id"] for e in eleves]
        marque = ",".join("?" * len(ids))
        for n in q(f"SELECT * FROM notes WHERE periode=? AND annee=? AND eleve_id IN ({marque})",
                   [periode, config.ANNEE_ACTIVE] + ids):
            notes[(n["eleve_id"], n["matiere_id"])] = n
    res = {}
    for e in eleves:
        lignes = []
        for m in matieres:
            n = notes.get((e["id"], m["id"]))
            lignes.append(LigneNote(m["code"], m["nom"], m["coefficient"], m["mode_calcul"],
                                    n["valeur"] if n else None, bool(n["dispense"]) if n else False,
                                    n["appreciation"] if n else None))
        res[e["id"]] = calculer(classe["niveau"], lignes)
    if eleves:
        for o in q(f"SELECT * FROM observations WHERE periode=? AND annee=? AND eleve_id IN ({marque})",
                   [periode, config.ANNEE_ACTIVE] + ids):
            if o["eleve_id"] in res:
                res[o["eleve_id"]].details["observation"] = o["texte"] or ""
    for eid, (rang, eq) in classer({i: r.moyenne for i, r in res.items()}).items():
        res[eid].rang, res[eid].ex_aequo, res[eid].effectif = rang, eq, len(eleves)
    return matieres, eleves, notes, res, statistiques(list(res.values()))


# ================================================================ application
PERIODES_TYPES = {
    "trimestres": ["Trimestre 1", "Trimestre 2", "Trimestre 3"],
    "semestres": ["Semestre 1", "Semestre 2"],
}
CHAMPS_PARAM = [  # (clé en base, libellé, obligatoire)
    ("ecole_nom", "Nom de l'établissement", True), ("ecole_sigle", "Sigle (utilisé dans les matricules)", True),
    ("ecole_adresse", "Adresse", True), ("ecole_ville", "Ville (lieu de signature des documents)", True),
    ("ecole_telephone", "Téléphone", False), ("ecole_email", "E-mail", False),
    ("ecole_directeur", "Nom du directeur / de la directrice", False),
]
IMAGES_ECOLE = {"logo": "Logo", "cachet": "Cachet", "signature": "Signature du directeur"}


def lire_parametres():
    vals = dict(config.DEFAUTS)
    for r in q("SELECT cle, valeur FROM parametres"):
        if r["valeur"] is not None:
            vals[r["cle"]] = r["valeur"]
    return vals


def appliquer_parametres():
    """Recopie les paramètres enregistrés dans l'application vers config (un seul
    établissement par installation)."""
    v = lire_parametres()
    for k in ("nom", "sigle", "adresse", "telephone", "email", "directeur", "ville"):
        config.ECOLE[k] = v.get("ecole_" + k, "")
    config.ANNEE_ACTIVE = v.get("annee_active") or config.DEFAUTS["annee_active"]
    config.PERIODES = PERIODES_TYPES.get(v.get("periodes"), PERIODES_TYPES["trimestres"])
    config.URL_PUBLIQUE = v.get("url_publique", "")
    if config.EDITION_IMPOSEE not in config.EDITIONS:   # édition choisie dans les paramètres
        config.EDITION = v.get("edition") if v.get("edition") in config.EDITIONS else "privee"


MODULES = ["m_en_ligne", "m_ecoles", "m_parents", "m_paiement_en_ligne", "m_appel", "m_paie", "m_tresorerie", "m_secretariat",
           # v1.3
           "m_inscriptions", "m_evaluations", "m_resultats", "m_registre", "m_affichage", "m_cep", "m_synthese",
           "m_cantine", "m_donnees",
           # édition publique (chargés dans les deux éditions ; menus affichés en édition publique)
           "m_finances_publiques", "m_carriere", "m_maitre_semaine", "m_visites", "m_patrimoine", "m_recensement",
           "m_docs_enseignant", "m_rapports",
           # transmission école → CS (dans GESCOL / GESCOL Public)
           "m_transmission",
           # applications Circonscription scolaire et DDEMP (chargés dans toutes les éditions, menus seulement là)
           "m_juridiction", "a_transmission", "a_tableau", "a_cep", "a_personnel", "a_structure", "a_visites", "a_fiches"]


def create_app(test_config=None):
    app = Flask(__name__, instance_path=config.INSTANCE_DIR,
                template_folder=os.path.join(config.WEB_DIR, "templates"),
                static_folder=os.path.join(config.WEB_DIR, "static"))
    os.makedirs(os.path.join(app.instance_path, "photos"), exist_ok=True)
    os.makedirs(config.ECOLE_DIR, exist_ok=True)
    cle = os.path.join(app.instance_path, "secret.key")
    if not os.path.exists(cle):
        with open(cle, "w") as f:
            f.write(secrets.token_hex(32))
    with open(cle) as f:
        app.config["SECRET_KEY"] = f.read().strip()
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if test_config:
        app.config.update(test_config)
    app.teardown_appcontext(fermer_db)
    with app.app_context():
        initialiser()
        appliquer_parametres()

    @app.before_request
    def charger_utilisateur():
        appliquer_parametres()
        g.user = None
        if "uid" in session:
            u = q("SELECT * FROM utilisateurs WHERE id=? AND actif=1", (session["uid"],), un=True)
            g.user = u
            if not u:
                session.clear()

    @app.context_processor
    def contexte():
        return dict(ECOLE=config.ECOLE, ANNEE=config.ANNEE_ACTIVE, PERIODES=config.PERIODES,
                    ROLES=ROLES, peut=peut, fcfa=fcfa, date_fr=pdfs.date_fr,
                    MODES_PAIEMENT=config.MODES_PAIEMENT, TYPES_DOCS=TYPES_DOCS, VERSION=config.VERSION, AUTONOME=config.AUTONOME,
                    EDITION=config.EDITION, PUBLIQUE=config.publique(), EDITIONS=config.EDITIONS,
                    JURIDICTION=config.juridiction(), NOM_APPLI=config.NOMS_APPLI.get(config.EDITION, "GESCOL"),
                    ROLES_EDITION={k: ROLES[k] for k in (ROLES_JURIDICTION if config.juridiction() else ROLES_ECOLE)},
                    EDITION_IMPOSEE=config.EDITION_IMPOSEE in config.EDITIONS, CONCEPTEUR=config.CONCEPTEUR,
                    ep_existe=lambda e: e in app.view_functions)

    @app.errorhandler(403)
    def interdit(_e):
        return render_template("erreur.html", titre="Accès refusé",
                               message="Votre rôle ne permet pas d'accéder à cette page."), 403

    @app.errorhandler(404)
    def introuvable(_e):
        return render_template("erreur.html", titre="Page introuvable",
                               message="L'élément demandé n'existe pas."), 404

    # ------------------------------------------------------------ connexion
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            u = q("SELECT * FROM utilisateurs WHERE identifiant=?", (request.form.get("identifiant", "").strip(),), un=True)
            if u and u["actif"] and check_password_hash(u["mdp_hash"], request.form.get("mdp", "")):
                session.pop("pid", None)
                session["uid"] = u["id"]
                g.user = u
                journal("connexion")
                suivant = request.args.get("suivant", "")
                return redirect(suivant if suivant.startswith("/") and not suivant.startswith("//") else url_for("accueil"))
            flash("Identifiant ou mot de passe incorrect.", "danger")
        # application autonome (sur le téléphone) : rappel des identifiants de départ tant qu'ils n'ont pas été changés
        premiere = config.AUTONOME and bool(q("SELECT 1 FROM utilisateurs WHERE identifiant='admin' AND doit_changer_mdp=1",
                                              un=True))
        return render_template("login.html", premiere=premiere)

    @app.route("/logout")
    def logout():
        session.pop("uid", None)
        return redirect(url_for("login"))

    @app.route("/mon-compte", methods=["GET", "POST"])
    @connexion_requise()
    def mon_compte():
        if request.method == "POST":
            ancien, nouveau, conf = (request.form.get(k, "") for k in ("ancien", "nouveau", "confirmation"))
            if not check_password_hash(g.user["mdp_hash"], ancien):
                flash("Mot de passe actuel incorrect.", "danger")
            elif len(nouveau) < 8:
                flash("Le nouveau mot de passe doit faire au moins 8 caractères.", "danger")
            elif nouveau != conf:
                flash("La confirmation ne correspond pas.", "danger")
            else:
                ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE id=?",
                   (generate_password_hash(nouveau), g.user["id"]))
                journal("changement_mdp")
                flash("Mot de passe modifié.", "success")
                return redirect(url_for("accueil"))
        return render_template("mon_compte.html")

    # ------------------------------------------------------------ tableau de bord
    @app.route("/")
    @connexion_requise()
    def accueil():
        if config.juridiction():   # Circonscription / DDEMP : tableau de bord de la juridiction
            for ep_ in ("jur_tableau", "jur_accueil"):
                if ep_ in app.view_functions:
                    return redirect(url_for(ep_))
        a = config.ANNEE_ACTIVE
        e_ = eco()
        # élèves / paiements de l'école courante (via leur classe)
        EL = "FROM eleves e JOIN classes c ON c.id=e.classe_id AND c.ecole_id=%d WHERE e.statut='inscrit'" % e_
        PA = "FROM paiements p JOIN eleves e ON e.id=p.eleve_id JOIN classes c ON c.id=e.classe_id AND c.ecole_id=%d WHERE p.annule=0" % e_
        stats = {
            "eleves": q("SELECT COUNT(*) n " + EL, un=True)["n"],
            "filles": q("SELECT COUNT(*) n " + EL + " AND e.sexe='F'", un=True)["n"],
            "classes": q("SELECT COUNT(*) n FROM classes WHERE ecole_id=?", (e_,), un=True)["n"],
            "attendu": q("SELECT COALESCE(SUM(c.frais_scolarite),0) s " + EL, un=True)["s"],
            "encaisse": q("SELECT COALESCE(SUM(p.montant),0) s " + PA + " AND p.annee=?", (a,), un=True)["s"],
            "aujourdhui": q("SELECT COALESCE(SUM(p.montant),0) s " + PA + " AND date(p.date_paiement)=date('now','localtime')",
                            un=True)["s"],
        }
        stats["taux"] = round(100 * stats["encaisse"] / stats["attendu"], 1) if stats["attendu"] else 0
        auj = date.today().isoformat()
        stats["absents_jour"] = q("SELECT COUNT(*) n FROM presences p JOIN eleves e ON e.id=p.eleve_id JOIN classes c "
                                  "ON c.id=e.classe_id AND c.ecole_id=? WHERE p.date=? AND p.statut='absent'", (e_, auj), un=True)["n"]
        stats["appels_faits"] = q("SELECT COUNT(*) n FROM appels a JOIN classes c ON c.id=a.classe_id AND c.ecole_id=? WHERE a.date=?",
                                  (e_, auj), un=True)["n"]
        stats["en_ligne_jour"] = q("SELECT COALESCE(SUM(montant),0) s FROM paiements_en_ligne WHERE statut='approuve' "
                                   "AND date(maj_le)=date('now','localtime')", un=True)["s"]
        stats["parents"] = q("SELECT COUNT(*) n FROM parents WHERE actif=1", un=True)["n"]
        stats["courrier"] = q("SELECT COUNT(*) n FROM courriers WHERE statut='a_traiter' AND ecole_id=?", (e_,), un=True)["n"]
        par_classe = q("""SELECT c.id, c.nom, c.niveau, COUNT(e.id) effectif,
                          SUM(CASE WHEN e.sexe='F' THEN 1 ELSE 0 END) filles
                          FROM classes c LEFT JOIN eleves e ON e.classe_id=c.id AND e.statut='inscrit'
                          WHERE c.ecole_id=? GROUP BY c.id ORDER BY c.nom""", (e_,))
        derniers = q("SELECT p.*, e.nom, e.prenoms " + PA + " ORDER BY p.id DESC LIMIT 8")
        if config.publique() and getattr(H, "stats_publique", None):
            # école publique : fonds reçus (subventions, cantine, frais de dossier CEP), dépenses et solde en caisse
            stats.update(H.stats_publique())
        return render_template("accueil.html", s=stats, par_classe=par_classe, derniers=derniers)

    # ------------------------------------------------------------ classes
    @app.route("/classes")
    @connexion_requise()
    def classes():
        lst = q("""SELECT c.*, COUNT(e.id) effectif FROM classes c
                   LEFT JOIN eleves e ON e.classe_id=c.id AND e.statut='inscrit'
                   WHERE c.ecole_id=? GROUP BY c.id ORDER BY c.nom""", (eco(),))
        return render_template("classes.html", classes=lst)

    @app.route("/classes/nouvelle", methods=["GET", "POST"])
    @app.route("/classes/<int:cid>/modifier", methods=["GET", "POST"])
    @connexion_requise("classes")
    def classe_form(cid=None):
        cl = classe_ou_404(cid) if cid else None
        if request.method == "POST":
            nom = request.form.get("nom", "").strip()
            niveau = request.form.get("niveau", "")
            try:
                frais = int(request.form.get("frais_scolarite", "0").replace(" ", "") or 0)
            except ValueError:
                frais = -1
            if not nom or niveau not in NIVEAUX_MATERNELLE + NIVEAUX_PRIMAIRE + NIVEAUX_SECONDAIRE or frais < 0:
                flash("Vérifiez le nom, le niveau et le montant de la scolarité.", "danger")
            elif q("SELECT 1 FROM classes WHERE nom=? AND id<>? AND ecole_id=?", (nom, cid or 0, eco()), un=True):
                flash("Une classe porte déjà ce nom.", "danger")
            else:
                tit_nom = request.form.get("titulaire_nom", "").strip()[:120]
                tit_titre = request.form.get("titulaire_titre", "Le titulaire")[:40]
                if cl:
                    ex("UPDATE classes SET nom=?, niveau=?, frais_scolarite=?, titulaire_nom=?, titulaire_titre=? WHERE id=?",
                       (nom, niveau, frais, tit_nom, tit_titre, cid))
                    journal("classe_modifiee", nom)
                else:
                    ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id, titulaire_nom, titulaire_titre) "
                       "VALUES (?,?,?,?,?,?)", (nom, niveau, frais, eco(), tit_nom, tit_titre))
                    journal("classe_creee", nom)
                flash("Classe enregistrée.", "success")
                return redirect(url_for("classes"))
        return render_template("classe_form.html", cl=cl, maternelle=NIVEAUX_MATERNELLE, primaire=NIVEAUX_PRIMAIRE,
                               secondaire=NIVEAUX_SECONDAIRE)

    @app.route("/classes/<int:cid>")
    @connexion_requise()
    def classe_detail(cid):
        cl = classe_ou_404(cid)
        eleves = q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (cid,))
        soldes = {e["id"]: situation(e) for e in eleves}
        return render_template("classe_detail.html", cl=cl, eleves=eleves, soldes=soldes)

    @app.route("/classes/<int:cid>/liste-cep.csv")
    @connexion_requise("documents")
    def liste_cep(cid):
        cl = classe_ou_404(cid)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["N°", "Matricule", "Nom", "Prénoms", "Sexe", "Date de naissance", "Lieu de naissance", "Classe", "École"])
        for i, e in enumerate(q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (cid,)), 1):
            w.writerow([i, e["matricule"], e["nom"], e["prenoms"], e["sexe"], pdfs.date_fr(e["date_naissance"]),
                        e["lieu_naissance"], cl["nom"], config.ECOLE["nom"]])
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=liste_CEP_{cl['nom']}.csv"})

    # ------------------------------------------------------------ élèves
    @app.route("/eleves")
    @connexion_requise()
    def eleves():
        rech = request.args.get("q", "").strip()
        cid = request.args.get("classe", type=int)
        statut = request.args.get("statut", "inscrit")
        sql = "SELECT e.*, c.nom classe_nom FROM eleves e JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=?"
        args = [eco()]
        if statut != "tous":
            sql += " AND e.statut=?"
            args.append(statut)
        if rech:
            sql += " AND (e.nom LIKE ? OR e.prenoms LIKE ? OR e.matricule LIKE ? OR e.parent_telephone LIKE ?)"
            args += [f"%{rech}%"] * 4
        if cid:
            sql += " AND e.classe_id=?"
            args.append(cid)
        lst = q(sql + " ORDER BY e.nom, e.prenoms LIMIT 500", args)
        return render_template("eleves.html", eleves=lst, classes=H.classes_autorisees(),
                               rech=rech, cid=cid, statut=statut)

    @app.route("/eleves/export.csv")
    @connexion_requise("eleves")
    def eleves_export():
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Matricule", "Nom", "Prénoms", "Sexe", "Date de naissance", "Lieu", "Classe", "Parent",
                    "Téléphone", "WhatsApp", "Adresse", "Statut", "Inscription"])
        for e in q("SELECT e.*, c.nom cn FROM eleves e JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=? ORDER BY e.nom", (eco(),)):
            w.writerow([e["matricule"], e["nom"], e["prenoms"], e["sexe"], e["date_naissance"], e["lieu_naissance"],
                        e["cn"], e["parent_nom"], e["parent_telephone"], e["parent_whatsapp"], e["adresse"],
                        e["statut"], e["date_inscription"]])
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=eleves.csv"})

    @app.route("/eleves/nouveau", methods=["GET", "POST"])
    @app.route("/eleves/<int:eid>/modifier", methods=["GET", "POST"])
    @connexion_requise("eleves")
    def eleve_form(eid=None):
        e = eleve_ou_404(eid) if eid else None
        cls = q("SELECT * FROM classes WHERE ecole_id=? ORDER BY nom", (eco(),))
        if not cls:
            flash("Créez d'abord au moins une classe.", "warning")
            return redirect(url_for("classe_form"))
        if request.method == "POST":
            f = {k: request.form.get(k, "").strip()[:200] for k in (
                "nom", "prenoms", "sexe", "date_naissance", "lieu_naissance", "classe_id", "parent_nom",
                "parent_telephone", "parent_whatsapp", "adresse", "statut") + CHAMPS_CARTE}
            f["nom"] = f["nom"].upper()
            erreurs = []
            if not f["nom"] or not f["prenoms"]:
                erreurs.append("Nom et prénoms sont obligatoires.")
            if f["sexe"] not in ("M", "F"):
                erreurs.append("Indiquez le sexe.")
            if not q("SELECT 1 FROM classes WHERE id=? AND ecole_id=?", (f["classe_id"] or 0, eco()), un=True):
                erreurs.append("Choisissez une classe.")
            if f["date_naissance"]:
                try:
                    datetime.strptime(f["date_naissance"], "%Y-%m-%d")
                except ValueError:
                    erreurs.append("Date de naissance invalide.")
            if f["statut"] not in ("inscrit", "transfere", "sorti"):
                f["statut"] = "inscrit"
            photo = request.files.get("photo")
            ext = os.path.splitext(photo.filename)[1].lower() if photo and photo.filename else ""
            if ext and ext not in EXT_PHOTO:
                erreurs.append("La photo doit être au format JPG ou PNG.")
            if erreurs:
                for m in erreurs:
                    flash(m, "danger")
                return render_template("eleve_form.html", e=f, cls=cls, edition=bool(eid)), 400
            if f["annees_scolarite"] and not f["annees_scolarite"].isdigit():
                f["annees_scolarite"] = ""
            f["redoublant"] = "1" if request.form.get("redoublant") else "0"
            champs = ("nom", "prenoms", "sexe", "date_naissance", "lieu_naissance", "classe_id", "parent_nom",
                      "parent_telephone", "parent_whatsapp", "adresse", "statut") + CHAMPS_CARTE + ("redoublant",)
            vals = [f[k] or None for k in champs]
            if e:
                ex(f"UPDATE eleves SET {', '.join(k + '=?' for k in champs)} WHERE id=?", vals + [eid])
                journal("eleve_modifie", f"{e['matricule']}")
            else:
                eid = ex(f"INSERT INTO eleves ({', '.join(champs)}, date_inscription, annee) VALUES "
                         f"({', '.join('?' * len(champs))},?,?)", vals + [date.today().isoformat(), config.ANNEE_ACTIVE])
                cyc = {"maternelle": "M", "primaire": "P"}.get(
                    cycle_du_niveau(classe_ou_404(int(f["classe_id"]))["niveau"]), "S")
                mat = f"{config.ECOLE['sigle']}-{config.ANNEE_ACTIVE[:4]}-{cyc}-{eid:04d}"
                ex("UPDATE eleves SET matricule=? WHERE id=?", (mat, eid))
                journal("eleve_inscrit", mat)
            if ext:
                nom_fichier = f"{eid}{ext}"
                photo.save(os.path.join(config.INSTANCE_DIR, "photos", nom_fichier))
                ex("UPDATE eleves SET photo=? WHERE id=?", (nom_fichier, eid))
            else:
                enregistrer_photo_data(eid, request.form.get("photo_data", ""))
            flash("Élève enregistré.", "success")
            return redirect(url_for("eleve_detail", eid=eid))
        return render_template("eleve_form.html", e=e or {"classe_id": request.args.get("classe", type=int)},
                               cls=cls, edition=bool(eid))

    @app.route("/eleves/<int:eid>")
    @connexion_requise()
    def eleve_detail(eid):
        e = eleve_ou_404(eid)
        cl = classe_de(e)
        du, paye, reste = situation(e)
        paiements = q("SELECT * FROM paiements WHERE eleve_id=? ORDER BY id DESC", (eid,))
        docs = q("SELECT * FROM documents WHERE eleve_id=? ORDER BY id DESC LIMIT 30", (eid,))
        moyennes = []
        if cl and e["statut"] == "inscrit":
            for i, per in enumerate(config.PERIODES, 1):
                _, _, _, res, _ = resultats_classe(cl, per)
                r = res.get(eid)
                if r and (r.moyenne is not None or r.details.get("evalues")):
                    moyennes.append((i, per, r))
        return render_template("eleve_detail.html", e=e, cl=cl, du=du, paye=paye, reste=reste,
                               paiements=paiements, docs=docs, moyennes=moyennes, absences=absences_eleve(eid))

    @app.route("/eleves/<int:eid>/photo")
    @connexion_requise()
    def eleve_photo(eid):
        p = chemin_photo(eleve_ou_404(eid))
        if not p:
            abort(404)
        return send_file(p, max_age=0)

    # ------------------------------------------------------------ notes
    @app.route("/notes")
    @connexion_requise("notes")
    def notes_accueil():
        return render_template("notes_accueil.html", classes=H.classes_autorisees())

    @app.route("/notes/<int:cid>/<int:p>", methods=["GET", "POST"])
    @connexion_requise("notes")
    def notes_saisie(cid, p):
        cl, per = classe_ou_404(cid), periode_de(p)
        matieres, eleves, notes, res, stats = resultats_classe(cl, per)
        erreurs = []
        if request.method == "POST":
            db = get_db()
            modifs = 0
            mat = cl["cycle"] == "maternelle"
            for e in eleves:
                obs = request.form.get(f"obs_{e['id']}")
                if obs is not None:
                    obs = obs.strip()[:600]
                    if obs != res[e["id"]].details.get("observation", ""):
                        db.execute("INSERT INTO observations (eleve_id, periode, annee, texte) VALUES (?,?,?,?) "
                                   "ON CONFLICT(eleve_id, periode, annee) DO UPDATE SET texte=excluded.texte",
                                   (e["id"], per, config.ANNEE_ACTIVE, obs))
                        modifs += 1
                for m in matieres:
                    cle = f"n_{e['id']}_{m['id']}"
                    if cle not in request.form:
                        continue
                    if mat:
                        code = request.form[cle].strip().upper()
                        ancien = notes.get((e["id"], m["id"]))
                        disp = code == "D"
                        code = code if code in APPRECIATIONS else None
                        if ancien and ancien["appreciation"] == code and bool(ancien["dispense"]) == disp:
                            continue
                        if not code and not disp:
                            if ancien:
                                db.execute("DELETE FROM notes WHERE id=?", (ancien["id"],))
                                modifs += 1
                            continue
                        db.execute("""INSERT INTO notes (eleve_id, matiere_id, periode, annee, valeur, appreciation, dispense, saisi_par, modifie_le)
                                      VALUES (?,?,?,?,NULL,?,?,?,?)
                                      ON CONFLICT(eleve_id, matiere_id, periode, annee)
                                      DO UPDATE SET appreciation=excluded.appreciation, dispense=excluded.dispense,
                                                    saisi_par=excluded.saisi_par, modifie_le=excluded.modifie_le""",
                                   (e["id"], m["id"], per, config.ANNEE_ACTIVE, code, int(disp), g.user["id"], maintenant()))
                        modifs += 1
                        continue
                    try:
                        val, disp = lire_note(request.form[cle])
                    except ValueError:
                        erreurs.append(f"{e['nom']} {e['prenoms']} – {m['nom']} : « {request.form[cle]} » n'est pas une note valide (0 à 20, ou D).")
                        continue
                    ancien = notes.get((e["id"], m["id"]))
                    if ancien and ancien["valeur"] == val and bool(ancien["dispense"]) == disp:
                        continue
                    if val is None and not disp:
                        if ancien:
                            db.execute("DELETE FROM notes WHERE id=?", (ancien["id"],))
                            modifs += 1
                        continue
                    db.execute("""INSERT INTO notes (eleve_id, matiere_id, periode, annee, valeur, dispense, saisi_par, modifie_le)
                                  VALUES (?,?,?,?,?,?,?,?)
                                  ON CONFLICT(eleve_id, matiere_id, periode, annee)
                                  DO UPDATE SET valeur=excluded.valeur, dispense=excluded.dispense,
                                                saisi_par=excluded.saisi_par, modifie_le=excluded.modifie_le""",
                               (e["id"], m["id"], per, config.ANNEE_ACTIVE, val, int(disp), g.user["id"], maintenant()))
                    modifs += 1
            db.commit()
            journal("notes_saisies", f"{cl['nom']} {per} : {modifs} modification(s)")
            if erreurs:
                for m in erreurs[:10]:
                    flash(m, "danger")
                flash("Les autres notes ont été enregistrées.", "warning")
            else:
                flash(f"Notes enregistrées ({modifs} modification(s)).", "success")
            return redirect(url_for("notes_saisie", cid=cid, p=p))
        return render_template("notes_saisie.html", cl=cl, p=p, per=per, matieres=matieres,
                               eleves=eleves, notes=notes, res=res, stats=stats, APPRECIATIONS=APPRECIATIONS)

    @app.route("/notes/<int:cid>/<int:p>/resultats")
    @connexion_requise()
    def resultats(cid, p):
        cl, per = classe_ou_404(cid), periode_de(p)
        matieres, eleves, notes, res, stats = resultats_classe(cl, per)
        ordre = sorted(eleves, key=lambda e: (res[e["id"]].rang is None, res[e["id"]].rang or 0, e["nom"]))
        publie = q("SELECT * FROM publications WHERE classe_id=? AND periode=? AND annee=?",
                   (cid, per, config.ANNEE_ACTIVE), un=True)
        return render_template("resultats.html", cl=cl, p=p, per=per, eleves=ordre, res=res, stats=stats, publie=publie)

    def _bulletin_data(cl, per, e, r, stats):
        code = enregistrer_document("bulletin", e["id"], f"Bulletin {per} {config.ANNEE_ACTIVE} – {cl['nom']}",
                                    cle=f"{e['id']}|{per}|{config.ANNEE_ACTIVE}")
        return dict(eleve=e, classe=cl, periode=per, annee=config.ANNEE_ACTIVE, resultat=r, stats=stats, code=code,
                    absences=absences_eleve(e["id"]))
    app.bulletin_data = _bulletin_data

    @app.route("/notes/<int:cid>/<int:p>/bulletins.pdf")
    @connexion_requise()
    def bulletins_classe(cid, p):
        if g.user["role"] == "comptable":
            abort(403)
        cl, per = classe_ou_404(cid), periode_de(p)
        _, eleves, _, res, stats = resultats_classe(cl, per)
        if not eleves:
            flash("Aucun élève dans cette classe.", "warning")
            return redirect(url_for("resultats", cid=cid, p=p))
        liste = [_bulletin_data(cl, per, e, res[e["id"]], stats) for e in eleves]
        journal("bulletins_classe", f"{cl['nom']} {per}")
        return pdf_reponse(pdfs.bulletins(liste), f"bulletins_{cl['nom']}_{per}.pdf")

    @app.route("/eleves/<int:eid>/bulletin/<int:p>.pdf")
    @connexion_requise()
    def bulletin_eleve(eid, p):
        if g.user["role"] == "comptable":
            abort(403)
        e = eleve_ou_404(eid)
        cl, per = classe_de(e), periode_de(p)
        if not cl:
            abort(404)
        _, eleves, _, res, stats = resultats_classe(cl, per)
        if eid not in res:
            abort(404)
        return pdf_reponse(pdfs.bulletins([_bulletin_data(cl, per, e, res[eid], stats)]),
                           f"bulletin_{e['matricule']}_{per}.pdf")

    # ------------------------------------------------------------ matières
    @app.route("/matieres", methods=["GET", "POST"])
    @connexion_requise()
    def matieres():
        if request.method == "POST":
            if not peut("parametres"):
                abort(403)
            for m in q("SELECT * FROM matieres"):
                i = m["id"]
                try:
                    coef = float(request.form.get(f"coef_{i}", m["coefficient"]).replace(",", "."))
                    ordre = int(request.form.get(f"ordre_{i}", m["ordre"]))
                except ValueError:
                    flash(f"Valeur invalide pour {m['nom']}.", "danger")
                    continue
                mode = request.form.get(f"mode_{i}", m["mode_calcul"])
                mode = mode if mode in MODES_CALCUL else "standard"
                nom = request.form.get(f"nom_{i}", m["nom"]).strip() or m["nom"]
                actif = 1 if request.form.get(f"actif_{i}") else 0
                if coef <= 0:
                    coef = m["coefficient"]
                ex("UPDATE matieres SET nom=?, coefficient=?, mode_calcul=?, ordre=?, actif=? WHERE id=?",
                   (nom, coef, mode, ordre, actif, i))
            code = request.form.get("new_code", "").strip().upper()
            nom = request.form.get("new_nom", "").strip()
            cyc = request.form.get("new_cycle")
            if code and nom and cyc in ("maternelle", "primaire", "secondaire"):
                try:
                    coef = float(request.form.get("new_coef", "1").replace(",", ".") or 1)
                    ex("INSERT INTO matieres (code, nom, cycle, coefficient, mode_calcul, ordre) VALUES (?,?,?,?,?,?)",
                       (code, nom, cyc, coef, request.form.get("new_mode", "standard"), 99))
                except Exception:
                    flash("Impossible d'ajouter la matière (code déjà utilisé ?).", "danger")
            journal("matieres_modifiees")
            flash("Référentiel des matières enregistré.", "success")
            return redirect(url_for("matieres"))
        return render_template("matieres.html",
                               mat=q("SELECT * FROM matieres WHERE cycle='maternelle' ORDER BY ordre"),
                               prim=q("SELECT * FROM matieres WHERE cycle='primaire' ORDER BY ordre"),
                               sec=q("SELECT * FROM matieres WHERE cycle='secondaire' ORDER BY ordre"),
                               modes=MODES_CALCUL)

    # ------------------------------------------------------------ paiements
    @app.route("/paiements")
    @connexion_requise("paiements")
    def paiements():
        d1 = request.args.get("du", "")
        d2 = request.args.get("au", "")
        mode = request.args.get("mode", "")
        sql = """SELECT p.*, e.nom, e.prenoms, e.matricule, c.nom classe_nom FROM paiements p
                 JOIN eleves e ON e.id=p.eleve_id JOIN classes c ON c.id=e.classe_id WHERE p.annee=? AND c.ecole_id=?"""
        args = [config.ANNEE_ACTIVE, eco()]
        if d1:
            sql += " AND date(p.date_paiement)>=?"
            args.append(d1)
        if d2:
            sql += " AND date(p.date_paiement)<=?"
            args.append(d2)
        if mode in config.MODES_PAIEMENT:
            sql += " AND p.mode=?"
            args.append(mode)
        lst = q(sql + " ORDER BY p.id DESC LIMIT 1000", args)
        total = sum(p["montant"] for p in lst if not p["annule"])
        par_mode = {}
        for p in lst:
            if not p["annule"]:
                par_mode[p["mode"]] = par_mode.get(p["mode"], 0) + p["montant"]
        return render_template("paiements.html", paiements=lst, total=total, par_mode=par_mode, d1=d1, d2=d2, mode=mode)

    @app.route("/paiements/impayes")
    @connexion_requise("paiements")
    def impayes():
        lst = []
        for e in q("SELECT e.*, c.nom classe_nom FROM eleves e JOIN classes c ON c.id=e.classe_id "
                   "WHERE e.statut='inscrit' AND c.ecole_id=? ORDER BY c.nom, e.nom", (eco(),)):
            du, paye, reste = situation(e)
            if reste > 0:
                lst.append((e, du, paye, reste))
        return render_template("impayes.html", lst=lst, total=sum(x[3] for x in lst))

    @app.route("/paiements/nouveau", methods=["GET", "POST"])
    @connexion_requise("paiements")
    def paiement_nouveau():
        eid = request.values.get("eleve_id", type=int)
        e = eleve_ou_404(eid) if eid else None
        if request.method == "POST" and e:
            du, paye, reste = situation(e)
            mode = request.form.get("mode", "")
            ref = request.form.get("reference", "").strip()
            tel = request.form.get("telephone", "").strip()
            motif = request.form.get("motif", "").strip() or "Frais de scolarité"
            try:
                montant = int(request.form.get("montant", "0").replace(" ", ""))
            except ValueError:
                montant = 0
            erreur = None
            if montant <= 0:
                erreur = "Montant invalide."
            elif montant > reste:
                erreur = f"Le montant dépasse le reste à payer ({fcfa(reste)})."
            elif mode not in config.MODES_PAIEMENT or mode in ("fedapay", "kkiapay"):
                erreur = "Choisissez un mode de paiement."
            elif mode in config.MODES_MOBILE and not ref:
                erreur = "La référence de la transaction Mobile Money est obligatoire."
            elif ref and q("SELECT 1 FROM paiements WHERE reference=? AND mode=? AND annule=0", (ref, mode), un=True):
                erreur = "Cette référence de transaction a déjà été enregistrée."
            if erreur:
                flash(erreur, "danger")
            else:
                pid = ex("INSERT INTO paiements (eleve_id, annee, montant, mode, reference, telephone, motif, date_paiement, saisi_par) "
                         "VALUES (?,?,?,?,?,?,?,?,?)",
                         (eid, config.ANNEE_ACTIVE, montant, mode, ref or None, tel or None, motif, maintenant(), g.user["id"]))
                num = f"REC-{config.ANNEE_ACTIVE[:4]}-{pid:05d}"
                ex("UPDATE paiements SET numero_recu=? WHERE id=?", (num, pid))
                journal("paiement", f"{num} {e['matricule']} {montant}")
                try:
                    import notif
                    notif.notifier_eleve(e, "paiement", "Paiement reçu",
                                         f"Nous avons reçu {fcfa(montant)} pour {e['prenoms']} {e['nom']} (reçu {num}). "
                                         f"Reste à payer : {fcfa(reste - montant)}.")
                except Exception:  # noqa: BLE001 — un message non envoyé ne bloque pas l'encaissement
                    pass
                flash(f"Paiement enregistré – reçu {num}.", "success")
                return redirect(url_for("eleve_detail", eid=eid, recu=pid))
        situ = situation(e) if e else None
        rech = request.args.get("q", "").strip()
        trouves = []
        if rech and not e:
            trouves = q("SELECT e.*, c.nom classe_nom FROM eleves e JOIN classes c ON c.id=e.classe_id "
                        "WHERE e.statut='inscrit' AND c.ecole_id=? AND (e.nom LIKE ? OR e.prenoms LIKE ? OR e.matricule LIKE ?) "
                        "ORDER BY e.nom LIMIT 30", [eco()] + [f"%{rech}%"] * 3)
        return render_template("paiement_form.html", e=e, cl=classe_de(e) if e else None, situ=situ,
                               rech=rech, trouves=trouves)

    @app.route("/paiements/<int:pid>/recu.pdf")
    @connexion_requise()
    def recu(pid):
        p = q("SELECT * FROM paiements WHERE id=?", (pid,), un=True)
        if not p:
            abort(404)
        e = eleve_ou_404(p["eleve_id"])
        cl = classe_de(e)
        du = cl["frais_scolarite"] if cl else 0
        paye = q("SELECT COALESCE(SUM(montant),0) s FROM paiements WHERE eleve_id=? AND annee=? AND annule=0 AND id<=?",
                 (e["id"], p["annee"], pid), un=True)["s"]
        caissier = q("SELECT nom FROM utilisateurs WHERE id=?", (p["saisi_par"],), un=True)
        code = enregistrer_document("recu", e["id"], f"Reçu {p['numero_recu']} – {fcfa(p['montant'])}", cle=p["numero_recu"])
        return pdf_reponse(pdfs.recu(p, e, cl, paye, du, caissier["nom"] if caissier else "", code,
                                     config.MODES_PAIEMENT.get(p["mode"], p["mode"])), f"{p['numero_recu']}.pdf")

    @app.route("/paiements/<int:pid>/annuler", methods=["POST"])
    @connexion_requise("paiements")
    def paiement_annuler(pid):
        if g.user["role"] not in ("admin", "directeur"):
            abort(403)
        p = q("SELECT * FROM paiements WHERE id=?", (pid,), un=True)
        if not p or p["annule"]:
            abort(404)
        motif = request.form.get("motif", "").strip()
        if not motif:
            flash("Indiquez le motif de l'annulation.", "danger")
        else:
            ex("UPDATE paiements SET annule=1, motif_annulation=? WHERE id=?", (motif, pid))
            journal("paiement_annule", f"{p['numero_recu']} : {motif}")
            flash(f"Reçu {p['numero_recu']} annulé.", "success")
        return redirect(url_for("eleve_detail", eid=p["eleve_id"]))

    # ------------------------------------------------------------ documents officiels
    @app.route("/eleves/<int:eid>/document/<type_doc>.pdf")
    @connexion_requise("documents")
    def document(eid, type_doc):
        if type_doc not in ("carte", "certificat_frequentation", "attestation_inscription", "certificat_transfert", "fiche_cep"):
            abort(404)
        e = eleve_ou_404(eid)
        cl = classe_de(e)
        a = config.ANNEE_ACTIVE
        if type_doc in ("certificat_frequentation", "carte", "attestation_inscription") and e["statut"] != "inscrit":
            flash("Ce document n'est délivré qu'aux élèves inscrits.", "danger")
            return redirect(url_for("eleve_detail", eid=eid))
        if type_doc == "fiche_cep" and (not cl or cl["niveau"] != "CM2"):
            flash("La fiche CEP concerne uniquement les élèves de CM2.", "danger")
            return redirect(url_for("eleve_detail", eid=eid))
        libelle = f"{TYPES_DOCS[type_doc]} – {e['nom']} {e['prenoms']} ({a})"
        cle = f"{eid}|{a}" if type_doc in ("carte", "fiche_cep") else None
        code = enregistrer_document(type_doc, eid, libelle, cle=cle)
        journal("document", f"{type_doc} {e['matricule']} {code}")
        if type_doc == "carte":
            contenu = pdfs.carte(e, cl, a, code, chemin_photo(e))
        elif type_doc == "fiche_cep":
            contenu = pdfs.fiche_cep(e, cl, a, code, chemin_photo(e))
        else:
            reste = situation(e)[2] if type_doc == "certificat_transfert" else None
            contenu = pdfs.certificat(type_doc, e, cl, a, code, situation_financiere=reste,
                                      destination=request.args.get("destination", "").strip())
        return pdf_reponse(contenu, f"{type_doc}_{e['matricule']}.pdf")

    @app.route("/verifier", methods=["GET", "POST"])
    @app.route("/verifier/<code>")
    def verifier(code=None):
        code = (code or request.values.get("code", "")).strip().upper()
        doc = eleve = None
        if code:
            doc = q("SELECT * FROM documents WHERE code=?", (code,), un=True)
            if doc and doc["eleve_id"]:
                eleve = q("SELECT e.nom, e.prenoms, e.matricule, c.nom classe_nom FROM eleves e "
                          "LEFT JOIN classes c ON c.id=e.classe_id WHERE e.id=?", (doc["eleve_id"],), un=True)
            if doc and doc["type"] == "recu":
                p = q("SELECT annule FROM paiements WHERE numero_recu=?", (doc["cle"],), un=True)
                if p and p["annule"]:
                    doc = dict(doc)
                    doc["annule"] = True
        return render_template("verifier.html", code=code, doc=doc, eleve=eleve)

    # ------------------------------------------------------------ utilisateurs & journal
    @app.route("/utilisateurs", methods=["GET", "POST"])
    @connexion_requise("parametres")
    def utilisateurs():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "creer":
                ident = request.form.get("identifiant", "").strip().lower()
                nom = request.form.get("nom", "").strip()
                role = request.form.get("role")
                mdp = request.form.get("mdp", "")
                if not ident or not nom or role not in ROLES or len(mdp) < 8:
                    flash("Tous les champs sont obligatoires (mot de passe : 8 caractères minimum).", "danger")
                elif q("SELECT 1 FROM utilisateurs WHERE identifiant=?", (ident,), un=True):
                    flash("Cet identifiant existe déjà.", "danger")
                else:
                    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp) VALUES (?,?,?,?,1)",
                       (ident, nom, role, generate_password_hash(mdp)))
                    journal("utilisateur_cree", f"{ident} ({role})")
                    flash(f"Compte {ident} créé. Mot de passe à changer à la première connexion.", "success")
            else:
                uid = request.form.get("uid", type=int)
                u = q("SELECT * FROM utilisateurs WHERE id=?", (uid,), un=True)
                if not u:
                    abort(404)
                if action == "basculer" and uid != g.user["id"]:
                    ex("UPDATE utilisateurs SET actif=1-actif WHERE id=?", (uid,))
                    journal("utilisateur_actif", u["identifiant"])
                elif action == "reinit":
                    nouveau = secrets.token_urlsafe(6)
                    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=1 WHERE id=?",
                       (generate_password_hash(nouveau), uid))
                    journal("utilisateur_reinit", u["identifiant"])
                    flash(f"Mot de passe provisoire de {u['identifiant']} : {nouveau}", "info")
            return redirect(url_for("utilisateurs"))
        return render_template("utilisateurs.html", users=q("SELECT * FROM utilisateurs ORDER BY nom"))

    @app.route("/journal")
    @connexion_requise("parametres")
    def journal_page():
        lst = q("SELECT j.*, u.identifiant FROM journal j LEFT JOIN utilisateurs u ON u.id=j.user_id "
                "ORDER BY j.id DESC LIMIT 500")
        return render_template("journal.html", lst=lst)

    # ------------------------------------------------------------ écoles candidates (public)
    listes_form = dict(departements=DEPARTEMENTS, ordres=ORDRES, statuts_etab=STATUTS_ETAB, fonctions=FONCTIONS,
                       modules=MODULES, demarrages=DEMARRAGES, outils=OUTILS)

    @app.route("/rejoindre", methods=["GET", "POST"])
    def rejoindre():
        """Formulaire public : aucune connexion requise."""
        if request.method == "GET":
            return render_template("rejoindre.html", f={"modules": MODULES[:2]}, erreurs=[], ok=None, **listes_form)
        f = {k: request.form.get(k, "").strip()[:200] for k in (
            "ecole", "type", "statut_etab", "departement", "commune", "effectif", "enseignants", "contact",
            "fonction", "telephone", "whatsapp", "email", "demarrage", "outil")}
        f["message"] = request.form.get("message", "").strip()[:1500]
        f["modules"] = [m for m in request.form.getlist("modules") if m in MODULES]
        if request.form.get("site_web"):  # champ piège invisible : rempli uniquement par les robots
            return render_template("rejoindre.html", f={}, erreurs=[], ok=f["ecole"] or "votre école", **listes_form)
        erreurs = []
        if not f["ecole"]: erreurs.append("le nom de l'établissement")
        if f["type"] not in ORDRES: erreurs.append("l'ordre d'enseignement")
        if f["departement"] not in DEPARTEMENTS: erreurs.append("le département")
        if not f["commune"]: erreurs.append("la commune")
        if not f["contact"]: erreurs.append("le nom de la personne à contacter")
        chiffres = "".join(ch for ch in f["telephone"] if ch.isdigit())
        if len(chiffres) < 8: erreurs.append("un numéro de téléphone valide")
        if f["email"] and ("@" not in f["email"] or "." not in f["email"].split("@")[-1]): erreurs.append("une adresse e-mail valide")
        if not request.form.get("accord"): erreurs.append("votre accord pour être recontacté")
        for k in ("effectif", "enseignants"):
            f[k] = int(f[k]) if f[k].isdigit() else None
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        recent = [t for t in _envois_ip.get(ip, []) if (datetime.now() - t).total_seconds() < 3600]
        if len(recent) >= 5:
            erreurs.append("moins de demandes à la suite (limite atteinte, réessayez dans une heure)")
        if erreurs:
            return render_template("rejoindre.html", f=f, erreurs=erreurs, ok=None, **listes_form), 400
        _envois_ip[ip] = recent + [datetime.now()]
        ex("""INSERT INTO demandes_ecoles (ecole, type, statut_etab, departement, commune, effectif, enseignants, contact,
              fonction, telephone, whatsapp, email, modules, demarrage, outil, message, ip, cree_le)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
           (f["ecole"], f["type"], f["statut_etab"] or None, f["departement"], f["commune"], f["effectif"],
            f["enseignants"], f["contact"], f["fonction"] or None, f["telephone"], f["whatsapp"] or None,
            f["email"] or None, " / ".join(f["modules"]), f["demarrage"] or None, f["outil"] or None,
            f["message"] or None, ip, maintenant()))
        return render_template("rejoindre.html", f={"modules": MODULES[:2]}, erreurs=[], ok=f["ecole"],
                               telephone=f["telephone"], **listes_form)

    @app.route("/demandes-ecoles", methods=["GET", "POST"])
    @connexion_requise("parametres")
    def demandes_ecoles():
        if request.method == "POST":
            did = request.form.get("id", type=int)
            suivi = request.form.get("suivi")
            if suivi in SUIVIS:
                ex("UPDATE demandes_ecoles SET suivi=?, note_interne=? WHERE id=?",
                   (suivi, request.form.get("note_interne", "").strip()[:500] or None, did))
                journal("demande_ecole_suivi", f"#{did} → {suivi}")
                flash("Suivi enregistré.", "success")
            return redirect(url_for("demandes_ecoles", suivi=request.args.get("suivi", "")))
        filtre = request.args.get("suivi", "")
        sql, args = "SELECT * FROM demandes_ecoles", []
        if filtre in SUIVIS:
            sql += " WHERE suivi=?"
            args.append(filtre)
        lst = q(sql + " ORDER BY id DESC", args)
        compte = {k: q("SELECT COUNT(*) n FROM demandes_ecoles WHERE suivi=?", (k,), un=True)["n"] for k in SUIVIS}
        eleves_total = q("SELECT COALESCE(SUM(effectif),0) s FROM demandes_ecoles", un=True)["s"]
        return render_template("demandes_ecoles.html", lst=lst, compte=compte, filtre=filtre, suivis=SUIVIS,
                               total=sum(compte.values()), eleves_total=eleves_total)

    @app.route("/demandes-ecoles.csv")
    @connexion_requise("parametres")
    def demandes_ecoles_csv():
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        cols = ["cree_le", "ecole", "type", "statut_etab", "departement", "commune", "effectif", "enseignants", "contact",
                "fonction", "telephone", "whatsapp", "email", "modules", "demarrage", "outil", "message", "suivi", "note_interne"]
        w.writerow(["Date", "Établissement", "Ordre", "Statut", "Département", "Commune", "Élèves", "Enseignants", "Contact",
                    "Fonction", "Téléphone", "WhatsApp", "E-mail", "Modules", "Démarrage", "Outil actuel", "Message", "Suivi", "Note interne"])
        for d in q("SELECT * FROM demandes_ecoles ORDER BY id DESC"):
            w.writerow([SUIVIS.get(d[c], d[c]) if c == "suivi" else (d[c] if d[c] is not None else "") for c in cols])
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=ecoles_inscrites.csv"})

    # ------------------------------------------------------------ paramètres de l'établissement
    @app.route("/parametres", methods=["GET", "POST"])
    @connexion_requise("parametres")
    def parametres():
        vals = lire_parametres()
        if request.method == "POST":
            nouv = {k: request.form.get(k, "").strip()[:200] for k, _, _ in CHAMPS_PARAM}
            manquants = [lib for k, lib, obl in CHAMPS_PARAM if obl and not nouv[k]]
            annee = request.form.get("annee_active", "").strip()
            ok_annee = (len(annee) == 9 and annee[4] == "-" and annee[:4].isdigit() and annee[5:].isdigit()
                        and int(annee[5:]) == int(annee[:4]) + 1)
            url = request.form.get("url_publique", "").strip().rstrip("/")
            if manquants:
                flash("Champs obligatoires : " + ", ".join(manquants) + ".", "danger")
            elif not ok_annee:
                flash("L'année scolaire doit être au format 2026-2027.", "danger")
            elif url and not url.startswith(("http://", "https://")):
                flash("L'adresse publique doit commencer par http:// ou https://", "danger")
            else:
                per = request.form.get("periodes")
                nouv.update(annee_active=annee, url_publique=url,
                            periodes=per if per in PERIODES_TYPES else "trimestres")
                if config.EDITION_IMPOSEE not in config.EDITIONS:
                    ed = request.form.get("edition")
                    nouv["edition"] = ed if ed in config.EDITIONS else "privee"
                db = get_db()
                for k, v in nouv.items():
                    db.execute("INSERT INTO parametres (cle, valeur) VALUES (?,?) "
                               "ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", (k, v))
                db.commit()
                for nom in IMAGES_ECOLE:
                    fichier = request.files.get(nom)
                    chemin = os.path.join(config.ECOLE_DIR, nom + ".png")
                    if request.form.get("supprimer_" + nom):
                        if os.path.exists(chemin):
                            os.remove(chemin)
                    elif fichier and fichier.filename:
                        try:
                            from PIL import Image
                            img = Image.open(fichier.stream)
                            img.thumbnail((800, 800))
                            if img.mode not in ("RGB", "RGBA"):
                                img = img.convert("RGBA")
                            img.save(chemin, "PNG")
                        except Exception:
                            flash(f"{IMAGES_ECOLE[nom]} : image illisible (utilisez un fichier PNG ou JPG).", "danger")
                if getattr(app, "apres_parametres", None):
                    app.apres_parametres(nouv)
                journal("parametres_modifies")
                appliquer_parametres()
                flash("Paramètres enregistrés.", "success")
                return redirect(url_for("parametres"))
            vals.update(request.form.to_dict())
        else:
            for k in ("nom", "sigle", "adresse", "telephone", "email", "directeur", "ville"):
                if config.ECOLE.get(k):
                    vals["ecole_" + k] = config.ECOLE[k]
        images = {n: os.path.exists(os.path.join(config.ECOLE_DIR, n + ".png")) for n in IMAGES_ECOLE}
        return render_template("parametres.html", v=vals, champs=CHAMPS_PARAM, images=images,
                               images_lib=IMAGES_ECOLE, dossier=config.INSTANCE_DIR, periodes_types=PERIODES_TYPES)

    @app.route("/parametres/image/<nom>.png")
    @connexion_requise("parametres")
    def image_ecole(nom):
        chemin = os.path.join(config.ECOLE_DIR, nom + ".png")
        if nom not in IMAGES_ECOLE or not os.path.exists(chemin):
            abort(404)
        return send_file(chemin, max_age=0)

    @app.route("/sauvegarde")
    @connexion_requise("parametres")
    def sauvegarde():
        """Archive ZIP : base de données (copie cohérente), photos, logo/cachet/signature."""
        import sqlite3
        import tempfile
        import zipfile
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        buf = io.BytesIO()
        try:
            dest = sqlite3.connect(tmp)
            get_db().backup(dest)
            dest.close()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(tmp, "gescol.db")
                for sous in ("photos", "ecole", "archives"):
                    dossier = os.path.join(config.INSTANCE_DIR, sous)
                    if os.path.isdir(dossier):
                        for nom in os.listdir(dossier):
                            z.write(os.path.join(dossier, nom), f"{sous}/{nom}")
                z.writestr("LISEZ-MOI.txt",
                           f"Sauvegarde GESCOL du {maintenant()}.\r\n"
                           "Pour restaurer : arretez GESCOL, copiez ces fichiers dans le dossier de donnees\r\n"
                           f"{config.INSTANCE_DIR}\r\n(en remplacant les fichiers existants), puis relancez GESCOL.\r\n")
        finally:
            os.remove(tmp)
        journal("sauvegarde")
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True,
                         download_name=f"sauvegarde_gescol_{date.today().isoformat()}.zip")

    # ------------------------------------------------------------ application installable (PWA)
    @app.route("/manifest.webmanifest")
    def manifeste():
        import json
        m = {
            "name": f"GESCOL – {config.ECOLE['nom']}", "short_name": "GESCOL",
            "description": "Gestion d'établissement scolaire : élèves, notes, bulletins, paiements.",
            "lang": "fr", "id": "/", "start_url": "/?source=app", "scope": "/", "display": "standalone",
            "orientation": "any", "background_color": "#F4F6F9", "theme_color": "#1F4E79",
            "icons": [
                {"src": url_for("static", filename="icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
                {"src": url_for("static", filename="icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
                {"src": url_for("static", filename="icons/maskable-512.png"), "sizes": "512x512",
                 "type": "image/png", "purpose": "maskable"},
            ],
        }
        return Response(json.dumps(m, ensure_ascii=False), mimetype="application/manifest+json")

    @app.route("/sw.js")
    def service_worker():
        r = send_file(os.path.join(config.WEB_DIR, "static", "sw.js"), mimetype="application/javascript", max_age=0)
        r.headers["Service-Worker-Allowed"] = "/"
        r.headers["Cache-Control"] = "no-cache"
        return r

    @app.route("/hors-ligne")
    def hors_ligne():
        return render_template("hors_ligne.html")

    @app.route("/installer")
    def installer():
        return render_template("installer.html")

    # ------------------------------------------------------------ modules complémentaires
    import types
    H = types.SimpleNamespace(
        q=q, ex=ex, get_db=get_db, config=config, pdfs=pdfs, journal=journal, peut=peut,
        connexion_requise=connexion_requise, maintenant=maintenant, fcfa=fcfa, eleve_ou_404=eleve_ou_404,
        classe_ou_404=classe_ou_404, classe_de=classe_de, situation=situation, pdf_reponse=pdf_reponse,
        enregistrer_document=enregistrer_document, absences_eleve=absences_eleve, bornes_annee=bornes_annee,
        resultats_classe=resultats_classe, periode_de=periode_de, lire_parametres=lire_parametres,
        chemin_photo=chemin_photo, ROLES=ROLES, DROITS=DROITS, enregistrer_photo_data=enregistrer_photo_data,
        CHAMPS_CARTE=CHAMPS_CARTE, fcfa_txt=fcfa)
    import importlib
    import notif

    def schema(sql):
        """Tables propres à un module (CREATE TABLE IF NOT EXISTS …), créées au démarrage."""
        with app.app_context():
            db = get_db()
            db.executescript(sql)
            db.commit()

    def ajouter_colonne(table, col, typ):
        with app.app_context():
            db = get_db()
            if col not in {r[1] for r in db.execute(f"PRAGMA table_info({table})")}:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                db.commit()

    H.schema = schema
    H.ajouter_colonne = ajouter_colonne
    H.eco = eco
    notif.configurer(H)
    H.notif = notif
    # m_ecoles en premier : il fixe l'école courante avant les autres modules
    for nom in MODULES:
        try:
            module = importlib.import_module(nom)
        except ModuleNotFoundError as e:
            if e.name != nom:
                raise
            continue  # module absent de cette installation
        module.enregistrer(app, H)

    return app


app = create_app()


def servir(host="0.0.0.0", port=5000):
    """Serveur de production (waitress) si disponible, sinon serveur Flask intégré."""
    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  GESCOL démarré : http://localhost:{port}\n  (Ctrl+C pour arrêter)\n")
    if "--debug" in sys.argv:
        app.run(host="0.0.0.0", port=port, debug=True)
    else:
        servir(port=port)
