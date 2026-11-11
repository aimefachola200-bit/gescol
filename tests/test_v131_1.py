# -*- coding: utf-8 -*-
"""Tests 1.31.1 : la préparation de classe s'ouvre dans toutes les éditions.
(1) fiche ouverte depuis une classe (« ?classe= ») : le gabarit plantait (« 'int' is undefined ») ;
(2) PDF des guides dont le HTML ouvre une balise <b> dans un bloc et la ferme dans le suivant ;
(3) parcours de toutes les pages /preparation (liens suivis) en école privée, publique, circonscription et pour
l'application de l'enseignant (après le premier lancement), base neuve et base créée par une version antérieure ;
(4) chaque fiche du corpus avec « ?classe= », chaque guide (page et PDF), chaque programme, chaque cahier de révision.
Lancer : python3 -m unittest tests.test_v131_1"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import html, os, re, sys, tempfile, random
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
ENS = dict(nom="Houngbo", prenoms="Afiavi", sexe="F", nip="1234567890", matricule="MAT-77", grade="B1-5", categorie="ACDPE",
           statut="Titulaire", date_naissance="1990-04-02", lieu_naissance="Pobè", telephone="0197000000", email="",
           date_prise_service="2015-10-01", date_service_ecole="2022-10-01", diplome_academique="BAC D", diplome_academique_annee="2010",
           diplome_pro="CEAP et CAP", diplome_pro_annee="2018", ecole_nom="EPP Issaba", secteur="publique", cs="Pobè",
           departement="Plateau", commune="Pobè", directeur_nom="ADJAHO Paul", directeur_tel="0196000000", ecole_telephone="",
           ccs_nom="KOTO Marc", identifiant="afiavi", mdp="motdepasse1", confirmation="motdepasse1",
           classe_nom_1="CE2 A", classe_niveau_1="CE2", classe_nom_2="CM2 B", classe_niveau_2="CM2")
clients = []
if ED == "enseignant":
    c = app.test_client()
    assert c.post("/enseignant/premier-lancement", data=ENS).status_code == 302
    clients.append(("enseignant", c))
else:
    with app.app_context():
        ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
        ce2 = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CE2 P','CE2',0,1)")
        uid = ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) VALUES ('ens1','DOSSOU Jean','enseignant',?,0,1,1)",
                 (generate_password_hash("ens-mdp-123"),))
        ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,NULL)", (uid, ce2))
        ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) VALUES ('dir1','DIR Paul','directeur',?,0,1,1)",
           (generate_password_hash("dir-mdp-123"),))
    for ident, mdp in (("admin", "admin123"), ("dir1", "dir-mdp-123"), ("ens1", "ens-mdp-123")):
        c = app.test_client()
        assert c.post("/login", data={"identifiant": ident, "mdp": mdp}).status_code == 302
        if c.get("/preparation").status_code == 200:
            clients.append((ident, c))
assert clients, "aucun compte n'ouvre la préparation"
erreurs = []
def lire(c, u):
    r = c.get(u)
    if r.status_code >= 500 or r.status_code == 404 and "/preparation/" in u and "classe=" not in u:
        erreurs.append((u, r.status_code))
    return r
for ident, c in clients:
    vus, file = set(), ["/preparation", "/preparation/programmes", "/preparation/guides", "/preparation/fiches", "/preparation/resumes",
                        "/preparation/revisions"]
    while file and len(vus) < int(os.environ.get("LIMITE", "250")):
        u = file.pop(0)
        if u in vus:
            continue
        vus.add(u)
        r = lire(c, u)
        if r.status_code == 200 and r.mimetype == "text/html":
            for h in re.findall(r'href="(/preparation[^"#]*)"', r.data.decode("utf8", "replace")):
                h = html.unescape(h)
                if h not in vus:
                    file.append(h)
import m_preparation as MP
C = MP.corpus()
ident, c = clients[0]
cid = 1
if ED == "enseignant":
    with app.app_context():
        cid = q("SELECT id FROM classes ORDER BY id", un=True)["id"]
for f in C["fiches"]:
    lire(c, f"/preparation/fiches/{f['id']}?classe={cid}")
for x in C["guides"]:
    lire(c, f"/preparation/guides/{x['id']}"); lire(c, f"/preparation/guides/{x['id']}.pdf")
for x in C["programmes"]:
    lire(c, f"/preparation/programmes/{x['id']}")
for x in C.get("revisions") or []:
    lire(c, f"/preparation/revisions/{x['id']}.pdf")
random.seed(131)
for f in random.sample(C["fiches"], 40):
    lire(c, f"/preparation/fiches/{f['id']}.pdf?classe={cid}")
assert not erreurs, erreurs[:15]
assert MP._equilibrer("<b>a</b>b</b><i>c") == "<b>a</b>b<i>c</i>"
print("OK-" + ED, len(clients))
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA", "SCOLARIS_AUTONOME", "GESCOL_AUTONOME"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=1500)


class TestPreparationToutesEditions(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")

    def test_enseignant(self):
        self.verifier("enseignant")


class TestGabarits(unittest.TestCase):
    def test_pas_de_type_int(self):
        """« request.args.get(..., type=int) » n'existe pas dans les gabarits Jinja (int n'y est pas défini)."""
        dossier = os.path.join(RACINE, "templates")
        for nom in os.listdir(dossier):
            with open(os.path.join(dossier, nom), encoding="utf-8") as f:
                t = f.read()
            self.assertNotRegex(t, r"type=(int|float|bool)\b", nom)


if __name__ == "__main__":
    unittest.main()
