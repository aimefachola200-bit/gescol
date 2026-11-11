# -*- coding: utf-8 -*-
"""Tests de la version 1.11 : saisie manuelle (CS / DDEMP) des fiches officielles des écoles, de l'état nominatif du
personnel et des directeurs, sans import Excel ni transmission. Lancer : python3 -m unittest tests.test_v111"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"


def lancer(script, edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


SCRIPT = r'''
import html, json, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config, demo_juridiction
from app import app, q, ex
app.config["TESTING"] = True
demo_juridiction.main()
import m_juridiction as J, m_rapports as MRA
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.data[-2500:]); return r
def txt(r): return html.unescape(r.data.decode())
with app.app_context():
    a = J.annee()
    e = q("SELECT * FROM jur_ecoles WHERE type='EP' ORDER BY id", un=True)
    m = q("SELECT * FROM jur_ecoles WHERE type IN ('EM','EE') ORDER BY id", un=True)
    ex("DELETE FROM jur_sections WHERE ecole_id=?", (e["id"],))
c = app.test_client(); ok(c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"}), 302)
t = txt(ok(c.get("/juridiction/saisie")))
assert "Saisie manuelle des fiches et du personnel" in t and e["nom"] in t and "Saisir les noms" in t
assert "Saisie manuelle (sans Excel)" in txt(ok(c.get("/juridiction/tableau-de-bord")))   # menu
# 1. fiche de recensement du primaire saisie à la main
t = txt(ok(c.get(f"/juridiction/saisie/{e['id']}/recensement-primaire")))
assert "Saisie manuelle" in t and e["nom"] in t and "Importer depuis Excel" not in t
r = ok(c.post(f"/juridiction/saisie/{e['id']}/recensement-primaire?annee={a}", json={"annee": a, "valeurs": {"point_eau": "Oui", "t631.fr.ci": "9"}}))
assert r.get_json()["ok"], r.get_json()
with app.app_context():
    s = J.section(e["id"], "recensement", a)
    assert s["primaire"]["source"] == "saisie" and s["primaire"]["valeurs"]["t631.fr.ci"] in ("9", 9), s
r = ok(c.get(f"/juridiction/fiches/{e['id']}/recensement-primaire.pdf?annee={a}")); assert r.data[:4] == b"%PDF"
t = txt(ok(c.get(f"/juridiction/saisie?annee={a}")))
assert "saisie" in t
# 2. rapport de rentrée : formulaire officiel, enregistrement, PDF
t = txt(ok(c.get(f"/juridiction/saisie/{e['id']}/rentree-ep?annee={a}")))
assert "Saisie manuelle" in t and "Téléverser" not in t
assert 'value="' + e["nom"] + '"' in t, "identification pré-remplie"
champs = [k for k, sp in MRA.champs_editables("rentree-ep", 3)]
form = {"action": "sauver", "pers_n": "3", "classes_ouvertes": "6", "pers.1.nom": "AGBO Rose"}
assert "classes_ouvertes" in champs and "pers.1.nom" in champs, champs[:40]
ok(c.post(f"/juridiction/saisie/{e['id']}/rentree-ep?annee={a}", data=form), 302)
with app.app_context():
    v = J.section(e["id"], "rapports", a)["rentree-ep"]
    assert v["source"] == "saisie" and v["valeurs"]["classes_ouvertes"] in ("6", 6) and v["valeurs"]["pers.1.nom"] == "AGBO Rose", v
r = ok(c.get(f"/juridiction/fiches/{e['id']}/rentree-ep.pdf?annee={a}")); assert r.data[:4] == b"%PDF"
ok(c.get(f"/juridiction/saisie/{m['id']}/fin-em?annee={a}"))
ok(c.get(f"/juridiction/saisie/{m['id']}/recensement-maternelle?annee={a}"))
t = txt(ok(c.get(f"/juridiction/fiches?annee={a}")))
assert "Saisie manuelle" in t
# 3. état nominatif du personnel : directeur, adjoint, administratif
t = txt(ok(c.get(f"/juridiction/saisie/{e['id']}/personnel?annee={a}")))
assert "État nominatif du personnel" in t
data = {"annee": a, "n": "3", "nom_0": "HOUNKPE", "prenoms_0": "Jean", "sexe_0": "M", "fonction_0": "Directeur / directrice", "categorie_0": "FE", "grade_0": "B1-6",
        "date_naissance_0": "1970-05-12", "date_premiere_ps_0": "1995-10-01", "telephone_0": "0197000000",
        "nom_1": "AZON", "prenoms_1": "Marie", "sexe_1": "F", "fonction_1": "Adjoint(e)", "categorie_1": "ACDPE", "nom_2": "KOFFI", "prenoms_2": "Paul", "sexe_2": "M", "fonction_2": "Secrétaire"}
ok(c.post(f"/juridiction/saisie/{e['id']}/personnel", data=data), 302)
with app.app_context():
    p = J.section(e["id"], "personnel", a)
    assert [x["role"] for x in p] == ["directeur", "adjoint", "administratif"], p
    assert q("SELECT directeur_nom FROM jur_ecoles WHERE id=?", (e["id"],), un=True)["directeur_nom"] == "HOUNKPE Jean"
t = txt(ok(c.get("/juridiction/personnel?onglet=enseignants")))
assert "AZON" in t or "HOUNKPE" in t, "personnel saisi visible dans la gestion de carrière"
# 4. directeurs de toutes les écoles
t = txt(ok(c.get("/juridiction/saisie/directeurs")))
assert "Directeurs des écoles" in t
ok(c.post("/juridiction/saisie/directeurs", data={f"nom_{e['id']}": "SOSSOU Luc", f"titre_{e['id']}": "Le Directeur", f"tel_{e['id']}": "0190000000"}), 302)
with app.app_context():
    assert q("SELECT directeur_nom FROM jur_ecoles WHERE id=?", (e["id"],), un=True)["directeur_nom"] == "SOSSOU Luc"
print("OK-" + config.EDITION)
'''


class TestSaisie(unittest.TestCase):
    def test_cs(self):
        r = lancer(SCRIPT, "cs")
        self.assertIn("OK-cs", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_ddemp(self):
        r = lancer(SCRIPT, "ddemp")
        self.assertIn("OK-ddemp", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])


if __name__ == "__main__":
    unittest.main()
