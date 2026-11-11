# -*- coding: utf-8 -*-
"""Tests 2.3.1 : classes ouvertes — une classe jumelée (2 cours) ou multigrade (3 cours et plus) compte pour UNE classe.
Exemples de l'utilisateur : CI-CP, CE1-CE2, CM1-CM2 = 3 classes ; CI + CE2 + CM1 en multigrade = 1 classe.
(1) règle (classes_org) ; (2) paquet transmis et calculs de la juridiction (jur_calc) ; (3) école : regrouper / séparer,
page Classes, fiche de recensement, rapport de rentrée, fiche statistique de rentrée, pilotage, tableau de bord.
Lancer : python3 -m unittest tests.test_v231"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

import classes_org as CO  # noqa: E402
import jur_calc as JC  # noqa: E402


def cl(i, niv, grp=None, nom=None):
    return {"id": i, "nom": nom or f"{niv} A", "niveau": niv, "groupe_classe": grp}


class TestRegle(unittest.TestCase):
    def test_exemples_utilisateur(self):
        trois_jumelees = [cl(1, "CI", "a"), cl(2, "CP", "a"), cl(3, "CE1", "b"), cl(4, "CE2", "b"), cl(5, "CM1", "c"), cl(6, "CM2", "c")]
        self.assertEqual(CO.compter(trois_jumelees), {"simples": 0, "jumelees": 3, "multigrades": 0, "total": 3, "ouvertes": 3})
        multi = [cl(1, "CI", "m"), cl(2, "CE2", "m"), cl(3, "CM1", "m")]
        self.assertEqual(CO.compter(multi), {"simples": 0, "jumelees": 0, "multigrades": 1, "total": 1, "ouvertes": 1})
        mixte = [cl(1, "CI", "m"), cl(2, "CE2", "m"), cl(3, "CM1", "m"), cl(4, "CP", "j"), cl(5, "CE1", "j"), cl(6, "CM2"), cl(7, "CM2", nom="CM2 B")]
        self.assertEqual(CO.compter(mixte), {"simples": 2, "jumelees": 1, "multigrades": 1, "total": 4, "ouvertes": 4})
        ps = CO.physiques(mixte)
        self.assertIn("CI-CE2-CM1", [p["libelle"] for p in ps])
        self.assertEqual(CO.ecart_autorisees(4, 3), "Au-delà des classes autorisées (+1)")
        self.assertEqual(CO.ecart_autorisees(3, 6), "En deçà des classes autorisées (-3)")
        self.assertEqual(CO.ecart_autorisees(3, ""), "Autorisées non renseignées")

    def test_paquet_transmis(self):
        sec = {"classes": [
            {"niveau": "CI", "garcons": 10, "filles": 12, "groupe": "jumele", "groupe_id": "a"},
            {"niveau": "CP", "garcons": 9, "filles": 8, "groupe": "jumele", "groupe_id": "a"},
            {"niveau": "CE1", "garcons": 5, "filles": 5, "groupe": "multigrade", "groupe_id": "m"},
            {"niveau": "CE2", "garcons": 6, "filles": 4, "groupe": "multigrade", "groupe_id": "m"},
            {"niveau": "CM1", "garcons": 7, "filles": 3, "groupe": "multigrade", "groupe_id": "m"},
            {"niveau": "CM2", "garcons": 20, "filles": 22, "groupe": "simple"},
            {"niveau": "CI", "garcons": 30, "filles": 28, "groupe": "jumele"}]}        # ancien format : une ligne = une classe
        e = JC.effectifs(sec)
        self.assertEqual(e["classes"], 4)
        self.assertEqual((e["classes_simples"], e["classes_jumelees"], e["classes_multigrades"]), (1, 2, 1))
        self.assertEqual(sorted(e["tailles"]), [30, 39, 42, 58])                # effectif de chaque classe physique
        self.assertEqual(e["par_niveau"]["CI"], [40, 40])                       # effectifs par cours inchangés
        self.assertEqual(JC.besoin_enseignants(sec, [])["classes"], 4)


SCRIPT = r'''
import io, os, sys, tempfile, json
from datetime import date
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "publique"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from werkzeug.security import generate_password_hash
import config
app.config["TESTING"] = True
auj = date.today().isoformat()
ids = {}
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    for niv in ("CI", "CP", "CE1", "CE2", "CM1", "CM2"):
        ids[niv] = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES (?,?,0,1)", (niv + " A", niv))
        for i, s in enumerate("MF"):
            ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, classe_id, statut, date_inscription, annee) VALUES (?,?,?,?,?,'inscrit',?,?)",
               (f"{niv}{i}", f"N{niv}{i}", "P", s, ids[niv], auj, config.ANNEE_ACTIVE))
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
h = c.get("/classes").data.decode()
assert "6 classe(s) ouverte(s)" in h, h[-1500:]
for a, b in (("CI", "CP"), ("CE1", "CE2"), ("CM1", "CM2")):
    r = c.post("/classes/regrouper", data={"ids": [str(ids[a]), str(ids[b])]}, follow_redirects=True)
    assert "compte pour une classe ouverte" in r.data.decode()
h = c.get("/classes").data.decode()
assert "3 classe(s) ouverte(s)" in h and "0 simple(s), 3 jumelée(s), 0 multigrade(s)" in h and "Jumelée CI-CP" in h, h[-2500:]
import flask
import registres
HH = registres._H
with app.app_context():
    grp = {r["niveau"]: r["groupe_classe"] for r in q("SELECT niveau, groupe_classe FROM classes")}
assert grp["CI"] == grp["CP"] and grp["CI"] != grp["CE1"]
# paquet transmis : groupe / groupe_id / cours_groupe ; calcul de la juridiction
with app.test_request_context():
    flask.g.user = q("SELECT * FROM utilisateurs WHERE identifiant='admin'", un=True)
    pq = HH.transmission_paquet()
def trouver(d, prof=0):
    if isinstance(d, dict):
        if "classes" in d and isinstance(d["classes"], list) and d["classes"] and "garcons" in d["classes"][0]:
            return d["classes"]
        for v in d.values():
            r_ = trouver(v, prof + 1) if prof < 6 else None
            if r_:
                return r_
    if isinstance(d, list):
        for v in d:
            r_ = trouver(v, prof + 1) if prof < 6 else None
            if r_:
                return r_
    return None
eff = trouver(pq)
assert eff, list(pq)
assert {x["groupe"] for x in eff} == {"jumele"} and all(x["groupe_id"] for x in eff), eff
assert {x["cours_groupe"] for x in eff} == {"CI-CP", "CE1-CE2", "CM1-CM2"}
import jur_calc
assert jur_calc.effectifs({"classes": eff})["classes"] == 3
# multigrade : CI + CE2 + CM1 ensemble, les autres simples → 4 classes (1 multigrade + 3 simples)
for k in ("CI", "CE2"):
    pass
with app.app_context():
    ex("UPDATE classes SET groupe_classe=NULL")
r = c.post("/classes/regrouper", data={"ids": [str(ids["CI"]), str(ids["CE2"]), str(ids["CM1"])]}, follow_redirects=True)
assert "multigrade CI-CE2-CM1" in r.data.decode(), r.data.decode()[-1500:]
h = c.get("/classes").data.decode()
assert "4 classe(s) ouverte(s)" in h and "3 simple(s), 0 jumelée(s), 1 multigrade(s)" in h
# fiche de recensement (structure pédagogique) : classes existantes = 4 ; multigrades cochées par cours
with app.test_request_context():
    flask.g.user = q("SELECT * FROM utilisateurs WHERE identifiant='admin'", un=True)
    flask.g.ecole = q("SELECT * FROM ecoles WHERE id=1", un=True)
    import m_recensement as MR
    auto, _inf = MR.calculs(HH, "primaire", config.ANNEE_ACTIVE)
assert auto["classes_existantes"] == "4" and auto["salles_utilisees"] == "4", {k: v for k, v in auto.items() if "t314" in k or "classes" in k}
assert auto["t314.multi.ci"] == "1" and auto["t314.multi.ce2"] == "1" and auto["t314.multi.cm1"] == "1" and auto["t314.multi.salles"] == "1"
assert auto["t314.simples.salles"] == "3" and auto.get("t314.simples.ci") in (None, "", "0")
# fiche statistique de rentrée : classes ouvertes et répartition proposées
h = c.get("/reg/territoire/rentree").data.decode()
import re
def valeur(nom):
    m = re.search(r'name="%s"[^>]*value="([^"]*)"' % nom, h) or re.search(r'value="([^"]*)"[^>]*name="%s"' % nom, h)
    return m.group(1) if m else None
assert valeur("classes") == "4" and valeur("classesSimples") == "3" and valeur("classesMultigrades") == "1", (valeur("classes"), valeur("classesSimples"))
# séparer : chaque cours redevient une classe simple
with app.app_context():
    cle = q("SELECT groupe_classe FROM classes WHERE niveau='CI'", un=True)["groupe_classe"]
c.post(f"/classes/separer/{cle}")
assert "6 classe(s) ouverte(s)" in c.get("/classes").data.decode()
print("OK-231")
'''


ECOLE_PAQUET = r'''
import json, os, sys, tempfile
from datetime import date
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "publique"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from werkzeug.security import generate_password_hash
import config, flask, registres
app.config["TESTING"] = True
auj = date.today().isoformat()
ids = {}
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    ex("UPDATE ecoles SET nom=?, cs=? WHERE id=1", (sys.argv[2], "POBE"))
    for niv in ("CI", "CP", "CE1", "CE2", "CM1", "CM2"):
        ids[niv] = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES (?,?,0,1)", (niv + " A", niv))
        for i, s in enumerate("MFF"):
            eid = ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, classe_id, statut, date_inscription, annee) VALUES (?,?,?,?,?,'inscrit',?,?)",
                     (f"{niv}{i}", f"N{niv}{i}", "P", s, ids[niv], auj, config.ANNEE_ACTIVE))
            if niv == "CM2":
                ex("INSERT INTO cep_fiches (eleve_id, session, centre) VALUES (?,?,?)", (eid, "2027", "POBE-CENTRE"))
    for a, b in (("CI", "CP"), ("CE1", "CE2"), ("CM1", "CM2")):
        ex("UPDATE classes SET groupe_classe=? WHERE id IN (?,?)", (f"g{ids[a]}", ids[a], ids[b]))
with app.test_request_context():
    flask.g.user = q("SELECT * FROM utilisateurs WHERE identifiant='admin'", un=True)
    flask.g.ecole = q("SELECT * FROM ecoles WHERE id=1", un=True)
    pq = registres._H.transmission_paquet()
json.dump(pq, open(sys.argv[1], "w"), ensure_ascii=False)
print("OK-paquet")
'''

CS_IMPORT = r'''
import json, os, subprocess, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
D = tempfile.mkdtemp()
os.environ.update({P + "_EDITION": "cs", P + "_DATA": D})
subprocess.run([sys.executable, "demo_juridiction.py"], check=True, stdout=subprocess.DEVNULL)
sys.path.insert(0, os.getcwd())
from app import app, ex, q
import config, flask, registres
app.config["TESTING"] = True
pq = json.load(open(sys.argv[1]))
with app.test_request_context():
    flask.g.user = q("SELECT * FROM utilisateurs WHERE identifiant='responsable'", un=True)
    res = registres._H.jur_importer_paquet(pq, "fichier", "test", 0, controle_perimetre=False)
c = app.test_client()
assert c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"}).status_code == 302
h = c.get("/territoire/rentree/suivi").data.decode()
nom = sys.argv[2]
assert nom in h and "3 (0 / 3 / 0)" in h and "transmission de l" in h, h[h.find("sans fiche"):][:2500]
assert c.post("/examens/cep2027/pobe").status_code == 302
c.post("/examens/cep2027/pre-remplir")
with app.app_context():
    r = q("SELECT * FROM reg_examens_salles WHERE centre='POBE-CENTRE'", un=True)
    assert (r["offG"], r["offF"]) == (1, 2), dict(r)
    assert nom in (r["sourceCandidats"] or "") and "transmis le" in r["sourceCandidats"]
h = c.get("/examens/cep2027").data.decode()
assert "transmis le" in h
print("OK-cs-import")
'''


class TestBoutEnBout(unittest.TestCase):
    """École (classes jumelées, candidats au CEP avec leur centre) → paquet → CS : suivi pré-rempli, centres du CEP pré-remplis."""
    def test_ecole_vers_cs(self):
        import tempfile
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        for k in list(env):
            if k.endswith(("_EDITION", "_DATA")) and k.startswith(("SCOLARIS", "GESCOL")):
                env.pop(k)
        f = tempfile.mktemp(suffix=".json")
        nom = "EPP JUMELEE TEST"
        r = subprocess.run([sys.executable, "-c", ECOLE_PAQUET, f, nom], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)
        self.assertIn("OK-paquet", r.stdout, r.stdout[-2000:] + r.stderr[-5000:])
        r = subprocess.run([sys.executable, "-c", CS_IMPORT, f, nom], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)
        self.assertIn("OK-cs-import", r.stdout, r.stdout[-2000:] + r.stderr[-5000:])


class TestEcole(unittest.TestCase):
    def test_ecole(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        for k in list(env):
            if k.endswith(("_EDITION", "_DATA")) and k.startswith(("SCOLARIS", "GESCOL")):
                env.pop(k)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK-231", r.stdout)


if __name__ == "__main__":
    unittest.main()


class TestV232(unittest.TestCase):
    """2.3.2 : « Autre combinaison » des rapports (comptée comme une jumelée, cours concernés), libellé 3.15 ii du recensement,
    fiche signalétique dans le paquet de transmission, référentiel des structures descendant."""

    def test_autre_combinaison_et_libelles(self):
        import m_sync
        src = open(os.path.join(RACINE, "m_rapports.py"), encoding="utf-8").read()
        self.assertIn('("AUTRE", "Autre combinaison")', src)
        self.assertIn("sp.jumelee.AUTRE_cours", src)
        self.assertIn("ii. Nombre de classes existantes (jumelées et multigrades comptées une fois)", open(os.path.join(RACINE, "m_recensement.py"), encoding="utf-8").read())
        self.assertIn(("territoire", "structures"), m_sync.REG_DESCENDANT)
        self.assertNotIn(("inspection", "visites"), m_sync.REG_MONTANT + m_sync.REG_DESCENDANT)


SCRIPT_232 = r'''
import os, sys, tempfile
from datetime import date
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "publique"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from werkzeug.security import generate_password_hash
import config, flask, registres
app.config["TESTING"] = True
auj = date.today().isoformat()
ids = {}
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    for niv in ("CI", "CP", "CE1", "CE2", "CM1", "CM2"):
        ids[niv] = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES (?,?,0,1)", (niv + " A", niv))
        ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, classe_id, statut, date_inscription, annee) VALUES (?,?,?,?,?,'inscrit',?,?)",
           (f"{niv}1", f"N{niv}", "P", "M", ids[niv], auj, config.ANNEE_ACTIVE))
    ex("UPDATE classes SET groupe_classe='x' WHERE niveau IN ('CI','CE1')")      # autre combinaison CI-CE1
    ex("UPDATE classes SET groupe_classe='y' WHERE niveau IN ('CM1','CM2')")
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
H = registres._H
with app.test_request_context():
    flask.g.user = q("SELECT * FROM utilisateurs WHERE identifiant='admin'", un=True)
    flask.g.ecole = q("SELECT * FROM ecoles WHERE id=1", un=True)
    v = H.rapports_valeurs("rentree-ep", config.ANNEE_ACTIVE)
    v = v.get("valeurs", v)
    assert v.get("sp.jumelee.AUTRE") == "1" and v.get("sp.jumelee.AUTRE_cours") == "CI-CE1", {k: x for k, x in v.items() if k.startswith("sp.")}
    assert v.get("sp.jumelee.CM1_CM2") == "1" and v.get("classes_ouvertes") == "4" and v.get("sp.jumelee.salles") == "2"
    H.doc_ecrire("signaletique:e1", {"latitude": 7.36, "longitude": 2.6, "numeroAgrement": "AG-1"})
    pq = H.transmission_paquet()
import json
assert '"numeroAgrement": "AG-1"' in json.dumps(pq, ensure_ascii=False), "signalétique dans le paquet"
import io, openpyxl, pypdf
c.post("/rapports/rentree-ep", data={"action": "sauver"})
r = c.get(f"/rapports/rentree-ep/pdf?annee={config.ANNEE_ACTIVE}")
assert r.status_code == 200, r.status_code
t = "".join(p_.extract_text() or "" for p_ in pypdf.PdfReader(io.BytesIO(r.data)).pages)
assert "Autre : 1 (CI-CE1)" in t, t[:1500]
r = c.get(f"/rapports/rentree-ep/excel?annee={config.ANNEE_ACTIVE}")
wb = openpyxl.load_workbook(io.BytesIO(r.data))
assert any("Autre combinaison (CI-CE1) : 1" in str(x.value or "") for ws in wb for row in ws.iter_rows() for x in row)
print("OK-232")
'''


class TestV232Ecole(unittest.TestCase):
    def test_autre_combinaison_rapport_et_signaletique(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        for k in list(env):
            if k.endswith(("_EDITION", "_DATA")) and k.startswith(("SCOLARIS", "GESCOL")):
                env.pop(k)
        r = subprocess.run([sys.executable, "-c", SCRIPT_232], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK-232", r.stdout)
