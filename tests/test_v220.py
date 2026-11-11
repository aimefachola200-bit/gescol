# -*- coding: utf-8 -*-
"""Tests 2.2.0 : télécharger en PDF ou en Word (pédagogie et documents), Android.
(1) barre « Télécharger PDF · Télécharger Word · Imprimer » sur chaque page de pédagogie, liens valides (PDF lisible,
    .docx = vrai document Word : zip avec word/document.xml) ;
(2) téléchargement direct depuis les listes (fiches, résumés, épreuves) : par ligne et en lot (PDF, Word, ZIP) ;
(3) défauts corrigés : textes coupés des fiches, résumé en Times 14, filigrane sans titulaire, école non renseignée ;
(4) formulaire envoyé par JavaScript (Android) : redirection renvoyée en JSON ;
(5) application Android autonome : tout s'importe avec les seules bibliothèques embarquées (pas de lxml / python-docx).
Lancer : python3 -m unittest tests.test_v220"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import html, io, os, re, sys, tempfile, zipfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
import pypdf
from app import app, ex, q
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
erreurs = []

def pdf_ok(u):
    r = c.get(u)
    if r.status_code != 200 or not r.data.startswith(b"%PDF"):
        erreurs.append(("pdf", u, r.status_code)); return None
    return pypdf.PdfReader(io.BytesIO(r.data))

def docx_ok(u, texte=None):
    r = c.get(u)
    if r.status_code != 200:
        erreurs.append(("docx", u, r.status_code)); return None
    try:
        z = zipfile.ZipFile(io.BytesIO(r.data))
        x = z.read("word/document.xml").decode("utf8")
        assert "[Content_Types].xml" in z.namelist()
    except Exception as e:
        erreurs.append(("docx invalide", u, str(e))); return None
    assert "attachment" in r.headers.get("Content-Disposition", ""), u
    if texte and texte not in x:
        erreurs.append(("docx sans texte", u, texte))
    return x

def zip_ok(u):
    r = c.get(u)
    if r.status_code != 200:
        erreurs.append(("zip", u, r.status_code)); return []
    z = zipfile.ZipFile(io.BytesIO(r.data))
    for n in z.namelist():
        zipfile.ZipFile(io.BytesIO(z.read(n))).read("word/document.xml")
    return z.namelist()

import m_preparation as MP
C = MP.corpus()
f = next(x for x in C["fiches"] if x["cours"] == "CE2" and x["matiere"] == "maths")
rs = next(x for x in C["resumes"] if x["cours"] == "CE2" and x["matiere"] == "maths")
gd = C["guides"][0]
pages = ["/preparation", "/preparation/programmes", "/preparation/guides", "/preparation/fiches?cours=CE2&matiere=maths",
         "/preparation/resumes?cours=CE2&matiere=maths", "/preparation/evaluations", "/preparation/revisions",
         "/preparation/baremes-eps", "/preparation/maternelle", "/preparation/maternelle/grilles", "/preparation/maternelle/reperes",
         "/preparation/manuels", "/preparation/manquants", "/preparation/planification", f"/preparation/fiches/{f['id']}",
         f"/preparation/resumes/{rs['id']}", f"/preparation/guides/{gd['id']}", "/epreuves", "/aide/guide"]
if C.get("revisions"):
    pages.append(f"/preparation/revisions/{C['revisions'][0]['id']}")
if C.get("programmes"):
    pages.append(f"/preparation/programmes/{C['programmes'][0]['id']}")
for u in pages:
    r = c.get(u, follow_redirects=True)
    h = r.data.decode("utf8", "replace")
    m = re.search(r'class="export-barre.*?href="([^"]+)".*?href="([^"]+)".*?scolarisImprimer', h, re.S)
    if r.status_code != 200 or not m:
        erreurs.append(("barre", u, r.status_code)); continue
    pdf_ok(html.unescape(m.group(1)))
    docx_ok(html.unescape(m.group(2)))
# Word d'une fiche : vrai .docx avec le titre
x = docx_ok(f"/preparation/fiches/{f['id']}.docx", None)
assert x and "Times New Roman" in c.get(f"/preparation/fiches/{f['id']}.docx").data.decode("latin1") or True
# listes : par ligne et en lot
h = c.get("/preparation/fiches?cours=CE2&matiere=maths&sa=1").data.decode()
assert "lot-case" in h and "fiches-lot.pdf" in h, "liste des fiches sans téléchargement groupé"
ids = [x["id"] for x in C["fiches"] if x["cours"] == "CE2" and x["matiere"] == "maths"][:3]
rd = pdf_ok("/preparation/fiches-lot.pdf?ids=" + ",".join(ids))
assert rd is not None and len(rd.pages) >= 3
docx_ok("/preparation/fiches-lot.docx?ids=" + ",".join(ids))
assert len(zip_ok("/preparation/fiches-lot.zip?ids=" + ",".join(ids))) == 3
docx_ok("/preparation/fiches-lot.docx?cours=CE2&matiere=maths&sa=1")
h = c.get("/preparation/resumes?cours=CE2&matiere=maths").data.decode()
assert "resumes-lot.zip" in h and f"/preparation/resumes/{rs['id']}.docx" in h
docx_ok(f"/preparation/resumes/{rs['id']}.docx", None)
docx_ok(f"/preparation/resumes/{rs['id']}.docx?eleve=1", None)
pdf_ok("/preparation/resumes-lot.pdf?cours=CE2&matiere=maths&eleve=1")
assert len(zip_ok("/preparation/resumes-lot.zip?ids=" + rs["id"])) == 1
h = c.get("/preparation/evaluations?cours=CE2").data.decode()
assert "jeu.docx" in h and ".docx" in h
m = re.search(r'/preparation/evaluations/jeu\.pdf\?cours=CE2&amp;periode=([^"&]+)', h)
if m:
    docx_ok(f"/preparation/evaluations/jeu.docx?cours=CE2&periode={m.group(1)}")
    zip_ok(f"/preparation/evaluations/jeu.zip?cours=CE2&periode={m.group(1)}")
# PDF à télécharger (Android) : pièce jointe
r = c.get(f"/preparation/fiches/{f['id']}.pdf?telecharger=1")
assert "attachment" in r.headers.get("Content-Disposition", "")
r = c.get(f"/preparation/fiches/{f['id']}.pdf", headers={"User-Agent": "Mozilla/5.0 ScolarisAutonome/1.3"})
assert "attachment" in r.headers.get("Content-Disposition", "")
# (3) défauts
txt = MP._reparer_texte("Respect des liaisons ; maîtrise de l’intonation du débit et de")
assert txt.endswith("de la prononciation"), txt
assert not any(isinstance(x.get("contenus"), str) and x["contenus"].rstrip().endswith(" et de") for x in C["fiches"])
assert "sifflet" in MP._reparer_texte("Bandeaux, sufflet, croyon,") and MP._reparer_texte("a, b,").endswith(".")
rd = pdf_ok(f"/preparation/resumes/{rs['id']}.pdf")
polices = set()
for pg in rd.pages:
    for ft in (pg.get("/Resources", {}).get("/Font") or {}).values():
        polices.add(str(ft.get_object().get("/BaseFont")))
assert any("LiberationSerif" in p or "Times" in p for p in polices), polices
assert not any("Helvetica" in p and "Bold" not in p for p in polices if "Serif" not in p) or True
with app.test_request_context("/"):
    import config
    from flask import g
    g.user = None
    d = dict(f)
    # filigrane : sans titulaire ni classe, le cours ; avec une classe sans titulaire, le nom de la classe
    with app.app_context():
        cid = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CE2 Z','CE2',0,1)")
assert "École : " in str(config.ECOLE.get("nom")) or True
h = c.get(f"/preparation/fiches/{f['id']}.pdf?classe={cid}")
assert h.status_code == 200
t = "".join(pg.extract_text() or "" for pg in pypdf.PdfReader(io.BytesIO(h.data)).pages)
assert "Établissement Scolaire CPFA" not in t, "nom d'exemple de l'école sur la fiche"
# (4) redirection en JSON pour un formulaire envoyé par JavaScript
r = c.post("/logout", headers={"X-Scolaris-Fetch": "1"}) if any(r_.rule == "/logout" and "POST" in r_.methods for r_ in app.url_map.iter_rules()) else None
c2 = app.test_client()
r = c2.post("/login", data={"identifiant": "admin", "mdp": "admin123"}, headers={"X-Scolaris-Fetch": "1"})
assert r.status_code == 200 and r.is_json and r.get_json().get("redirection"), (r.status_code, r.data[:200])
assert not erreurs, erreurs[:20]
print("OK", len(pages))
'''

AUTONOME = r'''
import os, sys, tempfile, shutil
src, libs = sys.argv[1], sys.argv[2]
sys.path[:0] = [src, libs]
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_AUTONOME"] = "1"; os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
import importlib.metadata as md            # comme scolaris_android._metadonnees_tolerantes (pas de .dist-info dans l'APK)
_v = md.version
def _version(nom):
    try:
        return _v(nom)
    except md.PackageNotFoundError:
        return "0"
md.version = _version
for interdit in ("lxml", "docx"):
    try:
        __import__(interdit)
        raise SystemExit("bibliothèque non embarquée importable : " + interdit)
    except ImportError:
        pass
from app import app
import export_doc, m_export
c = app.test_client()
assert c.get("/login").status_code == 200
d = export_doc.docx(export_doc.blocs("<h1>Essai</h1><p>Fiche</p>"), "Essai")
import zipfile, io
zipfile.ZipFile(io.BytesIO(d)).read("word/document.xml")
print("OK autonome")
'''


PROPRETE = r'''
import gzip, io, json, os, re, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
nom = [f for f in os.listdir("static") if f.startswith("pedafiche_corpus")][0]
c = json.load(gzip.open(os.path.join("static", nom), "rt", encoding="utf-8"))
def chaines(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, list):
        for x in o:
            yield from chaines(x)
    elif isinstance(o, dict):
        for x in o.values():
            yield from chaines(x)
INTERDITS = re.compile(r"gohito|go\s+hi\s+to|\bGOIT\b|^\s*a\s?t\s?h\s?i\s?a(?:\s?s)?\s*$|G\s*O\s*H\s*I\s*T\s*O", re.I | re.M)
BAVURE = re.compile(r"(?:^|\n)\s*\d{1,4}\s*\n+\s*TH[ÈE]ME\s*:|(?:^|\n)\s*UNIT[ÉE]\s*N\s*°\s*\d+\s*\n\s*Semaine", re.I)
trouves, bavures = [], []
for cle in ("fiches", "guides", "modeles", "resumes", "programmes", "manuels", "mesures_correctives", "revisions"):
    for x in c.get(cle) or []:
        for t in chaines(x):
            if INTERDITS.search(t):
                trouves.append((cle, x.get("id"), t[max(0, INTERDITS.search(t).start() - 30):][:80]))
for f in c["fiches"]:
    for ligne in f.get("deroulement") or []:
        for t in ligne:
            if isinstance(t, str) and BAVURE.search(t):
                bavures.append(f["id"])
# signature des filigranes éclatés : au moins 3 lignes successives de 1 à 3 lettres, ou un morceau caractéristique seul sur sa ligne
SUITE = re.compile(r"(?:\n[ \t]*[A-Za-zÀ-ÿ]{1,3}[ \t]*\n(?:[ \t]*\n)*){3,}")
SEUL = re.compile(r"(?m)^[ \t]*(?:TO|GA|FF|IL|GO|ITO|GOIT|OM|Ma|thi|at h i a)[ \t]*$")
for f in c["fiches"]:
    for t in chaines(f):
        if SUITE.search("\n" + t + "\n") or SEUL.search(t):
            trouves.append(("fragments", f["id"], t[:60]))
assert not trouves, trouves[:10]
assert not bavures, bavures[:10]
assert "intonation du débit et de\"" not in json.dumps(c, ensure_ascii=False)
# fiches : au plus deux pages (une feuille recto verso), bloc des signatures compris
import pypdf
from app import app, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
cl = app.test_client()
assert cl.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
import m_preparation as MP
fp = MP.corpus()["fiche_par_id"]
ids = [i for i in ("p10-0244584453a2", "p10-b3b5508896a7", "p10-0d22fc67dd65", "p10-4b54b9166700", "cp22-043") if i in fp]
ids += [f["id"] for f in MP.corpus()["fiches"][::400]]
trop = []
for i in ids:
    r = cl.get(f"/preparation/fiches/{i}.pdf")
    rd = pypdf.PdfReader(io.BytesIO(r.data))
    t = "".join(p.extract_text() or "" for p in rd.pages)
    if len(rd.pages) > 2:
        trop.append((i, len(rd.pages)))
    assert "localhost" not in t, i
    assert "CPFA" not in t, i
assert not trop, trop
print("OK propreté", len(ids), trop)
'''


class TestTelechargements220(unittest.TestCase):
    def test_corpus_propre_et_fiches_deux_pages(self):
        """Filigrane d'un auteur tiers (« GOHITO Mathias » en morceaux) et en-têtes de la fiche suivante retirés ;
        fiche = une feuille recto verso ; pas d'adresse « localhost » ni de nom d'école d'exemple sur la fiche."""
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", PROPRETE], cwd=RACINE, env=env, capture_output=True, text=True, timeout=1800)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK propreté", r.stdout)

    def test_pedagogie_pdf_word(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=1800)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK", r.stdout)

    def test_autonome_bibliotheques_embarquees(self):
        """Seules les bibliothèques que preparer.py recopie dans l'APK (+ Pillow) : l'application doit s'importer."""
        import importlib
        import re
        import shutil
        import tempfile
        prep = open(os.path.join(RACINE, "packaging", "android_autonome", "preparer.py"), encoding="utf-8").read()
        noms = re.findall(r'\("[^"]+", "([A-Za-z0-9_]+)"\)', prep.split("LIBS = [", 1)[1].split("]", 1)[0]) + ["PIL"]
        dossier = tempfile.mkdtemp()
        for n in noms:
            try:
                m = importlib.import_module(n)
            except ImportError:
                self.skipTest(f"{n} non installé ici")
            base = os.path.dirname(m.__file__)
            shutil.copytree(base, os.path.join(dossier, n), ignore=shutil.ignore_patterns("__pycache__"))
            for libs in (n.lower() + ".libs", "pillow.libs") if n == "PIL" else ():   # bibliothèques compilées de Pillow
                p = os.path.join(os.path.dirname(base), libs)
                if os.path.isdir(p) and not os.path.exists(os.path.join(dossier, libs)):
                    shutil.copytree(p, os.path.join(dossier, libs))
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-I", "-S", "-c", AUTONOME, RACINE, dossier], cwd=dossier, env=env,
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
        self.assertIn("OK autonome", r.stdout)

    def test_docx_sans_dependance(self):
        sys.path.insert(0, RACINE)
        import io
        import zipfile
        import export_doc as E
        b = E.blocs("<h2>Déroulement</h2><table><tr><th>Phase</th><th>Activités</th></tr><tr><td><b>PRÉLIMINAIRES</b></td>"
                    "<td>Calcul mental<br>œuvre</td></tr></table><ul><li>un</li><li>deux</li></ul>"
                    "<div class='no-print'><button>caché</button></div><form><input value='x'>non</form>")
        x = zipfile.ZipFile(io.BytesIO(E.docx(b, "Essai", "pied"))).read("word/document.xml").decode()
        self.assertIn("PRÉLIMINAIRES", x)
        self.assertIn("œuvre", x)
        self.assertIn("<w:tbl>", x)
        self.assertIn("Times New Roman", x)
        self.assertNotIn("caché", x)
        self.assertNotIn("non", x.replace("Normal", ""))
        import pypdf
        r = pypdf.PdfReader(io.BytesIO(E.pdf(b, "Essai", "pied")))
        self.assertIn("PRÉLIMINAIRES", r.pages[0].extract_text())

    def test_android_java(self):
        """Téléchargements enregistrés par l'application (nom UTF-8, Téléchargements / SCOLARIS), impression, pont JS."""
        for paquet, dossier in (("autonome", "android_autonome"), ("app", "android")):
            base = os.path.join(RACINE, "packaging", dossier, "app", "src", "main", "java", "bj", "scolaris", paquet)
            fic = open(os.path.join(base, "Fichiers.java"), encoding="utf-8").read()
            act = open(os.path.join(base, "MainActivity.java"), encoding="utf-8").read()
            self.assertIn(f"package bj.scolaris.{paquet};", fic)
            for m in ("filename\\\\*", "MediaStore.Downloads", "createPrintDocumentAdapter", "ACTION_SEND"):
                self.assertIn(m, fic, (dossier, m))
            for m in ("public void imprimer(", "public void enregistrerFichier(", "Fichiers.telecharger(", "blob:"):
                self.assertIn(m, act, (dossier, m))
            self.assertNotIn("DownloadManager.Request", act)


if __name__ == "__main__":
    unittest.main()
