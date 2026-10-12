# -*- coding: utf-8 -*-
"""Données de démonstration des applications Circonscription (CS) et DDEMP.

    GESCOL_EDITION=cs    GESCOL_DATA=dossier python3 demo_juridiction.py      → CS de Pobè (Plateau)
    GESCOL_EDITION=ddemp GESCOL_DATA=dossier python3 demo_juridiction.py      → DDEMP du Plateau (6 CS)

Comptes (mot de passe demo1234) : responsable, cp1, cp2, chef (DOSP), rh (Ressources humaines), agent ; admin / admin123.
Les écoles « envoient » de vrais paquets de transmission (jur_format), importés comme le ferait la CS.
v1.6 : unités pédagogiques (jur_up, jur_up_activites) et CP de chaque zone pédagogique (jur_zones.cp_nom).
"""
import random
from datetime import date

from werkzeug.security import generate_password_hash

import config
import jur_format
import m_juridiction as J
import referentiel_benin as RB
from app import app
from db import ex, q

NOMS = ["ADJAHO", "AGOSSOU", "AKPO", "ASSOGBA", "AVOCE", "BIAOU", "DOSSOU", "FADONOUGBO", "GBAGUIDI", "HOUNKPE",
        "KOUTON", "LAWANI", "OLOU", "OGOUBIYI", "SALAMI", "SOSSOU", "TOSSOU", "YESSOUFOU", "ZINSOU", "OKE", "ADEOTI",
        "AFOLABI", "IDOWU", "OLADELE", "AMOUSSA", "BELLO", "OGOUNDELE", "KPADONOU", "HOUNSOU", "AHOUANSOU"]
PRENOMS_H = ["Koffi", "Rachidi", "Moïse", "Salomon", "Aimé", "Jean", "Fiacre", "Sylvain", "Basile", "Gildas", "Bio", "Idrissou"]
PRENOMS_F = ["Afiavi", "Rosine", "Pélagie", "Bernadette", "Odile", "Mariam", "Céline", "Florence", "Grâce", "Yvette", "Sika", "Nafissatou"]
VILLAGES = ["Issaba", "Towé", "Igana", "Ahoyéyé", "Pobè-Centre", "Onigbolo", "Okeita", "Iko", "Adjégounlè", "Ita-Djèbou",
            "Kétou-Centre", "Idigny", "Sakété", "Ifangni", "Adja-Ouèrè", "Massè", "Ikpinlè", "Okpomèta", "Ilikimou", "Banigbé"]
NIV_EP = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
AGE_EP = {"CI": 6, "CP": 7, "CE1": 8, "CE2": 9, "CM1": 10, "CM2": 11}


def personne(rnd, role, categorie, fonction, classe="", sexe=None):
    sexe = sexe or rnd.choice("MF")
    lettre = {"FE": rnd.choice("AB"), "ACDPE": rnd.choice("BC"), "ACDPCTD": "C", "PRIVE": "C"}.get(categorie, "B")
    naiss = rnd.randint(1965, 2000)
    if rnd.random() < 0.12:
        naiss = {"A": 1966, "B": 1968, "C": 1971}[lettre] + rnd.randint(0, 2)   # proches de la retraite
    ps = max(naiss + 22, rnd.randint(1990, 2024))
    cap = categorie in ("FE", "ACDPE") or rnd.random() < 0.3
    apt = rnd.random() < 0.6
    return {
        "nom": rnd.choice(NOMS), "prenoms": rnd.choice(PRENOMS_H if sexe == "M" else PRENOMS_F), "sexe": sexe,
        "nip": "" if categorie == "PRIVE" else str(rnd.randint(10**11, 10**12 - 1)),
        "matricule": "" if categorie == "PRIVE" else str(rnd.randint(100000, 999999)),
        "date_naissance": f"{naiss}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}", "telephone": f"01{rnd.randint(40000000, 99999999)}",
        "email": "", "fonction": fonction, "role": role, "categorie": categorie,
        "grade": f"{lettre}{rnd.randint(1, 3)}-{rnd.randint(1, 15)}" if categorie != "PRIVE" else "",
        "indice_paye": str(rnd.randint(300, 900)), "indice_reel": str(rnd.randint(300, 950)),
        "date_premiere_ps": f"{ps}-10-01", "date_ps_departement": f"{max(ps, 2005)}-10-01",
        "date_ps_commune": f"{max(ps, 2010)}-10-01", "date_ps_ecole": f"{max(ps, rnd.randint(2015, 2025))}-10-01",
        "diplome_academique": rnd.choice(["BEPC", "BAC", "Licence", "Master", "BAC"]), "annee_diplome": str(naiss + 19),
        "ceap": cap or rnd.random() < 0.5, "annee_ceap": str(ps + 1), "cap": cap, "annee_cap": str(ps + 4) if cap else "",
        "type_cap": rnd.choice(["EP", "EP", "EM"]) if cap else "", "visite_aptitude": apt,
        "note_aptitude": round(rnd.uniform(10, 18), 1) if apt else "", "annee_aptitude": str(rnd.randint(2012, 2025)) if apt else "",
        "departement_a_servir": "Plateau", "nb_visites_cp": rnd.randint(0, 3), "nb_visites_ccs": rnd.randint(0, 1),
        "participation_up": rnd.choice([60, 75, 80, 90, 100]), "gestion_collegiale": rnd.choice(["", "Trésorier APE", "Coopérative"]),
        "note_evaluation": round(rnd.uniform(12, 19), 1), "classe": classe, "actif": True,
    }


def paquet_ecole(rnd, code, nom, typ, secteur, dep, cs, zone, an):
    a0 = int(an[:4])
    classes, ages, pers = [], {}, []
    cat_pub = lambda: rnd.choice(["FE", "FE", "ACDPE", "ACDPE", "ACDPCTD"])  # noqa: E731
    if typ == "EP":
        double = rnd.random() < 0.25
        for niv in NIV_EP:
            for lettre in (("A", "B") if double and niv in ("CI", "CP") else ("",)):
                g_, f_ = rnd.randint(8, 30), rnd.randint(8, 30)
                ens = personne(rnd, "enseignant", cat_pub() if secteur == "public" else "PRIVE",
                               "Instituteur" if secteur == "public" else "Enseignant", f"{niv} {lettre}".strip())
                pers.append(ens)
                classes.append({"nom": f"{niv} {lettre}".strip(), "niveau": niv, "garcons": g_, "filles": f_,
                                "redoublants_g": rnd.randint(0, 3), "redoublants_f": rnd.randint(0, 3),
                                "titulaire_nom": f"{ens['nom']} {ens['prenoms']}", "titulaire_sexe": ens["sexe"],
                                "groupe": "simple"})
                base = AGE_EP[niv]
                d = ages.setdefault(niv, {})
                for _ in range(g_ + f_):
                    a = base + rnd.choice([-1, 0, 0, 0, 1, 1, 2])
                    d.setdefault(str(a), [0, 0])[rnd.randint(0, 1)] += 1
    else:
        for niv in (["Maternelle 1", "Maternelle 2"] if typ == "EM" else ["Espace enfance"]):
            g_, f_ = rnd.randint(8, 25), rnd.randint(8, 25)
            ens = personne(rnd, "enseignant", cat_pub() if secteur == "public" else "PRIVE", "Éducateur / Éducatrice",
                           niv, sexe="F" if rnd.random() < .8 else "M")
            pers.append(ens)
            classes.append({"nom": niv, "niveau": niv, "garcons": g_, "filles": f_, "redoublants_g": 0, "redoublants_f": 0,
                            "titulaire_nom": f"{ens['nom']} {ens['prenoms']}", "titulaire_sexe": ens["sexe"], "groupe": "simple"})
            ages[niv] = {"4": [g_ // 2, f_ // 2], "5": [g_ - g_ // 2, f_ - f_ // 2]}
    d = personne(rnd, "directeur", cat_pub() if secteur == "public" else "PRIVE",
                 "Directeur" if rnd.random() < .6 else "Directrice")
    d["categorie"] = "FE" if secteur == "public" and rnd.random() < .7 else d["categorie"]
    pers.insert(0, d)
    if rnd.random() < 0.5:
        pers.append(personne(rnd, "soutien", "AUTRE", rnd.choice(["Gardien", "Cuisinière", "Agent d'entretien"])))
    visites = []
    for _ in range(rnd.randint(0, 4)):
        e = rnd.choice(pers[1:] or pers)
        visites.append({"date": f"{a0}-{rnd.choice([11, 12])}-{rnd.randint(1, 28):02d}", "type": rnd.choice(["CP", "CP", "CCS"]),
                        "visiteur": rnd.choice(["KOUTON Basile", "OLOU Rosine", "HOUNGBO Pascal"]),
                        "enseignant": f"{e['nom']} {e['prenoms']}", "enseignant_nip": e["nip"], "classe": e["classe"],
                        "discipline": rnd.choice(["Français", "Mathématiques", "Éducation scientifique"]),
                        "sequence": "SA 2", "note": round(rnd.uniform(9, 17), 1), "effectif_g": 20, "effectif_f": 18,
                        "recommandations": "Renforcer la phase d'évaluation."})
    secs = {"effectifs": {"classes": classes, "ages": ages, "nouveaux_ci": [rnd.randint(10, 30), rnd.randint(10, 30)],
                          "handicapes": [rnd.randint(0, 2), rnd.randint(0, 2)], "salles": len(classes)},
            "personnel": pers, "visites": visites,
            "cantine": {"existe": secteur == "public" and rnd.random() < .7, "beneficiaires": rnd.randint(50, 200),
                        "montant_annee": rnd.randint(100, 900) * 1000},
            "patrimoine": {"salles_classe": len(classes), "salles_bon_etat": max(0, len(classes) - rnd.randint(0, 2)),
                           "latrines": rnd.randint(0, 4), "point_eau": rnd.random() < .6, "electricite": rnd.random() < .4,
                           "tables_bancs": rnd.randint(40, 120)}}
    if typ == "EP":
        cm2 = [c for c in classes if c["niveau"] == "CM2"]
        cm1 = [c for c in classes if c["niveau"] == "CM1"]
        cg, cf = sum(c["garcons"] for c in cm2), sum(c["filles"] for c in cm2)
        taux = rnd.uniform(0.45, 0.98)
        secs["cep"] = {"session": str(a0 + 1), "candidats_g": cg, "candidats_f": cf,
                       "admis_g": round(cg * taux), "admis_f": round(cf * min(1, taux + rnd.uniform(-.08, .08))),
                       "cm1_g": sum(c["garcons"] for c in cm1), "cm1_f": sum(c["filles"] for c in cm1),
                       "cm2_g": cg, "cm2_f": cf, "liste": []}
    ident = {"code": code, "nom": nom, "type": typ, "secteur": secteur, "departement": dep, "cs": cs, "zone": zone,
             "commune": cs.split()[0].title(), "arrondissement": "", "localite": rnd.choice(VILLAGES), "adresse": "",
             "telephone": "", "email": "", "directeur_titre": "Directrice" if d["sexe"] == "F" else "Directeur",
             "directeur_nom": f"{d['nom']} {d['prenoms']}", "directeur_tel": d["telephone"],
             "annee_creation": str(rnd.randint(1950, 2018))}
    p = jur_format.nouveau("ecole", code, nom, an, dep, cs, "publique" if secteur == "public" else "privee", "GESCOL démo")
    p["genere_le"] = f"{date.today().isoformat()} 08:00:00"
    p["ecoles"] = [{"ecole": ident, "sections": secs}]
    return jur_format.sceller(p)


def ecoles_de_cs(rnd, dep, cs, nb_zones, n):
    """Liste (code, nom, type, secteur, zone) d'écoles fictives pour une CS."""
    out = []
    for i in range(n):
        typ = "EP" if i < n * 0.7 else ("EM" if i < n * 0.92 else "EE")
        sect = "prive" if rnd.random() < 0.2 else "public"
        vil = rnd.choice(VILLAGES)
        nom = {"EP": ("EPP " if sect == "public" else "EPPr ") + vil, "EM": ("EM " if sect == "public" else "EM privée ") + vil,
               "EE": "Espace enfance " + vil}[typ] + ("" if i < 10 else f" {i}")
        code = f"{''.join(ch for ch in J.norm(cs) if ch.isalnum())[:6]}-{typ}{i + 1:03d}"
        out.append((code, nom, typ, sect, f"Zone pédagogique {1 + i % max(1, nb_zones)}"))
    return out


def agents_cs(rnd, cs_nom):
    postes = [("ccs", "Chef de la Circonscription Scolaire", "ccs"), ("animation", "Conseiller pédagogique", "cp"),
              ("animation", "Conseiller pédagogique", "cp"), ("animation", "Conseiller pédagogique", "cp"),
              ("secretariat", "Chef Division Secrétariat (CDS)", "chef_service"),
              ("personnel", "Chef du Service des Ressources Humaines (RH)", "chef_service"),
              ("animation", "Chef Division Animation Pédagogique (CDAP)", "chef_service"),
              ("organisation", "Chef Division Organisation Scolaire et Prévision (CDOSP)", "chef_service"),
              ("secretariat", "Secrétaire", "administratif"), ("administration", "Agent d'entretien", "soutien")]
    out = []
    for svc, poste, role in postes:
        p = personne(rnd, role, "FE" if role in ("ccs", "cp", "chef_service") else rnd.choice(["ACDPE", "AUTRE"]), poste)
        p.update(service_code=svc, poste=poste)
        out.append(p)
    return out


THEMES_UP = ["Planification des situations d'apprentissage en mathématiques", "Leçon modèle de lecture au CI",
             "Évaluation des acquis : construction d'une épreuve", "Gestion d'une classe multigrade",
             "Exploitation du cahier de textes et du cahier journal", "Didactique de l'éducation scientifique et technologique",
             "Préparation du CEP blanc", "Techniques d'animation de la maternelle"]
TYPES_UP = ["Animation pédagogique", "Leçon modèle", "Atelier", "Formation"]
CP_ZONES = ["KOUTON Basile", "OLOU Rosine", "AKPO Fiacre", "SOSSOU Mariam"]


def inserer_up(rnd, cs_id, an):
    """Unités pédagogiques de démonstration (1 à 2 par zone) avec leurs activités de l'année (v1.6)."""
    a0 = int(an[:4])
    zones = q("SELECT * FROM jur_zones WHERE cs_id=? ORDER BY ordre, nom", (cs_id,))
    for i, z in enumerate(zones):
        if not z["cp_nom"]:
            ex("UPDATE jur_zones SET cp_nom=?, cp_telephone=? WHERE id=?",
               (CP_ZONES[i % len(CP_ZONES)], f"01{rnd.randint(40000000, 99999999)}", z["id"]))
        ecs = q("SELECT id, nom FROM jur_ecoles WHERE zone_id=? AND actif=1 ORDER BY nom", (z["id"],))
        for n in range(rnd.randint(1, 2)):
            num = i * 2 + n + 1
            siege = ecs[n % len(ecs)] if ecs else None
            uid = ex("INSERT INTO jur_up (cs_id, zone_id, nom, ecole_siege, ecole_id, rup_nom, rup_tel, corup_nom, corup_tel, "
                     "nb_ecoles, actif, cree_le, maj) VALUES (?,?,?,?,?,?,?,?,?,?,1,datetime('now','localtime'),datetime('now','localtime'))",
                     (cs_id, z["id"], f"UP {num}", siege["nom"] if siege else "", siege["id"] if siege else None,
                      f"{rnd.choice(NOMS)} {rnd.choice(PRENOMS_H + PRENOMS_F)}", f"01{rnd.randint(40000000, 99999999)}",
                      f"{rnd.choice(NOMS)} {rnd.choice(PRENOMS_H + PRENOMS_F)}", f"01{rnd.randint(40000000, 99999999)}",
                      max(2, len(ecs) // 2 + rnd.randint(0, 2))))
            mois = [(a0, 10), (a0, 11), (a0, 12), (a0 + 1, 1), (a0 + 1, 2), (a0 + 1, 3)]
            for k, (y, m) in enumerate(mois[:rnd.randint(3, 6)]):
                prevue, executee = 1, 1 if k < 3 and rnd.random() < 0.85 else (1 if rnd.random() < 0.3 else 0)
                ex("INSERT INTO jur_up_activites (up_id, annee, date, theme, type, prevue, executee, participants, "
                   "taux_participation, observations, maj) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                   (uid, an, f"{y}-{m:02d}-{rnd.randint(5, 26):02d}", rnd.choice(THEMES_UP), rnd.choice(TYPES_UP), prevue, executee,
                    rnd.randint(8, 25) if executee else None, round(rnd.uniform(60, 100), 1) if executee else None, ""))


def inserer_lignes_action(rnd, an):
    """v1.6 (a_divisions) : lignes d'action de chaque division générées depuis les puces de ses attributions (AOF),
    avec un état varié (prévue / en cours / réalisée / reportée) pour la démonstration."""
    import json
    import a_divisions as AD
    import a_structure as S
    n = S.niveau()
    if not n:
        return
    a0 = int(an[:4])
    for svc in S.services():
        if q("SELECT 1 FROM jur_lignes_action WHERE niveau=? AND service_code=? AND annee=?", (n, svc["code"], an), un=True):
            continue
        mods = [m[1] for m in AD.MODULES_PAR_DIVISION.get(svc["code"], [])]
        chef = svc.get("responsable_nom") or ""
        for i, lib in enumerate(AD.lignes_depuis_attributions(svc["attributions"]), start=1):
            etat = rnd.choice(["prévue", "en cours", "en cours", "réalisée", "réalisée", "reportée"])
            taux = {"prévue": 0, "en cours": rnd.choice([25, 40, 50, 60, 75]), "réalisée": 100, "reportée": rnd.choice([0, 10, 20])}[etat]
            ech = rnd.choice([f"{a0}-12-20", f"{a0 + 1}-03-31", f"{a0 + 1}-06-30", "Toute l'année", "2e trimestre"])
            ex("INSERT INTO jur_lignes_action (niveau, service_code, annee, ordre, libelle, indicateur, cible, echeance, responsable, "
               "modules, etat, taux, observations, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
               (n, svc["code"], an, i, lib, rnd.choice(["Nombre d'activités réalisées", "Taux de couverture", "Rapport transmis", ""]),
                rnd.choice(["100 %", "Toutes les écoles", "1 par trimestre", ""]), ech, chef,
                json.dumps(rnd.sample(mods, min(len(mods), rnd.randint(0, 2))), ensure_ascii=False), etat, taux,
                "Reporté : attente des crédits." if etat == "reportée" else ""))
        ex("INSERT OR REPLACE INTO jur_lignes_action_gen (niveau, service_code, annee, maj) VALUES (?,?,?,datetime('now','localtime'))",
           (n, svc["code"], an))


def creer_comptes():
    """Comptes de démonstration. v1.6 : « chef » est rattaché à la division de l'Organisation Scolaire et de la Prévision
    (DOSP, code organisation ; DDEMP : Service des Écoles Maternelles et Primaires, semp) et « rh » au Service des
    Ressources Humaines (code personnel ; DDEMP : srh) : leur périmètre d'accès (a_integration) se limite aux modules
    de leur division (utilisateurs.service_code)."""
    for ident, nom, role, svc in (("responsable", "Responsable (démo)", "responsable", None), ("cp1", "KOUTON Basile", "cp", None),
                                  ("cp2", "OLOU Rosine", "cp", None),
                                  ("chef", "Chef de division DOSP (démo)", "chef_service", "organisation"),
                                  ("rh", "Chef du Service des Ressources Humaines (démo)", "chef_service", "personnel"),
                                  ("agent", "Agent (démo)", "agent", None)):
        if not q("SELECT 1 FROM utilisateurs WHERE identifiant=?", (ident,), un=True):
            ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp) VALUES (?,?,?,?,0)",
               (ident, nom, role, generate_password_hash("demo1234")))
        if svc and "service_code" in {c[1] for c in q("PRAGMA table_info(utilisateurs)")}:
            # DDEMP : le SRH porte le code « srh » et l'organisation scolaire relève du SEMP
            code = {"personnel": "srh", "organisation": "semp"}.get(svc, svc) if config.EDITION == "ddemp" else svc
            ex("UPDATE utilisateurs SET service_code=? WHERE identifiant=? AND (service_code IS NULL OR service_code='')", (code, ident))


def inserer_agents(liste, cs_id=None):
    import json
    for a in liste:
        extra = {k: v for k, v in a.items() if k not in ("nom", "prenoms", "sexe", "nip", "matricule", "telephone", "email",
                                                         "service_code", "poste")}
        ex("INSERT INTO jur_agents (cs_id, service_code, poste, nom, prenoms, sexe, nip, matricule, telephone, email, donnees, maj) "
           "VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
           (cs_id, a["service_code"], a["poste"], a["nom"], a["prenoms"], a["sexe"], a["nip"], a["matricule"],
            a["telephone"], a.get("email", ""), json.dumps(extra, ensure_ascii=False)))


def inserer_examen_blanc(rnd, an):
    """v1.6 (a_integration) : un examen blanc CS / DDEMP avec des candidats de CM2 pour chaque école primaire
    (notes aléatoires). Les écoles s'ouvrent ensuite depuis « Administration › Ouvrir une école (modules) »."""
    import json
    mats = ["Français", "Mathématiques", "Éducation scientifique et technologique", "Éducation sociale"]
    niv = "CS" if config.EDITION == "cs" else "DDEMP"
    sid = ex("INSERT INTO jur_cep_blanc_sessions (annee, numero, nom, date, niveau, matieres, seuil, cree_le) "
             "VALUES (?,?,?,?,?,?,?,datetime('now','localtime'))",
             (an, 1, f"Examen blanc {niv} N° 1", f"{int(an[:4]) + 1}-03-15", "CM2", json.dumps(mats, ensure_ascii=False), None))
    for e in J.ecoles(type_="EP"):
        eff = J.section(e["id"], "effectifs", an) or {}
        cm2 = [c for c in eff.get("classes", []) if c.get("niveau") == "CM2"]
        n = sum(int(c.get("garcons") or 0) + int(c.get("filles") or 0) for c in cm2) or rnd.randint(10, 30)
        base = rnd.uniform(7, 14)
        for i in range(min(n, 40)):
            notes = {m: round(min(20, max(0, rnd.gauss(base, 3.5))), 1) for m in mats}
            ex("INSERT INTO jur_cep_blanc_resultats (session_id, ecole_id, zone, numero_table, nom, prenoms, sexe, notes, maj) "
               "VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'))",
               (sid, e["id"], e["zone_nom"] or "", f"{e['id']:02d}{i + 1:03d}", rnd.choice(NOMS),
                rnd.choice(PRENOMS_H + PRENOMS_F), rnd.choice("MF"), json.dumps(notes, ensure_ascii=False)))
    return sid


def inserer_synoptique(niveau, an):
    """v1.6 (a_synoptique) : identité de la structure (tableau synoptique de la CS / DDEMP) et quelques membres de
    comités (conseil de direction, cantines, jury CEP)."""
    if q("SELECT 1 FROM jur_synoptique_identite WHERE id=1", un=True):
        return
    if niveau == "cs":
        ident = {"ddemp_nom": "Gildas AKPO", "arrondissements": "Pobè, Issaba, Towé, Igana, Ahoyéyé", "commune": "Pobè",
                 "resp_grade": "A1-7", "resp_prise_fonction": "2021-10-01", "annee_creation": "1998", "adresse": "Quartier Alakoutin, Pobè"}
    else:
        ident = {"commune": "Pobè", "resp_grade": "A1-9", "resp_prise_fonction": "2020-09-15", "annee_creation": "1990",
                 "adresse": "Route de Kétou, Pobè"}
    cols = list(ident)
    ex(f"INSERT INTO jur_synoptique_identite (id, {', '.join(cols)}, maj) VALUES (1, {', '.join('?' * len(cols))}, datetime('now','localtime'))",
       tuple(ident[k] for k in cols))
    membres = [("conseil", "", "HOUNGBO Pascal" if niveau == "cs" else "AKPO Gildas", "Président(e)", "CS" if niveau == "cs" else "DDEMP"),
               ("conseil", "", "KOUTON Basile", "Membre", "CS" if niveau == "cs" else "DDEMP"),
               ("cantine", "", "DOSSOU Paul", "Président(e)", "Mairie / commune"),
               ("cantine", "", "HOUNSOU Marie", "Trésorier(ère)", "APE / parents d'élèves"),
               ("cep", "", "OLOU Rosine", "Secrétaire", "CS" if niveau == "cs" else "DDEMP")]
    for i, (comite, lib, nom, qual, orig) in enumerate(membres, 1):
        ex("INSERT INTO jur_synoptique_membres (annee, comite, libelle, ordre, nom_prenoms, qualite, origine, contact, observations, maj) "
           "VALUES (?,?,?,?,?,?,?,?,?,datetime('now','localtime'))", (an, comite, lib, i, nom, qual, orig, "", ""))


def main():
    niveau = config.EDITION
    if niveau not in ("cs", "ddemp"):
        raise SystemExit("Lancez avec GESCOL_EDITION=cs ou GESCOL_EDITION=ddemp")
    rnd = random.Random(2027)
    an = config.ANNEE_ACTIVE
    dep = "Plateau"
    with app.app_context():
        creer_comptes()
        if niveau == "cs":
            J.configurer("cs", dep, "POBE", responsable_titre="Le Chef de la Circonscription Scolaire",
                         responsable_nom="Pascal HOUNGBO", ville="Pobè", telephone="0197000000")
            for code, nom, typ, sect, zone in ecoles_de_cs(rnd, dep, "POBE", 3, 18):
                J.importer_paquet(paquet_ecole(rnd, code, nom, typ, sect, dep, "POBE", zone, an), "fichier", "démo")
            inserer_agents(agents_cs(rnd, "POBE"), (J.cs_courante() or {"id": None})["id"])
            inserer_up(rnd, J.cs_courante()["id"], an)
            print(f"CS de Pobè : {q('SELECT COUNT(*) n FROM jur_ecoles', un=True)['n']} écoles importées, "
                  f"{q('SELECT COUNT(*) n FROM jur_up', un=True)['n']} UP.")
        else:
            J.configurer("ddemp", dep, responsable_titre="Le Directeur Départemental", responsable_nom="Gildas AKPO",
                         ville="Pobè")
            for c in RB.CIRCONSCRIPTIONS[dep]:
                p = jur_format.nouveau("cs", f"CS-{c['cs']}", f"Circonscription scolaire de {c['cs'].title()}", an, dep,
                                       c["cs"], "cs", "GESCOL démo")
                p["genere_le"] = f"{date.today().isoformat()} 09:00:00"
                for code, nom, typ, sect, zone in ecoles_de_cs(rnd, dep, c["cs"], c["zones"], rnd.randint(8, 14)):
                    p["ecoles"] += paquet_ecole(rnd, code, nom, typ, sect, dep, c["cs"], zone, an)["ecoles"]
                p["cs"] = {"identite": {"departement": dep, "nom": c["cs"], "ccs_titre": "Le Chef de la Circonscription Scolaire",
                                        "ccs_nom": f"{rnd.choice(PRENOMS_H)} {rnd.choice(NOMS)}"},
                           "sections": {"agents": agents_cs(rnd, c["cs"])}}
                J.importer_paquet(jur_format.sceller(p), "fichier", "démo")
            inserer_agents([dict(personne(rnd, "chef_service", "FE", poste), service_code=svc, poste=poste) for svc, poste in
                            (("direction", "Directeur Départemental"), ("sec", "Chef du Service des Examens et Concours"),
                             ("semp", "Chef du Service des Écoles Maternelles et Primaires"),
                             ("srh", "Chef du Service des Ressources Humaines"),
                             ("spaf", "Chef du Service de la Planification, de l'Administration et des Finances"),
                             ("cantines", "Chef du Service de Gestion des Cantines Scolaires"),
                             ("statistiques", "Chef du Service des Statistiques"))])
            for c in J.cs_liste():
                inserer_up(rnd, c["id"], an)
            print(f"DDEMP du Plateau : {q('SELECT COUNT(*) n FROM jur_cs', un=True)['n']} CS, "
                  f"{q('SELECT COUNT(*) n FROM jur_ecoles', un=True)['n']} écoles importées, "
                  f"{q('SELECT COUNT(*) n FROM jur_up', un=True)['n']} UP.")
        inserer_examen_blanc(rnd, an)
        inserer_lignes_action(rnd, an)
        inserer_synoptique(niveau, an)
        print("Comptes : responsable / cp1 / cp2 / chef (DOSP) / rh (RH) / agent (mot de passe demo1234) ; admin / admin123.")


if __name__ == "__main__":
    main()
