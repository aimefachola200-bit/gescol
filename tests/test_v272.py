"""v2.7.2 : fiches officielles d'EPS CP (SA 10 à 13) dans la préparation de classe."""
import gzip, json, os

CORPUS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "pedafiche_corpus.json.gz")


def _eps_cp():
    c = json.load(gzip.open(CORPUS))
    return [f for f in c["fiches"] if f["cours"] == "CP" and f["matiere"] == "eps"]


def test_sa10_a_13_officielles():
    e = _eps_cp()
    for sa, n in (("10", 5), ("11", 5), ("12", 4), ("13", 5)):
        l = [f for f in e if str(f["sa"]) == sa]
        assert len(l) == n and all(f["statut"] == "source" for f in l)
        assert all(f["deroulement"] and len(f["deroulement"]) >= 5 for f in l)


def test_sa4_completee():
    seances = {f["seance"] for f in _eps_cp() if str(f["sa"]) == "4"}
    assert {1, 2, 3, 4, 5} <= seances


def test_banque_secondaire_via_dossier_web():
    """Android : la banque d'épreuves est cherchée dans le dossier web, pas à côté des modules."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "m_ressources_sec.py"), encoding="utf-8").read()
    assert "fichier_static" in src


def test_bouton_appliquer_maj():
    base = os.path.dirname(os.path.dirname(__file__))
    assert "maj_appliquer" in open(os.path.join(base, "maj_auto.py"), encoding="utf-8").read()
    assert 'id="maj-appliquer"' in open(os.path.join(base, "templates", "base.html"), encoding="utf-8").read()


def test_changer_identifiant():
    """Chaque utilisateur peut remplacer son identifiant de départ (mot de passe requis, unicité)."""
    import subprocess, sys
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pref = "GESCOL" if os.path.exists(os.path.join(racine, "GESCOL_PUBLIC.md")) else "SCOLARIS"
    script = r'''
import os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
c.post("/mon-compte", data={"action": "identifiant", "identifiant": "nouveau.nom", "mdp": "faux"})
c2 = app.test_client()
assert c2.post("/login", data={"identifiant": "nouveau.nom", "mdp": "admin123"}).status_code == 200
c.post("/mon-compte", data={"action": "identifiant", "identifiant": "Nouveau.Nom", "mdp": "admin123"})
c3 = app.test_client()
assert c3.post("/login", data={"identifiant": "nouveau.nom", "mdp": "admin123"}).status_code == 302
print("OK")
'''
    env = dict(os.environ, PREFIXE_SCRIPT=pref)
    r = subprocess.run([sys.executable, "-c", script], cwd=racine, env=env, capture_output=True, text=True, timeout=180)
    assert "OK" in r.stdout, r.stdout + r.stderr


def test_identifiant_parent_et_eleve():
    """Parents et élèves : identifiant de départ (téléphone / matricule) + identifiant personnel au choix."""
    import subprocess, sys
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pref = "GESCOL" if os.path.exists(os.path.join(racine, "GESCOL_PUBLIC.md")) else "SCOLARIS"
    script = r'''
import os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from werkzeug.security import generate_password_hash as gh
import config
app.config["TESTING"] = True
ctx = app.app_context(); ctx.push()
cl = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM1 T','CM1',50000,1)")
pid = ex("INSERT INTO parents (nom, telephone, mdp_hash, doit_changer_mdp, cree_le) VALUES ('P','22901970000',?,0,'2026-01-01')", (gh("secret1"),))
eid = ex("INSERT INTO eleves (nom, prenoms, sexe, date_naissance, classe_id, statut, matricule, date_inscription, annee, mdp_hash) VALUES ('K','A','F','2014-01-01',?, 'inscrit','MX9','2026-09-15',?,?)", (cl, config.ANNEE_ACTIVE, gh("secret2")))
ex("INSERT INTO comptes_eleves (eleve_id, doit_changer, actif) VALUES (?,0,1)", (eid,))
c = app.test_client(); assert c.post("/parent/connexion", data={"telephone": "01970000", "mdp": "secret1"}).status_code in (200, 302)
c = app.test_client(); c.post("/parent/connexion", data={"telephone": "0197000000", "mdp": "secret1"})
with c.session_transaction() as s: s["pid"] = pid
c.post("/parent/mot-de-passe", data={"action": "identifiant", "identifiant": "mama.ama", "mdp": "secret1"})
assert q("SELECT identifiant FROM parents WHERE id=?", (pid,))[0]["identifiant"] == "mama.ama"
c2 = app.test_client(); r = c2.post("/parent/connexion", data={"telephone": "Mama.Ama", "mdp": "secret1"}); assert r.status_code == 302, r.status_code
ce = app.test_client()
with ce.session_transaction() as s: s["eid_eleve"] = eid
ce.post("/eleve/mot-de-passe", data={"action": "identifiant", "identifiant": "ama.k", "mdp": "secret2"})
assert q("SELECT identifiant FROM eleves WHERE id=?", (eid,))[0]["identifiant"] == "ama.k"
c3 = app.test_client(); assert c3.post("/eleve/connexion", data={"identifiant": "AMA.K", "mdp": "secret2"}).status_code == 302
c4 = app.test_client(); assert c4.post("/eleve/connexion", data={"identifiant": "MX9", "mdp": "secret2"}).status_code == 302
print("OK")
'''
    env = dict(os.environ, PREFIXE_SCRIPT=pref)
    r = subprocess.run([sys.executable, "-c", script], cwd=racine, env=env, capture_output=True, text=True, timeout=180)
    assert "OK" in r.stdout, r.stdout + r.stderr[-1500:]


def test_ecritures_fiches():
    """Gras / italique / cursive dans les fiches : balises ajoutées, texte existant inchangé, PDF valide."""
    import sys
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, racine)
    import m_preparation as P
    assert P.txt_html("a **b** ^^c^^ ~~d~~") == 'a <b>b</b> <i>c</i> <i class="cursif">d</i>'
    assert P.txt_html("5*3 et http://x") == "5*3 et http://x"            # texte existant inchangé
    s = P.txt_pdf("a **b** ^^c^^ ~~d~~")
    assert "<b>b</b>" in s and "<i>c</i>" in s and ("d</font>" in s or "<i>d</i>" in s)
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    Paragraph(s, ParagraphStyle("x")).wrap(400, 100)                      # balisage accepté par reportlab
    for js in ("gescol.js", "scolaris.js"):
        f = os.path.join(racine, "static", js)
        if os.path.exists(f):
            assert "initEcriture" in open(f, encoding="utf-8").read()


def test_menage_garde_la_version_en_cours(tmp_path):
    """v2.7.4 : le ménage des mises à jour ne supprime jamais le dossier de la version en cours d'utilisation."""
    import sys
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, racine)
    import amorcage
    import config
    import maj_auto
    for v in ("1.0.0", config.VERSION, "9.9.9", "9.9.8"):
        (tmp_path / v / "web" / "templates").mkdir(parents=True)
        (tmp_path / v / "web" / "templates" / "login.html").write_text("x")
    amorcage._etat["actif"] = config.VERSION
    try:
        maj_auto.menage(str(tmp_path), "9.9.9")
    finally:
        amorcage._etat["actif"] = None
    assert (tmp_path / config.VERSION / "web" / "templates" / "login.html").exists()   # en cours : conservée
    assert (tmp_path / "9.9.9").exists()                                                 # nouvelle : conservée
    assert not (tmp_path / "1.0.0").exists() and not (tmp_path / "9.9.8").exists()      # anciennes : supprimées
