# -*- coding: utf-8 -*-
"""Tests 1.28 : UASCEP — onglets « Ajouter un membre », Membres, Bureaux, Vie du bureau, Documents, Logo, Importer, Comment
renseigner ; ajout d'un membre sur une base neuve par l'administrateur et par le directeur (éditions école), par le CP, le chef
de la CS et la DDEMP (éditions juridiction), entité saisie à la main, bureau créé automatiquement ; compte en lecture seule.
Examen blanc du CEP (modèle commun CS Pobè) : mêmes résultats que outils/examen-blanc/examen.js (exécuté par Node sur les
mêmes données), centres, candidats (saisie, Excel, reprise du CEP), notes, PV / relevé / résultats signés, Excel, pilotage.
Lancer : python3 -m unittest tests.test_v128"""
import json
import os
import shutil
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

# échantillon commun : absent, dispensé d'EPS, ex æquo, virgules, quart de point
ECHANTILLON = [
    {"nom": "AGBO Rita", "sexe": "F", "dictee": 12, "communication": 11, "comprehension": 14, "maths": 9.5, "est": 13, "es": 15, "ea_vivant": 10,
     "ea_artistique": 12, "eps": 16},
    {"nom": "SOSSOU Marc", "sexe": "G", "dictee": 8, "communication": 9, "comprehension": 10, "maths": 12, "est": 7.25, "es": 11, "ea_vivant": 9,
     "ea_artistique": 14, "eps": 15},
    {"nom": "BIO Awa", "sexe": "F", "dictee": 10, "communication": 10, "comprehension": 10, "maths": 10, "est": 10, "es": 10, "ea_vivant": 6,
     "ea_artistique": 6},
    {"nom": "ADJOVI Paul", "sexe": "G", "dictee": 12, "communication": 11, "comprehension": 14, "maths": 9.5, "est": 13, "es": 15, "ea_vivant": 10,
     "ea_artistique": 12, "eps": 16},
    {"nom": "KPOVI Jean", "sexe": "G"},
    {"nom": "DOSSA Inès", "sexe": "F", "dictee": "4,5", "communication": 6, "comprehension": 3, "maths": 2.75, "est": 8, "es": 5, "ea_vivant": 11,
     "ea_artistique": 9, "eps": 12},
]

NODE = r'''
const fs = require("fs"); global.window = {};
const [JSF, CF] = process.argv.slice(-2); eval(fs.readFileSync(JSF, "utf8"));
const E = window.ExamenBlanc; const cands = JSON.parse(fs.readFileSync(CF, "utf8"));
const b = E.bilan(cands);
const out = {classes: b.classes.map(x => [x.candidat.nom, x.total, x.moyenne, x.maitrises, x.admis, x.rang, x.composees]),
  inscrits: b.inscrits, composes: b.composes, admis: b.admis, absents: b.absents, taux: b.taux, moyenneCentre: b.moyenneCentre,
  ecartTypeMoyennes: b.ecartTypeMoyennes, g: b.g, f: b.f, ecartGenre: b.ecartGenre,
  matieres: b.matieres.map(m => [m.matiere.cle, m.notes, m.moyenne, m.maitrises, m.taux, m.ecartType]),
  fortes: b.fortes.map(m => m.matiere.cle), faibles: b.faibles.map(m => m.matiere.cle), recos: E.recommandations(b)};
process.stdout.write(JSON.stringify(out));
'''


def bilan_py(cands):
    import m_examen_blanc as EB
    b = EB.bilan(cands)
    return {"classes": [[x["candidat"]["nom"], x["total"], x["moyenne"], x["maitrises"], x["admis"], x["rang"], x["composees"]] for x in b["classes"]],
            "inscrits": b["inscrits"], "composes": b["composes"], "admis": b["admis"], "absents": b["absents"], "taux": b["taux"],
            "moyenneCentre": b["moyenneCentre"], "ecartTypeMoyennes": b["ecartTypeMoyennes"], "g": b["g"], "f": b["f"], "ecartGenre": b["ecartGenre"],
            "matieres": [[m["cle"], m["notes"], m["moyenne"], m["maitrises"], m["taux"], m["ecartType"]] for m in b["matieres"]],
            "fortes": [m["cle"] for m in b["fortes"]], "faibles": [m["cle"] for m in b["faibles"]], "recos": EB.recommandations(b)}


class TestExamenBlancParite(unittest.TestCase):
    """Le calcul Python donne exactement les mêmes résultats que le fichier JS commun (CS Pobè)."""

    def comparer(self, cands, tmp):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js absent")
        p = os.path.join(tmp, "c.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cands, f, ensure_ascii=False)
        r = subprocess.run([node, "-e", NODE, "--", os.path.join(RACINE, "tests", "donnees", "examen_blanc.js"), p], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        js = json.loads(r.stdout)
        py = json.loads(json.dumps(bilan_py(cands)))
        for k in js:
            self.assertEqual(py[k], js[k], k)

    def test_echantillon(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            self.comparer(ECHANTILLON, t)
            self.comparer(ECHANTILLON[:2] + [dict(ECHANTILLON[0], nom="X", sexe="F", eps=9)], t)
            self.comparer([{"nom": "A", "sexe": "G"}], t)
            fort = [dict(ECHANTILLON[0], nom=f"E{i}", sexe="F" if i % 2 else "G") for i in range(7)]
            self.comparer(fort, t)

    def test_regles(self):
        import m_examen_blanc as EB
        b = EB.bilan(ECHANTILLON)
        r = {x["candidat"]["nom"]: x for x in b["classes"]}
        self.assertEqual((r["AGBO Rita"]["rang"], r["ADJOVI Paul"]["rang"]), (1, 1))          # ex æquo
        self.assertTrue(r["BIO Awa"]["admis"])                                               # dispensée d'EPS : 6 maîtrises sur 8
        self.assertEqual(r["BIO Awa"]["composees"], 8)
        self.assertIsNone(r["KPOVI Jean"]["rang"])
        self.assertEqual(b["absents"], 1)
        self.assertEqual(EB.js_round(2.675), 2.68)
        self.assertEqual(EB.sexe_de("Masculin"), "G")
        self.assertEqual(EB.sexe_de("Fille"), "F")


SCRIPT = r'''
import html, io, json, os, re, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
import openpyxl
app.config["TESTING"] = True
ED = config.EDITION
JUR = ED in ("cs", "ddemp")
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-2500:]); return r
def txt(r): return html.unescape(r.data.decode())
def texte_pdf(r):
    import pdfplumber
    assert r.mimetype == "application/pdf", (r.request.path, r.mimetype)
    with pdfplumber.open(io.BytesIO(r.data)) as d:
        return "\n".join(p.extract_text() or "" for p in d.pages).replace("\n", " ")
def Q(*a, **k):
    with app.app_context():
        return q(*a, **k)
def EX(*a, **k):
    with app.app_context():
        return ex(*a, **k)
EX("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
cols = [c["name"] for c in Q("PRAGMA table_info(utilisateurs)")]
def compte(ident, role):
    d = {"identifiant": ident, "nom": ident.upper(), "role": role, "mdp_hash": generate_password_hash("motdepasse1"), "doit_changer_mdp": 0}
    if "ecole_id" in cols and not JUR:
        d["ecole_id"] = 1
    EX("INSERT INTO utilisateurs (" + ",".join(d) + ") VALUES (" + ",".join("?" * len(d)) + ")", tuple(d.values()))
    c = app.test_client()
    ok(c.post("/login", data={"identifiant": ident, "mdp": "motdepasse1"}), 302)
    if "acces_codes" in [t["name"] for t in Q("SELECT name FROM sqlite_master WHERE type='table'")]:
        pass
    return c
if JUR:   # base neuve d'une juridiction : la structure est déclarée au premier usage
    EX("INSERT OR REPLACE INTO jur_structure (id, niveau, departement, cs, nom) VALUES (1, ?, 'Plateau', 'Pobè', 'CS Pobè')", (ED,))
c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)

# ===================== UASCEP : base neuve -> onglets, aide, ajout d'un membre
t = txt(ok(c.get("/uascep")))
for o in ("Ajouter un membre", "Membres", "Bureaux", "Vie du bureau", "Documents", "Logo", "Importer (Excel)", "Comment renseigner"):
    assert o in t, o
for quoi in ("bureaux", "vie", "documents", "logo", "importer", "aide"):
    t = txt(ok(c.get(f"/uascep/onglet/{quoi}")))
    if quoi in ("bureaux", "vie", "documents", "logo"):
        assert "Aucun bureau pour l'instant" in t, quoi
assert "Comment renseigner le module UASCEP" in txt(ok(c.get("/uascep/onglet/aide")))
wb = openpyxl.load_workbook(io.BytesIO(ok(c.get("/uascep/modele.xlsx?vide=1")).data))
ws = wb["Membres UASCEP"]
assert [x.value for x in ws[1]][:4] == ["Niveau", "Entité", "N° d'ordre", "Nom"] and ws.max_row == 1
t = txt(ok(c.get("/uascep/ajouter")))
assert "Enregistrer et ajouter un autre" in t and "Réinitialiser" in t and 'name="entite"' in t
niv = "CS" if JUR else "ECOLE"
ent = "CS Pobè" if JUR else ""
r = ok(c.post("/uascep/ajouter", data={"niveau": niv, "entite": ent or "École", "nom": "AKPO", "prenoms": "Jules", "sexe": "M", "fonction": "Président",
                                     "date_election": "2026-10-15", "duree": "2", "suite": "autre"}), 302)
assert "/uascep/ajouter" in r.headers["Location"]
b = Q("SELECT * FROM uascep_bureaux", un=True)
m = Q("SELECT * FROM uascep_membres", un=True)
assert b and b["niveau"] == niv and m["nom"] == "AKPO" and m["ordre"] == 1 and b["date_fin"] == "2028-10-15", (dict(b), dict(m))
t = txt(ok(c.get(f"/uascep?onglet={niv}&entite={b['entite']}")))
assert "AKPO" in t
assert "AKPO" not in txt(ok(c.get("/uascep/onglet/bureaux"))) and "Aucun bureau" not in txt(ok(c.get("/uascep/onglet/bureaux")))
ok(c.post("/uascep/ajouter", data={"niveau": niv, "entite": ent or "École", "nom": "", "suite": "liste"}), 400)
if JUR:
    # entité absente des listes : saisie libre (zone, UP) -> bureau créé
    ok(c.post("/uascep/ajouter", data={"niveau": "ZONE", "entite": "Zone pédagogique 3", "nom": "BIO", "fonction": "Secrétaire général", "suite": "liste"}), 302)
    assert Q("SELECT entite FROM uascep_bureaux WHERE niveau='ZONE'", un=True)["entite"] == "Zone pédagogique 3"
    roles = [("cp1", "cp", "UP", "UP Pobè 2"), ("dir1", "directeur", "ECOLE", "EPP Towé")]
    roles.append(("chef1", "responsable", "DDEMP" if ED == "ddemp" else "CS", "Plateau" if ED == "ddemp" else "CS Pobè"))
else:
    roles = [("dir1", "directeur", "ECOLE", "École")]
for ident, role, n_, e_ in roles:
    cc = compte(ident, role)
    rr = cc.get("/uascep/ajouter")
    if rr.status_code == 302:     # code d'accès personnel demandé : le module reste accessible après la saisie
        rr = cc.get(rr.headers["Location"])
    t = txt(ok(cc.get("/uascep/ajouter")))
    assert f'value="{n_}"' in t, (ident, t[t.find("Niveau *"):][:600])
    ok(cc.post("/uascep/ajouter", data={"niveau": n_, "entite": e_, "nom": "NOM" + ident.upper(), "fonction": "Membre", "suite": "liste"}), 302)
    assert Q("SELECT 1 FROM uascep_membres WHERE nom=?", ("NOM" + ident.upper(),), un=True), ident
# compte en lecture seule : message qui dit qui peut écrire
ce = compte("ens1", "agent" if JUR else "enseignant")
t = txt(ok(ce.get("/uascep")))
assert "peut consulter ce module mais pas l'écrire" in t, t[:3000]
ok(ce.post("/uascep/ajouter", data={"niveau": niv, "entite": "X", "nom": "Z"}), 403)

# ===================== Examen blanc
S = config.ANNEE_ACTIVE
t = txt(ok(c.get("/examen-blanc")))
assert "Aucun centre pour la session" in t
ok(c.post("/examen-blanc", data={"session": S, "action": "proposer"}), 302)
cs_ = Q("SELECT * FROM eb_centres ORDER BY id")
if JUR and ED == "cs":
    assert len(cs_) == 7 and cs_[0]["nom"] == "Centre de Pobè centre", [x["nom"] for x in cs_]
else:
    assert len(cs_) == 1 and cs_[0]["nom"].startswith("Centre"), [x["nom"] for x in cs_]
cid = cs_[0]["id"]
ok(c.post("/examen-blanc", data={"session": S, "action": "centre", "cid": cid, "nom": "Centre A", "chef": "KOKO Albert", "date": "12/05/2027"}), 302)
# import Excel avec des en-têtes alternatifs (Nom, École, Expression écrite, Maths, EA plastique), sexe Masculin / Fille
ent = ["N° d’ordre", "Nom", "Sexe", "École", "Dictée", "Expression écrite", "Compréhension de l’écrit", "Maths", "EST", "ES", "EA vivant", "EA plastique", "EPS"]
K = ["dictee", "communication", "comprehension", "maths", "est", "es", "ea_vivant", "ea_artistique", "eps"]
DATA = json.loads(os.environ["ECHANTILLON"])
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Candidats à l'examen blanc"; ws.append(ent)
for i, x in enumerate(DATA, 1):
    ws.append([i, x["nom"], {"F": "Fille", "G": "Masculin"}[x["sexe"]], "EPP Towé"] + [x.get(k) for k in K])
bio = io.BytesIO(); wb.save(bio); bio.seek(0)
ok(c.post(f"/examen-blanc/centre/{cid}/import", data={"fichier": (bio, "eb.xlsx")}, content_type="multipart/form-data"), 302)
assert Q("SELECT COUNT(*) n FROM eb_candidats WHERE centre_id=?", (cid,), un=True)["n"] == 6
t = txt(ok(c.get(f"/examen-blanc/centre/{cid}")))
assert "Recommandations" in t and "absent" in t and "Épreuves fortes" in t
attendu = json.loads(os.environ["ATTENDU"])
for nom, total, moy, mait, adm, rang, _n in attendu["classes"]:
    if rang:
        assert f"<td>{rang}</td>" in t, nom
for rec in attendu["recos"]:
    assert html.unescape(rec) in t, rec
# saisie : AGBO en EPS 16 -> 18 (à l'écran)
x = Q("SELECT id FROM eb_candidats WHERE nom='AGBO Rita'", un=True)
form = {"action": "notes"}
for y in Q("SELECT * FROM eb_candidats WHERE centre_id=?", (cid,)):
    for k, v in json.loads(y["notes"]).items():
        form[f"n_{y['id']}_{k}"] = str(v)
form[f"n_{x['id']}_eps"] = "18,25"
ok(c.post(f"/examen-blanc/centre/{cid}", data=form), 302)
assert json.loads(Q("SELECT notes FROM eb_candidats WHERE id=?", (x["id"],), un=True)["notes"])["eps"] == 18.25
# ajout / suppression d'un candidat
ok(c.post(f"/examen-blanc/centre/{cid}", data={"action": "candidat", "nom": "NOUVEAU Test", "sexe": "F", "ecole": "EPP Towé"}), 302)
nid = Q("SELECT id FROM eb_candidats WHERE nom='NOUVEAU Test'", un=True)["id"]
ok(c.post(f"/examen-blanc/centre/{cid}", data={"action": "supprimer", "candidat": nid}), 302)
# Excel export -> réimport identique
wb = openpyxl.load_workbook(io.BytesIO(ok(c.get(f"/examen-blanc/centre/{cid}.xlsx")).data))
assert wb.sheetnames == ["Candidats à l'examen blanc", "Résultats par épreuve", "Synthèse des centres"]
h = [v.value for v in wb["Candidats à l'examen blanc"][1]]
assert h[:4] == ["N° d’ordre", "Nom et prénoms", "Sexe", "École de provenance"] and h[-5:] == ["Total", "Moyenne", "Nombre de maîtrises", "Seuil atteint", "Rang"], h
assert [v.value for v in wb["Synthèse des centres"][1]][:3] == ["Centre", "Inscrits G", "Inscrits F"]
bio = io.BytesIO(); wb.save(bio); bio.seek(0)
ok(c.post(f"/examen-blanc/centre/{cid}/import", data={"fichier": (bio, "eb.xlsx")}, content_type="multipart/form-data"), 302)
assert Q("SELECT COUNT(*) n FROM eb_candidats WHERE centre_id=?", (cid,), un=True)["n"] == 6
# documents signés
s = texte_pdf(ok(c.get(f"/examen-blanc/centre/{cid}/pv.pdf")))
assert "PROCÈS-VERBAL D'EXAMEN BLANC" in s and "AGBO Rita" in s and "KOKO Albert" in s and "Recommandations" in s and "code" in s.lower(), s[:1500]
s = texte_pdf(ok(c.get(f"/examen-blanc/centre/{cid}/releve.pdf")))
assert "RELEVÉ DE NOTES DU CENTRE" in s and "Épreuves fortes" in s
s = texte_pdf(ok(c.get(f"/examen-blanc/resultats.pdf?session={S}")))
assert "RÉSULTATS DE L'EXAMEN BLANC" in s and "Centre A" in s and "Ensemble" in s
# reprise de la liste du CEP (module Examens et concours)
ok(c.post(f"/reg/examens/candidats/0?annee={S}", data={"niveau": "ECOLE", "entite": "EPP Issaba", "session": "CEP 2027", "nom": "ZINSOU", "prenoms": "Léa", "sexe": "F",
          "centre": "Centre Pobè 1", "statut": "Inscrit"}), 302)
ok(c.post(f"/examen-blanc/centre/{cid}", data={"action": "cep", "session_cep": "CEP 2027", "centre_cep": ""}), 302)
ok(c.post(f"/examen-blanc/centre/{cid}", data={"action": "cep", "session_cep": "CEP 2027", "centre_cep": ""}), 302)
z = Q("SELECT * FROM eb_candidats WHERE nom='ZINSOU Léa'")
assert len(z) == 1 and z[0]["sexe"] == "F" and z[0]["ecole"] == "EPP Issaba"
# tableau de bord du pilotage
if ED != "enseignant":
    t = txt(ok(c.get(f"/pilotage?annee={S}")))
    assert "Examen blanc du CEP" in t and "EPP Towé" in t, t[-3000:]
assert "Examen blanc du CEP" in txt(ok(c.get("/examen-blanc")))
# réinitialiser, supprimer le centre
ok(c.post(f"/examen-blanc/centre/{cid}", data={"action": "reinitialiser"}), 302)
assert Q("SELECT COUNT(*) n FROM eb_candidats WHERE centre_id=?", (cid,), un=True)["n"] == 0
ok(c.post("/examen-blanc", data={"session": S, "action": "supprimer", "cid": cid}), 302)
print("OK-" + ED)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    env["ECHANTILLON"] = json.dumps(ECHANTILLON, ensure_ascii=False)
    env["ATTENDU"] = json.dumps(bilan_py(ECHANTILLON), ensure_ascii=False)
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestV128(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")

    def test_cs(self):
        self.verifier("cs")

    def test_ddemp(self):
        self.verifier("ddemp")


if __name__ == "__main__":
    unittest.main()
