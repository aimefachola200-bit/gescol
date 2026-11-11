# -*- coding: utf-8 -*-
"""Tests 1.30 : (1) un résumé pour chaque séance de la progression du CE2 au CM2 (six matières) et fiches APC conçues
pour les séances du programme sans fiche ; (2) épreuves : dictée (et questions du CE2 au CM2, barème des fautes), EA
(A : dessin / arts plastiques, B : couture / travaux manuels, grille critériée) et EPS (course + saut, lancer ou jeu,
barèmes filles / garçons par âge, fiche de notation) à toutes les évaluations ; Times New Roman 14 pt (Liberation Serif
incorporée) ; deux exemplaires par feuille quand le sujet est court ; onglet Modifier (en-tête, version locale, original,
copies).
Lancer : python3 -m unittest tests.test_v130"""
import io
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "tests"))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
COURS_LOT = ("CE2", "CM1", "CM2")


class TestCorpusSeances(unittest.TestCase):
    def test_chaque_seance_a_son_resume(self):
        import test_v129 as T
        T.verifier_cours(self, T.corpus(), COURS_LOT, minimum=800)


class TestBanqueEpreuves(unittest.TestCase):
    def test_organigramme_et_contenus(self):
        import banque_epreuves as B
        par = {}
        for c in B.COURS:
            for p in B.periodes_du_cours(c):
                codes = [e["code"] for e in B.organigramme(c, p[2])]
                for x in ("dictee", "ea", "eps", "math", "es", "est"):
                    self.assertIn(x, codes, (c, p[0]))
                for d in B.jeu_complet(c, p[0], {}):
                    par[(c, d["type"])] = par.get((c, d["type"]), 0) + 1
                    self.assertAlmostEqual(B.total_bareme(d), 20, places=2, msg=d["cle"])
                    self.assertAlmostEqual(sum(g["points"] for g in d["grille"]), 20, places=2, msg=d["cle"])
                    if d["code"] == "dictee":
                        self.assertTrue(d["support"], d["cle"])
                        if c in ("CE2", "CM1", "CM2"):
                            qs = next(it for it in d["consignes"] if it["titre"] == "Questions")["questions"]
                            self.assertEqual(len(qs), 3, d["cle"])
                            self.assertTrue(all(x["r"] for x in qs), d["cle"])
                            self.assertTrue(any("Faute grave" in i for g in d["grille"] for i in g["indicateurs"]), d["cle"])
                    if d["code"] == "ea":
                        self.assertEqual([pa["partie"] for pa in d["parties_ea"]], ["A", "B"], d["cle"])
                        self.assertTrue(all(pa["materiel"] for pa in d["parties_ea"]), d["cle"])
                        self.assertEqual(len(d["grille"]), 8, d["cle"])
                    if d["code"] == "eps":
                        self.assertEqual(len(d["baremes"]), 2, d["cle"])
                        self.assertTrue(d["fiche_notation"]["lignes"] >= 20, d["cle"])
                        b0 = d["baremes"][0]["lignes"]
                        self.assertEqual([l[0] for l in b0], [10, 8, 6, 4, 2], d["cle"])
                        self.assertEqual(len(b0[0]), 5, d["cle"])        # note, garçons (âge, âge + 2), filles (âge, âge + 2)
        for c in B.COURS:
            self.assertEqual(par[(c, "mensuelle")], 48, c)
            self.assertEqual(par[(c, "trimestrielle")], 24, c)
        self.assertEqual(par[("CM2", "cep_blanc")], 24)
        self.assertEqual([e["code"] for e in B.organigramme("CM2", "cep_blanc")], ["dictee", "expr", "comp", "math", "est", "es", "ea", "eps"])

    def test_police_serif(self):
        import pdfs
        f = pdfs.police_serif()
        self.assertIn(f["normal"], ("LiberationSerif-Regular", "Times-Roman"))
        self.assertTrue(os.path.exists(os.path.join(RACINE, "static", "fonts", "LiberationSerif-Regular.ttf")))
        self.assertTrue(os.path.exists(os.path.join(RACINE, "static", "fonts", "LICENSE-LiberationSerif-OFL.txt")))


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
# ---- rendu : police Times (Liberation Serif) 14 pt, accents et œ
d, s = pdf(ok(c.get("/preparation/evaluations/e/CM1-T1-comp.pdf")))
fonts = {ch["fontname"].split("+")[-1] for p in d.pages for ch in p.chars}
assert any(f.startswith("LiberationSerif") or f.startswith("Times") for f in fonts), fonts
tailles = [round(ch["size"]) for p in d.pages for ch in p.chars if ch["fontname"].split("+")[-1] in ("LiberationSerif", "LiberationSerif-Regular", "Times-Roman")]
assert tailles and max(set(tailles), key=tailles.count) == 14, sorted(set(tailles))
assert d.pages[0].width < d.pages[0].height                         # sujet long : un par page (portrait)
assert "PÉRIODE" in s and "épreuve".upper() in s.upper()
d, s = pdf(ok(c.get("/preparation/evaluations/e/CM2-M3-dictee.pdf?partie=corrige")))
assert "Faute grave" in s and "Questions" in s
s = pdf(ok(c.get("/preparation/evaluations/e/CM1-M1-ea.pdf")))[1]
assert "vœux" in s and "Éducation".upper() in s.upper() and "à" in s, s[:400]          # accents et ligature œ
# ---- deux par page quand le sujet est court (dictée) ; forcé à 1 ; forcé à 2
d, s = pdf(ok(c.get("/preparation/evaluations/e/CE2-T1-dictee.pdf")))
assert len(d.pages) == 1 and d.pages[0].width > d.pages[0].height and s.count("DICTÉE ET") == 2 and ("découper ici" in s or "repuocéd" in s), (len(d.pages), s[:300])
d, s = pdf(ok(c.get("/preparation/evaluations/e/CE2-T1-dictee.pdf?par_page=1")))
assert d.pages[0].width < d.pages[0].height and s.count("DICTÉE ET") == 1
d, s = pdf(ok(c.get("/preparation/evaluations/e/CI-M2-math.pdf?par_page=2")))
assert d.pages[0].width > d.pages[0].height
# ---- EPS : fiche de notation ; EA : deux parties
d, s = pdf(ok(c.get("/preparation/evaluations/e/CM2-C2-eps.pdf")))
assert "FICHE DE NOTATION" in s and "Nom et prénoms" in s
d, s = pdf(ok(c.get("/preparation/evaluations/e/CM2-C2-eps.pdf?partie=corrige")))
assert "Garçons" in s and "Filles" in s and "Barème" in s
t = txt(ok(c.get("/preparation/evaluations/e/CE1-M4-ea")))
assert "Partie A" in t and "Partie B" in t and "matériel" in t
t = txt(ok(c.get("/preparation/evaluations/e/CP-M1-eps?onglet=grille")))
assert "Barème" in t and "Garçons" in t and "Filles" in t
# ---- jeu complet d'une période (mise en page mixte portrait / deux par page)
d, s = pdf(ok(c.get("/preparation/evaluations/jeu.pdf?cours=CE2&periode=M1")))
assert len(d.pages) >= 6 and "DICTÉE" in s and "ÉDUCATION ARTISTIQUE" in s and "PHYSIQUE ET SPORTIVE" in s
# ---- onglet Modifier : en-tête, version locale, original, copie, retour à l'original
cle = "CE2-M2-dictee"
t = txt(ok(c.get(f"/preparation/evaluations/e/{cle}")))
assert "Modifier" in t and "Sujet" in t and "Corrigé" in t and "Dupliquer" in t
t = txt(ok(c.get(f"/preparation/evaluations/e/{cle}/modifier")))
assert "En-tête" in t and "entete_ecole" in t and "version locale" in t
ok(c.post(f"/preparation/evaluations/e/{cle}/modifier", data={"entete_ecole": "EPP Towé", "entete_classe": "CE2 A", "entete_date": "18 novembre 2026",
                                                           "duree": "35 min", "q_1_0": "Question de l'école ?", "r_1_0": "Réponse de l'école.", "p_1_0": "2"}), 302)
t = txt(ok(c.get(f"/preparation/evaluations/e/{cle}")))
assert "EPP Towé" in t and "Question de l'école ?" in t and "Version locale" in t and "voir l'original" in t and "35 min" in t
d, s = pdf(ok(c.get(f"/preparation/evaluations/e/{cle}.pdf")))
assert "EPP Towé" in s and "18 novembre 2026" in s and "CE2 A" in s
t = txt(ok(c.get(f"/preparation/evaluations/e/{cle}?original=1")))
assert "Question de l'école ?" not in t and "original de la banque" in t
r = ok(c.post(f"/preparation/evaluations/e/{cle}/dupliquer"), 302)
assert r.headers["Location"].endswith(f"/e/{cle}~2/modifier"), r.headers["Location"]
ok(c.post(f"/preparation/evaluations/e/{cle}~2/modifier", data={"entete_ecole": "EPP Towé", "entete_classe": "CE2 B", "entete_date": "19 novembre 2026"}), 302)
t = txt(ok(c.get(f"/preparation/evaluations/e/{cle}~2")))
assert "copie n° 2" in t and "CE2 B" in t and "Question de l'école ?" in t
assert "CE2 A" in txt(ok(c.get(f"/preparation/evaluations/e/{cle}")))
ok(c.get(f"/preparation/evaluations/e/{cle}~2.pdf"))
ok(c.post(f"/preparation/evaluations/e/{cle}/regenerer", data={"banque": "1"}), 302)          # revenir à l'original
t = txt(ok(c.get(f"/preparation/evaluations/e/{cle}")))
assert "Question de l'école ?" not in t and "EPP Towé" not in t and "copie n° 2" in t
r = ok(c.post(f"/preparation/evaluations/e/{cle}~2/regenerer", data={"banque": "1"}), 302)    # supprimer la copie
assert r.headers["Location"].endswith(f"/e/{cle}")
ok(c.get(f"/preparation/evaluations/e/{cle}~2"), 404)
ok(c.get("/preparation/evaluations/e/CE2-M2-dictee~1"), 404)
# ---- résumés par séance CE2 → CM2 : onglet, fiche de séance, fiche conçue, PDF (résumé, livret de SA, cahier)
import m_preparation as MP
CC = MP.corpus()
RS = [r for r in CC["resumes"] if r.get("seance_resume") and r["cours"] in ("CE2", "CM1", "CM2")]
for cours, mat in (("CE2", "maths"), ("CM1", "francais"), ("CM2", "es")):
    t = txt(ok(c.get(f"/preparation/resumes?cours={cours}&matiere={mat}&seances=1&vue=progression")))
    r0 = next(r for r in RS if r["cours"] == cours and r["matiere"] == mat)
    assert r0["titre"] in t and "Cahier de résumés (séances)" in t, (cours, mat)
    t = txt(ok(c.get(f"/preparation/fiches/{r0['fiches'][0]}")))
    assert "Résumé de la séance" in t, (cours, mat)
    d, s = pdf(ok(c.get(f"/preparation/resumes/{r0['id']}.pdf")))
    assert "Séance(s)" in s
    d, s = pdf(ok(c.get(f"/preparation/resumes.pdf?cours={cours}&matiere={mat}&seances=1")))
    assert "CAHIER DE RÉSUMÉS" in s.upper() and len(d.pages) >= 2
fc = next(f for f in CC["fiches"] if f.get("v129") and f["cours"] == "CM1" and f["matiere"] == "francais")
t = txt(ok(c.get(f"/preparation/fiches/{fc['id']}")))
assert "Résumé de la séance" in t and "Conçue selon l'APC" in t
ok(c.get(f"/preparation/fiches/{fc['id']}.pdf"))
rs_sa = next(r for r in RS if r["cours"] == "CM2" and r["matiere"] == "est" and r["sa"])
d, s = pdf(ok(c.get(f"/preparation/resumes.pdf?cours=CM2&matiere=est&sa={rs_sa['sa'][0]}")))
assert "LIVRET DE LA" in s.upper()
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestPagesEpreuves(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")


if __name__ == "__main__":
    unittest.main()
