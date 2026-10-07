# -*- coding: utf-8 -*-
"""Tests du chantier « Griffe et NIP » : cachet rectangulaire du nom du responsable (griffe), préconçu, apposé sur les
documents signés, et ligne « NIP » avant la ligne du nom sur les certificats (enseignant, élève, CS / DDEMP).
Lancer : python3 -m unittest tests.test_griffe_nip   (depuis /home/claude/gescol)

L'édition chargée est choisie par GESCOL_EDITION_TEST (publique par défaut) ; la partie CS est rejouée dans un second
processus (TestEditionsSeparees) avec la base de démonstration de demo_juridiction (compte « responsable »)."""
import base64
import html as html_mod
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
EDITION = os.environ.get("GESCOL_EDITION_TEST", "publique")
DOSSIER = tempfile.mkdtemp(prefix=f"gescol_griffe_{EDITION}_")
os.environ["GESCOL_EDITION"] = EDITION
os.environ["GESCOL_DATA"] = DOSSIER

from app import app  # noqa: E402
import config  # noqa: E402
import cachet  # noqa: E402

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

EN_PLACE = config.EDITION == EDITION


def txt(r):
    return html_mod.unescape(r.data.decode())


def texte_pdf(data):
    assert data.startswith(b"%PDF"), data[:40]
    with pdfplumber.open(io.BytesIO(data)) as p:
        return "\n".join((pg.extract_text() or "") for pg in p.pages)


def signature_png():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(10, 100), (80, 20), (150, 100), (220, 30), (290, 90)], fill=(20, 40, 160, 255), width=6)
    b = io.BytesIO()
    img.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def champs_formulaire(html):
    return dict(re.findall(r'name="([a-z_0-9]+)" value="([^"]*)"', html))


def _rejouer(edition, classe):
    env = dict(os.environ, GESCOL_EDITION_TEST=edition)
    env.pop("GESCOL_EDITION", None)
    env.pop("GESCOL_DATA", None)
    return subprocess.run([sys.executable, "-m", "unittest", f"tests.test_griffe_nip.{classe}"], cwd=RACINE, env=env,
                          capture_output=True, text=True, timeout=900)


class TestCachetModule(unittest.TestCase):
    def test_svg_et_dessin(self):
        s = cachet.svg_nom(["Le Directeur", "Dagba Rosine", "Institutrice"], "rouge")
        self.assertIn("<svg", s)
        self.assertIn("LE DIRECTEUR", s)
        self.assertIn("DAGBA ROSINE", s)
        self.assertIn(cachet.COULEURS["rouge"], s)
        self.assertEqual(cachet.lignes_griffe(["", " a  b ", "c", "d", "e"]), ["A B", "C", "D"])
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        h = cachet.dessiner_nom(c, 200, 700, ["Le Chef de la Circonscription Scolaire", "HOUNGBO Marc"], largeur=120)
        self.assertGreater(h, 10)
        c.save()
        self.assertIn("HOUNGBO MARC", texte_pdf(buf.getvalue()))


@unittest.skipIf(pdfplumber is None, "pdfplumber absent")
class TestEcolePublique(unittest.TestCase):
    """Édition publique : griffe de l'école, certificats de l'enseignant et de l'élève avec la ligne NIP."""

    @classmethod
    def setUpClass(cls):
        if not EN_PLACE or EDITION != "publique":
            raise unittest.SkipTest(f"édition « {config.EDITION} » chargée : suite rejouée en sous-processus")
        app.config["TESTING"] = True
        from werkzeug.security import generate_password_hash
        with app.app_context():
            from app import ex, q
            ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'",
               (generate_password_hash("admin123"),))
            ex("DELETE FROM eleves")
            ex("DELETE FROM classes")
            ex("DELETE FROM personnel")
            cls.cl = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES (?,?,?,?)", ("CM2 A", "CM2", 0, 1))
            cls.el = ex("""INSERT INTO eleves (nom, prenoms, sexe, date_naissance, lieu_naissance, classe_id, statut,
                           date_inscription, annee, matricule, nip) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        ("DOSSOU", "Grâce", "F", "2015-05-03", "Cotonou", cls.cl, "inscrit", "2026-09-15",
                         config.ANNEE_ACTIVE, "TEST-0001", "NIP-ELEVE-77"))
            cls.pid = ex("INSERT INTO personnel (nom, prenoms, fonction, type_contrat, ecole_id, date_embauche) "
                         "VALUES (?,?,?,?,?,?)", ("KOUTON", "Serge", "Enseignant(e)", "CDI", 1, "2024-09-02"))
            cls.cols_personnel = {r["name"] for r in q("PRAGMA table_info(personnel)")}
            if "nip" in cls.cols_personnel:
                ex("UPDATE personnel SET nip=? WHERE id=?", ("NIP-AGENT-55", cls.pid))
            ex("UPDATE ecoles SET directeur_titre='Directrice', directeur_nom='DAGBA Rosine', cachet_sup='EPP TEST', "
               "cachet_inf='COTONOU', cachet_centre='LA DIRECTION', cachet_couleur='bleu', ville='Cotonou' WHERE id=1")
            ex("INSERT OR REPLACE INTO signatures (cle, image, maj) VALUES (?,?,?)",
               ("ecole:1:directeur", signature_png(), "2026-01-01 00:00:00"))
        cls.c = app.test_client()
        r = cls.c.post("/login", data={"identifiant": "admin", "mdp": "admin123"})
        assert r.status_code == 302, r.status_code

    def get(self, url, code=200):
        r = self.c.get(url)
        self.assertEqual(r.status_code, code, f"{url} → {r.status_code}\n{r.data[:300]}")
        return r

    def test_01_activer_griffe(self):
        r = self.get("/ecoles/1/modifier")
        h = txt(r)
        self.assertIn('name="griffe_actif"', h)
        self.assertIn('name="griffe_ligne3"', h)
        self.assertIn("apercu-griffe", h)
        champs = champs_formulaire(h)
        champs.update(nom="École test", statut="Publique", directeur_titre="Directrice", directeur_nom="DAGBA Rosine",
                      admin_titre="Administrateur", ccs_titre="Le CCS", cachet_couleur="bleu",
                      griffe_actif="1", griffe_ligne3="Institutrice", griffe_couleur="rouge")
        r = self.c.post("/ecoles/1/modifier", data=champs)
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            from app import q
            e = q("SELECT * FROM ecoles WHERE id=1", un=True)
            self.assertEqual(e["griffe_actif"], 1)
            self.assertEqual(e["griffe_ligne3"], "Institutrice")
            self.assertEqual(e["griffe_couleur"], "rouge")
        # aperçu SVG : nom en majuscules, couleur rouge
        r = self.get("/ecoles/1/griffe.svg")
        self.assertEqual(r.mimetype, "image/svg+xml")
        s = r.data.decode()
        self.assertIn("LA DIRECTRICE", s)
        self.assertIn("DAGBA ROSINE", s)
        self.assertIn("INSTITUTRICE", s)
        self.assertIn(cachet.COULEURS["rouge"], s)
        # aperçu instantané avec paramètres
        r = self.get("/ecoles/griffe.svg?titre=Directeur&nom=Zinsou+Paul&ligne3=&couleur=bleu")
        self.assertIn("ZINSOU PAUL", r.data.decode())
        # H.griffe_ecole
        with app.test_request_context("/"):
            app.preprocess_request()
            from notif import H
            gr = H.griffe_ecole(1)
            self.assertIsNotNone(gr)
            self.assertEqual(gr[0][1], "DAGBA Rosine")
            self.assertEqual(gr[1], "rouge")
            self.assertIsNotNone(config.ECOLE.get("_griffe"))

    def test_02_certificat_enseignant_nip_et_griffe(self):
        r = self.get(f"/docs-enseignant/prise_service_dir?p={self.pid}")
        h = txt(r)
        self.assertLess(h.find('name="nip"'), h.find('name="nom_prenoms"'), "le champ NIP précède le champ du nom")
        champs = champs_formulaire(h)
        if "nip" in self.cols_personnel:
            self.assertEqual(champs.get("nip"), "NIP-AGENT-55")
        champs.update(p=str(self.pid), signer="1", action="pdf", directeur_titre="Directrice")
        r = self.c.post("/docs-enseignant/prise_service_dir", data=champs)
        self.assertEqual(r.status_code, 200)
        t = texte_pdf(r.data)
        self.assertIn("NIP", t)
        self.assertLess(t.find("NIP"), t.find("KOUTON Serge"), "la ligne NIP précède la ligne du nom")
        self.assertIn("DAGBA ROSINE", t, "la griffe porte le nom du signataire en majuscules")
        self.assertIn("LA DIRECTRICE", t)
        # version vierge : la ligne NIP reste (pointillés)
        t = texte_pdf(self.get("/docs-enseignant/prise_service_dir/vierge.pdf").data)
        self.assertIn("NIP", t)
        # certificat délivré par le CCS (griffe du CCS inconnue côté école : nom en clair)
        r = self.get(f"/docs-enseignant/presence_poste_ccs?p={self.pid}")
        champs = champs_formulaire(txt(r))
        champs.update(p=str(self.pid), signer="1", action="pdf")
        r = self.c.post("/docs-enseignant/presence_poste_ccs", data=champs)
        t = texte_pdf(r.data)
        self.assertLess(t.find("NIP"), t.find("KOUTON Serge"))
        # fiche d'évaluation : NIP avant le nom dans l'identification
        r = self.get(f"/docs-enseignant/eval_ace?p={self.pid}")
        champs = champs_formulaire(txt(r))
        champs.update(p=str(self.pid), signer="1", action="pdf")
        t = texte_pdf(self.c.post("/docs-enseignant/eval_ace", data=champs).data)
        self.assertLess(t.find("NIP"), t.find("KOUTON"))

    def test_03_certificats_eleve(self):
        r = self.get(f"/docs-enseignant/certificat_scolarite?p={self.el}")
        h = txt(r)
        self.assertLess(h.find('name="nip"'), h.find('name="nom_prenoms"'))
        champs = champs_formulaire(h)
        self.assertEqual(champs.get("nip"), "NIP-ELEVE-77")
        champs.update(p=str(self.el), signer="1", action="pdf")
        r = self.c.post("/docs-enseignant/certificat_scolarite", data=champs)
        self.assertEqual(r.status_code, 200)
        t = texte_pdf(r.data)
        self.assertIn("NIP-ELEVE-77", t)
        self.assertLess(t.find("NIP"), t.find("DOSSOU"))
        self.assertIn("DAGBA ROSINE", t)
        t = texte_pdf(self.get("/docs-enseignant/certificat_scolarite/vierge.pdf").data)
        self.assertIn("NIP", t)
        for doc in ("certificat_frequentation", "attestation_inscription", "certificat_transfert"):
            t = texte_pdf(self.get(f"/eleves/{self.el}/document/{doc}.pdf").data)
            self.assertIn("NIP-ELEVE-77", t, doc)
            self.assertLess(t.find("NIP"), t.find("Nom et prénoms"), doc)
            self.assertIn("DAGBA ROSINE", t, doc)

    def test_04_griffe_desactivee(self):
        with app.app_context():
            from app import ex
            ex("UPDATE ecoles SET griffe_actif=0 WHERE id=1")
        try:
            t = texte_pdf(self.get(f"/eleves/{self.el}/document/certificat_frequentation.pdf").data)
            self.assertNotIn("DAGBA ROSINE", t)
            self.assertIn("DAGBA Rosine", t)
            r = self.get("/ecoles/1/griffe.svg?nom=DAGBA+Rosine")   # l'aperçu du formulaire reste disponible
            self.assertIn("DAGBA ROSINE", r.data.decode())
        finally:
            with app.app_context():
                from app import ex
                ex("UPDATE ecoles SET griffe_actif=1 WHERE id=1")


@unittest.skipIf(pdfplumber is None, "pdfplumber absent")
class TestCS(unittest.TestCase):
    """Édition CS : page Cachets et signatures (griffe), aperçu SVG, document avec NIP et griffe du responsable."""

    @classmethod
    def setUpClass(cls):
        if not EN_PLACE or EDITION != "cs":
            raise unittest.SkipTest(f"édition « {config.EDITION} » chargée : suite rejouée en sous-processus")
        app.config["TESTING"] = True
        import demo_juridiction
        demo_juridiction.main()
        with app.app_context():
            from app import ex
            ex("INSERT OR REPLACE INTO signatures (cle, image, maj) VALUES (?,?,?)",
               ("jur:structure:responsable", signature_png(), "2026-01-01 00:00:00"))
        cls.c = app.test_client()
        r = cls.c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"})
        assert r.status_code == 302, r.status_code

    def get(self, url, code=200):
        r = self.c.get(url)
        self.assertEqual(r.status_code, code, f"{url} → {r.status_code}\n{r.data[:300]}")
        return r

    def test_01_page_cachets_et_griffe(self):
        h = txt(self.get("/juridiction/cachets"))
        self.assertIn('name="griffe_actif"', h)
        self.assertIn("griffe.svg", h)
        r = self.c.post("/juridiction/cachets", data={"cible": "structure", "sup": "", "inf": "", "centre": "",
                                                     "couleur": "bleu", "griffe_actif": "1",
                                                     "griffe_ligne3": "Inspecteur de l'Enseignement Primaire",
                                                     "griffe_couleur": "rouge"})
        self.assertEqual(r.status_code, 302)
        with app.test_request_context("/"):
            from notif import H
            import a_structure as AS
            reg = AS.jur_griffe_reglages(None)
            self.assertEqual(reg["actif"], 1)
            self.assertEqual(reg["couleur"], "rouge")
            gr = H.jur_griffe(None)
            self.assertIsNotNone(gr)
            self.assertEqual(gr[1], "rouge")
            self.assertEqual(gr[0][0], "Le Chef de la Circonscription Scolaire")
            self.nom = gr[0][1]
        r = self.get("/juridiction/cachets/griffe.svg")
        s = html_mod.unescape(r.data.decode())
        self.assertIn("LE CHEF DE LA CIRCONSCRIPTION SCOLAIRE", s)
        self.assertIn(self.nom.upper(), s)
        self.assertIn("INSPECTEUR DE L'ENSEIGNEMENT PRIMAIRE", s)
        self.assertIn(cachet.COULEURS["rouge"], s)
        self.assertTrue(self.get("/juridiction/cachets?export=pdf").data.startswith(b"%PDF"))
        # désactivation puis réactivation
        self.c.post("/juridiction/cachets", data={"cible": "structure", "sup": "", "inf": "", "centre": "",
                                                 "couleur": "bleu", "griffe_ligne3": "", "griffe_couleur": ""})
        with app.test_request_context("/"):
            from notif import H
            self.assertIsNone(H.jur_griffe(None))
        self.c.post("/juridiction/cachets", data={"cible": "structure", "sup": "", "inf": "", "centre": "",
                                                 "couleur": "bleu", "griffe_actif": "1", "griffe_ligne3": "",
                                                 "griffe_couleur": ""})

    def test_02_document_nip_et_griffe(self):
        h = txt(self.get("/juridiction/documents/presence_poste"))
        cles = re.findall(r'<option value="(e\d+-\d+|a\d+)"', h)
        self.assertTrue(cles)
        h = txt(self.get(f"/juridiction/documents/presence_poste?p={cles[0]}"))
        self.assertLess(h.find('name="nip"'), h.find('name="nom_prenoms"'))
        champs = champs_formulaire(h)
        champs.update(p=cles[0], civilite="Mr", signer="1", action="enregistrer", nip=champs.get("nip") or "NIP-CS-99",
                      suivant="")
        r = self.c.post("/juridiction/documents/presence_poste/pdf", data=champs)
        self.assertEqual(r.status_code, 200, r.data[:300])
        t = texte_pdf(r.data)
        self.assertIn("NIP", t)
        self.assertIn(champs["nip"], t)
        self.assertLess(t.find("NIP"), t.find(champs["nom_prenoms"]), "la ligne NIP précède la ligne du nom")
        self.assertIn(champs["signataire_nom"].upper(), t, "griffe du responsable (nom en majuscules)")
        t = texte_pdf(self.get("/juridiction/documents/presence_poste/vierge.pdf").data)
        self.assertIn("NIP", t)
        t = texte_pdf(self.get("/juridiction/documents/ame_prise_service/vierge.pdf").data)
        self.assertIn("NIP", t)


class TestEditionsSeparees(unittest.TestCase):
    """Rejoue dans un sous-processus la partie dont l'édition n'est pas chargée dans ce processus."""

    def test_publique(self):
        if EN_PLACE and EDITION == "publique":
            self.skipTest("déjà exécutée dans ce processus")
        r = _rejouer("publique", "TestEcolePublique")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])

    def test_cs(self):
        if EN_PLACE and EDITION == "cs":
            self.skipTest("déjà exécutée dans ce processus")
        r = _rejouer("cs", "TestCS")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])


if __name__ == "__main__":
    unittest.main()
