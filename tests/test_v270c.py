# -*- coding: utf-8 -*-
"""v2.7 : lycée agricole (registres de ferme-école, bibliothèque agricole, TP) et signature masquable des devoirs et fiches."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
SCRIPT = r'''
import base64, io, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "sec_publique"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from PIL import Image
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0, mdp_hash=? WHERE identifiant='admin'", (generate_password_hash("Adm#2026xy"),))
    ex("INSERT INTO classes (nom, niveau) VALUES ('2nde AGRI','2nde')")
    ca = q("SELECT id FROM classes")[0]["id"]
    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash) VALUES ('prof1','KOUASSI Paul','enseignant',?)", (generate_password_hash("Prof#2026x"),))
    uid = q("SELECT id FROM utilisateurs WHERE identifiant='prof1'")[0]["id"]
    b = io.BytesIO(); Image.new("RGBA", (120, 40), (0, 0, 0, 255)).save(b, "PNG")
    ex("INSERT INTO signatures (cle, image, maj) VALUES (?,?,'x')", (f"enseignant:{uid}", "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()))
ctx = app.app_context(); ctx.push()
a = app.test_client(); a.get("/login"); a.post("/login", data={"identifiant": "admin", "mdp": "Adm#2026xy"})
for k in ["campagnes", "parcelles", "travaux_agri", "cheptel", "sante_animale", "intrants", "production", "materiel_agri"]:
    assert a.get(f"/reg/sec/{k}").status_code == 200, k
for vue in ["apc", "tp", "exposes", "fiches", "revisions"]:
    r = a.get(f"/ressources-secondaire?vue={vue}&matiere=" + {"apc": "Productions animales", "tp": "Travaux pratiques agricoles", "exposes": "Productions animales", "fiches": "Productions animales", "revisions": "Productions animales"}[vue])
    assert r.status_code == 200 and (b"Productions animales" in r.data or b"Travaux pratiques agricoles" in r.data), vue
import epreuves_apc as AP, agri_sec as AG, fiches_sec as FS
ia = next(i for i, e in enumerate(AP.EPREUVES) if e["matiere"] == AG.PA and e.get("type") == "Interrogation écrite")
assert a.get(f"/ressources-secondaire/apc/{ia}").status_code == 200
assert "Interrogation écrite" in a.get(f"/ressources-secondaire/apc/{ia}").get_data(as_text=True)
assert a.get(f"/ressources-secondaire/apc/{ia}?corrige=1").status_code == 200
assert a.get("/ressources-secondaire/tp/0").status_code == 200
assert a.get("/ressources-secondaire/tp/0").status_code == 200 and a.get("/ressources-secondaire/tp/999").status_code == 404
c = app.test_client(); c.get("/login"); c.post("/login", data={"identifiant": "prof1", "mdp": "Prof#2026x"})
mat = q("SELECT id, nom FROM matieres WHERE code='AGRI_TP'")
assert mat, "matière agricole absente"
mid = mat[0]["id"]
ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,?)", (uid, ca, mid))
r = c.get(f"/ens-sec/cours/{ca}/{mid}"); assert r.status_code == 200 and "Copier et modifier" in r.get_data(as_text=True)
r = c.post(f"/ens-sec/copier/tp/0", data={"cid": ca, "mid": mid}); assert r.status_code == 302, r.status_code
did = q("SELECT id FROM docs_sec WHERE kind='tp'")[0]["id"]
h = c.get(f"/ens-sec/tp/{did}").get_data(as_text=True)
assert "Signature du professeur" in h and "Masquer la signature" in h
h2 = c.get(f"/ens-sec/tp/{did}?sans_sig=1").get_data(as_text=True)
assert "Signature du professeur" not in h2 and "Afficher la signature" in h2
r = c.post(f"/ens-sec/copier/apc/{ia}", data={"cid": ca, "mid": mid}); assert r.status_code == 302
dv = q("SELECT donnees FROM docs_sec WHERE kind='devoir'")[0]["donnees"]
assert "Interrogation écrite" in dv and "Éléments" not in dv and ". " in dv
did2 = q("SELECT id FROM docs_sec WHERE kind='devoir'")[0]["id"]
assert "Signature du professeur" not in c.get(f"/ens-sec/devoir/{did2}?sans_sig=1").get_data(as_text=True)
assert "Signature du professeur" in c.get(f"/ens-sec/devoir/{did2}").get_data(as_text=True)
import json
l = json.loads(a.get("/referentiel-ecoles/chercher?q=EPP+Akpakpa").data)
assert l and all("EPP" in x["nom"] or "AKPAKPA" in x["nom"] for x in l), l
assert json.loads(a.get("/referentiel-ecoles/chercher?q=a").data) == []
r = a.get("/rapport-etablissement"); assert r.status_code == 200 and "Situation statistique" in r.get_data(as_text=True), r.status_code
r = a.get("/exporter.pdf?page=/rapport-etablissement"); assert r.status_code == 200 and r.mimetype == "application/pdf", r.status_code
r = a.get("/exporter.docx?page=/rapport-etablissement"); assert r.status_code == 200, r.status_code
print("OK")
'''


class TestV270c(unittest.TestCase):
    def test_agri(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)
        self.assertIn("OK", r.stdout, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
