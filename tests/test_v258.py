# -*- coding: utf-8 -*-
"""Onglet Téléchargements : budget prévisionnel et compte rendu en PDF et en Word (écoles publiques) ; absents du secondaire."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
SCRIPT = r'''
import os, re, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "publique"
sys.path.insert(0, os.getcwd())
from app import app, ex
app.config["TESTING"] = True
c = app.test_client(); c.get("/login"); c.post("/login", data={"identifiant": "admin", "mdp": "admin123"})
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
h = c.get("/telechargements").get_data(as_text=True)
assert "Budget prévisionnel" in h and "Compte rendu d" in h
liens = [u.replace("&amp;", "&") for u in re.findall(r'href="(/exporter\.[^"]+)"', h)]
assert len(liens) >= 4
for u in liens[:4]:
    r = c.get(u)
    assert r.status_code == 200 and len(r.data) > 1000, u
    assert r.data[:4] in (b"%PDF", b"PK\x03\x04"), u
import subprocess
print("OK")
'''


class T(unittest.TestCase):
    def test_telechargements(self):
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=dict(os.environ, PREFIXE_SCRIPT=PREFIXE), capture_output=True, text=True)
        self.assertIn("OK", r.stdout, (r.stdout + r.stderr)[-1500:])


if __name__ == "__main__":
    unittest.main()
