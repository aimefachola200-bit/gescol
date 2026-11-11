# -*- coding: utf-8 -*-
"""Tests 1.18 : Préparation de classe — programmes et progressions, guides pédagogiques, fiches de préparation APC
(bibliothèque filtrable, PDF, Word, adaptation pour SA classe, fiches de la semaine selon la planification),
fiches et guides manquants ; menu dans les éditions école privée et école publique (application de l'école et
portail /enseignant) et dans l'application de l'enseignant ; périmètre de l'enseignant ; choix tactiles (Android).
Lancer : python3 -m unittest tests.test_v118"""
import gzip
import json
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "GESCOL"

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
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-1500:]); return r
def txt(r): return html.unescape(r.data.decode())
def texte_pdf(r):
    import pdfplumber
    assert r.mimetype == "application/pdf", (r.request.path, r.mimetype)
    with pdfplumber.open(io.BytesIO(r.data)) as d:
        return "\n".join(p.extract_text() or "" for p in d.pages), len(d.pages)
AUJ = date.today()
lundi = AUJ - timedelta(days=AUJ.weekday())
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    ce2 = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CE2 P','CE2',0,1)")
    ci = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CI P','CI',0,1)")
    uid = ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) VALUES ('ens1','DOSSOU Jean','enseignant',?,0,1,1)",
             (generate_password_hash("ens-mdp-123"),))
    ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,NULL)", (uid, ce2))
    ex("INSERT INTO eleves (nom, prenoms, sexe, date_naissance, classe_id, statut, date_inscription, annee) VALUES ('AKPO','Jean','M','2017-01-01',?,'inscrit','2026-09-15',?)", (ce2, config.ANNEE_ACTIVE))
    # planification mensuelle de la CE2 : semaine en cours = EST SA 2, Mathématiques D3 SA1
    sem = [{"du": (lundi + timedelta(days=7 * (k - 1))).isoformat(), "au": (lundi + timedelta(days=7 * (k - 1) + 4)).isoformat()} for k in range(5)]
    sem[1] = {"du": lundi.isoformat(), "au": (lundi + timedelta(days=6)).isoformat()}
    cont = {"est": ["", "SA 2", "", "", ""], "maths": ["", "D3 SA1", "", "", ""]}
    ex("INSERT INTO synoptique_planification_mensuelle (ecole_id, annee, classe_id, mois, semaines, contenu) VALUES (1,?,?,?,?,?)",
       (config.ANNEE_ACTIVE, ce2, f"{AUJ.year}-{AUJ.month:02d}", json.dumps(sem), json.dumps(cont)))
import m_preparation as MP
C = MP.corpus()
assert len(C["fiches"]) >= 1000 and len(C["guides"]) >= 40 and len(C["programmes"]) >= 100, (len(C["fiches"]), len(C["guides"]))
assert all(f["cours"] in MP.COURS and f["matiere"] in C["matieres"] for f in C["fiches"])
conc = [f for f in C["fiches"] if f.get("statut") == "concue"]
assert conc and all("à valider par le conseiller pédagogique" in f["mention"] for f in conc)
assert MP.references("U1 semaine2 à U3 semaine 1")["u"] == [1, 2, 3]
assert MP.references("D1 SA1 Séq 8 à 15 SA2 et 3") == {"sa": [1, 2, 3], "u": [], "d": [1]}
assert MP.txt_html("**a** <b>\nx") == "<b>a</b> &lt;b&gt;<br>x"
f_est = next(f for f in C["fiches"] if f["cours"] == "CE2" and f["matiere"] == "est" and f.get("sa") == 2)
f_ci = next(f for f in C["fiches"] if f["cours"] == "CI" and f["matiere"] == "francais")

def menu(t):
    for m_ in ("Préparation de classe", "Programmes et progressions", "Guides pédagogiques", "Fiches de préparation (bibliothèque)",
               "Préparer une fiche", "Fiches et guides manquants"):
        assert m_ in t, m_

def parcours(c, directeur):
    t = txt(ok(c.get("/preparation")))
    menu(t)
    # fiches de la semaine : elles dépendent du jour (séances réparties sur le mois) — une fiche de CE2 au moins
    assert "CE2 P" in t and "Planification mensuelle, semaine du" in t and any(x["titre"] in t for x in C["fiches"] if x["cours"] == "CE2"), "cette semaine"
    assert ("CI P" in t) == directeur
    ok(c.get("/preparation/programmes"))
    t = txt(ok(c.get("/preparation/programmes?cours=CE2&matiere=maths")))
    assert "Une riche fermière" in t
    ok(c.get("/preparation/programmes/m2-d3-sa1"))
    t = txt(ok(c.get("/preparation/guides")))
    assert "Gestion d'une unité de français" in t and "conçu" in t
    ok(c.get("/preparation/guides/g-apc-eps"))
    s, n = texte_pdf(ok(c.get("/preparation/guides/g-fr-gestion.pdf")))
    assert "GUIDE PÉDAGOGIQUE" in s and n >= 1
    t = txt(ok(c.get("/preparation/fiches?cours=CE2&matiere=est&sa=2")))
    assert f_est["titre"] in t and "fiche(s)" in t
    t = txt(ok(c.get("/preparation/fiches?statut=concue")))
    assert "conçue" in t
    t = txt(ok(c.get(f"/preparation/fiches?classe={ce2}&semaine=1")))
    assert any(x["titre"] in t for x in C["fiches"] if x["cours"] == "CE2")          # dépend du jour
    t = txt(ok(c.get(f"/preparation/fiches/{f_est['id']}")))
    assert "Déroulement" in t and "Adapter pour ma classe" in t
    s, n = texte_pdf(ok(c.get(f"/preparation/fiches/{f_est['id']}.pdf?classe={ce2}")))
    assert "FICHE DE PRÉPARATION" in s and "CE2 P" in s and "Phases" in s and "code" in s, s[:800]
    r = ok(c.get(f"/preparation/fiches/{f_ci['id']}.docx"))
    # v2.2 : vrai document Word (.docx) au lieu d'une page HTML nommée « .doc »
    import zipfile as _zf, io as _io
    assert r.mimetype.endswith("wordprocessingml.document") and "FICHE DE PRÉPARATION" in _zf.ZipFile(_io.BytesIO(r.data)).read("word/document.xml").decode("utf-8")
    s, n = texte_pdf(ok(c.get(f"/preparation/semaine.pdf?classe={ce2}")))
    assert n >= 2 and any(x["titre"][:25] in s.replace("\n", " ") for x in C["fiches"] if x["cours"] == "CE2")
    # préparer une fiche en adaptant une fiche de la bibliothèque
    t = txt(ok(c.get(f"/preparation/preparer?depuis={f_est['id']}&classe={ce2}")))
    assert f_est["titre"] in t and 'name="ph_0"' in t
    ok(c.get("/preparation/preparer?modele=" + C["modeles"][0]["id"]))
    d = {"classe": str(ce2), "date_seance": AUJ.isoformat(), "matiere": "est", "sa": "2", "seance": "1",
         "titre": "Ma séance adaptée " + ("dir" if directeur else "ens"), "cd": "CD adapté", "ph_0": "**INTRODUCTION**",
         "ac_0": "▪ Rappel\n▪ Situation", "re_0": "Réponses", "ph_1": "RÉALISATION", "ac_1": "Travail en groupe",
         "source_id": f_est["id"]}
    r = ok(c.post("/preparation/preparer", data=d), 302)
    mid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    ok(c.post("/preparation/preparer", data=dict(d, titre="")), 400)
    t = txt(ok(c.get(f"/preparation/mes-fiches/{mid}")))
    assert d["titre"] in t and "CD adapté" in t
    t = txt(ok(c.get(f"/preparation/mes-fiches/{mid}?modifier=1")))
    assert 'value="' + d["titre"] + '"' in t
    ok(c.post(f"/preparation/mes-fiches/{mid}", data=dict(d, titre=d["titre"] + " v2")), 302)
    s, n = texte_pdf(ok(c.get(f"/preparation/mes-fiches/{mid}.pdf")))
    assert d["titre"] + " v2" in s and "CD adapté" in s and "Rappel" in s
    import zipfile as _zf2, io as _io2
    assert "CE2 P" in _zf2.ZipFile(_io2.BytesIO(ok(c.get(f"/preparation/mes-fiches/{mid}.docx")).data)).read("word/document.xml").decode("utf-8")
    r = ok(c.post(f"/preparation/mes-fiches/{mid}/dupliquer"), 302)
    t = txt(ok(c.get("/preparation/mes-fiches")))
    assert "(copie)" in t
    # la fiche datée de la semaine entre dans « fiches de la semaine »
    s, n = texte_pdf(ok(c.get(f"/preparation/semaine.pdf?classe={ce2}")))
    assert d["titre"] + " v2" in s
    t = txt(ok(c.get("/preparation/manquants")))
    assert "SA sans fiche" in t and "à valider par le conseiller pédagogique" in t
    ok(c.get("/preparation/fiches/inconnue"), 404)
    return mid

# ---- 1. directeur / administrateur de l'école (application de l'école)
c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
menu(txt(ok(c.get("/eleves"))))       # entrée de menu de l'application de l'école
mid_dir = parcours(c, True)
ok(c.post("/preparation/preparer", data={"classe": str(ci), "titre": "Fiche CI", "matiere": "francais"}), 302)
ok(c.get("/logout"), 302)

# ---- 2. enseignant connecté à l'application de l'école : ses classes seulement
c = app.test_client()
ok(c.post("/login", data={"identifiant": "ens1", "mdp": "ens-mdp-123"}), 302)
mid_ens = parcours(c, False)
ok(c.post("/preparation/preparer", data={"classe": str(ci), "titre": "Hors périmètre", "matiere": "francais"}), 403)
r = c.get(f"/preparation/mes-fiches/{mid_dir}")
assert r.status_code in (403, 404), r.status_code      # fiche du directeur
ok(c.post(f"/preparation/mes-fiches/{mid_dir}/supprimer"), 403)
t = txt(ok(c.get("/preparation/mes-fiches")))
assert "Fiche CI" not in t and "Ma séance adaptée dir" not in t
ok(c.get("/logout"), 302)

# ---- 3. le directeur voit les fiches des enseignants (lecture), sans pouvoir les modifier
c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
t = txt(ok(c.get("/preparation/mes-fiches")))
assert "Ma séance adaptée ens v2" in t and "DOSSOU Jean" in t and "Fiches des enseignants" in t
ok(c.get(f"/preparation/mes-fiches/{mid_ens}"))
ok(c.get(f"/preparation/mes-fiches/{mid_ens}.pdf"))
ok(c.post(f"/preparation/mes-fiches/{mid_ens}", data={"classe": str(ce2), "titre": "x"}), 403)
ok(c.get("/logout"), 302)

# ---- 4. portail /enseignant : menu de l'enseignant
if "ens_portail" in app.view_functions:
    c = app.test_client()
    ok(c.post("/enseignant", data={"identifiant": "ens1", "mdp": "ens-mdp-123"}), 302)
    t = txt(ok(c.get("/enseignant/tableau")))
    assert "Préparation de classe" in t and "fiches APC" in t
    menu(txt(ok(c.get("/preparation"))))
with app.app_context():
    assert q("SELECT COUNT(*) n FROM prep_fiches", un=True)["n"] == 5
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("GESCOL_EDITION", "GESCOL_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestPreparation(unittest.TestCase):
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

    def test_corpus(self):
        with gzip.open(os.path.join(RACINE, "static", "pedafiche_corpus.json.gz"), "rt", encoding="utf-8") as f:
            c = json.load(f)
        self.assertGreaterEqual(len(c["fiches"]), 1000)
        self.assertTrue(c["manquants"]["avant"] and c["manquants"]["apres"])
        for x in c["guides"]:                       # HTML nettoyé : aucune balise de script ni attribut
            self.assertNotRegex(x["html"].lower(), r"<script|<iframe|\son\w+=|javascript:")

    def test_menus(self):
        for g in ("base.html", "_menu_enseignant.html"):
            t = self.lire("templates", g)
            for ep in ("prep_accueil", "prep_programmes", "prep_guides", "prep_fiches", "prep_preparer", "prep_mes_fiches", "prep_manquants"):
                self.assertIn(f"lien('{ep}'", t, (g, ep))
        self.assertIn("prep_accueil", self.lire("templates", "ens_tableau.html"))
        self.assertIn('"preparation"', self.lire("app.py"))
        self.assertIn('"m_preparation"', self.lire("app.py"))

    def test_choix_tactile(self):
        js = self.lire("static", "choix.js")
        for m in ("visualViewport", "(pointer: coarse)", "SEUIL_SELECT = 12", "choix-panneau", "history.pushState",
                  "dispatchEvent(new Event('change'", "data-choix", "Utiliser « "):
            self.assertIn(m, js)
        self.assertIn("choix.js", self.lire("templates", "base.html"))
        if subprocess.run(["node", "--version"], capture_output=True).returncode == 0:
            self.assertEqual(subprocess.run(["node", "--check", os.path.join(RACINE, "static", "choix.js")]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
