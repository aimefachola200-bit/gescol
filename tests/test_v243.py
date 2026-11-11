# -*- coding: utf-8 -*-
"""Tests 2.4.3 : mode sombre et graphiques du tableau de bord.
Lancer : python3 -m unittest tests.test_v243"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")



SCRIPT = r'''
import html, io, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, q as _q, ex as _ex
import openpyxl
app.config["TESTING"] = True

def q(*a, **k):
    with app.app_context():
        r = _q(*a, **k)
        return [dict(x) for x in r] if isinstance(r, list) else (dict(r) if r else r)
def ex(*a, **k):
    with app.app_context():
        return _ex(*a, **k)
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-1500:]); return r
def txt(r): return html.unescape(ok(r).data.decode())
def pdf(r):
    ok(r); assert r.mimetype == "application/pdf" and r.data.startswith(b"%PDF"), (r.request.path, r.mimetype); return r
def xlsx(r):
    wb = openpyxl.load_workbook(io.BytesIO(ok(r).data)); return [[c.value for c in l] for l in wb.active.iter_rows()]

with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client()
p0 = txt(c.get("/login"))
assert "data-theme-btn" in p0 and "sombre.css" in p0 and "theme.js" in p0
for f in ("sombre.css", "theme.js"):
    ok(c.get("/static/" + f))
css = txt(c.get("/static/sombre.css"))
assert "@media screen" in css and "prefers-color-scheme:dark" in css
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
p1 = txt(c.get("/"))
assert "data-theme-btn" in p1 and "Tableau de bord" in p1
with app.app_context():
    ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM2 A','CM2',10000,?)", (_q("SELECT MIN(id) i FROM ecoles", un=True)["i"],))
    cid = q("SELECT id FROM classes WHERE nom='CM2 A'", un=True)["id"]
    for i in range(3):
        ex("INSERT INTO eleves (nom, prenoms, sexe, classe_id, statut, matricule, date_inscription, annee) VALUES (?,?,?,?,?,?,?,?)",
           (f"ELEVE{i}", "Test", "F" if i else "M", cid, "inscrit", f"M2430{i}", "2026-10-01", "2026-2027"))
p2 = txt(c.get("/"))
assert "Effectifs par classe" in p2 and "CM2 A" in p2, p2[:300]
if ED == "privee":
    assert "Encaissements mensuels" in p2
else:
    assert "Encaissements mensuels" not in p2
import m_graphiques_accueil as G
assert G.mois_annee("2026-2027")[0][1] == "Sept" and G.mois_annee("2026-2027")[4][0] == "2027-01"
assert G.barres([("a", 0), ("b", 0)])[0][2] == 0 and G.barres([("a", 5), ("b", 10)])[0][2] == 60.0
for u in ("/classes", "/eleves", "/communication"):
    ok(c.get(u))
print("OK", ED)
'''


def lancer(edition):
    env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_SCRIPT=edition)
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)


class Parcours(unittest.TestCase):
    def _edition(self, ed):
        r = lancer(ed)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3500:])
        self.assertIn("OK " + ed, r.stdout)

    def test_edition_privee(self):
        self._edition("privee")

    def test_edition_publique(self):
        self._edition("publique")


if __name__ == "__main__":
    unittest.main()
