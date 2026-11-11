# -*- coding: utf-8 -*-
"""Tests v1.6 — applications CS / DDEMP : comptes des directeurs et enseignants (à la place des comptes parents),
Service des Ressources Humaines de la CS, financement des écoles (subventions, cotisations de cantine, dépenses, bilan
et budget), périmètre d'accès de chaque division (a_integration, a_divisions, a_structure).
Lancer : python3 -m unittest tests.test_perimetres   (depuis /home/claude/gescol)

La base est construite par demo_juridiction.py (sous-processus) dans un dossier temporaire, en édition « cs » ;
TestEditionsSeparees rejoue la suite en édition « ddemp » dans un sous-processus."""
import html as html_mod
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
EDITION = os.environ.get("GESCOL_EDITION_TEST", "cs")
DOSSIER = tempfile.mkdtemp(prefix=f"gescol_perim_{EDITION}_")
os.environ["GESCOL_EDITION"] = EDITION
os.environ["GESCOL_DATA"] = DOSSIER
if EDITION in ("cs", "ddemp"):
    subprocess.run([sys.executable, os.path.join(RACINE, "demo_juridiction.py")], check=True, cwd=RACINE,
                   env=dict(os.environ, GESCOL_EDITION=EDITION, GESCOL_DATA=DOSSIER), stdout=subprocess.DEVNULL)

from app import app, q, ex  # noqa: E402
import config  # noqa: E402
import a_divisions as D  # noqa: E402
import a_structure as S  # noqa: E402

EN_PLACE = config.EDITION == EDITION and config.INSTANCE_DIR == DOSSIER
DDEMP = EDITION == "ddemp"
CIBLE = "tests.test_perimetres"

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None


def _rejouer(edition):
    env = dict(os.environ, GESCOL_EDITION_TEST=edition)
    env.pop("GESCOL_EDITION", None)
    env.pop("GESCOL_DATA", None)
    return subprocess.run([sys.executable, "-m", "unittest", CIBLE], cwd=RACINE, env=env, capture_output=True, text=True,
                          timeout=900)


def txt(r):
    return html_mod.unescape(r.data.decode())


def client(ident, mdp="demo1234"):
    c = app.test_client()
    r = c.post("/login", data={"identifiant": ident, "mdp": mdp})
    assert r.status_code == 302, (ident, r.status_code)
    return c


def menu(r):
    """Partie « menu latéral » de la page (nav#menu)."""
    t = txt(r)
    i, j = t.find('<nav id="menu">'), t.find("</nav>")
    return t[i:j] if i >= 0 else ""


def urls_perimetre(r):
    m = re.search(r'id="perimetre-menu"[^>]*>(.*?)</script>', r.data.decode(), re.S)
    return json.loads(m.group(1)) if m else None


def feuille(r):
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    return [[c for c in row] for row in wb.active.iter_rows(values_only=True)]


@unittest.skipUnless(EN_PLACE, "édition déjà chargée par un autre module de test : suite rejouée en sous-processus")
class TestPerimetres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.c = client("responsable")
        with app.app_context():
            cls.jur = [dict(r) for r in q("SELECT * FROM jur_ecoles WHERE actif=1 AND secteur='public' AND type='EP' ORDER BY id")]
        cls.jid = cls.jur[0]["id"]
        cls.c.post(f"/juridiction/ecoles-modules/{cls.jid}/ouvrir")
        with app.app_context():
            cls.eid = q("SELECT id FROM ecoles WHERE jur_ecole_id=?", (cls.jid,), un=True)["id"]

    # ------------------------------------------------------------ 1. comptes des directeurs et enseignants
    def test_01_menu_directeurs_enseignants(self):
        m = menu(self.c.get("/juridiction/comptes"))
        self.assertIn("Directeurs et enseignants", m)
        self.assertIn("Comptes des directeurs et enseignants", m)
        self.assertIn("WhatsApp et SMS : directeurs et enseignants", m)
        self.assertNotIn("Comptes parents", m)
        self.assertNotIn("Comptes élèves", m)
        self.assertNotIn(">Parents", m)
        # les pages parents restent accessibles par leur adresse
        self.assertEqual(self.c.get("/communication").status_code, 200)

    def test_02_creation_comptes_pdf_excel(self):
        r = self.c.post("/juridiction/comptes", data={"action": "creer", "role": "directeur", "ecole": self.jur[1]["id"]})
        self.assertEqual(r.status_code, 200)
        t = txt(r)
        self.assertIn("Codes d'accès", t)
        m = re.search(r'name="uid" value="(\d+)"><input type="hidden" name="mdp" value="([^"]+)"', r.data.decode())
        self.assertTrue(m)
        uid, mdp = int(m.group(1)), m.group(2)
        with app.app_context():
            u = q("SELECT * FROM utilisateurs WHERE id=?", (uid,), un=True)
            loc = q("SELECT id FROM ecoles WHERE jur_ecole_id=?", (self.jur[1]["id"],), un=True)
        self.assertEqual(u["role"], "directeur")
        self.assertEqual(u["doit_changer_mdp"], 1)
        self.assertTrue(loc and u["ecole_id"] == loc["id"])            # école locale créée et rattachée
        self.assertTrue(u["identifiant"].startswith("dir-"))
        # PDF des codes d'accès (mot de passe vérifié contre l'empreinte)
        r = self.c.post("/juridiction/comptes/codes.pdf", data={"uid": uid, "mdp": mdp})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF"))
        r = self.c.post("/juridiction/comptes/codes.pdf", data={"uid": uid, "mdp": "faux"})
        self.assertEqual(r.status_code, 302)                           # code faux : rien à imprimer
        # compte enseignant + identifiant proposé + lien vers les affectations
        r = self.c.post("/juridiction/comptes", data={"action": "creer", "role": "enseignant", "ecole": self.jid,
                                                      "nom": "DOSSOU Afiavi", "identifiant": "", "mdp": "court"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Affecter à ses classes", txt(r))
        with app.app_context():
            e = q("SELECT * FROM utilisateurs WHERE role='enseignant' AND nom='DOSSOU Afiavi'", un=True)
        self.assertEqual(e["identifiant"], "dossou.afiavi")
        self.assertEqual(e["ecole_id"], self.eid)
        # le directeur se connecte : école ouverte d'office, mot de passe à changer
        c2 = client(u["identifiant"], mdp)
        self.assertEqual(c2.get("/mon-compte").status_code, 200)
        # liste, filtre, Excel
        t = txt(self.c.get("/juridiction/comptes"))
        self.assertIn(u["identifiant"], t)
        self.assertIn("dossou.afiavi", t)
        t = txt(self.c.get(f"/juridiction/comptes?role=directeur&ecole={self.jur[1]['id']}"))
        self.assertIn(u["identifiant"], t)
        self.assertNotIn("dossou.afiavi", t)
        if openpyxl:
            r = self.c.get("/juridiction/comptes.xlsx")
            self.assertEqual(r.status_code, 200)
            rows = feuille(r)
            self.assertTrue(any(u["identifiant"] in [str(x) for x in row] for row in rows))
        # réinitialisation et désactivation
        r = self.c.post("/juridiction/comptes", data={"action": "reinit", "uid": e["id"]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Codes d'accès", txt(r))
        self.assertEqual(self.c.post("/juridiction/comptes", data={"action": "basculer", "uid": e["id"]}).status_code, 302)
        with app.app_context():
            self.assertEqual(q("SELECT actif FROM utilisateurs WHERE id=?", (e["id"],), un=True)["actif"], 0)
        # droit : le conseiller pédagogique n'a pas jur_comptes
        self.assertEqual(client("cp1").get("/juridiction/comptes").status_code, 403)

    # ------------------------------------------------------------ 2. service des ressources humaines (CS)
    def test_03_service_rh(self):
        with app.app_context():
            code = "srh" if DDEMP else "personnel"
            svc = S.service_par_code(code)
            self.assertEqual(svc["nom"], "Service des Ressources Humaines")
            self.assertEqual(svc["sigle"], "SRH" if DDEMP else "RH")
            if not DDEMP:
                self.assertIn("HORS AOF", (svc["note"] or "").upper().replace("SERVICE HORS AOF", "HORS AOF"))
                self.assertIn("comptes GESCOL des directeurs", svc["attributions"])
                # un service encore nommé CSPAF est renommé par assurer_services
                ex("UPDATE jur_services SET nom='Service du Personnel et des Affaires financières', sigle='CSPAF' WHERE code='personnel'")
                S.assurer_services()
                svc = S.service_par_code("personnel")
                self.assertEqual((svc["nom"], svc["sigle"]), ("Service des Ressources Humaines", "RH"))
            eps = {ep for _l, ep, _d in D.MODULES_PAR_DIVISION[code]}
        for ep in ("jur_personnel", "jur_retraite", "personnel", "carriere_accueil", "docs_enseignant_accueil",
                   "synoptique_personnel_liste", "jur_comptes", "jur_messages"):
            self.assertIn(ep, eps)
        self.assertNotIn("cantine_accueil", eps)
        self.assertIn("cantine_accueil", {ep for _l, ep, _d in D.MODULES_PAR_DIVISION["administration" if not DDEMP else "spaf"]})
        r = self.c.get(f"/juridiction/divisions/{code}")
        self.assertEqual(r.status_code, 200)
        t = txt(r)
        self.assertIn("Service des Ressources Humaines", t)
        self.assertIn("Comptes rattachés et périmètre", t)
        self.assertIn("Comptes des directeurs et enseignants", t)
        m = menu(r)
        self.assertIn("Ressources humaines (personnel, carrière)", m)
        self.assertIn("Personnel de l'école (RH)", m)

    # ------------------------------------------------------------ 3. financement
    def test_04_finances_menu_et_routes(self):
        m = menu(self.c.get("/juridiction/ecole"))
        for lib in ("Subventions de l'État et recettes", "Cotisations de cantine (paiements)", "Impayés de cantine", "Dépenses",
                    "Frais de dossier CEP", "Trésorerie", "Bilan et budget", "Vivres et stock"):
            self.assertIn(lib, m)
        self.assertNotIn("Paiements de scolarité", m)       # école publique ouverte
        for u in ("/recettes", "/cantine", "/cantine/impayes", "/depenses", "/cep-frais", "/tresorerie", "/tresorerie/bilan",
                  "/tresorerie/budget", "/cantine/stock", "/juridiction/financement"):
            self.assertEqual(self.c.get(u).status_code, 200, u)

    def test_05_financement_totaux(self):
        d1 = config.ANNEE_ACTIVE[:4] + "-10-05"
        with app.app_context():
            cid = ex("INSERT INTO classes (nom, niveau, ecole_id, frais_scolarite) VALUES ('CM1 FIN', 'CM1', ?, 0)", (self.eid,))
            e1 = ex("INSERT INTO eleves (nom, prenoms, sexe, classe_id, statut, date_inscription, annee) VALUES ('FIN', 'Un', 'M', ?, 'inscrit', ?, ?)", (cid, d1, config.ANNEE_ACTIVE))
            e2 = ex("INSERT INTO eleves (nom, prenoms, sexe, classe_id, statut, date_inscription, annee) VALUES ('FIN', 'Deux', 'F', ?, 'inscrit', ?, ?)", (cid, d1, config.ANNEE_ACTIVE))
            ex("INSERT INTO cantine_paiements (eleve_id, date, montant) VALUES (?,?,100)", (e1, d1))
            ex("INSERT INTO cantine_paiements (eleve_id, date, montant) VALUES (?,?,100)", (e2, d1))
            ex("INSERT INTO fp_recettes (ecole_id, date, origine, libelle, montant) VALUES (?,?,'Subvention de l''État','Subvention 1er trimestre',50000)",
               (self.eid, d1))
            ex("INSERT INTO fp_recettes (ecole_id, date, origine, libelle, montant) VALUES (?,?,'Cotisations APE','APE',5000)", (self.eid, d1))
            ex("INSERT INTO fp_recettes (ecole_id, date, origine, libelle, montant, annule) VALUES (?,?,'Subvention de l''État','annulée',9999,1)",
               (self.eid, d1))
            ex("INSERT INTO fp_depenses (ecole_id, date, categorie, libelle, montant) VALUES (?,?,'Cantine – vivres','Riz',20000)", (self.eid, d1))
            ex("INSERT INTO fp_parametres (ecole_id, annee, solde_ouverture) VALUES (?,?,1000)", (self.eid, config.ANNEE_ACTIVE))
            ex("INSERT OR REPLACE INTO budget (annee, type, categorie, montant) VALUES (?,'entree','Cantine',300000)", (config.ANNEE_ACTIVE,))
            ex("INSERT OR REPLACE INTO budget (annee, type, categorie, montant) VALUES (?,'sortie','Cantine',120000)", (config.ANNEE_ACTIVE,))
        H = app.extensions["gescol"]["H"]
        with app.test_request_context("/juridiction/financement"):
            app.preprocess_request()
            fin = H.jur_financement(config.ANNEE_ACTIVE)
        e = next(x for x in fin["ecoles"] if x["je"]["id"] == self.jid)
        self.assertEqual(e["source"], "locale")
        self.assertEqual((e["subventions"], e["autres"], e["cantine"], e["depenses"], e["beneficiaires"]), (50000, 5000, 200, 20000, 2))
        self.assertEqual(e["solde"], 1000 + 50000 + 5000 + 200 - 20000)
        T = fin["total"]
        self.assertEqual(T["subventions"], 50000)
        self.assertEqual(T["depenses"], 20000)
        self.assertEqual(T["cantine"], sum(x["cantine"] or 0 for x in fin["ecoles"]))
        self.assertTrue(any(x["source"] == "transmission" for x in fin["ecoles"]))   # section cantine des paquets de la démo
        self.assertEqual(sum(z["subventions"] for z in fin["zones"]), T["subventions"])
        self.assertEqual((fin["budget"]["entree"], fin["budget"]["sortie"]), (300000, 120000))
        # page, Excel, PDF
        t = txt(self.c.get("/juridiction/financement"))
        self.assertIn("50 000", t)
        self.assertIn("300 000", t)
        self.assertIn(e["nom"], t)
        r = self.c.get("/juridiction/financement?export=pdf")
        self.assertTrue(r.data.startswith(b"%PDF"))
        if openpyxl:
            r = self.c.get("/juridiction/financement?export=xlsx")
            self.assertEqual(r.status_code, 200)
            rows = feuille(r)
            total = next(row for row in rows if row and row[0] == "TOTAL GÉNÉRAL")
            self.assertEqual(total[3], "50 000")
        self.assertEqual(self.c.get("/juridiction/financement?annee=2019-2020").status_code, 200)
        # trésorerie / bilan de l'école publique ouverte : les subventions et dépenses y entrent (m_tresorerie)
        t = txt(self.c.get("/tresorerie/bilan"))
        self.assertIn("Subvention de l'État", t)
        # le CP n'a pas accès aux finances
        self.assertEqual(client("cp1").get("/juridiction/financement").status_code, 403)

    # ------------------------------------------------------------ 4. périmètres des divisions
    def test_06_perimetre_chef_dosp(self):
        chef = client("chef")
        self.assertEqual(chef.post(f"/juridiction/ecoles-modules/{self.jid}/ouvrir").status_code, 302)
        self.assertEqual(chef.get("/recensement").status_code, 200)
        self.assertEqual(chef.get("/juridiction/statistiques/ecoles").status_code, 200)
        self.assertEqual(chef.get("/juridiction/fiches").status_code, 200)
        r = chef.get("/juridiction/personnel")
        self.assertEqual(r.status_code, 403)
        self.assertIn("Hors du périmètre de votre division", txt(r))
        self.assertEqual(chef.get("/juridiction/comptes").status_code, 403)
        self.assertEqual(chef.get("/personnel").status_code, 403)
        self.assertEqual(chef.get("/juridiction/cep").status_code, 403 if DDEMP else 200)
        # pages communes
        for u in ("/juridiction/tableau-de-bord", "/juridiction/synoptique", "/juridiction/messages", "/mon-compte", "/verifier",
                  "/juridiction/ecoles-modules", "/juridiction/ecole", "/juridiction/divisions"):
            self.assertEqual(chef.get(u).status_code, 200, u)
        # menu filtré : liste JSON des adresses autorisées + script de filtrage
        r = chef.get("/juridiction/tableau-de-bord")
        urls = urls_perimetre(r)
        self.assertIsNotNone(urls)
        self.assertIn("/recensement", urls)
        self.assertIn("/juridiction/tableau-de-bord", urls)
        self.assertNotIn("/juridiction/personnel", urls)
        self.assertNotIn("/juridiction/comptes", urls)
        self.assertIn('data-division="' + ("semp" if DDEMP else "organisation") + '"', r.data.decode())
        self.assertIn("removeChild", r.data.decode())
        # fiche de la division : le compte chef y figure avec son périmètre
        t = txt(chef.get("/juridiction/divisions/" + ("semp" if DDEMP else "organisation")))
        self.assertIn("Comptes rattachés et périmètre", t)
        self.assertIn("chef", t)
        self.assertIn("limité à la division", t)

    def test_07_perimetre_rh(self):
        rh = client("rh")
        self.assertEqual(rh.get("/juridiction/personnel").status_code, 200)
        self.assertEqual(rh.get("/juridiction/personnel/retraite").status_code, 200)
        self.assertEqual(rh.get("/juridiction/comptes").status_code, 200)
        self.assertEqual(rh.get("/juridiction/messages").status_code, 200)
        self.assertEqual(rh.get("/juridiction/cep").status_code, 403)
        self.assertEqual(rh.get("/recensement").status_code, 403)
        self.assertEqual(rh.get("/juridiction/financement").status_code, 403)
        rh.post(f"/juridiction/ecoles-modules/{self.jid}/ouvrir")
        self.assertEqual(rh.get("/personnel").status_code, 200)
        self.assertEqual(rh.get("/carriere").status_code, 200)
        self.assertEqual(rh.get("/eleves").status_code, 403)
        urls = urls_perimetre(rh.get("/juridiction/personnel"))
        self.assertIn("/juridiction/personnel", urls)
        self.assertIn("/juridiction/comptes", urls)
        self.assertNotIn("/recensement", urls)

    def test_08_sans_perimetre(self):
        # responsable : tout 200, pas de filtrage du menu
        for u in ("/juridiction/personnel", "/juridiction/cep", "/recensement", "/juridiction/comptes", "/juridiction/financement", "/eleves"):
            self.assertEqual(self.c.get(u).status_code, 200, u)
        self.assertIsNone(urls_perimetre(self.c.get("/juridiction/tableau-de-bord")))
        # conseiller pédagogique et agent sans division : non concernés par les périmètres
        self.assertIsNone(urls_perimetre(client("cp1").get("/juridiction/visites")))
        ag = client("agent")
        self.assertIsNone(urls_perimetre(ag.get("/juridiction/tableau-de-bord")))
        self.assertEqual(ag.get("/juridiction/transmissions").status_code, 200)
        # la division du compte (utilisateurs.service_code) prime sur la fiche agent ; changement par la page Utilisateurs
        with app.app_context():
            uid = q("SELECT id FROM utilisateurs WHERE identifiant='agent'", un=True)["id"]
        r = self.c.post("/utilisateurs", data={"action": "service", "uid": uid, "service_code": "secretariat" if not DDEMP else "sec"})
        self.assertEqual(r.status_code, 302)
        ag = client("agent")
        self.assertIsNotNone(urls_perimetre(ag.get("/juridiction/tableau-de-bord")))
        self.assertEqual(ag.get("/juridiction/personnel/retraite").status_code, 403)
        self.c.post("/utilisateurs", data={"action": "service", "uid": uid, "service_code": ""})
        self.assertIsNone(urls_perimetre(client("agent").get("/juridiction/tableau-de-bord")))
        t = txt(self.c.get("/utilisateurs"))
        self.assertIn("Division / service", t)
        # création d'un compte avec division depuis la page Utilisateurs
        r = self.c.post("/utilisateurs", data={"action": "creer", "identifiant": "agentdiv", "nom": "Agent division", "role": "agent",
                                               "mdp": "motdepasse8", "service_code": "secretariat" if not DDEMP else "sec"})
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            self.assertEqual(q("SELECT service_code FROM utilisateurs WHERE identifiant='agentdiv'", un=True)["service_code"],
                             "secretariat" if not DDEMP else "sec")


class TestEditionsSeparees(unittest.TestCase):
    """Rejoue la suite dans un processus séparé pour l'édition « cs » (si elle n'a pas tourné ici) et « ddemp »."""

    def test_cs(self):
        if EN_PLACE and EDITION == "cs" or EDITION == "ddemp":
            self.skipTest("édition cs déjà testée dans ce processus, ou processus secondaire")
        r = _rejouer("cs")
        self.assertEqual(r.returncode, 0, r.stderr[-4000:])

    def test_ddemp(self):
        if EDITION == "ddemp":
            self.skipTest("processus secondaire")
        r = _rejouer("ddemp")
        self.assertEqual(r.returncode, 0, r.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
