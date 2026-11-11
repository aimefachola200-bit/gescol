# -*- coding: utf-8 -*-
"""v2.1 — École maternelle dans la préparation de classe.

Section (petits / grands) → domaine de développement → composante → mois / semaine → activité (fiche) ; progression
2026-2027 (grands : planification de la CS Cotonou II, source citée ; petits : progression proposée), emplois du temps
(grands : Direction de l'enseignement maternel, 2012 ; petits : proposé), grilles d'observation (pas d'épreuves
écrites), repères « je retiens » pour l'éducateur, planification du jour, de la semaine et du mois, classeurs PDF
(Times 14, style des fiches de la v1.32). Les classes « Maternelle 1 / 2 » voient ces activités dans « Cette semaine ».
"""
import io
import re
import unicodedata
from datetime import date

from flask import abort, g, render_template, request

import config
import m_preparation as MP

SECTION_NIVEAU = {"Maternelle 1": "petits", "Maternelle 2": "grands"}
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
VUES = [("progression", "Progression"), ("mois", "Mois"), ("semaine", "Semaine"), ("jour", "Jour")]
# mots qui relient une case de l'emploi du temps à une composante de la progression
MOTS_EDT = {"Education pour la santé": ["education pour la sante"], "Passage aux toilettes": ["toilettes"],
            "Lavage des mains": ["lavage des mains"], "Goûters": ["gouter"], "Expression corporelle": ["expression corporelle"],
            "Pré-lecture": ["pre-lecture", "pre lecture"], "Pré-écriture": ["pre-ecriture", "pre ecriture"],
            "Pré-mathématique": ["pre-mathematique", "pre mathematique"], "Observation": ["observation"],
            "Education sensorielle": ["education sensorielle"], "Travaux manuels": ["activites manuelles", "travaux manuels"],
            "Expression plastique": ["expression plastique"], "Expression émotionnelle": ["expression emotionnelle"],
            "Communication orale": ["communication orale"], "Poésie": ["poesie"], "Chant": ["chant"], "Contes": ["conte"],
            "Comptine": ["comptine"]}


def _sa(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("’", "'")


def donnees():
    return MP.corpus().get("maternelle") or {}


def section_de_classe(cl):
    return SECTION_NIVEAU.get(cl["niveau"]) if cl else None


def semaine_du_mois(auj):
    return min((auj.day - 1) // 7 + 1, 5)


def mois_scolaire(auj):
    m = MP.MOIS_FR[auj.month - 1]
    return m if m not in ("Juillet", "Août") else "Septembre"


def lignes(section=None, domaine=None, composante=None, mois=None, semaine=None):
    out = []
    for x in donnees().get("progressions") or []:
        if section and x["section"] != section:
            continue
        if domaine and x["domaine"] != domaine:
            continue
        if composante and x["composante"] != composante:
            continue
        if mois and x["mois"] != mois:
            continue
        if semaine and int(x["semaine"] or 0) != int(semaine):
            continue
        out.append(x)
    ordre = list(MP.MOIS_FR[8:]) + list(MP.MOIS_FR[:8])
    out.sort(key=lambda x: (ordre.index(x["mois"]) if x["mois"] in ordre else 99, int(x["semaine"] or 0), x["domaine"], x["composante"]))
    return out


def edt(section):
    return next((e for e in donnees().get("emplois_du_temps") or [] if e["section"] == section), None)


def cases_du_jour(e, j):
    """Lignes de l'emploi du temps pour le jour j (0 = lundi) : une case vide reprend la case du lundi (cellule fusionnée)."""
    out = []
    for l in (e or {}).get("lignes") or []:
        v = l[1 + j] if 1 + j < len(l) else ""
        v = l[1] if v == "" else v
        if v and v != "—":
            out.append((l[0], v))
    return out


def repartition_semaine(section, mois, semaine):
    """Activités de la semaine placées dans les cases de l'emploi du temps : {jour: [(heure, case, [lignes])]}."""
    e = edt(section)
    acts = [x for x in lignes(section=section, mois=mois, semaine=semaine) if x.get("fiche") or x["activite"]]
    par_comp = {}
    for x in acts:
        par_comp.setdefault(x["composante"], []).append(x)
    utilises = {k: 0 for k in par_comp}
    jours = {}
    for j, nom in enumerate(JOURS):
        cases = []
        for heure, case in cases_du_jour(e, j):
            c = _sa(case)
            mis = []
            for comp, mots in MOTS_EDT.items():
                if comp in par_comp and any(m in c for m in mots):
                    liste = par_comp[comp]
                    mis.append(liste[utilises[comp] % len(liste)])
                    utilises[comp] += 1
            cases.append((heure, case, mis))
        jours[nom] = cases
    return jours


def enregistrer(app, H):

    def domaines():
        return donnees().get("domaines") or []

    def sections():
        return donnees().get("sections") or []

    def fiche(fid):
        return MP.corpus()["fiche_par_id"].get(fid) if fid else None

    def classes_em():
        return [dict(c) for c in H.prep_classes() if c["niveau"] in SECTION_NIVEAU]

    def choix():
        a = request.args
        cl = None
        if a.get("classe", type=int):
            cl = next((c for c in classes_em() if c["id"] == a.get("classe", type=int)), None)
        auj = date.today()
        section = a.get("section") if a.get("section") in ("petits", "grands") else (section_de_classe(cl) or "grands")
        mois = a.get("mois") if a.get("mois") in MP.MOIS_FR else None
        semaine = a.get("semaine", type=int)
        vue = a.get("vue") if a.get("vue") in dict(VUES) else "progression"
        if vue in ("mois", "semaine", "jour") and not mois:
            mois = mois_scolaire(auj)
        if vue in ("semaine", "jour") and not semaine:
            semaine = semaine_du_mois(auj)
        jour = a.get("jour") if a.get("jour") in JOURS else JOURS[min(auj.weekday(), 4)]
        dom = a.get("domaine") if a.get("domaine") in {d["code"] for d in domaines()} else None
        comps = [c for d in domaines() if not dom or d["code"] == dom for c in d["composantes"]]
        comp = a.get("composante") if a.get("composante") in comps else None
        return {"classe": cl, "section": section, "mois": mois, "semaine": semaine, "vue": vue, "jour": jour, "domaine": dom,
                "composante": comp, "composantes": comps}

    def mat_semaine(cl, auj=None):
        """« Cette semaine » d'une classe de maternelle : activités de la semaine par domaine (progression de la section)."""
        auj = auj or date.today()
        section = section_de_classe(cl)
        if not section or not donnees():
            return None
        mois, sem = mois_scolaire(auj), semaine_du_mois(auj)
        mats = []
        for d in domaines():
            ls = lignes(section=section, domaine=d["code"], mois=mois, semaine=sem)
            if not ls:
                continue
            fs, vus = [], set()
            for x in ls:
                f = fiche(x.get("fiche"))
                if f and f["id"] not in vus:
                    vus.add(f["id"])
                    fs.append(f)
            mats.append({"matiere": "dg", "nom": d["nom"], "annuel": "", "domaine": d["code"],
                         "semaine": " ; ".join(f"{x['composante']} : {x['activite']}" for x in ls),
                         "refs": {"sa": [], "u": [], "d": []}, "fiches": fs[:MP.PAR_MATIERE], "total": len(fs), "ids": [f["id"] for f in fs]})
        return {"classe": cl, "cours": "MAT", "mois": mois, "bornes": None, "matieres": mats, "maternelle": True,
                "section": section, "semaine_num": sem}

    H.mat_semaine = mat_semaine

    # ------------------------------------------------------------------ pages
    @app.route("/preparation/maternelle")
    @H.connexion_requise("preparation")
    def mat_accueil():
        M = donnees()
        if not M:
            abort(404)
        c = choix()
        ls = lignes(section=c["section"], domaine=c["domaine"], composante=c["composante"], mois=c["mois"] if c["vue"] != "progression" or request.args.get("mois") else None,
                    semaine=c["semaine"] if c["vue"] in ("semaine", "jour") or request.args.get("semaine") else None)
        semaines_mois = {}
        if c["vue"] == "mois":
            for x in ls:
                semaines_mois.setdefault(int(x["semaine"] or 0), {}).setdefault(x["domaine"], []).append(x)
        rep = repartition_semaine(c["section"], c["mois"], c["semaine"]) if c["vue"] in ("semaine", "jour") else {}
        return render_template("mat_accueil.html", M=M, c=c, ls=ls, fiche=fiche, VUES=VUES, JOURS=JOURS, MOIS=MP.MOIS_FR[8:] + MP.MOIS_FR[:6],
                               semaines_mois=semaines_mois, rep=rep, classes=classes_em(), dom_nom={d["code"]: d["nom"] for d in domaines()})

    @app.route("/preparation/maternelle/emploi-du-temps")
    @H.connexion_requise("preparation")
    def mat_edt():
        c = choix()
        return render_template("mat_edt.html", M=donnees(), c=c, e=edt(c["section"]), JOURS=JOURS)

    @app.route("/preparation/maternelle/grilles")
    @H.connexion_requise("preparation")
    def mat_grilles():
        c = choix()
        gs = [x for x in donnees().get("grilles") or [] if (not c["domaine"] or x["domaine"] == c["domaine"]) and (not c["composante"] or x["composante"] == c["composante"])]
        return render_template("mat_grilles.html", M=donnees(), c=c, gs=gs, classes=classes_em())

    @app.route("/preparation/maternelle/reperes")
    @H.connexion_requise("preparation")
    def mat_reperes():
        c = choix()
        rs = [x for x in donnees().get("reperes") or [] if not c["domaine"] or x["domaine_code"] == c["domaine"]]
        return render_template("mat_reperes.html", M=donnees(), c=c, rs=rs)

    # ------------------------------------------------------------------ PDF (Times 14, style des fiches v1.32)
    def doc_pdf(titre, sous_titre, corps_fn, paysage=False):
        import pdfs
        import dessins_pdf as DS
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer
        taille = landscape(A4) if paysage else A4
        W, Hh = taille
        SER = pdfs.police_serif()
        coul_hex = DS.couleur_matiere("dg")
        coul = colors.HexColor(coul_hex)
        st = {"t": ParagraphStyle("t", fontName=SER["gras"], fontSize=16, leading=20, alignment=1, textColor=coul),
              "s": ParagraphStyle("s", fontName=SER["normal"], fontSize=13, leading=16, alignment=1, spaceAfter=6),
              "c": ParagraphStyle("c", fontName=SER["normal"], fontSize=14, leading=18),
              "h": ParagraphStyle("h", fontName=SER["gras"], fontSize=14, leading=18, textColor=coul, spaceBefore=6),
              "p": ParagraphStyle("p", fontName=SER["normal"], fontSize=12, leading=15),
              "pb": ParagraphStyle("pb", fontName=SER["gras"], fontSize=12, leading=15),
              "ph": ParagraphStyle("ph", fontName=SER["gras"], fontSize=12, leading=15, textColor=colors.white, alignment=1),
              "m": ParagraphStyle("m", fontName=SER["italique"], fontSize=10, leading=13, textColor=colors.HexColor("#B54708"))}

        def deco(cv, doc):
            cv.saveState()
            if doc.page == 1:
                pdfs._entete_primaire(cv, W, Hh, doc.leftMargin, None, "maternelle")
                cv.setFillColor(coul)
                cv.rect(doc.leftMargin, Hh - 43 * mm, W - doc.leftMargin - doc.rightMargin, 1.6 * mm, stroke=0, fill=1)
            cv.setFillColor(colors.HexColor("#667085"))
            cv.setFont(SER["normal"], 9)
            cv.drawString(doc.leftMargin, 8 * mm, f"{config.ECOLE.get('nom', '')} · {config.ANNEE_ACTIVE} · École maternelle")
            cv.drawRightString(W - doc.rightMargin, 8 * mm, f"imprimé le {date.today().strftime('%d/%m/%Y')}")
            cv.restoreState()

        buf = io.BytesIO()
        doc = BaseDocTemplate(buf, pagesize=taille, title=titre, author="SCOLARIS", leftMargin=15 * mm, rightMargin=12 * mm)
        def cadre(haut):
            return Frame(15 * mm, 16 * mm, W - 27 * mm, Hh - haut - 16 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        doc.addPageTemplates([PageTemplate("premiere", [cadre(48 * mm)], onPage=deco, autoNextPageTemplate="suite"),
                              PageTemplate("suite", [cadre(14 * mm)], onPage=deco)])
        h = [Paragraph(MP.txt_pdf(titre), st["t"]), Paragraph(MP.txt_pdf(sous_titre), st["s"]), Spacer(1, 4)]
        h += corps_fn(st, W - 27 * mm, coul, colors)
        doc.build(h, canvasmaker=pdfs.GCanvasPedaNum)
        return buf.getvalue()

    def table(data, largeurs, st, coul, colors, entete=True):
        from reportlab.platypus import Paragraph, Table, TableStyle
        rows = []
        for i, l in enumerate(data):
            rows.append([Paragraph(MP.txt_pdf(v), st["ph"] if (entete and i == 0) else st["p"]) for v in l])
        t = Table(rows, colWidths=largeurs, repeatRows=1 if entete else 0, splitByRow=1)
        style = [("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#667085")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if entete:
            style.append(("BACKGROUND", (0, 0), (-1, 0), coul))
        t.setStyle(TableStyle(style))
        return t

    def nom_section(s):
        return next((x["nom"] for x in sections() if x["code"] == s), s)

    def corps_planification(c):
        def f(st, L, coul, colors):
            from reportlab.platypus import Paragraph, Spacer
            out = []
            if c["vue"] in ("semaine", "jour"):
                rep = repartition_semaine(c["section"], c["mois"], c["semaine"])
                jours = [c["jour"]] if c["vue"] == "jour" else JOURS
                for j in jours:
                    out.append(Paragraph(j, st["h"]))
                    data = [["Heure", "Emploi du temps", "Activité prévue"]]
                    for heure, case, mis in rep.get(j, []):
                        data.append([heure, case, " ; ".join(f"{x['composante']} : {x['activite']}" for x in mis) or ""])
                    out.append(table(data, [36 * 2.83, L * 0.40, L - 36 * 2.83 - L * 0.40], st, coul, colors))
                    out.append(Spacer(1, 6))
            else:
                ls = lignes(section=c["section"], domaine=c["domaine"], mois=c["mois"])
                data = [["Mois", "Sem.", "Domaine", "Composante", "Activité"]]
                for x in ls:
                    data.append([x["mois"], str(x["semaine"]), x["domaine"], x["composante"], x["activite"]])
                out.append(table(data, [L * 0.12, L * 0.06, L * 0.07, L * 0.22, L * 0.53], st, coul, colors))
            src = (edt(c["section"]) or {}).get("source", "")
            out += [Spacer(1, 6), Paragraph(MP.txt_pdf("Progression : " + (lignes(section=c["section"])[:1] or [{"source": ""}])[0]["source"]), st["m"])]
            if c["vue"] in ("semaine", "jour") and src:
                out.append(Paragraph(MP.txt_pdf("Emploi du temps : " + src), st["m"]))
            return out
        return f

    def titre_planif(c):
        t = {"jour": f"Planification du {c['jour'].lower()} — {c['mois']}, semaine {c['semaine']}",
             "semaine": f"Planification de la semaine — {c['mois']}, semaine {c['semaine']}",
             "mois": f"Planification du mois — {c['mois']}"}.get(c["vue"], "Progression annuelle")
        return t

    @app.route("/preparation/maternelle/planification.pdf")
    @H.connexion_requise("preparation")
    def mat_planification_pdf():
        c = choix()
        if c["vue"] == "progression":
            c["vue"] = "mois" if c["mois"] else "progression"
        sous = f"{nom_section(c['section'])} · {donnees().get('annee', '')}" + (f" · {c['classe']['nom']}" if c["classe"] else "")
        H.journal("mat_planification_pdf", f"{c['section']} {c['vue']} {c['mois'] or ''} {c['semaine'] or ''}")
        return H.pdf_reponse(doc_pdf(titre_planif(c), sous, corps_planification(c), paysage=c["vue"] in ("semaine", "jour")),
                             f"maternelle_{c['section']}_{c['vue']}.pdf")

    @app.route("/preparation/maternelle/emploi-du-temps.pdf")
    @H.connexion_requise("preparation")
    def mat_edt_pdf():
        c = choix()
        e = edt(c["section"])
        if not e:
            abort(404)

        def f(st, L, coul, colors):
            from reportlab.platypus import Paragraph, Spacer
            data = [["Heure"] + JOURS]
            for l in e["lignes"]:
                data.append([l[0]] + [(l[1 + j] if l[1 + j] != "" else l[1]) if 1 + j < len(l) else "" for j in range(5)])
            out = [table(data, [L * 0.13] + [L * 0.174] * 5, st, coul, colors), Spacer(1, 6)]
            if e.get("note"):
                out.append(Paragraph(MP.txt_pdf(e["note"]), st["p"]))
            out.append(Paragraph(MP.txt_pdf(("Proposé — " if e.get("propose") else "") + e["source"]), st["m"]))
            return out
        return H.pdf_reponse(doc_pdf("Emploi du temps", nom_section(c["section"]) + (" (proposé)" if e.get("propose") else ""), f, paysage=True),
                             f"emploi_du_temps_{c['section']}.pdf")

    @app.route("/preparation/maternelle/grilles.pdf")
    @H.connexion_requise("preparation")
    def mat_grilles_pdf():
        c = choix()
        gs = [x for x in donnees().get("grilles") or [] if (not c["domaine"] or x["domaine"] == c["domaine"]) and (not c["composante"] or x["composante"] == c["composante"])]
        noms = []
        if c["classe"]:
            noms = [f"{r['nom']} {r['prenoms']}" for r in H.q("SELECT nom, prenoms FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms",
                                                            (c["classe"]["id"],))]

        def f(st, L, coul, colors):
            from reportlab.platypus import PageBreak, Paragraph, Spacer
            out = []
            for i, gr in enumerate(gs):
                if i:
                    out.append(PageBreak())
                out.append(Paragraph(MP.txt_pdf(f"{gr['domaine']} — {gr['composante']}"), st["h"]))
                out.append(Paragraph(MP.txt_pdf(gr["consigne"]), st["p"]))
                out.append(Spacer(1, 4))
                ent = ["N°", "Nom et prénoms"] + [x for x in gr["criteres"]] + ["Observation"]
                data = [ent]
                for n, nom in enumerate(noms or [""] * 20, 1):
                    data.append([str(n), nom] + ["A · EC · NA"] * len(gr["criteres"]) + [""])
                lc = (L * 0.5) / max(1, len(gr["criteres"]))
                out.append(table(data, [L * 0.05, L * 0.25] + [lc] * len(gr["criteres"]) + [L * 0.2], st, coul, colors))
                out.append(Spacer(1, 4))
                out.append(Paragraph("A : acquis · EC : en cours d'acquisition · NA : non acquis — " + MP.txt_pdf(gr["mention"]), st["m"]))
            return out
        sous = "Grilles d'observation (pas d'épreuves écrites)" + (f" · {c['classe']['nom']}" if c["classe"] else "")
        return H.pdf_reponse(doc_pdf("Grilles d'observation", sous, f, paysage=True), "grilles_observation_maternelle.pdf")

    @app.route("/preparation/maternelle/classeur.pdf")
    @H.connexion_requise("preparation")
    def mat_classeur_pdf():
        """Classeur de la semaine ou du mois : planification puis fiches d'activités (une par activité)."""
        import pypdf
        c = choix()
        c["vue"] = "semaine" if c["semaine"] else "mois"
        c["mois"] = c["mois"] or mois_scolaire(date.today())
        ls = lignes(section=c["section"], mois=c["mois"], semaine=c["semaine"] if c["vue"] == "semaine" else None)
        fs, vus = [], set()
        for x in ls:
            f = fiche(x.get("fiche"))
            if f and f["id"] not in vus:
                vus.add(f["id"])
                d = dict(f, source_id=f["id"], duree="20 min" if c["section"] == "petits" else "25 min")
                if c["classe"]:
                    d["classe_id"] = c["classe"]["id"]
                fs.append(d)
        sous = f"{nom_section(c['section'])} · {donnees().get('annee', '')}" + (f" · {c['classe']['nom']}" if c["classe"] else "")
        w = pypdf.PdfWriter()
        for pg in pypdf.PdfReader(io.BytesIO(doc_pdf(titre_planif(c), sous, corps_planification(c), paysage=c["vue"] == "semaine"))).pages:
            w.add_page(pg)
        if fs:
            for pg in pypdf.PdfReader(io.BytesIO(H.prep_pdf_fiches(fs, "FICHE D'ACTIVITÉ — ÉCOLE MATERNELLE"))).pages:
                w.add_page(pg)
        out = io.BytesIO()
        w.add_metadata({"/Title": "Classeur — école maternelle", "/Author": "SCOLARIS"})
        if hasattr(w, "compress_identical_objects"):   # v2.2 : images communes une seule fois
            try:
                w.compress_identical_objects(remove_identicals=True, remove_orphans=True)
            except Exception:  # noqa: BLE001
                pass
        w.write(out)
        H.journal("mat_classeur_pdf", f"{c['section']} {c['mois']} {c['semaine'] or ''} : {len(fs)} fiche(s)")
        return H.pdf_reponse(out.getvalue(), f"classeur_maternelle_{c['section']}_{_sa(c['mois'])}{'_s' + str(c['semaine']) if c['semaine'] else ''}.pdf")

    @app.context_processor
    def _ctx_mat():
        try:  # v2.1.1 : jamais d'erreur sur toutes les pages (connexion comprise) si le corpus manque
            return {"MAT_DISPO": bool(donnees())}
        except Exception:  # noqa: BLE001
            return {"MAT_DISPO": False}
