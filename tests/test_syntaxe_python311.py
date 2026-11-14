# -*- coding: utf-8 -*-
"""Tous les fichiers .py du projet doivent se compiler (syntaxe valide) : l'exécutable Windows (Python 3.11) échoue sinon,
même si les tests passent (ex. : un serveur de bureau jamais importé par les tests)."""
import glob
import os
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSyntaxe(unittest.TestCase):
    def test_tous_les_py_compilent(self):
        mauvais = []
        for f in glob.glob(os.path.join(RACINE, "**", "*.py"), recursive=True):
            if any(x in f for x in (os.sep + "venv", os.sep + "build" + os.sep, os.sep + "dist" + os.sep, "__pycache__", os.sep + "instance" + os.sep)):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    compile(fh.read(), f, "exec")
            except SyntaxError as e:
                mauvais.append(f"{os.path.relpath(f, RACINE)}:{e.lineno} {e.msg}")
        self.assertEqual(mauvais, [], "Fichiers à syntaxe invalide : " + "; ".join(mauvais))


if __name__ == "__main__":
    unittest.main()
