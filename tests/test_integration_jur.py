# -*- coding: utf-8 -*-
"""Tests de l'ouverture des modules des écoles dans GESCOL Circonscription / DDEMP (a_integration, v1.6).
Lancer : python3 -m unittest tests.test_integration_jur   (depuis /home/claude/gescol)

La base est construite par demo_juridiction.py (sous-processus) dans un dossier temporaire ; l'édition testée
est GESCOL_EDITION_TEST (cs par défaut). TestEditionDDEMP relance un sous-ensemble en édition « ddemp » et
TestEditionPrivee vérifie que le menu de l'édition privée est inchangé."""
import html as html_mod
import io
import os
import subprocess
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
EDITION = os.environ.get("GESCOL_EDITION_TEST", "cs")
DOSSIER = tempfile.mkdtemp(prefix=f"gescol_integ_{EDITION}_")
os.environ["GESCOL_EDITION"] = EDITION
os.environ["GESCOL_DATA"] = DOSSIER
if EDITION in ("cs", "ddemp"):
    subprocess.run([sys.executable, os.path.join(RACINE, "demo_juridiction.py")], check=True, cwd=RACINE,
                   env=dict(os.environ, GESCOL_EDITION=EDITION, GESCOL_DATA=DOSSIER), stdout=subprocess.DEVNULL)

from app import app, q, ex  # noqa: E402
import config  # noqa: E402

# Avec « unittest discover », plusieurs modules de test partagent un processus : l'édition chargée par le premier
# l'emporte. Si ce n'est pas la nôtre, la suite est rejouée dans un sous-processus (TestAutresEditions.test_cs).
EN_PLACE = config.EDITION == EDITION and config.INSTANCE_DIR == DOSSIER


def _rejouer(edition, cible="tests.test_integration_jur"):
    env = dict(os.environ, GESCOL_EDITION_TEST=edition)
    env.pop("GESCOL_EDITION", None)
    env.pop("GESCOL_DATA", None)
    return subprocess.run([sys.executable, "-m", "unittest", cible], cwd=RACINE, env=env, capture_output=True, text=True,
                          timeout=900)

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None


def txt(r):
    return html_mod.unescape(r.data.decode())


def client(ident, mdp="demo1234"):
    c = app.test_client()
    r = c.post("/login", data={"identifiant": ident, "mdp": mdp})
    assert r.status_code == 302, (ident, r.status_code)
    return c


def canevas(mats, ecoles, n=6, debut=0):
    """Classeur au format du canevas de l'examen blanc (m_cep) : une ligne par candidat."""
    wb = openpyxl.Workbook()
    w = wb.active
    w.append(["N° table", "Nom", "Prénoms", "Sexe (M/F)", "École de provenance"] + mats)
    for e in ecoles:
        for i in range(n):
            w.append([f"{i + 1:03d}", f"CAND{debut + i}", f"Prenom{i}", "M" if i % 2 else "F", e["nom"]]
                     + [(5 + 3 * i + j) % 21 for j in range(len(mats))])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@unittest.skipUnless(EDITION == "cs", "édition CS")
class TestIntegrationCS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EN_PLACE:
            raise unittest.SkipTest(f"édition « {config.EDITION} » déjà chargée : suite rejouée en sous-processus")
        app.config["TESTING"] = True
        cls.c = client("responsable")
        with app.app_context():
            # écoles primaires au nom unique (l'import d'un canevas reconnaît l'école par son nom)
            cls.jur = [dict(r) for r in q("SELECT * FROM jur_ecoles WHERE type='EP' AND actif=1 AND nom IN "
                                          "(SELECT nom FROM jur_ecoles GROUP BY nom HAVING COUNT(*)=1) ORDER BY id LIMIT 3")]

    # ------------------------------------------------------------ 1. ouverture d'une école et modules
    def test_01_ouvrir_ecole_et_modules(self):
        r = self.c.get("/juridiction/ecoles-modules")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Ouvrir cette école", txt(r))
        jid = self.jur[0]["id"]
        r = self.c.post(f"/juridiction/ecoles-modules/{jid}/ouvrir")
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            e = q("SELECT * FROM ecoles WHERE jur_ecole_id=?", (jid,), un=True)
            self.assertIsNotNone(e)
            self.assertEqual(e["nom"], self.jur[0]["nom"])
            self.assertEqual(e["statut"], "Publique" if self.jur[0]["secteur"] == "public" else "Privée")
            self.assertEqual(e["cs"], "POBE")
        for url in ("/juridiction/ecole", "/eleves", "/classes", "/evaluations", "/cep", "/cantine", "/recensement",
                    "/patrimoine", "/secretariat/courrier", "/secretariat/archives", "/donnees", "/educmaster",
                    "/conversion-pdf", "/ecoles", "/parametres", "/utilisateurs", "/synthese", "/cep-blanc", "/visites",
                    "/maitre-semaine", "/docs-enseignant", "/rapports", "/personnel", "/carriere", "/depenses",
                    "/recettes", "/tresorerie", "/directeur", "/notes", "/tableau-honneur", "/bilan-annuel", "/appel",
                    "/registre", "/affichage", "/matieres", "/journal", "/demandes-ecoles", "/administration/en-ligne",
                    "/communication/reglages", "/paiements/en-ligne/reglages", "/cantine/stock", "/cantine/config",
                    "/juridiction/cep-blanc", "/juridiction/cep-blanc/synthese", "/juridiction/synthese-evaluation"):
            r = self.c.get(url)
            self.assertEqual(r.status_code, 200, f"{url} -> {r.status_code}")
        html = txt(self.c.get("/eleves"))
        # menu des modules d'école + école ouverte dans la barre du haut
        for mot in ("École ouverte", self.jur[0]["nom"], "/juridiction/cep-blanc", "/juridiction/synthese-evaluation",
                    "/recensement", "/secretariat/courrier", "/donnees", "Écoles (ajout, modification, suppression)",
                    "Écoles, CS et DDEMP candidates", "WhatsApp et SMS"):
            self.assertIn(mot, html)
        # sélecteur d'école visible en juridiction ; rôle réel affiché
        self.assertIn('id="choix-ecole"', html)
        self.assertIn("Responsable (CCS / Directeur départemental)", html)
        # page de juridiction : identité de la structure, pas celle de l'école
        html_j = txt(self.c.get("/juridiction/tableau-de-bord"))
        self.assertIn("Circonscription scolaire de Pobe", html_j)

    def test_02_roles(self):
        self.c.post(f"/juridiction/ecoles-modules/{self.jur[0]['id']}/ouvrir")
        r = self.c.post("/classes/nouvelle", data={"nom": "CM2 TEST", "niveau": "CM2", "frais_scolarite": "0"})
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            cid = q("SELECT id FROM classes WHERE nom='CM2 TEST'", un=True)["id"]
        # chef de service : écrit un élève (droits du directeur), pas les paramètres
        chef = client("chef")
        r = chef.post("/eleves/nouveau", data={"nom": "DOSSOU", "prenoms": "Ayi", "sexe": "F", "classe_id": str(cid), "statut": "inscrit"})
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            self.assertTrue(q("SELECT 1 FROM eleves WHERE nom='DOSSOU' AND classe_id=?", (cid,), un=True))
        self.assertEqual(chef.get("/parametres").status_code, 403)
        self.assertEqual(chef.get("/directeur").status_code, 200)   # contrôle direct de rôle (m_carriere) : rôle substitué
        # agent : droits du secrétaire
        agent = client("agent")
        self.assertEqual(agent.get("/parametres").status_code, 403)
        self.assertEqual(agent.get("/eleves").status_code, 200)
        self.assertEqual(agent.post("/eleves/nouveau", data={"nom": "AGENT", "prenoms": "X", "sexe": "M", "classe_id": str(cid),
                                                              "statut": "inscrit"}).status_code, 302)
        self.assertEqual(agent.get("/juridiction/cep-blanc/synthese").status_code, 200)
        # conseiller pédagogique : pédagogie oui, finances non ; pas les droits jur_* d'un chef
        cp = client("cp1")
        self.assertEqual(cp.get("/evaluations").status_code, 200)
        self.assertEqual(cp.get("/paiements").status_code, 403)
        self.assertEqual(cp.get("/cantine").status_code, 403)
        self.assertEqual(cp.post("/juridiction/cep-blanc/nouvelle", data={"matieres": "Français"}).status_code, 403)
        # comptes directeur / enseignant proposés dans la juridiction
        html = txt(self.c.get("/utilisateurs"))
        self.assertIn('value="directeur"', html)
        self.assertIn('value="enseignant"', html)
        r = self.c.post("/utilisateurs", data={"action": "creer", "identifiant": "dir1", "nom": "Directeur 1", "role": "directeur",
                                               "mdp": "motdepasse1"})
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            eid = q("SELECT id FROM ecoles WHERE jur_ecole_id=?", (self.jur[0]["id"],), un=True)["id"]
            ex("UPDATE utilisateurs SET doit_changer_mdp=0, ecole_id=? WHERE identifiant='dir1'", (eid,))
        d = client("dir1", "motdepasse1")
        r = d.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/juridiction/ecole"))
        self.assertEqual(d.get("/eleves").status_code, 200)
        self.assertEqual(d.get("/juridiction/structure").status_code, 403)

    # ------------------------------------------------------------ 2. écoles : création → jur_ecoles, suppression
    def test_03_creer_supprimer_ecole(self):
        r = self.c.post("/ecoles/nouvelle", data={"nom": "EPP TEST INTEGRATION", "statut": "Publique", "ordre": "Primaire",
                                                  "zone": "Zone pédagogique 2", "cachet_couleur": "bleu"})
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            e = q("SELECT * FROM ecoles WHERE nom='EPP TEST INTEGRATION'", un=True)
            self.assertIsNotNone(e["jur_ecole_id"])
            je = q("SELECT * FROM jur_ecoles WHERE id=?", (e["jur_ecole_id"],), un=True)
            self.assertEqual(je["nom"], "EPP TEST INTEGRATION")
            self.assertEqual(je["secteur"], "public")
            self.assertTrue(je["code"].startswith("POBE-"))
            self.assertEqual(q("SELECT nom FROM jur_zones WHERE id=?", (je["zone_id"],), un=True)["nom"], "Zone pédagogique 2")
            nid = e["id"]
        self.assertIn("Supprimer", txt(self.c.get("/ecoles")))
        r = self.c.post(f"/ecoles/{nid}/supprimer", follow_redirects=True)
        self.assertIn("supprimée", txt(r))
        with app.app_context():
            self.assertIsNone(q("SELECT 1 FROM ecoles WHERE id=?", (nid,), un=True))
            self.assertEqual(q("SELECT actif FROM jur_ecoles WHERE id=?", (e["jur_ecole_id"],), un=True)["actif"], 0)
        # école avec classes : refus (désactivation proposée)
        self.c.post(f"/juridiction/ecoles-modules/{self.jur[0]['id']}/ouvrir")
        self.c.post("/classes/nouvelle", data={"nom": "CI TEST", "niveau": "CI", "frais_scolarite": "0"})
        with app.app_context():
            eid = q("SELECT id FROM ecoles WHERE jur_ecole_id=?", (self.jur[0]["id"],), un=True)["id"]
        r = self.c.post(f"/ecoles/{eid}/supprimer", follow_redirects=True)
        self.assertIn("ne peut pas être supprimée", txt(r))
        with app.app_context():
            self.assertTrue(q("SELECT 1 FROM ecoles WHERE id=?", (eid,), un=True))
        # agent : pas le droit
        self.assertEqual(client("agent").post(f"/ecoles/{eid}/supprimer").status_code, 403)

    # ------------------------------------------------------------ 3. examen blanc CS
    @unittest.skipUnless(openpyxl, "openpyxl requis")
    def test_04_examen_blanc(self):
        mats = ["Français", "Mathématiques", "ES", "EST"]
        r = self.c.post("/juridiction/cep-blanc/nouvelle", data={"numero": "7", "annee": "2026-2027", "niveau": "CM2",
                                                                 "nom": "Examen blanc test", "matieres": "\n".join(mats), "seuil": ""})
        self.assertEqual(r.status_code, 302)
        sid = int(r.headers["Location"].rsplit("/", 1)[1])
        html = txt(self.c.get("/juridiction/cep-blanc"))
        self.assertIn("Examen blanc test", html)
        # canevas : même format que m_cep (N° table, Nom, Prénoms, Sexe (M/F), École de provenance, matières)
        r = self.c.get(f"/juridiction/cep-blanc/{sid}/canevas.xlsx")
        self.assertEqual(r.status_code, 200)
        ws = openpyxl.load_workbook(io.BytesIO(r.data)).active
        lignes = [list(x) for x in ws.iter_rows(values_only=True)]
        self.assertEqual(lignes[3], ["N° table", "Nom", "Prénoms", "Sexe (M/F)", "École de provenance"] + mats)
        # import d'un canevas à deux écoles (école d'après la colonne), puis d'un canevas affecté à une école
        r = self.c.post(f"/juridiction/cep-blanc/{sid}/importer", data={"fichier": (canevas(mats, self.jur[:2]), "canevas.xlsx")},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("Import terminé : 12 candidat(s) ajouté(s)", txt(r))
        r = self.c.post(f"/juridiction/cep-blanc/{sid}/importer",
                        data={"fichier": (canevas(mats, [{"nom": "école inconnue"}], 4, 100), "canevas.xlsx"), "ecole": str(self.jur[2]["id"])},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("4 candidat(s) ajouté(s)", txt(r))
        # réimport : mise à jour sans doublon
        r = self.c.post(f"/juridiction/cep-blanc/{sid}/importer", data={"fichier": (canevas(mats, self.jur[:1]), "canevas.xlsx")},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("0 candidat(s) ajouté(s), 6 mis à jour", txt(r))
        with app.app_context():
            self.assertEqual(q("SELECT COUNT(*) n FROM jur_cep_blanc_resultats WHERE session_id=?", (sid,), un=True)["n"], 16)
            self.assertEqual(q("SELECT COUNT(DISTINCT ecole_id) n FROM jur_cep_blanc_resultats WHERE session_id=?", (sid,), un=True)["n"], 3)
            self.assertTrue(q("SELECT 1 FROM jur_cep_blanc_resultats WHERE session_id=? AND admis IS NOT NULL", (sid,), un=True))
        # résultats par école / zone, classement, candidats
        html = txt(self.c.get(f"/juridiction/cep-blanc/{sid}"))
        for mot in ("Sous-total Zone pédagogique", "TOTAL GÉNÉRAL", "Classement des écoles", self.jur[0]["nom"], self.jur[2]["nom"]):
            self.assertIn(mot, html)
        html = txt(self.c.get(f"/juridiction/cep-blanc/{sid}?vue=candidats&tri=merite"))
        self.assertIn("CAND0", html)
        self.assertIn("MAÎTRISE", html)
        # saisie manuelle par école (ajout, modification, suppression)
        jid = self.jur[0]["id"]
        r = self.c.post(f"/juridiction/cep-blanc/{sid}/ecole/{jid}/sauvegarder",
                        data={"cid": ["", ""], "table": ["A1", "A2"], "nom": ["Saisi", "Saisie"], "prenoms": ["Un", "Deux"],
                              "sexe": ["M", "F"], "n0": ["12", "3"], "n1": ["15", "4"], "n2": ["10", "2"], "n3": ["9", "25"]},
                        follow_redirects=True)
        self.assertIn("2 ajouté(s)", txt(r))
        self.assertIn("note(s) invalide(s)", txt(r))
        with app.app_context():
            c1 = q("SELECT * FROM jur_cep_blanc_resultats WHERE session_id=? AND nom='SAISI'", (sid,), un=True)
            self.assertEqual(c1["admis"], 1)      # 3 matières sur 4 à 10/20 ≥ seuil 2/3 (3)
            c2 = q("SELECT * FROM jur_cep_blanc_resultats WHERE session_id=? AND nom='SAISIE'", (sid,), un=True)
            self.assertEqual(c2["admis"], 0)
        html = txt(self.c.get(f"/juridiction/cep-blanc/{sid}?vue=saisie&ecole={jid}"))
        self.assertIn("SAISI", html)
        r = self.c.post(f"/juridiction/cep-blanc/{sid}/ecole/{jid}/sauvegarder",
                        data={"cid": [str(c1["id"]), str(c2["id"])], "table": ["A1", "A2"], "nom": ["Saisi", "Saisie"],
                              "prenoms": ["Un", "Deux"], "sexe": ["M", "F"], "n0": ["2", "3"], "n1": ["2", "4"], "n2": ["2", "2"],
                              "n3": ["2", ""], "suppr": [str(c2["id"])]}, follow_redirects=True)
        self.assertIn("1 candidat(s) mis à jour, 0 ajouté(s), 1 supprimé(s)", txt(r))
        with app.app_context():
            self.assertEqual(q("SELECT admis FROM jur_cep_blanc_resultats WHERE id=?", (c1["id"],), un=True)["admis"], 0)
            self.assertIsNone(q("SELECT 1 FROM jur_cep_blanc_resultats WHERE id=?", (c2["id"],), un=True))
        # PDF et Excel (résultats, candidats, une école)
        for vue in ("resultats", "candidats", f"candidats&ecole={jid}"):
            r = self.c.get(f"/juridiction/cep-blanc/{sid}?vue={vue}&export=pdf")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.data.startswith(b"%PDF"))
            r = self.c.get(f"/juridiction/cep-blanc/{sid}?vue={vue}&export=xlsx")
            self.assertEqual(r.status_code, 200)
            wb = openpyxl.load_workbook(io.BytesIO(r.data))
            self.assertTrue(wb.active.max_row > 3)
        # en-tête : renommage d'une matière → les notes suivent
        r = self.c.post(f"/juridiction/cep-blanc/{sid}/entete", data={"numero": "7", "annee": "2026-2027", "niveau": "CM2",
                                                                      "nom": "Examen blanc test", "matieres": "Français\nMaths\nES\nEST", "seuil": "2"},
                        follow_redirects=True)
        self.assertIn("En-tête de l'examen blanc enregistré", txt(r))
        with app.app_context():
            n = q("SELECT notes FROM jur_cep_blanc_resultats WHERE id=?", (c1["id"],), un=True)["notes"]
            self.assertIn("Maths", n)
            self.assertNotIn("Mathématiques", n)
        # synthèse des examens par niveau (examen blanc + CEP officiel de la démo)
        html = txt(self.c.get("/juridiction/cep-blanc/synthese?annee=2026-2027"))
        for mot in ("Résultats par niveau", "CEP officiel", "Examen blanc test", "Zone pédagogique 1", "TOTAL"):
            self.assertIn(mot, html)
        for ext, debut in (("pdf", b"%PDF"), ("xlsx", b"PK")):
            r = self.c.get(f"/juridiction/cep-blanc/synthese?annee=2026-2027&export={ext}")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.data.startswith(debut))
        # suppression de la session
        r = self.c.post(f"/juridiction/cep-blanc/{sid}/supprimer", follow_redirects=True)
        self.assertIn("supprimé", txt(r))
        with app.app_context():
            self.assertIsNone(q("SELECT 1 FROM jur_cep_blanc_resultats WHERE session_id=?", (sid,), un=True))

    # ------------------------------------------------------------ 4. synthèse de l'évaluation CS
    @unittest.skipUnless(openpyxl, "openpyxl requis")
    def test_05_synthese_evaluation(self):
        # deux écoles ouvertes, chacune avec une classe, des élèves et une synthèse sauvegardée
        for k, je in enumerate(self.jur[:2]):
            self.c.post(f"/juridiction/ecoles-modules/{je['id']}/ouvrir")
            self.c.post("/classes/nouvelle", data={"nom": f"CE1 S{k}", "niveau": "CE1", "frais_scolarite": "0"})
            with app.app_context():
                cid = q("SELECT id FROM classes WHERE nom=?", (f"CE1 S{k}",), un=True)["id"]
            for i in range(3):
                self.c.post("/eleves/nouveau", data={"nom": f"SYN{k}{i}", "prenoms": "P", "sexe": "F" if i else "M",
                                                     "classe_id": str(cid), "statut": "inscrit"})
            r = self.c.post("/synthese?type=sommative&numero=1", data={"action": "sauver"}, follow_redirects=True)
            self.assertEqual(r.status_code, 200)
        html = txt(self.c.get("/juridiction/synthese-evaluation?type=sommative&numero=1"))
        for mot in ("niveau CS", self.jur[0]["nom"], self.jur[1]["nom"], "Résultats par école", "Synthèse générale par niveau",
                    "CE1", "Analyse des résultats", "Écarts de genre"):
            self.assertIn(mot, html)
        self.assertIn("2 école(s) ouverte(s)", html)
        for ext, debut in (("pdf", b"%PDF"), ("xlsx", b"PK")):
            r = self.c.get(f"/juridiction/synthese-evaluation?type=sommative&numero=1&export={ext}")
            self.assertEqual(r.status_code, 200, ext)
            self.assertTrue(r.data.startswith(debut))
        if openpyxl:
            wb = openpyxl.load_workbook(io.BytesIO(r.data))
            self.assertEqual(wb.sheetnames, ["Synthèse par niveau", "Par zone", "Par école", "Analyse"])
        # évaluation sans synthèse : page vide mais valide
        html = txt(self.c.get("/juridiction/synthese-evaluation?type=formative&numero=9"))
        self.assertIn("Aucune synthèse enregistrée", html)


@unittest.skipUnless(EDITION == "ddemp", "édition DDEMP")
class TestIntegrationDDEMP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EN_PLACE:
            raise unittest.SkipTest(f"édition « {config.EDITION} » déjà chargée")
        app.config["TESTING"] = True
        cls.c = client("responsable")
        with app.app_context():
            cls.jur = [dict(r) for r in q("SELECT e.*, c.nom cs_nom FROM jur_ecoles e JOIN jur_cs c ON c.id=e.cs_id "
                                          "WHERE e.type='EP' AND e.actif=1 ORDER BY e.cs_id, e.id")]

    @unittest.skipUnless(openpyxl, "openpyxl requis")
    def test_01_ddemp(self):
        # deux écoles de CS différentes
        e1 = self.jur[0]
        e2 = next(e for e in self.jur if e["cs_id"] != e1["cs_id"])
        r = self.c.post(f"/juridiction/ecoles-modules/{e1['id']}/ouvrir")
        self.assertEqual(r.status_code, 302)
        for url in ("/juridiction/ecole", "/eleves", "/recensement", "/cep", "/ecoles", "/parametres", "/juridiction/cep-blanc",
                    "/juridiction/synthese-evaluation"):
            self.assertEqual(self.c.get(url).status_code, 200, url)
        html = txt(self.c.get("/eleves"))
        self.assertIn("Examen blanc DDEMP", html)
        self.assertIn("Vie de la DDEMP", html)
        with app.app_context():
            e = q("SELECT * FROM ecoles WHERE jur_ecole_id=?", (e1["id"],), un=True)
            self.assertEqual(e["cs"], e1["cs_nom"])
        # examen blanc DDEMP : totaux par CS
        mats = ["Français", "Mathématiques", "ES"]
        r = self.c.post("/juridiction/cep-blanc/nouvelle", data={"matieres": "\n".join(mats)})
        sid = int(r.headers["Location"].rsplit("/", 1)[1])
        for e in (e1, e2):   # un canevas par école (les noms d'écoles ne sont pas uniques dans le département)
            r = self.c.post(f"/juridiction/cep-blanc/{sid}/importer", data={"fichier": (canevas(mats, [e], 5), "c.xlsx"), "ecole": str(e["id"])},
                            content_type="multipart/form-data", follow_redirects=True)
            self.assertIn("5 candidat(s) ajouté(s)", txt(r))
        # d'après la colonne « École de provenance » : code de l'école accepté
        r = self.c.post(f"/juridiction/cep-blanc/{sid}/importer", data={"fichier": (canevas(mats, [{"nom": e1["code"]}], 2, 50), "c.xlsx")},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("2 candidat(s) ajouté(s)", txt(r))
        html = txt(self.c.get(f"/juridiction/cep-blanc/{sid}"))
        self.assertIn(f"Total CS {e1['cs_nom']}", html)
        self.assertIn(f"Total CS {e2['cs_nom']}", html)
        for ext in ("pdf", "xlsx"):
            self.assertEqual(self.c.get(f"/juridiction/cep-blanc/{sid}?export={ext}").status_code, 200)
            self.assertEqual(self.c.get(f"/juridiction/cep-blanc/synthese?export={ext}").status_code, 200)
        html = txt(self.c.get("/juridiction/cep-blanc/synthese"))
        self.assertIn(f"CS {e1['cs_nom']}", html)
        # création d'une école locale dans une CS du département → jur_ecoles de cette CS
        r = self.c.post("/ecoles/nouvelle", data={"nom": "EPP DDEMP TEST", "statut": "Privée", "cs": e2["cs_nom"],
                                                  "zone": "Zone pédagogique 1", "cachet_couleur": "bleu"})
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            e = q("SELECT * FROM ecoles WHERE nom='EPP DDEMP TEST'", un=True)
            je = q("SELECT * FROM jur_ecoles WHERE id=?", (e["jur_ecole_id"],), un=True)
            self.assertEqual(je["cs_id"], e2["cs_id"])
            self.assertEqual(je["secteur"], "prive")


class TestAutresEditions(unittest.TestCase):
    """Relance ce fichier en édition DDEMP (sous-processus) et vérifie l'édition privée (menus inchangés)."""

    def test_cs(self):
        if EN_PLACE and EDITION == "cs" or EDITION == "ddemp":
            self.skipTest("édition cs déjà testée dans ce processus, ou processus secondaire")
        r = _rejouer("cs", "tests.test_integration_jur.TestIntegrationCS")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])

    @unittest.skipUnless(EDITION == "cs", "lancé une seule fois")
    def test_ddemp(self):
        r = _rejouer("ddemp", "tests.test_integration_jur.TestIntegrationDDEMP")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])

    @unittest.skipUnless(EDITION == "cs", "lancé une seule fois")
    def test_privee_menus_inchanges(self):
        code = r'''
import os, sys, tempfile, html
os.environ["GESCOL_EDITION"] = "privee"; os.environ["GESCOL_DATA"] = tempfile.mkdtemp(prefix="gescol_priv_")
from app import app, ex, q
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
c = app.test_client(); c.post("/login", data={"identifiant": "admin", "mdp": "admin123"})
h = html.unescape(c.get("/").data.decode())
assert c.get("/").status_code == 200
for mot in ("Tableau du fondateur", "Paiements de scolarité", "Transmission à la circonscription", "Écoles (ajout, modification, suppression)",
            "Paramètres de paie", "Écoles, CS et DDEMP candidates"):
    assert mot in h, mot
for mot in ("École ouverte", "juridiction", "Examen blanc CS", "choix-ecole", "Vie de l'école"):
    assert mot not in h, mot
assert "Administrateur" in h
# école principale : pas de suppression ; rôle de juridiction non proposé
assert "Fondateur / promoteur" in html.unescape(c.get("/utilisateurs").data.decode())
assert 'value="responsable"' not in html.unescape(c.get("/utilisateurs").data.decode())
r = c.post("/ecoles/1/supprimer", follow_redirects=True)
assert "ne peut pas être supprimée" in html.unescape(r.data.decode())
print("ok")
'''
        env = dict(os.environ)
        env.pop("GESCOL_EDITION", None)
        env.pop("GESCOL_DATA", None)
        r = subprocess.run([sys.executable, "-c", code], cwd=RACINE, env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        self.assertIn("ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
