# -*- coding: utf-8 -*-
"""Charge des données de démonstration (2 classes, 12 élèves, notes, paiements).
Usage : python demo.py        (à ne PAS lancer sur la base réelle de l'école)"""
import random
from datetime import date

from werkzeug.security import generate_password_hash

import config
from app import create_app
from db import ex, get_db, q

NOMS = ["AHOUANDJINOU", "DOSSOU", "HOUNKPATIN", "KPADONOU", "ADJOVI", "SOSSOU", "AGBODJAN", "ZINSOU",
        "TOSSOU", "GBAGUIDI", "HOUNSOU", "ASSOGBA"]
PRENOMS_F = ["Grâce", "Carine", "Mireille", "Fifamè", "Sêmêvo", "Nadège"]
PRENOMS_M = ["Rodrigue", "Koffi", "Sèdjro", "Arnaud", "Mahougnon", "Brice"]


def charger():
    app = create_app()
    with app.app_context():
        if q("SELECT 1 FROM eleves LIMIT 1"):
            print("La base contient déjà des élèves : démonstration non chargée.")
            return
        random.seed(7)
        cm2 = ex("INSERT INTO classes (nom, niveau, frais_scolarite) VALUES ('CM2 A','CM2',60000)")
        q4 = ex("INSERT INTO classes (nom, niveau, frais_scolarite) VALUES ('4ème A','4ème',95000)")
        for ident, nom, role in (("secretariat", "Secrétariat", "secretaire"), ("compta", "Comptabilité", "comptable"),
                                 ("enseignant", "Enseignant", "enseignant"), ("directeur", "Direction", "directeur")):
            ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash) VALUES (?,?,?,?)",
               (ident, nom, role, generate_password_hash("demo1234")))
        for i, nom in enumerate(NOMS):
            cid, niv = (cm2, "P") if i < 6 else (q4, "S")
            sexe = "F" if i % 2 == 0 else "M"
            prenom = (PRENOMS_F if sexe == "F" else PRENOMS_M)[i // 2]
            naiss = date(2015 if cid == cm2 else 2012, 1 + i, 3 + i).isoformat()
            eid = ex("INSERT INTO eleves (nom, prenoms, sexe, date_naissance, lieu_naissance, classe_id, parent_nom, "
                     "parent_telephone, adresse, date_inscription, annee) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (nom, prenom, sexe, naiss, random.choice(["Cotonou", "Porto-Novo", "Abomey-Calavi", "Parakou"]),
                      cid, f"{nom} Parent", f"+229 01 9{i}00 00 {10 + i}", "Cotonou", date.today().isoformat(),
                      config.ANNEE_ACTIVE))
            ex("UPDATE eleves SET matricule=? WHERE id=?", (f"{config.ECOLE['sigle']}-{config.ANNEE_ACTIVE[:4]}-{niv}-{eid:04d}", eid))
            cycle = "primaire" if cid == cm2 else "secondaire"
            niveau_eleve = random.uniform(7, 16)
            for m in q("SELECT * FROM matieres WHERE cycle=?", (cycle,)):
                if m["code"] == "ALL" and i % 2 == 0:
                    continue  # langue vivante 2 : Espagnol OU Allemand
                if m["code"] == "ESP" and i % 2 == 1:
                    continue
                if m["code"] == "PHILO":
                    continue  # pas de philosophie en 4ème
                v = round(max(0, min(20, random.gauss(niveau_eleve, 3))) * 4) / 4
                ex("INSERT INTO notes (eleve_id, matiere_id, periode, annee, valeur) VALUES (?,?,?,?,?)",
                   (eid, m["id"], config.PERIODES[0], config.ANNEE_ACTIVE, v))
            du = 60000 if cid == cm2 else 95000
            for k, montant in enumerate([du // 2, du // 4][: 1 + i % 2]):
                mode = ["especes", "mtn_momo", "moov_money"][(i + k) % 3]
                pid = ex("INSERT INTO paiements (eleve_id, annee, montant, mode, reference, motif, date_paiement, saisi_par) "
                         "VALUES (?,?,?,?,?,?,datetime('now','localtime'),1)",
                         (eid, config.ANNEE_ACTIVE, montant, mode, None if mode == "especes" else f"TX{eid}{k}8812",
                          "Frais de scolarité"))
                ex("UPDATE paiements SET numero_recu=? WHERE id=?", (f"REC-{config.ANNEE_ACTIVE[:4]}-{pid:05d}", pid))
        charger_complements()
        print("Démonstration chargée. Comptes : secretariat / compta / enseignant / directeur (mot de passe demo1234).")


def charger_complements():
    """Maternelle, parents, appel, personnel, trésorerie, courrier (version 1.2)."""
    from datetime import timedelta
    import notif
    random.seed(11)
    mat = ex("INSERT INTO classes (nom, niveau, frais_scolarite) VALUES ('Maternelle 2 A','Maternelle 2',45000)")
    domaines = q("SELECT * FROM matieres WHERE cycle='maternelle'")
    for i, (nom, prenom, sexe) in enumerate([("AKPLOGAN", "Divine", "F"), ("HOUNGBO", "Élie", "M"), ("QUENUM", "Ornella", "F"),
                                             ("AGOSSOU", "Josué", "M"), ("SAGBO", "Précieuse", "F")]):
        eid = ex("INSERT INTO eleves (nom, prenoms, sexe, date_naissance, lieu_naissance, classe_id, parent_nom, "
                 "parent_telephone, adresse, date_inscription, annee) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (nom, prenom, sexe, date(2021, 2 + i, 10 + i).isoformat(), "Cotonou", mat, f"{nom} Parent",
                  f"01 96 40 00 {20 + i}", "Cotonou", date.today().isoformat(), config.ANNEE_ACTIVE))
        ex("UPDATE eleves SET matricule=? WHERE id=?", (f"{config.ECOLE['sigle']}-{config.ANNEE_ACTIVE[:4]}-M-{eid:04d}", eid))
        for d in domaines:
            a = random.choices(["A", "ECA", "NA"], weights=[6, 3, 1])[0]
            ex("INSERT INTO notes (eleve_id, matiere_id, periode, annee, appreciation) VALUES (?,?,?,?,?)",
               (eid, d["id"], config.PERIODES[0], config.ANNEE_ACTIVE, a))
    # compte parent de démonstration (tél. 01 96 40 00 20, mot de passe parent123)
    tel = notif.normaliser_tel("01 96 40 00 20")
    pid = ex("INSERT INTO parents (nom, telephone, whatsapp, mdp_hash, doit_changer_mdp, cree_le) VALUES (?,?,?,?,0,?)",
             ("AKPLOGAN Parent", tel, tel, generate_password_hash("parent123"), date.today().isoformat() + " 08:00:00"))
    ex("UPDATE eleves SET parent_id=? WHERE parent_telephone='01 96 40 00 20'", (pid,))
    ex("UPDATE eleves SET parent_id=? WHERE id=1", (pid,))  # un 2e enfant au primaire (CM2 A)
    ex("INSERT INTO publications (classe_id, periode, annee, publie_le) VALUES (?,?,?,?)",
       (mat, config.PERIODES[0], config.ANNEE_ACTIVE, date.today().isoformat()))
    ex("INSERT INTO messages (parent_id, sens, sujet, texte, cree_le) VALUES (?,?,?,?,?)",
       (pid, "ecole", "Bienvenue", "Bienvenue dans l'espace parents de l'école.", date.today().isoformat() + " 08:00:00"))
    # appel des 5 derniers jours ouvrés
    jour, faits = date.today(), 0
    eleves = q("SELECT id, classe_id FROM eleves")
    while faits < 5:
        jour -= timedelta(days=1)
        if jour.weekday() >= 5:
            continue
        faits += 1
        for cid in {e["classe_id"] for e in eleves}:
            ex("INSERT INTO appels (classe_id, date, fait_le) VALUES (?,?,?)", (cid, jour.isoformat(), jour.isoformat() + " 08:10:00"))
        for e in eleves:
            r = random.random()
            if r < 0.07:
                ex("INSERT INTO presences (eleve_id, date, statut, justifie) VALUES (?,?,?,?)",
                   (e["id"], jour.isoformat(), "absent", int(random.random() < 0.5)))
            elif r < 0.11:
                ex("INSERT INTO presences (eleve_id, date, statut) VALUES (?,?,?)", (e["id"], jour.isoformat(), "retard"))
    # personnel
    for nom, prenoms, fonction, contrat, base, taux in [
            ("DAGBA", "Rosine", "Directeur / directrice", "CDI", 220000, 0), ("KOUTON", "Serge", "Enseignant(e)", "CDI", 110000, 0),
            ("AHOYO", "Pélagie", "Enseignant(e)", "CDI", 95000, 0), ("SOGLO", "Marcel", "Enseignant(e)", "Vacataire", 0, 2500),
            ("GANGBO", "Luc", "Gardien", "CDD", 55000, 0)]:
        i = ex("INSERT INTO personnel (nom, prenoms, fonction, type_contrat, salaire_base, taux_horaire, assujetti_its, date_embauche) "
               "VALUES (?,?,?,?,?,?,?,?)", (nom, prenoms, fonction, contrat, base, taux, 0 if contrat == "Vacataire" else 1, "2024-09-02"))
        ex("UPDATE personnel SET matricule=? WHERE id=?", (f"{config.ECOLE['sigle']}-RH-{i:04d}", i))
    # trésorerie et courrier
    d0 = date.today().replace(day=1).isoformat()
    for typ, cat, lib, m in [("sortie", "Eau et électricité", "Facture SBEE", 38500), ("sortie", "Fournitures et matériel", "Craies, cahiers de préparation", 27000),
                             ("entree", "Cantine", "Tickets de cantine", 42000), ("sortie", "Loyer", "Loyer du bâtiment annexe", 150000)]:
        ex("INSERT INTO tresorerie (date, type, categorie, libelle, montant, mode, cree_le) VALUES (?,?,?,?,?,?,?)",
           (d0, typ, cat, lib, m, "especes", d0))
    ex("INSERT INTO courriers (numero, sens, date, correspondant, objet, cree_le) VALUES (?,?,?,?,?,?)",
       (f"A-{date.today().year}-0001", "arrivee", d0, "Circonscription scolaire", "Calendrier des évaluations du 1er trimestre", d0))
    # v1.3 : fiche de l'école, titulaires, infos de carte scolaire
    ex("""UPDATE ecoles SET departement='Littoral', cs='Cotonou 1', up='UP 3', zone='Zone 2', commune='Cotonou',
          statut='Privée', ordre='Complexe (maternelle, primaire, secondaire)', directeur_titre='Directrice',
          directeur_nom='DAGBA Rosine', directeur_tel='01 97 00 00 00', admin_titre='Administrateur',
          admin_nom='HOUNSOU Parfait', ccs_titre='Le CCS', ccs_nom='TOSSOU Barthélemy', cachet_couleur='bleu'
          WHERE id=1""")
    ex("UPDATE classes SET titulaire_titre='Le titulaire', titulaire_nom='KOUTON Serge' WHERE niveau='CM2'")
    ex("UPDATE classes SET titulaire_titre='La titulaire', titulaire_nom='AHOYO Pélagie' WHERE niveau LIKE 'Maternelle%'")
    ex("UPDATE classes SET titulaire_titre='Le professeur principal', titulaire_nom='SOGLO Marcel' WHERE niveau='4ème'")
    for i, e in enumerate(q("SELECT * FROM eleves ORDER BY id"), 1):
        ex("UPDATE eleves SET matricule_educmaster=?, nip=?, annees_scolarite=?, centre_examen=? WHERE id=?",
           (f"EM{2026000 + i}", f"{1020304050 + i * 7}", 6 if i <= 6 else 3, "EPP Akpakpa Centre" if i <= 6 else None, e["id"]))


if __name__ == "__main__":
    charger()
