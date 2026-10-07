# -*- coding: utf-8 -*-
"""Base de données SQLite (bibliothèque standard, aucune installation requise)."""
import os
import sqlite3
from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY,
    identifiant TEXT UNIQUE NOT NULL,
    nom TEXT NOT NULL,
    role TEXT NOT NULL,
    mdp_hash TEXT NOT NULL,
    actif INTEGER NOT NULL DEFAULT 1,
    doit_changer_mdp INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,                              -- unique par école (v1.3), vérifié par l'application
    niveau TEXT NOT NULL,
    frais_scolarite INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS eleves (
    id INTEGER PRIMARY KEY,
    matricule TEXT UNIQUE,
    nom TEXT NOT NULL,
    prenoms TEXT NOT NULL,
    sexe TEXT NOT NULL,
    date_naissance TEXT,
    lieu_naissance TEXT,
    classe_id INTEGER REFERENCES classes(id),
    parent_nom TEXT,
    parent_telephone TEXT,
    parent_whatsapp TEXT,
    adresse TEXT,
    statut TEXT NOT NULL DEFAULT 'inscrit',     -- inscrit | transfere | sorti
    date_inscription TEXT NOT NULL,
    annee TEXT NOT NULL,
    photo TEXT
);

CREATE TABLE IF NOT EXISTS matieres (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    nom TEXT NOT NULL,
    cycle TEXT NOT NULL,
    coefficient REAL NOT NULL DEFAULT 1,
    mode_calcul TEXT NOT NULL DEFAULT 'standard',
    ordre INTEGER NOT NULL DEFAULT 0,
    actif INTEGER NOT NULL DEFAULT 1,
    UNIQUE(code, cycle)
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    eleve_id INTEGER NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
    matiere_id INTEGER NOT NULL REFERENCES matieres(id),
    periode TEXT NOT NULL,
    annee TEXT NOT NULL,
    valeur REAL,
    dispense INTEGER NOT NULL DEFAULT 0,
    saisi_par INTEGER,
    modifie_le TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(eleve_id, matiere_id, periode, annee)
);

CREATE TABLE IF NOT EXISTS paiements (
    id INTEGER PRIMARY KEY,
    numero_recu TEXT UNIQUE,
    eleve_id INTEGER NOT NULL REFERENCES eleves(id),
    annee TEXT NOT NULL,
    montant INTEGER NOT NULL,
    mode TEXT NOT NULL,
    reference TEXT,
    telephone TEXT,
    motif TEXT,
    date_paiement TEXT NOT NULL,
    saisi_par INTEGER,
    annule INTEGER NOT NULL DEFAULT 0,
    motif_annulation TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    cle TEXT,
    eleve_id INTEGER REFERENCES eleves(id),
    libelle TEXT,
    empreinte TEXT NOT NULL,
    cree_le TEXT NOT NULL,
    cree_par INTEGER
);
CREATE INDEX IF NOT EXISTS idx_doc_cle ON documents(type, cle);

CREATE TABLE IF NOT EXISTS demandes_ecoles (
    id INTEGER PRIMARY KEY,
    ecole TEXT NOT NULL,
    type TEXT NOT NULL,
    statut_etab TEXT,
    departement TEXT NOT NULL,
    commune TEXT NOT NULL,
    effectif INTEGER,
    enseignants INTEGER,
    contact TEXT NOT NULL,
    fonction TEXT,
    telephone TEXT NOT NULL,
    whatsapp TEXT,
    email TEXT,
    modules TEXT,
    demarrage TEXT,
    outil TEXT,
    message TEXT,
    suivi TEXT NOT NULL DEFAULT 'nouvelle',
    note_interne TEXT,
    ip TEXT,
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parametres (
    cle TEXT PRIMARY KEY,
    valeur TEXT
);

-- ---------------------------------------------------------------- v1.2
CREATE TABLE IF NOT EXISTS observations (
    eleve_id INTEGER NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
    periode TEXT NOT NULL,
    annee TEXT NOT NULL,
    texte TEXT,
    PRIMARY KEY (eleve_id, periode, annee)
);

CREATE TABLE IF NOT EXISTS publications (          -- bulletins visibles par les parents
    classe_id INTEGER NOT NULL,
    periode TEXT NOT NULL,
    annee TEXT NOT NULL,
    publie_le TEXT NOT NULL,
    publie_par INTEGER,
    PRIMARY KEY (classe_id, periode, annee)
);

CREATE TABLE IF NOT EXISTS parents (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    telephone TEXT UNIQUE NOT NULL,                 -- chiffres seuls, format 229XXXXXXXXXX
    whatsapp TEXT,
    email TEXT,
    mdp_hash TEXT NOT NULL,
    doit_changer_mdp INTEGER NOT NULL DEFAULT 1,
    actif INTEGER NOT NULL DEFAULT 1,
    dernier_acces TEXT,
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES parents(id),
    eleve_id INTEGER,
    sens TEXT NOT NULL DEFAULT 'ecole',             -- ecole -> parent | parent -> ecole
    sujet TEXT NOT NULL,
    texte TEXT NOT NULL,
    lu INTEGER NOT NULL DEFAULT 0,
    auteur_id INTEGER,
    cree_le TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_id, sens, lu);

CREATE TABLE IF NOT EXISTS notifications (          -- SMS et WhatsApp
    id INTEGER PRIMARY KEY,
    parent_id INTEGER,
    eleve_id INTEGER,
    telephone TEXT NOT NULL,
    canal TEXT NOT NULL,                            -- sms | whatsapp
    evenement TEXT,
    texte TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'a_envoyer',       -- a_envoyer | envoye | echec
    erreur TEXT,
    cree_le TEXT NOT NULL,
    envoye_le TEXT
);

CREATE TABLE IF NOT EXISTS paiements_en_ligne (
    id INTEGER PRIMARY KEY,
    reference TEXT UNIQUE NOT NULL,
    eleve_id INTEGER NOT NULL,
    parent_id INTEGER,
    montant INTEGER NOT NULL,
    fournisseur TEXT NOT NULL,                      -- fedapay | kkiapay
    transaction_id TEXT,
    statut TEXT NOT NULL DEFAULT 'en_attente',      -- en_attente | approuve | echoue
    paiement_id INTEGER,
    telephone TEXT,
    details TEXT,
    cree_le TEXT NOT NULL,
    maj_le TEXT
);

CREATE TABLE IF NOT EXISTS presences (
    id INTEGER PRIMARY KEY,
    eleve_id INTEGER NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    statut TEXT NOT NULL,                           -- absent | retard
    motif TEXT,
    justifie INTEGER NOT NULL DEFAULT 0,
    saisi_par INTEGER,
    cree_le TEXT,
    UNIQUE(eleve_id, date)
);
CREATE TABLE IF NOT EXISTS appels (                 -- appel fait pour une classe et une date
    classe_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    fait_par INTEGER,
    fait_le TEXT,
    PRIMARY KEY (classe_id, date)
);

CREATE TABLE IF NOT EXISTS personnel (
    id INTEGER PRIMARY KEY,
    matricule TEXT UNIQUE,
    nom TEXT NOT NULL,
    prenoms TEXT NOT NULL,
    sexe TEXT,
    fonction TEXT NOT NULL,
    telephone TEXT,
    email TEXT,
    type_contrat TEXT NOT NULL DEFAULT 'CDI',       -- CDI | CDD | Vacataire | Stagiaire
    date_embauche TEXT,
    salaire_base INTEGER NOT NULL DEFAULT 0,
    taux_horaire INTEGER NOT NULL DEFAULT 0,
    assujetti_cnss INTEGER NOT NULL DEFAULT 1,
    assujetti_its INTEGER NOT NULL DEFAULT 1,
    numero_cnss TEXT,
    numero_paiement TEXT,                           -- n° Mobile Money pour le virement du salaire
    actif INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bulletins_paie (
    id INTEGER PRIMARY KEY,
    personnel_id INTEGER NOT NULL REFERENCES personnel(id),
    mois TEXT NOT NULL,                             -- AAAA-MM
    heures REAL NOT NULL DEFAULT 0,
    salaire_base INTEGER NOT NULL DEFAULT 0,
    primes INTEGER NOT NULL DEFAULT 0,
    retenues INTEGER NOT NULL DEFAULT 0,
    avances INTEGER NOT NULL DEFAULT 0,
    brut INTEGER NOT NULL DEFAULT 0,
    cnss_salarie INTEGER NOT NULL DEFAULT 0,
    its INTEGER NOT NULL DEFAULT 0,
    net INTEGER NOT NULL DEFAULT 0,
    cnss_patronal INTEGER NOT NULL DEFAULT 0,
    vps INTEGER NOT NULL DEFAULT 0,
    statut TEXT NOT NULL DEFAULT 'brouillon',       -- brouillon | valide | paye
    valide_par INTEGER,
    paye_le TEXT,
    mode_paiement TEXT,
    UNIQUE(personnel_id, mois)
);

CREATE TABLE IF NOT EXISTS tresorerie (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    type TEXT NOT NULL,                             -- entree | sortie
    categorie TEXT NOT NULL,
    libelle TEXT NOT NULL,
    montant INTEGER NOT NULL,
    mode TEXT,
    reference TEXT,
    source TEXT NOT NULL DEFAULT 'manuel',          -- manuel | paie
    source_id INTEGER,
    saisi_par INTEGER,
    annule INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT
);

CREATE TABLE IF NOT EXISTS budget (
    annee TEXT NOT NULL,
    type TEXT NOT NULL,
    categorie TEXT NOT NULL,
    montant INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (annee, type, categorie)
);

CREATE TABLE IF NOT EXISTS courriers (
    id INTEGER PRIMARY KEY,
    numero TEXT UNIQUE,
    sens TEXT NOT NULL,                             -- arrivee | depart
    date TEXT NOT NULL,
    correspondant TEXT NOT NULL,
    objet TEXT NOT NULL,
    reference TEXT,
    suite TEXT,
    statut TEXT NOT NULL DEFAULT 'a_traiter',       -- a_traiter | traite | classe
    fichier TEXT,
    saisi_par INTEGER,
    cree_le TEXT
);

CREATE TABLE IF NOT EXISTS archives (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    titre TEXT NOT NULL,
    eleve_id INTEGER,
    annee TEXT,
    fichier TEXT NOT NULL,
    nom_original TEXT,
    saisi_par INTEGER,
    cree_le TEXT
);

-- ---------------------------------------------------------------- v1.3
CREATE TABLE IF NOT EXISTS ecoles (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    sigle TEXT,
    statut TEXT DEFAULT 'Privée',                   -- Publique | Privée
    ordre TEXT,                                     -- Maternelle et primaire, Secondaire…
    departement TEXT,                               -- DDEMP
    cs TEXT,                                        -- circonscription scolaire
    up TEXT,                                        -- unité pédagogique
    zone TEXT,
    commune TEXT,
    ville TEXT,
    adresse TEXT,
    bp TEXT,
    telephone TEXT,
    email TEXT,
    directeur_titre TEXT DEFAULT 'Directeur',
    directeur_nom TEXT,
    directeur_tel TEXT,
    admin_titre TEXT DEFAULT 'Administrateur',
    admin_nom TEXT,
    ccs_titre TEXT DEFAULT 'Le CCS',
    ccs_nom TEXT,
    cachet_sup TEXT,
    cachet_inf TEXT,
    cachet_centre TEXT,
    cachet_couleur TEXT DEFAULT 'bleu',
    actif INTEGER NOT NULL DEFAULT 1,
    cree_le TEXT
);

CREATE TABLE IF NOT EXISTS affectations (           -- enseignants : classes (et matières au secondaire)
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    classe_id INTEGER NOT NULL,
    matiere_id INTEGER,                             -- NULL = titulaire (toutes les matières)
    UNIQUE(user_id, classe_id, matiere_id)
);

CREATE TABLE IF NOT EXISTS signatures (
    cle TEXT PRIMARY KEY,                           -- ex. ecole:1:directeur, classe:3:titulaire, eleve:12
    image TEXT NOT NULL,                            -- image PNG en data URL
    maj TEXT
);

CREATE TABLE IF NOT EXISTS documents_modules (      -- en-têtes et réglages sauvegardés par module
    cle TEXT PRIMARY KEY,
    donnees TEXT NOT NULL,
    maj TEXT,
    maj_par INTEGER
);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY,
    classe_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    annee TEXT NOT NULL,
    type TEXT NOT NULL,                             -- diagnostique | formative | sommative | certificative
    numero INTEGER NOT NULL DEFAULT 1,
    libelle TEXT NOT NULL,                          -- clé des notes (notes.periode)
    date TEXT,
    matieres TEXT,                                  -- liste JSON des matières évaluées
    seuil INTEGER,                                  -- nombre de matières >= 10 exigé (vide = 2/3 automatique)
    cree_le TEXT,
    UNIQUE(classe_id, annee, libelle)
);

CREATE TABLE IF NOT EXISTS cep_fiches (
    eleve_id INTEGER PRIMARY KEY REFERENCES eleves(id) ON DELETE CASCADE,
    session TEXT, centre TEXT, option TEXT DEFAULT 'CEP + entrée en 6è',
    etab1 TEXT, etab2 TEXT, etab3 TEXT, residence_parents TEXT,
    dispense_age INTEGER DEFAULT 0, dispense_sport INTEGER DEFAULT 0,
    parent_lien TEXT, fait_a TEXT, fait_le TEXT, maj TEXT
);

CREATE TABLE IF NOT EXISTS jours_classe (            -- exceptions au calendrier (congés, jours fériés, rattrapages)
    ecole_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    demi_journees INTEGER NOT NULL,                 -- 0, 1 ou 2
    motif TEXT,
    PRIMARY KEY (ecole_id, date)
);

CREATE TABLE IF NOT EXISTS registre (               -- absences par demi-journée (1 = matin, 2 = après-midi)
    eleve_id INTEGER NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    demi INTEGER NOT NULL,
    PRIMARY KEY (eleve_id, date, demi)
);

CREATE TABLE IF NOT EXISTS cep_blanc_sessions (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER,
    annee TEXT, departement TEXT, ddemp TEXT, cs TEXT, commune TEXT, centre TEXT, chef_centre TEXT,
    numero INTEGER DEFAULT 1, date_signature TEXT,
    matieres TEXT,                                  -- liste JSON des matières
    seuil INTEGER,
    cree_le TEXT
);

CREATE TABLE IF NOT EXISTS cep_blanc_candidats (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES cep_blanc_sessions(id) ON DELETE CASCADE,
    numero_table TEXT, nom TEXT NOT NULL, prenoms TEXT, sexe TEXT, ecole TEXT,
    notes TEXT,                                     -- JSON {matiere: note}
    eleve_id INTEGER
);

CREATE TABLE IF NOT EXISTS cantine_config (
    classe_id INTEGER PRIMARY KEY,
    montant_jour INTEGER NOT NULL DEFAULT 0,
    valide INTEGER NOT NULL DEFAULT 0,
    valide_le TEXT
);

CREATE TABLE IF NOT EXISTS cantine_paiements (
    id INTEGER PRIMARY KEY,
    eleve_id INTEGER NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    montant INTEGER NOT NULL,
    saisi_par INTEGER,
    cree_le TEXT,
    UNIQUE(eleve_id, date)
);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    cree_le TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# Référentiel repris de gescol_complet.py
MATIERES_PRIMAIRE = [
    ("COM.OR", "Communication orale", 1, "standard"),
    ("DIC", "Dictée", 1, "standard"),
    ("COMP.EC", "Compréhension de l'écrit", 1, "standard"),
    ("MATH", "Mathématiques", 2, "standard"),
    ("ED.SOC", "Éducation sociale (incl. EM)", 1, "standard"),
    ("ED.SCI", "Éducation scientifique et technologique", 1, "standard"),
    ("ART.P", "Éducation artistique (plastique)", 1, "exclu_2_3"),
    ("ART.V", "Éducation artistique (vivant)", 1, "exclu_2_3"),
    ("ANG", "Anglais", 1, "standard"),
    ("EXP.EC", "Expression écrite", 1, "standard"),
    ("EPS", "Éducation physique et sportive", 1, "exclu_2_3"),
]
# Maternelle : domaines d'apprentissage (modifiables dans la page Matières)
MATIERES_MATERNELLE = [
    ("LANG", "Langage et communication", 1, "standard"),
    ("PRE.LECT", "Pré-lecture et pré-écriture", 1, "standard"),
    ("EV.MATH", "Éveil mathématique", 1, "standard"),
    ("EV.SCI", "Éveil scientifique et technologique", 1, "standard"),
    ("ED.SOC", "Éducation sociale et vie pratique", 1, "standard"),
    ("MOTR", "Motricité et éducation physique", 1, "standard"),
    ("ART", "Expression artistique (dessin, chant, danse)", 1, "standard"),
    ("AUTO", "Autonomie et comportement", 1, "standard"),
]
MATIERES_SECONDAIRE = [
    ("FR.COM", "Français – Communication écrite", 2, "standard"),
    ("FR.DIC", "Français – Dictée", 1, "standard"),
    ("FR.EXP", "Français – Expression écrite", 2, "standard"),
    ("FR.LEC", "Français – Lecture / compréhension", 2, "standard"),
    ("MATH", "Mathématiques", 3, "standard"),
    ("HG", "Histoire et géographie", 2, "standard"),
    ("ANG", "Anglais", 2, "standard"),
    ("ESP", "Espagnol", 2, "standard"),
    ("ALL", "Allemand", 2, "standard"),
    ("PCT", "Physique, chimie et technologie", 3, "standard"),
    ("SVT", "Sciences de la vie et de la terre", 2, "standard"),
    ("PHILO", "Philosophie", 2, "standard"),
    ("EPS", "Éducation physique et sportive", 1, "standard"),
]


def chemin_db():
    return os.path.join(current_app.instance_path, "gescol.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(chemin_db())
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def fermer_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def q(sql, args=(), un=False):
    cur = get_db().execute(sql, args)
    lignes = cur.fetchall()
    return (lignes[0] if lignes else None) if un else lignes


def ex(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def initialiser():
    db = get_db()
    db.executescript(SCHEMA)
    if not q("SELECT 1 FROM utilisateurs LIMIT 1"):
        db.execute("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp) "
                   "VALUES (?,?,?,?,1)",
                   ("admin", "Administrateur", "admin", generate_password_hash(os.environ.get("GESCOL_ADMIN_MDP") or "admin123")))
    for cycle, liste in (("primaire", MATIERES_PRIMAIRE), ("secondaire", MATIERES_SECONDAIRE),
                         ("maternelle", MATIERES_MATERNELLE)):
        if not q("SELECT 1 FROM matieres WHERE cycle=? LIMIT 1", (cycle,)):
            for ordre, (code, nom, coef, mode) in enumerate(liste, 1):
                db.execute("INSERT INTO matieres (code, nom, cycle, coefficient, mode_calcul, ordre) "
                           "VALUES (?,?,?,?,?,?)", (code, nom, cycle, coef, mode, ordre))
    migrer(db)
    db.commit()


def colonnes(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def migrer(db):
    """Met à niveau une base créée par une version précédente, sans perte de données."""
    ajouts = [
        ("notes", "appreciation", "TEXT"),
        ("eleves", "parent_id", "INTEGER"),
        # v1.3
        ("utilisateurs", "ecole_id", "INTEGER"),
        ("classes", "ecole_id", "INTEGER NOT NULL DEFAULT 1"),
        ("classes", "titulaire_nom", "TEXT"),
        ("classes", "titulaire_titre", "TEXT DEFAULT 'Le titulaire'"),
        ("personnel", "ecole_id", "INTEGER NOT NULL DEFAULT 1"),
        ("tresorerie", "ecole_id", "INTEGER NOT NULL DEFAULT 1"),
        ("courriers", "ecole_id", "INTEGER NOT NULL DEFAULT 1"),
        ("archives", "ecole_id", "INTEGER NOT NULL DEFAULT 1"),
        ("eleves", "matricule_educmaster", "TEXT"),
        ("eleves", "nip", "TEXT"),
        ("eleves", "numero_table", "TEXT"),
        ("eleves", "centre_examen", "TEXT"),
        ("eleves", "annees_scolarite", "INTEGER"),
        ("eleves", "redoublant", "INTEGER DEFAULT 0"),
        ("eleves", "mdp_hash", "TEXT"),
    ]
    # v1.3 : le nom de classe n'est plus unique pour toute l'installation (deux écoles peuvent avoir un « CM2 »)
    sql_classes = (db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='classes'").fetchone() or [""])[0]
    if "UNIQUE" in (sql_classes or "").upper():
        db.commit()
        db.execute("PRAGMA foreign_keys = OFF")
        import re as _re
        cols = ", ".join(r[1] for r in db.execute("PRAGMA table_info(classes)"))
        nouveau = _re.sub(r"nom\s+TEXT\s+UNIQUE\s+NOT\s+NULL", "nom TEXT NOT NULL", sql_classes, flags=_re.I)
        nouveau = _re.sub(r"(?i)CREATE TABLE\s+(IF NOT EXISTS\s+)?\"?classes\"?", "CREATE TABLE classes_v13", nouveau, count=1)
        db.execute(nouveau)
        db.execute(f"INSERT INTO classes_v13 ({cols}) SELECT {cols} FROM classes")
        db.execute("DROP TABLE classes")
        db.execute("ALTER TABLE classes_v13 RENAME TO classes")
        db.commit()
        db.execute("PRAGMA foreign_keys = ON")
    for table, col, typ in ajouts:
        if col not in colonnes(db, table):
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    # v1.3 : l'établissement des versions précédentes devient l'école n° 1
    if not db.execute("SELECT 1 FROM ecoles LIMIT 1").fetchone():
        p = {r[0]: r[1] for r in db.execute("SELECT cle, valeur FROM parametres")}
        db.execute("""INSERT INTO ecoles (id, nom, sigle, adresse, ville, telephone, email, directeur_nom, cachet_sup,
                      cachet_centre, cachet_inf, cree_le) VALUES (1,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))""",
                   (p.get("ecole_nom") or "Établissement Scolaire CPFA", p.get("ecole_sigle") or "CPFA",
                    p.get("ecole_adresse") or "Cotonou, Bénin", p.get("ecole_ville") or "Cotonou",
                    p.get("ecole_telephone") or "", p.get("ecole_email") or "", p.get("ecole_directeur") or "",
                    (p.get("ecole_nom") or "Établissement Scolaire CPFA").upper()[:40], "LA DIRECTION",
                    (p.get("ecole_ville") or "Cotonou").upper()))
