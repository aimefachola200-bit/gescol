# -*- coding: utf-8 -*-
"""Tests 2.4.4 : orientation (série après le BEPC, filières après le bac, passage des autres classes).
Lancer : python3 -m unittest tests.test_v244"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")

import m_orientation as O  # noqa: E402


class CalculsPurs(unittest.TestCase):
    def test_groupes_de_matieres(self):
        self.assertEqual(O.groupe_matiere("FR.COM", "Français – Communication écrite"), "lettres")
        self.assertEqual(O.groupe_matiere("MATH", "Mathématiques"), "maths")
        self.assertEqual(O.groupe_matiere("PCT", "x"), "pct")
        self.assertEqual(O.groupe_matiere("SVT", "x"), "svt")
        self.assertEqual(O.groupe_matiere("", "Éveil scientifique"), None)
        self.assertEqual(O.groupe_matiere("", "Lecture"), "lettres")
        self.assertIsNone(O.groupe_matiere("EPS", "Éducation physique et sportive"))

    def test_profil_coefficients_et_periodes(self):
        notes = [("D1", 10, 3, "MATH", "Mathématiques"), ("D1", 14, 1, "ANG", "Anglais"), ("D2", 16, 3, "MATH", "Mathématiques")]
        p = O.profil_eleve(notes, "3ème")
        self.assertEqual(p["periodes"]["D1"], 11.0)           # (10*3+14*1)/4
        self.assertEqual(p["generale"], round((11.0 + 16.0) / 2, 2))
        self.assertEqual(p["groupes"]["maths"], 13.0)
        self.assertEqual(O.profil_eleve(notes, "3ème", ["D2"])["generale"], 16.0)
        # 6ème : coefficients ignorés
        self.assertEqual(O.profil_eleve(notes, "6ème", ["D1"])["generale"], 12.0)
        self.assertIsNone(O.profil_eleve([], "3ème")["generale"])

    def test_series_proposees(self):
        sci = O.profil_eleve([("D", 15, 3, "MATH", "M"), ("D", 14, 3, "PCT", "P"), ("D", 11, 2, "SVT", "S"), ("D", 9, 2, "ANG", "A")], "3ème")
        s = O.propose_series(sci)
        self.assertEqual(s[0]["serie"], "C")
        self.assertTrue(s[0]["admissible"])
        let = O.profil_eleve([("D", 8, 3, "MATH", "M"), ("D", 8, 3, "PCT", "P"), ("D", 15, 2, "ANG", "A"), ("D", 14, 2, "HG", "H")], "3ème")
        s2 = O.propose_series(let)
        self.assertIn(s2[0]["serie"], ("A1", "A2"))
        c = next(x for x in s2 if x["serie"] == "C")
        self.assertFalse(c["admissible"]); self.assertTrue(c["manque"])
        faible = O.profil_eleve([("D", 6, 1, "MATH", "M"), ("D", 7, 1, "ANG", "A")], "3ème")
        self.assertFalse(any(x["admissible"] for x in O.propose_series(faible)))

    def test_lecture_des_annonces(self):
        import m_annonces_personnel as A
        self.assertTrue(A.lisible_par("enseignant", "enseignants")); self.assertTrue(A.lisible_par("enseignant", "tous"))
        self.assertTrue(A.lisible_par("directeur", "enseignants"))

    def test_decisions_et_filieres(self):
        self.assertEqual(O.decision_proposee(12, "CM1"), "Admis en classe supérieure")
        self.assertEqual(O.decision_proposee(9.5, "5ème"), "Conseil de classe")
        self.assertEqual(O.decision_proposee(7, "4ème"), "Redoublement")
        self.assertEqual(O.decision_proposee(11, "Tle"), "Présentation au baccalauréat")
        self.assertEqual(O.decision_proposee(None, "CM1"), "")
        self.assertEqual(O.etape_de("3ème"), "apres_bepc"); self.assertEqual(O.etape_de("Tle"), "apres_bac")
        self.assertEqual(O.etape_de("CM2"), "passage"); self.assertEqual(O.etape_de("Maternelle 1"), "aucune")
        self.assertEqual(O.serie_de_classe("Tle D"), "D"); self.assertEqual(O.serie_de_classe("3ème A"), "A")
        self.assertIn("Droit", O.filieres_pour("A1", 12)); self.assertEqual(len(O.filieres_pour("C", 8)), 2)


SCRIPT = r'''
import html, io, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, q as _q, ex as _ex
import openpyxl
app.config["TESTING"] = True

def q(*a, **k):
    with app.app_context():
        r = _q(*a, **k)
        return [dict(x) for x in r] if isinstance(r, list) else (dict(r) if r else r)
def ex(*a, **k):
    with app.app_context():
        return _ex(*a, **k)
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-1500:]); return r
def txt(r): return html.unescape(ok(r).data.decode())
def pdf(r):
    ok(r); assert r.mimetype == "application/pdf" and r.data.startswith(b"%PDF"), (r.request.path, r.mimetype); return r
def xlsx(r):
    wb = openpyxl.load_workbook(io.BytesIO(ok(r).data)); return [[c.value for c in l] for l in wb.active.iter_rows()]

with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client()
p0 = txt(c.get("/login"))
assert "data-theme-btn" in p0 and "sombre.css" in p0 and "theme.js" in p0
for f in ("sombre.css", "theme.js"):
    ok(c.get("/static/" + f))
css = txt(c.get("/static/sombre.css"))
assert "@media screen" in css and "prefers-color-scheme:dark" in css
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302

def mat(code):
    return _q("SELECT id FROM matieres WHERE code=? AND cycle='secondaire'", (code,), un=True)["id"]
def classe(nom, niv):
    _ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES (?,?,0,(SELECT MIN(id) FROM ecoles))", (nom, niv))
    return _q("SELECT id FROM classes WHERE nom=?", (nom,), un=True)["id"]
def eleve(nom, cid, i):
    _ex("INSERT INTO eleves (nom, prenoms, sexe, classe_id, statut, matricule, date_inscription, annee) VALUES (?,?,?,?,?,?,?,?)",
        (nom, "T", "F" if i % 2 else "M", cid, "inscrit", f"O{cid}{i}", "2026-10-01", "2026-2027"))
    return _q("SELECT id FROM eleves WHERE matricule=?", (f"O{cid}{i}",), un=True)["id"]
def note(eid, code, per, val):
    _ex("INSERT INTO notes (eleve_id, matiere_id, periode, annee, valeur) VALUES (?,?,?,?,?)", (eid, mat(code), per, "2026-2027", val))

with app.app_context():
    c3 = classe("3ème A", "3ème"); c2 = classe("2nde C", "2nde"); ct = classe("Tle D", "Tle"); c6 = classe("6ème A", "6ème")
    sci = eleve("SCIENCES", c3, 0); let = eleve("LETTRES", c3, 1); fai = eleve("FAIBLE", c3, 2)
    for per in ("Devoir 1", "Composition 1"):
        for code, v in (("MATH", 16), ("PCT", 15), ("SVT", 12), ("ANG", 9), ("HG", 9)): note(sci, code, per, v)
        for code, v in (("MATH", 8), ("PCT", 8), ("SVT", 9), ("ANG", 16), ("HG", 15), ("FR.COM", 15)): note(let, code, per, v)
        for code, v in (("MATH", 5), ("PCT", 6), ("ANG", 7)): note(fai, code, per, v)
    note(sci, "MATH", "Devoir 3", 2)                       # évaluation à exclure du calcul
    bac = eleve("BACHELIER", ct, 0)
    for code, v in (("MATH", 13), ("SVT", 14), ("PCT", 12)): note(bac, code, "Composition 1", v)
    e6 = eleve("SIXIEME", c6, 0); e6b = eleve("SIXIEMEB", c6, 1)
    for code, v in (("MATH", 12), ("ANG", 13)): note(e6, code, "Devoir 1", v)
    for code, v in (("MATH", 6), ("ANG", 8)): note(e6b, code, "Devoir 1", v)

page = txt(c.get("/orientation"))
assert "3ème A" in page and "2nde C" in page and "6ème A" in page
p3 = txt(c.get(f"/orientation/{c3}"))
assert "Choix de la série après le BEPC" in p3 and "SCIENCES" in p3
assert "Devoir 3" in p3 and "Composition 1" in p3
# SCIENCES : série C proposée ; LETTRES : série A ; FAIBLE : aucune
import re
def ligne(page, nom):
    m = re.search(r"<tr>\s*<td><a[^>]*>" + nom + r" T</a></td>(.*?)</tr>", page, re.S); assert m, nom; return m.group(1)
assert "conditions non remplies" in ligne(p3, "SCIENCES")      # toutes évaluations : le Devoir 3 (2/20 en maths) fait baisser la moyenne
assert re.search(r"<b>A[12]</b>", ligne(p3, "LETTRES")), ligne(p3, "LETTRES")[:400]
assert "conditions non remplies" in ligne(p3, "FAIBLE")
# retenir seulement certaines évaluations : le Devoir 3 (2/20 en maths) est exclu
pf = txt(c.get(f"/orientation/{c3}?periodes=Devoir 1&periodes=Composition 1"))
assert '<b>C</b>' in ligne(pf, "SCIENCES")
# enregistrement
d = {"annee": "2026-2027"}
for eid, avis, dec, voeu, res in ((sci, "C", "Orienté", "D", "Admis"), (let, "A1", "Orienté", "A1", "Admis"), (fai, "", "Conseil de classe", "", "Ajourné")):
    d.update({f"voeu_{eid}": voeu, f"avis_{eid}": avis, f"decision_{eid}": dec, f"resultat_{eid}": res, f"obs_{eid}": "RAS" if eid == sci else ""})
r = c.post(f"/orientation/{c3}", data=d); assert r.status_code == 302, r.status_code
p3 = txt(c.get(f"/orientation/{c3}"))
assert "Orienté : 1" not in p3 and ("C : 1" in p3 and "A1 : 1" in p3), re.findall(r"badge\">([^<]*)", p3)
assert 'value="RAS"' in p3
with app.app_context():
    assert _q("SELECT COUNT(*) n FROM orientation_decisions", un=True)["n"] == 3
    assert _q("SELECT avis FROM orientation_decisions WHERE eleve_id=?", (sci,), un=True)["avis"] == "C"
# vider une ligne la supprime
d2 = dict(d); d2.update({f"voeu_{fai}": "", f"avis_{fai}": "", f"decision_{fai}": "", f"resultat_{fai}": "", f"obs_{fai}": ""})
assert c.post(f"/orientation/{c3}", data=d2).status_code == 302
with app.app_context():
    assert _q("SELECT COUNT(*) n FROM orientation_decisions", un=True)["n"] == 2
pdf(c.get(f"/orientation/{c3}/liste.pdf")); pdf(c.get(f"/orientation/eleve/{sci}.pdf"))
rows = xlsx(c.get(f"/orientation/{c3}/liste.xlsx"))
assert any("SCIENCES" in str(x) for l in rows for x in l if x)
# 2nde et Tle
assert "1ère" in txt(c.get(f"/orientation/{c2}"))
pt = txt(c.get(f"/orientation/{ct}"))
assert "Orientation après le baccalauréat" in pt and "Santé" in pt or "Sciences de la vie" in pt, pt[:200]
pdf(c.get(f"/orientation/eleve/{bac}.pdf"))
# passage : 6ème
p6 = txt(c.get(f"/orientation/{c6}"))
assert "Admis en classe supérieure" in p6 and "Redoublement" in p6
# erreurs : maternelle et classe inconnue
ok(c.get("/orientation/99999"), 404)
# annonces au personnel (cible « enseignants » de la diffusion)
r = c.post("/communication/diffuser", data={"cible": "enseignants", "sujet": "Conseil des maîtres", "texte": "Vendredi à 15 h.", "canaux": "portail"})
assert r.status_code == 302 and "/annonces" in r.headers["Location"], r.headers.get("Location")
pa = txt(c.get("/annonces"))
assert "Conseil des maîtres" in pa and "Vendredi à 15 h." in pa and "Enseignants" in pa
assert "Enseignants (annonce interne)" in txt(c.get("/communication?onglet=ecrire"))
assert c.post("/annonces/nouvelle", data={"cible": "tous", "sujet": "", "texte": ""}).status_code == 302
assert c.post("/annonces/nouvelle", data={"cible": "tous", "sujet": "Rentrée", "texte": "Lundi."}).status_code == 302
assert "Rentrée" in txt(c.get("/annonces"))
with app.app_context():
    aid = _q("SELECT id FROM annonces_personnel WHERE sujet='Rentrée'", un=True)["id"]
assert c.post(f"/annonces/{aid}/supprimer").status_code == 302
assert "Rentrée" not in txt(c.get("/annonces"))
print("OK", ED)
'''


def lancer(edition):
    env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_SCRIPT=edition)
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)


class Parcours(unittest.TestCase):
    def _edition(self, ed):
        r = lancer(ed)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3500:])
        self.assertIn("OK " + ed, r.stdout)

    def test_edition_privee(self):
        self._edition("privee")

    def test_edition_publique(self):
        self._edition("publique")


if __name__ == "__main__":
    unittest.main()
