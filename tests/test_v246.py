# -*- coding: utf-8 -*-
"""Tests 2.4.6 : bouton « Cachets » (masquer les cachets dans les PDF).
Lancer : python3 -m unittest tests.test_v246"""
import io
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import io, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex as _ex
import cachet, pdfs
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
app.config["TESTING"] = True

def pdf(url=""):
    tampon = io.BytesIO(); c = canvas.Canvas(tampon, pageCompression=0)
    cachet.dessiner(c, 100, 100, 40, "MINISTERE", "ECOLE", "DIRECTION", "bleu")
    h = cachet.dessiner_nom(c, 300, 300, ["Le Directeur", "Jean"], "bleu", 150)
    c.showPage(); c.save()
    return len(tampon.getvalue()), h

with app.test_request_context("/"):
    avec, h1 = pdf()
with app.test_request_context("/", headers={"Cookie": "sans_cachet=1"}):
    sans, h2 = pdf()
    assert pdfs.cachet_ecole(canvas.Canvas(io.BytesIO()), 10, 10) is False
with app.test_request_context("/?sans_cachet=1"):
    sans2, _ = pdf()
assert avec > sans + 500, (avec, sans)
assert sans == sans2, (sans, sans2)
assert h1 > 0 and h2 == 0, (h1, h2)
assert pdf()[0] == avec            # hors requête : on dessine
with app.app_context():
    _ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
page = c.get("/mon-compte", follow_redirects=True).data.decode()
assert "cachets.js" in page and "data-theme-btn" in page
r = c.get("/static/cachets.js"); assert r.status_code == 200 and b"sans_cachet" in r.data
print("OK")
'''


class Cachets(unittest.TestCase):
    def test_masquage(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3000:])
        self.assertIn("OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
