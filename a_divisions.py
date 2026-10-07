# -*- coding: utf-8 -*-
"""Divisions, modules et attributions des applications « GESCOL Circonscription » (CS) et « GESCOL DDEMP » (v1.6).

Le client demande que « les divisions apparaissent chacune avec leurs modules et attributions ». Les divisions /
services existent déjà dans la table jur_services (a_structure.assurer_services crée la liste officielle : CS =
articles 9 à 14 ; DDEMP = services départementaux). Ce module ajoute, pour chaque division :
  * ses attributions (texte de jur_services.attributions, modifiable ici) et son responsable (jur_agents) ;
  * ses MODULES : les fonctionnalités de l'application qui la concernent, décrites dans MODULES_PAR_DIVISION
    (clé = code de service, valeur = liste de (libellé, endpoint, droit)). Un lien n'est affiché que si l'endpoint
    existe (`endpoint in app.view_functions`) : les modules fournis par d'autres chantiers (vivres et stock, épreuves,
    examen blanc, courrier, archives…) apparaissent dès qu'ils sont installés, sans erreur s'ils ne le sont pas ;
  * la liste des agents affectés (jur_agents.service_code = code de la division).

Routes (édition cs / ddemp uniquement) :
    jur_divisions         /juridiction/divisions                 GET      cartes de toutes les divisions
    jur_division          /juridiction/divisions/<code>          GET/POST fiche d'une division ; POST = attributions
                                                                          (droit jur_divisions)
    jur_divisions_pdf     /juridiction/divisions.pdf             GET      « Divisions, modules et attributions »
Les divisions dont le code n'est pas dans MODULES_PAR_DIVISION reçoivent les modules « communs » (clé "*").
"""
import io

from flask import abort, flash, g, redirect, render_template, request, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Frame, Paragraph, Spacer
from werkzeug.routing import BuildError

import a_structure as S
import config
from pdfs import GCanvas

W, H_PAGE = A4

# ------------------------------------------------------------------------------------------ modules par division
# (libellé, endpoint, droit requis pour y écrire — None : lecture pour tout utilisateur connecté)
_TABLEAU = [("Tableau de bord (effectifs, classes par cours, CEP, visites)", "jur_tableau", None),
            ("Classes par cours et par zone", "jur_classes", None)]
_STATS = [("Statistiques des écoles", "jur_stats_ecoles", None),
          ("Effectifs des apprenants (tableaux de recensement)", "jur_stats_effectifs", None),
          ("Enseignants : besoins et écarts", "jur_stats_enseignants", None)]
_FICHES = [("Fiches de recensement, de rentrée et de fin d'année des écoles", "jur_fiches", "jur_fiches"),
           ("Fiches consolidées (synthèse)", "jur_fiches_synthese", "jur_fiches"),
           ("Fiche de recensement (module des écoles)", "recensement_accueil", None),
           ("Rapports de rentrée et de fin d'année (module des écoles)", "rapports_accueil", None),
           ("Tableau synoptique de l'école", "synoptique_accueil", None)]
_CEP = [("CEP : candidats et résultats", "jur_cep", "jur_cep"),
        ("CEP : prévision de l'année suivante", "jur_cep_prevision", "jur_cep"),
        ("CEP : frais de relevés", "jur_cep_frais", "jur_cep"),
        ("Examen blanc (CEP blanc) de la circonscription", "jur_cep_blanc", "jur_cep"),
        ("CEP blanc (module des écoles)", "cep_blanc_accueil", None),
        ("Synthèse des évaluations", "synthese_accueil", None),
        ("Statistiques des évaluations", "eval_statistiques", None),
        ("Analyse des évaluations", "eval_analyse", None),
        ("Bilan annuel", "bilan_annuel", None)]
_PEDA = [("Unités pédagogiques (UP) : responsables, activités, taux d'exécution", "jur_up", "jur_up"),
         ("Conseillers pédagogiques : visites et synthèses", "jur_cp", None),
         ("Visites d'école et de classe", "jur_visites", "jur_visites"),
         ("Bilan des activités des CP et CCS", "jur_bilan_activites", None),
         ("Visites (module des écoles)", "visites_accueil", None),
         ("Comité d'évaluation, épreuves et grilles", "epreuves_accueil", None),
         ("Documents de l'enseignant", "docs_enseignant_accueil", None)]
_PERS = [("Personnel et carrière (par catégorie)", "jur_personnel", "jur_personnel"),
         ("Visites d'aptitude et diplômes", "jur_aptitude", "jur_personnel"),
         ("Départs à la retraite", "jur_retraite", "jur_personnel"),
         ("Agents de la structure", "jur_agents", "jur_personnel"),
         ("Attestations et certificats", "jur_documents", "jur_documents")]
_FIN = [("Frais de relevés (CEP)", "jur_cep_frais", "jur_cep"),
        ("Patrimoine et infrastructures", "patrimoine_accueil", None),
        ("Cantine scolaire", "cantine_accueil", None),
        ("Vivres et stock", "stock_accueil", None)]
_SECR = [("Courrier (arrivée, départ)", "courrier", None),
         ("Archives", "archives", None),
         ("Attestations et certificats", "jur_documents", "jur_documents"),
         ("Conversion de documents en PDF", "conversion_pdf", None),
         ("Transmissions : recevoir", "jur_transmissions", "jur_transmission"),
         ("Suivi des envois des écoles", "jur_transmission_suivi", "jur_transmission")]
_DONNEES = [("Données (sauvegardes, imports)", "donnees_accueil", None),
            ("EducMaster (export)", "educmaster_accueil", None)]
_JUR = [("Écoles de la juridiction", "jur_ecoles", "jur_ecoles"),
        ("Zones pédagogiques / circonscriptions", "jur_zones", "jur_ecoles")]
_SERV = [("Services et attributions (organigramme)", "jur_organigramme", None),
         ("Cachets et signatures", "jur_cachets", "jur_structure")]

MODULES_PAR_DIVISION = {
    # ------------------------------------------------------------------ Circonscription scolaire
    "ccs": _TABLEAU + _STATS + _CEP[:3] + _PEDA[:4] + _PERS[:1] + _SERV + _JUR,
    "cp": _PEDA + [("Fiches des écoles (lecture)", "jur_fiches", "jur_fiches")],
    "secretariat": _SECR + _DONNEES + [("Services et attributions", "jur_organigramme", None)],
    "personnel": _PERS + _FIN + [("Courrier", "courrier", None), ("Archives", "archives", None)],   # SPAF / CSPAF
    "animation": _PEDA + _CEP[3:],                                                                   # CDAP
    "administration": _PERS + _FIN + _SECR[:2] + _DONNEES,                                          # CDAF
    "organisation": _TABLEAU + _STATS + _FICHES + _CEP + _PEDA[:2] + _JUR +                       # DOSP / CDOSP
                    [("Transmissions : recevoir", "jur_transmissions", "jur_transmission"),
                     ("Suivi des envois des écoles", "jur_transmission_suivi", "jur_transmission"),
                     ("Patrimoine et infrastructures", "patrimoine_accueil", None)],
    # ------------------------------------------------------------------ DDEMP
    "direction": _TABLEAU + _STATS + _CEP[:3] + _PEDA[:4] + _PERS[:1] + _SERV + _JUR,
    "sec": _CEP + [("Épreuves et grilles", "epreuves_accueil", None)],
    "semp": _TABLEAU + _STATS + _FICHES + _PEDA + _JUR,
    "srh": _PERS + [("Courrier", "courrier", None), ("Archives", "archives", None)],
    "spaf": _PERS[4:] + _FIN + _SECR + _DONNEES + _STATS[:1],
    "cantines": [("Cantine scolaire", "cantine_accueil", None), ("Vivres et stock", "stock_accueil", None),
                 ("Statistiques des écoles", "jur_stats_ecoles", None)],
    "statistiques": _TABLEAU + _STATS + _FICHES + _CEP[:2] + _DONNEES + [("Fiches consolidées", "jur_fiches_synthese", "jur_fiches")],
    "infrastructures": [("Patrimoine et infrastructures", "patrimoine_accueil", None),
                        ("Classes par cours et par zone (salles)", "jur_classes", None),
                        ("Statistiques des écoles", "jur_stats_ecoles", None), ("Écoles de la juridiction", "jur_ecoles", "jur_ecoles")],
    # ------------------------------------------------------------------ division ajoutée à la main
    "*": _TABLEAU[:1] + [("Services et attributions", "jur_organigramme", None),
                         ("Attestations et certificats", "jur_documents", "jur_documents")],
}


def modules_division(app, code):
    """Modules effectivement disponibles pour une division : [{libelle, endpoint, droit, url, acces}] — uniquement
    les endpoints existants (sans doublon, dans l'ordre de MODULES_PAR_DIVISION)."""
    out, vus = [], set()
    for lib, ep, droit in MODULES_PAR_DIVISION.get(code, MODULES_PAR_DIVISION["*"]):
        if ep in vus or ep not in app.view_functions:
            continue
        try:
            url = url_for(ep)
        except BuildError:
            continue    # endpoint à paramètres : pas de lien direct
        vus.add(ep)
        acces = True
        if droit and g.get("user"):
            try:
                acces = bool(_peut(droit))
            except KeyError:
                acces = True
        out.append({"libelle": lib, "endpoint": ep, "droit": droit, "url": url, "acces": acces})
    return out


_peut = None    # H.peut, fixé par enregistrer()


def _texte_para(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")


def pdf_divisions(divs, s):
    """PDF « Divisions, modules et attributions » : une rubrique par division (en-tête officiel sur la 1re page)."""
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A4)
    c.setTitle("Divisions, modules et attributions")
    c.setAuthor("GESCOL")
    st_t = ParagraphStyle("t", fontName="Times-Bold", fontSize=15, leading=19, alignment=1, spaceAfter=4)
    st_s = ParagraphStyle("s", fontName="Times-Italic", fontSize=9.5, leading=12, alignment=1, spaceAfter=10)
    st_h = ParagraphStyle("h", fontName="Times-Bold", fontSize=11.5, leading=14, spaceBefore=10, spaceAfter=3,
                          textColor=colors.HexColor("#1F4E79"))
    st_i = ParagraphStyle("i", fontName="Times-Italic", fontSize=9.5, leading=12, spaceAfter=2)
    st_k = ParagraphStyle("k", fontName="Helvetica-Bold", fontSize=9, leading=12, spaceBefore=4, spaceAfter=1,
                          textColor=colors.HexColor("#344054"))
    st_p = ParagraphStyle("p", fontName="Times-Roman", fontSize=10, leading=13, alignment=4)
    st_m = ParagraphStyle("m", fontName="Helvetica", fontSize=8.8, leading=11.5, leftIndent=10)
    story = [Paragraph("DIVISIONS, MODULES ET ATTRIBUTIONS", st_t),
             Paragraph(_texte_para(f"{(s or {}).get('nom') or ''} — année scolaire {config.ANNEE_ACTIVE}"), st_s)]
    for d in divs:
        story.append(Paragraph(_texte_para(f"{d['sigle'] or ''} – {d['nom']}".strip(" –")), st_h))
        infos = [f"Responsable : {d['responsable_nom'] or 'non désigné'}"]
        if d.get("reference"):
            infos.insert(0, f"Texte : {d['reference']}")
        if d.get("agents"):
            infos.append(f"Agents affectés : {len(d['agents'])}")
        story.append(Paragraph(_texte_para(" · ".join(infos)), st_i))
        story.append(Paragraph("Modules de l'application", st_k))
        if d["modules"]:
            story.append(Paragraph("<br/>".join("• " + _texte_para(m["libelle"]) for m in d["modules"]), st_m))
        else:
            story.append(Paragraph("Aucun module installé pour cette division.", st_m))
        story.append(Paragraph("Attributions", st_k))
        story.append(Paragraph(_texte_para(d["attributions"] or "Attributions non renseignées."), st_p))
        if d.get("agents"):
            story.append(Paragraph("Agents", st_k))
            story.append(Paragraph("<br/>".join("• " + _texte_para(f"{a['nom']} {a['prenoms'] or ''} — {a['poste'] or ''}".strip(" —"))
                                                for a in d["agents"]), st_m))
        story.append(Spacer(1, 4))
    premiere = True
    while story:
        haut = H_PAGE - 30
        if premiere:
            haut = S.entete_officiel(c, s) - 8
            premiere = False
        f = Frame(45, 40, W - 90, haut - 40, showBoundary=0)
        avant = len(story)
        f.addFromList(story, c)
        c.showPage()
        if len(story) == avant:     # élément trop grand pour une page : abandonné (évite une boucle sans fin)
            story.pop(0)
    c.save()
    return buf.getvalue()


# ------------------------------------------------------------------------------------------ enregistrement Flask
def enregistrer(app, H):
    global _peut
    _peut = H.peut
    q, ex = H.q, H.ex

    def juridiction_ou_404():
        if not config.juridiction():
            abort(404)

    def agents_par_service():
        out = {}
        for a in S.agents_structure():
            out.setdefault(a["service_code"] or "", []).append(a)
        return out

    def divisions():
        """Divisions actives avec responsable, modules et agents."""
        ag = agents_par_service()
        out = []
        for x in S.services():
            d = dict(x)
            d["modules"] = modules_division(app, x["code"])
            d["agents"] = ag.get(x["code"], [])
            out.append(d)
        return out

    def division_ou_404(code):
        d = S.service_par_code(code)
        if not d or not d["actif"]:
            abort(404)
        d = dict(d)
        a = q("SELECT * FROM jur_agents WHERE id=?", (d["responsable_id"],), un=True) if d.get("responsable_id") else None
        d["responsable_nom"] = S.nom_agent(a)
        d["modules"] = modules_division(app, code)
        d["agents"] = agents_par_service().get(code, [])
        return d

    @app.route("/juridiction/divisions")
    @H.connexion_requise()
    def jur_divisions():
        juridiction_ou_404()
        divs = divisions()
        return render_template("jur_divisions.html", divisions=divs, s=S.structure(),
                               nb_modules=sum(len(d["modules"]) for d in divs),
                               nb_agents=sum(len(d["agents"]) for d in divs), racine=S.RACINE.get(S.niveau()))

    @app.route("/juridiction/divisions/<code>", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_division(code):
        juridiction_ou_404()
        d = division_ou_404(code)
        if request.method == "POST":
            if not H.peut("jur_divisions"):
                abort(403)
            attr = (request.form.get("attributions") or "").strip()[:8000]
            ex("UPDATE jur_services SET attributions=? WHERE id=?", (attr, d["id"]))
            H.journal("jur_division_attributions", f"{code} {d['nom']}")
            flash("Attributions enregistrées.", "success")
            return redirect(url_for("jur_division", code=code))
        return render_template("jur_division.html", d=d, s=S.structure(), modifiable=H.peut("jur_divisions"))

    @app.route("/juridiction/divisions.pdf")
    @H.connexion_requise()
    def jur_divisions_pdf():
        juridiction_ou_404()
        H.journal("jur_divisions_pdf", "")
        return H.pdf_reponse(pdf_divisions(divisions(), S.structure()), "divisions_modules_attributions.pdf")
