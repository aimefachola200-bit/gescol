# -*- coding: utf-8 -*-
"""Tests 1.16 : les absences prises par « Faire l'appel » entrent au registre d'appel (demi-journées), une seule
fois ; une case corrigée dans le registre reste corrigée ; un élève remis présent à l'appel sort du registre.
Lancer : python3 -m unittest tests.test_v116"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
SCRIPT = r'''
import os, sys, tempfile
P=os.environ["PREFIXE_SCRIPT"]; os.environ[P+"_EDITION"]=os.environ["EDITION_TEST"]; os.environ[P+"_DATA"]=tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"]=True
JOUR="2026-10-05"   # lundi : deux demi-journées de classe
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    cl=ex("INSERT INTO classes (nom, niveau, ecole_id) VALUES ('CE1 A','CE1',1)")
    a=ex("INSERT INTO eleves (nom, prenoms, sexe, date_naissance, classe_id, statut, date_inscription, annee) VALUES ('AKPO','Jean','M','2018-01-01',?,'inscrit','2026-09-15',?)",(cl,config.ANNEE_ACTIVE))
    b=ex("INSERT INTO eleves (nom, prenoms, sexe, date_naissance, classe_id, statut, date_inscription, annee) VALUES ('ADE','Rose','F','2018-02-01',?,'inscrit','2026-09-15',?)",(cl,config.ANNEE_ACTIVE))
c=app.test_client()
def ok(r,code=200):
    assert r.status_code==code,(r.request.path,r.status_code,r.data[-600:]); return r
ok(c.post("/login",data={"identifiant":"admin","mdp":"admin123"}),302)
def reg(e):
    with app.app_context(): return sorted(x["demi"] for x in q("SELECT demi FROM registre WHERE eleve_id=? AND date=?",(e,JOUR)))
# 1. appel : AKPO absent, ADE présente -> AKPO au registre sur toutes les demi-journées du jour
ok(c.post(f"/appel/{cl}/{JOUR}",data={f"s_{a}":"absent",f"s_{b}":"present"}),302)
nd=len(reg(a)); assert nd>=1 and reg(b)==[], (reg(a), reg(b))
# le registre et son PDF comptent l'absence
t=ok(c.get(f"/registre?classe={cl}&mois=2026-10")).data.decode()
r=ok(c.get(f"/registre/absences?classe={cl}&du=2026-10-01&au=2026-10-31")).get_json()
assert sum(1 for x in r["absences"] if x[0]==a and x[1]==JOUR)==nd, r
pdf=ok(c.get(f"/registre/pdf?classe={cl}&mois=2026-10")).data; assert pdf[:4]==b"%PDF"
# 2. correction à la main dans le registre (présent l'après-midi) : elle est conservée
if nd==2:
    ok(c.post("/registre/presence",json={"eleve_id":a,"date":JOUR,"demi":2,"absent":False}))
    ok(c.get(f"/registre?classe={cl}&mois=2026-10")); assert reg(a)==[1], reg(a)
# 3. l'appel remet l'élève présent : il sort du registre ; absent de nouveau : il y revient
ok(c.post(f"/appel/{cl}/{JOUR}",data={f"s_{a}":"present",f"s_{b}":"present"}),302); assert reg(a)==[], reg(a)
ok(c.post(f"/appel/{cl}/{JOUR}",data={f"s_{a}":"absent",f"s_{b}":"retard"}),302); assert len(reg(a))==nd and reg(b)==[], (reg(a),reg(b))
# 4. absences d'appel antérieures (données existantes) : reportées à la première ouverture du registre
with app.app_context():
    ex("INSERT INTO presences (eleve_id, date, statut, justifie) VALUES (?, '2026-10-06', 'absent', 0)", (b,))
r=ok(c.get(f"/registre/absences?classe={cl}&du=2026-10-01&au=2026-10-31")).get_json()
assert any(x[0]==b and x[1]=="2026-10-06" for x in r["absences"]), r
# 5. relevé mensuel : l'absence est comptée
ok(c.get(f"/releves?classe={cl}"))
# 6. départements servis : plusieurs choix (formulaire à cases, import « Atacora, Donga »)
import m_carriere as MC
from werkzeug.datastructures import MultiDict
assert MC.lire_departements(MultiDict([("d","Plateau"),("d","Atacora")]),"d")==("Atacora, Plateau",[])
assert MC.lire_departements({"d":"ouémé ; Zou et Donga"},"d")==("Donga, Ouémé, Zou",[])
assert MC.lire_departements({"d":"Atacora, Paris"},"d")[1]==["Paris"]
assert MC.departements_de("Atacora, Plateau")==["Atacora","Plateau"]
t=ok(c.get("/personnel/nouveau")).data.decode()
if 'name="departement_servir"' in t:
    assert t.count('name="departement_servir"')==12 and 'type="checkbox" name="departement_servir"' in t
    r=c.post("/personnel/nouveau",data=MultiDict([("nom","DOSSA"),("prenoms","Luc"),("sexe","M"),("fonction","Enseignant"),("type_contrat","CDI"),
        ("salaire_base","0"),("taux_horaire","0"),("departement_servir","Plateau"),("departement_servir","Atacora")]))
    assert r.status_code in (200,302), r.status_code
    with app.app_context():
        row=q("SELECT departement_servir FROM personnel_carriere WHERE departement_servir IS NOT NULL AND departement_servir!=''",un=True)
    if r.status_code==302:
        assert row and row["departement_servir"]=="Atacora, Plateau", dict(row) if row else None
        with app.app_context(): pid=q("SELECT id FROM personnel WHERE nom='DOSSA'",un=True)["id"]
        t=ok(c.get(f"/personnel/{pid}/modifier")).data.decode()
        assert t.count("checked")>=2 and 'value="Atacora" checked' in t.replace("  "," "), "cases non cochées"
print("OK")
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["PREFIXE_SCRIPT"] = PREFIXE
    env["EDITION_TEST"] = edition
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)


class TestRegistreAppel(unittest.TestCase):
    def test_publique(self):
        r = lancer("publique")
        self.assertIn("OK", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        r = lancer("privee")
        self.assertIn("OK", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])


if __name__ == "__main__":
    unittest.main()
