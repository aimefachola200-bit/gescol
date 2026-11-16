# -*- coding: utf-8 -*-
"""Purge du vocabulaire du primaire dans les éditions du secondaire (sec_privee) : aucune page courante ne doit
afficher maître, maternelle, CI-CM2, CEP, MEMP, UP, CCS, jumelée, multigrade…
Les textes des épreuves et les ressources documentaires (contenu d'auteur) sont exclus."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import os, re, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "sec_privee"
sys.path.insert(0, os.getcwd())
from app import app, ex
app.config["TESTING"] = True
c = app.test_client(); c.get("/login"); c.post("/login", data={"identifiant": "admin", "mdp": "admin123"})
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
BAD = re.compile(r"\b(?:EPP|CEP|MEMP|CCS|CM1|CM2|CE1|CE2)\b|[Mm]aternelle|jumelée|multigrade|[Ii]nstituteur|[Éé]coles? primaires?|[Mm]aîtresse|[Mm]aître(?! Aimé)")
pages = ["/", "/classes", "/classes/nouvelle", "/matieres", "/ecoles/nouvelle", "/visites", "/docs-enseignant", "/partage",
         "/textes-officiels", "/rapports", "/aide/guide", "/acteurs-etablissement", "/patrimoine/mobilier", "/uascep"]
mauvais = []
for u in pages:
    r = c.get(u, follow_redirects=True)
    if r.status_code != 200:
        continue
    h = re.sub(r"<(script|style)\b.*?</\1>|<!--.*?-->", " ", r.get_data(as_text=True), flags=re.S)
    t = re.sub(r"<[^>]+>", "\n", h)
    for l in t.split("\n"):
        for m in BAD.finditer(l):
            mauvais.append((u, l.strip()[:90]))
for u in ("/preparation", "/synoptique", "/themes-up"):
    r = c.get(u)
    assert r.status_code == 302, u
assert not mauvais, mauvais[:12]
print("OK")
'''


class T(unittest.TestCase):
    def test_plus_de_primaire_dans_le_secondaire(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True)
        self.assertIn("OK", r.stdout, (r.stdout + r.stderr)[-1500:])


if __name__ == "__main__":
    unittest.main()
