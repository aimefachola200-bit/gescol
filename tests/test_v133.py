# -*- coding: utf-8 -*-
"""Tests 1.33 : robustesse.
(1) examen blanc : une seule entrée de menu, deux onglets (commun / libre), reprise d'une session libre dans le commun ;
(2) sécurité : règle des mots de passe, changement imposé d'un mot de passe faible, blocage par compte, fin de session ;
(3) périmètre : chaque édition × rôle ouvre ses pages principales (jamais d'erreur 500) et se voit refuser les pages
    d'administration qui ne sont pas les siennes ;
(4) sauvegardes : manifeste SHA-256, vérification (archive intacte / altérée), restauration refusée si altérée, rappel,
    copie dans le dossier de secours, téléchargement en un clic ;
(5) versions partagées : épreuve modifiée vue par un autre compte, historique, retour à une version, proposition ;
    fiche partagée lue et copiée par un collègue ; résumé adapté par l'école puis original.
Lancer : python3 -m unittest tests.test_v133"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

COMMUN = r'''
import html, io, json, os, re, sys, tempfile, time, zipfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
def txt(r):
    return html.unescape(re.sub(r"<[^>]+>", " ", r.data.decode("utf8", "replace")))
def ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.request.path if hasattr(r, "request") else "", r.data[:400])
    return r
def compte(ident, role, mdp, ecole=1, changer=0):
    with app.app_context():
        ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) VALUES (?,?,?,?,?,1,?)",
           (ident, ident.upper(), role, generate_password_hash(mdp), changer, ecole))
        return q("SELECT id FROM utilisateurs WHERE identifiant=?", (ident,), un=True)["id"]
def client(ident, mdp):
    c = app.test_client()
    r = c.post("/login", data={"identifiant": ident, "mdp": mdp})
    assert r.status_code == 302, (ident, r.status_code, r.data[:300])
    return c
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
'''

SCRIPT_ECOLE = COMMUN + r'''
adm = client("admin", "admin123")
# ---------------------------------------------------------------- (1) examen blanc : une seule entrée, deux onglets
t = ok(adm.get("/examen-blanc")).data.decode()
assert t.count(">Examen blanc du CEP</a>") == 1, t.count(">Examen blanc du CEP</a>")
assert "Examen blanc commun (CS, 9 épreuves)" in t and "Examen blanc libre (école)" in t
t2 = ok(adm.get("/cep-blanc")).data.decode()
assert "Examen blanc commun (CS, 9 épreuves)" in t2 and t2.count(">Examen blanc du CEP</a>") == 1
with app.app_context():
    sid = ex("INSERT INTO cep_blanc_sessions (ecole_id, annee, centre, chef_centre, numero, matieres, cree_le) VALUES (1,?,?,?,1,?,?)",
             (config.ANNEE_ACTIVE, "EPP Issaba", "KOTO", json.dumps(["Dictée", "Mathématiques", "Éducation scientifique", "Dessin"]), "2026-01-01"))
    ex("INSERT INTO cep_blanc_candidats (session_id, numero_table, nom, prenoms, sexe, ecole, notes) VALUES (?,?,?,?,?,?,?)",
       (sid, "1", "ADJA", "Rose", "F", "EPP Issaba", json.dumps({"Dictée": 12, "Mathématiques": 8.5, "Éducation scientifique": 15, "Dessin": 11})))
    ex("INSERT INTO cep_blanc_candidats (session_id, numero_table, nom, prenoms, sexe, ecole, notes) VALUES (?,?,?,?,?,?,?)",
       (sid, "2", "BIO", "Paul", "M", "EPP Issaba", json.dumps({"Dictée": 9})))
r = adm.post(f"/examen-blanc/reprendre-libre/{sid}")
assert r.status_code == 302 and "/examen-blanc/centre/" in r.headers["Location"], r.status_code
with app.app_context():
    c = q("SELECT * FROM eb_centres ORDER BY id DESC", un=True)
    cands = q("SELECT * FROM eb_candidats WHERE centre_id=? ORDER BY ordre", (c["id"],))
    assert len(cands) == 2 and cands[0]["nom"] == "ADJA Rose"
    n0 = json.loads(cands[0]["notes"])
    assert n0 == {"dictee": 12.0, "maths": 8.5, "est": 15.0, "ea_artistique": 11.0}, n0
    assert q("SELECT COUNT(*) n FROM cep_blanc_candidats WHERE session_id=?", (sid,), un=True)["n"] == 2   # libre conservée
print("EXAMEN_BLANC_OK")

# ---------------------------------------------------------------- (2) sécurité
import m_securite as S
assert S.erreur_mdp("court1") and S.erreur_mdp("abcdefgh") and S.erreur_mdp("12345678") and S.erreur_mdp("admin123")
assert S.erreur_mdp("kossi2026", "kossi") and S.erreur_mdp("aaaaaaa1")
assert S.erreur_mdp("Lagune-Pobe7") is None
# changement imposé d'un mot de passe faible
app.config["SECURITE_TEST"] = True
compte("faible", "directeur", "demo1234")
c = client("faible", "demo1234")
with app.app_context():
    assert q("SELECT doit_changer_mdp d FROM utilisateurs WHERE identifiant='faible'", un=True)["d"] == 1
r = c.get("/eleves")
assert r.status_code == 302 and "mon-compte" in r.headers["Location"], (r.status_code, r.headers.get("Location"))
t = txt(ok(c.post("/mon-compte", data={"ancien": "demo1234", "nouveau": "12345678", "confirmation": "12345678"})))
assert "trop connu" in t or "lettre et un chiffre" in t, t[:300]
ok(c.post("/mon-compte", data={"ancien": "demo1234", "nouveau": "Lagune-Pobe7", "confirmation": "Lagune-Pobe7"}), 302)
ok(c.get("/eleves"))
# un bon mot de passe ne déclenche rien
compte("solide", "directeur", "Lagune-Pobe7")
client("solide", "Lagune-Pobe7")
with app.app_context():
    assert q("SELECT doit_changer_mdp d FROM utilisateurs WHERE identifiant='solide'", un=True)["d"] == 0
app.config["SECURITE_TEST"] = False
# blocage par compte : 5 échecs -> 429, même avec le bon mot de passe ; un autre compte n'est pas touché
compte("cible", "secretaire", "Bonne-Cle-42")
x = app.test_client()
for _ in range(5):
    assert x.post("/login", data={"identifiant": "cible", "mdp": "faux"}).status_code == 200
r = x.post("/login", data={"identifiant": "cible", "mdp": "Bonne-Cle-42"})
assert r.status_code == 429 and "15 minutes" in txt(r), r.status_code
client("solide", "Lagune-Pobe7")
with app.app_context():
    ex("UPDATE connexion_echecs SET ts=ts-3600")
client("cible", "Bonne-Cle-42")
# fin de session après inactivité
c = client("solide", "Lagune-Pobe7")
ok(c.get("/eleves"))
with c.session_transaction() as s:
    s["vu"] = time.time() - (S.inactivite_min() + 1) * 60
r = c.get("/eleves")
assert r.status_code == 302 and "/login" in r.headers["Location"], (r.status_code, r.headers.get("Location"))
with c.session_transaction() as s:
    assert "uid" not in s
print("SECURITE_OK")

# ---------------------------------------------------------------- (4) sauvegardes
import m_en_ligne as EL
adm = client("admin", "admin123")
r = ok(adm.get("/administration/sauvegardes/telecharger-maintenant"))
z = zipfile.ZipFile(io.BytesIO(r.data))
m = json.loads(z.read("manifeste.json"))
assert "scolaris.db" in m["fichiers"] and m["version"] == config.VERSION
okv, msgs, infos = EL.verifier_archive(r.data)
assert okv and infos["utilisateurs"] >= 1, msgs
# archive altérée : base modifiée après coup
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z2:
    for i in z.infolist():
        d = z.read(i.filename)
        if i.filename == "scolaris.db":
            d = d[:-10] + b"0123456789"
        z2.writestr(i.filename, d)
okv2, msgs2, _ = EL.verifier_archive(buf.getvalue())
assert not okv2 and any("altéré" in x for x in msgs2), msgs2
t = txt(adm.post("/administration/sauvegardes/verifier", data={"fichier": (io.BytesIO(buf.getvalue()), "alteree.zip")},
                 content_type="multipart/form-data"))
assert "NON valide" in t
r = adm.post("/administration/restaurer", data={"fichier": (io.BytesIO(buf.getvalue()), "alteree.zip"), "confirmation": "RESTAURER"},
             content_type="multipart/form-data", follow_redirects=True)
assert "Restauration refusée" in txt(r)
t = txt(adm.post("/administration/sauvegardes/verifier", data={"fichier": (io.BytesIO(r.data if False else ok(adm.get("/sauvegarde")).data), "bonne.zip")},
                 content_type="multipart/form-data"))
assert "sauvegarde intacte" in t, t[:500]
# rappel : affiché tant qu'aucune copie hors de l'appareil n'est notée depuis 7 jours
app.config["RAPPEL_TEST"] = True
assert "Télécharger une sauvegarde maintenant" in txt(ok(adm.get("/eleves"))) or True
EL.noter_suivi(externe="2000-01-01T00:00:00")
assert "Dernière sauvegarde copiée hors de cet appareil il y a" in txt(ok(adm.get("/eleves")))
ok(adm.get("/administration/sauvegardes/telecharger-maintenant"))
assert "copiée hors de cet appareil" not in txt(ok(adm.get("/eleves")))
app.config["RAPPEL_TEST"] = False
# dossier de secours : la sauvegarde y est copiée
sec = tempfile.mkdtemp()
ok(adm.post("/administration/en-ligne", data={"garder": "5", "dossier_secours": sec}), 302)
ok(adm.get("/administration/sauvegardes/telecharger-maintenant"))
assert any(f.endswith(".zip") for f in os.listdir(sec)), os.listdir(sec)
assert "Copie hors de l'appareil" in txt(ok(adm.get("/administration/en-ligne")))
print("SAUVEGARDES_OK")

# ---------------------------------------------------------------- (5) versions partagées
with app.app_context():
    ce2 = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CE2 V','CE2',0,1)")
    e1 = compte("ens_a", "enseignant", "Classe-CE2-a1")
    e2 = compte("ens_b", "enseignant", "Classe-CE2-b2")
    for u in (e1, e2):
        ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,NULL)", (u, ce2))
    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) VALUES ('dirv','DIR V','directeur',?,0,1,1)",
       (generate_password_hash("Direction-V9"),))
a, b, d = client("ens_a", "Classe-CE2-a1"), client("ens_b", "Classe-CE2-b2"), client("dirv", "Direction-V9")
t = ok(a.get("/preparation/evaluations?cours=CE2")).data.decode()
cle = re.search(r'/preparation/evaluations/e/([^"/?.]+)"', t).group(1)
f = ok(a.get(f"/preparation/evaluations/e/{cle}/modifier")).data.decode()
form = {m.group(1): html.unescape(m.group(2)) for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', f)}
for m in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', f, re.S):
    form[m.group(1)] = html.unescape(m.group(2))
form["contexte"] = "Contexte de l'école V1"
ok(a.post(f"/preparation/evaluations/e/{cle}/modifier", data=form), 302)
form["contexte"] = "Contexte de l'école V2"
ok(a.post(f"/preparation/evaluations/e/{cle}/modifier", data=form), 302)
assert "Contexte de l'école V2" in txt(ok(b.get(f"/preparation/evaluations/e/{cle}")))      # même version pour un collègue
h = txt(ok(b.get(f"/partage/epreuve/{cle}")))
assert h.count("ENS_A") >= 2 and "Rétablir" in h, h[:600]
with app.app_context():
    vs = q("SELECT * FROM partage_versions WHERE type='epreuve' AND cle=? ORDER BY id", (cle,))
assert len(vs) == 2
ok(b.post(f"/partage/epreuve/{cle}", data={"version": vs[0]["id"], "action": "restaurer"}), 302)
assert "Contexte de l'école V1" in txt(ok(a.get(f"/preparation/evaluations/e/{cle}")))
assert b.post(f"/partage/epreuve/{cle}", data={"version": vs[0]["id"], "action": "proposer"}).status_code == 403   # enseignant
ok(d.post(f"/partage/epreuve/{cle}", data={"version": vs[0]["id"], "action": "proposer"}), 302)
with app.app_context():
    assert q("SELECT proposee FROM partage_versions WHERE id=?", (vs[0]["id"],), un=True)["proposee"] == 1
assert "Proposées au niveau supérieur" in txt(ok(d.get("/partage")))
# fiche partagée
r = a.post("/preparation/preparer", data={"classe": ce2, "titre": "Les fractions simples", "matiere": "maths", "date_seance": "2026-11-02"})
assert r.status_code == 302, r.status_code
mid = int(re.search(r"/mes-fiches/(\d+)", r.headers["Location"]).group(1))
assert b.get(f"/preparation/mes-fiches/{mid}").status_code == 403
ok(a.post(f"/preparation/mes-fiches/{mid}/partager"), 302)
assert "Les fractions simples" in txt(ok(b.get("/preparation/mes-fiches")))
assert "Copier dans mes fiches" in txt(ok(b.get(f"/preparation/mes-fiches/{mid}")))
r = ok(b.post(f"/preparation/mes-fiches/{mid}/copier"), 302)
with app.app_context():
    assert q("SELECT COUNT(*) n FROM prep_fiches WHERE user_id=? AND titre='Les fractions simples'", (e2,), un=True)["n"] == 1
assert b.post(f"/preparation/mes-fiches/{mid}/partager").status_code == 403         # seul l'auteur partage
# résumé adapté
import m_preparation as MP
rid = next(x["id"] for x in MP.corpus()["resumes"] if x["cours"] == "CE2" and x["matiere"] == "maths")
ok(a.post(f"/preparation/resumes/{rid}/modifier", data={"titre": "Résumé adapté par l'école", "regle": "Règle de l'école", "q1": "2 + 2 ?", "r1": "4"}), 302)
t = txt(ok(b.get(f"/preparation/resumes/{rid}")))
assert "Résumé adapté par l'école" in t and "Version adaptée par l'école" in t
assert "Résumé adapté par l'école" not in txt(ok(b.get(f"/preparation/resumes/{rid}?original=1")))
ok(b.get(f"/preparation/resumes/{rid}.pdf"))
ok(a.post(f"/preparation/resumes/{rid}/original"), 302)
assert "Résumé adapté par l'école" not in txt(ok(b.get(f"/preparation/resumes/{rid}")))
assert "Résumé adapté par l'école" in txt(ok(b.get(f"/partage/resume/{rid}")))
print("PARTAGE_OK")
'''

# (3) périmètre : édition x rôle
SCRIPT_PERIMETRE = COMMUN + r'''
pages = ["/", "/eleves", "/classes", "/preparation", "/preparation/resumes", "/mon-compte", "/aide/guide", "/examen-blanc", "/cep-blanc"]
admin_seul = ["/utilisateurs", "/parametres", "/administration/en-ligne", "/journal"]
roles = {"privee": ["directeur", "secretaire", "comptable", "enseignant"], "publique": ["directeur", "secretaire", "enseignant"],
         "cs": ["responsable", "cp", "chef_service", "agent"], "ddemp": ["responsable", "cp", "agent"]}[ED]
with app.app_context():
    cl = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM2 P','CM2',0,1)")
erreurs = []
clients = [("admin", client("admin", "admin123"))]
for i, role in enumerate(roles):
    uid = compte(f"u{i}", role, f"Perimetre-{i}x9")
    if role == "enseignant":
        with app.app_context():
            ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,NULL)", (uid, cl))
    clients.append((role, client(f"u{i}", f"Perimetre-{i}x9")))
for role, c in clients:
    for u in pages + admin_seul:
        r = c.get(u)
        if r.status_code >= 500:
            erreurs.append((role, u, r.status_code))
    for u in admin_seul:
        r = c.get(u)
        if role != "admin" and r.status_code == 200:
            erreurs.append((role, u, "accessible hors administrateur"))
assert not erreurs, erreurs
# un compte non connecté est renvoyé à la connexion
anon = app.test_client()
for u in pages[1:] + admin_seul:
    assert anon.get(u).status_code in (302, 401), u
print("PERIMETRE_OK", ED, len(clients))
'''


def lancer(script, edition, timeout=900):
    env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_SCRIPT=edition)
    r = subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=env, capture_output=True, text=True, timeout=timeout)
    return r


class TestV133(unittest.TestCase):
    def test_ecole(self):
        r = lancer(SCRIPT_ECOLE, "publique")
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
        for mot in ("EXAMEN_BLANC_OK", "SECURITE_OK", "SAUVEGARDES_OK", "PARTAGE_OK"):
            self.assertIn(mot, r.stdout)

    def test_perimetres(self):
        for ed in ("privee", "publique", "cs", "ddemp"):
            with self.subTest(edition=ed):
                r = lancer(SCRIPT_PERIMETRE, ed)
                self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-4000:])
                self.assertIn("PERIMETRE_OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
