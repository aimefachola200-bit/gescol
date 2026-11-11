# -*- coding: utf-8 -*-
"""Tests de la version 1.9 : groupes WhatsApp des directeurs et des enseignants (école, CS, DDEMP).
Lancer : python3 -m unittest tests.test_v19"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import m_groupes_whatsapp as W  # noqa: E402
import acces as A  # noqa: E402
import garde_notes as GN  # noqa: E402


def signer(graine, msg):
    """Signature Ed25519 (RFC 8032) pour les tests, avec une clé de test (la vraie clé privée n'est pas dans le dépôt)."""
    import hashlib
    h = hashlib.sha512(graine).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    pub = A._encoder(A._multiplier(a, A._BASE))
    r = int.from_bytes(hashlib.sha512(h[32:] + msg).digest(), "little") % A._L
    R = A._encoder(A._multiplier(r, A._BASE))
    k = int.from_bytes(hashlib.sha512(R + pub + msg).digest(), "little") % A._L
    return pub, R + ((r + k * a) % A._L).to_bytes(32, "little")


def lancer(script, edition):
    env = dict(os.environ)
    env.pop("SCOLARIS_EDITION", None)
    env.pop("SCOLARIS_DATA", None)
    env["SCOLARIS_EDITION_SCRIPT"] = edition
    return subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestGardeNotes(unittest.TestCase):
    def test_regles(self):
        self.assertEqual(GN.lire("18", "2"), (20.0, False, 2.0))
        self.assertEqual(GN.lire("12,5", ""), (12.5, False, None))
        self.assertEqual(GN.lire("D", "1"), (None, True, None))
        self.assertEqual(GN.lire("", ""), (None, False, None))
        self.assertEqual(GN.lire("9", "0"), (9.0, False, 0.0))
        self.assertEqual(GN.lire("9", ""), (9.0, False, None))
        self.assertEqual(GN.lire("10", "2"), (12.0, False, 2.0))
        self.assertEqual(GN.lire("19", "1"), (20.0, False, 1.0))
        for a, b in (("20", ""), ("20", "0"), ("19", "1.5"), ("15", "3"), ("", "1"), ("abc", ""), ("-1", ""),
                     ("9", "1"), ("9,5", "0.5")):
            with self.assertRaises(GN.NoteRefusee, msg=(a, b)):
                GN.lire(a, b)
        self.assertEqual(GN.separer("18|2"), ("18", "2"))
        self.assertEqual(GN.afficher(20.0, 2.0), ("18", "2"))
        self.assertEqual(GN.afficher(12.5, None), ("12.5", ""))


class TestCodesAcces(unittest.TestCase):
    def test_signature(self):
        pub, sig = signer(b"\x01" * 32, b"SCOLARIS|AAAA-BBBB-CCCC|directeur")
        self.assertTrue(A.verifier_signature(pub, b"SCOLARIS|AAAA-BBBB-CCCC|directeur", sig))
        self.assertFalse(A.verifier_signature(pub, b"SCOLARIS|AAAA-BBBB-CCCC|enseignant", sig))
        self.assertFalse(A.verifier_signature(A.CLE_PUBLIQUE, b"SCOLARIS|AAAA-BBBB-CCCC|directeur", sig))

    def test_desactive(self):
        self.assertFalse(A.ACTIF)  # codes d'accès désactivés pour le moment (v1.9.2)

    def test_code(self):
        self.assertEqual(len(A.nouvel_identifiant_installation()), 14)
        self.assertEqual(A.message("scolaris", "aaaa-bbbb-cccc", " Directeur "), "SCOLARIS|AAAA-BBBB-CCCC|directeur")
        self.assertFalse(A.code_valide("SCOLARIS", "AAAA-BBBB-CCCC", "directeur", "ABCDE-FGHIJ"))


class TestRegles(unittest.TestCase):
    def test_role(self):
        self.assertEqual(W.role_de("Directeur"), "directeur")
        self.assertEqual(W.role_de("Directeur adjoint"), "adjoint")
        self.assertEqual(W.role_de("Instituteur"), "enseignant")
        self.assertEqual(W.role_de("Gardien"), "autre")

    def test_date_longue(self):
        self.assertEqual(W.date_longue("2026-10-23"), "vendredi 23 octobre 2026")
        self.assertEqual(W.date_longue("2026-11-01"), "dimanche 1er novembre 2026")
        self.assertEqual(W.date_longue(""), "")

    def test_texte_modele(self):
        m = {"type": "convocation", "objet": "la réunion de rentrée", "date": "2026-10-23", "heure": "09:00", "lieu": "la CS"}
        t = W.texte_modele(m, "CS Pobè", "Le Chef de la Circonscription Scolaire", W.PUBLIC["directeurs"])
        self.assertIn("CONVOCATION — CS Pobè", t)
        self.assertIn("Les directeurs et directrices sont convoqués à la réunion de rentrée le *vendredi 23 octobre 2026* à *09:00*", t)
        self.assertTrue(t.endswith("Le Chef de la Circonscription Scolaire"))
        t = W.texte_modele(m, "CS", "X", "Y", {"nom": "ADJOVI Paul", "ecole": "EPP Ahoyéyé"})
        self.assertIn("Bonjour ADJOVI Paul (EPP Ahoyéyé),", t)
        self.assertNotIn("\n\n\n", t)

    def test_vcard(self):
        v = W.vcard([{"nom": "ADJOVI Paul", "ecole": "EPP A, B", "num": "2290197000001", "role_lib": "Directeur"}], "Dir", "CS Pobè")
        self.assertIn("FN:Dir ADJOVI Paul (EPP A\\, B)", v)
        self.assertIn("TEL;TYPE=CELL:+2290197000001", v)
        self.assertTrue(v.startswith("BEGIN:VCARD\r\nVERSION:3.0"))


SCRIPT_ECOLE = r'''
import html, os, sys, tempfile, subprocess
ED = os.environ["SCOLARIS_EDITION_SCRIPT"]
os.environ["SCOLARIS_EDITION"] = ED; os.environ["SCOLARIS_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
subprocess.run([sys.executable, "demo.py"], check=True, env=dict(os.environ), stdout=subprocess.DEVNULL)
from app import app, q, ex
app.config["TESTING"] = True
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.data[-800:]); return r
def txt(r): return html.unescape(r.data.decode())
with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0")
    eco = q("SELECT id FROM ecoles ORDER BY id", un=True)["id"]
    ex("INSERT INTO personnel (matricule, nom, prenoms, fonction, telephone, ecole_id, actif) VALUES ('T1','HOUNSA','Marie','Institutrice','97 00 00 01',?,1)", (eco,))
    ex("INSERT INTO personnel (matricule, nom, prenoms, fonction, telephone, ecole_id, actif) VALUES ('T2','DOSSOU','Jean','Gardien','0196000002',?,1)", (eco,))
c = app.test_client(); ok(c.post("/login", data={"identifiant": "directeur", "mdp": "demo1234"}), 302)
t = txt(ok(c.get("/groupes-whatsapp")))
assert "Groupes WhatsApp" in t and "HOUNSA Marie" in t and "+229 01 97 00 00 01" in t, t[-3000:]
assert "DOSSOU" not in t.split("<table")[1]           # le gardien n'est pas dans le groupe des enseignants
t = txt(ok(c.get("/groupes-whatsapp?groupe=personnel")))
assert "DOSSOU Jean" in t and "contacts.vcf?groupe=personnel" in t and "avec tout le personnel" in t
ok(c.post("/groupes-whatsapp/reglages?groupe=enseignants", data={"nom": "Enseignants test", "lien": "https://chat.whatsapp.com/ABC", "message": "Rejoins {groupe} : {lien}"}), 302)
v = ok(c.get("/groupes-whatsapp/contacts.vcf?groupe=enseignants"))
assert "TEL;TYPE=CELL:+2290197000001" in v.data.decode() and v.mimetype == "text/vcard"
r = ok(c.get("/groupes-whatsapp/suivant?groupe=enseignants"), 302)
assert r.headers["Location"].startswith("https://wa.me/2290197000001?text=Rejoins%20Enseignants%20test"), r.headers["Location"]
t = txt(ok(c.get("/groupes-whatsapp")))
assert "envoyée le" in t
ok(c.post("/groupes-whatsapp/reglages?groupe=enseignants", data={"modele_type": "convocation", "objet": "la réunion", "date": "2026-10-23", "heure": "09:00", "lieu": "l'école"}), 302)
t = txt(ok(c.get("/groupes-whatsapp")))
assert "Les enseignants et enseignantes sont convoqués à la réunion le *vendredi 23 octobre 2026*" in t
r = ok(c.get("/groupes-whatsapp/suivant?groupe=enseignants&message=1"), 302)
assert "Bonjour%20HOUNSA%20Marie" in r.headers["Location"]
ok(c.post("/groupes-whatsapp/remise-a-zero?groupe=enseignants"), 302)
assert "envoyée le" not in txt(ok(c.get("/groupes-whatsapp")))
assert "Groupes WhatsApp" in txt(ok(c.get("/")))      # lien dans le menu
c2 = app.test_client(); ok(c2.post("/login", data={"identifiant": "enseignant", "mdp": "demo1234"}), 302)
assert c2.get("/groupes-whatsapp").status_code in (302, 403)
# --- garde-fou des notes : note principale + performance
import json, sys
sys.path.insert(0, os.getcwd())
with app.app_context():
    from datetime import date as _d
    cl = q("SELECT * FROM classes WHERE niveau='CM2' ORDER BY id", un=True)
    import config as _c
    ev = ex("INSERT INTO evaluations (classe_id, annee, type, numero, libelle, date) VALUES (?,?,?,?,?,?)", (cl["id"], _c.ANNEE_ACTIVE, "sommative", 9, "Test perf", "2000-01-01"))
    ev = q("SELECT id FROM evaluations WHERE classe_id=? AND libelle='Test perf'", (cl["id"],), un=True)["id"]
    els = [r["id"] for r in q("SELECT id FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY id", (cl["id"],))][:5]
    mid = q("SELECT id FROM matieres WHERE cycle='primaire' AND actif=1 ORDER BY ordre", un=True)["id"]
d = client_dir = c
saisies = {str(els[0]): {str(mid): "18|2"}, str(els[1]): {str(mid): "20"}, str(els[2]): {str(mid): "15|3"},
           str(els[3]): {str(mid): "12,5"}, str(els[4]): {str(mid): "19|1.5"}}
r = c.post(f"/evaluations/{ev}/saisie", data={"notes_json": json.dumps(saisies)})
assert r.status_code == 302, r.status_code
with app.app_context():
    v = {n["eleve_id"]: (n["valeur"], n["performance"]) for n in q("SELECT * FROM notes WHERE periode='Test perf'")}
assert v.get(els[0]) == (20.0, 2.0), v
assert v.get(els[3]) == (12.5, None), v
assert els[1] not in v and els[2] not in v and els[4] not in v, v
t = txt(ok(c.get(f"/evaluations/{ev}/saisie")))
assert 'class="perf"' in t and "GardeNotes" in t and 'value="18"' in t
# --- codes d'accès personnels (contrôle activé, délai écoulé)
import acces as A, hashlib
graine = b"\x07" * 32
h = hashlib.sha512(graine).digest(); a = int.from_bytes(h[:32], "little"); a &= (1 << 254) - 8; a |= 1 << 254
pub = A._encoder(A._multiplier(a, A._BASE)); A.CLE_PUBLIQUE = pub; A._cache.clear()
def sig(msg):
    r_ = int.from_bytes(hashlib.sha512(h[32:] + msg).digest(), "little") % A._L
    R = A._encoder(A._multiplier(r_, A._BASE)); k = int.from_bytes(hashlib.sha512(R + pub + msg).digest(), "little") % A._L
    return R + ((r_ + k * a) % A._L).to_bytes(32, "little")
app.config["ACCES_CONTROLE"] = True
with app.app_context():
    ex("UPDATE parametres SET valeur='2000-01-01' WHERE cle='acces_debut'")
    inst = q("SELECT valeur FROM parametres WHERE cle='acces_installation'", un=True)["valeur"]
r = c.get("/groupes-whatsapp"); assert r.status_code == 302 and "/acces" in r.headers["Location"], r.headers.get("Location")
t = txt(ok(c.get("/acces")))
appli = "GESCOL" if "GESCOL" in t.split("|")[0][-20:] or os.environ.get("GESCOL_EDITION") else "SCOLARIS"
dem = f"{appli}|{inst}|directeur"
assert dem in t, (dem, t[-2000:])
assert "wa.me/2290196510333" in t, t[t.find("<main"):][:3000]
ok(c.post("/acces", data={"code": "AAAAA-BBBBB"}))
assert c.get("/groupes-whatsapp").status_code == 302
code = A.presenter_code(sig(dem.encode()))
ok(c.post("/acces", data={"code": code}), 302)
ok(c.get("/groupes-whatsapp"))
# l'administrateur : demandes de tous les comptes, codes collés en une fois
t = txt(ok(c.get("/acces/comptes")))
assert f"{appli}|{inst}|enseignant" in t
code_e = A.presenter_code(sig(f"{appli}|{inst}|enseignant".encode()))
ok(c.post("/acces/comptes", data={"codes": f"enseignant : {code_e}\nfaux : ABC"}), 302)
e2 = app.test_client(); ok(e2.post("/login", data={"identifiant": "enseignant", "mdp": "demo1234"}), 302)
assert "/acces" not in (e2.get("/").headers.get("Location") or "")
# délai de grâce : bandeau, accès permis
with app.app_context():
    ex("UPDATE parametres SET valeur=date('now') WHERE cle='acces_debut'")
    ex("UPDATE utilisateurs SET code_acces=NULL WHERE identifiant='directeur'")
t = txt(ok(c.get("/groupes-whatsapp")))
assert "code d'accès personnel" in t and "jour(s) avant le blocage" in t
print("ECOLE-OK")
'''

SCRIPT_JUR = r'''
import html, json, os, sys, tempfile
os.environ["SCOLARIS_EDITION"] = os.environ["SCOLARIS_EDITION_SCRIPT"]; os.environ["SCOLARIS_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config, demo_juridiction
from app import app, q, ex
app.config["TESTING"] = True
demo_juridiction.main()
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.data[-800:]); return r
def txt(r): return html.unescape(r.data.decode())
with app.app_context():
    e = q("SELECT * FROM jur_ecoles ORDER BY id", un=True)
    ex("UPDATE jur_ecoles SET directeur_nom='ADJOVI Paul', directeur_tel='97000001' WHERE id=?", (e["id"],))
    ex("INSERT OR REPLACE INTO jur_sections (ecole_id, annee, section, donnees, source, maj) VALUES (?,?,?,?,?,datetime('now'))",
       (e["id"], config.ANNEE_ACTIVE, "personnel", json.dumps([{"nom": "HOUNSA", "prenoms": "Marie", "fonction": "Institutrice", "role": "enseignant", "telephone": "0196000002", "nip": "N1"}]), "test"))
    z = q("SELECT id FROM jur_zones ORDER BY id", un=True)
    ex("UPDATE jur_zones SET cp_nom='AGBO Rose', cp_telephone='0195000003' WHERE id=?", (z["id"],))
c = app.test_client(); ok(c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"}), 302)
t = txt(ok(c.get("/groupes-whatsapp")))
assert "Partager les informations avec directeurs des écoles" in t and "contacts.vcf?groupe=directeurs" in t
assert "ADJOVI Paul" in t and "+229 01 97 00 00 01" in t, t[-3000:]
t = txt(ok(c.get("/groupes-whatsapp?groupe=enseignants")))
assert "HOUNSA Marie" in t, t[-3000:]
t = txt(ok(c.get("/groupes-whatsapp?groupe=cp")))
assert "AGBO Rose" in t
if config.EDITION == "ddemp":
    assert "Chefs de circonscription" in t
v = ok(c.get("/groupes-whatsapp/contacts.vcf?groupe=directeurs")).data.decode()
assert "TEL;TYPE=CELL:+2290197000001" in v
r = ok(c.get("/groupes-whatsapp/inviter/E%d?groupe=directeurs" % e["id"]), 302)
assert r.headers["Location"].startswith("https://wa.me/2290197000001")
assert "Groupes WhatsApp" in txt(ok(c.get("/juridiction/tableau-de-bord")))
app.config["ACCES_CONTROLE"] = True
with app.app_context():
    ex("UPDATE parametres SET valeur='2000-01-01' WHERE cle='acces_debut'")
r = c.get("/juridiction/tableau-de-bord"); assert r.status_code == 302 and "/acces" in r.headers["Location"]
t = txt(ok(c.get("/acces"))); assert "|responsable" in t
t = txt(ok(c.get("/acces/comptes"))); assert "|cp1" in t
print("JUR-OK")
'''


class TestParcours(unittest.TestCase):
    def test_publique(self):
        r = lancer(SCRIPT_ECOLE, "publique")
        self.assertIn("ECOLE-OK", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_privee(self):
        r = lancer(SCRIPT_ECOLE, "privee")
        self.assertIn("ECOLE-OK", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_cs(self):
        r = lancer(SCRIPT_JUR, "cs")
        self.assertIn("JUR-OK", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_ddemp(self):
        r = lancer(SCRIPT_JUR, "ddemp")
        self.assertIn("JUR-OK", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])


if __name__ == "__main__":
    unittest.main()
