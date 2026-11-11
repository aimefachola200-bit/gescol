# -*- coding: utf-8 -*-
"""v1.25 — Tableau de bord du pilotage (toutes éditions) : indicateurs de l'école, de la zone, de la CS ou du département.

Mêmes règles de calcul partout (jur_calc / a_tableau.agreger) :
* effectifs G / F / T, part des filles, indice de parité, classes, élèves par classe, classes pléthoriques ;
* enseignants (H / F), ratio élèves / maître, besoins (manque / surplus) ;
* réussite aux évaluations (par type et numéro : composés, réussis, taux G / F / T) ;
* CEP : candidats, admis, taux G / F / T ;
* redoublements, abandons (élèves sortis), transferts ;
* infrastructures (salles de classe, places assises, déficit, tables-bancs manquantes, latrines, eau, électricité) ;
* sport scolaire (licences G / F, aptes, compétitions, matchs joués).

Éditions école : calcul sur les données de l'école (paquet de transmission) ; une photo de l'année (« instantané ») est
gardée pour comparer les années. Éditions CS / DDEMP : écoles de la juridiction (sections transmises), regroupées par
zone pédagogique, circonscription ou école ; comparaison avec une autre année.
La section « pilotage » (évaluations, abandons, sport…) est ajoutée au paquet de transmission école → CS → DDEMP.

Routes : /pilotage · /pilotage.pdf (signé, QR) · /pilotage.xlsx · POST /pilotage/instantane · POST /pilotage/instantane/supprimer
"""
import json
import re
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

import jur_calc as C
import registres as R

SCHEMA = """
CREATE TABLE IF NOT EXISTS pilotage_instantanes (
    id INTEGER PRIMARY KEY, portee INTEGER NOT NULL, annee TEXT NOT NULL, contenu TEXT NOT NULL, maj TEXT, UNIQUE(portee, annee)
);
"""
TYPES_EVAL = {"diagnostique": "Diagnostique", "formative": "Formative", "sommative": "Sommative", "certificative": "Certificative"}


def taux(a, b):
    return round(100.0 * a / b, 1) if b else None


def vide_pilotage():
    return {"evaluations": [], "abandons": [0, 0], "transferts": [0, 0], "sport": {"licences_g": 0, "licences_f": 0, "aptes": 0,
                                                                                    "competitions": 0, "matchs": 0, "matchs_joues": 0},
            "sante": {}}


def cumuler_pilotage(secs):
    """Somme de sections « pilotage » (plusieurs écoles)."""
    out = vide_pilotage()
    ev = {}
    for s in secs:
        if not s:
            continue
        for e in s.get("evaluations") or []:
            k = (e.get("type") or "", int(e.get("numero") or 1))
            d = ev.setdefault(k, {"type": k[0], "numero": k[1], "libelle": e.get("libelle") or "", "composes_g": 0, "composes_f": 0,
                                  "reussis_g": 0, "reussis_f": 0, "classes": 0})
            for c in ("composes_g", "composes_f", "reussis_g", "reussis_f", "classes"):
                d[c] += int(e.get(c) or 0)
        for k in ("abandons", "transferts"):
            v = s.get(k) or [0, 0]
            out[k] = [out[k][0] + int(v[0] or 0), out[k][1] + int(v[1] or 0)]
        for k, v in (s.get("sport") or {}).items():
            out["sport"][k] = out["sport"].get(k, 0) + int(v or 0)
        for k, v in (s.get("sante") or {}).items():
            if isinstance(v, (int, float)):
                out["sante"][k] = out["sante"].get(k, 0) + v
    ordre = list(TYPES_EVAL)
    out["evaluations"] = sorted(ev.values(), key=lambda d: (ordre.index(d["type"]) if d["type"] in ordre else 9, d["numero"]))
    for d in out["evaluations"]:
        d["composes"] = d["composes_g"] + d["composes_f"]
        d["reussis"] = d["reussis_g"] + d["reussis_f"]
        d["taux"], d["taux_g"], d["taux_f"] = taux(d["reussis"], d["composes"]), taux(d["reussis_g"], d["composes_g"]), taux(d["reussis_f"], d["composes_f"])
    return out


def infra(pat):
    """Indicateurs d'infrastructures à partir de la section « patrimoine » (H.patrimoine_synthese)."""
    pat = pat or {}

    def _d(v, cle):
        """v2.3.4 : une section reçue sous forme de nombre (ex. « salles_classe »: 6, données transmises ou d'exemple)
        compte comme son total au lieu de faire échouer le tableau de bord."""
        if isinstance(v, dict):
            return v
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return {cle: v}
        if isinstance(v, str) and v.strip().isdigit():
            return {cle: int(v)}
        return {}
    sc = _d(pat.get("salles_classe"), "total")
    mob = _d(pat.get("mobilier"), "places_assises")
    lat = _d(pat.get("latrines"), "cabines_total")
    eq = pat.get("equipements") if isinstance(pat.get("equipements"), dict) else {}
    return {"salles": int(sc.get("total") or 0), "salles_mauvais": int(sc.get("mauvais") or 0), "places": int(mob.get("places_assises") or 0),
            "deficit_places": int(mob.get("deficit_places") or 0), "tb_manquantes": int(mob.get("tables_bancs_manquantes") or 0),
            "cabines": int(lat.get("cabines_total") or 0), "eau": 1 if eq.get("point_eau") else 0, "electricite": 1 if eq.get("electricite") else 0,
            "ecoles": 1 if pat else 0}


def cumuler_infra(lst):
    out = {"salles": 0, "salles_mauvais": 0, "places": 0, "deficit_places": 0, "tb_manquantes": 0, "cabines": 0, "eau": 0, "electricite": 0, "ecoles": 0,
           "tables_bancs": 0}
    for x in lst:
        for k in out:
            out[k] += x.get(k) or 0
    return out


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config
    H.schema(SCHEMA)
    H.DROITS["pilotage"] = {"admin", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent"}
    import a_tableau as T
    R._H = R._H or H
    R.types_documents({"pilotage": "Tableau de bord du pilotage (indicateurs)"})

    # ------------------------------------------------------------------ saisie des indicateurs (registre, spécification commune)
    G = R.Groupe(app, H, "pilotage", "Tableau de bord du pilotage", "pilotage", ico="pilotage",
                 ecriture_roles={"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp"},
                 sous_titre="Indicateurs de l'école, de la zone, de la circonscription et du département",
                 onglets_avant=[("pilotage", "Tableau de bord", {})])
    N = "entier"
    G.registre("indicateurs", "Saisie des indicateurs", [
        ("ecole", "École", "ecole"), ("eff_g", "Effectif garçons", N), ("eff_f", "Effectif filles", N), ("groupes", "Groupes pédagogiques", N),
        ("salles", "Salles de classe utilisables", N), ("enseignants", "Enseignants (total)", N), ("enseignants_f", "Enseignantes", N),
        ("ens_fe", "Enseignants fonctionnaires (APE / FE)", N), ("ens_contractuels", "Enseignants contractuels (ACE / ACDPE)", N),
        ("ens_communautaires", "Enseignants communautaires / volontaires", N), ("ens_autres", "Autres enseignants", N),
        ("tables_bancs", "Tables-bancs en bon état", N), ("latrines", "Cabines de latrines", N), ("point_eau", "Point d’eau", "oui_non"),
        ("cantine", "Cantine scolaire", "oui_non"), ("reussite_t1", "Taux de réussite 1er trimestre (%)", "decimal"),
        ("reussite_t2", "Taux de réussite 2e trimestre (%)", "decimal"), ("reussite_t3", "Taux de réussite 3e trimestre (%)", "decimal"),
        ("cep_inscrits_g", "CEP inscrits G", N), ("cep_inscrits_f", "CEP inscrits F", N), ("cep_presents_g", "CEP présents G", N),
        ("cep_presents_f", "CEP présents F", N), ("cep_admis_g", "CEP admis G", N), ("cep_admis_f", "CEP admis F", N),
        ("abandons_g", "Abandons G", N), ("abandons_f", "Abandons F", N), ("redoublants_g", "Redoublants G", N), ("redoublants_f", "Redoublants F", N),
        ("observations", "Observations", "long")],
        defauts=lambda: {} if R.juridiction() else {"ecole": config.ECOLE.get("nom") or ""},
        unite="ligne d'indicateurs", oblig="ecole", ordre="ecole", portee="structure", feuille="Saisie des indicateurs",
        doc="Saisie des indicateurs des écoles", prefixe=lambda x: ("ECOLE", x.get("ecole") or config.ECOLE.get("nom") or ""),
        colonnes=("ecole", "eff_g", "eff_f", "groupes", "salles", "enseignants", "enseignants_f", "tables_bancs", "reussite_t1", "reussite_t2",
                  "reussite_t3", "cep_admis_g", "cep_admis_f", "abandons_g", "abandons_f"),
        calcul=lambda x: {"Effectif total": (x.get("eff_g") or 0) + (x.get("eff_f") or 0)},
        aide="Une ligne par école et par année scolaire : les valeurs saisies complètent ou remplacent, rubrique par rubrique, celles que "
             "l'application calcule (effectifs, personnel, CEP, infrastructures).")

    # ------------------------------------------------------------------ section « pilotage » de l'école (transmise à la CS)
    def section_pilotage(annee=None):
        annee = annee or config.ANNEE_ACTIVE
        import evaluations_core as EC
        out = vide_pilotage()
        e_ = H.eco()
        try:
            classes = [dict(c) for c in q("SELECT * FROM classes WHERE ecole_id=? ORDER BY niveau, nom", (e_,))]
        except Exception:  # noqa: BLE001
            classes = []
        from calcul import cycle_du_niveau
        for c in classes:
            c["cycle"] = cycle_du_niveau(c["niveau"])
            if c["cycle"] not in ("primaire", "maternelle"):
                continue
            try:
                evs = EC.evaluations_classe(c["id"], annee)
            except Exception:  # noqa: BLE001
                evs = []
            for ev in evs:
                try:
                    mat, lignes = EC.resultats(ev, c)
                    s = EC.statistiques(mat, lignes)
                except Exception:  # noqa: BLE001
                    continue
                if not s["composes"]["T"]:
                    continue
                out["evaluations"].append({"type": ev["type"], "numero": ev["numero"], "libelle": ev["libelle"], "niveau": c["niveau"], "classes": 1,
                                           "composes_g": s["composes"]["G"], "composes_f": s["composes"]["F"],
                                           "reussis_g": s["reussis"]["G"], "reussis_f": s["reussis"]["F"]})
        try:
            for st, k in (("sorti", "abandons"), ("transfere", "transferts")):
                r = q("SELECT SUM(e.sexe<>'F') g, SUM(e.sexe='F') f FROM eleves e JOIN classes c ON c.id=e.classe_id AND c.ecole_id=? WHERE e.statut=?",
                      (e_, st), un=True)
                out[k] = [r["g"] or 0, r["f"] or 0]
        except Exception:  # noqa: BLE001
            pass
        try:
            p = R.cle_portee("structure")
            r = q("SELECT SUM(sexe='M') g, SUM(sexe='F') f, SUM(aptitude IN ('Apte', 'Apte avec réserve')) aptes FROM reg_sport_licences WHERE portee=? AND annee=?",
                  (p, annee), un=True)
            out["sport"].update(licences_g=r["g"] or 0, licences_f=r["f"] or 0, aptes=r["aptes"] or 0)
            r = q("SELECT COUNT(*) n FROM sport_competitions WHERE portee=? AND saison=?", (p, annee), un=True)
            out["sport"]["competitions"] = r["n"] or 0
            r = q("SELECT COUNT(*) n, SUM(score_a IS NOT NULL OR COALESCE(forfait,'')<>'') j FROM sport_matchs WHERE competition_id IN "
                  "(SELECT id FROM sport_competitions WHERE portee=? AND saison=?)", (p, annee), un=True)
            out["sport"].update(matchs=r["n"] or 0, matchs_joues=r["j"] or 0)
        except Exception:  # noqa: BLE001
            pass
        f = getattr(H, "sante_synthese", None)
        if callable(f):
            try:
                out["sante"] = f(annee) or {}
            except Exception:  # noqa: BLE001
                out["sante"] = {}
        return out

    if not hasattr(H, "sections_extra"):
        H.sections_extra = {}
    H.sections_extra["pilotage"] = lambda annee=None: (section_pilotage(annee), None)
    H.pilotage_section = section_pilotage

    # ------------------------------------------------------------------ indicateurs
    def indicateurs(lignes, pils, pats):
        """lignes : lignes « école » (format a_tableau.donnees) ; pils : sections pilotage ; pats : sections patrimoine."""
        a = T.agreger(lignes)
        p = cumuler_pilotage(pils)
        i = cumuler_infra([x if (x and "salles" in x) else infra(x) for x in pats if x])
        eff = a["t"] or 0
        a.update(pil=p, infra=i, abandons=sum(p["abandons"]), transferts=sum(p["transferts"]),
                 taux_abandon=taux(sum(p["abandons"]), eff + sum(p["abandons"])),
                 eleves_salle=round(eff / i["salles"], 1) if i["salles"] else None,
                 licences=p["sport"].get("licences_g", 0) + p["sport"].get("licences_f", 0))
        somm = [e for e in p["evaluations"] if e["type"] in ("sommative", "certificative")]
        a["eval_derniere"] = somm[-1] if somm else (p["evaluations"][-1] if p["evaluations"] else None)
        for k in ("reussite_t1", "reussite_t2", "reussite_t3"):   # moyenne des écoles renseignées (saisie des indicateurs)
            v = [x.get(k) for x in pils if x and x.get(k) is not None]
            a[k] = round(sum(v) / len(v), 1) if v else None
        a["cantine"] = sum(1 for x in pils if x and x.get("cantine"))
        a["tables_bancs"] = i.get("tables_bancs", 0)
        return a

    # ---- saisie des indicateurs (spécification commune) : la ligne saisie prime champ par champ
    def saisies(annee):
        try:
            rows = q("SELECT * FROM reg_pilotage_indicateurs WHERE portee=? AND annee=? ORDER BY id", (R.cle_portee("structure"), annee))
        except Exception:  # noqa: BLE001
            return {}
        out = {}
        for r in rows:
            out[R._norm(r["ecole"] or config.ECOLE.get("nom") or "")] = dict(r)
        return out

    def appliquer(l, pil, pat, sx):
        """Applique une ligne « Saisie des indicateurs » à une ligne d'école (copies)."""
        import copy
        l = copy.deepcopy(l)
        pil = copy.deepcopy(pil) if pil else vide_pilotage()
        inf = infra(pat) if not (pat and "salles" in pat) else dict(pat)
        if not sx:
            return l, pil, inf
        def v(k):
            return sx.get(k)
        e = l["eff"]
        if v("eff_g") is not None or v("eff_f") is not None:
            e["g"] = v("eff_g") if v("eff_g") is not None else e["g"]
            e["f"] = v("eff_f") if v("eff_f") is not None else e["f"]
            e["t"] = e["g"] + e["f"]
            l["a_effectifs"] = True
        if v("groupes") is not None:
            e["classes"] = v("groupes")
            if e["classes"]:
                e["tailles"] = [round(e["t"] / e["classes"])] * e["classes"]
        if v("redoublants_g") is not None or v("redoublants_f") is not None:
            e["redoublants"] = (v("redoublants_g") or 0) + (v("redoublants_f") or 0)
        if v("enseignants") is not None:
            l["ens"]["t"] = v("enseignants")
            l["ens"]["f"] = v("enseignants_f") if v("enseignants_f") is not None else l["ens"]["f"]
            l["ens"]["h"] = max(0, l["ens"]["t"] - l["ens"]["f"])
            l["besoin"] = dict(l["besoin"], enseignants=v("enseignants"))
            cats = {"FE": v("ens_fe") or 0, "ACDPE": v("ens_contractuels") or 0, "AUTRE": (v("ens_communautaires") or 0) + (v("ens_autres") or 0)}
            if any(cats.values()):
                l["ens"]["par_categorie"] = cats
        for k, kk in (("salles", "salles"), ("tables_bancs", "tables_bancs"), ("latrines", "cabines")):
            if v(k) is not None:
                inf[kk] = v(k)
        if v("tables_bancs") is not None:
            inf["places"] = 2 * v("tables_bancs")
        if v("point_eau"):
            inf["eau"] = 1 if v("point_eau") == "Oui" else 0
        if v("cantine"):
            pil["cantine"] = v("cantine") == "Oui"
        inf["ecoles"] = 1
        if any(v(k) is not None for k in ("cep_inscrits_g", "cep_inscrits_f", "cep_presents_g", "cep_presents_f", "cep_admis_g", "cep_admis_f")):
            cg = v("cep_presents_g") if v("cep_presents_g") is not None else (v("cep_inscrits_g") or 0)
            cf = v("cep_presents_f") if v("cep_presents_f") is not None else (v("cep_inscrits_f") or 0)
            ag, af = v("cep_admis_g"), v("cep_admis_f")
            l["cep"] = {"candidats_g": cg, "candidats_f": cf, "candidats": cg + cf, "admis_g": ag, "admis_f": af,
                        "admis": (ag or 0) + (af or 0) if (ag is not None or af is not None) else None}
        if v("abandons_g") is not None or v("abandons_f") is not None:
            pil["abandons"] = [v("abandons_g") or 0, v("abandons_f") or 0]
        for k in ("reussite_t1", "reussite_t2", "reussite_t3"):
            if v(k) is not None:
                pil[k] = v(k)
        l["ratio"] = round(e["t"] / l["besoin"]["enseignants"], 1) if l["besoin"].get("enseignants") else None
        return l, pil, inf

    def ligne_ecole_locale(annee):
        """Ligne au format a_tableau.donnees pour l'école courante (paquet de transmission) + sections pilotage / patrimoine."""
        try:
            paquet = H.transmission_paquet(annee)
            item = (paquet.get("ecoles") or [{}])[0]
        except Exception:  # noqa: BLE001
            item = {}
        secs = item.get("sections") or {}
        ident = item.get("ecole") or {}
        sec = secs.get("effectifs")
        pers = secs.get("personnel")
        eff = C.effectifs(sec)
        ens = C.enseignants(pers)
        bes = C.besoin_enseignants(sec, pers)
        cep = C.cep(secs["cep"]) if secs.get("cep") else None
        typ = ident.get("type") or "EP"
        seuil = T.SEUIL_PLETHORE.get(typ, 60)
        l = {"id": H.eco(), "code": ident.get("code") or "", "nom": ident.get("nom") or config.ECOLE.get("nom") or "École", "type": typ,
             "secteur": ident.get("secteur") or ("public" if config.publique() else "prive"), "cs_id": None, "cs_nom": ident.get("cs") or "",
             "zone_id": None, "zone_nom": ident.get("zone") or "", "localite": ident.get("localite") or "", "directeur_nom": ident.get("directeur_nom") or "",
             "transmis": True, "a_effectifs": sec is not None, "a_personnel": pers is not None, "eff": eff,
             "ens": {k: ens[k] for k in ("t", "h", "f", "par_categorie")}, "besoin": bes, "cep": cep, "moy_classe": C.moyenne(eff["tailles"]),
             "ratio": round(eff["t"] / bes["enseignants"], 1) if bes["enseignants"] else None,
             "plethoriques": sum(1 for t in eff["tailles"] if t > seuil), "seuil": seuil, "_sec_eff": sec or {}}
        pil = secs.get("pilotage") or section_pilotage(annee)
        return l, pil, secs.get("patrimoine"), sec

    def par_classe_locale(sec, pil):
        """Tableau par classe (effectifs) et par niveau (réussite aux évaluations)."""
        cl = [{"nom": c.get("nom"), "niveau": c.get("niveau"), "g": c.get("garcons") or 0, "f": c.get("filles") or 0,
               "red": (c.get("redoublants_g") or 0) + (c.get("redoublants_f") or 0), "titulaire": c.get("titulaire_nom") or ""}
              for c in (sec or {}).get("classes") or []]
        niv = {}
        for e in (pil or {}).get("evaluations") or []:
            d = niv.setdefault((e["niveau"], e["type"], e["numero"]), {"niveau": e["niveau"], "libelle": e["libelle"], "c": 0, "r": 0})
            d["c"] += e["composes_g"] + e["composes_f"]
            d["r"] += e["reussis_g"] + e["reussis_f"]
        for d in niv.values():
            d["taux"] = taux(d["r"], d["c"])
        return cl, sorted(niv.values(), key=lambda d: (d["niveau"], d["libelle"]))

    def portee():
        return 0 if R.juridiction() else -H.eco()

    def instantane(annee):
        r = q("SELECT * FROM pilotage_instantanes WHERE portee=? AND annee=?", (portee(), annee), un=True)
        if not r:
            return None
        try:
            return json.loads(r["contenu"]) | {"_maj": r["maj"]}
        except (ValueError, TypeError):
            return None

    def figer(annee, ind, extra):
        contenu = json.dumps({"ind": ind, **extra}, ensure_ascii=False, default=str)
        ex("INSERT INTO pilotage_instantanes (portee, annee, contenu, maj) VALUES (?,?,?,?) ON CONFLICT(portee, annee) DO UPDATE SET "
           "contenu=excluded.contenu, maj=excluded.maj", (portee(), annee, contenu, H.maintenant()))

    def calculer(annee, par, flt):
        """{'ind': indicateurs globaux, 'groupes': [(nom, ind)], 'classes', 'niveaux', 'source'}"""
        sxs = saisies(annee)
        if not R.juridiction():
            l, pil, pat, sec = ligne_ecole_locale(annee)
            sx = next(iter(sxs.values()), None)
            l, pil, inf = appliquer(l, pil, pat, sx)
            ind = indicateurs([l], [pil], [inf])
            cl, niv = par_classe_locale(sec, pil)
            return {"ind": ind, "groupes": [], "classes": cl, "niveaux": niv, "source": "école", "nb_ecoles": 1}
        lignes = T.donnees(annee, cs_id=flt.get("cs_id"), zone_id=flt.get("zone_id"), type_=flt.get("type"), secteur=flt.get("secteur"))
        ids = [x["id"] for x in lignes]
        try:
            spil = H.jur_sections("pilotage", annee, ids)
            spat = H.jur_sections("patrimoine", annee, ids)
        except Exception:  # noqa: BLE001
            spil, spat = {}, {}
        triplets = {}
        for x in lignes:
            l2, p2, i2 = appliquer(x, spil.get(x["id"]), spat.get(x["id"]), sxs.get(R._norm(x["nom"])))
            triplets[x["id"]] = (l2, p2, i2)
        gr = []
        if par == "ecole":
            for x in lignes:
                l2, p2, i2 = triplets[x["id"]]
                gr.append((x["nom"], indicateurs([l2], [p2], [i2])))
        else:
            for _k, nom, ll in T.groupes(lignes, "cs" if par == "cs" else "zone"):
                tt = [triplets[x["id"]] for x in ll]
                gr.append((nom, indicateurs([t[0] for t in tt], [t[1] for t in tt], [t[2] for t in tt])))
        tt = [triplets[i] for i in ids]
        return {"ind": indicateurs([t[0] for t in tt], [t[1] for t in tt], [t[2] for t in tt]), "groupes": gr, "classes": [], "niveaux": [],
                "source": "juridiction", "nb_ecoles": len(lignes)}

    H.pilotage_calculer = calculer          # v2.3 : niveau national et /api/stats.json (m_territoire)

    def filtres():
        f = {}
        for k in ("cs_id", "zone_id"):
            v = request.args.get(k, type=int)
            if v:
                f[k] = v
        for k in ("type", "secteur"):
            if request.args.get(k):
                f[k] = request.args[k]
        return f

    def annee_de(nom, defaut):
        v = (request.args.get(nom) or "").strip()
        return v if re.fullmatch(r"\d{4}-\d{4}", v) else defaut

    def precedente(annee):
        a = int(annee[:4])
        return f"{a - 1}-{a}"

    def lignes_kpi(ind, comp):
        """[(libellé, valeur, valeur comparée, unité, sens)] ; sens : +1 = hausse souhaitée, -1 = baisse souhaitée, 0 neutre."""
        ci = (comp or {}).get("ind") if comp else None

        def v(d, *ks):
            for k in ks:
                if d is None:
                    return None
                d = d.get(k) if isinstance(d, dict) else None
            return d
        out = [("Écoles", "ecoles", 0, ""), ("Élèves (total)", "t", 0, ""), ("Garçons", "g", 0, ""), ("Filles", "f", 0, ""),
               ("Part des filles", "pct_f", 0, " %"), ("Indice de parité F/G", "ip", 0, ""), ("Classes ouvertes (une jumelée / multigrade = 1)", "classes", 0, ""),
               ("dont classes simples", "classes_simples", 0, ""), ("dont classes jumelées", "classes_jumelees", 0, ""),
               ("dont classes multigrades", "classes_multigrades", 0, ""),
               ("Élèves par classe (moyenne)", "moy_classe", -1, ""), ("Classes pléthoriques", "plethoriques", -1, ""),
               ("Enseignants", ("ens", "t"), 0, ""), ("dont femmes", ("ens", "f"), 0, ""), ("Ratio élèves / maître", ("ens", "ratio"), -1, ""),
               ("Enseignants manquants", ("ens", "manque"), -1, ""), ("Redoublants", "redoublants", -1, ""), ("Taux de redoublement", "taux_redoublement", -1, " %"),
               ("Abandons (élèves sortis)", "abandons", -1, ""), ("Taux d'abandon", "taux_abandon", -1, " %"), ("Transferts", "transferts", 0, ""),
               ("CEP : candidats", ("cep", "candidats"), 0, ""), ("CEP : admis", ("cep", "admis"), 1, ""), ("CEP : taux de réussite", ("cep", "taux"), 1, " %"),
               ("CEP : taux garçons", ("cep", "taux_g"), 1, " %"), ("CEP : taux filles", ("cep", "taux_f"), 1, " %"),
               ("Salles de classe", ("infra", "salles"), 1, ""), ("Élèves par salle", "eleves_salle", -1, ""), ("Places assises", ("infra", "places"), 1, ""),
               ("Déficit de places assises", ("infra", "deficit_places"), -1, ""), ("Tables-bancs manquantes", ("infra", "tb_manquantes"), -1, ""),
               ("Cabines de latrines", ("infra", "cabines"), 1, ""), ("Tables-bancs en bon état", "tables_bancs", 1, ""),
               ("Écoles avec point d'eau", ("infra", "eau"), 1, ""), ("Écoles avec cantine", "cantine", 1, ""),
               ("Réussite 1er trimestre (saisie)", "reussite_t1", 1, " %"), ("Réussite 2e trimestre (saisie)", "reussite_t2", 1, " %"),
               ("Réussite 3e trimestre (saisie)", "reussite_t3", 1, " %"), ("Licences sportives", "licences", 1, ""), ("Licences : filles", ("pil", "sport", "licences_f"), 1, ""),
               ("Compétitions sportives", ("pil", "sport", "competitions"), 1, ""), ("Matchs joués", ("pil", "sport", "matchs_joues"), 1, "")]
        res = []
        for lib, k, sens, u in out:
            ks = k if isinstance(k, tuple) else (k,)
            res.append((lib, v(ind, *ks), v(ci, *ks) if ci else None, u, sens))
        ev = ind.get("eval_derniere")
        if ev:
            evc = None
            if ci:
                evc = next((e for e in (ci.get("pil") or {}).get("evaluations") or [] if e["type"] == ev["type"] and e["numero"] == ev["numero"]), None)
            res.insert(21, (f"Réussite — {ev['libelle'] or TYPES_EVAL.get(ev['type'], ev['type'])}", ev["taux"], evc["taux"] if evc else None, " %", 1))
        return res

    def fmt(v, u=""):
        if v is None or not isinstance(v, (int, float, str)) or isinstance(v, bool):
            return "—"
        if isinstance(v, str):
            return v or "—"
        if isinstance(v, float):
            return (f"{v:.1f}".rstrip("0").rstrip(".")).replace(".", ",") + u
        return f"{v:,}".replace(",", " ") + u

    def ecart(a, b, sens):
        if a is None or b is None or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return "", ""
        d = round(a - b, 1)
        if d == 0:
            return "=", ""
        cl = "" if not sens else ("ok" if (d > 0) == (sens > 0) else "ko")
        return ("+" if d > 0 else "") + fmt(d), cl

    @app.route("/pilotage")
    @H.connexion_requise("pilotage")
    def pilotage():
        annee = annee_de("annee", config.ANNEE_ACTIVE)
        comparer = annee_de("comparer", precedente(annee)) if request.args.get("comparer") != "" else ""
        par = request.args.get("par") if request.args.get("par") in ("zone", "cs", "ecole") else ("zone" if config.EDITION == "cs" else "cs")
        flt = filtres()
        res = calculer(annee, par, flt)
        if not R.juridiction() and annee == config.ANNEE_ACTIVE:
            figer(annee, res["ind"], {"classes": res["classes"], "niveaux": res["niveaux"]})
        comp = None
        if comparer and comparer != annee:
            if R.juridiction():
                comp = calculer(comparer, par, flt)
            else:
                comp = instantane(comparer)
        kpi = lignes_kpi(res["ind"], comp)
        ind = res["ind"]
        # graphiques
        charts = {}
        if res["groupes"]:
            noms = [n for n, _i in res["groupes"]][:40]
            gi = [i for _n, i in res["groupes"]][:40]
            charts["Effectifs (garçons / filles)"] = T.svg_barres(noms, [("Garçons", T.COULEUR_G, [i["g"] for i in gi]), ("Filles", T.COULEUR_F, [i["f"] for i in gi])],
                                                                   aria="Effectifs par entité")
            charts["Ratio élèves / maître"] = T.svg_barres(noms, [("Ratio", "#1F4E79", [i["ens"]["ratio"] for i in gi])], ref=ind["ens"]["ratio"], ref_lib="Ensemble",
                                                            aria="Ratio élèves par maître")
            charts["Taux de réussite au CEP"] = T.svg_barres(noms, [("Garçons", T.COULEUR_G, [i["cep"]["taux_g"] for i in gi]), ("Filles", T.COULEUR_F, [i["cep"]["taux_f"] for i in gi])],
                                                              unite=" %", max_=100, ref=ind["cep"]["taux"], ref_lib="Ensemble", aria="Taux de réussite au CEP")
            charts["Taux de réussite (dernière évaluation sommative)"] = T.svg_barres(
                noms, [("Total", "#12B76A", [(i["eval_derniere"] or {}).get("taux") for i in gi])], unite=" %", max_=100, aria="Réussite aux évaluations")
        if res["classes"]:
            cl = res["classes"]
            charts["Effectifs par classe"] = T.svg_barres([c["nom"] for c in cl], [("Garçons", T.COULEUR_G, [c["g"] for c in cl]), ("Filles", T.COULEUR_F, [c["f"] for c in cl])],
                                                           aria="Effectifs par classe")
        evs = ind["pil"]["evaluations"]
        if evs:
            charts["Réussite par évaluation"] = T.svg_barres([e["libelle"] or f"{TYPES_EVAL.get(e['type'], e['type'])} {e['numero']}" for e in evs],
                                                             [("Garçons", T.COULEUR_G, [e["taux_g"] for e in evs]), ("Filles", T.COULEUR_F, [e["taux_f"] for e in evs])],
                                                             unite=" %", max_=100, aria="Réussite par évaluation")
        if ind["t"]:
            charts["Répartition filles / garçons"] = T.svg_repartition(ind["g"], ind["f"])
        zones, cs = [], []
        if R.juridiction():
            try:
                cs = [dict(x) for x in H.jur_cs_liste()]
                zones = [dict(x) for x in H.jur_zones()]
            except Exception:  # noqa: BLE001
                pass
        eb = None                                   # v1.28 : examen blanc (ebComposes, ebAdmis, ebTaux)
        f_eb = getattr(H, "examen_blanc_synthese", None)
        if callable(f_eb):
            try:
                d_eb = f_eb(annee)
                c_eb, a_eb = sum(v["ebComposes"] for v in d_eb.values()), sum(v["ebAdmis"] for v in d_eb.values())
                eb = {"ebComposes": c_eb, "ebAdmis": a_eb, "ebTaux": round(a_eb / c_eb * 100, 1) if c_eb else None, "ecoles": d_eb} if d_eb else None
            except Exception:  # noqa: BLE001
                eb = None
        return render_template("pilotage.html", G=G, ep_actif="pilotage", annee=annee, eb=eb, comparer=comparer, par=par, flt=flt, res=res, comp=comp, kpi=kpi, fmt=fmt, ecart=ecart,
                               charts=charts, annees=R.annees_proposees([annee, comparer]), JUR=R.juridiction(), zones=zones, cs=cs,
                               TYPES_EVAL=TYPES_EVAL, instantanes=[r["annee"] for r in q("SELECT annee FROM pilotage_instantanes WHERE portee=? ORDER BY annee DESC", (portee(),))])

    @app.route("/pilotage/instantane", methods=["POST"])
    @H.connexion_requise("pilotage")
    def pilotage_instantane():
        if g.user["role"] not in ("admin", "fondateur", "directeur", "responsable", "chef_service"):
            abort(403)
        annee = (request.form.get("annee") or config.ANNEE_ACTIVE)
        res = calculer(annee, "zone", {})
        figer(annee, res["ind"], {"classes": res["classes"], "niveaux": res["niveaux"]})
        flash(f"Instantané {annee} enregistré (pour les comparaisons entre années).", "success")
        return redirect(url_for("pilotage", annee=annee))

    @app.route("/pilotage/instantane/supprimer", methods=["POST"])
    @H.connexion_requise("pilotage")
    def pilotage_instantane_supprimer():
        if g.user["role"] not in ("admin", "fondateur", "directeur", "responsable", "chef_service"):
            abort(403)
        ex("DELETE FROM pilotage_instantanes WHERE portee=? AND annee=?", (portee(), request.form.get("annee") or ""))
        flash("Instantané supprimé.", "success")
        return redirect(url_for("pilotage"))

    def tables_export(annee, comparer, par):
        flt = filtres()
        res = calculer(annee, par, flt)
        comp = (calculer(comparer, par, flt) if R.juridiction() else instantane(comparer)) if comparer and comparer != annee else None
        kpi = lignes_kpi(res["ind"], comp)
        t1 = [[lib, fmt(v, u), fmt(c, u) if comp else "", ecart(v, c, s)[0] if comp else ""] for lib, v, c, u, s in kpi]
        grp = [[n, i["ecoles"], i["t"], i["g"], i["f"], fmt(i["pct_f"], " %"), i["classes"], fmt(i["moy_classe"]), i["ens"]["t"], fmt(i["ens"]["ratio"]),
                i["ens"]["manque"], fmt(i["cep"]["taux"], " %"), fmt(i["cep"]["taux_g"], " %"), fmt(i["cep"]["taux_f"], " %"),
                fmt((i["eval_derniere"] or {}).get("taux"), " %"), i["abandons"], i["licences"]] for n, i in res["groupes"]]
        ev = [[e["libelle"] or f"{TYPES_EVAL.get(e['type'], e['type'])} {e['numero']}", e["classes"], e["composes"], e["reussis"], fmt(e["taux"], " %"),
               fmt(e["taux_g"], " %"), fmt(e["taux_f"], " %")] for e in res["ind"]["pil"]["evaluations"]]
        cl = [[c["nom"], c["niveau"], c["g"], c["f"], c["g"] + c["f"], c["red"], c["titulaire"]] for c in res["classes"]]
        return res, comp, t1, grp, ev, cl

    ENT_GRP = ["Entité", "Écoles", "Élèves", "G", "F", "% F", "Classes", "Él./classe", "Enseignants", "Él./maître", "Manque", "CEP %", "CEP G %",
               "CEP F %", "Réussite éval. %", "Abandons", "Licences"]
    ENT_EV = ["Évaluation", "Classes", "Composés", "Réussis", "Taux", "Taux G", "Taux F"]
    ENT_CL = ["Classe", "Cours", "G", "F", "Total", "Redoublants", "Titulaire"]

    @app.route("/pilotage.xlsx")
    @H.connexion_requise("pilotage")
    def pilotage_xlsx():
        annee = annee_de("annee", config.ANNEE_ACTIVE)
        comparer = annee_de("comparer", "") if request.args.get("comparer") else ""
        par = request.args.get("par") if request.args.get("par") in ("zone", "cs", "ecole") else "zone"
        _res, _c, t1, grp, ev, cl = tables_export(annee, comparer, par)
        f = [("Indicateurs", ["Indicateur", annee, comparer or "", "Écart"], t1, {})]
        if grp:
            f.append(("Par entité", ENT_GRP, grp, {}))
        if ev:
            f.append(("Évaluations", ENT_EV, ev, {}))
        if cl:
            f.append(("Classes", ENT_CL, cl, {}))
        return H.xlsx.reponse_classeur(f"pilotage_{annee}.xlsx", f)

    @app.route("/pilotage.pdf")
    @H.connexion_requise("pilotage")
    def pilotage_pdf():
        from reportlab.platypus import Paragraph
        annee = annee_de("annee", config.ANNEE_ACTIVE)
        comparer = annee_de("comparer", "") if request.args.get("comparer") else ""
        par = request.args.get("par") if request.args.get("par") in ("zone", "cs", "ecole") else "zone"
        res, comp, t1, grp, ev, cl = tables_export(annee, comparer, par)
        st = R.styles()
        L = R.largeur_utile(True)
        corps = [R.tableau(["Indicateur", annee, comparer or "—", "Écart"], t1, [60, 22, 22, 16], L * 0.75)]
        if grp:
            corps += [Paragraph(f"<b>Par {'école' if par == 'ecole' else 'circonscription' if par == 'cs' else 'zone pédagogique'}</b>", st["h2"]),
                      R.tableau(ENT_GRP, grp, [30] + [8] * (len(ENT_GRP) - 1), L, taille=6.8)]
        if ev:
            corps += [Paragraph("<b>Réussite aux évaluations</b>", st["h2"]), R.tableau(ENT_EV, ev, [40, 10, 12, 12, 10, 10, 10], L * 0.8)]
        if cl:
            corps += [Paragraph("<b>Effectifs par classe</b>", st["h2"]), R.tableau(ENT_CL, cl, [20, 10, 8, 8, 8, 12, 30], L * 0.8)]
        code = R.code_document("pilotage", f"Tableau de bord du pilotage {annee}" + (f" (comparé à {comparer})" if comparer else "")
                               + f" — {res['nb_ecoles']} école(s)", f"pilotage:{portee()}:{annee}:{comparer}:{par}:{json.dumps(filtres(), sort_keys=True)}:{date.today()}")
        return H.pdf_reponse(R.pdf_document(f"TABLEAU DE BORD DU PILOTAGE — {annee}", corps, [R.signature_autorite()], code, True,
                                            f"{res['nb_ecoles']} école(s)" + (f" · comparaison avec {comparer}" if comparer else "")), f"pilotage_{annee}.pdf")
