# -*- coding: utf-8 -*-
"""Vocabulaire du secondaire (BEPC, professeur ou délégué de semaine) et répartition des colonnes des fiches de préparation."""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"

SCRIPT = r'''
import os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_DATA"] = tempfile.mkdtemp(); os.environ[P + "_SANS_PRECHARGEMENT"] = "1"
sys.path.insert(0, os.getcwd())
import m_vocab_sec as V, m_preparation as M
t = V.adapter_html('<p>Session CEP du maître de semaine, Certificat d’Études Primaires</p><script>var a="CEP";</script><option value="CEP">Centre CEP</option>UASCEP')
assert "Session BEPC du professeur ou délégué de semaine" in t and "Brevet d'Études du Premier Cycle" in t
assert 'var a="CEP"' in t and 'value="CEP"' in t and "Centre BEPC" in t and "UASCEP" in t
l = M.repartir_ligne(["Phase", "L'enseignant présente le support.\nÉlèves : lisent le texte.", "Attendu"])
assert l[1] == "L'enseignant présente le support." and l[2].startswith("Élèves : lisent le texte.") and l[2].endswith("Attendu")
print("OK")
'''


class T(unittest.TestCase):
    def test_vocab_et_repartition(self):
        env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
        r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RACINE, env=env, capture_output=True, text=True)
        self.assertIn("OK", r.stdout, r.stderr[-1200:])


if __name__ == "__main__":
    unittest.main()
