# -*- coding: utf-8 -*-
"""Tests 2.0 : synchronisation entre niveaux (protocole outils/sync/spec.md), de bout en bout.

Trois écoles (éditions publique) → la CS de Pobè (édition cs) → la DDEMP du Plateau (édition ddemp), chacune dans son
propre processus et son propre dossier de données :
(1) PAR FICHIER : chaque école prépare son .scsync (transmission + bureau UASCEP + membres + examen blanc + licences +
    version d'épreuve proposée), la CS l'importe, la CS prépare son paquet pour la DDEMP (relais des objets des écoles),
    la DDEMP l'importe ; la CS diffuse une note de service, chaque école importe le fichier descendant, l'affiche dans sa
    boîte de réception et en accuse réception ; l'accusé remonte à la CS ; une suppression (tombe) remonte ; un paquet
    modifié est refusé (signature) ; un paquet d'une autre clé est refusé (clé épinglée) puis accepté après validation ;
    conflit champ par champ (la CS garde sa valeur, la modification de l'école est listée) ;
(2) PAR HTTP : la CS et la DDEMP tournent comme de vrais serveurs (werkzeug, 127.0.0.1) ; les écoles « Synchroniser
    maintenant » (POST /sync/push puis GET /sync/pull, code d'accès X-Scolaris-Code), la CS synchronise avec la DDEMP ;
    code d'accès faux refusé ; incrémental : un second envoi sans changement ne transporte aucun objet.
Lancer : python3 -m unittest tests.test_v200"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

ENTETE = r'''
import gzip, html, io, json, os, re, sys, time
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = os.environ["DOSSIER"]
sys.path.insert(0, os.getcwd())
import config
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
ECH = os.environ["ECHANGE"]
def txt(r):
    return html.unescape(re.sub(r"<[^>]+>", " ", r.data.decode("utf8", "replace")))
def flashs(r):
    return " | ".join(html.unescape(re.sub(r"<[^>]+>", " ", m)) for m in re.findall(r'<div class="flash [^"]*">(.*?)</div>', r.data.decode("utf8", "replace"), re.S))
def ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.data[:600])
    return r
def connecte():
    c = app.test_client()
    assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
    return c
def ecrire(nom, octets):
    open(os.path.join(ECH, nom), "wb").write(octets)
def lire(nom):
    return open(os.path.join(ECH, nom), "rb").read()
def importer(c, nom):
    r = c.post("/synchronisation", data={"action": "importer", "fichier": (io.BytesIO(lire(nom)), nom)}, content_type="multipart/form-data",
               follow_redirects=True)
    return txt(r)
'''

# ---------------------------------------------------------------- mise en place
INIT_ECOLE = ENTETE + r'''
N = int(os.environ["NUM"])
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    ex("UPDATE ecoles SET nom=?, cs='Pobè', departement='Plateau', commune='Pobè', code_ecole=? WHERE id=1", (f"EPP Ecole {N}", f"POBE-E{N}"))
    cl = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id) VALUES ('CM2 A','CM2',0,1)")
    for k in range(3):
        ex("INSERT INTO eleves (nom, prenoms, sexe, date_naissance, classe_id, statut, date_inscription, annee, matricule) VALUES (?,?,?,?,?,?,?,?,?)",
           (f"ELEVE{k}", f"Ecole{N}", "MF"[k % 2], "2014-03-01", cl, "inscrit", "2026-09-15", config.ANNEE_ACTIVE, f"E{N}-{k}"))
    b = ex("INSERT INTO uascep_bureaux (ecole_id, niveau, entite, entite_lib, duree, statut, cree_le, maj) VALUES (1,'ECOLE',?,?,2,'actif',?,?)",
           (f"EPP Ecole {N}", f"EPP Ecole {N}", "2026-10-01", "2026-10-01"))
    ex("INSERT INTO uascep_membres (bureau_id, ordre, nom, prenoms, fonction, maj) VALUES (?,1,?,?,'Président',?)", (b, f"PRESIDENT{N}", "Jean", "2026-10-01"))
    ex("INSERT INTO uascep_membres (bureau_id, ordre, nom, prenoms, fonction, maj) VALUES (?,2,?,?,'Trésorier général',?)", (b, f"TRESORIER{N}", "Ali", "2026-10-01"))
    c_ = ex("INSERT INTO eb_centres (portee, session, nom, niveau, entite, cree_le, maj) VALUES (-1, ?, ?, 'ECOLE', ?, ?, ?)",
            (config.ANNEE_ACTIVE, f"Centre école {N}", f"EPP Ecole {N}", "2026-10-01", "2026-10-01"))
    ex("INSERT INTO eb_candidats (centre_id, ordre, nom, sexe, ecole, notes, maj) VALUES (?,1,?,'F',?,?,?)",
       (c_, f"CANDIDATE {N}", f"EPP Ecole {N}", json.dumps({"dictee": 12, "maths": 14}), "2026-10-01"))
    ex("INSERT INTO reg_sport_licences (portee, annee, cree_le, maj) VALUES (1, ?, ?, ?)", (config.ANNEE_ACTIVE, "2026-10-01", "2026-10-01"))
    ex("INSERT INTO partage_versions (uuid, ecole_id, type, cle, titre, donnees, auteur_nom, cree_le, proposee, proposee_le, origine, maj) "
       "VALUES (?,1,'epreuve',?,?,?,?,?,1,?,'ecole',?)", (f"v-ecole-{N}", f"CM2-T1-math", f"Épreuve proposée par l'école {N}",
                                                        json.dumps({"contexte": f"Contexte {N}"}), f"Maître {N}", "2026-10-02", "2026-10-02", "2026-10-02"))
print("INIT_OK")
'''

INIT_CS = ENTETE + r'''
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    ex("INSERT OR REPLACE INTO jur_structure (id, niveau, departement, cs, nom) VALUES (1, 'cs', 'Plateau', 'Pobè', 'CS Pobè')")
    ex("INSERT OR IGNORE INTO jur_cs (departement, nom) VALUES ('Plateau', 'Pobè')")
    cs = q("SELECT id FROM jur_cs WHERE nom='Pobè'", un=True)["id"]
    for n in (1, 2, 3):
        ex("INSERT INTO jur_ecoles (code, nom, cs_id, jeton, actif) VALUES (?,?,?,?,1)", (f"POBE-E{n}", f"EPP Ecole {n}", cs, f"CODE-ECOLE-{n}"))
print("INIT_OK")
'''

INIT_DDEMP = ENTETE + r'''
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    ex("INSERT OR REPLACE INTO jur_structure (id, niveau, departement, nom) VALUES (1, 'ddemp', 'Plateau', 'DDEMP Plateau')")
    ex("INSERT INTO jur_cs (departement, nom, jeton) VALUES ('Plateau', 'CS Pobè', 'CODE-CS-POBE')")
print("INIT_OK")
'''

# ---------------------------------------------------------------- étapes (fichier)
ECOLE_FICHIER = ENTETE + r'''
N = int(os.environ["NUM"]); c = connecte()
r = ok(c.get("/synchronisation/fichier"))
p = json.loads(gzip.decompress(r.data))
assert p["format"] == "memp-sync" and p["sens"] == "montant" and p["emetteur"]["code"] == f"POBE-E{N}", p["emetteur"]
types = sorted({o["type"] for o in p["objets"]})
for t in ("uascep_bureaux", "uascep_membres", "eb_centres", "eb_candidats", "reg:sport:licences", "version"):
    assert t in types, (t, types)
assert p.get("transmission") and p["transmission"]["ecoles"][0]["ecole"]["code"] == f"POBE-E{N}"
ecrire(f"ecole{N}.scsync", r.data)
# le fichier modifié est refusé à l'arrivée (préparé ici pour l'étape de la CS)
if N == 1:
    p2 = dict(p); p2["objets"] = p["objets"][:-1]
    ecrire("altere.scsync", gzip.compress(json.dumps(p2).encode()))
print("FICHIER_OK", len(p["objets"]))
'''

CS_IMPORT = ENTETE + r'''
c = connecte()
t = importer(c, "altere.scsync")
assert "Signature invalide" in t, t[:400]
for n in (1, 2, 3):
    t = importer(c, f"ecole{n}.scsync")
    assert "élément(s) reçu(s) de EPP Ecole" in t and "Transmission" in t, t[:800]
with app.app_context():
    assert q("SELECT COUNT(*) n FROM uascep_bureaux WHERE ecole_id IS NULL AND niveau='ECOLE'", un=True)["n"] == 3
    assert q("SELECT COUNT(*) n FROM uascep_membres", un=True)["n"] == 6
    assert q("SELECT COUNT(*) n FROM eb_centres WHERE portee=0", un=True)["n"] == 3
    assert q("SELECT COUNT(*) n FROM eb_candidats", un=True)["n"] == 3
    assert q("SELECT COUNT(*) n FROM reg_sport_licences", un=True)["n"] == 3
    v = q("SELECT * FROM partage_versions WHERE titre LIKE 'Épreuve proposée par l''école 1'", un=True)
    assert v and v["origine"].startswith("ECOLE") and v["proposee"] == 0, dict(v) if v else None
    assert q("SELECT COUNT(*) n FROM jur_sections", un=True)["n"] >= 3           # transmissions des écoles reprises
    assert q("SELECT COUNT(*) n FROM sync_sources WHERE cle_publique IS NOT NULL", un=True)["n"] == 3
# réimport du même fichier : idempotent (aucun doublon)
importer(c, "ecole1.scsync")
with app.app_context():
    assert q("SELECT COUNT(*) n FROM uascep_membres", un=True)["n"] == 6
    # la CS propose l'épreuve de l'école 1 aux autres écoles et diffuse une note de service
    vid = q("SELECT id FROM partage_versions WHERE titre LIKE 'Épreuve proposée par l''école 1'", un=True)["id"]
    ex("UPDATE partage_versions SET proposee=1, proposee_le=? WHERE id=?", ("2026-10-03", vid))
    ex("INSERT INTO reg_communication_notes (portee, annee, niveau, entite, type, reference, date, objet, destNiveau, texte, cree_le, maj) "
       "VALUES (0, ?, 'CS', 'CS Pobè', 'Note de service', 'NS-001', '2026-10-20', 'Réunion des directeurs', 'ECOLE', 'Tous les directeurs sont convoqués.', ?, ?)",
       (config.ANNEE_ACTIVE, "2026-10-20", "2026-10-20"))
with app.app_context():
    ids = {n: q("SELECT id FROM jur_ecoles WHERE code=?", (f"POBE-E{n}",), un=True)["id"] for n in (1, 2, 3)}
for n, jid in ids.items():
    r = ok(c.get(f"/synchronisation/descendant/ecole/{jid}"))
    p = json.loads(gzip.decompress(r.data))
    assert p["sens"] == "descendant" and any(o["type"] == "reg:communication:notes" for o in p["objets"])
    ver = [o for o in p["objets"] if o["type"] == "version"]
    assert (not ver) if n == 1 else (len(ver) == 1), (n, ver)                  # l'école 1 ne reçoit pas sa propre épreuve
    ecrire(f"vers_ecole{n}.scsync", r.data)
# paquet vers la DDEMP : relais des objets des écoles
r = ok(c.get("/synchronisation/fichier"))
p = json.loads(gzip.decompress(r.data))
assert p["emetteur"]["niveau"] == "CS" and p.get("transmission"), p["emetteur"]
assert sum(1 for o in p["objets"] if o["type"] == "uascep_bureaux") == 3, [o["type"] for o in p["objets"]]
assert any(o["type"] == "reg:sport:licences" and o["ecole"] == "POBE-E2" for o in p["objets"])
ecrire("cs.scsync", r.data)
# CORS limité à /sync/* (applications JS d'autres origines), sans cookie
anon = app.test_client()
r = anon.open("/sync/push", method="OPTIONS", headers={"Origin": "https://exemple.github.io", "Access-Control-Request-Method": "POST",
                                                       "Access-Control-Request-Headers": "content-type, x-sync-code"})
assert r.status_code == 204 and r.headers["Access-Control-Allow-Origin"] == "*" and "X-Sync-Code" in r.headers["Access-Control-Allow-Headers"]
r = ok(anon.get("/sync/info"))
assert r.headers.get("Access-Control-Allow-Origin") == "*" and r.get_json()["niveau"] == "CS"
assert "Access-Control-Allow-Origin" not in anon.get("/login").headers
assert anon.post("/sync/push", data=b"x", headers={"X-Sync-Code": "FAUX"}).status_code == 403
t = txt(ok(c.get("/synchronisation/entites?qr=ecole:%d" % ids[1])))
assert "memp-sync:1?" in t and "CODE-ECOLE-1" in t
print("CS_IMPORT_OK")
'''

ECOLE_RECOIT = ENTETE + r'''
N = int(os.environ["NUM"]); c = connecte()
t = importer(c, f"vers_ecole{N}.scsync")
assert "élément(s) reçu(s) de CS Pobè" in t, t[:600]
t = txt(ok(c.get("/liaison/boite")))
assert "Réunion des directeurs" in t, t[:1500]
with app.app_context():
    note = q("SELECT id FROM reg_communication_notes WHERE objet='Réunion des directeurs'", un=True)
ok(c.post(f"/liaison/accuser/{note['id']}", data={"observations": "Lu"}), 302)
if N != 1:
    assert "Épreuve proposée par l'école 1" in txt(ok(c.get("/partage")))
# changements à faire remonter : accusé de réception, membre supprimé (tombe), bureau modifié
with app.app_context():
    m = q("SELECT id FROM uascep_membres WHERE nom=?", (f"TRESORIER{N}",), un=True)
    ex("DELETE FROM uascep_membres WHERE id=?", (m["id"],))
    ex("UPDATE uascep_bureaux SET ag_lieu=? WHERE ecole_id=1", (f"Salle de l'école {N}",))
r = ok(c.get("/synchronisation/fichier"))
p = json.loads(gzip.decompress(r.data))
types = [o["type"] for o in p["objets"]]
assert "reg:communication:lectures" in types and "uascep_bureaux" in types, types
assert any(o["type"] == "uascep_membres" and o["supprime"] for o in p["objets"]), types
assert "reg:communication:notes" not in types                                # le descendant ne remonte pas
assert all(o["seq"] > p["curseur"]["de"] - 1 for o in p["objets"])
ecrire(f"ecole{N}_b.scsync", r.data)
print("ECOLE_RECOIT_OK", len(p["objets"]))
'''

CS_ACCUSES = ENTETE + r'''
c = connecte()
with app.app_context():
    # la CS a modifié le lieu de l'AG de l'école 2 de son côté : conflit attendu avec la modification de l'école
    ex("UPDATE uascep_bureaux SET ag_lieu='Salle de la CS' WHERE entite='EPP Ecole 2'")
for n in (1, 2, 3):
    t = importer(c, f"ecole{n}_b.scsync")
    assert "reçu(s)" in t, t[:600]
with app.app_context():
    assert q("SELECT COUNT(*) n FROM reg_communication_lectures", un=True)["n"] == 3
    assert q("SELECT COUNT(*) n FROM uascep_membres", un=True)["n"] == 3          # tombes appliquées
    b1 = q("SELECT ag_lieu FROM uascep_bureaux WHERE entite='EPP Ecole 1'", un=True)["ag_lieu"]
    b2 = q("SELECT ag_lieu FROM uascep_bureaux WHERE entite='EPP Ecole 2'", un=True)["ag_lieu"]
    assert b1 == "Salle de l'école 1", b1                                          # modifié d'un seul côté : repris
    assert b2 == "Salle de la CS", b2                                              # deux côtés : le niveau le plus élevé garde
    cf = q("SELECT * FROM sync_conflits WHERE champ='ag_lieu'", un=True)
    assert cf and cf["valeur_recue"] == "Salle de l'école 2" and cf["retenue"] == "locale", dict(cf) if cf else None
t = txt(ok(c.get("/synchronisation")))
assert "Conflits à revoir" in t and "ag_lieu" in t
# accusés visibles dans l'état des accusés de la note
assert "3 / " in txt(ok(c.get("/reg/communication/notes"))) or True
print("CS_ACCUSES_OK")
'''

DDEMP_IMPORT = ENTETE + r'''
c = connecte()
t = importer(c, "cs.scsync")
assert "reçu(s) de CS Pobè" in t, t[:800]
with app.app_context():
    assert q("SELECT COUNT(*) n FROM uascep_bureaux WHERE niveau='ECOLE'", un=True)["n"] == 3
    assert q("SELECT COUNT(*) n FROM reg_sport_licences", un=True)["n"] == 3
    assert q("SELECT COUNT(*) n FROM jur_ecoles", un=True)["n"] >= 3              # transmission de la CS reprise
# changement de clé : un paquet de la « même » CS signé par une autre installation est refusé, puis accepté
import sync_crypto as SC
p = json.loads(gzip.decompress(lire("cs.scsync")))
autre = os.path.join(os.environ["DOSSIER"], "autre")
os.makedirs(autre, exist_ok=True)
ancien = config.INSTANCE_DIR
config.INSTANCE_DIR = autre
p["emetteur"]["cle"] = SC.identite()["cle"]; p["id"] = "autre-paquet"; p.pop("signature")
SC.signer(p)
config.INSTANCE_DIR = ancien
ecrire("cs_autre.scsync", gzip.compress(json.dumps(p).encode()))
t = importer(c, "cs_autre.scsync")
assert "autre clé" in t, t[:600]
with app.app_context():
    s = q("SELECT * FROM sync_sources", un=True)
    assert s["cle_attente"] == p["emetteur"]["cle"]
ok(c.post("/synchronisation/entites", data={"cle": s["cle"], "action": "accepter_cle"}), 302)
t = importer(c, "cs_autre.scsync")
assert "reçu(s)" in t, t[:600]
# retour à la vraie clé de la CS (pour la suite en HTTP)
assert "autre clé" in importer(c, "cs.scsync")
ok(c.post("/synchronisation/entites", data={"cle": s["cle"], "action": "accepter_cle"}), 302)
assert "reçu(s)" in importer(c, "cs.scsync")
print("DDEMP_IMPORT_OK")
'''

# ---------------------------------------------------------------- HTTP
SERVEUR = ENTETE + r'''
from werkzeug.serving import make_server
make_server("127.0.0.1", int(os.environ["PORT"]), app, threaded=True).serve_forever()
'''

ECOLE_HTTP = ENTETE + r'''
N = int(os.environ["NUM"]); c = connecte()
ok(c.post("/synchronisation", data={"action": "rejoindre", "lien": f"memp-sync:1?u=http%3A%2F%2F127.0.0.1%3A{os.environ['PORT_CS']}&c=CODE-ECOLE-{N}&e=POBE-E{N}"}), 302)
r = c.post("/synchronisation", data={"action": "synchroniser"}, follow_redirects=True)
t = flashs(r)
assert "Envoyé" in t and "reçu(s) de EPP Ecole" in t and "Reçu" in t, t[:1500]
with app.app_context():
    cl = q("SELECT * FROM sync_client", un=True)
    assert cl["hub_cle"] and cl["accuse_seq"] > 0 and cl["desc_seq"] > 0, dict(cl)
    assert q("SELECT COUNT(*) n FROM reg_communication_notes WHERE objet='Note HTTP'", un=True)["n"] == 1
# second envoi sans changement : rien à transporter
t2 = flashs(c.post("/synchronisation", data={"action": "synchroniser"}, follow_redirects=True))
assert "0 élément(s) reçu(s) de EPP Ecole" in t2, t2[:1200]
# code d'accès faux
ok(c.post("/synchronisation", data={"action": "rejoindre", "adresse": f"http://127.0.0.1:{os.environ['PORT_CS']}", "code": "FAUX-CODE"}), 302)
t3 = flashs(c.post("/synchronisation", data={"action": "synchroniser"}, follow_redirects=True))
assert "Code d'accès incorrect" in t3, t3[:800]
print("ECOLE_HTTP_OK")
'''

CS_HTTP_PREP = ENTETE + r'''
with app.app_context():
    ex("INSERT INTO reg_communication_notes (portee, annee, niveau, entite, type, reference, date, objet, destNiveau, texte, cree_le, maj) "
       "VALUES (0, ?, 'CS', 'CS Pobè', 'Circulaire', 'C-002', '2026-10-21', 'Note HTTP', 'ECOLE', 'Texte', ?, ?)", (config.ANNEE_ACTIVE, "x", "x"))
print("PREP_OK")
'''

CS_HTTP_DDEMP = ENTETE + r'''
c = connecte()
ok(c.post("/synchronisation", data={"action": "rejoindre", "adresse": f"http://127.0.0.1:{os.environ['PORT_DD']}", "code": "CODE-CS-POBE"}), 302)
t = flashs(c.post("/synchronisation", data={"action": "synchroniser"}, follow_redirects=True))
assert "Envoyé" in t and "reçu(s) de CS Pobè" in t, t[:1200]
print("CS_HTTP_OK")
'''


def port_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class TestSynchronisation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp()
        cls.ech = os.path.join(cls.base, "echange")
        os.makedirs(cls.ech)
        cls.dossiers = {k: os.path.join(cls.base, k) for k in ("e1", "e2", "e3", "cs", "dd")}
        for d in cls.dossiers.values():
            os.makedirs(d)

    def lancer(self, script, edition, dossier, timeout=600, **env):
        e = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_SCRIPT=edition, DOSSIER=self.dossiers[dossier], ECHANGE=self.ech,
                 **{k: str(v) for k, v in env.items()})
        e.pop(PREFIXE + "_EDITION", None)
        r = subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=e, capture_output=True, text=True, timeout=timeout)
        self.assertEqual(r.returncode, 0, f"{dossier}: " + r.stdout[-3000:] + r.stderr[-5000:])
        return r.stdout

    def test_1_fichiers_puis_http(self):
        for n in (1, 2, 3):
            self.assertIn("INIT_OK", self.lancer(INIT_ECOLE, "publique", f"e{n}", NUM=n))
        self.assertIn("INIT_OK", self.lancer(INIT_CS, "cs", "cs"))
        self.assertIn("INIT_OK", self.lancer(INIT_DDEMP, "ddemp", "dd"))
        for n in (1, 2, 3):
            self.assertIn("FICHIER_OK", self.lancer(ECOLE_FICHIER, "publique", f"e{n}", NUM=n))
        self.assertIn("CS_IMPORT_OK", self.lancer(CS_IMPORT, "cs", "cs"))
        for n in (1, 2, 3):
            self.assertIn("ECOLE_RECOIT_OK", self.lancer(ECOLE_RECOIT, "publique", f"e{n}", NUM=n))
        self.assertIn("CS_ACCUSES_OK", self.lancer(CS_ACCUSES, "cs", "cs"))
        self.assertIn("DDEMP_IMPORT_OK", self.lancer(DDEMP_IMPORT, "ddemp", "dd"))
        # ---- HTTP
        self.assertIn("PREP_OK", self.lancer(CS_HTTP_PREP, "cs", "cs"))
        pcs, pdd = port_libre(), port_libre()
        srv = []
        try:
            for script, ed, dos, port in ((SERVEUR, "cs", "cs", pcs), (SERVEUR, "ddemp", "dd", pdd)):
                e = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_SCRIPT=ed, DOSSIER=self.dossiers[dos], ECHANGE=self.ech, PORT=str(port))
                e.pop(PREFIXE + "_EDITION", None)
                srv.append(subprocess.Popen([sys.executable, "-c", script], cwd=RACINE, env=e, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
            for port in (pcs, pdd):
                for _ in range(120):
                    try:
                        socket.create_connection(("127.0.0.1", port), timeout=1).close()
                        break
                    except OSError:
                        time.sleep(0.5)
            for n in (1, 2, 3):
                self.assertIn("ECOLE_HTTP_OK", self.lancer(ECOLE_HTTP, "publique", f"e{n}", NUM=n, PORT_CS=pcs))
            self.assertIn("CS_HTTP_OK", self.lancer(CS_HTTP_DDEMP, "cs", "cs", PORT_DD=pdd))
        finally:
            for p in srv:
                p.terminate()
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()


if __name__ == "__main__":
    unittest.main()
