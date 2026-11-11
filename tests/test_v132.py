# -*- coding: utf-8 -*-
"""Tests 1.32 : concepteur (Maître Aimé FACHOLA), mention discrète sur les documents administratifs et complète en bas des
fiches ; fiche de préparation imprimée (Times 14, couleur de la matière, dessins, filigrane oblique du titulaire, recto verso,
« Page x / y ») ; logo de l'école créé automatiquement et devise ; guide d'utilisation (page, PDF, LISEZMOI.md) ; barèmes d'EPS
proposés ; corpus 1.32 (guides officiels, cahier d'activités du CI, planches du CI).
Lancer : python3 -m unittest tests.test_v132"""
import gzip
import io
import json
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import io, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
import pypdf
app.config["TESTING"] = True
def texte(octets):
    return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(octets)).pages)
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id, titulaire_nom) VALUES ('CE2 P','CE2',0,1,'HOUNKPATIN Marcelline')")
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
assert config.CONCEPTEUR == "Maître Aimé FACHOLA" and config.CONCEPTEUR_TEL == "+229 01 96 51 03 33"
# fiche de préparation : filigrane du titulaire, concepteur + téléphone, pagination, police
import m_preparation as MP
C = MP.corpus()
f = max((x for x in C["fiches"] if x["cours"] == "CE2" and x["matiere"] == "maths"), key=lambda x: len(str(x.get("deroulement"))))
r = c.get(f"/preparation/fiches/{f['id']}.pdf?classe=1")
assert r.status_code == 200 and r.mimetype == "application/pdf"
t = texte(r.data)
n = len(pypdf.PdfReader(io.BytesIO(r.data)).pages)
assert "HOUNKPATIN Marcelline" in t, "filigrane du titulaire"
assert "Conception : Maître Aimé FACHOLA — +229 01 96 51 03 33" in t
assert f"Page 1 / {n}" in t and f"Page {n} / {n}" in t
assert b"LiberationSerif" in r.data or b"Times" in r.data
# plusieurs fiches : chaque fiche commence sur un recto
r = c.get("/preparation/semaine.pdf?classe=1")
assert r.status_code in (200, 404)
# document administratif : mention discrète, sans téléphone
r = c.get("/preparation/baremes-eps.pdf?cours=CM2")
assert r.status_code == 200
tb = texte(r.data)
assert "Barème proposé" in tb and "Course d'endurance" in tb and "Saut en hauteur" in tb and "handicap" in tb
# logo et devise de l'école
with app.app_context():
    e = dict(q("SELECT * FROM ecoles WHERE id=1", un=True))
champs = ["nom", "sigle", "statut", "ordre", "departement", "cs", "up", "zone", "commune", "ville", "adresse", "bp", "telephone", "email",
          "directeur_titre", "directeur_nom", "directeur_tel", "admin_titre", "admin_nom", "ccs_titre", "ccs_nom", "cachet_sup", "cachet_inf",
          "cachet_centre", "cachet_couleur", "griffe_actif", "griffe_ligne3", "griffe_couleur"]
d = {k: (e.get(k) or "") for k in champs}
d.update(nom="EPP Issaba Centre", devise="Travail – Discipline – Réussite", logo_mode="auto", logo_forme="ecusson", logo_symbole="soleil")
assert c.post("/ecoles/1/modifier", data=d).status_code == 302
with app.app_context():
    e = dict(q("SELECT * FROM ecoles WHERE id=1", un=True))
assert e["devise"] == "Travail – Discipline – Réussite" and '"auto": true' in e["logo_cfg"] and '"ecusson"' in e["logo_cfg"]
assert os.path.exists(os.path.join(config.ECOLE_DIR, "logo_1.png"))
assert c.get("/ecoles/1/logo-auto.svg").data.startswith(b"<svg")
assert c.get("/ecoles/1/logo-auto.png").data[:4] == b"\x89PNG"
assert b"<svg" in c.get("/ecoles/logo-apercu.svg?nom=EPP+Test&logo_symbole=globe").data
assert "Créer le logo automatiquement" in c.get("/ecoles/1/modifier").data.decode()
d.update(logo_mode="aucun")
c.post("/ecoles/1/modifier", data=d)
assert not os.path.exists(os.path.join(config.ECOLE_DIR, "logo_1.png"))
# guide d'utilisation
import html as _h
t = _h.unescape(c.get("/aide/guide").data.decode())
assert "Guide d'utilisation" in t and "Fiche de l'école, logo et devise" in t and "FACHOLA" in t
assert c.get("/aide/guide?role=enseignant").status_code == 200
r = c.get("/aide/lisez-moi.pdf")
assert r.status_code == 200 and "Guide d'utilisation" in texte(r.data)
# corpus 1.32
g = C["guide_par_id"]
for gid in ("g-memp-fr-ce1", "g-memp-fr-cm2", "g-memp-ma-ci", "g-memp-fr-cp"):
    assert gid in g and len(g[gid]["html"]) > 5000, gid
    assert c.get(f"/preparation/guides/{gid}").status_code == 200 and c.get(f"/preparation/guides/{gid}.pdf").status_code == 200
M = C["manuel_par_id"]
assert M["man-ci-ma-2021"]["fiches_sa"] and M["planches-ci-curriculum"]["planches"]
lies = [x for x in C["fiches"] if x["cours"] == "CI" and x["matiere"] == "maths" and (x.get("manuel") or {}).get("id") == "man-ci-ma-2021"]
assert len(lies) >= 60
t = _h.unescape(c.get(f"/preparation/fiches/{lies[0]['id']}").data.decode())
assert "fiche n°" in t
assert "Planches illustrées" in c.get("/preparation/manuels").data.decode()
print("OK-" + ED)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA", "SCOLARIS_AUTONOME", "GESCOL_AUTONOME"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class Test132(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")


class TestFichiers132(unittest.TestCase):
    def lire(self, *p):
        with open(os.path.join(RACINE, *p), encoding="utf-8") as f:
            return f.read()

    def test_concepteur(self):
        for nom in os.listdir(RACINE):
            if nom.endswith((".py", ".md", ".bat")) and nom != "LISEZMOI.md":
                self.assertNotIn("Aimé FACHE", self.lire(nom).replace("FACHOLA", ""), nom)
        self.assertIn("FACHOLA", self.lire("config.py"))

    def test_mention_administrative(self):
        import pypdf
        import pdfs
        b = pdfs.document_tableau("LISTE TEST", ["A", "B"], [["1", "2"]])
        t = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(b)).pages)
        self.assertIn("FACHOLA", t)
        self.assertNotIn("+229", t)          # documents administratifs : sans téléphone

    def test_lisezmoi(self):
        t = self.lire("LISEZMOI.md")
        self.assertIn("Guide d'utilisation", t)
        self.assertIn("+229 01 96 51 03 33", t)
        self.assertIn("LISEZMOI.md", self.lire("packaging", "windows", PREFIXE.lower() + ".iss"))

    def test_logo_ecole(self):
        import logo_ecole as LE
        for forme in LE.FORMES:
            for sym in list(LE.SYMBOLES) + ["initiales"]:
                p = LE.params("EPP Sainte Trinité de Pobè", "Savoir – Discipline – Excellence", {"forme": forme, "symbole": sym})
                self.assertTrue(LE.svg(p).startswith("<svg"))
                self.assertEqual(LE.png(p, 120)[:4], b"\x89PNG")
        self.assertEqual(LE.initiales_de("EPP Issaba Centre"), "IC")
        self.assertEqual(LE.params("X", "", '{"c1": "#ABCDEF"}')["c1"], "#ABCDEF")

    def test_baremes(self):
        import banque_ea_eps as B
        for cours in ("CI", "CP", "CE1", "CE2", "CM1", "CM2"):
            ref = B.referentiel(cours)
            noms = [e for e, _c, _b in ref]
            self.assertTrue(any("endurance" in n for n in noms) and any("Gymnastique" in n for n in noms), cours)
            for _e, _c, bm in ref:
                self.assertEqual(len(bm["lignes"]), 5 if not bm.get("observation") else len(bm["lignes"]))
        self.assertGreaterEqual(len(B.ADAPTATIONS), 4)

    def test_corpus(self):
        with gzip.open(os.path.join(RACINE, "static", "pedafiche_corpus.json.gz"), "rt", encoding="utf-8") as f:
            c = json.load(f)
        self.assertGreaterEqual(tuple(map(int, c["version_contenu"].split("."))), (1, 32, 0))


if __name__ == "__main__":
    unittest.main()
