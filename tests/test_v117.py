# -*- coding: utf-8 -*-
"""Tests 1.17 : en-têtes fixes — la ligne des rubriques des tableaux (et les titres de section des formulaires)
reste visible pendant le défilement. Vérifie la feuille de style, le script et la présence des cadres .tw.
Lancer : python3 -m unittest tests.test_v117"""
import os
import re
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(*p):
    with open(os.path.join(RACINE, *p), encoding="utf-8") as f:
        return f.read()


class TestEntetesFixes(unittest.TestCase):
    def test_style(self):
        css = lire("static", "style.css")
        self.assertIn("table .th-fixe{position:sticky!important", css)
        self.assertRegex(css, r"\.tw\{overflow:auto;max-height:calc\(100vh")
        self.assertIn("table .col-fixe{position:sticky;left:0", css)
        self.assertRegex(css, r"@media print\{\.tw\{max-height:none!important")

    def test_script(self):
        js = lire("static", "scolaris.js")
        for marque in ("function fixerEntetes", "function placerEntetes", "function titreAuDessus", "fixerEntetes(racine);",
                       "window.SCOLARIS.fixerEntetes", "data-entete=\"non\""):
            self.assertIn(marque, js)

    def test_gabarits(self):
        # les grands tableaux de saisie sont dans un cadre .tw (défilement propre, en-tête collé)
        for g in ("registre_accueil.html", "eval_saisie.html", "rapports_formulaire.html"):
            self.assertRegex(lire("templates", g), r'class="tw[ "]', g)
        self.assertIn("scolaris.js", lire("templates", "base.html"))


if __name__ == "__main__":
    unittest.main()
