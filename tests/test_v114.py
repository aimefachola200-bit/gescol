# -*- coding: utf-8 -*-
"""Tests de la version 1.14 : SCOLARIS Enseignant — application personnelle de l'enseignant (premier lancement,
menu réduit, élèves ajoutés / importés par l'enseignant, emplois du temps de ses niveaux, certificats PDF pré-remplis,
périmètre) et portail /enseignant des applications d'école. Lancer : python3 -m unittest tests.test_v114"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"


def lancer(script, edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)


ENTETE = r'''
import html, io, json, os, sys, tempfile
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
        return "\n".join(p.extract_text() or "" for p in d.pages)
NOM = config.NOMS_APPLI["enseignant"]
from html.parser import HTMLParser
class Champs(HTMLParser):
    """Valeurs pré-remplies d'un formulaire (input, select, textarea) : ce que l'enseignant enverrait sans rien toucher."""
    def __init__(self):
        super().__init__(); self.v = {}; self.sel = None; self.zone = None
    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "input" and a.get("name") and a.get("type") not in ("submit", "button", "file", "checkbox", "radio"):
            self.v[a["name"]] = a.get("value") or ""
        elif tag == "select" and a.get("name"):
            self.sel = a["name"]; self.v.setdefault(self.sel, "")
        elif tag == "option" and self.sel and "selected" in a:
            self.v[self.sel] = a.get("value", "")
        elif tag == "textarea" and a.get("name"):
            self.zone = a["name"]; self.v[self.zone] = ""
    def handle_endtag(self, tag):
        if tag == "select": self.sel = None
        if tag == "textarea": self.zone = None
    def handle_data(self, d):
        if self.zone: self.v[self.zone] += d
def champs(r):
    p = Champs(); p.feed(r.data.decode()); return p.v
'''

APPLICATION = ENTETE + r'''
assert config.enseignant() and NOM == P + " Enseignant"
c = app.test_client()
# 1. premier lancement : tout mène à l'assistant
assert ok(c.get("/"), 302).headers["Location"].endswith("/enseignant/premier-lancement")
assert ok(c.get("/login"), 302).headers["Location"].endswith("/enseignant/premier-lancement")
t = txt(ok(c.get("/enseignant/premier-lancement")))
assert "Mon profil" in t and "Mon école" in t and "Ma ou mes classes" in t and "NIP" in t and "Grade" in t
d = dict(nom="Houngbo", prenoms="Afiavi Rosine", sexe="F", nip="1234567890", matricule="MAT-77", grade="B1-5",
         categorie="ACDPE", statut="Titulaire", date_naissance="1990-04-02",
         lieu_naissance="Pobè", telephone="0197000000", email="", date_prise_service="2015-10-01",
         date_service_ecole="2022-10-01", diplome_academique="BAC D", diplome_academique_annee="2010",
         diplome_pro="CEAP et CAP", diplome_pro_annee="2018", ecole_nom="EPP Issaba Centre", secteur="publique",
         cs="Pobè", departement="Plateau", commune="Pobè", directeur_nom="ADJAHO Paul", directeur_tel="0196000000",
         ecole_telephone="", ccs_nom="KOTO Marc", identifiant="afiavi", mdp="motdepasse1", confirmation="motdepasse1",
         classe_nom_1="CM2 A", classe_niveau_1="CM2", classe_nom_2="CE1 B", classe_niveau_2="CE1")
mauvais = dict(d, confirmation="autre-mdp", classe_nom_1="", classe_niveau_1="", classe_nom_2="", classe_niveau_2="")
t = txt(ok(c.post("/enseignant/premier-lancement", data=mauvais), 400))
assert "confirmation" in t and "au moins une classe" in t
assert ok(c.post("/enseignant/premier-lancement", data=d), 302).headers["Location"].endswith("/enseignant/tableau")
with app.app_context():
    assert q("SELECT actif FROM utilisateurs WHERE identifiant='admin'", un=True)["actif"] == 0
    u = q("SELECT * FROM utilisateurs WHERE identifiant='afiavi'", un=True)
    assert u["role"] == "enseignant" and u["actif"] == 1
    assert len(q("SELECT * FROM affectations WHERE user_id=?", (u["id"],))) == 2
    p = q("SELECT * FROM personnel WHERE user_id=?", (u["id"],), un=True)
    assert p["nip"] == "1234567890" and p["matricule"] == "MAT-77"
    car = q("SELECT * FROM personnel_carriere WHERE personnel_id=?", (p["id"],), un=True)
    assert car["grade"] == "B1-5" and car["categorie"] == "ACDPE"
    assert car["date_prise_service"] == "2015-10-01" and car["cap"] == "oui" and car["ceap"] == "oui"
    e = q("SELECT * FROM ecoles WHERE id=1", un=True)
    assert e["nom"] == "EPP Issaba Centre" and e["statut"] == "Publique" and e["cs"] == "Pobè" and e["directeur_nom"] == "ADJAHO Paul"
    cm2 = q("SELECT id FROM classes WHERE nom='CM2 A'", un=True)["id"]
    pid = p["id"]
# l'assistant n'est plus accessible ; le compte admin de départ ne se connecte plus
assert ok(c.get("/enseignant/premier-lancement"), 302).headers["Location"].endswith("/enseignant")
assert config.publique()
# 2. menu de l'enseignant uniquement
t = txt(ok(c.get("/enseignant/tableau")))
for m in ("Tableau de bord", "Ma classe", "Emplois du temps", "Planification annuelle", "Planification mensuelle",
          "Calendrier scolaire officiel", "Règlement intérieur", "Thèmes d'UP", "Mes certificats et attestations",
          "Ma fiche de carrière", "Mot de passe et question de secours", "Ma signature", "Importer mes élèves", NOM):
    assert m in t, m
for m in ("Finances", "Administration", "Trésorerie", "Utilisateurs et affectations", "Tableau synoptique de l'école", "Recensement"):
    assert m not in t, m
assert ok(c.get("/"), 302).headers["Location"].endswith("/enseignant/tableau")
m = json.loads(ok(c.get("/enseignant/manifest.webmanifest")).data)
assert m["start_url"].startswith("/enseignant") and m["name"].startswith(NOM)
assert "/enseignant/manifest.webmanifest" in t
# 3. l'enseignant ajoute et importe lui-même ses élèves (dans SES classes)
ok(c.get(f"/eleves/nouveau?classe={cm2}"))
r = ok(c.post("/eleves/nouveau", data=dict(nom="AGBO", prenoms="Kossi", sexe="M", classe_id=str(cm2), statut="inscrit",
                                          date_naissance="2014-01-01")), 302)
with app.app_context():
    assert q("SELECT COUNT(*) n FROM eleves WHERE classe_id=?", (cm2,), un=True)["n"] == 1
    autre = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CP Z','CP',0,1)")
ok(c.post("/eleves/nouveau", data=dict(nom="X", prenoms="Y", sexe="M", classe_id=str(autre), statut="inscrit")), 403)
ok(c.get("/eleves/import")); ok(c.get("/eleves/modele.xlsx") if "eleves_modele_xlsx" in app.view_functions else c.get("/eleves/import"))
# classes de l'enseignant
ok(c.post("/enseignant/classes", data={"action": "ajouter", "nom": "CM1 C", "niveau": "CM1"}), 302)
assert "CM1 C" in txt(ok(c.get("/enseignant/classes")))
# 4. emploi du temps et planification : SES niveaux en écriture, pas les autres
ok(c.get("/synoptique/edt/cm2/modifier"))
ok(c.get("/synoptique/edt/cp/modifier"), 403)
ok(c.get("/synoptique/planification/ce1/modifier"))
ok(c.get("/synoptique/planification-mensuelle"))
ok(c.get("/synoptique/reglement"))
ok(c.post("/synoptique/reglement/retablir"), 403)
# 5. périmètre : modules du directeur et de l'école refusés
for u_ in ("/parametres", "/utilisateurs", "/paiements", "/tresorerie", "/personnel", "/ecoles", "/synoptique/personnel/1"):
    ok(c.get(u_), 403)
# 6. certificats pré-remplis
t = txt(ok(c.get("/enseignant/certificats")))
assert "Certificat de travail" in t and "Attestation de direction" in t
for doc in ("certificat_travail", "prise_service_dir", "presence_poste_dir", "attestation_direction", "prise_en_charge"):
    f = champs(ok(c.get(f"/docs-enseignant/{doc}?p={pid}")))
    assert "HOUNGBO" in " ".join(f.values()).upper(), (doc, f)
    f.pop("action", None)
    s = texte_pdf(ok(c.post(f"/docs-enseignant/{doc}?p={pid}", data=f)))
    assert "HOUNGBO" in s.upper(), (doc, s[:400])
# 7. profil modifiable
v = dict(d); v.pop("identifiant"); v.pop("mdp"); v.pop("confirmation"); v["grade"] = "B1-6"; v["ecole_nom"] = "EPP Issaba Nord"
ok(c.post("/enseignant/profil", data=v), 302)
with app.app_context():
    assert q("SELECT grade FROM personnel_carriere WHERE personnel_id=?", (pid,), un=True)["grade"] == "B1-6"
    assert q("SELECT nom FROM ecoles WHERE id=1", un=True)["nom"] == "EPP Issaba Nord"
# 8. déconnexion → page de connexion de l'enseignant ; connexion
assert ok(c.get("/logout"), 302).headers["Location"].endswith("/enseignant")
assert NOM in txt(ok(c.get("/enseignant")))
ok(c.post("/enseignant", data={"identifiant": "admin", "mdp": "admin123"}))
assert ok(c.post("/enseignant", data={"identifiant": "afiavi", "mdp": "motdepasse1"}), 302).headers["Location"].endswith("/enseignant/tableau")
print("OK-" + config.EDITION)
'''

PORTAIL = ENTETE + r'''
if config.juridiction():
    import demo_juridiction; demo_juridiction.main()
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    cid = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM2 T','CM2',0,1)")
    autre = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CP T','CP',0,1)")
    uid = ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) VALUES ('ens1','DOSSOU Jean','enseignant',?,0,1,1)",
             (generate_password_hash("ens-mdp-123"),))
    ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,NULL)", (uid, cid))
    ex("INSERT INTO personnel (matricule, nom, prenoms, sexe, fonction, ecole_id, user_id) VALUES ('P-9','DOSSOU','Jean','M','Enseignant',1,?)", (uid,))
c = app.test_client()
t = txt(ok(c.get("/enseignant")))
assert "SCOLARIS Enseignant".replace("SCOLARIS", P) in t or config.NOM_PORTAIL_ENSEIGNANT in t
assert "/enseignant/manifest.webmanifest" in t
m = json.loads(ok(c.get("/enseignant/manifest.webmanifest")).data)
assert m["start_url"].startswith("/enseignant") and m["id"] == "/enseignant" and config.NOM_PORTAIL_ENSEIGNANT in m["name"]
# un compte qui n'est pas enseignant est renvoyé vers l'application de l'école
assert "réservée aux enseignants" in txt(ok(c.post("/enseignant", data={"identifiant": "admin", "mdp": "admin123"}), 403))
assert ok(c.post("/enseignant", data={"identifiant": "ens1", "mdp": "ens-mdp-123"}), 302).headers["Location"].endswith("/enseignant/tableau")
t = txt(ok(c.get("/enseignant/tableau")))
assert "Mes certificats et attestations" in t and "Ma fiche de carrière" in t and "CM2 T" in t
for m_ in ("Finances", "Administration", "Importer mes élèves", "Mon profil et mon école"):
    assert m_ not in t, m_
# sécurité inchangée (m_perimetre_enseignant)
ok(c.get(f"/ma-classe/{autre}"), 403)
ok(c.get("/eleves/nouveau"), 403)
ok(c.get("/eleves/import"), 403)
ok(c.get("/synoptique/edt/cm2/modifier"), 403)
ok(c.get("/enseignant/classes"), 404)
for u_ in ("/parametres", "/utilisateurs", "/paiements"):
    ok(c.get(u_), 403)
assert ok(c.get("/enseignant/profil"), 302).headers["Location"].endswith("/carriere/moi")
ok(c.get("/enseignant/certificats"))
assert ok(c.get("/logout"), 302).headers["Location"].endswith("/enseignant")
# l'application de l'école garde sa page de connexion et son manifeste
assert "/manifest.webmanifest" in txt(ok(c.get("/login")))
print("OK-" + config.EDITION)
'''


class TestApplicationEnseignant(unittest.TestCase):
    def test_application(self):
        r = lancer(APPLICATION, "enseignant")
        self.assertIn("OK-enseignant", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])


class TestPortailEnseignant(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(PORTAIL, ed)
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
