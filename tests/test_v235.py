# -*- coding: utf-8 -*-
"""Tests 2.4 : établissement secondaire (m_secondaire) — calculs purs (série d'une classe, mention, décision d'examen, statistiques,
conflits d'emploi du temps, moyenne pondérée) et parcours complet dans les éditions privée et publique : gabarit du programme,
professeurs, conseil de classe calculé depuis les notes, sanctions, emploi du temps (conflits, grille), centres et candidats
(numéros de table, statistiques par série et par sexe), synoptique, filières, stages, fiches PDF signées, Excel.
Lancer : python3 -m unittest tests.test_v235"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")

import m_secondaire as S  # noqa: E402


class CalculsPurs(unittest.TestCase):
    def test_serie_de_classe(self):
        self.assertEqual(S.serie_de_classe("2nde C", "2nde"), "C")
        self.assertEqual(S.serie_de_classe("Tle A1", "Tle"), "A1")
        self.assertEqual(S.serie_de_classe("1ère G2"), "G2")
        self.assertEqual(S.serie_de_classe("Tle D 2", "Tle"), "D")
        self.assertEqual(S.serie_de_classe("6ème A", "6ème"), "Tronc commun")      # section, pas série
        self.assertEqual(S.serie_de_classe("3ème B", "3ème"), "Tronc commun")
        self.assertEqual(S.serie_de_classe("2nde"), "Tronc commun")

    def test_mention_et_decision(self):
        self.assertEqual(S.mention(9.99), "")
        self.assertEqual([S.mention(x) for x in (10, 12, 14, 16, "17,5")], ["Passable", "Assez bien", "Bien", "Très bien", "Très bien"])
        self.assertEqual(S.decision_proposee("BEPC", 10), "Admis")
        self.assertEqual(S.decision_proposee("BEPC", "9,5"), "Ajourné")            # pas de second tour au BEPC
        self.assertEqual(S.decision_proposee("BAC général", 9), "Second tour")
        self.assertEqual(S.decision_proposee("BAC technique", 7.9), "Ajourné")
        self.assertEqual(S.decision_proposee("BAC général", None), "")
        self.assertEqual(S.decision_proposee("BEPC", 15, "Oui"), "Absent")
        self.assertEqual(S.decision_retenue({"examen": "BEPC", "moyenne": 15, "decisionJury": "Ajourné"}), "Ajourné")   # le jury l'emporte
        self.assertEqual(S.decision_retenue({"examen": "BEPC", "moyenne": 15}), "Admis")

    def test_statistiques(self):
        L = [{"examen": "BEPC", "serie": "", "sexe": "F", "moyenne": 12}, {"examen": "BEPC", "serie": "", "sexe": "F", "moyenne": 8},
             {"examen": "BEPC", "serie": "", "sexe": "M", "moyenne": 11}, {"examen": "BEPC", "serie": "", "sexe": "M", "absent": "Oui"},
             {"examen": "BAC général", "serie": "D", "sexe": "M", "moyenne": 9}]
        groupes, total = S.stats_candidats(L)
        b = S.resume_stats(groupes[("BEPC", "")])
        self.assertEqual((b["inscrits"], b["presents"], b["admis"], b["admis_f"], b["admis_g"]), (4, 3, 2, 1, 1))
        self.assertEqual(b["taux"], 66.7)
        self.assertEqual(b["taux_f"], 50.0)
        self.assertEqual(S.resume_stats(groupes[("BAC général", "D")])["second"], 1)
        self.assertEqual(S.resume_stats(total)["inscrits"], 5)
        self.assertIsNone(S.taux(1, 0))

    def test_conflits_emploi(self):
        L = [{"id": 1, "classe": "2nde C", "jour": "Lundi", "debut": "8h00", "fin": "10h00", "professeur": "M. Z", "salle": "S1"},
             {"id": 2, "classe": "Tle D", "jour": "Lundi", "debut": "9h00", "fin": "11h00", "professeur": "M. Z", "salle": "S2"},
             {"id": 3, "classe": "3ème A", "jour": "Lundi", "debut": "10h00", "fin": "12h00", "professeur": "Mme Y", "salle": "S2"},
             {"id": 4, "classe": "3ème A", "jour": "Mardi", "debut": "8h00", "fin": "10h00", "professeur": "M. Z", "salle": "S1"}]
        c = S.conflits_emploi(L)
        self.assertEqual(set(c), {1, 2, 3})                                         # 1 et 2 (professeur) ; 2 et 3 (salle)
        self.assertIn(1, c)
        self.assertIn(2, c)
        self.assertIn(3, c)
        self.assertNotIn(4, c)                                                      # un autre jour : aucun conflit
        self.assertTrue(any("professeur" in m for m in c[1]))
        self.assertTrue(any("salle" in m for m in c[3]))
        self.assertEqual(S.conflits_emploi([{"id": 1, "jour": "Lundi", "debut": "8h00", "fin": "9h00", "classe": "A"},
                                            {"id": 2, "jour": "Lundi", "debut": "9h00", "fin": "10h00", "classe": "A"}]), {})   # bout à bout : pas de conflit

    def test_moyenne_ponderee(self):
        self.assertEqual(S.moyenne_eleve([(10, 3), (16, 1)], "2nde"), 11.5)         # (30 + 16) / 4
        self.assertEqual(S.moyenne_eleve([(10, 3), (16, 1)], "6ème"), 13.0)         # sans coefficient en 6ème et 5ème
        self.assertIsNone(S.moyenne_eleve([], "3ème"))
        self.assertEqual(S.stats_moyennes([12, 8, None, 10])["sup10"], 2)

    def test_gabarit(self):
        lignes = S.gabarit(["Mathématiques", "Espagnol", "Philosophie", "Anglais"], {"Mathématiques": 3, "Philosophie": 2})
        par = {(n, s, m) for n, s, m, _c, _h in lignes}
        self.assertNotIn(("6ème", "Tronc commun", "Espagnol"), par)
        self.assertIn(("4ème", "Tronc commun", "Espagnol"), par)
        self.assertNotIn(("2nde", "C", "Philosophie"), par)
        self.assertIn(("Tle", "D", "Philosophie"), par)
        self.assertIn(("2nde", "A1", "Mathématiques"), par)
        self.assertEqual({c for n, s, m, c, _h in lignes if m == "Mathématiques"}, {3})


SCRIPT = r'''
import html, io, os, re, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
import config
from app import app, q as _q, ex as _ex
import openpyxl
app.config["TESTING"] = True

def q(*a, **k):                      # requêtes hors requête : contexte d'application propre, lignes converties en dict
    with app.app_context():
        r = _q(*a, **k)
        return [dict(x) for x in r] if isinstance(r, list) else (dict(r) if r else r)
def ex(*a, **k):
    with app.app_context():
        return _ex(*a, **k)

def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.headers.get("Location"), r.data[-1500:]); return r
def txt(r): return html.unescape(ok(r).data.decode())
def pdf(r):
    ok(r); assert r.mimetype == "application/pdf" and r.data.startswith(b"%PDF"), (r.request.path, r.mimetype); return r
def xlsx(r):
    wb = openpyxl.load_workbook(io.BytesIO(ok(r).data)); return [[c.value for c in l] for l in wb.active.iter_rows()]

with app.app_context():
    ex("UPDATE utilisateurs SET doit_changer_mdp=0 WHERE identifiant='admin'")
c = app.test_client()
assert c.post("/login", data={"identifiant": "admin", "mdp": "admin123"}).status_code == 302

# sans classe du secondaire : le menu est masqué, les pages restent ouvertes
assert "Établissement secondaire" not in txt(c.get("/"))

with app.app_context():
    c6 = ex("INSERT INTO classes (nom, niveau, frais_scolarite) VALUES ('6ème A', '6ème', 0)")
    c2 = ex("INSERT INTO classes (nom, niveau, frais_scolarite) VALUES ('2nde C', '2nde', 0)")
    ct = ex("INSERT INTO classes (nom, niveau, frais_scolarite) VALUES ('Tle D', 'Tle', 0)")
    ids = []
    for i, (nom, sexe, cl) in enumerate([("ADJOVI", "F", c2), ("BIO", "M", c2), ("CHABI", "F", c2), ("DOSSOU", "M", ct), ("EDAH", "F", c6)]):
        ids.append(ex("INSERT INTO eleves (matricule, nom, prenoms, sexe, classe_id, statut, date_inscription, annee) VALUES (?,?,?,?,?,'inscrit','2026-10-01','2026-2027')",
                     ("M%03d" % i, nom, "Prénom", sexe, cl)))
    math = q("SELECT id FROM matieres WHERE cycle='secondaire' AND code='MATH'", un=True)["id"]
    pct = q("SELECT id FROM matieres WHERE cycle='secondaire' AND code='PCT'", un=True)["id"]
    # 2nde C : ADJOVI (MATH 14, PCT 10), BIO (MATH 8, PCT 12), CHABI sans note
    for eid, m, v in [(ids[0], math, 14), (ids[0], pct, 10), (ids[1], math, 8), (ids[1], pct, 12)]:
        ex("INSERT INTO notes (eleve_id, matiere_id, periode, annee, valeur) VALUES (?,?,?,?,?)", (eid, m, "Devoir 1 – Trimestre 1", "2026-2027", v))

page = txt(c.get("/"))
assert "Établissement secondaire" in page and "/secondaire/synoptique" in page

# toutes les pages s'ouvrent
for rcle in ("programme", "professeurs", "conseils", "sanctions", "emploi", "centres", "candidats", "filieres", "ateliers", "stages", "etablissement"):
    t = txt(c.get("/reg/sec/%s" % rcle)); assert "Établissement secondaire" in t, rcle
    assert xlsx(c.get("/reg/sec/%s.xlsx" % rcle)) is not None
    assert xlsx(c.get("/reg/sec/%s/modele.xlsx" % rcle)) is not None
for u in ("/secondaire/synoptique", "/secondaire/examens/statistiques", "/secondaire/emploi/grille"):
    txt(c.get(u))

def ajouter(rcle, **champs):
    ok(c.post("/reg/sec/%s/0" % rcle, data=champs), 302)
    return q("SELECT * FROM reg_sec_%s ORDER BY id DESC LIMIT 1" % rcle, un=True)

# ---- programme : gabarit, sans doublon
ok(c.post("/secondaire/programme/gabarit"), 302)
n1 = q("SELECT COUNT(*) n FROM reg_sec_programme", un=True)["n"]
assert n1 > 100, n1
assert q("SELECT COUNT(*) n FROM reg_sec_programme WHERE niveauClasse='6ème' AND matiere LIKE '%Espagnol%'", un=True)["n"] == 0
assert q("SELECT COUNT(*) n FROM reg_sec_programme WHERE niveauClasse='Tle' AND serie='D' AND matiere='Philosophie'", un=True)["n"] == 1
ok(c.post("/secondaire/programme/gabarit"), 302)
assert q("SELECT COUNT(*) n FROM reg_sec_programme", un=True)["n"] == n1
# coefficient propre à la série C pour les mathématiques (2nde C) : 5
ex("UPDATE reg_sec_programme SET coefficient=5 WHERE niveauClasse='2nde' AND serie='C' AND matiere='Mathématiques'")

# ---- professeurs
ajouter("professeurs", nom="AGBO", prenoms="Léa", sexe="F", statut=("Agent permanent de l'État (APE)" if ED == "publique" else "Enseignant de l'établissement (privé)"),
        discipline="Mathématiques", heures="18")
ajouter("professeurs", nom="TOKO", prenoms="Paul", sexe="M", statut="Vacataire", discipline="Anglais", heures="12")

# ---- conseil de classe calculé depuis les notes (coefficient propre à la série C : MATH 5, PCT : valeur de la table)
ok(c.post("/secondaire/conseils/calculer", data={"classe": "2nde C", "periode": "Trimestre 1"}), 302)
cons = q("SELECT * FROM reg_sec_conseils WHERE classe='2nde C' AND periode='Trimestre 1'", un=True)
assert cons["effectif"] == 3 and cons["composes"] == 2, dict(cons)
coef_pct = q("SELECT coefficient FROM matieres WHERE id=?", (pct,), un=True)["coefficient"]
attendu_adjovi = round((14 * 5 + 10 * coef_pct) / (5 + coef_pct), 2); attendu_bio = round((8 * 5 + 12 * coef_pct) / (5 + coef_pct), 2)
assert abs(cons["moyenneMax"] - max(attendu_adjovi, attendu_bio)) < 0.011 and abs(cons["moyenneMin"] - min(attendu_adjovi, attendu_bio)) < 0.011, (dict(cons), attendu_adjovi, attendu_bio)
ok(c.post("/secondaire/conseils/calculer", data={"classe": "2nde C", "periode": "Trimestre 1"}), 302)          # recalcul : pas de doublon
assert q("SELECT COUNT(*) n FROM reg_sec_conseils", un=True)["n"] == 1
ex("UPDATE reg_sec_conseils SET president='M. LE PROVISEUR', passage=1, redoublement=1 WHERE id=?", (cons["id"],))
t = pdf(c.get("/reg/sec/conseils/%d/pv.pdf" % cons["id"]))
import pdfplumber
def texte(r):
    with pdfplumber.open(io.BytesIO(r.data)) as d: return " ".join((p.extract_text() or "") for p in d.pages).replace("\n", " ")
assert "conseil de classe" in texte(t).lower() and "2nde C" in texte(t)

# ---- sanctions
s = ajouter("sanctions", eleve=str(ids[1]), classe="2nde C", dateFait="2026-11-03", nature="Retard", sanction="Avertissement", parentInforme="Oui", faits="Trois retards.")
assert "sanction" in texte(pdf(c.get("/reg/sec/sanctions/%d/fiche.pdf" % s["id"]))).lower()

# ---- emploi du temps : conflit de professeur, grille
ajouter("emploi", classe="2nde C", jour="Lundi", debut="8h00", fin="10h00", matiere="Mathématiques", professeur="AGBO", salle="S1")
ajouter("emploi", classe="Tle D", jour="Lundi", debut="9h00", fin="11h00", matiere="Mathématiques", professeur="AGBO", salle="S2")
ajouter("emploi", classe="Tle D", jour="Mardi", debut="8h00", fin="10h00", matiere="Anglais", professeur="TOKO", salle="S2")
t = txt(c.get("/reg/sec/emploi")); assert "même professeur : AGBO" in t, t[-1500:]
g = txt(c.get("/secondaire/emploi/grille?classe=Tle D")); assert "Anglais" in g and "TOKO" in g and "en conflit" in g
assert "alerte" in txt(c.get("/reg/sec/emploi")).lower()

# ---- centres et candidats
ajouter("centres", code="C1", nom="CEG Test", examen="BEPC", salles="3", capacite="30")
cand = [("BEPC", "", "ZINSOU", "F", "12"), ("BEPC", "", "ABOKI", "M", "9"), ("BEPC", "", "YAYI", "F", "15,5"), ("BEPC", "", "KPADE", "M", ""),
        ("BAC général", "D", "HOUNKPE", "M", "9"), ("BAC général", "D", "GBEDO", "F", "13")]
for ex_, serie, nom, sexe, moy in cand:
    ajouter("candidats", examen=ex_, serie=serie, nom=nom, prenoms="X", sexe=sexe, dateNaissance="2008-05-01", centre="CEG Test", moyenne=moy)
ok(c.post("/secondaire/examens/numeroter?annee=2026-2027", data={"examen": ""}), 302)
nums = [r["numTable"] for r in q("SELECT numTable FROM reg_sec_candidats ORDER BY examen, centre, nom")]
assert all(nums) and len(set(nums)) == len(nums), nums
assert q("SELECT numTable FROM reg_sec_candidats WHERE nom='ABOKI'", un=True)["numTable"] == "BEPC-0001"     # ordre alphabétique dans l'examen
ok(c.post("/secondaire/examens/numeroter?annee=2026-2027", data={"examen": ""}), 302)                          # idempotent
assert [r["numTable"] for r in q("SELECT numTable FROM reg_sec_candidats ORDER BY examen, centre, nom")] == nums
t = txt(c.get("/secondaire/examens/statistiques?examen=BEPC"))
assert "BEPC" in t and "66,7" in t, t[-2500:]                                                                    # 2 admis / 3 présents
rows = xlsx(c.get("/secondaire/examens/statistiques.xlsx"))
assert rows[0][0] == "Examen" and rows[-1][0] == "Total" and rows[-1][2] == 6, rows
assert "STATISTIQUES" in texte(pdf(c.get("/secondaire/examens/statistiques.pdf"))).upper()
cid = q("SELECT id FROM reg_sec_candidats WHERE nom='ZINSOU'", un=True)["id"]
t = texte(pdf(c.get("/reg/sec/candidats/%d/convocation.pdf" % cid))); assert "ZINSOU" in t and "BEPC-" in t

# ---- ETP
ajouter("filieres", intitule="Électricité", domaine="Industriel (mécanique, électricité, froid…)", diplome="BT", cycle="2nd cycle", duree="3", capacite="40", effectif="35")
ajouter("ateliers", atelier="Atelier électricité", filiere="Électricité", capacite="20", etat="Bon")
st = ajouter("stages", eleve=str(ids[3]), filiere="Électricité", entreprise="SBEE", tuteur="M. HOUNSA", dateDebut="2026-12-01", dateFin="2026-12-15", duree="15", note="14,5")
assert "SBEE" in texte(pdf(c.get("/reg/sec/stages/%d/attestation.pdf" % st["id"])))

# ---- identité et synoptique
ajouter("etablissement", typeEtab="Public (lycée)", cycles="1er et 2nd cycles", ddestfp="DDESTFP Test", directeur="M. LE PROVISEUR")
t = txt(c.get("/secondaire/synoptique")); assert "DDESTFP Test" in t and "2nde" in t
rows = xlsx(c.get("/secondaire/synoptique.xlsx"))
tot = [r for r in rows if r[0] == "Total"][0]
assert tot[2] == 3 and tot[3] == 2 and tot[4] == 3 and tot[5] == 5, rows                                          # 3 classes, 2 G, 3 F, 5 élèves
assert any(r[0] == "Professeurs" and r[1] == 2 for r in rows), rows
assert "SYNOPTIQUE" in texte(pdf(c.get("/secondaire/synoptique.pdf"))).upper()

# ---- la synthèse pour les tableaux de bord et l'import / export Excel commun
import m_secondaire
with app.test_request_context():
    pass
x = xlsx(c.get("/reg/sec/candidats.xlsx")); assert len(x) == 7 and "Mention" in x[0] and "Décision retenue" in x[0], x[0]
print("OK", ED)
'''


def lancer(edition):
    env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE, EDITION_SCRIPT=edition)
    return subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)


class Parcours(unittest.TestCase):
    def _edition(self, ed):
        r = lancer(ed)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3500:])
        self.assertIn("OK " + ed, r.stdout)

    def test_edition_privee(self):
        self._edition("privee")

    def test_edition_publique(self):
        self._edition("publique")


if __name__ == "__main__":
    unittest.main()
