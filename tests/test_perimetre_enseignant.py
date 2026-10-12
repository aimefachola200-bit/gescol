# -*- coding: utf-8 -*-
"""Tests du périmètre de l'enseignant (m_perimetre_enseignant, v1.6) : le compte « enseignant » de demo.py
(mot de passe demo1234), affecté à la classe CM2 A, accède à ses classes (élèves, cantine, CEP, notes, registre,
messages aux parents…) avec sa signature digitale « enseignant:<uid> », et se voit refuser le domaine du directeur
(tableau de bord, synoptique, finances, administration, recensement, données, secrétariat, suppression d'élèves…).
Le directeur, le secrétariat, la comptabilité et l'administrateur gardent leurs accès.

Lancer : python3 -m unittest tests.test_perimetre_enseignant   (depuis /home/claude/gescol)
La base est construite par demo.py (sous-processus) dans un dossier temporaire, en édition « publique » ;
TestEditionPrivee rejoue la suite en édition « privee »."""
import html as html_mod
import os
import subprocess
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
EDITION = os.environ.get("GESCOL_EDITION_TEST", "publique")
DOSSIER = tempfile.mkdtemp(prefix=f"gescol_perim_ens_{EDITION}_")
os.environ["GESCOL_EDITION"] = EDITION
os.environ["GESCOL_DATA"] = DOSSIER
subprocess.run([sys.executable, os.path.join(RACINE, "demo.py")], check=True, cwd=RACINE,
               env=dict(os.environ, GESCOL_EDITION=EDITION, GESCOL_DATA=DOSSIER), stdout=subprocess.DEVNULL)

from app import app, q, ex  # noqa: E402
import config  # noqa: E402
import m_perimetre_enseignant as PE  # noqa: E402

EN_PLACE = config.EDITION == EDITION and config.INSTANCE_DIR == DOSSIER
CIBLE = "tests.test_perimetre_enseignant"
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def txt(r):
    return html_mod.unescape(r.data.decode())


def menu(r):
    t = txt(r)
    i, j = t.find('<nav id="menu">'), t.find("</nav>")
    return t[i:j] if i >= 0 else ""


def client(ident, mdp="demo1234"):
    c = app.test_client()
    r = c.post("/login", data={"identifiant": ident, "mdp": mdp})
    assert r.status_code == 302, (ident, r.status_code)
    return c


class TestRegles(unittest.TestCase):
    """Règles pures du module."""

    def test_interdits(self):
        for ep in ("tresorerie", "tresorerie_bilan", "parametres", "utilisateurs", "recensement_accueil", "donnees_accueil",
                   "courrier", "eleve_supprimer", "eleves_export_xlsx", "fondateur_tableau", "directeur_tableau_pdf",
                   "paiements", "paie_accueil", "personnel_form", "educmaster_accueil", "patrimoine_supprimer"):
            self.assertTrue(PE.est_interdit(ep), ep)
        for ep in ("eleves", "eleve_detail", "eleve_form", "cantine_accueil", "cep_accueil", "carriere_moi_fiche",
                   "educmaster_modele_notes_rempli", "espace_enseignant", "verifier", "mon_compte", "communication",
                   "calendrier_scolaire", "patrimoine_accueil", "stock_accueil", "epreuve_form"):
            self.assertFalse(PE.est_interdit(ep), ep)

    def test_cle_niveau(self):
        self.assertEqual(PE.cle_niveau("Maternelle 1"), "maternelle1")
        self.assertEqual(PE.cle_niveau("CM2"), "cm2")
        self.assertEqual(PE.cle_niveau(None), "")


@unittest.skipUnless(EN_PLACE, "édition déjà chargée par un autre module de test : suite rejouée en sous-processus")
class TestPerimetreEnseignant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        with app.app_context():
            cls.u = dict(q("SELECT * FROM utilisateurs WHERE identifiant='enseignant'", un=True))
            cls.cm2 = q("SELECT id FROM classes WHERE niveau='CM2' ORDER BY id", un=True)["id"]
            cls.autre = q("SELECT id FROM classes WHERE niveau<>'CM2' ORDER BY id", un=True)["id"]
            # le compte de démonstration n'a pas d'affectation : on l'affecte à sa classe (CM2 A)
            if not q("SELECT 1 FROM affectations WHERE user_id=?", (cls.u["id"],), un=True):
                ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,NULL)", (cls.u["id"], cls.cm2))
            cls.el_mien = q("SELECT id FROM eleves WHERE classe_id=? ORDER BY id", (cls.cm2,), un=True)["id"]
            cls.el_autre = q("SELECT id FROM eleves WHERE classe_id=? ORDER BY id", (cls.autre,), un=True)["id"]
            cls.nom_autre = q("SELECT nom FROM classes WHERE id=?", (cls.autre,), un=True)["nom"]
            cls.nom_cm2 = q("SELECT nom FROM classes WHERE id=?", (cls.cm2,), un=True)["nom"]
        cls.c = client("enseignant")

    # ------------------------------------------------------------ 1. tableau de bord → Mon espace
    def test_01_accueil_redirige_vers_mon_espace(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/mon-espace"))
        r = self.c.get("/mon-espace")
        self.assertEqual(r.status_code, 200)
        t = txt(r)
        for k in ("Ma signature digitale", f"enseignant:{self.u['id']}", "Mon compte", "Changer mon mot de passe",
                  "Mes documents", self.nom_cm2, "Appel du jour", "Cantine", "CEP (fiches", "Emploi du temps",
                  "Comité de classe", self.u["identifiant"]):
            self.assertIn(k, t, k)
        self.assertNotIn(self.nom_autre, t)

    # ------------------------------------------------------------ 2. domaine du directeur → 403
    def test_02_interdits(self):
        for url in ("/synoptique", "/synoptique/personnel", "/synoptique/comites/sante", "/synoptique/edt/ci",
                    "/tresorerie", "/tresorerie/bilan", "/parametres", "/utilisateurs", "/recensement", "/donnees",
                    "/educmaster", "/secretariat/courrier", "/secretariat/archives", "/directeur", "/fondateur",
                    "/depenses", "/recettes", "/paiements", "/paiements/impayes", "/personnel", "/carriere",
                    "/eleves/nouveau", "/eleves/export.csv", "/eleves/export.xlsx", "/eleves/import", "/classes/nouvelle",
                    "/parents", "/transmission", "/conversion-pdf", "/rapports", "/journal", "/administration/en-ligne",
                    "/cantine/stock/vivres/0", "/patrimoine/mobilier/0"):
            r = self.c.get(url)
            self.assertEqual(r.status_code, 403, url)
        r = self.c.get("/tresorerie")
        self.assertIn("Hors de votre périmètre d'enseignant", txt(r))
        # suppression d'un élève (même de sa classe) : refusée
        self.assertEqual(self.c.post(f"/eleves/{self.el_mien}/supprimer").status_code, 403)
        self.assertEqual(self.c.post("/eleves/supprimer-selection", data={"ids": [self.el_mien]}).status_code, 403)
        with app.app_context():
            self.assertTrue(q("SELECT 1 FROM eleves WHERE id=?", (self.el_mien,), un=True))
        # écritures du domaine du directeur
        self.assertEqual(self.c.post("/cantine/config", data={"classe": self.cm2, "montant": "100", "action": "valider"}).status_code, 403)
        self.assertEqual(self.c.post("/synthese", data={"action": "sauver"}).status_code, 403)
        self.assertEqual(self.c.post("/calendrier/feries", data={}).status_code, 403)
        self.assertEqual(self.c.post("/synoptique/identite", data={"memp": "x"}).status_code, 403)
        self.assertEqual(self.c.post("/synoptique/reglement/retablir").status_code, 403)
        self.assertEqual(self.c.post("/epreuves/comite/0", data={"nom_prenoms": "X"}).status_code, 403)
        self.assertEqual(self.c.post("/cantine/stock/reinitialiser", data={"confirmation": "REINITIALISER"}).status_code, 403)

    # ------------------------------------------------------------ 3. périmètre : ses classes
    def test_03_listes_filtrees(self):
        t = txt(self.c.get("/eleves"))
        self.assertIn(self.nom_cm2, t)
        self.assertNotIn(self.nom_autre, t)
        self.assertNotIn("Inscrire un élève", t)
        self.assertNotIn("supprimer-selection", t)
        t = txt(self.c.get("/classes"))
        self.assertIn(self.nom_cm2, t)
        self.assertNotIn(self.nom_autre, t)
        for url in ("/cantine", "/cantine/recap", "/appel", "/appel/statistiques", "/registre", "/releves", "/affichage",
                    "/evaluations", "/notes", "/eleves/acces-eleves", "/communication"):
            r = self.c.get(url)
            self.assertEqual(r.status_code, 200, url)
            t = txt(r)
            self.assertIn(self.nom_cm2, t, url)
            self.assertNotIn(f">{self.nom_autre}<", t, url)
        if EDITION == "publique":
            t = txt(self.c.get("/cantine/impayes"))
            self.assertNotIn(f">{self.nom_autre}<", t)
        # pages ouvertes
        for url in ("/cep", "/carte", "/cep-blanc", "/synthese", "/epreuves", "/epreuves/0", "/epreuves/grilles", "/matieres",
                    "/calendrier", "/calendrier-scolaire", "/cantine/stock", "/patrimoine", "/verifier", "/bilan-annuel",
                    "/tableau-honneur", "/statistiques-evaluation", "/analyse-evaluation", "/synoptique/edt/cm2",
                    "/synoptique/planification/cm2", "/synoptique/comites/classe", "/synoptique/reglement",
                    f"/classes/{self.cm2}", f"/eleves/{self.el_mien}", f"/eleves/{self.el_mien}/modifier",
                    f"/notes/{self.cm2}/1", f"/cantine/classe/{self.cm2}", f"/educmaster/modeles/notes-primaire/{self.cm2}.xlsx",
                    f"/eleves?classe={self.cm2}", "/mon-compte"):
            self.assertEqual(self.c.get(url).status_code, 200, url)
        # les niveaux par défaut du synoptique sont les siens
        r = self.c.get("/synoptique/edt")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/synoptique/edt/cm2"))
        self.assertTrue(self.c.get("/synoptique/comites").headers["Location"].endswith("/synoptique/comites/classe"))

    def test_04_autre_classe_refusee(self):
        for url in (f"/classes/{self.autre}", f"/eleves/{self.el_autre}", f"/eleves/{self.el_autre}/modifier",
                    f"/eleves/{self.el_autre}/photo", f"/notes/{self.autre}/1", f"/cantine/classe/{self.autre}",
                    f"/eleves?classe={self.autre}", f"/registre?classe={self.autre}", f"/evaluations?classe={self.autre}",
                    f"/appel/{self.autre}/2026-10-01", f"/eleves/{self.el_autre}/absences", f"/carte?eleve={self.el_autre}",
                    f"/educmaster/modeles/notes-primaire/{self.autre}.xlsx"):
            self.assertEqual(self.c.get(url).status_code, 403, url)
        self.assertEqual(self.c.post("/communication/diffuser", data={"cible": f"classe:{self.autre}", "sujet": "s", "texte": "t",
                                                                      "canaux": "portail"}).status_code, 403)
        # diffusion à toute l'école : refusée (redirection avec message), à sa classe : acceptée
        r = self.c.post("/communication/diffuser", data={"cible": "tous", "sujet": "s", "texte": "t", "canaux": "portail"})
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            n0 = q("SELECT COUNT(*) n FROM messages", un=True)["n"]
        r = self.c.post("/communication/diffuser", data={"cible": f"classe:{self.cm2}", "sujet": "Réunion", "texte": "Vendredi",
                                                         "canaux": "portail"})
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            self.assertGreater(q("SELECT COUNT(*) n FROM messages", un=True)["n"], n0)

    def test_05_modification_eleve_courante(self):
        """Renseignements courants modifiables ; ni la classe ni le statut ne changent."""
        with app.app_context():
            e = dict(q("SELECT * FROM eleves WHERE id=?", (self.el_mien,), un=True))
        data = {k: (e.get(k) or "") for k in ("nom", "prenoms", "sexe", "date_naissance", "lieu_naissance", "parent_nom",
                                               "parent_telephone", "parent_whatsapp", "adresse", "nationalite")}
        data.update(parent_telephone="01 99 00 00 01", classe_id=str(self.autre), statut="sorti")
        r = self.c.post(f"/eleves/{self.el_mien}/modifier", data=data)
        self.assertEqual(r.status_code, 302, txt(r)[:300])
        with app.app_context():
            e2 = q("SELECT * FROM eleves WHERE id=?", (self.el_mien,), un=True)
        self.assertEqual(e2["parent_telephone"], "01 99 00 00 01")
        self.assertEqual(e2["classe_id"], self.cm2)
        self.assertEqual(e2["statut"], "inscrit")

    # ------------------------------------------------------------ 4. signature digitale
    def test_06_signature_enseignant(self):
        uid = self.u["id"]
        self.assertEqual(self.c.post(f"/signatures/enseignant:{uid}", json={"image": PNG}).status_code, 200)
        self.assertEqual(self.c.post(f"/signatures/enseignant:{uid + 1}", json={"image": PNG}).status_code, 403)
        self.assertEqual(self.c.post(f"/signatures/classe:{self.autre}:titulaire", json={"image": PNG}).status_code, 403)
        self.assertEqual(self.c.post(f"/signatures/eleve:{self.el_mien}", json={"image": PNG}).status_code, 403)
        self.assertEqual(self.c.post(f"/signatures/ecole:1:directeur", json={"image": PNG}).status_code, 403)
        self.assertEqual(self.c.get(f"/signatures/enseignant:{uid}.png").status_code, 200)
        with app.app_context():
            self.assertEqual(q("SELECT image FROM signatures WHERE cle=?", (f"enseignant:{uid}",), un=True)["image"], PNG)
        # les bulletins / relevés de sa classe sont signés (PDF produits sans erreur)
        r = self.c.get(f"/notes/{self.cm2}/1/bulletins.pdf")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF"))
        r = self.c.post(f"/releves/pdf?classe={self.cm2}", data={})
        self.assertIn(r.status_code, (200, 302))
        if r.status_code == 200:
            self.assertTrue(r.data.startswith(b"%PDF"))
        r = self.c.get(f"/cantine/classe/{self.cm2}/pdf")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF"))

    def test_07_signature_titulaire_repli(self):
        """H.signature_titulaire(cid) : la signature de classe si elle existe, sinon celle de l'enseignant affecté."""
        from flask import g
        uid = self.u["id"]
        with app.app_context():
            ex("INSERT OR REPLACE INTO signatures (cle, image, maj) VALUES (?,?,?)", (f"enseignant:{uid}", PNG, "2026-10-01"))
            ex("DELETE FROM signatures WHERE cle=?", (f"classe:{self.cm2}:titulaire",))
        import m_ecoles
        with app.test_request_context("/"):
            g.user = q("SELECT * FROM utilisateurs WHERE id=?", (uid,), un=True)
            g.ecole = q("SELECT * FROM ecoles WHERE id=1", un=True)
            H = _H_de(m_ecoles)
            self.assertEqual(H.signature_enseignant(uid), PNG)
            self.assertEqual(H.signature_titulaire(self.cm2), PNG)      # seul enseignant affecté → sa signature
            self.assertIsNone(H.signature_titulaire(self.autre))
            self.assertTrue(H.perimetre_enseignant())
            self.assertEqual(H.niveaux_enseignant(), ["cm2"])
            g.user = q("SELECT * FROM utilisateurs WHERE identifiant='directeur'", un=True)
            self.assertFalse(H.perimetre_enseignant())
            self.assertEqual(H.signature_titulaire(self.cm2), PNG)      # repli aussi pour les documents du directeur
            self.assertTrue(m_ecoles.RE_CLE_SIGNATURE.match(f"enseignant:{uid}"))

    # ------------------------------------------------------------ 5. menu
    def test_08_menu(self):
        m = menu(self.c.get("/mon-espace"))
        for k in ("Mon espace", "Élèves de mes classes", "Mes classes", "Registre d'appel", "Saisie des notes",
                  "Notes par période", "Examens (CEP)", "Paiements de cantine", "Messages et WhatsApp", "Comptes élèves",
                  "Vérifier un document"):
            self.assertIn(k, m, k)
        for k in ("Tableau de bord", "Tableau synoptique", "Trésorerie", "Finances", "Administration", "Paramètres",
                  "Utilisateurs", "Secrétariat", "Données", "Import / export", "Comptes parents", "Configuration (montants)",
                  "recensement"):
            self.assertNotIn(k, m, k)
        if EDITION == "publique":
            self.assertIn("Ma fiche de carrière", m)
            self.assertIn("Impayés de cantine", m)

    # ------------------------------------------------------------ 6. autres rôles inchangés
    def test_09_autres_roles(self):
        for ident, syno in (("directeur", 200), ("secretariat", 200), ("compta", 200)):
            d = client(ident)
            self.assertEqual(d.get("/").status_code, 200, ident)
            self.assertEqual(d.get("/eleves").status_code, 200)
            self.assertEqual(d.get(f"/classes/{self.autre}").status_code, 200)
            self.assertEqual(d.get("/synoptique").status_code, syno)
            t = txt(d.get("/eleves"))
            self.assertIn(self.nom_autre, t)
        d = client("directeur")
        self.assertEqual(d.get("/tresorerie").status_code, 200)
        self.assertEqual(d.get("/eleves/nouveau").status_code, 200)
        self.assertIn("Inscrire un élève", txt(d.get("/eleves")))
        self.assertIn("Tableau de bord", menu(d.get("/")))
        self.assertEqual(d.post(f"/signatures/enseignant:{self.u['id']}", json={"image": PNG}).status_code, 200)
        # administrateur (mot de passe à changer : page du compte)
        a = app.test_client()
        self.assertEqual(a.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code, 302)
        self.assertIn(a.get("/").status_code, (200, 302))
        self.assertEqual(a.get("/mon-compte").status_code, 200)


def _H_de(module):
    """Espace H d'un module : retrouvé dans la fermeture d'une de ses vues."""
    for f in app.view_functions.values():
        code = getattr(f, "__wrapped__", f)
        if getattr(code, "__module__", "") == module.__name__ and code.__closure__:
            for cel in code.__closure__:
                try:
                    v = cel.cell_contents
                except ValueError:
                    continue
                if hasattr(v, "classes_autorisees") and hasattr(v, "signature_titulaire"):
                    return v
    raise AssertionError("H introuvable")


def _rejouer(edition):
    env = dict(os.environ, GESCOL_EDITION_TEST=edition)
    env.pop("GESCOL_EDITION", None)
    env.pop("GESCOL_DATA", None)
    return subprocess.run([sys.executable, "-m", "unittest", f"{CIBLE}.TestPerimetreEnseignant", f"{CIBLE}.TestRegles"],
                          cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestEditionsSeparees(unittest.TestCase):
    """Rejoue la suite dans un processus séparé pour l'édition « publique » (si elle n'a pas tourné ici) et « privee »."""

    def test_publique(self):
        if EN_PLACE and EDITION == "publique" or EDITION == "privee":
            self.skipTest("édition publique déjà testée dans ce processus, ou processus secondaire")
        r = _rejouer("publique")
        self.assertEqual(r.returncode, 0, r.stderr[-4000:])

    def test_privee(self):
        if EDITION == "privee":
            self.skipTest("processus secondaire")
        r = _rejouer("privee")
        self.assertEqual(r.returncode, 0, r.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
