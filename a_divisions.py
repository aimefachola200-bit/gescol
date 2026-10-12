# -*- coding: utf-8 -*-
"""Divisions, rubriques, modules et lignes d'action des applications « GESCOL Circonscription » (CS) et « GESCOL DDEMP »
(v1.6).

Demande du client : « les divisions apparaissent chacune avec leurs modules et attributions » et « chaque division au
niveau déconcentré doit avoir sa rubrique et sa ligne d'action conformément à l'AOF » (AOF = arrêté portant
Attributions, Organisation et Fonctionnement des structures déconcentrées du MEMP : CS et DDEMP).

Décisions
  * La liste des divisions de la CS suit l'AOF (a_structure.SERVICES_DEFAUT, articles 9 à 14 : Division du Secrétariat
    art. 10, Division de l'Animation Pédagogique art. 11, Division de l'Administration et des Finances art. 12,
    Division de l'Organisation Scolaire et de la Prévision art. 13). Le « Service du Personnel et des Affaires
    financières » (CSPAF), conservé parce que le client y fait référence, devient en v1.6 le « Service des Ressources
    Humaines » (RH, code inchangé « personnel ») : « le personnel de l'école au RH de la CS » — ses modules sont ceux
    du personnel de la juridiction ET du personnel de l'école ouverte (comme le SRH de la DDEMP) ; les affaires
    financières relèvent de la CDAF. Il reste marqué « hors AOF » tant que le texte officiel n'est pas saisi.
  * Périmètre d'accès (v1.6, a_integration.perimetre_utilisateur) : un compte chef_service / agent rattaché à une
    division (utilisateurs.service_code, sinon jur_agents.user_id) n'accède qu'aux modules de MODULES_PAR_DIVISION
    de sa division (et à leurs sous-pages) ; la fiche /juridiction/divisions/<code> montre les comptes rattachés et
    leur périmètre (H.perimetre_division).
  * DDEMP : le texte de l'AOF n'a pas pu être obtenu ; les attributions des services ont été rédigées par GESCOL et
    sont marquées « Rédigé par GESCOL, à conformer à l'AOF ». Le bouton « Saisir le texte de l'AOF » (numéro d'article +
    attributions collées) remplace le texte rédigé et change la source en « AOF – article N ».
  * Rubrique d'une division = sigle, nom, article de l'AOF, autorité de rattachement (parent_code), chef (agent
    responsable + titre du signataire), attributions, source. Colonnes ajoutées à jur_services (H.ajouter_colonne, sans
    modifier m_juridiction) : article_aof TEXT, source_aof TEXT, initialisées depuis jur_services.reference
    (« Article N » → AOF) ou la note (REDIGE → GESCOL).
  * Lignes d'action (table jur_lignes_action) : une ligne d'action = une attribution de l'AOF (une puce « - … ; » ou
    « • … ; » du texte), avec indicateur, cible, échéance, responsable, modules GESCOL liés (JSON d'endpoints), état
    (prévue | en cours | réalisée | reportée), taux (0-100), observations. Au premier affichage d'une division pour une
    année, les lignes sont générées depuis les puces des attributions (table jur_lignes_action_gen = mémoire de cette
    génération, pour ne pas recréer ce que l'utilisateur a supprimé). « Régénérer depuis l'AOF » AJOUTE les attributions
    manquantes (comparaison des libellés) et conserve les lignes existantes et leur suivi.
  * Taux de réalisation : taux effectif d'une ligne = 100 si l'état est « réalisée », sinon le taux saisi (0 par
    défaut) ; taux d'une division = moyenne des taux effectifs de ses lignes de l'année (— sans ligne) ; taux de la
    structure = moyenne de toutes les lignes de toutes les divisions.
  * MODULES : fonctionnalités de l'application liées à la division (MODULES_PAR_DIVISION, clé = code de service, valeur
    = liste de (libellé, endpoint, droit)). Un lien n'est affiché que si l'endpoint existe.

Routes (édition cs / ddemp uniquement) :
    jur_divisions               /juridiction/divisions                        GET      rubriques de toutes les divisions
    jur_divisions_plan          /juridiction/divisions/plan                   GET      vue d'ensemble des lignes d'action
    jur_divisions_plan_pdf      /juridiction/divisions/plan.pdf               GET
    jur_divisions_plan_xlsx     /juridiction/divisions/plan.xlsx              GET
    jur_divisions_pdf           /juridiction/divisions.pdf                    GET      « Divisions, modules et attributions »
    jur_division                /juridiction/divisions/<code>                 GET/POST fiche ; POST = attributions
    jur_division_aof            /juridiction/divisions/<code>/aof             POST     saisie du texte officiel (article + texte)
    jur_division_lignes_generer /juridiction/divisions/<code>/lignes/generer  POST     (ré)génération depuis les attributions
    jur_division_ligne_form     /juridiction/divisions/<code>/lignes/nouvelle GET/POST
                                /juridiction/divisions/lignes/<lid>/modifier  GET/POST
    jur_division_ligne_rapide   /juridiction/divisions/lignes/<lid>/suivi     POST     état / taux / échéance / observations
    jur_division_ligne_supprimer /juridiction/divisions/lignes/<lid>/supprimer POST
    jur_division_pdf            /juridiction/divisions/<code>/plan.pdf        GET      « Plan d'action de la division »
    jur_division_xlsx           /juridiction/divisions/<code>/plan.xlsx       GET
    jur_division_import         /juridiction/divisions/<code>/lignes/import   GET/POST (?modele=1 : modèle Excel)
Droit d'écriture : jur_divisions (admin, responsable, chef_service) ; lecture : tout utilisateur connecté.
"""
import io
import json
import re

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

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_lignes_action (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    niveau TEXT NOT NULL,                 -- cs | ddemp
    service_code TEXT NOT NULL,           -- jur_services.code
    annee TEXT NOT NULL,
    ordre INTEGER DEFAULT 0,
    libelle TEXT NOT NULL,                -- une attribution de l'AOF (verbe d'action)
    indicateur TEXT, cible TEXT, echeance TEXT, responsable TEXT,
    modules TEXT,                         -- JSON : liste d'endpoints GESCOL liés
    etat TEXT DEFAULT 'prévue',           -- prévue | en cours | réalisée | reportée
    taux INTEGER DEFAULT 0,               -- 0-100
    observations TEXT, maj TEXT);
CREATE INDEX IF NOT EXISTS i_jur_lignes_action ON jur_lignes_action(niveau, service_code, annee, ordre);
CREATE TABLE IF NOT EXISTS jur_lignes_action_gen (
    niveau TEXT NOT NULL, service_code TEXT NOT NULL, annee TEXT NOT NULL, maj TEXT,
    PRIMARY KEY (niveau, service_code, annee));
"""

ETATS = ["prévue", "en cours", "réalisée", "reportée"]
ENT_LIGNES = ["Division", "Ordre", "Ligne d'action", "Indicateur", "Cible", "Échéance", "Responsable", "Modules GESCOL",
              "État", "Taux (%)", "Observations"]

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
# v1.6 : personnel de l'école ouverte (RH de la CS, SRH de la DDEMP) + comptes des directeurs et enseignants
_PERS_ECOLE = [("Personnel de l'école ouverte", "personnel", None),
               ("Gestion de carrière des enseignants (école ouverte)", "carriere_accueil", None),
               ("Documents de l'enseignant (certificats, fiches d'évaluation)", "docs_enseignant_accueil", None),
               ("Tableau synoptique du personnel (école ouverte)", "synoptique_personnel_liste", None),
               ("Comptes des directeurs et enseignants", "jur_comptes", "jur_comptes"),
               ("Messages WhatsApp / SMS aux directeurs et enseignants", "jur_messages", None)]
_FIN = [("Frais de relevés (CEP)", "jur_cep_frais", "jur_cep"),
        ("Patrimoine et infrastructures", "patrimoine_accueil", None),
        ("Cantine scolaire", "cantine_accueil", None),
        ("Vivres et stock", "stock_accueil", None)]
# v1.6 : financement des écoles (subventions de l'État, cotisations de cantine, dépenses, trésorerie, bilan et budget)
_FIN_ECOLE = [("Financement des écoles (subventions, cantine, dépenses, bilan)", "jur_financement", "jur_financement"),
              ("Subventions de l'État et recettes (école ouverte)", "recettes_accueil", None),
              ("Dépenses (école ouverte)", "depenses_accueil", None),
              ("Trésorerie, bilan et budget (école ouverte)", "tresorerie", None),
              ("Frais de dossier CEP (école ouverte)", "cep_frais", None)]
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
    # v1.6 : Service des Ressources Humaines (RH, ex-CSPAF) : personnel de la juridiction + personnel de l'école
    # ouverte (comme le SRH de la DDEMP) ; les affaires financières passent à la CDAF
    "personnel": _PERS + _PERS_ECOLE,                                                                # RH
    "animation": _PEDA + _CEP[3:],                                                                   # CDAP
    "administration": _PERS + _FIN + _FIN_ECOLE + _SECR[:2] + _DONNEES,                             # CDAF
    "organisation": _TABLEAU + _STATS + _FICHES + _CEP + _PEDA[:2] + _JUR +                       # DOSP / CDOSP
                    [("Transmissions : recevoir", "jur_transmissions", "jur_transmission"),
                     ("Suivi des envois des écoles", "jur_transmission_suivi", "jur_transmission"),
                     ("Patrimoine et infrastructures", "patrimoine_accueil", None)],
    # ------------------------------------------------------------------ DDEMP
    "direction": _TABLEAU + _STATS + _CEP[:3] + _PEDA[:4] + _PERS[:1] + _SERV + _JUR,
    "sec": _CEP + [("Épreuves et grilles", "epreuves_accueil", None)],
    "semp": _TABLEAU + _STATS + _FICHES + _PEDA + _JUR,
    # DDEMP : le personnel enseignant et administratif relève du Service des Ressources Humaines (SRH)
    "srh": _PERS + _PERS_ECOLE,
    "spaf": _FIN + _FIN_ECOLE + _SECR[:2] + _SECR[3:] + _DONNEES + _STATS[:1],
    "cantines": [("Cantine scolaire", "cantine_accueil", None), ("Vivres et stock", "stock_accueil", None),
                 ("Financement des écoles (cotisations de cantine, subventions)", "jur_financement", "jur_financement"),
                 ("Statistiques des écoles", "jur_stats_ecoles", None)],
    "statistiques": _TABLEAU + _STATS + _FICHES + _CEP[:2] + _DONNEES + [("Fiches consolidées", "jur_fiches_synthese", "jur_fiches")],
    "infrastructures": [("Patrimoine et infrastructures", "patrimoine_accueil", None),
                        ("Classes par cours et par zone (salles)", "jur_classes", None),
                        ("Statistiques des écoles", "jur_stats_ecoles", None), ("Écoles de la juridiction", "jur_ecoles", "jur_ecoles")],
    # ------------------------------------------------------------------ division ajoutée à la main
    "*": _TABLEAU[:1] + [("Services et attributions", "jur_organigramme", None),
                         ("Attestations et certificats", "jur_documents", "jur_documents")],
}

# libellé de chaque endpoint connu (pour afficher les modules d'une ligne d'action même s'ils ne sont pas installés)
LIBELLES_MODULES = {}
for _liste in MODULES_PAR_DIVISION.values():
    for _lib, _ep, _dr in _liste:
        LIBELLES_MODULES.setdefault(_ep, _lib)


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


# ------------------------------------------------------------------------------------------ rubriques et lignes d'action
_RE_ARTICLE = re.compile(r"article\s*(\d+)", re.I)
_RE_PUCE = re.compile(r"^\s*(?:[-–—•*·▪]|\d{1,2}[.)])\s*(.+?)\s*$")


def numero_article(texte):
    """« Article 11 » / « AOF – article 11 » / « 11 » → « 11 » ; '' sinon."""
    t = (texte or "").strip()
    m = _RE_ARTICLE.search(t)
    if m:
        return m.group(1)
    return t if t.isdigit() else ""


def source_division(d):
    """(source, officiel) d'une division d'après ses colonnes : article_aof / source_aof, sinon reference / note."""
    if d.get("source_aof"):
        return d["source_aof"], d["source_aof"].startswith("AOF")
    n = numero_article(d.get("article_aof") or d.get("reference"))
    if n:
        return S.SOURCE_AOF.format(n=n), True
    return S.SOURCE_GESCOL, False


def lignes_depuis_attributions(texte):
    """Une ligne d'action par puce (« - … ; », « • … ; », « 1. … ») du texte des attributions. Le signe de fin
    (« ; », « . ») est retiré et l'initiale mise en majuscule."""
    out = []
    for ligne in (texte or "").splitlines():
        m = _RE_PUCE.match(ligne)
        if not m:
            continue
        lib = m.group(1).strip().rstrip(";.,").strip()
        if len(lib) < 3:
            continue
        out.append(lib[0].upper() + lib[1:])
    return out


def _norm(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower().replace("œ", "oe").replace("é", "e").replace("è", "e")
                  .replace("ê", "e").replace("à", "a").replace("ç", "c")).strip()


def taux_effectif(ligne):
    """100 si réalisée, sinon le taux saisi (0 par défaut)."""
    if (ligne.get("etat") or "") == "réalisée":
        return 100
    try:
        return max(0, min(100, int(ligne.get("taux") or 0)))
    except (TypeError, ValueError):
        return 0


def synthese_lignes(lignes):
    """{total, realisees, en_cours, prevues, reportees, taux (moyenne des taux effectifs | None)}."""
    s = {"total": len(lignes), "realisees": 0, "en_cours": 0, "prevues": 0, "reportees": 0, "taux": None}
    for l in lignes:
        e = l.get("etat") or "prévue"
        cle = {"réalisée": "realisees", "en cours": "en_cours", "reportée": "reportees"}.get(e, "prevues")
        s[cle] += 1
    if lignes:
        s["taux"] = round(sum(taux_effectif(l) for l in lignes) / len(lignes), 1)
    return s


def pct(v):
    if v is None:
        return "—"
    return f"{int(v) if float(v).is_integer() else v} %"


def _modules_liste(valeur):
    """Colonne modules (JSON) → liste d'endpoints."""
    try:
        v = json.loads(valeur or "[]")
    except ValueError:
        return []
    return [x for x in v if isinstance(x, str)]


def _texte_para(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")


# ------------------------------------------------------------------------------------------ PDF divisions (rubriques)
def pdf_divisions(divs, s, annee=None):
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
             Paragraph(_texte_para(f"{(s or {}).get('nom') or ''} — année scolaire {annee or config.ANNEE_ACTIVE}"), st_s)]
    for d in divs:
        story.append(Paragraph(_texte_para(f"{d['sigle'] or ''} – {d['nom']}".strip(" –")), st_h))
        infos = [f"Chef : {d['responsable_nom'] or 'non désigné'}"]
        if d.get("signataire_titre"):
            infos.append(d["signataire_titre"])
        if d.get("parent_nom"):
            infos.append(f"Rattachement : {d['parent_nom']}")
        infos.append(f"Source : {d.get('source') or ''}")
        if d.get("agents"):
            infos.append(f"Agents affectés : {len(d['agents'])}")
        if d.get("synthese"):
            sy = d["synthese"]
            infos.append(f"Lignes d'action : {sy['realisees']} réalisée(s) / {sy['total']} ({pct(sy['taux'])})")
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
    H.schema(SCHEMA)
    H.ajouter_colonne("jur_services", "article_aof", "TEXT")
    H.ajouter_colonne("jur_services", "source_aof", "TEXT")

    def juridiction_ou_404():
        if not config.juridiction():
            abort(404)

    def annee_demandee(args):
        a = (args.get("annee") or "").strip()
        return a if re.match(r"^\d{4}-\d{4}$", a) else config.ANNEE_ACTIVE

    def annees_dispo():
        a = {r["annee"] for r in q("SELECT DISTINCT annee FROM jur_lignes_action")} | {config.ANNEE_ACTIVE}
        try:
            a |= set(H.jur_annees())
        except Exception:  # noqa: BLE001
            pass
        return sorted(a, reverse=True)

    # ---------------------------------------------------------------- rubriques
    def completer_sources():
        """Initialise article_aof / source_aof des services qui n'en ont pas (d'après reference / note)."""
        n = S.niveau()
        if not n:
            return
        for r in q("SELECT id, reference, note, article_aof, source_aof FROM jur_services WHERE niveau=? "
                   "AND (source_aof IS NULL OR source_aof='')", (n,)):
            num = numero_article(r["article_aof"] or r["reference"])
            if num:
                ex("UPDATE jur_services SET article_aof=?, source_aof=? WHERE id=?", (num, S.SOURCE_AOF.format(n=num), r["id"]))
            else:
                ex("UPDATE jur_services SET source_aof=? WHERE id=?", (S.SOURCE_GESCOL, r["id"]))

    def agents_par_service():
        out = {}
        for a in S.agents_structure():
            out.setdefault(a["service_code"] or "", []).append(a)
        return out

    def rubrique(d, noms=None):
        """Complète un service (dict) : chef, titre, parent, article, source, hors AOF."""
        d["chef_nom"] = d.get("responsable_nom") or ""
        if not d["chef_nom"] and d.get("responsable_id"):
            d["chef_nom"] = S.nom_agent(q("SELECT * FROM jur_agents WHERE id=?", (d["responsable_id"],), un=True))
        d["responsable_nom"] = d["chef_nom"]
        d["chef_titre"] = d.get("signataire_titre") or S.titre_service(d)
        d["source"], d["officiel"] = source_division(d)
        d["article"] = numero_article(d.get("article_aof") or d.get("reference")) if d["officiel"] else ""
        d["hors_aof"] = (not d["officiel"]) and S.niveau() == "cs" and d["code"] not in S.RACINE.values()
        d["racine"] = d["code"] == S.RACINE.get(S.niveau())
        if noms is not None:
            d["parent_nom"] = noms.get(d.get("parent_code") or "", "")
        else:
            p = S.service_par_code(d.get("parent_code")) if d.get("parent_code") else None
            d["parent_nom"] = (f"{p['sigle']} – {p['nom']}" if p and p.get("sigle") else (p["nom"] if p else ""))
        return d

    # ---------------------------------------------------------------- lignes d'action
    def lignes(code, annee):
        n = S.niveau()
        out = []
        for r in q("SELECT * FROM jur_lignes_action WHERE niveau=? AND service_code=? AND annee=? ORDER BY ordre, id",
                   (n, code, annee)):
            d = dict(r)
            d["modules_liste"] = _modules_liste(d["modules"])
            d["modules_libelles"] = [LIBELLES_MODULES.get(e, e) for e in d["modules_liste"]]
            d["taux_effectif"] = taux_effectif(d)
            out.append(d)
        return out

    def generer(d, annee, forcer=False):
        """Génère les lignes d'action depuis les puces des attributions. Au premier affichage de l'année (jamais
        généré) ou sur demande (forcer) : ajoute les attributions absentes, conserve le reste. Renvoie le nombre ajouté."""
        n, code = S.niveau(), d["code"]
        deja = q("SELECT 1 FROM jur_lignes_action_gen WHERE niveau=? AND service_code=? AND annee=?", (n, code, annee), un=True)
        if deja and not forcer:
            return 0
        existants = {_norm(r["libelle"]) for r in q("SELECT libelle FROM jur_lignes_action WHERE niveau=? AND service_code=? "
                                                   "AND annee=?", (n, code, annee))}
        ordre = (q("SELECT COALESCE(MAX(ordre),0) m FROM jur_lignes_action WHERE niveau=? AND service_code=? AND annee=?",
                   (n, code, annee), un=True)["m"] or 0)
        nb = 0
        for lib in lignes_depuis_attributions(d.get("attributions")):
            if _norm(lib) in existants:
                continue
            ordre += 1
            ex("INSERT INTO jur_lignes_action (niveau, service_code, annee, ordre, libelle, indicateur, cible, echeance, "
               "responsable, modules, etat, taux, observations, maj) VALUES (?,?,?,?,?,'','','',?,'[]','prévue',0,'',?)",
               (n, code, annee, ordre, lib[:500], d.get("chef_nom") or "", H.maintenant()))
            existants.add(_norm(lib))
            nb += 1
        ex("INSERT INTO jur_lignes_action_gen (niveau, service_code, annee, maj) VALUES (?,?,?,?) "
           "ON CONFLICT(niveau, service_code, annee) DO UPDATE SET maj=excluded.maj", (n, code, annee, H.maintenant()))
        return nb

    def divisions(annee, avec_lignes=True):
        """Divisions actives avec rubrique, modules, agents et synthèse des lignes d'action de l'année."""
        completer_sources()
        ag = agents_par_service()
        svcs = S.services()
        noms = {x["code"]: (f"{x['sigle']} – {x['nom']}" if x.get("sigle") else x["nom"]) for x in svcs}
        out = []
        for x in svcs:
            d = rubrique(dict(x), noms)
            d["modules"] = modules_division(app, x["code"])
            d["agents"] = ag.get(x["code"], [])
            if avec_lignes:
                generer(d, annee)
                d["lignes"] = lignes(x["code"], annee)
                d["synthese"] = synthese_lignes(d["lignes"])
            out.append(d)
        return out

    def comptes_division(code):
        """Comptes utilisateurs rattachés à la division : utilisateurs.service_code (prioritaire), sinon la fiche
        agent (jur_agents.user_id → service_code). Seuls les rôles chef_service / agent ont un périmètre."""
        cols = {c[1] for c in q("PRAGMA table_info(utilisateurs)")}
        out, vus = [], set()
        if "service_code" in cols:
            for u in q("SELECT * FROM utilisateurs WHERE actif=1 AND service_code=? ORDER BY nom", (code,)):
                out.append(dict(u, origine="compte", limite=u["role"] in ("chef_service", "agent")))
                vus.add(u["id"])
        for u in q("""SELECT u.* FROM jur_agents a JOIN utilisateurs u ON u.id=a.user_id
                      WHERE a.actif=1 AND a.service_code=? AND u.actif=1 ORDER BY u.nom""", (code,)):
            if u["id"] in vus or ("service_code" in cols and u["service_code"] and u["service_code"] != code):
                continue   # division du compte prioritaire sur celle de la fiche agent
            out.append(dict(u, origine="agent", limite=u["role"] in ("chef_service", "agent")))
            vus.add(u["id"])
        return out

    def division_ou_404(code, annee=None):
        completer_sources()
        d = S.service_par_code(code)
        if not d or not d["actif"]:
            abort(404)
        d = rubrique(dict(d))
        d["modules"] = modules_division(app, code)
        d["agents"] = agents_par_service().get(code, [])
        d["comptes"] = comptes_division(code)
        d["perimetre"] = H.perimetre_division(code) if getattr(H, "perimetre_division", None) else None
        if annee:
            generer(d, annee)
            d["lignes"] = lignes(code, annee)
            d["synthese"] = synthese_lignes(d["lignes"])
        return d

    def ligne_ou_404(lid):
        r = q("SELECT * FROM jur_lignes_action WHERE id=? AND niveau=?", (lid, S.niveau()), un=True)
        if not r:
            abort(404)
        return dict(r)

    def ecriture_requise():
        if not H.peut("jur_divisions"):
            abort(403)

    def lire_ligne_form(f, d):
        """Champs d'une ligne d'action depuis le formulaire (validation)."""
        lib = (f.get("libelle") or "").strip()[:500]
        if not lib:
            return None, "Le libellé de la ligne d'action est obligatoire."
        etat = f.get("etat") or "prévue"
        if etat not in ETATS:
            etat = "prévue"
        try:
            taux = max(0, min(100, int(float((f.get("taux") or "0").replace(",", ".")))))
        except ValueError:
            return None, "Le taux doit être un nombre entre 0 et 100."
        dispo = {m["endpoint"] for m in d["modules"]} | set(LIBELLES_MODULES)
        mods = [m for m in f.getlist("modules") if m in dispo]
        try:
            ordre = int(f.get("ordre") or 0)
        except ValueError:
            ordre = 0
        return {"ordre": ordre, "libelle": lib, "indicateur": (f.get("indicateur") or "").strip()[:300],
                "cible": (f.get("cible") or "").strip()[:200], "echeance": (f.get("echeance") or "").strip()[:80],
                "responsable": (f.get("responsable") or "").strip()[:150], "modules": json.dumps(mods, ensure_ascii=False),
                "etat": etat, "taux": taux, "observations": (f.get("observations") or "").strip()[:2000]}, None

    # ---------------------------------------------------------------- pages
    @app.route("/juridiction/divisions")
    @H.connexion_requise()
    def jur_divisions():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        divs = divisions(annee)
        toutes = [l for d in divs for l in d["lignes"]]
        return render_template("jur_divisions.html", divisions=divs, s=S.structure(), annee=annee, annees=annees_dispo(),
                               nb_modules=sum(len(d["modules"]) for d in divs), pct=pct,
                               nb_agents=sum(len(d["agents"]) for d in divs), racine=S.RACINE.get(S.niveau()),
                               synthese=synthese_lignes(toutes), AOF=S.AOF, modifiable=H.peut("jur_divisions"))

    @app.route("/juridiction/divisions/<code>", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_division(code):
        juridiction_ou_404()
        annee = annee_demandee(request.args if request.method == "GET" else request.form)
        d = division_ou_404(code, annee)
        if request.method == "POST":
            ecriture_requise()
            attr = (request.form.get("attributions") or "").strip()[:8000]
            ex("UPDATE jur_services SET attributions=? WHERE id=?", (attr, d["id"]))
            H.journal("jur_division_attributions", f"{code} {d['nom']}")
            flash("Attributions enregistrées.", "success")
            return redirect(url_for("jur_division", code=code, annee=annee))
        return render_template("jur_division.html", d=d, s=S.structure(), modifiable=H.peut("jur_divisions"), annee=annee,
                               annees=annees_dispo(), ETATS=ETATS, pct=pct, AOF=S.AOF)

    @app.route("/juridiction/divisions/<code>/aof", methods=["POST"])
    @H.connexion_requise("jur_divisions")
    def jur_division_aof(code):
        """Saisie du texte officiel de l'AOF : remplace les attributions rédigées, source = « AOF – article N »."""
        juridiction_ou_404()
        annee = annee_demandee(request.form)
        d = division_ou_404(code)
        num = numero_article(request.form.get("article"))
        attr = (request.form.get("attributions") or "").strip()[:8000]
        if not num or not attr:
            flash("Indiquez le numéro de l'article de l'AOF et collez le texte des attributions.", "danger")
            return redirect(url_for("jur_division", code=code, annee=annee) + "#rubrique")
        note = (d.get("note") or "").replace(S.HORS_AOF, "").replace(S.REDIGE, "").strip()    # mentions « rédigé » retirées
        ex("UPDATE jur_services SET attributions=?, article_aof=?, source_aof=?, reference=?, note=? WHERE id=?",
           (attr, num, S.SOURCE_AOF.format(n=num), f"Article {num}", note, d["id"]))
        H.journal("jur_division_aof", f"{code} article {num}")
        flash(f"Texte officiel enregistré : source « {S.SOURCE_AOF.format(n=num)} ». Vous pouvez régénérer les lignes d'action.", "success")
        return redirect(url_for("jur_division", code=code, annee=annee))

    @app.route("/juridiction/divisions/<code>/lignes/generer", methods=["POST"])
    @H.connexion_requise("jur_divisions")
    def jur_division_lignes_generer(code):
        juridiction_ou_404()
        annee = annee_demandee(request.form)
        d = division_ou_404(code)
        nb = generer(d, annee, forcer=True)
        H.journal("jur_lignes_action_generer", f"{code} {annee} +{nb}")
        flash(f"{nb} ligne(s) d'action ajoutée(s) depuis les attributions." if nb else
              "Toutes les attributions ont déjà leur ligne d'action.", "success" if nb else "info")
        return redirect(url_for("jur_division", code=code, annee=annee) + "#lignes")

    @app.route("/juridiction/divisions/<code>/lignes/nouvelle", methods=["GET", "POST"])
    @app.route("/juridiction/divisions/lignes/<int:lid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("jur_divisions")
    def jur_division_ligne_form(code=None, lid=None):
        juridiction_ou_404()
        l = ligne_ou_404(lid) if lid else None
        code = l["service_code"] if l else code
        annee = l["annee"] if l else annee_demandee(request.args if request.method == "GET" else request.form)
        d = division_ou_404(code)
        if request.method == "POST":
            vals, err = lire_ligne_form(request.form, d)
            if err:
                flash(err, "danger")
                return render_template("jur_division_ligne_form.html", d=d, l=l, v=request.form, annee=annee, ETATS=ETATS,
                                       modules=d["modules"], modules_choisis=request.form.getlist("modules")), 400
            if l:
                ex("UPDATE jur_lignes_action SET " + ", ".join(f"{k}=?" for k in vals) + ", maj=? WHERE id=?",
                   tuple(vals.values()) + (H.maintenant(), l["id"]))
                H.journal("jur_ligne_action_modifier", f"{code} #{l['id']}")
                flash("Ligne d'action modifiée.", "success")
            else:
                if not vals["ordre"]:
                    vals["ordre"] = (q("SELECT COALESCE(MAX(ordre),0) m FROM jur_lignes_action WHERE niveau=? AND service_code=? "
                                       "AND annee=?", (S.niveau(), code, annee), un=True)["m"] or 0) + 1
                ex("INSERT INTO jur_lignes_action (niveau, service_code, annee, " + ", ".join(vals) + ", maj) VALUES (?,?,?,"
                   + ",".join("?" * len(vals)) + ",?)", (S.niveau(), code, annee) + tuple(vals.values()) + (H.maintenant(),))
                H.journal("jur_ligne_action_ajouter", f"{code} {annee}")
                flash("Ligne d'action ajoutée.", "success")
            return redirect(url_for("jur_division", code=code, annee=annee) + "#lignes")
        v = dict(l) if l else {"etat": "prévue", "taux": 0, "responsable": d["chef_nom"]}
        return render_template("jur_division_ligne_form.html", d=d, l=l, v=v, annee=annee, ETATS=ETATS, modules=d["modules"],
                               modules_choisis=_modules_liste(l["modules"]) if l else [])

    @app.route("/juridiction/divisions/lignes/<int:lid>/suivi", methods=["POST"])
    @H.connexion_requise("jur_divisions")
    def jur_division_ligne_rapide(lid):
        """Mise à jour rapide depuis le tableau : état, taux, échéance, responsable, observations, ordre."""
        juridiction_ou_404()
        l = ligne_ou_404(lid)
        f = request.form
        etat = f.get("etat") if f.get("etat") in ETATS else l["etat"]
        try:
            taux = max(0, min(100, int(float((f.get("taux") or "0").replace(",", ".")))))
        except ValueError:
            taux = l["taux"] or 0
        try:
            ordre = int(f.get("ordre") or l["ordre"] or 0)
        except ValueError:
            ordre = l["ordre"] or 0
        ex("UPDATE jur_lignes_action SET etat=?, taux=?, ordre=?, echeance=?, responsable=?, observations=?, maj=? WHERE id=?",
           (etat, taux, ordre, (f.get("echeance") if f.get("echeance") is not None else l["echeance"] or "")[:80],
            (f.get("responsable") if f.get("responsable") is not None else l["responsable"] or "")[:150],
            (f.get("observations") if f.get("observations") is not None else l["observations"] or "")[:2000],
            H.maintenant(), lid))
        H.journal("jur_ligne_action_suivi", f"#{lid} {etat} {taux}%")
        flash("Suivi enregistré.", "success")
        return redirect(url_for("jur_division", code=l["service_code"], annee=l["annee"]) + "#lignes")

    @app.route("/juridiction/divisions/lignes/<int:lid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_divisions")
    def jur_division_ligne_supprimer(lid):
        juridiction_ou_404()
        l = ligne_ou_404(lid)
        ex("DELETE FROM jur_lignes_action WHERE id=?", (lid,))
        H.journal("jur_ligne_action_supprimer", f"{l['service_code']} #{lid} {l['libelle'][:60]}")
        flash("Ligne d'action supprimée.", "success")
        return redirect(url_for("jur_division", code=l["service_code"], annee=l["annee"]) + "#lignes")

    # ---------------------------------------------------------------- vue d'ensemble
    @app.route("/juridiction/divisions/plan")
    @H.connexion_requise()
    def jur_divisions_plan():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        divs = divisions(annee)
        toutes = [l for d in divs for l in d["lignes"]]
        return render_template("jur_divisions_plan.html", divisions=divs, s=S.structure(), annee=annee, annees=annees_dispo(),
                               synthese=synthese_lignes(toutes), pct=pct, modifiable=H.peut("jur_divisions"))

    # ---------------------------------------------------------------- exports
    def feuille_lignes(divs):
        rows = []
        for d in divs:
            for l in d["lignes"]:
                rows.append([f"{d['sigle'] or d['code'].upper()} – {d['nom']}", l["ordre"], l["libelle"], l["indicateur"] or "",
                             l["cible"] or "", l["echeance"] or "", l["responsable"] or "", " ; ".join(l["modules_libelles"]),
                             l["etat"] or "prévue", l["taux_effectif"], l["observations"] or ""])
        return rows

    def feuille_synthese(divs):
        rows = []
        for d in divs:
            sy = d["synthese"]
            rows.append([f"{d['sigle'] or d['code'].upper()} – {d['nom']}", d["article"] or "", d["source"], d["chef_nom"] or "",
                         sy["total"], sy["prevues"], sy["en_cours"], sy["realisees"], sy["reportees"],
                         sy["taux"] if sy["taux"] is not None else ""])
        return rows

    ENT_SYNTH = ["Division", "Article AOF", "Source", "Chef", "Lignes d'action", "Prévues", "En cours", "Réalisées", "Reportées",
                 "Taux (%)"]

    def haut(annee, titre):
        s = S.structure() or {}
        return [titre, f"{s.get('nom') or ''} — année scolaire {annee}"]

    @app.route("/juridiction/divisions/<code>/plan.xlsx")
    @H.connexion_requise()
    def jur_division_xlsx(code):
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        d = division_ou_404(code, annee)
        H.journal("jur_division_xlsx", f"{code} {annee}")
        return H.xlsx.reponse_classeur(f"plan_action_{code}_{annee}.xlsx",
                                       [("Lignes d'action", ENT_LIGNES, feuille_lignes([d]),
                                         {"titre_haut": haut(annee, f"Plan d'action — {d['sigle'] or ''} {d['nom']}")})])

    @app.route("/juridiction/divisions/plan.xlsx")
    @H.connexion_requise()
    def jur_divisions_plan_xlsx():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        divs = divisions(annee)
        toutes = synthese_lignes([l for d in divs for l in d["lignes"]])
        synth = feuille_synthese(divs) + [["TOTAL STRUCTURE", "", "", "", toutes["total"], toutes["prevues"], toutes["en_cours"],
                                           toutes["realisees"], toutes["reportees"], toutes["taux"] if toutes["taux"] is not None else ""]]
        H.journal("jur_divisions_plan_xlsx", annee)
        return H.xlsx.reponse_classeur(f"plan_action_divisions_{annee}.xlsx",
                                       [("Synthèse", ENT_SYNTH, synth, {"titre_haut": haut(annee, "Plan d'action des divisions")}),
                                        ("Lignes d'action", ENT_LIGNES, feuille_lignes(divs),
                                         {"titre_haut": haut(annee, "Plan d'action des divisions")})])

    def signataire_pdf(code=None):
        titre, nom, sig = S.jur_signataire(code)
        return (titre or "").upper(), nom or "", H.pdfs.image_data_url(sig) if sig else None

    def infos_haut():
        s = S.structure() or {}
        out = [("DDEMP", s.get("departement") or "")]
        if config.EDITION == "cs":
            out.append(("CS", s.get("cs") or ""))
        return out

    def pdf_plan(divs, annee, titre, sous_titre, code=None, ensemble=False):
        P = H.pdfs
        ent = ["N°", "Ligne d'action", "Indicateur", "Cible", "Échéance", "Responsable", "Modules GESCOL", "État", "Taux", "Observations"]
        rows, surlignes = [], {}
        for d in divs:
            if ensemble:
                surlignes[len(rows)] = "#E4ECF5"
                sy = d["synthese"]
                nom_div = _texte_para(f"{d['sigle'] or ''} – {d['nom']}")
                rows.append(["", P.paragraphe(f"<b>{nom_div}</b> — {_texte_para(d['source'])}", 7.5, espace=0),
                             "", "", "", d["chef_nom"] or "non désigné", "", f"{sy['realisees']} / {sy['total']}",
                             pct(sy["taux"]), ""])
            for l in d["lignes"]:
                rows.append([l["ordre"], l["libelle"], l["indicateur"] or "", l["cible"] or "", l["echeance"] or "",
                             l["responsable"] or "", "\n".join(l["modules_libelles"]), l["etat"] or "prévue",
                             pct(l["taux_effectif"]), l["observations"] or ""])
            if not d["lignes"] and not ensemble:
                rows.append(["", "Aucune ligne d'action pour cette année.", "", "", "", "", "", "", "", ""])
        if not rows:
            rows.append(["", "Aucune ligne d'action enregistrée.", "", "", "", "", "", "", "", ""])
        toutes = synthese_lignes([l for d in divs for l in d["lignes"]])
        total = ["", f"TOTAL : {toutes['total']} ligne(s) d'action", "", "", "", "", "", f"{toutes['realisees']} réalisée(s)",
                 pct(toutes["taux"]), ""]
        infos = [("Lignes d'action", toutes["total"]), ("Réalisées", toutes["realisees"]), ("En cours", toutes["en_cours"]),
                 ("Prévues / reportées", f"{toutes['prevues']} / {toutes['reportees']}"), ("Taux de réalisation", pct(toutes["taux"]))]
        apres = []
        if ensemble:
            apres = [P.paragraphe("Taux de réalisation par division", 9.5, True, espace=6),
                     P.mini_tableau([["Division", "Article AOF", "Chef", "Lignes", "Réalisées", "Taux"]] +
                                    [[f"{d['sigle'] or ''} – {d['nom']}", d["article"] or "—", d["chef_nom"] or "—", d["synthese"]["total"],
                                      d["synthese"]["realisees"], pct(d["synthese"]["taux"])] for d in divs] +
                                    [["TOTAL STRUCTURE", "", "", toutes["total"], toutes["realisees"], pct(toutes["taux"])]], taille=7.5)]
        else:
            d = divs[0]
            infos = [("Division", f"{d['sigle'] or ''} – {d['nom']}"), ("Article de l'AOF", d["article"] or "—"), ("Source", d["source"]),
                     ("Chef", d["chef_nom"] or "non désigné"), ("Rattachement", d["parent_nom"] or "—")] + infos
        titre_s, nom, img = signataire_pdf(None)          # responsable de la structure (CCS / Directeur départemental)
        sigs = [(titre_s, nom, img, True)]
        if code and code not in S.RACINE.values():       # + le chef de la division, à gauche
            t2, n2, i2 = signataire_pdf(code)
            sigs.insert(0, (t2, n2, i2, False))
        return P.document_tableau(titre, ent, rows, total=total, paysage=True, taille=7, largeurs=[5, 34, 18, 10, 11, 15, 22, 10, 8, 20],
                                  sous_titre=sous_titre, infos=infos, infos_haut=infos_haut(), apres=apres, signatures=sigs,
                                  surlignes=surlignes,
                                  notes_bas=["Une ligne d'action = une attribution de l'AOF (arrêté portant attributions, organisation "
                                             "et fonctionnement des structures déconcentrées du MEMP). Taux de réalisation = moyenne "
                                             "des taux des lignes (100 % pour une ligne réalisée)."])

    @app.route("/juridiction/divisions/<code>/plan.pdf")
    @H.connexion_requise()
    def jur_division_pdf(code):
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        d = division_ou_404(code, annee)
        s = S.structure() or {}
        pdf = pdf_plan([d], annee, "PLAN D'ACTION DE LA DIVISION", f"{d['sigle'] or ''} – {d['nom']} — {s.get('nom') or ''} — année scolaire {annee}", code)
        H.journal("jur_division_pdf", f"{code} {annee}")
        return H.pdf_reponse(pdf, f"plan_action_{code}_{annee}.pdf")

    @app.route("/juridiction/divisions/plan.pdf")
    @H.connexion_requise()
    def jur_divisions_plan_pdf():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        s = S.structure() or {}
        pdf = pdf_plan(divisions(annee), annee, "PLAN D'ACTION DES DIVISIONS", f"{s.get('nom') or ''} — année scolaire {annee}", None, True)
        H.journal("jur_divisions_plan_pdf", annee)
        return H.pdf_reponse(pdf, f"plan_action_divisions_{annee}.pdf")

    @app.route("/juridiction/divisions.pdf")
    @H.connexion_requise()
    def jur_divisions_pdf():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        H.journal("jur_divisions_pdf", "")
        return H.pdf_reponse(pdf_divisions(divisions(annee), S.structure(), annee), "divisions_modules_attributions.pdf")

    # ---------------------------------------------------------------- import Excel
    def importer(d, annee, ent, lignes_x):
        """Une ligne du fichier = une ligne d'action (même libellé → mise à jour, sinon ajout). Renvoie (ajouts, maj, erreurs)."""
        col = lambda *n: H.xlsx.colonne(ent, *n)  # noqa: E731
        i_lib = col("ligne d'action", "ligne d action", "libelle", "libellé", "attribution")
        if i_lib is None:
            return 0, 0, ["Colonne « Ligne d'action » introuvable."]
        i_ord, i_ind, i_cib = col("ordre", "n°", "no"), col("indicateur"), col("cible")
        i_ech, i_resp, i_mod = col("echeance", "échéance"), col("responsable"), col("modules")
        i_etat, i_taux, i_obs = col("etat", "état"), col("taux"), col("observations")
        libs = {_norm(lib): ep for ep, lib in LIBELLES_MODULES.items()}
        n = S.niveau()
        existants = {_norm(r["libelle"]): r["id"] for r in q("SELECT id, libelle FROM jur_lignes_action WHERE niveau=? AND "
                                                            "service_code=? AND annee=?", (n, d["code"], annee))}
        ordre_max = max([0] + [r["ordre"] or 0 for r in q("SELECT ordre FROM jur_lignes_action WHERE niveau=? AND service_code=? "
                                                         "AND annee=?", (n, d["code"], annee))])
        ajouts, maj, err = 0, 0, []
        for num, l in enumerate(lignes_x, start=2):
            v = lambda i: H.xlsx.valeur(l, i)  # noqa: E731
            lib = v(i_lib)[:500]
            if not lib or lib.upper().startswith("TOTAL") or lib.startswith("Aucune ligne"):
                continue
            etat = v(i_etat).lower().strip()
            etat = {"realisee": "réalisée", "réalisée": "réalisée", "en cours": "en cours", "reportee": "reportée", "reportée": "reportée",
                    "prevue": "prévue", "prévue": "prévue"}.get(etat, "prévue" if not etat else None)
            if etat is None:
                err.append(f"Ligne {num} : état « {v(i_etat)} » inconnu (prévue, en cours, réalisée, reportée).")
                continue
            t = v(i_taux).replace(",", ".").replace("%", "").strip()
            try:
                taux = max(0, min(100, int(float(t)))) if t else 0
            except ValueError:
                err.append(f"Ligne {num} : taux « {v(i_taux)} » invalide.")
                continue
            mods = [libs[_norm(x)] for x in re.split(r"[;\n|]", v(i_mod)) if _norm(x) in libs] if i_mod is not None else []
            o = v(i_ord)
            ordre = int(float(o)) if re.match(r"^\d+(\.0+)?$", o) else None
            vals = {"libelle": lib, "indicateur": v(i_ind)[:300], "cible": v(i_cib)[:200], "echeance": v(i_ech)[:80],
                    "responsable": v(i_resp)[:150], "modules": json.dumps(mods, ensure_ascii=False), "etat": etat, "taux": taux,
                    "observations": v(i_obs)[:2000]}
            lid = existants.get(_norm(lib))
            if lid:
                if ordre is not None:
                    vals["ordre"] = ordre
                ex("UPDATE jur_lignes_action SET " + ", ".join(f"{k}=?" for k in vals) + ", maj=? WHERE id=?",
                   tuple(vals.values()) + (H.maintenant(), lid))
                maj += 1
            else:
                if ordre is None:
                    ordre_max += 1
                    ordre = ordre_max
                vals["ordre"] = ordre
                nid = ex("INSERT INTO jur_lignes_action (niveau, service_code, annee, " + ", ".join(vals) + ", maj) VALUES (?,?,?,"
                         + ",".join("?" * len(vals)) + ",?)", (n, d["code"], annee) + tuple(vals.values()) + (H.maintenant(),))
                existants[_norm(lib)] = nid
                ajouts += 1
        ex("INSERT INTO jur_lignes_action_gen (niveau, service_code, annee, maj) VALUES (?,?,?,?) "
           "ON CONFLICT(niveau, service_code, annee) DO UPDATE SET maj=excluded.maj", (n, d["code"], annee, H.maintenant()))
        return ajouts, maj, err

    @app.route("/juridiction/divisions/<code>/lignes/import", methods=["GET", "POST"])
    @H.connexion_requise("jur_divisions")
    def jur_division_import(code):
        juridiction_ou_404()
        annee = annee_demandee(request.args if request.method == "GET" else request.form)
        d = division_ou_404(code)
        if request.args.get("modele"):
            ex_ = [[f"{d['sigle'] or ''} – {d['nom']}", 1, "Traiter le courrier à l'arrivée et au départ", "Nombre de courriers enregistrés",
                    "100 %", "Toute l'année", d["chef_nom"] or "Chef de division", LIBELLES_MODULES.get("courrier", ""), "en cours", 50, ""],
                   [f"{d['sigle'] or ''} – {d['nom']}", 2, "Tenir et classer les archives", "Registre à jour", "Trimestriel", "2027-06-30",
                    "", LIBELLES_MODULES.get("archives", ""), "prévue", 0, ""]]
            return H.xlsx.reponse_xlsx(f"modele_plan_action_{code}.xlsx", ENT_LIGNES, ex_, "Lignes d'action",
                                       ["Modèle d'import des lignes d'action : une ligne par attribution. État : prévue, en cours, "
                                        "réalisée ou reportée ; taux de 0 à 100 ; modules : libellés GESCOL séparés par « ; »."])
        if request.method == "POST":
            fic = request.files.get("fichier")
            if not fic or not fic.filename.lower().endswith((".xlsx", ".csv")):
                flash("Choisissez un fichier Excel (.xlsx).", "danger")
                return redirect(url_for("jur_division_import", code=code, annee=annee))
            try:
                ent, lignes_x = H.xlsx.lire_tableau(fic, ("ligne d'action", "libellé", "libelle"))
            except H.xlsx.ExcelIndisponible as e_:
                flash(str(e_), "danger")
                return redirect(url_for("jur_division_import", code=code, annee=annee))
            except Exception:  # noqa: BLE001
                flash("Fichier Excel illisible.", "danger")
                return redirect(url_for("jur_division_import", code=code, annee=annee))
            ajouts, maj, err = importer(d, annee, ent, lignes_x)
            for m in err[:15]:
                flash(m, "warning")
            flash(f"{ajouts} ligne(s) d'action ajoutée(s), {maj} mise(s) à jour.", "success" if (ajouts or maj) else "warning")
            H.journal("jur_division_import", f"{code} {annee} +{ajouts} ~{maj}")
            return redirect(url_for("jur_division", code=code, annee=annee) + "#lignes")
        return render_template("jur_division_import.html", d=d, annee=annee, annees=annees_dispo())

    H.jur_lignes_action = lignes
    H.jur_divisions = divisions
