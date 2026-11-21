# -*- coding: utf-8 -*-
"""Tests 2.8 : cahier de matériel (enseignant, école, mouvements, besoins et dotations) — éditions école et CS.
Lancer : python3 -m unittest tests.test_v280"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "SCOLARIS" if os.path.exists(os.path.join(RACINE, "SCOLARIS_LISEZMOI.md")) or "scolaris" in RACINE.lower() else "GESCOL"

SCRIPT = r'''
import html, io, os, re, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-1500:]); return r
def txt(r): return html.unescape(r.data.decode())
S = config.ANNEE_ACTIVE
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
JUR = config.EDITION in ("cs", "ddemp")
if JUR:
    with app.app_context():
        ex("INSERT OR REPLACE INTO jur_structure (id, niveau, departement, cs, nom) VALUES (1, ?, 'Plateau', 'Pobè', 'CS Pobè')", (config.EDITION,))
        cs = ex("INSERT INTO jur_cs (departement, nom) VALUES ('Plateau', 'Pobè')")
        zid = ex("INSERT INTO jur_zones (cs_id, nom, ordre) VALUES (?, 'Zone 1', 1)", (cs,))
        ex("INSERT INTO jur_ecoles (cs_id, zone_id, code, nom, type, secteur, actif) VALUES (?,?,?,?,?,?,1)", (cs, zid, "E1", "EPP Towé", "EP", "public"))
if not JUR:
    assert "Cahier de matériel" in txt(ok(c.get("/"))), "menu"
ok(c.get("/cahier-materiel"), 200 if JUR else 302)
if not JUR:
    ok(c.post(f"/reg/materiel/inventaire/0?annee={S}", data={"niveau": "ECOLE", "entite": "Mon école", "designation": "Boîte de solides", "categorie": "Matériel de mathématiques (compas, équerres, boulier, solides)",
              "quantite": "6", "etat": "Bon", "source": "APE", "valeur": "30000", "localisation": "Magasin"}), 302)
    ok(c.post(f"/reg/materiel/inventaire/0?annee={S}", data={"niveau": "ECOLE", "entite": "Mon école", "designation": "Ballons", "categorie": "Matériel sportif (EPS)",
              "quantite": "4", "etat": "Usé", "valeur": "20000", "localisation": "Salle 1"}), 302)
    t = txt(ok(c.get(f"/reg/materiel/inventaire?annee={S}")))
    assert "Boîte de solides" in t and "Ballons" in t and "50 000" in t.replace(" ", " ").replace("\xa0", " "), t[-1500:]
    ok(c.post(f"/reg/materiel/enseignant/0?annee={S}", data={"niveau": "ECOLE", "entite": "Mon école", "date": "2026-11-10", "classe": "CM1", "discipline": "Mathématiques", "sa": "2", "seance": "3",
              "lecon": "Les solides", "materiel": "Boîte de solides, règle", "dispo": "Partiellement disponible", "renouveler": "Règles"}), 302)
    assert "Les solides" in txt(ok(c.get(f"/reg/materiel/enseignant?annee={S}&classe=CM1")))
    ok(c.post(f"/reg/materiel/mouvements/0?annee={S}", data={"niveau": "ECOLE", "entite": "Mon école", "date": "2026-11-11", "designation": "Ballons", "mouvement": "Décharge à un enseignant",
              "quantite": "2", "beneficiaire": "M. KOUDJO"}), 302)
    assert "KOUDJO" in txt(ok(c.get(f"/reg/materiel/mouvements?annee={S}")))
    ok(c.get(f"/reg/materiel/inventaire.xlsx?annee={S}"))
    assert ok(c.get(f"/reg/materiel/inventaire.pdf?annee={S}")).mimetype == "application/pdf"
for rc in (("dotations",) if JUR else ("enseignant", "inventaire", "mouvements", "dotations")):   # la CS / DDEMP ouvre une école pour ses registres d'école
    ok(c.get(f"/reg/materiel/{rc}?annee={S}"))
ok(c.post(f"/reg/materiel/dotations/0?annee={S}", data={"niveau": "CS" if JUR else "ECOLE", "entite": "x", "date": "2026-11-12", "designation": "Tables-bancs", "demande": "30", "recue": "10", "statut": "Livré en partie"}), 302)
t = txt(ok(c.get(f"/reg/materiel/dotations?annee={S}")))
assert "Tables-bancs" in t and "20" in t
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("GESCOL_EDITION", "GESCOL_DATA", "SCOLARIS_EDITION", "SCOLARIS_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestCahierMateriel(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_cs(self):
        self.verifier("cs")
