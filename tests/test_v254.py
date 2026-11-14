# -*- coding: utf-8 -*-
"""Textes officiels (MEMP / MESTFP) embarqués : page accessible, PDF présents et valides."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client(); c.get("/login")
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
r = c.get("/textes-officiels"); assert r.status_code == 200, r.status_code; assert "progression des 70".encode() in r.data
for u in ("/cahier-cp-francais.pdf", "/cahier-cp-francais.pdf?corrige=1"):
    rr = c.get(u); assert rr.status_code == 200 and rr.data[:4] == b"%PDF" and len(rr.data) > 20000, (u, rr.status_code)
t = r.get_data(as_text=True); t2 = t
assert "BEPC" in t and "103" in t and "075" in t
assert "textes_officiels/arrete_bepc_2024.pdf" in t
a = c.get("/secretariat/archives"); assert a.status_code == 200 and "Textes officiels" in a.get_data(as_text=True)
r = c.get("/acteurs-etablissement"); assert r.status_code == 200 and "Censeur" in r.get_data(as_text=True)
r = c.get("/reperes-pedagogiques"); t = r.get_data(as_text=True); assert r.status_code == 200 and "Piaget" in t and "Freud" in t
r = c.get("/lectures-college"); assert r.status_code == 200 and "Climbi" in r.get_data(as_text=True)
r = c.get("/cahiers-langues"); assert r.status_code == 200 and "Allemand" in r.get_data(as_text=True)
for l in ("Français", "Anglais", "Allemand", "Espagnol"):
    for n in ("CE2", "6e", "3e") if l == "Français" else ("4e", "Tle"):
        for q in ("eleve", "enseignant"):
            r = c.get(f"/cahiers-langues/{l}/{n}/{q}.pdf"); assert r.status_code == 200 and r.data[:5] == b"%PDF-", (l, n, q)
r = c.get("/schemas-fournis"); assert r.status_code == 200 and "carte_01.jpg" in r.get_data(as_text=True)
assert "maths_cp.pdf" in t2 and "cahiers_des_charges_rap_2006" in t2
r = c.get("/poesies"); assert r.status_code == 200 and "Mon école" in r.get_data(as_text=True)
assert "annale_cm2_2017.pdf" in t2
print("OK")
'''


class TestTextes(unittest.TestCase):
    def test_pdf_presents(self):
        for f in ("arrete_075_2018.pdf", "arrete_103_2021.pdf", "arrete_bepc_2024.pdf", "cahiers_des_charges_rap_2006.pdf"):
            p = os.path.join(RACINE, "static", "textes_officiels", f)
            self.assertTrue(os.path.exists(p), f)
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(5), b"%PDF-")

    def test_pages(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True)
        self.assertIn("OK", r.stdout, r.stderr[-800:])


if __name__ == "__main__":
    unittest.main()
