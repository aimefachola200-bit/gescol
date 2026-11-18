# -*- coding: utf-8 -*-
"""v2.6 : espace enseignant du secondaire (cours par classe et matière, fiches/devoirs/TP modifiables, signature, filigrane)."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
SCRIPT = r'''
import io, os, re, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "sec_publique"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
    ex("INSERT INTO classes (nom, niveau) VALUES ('6e A','6ème')"); ex("INSERT INTO classes (nom, niveau) VALUES ('5e B','5ème')")
    ca = q("SELECT id FROM classes WHERE nom='6e A'")[0]["id"]; cb = q("SELECT id FROM classes WHERE nom='5e B'")[0]["id"]
    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash) VALUES ('prof1','KOUASSI Paul','enseignant',?)", (generate_password_hash("Prof#2026x"),))
    uid = q("SELECT id FROM utilisateurs WHERE identifiant='prof1'")[0]["id"]
    mm = q("SELECT id, nom FROM matieres WHERE cycle='secondaire' ORDER BY ordre LIMIT 2")
    ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,?)", (uid, ca, mm[0]["id"]))
    ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,?)", (uid, ca, mm[1]["id"]))
ctx = app.app_context(); ctx.push()
c = app.test_client(); c.get("/login"); r = c.post("/login", data={"identifiant": "prof1", "mdp": "Prof#2026x"})
h = c.get("/ens-sec").get_data(as_text=True)
assert "6e A" in h and mm[0]["nom"] in h and "5e B" not in h, h[:400]
r = c.get(f"/ens-sec/cours/{ca}/{mm[0]['id']}"); assert r.status_code == 200
assert c.get(f"/ens-sec/cours/{cb}/{mm[0]['id']}").status_code in (403, 404, 302)       # classe qui n'est pas la sienne
r = c.post(f"/ens-sec/nouveau/fiche?cid={ca}&mid={mm[0]['id']}", data={"titre": "Les fractions", "matiere": mm[0]["nom"], "niveau": "6e", "objectifs": "Lire une fraction"}, follow_redirects=False)
assert r.status_code == 302, r.status_code
did = q("SELECT id FROM docs_sec WHERE kind='fiche'")[0]["id"]
v = c.get(f"/ens-sec/fiche/{did}").get_data(as_text=True)
assert 'class="filigrane"' in v and "KOUASSI Paul" in v and "Conception" in v and "Lire une fraction" in v
assert "Cachet" not in v and "griffe.svg" not in v                                 # pas de cachet sur les fiches
# modifier
r = c.post(f"/ens-sec/fiche/{did}/modifier", data={"titre": "Les fractions v2", "objectifs": "Comparer"}); assert r.status_code == 302
assert "Comparer" in c.get(f"/ens-sec/fiche/{did}").get_data(as_text=True)
# devoir : cachet + signature, sans mention Conception
r = c.post(f"/ens-sec/nouveau/devoir?cid={ca}&mid={mm[0]['id']}", data={"titre": "Devoir 1", "type": "Composition", "consignes": "Calcule 1/2+1/4 | 3\nComplète | 2", "total": "20"})
dv = q("SELECT id FROM docs_sec WHERE kind='devoir'")[0]["id"]
v = c.get(f"/ens-sec/devoir/{dv}").get_data(as_text=True)
assert "griffe.svg" in v and "Signature du professeur" in v and "Conception" not in v and 'class="filigrane"' not in v, ("griffe.svg" in v, "Signature du professeur" in v, [v[m.start()-80:m.end()+40] for m in re.finditer("Conception", v)])
# bibliothèque -> copie modifiable
r = c.post("/ens-sec/copier/fiche/0", data={"cid": ca, "mid": mm[0]["id"]}); assert r.status_code == 302
r = c.post("/ens-sec/copier/apc/0", data={"cid": ca, "mid": mm[0]["id"]}); assert r.status_code == 302
assert q("SELECT COUNT(*) n FROM docs_sec")[0]["n"] == 4
assert "Copier dans mes documents" in c.get("/ressources-secondaire/fiche/0").get_data(as_text=True)
# exports : PDF avec filigrane, devoir sans « Conception »
r = c.get(f"/exporter.pdf?page=/ens-sec/devoir/{dv}"); assert r.data[:4] == b"%PDF"
from pypdf import PdfReader
t = PdfReader(io.BytesIO(r.data)).pages[0].extract_text(); assert "Conception" not in t and "Devoir 1" in t, t[-300:]
r = c.get(f"/exporter.pdf?page=/ens-sec/fiche/{did}"); t = PdfReader(io.BytesIO(r.data)).pages[0].extract_text(); assert "Conception" in t
r = c.get(f"/exporter.docx?page=/ens-sec/fiche/{did}"); assert r.data[:2] == b"PK"
assert q("SELECT COUNT(*) n FROM matieres WHERE code LIKE 'TECH_%'")[0]["n"] == 14, "matières techniques"
print("OK")
'''


class T(unittest.TestCase):
    def test_ens_sec(self):
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=dict(os.environ, PREFIXE_SCRIPT=PREFIXE), capture_output=True, text=True)
        self.assertIn("OK", r.stdout, (r.stdout + r.stderr)[-2500:])


if __name__ == "__main__":
    unittest.main()
