# -*- coding: utf-8 -*-
"""Saisie des notes : au collège, note directe de 0 à 20 (20/20 accepté, pas de note de performance) ; au primaire, règle inchangée."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")
import garde_notes as G  # noqa: E402

SCRIPT = r'''
import os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client(); c.get("/login")
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
    niv = os.environ["NIVEAU"]
    cid = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES (?, ?, 0, 1)", (niv + " A", niv))
    eid = ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, date_naissance, classe_id, statut, date_inscription, annee) VALUES ('M1','TEST','Eleve','M','2012-01-01',?,'inscrit','2026-09-15','2026-2027')", (cid,))
    cl = q("SELECT * FROM classes WHERE id=?", (cid,), un=True)
    mats = q("SELECT id, nom FROM matieres WHERE ecole_id=1 LIMIT 3") if False else None
r = c.get(f"/notes/{cid}/1"); assert r.status_code == 200, r.status_code
page = r.data.decode()
import re
noms = re.findall(r'name="n_%d_(\d+)"' % eid, page)
assert noms, "aucune case de note"
m1 = noms[0]
sec = os.environ["SIMPLE"] == "1"
assert (('name="p_%d_%s"' % (eid, m1)) in page) != sec, "case performance " + ("presente" if sec else "absente")
c.post(f"/notes/{cid}/1", data={f"n_{eid}_{m1}": "20"})
with app.app_context():
    v = q("SELECT valeur, performance FROM notes WHERE eleve_id=? AND matiere_id=?", (eid, m1), un=True)
if sec:
    assert v and v["valeur"] == 20 and v["performance"] is None, v
    c.post(f"/notes/{cid}/1", data={f"n_{eid}_{m1}": "14,75"})
    with app.app_context():
        assert q("SELECT valeur FROM notes WHERE eleve_id=? AND matiere_id=?", (eid, m1), un=True)["valeur"] == 14.75
    c.post(f"/notes/{cid}/1", data={f"n_{eid}_{m1}": "21"})
    with app.app_context():
        assert q("SELECT valeur FROM notes WHERE eleve_id=? AND matiere_id=?", (eid, m1), un=True)["valeur"] == 14.75
else:
    assert v is None, v          # primaire : 20 sans performance reste refuse
print("OK")
'''


class T(unittest.TestCase):
    def test_garde(self):
        self.assertEqual(G.lire("20", None, simple=True), (20.0, False, None))
        self.assertEqual(G.lire("14,5", "1", simple=True), (14.5, False, None))
        with self.assertRaises(G.NoteRefusee):
            G.lire("20.5", None, simple=True)
        with self.assertRaises(G.NoteRefusee):
            G.lire("20", None)                       # règle du primaire inchangée
        self.assertEqual(G.lire("19", "1"), (20.0, False, 1.0))
        self.assertEqual(G.afficher(15.5, 1.5, True), ("15.5", ""))

    def _lancer(self, edition, niveau, simple):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, NIVEAU=niveau, SIMPLE=simple, **{PREFIXE + "_EDITION": edition})
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True)
        self.assertIn("OK", r.stdout, r.stderr[-2500:])

    def test_college(self):
        self._lancer("sec_privee", "4ème", "1")

    def test_primaire(self):
        self._lancer("privee", "CM1", "0")


if __name__ == "__main__":
    unittest.main()
