# -*- coding: utf-8 -*-
"""v2.4.7 — Hiérarchie du SECONDAIRE : établissements → conseillers / inspecteurs pédagogiques → Inspection secondaire → DDESTFP.

Applications concernées (éditions « sec_* ») :
* « Secondaire » / « Secondaire Public » (collèges, lycées, ETP) : section « secondaire » ajoutée au paquet de transmission
  (effectifs par classe et série, redoublants, orientation) + saisie des résultats BEPC / BAC (/secondaire/examens-resultats) ;
* « Inspection Secondaire » (édition de base « cs ») et « DDESTFP » (édition de base « ddemp ») : tableaux de supervision
  (/sec/tableau, /sec/examens, /sec/personnel) avec filtres et exports PDF / Excel ; le tableau de bord du primaire y est remplacé.
Le vocabulaire (Circonscription → Inspection secondaire, DDEMP → DDESTFP, école → établissement) est adapté à l'affichage
(pages HTML, titres des PDF) sans toucher aux données.
"""
import re

from flask import abort, flash, g, redirect, render_template, request, url_for

import config
import jur_format

NIVEAUX = ["6ème", "5ème", "4ème", "3ème", "2nde", "1ère", "Tle"]
TYPES_SEC = ("CEG", "LYC", "ETP")
EXAMENS = ("BEPC", "BAC")
CHAMPS_EXAM = ("inscrits_g", "inscrits_f", "presents_g", "presents_f", "admis_g", "admis_f")

# --------------------------------------------------------------------------- vocabulaire
_ELISIONS = [("de la Inspection", "de l'Inspection"), ("de la inspection", "de l'inspection"), ("la Inspection", "l'Inspection"),
             ("la inspection", "l'inspection"), ("de Inspection", "d'Inspection"), ("de inspection", "d'inspection"),
             ("de Inspections", "d'Inspections"),
             # accords après « école » → « établissement » (supervision)
             ("Aucune établissement", "Aucun établissement"), ("aucune établissement", "aucun établissement"),
             ("Une établissement", "Un établissement"), ("une établissement", "un établissement"),
             ("cette établissement", "cet établissement"), ("Cette établissement", "Cet établissement"),
             ("de la établissement", "de l'établissement"), ("de la Établissement", "de l'Établissement"),
             ("la établissement", "l'établissement"), ("La établissement", "L'établissement"),
             ("établissement ouverte", "établissement ouvert"), ("Établissement ouverte", "Établissement ouvert"),
             ("établissement choisie", "établissement choisi")]
_COMMUN = [("Circonscriptions scolaires", "Inspections secondaires"), ("Circonscription scolaire", "Inspection secondaire"),
           ("circonscriptions scolaires", "inspections secondaires"), ("circonscription scolaire", "inspection secondaire"),
           ("Circonscriptions", "Inspections"), ("Circonscription", "Inspection"), ("circonscriptions", "inspections"),
           ("circonscription", "inspection"), ("DDEMP", "DDESTFP"),
           ("UASCEP", "UASCES"), ("Uascep", "Uasces"), ("uascep", "uasces"), ("Note /10", "Note /20"),   # v2.5.0 : au collège, UASCES ; barème d'EPS sur 20
           ("Chef de Inspection", "Chef d'Inspection")]
_SUPERVISION = [("Écoles", "Établissements"), ("écoles", "établissements"), ("École", "Établissement"), ("école", "établissement"),
                ("Ecoles", "Établissements"), ("Ecole", "Établissement")]


def habiller_texte(t, supervision=False):
    """Adapte un texte au vocabulaire du secondaire."""
    if not t or not isinstance(t, str):
        return t
    for a, b in _COMMUN + ([(x, y) for x, y in _SUPERVISION] if supervision else []):
        if a in t:
            t = t.replace(a, b)
    t = re.sub(r"\bCS\b", "Inspection", t)
    for a, b in _ELISIONS:
        if a in t:
            t = t.replace(a, b)
    return t


def habiller_html(html, supervision=False):
    parts = re.split(r"(<script\b.*?</script>|<style\b.*?</style>|<[^>]+>)", html, flags=re.S | re.I)
    for i in range(0, len(parts), 2):
        parts[i] = habiller_texte(parts[i], supervision)
    return "".join(parts)


def _mapper(v, supervision):
    if isinstance(v, str):
        return habiller_texte(v, supervision)
    if isinstance(v, list):
        return [_mapper(x, supervision) for x in v]
    if isinstance(v, tuple):
        return tuple(_mapper(x, supervision) for x in v)
    return v


# --------------------------------------------------------------------------- calculs purs
def _n(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def totaux_classes(classes):
    """[{"niveau", "garcons", "filles", "redoublants_g", "redoublants_f"}] → {niveau: [g, f, red_g, red_f]} + totaux."""
    par = {n: [0, 0, 0, 0] for n in NIVEAUX}
    for c in classes or []:
        n = c.get("niveau")
        if n not in par:
            par[n] = [0, 0, 0, 0]
        for i, k in enumerate(("garcons", "filles", "redoublants_g", "redoublants_f")):
            par[n][i] += _n(c.get(k))
    return par


def taux(admis, presents):
    return round(100.0 * admis / presents, 1) if presents else None


def ligne_etablissement(e, d, personnel):
    """Une ligne de supervision pour un établissement : effectifs, classes, enseignants, ratios."""
    classes = (d or {}).get("classes") or []
    par = totaux_classes(classes)
    g_ = sum(v[0] for v in par.values())
    f_ = sum(v[1] for v in par.values())
    red = sum(v[2] + v[3] for v in par.values())
    ens = sum(1 for p in personnel or [] if p.get("role") == "enseignant")
    ensf = sum(1 for p in personnel or [] if p.get("role") == "enseignant" and (p.get("sexe") or "").upper() == "F")
    adm = sum(1 for p in personnel or [] if p.get("role") in ("directeur", "adjoint", "administratif"))
    return {"id": e["id"], "nom": e["nom"], "code": e["code"], "type": e["type"], "secteur": e["secteur"],
            "cs_nom": e["cs_nom"], "zone_nom": e["zone_nom"] or "", "commune": e["commune"] or "",
            "transmis": bool(d), "classes": len(classes), "g": g_, "f": f_, "t": g_ + f_, "red": red, "par": par,
            "ens": ens, "ensf": ensf, "adm": adm,
            "eleves_classe": round((g_ + f_) / len(classes), 1) if classes else None,
            "eleves_ens": round((g_ + f_) / ens, 1) if ens else None}


def examens_etablissement(d, examen):
    x = ((d or {}).get("examens") or {}).get(examen) or {}
    v = {k: _n(x.get(k)) for k in CHAMPS_EXAM}
    v["taux_g"], v["taux_f"] = taux(v["admis_g"], v["presents_g"]), taux(v["admis_f"], v["presents_f"])
    v["taux"] = taux(v["admis_g"] + v["admis_f"], v["presents_g"] + v["presents_f"])
    v["saisi"] = bool(x)
    return v


def additionner(valeurs):
    t = {k: sum(v[k] for v in valeurs) for k in CHAMPS_EXAM}
    t["taux"] = taux(t["admis_g"] + t["admis_f"], t["presents_g"] + t["presents_f"])
    t["taux_g"], t["taux_f"] = taux(t["admis_g"], t["presents_g"]), taux(t["admis_f"], t["presents_f"])
    return t


def enseignant_par_fonction(fonction):
    f = (fonction or "").lower()
    return any(m in f for m in ("enseign", "professeur", "instit", "educat", "éducat", "maitre", "maître", "animat", "pcem", "pcet"))


# --------------------------------------------------------------------------- enregistrement
def enregistrer(app, H):
    q, ex = H.q, H.ex
    if not config.secondaire():
        return
    supervision = config.juridiction()

    # ---- vocabulaire (HTML + titres des PDF)
    @app.after_request
    def _vocabulaire(rep):
        try:
            if rep.mimetype == "text/html" and rep.status_code == 200 and not rep.direct_passthrough:
                rep.set_data(habiller_html(rep.get_data(as_text=True), supervision))
        except Exception:  # noqa: BLE001 - l'habillage ne doit jamais casser une page
            pass
        return rep

    try:
        import pdfs as _pdfs
        if not getattr(_pdfs, "_habille_v247", False):
            _orig = _pdfs.document_tableau

            def document_tableau(*a, **k):
                return _orig(*_mapper(list(a), supervision), **{x: _mapper(y, supervision) for x, y in k.items()})
            _pdfs.document_tableau = document_tableau
            _pdfs._habille_v247 = True
    except Exception:  # noqa: BLE001
        pass

    # ======================================================================= côté établissement
    if not supervision:
        H.schema("""
            CREATE TABLE IF NOT EXISTS sec_examens (
                id INTEGER PRIMARY KEY, ecole_id INTEGER, annee TEXT NOT NULL, examen TEXT NOT NULL,
                inscrits_g INTEGER DEFAULT 0, inscrits_f INTEGER DEFAULT 0, presents_g INTEGER DEFAULT 0, presents_f INTEGER DEFAULT 0,
                admis_g INTEGER DEFAULT 0, admis_f INTEGER DEFAULT 0, maj TEXT, UNIQUE (ecole_id, annee, examen));
        """)

        def section_secondaire(annee=None):
            annee = annee or config.ANNEE_ACTIVE
            classes = []
            for c in H.classes_autorisees():
                if c["niveau"] not in NIVEAUX:
                    continue
                el = q("SELECT sexe, COALESCE(redoublant,0) r FROM eleves WHERE statut='inscrit' AND classe_id=?", (c["id"],))
                f_ = sum(1 for e in el if (e["sexe"] or "").upper().startswith("F"))
                rf = sum(1 for e in el if e["r"] and (e["sexe"] or "").upper().startswith("F"))
                rg = sum(1 for e in el if e["r"]) - rf
                try:
                    from m_orientation import serie_de_classe
                    serie = serie_de_classe(c["nom"])
                except Exception:  # noqa: BLE001
                    serie = ""
                classes.append({"nom": c["nom"], "niveau": c["niveau"], "serie": serie, "garcons": len(el) - f_, "filles": f_,
                                "redoublants_g": rg, "redoublants_f": rf, "titulaire_nom": (c["titulaire_nom"] if "titulaire_nom" in c.keys() else "") or ""})
            out = {"annee": annee, "classes": classes}
            ex_ = {}
            for r in q("SELECT * FROM sec_examens WHERE ecole_id=? AND annee=?", (H.eco(), annee)):
                ex_[r["examen"]] = {k: r[k] or 0 for k in CHAMPS_EXAM}
            if ex_:
                out["examens"] = ex_
            try:
                dec = {}
                for r in q("SELECT COALESCE(o.decision,'') d, e.sexe s FROM orientation_decisions o JOIN eleves e ON e.id=o.eleve_id "
                           "JOIN classes c ON c.id=e.classe_id WHERE o.annee=? AND COALESCE(o.decision,'')!=''", (annee,)):
                    k = dec.setdefault(r["d"], [0, 0])
                    k[1 if (r["s"] or "").upper().startswith("F") else 0] += 1
                if dec:
                    out["orientation"] = dec
            except Exception:  # noqa: BLE001
                pass
            return (out if classes else None), (None if classes else "Aucune classe du secondaire (6ème à Tle).")

        if not hasattr(H, "sections_extra"):
            H.sections_extra = {}
        H.sections_extra["secondaire"] = lambda annee=None: section_secondaire(annee)

        @app.route("/secondaire/examens-resultats", methods=["GET", "POST"])
        @H.connexion_requise("donnees")
        def sec_examens_saisie():
            annee = config.ANNEE_ACTIVE
            if request.method == "POST":
                for exa in EXAMENS:
                    vals = [max(0, _n(request.form.get(f"{exa}_{k}"))) for k in CHAMPS_EXAM]
                    if not any(vals):
                        continue
                    ex("INSERT INTO sec_examens (ecole_id, annee, examen, inscrits_g, inscrits_f, presents_g, presents_f, admis_g, admis_f, maj) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ecole_id, annee, examen) DO UPDATE SET inscrits_g=excluded.inscrits_g, "
                       "inscrits_f=excluded.inscrits_f, presents_g=excluded.presents_g, presents_f=excluded.presents_f, "
                       "admis_g=excluded.admis_g, admis_f=excluded.admis_f, maj=excluded.maj", (H.eco(), annee, exa, *vals, H.maintenant()))
                H.journal("sec_examens", annee)
                flash("Résultats enregistrés : ils partiront avec la prochaine transmission.", "success")
                return redirect(url_for("sec_examens_saisie"))
            cur = {r["examen"]: r for r in q("SELECT * FROM sec_examens WHERE ecole_id=? AND annee=?", (H.eco(), annee))}
            return render_template("sec_examens_saisie.html", annee=annee, cur=cur, EXAMENS=EXAMENS, CHAMPS=CHAMPS_EXAM)
        return

    # ======================================================================= côté supervision (Inspection / DDESTFP)
    import m_juridiction as J
    ddemp = config.EDITION == "ddemp"

    @app.before_request
    def _accueil():
        if request.endpoint == "jur_tableau":
            return redirect(url_for("sec_tableau"))
        return None

    def filtres():
        a = {"annee": (request.args.get("annee") or "").strip() or J.annee(), "cs_id": request.args.get("cs_id", type=int),
             "zone_id": request.args.get("zone_id", type=int), "type_": (request.args.get("type") or "").strip() or None,
             "secteur": (request.args.get("secteur") or "").strip() or None}
        if a["type_"] not in TYPES_SEC:
            a["type_"] = None
        if a["secteur"] not in ("public", "prive"):
            a["secteur"] = None
        return a

    def charger(a):
        ecs = [e for e in J.ecoles(cs_id=a["cs_id"], zone_id=a["zone_id"], type_=a["type_"], secteur=a["secteur"]) if e["type"] in TYPES_SEC]
        ids = [e["id"] for e in ecs]
        sec = J.sections("secondaire", a["annee"], ids)
        pers = J.sections("personnel", a["annee"], ids)
        return ecs, sec, pers

    def regrouper(lignes):
        """Totaux par Inspection (DDESTFP) ou par zone (Inspection)."""
        cle = "cs_nom" if ddemp else "zone_nom"
        d = {}
        for l in lignes:
            k = l[cle] or "—"
            r = d.setdefault(k, {"nom": k, "etabs": 0, "g": 0, "f": 0, "t": 0, "classes": 0, "ens": 0, "transmis": 0})
            r["etabs"] += 1
            r["transmis"] += 1 if l["transmis"] else 0
            for x in ("g", "f", "t", "classes", "ens"):
                r[x] += l[x]
        return sorted(d.values(), key=lambda r: r["nom"])

    def vue_tableau(a):
        ecs, sec, pers = charger(a)
        lignes = [ligne_etablissement(e, sec.get(e["id"]), pers.get(e["id"])) for e in ecs]
        niv = {n: [0, 0, 0, 0] for n in NIVEAUX}
        for l in lignes:
            for n, v in l["par"].items():
                niv.setdefault(n, [0, 0, 0, 0])
                for i in range(4):
                    niv[n][i] += v[i]
        tot = {"etabs": len(lignes), "transmis": sum(1 for l in lignes if l["transmis"]), "g": sum(l["g"] for l in lignes),
               "f": sum(l["f"] for l in lignes), "classes": sum(l["classes"] for l in lignes), "ens": sum(l["ens"] for l in lignes),
               "red": sum(l["red"] for l in lignes)}
        tot["t"] = tot["g"] + tot["f"]
        tot["eleves_classe"] = round(tot["t"] / tot["classes"], 1) if tot["classes"] else None
        tot["eleves_ens"] = round(tot["t"] / tot["ens"], 1) if tot["ens"] else None
        tot["pct_f"] = round(100 * tot["f"] / tot["t"], 1) if tot["t"] else None
        return lignes, niv, tot

    def vue_examens(a):
        ecs, sec, _ = charger(a)
        res = {}
        lignes = []
        for e in ecs:
            ligne = {"nom": e["nom"], "type": e["type"], "zone_nom": e["zone_nom"] or "", "cs_nom": e["cs_nom"]}
            for exa in EXAMENS:
                ligne[exa] = examens_etablissement(sec.get(e["id"]), exa)
            lignes.append(ligne)
        for exa in EXAMENS:
            res[exa] = additionner([l[exa] for l in lignes])
        return lignes, res

    def vue_personnel(a):
        ecs, sec, pers = charger(a)
        lignes = []
        for e in ecs:
            ps = pers.get(e["id"]) or []
            ens = [p for p in ps if p.get("role") == "enseignant" or enseignant_par_fonction(p.get("fonction"))]
            cat = {}
            for p in ens:
                cat[p.get("categorie") or "—"] = cat.get(p.get("categorie") or "—", 0) + 1
            lignes.append({"nom": e["nom"], "type": e["type"], "zone_nom": e["zone_nom"] or "", "cs_nom": e["cs_nom"],
                           "ens": len(ens), "ensf": sum(1 for p in ens if (p.get("sexe") or "").upper() == "F"),
                           "admin": sum(1 for p in ps if p.get("role") in ("directeur", "adjoint", "administratif")),
                           "soutien": sum(1 for p in ps if p.get("role") == "soutien"), "cat": cat,
                           "total": len(ps), "transmis": bool(ps)})
        return lignes

    def contexte(vue):
        a = filtres()
        cs = J.cs_liste()
        return dict(vue=vue, a=a, annees=J.annees(), cs=cs, zones=J.zones(a["cs_id"]) if (a["cs_id"] or not ddemp) else [],
                    TYPES={k: v for k, v in jur_format.TYPES_ECOLE.items() if k in TYPES_SEC}, DDEMP=ddemp, NIVEAUX=NIVEAUX,
                    EXAMENS=EXAMENS, struct=J.structure())

    @app.route("/sec/tableau")
    @H.connexion_requise("jur_ecoles")
    def sec_tableau():
        c = contexte("tableau")
        lignes, niv, tot = vue_tableau(c["a"])
        return render_template("sec_supervision.html", lignes=lignes, niv=niv, tot=tot, groupes=regrouper(lignes), **c)

    @app.route("/sec/examens")
    @H.connexion_requise("jur_ecoles")
    def sec_examens():
        c = contexte("examens")
        lignes, res = vue_examens(c["a"])
        return render_template("sec_supervision.html", lignes=lignes, res=res, **c)

    @app.route("/sec/personnel")
    @H.connexion_requise("jur_ecoles")
    def sec_personnel():
        c = contexte("personnel")
        lignes = vue_personnel(c["a"])
        return render_template("sec_supervision.html", lignes=lignes, **c)

    def tableau_export(vue, a):
        zone = "Inspection" if ddemp else "Zone"
        if vue == "examens":
            lignes, res = vue_examens(a)
            cols = ["Établissement", "Type", zone] + [f"{x} {s}" for x in EXAMENS for s in ("Prés.", "Admis", "Taux %")]
            rows = [[l["nom"], l["type"], l["cs_nom" if ddemp else "zone_nom"] or ""] +
                    [v for x in EXAMENS for v in (l[x]["presents_g"] + l[x]["presents_f"], l[x]["admis_g"] + l[x]["admis_f"],
                                                   "" if l[x]["taux"] is None else l[x]["taux"])] for l in lignes]
            tot = ["TOTAL", "", ""] + [v for x in EXAMENS for v in (res[x]["presents_g"] + res[x]["presents_f"],
                                                                      res[x]["admis_g"] + res[x]["admis_f"], "" if res[x]["taux"] is None else res[x]["taux"])]
            return "RÉSULTATS AUX EXAMENS (BEPC, BAC)", cols, rows, tot
        if vue == "personnel":
            lignes = vue_personnel(a)
            cols = ["Établissement", "Type", zone, "Enseignants", "dont F", "Administration", "Soutien", "Total"]
            rows = [[l["nom"], l["type"], l["cs_nom" if ddemp else "zone_nom"] or "", l["ens"], l["ensf"], l["admin"], l["soutien"], l["total"]] for l in lignes]
            tot = ["TOTAL", "", ""] + [sum(l[k] for l in lignes) for k in ("ens", "ensf", "admin", "soutien", "total")]
            return "PERSONNEL DES ÉTABLISSEMENTS", cols, rows, tot
        lignes, niv, t = vue_tableau(a)
        cols = ["Établissement", "Type", zone, "Classes", "Garçons", "Filles", "Total", "Redoublants", "Enseignants", "Élèves/classe", "Élèves/enseignant"]
        rows = [[l["nom"], l["type"], l["cs_nom" if ddemp else "zone_nom"] or "", l["classes"], l["g"], l["f"], l["t"], l["red"], l["ens"],
                 "" if l["eleves_classe"] is None else l["eleves_classe"], "" if l["eleves_ens"] is None else l["eleves_ens"]] for l in lignes]
        tot = ["TOTAL", "", "", t["classes"], t["g"], t["f"], t["t"], t["red"], t["ens"],
               "" if t["eleves_classe"] is None else t["eleves_classe"], "" if t["eleves_ens"] is None else t["eleves_ens"]]
        return "EFFECTIFS DES ÉTABLISSEMENTS DU SECONDAIRE", cols, rows, tot

    def vue_arg():
        v = request.args.get("vue", "tableau")
        return v if v in ("tableau", "examens", "personnel") else "tableau"

    @app.route("/sec/export.pdf")
    @H.connexion_requise("jur_ecoles")
    def sec_export_pdf():
        a = filtres()
        titre, cols, rows, tot = tableau_export(vue_arg(), a)
        st = J.structure() or {}
        pdf = H.pdfs.document_tableau(titre, cols, rows, sous_titre=f"{st.get('nom') or ''} — {a['annee']}", total=tot, paysage=True,
                                      taille=7.5, signatures=[(st.get("responsable_titre") or "Le responsable", st.get("responsable_nom") or "", None, True)])
        return H.pdf_reponse(pdf, f"secondaire_{vue_arg()}_{a['annee']}.pdf")

    @app.route("/sec/export.xlsx")
    @H.connexion_requise("jur_ecoles")
    def sec_export_xlsx():
        a = filtres()
        titre, cols, rows, tot = tableau_export(vue_arg(), a)
        try:
            return H.xlsx.reponse_classeur(f"secondaire_{vue_arg()}_{a['annee']}.xlsx",
                                           [("Secondaire", cols, rows + [tot], {"titre_haut": [habiller_texte(titre), a["annee"]]})])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("sec_tableau"))
