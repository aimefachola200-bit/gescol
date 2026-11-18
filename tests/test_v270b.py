# -*- coding: utf-8 -*-
"""v2.7 : signatures, griffes, cachets et logo intégrés aux exports PDF / Word ; filigrane Word."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
SCRIPT = r'''
import base64, io, os, sys, tempfile, zipfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "sec_publique"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from PIL import Image
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
    ex("INSERT INTO classes (nom, niveau) VALUES ('2nde A','2nde')")
    ca = q("SELECT id FROM classes")[0]["id"]
    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash) VALUES ('prof1','KOUASSI Paul','enseignant',?)", (generate_password_hash("Prof#2026x"),))
    uid = q("SELECT id FROM utilisateurs WHERE identifiant='prof1'")[0]["id"]
    b = io.BytesIO(); Image.new("RGBA", (120, 40), (0, 0, 0, 255)).save(b, "PNG")
    ex("INSERT INTO signatures (cle, image, maj) VALUES (?,?,'x')", (f"enseignant:{uid}", "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()))
    mm = q("SELECT id, nom FROM matieres WHERE cycle='secondaire' ORDER BY ordre LIMIT 1")[0]
    ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,?)", (uid, ca, mm["id"]))
ctx = app.app_context(); ctx.push()
c = app.test_client(); c.get("/login"); c.post("/login", data={"identifiant": "prof1", "mdp": "Prof#2026x"})
def creer(kind, **v):
    r = c.post(f"/ens-sec/nouveau/{kind}?cid={ca}&mid={mm['id']}", data=dict(titre="Essai " + kind, matiere=mm["nom"], **v)); assert r.status_code == 302, (kind, r.status_code)
    return q("SELECT id FROM docs_sec WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,))[0]["id"]
with app.app_context():
    eid = q("SELECT id FROM ecoles ORDER BY id LIMIT 1")
    eid = eid[0]["id"] if eid else 1
    ex("INSERT INTO signataires (ecole_id, fonction, nom) VALUES (?,?,?)", (eid, "censeur", "AGBO Théophile"))
    ex("INSERT INTO signatures (cle, image, maj) VALUES (?,?,'x')", (f"ecole:{eid}:censeur", "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()))
dv = creer("devoir", consignes="Question un | 5", total="20", visa="censeur")
assert "Visa : Le Censeur" in c.get(f"/ens-sec/devoir/{dv}").get_data(as_text=True)
assert "Ma signature et ma griffe" in c.get("/ens-sec").get_data(as_text=True)
h = c.get("/signatures-cachets").get_data(as_text=True); assert "Ma signature" in h and "classe:%d:titulaire" % ca in h and "Noms des signataires" not in h
fi = creer("fiche", competence="Compétence XYZ")
def docx_texte(data):
    z = zipfile.ZipFile(io.BytesIO(data)); return z, z.read("word/document.xml").decode()
r = c.get(f"/exporter.docx?page=/ens-sec/devoir/{dv}"); z, x = docx_texte(r.data)
medias = [n for n in z.namelist() if n.startswith("word/media/")]
assert len(medias) >= 3, (z.namelist(), "signature + griffe attendues")      # signature + griffe (+ logo si présent)
assert "<w:drawing>" in x and "word/header1.xml" not in z.namelist()          # pas de filigrane sur un devoir
r = c.get(f"/exporter.pdf?page=/ens-sec/devoir/{dv}"); assert r.data[:4] == b"%PDF"
from pypdf import PdfReader
pg = PdfReader(io.BytesIO(r.data)).pages
assert any("/XObject" in (p.get("/Resources") or {}) and len(p["/Resources"]["/XObject"]) for p in pg), "images absentes du PDF"
r = c.get(f"/exporter.docx?page=/ens-sec/fiche/{fi}"); z, x = docx_texte(r.data)
assert "word/header1.xml" in z.namelist(), z.namelist()
h = z.read("word/header1.xml").decode(); assert "KOUASSI Paul" in h
assert "headerReference" in x
print("OK")
'''


class T(unittest.TestCase):
    def test_images_export(self):
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=dict(os.environ, PREFIXE_SCRIPT=PREFIXE), capture_output=True, text=True)
        self.assertIn("OK", r.stdout, (r.stdout + r.stderr)[-2500:])


if __name__ == "__main__":
    unittest.main()
