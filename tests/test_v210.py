# -*- coding: utf-8 -*-
"""Tests 2.1 : lot du 29/10/2026.
(1) ES / EPS : les SA des mesures correctives sont le programme en vigueur (CI → CM2, séquences, source citée), page
    Programmes avec le bandeau « Programme en vigueur : mesures correctives », fiches et résumés rattachés ;
(2) maternelle : domaines, sections, progression (grands sourcés, petits « proposé »), fiches conçues ouvertes et
    imprimées, filtres section → domaine → composante → mois / semaine, vues mois / semaine / jour, emploi du temps,
    grilles d'observation (avec la liste des enfants), repères, classeur PDF ; « Cette semaine » d'une classe de
    Maternelle 2 montre les activités de la maternelle ;
(3) corpus : aucun texte du document de référence marqué (« Fiche de la maternelle ») n'est repris.
Lancer : python3 -m unittest tests.test_v210"""
import gzip
import json
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import html, io, json, os, re, sys, tempfile
from datetime import date
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = "publique"; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
def ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.data[:400])
    return r
def pdf(r):
    ok(r); assert r.data[:4] == b"%PDF", r.data[:100]; return r
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    m2 = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES (?,?,?,?)", ("Maternelle 2 A", "Maternelle 2", 0, 1))
    for n, (nom, pr) in enumerate([("ADJOVI", "Grâce"), ("BIAOU", "Rodrigue")]):
        ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, classe_id, statut, date_inscription, annee) VALUES (?,?,?,?,?, 'inscrit', '2026-09-15', ?)", (f"M2-{n}", nom, pr, "F", m2, config.ANNEE_ACTIVE))
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302

# ---------------------------------------------------------------- (1) programme en vigueur ES / EPS
import m_preparation as MP
C = MP.corpus()
pr = [p for p in C["programmes"] if p["matiere"] in ("es", "eps")]
assert pr and all(p.get("en_vigueur") and "Mesures correctives" in p["source"] for p in pr)
for m in ("es", "eps"):
    for cours in ("CI", "CP", "CE1", "CE2", "CM1", "CM2"):
        assert any(p["matiere"] == m and p["cours"] == cours and p["sequences"] for p in pr), (m, cours)
assert sum(len(p["sequences"]) for p in pr) > 500
t = ok(c.get("/preparation/programmes?cours=CI&matiere=es")).data.decode()
assert "Programme en vigueur : mesures correctives" in t and "Je respecte le drapeau" in t
t = ok(c.get("/preparation/programmes?cours=CE1&matiere=es")).data.decode()
assert "Morale" in t and "Répartition de l" in t
p = next(x for x in pr if x["cours"] == "CM1" and x["matiere"] == "eps" and x["num"] == 1)
t = ok(c.get("/preparation/programmes/" + p["id"])).data.decode()
assert "Programme en vigueur : mesures correctives" in t and "triple saut" in t and "Séquences (15)" in t
fes = [f for f in C["fiches"] if f["matiere"] in ("es", "eps")]
rat = [f for f in fes if f.get("programme_id")]
assert len(rat) / len(fes) > 0.85, (len(rat), len(fes))
f = next(f for f in rat if f["cours"] == "CM1")
assert f["programme_id"] in C["prog_par_id"] and C["prog_par_id"][f["programme_id"]]["num"] == f["sa"]
t = ok(c.get("/preparation/fiches/" + f["id"])).data.decode()
assert "Programme en vigueur : mesures correctives" in t
assert any(x["id"] == "mc-10" and "Prise en main" in x["contenu"] for x in C["mesures_correctives"])
print("ES_EPS_OK")

# ---------------------------------------------------------------- (2) maternelle
M = C["maternelle"]
assert len(M["domaines"]) == 5 and {s["code"] for s in M["sections"]} == {"petits", "grands"}
gr = [x for x in M["progressions"] if x["section"] == "grands"]
pe = [x for x in M["progressions"] if x["section"] == "petits"]
assert len(gr) > 400 and len(pe) == len(gr) and all(x["propose"] for x in pe) and all("CS Cotonou II" in x["source"] for x in gr)
assert len(M["fiches"]) > 250 and all(C["fiche_par_id"][i]["cours"] == "MAT" for i in M["fiches"])
fm = C["fiche_par_id"][M["fiches"][0]]
assert fm["statut"] == "concue" and "à valider" in fm["mention"] and fm["je_retiens"].startswith("Pour l'éducateur")
assert {e["section"]: e["propose"] for e in M["emplois_du_temps"]} == {"grands": False, "petits": True}
t = ok(c.get("/preparation/maternelle")).data.decode()
assert "Progression 2026-2027" in t and "École maternelle" in t
t = ok(c.get("/preparation/maternelle?section=grands&domaine=D3&composante=Pré-mathématique")).data.decode()
assert "Pré-mathématique" in t and "Lavage des mains" not in t.split("Progression 2026")[1]
t = ok(c.get("/preparation/maternelle?section=petits")).data.decode()
assert "proposé" in t
for vue in ("mois", "semaine", "jour"):
    ok(c.get(f"/preparation/maternelle?vue={vue}&mois=Novembre&semaine=2&jour=Mardi"))
    pdf(c.get(f"/preparation/maternelle/planification.pdf?vue={vue}&mois=Novembre&semaine=2&jour=Mardi"))
t = ok(c.get("/preparation/maternelle?vue=semaine&mois=Novembre&semaine=1")).data.decode()
assert "Lundi" in t and "Vendredi" in t
ok(c.get("/preparation/maternelle/emploi-du-temps?section=grands")); pdf(c.get("/preparation/maternelle/emploi-du-temps.pdf?section=petits"))
t = ok(c.get("/preparation/maternelle/grilles")).data.decode()
assert "pas d'épreuves écrites" in t
r = pdf(c.get(f"/preparation/maternelle/grilles.pdf?composante=Pré-lecture&classe={m2}"))
assert len(r.data) > 3000
ok(c.get("/preparation/maternelle/reperes?domaine=D1"))
pdf(c.get(f"/preparation/fiches/{fm['id']}.pdf"))
r = pdf(c.get(f"/preparation/maternelle/classeur.pdf?mois=Octobre&semaine=2&classe={m2}"))
import pypdf
assert len(pypdf.PdfReader(io.BytesIO(r.data)).pages) >= 3
# « Cette semaine » : la classe de Maternelle 2 voit les activités de la maternelle (domaines)
t = ok(c.get("/preparation")).data.decode()
assert "Maternelle 2 A" in t and "section des grands" in t and "Domaine" in t
print("MATERNELLE_OK")
'''


def lancer(script, timeout=900):
    env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
    return subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=env, capture_output=True, text=True, timeout=timeout)


class TestV210(unittest.TestCase):
    def test_lot_2026_10_29(self):
        r = lancer(SCRIPT)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
        self.assertIn("ES_EPS_OK", r.stdout)
        self.assertIn("MATERNELLE_OK", r.stdout)

    def test_reference_non_reprise(self):
        """Le document marqué n'est cité qu'en référence : aucun extrait (phrase caractéristique) dans le corpus."""
        with gzip.open(os.path.join(RACINE, "static", "pedafiche_corpus.json.gz"), "rt", encoding="utf-8") as f:
            C = json.load(f)
        M = C["maternelle"]
        self.assertTrue(any("référence seulement" in s for s in M["sources"]))
        texte = json.dumps([C["fiches"][i] for i in range(len(C["fiches"])) if C["fiches"][i]["cours"] == "MAT"], ensure_ascii=False)
        self.assertNotIn("@", texte)


if __name__ == "__main__":
    unittest.main()
