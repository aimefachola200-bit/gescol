# -*- coding: utf-8 -*-
"""v2.7 : exposés par cours (professeur propose, élèves en groupe rédigent, page de garde sans nom du concepteur)."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
SCRIPT = r'''
import io, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "sec_publique"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
    ex("INSERT INTO classes (nom, niveau) VALUES ('6e A','6ème')"); ex("INSERT INTO classes (nom, niveau) VALUES ('5e B','5ème')")
    ca = q("SELECT id FROM classes WHERE nom='6e A'")[0]["id"]; cb = q("SELECT id FROM classes WHERE nom='5e B'")[0]["id"]
    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash) VALUES ('prof1','KOUASSI Paul','enseignant',?)", (generate_password_hash("Prof#2026x"),))
    uid = q("SELECT id FROM utilisateurs WHERE identifiant='prof1'")[0]["id"]
    mm = q("SELECT id, nom FROM matieres WHERE cycle='secondaire' ORDER BY ordre LIMIT 1")[0]
    ex("INSERT INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,?)", (uid, ca, mm["id"]))
    ids = []
    for i, (n, p, cl) in enumerate([("ADJOVI", "Marie", ca), ("DOSSOU", "Jean", ca), ("HOUNKPE", "Rose", ca), ("AKPO", "Luc", cb)]):
        e = ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, date_inscription, annee, classe_id, statut, mdp_hash) VALUES (?,?,?,'F','2026-09-15','2026-2027',?,'inscrit',?)", (f"M{i}", n, p, cl, generate_password_hash("Elev#2026x")))
        ex("INSERT INTO comptes_eleves (eleve_id, actif, doit_changer) VALUES (?,1,0)", (e,)); ids.append(e)
ctx = app.app_context(); ctx.push()
pr = app.test_client(); pr.get("/login"); pr.post("/login", data={"identifiant": "prof1", "mdp": "Prof#2026x"})
assert pr.get(f"/ens-sec/expose/nouveau?cid={ca}&mid={mm['id']}").status_code == 200
assert pr.get(f"/ens-sec/expose/nouveau?cid={cb}").status_code in (403, 404, 302)
r = pr.post(f"/ens-sec/expose/nouveau?cid={ca}&mid={mm['id']}", data={"titre": "La décentralisation au Bénin", "matiere": mm["nom"], "axes": "Définition\nEnjeux", "remise": "2026-12-01", "taille_max": "2"})
assert r.status_code == 302, r.status_code
xid = q("SELECT id FROM exposes_sec")[0]["id"]
assert "La décentralisation" in pr.get(f"/ens-sec/expose/{xid}").get_data(as_text=True)
assert "La décentralisation" in pr.get(f"/ens-sec/cours/{ca}/{mm['id']}").get_data(as_text=True)

# thème de la bibliothèque développé
r = pr.post(f"/ens-sec/expose/nouveau?cid={ca}&mid={mm['id']}&theme=0&source=theme:0", data={"titre": "La condition de la femme", "matiere": "Français", "axes": "a", "taille_max": "3"})
x2 = q("SELECT id, source FROM exposes_sec ORDER BY id DESC LIMIT 1")[0]; assert x2["source"] == "theme:0", x2["source"]
import ressources_secondaire as RR
for i in range(len(RR.EXPOSES)):
    assert pr.get(f"/ressources-secondaire/expose/{i}").status_code == 200, i
h = pr.get("/ressources-secondaire/expose/0").get_data(as_text=True)
assert "Plan détaillé" in h and "Problématique" in h and "Polygamie et mariage forcé" in h and "Conclusion" in h and "Sources à consulter" in h and "Conception" not in h
assert "Voir le thème développé" in pr.get("/ressources-secondaire?vue=exposes").get_data(as_text=True)
assert "Thème développé" in pr.get(f"/ens-sec/expose/{x2['id']}").get_data(as_text=True)
ex("DELETE FROM exposes_sec WHERE id=?", (x2["id"],)) if False else None
def eleve(i):
    c = app.test_client(); c.post("/eleve/connexion", data={"identifiant": f"M{i}", "mdp": "Elev#2026x"}); return c
e0, e3 = eleve(0), eleve(3)
assert "La décentralisation" in e0.get("/eleve/exposes").get_data(as_text=True)
assert "La décentralisation" not in e3.get("/eleve/exposes").get_data(as_text=True)      # autre classe
assert e3.get(f"/eleve/exposes/{xid}").status_code == 404
# trop gros groupe refusé (max 2), puis groupe valide
e0b = e0.get(f"/eleve/exposes/{x2['id']}")
e0.post(f"/eleve/exposes/{x2['id']}", data={"membres": [ids[2]]})                      # exposé issu de la bibliothèque : plan prérempli
g2 = q("SELECT contenu FROM exposes_groupes WHERE expose_id=?", (x2["id"],))[0]["contenu"]; assert "Polygamie" in g2, g2
assert "Guide de rédaction" in e0.get(f"/eleve/exposes/{x2['id']}").get_data(as_text=True)
ex("DELETE FROM exposes_groupes WHERE expose_id=?", (x2["id"],))
e0.post(f"/eleve/exposes/{xid}", data={"membres": [ids[1], ids[2]]})
assert q("SELECT COUNT(*) n FROM exposes_groupes WHERE expose_id=?", (xid,))[0]["n"] == 0
e0.post(f"/eleve/exposes/{xid}", data={"membres": [ids[1]]})
gid = q("SELECT id FROM exposes_groupes")[0]["id"]
e1 = eleve(1)
e1.post(f"/eleve/exposes/{xid}", data={"membres": [ids[2]]})                           # déjà dans un groupe : rien de plus
assert q("SELECT COUNT(*) n FROM exposes_groupes")[0]["n"] == 1
r = e1.post(f"/eleve/exposes/groupe/{gid}/enregistrer", data={"action": "brouillon", "introduction": "Intro XYZ", "developpement": "Corps ABC", "conclusion": "Fin", "plan": "I. II.", "sources": "Manuel"})
assert r.status_code == 302
g = e0.get(f"/eleve/exposes/groupe/{gid}/garde").get_data(as_text=True)
assert "ADJOVI" in g and "DOSSOU" in g and "La décentralisation" in g and "Conception" not in g and "FACHOLA" not in g
assert e3.get(f"/eleve/exposes/groupe/{gid}/garde").status_code == 404
r = e0.get(f"/eleve/exposes/groupe/{gid}.pdf"); assert r.data[:4] == b"%PDF"
from pypdf import PdfReader
t = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.data)).pages)
assert "ADJOVI" in t and "Intro XYZ" in t and "Conception" not in t and "FACHOLA" not in t, t[-400:]
assert e0.get(f"/eleve/exposes/groupe/{gid}.docx").data[:2] == b"PK"
e0.post(f"/eleve/exposes/groupe/{gid}/enregistrer", data={"action": "remettre", "introduction": "Intro XYZ"})
assert q("SELECT statut FROM exposes_groupes")[0]["statut"] == "remis"
e0.post(f"/eleve/exposes/groupe/{gid}/enregistrer", data={"action": "brouillon", "introduction": "PIRATE"})   # verrouillé
assert "PIRATE" not in q("SELECT contenu FROM exposes_groupes")[0]["contenu"]
# prof : lire, noter, rouvrir
assert "Intro XYZ" in pr.get(f"/ens-sec/expose/groupe/{gid}").get_data(as_text=True)
pr.post(f"/ens-sec/expose/groupe/{gid}/noter", data={"note": "15/20", "appreciation": "Bien"})
assert q("SELECT note FROM exposes_groupes")[0]["note"] == "15/20"
assert "15/20" in e0.get(f"/eleve/exposes/{xid}").get_data(as_text=True)
pr.post(f"/ens-sec/expose/groupe/{gid}/noter", data={"action": "rouvrir"})
assert q("SELECT statut FROM exposes_groupes")[0]["statut"] == "brouillon"
r = pr.get(f"/exporter.pdf?page=/eleve/exposes/groupe/{gid}"); 
pr.post(f"/ens-sec/expose/{xid}/modifier", data={"titre": "Nouveau thème", "taille_max": "3"})
assert q("SELECT titre FROM exposes_sec")[0]["titre"] == "Nouveau thème"
pr.post(f"/ens-sec/expose/{xid}/supprimer")
assert q("SELECT COUNT(*) n FROM exposes_sec WHERE id=?", (xid,))[0]["n"] == 0 and q("SELECT COUNT(*) n FROM exposes_groupes WHERE expose_id=?", (xid,))[0]["n"] == 0
print("OK")
'''


class T(unittest.TestCase):
    def test_exposes(self):
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=dict(os.environ, PREFIXE_SCRIPT=PREFIXE), capture_output=True, text=True)
        self.assertIn("OK", r.stdout, (r.stdout + r.stderr)[-2500:])


if __name__ == "__main__":
    unittest.main()
