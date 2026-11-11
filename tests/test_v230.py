# -*- coding: utf-8 -*-
"""Tests 2.3.0 : territoire et suivi administratif (compléments du prototype « GESCOL Territoire »).
(1) école : fiche statistique de rentrée proposée depuis les données, transmise, verrouillée, renvoyée par décision descendue ;
    courrier administratif envoyé (registre du secrétariat « départ »), accusé descendu ; fiche signalétique (GPS contrôlé) ;
    présence du personnel (appel du jour, statistiques du mois) ; incidents de discipline ; visites (statut, prochaine visite) ;
    catégories de besoins ajoutées ;
(2) CS : suivi des fiches, validation / renvoi (motif obligatoire), courrier reçu (non lu → reçu → traité, registre « arrivée »),
    référentiel des structures (arbre amorcé), niveau national (rôle observateur en lecture seule, /api/stats.json par jeton) ;
(3) DDEMP : validation départementale puis clôture ; (4) synchronisation : registres suivis (montant / descendant).
Lancer : python3 -m unittest tests.test_v230"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "GESCOL"

ECOLE = r'''
import io, os, sys, tempfile
from datetime import date
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"; os.environ[P + "_EDITION"] = "publique"
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
auj = date.today().isoformat()
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    cid = ex("INSERT INTO classes (nom, niveau, ecole_id) VALUES ('CM1 A', 'CM1', 1)")
    for i, s in enumerate("MFFMF"):
        ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, classe_id, statut, date_inscription, annee) VALUES (?,?,?,?,?, 'inscrit', ?, ?)",
           (f"T23{i}", f"ELEVE{i}", "Test", s, cid, auj, "2026-2027"))
    for n, f in (("AGO", "Enseignant"), ("BIO", "Enseignante"), ("CAKPO", "Gardien")):
        ex("INSERT INTO personnel (nom, prenoms, fonction) VALUES (?,?,?)", (n, "X", f))
    nom_ecole = q("SELECT valeur FROM parametres WHERE cle='ecole_nom'", un=True)
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302
import registres as R
with app.test_request_context():
    pass
# --- fiche signalétique : coordonnées contrôlées puis reprises dans la fiche de rentrée
r = c.post("/territoire/ecole", data={"latitude": "95", "longitude": "2.6"}, follow_redirects=True)
assert "Coordonnées invalides" in r.data.decode()
r = c.post("/territoire/ecole", data={"latitude": "7,3637", "longitude": "2.6086", "statutJuridique": "Public", "numeroAutorisation": "A-12",
                                      "dateAutorisation": "2001-09-15", "pointEau": "Oui", "latrines": "6"}, follow_redirects=True)
assert "Fiche signalétique enregistrée" in r.data.decode(), r.data.decode()[-800:]
h = c.get("/reg/territoire/rentree").data.decode()
assert 'value="5"' in h and "7.3637" in h, "valeurs proposées (effectif 5, latitude)"
# --- fiche de rentrée : création, transmission, verrouillage
r = c.post("/reg/territoire/rentree/0", data={"niveau": "ECOLE", "entite": "EPP TEST", "effG": "2", "effF": "3", "effT": "5",
                                               "ensPoste": "2", "latitude": "7.3637", "longitude": "2.6086"})
assert r.status_code == 302, r.status_code
with app.app_context():
    f = dict(q("SELECT * FROM reg_territoire_rentree", un=True))
assert (f["statut"] or "BROUILLON") == "BROUILLON"
h = c.get("/reg/territoire/rentree").data.decode()
assert "Transmettre" in h
assert c.post(f"/territoire/rentree/{f['id']}/transmettre").status_code == 302
with app.app_context():
    f = dict(q("SELECT * FROM reg_territoire_rentree", un=True))
assert f["statut"] == "TRANSMISE" and f["dateTransmission"] == auj
r = c.post(f"/reg/territoire/rentree/{f['id']}", data={"niveau": "ECOLE", "entite": "EPP TEST", "effT": "999"}, follow_redirects=True)
assert "déjà transmise" in r.data.decode()
with app.app_context():
    assert q("SELECT effT FROM reg_territoire_rentree", un=True)["effT"] == 5
    # décision de la CS descendue par la synchronisation : renvoi avec motif
    ex("INSERT INTO reg_territoire_retours (portee, annee, objet, cle, destinataire, statut, date, decidePar, motif) VALUES (-1,?,?,?,?,?,?,?,?)",
       (f["annee"], "Fiche de rentrée", f"rentree|epp test|{f['annee']}", "EPP TEST", "RENVOYEE", auj, "CS — CS POBE", "Préciser les salles"))
h = c.get("/reg/territoire/rentree").data.decode()
with app.app_context():
    f = dict(q("SELECT * FROM reg_territoire_rentree", un=True))
assert f["statut"] == "RENVOYEE" and f["motifRenvoi"] == "Préciser les salles", f
assert "Transmettre" in h
a = c.get("/liaison/alertes").data.decode()
assert "Fiche de rentrée renvoyée" in a
# --- courrier administratif : envoi (registre du secrétariat « départ »), accusé de lecture descendu
r = c.post("/reg/communication/courrier/0", data={"niveau": "ECOLE", "entite": "EPP TEST", "type": "Rapport", "reference": "R-01", "date": auj,
                                                  "objet": "Rapport de rentrée", "destNiveau": "CS", "texte": "Texte"})
assert r.status_code == 302
with app.app_context():
    x = dict(q("SELECT * FROM reg_communication_courrier", un=True))
assert c.post(f"/territoire/courrier/{x['id']}/envoyer").status_code == 302
with app.app_context():
    x = dict(q("SELECT * FROM reg_communication_courrier", un=True))
    assert x["statut"] == "Envoyé"
    d = q("SELECT * FROM courriers WHERE sens='depart'", un=True)
    assert d and d["numero"].startswith("D-") and d["objet"] == "Rapport de rentrée"
    ex("INSERT INTO reg_territoire_retours (portee, annee, objet, cle, destinataire, statut, date, decidePar) VALUES (-1,?,?,?,?,?,?,?)",
       (x["annee"], "Courrier", f"courrier|epp test|r-01|rapport de rentree|{auj}", "EPP TEST", "Reçu", auj, "CS — CS POBE"))
c.get("/reg/communication/courrier")
with app.app_context():
    x = dict(q("SELECT * FROM reg_communication_courrier", un=True))
    assert x["statut"] == "Reçu" and x["dateLecture"] == auj, x
r = c.post(f"/reg/communication/courrier/{x['id']}", data={"objet": "modifié"}, follow_redirects=True)
assert "déjà envoyé" in r.data.decode()
# --- présence du personnel : appel du jour et statistiques du mois
h = c.get("/territoire/presences/appel").data.decode()
assert "AGO X" in h and "Maladie" in h
r = c.post("/territoire/presences/appel", data={"date": auj, "s0": "Présent", "s1": "Maladie", "m1": "certificat", "s2": "Retard"})
assert r.status_code == 302
with app.app_context():
    assert q("SELECT COUNT(*) n FROM reg_presences_agents", un=True)["n"] == 3
c.post("/territoire/presences/appel", data={"date": auj, "s0": "Absent", "s1": "Maladie", "s2": "Retard"})
with app.app_context():
    assert q("SELECT COUNT(*) n FROM reg_presences_agents", un=True)["n"] == 3        # mise à jour, pas de doublon
h = c.get("/territoire/presences/mois?mois=" + auj[:7]).data.decode()
assert "33.3 %" in h, h[-2000:]
# --- incidents de discipline (élève de l'école)
with app.app_context():
    eid = q("SELECT id FROM eleves LIMIT 1", un=True)["id"]
assert c.post("/reg/discipline/incidents/0", data={"eleve": str(eid), "date": auj, "description": "Bagarre", "sanction": "Avertissement écrit",
                                                    "decidePar": "Directeur", "parents": "Oui"}).status_code == 302
assert "Bagarre" in c.get("/reg/discipline/incidents").data.decode()
# --- visites : statut et prochaine visite (rubriques ajoutées en fin de registre)
import openpyxl
wb = openpyxl.load_workbook(io.BytesIO(c.get("/reg/inspection/visites/modele.xlsx").data))
ent = [x.value for x in next(wb.active.iter_rows(max_row=8)) if x.value] or []
tout = " ".join(str(v.value) for row in wb.active.iter_rows(max_row=8) for v in row if v.value)
assert "Statut de la visite" in tout and "Date de la prochaine visite" in tout, tout
assert c.post("/reg/inspection/visites/0", data={"niveau": "ECOLE", "entite": "EPP TEST", "enseignant": "AGO X", "date": "2000-01-01",
                                                  "statutVisite": "Planifiée"}).status_code == 302
assert "Visite planifiée dépassée" in c.get("/liaison/alertes").data.decode()
# --- besoins : catégories ajoutées, données existantes inchangées
assert "Eau, hygiène et assainissement" in c.get("/reg/patrimoine/besoins").data.decode()
# --- école : pas de niveau national ni d'API
assert c.get("/territoire/national").status_code == 404
assert c.get("/api/stats.json?jeton=x").status_code == 401
print("OK-230-ecole")
'''

JUR = r'''
import json, os, re, subprocess, sys, tempfile
from datetime import date
P = os.environ["PREFIXE_SCRIPT"]
ED = sys.argv[1]
D = tempfile.mkdtemp()
os.environ.update({P + "_EDITION": ED, P + "_DATA": D})
subprocess.run([sys.executable, "demo_juridiction.py"], check=True, stdout=subprocess.DEVNULL)
sys.path.insert(0, os.getcwd())
from app import app, ex, q
from werkzeug.security import generate_password_hash
app.config["TESTING"] = True
auj = date.today().isoformat()
c = app.test_client()
assert c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"}).status_code == 302
with app.app_context():
    e = dict(q("SELECT * FROM jur_ecoles WHERE actif=1 ORDER BY id LIMIT 1", un=True))
    an = q("SELECT valeur FROM parametres WHERE cle='annee_active'", un=True)
    import config
    annee = config.ANNEE_ACTIVE
    statut0 = "TRANSMISE" if ED == "cs" else "VALIDEE_CS"
    fid = ex("INSERT INTO reg_territoire_rentree (portee, annee, niveau, entite, effG, effF, effT, statut, dateTransmission) "
             "VALUES (?,?,?,?,?,?,?,?,?)", (e["id"], annee, "ECOLE", e["nom"], 10, 12, 22, statut0, auj))
h = c.get("/territoire/rentree/suivi").data.decode()
assert e["nom"] in h and {"TRANSMISE": "Transmise", "VALIDEE_CS": "Validée CS"}[statut0] in h, h[-1500:]
r = c.post(f"/territoire/rentree/{fid}/decider", data={"statut": "Renvoyée", "motif": ""}, follow_redirects=True)
assert "indiquez le motif" in r.data.decode()
if ED == "cs":
    c.post(f"/territoire/rentree/{fid}/decider", data={"statut": "Validée CS"})
    with app.app_context():
        assert q("SELECT statut FROM reg_territoire_rentree WHERE id=?", (fid,), un=True)["statut"] == "VALIDEE_CS"
        rt = q("SELECT * FROM reg_territoire_retours", un=True)
        assert rt["statut"] == "VALIDEE_CS" and rt["portee"] == 0 and rt["destinataire"] == e["nom"]
    r = c.post(f"/territoire/rentree/{fid}/decider", data={"statut": "Clôturée"}, follow_redirects=True)
    assert "impossible" in r.data.decode()
else:
    c.post(f"/territoire/rentree/{fid}/decider", data={"statut": "Validée département"})
    c.post(f"/territoire/rentree/{fid}/decider", data={"statut": "Clôturée"})
    with app.app_context():
        assert q("SELECT statut FROM reg_territoire_rentree WHERE id=?", (fid,), un=True)["statut"] == "CLOTUREE"
        assert q("SELECT COUNT(*) n FROM reg_territoire_retours WHERE objet='Fiche de rentrée'", un=True)["n"] == 2
# --- courrier reçu : non lu (alerte) → reçu (accusé, registre « arrivée ») → traité
niv = "CS" if ED == "cs" else "DDEMP"
with app.app_context():
    cid = ex("INSERT INTO reg_communication_courrier (portee, annee, niveau, entite, type, reference, date, objet, destNiveau, statut, dateEnvoi) "
             "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (e["id"], annee, "ECOLE", e["nom"], "Demande", "D-7", auj, "Demande de tables-bancs", niv, "Envoyé", auj))
h = c.get("/territoire/courrier").data.decode()
assert "Demande de tables-bancs" in h and "Non lu" in h
assert "Courrier non lu" in c.get("/liaison/alertes").data.decode()
h = c.get(f"/territoire/courrier/{cid}").data.decode()
assert "Reçu" in h
with app.app_context():
    x = q("SELECT * FROM reg_communication_courrier WHERE id=?", (cid,), un=True)
    assert x["statut"] == "Reçu" and x["dateLecture"] == auj
    assert q("SELECT COUNT(*) n FROM courriers WHERE sens='arrivee' AND objet='Demande de tables-bancs'", un=True)["n"] == 1
c.post(f"/territoire/courrier/{cid}", data={"statut": "Traité"})
with app.app_context():
    assert q("SELECT statut FROM reg_communication_courrier WHERE id=?", (cid,), un=True)["statut"] == "Traité"
# --- référentiel des structures : arbre amorcé (ministère, structure, services)
assert c.post("/territoire/structures/arbre").status_code == 302
h = c.get("/territoire/structures/arbre").data.decode()
assert "Ministère des Enseignements Maternel et Primaire" in h and h.count("<li>") >= 3
c.post("/territoire/structures/arbre")
with app.app_context():
    n1 = q("SELECT COUNT(*) n FROM reg_territoire_structures", un=True)["n"]
assert n1 == h.count("<li>")                               # pas de double amorçage
# --- niveau national : jeton, API, rôle observateur en lecture seule
r = c.post("/territoire/national")
jeton = re.search(r"<code>([A-Za-z0-9_-]{20,})</code>", r.data.decode()).group(1)
with app.app_context():
    assert jeton not in json.dumps([dict(x) for x in q("SELECT * FROM parametres")])   # seule l'empreinte est gardée
anon = app.test_client()
assert anon.get("/api/stats.json").status_code == 401
assert anon.get("/api/stats.json", headers={"X-Jeton": "faux"}).status_code == 401
r = anon.get("/api/stats.json", headers={"X-Jeton": jeton})
assert r.status_code == 200
j = r.get_json()
assert "indicateurs" in j and "fiches_rentree" in j and j["annee"] == annee, j
assert "nom" not in json.dumps(j.get("indicateurs"))
with app.app_context():
    ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, actif, doit_changer_mdp) VALUES ('obs', 'Observateur', 'observateur', ?, 1, 0)",
       (generate_password_hash("observ123"),))
o = app.test_client()
assert o.post("/login", data={"identifiant": "obs", "mdp": "observ123"}).status_code == 302
r = o.get("/juridiction/ecoles")
assert r.status_code == 302 and r.location.endswith("/territoire/national"), (r.status_code, r.location)
assert o.get("/territoire/national").status_code == 200
assert o.post("/territoire/national").status_code == 403
assert o.post(f"/territoire/rentree/{fid}/decider", data={"statut": "Validée CS"}).status_code in (302, 403)
with app.app_context():
    assert q("SELECT COUNT(*) n FROM reg_territoire_retours WHERE objet='Fiche de rentrée'", un=True)["n"] == (1 if ED == "cs" else 2)
print("OK-230-" + ED)
'''


def lancer(script, *args):
    env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
    for k in list(env):
        if k.endswith(("_EDITION", "_DATA")) and k.startswith(("GESCOL", "GESCOL")):
            env.pop(k)
    return subprocess.run([sys.executable, "-c", script] + list(args), cwd=RACINE, env=env, capture_output=True, text=True, timeout=1200)


CEP = r'''
import io, os, subprocess, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
ED = sys.argv[1]
D = tempfile.mkdtemp()
os.environ.update({P + "_EDITION": ED, P + "_DATA": D})
subprocess.run([sys.executable, "demo_juridiction.py"], check=True, stdout=subprocess.DEVNULL)
sys.path.insert(0, os.getcwd())
from app import app, ex, q
import config, openpyxl, pypdf
app.config["TESTING"] = True
c = app.test_client()
assert c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"}).status_code == 302
import m_cep2027 as M
# règle : salles nécessaires = arrondi supérieur (total / n), écart, situation
x = M.calculer({"offG": 150, "offF": 140, "libG": 3, "libF": 2, "offH": 1, "salles": 8}, 35)
assert (x["tt"], x["th"], x["necessaires"], x["ecart"]) == (295, 1, 9, -1) and x["situation"] == "Capacité dépassée : 1 salle(s) manquante(s)", x
x = M.calculer({"offG": 60, "offF": 60, "salles": 4, "observations": "Centre rénové"}, 30)
assert x["necessaires"] == 4 and x["situation"] == "Capacité suffisante" and x["observation"] == "Centre rénové"
assert M.calculer({}, 30)["situation"] == "" and M.nom_court("Circonscription scolaire de Pobè") == "POBÈ"
if ED == "cs":
    assert c.post("/examens/cep2027/pobe").status_code == 302
    c.post("/examens/cep2027/pobe")                                            # pas de doublon
    with app.app_context():
        noms = [r["centre"] for r in q("SELECT centre FROM reg_examens_salles ORDER BY ordre")]
        assert noms == ["POBE-CENTRE", "POBE-NORD", "OKE-OLA", "OKE-ATA", "ONIGBOLO", "TOWE"], noms
        ex("UPDATE reg_examens_salles SET offG=150, offF=140, libG=3, libF=2, offH=1, salles=8 WHERE centre='POBE-CENTRE'")
        ex("UPDATE reg_examens_salles SET offG=60, offF=55, salles=5 WHERE centre='POBE-NORD'")
        # candidats inscrits : pré-remplissage des cases vides seulement
        for i, (centre, sexe) in enumerate([("OKE-OLA", "M"), ("OKE-OLA", "F"), ("OKE-OLA", "F"), ("POBE-NORD", "M")]):
            ex("INSERT INTO reg_examens_candidats (portee, annee, niveau, entite, nom, sexe, centre, statut) VALUES (0,?,?,?,?,?,?,?)",
               (config.ANNEE_ACTIVE, "ECOLE", "EPP X", f"C{i}", sexe, centre, "Inscrit"))
    c.post("/examens/cep2027/pre-remplir")
    with app.app_context():
        r = q("SELECT * FROM reg_examens_salles WHERE centre='OKE-OLA'", un=True)
        assert (r["offG"], r["offF"]) == (1, 2)
        assert q("SELECT offG FROM reg_examens_salles WHERE centre='POBE-NORD'", un=True)["offG"] == 60
    h = c.get("/examens/cep2027?n=35").data.decode()
    assert "Capacité dépassée : 1 salle(s) manquante(s)" in h and "Capacité suffisante" in h and "TOTAL" in h
    h = c.get("/examens/cep2027?vue=simple&n=35").data.decode()
    assert "Nombre de salles de composition en bon état disponible" in h
else:
    with app.app_context():
        for por, cs, nom, og, of, sal, maj in [(11, "Circonscription scolaire de Pobè", "POBE-CENTRE", 150, 140, 8, "2026-11-02"),
                                                (12, "CS KETOU", "KETOU-CENTRE", 100, 90, 7, "2026-11-02"), (13, "CS KETOU", "KETOU-CENTRE", 1, 1, 1, "2026-10-01")]:
            ex("INSERT INTO reg_examens_salles (portee, annee, niveau, entite, centre, ordre, offG, offF, salles, maj) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (por, config.ANNEE_ACTIVE, "CS", cs, nom, 1, og, of, sal, maj))
    h = c.get("/examens/cep2027?n=30").data.decode()
    assert h.count("<h3>") == 3 and "Total du département" in h and "480" in h, h[-3000:]
for vue in ("simple", "detaille"):
    r = c.get(f"/examens/cep2027.pdf?vue={vue}&n=35")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    t = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(r.data)).pages)
    assert "TABLEAU DE SYNTHESE DES STATISTIQUES" in t and "SESSION DE JUIN 2027" in t and ("POBÈ" in t or "POBE" in t), t[:600]
    assert "Garçons" in t and "code" in t
    r = c.get(f"/examens/cep2027.xlsx?vue={vue}&n=35")
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    ws = wb[wb.sheetnames[0]]
    assert ws["A1"].value == "TABLEAU DE SYNTHESE DES STATISTIQUES" and ws["A3"].value == "CEP : SESSION DE JUIN 2027"
    if vue == "detaille":
        assert "C6:N6" in [str(m) for m in ws.merged_cells.ranges] and ws["C7"].value == "Candidats officiels"
        assert ws["E9"].value.startswith("=IF(COUNT(C9:D9)") and str(ws["M9"].value).startswith("=IF(COUNT(K9:L9)")
        assert any(str(c_.value or "").startswith("=SUM(") for c_ in ws["C"])
    else:
        assert ws["D6"].value == "Nombre de salles de composition en bon état disponible"
if ED == "ddemp":
    assert "Département" in wb.sheetnames
print("OK-cep-" + ED)
'''


class TestCep2027(unittest.TestCase):
    def test_cs(self):
        r = lancer(CEP, "cs")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK-cep-cs", r.stdout)

    def test_ddemp(self):
        r = lancer(CEP, "ddemp")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK-cep-ddemp", r.stdout)

    def test_synchronisation(self):
        sys.path.insert(0, RACINE)
        import m_sync
        self.assertIn(("examens", "salles"), m_sync.REG_MONTANT)
        self.assertIn(("examens", "salles"), m_sync.REG_AUSSI_DESCENDANT)


class TestTerritoire230(unittest.TestCase):
    def test_ecole(self):
        r = lancer(ECOLE)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK-230-ecole", r.stdout)

    def test_cs(self):
        r = lancer(JUR, "cs")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK-230-cs", r.stdout)

    def test_ddemp(self):
        r = lancer(JUR, "ddemp")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-6000:])
        self.assertIn("OK-230-ddemp", r.stdout)

    def test_synchronisation_suit_les_registres(self):
        sys.path.insert(0, RACINE)
        import m_sync
        self.assertIn(("territoire", "rentree"), m_sync.REG_MONTANT)
        self.assertIn(("communication", "courrier"), m_sync.REG_MONTANT)
        self.assertIn(("territoire", "retours"), m_sync.REG_DESCENDANT)
        self.assertNotIn(("discipline", "incidents"), m_sync.REG_MONTANT)      # données d'élèves : restent à l'école
        app_src = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()
        self.assertLess(app_src.index('"m_territoire"'), app_src.index('"m_sync",'))


if __name__ == "__main__":
    unittest.main()
