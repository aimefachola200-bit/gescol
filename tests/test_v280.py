# -*- coding: utf-8 -*-
"""v2.8 : périmètre « professeur » dans l'application personnelle de l'enseignant (choix titulaire / professeur / les deux)."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "GESCOL"
SCRIPT = r'''
import html, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = "enseignant"; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
app.config["TESTING"] = True
def txt(r): return html.unescape(r.data.decode())
c = app.test_client()
d = dict(nom="Houngbo", prenoms="Afiavi Rosine", sexe="F", nip="1234567890", matricule="MAT-77", grade="B1-5", categorie="ACDPE", statut="Titulaire",
         date_naissance="1990-04-02", lieu_naissance="Pobè", telephone="0197000000", email="", date_prise_service="2015-10-01", date_service_ecole="2022-10-01",
         diplome_academique="BAC D", diplome_academique_annee="2010", diplome_pro="CEAP et CAP", diplome_pro_annee="2018", ecole_nom="Lycée agricole de Pobè",
         secteur="publique", cs="Pobè", departement="Plateau", commune="Pobè", directeur_nom="ADJAHO Paul", directeur_tel="0196000000", ecole_telephone="",
         ccs_nom="KOTO Marc", identifiant="afiavi", mdp="motdepasse1", confirmation="motdepasse1", classe_nom_1="CM2 A", classe_niveau_1="CM2",
         classe_nom_2="2nde AGRI", classe_niveau_2="2nde")
assert c.post("/enseignant/premier-lancement", data=d).status_code == 302
# titulaire par défaut : pas de périmètre professeur
assert c.get("/ens-sec").status_code == 404 and c.get("/ressources-secondaire").status_code == 404
t = txt(c.get("/enseignant/tableau")); assert "Mon périmètre" in t and "Mes cours (professeur)" not in t and "<b>Planification annuelle</b>" in t
# choix : professeur
assert c.post("/enseignant/perimetre", data={"action": "mode", "mode": "professeur"}).status_code == 302
t = txt(c.get("/enseignant/tableau")); assert "Mes cours (professeur)" in t and "<b>Planification annuelle</b>" not in t
t = txt(c.get("/enseignant/perimetre")); assert "Mes matières par classe" in t and "2nde AGRI" in t and "Productions animales" in t
assert c.get("/ens-sec").status_code == 200
assert "Aucun" in txt(c.get("/ens-sec")) or "cours" in txt(c.get("/ens-sec")).lower()
with app.app_context():
    cid = q("SELECT id FROM classes WHERE nom='2nde AGRI'", un=True)["id"]
    mid = q("SELECT id FROM matieres WHERE nom='Productions animales'", un=True)["id"]
assert c.post("/enseignant/perimetre", data={"action": "matieres", "cm": [f"{cid}-{mid}"]}).status_code == 302
t = txt(c.get(f"/ens-sec/cours/{cid}/{mid}")); assert "Productions animales" in t
assert c.get("/ressources-secondaire?vue=apc&matiere=Productions animales").status_code == 200
r = c.post(f"/ens-sec/copier/fiche/0", data={"cid": cid, "mid": mid})
assert r.status_code in (302, 404)
# une classe du primaire ne reçoit aucune matière de professeur
with app.app_context():
    cm2 = q("SELECT id FROM classes WHERE nom='CM2 A'", un=True)["id"]
assert c.post("/enseignant/perimetre", data={"action": "matieres", "cm": [f"{cm2}-{mid}"]}).status_code == 302
with app.app_context():
    assert not q("SELECT 1 FROM affectations WHERE classe_id=? AND matiere_id IS NOT NULL", (cm2,))
# retour titulaire : le périmètre professeur se referme
assert c.post("/enseignant/perimetre", data={"action": "mode", "mode": "titulaire"}).status_code == 302
assert c.get("/ens-sec").status_code == 404
# sauvegarde et restauration depuis l'application de l'enseignant
t = txt(c.get("/enseignant/sauvegarde")); assert "Ma sauvegarde" in t
r = c.post("/enseignant/sauvegarde/telecharger"); assert r.status_code == 200 and r.mimetype == "application/zip", r.status_code
import io
zipdata = r.data
r = c.post("/enseignant/sauvegarde/restaurer", data={"fichier": (io.BytesIO(zipdata), "s.zip"), "confirmation": "non"}); assert r.status_code == 302 and "/enseignant/sauvegarde" in r.headers["Location"]
r = c.post("/enseignant/sauvegarde/verifier", data={"fichier": (io.BytesIO(zipdata), "s.zip")}); assert r.status_code == 302
r = c.post("/enseignant/sauvegarde/restaurer", data={"fichier": (io.BytesIO(zipdata), "s.zip"), "confirmation": "RESTAURER"}); assert r.status_code == 302 and "login" in r.headers["Location"], r.headers["Location"]
print("OK")
'''


class TestV280(unittest.TestCase):
    def test_perimetre_professeur(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GESCOL_")}
        env["PREFIXE_SCRIPT"] = PREFIXE
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)
        self.assertIn("OK", r.stdout, r.stdout + r.stderr[-2500:])


if __name__ == "__main__":
    unittest.main()
