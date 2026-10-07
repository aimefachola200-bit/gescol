# -*- coding: utf-8 -*-
"""Fiches officielles des écoles dans les applications « GESCOL Circonscription » (CS) et « GESCOL DDEMP ».

Source : sections « recensement » et « rapports » des paquets de transmission des écoles (jur_sections) :
    recensement = {"primaire" | "maternelle": {"annee", "valeurs": {clé: valeur}}}
    rapports    = {"rentree-ep" | "fin-ep" | "rentree-em" | "fin-em": {"annee", "valeurs": {...}}}
Les valeurs sont celles produites côté école par H.recensement_valeurs / H.rapports_valeurs ; elles sont
redessinées dans la forme OFFICIELLE (en-tête MEMP, NIP…) par m_recensement.pdf_depuis_valeurs et
m_rapports.pdf_depuis_valeurs : exactement la même fiche que celle imprimée par l'école.

Pages :
* jur_fiches (/juridiction/fiches) : tableau écoles × fiches (reçue / incomplète / absente, date), filtres année,
  CS, zone, type, secteur, fiche, état ; jur_fiche_pdf (fiche officielle remplie), jur_fiche_voir (page lisible),
  jur_fiches_lot (téléchargement groupé : un PDF pour la sélection, ou un .zip : un PDF par zone / CS + un PDF
  par école).
* jur_fiches_synthese (/juridiction/fiches/synthese) : fiche CONSOLIDÉE de la CS (ou d'une zone) / de la DDEMP
  (ou d'une CS) : sommes des champs numériques, nombre d'écoles par réponse, récapitulatif du personnel par
  statut ; PDF officiel (titre « Synthèse de la CS … ») et Excel (une feuille par tableau + « Écoles prises en
  compte ») ; contrôles de cohérence (totaux, écoles manquantes ou incomplètes).
"""
import io
import re
import zipfile
from collections import OrderedDict
from datetime import date

from flask import abort, flash, redirect, render_template, request, send_file, url_for

import config
import m_juridiction as J
import m_rapports as MRA
import m_recensement as MRE
from db import q

# code de fiche → (section du paquet, clé dans la section, types d'école concernés, libellé, libellé court)
FICHES = OrderedDict([
    ("recensement-primaire", ("recensement", "primaire", ("EP",), "Fiche de recensement – primaire", "Recens. EP")),
    ("recensement-maternelle", ("recensement", "maternelle", ("EM", "EE"), "Fiche de recensement – maternelle",
                                "Recens. EM")),
    ("rentree-ep", ("rapports", "rentree-ep", ("EP",), "Rapport de rentrée – EP", "Rentrée EP")),
    ("fin-ep", ("rapports", "fin-ep", ("EP",), "Rapport de fin d'année – EP", "Fin d'année EP")),
    ("rentree-em", ("rapports", "rentree-em", ("EM", "EE"), "Rapport de rentrée – EM", "Rentrée EM")),
    ("fin-em", ("rapports", "fin-em", ("EM", "EE"), "Rapport de fin d'année – EM", "Fin d'année EM")),
])
# cases indispensables : une fiche reçue sans elles est « incomplète »
REQUIS = {
    "recensement-primaire": [("nom", "nom de l'école"), ("eff_t", "effectif global (7.1)"),
                             ("t73.tot.ens_t", "total ENSEMBLE (7.3)"), ("salles_utilisees", "salles utilisées (3.15)"),
                             ("t8.1.nom", "état nominatif du personnel (8)")],
    "recensement-maternelle": [("nom", "nom de l'école"), ("t21.enfants.t", "effectif des enfants (2.1)"),
                               ("t3.tot.ens_t", "total Ensemble (3)"), ("salles_utilisees", "salles utilisées (2.2)"),
                               ("t6.1.nom", "état nominatif du personnel (6)")],
    "rentree-ep": [("nom_ecole", "nom de l'école"), ("classes_ouvertes", "classes ouvertes (2.3)"),
                   ("eff.nb.ENS_T", "nombre d'élèves (3)"), ("pers.1.nom", "état nominatif (7)")],
    "fin-ep": [("nom_ecole", "nom de l'école"), ("eff.debut.ENS_T", "élèves en début d'année (3)"),
               ("eff.fin.ENS_T", "élèves en fin d'année (3)"), ("pers.1.nom", "état nominatif (7)")],
    "rentree-em": [("nom_ecole", "nom de l'école"), ("sections_ouvertes", "sections ouvertes (2.3)"),
                   ("rep.debut.tot_T", "effectif au début de l'année (III)"), ("pers.1.nom", "état nominatif (XI)")],
    "fin-em": [("nom_ecole", "nom de l'école"), ("rep.debut.tot_T", "effectif au début (III)"),
               ("rep.fin.tot_T", "effectif en fin d'année (III)"), ("pers.1.nom", "état nominatif (XI)")],
}
ETATS = {"recue": "Reçue", "incomplete": "Incomplète", "absente": "Absente", "sans_objet": "Non concernée"}


# ============================================================================ accès aux fiches transmises
def _vide(v):
    return v is None or (isinstance(v, str) and v.strip() in ("", "-")) or v == [] or v == {}


def sections_brutes(annee, ecole_ids=None):
    """{ecole_id: {"recensement": (données, maj), "rapports": (données, maj)}} pour l'année."""
    import json
    out = {}
    for r in q("SELECT s.ecole_id, s.section, s.donnees, s.maj FROM jur_sections s JOIN jur_ecoles e ON e.id=s.ecole_id "
               "WHERE s.annee=? AND s.section IN ('recensement','rapports')", (annee,)):
        if ecole_ids is not None and r["ecole_id"] not in ecole_ids:
            continue
        try:
            d = json.loads(r["donnees"])
        except ValueError:
            continue
        out.setdefault(r["ecole_id"], {})[r["section"]] = (d if isinstance(d, dict) else {}, r["maj"] or "")
    return out


def fiche_de(secs, code):
    """(valeurs, date de réception) d'une fiche dans les sections d'une école, ou (None, None)."""
    sec, cle = FICHES[code][0], FICHES[code][1]
    d, maj = (secs or {}).get(sec, ({}, ""))
    f = (d or {}).get(cle)
    if not isinstance(f, dict):
        return None, None
    v = f.get("valeurs") if isinstance(f.get("valeurs"), dict) else None
    if not v:
        return None, None
    return v, (f.get("transmis_le") or f.get("maj") or maj or "")[:16]


def etat(code, valeurs, type_ecole):
    """(état, cases manquantes)."""
    if valeurs is None:
        return ("absente" if type_ecole in FICHES[code][2] else "sans_objet"), []
    manq = [lib for k, lib in REQUIS[code] if _vide(valeurs.get(k))]
    return ("incomplete" if manq else "recue"), manq


def entete_ecole(e):
    """Identité d'une école de la juridiction (en-tête des fiches)."""
    return {"ecole": e["nom"] or "", "code": e["code"] or "", "cs": e["cs_nom"] or "",
            "departement": e["departement"] or "", "zone": e["zone_nom"] or "", "commune": e["commune"] or "",
            "arrondissement": e["arrondissement"] or "", "localite": e["localite"] or "",
            "telephone": e["telephone"] or "", "email": e["email"] or "",
            "directeur": e["directeur_nom"] or "", "directeur_titre": e["directeur_titre"] or ""}


def pdf_fiche(code, valeurs, annee, entete, vierge=False):
    sec, cle = FICHES[code][0], FICHES[code][1]
    if sec == "recensement":
        return MRE.pdf_depuis_valeurs(cle, valeurs, annee, entete, vierge=vierge)
    return MRA.pdf_depuis_valeurs(cle, valeurs, annee, entete, vierge=vierge)


def vue(code, valeurs, synthese=False):
    sec, cle = FICHES[code][0], FICHES[code][1]
    return (MRE if sec == "recensement" else MRA).vue_lecture(cle, valeurs, synthese)


def fusionner(pdfs):
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for b in pdfs:
        for p in PdfReader(io.BytesIO(b)).pages:
            w.add_page(p)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def nom_fichier(t):
    import unicodedata
    t = unicodedata.normalize("NFD", str(t)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")[:60] or "fiche"


# ============================================================================ synthèse
def synthese(code, ecoles_vals, titre, s, cs_nom=""):
    """Fiche consolidée : {"valeurs", "controles" [(niveau, texte)], "personnel", "n"}."""
    sec, cle = FICHES[code][0], FICHES[code][1]
    resp_t, resp_n = (s or {}).get("responsable_titre") or "", (s or {}).get("responsable_nom") or ""
    if sec == "recensement":
        r = MRE.synthese_valeurs(cle, ecoles_vals, titre,
                                 {"cs": cs_nom, "departement": (s or {}).get("departement") or "",
                                  "rempli_par": resp_n, "rempli_fonction": resp_t})
        r["controles"] = [("warning", m) for m in r["controles"]]
    else:
        r = MRA.synthese_valeurs(cle, ecoles_vals, titre,
                                 {"cs": cs_nom, "departement": (s or {}).get("departement") or "",
                                  "par_nom": resp_n, "par_fonction": resp_t,
                                  "chef_nom": resp_n if config.EDITION == "cs" else ""})
    return r


def feuilles_vue(vue_, haut, prefixe=""):
    """Feuilles Excel d'une vue lisible : « Champs » + une feuille par tableau."""
    vus = set()

    def nom_f(t):
        t = re.sub(r"[\[\]:*?/\\]", " ", t).strip()[:28] or "Tableau"
        base, i = t, 2
        while t.lower() in vus:
            t = f"{base[:25]} {i}"
            i += 1
        vus.add(t.lower())
        return t
    champs = []
    feuilles = []
    for s in vue_:
        for num, lib, val in s["champs"]:
            champs.append([s["titre"], num, lib, val])
    feuilles.append((nom_f(prefixe + "Champs"), ["Rubrique", "N°", "Libellé", "Valeur"], champs, {"titre_haut": haut}))
    for s in vue_:
        for t in s["tableaux"]:
            lignes = []
            for l in t["lignes"]:
                cells = []
                for c in l["cells"]:
                    x = MRE.nombre(c) if c not in (None, "") else None
                    cells.append("" if c is None else (int(x) if x is not None and float(x).is_integer() and
                                                       re.match(r"^\d+$", str(c)) else c))
                lignes.append([l["lib"]] + cells)
            feuilles.append((nom_f(s["titre"].split(" (")[0] if t["titre"].startswith("Rubrique") or t["titre"] == s["titre"]
                                   else t["titre"]),
                             [t["coin"] or "Ligne"] + t["colonnes"], lignes, {"titre_haut": haut + [s["titre"]]}))
    return feuilles


# ============================================================================ enregistrement Flask
def enregistrer(app, H):

    def garde():
        if not config.juridiction():
            abort(404)

    def annee_req():
        a = request.args.get("annee") or J.annee()
        return a if re.match(r"^\d{4}-\d{4}$", a) else J.annee()

    def entier_arg(nom):
        try:
            return int(request.args.get(nom) or 0) or None
        except ValueError:
            return None

    def filtres():
        f = request.args
        cs_id = entier_arg("cs")
        if config.EDITION == "cs" and not cs_id:
            c = J.cs_courante()
            cs_id = c["id"] if c else None
        typ = f.get("type") if f.get("type") in J.TYPES else None
        sect = f.get("secteur") if f.get("secteur") in J.SECTEURS else None
        return cs_id, entier_arg("zone"), typ, sect

    def tableau(annee, cs_id, zone_id, typ, sect):
        """Lignes du tableau écoles × fiches."""
        ecs = J.ecoles(cs_id, zone_id, typ, sect)
        secs = sections_brutes(annee, {e["id"] for e in ecs})
        lignes = []
        for e in ecs:
            fiches = {}
            for code in FICHES:
                v, d = fiche_de(secs.get(e["id"]), code)
                et, manq = etat(code, v, e["type"])
                fiches[code] = {"etat": et, "date": d or "", "manquants": manq}
            lignes.append({"e": e, "fiches": fiches})
        return lignes

    def ecole_fiche(ecole_id, code):
        if code not in FICHES:
            abort(404)
        e = J.ecole(ecole_id)
        if not e:
            abort(404)
        return e

    def titre_portee(cs_id, zone_id):
        s = J.structure() or {}
        if zone_id:
            z = q("SELECT z.nom, c.nom cs FROM jur_zones z JOIN jur_cs c ON c.id=z.cs_id WHERE z.id=?", (zone_id,), un=True)
            return (f"Synthèse de la CS {z['cs']} – {z['nom']}" if z else "Synthèse de la zone"), (z["cs"] if z else "")
        if cs_id:
            c = J.cs_par_id(cs_id)
            return f"Synthèse de la CS {c['nom'] if c else ''}", (c["nom"] if c else "")
        return f"Synthèse de la DDEMP du {s.get('departement') or ''}", ""

    # ------------------------------------------------------------------ tableau des fiches
    @app.route("/juridiction/fiches")
    @H.connexion_requise("jur_fiches")
    def jur_fiches():
        garde()
        annee = annee_req()
        cs_id, zone_id, typ, sect = filtres()
        codes = [request.args["fiche"]] if request.args.get("fiche") in FICHES else list(FICHES)
        lignes = tableau(annee, cs_id, zone_id, typ, sect)
        filtre_etat = request.args.get("etat") if request.args.get("etat") in ETATS else None
        if filtre_etat:
            lignes = [l for l in lignes if any(l["fiches"][c]["etat"] == filtre_etat for c in codes)]
        stats = {c: {k: sum(1 for l in lignes if l["fiches"][c]["etat"] == k) for k in ETATS} for c in FICHES}
        return render_template("jur_fiches.html", lignes=lignes, codes=codes, FICHES=FICHES, ETATS=ETATS, stats=stats,
                               annee=annee, annees=J.annees(), cs=J.cs_liste(), zones=J.zones(cs_id),
                               f=request.args, cs_id=cs_id, zone_id=zone_id)

    # ------------------------------------------------------------------ une fiche : PDF officiel, page lisible
    @app.route("/juridiction/fiches/<int:ecole_id>/<fiche>.pdf")
    @H.connexion_requise("jur_fiches")
    def jur_fiche_pdf(ecole_id, fiche):
        garde()
        e = ecole_fiche(ecole_id, fiche)
        annee = annee_req()
        vierge = request.args.get("vierge") == "1"
        v, d = fiche_de(sections_brutes(annee, {ecole_id}).get(ecole_id), fiche)
        if v is None and not vierge:
            flash(f"{FICHES[fiche][3]} : aucune fiche transmise par « {e['nom']} » pour {annee}.", "warning")
            return redirect(url_for("jur_fiches", annee=annee))
        ent = entete_ecole(e)
        if not vierge:
            ent["mention"] = f"Fiche transmise par l'école (reçue le {d[:10]}) – éditée par {config.ECOLE.get('nom', '')}"
        H.journal("jur_fiche_pdf", f"{e['code']} {fiche} {annee}")
        return H.pdf_reponse(pdf_fiche(fiche, v or {}, annee, ent, vierge),
                             f"{fiche}_{nom_fichier(e['nom'])}_{annee}{'_vierge' if vierge else ''}.pdf")

    @app.route("/juridiction/fiches/<int:ecole_id>/<fiche>")
    @H.connexion_requise("jur_fiches")
    def jur_fiche_voir(ecole_id, fiche):
        garde()
        e = ecole_fiche(ecole_id, fiche)
        annee = annee_req()
        v, d = fiche_de(sections_brutes(annee, {ecole_id}).get(ecole_id), fiche)
        et, manq = etat(fiche, v, e["type"])
        sec, cle = FICHES[fiche][0], FICHES[fiche][1]
        ctrl = []
        if v is not None:
            if sec == "recensement":
                ctrl = [("warning", m) for m in MRE.controles(cle, v, [])]
            else:
                ctrl = MRA.controles(cle, v)
        return render_template("jur_fiche_voir.html", e=e, fiche=fiche, info=FICHES[fiche], annee=annee,
                               annees=J.annees(), vue=vue(fiche, v) if v is not None else [], date=d, etat=et,
                               manquants=manq, ETATS=ETATS, controles=ctrl, FICHES=FICHES)

    # ------------------------------------------------------------------ téléchargement groupé
    @app.route("/juridiction/fiches/lot")
    @H.connexion_requise("jur_fiches")
    def jur_fiches_lot():
        garde()
        annee = annee_req()
        fiche = request.args.get("fiche")
        if fiche not in FICHES:
            flash("Choisissez la fiche à télécharger.", "warning")
            return redirect(url_for("jur_fiches", annee=annee))
        cs_id, zone_id, typ, sect = filtres()
        ecs = J.ecoles(cs_id, zone_id, typ, sect)
        secs = sections_brutes(annee, {e["id"] for e in ecs})
        groupes = OrderedDict()   # (CS, zone) → [(école, pdf)]
        for e in ecs:
            v, d = fiche_de(secs.get(e["id"]), fiche)
            if v is None:
                continue
            ent = dict(entete_ecole(e), mention=f"Fiche transmise par l'école (reçue le {d[:10]})")
            cle = e["cs_nom"] or "" if config.EDITION == "ddemp" and not cs_id else (e["zone_nom"] or "Sans zone")
            groupes.setdefault(cle, []).append((e, pdf_fiche(fiche, v, annee, ent)))
        if not groupes:
            flash("Aucune fiche reçue pour cette sélection.", "warning")
            return redirect(url_for("jur_fiches", annee=annee, fiche=fiche))
        base = f"{fiche}_{annee}"
        H.journal("jur_fiches_lot", f"{fiche} {annee} {sum(len(x) for x in groupes.values())} fiche(s)")
        if request.args.get("format") == "zip":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for g_, lst in groupes.items():
                    dossier = nom_fichier(g_)
                    z.writestr(f"{dossier}.pdf", fusionner([p for _e, p in lst]))
                    for e, p in lst:
                        z.writestr(f"{dossier}/{nom_fichier(e['nom'])}_{e['code']}.pdf", p)
            buf.seek(0)
            return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=base + ".zip")
        return H.pdf_reponse(fusionner([p for lst in groupes.values() for _e, p in lst]), base + ".pdf")

    # ------------------------------------------------------------------ fiches consolidées
    def donnees_synthese(fiche, annee, cs_id, zone_id, typ, sect):
        ecs = J.ecoles(cs_id, zone_id, typ, sect)
        secs = sections_brutes(annee, {e["id"] for e in ecs})
        prises, ecoles = [], []
        for e in ecs:
            v, d = fiche_de(secs.get(e["id"]), fiche)
            et, manq = etat(fiche, v, e["type"])
            if et == "sans_objet":
                continue
            ecoles.append({"e": e, "etat": et, "date": d or "", "manquants": manq})
            if v is not None:
                prises.append((e, v))
        titre, cs_nom = titre_portee(cs_id, zone_id)   # CS / zone / DDEMP selon la portée choisie
        r = synthese(fiche, [(e["nom"], v) for e, v in prises], titre, J.structure(), cs_nom)
        manque = [(("danger" if x["etat"] == "absente" else "warning"),
                   f"{x['e']['nom']} : fiche {ETATS[x['etat']].lower()}"
                   + (f" ({', '.join(x['manquants'])})" if x["manquants"] else "")) for x in ecoles if x["etat"] != "recue"]
        r["controles"] = manque + r["controles"]
        r.update(titre=titre, ecoles=ecoles, prises=prises)
        return r

    @app.route("/juridiction/fiches/synthese")
    @H.connexion_requise("jur_fiches")
    def jur_fiches_synthese():
        garde()
        annee = annee_req()
        fiche = request.args.get("fiche") if request.args.get("fiche") in FICHES else "recensement-primaire"
        cs_id, zone_id, typ, sect = filtres()
        r = donnees_synthese(fiche, annee, cs_id, zone_id, typ, sect)
        sec, cle = FICHES[fiche][0], FICHES[fiche][1]
        fmt_ = request.args.get("format")
        s = J.structure() or {}
        if fmt_ == "pdf":
            if not r["prises"]:
                flash("Aucune fiche reçue : synthèse impossible.", "warning")
                return redirect(url_for("jur_fiches_synthese", **request.args.to_dict(flat=True) | {"format": ""}))
            ent = {"synthese": True, "titre": r["titre"], "departement": s.get("departement") or "",
                   "visa": s.get("responsable_titre") or ("Le Chef de la Circonscription Scolaire" if config.EDITION == "cs"
                                                          else "Le Directeur Départemental"),
                   "mention": f"{r['n']} école(s) prise(s) en compte – édité le {date.today().strftime('%d/%m/%Y')}"}
            pdfs = [pdf_fiche(fiche, r["valeurs"], annee, ent)]
            if request.args.get("par") == "1":   # une synthèse par zone (CS) / par CS (DDEMP) à la suite
                grp = J.zones(cs_id) if (config.EDITION == "cs" or cs_id) and not zone_id else \
                    ([] if zone_id else J.cs_liste())
                for x in grp:
                    rz = donnees_synthese(fiche, annee, (x["cs_id"] if "cs_id" in x.keys() else x["id"]),
                                          (x["id"] if "cs_id" in x.keys() else None), typ, sect)
                    if rz["prises"]:
                        pdfs.append(pdf_fiche(fiche, rz["valeurs"], annee,
                                              dict(ent, titre=rz["titre"],
                                                   mention=f"{rz['n']} école(s) prise(s) en compte")))
            H.journal("jur_fiches_synthese", f"{fiche} {annee} pdf")
            return H.pdf_reponse(fusionner(pdfs) if len(pdfs) > 1 else pdfs[0],
                                 f"synthese_{fiche}_{nom_fichier(r['titre'])}_{annee}.pdf")
        vue_ = vue(fiche, r["valeurs"], synthese=True)
        if fmt_ == "xlsx":
            haut = [config.ECOLE.get("nom", ""), f"{r['titre']} – {FICHES[fiche][3]} – année {annee}"]
            feuilles = feuilles_vue(vue_, haut)
            if sec == "recensement":
                tk = MRE._tables_personnel(cle)
                for k, nom_f, lst in ((tk[0], "Personnel", r["personnel"]), (tk[1], "Personnel de soutien",
                                                                              r.get("soutien", []))):
                    t = MRE.index(cle).tables[k][1]
                    cols = MRE.feuilles(t["cols"])
                    ch = MRE.chemins(t["cols"])
                    feuilles.append((nom_f, ["École"] + [ch[c["k"]] for c in cols],
                                     [[p["ecole"]] + [("X" if c["t"] == "c" and p.get(c["k"]) == "1" else
                                                       ("" if c["t"] == "c" else p.get(c["k"], ""))) for c in cols]
                                      for p in lst], {"titre_haut": haut}))
            else:
                cols = MRA.bloc_personnel(cle)["cols"]
                feuilles.append(("Personnel", ["École"] + [c["l"] for c in cols],
                                 [[p["ecole"]] + [p.get(c["c"], "") for c in cols] for p in r["personnel"]],
                                 {"titre_haut": haut}))
            feuilles.append(("Contrôles", ["Niveau", "Contrôle de cohérence"],
                             [["Incohérence" if n_ == "danger" else "À vérifier", m] for n_, m in r["controles"]]
                             or [["", "Aucune incohérence détectée."]], {"titre_haut": haut}))
            feuilles.append(("Écoles prises en compte", ["École", "Code", "Type", "Secteur", "CS", "Zone pédagogique",
                                                         "État de la fiche", "Reçue le", "Cases manquantes",
                                                         "Prise en compte"],
                             [[x["e"]["nom"], x["e"]["code"], x["e"]["type"], J.SECTEURS.get(x["e"]["secteur"], ""),
                               x["e"]["cs_nom"] or "", x["e"]["zone_nom"] or "", ETATS[x["etat"]], x["date"][:10],
                               ", ".join(x["manquants"]), "Oui" if x["etat"] != "absente" else "Non"]
                              for x in r["ecoles"]], {"titre_haut": haut}))
            H.journal("jur_fiches_synthese", f"{fiche} {annee} xlsx")
            try:
                return H.xlsx.reponse_classeur(f"synthese_{fiche}_{annee}.xlsx", feuilles)
            except H.xlsx.ExcelIndisponible as err:
                flash(str(err), "danger")
        # ventilation par zone (CS) / par CS (DDEMP)
        ventil = OrderedDict()
        for x in r["ecoles"]:
            g_ = (x["e"]["cs_nom"] or "—") if config.EDITION == "ddemp" and not cs_id else (x["e"]["zone_nom"] or "Sans zone")
            d = ventil.setdefault(g_, {"attendues": 0, "recues": 0, "incompletes": 0})
            d["attendues"] += 1
            d["recues"] += x["etat"] == "recue"
            d["incompletes"] += x["etat"] == "incomplete"
        return render_template("jur_fiches_synthese.html", r=r, vue=vue_, fiche=fiche, FICHES=FICHES, ETATS=ETATS,
                               annee=annee, annees=J.annees(), cs=J.cs_liste(), zones=J.zones(cs_id), f=request.args,
                               cs_id=cs_id, zone_id=zone_id, ventil=ventil)
