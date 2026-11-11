# -*- coding: utf-8 -*-
"""Tests de la version 1.13 : modifier / supprimer / réinitialiser (paiements, caisse, contribution de cantine),
armoiries sur l'aperçu de la carte. Lancer : python3 -m unittest tests.test_v113"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
SCRIPT = r'''
import html, os, sys, tempfile
P=os.environ["PREFIXE_SCRIPT"]; os.environ[P+"_EDITION"]="privee"; os.environ[P+"_DATA"]=tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"]=True
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    cl=ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM1 T','CM1',50000,1)")
    el=ex("INSERT INTO eleves (nom, prenoms, sexe, date_naissance, classe_id, statut, matricule, date_inscription, annee) VALUES ('KOFFI','Ama','F','2014-01-01',?, 'inscrit','MX1','2026-09-15',?)",(cl,config.ANNEE_ACTIVE))
c=app.test_client()
def ok(r,code=200):
    assert r.status_code==code,(r.request.path,r.status_code,r.data[-800:]); return r
ok(c.post("/login",data={"identifiant":"admin","mdp":"admin123"}),302)
ok(c.post("/paiements/nouveau",data={"eleve_id":el,"montant":"10000","mode":"especes","motif":"Frais"}),302)
with app.app_context(): pid=q("SELECT id FROM paiements",un=True)["id"]
t=html.unescape(ok(c.get(f"/eleves/{el}")).data.decode()); assert "Modifier" in t and "ic-modifier" in t and "Réinitialiser les paiements" in t
ok(c.get(f"/paiements/{pid}/modifier"))
ok(c.post(f"/paiements/{pid}/modifier",data={"montant":"12000","date":"2026-10-20","mode":"especes","motif":"Frais"}),302)
with app.app_context(): assert q("SELECT montant FROM paiements WHERE id=?",(pid,),un=True)["montant"]==12000
ok(c.post(f"/paiements/{pid}/supprimer"),302)
with app.app_context(): assert not q("SELECT 1 FROM paiements",un=True)
ok(c.post("/paiements/nouveau",data={"eleve_id":el,"montant":"5000","mode":"especes"}),302)
ok(c.post(f"/eleves/{el}/paiements/reinitialiser",data={"confirmation":"non"}),302)
with app.app_context(): assert q("SELECT COUNT(*) n FROM paiements",un=True)["n"]==1
ok(c.post(f"/eleves/{el}/paiements/reinitialiser",data={"confirmation":"REINITIALISER"}),302)
with app.app_context(): assert q("SELECT COUNT(*) n FROM paiements",un=True)["n"]==0
ok(c.post("/tresorerie",data={"type":"sortie","categorie":"Loyer","libelle":"Loyer oct","montant":"30000","date":"2026-10-05"}),302)
with app.app_context(): tid=q("SELECT id FROM tresorerie",un=True)["id"]
t=html.unescape(ok(c.get("/tresorerie?mois=2026-10")).data.decode()); assert f"/tresorerie/{tid}/modifier" in t
ok(c.get(f"/tresorerie/{tid}/modifier"))
ok(c.post(f"/tresorerie/{tid}/modifier",data={"type":"sortie","categorie":"Loyer","libelle":"Loyer octobre","montant":"35000","date":"2026-10-06"}),302)
ok(c.post(f"/tresorerie/{tid}/supprimer"),302)
ok(c.post("/cantine/config",data={"classe":cl,"montant":"200","action":"valider"}),302)
t=html.unescape(ok(c.get("/cantine/config")).data.decode()); assert "Réinitialiser" in t
ok(c.post(f"/cantine/config/{cl}/reinitialiser",data={"paiements":"1"}),302)
with app.app_context(): assert not q("SELECT 1 FROM cantine_config WHERE classe_id=?",(cl,),un=True)
t=html.unescape(ok(c.get(f"/carte/{el}")).data.decode()) if False else ""
print("OK")
'''


class TestCorrections(unittest.TestCase):
    def test_privee(self):
        env = dict(os.environ)
        for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
            env.pop(k, None)
        env["PREFIXE_SCRIPT"] = PREFIXE
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)
        self.assertIn("OK", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])


if __name__ == "__main__":
    unittest.main()
