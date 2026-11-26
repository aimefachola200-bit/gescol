# -*- coding: utf-8 -*-
"""v2.9.4 : module Zone déshéritée (liste par école, nombre d'ayants droit, montants par couleur, Excel, PDF)."""
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREF = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import os, sys, tempfile, io
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
assert c.get("/zone-desheritee/liste").status_code == 200
c.post("/reg/zone/baremes/0", data={"couleur": "Orange", "rendement": "10000", "prime": "25000"})
c.post("/reg/zone/baremes/0", data={"couleur": "Rouge", "rendement": "15000", "prime": "40000"})
c.post("/reg/zone/agents/0", data={"ecole": "EPP A", "matricule": "111", "nom": "Zinsou", "prenoms": "Paul", "poste_desherite": "Orange", "fonction": "Directeur"})
c.post("/reg/zone/agents/0", data={"ecole": "EPP A", "matricule": "112", "nom": "Adjovi", "prenoms": "Rose", "poste_desherite": "Rouge", "fonction": "Autre"})
c.post("/reg/zone/agents/0", data={"ecole": "EPP B", "matricule": "113", "nom": "Kpanou", "prenoms": "Luc", "poste_desherite": "Orange", "fonction": "Autre", "prime_zone": "30000"})
r = c.get("/zone-desheritee/liste")
t = r.get_data(as_text=True)
assert r.status_code == 200 and "École : EPP A" in t and "École : EPP B" in t, t[:500]
assert "Nombre d&#39;ayants droit : 2" in t or "Nombre d'ayants droit : 2" in t
assert "Total général : 3" in t
assert "25 000" in t.replace(" ", " ").replace("\xa0", " ") and "40 000" in t.replace(" ", " ").replace("\xa0", " ")
assert "30 000" in t.replace(" ", " ").replace("\xa0", " ")        # montant saisi conservé (modifiable)
x = c.get("/zone-desheritee/liste.xlsx"); assert x.status_code == 200 and x.data[:2] == b"PK"
p = c.get("/zone-desheritee/liste.pdf"); assert p.status_code == 200 and p.data[:4] == b"%PDF"
assert c.get("/zone-desheritee/liste?couleur=Rouge").get_data(as_text=True).count("Zinsou") == 0
assert c.get("/reg/zone/agents").status_code == 200 and c.get("/reg/zone/baremes").status_code == 200
print("OK")
'''


def test_zone_desheritee():
    env = dict(os.environ, PREFIXE_SCRIPT=PREF)
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-800:] + r.stderr[-1500:]
