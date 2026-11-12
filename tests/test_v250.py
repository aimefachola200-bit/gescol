# -*- coding: utf-8 -*-
"""Tests 2.5.0 : liste officielle des écoles (rangement par CS, chargement, sans doublon à la transmission, cascade du formulaire)."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")

import referentiel_ecoles as RE  # noqa: E402

SCRIPT = r'''
import html, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = "cs"; os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
import config
from app import app, ex as _ex, q as _q
import m_juridiction as J
app.config["TESTING"] = True
with app.app_context():
    _ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
    J.configurer("cs", "Alibori", "KANDI 1")
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
def txt(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.data[-500:]); return html.unescape(r.data.decode(errors="replace"))
page = txt(c.get("/juridiction/ecoles/liste-officielle"))
assert "KANDI 1" in page
with app.app_context():
    cid = _q("SELECT id FROM jur_cs WHERE nom='KANDI 1'", un=True)["id"]
r = c.post("/juridiction/ecoles/liste-officielle", data={"cs": [cid]}); assert r.status_code == 302
with app.app_context():
    n1 = _q("SELECT COUNT(*) n FROM jur_ecoles WHERE cs_id=?", (cid,), un=True)["n"]
    e = _q("SELECT * FROM jur_ecoles WHERE cs_id=? ORDER BY id LIMIT 1", (cid,), un=True)
assert n1 > 20, n1
assert e["code"].startswith("REF-") and e["commune"] and e["arrondissement"], dict(e)
c.post("/juridiction/ecoles/liste-officielle", data={"cs": [cid]})          # 2e chargement : aucun doublon
with app.app_context():
    assert _q("SELECT COUNT(*) n FROM jur_ecoles WHERE cs_id=?", (cid,), un=True)["n"] == n1
    # la 1re transmission de l'école se rattache à la fiche existante (pas de doublon)
    eid, cree = J.enregistrer_ecole({"code": "KAN-0001", "nom": e["nom"], "type": e["type"], "secteur": "public"}, cid, None)
    assert not cree and eid == e["id"]
    assert _q("SELECT code FROM jur_ecoles WHERE id=?", (eid,), un=True)["code"] == "KAN-0001"
    assert _q("SELECT COUNT(*) n FROM jur_ecoles WHERE cs_id=?", (cid,), un=True)["n"] == n1
assert 'data-geo="ecole"' in txt(c.get("/juridiction/ecoles/nouvelle"))
print("OK", n1)
'''


class T(unittest.TestCase):
    def test_referentiel(self):
        D = RE.donnees()
        self.assertEqual(sum(len(a[1]) for d in D["d"] for c in d[1] for a in c[1]), 9217)
        self.assertEqual(len(D["cs"]), 118)
        s = RE.ecoles_de_cs("KANDI 1")
        self.assertTrue(len(s) > 20 and all(e["sure"] for e in s))
        plus = RE.ecoles_de_cs("PARAKOU 1", a_confirmer=True)
        self.assertTrue(any(not e["sure"] for e in plus))
        self.assertEqual(RE.code(s[0]), RE.code(dict(s[0])))

    def test_chargement_cs(self):
        e = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=e, capture_output=True, text=True, timeout=600)
        self.assertIn("OK", r.stdout, r.stdout[-500:] + r.stderr[-1500:])

    def test_services_secondaire_decret_2016_427(self):
        code = ("import os,sys,tempfile\n"
                "os.environ[P+'_EDITION']='sec_publique'; os.environ[P+'_DATA']=tempfile.mkdtemp(); os.environ[P+'_SANS_PRECHARGEMENT']='1'\n"
                "sys.path.insert(0,os.getcwd())\n"
                "import a_structure as S, a_personnel as Q\n"
                "d=[x[0] for x in S.SERVICES_DEFAUT['ddemp']]; assert d==['direction','secretariat','sestfp','sec','administration','ipd'], d\n"
                "assert 'IPD' in [x[2] for x in S.SERVICES_DEFAUT['cs']]\n"
                "assert '2016-427' in S.SOURCE_AOF and 'Inspecteur pédagogique délégué' in Q.POSTES['cs']\n"
                "print('OK')")
        e = dict(os.environ, P=PREFIXE)
        r = subprocess.run([sys.executable, "-c", "P=%r\n" % PREFIXE + code], cwd=RACINE, env=e, capture_output=True, text=True, timeout=300)
        self.assertIn("OK", r.stdout, r.stderr[-1500:])

    def test_ressources_secondaire(self):
        code = ("import html,os,sys,tempfile\n"
                "os.environ[P+'_EDITION']='sec_publique'; os.environ[P+'_DATA']=tempfile.mkdtemp(); os.environ[P+'_SANS_PRECHARGEMENT']='1'\n"
                "sys.path.insert(0,os.getcwd())\n"
                "from app import app, ex\n"
                "with app.app_context(): ex(\"UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'\")\n"
                "c=app.test_client(); c.get('/login'); c.post('/login',data={'identifiant':'admin','mdp':'admin123'})\n"
                "with app.app_context(): ex(\"UPDATE utilisateurs SET doit_changer_mdp=0\")\n"
                "for u in ('/ressources-secondaire','/ressources-secondaire?vue=exposes&niveau=Tle','/ressources-secondaire?vue=revisions','/ressources-secondaire/epreuve/1','/ressources-secondaire/revision/0','/ressources-secondaire?vue=epreuves&matiere=SVT'):\n"
                "    r=c.get(u); assert r.status_code==200,(u,r.status_code)\n"
                "t=html.unescape(c.get('/ressources-secondaire?vue=exposes').data.decode())\n"
                "assert 'Une si longue lettre' in t and 'Tresseurs de corde' in t and 'Une vie de boy' in t\n"
                "assert 'Pythagore' in html.unescape(c.get('/ressources-secondaire?vue=revisions').data.decode())\n"
                "print('OK')")
        r = subprocess.run([sys.executable, "-c", "P=%r\n" % PREFIXE + code], cwd=RACINE, env=dict(os.environ), capture_output=True, text=True, timeout=600)
        self.assertIn("OK", r.stdout, r.stderr[-1800:])

    def test_corrections_college(self):
        code = ("import os,sys,tempfile\n"
                "os.environ[P+'_EDITION']='sec_publique'; os.environ[P+'_DATA']=tempfile.mkdtemp(); os.environ[P+'_SANS_PRECHARGEMENT']='1'\n"
                "sys.path.insert(0,os.getcwd())\n"
                "import m_sec_supervision as M, banque_ea_eps as B\n"
                "assert M.habiller_texte('Bureaux de l UASCEP')=='Bureaux de l UASCES'\n"
                "assert M.habiller_texte('Note /10')=='Note /20' and B.NOTES[0]==20 and 'Note /20' in B.FICHE_COLONNES\n"
                "print('OK')")
        r = subprocess.run([sys.executable, "-c", "P=%r\n" % PREFIXE + code], cwd=RACINE, env=dict(os.environ), capture_output=True, text=True, timeout=300)
        self.assertIn("OK", r.stdout, r.stderr[-1500:])

    def test_js_et_json(self):
        self.assertIn("data-geo=\"ecole\"", open(os.path.join(RACINE, "templates", "ecole_form.html"), encoding="utf-8").read())
        self.assertTrue(os.path.getsize(os.path.join(RACINE, "static", "referentiel_ecoles.json")) > 100000)


if __name__ == "__main__":
    unittest.main()
