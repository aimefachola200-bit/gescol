# -*- coding: utf-8 -*-
"""Tests 2.4.5 : applications jumelles du secondaire (sec_privee, sec_publique).
Lancer : python3 -m unittest tests.test_v245"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import html, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
import config
from app import app, ex as _ex, q as _q
app.config["TESTING"] = True
sec = ED.startswith("sec_")
secteur = ED[4:] if sec else ED
assert config.SECONDAIRE == sec, config.SECONDAIRE
assert config.EDITION == secteur, (config.EDITION, secteur)
assert config.publique() == (secteur == "publique")
if sec:
    assert "Secondaire" in config.NOMS_APPLI[config.EDITION], config.NOMS_APPLI
    assert (" Public" in config.NOMS_APPLI[config.EDITION]) == (secteur == "publique")
    ports = {v for k, v in config.PORTS.items() if k not in (secteur,)}
    assert config.PORTS[secteur] not in ports, config.PORTS
    assert "Secondaire" in config.DOSSIERS[secteur], config.DOSSIERS
def txt(r):
    assert r.status_code == 200, (r.request.path, r.status_code, r.data[-800:])
    return html.unescape(r.data.decode())
with app.app_context():
    _ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
form = txt(c.get("/classes/nouvelle")) if c.get("/classes/nouvelle").status_code == 200 else txt(c.get("/classes"))
if sec:
    assert "6ème" in form or "Tle" in form or "Terminale" in form, form[-600:]
    assert "CM2" not in form and "Maternelle" not in form, "niveaux primaire/maternelle visibles"
    r = c.post("/classes/nouvelle", data={"nom": "CE1 A", "niveau": "CE1", "frais_scolarite": "0"})
    with app.app_context():
        assert _q("SELECT COUNT(*) n FROM classes WHERE niveau='CE1'", un=True)["n"] == 0, "CE1 accepté"
    home = txt(c.get("/"))
    assert "/cep" not in home and "/preparation" not in home, [home[max(0, home.find(k) - 150):home.find(k) + 40] for k in ("/cep", "/preparation") if k in home]
else:
    assert "CM2" in form
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

    def test_secondaire_prive(self):
        self._edition("sec_privee")

    def test_secondaire_public(self):
        self._edition("sec_publique")

    def test_editions_de_base_inchangees(self):
        self._edition("privee")
        self._edition("publique")


if __name__ == "__main__":
    unittest.main()
