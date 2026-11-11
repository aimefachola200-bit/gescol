# -*- coding: utf-8 -*-
"""Conversion du paquet d'école de « Mon école » (CS Pobè) en paquet de transmission (format jur_format).

Mon école joint à ses paquets de synchronisation un « POBE-PAQUET-ECOLE » (Ameliorations.paquetEcole()) :

    {"format": "POBE-PAQUET-ECOLE", "version": 2, "cree", "annee", "ecole": {fiche de l'école du poste},
     "collections": {nom: [enregistrements de l'école]}, "reglages": {...}}

Le concentrateur de la CS (SCOLARIS / GESCOL, édition cs) le convertit ici, rubrique par rubrique, vers le format
jur_format (rubriques « effectifs », « personnel », « visites », « cep ») ; les compléments des fiches officielles sont
conservés tels quels dans la rubrique libre « fiches_mon_ecole ». Tout ce qui n'a pas d'équivalent est listé dans le
compte rendu d'import (collections et champs non repris) : rien n'est perdu en silence.
Aucune modification n'est demandée côté Mon école.
"""
import jur_format

FORMAT_POBE = "POBE-PAQUET-ECOLE"
COURS = ("ci", "cp", "ce1", "ce2", "cm1", "cm2")
SECTIONS_MAT = (("sp", "Maternelle 1"), ("sg", "Maternelle 2"))
SECTION_FICHES = "fiches_mon_ecole"

# champs repris par rubrique (le reste est signalé « non repris »)
_TECH = {"id", "ecoleId", "_maj", "_cree", "_uuid", "_v", "_supprime", "_origine", "photo"}
_EFF = {"annee", "source", "handicapes", "redoublants", "sansActe", "totalG", "totalF", "total"} | \
       {f"c_{c}_{s}" for c in COURS for s in "GF"} | {f"s_eff_{c}_{s}" for c, _ in SECTIONS_MAT for s in "GF"}
_PERS = {"nom", "sexe", "matricule", "dateNaissance", "telephone", "fonction", "categorie", "statut", "grade", "indice",
         "indicePaye", "datePriseServiceFP", "datePriseServiceDept", "datePriseServiceEcole", "diplomeAca", "diplomePro",
         "cours"}
_VIS = {"date", "type", "enseignantNom", "enseignantId", "cours", "matiere", "discipline", "sequence", "note", "presents"}
_CEP = {"nom", "prenoms", "sexe", "dateNaiss", "lieuNaiss", "numTable", "session", "apprenantId", "admis", "resultat"}
_INFRA = {"typeLocal"}
_ECOLE = {"code", "nom", "type", "zone_ped", "annee_creation", "classes_autorisees", "classes_existantes",
          "organisation_classes", "telephone", "commune", "arrondissement", "localite", "directeur", "directeurTel"}
COLLECTIONS_REPRISES = {"effectifs": _EFF, "personnel": _PERS, "visites": _VIS, "cep": _CEP, "infrastructures": _INFRA,
                        "fiches": None}


def _int(v):
    try:
        return int(float(str(v).replace(",", ".").strip() or 0))
    except (TypeError, ValueError):
        return 0


def _float(v):
    try:
        s = str(v).replace(",", ".").strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def _sexe(v):
    v = str(v or "").strip().upper()[:1]
    return "M" if v in ("M", "G") else "F" if v == "F" else ""


def est_paquet_pobe(p):
    return isinstance(p, dict) and p.get("format") == FORMAT_POBE


def _identite(ec, code, nom, departement, cs):
    t = str(ec.get("type") or "").upper()
    return {
        "code": code, "nom": nom,
        "type": "EM" if t.startswith("EM") or "MATERN" in t else "EP",
        "secteur": "prive" if "PRIV" in t or t in ("EPPR",) else "public",
        "departement": departement, "cs": cs, "zone": str(ec.get("zone_ped") or ec.get("zone") or ""),
        "commune": str(ec.get("commune") or ""), "arrondissement": str(ec.get("arrondissement") or ""),
        "localite": str(ec.get("localite") or ""), "adresse": "", "telephone": str(ec.get("telephone") or ""),
        "email": "", "directeur_titre": "", "directeur_nom": str(ec.get("directeur") or ""),
        "directeur_tel": str(ec.get("directeurTel") or ""), "annee_creation": str(ec.get("annee_creation") or ""),
    }


def _effectifs(recs, annee, infra):
    if not recs:
        return None, None
    du = [r for r in recs if str(r.get("annee") or "") == annee]
    r = (du or sorted(recs, key=lambda x: str(x.get("annee") or "")))[-1]
    classes = []
    for c in COURS:
        g, f = _int(r.get(f"c_{c}_G")), _int(r.get(f"c_{c}_F"))
        if g or f:
            classes.append({"nom": c.upper(), "niveau": c.upper(), "garcons": g, "filles": f, "redoublants_g": 0,
                            "redoublants_f": 0, "titulaire_nom": "", "titulaire_sexe": "", "groupe": "simple"})
    for c, niv in SECTIONS_MAT:
        g, f = _int(r.get(f"s_eff_{c}_G")), _int(r.get(f"s_eff_{c}_F"))
        if g or f:
            classes.append({"nom": niv, "niveau": niv, "garcons": g, "filles": f, "redoublants_g": 0, "redoublants_f": 0,
                            "titulaire_nom": "", "titulaire_sexe": "", "groupe": "simple"})
    tg, tf = _int(r.get("totalG")), _int(r.get("totalF"))
    if not classes and (tg or tf):     # relevé sans détail par cours : un seul groupe « Total »
        classes.append({"nom": "Total (sans détail par cours)", "niveau": "", "garcons": tg, "filles": tf,
                        "redoublants_g": 0, "redoublants_f": 0, "titulaire_nom": "", "titulaire_sexe": "", "groupe": "simple"})
    d = {"classes": classes, "source": "Mon école (CS Pobè)", "annee_releve": str(r.get("annee") or annee),
         "handicapes_total": _int(r.get("handicapes")), "redoublants_total": _int(r.get("redoublants")),
         "sans_acte": _int(r.get("sansActe"))}
    salles = sum(1 for i in infra or [] if str(i.get("typeLocal") or "").lower().startswith("salle de classe"))
    if salles:
        d["salles"] = salles
    return d, r


ROLES = {"directeur": "directeur", "adjoint": "adjoint", "instituteur": "enseignant", "éducateur": "enseignant",
         "educateur": "enseignant", "personnel de soutien": "soutien"}
CATS = {"FE": "FE", "ACDPE": "ACDPE", "ACDPCTD": "ACDPCTD", "AME": "ACDPCTD", "PRIVE": "PRIVE"}


def _personne(p):
    fonction = str(p.get("fonction") or "")
    cat = str(p.get("categorie") or "Enseignant")
    role = ROLES.get(fonction.lower()) or {"Administratif": "administratif", "Soutien": "soutien"}.get(cat, "enseignant")
    dpro = str(p.get("diplomePro") or "").upper()
    notes = sorted((k[4:], p[k]) for k in p if k.startswith("note") and k[4:].isdigit() and str(p[k]).strip())
    return {"nom": str(p.get("nom") or ""), "prenoms": "", "sexe": _sexe(p.get("sexe")), "nip": "",
            "matricule": str(p.get("matricule") or ""), "date_naissance": str(p.get("dateNaissance") or ""),
            "telephone": str(p.get("telephone") or ""), "email": "", "fonction": fonction or cat, "role": role,
            "categorie": CATS.get(str(p.get("statut") or "").upper(), "AUTRE"), "grade": str(p.get("grade") or ""),
            "indice_paye": str(p.get("indicePaye") or ""), "indice_reel": str(p.get("indice") or ""),
            "date_premiere_ps": str(p.get("datePriseServiceFP") or ""),
            "date_ps_departement": str(p.get("datePriseServiceDept") or ""), "date_ps_commune": "",
            "date_ps_ecole": str(p.get("datePriseServiceEcole") or ""),
            "diplome_academique": str(p.get("diplomeAca") or ""), "annee_diplome": "",
            "ceap": "CEAP" in dpro, "annee_ceap": "", "cap": "CAP" in dpro.replace("CEAP", ""), "annee_cap": "",
            "type_cap": "", "visite_aptitude": False, "note_aptitude": "", "annee_aptitude": "",
            "departement_a_servir": "", "nb_visites_cp": "", "nb_visites_ccs": "", "participation_up": "",
            "gestion_collegiale": "", "note_evaluation": notes[-1][1] if notes else "", "classe": str(p.get("cours") or ""),
            "actif": True, "statut_mon_ecole": str(p.get("statut") or ""), "categorie_mon_ecole": cat}


def _visite(v):
    return {"date": str(v.get("date") or ""), "type": "CCS" if v.get("type") == "INSPECTION_ECOLE" else "CP",
            "visiteur": "", "enseignant": str(v.get("enseignantNom") or ""), "enseignant_nip": "",
            "classe": str(v.get("cours") or ""), "discipline": str(v.get("matiere") or v.get("discipline") or ""),
            "sequence": str(v.get("sequence") or ""), "note": _float(v.get("note")),
            "effectif_g": "", "effectif_f": "", "recommandations": "", "presents": _int(v.get("presents"))}


def _cep(recs, annee):
    liste, g, f, session = [], 0, 0, ""
    for c in recs:
        sx = _sexe(c.get("sexe"))
        g += sx == "M"
        f += sx == "F"
        session = session or str(c.get("session") or "")
        adm = c.get("admis")
        liste.append({"nom": str(c.get("nom") or ""), "prenoms": str(c.get("prenoms") or ""), "sexe": sx,
                      "date_naissance": str(c.get("dateNaiss") or ""), "lieu_naissance": str(c.get("lieuNaiss") or ""),
                      "numero_table": str(c.get("numTable") or ""), "admis": adm if isinstance(adm, bool) else None})
    if not session and annee[-4:].isdigit():
        session = annee[-4:]
    return {"session": session,
            "candidats_g": g, "candidats_f": f, "admis_g": None, "admis_f": None, "cm1_g": "", "cm1_f": "",
            "cm2_g": "", "cm2_f": "", "liste": liste}


def _non_repris(recs, pris):
    vus = set()
    for r in recs:
        vus |= {k for k in r if k not in _TECH and not k.startswith(("age_", "agem_", "ages", "note", "doc_", "rent_",
                                                                       "fin_", "s_age"))}
    return sorted(vus - pris)


def convertir(pp, code, nom, departement="", cs=""):
    """POBE-PAQUET-ECOLE → (paquet jur_format scellé, sections libres {nom: données}, compte rendu).

    Le compte rendu : {"reprises": {rubrique: description}, "non_reprises": {collection: nombre},
                       "champs_non_repris": {collection: [champs]}}."""
    if not est_paquet_pobe(pp):
        raise jur_format.PaquetInvalide("Ce fichier n'est pas un paquet d'école Mon école.")
    ec = pp.get("ecole") or {}
    cols = pp.get("collections") or {}
    annee = str(pp.get("annee") or "").strip()
    if not annee:
        raise jur_format.PaquetInvalide("Paquet Mon école sans année scolaire.")
    code = code or str(ec.get("code") or "").strip()
    nom = nom or str(ec.get("nom") or "").strip()
    paquet = jur_format.nouveau("ecole", code, nom, annee, departement, cs, edition="mon-ecole",
                                logiciel=f"Mon école (CS Pobè) — paquet v{pp.get('version', '')}")
    paquet["genere_le"] = str(pp.get("cree") or "")
    secs, rep, champs = {}, {}, {}
    liste = lambda n: [r for r in (cols.get(n) or []) if isinstance(r, dict)]   # noqa: E731

    eff, r_eff = _effectifs(liste("effectifs"), annee, liste("infrastructures"))
    if eff:
        secs["effectifs"] = eff
        rep["effectifs"] = (f"{sum(c['garcons'] + c['filles'] for c in eff['classes'])} élève(s), "
                            f"{len(eff['classes'])} cours (relevé {eff['annee_releve']})")
        champs["effectifs"] = _non_repris([r_eff], _EFF)
    pers = [_personne(p) for p in liste("personnel")]
    if pers:
        secs["personnel"] = pers
        rep["personnel"] = f"{len(pers)} agent(s)"
        champs["personnel"] = _non_repris(liste("personnel"), _PERS)
    vis = [_visite(v) for v in liste("visites")]
    if vis:
        secs["visites"] = vis
        rep["visites"] = f"{len(vis)} visite(s)"
        champs["visites"] = _non_repris(liste("visites"), _VIS)
    if liste("cep"):
        secs["cep"] = _cep(liste("cep"), annee)
        rep["cep"] = f"{len(secs['cep']['liste'])} candidat(s)"
        champs["cep"] = _non_repris(liste("cep"), _CEP)
    if liste("infrastructures"):
        rep["infrastructures"] = f"{eff.get('salles', 0) if eff else 0} salle(s) de classe comptée(s)"
        if not eff:
            secs["effectifs"] = {"classes": [], "salles": sum(1 for i in liste("infrastructures")
                                                             if str(i.get("typeLocal") or "").lower().startswith("salle de classe"))}
        champs["infrastructures"] = _non_repris(liste("infrastructures"), _INFRA)
    libres = {}
    fiches = [f for f in liste("fiches") if str(f.get("annee") or annee) == annee] or liste("fiches")
    if fiches:
        valeurs = {}
        for f in fiches:
            valeurs.update({k: v for k, v in f.items() if k not in _TECH and k != "annee" and v not in ("", None)})
        libres[SECTION_FICHES] = {"source": "Mon école (CS Pobè)", "annee": annee, "recu_le": paquet["genere_le"],
                                  "valeurs": valeurs}
        rep["fiches"] = f"{len(valeurs)} complément(s) de fiche conservé(s) tels quels"
    champs = {k: v for k, v in champs.items() if v}
    ecole_hors = sorted(k for k in ec if k not in _ECOLE and k not in _TECH and ec.get(k) not in ("", None, [], {}))
    if ecole_hors:
        champs["ecole"] = ecole_hors
    for k in ("classes_autorisees", "classes_existantes", "organisation_classes", "unite_ped"):
        if ec.get(k) not in (None, ""):
            libres.setdefault(SECTION_FICHES, {"source": "Mon école (CS Pobè)", "annee": annee,
                                               "recu_le": paquet["genere_le"], "valeurs": {}})
            libres[SECTION_FICHES].setdefault("ecole", {})[k] = ec[k]
    non = {n: len(v) for n, v in cols.items() if n not in COLLECTIONS_REPRISES and isinstance(v, list) and v}
    paquet["ecoles"] = [{"ecole": _identite(ec, code, nom, departement, cs), "sections": secs}]
    return jur_format.sceller(paquet), libres, {"reprises": rep, "non_reprises": non, "champs_non_repris": champs}


def resume(cr, limite=400):
    """Compte rendu court (message de synchronisation, journal)."""
    morceaux = []
    if cr["reprises"]:
        morceaux.append("repris : " + " ; ".join(f"{k} ({v})" for k, v in cr["reprises"].items()))
    if cr["non_reprises"]:
        morceaux.append("sans équivalent dans l'application : " + ", ".join(f"{k} ({n})" for k, n in sorted(cr["non_reprises"].items())))
    if cr["champs_non_repris"]:
        morceaux.append("champs non repris : " + " ; ".join(f"{k} : {', '.join(v)}" for k, v in sorted(cr["champs_non_repris"].items())))
    s = ". ".join(morceaux) or "aucune donnée exploitable"
    return s if len(s) <= limite else s[:limite - 1] + "…"
