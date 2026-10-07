# -*- coding: utf-8 -*-
"""Documents de l'enseignant (édition « École publique »).

Documents officiels remplis automatiquement avec les données de GESCOL (école, personnel, carrière, élèves,
classes, registre d'appel, notes), complétés dans un formulaire web puis imprimés en PDF à l'identique
des modèles fournis par le client :

* fiches d'évaluation de l'agent contractuel de l'État (ACE) : collaborateurs / adjoints, directeurs,
  nouvelle fiche (collège / lycée) — notes par critère, totaux et classe de performance calculés ;
* certificats et attestations du personnel (« Les différents certificats ») : présence au poste (directeur
  ou CCS), attestation de direction, certificat de travail, prise de service (CCS ou directeur),
  prise en charge (hospitalisation) ;
* certificat de scolarité (nouveau format 2023, en couleur) pour les élèves.

Pour chaque document : PDF individuel, PDF vierge, génération groupée et historique des documents produits.
Règles communes : la ligne « NIP » (personnel.nip / eleves.nip) précède toujours la ligne du nom sur les certificats
et dans l'identification des fiches ; quand la griffe de l'école (cachet rectangulaire du nom, ecoles.griffe_*) est
active, elle remplace le nom en clair sous la signature du directeur (cachet.dessiner_nom).
"""
import json
import os
import re
from datetime import date, datetime

from flask import abort, flash, g, redirect, render_template, request, url_for
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, Table, TableStyle

import config
import pdfs
from pdfs import GCanvas

W, H_PAGE = A4
DOSSIER_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
VERT_BJ = colors.HexColor("#008751")
JAUNE_BJ = colors.HexColor("#FCD116")
ROUGE_BJ = colors.HexColor("#E8112D")

HELV = {"n": "Helvetica", "b": "Helvetica-Bold", "i": "Helvetica-Oblique", "bi": "Helvetica-BoldOblique"}
TIMES = {"n": "Times-Roman", "b": "Times-Bold", "i": "Times-Italic", "bi": "Times-BoldItalic"}

# ------------------------------------------------------------------------------------------------ catalogue
FAMILLES = [
    ("eval", "Fiches d'évaluation du personnel", "Agent contractuel de l'État (ACE) : identification, situation "
     "administrative, objectifs, résultats, notes par critère avec total et classe de performance calculés."),
    ("cert_agent", "Certificats et attestations du personnel", "Modèles « Les différents certificats » : "
     "présence au poste, direction, travail, prise de service, prise en charge."),
    ("cert_eleve", "Certificats des élèves", "Certificat de scolarité (nouveau format 2023, en couleur) avec QR "
     "de vérification."),
]

DOCS = {
    "eval_ace": dict(famille="eval", cible="agent", titre="Fiche d'évaluation des collaborateurs (adjoints)",
                     desc="ACE n'ayant pas la qualité de supérieur hiérarchique immédiat — modèle MEMP / DAF.",
                     qr=False),
    "eval_directeur": dict(famille="eval", cible="agent", titre="Fiche d'évaluation des directeurs",
                           desc="ACE ayant la qualité de supérieur hiérarchique immédiat — modèle MEMP / DAF.",
                           qr=False),
    "eval_secondaire": dict(famille="eval", cible="agent", titre="Nouvelle fiche d'évaluation (collège / lycée)",
                            desc="Modèle MESTFP : DDESTFP, CEG / lycée, classe de recrutement.", qr=False),
    "presence_poste_dir": dict(famille="cert_agent", cible="agent", qr=True,
                               titre="Certificat de présence au poste (délivré par le directeur)",
                               desc="Signé par le directeur et le chef de la circonscription scolaire."),
    "presence_poste_ccs": dict(famille="cert_agent", cible="agent", qr=True,
                               titre="Certificat de présence au poste (délivré par le CCS)",
                               desc="Le chef de la circonscription scolaire certifie la présence au poste."),
    "attestation_direction": dict(famille="cert_agent", cible="agent", qr=True, titre="Attestation de direction",
                                  desc="Délivrée par le CCS au directeur / à la directrice d'école."),
    "certificat_travail": dict(famille="cert_agent", cible="agent", qr=True, titre="Certificat de travail",
                               desc="Délivré par le chef de la circonscription scolaire."),
    "prise_service_ccs": dict(famille="cert_agent", cible="agent", qr=True,
                              titre="Certificat de prise de service (délivré par le CCS)",
                              desc="Affectation, remplacement, acte, fonction, date de prise de service, motif."),
    "prise_service_dir": dict(famille="cert_agent", cible="agent", qr=True,
                              titre="Certificat de prise de service (délivré par le directeur)",
                              desc="Le directeur certifie la prise de service de l'agent affecté à l'école."),
    "prise_en_charge": dict(famille="cert_agent", cible="agent", qr=True,
                            titre="Certificat de prise en charge (hospitalisation)",
                            desc="Admission des fonctionnaires et assimilés : indice, budget, catégorie."),
    "certificat_scolarite": dict(famille="cert_eleve", cible="eleve", qr=True,
                                 titre="Certificat de scolarité (format 2023)",
                                 desc="Identité, matricule EducMaster, fréquentation, cours, assiduité, conduite, "
                                      "travail, observations."),
}

# Critères des fiches d'évaluation : (groupe, [(clé, libellé, barème)])
CRIT_CONSCIENCE = ("Conscience professionnelle (07)", [
    ("ponctualite", "Ponctualité", 2), ("assiduite", "Assiduité", 2),
    ("ethique", "Ethique professionnelle", 1.5), ("valeurs", "Sens des valeurs", 1.5)])
CRITERES = {
    "ace": [
        ("Compétence professionnelle (08)", [("taux", "Taux de réalisation des attentes assignées à l'agent", 8)]),
        CRIT_CONSCIENCE,
        ("Le sens du service public (05)", [("sacrifice", "Esprit de sacrifice", 1),
                                            ("bien_public", "Respect du bien public", 2),
                                            ("hierarchie", "Respect de la hiérarchie", 2)]),
    ],
    "dir": [
        ("Compétence professionnelle (08)", [("taux", "Taux de réalisation des programmes d'activités de la "
                                                      "structure dont ils sont responsables", 8)]),
        CRIT_CONSCIENCE,
        ("Le sens de leadership (05)", [("animation", "Sens de l'animation d'équipe", 1),
                                        ("encadrement", "aptitude à l'encadrement", 2),
                                        ("evaluer", "Capacité à évaluer", 2)]),
    ],
}
TABLES_NOTES = [("sh", "3.4 - Note et appréciation du supérieur hiérarchique"),
                ("cd", "3.5 - Note et appréciation du comité de direction")]
# Classes de performance (note sur 20) — proposées automatiquement, modifiables dans le formulaire.
CLASSES_PERF = [(18, "Excellent"), (16, "Très bon"), (14, "Bon"), (12, "Assez bon"), (10, "Passable"),
                (0, "Insuffisant")]


def criteres_de(doc):
    return CRITERES["dir"] if doc == "eval_directeur" else CRITERES["ace"]


def classe_perf(total):
    if total is None:
        return ""
    return next(lib for seuil, lib in CLASSES_PERF if total >= seuil)


def fmt_note(n):
    if n is None:
        return ""
    s = f"{n:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def lire_note_bareme(brut, bareme):
    """'' -> None ; '1,5' -> 1.5 ; ValueError si invalide ou hors barème."""
    brut = (brut or "").strip().replace(",", ".")
    if not brut:
        return None
    v = float(brut)
    if not 0 <= v <= bareme:
        raise ValueError
    return round(v, 2)


def totaux(doc, v):
    """{'sh': total|None, 'cd': total|None} à partir des notes enregistrées dans v."""
    res = {}
    for t, _ in TABLES_NOTES:
        notes = []
        for _g, crits in criteres_de(doc):
            for k, _l, bar in crits:
                try:
                    n = lire_note_bareme(v.get(f"{t}_{k}"), bar)
                except ValueError:
                    n = None
                if n is not None:
                    notes.append(n)
        res[t] = round(sum(notes), 2) if notes else None
    return res


# ------------------------------------------------------------------------------------------------ champs
# clé -> (libellé, type) ; types : t = texte, z = zone de texte, date = jj/mm/aaaa, civ = M./Mme, sexe, dir
CHAMPS = {
    "ref": ("Référence du document (SO N° …)", "t"),
    "soussigne": ("Je soussigné(e) (nom du signataire)", "t"),
    "directeur_titre": ("Directeur / Directrice (signataire)", "dir"),
    "directeur_nom": ("Nom du directeur / de la directrice", "t"),
    "ccs_nom": ("Chef de la circonscription scolaire (nom)", "t"),
    "cs": ("Circonscription scolaire", "t"),
    "departement": ("Département", "t"),
    "ecole": ("École", "t"),
    "localite": ("Localité (« de : … »)", "t"),
    "civilite": ("Civilité", "civ"),
    "nip": ("NIP (Numéro d'Identification Personnel)", "t"),
    "nom_prenoms": ("Nom et prénom(s)", "t"),
    "lieu_naissance": ("Lieu de naissance", "t"),
    "date_naissance": ("Date de naissance", "date"),
    "telephone": ("Téléphone", "t"),
    "email": ("E-mail", "t"),
    "situation_famille": ("Situation de famille", "t"),
    "situation_militaire": ("Situation militaire", "t"),
    "diplome_recrutement": ("Diplôme de recrutement", "t"),
    "classe_recrutement": ("Classe de recrutement", "t"),
    "matricule": ("Matricule", "t"),
    "adresse": ("Adresse", "t"),
    "date_prise_service": ("Date de première prise de service", "date"),
    "grade": ("Grade actuel", "t"),
    "categorie": ("Catégorie", "t"),
    "echelle": ("Echelle", "t"),
    "echelon": ("Echelon", "t"),
    "emploi": ("Emploi", "t"),
    "contrat_initial": ("Contrat initial", "t"),
    "contrat_renouvele": ("Contrat de travail renouvelé", "t"),
    "contrat_cdi": ("Contrat à durée indéterminée", "t"),
    "avenants": ("Avenant(s)", "z"),
    "fait_a": ("Fait à", "t"),
    "fait_le": ("le", "date"),
    "periode_debut": ("Période de référence : du", "date"),
    "periode_fin": ("au", "date"),
    "objectifs": ("3.1 - Rappel des objectifs sur la période (une ligne par objectif)", "z"),
    "resultats": ("3.2 - Résultats de la période (une ligne par résultat)", "z"),
    "contraintes": ("3.3 - Contraintes et difficultés (une ligne par point)", "z"),
    "sup_titre": ("Titre du supérieur hiérarchique", "t"),
    "sup_nom": ("Prénoms et nom du supérieur hiérarchique", "t"),
    "resp_titre": ("Titre du responsable de la structure", "t"),
    "resp_nom": ("Prénoms et nom du responsable de la structure", "t"),
    "ddes": ("Direction départementale (DDESTFP) de", "t"),
    "etablissement": ("Collège d'enseignement général / lycée de", "t"),
    "corps_grade": ("Corps et grade payé", "t"),
    "en_service_a": ("Est en service à", "t"),
    "suivant": ("Suivant (acte : arrêté, décision, note de service…)", "t"),
    "acte": ("Arrêté / décision / note de service N°", "t"),
    "acte_date": ("Date de l'acte (du …)", "date"),
    "fonction": ("En qualité de (fonction)", "t"),
    "depuis": ("Depuis le", "date"),
    "jusqu_au": ("Jusqu'à ce jour", "date"),
    "affecte_a": ("Affecté(e) à", "t"),
    "du_lieu": ("Du (date d'affectation)", "t"),
    "direction_de": ("Est effectivement directeur / directrice de EM/EP", "t"),
    "nb_classes": ("Nombre de classes", "t"),
    "pour_compter": ("Pour compter du", "date"),
    "remplace_nom": ("En remplacement de (M. / Mme, nom)", "t"),
    "remplace_matricule": ("Matricule de l'agent remplacé", "t"),
    "motif": ("Motif", "t"),
    "date_effective": ("A effectivement pris service le", "date"),
    "profession": ("Profession", "t"),
    "indice": ("Indice de traitement", "t"),
    "budget": ("Budget devant supporter l'hospitalisation", "t"),
    "categorie_hosp": ("Catégorie d'hospitalisation", "t"),
    # élève
    "ecole_l1": ("ÉCOLE (1re ligne de l'en-tête)", "t"),
    "ecole_l2": ("(2e ligne de l'en-tête)", "t"),
    "ecole_de": ("DE (localité de l'en-tête)", "t"),
    "ecole_designation": ("de l'École (désignation complète)", "z"),
    "sexe": ("Sexe", "sexe"),
    "frequente_du": ("A fréquenté l'école du", "date"),
    "frequente_au": ("au", "t"),
    "cours": ("Élève du cours", "t"),
    "assiduite": ("ASSIDUITÉ", "t"),
    "conduite": ("CONDUITE", "t"),
    "travail": ("TRAVAIL", "t"),
    "observations": ("OBSERVATIONS PARTICULIÈRES", "z"),
}

_ID_ACE = ["nip", "nom_prenoms", "lieu_naissance", "date_naissance", "telephone", "email", "situation_famille",
           "situation_militaire", "diplome_recrutement", "matricule", "adresse"]
_ADM = ["date_prise_service", "grade", "categorie", "echelle", "echelon", "emploi"]
_EVAL = ["periode_debut", "periode_fin", "objectifs", "resultats", "contraintes"]
_SIGN_EVAL = ["sup_titre", "sup_nom", "resp_titre", "resp_nom"]

# Sections du formulaire : doc -> [(titre, [clés])]
SECTIONS = {
    "eval_ace": [("1 - Identification de l'agent", _ID_ACE),
                 ("2 - Situation administrative de l'agent", _ADM),
                 ("Référence des actes de carrière", ["contrat_initial", "contrat_renouvele", "contrat_cdi",
                                                      "avenants", "fait_a", "fait_le"]),
                 ("3 - Évaluation", _EVAL), ("Signataires", _SIGN_EVAL)],
    "eval_secondaire": [("En-tête", ["ddes", "etablissement"]),
                        ("I - Identification de l'agent", ["nip", "nom_prenoms", "lieu_naissance", "date_naissance",
                                                           "telephone", "email", "classe_recrutement",
                                                           "diplome_recrutement", "matricule", "adresse"]),
                        ("2 - Situation administrative de l'agent", _ADM + ["contrat_initial", "fait_a",
                                                                            "fait_le"]),
                        ("3 - Évaluation", _EVAL), ("Signataires", _SIGN_EVAL)],
    "presence_poste_dir": [("Signataires", ["ref", "soussigne", "directeur_titre", "ecole", "localite", "ccs_nom"]),
                           ("Agent", ["civilite", "nip", "nom_prenoms", "date_naissance", "lieu_naissance",
                                      "date_prise_service", "matricule", "corps_grade", "en_service_a", "cs",
                                      "departement", "suivant", "fonction", "depuis", "jusqu_au", "fait_a",
                                      "fait_le"])],
    "presence_poste_ccs": [("Signataire", ["ref", "ccs_nom", "cs", "departement"]),
                           ("Agent", ["civilite", "nip", "nom_prenoms", "date_naissance", "lieu_naissance",
                                      "date_prise_service", "matricule", "corps_grade", "en_service_a", "acte",
                                      "acte_date", "fonction", "depuis", "jusqu_au", "fait_a", "fait_le"])],
    "attestation_direction": [("Signataire", ["ref", "ccs_nom", "cs"]),
                              ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule", "affecte_a", "du_lieu",
                                         "direction_de", "depuis", "nb_classes", "pour_compter", "acte",
                                         "acte_date", "remplace_nom", "remplace_matricule", "motif", "fait_a",
                                         "fait_le"])],
    "certificat_travail": [("Signataire", ["ref", "ccs_nom", "cs"]),
                           ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule", "en_service_a", "acte",
                                      "acte_date", "fonction", "depuis", "jusqu_au", "fait_a", "fait_le"])],
    "prise_service_ccs": [("Signataire", ["ref", "ccs_nom", "cs"]),
                          ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule", "affecte_a", "remplace_nom",
                                     "acte", "acte_date", "fonction", "nb_classes", "date_effective", "motif",
                                     "fait_a", "fait_le"])],
    "prise_service_dir": [("Signataire", ["ref", "soussigne", "directeur_titre", "ecole", "localite"]),
                          ("Agent", ["civilite", "nip", "nom_prenoms", "grade", "matricule", "affecte_a", "acte",
                                     "acte_date", "fonction", "date_effective", "fait_a", "fait_le"])],
    "prise_en_charge": [("En-tête", ["departement", "cs", "ref", "ccs_nom"]),
                        ("Malade", ["nip", "nom_prenoms", "profession", "en_service_a", "indice", "budget",
                                    "categorie_hosp", "fait_a", "fait_le"])],
    "certificat_scolarite": [("En-tête de l'école", ["ecole_l1", "ecole_l2", "ecole_de", "directeur_titre",
                                                     "ecole_designation"]),
                             ("Élève", ["nip", "nom_prenoms", "sexe", "lieu_naissance", "date_naissance", "matricule",
                                        "frequente_du", "frequente_au", "cours", "depuis"]),
                             ("Notes et observations", ["assiduite", "conduite", "travail", "observations"]),
                             ("Signature", ["fait_a", "fait_le", "directeur_nom"])],
}
SECTIONS["eval_directeur"] = SECTIONS["eval_ace"]


def cles_doc(doc):
    ks = [k for _t, liste in SECTIONS[doc] for k in liste]
    if DOCS[doc]["famille"] == "eval":
        for t, _ in TABLES_NOTES:
            ks += [f"{t}_{k}" for _g, crits in criteres_de(doc) for k, _l, _b in crits] + [f"{t}_classe"]
    return ks


# ------------------------------------------------------------------------------------------------ outils texte
def date_fr(iso):
    if not iso:
        return ""
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(iso)


def aujourdhui():
    return date.today().strftime("%d/%m/%Y")


def lire_date_fr(s):
    """'12/03/2026' -> date, sinon None."""
    try:
        return datetime.strptime((s or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def suffixe_dir(titre_ou_sexe):
    t = (titre_ou_sexe or "").lower()
    if t in ("f", "directrice", "la directrice") or "directrice" in t:
        return "rice"
    if t in ("m", "directeur", "le directeur") or "directeur" in t:
        return "eur"
    return ""


def titre_dir(titre):
    """« Directeur » -> « Le Directeur » ; « Directrice » -> « La Directrice »."""
    s = suffixe_dir(titre)
    return {"eur": "Le Directeur", "rice": "La Directrice"}.get(s, "")


# ================================================================================================ PDF : primitives
def sw(c, t, f, s):
    return c.stringWidth(t, f, s)


def pointilles(c, x1, x2, y, font, size):
    if x2 - x1 < 3:
        return
    w = sw(c, ".", font, size)
    c.setFont(font, size)
    c.drawString(x1, y, "." * int((x2 - x1) / w))


def texte_ajuste(c, x, y, largeur, texte, font, size, mini=6):
    """Écrit texte dans la largeur, en réduisant la taille si besoin (puis en tronquant). Retourne la largeur."""
    s = size
    while s > mini and sw(c, texte, font, s) > largeur:
        s -= 0.5
    while texte and sw(c, texte, font, s) > largeur:
        texte = texte[:-1]
    c.setFont(font, s)
    c.drawString(x, y, texte)
    return sw(c, texte, font, s)


def T(texte, style="n"):
    return ("t", texte, style)


def V(cle, poids=1.0):
    return ("v", cle, poids)


def D(cle, poids=1.0):
    return ("d", cle, poids)


def S(cle, vide=40, style="b"):
    return ("s", cle, vide, style)


def C(cle, defaut, style="n"):
    return ("c", cle, defaut, style)


def ligne(c, x, y, x2, segs, v, fam, size, align="l", style_val="b"):
    """Dessine une ligne « libellé ……valeur…… » : segments texte (T), valeurs extensibles (V, D) complétées de
    pointillés, valeurs ajustées (S) et textes conditionnels (C). v = valeurs (dict de chaînes)."""
    fixes, flex = [], 0.0
    for s in segs:
        k = s[0]
        if k == "t":
            fixes.append(sw(c, s[1], fam[s[2]], size))
        elif k == "c":
            fixes.append(sw(c, str(v.get(s[1]) or s[2]), fam[s[3]], size))
        elif k == "s":
            val = str(v.get(s[1]) or "")
            fixes.append(sw(c, val, fam[s[3]], size) if val else s[2])
        else:
            fixes.append(None)
            flex += s[2]
    total_fixe = sum(f for f in fixes if f is not None)
    reste = max(0.0, (x2 - x) - total_fixe)
    if flex == 0:
        if align == "c":
            x = (x + x2) / 2 - total_fixe / 2
        elif align == "r":
            x = x2 - total_fixe
    for s, f in zip(segs, fixes):
        k = s[0]
        if k == "t":
            c.setFont(fam[s[2]], size)
            c.drawString(x, y, s[1])
            x += f
        elif k == "c":
            c.setFont(fam[s[3]], size)
            c.drawString(x, y, str(v.get(s[1]) or s[2]))
            x += f
        elif k == "s":
            val = str(v.get(s[1]) or "")
            if val:
                c.setFont(fam[s[3]], size)
                c.drawString(x, y, val)
            else:
                pointilles(c, x, x + f, y, fam["n"], size)
            x += f
        else:
            larg = reste * s[2] / flex
            val = str(v.get(s[1]) or "").replace("\n", " ").strip()
            if val:
                lw = texte_ajuste(c, x + 2, y, larg - 4, val, fam[style_val], size)
                pointilles(c, x + lw + 4, x + larg, y, fam["n"], size)
            elif k == "d":  # date vierge : ……/……/……
                tiers = larg / 3
                wsl = sw(c, "/", fam["n"], size)
                for i in range(3):
                    pointilles(c, x + i * tiers, x + (i + 1) * tiers - (wsl if i < 2 else 0), y, fam["n"], size)
                    if i < 2:
                        c.setFont(fam["n"], size)
                        c.drawString(x + (i + 1) * tiers - wsl, y, "/")
            else:
                pointilles(c, x, x + larg, y, fam["n"], size)
            x += larg


def couper(c, texte, font, size, largeurs):
    """Découpe texte (retours à la ligne respectés) selon une largeur par ligne (la dernière se répète)."""
    lignes = []
    for para in str(texte or "").splitlines():
        cur = ""
        for mot in para.split():
            larg = largeurs[min(len(lignes), len(largeurs) - 1)]
            essai = (cur + " " + mot).strip()
            if not cur or sw(c, essai, font, size) <= larg:
                cur = essai
            else:
                lignes.append(cur)
                cur = mot
        if cur:
            lignes.append(cur)
    return lignes


def flux(c, x, y, x2, xplein, libelle, texte, nb, pas, fam, size, style_lib="n", style_val="b", minimum=None):
    """Libellé puis valeur répartie sur nb lignes pointillées (1re après le libellé, suivantes pleine largeur).
    Retourne l'ordonnée de la ligne suivante."""
    c.setFont(fam[style_lib], size)
    c.drawString(x, y, libelle)
    x0 = x + sw(c, libelle, fam[style_lib], size) + (2 if libelle else 0)
    lignes = couper(c, texte, fam[style_val], size, [x2 - x0 - 4, x2 - xplein - 4])
    nb = max(nb, minimum or 0)
    if len(lignes) > nb:  # trop long : on garde tout en fusionnant la fin sur la dernière ligne
        lignes = lignes[:nb - 1] + [" ".join(lignes[nb - 1:])]
    for i in range(nb):
        xd = x0 if i == 0 else xplein
        val = lignes[i] if i < len(lignes) else ""
        if val:
            lw = texte_ajuste(c, xd + 2, y, x2 - xd - 4, val, fam[style_val], size)
            pointilles(c, xd + lw + 4, x2, y, fam["n"], size)
        else:
            pointilles(c, xd, x2, y, fam["n"], size)
        y -= pas
    return y


def barre_drapeau(c, x, y, w, h, style="tiers"):
    """Bande aux couleurs nationales. « tiers » : vert | jaune | rouge ; « moitie » : vert | (jaune / rouge)."""
    c.saveState()
    if style == "moitie":
        c.setFillColor(VERT_BJ)
        c.rect(x, y, w / 2, h, stroke=0, fill=1)
        c.setFillColor(JAUNE_BJ)
        c.rect(x + w / 2, y + h / 2, w / 2, h / 2, stroke=0, fill=1)
        c.setFillColor(ROUGE_BJ)
        c.rect(x + w / 2, y, w / 2, h / 2, stroke=0, fill=1)
    else:
        for i, col in enumerate((VERT_BJ, JAUNE_BJ, ROUGE_BJ)):
            c.setFillColor(col)
            c.rect(x + i * w / 3, y, w / 3, h, stroke=0, fill=1)
    c.restoreState()


_IMAGES = {}


def image_static(nom):
    """Image fournie avec le module (armoiries, bloc MEMP), mise en cache."""
    if nom not in _IMAGES:
        chemin = os.path.join(DOSSIER_STATIC, nom)
        _IMAGES[nom] = ImageReader(chemin) if os.path.exists(chemin) else None
    return _IMAGES[nom]


def armoiries(c, x, y_haut, hauteur):
    img = image_static("docs_enseignant_armoiries.png")
    if img:
        iw, ih = img.getSize()
        c.drawImage(img, x, y_haut - hauteur, hauteur * iw / ih, hauteur, mask="auto")


def bloc_memp(c, x, y_haut, hauteur):
    """Bloc « armoiries + MINISTÈRE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE + RÉPUBLIQUE DU BÉNIN »."""
    img = image_static("docs_enseignant_memp.png")
    if img:
        iw, ih = img.getSize()
        c.drawImage(img, x, y_haut - hauteur, hauteur * iw / ih, hauteur)
        return hauteur * iw / ih
    armoiries(c, x, y_haut, hauteur)
    c.setFont("Helvetica", hauteur / 7)
    for i, t in enumerate(("MINISTÈRE", "DES ENSEIGNEMENTS", "MATERNEL ET PRIMAIRE", "", "RÉPUBLIQUE DU BÉNIN")):
        c.drawString(x + hauteur * 1.2, y_haut - (i + 1) * hauteur / 5.5, t)
    return hauteur * 3.4


def lignes_droite(c, x_droite, y, lignes, font, size, pas):
    c.setFont(font, size)
    for i, t in enumerate(lignes):
        c.drawRightString(x_droite, y - i * pas, t)


def image_sig(dataurl):
    return pdfs.image_data_url(dataurl) if dataurl else None


def griffe_dir(c, cx, cy, largeur=130, griffe=None):
    """Griffe (cachet rectangulaire du nom) du directeur de l'école courante — ou griffe (lignes, couleur) donnée —
    centrée en (cx, cy). Retourne la hauteur dessinée (0 si inactive)."""
    return pdfs.griffe_ecole(c, cx, cy, largeur, griffe)


def signature_bloc(c, x_centre, y, titre, nom, fam, size_titre, style_titre="b", image=None, cachet=False,
                   hauteur=62, size_nom=None, style_nom="b", griffe=None):
    """Titre, (cachet + signature), nom. y = ligne de base du titre. Si la griffe de l'école est active (cachet=True)
    ou qu'une griffe est donnée, elle remplace la ligne du nom (nom lisible dans la griffe)."""
    c.setFont(fam[style_titre], size_titre)
    c.drawCentredString(x_centre, y, titre)
    if cachet:
        pdfs.cachet_ecole(c, x_centre - 30, y - 34, 27)
    if image is not None:
        c.drawImage(image, x_centre - 60, y - hauteur + 8, 120, hauteur - 18, preserveAspectRatio=True, mask="auto")
    gr = griffe if griffe is not None else (config.ECOLE.get("_griffe") if cachet else None)
    if nom and gr:
        griffe_dir(c, x_centre + 12, y - hauteur - 4, 130, gr)
    elif nom:
        c.setFont(fam[style_nom], size_nom or size_titre)
        c.drawCentredString(x_centre, y - hauteur, nom)


# ================================================================================================ PDF : fiches d'évaluation
ST_CELL = ParagraphStyle("de_cell", fontName="Helvetica", fontSize=9.5, leading=11.5)
ST_CELL_B = ParagraphStyle("de_cellb", parent=ST_CELL, fontName="Helvetica-Bold", alignment=TA_CENTER)


def tableau_notes(c, doc, v, t, x, y_haut, largeurs, style):
    """Tableau « Critères de performance / Note par critère / Total / Classe de performance »."""
    fam = TIMES if style == "dir" else HELV
    size = 9 if style == "dir" else 9.5
    st = ParagraphStyle("c", parent=ST_CELL, fontSize=size, leading=size + 2)
    stb = ParagraphStyle("cb", parent=st, fontName="Helvetica-Bold", alignment=TA_CENTER)
    st_grp = ParagraphStyle("g", parent=st, fontName="Helvetica-Bold" if style == "dir" else "Helvetica",
                            alignment=TA_CENTER if style == "dir" else 0)
    if style == "sec":
        stb = ParagraphStyle("cb2", parent=st)
    entete = [Paragraph("Critères de performance" if style != "dir" else "Critère de performance", stb), "",
              Paragraph("Note par critère", stb), Paragraph("Total", stb), Paragraph("Classe de performance", stb)]
    data, spans, ligne_i = [entete], [("SPAN", (0, 0), (1, 0))], 1
    tot = totaux(doc, v)[t]
    classe = v.get(f"{t}_classe") or (classe_perf(tot) if tot is not None else "")
    for grp, crits in criteres_de(doc):
        debut = ligne_i
        for j, (k, lib, bar) in enumerate(crits):
            try:
                n = lire_note_bareme(v.get(f"{t}_{k}"), bar)
            except ValueError:
                n = None
            barre = "/" + (f"{int(bar):02d}" if bar == int(bar) else fmt_note(bar))
            if n is not None:
                note_txt = f"<b>{fmt_note(n)}</b>{barre}"
            else:
                note_txt = barre if style == "dir" else "…………" + barre
            nom_grp = grp.replace(" (", "<br/>(") if style != "dir" else grp.replace(" (", "<br/>(")
            data.append([Paragraph(nom_grp, st_grp) if j == 0 else "",
                         Paragraph((". " if style == "dir" else "") + lib, st),
                         Paragraph(note_txt, ParagraphStyle("n", parent=st, alignment=TA_CENTER)), "", ""])
            ligne_i += 1
        if ligne_i - 1 > debut:
            spans.append(("SPAN", (0, debut), (0, ligne_i - 1)))
    spans += [("SPAN", (3, 1), (3, ligne_i - 1)), ("SPAN", (4, 1), (4, ligne_i - 1))]
    if tot is not None:
        data[1][3] = Paragraph(f"<b>{fmt_note(tot)}</b> / 20", ParagraphStyle("t", parent=st, alignment=TA_CENTER,
                                                                             fontSize=size + 2, leading=size + 4))
    if classe:
        data[1][4] = Paragraph(f"<b>{classe}</b>", ParagraphStyle("k", parent=st, alignment=TA_CENTER))
    tb = Table(data, colWidths=largeurs)
    tb.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("VALIGN", (0, 0), (-1, 0), "TOP" if style == "sec" else "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ] + spans))
    _, h = tb.wrapOn(c, sum(largeurs), 400)
    tb.drawOn(c, x, y_haut - h)
    return y_haut - h


def puces(c, x, y, x2, texte, pas, fam, size, nb=3):
    """Lignes « - … » (au moins nb)."""
    lignes = couper(c, texte, fam["n"], size, [x2 - x - 10])
    lignes = lignes[:6]
    for i in range(max(nb, len(lignes))):
        c.setFont(fam["n"], size)
        c.drawString(x, y, "-")
        if i < len(lignes):
            texte_ajuste(c, x + 9, y, x2 - x - 10, lignes[i], fam["n"], size)
        y -= pas
    return y


def page_evaluation(c, doc, v, opt):
    """Page 2 commune des fiches d'évaluation (3 - Évaluation, tableaux de notes, signatures)."""
    if doc == "eval_directeur":
        fam, size, x1, x2 = HELV, 9.5, 29, 560
        pas = 15.5
        y = H_PAGE - 35
        c.setFont("Times-Bold", 11.5)
        c.drawCentredString(W / 2, y, "3- EVALUATION")
        y -= 27
        ligne(c, x1, y, 450, [T("Période de référence :   "), D("periode_debut", 1), T("  à  "),
                              D("periode_fin", 1)], v, fam, size)
        y -= 25
        titres = ["3.1. Rappel des objectifs sur la période :", "3.2. Résultats de la période :",
                  "3.3. Contraintes et difficultés :"]
        style_titre, xp = "n", x1 + 18
    else:
        sec = doc == "eval_secondaire"
        fam, size, x1, x2 = HELV, 10.5 if not sec else 11, 66 if not sec else 42, 531 if not sec else 516
        pas = 17
        y = H_PAGE - 40
        c.setFont("Helvetica-Bold", 11.5)
        c.drawString(x1, y, "3- Evaluation" if not sec else "3-Evaluation")
        y -= 17
        ligne(c, x1, y, x2, [T("Période de référence : " if not sec else "Période de référence :"),
                             D("periode_debut", 1), T("   à   "), D("periode_fin", 1)], v, fam, size)
        y -= 17
        if sec:
            titres = ["3.1- Rappel des objectifs sur la période :", "3.2-Résultats de la période",
                      "3.3- Contraintes et difficultés"]
            style_titre = "n"
        else:
            titres = ["3.1- Rappel des objectifs sur la période", "3.2- Résultats de la période",
                      "3.3- Contraintes et difficultés"]
            style_titre = "b"
        xp = x1
    for titre, cle in zip(titres, ("objectifs", "resultats", "contraintes")):
        c.setFont(fam[style_titre], size + (1 if style_titre == "b" else 0))
        c.drawString(x1, y, titre)
        y -= pas
        y = puces(c, xp, y, x2, v.get(cle, ""), pas, fam, size)
        y -= 1 if doc != "eval_directeur" else 3
    # tableaux de notes
    if doc == "eval_directeur":
        largeurs, st = [104, 177, 78, 63, 114], "dir"
    elif doc == "eval_secondaire":
        largeurs, st = [98, 154, 72, 60, 94], "sec"
    else:
        largeurs, st = [90, 155, 78.5, 55, 86.5], "ace"
    for i, (t, titre) in enumerate(TABLES_NOTES):
        lib = titre.replace(" - ", "- " if st == "ace" else ("-" if st == "sec" else ". "), 1)
        lib = lib.replace("3.4", "3.4" + (" " if st == "dir" else ""), 1)
        if st == "dir":
            lib = "3.4.  Note et appréciation du supérieur hiérarchique" if t == "sh" else \
                "3.5. Note et appréciation du comité de direction"
            if t == "cd":
                y -= 18
        c.setFont(fam["b" if st == "ace" else "n"], size + (1.5 if st == "ace" else 0.5))
        c.drawString(x1 if st != "dir" else x1 + 4, y, lib)
        y = tableau_notes(c, doc, v, t, x1 if st != "dir" else 24, y - 4, largeurs, st) - (20 if i == 0 else 0)
        if st == "dir" and i == 0:
            y += 4
    # signatures
    y -= 26 if st != "dir" else 34
    vierge = opt.get("vierge")
    signer = opt.get("signer")
    qui = SIGNATAIRES_EVAL[doc]
    if st == "sec":
        titres_sig = [v.get("sup_titre") or "Le supérieur hiérarchique", v.get("resp_titre") or "Le Chef d'établissement"]
        xs = [x1 + 5, 350]
        noms = [v.get("sup_nom", ""), v.get("resp_nom", "")]
        fs, stl = 11, "n"
    else:
        titres_sig = [v.get("sup_titre") or ("Préciser le titre du supérieur hiérarchique" if st == "ace"
                                             else "Préciser le titre du supérieur Hiérarchique"),
                      v.get("resp_titre") or "Préciser le titre du responsable de la structure"]
        noms = [v.get("sup_nom") or ("Prénoms et Nom supérieur hiérarchique" if st == "ace"
                                     else "Nom et Prénoms du supérieur Hiérarchique"),
                v.get("resp_nom") or ("Prénoms et Nom du responsable de la structure" if st == "ace"
                                      else "Nom et Prénoms du responsable de la structure")]
        xs = [x1 if st == "ace" else 26, 345 if st == "ace" else 315]
        fs, stl = (8, "n") if st == "ace" else (10, "b")
    for i in range(2):
        lim = (xs[1] - xs[0] - 12) if i == 0 else (W - 22 - xs[1])
        titre_i = titres_sig[i]
        largeur_titre = texte_ajuste(c, xs[i], y, lim, titre_i, fam[stl], fs)
        cx = xs[i] + largeur_titre / 2
        griffe = None
        if not vierge and signer:
            img, cach = image_signataire(qui[i], opt)
            if cach:
                pdfs.cachet_ecole(c, cx - 25, y - 38, 26)
                griffe = config.ECOLE.get("_griffe")
            if img is not None:
                c.drawImage(img, cx - 55, y - 62, 110, 50, preserveAspectRatio=True, mask="auto")
        est_nom = bool(v.get("sup_nom" if i == 0 else "resp_nom"))
        if griffe and est_nom:
            griffe_dir(c, cx + 10, y - (80 if st == "sec" else 96), min(130, lim), griffe)
        elif st == "sec":
            if noms[i]:
                texte_ajuste(c, xs[i], y - 75, lim, noms[i], fam["b"], fs)
        else:
            f_nom = fam["b"] if est_nom and st == "ace" else fam[stl]
            texte_ajuste(c, xs[i], y - (88 if st == "ace" else 95), lim, noms[i],
                         f_nom, fs + (1 if est_nom and st == "ace" else 0))


# signataires des fiches : (gauche, droite) parmi 'dir', 'ccs', None
SIGNATAIRES_EVAL = {"eval_ace": ("dir", "ccs"), "eval_directeur": ("ccs", None), "eval_secondaire": (None, "dir")}


def image_signataire(qui, opt):
    """(image de signature, cachet ?) du signataire."""
    if qui == "dir":
        return pdfs.signature_directeur(), True
    if qui == "ccs":
        return image_sig(opt.get("sig_ccs")), False
    return None, False


def page1_ace(c, v, opt):
    """Fiche collaborateurs / adjoints — page 1 (modèle MEMP/DAF, Calibri)."""
    fam, size = HELV, 11
    armoiries(c, 49, H_PAGE - 36, 72)
    c.setFont("Helvetica", 8.2)
    c.drawString(135, H_PAGE - 48, "MINISTERE  DES  ENSEIGNEMENTS")
    c.drawString(135, H_PAGE - 59, "MATERNEL  ET  PRIMAIRE")
    barre_drapeau(c, 135, H_PAGE - 67, 113, 2.4)
    c.drawString(135, H_PAGE - 82, "REPUBLIQUE DU BENIN")
    c.setFont("Helvetica-Bold", 8.2)
    c.drawCentredString(207, H_PAGE - 104, "DIRECTION DE L'ADMINISTRATION")
    c.drawCentredString(207, H_PAGE - 115, "ET DES FINANCES")
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(298, H_PAGE - 151, "FICHE D'EVALUATION DE L'AGENT CONTRACTUEL DE L'ETAT")
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(298, H_PAGE - 166, "(Pour ACE n'ayant pas la qualité de supérieur hiérarchique immédiat)")
    x1, x2, pas = 89, 522, 23
    c.setFont("Helvetica-Bold", 12)
    c.drawString(107, H_PAGE - 201, "1- Identification de l'agent")
    y = H_PAGE - 224
    for segs in lignes_identification(v, secondaire=False):
        ligne(c, x1, y, x2, segs, v, fam, size)
        y -= pas
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(107, y, "2-  Situation administrative de l'agent")
    y -= 23
    for segs in lignes_admin():
        ligne(c, x1, y, x2, segs, v, fam, size)
        y -= pas
    y -= 18
    c.setFont("Helvetica-Bold", 12)
    c.drawString(105, y, "Référence des actes de carrière :")
    y -= 22
    for segs in ([T("Contrat initial : "), V("contrat_initial")], [T("Contrat de travail renouvelé : "),
                                                                    V("contrat_renouvele")],
                 [T("Contrat à durée indéterminé : "), V("contrat_cdi")]):
        ligne(c, x1, y, x2 - 6, segs, v, fam, size)
        y -= pas
    y = flux(c, x1, y, x2 - 6, x1, "Avenant : ", v.get("avenants", ""), 1, pas, fam, size,
             minimum=min(3, len(couper(c, v.get("avenants", ""), "Helvetica-Bold", size, [380]))) or 1)
    y -= 14
    ligne(c, 250, y, 525, [T("Fait à "), V("fait_a", 1.3), T(", le "), V("fait_le", 1)], v, fam, 8.5, align="r")
    signature_agent(c, v, 525, y - 43, y - 105, fam, 11, "r")


def lignes_identification(v, secondaire=False):
    L = [[T("NIP : "), V("nip")],
         [T("Nom et prénom(s) : " if not secondaire else "Nom et prénoms : "), V("nom_prenoms")],
         [T("Lieu et date de naissance : "), V("_lieu_date")],
         [T("Tél : "), V("telephone", 0.55), T("  E-mail : " if not secondaire else "Email :"), V("email", 1)]]
    if secondaire:
        L += [[T("Classe de recrutement :"), V("classe_recrutement")]]
    else:
        L += [[T("Situation Familiale : "), V("situation_famille")], [T("Situation militaire : "),
                                                                      V("situation_militaire")]]
    L += [[T("Diplôme de recrutement : " if not secondaire else "Diplôme de recrutement :"),
           V("diplome_recrutement")],
          [T("Matricule : " if not secondaire else "Matricule :"), V("matricule", 1)] + ([T(" ")] if not secondaire
                                                                                        else [T("", "n")]),
          [T("Adresse : " if not secondaire else "Adresse :"), V("adresse", 1)]]
    return L


def lignes_admin(secondaire=False):
    sep = " : " if not secondaire else " :"
    return [[T("Date de première prise de service" + sep), V("date_prise_service")],
            [T("Grade actuel" + sep), V("grade", 1.2), T("  Catégorie" + sep), V("categorie", 0.6),
             T("  Echelle" + sep), V("echelle", 0.6), T("  Echelon" + sep), V("echelon", 0.6)],
            [T("Emploi" + sep), V("emploi")]]


def signature_agent(c, v, x, y_titre, y_nom, fam, size, align="r"):
    """« Signature de l'agent » puis « Prénom (s) et Nom » (remplacé par le nom de l'agent)."""
    nom = v.get("_prenoms_nom") or ""
    c.setFont(fam["n"], size)
    dessin = c.drawRightString if align == "r" else c.drawString
    dessin(x, y_titre, "Signature de l'agent")
    if nom:
        c.setFont(fam["b"], size)
        dessin(x, y_nom, nom)
    else:
        dessin(x, y_nom, "Prénom (s) et Nom")


def page1_directeur(c, v, opt):
    """Fiche directeurs — page 1 (bandeau MEMP, titres en Times)."""
    fam, size = HELV, 9
    bandeau_memp(c, H_PAGE - 28, "memp.info@gouv.bj", marge_g=34, marge_d=560, hauteur=36)
    c.setFont("Times-BoldItalic", 13.5)
    c.drawString(58, H_PAGE - 90, "Ministère  des  Enseignements  Maternel  et  Primaire")
    c.setFont("Times-Bold", 9)
    c.drawCentredString(177, H_PAGE - 101, "******")
    c.setFont("Times-BoldItalic", 13.5)
    c.drawString(75, H_PAGE - 123, "Direction  de  l'Administration  et  des  Finances")
    c.setFont("Times-Bold", 9)
    c.drawCentredString(177, H_PAGE - 134, "******")
    c.setFont("Times-Bold", 13)
    c.drawCentredString(W / 2, H_PAGE - 159, "FICHE D'EVALUATION DE L'AGENT CONTRACTUEL DE L'ETAT")
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(W / 2, H_PAGE - 172, "Pour ACE ayant la qualité de supérieur hiérarchique immédiat")
    c.setFont("Times-Bold", 11)
    c.drawCentredString(W / 2, H_PAGE - 198, "1- IDENTIFICATION DE L'AGENT")
    x1, x2, pas = 29, 566, 25.3
    y = H_PAGE - 225
    for segs in lignes_identification(v):
        segs = [(("t", s[1].replace("Nom et prénom(s)", "Nom et Prénoms").replace("Tél : ", "Téléphone :")
                  .replace("  E-mail : ", "Email :").replace("Situation Familiale", "Situation de famille"), s[2])
                 if s[0] == "t" else s) for s in segs]
        ligne(c, x1, y, x2, segs, v, fam, size)
        y -= pas
    c.setFont("Times-Bold", 11)
    c.drawCentredString(W / 2, y + 2, "2- SITUATION ADMINISTRATIVE DE L'AGENT")
    y -= 21
    for segs in lignes_admin():
        ligne(c, x1, y, x2, segs, v, fam, size)
        y -= pas
    c.setFont("Helvetica", size)
    c.drawString(x1, y, "Référence des actes de carrière :")
    y -= pas
    for segs in ([T("Contrat initial : "), V("contrat_initial")],
                 [T("Contrat de travail renouvelé : "), V("contrat_renouvele")],
                 [T("Contrat à durée Indéterminée: "), V("contrat_cdi")]):
        ligne(c, x1, y, x2, segs, v, fam, size)
        y -= pas
    y = flux(c, x1, y, x2, 74, "Avenants : ", v.get("avenants", ""), 3, pas, fam, size)
    y += 6
    ligne(c, 190, y, x2, [T("Fait à "), V("fait_a", 1.3), T(", le "), V("fait_le", 1)], v, fam, size)
    c.setFont("Helvetica", size)
    c.drawString(253, y - 26, "Signature de l'agent")
    c.drawString(254, y - 70, "Prénom (s) et Nom")
    nom = v.get("_prenoms_nom") or ""
    if nom:
        c.setFont("Helvetica-Bold", size + 1)
        c.drawCentredString(297, y - 96, nom)
    else:
        pointilles(c, 173, 423, y - 96, "Helvetica", size)


def bandeau_memp(c, y_haut, email, marge_g=36, marge_d=558, hauteur=48, tel="+229 20 21 52 22",
                 fax="+229 20 21 52 22", style="cert"):
    """Bandeau ministère (bloc MEMP à gauche, adresse du ministère à droite)."""
    bloc_memp(c, marge_g, y_haut, hauteur)
    c.setFillColor(colors.HexColor("#222222"))
    if style == "cert":
        lignes = ["01 BP 10 Porto-Novo", f"Tél:{tel}", f"Fax: {fax}", f"E-mail: {email}"]
    else:
        lignes = ["01 BP 10 Porto-Novo", f"Tél. : {tel}", f"Fax : {fax}", f"E-mail : {email}"]
    lignes_droite(c, marge_d, y_haut - hauteur * 0.3, lignes, "Helvetica-Bold", hauteur / 6.2, hauteur / 5.4)
    c.setFillColor(colors.black)


def page1_secondaire(c, v, opt):
    """Nouvelle fiche (MESTFP) — page 1."""
    fam, size = HELV, 11.5
    armoiries(c, 42, H_PAGE - 34, 60)
    c.setFont("Helvetica", 8)
    for i, t in enumerate(("MINISTERE DES ENSEIGNEMENTS", "SECONDAIRE, TECHNIQUE ET DE LA",
                           "FORMATION PROFESSIONNELLE")):
        c.drawString(114, H_PAGE - 42 - i * 10, t)
    barre_drapeau(c, 142, H_PAGE - 73, 161, 2.6)
    c.drawString(117, H_PAGE - 83, "REPUBLIQUE DU BENIN")
    c.setFont("Helvetica", 7.2)
    for i, t in enumerate(("Route de l'aéroport", "10BP 250 Cotonou", "Tél. : (229) 21 32 38 43 ; Fax : 21 32 41 88",
                           "web: www.enseignementsecondaire.gouv.bj")):
        c.drawRightString(502, H_PAGE - 42 - i * 12, t)
    # bloc DDESTFP / établissement
    cx = 156
    c.setFont("Helvetica", 7.4)
    c.drawCentredString(cx, H_PAGE - 122, "DIRECTION DEPARTEMENTALE DES")
    c.drawCentredString(cx, H_PAGE - 131, "ENSEIGNEMENTS SECONDAIRE, TECHNIQUE ET")
    y = flux(c, 48, H_PAGE - 140, 265, 48, "DE LA FORMATION PROFESSIONNELLE DE ", v.get("ddes", ""), 3, 9,
             HELV, 7.4)
    c.setFont("Helvetica", 7)
    c.drawCentredString(cx, y + 1, "-------- & --------")
    c.setFont("Helvetica", 7.4)
    c.drawCentredString(cx, y - 8, "COLLEGE D'ENSEIGNEMENT GENERAL/LYCEE")
    y = flux(c, 55, y - 17, 260, 52, "DE", v.get("etablissement", ""), 2, 9, HELV, 7.4)
    c.setFont("Helvetica", 7)
    c.drawCentredString(cx, y + 1, "-------- & --------")
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(300, H_PAGE - 259, "FICHE D'EVALUATION DE L'AGENT CONTRACTUEL DE L'ETAT")
    c.setFont("Helvetica", 12)
    c.drawCentredString(307, H_PAGE - 276, "(Pour ACE n'ayant pas la qualité de supérieur hiérarchique immédiat)")
    x1, x2, pas = 42, 510, 17.3
    y = H_PAGE - 294
    c.setFont("Helvetica-Bold", size)
    c.drawString(x1, y, "I-Identification de l'agent")
    y -= pas
    for segs in lignes_identification(v, secondaire=True):
        ligne(c, x1, y, x2 if segs[0][1] not in ("Matricule :", "Adresse :") else 245, segs, v, fam, size)
        y -= pas
    c.setFont("Helvetica-Bold", size)
    c.drawString(x1, y, "2-Situation administrative de l'agent")
    y -= pas
    for segs in lignes_admin(secondaire=True):
        ligne(c, x1, y, x2 if segs[0][1] != "Emploi :" else 210, segs, v, fam, size)
        y -= pas
    c.setFont("Helvetica", size)
    c.drawString(x1, y, "Référence des actes de carrière :")
    y -= pas
    ligne(c, x1, y, x2, [T("Contrat initial :"), V("contrat_initial")], v, fam, size)
    y -= 38
    ligne(c, 219, y, 560, [T("Fait à "), V("fait_a", 1), T(", le "), V("fait_le", 1.4)], v, fam, size)
    signature_agent(c, v, 184, y - 36, y - 104, fam, size, "l")
    barre_drapeau(c, 199, 20, 198, 4.5)


def dessiner_eval(c, doc, v, opt):
    {"eval_ace": page1_ace, "eval_directeur": page1_directeur, "eval_secondaire": page1_secondaire}[doc](c, v, opt)
    c.showPage()
    page_evaluation(c, doc, v, opt)
    if doc == "eval_secondaire":
        barre_drapeau(c, 199, 20, 198, 4.5)
    c.showPage()


# ================================================================================================ PDF : certificats du personnel
EN_FOI = "En foi, de quoi la présente Attestation lui est délivrée pour servir et valoir ce que de droit."

# Chaque certificat : cadre du titre, signataires, interligne, lignes du corps.
# Une ligne = liste de segments, ou ("centre", segments), ou ("vierge", segments) (ligne de réserve, PDF vierge).
LIGNE_CS = ("centre", [T("Circonscription Scolaire de "), S("cs", 60), T(", département du "),
                       S("departement", 60)])
ACTE = [[T("Suivant l'arrêté /décision /Note de Service N°"), V("acte")],
        [V("_acte_suite", 1), T("du"), D("acte_date", 0.42)]]
INTRO_CCS = [("centre", [T("Je soussigné "), S("ccs_nom", 150, "bi")]),
             ("centre", [T("Chef de la Circonscription Scolaire de "), S("cs", 70, "n")])]
# Ligne du NIP (Numéro d'Identification Personnel), toujours placée avant la ligne du nom.
LIGNE_NIP = [T("NIP (Numéro d'Identification Personnel) : "), V("nip")]

CERTIFICATS = {
    "presence_poste_dir": dict(
        titre="CERTIFICAT DE PRESENCE AU POSTE", cadre="double", pas=29, sig=("ccs", "dir"),
        corps=[[T("Je soussigné (e) "), V("soussigne")],
               [T("Direct"), S("_suf_dir", 32, "n"), T(" de l'Ecole Primaire "), V("ecole", 1), T(" de :")],
               [V("localite")], LIGNE_NIP,
               [T("Atteste que "), C("civilite", "Mr ou Mme", "b"), T(" "), V("nom_prenoms")],
               [C("_ne", "Né (e)"), T(" le "), D("date_naissance", 0.55), T(" à "), V("lieu_naissance", 0.45)],
               [T("Première prise de service "), V("date_prise_service")],
               [T("Numéro matricule "), V("matricule")],
               [T("Corps et Grade payé "), V("corps_grade")],
               [T("Est en service à "), V("en_service_a")],
               LIGNE_CS,
               [T("Suivant : "), V("suivant")],
               [T("En qualité de (Fonction) "), V("fonction")],
               [T("Depuis le "), D("depuis", 0.8), T(" jusqu'à ce jour "), D("jusqu_au", 1)]]),
    "presence_poste_ccs": dict(
        titre="CERTIFICAT DE PRESENCE AU POSTE", cadre="arrondi", pas=26, sig=("ccs",),
        corps=INTRO_CCS + [LIGNE_NIP, ("centre", [T("Certifie que "), C("civilite", "Mr ou Mme", "b")]),
                           ("petit", [V("nom_prenoms")]),
                           [C("_ne", "Né (e)"), T(" le "), D("date_naissance", 0.6), T(" à "),
                            V("lieu_naissance", 0.4)],
                           [T("Première prise de service "), V("date_prise_service")],
                           [T("Numéro matricule "), V("matricule")],
                           [T("Corps et Grade payé "), V("corps_grade")],
                           [T("Est en service à "), V("en_service_a")]] + ACTE + [
            LIGNE_CS,
            [T("En qualité de (Fonction) "), V("fonction")],
            [T("Depuis le "), D("depuis", 0.8), T(" jusqu'à ce jour "), D("jusqu_au", 1)]]),
    "attestation_direction": dict(
        titre="ATTESTATION DE DIRECTION", cadre="epais", pas=19.5, sig=("ccs",),
        corps=INTRO_CCS + [LIGNE_NIP, ("centre", [T("Atteste que "), C("civilite", "Mr ou Mme")]),
                           [V("nom_prenoms")],
                           [T("Grade :"), V("grade", 1), T("Matricule"), V("matricule", 1.2)],
                           [C("_affecte", "Affecté (e)"), T(" à "), V("affecte_a")],
                           [T("Du"), V("du_lieu")],
                           [T("Est effectivement Direct"), S("_suf_agent", 32, "n"), T(" de EM/EP "),
                            V("direction_de")],
                           [T("Depuis le :"), V("depuis")],
                           [T("Et demeurant réellement Direct"), S("_suf_agent", 32, "n"), T(" de "),
                            V("nb_classes", 1), T("classe (s)")],
                           [T("Pour compter du "), V("pour_compter")]] + ACTE + [
            [T("En remplacement de "), C("_remplace_civ", "Mr ou Mme"), V("remplace_nom")],
            [T("Matricule "), V("remplace_matricule")],
            [T("Motif "), V("motif")]]),
    "certificat_travail": dict(
        titre="CERTIFICAT DE TRAVAIL", cadre="epais", pas=24, sig=("ccs",),
        corps=INTRO_CCS + [LIGNE_NIP, ("centre", [T("Certifie que "), C("civilite", "Mr ou Mme"), T(" "),
                                                  S("nom_prenoms", 180)]),
                           ("vierge", ("centre", [S("_rien", 130)])),
                           [T("Grade : "), V("grade", 1), T(" Matricule"), V("matricule", 0.9)],
                           [T("Est en service à l'école "), V("en_service_a")]] + ACTE + [
            [T("en qualité d" + "e "), V("fonction")],
            [T("Depuis le "), D("depuis", 0.8), T("jusqu'à ce jour "), D("jusqu_au", 0.8)]]),
    "prise_service_ccs": dict(
        titre="CERTIFICAT DE PRISE DE SERVICE", cadre="epais", pas=22.5, sig=("ccs",),
        corps=INTRO_CCS + [LIGNE_NIP, ("centre", [T("Certifie que "), C("civilite", "Mr ou Mme", "b")]),
                           [V("nom_prenoms")],
                           [T("Grade : "), V("grade", 1), T("Matricule"), V("matricule", 1)],
                           [C("_affecte", "Affecté(e)"), T(" à l'Ecole Primaire "), V("affecte_a")],
                           [T("En remplacement de "), V("remplace_nom")]] + ACTE + [
            [T("en qualité de :"), V("fonction", 1), T("de"), V("nb_classes", 0.22), T("classe(s)")],
            [T("a effectivement pris service le "), D("date_effective")],
            ("retrait", [T("Motif :"), V("motif")])]),
    "prise_service_dir": dict(
        titre="CERTIFICAT DE PRISE DE SERVICE", cadre="epais", pas=27.5, sig=("dir",),
        corps=[[T("Je soussigné (e)"), V("soussigne")],
               [T("Direct"), S("_suf_dir", 32, "n"), T(" de l'Ecole Primaire"), V("ecole", 1), T(" de :"),
                V("localite", 0.6)], LIGNE_NIP,
               [T("Certifie que "), C("civilite", "Mr ou Mme"), T(" "), V("nom_prenoms")],
               [T("Grade :"), V("grade", 1), T("Matricule :"), V("matricule", 1)],
               [C("_affecte", "Affecté(e)"), T(" à l'école "), V("affecte_a")]] + ACTE + [
            [T("en qualité de :"), V("fonction")],
            [T("a effectivement pris service le"), D("date_effective")]]),
    "prise_en_charge": dict(
        titre="CERTIFICAT DE PRISE EN CHARGE", cadre="aucun", pas=24.5, sig=("ccs",),
        corps=[LIGNE_NIP,
               [T("Nom et Prénoms du malade : "), V("nom_prenoms")],
               ("vierge", [V("_rien")]),
               [T("Profession :"), V("profession")],
               [T("En service à "), V("en_service_a")],
               [T("Indice de traitement :"), V("indice")],
               [T("Budget devant supporter l'hospitalisation :"), V("budget")],
               [T("Catégorie d'hospitalisation :"), V("categorie_hosp")]]),
}


def cadre_titre(c, titre, style, y_haut, x1=108, x2=497, hauteur=44, size=16):
    """Cadre du titre (double trait, arrondi, trait épais)."""
    c.saveState()
    c.setStrokeColor(colors.black)
    if style == "double":
        c.setLineWidth(2.2)
        c.rect(x1, y_haut - hauteur, x2 - x1, hauteur)
        c.setLineWidth(0.8)
        c.rect(x1 + 5, y_haut - hauteur + 5, x2 - x1 - 10, hauteur - 10)
    elif style == "arrondi":
        c.setLineWidth(1)
        c.roundRect(x1, y_haut - hauteur, x2 - x1, hauteur, 8)
    elif style == "epais":
        c.setLineWidth(5)
        c.rect(x1 + 2.5, y_haut - hauteur + 2.5, x2 - x1 - 5, hauteur - 5)
        c.setLineWidth(0.8)
        c.rect(x1 + 7, y_haut - hauteur + 7, x2 - x1 - 14, hauteur - 14)
    c.restoreState()
    c.setFont("Times-Bold", size)
    c.drawCentredString((x1 + x2) / 2, y_haut - hauteur / 2 - size * 0.33, titre)


def dessiner_certificat_agent(c, doc, v, opt):
    spec = CERTIFICATS[doc]
    fam, size = TIMES, 13.5
    x1, x2 = 36, 558
    vierge = opt.get("vierge")
    barre_drapeau(c, 195, H_PAGE - 22, 204, 6, "moitie")
    bandeau_memp(c, H_PAGE - 33, "mempmatprim@gmail.com", marge_g=40, marge_d=556, hauteur=50)
    if doc == "prise_en_charge":
        cx = 164
        c.setFont("Times-Bold", 10)
        dep = (v.get("departement") or "").upper()
        c.drawCentredString(cx, H_PAGE - 105, "DIRECTION DEPARTEMENTALE DES")
        c.drawCentredString(cx, H_PAGE - 116, "ENSEIGNEMENTS MATERNEL ET")
        if dep:
            c.drawCentredString(cx, H_PAGE - 127, f"PRIMAIRE DU {dep}"[:48])
        else:
            c.drawString(cx - 70, H_PAGE - 127, "PRIMAIRE DU")
            pointilles(c, cx - 70 + sw(c, "PRIMAIRE DU ", "Times-Bold", 10), cx + 100, H_PAGE - 127, "Times-Roman", 10)
        c.setFont("Times-Roman", 7)
        c.drawCentredString(cx, H_PAGE - 135, "°°°°°°°")
        c.setFont("Times-Bold", 10)
        cs = (v.get("cs") or "").upper()
        if cs:
            c.drawCentredString(cx, H_PAGE - 147, f"CIRCONSCRIPTION SCOLAIRE DE {cs}"[:52])
        else:
            c.drawString(cx - 100, H_PAGE - 147, "CIRCONSCRIPTION SCOLAIRE DE")
            pointilles(c, cx + 60, cx + 110, H_PAGE - 147, "Times-Roman", 10)
        c.setFont("Times-Roman", 7)
        c.drawCentredString(cx, H_PAGE - 155, "°°°°°°°")
        ref = v.get("ref") or ""
        c.setFont("Times-Bold", 10)
        if ref:
            texte_ajuste(c, cx - 110, H_PAGE - 168, 235, ref, "Times-Bold", 10)
        else:
            c.drawString(cx - 100, H_PAGE - 168, "S0N°")
            pointilles(c, cx - 76, cx + 10, H_PAGE - 168, "Times-Roman", 7)
            c.drawString(cx + 11, H_PAGE - 168, "/CS-")
            pointilles(c, cx + 34, cx + 70, H_PAGE - 168, "Times-Roman", 7)
            c.drawString(cx + 71, H_PAGE - 168, "/DDEMP-")
            pointilles(c, cx + 112, cx + 130, H_PAGE - 168, "Times-Roman", 7)
        c.setFont("Times-Roman", 18)
        c.drawCentredString(W / 2, H_PAGE - 224, spec["titre"])
        c.setFont("Times-Italic", 9)
        c.drawCentredString(W / 2, H_PAGE - 240, "Admission des fonctionnaires et assimilés")
        y = H_PAGE - 262
    else:
        ref = v.get("ref") or ""
        if ref:
            texte_ajuste(c, x1, H_PAGE - 105, x2 - x1, ref, "Times-Roman", 9)
        else:
            ligne(c, x1, H_PAGE - 105, 520, [T("SO N°"), V("_x", 0.2)] + (
                [T("EPP/EM"), V("_x", 1)] if doc in ("presence_poste_dir", "prise_service_dir") else []) + [
                T("/CS-"), V("_x", 0.3), T("/DDEMP-"), V("_x", 0.15), T("/SP")], {}, fam, 9)
        haut = {"double": 126, "arrondi": 124, "epais": 126}[spec["cadre"]]
        larg = {"double": (87, 514), "arrondi": (103, 526), "epais": (108, 497)}[spec["cadre"]]
        cadre_titre(c, spec["titre"], spec["cadre"], H_PAGE - haut, *larg,
                    hauteur=46 if spec["cadre"] != "arrondi" else 40, size=16)
        y = H_PAGE - (208 if spec["cadre"] != "arrondi" else 185)
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
    # interligne réduit si nécessaire pour garder la place de la formule, des signatures (griffe) et du QR
    bas = 268 if len(spec["sig"]) else 240
    pas = min(spec["pas"], (y - bas) / max(1, len(lignes)))
    for mode, segs in lignes:
        if mode == "centre":
            ligne(c, x1, y, x2, segs, v, fam, size, align="c")
        elif mode == "petit":
            ligne(c, x1 + 30, y, x2 - 30, segs, v, fam, size)
        elif mode == "retrait":
            ligne(c, x1 + 72, y, x2 - 10, segs, v, fam, size)
        else:
            ligne(c, x1, y, x2, segs, v, fam, size)
        y -= pas
    # En foi de quoi…
    y += pas - 26
    if doc == "prise_en_charge":  # pas de formule « En foi de quoi » sur ce modèle
        y -= 16
    p = None if doc == "prise_en_charge" else Paragraph(f"<para firstLineIndent='28'>{EN_FOI}</para>",
                  ParagraphStyle("foi", fontName="Times-BoldItalic", fontSize=12, leading=15))
    if p is not None:
        _, h = p.wrap(x2 - x1 - 10, 60)
        p.drawOn(c, x1, y - h + 12)
        y -= h + 10
    fait_segs = [T("Fait à "), S("fait_a", 90), T(", le "), S("fait_le", 120)]
    if doc == "prise_en_charge":
        ligne(c, 230, y, x2, fait_segs, v, fam, size, align="r")
    else:
        ligne(c, 150 if len(spec["sig"]) == 1 else 190, y, x2, fait_segs, v,
              {"n": "Times-Bold", "b": "Times-Bold", "i": "Times-Italic", "bi": "Times-BoldItalic"}, 13, align="r")
    y -= 26
    signer = opt.get("signer") and not vierge
    if spec["sig"] == ("ccs", "dir"):
        sig_ccs(c, v, 170, y, opt, signer, style="b")
        sig_dir(c, v, 468, y, opt, signer)
    elif spec["sig"] == ("dir",):
        sig_dir(c, v, 470, y - 18, opt, signer)
    else:
        sig_ccs(c, v, 420, y, opt, signer, style="bi" if doc == "presence_poste_ccs" else "b",
                size=15 if doc == "presence_poste_ccs" else 13.5)
    if opt.get("code"):
        pdfs._qr(c, opt["code"], 36, 44, 46)
    barre_drapeau(c, 108, 30, 378, 6, "moitie")
    c.showPage()


def sig_ccs(c, v, cx, y, opt, signer, style="b", size=13.5):
    """Signature du CCS : titre, signature numérique, nom — ou griffe (opt["griffe_ccs"] = (lignes, couleur),
    connue dans les applications CS / DDEMP) à la place du nom quand le document est signé."""
    img = image_sig(opt.get("sig_ccs")) if signer else None
    c.setFont(TIMES[style], size)
    c.drawCentredString(cx, y, "Le Chef de la Circonscription Scolaire")
    if img is not None:
        c.drawImage(img, cx - 60, y - 70, 120, 55, preserveAspectRatio=True, mask="auto")
    nom = v.get("ccs_nom") or ""
    c.setFont("Times-Bold", 13.5)
    if nom and signer and opt.get("griffe_ccs"):
        griffe_dir(c, cx + 10, y - 92, 150, opt["griffe_ccs"])
    elif nom:
        c.drawCentredString(cx, y - 88, nom)
    else:
        pointilles(c, cx - 80, cx + 80, y - 88, "Times-Roman", 13.5)


def sig_dir(c, v, cx, y, opt, signer):
    """Signature du directeur : titre, cachet rond + signature numérique, puis griffe (si active) ou nom."""
    titre = titre_dir(v.get("directeur_titre"))
    c.setFont("Times-BoldItalic", 13.5)
    if titre:
        c.drawCentredString(cx, y, titre)
    else:
        c.drawCentredString(cx, y, "L…… Direct………")
    griffe = None
    if signer:
        pdfs.cachet_ecole(c, cx - 25, y - 45, 28)
        img = pdfs.signature_directeur()
        if img is not None:
            c.drawImage(img, cx - 60, y - 72, 120, 55, preserveAspectRatio=True, mask="auto")
        griffe = opt.get("griffe_dir") or config.ECOLE.get("_griffe")
    nom = v.get("directeur_nom") or v.get("soussigne") or ""
    c.setFont("Times-Bold", 13.5)
    if nom and griffe:
        griffe_dir(c, cx + 10, y - 92, 150, griffe)
    elif nom:
        c.drawCentredString(cx, y - 88, nom)
    else:
        pointilles(c, cx - 55, cx + 55, y - 88, "Times-Roman", 13.5)


# ================================================================================================ PDF : certificat de scolarité
def dessiner_certificat_scolarite(c, v, opt):
    """Certificat de scolarité (format 2023). Modèle 522 x 756 pt, agrandi ×1,1 et centré sur A4."""
    vierge = opt.get("vierge")
    c.saveState()
    c.translate(10.4, 5.2)
    c.scale(1.1, 1.1)
    HM = 756

    def Y(px):  # ordonnée depuis le haut du modèle rendu à 100 dpi
        return HM - px * 0.72

    def X(px):
        return px * 0.72

    fam, size = HELV, 11
    x1, x2 = X(124), X(594)
    bloc_memp(c, X(122), Y(104), 54)
    c.setFont("Helvetica-Bold", 10)
    for i, t in enumerate(("01 BP 10 Porto-Novo", "Tél : + 229 20 21 52 22", "Fax : +229 20 21 52 22",
                           "Email : memp.info@gouv.bj")):
        c.drawRightString(X(592), Y(120 + i * 18.7), t)
    # école (gauche) et titre tricolore (droite)
    ligne(c, x1, Y(214), X(357), [T("ECOLE ", "b"), V("ecole_l1")], v, HELV, 11)
    ligne(c, x1, Y(254), X(357), [V("ecole_l2")], v, HELV, 11)
    ligne(c, x1, Y(294), X(357), [T("DE ", "b"), V("ecole_de")], v, HELV, 11)
    c.setFont("Helvetica-Bold", 14)
    for txt, col, py in (("CERTIFICAT", "#00B050", 214), ("DE", "#FFD500", 254), ("SCOLARITE", "#FF0000", 294)):
        c.setFillColor(colors.HexColor(col))
        c.drawCentredString(X(527), Y(py), txt)
    c.setFillColor(colors.black)
    pas = 19.4 * 0.72
    y = Y(355)
    # « L… Direct… de l'Ecole … » sur trois lignes
    c.setFont("Helvetica", size)
    titre = titre_dir(v.get("directeur_titre"))
    if titre:
        debut = f"{titre} de l'Ecole "
    else:
        debut = "L ……Direct …… de l'Ecole "
    y = flux(c, x1, y, x2, x1, debut, v.get("ecole_designation", ""), 3, pas, fam, size)
    ligne(c, x1, y, x2, [T("NIP : "), V("nip")], v, fam, size)
    y -= pas
    y = flux(c, x1, y, x2, x1, "Atteste que l'Elève : ", v.get("nom_prenoms", ""), 2, pas, fam, size)
    ligne(c, x1, y, x2, [C("_ne", "Né (e)"), T(" à "), V("lieu_naissance", 1.35), T(" le "),
                         V("date_naissance", 1)], v, fam, size)
    y -= pas
    ligne(c, x1, y, x2, [C("_inscrit", "Inscrit (e)"), T(" sous le N° Matricule "), V("matricule")], v, fam, size)
    y -= pas
    ligne(c, x1, y, x2, [T("a fréquenté l'Ecole du "), V("frequente_du", 1), T(" au "), V("frequente_au", 1)],
          v, fam, size)
    y -= pas
    ligne(c, x1, y, x2, [T("Elève du cours "), V("cours")], v, fam, size)
    y -= pas
    ligne(c, x1, y, x2, [T("depuis le  "), V("depuis")], v, fam, size)
    y -= pas
    ligne(c, x1, y, x2, [C("_il", "Il (elle)"), T(" mérite les notes suivantes : "), V("_rien")], v, fam, size)
    y = Y(586)
    for lib, cle in (("ASSIDUITE", "assiduite"), ("CONDUITE", "conduite"), ("TRAVAIL", "travail")):
        ligne(c, X(228), y, X(590), [T(lib + " ", "b"), V(cle)], v, fam, size)
        y -= 19.6 * 0.72
    c.setFont("Helvetica-Bold", 13)
    t = "OBSERVATIONS PARTICULIERES"
    c.drawCentredString(X(362), Y(666), t)
    c.setLineWidth(0.9)
    c.line(X(362) - sw(c, t, "Helvetica-Bold", 13) / 2, Y(669), X(362) + sw(c, t, "Helvetica-Bold", 13) / 2, Y(669))
    flux(c, x1, Y(686), x2, x1, "", v.get("observations", ""), 4, pas, fam, size, style_val="n")
    ligne(c, X(215), Y(780), X(594), [S("fait_a", 115, "n"), T(" le "), D("fait_le", 1)], v, fam, size)
    titre_sig = (titre or "Direct .…….…") + " de l'Ecole"
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(X(600), Y(837), titre_sig)
    cx = X(600) - sw(c, titre_sig, "Helvetica-Bold", 11) / 2
    griffe = None
    if opt.get("signer") and not vierge:
        pdfs.cachet_ecole(c, cx - 22, Y(837) - 40, 26)
        img = pdfs.signature_directeur()
        if img is not None:
            c.drawImage(img, cx - 50, Y(837) - 68, 100, 50, preserveAspectRatio=True, mask="auto")
        griffe = config.ECOLE.get("_griffe")
    if v.get("directeur_nom") and griffe:
        griffe_dir(c, cx + 8, Y(837) - 86, 120, griffe)
    elif v.get("directeur_nom"):
        c.setFont("Helvetica-Bold", 10.5)
        c.drawCentredString(cx, Y(837) - 82, v["directeur_nom"])
    c.restoreState()
    if opt.get("code"):
        pdfs._qr(c, opt["code"], 40, 40, 20 * 2.83)
    c.showPage()


# ================================================================================================ PDF : assemblage
def preparer(doc, v):
    """Valeurs dérivées (accords, libellés composés) à partir des valeurs saisies."""
    v = {k: ("" if val is None else str(val)) for k, val in (v or {}).items()}
    civ = v.get("civilite", "")
    sexe = v.get("sexe", "") or ("F" if civ.lower().startswith("mme") or civ.lower().startswith("mlle") else
                                 "M" if civ.lower().startswith("m") else "")
    if sexe:
        v["_ne"] = "Née" if sexe == "F" else "Né"
        v["_inscrit"] = "Inscrite" if sexe == "F" else "Inscrit"
        v["_il"] = "Elle" if sexe == "F" else "Il"
        v["_affecte"] = "Affectée" if sexe == "F" else "Affecté"
        v["_suf_agent"] = "rice" if sexe == "F" else "eur"
    v["_suf_dir"] = suffixe_dir(v.get("directeur_titre"))
    lieu, dn = v.get("lieu_naissance", ""), v.get("date_naissance", "")
    v["_lieu_date"] = f"{lieu}, le {dn}" if lieu and dn else (lieu or dn)
    if v.get("remplace_nom"):
        v["_remplace_civ"] = " "
    nom = v.get("_nom", "")
    v["_prenoms_nom"] = v.get("_prenoms_nom") or nom
    return v


def construire_pdf(doc, lots, titre):
    """lots = [(valeurs, options)] -> bytes PDF (une ou plusieurs personnes)."""
    import io
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A4)
    c.setTitle(titre)
    c.setAuthor("GESCOL")
    for v, opt in lots:
        v = preparer(doc, v)
        fam = DOCS[doc]["famille"]
        if fam == "eval":
            dessiner_eval(c, doc, v, opt)
        elif doc == "certificat_scolarite":
            dessiner_certificat_scolarite(c, v, opt)
        else:
            dessiner_certificat_agent(c, doc, v, opt)
    c.save()
    return buf.getvalue()


# ================================================================================================ module Flask
def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config

    H.schema("""
    CREATE TABLE IF NOT EXISTS docs_enseignant_historique (
        id INTEGER PRIMARY KEY,
        ecole_id INTEGER NOT NULL,
        type TEXT NOT NULL,               -- clé du document (DOCS)
        cible TEXT NOT NULL,              -- agent | eleve
        cible_id INTEGER,                 -- personnel.id ou eleves.id (NULL pour un document groupé)
        libelle TEXT NOT NULL,
        nombre INTEGER NOT NULL DEFAULT 1,
        codes TEXT,                       -- codes de vérification (QR), séparés par des virgules
        donnees TEXT NOT NULL,            -- JSON : liste des valeurs imprimées (réimpression à l'identique)
        signe INTEGER NOT NULL DEFAULT 0,
        annee TEXT,
        cree_le TEXT NOT NULL,
        cree_par INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_docens_hist ON docs_enseignant_historique(ecole_id, type, cree_le);
    """)

    # Libellés des documents vérifiables (page /verifier) : ajout au dictionnaire existant de l'application.
    try:
        import sys
        for nom_mod in ("app", "__main__"):
            td = getattr(sys.modules.get(nom_mod), "TYPES_DOCS", None)
            if isinstance(td, dict):
                for k, d in DOCS.items():
                    if d["qr"]:
                        td.setdefault(f"docens_{k}", d["titre"])
    except Exception:  # noqa: BLE001 — simple confort d'affichage
        pass

    # ------------------------------------------------------------------ utilitaires base
    def colonnes(table):
        try:
            return {r["name"] for r in q(f"PRAGMA table_info({table})")}
        except Exception:  # noqa: BLE001
            return set()

    def table_existe(nom):
        return bool(q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nom,), un=True))

    def role():
        return "admin" if g.user["role"] == "fondateur" else g.user["role"]

    def peut_signer():
        """Cachet et signature du directeur : direction et secrétariat uniquement (pas l'enseignant)."""
        return role() in ("admin", "directeur", "secretaire")

    def norm(t):
        return H.xlsx.normaliser(t)

    # ------------------------------------------------------------------ personnes autorisées
    def mes_agents_ids():
        """Fiches de personnel de l'enseignant connecté (lien personnel.user_id, sinon même nom)."""
        ids = set()
        if "user_id" in colonnes("personnel"):
            ids |= {r["id"] for r in q("SELECT id FROM personnel WHERE user_id=?", (g.user["id"],))}
        nom_u = norm(g.user["nom"])
        if nom_u:
            for r in q("SELECT id, nom, prenoms FROM personnel WHERE ecole_id=?", (H.eco(),)):
                if nom_u in (norm(f"{r['nom']} {r['prenoms']}"), norm(f"{r['prenoms']} {r['nom']}")):
                    ids.add(r["id"])
        return ids

    def agents_autorises(actifs=True):
        rows = q("SELECT * FROM personnel WHERE ecole_id=?" + (" AND actif=1" if actifs else "") +
                 " ORDER BY nom, prenoms", (H.eco(),))
        if role() == "enseignant":
            mes = mes_agents_ids()
            rows = [r for r in rows if r["id"] in mes]
        return rows

    def agent_ou_403(pid):
        a = q("SELECT * FROM personnel WHERE id=? AND ecole_id=?", (pid, H.eco()), un=True)
        if not a:
            abort(404)
        if role() == "enseignant" and pid not in mes_agents_ids():
            abort(403)
        return a

    def eleve_autorise(eid):
        e = H.eleve_ou_404(eid)
        if e["classe_id"] not in {c["id"] for c in H.classes_autorisees()}:
            abort(403)
        return e

    # ------------------------------------------------------------------ données automatiques
    def ecole_auto():
        ident = H.identification()
        e = g.ecole
        return dict(
            ecole=ident["ecole"] or "", cs=ident["cs"] or "", departement=ident["departement"] or "",
            commune=ident["commune"] or "", ville=((e["ville"] if e else "") or ident["commune"] or ""),
            directeur_nom=ident["directeur_nom"] or "", directeur_titre=ident["directeur_titre"] or "Directeur",
            ccs_nom=ident["ccs_nom"] or "", annee=ident["annee"])

    def carriere(pid):
        if not table_existe("personnel_carriere"):
            return {}
        try:
            r = q("SELECT * FROM personnel_carriere WHERE personnel_id=?", (pid,), un=True)
        except Exception:  # noqa: BLE001
            return {}
        return dict(r) if r else {}

    def classes_de_agent(a):
        """Classes tenues par l'agent : affectations de son compte, sinon titulaire de la classe."""
        noms = []
        if "user_id" in a.keys() and a["user_id"]:
            noms = [r["nom"] for r in q("""SELECT DISTINCT c.nom FROM affectations f JOIN classes c ON c.id=f.classe_id
                                           WHERE f.user_id=? AND c.ecole_id=? ORDER BY c.nom""",
                                        (a["user_id"], H.eco()))]
        if not noms:
            cible = {norm(f"{a['nom']} {a['prenoms']}"), norm(f"{a['prenoms']} {a['nom']}")}
            noms = [c["nom"] for c in q("SELECT nom, titulaire_nom FROM classes WHERE ecole_id=? ORDER BY nom",
                                        (H.eco(),)) if c["titulaire_nom"] and norm(c["titulaire_nom"]) in cible]
        return noms

    def agent_auto(a):
        """Toutes les valeurs connues de GESCOL pour un agent (personnel + carrière)."""
        a = dict(a)
        car = carriere(a["id"])

        def pick(*noms):
            for n in noms:
                for src in (car, a):
                    val = src.get(n)
                    if val not in (None, ""):
                        s = str(val).strip()
                        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
                            s = date_fr(s)
                        return s
            return ""

        sexe = (pick("sexe") or "").upper()[:1]
        nom_prenoms = f"{a['nom']} {a['prenoms']}".strip()
        corps, grade = pick("corps", "statut_agent", "corps_statut"), pick("grade", "grade_actuel")
        d = dict(
            nom_prenoms=nom_prenoms, _prenoms_nom=f"{a['prenoms']} {a['nom']}".strip(),
            civilite="Mme" if sexe == "F" else ("M." if sexe == "M" else ""), sexe=sexe,
            lieu_naissance=pick("lieu_naissance"), date_naissance=pick("date_naissance"),
            telephone=pick("telephone", "tel"), email=pick("email"),
            situation_famille=pick("situation_familiale", "situation_famille", "situation_matrimoniale",
                                   "etat_civil"),
            situation_militaire=pick("situation_militaire"),
            diplome_recrutement=pick("diplome_recrutement", "diplome_professionnel", "diplome", "diplomes",
                                     "diplome_academique"),
            nip=pick("nip", "npi"),
            classe_recrutement=pick("classe_recrutement"),
            matricule=pick("matricule_etat", "matricule_fonction_publique", "matricule"),
            adresse=pick("adresse", "domicile", "residence"),
            date_prise_service=pick("date_premiere_prise_service", "date_prise_service", "premiere_prise_service",
                                    "date_ps", "date_recrutement", "date_embauche"),
            grade=grade, categorie=pick("categorie"), echelle=pick("echelle"), echelon=pick("echelon"),
            indice=pick("indice_paye", "indice", "indice_actuel", "indice_traitement", "indice_reel"),
            emploi=pick("emploi", "fonction"), fonction=pick("fonction", "emploi"),
            corps_grade=" – ".join(x for x in (corps, grade) if x),
            contrat_initial=pick("contrat_initial", "ref_contrat_initial", "acte_recrutement",
                                 "reference_recrutement"),
            contrat_renouvele=pick("contrat_renouvele", "ref_contrat_renouvele"),
            contrat_cdi=pick("contrat_cdi", "contrat_duree_indeterminee", "ref_cdi"),
            avenants=pick("avenants", "avenant"),
            acte=pick("acte_affectation", "ref_affectation", "reference_affectation", "note_affectation",
                      "arrete_affectation"),
            acte_date=pick("date_acte_affectation", "date_acte"),
            _prise_ecole=pick("date_service_ecole", "date_prise_service_ecole", "date_prise_service_poste", "date_affectation",
                              "date_arrivee", "date_prise_service", "date_embauche"),
        )
        d["_classes"] = ", ".join(classes_de_agent(a))
        d["_carriere"] = car
        # éléments pour « 3.2 Résultats de la période »
        res = []
        if d["_classes"]:
            res.append(f"Classe(s) tenue(s) : {d['_classes']}")
        # dossier de carrière (module « Gestion de carrière ») : visites, UP, note d'évaluation
        va = pick("visite_aptitude")
        if va:
            note_va = pick("visite_aptitude_note")
            res.append(f"Visite d'aptitude : {va}" + (f" (note : {note_va.replace('.', ',')}/20)" if note_va else ""))
        for lib, noms in (("Nombre de visites du CP", ("visites_cp", "visite_cp")),
                          ("Nombre de visites du CCS", ("visites_ccs", "visite_ccs")),
                          ("Participation aux unités pédagogiques (UP)", ("participation_up",)),
                          ("Note d'évaluation précédente", ("note_evaluation",))):
            val = pick(*noms)
            if val:
                if noms[0] == "participation_up":
                    val = val.replace(".0", "").replace(".", ",") + " %"
                elif noms[0] == "note_evaluation":
                    val = val.replace(".", ",") + "/20"
                res.append(f"{lib} : {val}")
        dipl = [x for x in (pick("cap") and "CAP " + pick("cap_annee"), pick("ceap") and "CEAP " + pick("ceap_annee"))
                if x and pick("cap" if x.startswith("CAP") else "ceap").lower() not in ("non",)]
        if dipl:
            d["_diplomes_pro"] = ", ".join(x.strip() for x in dipl)
        res += resultats_classes(a)
        d["resultats"] = "\n".join(res)
        return d

    def resultats_classes(a):
        """Taux de maîtrise / de réussite des classes tenues à la dernière évaluation (moteur partagé)."""
        lignes = []
        try:
            import evaluations_core as EC
        except Exception:  # noqa: BLE001
            return lignes
        noms = set(classes_de_agent(a))
        for cl in q("SELECT id, nom FROM classes WHERE ecole_id=? ORDER BY nom", (H.eco(),)):
            if cl["nom"] not in noms:
                continue
            try:
                classe = H.classe_ou_404(cl["id"])
                evs = EC.evaluations_classe(cl["id"], config.ANNEE_ACTIVE)
                if not evs:
                    continue
                ev = evs[-1]
                _m, lignes_res = EC.resultats(ev, classe)
                composes = [r for r in lignes_res if r.get("compose")]
                if not composes:
                    continue
                ok = sum(1 for r in composes if r.get("maitrise"))
                etat = "en situation de maîtrise" if classe["cycle"] == "primaire" else "admis"
                lignes.append(f"{cl['nom']} – {EC.titre(ev)} : {ok}/{len(composes)} élèves {etat} "
                              f"({round(100 * ok / len(composes))} %)")
            except Exception:  # noqa: BLE001 — informations facultatives
                continue
        return lignes

    def absences_annee(eid):
        d1, d2 = H.bornes_annee()
        n, unite = 0, "demi-journée"
        if table_existe("registre"):
            n = q("SELECT COUNT(*) n FROM registre WHERE eleve_id=? AND date BETWEEN ? AND ?", (eid, d1, d2),
                  un=True)["n"]
        if not n:
            n = H.absences_eleve(eid)["absent"]
            unite = "journée"
        return n, unite

    def eleve_auto(e):
        ea = ecole_auto()
        cl = H.classe_de(e)
        d1, d2 = H.bornes_annee()
        sexe = e["sexe"] or ""
        nom = ea["ecole"]
        # « ECOLE … / … / DE … » : nom de l'école sur deux lignes si besoin
        l1, l2 = nom, ""
        if len(nom) > 24 and " " in nom:
            coupe = nom.rfind(" ", 0, 24)
            coupe = coupe if coupe > 0 else nom.find(" ")
            l1, l2 = nom[:coupe], nom[coupe + 1:]
        design = nom
        if ea["cs"]:
            design += f", Circonscription Scolaire de {ea['cs']}"
        if ea["commune"]:
            design += f", Commune de {ea['commune']}"
        insc = e["date_inscription"] or ""
        depuis = insc if insc and d1 <= insc[:10] <= d2 else d1
        niveaux = {"CI": "Cours d'Initiation", "CP": "Cours Préparatoire", "CE1": "Cours Élémentaire 1re année",
                   "CE2": "Cours Élémentaire 2e année", "CM1": "Cours Moyen 1re année",
                   "CM2": "Cours Moyen 2e année"}
        cours = ""
        if cl:
            cours = cl["nom"]
            if cl["niveau"] in niveaux:
                cours = f"{niveaux[cl['niveau']]} ({cl['nom']})"
        n_abs, unite = absences_annee(e["id"])
        if n_abs == 0:
            assid = "Très bonne (aucune absence enregistrée)"
        else:
            appr = "Très bonne" if n_abs <= 4 else "Bonne" if n_abs <= 10 else "Passable" if n_abs <= 20 \
                else "Insuffisante"
            assid = f"{appr} ({n_abs} {unite}{'s' if n_abs > 1 else ''} d'absence)"
        moy = q("SELECT AVG(valeur) m, COUNT(valeur) n FROM notes WHERE eleve_id=? AND annee=? AND valeur IS NOT NULL",
                (e["id"], config.ANNEE_ACTIVE), un=True)
        travail = ""
        if moy and moy["n"]:
            m = moy["m"]
            travail = ("Très bon" if m >= 16 else "Bon" if m >= 14 else "Assez bon" if m >= 12 else "Passable"
                       if m >= 10 else "Insuffisant") + f" (moyenne des notes : {fmt_note(round(m, 2))}/20)"
        return dict(
            ecole_l1=l1, ecole_l2=l2, ecole_de=ea["commune"] or ea["ville"], directeur_titre=ea["directeur_titre"],
            ecole_designation=design, nip=(e["nip"] if "nip" in e.keys() else "") or "",
            nom_prenoms=f"{e['nom']} {e['prenoms']}", sexe=sexe,
            lieu_naissance=e["lieu_naissance"] or "", date_naissance=date_fr(e["date_naissance"]),
            matricule=e["matricule_educmaster"] or e["matricule"] or "",
            frequente_du=date_fr(insc) if insc else "", frequente_au="ce jour" if e["statut"] == "inscrit" else
            aujourdhui(), cours=cours, depuis=date_fr(depuis), assiduite=assid, conduite="", travail=travail,
            observations="", fait_a=ea["ville"], fait_le=aujourdhui(), directeur_nom=ea["directeur_nom"])

    def defauts(doc, cible_id):
        """Valeurs pré-remplies : données GESCOL + valeurs propres au document."""
        ea = ecole_auto()
        if DOCS[doc]["cible"] == "eleve":
            return eleve_auto(eleve_autorise(cible_id))
        a = agent_ou_403(cible_id)
        v = agent_auto(a)
        d1, d2 = H.bornes_annee()
        v.update(fait_a=ea["ville"], fait_le=aujourdhui(), cs=ea["cs"], departement=ea["departement"],
                 ecole=ea["ecole"], ccs_nom=ea["ccs_nom"], directeur_nom=ea["directeur_nom"],
                 directeur_titre=ea["directeur_titre"])
        dep, cs = (ea["departement"] or "").upper(), (ea["cs"] or "").upper()
        if DOCS[doc]["famille"] == "eval":
            v.update(periode_debut=date_fr(d1), periode_fin=date_fr(min(d2, date.today().isoformat())),
                     objectifs="", contraintes="")
            titre_d = titre_dir(ea["directeur_titre"]) or "Le Directeur"
            if doc == "eval_ace":
                v.update(sup_titre=f"{titre_d} de l'école", sup_nom=ea["directeur_nom"],
                         resp_titre="Le Chef de la Circonscription Scolaire", resp_nom=ea["ccs_nom"])
            elif doc == "eval_directeur":
                v.update(sup_titre="Le Chef de la Circonscription Scolaire", sup_nom=ea["ccs_nom"],
                         resp_titre="Le Directeur Départemental des Enseignements Maternel et Primaire",
                         resp_nom="")
            else:
                v.update(sup_titre="Le supérieur hiérarchique", sup_nom="", resp_titre="Le Chef d'établissement",
                         resp_nom=ea["directeur_nom"], ddes=ea["departement"].upper(), etablissement=ea["ecole"])
            return v
        # certificats du personnel
        prise_ecole = v.pop("_prise_ecole", "")
        nb_classes = q("SELECT COUNT(*) n FROM classes WHERE ecole_id=?", (H.eco(),), un=True)["n"]
        par_dir = doc in ("presence_poste_dir", "prise_service_dir")
        ref = (f"SO N° ……/{ea['ecole']}/CS-{cs}/DDEMP-{dep}/SP" if par_dir
               else f"SO N° ……/CS-{cs}/DDEMP-{dep}/SP")
        if doc == "prise_en_charge":
            ref = f"S0N° ……/CS-{cs}/DDEMP-{dep}"
        acte_txt = v.get("acte", "")
        v.update(ref=ref, soussigne=ea["directeur_nom"], localite=ea["commune"] or ea["ville"],
                 en_service_a=ea["ecole"], affecte_a=ea["ecole"], direction_de=ea["ecole"],
                 du_lieu=prise_ecole,
                 suivant=(f"Arrêté / décision / note de service N° {acte_txt}" + (
                     f" du {v['acte_date']}" if v.get("acte_date") else "")) if acte_txt else "",
                 depuis=prise_ecole, jusqu_au=aujourdhui(), pour_compter=prise_ecole, date_effective=prise_ecole,
                 nb_classes=str(nb_classes or ""), profession=v.get("emploi") or v.get("fonction", ""),
                 remplace_nom="", remplace_matricule="", motif="", budget="", categorie_hosp="")
        return v

    def cle_saisie(doc, cible_id):
        return f"e{H.eco()}:docs_enseignant:{doc}:{cible_id}"

    def valeurs(doc, cible_id, reinit=False):
        """Pré-remplissage GESCOL, puis compléments saisis précédemment (sauf « revenir aux données GESCOL »)."""
        v = defauts(doc, cible_id)
        if not reinit:
            for k, val in (H.doc_lire(cle_saisie(doc, cible_id), {}) or {}).items():
                if k in CHAMPS or k.startswith(("sh_", "cd_")):
                    v[k] = val
        return v

    def griffe_ccs():
        """Griffe du CCS : connue dans les applications CS / DDEMP (responsable de la structure)."""
        if config.juridiction() and getattr(H, "jur_griffe", None):
            try:
                return H.jur_griffe(None)
            except Exception:  # noqa: BLE001
                return None
        return None

    def options(doc, v, code=None, signer=True):
        return dict(vierge=False, code=code, signer=signer and peut_signer(),
                    sig_ccs=H.signature(f"ecole:{H.eco()}:ccs"), griffe_ccs=griffe_ccs())

    def libelle(doc, v):
        return f"{DOCS[doc]['titre']} – {v.get('nom_prenoms', '')}".strip(" –")

    def lire_formulaire(doc):
        """Valeurs du formulaire (contrôle des notes : 0 ≤ note ≤ barème). Retourne (valeurs, erreurs)."""
        v, erreurs = {}, []
        for k in cles_doc(doc):
            v[k] = (request.form.get(k) or "").strip()[:1500]
        if DOCS[doc]["famille"] == "eval":
            for t, titre in TABLES_NOTES:
                for _g, crits in criteres_de(doc):
                    for k, lib, bar in crits:
                        try:
                            n = lire_note_bareme(v.get(f"{t}_{k}"), bar)
                            v[f"{t}_{k}"] = fmt_note(n)
                        except ValueError:
                            erreurs.append(f"{titre[6:]} – {lib} : note invalide (entre 0 et {fmt_note(bar)}).")
        for k in cles_doc(doc):
            if CHAMPS.get(k, ("", ""))[1] == "date" and v.get(k) and not lire_date_fr(v[k]):
                erreurs.append(f"{CHAMPS[k][0]} : date invalide (format jj/mm/aaaa).")
        return v, erreurs

    def completer(doc, v, auto):
        """Classe de performance calculée si non saisie ; valeurs internes (_…) reprises des données GESCOL."""
        for k, val in auto.items():
            if k.startswith("_") and k not in ("_carriere",):
                v.setdefault(k, val)
        if DOCS[doc]["famille"] == "eval":
            tt = totaux(doc, v)
            for t, _ in TABLES_NOTES:
                if not v.get(f"{t}_classe") and tt[t] is not None:
                    v[f"{t}_classe"] = classe_perf(tt[t])
        return v

    def historiser(doc, cible, cible_id, lib, lots, signe):
        codes = [o.get("code") for _v, o in lots if o.get("code")]
        donnees = [dict({k: val for k, val in v.items() if k != "_carriere"}, _code=o.get("code") or "")
                   for v, o in lots]
        return ex("""INSERT INTO docs_enseignant_historique (ecole_id, type, cible, cible_id, libelle, nombre, codes,
                     donnees, signe, annee, cree_le, cree_par) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (H.eco(), doc, cible, cible_id, lib, len(lots), ",".join(codes),
                   json.dumps(donnees, ensure_ascii=False), 1 if signe else 0, config.ANNEE_ACTIVE,
                   H.maintenant(), g.user["id"]))

    def lot_pour(doc, v, cible_id, signer):
        """(valeurs, options) pour un document ; enregistre le code QR des certificats signés."""
        opt = options(doc, v, signer=signer)
        if DOCS[doc]["qr"] and opt["signer"]:
            eleve_id = cible_id if DOCS[doc]["cible"] == "eleve" else None
            opt["code"] = H.enregistrer_document(f"docens_{doc}", eleve_id, libelle(doc, v) + f" ({config.ANNEE_ACTIVE})")
        return v, opt

    def doc_ou_404(doc):
        if doc not in DOCS:
            abort(404)
        return DOCS[doc]

    def nom_fichier(doc, suffixe=""):
        return f"{doc}{('_' + re.sub(r'[^A-Za-z0-9]+', '_', suffixe)) if suffixe else ''}.pdf"

    # ------------------------------------------------------------------ pages
    @app.route("/docs-enseignant")
    @H.connexion_requise("docs_enseignant")
    def docs_enseignant_accueil():
        d1, _d2 = H.bornes_annee()
        filtre, args = "ecole_id=?", [H.eco()]
        if role() == "enseignant":
            filtre += " AND cree_par=?"
            args.append(g.user["id"])
        stats = q(f"SELECT COUNT(*) n, COALESCE(SUM(nombre),0) docs FROM docs_enseignant_historique "
                  f"WHERE {filtre} AND annee=?", args + [config.ANNEE_ACTIVE], un=True)
        par_type = {r["type"]: r["n"] for r in q(
            f"SELECT type, COALESCE(SUM(nombre),0) n FROM docs_enseignant_historique WHERE {filtre} AND annee=? "
            f"GROUP BY type", args + [config.ANNEE_ACTIVE])}
        recents = q(f"SELECT h.*, u.nom auteur FROM docs_enseignant_historique h LEFT JOIN utilisateurs u "
                    f"ON u.id=h.cree_par WHERE {filtre.replace('ecole_id', 'h.ecole_id').replace('cree_par', 'h.cree_par')} "
                    f"ORDER BY h.id DESC LIMIT 8", args)
        agents = agents_autorises()
        nb_eleves = 0
        cls = H.classes_autorisees()
        if cls:
            marque = ",".join("?" * len(cls))
            nb_eleves = q(f"SELECT COUNT(*) n FROM eleves WHERE statut='inscrit' AND classe_id IN ({marque})",
                          [c["id"] for c in cls], un=True)["n"]
        return render_template("docs_enseignant_accueil.html", FAMILLES=FAMILLES, DOCS=DOCS, stats=stats,
                               par_type=par_type, recents=recents, nb_agents=len(agents), nb_eleves=nb_eleves,
                               est_enseignant=role() == "enseignant", peut_signer=peut_signer(),
                               carriere=table_existe("personnel_carriere"))

    @app.route("/docs-enseignant/<doc>", methods=["GET", "POST"])
    @H.connexion_requise("docs_enseignant")
    def docs_enseignant_form(doc):
        d = doc_ou_404(doc)
        cible = d["cible"]
        classes = H.classes_autorisees() if cible == "eleve" else []
        cid = request.values.get("classe", type=int)
        pid = request.values.get("p", type=int)
        personnes, classe = [], None
        if cible == "agent":
            personnes = agents_autorises()
        else:
            if pid and not cid:
                cid = eleve_autorise(pid)["classe_id"]
            if not cid and len(classes) == 1:
                cid = classes[0]["id"]
            if cid:
                H.verifier_classe(cid)
                classe = H.classe_ou_404(cid)
                personnes = q("SELECT * FROM eleves WHERE classe_id=? ORDER BY statut<>'inscrit', nom, prenoms",
                              (cid,))
        if not pid and cible == "agent" and len(personnes) == 1:
            pid = personnes[0]["id"]
        v, auto, personne = None, {}, None
        if pid:
            auto = defauts(doc, pid)
            personne = agent_ou_403(pid) if cible == "agent" else eleve_autorise(pid)
            if cible == "eleve" and classe and personne["classe_id"] != classe["id"]:
                abort(404)
        if request.method == "POST":
            if not pid:
                flash("Choisissez d'abord la personne concernée.", "warning")
                return redirect(url_for("docs_enseignant_form", doc=doc, classe=cid))
            v, erreurs = lire_formulaire(doc)
            if erreurs:
                for e in erreurs[:6]:
                    flash(e, "danger")
                return render_template("docs_enseignant_form.html", **contexte_form(
                    doc, d, classes, classe, personnes, personne, pid, v, auto)), 400
            # compléments mémorisés : seulement les valeurs saisies qui diffèrent des données GESCOL
            memo = {k: val for k, val in v.items() if val and str(val) != str(auto.get(k, ""))}
            H.doc_ecrire(cle_saisie(doc, pid), memo)
            if request.form.get("action") == "sauver":
                H.journal("docs_enseignant_saisie", f"{doc} #{pid}")
                flash("Saisie enregistrée : elle sera reprise pour ce document et dans la génération groupée.",
                      "success")
                return redirect(url_for("docs_enseignant_form", doc=doc, p=pid, classe=cid))
            v = completer(doc, v, auto)
            signer = request.form.get("signer") == "1"
            lot = lot_pour(doc, v, pid, signer)
            historiser(doc, cible, pid, libelle(doc, v), [lot], lot[1]["signer"])
            H.journal("docs_enseignant_pdf", libelle(doc, v))
            return H.pdf_reponse(construire_pdf(doc, [lot], d["titre"]),
                                 nom_fichier(doc, v.get("nom_prenoms", "")))
        if pid:
            v = valeurs(doc, pid, reinit=request.args.get("reinit") == "1")
        return render_template("docs_enseignant_form.html", **contexte_form(
            doc, d, classes, classe, personnes, personne, pid, v, auto))

    def contexte_form(doc, d, classes, classe, personnes, personne, pid, v, auto):
        car = auto.get("_carriere") or {}
        infos_car = [(k.replace("_", " ").capitalize(), date_fr(val) if re.match(r"^\d{4}-\d{2}-\d{2}", str(val))
                      else val) for k, val in car.items()
                     if val not in (None, "") and k not in ("personnel_id", "id", "maj", "cree_le")]
        gescol = []
        if personne is not None and d["cible"] == "agent":
            gescol = [("Matricule GESCOL", personne["matricule"]), ("Fonction", personne["fonction"]),
                      ("Téléphone", personne["telephone"]), ("Contrat", personne["type_contrat"]),
                      ("Date d'embauche", date_fr(personne["date_embauche"])),
                      ("Classe(s) tenue(s)", auto.get("_classes"))]
        elif personne is not None:
            cl = H.classe_de(personne)
            gescol = [("Matricule", personne["matricule"]), ("N° EducMaster", personne["matricule_educmaster"]),
                      ("Classe", cl["nom"] if cl else ""), ("Statut", personne["statut"]),
                      ("Inscription", date_fr(personne["date_inscription"])),
                      ("Année(s) de scolarité", personne["annees_scolarite"])]
        tt = totaux(doc, v or {}) if v and d["famille"] == "eval" else {}
        return dict(doc=doc, d=d, classes=classes, classe=classe, personnes=personnes, personne=personne, pid=pid,
                    v=v or {}, sections=SECTIONS[doc], CHAMPS=CHAMPS,
                    criteres=criteres_de(doc) if d["famille"] == "eval" else [], TABLES_NOTES=TABLES_NOTES,
                    CLASSES_PERF=CLASSES_PERF, gescol=[x for x in gescol if x[1] not in (None, "")],
                    infos_car=infos_car, carriere=bool(car), peut_signer=peut_signer(),
                    totaux=tt, fmt_note=fmt_note, classe_perf=classe_perf,
                    carriere_table=table_existe("personnel_carriere"))

    @app.route("/docs-enseignant/<doc>/vierge.pdf")
    @H.connexion_requise("docs_enseignant")
    def docs_enseignant_vierge(doc):
        d = doc_ou_404(doc)
        return H.pdf_reponse(construire_pdf(doc, [({}, dict(vierge=True))], d["titre"] + " (vierge)"),
                             nom_fichier(doc, "vierge"))

    @app.route("/docs-enseignant/<doc>/groupe", methods=["GET", "POST"])
    @H.connexion_requise("docs_enseignant")
    def docs_enseignant_groupe(doc):
        """PDF groupé : toute une classe (certificats d'élèves) ou tout le personnel (fiches, certificats).
        POST : personnes cochées ; GET : tous (paramètre classe= pour les élèves)."""
        d = doc_ou_404(doc)
        if d["cible"] == "eleve":
            cid = request.values.get("classe", type=int)
            if not cid:
                flash("Choisissez une classe pour la génération groupée.", "warning")
                return redirect(url_for("docs_enseignant_form", doc=doc))
            H.verifier_classe(cid)
            classe = H.classe_ou_404(cid)
            tous = q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (cid,))
            quoi = f"classe {classe['nom']}"
        else:
            cid = None
            tous = agents_autorises()
            quoi = "personnel"
        if request.method == "POST":
            choix = {int(x) for x in request.form.getlist("ids") if x.isdigit()}
            tous = [p for p in tous if p["id"] in choix]
            signer = request.form.get("signer") == "1"
        else:
            signer = True
        if not tous:
            flash("Aucune personne sélectionnée pour la génération groupée.", "warning")
            return redirect(url_for("docs_enseignant_form", doc=doc, classe=cid))
        lots = []
        for p in tous:
            auto = defauts(doc, p["id"])
            v = valeurs(doc, p["id"])
            lots.append(lot_pour(doc, completer(doc, v, auto), p["id"], signer))
        lib = f"{d['titre']} – {quoi} ({len(lots)} document{'s' if len(lots) > 1 else ''})"
        historiser(doc, d["cible"], None, lib, lots, lots[0][1]["signer"])
        H.journal("docs_enseignant_groupe", lib)
        return H.pdf_reponse(construire_pdf(doc, lots, lib), nom_fichier(doc, quoi))

    @app.route("/docs-enseignant/historique")
    @H.connexion_requise("docs_enseignant")
    def docs_enseignant_historique():
        typ = request.args.get("type", "")
        filtre, args = "h.ecole_id=?", [H.eco()]
        if role() == "enseignant":
            filtre += " AND h.cree_par=?"
            args.append(g.user["id"])
        if typ in DOCS:
            filtre += " AND h.type=?"
            args.append(typ)
        lignes = q(f"""SELECT h.id, h.type, h.cible, h.cible_id, h.libelle, h.nombre, h.codes, h.signe, h.annee,
                              h.cree_le, u.nom auteur
                       FROM docs_enseignant_historique h LEFT JOIN utilisateurs u ON u.id=h.cree_par
                       WHERE {filtre} ORDER BY h.id DESC LIMIT 500""", args)
        return render_template("docs_enseignant_historique.html", lignes=lignes, DOCS=DOCS, typ=typ,
                               peut_supprimer=role() in ("admin", "directeur"))

    def entree_hist(hid):
        h = q("SELECT * FROM docs_enseignant_historique WHERE id=? AND ecole_id=?", (hid, H.eco()), un=True)
        if not h:
            abort(404)
        if role() == "enseignant" and h["cree_par"] != g.user["id"]:
            abort(403)
        return h

    @app.route("/docs-enseignant/historique/<int:hid>.pdf")
    @H.connexion_requise("docs_enseignant")
    def docs_enseignant_reimprimer(hid):
        h = entree_hist(hid)
        if h["type"] not in DOCS:
            abort(404)
        try:
            donnees = json.loads(h["donnees"])
        except ValueError:
            abort(404)
        lots = [(v, dict(vierge=False, code=v.get("_code") or None, signer=bool(h["signe"]),
                         sig_ccs=H.signature(f"ecole:{H.eco()}:ccs"), griffe_ccs=griffe_ccs())) for v in donnees]
        return H.pdf_reponse(construire_pdf(h["type"], lots, h["libelle"]), nom_fichier(h["type"], f"h{hid}"))

    @app.route("/docs-enseignant/historique/<int:hid>/supprimer", methods=["POST"])
    @H.connexion_requise("docs_enseignant")
    def docs_enseignant_hist_supprimer(hid):
        if role() not in ("admin", "directeur"):
            abort(403)
        h = entree_hist(hid)
        ex("DELETE FROM docs_enseignant_historique WHERE id=?", (hid,))
        H.journal("docs_enseignant_hist_suppr", h["libelle"])
        flash("Entrée supprimée de l'historique (les codes de vérification déjà imprimés restent valables).",
              "success")
        return redirect(url_for("docs_enseignant_historique"))
