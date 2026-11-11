# -*- coding: utf-8 -*-
"""Tests 2.4.1 : petit magasin et grand magasin de la cantine (m_magasins_cantine).
Calculs purs (ration × effectif × 5 jours, consommation du jour, reste, situation du grand magasin, fiche de stock) et parcours
complet dans les éditions privée et publique : rations, prélèvement hebdomadaire (sortie du grand magasin), consommation par jour,
retour du reste (manuel puis automatique avant la semaine suivante), réouverture, suppression, bilans journalier / hebdomadaire /
mensuel / annuel (écran, PDF, Excel), fiche de stock par vivre, cahier des menus hebdomadaires.
Lancer : python3 -m unittest tests.test_v241"""
import os
import subprocess
import sys
import unittest
from datetime import date

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
os.environ.setdefault(PREFIXE + "_SANS_PRECHARGEMENT", "1")

import m_magasins_cantine as M  # noqa: E402


class CalculsPurs(unittest.TestCase):
    def test_prelevement_de_la_semaine(self):
        # ration (g) × effectif moyen par jour × 5 jours ÷ 1000
        self.assertEqual(M.quantite_semaine(150, 220), 165.0)
        self.assertEqual(M.quantite_semaine(40, 220), 44.0)
        self.assertEqual(M.quantite_semaine(3, 220), 3.3)
        self.assertEqual(M.quantite_semaine(10, 0), 0.0)

    def test_consommation_du_jour(self):
        self.assertEqual(M.quantite_jour(150, 210), 31.5)
        self.assertEqual(M.quantite_jour(0, 210), 0.0)

    def test_reste_et_manque(self):
        self.assertEqual(M.bilan_vivre_semaine(165, 126), (39.0, 0.0))
        self.assertEqual(M.bilan_vivre_semaine(44, 46.2), (0.0, 2.2))
        self.assertEqual(M.bilan_vivre_semaine(10, 10), (0.0, 0.0))

    def test_rations_proposees(self):
        self.assertEqual(M.ration_proposee("Maïs"), 150)
        self.assertEqual(M.ration_proposee("Riz"), 150)
        self.assertEqual(M.ration_proposee("Haricot (niébé)"), 40)
        self.assertEqual(M.ration_proposee("Huile végétale"), 10)
        self.assertEqual(M.ration_proposee("Sel"), 3)
        self.assertIsNone(M.ration_proposee("Sucre"))
        self.assertIsNone(M.ration_proposee("Gari"))

    def test_unites(self):
        self.assertEqual(M.facteur_kg("kg"), 1.0)
        self.assertEqual(M.facteur_kg("sac de 50 kg"), 50.0)
        self.assertEqual(M.facteur_kg("litre"), 1.0)
        self.assertIsNone(M.facteur_kg("boîte"))

    def test_lundi(self):
        self.assertEqual(M.lundi_de(date(2026, 11, 8)), date(2026, 11, 2))     # dimanche
        self.assertEqual(M.lundi_de(date(2026, 11, 2)), date(2026, 11, 2))
        self.assertEqual(M.lundi_de(date(2026, 11, 6)), date(2026, 11, 2))

    def _mv(self):
        def m(i, d, t, x, bon=None, org=None, obs=None):
            return {"id": i, "date": d, "type": t, "quantite": x, "bon_numero": bon, "origine": org, "observations": obs}
        return [m(1, "2026-10-01", "entree", 500, org="ANAN"), m(2, "2026-11-02", "sortie", 165, M.BON_PRELEVEMENT),
                m(3, "2026-11-06", "entree", 39, M.BON_RETOUR), m(4, "2026-11-10", "perte", 2)]

    def test_grand_magasin(self):
        e = M.etat_grand(self._mv(), 1.0, "2026-11-01", "2026-11-30")
        self.assertEqual((e["initial"], e["entrees"], e["retours"], e["prelevements"], e["pertes"], e["final"]), (500.0, 0.0, 39.0, 165.0, 2.0, 372.0))
        self.assertEqual(e["ecart_inventaire"], 0.0)
        e = M.etat_grand(self._mv(), 1.0, "2026-10-01", "2026-10-31")
        self.assertEqual((e["initial"], e["entrees"], e["final"]), (0.0, 500.0, 500.0))

    def test_grand_magasin_sacs(self):
        mv = [{"id": 1, "date": "2026-10-01", "type": "entree", "quantite": 10, "bon_numero": None}]      # 10 sacs de 50 kg
        e = M.etat_grand(mv, 50.0, "2026-10-01", "2026-10-31")
        self.assertEqual((e["entrees"], e["final"]), (500.0, 500.0))

    def test_fiche_de_stock(self):
        lg = M.fiche_stock(self._mv(), 1.0, "2026-10-01", "2026-12-31")
        self.assertEqual(lg[0][:6], ("2026-10-01", 0.0, 500.0, 500.0, 0.0, 500.0))             # entrée de dotation
        self.assertEqual(lg[1][:6], ("2026-11-02", 500.0, 0.0, 500.0, 165.0, 335.0))           # prélèvement
        self.assertEqual(lg[2][:6], ("2026-11-06", 335.0, 39.0, 374.0, 0.0, 374.0))            # retour
        self.assertEqual(lg[3][:6], ("2026-11-10", 374.0, 0.0, 374.0, 2.0, 372.0))             # perte
        # l'ancien stock est reporté sur l'année suivante
        lg = M.fiche_stock(self._mv(), 1.0, "2026-11-05", "2026-12-31")
        self.assertEqual(lg[0][1], 335.0)


SCRIPT = r'''
import html, io, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]; ED = os.environ["EDITION_SCRIPT"]
os.environ[P + "_EDITION"] = ED; os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
from app import app, q as _q, ex as _ex
import openpyxl
app.config["TESTING"] = True

def q(*a, **k):
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

# vivres types (riz, maïs, haricot, soja, gari, huile, sel…), puis dotation du grand magasin
ok(c.post("/cantine/stock/vivres/liste-type"), 302)
viv = {v["nom"]: v for v in q("SELECT * FROM cantine_vivres")}
eid = viv["Riz"]["ecole_id"]
def entree(nom, kg, d="2026-10-01"):
    ex("""INSERT INTO cantine_stock_mouvements (ecole_id, vivre_id, annee, date, type, quantite, origine, bon_numero, cree_le, maj)
          VALUES (?,?,'2026-2027',?,'entree',?,'ANAN','BL-1','2026-10-01','2026-10-01')""", (eid, viv[nom]["id"], d, kg))
entree("Maïs", 500); entree("Riz", 300); entree("Haricot (niébé)", 40); entree("Huile végétale", 30); entree("Sel", 20)

def stock(nom):
    mv = q("SELECT * FROM cantine_stock_mouvements WHERE vivre_id=?", (viv[nom]["id"],))
    import m_stock_cantine as S
    return S.calculer_stock(mv)

assert "Petit et grand magasin" in txt(c.get("/cantine/stock"))
page = txt(c.get("/cantine/stock/magasins"))
assert "Rations manquantes" in page and "Grand magasin" in page and "Gari" in page, page[:600]

# sans ration : refus guidé
r = c.post("/cantine/stock/magasins/semaine/nouvelle", data={"debut": "2026-11-02", "garcons": "120", "filles": "100"})
ok(r, 302); assert "rations" in r.headers["Location"], r.headers["Location"]

# rations proposées puis enregistrées
assert "150" in txt(c.get("/cantine/stock/magasins/rations?proposer=1"))
data = {f"r_{v['id']}": r_ for n, v in viv.items() for k, r_ in [("Maïs", "150"), ("Riz", "150"), ("Haricot (niébé)", "40"), ("Huile végétale", "10"), ("Sel", "3")] if n == k}
ok(c.post("/cantine/stock/magasins/rations", data=data), 302)
assert q("SELECT ration_g FROM cantine_rations WHERE vivre_id=?", (viv["Maïs"]["id"],), un=True)["ration_g"] == 150

# ---- semaine 1 : 220 élèves par jour (120 G + 100 F) × 5 jours
r = c.post("/cantine/stock/magasins/semaine/nouvelle", data={"debut": "2026-11-04", "garcons": "120", "filles": "100"}, follow_redirects=True)
page = txt(r)
assert "Stock insuffisant" in page and "Haricot" in page, page[:1500]            # 44 kg à prélever, 40 kg en stock
s1 = q("SELECT * FROM cantine_semaines", un=True)
assert s1["debut"] == "2026-11-02" and s1["statut"] == "ouverte", s1                # ramenée au lundi
prel = {p["vivre_id"]: p["quantite_kg"] for p in q("SELECT * FROM cantine_petit_prelevements")}
assert prel[viv["Maïs"]["id"]] == 165.0 and prel[viv["Haricot (niébé)"]["id"]] == 44.0 and prel[viv["Huile végétale"]["id"]] == 11.0 and prel[viv["Sel"]["id"]] == 3.3, prel
assert stock("Maïs") == 335.0 and stock("Riz") == 135.0, (stock("Maïs"), stock("Riz"))   # sortie du grand magasin
assert q("SELECT COUNT(*) n FROM cantine_stock_mouvements WHERE bon_numero='Prélèvement petit magasin'", un=True)["n"] == 5
# la même semaine ne se prélève pas deux fois
ok(c.post("/cantine/stock/magasins/semaine/nouvelle", data={"debut": "2026-11-03", "garcons": "1", "filles": "1"}), 302)
assert q("SELECT COUNT(*) n FROM cantine_semaines", un=True)["n"] == 1

# ---- jours de cantine : lundi à jeudi, effectifs réels (vendredi sans cantine)
sid = s1["id"]
form = {}
for d, gar, fil in [("2026-11-02", 110, 100), ("2026-11-03", 115, 100), ("2026-11-04", 120, 95), ("2026-11-05", 110, 100)]:
    form.update({f"g_{d}": str(gar), f"f_{d}": str(fil), f"menu_{d}": "Akassa et sauce haricot"})
page = txt(c.post(f"/cantine/stock/magasins/semaine/{sid}/jours", data=form, follow_redirects=True))
assert "4 jour(s) de cantine" in page, page[:800]
cons = {p["vivre_id"]: p["k"] for p in q("SELECT s.vivre_id, SUM(s.quantite_kg) k FROM cantine_petit_sorties s GROUP BY s.vivre_id")}
total = 210 + 215 + 215 + 210                                                          # élèves-jours
assert abs(cons[viv["Maïs"]["id"]] - 150 * total / 1000) < 1e-6, cons                 # 126,6 kg
assert abs(cons[viv["Sel"]["id"]] - 3 * total / 1000) < 1e-6
assert "Semaine du 02/11/2026" in txt(c.get(f"/cantine/stock/magasins/semaine/{sid}"))
# modifier un jour recalcule (et vider un jour le retire)
form["g_2026-11-05"] = ""; form["f_2026-11-05"] = ""
ok(c.post(f"/cantine/stock/magasins/semaine/{sid}/jours", data=form), 302)
assert q("SELECT COUNT(*) n FROM cantine_petit_jours", un=True)["n"] == 3
total = 210 + 215 + 215
cons = {p["vivre_id"]: p["k"] for p in q("SELECT s.vivre_id, SUM(s.quantite_kg) k FROM cantine_petit_sorties s GROUP BY s.vivre_id")}
assert abs(cons[viv["Maïs"]["id"]] - 150 * total / 1000) < 1e-6, cons                 # 96 kg
form["g_2026-11-05"] = "110"; form["f_2026-11-05"] = "100"
ok(c.post(f"/cantine/stock/magasins/semaine/{sid}/jours", data=form), 302)

# ---- documents de la semaine
assert pdf(c.get(f"/cantine/stock/magasins/semaine/{sid}/cahier.pdf")).data
assert pdf(c.get("/cantine/stock/magasins/bilan.pdf?periode=semaine&date=2026-11-03")).data

# ---- clôture : le reste retourne au grand magasin
reste_mais = round(165 - 150 * (210 + 215 + 215 + 210) / 1000, 3)                    # 38,4 kg
ok(c.post(f"/cantine/stock/magasins/semaine/{sid}/cloturer"), 302)
assert q("SELECT statut FROM cantine_semaines WHERE id=?", (sid,), un=True)["statut"] == "cloturee"
assert abs(stock("Maïs") - (335.0 + reste_mais)) < 1e-6, stock("Maïs")
ret = q("SELECT * FROM cantine_stock_mouvements WHERE bon_numero='Retour petit magasin' AND vivre_id=?", (viv["Maïs"]["id"],))
assert len(ret) == 1 and abs(ret[0]["quantite"] - reste_mais) < 1e-6 and ret[0]["type"] == "entree", ret
# haricot : consommation 40 × 850 / 1000 = 34 sur 44 prélevés → reste 10 ; idempotent (second clic sans effet)
ok(c.post(f"/cantine/stock/magasins/semaine/{sid}/cloturer"), 302)
assert q("SELECT COUNT(*) n FROM cantine_stock_mouvements WHERE bon_numero='Retour petit magasin'", un=True)["n"] == 5
# réouverture : le retour est annulé
ok(c.post(f"/cantine/stock/magasins/semaine/{sid}/rouvrir"), 302)
assert q("SELECT COUNT(*) n FROM cantine_stock_mouvements WHERE bon_numero='Retour petit magasin'", un=True)["n"] == 0
assert abs(stock("Maïs") - 335.0) < 1e-6

# ---- semaine 2 : l'ancienne semaine ouverte est clôturée AUTOMATIQUEMENT (retour) avant le nouveau prélèvement
page = txt(c.post("/cantine/stock/magasins/semaine/nouvelle", data={"debut": "2026-11-09", "garcons": "110", "filles": "100"}, follow_redirects=True))
assert "retourné au grand magasin" in page, page[:1200]
assert q("SELECT statut FROM cantine_semaines WHERE id=?", (sid,), un=True)["statut"] == "cloturee"
s2 = q("SELECT * FROM cantine_semaines WHERE debut='2026-11-09'", un=True)
assert abs(stock("Maïs") - (335.0 + reste_mais - 150 * 210 * 5 / 1000)) < 1e-6, stock("Maïs")
# la semaine 1 ne peut plus être rouverte (une semaine plus récente existe)
ok(c.post(f"/cantine/stock/magasins/semaine/{sid}/rouvrir"), 302)
assert q("SELECT statut FROM cantine_semaines WHERE id=?", (sid,), un=True)["statut"] == "cloturee"
# supprimer la semaine 2 remet son prélèvement dans le grand magasin
ok(c.post(f"/cantine/stock/magasins/semaine/{s2['id']}/supprimer"), 302)
assert q("SELECT COUNT(*) n FROM cantine_semaines", un=True)["n"] == 1
assert abs(stock("Maïs") - (335.0 + reste_mais)) < 1e-6

# ---- bilans : écran, PDF, Excel
for per, ref in [("jour", "2026-11-03"), ("semaine", "2026-11-04"), ("mois", "2026-11-01"), ("annee", "2026-11-01")]:
    page = txt(c.get(f"/cantine/stock/magasins/bilan?periode={per}&date={ref}&annee=2026-2027"))
    assert "Maïs" in page, (per, page[:600])
    pdf(c.get(f"/cantine/stock/magasins/bilan.pdf?periode={per}&date={ref}&annee=2026-2027"))
    lg = xlsx(c.get(f"/cantine/stock/magasins/bilan.xlsx?periode={per}&date={ref}&annee=2026-2027"))
    assert len(lg) >= 3, (per, lg)
page = txt(c.get("/cantine/stock/magasins/bilan?periode=semaine&date=2026-11-04"))
assert "165" in page and "127,5" in page, page[-2500:]                  # prélevé et consommé de la semaine

# ---- fiche de stock par vivre (colonnes du cahier)
f = txt(c.get(f"/cantine/stock/magasins/fiche?vivre={viv['Maïs']['id']}&annee=2026-2027"))
assert "Entrée dotation" in f and "Stock restant" in f and "Prélèvement petit magasin" in f and "Retour petit magasin" in f
pdf(c.get(f"/cantine/stock/magasins/fiche.pdf?vivre={viv['Maïs']['id']}&annee=2026-2027"))
lg = xlsx(c.get(f"/cantine/stock/magasins/fiche.xlsx?vivre={viv['Maïs']['id']}&annee=2026-2027"))
assert any(l and l[0] == "Date" for l in lg), lg[:4]
# les autres écrans de Vivres et stock restent ouverts
for u in ("/cantine/stock", "/cantine/stock/vivres", "/cantine/stock/mouvements", "/cantine/stock/recap", "/cantine/stock/sortie-jour"):
    ok(c.get(u))
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
