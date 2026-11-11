# -*- coding: utf-8 -*-
"""Tests 1.20 : lot 3 — fiches APC conçues d'après les inventaires CI / CP / CE2 / CM2 (recueils de référence : structure
seulement), fiches d'EST CM2 transmises par la CS (importées, dédoublonnées), guides officiels CM1 (Français,
Mathématiques, EPS, EST), titres de SA ajoutés aux programmes, actualisation de l'Éducation sociale (faits vérifiés,
sources, résumés « Éducation sociale » CE1 → CM2, guide d'actualité), état du lot 3 dans « Fiches et guides manquants » ;
éditions école privée et école publique.
Lancer : python3 -m unittest tests.test_v120"""
import gzip
import json
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import html, io, json, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-1500:]); return r
def txt(r): return html.unescape(r.data.decode())
def texte_pdf(r):
    import pdfplumber
    assert r.mimetype == "application/pdf", (r.request.path, r.mimetype)
    with pdfplumber.open(io.BytesIO(r.data)) as d:
        return "\n".join(p.extract_text() or "" for p in d.pages), len(d.pages)
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
import m_preparation as MP
C = MP.corpus()
MENTION = "Conçue selon l'APC — à valider par le conseiller pédagogique"
L3 = [f for f in C["fiches"] if f["id"].startswith("lot3-")]
par = {}
for f in L3:
    par[f["cours"]] = par.get(f["cours"], 0) + 1
    assert f["statut"] == "concue" and f["mention"].startswith(MENTION) and "(lot 3)" in f["source"], f["id"]
    assert [p[0] for p in f["deroulement"]] == ["**INTRODUCTION**", "**RÉALISATION**", "**RETOUR ET PROJECTION**"], f["id"]
    assert all("**Enseignant(e)**" in p[1] and "**Apprenants**" in p[1] and p[2] for p in f["deroulement"]), f["id"]
    for k in ("cd", "ct", "contenus", "strategies", "materiel", "duree", "evaluation", "je_retiens", "titre", "unite"):
        assert f[k], (f["id"], k)
assert par.get("CI", 0) >= 600 and par.get("CP", 0) >= 600 and par.get("CM2", 0) >= 200 and par.get("CE2", 0) >= 100, par
assert len({f["id"] for f in L3}) == len(L3)
st = C["lots"]["lot3-inventaire"]
assert set(st) >= {"CI", "CP", "CE2", "CM2"} and st["CP"]["reference"] == 799 and st["CM2"]["reference"] == 603
# priorités : CP français et ES / EPS, CM2 ES et EA, CI français
def n(c, m): return sum(1 for f in L3 if f["cours"] == c and f["matiere"] == m)
assert n("CP", "francais") >= 400 and n("CP", "es") >= 60 and n("CP", "eps") >= 60 and n("CM2", "es") >= 90 and n("CM2", "ea") >= 60
assert n("CI", "francais") >= 400 and n("CI", "es") >= 80 and n("CI", "eps") >= 40 and n("CI", "ea") >= 40
lec = [f for f in L3 if f["cours"] == "CP" and f["sous_matiere"] == "Lecture-écriture"]
assert {f["titre"].split(" — ")[-1] for f in lec} >= {"découverte du texte et du son", "formation et lecture des syllabes", "écriture individuelle 1",
                                                       "formation et lecture des mots", "lecture récréative", "expression écrite"}
# ES actualisée : faits vérifiés et sources
pr = next(f for f in L3 if f["cours"] == "CM2" and f["titre"] == "Le président de la République")
assert "Romuald Wadagni" in pr["je_retiens"] and "sept ans" in pr["je_retiens"] and "Sources vérifiées le 27/10/2026" in pr["mention"]
an = next(f for f in C["fiches"] if f["id"] == "p10-5b19d8399227")
assert "109 députés" in an["je_retiens"] and "83 députés" not in an["je_retiens"] and "Sources vérifiées le 27/10/2026" in an["observations"]
assert not any("le maître complète avec le président issu" in f.get("je_retiens", "") for f in C["fiches"])
assert not any("5 ans, renouvelable une fois" in f.get("je_retiens", "") for f in C["fiches"] if f["matiere"] == "es")
RES = [r for r in C["resumes"] if r["collection"] == "Éducation sociale" and not r.get("seance_resume")]   # v1.29 : résumés de séance testés à part
assert {r["cours"] for r in RES} >= {"CE1", "CE2", "CM1", "CM2"} and len(RES) >= 16 and all(len(r["exercices"]) == 3 for r in RES)  # v1.23 : + CI, CP
assert all("Sources vérifiées le 27/10/2026" in r["mention"] for r in RES)
senat = next(r for r in RES if "Sénat" in r["titre"] and r["cours"] == "CM2")
gact = C["guide_par_id"]["g-es-actualite"]
assert "https://" in gact["html"] and "Sénat" in gact["html"] and "27/10/2026" in gact["titre"]
# EST CM2 de la CS et doublons
est = [f for f in C["fiches"] if f["id"].startswith("csest-cm2-")]
assert len(est) >= 25 and all(f["statut"] == "source" and "transmises par la CS" in f["source"] and f["deroulement"] for f in est)
assert [f["seance"] for f in est if f["sa"] == 1] == list(range(1, len([f for f in est if f["sa"] == 1]) + 1))
dbl = [d for d in C["doublons"] if d["lot"] == "lot3-est-cs"]
assert len(dbl) >= 10 and all(d["retire"] not in C["fiche_par_id"] for d in dbl if d["retire"] != "copie répétée")
# guides officiels CM1, EPS CM1 réalignée
for gid in ("g-memp-fr-cm1", "g-memp-ma-cm1", "g-memp-eps-cm1", "g-memp-est-cm1"):
    g = C["guide_par_id"][gid]
    assert g["statut"] == "officiel" and g["cours"] == ["CM1"] and g["groupe"] == "Guides officiels" and len(g["html"]) > 4000, gid
eps = [f for f in C["fiches"] if f["cours"] == "CM1" and f["matiere"] == "eps" and f.get("intitule")]
assert all(f["sa"] == 1 for f in eps if "lancer" in f["intitule"].lower()) and all(f["sa"] == 2 for f in eps if "coopération" in f["intitule"].lower())
assert any(p["id"] in ("off-cm1-eps-2", "mc-eps-cm1-sa2") for p in C["programmes"])  # v2.1 : programme en vigueur (mesures correctives)
assert True and any(p["id"].startswith("off-cm1-ma-d3") for p in C["programmes"])
assert any(p["id"].startswith(("ref-", "mc-")) for p in C["programmes"])  # v2.1 : ES / EPS remplacés par les mesures correctives
cp_lec = lec[0]
ci_co = next(f for f in L3 if f["cours"] == "CI" and f["sous_matiere"] == "Communication orale")

from urllib.parse import quote
c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
t = txt(ok(c.get("/preparation/manquants")))
assert "Lot 3 (v1.20)" in t and "Guides officiels CM1" in t and "Éducation sociale actualisée" in t and "Intrus écartés" in t
for x in ("CI", "CP", "CE2", "CM2"):
    assert f"<td>{x}</td>" in t
t = txt(ok(c.get(f"/preparation/fiches/{pr['id']}")))
assert "Romuald Wadagni" in t and "à valider par le conseiller pédagogique" in t and "Sources vérifiées" in t
s, npg = texte_pdf(ok(c.get(f"/preparation/fiches/{cp_lec['id']}.pdf")))
assert "FICHE DE PRÉPARATION" in s and "RETOUR ET" in s
t = txt(ok(c.get(f"/preparation/fiches/{ci_co['id']}")))
assert ci_co["titre"][:30] in t
t = txt(ok(c.get("/preparation/fiches?cours=CP&statut=concue&q=" + quote("lettres-son"))))
assert "fiche(s)" in t
t = txt(ok(c.get("/preparation/resumes?col=es")))
assert senat["titre"] in t and "Éducation sociale" in t
t = txt(ok(c.get(f"/preparation/resumes/{senat['id']}")))
assert "Patrice Talon" in t and "Sources vérifiées" in t
s, npg = texte_pdf(ok(c.get("/preparation/resumes.pdf?col=es&cours=CM1")))
assert "Wadagni" in s.replace("\n", " ")
t = txt(ok(c.get("/preparation/guides/g-memp-eps-cm1")))
assert "attitudes posturales" in t and "relevé par OCR" in t
t = txt(ok(c.get("/preparation/guides/g-es-actualite")))
assert "Joseph Djogbénou" in t and "Sources consultées" in t
t = txt(ok(c.get("/preparation/fiches?q=" + quote("EST CM2 transmises par la CS"))))
assert "fiche(s)" in t and est[0]["titre"][:20] in t
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestLot3(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")


class TestFichiers(unittest.TestCase):
    def lire(self, *p):
        with open(os.path.join(RACINE, *p), encoding="utf-8") as f:
            return f.read()

    def test_corpus_et_doc(self):
        with gzip.open(os.path.join(RACINE, "static", "pedafiche_corpus.json.gz"), "rt", encoding="utf-8") as f:
            c = json.load(f)
        brut = json.dumps(c, ensure_ascii=False)
        # aucune marque d'auteur ou d'éditeur des recueils de référence ni de coordonnées dans le corpus publié
        for interdit in ("SONDJO", "AFROMAUD", "ROMUALD 61", "61 47 7313", "DOUNOU", "COPAS", "Copas", "gmail", "@g ", "AnyScanner",
                         "imprimée par", "Fiche conçue et"):
            self.assertNotIn(interdit, brut, interdit)
        self.assertEqual(c["version"], 2)
        doc = self.lire("docs", "inventaire_fiches.md")
        for x in ("## CI — inventaire", "## CP — inventaire", "## CE2 — inventaire", "## CM2 — inventaire", "Guides officiels CM1",
                  "## Doublons (lot 3)", "Intrus écartés", "Sources :", "https://"):
            self.assertIn(x, doc)
        self.assertNotIn("SONDJO", doc)
        self.assertFalse(os.path.exists(os.path.join(RACINE, "docs", "inventaire_cm1.md")))


if __name__ == "__main__":
    unittest.main()
