# -*- coding: utf-8 -*-
"""Interopérabilité de la synchronisation 2.0 avec les applications JS (protocole memp-sync, outils/sync/spec.md).
(1) paquet DESCENDANT réel de SCOLARIS édition cs (reg:examens:salles@bas, reg:territoire:structures, reg:territoire:retours)
    importé par « Mon école » (build CS Pobè, /home/claude/cs-pobe/ecole) avec son client sync-client.js dans Chromium :
    signature vérifiée, centres et salles (offG…, saison), structures (rattachement, active), décision (RENVOYEE, motif) ;
(2) paquet MONTANT préparé par Mon école (reg:territoire:rentree, reg:communication:courrier, reg:territoire:signaletique)
    importé par le hub SCOLARIS cs : signature vérifiée en Python, fiche rangée sous le nom de l'école, courrier reçu.
Ignoré si le build CS Pobè, Node / Playwright ou Chromium manquent (fabrication en ligne).
Lancer : python3 -m unittest tests.test_interop_js"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
CS_POBE = os.environ.get("CS_POBE_BUILD", "/home/claude/cs-pobe")
ICI = os.path.join(RACINE, "tests", "interop")


def node_path():
    try:
        return subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


@unittest.skipUnless(os.path.isfile(os.path.join(CS_POBE, "ecole", "js", "sync-client.js")) and shutil.which("node"), "build CS Pobè ou Node absent")
class TestInteropJS(unittest.TestCase):
    def test_aller_retour(self):
        npath = node_path()
        if not os.path.isdir(os.path.join(npath, "playwright")):
            self.skipTest("Playwright (Node) absent")
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=CS_POBE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(1.5)
            tmp = tempfile.mkdtemp()
            d = tempfile.mkdtemp()
            env = dict(os.environ, PREFIXE=PREFIXE)
            for k in list(env):
                if k.endswith(("_EDITION", "_DATA")) and k.startswith(("SCOLARIS", "GESCOL")):
                    env.pop(k)
            desc, mont = os.path.join(tmp, "desc.scsync"), os.path.join(tmp, "montant.json")
            r = subprocess.run([sys.executable, os.path.join(ICI, "scolaris_cs.py"), "export", d, desc], cwd=RACINE, env=env,
                               capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stderr[-4000:])
            ex = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertTrue(ex["signature_ok"])
            self.assertEqual(set(ex["types"]), {"reg:examens:salles@bas", "reg:territoire:structures", "reg:territoire:retours"})
            r = subprocess.run(["node", os.path.join(ICI, "mon_ecole.js"), f"http://127.0.0.1:{port}", desc, mont], cwd=ICI,
                               env=dict(os.environ, NODE_PATH=npath), capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
            js = json.loads(r.stdout)
            self.assertNotIn("erreurImport", js, js.get("erreurImport"))
            self.assertEqual(js["import"]["appliques"], sum(ex["types"].values()))
            c = {x["centre"]: x for x in js["cepSalles"]}
            self.assertEqual([c["POBE-CENTRE"][k] for k in ("offG", "offF", "offH", "libG", "salles", "saison")], [150, 140, 1, 3, 8, "JUIN 2027"])
            self.assertEqual(len(c), 6)
            st = {x["nom"]: x for x in js["structures"]}
            self.assertIn("Ministère des Enseignements Maternel et Primaire", st)
            self.assertTrue(any(x["rattachement"] == "Ministère des Enseignements Maternel et Primaire" for x in js["structures"]))
            self.assertEqual([(x["statut"], x["motif"], x["destinataire"]) for x in js["retours"]], [("RENVOYEE", "Compléter les salles", "EPP Interop")])
            self.assertEqual(set(js["montantTypes"]), {"reg:territoire:rentree", "reg:communication:courrier", "reg:territoire:signaletique"})
            r = subprocess.run([sys.executable, os.path.join(ICI, "scolaris_cs.py"), "import", d, mont], cwd=RACINE, env=env,
                               capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stderr[-4000:])
            im = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertTrue(im["signature_ok"])
            self.assertIn({"entite": "EPP Interop", "effG": 31, "effF": 29, "statut": "TRANSMISE", "dateTransmission": "2026-11-02"}, im["rentree"])
            self.assertEqual([(x["entite"], x["reference"], x["statut"]) for x in im["courrier"]], [("EPP Interop", "R-JS-1", "Envoyé")])
            # paquet d'école Mon école (POBE-PAQUET-ECOLE) : accepté et converti par le concentrateur
            self.assertEqual((js["transmission"] or {}).get("format"), "POBE-PAQUET-ECOLE")
            self.assertNotIn("non reprise", im["message"])
            self.assertIn("Paquet Mon école converti", im["message"])
            secs = im["sections"]
            cl = {x["niveau"]: (x["garcons"], x["filles"]) for x in secs["effectifs"]["classes"]}
            self.assertEqual(cl, {"CI": (12, 10), "CP": (9, 11), "CM2": (7, 6)})
            self.assertEqual((secs["effectifs"]["handicapes_total"], secs["effectifs"]["salles"]), (2, 2))
            pers = {x["matricule"]: x for x in secs["personnel"]}
            self.assertEqual((pers["T-0001"]["role"], pers["T-0001"]["categorie"], pers["T-0001"]["cap"], pers["T-0001"]["note_evaluation"]),
                             ("directeur", "FE", True, "15.5"))
            self.assertEqual((pers["T-0002"]["role"], pers["T-0002"]["sexe"], pers["T-0002"]["classe"]), ("adjoint", "F", "CI"))
            self.assertEqual([(v["type"], v["discipline"], v["note"]) for v in secs["visites"]], [("CP", "Français", 14.0)])
            self.assertEqual((secs["cep"]["candidats_f"], secs["cep"]["session"], secs["cep"]["liste"][0]["nom"]), (1, "2027", "FICTIF"))
            self.assertEqual(secs["fiches_mon_ecole"]["valeurs"]["point_eau"], "Forage")
            self.assertEqual(secs["fiches_mon_ecole"]["ecole"]["classes_autorisees"], 4)
            rap = secs["import_mon_ecole"]
            self.assertEqual(rap["non_reprises"].get("mobilier"), 1)
            self.assertIn("lieuNaiss", rap["champs_non_repris"]["personnel"])
            self.assertIn("pere", rap["champs_non_repris"]["cep"])
            self.assertIn("mobilier (1)", im["message"])
            self.assertEqual(im["signaletique"][0]["numeroAgrement"], "AG-JS-7")
            self.assertTrue(im["courrier_page"] and im["suivi_page"])
        finally:
            srv.terminate()


if __name__ == "__main__":
    unittest.main()
