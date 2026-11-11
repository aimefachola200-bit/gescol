# -*- coding: utf-8 -*-
"""Tests 1.21 : évaluations (banque d'épreuves mensuelles, trimestrielles, de passage et examens blancs du CEP selon
l'organigramme INFRE ; corrigés types et grilles ; PDF / Word ; modification, régénération, « créer l'évaluation »),
planification journalière / hebdomadaire / mensuelle d'une classe (emploi du temps × planification × fiches ; cases
modifiables ; PDF / Excel), classeurs de fiches (PDF avec sommaire, Word, zip) ; éditions école privée et publique,
périmètre de l'enseignant.
Lancer : python3 -m unittest tests.test_v121"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import html, io, json, os, sys, tempfile, zipfile
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
import banque_epreuves as B
# ---- banque : volume, structure, barèmes, organigramme
n = 0
par = {}
for c in B.COURS:
    for p in B.periodes_du_cours(c):
        for d in B.jeu_complet(c, p[0], {}):
            n += 1
            par[(c, d["type"])] = par.get((c, d["type"]), 0) + 1
            assert abs(B.total_bareme(d) - 20) < 0.01, d["cle"]
            assert d["mention"] == "Épreuve conçue selon l'APC — à valider par le conseiller pédagogique"
            assert d["tache"].startswith("Tu es invité") and d["grille"] and d["consignes"], d["cle"]
assert n >= 490, n
assert {c for c, t in par if t == "passage"} == {"CI", "CP", "CE1", "CE2", "CM1"} and par[("CM2", "cep_blanc")] == 24   # v1.30 : dictée, EA, EPS
assert all(par[(c, "mensuelle")] == 48 for c in B.COURS) and all(par[(c, "trimestrielle")] == 24 for c in B.COURS)
assert [e["code"] for e in B.organigramme("CM1")][:2] == ["expr", "comp"] and [e["code"] for e in B.organigramme("CE1")][:2] == ["comp", "expr"]
assert B.organigramme("CE2")[0]["duree"] == "45 minutes" and B.organigramme("CI")[0]["duree"] == "30 min"
infre = [d for c in ("CE1", "CE2", "CM1", "CM2") for p in ("T1", "T2", "T3", "FA") for d in B.jeu_complet(c, p, {}) if d.get("infre")]
assert len(infre) == 32 and all(d["source"].startswith("D'après les épreuves standardisées INFRE") for d in infre)
d = B.jeu_complet("CM2", "C1", {})
assert [x["code"] for x in d] == ["dictee", "expr", "comp", "math", "est", "es", "ea", "eps"]   # ordre du PV du CEP (v1.30)
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    cm1 = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM1 A','CM1',0,1)")
    ce2 = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CE2 B','CE2',0,1)")
    uid = ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) VALUES ('ens1','HOUNSOU Awa','enseignant',?,0,1,1)",
             (generate_password_hash("ens-mdp-123"),))
    ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,NULL)", (uid, cm1))
AUJ = date.today()
lundi = AUJ - timedelta(days=AUJ.weekday())

def parcours(c, directeur):
    t = txt(ok(c.get("/preparation/evaluations?cours=CM1")))
    assert "Banque d'épreuves" in t and "Premier trimestre" in t and "Évaluation mensuelle — octobre" in t and "Créer l'évaluation — CM1 A" in t
    t = txt(ok(c.get("/preparation/evaluations/organigramme")))
    assert "Organigramme des épreuves (INFRE)" in t and "Compréhension de l'écrit" in t and "45 minutes" in t
    cle = "CM1-T1-comp"
    t = txt(ok(c.get(f"/preparation/evaluations/e/{cle}")))
    assert "Le carnet de vaccination de Bilal" in t and "Corrigé type" in t and "Grille de correction" in t and "INFRE (2014)" in t
    s, npg = texte_pdf(ok(c.get(f"/preparation/evaluations/e/{cle}.pdf")))
    assert "COURS" in s and "PÉRIODE" in s and "Tâche" in s and "Item 1" in s and "réponse attendue" not in s.lower()
    s, npg = texte_pdf(ok(c.get(f"/preparation/evaluations/e/{cle}.pdf?partie=corrige")))
    assert "CORRIGÉ TYPE" in s and "rougeole" in s
    s, npg = texte_pdf(ok(c.get(f"/preparation/evaluations/e/CM1-T1-expr.pdf?partie=grille")))
    assert "Pertinence" in s and "Cohérence" in s and "Total" in s
    r = ok(c.get(f"/preparation/evaluations/e/{cle}.docx?partie=corrige"))
    # v2.2 : vrai document Word (.docx) au lieu d'une page HTML nommée « .doc »
    import zipfile as _zf, io as _io
    assert r.mimetype.endswith("wordprocessingml.document") and "Réponse attendue" in _zf.ZipFile(_io.BytesIO(r.data)).read("word/document.xml").decode("utf-8")
    s, npg = texte_pdf(ok(c.get("/preparation/evaluations/jeu.pdf?cours=CM1&periode=M1")))
    assert npg >= 5 and "Mathématique".upper() in s.upper()
    ok(c.get("/preparation/evaluations/e/CM2-FA-comp"), 404)        # pas d'évaluation de passage au CM2 (CEP)
    ok(c.get("/preparation/evaluations/e/CM1-C1-comp"), 404)        # pas de CEP blanc au CM1
    ok(c.post(f"/preparation/evaluations/e/{cle}/modifier", data={"contexte": "Contexte modifié par l'école.", "q_0_0": "Question modifiée ?", "r_0_0": "Réponse modifiée.", "p_0_0": "3"}), 302)
    t = txt(ok(c.get(f"/preparation/evaluations/e/{cle}")))
    assert "Contexte modifié par l'école." in t and "Question modifiée ?" in t and "version modifiée" in t
    ok(c.post(f"/preparation/evaluations/e/{cle}/regenerer", data={"banque": "1"}), 302)
    assert "Contexte modifié" not in txt(ok(c.get(f"/preparation/evaluations/e/{cle}")))
    ok(c.post("/preparation/evaluations/e/CM1-M1-es/regenerer", data={}), 302)
    t = txt(ok(c.get("/preparation/evaluations/e/CM1-M1-es")))
    assert "régénérée" in t and "Progression prise en compte" in t
    r = ok(c.post("/preparation/evaluations/creer", data={"classe": cm1, "periode": "T1"}), 302)
    assert "/evaluations/" in r.headers["Location"]
    with app.app_context():
        ev = q("SELECT * FROM evaluations WHERE classe_id=? ORDER BY id DESC", (cm1,), un=True)
        assert ev["type"] == "sommative" and len(json.loads(ev["matieres"])) >= 5, dict(ev)
    # ---- planification
    t = txt(ok(c.get(f"/preparation/planification?classe={cm1}&vue=semaine&date={lundi.isoformat()}")))
    assert "Planification de la classe" in t and "Lundi" in t and "Mathématiques" in t
    t = txt(ok(c.get(f"/preparation/planification?classe={cm1}&vue=jour&date={lundi.isoformat()}")))
    assert "Fiche à utiliser" in t
    ok(c.post("/preparation/planification/case", data={"classe": cm1, "date": lundi.isoformat(), "creneau": 1, "matiere": "francais",
                                                       "sous_matiere": "Lecture", "fiche_titre": "Ma séance de lecture", "note": "Apporter les livres", "vue": "jour"}), 302)
    t = txt(ok(c.get(f"/preparation/planification?classe={cm1}&vue=jour&date={lundi.isoformat()}")))
    assert "Ma séance de lecture" in t and "Apporter les livres" in t and "modifié" in t
    t = txt(ok(c.get(f"/preparation/planification?classe={cm1}&vue=mois&date={lundi.isoformat()}")))
    assert "Semaine du" in t
    s, npg = texte_pdf(ok(c.get(f"/preparation/planification.pdf?classe={cm1}&vue=semaine&date={lundi.isoformat()}")))
    assert "PLANIFICATION HEBDOMADAIRE" in s and "CM1 A" in s
    r = ok(c.get(f"/preparation/planification.xlsx?classe={cm1}&vue=jour&date={lundi.isoformat()}"))
    assert r.data[:2] == b"PK"
    # ---- classeur (la planification officielle du CM1 cite des SA / unités chaque mois)
    r = c.get(f"/preparation/classeur?classe={cm1}&portee=semaine&date=2026-11-09")
    if r.status_code == 200:
        s, npg = texte_pdf(r)
        assert "CLASSEUR DES FICHES DE LA SEMAINE" in s and "SOMMAIRE" in s and npg >= 2
        r = ok(c.get(f"/preparation/classeur?classe={cm1}&portee=semaine&date=2026-11-09&format=zip"))
        z = zipfile.ZipFile(io.BytesIO(r.data))
        assert any(n.endswith(".pdf") for n in z.namelist()) and any(n.endswith((".doc", ".docx")) for n in z.namelist())
    else:
        assert r.status_code == 302
    if not directeur:
        ok(c.get("/preparation/evaluations/e/CE2-T1-comp"), 403)            # CE2 : hors de ses classes
        r = c.get(f"/preparation/planification?classe={ce2}")
        assert r.status_code == 403, r.status_code
        assert "CE2" not in txt(ok(c.get("/preparation/evaluations"))).split("Cours")[1][:200]
    else:
        ok(c.get("/preparation/evaluations/e/CE2-T1-comp"))

c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
t = txt(ok(c.get("/preparation")))
assert "Évaluations et épreuves" in t and "Planification et classeurs" in t
parcours(c, True)
ok(c.get("/logout"), 302)
c = app.test_client()
ok(c.post("/login", data={"identifiant": "ens1", "mdp": "ens-mdp-123"}), 302)
parcours(c, False)
ok(c.get("/logout"), 302)
if "ens_portail" in app.view_functions:
    c = app.test_client()
    ok(c.post("/enseignant", data={"identifiant": "ens1", "mdp": "ens-mdp-123"}), 302)
    assert "Banque d'épreuves" in txt(ok(c.get("/preparation/evaluations")))
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestEvaluationsPlanification(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")


class TestFichiers(unittest.TestCase):
    def test_textes_originaux(self):
        import importlib
        sys.path.insert(0, RACINE)
        bx = importlib.import_module("banque_textes")
        brut = repr(bx.T) + repr(bx.DICTEES)
        # supports des épreuves INFRE : reformulés, jamais recopiés
        for interdit in ("J'ai grandi", "Saliou", "Kpankou", "Babalola", "Anita", "Comlan", "Porga", "Dansou aimait"):
            self.assertNotIn(interdit, brut)


if __name__ == "__main__":
    unittest.main()
