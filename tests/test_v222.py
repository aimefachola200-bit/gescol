# -*- coding: utf-8 -*-
"""Tests 2.2.2 : une fiche de préparation ne dépasse jamais deux pages (une feuille recto verso).
(1) les 150 fiches les plus longues du corpus sont rendues en PDF : au plus 2 pages chacune
    (cascade : 14 pt sur 1 page ; planification p. 1 / déroulement p. 2 de 14 à 12 pt ; déroulement dès la page 1
    jusqu'à 10 pt ; déroulement resserré jusqu'à 9 pt) ;
(2) fiches abîmées du guide CP 2022 allégées : plus de bloc « éléments de planification » dans les préliminaires,
    plus de semaine d'intégration suivante en fin de fiche, plus de déroulement recopié dans les stratégies.
Lancer : python3 -m unittest tests.test_v222"""
import gzip
import json
import os
import re
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
from app import app, ex
from werkzeug.security import generate_password_hash
import pypdf
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
import m_preparation as MP
def poids(f):
    return sum(len(str(v or "")) for k, v in f.items() if k != "deroulement") + \
        sum(len(str(z)) for l in f.get("deroulement") or [] for z in (l if isinstance(l, list) else [l]))
lourdes = sorted(MP.corpus()["fiches"], key=poids, reverse=True)[:int(sys.argv[1])]
trop = []
for f in lourdes:
    r = c.get(f"/preparation/fiches/{f['id']}.pdf")
    assert r.status_code == 200, f["id"]
    n = len(pypdf.PdfReader(io.BytesIO(r.data)).pages)
    if n > 2:
        trop.append((f["id"], n))
assert not trop, trop
assert not MP.FICHES_DEBORDANTES, MP.FICHES_DEBORDANTES
print("OK-222", len(lourdes))
'''


class TestFichesDeuxPages222(unittest.TestCase):
    def test_150_fiches_les_plus_longues_sur_deux_pages(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", SCRIPT, "150"], cwd=RACINE, env=env, capture_output=True, text=True,
                           timeout=5400)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK-222", r.stdout)

    def test_fiches_cp_allegees(self):
        c = json.load(gzip.open(os.path.join(RACINE, "static", "pedafiche_corpus.json.gz")))
        planif, suite, colle = [], [], []
        for f in c["fiches"]:
            d = [l for l in f.get("deroulement") or [] if isinstance(l, list) and len(l) > 1]
            if d and re.search(r"(?m)^\s*\d\.\s*Calcul mental", d[0][1]) and \
                    re.search(r"[ÉE]L[ÉE]MENTS DE PLANIFICATION|Objectifs de la s[ée]quence", d[0][1]):
                planif.append(f["id"])
            if d and re.search(r"\n\s*SA couvertes\s*:", d[-1][1][150:]):
                suite.append(f["id"])
            if re.search(r"(?:Nous faisons|Tu fais)\s*[|\[A-Z]|Objectifs de la s[ée]quence", f.get("strategies") or ""):
                colle.append(f["id"])
        self.assertEqual(planif, [])
        self.assertEqual(suite, [])
        self.assertEqual(colle, [])


if __name__ == "__main__":
    unittest.main()
