# -*- coding: utf-8 -*-
"""Tests 2.4.2 : « Par classe » du module Préparation de classe (m_prep_classes), de la maternelle au CM2.
Lancer : python3 -m unittest tests.test_v242"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")

import m_prep_classes as PC  # noqa: E402
import m_preparation as MP  # noqa: E402


class Contenus(unittest.TestCase):
    def test_chaque_cours_a_un_dossier(self):
        for c in MP.COURS:
            t = PC.contenus_du_cours(c)
            self.assertEqual(set(t), {"fiches", "resumes", "evaluations", "guides", "programmes"})
            self.assertTrue(all(f["cours"] == c for f in t["fiches"]))
            self.assertTrue(all(r["cours"] == c for r in t["resumes"]))

    def test_fiches_cm2_par_matiere(self):
        t = PC.contenus_du_cours("CM2", "maths")
        self.assertTrue(t["fiches"] and all(f["matiere"] == "maths" for f in t["fiches"]))
        self.assertTrue(t["evaluations"] and all(e["matiere"] == "maths" for e in t["evaluations"]))

    def test_evaluations_ci_cm2_seulement(self):
        self.assertEqual(PC.contenus_du_cours("MAT")["evaluations"], [])
        self.assertTrue(PC.contenus_du_cours("CP")["evaluations"])

    def test_recherche_et_groupes(self):
        tout = PC.contenus_du_cours("CE1", "maths")["fiches"]
        mot = tout[0]["titre"].split()[0]
        trouve = PC.contenus_du_cours("CE1", "maths", mot)["fiches"]
        self.assertTrue(trouve and len(trouve) <= len(tout))
        self.assertEqual(PC.contenus_du_cours("CE1", "maths", "zzqxwv")["fiches"], [])
        self.assertEqual(sum(len(fs) for _k, fs in PC.grouper_fiches(tout)), len(tout))


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
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
page = txt(c.get("/preparation/classes"))
for lib in ("Maternelle", "CI", "CP", "CE1", "CE2", "CM1", "CM2"):
    assert lib in page, lib
assert "Par classe" in page
for cours in ("MAT", "CI", "CP", "CE1", "CE2", "CM1", "CM2"):
    p = txt(c.get(f"/preparation/classes/{cours}"))
    assert "Fiches de préparation" in p and "Résumés" in p and "Guides pédagogiques" in p, cours
    assert "Évaluations et épreuves" in p and "Programmes et progressions" in p, cours
ok(c.get("/preparation/classes/XX"), 404)
p = txt(c.get("/preparation/classes/CM2?matiere=maths"))
assert "Mathématiques" in p or "Mathématique" in p, p[:500]
p = txt(c.get("/preparation/classes/CM2?q=zzqxwv"))
assert "Aucune fiche pour ce choix" in p
# les liens de la page mènent à des pages valides
import re
liens = set(re.findall(r'href="(/preparation/(?:fiches|resumes|guides|programmes)/[^"#?]+)"', txt(c.get("/preparation/classes/CP"))))
assert liens
for u in sorted(liens)[:12]:
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
