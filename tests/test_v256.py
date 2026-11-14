# -*- coding: utf-8 -*-
"""Tests v2.5.2 — tableau de bord et tableau synoptique de chaque division (a_tb_division).
Rejoué dans deux sous-processus (éditions cs et ddemp) : base de démonstration, comptes responsable / chef / rh."""
import os
import subprocess
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITION = os.environ.get("GESCOL_EDITION_TEST")
if EDITION:
    os.environ["GESCOL_EDITION"] = EDITION
    os.environ["GESCOL_DATA"] = tempfile.mkdtemp(prefix=f"gescol_v256_{EDITION}_")
    sys.path.insert(0, RACINE)
    from app import app  # noqa: E402
    import demo_juridiction  # noqa: E402


class Division(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EDITION:
            raise unittest.SkipTest("rejoué en sous-processus")
        app.config["TESTING"] = True
        demo_juridiction.main()

    def client(self, ident):
        c = app.test_client()
        r = c.post("/login", data={"identifiant": ident, "mdp": "demo1234"})
        self.assertEqual(r.status_code, 302)
        return c

    def test_responsable(self):
        c = self.client("responsable")
        r = c.get("/juridiction/divisions/synoptique")
        self.assertEqual(r.status_code, 200, r.data[:400])
        self.assertIn("Tableau synoptique des divisions".encode(), r.data)
        for url in ("/juridiction/divisions/synoptique.pdf", "/juridiction/divisions/synoptique.xlsx"):
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url)
        import a_structure as S
        with app.app_context():
            codes = [x["code"] for x in S.services()]
        self.assertTrue(codes)
        for code in codes:
            for suffixe in ("tableau-de-bord", "synoptique", "synoptique.pdf"):
                r = c.get(f"/juridiction/divisions/{code}/{suffixe}")
                self.assertEqual(r.status_code, 200, f"{code}/{suffixe} → {r.status_code}")
        r = c.get("/juridiction/mon-tableau-de-bord")
        self.assertEqual(r.status_code, 302)

    def test_chef_limite_a_sa_division(self):
        c = self.client("chef")
        r = c.get("/juridiction/mon-tableau-de-bord")
        self.assertEqual(r.status_code, 302)
        mien = r.headers["Location"].split("?")[0]
        self.assertTrue(mien.endswith("/tableau-de-bord"), mien)
        self.assertEqual(c.get(mien).status_code, 200)
        code = mien.split("/divisions/")[1].split("/")[0]
        import a_structure as S
        with app.app_context():
            autres = [x["code"] for x in S.services() if x["code"] != code]
        self.assertTrue(autres)
        self.assertEqual(c.get(f"/juridiction/divisions/{autres[0]}/tableau-de-bord").status_code, 403)
        self.assertEqual(c.get(f"/juridiction/divisions/{autres[0]}/synoptique").status_code, 403)
        self.assertEqual(c.get("/juridiction/divisions/synoptique.xlsx").status_code, 403)
        r = c.get("/juridiction/divisions/synoptique")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get(f"/juridiction/divisions/{code}/synoptique").status_code, 200)

    def test_indicateurs_et_analyse(self):
        c = self.client("responsable")
        r = c.get("/juridiction/divisions/organisation/tableau-de-bord") if EDITION == "cs" else \
            c.get("/juridiction/divisions/statistiques/tableau-de-bord")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Indicateurs de terrain".encode(), r.data)
        self.assertIn("Écoles actives".encode(), r.data)


class Edition(unittest.TestCase):
    def test_editions(self):
        if EDITION:
            self.skipTest("sous-processus")
        for ed in ("cs", "ddemp"):
            env = dict(os.environ, GESCOL_EDITION_TEST=ed)
            env.pop("GESCOL_EDITION", None)
            env.pop("GESCOL_DATA", None)
            r = subprocess.run([sys.executable, "-m", "unittest", "tests.test_v256.Division"], cwd=RACINE, env=env,
                               capture_output=True, text=True, timeout=900)
            self.assertEqual(r.returncode, 0, f"{ed}\n{r.stderr[-2500:]}")


if __name__ == "__main__":
    unittest.main()
