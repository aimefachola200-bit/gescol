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
