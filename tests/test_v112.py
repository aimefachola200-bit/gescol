# -*- coding: utf-8 -*-
"""Tests de la version 1.12 : bouton « ← Retour », mot de passe oublié (question de secours, demande à
l'administrateur), œil sur les mots de passe. Lancer : python3 -m unittest tests.test_v112"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"


def lancer(script, edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)


SCRIPT = r'''
import html, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
if config.juridiction():
    import demo_juridiction; demo_juridiction.main()
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif) VALUES ('agnes','AGNES Test','secretaire',?,0,1)",
       (generate_password_hash("ancien-mdp1"),))
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.data[-1500:]); return r
def txt(r): return html.unescape(r.data.decode())
c = app.test_client()
assert "Mot de passe oublié" in txt(ok(c.get("/login")))
# 1. question de secours définie dans « Mon compte »
ok(c.post("/login", data={"identifiant": "agnes", "mdp": "ancien-mdp1"}), 302)
t = txt(ok(c.get("/mon-compte")))
assert "Question de secours" in t and "← Retour" in t
ok(c.post("/mon-compte/secours", data={"mdp": "faux", "question": "Ville ou village de naissance", "reponse": "Pobè"}), 302)
with app.app_context():
    assert not q("SELECT 1 FROM mdp_secours", un=True)
ok(c.post("/mon-compte/secours", data={"mdp": "ancien-mdp1", "question": "Ville ou village de naissance", "reponse": "Pobè"}), 302)
c.get("/logout")
# 2. oubli : mauvaise réponse puis bonne réponse (accents / majuscules ignorés), nouveau mot de passe
t = txt(ok(c.post("/mot-de-passe-oublie", data={"identifiant": "agnes"})))
assert "Ville ou village de naissance" in t
t = txt(ok(c.post("/mot-de-passe-oublie", data={"identifiant": "agnes", "action": "repondre", "reponse": "Cotonou"})))
assert "Réponse incorrecte" in t
t = txt(ok(c.post("/mot-de-passe-oublie", data={"identifiant": "agnes", "action": "repondre", "reponse": "  POBE "})))
assert "Choisissez votre nouveau mot de passe" in t
ok(c.post("/mot-de-passe-oublie", data={"identifiant": "agnes", "action": "nouveau", "nouveau": "nouveau-mdp2", "confirmation": "nouveau-mdp2"}), 302)
assert ok(c.post("/login", data={"identifiant": "agnes", "mdp": "nouveau-mdp2"}), 302).headers["Location"] != "/login"
c.get("/logout")
# jeton exigé pour l'étape « nouveau »
c2 = app.test_client()
t = txt(ok(c2.post("/mot-de-passe-oublie", data={"identifiant": "agnes", "action": "nouveau", "nouveau": "pirate-1234", "confirmation": "pirate-1234"})))
assert "Délai dépassé" in t
# 3. demande à l'administrateur → mot de passe provisoire
t = txt(ok(c2.post("/mot-de-passe-oublie", data={"identifiant": "agnes", "action": "demande", "nom": "Agnès", "contact": "0197000000"})))
assert "Demande transmise" in t
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
t = txt(ok(c.get("/utilisateurs")))
assert "Demandes « mot de passe oublié » (1)" in t
with app.app_context():
    did = q("SELECT id FROM mdp_demandes", un=True)["id"]
r = ok(c.post(f"/utilisateurs/demandes-mdp/{did}", data={"action": "reinit"}, follow_redirects=True))
t = txt(r); assert "Mot de passe provisoire de agnes" in t
with app.app_context():
    assert q("SELECT doit_changer_mdp FROM utilisateurs WHERE identifiant='agnes'", un=True)["doit_changer_mdp"] == 1
    assert q("SELECT statut FROM mdp_demandes WHERE id=?", (did,), un=True)["statut"] == "traitee"
assert "Demandes « mot de passe oublié »" not in txt(ok(c.get("/utilisateurs")))
print("OK-" + config.EDITION)
'''


class TestMotDePasse(unittest.TestCase):
    def test_publique(self):
        r = lancer(SCRIPT, "publique")
        self.assertIn("OK-publique", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_cs(self):
        r = lancer(SCRIPT, "cs")
        self.assertIn("OK-cs", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])


if __name__ == "__main__":
    unittest.main()
