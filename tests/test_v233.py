# -*- coding: utf-8 -*-
"""Tests 2.3.3 : « Listes de classe » — accès rapide, lecture seule (cours → classe → élèves).
(1) école : menu, tuile du tableau de bord, cours (maternelle et primaire), classe ou toutes les classes du cours,
colonnes, effectifs G / F / T, recherche, tri, lien vers la fiche, PDF (Times, en-tête officiel), Excel, impression ;
pages d'inscription inchangées ; (2) enseignant : seulement ses classes (403 sinon), lien dans le portail ;
(3) CS : école → cours → classe, page de la structure (pas de « Choisissez une école »), observateur exclu.
Données fictives. Lancer : python3 -m unittest tests.test_v233"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

ECOLE = r'''
import io, os, sys, tempfile, zipfile
import openpyxl
from datetime import date
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = os.environ["EDITION_TEST"]
if os.environ.get("AUTONOME_TEST"): os.environ[P + "_AUTONOME"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from werkzeug.security import generate_password_hash
import config
app.config["TESTING"] = True
auj = date.today().isoformat()
A = config.ANNEE_ACTIVE
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    cia = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id, titulaire_nom) VALUES ('CI A','CI',0,1,'TITULAIRE Un')")
    cib = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CI B','CI',0,1)")
    cm2 = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM2 A','CM2',0,1)")
    mat = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('Petits','Maternelle 1',0,1)")
    def el(m, nom, pre, s, cid, red=0, statut="inscrit", em="", dn="2019-03-04", ln="Pobè", par="PARENT X", tel="0102030405"):
        return ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, classe_id, statut, date_inscription, annee, redoublant, "
                  "matricule_educmaster, date_naissance, lieu_naissance, parent_nom, parent_telephone) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (m, nom, pre, s, cid, statut, auj, A, red, em, dn, ln, par, tel))
    e1 = el("M1", "ZOUNON", "Afi", "F", cia, em="EM-001")
    el("M2", "ADJOVI", "Koffi", "M", cia, red=1)
    el("M3", "BOKO", "Ama", "F", cib)
    el("M4", "SORTI", "Parti", "M", cia, statut="sorti")
    el("M5", "DOSSOU", "Yao", "M", cm2)
    el("M6", "AHO", "Bébé", "F", mat, dn="2022-01-01")
    ens = ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, ecole_id) VALUES ('ens1','ENS Un','enseignant',?,0,1)",
             (generate_password_hash("Ens-12345"),))
    ex("INSERT INTO affectations (user_id, classe_id) VALUES (?,?)", (ens, cm2))
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
h = c.get("/").data.decode()
assert "Listes de classe" in h and "/listes-classe" in h, "menu / tuile"
h = c.get("/listes-classe").data.decode()
for n in ("Maternelle 1", "CI", "CM2"):
    assert ">" + n + "<" in h, n
assert h.index("Maternelle 1") < h.index(">CI<") < h.index(">CM2<")              # ordre des cours
h = c.get("/listes-classe?cours=CI").data.decode()                              # toutes les classes du CI
assert "Toutes les classes du CI" in h and "LISTE DES ÉLÈVES DU CI" in h
assert "ZOUNON" in h and "BOKO" in h and "ADJOVI" in h and "SORTI" not in h     # inscrits seulement
assert "Effectif : <b>3</b> — garçons : <b>1</b>, filles : <b>2</b>" in h, h[h.find("Effectif"):][:200]
assert h.index("ADJOVI") < h.index("BOKO") < h.index("ZOUNON")                    # tri par nom
assert "Redoublant" in h and "Nouveau" in h and "M1 / EM-001" in h and "04/03/2019 à Pobè" in h and "PARENT X" in h
assert "/eleves/%d" % e1 in h                                                     # lien vers la fiche
h = c.get("/listes-classe?classe=%d" % cia).data.decode()
assert "LISTE DE LA CLASSE CI A" in h and "BOKO" not in h and "Titulaire : TITULAIRE Un" in h
h = c.get("/listes-classe?cours=CI&tri=sexe").data.decode()
assert h.index("BOKO") < h.index("ADJOVI")                                        # F avant M
h = c.get("/listes-classe?cours=CI&q=zoun").data.decode()
assert "ZOUNON" in h and "BOKO" not in h
r = c.get("/listes-classe.pdf?cours=CI")
assert r.status_code == 200 and r.data[:4] == b"%PDF" and "liste_ci.pdf" in r.headers["Content-Disposition"]
txt = r.data
assert b"Serif" in txt or b"Times" in txt or b"Liberation" in txt                 # Times New Roman (Liberation Serif)
r = c.get("/listes-classe.xlsx?classe=%d" % cia)
assert r.status_code == 200
ws = openpyxl.load_workbook(io.BytesIO(r.data)).active
vals = [[x for x in row] for row in ws.iter_rows(values_only=True)]
assert any(v and "LISTE DE LA CLASSE CI A" in str(v) for row in vals for v in row)
lignes = [row for row in vals if row and row[0] in (1, 2)]
assert [row[1] for row in lignes] == ["ADJOVI", "ZOUNON"] and lignes[0][6] == "Redoublant", lignes
assert c.get("/listes-classe?classe=99999").status_code == 403
# Excel EducMaster (importation) : modèle officiel rempli, puis relu par l'import EducMaster existant (aller-retour)
h = c.get("/listes-classe?cours=CI").data.decode()
assert "Excel EducMaster (importation)" in h and "Excel liste de classe (lisible)" in h
r = c.get("/listes-classe/educmaster.xlsx?cours=CI")
assert r.status_code == 200 and r.data[:2] == b"PK", r.status_code
modele = openpyxl.load_workbook(os.path.join("modeles", "educmaster_modele_classe.xlsx"))
wb = openpyxl.load_workbook(io.BytesIO(r.data))
assert wb.sheetnames == modele.sheetnames and wb.active.title == "CI", (wb.sheetnames, wb.active.title)
ws = wb["CI"]
assert [x.value for x in ws[1]] == [x.value for x in modele["CI"][1]] == ["Nom", "Prénom ( s )", "Sexe", "Date de naissance",
       "Lieu de naissance", "Téléphone de parents", "Nationalité", "Npi"]
rows = [list(x) for x in ws.iter_rows(min_row=2, values_only=True) if any(x)]
assert rows[0] == ["ADJOVI", "Koffi", "M", "04/03/2019", "Pobè", "0102030405", "Béninoise", None], rows
assert [x[0] for x in rows] == ["ADJOVI", "BOKO", "ZOUNON"] and all(ws.cell(row=2, column=j).number_format == "@" for j in (6, 8))
assert all(not any(x) for n in wb.sheetnames if n != "CI" for x in wb[n].iter_rows(min_row=2, values_only=True))
r = c.post("/educmaster/modeles/classe/importer", data={"simuler": "1", "fichier": (io.BytesIO(c.get("/listes-classe/educmaster.xlsx?cours=CI").data), "liste.xlsx")},
           content_type="multipart/form-data", follow_redirects=True)
t = r.data.decode()
assert "0 élève(s) mis à jour, 0 créé(s), 3 inchangé(s), 0 ignoré(s)" in t, t[t.find("Simulation"):][:300]
r = c.get("/listes-classe/educmaster.xlsx?cours=Maternelle 1")
assert openpyxl.load_workbook(io.BytesIO(r.data)).active.title == "Marternelle 1"
# notes vers EducMaster (export existant, inchangé) : lien depuis la liste du CM2, aller-retour avec l'import des notes
h = c.get("/listes-classe?classe=%d" % cm2).data.decode()
assert "Excel EducMaster (notes) — CM2 A" in h and "/educmaster/modeles/notes-primaire/%d.xlsx" % cm2 in h
r = c.get("/educmaster/modeles/notes-primaire/%d.xlsx" % cm2)
assert r.status_code == 200 and r.data[:2] == b"PK"
wbn = openpyxl.load_workbook(io.BytesIO(r.data))
mod_n = openpyxl.load_workbook(os.path.join("modeles", "educmaster_modele_notes_primaire.xlsx"))
assert wbn.sheetnames == mod_n.sheetnames
wsn = wbn.worksheets[1]
assert [x.value for x in wsn[1]] == [x.value for x in mod_n.worksheets[1][1]]
lig = next(rr for rr in range(1, 12) if wsn.cell(row=rr, column=2).value == "DOSSOU")
colm = next(x.column for x in wsn[1] if x.column > 3 and x.value)
wsn.cell(row=lig, column=colm, value=14)
b = io.BytesIO(); wbn.save(b)
t = c.post("/educmaster/modeles/notes-primaire/%d/importer" % cm2, data={"simuler": "1", "creer": "1", "fichier": (io.BytesIO(b.getvalue()), "notes.xlsx")},
           content_type="multipart/form-data", follow_redirects=True).data.decode()
assert "notes importées pour 1 élève(s)" in t, t[t.find("Simulation"):][:300]
# personnel vers EducMaster (export existant « Mes agents », inchangé) : lien depuis la liste du personnel, aller-retour
with app.app_context():
    ex("INSERT INTO personnel (matricule, nom, prenoms, sexe, fonction, telephone, ecole_id, actif) VALUES ('AG-77','AGENT','Test','F','Enseignant(e)','0199887766',1,1)")
h = c.get("/personnel").data.decode()
assert "Excel EducMaster (agents)" in h, h[:3000]
r = c.get("/educmaster/modeles/agents/rempli.xlsx")
wa = openpyxl.load_workbook(io.BytesIO(r.data))
mod_a = openpyxl.load_workbook(os.path.join("modeles", "educmaster_modele_agents.xlsx"))
assert wa.sheetnames == mod_a.sheetnames and [x.value for x in wa.worksheets[0][1]] == [x.value for x in mod_a.worksheets[0][1]]
t = c.post("/educmaster/modeles/agents/importer", data={"simuler": "1", "fichier": (io.BytesIO(r.data), "agents.xlsx")},
           content_type="multipart/form-data", follow_redirects=True).data.decode()
assert "0 créé(s)" in t and "0 ignoré(s)" in t, t[t.find("Simulation"):][:300]
# pages d'inscription inchangées
assert c.get("/eleves").status_code == 200 and "Inscrire un élève" in c.get("/eleves").data.decode()
print("ADMIN_OK")
# enseignant : ses classes seulement
c2 = app.test_client()
assert c2.post("/login", data={"identifiant": "ens1", "mdp": "Ens-12345"}).status_code == 302
h = c2.get("/listes-classe").data.decode()
assert "DOSSOU" in h and "ZOUNON" not in h and ">CI<" not in h, h[-2000:]
assert c2.get("/listes-classe?classe=%d" % cia).status_code == 403
assert c2.get("/listes-classe?cours=CI").status_code == 200 and "ZOUNON" not in c2.get("/listes-classe?cours=CI").data.decode()
assert c2.get("/listes-classe.pdf?classe=%d" % cm2).status_code == 200
assert c2.get("/listes-classe.xlsx?classe=%d" % cia).status_code == 403
h = c2.get("/enseignant/tableau").data.decode()
assert "Listes de classe" in h and "Listes de mes classes" in h, h[-1500:]
print("ENSEIGNANT_OK")
'''

CS = r'''
import os, sys, subprocess, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ.update({P + "_EDITION": "cs", P + "_DATA": tempfile.mkdtemp()})
subprocess.run([sys.executable, "demo_juridiction.py"], check=True, stdout=subprocess.DEVNULL)
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from datetime import date
from werkzeug.security import generate_password_hash
import config
app.config["TESTING"] = True
with app.app_context():
    eid = ex("INSERT INTO ecoles (nom, actif) VALUES ('EPP Liste Test', 1)")
    cid = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CE1 A','CE1',0,?)", (eid,))
    ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, classe_id, statut, date_inscription, annee) VALUES ('X1','KPADE','Rita','F',?,'inscrit',?,?)",
       (cid, date.today().isoformat(), config.ANNEE_ACTIVE))
    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp) VALUES ('obs1','OBS','observateur',?,0)",
       (generate_password_hash("Obs-12345"),))
c = app.test_client()
assert c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"}).status_code == 302
assert "Listes de classe" in c.get("/").data.decode() or "Listes de classe" in c.get("/juridiction").data.decode()
h = c.get("/listes-classe").data.decode()
assert "Choisissez une école à ouvrir" not in h and "EPP Liste Test" in h, h[-2000:]
h = c.get("/listes-classe?ecole=%d" % eid).data.decode()
assert ">CE1<" in h and "KPADE" in h and "ecoles/%d/choisir" % eid in h, h[-2500:]       # fiche : ouvre l'école
r = c.get("/listes-classe.pdf?ecole=%d&cours=CE1" % eid)
assert r.status_code == 200 and r.data[:4] == b"%PDF"
r = c.get("/listes-classe/educmaster.xlsx?ecole=%d&cours=CE1" % eid)
assert r.status_code == 200 and r.data[:2] == b"PK"
assert c.get("/listes-classe?ecole=999999").status_code == 403
c3 = app.test_client()
assert c3.post("/login", data={"identifiant": "obs1", "mdp": "Obs-12345"}).status_code == 302
r = c3.get("/listes-classe")
assert r.status_code in (302, 403) and b"KPADE" not in r.data
print("CS_OK")
'''


class TestV233(unittest.TestCase):
    def lancer(self, script, edition, attendu, **plus):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_TEST=edition, **plus)
        for k in list(env):
            if k.endswith(("_EDITION", "_DATA")) and k.startswith(("SCOLARIS", "GESCOL")):
                env.pop(k)
        r = subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)
        for a in attendu:
            self.assertIn(a, r.stdout, r.stdout[-2000:] + r.stderr[-5000:])

    def test_ecole_privee(self):
        self.lancer(ECOLE, "privee", ("ADMIN_OK", "ENSEIGNANT_OK"))

    def test_ecole_publique(self):
        self.lancer(ECOLE, "publique", ("ADMIN_OK", "ENSEIGNANT_OK"))

    def test_ecole_autonome(self):
        self.lancer(ECOLE, "privee", ("ADMIN_OK", "ENSEIGNANT_OK"), AUTONOME_TEST="1")

    def test_cs(self):
        self.lancer(CS, "cs", ("CS_OK",))


if __name__ == "__main__":
    unittest.main()
