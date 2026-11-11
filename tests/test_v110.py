# -*- coding: utf-8 -*-
"""Tests de la version 1.10 : tableau de bord (programmation et bilan, CCS puis CP), module Effectifs
(apprenants, personnel, catégories, CAP / CEAP, courbes), tableaux globaux des fiches (recensement, rentrée, fin).
Lancer : python3 -m unittest tests.test_v110"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import a_effectifs as E  # noqa: E402
import a_fiches as F  # noqa: E402
import a_infra as I  # noqa: E402
import a_ecoles_struct as ES  # noqa: E402
import a_rubriques as RB  # noqa: E402
import a_cep_fiches as CF  # noqa: E402

PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"


def lancer(script, edition):
    env = dict(os.environ)
    for k in ("SCOLARIS_EDITION", "SCOLARIS_DATA", "GESCOL_EDITION", "GESCOL_DATA"):
        env.pop(k, None)
    env["EDITION_SCRIPT"] = edition
    env["PREFIXE_SCRIPT"] = PREFIXE
    return subprocess.run([sys.executable, "-c", script], cwd=RACINE, env=env, capture_output=True, text=True, timeout=900)


class TestRegles(unittest.TestCase):
    def test_categorie(self):
        self.assertEqual(E.categorie({"categorie": "FE"}), "FE")
        self.assertEqual(E.categorie({"categorie": "ACDPCTD"}), "ACDPCTD")
        self.assertEqual(E.categorie({"categorie": "AME"}), "ACDPCTD")
        self.assertEqual(E.categorie({"categorie": "", "fonction": "Éducatrice"}), "EDUCATEUR")
        self.assertEqual(E.categorie({"categorie": "EDUCATEUR"}), "EDUCATEUR")
        self.assertEqual(E.categorie({"categorie": "PRIVE"}), "PRIVE")
        self.assertEqual(E.categorie({"categorie": ""}), "AUTRE")

    def test_calcul(self):
        lignes = [{"id": 1, "nom": "EPP A", "type": "EP", "cs_id": 1, "cs_nom": "CS1", "zone_id": 10, "zone_nom": "Z1",
                   "eff": {"g": 30, "f": 25, "t": 55}},
                  {"id": 2, "nom": "EM B", "type": "EM", "cs_id": 1, "cs_nom": "CS1", "zone_id": 11, "zone_nom": "Z2",
                   "eff": {"g": 10, "f": 12, "t": 22}}]
        pers = [{"ecole_id": 1, "role": "directeur", "sexe": "M", "categorie": "FE", "cap": True, "type_cap": "EP", "ceap": True},
                {"ecole_id": 1, "role": "enseignant", "sexe": "F", "categorie": "ACDPE", "cap": False, "ceap": True},
                {"ecole_id": 2, "role": "enseignant", "sexe": "F", "categorie": "", "fonction": "Éducatrice", "cap": True},
                {"ecole_id": 2, "role": "soutien", "sexe": "M"}]
        grp, tot = E.calculer(lignes, pers, "zone")
        self.assertEqual([g["nom"] for g in grp], ["Z1", "Z2"])
        self.assertEqual(tot["app"]["ep"]["t"], 55)
        self.assertEqual(tot["app"]["em"]["f"], 12)
        self.assertEqual(tot["app"]["t"]["t"], 77)
        self.assertEqual((tot["dir"]["h"], tot["ens"]["f"], tot["tous"]["t"]), (1, 2, 3))
        self.assertEqual(tot["cat"]["EDUCATEUR"]["f"], 1)
        self.assertEqual(tot["dip"]["cap_ep"]["h"], 1)
        self.assertEqual(tot["dip"]["cap_em"]["f"], 1)     # CAP sans option : celle de l'école (EM)
        self.assertEqual(tot["dip"]["ceap_ep"]["t"], 2)
        grp, tot = E.calculer(lignes, pers, "cs")
        self.assertEqual(len(grp), 1)

    def test_diplomes_prive(self):
        self.assertEqual(E.diplome_academique("Licence en sociologie"), "licence")
        self.assertEqual(E.diplome_academique("BAC D"), "bac")
        self.assertEqual(E.diplome_academique("DEUG"), "bac2")
        self.assertEqual(E.diplome_academique("Maîtrise"), "maitrise")
        self.assertEqual(E.diplome_academique("DEA"), "master")
        self.assertEqual(E.diplome_academique(""), "nr")
        self.assertEqual(E.diplome_academique("Diplôme X"), "autre")
        lignes = [{"id": 1, "nom": "EPP", "type": "EP", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 1, "zone_nom": "Z",
                   "eff": {"g": 1, "f": 1, "t": 2}},
                  {"id": 2, "nom": "EPRIV", "type": "EM", "secteur": "prive", "cs_id": 1, "cs_nom": "C", "zone_id": 1, "zone_nom": "Z",
                   "eff": {"g": 1, "f": 1, "t": 2}}]
        pers = [{"ecole_id": 1, "role": "enseignant", "sexe": "F", "diplome_academique": "Licence"},
                {"ecole_id": 2, "role": "enseignant", "sexe": "M", "diplome_academique": "BAC"},
                {"ecole_id": 2, "role": "directeur", "sexe": "F"}]
        _g, tot = E.calculer(lignes, pers, "zone")
        # le privé est à part : rien de l'école privée dans les rubriques 1 à 5
        self.assertEqual((tot["ecoles"], tot["app"]["t"]["t"], tot["tous"]["t"]), (1, 2, 1))
        self.assertEqual((tot["aca"]["licence"]["f"], tot["aca"]["bac"]["h"], tot["aca"]["nr"]["t"]), (1, 0, 0))
        self.assertEqual((tot["prive"]["ecoles"], tot["prive"]["app"]["em"]["t"], tot["prive"]["ens"]["h"],
                          tot["prive"]["dir"]["f"], tot["prive"]["em"]["t"]), (1, 2, 1, 1, 2))

    def test_ages(self):
        self.assertEqual((E.cle_age(3), E.cle_age(5), E.cle_age(11), E.cle_age(19)), ("m5", "a5", "a11", "a16"))
        self.assertEqual(E.moyenne_ecart([(6, 1), (8, 1)]), (7.0, 1.0))
        self.assertEqual(E.moyenne_ecart([(6, 0)]), (None, None))
        sec = {"ages": {"CI": {"6": [3, 1], "4": [1, 0]}, "CM2": {"11": [0, 2], "17": [1, 0]}}}
        rec = {"primaire": {"valeurs": {"t73.a4.ci_g": 5, "t73.a7.cp_f": 2}}}
        lignes = [{"id": 1, "nom": "A", "type": "EP", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 1,
                   "zone_nom": "Z", "eff": {}, "_sec_eff": sec, "_rec": rec},
                  {"id": 2, "nom": "B", "type": "EP", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 2,
                   "zone_nom": "Z2", "eff": {}, "_sec_eff": {}, "_rec": rec},          # repli sur le 7.3 de la fiche
                  {"id": 3, "nom": "P", "type": "EP", "secteur": "prive", "cs_id": 1, "cs_nom": "C", "zone_id": 1,
                   "zone_nom": "Z", "eff": {}, "_sec_eff": {"ages": {"CE1": {"8": [2, 2]}}}, "_rec": {}}]
        grp, tot = E.calculer(lignes, [], "zone")
        t = E.tableau_ages(tot["ages"])
        lg = {x["cle"]: x for x in t["lignes"]}
        self.assertEqual(lg["m5"]["cells"]["CI"][0][0], 6)                   # 1 (âges) + 5 (fiche)
        self.assertEqual(lg["a16"]["cells"]["CM2"][2][0], 1)
        self.assertEqual(t["tot"]["ENS"], [10, 5, 15])
        self.assertEqual(lg["a6"]["cells"]["CI"][0][1], round(100 * 3 / 9, 1))  # 3 G de 6 ans sur 9 G au CI
        self.assertEqual(t["stats"]["CI"][1], (6.0, 0.0))                    # 1 F de 6 ans
        m, e = t["stats"]["ENS"][2]
        self.assertTrue(m and e and e > 0)
        p = E.tableau_ages(tot["prive"]["ages"])
        self.assertEqual((p["tot"]["CE1"], p["stats"]["CE1"][2]), ([2, 2, 4], (8.0, 0.0)))

    def test_maternelles(self):
        self.assertEqual((E.cle_age_m(1), E.cle_age_m(2), E.cle_age_m(4), E.cle_age_m(7)), ("m25", "a25", "a4", "p5"))
        self.assertEqual((E.section_de("Maternelle 1"), E.section_de("GS"), E.section_de("CI")), ("SP", "SG", None))
        rec = {"maternelle": {"valeurs": {"t3.a3.pe_g": 4, "t3.a3.pe_f": 6, "t3.a5.gr_g": 5, "t3.p5.gr_f": 1}}}
        rap = {"rentree-em": {"valeurs": {"rep.debut.pet_G": 4, "rep.debut.pet_F": 6, "rep.debut.gra_G": 5,
                                          "rep.besoin.gra_F": 1}},
               "fin-em": {"valeurs": {"rep.fin.pet_G": 3, "rep.aband.gra_F": 2}}}
        lignes = [{"id": 1, "nom": "EM A", "type": "EM", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 1,
                   "zone_nom": "Z", "eff": {}, "_sec_eff": {}, "_rec": rec, "_rap": rap},
                  {"id": 2, "nom": "EM B", "type": "EM", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 2,
                   "zone_nom": "Z2", "eff": {}, "_rec": {}, "_rap": {},
                   "_sec_eff": {"ages": {"Maternelle 2": {"5": [2, 2]}}, "classes": []}},
                  {"id": 3, "nom": "EM P", "type": "EM", "secteur": "prive", "cs_id": 1, "cs_nom": "C", "zone_id": 1,
                   "zone_nom": "Z", "eff": {}, "_rec": {}, "_rap": {},
                   "_sec_eff": {"classes": [{"niveau": "Maternelle 1", "garcons": 7, "filles": 8}]}}]
        _g, tot = E.calculer(lignes, [], "zone")
        m = E.tableau_mat(tot["mat"])
        self.assertEqual((m["ecoles"], m["rec"]["SP"], m["rec"]["SG"], m["rec"]["T"]), (2, [4, 6, 10], [7, 3, 10], [11, 9, 20]))
        self.assertEqual(m["ages"]["stats"]["SP"][2], (3.0, 0.0))
        self.assertEqual(m["ages"]["tot"]["ENS"], [11, 9, 20])
        self.assertEqual((m["deb"]["T"], m["rentree"][1][2]["SG"], m["finf"]["SP"], m["fin"][3][2]["T"]),
                         ([9, 6, 15], [0, 1, 1], [3, 0, 3], [0, 2, 2]))
        self.assertEqual((m["n_rentree"], m["n_fin"], m["n_rec"]), (1, 1, 2))
        p = E.tableau_mat(tot["prive"]["mat"])
        self.assertEqual((p["ecoles"], p["rec"]["SP"], p["ages"]["vide"]), (1, [7, 8, 15], True))

    def test_infrastructures(self):
        rec_ep = {"primaire": {"valeurs": {
            "t4.s1.m_dur": "1", "t4.s1.t_toles": "1", "t4.s1.em_bon": "1", "t4.s1.et_bon": "1",
            "t4.s2.m_dur": "1", "t4.s2.t_toles": "1", "t4.s2.em_mauv": "1",
            "t4.s3.m_semi": "1", "t4.s3.t_toles": "1",
            "t4.s4.m_autre": "1", "t4.s4.t_paille": "1",
            "t4.s5.m_sans": "1",
            "t5.s1.t2": "10", "t5.s2.t3": "5", "t5.s1.t1": "2", "t5.s1.bureau": "1", "t5.bureau.armoire": "1",
            "t631.fr.ci": "30", "t631.ma.ci": "10", "salles_existantes": "5", "salles_utilisees": "4",
            "point_eau": "Oui", "electricite": "Non", "latrines": "Oui", "latrines_blocs": "1", "latrines_cabines": "3",
            "cloture": "Non"}}}
        rec_em = {"maternelle": {"valeurs": {"t8.salle.def_b": "2", "t8.salle.prov": "1", "t9.bon.chaises_enf": "20",
                                             "t9.mauv.chaises_enf": "5", "t9.bon.tabourets": "10", "t9.bon.tables_enf": "6",
                                             "eau": "Oui", "electricite": "Oui"}}}
        rap = {"rentree-ep": {"valeurs": {"infra.salles.def": "3", "infra.salles.prov": "1", "mob.tb2.CI": "8",
                                          "mob.tb3.CP": "4", "man.fr.CI": "20", "lavage": "oui"}}}
        lignes = [{"id": 1, "nom": "EPP A", "type": "EP", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 1,
                   "zone_nom": "Z", "eff": {"t": 80}, "_rec": rec_ep, "_rap": rap},
                  {"id": 2, "nom": "EM B", "type": "EM", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 1,
                   "zone_nom": "Z", "eff": {"t": 40}, "_rec": rec_em, "_rap": {}},
                  {"id": 3, "nom": "EPP privée", "type": "EP", "secteur": "prive", "cs_id": 1, "cs_nom": "C", "zone_id": 2,
                   "zone_nom": "Z2", "eff": {"t": 50}, "_rec": rec_ep, "_rap": {}}]
        grp, tot = I.calculer(lignes, "recensement", "zone")
        p = tot["pub"]
        self.assertEqual(p["salles"], {"def_b": 3, "def_m": 1, "def_n": 0, "mix": 1, "prov": 2, "sans": 1, "cons": 0})
        self.assertEqual((p["salles_tot"], p["fiches"], p["ecoles"]), (8, 2, 2))
        self.assertEqual((p["places_ep"], p["eleves_ep"], p["deficit_ep"]), (2 + 20 + 15, 80, 80 - 37))
        self.assertEqual((p["places_em"], p["eleves_em"], p["deficit_em"]), (35, 40, 5))
        self.assertEqual(p["mob_em"]["mauvais"], 5)
        self.assertEqual((p["com"]["eau"], p["com"]["elec"], p["com"]["cloture"]), ([2, 2], [1, 2], [0, 1]))
        self.assertEqual((p["p_com"]["eau"], p["p_com"]["elec"]), (100.0, 50.0))
        self.assertEqual((p["man"]["fr"], p["man_el"]["fr"]), (30, round(30 / 80, 2)))
        self.assertEqual(p["el_salle"], round(120 / 4, 1))
        self.assertEqual((tot["prv"]["ecoles"], tot["prv"]["places_ep"]), (1, 37))
        self.assertEqual([g["nom"] for g in grp], ["Z", "Z2"])
        _g, tot = I.calculer(lignes, "rentree", "cs")
        self.assertEqual((tot["pub"]["fiches"], tot["pub"]["salles"]["def_n"], tot["pub"]["places_ep"], tot["pub"]["man"]["fr"],
                          tot["pub"]["com"]["lavage"]), (1, 3, 16 + 12, 20, [1, 1]))

    def test_ecoles_structure(self):
        self.assertEqual(ES.sources_choisies(["iv. Puits", "ii. Forage fonctionnel", "iii Adduction d'eau villageoise"], ES.EAU),
                         {"puits", "forage", "aev"})
        self.assertEqual(ES.sources_choisies("SBEE;Energie solaire", ES.ELEC), {"sbee", "solaire"})
        self.assertEqual(ES.moy_ecart([2, 4, 4, 4, 5, 5, 7, 9]), {"n": 8, "moy": 5.0, "et": 2.0, "min": 2, "max": 9})
        rec = {"primaire": {"valeurs": {"classes_autorisees": "6", "classes_existantes": "5", "salles_existantes": "5",
                                        "salles_utilisees": "4", "t314.simples.ci": "1", "t314.simples.cp": "1",
                                        "t314.simples.ce1": "1", "t314.jumeles.ce2": "1", "t314.jumeles.cm1": "1",
                                        "t314.jumeles.salles": "1", "t314.multi.cm2": "1", "t314.multi.salles": "1",
                                        "point_eau": "Oui", "point_eau_src": ["iv. Puits"], "electricite": "Non",
                                        "titre_propriete": "v. Aucun Acte", "cantine": "Oui"}}}
        rec_m = {"maternelle": {"valeurs": {"sections_autorisees": "2", "sections_existantes": "2", "t4.simple.pe": "1",
                                            "t4.simple.gr": "1", "eau": "Oui", "eau_src": ["Forage"], "electricite": "Oui",
                                            "electricite_src": ["SBEE"]}}}
        rap = {"rentree-ep": {"valeurs": {"classes_autorisees": "6", "classes_ouvertes": "6", "sp.simple.CI": "1",
                                          "sp.simple.CP": "1", "sp.jumelee.CE1_CE2": "1", "sp.multi.salles": "1", "cantine": "OUI"}}}
        lignes = [{"id": 1, "nom": "EPP A", "type": "EP", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 1, "zone_nom": "Z",
                   "eff": {"t": 150, "classes": 5, "tailles": [30, 40, 20, 30, 30]}, "_rec": rec, "_rap": rap},
                  {"id": 2, "nom": "EM B", "type": "EM", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 1, "zone_nom": "Z",
                   "eff": {"t": 50, "classes": 2, "tailles": [25, 25]}, "_rec": rec_m, "_rap": {}},
                  {"id": 3, "nom": "EPP P", "type": "EP", "secteur": "prive", "cs_id": 1, "cs_nom": "C", "zone_id": 2, "zone_nom": "Z2",
                   "eff": {"t": 60, "classes": 2, "tailles": [30, 30]}, "_rec": {}, "_rap": {}}]
        _g, tot = ES.calculer(lignes, "recensement", "zone")
        p = tot["pub"]
        self.assertEqual((p["ecoles"], p["EP"], p["EM"], p["fiches"], p["aut"], p["ouv"]), (2, 1, 1, 2, 8, 7))
        self.assertEqual(p["struct"], {"simple": 5, "jumelee": 1, "multi": 1})
        self.assertEqual((p["struct_tot"], p["p_multi"]), (7, round(100 / 7, 1)))
        self.assertEqual((p["equip"]["eau"], p["equip"]["elec"], p["equip"]["titre"], p["eau_src"]["puits"], p["eau_src"]["forage"],
                          p["elec_src"]["sbee"]), ([2, 2], [1, 2], [0, 1], 1, 1, 1))
        self.assertEqual(p["stats"]["taille"], ES.moy_ecart([30, 40, 20, 30, 30, 25, 25]))
        self.assertEqual(p["stats"]["classes"]["moy"], 3.5)
        self.assertEqual((tot["prv"]["ecoles"], tot["prv"]["fiches"], tot["prv"]["stats"]["classes"]["n"]), (1, 0, 1))
        _g, tot = ES.calculer(lignes, "rentree", "cs")
        self.assertEqual((tot["pub"]["struct"], tot["pub"]["equip"]["cantine"], tot["pub"]["ouv"]),
                         ({"simple": 2, "jumelee": 1, "multi": 1}, [1, 1], 6))

    def test_rubriques(self):
        for code in RB.FICHES:
            rubs = RB.questions(code)
            self.assertTrue(rubs, code)
            titres = " ".join(r["titre"].lower() for r in rubs)
            self.assertNotIn("identification", titres, code)
        rp = RB.questions("recensement-primaire")
        ks = {q["k"]: q for r in rp for q in r["qs"]}
        self.assertEqual(ks["point_eau"]["type"], "on")
        self.assertEqual(ks["point_eau_src"]["type"], "multi")
        self.assertEqual(ks["salles_existantes"]["type"], "nb")
        self.assertIn("t314.multi.salles", ks)
        self.assertIn("t4.s1.m_dur", ks)
        self.assertIn("sp.multi.salles", {q["k"] for r in RB.questions("rentree-ep") for q in r["qs"]})
        rub = [r for r in rp if any(q["k"] == "point_eau" for q in r["qs"])]
        a, b, tot = RB.nouvel_agregat(rub), RB.nouvel_agregat(rub), RB.nouvel_agregat(rub)
        for x, v in ((a, {"point_eau": "Oui", "point_eau_src": ["iv. Puits"], "salles_existantes": "4"}),
                     (a, {"point_eau": "Non", "salles_existantes": "6"}), (b, None),
                     (b, {"point_eau": "Oui", "point_eau_src": ["iv. Puits", "i. SONEB"], "salles_existantes": "2"})):
            RB.cumuler(x, rub, v)
            RB.cumuler(tot, rub, v)
        lg = {x["lib"]: x for x in RB.lignes_rubrique(rub[0], [a, b], tot)}
        eau = next(x for k, x in lg.items() if k.startswith("3.5."))
        self.assertEqual((eau["cells"], eau["total"]), ([(1, 2, 50.0), (1, 1, 100.0)], (2, 3, 66.7)))
        puits = next(x for k, x in lg.items() if k.endswith("→ iv. Puits"))
        self.assertEqual(puits["total"], (2, 2, 100.0))
        sal = next(x for k, x in lg.items() if "salles de classes existantes" in k)
        self.assertEqual((sal["cells"], sal["total"], sal["stat"]["moy"], sal["stat"]["et"]), ([10.0, 2.0], 12.0, 4.0, 1.63))
        self.assertEqual((tot["ecoles"], tot["fiches"]), (4, 3))

    def test_cep_fiches(self):
        r9 = {"primaire": {"valeurs": {"t9.inscrits.cep_g": "20", "t9.inscrits.cep_f": "30", "t9.composes.cep_g": "20",
                                       "t9.composes.cep_f": "25", "t9.admis.cep_g": "15", "t9.admis.cep_f": "20",
                                       "t9.inscrits.cva_g": "2", "t9.admis.cva_g": "1", "t9.inscrits.eh_f": "1", "t9.admis.eh_f": "1"}}}
        r9b = {"primaire": {"valeurs": {"t9.inscrits.cep_g": "10", "t9.inscrits.cep_f": "10", "t9.composes.cep_g": "10",
                                        "t9.composes.cep_f": "10", "t9.admis.cep_g": "10", "t9.admis.cep_f": "10"}}}
        fin = {"fin-ep": {"valeurs": {"cep.insc.G": "8", "cep.insc.F": "12", "cep.pres.G": "8", "cep.pres.F": "10", "cep.adm.G": "4", "cep.adm.F": "9"}}}
        lignes = [{"id": 1, "nom": "A", "type": "EP", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 1, "zone_nom": "Z",
                   "_rec": r9, "_rap": fin, "cep": {"candidats": 50, "candidats_g": 20, "candidats_f": 30, "admis": 40, "admis_g": 16, "admis_f": 24}},
                  {"id": 2, "nom": "B", "type": "EP", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 2, "zone_nom": "Z2",
                   "_rec": r9b, "_rap": {}, "cep": {}},
                  {"id": 3, "nom": "P", "type": "EP", "secteur": "prive", "cs_id": 1, "cs_nom": "C", "zone_id": 1, "zone_nom": "Z",
                   "_rec": r9b, "_rap": {}, "cep": {}},
                  {"id": 4, "nom": "EM", "type": "EM", "secteur": "public", "cs_id": 1, "cs_nom": "C", "zone_id": 1, "zone_nom": "Z",
                   "_rec": {}, "_rap": {}, "cep": {}}]
        grp, tot = CF.calculer(lignes, "recensement", "zone")
        c = tot["pub"]["ind"]["cep"]
        self.assertEqual((tot["pub"]["ecoles"], tot["pub"]["fiches"]), (2, 2))
        self.assertEqual((c["r"]["insc"], c["r"]["comp"], c["r"]["adm"]), ([30, 40, 70], [30, 35, 65], [25, 30, 55]))
        self.assertEqual((c["p_g"], c["p_f"], c["parite"]), (42.9, 57.1, 1.33))
        self.assertEqual(c["reussite"], [round(2500 / 30, 1), round(3000 / 35, 1), round(5500 / 65, 1)])
        self.assertEqual(c["presence"][2], round(6500 / 70, 1))
        self.assertEqual(tot["pub"]["ind"]["ens"]["r"]["insc"], [32, 40, 72])          # CEP + CEP Vie active
        self.assertEqual(tot["pub"]["ind"]["eh"]["reussite"][1], 100.0)                 # pas de « ont composé » : base inscrits
        d = tot["pub"]["disp"]["T"]
        self.assertEqual((d["n"], d["cent"], d["sous50"], d["max"]), (2, 1, 0, 100.0))
        self.assertEqual(d["moy"], round((3500 / 45 + 100) / 2, 1))
        self.assertEqual(tot["prv"]["ecoles"], 1)
        _g, tot = CF.calculer(lignes, "fin", "cs")
        self.assertEqual((tot["pub"]["ind"]["cep"]["r"]["comp"], tot["pub"]["ind"]["cep"]["reussite"][2]), ([8, 10, 18], round(1300 / 18, 1)))
        _g, tot = CF.calculer(lignes, "module", "cs")
        self.assertEqual((tot["pub"]["fiches"], tot["pub"]["ind"]["cep"]["reussite"]), (1, [80.0, 80.0, 80.0]))

    def test_courbes(self):
        s = str(E.svg_courbes(["A", "B"], [("X", "#000", [1, 3]), ("Y", "#111", [2, None])]))
        self.assertIn("<polyline", s)
        self.assertIn("A – X : 1", s)
        self.assertEqual(str(E.svg_courbes([], [])), "")

    def test_comparatif(self):
        vue = [{"titre": "1. IDENTIFICATION", "champs": [("1", "Nom", "X")], "tableaux": []},
               {"titre": "4. Infrastructures", "champs": [("4.1", "Salles", "3")],
                "tableaux": [{"titre": "t", "coin": "", "colonnes": ["Bon", "Mauvais"],
                              "lignes": [{"lib": "Classes", "cells": ["2", "1"]}]}]}]
        self.assertEqual(F.rubriques_chiffrees(vue), [1])
        lg = F.comparer([vue, None], vue, 1)
        self.assertEqual([(x["ligne"], x["colonne"], x["vals"], x["total"]) for x in lg],
                         [("4.1 Salles", "", [3.0, None], 3.0), ("Classes", "Bon", [2.0, None], 2.0),
                          ("Classes", "Mauvais", [1.0, None], 1.0)])


SCRIPT = r'''
import html, json, os, sys, tempfile
P = os.environ["PREFIXE_SCRIPT"]
os.environ[P + "_EDITION"] = os.environ["EDITION_SCRIPT"]; os.environ[P + "_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config, demo_juridiction
from app import app, q, ex
app.config["TESTING"] = True
demo_juridiction.main()
import m_juridiction as J
def ok(r, code=200):
    assert r.status_code == code, (r.request.path, r.status_code, r.data[-1500:]); return r
def txt(r): return html.unescape(r.data.decode())
with app.app_context():
    a = J.annee()
    c1 = J.cs_liste()[0]
    ex("INSERT OR REPLACE INTO jur_cp_programmes (cs_id, annee, periode, acteur, indicateur, valeur, maj) VALUES (?,?,?,?,?,?,datetime('now'))",
       (c1["id"], a, "T1", "ccs", "su_t", 10))
    ex("INSERT INTO jur_cp_activites (cs_id, zone_id, annee, categorie, date_debut, designation, nb, statut, cree_le) VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
       (c1["id"], None, a, "suivi", a[:4] + "-10-05", "Suivi", 1, "realisee"))
    e = q("SELECT * FROM jur_ecoles WHERE type='EP' AND cs_id=? ORDER BY id", (c1["id"],), un=True)
    ex("INSERT OR REPLACE INTO jur_sections (ecole_id, annee, section, donnees, source, maj) VALUES (?,?,?,?,?,datetime('now'))",
       (e["id"], a, "rapports", json.dumps({"rentree-ep": {"annee": a, "valeurs": {"nom_ecole": e["nom"]}}}), "test"))
c = app.test_client(); ok(c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"}), 302)
t = txt(ok(c.get("/juridiction/tableau-de-bord?periode=T1")))
assert "Programmation et bilan des activités pédagogiques" in t and "Conseillers pédagogiques (CP)" in t
i_ccs, i_cp = t.find("Chef"), t.find("Conseillers pédagogiques (CP)")
assert 0 < i_ccs < i_cp, (i_ccs, i_cp)                      # les CCS avant les CP
assert "1 / 10" in t.replace("<span class=\"gris\"> / ", " / ").replace("</span>", ""), "suivi du CCS : 1 réalisé / 10 programmés"
t = txt(ok(c.get("/juridiction/effectifs")))
for k in ("1. Apprenants", "2. Personnel enseignant", "ACDPCTD (AME)", "Éducateur", "CAP – EP", "CEAP – EM", "<polyline",
          "5. Diplômes académiques", "Licence", "Doctorat", "6. Secteur privé (à part)", "Écoles privées (à part)", "7. Catégories d'âge", "Moins de 5 ans",
          "16 ans et plus", "Écart type", "Âge moyen", "8. Écoles maternelles", "Section des petits (SP)",
          "Section des grands (SG)", "Rapport de rentrée (EM)", "Fiche de fin d'année (EM)", "Moins de 2 ans ½"):
    assert k in t, k
assert ok(c.get("/juridiction/effectifs?par=ecole")).status_code == 200
x = ok(c.get("/juridiction/effectifs?export=xlsx")); assert x.data[:2] == b"PK"
with app.app_context():
    e = q("SELECT * FROM jur_ecoles WHERE type='EP' AND secteur='public' AND cs_id=? ORDER BY id", (c1["id"],), un=True)
    ex("INSERT OR REPLACE INTO jur_sections (ecole_id, annee, section, donnees, source, maj) VALUES (?,?,?,?,?,datetime('now'))",
       (e["id"], a, "recensement", json.dumps({"primaire": {"valeurs": {"t4.s1.m_dur": "1", "t4.s1.t_toles": "1", "t5.s1.t2": "12",
                                                                        "point_eau": "Oui", "t631.fr.ci": "9"}}}), "test"))
t = txt(ok(c.get("/juridiction/infrastructures")))
for k in ("Infrastructures et mobilier", "1. Salles de classe", "2. Commodités", "Places assises", "Déficit de places",
          "4. Mobilier de la maternelle", "5. Manuels du primaire", "Secteur public", "<polyline"):
    assert k in t, k
for u in ("?source=rentree", "?source=fin&par=ecole", "?par=zone"):
    ok(c.get("/juridiction/infrastructures" + u))
x = ok(c.get("/juridiction/infrastructures?export=xlsx")); assert x.data[:2] == b"PK"
t = txt(ok(c.get("/juridiction/ecoles-structure")))
for k in ("Écoles : nombre, structure", "Structure pédagogique", "Multigrades", "Écart type", "Puits", "Électricité", "<polyline"):
    assert k in t, k
for u in ("?source=rentree", "?source=fin&par=ecole"):
    ok(c.get("/juridiction/ecoles-structure" + u))
x = ok(c.get("/juridiction/ecoles-structure?export=xlsx")); assert x.data[:2] == b"PK"
t = txt(ok(c.get("/juridiction/fiches/rubriques")))
assert "Rubriques des fiches, consolidées" in t and "Écart type" in t and "point d'eau" in t.replace("’", "'"), t[-3000:]
for fi in ("recensement-maternelle", "rentree-ep", "fin-ep", "rentree-em", "fin-em"):
    for sc in ("public", "prive"):
        ok(c.get(f"/juridiction/fiches/rubriques?fiche={fi}&sect={sc}&par=ecole"))
x = ok(c.get("/juridiction/fiches/rubriques?export=xlsx")); assert x.data[:2] == b"PK"
t = txt(ok(c.get("/juridiction/cep/fiches")))
for k in ("CEP : candidats et réussite", "Inscrits", "Parité F/G", "Taux de réussite", "Rubrique 9", "CEP Vie active", "Écart type"):
    assert k in t, k
for u in ("?source=fin", "?source=module&par=ecole"):
    ok(c.get("/juridiction/cep/fiches" + u))
x = ok(c.get("/juridiction/cep/fiches?export=xlsx")); assert x.data[:2] == b"PK"
for fiche in ("recensement-primaire", "recensement-maternelle", "rentree-ep", "fin-ep", "rentree-em", "fin-em"):
    t = txt(ok(c.get("/juridiction/fiches/tableaux?fiche=" + fiche)))
    assert "Tableaux globaux des fiches" in t and "Rubrique" in t, fiche
x = ok(c.get("/juridiction/fiches/tableaux?fiche=rentree-ep&format=xlsx")); assert x.data[:2] == b"PK"
t = txt(ok(c.get("/juridiction/tableau-de-bord")))
assert "Tableaux globaux" in t and "/juridiction/effectifs" in t       # menu
# division DOSP / statistiques : accès au module Effectifs et aux tableaux globaux
d = app.test_client(); ok(d.post("/login", data={"identifiant": "chef", "mdp": "demo1234"}), 302)
ok(d.get("/juridiction/effectifs"))
ok(d.get("/juridiction/infrastructures"))
ok(d.get("/juridiction/ecoles-structure"))
print("OK-" + config.EDITION)
'''


class TestParcours(unittest.TestCase):
    def test_cs(self):
        r = lancer(SCRIPT, "cs")
        self.assertIn("OK-cs", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])

    def test_ddemp(self):
        r = lancer(SCRIPT, "ddemp")
        self.assertIn("OK-ddemp", r.stdout, r.stdout[-3000:] + r.stderr[-6000:])


if __name__ == "__main__":
    unittest.main()
