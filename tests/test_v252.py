# -*- coding: utf-8 -*-
"""Tests : schémas et cartes, fiches pédagogiques du secondaire, insignes des applications."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")
import insignes as I  # noqa: E402
import schemas as S  # noqa: E402

SCRIPT = r'''
import html, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
import config
from app import app, ex
app.config["TESTING"] = True
with app.app_context(): ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client(); c.get("/login")
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
with app.app_context(): ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
cle = os.environ["CLE_ATTENDUE"]
r = c.get("/schemas"); assert r.status_code == 200
assert b"insigne-" in r.data and ("icons/insignes/" + cle + "-icon-192.png").encode() in r.data, cle
assert c.get("/schemas/carte-departements").status_code == (200 if not config.secondaire() or True else 404)
r = c.get("/manifest.webmanifest"); assert ("insignes/" + cle + "-icon-512.png").encode() in r.data
if config.secondaire():
    assert c.get("/schemas/carte-departements").status_code == 200 and c.get("/schemas/plante").status_code == 404
    assert c.get("/ressources-secondaire?vue=fiches").status_code == 200
    assert c.get("/ressources-secondaire/fiche/0").status_code == 200
    r = c.get("/ressources-secondaire?vue=apc"); assert r.status_code == 200 and r.data.count(b"Corrig") >= 24
    r = c.get("/ressources-secondaire/apc/0?corrige=1"); assert r.status_code == 200 and b"15,15" in r.data
    assert c.get("/exporter.pdf?page=/ressources-secondaire/apc/5%3Fcorrige%3D1").data[:2] == b"%P"
else:
    assert c.get("/schemas/plante").status_code == 200 and c.get("/schemas/cellules").status_code == 404
print("OK")
'''


class T(unittest.TestCase):
    def test_svg_valides(self):
        import xml.dom.minidom as M
        self.assertGreaterEqual(len(S.SCHEMAS), 20)
        ids = set()
        for sid, titre, cycle, mat, leg, f in S.SCHEMAS:
            self.assertNotIn(sid, ids); ids.add(sid)
            M.parseString(f())            # XML bien formé
        self.assertTrue(any(s[0].startswith("carte-") for s in S.SCHEMAS))

    def test_epreuves_apc(self):
        import epreuves_apc as A
        self.assertEqual(len(A.EPREUVES), 94)
        for e in A.EPREUVES:
            self.assertEqual(e["total"], 20, (e["matiere"], e["niveau"]))
            self.assertGreaterEqual(len(e["items"]), 4)
        self.assertEqual({e["niveau"] for e in A.EPREUVES}, {"6e", "5e", "4e", "3e", "Tle"})

    def test_insignes_et_fichiers(self):
        for cle in I.INSIGNES:
            for nom in I.TAILLES:
                self.assertTrue(os.path.exists(os.path.join(RACINE, "static", "icons", "insignes", f"{cle}-{nom}.png")), cle)
            self.assertTrue(os.path.exists(os.path.join(RACINE, "static", "icons", "insignes", f"{cle}.ico")), cle)
        self.assertEqual(len({v[:2] + (v[2],) for v in I.INSIGNES.values()}), len(I.INSIGNES))  # tous distincts

    def _lancer(self, edition, cle):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, CLE_ATTENDUE=cle, **{PREFIXE + "_EDITION": edition})
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True)
        self.assertIn("OK", r.stdout, r.stderr[-2500:])

    def test_primaire_publique(self):
        self._lancer("publique", "publique")

    def test_secondaire_privee(self):
        self._lancer("sec_privee", "sec_privee")


if __name__ == "__main__":
    unittest.main()
