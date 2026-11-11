# -*- coding: utf-8 -*-
"""Tests 1.19 : lot 2 (fiches de mathématiques transmises par la CS importées et dédoublonnées, recueils de référence
CE1 / CE2 / EA, guide officiel de Mathématiques CP et ses 140 fiches), inventaire CM1 (fiches APC conçues pour les séances CM1 absentes, mention et source, liens SA / unité
/ semaine retrouvés par « Cette semaine »), « Résumés — l'essentiel à retenir » (Mathématiques CE1 → CM2, Français CM1,
révision CEP : vue enseignant / élève, PDF unitaire et par lot), état de l'inventaire dans « Fiches et guides
manquants » ; éditions école privée et école publique.
Lancer : python3 -m unittest tests.test_v119"""
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
    cm1 = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM1 A','CM1',0,1)")
    uid = ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) VALUES ('ens1','HOUNSOU Awa','enseignant',?,0,1,1)",
             (generate_password_hash("ens-mdp-123"),))
    ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,NULL)", (uid, cm1))
    sem = [{"du": (lundi + timedelta(days=7 * (k - 1))).isoformat(), "au": (lundi + timedelta(days=7 * (k - 1) + 4)).isoformat()} for k in range(5)]
    sem[1] = {"du": lundi.isoformat(), "au": (lundi + timedelta(days=6)).isoformat()}
    cont = {"es_geographie": ["", "SA 6", "", "", ""], "francais": ["", "U4 semaine 1", "", "", ""], "ea_conte": ["", "SA 10", "", "", ""]}
    ex("INSERT INTO synoptique_planification_mensuelle (ecole_id, annee, classe_id, mois, semaines, contenu) VALUES (1,?,?,?,?,?)",
       (config.ANNEE_ACTIVE, cm1, f"{AUJ.year}-{AUJ.month:02d}", json.dumps(sem), json.dumps(cont)))
import m_preparation as MP
# v2.4.8 : « Cette semaine » choisit l'unité / la SA selon le jour du mois (semaines 1 à 4) : le test était donc vrai
# seulement les jours 1-7 et 22-31. On le rend indépendant de la date en le plaçant toujours en première semaine du mois.
_refs_origine = MP.refs_de_la_semaine
MP.refs_de_la_semaine = lambda refs, matiere, jour: _refs_origine(refs, matiere, jour.replace(day=1))
C = MP.corpus()
inv = [f for f in C["fiches"] if f["id"].startswith("cm1i-")]
assert len(inv) >= 230, len(inv)
for f in inv:
    assert f["cours"] == "CM1" and f["statut"] == "concue" and f["source"].endswith("inventaire CM1"), f["id"]
    assert f["mention"] == "Conçue selon l'APC — à valider par le conseiller pédagogique"
    assert [p[0] for p in f["deroulement"]] == ["**INTRODUCTION**", "**RÉALISATION**", "**RETOUR ET PROJECTION**"], f["id"]
    assert all("**Enseignant(e)**" in p[1] and "**Apprenants**" in p[1] and p[2] for p in f["deroulement"]), f["id"]
    for k in ("cd", "ct", "contenus", "strategies", "materiel", "duree", "evaluation", "je_retiens", "unite"):
        assert f[k], (f["id"], k)
    assert f["sa"] and f["seance"], f["id"]
par = {}
for f in inv:
    par[f["matiere"]] = par.get(f["matiere"], 0) + 1
assert par["es"] == 96 and par["ea"] == 110 and par["francais"] == 25 and par["eps"] == 2, par
I = C["inventaire_cm1"]
assert {m["matiere"]: m["restent"] for m in I["matieres"]} == {m: 0 for m in ("francais", "maths", "es", "est", "eps", "ea")}
R = C["resumes"]
assert len(R) >= 110 and all(len(r["exercices"]) == 3 for r in R)
assert {r["cours"] for r in R if r["collection"] == "Mathématiques"} >= {"CE1", "CE2", "CM1", "CM2"}  # v1.23 : + CI, CP
assert {r["matiere"] for r in R if r["collection"] == "Révision CEP"} == {"francais", "maths", "es", "est"}
assert sum(1 for r in R if r["collection"] == "Français CM1") >= 30
# ---- lot 2
cs = [f for f in C["fiches"] if f["id"].startswith("cs-")]
assert len(cs) >= 50 and all(f["source"].startswith("Fiches transmises par la CS") and f["statut"] == "source" for f in cs)
assert {f["cours"] for f in cs} == {"CE1", "CM2"} and any("BOUKARY HABIB" in f["source"] for f in cs)
assert all(f["deroulement"] and f["titre"] for f in cs)
cles = [(f["cours"], f["unite"], f["sa"], tuple(f["sequences"]), f["titre"]) for f in cs]
assert len(cles) == len(set(cles)), "doublons restants dans le lot 2"
assert len([d for d in C["doublons"] if d["lot"] == "lot2-cs" and d["retire"] != "—"]) >= 20
l2c = [f for f in C["fiches"] if f["id"].startswith("l2c-")]
assert len(l2c) >= 130 and all(f["statut"] == "concue" and f["source"].endswith("inventaire lot 2") for f in l2c)
assert any(f["cours"] == "CE2" and f["unite"] == "UNITÉ N°12" for f in l2c) and any(f["cours"] == "CE1" and f["matiere"] == "maths" for f in l2c)
cp = sorted((f for f in C["fiches"] if f["cours"] == "CP" and f["matiere"] == "maths"), key=lambda f: f["seance"])
assert len(cp) == 140 and [f["seance"] for f in cp] == list(range(1, 141)), len(cp)
assert sum(1 for f in cp if f["statut"] == "source") >= 90 and all(f["semaine"] and f["sa"] for f in cp)
gcp = C["guide_par_id"]["g-memp-ma-cp"]
assert gcp["statut"] == "officiel" and "PROGRESSION" in gcp["html"].upper() and "fiche n° 140" in gcp["html"]
assert C["guide_par_id"]["g-apc-ma-cicp"]["cours"] == ["CI"]
cs1 = next(f for f in cs if f["cours"] == "CM2")
cp7 = next(f for f in cp if f["seance"] == 7)
geo = next(f for f in inv if f["matiere"] == "es" and "pêche" in f["titre"])
fr4 = next(f for f in inv if f["matiere"] == "francais" and f["unite"] == "UNITÉ N°4")
conte = next(f for f in inv if f["matiere"] == "ea" and f["sa"] == 10)
rm = next(r for r in R if r["collection"] == "Mathématiques" and r["cours"] == "CM2")
rc = next(r for r in R if r["collection"] == "Révision CEP" and r["matiere"] == "es")

from urllib.parse import quote
def parcours(c):
    t = txt(ok(c.get("/preparation")))
    assert "Résumés" in t and "CM1 A" in t
    for f in (geo, fr4, conte):                  # « Cette semaine » retrouve les fiches conçues par SA / unité
        t = "".join(txt(ok(c.get(f"/preparation/fiches?classe={cm1}&semaine=1&matiere={f['matiere']}&page={p}"))) for p in (1, 2, 3))
        # la fiche retenue dans la SA / l'unité dépend du jour (séances réparties sur le mois) : une fiche de la même SA / unité
        meme = [x for x in C["fiches"] if x["cours"] == f["cours"] and x["matiere"] == f["matiere"]]
        assert any(x["titre"] in t for x in meme), f["titre"]
    t = txt(ok(c.get("/preparation")))
    assert "au total" in t
    t = txt(ok(c.get(f"/preparation/fiches/{geo['id']}")))
    assert "à valider par le conseiller pédagogique" in t and "RÉALISATION" in t and "Port autonome" not in t
    s, n = texte_pdf(ok(c.get(f"/preparation/fiches/{geo['id']}.pdf?classe={cm1}")))
    assert "FICHE DE PRÉPARATION" in s and "CM1 A" in s and "RETOUR ET" in s and "PROJECTION" in s, s[:600]
    from urllib.parse import quote
    t = txt(ok(c.get("/preparation/fiches?cours=CM1&matiere=ea&statut=concue&q=" + quote(conte["titre"]))))
    assert conte["titre"] in t and "fiche(s)" in t
    # résumés
    t = txt(ok(c.get("/preparation/resumes")))
    assert "l'essentiel à retenir" in t and rm["titre"] in t and rc["titre"] in t and "PDF élève" in t
    t = txt(ok(c.get("/preparation/resumes?col=cep&matiere=es")))
    assert rc["titre"] in t and rm["titre"] not in t
    t = txt(ok(c.get(f"/preparation/resumes/{rm['id']}")))
    assert rm["regle"] in t and rm["exercices"][0]["r"] in t and "Réponse" in t
    t = txt(ok(c.get(f"/preparation/resumes/{rm['id']}?eleve=1")))
    assert rm["exercices"][0]["q"] in t and "Réponse :" not in t
    s, n = texte_pdf(ok(c.get(f"/preparation/resumes/{rc['id']}.pdf")))
    assert "Je retiens" in s and "Réponse" in s and "Exercices" in s
    s, n = texte_pdf(ok(c.get(f"/preparation/resumes/{rc['id']}.pdf?eleve=1")))
    assert "Exercices" in s and "Réponse" not in s and "Nom :" in s
    s, n = texte_pdf(ok(c.get("/preparation/resumes.pdf?col=maths&cours=CE1")))
    assert "RÉSUMÉS" in s and n >= 3, n
    s, n = texte_pdf(ok(c.get("/preparation/resumes.pdf?col=francais-cm1&eleve=1")))
    assert "FICHES DE RÉVISION" in s and "Réponse" not in s and n >= 10, n
    ok(c.get("/preparation/resumes/inconnu"), 404)
    ok(c.get("/preparation/resumes.pdf?col=cep&cours=CI"), 404)
    # lot 2 : fiches importées, guide officiel CP, doublons
    t = txt(ok(c.get(f"/preparation/fiches/{cs1['id']}")))
    assert cs1["titre"] in t and "transmises par la CS" in t
    s, n = texte_pdf(ok(c.get(f"/preparation/fiches/{cs1['id']}.pdf")))
    assert "FICHE DE PRÉPARATION" in s
    t = txt(ok(c.get("/preparation/fiches?q=" + quote("transmises par la CS"))))
    assert "fiche(s)" in t and cs1["titre"][:20] in t
    t = txt(ok(c.get("/preparation/guides?matiere=maths&cours=CP")))
    assert "Guide de l'enseignant CP" in t and "officiel" in t
    t = txt(ok(c.get("/preparation/guides/g-memp-ma-cp")))
    assert "Progression annuelle" in t and "Fiches de référence et fiches associées" in t
    s, n = texte_pdf(ok(c.get("/preparation/guides/g-memp-ma-cp.pdf")))
    assert "GUIDE PÉDAGOGIQUE" in s and n >= 5, n
    t = txt(ok(c.get(f"/preparation/fiches/{cp7['id']}")))
    assert "relevé par OCR" in t and "RÉALISATION" in t
    t = txt(ok(c.get("/preparation/manquants")))
    assert "Lot 2" in t and "Doublons" in t and "Guide officiel de Mathématiques CP" in t
    assert "Inventaire CM1" in t and "Séances de référence" in t and "Éducation artistique" in t and "Restent à faire" in t

c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
t = txt(ok(c.get("/eleves")))
assert "Résumés — l’essentiel à retenir" in t
parcours(c)
ok(c.get("/logout"), 302)
c = app.test_client()
ok(c.post("/login", data={"identifiant": "ens1", "mdp": "ens-mdp-123"}), 302)
parcours(c)
ok(c.get("/logout"), 302)
if "ens_portail" in app.view_functions:
    c = app.test_client()
    ok(c.post("/enseignant", data={"identifiant": "ens1", "mdp": "ens-mdp-123"}), 302)
    assert "Résumés — l’essentiel à retenir" in txt(ok(c.get("/preparation/resumes")))
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("GESCOL_EDITION", "GESCOL_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestInventaireCM1(unittest.TestCase):
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
        self.assertIn("inventaire_cm1", c)
        self.assertTrue(all(r["mention"].startswith("Résumé original") for r in c["resumes"]))
        # aucune trace de l'auteur ou de l'éditeur des documents de référence dans le corpus publié
        brut = json.dumps(c, ensure_ascii=False)
        for interdit in ("MARIUS", "97125727", "ABOGOUNRIN", "Yaslo", "PIOILALOUBI", "PIO ILALOU", "97235640", "HOUNGBEDJI",
                         "@jacques", "gmail", "Propriété privée", "CamScanner"):
            self.assertNotIn(interdit, brut)
        doc = self.lire("docs", "inventaire_fiches.md")
        self.assertIn("Inventaire CM1", doc)
        self.assertIn("## 9. Doublons", doc)
        self.assertNotIn("PIO ILALOU", doc)
        self.assertNotIn("MARIUS", doc)
        self.assertIn("prep_resumes", self.lire("templates", "base.html"))


if __name__ == "__main__":
    unittest.main()
