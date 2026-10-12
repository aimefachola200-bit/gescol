# -*- coding: utf-8 -*-
"""Personnel et gestion de carrière des applications « GESCOL Circonscription » (CS) et « GESCOL DDEMP ».

Sources des données (lecture) :
* personnel des écoles : section « personnel » des paquets de transmission (H.jur_personnel) ;
* agents de la structure : table jur_agents (gérée ici : CCS, CP, chefs de division / de service,
  administratifs, soutien) — colonnes de la table + JSON `donnees` pour les autres clés PERSONNE ;
* en DDEMP, agents des CS : section « agents » des paquets des CS (H.jur_cs_section), en lecture seule.

Règles de calcul (identiques à m_carriere, dont les fonctions sont réutilisées par import) :
* anciennetés au 31/12 de l'année civile en cours (31/12 inclus), en années et mois révolus ; pour une
  année scolaire passée « AAAA-BBBB » : au 31/12/AAAA ;
* départ probable à la retraite : naissance + 60 ans (grade A), 58 ans (B), 55 ans (C) ; né(e) un 29/02 :
  28/02 si l'année de départ n'est pas bissextile ; année de naissance seule : 31/12 de l'année.

Pages : jur_personnel (onglets par catégorie), jur_personnel_fiche, jur_aptitude, jur_retraite,
jur_agents, jur_agent_form, jur_agent_supprimer, jur_agents_import.
Exposé : H.jur_retraites_proches(annee, cs_id=None, ans=2).
"""
import json
import re
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

import config
import jur_calc
import jur_format
import m_carriere as MC   # fonctions pures de calcul (ancienneté, retraite, formats) — non modifié

ROLES_ENS = ("directeur", "adjoint", "enseignant")
ROLES_AGENT = {k: v for k, v in jur_format.ROLES_PERSONNE.items() if k not in ROLES_ENS}
CATEGORIES = jur_format.CATEGORIES
RE_GRADE = re.compile(r"^[A-E]([1-3](-(1[0-5]|[1-9]))?)?$")
SEXES = {"M": "Masculin", "F": "Féminin"}

# services par défaut (si la table jur_services ne contient rien pour le niveau)
SERVICES_DEFAUT = {
    "cs": [("ccs", "Chef de la Circonscription Scolaire (CCS)"), ("animation", "Animation pédagogique (CP, CDAP)"),
           ("secretariat", "Division Secrétariat (CDS)"), ("personnel", "Service des Ressources Humaines (RH)"),
           ("organisation", "Organisation scolaire et prévision (CDOSP)"), ("administration", "Administration et soutien")],
    "ddemp": [("direction", "Direction départementale (DD)"), ("sec", "Service des Examens et Concours (SEC)"),
              ("semp", "Service des Écoles Maternelles et Primaires (SEMP)"),
              ("srh", "Service des Ressources Humaines (SRH)"),
              ("spaf", "Service de la Planification, de l'Administration et des Finances (SPAF)"),
              ("cantines", "Service des cantines scolaires"), ("statistiques", "Service des statistiques"),
              ("infrastructures", "Service des infrastructures et équipements"),
              ("secretariat", "Secrétariat"), ("administration", "Administration et soutien")],
}
POSTES = {
    "cs": ["Chef de la Circonscription Scolaire (CCS)", "Conseiller pédagogique (CP)", "Chef Division Secrétariat (CDS)",
           "Chef du Service des Ressources Humaines (RH)", "Chef Division Animation Pédagogique (CDAP)",
           "Chef Division Organisation Scolaire et Prévision (CDOSP)", "Secrétaire", "Agent d'entretien", "Gardien",
           "Chauffeur", "Planton"],
    "ddemp": ["Directeur Départemental (DD)", "Directeur Départemental Adjoint", "Chef du Service des Examens et Concours",
              "Chef du Service des Écoles Maternelles et Primaires", "Chef du Service des Ressources Humaines",
              "Chef du Service de la Planification, de l'Administration et des Finances",
              "Chef du Service des cantines scolaires", "Chef du Service des statistiques",
              "Chef du Service des infrastructures", "Secrétaire", "Agent d'entretien", "Gardien", "Chauffeur", "Planton"],
}

# ------------------------------------------------------------------ champs d'un agent (formulaire, import, export)
# (clé PERSONNE, libellé, type)  — l'ordre est celui du formulaire et du fichier Excel
CHAMPS_AGENT = [
    ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"), ("sexe", "Sexe (M/F)", "sexe"),
    ("nip", "NIP", "nip"), ("matricule", "Matricule", "texte"), ("date_naissance", "Date de naissance", "naissance"),
    ("telephone", "Téléphone", "texte"), ("email", "E-mail", "texte"),
    ("service_code", "Service (code)", "service"), ("poste", "Poste", "texte"), ("fonction", "Fonction", "texte"),
    ("role", "Rôle (ccs, cp, chef_service, administratif, soutien)", "role"),
    ("categorie", "Catégorie (FE, ACDPE, ACDPCTD, AUTRE)", "categorie"), ("grade", "Grade", "grade"),
    ("indice_paye", "Indice payé", "indice"), ("indice_reel", "Indice réel", "indice"),
    ("date_premiere_ps", "Date de première prise de service", "date"),
    ("date_ps_departement", "Prise de service dans le département", "date"),
    ("date_ps_commune", "Prise de service dans la commune", "date"),
    ("date_ps_ecole", "Prise de service au poste (service)", "date"),
    ("departement_a_servir", "Département à servir", "departement"),
    ("diplome_academique", "Diplôme académique", "texte"), ("annee_diplome", "Année du diplôme académique", "annee"),
    ("ceap", "CEAP (oui/non)", "bool"), ("annee_ceap", "Année du CEAP", "annee"),
    ("cap", "CAP (oui/non)", "bool"), ("annee_cap", "Année du CAP", "annee"), ("type_cap", "Type de CAP (EP/EM)", "type_cap"),
    ("visite_aptitude", "Visite d'aptitude (oui/non)", "bool"), ("note_aptitude", "Note de la visite d'aptitude", "note"),
    ("annee_aptitude", "Année de la visite d'aptitude", "annee"),
    ("nb_visites_cp", "Visites du CP", "compte"), ("nb_visites_ccs", "Visites du CCS", "compte"),
    ("participation_up", "Participation à l'UP (%)", "pct"), ("gestion_collegiale", "Gestion collégiale", "texte"),
    ("note_evaluation", "Note d'évaluation", "note"), ("actif", "En activité (oui/non)", "bool"),
]
COLONNES_TABLE = ("service_code", "poste", "nom", "prenoms", "sexe", "nip", "matricule", "telephone", "email")
LIB_CHAMP = {k: lib for k, lib, _t in CHAMPS_AGENT}


# ======================================================================== utilitaires de lecture
def vrai(v):
    """Booléen tolérant (True, « oui », « 1 »…)."""
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("oui", "o", "1", "true", "vrai", "yes", "x")


def tri_etat(v):
    """'oui' | 'non' | '' (non renseigné)."""
    if v is True or vrai(v):
        return "oui"
    if v is False or str(v or "").strip().lower() in ("non", "n", "0", "false", "faux", "no"):
        return "non"
    return ""


def nombre(v):
    """Nombre (float) ou None."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(str(v).replace(",", ".").replace(" ", "").rstrip("%"))
    except ValueError:
        return None


def iso(v):
    """Date ISO (texte) ou None, tolérante (jj/mm/aaaa accepté)."""
    try:
        return MC.lire_date(str(v or "")[:10]) if v else None
    except ValueError:
        return None


def iso_naissance(v):
    try:
        return MC.lire_naissance(str(v or "")[:10]) if v else None
    except ValueError:
        return None


def fmt_n(v, suffixe=""):
    x = nombre(v)
    return MC.fmt_nombre(x if x is None or not x.is_integer() else int(x), suffixe) if x is not None else ""


def reference(annee_):
    """Date de calcul des anciennetés : 31/12 de l'année en cours (année active) ou 31/12/AAAA (année passée)."""
    if annee_ == config.ANNEE_ACTIVE or not re.match(r"^\d{4}", annee_ or ""):
        return MC.date_reference()
    return date(int(annee_[:4]), 12, 31)


# ======================================================================== fiche calculée d'une personne
def fiche(p, ref, auj=None, services=None):
    """dict PERSONNE enrichi (H.jur_personnel ou agents des CS) → dict avec les valeurs calculées et formatées."""
    auj = auj or date.today()
    f = dict(p)
    f["role"] = f.get("role") or ("enseignant" if f.get("source") == "ecole" else "administratif")
    f["nom_complet"] = f"{f.get('nom') or ''} {f.get('prenoms') or ''}".strip()
    f["sexe"] = (f.get("sexe") or "").upper()[:1]
    f["categorie"] = f.get("categorie") or ""
    f["categorie_lib"] = {"ACDPCTD": "ACDPCTD (AME)", "PRIVE": "Privé"}.get(f["categorie"], f["categorie"])
    f["grade"] = str(f.get("grade") or "").strip().upper()
    if f.get("source") == "ecole":
        f["ecole_service"] = f.get("ecole_nom") or ""
        f["fonction_txt"] = f.get("fonction") or jur_format.ROLES_PERSONNE.get(f["role"], "")
    else:
        svc = (services or {}).get(f.get("service_code") or "", f.get("service_code") or "")
        lieu = ("CS " + f["cs_nom"]) if f.get("source") == "agent_cs" and f.get("cs_nom") else ""
        f["ecole_service"] = " – ".join(x for x in (lieu, svc) if x) or ("Agent de la structure")
        f["fonction_txt"] = f.get("poste") or f.get("fonction") or ROLES_AGENT.get(f["role"], "")
    # dates et anciennetés
    f["naissance_iso"] = iso_naissance(f.get("date_naissance"))
    f["naissance_txt"] = MC.fmt_date(f["naissance_iso"]).replace("(année) ", "") if f["naissance_iso"] else ""
    f["annee_naissance"] = int(f["naissance_iso"][:4]) if f["naissance_iso"] else None
    f["ps"] = {k: iso(f.get(c)) for k, c in (("generale", "date_premiere_ps"), ("departement", "date_ps_departement"),
                                             ("commune", "date_ps_commune"), ("ecole", "date_ps_ecole"))}
    f["ps_txt"] = {k: MC.fmt_date(v) if v else "" for k, v in f["ps"].items()}
    f["reference"] = ref
    f["anc"] = {k: MC.anciennete(v, ref) if v else None for k, v in f["ps"].items()}
    f["anc_txt"] = {k: MC.fmt_duree(t, True) if t else "" for k, t in f["anc"].items()}
    # retraite
    f["lettre"] = MC.lettre_grade(f["grade"])
    f["age_retraite"] = MC.AGES_RETRAITE.get(f["lettre"])
    ret = MC.date_retraite(f["naissance_iso"], f["grade"]) if f["naissance_iso"] else None
    f["retraite"] = ret
    f["retraite_txt"] = MC.fmt_date(ret) if ret else ""
    f["retraite_atteinte"] = bool(ret and ret <= auj)
    f["alerte_retraite"] = bool(ret and ret <= MC.plus_ans(auj, 2))
    if ret and not f["retraite_atteinte"]:
        f["restant"] = divmod(MC.mois_ecoules(auj, ret), 12)
        f["restant_txt"] = MC.fmt_duree(f["restant"], True)
    else:
        f["restant"] = None
        f["restant_txt"] = "départ atteint" if ret else ""
    f["retraite_raison"] = "" if ret else ("grade inconnu ou hors catégories A, B, C" if not f["lettre"]
                                           else "date de naissance inconnue")
    # diplômes, aptitude, évaluation
    f["ceap_o"], f["cap_o"] = tri_etat(f.get("ceap")), tri_etat(f.get("cap"))
    f["type_cap"] = (f.get("type_cap") or "").upper()
    # EP / EM : type de CAP déclaré, sinon type de l'école (EM et espace enfance → EM)
    typ_ecole = "EM" if f.get("ecole_type") in ("EM", "EE") else ("EP" if f.get("ecole_type") == "EP" else "")
    f["cap_type_eff"] = f["type_cap"] if f["type_cap"] in ("EP", "EM") else typ_ecole
    f["ceap_type_eff"] = (f.get("type_ceap") or "").upper() if (f.get("type_ceap") or "").upper() in ("EP", "EM") else typ_ecole
    f["apt_o"] = tri_etat(f.get("visite_aptitude"))
    f["note_apt"] = nombre(f.get("note_aptitude"))
    f["note_eval"] = nombre(f.get("note_evaluation"))
    f["dip"] = (f.get("diplome_academique") or "").strip()
    return f


# ------------------------------------------------------------------ colonnes (écran / Excel / PDF)
def _an(f, k):
    v = f.get(k)
    return str(v) if v not in (None, "") else ""


COLS = {   # clé : (libellé écran / Excel, fonction valeur)
    "nip": ("NIP", lambda f: f.get("nip") or ""),
    "nom": ("Nom et prénoms", lambda f: f["nom_complet"]),
    "sexe": ("Sexe", lambda f: f["sexe"]),
    "fonction": ("Fonction / poste", lambda f: f["fonction_txt"]),
    "ecole": ("École / service", lambda f: f["ecole_service"]),
    "zone": ("Zone pédagogique", lambda f: f.get("zone_nom") or ""),
    "cs": ("CS", lambda f: f.get("cs_nom") or ""),
    "categorie": ("Catégorie", lambda f: f["categorie_lib"]),
    "grade": ("Grade", lambda f: f["grade"]),
    "ind_paye": ("Indice payé", lambda f: fmt_n(f.get("indice_paye"))),
    "ind_reel": ("Indice réel", lambda f: fmt_n(f.get("indice_reel"))),
    "naissance": ("Date de naissance", lambda f: f["naissance_txt"]),
    "ps1": ("1re prise de service", lambda f: f["ps_txt"]["generale"]),
    "ps_dep": ("PS département", lambda f: f["ps_txt"]["departement"]),
    "ps_com": ("PS commune", lambda f: f["ps_txt"]["commune"]),
    "ps_ecole": ("PS école / service", lambda f: f["ps_txt"]["ecole"]),
    "anc_gen": ("Anc. générale", lambda f: f["anc_txt"]["generale"]),
    "anc_dep": ("Anc. département", lambda f: f["anc_txt"]["departement"]),
    "anc_com": ("Anc. commune", lambda f: f["anc_txt"]["commune"]),
    "anc_ecole": ("Anc. école / service", lambda f: f["anc_txt"]["ecole"]),
    "retraite": ("Retraite (date probable)", lambda f: f["retraite_txt"]),
    "restant": ("Temps restant", lambda f: f["restant_txt"]),
    "dip": ("Diplôme académique", lambda f: f["dip"]),
    "dip_an": ("Année", lambda f: _an(f, "annee_diplome")),
    "ceap": ("CEAP", lambda f: f["ceap_o"]),
    "ceap_an": ("Année CEAP", lambda f: _an(f, "annee_ceap") if f["ceap_o"] == "oui" else ""),
    "cap": ("CAP", lambda f: (f["cap_o"] + (f" ({f['type_cap']})" if f["type_cap"] and f["cap_o"] == "oui" else ""))),
    "cap_an": ("Année CAP", lambda f: _an(f, "annee_cap") if f["cap_o"] == "oui" else ""),
    "apt": ("Visite d'aptitude", lambda f: f["apt_o"]),
    "apt_note": ("Note aptitude", lambda f: fmt_n(f["note_apt"])),
    "apt_an": ("Année aptitude", lambda f: _an(f, "annee_aptitude")),
    "dep_servir": ("Département à servir", lambda f: f.get("departement_a_servir") or ""),
    "vis_cp": ("Visites CP", lambda f: fmt_n(f.get("nb_visites_cp"))),
    "vis_ccs": ("Visites CCS", lambda f: fmt_n(f.get("nb_visites_ccs"))),
    "up": ("Participation UP (%)", lambda f: fmt_n(f.get("participation_up"))),
    "gestion": ("Gestion collégiale", lambda f: f.get("gestion_collegiale") or ""),
    "note_eval": ("Note d'évaluation", lambda f: fmt_n(f["note_eval"])),
}


def _pdf_diplomes(f):
    return f["dip"] + (f" ({f['annee_diplome']})" if f["dip"] and f.get("annee_diplome") else "")


def _pdf_pro(f):
    m = []
    if f["ceap_o"] == "oui":
        m.append("CEAP" + (f" {f['annee_ceap']}" if f.get("annee_ceap") else ""))
    if f["cap_o"] == "oui":
        m.append("CAP" + (f" {f['type_cap']}" if f["type_cap"] else "") + (f" {f['annee_cap']}" if f.get("annee_cap") else ""))
    return " / ".join(m) or ("non" if "non" in (f["ceap_o"], f["cap_o"]) else "")


def _pdf_apt(f):
    if f["apt_o"] != "oui":
        return f["apt_o"]
    return "oui" + (f" {fmt_n(f['note_apt'])}" if f["note_apt"] is not None else "") + \
        (f" ({f['annee_aptitude']})" if f.get("annee_aptitude") else "")


# colonnes PDF : (libellé court, largeur mm, fonction) ; certaines regroupent plusieurs colonnes écran
COLS_PDF = {
    "nip": ("NIP", 17.5, COLS["nip"][1]),
    "nom": ("Nom et prénoms (sexe)", 25, lambda f: f["nom_complet"] + (f" ({f['sexe']})" if f["sexe"] else "")),
    "fonction": ("Fonction", 14, COLS["fonction"][1]),
    "ecole": ("École / service\n(zone · CS)", 24,
              lambda f: f["ecole_service"] + ("\n" + " · ".join(x for x in (f.get("zone_nom"), f.get("cs_nom")) if x)
                                               if (f.get("zone_nom") or f.get("cs_nom")) else "")),
    "categorie": ("Caté-\ngorie", 11, COLS["categorie"][1]),
    "grade": ("Grade", 8.5, COLS["grade"][1]),
    "indices": ("Ind. payé\n/ réel", 10, lambda f: " / ".join(x or "—" for x in (fmt_n(f.get("indice_paye")),
                                                                                fmt_n(f.get("indice_reel")))).strip(" /—")),
    "naissance": ("Naissance", 12.5, COLS["naissance"][1]),
    "ps1": ("1re PS", 12.5, COLS["ps1"][1]), "ps_dep": ("PS dép.", 12.5, COLS["ps_dep"][1]),
    "ps_com": ("PS com.", 12.5, COLS["ps_com"][1]), "ps_ecole": ("PS école\n/ service", 12.5, COLS["ps_ecole"][1]),
    "anc_gen": ("Anc.\ngén.", 8, COLS["anc_gen"][1]), "anc_dep": ("Anc.\ndép.", 8, COLS["anc_dep"][1]),
    "anc_com": ("Anc.\ncom.", 8, COLS["anc_com"][1]), "anc_ecole": ("Anc.\nécole", 8, COLS["anc_ecole"][1]),
    "ret": ("Retraite\n(reste)", 13, lambda f: f["retraite_txt"] + (f"\n({f['restant_txt']})" if f["restant_txt"] else "")),
    "dip": ("Diplôme\nacadémique", 13, _pdf_diplomes),
    "pro": ("CEAP / CAP", 14, _pdf_pro),
    "apt": ("Aptitude\n(note, année)", 12, _pdf_apt),
    "dep_servir": ("Dép. à\nservir", 9, COLS["dep_servir"][1]),
    "vis": ("Vis.\nCP/CCS", 8, lambda f: "" if f.get("nb_visites_cp") in (None, "") and f.get("nb_visites_ccs") in (None, "")
            else f"{fmt_n(f.get('nb_visites_cp')) or '—'} / {fmt_n(f.get('nb_visites_ccs')) or '—'}"),
    "up": ("UP\n%", 6, COLS["up"][1]),
    "gestion": ("Gestion\ncollégiale", 11, COLS["gestion"][1]),
    "note_eval": ("Note\néval.", 7, COLS["note_eval"][1]),
}
# regroupements écran → PDF (la 1re colonne présente du groupe porte la colonne PDF)
GROUPES_PDF = {"sexe": "nom", "zone": "ecole", "cs": "ecole", "ind_paye": "indices", "ind_reel": "indices",
               "retraite": "ret", "restant": "ret", "dip_an": "dip", "ceap": "pro", "ceap_an": "pro", "cap": "pro",
               "cap_an": "pro", "apt_note": "apt", "apt_an": "apt", "vis_cp": "vis", "vis_ccs": "vis"}


def colonnes_pdf(cols):
    out = []
    for k in cols:
        k2 = GROUPES_PDF.get(k, k)
        if k2 in COLS_PDF and k2 not in out:
            out.append(k2)
    return out


TOUTES = ["nip", "nom", "sexe", "fonction", "ecole", "zone", "cs", "categorie", "grade", "ind_paye", "ind_reel",
          "naissance", "ps1", "ps_dep", "ps_com", "ps_ecole", "anc_gen", "anc_dep", "anc_com", "anc_ecole", "retraite",
          "restant", "dip", "dip_an", "ceap", "ceap_an", "cap", "cap_an", "apt", "apt_note", "apt_an", "dep_servir",
          "vis_cp", "vis_ccs", "up", "gestion", "note_eval"]
C_PRIVE = ["nom", "sexe", "fonction", "ecole", "zone", "cs", "naissance", "ps1", "ps_dep", "ps_com", "ps_ecole", "anc_gen",
           "anc_dep", "anc_com", "anc_ecole", "dip", "dip_an", "ceap", "ceap_an", "cap", "cap_an", "apt", "apt_note", "apt_an",
           "vis_cp", "vis_ccs", "up", "gestion", "note_eval"]
C_ENCADREMENT = ["nip", "nom", "sexe", "fonction", "ecole", "cs", "categorie", "grade", "ind_paye", "ind_reel", "naissance",
                 "ps1", "ps_dep", "ps_com", "ps_ecole", "anc_gen", "anc_dep", "anc_com", "anc_ecole", "retraite", "restant",
                 "dip", "dip_an", "ceap", "ceap_an", "cap", "cap_an", "dep_servir", "note_eval"]
C_ADMIN = ["nip", "nom", "sexe", "fonction", "ecole", "cs", "categorie", "grade", "ind_paye", "ind_reel", "naissance", "ps1",
           "ps_dep", "ps_ecole", "anc_gen", "anc_dep", "anc_ecole", "retraite", "restant", "dip", "dip_an", "dep_servir",
           "note_eval"]
C_SOUTIEN = ["nom", "sexe", "fonction", "ecole", "zone", "cs", "categorie", "naissance", "ps1", "ps_ecole", "anc_gen",
             "anc_ecole", "retraite", "restant", "dip"]


def _ens(f):
    return f["source"] == "ecole" and f["role"] in ROLES_ENS


# onglets : (code, libellé, filtre, colonnes)
ONGLETS = [
    ("enseignants", "Enseignants (tous)", _ens, TOUTES),
    ("fe", "Directeurs et adjoints FE", lambda f: _ens(f) and f["categorie"] == "FE", TOUTES),
    ("acdpe", "Directeurs et adjoints ACDPE", lambda f: _ens(f) and f["categorie"] == "ACDPE", TOUTES),
    ("acdpctd", "ACDPCTD (AME)", lambda f: _ens(f) and f["categorie"] == "ACDPCTD", TOUTES),
    ("prive", "Directeurs et adjoints du privé", lambda f: _ens(f) and (f.get("secteur") == "prive" or f["categorie"] == "PRIVE"),
     C_PRIVE),
    ("cp", "Conseillers pédagogiques (CP)", lambda f: f["role"] == "cp", C_ENCADREMENT),
    ("ccs", "Chefs de circonscription (CCS)", lambda f: f["role"] == "ccs", C_ENCADREMENT),
    ("administratif", "Personnel administratif", lambda f: f["role"] in ("administratif", "chef_service"), C_ADMIN),
    ("soutien", "Personnel de soutien", lambda f: f["role"] == "soutien", C_SOUTIEN),
]
ONGLETS_D = {o[0]: o for o in ONGLETS}
jur_retraites_proches = None   # renseigné par enregistrer() (= H.jur_retraites_proches)


# ======================================================================== signature + cachet de la structure (PDF)
def _bloc_signatures(sigs, largeur):
    """Flowable : signatures côte à côte. sigs = [(titre, nom, image_reader|None, cachet (sup, inf, centre, couleur)|None)]."""
    from reportlab.lib.units import mm
    from reportlab.platypus.flowables import Flowable
    import cachet as _cachet

    class _Sig(Flowable):
        def wrap(self, *_):
            return largeur, 44 * mm

        def draw(self):
            c = self.canv
            n = len(sigs)
            for i, (titre, nom, image, cach) in enumerate(sigs):
                x = largeur * (i + 0.5) / n
                y = 44 * mm - 8
                c.setFont("Helvetica", 8)
                c.drawCentredString(x, y, f"{config.ECOLE.get('ville') or ''}, le {date.today().strftime('%d/%m/%Y')}".lstrip(", "))
                c.setFont("Helvetica-Bold", 8.5)
                c.drawCentredString(x, y - 11, titre or "")
                if cach:
                    _cachet.dessiner(c, x - 21 * mm, y - 24 * mm, 11.5 * mm, *cach)
                if image is not None:
                    c.drawImage(image, x - 22 * mm, y - 30 * mm, 44 * mm, 17 * mm, preserveAspectRatio=True, mask="auto")
                if nom:
                    c.setFont("Helvetica-Bold", 8.5)
                    c.drawCentredString(x, y - 39 * mm, nom)
    return _Sig()


# ======================================================================== module Flask
def enregistrer(app, H):
    q, ex = H.q, H.ex

    def juridiction_ou_404():
        if not config.juridiction():
            abort(404)

    def niveau():
        return config.EDITION if config.EDITION in ("cs", "ddemp") else "cs"

    # ------------------------------------------------------------ services
    def services(niv=None):
        """[(code, nom)] des services du niveau : table jur_services si renseignée, sinon liste par défaut."""
        niv = niv or niveau()
        try:
            rows = q("SELECT code, nom, sigle FROM jur_services WHERE niveau=? AND actif=1 ORDER BY ordre, nom", (niv,))
        except Exception:  # noqa: BLE001  (table absente : base ancienne)
            rows = []
        if rows:
            return [(r["code"], r["nom"] + (f" ({r['sigle']})" if r["sigle"] and r["sigle"] not in r["nom"] else "")) for r in rows]
        return list(SERVICES_DEFAUT.get(niv, SERVICES_DEFAUT["cs"]))

    # ------------------------------------------------------------ collecte
    def collecter(annee_, cs_id=None, zone_id=None, inactifs=False):
        """Toutes les personnes (fiches calculées) : écoles + agents de la structure + (DDEMP) agents des CS."""
        ref, auj = reference(annee_), date.today()
        svc = {"cs": dict(services("cs")), "ddemp": dict(services("ddemp"))}
        brut, compteur = [], {}
        for p in H.jur_personnel(annee_, cs_id, zone_id):
            p = dict(p)
            if p.get("source") == "ecole":
                i = compteur.get(p["ecole_id"], 0)
                compteur[p["ecole_id"]] = i + 1
                p["cle"] = f"e{p['ecole_id']}-{i}"
            else:
                p["cle"] = f"a{p['agent_id']}"
                p["_svc"] = svc[niveau()]
            brut.append(p)
        if niveau() == "ddemp" and not zone_id:
            for c in H.jur_cs_liste():
                if cs_id and c["id"] != cs_id:
                    continue
                for i, a in enumerate(H.jur_cs_section(c["id"], "agents", annee_) or []):
                    d = dict(a or {})
                    d.update(ecole_id=None, ecole_nom="", ecole_type="", secteur="public", cs_id=c["id"], cs_nom=c["nom"],
                             zone_nom="", source="agent_cs", agent_id=None, cle=f"c{c['id']}-{i}", _svc=svc["cs"])
                    d.setdefault("role", "administratif")
                    brut.append(d)
        out = []
        for p in brut:
            if not inactifs and p.get("actif") is False:
                continue
            out.append(fiche(p, ref, auj, p.pop("_svc", None)))
        return out

    def appliquer_filtres(lst, a):
        sexe, cat, grade, secteur, texte = a["sexe"], a["categorie"], a["grade"], a["secteur"], H.jur_norm(a["q"])
        out = []
        for f in lst:
            if sexe and f["sexe"] != sexe:
                continue
            if cat and f["categorie"] != cat:
                continue
            if grade and not (f["grade"] == grade or (len(grade) == 1 and f["lettre"] == grade)):
                continue
            if secteur and (f.get("secteur") or "public") != secteur:
                continue
            if texte and texte not in H.jur_norm(" ".join(str(x or "") for x in (
                    f["nom_complet"], f.get("nip"), f.get("matricule"), f["ecole_service"], f["fonction_txt"]))):
                continue
            out.append(f)
        return out

    def lire_filtres(defauts=None):
        a = {k: (request.args.get(k) or "").strip() for k in
             ("annee", "cs", "zone", "secteur", "sexe", "categorie", "grade", "q", "onglet", "cols")}
        for k, v in (defauts or {}).items():
            if k not in request.args:
                a[k] = v
        if a["annee"] not in H.jur_annees():
            a["annee"] = H.jur_annee()
        a["cs_id"] = int(a["cs"]) if a["cs"].isdigit() else None
        a["zone_id"] = int(a["zone"]) if a["zone"].isdigit() else None
        if niveau() == "cs":
            a["cs_id"], a["cs"] = None, ""
        return a

    def qs(a, **extra):
        """Paramètres d'URL des filtres courants."""
        d = {k: a[k] for k in ("annee", "cs", "zone", "secteur", "sexe", "categorie", "grade", "q", "onglet", "cols") if a.get(k)}
        d.update({k: v for k, v in extra.items() if v not in (None, "")})
        return d

    def contexte_filtres(a, lst_complete):
        grades = sorted({f["grade"] for f in lst_complete if f["grade"]})
        return dict(a=a, cs_liste=H.jur_cs_liste(), zones=H.jur_zones(a["cs_id"]) if a["cs_id"] else H.jur_zones(),
                    annees=H.jur_annees(), grades=grades, categories=CATEGORIES, ddemp=niveau() == "ddemp")

    def stats_sexe(lst):
        h = sum(1 for f in lst if f["sexe"] == "M")
        fe = sum(1 for f in lst if f["sexe"] == "F")
        return {"t": len(lst), "h": h, "f": fe, "nc": len(lst) - h - fe}

    def colonnes_onglet(code, toutes=False):
        cols = TOUTES if toutes else ONGLETS_D[code][3]
        if niveau() != "ddemp":
            cols = [c for c in cols if c != "cs"]
        return cols

    # ------------------------------------------------------------ en-tête, signature, textes des PDF
    def infos_haut(a=None):
        s = H.jur_structure() or {}
        lignes = [("DDEMP", s.get("departement") or "—")]
        if niveau() == "cs":
            lignes.append(("CS", s.get("cs") or "—"))
        elif a and a.get("cs_id"):
            c = H.jur_cs(a["cs_id"])
            lignes.append(("CS", c["nom"] if c else "—"))
        return lignes

    def cachet_structure():
        """(sup, inf, centre, couleur) : cachet du service de direction s'il est paramétré, sinon cachet standard."""
        s = H.jur_structure() or {}
        code = "ccs" if niveau() == "cs" else "direction"
        try:
            r = q("SELECT cachet_sup, cachet_inf, cachet_centre, cachet_couleur FROM jur_services WHERE niveau=? AND code=?",
                  (niveau(), code), un=True)
        except Exception:  # noqa: BLE001
            r = None
        if r and (r["cachet_sup"] or r["cachet_centre"]):
            return (r["cachet_sup"] or "", r["cachet_inf"] or "", r["cachet_centre"] or "", r["cachet_couleur"] or "bleu")
        dep = (s.get("departement") or "").upper()
        if niveau() == "cs":
            return (f"DDEMP {dep}".strip(), "RÉPUBLIQUE DU BÉNIN", f"CS|{(s.get('cs') or '').upper()}", "bleu")
        return ("MEMP", "RÉPUBLIQUE DU BÉNIN", f"DDEMP|{dep}", "bleu")

    def signature_responsable():
        s = H.jur_structure() or {}
        titre = s.get("responsable_titre") or ("Le Chef de la Circonscription Scolaire" if niveau() == "cs"
                                               else "Le Directeur Départemental")
        img = H.pdfs.image_data_url(H.signature("jur:structure:responsable"))
        return (titre, s.get("responsable_nom") or "", img, cachet_structure())

    def apres_pdf(notes, sigs, largeur_mm):
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Spacer
        fl = [Spacer(1, 4)] + [H.pdfs.paragraphe(n, 7.3) for n in notes]
        fl.append(KeepTogether([Spacer(1, 6), _bloc_signatures(sigs, largeur_mm * mm)]))
        return fl

    NOTES_CALCUL = ("Anciennetés arrêtées au {ref} (jour inclus), en années (a) et mois (m) révolus ; PS = prise de service. "
                    "Retraite : naissance + 60 ans (grade A), 58 ans (B), 55 ans (C) ; année de naissance seule : 31/12 de "
                    "l'année ; né(e) un 29/02 : 28/02 si l'année n'est pas bissextile.")

    def sous_titre(a, extra=""):
        morceaux = [f"Année scolaire {a['annee']}"]
        if a.get("zone_id"):
            z = next((z for z in H.jur_zones() if z["id"] == a["zone_id"]), None)
            if z:
                morceaux.append(z["nom"])
        if a.get("secteur"):
            morceaux.append("secteur " + jur_format.SECTEURS.get(a["secteur"], a["secteur"]).lower())
        if a.get("sexe"):
            morceaux.append(SEXES.get(a["sexe"], a["sexe"]).lower())
        if a.get("categorie"):
            morceaux.append("catégorie " + a["categorie"])
        if a.get("grade"):
            morceaux.append("grade " + a["grade"])
        if a.get("q"):
            morceaux.append(f"recherche « {a['q']} »")
        return " · ".join(morceaux) + (f" — {extra}" if extra else "")

    def titre_haut_xlsx(titre, a):
        s = H.jur_structure() or {}
        return [f"{s.get('nom') or config.ECOLE.get('nom', '')} — {titre}", sous_titre(a),
                f"Anciennetés au {reference(a['annee']).strftime('%d/%m/%Y')} · extrait le {date.today().strftime('%d/%m/%Y')}"]

    # ------------------------------------------------------------ fonction exposée (tableau de bord)
    def retraites_proches(annee_=None, cs_id=None, ans=2):
        """Personnes (dict fiche) dont le départ à la retraite intervient dans `ans` ans ou moins (ou est atteint),
        triées par date. Clés utiles : nom_complet, sexe, ecole_service, cs_nom, zone_nom, grade, lettre,
        retraite (date), retraite_txt, restant_txt, retraite_atteinte, cle (pour url_for('jur_personnel_fiche', cle=…))."""
        auj = date.today()
        limite = MC.plus_ans(auj, int(ans))
        lst = [f for f in collecter(annee_ or H.jur_annee(), cs_id) if f["retraite"] and f["retraite"] <= limite]
        return sorted(lst, key=lambda f: (f["retraite"], f["nom_complet"]))

    H.jur_retraites_proches = retraites_proches
    global jur_retraites_proches            # accessible aussi par import (tests, scripts)
    jur_retraites_proches = retraites_proches

    # ================================================================ 1. personnel par onglets
    @app.route("/juridiction/personnel")
    @H.connexion_requise()
    def jur_personnel():
        juridiction_ou_404()
        a = lire_filtres()
        if a["onglet"] not in ONGLETS_D:
            a["onglet"] = "enseignants"
        complet = collecter(a["annee"], a["cs_id"], a["zone_id"])
        lst = appliquer_filtres(complet, a)
        par_onglet = {code: [f for f in lst if filtre(f)] for code, _l, filtre, _c in ONGLETS}
        toutes = a["cols"] == "toutes"
        export = request.args.get("export")
        if export == "xlsx":
            return export_xlsx(a, par_onglet, toutes)
        if export == "pdf":
            return export_pdf(a, par_onglet[a["onglet"]], toutes)
        cols = colonnes_onglet(a["onglet"], toutes)
        courant = sorted(par_onglet[a["onglet"]], key=lambda f: (f.get("cs_nom") or "", f["ecole_service"], f["nom_complet"]))
        lignes = [(f, [COLS[c][1](f) for c in cols]) for f in courant]
        par_cat = {}
        for f in courant:
            par_cat[f["categorie_lib"] or "non renseignée"] = par_cat.get(f["categorie_lib"] or "non renseignée", 0) + 1
        return render_template(
            "jur_personnel.html", onglets=ONGLETS, compte={k: stats_sexe(v) for k, v in par_onglet.items()},
            st=stats_sexe(courant), cols=[(c, COLS[c][0]) for c in cols], lignes=lignes, par_cat=par_cat,
            qs=qs(a), qs_sans_onglet={k: v for k, v in qs(a).items() if k != "onglet"}, toutes=toutes,
            reference=reference(a["annee"]), vide=not complet, **contexte_filtres(a, complet))

    def export_xlsx(a, par_onglet, toutes):
        feuilles = []
        for code, lib, _f, _c in ONGLETS:
            cols = colonnes_onglet(code, toutes)
            lst = sorted(par_onglet[code], key=lambda f: (f.get("cs_nom") or "", f["ecole_service"], f["nom_complet"]))
            st = stats_sexe(lst)
            lignes = [[i] + [COLS[c][1](f) for c in cols] for i, f in enumerate(lst, 1)]
            lignes.append([""] * (len(cols) + 1))
            lignes.append(["", f"Total : {st['t']} (hommes : {st['h']}, femmes : {st['f']})"] + [""] * (len(cols) - 1))
            feuilles.append((lib[:31], ["N°"] + [COLS[c][0] for c in cols], lignes, {"titre_haut": titre_haut_xlsx(lib, a)}))
        synth = [[lib, stats_sexe(par_onglet[code])["h"], stats_sexe(par_onglet[code])["f"], stats_sexe(par_onglet[code])["t"]]
                 for code, lib, _f, _c in ONGLETS]
        feuilles.insert(0, ("Synthèse", ["Module", "Hommes", "Femmes", "Total"], synth,
                            {"titre_haut": titre_haut_xlsx("Personnel par catégorie", a)}))
        try:
            return H.xlsx.reponse_classeur(f"personnel_{a['annee']}.xlsx", feuilles)
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("jur_personnel", **qs(a)))

    def export_pdf(a, lst, toutes):
        code = a["onglet"]
        cols = colonnes_pdf(colonnes_onglet(code, toutes))
        lst = sorted(lst, key=lambda f: (f.get("cs_nom") or "", f["ecole_service"], f["nom_complet"]))
        corps = [[i] + [COLS_PDF[c][2](f) for c in cols] for i, f in enumerate(lst, 1)]
        if not corps:
            corps = [["", "Aucune personne (voir les filtres)"] + [""] * (len(cols) - 1)]
        st = stats_sexe(lst)
        largeurs = [5] + [COLS_PDF[c][1] for c in cols]
        taille = 6.2 if len(cols) <= 16 else (5.6 if len(cols) <= 21 else 5.0)
        notes = [f"Total : {st['t']} personne(s) — hommes : {st['h']}, femmes : {st['f']}"
                 + (f", sexe non renseigné : {st['nc']}" if st["nc"] else "") + ".",
                 NOTES_CALCUL.format(ref=reference(a["annee"]).strftime("%d/%m/%Y")) + " Lignes orangées : départ dans 2 ans ou moins."]
        pdf = H.pdfs.document_tableau(
            f"PERSONNEL — {ONGLETS_D[code][1].upper()}", ["N°"] + [COLS_PDF[c][0] for c in cols], corps, paysage=True,
            taille=taille, largeurs=largeurs, sous_titre=sous_titre(a, f"situation au {date.today().strftime('%d/%m/%Y')}"),
            infos_haut=infos_haut(a), surlignes={i: "#FDEAD7" for i, f in enumerate(lst) if f["alerte_retraite"]},
            apres=apres_pdf(notes, [signature_responsable()], 273))
        return H.pdf_reponse(pdf, f"personnel_{code}.pdf")

    # ------------------------------------------------------------ fiche individuelle
    def sections_fiche(f):
        n = fmt_n
        dip = f["dip"] + (f" (obtenu en {f['annee_diplome']})" if f["dip"] and f.get("annee_diplome") else "")

        def pro(o, an, typ=""):
            if o == "oui":
                return "oui" + (f" — {typ}" if typ else "") + (f" (obtenu en {an})" if an else "")
            return o

        apt = f["apt_o"]
        if f["note_apt"] is not None:
            apt += f" — note : {n(f['note_apt'])}/20"
        if f.get("annee_aptitude"):
            apt += f" — année {f['annee_aptitude']}"
        if f["retraite"]:
            ret = f"{f['retraite_txt']} ({f['age_retraite']} ans, grade {f['lettre']}) — " + (
                "départ atteint" if f["retraite_atteinte"] else f"reste {MC.fmt_duree(f['restant'])}")
        else:
            ret = f"non calculable : {f['retraite_raison']}"
        anc = lambda k: MC.fmt_duree(f["anc"][k]) if f["anc"][k] else "—"   # noqa: E731
        return [
            ("1. Identification", [
                ("Nom et prénoms", f["nom_complet"]), ("Sexe", SEXES.get(f["sexe"], "")), ("NIP", f.get("nip") or ""),
                ("Matricule", f.get("matricule") or ""), ("Date de naissance", MC.fmt_date(f["naissance_iso"]) if f["naissance_iso"] else ""),
                ("Téléphone", f.get("telephone") or ""), ("E-mail", f.get("email") or "")]),
            ("2. Affectation et situation administrative", [
                ("École / service", f["ecole_service"]), ("Fonction / poste", f["fonction_txt"]),
                ("Zone pédagogique", f.get("zone_nom") or ""), ("Circonscription scolaire", f.get("cs_nom") or ""),
                ("Catégorie", f["categorie_lib"]), ("Grade", f["grade"]),
                ("Indice payé", n(f.get("indice_paye"))), ("Indice réel", n(f.get("indice_reel"))),
                ("Département à servir", f.get("departement_a_servir") or "")]),
            ("3. Prises de service", [
                ("Première prise de service", f["ps_txt"]["generale"]), ("Dans le département", f["ps_txt"]["departement"]),
                ("Dans la commune", f["ps_txt"]["commune"]), ("Dans l'école / le service", f["ps_txt"]["ecole"])]),
            (f"4. Anciennetés au {f['reference'].strftime('%d/%m/%Y')}", [
                ("Ancienneté générale", anc("generale")), ("Ancienneté dans le département", anc("departement")),
                ("Ancienneté dans la commune", anc("commune")), ("Ancienneté dans l'école / le service", anc("ecole"))]),
            ("5. Départ à la retraite", [("Date probable de départ", ret)]),
            ("6. Diplômes", [
                ("Diplôme académique le plus élevé", dip),
                ("CEAP", pro(f["ceap_o"], f.get("annee_ceap"))),
                ("CAP", pro(f["cap_o"], f.get("annee_cap"), f["type_cap"]))]),
            ("7. Suivi pédagogique et évaluation", [
                ("Visite d'aptitude", apt), ("Visites de classe du CP", n(f.get("nb_visites_cp"))),
                ("Visites de classe du CCS", n(f.get("nb_visites_ccs"))),
                ("Participation à l'UP", n(f.get("participation_up"), " %")),
                ("Gestion collégiale", f.get("gestion_collegiale") or ""),
                ("Note d'évaluation", (n(f["note_eval"]) + " / 20") if f["note_eval"] is not None else "")]),
        ]

    @app.route("/juridiction/personnel/fiche")
    @H.connexion_requise()
    def jur_personnel_fiche():
        juridiction_ou_404()
        cle = request.args.get("cle", "")
        a = lire_filtres()
        if not re.fullmatch(r"(e\d+-\d+|a\d+|c\d+-\d+)", cle):
            abort(404)
        if cle.startswith("a"):     # agent de la structure (y compris retiré) : lu directement
            r = q("SELECT a.*, c.nom cs_nom FROM jur_agents a LEFT JOIN jur_cs c ON c.id=a.cs_id WHERE a.id=?",
                  (int(cle[1:]),), un=True)
            f = fiche(dict(agent_valeurs(r), source="agent", agent_id=r["id"], cs_id=r["cs_id"], cs_nom=r["cs_nom"] or "",
                           zone_nom="", secteur="public", cle=cle), reference(a["annee"]),
                      services=dict(services())) if r else None
        else:
            f = next((x for x in collecter(a["annee"], inactifs=True) if x["cle"] == cle), None)
        if not f:
            abort(404)
        secs = sections_fiche(f)
        if request.args.get("pdf"):
            lignes, surl = [], {}
            for titre, champs in secs:
                surl[len(lignes)] = "#DCE7F3"
                lignes.append([titre, "", "", ""])
                cases = [[lib, val or "……………………"] for lib, val in champs]
                for i in range(0, len(cases), 2):
                    lignes.append(cases[i] + (cases[i + 1] if i + 1 < len(cases) else ["", ""]))
            notes = [NOTES_CALCUL.format(ref=f["reference"].strftime("%d/%m/%Y"))]
            origine = {"ecole": "données transmises par l'école", "agent": "agent de la structure",
                       "agent_cs": "données transmises par la circonscription"}.get(f["source"], "")
            pdf = H.pdfs.document_tableau(
                "FICHE INDIVIDUELLE DE CARRIÈRE", ["Rubrique", "Renseignement", "Rubrique", "Renseignement"], lignes,
                largeurs=[24, 26, 24, 26], taille=8, sous_titre=f"{f['nom_complet']} — année scolaire {a['annee']} ({origine})",
                infos_haut=infos_haut({"cs_id": f.get("cs_id")} if niveau() == "ddemp" else None), surlignes=surl,
                apres=apres_pdf(notes, [("L'INTÉRESSÉ(E)", f["nom_complet"], None, None), signature_responsable()], 186))
            return H.pdf_reponse(pdf, "fiche_carriere_" + re.sub(r"[^A-Za-z0-9]+", "_", f["nom_complet"]) + ".pdf")
        return render_template("jur_personnel_fiche.html", f=f, sections=secs, a=a,
                               retour=request.args.get("retour") or url_for("jur_personnel", annee=a["annee"]))

    # ================================================================ 2. visites d'aptitude et diplômes
    LISTES_APT = [("visite", "Visite d'aptitude effectuée"), ("sans_visite", "Sans visite d'aptitude"),
                  ("cap_ep", "Titulaires du CAP (EP)"), ("cap_em", "Titulaires du CAP (EM)"),
                  ("ceap_ep", "Titulaires du CEAP (EP)"), ("ceap_em", "Titulaires du CEAP (EM)"),
                  ("autres", "Diplôme académique seul (ni CEAP ni CAP)"), ("aucun", "Aucun diplôme renseigné")]
    LISTES_APT_D = dict(LISTES_APT)

    def classer_aptitude(lst):
        L = {k: [] for k, _l in LISTES_APT}
        for f in lst:
            (L["visite"] if f["apt_o"] == "oui" else L["sans_visite"]).append(f)
            if f["cap_o"] == "oui":
                L["cap_em" if f["cap_type_eff"] == "EM" else "cap_ep"].append(f)
            if f["ceap_o"] == "oui":
                L["ceap_em" if f["ceap_type_eff"] == "EM" else "ceap_ep"].append(f)
            if f["cap_o"] != "oui" and f["ceap_o"] != "oui":
                (L["autres"] if f["dip"] else L["aucun"]).append(f)
        for k in L:
            L[k].sort(key=lambda f: (f.get("cs_nom") or "", f["ecole_service"], f["nom_complet"]))
        return L

    def stats_aptitude(visite):
        notes = [f["note_apt"] for f in visite if f["note_apt"] is not None]
        reussis = sum(1 for x in notes if x >= 10)
        return {"n": len(visite), "notes": len(notes), "reussis": reussis, "taux": jur_calc.taux(reussis, len(notes)),
                "moyenne": jur_calc.moyenne(notes),
                "h": sum(1 for f in visite if f["sexe"] == "M"), "f": sum(1 for f in visite if f["sexe"] == "F")}

    APT_COLS = [("N°", 5), ("Nom et prénoms", 30), ("Sexe", 6), ("NIP", 17), ("École", 30), ("Zone / CS", 22),
                ("Catégorie", 12), ("Grade", 9), ("Diplôme académique", 18), ("CEAP", 12), ("CAP", 14),
                ("Aptitude (note, année)", 18)]

    def ligne_apt(i, f):
        zc = " · ".join(x for x in (f.get("zone_nom"), f.get("cs_nom") if niveau() == "ddemp" else "") if x)
        ceap = ("oui" + (f" {f['annee_ceap']}" if f.get("annee_ceap") else "") + (f" ({f['ceap_type_eff']})" if f["ceap_type_eff"] else "")) \
            if f["ceap_o"] == "oui" else f["ceap_o"]
        cap = ("oui" + (f" {f['annee_cap']}" if f.get("annee_cap") else "") + (f" ({f['cap_type_eff']})" if f["cap_type_eff"] else "")) \
            if f["cap_o"] == "oui" else f["cap_o"]
        return [i, f["nom_complet"], f["sexe"], f.get("nip") or "", f["ecole_service"], zc, f["categorie_lib"], f["grade"],
                _pdf_diplomes(f), ceap, cap, _pdf_apt(f)]

    @app.route("/juridiction/personnel/aptitude")
    @H.connexion_requise()
    def jur_aptitude():
        juridiction_ou_404()
        a = lire_filtres()
        liste = request.args.get("liste") if request.args.get("liste") in LISTES_APT_D else "visite"
        complet = [f for f in collecter(a["annee"], a["cs_id"], a["zone_id"]) if _ens(f)]
        ens = appliquer_filtres(complet, a)
        L = classer_aptitude(ens)
        st = stats_aptitude(L["visite"])
        compte = {k: len(v) for k, v in L.items()}
        export = request.args.get("export")
        resume = [("Enseignants", len(ens)), ("Visite d'aptitude effectuée", st["n"]), ("dont notés", st["notes"]),
                  ("Réussite (note ≥ 10)", f"{st['reussis']} ({st['taux']} %)" if st["taux"] is not None else "—"),
                  ("Moyenne des notes", fmt_n(st["moyenne"]) or "—"),
                  ("Sans diplôme professionnel", compte["autres"] + compte["aucun"])]
        if export == "xlsx":
            ent = [c for c, _w in APT_COLS]
            feuilles = [("Statistiques", ["Indicateur", "Valeur"], [[k, v] for k, v in resume]
                         + [[f"Nombre : {lib}", compte[k]] for k, lib in LISTES_APT],
                         {"titre_haut": titre_haut_xlsx("Visites d'aptitude et diplômes", a)})]
            for k, lib in LISTES_APT:
                feuilles.append((lib[:31].replace("(", "").replace(")", ""), ent, [ligne_apt(i, f) for i, f in enumerate(L[k], 1)],
                                 {"titre_haut": titre_haut_xlsx(lib, a)}))
            try:
                return H.xlsx.reponse_classeur(f"aptitude_diplomes_{a['annee']}.xlsx", feuilles)
            except H.xlsx.ExcelIndisponible as e:
                flash(str(e), "danger")
                return redirect(url_for("jur_aptitude", **qs(a, liste=liste)))
        if export == "pdf":
            lst = L[liste]
            corps = [ligne_apt(i, f) for i, f in enumerate(lst, 1)] or [["", "Aucun enseignant dans cette liste"] + [""] * 10]
            st_l = stats_sexe(lst)
            notes = [f"{LISTES_APT_D[liste]} : {st_l['t']} enseignant(s) — hommes : {st_l['h']}, femmes : {st_l['f']}.",
                     "Réussite à la visite d'aptitude : note ≥ 10/20. CEAP / CAP EP ou EM : type déclaré, à défaut type de "
                     "l'école (maternelle et espace enfance → EM)."]
            pdf = H.pdfs.document_tableau(
                f"VISITES D'APTITUDE ET DIPLÔMES — {LISTES_APT_D[liste].upper()}", [c for c, _w in APT_COLS], corps,
                paysage=True, taille=7, largeurs=[w for _c, w in APT_COLS], sous_titre=sous_titre(a), infos=resume,
                infos_haut=infos_haut(a), apres=apres_pdf(notes, [signature_responsable()], 273))
            return H.pdf_reponse(pdf, f"aptitude_{liste}.pdf")
        return render_template("jur_aptitude.html", L=L, liste=liste, listes=LISTES_APT, compte=compte, st=st,
                               nb_ens=len(ens), st_ens=stats_sexe(ens), lignes=[ligne_apt(i, f) for i, f in enumerate(L[liste], 1)],
                               fiches=L[liste], cols=[c for c, _w in APT_COLS], qs=qs(a), vide=not complet,
                               **contexte_filtres(a, complet))

    # ================================================================ 3. départs à la retraite
    @app.route("/juridiction/personnel/retraite")
    @H.connexion_requise()
    def jur_retraite():
        juridiction_ou_404()
        a = lire_filtres({"secteur": "public"})
        try:
            horizon = min(10, max(1, int(request.args.get("horizon") or 5)))
        except ValueError:
            horizon = 5
        auj = date.today()
        y0 = auj.year
        annees = list(range(y0, y0 + horizon + 1))
        complet = collecter(a["annee"], a["cs_id"], a["zone_id"])
        lst = appliquer_filtres(complet, a)
        sans_naiss = [f for f in lst if f["lettre"] and not f["naissance_iso"]]
        grade_inconnu = [f for f in lst if not f["lettre"]]
        depasses = [f for f in lst if f["retraite"] and f["retraite"].year < y0]
        departs = sorted([f for f in lst if f["retraite"] and y0 <= f["retraite"].year <= annees[-1]],
                         key=lambda f: (f["retraite"], f["nom_complet"]))
        # tableau croisé par grade : effectif, sorties prévues par année, restant
        grades = {}
        for f in lst:
            if f["lettre"]:
                d = grades.setdefault(f["grade"], {"lettre": f["lettre"], "eff": 0, "dep": 0, "an": {y: 0 for y in annees}})
                d["eff"] += 1
                if f["retraite"] and f["retraite"].year < y0:
                    d["dep"] += 1
                elif f["retraite"] and f["retraite"].year in d["an"]:
                    d["an"][f["retraite"].year] += 1
        lignes_grade = []
        for lettre in ("A", "B", "C"):
            gs = sorted((k for k, v in grades.items() if v["lettre"] == lettre),
                        key=lambda k: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", k)])
            tot = {"eff": 0, "dep": 0, "an": {y: 0 for y in annees}}
            for k in gs:
                v = grades[k]
                s = sum(v["an"].values())
                lignes_grade.append({"grade": k, "eff": v["eff"], "dep": v["dep"], "an": v["an"], "sorties": s,
                                     "restant": v["eff"] - v["dep"] - s, "total": False})
                tot["eff"] += v["eff"]
                tot["dep"] += v["dep"]
                for y in annees:
                    tot["an"][y] += v["an"][y]
            if gs:
                s = sum(tot["an"].values())
                lignes_grade.append({"grade": f"Total grade {lettre} ({MC.AGES_RETRAITE[lettre]} ans)", "eff": tot["eff"],
                                     "dep": tot["dep"], "an": tot["an"], "sorties": s, "restant": tot["eff"] - tot["dep"] - s,
                                     "total": True})
        tg = [l for l in lignes_grade if l["total"]]
        total_general = {"grade": "TOTAL GÉNÉRAL", "eff": sum(l["eff"] for l in tg), "dep": sum(l["dep"] for l in tg),
                         "an": {y: sum(l["an"][y] for l in tg) for y in annees}, "sorties": sum(l["sorties"] for l in tg),
                         "restant": sum(l["restant"] for l in tg), "total": True}
        # par année de naissance (départs de l'horizon)
        naiss = {}
        for f in departs:
            d = naiss.setdefault(f["annee_naissance"], {"A": 0, "B": 0, "C": 0, "t": 0, "h": 0, "f": 0})
            d[f["lettre"]] += 1
            d["t"] += 1
            d["h" if f["sexe"] == "M" else "f"] += 1 if f["sexe"] in ("M", "F") else 0
        lignes_naiss = [dict(v, annee=k, departs=" · ".join(f"{l} : {k + MC.AGES_RETRAITE[l]}" for l in "ABC" if v[l]))
                        for k, v in sorted(naiss.items())]
        par_an = {y: [f for f in departs if f["retraite"].year == y] for y in annees}
        export = request.args.get("export")
        if export:
            return export_retraite(export, a, horizon, annees, departs, depasses, lignes_grade, total_general,
                                   lignes_naiss, sans_naiss, grade_inconnu)
        return render_template("jur_retraite.html", horizon=horizon, periode=annees, departs=departs, depasses=depasses,
                               lignes_grade=lignes_grade, total_general=total_general, lignes_naiss=lignes_naiss,
                               sans_naiss=sans_naiss, grade_inconnu=grade_inconnu, par_an=par_an, st=stats_sexe(departs),
                               nb=len(lst), qs=qs(a, horizon=horizon), ages=MC.AGES_RETRAITE, vide=not complet,
                               **contexte_filtres(a, complet))

    RET_COLS = [("N°", 5), ("Nom et prénoms", 30), ("Sexe", 6), ("École / service", 32), ("Zone / CS", 22), ("Catégorie", 12),
                ("Grade", 9), ("Naissance", 14), ("Âge limite", 9), ("Départ probable", 15), ("Temps restant", 15)]

    def ligne_ret(i, f):
        zc = " · ".join(x for x in (f.get("zone_nom"), f.get("cs_nom") if niveau() == "ddemp" else "") if x)
        return [i, f["nom_complet"], f["sexe"], f["ecole_service"], zc, f["categorie_lib"], f["grade"], f["naissance_txt"],
                f"{f['age_retraite']} ans" if f["age_retraite"] else "", f["retraite_txt"], f["restant_txt"]]

    def export_retraite(fmt, a, horizon, annees, departs, depasses, lignes_grade, total_general, lignes_naiss,
                        sans_naiss, grade_inconnu):
        ent_g = ["Grade", "Effectif", "Départ dépassé"] + [str(y) for y in annees] + [f"Sorties {annees[0]}-{annees[-1]}",
                                                                                     "Restant"]
        rows_g = [[l["grade"], l["eff"], l["dep"]] + [l["an"][y] for y in annees] + [l["sorties"], l["restant"]]
                  for l in lignes_grade + [total_general]]
        ent_n = ["Année de naissance", "Grade A", "Grade B", "Grade C", "Total", "Hommes", "Femmes", "Année de départ"]
        rows_n = [[l["annee"], l["A"], l["B"], l["C"], l["t"], l["h"], l["f"], l["departs"]] for l in lignes_naiss]
        anomalies = [[i, f["nom_complet"], f["ecole_service"], f["grade"] or "—", f["naissance_txt"] or "—",
                      "date de naissance inconnue" if f in sans_naiss else "grade inconnu ou hors A, B, C"]
                     for i, f in enumerate(sans_naiss + grade_inconnu, 1)]
        titre = f"Départs à la retraite {annees[0]}–{annees[-1]}"
        if fmt == "xlsx":
            th = titre_haut_xlsx(titre, a)
            try:
                return H.xlsx.reponse_classeur(f"retraites_{annees[0]}_{annees[-1]}.xlsx", [
                    ("Départs", [c for c, _w in RET_COLS], [ligne_ret(i, f) for i, f in enumerate(depasses + departs, 1)],
                     {"titre_haut": th}),
                    ("Par grade", ent_g, rows_g, {"titre_haut": th}),
                    ("Par année de naissance", ent_n, rows_n, {"titre_haut": th}),
                    ("Cas à vérifier", ["N°", "Nom et prénoms", "École / service", "Grade", "Naissance", "Problème"], anomalies,
                     {"titre_haut": th})])
            except H.xlsx.ExcelIndisponible as e:
                flash(str(e), "danger")
                return redirect(url_for("jur_retraite", **qs(a, horizon=horizon)))
        if fmt != "pdf":
            abort(400)
        P = H.pdfs
        larg_g = [40, 16, 18] + [min(15, 150 / len(annees))] * len(annees) + [22, 18]
        avant = [P.paragraphe("1. Effectifs par grade et sorties prévues par année", 9, True),
                 P.mini_tableau([ent_g] + rows_g, [x * 2.83 for x in larg_g], taille=6.8) if rows_g[:-1]
                 else P.paragraphe("Aucun agent dont le grade est renseigné (A, B ou C)."),
                 P.paragraphe("2. Départs par année de naissance", 9, True),
                 P.mini_tableau([ent_n] + rows_n, [x * 2.83 for x in (30, 20, 20, 20, 18, 18, 18, 80)], taille=6.8) if rows_n else P.paragraphe("Aucun départ sur la période."),
                 P.paragraphe("3. Liste nominative des départs (par date)", 9, True)]
        lst = depasses + departs
        corps = [ligne_ret(i, f) for i, f in enumerate(lst, 1)] or [["", "Aucun départ sur la période"] + [""] * 9]
        st = stats_sexe(departs)
        notes = [f"Départs {annees[0]}–{annees[-1]} : {st['t']} (hommes : {st['h']}, femmes : {st['f']})"
                 + (f" ; départs déjà dépassés mais toujours déclarés : {len(depasses)} (lignes rouges)" if depasses else "") + ".",
                 f"Cas à vérifier : {len(sans_naiss)} sans date de naissance, {len(grade_inconnu)} grade inconnu ou hors A, B, C.",
                 "Règle : naissance + 60 ans (grade A), 58 ans (B), 55 ans (C) ; année de naissance seule : 31/12 ; "
                 "né(e) un 29/02 : 28/02 si l'année de départ n'est pas bissextile."]
        surl = {i: "#FAD4D4" for i in range(len(depasses))}
        surl.update({len(depasses) + i: "#FDEAD7" for i, f in enumerate(departs) if f["retraite"].year == annees[0]})
        if anomalies:
            apres_extra = [P.paragraphe("4. Cas à vérifier", 9, True),
                           P.mini_tableau([["N°", "Nom et prénoms", "École / service", "Grade", "Naissance", "Problème"]]
                                          + anomalies, taille=6.8)]
        else:
            apres_extra = []
        pdf = P.document_tableau(
            titre.upper(), [c for c, _w in RET_COLS], corps, paysage=True, taille=7, largeurs=[w for _c, w in RET_COLS],
            sous_titre=sous_titre(a, f"horizon : {annees[0]} à {annees[-1]}"), infos_haut=infos_haut(a), avant=avant,
            surlignes=surl, apres=apres_extra + apres_pdf(notes, [signature_responsable()], 273))
        return H.pdf_reponse(pdf, f"retraites_{annees[0]}_{annees[-1]}.pdf")

    # ================================================================ 4. agents de la structure
    def comptes():
        return q("SELECT id, identifiant, nom, role FROM utilisateurs WHERE actif=1 ORDER BY nom")

    def agent_ou_404(aid):
        r = q("SELECT * FROM jur_agents WHERE id=?", (aid,), un=True)
        if not r:
            abort(404)
        return r

    def agent_valeurs(r):
        """Ligne jur_agents → dict de tous les champs (pour le formulaire / l'export)."""
        d = json.loads(r["donnees"] or "{}")
        for k in COLONNES_TABLE:
            d[k] = r[k] or ""
        d["actif"] = bool(r["actif"])
        d["user_id"] = r["user_id"]
        return d

    def lire_agent(src, aid=None, auj=None):
        """Valide un agent (formulaire ou ligne Excel : dict clé → texte). Renvoie (valeurs, erreurs)."""
        auj = auj or date.today()
        v, err = {}, []
        txt = lambda k, n=150: str(src.get(k) if src.get(k) is not None else "").strip()[:n]   # noqa: E731
        codes_svc = {c for c, _n in services()}
        for k, lib, typ in CHAMPS_AGENT:
            brut = txt(k, 500 if k == "gestion_collegiale" else 150)
            val = brut
            if typ == "sexe":
                val = H.xlsx.sexe(brut) if brut else ""
                if brut and not val:
                    err.append("Sexe : indiquez M ou F.")
            elif typ == "nip":
                val = brut.replace(" ", "")
                if val and not re.fullmatch(r"\d{1,12}", val):
                    err.append("NIP : 12 chiffres au maximum, sans lettres.")
            elif typ == "naissance":
                try:
                    val = MC.lire_naissance(brut[:10]) or ""
                except ValueError:
                    err.append("Date de naissance invalide (jj/mm/aaaa ou l'année seule).")
                    val = ""
                if val and not 1930 <= int(val[:4]) <= auj.year - 15:
                    err.append("Date de naissance hors limites.")
            elif typ == "date":
                try:
                    val = MC.lire_date(brut[:10]) or ""
                except ValueError:
                    err.append(f"{lib} : date invalide (jj/mm/aaaa).")
                    val = ""
                if val and val > MC.plus_ans(auj, 1).isoformat():
                    err.append(f"{lib} : date trop lointaine dans l'avenir.")
            elif typ == "service":
                if val and val not in codes_svc:
                    err.append("Service inconnu.")
            elif typ == "role":
                val = val or "administratif"
                if val not in ROLES_AGENT:
                    err.append("Rôle invalide (ccs, cp, chef_service, administratif ou soutien).")
            elif typ == "categorie":
                val = val.upper()
                if val and val not in CATEGORIES:
                    err.append("Catégorie invalide (FE, ACDPE, ACDPCTD, PRIVE ou AUTRE).")
            elif typ == "grade":
                val = val.upper().replace(" ", "")
                if val and not RE_GRADE.fullmatch(val):
                    err.append("Grade invalide (exemples : A1-5, B2-12, C3-1).")
            elif typ in ("indice", "compte", "pct", "note"):
                maxi = {"indice": 9999, "compte": 99, "pct": 100, "note": 20}[typ]
                x = nombre(brut)
                if brut and (x is None or not 0 <= x <= maxi or (typ in ("indice", "compte") and not x.is_integer())):
                    err.append(f"{lib} : valeur invalide (0 à {maxi}{' sur 20' if typ == 'note' else ''}).")
                    x = None
                val = "" if x is None else (int(x) if x.is_integer() and typ != "note" else x)
            elif typ == "annee":
                if val and not (re.fullmatch(r"\d{4}", val) and 1940 <= int(val) <= auj.year):
                    err.append(f"{lib} : année invalide.")
                    val = ""
            elif typ == "bool":
                e_ = tri_etat(brut)
                val = True if e_ == "oui" else (False if e_ == "non" else "")
                if k == "actif":
                    val = val is not False
            elif typ == "type_cap":
                val = val.upper()
                if val and val not in ("EP", "EM"):
                    err.append("Type de CAP : EP ou EM.")
            elif typ == "departement":
                if val and val not in MC.DEPARTEMENTS:
                    err.append("Département à servir invalide.")
            v[k] = val
        if not v["nom"]:
            err.append("Le nom est obligatoire.")
        v["nom"] = v["nom"].upper()
        # cohérence des dates
        n = v["date_naissance"]
        for k in ("date_premiere_ps", "date_ps_departement", "date_ps_commune", "date_ps_ecole"):
            if n and v[k] and v[k][:4] <= n[:4]:
                err.append(f"{LIB_CHAMP[k]} : antérieure ou égale à l'année de naissance.")
            if k != "date_premiere_ps" and v["date_premiere_ps"] and v[k] and v[k] < v["date_premiere_ps"]:
                err.append(f"{LIB_CHAMP[k]} : antérieure à la première prise de service.")
        for k in ("ceap", "cap"):
            if v[f"annee_{k}"] and v[k] == "":
                v[k] = True
            if v[k] is False and v[f"annee_{k}"]:
                err.append(f"{k.upper()} : « non » avec une année d'obtention.")
        if v["type_cap"] and v["cap"] is not True:
            v["cap"] = True if v["cap"] == "" else v["cap"]
        if (v["note_aptitude"] != "" or v["annee_aptitude"]) and v["visite_aptitude"] == "":
            v["visite_aptitude"] = True
        if v["visite_aptitude"] is False and v["note_aptitude"] != "":
            err.append("Visite d'aptitude « non » avec une note.")
        # compte utilisateur lié
        brut = txt("user_id")
        v["user_id"] = None
        if brut:
            if not brut.isdigit() or not q("SELECT 1 FROM utilisateurs WHERE id=? AND actif=1", (int(brut),), un=True):
                err.append("Compte utilisateur invalide.")
            else:
                autre = q("SELECT nom, prenoms FROM jur_agents WHERE user_id=? AND id<>? AND actif=1", (int(brut), aid or 0), un=True)
                if autre:
                    err.append(f"Ce compte est déjà lié à l'agent {autre['nom']} {autre['prenoms'] or ''}.")
                else:
                    v["user_id"] = int(brut)
        return v, err

    def enregistrer_agent(v, aid=None):
        donnees = {k: v[k] for k, _l, _t in CHAMPS_AGENT if k not in COLONNES_TABLE and k != "actif"}
        donnees["actif"] = bool(v["actif"])
        cols = {k: v[k] for k in COLONNES_TABLE}
        cs_id = (H.jur_cs_courante() or {"id": None})["id"] if niveau() == "cs" else None
        if aid:
            ex("UPDATE jur_agents SET " + ", ".join(f"{k}=?" for k in cols) + ", donnees=?, user_id=?, actif=?, "
               "maj=datetime('now','localtime') WHERE id=?",
               tuple(cols.values()) + (json.dumps(donnees, ensure_ascii=False), v["user_id"], 1 if v["actif"] else 0, aid))
            return aid
        return ex("INSERT INTO jur_agents (cs_id, " + ", ".join(cols) + ", donnees, user_id, actif, maj) VALUES (?, " +
                  ", ".join("?" * len(cols)) + ", ?, ?, ?, datetime('now','localtime'))",
                  (cs_id,) + tuple(cols.values()) + (json.dumps(donnees, ensure_ascii=False), v["user_id"], 1 if v["actif"] else 0))

    def ligne_export_agent(d):
        out = []
        for k, _l, typ in CHAMPS_AGENT:
            x = d.get(k)
            if typ == "bool":
                x = tri_etat(x) if k != "actif" else ("oui" if d.get("actif", True) else "non")
            elif typ in ("date", "naissance"):
                x = x or ""
            out.append("" if x is None else x)
        return out

    @app.route("/juridiction/agents")
    @H.connexion_requise()
    def jur_agents():
        juridiction_ou_404()
        a = {k: (request.args.get(k) or "").strip() for k in ("service", "role", "q", "tous")}
        sql, args = "SELECT * FROM jur_agents WHERE 1=1", []
        if a["tous"] != "1":
            sql += " AND actif=1"
        if a["service"]:
            sql += " AND service_code=?"
            args.append(a["service"])
        if a["q"]:
            sql += " AND (nom LIKE ? OR prenoms LIKE ? OR nip LIKE ? OR poste LIKE ?)"
            args += [f"%{a['q']}%"] * 4
        rows = q(sql + " ORDER BY service_code, nom, prenoms", tuple(args))
        svc = dict(services())
        ref, auj = reference(H.jur_annee()), date.today()
        agents = []
        for r in rows:
            d = agent_valeurs(r)
            if a["role"] and (d.get("role") or "administratif") != a["role"]:
                continue
            f = fiche(dict(d, source="agent", agent_id=r["id"], cs_nom="", zone_nom="", secteur="public"), ref, auj, svc)
            agents.append((r, f))
        if request.args.get("export") == "xlsx":
            try:
                return H.xlsx.reponse_xlsx("agents.xlsx", [lib for _k, lib, _t in CHAMPS_AGENT],
                                           [ligne_export_agent(agent_valeurs(r)) for r, _f in agents], "Agents",
                                           [f"{(H.jur_structure() or {}).get('nom', '')} — agents de la structure",
                                            f"Extrait le {date.today().strftime('%d/%m/%Y')}"])
            except H.xlsx.ExcelIndisponible as e:
                flash(str(e), "danger")
        recus = []
        if niveau() == "ddemp":
            recus = [f for f in collecter(H.jur_annee()) if f["source"] == "agent_cs"]
            recus.sort(key=lambda f: (f.get("cs_nom") or "", f["fonction_txt"], f["nom_complet"]))
        comptes_lies = {u["id"]: u for u in comptes()}
        return render_template("jur_agents.html", agents=agents, a=a, services=services(), roles=ROLES_AGENT, recus=recus,
                               st=stats_sexe([f for _r, f in agents]), comptes=comptes_lies)

    @app.route("/juridiction/agents/nouveau", methods=["GET", "POST"])
    @app.route("/juridiction/agents/<int:aid>", methods=["GET", "POST"])
    @H.connexion_requise("jur_personnel")
    def jur_agent_form(aid=None):
        juridiction_ou_404()
        r = agent_ou_404(aid) if aid else None
        if request.method == "POST":
            v, err = lire_agent(request.form, aid)
            if err:
                for m in err:
                    flash(m, "danger")
                vals = dict(request.form)
                vals["actif"] = request.form.get("actif") == "oui"
                return render_template("jur_agent_form.html", v=vals, aid=aid, **options_form()), 400
            aid = enregistrer_agent(v, aid)
            H.journal("jur_agent", f"{v['nom']} {v['prenoms']}")
            flash("Agent enregistré.", "success")
            return redirect(url_for("jur_agent_form", aid=aid))
        v = agent_valeurs(r) if r else {"actif": True, "role": "administratif", "categorie": "FE",
                                        "departement_a_servir": (H.jur_structure() or {}).get("departement", "")}
        if r:
            for k in ("ceap", "cap", "visite_aptitude"):
                v[k] = tri_etat(v.get(k))
            for k in ("date_naissance", "date_premiere_ps", "date_ps_departement", "date_ps_commune", "date_ps_ecole"):
                if len(str(v.get(k) or "")) == 10 and MC.en_date(v[k]):     # affichage jj/mm/aaaa
                    v[k] = MC.en_date(v[k]).strftime("%d/%m/%Y")
        f = None
        if r:
            f = fiche(dict(v, source="agent", agent_id=r["id"], cs_nom="", zone_nom=""), reference(H.jur_annee()),
                      services=dict(services()))
        return render_template("jur_agent_form.html", v=v, aid=aid, f=f, **options_form())

    def options_form():
        return dict(services=services(), roles=ROLES_AGENT, categories=CATEGORIES, departements=MC.DEPARTEMENTS,
                    diplomes=MC.DIPLOMES, grades=MC.GRADES, postes=POSTES.get(niveau(), []), comptes=comptes())

    @app.route("/juridiction/agents/<int:aid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_personnel")
    def jur_agent_supprimer(aid):
        juridiction_ou_404()
        r = agent_ou_404(aid)
        # retrait logique : l'agent n'apparaît plus (ni dans les listes ni dans le paquet envoyé à la DDEMP),
        # mais sa fiche est conservée et peut être réactivée.
        ex("UPDATE jur_agents SET actif=0, user_id=NULL, maj=datetime('now','localtime') WHERE id=?", (aid,))
        H.journal("jur_agent_retire", f"{r['nom']} {r['prenoms'] or ''}")
        flash(f"Agent « {r['nom']} {r['prenoms'] or ''} » retiré de la liste (fiche conservée, réactivable).", "success")
        return redirect(url_for("jur_agents"))

    @app.route("/juridiction/agents/import", methods=["GET", "POST"])
    @H.connexion_requise("jur_personnel")
    def jur_agents_import():
        juridiction_ou_404()
        if request.args.get("modele"):
            ex_ = {k: "" for k, _l, _t in CHAMPS_AGENT}
            ex_.update(nom="EXEMPLE", prenoms="Jean", sexe="M", nip="123456789012", service_code=services()[0][0],
                       poste=(POSTES.get(niveau()) or [""])[0], role="administratif", categorie="FE", grade="A1-5",
                       date_naissance="15/03/1975", date_premiere_ps="01/10/2000", ceap="oui", annee_ceap="2001",
                       actif="oui")
            return H.xlsx.reponse_xlsx("modele_agents.xlsx", [lib for _k, lib, _t in CHAMPS_AGENT],
                                       [[ex_[k] for k, _l, _t in CHAMPS_AGENT]], "Agents",
                                       ["Codes des services : " + ", ".join(f"{c} = {n}" for c, n in services())])
        if request.method == "POST":
            fic = request.files.get("fichier")
            if not fic or not fic.filename.lower().endswith((".xlsx", ".csv")):
                flash("Choisissez un fichier Excel (.xlsx).", "danger")
                return redirect(url_for("jur_agents_import"))
            try:
                ent, lignes = H.xlsx.lire_tableau(fic, ("nom",))
            except H.xlsx.ExcelIndisponible as e:
                flash(str(e), "danger")
                return redirect(url_for("jur_agents_import"))
            except Exception:  # noqa: BLE001
                flash("Fichier Excel illisible.", "danger")
                return redirect(url_for("jur_agents_import"))
            norm = [H.xlsx.normaliser(h) for h in ent]
            idx = {}
            for k, lib, _t in CHAMPS_AGENT:
                for cand in (lib, k, lib.split(" (")[0]):
                    c = H.xlsx.normaliser(cand)
                    if c in norm:
                        idx[k] = norm.index(c)
                        break
            if "nom" not in idx:
                flash("Colonne « Nom » introuvable (utilisez le modèle).", "danger")
                return redirect(url_for("jur_agents_import"))
            # le libellé du service est accepté à la place du code
            par_nom = {H.xlsx.normaliser(n): c for c, n in services()}
            nb_c, nb_m, erreurs = 0, 0, []
            for n, l in enumerate(lignes, start=2):
                src = {k: H.xlsx.valeur(l, i) for k, i in idx.items()}
                if not src.get("nom"):
                    continue
                if src.get("service_code") and H.xlsx.normaliser(src["service_code"]) in par_nom:
                    src["service_code"] = par_nom[H.xlsx.normaliser(src["service_code"])]
                if "actif" not in idx:
                    src["actif"] = "oui"
                existant = None
                nip = str(src.get("nip") or "").replace(" ", "")
                if nip:
                    existant = q("SELECT * FROM jur_agents WHERE nip=?", (nip,), un=True)
                if not existant:
                    existant = q("SELECT * FROM jur_agents WHERE UPPER(nom)=UPPER(?) AND UPPER(COALESCE(prenoms,''))=UPPER(?)",
                                 (str(src["nom"]).strip(), str(src.get("prenoms") or "").strip()), un=True)
                if existant and "user_id" not in src and existant["user_id"]:
                    src["user_id"] = str(existant["user_id"])
                v, err = lire_agent(src, existant["id"] if existant else None)
                if err:
                    erreurs.append(f"Ligne {n} ({src['nom']}) : " + " ".join(err))
                    continue
                enregistrer_agent(v, existant["id"] if existant else None)
                if existant:
                    nb_m += 1
                else:
                    nb_c += 1
            for m in erreurs[:15]:
                flash(m, "warning")
            if len(erreurs) > 15:
                flash(f"… et {len(erreurs) - 15} autre(s) ligne(s) refusée(s).", "warning")
            flash(f"Import terminé : {nb_c} agent(s) ajouté(s), {nb_m} mis à jour, {len(erreurs)} ligne(s) refusée(s).",
                  "success" if nb_c + nb_m else "warning")
            H.journal("jur_agents_import", f"{nb_c} ajout(s), {nb_m} maj")
            return redirect(url_for("jur_agents"))
        return render_template("jur_agents_import.html", champs=CHAMPS_AGENT, services=services())
