# -*- coding: utf-8 -*-
"""Tests 1.23 : résumés « l'essentiel à retenir » pour chaque cours (CI → CM2) dans chaque matière (Français,
Mathématiques, Éducation sociale, EST, EPS, Éducation artistique), rattachés aux SA / unités ; tableau cours × matière
dans l'onglet Résumés ; « Résumés de la semaine » dans la planification ; PDF enseignant / élève ; éditions privée et publique.
Lancer : python3 -m unittest tests.test_v123"""
import gzip
import json
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
COURS = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
MATS = ["francais", "maths", "es", "est", "eps", "ea"]

SCRIPT = r'''
import html, io, json, os, sys, tempfile
from datetime import date, timedelta
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-1500:]); return r
def txt(r): return html.unescape(r.data.decode())
def texte_pdf(r):
    import pdfplumber
    assert r.mimetype == "application/pdf", (r.request.path, r.mimetype)
    with pdfplumber.open(io.BytesIO(r.data)) as d:
        return "\n".join(p.extract_text() or "" for p in d.pages), len(d.pages)
import m_preparation as MP
C = MP.corpus()
R = C["resumes"]
COURS = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
MATS = ["francais", "maths", "es", "est", "eps", "ea"]
T = MP.table_resumes(R)
manque = [(c, m) for c in COURS for m in MATS if T[(c, m)] < 1]
assert not manque, manque
assert all(T[(c, "francais")] >= 7 for c in COURS) and T[("CI", "est")] >= 7 and T[("CP", "est")] >= 7
N = [r for r in R if r["id"].startswith("r123-")]
assert len(N) >= 150 and all(len(r["exercices"]) == 3 and r["regle"] and r["methode"] and r["exemple"] for r in N)
assert all(r["mention"].startswith("Résumé original conçu selon le programme — à valider par le conseiller pédagogique") for r in N)
assert all(MP.COLLECTION_DE[r["collection"]] for r in R)
# EST : un résumé par SA du programme, CI → CM2
for p in C["programmes"]:
    if p["matiere"] == "est" and p["id"].startswith("ea-est-"):
        assert any(r["cours"] == p["cours"] and r["matiere"] == "est" and p["num"] in (r.get("sa") or []) for r in R), p["id"]
# Français CE1 → CM2 : toutes les sous-matières
for c in ("CE1", "CE2", "CM2"):
    doms = {r["domaine"] for r in R if r["cours"] == c and r["matiere"] == "francais"}
    assert doms >= {"Grammaire", "Conjugaison", "Orthographe", "Vocabulaire", "Lecture", "Expression écrite"}, (c, doms)
# ES : faits vérifiés (sources) sur tous les résumés de la collection, CI → CM2
ES = [r for r in R if r["collection"] == "Éducation sociale" and not r.get("seance_resume")]   # v1.29 : résumés de séance testés à part
assert {r["cours"] for r in ES} == set(COURS) and all("Sources vérifiées le 27/10/2026" in r["mention"] for r in ES)
# rattachement à la semaine
fi = [f for f in C["fiches"] if f["cours"] == "CE1" and f["matiere"] == "francais" and f.get("sous_matiere") == "Grammaire" and MP._num_fiche(f) == 5]
if fi:
    rs = MP.resumes_semaine("CE1", {"francais": fi})["francais"]
    assert any("adjectif" in r["titre"] for r in rs) and all(r["domaine"] == "Grammaire" for r in rs if not r.get("seance_resume")), [r["titre"] for r in rs]
est = [f for f in C["fiches"] if f["cours"] == "CE2" and f["matiere"] == "est" and f.get("sa") == 8]
assert est, "fiches EST CE2 SA8"
assert [r["titre"] for r in MP.resumes_semaine("CE2", {"est": est})["est"] if not r.get("seance_resume")] == ["Jouons avec les aimants"]   # v1.30 : résumés de séance à part
assert MP.resumes_semaine("CM2", {"maths": []}) == {}
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    ci = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CI A','CI',0,1)")
    cm1 = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM1 A','CM1',0,1)")
c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
t = txt(ok(c.get("/preparation/resumes")))
assert "Résumés par cours et par matière" in t and "Éducation physique et sportive" in t and "Éducation artistique" in t
brut = ok(c.get("/preparation/resumes")).data.decode()
for c_ in COURS:
    assert f"cours={c_}&amp;matiere=eps" in brut or f"matiere=eps&amp;cours={c_}" in brut, c_
t = txt(ok(c.get("/preparation/resumes?cours=CI&matiere=francais")))
assert "Les voyelles : a, e, i, o, u, y" in t and "Français CI → CM2" in t
for col in ("francais", "est", "eps", "ea", "es", "maths"):
    t = txt(ok(c.get(f"/preparation/resumes?col={col}&cours=CP")))
    assert "Aucun résumé pour ce choix" not in t, col
r1 = next(r for r in N if r["cours"] == "CP" and r["matiere"] == "est")
t = txt(ok(c.get(f"/preparation/resumes/{r1['id']}")))
assert r1["titre"] in t and "à valider par le conseiller pédagogique" in t
t = txt(ok(c.get(f"/preparation/resumes/{r1['id']}?eleve=1")))
assert r1["exercices"][0]["q"][:20] in t
for cours, mat in (("CI", "maths"), ("CE1", "francais"), ("CM2", "eps"), ("CE2", "ea"), ("CP", "es")):
    s, npg = texte_pdf(ok(c.get(f"/preparation/resumes.pdf?cours={cours}&matiere={mat}")))
    s = s.replace("\n", " ")
    assert npg >= 1 and len(s) > 400, (cours, mat)
    s2, _ = texte_pdf(ok(c.get(f"/preparation/resumes.pdf?cours={cours}&matiere={mat}&eleve=1")))
    assert "Réponse :" in s and "Réponse :" not in s2 and "version élève" in s2.replace("\n", " "), (cours, mat)
s, npg = texte_pdf(ok(c.get(f"/preparation/resumes/{r1['id']}.pdf")))
assert "à valider" in s.replace("\n", " ")
# planification : résumés de la semaine
lundi = date.today() - timedelta(days=date.today().weekday())
for cl in (ci, cm1):
    t = txt(ok(c.get(f"/preparation/planification?classe={cl}&vue=semaine&date={lundi.isoformat()}")))
    assert "Résumés de la semaine" in t
t = txt(ok(c.get(f"/preparation/planification?classe={cm1}&vue=semaine&date=2026-11-09")))
assert "Résumés de la semaine" in t
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestResumesParCours(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")


class TestFichiers(unittest.TestCase):
    def test_corpus_table(self):
        with gzip.open(os.path.join(RACINE, "static", "pedafiche_corpus.json.gz"), "rt", encoding="utf-8") as f:
            c = json.load(f)
        tab = {}
        for r in c["resumes"]:
            tab[(r["cours"], r["matiere"])] = tab.get((r["cours"], r["matiere"]), 0) + 1
        for co in COURS:
            for m in MATS:
                self.assertGreaterEqual(tab.get((co, m), 0), 1, (co, m))
        lot = c["lots"]["v123-resumes"]
        self.assertLessEqual(lot["total"], len(c["resumes"]))   # v1.25 : résumés ajoutés depuis (lot v125-resumes)
        ids = [r["id"] for r in c["resumes"]]
        self.assertEqual(len(ids), len(set(ids)))
        brut = json.dumps(c["resumes"], ensure_ascii=False)
        for interdit in ("gmail", "SONDJO", "AFROMAUD"):
            self.assertNotIn(interdit, brut)

    def test_gabarits(self):
        with open(os.path.join(RACINE, "templates", "prep_resumes.html"), encoding="utf-8") as f:
            self.assertIn("Résumés par cours et par matière", f.read())
        with open(os.path.join(RACINE, "templates", "prep_planif.html"), encoding="utf-8") as f:
            self.assertIn("Résumés de la semaine", f.read())


if __name__ == "__main__":
    unittest.main()
