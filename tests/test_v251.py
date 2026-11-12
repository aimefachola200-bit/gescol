# -*- coding: utf-8 -*-
"""Tests 2.5.1 : budget prévisionnel et compte rendu d'exécution (Finances)."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")
import m_budget_ecole as B  # noqa: E402

SCRIPT = r'''
import html, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex as _ex
app.config["TESTING"] = True
with app.app_context():
    _ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client(); c.get("/login")
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
with app.app_context():
    _ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
r = c.get("/budget-previsionnel"); assert r.status_code == 200, r.status_code
d = {"vue": "saisie", "p_R_I-1-1": "10 000", "p_R_I-2": "500000", "p_D_II-1": "300000", "p_D_V-3": "210000", "e_D_II-1": "150000"}
assert c.post("/budget-previsionnel", data=d).status_code == 302
t = html.unescape(c.get("/budget-previsionnel?vue=previsionnel").data.decode())
assert "510 000" in t and "cinq cent dix mille" in t and "BUDGET PRÉVISIONNEL" in t
t = html.unescape(c.get("/budget-previsionnel?vue=compte-rendu").data.decode())
assert "150 000" in t and "50.0 %" in t, t[-1500:]
for ext in ("pdf", "docx"):
    r = c.get("/exporter." + ext + "?page=/budget-previsionnel%3Fvue%3Dprevisionnel")
    assert r.status_code == 200 and r.data[:2] in (b"%P", b"PK"), (ext, r.status_code, r.data[:200])
print("OK")
'''


class T(unittest.TestCase):
    def test_lettres(self):
        for n, s in ((0, "zéro"), (80, "quatre-vingts"), (510000, "cinq cent dix mille"), (1250000, "un million deux cent cinquante mille"),
                     (71, "soixante et onze"), (200, "deux cents")):
            self.assertEqual(B.en_lettres(n), s)

    def test_totaux(self):
        par, tot = B.totaux({"I-1-1": 10, "I-1-2": 5, "I-2": 100}, "R")
        self.assertEqual(tot, 115)

    def test_page(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, **{PREFIXE + "_EDITION": "public"})
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True)
        self.assertIn("OK", r.stdout, r.stderr[-2500:])


if __name__ == "__main__":
    unittest.main()
