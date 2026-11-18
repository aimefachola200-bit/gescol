# -*- coding: utf-8 -*-
"""CEP : photos des candidats pour la plateforme EducMaster (Excel avec photos, PDF légendé, ZIP numéro_NOM_Prénom.jpg)."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
SCRIPT = r'''
import base64, io, os, sys, tempfile, zipfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "publique"
sys.path.insert(0, os.getcwd())
from app import app, ex, q, enregistrer_photo_data
from PIL import Image
app.config["TESTING"] = True
c = app.test_client(); c.get("/login"); c.post("/login", data={"identifiant": "admin", "mdp": "admin123"})
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
    cl = q("SELECT id FROM classes WHERE niveau='CM2' LIMIT 1")
    if not cl:
        ex("INSERT INTO classes (nom, niveau) VALUES ('CM2 A','CM2')"); cl = q("SELECT id FROM classes WHERE niveau='CM2' LIMIT 1")
    cid = cl[0]["id"]
    for nom, pre, mat in (("FACHOLA", "Aimé", "1236549879"), ("DOSSOU", "Marie Claire", ""), ("ADJOVI", "Jean", "5550001")):
        ex("INSERT INTO eleves (nom, prenoms, sexe, classe_id, statut, date_inscription, annee, matricule_educmaster) VALUES (?,?,?,?,?,?,?,?)",
           (nom, pre, "M", cid, "inscrit", "2026-10-01", __import__("config").ANNEE_ACTIVE, mat or None))
    eid = q("SELECT id FROM eleves WHERE nom='FACHOLA'")[0]["id"]
    b = io.BytesIO(); Image.new("RGB", (300, 380), (30, 90, 200)).save(b, "JPEG")
    assert enregistrer_photo_data(eid, "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode())
r = c.get(f"/cep/classe/{cid}/photos-educmaster.xlsx"); assert r.status_code == 200 and r.data[:2] == b"PK", r.status_code
z = zipfile.ZipFile(io.BytesIO(r.data)); assert any(n.startswith("xl/media/") for n in z.namelist())
from openpyxl import load_workbook
ws = load_workbook(io.BytesIO(r.data)).active
vals = [[x.value for x in row] for row in ws.iter_rows(min_row=4)]
assert any(v[1] == "1236549879" and v[2] == "FACHOLA" and v[3] == "Aimé" and v[4] == "1236549879_FACHOLA_Aimé.jpg" for v in vals), vals
assert any(v[1] == "À COMPLÉTER" for v in vals)
r = c.get(f"/cep/classe/{cid}/photos-educmaster.pdf"); assert r.data[:4] == b"%PDF"
from pypdf import PdfReader
t = PdfReader(io.BytesIO(r.data)).pages[0].extract_text(); assert "1236549879_FACHOLA_Aim" in t, t
r = c.get(f"/cep/classe/{cid}/photos-educmaster.zip"); z = zipfile.ZipFile(io.BytesIO(r.data))
assert "1236549879_FACHOLA_Aimé.jpg" in z.namelist() or any(n.startswith("1236549879_FACHOLA_Aim") for n in z.namelist()), z.namelist()
assert "_non_exportes.txt" in z.namelist()
assert "Photos EducMaster" in c.get(f"/cep?classe={cid}").get_data(as_text=True)
print("OK")
'''


class T(unittest.TestCase):
    def test_photos_educmaster(self):
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=dict(os.environ, PREFIXE_SCRIPT=PREFIXE), capture_output=True, text=True)
        self.assertIn("OK", r.stdout, (r.stdout + r.stderr)[-2000:])


if __name__ == "__main__":
    unittest.main()
