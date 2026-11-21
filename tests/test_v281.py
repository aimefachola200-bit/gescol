# -*- coding: utf-8 -*-
"""Tests 2.8.1 : fiches CM2 ajoutées (français, ES, EA, maths), sans doublon ni filigrane.
Lancer : python3 -m unittest tests.test_v281"""
import gzip, json, os, re, unittest
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestCorpus281(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(os.path.join(RACINE, "static", "pedafiche_corpus.json.gz"), "rt", encoding="utf-8") as f:
            cls.c = json.load(f)
        cls.fiches = cls.c["fiches"]
        cls.ajout = [f for f in cls.fiches if f["id"].startswith(("dav-", "fm-"))]

    def test_ajouts_presents(self):
        self.assertGreaterEqual(len(self.ajout), 150)
        self.assertGreaterEqual(len(self.fiches), 4500)

    def test_ids_uniques(self):
        ids = [f["id"] for f in self.fiches]
        self.assertEqual(len(ids), len(set(ids)))

    def test_forme(self):
        for f in self.ajout:
            self.assertTrue(f["titre"].strip(), f["id"])
            self.assertTrue(f["deroulement"], f["id"])
            for ligne in f["deroulement"]:
                self.assertEqual(len(ligne), 3)
            self.assertIn("APC", f["source"] if f["source"] else "APC")

    def test_pas_de_filigrane_ni_signature(self):
        for f in self.ajout:
            t = json.dumps(f, ensure_ascii=False)
            self.assertNotIn("DAYORI", t, f["id"])
            self.assertNotIn("FICHE DE PREPARATION", t, f["id"])

    def test_pas_de_doublon_exact(self):
        cles = {}
        for f in self.ajout:
            k = (f["matiere"], f["cours"], f["titre"], json.dumps(f["deroulement"], ensure_ascii=False))
            self.assertNotIn(k, cles)
            cles[k] = 1

    def test_inventaire(self):
        self.assertIn("inventaire_fm", self.c)

if __name__ == "__main__":
    unittest.main()
