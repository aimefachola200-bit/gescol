# -*- coding: utf-8 -*-
"""Tests 1.29 : un résumé pour chaque séance de la progression (CI, CP, CE1 ; six matières) — chaque fiche de séance du
corpus a son résumé (au plus trois séances consécutives par résumé, hors bilans), les séances prévues par les programmes
sans fiche ont reçu une fiche APC conçue avec son résumé ; Français par outils de la langue, Mathématiques par domaines ;
affichage sur la fiche de la séance, dans l'onglet Résumés (résumés de séance, livret de SA, cahier de résumés) et dans la
planification (résumés de la semaine) ; PDF par résumé, par SA et par cours × matière.
Lancer : python3 -m unittest tests.test_v129"""
import gzip
import json
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
COURS_LOT = ("CI", "CP", "CE1")
MATS = ("francais", "maths", "es", "est", "eps", "ea")
OUTILS_FR = {"Sons et graphies", "Structures de la langue", "Grammaire", "Conjugaison", "Orthographe", "Vocabulaire", "Lecture",
             "Expression écrite", "Écriture", "Communication orale"}
DOMAINES_MA = {"Numération et arithmétique", "Mesures", "Géométrie", "Résolution de problèmes"}


def corpus():
    with gzip.open(os.path.join(RACINE, "static", "pedafiche_corpus.json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


def verifier_cours(test, C, cours_liste, minimum=900):
    rpf = {}
    for r in C["resumes"]:
        for fid in r.get("fiches") or []:
            rpf.setdefault(fid, []).append(r)
    manque = [(f["cours"], f["matiere"], f["titre"]) for f in C["fiches"] if f["cours"] in cours_liste and f["matiere"] in MATS and f["id"] not in rpf]
    test.assertEqual(manque, [], manque[:20])
    lot = C["lots"]["v129-resumes-seances"]["table"]
    for c in cours_liste:
        for m in MATS:
            t = lot[c][m]
            test.assertEqual(t["couvertes"], t["seances"], (c, m))
            test.assertGreater(t["resumes"], 0, (c, m))
    rs = [r for r in C["resumes"] if r.get("seance_resume") and r["cours"] in cours_liste]
    test.assertGreater(len(rs), minimum)
    ids = set()
    for r in rs:
        test.assertNotIn(r["id"], ids)
        ids.add(r["id"])
        test.assertEqual(len(r["exercices"]), 3, r["id"])
        test.assertTrue(r["regle"] and r["exemple"] and r["titre"], r["id"])
        test.assertTrue(all(e["q"] and e["r"] for e in r["exercices"]), r["id"])
        test.assertIn("à valider par le conseiller pédagogique", r["mention"], r["id"])
        test.assertIn(r["trimestre"], ("I", "II", "III"), r["id"])
        test.assertTrue(r["mois"] and r["ancres"] and r["fiches"], r["id"])
        if not r.get("bilan"):
            test.assertLessEqual(len(r["ancres"]), 3, r["id"])
        if r["matiere"] == "francais":
            test.assertIn(r["domaine"], OUTILS_FR, r["id"])
        if r["matiere"] == "maths":
            test.assertIn(r["domaine"], DOMAINES_MA, r["id"])
    brut = json.dumps(rs, ensure_ascii=False)
    for interdit in ("gmail", "SONDJO", "AFROMAUD", "MARIUS", "COPAS", "HOUNGBEDJI", "PIOILALOUBI", "@jacques"):
        test.assertNotIn(interdit, brut)
    # fiches conçues pour les séances du programme sans fiche
    fc = [f for f in C["fiches"] if f.get("v129") and f["cours"] in cours_liste]
    test.assertGreater(len(fc), 150)
    for f in fc:
        test.assertEqual(f["statut"], "concue", f["id"])
        test.assertTrue(f["mention"].startswith("Conçue selon l'APC"), f["id"])
        test.assertEqual([p[0] for p in f["deroulement"]], ["**INTRODUCTION**", "**RÉALISATION**", "**RETOUR ET PROJECTION**"], f["id"])
        for k in ("cd", "ct", "contenus", "objectifs", "evaluation", "je_retiens", "titre", "duree"):
            test.assertTrue(f[k], (f["id"], k))
        test.assertIn(f["id"], rpf, f["id"])


SCRIPT = r'''
import html, io, os, re, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
import m_preparation as MP
app.config["TESTING"] = True
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-2500:]); return r
def txt(r): return html.unescape(r.data.decode())
def texte_pdf(r):
    import pdfplumber
    assert r.mimetype == "application/pdf", (r.request.path, r.mimetype)
    with pdfplumber.open(io.BytesIO(r.data)) as d:
        return "\n".join(p.extract_text() or "" for p in d.pages).replace("\n", " "), len(d.pages)
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
C = MP.corpus()
RS = [r for r in C["resumes"] if r.get("seance_resume") and r["cours"] in ("CI", "CP", "CE1")]
# onglet Résumés : tableau des séances couvertes, résumés de séance seulement, progression
t = txt(ok(c.get("/preparation/resumes")))
assert "Un résumé pour chaque séance de la progression" in t and "titres à vérifier" in t
t = txt(ok(c.get("/preparation/resumes?cours=CI&matiere=maths&seances=1&vue=progression")))
assert "Cahier de résumés (séances)" in t and "Livret d'une SA" in t and "Trimestre I" in t
r0 = next(r for r in RS if r["cours"] == "CI" and r["matiere"] == "maths")
assert r0["titre"] in t
# fiche d'une séance -> son résumé ; résumé -> ses séances (liens vers les fiches)
fid = r0["fiches"][0]
t = txt(ok(c.get(f"/preparation/fiches/{fid}")))
assert "Résumé de la séance" in t and r0["titre"] in t
t = txt(ok(c.get(f"/preparation/resumes/{r0['id']}")))
assert "Séance(s) de la progression" in t and r0["regle"][:40] in t
# fiche conçue (séance du programme sans fiche) et son résumé
fc = next(f for f in C["fiches"] if f.get("v129") and f["cours"] == "CE1" and f["matiere"] == "francais")
t = txt(ok(c.get(f"/preparation/fiches/{fc['id']}")))
assert "Résumé de la séance" in t and "Conçue selon l'APC" in t
ok(c.get(f"/preparation/fiches/{fc['id']}.pdf"))
# PDF : un résumé, version élève, livret de SA, cahier de résumés
s, n = texte_pdf(ok(c.get(f"/preparation/resumes/{r0['id']}.pdf")))
assert "Séance(s)" in s and n >= 1
s, n = texte_pdf(ok(c.get(f"/preparation/resumes/{r0['id']}.pdf?eleve=1")))
assert "Réponse :" not in s
sa = next(r for r in RS if r["cours"] == "CI" and r["matiere"] == "maths" and r["sa"])["sa"][0]
s, n = texte_pdf(ok(c.get(f"/preparation/resumes.pdf?cours=CI&matiere=maths&sa={sa}")))
assert "LIVRET DE LA" in s.upper()
s, n = texte_pdf(ok(c.get("/preparation/resumes.pdf?cours=CE1&matiere=es&seances=1")))
assert "CAHIER DE RÉSUMÉS" in s.upper() and n >= 2
# planification : les résumés de la semaine sont ceux des séances (fiches) de la semaine
for cours, mat in (("CI", "francais"), ("CP", "maths"), ("CE1", "est")):
    fs = [f for f in C["fiches"] if f["cours"] == cours and f["matiere"] == mat][:3]
    rs = MP.resumes_semaine(cours, {mat: fs})[mat]
    fids = {f["id"] for f in fs}
    assert rs and all(set(r.get("fiches") or []) & fids for r in rs if r.get("seance_resume")), (cours, mat)
# résumés du mois (progression annuelle) : EPS et EA aussi
assert MP.resumes_mois("CI", "Octobre").get("eps") or MP.resumes_mois("CI", "Novembre").get("eps")
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestCorpusSeances(unittest.TestCase):
    def test_chaque_seance_a_son_resume(self):
        verifier_cours(self, corpus(), COURS_LOT)


class TestPagesResumes(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")


if __name__ == "__main__":
    unittest.main()
