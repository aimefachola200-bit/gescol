# -*- coding: utf-8 -*-
"""Tests 2.1.1 : l'application Android autonome s'ouvre.
Dans l'APK, la fabrication Android retire l'extension « .gz » : le corpus pédagogique devient
static/pedafiche_corpus.json (non compressé). En 2.1.0 il n'était plus trouvé et toutes les pages, connexion
comprise, affichaient « Une erreur est survenue ». On vérifie : (1) corpus sous forme .json non compressée,
chargé en entier ; (2) corpus absent : la connexion et la préparation s'ouvrent quand même.
Lancer : python3 -m unittest tests.test_v211"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import gzip, os, shutil, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]; MODE = os.environ["MODE_SCRIPT"]
racine = os.getcwd()
web = tempfile.mkdtemp()
shutil.copytree(os.path.join(racine, "templates"), os.path.join(web, "templates"))
shutil.copytree(os.path.join(racine, "static"), os.path.join(web, "static"),
                ignore=shutil.ignore_patterns("pedafiche_corpus.json.gz"))
if MODE == "json":      # ce que produit la fabrication de l'APK
    with gzip.open(os.path.join(racine, "static", "pedafiche_corpus.json.gz"), "rb") as f, \
            open(os.path.join(web, "static", "pedafiche_corpus.json"), "wb") as g:
        shutil.copyfileobj(f, g)
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp()
os.environ[P + "_WEB_DIR"] = web; os.environ[P + "_AUTONOME"] = "1"
os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
os.chdir(tempfile.mkdtemp())
sys.path.insert(0, racine)
import config
assert config.WEB_DIR == web
# hors APK, le code cherche aussi static/ à côté des modules : on ne garde que le dossier web simulé
import pdfs
_orig = pdfs.fichier_static
_cache = {"pedafiche_corpus.json.gz": None,
          "pedafiche_corpus.json": os.path.join(web, "static", "pedafiche_corpus.json") if MODE == "json" else None}
pdfs.fichier_static = lambda nom: _cache[nom] if nom in _cache else _orig(nom)
from app import app, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
c = app.test_client()
for u in ("/", "/login"):
    r = c.get(u, follow_redirects=True)
    assert r.status_code == 200, (u, r.status_code)
    assert b'type="password"' in r.data, u
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
for u in ("/", "/preparation", "/preparation/programmes", "/preparation/fiches", "/preparation/resumes"):
    r = c.get(u, follow_redirects=True)
    assert r.status_code == 200, (u, r.status_code)
import m_preparation as MP
n = len(MP.corpus()["fiches"])
if MODE == "json":
    assert n > 1000, n
else:
    assert n == 0, n
print("OK", ED, MODE, n)
'''


class TestApkCorpus(unittest.TestCase):
    def lancer(self, edition, mode):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_SCRIPT=edition, MODE_SCRIPT=mode)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
        self.assertIn("OK", r.stdout)

    def test_corpus_non_compresse(self):
        for ed in ("privee", "publique"):
            with self.subTest(edition=ed):
                self.lancer(ed, "json")

    def test_corpus_absent(self):
        self.lancer("publique", "absent")


if __name__ == "__main__":
    unittest.main()
