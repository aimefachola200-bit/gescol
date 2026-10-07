# -*- coding: utf-8 -*-
"""Carte d'identité de l'école : fiches de recensement annuel (écoles primaires / maternelles inclusives).

Principe
--------
* Chaque fiche officielle est décrite par un SCHÉMA DÉCLARATIF (rubriques → lignes de champs / tableaux) qui
  reprend 100 % des rubriques, champs, tableaux, numérotations et libellés du modèle du Ministère (fichiers
  recensement_primaire.pdf, 8 pages + guide de 5 pages, et recensement_maternelle.pdf, 5 pages).
* Le même schéma pilote : le formulaire web (onglets par rubrique), le stockage, le calcul automatique depuis
  GESCOL, les contrôles de cohérence, le PDF (qui redessine la fiche dans sa forme d'origine), le PDF vierge et
  l'export / import Excel.
* Stockage : H.doc_ecrire(f"e{école}:recensement:{type}:{année}") → {clé_champ: valeur saisie}. Une valeur
  vide = valeur CALCULÉE par GESCOL (si disponible) ; une valeur non vide = valeur SAISIE (correction).
  La barre « Sauvegarder / Charger / Réinitialiser » (M.barre_doc) travaille sur la même clé.
* Téléversement : la fiche officielle scannée / remplie (PDF ou image) est archivée par année
  (table recensement_depots, fichiers dans <données>/recensement/).

Routes : voir enregistrer().
"""
import io
import json
import os
import re
import uuid
from datetime import date, datetime

from flask import abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

# ============================================================================ mini-langage des schémas
# Champs simples (placés dans une ligne L) ---------------------------------------------------------------
def ON(k, lib="", maj=False):
    """Question Oui / Non (deux cases)."""
    return {"k": k, "t": "on", "lib": lib, "maj": maj}


def CH(k, opts, lib="", multi=False):
    """Cases à cocher : une seule (multi=False) ou plusieurs (multi=True)."""
    return {"k": k, "t": "ch", "opts": list(opts), "lib": lib, "multi": multi}


def NB(k, lib="", n=2, dec=0, unite="", somme=None):
    """Nombre écrit dans des cases l__l__l (n cases avant la virgule, dec après)."""
    return {"k": k, "t": "nb", "lib": lib, "n": n, "dec": dec, "unite": unite, "somme": somme}


def TX(k, lib="", w=45, lignes=1):
    """Texte libre sur pointillés (w = largeur en mm dans le PDF)."""
    return {"k": k, "t": "tx", "lib": lib, "w": w, "lignes": lignes}


def MT(k, lib="", somme=None):
    """Montant en FCFA (cadre)."""
    return {"k": k, "t": "mt", "lib": lib, "somme": somme}


def CASE(k, lib=""):
    """Case unique (cochée / non cochée)."""
    return {"k": k, "t": "case", "lib": lib}


# Éléments de mise en page ----------------------------------------------------------------------------------
def L(num, texte, *champs, ind=0, st=""):
    """Ligne : numéro, texte, puis champs (ou textes littéraux) les uns à la suite des autres."""
    return {"i": "L", "num": num, "texte": texte, "champs": list(champs), "ind": ind, "st": st}


def P(texte, st="", ind=0):
    """Texte seul (note, consigne). st : 'i' italique, 'b' gras, 'p' petit."""
    return {"i": "P", "texte": texte, "st": st, "ind": ind}


def GRILLE(champs, ncol=3, ind=6):
    """Grille de champs numériques (libellé + cases) sur ncol colonnes."""
    return {"i": "G", "champs": champs, "ncol": ncol, "ind": ind}


def C2(gauche, droite, ratio=0.5):
    """Deux colonnes côte à côte (dans le PDF) ; l'une après l'autre dans le formulaire web."""
    return {"i": "C2", "g": gauche, "d": droite, "ratio": ratio}


def SAUT(paysage=False):
    """Saut de page du modèle (paysage : page à l'italienne)."""
    return {"i": "SAUT", "paysage": paysage}


def SIGNATURES(kind):
    return {"i": "SIG", "kind": kind}


def ESP(mm_=2):
    return {"i": "ESP", "h": mm_}


# Tableaux ------------------------------------------------------------------------------------------------
def K(k, lib, t="n", v=False, w=None, somme=None):
    """Colonne feuille. t : n (entier), d (décimal), c (case), t (texte), an (année). v : en-tête vertical."""
    return {"k": k, "lib": lib, "t": t, "v": v, "w": w, "somme": somme}


def GR(lib, *sub, v=False):
    """Groupe de colonnes (en-tête fusionné)."""
    return {"k": None, "lib": lib, "sub": list(sub), "v": v}


def R(k, lib, groupe=None, total=None, grise=(), fusion=None, span=None, st=""):
    """Ligne de tableau. total : clés des lignes additionnées ; grise : colonnes grisées (non applicables) ;
    fusion : (colonnes, texte) cellules fusionnées portant un texte ; span : {col: nb} cellule saisissable
    étendue sur nb colonnes."""
    return {"k": k, "lib": lib, "groupe": groupe, "total": total, "grise": set(grise), "fusion": fusion,
            "span": span or {}, "st": st}


def T(k, cols, rows, coin="", label_w=32, taille=6.5, dyn=None, titre="", ind=0, largeur=None, h_ligne=None,
      label_v=False):
    return {"i": "T", "k": k, "cols": cols, "rows": rows, "coin": coin, "label_w": label_w, "taille": taille,
            "dyn": dyn, "titre": titre, "ind": ind, "largeur": largeur, "h_ligne": h_ligne, "label_v": label_v}


def S(num, titre, *items, onglet=None):
    return {"num": num, "titre": titre, "items": list(items), "onglet": onglet or f"{num}. {titre.capitalize()}"}


def gft(p, lib, noms=("G", "F", "T"), v=False):
    """Groupe de trois colonnes Garçons / Filles / Total (Total = G + F)."""
    return GR(lib, K(p + "_g", noms[0], v=v), K(p + "_f", noms[1], v=v),
              K(p + "_t", noms[2], somme=[p + "_g", p + "_f"], v=v))


NIV = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
OUINON = ["Oui", "Non"]


def _dist(k, lib):
    return L("", lib, NB(k, n=3, dec=1, unite="km"), ind=4)


# ============================================================================ FICHE PRIMAIRE (EP)
_ETAT_LOCAUX = [
    K("annee", "Année mise en service du local", "an", v=True, w=13),
    K("non_util", "cocher si la salle de classe n'est pas utilisée", "c", v=True, w=6),
    K("superficie", "Superficie de la salle (m²)", "n", v=True, w=10),
    GR("Nature des murs", K("m_dur", "en dur", "c", v=True), K("m_semi", "semi-dur / banco …", "c", v=True),
       K("m_autre", "autre : Planche / bambou", "c", v=True), K("m_sans", "sans mur", "c", v=True), v=True),
    GR("Etat des murs", K("em_bon", "bon / acceptable", "c", v=True), K("em_mauv", "mauvais", "c", v=True), v=True),
    GR("Nature du toit", K("t_toles", "tôles", "c", v=True), K("t_tuiles", "tuiles / fibro ciment / dalles", "c", v=True),
       K("t_banco", "banco", "c", v=True), K("t_paille", "paille", "c", v=True), K("t_sans", "sans toit", "c", v=True),
       v=True),
    GR("Etat du toit", K("et_bon", "bon / acceptable", "c", v=True), K("et_mauv", "mauvais", "c", v=True), v=True),
    GR("Nature des portes", K("p_metal", "métallique", "c", v=True), K("p_tole", "tôle / bois", "c", v=True),
       K("p_non", "non installées", "c", v=True), v=True),
    GR("Nature des fenêtres", K("f_pers", "persiennes", "c", v=True), K("f_volets", "volets", "c", v=True),
       K("f_claus", "claustras", "c", v=True), K("f_non", "non installées", "c", v=True), v=True),
    GR("Qui a financé la construction du local", K("fin_etat", "Etat", "c", v=True),
       K("fin_coll", "collectivités locales", "c", v=True), K("fin_ape", "APE", "c", v=True),
       K("fin_ext", "aide extérieure", "c", v=True), K("fin_autre", "autres / non déterminé", "c", v=True), v=True),
    GR("Rampe", K("r_anti", "antidérapant", "c", v=True), K("r_main", "main courante", "c", v=True),
       K("r_incl", "inclinaison de moins de 5°", "c", v=True), v=True),
]
_SALLES = [R(f"s{i}", f"Salle/Classe {i}") for i in range(1, 13)]
_AUTRES_LOCAUX = [R(k, lib, grise={"non_util"}) for k, lib in [
    ("bureau", "Bureau"), ("magasin", "Magasin"), ("latrines", "Latrines"), ("cuisine", "Cuisine"),
    ("biblio", "Bibliothéque"), ("info", "Salle informatique"), ("logement", "Logement")]]

_MOB_COLS = [
    GR("Mobilier enseignants", K("bureau", "Bureau maître avec chaise"), K("armoire", "Armoire ou placard")),
    K("tableau", "Tableau noir"),
    GR("Année d'études", *[K("a_" + n.lower(), n, "c", v=True, w=4.2) for n in NIV]),
    GR("Mobilier élèves", K("t1", "Nombre de table avec chaises (1 place)"),
       GR("Nombre de table-bancs ou table+banc à :", K("t2", "2 places"), K("t3", "3 places et plus")),
       K("adapt", "Mobiliers adaptés")),
]
_MOB_ANNEES = ["a_" + n.lower() for n in NIV]
_OUVRAGES = ["Programmes d'études Français", "Prog. d'études Mathématiques", "Programmes d'études EST",
             "Programmes d'études ES", "Programmes d'études EA", "Programmes d'études EPS", "Guide de Français",
             "Guide de Mathématiques", "Guide d'EST", "Guide d'ES", "Guide d'EA", "Guide d'EPS"]
_OUVRAGES2 = ["Guide d'Anglais", "Guide d'Informatique", "Mesures correctives", "Guide d'évaluation",
              "Manuel sur la non violence", "Mesures alternatives aux châtiments corporels"]
_COLS_NIV = [K(n.lower(), n) for n in NIV]

_EH = ("eh_g", "eh_f", "eh_t")
_AGES_P = [("a4", "Moins de 5 ans")] + [(f"a{i}", f"{i} ans") for i in range(5, 16)] + [("a16", "16 ans et plus")]
_T73_COLS = [gft(n.lower(), n) for n in NIV] + [
    GR("ENSEMBLE", K("ens_g", "G", somme=[n.lower() + "_g" for n in NIV]),
       K("ens_f", "F", somme=[n.lower() + "_f" for n in NIV]), K("ens_t", "T", somme=["ens_g", "ens_f"])),
    gft("eh", "DONT E.H")]
_HANDI = [("hm", "Moteur"), ("hv", "Visuel"), ("ha", "Auditif"), ("hi", "Intellectuel"), ("hx", "Autres")]
_T73_ROWS = ([R(k, lib) for k, lib in _AGES_P]
             + [R("tot", "Total", total=[k for k, _ in _AGES_P], st="b"),
                R("red", "Total des redoublants", groupe="Dont redoublants"),
                R("red6", "Redoublants ayant 6 ans", groupe="Dont redoublants"),
                R("red11", "Redoublants ayant 11 ans", groupe="Dont redoublants"),
                R("etr", "dont étrangers"),
                R("ov", "Orphelins ou enfants vulnérables"),
                R("orph_h", "handicapés", groupe="Orphelins", grise=_EH),
                R("orph_nh", "non handicapés", groupe="Orphelins", grise=_EH)]
             + [R(k, lib, groupe="Enfants handicapés", grise=_EH) for k, lib in _HANDI]
             + [R("htot", "Total Enfants Handicapés", groupe="Enfants handicapés", total=[k for k, _ in _HANDI],
                  grise=_EH, st="b"),
                R("sans_acte", "Elèves sans acte de naissance", grise=_EH),
                R("venus", "Nouveaux élèves venus d'une autre école", grise=_EH),
                R("gross", "Cas de grossesse", grise=_EH)])

_PERS_P_COLS = [
    K("mat", "N° matri-cule (1)", "t", w=15), K("nip", "NIP", "t", w=17), K("nom", "Nom et Prénoms", "t", w=36),
    GR("PH", K("ph_o", "Oui", "c", w=5), K("ph_n", "Non", "c", w=5)),
    GR("sexe (2)", K("sx_m", "M", "c", w=4.5), K("sx_f", "F", "c", w=4.5)),
    K("naiss", "Année de naissance", "an", w=13),
    GR("Diplômes le plus élevé (3)", K("dip_a", "académique", "t", v=True, w=11),
       K("dip_p", "professionnel", "t", v=True, w=11)),
    K("grade", "Grade", "t", v=True, w=10), K("statut", "Statut (4)", "t", w=10),
    K("fonction", "Fonction", "t", w=15),
    GR("Cours tenus", *[K("c_" + n.lower(), n, "c", v=True, w=4.2) for n in NIV]),
    K("indice", "Indice réel", "t", v=True, w=8),
    GR("Ancienneté", K("anc_fp", "Fonction Publique", "t", v=True, w=7), K("anc_dep", "Département", "t", v=True, w=7),
       K("anc_ec", "Ecole", "t", v=True, w=7)),
    K("formation", "Date de la dernière formation continue", "t", v=True, w=12),
    GR("Nombre de visites (5)", K("vis_i", "Inspecteur", "n", v=True, w=5.5), K("vis_cp", "CP", "n", v=True, w=5.5),
       K("vis_d", "Directeur", "n", v=True, w=5.5)),
    K("up_pct", "% participation aux UP", "d", v=True, w=9),
    GR("Formations", K("f_ls", "Langue des signes", "t", v=True, w=8), K("f_eb", "Ecriture braille", "t", v=True, w=8),
       K("f_pi", "Pédagogie inclusive", "t", v=True, w=9)),
]
_NOTES_PERS_P = [
    "(1) Pour les APE et ACE, indiquer le numéro matricule figurant sur la fiche de paie",
    "(2) Cocher \"M\" pour masculin et \"F\" pour féminin",
    "(3) Diplômes académiques (BEPC, BAC, LICENCE etc.) ou professionnels (CEAP, CAP, etc.) le plus élevé",
    "(4) C'est le statut de l'enseignant? Il peut être APE, ACE, AME, Stagiaire, PRIVE ou Autre",
    "(5) Il s'agit des inspections, contrôles et visites effectués par le personnel d'encadrement et le Directeur "
    "à l'enseignant au cours de l'année antérieure"]

SCHEMA_PRIMAIRE = {
    "type": "primaire", "titre": "FICHE DE RECENSEMENT ANNUEL DES ECOLES PRIMAIRES",
    "titre_court": "Fiche de recensement annuel des écoles primaires (EP)",
    "pied": "Recensement annuel écoles primaires", "pages_modele": 8, "georef": True,
    "admin": [TX("code_ecole", "Code école"), TX("georef", "Géo-référencement")],
    "sections": [
        S("1", "IDENTIFICATION ET LOCALISATION DE L'ETABLISSEMENT",
          L("1.1.", "Nom de l'école :", NB("nom", n=27), st="cadre"),
          L("1.2.", "Année de création :", NB("creation_an", n=4), TX("creation_ref", "Référence :", w=55),
            TX("creation_du", "du", w=30)),
          L("1.3.", "Année dernière extension :", NB("extension_an", n=4), TX("extension_ref", "Référence :", w=50),
            TX("extension_du", "du", w=28)),
          L("1.4.", "Statut :", CH("statut", ["Public", "Privé Laïc", "Privé Confessionnel", "Communautaire"])),
          L("1.5.", "Type :", CH("type_ens", ["Classique", "Inclusif", "Spécialisé", "Autres :"]),
            TX("type_preciser", "Préciser :", w=35)),
          L("1.6.", "Localisation dans le Réseau d'Animation Pédagogique :"),
          L("", "i. Circonscription Scolaire :", TX("cs", w=110), ind=6),
          L("", "ii. Zone Pédagogique :", CH("zone", ["1", "2", "3", "4", "5", "6"]), ind=6),
          L("", "iii. Unité Pédagogique :", TX("up", w=110), ind=6),
          L("1.7.", "Localisation dans l'Administration Territoriale :"),
          L("", "i. Département :", TX("departement", w=115), ind=6),
          L("", "ii. Commune :", TX("commune", w=115), ind=6),
          L("", "iii. Arrondissement :", TX("arrondissement", w=110), ind=6),
          L("", "iv. Village ou Quartier de ville :", TX("village", w=100), ind=6),
          L("", "v. Adresse :", TX("adresse", w=30), TX("bp", "BP.", w=16), TX("ville", "Ville", w=28),
            TX("telephone", "Téléphone", w=34), ind=6),
          L("", "vi. Adresse mail", TX("email", w=70), ind=6),
          onglet="1. Identification"),
        S("2", "ENVIRONNEMENT SOCIO-ECONOMIQUE",
          C2([L("2.1.", "Distance de l'école au :"),
              _dist("d_dep", "i. chef-lieu du département :"), _dist("d_com", "ii. Chef-lieu de commune :"),
              _dist("d_arr", "iii. chef-lieu de l'arrondissement :"), _dist("d_cs", "iv. bureau de la Circ. Scolaire"),
              _dist("d_sante", "v. centre de santé le plus proche :"), _dist("d_marche", "vi. marché le plus proche :"),
              _dist("d_village", "vii. village le plus éloigné desservi"),
              L("2.3.", "L'école est-elle inondable?", ON("inondable", maj=True)),
              L("2.4.", "La localité est-elle électrifiée ?", ON("electrifiee", maj=True)),
              L("", "", CH("electrifiee_src", ["i. SBEE", "ii. Autres alternatives :"], multi=True),
                TX("electrifiee_autre", "(précisez)", w=25), ind=4)],
             [L("2.2.", "Accessibilité :"),
              L("", "L'Accès est-il permanent ?", ON("acces_permanent")),
              L("", "précisez la période favorable :", TX("acces_periode", w=40), st="i"),
              P("Etat de la route et distance de l'école au bureau de la CS.", st="ip"),
              L("", "i. Route bitumée :", NB("r_bitume", n=3, dec=1, unite="km")),
              L("", "ii. Piste accessible à tous véhicules:", NB("r_piste", n=3, dec=1, unite="km")),
              L("", "iii. Piste accessible seulement aux véhicules tout terrain (4*4) :",
                NB("r_4x4", n=3, dec=1, unite="km")),
              L("", "iv. Piste accessible seulement aux 2 roues :", NB("r_2roues", n=3, dec=1, unite="km")),
              L("", "v. Piste accessible seulement à pieds :", NB("r_pieds", n=3, dec=1, unite="km")),
              L("", "vi. Autres moyens d'accès (précisez)", TX("r_autres", w=30)),
              L("", "vii. L'école est-elle accessible à tout enfant handicapé ?", ON("acces_handicape"))]),
          C2([L("2.5.", "Etablissements scolaires environnants:"),
              P("(établissement scolaire le plus proche et distance qui sépare)", st="p", ind=4),
              L("", "i. EM:", NB("e_em", n=2, dec=1, unite="km"), ind=6),
              L("", "ii. 1ère EP:", NB("e_ep1", n=2, dec=1, unite="km"), ind=6),
              L("", "iii. 2ème EP", NB("e_ep2", n=2, dec=1, unite="km"), ind=6),
              L("", "iv. CEG ou Lycée", NB("e_ceg", n=2, dec=1, unite="km"), ind=6)],
             [L("2.6.", "Approvisionnement de la localité en eau potable"),
              P("(cocher la ou les cases correspondantes)", st="p", ind=4),
              L("", "", CH("eau_localite", ["i. Eau courante", "ii. Forage", "iii. Puits", "iv. Citerne",
                                            "v. Autres (préciser) ."], multi=True), TX("eau_localite_autre", w=30))]),
          L("2.7.", "L'environnement scolaire est-il pollué", ON("pollue", maj=True),
            "Si oui cocher les cases correspondantes"),
          L("", "", CH("pollution", ["i Sonore", "ii Atmosphérique"], multi=True),
            TX("pollution_autre", "iii Autre (Précisez)", w=40), ind=4),
          onglet="2. Environnement"),
        SAUT(),
        S("3", "INFORMATIONS GENERALES SUR L'ECOLE",
          L("3.1.", "Titre de propriété de l'école", "(cocher la case correspondante)"),
          L("", "", CH("titre_propriete", ["i. Titre foncier", "ii. Acte de l'autorité chargée de l'administration "
                                           "territoriale", "iii. Acte de donation", "iv. Contrat de location entre "
                                           "l'école et un propriétaire", "v. Aucun Acte"]), ind=4),
          L("3.2.", "Le domaine scolaire est-il délimité ?", ON("domaine_delimite"),
            NB("domaine_superficie", "Si Oui, quelle est sa superficie ?", n=2, dec=2, unite="ha")),
          L("3.3.", "Le domaine scolaire est-il limité par une clôture ?", ON("cloture")),
          L("3.4.", "La cour de la récréation est-elle ombragée ?", ON("cour_ombragee")),
          L("3.5.", "L'école a-t-elle un point d'eau potable dans le domaine ?", ON("point_eau")),
          P("(si oui, cocher la ou les cases correspondantes)", st="ip", ind=8),
          L("", "", CH("point_eau_src", ["i. SONEB", "ii. Forage fonctionnel", "iii Adduction d'eau villageoise",
                                         "iv. Puits", "v. Citerne", "vi. Autres (préciser) ."], multi=True),
            TX("point_eau_autre", w=30), ind=8),
          P("(si non, à quelle distance se trouve le point d'eau potable, le plus proche? Cocher la ou les cases "
            "correspondantes)", st="ip", ind=8),
          L("", "", CH("point_eau_dist", ["moins de 1 km", "2 km?", "3 km?", "5 km?", "plus de 5 km?"])),
          L("3.6.", "L'école dispose t-elle d'un dispositif de lavage de mains ?", ON("lavage_mains")),
          L("3.7.", "L'école est-elle alimentée en électricité ?", ON("electricite"),
            "(si oui, cocher la ou les cases correspondantes)"),
          L("", "", CH("electricite_src", ["SBEE", "Groupe électrogène", "Energie solaire", "Autre"], multi=True),
            TX("electricite_autre", w=30), ind=6),
          L("3.8.", "L'école dispose-t-elle d'une cantine fonctionnelle ?", ON("cantine")),
          L("", "Si oui, préciser l'organisme de soutien", CH("cantine_org", ["i. Gouvernement", "ii. Autres"],
                                                               multi=True),
            TX("cantine_org_autre", "(Préciser)", w=35), st="p"),
          L("3.9.", "L'école dispose-t-elle d'un équipement de cuisine ?", ON("equip_cuisine")),
          L("3.10.", "L'école dispose-t-elle d'un magasin de vivres en bon état ?", ON("magasin_vivres")),
          L("3.11.", "L'école dispose-t-elle d'un jardin ou d'un champ scolaire ?", ON("jardin")),
          L("3.12.", "L'école a-t-elle :"),
          L("", "i. des latrines fonctionnelles ?", ON("latrines"), ind=8),
          L("", "Si Oui, indiquer le nombre de blocs :", NB("latrines_blocs", n=2),
            NB("latrines_cabines", "Le nombre de cabines", n=2),
            CASE("latrines_separees", "Sont-elles séparées pour F/G"), ind=10),
          L("", "Existe-t-il des latrines pour le personnel enseignant ?", ON("latrines_personnel"), ind=8),
          L("", "ii. des latrines handi sexospécifique ?", ON("latrines_handi"),
            CASE("latrines_handi_sep", "Sont-ils séparés pour F/G"), ind=8),
          L("", "iii. un urinoir aménagé ?", ON("urinoir"), CASE("urinoir_sep", "Sont-ils séparés pour F/G"), ind=8),
          L("", "iv. une bibliothèque fonctionnelle ?", ON("bibliotheque"),
            NB("bibliotheque_ouvrages", "Si oui, préciser le nombre d'ouvrages", n=2), ind=8),
          L("", "v. une boîte à pharmacie ?", ON("pharmacie"), ind=8),
          L("", "vi. un terrain de sport tracé ?", ON("sport_trace"), ind=8),
          L("", "vii. un terrain de sport équipé ?", ON("sport_equipe"), ind=8),
          L("", "vii. des aménagements adaptés aux enfants handicapés ?", ON("amenag_handi"), ind=8),
          L("", "Si oui, préciser le type d'aménagement sportif", TX("amenag_type", w=60), ind=14),
          L("3.13.", "Les organes de gestion existants", "(cocher la case correspondante)"),
          L("", "i. Existe-t-il une Association des Parents d'Elèves ? :", ON("ape"), ind=4),
          L("", "ii. Existe-t-il une Association des mères d'Elèves ?:", ON("ame"), ind=4),
          L("", "iii. Existe-t-il un comité de direction ?", ON("comite_direction"), ind=4),
          L("", "iv. Existe-t-il un conseil des maîtres ?", ON("conseil_maitres"), ind=4),
          L("", "v. Existe-t-il d'autres comités de gestion ?", ON("autres_comites"), ind=4),
          L("", "Si Oui cocher ceux qui existent :", CH("comites", [
              "Comité de gestion de la cantine", "Comité de santé", "Comité de gestion du livre", "Comité espace vert",
              "Gouvernement des enfants", "Comité genre", "Comité de réception de matériels et fournitures scolaires"],
              multi=True), ind=14),
          L("", "vi. Y-a-t-il de parents d'enfant handicapé au sein du bureau APE ?", ON("ape_parents_handi"), ind=4),
          L("", "vii. Y-a-t-il de personnes handicapées au sein du bureau APE ?", ON("ape_personnes_handi"), ind=4),
          L("3.14", "Structure pédagogique"),
          T("t314", _COLS_NIV + [K("salles", "Nombre de salles de classes utilisées", w=28)],
            [R("simples", "Simples"), R("jumeles", "Jumelés"), R("multi", "Multigrades")], label_w=30, largeur=150,
            ind=4),
          C2([L("3.15.", "Nombre de classes et de salles de classes"),
              L("", "i. Nombre de classes autorisées :", NB("classes_autorisees", n=2), ind=6),
              L("", "ii. Nombre de classes existantes :", NB("classes_existantes", n=2), ind=6),
              L("", "iii. Nombre de salles de classes existantes :", NB("salles_existantes", n=2), ind=6),
              L("", "iv. Nombre de salles de classes utilisées :", NB("salles_utilisees", n=2), ind=6)],
             [L("3.16.", "L'enseignement est-il dispensé en :"),
              L("", "Français", ON("l_francais"), ind=4), L("", "Anglais", ON("l_anglais"), ind=4),
              L("", "Arabe", ON("l_arabe"), ind=4), L("", "Langue nationale", ON("l_nationale"), ind=4),
              L("", "si oui, precisez", TX("l_nationale_p", w=40), ind=4),
              L("", "Langue des signes", ON("l_signes"), ind=4), L("", "Autre langue", ON("l_autre"), ind=4),
              L("", "si oui, precisez", TX("l_autre_p", w=40), ind=4)], ratio=0.55),
          onglet="3. Informations générales"),
        SAUT(),
        S("4", "CARACTERISTIQUES ET ETAT DES LOCAUX",
          T("t4", _ETAT_LOCAUX, _SALLES + _AUTRES_LOCAUX, label_w=26, taille=6, h_ligne=7.6),
          L("", "Observations éventuelles sur les locaux :", TX("obs_locaux", w=170, lignes=3), ind=6),
          onglet="4. Locaux"),
        SAUT(),
        S("5", "CARACTERISTIQUES DU MOBILIER",
          T("t5", _MOB_COLS, [R(f"s{i}", f"Salle/Classe {i}") for i in range(1, 13)] + [
              R(k, lib, fusion=(_MOB_ANNEES, lib)) for k, lib in [
                  ("magasin", "Magasin"), ("bureau", "Bureau"), ("biblio", "Bibliothèque"),
                  ("info", "Salle informatique")]] + [
              R("total", "TOTAL", total=[f"s{i}" for i in range(1, 13)] + ["magasin", "bureau", "biblio", "info"],
                fusion=(_MOB_ANNEES, "TOTAL"), st="b")], label_w=20, taille=6.5),
          onglet="5. Mobilier"),
        S("6", "EQUIPEMENTS DIDACTIQUES ET PEDAGOGIQUES",
          L("6.1.", "Equipements collectifs"),
          L("6.1.1.", "Equipements Ordinaires"),
          GRILLE([NB("eq_malettes", "Malettes pédagogiques :"), NB("eq_comp_geo", "Compendiums géométriques"),
                  NB("eq_globes", "Globes terrestres"), NB("eq_cartes", "Cartes murales géographiques"),
                  NB("eq_comp_sci", "Compendiums scientifiques"), NB("eq_dico", "Dictionnaires"),
                  NB("eq_comp_met", "Compendiums métriques"), NB("eq_planches", "Planches scientifiques"),
                  NB("eq_polyedre", "Caisse à polyèdre"), NB("eq_ordi", "Ordinateurs de bureau"),
                  NB("eq_imprimantes", "Imprimantes"), NB("eq_photocop", "Photocopieurs"),
                  NB("eq_boite_images", "Boîte à images")]),
          L("6.1.2.", "Equipements adaptés"),
          GRILLE([NB("ea_poincon", "Poinçon"), NB("ea_tablette", "Tablette"), NB("ea_cube", "Cube"),
                  NB("ea_loupe", "Loupe"), NB("ea_imp_braille", "Imprimante braille"),
                  NB("ea_lecteur", "Lecteur d'écran"), NB("ea_perkins", "Machine perkins"),
                  NB("ea_telea", "Téléagrandisseur"), NB("ea_cubary", "Cubarythme")]),
          L("6.2.", "Ouvrages pédagogiques à la disposition du maître"),
          T("t62", _COLS_NIV, [R(f"o{i}", lib) for i, lib in enumerate(_OUVRAGES, 1)], label_w=48, ind=4,
            taille=7),
          SAUT(),
          T("t62b", _COLS_NIV, [R(f"o{i}", lib) for i, lib in enumerate(_OUVRAGES2, 13)]
            + [R("autres", "Autres (Précisez)")], label_w=48, ind=4, taille=7, titre="6.2 (suite)"),
          L("", "Autres ouvrages (précisez) :", TX("ouvrages_autres", w=80), ind=4),
          L("6.3.", "Manuels des élèves conformes aux programmes d'études (préciser le nombre de manuels officiels)"),
          L("6.3.1.", "Manuels ordinaires"),
          T("t631", _COLS_NIV, [R("fr", "Manuel de français"), R("ma", "Manuel de Mathématiques")], label_w=48,
            ind=4, taille=7),
          L("6.3.2.", "Manuels adaptés"),
          T("t632", _COLS_NIV, [R("fr", "Manuel de français en braille"),
                                R("ma", "Manuel de Mathématiques en braille")], label_w=48, ind=4, taille=7),
          onglet="6. Équipements"),
        SAUT(),
        S("7", "EFFECTIFS DES ELEVES",
          C2([L("7.1.", "Effectif global"),
              L("", "Masculin", NB("eff_m", n=4), ind=6), L("", "Féminin", NB("eff_f", n=4), ind=6),
              L("", "Total", NB("eff_t", n=4, somme=["eff_m", "eff_f"]), ind=6)],
             [L("7.2.", "Nouveaux inscrits au CI"),
              L("", "i. Répartition selon le genre et par âge", ind=4),
              T("t72", [K("g", "G"), K("f", "F"), K("t", "T", somme=["g", "f"])],
                [R("m45", "Moins de 4 ans et demi"), R("a45", "4 ans et demi"), R("a5", "5 ans"), R("a6", "6 ans"),
                 R("a7", "7 ans"), R("a8", "8 ans"), R("a9", "9 ans et plus"),
                 R("tot", "Total", total=["m45", "a45", "a5", "a6", "a7", "a8", "a9"], st="b")],
                coin="Age", label_w=26, largeur=62, ind=4, taille=7),
              L("", "ii. Nouveaux inscrits CI ayant suivi l'enseignement maternel (tous âges confondus)", ind=4),
              T("t72b", [K("g", "G"), K("f", "F"), K("t", "T", somme=["g", "f"])], [R("n", "Effectif")],
                label_w=26, largeur=62, ind=4, taille=7)], ratio=0.36),
          L("7.3.", "Répartition des élèves par âge, selon le genre et par année d'étude"),
          T("t73", _T73_COLS, _T73_ROWS, label_w=32, taille=6.5),
          onglet="7. Effectifs"),
        SAUT(paysage=True),
        S("8", "ETAT NOMINATIF DU PERSONNEL ENSEIGNANT",
          T("t8", _PERS_P_COLS, [], coin="N° d'ordre", label_w=7, taille=6.5, label_v=True,
            dyn={"min": 12, "fonction": "fonction", "premier": "Directeur", "autres": "Adjoint"}, h_ligne=8),
          *[P(n, st="p") for n in _NOTES_PERS_P],
          onglet="8. Personnel enseignant"),
        SAUT(),
        S("9", "RESULTATS AUX EXAMENS DE LA DERNIERE SESSION",
          T("t9", [gft("cep", "CEP", ("G", "F", "Total")), gft("cva", "CEP Vie active", ("G", "F", "Total")),
                   GR("Ensemble", K("ens_g", "G", somme=["cep_g", "cva_g"]), K("ens_f", "F", somme=["cep_f", "cva_f"]),
                      K("ens_t", "Total", somme=["ens_g", "ens_f"])),
                   gft("eh", "Dont enfants handicapés", ("G", "F", "Total"))],
            [R("inscrits", "Inscrits"), R("composes", "Ont Composé"), R("admis", "Admis")], label_w=30, taille=7.5),
          onglet="9. Examens"),
        S("10", "ETAT NOMINATIF DU PERSONNEL DE SOUTIEN",
          T("t10", [K("mat", "N° matricule", "t", w=18), K("nip", "NIP", "t", w=20), K("nom", "Nom et prénoms", "t", w=48),
                    GR("Sexe", K("sx_m", "M", "c", w=5), K("sx_f", "F", "c", w=5)),
                    GR("PH", K("ph_o", "Oui", "c", w=6), K("ph_n", "Non", "c", w=6)),
                    K("fonction", "Fonction", "t", w=24), K("age", "Age", "n", w=14), K("statut", "Statut", "t")],
            [], coin="N° ordre", label_w=8, taille=7.5, label_v=True, dyn={"min": 4}),
          P("qualité* : secrétaire, gardien, cuisinier, agent de liaison, Agent d'entretien, etc.", st="", ind=4),
          onglet="10. Personnel de soutien"),
        S("11", "GESTION PARTICIPATIVE DE L'ECOLE",
          L("11.1.", "Le bureau APE est-il fonctionnel ?", ON("ape_fonctionnel")),
          L("11.2.", "Si oui, Ce bureau comporte-t-il tous les membres requis ?", ON("ape_complet")),
          L("11.3.", "Combien de réunions avez-vous tenu l'année scolaire précédente :", TX("nb_reunions", w=30)),
          L("11.4.", "Combien d'Assemblées Générales (AG) avez-vous tenu l'année scolaire précédente :",
            TX("nb_ag", w=25)),
          L("11.5.", ": Combien d'AG ont traité des questions du budget :", TX("nb_ag_budget", w=40)),
          L("11.6.", ": Combien d'AG ont traité des questions des résultats scolaires :", TX("nb_ag_resultats", w=40)),
          L("1.7-", "Autres sujets abordés au cours des AG :", CH("sujets_ag", [
              "Environnement / Santé", "Kit Scolaire", "Maintien des enfants à l'Ecole", "Autres"], multi=True),
            TX("sujets_ag_autre", "Préciser", w=35)),
          L("11.8.", "Communication des résultats :", CH("communication", [
              "Carnet de correspondance", "AG", "Réunion APE", "Echange avec les parents concernés"], multi=True),
            TX("communication_autre", "Autre :", w=30)),
          L("11.9.", "L'école dispose-t-elle de projets d'éducation au développement (Ecoles verte) ?",
            ON("projet_ecole_verte")),
          L("11.10.", "L'école dispose-t-elle d'un projet de développement inclusif ?", ON("projet_inclusif")),
          onglet="11. Gestion participative"),
        S("12", "DONNEES FINANCIERES",
          L("12.1.", "Montant du budget exécuté l'année précédente :", MT("budget_execute")),
          L("", "Le bureau APE est-il opérationnel ?", ON("ape_operationnel"), ind=8),
          L("12.2.", "Eléments constitutifs du budget de l'année en cours :"),
          L("", "i. Solde de l'exercice antérieur :", MT("b_solde"), ind=18),
          L("", "ii. Montant de la subvention reçue de l'Etat :", MT("b_subvention"), ind=18),
          L("", "iii. Montant de la cotisation des parents d'élèves :", MT("b_cotisation"), ind=18),
          L("", "iv. Autres ressources :", MT("b_autres"), ind=18),
          L("", "TOTAL BUDGET (i + ii + iii + iv) :",
            MT("b_total", somme=["b_solde", "b_subvention", "b_cotisation", "b_autres"]), ind=30, st="b"),
          L("", "Date de remplissage :", TX("date_remplissage", w=110), ind=4),
          L("", "Par Madame / Monsieur", TX("rempli_par", w=110), ind=4),
          SIGNATURES("primaire"),
          onglet="12. Données financières"),
    ],
}

# ============================================================================ FICHE MATERNELLE (EM inclusive)
_AGES_M = [("m25", "Moins de 2 ans 1/2"), ("a25", "2 ans 1/2 à 3 ans"), ("a3", "3 ans"), ("a4", "4 ans"),
           ("a5", "5 ans"), ("p5", "Plus de 5 ans")]
_MFT = ("Masculin", "Féminin", "Total")
_T3M_COLS = [gft("pe", "Section des petits", _MFT), gft("gr", "Section des grands", _MFT),
             GR("Ensemble", K("ens_g", "Masculin", somme=["pe_g", "gr_g"]), K("ens_f", "Féminin", somme=["pe_f", "gr_f"]),
                K("ens_t", "Total", somme=["ens_g", "ens_f"])),
             gft("eh", "Dont Enfants handicapés", _MFT)]
_T3M_ROWS = ([R(k, lib) for k, lib in _AGES_M]
             + [R("tot", "Total", total=[k for k, _ in _AGES_M], st="b"),
                R("ov", "dont orphelins ou enfants vulnérables"),
                R("orph_h", "Handicapés", groupe="Orphelins"), R("orph_nh", "Non handicapés", groupe="Orphelins")]
             + [R(k, lib, groupe="Enfants handicapés") for k, lib in _HANDI]
             + [R("htot", "Total Enfants handicapés", groupe="Enfants handicapés", total=[k for k, _ in _HANDI],
                  st="b")])
_PERS_M_COLS = [
    K("mat", "N° matricule (1)", "t", w=14), K("nip", "NIP", "t", w=17), K("nom", "Nom et Prénoms", "t", w=40),
    GR("PH", K("ph_o", "OUI", "c", v=True, w=5), K("ph_n", "NON", "c", v=True, w=5)),
    GR("sexe (2)", K("sx_m", "M", "c", w=4.5), K("sx_f", "F", "c", w=4.5)),
    K("naiss", "Année de naissance", "an", w=15),
    GR("Diplôme le plus élevé", K("dip_a", "acadé-mique", "t", w=13), K("dip_p", "profes-sionnel", "t", w=13)),
    K("grade", "Grade", "t", w=11), K("statut", "Statut (4)", "t", w=10), K("fonction", "Fonction", "t", w=15),
    K("qualite", "Qualité (5)", "t", w=14),
    GR("Section tenue", K("s_pe", "Section des Petits", "c", v=True, w=7), K("s_gr", "Section des Grands", "c", v=True,
                                                                          w=7)),
    K("indice", "Indice réel", "t", w=10), K("anc", "Ancienneté générale", "t", v=True, w=8),
    GR("Nombre de visites (6)", K("vis_i", "Inspecteur", "n", v=True, w=6), K("vis_cp", "CP", "n", v=True, w=6),
       K("vis_d", "Directeur", "n", v=True, w=6), K("vis_pct", "% participation", "d", v=True, w=6)),
    GR("Formations", K("f_ls", "Langue des signes", "t", v=True, w=10), K("f_eb", "Ecriture braille", "t", v=True, w=10),
       K("f_pi", "Pédagogie inclusive", "t", v=True, w=10)),
]
_NOTES_PERS_M = [
    "(1) Pour les APE et ACE, indiquer le numéro matricule figurant sur la fiche de paie",
    "(2) Cocher \"M\" pour masculin et \"F\" pour féminin",
    "(3) Diplômes académiques (BEPC, BAC, LICENCE etc.) ou professionnels (CEAP, CAP, etc.) le plus élevé",
    "(4) C'est le statut de l'enseignant? Il peut être APE, ACE, AME, Contractuel Non Reversé (CNR), Stagiaire, "
    "PRIVE ou Autre",
    "(5) La Qualité peut être ''Instituteur'' ou ''Educateur'' (Voir Guide)",
    "(6) Il s'agit des inspections, contrôles et visites effectués par le personnel d'encadrement et le Directeur "
    "à l'enseignant au cours de l'année antérieure"]
_BM = [("bon", "Bon état"), ("mauv", "Mauvais état")]
_INFRA_COLS = [
    GR("Matériaux définitifs (murs et toitures)", K("def_b", "Bon état"), K("def_m", "Mauvais état")),
    GR("Murs en matériaux provisoires et toitures en matériaux définitifs", K("mix_b", "Bon état"),
       K("mix_m", "Mauvais état")),
    GR("Sous-Total", K("st_b", "Bon état", somme=["def_b", "mix_b"]), K("st_m", "Mauvais état", somme=["def_m", "mix_m"])),
    K("prov", "Murs et toitures en matériaux provisoires"), K("apatam", "Apatam"),
    K("sans", "Sans mur et sans toit"),
    K("total", "Total", somme=["st_b", "st_m", "prov", "apatam", "sans"]), K("cours", "Construction en cours"),
    GR("Rampe", K("r_anti", "antidérapant", v=True), K("r_main", "main courante", v=True),
       K("r_incl", "inclinaison de moins de 5°", v=True)),
]

SCHEMA_MATERNELLE = {
    "type": "maternelle", "titre": "FICHE DE RECENSEMENT ANNUEL DES ECOLES MATERNELLES",
    "titre_court": "Fiche de recensement annuel des écoles maternelles (EM inclusive)",
    "pied": "Recensement annuel des écoles maternelles", "pages_modele": 5, "georef": False,
    "admin": [TX("code_ecole", "Code école")],
    "sections": [
        S("1", "IDENTIFICATION ET LOCALISATION DE L'ETABLISSEMENT",
          L("1.1.", "Ecole Maternelle", NB("nom", n=27), st="cadre"),
          L("1.2.", "Année de création :", NB("creation_an", n=4), TX("creation_ref", "Référence :", w=60),
            TX("creation_du", "du", w=30)),
          L("1.3.", "Année dernière extension :", NB("extension_an", n=4), TX("extension_ref", "Référence :", w=55),
            TX("extension_du", "du", w=30)),
          L("1.4.", "Statut :", CH("statut", ["Public", "Communautaire", "Privé Laïc", "Privé Confessionnel"])),
          L("1.5.", "Type :", CH("type_ens", ["Classique", "Inclusif", "Spécialisé", "Autres :"]),
            TX("type_preciser", "Préciser :", w=30)),
          L("1.6.", "Localisation dans le Réseau d'Animation Pédagogique :"),
          L("", "i. Circonscription Scolaire :", TX("cs", w=110), ind=6),
          L("", "ii. Zone Pédagogique :", CH("zone", ["1", "2", "3", "4", "5", "6"]), ind=6),
          L("", "iii. Unité Pédagogique :", TX("up", w=110), ind=6),
          L("1.7.", "Localisation dans l'Administration Territoriale :"),
          L("", "i. Département :", TX("departement", w=115), ind=6),
          L("", "ii. Commune :", TX("commune", w=115), ind=6),
          L("", "iii. Arrondissement :", TX("arrondissement", w=110), ind=6),
          L("", "iv. Village ou Quartier de ville :", TX("village", w=100), ind=6),
          L("", "v. Adresse :", TX("adresse", w=30), TX("bp", "BP.", w=16), TX("ville", "Ville", w=28),
            TX("telephone", "Téléphone", w=34), ind=6),
          L("", "vi. Adresse mail", TX("email", w=70), ind=6),
          onglet="1. Identification"),
        S("2", "RENSEIGNEMENTS GENERAUX",
          C2([L("2.1.", "Effectifs de l'école.", st="b"),
              T("t21", [K("m", "M"), K("f", "F"), K("t", "T", somme=["m", "f"]),
                        GR("PH", K("ph_m", "M"), K("ph_f", "F"), K("ph_t", "T", somme=["ph_m", "ph_f"]))],
                [R("enfants", "Enfants"), R("instit", "Instituteurs"), R("educ", "Educateurs"),
                 R("soutien", "Personnel de soutien")], label_w=26, taille=7.5)],
             [L("2.2", "Nombre de sections et de salles de classes", st="b"),
              L("", "Nombre de sections existantes :", NB("sections_existantes", n=2)),
              L("", "Nombre de sections autorisées :", NB("sections_autorisees", n=2)),
              L("", "Nombre de salles de classes existantes :", NB("salles_existantes", n=2)),
              L("", "Nombre de salles de classes utilisées :", NB("salles_utilisees", n=2))], ratio=0.5),
          L("2.3.", "Environnement de l'école:", st="b"),
          L("", "L'école est-elle accessible toute l'année ?", ON("accessible"),
            TX("accessible_periode", "Si non, précisez la période favorable :", w=25)),
          L("", "vii. L'école est-elle accessible à tout enfant handicapé ?", ON("acces_handicape")),
          L("", "L'école est-elle inondable ?", ON("inondable"), TX("inondable_periode", "Si oui, précisez la période :",
                                                                     w=25)),
          P("Dispose t-elle :   Oui Non   Si Oui préciser à chaque fois si nécessaire (Autres à préciser)", st="i"),
          L("", "- d'eau potable ?", ON("eau"), CH("eau_src", ["SONEB", "Forage", "Puits", "Citerne", "Autre"],
                                                   multi=True), TX("eau_autre", w=15), ind=2),
          L("", "- d'électricité ?", ON("electricite"), CH("electricite_src", ["SBEE", "Groupe electrogène",
                                                                             "Energie solaire", "Autre"], multi=True),
            TX("electricite_autre", w=15), ind=2),
          L("", "- d'une cantine ?", ON("cantine"), CH("cantine_src", ["PAM", "Gouvernementale", "CRS", "Autre"],
                                                        multi=True), TX("cantine_autre", w=15), ind=2),
          L("", "- de latrines ?", ON("latrines"), NB("latrines_modules", "Nombre de modules :", n=2),
            NB("latrines_isoloirs", "Nombre d'isoloirs", n=2), ind=2),
          L("", "Si oui dispose t-elle des latrines handi sexospécifiques ?", ON("latrines_handi"), st="p"),
          L("", "- dispositifs de lavage de mains ?", ON("lavage"), CH("lavage_src", [
              "Lavabo", "Tip Tap", "Circuit de lavage de mains"], multi=True), ind=2),
          L("", "", TX("lavage_autre", "Autre (Précisez)", w=80), ind=60),
          L("", "- d'un titre de propriété ?", ON("titre"), CH("titre_src", [
              "Titre foncier", "Acte de l'autorité administrative", "Acte de Donation", "Location", "Autre"],
              multi=True), TX("titre_autre", w=12), ind=2),
          SAUT(),
          P("L'école dispose-t-elle :", ind=2),
          L("", "- de clôture ?", ON("cloture"), ind=4),
          L("", "- d'une boite à pharmacie?", ON("pharmacie"), ind=4),
          L("", "- d'aire de jeu ?", ON("aire_jeu"), ind=4),
          L("", "- salle de classe adaptée aux personnes handicapées ?", ON("salle_adaptee"), ind=4),
          L("", "- d'une structure de gestion collégiale?", ON("gestion_collegiale"),
            "Si oui, cocher la case correspondante", ind=4),
          L("", "", CH("gestion_structures", ["APE", "AME", "Comité de direction", "Comité de santé", "Autres"],
                       multi=True), TX("gestion_autre", "préciser", w=30), ind=4),
          L("", "vi. Y-a-t-il de parents d'enfant handicapé au sein du bureau APE ?", ON("ape_parents_handi"), ind=4),
          L("", "vii. Y-a-t-il de personnes handicapées au sein du bureau APE ?", ON("ape_personnes_handi"), ind=4),
          L("", "L'environnement de l'école est-il pollué?", ON("pollue"), "Si oui, cocher la case correspondante",
            ind=4),
          L("", "", CH("pollution", ["i Sonore", "ii Atmosphérique"], multi=True),
            TX("pollution_autre", "iii Autre (Précisez)", w=35), ind=4),
          L("2.4.", "Ecole environnante / Centre de santé environnant"),
          T("t24", [K("d05", "≤ 0,5 Km", "c"), K("d1", "entre 0,5 et 1 Km", "c"), K("d3", "entre 1 et 3 Km", "c"),
                    K("dp3", "> 3 Km", "c")],
            [R("ep", "Distance avec la plus proche école primaire"),
             R("sante", "Distance avec le plus proche centre de santé")], label_w=62, largeur=160, taille=7.5),
          L("2.5.", "Langue utilisée pendant les activités d'éveil et de stimulation"),
          L("", "Français", ON("l_francais"), ind=2), L("", "Anglais", ON("l_anglais"), ind=2),
          L("", "Arabe", ON("l_arabe"), ind=2), L("", "Langue des signes", ON("l_signes"), ind=2),
          L("", "Autres langues", ON("l_autres"), TX("l_autres_p", "si oui, precisez", w=30), ind=2),
          L("", "Langue nationale", ON("l_nationale"), TX("l_nationale_p", "si oui, precisez", w=30), ind=2),
          onglet="2. Renseignements généraux"),
        S("3", "REPARTITION DES ENFANTS PAR SECTION ET PAR AGE",
          T("t3", _T3M_COLS, _T3M_ROWS, label_w=34, taille=6.5),
          onglet="3. Enfants par section et âge"),
        S("4", "STRUCTURE PEDAGOGIQUE",
          T("t4", [K("pe", "Nombre de sections des petits"), K("gr", "Nombre de sections des grands"),
                   K("salles", "Nombre de salles de classe")],
            [R("simple", "Simple"), R("jumelee", "Jumelée"), R("multi", "Multigrade", span={"pe": 2}, grise={"gr"})],
            label_w=50, largeur=150, taille=8, ind=10),
          onglet="4. Structure pédagogique"),
        S("5", "MATERIEL PEDAGOGIQUE",
          T("t5", [K("prog", "Programmes d'activites"), K("guides", "Guides pédagogiques"),
                   K("recueils", "Recueils de jeux"), K("specifiques", "Matériels spécifiques"), K("autres", "Autres")],
            [R("nombre", "Nombre", st="b")], label_w=30, largeur=150, taille=8),
          onglet="5. Matériel pédagogique"),
        SAUT(paysage=True),
        S("6", "ETAT NOMINATIF DU PERSONNEL ENSEIGNANT",
          T("t6", _PERS_M_COLS, [], coin="N° d'ordre", label_w=7, taille=6.5, label_v=True,
            dyn={"min": 12, "fonction": "fonction", "premier": "Directeur", "autres": "Adjoint"}, h_ligne=5.4),
          *[P(n, st="p") for n in _NOTES_PERS_M],
          onglet="6. Personnel enseignant"),
        S("7", "Etat nominatif du personnel de soutien",
          T("t7", [K("nip", "NIP", "t", w=22), K("nom", "Nom et prenoms", "t", w=60), GR("PH", K("ph_o", "O", "c", w=4.5), K("ph_n", "N", "c", w=4.5)),
                   GR("Sexe", K("sx_m", "M", "c", w=4.5), K("sx_f", "F", "c", w=4.5)), K("fonction", "Fonction", "t", w=48),
                   K("age", "Age", "n", w=15), K("statut", "Statut", "t", w=20)],
            [], coin="N° ordre", label_w=8, taille=7.5, label_v=True, dyn={"min": 6}),
          onglet="7. Personnel de soutien"),
        SAUT(),
        S("8", "ETAT DES INFRASTRUCTURES (mentionner chaque fois le nombre correspondant)",
          T("t8", _INFRA_COLS, [R("salle", "Salle de classe"), R("bureau", "Bureau (Direction)"),
                                R("magasin", "Magasin de rangement"), R("vivres", "Magasin de vivres"),
                                R("biblio", "Bibliothèque"), R("latrine", "Latrine"), R("cuisine", "Cuisine")],
            label_w=20, taille=6.5, h_ligne=7),
          L("", "Observations éventuelles sur les locaux", TX("obs_locaux", w=170, lignes=3)),
          onglet="8. Infrastructures"),
        S("9", "ETAT DU MOBILIER (mentionner chaque fois le nombre correspondant)",
          T("t9", [K(k, lib, v=True) for k, lib in [
              ("bureaux", "Bureaux enseignant"), ("chaises_ens", "Chaises enseignant"), ("armoires", "Armoires et placards"),
              ("tables_jeux", "Tables de jeux"), ("tables_enf", "Tables pour enfants"),
              ("tab_chevalet", "Tableaux sur chevalet"), ("tab_muraux", "Tableaux muraux"),
              ("tabourets", "Tabourets pour enfants"), ("chaises_enf", "Chaises pour enfants"), ("nattes", "Nattes"),
              ("matelas", "Matelas"), ("table_adapt", "Table adaptée"), ("chaise_adapt", "Chaise adaptée")]],
            [R(k, lib) for k, lib in _BM], label_w=26, taille=6.5),
          onglet="9. Mobilier"),
        S("10", "EQUIPEMENTS",
          L("10.1", "Equipements extérieurs ( mentionner chaque fois le nombre correspondant )", st="b", ind=10),
          T("t101", [K(k, lib, v=True) for k, lib in [
              ("tourniquet", "Tourniquet"), ("cage", "Cage à écureuil"), ("escalier", "Escalier de géants"),
              ("tobogan", "Tobogan"), ("balancoire", "Balançoire"), ("corde", "Corde à grimper"), ("bac_eau", "Bac à eau"),
              ("bac_sable", "Bac à sable"), ("echelle", "Echelle à grimper"), ("tunnel", "Tunnel avec pneus"),
              ("poutre", "Poutre"), ("autres", "Autres"), ("adaptes", "Equipements adaptés")]],
            [R(k, lib, st="b") for k, lib in _BM], label_w=20, taille=6.5),
          L("10.2", "Equipements intérieurs ( mentionner chaque fois le nombre correspondant )", st="b", ind=10),
          T("t102", [K(k, lib, v=True) for k, lib in [
              ("peinture", "Piste de Peinture"), ("encastrement", "Encastrement"), ("puzzle", "Puzzle"),
              ("ordinateur", "Ordinateur"), ("television", "Télévision"), ("graphisme", "Matériel de graphisme"),
              ("presentoir", "Présentoir"), ("cube", "Cube"), ("cubarythme", "Cubarythme"), ("loupe", "Loupe"),
              ("poincon", "Poinçon"), ("tablette", "Tablette"), ("teleagr", "Téléagrandisseur"), ("imagier", "Imagier"),
              ("grille", "Grille")]],
            [R(k, lib, st="b") for k, lib in _BM], label_w=20, taille=6.5),
          P("Autres Equipements adaptés"),
          L("", "Formes solides", NB("formes_solides", n=2), ind=24),
          L("", "Autres", NB("eq_adaptes_autres", n=2), ind=24),
          onglet="10. Équipements"),
        SAUT(),
        S("11", "DONNEES FINANCIERES",
          L("11.1", "Montant du budget exécuté l'année précédente", MT("budget_execute"), ind=14),
          L("11.2", "Elements constitutifs du budget de l'année en cours", ind=14),
          L("", "i. Solde exercice antérieur", MT("b_solde"), ind=22),
          L("", "ii. Montant de la subvention de l'Etat", MT("b_subvention"), ind=22),
          L("", "iii. Montant de la cotisation des parents d'élèves", MT("b_cotisation"), ind=22),
          L("", "iv. Autres ressources", MT("b_autres"), ind=22),
          L("", "TOTAL BUDGET (i + ii + iii + iv)",
            MT("b_total", somme=["b_solde", "b_subvention", "b_cotisation", "b_autres"]), ind=40, st="b"),
          L("11.3", "Implication de l'APE dans la gestion de l'Ecole", ind=14),
          L("", "i. Nombre d'AG effectivement tenues (année précédente)", NB("nb_ag", n=2), ind=14),
          L("", "ii. Nombre de réunion tenues avec le bureau APE (année précédente)", NB("nb_reunions", n=2), ind=14),
          L("", "iii. L'école dispose-t-elle d'un projet de développement inclusif ?", ON("projet_inclusif"), ind=14),
          L("", "Date de remplissage :", TX("date_remplissage", w=100), ind=14),
          L("", "Par Madame / Monsieur", TX("rempli_par", w=100), ind=14),
          L("", "Fonction :", TX("rempli_fonction", w=110), ind=14),
          SIGNATURES("maternelle"),
          onglet="11. Données financières"),
    ],
}

SCHEMAS = {"primaire": SCHEMA_PRIMAIRE, "maternelle": SCHEMA_MATERNELLE}

# Guide de remplissage (pages 9 à 13 du modèle primaire), reproduit intégralement --------------------------
GUIDE_PRIMAIRE = [
    ("h0", "Présentation de la fiche"),
    ("p", "Le questionnaire de recensement des Ecoles Primaires (EP) est composé de douze (12) rubriques. Pour chaque "
          "rubrique, les indications ci-après facilitent la compréhension et le remplissage de ce questionnaire."),
    ("p", "<b>NB :</b> Le code et le géo référencement sont réservés à l'administration."),
    ("h", "1. IDENTIFICATION ET LOCALISATION DE L'ETABLISSEMENT"),
    ("p", "Elle permet de situer l'école dans sa structure administrative, son réseau d'animation pédagogique et "
          "d'avoir les informations relatives à son statut et au type d'enseignement."),
    ("p", "<b>Point 1.1</b> : « Nom de l'école ». On inscrira directement le nom de l'école, en caractère "
          "d'imprimerie, un caractère par case."),
    ("p", "<b>Point 1.2</b> : « Année de création » : il s'agit de l'année de création de l'école et les références "
          "de l'acte de création s'il en existe."),
    ("p", "<b>Point 1.3</b> : « Année dernière extension » : il s'agit de l'année de la dernière extension de classes "
          "et les références de l'acte l'accordant, s'il en existe."),
    ("p", "<b>Point 1.4 :</b> « Statut » : Cocher le statut de l'école. Le statut ''communautaire'' est réservé aux "
          "écoles créées par la communauté sans ou avec l'appui des ONGs."),
    ("p", "<b>Point 1.5 :</b> « Type » : Cocher le type d'enseignement de l'école. Le type ''inclusif'' est réservé "
          "aux écoles ayant en son sein aussi bien les enfants à besoins spécifiques que les enfants à besoins "
          "ordinaires et partagent les mêmes types d'enseignement. Le type spécialisé est coché lorsque "
          "l'enseignement est spécifique : réservé exclusivement aux besoins spécifiques des enfants qui s'y trouvent."),
    ("p", "<b>Points 1.6 et 1.7 :</b> Ces points permettent de situer l'école dans sa structure administrative et "
          "dans son réseau d'animation pédagogique."),
    ("h", "2. ENVIRONNEMENT SOCIO-ECONOMIQUE"),
    ("s", "Point 2.1 Distance de l'école"),
    ("p", "Indiquer les distances en kilomètre séparant le centre du point identifié (i à vii)"),
    ("s", "Point 2.2 : Accessibilité"),
    ("p", "Ce point permet d'avoir l'information sur l'état, la nature de la route de la circonscription scolaire au "
          "centre. La somme des distances indiquées selon l'état de la route doit donner la distance initialement "
          "indiquée au 2.1, iv."),
    ("p", "Il renseigne aussi sur l'accessibilité permanente ou non à l'école. Au cas où l'accessibilité ne serait "
          "pas permanente, le directeur précise la période favorable."),
    ("p", "Les caractéristiques de la voie de l'école au bureau de la CS permet d'éclater la distance inscrite au "
          "2.1 – iv en tenant compte des moyens de transport appropriés pour y avoir accès. Autrement dit, la somme "
          "des distances selon les caractéristiques du tronçon doit donner la distance inscrite au 2.1 – iv"),
    ("p", "Par ailleurs ce point indique la possibilité d'accessibilité à tout enfant handicapé."),
    ("s", "Point 2.3 : Inondation"),
    ("p", "Il s'agit d'apprécier le risque pour l'école de connaitre le phénomène d'inondation avec les pluies ou en "
          "fonction de certains phénomènes climatiques cycliques."),
    ("s", "Point 2.4 : Alimentation en énergie"),
    ("p", "Cocher la case correspondante pour dire si l'école est alimentée ou non et le type d'énergie."),
    ("s", "Point 2.5 : Etablissements scolaires environnants"),
    ("p", "Il s'agit de préciser les établissements scolaires (EM, EP, CEG ou lycée) environnants et leur distance "
          "par rapport à l'école."),
    ("s", "Point 2.6 : Approvisionnement de la localité en eau potable"),
    ("p", "Il s'agit de mettre une croix dans la case correspondante à la source d'approvisionnement de la localité "
          "en eau potable."),
    ("p", "N.B : préciser d'autres sources dans « Autres » s'il en existe"),
    ("s", "Point 2.7 : L'environnement de l'école est-il pollué ?"),
    ("p", "Cocher la case correspondante. « Sonore » pour les environnements trop bruyants (proximité d'une buvette "
          "bruyante, scierie, etc.). « Atmosphérique » pour les environnements avec odeur nauséabonde d'ordures, "
          "poussière permanente, etc."),
    ("h", "3. INFORMATIONS GENERALES SUR L'ECOLE"),
    ("p", "Il faut cocher les cases correspondantes. Toutefois, certaines clarifications sont nécessaires pour "
          "certains points :"),
    ("s", "Point 3.12 : L'école a-t-elle :"),
    ("p", "On dira qu'un terrain de sport est équipé lorsque certains équipements y sont à savoir : (Ballons, Corde à "
          "grimper, corde à sauter, etc.)."),
    ("s", "Point 3.14 : Structure pédagogique"),
    ("p", "Simples : on inscrira le nombre de cours existants, occupant chacun un local."),
    ("p", "Jumelées : on inscrira les cours de même niveau occupant ensemble un même local. On précisera 1 pour "
          "chaque cours."),
    ("p", "Multigrades : on mentionnera ici les cours de niveaux différents occupent le même local. On précisera 1 "
          "pour chaque cours."),
    ("s", "Point 3.15 : Données sur les classes et salles de classe"),
    ("p", "On entend par classes autorisées un cours autorisé."),
    ("p", "On entend par classe existante un cours existant."),
    ("p", "On entend par salles de classe existantes, salles de classe en thème de local appartenant à l'école."),
    ("p", "On entend par salles de classe utilisées, salles de classe en thème de local utilisées."),
    ("p", "NB : Le nombre de salles de classe utilisées de la structure pédagogique est le même que celui du 3.15"),
    ("s", "Point 3.16 : Langues d'enseignements"),
    ("p", "Il ne s'agit pas des langues qui sont apprises mais celles utilisées pour l'enseignement. Il est possible "
          "que plusieurs langues soient utilisées."),
    ("h", "4. CARACTERISTIQUES ET ETAT DES LOCAUX"),
    ("p", "Il s'agit de mentionner conformément aux tableaux, pour chaque local de l'école les caractéristiques "
          "réelles. Faites attention à la colonne ''cocher si la salle n'est pas utilisée''. Si en effet une salle de "
          "classe n'est pas utilisée, il faudra nécessairement cocher."),
    ("h", "5. CARACTERISTIQUES DU MOBILIER"),
    ("p", "Il s'agit de remplir conformément aux tableaux, le nombre de meubles selon le type, la nature et leur "
          "état. Il faut prendre en compte ici les salles de classe utilisées. Faites attention à la colonne mobilier "
          "adapté. Il s'agit de renseigner le mobilier adapté pour les enfants handicapés."),
    ("h", "6. EQUIPEMENTS DIDACTIQUES ET PEDAGOGIQUES"),
    ("p", "Renseigner le nombre par matériel, ouvrage et manuel selon chaque niveau. Il s'agit des équipements "
          "utilisés à titre pédagogique. Ainsi par exemple si un ordinateur n'est pas utilisé à titre pédagogique, il "
          "ne doit pas être compté."),
    ("s", "Point 6.1.2 Equipements adaptés"),
    ("p", "Il s'agit de rendre compte du nombre disponibles d'équipements adaptés aux enfants handicapés."),
    ("s", "Point 6.1.2 Manuels adaptés"),
    ("p", "Il s'agit de rendre compte du nombre disponibles d'équipements adaptés aux enfants handicapés."),
    ("h", "7. EFFECTIFS DES APPRENANTS"),
    ("s", "Point 7.1 Effectif global"),
    ("p", "Il s'agit de rendre compte de l'effectif global de l'école selon le genre."),
    ("s", "Point 7.2 Nouveaux inscrits au CI selon le genre et par âge"),
    ("p", "Il suffit de renseigner l'effectif des nouveaux apprenants qui se sont inscrits au CI dans l'école."),
    ("s", "Point 7.3 répartition des élèves par âge, par année d'étude et selon le genre"),
    ("p", "Indiquer par âge et par genre et année d'études les effectifs de l'école. Vérifier que le total au niveau "
          "de « ENSEMBLE » est conforme à l'effectif selon le genre mentionné au 7.1"),
    ("p", "Mentionner le nombre de redoublants et d'étrangers<super>1</super> par cours sur les lignes "
          "correspondantes."),
    ("p", "Au niveau de la ligne « dont orphelins ou enfants vulnérables<super>2</super> », il s'agit de mettre par "
          "niveau le nombre d'orphelins, de handicapés ou des enfants vulnérables de l'école."),
    ("p", "« Dont Handicapés » permet de classer les enfants handicapés selon leur handicape. Les définitions sont "
          "en bas de page : « Moteur », « Visuel », « Auditif », « Intellectuel »."),
    ("p", "- La vulnérabilité ici s'appliquera aux enfants ayant perdu la protection de leur famille immédiate. Du "
          "coup, ils courent un grand risque de devenir des victimes de la violence, de l'exploitation, de la traite, "
          "de la discrimination ou d'autres formes de mauvais traitements. Il ne faut confondre pauvreté et "
          "vulnérabilité."),
    ("p", "- Le handicap moteur se caractérise par une capacité limitée pour un individu de se déplacer, de réaliser "
          "des gestes, ou de bouger certains membres. L'atteinte à la motricité peut être partielle ou totale, "
          "temporaire ou incurable, selon son origine."),
    ("p", "- Le handicap visuel : qui sous-entend une déficience de la fonction visuelle Exemples : cécité et "
          "malvoyance, amblyopie, achromatopsie..."),
    ("p", "- Le handicap auditif : qui désigne une perte partielle (mal entendant) ou totale de l'audition. Un "
          "handicap qui peut parfois entraîner des troubles de la parole. Exemple : surdité"),
    ("p", "- Le handicap intellectuel est caractérisé par un fonctionnement intellectuel sensiblement inférieur à la "
          "moyenne associée à des limitations du fonctionnement adaptatif : communication, autonomie, conséquences "
          "sociales, prise en charge de la personne par elle-même, le besoin démontré de soutien."),
    ("n", "<super>1</super> Les étrangers fait référence aux enfants non Béninois"),
    ("h", "8- ETAT NOMINATIF DU PERSONNEL ENSEIGNANT"),
    ("p", "Il s'agit ici de fournir conformément au tableau les renseignements relatifs aux enseignants de l'école :"),
    ("p", "(1) « Matricule » : le matricule des instituteurs sera noté lorsqu'il s'agit d'APE et ACE."),
    ("p", "(2) « Sexe » marquer M pour Masculin et F pour Féminin"),
    ("p", "(3) « Diplôme académique » : noter le diplôme académique (BEPC, BAC, Licence, Etc.) et professionnel "
          "(CEAP/EP, CAP/EP, etc.) le plus élevé de l'enseignant."),
    ("p", "(5) « Nombre de visites » : indiquer le nombre de visites effectuées l'année scolaire antérieure par "
          "l'inspecteur, le Conseiller Pédagogique ou le directeur de l'école."),
    ("p", "(6) « % participation aux UP » : Ce pourcentage est obtenu en faisant le rapport de nombre de "
          "participations de l'enseignant aux UP (l'année antérieure) sur le nombre total d'UP (Année antérieure) "
          "x 100."),
    ("h", "9- RESULTATS AUX EXAMENS DE LA DERNIERE SESSION"),
    ("p", "Il s'agit de donner des renseignements sur les résultats de l'examen du Certificat d'Etudes Primaire (CEP) "
          "de l'année scolaire antérieure."),
    ("h", "10- ETAT NOMINATIF DU PERSONNEL DE SOUTIEN"),
    ("p", "Il s'agit de remplir suivant les indicateurs de chaque colonne."),
    ("h", "11- GESTION PARTICIPATIVE DE L'ECOLE"),
    ("p", "Il s'agit de fournir les informations relatives aux instances de gestion collégiale de l'école (Bureau APE "
          "et Assemblée Générale) et les sujets généralement à l'ordre du jour des réunions pour l'année scolaire "
          "précédente."),
    ("h", "12. DONNEES FINANCIERES"),
    ("s", "Montant du budget exécuté l'année précédente"),
    ("p", "Indiquer le montant prévisionnel alloué à l'école pour l'année en cours."),
    ("s", "Montant de l'année en cours"),
    ("p", "(i) Solde de l'exercice antérieur"),
    ("p", "(ii) Montant de la subvention reçue de l'Etat"),
    ("p", "(iii) Montant de la cotisation des parents d'élèves"),
    ("p", "(iv) Autres ressources (souscriptions, dons, legs, etc)."),
    ("p", "Total Budget : faire la somme de (i)+(ii)+(iii)+(iv)."),
]


# ============================================================================ outils sur les schémas
TYPES = {"primaire": "École primaire (EP)", "maternelle": "École maternelle inclusive (EM)"}
NUMERIQUES_CHAMP = ("nb", "mt")
NUMERIQUES_CELLULE = ("n", "d", "an")
RE_ANNEE = re.compile(r"^(\d{4})-(\d{4})$")


def sections(schema):
    return [s for s in schema["sections"] if "items" in s]


def _aplatir(it):
    if it["i"] == "C2":
        for x in it["g"] + it["d"]:
            yield from _aplatir(x)
    else:
        yield it


def elements(schema):
    for s in sections(schema):
        for it in s["items"]:
            for x in _aplatir(it):
                yield s, x


def champs_simples(schema):
    """[(section, ligne, champ)] dans l'ordre du modèle (champs réservés à l'administration en premier)."""
    out = [(None, None, f) for f in schema["admin"]]
    for s, it in elements(schema):
        if it["i"] in ("L", "G"):
            out += [(s, it, ch) for ch in it["champs"] if isinstance(ch, dict)]
    return out


def tableaux(schema):
    return [(s, it) for s, it in elements(schema) if it["i"] == "T"]


def feuilles(cols):
    out = []
    for c in cols:
        out += feuilles(c["sub"]) if c.get("sub") else [c]
    return out


def profondeur(cols):
    return max((1 + profondeur(c["sub"])) if c.get("sub") else 1 for c in cols)


def chemins(cols, parent=""):
    """{clé de colonne: « Groupe › Sous-groupe › Colonne »}"""
    out = {}
    for c in cols:
        nom = f"{parent} › {c['lib']}" if parent else c["lib"]
        if c.get("sub"):
            out.update(chemins(c["sub"], nom))
        else:
            out[c["k"]] = nom
    return out


def lignes_tableau(t, n=None):
    if not t["dyn"]:
        return t["rows"]
    return [R(str(i), str(i)) for i in range(1, max(t["dyn"]["min"], n or 0) + 1)]


def entete_cellules(cols, depth):
    """Cellules d'en-tête [(ligne, colonne, nb lignes, nb colonnes, libellé, vertical)] (colonnes = feuilles)."""
    out = []

    def placer(noeuds, niveau, col):
        for n in noeuds:
            if n.get("sub"):
                larg = len(feuilles(n["sub"]))
                out.append((niveau, col, 1, larg, n["lib"], False))
                placer(n["sub"], niveau + 1, col)
                col += larg
            else:
                out.append((niveau, col, depth - niveau, 1, n["lib"], bool(n.get("v"))))
                col += 1
        return col
    placer(cols, 0, 0)
    return out


def libelle_champ(s, it, ch):
    parts = [it.get("num", ""), it.get("texte", "")] if it else []
    if ch.get("lib"):
        parts.append(ch["lib"])
    txt = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip(" :")
    return txt or ch["k"]


def nombre(v):
    """'12', '12,5', '1 250 000' -> float ; None si vide ou invalide."""
    if v is None or isinstance(v, (list, dict, bool)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt(x):
    if x is None:
        return ""
    x = float(x)
    return str(int(x)) if x.is_integer() else f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def milliers(v):
    x = nombre(v)
    if x is None:
        return str(v or "")
    return f"{int(round(x)):,}".replace(",", " ")


def vide(v):
    return v is None or v == "" or v == []


class Index:
    """Index des clés d'un schéma : champs simples, cellules des tableaux fixes, tableaux dynamiques."""

    def __init__(self, schema):
        self.simples = {ch["k"]: (s, it, ch) for s, it, ch in champs_simples(schema)}
        self.cellules, self.dyn, self.tables = {}, {}, {}
        for s, t in tableaux(schema):
            leaves = {c["k"]: c for c in feuilles(t["cols"])}
            self.tables[t["k"]] = (s, t)
            if t["dyn"]:
                self.dyn[t["k"]] = (s, t, leaves)
                continue
            for r in t["rows"]:
                for ck, c in leaves.items():
                    self.cellules[f"{t['k']}.{r['k']}.{ck}"] = (s, t, r, c)

    def definition(self, k):
        """('champ', ch) | ('cellule', colonne) | (None, None)"""
        if k in self.simples:
            return "champ", self.simples[k][2]
        if k in self.cellules:
            return "cellule", self.cellules[k][3]
        m = re.match(r"^([a-z0-9]+)\.(\d{1,2})\.([a-z0-9_]+)$", k)
        if m and m.group(1) in self.dyn and 1 <= int(m.group(2)) <= 60 and m.group(3) in self.dyn[m.group(1)][2]:
            return "cellule", self.dyn[m.group(1)][2][m.group(3)]
        return None, None


_INDEX = {}


def index(typ):
    if typ not in _INDEX:
        _INDEX[typ] = Index(SCHEMAS[typ])
    return _INDEX[typ]


def libelle_cle(typ, k):
    """Libellé lisible d'une clé (messages, Excel)."""
    idx = index(typ)
    if k in idx.simples:
        s, it, ch = idx.simples[k]
        lib = libelle_champ(s, it, ch)
        return f"Rubrique {s['num']} – {lib}" if s and not (it and it.get("num")) else lib
    parts = k.split(".")
    if len(parts) == 3 and parts[0] in idx.tables:
        s, t = idx.tables[parts[0]]
        if t["dyn"]:
            rl = f"ligne {parts[1]}"
        else:
            r = next((r for r in t["rows"] if r["k"] == parts[1]), None)
            rl = ((r["groupe"] + " › ") if r and r["groupe"] else "") + (r["lib"] if r else parts[1])
        return f"Rubrique {s['num']} – {rl} / {chemins(t['cols']).get(parts[2], parts[2])}"
    return k


def valider_saisies(typ, brut):
    """Nettoie les valeurs reçues (formulaire, JSON, Excel). Retourne (propres, erreurs, inconnues).
    Conventions : texte/nombre vide = valeur calculée ; case : '1' cochée, '0' décochée volontairement ;
    choix multiple : liste (éventuellement vide)."""
    idx, propres, erreurs, inconnues = index(typ), {}, [], 0
    for k, v in (brut or {}).items():
        k = str(k)
        kind, d = idx.definition(k)
        if not kind:
            inconnues += 1
            continue
        t = d["t"]
        multi = kind == "champ" and t == "ch" and d["multi"]
        if isinstance(v, list):
            if multi:
                propres[k] = [o for o in d["opts"] if o in {str(x) for x in v}]
                continue
            v = v[-1] if v else ""
        if isinstance(v, bool):
            v = "1" if v else "0"
        v = "" if v is None else (fmt(v) if isinstance(v, (int, float)) else str(v)).strip()[:400]
        if v == "":
            continue
        lib = libelle_cle(typ, k)
        if (kind == "champ" and t in NUMERIQUES_CHAMP) or (kind == "cellule" and t in NUMERIQUES_CELLULE):
            x = nombre(v)
            if x is None or x < 0:
                erreurs.append(f"{lib} : « {v} » n'est pas un nombre positif.")
                continue
            if (t == "an" or k.endswith("_an")) and not (1900 <= x <= 2100 and x.is_integer()):
                erreurs.append(f"{lib} : année invalide « {v} ».")
                continue
            if (t in ("n", "an", "mt") or (t == "nb" and not d["dec"])) and not x.is_integer():
                erreurs.append(f"{lib} : un nombre entier est attendu (« {v} »).")
                continue
            if x > 10 ** 12:
                erreurs.append(f"{lib} : valeur trop grande.")
                continue
            v = fmt(x)
        elif multi:
            v = [o for o in d["opts"] if o in [x.strip() for x in v.split(";")]]
        elif kind == "champ" and t == "ch":
            if v not in d["opts"]:
                erreurs.append(f"{lib} : choix invalide « {v} ».")
                continue
        elif kind == "champ" and t == "on":
            v = {"oui": "Oui", "non": "Non"}.get(v.lower(), v)
            if v not in OUINON:
                erreurs.append(f"{lib} : répondre Oui ou Non.")
                continue
        elif (kind == "champ" and t == "case") or (kind == "cellule" and t == "c"):
            v = "1" if v.lower() in ("1", "x", "oui", "true", "on") else "0"
        propres[k] = v
    return propres, erreurs, inconnues


# ============================================================================ évaluation : saisie / calcul / contrôles
def nb_lignes_dyn(schema, saisies, auto):
    out = {}
    for _s, t in tableaux(schema):
        if t["dyn"]:
            n = 0
            for src in (saisies, auto):
                for k, v in src.items():
                    m = re.match(r"^" + t["k"] + r"\.(\d+)\.", k)
                    if m and not vide(v) and v != "0":
                        n = max(n, int(m.group(1)))
            out[t["k"]] = max(t["dyn"]["min"], min(n, 60))
    return out


def evaluer(schema, saisies, auto, dyn):
    """Valeurs effectives. Retourne (eff, calc, orig, alertes).
    eff : valeur retenue ; calc : valeur calculée (GESCOL ou total) ; orig : 'saisie' | 'calculée' | ''."""
    eff, calc, orig, alertes = {}, {}, {}, []

    def saisie(k):
        if k not in saisies:
            return None
        v = saisies[k]
        if isinstance(v, list):
            return v
        v = str(v).strip()
        return v if v else None

    def retenir(k, c, estcase=False, lib=None, somme=False):
        calc[k] = c
        v = saisie(k)
        if v is not None:
            eff[k] = ("" if v == "0" else "1") if estcase else v
            orig[k] = "saisie"
            if somme and not vide(c) and nombre(v) is not None and nombre(v) != nombre(c):
                alertes.append(f"{lib} : valeur saisie {v} différente du total calculé {c}.")
        else:
            eff[k] = c
            orig[k] = "calculée" if not vide(c) else ""

    def somme_de(cles):
        xs = [nombre(eff.get(x)) for x in cles]
        return fmt(sum(x for x in xs if x is not None)) if any(x is not None for x in xs) else ""

    simples = champs_simples(schema)
    for passe in (False, True):
        for s, it, ch in simples:
            if bool(ch.get("somme")) != passe:
                continue
            k = ch["k"]
            if passe:
                c = somme_de(ch["somme"])
            else:
                c = auto.get(k, "")
                if ch["t"] == "ch" and ch["multi"] and not isinstance(c, list):
                    c = [c] if c else []
            retenir(k, c, estcase=ch["t"] == "case", lib=libelle_champ(s, it, ch), somme=passe)
    for s, t in tableaux(schema):
        rows = lignes_tableau(t, dyn.get(t["k"]))
        leaves = feuilles(t["cols"])
        noms = chemins(t["cols"])
        for r in [r for r in rows if not r["total"]] + [r for r in rows if r["total"]]:
            for c in leaves:
                k = f"{t['k']}.{r['k']}.{c['k']}"
                if c["k"] in r["grise"] or (r["fusion"] and c["k"] in r["fusion"][0]):
                    eff[k] = calc[k] = orig[k] = ""
                    continue
                lib = f"Rubrique {s['num']} – {(r['groupe'] + ' › ') if r['groupe'] else ''}{r['lib']} / {noms[c['k']]}"
                if r["total"] and c["t"] in NUMERIQUES_CELLULE:
                    retenir(k, somme_de([f"{t['k']}.{x}.{c['k']}" for x in r["total"]]), lib=lib, somme=True)
                elif c.get("somme"):
                    retenir(k, somme_de([f"{t['k']}.{r['k']}.{p}" for p in c["somme"]]), lib=lib, somme=True)
                else:
                    retenir(k, auto.get(k, ""), estcase=c["t"] == "c", lib=lib)
    return eff, calc, orig, alertes


def controles(typ, eff, alertes_somme):
    """Contrôles de cohérence : totaux (G+F=T, lignes, colonnes), concordances entre rubriques, nombres."""
    out = list(alertes_somme)
    idx = index(typ)
    for k, v in eff.items():
        if vide(v):
            continue
        kind, d = idx.definition(k)
        if kind and ((kind == "champ" and d["t"] in NUMERIQUES_CHAMP)
                     or (kind == "cellule" and d["t"] in NUMERIQUES_CELLULE)) and nombre(v) is None:
            out.append(f"{libelle_cle(typ, k)} : « {v} » n'est pas un nombre.")

    def n(k):
        return nombre(eff.get(k))

    def egal(a, b, msg):
        if n(a) is not None and n(b) is not None and n(a) != n(b):
            out.append(f"{msg} ({fmt(n(a))} ≠ {fmt(n(b))}).")

    if typ == "primaire":
        egal("eff_m", "t73.tot.ens_g", "7.1 Masculin différent du Total ENSEMBLE G du 7.3")
        egal("eff_f", "t73.tot.ens_f", "7.1 Féminin différent du Total ENSEMBLE F du 7.3")
        egal("eff_t", "t73.tot.ens_t", "7.1 Total différent du Total ENSEMBLE T du 7.3")
        if n("t72.tot.t") is not None and n("t73.tot.ci_t") is not None and n("t72.tot.t") > n("t73.tot.ci_t"):
            out.append(f"7.2 : les nouveaux inscrits au CI ({fmt(n('t72.tot.t'))}) dépassent l'effectif total du CI "
                       f"au 7.3 ({fmt(n('t73.tot.ci_t'))}).")
        route = [n(k) for k in ("r_bitume", "r_piste", "r_4x4", "r_2roues", "r_pieds")]
        if n("d_cs") is not None and any(x is not None for x in route):
            tot = sum(x for x in route if x is not None)
            if abs(tot - n("d_cs")) > 0.05:
                out.append(f"2.2 : la somme des distances selon l'état de la route ({fmt(tot)} km) doit être égale à "
                           f"la distance au bureau de la CS du 2.1 iv ({fmt(n('d_cs'))} km).")
        sal = [n(f"t314.{r}.salles") for r in ("simples", "jumeles", "multi")]
        if n("salles_utilisees") is not None and any(x is not None for x in sal):
            tot = sum(x for x in sal if x is not None)
            if tot != n("salles_utilisees"):
                out.append(f"3.14 / 3.15 : le nombre de salles de classes utilisées de la structure pédagogique "
                           f"({fmt(tot)}) doit être le même que celui du 3.15 iv ({fmt(n('salles_utilisees'))}).")
        for niv in [x.lower() for x in NIV] + ["ens"]:
            for sx in ("g", "f", "t"):
                tot = n(f"t73.tot.{niv}_{sx}")
                if tot is not None and (n(f"t73.red.{niv}_{sx}") or 0) > tot:
                    out.append(f"7.3 : plus de redoublants que d'élèves ({niv.upper()} {sx.upper()}).")
    else:
        egal("t21.enfants.m", "t3.tot.ens_g", "2.1 Enfants M différent du Total Ensemble Masculin de la rubrique 3")
        egal("t21.enfants.f", "t3.tot.ens_f", "2.1 Enfants F différent du Total Ensemble Féminin de la rubrique 3")
        egal("t21.enfants.t", "t3.tot.ens_t", "2.1 Enfants T différent du Total Ensemble de la rubrique 3")
        egal("t21.enfants.ph_t", "t3.tot.eh_t", "2.1 Enfants PH différent du Total « Dont enfants handicapés » (3)")
    return list(dict.fromkeys(out))


# ============================================================================ remplissage automatique (GESCOL)
STATUTS = {"publique": "Public", "public": "Public", "privée": "Privé Laïc", "privee": "Privé Laïc",
           "confessionnelle": "Privé Confessionnel", "communautaire": "Communautaire"}
RE_ENS = re.compile(r"enseign|instit|direct|ma[iî]tre|adjoint|[ée]ducat|titulaire|professeur", re.I)
# Synthèse du patrimoine (module du collègue, si présent) : clé générique -> clé du champ par type de fiche
PATRIMOINE = {
    "salles_existantes": {"primaire": "salles_existantes", "maternelle": "salles_existantes"},
    "salles_utilisees": {"primaire": "salles_utilisees", "maternelle": "salles_utilisees"},
    "latrines": {"primaire": "latrines", "maternelle": "latrines"},
    "latrines_blocs": {"primaire": "latrines_blocs", "maternelle": "latrines_modules"},
    "latrines_cabines": {"primaire": "latrines_cabines", "maternelle": "latrines_isoloirs"},
    "cloture": {"primaire": "cloture", "maternelle": "cloture"},
    "point_eau": {"primaire": "point_eau", "maternelle": "eau"},
    "electricite": {"primaire": "electricite", "maternelle": "electricite"},
    "pharmacie": {"primaire": "pharmacie", "maternelle": "pharmacie"},
    "bibliotheque": {"primaire": "bibliotheque"},
    "bibliotheque_ouvrages": {"primaire": "bibliotheque_ouvrages"},
    "ordinateurs": {"primaire": "eq_ordi"}, "imprimantes": {"primaire": "eq_imprimantes"},
    "photocopieurs": {"primaire": "eq_photocop"},
}


def cycle_de(niveau):
    """('primaire', 'CI') | ('maternelle', 'pe'|'gr') | (None, None)"""
    n = (niveau or "").strip()
    if n in NIV:
        return "primaire", n
    low = n.lower()
    if low.startswith("maternelle") or "section" in low or "petit" in low or "grand" in low:
        return "maternelle", ("gr" if ("2" in low or "3" in low or "grand" in low) else "pe")
    return None, None


def age_mois(dn, ref):
    try:
        b = date.fromisoformat(str(dn)[:10])
    except (TypeError, ValueError):
        return None
    m = (ref.year - b.year) * 12 + ref.month - b.month - (1 if ref.day < b.day else 0)
    return m if m >= 0 else None


def date_reference(annee):
    """Âges calculés au 31 décembre de la seconde année de l'année scolaire
    (2026-2027 -> 31/12/2027), date de référence officielle."""
    return date(int(annee[:4]) + 1, 12, 31)


def ligne_age_primaire(mois):
    a = mois // 12
    return "a4" if a < 5 else ("a16" if a >= 16 else f"a{a}")


def ligne_age_ci(mois):
    if mois < 54:
        return "m45"
    if mois < 60:
        return "a45"
    a = mois // 12
    return "a9" if a >= 9 else f"a{a}"


def ligne_age_maternelle(mois):
    if mois < 30:
        return "m25"
    if mois < 36:
        return "a25"
    a = mois // 12
    return "p5" if a > 5 else f"a{a}"


def _pick(d, *noms):
    for n in noms:
        if d.get(n) not in (None, ""):
            return d[n]
    return ""


def _annees_depuis(v, ref):
    m = age_mois(v, ref)
    return str(m // 12) if m is not None else ""


def _vrai(v):
    return str(v).strip().lower() in ("1", "oui", "o", "true", "vrai", "x")


def calculs(H, typ, annee):
    """Valeurs calculées depuis GESCOL : ({clé: valeur}, [messages d'information])."""
    auto, infos = {}, []
    e = g.get("ecole")
    if e:
        e = dict(e)
        auto.update({k: v for k, v in {
            "nom": (e.get("nom") or "").upper(), "cs": e.get("cs") or "", "up": e.get("up") or "",
            "departement": e.get("departement") or "", "commune": e.get("commune") or "",
            "adresse": e.get("adresse") or "", "bp": e.get("bp") or "", "ville": e.get("ville") or "",
            "telephone": e.get("telephone") or "", "email": e.get("email") or "",
            "rempli_par": e.get("directeur_nom") or ""}.items() if v})
        st = STATUTS.get((e.get("statut") or "").strip().lower())
        if st:
            auto["statut"] = st
        z = re.search(r"[1-6]", e.get("zone") or "")
        if z:
            auto["zone"] = z.group(0)
        if typ == "maternelle":
            auto["rempli_fonction"] = e.get("directeur_titre") or "Directeur"
    auto["date_remplissage"] = date.today().strftime("%d/%m/%Y")
    eco = H.eco()
    classes = [dict(c) for c in H.q("SELECT * FROM classes WHERE ecole_id=? ORDER BY nom", (eco,))]
    mes_classes = [c for c in classes if cycle_de(c["niveau"])[0] == typ]

    def inc(k, n=1):
        auto[k] = fmt((nombre(auto.get(k)) or 0) + n)

    # --- classes / sections (structure pédagogique : chaque classe = un cours simple dans son local)
    if mes_classes:
        for c in mes_classes:
            inc(f"t314.simples.{c['niveau'].lower()}" if typ == "primaire" else f"t4.simple.{cycle_de(c['niveau'])[1]}")
        n = fmt(len(mes_classes))
        if typ == "primaire":
            auto.update({"t314.simples.salles": n, "classes_existantes": n, "salles_utilisees": n})
        else:
            auto.update({"t4.simple.salles": n, "sections_existantes": n, "salles_utilisees": n})
    # --- cantine (module Cantine : configuration validée pour au moins une classe du cycle)
    try:
        rows = H.q("SELECT c.niveau FROM cantine_config cc JOIN classes c ON c.id=cc.classe_id "
                   "WHERE c.ecole_id=? AND cc.valide=1 AND cc.montant_jour>0", (eco,))
        if any(cycle_de(r["niveau"])[0] == typ for r in rows):
            auto["cantine"] = "Oui"
            if typ == "primaire":
                auto["cantine_org"] = ["i. Gouvernement"] if config_publique(H) else []
    except Exception:  # noqa: BLE001 - module Cantine absent
        pass
    # --- élèves (année active seulement : GESCOL ne garde pas les effectifs par classe des années passées)
    if annee == H.config.ANNEE_ACTIVE:
        ref = date_reference(annee)
        ids = [c["id"] for c in mes_classes]
        eleves = []
        if ids:
            marque = ",".join("?" * len(ids))
            eleves = H.q(f"SELECT e.sexe, e.date_naissance, e.redoublant, c.niveau FROM eleves e "
                         f"JOIN classes c ON c.id=e.classe_id WHERE e.classe_id IN ({marque}) AND e.statut='inscrit'",
                         ids)
        sans_date = sans_sexe = 0
        for el in eleves:
            sx = {"M": "g", "F": "f"}.get((el["sexe"] or "").upper())
            if not sx:
                sans_sexe += 1
                continue
            niv = cycle_de(el["niveau"])[1]
            mois = age_mois(el["date_naissance"], ref)
            if typ == "primaire":
                inc("eff_m" if sx == "g" else "eff_f")
                col = f"{niv.lower()}_{sx}"
                if mois is None:
                    sans_date += 1
                else:
                    inc(f"t73.{ligne_age_primaire(mois)}.{col}")
                if el["redoublant"]:
                    inc(f"t73.red.{col}")
                    if mois is not None and mois // 12 in (6, 11):
                        inc(f"t73.red{mois // 12}.{col}")
                elif niv == "CI" and mois is not None:
                    inc(f"t72.{ligne_age_ci(mois)}.{sx}")
            else:
                inc(f"t21.enfants.{'m' if sx == 'g' else 'f'}")
                if mois is None:
                    sans_date += 1
                else:
                    inc(f"t3.{ligne_age_maternelle(mois)}.{niv}_{sx}")
        if sans_date:
            infos.append(f"{sans_date} élève(s) sans date de naissance : non compté(s) dans la répartition par âge.")
        if sans_sexe:
            infos.append(f"{sans_sexe} élève(s) sans sexe renseigné : non compté(s).")
        if not eleves:
            infos.append("Aucun élève inscrit dans les classes de ce cycle : effectifs à saisir.")
    else:
        infos.append(f"Les effectifs ne sont calculés automatiquement que pour l'année active "
                     f"({H.config.ANNEE_ACTIVE}) : pour {annee}, saisissez-les.")
    # --- personnel
    try:
        ens, sout = personnel(H, typ, date_reference(annee))
    except Exception as ex_:  # noqa: BLE001
        ens, sout = [], []
        infos.append(f"Personnel non lu ({ex_}).")
    tp, ts = ("t8", "t10") if typ == "primaire" else ("t6", "t7")
    for tab, lst in ((tp, ens[:60]), (ts, sout[:60])):
        for i, row in enumerate(lst, 1):
            for ck, v in row.items():
                if not vide(v):
                    auto[f"{tab}.{i}.{ck}"] = v
    if typ == "maternelle":
        if any(r.get("sx_m") or r.get("sx_f") for r in sout):   # seulement si le sexe est renseigné
            auto["t21.soutien.m"] = fmt(sum(1 for r in sout if r.get("sx_m")))
            auto["t21.soutien.f"] = fmt(sum(1 for r in sout if r.get("sx_f")))
        for q_, mot in (("instit", "instit"), ("educ", "educat")):
            lst = [r for r in ens if mot in H.xlsx.normaliser(r.get("qualite"))]
            if lst:
                auto[f"t21.{q_}.m"] = fmt(sum(1 for r in lst if r.get("sx_m")))
                auto[f"t21.{q_}.f"] = fmt(sum(1 for r in lst if r.get("sx_f")))
    # --- patrimoine (si le module Patrimoine expose H.patrimoine_synthese)
    f = getattr(H, "patrimoine_synthese", None)
    if callable(f):
        d = None
        for args in ((annee,), ()):
            try:
                d = f(*args)
                break
            except TypeError:
                continue
            except Exception:  # noqa: BLE001
                break
        if isinstance(d, dict):
            idx = index(typ)
            for gk, v in d.items():
                cle = PATRIMOINE.get(gk, {}).get(typ)
                if cle and not vide(v) and not isinstance(v, (dict, list)):
                    auto[cle] = ("Oui" if v else "Non") if isinstance(v, bool) else (
                        fmt(v) if isinstance(v, (int, float)) else str(v))
            direct = d.get(f"recensement_{typ}")
            for cle, v in (direct.items() if isinstance(direct, dict) else []):
                if idx.definition(cle)[0] and not vide(v):
                    auto[cle] = v
            infos.append("Données du patrimoine reprises automatiquement (module Patrimoine).")
    return auto, infos


def config_publique(H):
    try:
        return H.config.publique()
    except Exception:  # noqa: BLE001
        return False


def personnel(H, typ, ref):
    """(enseignants, soutien) : listes de lignes {colonne: valeur} pour les tableaux nominatifs."""
    db = H.get_db()
    cols = {r[1] for r in db.execute("PRAGMA table_info(personnel)")}
    if not cols:
        return [], []
    sql, args = "SELECT * FROM personnel WHERE actif=1", []
    if "ecole_id" in cols:
        sql += " AND ecole_id=?"
        args.append(H.eco())
    rows = [dict(r) for r in H.q(sql + " ORDER BY nom, prenoms", args)]
    carr = {}
    if {r[1] for r in db.execute("PRAGMA table_info(personnel_carriere)")}:
        carr = {r["personnel_id"]: dict(r) for r in H.q("SELECT * FROM personnel_carriere")}
    classes = [dict(c) for c in H.q("SELECT niveau, titulaire_nom FROM classes WHERE ecole_id=?", (H.eco(),))]
    norm = H.xlsx.normaliser
    ens, sout = [], []
    for p in rows:
        c = carr.get(p["id"], {})
        fonction = p.get("fonction") or ""
        nomc = f"{p.get('nom') or ''} {p.get('prenoms') or ''}".strip()
        cle_nom = norm(p.get("nom"))
        prenom1 = (norm(p.get("prenoms")).split() or [""])[0]
        niveaux = [cl["niveau"] for cl in classes if cle_nom and cle_nom in norm(cl["titulaire_nom"])
                   and prenom1 in norm(cl["titulaire_nom"])]
        sexe = str(p.get("sexe") or c.get("sexe") or "").upper()[:1]
        base = {"nom": nomc, "sx_m": "1" if sexe == "M" else "", "sx_f": "1" if sexe == "F" else ""}
        mat = _pick(c, "matricule", "matricule_fp", "matricule_solde")
        if not mat and p.get("matricule") and "-RH-" not in str(p.get("matricule")):
            mat = p["matricule"]
        base["mat"] = str(mat or "")
        base["nip"] = str(p.get("nip") or c.get("nip") or "").strip()   # NIP (module Carrière : personnel.nip)
        ph = _pick(c, "handicap", "ph", "personne_handicapee")
        if ph != "":
            base["ph_o" if _vrai(ph) else "ph_n"] = "1"
        naiss = _pick(c, "date_naissance", "naissance", "ne_le") or p.get("date_naissance") or ""
        statut = str(_pick(c, "statut", "statut_agent", "corps") or "")
        if RE_ENS.search(fonction) or _pick(c, "qualite", "grade"):
            directeur = bool(re.search(r"direct", fonction, re.I))
            if not directeur and niveaux and typ not in {cycle_de(n)[0] for n in niveaux}:
                continue  # titulaire d'une classe d'un autre cycle
            row = dict(base)
            row.update({"naiss": str(naiss)[:4] if re.match(r"^\d{4}", str(naiss)) else "",
                        "dip_a": str(_pick(c, "diplome_academique", "diplome_acad", "diplome") or ""),
                        "dip_p": str(_pick(c, "diplome_professionnel", "diplome_prof") or ""),
                        "grade": str(_pick(c, "grade") or ""), "statut": statut,
                        "fonction": "Directeur" if directeur else "Adjoint",
                        "indice": str(_pick(c, "indice_reel", "indice") or "")})
            date_fp = _pick(c, "date_entree_fonction_publique", "date_entree_fp", "date_recrutement",
                            "date_prise_service")
            if typ == "primaire":
                row.update({f"c_{n.lower()}": "1" for n in niveaux if n in NIV})
                row["anc_fp"] = _annees_depuis(date_fp, ref) if date_fp else ""
                row["anc_ec"] = _annees_depuis(_pick(c, "date_affectation", "date_arrivee_ecole")
                                               or p.get("date_embauche"), ref)
                row["formation"] = str(_pick(c, "date_derniere_formation", "derniere_formation") or "")
            else:
                row.update({"s_pe": "1" if any(cycle_de(n)[1] == "pe" for n in niveaux) else "",
                            "s_gr": "1" if any(cycle_de(n)[1] == "gr" for n in niveaux) else "",
                            "qualite": str(_pick(c, "qualite") or ""),
                            "anc": _annees_depuis(date_fp, ref) if date_fp else ""})
            ens.append((not directeur, nomc, row))
        else:
            row = dict(base)
            row.update({"fonction": fonction, "statut": statut, "age": _annees_depuis(naiss, ref) if naiss else ""})
            sout.append(row)
    ens.sort(key=lambda x: (x[0], x[1]))
    ens = [r for _d, _n, r in ens]
    e = g.get("ecole")
    if e and e["directeur_nom"] and not any(r.get("fonction") == "Directeur" for r in ens):
        titre = (e["directeur_titre"] or "").lower()
        ens.insert(0, {"nom": e["directeur_nom"], "fonction": "Directeur",
                       "sx_f": "1" if titre.startswith("directrice") else "",
                       "sx_m": "1" if titre == "directeur" else ""})
    return ens, sout


def completer_auto(schema, auto, dyn):
    """Fonction pré-imprimée des tableaux nominatifs (ligne 1 = Directeur, suivantes = Adjoint)."""
    for _s, t in tableaux(schema):
        d = t["dyn"]
        if d and d.get("fonction"):
            for i in range(1, dyn.get(t["k"], d["min"]) + 1):
                auto.setdefault(f"{t['k']}.{i}.{d['fonction']}", d["premier"] if i == 1 else d["autres"])


# ============================================================================ PDF : reproduction de la fiche
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.lib.utils import simpleSplit  # noqa: E402
from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: E402
from reportlab.platypus import Flowable, Frame, Paragraph, Table, TableStyle  # noqa: E402

ENCRE = colors.HexColor("#0B3D91")      # couleur des valeurs inscrites (comme au stylo)
GRISE = colors.HexColor("#948A85")      # cellules non applicables (comme le modèle)


_IMAGES_MEMP = {}


def image_memp(nom):
    """Image officielle fournie avec GESCOL (static/docs_enseignant_memp.png = armoiries + « MINISTÈRE DES
    ENSEIGNEMENTS MATERNEL ET PRIMAIRE / RÉPUBLIQUE DU BÉNIN », static/docs_enseignant_armoiries.png), en cache."""
    if nom not in _IMAGES_MEMP:
        import config
        from reportlab.lib.utils import ImageReader
        chemin = os.path.join(config.WEB_DIR, "static", nom)
        try:
            _IMAGES_MEMP[nom] = ImageReader(chemin) if os.path.exists(chemin) else None
        except Exception:  # noqa: BLE001 - image illisible : en-tête texte
            _IMAGES_MEMP[nom] = None
    return _IMAGES_MEMP[nom]


def bloc_memp(c, x, y_haut, hauteur):
    """En-tête officiel du MEMP avec logo (armoiries + ministère + République du Bénin), coin haut-gauche en
    (x, y_haut), hauteur en points. Repli : armoiries seules + texte. Renvoie la largeur occupée."""
    img = image_memp("docs_enseignant_memp.png")
    if img:
        iw, ih = img.getSize()
        c.drawImage(img, x, y_haut - hauteur, hauteur * iw / ih, hauteur)
        return hauteur * iw / ih
    arm = image_memp("docs_enseignant_armoiries.png")
    xt = x
    if arm:
        iw, ih = arm.getSize()
        c.drawImage(arm, x, y_haut - hauteur, hauteur * iw / ih, hauteur, mask="auto")
        xt = x + hauteur * iw / ih + 6
    c.saveState()
    c.setFillColor(colors.HexColor("#333333"))
    c.setFont("Helvetica-Bold", hauteur / 7.5)
    for i, t in enumerate(("MINISTÈRE", "DES ENSEIGNEMENTS", "MATERNEL ET PRIMAIRE", "", "RÉPUBLIQUE DU BÉNIN")):
        c.drawString(xt, y_haut - (i + 1) * hauteur / 5.6, t)
    c.restoreState()
    return xt - x + hauteur * 2.4


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _Vert(Flowable):
    """Texte vertical (en-têtes de colonnes étroites), coupé en lignes si trop long."""

    def __init__(self, txt, taille=6, maxh=46 * mm, gras=False):
        super().__init__()
        self.font = "Helvetica-Bold" if gras else "Helvetica"
        self.taille = taille
        self.lignes = simpleSplit(str(txt), self.font, taille, maxh) or [""]
        self.lead = taille + 1.2
        self.h = max(stringWidth(x, self.font, taille) for x in self.lignes) + 3
        self.w = len(self.lignes) * self.lead + 1

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont(self.font, self.taille)
        c.rotate(90)
        for i, txt in enumerate(self.lignes):
            c.drawString(1.5, -((i + 1) * self.lead - 1.6), txt)
        c.restoreState()


class _Case(Flowable):
    """Case à cocher ❒ (avec croix si cochée)."""

    def __init__(self, coche=False, cote=2.6 * mm):
        super().__init__()
        self.coche, self.cote = coche, cote

    def wrap(self, aw, ah):
        return self.cote, self.cote

    def draw(self):
        _dessiner_case(self.canv, 0, 0, self.cote, self.coche)


def _dessiner_case(c, x, y, cote, coche):
    c.saveState()
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)
    c.rect(x, y, cote, cote)
    if coche:
        c.setStrokeColor(ENCRE)
        c.setLineWidth(1.1)
        c.line(x + 0.5, y + 0.5, x + cote - 0.5, y + cote - 0.5)
        c.line(x + 0.5, y + cote - 0.5, x + cote - 0.5, y + 0.5)
    c.restoreState()


class RenduFiche:
    """Dessine une fiche de recensement dans la forme du modèle (pages, rubriques, tableaux, cases)."""
    LH = 4.35 * mm
    TAILLE = 8.3

    def __init__(self, schema, eff, dyn, annee, sig=None, total=None, ecole_id=None, entete=None):
        from pdfs import GCanvas
        self.buf = io.BytesIO()
        self.c = GCanvas(self.buf, pagesize=A4)
        self.ent = entete or {}
        self.synth = bool(self.ent.get("synthese"))   # fiche consolidée (CS / DDEMP) : comptes au lieu de cases
        self.c.setTitle((self.ent.get("titre") + " – " if self.ent.get("titre") else "")
                        + f"{schema['titre_court']} – {annee}")
        self.c.setAuthor("GESCOL")
        self.s, self.v, self.dyn, self.annee, self.sig, self.total = schema, eff, dyn, annee, sig, total
        self.page, self.pages_fiche, self.cadre, self.mode = 0, 0, None, "fiche"
        self.primaire = schema["type"] == "primaire"
        self.coul = colors.HexColor("#FFFF99" if self.primaire else "#FFD966")

    # ------------------------------------------------------------------ pages
    def nouvelle_page(self, paysage=False, mode=None):
        rouvrir = self.cadre is not None and mode is None
        if self.page:
            self.fermer_cadre()
            self.pied()
            self.c.showPage()
        if mode:
            self.mode = mode
        self.page += 1
        if self.mode == "fiche":
            self.pages_fiche = self.page
        self.paysage = paysage
        self.c.setPageSize(landscape(A4) if paysage else A4)
        self.W, self.Hp = self.c._pagesize
        self.m = 11 * mm
        self.x0, self.x1 = self.m, self.W - self.m
        self.y = self.Hp - 11 * mm
        self.bas = 17 * mm
        if self.mode == "fiche":
            self.filigrane()
        if rouvrir:
            self.cadre = self.y

    def filigrane(self):
        c = self.c
        c.saveState()
        c.setFillColor(colors.HexColor("#C8C8C8"))
        c.setFillAlpha(0.35)
        c.translate(self.W / 2, self.Hp / 2)
        c.rotate(57 if not self.paysage else 30)
        c.setFont("Helvetica", 54)
        c.drawCentredString(0, 18, "ANNEE SCOLAIRE")
        c.drawCentredString(0, -42, self.annee)
        c.restoreState()

    def pied(self):
        c = self.c
        c.saveState()
        c.setFillColor(colors.black)
        if self.mode == "fiche":
            y = 9 * mm
            c.setFont("Helvetica", 9)
            c.drawString(self.x0 + 14 * mm, y, self.s["pied"])
            c.setFont("Helvetica-Bold", 9.5)
            c.drawCentredString(self.W / 2 + 18 * mm, y, f"Année scolaire {self.annee}")
            c.setFont("Helvetica", 9)
            c.drawRightString(self.x1 - 8 * mm, y, f"Page {self.page} / {self.total or '…'}")
        else:
            n = self.page - self.pages_fiche
            c.setFont("Helvetica", 8)
            c.rect(self.x1 - 12 * mm, 9 * mm, 8 * mm, 5 * mm)
            c.drawCentredString(self.x1 - 8 * mm, 10.5 * mm, str(n))
        c.restoreState()

    def place(self, h):
        if self.y - h < self.bas:
            self.nouvelle_page(self.paysage)

    def fermer_cadre(self):
        if self.cadre is not None:
            self.y -= 1 * mm
            self.c.setLineWidth(0.8)
            self.c.rect(self.x0, self.y, self.x1 - self.x0, self.cadre - self.y)
            self.cadre = None

    # ------------------------------------------------------------------ en-tête de la 1re page
    def entete(self):
        c, x0, x1 = self.c, self.x0, self.x1
        y = self.y
        # en-tête officiel du MEMP avec logo (armoiries + ministère + République), comme sur le modèle
        bloc_memp(c, x0, y - 0.5 * mm, 19.5 * mm)
        c.saveState()
        c.setFillColor(colors.HexColor("#333333"))
        c.setFont("Helvetica-Bold", 6.8)
        for i, t in enumerate(["01 BP 10 Porto-Novo", "Tél:+229 20 21 52 22", "Fax: +229 20 21 52 22",
                               "E-mail: mempmatprim@gmail.com"]):
            c.drawString(x1 - 58 * mm, y - 4 * mm - i * 3 * mm, t)
        c.restoreState()
        y -= 24 * mm
        hb = 18 * mm
        c.saveState()
        c.setFillColor(colors.HexColor("#FFFF33"))
        c.rect(x0 + 2 * mm, y - hb, 82 * mm, hb, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.8)
        c.drawString(x0 + 4 * mm, y - 4.5 * mm, "RESERVER A L'ADMINISTRATION")
        c.setFont("Helvetica", 7.8)
        yy = y - 9 * mm
        for f in self.s["admin"]:
            c.setFillColor(colors.black)
            c.drawString(x0 + 4 * mm, yy, f"{f['lib']} :")
            c.setFillColor(ENCRE)
            c.drawString(x0 + 6 * mm + stringWidth(f"{f['lib']} :", "Helvetica", 7.8), yy, str(self.v.get(f["k"], ""))[:40])
            yy -= 4 * mm
        c.setFillColor(colors.black)
        c.rect(x1 - 85 * mm, y - hb, 85 * mm, hb, fill=1, stroke=0)
        c.setFillColor(colors.white)
        titre = self.s["titre"]
        if self.primaire:
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(x1 - 42.5 * mm, y - 7.5 * mm, "FICHE DE RECENSEMENT ANNUEL")
            c.drawCentredString(x1 - 42.5 * mm, y - 12 * mm, "DES ECOLES PRIMAIRES")
        else:
            c.setFont("Helvetica-Bold", 6.9)
            c.drawCentredString(x1 - 42.5 * mm, y - 10 * mm, titre)
        c.restoreState()
        y -= hb + 7 * mm
        if self.ent.get("titre"):   # fiche consolidée : « Synthèse de la CS … » à la place de la consigne
            c.setFont("Helvetica-Bold", 10.5)
            c.setFillColor(ENCRE)
            c.drawString(x0 + 2 * mm, y, str(self.ent["titre"])[:70])
            c.setFillColor(colors.black)
        else:
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(x0 + 2 * mm, y, "(Merci de bien vouloir remplir cette fiche au crayon)")
        if self.ent.get("mention"):  # ex. « Fiche transmise par l'école – reçue le … »
            c.setFont("Helvetica-Oblique", 7)
            c.setFillColor(colors.HexColor("#555555"))
            c.drawString(x0 + 2 * mm, y - 3.6 * mm, str(self.ent["mention"])[:150])
            c.setFillColor(colors.black)
        a, b = self.annee.split("-")
        c.setFont("Times-Roman", 19)
        c.drawRightString(x1 - 3 * mm, y - 1, f"Année Scolaire {a} - {b}")
        self.y = y - 4 * mm

    # ------------------------------------------------------------------ rubriques
    def bande(self, num, titre):
        h = 5.2 * mm
        self.fermer_cadre()
        self.place(h + 3 * self.LH)
        c = self.c
        c.saveState()
        c.setFillColor(self.coul)
        c.setLineWidth(0.8)
        c.rect(self.x0, self.y - h, self.x1 - self.x0, h, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 8.6)
        c.drawString(self.x0 + 24 * mm, self.y - h + 1.6 * mm, f"{num}. {titre}")
        c.restoreState()
        self.y -= h + 0.8 * mm
        self.cadre = self.y + 0.8 * mm

    def police(self, st):
        f = "Helvetica-Bold" if "b" in st else ("Helvetica-Oblique" if "i" in st else "Helvetica")
        return f, (6.8 if "p" in st else self.TAILLE)

    # groupes de segments insécables : [("t", txt, font, taille) | ("sp", w) | ("case", bool) |
    # ("boites", n, dec, val, texte) | ("pts", w, val) | ("mt", val)]
    def _mots(self, txt, f):
        return [[("t", m + " ", f[0], f[1])] for m in str(txt).split()]

    def groupes(self, it):
        f = self.police(it["st"])
        out = self._mots(it["texte"], f) if it["texte"] else []
        for ch in it["champs"]:
            if isinstance(ch, str):
                out.append([("sp", 2 * mm)])
                out += self._mots(ch, self.police("p" if len(ch) > 30 else ""))
                continue
            out.append([("sp", 2.5 * mm)])
            out += self.groupes_champ(ch, f)
        return out

    def groupes_champ(self, ch, f):
        v = self.v.get(ch["k"], "")
        t, out = ch["t"], []
        lib = self._mots(ch["lib"], f) if ch.get("lib") and t not in ("case",) else []
        if isinstance(v, dict) and t in ("on", "ch", "case"):
            # fiche consolidée : nombre d'écoles pour chaque réponse (case + nombre écrit à côté)
            opts = ["1"] if t == "case" else (OUINON if t == "on" else ch["opts"])
            labs = [ch["lib"]] if t == "case" else (["OUI", "NON"] if t == "on" and ch.get("maj") else opts)
            for o, lab in zip(opts, labs):
                n = v.get(o, 0)
                out.append([("t", lab, f[0], f[1]), ("sp", 1.2 * mm), ("case", bool(n)), ("sp", 0.8 * mm),
                            ("cnt", str(n)), ("sp", 3.5 * mm)])
            return out
        if t == "on":
            for o, lab in zip(OUINON, ["OUI", "NON"] if ch.get("maj") else OUINON):
                out.append([("t", lab, f[0], f[1]), ("sp", 1.2 * mm), ("case", v == o), ("sp", 5 * mm)])
        elif t == "ch":
            choisis = v if isinstance(v, list) else [v]
            for o in ch["opts"]:
                out.append([("t", o, f[0], f[1]), ("sp", 1.2 * mm), ("case", o in choisis), ("sp", 4 * mm)])
        elif t == "case":
            out.append([("t", ch["lib"], f[0], f[1]), ("sp", 1.5 * mm), ("case", v == "1")])
        elif t == "nb":
            out = lib + [[("boites", ch["n"], ch["dec"], v, ch["k"] == "nom")]]
            if ch["unite"]:
                out[-1] += [("sp", 1 * mm), ("t", ch["unite"], f[0], f[1])]
        elif t == "tx":
            out = lib + [[("pts", ch["w"] * mm, v)]]
        elif t == "mt":
            out = lib + [[("mt", v)]]
        return out

    def largeur(self, seg):
        k = seg[0]
        if k == "pts" and len(seg) > 3:
            return seg[3]
        if k == "t":
            return stringWidth(seg[1], seg[2], seg[3])
        if k == "sp":
            return seg[1]
        if k == "case":
            return 2.7 * mm
        if k == "boites":
            n, dec, val, texte = seg[1], seg[2], str(seg[3]), seg[4]
            if texte:
                return 4.2 * mm * n
            ip = val.replace(".", ",").split(",")[0]
            return 4 * mm * (max(n, len(ip)) + dec) + (2 * mm if dec else 0)
        if k == "pts":
            return max(seg[1], stringWidth(str(seg[2]), "Helvetica", 8) + 3 * mm)
        if k == "mt":
            return 52 * mm
        if k == "cnt":
            return stringWidth(seg[1], "Helvetica-Bold", 7.5) + 0.5 * mm
        return 0

    def dessiner_seg(self, seg, x, y):
        c, k = self.c, seg[0]
        if k == "t":
            c.setFillColor(colors.black)
            c.setFont(seg[2], seg[3])
            c.drawString(x, y, seg[1])
        elif k == "case":
            _dessiner_case(c, x, y - 0.4 * mm, 2.6 * mm, seg[1])
        elif k == "cnt":
            c.setFillColor(ENCRE)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(x, y, seg[1])
            c.setFillColor(colors.black)
        elif k == "boites":
            self.boites(x, y, *seg[1:])
        elif k == "pts":
            w = self.largeur(seg)
            c.saveState()
            c.setDash(0.6, 1.4)
            c.setLineWidth(0.5)
            c.line(x, y - 0.8, x + w, y - 0.8)
            c.restoreState()
            if seg[2]:
                c.setFillColor(ENCRE)
                c.setFont("Helvetica", 8)
                c.drawString(x + 1.2 * mm, y + 0.2, str(seg[2]))
        elif k == "mt":
            c.saveState()
            c.setLineWidth(0.6)
            c.rect(x, y - 1.4 * mm, 50 * mm, 4.5 * mm)
            c.setFont("Helvetica-Bold", 8)
            c.drawRightString(x + 48.5 * mm, y, "FCFA")
            if seg[1] != "":
                c.setFillColor(ENCRE)
                c.setFont("Helvetica-Bold", 8.5)
                c.drawRightString(x + 36 * mm, y, milliers(seg[1]))
            c.restoreState()

    def boites(self, x, y, n, dec, val, texte):
        c = self.c
        val = str(val or "")
        c.saveState()
        c.setLineWidth(0.6)
        if texte:   # nom de l'école : un caractère par case
            bw = 4.2 * mm
            n = max(n, len(val))
            if len(val) > 27:
                bw = 4.2 * mm * 27 / len(val)
            cars = list(val.upper())
            debut = 0
        else:
            bw = 4 * mm
            ip, _, dp = val.replace(".", ",").partition(",")
            n = max(n, len(ip))
            cars = [""] * (n - len(ip)) + list(ip)
            debut = 0
        c.line(x, y - 0.8, x + n * bw, y - 0.8)
        for i in range(n + 1):
            c.line(x + i * bw, y - 0.8, x + i * bw, y + 2.4 * mm)
        c.setFillColor(ENCRE)
        c.setFont("Helvetica-Bold", 8 if bw > 3 * mm else 6.5)
        for i, ch in enumerate(cars[debut:]):
            if ch.strip():
                c.drawCentredString(x + (i + 0.5) * bw, y + 0.2, ch)
        if not texte and dec:
            xd = x + n * bw
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(xd + 0.4 * mm, y, ",")
            xd += 2 * mm
            c.line(xd, y - 0.8, xd + dec * bw, y - 0.8)
            for i in range(dec + 1):
                c.line(xd + i * bw, y - 0.8, xd + i * bw, y + 2.4 * mm)
            c.setFillColor(ENCRE)
            c.setFont("Helvetica-Bold", 8)
            for i, ch in enumerate(dp[:dec]):
                c.drawCentredString(xd + (i + 0.5) * bw, y + 0.2, ch)
        c.restoreState()

    def ligne(self, it, x0, x1):
        """Ligne : numéro + texte + champs, avec retour à la ligne si nécessaire."""
        xt = x0 + 14 * mm + it["ind"] * mm
        self.place(self.LH)
        y = self.y - self.LH + 1.3 * mm
        ytop = self.y
        if it["num"]:
            self.c.setFont("Helvetica", self.TAILLE)
            self.c.setFillColor(colors.black)
            self.c.drawString(x0 + 3 * mm, y, it["num"])
        x = xt
        for grp in self.groupes(it):
            w = sum(self.largeur(s) for s in grp)
            if x + w > x1 - 1 * mm and x > xt + 1:
                self.y -= self.LH
                self.place(self.LH)
                y = self.y - self.LH + 1.3 * mm
                x = xt + 3 * mm
            for seg in grp:
                if seg[0] == "mt":      # montants alignés en colonne, comme sur le modèle
                    x = max(x, x1 - 62 * mm)
                if seg[0] == "pts" and x + self.largeur(seg) > x1 - 2 * mm:
                    wcap = max(x1 - 2 * mm - x, 10 * mm)
                    seg = ("pts", wcap, seg[2], wcap)
                self.dessiner_seg(seg, x, y)
                x += self.largeur(seg)
        self.y -= self.LH
        # texte libre sur plusieurs lignes (observations)
        for ch in it["champs"]:
            if isinstance(ch, dict) and ch["t"] == "tx" and ch.get("lignes", 1) > 1:
                reste = simpleSplit(str(self.v.get(ch["k"], "")), "Helvetica", 8, x1 - xt - 6 * mm)
                for i in range(max(ch["lignes"], len(reste))):
                    self.place(self.LH)
                    yy = self.y - self.LH + 1.3 * mm
                    self.c.saveState()
                    self.c.setDash(0.6, 1.4)
                    self.c.setLineWidth(0.5)
                    self.c.line(xt, yy - 0.8, x1 - 6 * mm, yy - 0.8)
                    self.c.restoreState()
                    if i < len(reste):
                        self.c.setFillColor(ENCRE)
                        self.c.setFont("Helvetica", 8)
                        self.c.drawString(xt + 1 * mm, yy + 0.2, reste[i])
                    self.y -= self.LH
        if it["st"] == "cadre":
            self.c.setLineWidth(0.6)
            self.c.rect(xt - 1.5 * mm, self.y + 0.4 * mm, x1 - xt - 3 * mm, ytop - self.y - 0.8 * mm)

    def para(self, it, x0, x1):
        f = self.police(it["st"])
        xt = x0 + 14 * mm + it["ind"] * mm
        for txt in simpleSplit(it["texte"], f[0], f[1], x1 - xt - 2 * mm):
            self.place(self.LH)
            self.c.setFont(*f)
            self.c.setFillColor(colors.black)
            self.c.drawString(xt, self.y - self.LH + 1.3 * mm, txt)
            self.y -= self.LH * (0.85 if "p" in it["st"] else 1)

    def grille(self, it, x0, x1):
        xt = x0 + 14 * mm + it["ind"] * mm
        lc = (x1 - xt) / it["ncol"]
        champs = it["champs"]
        for i in range(0, len(champs), it["ncol"]):
            self.place(self.LH)
            y = self.y - self.LH + 1.3 * mm
            for j, ch in enumerate(champs[i:i + it["ncol"]]):
                xc = xt + j * lc
                self.c.setFont("Helvetica", self.TAILLE)
                self.c.setFillColor(colors.black)
                self.c.drawString(xc, y, ch["lib"])
                seg = ("boites", ch["n"], ch["dec"], self.v.get(ch["k"], ""), False)
                self.boites(xc + lc - self.largeur(seg) - 4 * mm, y, *seg[1:])
            self.y -= self.LH

    # ------------------------------------------------------------------ tableaux
    def table(self, t, larg):
        leaves = feuilles(t["cols"])
        depth = profondeur(t["cols"])
        rows = lignes_tableau(t, self.dyn.get(t["k"]))
        nlab = 2 if any(r["groupe"] for r in rows) else 1
        nc = nlab + len(leaves)
        T_ = t["taille"]
        st_h = ParagraphStyle("h", fontName="Helvetica", fontSize=T_, leading=T_ + 1.2, alignment=1)
        st_l = ParagraphStyle("l", fontName="Helvetica", fontSize=T_, leading=T_ + 1.2)
        st_lb = ParagraphStyle("lb", parent=st_l, fontName="Helvetica-Bold")
        st_v = ParagraphStyle("v", fontName="Helvetica-Bold", fontSize=T_ + 0.5, leading=T_ + 1.6, alignment=1,
                              textColor=ENCRE)
        st_vt = ParagraphStyle("vt", parent=st_v, fontName="Helvetica", alignment=0, fontSize=T_)
        # largeurs (calculées d'abord : elles servent à ajuster la taille des valeurs longues, ex. NIP)
        labw = [5 * mm, t["label_w"] * mm] if nlab == 2 else [t["label_w"] * mm]
        dispo = larg - sum(labw)
        fixes = sum(c["w"] * mm for c in leaves if c["w"])
        libres = [c for c in leaves if not c["w"]]
        if libres:
            each = max((dispo - fixes) / len(libres), 4 * mm)
            ws = [c["w"] * mm if c["w"] else each for c in leaves]
        else:
            ws = [c["w"] * mm * dispo / fixes for c in leaves]
        data = [[""] * nc for _ in range(depth + len(rows))]
        style = [("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 1.2),
                 ("RIGHTPADDING", (0, 0), (-1, -1), 1.2), ("TOPPADDING", (0, 0), (-1, -1), 1),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]
        for (r, c, rs, cs, lib, vert) in entete_cellules(t["cols"], depth):
            data[r][nlab + c] = _Vert(lib, T_) if vert else Paragraph(_esc(lib), st_h)
            if rs > 1 or cs > 1:
                style.append(("SPAN", (nlab + c, r), (nlab + c + cs - 1, r + rs - 1)))
            if vert:
                style.append(("VALIGN", (nlab + c, r), (nlab + c, r), "BOTTOM"))
        data[0][0] = (_Vert(t["coin"], T_) if t["label_v"] else Paragraph(_esc(t["coin"]), st_h)) if t["coin"] else ""
        if nlab > 1 or depth > 1:
            style.append(("SPAN", (0, 0), (nlab - 1, depth - 1)))
        i = 0
        while i < len(rows):   # étiquettes de groupe verticales
            r = rows[i]
            if r["groupe"]:
                j = i
                while j + 1 < len(rows) and rows[j + 1]["groupe"] == r["groupe"]:
                    j += 1
                data[depth + i][0] = _Vert(r["groupe"], T_ - 0.5, maxh=(j - i + 1) * 5 * mm)
                style.append(("SPAN", (0, depth + i), (0, depth + j)))
                i = j + 1
            else:
                i += 1
        for i, r in enumerate(rows):
            ri = depth + i
            lab = Paragraph(_esc(r["lib"]), st_lb if r["st"] == "b" else st_l)
            if r["groupe"]:
                data[ri][1] = lab
            else:
                data[ri][0] = lab
                if nlab == 2:
                    style.append(("SPAN", (0, ri), (1, ri)))
            fus = r["fusion"]
            if fus:
                cols_f = [j for j, c in enumerate(leaves) if c["k"] in fus[0]]
                data[ri][nlab + cols_f[0]] = Paragraph(_esc(fus[1]), st_lb if r["st"] == "b" else st_h)
                style.append(("SPAN", (nlab + cols_f[0], ri), (nlab + cols_f[-1], ri)))
            for j, c in enumerate(leaves):
                cj = nlab + j
                if fus and c["k"] in fus[0]:
                    continue
                if c["k"] in r["grise"]:
                    if not any(r["span"].get(x["k"], 1) > 1 and j in range(m, m + r["span"][x["k"]])
                               for m, x in enumerate(leaves)):
                        style.append(("BACKGROUND", (cj, ri), (cj, ri), GRISE))
                        continue
                if any(j in range(m + 1, m + r["span"].get(x["k"], 1)) for m, x in enumerate(leaves)):
                    continue
                if r["span"].get(c["k"], 1) > 1:
                    style.append(("SPAN", (cj, ri), (cj + r["span"][c["k"]] - 1, ri)))
                val = self.v.get(f"{t['k']}.{r['k']}.{c['k']}", "")
                if c["t"] == "c" and not self.synth:
                    data[ri][cj] = _Case(val == "1", 2.4 * mm)
                elif val != "":
                    st_ = st_vt if c["t"] == "t" else st_v
                    dispo_c = ws[j] * r["span"].get(c["k"], 1) - 2.6
                    mot = max((stringWidth(m_, st_.fontName, st_.fontSize) for m_ in str(val).split()), default=0)
                    if mot > dispo_c > 0:   # valeur insécable trop large (NIP, matricule) : police réduite
                        st_ = ParagraphStyle("ajuste", parent=st_, fontSize=max(4.2, st_.fontSize * dispo_c / mot),
                                             leading=max(5, st_.fontSize * dispo_c / mot + 1.2))
                    data[ri][cj] = Paragraph(_esc(val), st_)
        hl = t["h_ligne"] * mm if t["h_ligne"] else None
        tab = Table(data, colWidths=labw + ws, rowHeights=[None] * depth + [hl] * len(rows), repeatRows=depth)
        style += [("ALIGN", (0, depth), (nlab - 1, -1), "LEFT")]
        tab.setStyle(TableStyle(style))
        return tab

    def tableau(self, t, x0, x1):
        larg = (t["largeur"] * mm) if t["largeur"] else (x1 - x0 - 4 * mm - t["ind"] * mm)
        larg = min(larg, x1 - x0 - 4 * mm)
        x = x0 + 2 * mm + t["ind"] * mm
        tab = self.table(t, larg)
        _w, h = tab.wrap(larg, self.Hp)
        if self.y - h - 1 * mm < self.bas:
            if h < self.Hp - 30 * mm and self.y < self.Hp - 60 * mm:
                self.nouvelle_page(self.paysage)
            else:
                morceaux = tab.split(larg, self.y - self.bas - 1 * mm)
                for i, mo in enumerate(morceaux):
                    _w, hm = mo.wrap(larg, self.Hp)
                    if i:
                        self.nouvelle_page(self.paysage)
                    mo.drawOn(self.c, x, self.y - hm - 0.5 * mm)
                    self.y -= hm + 1.5 * mm
                return
        tab.drawOn(self.c, x, self.y - h - 0.5 * mm)
        self.y -= h + 1.8 * mm

    # ------------------------------------------------------------------ signatures
    def signatures(self, kind):
        c = self.c
        if kind == "primaire":
            h = 30 * mm
            self.place(h + 6 * mm)
            c.setFont("Helvetica", 9)
            c.drawCentredString(self.W / 2, self.y - 3.5 * mm, "Signatures et Visas")
            self.y -= 5 * mm
            titres = [["Directeur"], ["RUP"], ["Conseiller Pédagogique"], ["Chef de la", "Circonscription Scolaire"]]
            larg = (self.x1 - self.x0) / 4
            c.setLineWidth(0.6)
            for i, tt in enumerate(titres):
                x = self.x0 + i * larg
                c.rect(x, self.y - h, larg, h)
                for j, t in enumerate(tt):
                    c.drawCentredString(x + larg / 2, self.y - 4 * mm - j * 3.8 * mm, t)
            if self.sig is not None:
                from pdfs import griffe_ecole
                import config as _cfg
                if _cfg.ECOLE.get("_griffe"):
                    # griffe du directeur (cachet rectangulaire du nom) sous la signature, dans la case « Directeur »
                    c.drawImage(self.sig, self.x0 + 4 * mm, self.y - h + 11 * mm, larg - 8 * mm, h - 19 * mm,
                                preserveAspectRatio=True, mask="auto")
                    griffe_ecole(c, self.x0 + larg / 2, self.y - h + 5.5 * mm, larg - 12 * mm)
                else:
                    c.drawImage(self.sig, self.x0 + 4 * mm, self.y - h + 2 * mm, larg - 8 * mm, h - 12 * mm,
                                preserveAspectRatio=True, mask="auto")
            self.y -= h
        else:
            xt = self.x0 + 28 * mm
            self.place(6 * self.LH)
            c.setFont("Helvetica", self.TAILLE)
            c.drawString(xt, self.y - 3 * mm, "Signature : " + "." * 90)
            if self.sig is not None:
                c.drawImage(self.sig, xt + 20 * mm, self.y - 10 * mm, 40 * mm, 14 * mm, preserveAspectRatio=True,
                            mask="auto")
            self.y -= 8 * mm
            for titre, sous in (("Contrôlé par le Responsable d'Unité Pédagogique", "(Signature - Nom et Prénoms - date)"),
                                ("Contrôlé par le Conseiller Pédagogique", "(Signature - Nom et Prénoms - date)"),
                                ("Visa du chef de la Circonscription scolaire", "(Signature- Nom et Prénoms - date)")):
                self.place(26 * mm)
                c.setFont("Helvetica", self.TAILLE)
                c.drawString(xt, self.y - 3 * mm, titre)
                c.drawString(xt, self.y - 8 * mm, sous)
                self.y -= 26 * mm

    # ------------------------------------------------------------------ assemblage
    def items(self, items, x0, x1):
        for it in items:
            k = it["i"]
            if k == "L":
                self.ligne(it, x0, x1)
            elif k == "P":
                self.para(it, x0, x1)
            elif k == "G":
                self.grille(it, x0, x1)
            elif k == "T":
                self.tableau(it, x0, x1)
            elif k == "SAUT":
                self.nouvelle_page(it["paysage"])
            elif k == "SIG":
                self.signatures(it["kind"])
            elif k == "ESP":
                self.y -= it["h"] * mm
            elif k == "C2":
                h = max(self.hauteur(it["g"], x0, x0 + (x1 - x0) * it["ratio"]),
                        self.hauteur(it["d"], x0 + (x1 - x0) * it["ratio"], x1))
                self.place(h)
                y0, xm = self.y, x0 + (x1 - x0) * it["ratio"]
                self.items(it["g"], x0, xm)
                yg, self.y = self.y, y0
                self.items(it["d"], xm - 10 * mm, x1)
                self.y = min(yg, self.y)

    def hauteur(self, items, x0, x1):
        h = 0
        for it in items:
            if it["i"] == "T":
                larg = min((it["largeur"] * mm) if it["largeur"] else (x1 - x0), x1 - x0 - 4 * mm)
                h += self.table(it, larg).wrap(larg, self.Hp)[1] + 2 * mm
            else:
                h += self.LH * (2 if it["i"] == "L" and len(it.get("champs", [])) > 2 else 1)
        return h

    def dessiner(self, guide=True):
        self.nouvelle_page(False)
        self.entete()
        for s in self.s["sections"]:
            if s.get("i") == "SAUT":
                self.fermer_cadre()
                self.nouvelle_page(s["paysage"])
                continue
            self.bande(s["num"], s["titre"])
            self.items(s["items"], self.x0, self.x1)
            self.fermer_cadre()
            self.y -= 1.5 * mm
        if guide and self.primaire:
            self.guide()
        self.pied()
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()

    def guide(self):
        self.nouvelle_page(False, mode="guide")
        c = self.c
        bx, bw, bh = self.x0 + 28 * mm, self.x1 - self.x0 - 56 * mm, 17 * mm
        c.setLineWidth(2.2)
        c.rect(bx, self.y - bh, bw, bh)
        c.setLineWidth(0.6)
        c.rect(bx + 1.2 * mm, self.y - bh + 1.2 * mm, bw - 2.4 * mm, bh - 2.4 * mm)
        c.setFont("Helvetica", 13)
        c.drawCentredString(bx + bw / 2, self.y - 7 * mm, "Guide de remplissage de la fiche de recensement")
        c.drawCentredString(bx + bw / 2, self.y - 13 * mm, "annuel des Ecoles Primaires (EP)")
        self.y -= bh + 8 * mm
        st = {"p": ParagraphStyle("gp", fontName="Helvetica", fontSize=10, leading=14, alignment=4, spaceAfter=5),
              "s": ParagraphStyle("gs", fontName="Helvetica-Bold", fontSize=10, leading=14, spaceBefore=4, spaceAfter=3),
              "h": ParagraphStyle("gh", fontName="Helvetica-Bold", fontSize=10, leading=14, spaceBefore=6,
                                  spaceAfter=6, leftIndent=10),
              "h0": ParagraphStyle("g0", fontName="Helvetica-Bold", fontSize=10, leading=14, spaceAfter=6),
              "n": ParagraphStyle("gn", fontName="Helvetica", fontSize=8, leading=10, spaceBefore=8)}
        flux = []
        for typ_, txt in GUIDE_PRIMAIRE:
            if typ_ in ("h", "h0"):
                txt = f"<u>{txt}</u>"
            flux.append(Paragraph(txt, st[typ_]))
        while flux:
            fr = Frame(self.x0 + 8 * mm, self.bas, self.x1 - self.x0 - 16 * mm, self.y - self.bas, showBoundary=0)
            fr.addFromList(flux, c)
            if flux:
                self.nouvelle_page(False)


def pdf_fiche(schema, eff, dyn, annee, sig=None, guide=True, entete=None):
    """PDF de la fiche (2 passes : la 1re compte les pages pour « Page n / N »)."""
    r1 = RenduFiche(schema, eff, dyn, annee, sig, entete=entete)
    r1.dessiner(guide=False)
    return RenduFiche(schema, eff, dyn, annee, sig, total=r1.pages_fiche, entete=entete).dessiner(guide=guide)


# ============================================================================ vues web (formulaire par rubriques)
def vue_tableau(t, dyn, saisies, calc, orig):
    """Structure prête pour le gabarit : en-tête (cellules fusionnées) et lignes de cellules saisissables."""
    leaves = feuilles(t["cols"])
    depth = profondeur(t["cols"])
    rows = lignes_tableau(t, dyn.get(t["k"]))
    nlab = 2 if any(r["groupe"] for r in rows) else 1
    entete = [[] for _ in range(depth)]
    entete[0].append({"txt": t["coin"], "cs": nlab, "rs": depth, "v": t["label_v"], "coin": True})
    for (r, _c, rs, cs, lib, vert) in entete_cellules(t["cols"], depth):
        entete[r].append({"txt": lib, "cs": cs, "rs": rs, "v": vert})
    lignes, vu_groupes = [], set()
    for i, r in enumerate(rows):
        grp = None
        if r["groupe"]:
            if r["groupe"] in vu_groupes:
                grp = "suite"
            else:
                vu_groupes.add(r["groupe"])
                grp = {"txt": r["groupe"], "rs": sum(1 for x in rows if x["groupe"] == r["groupe"])}
        cells, saut = [], 0
        fus = r["fusion"]
        fus_fait = False
        for j, c in enumerate(leaves):
            if saut:
                saut -= 1
                continue
            k = f"{t['k']}.{r['k']}.{c['k']}"
            if fus and c["k"] in fus[0]:
                if not fus_fait:
                    cells.append({"fusion": fus[1], "cs": len(fus[0])})
                    fus_fait = True
                continue
            span = r["span"].get(c["k"], 1)
            if span > 1:
                saut = span - 1
            elif c["k"] in r["grise"]:
                cells.append({"grise": True})
                continue
            somme = []
            if r["total"] and c["t"] in NUMERIQUES_CELLULE:
                somme = [f"{t['k']}.{x}.{c['k']}" for x in r["total"]]
            elif c.get("somme"):
                somme = [f"{t['k']}.{r['k']}.{p}" for p in c["somme"]]
            s = saisies.get(k, "")
            cells.append({"key": k, "t": c["t"], "cs": span, "s": "" if isinstance(s, list) else s,
                          "c": calc.get(k, ""), "o": orig.get(k, ""), "somme": "|".join(somme),
                          "lib": f"{r['lib']} – {chemins(t['cols'])[c['k']]}"})
        lignes.append({"k": r["k"], "lib": r["lib"], "st": r["st"], "groupe": grp, "cells": cells,
                       "total": bool(r["total"])})
    return {"k": t["k"], "titre": t["titre"], "nlab": nlab, "entete": entete, "lignes": lignes,
            "dyn": bool(t["dyn"]), "petit": len(leaves) > 10}


# ============================================================================ API : transmission, CS / DDEMP
# Ces fonctions sont PURES (aucun contexte d'école ni de requête) : elles servent à la transmission
# (m_transmission : valeurs de la fiche) et aux applications CS / DDEMP (a_fiches : fiche officielle remplie
# avec les valeurs transmises, fiches consolidées, vue web lisible).
import copy  # noqa: E402

# Correspondance identité (paquet / école de la juridiction) → champs de la fiche
_ENTETE_CHAMPS = (("code", "code_ecole"), ("cs", "cs"), ("departement", "departement"), ("commune", "commune"),
                  ("arrondissement", "arrondissement"), ("localite", "village"), ("adresse", "adresse"),
                  ("telephone", "telephone"), ("email", "email"), ("up", "up"))


def valeurs_vierges(schema):
    """Valeurs de la fiche vierge : seules les fonctions pré-imprimées du modèle (Directeur / Adjoint)."""
    eff, dyn = {}, {t["k"]: t["dyn"]["min"] for _s, t in tableaux(schema) if t["dyn"]}
    for _s, t in tableaux(schema):
        d = t["dyn"]
        if d and d.get("fonction"):
            for i in range(1, d["min"] + 1):
                eff[f"{t['k']}.{i}.{d['fonction']}"] = d["premier"] if i == 1 else d["autres"]
    return eff, dyn


def completer_identite(valeurs, entete):
    """Complète (sans écraser) les champs d'identification de la fiche avec l'identité fournie
    (école, CS, département, zone, directeur…)."""
    v = dict(valeurs or {})
    e = entete or {}

    def poser(k, val):
        if val not in (None, "") and vide(v.get(k)):
            v[k] = val
    poser("nom", str(e.get("ecole") or e.get("nom") or "").upper())
    for src, k in _ENTETE_CHAMPS:
        poser(k, e.get(src))
    z = re.search(r"[1-6]", str(e.get("zone") or ""))
    if z:
        poser("zone", z.group(0))
    poser("rempli_par", e.get("directeur") or e.get("directeur_nom"))
    return v


def pdf_depuis_valeurs(typ, valeurs, annee, entete=None, vierge=False):
    """Fiche OFFICIELLE de recensement (même forme que côté école : en-tête MEMP, NIP…) remplie avec des valeurs
    déjà calculées (H.recensement_valeurs, paquet de transmission, synthese_valeurs), hors contexte d'école.
    entete : identité {ecole, code, cs, departement, zone, commune, directeur, …} + options facultatives
    {titre (fiche consolidée), mention (ligne d'information), synthese (bool), guide (bool), signature
    (ImageReader)}. Renvoie les octets du PDF."""
    if typ not in SCHEMAS:
        raise ValueError(f"Type de fiche inconnu : {typ}")
    e = dict(entete or {})
    schema = SCHEMAS[typ]
    if vierge:
        eff, dyn = valeurs_vierges(schema)
        e.pop("titre", None)
        e.pop("synthese", None)
    elif e.get("synthese"):
        schema = schema_synthese(typ)
        eff = dict(valeurs or {})
        dyn = {}
    else:
        eff = completer_identite(valeurs, e)
        dyn = nb_lignes_dyn(schema, eff, {})
    return pdf_fiche(schema, eff, dyn, annee_valide(annee, annee), sig=None if vierge else e.get("signature"),
                     guide=bool(e.get("guide")), entete=e)


# ------------------------------------------------------------------ fiches consolidées (synthèse CS / DDEMP)
STATUTS_SYNTHESE = [("fe", "Fonctionnaires de l'État (FE)", ("FE", "FONCTIONNAIRE", "APE")),
                    ("ace", "ACE / ACDPE", ("ACE", "ACDPE")), ("ame", "AME / ACDPCTD", ("AME", "ACDPCTD")),
                    ("cnr", "Contractuels non reversés (CNR)", ("CNR", "CONTRACTUEL")),
                    ("stag", "Stagiaires / aspirants", ("STAGIAIRE", "ASPIRANT")), ("sup", "Suppléants", ("SUPPLEANT",)),
                    ("prive", "Enseignants du privé", ("PRIVE",)), ("autre", "Autres statuts", ()),
                    ("nd", "Statut non précisé", ())]
FONCTIONS_SOUTIEN = [("gardien", "Gardiens", ("GARDIEN",)), ("cuisine", "Cuisiniers / cuisinières", ("CUISIN",)),
                     ("entretien", "Agents d'entretien", ("ENTRETIEN", "MENAGE")),
                     ("secretaire", "Secrétaires", ("SECRETAIRE",)), ("liaison", "Agents de liaison", ("LIAISON",)),
                     ("autre", "Autres fonctions", ()), ("nd", "Fonction non précisée", ())]


IDENTITE_ECOLE = {"creation_an", "creation_ref", "creation_du", "extension_an", "extension_ref", "extension_du",
                  "up", "commune", "arrondissement", "village", "adresse", "bp", "ville", "telephone", "email",
                  "rempli_par", "rempli_fonction", "type_preciser", "georef", "code_ecole"}


def _categorie(texte, liste):
    import unicodedata
    t = unicodedata.normalize("NFD", str(texte or "")).encode("ascii", "ignore").decode().upper().strip()
    if not t:
        return "nd"
    mots = set(re.split(r"[^A-Z0-9]+", t))
    for k, _lib, cles in liste:
        if any((c in mots) if len(c) <= 5 else (c in t) for c in cles):
            return k
    return "autre"


def _tables_personnel(typ):
    """(clé du tableau des enseignants, clé du tableau du personnel de soutien)."""
    return ("t8", "t10") if typ == "primaire" else ("t6", "t7")


def _table_synthese_personnel(k, soutien, titre):
    lst = FONCTIONS_SOUTIEN if soutien else STATUTS_SYNTHESE
    cols = [GR("Effectif", K("h", "Hommes"), K("f", "Femmes"), K("t", "Total")),   # Total : sexe inconnu compris
            K("ph", "dont personnes handicapées (PH)")]
    if not soutien:
        cols += [K("dir", "dont directeurs / directrices"),
                 GR("Diplôme professionnel le plus élevé", K("cap", "CAP"), K("ceap", "CEAP"), K("dpa", "Autre"),
                    K("dpn", "Non précisé"))]
    cols.append(K("nip", "NIP renseigné"))
    rows = [R(c, lib) for c, lib, _ in lst] + [R("tot", "Total", total=[c for c, _, _ in lst], st="b")]
    return T(k + "s", cols, rows, coin="Statut" if not soutien else "Fonction", label_w=52, taille=7.5, titre=titre)


def schema_synthese(typ):
    """Schéma de la fiche consolidée : identique au modèle, sauf les états nominatifs (impossibles à additionner),
    remplacés par un récapitulatif du personnel par statut (enseignants) ou par fonction (soutien)."""
    cle = f"synthese:{typ}"
    if cle in _INDEX:
        return _INDEX[cle]
    sch = copy.deepcopy(SCHEMAS[typ])
    tk, sk = _tables_personnel(typ)
    for s in sch["sections"]:
        if "items" not in s:
            continue
        items = []
        for it in s["items"]:
            if it["i"] == "T" and it["k"] in (tk, sk):
                items.append(P("Récapitulatif établi à partir des états nominatifs transmis par les écoles "
                               "(liste nominative détaillée : export Excel, feuille « Personnel »).", st="ip"))
                items.append(_table_synthese_personnel(it["k"], it["k"] == sk, ""))
            elif it["i"] == "P" and s["items"] and any(x["i"] == "T" and x["k"] in (tk, sk) for x in s["items"]) \
                    and it["texte"].startswith("("):
                continue   # renvois (1)…(6) des colonnes de l'état nominatif : sans objet dans le récapitulatif
            else:
                items.append(it)
        s["items"] = items
    sch["titre_court"] = "Synthèse – " + sch["titre_court"]
    _INDEX[cle] = sch
    return sch


def _calculees(schema):
    """Clés calculées (totaux de lignes, colonnes « somme », champs « somme ») d'un schéma."""
    out = {ch["k"] for _s, _it, ch in champs_simples(schema) if ch.get("somme")}
    for _s, t in tableaux(schema):
        if t["dyn"]:
            continue
        for r in t["rows"]:
            for c in feuilles(t["cols"]):
                if (r["total"] and c["t"] in NUMERIQUES_CELLULE) or c.get("somme"):
                    out.add(f"{t['k']}.{r['k']}.{c['k']}")
    return out


def lignes_personnel(typ, valeurs, soutien=False):
    """Lignes renseignées d'un état nominatif : [{colonne: valeur}] (lignes sans nom ignorées)."""
    tk = _tables_personnel(typ)[1 if soutien else 0]
    out = {}
    for k, val in (valeurs or {}).items():
        m = re.match(r"^" + tk + r"\.(\d+)\.([a-z0-9_]+)$", str(k))
        if m and not vide(val):
            out.setdefault(int(m.group(1)), {})[m.group(2)] = val
    return [out[i] for i in sorted(out) if not vide(out[i].get("nom"))]


def _mode(vals):
    vals = [v for v in vals if not vide(v)]
    return max(set(vals), key=vals.count) if vals else ""


def synthese_valeurs(typ, ecoles, titre="", infos=None):
    """Fiche consolidée d'une juridiction. ecoles : [(nom de l'école, valeurs de sa fiche)].
    Champs numériques : somme (distances en km : moyenne ; années : valeur la plus fréquente) ; Oui / Non et
    cases à cocher : nombre d'écoles par réponse ; texte : valeur commune, ou somme si numérique.
    Renvoie {"valeurs", "controles", "personnel" (liste nominative avec l'école), "soutien", "n"}."""
    schema = SCHEMAS[typ]
    infos = infos or {}
    liste = [(nom, v or {}) for nom, v in ecoles]
    n = len(liste)
    calc_k = _calculees(schema)
    base, comptes = {}, {}
    for _s, _it, ch in champs_simples(schema):
        k, t = ch["k"], ch["t"]
        vals = [v.get(k) for _n, v in liste]
        if k == "nom" or k in IDENTITE_ECOLE:
            continue   # identité propre à chaque école : sans objet dans une fiche consolidée
        if t in ("on", "ch", "case"):
            opts = ["1"] if t == "case" else (OUINON if t == "on" else ch["opts"])
            cpt = {o: 0 for o in opts}
            for x in vals:
                for o in (x if isinstance(x, list) else [x]):
                    o = "1" if t == "case" and str(o) == "1" else o
                    if o in cpt:
                        cpt[o] += 1
            comptes[k] = cpt
        elif t in NUMERIQUES_CHAMP:
            nums = [nombre(x) for x in vals if nombre(x) is not None]
            if not nums:
                continue
            if k.endswith("_an"):
                base[k] = fmt(_mode([nombre(x) for x in vals if nombre(x) is not None]))
            elif ch.get("unite") == "km":
                base[k] = fmt(round(sum(nums) / len(nums), 1))
            elif k not in calc_k:
                base[k] = fmt(sum(nums))
        elif t == "tx":
            txt = [str(x).strip() for x in vals if not vide(x) and not isinstance(x, (list, dict))]
            if txt and all(nombre(x) is not None for x in txt):
                base[k] = fmt(sum(nombre(x) for x in txt))
            elif txt and len(set(txt)) == 1:
                base[k] = txt[0]
    for _s, t in tableaux(schema):
        if t["dyn"]:
            continue
        for r in t["rows"]:
            for c in feuilles(t["cols"]):
                k = f"{t['k']}.{r['k']}.{c['k']}"
                if k in calc_k or c["t"] in ("an", "t") or c["k"] in r["grise"] \
                        or (r["fusion"] and c["k"] in r["fusion"][0]):
                    continue
                vals = [v.get(k) for _n, v in liste]
                if c["t"] == "c":
                    nb_ = sum(1 for x in vals if str(x) == "1")
                    if nb_:
                        base[k] = str(nb_)
                    continue
                nums = [nombre(x) for x in vals if nombre(x) is not None]
                if nums:
                    base[k] = fmt(round(sum(nums) / len(nums), 1) if c["t"] == "d" else sum(nums))
    # contrôle « total transmis = total recalculé » (G + F = T, totaux de lignes) sur les sommes des écoles
    alertes = []
    sch_s = schema_synthese(typ)
    for k in sorted(calc_k):
        if not k.startswith(tuple(f"{x}." for x in _tables_personnel(typ))):
            nums = [nombre(v.get(k)) for _n, v in liste if nombre(v.get(k)) is not None]
            if nums:
                base.setdefault("__transmis__", {})[k] = sum(nums)
    transmis = base.pop("__transmis__", {})
    eff, calc, _orig, _al = evaluer(sch_s, {}, base, {})
    for k, tot in transmis.items():
        if nombre(calc.get(k)) is not None and abs(nombre(calc.get(k)) - tot) > 0.01:
            alertes.append(f"{libelle_cle(typ, k)} : total transmis par les écoles {fmt(tot)} ≠ total recalculé "
                           f"{fmt(nombre(calc.get(k)))} (G + F = T ou somme des lignes).")
    # récapitulatif du personnel (par statut / par fonction)
    pers, sout = [], []
    for soutien, dest, lst_cat in ((False, pers, STATUTS_SYNTHESE), (True, sout, FONCTIONS_SOUTIEN)):
        tk = _tables_personnel(typ)[1 if soutien else 0] + "s"
        cpt = {}
        for nom_e, v in liste:
            for row in lignes_personnel(typ, v, soutien):
                dest.append(dict(row, ecole=nom_e))
                cat = _categorie(row.get("fonction") if soutien else row.get("statut"), lst_cat)
                d = cpt.setdefault(cat, {})

                def plus(col):
                    d[col] = d.get(col, 0) + 1
                plus("t")
                plus("h" if row.get("sx_m") == "1" else ("f" if row.get("sx_f") == "1" else "_"))
                if row.get("ph_o") == "1":
                    plus("ph")
                if not vide(row.get("nip")):
                    plus("nip")
                if not soutien:
                    if re.match(r"(?i)direct", str(row.get("fonction") or "")):
                        plus("dir")
                    dp = str(row.get("dip_p") or "").upper()
                    plus("cap" if "CAP" in dp and "CEAP" not in dp else ("ceap" if "CEAP" in dp else ("dpa" if dp.strip() else "dpn")))
        for cat, d in cpt.items():
            for col, x in d.items():
                if col != "_":
                    eff[f"{tk}.{cat}.{col}"] = str(x)
    # totaux du récapitulatif
    eff2, _c, _o, _a = evaluer(sch_s, {}, {k: x for k, x in eff.items() if not vide(x)}, {})
    eff = eff2
    eff.update(comptes)
    eff.update({"nom": (titre or "Synthèse").upper(), "code_ecole": f"{n} école(s) prise(s) en compte",
                "date_remplissage": date.today().strftime("%d/%m/%Y")})
    for k in ("cs", "departement", "rempli_par", "rempli_fonction"):
        if infos.get(k):
            eff[k] = infos[k]
    ctrl = controles(typ, eff, alertes)
    for nom_e, v in liste:
        for m_ in controles(typ, v, [])[:6]:
            ctrl.append(f"{nom_e} – {m_}")
    return {"valeurs": eff, "controles": list(dict.fromkeys(ctrl)), "personnel": pers, "soutien": sout, "n": n}


# ------------------------------------------------------------------ vue lisible (web, Excel)
def texte_valeur(ch_ou_col, v, synth=False):
    """Valeur affichable d'un champ ou d'une cellule."""
    if isinstance(v, dict):
        return " · ".join(f"{('Cochée' if o == '1' else o)} : {x}" for o, x in v.items())
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    t = ch_ou_col.get("t")
    if t in ("case", "c") and not synth:
        return "X" if str(v) == "1" else ""
    return "" if v is None else str(v)


def vue_lecture(typ, valeurs, synthese=False):
    """Fiche en lecture : [{"titre", "champs": [(num, libellé, valeur)], "tableaux": [{"titre", "entete":
    [[{txt, cs, rs}]], "colonnes": [chemins], "lignes": [{"lib", "cells": [texte | None (grisé)]}]}]}]."""
    schema = schema_synthese(typ) if synthese else SCHEMAS[typ]
    v = valeurs or {}
    dyn = nb_lignes_dyn(schema, v, {})
    out = []
    for s in sections(schema):
        sec = {"titre": f"{s['num']}. {s['titre']}", "champs": [], "tableaux": []}
        for it0 in s["items"]:
            for it in _aplatir(it0):
                if it["i"] in ("L", "G"):
                    for ch in it["champs"]:
                        if isinstance(ch, dict):
                            sec["champs"].append((it.get("num", ""), libelle_champ(s, it, ch),
                                                  texte_valeur(ch, v.get(ch["k"]), synthese)))
                elif it["i"] == "T":
                    leaves = feuilles(it["cols"])
                    depth = profondeur(it["cols"])
                    ent = [[] for _ in range(depth)]
                    ent[0].append({"txt": it["coin"] or "", "cs": 1, "rs": depth})
                    for (r_, _c, rs, cs, lib, _v) in entete_cellules(it["cols"], depth):
                        ent[r_].append({"txt": lib, "cs": cs, "rs": rs})
                    lignes = []
                    for r in lignes_tableau(it, dyn.get(it["k"])):
                        cells = []
                        for c in leaves:
                            if c["k"] in r["grise"] or (r["fusion"] and c["k"] in r["fusion"][0]):
                                cells.append(None)
                            else:
                                cells.append(texte_valeur(c, v.get(f"{it['k']}.{r['k']}.{c['k']}"), synthese))
                        if it["dyn"] and not any(cells[i] for i, c in enumerate(leaves) if c["k"] != "fonction"):
                            continue   # ligne vide de l'état nominatif
                        lignes.append({"lib": ((r["groupe"] + " › ") if r["groupe"] else "") + r["lib"],
                                       "cells": cells, "st": r["st"]})
                    ch_ = chemins(it["cols"])
                    sec["tableaux"].append({"titre": it["titre"] or f"Rubrique {s['num']}", "entete": ent,
                                            "colonnes": [ch_[c["k"]] for c in leaves], "lignes": lignes,
                                            "coin": it["coin"] or ""})
        out.append(sec)
    return out


# ============================================================================ dépôts (fiches officielles téléversées)
TYPES_DEPOT = {
    "fiche_primaire": "Fiche de recensement annuel – primaire (EP)",
    "fiche_maternelle": "Fiche de recensement annuel – maternelle (EM)",
    "rentree_ep": "Rapport de rentrée – EP", "rentree_em": "Rapport de rentrée – EM",
    "fin_ep": "Rapport de fin d'année – EP", "fin_em": "Rapport de fin d'année – EM",
    "autre": "Autre document de la carte d'identité",
}
SIGNATURES_FICHIERS = [(b"%PDF", ".pdf", "application/pdf"), (b"\x89PNG", ".png", "image/png"),
                       (b"\xff\xd8\xff", ".jpg", "image/jpeg")]
TAILLE_MAX_DEPOT = 15 * 1024 * 1024


def type_fichier(debut):
    for sig, ext, mime in SIGNATURES_FICHIERS:
        if debut.startswith(sig):
            return ext, mime
    if debut[:4] == b"RIFF" and debut[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None, None


def annee_valide(v, defaut):
    m = RE_ANNEE.match(str(v or "").strip())
    if m and int(m.group(2)) == int(m.group(1)) + 1 and 1990 <= int(m.group(1)) <= 2100:
        return m.group(0)
    return defaut


def annees_proches(annee_active):
    y = int(annee_active[:4])
    return [f"{a}-{a + 1}" for a in range(y + 1, y - 6, -1)]


# ============================================================================ routes
_H = None   # objet H de la dernière application (tests, outils)


def enregistrer(app, H):
    global _H
    _H = H
    q, ex, config = H.q, H.ex, H.config
    H.schema("""
    CREATE TABLE IF NOT EXISTS recensement_depots (
        id INTEGER PRIMARY KEY,
        ecole_id INTEGER NOT NULL,
        annee TEXT NOT NULL,
        type_doc TEXT NOT NULL,
        libelle TEXT,
        fichier TEXT NOT NULL,
        nom_original TEXT,
        mime TEXT,
        taille INTEGER,
        depose_le TEXT,
        depose_par TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_recensement_depots ON recensement_depots(ecole_id, annee);
    """)

    def dossier_depots():
        d = os.path.join(config.INSTANCE_DIR, "recensement", f"e{H.eco()}")
        os.makedirs(d, exist_ok=True)
        return d

    def typ_ou_404(typ):
        if typ not in SCHEMAS:
            abort(404)
        return SCHEMAS[typ]

    def annee_req():
        return annee_valide(request.values.get("annee"), config.ANNEE_ACTIVE)

    def cle_doc(typ, annee):
        return f"e{H.eco()}:recensement:{typ}:{annee}"

    def lire_saisies(typ, annee):
        d = H.doc_lire(cle_doc(typ, annee), None) or {}
        v = d.get("valeurs") if isinstance(d.get("valeurs"), dict) else {}
        return v, d.get("par"), d.get("maj")

    def ecrire_saisies(typ, annee, valeurs):
        H.doc_ecrire(cle_doc(typ, annee), {"valeurs": valeurs, "par": g.user["nom"] if g.get("user") else "",
                                           "maj": H.maintenant()})

    def contexte(typ, annee):
        schema = SCHEMAS[typ]
        saisies, par, maj = lire_saisies(typ, annee)
        auto, infos = calculs(H, typ, annee)
        dyn = nb_lignes_dyn(schema, saisies, auto)
        completer_auto(schema, auto, dyn)
        eff, calc, orig, al = evaluer(schema, saisies, auto, dyn)
        ctrl = controles(typ, eff, al)
        n_rempli = sum(1 for v in eff.values() if not vide(v))
        return {"schema": schema, "typ": typ, "annee": annee, "saisies": saisies, "auto": auto, "infos": infos,
                "dyn": dyn, "eff": eff, "calc": calc, "orig": orig, "ctrl": ctrl, "par": par, "maj": maj,
                "n_saisis": sum(1 for v in orig.values() if v == "saisie"),
                "n_calcules": sum(1 for v in orig.values() if v == "calculée"),
                "n_rempli": n_rempli, "n_total": len(eff)}

    def recensement_valeurs(typ, annee=None):
        """Valeurs COMPLÈTES de la fiche (calculées par GESCOL + saisies / corrigées) pour l'école courante :
        {clé: valeur} (toutes les cases, vides comprises). typ ∈ primaire | maternelle."""
        if typ not in SCHEMAS:
            raise ValueError(f"Type de fiche inconnu : {typ}")
        return dict(contexte(typ, annee_valide(annee, config.ANNEE_ACTIVE))["eff"])
    H.recensement_valeurs = recensement_valeurs

    # ------------------------------------------------------------------ hub « Carte d'identité de l'école »
    @app.route("/recensement")
    @H.connexion_requise("recensement")
    def recensement_accueil():
        annee = annee_req()
        e = dict(g.ecole) if g.get("ecole") else {}
        eco = H.eco()
        cl = [dict(c) for c in q("SELECT c.*, (SELECT COUNT(*) FROM eleves x WHERE x.classe_id=c.id AND "
                                 "x.statut='inscrit') eff FROM classes c WHERE c.ecole_id=?", (eco,))]
        par_cycle = {}
        for c in cl:
            cy = cycle_de(c["niveau"])[0] or "autre"
            d = par_cycle.setdefault(cy, {"classes": 0, "eleves": 0})
            d["classes"] += 1
            d["eleves"] += c["eff"]
        try:
            n_pers = q("SELECT COUNT(*) n FROM personnel WHERE actif=1 AND ecole_id=?", (eco,), un=True)["n"]
        except Exception:  # noqa: BLE001
            n_pers = 0
        fiches = []
        for typ in SCHEMAS:
            ctx = contexte(typ, annee)
            fiches.append({"typ": typ, "titre": SCHEMAS[typ]["titre_court"], "ctx": ctx,
                           "pct": round(100 * ctx["n_rempli"] / max(ctx["n_total"], 1))})
        depots = q("SELECT * FROM recensement_depots WHERE ecole_id=? ORDER BY annee DESC, depose_le DESC", (eco,))
        return render_template("recensement_accueil.html", e=e, annee=annee, annees=annees_proches(config.ANNEE_ACTIVE),
                               par_cycle=par_cycle, n_pers=n_pers, fiches=fiches, depots=depots,
                               TYPES_DEPOT=TYPES_DEPOT)

    # ------------------------------------------------------------------ formulaire d'une fiche
    @app.route("/recensement/fiche/<typ>")
    @H.connexion_requise("recensement")
    def recensement_fiche(typ):
        typ_ou_404(typ)
        ctx = contexte(typ, annee_req())
        schema = ctx["schema"]
        tables = {t["k"]: vue_tableau(t, ctx["dyn"], ctx["saisies"], ctx["calc"], ctx["orig"])
                  for _s, t in tableaux(schema)}
        return render_template("recensement_fiche.html", **ctx, tables=tables, sections=sections(schema),
                               annees=annees_proches(config.ANNEE_ACTIVE), OUINON=OUINON, TYPES=TYPES)

    @app.route("/recensement/fiche/<typ>/enregistrer", methods=["POST"])
    @H.connexion_requise("recensement")
    def recensement_enregistrer(typ):
        """Enregistre les valeurs saisies. JSON {annee, valeurs:{clé: valeur}} (formulaire web) ou formulaire
        classique (champs nommés par leur clé). Les champs vides reprennent la valeur calculée."""
        typ_ou_404(typ)
        donnees = request.get_json(silent=True)
        if isinstance(donnees, dict):
            annee = annee_valide(donnees.get("annee"), config.ANNEE_ACTIVE)
            brut = donnees.get("valeurs") if isinstance(donnees.get("valeurs"), dict) else {}
            if len(json.dumps(brut)) > 600_000:
                return jsonify(ok=False, erreurs=["Données trop volumineuses."]), 400
        else:
            annee = annee_req()
            brut = {k: (request.form.getlist(k) if len(request.form.getlist(k)) > 1 else request.form.get(k))
                    for k in request.form if k != "annee"}
        propres, erreurs, _inc = valider_saisies(typ, brut)
        json_ = isinstance(donnees, dict)
        if erreurs:
            if json_:
                return jsonify(ok=False, erreurs=erreurs[:20], n=len(erreurs)), 400
            for m in erreurs[:8]:
                flash(m, "danger")
            return redirect(url_for("recensement_fiche", typ=typ, annee=annee))
        if not json_:   # formulaire partiel : on complète les valeurs déjà enregistrées
            anciens = lire_saisies(typ, annee)[0]
            anciens.update(propres)
            propres = anciens
        ecrire_saisies(typ, annee, propres)
        H.journal("recensement_enregistrer", f"{typ} {annee} ({len(propres)} valeurs saisies)")
        if json_:
            return jsonify(ok=True, n=len(propres))
        flash("Fiche enregistrée.", "success")
        return redirect(url_for("recensement_fiche", typ=typ, annee=annee))

    @app.route("/recensement/fiche/<typ>/pdf")
    @H.connexion_requise("recensement")
    def recensement_pdf(typ):
        schema = typ_ou_404(typ)
        annee = annee_req()
        vierge = request.args.get("vierge") == "1"
        guide = request.args.get("guide", "1") != "0"
        if vierge:
            eff, dyn = valeurs_vierges(schema)   # fonctions pré-imprimées du modèle
            sig = None
        else:
            ctx = contexte(typ, annee)
            eff, dyn = ctx["eff"], ctx["dyn"]
            sig = H.pdfs.image_data_url(H.signature(f"ecole:{H.eco()}:directeur"))
        contenu = pdf_fiche(schema, eff, dyn, annee, sig=sig, guide=guide)
        nom = f"recensement_{typ}_{annee}{'_vierge' if vierge else ''}.pdf"
        return H.pdf_reponse(contenu, nom)

    @app.route("/recensement/fiche/<typ>/excel")
    @H.connexion_requise("recensement")
    def recensement_excel(typ):
        schema = typ_ou_404(typ)
        ctx = contexte(typ, annee_req())
        eff, orig = ctx["eff"], ctx["orig"]
        e = g.get("ecole")
        haut = [schema["titre_court"] + f" – année scolaire {ctx['annee']}", f"École : {e['nom'] if e else ''}"]
        lignes = []
        for s, it, ch in champs_simples(schema):
            v = eff.get(ch["k"], "")
            if isinstance(v, list):
                v = "; ".join(v)
            elif ch["t"] == "case":
                v = "X" if v == "1" else ""
            elif ch["t"] in NUMERIQUES_CHAMP and nombre(v) is not None:
                v = nombre(v) if not nombre(v).is_integer() else int(nombre(v))
            lignes.append([s["num"] if s else "—", libelle_champ(s, it, ch), v, orig.get(ch["k"], "")])
        feuilles_x = [("Rubriques", ["Rubrique", "Libellé", "Valeur", "Origine"], lignes, {"titre_haut": haut})]
        for s, t in tableaux(schema):
            leaves = feuilles(t["cols"])
            noms = chemins(t["cols"])
            data = []
            for r in lignes_tableau(t, ctx["dyn"].get(t["k"])):
                ligne = [((r["groupe"] + " › ") if r["groupe"] else "") + r["lib"]]
                for c in leaves:
                    v = eff.get(f"{t['k']}.{r['k']}.{c['k']}", "")
                    if c["t"] == "c":
                        v = "X" if v == "1" else ""
                    elif c["t"] in NUMERIQUES_CELLULE and nombre(v) is not None:
                        v = int(nombre(v)) if nombre(v).is_integer() else nombre(v)
                    ligne.append(v)
                data.append(ligne)
            titre = f"R{s['num']} {t['titre'] or t['k']}"
            feuilles_x.append((titre[:31], [t["coin"] or "Ligne"] + [noms[c["k"]] for c in leaves], data,
                               {"titre_haut": haut + [f"Rubrique {s['num']}. {s['titre']}"]}))
        feuilles_x.append(("Contrôles", ["Contrôle de cohérence"], [[m] for m in ctx["ctrl"]]
                           or [["Aucune incohérence détectée."]], {"titre_haut": haut}))
        feuilles_x.append(("Données (import)", ["Clé", "Valeur saisie", "Libellé"],
                           [[k, "; ".join(v) if isinstance(v, list) else v, libelle_cle(typ, k)]
                            for k, v in ctx["saisies"].items()],
                           {"titre_haut": ["Valeurs saisies (à modifier puis réimporter : Recensement › Importer)",
                                           f"type={typ} ; année={ctx['annee']}"]}))
        try:
            return H.xlsx.reponse_classeur(f"recensement_{typ}_{ctx['annee']}.xlsx", feuilles_x)
        except H.xlsx.ExcelIndisponible as err:
            flash(str(err), "danger")
            return redirect(url_for("recensement_fiche", typ=typ, annee=ctx["annee"]))

    @app.route("/recensement/fiche/<typ>/import", methods=["POST"])
    @H.connexion_requise("recensement")
    def recensement_import(typ):
        """Réimporte la feuille « Données (import) » d'un export Excel de la fiche."""
        typ_ou_404(typ)
        annee = annee_req()
        f = request.files.get("fichier")
        retour = redirect(url_for("recensement_fiche", typ=typ, annee=annee))
        if not f or not f.filename.lower().endswith(".xlsx"):
            flash("Choisissez le fichier Excel (.xlsx) exporté depuis cette fiche.", "danger")
            return retour
        try:
            import openpyxl
        except ImportError:
            flash("Le composant Excel (openpyxl) n'est pas installé.", "danger")
            return retour
        try:
            wb = openpyxl.load_workbook(io.BytesIO(f.read()), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            flash("Fichier Excel illisible.", "danger")
            return retour
        ws = next((w for w in wb.worksheets if w.title.lower().startswith("données")), None)
        if ws is None:
            flash("Feuille « Données (import) » introuvable : utilisez un fichier exporté par GESCOL.", "danger")
            return retour
        brut, entete = {}, False
        for row in ws.iter_rows(values_only=True):
            if not row or row[0] is None:
                continue
            if not entete:
                entete = str(row[0]).strip().lower() == "clé"
                continue
            brut[str(row[0]).strip()] = row[1] if len(row) > 1 and row[1] is not None else ""
        propres, erreurs, inconnues = valider_saisies(typ, brut)
        for m in erreurs[:6]:
            flash(m, "warning")
        anciens = lire_saisies(typ, annee)[0]
        anciens.update(propres)
        ecrire_saisies(typ, annee, anciens)
        H.journal("recensement_import", f"{typ} {annee} : {len(propres)} valeurs")
        flash(f"{len(propres)} valeur(s) importée(s)" + (f", {inconnues} clé(s) ignorée(s)" if inconnues else "")
              + (f", {len(erreurs)} valeur(s) rejetée(s)" if erreurs else "") + ".", "success")
        return retour

    # ------------------------------------------------------------------ téléversement des fiches officielles
    @app.route("/recensement/depots", methods=["POST"])
    @H.connexion_requise("recensement")
    def recensement_depot():
        annee = annee_req()
        typ = request.form.get("type_doc", "autre")
        typ = typ if typ in TYPES_DEPOT else "autre"
        retour = redirect(request.form.get("retour") if str(request.form.get("retour", "")).startswith("/recensement")
                          else url_for("recensement_accueil", annee=annee))
        f = request.files.get("fichier")
        if not f or not f.filename:
            flash("Choisissez un fichier (PDF ou image).", "danger")
            return retour
        contenu = f.read(TAILLE_MAX_DEPOT + 1)
        if len(contenu) > TAILLE_MAX_DEPOT:
            flash("Fichier trop volumineux (15 Mo au maximum).", "danger")
            return retour
        ext, mime = type_fichier(contenu[:16])
        if not ext:
            flash("Format non accepté : déposez un PDF ou une image (JPEG, PNG, WebP).", "danger")
            return retour
        nom = f"{annee}_{typ}_{uuid.uuid4().hex[:12]}{ext}"
        with open(os.path.join(dossier_depots(), nom), "wb") as out:
            out.write(contenu)
        libelle = (request.form.get("libelle") or "").strip()[:120] or TYPES_DEPOT[typ]
        ex("INSERT INTO recensement_depots (ecole_id, annee, type_doc, libelle, fichier, nom_original, mime, taille, "
           "depose_le, depose_par) VALUES (?,?,?,?,?,?,?,?,?,?)",
           (H.eco(), annee, typ, libelle, nom, os.path.basename(f.filename)[:120], mime, len(contenu), H.maintenant(),
            g.user["nom"]))
        H.journal("recensement_depot", f"{typ} {annee} {f.filename}")
        flash("Document téléversé et archivé.", "success")
        return retour

    def depot_ou_404(did):
        d = q("SELECT * FROM recensement_depots WHERE id=? AND ecole_id=?", (did, H.eco()), un=True)
        if not d:
            abort(404)
        return d

    @app.route("/recensement/depots/<int:did>")
    @H.connexion_requise("recensement")
    def recensement_depot_fichier(did):
        d = depot_ou_404(did)
        chemin = os.path.join(dossier_depots(), d["fichier"])
        if not os.path.exists(chemin):
            abort(404)
        return send_file(chemin, mimetype=d["mime"], as_attachment=request.args.get("telecharger") == "1",
                         download_name=d["nom_original"] or d["fichier"])

    @app.route("/recensement/depots/<int:did>/supprimer", methods=["POST"])
    @H.connexion_requise("recensement")
    def recensement_depot_supprimer(did):
        d = depot_ou_404(did)
        try:
            os.remove(os.path.join(dossier_depots(), d["fichier"]))
        except OSError:
            pass
        ex("DELETE FROM recensement_depots WHERE id=?", (did,))
        H.journal("recensement_depot_supprime", d["fichier"])
        flash("Document supprimé.", "success")
        return redirect(url_for("recensement_accueil", annee=d["annee"]))
