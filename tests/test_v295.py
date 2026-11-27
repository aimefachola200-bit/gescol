# -*- coding: utf-8 -*-
"""v2.9.5 : planification mensuelle préremplie depuis la planification annuelle du cours (modifiable ensuite)."""
import json
import unittest

import tests.test_planification_mensuelle as TPM
from tests.test_planification_mensuelle import q, txt
import m_synoptique as MS


class TestOutilsAnnuelle(unittest.TestCase):
    def test_repartition(self):
        self.assertEqual(MS.repartir_sequences("SA1 Séq2-5", 4)[:4], ["SA1 Séq2", "SA1 Séq3", "SA1 Séq4", "SA1 Séq5"])
        self.assertEqual(MS.repartir_sequences("SA3 Séq2 SA5 Séq1", 5)[:2], ["SA3 Séq2", "SA5 Séq1"])
        self.assertEqual(MS.repartir_sequences("SA1 Séq1-9", 2)[:2], ["SA1 Séq1-4", "SA1 Séq5-9"])
        self.assertEqual(MS.repartir_sequences("D1 SA2 à D2 SA2 Séq5", 5)[0], "D1 SA2 à D2 SA2 Séq5")
        self.assertEqual(MS.repartir_sequences("", 5), [""] * 5)
        self.assertEqual(len(MS.repartir_sequences("SA1 Séq1-3", 5)), MS.NB_SEMAINES_PM)

    def test_unites_et_ligne(self):
        self.assertEqual(MS.unites_francais("U2 à 3"), (2, 3))
        self.assertEqual(MS.unites_francais("U1"), (1, 1))
        self.assertIsNone(MS.unites_francais(""))
        lig = MS.ligne_annuelle_du_mois(MS.planification_defaut("ce2"), "2026-10")
        self.assertEqual(lig["mois"], "Octobre")
        c = MS.contenu_pm_depuis_annuelle(lig, MS.semaines_du_mois("2026-10"))
        self.assertTrue(c["fr_2"][0].startswith("U2 "))
        self.assertTrue(c["fr_2"][4].startswith("U3 "))
        self.assertEqual(c["es_morale"][0], "SA1 Séq2")
        self.assertEqual(len(c["maths"]), MS.NB_SEMAINES_PM)


class TestRouteAnnuelle(unittest.TestCase):
    setUpClass = classmethod(TPM.TestPlanificationMensuelle.setUpClass.__func__)
    url = TPM.TestPlanificationMensuelle.url

    @property
    def dec(self):
        return self.annee[:4] + "-12"

    def test_00_remplir_depuis_annuelle(self):
        h = txt(self.c.get(f"/synoptique/planification-mensuelle?classe={self.cid}&mois={self.dec}"))
        self.assertIn("Remplir depuis", h)
        r = self.c.post(self.url("/depuis-annuelle", self.dec), follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/modifier", r.headers["Location"])
        row = q("SELECT contenu FROM synoptique_planification_mensuelle WHERE classe_id=? AND mois=?", (self.cid, self.dec), un=True)
        d = json.loads(row["contenu"])
        self.assertTrue(d["fr_2"][0].startswith("U"))
        self.assertTrue(any(x for x in d["es_morale"]))
        # modifiable ensuite
        self.assertEqual(self.c.get(self.url("/modifier", self.dec)).status_code, 200)
        self.assertEqual(self.c.post(self.url("/depuis-annuelle", "2026-13")).status_code, 404)
        # on remet la base dans l'état initial (les autres tests de la planification mensuelle comptent les mois enregistrés)
        TPM.ex_("DELETE FROM synoptique_planification_mensuelle WHERE classe_id=? AND mois=?", (self.cid, self.dec))
