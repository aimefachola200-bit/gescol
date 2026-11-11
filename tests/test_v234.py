# -*- coding: utf-8 -*-
"""Tests 2.3.4 : « Télécharger PDF / Word » d'une page en application de circonscription ou de DDEMP.
Sans école ouverte, l'adresse /exporter.pdf était prise pour une page de module d'école et renvoyait la page HTML
« Choisissez une école » au lieu du fichier, pour les comptes CP, chef de division, directeur et enseignant.
Le tableau de bord du pilotage échouait (« 'int' object has no attribute 'get' ») quand une école transmettait ses salles
sous forme de nombre (« salles_classe »: 6), comme dans les données d'exemple de la circonscription.
Lancer : python3 -m unittest tests.test_v234"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "GESCOL"

SCRIPT = r'''
import os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
roles = ("cp", "chef_service", "directeur")
with app.app_context():
    for r in roles:
        ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif) VALUES (?,?,?,?,0,1)",
           (r + "1", r.upper(), r, generate_password_hash("Mdp-test-2026")))
for r in roles:
    c = app.test_client()
    assert c.post("/login", data={"identifiant": r + "1", "mdp": "Mdp-test-2026"}).status_code == 302, r
    for page in ("/pilotage", "/juridiction/tableau-de-bord", "/sport"):
        for fmt, magie in (("pdf", b"%PDF"), ("docx", b"PK")):
            x = c.get("/exporter.%s?page=%s" % (fmt, page))
            assert x.status_code == 200, (r, page, fmt, x.status_code)
            assert x.data.startswith(magie), (r, page, fmt, x.mimetype)
print("OK", ED)
'''


class TestExportJuridiction(unittest.TestCase):
    def test_export_sans_ecole_ouverte(self):
        for ed in ("cs", "ddemp"):
            with self.subTest(edition=ed):
                env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_SCRIPT=ed)
                r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)
                self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
                self.assertIn("OK", r.stdout)


DEMO = r'''
import os, subprocess, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
D = tempfile.mkdtemp()
os.environ.update({P + "_EDITION": ED, P + "_DATA": D, P + "_SANS_PRECHARGEMENT": "1"})
subprocess.run([sys.executable, "demo_juridiction.py"], check=True, stdout=subprocess.DEVNULL)
sys.path.insert(0, os.getcwd())
from app import app
app.config["TESTING"] = True
c = app.test_client()
assert c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"}).status_code == 302
for u in ("/pilotage", "/pilotage?par=zone", "/exporter.pdf?page=/pilotage"):
    r = c.get(u)
    assert r.status_code == 200, (u, r.status_code)
print("OK", ED)
'''


class TestPilotageDemo(unittest.TestCase):
    def test_pilotage_salles_en_nombre(self):
        for ed in ("cs", "ddemp"):
            with self.subTest(edition=ed):
                env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_SCRIPT=ed)
                r = subprocess.run([sys.executable, "-c", DEMO], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)
                self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
