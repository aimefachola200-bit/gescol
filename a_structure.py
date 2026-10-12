# -*- coding: utf-8 -*-
"""Services, cachets et documents administratifs des applications « GESCOL Circonscription » (CS) et « GESCOL DDEMP ».

1. Services et attributions (/juridiction/services) : services par défaut du niveau (CS : articles 9 à 14 du texte
   officiel des attributions ; DDEMP : services départementaux), ajout d'un service oublié, modification,
   désactivation, responsable choisi parmi les agents (jur_agents), organigramme SVG (DDEMP → services → CS →
   divisions → zones pédagogiques → écoles, avec les nombres), export PDF de l'organigramme et des attributions.
2. Cachets et signatures (/juridiction/cachets) : cachet de la structure et de chaque service (texte haut / bas /
   centre, couleur), aperçu SVG / PDF, signature digitale (clés jur:service:<id>, jur:structure:responsable).
   Griffe (cachet rectangulaire du nom, cachet.dessiner_nom) préconçue pour la structure et chaque service : composée
   automatiquement du titre et du nom du signataire ; réglages dans jur_docs_parametres (griffe_actif, griffe_ligne3,
   griffe_couleur ; par service : griffe_<code>_actif / _ligne3 / _couleur), aperçu /juridiction/cachets/griffe.svg.
   Fonctions exposées : H.jur_cachet(code|None) → (sup, inf, centre, couleur) ;
   H.jur_signataire(code|None) → (titre, nom, signature_dataurl) ; H.jur_griffe(code|None) → (lignes, couleur) | None.
3. Attestations et certificats (/juridiction/documents) : reproduction des modèles du client (présence au poste,
   direction, travail, prise / reprise de service, prise en charge, certificats des AME), pré-remplis depuis le
   personnel de la juridiction, numérotés au registre annuel « SO N° …/CS-…/DDEMP-…/SP », signés et cachetés,
   avec QR de vérification, historique et réimpression, version vierge.
"""
import io
import json
import re
from datetime import date, datetime

from flask import Response, abort, flash, g, redirect, render_template, request, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph

import cachet as CACHET
import config
import m_docs_enseignant as DE          # primitives de dessin des certificats officiels (lecture seule)
import pdfs
from pdfs import GCanvas
from db import ex, q

W, H_PAGE = A4

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_docs_parametres (
    cle TEXT PRIMARY KEY, valeur TEXT, maj TEXT);
CREATE TABLE IF NOT EXISTS jur_docs_historique (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    annee TEXT NOT NULL, type TEXT NOT NULL,
    numero INTEGER,                 -- numéro d'ordre au registre annuel (SO N°)
    ref TEXT,                       -- référence complète imprimée
    personne TEXT,                  -- clé de la personne (e<école>-<n> | a<agent>) ou ''
    libelle TEXT NOT NULL,
    donnees TEXT NOT NULL,          -- valeurs imprimées (JSON) : réimpression à l'identique
    code TEXT,                      -- code de vérification (QR)
    signe INTEGER DEFAULT 0, signataire TEXT,
    cree_le TEXT NOT NULL, cree_par INTEGER);
CREATE INDEX IF NOT EXISTS i_jur_docs_hist ON jur_docs_historique(annee, numero);
"""

# ================================================================================================ services par défaut
ART_9 = ("Article 9 : Le Chef de la Circonscription Scolaire (CCS) est nommé par arrêté du Ministre des Enseignements "
         "Maternel et Primaire sur proposition conjointe du Directeur de l'Inspection et de l'Innovation Pédagogiques, "
         "de la Directrice de l'Enseignement Maternel, du Directeur de l'Enseignement Primaire et du Directeur de la "
         "Planification, de l'Administration et des Finances.\n"
         "Article 10 (1er alinéa) : Le Chef de la Circonscription Scolaire (CCS), dans son ressort territorial, est "
         "assisté pour les activités du secrétariat par la Division du Secrétariat.")
ART_10 = ("La Division du Secrétariat a pour attributions de :\n"
          "• traiter le courrier à l'arrivée et au départ ;\n"
          "• saisir les correspondances et les actes administratifs ;\n"
          "• recenser les préoccupations des enseignants et autres usagers de l'école pour compte rendu au CCS ;\n"
          "• tenir et classer les archives ;\n"
          "• ventiler le courrier conformément aux instructions du CCS ;\n"
          "• exécuter toutes autres tâches à lui confiées dans le cadre du service public par son supérieur "
          "hiérarchique.")
ART_11 = ("La Division de l'Animation Pédagogique est chargée de :\n"
          "- assurer les activités de visites d'école et de visites d'inspection de classe dans les écoles du ressort "
          "de son territoire administratif ;\n"
          "- mettre en œuvre les formations des enseignants des écoles maternelles et primaires ;\n"
          "- élaborer la liste d'aptitude aux fonctions de directeur d'école ;\n"
          "- participer à l'organisation et à la gestion des examens et concours ;\n"
          "- suivre le respect de l'emploi du temps et la bonne gestion du calendrier scolaire.")
ART_12 = ("La Division de l'Administration et des Finances est chargée de :\n"
          "- l'organisation administrative des services de la Circonscription Scolaire conformément aux instructions "
          "du Chef de la Circonscription Scolaire ;\n"
          "- la gestion du personnel et la préparation des actes administratifs ;\n"
          "- la tenue des dossiers du personnel ;\n"
          "- l'établissement des états d'effectifs du personnel et de leur mise à jour régulière ;\n"
          "- collaborer à l'opérationnalisation du mouvement des personnels enseignants et administratifs affectés "
          "dans la Circonscription Scolaire ;\n"
          "- l'exécution des crédits délégués, des ressources ;\n"
          "- exécuter toutes les tâches de nature administrative et financière.")
ART_13 = ("La Division de l'Organisation Scolaire et de la Prévision est chargée de :\n"
          "- réceptionner et acheminer les points de rentrée et les rapports de fin d'année ;\n"
          "- préparer les documents de suivi et évaluation de la circonscription scolaire ;\n"
          "- renforcer les capacités des acteurs locaux.")
ART_14 = ("Article 14 : Les Chefs de Division de la Circonscription Scolaire (CS) sont nommés par le Chef de la "
          "Circonscription Scolaire (CCS) parmi les agents de l'État autres que les Conseillers Pédagogiques et les "
          "Inspecteurs.")
REDIGE = "Attributions rédigées par GESCOL (non reprises du texte officiel) : à adapter par la structure."
# v1.6 — rubriques des divisions (a_divisions). AOF = arrêté portant Attributions, Organisation et Fonctionnement des
# structures déconcentrées du MEMP (Circonscriptions scolaires, Directions départementales). Les textes des articles
# 9 à 14 (CS) sont repris ci-dessus ; les autres attributions ont été rédigées par GESCOL faute du texte officiel.
AOF = "Arrêté portant attributions, organisation et fonctionnement des structures déconcentrées du MEMP (AOF)"
SOURCE_AOF = "AOF – article {n}"
SOURCE_GESCOL = "Rédigé par GESCOL, à conformer à l'AOF"
HORS_AOF = ("Service hors AOF : les articles 10 à 13 de l'AOF ne prévoient que quatre divisions pour la CS ; ce service "
            "est conservé parce que la structure y fait référence, en attendant la saisie du texte officiel. ")
# v1.6 – Service des Ressources Humaines de la CS (ex-CSPAF) : le personnel des écoles (directeurs, enseignants,
# personnel de soutien) y est suivi avec les agents de la circonscription.
ATTR_RH_CS = ("Le Service des Ressources Humaines est chargé de :\n"
              "- tenir à jour le fichier et les dossiers individuels du personnel de la circonscription et des écoles "
              "(directeurs, enseignants, personnel de soutien) ;\n"
              "- établir et actualiser les états d'effectifs du personnel des écoles (par catégorie, grade, école et zone "
              "pédagogique) et évaluer les besoins en enseignants ;\n"
              "- préparer les actes de gestion courante (prises et reprises de service, attestations, certificats, congés, "
              "permissions) et les propositions d'avancement ;\n"
              "- suivre les carrières (avancements, reclassements, évaluations, visites d'aptitude, diplômes), les "
              "mutations et les départs à la retraite ;\n"
              "- gérer les comptes GESCOL des directeurs et des enseignants et leurs affectations aux classes ;\n"
              "- rendre compte au CCS de la situation du personnel.")
# anciens libellés du service « personnel » (renommés par assurer_services)
ANCIENS_NOMS_RH = ("Service du Personnel et des Affaires financières",)
ANCIENS_SIGLES_RH = ("CSPAF", "SPAF")

# (code, nom, sigle, ordre, parent, référence, attributions, note, titre du signataire)
SERVICES_DEFAUT = {
    "cs": [
        ("ccs", "Chef de la Circonscription Scolaire", "CCS", 1, "", "Article 9", ART_9, ART_14,
         "Le Chef de la Circonscription Scolaire"),
        ("cp", "Conseillers pédagogiques", "CP", 2, "ccs", "", (
            "Les Conseillers pédagogiques, placés sous l'autorité du Chef de la Circonscription Scolaire et en "
            "liaison avec la Division de l'Animation Pédagogique, sont chargés de :\n"
            "- assurer l'encadrement pédagogique des enseignants des écoles de leur zone pédagogique ;\n"
            "- effectuer les visites de classe, de conseil et d'aptitude ;\n"
            "- animer les unités pédagogiques (UP) et les regroupements de formation ;\n"
            "- suivre l'exécution des programmes, de l'emploi du temps et du calendrier scolaire ;\n"
            "- rendre compte au CCS de leurs activités (rapports de visites, bilans périodiques)."),
         REDIGE, "Le Conseiller Pédagogique"),
        ("secretariat", "Division du Secrétariat", "CDS", 3, "ccs", "Article 10", ART_10, "",
         "Le Chef de la Division du Secrétariat"),
        # v1.6 : « le personnel de l'école au RH de la CS » — l'ancien Service du Personnel et des Affaires
        # financières (CSPAF) devient le Service des Ressources Humaines (RH) ; les affaires financières relèvent de la
        # Division de l'Administration et des Finances (CDAF). Code inchangé (« personnel ») : les agents, lignes
        # d'action et comptes déjà rattachés sont conservés ; assurer_services() renomme le service existant.
        ("personnel", "Service des Ressources Humaines", "RH", 4, "ccs", "", ATTR_RH_CS, HORS_AOF + REDIGE,
         "Le Chef du Service des Ressources Humaines"),
        ("animation", "Division de l'Animation Pédagogique", "CDAP", 5, "ccs", "Article 11", ART_11, "",
         "Le Chef de la Division de l'Animation Pédagogique"),
        ("administration", "Division de l'Administration et des Finances", "CDAF", 6, "ccs", "Article 12", ART_12, "",
         "Le Chef de la Division de l'Administration et des Finances"),
        ("organisation", "Division de l'Organisation Scolaire et de la Prévision", "CDOSP", 7, "ccs", "Article 13",
         ART_13, "", "Le Chef de la Division de l'Organisation Scolaire et de la Prévision"),
    ],
    "ddemp": [
        ("direction", "Directeur départemental", "DDEMP", 1, "", "", (
            "Le Directeur départemental des Enseignements Maternel et Primaire représente le Ministre dans le "
            "département. À ce titre, il est chargé de :\n"
            "- mettre en œuvre la politique du Ministère en matière d'enseignement maternel et primaire ;\n"
            "- coordonner, animer et contrôler les services départementaux et les Circonscriptions scolaires (CS) du "
            "département, qui relèvent directement de son autorité ;\n"
            "- assurer la gestion des personnels enseignants et administratifs du département ;\n"
            "- veiller à l'organisation de la rentrée, des examens et concours et au respect du calendrier scolaire ;\n"
            "- rendre compte périodiquement au Ministre de la situation de l'enseignement dans le département."),
         "Les Circonscriptions scolaires du département dépendent directement du Directeur départemental ; "
         "elles transmettent leurs données à la DDEMP (paquets de transmission). " + REDIGE,
         "Le Directeur Départemental"),
        ("sec", "Service des Examens et Concours", "SEC", 2, "direction", "", (
            "Le Service des Examens et Concours est chargé de :\n"
            "- organiser, en liaison avec les Circonscriptions scolaires, le Certificat d'Études Primaires (CEP) et "
            "les examens et concours professionnels (CEAP, CAP) ;\n"
            "- recenser les candidats, constituer les centres d'examen et désigner les chefs de centre ;\n"
            "- assurer la sécurité des épreuves, la correction, la délibération et la proclamation des résultats ;\n"
            "- établir les statistiques des examens et délivrer les relevés de notes et attestations de réussite."),
         REDIGE, "Le Chef du Service des Examens et Concours"),
        ("semp", "Service des Écoles Maternelles et Primaires", "SEMP", 3, "direction", "", (
            "Le Service des Écoles Maternelles et Primaires est chargé de :\n"
            "- suivre le fonctionnement pédagogique et administratif des écoles maternelles et primaires publiques "
            "et privées ;\n"
            "- coordonner l'action des Circonscriptions scolaires et l'encadrement pédagogique (CP, CCS) ;\n"
            "- instruire les dossiers d'ouverture, d'extension et de contrôle des écoles privées ;\n"
            "- suivre la mise en œuvre des programmes et la formation continue des enseignants."),
         REDIGE, "Le Chef du Service des Écoles Maternelles et Primaires"),
        ("srh", "Service des Ressources Humaines", "SRH", 4, "direction", "", (
            "Le Service des Ressources Humaines est chargé de :\n"
            "- tenir le fichier départemental du personnel et les dossiers individuels ;\n"
            "- préparer les actes d'affectation, de mutation, de prise et de reprise de service ;\n"
            "- suivre les carrières (avancements, reclassements, évaluations, départs à la retraite) ;\n"
            "- évaluer les besoins en personnel enseignant et proposer leur répartition entre les Circonscriptions "
            "scolaires."),
         REDIGE, "Le Chef du Service des Ressources Humaines"),
        ("spaf", "Service de la Planification, de l'Administration et des Finances", "SPAF", 5, "direction", "", (
            "Le Service de la Planification, de l'Administration et des Finances est chargé de :\n"
            "- élaborer le plan de travail annuel et le budget de la Direction départementale ;\n"
            "- exécuter les crédits délégués et tenir la comptabilité administrative et matières ;\n"
            "- assurer la gestion du courrier, des archives et du matériel ;\n"
            "- préparer la carte scolaire et les prévisions d'effectifs, en liaison avec le Service des Statistiques."),
         REDIGE, "Le Chef du Service de la Planification, de l'Administration et des Finances"),
        ("cantines", "Service de gestion des Cantines scolaires", "SCS", 6, "direction", "", (
            "Le Service de gestion des Cantines scolaires est chargé de :\n"
            "- recenser les écoles bénéficiaires et le nombre d'élèves nourris ;\n"
            "- suivre l'approvisionnement, le stockage et la distribution des vivres ;\n"
            "- contrôler la gestion des contributions et le fonctionnement des comités de gestion ;\n"
            "- produire les rapports périodiques sur l'alimentation scolaire."),
         REDIGE, "Le Chef du Service de gestion des Cantines scolaires"),
        ("statistiques", "Service des Statistiques", "SSTAT", 7, "direction", "", (
            "Le Service des Statistiques est chargé de :\n"
            "- collecter, contrôler et traiter les données statistiques des écoles (recensement scolaire, points de "
            "rentrée, rapports de fin d'année) ;\n"
            "- produire l'annuaire statistique et les tableaux de bord du département ;\n"
            "- calculer les indicateurs (taux de scolarisation, de réussite, ratios élèves / maître) ;\n"
            "- mettre les données à la disposition des services et des Circonscriptions scolaires."),
         REDIGE, "Le Chef du Service des Statistiques"),
        ("infrastructures", "Service des Infrastructures et équipements", "SIE", 8, "direction", "", (
            "Le Service des Infrastructures et équipements est chargé de :\n"
            "- tenir l'inventaire des infrastructures scolaires (salles de classe, latrines, points d'eau) et des "
            "équipements (tables-bancs, mobilier) ;\n"
            "- identifier les besoins de construction, de réhabilitation et d'équipement ;\n"
            "- suivre l'exécution des travaux et la réception des ouvrages ;\n"
            "- veiller à l'entretien du patrimoine scolaire."),
         REDIGE, "Le Chef du Service des Infrastructures et équipements"),
    ],
}
RACINE = {"cs": "ccs", "ddemp": "direction"}
COULEURS = {"bleu": "Bleu", "rouge": "Rouge"}
# Article devant le nom du département (« département du Plateau », « de l'Atlantique »…)
DEP_DE = {"Alibori": "de l'", "Atacora": "de l'", "Atlantique": "de l'", "Borgou": "du ", "Collines": "des ",
          "Couffo": "du ", "Donga": "de la ", "Littoral": "du ", "Mono": "du ", "Ouémé": "de l'", "Plateau": "du ",
          "Zou": "du "}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def niveau():
    return config.EDITION if config.EDITION in ("cs", "ddemp") else None


def structure():
    try:
        r = q("SELECT * FROM jur_structure WHERE id=1", un=True)
    except Exception:  # noqa: BLE001
        return None
    return dict(r) if r else None


def param(cle, defaut=None):
    r = q("SELECT valeur FROM jur_docs_parametres WHERE cle=?", (cle,), un=True)
    if not r:
        return defaut
    try:
        return json.loads(r["valeur"])
    except ValueError:
        return defaut


def param_ecrire(cle, valeur):
    ex("INSERT INTO jur_docs_parametres (cle, valeur, maj) VALUES (?,?,?) ON CONFLICT(cle) DO UPDATE SET "
       "valeur=excluded.valeur, maj=excluded.maj", (cle, json.dumps(valeur, ensure_ascii=False), _now()))


# ================================================================================================ services : accès
def cs_courante():
    s = structure()
    if not s or s["niveau"] != "cs":
        return None
    return q("SELECT * FROM jur_cs WHERE departement=? AND nom=?", (s["departement"], s["cs"]), un=True)


def agents_structure():
    """Agents de la structure elle-même (responsables possibles des services)."""
    n = niveau()
    if n == "cs":
        c = cs_courante()
        return q("SELECT * FROM jur_agents WHERE actif=1 AND (cs_id IS NULL OR cs_id=?) ORDER BY nom, prenoms",
                 (c["id"] if c else 0,))
    return q("SELECT * FROM jur_agents WHERE actif=1 AND cs_id IS NULL ORDER BY nom, prenoms")


def nom_agent(a):
    if not a:
        return ""
    return f"{a['prenoms'] or ''} {a['nom'] or ''}".strip()


def _responsable_auto(code, agents):
    """Agent à désigner par défaut comme responsable d'un service (d'après service_code et poste)."""
    cands = [a for a in agents if (a["service_code"] or "") == code]
    if code == "cp":
        cands = [a for a in agents if "conseiller" in (a["poste"] or "").lower()]
    if code in ("ccs", "direction"):
        cands = cands or [a for a in agents if (a["service_code"] or "") in ("ccs", "direction")]
    for mot in ("chef", "directeur"):
        for a in cands:
            if mot in (a["poste"] or "").lower():
                return a["id"]
    return cands[0]["id"] if cands and code == "cp" else (cands[0]["id"] if len(cands) == 1 else None)


def renommer_service_rh():
    """v1.6 (CS) : le service « personnel » encore nommé « Service du Personnel et des Affaires financières » (CSPAF)
    devient « Service des Ressources Humaines » (RH) : nom, sigle, titre du signataire ; les attributions ne sont
    remplacées que si elles n'ont pas été modifiées (texte rédigé d'origine)."""
    if niveau() != "cs":
        return
    r = q("SELECT * FROM jur_services WHERE niveau='cs' AND code='personnel'", un=True)
    if not r or not ((r["nom"] or "").strip() in ANCIENS_NOMS_RH or (r["sigle"] or "").strip().upper() in ANCIENS_SIGLES_RH):
        return
    defaut = next(s for s in SERVICES_DEFAUT["cs"] if s[0] == "personnel")
    attr = r["attributions"] or ""
    if attr.startswith("Le Service du Personnel et des Affaires financières") or not attr.strip():
        attr = defaut[6]
    cols = {c[1] for c in q("PRAGMA table_info(jur_services)")}
    sql = "UPDATE jur_services SET nom=?, sigle=?, attributions=?"
    args = [defaut[1], defaut[2], attr]
    if "signataire_titre" in cols:
        sql += ", signataire_titre=?"
        args.append(defaut[8])
    ex(sql + " WHERE id=?", args + [r["id"]])


def assurer_services():
    """Crée les services par défaut du niveau s'ils sont absents (jamais d'écrasement des modifications) ;
    v1.6 : renomme le service CSPAF de la CS en Service des Ressources Humaines (renommer_service_rh)."""
    n = niveau()
    if not n:
        return
    renommer_service_rh()
    existants = {r["code"] for r in q("SELECT code FROM jur_services WHERE niveau=?", (n,))}
    manquants = [s for s in SERVICES_DEFAUT[n] if s[0] not in existants]
    if not manquants:
        return
    agents = agents_structure()
    for code, nom, sigle, ordre, parent, ref, attr, note, titre in manquants:
        ex("INSERT OR IGNORE INTO jur_services (niveau, code, nom, sigle, attributions, ordre, responsable_id, actif, "
           "parent_code, reference, note, signataire_titre) VALUES (?,?,?,?,?,?,?,1,?,?,?,?)",
           (n, code, nom, sigle, attr, ordre, _responsable_auto(code, agents), parent, ref, note, titre))


def services(actifs=True):
    n = niveau()
    if not n:
        return []
    assurer_services()
    rows = q("SELECT s.*, a.nom ag_nom, a.prenoms ag_prenoms, a.telephone ag_tel FROM jur_services s "
             "LEFT JOIN jur_agents a ON a.id=s.responsable_id WHERE s.niveau=?" + (" AND s.actif=1" if actifs else "") +
             " ORDER BY s.ordre, s.id", (n,))
    out = []
    for r in rows:
        d = dict(r)
        d["responsable_nom"] = f"{r['ag_prenoms'] or ''} {r['ag_nom'] or ''}".strip()
        d["defaut"] = r["code"] in {s[0] for s in SERVICES_DEFAUT[n]}
        out.append(d)
    return out


def service_par_code(code):
    n = niveau()
    if not n or not code:
        return None
    assurer_services()
    r = q("SELECT * FROM jur_services WHERE niveau=? AND code=?", (n, code), un=True)
    return dict(r) if r else None


def service_par_id(sid):
    n = niveau()
    r = q("SELECT * FROM jur_services WHERE niveau=? AND id=?", (n, sid), un=True) if n else None
    return dict(r) if r else None


# ================================================================================================ cachets / signataires
def _maj(t):
    return (t or "").upper()


def cachet_structure_defaut(s=None):
    s = s or structure() or {}
    dep, cs = _maj(s.get("departement")), _maj(s.get("cs"))
    if niveau() == "cs" or s.get("niveau") == "cs":
        return ("RÉPUBLIQUE DU BÉNIN – MEMP", f"CIRCONSCRIPTION SCOLAIRE DE {cs}".strip(), "LE CHEF|DE LA CS", "bleu")
    return ("RÉPUBLIQUE DU BÉNIN – MEMP", f"DDEMP {dep}".strip(), "LE DIRECTEUR|DÉPARTEMENTAL", "bleu")


def cachet_structure():
    v = param("cachet_structure")
    if v and (v.get("sup") or v.get("centre")):
        return (v.get("sup", ""), v.get("inf", ""), v.get("centre", ""), v.get("couleur") or "bleu")
    return cachet_structure_defaut()


def cachet_service_defaut(svc, s=None):
    """Cachet automatique d'un service : nom de la structure en haut, tutelle en bas, sigle du service au centre."""
    s = s or structure() or {}
    dep, cs = _maj(s.get("departement")), _maj(s.get("cs"))
    if niveau() == "cs":
        haut, bas = f"CIRCONSCRIPTION SCOLAIRE DE {cs}".strip(), f"DDEMP {dep}".strip()
    else:
        haut, bas = f"DDEMP {dep}".strip(), "RÉPUBLIQUE DU BÉNIN – MEMP"
    return (haut, bas, _maj(svc["sigle"] or svc["code"]), "bleu")


def jur_cachet(code=None):
    """(sup, inf, centre, couleur) du cachet de la structure (code None, 'ccs', 'direction') ou d'un service."""
    if code and code not in RACINE.values():
        svc = service_par_code(code)
        if svc:
            if svc.get("cachet_sup") or svc.get("cachet_centre"):
                return (svc["cachet_sup"] or "", svc["cachet_inf"] or "", svc["cachet_centre"] or "",
                        svc["cachet_couleur"] or "bleu")
            return cachet_service_defaut(svc)
    return cachet_structure()


def titre_responsable(s=None):
    s = s or structure() or {}
    return s.get("responsable_titre") or ("Le Chef de la Circonscription Scolaire" if niveau() == "cs"
                                          else "Le Directeur Départemental")


def signature(cle):
    r = q("SELECT image FROM signatures WHERE cle=?", (cle,), un=True)
    return r["image"] if r else None


def jur_signataire(code=None):
    """(titre, nom, signature data URL | None) du signataire : responsable de la structure ou chef d'un service."""
    s = structure() or {}
    if not code or code in RACINE.values():
        nom = s.get("responsable_nom") or ""
        racine = service_par_code(RACINE.get(niveau() or "", "")) if niveau() else None
        if not nom and racine and racine.get("responsable_id"):
            nom = nom_agent(q("SELECT * FROM jur_agents WHERE id=?", (racine["responsable_id"],), un=True))
        sig = signature("jur:structure:responsable")
        if not sig and racine:
            sig = signature(f"jur:service:{racine['id']}")
        return titre_responsable(s), nom, sig
    svc = service_par_code(code)
    if not svc:
        return jur_signataire(None)
    a = q("SELECT * FROM jur_agents WHERE id=?", (svc["responsable_id"],), un=True) if svc["responsable_id"] else None
    sig = signature(f"jur:service:{svc['id']}") or (signature(f"jur:agent:{a['id']}") if a else None)
    return (svc.get("signataire_titre") or titre_service(svc)), nom_agent(a), sig


def griffe_cle(code, suffixe):
    """Clé de paramètre de la griffe : structure (code None / racine) ou service."""
    if not code or code in RACINE.values():
        return f"griffe_{suffixe}"
    return f"griffe_{code}_{suffixe}"


def jur_griffe_reglages(code=None):
    """{actif, ligne3, couleur} de la griffe (valeurs enregistrées, sinon défauts : active, sans 3e ligne,
    couleur du cachet)."""
    actif = param(griffe_cle(code, "actif"))
    return {"actif": 1 if actif is None else int(actif or 0),
            "ligne3": str(param(griffe_cle(code, "ligne3")) or ""),
            "couleur": str(param(griffe_cle(code, "couleur")) or "")}


def jur_griffe(code=None, forcer=False):
    """(lignes, couleur) de la griffe du responsable de la structure (code None) ou du chef d'un service :
    ligne 1 = titre du signataire, ligne 2 = nom, ligne 3 facultative. None si désactivée (sauf forcer) ou sans nom."""
    titre, nom, _sig = jur_signataire(code)
    r = jur_griffe_reglages(code)
    if (not r["actif"] and not forcer) or not nom:
        return None
    couleur = r["couleur"] if r["couleur"] in COULEURS else (jur_cachet(code)[3] or "bleu")
    return [titre, nom, r["ligne3"]], couleur


def titre_service(svc):
    nom = svc["nom"] or ""
    if nom.lower().startswith("division"):
        return "Le Chef de la " + nom
    if nom.lower().startswith("service"):
        return "Le Chef du " + nom
    return "Le Chef : " + nom


# ================================================================================================ organigramme
STYLES_NOEUD = {  # remplissage, trait, texte
    "racine": ("#1F4E79", "#1F4E79", "#FFFFFF"),
    "service": ("#EEF4FB", "#1F4E79", "#10233A"),
    "cs": ("#E8F5EC", "#1B7F3B", "#0F3D1E"),
    "division": ("#F3EEFB", "#6B46C1", "#2D1A57"),
    "zone": ("#FFF7E6", "#B7791F", "#4A3108"),
    "ecole": ("#F2F4F7", "#667085", "#1D2939"),
}


def _couper(texte, n=30):
    mots, lignes, cur = str(texte or "").split(), [], ""
    for m in mots:
        if cur and len(cur) + 1 + len(m) > n:
            lignes.append(cur)
            cur = m
        else:
            cur = (cur + " " + m).strip()
    if cur:
        lignes.append(cur)
    return lignes or [""]


def _types(ecs):
    nb = {"EP": 0, "EM": 0, "EE": 0, "public": 0, "prive": 0}
    for e in ecs:
        nb[e["type"]] = nb.get(e["type"], 0) + 1
        nb[e["secteur"]] = nb.get(e["secteur"], 0) + 1
    return nb


def organigramme_donnees():
    """Rangées de l'organigramme : [(libellé, [nœud | None])] ; nœud = {id, titre, lignes, style, parent}.
    None = case laissée libre (passage du trait vers les rangées inférieures)."""
    n = niveau()
    s = structure() or {}
    rangs, nid = [], [0]

    def noeud(titre, lignes, style, parent=None):
        nid[0] += 1
        return {"id": nid[0], "titre": titre, "lignes": [l for l in lignes if l], "style": style, "parent": parent}

    svcs = services()
    agents = agents_structure() if n else []
    nb_ag = {}
    for a in agents:
        nb_ag[a["service_code"] or ""] = nb_ag.get(a["service_code"] or "", 0) + 1
    from m_juridiction import cs_liste, ecoles, zones, cs_section
    toutes = list(ecoles())
    dep = s.get("departement") or "…"
    racine_code = RACINE.get(n or "cs")
    rac = next((x for x in svcs if x["code"] == racine_code), None)

    def lignes_service(x):
        l = []
        if x["responsable_nom"]:
            l.append(x["responsable_nom"])
        if nb_ag.get(x["code"]):
            l.append(f"{nb_ag[x['code']]} agent(s)")
        return l

    def rangs_services(parent_noeud):
        """Services sous la racine, rangée par profondeur, avec une case libre au centre."""
        par_parent = {}
        for x in svcs:
            if x["code"] == racine_code:
                continue
            p = x["parent_code"] or racine_code
            if p not in {y["code"] for y in svcs}:
                p = racine_code
            par_parent.setdefault(p, []).append(x)
        niveau_courant = [(racine_code, parent_noeud)]
        prof = 1
        while True:
            rang = []
            for code_p, nd_p in niveau_courant:
                for x in par_parent.get(code_p, []):
                    rang.append((x, noeud(f"{x['sigle'] or ''} – {x['nom']}".strip(" –"), lignes_service(x),
                                          "service", nd_p["id"])))
            if not rang:
                break
            noeuds = [nd for _x, nd in rang]
            noeuds.insert((len(noeuds) + 1) // 2, None)
            rangs.append(("Services" if prof == 1 else f"Services (niveau {prof})", noeuds))
            niveau_courant = [(x["code"], nd) for x, nd in rang]
            prof += 1

    if n == "ddemp":
        r0 = noeud(f"DDEMP {dep}", ["Directeur départemental", s.get("responsable_nom") or
                                    (rac or {}).get("responsable_nom") or ""], "racine")
        rangs.append(("Direction", [r0]))
        rangs_services(r0)
        lcs = list(cs_liste())
        r_cs, r_div, r_zone, r_ec = [], [], [], []
        for c in lcs:
            ecs = [e for e in toutes if e["cs_id"] == c["id"]]
            nd = noeud(f"CS {c['nom']}", [f"CCS : {c['ccs_nom']}" if c["ccs_nom"] else "CCS : —"], "cs", r0["id"])
            ags = cs_section(c["id"], "agents") or []
            divs = {a.get("service_code") for a in ags if a.get("service_code") and a.get("service_code") != "ccs"}
            ncp = sum(1 for a in ags if a.get("role") == "cp" or "conseiller" in (a.get("poste") or "").lower())
            nd2 = noeud("Divisions et services", [f"{len(divs)} division(s)/service(s)", f"{len(ags)} agent(s) dont {ncp} CP"],
                        "division", nd["id"])
            nz = len(zones(c["id"]))
            nd3 = noeud(f"{nz} zone(s) pédagogique(s)", [], "zone", nd2["id"])
            t = _types(ecs)
            nd4 = noeud(f"{len(ecs)} école(s)", [f"EP {t['EP']} · EM {t['EM']} · EE {t['EE']}",
                                                 f"Public {t['public']} · Privé {t['prive']}"], "ecole", nd3["id"])
            r_cs.append(nd), r_div.append(nd2), r_zone.append(nd3), r_ec.append(nd4)
        if lcs:
            rangs += [("Circonscriptions", r_cs), ("Divisions des CS", r_div), ("Zones pédagogiques", r_zone),
                      ("Écoles", r_ec)]
        return rangs
    # application CS
    c = cs_courante()
    r0 = noeud(f"DDEMP {dep}", ["Direction départementale"], "racine")
    r1 = noeud(f"CS {s.get('cs') or '…'}", [f"CCS : {s.get('responsable_nom') or (rac or {}).get('responsable_nom') or '—'}",
                                             f"{len(agents)} agent(s)"], "cs", r0["id"])
    rangs += [("Tutelle", [r0]), ("Circonscription", [r1])]
    rangs_services(r1)
    lz = list(zones(c["id"])) if c else []
    r_zone, r_ec = [], []
    for z in lz:
        ecs = [e for e in toutes if e["zone_id"] == z["id"]]
        nd = noeud(z["nom"], [f"CP : {z['cp_nom']}" if z["cp_nom"] else ""], "zone", r1["id"])
        t = _types(ecs)
        r_zone.append(nd)
        r_ec.append(noeud(f"{len(ecs)} école(s)", [f"EP {t['EP']} · EM {t['EM']} · EE {t['EE']}",
                                                   f"Public {t['public']} · Privé {t['prive']}"], "ecole", nd["id"]))
    sans_zone = [e for e in toutes if not e["zone_id"]]
    if sans_zone:
        t = _types(sans_zone)
        nd = noeud("Sans zone", ["Écoles à rattacher"], "zone", r1["id"])
        r_zone.append(nd)
        r_ec.append(noeud(f"{len(sans_zone)} école(s)", [f"EP {t['EP']} · EM {t['EM']} · EE {t['EE']}"], "ecole", nd["id"]))
    if r_zone:
        rangs += [("Zones pédagogiques", r_zone), ("Écoles", r_ec)]
    return rangs


def organigramme_disposition(rangs, bw=170, gx=12, gy=34, marge_lib=108):
    """Coordonnées (origine en haut à gauche) : boîtes et traits. Renvoie (largeur, hauteur, boites, traits, libelles)."""
    cols = max([len(r) for _l, r in rangs] or [1])
    largeur = marge_lib + cols * (bw + gx) + gx
    y, boites, pos, libelles = 10, [], {}, []
    for lib, noeuds in rangs:
        prep = []
        for nd in noeuds:
            if nd is None:
                prep.append(None)
                continue
            lignes = [(t, True) for t in _couper(nd["titre"], 30)] + [(t, False) for l in nd["lignes"] for t in _couper(l, 32)]
            prep.append((nd, lignes))
        h = 12 + 12 * max([len(p[1]) for p in prep if p] or [1])
        rw = len(noeuds) * (bw + gx) - gx
        x = marge_lib + (largeur - marge_lib - rw) / 2
        libelles.append((lib, y + h / 2))
        for p in prep:
            if p:
                nd, lignes = p
                b = {"x": x, "y": y, "w": bw, "h": h, "lignes": lignes, "style": nd["style"], "id": nd["id"]}
                boites.append(b)
                pos[nd["id"]] = b
            x += bw + gx
        y += h + gy
    traits = []
    for b in boites:
        nd_parent = None
        for _l, noeuds in rangs:
            for nd in noeuds:
                if nd and nd["id"] == b["id"]:
                    nd_parent = nd["parent"]
        p = pos.get(nd_parent)
        if not p:
            continue
        px, py = p["x"] + p["w"] / 2, p["y"] + p["h"]
        cx, cy = b["x"] + b["w"] / 2, b["y"]
        mid = cy - gy / 2
        traits.append([(px, py), (px, mid), (cx, mid), (cx, cy)])
    return largeur, y, boites, traits, libelles


def organigramme_svg(rangs):
    from html import escape
    L, Ht, boites, traits, libelles = organigramme_disposition(rangs)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {L:.0f} {Ht:.0f}" width="100%" '
         f'style="max-width:{max(L, 600):.0f}px;min-width:{min(L, 900):.0f}px" role="img" aria-label="Organigramme" '
         f'font-family="Arial, Helvetica, sans-serif">']
    for lib, yy in libelles:
        o.append(f'<text x="6" y="{yy + 3:.1f}" font-size="10" fill="#667085" font-style="italic">{escape(lib)}</text>')
    for t in traits:
        o.append('<polyline fill="none" stroke="#98A2B3" stroke-width="1.3" points="' +
                 " ".join(f"{x:.1f},{y:.1f}" for x, y in t) + '"/>')
    for b in boites:
        fond, trait, txt = STYLES_NOEUD[b["style"]]
        o.append(f'<rect x="{b["x"]:.1f}" y="{b["y"]:.1f}" width="{b["w"]}" height="{b["h"]}" rx="6" fill="{fond}" '
                 f'stroke="{trait}" stroke-width="1.2"/>')
        for i, (t, gras) in enumerate(b["lignes"]):
            o.append(f'<text x="{b["x"] + b["w"] / 2:.1f}" y="{b["y"] + 15 + 12 * i:.1f}" font-size="{9.5 if gras else 9}" '
                     f'text-anchor="middle" fill="{txt}" font-weight="{700 if gras else 400}">{escape(t)}</text>')
    o.append("</svg>")
    return "".join(o)


def organigramme_dessiner(c, rangs, x0, y_haut, largeur_max, hauteur_max):
    """Dessine l'organigramme sur un canvas ReportLab, mis à l'échelle dans le cadre donné."""
    L, Ht, boites, traits, libelles = organigramme_disposition(rangs)
    k = min(largeur_max / L, hauteur_max / Ht, 1.4)
    c.saveState()
    c.translate(x0 + (largeur_max - L * k) / 2, y_haut)
    c.scale(k, -k)          # repère « vers le bas » comme le SVG
    c.setStrokeColor(colors.HexColor("#98A2B3"))
    c.setLineWidth(1.1)
    for t in traits:
        p = c.beginPath()
        p.moveTo(*t[0])
        for pt in t[1:]:
            p.lineTo(*pt)
        c.drawPath(p, stroke=1, fill=0)
    for lib, yy in libelles:
        c.saveState()
        c.translate(6, yy + 3)
        c.scale(1, -1)
        c.setFillColor(colors.HexColor("#667085"))
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(0, 0, lib)
        c.restoreState()
    for b in boites:
        fond, trait, txt = STYLES_NOEUD[b["style"]]
        c.setFillColor(colors.HexColor(fond))
        c.setStrokeColor(colors.HexColor(trait))
        c.roundRect(b["x"], b["y"], b["w"], b["h"], 5, stroke=1, fill=1)
        for i, (t, gras) in enumerate(b["lignes"]):
            c.saveState()
            c.translate(b["x"] + b["w"] / 2, b["y"] + 15 + 12 * i)
            c.scale(1, -1)
            c.setFillColor(colors.HexColor(txt))
            c.setFont("Helvetica-Bold" if gras else "Helvetica", 9.5 if gras else 9)
            c.drawCentredString(0, 0, t)
            c.restoreState()
    c.restoreState()
    return Ht * k


# ================================================================================================ en-tête officiel
def nom_dep_complet(dep):
    return f"{DEP_DE.get(dep, 'du ')}{dep}" if dep else ""


def entete_officiel(c, s, x1=40, x2=556, avec_cs=True):
    """Bande tricolore, bloc MEMP + adresse du ministère, puis DDEMP / CS. Renvoie l'ordonnée sous l'en-tête."""
    s = s or {}
    DE.barre_drapeau(c, 195, H_PAGE - 22, 204, 6, "moitie")
    DE.bandeau_memp(c, H_PAGE - 33, "mempmatprim@gmail.com", marge_g=x1, marge_d=x2, hauteur=50)
    dep = (s.get("departement") or "").upper()
    c.setFillColor(colors.black)
    c.setFont("Times-Bold", 8.6)
    y = H_PAGE - 95
    c.drawString(x1, y, "DIRECTION DÉPARTEMENTALE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE "
                 + (nom_dep_complet(s.get("departement")).upper() if dep else "DU ……………"))
    if avec_cs and (s.get("niveau") == "cs" or (not s and niveau() == "cs")):
        y -= 10.5
        c.drawString(x1, y, f"CIRCONSCRIPTION SCOLAIRE DE {(s.get('cs') or '……………').upper()}")
    return y - 6


# ================================================================================================ documents : catalogue
FOI_A = "En foi, de quoi la présente Attestation lui est délivrée pour servir et valoir ce que de droit."
FOI_C = "En foi de quoi, la présente Attestation lui est délivrée pour servir et valoir ce que de droit."
T, V, D, S, C = DE.T, DE.V, DE.D, DE.S, DE.C

LIGNE_CS = ("centre", [T("Circonscription Scolaire de "), S("cs_agent", 60, "b"), T(", département "),
                       C("_dep_de", "du "), S("departement_agent", 60, "b")])
LIGNE_NIP = [T("NIP (Numéro d'Identification Personnel) : "), V("nip")]
INTRO = [("centre", [T("Je soussigné"), C("_e_sig", ""), T(" "), S("signataire_nom", 150, "bi")]),
         ("centre", [S("signataire_qualite", 200, "n")])]

# Documents : famille « jur » (délivrés par le CCS / le Directeur départemental) ou « ame » (format école + visas)
DOCS = {
    "presence_poste": dict(
        titre="ATTESTATION DE PRESENCE AU POSTE", nom="Attestation de présence au poste",
        desc="Délivrée par le responsable de la structure (CCS / Directeur départemental).",
        cadre="arrondi", pas=24, sig=("resp",), foi=FOI_A, titre_sig_style="bi",
        corps=INTRO + [LIGNE_NIP, ("centre", [T("Atteste que "), C("civilite", "Mr ou Mme", "b")]),
                       ("petit", [V("nom_prenoms")]),
                       [C("_ne", "Né (e)"), T(" le "), D("date_naissance", 0.6), T(" à "), V("lieu_naissance", 0.4)],
                       [T("Première prise de service "), V("date_prise_service")],
                       [T("Numéro matricule "), V("matricule")],
                       [T("Corps et Grade payé "), V("corps_grade")],
                       [T("Est en service à "), V("en_service_a")],
                       [T("Suivant l'arrêté N°"), V("acte")],
                       [V("_acte_suite", 1), T("du "), D("acte_date", 0.9)],
                       LIGNE_CS,
                       [T("En qualité de (Fonction) "), V("fonction")],
                       [T("Depuis le "), D("depuis", 0.8), T(" jusqu'à ce jour "), D("jusqu_au", 1)]]),
    "presence_poste_dir": dict(
        titre="ATTESTATION DE PRESENCE AU POSTE", nom="Attestation de présence au poste (directeur + visa)",
        desc="Établie par le directeur de l'école, contresignée par le responsable de la structure.",
        cadre="double", pas=24, sig=("resp", "dir"), foi=FOI_A, fait_gras=True,
        corps=[[T("Je soussigné (e)"), V("soussigne")],
               [T("Direct"), S("_suf_dir", 32, "n"), T(" l'Ecole Primaire "), V("ecole", 1), T(" de :"),
                V("localite", 0.7)],
               ("vierge", [V("_rien")]), LIGNE_NIP,
               [T("Atteste que "), C("civilite", "Mr ou Mme", "b"), T(" "), V("nom_prenoms")],
               [C("_ne", "Né (e)"), T(" le "), D("date_naissance", 0.55), T(" à "), V("lieu_naissance", 0.45)],
               [T("Première prise de service "), V("date_prise_service")],
               [T("Numéro matricule "), V("matricule")],
               [T("Corps et Grade payé "), V("corps_grade")],
               [T("Est en service à "), V("en_service_a")],
               LIGNE_CS,
               [T("Suivant :"), V("suivant")],
               [T("En qualité de (Fonction) "), V("fonction")],
               [T("Depuis le "), D("depuis", 0.8), T(" jusqu'à ce jour "), D("jusqu_au", 1)]]),
    "attestation_direction": dict(
        titre="ATTESTATION DE DIRECTION", nom="Attestation de direction",
        desc="Au directeur / à la directrice d'école : école dirigée, nombre de classes, acte, remplacement.",
        cadre="epais", pas=19.5, sig=("resp",), foi=FOI_A,
        corps=INTRO + [LIGNE_NIP, ("centre", [T("Atteste que "), C("civilite", "Mr ou Mme")]),
                       [V("nom_prenoms")],
                       [T("Grade :"), V("grade", 1), T("Matricule"), V("matricule", 1.2)],
                       [C("_affecte", "Affecté (e)"), T(" à "), V("affecte_a")],
                       [T("Suivant l'arrêté N°"), V("acte")],
                       [V("_acte_suite", 1), T("du "), D("acte_date", 0.6)],
                       [T("Est effectivement Direct"), S("_suf_agent", 32, "n"), T(" de EM/EP "), V("direction_de")],
                       [T("Depuis le :"), V("depuis")],
                       [T("Et demeurant réellement Direct"), S("_suf_agent", 32, "n"), T(" de "), V("nb_classes", 1),
                        T("classe (s)")],
                       [T("Pour compter du "), V("pour_compter")],
                       [T("En remplacement de "), C("_remplace_civ", "Mr ou Mme"), V("remplace_nom")],
                       [T("Matricule "), V("remplace_matricule")],
                       [T("Motif "), V("motif")]]),
    "attestation_travail": dict(
        titre="ATTESTATION DE TRAVAIL", nom="Attestation / certificat de travail",
        desc="Titre au choix : « Attestation de travail » ou « Certificat de travail ».",
        cadre="epais", pas=24, sig=("resp",), foi=FOI_A,
        corps=INTRO + [LIGNE_NIP,
                       ("centre", [C("_verbe", "Atteste"), T(" que "), C("civilite", "Mr ou Mme"), T(" "),
                                   S("nom_prenoms", 180)]),
                       ("vierge", ("centre", [S("_rien", 130)])),
                       [T("Grade : "), V("grade", 1), T(" Matricule"), V("matricule", 0.9)],
                       [T("Est en service à l'école "), V("en_service_a")],
                       [T("Suivant le titre d'affectation n°"), V("acte")],
                       [T("du "), V("acte_date", 1), T(" en qualité de "), V("fonction", 1)],
                       [T("Depuis le "), D("depuis", 0.8), T("jusqu'à ce jour "), D("jusqu_au", 0.8)]]),
    "attestation_prise_service": dict(
        titre="ATTESTATION DE PRISE DE SERVICE", nom="Attestation de prise de service (école primaire)",
        desc="Enseignant affecté dans une école : remplacement, acte, classes, date de prise de service, motif.",
        cadre="epais", pas=22, sig=("resp",), foi=FOI_A,
        corps=INTRO + [LIGNE_NIP, ("centre", [T("Atteste que "), C("civilite", "Mr ou Mme", "b")]),
                       [V("nom_prenoms")],
                       [T("Grade : "), V("grade", 1), T("Matricule"), V("matricule", 1)],
                       [C("_affecte", "Affecté(e)"), T(" à l'Ecole Primaire "), V("affecte_a")],
                       [T("En remplacement de "), V("remplace_nom")],
                       [T("Suivant l'Arrêté/Note de Service n°"), V("acte")],
                       [V("_acte_suite")],
                       [T("du"), D("acte_date", 0.5), T(" en qualité"), V("fonction", 1), T("de"), V("nb_classes", 0.22),
                        T("classe(s)")],
                       [T("a effectivement pris service le "), D("date_effective")],
                       ("retrait", [T("Motif :"), V("motif")])]),
    "attestation_prise_service_dir": dict(
        titre="ATTESTATION DE PRISE DE SERVICE", nom="Attestation de prise de service (délivrée par le directeur)",
        desc="Le directeur certifie la prise de service de l'agent affecté à son école.",
        cadre="epais", pas=26, sig=("dir",), foi=FOI_A, fait_gras=True,
        corps=[[T("Je soussigné (e)"), V("soussigne")],
               [T("Direct"), S("_suf_dir", 32, "n"), T(" de l'Ecole Primaire"), V("ecole", 1), T(" de :"),
                V("localite", 0.6)],
               LIGNE_NIP,
               [T("Certifie que "), C("civilite", "Mr ou Mme"), T(" "), V("nom_prenoms")],
               [T("Grade :"), V("grade", 1), T("Matricule :"), V("matricule", 1)],
               [C("_affecte", "Affecté(e)"), T(" à l'école "), V("affecte_a")],
               [T("Suivant Note de Service ou Titre d'Affection n°"), V("acte")],
               [V("_acte_suite", 0.6), T("du"), D("acte_date", 0.5), T("en qualité"), V("fonction", 0.7)],
               [T("a effectivement pris service le"), D("date_effective")]]),
    "certificat_prise_service": dict(
        titre="CERTIFICAT DE PRISE DE SERVICE", nom="Certificat de prise de service (agent de la structure)",
        desc="Agent affecté à la circonscription / à la direction : remplacement, acte, fonction, motif.",
        cadre="epais", pas=22, sig=("resp",), foi=FOI_C,
        corps=INTRO + [LIGNE_NIP, ("centre", [T("Certifie que "), C("civilite", "Mr ou Mme", "b")]),
                       [V("nom_prenoms")],
                       [T("Grade : "), V("grade", 1), T("Matricule"), V("matricule", 1)],
                       [C("_affecte", "Affecté(e)"), T(" à "), C("_affecte_a_lib", "la Circonscription Scolaire de :"),
                        V("affecte_cs")],
                       [T("En remplacement de "), V("remplace_nom")],
                       [T("Suivant l'arrêté /décision /Note de Service N°"), V("acte")],
                       [V("_acte_suite", 1), T("du"), D("acte_date", 0.5)],
                       [T("en qualité de :"), V("fonction")],
                       [T("a effectivement pris service le "), D("date_effective")],
                       ("retrait", [T("Motif :"), V("motif")])]),
    "certificat_reprise_service": dict(
        titre="CERTIFICAT DE REPRISE DE SERVICE", nom="Certificat de reprise de service",
        desc="Reprise de service à son nouveau poste (après congé, formation, disponibilité…).",
        cadre="epais", pas=22, sig=("resp",), foi=FOI_C,
        corps=INTRO + [LIGNE_NIP, ("centre", [T("Certifie que "), C("civilite", "Mr ou Mme", "b")]),
                       [V("nom_prenoms")],
                       [T("Grade : "), V("grade", 1), T("Matricule"), V("matricule", 1)],
                       [C("_ne", "Né(e)"), T(" le :"), D("date_naissance", 1), T(" à "), V("lieu_naissance", 1)],
                       [T("Matricule : "), V("matricule")],
                       [T("Grade : "), V("grade")],
                       [T("Corps :"), V("corps")],
                       [T("A effectivement repris service à son nouveau poste le "), D("date_reprise", 0.6)],
                       [T("Suivant :"), V("suivant")],
                       [V("_suivant_suite")]]),
    "prise_en_charge": dict(
        titre="CERTIFICAT DE PRISE EN CHARGE", nom="Certificat de prise en charge (hospitalisation)",
        desc="Admission des fonctionnaires et assimilés : profession, indice, budget, catégorie.",
        cadre="aucun", pas=24, sig=("resp",), foi=None,
        corps=[LIGNE_NIP,
               [T("Nom et Prénoms du malade : "), V("nom_prenoms")],
               ("vierge", [V("_rien")]),
               [T("Profession :"), V("profession")],
               [T("En service à "), V("en_service_a")],
               [T("Indice de traitement :"), V("indice")],
               [T("Budget devant supporter l'hospitalisation :"), V("budget")],
               [T("Catégorie d'hospitalisation :"), V("categorie_hosp")]]),
    "ame_prise_service": dict(
        titre="CERTIFICAT DE PRISE DE SERVICE", nom="Certificat de prise de service (AME)", famille="ame",
        desc="Aspirant au métier d'enseignant (programme de pré-insertion) : format école, visas CP / directeur / APE.",
        verbe="pris"),
    "ame_reprise_service": dict(
        titre="CERTIFICAT DE REPRISE DE SERVICE", nom="Certificat de reprise de service (AME)", famille="ame",
        desc="Reprise de service d'un AME : format école, visas CP / directeur / APE.", verbe="repris"),
}
for _k, _d in DOCS.items():
    _d.setdefault("famille", "jur")

QUALITES_AME = {"instituteur": "Instituteur (trice)", "adjoint": "Instituteur (trice) adjoint(e)",
                "animateur": "Animateur (trice)", "eleve": "Elève-instituteur (trice)"}

# clé → (libellé, type) ; t texte, date jj/mm/aaaa, civ, genre, dir, titre_travail, qualite, type_ecole
CHAMPS = {
    "ref": ("Référence (SO N° … au registre)", "t"),
    "signataire_genre": ("Signataire", "genre"),
    "signataire_nom": ("Je soussigné(e) — nom du signataire", "t"),
    "signataire_qualite": ("Qualité du signataire", "t"),
    "signataire_titre": ("Titre au-dessus de la signature", "t"),
    "titre_doc": ("Titre du document", "titre_travail"),
    "soussigne": ("Je soussigné(e) — nom du directeur / de la directrice", "t"),
    "directeur_titre": ("Directeur / Directrice", "dir"),
    "ecole": ("École", "t"),
    "localite": ("Localité (« de : … »)", "t"),
    "civilite": ("Civilité", "civ"),
    "nom_prenoms": ("Nom et prénom(s)", "t"),
    "nip": ("NIP (Numéro d'Identification Personnel)", "t"),
    "matricule": ("Numéro matricule", "t"),
    "date_naissance": ("Date de naissance", "t"),
    "lieu_naissance": ("Lieu de naissance", "t"),
    "date_prise_service": ("Première prise de service", "t"),
    "grade": ("Grade", "t"),
    "corps": ("Corps", "t"),
    "corps_grade": ("Corps et grade payé", "t"),
    "en_service_a": ("Est en service à", "t"),
    "cs_agent": ("Circonscription scolaire de l'agent", "t"),
    "departement_agent": ("Département", "t"),
    "suivant": ("Suivant (acte : arrêté, décision, note de service…)", "t"),
    "acte": ("Acte (arrêté / note de service / titre d'affectation) N°", "t"),
    "acte_date": ("Date de l'acte", "t"),
    "fonction": ("En qualité de (fonction)", "t"),
    "depuis": ("Depuis le", "t"),
    "jusqu_au": ("Jusqu'à ce jour", "t"),
    "affecte_a": ("Affecté(e) à", "t"),
    "affecte_cs": ("Affecté(e) à la Circonscription Scolaire / la structure de", "t"),
    "direction_de": ("Est effectivement directeur / directrice de EM/EP", "t"),
    "nb_classes": ("Nombre de classes", "t"),
    "pour_compter": ("Pour compter du", "t"),
    "remplace_nom": ("En remplacement de (M. / Mme, nom)", "t"),
    "remplace_matricule": ("Matricule de l'agent remplacé", "t"),
    "motif": ("Motif", "t"),
    "date_effective": ("A effectivement pris service le", "t"),
    "date_reprise": ("A effectivement repris service le", "t"),
    "profession": ("Profession", "t"),
    "indice": ("Indice de traitement", "t"),
    "budget": ("Budget devant supporter l'hospitalisation", "t"),
    "categorie_hosp": ("Catégorie d'hospitalisation", "t"),
    "fait_a": ("Fait à", "t"),
    "fait_le": ("le (jj/mm/aaaa)", "date"),
    # AME
    "ame_departement": ("Direction départementale … de (département)", "t"),
    "ame_type": ("École primaire / maternelle (mention à barrer)", "type_ecole"),
    "ame_ecole": ("École publique de", "t"),
    "ame_groupe": ("Groupe (G/…)", "t"),
    "titulaire_de": ("Titulaire de (diplôme)", "t"),
    "edition": ("Programme spécial de pré-insertion — édition (ex. 2026-2027)", "t"),
    "date_service": ("Date de prise / reprise de service (jj/mm/aaaa)", "date"),
    "titre_affectation": ("Titre d'affectation n°", "t"),
    "titre_affectation_date": ("du (date du titre d'affectation)", "t"),
    "qualite": ("En qualité de (à cocher)", "qualite"),
    "classe_attribuee": ("Classe / section attribuée", "t"),
    "cp_nom": ("Conseiller pédagogique (nom et prénoms)", "t"),
    "cp_tel": ("Téléphone du CP", "t"),
    "dir_nom": ("Chef d'établissement (nom et prénoms)", "t"),
    "dir_tel": ("Téléphone du chef d'établissement", "t"),
    "ape_nom": ("Président / Secrétaire de l'APE (nom et prénoms)", "t"),
    "ape_tel": ("Téléphone (APE)", "t"),
    "lieu_visa": ("Lieu (visa du chef d'établissement)", "t"),
    "date_visa": ("Date (visa du chef d'établissement, jj/mm/aaaa)", "date"),
}

_SIG = ["ref", "signataire_genre", "signataire_nom", "signataire_qualite", "signataire_titre"]
_FAIT = ["fait_a", "fait_le"]
SECTIONS = {
    "presence_poste": [("Signataire", _SIG), ("Agent", ["civilite", "nip", "nom_prenoms", "date_naissance",
                                                         "lieu_naissance", "date_prise_service", "matricule", "corps_grade",
                                                         "en_service_a", "acte", "acte_date", "cs_agent",
                                                         "departement_agent", "fonction", "depuis", "jusqu_au"] + _FAIT)],
    "presence_poste_dir": [("Signataires", _SIG + ["soussigne", "directeur_titre", "ecole", "localite"]),
                           ("Agent", ["civilite", "nip", "nom_prenoms", "date_naissance", "lieu_naissance",
                                      "date_prise_service", "matricule", "corps_grade", "en_service_a",
                                      "cs_agent", "departement_agent", "suivant", "fonction", "depuis",
                                      "jusqu_au"] + _FAIT)],
    "attestation_direction": [("Signataire", _SIG), ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule",
                                                                "affecte_a", "acte", "acte_date", "direction_de",
                                                                "depuis", "nb_classes", "pour_compter", "remplace_nom",
                                                                "remplace_matricule", "motif"] + _FAIT)],
    "attestation_travail": [("Signataire", _SIG + ["titre_doc"]),
                            ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule", "en_service_a", "acte",
                                       "acte_date", "fonction", "depuis", "jusqu_au"] + _FAIT)],
    "attestation_prise_service": [("Signataire", _SIG),
                                  ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule", "affecte_a",
                                             "remplace_nom", "acte", "acte_date", "fonction", "nb_classes",
                                             "date_effective", "motif"] + _FAIT)],
    "attestation_prise_service_dir": [("Signataire", ["ref", "soussigne", "directeur_titre", "ecole", "localite"]),
                                      ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule", "affecte_a",
                                                 "acte", "acte_date", "fonction", "date_effective"] + _FAIT)],
    "certificat_prise_service": [("Signataire", _SIG),
                                 ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule", "affecte_cs",
                                            "remplace_nom", "acte", "acte_date", "fonction", "date_effective",
                                            "motif"] + _FAIT)],
    "certificat_reprise_service": [("Signataire", _SIG),
                                   ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule", "date_naissance",
                                              "lieu_naissance", "corps", "date_reprise", "suivant"] + _FAIT)],
    "prise_en_charge": [("Signataire", _SIG), ("Malade", ["nip", "nom_prenoms", "profession", "en_service_a", "indice",
                                                           "budget", "categorie_hosp"] + _FAIT)],
}
SECTIONS["ame_prise_service"] = SECTIONS["ame_reprise_service"] = [
    ("En-tête", ["ref", "ame_departement", "ame_type", "ame_ecole", "ame_groupe"]),
    ("Aspirant(e)", ["civilite", "nip", "nom_prenoms", "titulaire_de", "edition", "date_service", "titre_affectation",
                     "titre_affectation_date", "qualite", "classe_attribuee"]),
    ("Visas", ["cp_nom", "cp_tel", "dir_nom", "dir_tel", "lieu_visa", "date_visa", "ape_nom", "ape_tel"])]


def cles_doc(doc):
    return [k for _t, ks in SECTIONS[doc] for k in ks]


# ================================================================================================ documents : valeurs dérivées
def preparer(doc, v):
    """Accords (Né/Née, Affecté/Affectée, Directeur/Directrice, soussigné/soussignée) et libellés composés."""
    v = {k: ("" if val is None else str(val)) for k, val in (v or {}).items()}
    civ = (v.get("civilite") or "").lower()
    sexe = "F" if civ.startswith(("mme", "mlle")) else ("M" if civ.startswith("m") else "")
    if sexe:
        v["_ne"] = "Née" if sexe == "F" else "Né"
        v["_affecte"] = "Affectée" if sexe == "F" else "Affecté"
        v["_suf_agent"] = "rice" if sexe == "F" else "eur"
    v["_suf_dir"] = DE.suffixe_dir(v.get("directeur_titre"))
    if v.get("signataire_genre") == "F":
        v["_e_sig"] = "e"
    if v.get("departement_agent"):
        v["_dep_de"] = DEP_DE.get(v["departement_agent"], "du ")
    if v.get("remplace_nom"):
        v["_remplace_civ"] = " "
    if doc == "attestation_travail":
        certif = v.get("titre_doc", "").upper().startswith("CERTIFICAT")
        v["_verbe"] = "Certifie" if certif else "Atteste"
    if doc == "certificat_prise_service" and niveau() == "ddemp" and v.get("affecte_cs"):
        v["_affecte_a_lib"] = " "        # en DDEMP : « Affecté(e) à la DDEMP du Plateau / à la Circonscription … »
    return v


# ================================================================================================ documents : dessin PDF
def _fait_segments():
    return [T("Fait à "), S("fait_a", 90), T(", le "), S("fait_le", 120)]


def bloc_resp(c, v, cx, y, opt, style="b", size=13.5):
    """Titre du signataire, cachet et signature numériques (si signé), puis griffe (opt["griffe"], à droite du cachet
    rond, sous la signature) ou nom en clair."""
    titre = v.get("signataire_titre") or "Le Chef de la Circonscription Scolaire"
    DE.texte_ajuste(c, cx - DE.sw(c, titre, DE.TIMES[style], size) / 2 if DE.sw(c, titre, DE.TIMES[style], size) < 250
                    else cx - 125, y, 250, titre, DE.TIMES[style], size)
    griffe = None
    if opt.get("signer"):
        ca = opt.get("cachet")
        if ca:
            CACHET.dessiner(c, cx - 30, y - 42, 30, *ca)
        img = pdfs.image_data_url(opt.get("sig"))
        if img is not None:
            c.drawImage(img, cx - 55, y - 74, 120, 55, preserveAspectRatio=True, mask="auto")
        griffe = opt.get("griffe")
    nom = v.get("signataire_nom") or ""
    c.setFont("Times-Bold", 13.5)
    if nom and griffe:
        lignes = [titre] + list(griffe[0][1:])      # le titre imprimé sur le document prime sur celui du réglage
        CACHET.dessiner_nom(c, cx + 10, y - 96, lignes, griffe[1], 150)
    elif nom:
        c.drawCentredString(cx, y - 92, nom)
    else:
        DE.pointilles(c, cx - 80, cx + 80, y - 92, "Times-Roman", 13.5)


def bloc_dir(c, v, cx, y, opt=None):
    """Signature du directeur de l'école : nom en clair, ou griffe de l'école (opt["griffe_dir"]) quand l'école est
    aussi gérée localement (écoles liées) et que le document est signé."""
    titre = DE.titre_dir(v.get("directeur_titre"))
    c.setFont("Times-BoldItalic", 13.5)
    c.drawCentredString(cx, y, titre or "L…… Direct………")
    nom = v.get("soussigne") or ""
    griffe = (opt or {}).get("griffe_dir") if (opt or {}).get("signer") else None
    c.setFont("Times-Bold", 13.5)
    if nom and griffe:
        CACHET.dessiner_nom(c, cx + 10, y - 96, griffe[0], griffe[1], 150)
    elif nom:
        c.drawCentredString(cx, y - 92, nom)
    else:
        DE.pointilles(c, cx - 55, cx + 55, y - 92, "Times-Roman", 13.5)


def dessiner_doc_jur(c, doc, v, opt):
    spec = DOCS[doc]
    fam, size = DE.TIMES, 13.5
    x1, x2 = 40, 556
    vierge = opt.get("vierge")
    s = opt.get("structure") or {}
    y = entete_officiel(c, s, x1, x2)
    ref = v.get("ref") or ""
    c.setFillColor(colors.black)
    if ref:
        DE.texte_ajuste(c, x1, y - 6, x2 - x1, ref, "Times-Bold" if doc == "prise_en_charge" else "Times-Roman", 9.5)
    else:
        base = [T("SO N°"), V("_x", 0.2)]
        if doc in ("presence_poste_dir", "attestation_prise_service_dir"):
            base += [T("EPP/EM"), V("_x", 1)]
        if (s.get("niveau") or niveau()) == "cs":
            base += [T("/CS-" + (s.get("cs") or "").upper())] if s.get("cs") else [T("/CS-"), V("_x", 0.3)]
        base += [T(f"/DDEMP-{opt.get('sigle_dep') or ''}")] + ([V("_x", 0.12)] if not opt.get("sigle_dep") else []) + \
            [T("/SP")]
        DE.ligne(c, x1, y - 6, 520, base, {}, fam, 9.5)
    y -= 18
    if spec["cadre"] == "aucun":
        c.setFont("Times-Roman", 18)
        c.drawCentredString(W / 2, y - 30, spec["titre"])
        c.setFont("Times-Italic", 9)
        c.drawCentredString(W / 2, y - 45, "Admission des fonctionnaires et assimilés")
        y -= 70
    else:
        titre = v.get("titre_doc") or spec["titre"] if doc == "attestation_travail" else spec["titre"]
        larg = {"double": (87, 514), "arrondi": (103, 526), "epais": (100, 505)}[spec["cadre"]]
        h = 40 if spec["cadre"] == "arrondi" else 44
        DE.cadre_titre(c, titre.upper(), spec["cadre"], y, *larg, hauteur=h, size=16)
        y -= h + 26
    # corps : interligne réduit si nécessaire pour garder la place des signatures et du QR
    lignes = []
    for ln in spec["corps"]:
        mode, segs = "l", ln
        if isinstance(ln, tuple):
            mode, segs = ln
            if mode == "vierge":
                if not vierge:
                    continue
                mode, segs = segs if isinstance(segs, tuple) else ("l", segs)
        lignes.append((mode, segs))
    bas = 262 if len(spec["sig"]) else 240
    pas = min(spec["pas"], (y - bas) / max(1, len(lignes)))
    for mode, segs in lignes:
        if mode == "centre":
            DE.ligne(c, x1, y, x2, segs, v, fam, size, align="c")
        elif mode == "petit":
            DE.ligne(c, x1 + 30, y, x2 - 30, segs, v, fam, size)
        elif mode == "retrait":
            DE.ligne(c, x1 + 72, y, x2 - 10, segs, v, fam, size)
        else:
            DE.ligne(c, x1, y, x2, segs, v, fam, size)
        y -= pas
    y += pas - 24
    if spec["foi"]:
        p = Paragraph(f"<para firstLineIndent='28'>{spec['foi']}</para>",
                      ParagraphStyle("foi", fontName="Times-BoldItalic", fontSize=12, leading=15))
        _, h = p.wrap(x2 - x1 - 10, 60)
        p.drawOn(c, x1, y - h + 12)
        y -= h + 10
    else:
        y -= 12
    fam_fait = ({"n": "Times-Bold", "b": "Times-Bold", "i": "Times-Italic", "bi": "Times-BoldItalic"}
                if spec.get("fait_gras") else fam)
    DE.ligne(c, 150 if len(spec["sig"]) == 1 else 190, y, x2, _fait_segments(), v, fam_fait, 13, align="r")
    y -= 26
    sopt = dict(opt, signer=opt.get("signer") and not vierge)
    if spec["sig"] == ("resp", "dir"):
        bloc_resp(c, v, 170, y, sopt)
        bloc_dir(c, v, 450, y, sopt)
    elif spec["sig"] == ("dir",):
        bloc_dir(c, v, 450, y - 18, sopt)
    else:
        bloc_resp(c, v, 420, y, sopt, style=spec.get("titre_sig_style", "b"),
                  size=15 if spec.get("titre_sig_style") == "bi" else 13.5)
    if opt.get("code"):
        pdfs._qr(c, opt["code"], 40, 44, 46)
    DE.barre_drapeau(c, 108, 26, 378, 6, "moitie")
    c.showPage()


def _case(c, x, y, coche):
    c.rect(x, y - 1, 8, 8, stroke=1, fill=0)
    if coche:
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + 4, y + 0.5, "X")


def dessiner_doc_ame(c, doc, v, opt):
    """Certificat de prise / reprise de service des AME (modèle école : en-tête MEMP / DDEMP / école, visas)."""
    spec = DOCS[doc]
    k = 0.9015                       # 1 pixel du modèle (80 dpi) en points

    def Y(px):
        return H_PAGE - px * k

    def X(px):
        return px * k
    vierge = opt.get("vierge")
    DE.armoiries(c, X(62), Y(36), 52)
    c.setFillColor(colors.black)
    c.setFont("Times-Roman", 8.2)
    c.drawString(X(140), Y(38), "MINISTÈRE DES ENSEIGNEMENTS")
    c.drawString(X(140), Y(50), " MATERNEL ET PRIMAIRE")
    DE.barre_drapeau(c, X(140), Y(72), X(147), 4)
    c.drawString(X(140), Y(90), "RÉPUBLIQUE DU BÉNIN")
    c.setFont("Times-Roman", 8.2)
    for i, t in enumerate(("01 BP 10 Porto-Novo", "Tel.: +22920 21 52 22", "", "Fax : +229 20 21 5222",
                           "E-mail: memp.info@gouv.bj")):
        if t:
            c.drawRightString(X(598), Y(50 + i * 13), t)
    c.drawCentredString(X(160), Y(101), "---------------------")
    fam, size = DE.TIMES, 9
    c.setFont("Times-Roman", 9)
    c.drawString(X(64), Y(116), "DIRECTION DEPARTEMENTALE DES ENSEIGNEMENTS")
    DE.ligne(c, X(64), Y(130), X(340), [T("MATERNEL ET PRIMAIRE DE "), V("ame_departement")],
             {"ame_departement": (v.get("ame_departement") or "").upper()}, fam, size)
    c.drawCentredString(X(160), Y(141), "-------------------")
    # « ECOLE PRIMAIRE/MATERNELLE¹ PUBLIQUE DE » : la mention inutile est barrée
    xe = X(64)
    c.setFont("Times-Roman", 9)
    morceaux = [("ECOLE ", None), ("PRIMAIRE", "EP"), ("/", None), ("MATERNELLE", "EM")]
    for txt, typ in morceaux:
        w = DE.sw(c, txt, "Times-Roman", 9)
        c.drawString(xe, Y(160), txt)
        if typ and v.get("ame_type") in ("EP", "EM") and v.get("ame_type") != typ:
            c.setLineWidth(0.9)
            c.line(xe, Y(160) + 3, xe + w, Y(160) + 3)
        xe += w
    c.setFont("Times-Roman", 5.5)
    c.drawString(xe, Y(156), "1")
    c.setFont("Times-Roman", 9)
    c.drawString(xe + 4, Y(160), "PUBLIQUE DE")
    DE.ligne(c, X(66), Y(178), X(300), [V("ame_ecole", 1), T("G/"), V("ame_groupe", 0.35)], v, fam, size)
    ref = v.get("ref") or ""
    if ref:
        DE.texte_ajuste(c, X(64), Y(212), X(560) - X(64), ref, "Times-Bold", 9)
    else:
        c.setFont("Times-Bold", 9)
        c.drawString(X(64), Y(212), "N°______/20…..-20……/DIR/________/……...............................")
    # titre souligné
    c.setFont("Times-Bold", 11.5)
    titre = spec["titre"]
    c.drawCentredString(X(340), Y(253), titre)
    tw = DE.sw(c, titre, "Times-Bold", 11.5)
    c.setLineWidth(0.8)
    c.line(X(340) - tw / 2, Y(253) - 2, X(340) + tw / 2, Y(253) - 2)
    # corps
    fam, size, x1, x2, pas = DE.TIMES, 11, X(63), X(610), 20.5
    y = Y(276)
    DE.ligne(c, x1, y, x2, LIGNE_NIP, v, fam, size)
    y -= pas
    DE.ligne(c, x1, y, x2, [T("Nous, soussignés, certifions que "), C("_civ_ame", "Mme/M."), T(" "), V("nom_prenoms")],
             v, fam, size)
    y -= pas
    DE.ligne(c, x1, y, x2, [T("Titulaire de : "), V("titulaire_de")], v, fam, size)
    y -= pas
    c.setFont("Times-Roman", size)
    c.drawString(x1, y, "et mis(e) à disposition dans le cadre du Programme spécial de pré-insertion professionnelle dans")
    y -= pas
    DE.ligne(c, x1, y, x2, [T("l'enseignement-édition "), S("edition", 70), T(" , a effectivement " + spec["verbe"] +
                                                                              " service, le "), D("date_service", 1)],
             v, fam, size)
    y -= pas
    DE.ligne(c, x1, y, x2, [T("conformément au titre d'affectation n° "), V("titre_affectation")], v, fam, size)
    y -= pas
    DE.ligne(c, x1, y, x2 - 120, [V("_x", 0.3), T("du "), V("titre_affectation_date", 1), T(", en qualité de ")], v,
             fam, size)
    c.setFont("Times-Italic", size)
    c.drawString(x2 - 118, y, "(à cocher) :")
    y -= pas
    q_ = v.get("qualite") or ""
    c.setFont("Times-Roman", size)
    xq = X(95)
    for cle in ("instituteur", "adjoint", "eleve"):
        lib = "-" + QUALITES_AME[cle]
        c.setFont("Times-Roman", size)
        c.drawString(xq, y, lib)
        xx = xq + DE.sw(c, lib, "Times-Roman", size) + 6
        _case(c, xx, y, q_ == cle)
        if cle == "adjoint":
            c.setFont("Times-Roman", size)
            c.drawString(xx + 14, y, "ou Animateur (trice)")
            _case(c, xx + 14 + DE.sw(c, "ou Animateur (trice)", "Times-Roman", size) + 6, y, q_ == "animateur")
        y -= pas * 0.85
    y -= 8
    DE.ligne(c, x1, y, X(420), [T("Classe/Section attribuée : "), V("classe_attribuee")], v, fam, size)
    y -= pas
    c.setFont("Times-Roman", size)
    c.drawString(x1, y, "En foi de quoi, le présent certificat lui est délivré pour servir et valoir ce que de droit.")
    # visas
    y -= 18
    xm = X(346)
    c.setLineWidth(0.8)
    c.line(xm, y + 6, xm, y - 268)
    c.setFont("Times-Bold", size)
    c.drawCentredString(X(198), y, "Visas")
    c.line(X(198) - 14, y - 2, X(198) + 14, y - 2)
    c.drawCentredString(X(198), y - 18, "Le Conseiller Pédagogique,")
    c.drawString(xm + 12, y - 18, "Le Chef d'établissement,")

    def nom_tel(cx, yy, nom, tel):
        txt = ", ".join(t for t in (nom, tel) if t)
        if txt and not vierge:
            taille = 10
            while taille > 6 and DE.sw(c, txt, "Times-Bold", taille) > 200:
                taille -= 0.5
            c.setFont("Times-Bold", taille)
            c.drawCentredString(cx, yy, txt)
        else:
            DE.pointilles(c, cx - 75, cx + 75, yy, "Times-Roman", 10)
        c.setFont("Times-Italic", 10)
        c.drawCentredString(cx, yy - 14, "(Nom et Prénoms, téléphone)")
    nom_tel(X(198), y - 108, v.get("cp_nom"), v.get("cp_tel"))
    c.setFont("Times-Bold", size)
    c.drawCentredString(X(198), y - 150, "Le Président/Secrétaire de l'APE,")
    nom_tel(X(198), y - 230, v.get("ape_nom"), v.get("ape_tel"))
    c.setFont("Times-Italic", 10)
    c.drawString(xm + 12, y - 120, "(Signature, cachet, nom et prénoms, téléphone)")
    txt = ", ".join(t for t in (v.get("dir_nom"), v.get("dir_tel")) if t)
    if txt and not vierge:
        DE.texte_ajuste(c, xm + 12, y - 140, X(610) - xm - 12, txt, "Times-Bold", 10)
    DE.ligne(c, xm + 12, y - 170, X(560), [S("lieu_visa", 90, "n"), T(", le "), D("date_visa", 1)], v, fam, 10)
    # note de bas de page
    c.setLineWidth(0.5)
    c.line(X(40), 62, X(200), 62)
    c.setFont("Times-Roman", 5.5)
    c.drawString(X(70), 53, "1")
    c.setFont("Times-Roman", 8)
    c.drawString(X(75), 50, "barrer la mention inutile")
    if opt.get("code"):
        pdfs._qr(c, opt["code"], X(400), 34, 40)
    c.showPage()


def construire_pdf(doc, lots, titre):
    """lots = [(valeurs, options)] → octets PDF."""
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A4)
    c.setTitle(titre)
    c.setAuthor("GESCOL")
    for v, opt in lots:
        v = preparer(doc, v)
        if DOCS[doc]["famille"] == "ame":
            civ = (v.get("civilite") or "").lower()
            if civ:
                v["_civ_ame"] = "Mme" if civ.startswith(("mme", "mlle")) else "M."
            dessiner_doc_ame(c, doc, v, opt)
        else:
            dessiner_doc_jur(c, doc, v, opt)
    c.save()
    return buf.getvalue()


# ================================================================================================ PDF organigramme + attributions
def _texte_para(t):
    from xml.sax.saxutils import escape
    return escape(t or "").replace("\n", "<br/>")


def pdf_organigramme(rangs, svcs, s):
    from reportlab.platypus import Frame, Spacer
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=landscape(A4))
    c.setTitle("Organigramme et attributions")
    c.setAuthor("GESCOL")
    LW, LH = landscape(A4)
    # page 1 : organigramme (paysage)
    DE.bloc_memp(c, 30, LH - 22, 40)
    c.setFillColor(colors.black)
    c.setFont("Times-Bold", 9)
    dep = (s or {}).get("departement") or ""
    c.drawRightString(LW - 30, LH - 32, "DIRECTION DÉPARTEMENTALE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE "
                      + nom_dep_complet(dep).upper())
    if niveau() == "cs":
        c.drawRightString(LW - 30, LH - 44, f"CIRCONSCRIPTION SCOLAIRE DE {((s or {}).get('cs') or '').upper()}")
    c.setFont("Times-Bold", 15)
    c.drawCentredString(LW / 2, LH - 82, "ORGANIGRAMME " + ("DE LA CIRCONSCRIPTION SCOLAIRE" if niveau() == "cs"
                                                          else "DE LA DIRECTION DÉPARTEMENTALE"))
    c.setFont("Times-Italic", 9)
    c.drawCentredString(LW / 2, LH - 95, f"Année scolaire {config.ANNEE_ACTIVE} – situation au {date.today().strftime('%d/%m/%Y')}")
    organigramme_dessiner(c, rangs, 25, LH - 108, LW - 50, LH - 140)
    c.showPage()
    # pages suivantes : attributions (portrait)
    c.setPageSize(A4)
    st_t = ParagraphStyle("t", fontName="Times-Bold", fontSize=15, leading=19, alignment=1, spaceAfter=10)
    st_h = ParagraphStyle("h", fontName="Times-Bold", fontSize=11.5, leading=14, spaceBefore=10, spaceAfter=3,
                          textColor=colors.HexColor("#1F4E79"))
    st_i = ParagraphStyle("i", fontName="Times-Italic", fontSize=9.5, leading=12, spaceAfter=2)
    st_p = ParagraphStyle("p", fontName="Times-Roman", fontSize=10.5, leading=13.5, alignment=4)
    st_n = ParagraphStyle("n", fontName="Times-Italic", fontSize=9.5, leading=12, textColor=colors.HexColor("#475467"),
                          spaceBefore=3)
    story = [Paragraph("ATTRIBUTIONS DES SERVICES", st_t)]
    for x in svcs:
        story.append(Paragraph(_texte_para(f"{x['sigle'] or ''} – {x['nom']}".strip(" –")), st_h))
        infos = []
        if x.get("reference"):
            infos.append(f"Texte : {x['reference']}")
        if x.get("parent_nom"):
            infos.append(f"Rattachement : {x['parent_nom']}")
        infos.append(f"Responsable : {x['responsable_nom'] or 'non désigné'}")
        story.append(Paragraph(_texte_para(" · ".join(infos)), st_i))
        story.append(Paragraph(_texte_para(x["attributions"] or "Attributions non renseignées."), st_p))
        if x.get("note"):
            story.append(Paragraph(_texte_para(x["note"]), st_n))
        story.append(Spacer(1, 4))
    premiere = True
    while story:
        haut = H_PAGE - 30
        if premiere:
            haut = entete_officiel(c, s) - 8
            premiere = False
        f = Frame(45, 40, W - 90, haut - 40, showBoundary=0)
        avant = len(story)
        f.addFromList(story, c)
        c.showPage()
        if len(story) == avant:     # élément trop grand : on l'abandonne pour éviter une boucle sans fin
            story.pop(0)
    c.save()
    return buf.getvalue()


def pdf_cachets(lignes):
    """Planche des cachets (cachet.dessiner) avec titre et signature du signataire."""
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A4)
    c.setTitle("Cachets et signatures")
    y = entete_officiel(c, structure()) - 10
    c.setFont("Times-Bold", 14)
    c.drawCentredString(W / 2, y - 10, "CACHETS ET SIGNATURES")
    y -= 40
    for lib, ca, (titre, nom, sig), griffe in lignes:
        if y < 130:
            c.showPage()
            y = H_PAGE - 50
        x = 60
        CACHET.dessiner(c, x + 50, y - 55, 48, *ca)
        c.setFillColor(colors.black)
        DE.texte_ajuste(c, x + 115, y - 22, 360, lib, "Helvetica-Bold", 10)
        DE.texte_ajuste(c, x + 115, y - 36, 200, titre, "Helvetica", 8.5)
        DE.texte_ajuste(c, x + 115, y - 49, 200, nom or "(nom non renseigné)", "Helvetica-Oblique", 8.5)
        c.setFont("Helvetica", 7.5)
        c.drawString(x + 115, y - 64, f"Haut : {ca[0]}  ·  Bas : {ca[1]}  ·  Centre : {ca[2].replace('|', ' / ')}"[:110])
        img = pdfs.image_data_url(sig)
        if img is not None:
            c.drawImage(img, x + 330, y - 100, 140, 60, preserveAspectRatio=True, mask="auto")
        else:
            c.setFont("Helvetica-Oblique", 7.5)
            c.drawString(x + 330, y - 50, "Signature numérique non enregistrée")
        if griffe:
            CACHET.dessiner_nom(c, x + 200, y - 90, griffe[0], griffe[1], 160)
        c.setStrokeColor(colors.HexColor("#D0D5DD"))
        c.line(x, y - 110, W - 60, y - 110)
        y -= 118
    c.showPage()
    c.save()
    return buf.getvalue()


# ================================================================================================ outils documents
def date_fr(iso):
    s = str(iso or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    return s


def aujourdhui():
    return date.today().strftime("%d/%m/%Y")


def date_valide(s):
    try:
        datetime.strptime((s or "").strip(), "%d/%m/%Y")
        return True
    except ValueError:
        return False


def ville_cs(s):
    """« Pobè » plutôt que « POBE » quand la ville de la structure correspond à la CS."""
    import m_juridiction as J
    if s.get("ville") and J.norm(s["ville"]) == J.norm(s.get("cs")):
        return s["ville"]
    return (s.get("cs") or "").title()


def sigle_departement(s):
    v = param("sigle_dep")
    if v:
        return v
    import m_juridiction as J
    return J.norm((s or {}).get("departement") or "")[:1]


def prochain_numero(annee=None):
    a = annee or config.ANNEE_ACTIVE
    r = q("SELECT MAX(numero) m FROM jur_docs_historique WHERE annee=?", (a,), un=True)
    depart = int(param(f"registre_depart:{a}", 1) or 1)
    return max((r["m"] or 0) + 1, depart)


def reference(doc, numero, s, ecole=""):
    s = s or {}
    n = f"{numero:03d}" if isinstance(numero, int) else str(numero or "……")
    dsig = sigle_departement(s)
    cs = (s.get("cs") or "").upper()
    if DOCS[doc]["famille"] == "ame":
        return f"N° {n}/{config.ANNEE_ACTIVE}/DIR/{ecole or '……'}" + (f"/CS-{cs}" if cs else "")
    cs_part = f"/CS-{cs}" if (s.get("niveau") == "cs" and cs) else ""
    if doc in ("presence_poste_dir", "attestation_prise_service_dir"):
        return f"SO N° {n}/{ecole or 'EPP/EM'}{cs_part}/DDEMP-{dsig}/SP"
    if doc == "prise_en_charge":
        return f"S0N° {n}{cs_part}/DDEMP-{dsig}"
    return f"SO N° {n}{cs_part}/DDEMP-{dsig}/SP"


def numero_de_ref(ref):
    m = re.search(r"N°\s*0*(\d+)", ref or "")
    return int(m.group(1)) if m else None


def qualite_signataire(titre, s, code):
    """« Le Chef de la Circonscription Scolaire » → « Chef de la Circonscription Scolaire de Pobè »."""
    t = re.sub(r"^(Le|La|L')\s*", "", (titre or "").strip())
    if not code or code in RACINE.values():
        if niveau() == "cs" and "Circonscription" in t and " de " not in t.split("Circonscription")[-1]:
            t = f"{t} de {ville_cs(s)}"
        elif niveau() == "ddemp" and s.get("departement") and "Départemental" in t and "Enseignements" not in t:
            t = f"{t} des Enseignements Maternel et Primaire {nom_dep_complet(s['departement'])}"
    return t


def genre_titre(titre):
    t = (titre or "").lower()
    return "F" if t.startswith("la ") or "cheffe" in t or "directrice" in t else "M"


# ================================================================================================ module Flask
def enregistrer(app, H):
    H.schema(SCHEMA)
    for col in ("parent_code", "reference", "note", "signataire_titre"):
        H.ajouter_colonne("jur_services", col, "TEXT")
    H.jur_cachet = jur_cachet
    H.jur_griffe = jur_griffe
    H.jur_signataire = jur_signataire
    H.jur_services = services
    try:  # libellés pour la page /verifier
        import sys
        for nom_mod in ("app", "__main__"):
            td = getattr(sys.modules.get(nom_mod), "TYPES_DOCS", None)
            if isinstance(td, dict):
                for k, d in DOCS.items():
                    td.setdefault(f"jurdoc_{k}", d["nom"])
    except Exception:  # noqa: BLE001
        pass

    def juridiction_ou_404():
        if not config.juridiction():
            abort(404)

    # ------------------------------------------------------------------ services et attributions
    @app.route("/juridiction/services")
    @H.connexion_requise()
    def jur_organigramme():
        juridiction_ou_404()
        s = structure()
        tous = services(actifs=False)
        noms = {x["code"]: x["nom"] for x in tous}
        for x in tous:
            x["parent_nom"] = noms.get(x["parent_code"] or "", "")
        actifs = [x for x in tous if x["actif"]]
        rangs = organigramme_donnees() if s else []
        if request.args.get("export") == "pdf":
            H.journal("jur_organigramme_pdf", "")
            return H.pdf_reponse(pdf_organigramme(rangs, actifs, s), "organigramme_attributions.pdf")
        nb_ag = {}
        for a in agents_structure():
            nb_ag[a["service_code"] or ""] = nb_ag.get(a["service_code"] or "", 0) + 1
        import m_juridiction as J
        kpi = dict(services=len(actifs), inactifs=len(tous) - len(actifs), agents=len(agents_structure()),
                   cs=len(J.cs_liste()), zones=len(J.zones()), ecoles=len(J.ecoles()))
        return render_template("jur_organigramme.html", s=s, services=tous, svg=organigramme_svg(rangs) if rangs else "",
                               nb_ag=nb_ag, kpi=kpi, racine=RACINE.get(niveau()))

    @app.route("/juridiction/services/nouveau", methods=["GET", "POST"])
    @app.route("/juridiction/services/<int:sid>", methods=["GET", "POST"])
    @H.connexion_requise("jur_structure")
    def jur_service_form(sid=None):
        juridiction_ou_404()
        tous = services(actifs=False)
        svc = service_par_id(sid) if sid else None
        if sid and not svc:
            abort(404)
        agents = agents_structure()
        if request.method == "POST":
            f = request.form
            d = {k: (f.get(k) or "").strip() for k in ("nom", "sigle", "attributions", "parent_code", "reference",
                                                        "note", "signataire_titre")}
            d["attributions"] = d["attributions"][:8000]
            d["note"] = d["note"][:3000]
            erreurs = []
            try:
                ordre = int(f.get("ordre") or 0)
            except ValueError:
                ordre, _ = 0, erreurs.append("Ordre : nombre entier attendu.")
            resp = f.get("responsable_id", type=int)
            if resp and resp not in {a["id"] for a in agents}:
                erreurs.append("Responsable inconnu (choisissez un agent de la structure).")
            if not d["nom"]:
                erreurs.append("Le nom du service est obligatoire.")
            codes = {x["code"] for x in tous}
            if svc:
                code = svc["code"]
            else:
                import m_juridiction as J
                base = re.sub(r"[^a-z0-9]+", "_", J.norm(d["sigle"] or d["nom"]).lower()).strip("_")[:24] or "service"
                code, i = base, 2
                while code in codes:
                    code, i = f"{base}_{i}", i + 1
            # le service parent doit exister et ne pas créer de boucle
            if d["parent_code"]:
                if d["parent_code"] not in codes or d["parent_code"] == code:
                    erreurs.append("Service de rattachement invalide.")
                else:
                    par = {x["code"]: x["parent_code"] for x in tous}
                    p, vus = d["parent_code"], set()
                    while p and p not in vus:
                        if p == code:
                            erreurs.append("Rattachement impossible : il créerait une boucle.")
                            break
                        vus.add(p)
                        p = par.get(p)
            if svc and svc["code"] == RACINE.get(niveau()):
                d["parent_code"] = ""
            elif not d["parent_code"]:
                d["parent_code"] = RACINE.get(niveau())
            actif = 1 if f.get("actif") == "1" or (svc and svc["code"] == RACINE.get(niveau())) else 0
            if erreurs:
                for m in erreurs:
                    flash(m, "danger")
                vals = dict(d, ordre=f.get("ordre"), responsable_id=resp, actif=actif, code=code if svc else "")
                return render_template("jur_service_form.html", v=vals, svc=svc, services=tous, agents=agents), 400
            if svc:
                ex("UPDATE jur_services SET nom=?, sigle=?, attributions=?, ordre=?, responsable_id=?, parent_code=?, "
                   "reference=?, note=?, signataire_titre=?, actif=? WHERE id=?",
                   (d["nom"], d["sigle"], d["attributions"], ordre, resp, d["parent_code"], d["reference"], d["note"],
                    d["signataire_titre"], actif, sid))
                H.journal("jur_service_modifie", d["nom"])
                flash("Service enregistré.", "success")
            else:
                sid = ex("INSERT INTO jur_services (niveau, code, nom, sigle, attributions, ordre, responsable_id, actif, "
                         "parent_code, reference, note, signataire_titre) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (niveau(), code, d["nom"], d["sigle"], d["attributions"], ordre or (len(tous) + 1), resp, 1,
                          d["parent_code"], d["reference"], d["note"], d["signataire_titre"]))
                H.journal("jur_service_ajoute", d["nom"])
                flash("Service ajouté à l'organigramme.", "success")
            return redirect(url_for("jur_organigramme"))
        v = dict(svc) if svc else {"ordre": len(tous) + 1, "actif": 1, "parent_code": RACINE.get(niveau())}
        return render_template("jur_service_form.html", v=v, svc=svc, services=tous, agents=agents)

    @app.route("/juridiction/services/<int:sid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_structure")
    def jur_service_supprimer(sid):
        juridiction_ou_404()
        svc = service_par_id(sid) or abort(404)
        if svc["code"] == RACINE.get(niveau()):
            flash("Le service du responsable de la structure ne peut pas être désactivé.", "danger")
        elif svc["actif"]:
            ex("UPDATE jur_services SET actif=0 WHERE id=?", (sid,))
            ex("UPDATE jur_services SET parent_code=? WHERE niveau=? AND parent_code=?",
               (svc["parent_code"] or RACINE.get(niveau()), niveau(), svc["code"]))
            H.journal("jur_service_desactive", svc["nom"])
            flash(f"« {svc['nom']} » désactivé (il ne figure plus dans l'organigramme ; réactivable).", "success")
        elif svc["code"] in {x[0] for x in SERVICES_DEFAUT[niveau()]}:
            flash("Service prévu par les textes : il reste disponible (désactivé) et peut être réactivé.", "info")
        else:
            ex("DELETE FROM jur_services WHERE id=?", (sid,))
            H.journal("jur_service_supprime", svc["nom"])
            flash(f"« {svc['nom']} » supprimé définitivement.", "success")
        return redirect(url_for("jur_organigramme"))

    # ------------------------------------------------------------------ cachets et signatures
    @app.route("/juridiction/cachets", methods=["GET", "POST"])
    @H.connexion_requise("jur_structure")
    def jur_cachets():
        juridiction_ou_404()
        s = structure()
        tous = services()
        if request.method == "POST":
            f = request.form
            cible = f.get("cible", "")
            vals = {k: (f.get(k) or "").strip()[:80] for k in ("sup", "inf", "centre")}
            vals["couleur"] = f.get("couleur") if f.get("couleur") in COULEURS else "bleu"
            titre = (f.get("signataire_titre") or "").strip()[:150]
            if f.get("action") == "defaut":
                vals = {"sup": "", "inf": "", "centre": "", "couleur": "bleu"}
            code_griffe = None
            if cible == "structure":
                param_ecrire("cachet_structure", vals)
                H.journal("jur_cachet", "structure")
            else:
                svc = service_par_id(int(cible) if cible.isdigit() else 0) or abort(404)
                ex("UPDATE jur_services SET cachet_sup=?, cachet_inf=?, cachet_centre=?, cachet_couleur=?, "
                   "signataire_titre=? WHERE id=?",
                   (vals["sup"], vals["inf"], vals["centre"], vals["couleur"], titre or svc["signataire_titre"], svc["id"]))
                H.journal("jur_cachet", svc["nom"])
                code_griffe = svc["code"]
            # griffe (cachet rectangulaire du nom) : actif, 3e ligne, couleur (vide = couleur du cachet)
            param_ecrire(griffe_cle(code_griffe, "actif"), 1 if f.get("griffe_actif") == "1" else 0)
            param_ecrire(griffe_cle(code_griffe, "ligne3"), (f.get("griffe_ligne3") or "").strip()[:80])
            param_ecrire(griffe_cle(code_griffe, "couleur"), f.get("griffe_couleur") if f.get("griffe_couleur") in COULEURS else "")
            flash("Cachet rétabli par défaut." if f.get("action") == "defaut" else "Cachet enregistré.", "success")
            return redirect(url_for("jur_cachets") + (f"#c-{cible}"))
        lignes = [{"cible": "structure", "nom": (s or {}).get("nom") or "Structure", "cachet": cachet_structure(),
                   "perso": bool(param("cachet_structure", {}).get("sup") if param("cachet_structure") else False),
                   "sig": jur_signataire(None), "cle_sig": "jur:structure:responsable", "titre_mod": False, "code": "",
                   "griffe": jur_griffe(None), "griffe_reg": jur_griffe_reglages(None)}]
        for x in tous:
            if x["code"] == RACINE.get(niveau()):
                continue
            lignes.append({"cible": str(x["id"]), "nom": f"{x['sigle'] or ''} – {x['nom']}".strip(" –"),
                           "cachet": jur_cachet(x["code"]), "perso": bool(x["cachet_sup"] or x["cachet_centre"]),
                           "sig": jur_signataire(x["code"]), "cle_sig": f"jur:service:{x['id']}", "titre_mod": True, "code": x["code"],
                           "titre": x["signataire_titre"] or titre_service(x),
                           "griffe": jur_griffe(x["code"]), "griffe_reg": jur_griffe_reglages(x["code"])})
        if request.args.get("export") == "pdf":
            return H.pdf_reponse(pdf_cachets([(l["nom"], l["cachet"], l["sig"], l["griffe"]) for l in lignes]),
                                 "cachets.pdf")
        return render_template("jur_cachets.html", s=s, lignes=lignes, COULEURS=COULEURS,
                               svg=lambda ca: CACHET.svg(*ca, taille=150))

    @app.route("/juridiction/cachets/apercu.svg")
    @H.connexion_requise()
    def jur_cachet_apercu():
        juridiction_ou_404()
        a = request.args
        if any(a.get(k) for k in ("sup", "inf", "centre")):
            ca = (a.get("sup", "")[:80], a.get("inf", "")[:80], a.get("centre", "")[:80],
                  a.get("couleur") if a.get("couleur") in COULEURS else "bleu")
        else:
            ca = jur_cachet(a.get("service") or None)
        return Response(CACHET.svg(*ca, taille=int(a.get("taille") or 180) if (a.get("taille") or "").isdigit() else 180),
                        mimetype="image/svg+xml", headers={"Cache-Control": "no-cache"})

    @app.route("/juridiction/cachets/griffe.svg")
    @H.connexion_requise()
    def jur_griffe_apercu():
        """Aperçu SVG de la griffe de la structure (code vide) ou d'un service (code=…) ; ligne3 / couleur / titre
        de l'adresse pour l'aperçu instantané pendant la saisie."""
        juridiction_ou_404()
        a = request.args
        code = a.get("code") or None
        gr = jur_griffe(code, forcer=True)
        if gr is None:
            titre, nom, _s = jur_signataire(code)
            gr = [titre, nom or "NOM Prénoms (responsable à désigner)", ""], "bleu"
        lignes, couleur = list(gr[0]), gr[1]
        if a.get("titre"):
            lignes[0] = a.get("titre")[:150]
        if "ligne3" in a:
            lignes = lignes[:2] + [a.get("ligne3", "")[:80]]
        if a.get("couleur") in COULEURS:
            couleur = a.get("couleur")
        largeur = int(a.get("largeur") or 260) if (a.get("largeur") or "").isdigit() else 260
        return Response(CACHET.svg_nom(lignes, couleur, max(120, min(largeur, 600))), mimetype="image/svg+xml",
                        headers={"Cache-Control": "no-cache"})

    @app.route("/juridiction/cachets/apercu.pdf")
    @H.connexion_requise()
    def jur_cachet_apercu_pdf():
        """Aperçu du cachet tel qu'il sera imprimé (cachet.dessiner)."""
        juridiction_ou_404()
        a = request.args
        ca = jur_cachet(a.get("service") or None)
        buf = io.BytesIO()
        c = GCanvas(buf, pagesize=(90 * mm, 90 * mm))
        CACHET.dessiner(c, 45 * mm, 47 * mm, 38 * mm, *ca)
        c.showPage()
        c.save()
        return H.pdf_reponse(buf.getvalue(), "cachet.pdf")

    # ------------------------------------------------------------------ documents : données
    def personnes(cs_id=None, ecole_id=None, recherche=None):
        """Personnel de la juridiction avec une clé stable : e<école>-<rang> (écoles) ou a<agent> (agents)."""
        out, rang = [], {}
        for p in H.jur_personnel(config.ANNEE_ACTIVE, cs_id or None):
            if p.get("source") == "agent":
                p["cle"] = f"a{p['agent_id']}"
            else:
                rang[p["ecole_id"]] = rang.get(p["ecole_id"], 0) + 1
                p["cle"] = f"e{p['ecole_id']}-{rang[p['ecole_id']]}"
            out.append(p)
        if ecole_id:
            out = [p for p in out if p.get("ecole_id") == ecole_id or (ecole_id == -1 and p.get("source") == "agent")]
        if recherche:
            import m_juridiction as J
            r = J.norm(recherche)
            out = [p for p in out if r in J.norm(f"{p.get('nom')} {p.get('prenoms')} {p.get('nip')} {p.get('matricule')}")]
        return out

    def personne(cle):
        if not cle:
            return None
        m = re.match(r"^(e(\d+)-\d+|a(\d+))$", cle)
        if not m:
            return None
        ecole_id = int(m.group(2)) if m.group(2) else None
        for p in personnes(ecole_id=ecole_id):
            if p["cle"] == cle:
                return p
        return None

    def defauts(doc, p, sig_code, numero=None):
        import m_juridiction as J
        s = structure() or {}
        titre, nom, _sig = jur_signataire(sig_code)
        e = J.ecole(p["ecole_id"]) if p and p.get("ecole_id") else None
        v = dict(signataire_titre=titre, signataire_nom=nom, signataire_qualite=qualite_signataire(titre, s, sig_code),
                 signataire_genre=genre_titre(titre), fait_a=s.get("ville") or ville_cs(s) or "", fait_le=aujourdhui(),
                 departement_agent=s.get("departement") or "", cs_agent=(s.get("cs") or "").upper(),
                 affecte_cs=(s.get("cs") or "").upper() if niveau() == "cs" else "", jusqu_au=aujourdhui(),
                 titre_doc=DOCS[doc]["titre"], ame_departement=s.get("departement") or "", edition=config.ANNEE_ACTIVE)
        if p:
            sexe = (p.get("sexe") or "").upper()[:1]
            fonction = p.get("poste") or p.get("fonction") or ""
            grade = p.get("grade") or ""
            ps_ecole = date_fr(p.get("date_ps_ecole"))
            v.update(civilite="Mme" if sexe == "F" else ("Mr" if sexe == "M" else ""),
                     nom_prenoms=f"{(p.get('nom') or '').upper()} {p.get('prenoms') or ''}".strip(),
                     nip=p.get("nip") or "", matricule=p.get("matricule") or "", grade=grade,
                     date_naissance=date_fr(p.get("date_naissance")), lieu_naissance=p.get("lieu_naissance") or "",
                     date_prise_service=date_fr(p.get("date_premiere_ps")), corps=p.get("fonction") or "",
                     corps_grade=" – ".join(x for x in (p.get("fonction") or "", grade) if x),
                     en_service_a=p.get("ecole_nom") or s.get("nom") or "", fonction=fonction,
                     depuis=ps_ecole, pour_compter=ps_ecole, date_effective=ps_ecole,
                     affecte_a=p.get("ecole_nom") or s.get("nom") or "",
                     direction_de=p.get("ecole_nom") if p.get("role") == "directeur" else "",
                     profession=fonction, indice=str(p.get("indice_paye") or ""),
                     titulaire_de=p.get("diplome_academique") or "", date_service=ps_ecole,
                     classe_attribuee=p.get("classe") or "", cs_agent=(p.get("cs_nom") or s.get("cs") or "").upper())
            if niveau() == "ddemp":
                v["affecte_cs"] = (f"la Circonscription Scolaire de {p['cs_nom'].upper()}" if p.get("cs_nom") else
                                   f"la DDEMP {nom_dep_complet(s.get('departement') or '')}".strip())
            elif p.get("cs_nom"):
                v["affecte_cs"] = p["cs_nom"].upper()
        if e:
            eff = J.section(e["id"], "effectifs") or {}
            v.update(ecole=e["nom"], soussigne=e["directeur_nom"] or "", directeur_titre=e["directeur_titre"] or "",
                     localite=e["localite"] or e["commune"] or "", nb_classes=str(len(eff.get("classes") or []) or ""),
                     ame_type=e["type"] if e["type"] in ("EP", "EM") else "", ame_ecole=e["nom"],
                     dir_nom=e["directeur_nom"] or "", dir_tel=e["directeur_tel"] or "",
                     lieu_visa=e["localite"] or e["commune"] or "")
            if e["zone_id"]:
                z = q("SELECT * FROM jur_zones WHERE id=?", (e["zone_id"],), un=True)
                if z:
                    v.update(cp_nom=z["cp_nom"] or "", cp_tel=z["cp_telephone"] or "")
        v["ref"] = reference(doc, numero if numero is not None else prochain_numero(), s,
                             (e["nom"] if e else "") if DOCS[doc]["famille"] != "ame" else (e["code"] if e else ""))
        return v

    def doc_ou_404(doc):
        if doc not in DOCS:
            abort(404)
        return DOCS[doc]

    def griffe_dir_ecole(jur_ecole_id):
        """Griffe du directeur d'une école de la juridiction, si cette école est aussi gérée localement
        (ecoles.jur_ecole_id) et que sa griffe est active."""
        if not jur_ecole_id or not getattr(H, "griffe_ecole", None):
            return None
        try:
            r = q("SELECT id FROM ecoles WHERE jur_ecole_id=?", (jur_ecole_id,), un=True)
            return H.griffe_ecole(r["id"]) if r else None
        except Exception:  # noqa: BLE001
            return None

    def options(sig_code, signer, code=None, vierge=False, jur_ecole_id=None):
        _t, _n, sig = jur_signataire(sig_code)
        return dict(structure=structure() or {}, sigle_dep=sigle_departement(structure()), signer=signer,
                    cachet=jur_cachet(sig_code), sig=sig, code=code, vierge=vierge, griffe=jur_griffe(sig_code),
                    griffe_dir=griffe_dir_ecole(jur_ecole_id))

    def signataires():
        """Choix du signataire : responsable de la structure, ou chef d'un service (par délégation)."""
        out = [("", "Responsable de la structure")]
        for x in services():
            if x["code"] != RACINE.get(niveau()) and x["responsable_id"]:
                out.append((x["code"], f"{x['sigle'] or x['nom']} – {x['responsable_nom']}"))
        return out

    # ------------------------------------------------------------------ documents : pages
    @app.route("/juridiction/documents", methods=["GET", "POST"])
    @H.connexion_requise("jur_documents")
    def jur_documents():
        juridiction_ou_404()
        s = structure()
        if request.method == "POST":
            if not H.peut("jur_structure"):
                abort(403)
            sd = re.sub(r"[^A-Za-z0-9-]", "", request.form.get("sigle_dep") or "").upper()[:10]
            dep = request.form.get("depart", "")
            if dep and (not dep.isdigit() or not 1 <= int(dep) <= 99999):
                flash("Premier numéro du registre : nombre entier entre 1 et 99999.", "danger")
            else:
                if dep:
                    param_ecrire(f"registre_depart:{config.ANNEE_ACTIVE}", int(dep))
                param_ecrire("sigle_dep", sd)
                flash("Paramètres du registre enregistrés.", "success")
            return redirect(url_for("jur_documents"))
        a = config.ANNEE_ACTIVE
        par_type = {r["type"]: r["n"] for r in q("SELECT type, COUNT(*) n FROM jur_docs_historique WHERE annee=? "
                                                  "GROUP BY type", (a,))}
        recents = q("SELECT h.*, u.nom auteur FROM jur_docs_historique h LEFT JOIN utilisateurs u ON u.id=h.cree_par "
                    "ORDER BY h.id DESC LIMIT 8")
        return render_template("jur_documents.html", s=s, DOCS=DOCS, par_type=par_type, recents=recents,
                               prochain=prochain_numero(), sigle_dep=sigle_departement(s), sigle_perso=param("sigle_dep"),
                               exemple=reference("presence_poste", prochain_numero(), s or {}), total=sum(par_type.values()))

    @app.route("/juridiction/documents/<doc>")
    @H.connexion_requise("jur_documents")
    def jur_document_form(doc):
        juridiction_ou_404()
        d = doc_ou_404(doc)
        import m_juridiction as J
        f = request.args
        cs_id = f.get("cs", type=int)
        ecole_id = f.get("ecole", type=int)
        sig_code = f.get("sig") or ""
        if sig_code and not service_par_code(sig_code):
            sig_code = ""
        liste = personnes(cs_id, ecole_id, f.get("q") or None)
        p = personne(f.get("p")) if f.get("p") else None
        v = defauts(doc, p, sig_code)
        return render_template("jur_document_form.html", doc=doc, d=d, v=v, p=p, liste=liste[:400], nb=len(liste),
                               f=f, cs=J.cs_liste(), ecoles=J.ecoles(cs_id=cs_id), sections=SECTIONS[doc], CHAMPS=CHAMPS,
                               sig_code=sig_code, signataires=signataires(), QUALITES=QUALITES_AME, s=structure())

    @app.route("/juridiction/documents/<doc>/pdf", methods=["POST"])
    @H.connexion_requise("jur_documents")
    def jur_document_pdf(doc):
        juridiction_ou_404()
        d = doc_ou_404(doc)
        f = request.form
        v = {k: (f.get(k) or "").strip()[:300] for k in cles_doc(doc)}
        erreurs = [f"{CHAMPS[k][0]} : date invalide (jj/mm/aaaa)." for k in cles_doc(doc)
                   if CHAMPS[k][1] == "date" and v.get(k) and not date_valide(v[k])]
        if v.get("civilite") and v["civilite"] not in ("Mr", "Mme", "Mlle"):
            erreurs.append("Civilité invalide.")
        if not v.get("nom_prenoms"):
            erreurs.append("Le nom et les prénoms de la personne sont obligatoires.")
        sig_code = f.get("sig") or ""
        if sig_code and not service_par_code(sig_code):
            sig_code = ""
        if erreurs:
            for m in erreurs[:6]:
                flash(m, "danger")
            return redirect(url_for("jur_document_form", doc=doc, p=f.get("p") or None, sig=sig_code or None))
        signer = f.get("signer") == "1"
        pers = personne(f.get("p")) if f.get("p") else None
        jur_eid = pers.get("ecole_id") if pers else None
        if f.get("action") != "enregistrer":       # brouillon : ni numéro, ni QR, ni historique
            return H.pdf_reponse(construire_pdf(doc, [(v, options(sig_code, False))], d["nom"] + " (brouillon)"),
                                 f"{doc}_brouillon.pdf")
        numero = numero_de_ref(v.get("ref"))
        if numero is None:
            numero = prochain_numero()
            v["ref"] = reference(doc, numero, structure() or {}, v.get("ecole") or "")
        elif q("SELECT 1 FROM jur_docs_historique WHERE annee=? AND numero=?", (config.ANNEE_ACTIVE, numero), un=True):
            flash(f"Le numéro {numero} est déjà utilisé au registre {config.ANNEE_ACTIVE} : numéro suivant attribué.",
                  "warning")
            ancien = numero
            numero = prochain_numero()
            v["ref"] = re.sub(r"(N°\s*)0*" + str(ancien), lambda m: f"{m.group(1)}{numero:03d}", v["ref"], count=1)
        lib = f"{d['nom']} – {v.get('nom_prenoms')}"
        code = H.enregistrer_document(f"jurdoc_{doc}", None, f"{lib} ({v['ref']})")
        titre_sig = v.get("signataire_titre") or jur_signataire(sig_code)[0]
        ex("INSERT INTO jur_docs_historique (annee, type, numero, ref, personne, libelle, donnees, code, signe, signataire, "
           "cree_le, cree_par) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
           (config.ANNEE_ACTIVE, doc, numero, v["ref"], f.get("p") or "", lib,
            json.dumps(dict(v, _sig=sig_code, _ecole_id=jur_eid), ensure_ascii=False), code, 1 if signer else 0, titre_sig,
            H.maintenant(), g.user["id"]))
        H.journal("jur_document", f"{v['ref']} {lib}")
        return H.pdf_reponse(construire_pdf(doc, [(v, options(sig_code, signer, code, jur_ecole_id=jur_eid))], lib),
                             f"{doc}_{numero:03d}.pdf")

    @app.route("/juridiction/documents/<doc>/vierge.pdf")
    @H.connexion_requise("jur_documents")
    def jur_document_vierge(doc):
        juridiction_ou_404()
        d = doc_ou_404(doc)
        s = structure() or {}
        v = {}
        if DOCS[doc]["famille"] == "jur" and DOCS[doc]["sig"] != ("dir",):
            titre, nom, _sig = jur_signataire(None)
            v = dict(signataire_titre=titre, signataire_nom=nom, signataire_qualite=qualite_signataire(titre, s, None),
                     signataire_genre=genre_titre(titre), cs_agent=(s.get("cs") or "").upper(),
                     departement_agent=s.get("departement") or "", titre_doc=d["titre"])
        return H.pdf_reponse(construire_pdf(doc, [(v, options(None, False, vierge=True))], d["nom"] + " (vierge)"),
                             f"{doc}_vierge.pdf")

    @app.route("/juridiction/documents/historique")
    @H.connexion_requise("jur_documents")
    def jur_document_historique():
        juridiction_ou_404()
        f = request.args
        sql, args = ("SELECT h.*, u.nom auteur FROM jur_docs_historique h LEFT JOIN utilisateurs u ON u.id=h.cree_par "
                     "WHERE 1=1"), []
        if f.get("type") in DOCS:
            sql += " AND h.type=?"
            args.append(f["type"])
        annees = [r["annee"] for r in q("SELECT DISTINCT annee FROM jur_docs_historique ORDER BY annee DESC")]
        a = f.get("annee") or config.ANNEE_ACTIVE
        if a != "toutes":
            sql += " AND h.annee=?"
            args.append(a)
        if f.get("q"):
            sql += " AND (h.libelle LIKE ? OR h.ref LIKE ? OR h.code LIKE ?)"
            args += [f"%{f['q']}%"] * 3
        lignes = q(sql + " ORDER BY h.annee DESC, h.numero DESC, h.id DESC LIMIT 1000", tuple(args))
        if f.get("export") == "xlsx":
            return H.xlsx.reponse_xlsx("registre_documents.xlsx", ["N°", "Référence", "Document", "Personne / libellé",
                                                                    "Signé", "Signataire", "Code QR", "Date", "Par"],
                                       [[l["numero"], l["ref"], DOCS.get(l["type"], {}).get("nom", l["type"]), l["libelle"],
                                         "Oui" if l["signe"] else "Non", l["signataire"] or "", l["code"] or "",
                                         l["cree_le"], l["auteur"] or ""] for l in lignes],
                                       "Registre", [config.ECOLE.get("nom", ""), f"Registre des attestations – {a}"])
        return render_template("jur_document_historique.html", lignes=lignes, DOCS=DOCS, f=f, annees=annees, annee=a)

    @app.route("/juridiction/documents/historique/<int:hid>.pdf")
    @H.connexion_requise("jur_documents")
    def jur_document_reimprimer(hid):
        juridiction_ou_404()
        h = q("SELECT * FROM jur_docs_historique WHERE id=?", (hid,), un=True) or abort(404)
        if h["type"] not in DOCS:
            abort(404)
        try:
            v = json.loads(h["donnees"])
        except ValueError:
            abort(404)
        sig_code = v.pop("_sig", "") or ""
        jur_eid = v.pop("_ecole_id", None)
        if sig_code and not service_par_code(sig_code):
            sig_code = ""
        H.journal("jur_document_reimpression", h["ref"] or "")
        return H.pdf_reponse(construire_pdf(h["type"], [(v, options(sig_code, bool(h["signe"]), h["code"],
                                                                     jur_ecole_id=jur_eid))],
                                            h["libelle"] + " (réimpression)"), f"{h['type']}_{h['numero'] or hid}.pdf")
