# -*- coding: utf-8 -*-
"""Tests v1.6 du tableau synoptique de la structure (a_synoptique) : CS puis DDEMP.
Lancer : python3 -m unittest tests.test_jur_synoptique   (depuis /home/claude/gescol)

L'édition testée est choisie par GESCOL_EDITION_TEST (cs par défaut) ; la suite est rejouée dans un second processus
pour l'édition « ddemp » (TestEditionsSeparees), comme tests/test_jur_v16.py. Données : demo_juridiction.main() dans
un dossier temporaire ; connexion « responsable » / demo1234."""
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
DOSSIER = tempfile.mkdtemp(prefix=f"gescol_syno_{EDITION}_")
os.environ["GESCOL_EDITION"] = EDITION
os.environ["GESCOL_DATA"] = DOSSIER

from app import app  # noqa: E402
import config  # noqa: E402
import a_synoptique as AS  # noqa: E402
import demo_juridiction  # noqa: E402

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None


def txt(r):
    return html_mod.unescape(r.data.decode())


def xlsx_feuilles(data):
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


EN_PLACE = config.EDITION == EDITION


def _rejouer(edition):
    env = dict(os.environ, GESCOL_EDITION_TEST=edition)
    env.pop("GESCOL_EDITION", None)
    env.pop("GESCOL_DATA", None)
    return subprocess.run([sys.executable, "-m", "unittest", "tests.test_jur_synoptique.TestJurSynoptique"], cwd=RACINE, env=env,
                          capture_output=True, text=True, timeout=900)


class TestJurSynoptique(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EN_PLACE:
            raise unittest.SkipTest(f"édition « {config.EDITION} » déjà chargée : suite rejouée en sous-processus")
        app.config["TESTING"] = True
        demo_juridiction.main()
        cls.c = app.test_client()
        r = cls.c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"})
        assert r.status_code == 302, r.status_code
        cls.ddemp = EDITION == "ddemp"

    def get(self, url, code=200):
        r = self.c.get(url)
        self.assertEqual(r.status_code, code, f"{url} → {r.status_code}\n{r.data[:400]}")
        return r

    def post(self, url, data=None, code=302):
        r = self.c.post(url, data=data or {})
        self.assertEqual(r.status_code, code, f"POST {url} → {r.status_code}\n{txt(r)[-1500:] if r.status_code != 302 else ''}")
        return r

    def q(self, sql, args=(), un=True):
        with app.app_context():
            from app import q
            return q(sql, args, un=un)

    def identite(self):
        with app.app_context():
            return AS._H.jur_synoptique_identite()

    def personnel(self):
        with app.app_context():
            return AS._H.jur_synoptique_personnel()

    # ------------------------------------------------------------ 1. pages et menu
    def test_01_pages(self):
        t = txt(self.get("/juridiction/synoptique"))
        self.assertIn("Tableau synoptique de la " + ("DDEMP" if self.ddemp else "circonscription scolaire"), t)
        self.assertIn("Nombre de zones pédagogiques", t)
        self.assertIn("Tableau synoptique de la " + ("DDEMP" if self.ddemp else "CS"), t)      # lien du menu
        for u in ("/juridiction/synoptique/personnel", "/juridiction/synoptique/personnel?tous=1", "/juridiction/synoptique/reseau",
                  "/juridiction/synoptique/services", "/juridiction/synoptique/comites", "/juridiction/synoptique/comites/cantine",
                  "/juridiction/synoptique/comites/cep", "/juridiction/synoptique/comites/autre", "/juridiction/synoptique/import",
                  "/juridiction/synoptique/agent/0", "/juridiction/synoptique/comites/conseil/membre/0"):
            self.get(u)
        self.get("/juridiction/synoptique/comites/inconnu", 404)
        self.get("/juridiction/synoptique/agent/999999", 404)
        # données de démonstration
        t = txt(self.get("/juridiction/synoptique/comites/conseil"))
        self.assertIn("KOUTON Basile", t)
        t = txt(self.get("/juridiction/synoptique/reseau"))
        self.assertIn("Zone pédagogique 1", t)
        self.assertIn("RUP", t)
        if self.ddemp:
            self.assertIn("Circonscriptions scolaires du département", t)
        t = txt(self.get("/juridiction/synoptique/services"))
        self.assertIn("Article AOF", t)

    # ------------------------------------------------------------ 2. identité
    def test_02_identite(self):
        d = self.identite()
        self.assertEqual(d["departement"], "Plateau")
        self.assertGreater(d["nb_ecoles"], 0)
        self.assertEqual(d["nb_ecoles"], d["nb_ecoles_pub"] + d["nb_ecoles_priv"])
        self.assertEqual(d["nb_ecoles"], d["nb_ep"] + d["nb_em"] + d["nb_ee"])
        self.assertGreater(d["nb_zones"], 0)
        self.assertGreater(d["nb_up"], 0)
        if self.ddemp:
            self.assertEqual(d["nb_cs"], len(self.q("SELECT id FROM jur_cs WHERE actif=1", un=False)))
        else:
            self.assertEqual(d["cs_nom"], "POBE")
            self.assertEqual(d["annee_creation"], "1998")
        # POST : recopie dans jur_structure (et jur_cs)
        form = {k: (d.get(k) or "") for k in AS.TOUTES_CLES}
        form.update(resp_titre="La Cheffe de la Circonscription Scolaire" if not self.ddemp else "La Directrice Départementale",
                    resp_nom="ADJAHO Afiavi", resp_grade="A1-8", resp_nip="123456789012", resp_matricule="A1234", resp_prise_fonction="01/10/2022",
                    annee_creation="2001", telephone="0190000000", email="cs@test.bj", cs_numero="3", arrondissements="Pobè, Issaba")
        self.post("/juridiction/synoptique/identite", form)
        s = self.q("SELECT * FROM jur_structure WHERE id=1")
        self.assertEqual(s["responsable_nom"], "ADJAHO Afiavi")
        self.assertEqual(s["telephone"], "0190000000")
        self.assertEqual(s["email"], "cs@test.bj")
        d2 = self.identite()
        self.assertEqual(d2["resp_prise_fonction"], "2022-10-01")
        self.assertEqual(d2["annee_creation"], "2001")
        if not self.ddemp:
            c = self.q("SELECT * FROM jur_cs WHERE nom='POBE'")
            self.assertEqual(c["ccs_nom"], "ADJAHO Afiavi")
            self.assertEqual(c["arrondissements"], "Pobè, Issaba")
        t = txt(self.get("/juridiction/synoptique"))
        self.assertIn("ADJAHO Afiavi", t)
        self.assertIn("01/10/2022", t)
        # erreurs de saisie
        form["annee_creation"] = "20x1"
        r = self.c.post("/juridiction/synoptique/identite", data=form, follow_redirects=True)
        self.assertIn("Année de création invalide", txt(r))
        self.assertTrue(self.q("SELECT 1 FROM journal WHERE action='jur_synoptique'"))

    # ------------------------------------------------------------ 3. personnel : ajout, retraite, modification, retrait
    def test_03_agent(self):
        n0 = len(self.personnel())
        self.assertGreater(n0, 0)
        form = {"nom": "tossou", "prenoms": "Fiacre", "sexe": "M", "nip": "123456789011", "matricule": "T9999", "date_naissance": "15/02/1967",
                "poste": "Conseiller pédagogique (CP)", "role": "cp", "categorie": "FE", "grade": "A1-6", "indice_paye": "800", "indice_reel": "820",
                "promotion": "1990", "date_premiere_ps": "01/10/1990", "date_ps_departement": "01/10/2005", "date_ps_ecole": "01/10/2020",
                "date_derniere_formation": "12/03/2025", "diplome_academique": "Licence", "annee_diplome": "1989", "ceap": "oui", "annee_ceap": "1992",
                "cap": "oui", "annee_cap": "1996", "visite_aptitude": "oui", "note_aptitude": "15", "note_evaluation": "16.5", "telephone": "0197000001"}
        r = self.post("/juridiction/synoptique/agent/0", form)
        self.assertIn("agent-", r.headers["Location"])
        a = self.q("SELECT * FROM jur_agents WHERE matricule='T9999'")
        self.assertEqual(a["nom"], "TOSSOU")
        self.assertEqual(a["actif"], 1)
        import json
        dj = json.loads(a["donnees"])
        self.assertEqual(dj["promotion"], "1990")
        self.assertEqual(dj["date_derniere_formation"], "2025-03-12")
        self.assertEqual(dj["role"], "cp")
        lst = self.personnel()
        self.assertEqual(len(lst), n0 + 1)
        v = next(x for x in lst if x["matricule"] == "T9999")
        self.assertEqual(v["retraite_txt"], "01/04/2027")           # né 15/02/1967, grade A → 60 ans, 1er jour du trimestre suivant
        self.assertEqual(v["date_derniere_formation"], "12/03/2025")
        self.assertEqual(v["promotion"], "1990")
        self.assertIn("Licence (1989)", v["diplome_academique_txt"])
        self.assertIn("CEAP 1992", v["diplome_pro_txt"])
        import m_carriere as MC
        self.assertEqual(v["anc_generale"], MC.fmt_duree(MC.anciennete("1990-10-01", MC.date_reference()), True))
        self.assertTrue(v["anc_generale"].endswith(" a 3 m"), v["anc_generale"])
        self.assertEqual(v["visite_aptitude"], "oui")
        self.assertEqual(v["note_aptitude"], "15")
        self.assertEqual(v["fonction"], "Conseiller pédagogique (CP)")
        t = txt(self.get("/juridiction/synoptique/personnel"))
        self.assertIn("TOSSOU Fiacre", t)
        self.assertIn("01/04/2027", t)
        # l'agent apparaît aussi dans le module Personnel (même table)
        t = txt(self.get("/juridiction/agents"))
        self.assertIn("TOSSOU", t)
        # modification
        t = txt(self.get(f"/juridiction/synoptique/agent/{a['id']}"))
        self.assertIn("15/02/1967", t)
        self.assertIn("01/04/2027", t)
        form["grade"] = "B1-6"
        form["prenoms"] = "Fiacre Aimé"
        self.post(f"/juridiction/synoptique/agent/{a['id']}", form)
        v = next(x for x in self.personnel() if x["matricule"] == "T9999")
        self.assertEqual(v["retraite_txt"], "01/04/2025")           # grade B → 58 ans
        self.assertEqual(v["nom_complet"], "TOSSOU Fiacre Aimé")
        # erreurs : nom manquant, date invalide, matricule en double
        r = self.c.post("/juridiction/synoptique/agent/0", data={"nom": "", "prenoms": "X"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Le nom est obligatoire", txt(r))
        r = self.c.post("/juridiction/synoptique/agent/0", data={"nom": "Y", "matricule": "T9999", "date_naissance": "31/13/1970"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("déjà attribué", txt(r))
        self.assertIn("Date de naissance invalide", txt(r))
        # retrait puis réactivation
        self.post(f"/juridiction/synoptique/agent/{a['id']}/retirer")
        self.assertEqual(self.q("SELECT actif FROM jur_agents WHERE id=?", (a["id"],))["actif"], 0)
        self.assertEqual(len(self.personnel()), n0)
        t = txt(self.get("/juridiction/synoptique/personnel?tous=1"))
        self.assertIn("retiré", t)
        self.post(f"/juridiction/synoptique/agent/{a['id']}/reactiver")
        self.assertEqual(len(self.personnel()), n0 + 1)
        self.get("/juridiction/synoptique/agent/0/retirer", 405)

    # ------------------------------------------------------------ 4. comités
    def test_04_comites(self):
        self.post("/juridiction/synoptique/comites/conseil/membre/0",
                  {"nom_prenoms": "ZINSOU Grâce", "qualite": "Rapporteur", "origine": "CS", "contact": "0199", "ordre": "9"})
        m = self.q("SELECT * FROM jur_synoptique_membres WHERE nom_prenoms='ZINSOU Grâce'")
        self.assertEqual(m["comite"], "conseil")
        self.post(f"/juridiction/synoptique/comites/conseil/membre/{m['id']}",
                  {"nom_prenoms": "ZINSOU Grâce", "qualite": "Secrétaire", "origine": "CS", "contact": "", "ordre": "9"})
        self.assertEqual(self.q("SELECT qualite FROM jur_synoptique_membres WHERE id=?", (m["id"],))["qualite"], "Secrétaire")
        t = txt(self.get("/juridiction/synoptique/comites/conseil"))
        self.assertIn("ZINSOU Grâce", t)
        # comité « autre » : intitulé obligatoire
        r = self.c.post("/juridiction/synoptique/comites/autre/membre/0", data={"nom_prenoms": "LAWANI Bio"})
        self.assertEqual(r.status_code, 400)
        self.post("/juridiction/synoptique/comites/autre/membre/0", {"nom_prenoms": "LAWANI Bio", "libelle": "Comité de suivi des constructions"})
        t = txt(self.get("/juridiction/synoptique/comites/autre"))
        self.assertIn("Comité de suivi des constructions", t)
        self.get("/juridiction/synoptique/comites/cantine/membre/%d" % m["id"], 404)
        self.post(f"/juridiction/synoptique/comites/conseil/membre/{m['id']}/supprimer")
        self.assertIsNone(self.q("SELECT 1 FROM jur_synoptique_membres WHERE id=?", (m["id"],)))
        r = self.get("/juridiction/synoptique/comites/cantine.pdf")
        self.assertTrue(r.data.startswith(b"%PDF"))

    # ------------------------------------------------------------ 5. Excel : export, modèle, import
    @unittest.skipIf(openpyxl is None, "openpyxl absent")
    def test_05_excel(self):
        f = xlsx_feuilles(self.get("/juridiction/synoptique/export.xlsx").data)
        attendu = ["Identité", "Personnel", "Zones", "UP", "Écoles", "Services", "Comités"] + (["Circonscriptions"] if self.ddemp else [])
        for n in attendu:
            self.assertIn(n, f, list(f))
        self.assertTrue(any("Nom et prénoms" in [str(c) for c in r] for r in f["Personnel"][:6]))
        self.assertTrue(any(r and r[0] == "Rubrique" for r in f["Identité"]))
        self.assertTrue(any(r and "Nombre de zones pédagogiques" in str(r[0]) for r in f["Identité"]))
        self.assertTrue(any(r and r[2] == "UP 1" for r in f["UP"] if len(r) > 2))
        f2 = xlsx_feuilles(self.get("/juridiction/synoptique/personnel.xlsx").data)
        self.assertIn("Personnel", f2)
        fm = xlsx_feuilles(self.get("/juridiction/synoptique/modele.xlsx").data)
        self.assertIn("Personnel", fm)
        self.assertIn("Comités", fm)
        # import : un classeur Personnel + Comités
        from outils_xlsx import classeur
        svc = "animation" if not self.ddemp else "semp"
        ligne = [1, "IMP001", "123456789013", "OKE Rachidi", "2008", "FE", "Secrétaire", svc, "B2-4", 600, 580, "", "", "", "01/10/2008", "01/10/2012",
                 "01/09/2023", "", "10/01/2025", "BAC (2006)", "CEAP oui (2010)", "oui", 14, 15, "0198000000"]
        buf = classeur([("Personnel", AS.ENTETES_PERSONNEL, [ligne, [2, "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]]),
                        ("Comités", AS.ENT_MEMBRES, [[1, "Jury / commission CEP", "", "AMOUSSA Odile", "Présidente", "CS", "", ""],
                                                     [2, "Autre instance", "Commission des bourses", "BELLO Sika", "Membre", "Mairie / commune", "", ""],
                                                     [3, "Comité inconnu", "", "X Y", "", "", "", ""]])])
        r = self.c.post("/juridiction/synoptique/import", data={"fichier": (io.BytesIO(buf.getvalue()), "import.xlsx")},
                        content_type="multipart/form-data", follow_redirects=True)
        t = txt(r)
        self.assertIn("1 agent(s) ajouté(s)", t)
        self.assertIn("2 membre(s) importé(s)", t)
        self.assertIn("1 ligne(s) sans comité reconnu", t)
        v = next(x for x in self.personnel() if x["matricule"] == "IMP001")
        self.assertEqual(v["nom_complet"], "OKE Rachidi")
        self.assertEqual(v["date_derniere_formation"], "10/01/2025")
        self.assertIn("CEAP 2010", v["diplome_pro_txt"])
        self.assertIn("BAC (2006)", v["diplome_academique_txt"])
        self.assertEqual(v["promotion"], "2008")
        self.assertTrue(self.q("SELECT 1 FROM jur_synoptique_membres WHERE comite='cep' AND nom_prenoms='AMOUSSA Odile'"))
        self.assertTrue(self.q("SELECT 1 FROM jur_synoptique_membres WHERE comite='autre' AND libelle='Commission des bourses'"))
        # réimport : mise à jour, pas de doublon
        buf.seek(0)
        r = self.c.post("/juridiction/synoptique/import", data={"fichier": (io.BytesIO(buf.getvalue()), "import.xlsx")},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("0 agent(s) ajouté(s), 1 mis à jour", txt(r))
        self.assertEqual(len(self.q("SELECT id FROM jur_agents WHERE matricule='IMP001'", un=False)), 1)
        self.assertEqual(len(self.q("SELECT id FROM jur_synoptique_membres WHERE nom_prenoms='AMOUSSA Odile'", un=False)), 1)
        # fichier manquant
        r = self.c.post("/juridiction/synoptique/import", data={}, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("Choisissez un fichier", txt(r))

    # ------------------------------------------------------------ 6. PDF
    def test_06_pdf(self):
        for u in ("/juridiction/synoptique/synoptique.pdf", "/juridiction/synoptique/personnel.pdf", "/juridiction/synoptique/personnel.pdf?tous=1",
                  "/juridiction/synoptique/reseau.pdf", "/juridiction/synoptique/services.pdf", "/juridiction/synoptique/comites/conseil.pdf",
                  "/juridiction/synoptique/comites/autre.pdf"):
            r = self.get(u)
            self.assertTrue(r.data.startswith(b"%PDF"), u)
        self.assertGreater(len(self.get("/juridiction/synoptique/synoptique.pdf").data), 20000)

    # ------------------------------------------------------------ 7. droits
    def test_07_droits(self):
        c2 = app.test_client()
        self.assertEqual(c2.post("/login", data={"identifiant": "agent", "mdp": "demo1234"}).status_code, 302)
        self.assertEqual(c2.get("/juridiction/synoptique").status_code, 200)
        self.assertEqual(c2.get("/juridiction/synoptique/personnel").status_code, 200)
        self.assertEqual(c2.get("/juridiction/synoptique/agent/0").status_code, 403)
        self.assertEqual(c2.post("/juridiction/synoptique/identite", data={}).status_code, 403)
        self.assertEqual(c2.get("/juridiction/synoptique/import").status_code, 403)
        t = txt(c2.get("/juridiction/synoptique/personnel"))
        self.assertNotIn("Ajouter un agent", t)
        c3 = app.test_client()
        self.assertEqual(c3.post("/login", data={"identifiant": "chef", "mdp": "demo1234"}).status_code, 302)
        self.assertEqual(c3.get("/juridiction/synoptique/agent/0").status_code, 200)
        self.assertEqual(app.test_client().get("/juridiction/synoptique").status_code, 302)   # non connecté


class TestEditionsSeparees(unittest.TestCase):
    """Rejoue la suite dans un processus séparé pour l'édition « cs » (si elle n'a pas tourné ici) et « ddemp »."""

    def test_cs(self):
        if EN_PLACE and EDITION == "cs" or EDITION == "ddemp":
            self.skipTest("édition cs déjà testée dans ce processus, ou processus secondaire")
        r = _rejouer("cs")
        self.assertEqual(r.returncode, 0, r.stderr[-4000:])

    def test_ddemp(self):
        if EDITION == "ddemp":
            self.skipTest("déjà dans l'édition secondaire")
        r = _rejouer("ddemp")
        self.assertEqual(r.returncode, 0, r.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
