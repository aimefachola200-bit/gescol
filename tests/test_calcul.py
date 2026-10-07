# -*- coding: utf-8 -*-
"""Tests du moteur de calcul. Lancer : python -m unittest discover tests"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calcul import LigneNote, calculer, classer, seuil_deux_tiers

PRIM = [("COM.OR", 1, "standard"), ("DIC", 1, "standard"), ("COMP.EC", 1, "standard"),
        ("MATH", 2, "standard"), ("ED.SOC", 1, "standard"), ("ED.SCI", 1, "standard"),
        ("ART.P", 1, "exclu_2_3"), ("ART.V", 1, "exclu_2_3"), ("ANG", 1, "standard"),
        ("EXP.EC", 1, "standard"), ("EPS", 1, "exclu_2_3")]


def prim(notes, dispenses=()):
    return [LigneNote(c, c, k, m, v, c in dispenses) for (c, k, m), v in zip(PRIM, notes)]


class TestPrimaire(unittest.TestCase):
    def test_seuil_entier(self):
        self.assertEqual([seuil_deux_tiers(n) for n in (3, 6, 7, 8, 9)], [2, 4, 5, 6, 6])

    def test_admis_2_3(self):
        # 8 standard : 6 >= 10 -> seuil 6 atteint
        r = calculer("CM2", prim([14, 12, 15, 17, 11, 16, 9, 12, 8, 7, 15]))
        self.assertEqual(r.details["matieres_standard"], 8)
        self.assertEqual(r.details["seuil_2_3"], 6)
        self.assertEqual(r.details["standard_reussies"], 6)
        self.assertEqual(r.decision, "MAÎTRISE")
        self.assertTrue(r.admis)
        self.assertEqual(r.moyenne, round(136 / 11, 2))  # moyenne simple, coef ignoré

    def test_exclues_ne_sauvent_pas(self):
        # 5 standard sur 8 >= 10 -> NON ADMIS même avec 20 en Arts/EPS
        r = calculer("CE1", prim([14, 12, 15, 17, 11, 5, 20, 20, 5, 5, 20]))
        self.assertEqual(r.decision, "NON MAÎTRISE")
        self.assertGreaterEqual(r.moyenne, 10)  # la moyenne ne sauve pas : seule la maîtrise compte

    def test_seuil_impose(self):
        # seuil fixé par l'évaluation : 5 matières à 10/20 au moins
        r = calculer("CE1", prim([14, 12, 15, 17, 11, 5, 20, 20, 5, 5, 20]), seuil_impose=5)
        self.assertEqual(r.details["seuil_2_3"], 5)
        self.assertEqual(r.decision, "MAÎTRISE")

    def test_dispense_et_manquant(self):
        r = calculer("CM1", prim([14, 12, 15, 17, 11, 16, None, 12, 13, 14, 15], dispenses=("EPS",)))
        self.assertEqual(r.details["dispenses"], ["EPS"])
        self.assertEqual(r.details["notes_manquantes"], ["ART.P"])
        self.assertEqual(r.details["matieres_notees"], 9)


class TestSecondaire(unittest.TestCase):
    def test_pondere(self):
        l = [LigneNote("MATH", "Maths", 3, "standard", 12), LigneNote("FR", "Français", 2, "standard", 9),
             LigneNote("EPS", "EPS", 1, "standard", 15)]
        r = calculer("4ème", l)
        self.assertEqual(r.moyenne, round((36 + 18 + 15) / 6, 2))
        self.assertEqual(r.decision, "ADMIS")

    def test_sans_coef_6eme(self):
        l = [LigneNote("MATH", "Maths", 3, "standard", 6), LigneNote("FR", "Français", 2, "standard", 13)]
        r = calculer("6ème", l)
        self.assertEqual(r.moyenne, 9.5)
        self.assertEqual(r.decision, "NON ADMIS")

    def test_note_invalide(self):
        with self.assertRaises(ValueError):
            calculer("3ème", [LigneNote("M", "M", 1, "standard", 21)])


class TestRangs(unittest.TestCase):
    def test_ex_aequo(self):
        r = classer({1: 12.0, 2: 15.0, 3: 12.0, 4: 10.0, 5: None})
        self.assertEqual(r[2], (1, False))
        self.assertEqual(r[1], (2, True))
        self.assertEqual(r[3], (2, True))
        self.assertEqual(r[4], (4, False))
        self.assertEqual(r[5], (None, False))


if __name__ == "__main__":
    unittest.main()


class TestMaternelle(unittest.TestCase):
    def test_bilan(self):
        from calcul import calculer as calc
        l = [LigneNote(c, c, 1, "standard", None, False, a) for c, a in
             [("LANG", "A"), ("MATH", "A"), ("SCI", "ECA"), ("MOT", "A"), ("ART", None)]]
        r = calc("Maternelle 2", l)
        self.assertEqual(r.cycle, "maternelle")
        self.assertIsNone(r.moyenne)
        self.assertEqual(r.details["comptes"], {"A": 3, "ECA": 1, "NA": 0})
        self.assertEqual(r.decision, "Progrès très satisfaisants")
        self.assertEqual(r.details["notes_manquantes"], ["ART"])
        r2 = calc("Maternelle 1", [LigneNote("X", "X", 1, "standard", None, False, "NA"),
                                   LigneNote("Y", "Y", 1, "standard", None, False, "ECA")])
        self.assertEqual(r2.decision, "Progrès à renforcer")


class TestPaie(unittest.TestCase):
    P = {"paie_cnss_salarie": "3.6", "paie_cnss_patronal": "16.4", "paie_vps": "4",
         "paie_its_bareme": "60000:0;150000:10;250000:15;500000:19;*:30", "paie_its_apres_cnss": "1", "paie_arrondi_its": "0"}

    def test_its_tranches(self):
        from m_paie import its_mensuel, lire_bareme
        b = lire_bareme(self.P["paie_its_bareme"])
        self.assertEqual(its_mensuel(50000, b, False), 0)
        self.assertEqual(its_mensuel(100000, b, False), 4000)             # 40 000 x 10 %
        self.assertEqual(its_mensuel(200000, b, False), 9000 + 7500)      # 90 000 x 10 % + 50 000 x 15 %
        self.assertEqual(its_mensuel(600000, b, False), 9000 + 15000 + 47500 + 30000)

    def test_bulletin(self):
        from m_paie import calculer_paie
        d = calculer_paie(150000, self.P, retenues=1000, avances=10000)
        self.assertEqual(d["cnss_salarie"], 5400)
        self.assertEqual(d["base_its"], 144600)
        self.assertEqual(d["its"], 8460)                                  # (144 600 - 60 000) x 10 %
        self.assertEqual(d["net"], 150000 - 5400 - 8460 - 1000 - 10000)
        self.assertEqual(d["cnss_patronal"], 24600)
        self.assertEqual(d["vps"], 6000)
        v = calculer_paie(80000, self.P, cnss=False, its=False)
        self.assertEqual((v["cnss_salarie"], v["its"], v["net"]), (0, 0, 80000))


class TestCarriere(unittest.TestCase):
    """Règles de retraite et d'ancienneté (m_carriere) : départ le 1er jour du trimestre suivant le trimestre de
    naissance ; anciennetés au 31/12 de la première année de l'année scolaire active."""

    def test_retraite_trimestre_suivant(self):
        from datetime import date
        from m_carriere import date_retraite
        self.assertEqual(date_retraite("1967-02-15", "A1-5"), date(2027, 4, 1))     # janv–mars -> 1er avril
        self.assertEqual(date_retraite("1969-02-28", "B1-12"), date(2027, 4, 1))    # 28/02/2027 -> 01/04/2027
        self.assertEqual(date_retraite("1970-11-10", "C1-3"), date(2026, 1, 1))     # oct–déc -> 1er janvier suivant
        self.assertEqual(date_retraite("1966-07-01", "A"), date(2026, 10, 1))       # juil–sept -> 1er octobre
        self.assertEqual(date_retraite("1966-04-30", "a2-7"), date(2026, 7, 1))     # avril–juin -> 1er juillet
        self.assertEqual(date_retraite("1968-12-31", "B"), date(2027, 1, 1))
        self.assertEqual(date_retraite("1968", "A"), date(2029, 1, 1))              # année seule : 1er janvier (année + âge + 1)
        self.assertIsNone(date_retraite("1968-05-05", "D"))
        self.assertIsNone(date_retraite("", "A"))

    def test_date_reference(self):
        from datetime import date
        from m_carriere import date_reference, anciennete
        self.assertEqual(date_reference(annee="2026-2027"), date(2026, 12, 31))
        self.assertEqual(date_reference(annee="2027-2028"), date(2027, 12, 31))
        self.assertEqual(date_reference(date(2031, 3, 1), annee="n'importe quoi"), date(2031, 12, 31))
        ref = date(2026, 12, 31)
        self.assertEqual(anciennete("2020-01-01", ref), (7, 0))                      # 31/12 inclus
        self.assertEqual(anciennete("2024-02-29", ref), (2, 10))
        self.assertEqual(anciennete("2026-09-15", ref), (0, 3))
        self.assertIsNone(anciennete("2027-01-01", ref))

    def test_calculer_fiche(self):
        from datetime import date
        from m_carriere import calculer_fiche
        import config
        ancien = config.ANNEE_ACTIVE
        config.ANNEE_ACTIVE = "2026-2027"
        try:
            f = calculer_fiche({"nom": "AKPO", "prenoms": "Jean", "grade": "B1-12", "date_naissance": "1969-02-28",
                                "date_prise_service": "2000-10-01", "date_service_ecole": "2019-09-16"},
                               auj=date(2026, 10, 7))
        finally:
            config.ANNEE_ACTIVE = ancien
        self.assertEqual(f["reference"], date(2026, 12, 31))
        self.assertEqual(f["retraite"], date(2027, 4, 1))
        self.assertEqual(f["retraite_txt"], "01/04/2027")
        self.assertTrue(f["alerte_retraite"])
        self.assertEqual(f["anc"]["generale"], (26, 3))
        self.assertEqual(f["anc"]["ecole"], (7, 3))
        self.assertEqual(f["anc_txt"]["ecole"], "7 ans 3 mois")
