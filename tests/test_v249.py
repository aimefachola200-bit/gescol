# -*- coding: utf-8 -*-
"""v2.4.9 : mise à jour automatique du code (amorcage + maj_auto) — cycle complet avec un « GitHub » simulé."""
import hashlib, json, os, subprocess, sys, tempfile, textwrap, unittest, zipfile

RACINE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RACINE)


class T(unittest.TestCase):
    def test_version_amorcage_egale_config(self):
        import amorcage, config
        self.assertEqual(amorcage.BASE_VERSION, config.VERSION)
        self.assertTrue(amorcage.plus_recente("2.4.10", "2.4.9"))
        self.assertFalse(amorcage.plus_recente("2.4.9", "2.4.9"))
        self.assertFalse(amorcage.plus_recente("v2.4.8", "2.4.9"))

    def test_fabrication_du_paquet(self):
        d = tempfile.mkdtemp()
        subprocess.check_call([sys.executable, os.path.join(RACINE, "packaging", "fabriquer_maj.py"), d], stdout=subprocess.DEVNULL)
        info = json.load(open(os.path.join(d, "MAJ-CODE.json")))
        self.assertEqual(hashlib.sha256(open(os.path.join(d, "MAJ-CODE.zip"), "rb").read()).hexdigest(), info["sha256"])
        noms = zipfile.ZipFile(os.path.join(d, "MAJ-CODE.zip")).namelist()
        for n in ("code/app.py", "code/config.py", "code/maj_auto.py", "web/templates/base.html", "web/static/gescol.js"):
            self.assertIn(n, noms)
        self.assertNotIn("code/gescol_serveur.py", noms)

    def test_cycle_complet(self):
        """Télécharge (faux GitHub), active au lancement suivant, puis abandonne une version qui ne démarre pas."""
        data = tempfile.mkdtemp()
        script = textwrap.dedent(r'''
            import os, sys, json, hashlib, zipfile, tempfile, io
            RACINE, DATA = sys.argv[1], sys.argv[2]
            os.environ["GESCOL_DATA"] = DATA; os.environ["GESCOL_AUTONOME"] = "1"
            os.environ["SCOLARIS_DATA"] = DATA; os.environ["SCOLARIS_AUTONOME"] = "1"
            sys.path.insert(0, RACINE)
            import amorcage, config, maj_auto
            # faux paquet « 9.9.9 » : le vrai code + un marqueur dans config.py
            def paquet(version, casse=False):
                tmp = tempfile.mkdtemp(); zp = os.path.join(tmp, "m.zip")
                with zipfile.ZipFile(zp, "w") as z:
                    for f in os.listdir(RACINE):
                        if f.endswith(".py") and f not in ("gescol_serveur.py", "scolaris_serveur.py", "wsgi.py"):
                            src = open(os.path.join(RACINE, f), encoding="utf-8").read()
                            if f == "config.py":
                                src = src.replace('VERSION = "%s"' % config.VERSION, 'VERSION = "%s"' % version, 1)
                                if casse: src += "\nraise RuntimeError('boum')\n"
                            z.writestr("code/" + f, src)
                    for d in ("templates", "static"):
                        for dos, _, fs in os.walk(os.path.join(RACINE, d)):
                            for f in fs:
                                p = os.path.join(dos, f); z.write(p, "web/" + os.path.relpath(p, RACINE).replace(os.sep, "/"))
                return zp, hashlib.sha256(open(zp, "rb").read()).hexdigest()
            mode = sys.argv[3]
            if mode == "telecharger":
                zp, h = paquet("9.9.9", casse=(sys.argv[4] == "casse"))
                corps = {"MAJ-CODE.json": json.dumps({"version": "9.9.9", "sha256": h}).encode(), "MAJ-CODE.zip": open(zp, "rb").read()}
                maj_auto._http = lambda url, tmax=20: io.BytesIO(corps[url.rsplit("/", 1)[1]])
                print(maj_auto.verifier()); print(json.dumps(maj_auto.etat()))
            elif mode == "mauvaise_empreinte":
                zp, h = paquet("9.9.9")
                corps = {"MAJ-CODE.json": json.dumps({"version": "9.9.9", "sha256": "0" * 64}).encode(), "MAJ-CODE.zip": open(zp, "rb").read()}
                maj_auto._http = lambda url, tmax=20: io.BytesIO(corps[url.rsplit("/", 1)[1]])
                try: maj_auto.verifier(); print("ACCEPTE")
                except ValueError as e: print("REJETE")
            elif mode == "lancer":
                print(amorcage.appliquer())
                import config as c2
                print(c2.VERSION)
                try:
                    import app; print("APP_OK")
                except Exception as e: print("APP_KO", e)
        ''')
        f = os.path.join(tempfile.mkdtemp(), "sc.py"); open(f, "w", encoding="utf-8").write(script)
        def run(*a):
            r = subprocess.run([sys.executable, f, RACINE, data, *a], capture_output=True, text=True, timeout=300)
            return r.stdout.strip().splitlines(), r.stderr
        sortie, err = run("mauvaise_empreinte"); self.assertEqual(sortie[-1], "REJETE", err)
        self.assertFalse(os.path.exists(os.path.join(data, "maj_code", "9.9.9")))
        sortie, err = run("telecharger", "ok"); self.assertEqual(sortie[0], "prête", err)
        self.assertEqual(json.loads(sortie[1])["pret"], "9.9.9")
        sortie, err = run("lancer"); self.assertEqual(sortie[:2], ["9.9.9", "9.9.9"], err)   # le code mis à jour a pris la main
        self.assertIn("APP_OK", sortie, err)
        # réinstallation d'une version plus récente que la mise à jour : la mise à jour est ignorée
        os.environ["X"] = "1"
        # version qui ne démarre pas : 4 essais puis retour à l'installation
        run("telecharger", "casse")  # déjà prête (9.9.9 existe) : on la remplace à la main par la version cassée
        import shutil
        shutil.rmtree(os.path.join(data, "maj_code", "9.9.9"))
        run("telecharger", "casse")
        for _ in range(4): run("lancer")
        sortie, err = run("lancer")
        self.assertEqual(sortie[0], "None", err)                 # abandonnée
        self.assertEqual(sortie[1], __import__("config").VERSION)
        self.assertTrue(os.path.exists(os.path.join(data, "maj_code", "echec.json")))


if __name__ == "__main__":
    unittest.main()
