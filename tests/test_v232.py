"""2.3.2 : conversion du paquet d'école « Mon école » (POBE-PAQUET-ECOLE) par le concentrateur de la CS.
Données fictives ; le test de bout en bout avec un vrai paquet Mon école est dans test_interop_js.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jur_format  # noqa: E402
import jur_pobe as JP  # noqa: E402

PP = {"format": "POBE-PAQUET-ECOLE", "version": 2, "cree": "2026-11-02T08:00:00.000Z", "annee": "2026-2027",
      "ecole": {"id": "e1", "nom": "EPP Fictive", "code": "", "type": "EM", "classes_autorisees": 2, "posteLocal": True},
      "collections": {
          "effectifs": [{"id": "x", "ecoleId": "e1", "annee": "2025-2026", "s_eff_sp_G": 1, "s_eff_sp_F": 1},
                        {"id": "y", "ecoleId": "e1", "annee": "2026-2027", "s_eff_sp_G": 8, "s_eff_sp_F": 9,
                         "s_eff_sg_G": "7", "s_eff_sg_F": "6", "totalG": 15, "totalF": 15, "champInconnu": "1"}],
          "personnel": [{"id": "p", "ecoleId": "e1", "nom": "PERSONNE Test", "sexe": "F", "categorie": "Soutien",
                         "statut": "AME", "fonction": ""}],
          "certificats": [{"id": "c", "ecoleId": "e1"}], "notes": []}}


class TestV232(unittest.TestCase):
    def test_conversion(self):
        p, libres, cr = JP.convertir(PP, "EM-T1", "", "Plateau", "Pobè")
        jur_format.verifier(p)                      # paquet SCOLARIS valide (empreinte, type, secteur)
        e = p["ecoles"][0]
        self.assertEqual((e["ecole"]["code"], e["ecole"]["nom"], e["ecole"]["type"], e["ecole"]["secteur"]),
                         ("EM-T1", "EPP Fictive", "EM", "public"))
        cl = {c["niveau"]: (c["garcons"], c["filles"]) for c in e["sections"]["effectifs"]["classes"]}
        self.assertEqual(cl, {"Maternelle 1": (8, 9), "Maternelle 2": (7, 6)})   # relevé de l'année du paquet
        pers = e["sections"]["personnel"][0]
        self.assertEqual((pers["role"], pers["categorie"], pers["sexe"]), ("soutien", "ACDPCTD", "F"))
        self.assertEqual(cr["non_reprises"], {"certificats": 1})
        self.assertEqual(cr["champs_non_repris"]["effectifs"], ["champInconnu"])
        self.assertEqual(libres["fiches_mon_ecole"]["ecole"]["classes_autorisees"], 2)
        self.assertIn("certificats (1)", JP.resume(cr))

    def test_refus(self):
        with self.assertRaises(jur_format.PaquetInvalide):
            JP.convertir({"format": "autre"}, "X", "Y")
        with self.assertRaises(jur_format.PaquetInvalide):
            JP.convertir(dict(PP, annee=""), "X", "Y")


if __name__ == "__main__":
    unittest.main()
