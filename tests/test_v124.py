# -*- coding: utf-8 -*-
"""Tests 1.24 : bureaux de l'UASCEP — cachet (généré rond / rectangulaire, ou image importée) et signature digitale
(dessinée ou importée) de chaque responsable, à tous les niveaux ; documents signés avec cachets, visa de l'autorité
hiérarchique, code de vérification et QR : composition du bureau, PV d'élection et d'installation, attestation de
fonction, liste des bureaux ; vie du bureau par saison (calendrier, activités et résultats, engagements, réunions et
comptes rendus du rapporteur, journal de caisse, budget et état financier du trésorier, inventaire du matériel) et rapport
de fin de saison sportive (PDF signé, Excel) ; éditions école privée, école publique et CS.
Lancer : python3 -m unittest tests.test_v124"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import base64, html, io, os, re, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-1500:]); return r
def txt(r): return html.unescape(r.data.decode())
def texte_pdf(r):
    import pdfplumber
    assert r.mimetype == "application/pdf", (r.request.path, r.mimetype)
    with pdfplumber.open(io.BytesIO(r.data)) as d:
        return "\n".join(p.extract_text() or "" for p in d.pages).replace("\n", " "), len(d.pages), sum(len(p.images) for p in d.pages)
# petite image PNG valide (signature / cachet importés)
import struct, zlib
def png(w=120, h=50):
    lignes = b"".join(b"\x00" + b"".join((b"\x10\x20\x60\xff" if abs(y - x * h // w) < 3 else b"\x00\x00\x00\x00") for x in range(w)) for y in range(h))
    def bloc(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + bloc(b"IDAT", zlib.compress(lignes)) + bloc(b"IEND", b"")
PNG = png()
DATA = "data:image/png;base64," + base64.b64encode(PNG).decode()
JUR = config.EDITION in ("cs", "ddemp")
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
c = app.test_client()
ok(c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}), 302)
if JUR:
    with app.app_context():
        ex("INSERT OR REPLACE INTO jur_structure (id, niveau, departement, cs, nom) VALUES (1, ?, 'Plateau', 'Pobè', 'CS Pobè')", (config.EDITION,))
        cs = ex("INSERT INTO jur_cs (departement, nom) VALUES ('Plateau', 'Pobè')")
        zid = ex("INSERT INTO jur_zones (cs_id, nom, ordre) VALUES (?, 'Zone 1', 1)", (cs,))
        ex("INSERT INTO jur_up (cs_id, zone_id, nom, rup_nom) VALUES (?, ?, 'UP Pobè 1', 'ADJAI Rémi')", (cs, zid))
    niveau, entite = "UP", "UP Pobè 1"
else:
    niveau, entite = "ECOLE", "1"
ids = {}
for i, (nom, pre, sexe, fon) in enumerate([("AKPO", "Clarisse", "F", "Président"), ("BIO", "Saliou", "M", "Secrétaire général"),
                                            ("DOSSOU", "Awa", "F", "Trésorier général"), ("OLA", "Koffi", "M", "Responsable sport"),
                                            ("ADJA", "Rose", "F", "Rapporteur"), ("KOTO", "Paul", "M", "Commissaire aux comptes")], 1):
    ok(c.post(f"/uascep/membre/0?niveau={niveau}&entite={entite}", data={"ordre": i, "nom": nom, "prenoms": pre, "sexe": sexe, "fonction": fon,
       "qualite": "Enseignant", "date_election": "2026-10-15", "duree": 2, "contact": "0100000000"}), 302)
with app.app_context():
    b = q("SELECT * FROM uascep_bureaux WHERE niveau=? AND entite=? AND statut='actif'", (niveau, entite), un=True)
    ex("UPDATE uascep_bureaux SET ag_lieu='Pobè', ag_date='2026-10-15', date_installation='2026-10-30', date_election='2026-10-15', date_fin='2028-10-15' WHERE id=?", (b["id"],))
    for m in q("SELECT * FROM uascep_membres WHERE bureau_id=?", (b["id"],)):
        ids[m["fonction"]] = m["id"]
bid = b["id"]
pres, sg, tr = ids["Président"], ids["Secrétaire général"], ids["Trésorier général"]
# page du cachet : cachet rond généré par défaut (UASCEP + niveau + entité autour, fonction au centre)
t = txt(ok(c.get(f"/uascep/membre/{pres}/cachet")))
assert "Cachet et signature" in t and "<svg" in t and "UASCEP" in t and "PRÉSIDENT" in t.upper() and "Signez dans le cadre" in t
# signature dessinée + cachet rouge
ok(c.post(f"/uascep/membre/{pres}/cachet", data={"cachet_mode": "genere", "cachet_forme": "rond", "cachet_couleur": "rouge", "signature_dessin": DATA}), 302)
with app.app_context():
    m = q("SELECT * FROM uascep_membres WHERE id=?", (pres,), un=True)
    assert m["signature"] == DATA and m["cachet_couleur"] == "rouge" and m["cachet_mode"] == "genere"
assert "#B91C1C" in txt(ok(c.get(f"/uascep/membre/{pres}/cachet")))
# griffe rectangulaire + signature importée pour le SG
ok(c.post(f"/uascep/membre/{sg}/cachet", data={"cachet_mode": "genere", "cachet_forme": "rect", "cachet_couleur": "bleu",
          "signature_fichier": (io.BytesIO(PNG), "sig.png")}, content_type="multipart/form-data"), 302)
# cachet importé pour le trésorier ; format refusé
ok(c.post(f"/uascep/membre/{tr}/cachet", data={"cachet_mode": "image", "cachet_fichier": (io.BytesIO(PNG), "cachet.png")}, content_type="multipart/form-data"), 302)
r = c.post(f"/uascep/membre/{tr}/cachet", data={"cachet_mode": "image", "signature_fichier": (io.BytesIO(b"GIF89a....."), "x.gif")}, content_type="multipart/form-data", follow_redirects=True)
assert "PNG ou JPEG" in txt(r)
with app.app_context():
    s = q("SELECT * FROM uascep_membres WHERE id=?", (sg,), un=True)
    assert s["signature"].startswith("data:image/png;base64,") and s["cachet_forme"] == "rect"
    t_ = q("SELECT * FROM uascep_membres WHERE id=?", (tr,), un=True)
    assert t_["cachet_mode"] == "image" and t_["cachet_image"].startswith("data:image/png")
t = txt(ok(c.get(f"/uascep/membre/{sg}/cachet")))
assert "BIO Saliou".upper() in t.upper() and "Griffe" in t
# tableau du bureau : lien cachet et documents
t = txt(ok(c.get(f"/uascep?onglet={niveau}&entite={entite}")))
assert f"/uascep/membre/{pres}/cachet" in t and "Composition du bureau" in t and "PV d'élection" in t and "PV d'installation" in t and "Liste des bureaux" in t
# documents signés : cachets, signatures (images), visa, code et QR
codes = []
for url, attendu in ((f"/uascep/bureau/{bid}/composition.pdf", "COMPOSITION DU BUREAU DE L'UASCEP"),
                     (f"/uascep/bureau/{bid}/pv.pdf", "PROCÈS-VERBAL D'ÉLECTION"),
                     (f"/uascep/bureau/{bid}/pv.pdf?type=installation", "PROCÈS-VERBAL D'INSTALLATION"),
                     (f"/uascep/membre/{ids['Responsable sport']}/attestation.pdf", "ATTESTATION DE FONCTION"),
                     ("/uascep/liste.pdf", "LISTE DES BUREAUX DE L'UASCEP"),
                     (f"/uascep.pdf?niveau={niveau}&entite={entite}", "BUREAU DE L'UASCEP")):
    s, npg, nimg = texte_pdf(ok(c.get(url)))
    assert attendu in s and "Document vérifiable" in s, (url, s[:400])
    code = re.search(r"code ([0-9A-F]{10})", s).group(1)
    codes.append(code)
    assert nimg >= 1 or "liste" in url, (url, nimg)
    if "liste" not in url:
        assert "Président" in s and "Visa" in s, (url, s[-600:])
s, npg, nimg = texte_pdf(ok(c.get(f"/uascep/bureau/{bid}/composition.pdf")))
assert "Trésorier" in s and "AKPO Clarisse" in s
s, npg, nimg = texte_pdf(ok(c.get(f"/uascep/membre/{ids['Responsable sport']}/attestation.pdf")))
assert "OLA Koffi" in s and "Responsable sport" in s and "AKPO" in s and "Monsieur" in s
s, _, _ = texte_pdf(ok(c.get("/uascep/liste.pdf")))
assert "AKPO Clarisse" in s and "BIO Saliou" in s and "DOSSOU Awa" in s
for code in codes:
    t = txt(ok(c.get(f"/verifier/{code}")))
    assert "UASCEP" in t, code
# ---- saison sportive : rapporteur (réunions, journal), trésorier (caisse, budget), calendrier, engagements, matériel, rapport
S = config.ANNEE_ACTIVE
t = txt(ok(c.get(f"/uascep/bureau/{bid}/saison")))
assert "Saison sportive " + S in t and "Journal de caisse" in t and "Inventaire du matériel" in t and "Réunions et comptes rendus" in t
base = f"/uascep/bureau/{bid}/saison"
ok(c.post(f"{base}/activites/0?saison={S}", data={"date": "2027-03-12", "intitule": "Tournoi de football inter-écoles", "discipline": "Football",
          "categorie": "Minimes", "lieu": "Stade de Pobè", "statut": "Réalisée", "pg": "64", "pf": "12", "equipes": "8",
          "resultats": "Vainqueur : EPP Towé", "distinctions": "Coupe et médailles"}), 302)
ok(c.post(f"{base}/activites/0?saison={S}", data={"date": "2027-04-20", "intitule": "Cross scolaire", "discipline": "Athlétisme", "categorie": "Cadets",
          "lieu": "Pobè", "statut": "Réalisée", "pg": "30", "pf": "28", "resultats": "1re : AGBO Rita"}), 302)
ok(c.post(f"{base}/activites/0?saison={S}", data={"date": "2027-05-10", "intitule": "Finale de handball", "discipline": "Handball", "statut": "Prévue"}), 302)
ok(c.post(f"{base}/activites/0?saison={S}", data={"intitule": ""}), 302)  # refusé (intitulé obligatoire)
ok(c.post(f"{base}/engagements/0?saison={S}", data={"ecole": "EPP Towé", "discipline": "Football", "categorie": "Minimes", "equipe": "Les Aiglons",
          "encadreur": "SOSSA Marc", "jg": "14", "jf": "0", "droit": "5000", "date": "2027-02-01"}), 302)
ok(c.post(f"{base}/reunions/0?saison={S}", data={"date": "2027-01-15", "heure": "15 h", "lieu": "EPP Towé", "type": "Réunion ordinaire",
          "ordre": "1. Programme de la saison\n2. Cotisations", "presents": "AKPO, BIO, DOSSOU", "absents": "OLA (excusé)",
          "decisions": "Tournoi fixé au 12 mars ; cotisation de 10 000 F par école"}), 302)
for d_ in ({"date": "2027-01-20", "nature": "Recette", "categorie": "Cotisations des écoles", "libelle": "Cotisation", "ecole": "EPP Towé", "montant": "10 000", "piece": "R1"},
           {"date": "2027-01-22", "nature": "Recette", "categorie": "Cotisations des écoles", "libelle": "Cotisation", "ecole": "EPP Itassoumba", "montant": "10000", "piece": "R2"},
           {"date": "2027-03-10", "nature": "Dépense", "categorie": "Récompenses (coupes, médailles, prix)", "libelle": "Coupe et médailles", "montant": "12500", "piece": "D1"}):
    ok(c.post(f"{base}/caisse/0?saison={S}", data=d_), 302)
ok(c.post(f"{base}/budget/0?saison={S}", data={"nature": "Recette", "categorie": "Cotisations des écoles", "libelle": "Cotisations", "prevu": "30000"}), 302)
ok(c.post(f"{base}/budget/0?saison={S}", data={"nature": "Dépense", "categorie": "Récompenses (coupes, médailles, prix)", "libelle": "Récompenses", "prevu": "15000"}), 302)
ok(c.post(f"{base}/materiel/0?saison={S}", data={"designation": "Ballon de football", "discipline": "Football", "quantite": "6", "etat": "Bon", "valeur": "30000"}), 302)
with app.app_context():
    assert q("SELECT COUNT(*) n FROM uascep_activites WHERE bureau_id=?", (bid,), un=True)["n"] == 3
    rid = q("SELECT id FROM uascep_reunions WHERE bureau_id=?", (bid,), un=True)["id"]
    mat = q("SELECT id FROM uascep_materiel WHERE bureau_id=?", (bid,), un=True)["id"]
t = txt(ok(c.get(f"{base}?saison={S}&rub=caisse")))
assert "solde 7 500 FCFA" in t and "EPP Itassoumba 10 000 FCFA" in t
t = txt(ok(c.get(f"{base}?saison={S}&rub=budget")))
assert "30 000 FCFA" in t and "67 %" in t
t = txt(ok(c.get(f"{base}?saison={S}&rub=activites")))
assert "Tournoi de football inter-écoles" in t and "<b>134</b>" in t
# modifier / supprimer / réinitialiser
ok(c.post(f"{base}/materiel/{mat}?saison={S}", data={"designation": "Ballon de football", "quantite": "8", "etat": "Usagé", "valeur": "30000"}), 302)
t = txt(ok(c.get(f"{base}?saison={S}&rub=materiel&modifier={mat}")))
assert "Modifier" in t and "Usagé" in t
ok(c.post(f"{base}/materiel/{mat}/supprimer?saison={S}"), 302)
ok(c.post(f"{base}/materiel/0?saison={S}", data={"designation": "Filet de volley", "quantite": "2", "etat": "Neuf"}), 302)
ok(c.post(f"{base}/engagements/reinitialiser?saison={S}"), 302)
with app.app_context():
    assert q("SELECT COUNT(*) n FROM uascep_engagements WHERE bureau_id=?", (bid,), un=True)["n"] == 0
    assert q("SELECT quantite FROM uascep_materiel WHERE bureau_id=?", (bid,), un=True)["quantite"] == 2
ok(c.post(f"{base}/engagements/0?saison={S}", data={"ecole": "EPP Towé", "discipline": "Football", "equipe": "Les Aiglons", "droit": "5000"}), 302)
# cachets et signatures du rapporteur et du commissaire aux comptes
ok(c.post(f"/uascep/membre/{ids['Rapporteur']}/cachet", data={"cachet_mode": "genere", "cachet_forme": "rond", "signature_dessin": DATA}), 302)
# rapport : pré-rempli, modifiable, réinitialisable
t = txt(ok(c.get(f"/uascep/bureau/{bid}/rapport?saison={S}")))
assert "Rapport de fin de saison sportive " + S in t and "textes proposés d'après" in t and "134" in t and "7 500 FCFA" in t
ok(c.post(f"/uascep/bureau/{bid}/rapport?saison={S}", data={"titre": "Rapport de fin de saison sportive " + S, "contexte": "Saison marquée par la reprise des compétitions.",
          "organisation": "Le bureau s'est réuni régulièrement.", "resultats": "EPP Towé championne de football.", "difficultes": "Manque de ballons.",
          "recommandations": "Doter chaque école d'un kit sportif.", "conclusion": "Bonne saison."}), 302)
t = txt(ok(c.get(f"/uascep/bureau/{bid}/rapport?saison={S}")))
assert "Manque de ballons." in t and "textes proposés d'après" not in t
s, npg, nimg = texte_pdf(ok(c.get(f"/uascep/bureau/{bid}/rapport.pdf?saison={S}")))
for x in ("RAPPORT DE FIN DE SAISON SPORTIVE", "Contexte", "Organisation", "Activités réalisées", "Participation", "Résultats et distinctions",
          "Bilan financier", "Journal de caisse", "Cotisations par école", "Difficultés", "Recommandations", "Conclusion", "Tournoi de football",
          "Stade de Pobè", "Manque de ballons.", "Rapporteur", "Secrétaire général", "Trésorier", "Président", "Visa", "Document vérifiable", "7 500 FCFA"):
    assert x in s, x
assert npg >= 2 and nimg >= 2
codes.append(re.search(r"code ([0-9A-F]{10})", s).group(1))
for doc, attendu in (("journal", "CALENDRIER, RÉSULTATS ET JOURNAL"), ("engagements", "FICHES D'ENGAGEMENT"), ("finances", "ÉTAT FINANCIER ET JOURNAL DE CAISSE"),
                     ("inventaire", "INVENTAIRE DU MATÉRIEL")):
    s, npg, nimg = texte_pdf(ok(c.get(f"{base}/{doc}.pdf?saison={S}")))
    assert attendu in s and "Document vérifiable" in s, (doc, s[:300])
    codes.append(re.search(r"code ([0-9A-F]{10})", s).group(1))
s, _, _ = texte_pdf(ok(c.get(f"{base}/finances.pdf?saison={S}")))
assert "commissaire aux comptes" in s and "Trésorier" in s and "Budget prévisionnel" in s and "Cotisation" in s
s, _, _ = texte_pdf(ok(c.get(f"/uascep/bureau/{bid}/reunion/{rid}.pdf")))
assert "COMPTE RENDU DE RÉUNION" in s and "Programme de la saison" in s and "Tournoi fixé au 12 mars" in s and "Rapporteur" in s
codes.append(re.search(r"code ([0-9A-F]{10})", s).group(1))
r = ok(c.get(f"/uascep/bureau/{bid}/saison.xlsx?saison={S}"))
import openpyxl
wb = openpyxl.load_workbook(io.BytesIO(r.data))
assert {"Activités", "Engagements", "Réunions", "Caisse", "Budget", "Matériel", "État financier", "Rapport"} <= set(wb.sheetnames), wb.sheetnames
ok(c.get(f"/uascep/bureau/{bid}/saison.xlsx?saison={S}&rapport=1"))
for code in codes:
    assert "UASCEP" in txt(ok(c.get(f"/verifier/{code}"))), code
ok(c.post(f"/uascep/bureau/{bid}/rapport?saison={S}", data={"reinitialiser": "1"}), 302)
assert "textes proposés d'après" in txt(ok(c.get(f"/uascep/bureau/{bid}/rapport?saison={S}")))
ok(c.get(f"{base}/inconnu.pdf?saison={S}"), 404)
# réinitialiser le cachet et la signature
ok(c.post(f"/uascep/membre/{pres}/cachet/reinitialiser"), 302)
with app.app_context():
    m = q("SELECT * FROM uascep_membres WHERE id=?", (pres,), un=True)
    assert m["signature"] is None and m["cachet_couleur"] == "bleu" and m["cachet_forme"] == "rond"
# le renouvellement garde cachet et signature des membres reconduits
ok(c.post(f"/uascep/membre/{sg}/cachet", data={"cachet_mode": "genere", "cachet_forme": "rect", "signature_dessin": DATA}), 302)
ok(c.post(f"/uascep/bureau/{bid}/renouveler", data={"date_election": "2028-10-20"}), 302)
with app.app_context():
    nb = q("SELECT * FROM uascep_bureaux WHERE niveau=? AND entite=? AND statut='actif'", (niveau, entite), un=True)
    m2 = q("SELECT * FROM uascep_membres WHERE bureau_id=? AND nom='BIO'", (nb["id"],), un=True)
    assert m2["signature"] == DATA and m2["cachet_forme"] == "rect"
# l'enseignant : lecture seule (pas d'enregistrement de cachet)
with app.app_context():
    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) VALUES ('ens9','HOUNSOU Awa','enseignant',?,0,1,1)",
       (generate_password_hash("ens-mdp-123"),))
e = app.test_client()
ok(e.post("/login", data={"identifiant": "ens9", "mdp": "ens-mdp-123"}), 302)
if not JUR:
    t = txt(ok(e.get(f"/uascep/membre/{m2['id']}/cachet")))
    assert "Enregistrer" not in t
    ok(e.post(f"/uascep/membre/{m2['id']}/cachet", data={"cachet_mode": "aucun"}), 403)
    ok(e.post(f"/uascep/membre/{m2['id']}/cachet/reinitialiser"), 403)
    texte_pdf(ok(e.get(f"/uascep/membre/{m2['id']}/attestation.pdf")))
print("OK-" + config.EDITION)
'''


def lancer(edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestCachetsSignaturesUascep(unittest.TestCase):
    def verifier(self, ed):
        r = lancer(ed)
        self.assertIn("OK-" + ed, r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        self.verifier("privee")

    def test_publique(self):
        self.verifier("publique")

    def test_cs(self):
        self.verifier("cs")


class TestFichiers(unittest.TestCase):
    def test_gabarits(self):
        with open(os.path.join(RACINE, "templates", "uascep_cachet.html"), encoding="utf-8") as f:
            t = f.read()
        self.assertIn("Signez dans le cadre", t)
        self.assertIn("cachet_fichier", t)
        with open(os.path.join(RACINE, "m_uascep.py"), encoding="utf-8") as f:
            t = f.read()
        for x in ("uascep_composition_pdf", "uascep_pv_pdf", "uascep_attestation_pdf", "uascep_liste_pdf", "bloc_signatures"):
            self.assertIn(x, t)


if __name__ == "__main__":
    unittest.main()
