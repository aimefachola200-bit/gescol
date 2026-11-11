# -*- coding: utf-8 -*-
"""Tests 1.31 : lot de documents du 28/10/2026.
(1) manuels officiels : catalogue, séances de lecture rattachées à leur texte, résumés de lecture réécrits d'après les textes
réels (CE1, CE2, CM2), fiches de mathématiques rattachées au dossier / SA du manuel ;
(2) mesures correctives : 32 séries de diphtongues au CE1 (fiches + résumés), activité préliminaire des démarches d'ES / EST /
EA / EPS, journal des changements et guide de synthèse ;
(3) résumés complémentaires CE2 (ES, EST) ; (4) cahiers de révision d'éveil CM1 et CM2 et sujets type CEP (barème sur 20),
PDF en Times New Roman 14 pt ; (5) guides officiels du lot b ajoutés à l'onglet Guides et SA contrôlées ;
(6) pages : Révisions d'éveil, Manuels officiels, lien depuis le CEP.
Lancer : python3 -m unittest tests.test_v131"""
import gzip
import json
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "tests"))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"


def corpus():
    with gzip.open(os.path.join(RACINE, "static", "pedafiche_corpus.json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


class TestCorpus131(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C = corpus()

    def test_manuels(self):
        M = {m["id"]: m for m in self.C["manuels"]}
        for mid, n in (("man-ce1-fr-2008", 49), ("man-ce2-fr-2004", 49), ("man-cm2-fr-2004", 36)):
            self.assertEqual(len(M[mid]["textes"]), n, mid)
            self.assertEqual(M[mid]["statut"], "officiel")
        for mid in ("man-ce1-ma-2008", "man-ce2-ma-2004", "man-cm1-ma-2004", "man-cm2-ma-2004"):
            self.assertTrue(M[mid]["dossiers"], mid)

    def test_lecture(self):
        R = [r for r in self.C["resumes"] if r.get("lecture")]
        for cours, n in (("CE1", 49), ("CE2", 49), ("CM2", 36)):
            rs = [r for r in R if r["cours"] == cours]
            self.assertEqual(len(rs), n, cours)
            for r in rs:
                self.assertTrue(r["manuel_note"].startswith("Texte du manuel officiel"), r["id"])
                self.assertEqual(len(r["exercices"]), 3, r["id"])
                self.assertTrue(r["regle"] and r["methode"] and r["exemple"] and r["vocabulaire"], r["id"])
        fid = {f["id"]: f for f in self.C["fiches"]}
        liees = [f for f in self.C["fiches"] if f.get("manuel", {}).get("texte")]
        self.assertGreater(len(liees), 100)
        couvert = {x for r in R for x in r["fiches"]}
        for f in liees:                                   # chaque séance rattachée a le résumé de son texte
            self.assertIn(f["id"], couvert, f["id"])
        for r in R:
            for x in r["fiches"]:
                self.assertEqual(fid[x]["manuel"]["texte"], r["manuel"]["texte"], (r["id"], x))
        self.assertTrue(any("2003-03" in r.get("actualisation", "") for r in R))           # excision : loi en vigueur
        cedeao = next(r for r in R if r["id"] == "rs131-cm2-lec-31")
        self.assertIn("12 États membres", cedeao["actualisation"])

    def test_maths(self):
        F = [f for f in self.C["fiches"] if f["matiere"] == "maths" and f.get("manuel")]
        self.assertGreater(len(F), 350)
        f = next(f for f in F if f["cours"] == "CM1" and f["manuel"]["dossier"] == 2 and f["manuel"]["sa"] == 2)
        self.assertEqual(f["manuel"]["sa_titre"], "La commercialisation des produits finis")
        self.assertEqual(f["manuel"]["pages"], "59-74")

    def test_diphtongues_ce1(self):
        F = [f for f in self.C["fiches"] if f["id"].startswith("mc131-ce1-diph-")]
        R = [r for r in self.C["resumes"] if r["id"].startswith("rs131-ce1-diph-")]
        self.assertEqual((len(F), len(R)), (32, 32))
        self.assertEqual({f["semaine"] for f in F}, {1, 2, 3, 4})
        self.assertTrue(all(r["fiches"] == [r["id"].replace("rs131", "mc131")] for r in R))
        self.assertTrue(all(r["mois"] in ("Septembre", "Octobre") for r in R))

    def test_mesures(self):
        self.assertGreaterEqual(len(self.C["mesures_correctives"]), 10)
        g = next(g for g in self.C["guides"] if g["id"] == "g-mc-2011")
        self.assertIn("diphtongues", g["html"])
        es = [f for f in self.C["fiches"] if f["matiere"] == "es" and f["cours"] == "CM2"]
        self.assertTrue(all("Activité préliminaire" in f.get("activite_preliminaire", "") for f in es))

    def test_ce2_complements(self):
        R = [r for r in self.C["resumes"] if r["id"].startswith(("rs131-ce2-es-", "rs131-ce2-est-"))]
        self.assertEqual(len(R), 17)
        self.assertTrue(any("Danxomè" in r["titre"] for r in R))
        vote = next(r for r in R if r["titre"] == "Le droit de vote")
        self.assertIn("12 avril", vote["regle"])

    def test_revisions(self):
        V = {v["cours"]: v for v in self.C["revisions"]}
        for c, ns in (("CM1", 2), ("CM2", 4)):
            v = V[c]
            self.assertGreaterEqual(len(v["sections"]), 14)
            self.assertEqual(len(v["sujets"]), ns)
            for s in v["sections"]:
                self.assertTrue(s["je_retiens"] and len(s["qr"]) >= 5 and s["exercices"] and s["schema"], s["titre"])
            for sj in v["sujets"]:
                self.assertEqual(sj["total"], 20, sj["titre"])
        self.assertIn("Romuald Wadagni", json.dumps(V["CM2"], ensure_ascii=False))
        self.assertNotIn("Patrice Talon est le président", json.dumps(V["CM2"], ensure_ascii=False))

    def test_guides_lot_b(self):
        G = {g["id"]: g for g in self.C["guides"]}
        for gid in ("g-memp-eps-ci", "g-memp-eps-cp", "g-memp-eps-ce", "g-memp-es-cm1", "g-memp-est-ce", "g-memp-ma-ce2", "g-memp-fr-ci"):
            self.assertIn(gid, G)
            self.assertEqual(G[gid]["statut"], "officiel")
        import html as _h; self.assertIn("J'apprends à me situer par rapport à un repère", _h.unescape(G["g-memp-eps-ci"]["html"]))
        eps_ci = [p for p in self.C["programmes"] if p["cours"] == "CI" and p["matiere"] == "eps"]
        self.assertEqual(len(eps_ci), 9)   # v2.1 : SA 2-3, 4-5 et 11-12 traitées ensemble (mesures correctives)
        lot = self.C["lots"]["lot131-manuels-mesures"]["guides"]
        self.assertTrue(any("LAHA" in d["decision"] for d in lot["doublons_ou_reference"]))


SCRIPT = r'''
import html, io, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
import pdfplumber
app.config["TESTING"] = True
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-2500:]); return r
def txt(r): return html.unescape(r.data.decode())
def pdf(r):
    assert r.mimetype == "application/pdf", r.mimetype
    d = pdfplumber.open(io.BytesIO(r.data))
    return d, " ".join((p.extract_text() or "") for p in d.pages)
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
t = txt(ok(c.get("/preparation/revisions")))
assert "rev-eveil-cm2" in t and "Révisions d'éveil" in t
t = txt(ok(c.get("/preparation/revisions/rev-eveil-cm2")))
assert "Questions-réponses du type CEP" in t and "Sujet type CEP" in t and "Corrigé" in t
t = txt(ok(c.get("/preparation/revisions/rev-eveil-cm2?eleve=1")))
assert "Corrigé :" not in t
d, s = pdf(ok(c.get("/preparation/revisions/rev-eveil-cm2.pdf")))
fonts = {ch["fontname"].split("+")[-1] for p in d.pages for ch in p.chars}
assert any(f.startswith("LiberationSerif") or f.startswith("Times") for f in fonts), fonts
tailles = [round(ch["size"]) for p in d.pages for ch in p.chars if ch["fontname"].split("+")[-1] in ("LiberationSerif", "LiberationSerif-Regular", "Times-Roman")]
assert max(set(tailles), key=tailles.count) == 14, sorted(set(tailles))
assert "Sujet type CEP" in s and "Romuald Wadagni" in s
d, s = pdf(ok(c.get("/preparation/revisions/rev-eveil-cm1.pdf?sujet=1&eleve=1")))
assert len(d.pages) == 1 and "Corrigé" not in s, (len(d.pages), s[:300])
ok(c.get("/preparation/revisions/rev-eveil-cm1.pdf?sujet=9"), 404)
d, s = pdf(ok(c.get("/preparation/revisions/rev-eveil-cm2.pdf?partie=est")))
assert "SCIENTIFIQUE" in s and "royaume" not in s.lower()
t = txt(ok(c.get("/preparation/manuels")))
assert "Je lis tout seul" in t and "Les tics de Koladé" in t and "Mesures correctives" in t
t = txt(ok(c.get("/preparation/resumes/rs131-cm2-lec-01")))
assert "Ce que dit le texte" in t and "Texte du manuel officiel" in t and "Questions de compréhension" in t
d, s = pdf(ok(c.get("/preparation/resumes/rs131-ce2-lec-02.pdf")))
assert "Ce que dit le texte" in s and "aujourd'hui" in s.lower()
t = txt(ok(c.get("/preparation/resumes/rs131-ce1-diph-09")))
assert "or, ar" in t
import m_preparation as M
C = M.corpus()
f = next(f for f in C["fiches"] if f["cours"] == "CM2" and f.get("manuel", {}).get("texte") == 1)
t = txt(ok(c.get("/preparation/fiches/" + f["id"])))
assert "Manuel officiel" in t and "Les tics de Koladé" in t
f = next(f for f in C["fiches"] if f["cours"] == "CE2" and f["matiere"] == "es")
t = txt(ok(c.get("/preparation/fiches/" + f["id"])))
assert "Activité préliminaire" in t
t = txt(ok(c.get("/preparation/guides")))
assert "Mesures correctives (MEMP, 2011)" in t
t = txt(ok(c.get("/cep")))
assert "rev-eveil-cm2" in t
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestPages131(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")


if __name__ == "__main__":
    unittest.main()
