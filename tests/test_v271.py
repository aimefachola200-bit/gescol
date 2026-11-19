# -*- coding: utf-8 -*-
"""v2.7.1 : corrections de terrain — premier écran de l'enseignant, diplômes du secondaire, documents pédagogiques (PDF),
regroupement des fiches par cours et matière, export Excel, circonscriptions masquées au secondaire, bandeau de mise à jour."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "SCOLARIS" if os.path.exists(os.path.join(RACINE, "SCOLARIS_PUBLIC.md")) else "GESCOL"
SCRIPT = r'''
import html, io, os, sys, tempfile, zipfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["ED_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
app.config["TESTING"] = True
def txt(r): return html.unescape(r.data.decode())
c = app.test_client()
if ED == "enseignant":
    d = dict(nom="Houngbo", prenoms="Afiavi Rosine", sexe="F", nip="1234567890", matricule="MAT-77", grade="B1-5", categorie="ACDPE", statut="Titulaire",
             date_naissance="1990-04-02", lieu_naissance="Pobè", telephone="0197000000", email="", date_prise_service="2015-10-01", date_service_ecole="2022-10-01",
             diplome_academique="Licence", diplome_academique_annee="2012", diplome_pro="CAPES", diplome_pro_annee="2018", ecole_nom="Collège de Pobè",
             secteur="publique", cs="", departement="Plateau", commune="Pobè", arrondissement="Pobè", directeur_nom="ADJAHO Paul", directeur_tel="0196000000",
             ecole_telephone="", ccs_nom="", identifiant="afiavi", mdp="motdepasse1", confirmation="motdepasse1", classe_nom_1="3ème A", classe_niveau_1="3ème")
    r = c.get("/enseignant/premier-lancement"); t = txt(r)
    assert 'data-geo="departement"' in t and 'data-geo="commune"' in t and 'data-geo="ecole"' in t and 'data-geo="arrondissement"' in t
    assert t.index('id="departement"') < t.index('id="ecole_nom"')          # d'abord la localité, ensuite l'école
    assert "BAPES" in t and "CAPES" in t and "CAPET" in t
    assert c.post("/enseignant/premier-lancement", data=d).status_code == 302
    with app.app_context():
        car = q("SELECT * FROM personnel_carriere", un=True)
        assert car["dip_pro_sec"] == "CAPES" and car["dip_pro_sec_annee"] == 2018 and car["cap"] != "oui"       # CAPES n'est pas un CAP
        assert q("SELECT arrondissement FROM ecoles WHERE id=1", un=True)["arrondissement"] == "Pobè"
    assert "CAPES" in txt(c.get("/enseignant/profil"))
    # classes du secondaire seules -> professeur déduit ; menu et bibliothèque visibles
    t = txt(c.get("/enseignant/tableau")); assert "Bibliothèque pédagogique" in t and "Mes cours (professeur)" in t and "Documents pédagogiques" in t
    assert "Documents pédagogiques (secondaire)" in txt(c.get("/documents-pedagogiques"))
    assert c.get("/ressources-secondaire").status_code == 200
    t = txt(c.get("/documents-pedagogiques")); assert "Philosophie" in t and "Fichier de Mathématiques" in t        # les deux cycles dans l'application de l'enseignant
else:
    from werkzeug.security import generate_password_hash
    with app.app_context():
        ex("UPDATE utilisateurs SET doit_changer_mdp=0, mdp_hash=? WHERE identifiant='admin'", (generate_password_hash("Adm#2026xy"),))
    c.get("/login"); c.post("/login", data={"identifiant": "admin", "mdp": "Adm#2026xy"})
    t = txt(c.get("/documents-pedagogiques"))
    if config.secondaire():
        assert "Philosophie" in t and "Fichier de Français" not in t and "Mon cahier de réussite" not in t
    else:
        assert "Fichier de Français" in t and "Mon cahier de réussite" in t and "Terminales A et B" not in t
        t = txt(c.get("/documents-pedagogiques?niveau=CM1&matiere=Mathématiques")); assert "Mathématiques CM1" in t and "Fichier ES" not in t
        # fiches de préparation : accès rapide par cours et matière, et titres de regroupement
        t = txt(c.get("/preparation/fiches")); assert "Accès rapide" in t
        t = txt(c.get("/preparation/fiches?cours=CE1")); assert 'class="rupture"' in t
        assert "Documents pédagogiques (PDF)" in t
    # export Excel
    r = c.get("/exporter.xlsx?page=/documents-pedagogiques"); assert r.status_code == 200 and r.data[:2] == b"PK"
    assert "sheet" in r.mimetype
    z = zipfile.ZipFile(io.BytesIO(r.data)); assert any(n.startswith("xl/worksheets/") for n in z.namelist())
    assert "Télécharger Excel" in txt(c.get("/telechargements"))
    # circonscription masquée au secondaire
    t = txt(c.get("/ecoles/nouveau")) if c.get("/ecoles/nouveau").status_code == 200 else ""
    if t and config.secondaire():
        assert "118 circonscriptions" not in t and 'data-cs' not in t
for f in os.listdir(os.path.join(os.getcwd(), "static", "documents_pedagogiques")):
    assert f.endswith(".pdf")
assert len(os.listdir(os.path.join(os.getcwd(), "static", "documents_pedagogiques"))) == 25
print("OK")
'''


class T(unittest.TestCase):
    def lancer(self, ed):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, ED_SCRIPT=ed)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-2500:])

    def test_enseignant(self):
        self.lancer("enseignant")

    def test_primaire(self):
        self.lancer("privee")

    def test_secondaire(self):
        self.lancer("sec_privee")


if __name__ == "__main__":
    unittest.main()
