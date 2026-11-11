# -*- coding: utf-8 -*-
"""Tests 2.2.1 : cases du déroulement lisibles et documents Word nommés .docx.
(1) aucune case du déroulement avec deux colonnes mêlées (sous-titres répétés, mots collés), lignes doublées ou texte
    coupé net en fin de case ; (2) Word : adresse et nom en .docx, anciens liens .doc redirigés.
Lancer : python3 -m unittest tests.test_v221"""
import gzip
import json
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import io, os, sys, tempfile, zipfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
import m_preparation as MP
f = MP.corpus()["fiche_par_id"].get("p10-b3b5508896a7") or MP.corpus()["fiches"][0]
r = c.get(f"/preparation/fiches/{f['id']}.doc")
assert r.status_code == 301 and r.location.endswith(".docx"), (r.status_code, r.location)
r = c.get(f"/preparation/fiches/{f['id']}.docx")
cd = r.headers.get("Content-Disposition", "")
assert r.status_code == 200 and ".docx" in cd and '.doc"' not in cd, cd
x = zipfile.ZipFile(io.BytesIO(r.data)).read("word/document.xml").decode("utf8")
assert "alcoolisCite" not in x and "GOHITO" not in x.upper()
h = c.get("/preparation/fiches?cours=CE2&matiere=maths").data.decode()
assert ".docx" in h and '.doc"' not in h
print("OK-221")
'''


class TestDeroulementWord221(unittest.TestCase):
    def test_cases_lisibles(self):
        sys.path.insert(0, RACINE)
        import m_preparation as MP
        nom = [n for n in os.listdir(os.path.join(RACINE, "static")) if n.startswith("pedafiche_corpus")][0]
        c = json.load(gzip.open(os.path.join(RACINE, "static", nom), "rt", encoding="utf-8"))
        mauvais = []
        for f in c["fiches"]:
            for ligne in f.get("deroulement") or []:
                for k, t in enumerate(ligne):
                    if k and isinstance(t, str) and (MP.case_illisible(t) or MP.fin_coupee(t) or MP.lignes_doublees(t)):
                        mauvais.append(f["id"])
        self.assertEqual(mauvais, [], mauvais[:10])

    def test_word_docx(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
        self.assertIn("OK-221", r.stdout)


if __name__ == "__main__":
    unittest.main()
