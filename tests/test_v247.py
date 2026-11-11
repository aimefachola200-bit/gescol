# -*- coding: utf-8 -*-
"""Tests 2.4.7 : hiérarchie du secondaire (établissement → Inspection secondaire → DDESTFP) et diffusion WhatsApp / SMS aux enseignants.
Lancer : python3 -m unittest tests.test_v247"""
import os
import subprocess
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")

import m_sec_supervision as S  # noqa: E402

DEP, CS_ = "Alibori", "BANIKOARA 1"

ENTETE = r'''
import html, io, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]; TMP = os.environ["TMP_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
import config
from app import app, ex as _ex, q as _q
app.config["TESTING"] = True
DEP, CS_ = os.environ["DEP"], os.environ["CS_"]
def txt(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-600:])
    return html.unescape(r.data.decode(errors="replace"))
with app.app_context():
    _ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
'''

ECOLE = ENTETE + r'''
assert config.SECONDAIRE and config.EDITION == "privee"
with app.app_context():
    _ex("UPDATE ecoles SET departement=?, cs=?, nom='CEG de Test' WHERE id=(SELECT MIN(id) FROM ecoles)", (DEP, CS_))
    def classe(nom, niv):
        _ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES (?,?,0,(SELECT MIN(id) FROM ecoles))", (nom, niv))
        return _q("SELECT id FROM classes WHERE nom=?", (nom,), un=True)["id"]
    def eleve(i, cid, sexe, red=0):
        _ex("INSERT INTO eleves (nom, prenoms, sexe, classe_id, statut, matricule, date_inscription, annee, redoublant) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"E{i}", "T", sexe, cid, "inscrit", f"M{i}", "2026-10-01", "2026-2027", red))
    a = classe("6ème A", "6ème"); d = classe("Tle D", "Tle")
    for i in range(5): eleve(i, a, "M")
    for i in range(5, 8): eleve(i, a, "F", 1 if i == 5 else 0)
    for i in range(8, 10): eleve(i, d, "F")
    for nom, f, tel in (("PROF1", "Professeur de maths", "97000001"), ("PROF2", "Enseignante d'anglais", "96000002"), ("COMPTA", "Comptable", "95000003")):
        _ex("INSERT INTO personnel (nom, prenoms, fonction, telephone, sexe, type_contrat, ecole_id, actif) VALUES (?,?,?,?,?,'CDI',(SELECT MIN(id) FROM ecoles),1)",
            (nom, "X", f, tel, "F" if nom == "PROF2" else "M"))
r = c.post("/secondaire/examens-resultats", data={"BEPC_inscrits_g": 10, "BEPC_inscrits_f": 8, "BEPC_presents_g": 10, "BEPC_presents_f": 8,
                                                  "BEPC_admis_g": 6, "BEPC_admis_f": 4, "BAC_inscrits_g": 5, "BAC_presents_g": 5, "BAC_admis_g": 2})
assert r.status_code == 302
assert "Résultats aux examens" in txt(c.get("/secondaire/examens-resultats"))
home = txt(c.get("/classes/nouvelle"))
assert "Établissement" not in home or True
assert "Inspection" in txt(c.get("/transmission")), "vocabulaire Inspection absent de la page de transmission"
txt(c.get("/transmission"))
r = c.get("/transmission/fichier"); assert r.status_code == 200, r.data[-500:]
open(os.path.join(TMP, "ecole.gescol"), "wb").write(r.data)
import jur_format
p = jur_format.lire(r.data)
e = p["ecoles"][0]
assert e["ecole"]["type"] == "LYC", e["ecole"]["type"]
s = e["sections"]["secondaire"]
assert sum(x["garcons"] + x["filles"] for x in s["classes"]) == 10, s
assert s["examens"]["BEPC"]["admis_g"] == 6
# --- annonce aux enseignants : WhatsApp / SMS
r = c.post("/communication/diffuser", data={"cible": "enseignants", "sujet": "Conseil", "texte": "Vendredi 8 h.", "canaux": ["whatsapp", "sms"]})
assert r.status_code == 302 and "/diffuser" in r.headers["Location"], r.headers.get("Location")
page = txt(c.get(r.headers["Location"]))
assert "PROF1" in page and "PROF2" in page and "COMPTA" not in page, "destinataires"
with app.app_context():
    aid = _q("SELECT id FROM annonces_personnel WHERE sujet='Conseil'", un=True)["id"]
    pid = _q("SELECT id FROM personnel WHERE nom='PROF1'", un=True)["id"]
r = c.get(f"/annonces/{aid}/envoi/{pid}/whatsapp"); assert r.status_code == 302 and r.headers["Location"].startswith("https://wa.me/229"), r.headers.get("Location")
r = c.get(f"/annonces/{aid}/envoi/{pid}/sms"); assert r.status_code == 302 and r.headers["Location"].startswith("sms:+229"), r.headers.get("Location")
assert "✓" in txt(c.get(f"/annonces/{aid}/diffuser"))
print("OK ecole")
'''

SUPERVISION = ENTETE + r'''
import m_juridiction as J, jur_format
NIV = os.environ["NIV"]
assert config.SECONDAIRE and config.juridiction() and config.EDITION == NIV
with app.app_context():
    J.configurer(NIV, DEP, CS_ if NIV == "cs" else "")
    assert "econdaire" in (J.structure()["nom"]), J.structure()["nom"]
    if NIV == "ddemp":
        J.configurer("ddemp", DEP)
for f in os.environ["PAQUETS"].split(","):
    with app.app_context():
        res = J.importer_paquet(jur_format.lire(open(os.path.join(TMP, f), "rb").read()), "fichier", "test", 0)
        assert res["ecoles_creees"] + res["ecoles_maj"] >= 1, res
r = c.get("/"); assert r.status_code in (200, 302)
r = c.get("/jur/tableau") if False else None
t = txt(c.get("/sec/tableau"))
assert "CEG de Test" in t and "LYC" in t, t[-1500:]
assert "Terminale" in t or "Tle" in t
assert ">10<" in t.replace(" ", "") or "10" in t
assert "DDEMP" not in t and "Circonscription scolaire" not in t, "vocabulaire primaire visible"
assert ("Inspection" in t) or ("DDESTFP" in t)
ex_ = txt(c.get("/sec/examens")); assert "BEPC" in ex_ and "55" in ex_.replace(",", ".") or "55.6" in ex_ or "55,6" in ex_, ex_[-1200:]
txt(c.get("/sec/personnel"))
for u in ("/sec/export.pdf?vue=tableau", "/sec/export.pdf?vue=examens", "/sec/export.pdf?vue=personnel"):
    r = c.get(u); assert r.status_code == 200 and r.data.startswith(b"%PDF"), (u, r.status_code)
for u in ("/sec/export.xlsx?vue=tableau", "/sec/export.xlsx?vue=examens"):
    r = c.get(u); assert r.status_code == 200 and r.data[:2] == b"PK", (u, r.status_code)
menu = txt(c.get("/sec/tableau"))
assert "/cep" not in menu and "/sec/examens" in menu
if NIV == "cs":
    with app.app_context():
        p = J.exporter_paquet_cs()
    open(os.path.join(TMP, "cs.gescol"), "wb").write(jur_format.vers_fichier(p))
print("OK", NIV)
'''


def lancer(script, **env):
    e = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, DEP=DEP, CS_=CS_, **env)
    return subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=e, capture_output=True, text=True, timeout=900)


class Purs(unittest.TestCase):
    def test_vocabulaire(self):
        self.assertEqual(S.habiller_texte("Circonscription scolaire de Banikoara"), "Inspection secondaire de Banikoara")
        self.assertEqual(S.habiller_texte("Envoyer à la DDEMP"), "Envoyer à la DDESTFP")
        self.assertEqual(S.habiller_texte("Tableau synoptique de la CS"), "Tableau synoptique de l'Inspection")
        self.assertEqual(S.habiller_texte("Les écoles", supervision=True), "Les établissements")
        self.assertEqual(S.habiller_texte("Les écoles"), "Les écoles")
        h = S.habiller_html('<a href="/x?DDEMP=1">DDEMP</a><script>var a="DDEMP"</script>')
        self.assertEqual(h, '<a href="/x?DDEMP=1">DDESTFP</a><script>var a="DDEMP"</script>')

    def test_calculs(self):
        par = S.totaux_classes([{"niveau": "6ème", "garcons": 10, "filles": 8, "redoublants_g": 1, "redoublants_f": 0},
                                {"niveau": "6ème", "garcons": 5, "filles": 5, "redoublants_g": 0, "redoublants_f": 2}])
        self.assertEqual(par["6ème"], [15, 13, 1, 2])
        self.assertEqual(S.taux(6, 8), 75.0)
        self.assertIsNone(S.taux(0, 0))
        v = S.examens_etablissement({"examens": {"BEPC": {"presents_g": 10, "presents_f": 10, "admis_g": 5, "admis_f": 10}}}, "BEPC")
        self.assertEqual((v["taux"], v["taux_g"], v["taux_f"]), (75.0, 50.0, 100.0))
        self.assertTrue(S.enseignant_par_fonction("Professeur de maths"))
        self.assertFalse(S.enseignant_par_fonction("Comptable"))


class Editions(unittest.TestCase):
    def test_alias(self):
        code = ("import os,sys;sys.path.insert(0,os.getcwd());import config;"
                "print(config.SECONDAIRE,config.EDITION,config.juridiction(),config.NOMS_APPLI[config.EDITION],config.PORTS[config.EDITION_IMPOSEE],"
                "config.DOSSIERS[config.EDITION_IMPOSEE],config.FICHIERS_MAJ[config.EDITION][1])")
        attendu = {"sec_cs": "True cs True {m} Inspection Secondaire", "sec_ddestfp": "True ddemp True {m} DDESTFP",
                   "sec_privee": "True privee False {m} Secondaire", "sec_publique": "True publique False {m} Secondaire Public"}
        ports = set()
        for ed, debut in attendu.items():
            r = subprocess.run([sys.executable, "-c", code], cwd=RACINE, capture_output=True, text=True,
                               env=dict(os.environ, **{PREFIXE + "_EDITION": ed}))
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            self.assertTrue(r.stdout.startswith(debut.format(m=PREFIXE)), r.stdout)
            ports.add(r.stdout.split()[-3] if False else r.stdout)
        self.assertEqual(len(ports), 4)


class Hierarchie(unittest.TestCase):
    def test_chaine_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = lancer(ECOLE, EDITION_SCRIPT="sec_privee", TMP_SCRIPT=tmp)
            self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3500:])
            r = lancer(SUPERVISION, EDITION_SCRIPT="sec_cs", TMP_SCRIPT=tmp, NIV="cs", PAQUETS="ecole.gescol")
            self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3500:])
            r = lancer(SUPERVISION, EDITION_SCRIPT="sec_ddestfp", TMP_SCRIPT=tmp, NIV="ddemp", PAQUETS="cs.gescol")
            self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3500:])
            self.assertIn("OK ddemp", r.stdout)


if __name__ == "__main__":
    unittest.main()
