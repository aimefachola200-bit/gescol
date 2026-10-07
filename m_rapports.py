# -*- coding: utf-8 -*-
"""Rapports de RENTRÉE et de FIN D'ANNÉE des écoles primaires (EP) et maternelles (EM)
— éléments de la « carte d'identité de l'école » (édition publique, chargé aussi en édition privée).

Principe
--------
* Chaque document est décrit par un SCHÉMA déclaratif (rubriques → champs / tableaux / état nominatif) qui couvre
  tous les renseignements du modèle officiel (voir ``schema(doc)``).
* Les valeurs AUTOMATIQUES sont calculées à partir de GESCOL (école, classes, élèves, personnel, cantine,
  évaluations…) ; l'utilisateur peut corriger n'importe quelle case : seules les CORRECTIONS sont enregistrées
  (clé ``e<école>:rapports:<doc>:<année>`` dans documents_modules) avec un instantané complet des valeurs.
  Vider une case = revenir à la valeur calculée. « - » = case volontairement laissée sans objet.
* Les renseignements stables (année de création, références, infrastructures, mobilier, diplômes…) sont repris
  du rapport « frère » de la même année (rentrée ↔ fin d'année) ou du rapport de l'année précédente.
* PDF : reproduction de la mise en forme de chaque modèle (mêmes rubriques, cadres, tableaux, numérotation),
  version remplie ou vierge ; annexe GESCOL facultative (résultats, CEP, présence, âges, cantine).
* Export Excel (même structure) ; téléversement du rapport officiel scanné (archive par année).
"""
import io
import json
import os
import re
import unicodedata
from datetime import date, datetime

from flask import abort, flash, g, redirect, render_template, request, send_file, url_for

NIV_EP = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
SECTIONS_EM = [("pet", "Section des petits", "Maternelle 1"), ("gra", "Section des grands", "Maternelle 2")]
NIV_EM = [s[2] for s in SECTIONS_EM]
PERS_MAX = 60

DOCS = {
    "rentree-ep": {"court": "Rentrée EP", "titre": "Rapport de rentrée – écoles primaires", "cycle": "primaire",
                   "moment": "rentree", "fiche": "FICHE DE RAPPORT DE RENTREE DES ECOLES PRIMAIRES",
                   "direction": "DIRECTION DE L'ENSEIGNEMENT PRIMAIRE"},
    "fin-ep": {"court": "Fin d'année EP", "titre": "Fiche de fin d'année – écoles primaires", "cycle": "primaire",
               "moment": "fin", "fiche": "FICHE DE FIN D’ANNÉE DES ÉCOLES PRIMAIRES",
               "direction": "DIRECTION DE L'ENSEIGNEMENT PRIMAIRE"},
    "rentree-em": {"court": "Rentrée EM", "titre": "Rapport de rentrée – écoles maternelles", "cycle": "maternelle",
                   "moment": "rentree", "fiche": "FICHE DE RAPPORT DE RENTREE DES ECOLES MATERNELLES",
                   "direction": "DIRECTION DE L'ENSEIGNEMENT MATERNEL"},
    "fin-em": {"court": "Fin d'année EM", "titre": "Fiche de fin d'année – écoles maternelles", "cycle": "maternelle",
               "moment": "fin", "fiche": "FICHE DE FIN D’ANNÉE DES ÉCOLES MATERNELLES",
               "direction": "DIRECTION DE L'ENSEIGNEMENT PRIMAIRE"},
}
SOEUR = {"rentree-ep": "fin-ep", "fin-ep": "rentree-ep", "rentree-em": "fin-em", "fin-em": "rentree-em"}
STATUTS_AGENT = ["FE", "ACE", "Aspirant", "CNR", "Stagiaire", "Suppléant", "PRIVE", "Autre"]
EXT_OK = {".pdf": b"%PDF", ".jpg": b"\xff\xd8", ".jpeg": b"\xff\xd8", ".png": b"\x89PNG"}
RE_ANNEE = re.compile(r"^(\d{4})-(\d{4})$")


# =====================================================================================================
# 1. SCHÉMAS DÉCLARATIFS
# =====================================================================================================
def _champ(k, lib, type_="texte", num="", **kw):
    d = {"t": "champ", "k": k, "lib": lib, "type": type_, "num": num}
    d.update(kw)
    return d


def _choix(k, lib, options, num="", **kw):
    return _champ(k, lib, "choix", num, options=options, **kw)


def _tab(k, lignes, groupes, sous=None, **kw):
    """Tableau : lignes [(code, libellé)] ; groupes [{c, l, total?, somme?}] ; sous-colonnes communes [(code, lib)]."""
    d = {"t": "tableau", "k": k, "lignes": lignes, "groupes": groupes, "sous": sous}
    d.update(kw)
    return d


def _g(c, lib, **kw):
    d = {"c": c, "l": lib}
    d.update(kw)
    return d


GFT = [("G", "G"), ("F", "F"), ("T", "T")]
FGT = [("F", "F"), ("G", "G"), ("T", "T")]


def _pcol(c, lib, type_="texte", **kw):
    d = {"c": c, "l": lib, "type": type_}
    d.update(kw)
    return d


def colonnes_personnel(doc):
    base = [_pcol("mat", "N° matricule (1)"), _pcol("nip", "NIP"), _pcol("nom", "Nom et prénoms", larg=14),
            _pcol("sexe", "Sexe (2)", "choix", options=["M", "F"]), _pcol("naiss", "Année de naissance", "annee"),
            _pcol("dacad", "Diplôme académique le plus élevé (3)"),
            _pcol("dprof", "Diplôme professionnel le plus élevé (3)"), _pcol("grade", "Grade"),
            _pcol("statut", "Statut (4)", liste=STATUTS_AGENT), _pcol("fonction", "Fonction")]
    anc = [_pcol("indice", "Indice réel"), _pcol("afp", "Ancienneté : fonction publique (ans)", "nombre"),
           _pcol("adep", "Ancienneté : département (ans)", "nombre"), _pcol("aecole", "Ancienneté : école (ans)", "nombre")]
    visites = [_pcol("vinsp", "Visites : inspecteur", "nombre"), _pcol("vcp", "Visites : conseiller pédagogique", "nombre"),
               _pcol("vdir", "Visites : directeur", "nombre"), _pcol("pup", "% participation aux UP", "pct")]
    if doc == "rentree-ep":
        return base + [_pcol("cours", "Cours tenus (CI…CM2)", "cours")] + anc + [
            _pcol("form", "Date de la dernière formation continue (5)")]
    if doc == "fin-ep":
        return base + [_pcol("cours", "Cours tenus (CI…CM2)", "cours")] + anc + [
            _pcol("form", "Date de la dernière formation continue (5)")] + visites
    em = [_pcol("qualite", "Qualité (5)", "choix", options=["Instituteur", "Educateur"]),
          _pcol("section", "Section tenue", "choix", options=["Petits", "Grands", "Petits et grands"])]
    if doc == "rentree-em":
        return base + em + anc + [_pcol("fdate", "Dernière formation : date"),
                                  _pcol("fnature", "Dernière formation : nature (6)"), _pcol("obs", "Observations")]
    return base + em + anc + visites


def schema(doc):
    """Liste des rubriques du document : [{id, titre, blocs}] (100 % des renseignements du modèle)."""
    info = DOCS[doc]
    ep = info["cycle"] == "primaire"
    fin = info["moment"] == "fin"
    S = []
    # ---------------------------------------------------------------- 1. identification
    b = [_champ("nom_ecole", "Nom de l'école", num="1.1", larg="long"),
         _champ("annee_creation", "Année de création", "annee", "1.2"),
         _champ("ref_creation", "Référence (acte de création)", num="1.2"),
         _champ("annee_extension", "Année d'extension" if ep else "Année dernière extension", "annee", "1.3"),
         _champ("ref_extension", "Référence (acte d'extension)", num="1.3"),
         _choix("statut", "Statut", ["Public", "Privé", "Communautaire"] if ep else
                ["Public", "Privé", "Centre préscolaire communautaire"], "1.4"),
         _champ("initiative", "Si communautaire, précisez l'initiative", num="1.4", larg="long")]
    if ep:
        b.append(_champ("reseau_titre", "", "titre", lib_titre="1.5 Localisation dans le réseau d'animation pédagogique"))
        num = iter(["i-", "ii-", "iii-", "iv-"])
        b += [_champ("cs", "Circonscription scolaire", num=next(num)), _champ("zone", "Zone pédagogique", num=next(num)),
              _champ("up", "Unité pédagogique", num=next(num)),
              _champ("admin_titre", "", "titre", lib_titre="1.6 Localisation dans l'administration territoriale"),
              _champ("departement", "Département", num="i-"), _champ("commune", "Commune", num="ii-"),
              _champ("arrondissement", "Arrondissement", num="iii-"),
              _champ("village", "Village ou quartier de ville", num="iv-"),
              _champ("bp", "Adresse : boîte postale", num="1.8"), _champ("telephone", "Téléphone", "tel", "1.8"),
              _champ("email", "E-mail", "email", "1.8", larg="long")]
    else:
        n = 5
        for k, lib in [("departement", "Département"), ("commune", "Commune"), ("arrondissement", "Arrondissement")] + \
                [("cs", "Circonscription scolaire"), ("zone", "Zone pédagogique"), ("up", "Unité pédagogique"),
                 ("village", "Village ou quartier de ville"), ("adresse_postale", "Adresse postale"),
                 ("contact_directeur", "Contact du Directeur/Directrice")]:
            b.append(_champ(k, lib, "tel" if k == "contact_directeur" else "texte", f"1.{n}"))
            n += 1
    S.append({"id": "ident", "titre": ("1. " if ep or fin else "I. ") + "Identification et localisation de l'école",
              "blocs": b})
    # ---------------------------------------------------------------- 2. informations générales
    if ep:
        b = [_champ("fondateur", "Nom et prénoms du Fondateur/Fondatrice (uniquement pour le privé)", num="2.1", larg="long"),
             _choix("directeur_titre", "Direct… (titre)", ["Directeur", "Directrice"], "2.2"),
             _champ("directeur_nom", "Nom et prénoms du Directeur / de la Directrice", num="2.2", larg="long"),
             _champ("classes_autorisees", "Nombre de classes autorisées", "nombre", "2.3"),
             _champ("classes_ouvertes", "Nombre de classes ouvertes", "nombre", "2.3"),
             _champ("salles_existantes", "Nombre de salles de classe existantes", "nombre", "2.3"),
             _champ("salles_utilisees", "Nombre de salles de classe utilisées", "nombre", "2.3"),
             _choix("cantine", "L'école dispose-t-elle d'une cantine ?", ["OUI", "NON"], "1.7"),
             _choix("cantine_fonctionne", "Si oui, a-t-elle fonctionné ?", ["OUI", "NON"], "1.7"),
             _champ("cantine_raison", "Si non, donnez la raison", num="1.7", larg="long"),
             {"t": "structure_ep", "k": "sp", "titre": "2.4 Structure pédagogique",
              "jumelees": ([("CI_CP", "CI-CP"), ("CP_CE1", "CP-CE1"), ("CE1_CE2", "CE1-CE2"), ("CE2_CM1", "CE2-CM1"),
                            ("CM1_CM2", "CM1-CM2")] if fin else
                           [("CI_CP", "CI-CP"), ("CE1_CE2", "CE1-CE2"), ("CM1_CM2", "CM1-CM2")])}]
        S.append({"id": "gen", "titre": "2. Informations générales", "blocs": b})
    else:
        b = [_champ("fondateur", "Nom et prénoms du fondateur/fondatrice (pour les EM privées)", num="2.1", larg="long"),
             _choix("directeur_titre", "Directeur/Directrice (titre)", ["Directeur", "Directrice"], "2.2"),
             _champ("directeur_nom", "Nom et prénoms du Directeur/Directrice", num="2.2", larg="long"),
             _champ("sections_autorisees", "Nombre de sections autorisées", "nombre", "2.3"),
             _champ("sections_ouvertes", "Nombre de sections ouvertes", "nombre", "2.3"),
             _champ("salles_existantes", "Nombre de salles de classe existantes", "nombre", "2.4"),
             _champ("salles_utilisees", "Nombre de salles de classe utilisées", "nombre", "2.4"),
             _choix("cantine", "L'école dispose-t-elle d'une cantine fonctionnelle ?", ["oui", "non"], "2.5"),
             _champ("cantine_organisme", "Si oui, précisez l'organisme de soutien", num="2.5", larg="long"),
             _choix("lavage", "Dispositif de lavage de main fonctionnel ?", ["oui", "non"], "2.6"),
             _choix("gestion", "Structure de gestion collégiale ?", ["oui", "non"], "2.7"),
             _choix("g_ape", "Si oui : APE", ["oui", "non"], "2.7"),
             _choix("g_ame", "Si oui : AME", ["oui", "non"], "2.7"),
             _choix("g_comite", "Si oui : Comité de direction", ["oui", "non"], "2.7"),
             _champ("g_autres", "Autres à préciser", num="2.7", larg="long")]
        S.append({"id": "gen", "titre": "II. Informations générales", "blocs": b})
    # ---------------------------------------------------------------- 3. effectifs
    if ep:
        lignes = ([("debut", "Nombre d'élèves en début d'année"), ("fin", "Nombre d'élèves fin d'année"),
                   ("promus", "Promus"), ("red", "Redoublants"), ("aband", "Abandons")] if fin else
                  [("nb", "Nombre d'élèves"), ("red", "Dont redoublants"),
                   ("transf", "Dont élèves venus d'autres écoles (Transférés)"),
                   ("sans_acte", "Dont élèves sans acte de naissance"), ("handic", "Dont handicapés")])
        S.append({"id": "eff", "titre": "3. Effectif des élèves par sexe et par classe", "blocs": [
            _tab("eff", lignes, [_g(n, n) for n in NIV_EP] + [_g("ENS", "ENSEMBLE", total=True)], GFT)]})
    else:
        lignes = ([("debut", "Effectif au début de l'année"), ("fin", "Effectif en fin de l'année"),
                   ("besoin", "Dont enfants à besoin spécifique"), ("aband", "Abandons")] if fin else
                  [("debut", "Effectif au début de l'année"), ("besoin", "Dont enfants à besoin spécifique")])
        S.append({"id": "rep", "titre": "III. Répartition des enfants par section", "blocs": [
            _tab("rep", lignes, [_g("pet", "Section des petits"), _g("gra", "Section des grands"),
                                 _g("tot", "Total de l'école", total=True)], FGT)]})
    # ---------------------------------------------------------------- EP : 4 à 7 / EM : IV à X
    if ep:
        S.append({"id": "infra", "titre": "4. Infrastructures", "blocs": [
            _tab("infra", [("salles", "Salles de classe"), ("bureau", "Bureau/Magasin")],
                 [_g("def", "En matériaux définitifs (a)"), _g("prov", "En matériaux provisoires (b)"),
                  _g("sans", "Sans mur et sans toit"), _g("tot", "Total (a+b)", somme=["def", "prov"])])]})
        ens = [_g(n, n) for n in NIV_EP] + [_g("ENS", "ENSEMBLE", total=True)]
        S.append({"id": "mob", "titre": "5. Mobilier", "blocs": [
            _tab("mob", [("table_chaise", "Table + chaise"), ("tb2", "Table-banc à 2 places"),
                         ("tb3", "Table-banc à 3 places et plus"), ("bureau", "Bureau du maître + chaise")], ens)]})
        S.append({"id": "man", "titre": "6. Manuels", "blocs": [
            _tab("man", [("fr", "Manuel de français"), ("math", "Manuel de Maths")], ens)]})
        if fin:
            S.append({"id": "gest", "titre": "7. Fonctionnement des structures de gestion", "blocs": [
                _tab("gest", [("nb", "Nombre")], [_g("ag", "Assemblée Générale"), _g("ape", "Réunion bureau APE"),
                                                  _g("cm", "Conseil des maîtres")])]})
    else:
        S.append({"id": "sp", "titre": "IV. Structure pédagogique", "blocs": [
            _tab("sp", [("simple", "Simple"), ("jumelee", "Jumelée"), ("multi", "Multigrade")],
                 [_g("pet", "Nombre de sections des petits"), _g("gra", "Nombre de section des grands"),
                  _g("salles", "Nombre de salles de classe")])]})
        S.append({"id": "matped", "titre": "V. Matériel pédagogique", "blocs": [
            _tab("matped", [("nb", "Nombre")], [_g("paeapem", "Programmes d'activités (PAEAPEM)"),
                                                _g("guides", "Guides pédagogiques"), _g("recueils", "Recueils de jeux"),
                                                _g("autres", "Autres (à préciser)")]),
            _champ("matped_autres_lib", "Autres matériels pédagogiques (préciser)", larg="long")]})
        S.append({"id": "infra", "titre": "VI. Infrastructure (écrire le nombre)", "blocs": [
            _tab("infra", [("salles", "Salles de classe"), ("bureau", "Bureaux/Magasins")],
                 [_g("def", "Matériaux définitifs (a)"), _g("prov", "Matériaux provisoires (b)"),
                  _g("sans", "Sans mur et sans toît"), _g("cons", "En construction"),
                  _g("tot", "Total (a+b)", somme=["def", "prov"])])]})
        S.append({"id": "mob", "titre": "VII. Mobilier (mentionner chaque fois le nombre correspondant)", "blocs": [
            _tab("mob", [("nb", "Nombre")], [
                _g("bur_ens", "Bureaux enseignants"), _g("ch_ens", "Chaises enseignants"),
                _g("armoires", "Armoires et placards"), _g("tables_jeux", "Tables de jeux"), _g("tablettes", "Tablettes"),
                _g("ch_enf", "Chaises pour enfants"), _g("tables_enf", "Tables pour enfants"), _g("nattes", "Nattes"),
                _g("autre1", "Autres (1)"), _g("autre2", "Autres (2)")]),
            _champ("mob_autre1_lib", "Autres (1) : préciser"), _champ("mob_autre2_lib", "Autres (2) : préciser")]})
        S.append({"id": "ext", "titre": "VIII. Équipements extérieurs (mentionner chaque fois le nombre correspondant)",
                  "blocs": [_tab("ext", [("nb", "Nombre")], [
                      _g("tourniquet", "Tourniquet"), _g("cage", "Cage à écureuil"), _g("escalier", "Escalier de géant"),
                      _g("toboggan", "Toboggan"), _g("bac", "Bac à sable"), _g("balancoire", "Balançoire"),
                      _g("corde", "Corde à grimper"), _g("tunnel", "Tunnel"), _g("poutre", "Poutre équipement"),
                      _g("filet", "Ensemble filet échelle")]),
                      _champ("ext_autres", "Autres à préciser", larg="long")]})
        S.append({"id": "int", "titre": "IX. Équipements intérieurs (cocher la case correspondant)", "blocs": [
            _tab("int", [("nb", "Nombre")], [
                _g("peinture", "Piste de peinture"), _g("encastrement", "Encastrement"), _g("puzzle", "Puzzle"),
                _g("graphisme", "Matériel de graphisme et de dessin"), _g("chevalet", "Tableau sur chevalet"),
                _g("muraux", "Tableaux muraux"), _g("presentoir", "Présentoir"), _g("bricolage", "Matériel de bricolage")]),
            _champ("int_autres", "Autres à préciser", larg="long")]})
        S.append({"id": "gest", "titre": "X. Fonctionnement des structures de gestion", "blocs": [
            _tab("gest", [("nb", "Nombre")], [_g("ag", "Assemblée générale"), _g("cm", "Conseil des maîtres"),
                                              _g("ame", "Réunion AME (Association des Mères d'Enfants)"),
                                              _g("ape", "Réunion APE (Association des Parents d'Elèves)")])]})
    # ---------------------------------------------------------------- état nominatif + signatures
    mini = {"rentree-ep": 12, "fin-ep": 12, "rentree-em": 10, "fin-em": 9}[doc]
    S.append({"id": "pers", "titre": ("7. " if ep else "XI. ") + "État nominatif du personnel enseignant",
              "blocs": [{"t": "personnel", "k": "pers", "min": mini, "cols": colonnes_personnel(doc)}]})
    b = [_champ("date_remplissage", "Date de remplissage", "date"), _champ("par_nom", "Par Madame / Monsieur"),
         _champ("par_fonction", "Fonction"),
         _choix("sig_dir", "Apposer la signature numérique du directeur", ["Oui", "Non"]),
         _choix("cachet", "Apposer le cachet de l'école", ["Oui", "Non"]),
         _champ("cp_zone_num", "Conseiller pédagogique : zone n°"), _champ("cp_nom", "Nom du conseiller pédagogique"),
         _champ("rup_nom", "Nom du responsable de l'unité pédagogique")]
    b.append(_champ("chef_nom", "Nom du Chef de la Circonscription Scolaire"))
    S.append({"id": "sig", "titre": "Visas, signatures et contrôles", "blocs": b})
    if ep:
        S.append({"id": "annexe", "titre": "Annexe GESCOL (facultative) : résultats au CEP", "annexe": True, "blocs": [
            _champ("cep_session", "Session du CEP concernée (année)", "annee"),
            _tab("cep", [("insc", "Candidats inscrits"), ("pres", "Candidats présents"), ("adm", "Candidats admis")],
                 [_g("G", "Garçons"), _g("F", "Filles"), _g("T", "Total", somme=["G", "F"])])]})
    return S


# ------------------------------------------------------------------ parcours du schéma
def calculs_tableau(b):
    """Cellules calculées d'un tableau : {clé: [clés sources]} (T = G + F ; ENSEMBLE = somme ; Total (a+b))."""
    calc = {}
    k, gs, sous = b["k"], b["groupes"], b.get("sous")
    for lc, _ in b["lignes"]:
        for gr in gs:
            if sous:
                codes = [s for s, _ in sous]
                for s in codes:
                    cle = f"{k}.{lc}.{gr['c']}_{s}"
                    if gr.get("total"):
                        calc[cle] = [f"{k}.{lc}.{h['c']}_{s}" for h in gs if not h.get("total")]
                    elif s == "T" and "G" in codes and "F" in codes:
                        calc[cle] = [f"{k}.{lc}.{gr['c']}_G", f"{k}.{lc}.{gr['c']}_F"]
            else:
                cle = f"{k}.{lc}.{gr['c']}"
                if gr.get("somme"):
                    calc[cle] = [f"{k}.{lc}.{x}" for x in gr["somme"]]
                elif gr.get("total"):
                    calc[cle] = [f"{k}.{lc}.{h['c']}" for h in gs if not h.get("total")]
    return calc


def cles_tableau(b):
    k, sous = b["k"], b.get("sous")
    for lc, llib in b["lignes"]:
        for gr in b["groupes"]:
            if sous:
                for s, slib in sous:
                    yield f"{k}.{lc}.{gr['c']}_{s}", f"{llib} – {gr['l']} {slib}"
            else:
                yield f"{k}.{lc}.{gr['c']}", f"{llib} – {gr['l']}"


def cles_structure(b):
    for n in NIV_EP:
        yield f"sp.simple.{n}", f"Structure : simple {n}"
    yield "sp.simple.salles", "Structure : simple – salles utilisées"
    for c, lib in b["jumelees"]:
        yield f"sp.jumelee.{c}", f"Structure : jumelée {lib}"
    yield "sp.jumelee.salles", "Structure : jumelée – salles utilisées"
    for n in NIV_EP:
        yield f"sp.multi.{n}", f"Structure : multigrade {n}"
    yield "sp.multi.salles", "Structure : multigrade – salles utilisées"


def tous_calculs(doc):
    calc = {}
    for s in schema(doc):
        for b in s["blocs"]:
            if b["t"] == "tableau":
                calc.update(calculs_tableau(b))
    return calc


def bloc_personnel(doc):
    for s in schema(doc):
        for b in s["blocs"]:
            if b["t"] == "personnel":
                return b
    return None


def nb_lignes_personnel(doc, v):
    b = bloc_personnel(doc)
    try:
        n = int(str(v.get("pers_n") or 0))
    except ValueError:
        n = 0
    return max(b["min"], min(PERS_MAX, n))


def champs_editables(doc, n_pers=None, v=None):
    """[(clé, spec)] de TOUTES les cases saisissables du document (hors cellules calculées)."""
    calc = tous_calculs(doc)
    out = []
    for s in schema(doc):
        for b in s["blocs"]:
            if b["t"] == "champ" and b["type"] != "titre":
                out.append((b["k"], b))
            elif b["t"] == "choix" or (b["t"] == "champ" and b["type"] == "choix"):
                out.append((b["k"], b))
            elif b["t"] == "tableau":
                for k, lib in cles_tableau(b):
                    if k not in calc:
                        out.append((k, {"k": k, "lib": lib, "type": "nombre"}))
            elif b["t"] == "structure_ep":
                for k, lib in cles_structure(b):
                    out.append((k, {"k": k, "lib": lib, "type": "nombre"}))
            elif b["t"] == "personnel":
                n = n_pers if n_pers is not None else nb_lignes_personnel(doc, v or {})
                out.append(("pers_n", {"k": "pers_n", "lib": "Nombre de lignes de l'état nominatif", "type": "nombre"}))
                for i in range(1, n + 1):
                    for col in b["cols"]:
                        k = f"pers.{i}.{col['c']}"
                        spec = dict(col, k=k, lib=f"Personnel, ligne {i} – {col['l']}")
                        out.append((k, spec))
    # dédoublonnage (un choix est à la fois 'champ' et 'choix')
    vus, res = set(), []
    for k, sp in out:
        if k not in vus:
            vus.add(k)
            res.append((k, sp))
    return res


def valeurs_calculees(doc, v):
    """Valeurs finales : valeurs fusionnées + cellules calculées (sommes)."""
    calc = tous_calculs(doc)
    memo = {}

    def val(k):
        if k in memo:
            return memo[k]
        if k in calc:
            nums = [entier(val(s)) for s in calc[k]]
            nums = [n for n in nums if n is not None]
            r = str(sum(nums)) if nums else ""
        else:
            r = "" if v.get(k) is None else str(v.get(k))
        memo[k] = r
        return r

    out = dict(v)
    for k in calc:
        out[k] = val(k)
    return out


# =====================================================================================================
# 2. OUTILS
# =====================================================================================================
def normaliser(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def entier(v):
    try:
        s = str(v).strip().replace(" ", "")
        if not s or s == "-":
            return None
        return int(float(s.replace(",", "."))) if re.match(r"^\d+([.,]0+)?$", s) else None
    except (TypeError, ValueError):
        return None


def vrai(v):
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    return normaliser(v) not in ("", "0", "non", "n", "aucun", "aucune", "neant", "none", "false", "faux", "rien")


def lire_date(s):
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{4})$", s)
    return date(int(m.group(1)), 1, 1) if m else None


def annees_ecoulees(s, ref):
    d = lire_date(s)
    if not d or d > ref:
        return None
    return ref.year - d.year - ((ref.month, ref.day) < (d.month, d.day))


def annee_valide(a, defaut):
    m = RE_ANNEE.match(a or "")
    if m and int(m.group(2)) == int(m.group(1)) + 1 and 1990 <= int(m.group(1)) <= 2100:
        return a
    return defaut


def valider_valeur(spec, brut):
    """(ok, valeur normalisée, message)."""
    t = spec.get("type", "texte")
    if brut == "-":
        return True, "-", ""
    if len(brut) > 300:
        return False, None, "texte trop long (300 caractères au plus)"
    if t == "nombre":
        n = entier(brut)
        if n is None or n > 1_000_000:
            return False, None, f"« {brut} » n'est pas un nombre entier positif"
        return True, str(n), ""
    if t == "pct":
        try:
            x = float(brut.replace(",", ".").replace("%", "").strip())
        except ValueError:
            return False, None, f"« {brut} » n'est pas un pourcentage"
        if not 0 <= x <= 100:
            return False, None, "le pourcentage doit être compris entre 0 et 100"
        return True, (str(int(x)) if x.is_integer() else f"{x:.1f}".replace(".", ",")), ""
    if t == "annee":
        if not re.match(r"^\d{4}$", brut) or not 1850 <= int(brut) <= date.today().year + 1:
            return False, None, f"« {brut} » n'est pas une année valide (4 chiffres)"
        return True, brut, ""
    if t == "email":
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", brut):
            return False, None, f"« {brut} » n'est pas une adresse e-mail valide"
        return True, brut, ""
    if t == "date":
        d = lire_date(brut)
        if not d:
            return False, None, f"« {brut} » n'est pas une date (jj/mm/aaaa)"
        return True, d.strftime("%d/%m/%Y"), ""
    if t == "choix":
        for o in spec.get("options", []):
            if normaliser(o) == normaliser(brut):
                return True, o, ""
        return False, None, "valeur non prévue"
    if t == "cours":
        toks = [x for x in re.split(r"[\s,;/+-]+", brut.upper()) if x]
        mauvais = [x for x in toks if x not in NIV_EP]
        if mauvais:
            return False, None, f"cours inconnu(s) : {', '.join(mauvais)} (CI, CP, CE1, CE2, CM1, CM2)"
        return True, ", ".join(n for n in NIV_EP if n in toks), ""
    return True, re.sub(r"\s+", " ", brut), ""


def cours_de(v):
    return {x for x in re.split(r"[\s,;/+-]+", str(v or "").upper()) if x}


# =====================================================================================================
# 3. DONNÉES GESCOL → VALEURS AUTOMATIQUES
# =====================================================================================================
def _colonnes(H, table):
    try:
        return {r[1] for r in H.q(f"PRAGMA table_info({table})")}
    except Exception:  # noqa: BLE001
        return set()


def _table_existe(H, nom):
    return bool(H.q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nom,), un=True))


def _trouver(d, candidats, motifs=()):
    """Première valeur non vide parmi des noms de colonnes candidats, sinon par motifs (tous les mots présents)."""
    for c in candidats:
        if c in d and d[c] not in (None, ""):
            return d[c]
    for mots in motifs:
        for c, val in d.items():
            if val not in (None, "") and all(m in c for m in mots):
                return val
    return None


def statut_ecole(e, ep):
    s = normaliser(e["statut"] if e else "")
    if s.startswith("publi"):
        return "Public"
    if s.startswith("priv"):
        return "Privé"
    if s.startswith("commun"):
        return "Communautaire" if ep else "Centre préscolaire communautaire"
    return ""


def classes_du_cycle(H, doc):
    niveaux = NIV_EP if DOCS[doc]["cycle"] == "primaire" else NIV_EM
    return [dict(c) for c in H.classes_autorisees() if c["niveau"] in niveaux]


def eleves_des_classes(H, classes):
    if not classes:
        return []
    ids = [c["id"] for c in classes]
    return [dict(e) for e in H.q(f"SELECT * FROM eleves WHERE classe_id IN ({','.join('?' * len(ids))})", ids)]


def _sexe(v):
    s = normaliser(v)
    return "F" if s.startswith("f") else ("G" if s[:1] in ("m", "g", "h") else None)


def personnel_du_cycle(H, doc, classes_cycle, e):
    """Enseignants (et directeur) de l'école pour le cycle du document, avec leurs données de carrière."""
    cols = _colonnes(H, "personnel")
    sql, args = "SELECT * FROM personnel WHERE actif=1", []
    if "ecole_id" in cols:
        sql += " AND (ecole_id=? OR (ecole_id IS NULL AND ?=1))"
        args += [H.eco(), H.eco()]
    rows = [dict(r) for r in H.q(sql + " ORDER BY nom, prenoms", args)]
    carriere = {}
    if _table_existe(H, "personnel_carriere"):
        for r in H.q("SELECT * FROM personnel_carriere"):
            r = dict(r)
            carriere[r.get("personnel_id")] = r
    toutes = [dict(c) for c in H.classes_autorisees()]
    affect = {}
    if "user_id" in cols:
        for a in H.q("SELECT user_id, classe_id FROM affectations"):
            affect.setdefault(a["user_id"], set()).add(a["classe_id"])
    dir_nom = normaliser(e["directeur_nom"] if e else "")
    niveaux_cycle = {c["niveau"] for c in classes_cycle}
    ep = DOCS[doc]["cycle"] == "primaire"
    ecole_a_primaire = any(c["niveau"] in NIV_EP for c in toutes)
    out = []
    for p in rows:
        fct = normaliser(p.get("fonction"))
        noms = {normaliser(f"{p['nom']} {p['prenoms']}"), normaliser(f"{p['prenoms']} {p['nom']}")}
        est_dir = "direct" in fct or (dir_nom and dir_nom in noms)
        if not est_dir and not any(m in fct for m in ("enseign", "instit", "educat", "maitre", "adjoint", "titulaire",
                                                      "professeur", "moniteur")):
            continue
        liees = [c for c in toutes if normaliser(c.get("titulaire_nom")) in noms]
        if p.get("user_id") and p["user_id"] in affect:
            liees += [c for c in toutes if c["id"] in affect[p["user_id"]] and c not in liees]
        niv = [c["niveau"] for c in liees]
        if not est_dir:
            if liees:
                if not any(n in niveaux_cycle for n in niv):
                    continue
            else:  # sans classe : maternelle si la fonction l'indique, sinon primaire (si l'école en a)
                hint_em = "matern" in fct or "educat" in fct
                if ep and (hint_em or not ecole_a_primaire):
                    continue
                if not ep and not (hint_em or not ecole_a_primaire):
                    continue
        d = dict(carriere.get(p["id"], {}))
        d.update({k: v for k, v in p.items() if v not in (None, "")})
        out.append({"p": p, "d": d, "dir": est_dir, "niveaux": [n for n in niv if n in niveaux_cycle]})
    out.sort(key=lambda x: (not x["dir"], normaliser(x["p"]["nom"])))
    return out


def _visites(H, pid, d1, d2):
    """Nombre de visites par type de visiteur (module « visites » s'il existe), sinon None."""
    for t in ("visites", "visites_classe", "visites_pedagogiques"):
        if not _table_existe(H, t):
            continue
        cols = _colonnes(H, t)
        ref = next((c for c in ("personnel_id", "enseignant_id") if c in cols), None)
        typ = next((c for c in ("visiteur_qualite", "visiteur_type", "type_visiteur", "qualite_visiteur", "visiteur")
                    if c in cols), None)
        dcol = "date" if "date" in cols else None
        if not ref or not typ:
            continue
        try:
            sql = f"SELECT {typ} t FROM {t} WHERE {ref}=?" + (f" AND {dcol} BETWEEN ? AND ?" if dcol else "")
            rows = H.q(sql, (pid, d1, d2) if dcol else (pid,))
        except Exception:  # noqa: BLE001
            continue
        res = {"vinsp": 0, "vcp": 0, "vdir": 0}
        for r in rows:
            n = normaliser(r["t"])
            if "inspect" in n or n in ("ccs", "ccs inspecteur"):
                res["vinsp"] += 1
            elif "conseil" in n or n in ("cp", "cpc"):
                res["vcp"] += 1
            elif "direct" in n:
                res["vdir"] += 1
        if not res["vdir"]:
            res.pop("vdir")  # visites du directeur non enregistrées dans GESCOL : case laissée à la saisie
        return res
    return None


def patrimoine_auto(H, doc, v, classes):
    """Infrastructures, mobilier, manuels / matériel pédagogique depuis le module Patrimoine (s'il est installé)."""
    ep = DOCS[doc]["cycle"] == "primaire"
    eco = H.eco()
    niv_de = {c["id"]: c["niveau"] for c in classes}
    if _table_existe(H, "pat_locaux"):
        loc = [dict(r) for r in H.q("SELECT * FROM pat_locaux WHERE ecole_id=?", (eco,))]
        cpt = {}
        for r in loc:
            lig = "salles" if r["type"] == "salle_classe" else ("bureau" if r["type"] in ("bureau", "magasin") else None)
            if not lig:
                continue
            murs, toit = r.get("murs") or "", r.get("toit") or ""
            if murs == "sans_mur" and toit in ("sans_toit", ""):
                col = "sans"
            elif murs in ("dur", "semi_dur") and toit in ("tole", "dalle"):
                col = "def"
            else:
                col = "prov"
            cpt[(lig, col)] = cpt.get((lig, col), 0) + 1
        if loc:
            for lig in ("salles", "bureau"):
                for col in ("def", "prov", "sans"):
                    v[f"infra.{lig}.{col}"] = str(cpt.get((lig, col), 0))
            sc = [r for r in loc if r["type"] == "salle_classe"]
            if sc:
                v["salles_existantes"] = str(len(sc))
                v["salles_utilisees"] = str(sum(1 for r in sc if r.get("utilisee") in (1, "1", None)))
    if _table_existe(H, "pat_mobilier"):
        mob = [dict(r) for r in H.q("SELECT * FROM pat_mobilier WHERE ecole_id=? AND COALESCE(etat,'') != 'mauvais'",
                                    (eco,))]
        if mob:
            if ep:
                lig = {"tb1": "table_chaise", "tb2": "tb2", "tb3": "tb3", "bureau_maitre": "bureau"}
                cpt = {}
                for r in mob:
                    n = niv_de.get(r.get("classe_id"))
                    if r["categorie"] in lig and n:
                        cle = f"mob.{lig[r['categorie']]}.{n}"
                        cpt[cle] = cpt.get(cle, 0) + (r["quantite"] or 0)
                v.update({k: str(x) for k, x in cpt.items()})
            else:
                corr = {"bureau_maitre": "bur_ens", "bureau": "bur_ens", "armoire": "armoires", "etagere": "armoires"}
                cpt = {}
                for r in mob:
                    if r["categorie"] in corr:
                        cle = f"mob.nb.{corr[r['categorie']]}"
                        cpt[cle] = cpt.get(cle, 0) + (r["quantite"] or 0)
                v.update({k: str(x) for k, x in cpt.items()})
    if _table_existe(H, "pat_didactique"):
        did = [dict(r) for r in H.q("SELECT * FROM pat_didactique WHERE ecole_id=? AND COALESCE(etat,'') != 'mauvais'",
                                    (eco,))]
        cpt = {}
        for r in did:
            disc = normaliser(r.get("discipline"))
            if ep and r["categorie"] in ("manuel", "manuel_adapte") and r.get("niveau") in NIV_EP:
                lig = "fr" if disc.startswith(("francais", "lecture")) else ("math" if disc.startswith("math") else None)
                if lig:
                    cle = f"man.{lig}.{r['niveau']}"
                    cpt[cle] = cpt.get(cle, 0) + (r["quantite"] or 0)
            elif not ep and r["categorie"] in ("programme", "guide"):
                cle = "matped.nb." + ("paeapem" if r["categorie"] == "programme" else "guides")
                cpt[cle] = cpt.get(cle, 0) + (r["quantite"] or 0)
        v.update({k: str(x) for k, x in cpt.items()})


def calculer_auto(H, doc, annee):
    """Valeurs calculées depuis GESCOL : ({clé: valeur}, indicateurs pour l'annexe)."""
    info = DOCS[doc]
    ep = info["cycle"] == "primaire"
    fin = info["moment"] == "fin"
    a0 = int(annee[:4])
    e = g.get("ecole")
    v, ind = {}, {}
    active = annee == H.config.ANNEE_ACTIVE
    # ---------------------------------------------------------------- identification (fiche de l'école)
    if e:
        v.update({"nom_ecole": e["nom"] or "", "statut": statut_ecole(e, ep), "cs": e["cs"] or "",
                  "zone": e["zone"] or "", "up": e["up"] or "", "departement": e["departement"] or "",
                  "commune": e["commune"] or "", "village": e["ville"] or "",
                  "directeur_titre": e["directeur_titre"] if e["directeur_titre"] in ("Directeur", "Directrice") else "",
                  "directeur_nom": e["directeur_nom"] or ""})
        if ep:
            v.update({"bp": e["bp"] or "", "telephone": e["telephone"] or "", "email": e["email"] or ""})
        else:
            v.update({"adresse_postale": " ".join(x for x in (e["bp"] or "", e["adresse"] or "") if x),
                      "contact_directeur": e["directeur_tel"] or e["telephone"] or ""})
        v["par_nom"] = e["directeur_nom"] or ""
        v["par_fonction"] = e["directeur_titre"] or "Directeur"
        m = re.search(r"\d+", e["zone"] or "")
        if m:
            v["cp_zone_num"] = m.group(0)
        if fin:
            v["chef_nom"] = e["ccs_nom"] or ""
        v["sig_dir"] = "Oui" if H.signature(f"ecole:{e['id']}:directeur") else "Non"
        v["cachet"] = "Non"
    v["date_remplissage"] = date.today().strftime("%d/%m/%Y")
    classes = classes_du_cycle(H, doc)
    if not active:
        # année passée ou future : les effectifs ne sont pas historisés dans GESCOL → dernier instantané enregistré
        v["pers_n"] = str(bloc_personnel(doc)["min"])
        return v, {"inactive": True}
    eleves = eleves_des_classes(H, classes)
    niv_de = {c["id"]: c["niveau"] for c in classes}
    ecols = _colonnes(H, "eleves")
    col_transf = next((c for c in ("ecole_origine", "ecole_provenance", "provenance", "etablissement_origine",
                                   "ancienne_ecole", "transfere_de", "venu_de") if c in ecols), None)
    col_acte = next((c for c in ("acte_naissance", "a_acte_naissance", "acte") if c in ecols), None)
    col_sans_acte = next((c for c in ("sans_acte", "sans_acte_naissance") if c in ecols), None)
    col_handi = next((c for c in ("handicap", "handicape", "situation_handicap", "besoin_specifique",
                                  "besoins_specifiques", "type_handicap") if c in ecols), None)
    ind["colonnes"] = {"transferes": col_transf, "acte": col_acte or col_sans_acte, "handicap": col_handi}

    def compter(filtre, par):
        res = {}
        for el in eleves:
            s = _sexe(el["sexe"])
            if s and filtre(el):
                cle = (par(el), s)
                res[cle] = res.get(cle, 0) + 1
        return res

    niveaux_ouverts = {c["niveau"] for c in classes}

    def poser(prefixe, groupes, compte, forcer=True):
        for gcode, niv in groupes:
            if niv not in niveaux_ouverts:
                continue  # niveau sans classe dans l'école : case laissée vide
            for s in ("G", "F"):
                n = compte.get((niv, s), 0)
                if n or forcer:
                    v[f"{prefixe}.{gcode}_{s}"] = str(n)

    tous = lambda el: True  # noqa: E731
    inscrit = lambda el: (el.get("statut") or "inscrit") == "inscrit"  # noqa: E731
    sorti = lambda el: el.get("statut") == "sorti"  # noqa: E731
    par_niv = lambda el: niv_de.get(el["classe_id"])  # noqa: E731
    handi = (lambda el: vrai(el.get(col_handi))) if col_handi else None
    groupes = [(n, n) for n in NIV_EP] if ep else [(c, niv) for c, _, niv in SECTIONS_EM]
    if ep and not fin:
        poser("eff.nb", groupes, compter(inscrit, par_niv))
        poser("eff.red", groupes, compter(lambda el: inscrit(el) and vrai(el.get("redoublant")), par_niv))
        if col_transf:
            poser("eff.transf", groupes, compter(lambda el: inscrit(el) and vrai(el.get(col_transf)), par_niv))
        if col_acte or col_sans_acte:
            f_acte = ((lambda el: not vrai(el.get(col_acte))) if col_acte else (lambda el: vrai(el.get(col_sans_acte))))
            poser("eff.sans_acte", groupes, compter(lambda el: inscrit(el) and f_acte(el), par_niv))
        if handi:
            poser("eff.handic", groupes, compter(lambda el: inscrit(el) and handi(el), par_niv))
    elif ep and fin:
        poser("eff.debut", groupes, compter(tous, par_niv))
        poser("eff.fin", groupes, compter(inscrit, par_niv))
        poser("eff.aband", groupes, compter(sorti, par_niv))
    else:
        poser("rep.debut", groupes, compter(tous if fin else inscrit, par_niv))
        if fin:
            poser("rep.fin", groupes, compter(inscrit, par_niv))
            poser("rep.aband", groupes, compter(sorti, par_niv))
        if handi:
            poser("rep.besoin", groupes, compter(lambda el: inscrit(el) and handi(el), par_niv))
    # ---------------------------------------------------------------- classes, salles, structure pédagogique
    nb_cl = {}
    for c in classes:
        nb_cl[c["niveau"]] = nb_cl.get(c["niveau"], 0) + 1
    if classes:
        if ep:
            v["classes_ouvertes"] = str(len(classes))
            v["salles_utilisees"] = str(len(classes))
            for n in NIV_EP:
                if nb_cl.get(n):
                    v[f"sp.simple.{n}"] = str(nb_cl[n])
            v["sp.simple.salles"] = str(len(classes))
        else:
            v["sections_ouvertes"] = str(len(classes))
            v["salles_utilisees"] = str(len(classes))
            v["sp.simple.pet"] = str(nb_cl.get("Maternelle 1", 0))
            v["sp.simple.gra"] = str(nb_cl.get("Maternelle 2", 0))
            v["sp.simple.salles"] = str(len(classes))
    try:
        patrimoine_auto(H, doc, v, classes)
    except Exception:  # noqa: BLE001  (données du module Patrimoine incomplètes : on garde la saisie)
        pass
    # ---------------------------------------------------------------- cantine
    d1, d2 = f"{a0}-09-01", f"{a0 + 1}-08-31"
    ids_cl = [c["id"] for c in classes]
    if ids_cl:
        mq = ",".join("?" * len(ids_cl))
        cfg = H.q(f"SELECT COUNT(*) n FROM cantine_config WHERE classe_id IN ({mq}) AND montant_jour>0", ids_cl, un=True)["n"]
        pay = H.q(f"""SELECT COUNT(*) n, COALESCE(SUM(p.montant),0) m FROM cantine_paiements p JOIN eleves el ON el.id=p.eleve_id
                      WHERE el.classe_id IN ({mq}) AND p.date BETWEEN ? AND ?""", ids_cl + [d1, d2], un=True)
        if cfg or pay["n"]:
            if ep:
                v["cantine"] = "OUI"
                v["cantine_fonctionne"] = "OUI" if pay["n"] else "NON"
            elif pay["n"]:
                v["cantine"] = "oui"
        ind["cantine"] = [
            {"classe": c["nom"], **dict(H.q("""SELECT COUNT(*) repas, COALESCE(SUM(p.montant),0) montant,
                     COUNT(DISTINCT p.eleve_id) eleves FROM cantine_paiements p JOIN eleves el ON el.id=p.eleve_id
                     WHERE el.classe_id=? AND p.date BETWEEN ? AND ?""", (c["id"], d1, d2), un=True))}
            for c in classes]
    # ---------------------------------------------------------------- résultats (évaluations) : promus / redoublants
    try:
        import evaluations_core as EC
    except ImportError:  # pragma: no cover
        EC = None
    ind["resultats"] = []
    promus, redoub = {}, {}
    for c in classes:
        if not EC:
            break
        evs = EC.evaluations_classe(c["id"], annee)
        if not evs:
            continue
        mats, lignes = EC.resultats(evs[-1], c)
        st = EC.statistiques(mats, lignes)
        bil = EC.bilan_annuel(c, evs)
        ad = {"G": 0, "F": 0}
        for o in bil:
            s = _sexe(o["eleve"]["sexe"])
            if s and o["admis"]:
                ad[s] += 1
                promus[(c["niveau"], s)] = promus.get((c["niveau"], s), 0) + 1
            elif s and o["composees"]:
                redoub[(c["niveau"], s)] = redoub.get((c["niveau"], s), 0) + 1
        ind["resultats"].append({"classe": c["nom"], "niveau": c["niveau"], "evaluation": evs[-1]["titre"],
                                 "nb_evaluations": len(evs), "inscrits": st["inscrits"], "composes": st["composes"],
                                 "reussis": st["reussis"], "taux": st["taux_reussite"],
                                 "admis": {"G": ad["G"], "F": ad["F"], "T": ad["G"] + ad["F"]}})
    if ep and fin and ind["resultats"]:
        niv_eval = {r["niveau"] for r in ind["resultats"]}
        for n in NIV_EP:
            if n in niv_eval:
                for s in ("G", "F"):
                    v[f"eff.promus.{n}_{s}"] = str(promus.get((n, s), 0))
                    v[f"eff.red.{n}_{s}"] = str(redoub.get((n, s), 0))
    # ---------------------------------------------------------------- CEP blanc (primaire)
    ind["cep_blanc"] = []
    if ep:
        try:
            import m_cep
            for s in H.q("SELECT * FROM cep_blanc_sessions WHERE ecole_id=? AND annee=? ORDER BY numero, id",
                         (H.eco(), annee)):
                sd = m_cep.session_dict(s)
                cands = H.q("SELECT * FROM cep_blanc_candidats WHERE session_id=?", (s["id"],))
                st = m_cep.stats_blanc(m_cep.resultats_blanc(sd, cands))
                ind["cep_blanc"].append({"numero": s["numero"], "centre": s["centre"] or "", **st})
        except Exception:  # noqa: BLE001  (module CEP absent ou données incomplètes)
            pass
    # ---------------------------------------------------------------- âges, nouveaux inscrits
    ref_age = date(a0 + 1, 12, 31)   # 31 décembre de la seconde année (2026-2027 -> 31/12/2027)
    ages = {}
    for el in eleves:
        s, dn = _sexe(el["sexe"]), lire_date(el.get("date_naissance"))
        if not s or not dn or not inscrit(el):
            continue
        a = annees_ecoulees(dn.isoformat(), ref_age)
        if a is None:
            continue
        ages[(a, niv_de[el["classe_id"]], s)] = ages.get((a, niv_de[el["classe_id"]], s), 0) + 1
    ind["niveaux"] = [n for n in (NIV_EP if ep else NIV_EM) if n in nb_cl]
    ind["ages"] = sorted({k[0] for k in ages})
    ind["ages_n"] = {f"{a}|{n}|{s}": c for (a, n, s), c in ages.items()}
    nouv = compter(lambda el: inscrit(el) and d1 <= (el.get("date_inscription") or "")[:10] <= d2
                   and not vrai(el.get("redoublant")), par_niv)
    ind["nouveaux"] = {f"{n}|{s}": c for (n, s), c in nouv.items()}
    # ---------------------------------------------------------------- présence (registre)
    ind["presence"] = []
    try:
        import m_registre
        cal = m_registre.Calendrier(H, H.eco())
        p = m_registre.parametres_calendrier(H, H.eco(), annee)
        deb = lire_date(p["rentree"])
        fn = min(lire_date(p["fin"]), date.today())
        if deb and fn and fn >= deb:
            demi = cal.total(deb, fn)
            for c in classes:
                eff = sum(1 for el in eleves if el["classe_id"] == c["id"] and inscrit(el))
                ab = H.q("""SELECT COUNT(*) n FROM registre r JOIN eleves el ON el.id=r.eleve_id
                            WHERE el.classe_id=? AND el.statut='inscrit' AND r.date BETWEEN ? AND ?""",
                         (c["id"], deb.isoformat(), fn.isoformat()), un=True)["n"]
                poss = eff * demi
                ind["presence"].append({"classe": c["nom"], "effectif": eff, "demi": demi, "absences": ab,
                                        "taux": round(100 * (poss - ab) / poss, 1) if poss else None})
    except Exception:  # noqa: BLE001  (module registre absent)
        pass
    # ---------------------------------------------------------------- personnel
    pers = personnel_du_cycle(H, doc, classes, e)
    ref = date(a0, 10, 1) if not fin else date(a0 + 1, 6, 30)
    for i, x in enumerate(pers, 1):
        p, d = x["p"], {normaliser(k).replace(" ", "_"): val for k, val in x["d"].items()}
        pre = f"pers.{i}."
        v[pre + "mat"] = str(_trouver(d, ("matricule", "numero_matricule")) or "")
        nip = str(_trouver(d, ("nip",)) or "").strip()   # NIP (module Carrière : personnel.nip)
        if nip:
            v[pre + "nip"] = nip
        v[pre + "nom"] = f"{p['nom']} {p['prenoms']}".strip()
        sx = _sexe(p.get("sexe") or d.get("sexe"))
        if sx:
            v[pre + "sexe"] = "M" if sx == "G" else "F"
        dn = _trouver(d, ("date_naissance", "naissance", "annee_naissance"))
        dn = lire_date(dn)
        if dn:
            v[pre + "naiss"] = str(dn.year)
        for cle, cands, motifs in [("dacad", ("diplome_academique", "diplome_acad", "diplome"), (("diplome", "acad"),)),
                                   ("dprof", ("diplome_professionnel", "diplome_prof"), (("diplome", "prof"),)),
                                   ("grade", ("grade",), ()),
                                   ("statut", ("statut", "statut_agent", "categorie_agent", "categorie"), ()),
                                   ("indice", ("indice_reel", "indice", "indice_actuel", "indice_paye"), (("indice",),)),
                                   ("qualite", ("qualite",), ()),
                                   ("pup", ("participation_up", "taux_participation_up"), (("particip", "up"),))]:
            val = _trouver(d, cands, motifs)
            if val not in (None, ""):
                v[pre + cle] = str(val)
        if not v.get(pre + "dprof"):  # module carrière : CAP / CEAP (oui|non)
            if vrai(d.get("cap")) and normaliser(d.get("cap")) != "non":
                v[pre + "dprof"] = "CAP"
            elif vrai(d.get("ceap")) and normaliser(d.get("ceap")) != "non":
                v[pre + "dprof"] = "CEAP"
        if not v.get(pre + "statut") and statut_ecole(e, ep) == "Privé":
            v[pre + "statut"] = "PRIVE"
        v[pre + "fonction"] = ((e["directeur_titre"] if e and e["directeur_titre"] in ("Directeur", "Directrice")
                                else "Directeur") if x["dir"] else "Adjoint")
        if ep:
            v[pre + "cours"] = ", ".join(n for n in NIV_EP if n in x["niveaux"])
        else:
            pet, gra = "Maternelle 1" in x["niveaux"], "Maternelle 2" in x["niveaux"]
            if pet or gra:
                v[pre + "section"] = "Petits et grands" if pet and gra else ("Petits" if pet else "Grands")
        for cle, cands, motifs in [
                ("afp", ("date_prise_service", "date_entree_fp", "date_entree_fonction_publique", "date_recrutement", "date_integration",
                         "date_premiere_prise_service"), (("fonction", "publique"), ("recrut",))),
                ("adep", ("date_service_dep", "date_arrivee_departement", "date_affectation_departement", "date_entree_departement"),
                 (("depart",),)),
                ("aecole", ("date_service_ecole", "date_affectation_ecole", "date_arrivee_ecole", "date_affectation",
                            "date_embauche"), (("ecole",),))]:
            n = annees_ecoulees(_trouver(d, cands, motifs), ref)
            if n is not None:
                v[pre + cle] = str(n)
        f = _trouver(d, ("date_derniere_formation", "derniere_formation_date", "date_formation"), (("formation", "date"),))
        if f:
            fd = lire_date(f)
            v[pre + ("fdate" if doc == "rentree-em" else "form")] = fd.strftime("%d/%m/%Y") if fd else str(f)
        if doc == "rentree-em":
            nat = _trouver(d, ("nature_derniere_formation", "derniere_formation", "formation_nature", "type_formation"))
            if nat:
                v[pre + "fnature"] = str(nat)
        if fin:
            vis = _visites(H, p["id"], f"{a0}-09-01", f"{a0 + 1}-08-31")
            if not vis and (d.get("visites_cp") not in (None, "") or d.get("visites_ccs") not in (None, "")):
                vis = {"vinsp": str(d.get("visites_ccs") or 0), "vcp": str(d.get("visites_cp") or 0)}
            if vis:
                for k2, n in vis.items():
                    v[pre + k2] = str(n)
    v["pers_n"] = str(max(bloc_personnel(doc)["min"], len(pers)))
    ind["personnel"] = len(pers)
    ind["eleves"] = sum(1 for el in eleves if inscrit(el))
    ind["classes"] = len(classes)
    return v, ind


# ------------------------------------------------------------------ report des renseignements stables
REPORT_PREFIXES = ("annee_creation", "ref_creation", "annee_extension", "ref_extension", "initiative",
                   "arrondissement", "village", "fondateur", "classes_autorisees", "sections_autorisees",
                   "salles_existantes", "infra.", "mob.", "man.", "matped", "mob_autre", "ext", "int", "lavage",
                   "gestion", "g_", "cantine_organisme", "adresse_postale", "contact_directeur",
                   "cp_zone_num", "cp_nom", "rup_nom", "chef_nom", "bp", "telephone", "email", "cantine")
PERS_REPORT = ("mat", "nip", "sexe", "naiss", "dacad", "dprof", "grade", "statut", "indice", "qualite", "fdate", "fnature",
               "form", "afp", "adep", "aecole")


def cle_stockage(eco, doc, annee):
    return f"e{eco}:rapports:{doc}:{annee}"


def lire_stock(H, doc, annee):
    d = H.doc_lire(cle_stockage(H.eco(), doc, annee), None)
    return d if isinstance(d, dict) else {}


def sources_report(H, doc, annee):
    """Instantanés utilisables pour reprendre les renseignements stables, du plus pertinent au moins pertinent."""
    a0 = int(annee[:4])
    srcs = [(SOEUR[doc], annee, True)]
    for k in range(1, 4):
        an = f"{a0 - k}-{a0 - k + 1}"
        srcs += [(doc, an, False), (SOEUR[doc], an, False)]
    out = []
    for d, an, meme in srcs:
        st = lire_stock(H, d, an)
        if st.get("instantane"):
            out.append((d, an, meme, st["instantane"]))
    return out


def appliquer_report(doc, v, sources):
    """Complète v (valeurs automatiques) avec les renseignements stables d'autres rapports (sans écraser)."""
    origine = {}
    colonnes = {c["c"] for c in bloc_personnel(doc)["cols"]}
    for d, an, meme, inst in sources:
        for k, val in inst.items():
            if val in (None, "") or k.startswith("pers") or k in v and v[k] not in ("", None):
                continue
            if not k.startswith(REPORT_PREFIXES) and not (meme and k.startswith(("infra.", "mob.", "man."))):
                continue
            if k.startswith(("cantine",)) and k != "cantine_organisme" and not meme:
                continue
            # le tableau source doit exister dans ce document (ex. « mob. » EP ≠ EM)
            v[k] = val
            origine[k] = f"{DOCS[d]['court']} {an}"
        # personnel : rapprochement par le nom
        noms_src = {}
        i = 1
        while f"pers.{i}.nom" in inst or i <= 12:
            nm = normaliser(inst.get(f"pers.{i}.nom"))
            if nm:
                noms_src[nm] = i
            i += 1
            if i > PERS_MAX:
                break
        try:
            n = int(v.get("pers_n") or 0)
        except ValueError:
            n = 0
        for j in range(1, n + 1):
            j_src = noms_src.get(normaliser(v.get(f"pers.{j}.nom")))
            if not j_src:
                continue
            for c in PERS_REPORT:
                if c not in colonnes:
                    continue
                if c in ("afp", "adep", "aecole") and not meme:
                    continue
                k, ks = f"pers.{j}.{c}", f"pers.{j_src}.{c}"
                if v.get(k) in (None, "") and inst.get(ks) not in (None, ""):
                    v[k] = inst[ks]
                    origine[k] = f"{DOCS[d]['court']} {an}"
    return origine


def donnees_document(H, doc, annee):
    """(auto, surcharges, fusion, finales, indicateurs, origine, stock)."""
    auto, ind = calculer_auto(H, doc, annee)
    stock = lire_stock(H, doc, annee)
    if ind.get("inactive") and stock.get("instantane"):
        base = dict(stock["instantane"])
        for k, val in auto.items():
            base.setdefault(k, val)
        auto = base
    origine = appliquer_report(doc, auto, sources_report(H, doc, annee))
    # ne garder que les clés du schéma
    over = {k: str(val) for k, val in (stock.get("valeurs") or {}).items()}
    fusion = dict(auto)
    fusion.update(over)
    finales = valeurs_calculees(doc, fusion)
    return auto, over, fusion, finales, ind, origine, stock


# =====================================================================================================
# 4. CONTRÔLES DE COHÉRENCE
# =====================================================================================================
def controles(doc, v):
    """Liste de messages (niveau, texte) ; niveau = 'danger' (incohérence) ou 'warning' (à vérifier)."""
    info = DOCS[doc]
    ep, fin = info["cycle"] == "primaire", info["moment"] == "fin"
    out = []
    n = lambda k: entier(v.get(k))  # noqa: E731

    def cmp_le(a, b, msg, niveau="danger"):
        x, y = n(a), n(b)
        if x is not None and y is not None and x > y:
            out.append((niveau, msg.format(x=x, y=y)))

    ca, co = ("classes_autorisees", "classes_ouvertes") if ep else ("sections_autorisees", "sections_ouvertes")
    cmp_le(co, ca, "Le nombre de " + ("classes" if ep else "sections") + " ouvertes ({x}) dépasse le nombre autorisé ({y}).")
    cmp_le("salles_utilisees", "salles_existantes",
           "Salles de classe utilisées ({x}) supérieures aux salles existantes ({y}).", "warning")
    for k in ("annee_creation", "annee_extension"):
        a = n(k)
        if a and a > int(date.today().year):
            out.append(("danger", f"L'année {a} ({k.replace('_', ' ')}) est dans le futur."))
    if n("annee_creation") and n("annee_extension") and n("annee_extension") < n("annee_creation"):
        out.append(("danger", "L'année d'extension est antérieure à l'année de création."))
    if "commun" in normaliser(v.get("statut")) and not v.get("initiative"):
        out.append(("warning", "Statut communautaire : précisez l'initiative (rubrique 1.4)."))
    if ep:
        if v.get("cantine") == "NON" and v.get("cantine_fonctionne") == "OUI":
            out.append(("danger", "Cantine : « NON » à la première question mais « a fonctionné : OUI »."))
        if v.get("cantine") == "OUI" and v.get("cantine_fonctionne") == "NON" and not v.get("cantine_raison"):
            out.append(("warning", "La cantine n'a pas fonctionné : donnez la raison (rubrique 1.7)."))
        grp = NIV_EP + ["ENS"]
        if fin:
            for g_ in grp:
                for s in ("G", "F", "T"):
                    k = lambda r: f"eff.{r}.{g_}_{s}"  # noqa: E731
                    cmp_le(k("fin"), k("debut"), f"{g_} {s} : effectif de fin d'année ({{x}}) supérieur au début ({{y}}).")
                    fi, pr, re_, de, ab = n(k("fin")), n(k("promus")), n(k("red")), n(k("debut")), n(k("aband"))
                    if fi is not None and pr is not None and re_ is not None and pr + re_ != fi and g_ != "ENS":
                        out.append(("warning", f"{g_} {s} : promus ({pr}) + redoublants ({re_}) ≠ effectif de fin "
                                               f"d'année ({fi})."))
                    if de is not None and fi is not None and ab is not None and fi + ab > de:
                        out.append(("danger", f"{g_} {s} : fin d'année ({fi}) + abandons ({ab}) > début d'année ({de})."))
        else:
            for g_ in grp:
                for s in ("G", "F", "T"):
                    for r, lib in (("red", "redoublants"), ("transf", "transférés"), ("sans_acte", "sans acte de naissance"),
                                   ("handic", "handicapés")):
                        cmp_le(f"eff.{r}.{g_}_{s}", f"eff.nb.{g_}_{s}",
                               f"{g_} {s} : {lib} ({{x}}) supérieurs au nombre d'élèves ({{y}}).")
        tot_sp = sum(n(f"sp.simple.{x}") or 0 for x in NIV_EP) + sum(n(f"sp.multi.{x}") or 0 for x in NIV_EP)
        tot_sp += sum(n(k) or 0 for k in v if k.startswith("sp.jumelee.") and not k.endswith("salles"))
        if n(co) is not None and tot_sp and tot_sp != n(co):
            out.append(("warning", f"Structure pédagogique : {tot_sp} classe(s) décrite(s) pour {n(co)} classe(s) ouverte(s)."))
    else:
        if v.get("gestion") == "oui" and not any(v.get(k) == "oui" for k in ("g_ape", "g_ame", "g_comite")) \
                and not v.get("g_autres"):
            out.append(("warning", "Structure de gestion collégiale : cochez APE, AME, Comité de direction ou précisez."))
        if v.get("gestion") == "non" and any(v.get(k) == "oui" for k in ("g_ape", "g_ame", "g_comite")):
            out.append(("danger", "« Pas de structure de gestion collégiale » mais une structure est cochée (2.7)."))
        if v.get("cantine") == "oui" and not v.get("cantine_organisme"):
            out.append(("warning", "Cantine fonctionnelle : précisez l'organisme de soutien (2.5)."))
        for g_ in ("pet", "gra", "tot"):
            for s in ("F", "G", "T"):
                cmp_le(f"rep.besoin.{g_}_{s}", f"rep.debut.{g_}_{s}",
                       f"Section {g_} {s} : enfants à besoin spécifique ({{x}}) > effectif ({{y}}).")
                if fin:
                    cmp_le(f"rep.fin.{g_}_{s}", f"rep.debut.{g_}_{s}",
                           f"Section {g_} {s} : effectif de fin ({{x}}) > effectif de début ({{y}}).")
    tot_salles = n("infra.salles.tot")
    if tot_salles is not None and n("salles_existantes") is not None and tot_salles != n("salles_existantes"):
        out.append(("warning", f"Infrastructures : {tot_salles} salle(s) (a+b) pour {n('salles_existantes')} salle(s) "
                               f"existante(s) déclarée(s)."))
    # personnel
    np_ = nb_lignes_personnel(doc, v)
    noms = [i for i in range(1, np_ + 1) if v.get(f"pers.{i}.nom") not in (None, "", "-")]
    dirs = [i for i in noms if normaliser(v.get(f"pers.{i}.fonction")).startswith("direct")]
    if noms and len(dirs) != 1:
        out.append(("warning", f"État nominatif : {len(dirs)} directeur(s)/directrice(s) indiqué(s) (1 attendu)."))
    for i in noms:
        if v.get(f"pers.{i}.sexe") not in ("M", "F"):
            out.append(("warning", f"État nominatif, ligne {i} ({v.get(f'pers.{i}.nom')}) : sexe non renseigné."))
    return out


# =====================================================================================================
# 5. PDF (même forme que les modèles officiels)
# =====================================================================================================
BLEU_VAL = "#0B3A8C"


class Rendu:
    """Outils de dessin (coordonnées « depuis le haut de la page »)."""

    def __init__(self, c, v, vierge, serif, H, entete=None):
        from reportlab.lib import colors
        self.c, self.v, self.vierge, self.H = c, v, vierge, H
        self.ent = entete or {}
        self.synth = bool(self.ent.get("synthese"))       # fiche consolidée : nombres d'écoles par réponse
        self.ecole_locale = H is not None and not self.ent  # signature / cachet de l'école courante permis
        self.col = colors
        self.F = "Times-Roman" if serif else "Helvetica"
        self.FB = "Times-Bold" if serif else "Helvetica-Bold"
        self.FI = "Times-Italic" if serif else "Helvetica-Oblique"
        self.FBI = "Times-BoldItalic" if serif else "Helvetica-BoldOblique"
        self.FV = "Helvetica"
        self.lus = set()

    @property
    def PH(self):
        return self.c._pagesize[1]

    def Y(self, t):
        return self.PH - t

    def val(self, k):
        self.lus.add(k)
        if self.vierge:
            return ""
        x = self.v.get(k)
        if isinstance(x, dict):
            return ""
        return "" if x is None else str(x)

    def choix(self, k, option):
        """Option choisie ? (bool) ; fiche consolidée : nombre d'écoles ayant fait ce choix (int)."""
        self.lus.add(k)
        if self.vierge:
            return False
        x = self.v.get(k)
        if isinstance(x, dict):
            return int(x.get(option, 0) or 0)
        return normaliser(x) == normaliser(option) if x not in (None, "") else False

    def compte(self, x_fin, y, n, size=8):
        """Écrit le nombre d'écoles à droite d'une case (fiche consolidée)."""
        if isinstance(n, bool) or not self.synth:
            return x_fin
        self.c.setFillColor(self.col.HexColor(BLEU_VAL))
        self.c.setFont("Helvetica-Bold", size)
        s = str(n)
        self.c.drawString(x_fin + 1.5, self.Y(y), s)
        self.c.setFillColor(self.col.black)
        return x_fin + 1.5 + self.c.stringWidth(s, "Helvetica-Bold", size)

    # ---------------------------------------------------------------- texte
    def t(self, x, y, s, size=11, font=None, centre=False, droite=False):
        c = self.c
        f = font or self.F
        c.setFont(f, size)
        c.setFillColor(self.col.black)
        if centre:
            c.drawCentredString(x, self.Y(y), s)
            return x + c.stringWidth(s, f, size) / 2
        if droite:
            c.drawRightString(x, self.Y(y), s)
            return x
        c.drawString(x, self.Y(y), s)
        return x + c.stringWidth(s, f, size)

    def souligne(self, x, y, s, size, font=None):
        f = font or self.FB
        x2 = self.t(x, y, s, size, f)
        self.c.setLineWidth(0.7)
        self.c.line(x, self.Y(y) - 1.6, x2, self.Y(y) - 1.6)
        return x2

    def valeur(self, x1, x2, y, s, size=10, centre=False):
        """Écrit une valeur dans [x1, x2] en bleu (réduit la taille, voire 2 lignes, sans jamais tronquer)."""
        if not s:
            return
        from reportlab.lib.utils import simpleSplit
        c = self.c
        larg = max(8, x2 - x1)
        taille = size
        while taille > 5.5 and c.stringWidth(s, self.FV, taille) > larg:
            taille -= 0.25
        c.setFillColor(self.col.HexColor(BLEU_VAL))
        if c.stringWidth(s, self.FV, taille) <= larg:
            c.setFont(self.FV, taille)
            if centre:
                c.drawCentredString((x1 + x2) / 2, self.Y(y) + 1, s)
            else:
                c.drawString(x1, self.Y(y) + 1, s)
        else:
            lignes = simpleSplit(s, self.FV, 5.5, larg)
            taille = 5.5
            if len(lignes) > 3:
                taille = max(3.5, 5.5 * 3 / len(lignes))
                lignes = simpleSplit(s, self.FV, taille, larg)
            c.setFont(self.FV, taille)
            h = taille + 0.4
            y0 = self.Y(y) + 1 + h * (len(lignes) - 1) / 2
            for i, l in enumerate(lignes):
                c.drawString(x1, y0 - i * h, l)
        c.setFillColor(self.col.black)

    def points(self, x1, x2, y):
        if x2 - x1 < 3:
            return
        c = self.c
        c.saveState()
        c.setLineWidth(0.9)
        c.setLineCap(1)
        c.setDash([0.05, 2.3])
        c.setStrokeColor(self.col.HexColor("#333333"))
        c.line(x1, self.Y(y) - 0.5, x2, self.Y(y) - 0.5)
        c.restoreState()

    def champ(self, x, y, lib, k, x2, size=11, font=None, vsize=None):
        """« libellé ……… » avec la valeur écrite sur les pointillés. Retourne x de fin."""
        xd = self.t(x, y, lib, size, font) + 2 if lib else x
        self.points(xd, x2, y)
        self.valeur(xd + 2, x2 - 1, y, self.val(k), vsize or size - 0.5)
        return x2

    def cases_slash(self, x, y, n, larg, k, size=11, texte=None):
        """« /……/……/……/……/ » ; la valeur est répartie chiffre par chiffre si elle a n caractères."""
        s = self.val(k) if texte is None else texte
        c = self.c
        xs = x
        c.setFont(self.F, size)
        w_sl = c.stringWidth("/", self.F, size)
        for i in range(n):
            self.t(xs, y, "/", size)
            self.points(xs + w_sl + 1, xs + w_sl + larg - 1, y)
            xs += w_sl + larg
        self.t(xs, y, "/", size)
        fin = xs + w_sl
        if s and n > 1 and s.isdigit() and len(s) < n:
            s = s.rjust(n, "0")  # un chiffre par case, comme sur le formulaire papier (ex. /0/7/)
        if s:
            if len(s) == n and n > 1:
                for i, ch in enumerate(s):
                    a = x + i * (w_sl + larg) + w_sl
                    self.valeur(a, a + larg, y - 1, ch, size, centre=True)
            else:
                self.valeur(x + w_sl, fin - w_sl, y - 1, s, size, centre=True)
        return fin

    def cases_trait(self, x, y, larg, k=None, size=10, coche=None):
        """« /_____/ » (maternelle) avec X ou valeur dedans."""
        c = self.c
        self.t(x, y, "/", size)
        w = c.stringWidth("/", self.F, size)
        c.setLineWidth(0.6)
        c.line(x + w + 0.5, self.Y(y) - 1, x + w + larg, self.Y(y) - 1)
        self.t(x + w + larg + 0.5, y, "/", size)
        if coche is not None:
            if self.synth and not isinstance(coche, bool):   # fiche consolidée : nombre d'écoles dans la case
                if not self.vierge:
                    self.valeur(x + w, x + w + larg, y - 1, str(coche), size, centre=True)
            elif coche and not self.vierge:
                self.valeur(x + w, x + w + larg, y - 1, "X", size, centre=True)
        elif k:
            self.valeur(x + w, x + w + larg, y - 1, self.val(k), size, centre=True)
        return x + 2 * w + larg + 1

    def rond(self, x, y, r, plein):
        c = self.c
        c.setLineWidth(0.7)
        c.setStrokeColor(self.col.black)
        c.circle(x + r, self.Y(y) + r * 0.65, r, stroke=1, fill=0)
        if plein and not self.vierge:
            c.setFillColor(self.col.HexColor(BLEU_VAL))
            c.circle(x + r, self.Y(y) + r * 0.65, r * 0.55, stroke=0, fill=1)
            c.setFillColor(self.col.black)
        return self.compte(x + 2 * r, y, plein)

    def carre(self, cx, cy, s, coche):
        """Case ❒ centrée en (cx, cy [depuis le haut])."""
        c = self.c
        x, y = cx - s / 2, self.Y(cy) - s / 2
        c.setLineWidth(0.6)
        c.setStrokeColor(self.col.black)
        c.rect(x, y, s, s, stroke=1, fill=0)
        c.setLineWidth(1.1)
        c.line(x + s + 0.6, y - 0.6, x + s + 0.6, y + s - 0.8)
        c.line(x + 0.8, y - 0.6, x + s + 0.6, y - 0.6)
        if coche and not self.vierge:
            c.setStrokeColor(self.col.HexColor(BLEU_VAL))
            c.setLineWidth(1)
            c.line(x + 1.2, y + 1.2, x + s - 1.2, y + s - 1.2)
            c.line(x + 1.2, y + s - 1.2, x + s - 1.2, y + 1.2)
            c.setStrokeColor(self.col.black)

    def annee_boites(self, cx, cy, s):
        """« I__I__I__I__I » avec les 4 chiffres de l'année."""
        c = self.c
        w = 7.5
        x0 = cx - 2 * w
        y = self.Y(cy) - 3
        c.setLineWidth(0.5)
        c.line(x0, y, x0 + 4 * w, y)
        for i in range(5):
            c.line(x0 + i * w, y, x0 + i * w, y + 5)
        if s and len(s) == 4 and not self.vierge:
            c.setFillColor(self.col.HexColor(BLEU_VAL))
            c.setFont(self.FV, 7.5)
            for i, ch in enumerate(s):
                c.drawCentredString(x0 + i * w + w / 2, y + 1, ch)
            c.setFillColor(self.col.black)
        elif s and not self.vierge:
            self.valeur(x0, x0 + 4 * w, cy - 1.5, s, 7, centre=True)

    # ---------------------------------------------------------------- tableaux
    def grille(self, xs, ys, cellules, lw=0.6):
        """cellules : (ligne, col, nb_lignes, nb_cols, texte, options) ; xs / ys = bornes (ys depuis le haut)."""
        from reportlab.lib.utils import simpleSplit
        c = self.c
        c.setStrokeColor(self.col.black)
        for (r, k, rs, cs, txt, o) in cellules:
            x1, x2 = xs[k], xs[k + cs]
            y1, y2 = ys[r], ys[r + rs]
            if not o.get("sans_bord"):
                c.setLineWidth(o.get("lw", lw))
                c.rect(x1, self.Y(y2), x2 - x1, y2 - y1, stroke=1, fill=0)
            if txt in (None, ""):
                continue
            size = o.get("size", 8)
            if o.get("val"):
                if not self.vierge:
                    self.valeur(x1 + 1.5, x2 - 1.5, (y1 + y2) / 2 + size * 0.35, txt, size, centre=o.get("align", "c") == "c")
                continue
            font = o.get("font", self.F)
            if o.get("rot"):
                c.saveState()
                c.setFont(font, size)
                c.setFillColor(self.col.black)
                lignes = simpleSplit(txt, font, size, (y2 - y1) - 3)
                h = size + 1
                c.translate((x1 + x2) / 2 + (h * (len(lignes) - 1) / 2) - size * 0.33, self.Y((y1 + y2) / 2))
                c.rotate(90)
                for i, l in enumerate(lignes):
                    c.drawCentredString(0, -i * h, l)
                c.restoreState()
                continue
            larg = x2 - x1 - 3
            while size > 4.5 and max(c.stringWidth(w, font, size) for w in (txt.split() or [""])) > larg:
                size -= 0.25
            lignes = []
            for part in txt.split("\n"):
                lignes += simpleSplit(part, font, size, larg) or [""]
            h = size * 1.15
            ytop = (y1 + y2) / 2 - h * len(lignes) / 2 + size * 0.85
            if o.get("haut"):
                ytop = y1 + size + 1.5
            c.setFont(font, size)
            c.setFillColor(self.col.black)
            for i, l in enumerate(lignes):
                yy = self.Y(ytop + i * h)
                if o.get("align") == "l":
                    c.drawString(x1 + 2.5, yy, l)
                else:
                    c.drawCentredString((x1 + x2) / 2, yy, l)


def _armoiries(H):
    chemin = os.path.join(H.config.INSTANCE_DIR, "rapports", "armoiries.png")
    if not os.path.exists(chemin):  # à défaut : armoiries extraites des modèles officiels (module Documents de l'enseignant)
        chemin = os.path.join(getattr(H.config, "WEB_DIR", H.config.BASE_DIR), "static", "docs_enseignant_armoiries.png")
    if os.path.exists(chemin):
        try:
            from reportlab.lib.utils import ImageReader
            return ImageReader(chemin)
        except Exception:  # noqa: BLE001
            return None
    return None


def entete(R, doc, style):
    """En-tête ministériel commun (emblème, ministère, adresse, direction, cadre du titre). Retourne y bas."""
    c, H = R.c, R.H
    from reportlab.lib import colors
    info = DOCS[doc]
    scan = style == "scan"
    em = info["cycle"] == "maternelle"
    # bandes tricolores en haut
    yb = 60 if scan and not em else (41 if scan else (20 if not em else 25))
    xb = 225 if scan and not em else (190 if scan else 205)
    for i, coul in enumerate(("#1B8E3E", "#F4D21F", "#D52B1E")):
        c.setFillColor(colors.HexColor(coul))
        c.rect(xb + i * 50, R.Y(yb), 48 if scan else 52, 3, stroke=0, fill=1)
    c.setFillColor(colors.black)
    y0 = {True: {False: 80, True: 55}, False: {False: 30, True: 40}}[scan][em]
    # en-tête officiel du MEMP AVEC LOGO (static/docs_enseignant_memp.png : armoiries + ministère + République) ;
    # si l'école a téléversé ses propres armoiries (instance/rapports/armoiries.png) : armoiries + texte.
    perso = os.path.join(H.config.INSTANCE_DIR, "rapports", "armoiries.png") if H is not None else ""
    import m_recensement
    if perso and os.path.exists(perso):
        img = _armoiries(H)
        cx, cy = (78 if not em else 62), y0 + 26
        c.drawImage(img, cx - 32, R.Y(cy + 24), 64, 48, preserveAspectRatio=True, mask="auto")
        xm = 155 if not em else 125
        R.t(xm, y0 + 5, "MINISTÈRE", 7.8, "Helvetica-Bold")
        R.t(xm, y0 + 16, "DES ENSEIGNEMENTS", 7.8, "Helvetica-Bold")
        R.t(xm, y0 + 27, "MATERNEL ET PRIMAIRE", 7.8, "Helvetica-Bold")
        c.setLineWidth(1)
        c.setStrokeColor(colors.HexColor("#1B8E3E"))
        c.line(xm, R.Y(y0 + 31), xm + 45, R.Y(y0 + 31))
        c.setStrokeColor(colors.HexColor("#D52B1E"))
        c.line(xm + 60, R.Y(y0 + 31), xm + 115, R.Y(y0 + 31))
        c.setStrokeColor(colors.black)
        R.t(xm, y0 + 42, "RÉPUBLIQUE DU BENIN", 7.8, "Helvetica-Bold")
    else:
        m_recensement.bloc_memp(c, 46 if not em else 30, R.Y(y0 - 2), 54)
    xr = 405 if not em else 390
    for i, l in enumerate(("01 BP 10 Porto-Novo", "Tél:+229 20 21 52 22", "Fax: +229 20 21 52 22",
                           "E-mail: mempmatprim@gmail.com")):
        R.t(xr, y0 + 10 + i * 10, l, 7.5, "Helvetica-Bold")
    y = y0 + 62
    if R.ent.get("titre"):   # fiche consolidée : « Synthèse de la CS … » à droite de la ligne de direction
        R.c.setFillColor(colors.HexColor(BLEU_VAL))
        R.t(553, y + (8 if scan and em else 10), str(R.ent["titre"])[:60], 8.5, "Helvetica-Bold", droite=True)
        R.c.setFillColor(colors.black)
    if R.ent.get("mention"):
        R.t(553, y + (17 if scan and em else 19), str(R.ent["mention"])[:110], 6.5, "Helvetica-Oblique", droite=True)
    # direction + cadre du titre
    if scan and em:
        R.t(260, y + 8, info["direction"], 8.5, "Helvetica-BoldOblique", centre=True)
        y += 20
        c.setLineWidth(1)
        c.rect(67, R.Y(y + 36), 394, 36)
        R.t(264, y + 23, info["fiche"], 11.5, "Helvetica-BoldOblique", centre=True)
        return y + 44
    R.t(60 if scan else 43, y + 10, info["direction"], 9.5 if scan else 10, R.FB if not scan else "Helvetica")
    R.t(175 if scan else 205, y + 21, "---------" if scan else "-------------", 8, R.F)
    y += 30
    c.setLineWidth(1.1)
    if scan:
        c.rect(68, R.Y(y + 44), 477, 44)
        R.t(306, y + 27, info["fiche"], 12, "Helvetica-BoldOblique", centre=True)
        y += 44
    else:
        x1, x2 = (69, 513) if not em else (55, 499)
        c.rect(x1, R.Y(y + 28), x2 - x1, 28)
        R.t((x1 + x2) / 2, y + 19, info["fiche"], 13.5, "Times-BoldItalic", centre=True)
        y += 28
    return y


def annee_txt(annee):
    return annee.split("-")


def pied(R, n, doc, paysage=False):
    info = DOCS[doc]
    W = R.c._pagesize[0]
    if info["moment"] == "rentree" and info["cycle"] == "maternelle":
        if n < 3:
            R.t(W / 2 - 5, R.PH - 26, f"Page {n}", 8.5, "Helvetica", centre=True)
            R.t(W - 20, R.PH - 20, "FICHE RAPPORT  RENTREE EM", 8, "Helvetica", droite=True)
        else:
            R.t(W / 2, R.PH - 20, "FICHE RAPPORT RENTREE EM (Suite et fin)", 8, "Helvetica", centre=True)
        return
    if info["cycle"] == "maternelle":
        R.t(W - 50, R.PH - (26 if R.PH > 700 else 38), f"Page {n}", 11, "Times-Bold", droite=True)
        return
    R.t(W / 2, R.PH - (26 if not paysage else 24), f"Page {n}", 10 if info["moment"] == "fin" else 9, R.F, centre=True)


# ------------------------------------------------------------------ EP : page 1
def page1_ep(R, doc, annee):
    fin = DOCS[doc]["moment"] == "fin"
    y = entete(R, doc, "times" if fin else "scan")
    X0, X1 = (43, 553) if fin else (41, 555)
    fs = 11.2 if fin else 10.2
    pas = 21.6 if fin else 19.2
    a1, a2 = annee_txt(annee)
    if fin:
        y += 40
        x = R.t(200, y, "ANNEE SCOLAIRE : ", 12, R.FB)
        x = R.t(x, y, "20", 11.5)
        R.points(x, x + 16, y)
        R.valeur(x, x + 16, y, "" if R.vierge else a1[2:], 11)
        x = R.t(x + 17, y, " – 20", 11.5)
        R.points(x, x + 18, y)
        R.valeur(x, x + 18, y, "" if R.vierge else a2[2:], 11)
        y += 22
        x = R.t(X0, y, "1. ", 11.5, R.FB)
        R.souligne(x, y, "IDENTIFICATION ET LOCALISATION DE L'ECOLE", 11.5)
    else:
        y += 20
        x = R.t(180, y, "ANNEE SCOLAIRE ", 11.5, "Helvetica-BoldOblique")
        R.champ(x, y, "", "", 380)
        if not R.vierge:
            R.valeur(x + 3, 380, y, annee.replace("-", " – "), 11)
        y += 28
        R.t(X0, y, "1. IDENTIFICATION ET LOCALISATION DE L'ECOLE", 10.5, "Helvetica-Bold")
    y += pas
    R.champ(X0, y, "1.1 Nom de l'école : ", "nom_ecole", X1, fs)
    y += pas
    x = R.t(X0, y, "1.2 Année de création : ", fs)
    x = R.cases_slash(x, y, 4, 18, "annee_creation", fs)
    R.champ(x + 14, y, "Référence : ", "ref_creation", X1, fs)
    y += pas
    x = R.t(X0, y, "1.3 Année d'extension : ", fs)
    x = R.cases_slash(x, y, 4, 18, "annee_extension", fs)
    R.champ(x + 14, y, "Référence : ", "ref_extension", X1, fs)
    y += pas
    x = R.t(X0, y, "1.4 Statut :  Public", fs)
    x = R.rond(x + 4, y, 4.5, R.choix("statut", "Public"))
    x = R.t(x + 12, y, "Privé", fs)
    x = R.rond(x + 4, y, 4.5, R.choix("statut", "Privé"))
    x = R.t(x + 14, y, "Communautaire", fs)
    x = R.rond(x + 4, y, 4.5, R.choix("statut", "Communautaire"))
    R.champ(x + 6, y, "Si communautaire, précisez l'initiative : ", "initiative", X1, fs - (0.8 if fin else 0.6))
    y += pas
    R.t(X0, y, "1.5 Localisation dans le réseau d'Animation Pédagogique :", fs)
    y += pas
    # (la « Région pédagogique » n'existe plus : seule la Circonscription scolaire figure sur les fiches)
    R.champ(X0, y, "i- Circonscription scolaire : ", "cs", X1, fs)
    y += pas
    R.champ(X0, y, "ii- Zone pédagogique : ", "zone", 318, fs)
    R.champ(322, y, "iii- Unité pédagogique : ", "up", X1, fs)
    y += pas
    R.t(X0, y, "1.6 Localisation dans l'administration territoriale :", fs)
    y += pas
    R.champ(X0, y, "i- Département : ", "departement", 288, fs)
    R.champ(294, y, "ii- Commune : ", "commune", X1, fs)
    y += pas
    R.champ(X0, y, "iii- Arrondissement : ", "arrondissement", 296, fs)
    R.champ(300, y, "iv- Village ou quartier de ville : ", "village", X1, fs)
    y += pas
    x = R.t(X0, y, "1.8 Adresse :", fs)
    R.champ(x + 14, y, "Boîte Postale : ", "bp", 278, fs)
    R.champ(284, y, "Téléphone : ", "telephone", X1, fs)
    y += pas
    R.champ(X0, y, "E-mail : " if fin else "e-mail : ", "email", X1 - 10, fs)
    y += pas
    if fin:
        x = R.t(X0, y, "2. ", 11.5, R.FB)
        R.souligne(x, y, "INFORMATIONS GENERALES", 11.5)
    else:
        R.t(X0 + 2, y, "2. INFORMATIONS GENERALES", 10.5, "Helvetica-Bold")
    y += pas
    x = R.t(X0, y, "2.1 Nom et prénoms du Fondateur/Fondatrice", fs)
    x = R.t(x + 1, y - 4, "1", 6.5)
    R.champ(x + 2, y, " : ", "fondateur", X1, fs)
    y += pas
    x = R.t(X0, y, "2.2 Nom et prénoms du Direct", fs)
    R.points(x + 1, x + 42, y)
    tit = R.val("directeur_titre")
    if tit:
        R.valeur(x + 1, x + 42, y, "rice" if tit == "Directrice" else "eur", fs)
    R.champ(x + 44, y, " : ", "directeur_nom", X1, fs)
    y += pas
    x = R.t(X0, y, "2.3 Nombre de classes autorisées : ", fs)
    R.cases_slash(x, y, 2, 17, "classes_autorisees", fs)
    x = R.t(310 if fin else 284, y, "Nombre de classes ouvertes : ", fs)
    R.cases_slash(x, y, 2, 17, "classes_ouvertes", fs)
    y += pas
    x = R.t(X0 + (3 if fin else 26), y, "Nombre de salles de classe existantes : ", fs)
    R.cases_slash(x, y, 2, 17, "salles_existantes", fs)
    x = R.t(310 if fin else 328, y, "Nombre de salles de classe utilisées : ", fs)
    R.cases_slash(x, y, 2, 17, "salles_utilisees", fs)
    y += pas
    x = R.t(X0, y, "1.7 L'école dispose t'elle d'une cantine ?   OUI", fs)
    x = R.rond(x + 12, y, 5, R.choix("cantine", "OUI"))
    x = R.t(x + 18, y, "NON", fs)
    R.rond(x + 10, y, 5, R.choix("cantine", "NON"))
    y += pas
    x = R.t(X0, y, "Si Oui, a-t-elle fonctionné ?   OUI", fs)
    x = R.rond(x + 3, y, 5, R.choix("cantine_fonctionne", "OUI"))
    x = R.t(x + 8, y, "NON", fs)
    R.rond(x + 3, y, 5, R.choix("cantine_fonctionne", "NON"))
    y += pas
    R.champ(X0, y, "Si Non, donnez la raison ", "cantine_raison", X1 - 30, fs)
    y += pas
    R.t(X0, y, "2.4  Structure pédagogique", fs)
    # structure pédagogique (sans cadre, comme le modèle)
    cols = ([158, 201, 247, 294, 340, 388] if fin else [170, 228, 285, 339, 390, 442])
    xs_sal = 470 if fin else 505
    y += pas * 0.9
    for n, cx in zip(NIV_EP, cols):
        R.t(cx, y, n, fs, centre=True)
    R.t(xs_sal + 30, y - 6, "Nombre de salles", fs - 0.5, centre=True)
    R.t(xs_sal + 30, y + 6, "utilisées", fs - 0.5, centre=True)
    jum = ([("CI_CP", 0, 1), ("CP_CE1", 1, 2), ("CE1_CE2", 2, 3), ("CE2_CM1", 3, 4), ("CM1_CM2", 4, 5)] if fin else
           [("CI_CP", 0, 1), ("CE1_CE2", 2, 3), ("CM1_CM2", 4, 5)])
    for lig, lib in (("simple", "Simple"), ("jumelee", "Jumelée"), ("multi", "Multigrade")):
        y += pas
        R.t(X0 + (0 if fin else 38), y, lib, fs)
        if lig == "jumelee":
            for code, a, b_ in jum:
                cx = (cols[a] + cols[b_]) / 2
                R.cases_slash(cx - 9, y, 1, 11, f"sp.jumelee.{code}", fs)
        else:
            for n, cx in zip(NIV_EP, cols):
                R.cases_slash(cx - 14, y, 1, 21, f"sp.{lig}.{n}", fs)
        R.cases_slash(xs_sal + 2, y, 2, 21, f"sp.{lig}.salles", fs)
    y += pas * 1.2
    R.t(X0, y, "(1) Uniquement pour le privé.", 7.5 if not fin else 8.5)
    pied(R, 1, doc)


# ------------------------------------------------------------------ tableaux à partir du schéma
def cellules_tableau(R, b, lib_col=True, entete_opts=None, corps_opts=None, lignes_libs=None, coin_vide=True):
    """Construit les cellules d'un tableau du schéma (ligne 0 = en-tête de groupe, ligne 1 = sous-colonnes)."""
    eo = {"size": 8.5}
    eo.update(entete_opts or {})
    co = {"size": 8.5}
    co.update(corps_opts or {})
    sous = b.get("sous")
    cells = []
    off = 1 if lib_col else 0
    nh = 2 if sous else 1
    if lib_col and coin_vide:
        cells.append((0, 0, nh, 1, "", {"sans_bord": True}))
    j = off
    for gr in b["groupes"]:
        if sous:
            cells.append((0, j, 1, len(sous), gr["l"], eo))
            for s, slib in sous:
                cells.append((1, j, 1, 1, slib, eo))
                j += 1
        else:
            cells.append((0, j, 1, 1, gr["l"], eo))
            j += 1
    for i, (lc, llib) in enumerate(b["lignes"]):
        r = nh + i
        if lib_col:
            cells.append((r, 0, 1, 1, (lignes_libs or {}).get(lc, llib), dict(co, align="l")))
        j = off
        for gr in b["groupes"]:
            for s in ([x for x, _ in sous] if sous else [None]):
                k = f"{b['k']}.{lc}.{gr['c']}" + (f"_{s}" if s else "")
                cells.append((r, j, 1, 1, R.val(k), {"val": True, "size": 8.5}))
                j += 1
    return cells


def bloc(doc, k):
    for s in schema(doc):
        for b in s["blocs"]:
            if b.get("k") == k and b["t"] == "tableau":
                return b
    raise KeyError(k)


def _bornes(debut, largeurs):
    xs = [debut]
    for w in largeurs:
        xs.append(xs[-1] + w)
    return xs


def page2_ep(R, doc):
    fin = DOCS[doc]["moment"] == "fin"
    T = R.FB if fin else "Helvetica-Bold"
    hs = 11.5 if fin else 11

    def titre(y, num, lib, x=None):
        x = x if x is not None else (43 if fin else 24)
        if fin:
            xx = R.t(x, y, num + " ", hs, T)
            R.souligne(xx, y, lib, hs, T)
        else:
            R.t(x, y, f"{num} {lib}", hs, T)

    # 3. effectifs
    b = bloc(doc, "eff")
    if fin:
        titre(49, "3.", "EFFECTIF DES ELEVES PAR SEXE ET PAR CLASSE")
        xs = _bornes(26, [79] + [474 / 21] * 21)
        ys = [65, 86, 107, 138, 169, 190, 211, 232]
        libs = {"debut": "Nombre d’élèves\nen début d’année", "fin": "Nombre d'élèves\nfin d'année"}
        cells = cellules_tableau(R, b, entete_opts={"size": 9, "font": R.FB}, corps_opts={"size": 8.2},
                                 lignes_libs=libs)
        # le coin supérieur gauche n'a pas de cadre dans le modèle
    else:
        titre(62, "3.", "EFFECTIF DES ELEVES PAR SEXE ET PAR CLASSE")
        xs = _bornes(30, [89] + [460 / 21] * 21)
        ys = [83, 97, 113, 148, 183, 218, 253, 288]
        cells = cellules_tableau(R, b, entete_opts={"size": 7.5}, corps_opts={"size": 7.5})
        for i, cl in enumerate(cells):  # sous-colonnes G/F/T alignées à gauche comme sur le modèle
            if cl[0] == 1:
                cells[i] = (cl[0], cl[1], 1, 1, cl[4], {"size": 7.5, "align": "l"})
    R.grille(xs, ys, cells)
    # 4. infrastructures
    b = bloc(doc, "infra")
    if fin:
        titre(247, "4.", "INFRASTRUCTURES")
        xs = [48, 133, 253, 384, 504, 563]
        ys = [274, 301, 328, 355]
        cells = cellules_tableau(R, b, entete_opts={"size": 9.5}, corps_opts={"size": 9.5})
    else:
        titre(312, "4.", "INFRASTRUCTURES")
        xs = [30, 119, 250, 384, 515, 580]
        ys = [332, 357, 382, 409]
        cells = cellules_tableau(R, b, entete_opts={"size": 8.8}, corps_opts={"size": 8.8})
    cells = [(r, k, rs, cs, t, dict(o, align="c") if k == 0 and r > 0 else o) for (r, k, rs, cs, t, o) in cells]
    R.grille(xs, ys, cells)
    # 5. mobilier / 6. manuels
    for k, num, lib, yt, ys_ in (("mob", "5.", "MOBILIER", 384 if fin else 434,
                                  [397, 435, 468, 502, 535, 569] if fin else [446, 468, 499, 531, 563, 597]),
                                 ("man", "6.", "MANUELS :", 582 if fin else 615,
                                  [589, 613, 645, 678] if fin else [631, 653, 684, 716])):
        b = bloc(doc, k)
        if fin:
            titre(yt, num, lib.replace(" :", ""))
            if lib.endswith(":"):
                R.t(43 + R.c.stringWidth("6. MANUELS", R.FB, hs) + 1, yt, " :", hs, R.FB)
            xs = [42, 138, 191, 248, 312, 369, 425, 482, 558]
            cells = cellules_tableau(R, b, entete_opts={"size": 8.5, "font": R.FB, "haut": True}, corps_opts={"size": 8.5})
        else:
            titre(yt, num, lib)
            xs = _bornes(30, [89] + [65.8] * 7)
            cells = cellules_tableau(R, b, entete_opts={"size": 8.5}, corps_opts={"size": 8.5})
        R.grille(xs, ys_, cells)
    if fin:
        b = bloc(doc, "gest")
        titre(691, "7.", "FONCTIONNEMENT DES STRUCTURES DE GESTION")
        xs = [42, 138, 262, 404, 546]
        cells = cellules_tableau(R, b, entete_opts={"size": 8.5}, corps_opts={"size": 8.5})
        R.grille(xs, [699, 723, 755], cells)
    pied(R, 2, doc)


# ------------------------------------------------------------------ EM : pages 1 et 2
def page1_em(R, doc, annee):
    fin = DOCS[doc]["moment"] == "fin"
    y = entete(R, doc, "times" if fin else "scan")
    if fin:
        X0, X1, fs, pas = 29, 540, 11, 17.7
        a1, a2 = annee_txt(annee)
        y += 25
        x = R.t(203, y, "ANNEE SCOLAIRE : ", 12, R.FB)
        x = R.t(x, y, "20", 11.5)
        R.points(x, x + 16, y)
        R.valeur(x, x + 16, y, "" if R.vierge else a1[2:], 11)
        x = R.t(x + 17, y, " – 20", 11.5)
        R.points(x, x + 18, y)
        R.valeur(x, x + 18, y, "" if R.vierge else a2[2:], 11)
        y += 22
        x = R.t(X0, y, "1. ", 11.5, R.FB)
        R.souligne(x, y, "IDENTIFICATION ET LOCALISATION DE L'ECOLE", 11.5)
    else:
        X0, X1, fs, pas = 56, 540, 8.8, 16.8
        y += 12
        R.t(57, y, "I.", 10, "Helvetica-Bold")
        R.souligne(83, y, "IDENTIFICATION ET LOCALISATION DE L'ECOLE", 10, "Helvetica-Bold")
    y += pas
    R.champ(X0, y, "1.1 Nom de l'école " + (": " if fin else ""), "nom_ecole", X1, fs)
    y += pas
    for num, lib, ka, kr in (("1.2", "Année de création", "annee_creation", "ref_creation"),
                             ("1.3", "Année dernière extension", "annee_extension", "ref_extension")):
        x = R.t(X0, y, f"{num}  {lib}  ", fs)
        x = R.cases_slash(x, y, 4, 16 if fin else 14, ka, fs)
        R.champ(x + 8, y, "Référence", kr, X1, fs)
        y += pas
    x = R.t(X0, y, "1.4  Statut : Public", fs)
    x = R.cases_trait(x + 14, y, 26, coche=R.choix("statut", "Public"), size=fs)
    x = R.t(x + 20, y, "Privé", fs)
    R.cases_trait(x + 14, y, 26, coche=R.choix("statut", "Privé"), size=fs)
    y += pas
    x = R.t(X0 + 25, y, "Centre Préscolaire Communautaire", fs)
    x = R.cases_trait(x + 8, y, 22, coche=R.choix("statut", "Centre préscolaire communautaire"), size=fs)
    R.champ(x + 30, y, "Si Communautaire, préciser l'initiative ", "initiative", X1, fs)
    y += pas
    ordre = [("departement", "Département"), ("commune", "Commune"), ("arrondissement", "Arrondissement")] + \
            [("cs", "Circonscription scolaire"), ("zone", "Zone pédagogique"), ("up", "Unité pédagogique"),
             ("village", "Village  ou quartier de ville"), ("adresse_postale", "Adresse postale"),
             ("contact_directeur", "Contact du Directeur/Directrice")]
    for i, (k, lib) in enumerate(ordre, 5):
        R.champ(X0, y, f"1.{i}  {lib} ", k, X1, fs)
        y += pas
    if fin:
        R.t(X0, y, "II.", 11.5, R.FB)
        R.souligne(75, y, "INFORMATIONS GENERALES", 11.5)
    else:
        R.t(55, y, "II.", 10, "Helvetica-Bold")
        R.souligne(78, y, "INFORMATIONS GENERALES", 10, "Helvetica-Bold")
    y += pas
    R.champ(X0, y, "2.1 Nom et prénoms du fondateur/fondatrice (pour les EM privées)", "fondateur", X1, fs)
    y += pas
    R.champ(X0, y, "2.2  Nom et prénoms du Directeur/Directrice", "directeur_nom", X1, fs)
    tit = R.val("directeur_titre")  # souligne « Directeur » ou « Directrice » selon le titre
    if tit in ("Directeur", "Directrice"):
        x_a = X0 + R.c.stringWidth("2.2  Nom et prénoms du ", R.F, fs)
        mot = "Directeur" if tit == "Directeur" else "Directrice"
        x_m = x_a if tit == "Directeur" else x_a + R.c.stringWidth("Directeur/", R.F, fs)
        R.c.setStrokeColor(R.col.HexColor(BLEU_VAL))
        R.c.setLineWidth(0.9)
        R.c.line(x_m, R.Y(y) - 2, x_m + R.c.stringWidth(mot, R.F, fs), R.Y(y) - 2)
        R.c.setStrokeColor(R.col.black)
    y += pas
    x = R.t(X0, y, "2.3  Nombre de sections autorisées", fs)
    R.cases_trait(x + 10, y, 26, "sections_autorisees", fs)
    x = R.t(262, y, "Nombre de sections ouvertes", fs)
    R.cases_trait(x + 12, y, 26, "sections_ouvertes", fs)
    y += pas
    x = R.t(X0, y, "2.4  Nombre de salles de classe  existantes", fs)
    R.cases_trait(x + 8, y, 26, "salles_existantes", fs)
    x = R.t(290 if fin else 280, y, "Nombre de salles de classe utilisées", fs)
    R.cases_trait(x + 10, y, 26, "salles_utilisees", fs)
    y += pas
    fs2 = fs - (1.3 if fin else 0.2)
    x = R.t(X0, y, "2.5  L’école dispose-t-elle d’une cantine fonctionnelle : oui ", fs2)
    x = R.cases_trait(x + 1, y, 22, coche=R.choix("cantine", "oui"), size=fs2)
    x = R.t(x + 8, y, "non ", fs2)
    x = R.cases_trait(x + 1, y, 22, coche=R.choix("cantine", "non"), size=fs2)
    R.champ(x + 6, y, "Si oui précisez l’organisme de soutien ", "cantine_organisme", X1 + 4, fs2)
    y += pas
    x = R.t(X0, y, "2.6  L’école dispose-t-elle d’un dispositif de lavage de main fonctionnel : oui ", fs)
    x = R.cases_trait(x + 1, y, 24, coche=R.choix("lavage", "oui"), size=fs)
    x = R.t(x + 12, y, "non ", fs)
    R.cases_trait(x + 1, y, 24, coche=R.choix("lavage", "non"), size=fs)
    y += pas
    x = R.t(X0, y, "2.7  L’école dispose-t-elle d’une structure de gestion collégiale : oui ", fs2)
    x = R.cases_trait(x + 1, y, 20, coche=R.choix("gestion", "oui"), size=fs2)
    x = R.t(x + 8, y, "non ", fs2)
    x = R.cases_trait(x + 1, y, 20, coche=R.choix("gestion", "non"), size=fs2)
    R.t(x + 2, y, " si oui cocher la case correspondante", fs2)
    y += pas
    x = R.t(X0 + 22 if fin else 63, y, "APE ", fs)
    x = R.cases_trait(x + (2 if fin else 26), y, 24, coche=R.choix("g_ape", "oui"), size=fs)
    x = R.t(x + 24, y, "AME ", fs)
    x = R.cases_trait(x + (2 if fin else 30), y, 24, coche=R.choix("g_ame", "oui"), size=fs)
    x = R.t(x + 24, y, "Comité de direction ", fs)
    x = R.cases_trait(x + (6 if fin else 14), y, 24, coche=R.choix("g_comite", "oui"), size=fs)
    R.champ(x + 24, y, "Autres à préciser ", "g_autres", X1, fs)
    y += pas + (0 if fin else 8)
    if fin:
        R.t(X0, y, "III.", 11.5, R.FB)
        R.souligne(75, y, "REPARTITION DES ENFANTS PAR SECTION", 11.5)
        xs = [29, 178, 220, 263, 306, 348, 391, 433, 475, 511, 553]
        ys = [y + 20, y + 43, y + 62, y + 83, y + 104, y + 125, y + 153]
        libs = None
    else:
        R.t(28, y, "III", 10, "Helvetica-Bold")
        R.souligne(43, y, "REPARTITION DES ENFANTS PAR SECTION", 10, "Helvetica-Bold")
        xs = [60, 111, 162, 218, 262, 312, 361, 411, 451, 507, 558]
        ys = [y + 17, y + 31, y + 43, y + 76, y + 114]
        libs = {"debut": "Effectif au\ndébut de\nl’année", "besoin": "Dont enfants\nà besoin\nspécifique"}
    b = bloc(doc, "rep")
    cells = cellules_tableau(R, b, entete_opts={"size": 9.5 if fin else 8.5}, corps_opts={"size": 9.5 if fin else 8.3},
                             lignes_libs=libs)
    cells = [(r, k, rs, cs, t, dict(o, align="c") if k == 0 else o) for (r, k, rs, cs, t, o) in cells]
    R.grille(xs, ys, cells)
    pied(R, 1, doc)


def page2_em(R, doc):
    fin = DOCS[doc]["moment"] == "fin"
    hs = 11.5 if fin else 10
    TB = R.FB if fin else "Helvetica-Bold"
    fs = 9.5 if fin else 8.3

    def titre(y, num, lib, xnum, xlib, suite=""):
        R.t(xnum, y, num, hs, TB)
        x = R.souligne(xlib, y, lib, hs, TB)
        if suite:
            R.t(x, y, suite, hs, TB if fin else "Helvetica")

    def tab(k, xs, ys, libs=None, coin=True, **kw):
        b = bloc(doc, k)
        cells = cellules_tableau(R, b, entete_opts={"size": fs}, corps_opts={"size": fs}, lignes_libs=libs, coin_vide=coin)
        R.grille(xs, ys, cells)
        return b

    if fin:
        titre(35, "IV.", "STRUCTURE PEDAGOGIQUE", 61, 107)
        tab("sp", [29, 165, 282, 395, 514], [54, 82, 100, 118, 136])
        titre(154, "V.", "MATERIEL PEDAGOGIQUE", 53, 95)
        _tab_autres(R, doc, "matped", [29, 135, 248, 355, 447, 546], [172, 192, 210, 229], fs,
                    [("paeapem", "Programmes d'activités\n(PAEAPEM)"), ("guides", "Guides pédagogiques"),
                     ("recueils", "Recueils de jeux")], [("autres", "matped_autres_lib")])
        titre(247, "VI.", "INFRASTRUCTURE", 53, 83)
        tab("infra", [29, 128, 220, 326, 419, 496, 567], [266, 296, 312, 332], coin=False)
        titre(352, "VII.", "MOBILIER (mentionner chaque fois le nombre correspondant)", 29, 75)
        _tab_autres(R, doc, "mob", [29, 72, 130, 187, 239, 288, 336, 385, 435, 479, 524, 567], [371, 408, 423, 439], fs,
                    None, [("autre1", "mob_autre1_lib"), ("autre2", "mob_autre2_lib")])
        titre(458, "VIII.", "EQUIPEMENTS EXTERIEURS (mentionner chaque fois le nombre correspondant)", 29, 83)
        tab("ext", [29, 74, 130, 175, 222, 274, 319, 373, 425, 467, 524, 574], [478, 513, 531])
        R.champ(29, 551, "Autres à préciser ", "ext_autres", 560, 11)
        titre(564, "IX.", "EQUIPEMENTS INTERIEURS (cocher la case correspondant)", 29, 71)
        tab("int", [29, 89, 155, 225, 285, 342, 398, 455, 515, 574], [582, 634, 659])
        R.champ(29, 678, "Autres à préciser ", "int_autres", 560, 11)
        titre(692, "X.", "FONCTIONNEMENT DES STRUCTURES DE GESTION", 29, 42)
        tab("gest", [29, 114, 213, 319, 454, 574], [710, 753, 776])
    else:
        titre(41, "IV.", "STRUCTURE PEDAGOGIQUE", 58, 86)
        tab("sp", [119, 227, 320, 419, 516], [60, 82, 95, 108, 127])
        titre(140, "V.", "MATERIEL PEDAGOGIQUE", 56, 82)
        _tab_autres(R, doc, "matped", [168, 268, 368, 459, 514, 565], [161, 181, 181, 200], fs,
                    [("paeapem", "Programmes d'activités\n(PAEAPEM)"), ("guides", "Guides pédagogiques"),
                     ("recueils", "Recueils de\njeux")], [("autres", "matped_autres_lib")], simple_autres=True)
        R.t(55, 211, "VI. INFRASTRUCTURE", hs, TB)
        R.t(55 + R.c.stringWidth("VI. INFRASTRUCTURE ", TB, hs), 211, "( écrire le nombre)", hs - 0.5)
        tab("infra", [13, 117, 224, 316, 416, 513, 564], [227, 257, 277, 296],
            libs=None)
        titre(306, "VII.", "MOBILIER (mentionner chaque fois le nombre correspondant)", 53, 82)
        _tab_autres(R, doc, "mob", [12, 62, 114, 166, 222, 265, 314, 365, 414, 455, 510, 563], [322, 362, 375, 392], fs,
                    None, [("autre1", "mob_autre1_lib"), ("autre2", "mob_autre2_lib")])
        titre(404, "VIII.", "EQUIPEMENTS EXTERIEURS ", 52, 84, "(mentionner chaque fois le nombre correspondant)")
        tab("ext", [11, 61, 113, 163, 220, 263, 313, 362, 412, 454, 509, 561], [418, 447, 469])
        R.champ(27, 481, "Autres à préciser ", "ext_autres", 472, 8.5)
        titre(492, "IX.", "EQUIPEMENTS INTERIEURS (cocher la case correspondant)", 50, 76)
        tab("int", [59, 110, 162, 262, 311, 361, 410, 451, 507, 559], [510, 557, 578])
        R.champ(25, 593, "Autres à préciser ", "int_autres", 478, 8.5)
        R.t(48, 610, "X.", hs, TB)
        R.souligne(57, 610, "FONCTIONNEMENT DES STRUCTURES DE GESTION", hs, TB)
        b = bloc(doc, "gest")
        cells = cellules_tableau(R, b, entete_opts={"size": 8.3, "font": "Helvetica-Bold"}, corps_opts={"size": 8.3})
        R.grille([6, 108, 216, 359, 450, 556], [626, 664, 691], cells)
    pied(R, 2, doc)


def _tab_autres(R, doc, k, xs, ys, fs, libs_haut, autres, simple_autres=False):
    """Tableau à une ligne « Nombre » dont les dernières colonnes « Autres (à préciser) » ont une sous-case
    pour le libellé (modèles EM : V et VII)."""
    b = bloc(doc, k)
    cols = [gr["c"] for gr in b["groupes"]]
    libs = dict(libs_haut or [(gr["c"], gr["l"]) for gr in b["groupes"]])
    n_aut = len(autres)
    cells = [(0, 0, 3 if ys[1] != ys[2] else 2, 1, "", {"sans_bord": True})]
    j = 1
    for c_ in cols:
        if c_ in dict(autres):
            continue
        cells.append((0, j, 2, 1, libs.get(c_, ""), {"size": fs}))
        j += 1
    if simple_autres:  # rentrée EM, V : « Autres » sans sous-case (le libellé est écrit avec le nombre)
        cells.append((0, j, 2, 1, "Autres", {"size": fs}))
    else:
        cells.append((0, j, 1, n_aut, "Autres (à préciser)", {"size": fs, "font": R.FI if n_aut else R.F}))
        for i, (c_, klib) in enumerate(autres):
            cells.append((1, j + i, 1, 1, R.val(klib), {"val": True, "size": fs - 1}))
    cells.append((2, 0, 1, 1, "Nombre", {"size": fs, "align": "l"}))
    for i, c_ in enumerate([c for c in cols if c not in dict(autres)] + [c for c, _ in autres]):
        txt = R.val(f"{k}.nb.{c_}")
        if simple_autres and c_ in dict(autres):
            lib = R.val(dict(autres)[c_])
            txt = f"{txt} ({lib})" if txt and lib else (txt or lib)
        cells.append((2, 1 + i, 1, 1, txt, {"val": True, "size": fs}))
    R.grille(xs, ys, cells)


# ------------------------------------------------------------------ état nominatif (paysage)
def colonnes_pdf_personnel(doc):
    """[(groupe|None, [(code, libellé, largeur, rotation)])] dans l'ordre du modèle."""
    ep = DOCS[doc]["cycle"] == "primaire"
    fin = DOCS[doc]["moment"] == "fin"
    L = [(None, [("no", "N° d'ordre", 24, True)]), (None, [("mat", "N° matricule (1)", 41 if ep else 53, False)]),
         (None, [("nip", "NIP", 44, False)]),
         (None, [("nom", "Nom et Prénoms", 107 if ep else 158, False)]),
         ("Sexe (2)" if ep else "sexe\n(2)", [("sexe_M", "M", 20, False), ("sexe_F", "F", 20, False)]),
         (None, [("naiss", "Année de naissance", 54, False)]),
         ("Diplômes le plus élevé (3)" if ep else "Diplôme le plus élévé (3)",
          [("dacad", "Acadé\n-mique" if ep else "académique", 34 if ep else 22, not ep),
           ("dprof", "Profes-\nsionnel" if ep else "professionnel", 37 if ep else 28, not ep)]),
         (None, [("grade", "Grade", 29 if ep else 36, ep)]), (None, [("statut", "Statut    (4)", 26 if ep else 36, ep)]),
         (None, [("fonction", "Fonction", 44 if ep else 49, False)])]
    if ep:
        L.append(("Cours tenus", [(f"c_{n}", n, 20.6, True) for n in NIV_EP]))
    else:
        L.append((None, [("qualite", "Qualité\n(5)", 36, False)]))
        L.append(("Section\ntenue", [("s_pet", "Section des Petits", 21, True), ("s_gra", "Section des Grands", 28, True)]))
    L.append((None, [("indice", "Indice réel", 22 if ep else 36, ep)]))
    L.append(("Ancienneté", [("afp", "Fonction publique", 27 if ep else 21, True), ("adep", "Département", 27 if ep else 21, True),
                             ("aecole", "Ecole", 20 if ep else 21, True)]))
    if doc == "rentree-em":
        L.append(("Dernière formation", [("fdate", "Date", 45, False), ("fnature", "Nature (6)", 55, False)]))
        L.append((None, [("obs", "Obs.", 50, False)]))
    elif ep:
        L.append((None, [("form", "Date de la dernière formation continue (5)", 46, False)]))
    if fin:
        vis = [("vinsp", "Inspecteur", 20.5, True), ("vcp", "CP", 20.5, True), ("vdir", "Directeur", 20.5, True)]
        if ep:
            L.append(("Nombre de visites (5)", vis))
            L.append((None, [("pup", "% participation aux UP", 22, True)]))
        else:
            L.append(("Nombre de visites (6)", vis + [("pup", "% participation aux UP", 35, True)]))
    return L


NOTES_PERSONNEL = {
    "rentree-ep": ["(1) Pour les FE  et ACE,  indiquer le numéro matricule figurant sur la fiche de paie",
                   "(2) Cocher \"M\" pour masculin et \"F\" pour féminin",
                   "(3) Diplômes académiques (BEPC, BAC, LICENCE etc.) ou professionnels (CEAP, CAP, etc.) le plus élevé",
                   "(4) C'est le statut de l'enseignant? Il peut être FE, ACE, Contractuel Non Reversé (CNR), Stagiaire, "
                   "Suppléant, PRIVE ou Autre",
                   "(5) Il s'agit des formations organisées par le ministère ou avec sa collaboration."],
    "fin-ep": ["(1) Pour les FE et ACE, indiquer le numéro matricule figurant sur la fiche de paie",
               "(2) Cocher \"M\" pour masculin et \"F\" pour féminin",
               "(3) Diplômes académiques (BEPC, BAC, LICENCE etc.) ou professionnels (CEAP, CAP, etc.) le plus élevé",
               "(4) C'est le statut de l’enseignant ? Il peut être FE, ACE, Contractuel Non Reversé (CNR), Stagiaire, "
               "Suppléant, PRIVE ou Autre",
               "(5) Il s'agit des formations organisées par le ministère ou avec sa collaboration."],
    "rentree-em": ["(1) Pour les APE  et ACE,  indiquer le numéro matricule figurant sur la fiche de paie",
                   "(2) Cocher \"M\" pour masculin et \"F\" pour féminin",
                   "(3) Diplômes académiques (BEPC, BAC, LICENCE etc.) ou professionnels (CEAP, CAP, etc.) le plus élevé",
                   "(4) C'est le statut de l'enseignant. Il peut être Fonctionnaire de l'Etat (FE), ACE, Aspirant, "
                   "Contractuel Non Reversé (CNR), Stagiaire, PRIVE ou Autre",
                   "(5) La qualité peut-être \"Instituteur\" ou \"Educateur\" (Voir Guide)",
                   "(6) Préciser le type de formation : Formation diplômante, recyclage... (Voir Guide)"],
    "fin-em": ["(1)   Pour les Fonctionnaires de l'Etat (FE)  et ACE,  indiquer le numéro matricule figurant sur la fiche de paie",
               "(2)   Cocher \"M\" pour masculin et \"F\" pour féminin",
               "(3)   Diplômes académiques (BEPC, BAC, LICENCE etc.) ou professionnels (CEAP, CAP, etc.) le plus élevé",
               "(4)   C'est le statut de l'enseignant. Il peut être Fonctionnaire de l'Etat (FE), ACE, Aspirant, Contractuel "
               "Non Reversé (CNR), Stagiaire, PRIVE ou Autre",
               "(5)   La qualité peut être \"Instituteur\" ou \"Educateur\" (Voir Guide)",
               "(6)   Il s'agit des inspections, contrôles et visites effectués par le personnel d'encadrement et le "
               "Directeur à l'enseignant au cours de l'année antérieure"],
}


def pages_personnel(R, doc, n_page0):
    """État nominatif sur une ou plusieurs pages A4 paysage (12/10/9 lignes par page comme le modèle)."""
    from reportlab.lib.pagesizes import A4, landscape
    info = DOCS[doc]
    ep, fin = info["cycle"] == "primaire", info["moment"] == "fin"
    if R.synth:
        page_personnel_synthese(R, doc, n_page0)
        return
    mini = bloc_personnel(doc)["min"]
    n = mini if R.vierge else nb_lignes_personnel(doc, R.v)
    R.lus.add("pers_n")
    L = colonnes_pdf_personnel(doc)
    plates = [c for _, cols in L for c in cols]
    X0, X1 = (22, 805) if ep else (29, 815)
    tot = sum(c[2] for c in plates)
    ech = (X1 - X0) / tot
    xs = [X0]
    for c_ in plates:
        xs.append(xs[-1] + c_[2] * ech)
    serif = fin
    lignes_page = mini
    pages = max(1, -(-n // lignes_page))
    for p in range(pages):
        R.c.setPageSize(landscape(A4))
        # titre
        ttl = "ETAT NOMINATIF DU PERSONNEL ENSEIGNANT" if ep else "ETAT  NOMINATIF  DU  PERSONNEL  ENSEIGNANT"
        num = "7." if ep else "XI."
        if fin or not ep:
            x = R.t(91 if ep else 79, 35, num + " ", 12, "Times-Bold" if serif else "Helvetica-Bold")
            R.souligne(x, 35, ttl, 12, "Times-Bold" if serif else "Helvetica-Bold")
        else:
            R.t(60, 35, f"{num} {ttl}", 12, "Helvetica-Bold")
        if p:
            R.t(X1, 35, f"(suite – page {p + 1}/{pages})", 8, R.F, droite=True)
        hg, hs_ = (47, 66) if not ep else (41, 57)
        y0 = 50 if not ep else 72
        rh = 20 if not ep else 18
        nb = min(lignes_page, n - p * lignes_page)
        ys = [y0, y0 + hg, y0 + hg + hs_] + [y0 + hg + hs_ + rh * (i + 1) for i in range(nb)]
        cells = []
        j = 0
        fs = 8.5 if serif else 8
        for grp, cols in L:
            if grp:
                cells.append((0, j, 1, len(cols), grp, {"size": fs + (1 if not ep else 0.5)}))
                for c_ in cols:
                    cells.append((1, j, 1, 1, c_[1], {"size": fs - 0.5, "rot": c_[3]}))
                    j += 1
            else:
                c_ = cols[0]
                cells.append((0, j, 2, 1, c_[1], {"size": fs + (1 if c_[0] == "nom" else 0), "rot": c_[3]}))
                j += 1
        R.grille(xs, ys, cells)
        # corps
        idx = {c_[0]: i for i, c_ in enumerate(plates)}
        for r in range(nb):
            i = p * lignes_page + r + 1
            yt, yb = ys[2 + r], ys[3 + r]
            R.grille(xs, [yt, yb], [(0, k, 1, 1, "", {}) for k in range(len(plates))])
            ym = (yt + yb) / 2
            pre = f"pers.{i}."
            R.t((xs[0] + xs[1]) / 2 if not fin or not ep else xs[0] + 3, ym + 3.5,
                f"{i:02d}" if (ep and fin) else str(i), 10 if serif else 9, R.F, centre=not (fin and ep))
            sexe = R.val(pre + "sexe")
            for code in ("sexe_M", "sexe_F"):
                k = idx[code]
                R.carre((xs[k] + xs[k + 1]) / 2, ym - 1, 6.5, sexe == code[-1])
            k = idx["naiss"]
            R.annee_boites((xs[k] + xs[k + 1]) / 2, ym + 2, R.val(pre + "naiss"))
            if ep:
                cours = cours_de(R.val(pre + "cours"))
                for nv in NIV_EP:
                    k = idx[f"c_{nv}"]
                    R.carre((xs[k] + xs[k + 1]) / 2, ym - 1, 6.5, nv in cours)
            else:
                sec = R.val(pre + "section")
                for code, cle in (("s_pet", "Petits"), ("s_gra", "Grands")):
                    k = idx[code]
                    R.carre((xs[k] + xs[k + 1]) / 2, ym - 1, 6.5, cle in sec)
            fct = R.val(pre + "fonction")
            k = idx["fonction"]
            if not fct and (R.vierge or not R.val(pre + "nom")):
                fct = ("Direct…." if ep else "Directeur/\nDirectrice") if i == 1 else "Adjoint"
                if not ep and i == 1:
                    R.t((xs[k] + xs[k + 1]) / 2, ym - 1, "Directeur/", 7, R.F, centre=True)
                    R.t((xs[k] + xs[k + 1]) / 2, ym + 6, "Directrice", 7, R.F, centre=True)
                else:
                    R.t((xs[k] + xs[k + 1]) / 2, ym + 3.5, fct, 9 if serif else 8, R.F, centre=True)
            else:
                R.valeur(xs[k] + 1, xs[k + 1] - 1, ym + 3, fct, 8, centre=True)
            for code in ("mat", "nip", "nom", "dacad", "dprof", "grade", "statut", "qualite", "indice", "afp", "adep",
                         "aecole", "form", "fdate", "fnature", "obs", "vinsp", "vcp", "vdir", "pup"):
                if code in idx:
                    k = idx[code]
                    s = R.val(pre + code)
                    if code == "pup" and s and s != "-":
                        s += " %"
                    R.valeur(xs[k] + 1.5, xs[k + 1] - 1.5, ym + 3, s, 8, centre=code != "nom")
        # notes de bas et visas (dernière page : visas complets)
        yn = ys[-1] + (14 if not ep else 16)
        notes = NOTES_PERSONNEL[doc]
        for i, nt in enumerate(notes):
            R.t(47 if not ep else (50 if fin else 30), yn + i * 11.3, nt, 8.3 if serif else 7.6, R.F)
        if p == pages - 1:
            visas_personnel(R, doc, yn + len(notes) * 11.3)
        pied_personnel(R, doc, n_page0 + p)
        if p < pages - 1:
            R.c.showPage()


COLS_SYNTH_PERS = [("h", "Hommes"), ("f", "Femmes"), ("t", "Total"), ("dir", "dont directeurs / directrices"),
                   ("cap", "CAP"), ("ceap", "CEAP"), ("dpa", "Autre diplôme prof."), ("dpn", "Diplôme prof. non précisé"),
                   ("nip", "NIP renseigné")]


def statuts_synthese():
    import m_recensement
    return [(k, lib) for k, lib, _c in m_recensement.STATUTS_SYNTHESE]


def page_personnel_synthese(R, doc, n_page):
    """Fiche consolidée : l'état nominatif (non additionnable) devient un récapitulatif par statut."""
    from reportlab.lib.pagesizes import A4, landscape
    ep = DOCS[doc]["cycle"] == "primaire"
    R.c.setPageSize(landscape(A4))
    num = "7." if ep else "XI."
    x = R.t(60, 35, num + " ", 12, "Helvetica-Bold")
    R.souligne(x, 35, "ETAT NOMINATIF DU PERSONNEL ENSEIGNANT – RÉCAPITULATIF PAR STATUT", 12, "Helvetica-Bold")
    R.t(60, 52, "Établi à partir des états nominatifs transmis par les écoles (liste nominative détaillée : export "
                "Excel, feuille « Personnel »).", 8.5, "Helvetica-Oblique")
    xs = _bornes(60, [200] + [62] * len(COLS_SYNTH_PERS))
    lignes = statuts_synthese() + [("tot", "Total")]
    ys = [66, 100] + [100 + 20 * (i + 1) for i in range(len(lignes))]
    cells = [(0, 0, 1, 1, "Statut", {"size": 9, "font": "Helvetica-Bold"})]
    cells += [(0, j + 1, 1, 1, lib, {"size": 8.5, "font": "Helvetica-Bold"}) for j, (_c, lib) in enumerate(COLS_SYNTH_PERS)]
    for i, (k, lib) in enumerate(lignes, 1):
        cells.append((i, 0, 1, 1, lib, {"size": 9, "align": "l", "font": "Helvetica-Bold" if k == "tot" else R.F}))
        for j, (c_, _l) in enumerate(COLS_SYNTH_PERS):
            cells.append((i, j + 1, 1, 1, R.val(f"pers_s.{k}.{c_}"), {"val": True, "size": 9}))
    R.grille(xs, ys, cells)
    visas_personnel(R, doc, ys[-1] + 14)
    pied_personnel(R, doc, n_page)


def visas_personnel(R, doc, y):
    info = DOCS[doc]
    ep, fin = info["cycle"] == "primaire", info["moment"] == "fin"
    serif = fin
    F = R.F
    fs = 9.2 if serif else 8.5
    W = R.c._pagesize[0]
    xg = 50
    ys = [y + 20, y + 35, y + 50, y + 66]
    R.champ(xg, ys[0], "Date de remplissage :  ", "date_remplissage", xg + 230, fs)
    R.champ(xg, ys[1], "Par Madame / Monsieur ", "par_nom", xg + 225, fs)
    R.champ(xg, ys[2], "Fonction : ", "par_fonction", xg + 230, fs)
    x = R.t(xg - 3, ys[3], "Signature : ", fs, F)
    R.points(x, x + 70, ys[3])
    e = g.get("ecole") if R.ecole_locale else None   # hors école (CS / DDEMP) : ni signature ni cachet locaux
    if not R.vierge and e and R.val("sig_dir") == "Oui":
        from pdfs import image_data_url
        img = image_data_url(R.H.signature(f"ecole:{e['id']}:directeur"))
        if img:
            R.c.drawImage(img, x, R.Y(ys[3] + 8), 90, 32, preserveAspectRatio=True, mask="auto")
    if not R.vierge and R.ecole_locale and R.val("cachet") == "Oui":
        from pdfs import cachet_ecole
        cachet_ecole(R.c, x + 150, R.Y(ys[2]), 24)

    def bloc_visa(cx, yy, l1, l2, knom=None, gras=False, taille=None):
        R.t(cx, yy, l1, taille or fs, "Times-Bold" if gras and serif else ("Helvetica-Bold" if gras else F), centre=True)
        if l2:
            R.t(cx, yy + 11, l2, fs - (0.5 if not gras else 1), F, centre=True)
        if knom:
            s = R.val(knom)
            if s:
                R.valeur(cx - 90, cx + 90, yy + 48, s, 8.5, centre=True)

    num_cp = R.val("cp_zone_num")
    if R.synth:   # fiche consolidée : visa du responsable de la juridiction seulement
        bloc_visa(W - 230, ys[0] - 4, R.ent.get("visa") or "Le Responsable de la juridiction",
                  "(Signature- Nom et Prénoms- Date)", "par_nom")
        return
    if fin:
        bloc_visa(W - 102 if ep else W - 102, y - 30, "Contrôlé par le Responsable de l'Unité", "Pédagogique", "rup_nom")
        bloc_visa(W / 2 + 60 if ep else W / 2 + 60, ys[1] - 2, "Le Chef de la Circonscription Scolaire",
                  "(Signature- Nom et Prénoms- Date)", "chef_nom")
        bloc_visa(216 if ep else 225, ys[3] + 28, f"Contrôlé par le Conseiller Pédagogique de Zone n° {num_cp or '…….'}",
                  "(Signature- Nom et Prénoms- Date)", "cp_nom")
    elif ep:
        bloc_visa(620, ys[0] - 4, "Contrôlé par le Responsable de l'Unité Pédagogique",
                  "(Signature- Nom et Prénoms- Date)", "rup_nom")
        bloc_visa(230, ys[3] + 30, f"Contrôlé par le Conseiller Pédagogique de Zone n° {num_cp or '…'}",
                  "(Signature- Nom et Prénoms- Date)", "cp_nom")
        bloc_visa(620, ys[3] + 30, "Le Chef de la Circonscription Scolaire",
                  "(Signature- Nom et Prénoms- Date)", "chef_nom")
    else:
        bloc_visa(620, ys[0] - 4, "Contrôlé par le Responsable d'Unité Pédagogique",
                  "(Date- signature - Nom et Prénoms )", "rup_nom")
        bloc_visa(230, ys[3] + 28, f"Contrôlé par le Conseiller Pédagogique de la zone n° {num_cp or '…………'}",
                  "(Date- signature - Nom et Prénoms )", "cp_nom", gras=True)
        bloc_visa(620, ys[3] + 30, "Le Chef de la Circonscription Scolaire", "(Date- signature - Nom et Prénoms )",
                  "chef_nom", gras=True, taille=12)


def pied_personnel(R, doc, n):
    info = DOCS[doc]
    if info["cycle"] == "maternelle" and info["moment"] == "rentree":
        pied(R, 3, doc)
        return
    W = R.c._pagesize[0]
    if info["cycle"] == "maternelle":
        R.t(W - 50, R.PH - 38, f"Page {n}", 11, "Times-Bold", droite=True)
    else:
        R.t(W / 2, R.PH - 24, f"Page {n}", 10, R.F, centre=True)


# ------------------------------------------------------------------ annexe GESCOL
def page_annexe(R, doc, annee, ind):
    from reportlab.lib.pagesizes import A4
    R.c.setPageSize(A4)
    info = DOCS[doc]
    R.t(297, 40, "ANNEXE GESCOL – INDICATEURS CALCULÉS (document complémentaire, non officiel)", 10.5,
        "Helvetica-Bold", centre=True)
    R.t(297, 54, f"{info['titre']} · {R.v.get('nom_ecole') or ''} · année scolaire {annee}", 8.5, "Helvetica", centre=True)
    y = 72
    fs = 7.8

    def titre(s):
        nonlocal y
        y += 14
        R.t(30, y, s, 9.5, "Helvetica-Bold")
        y += 5

    def table(entetes, lignes, largeurs):
        nonlocal y
        xs = _bornes(30, [w * 535 / sum(largeurs) for w in largeurs])
        ys = [y + 13 * i for i in range(len(lignes) + 2)]
        cells = [(0, j, 1, 1, h, {"size": fs, "font": "Helvetica-Bold"}) for j, h in enumerate(entetes)]
        for i, l in enumerate(lignes, 1):
            cells += [(i, j, 1, 1, "" if v is None else str(v), {"size": fs, "align": "l" if j == 0 else "c"})
                      for j, v in enumerate(l)]
        R.grille(xs, ys, cells, lw=0.4)
        y = ys[-1] + 4

    if ind.get("inactive"):
        R.t(30, y + 16, "Les indicateurs ne sont calculés que pour l'année scolaire active.", 9)
        return
    # effectifs par âge
    nivs = ind.get("niveaux") or []
    titre("1. Répartition des élèves inscrits par âge (au 31 décembre), niveau et sexe")
    if ind.get("ages") and nivs:
        ent = ["Âge"] + [f"{n} {s}" for n in nivs for s in ("G", "F")] + ["Total"]
        lignes = []
        for a in ind["ages"]:
            vals = [ind["ages_n"].get(f"{a}|{n}|{s}", 0) for n in nivs for s in ("G", "F")]
            lignes.append([f"{a} ans"] + vals + [sum(vals)])
        table(ent, lignes, [2] + [1] * (len(ent) - 1))
    else:
        R.t(30, y + 10, "Aucune date de naissance renseignée.", fs)
        y += 14
    titre("2. Nouveaux inscrits de l'année (hors redoublants)")
    if nivs:
        table(["Niveau", "Garçons", "Filles", "Total"],
              [[n, ind["nouveaux"].get(f"{n}|G", 0), ind["nouveaux"].get(f"{n}|F", 0),
                ind["nouveaux"].get(f"{n}|G", 0) + ind["nouveaux"].get(f"{n}|F", 0)] for n in nivs], [2, 1, 1, 1])
    titre("3. Résultats scolaires (dernière évaluation de l'année ; " +
          ("maîtrise = seuil de matières à 10/20)" if info["cycle"] == "primaire" else "progrès satisfaisants)"))
    if ind.get("resultats"):
        table(["Classe", "Évaluation", "Composés G/F/T", "Maîtrise G/F/T", "Taux de maîtrise", "Admis (bilan) G/F/T"],
              [[r["classe"], r["evaluation"], "{G}/{F}/{T}".format(**r["composes"]), "{G}/{F}/{T}".format(**r["reussis"]),
                f"{r['taux']['T']:.1f} %".replace(".", ","), "{G}/{F}/{T}".format(**r["admis"])]
               for r in ind["resultats"]], [2, 3, 2, 2, 1.5, 2])
    else:
        R.t(30, y + 10, "Aucune évaluation saisie pour cette année.", fs)
        y += 14
    if info["cycle"] == "primaire":
        titre("4. CEP blanc (sessions de l'école) et CEP officiel")
        lignes = [[f"CEP blanc n° {s['numero']} ({s['centre']})", "{G}/{F}/{T}".format(**s["inscrits"]),
                   "{G}/{F}/{T}".format(**s["presents"]), "{G}/{F}/{T}".format(**s["maitrise"]),
                   f"{s['taux']['T']:.1f} %".replace(".", ",")] for s in ind.get("cep_blanc", [])]
        fv = valeurs_calculees(doc, R.v)
        if any(fv.get(f"cep.{l}.T") for l in ("insc", "pres", "adm")):
            f3 = lambda l: f"{fv.get(f'cep.{l}.G') or 0}/{fv.get(f'cep.{l}.F') or 0}/{fv.get(f'cep.{l}.T') or 0}"  # noqa
            pres, adm = entier(fv.get("cep.pres.T")), entier(fv.get("cep.adm.T"))
            lignes.append([f"CEP officiel {fv.get('cep_session') or ''}", f3("insc"), f3("pres"), f3("adm"),
                           f"{100 * adm / pres:.1f} %".replace(".", ",") if pres and adm is not None else ""])
        if lignes:
            table(["Session", "Inscrits G/F/T", "Présents G/F/T", "Admis / maîtrise G/F/T", "Taux"], lignes, [4, 2, 2, 2, 1.3])
        else:
            R.t(30, y + 10, "Aucun résultat de CEP (blanc ou officiel) enregistré.", fs)
            y += 14
    titre(("5. " if info["cycle"] == "primaire" else "4. ") + "Taux de présence (registre de présence)")
    if ind.get("presence"):
        table(["Classe", "Effectif", "Demi-journées de classe", "Absences (demi-journées)", "Taux de présence"],
              [[p["classe"], p["effectif"], p["demi"], p["absences"],
                (f"{p['taux']:.1f} %".replace(".", ",") if p["taux"] is not None else "—")] for p in ind["presence"]],
              [2, 1, 1.6, 1.6, 1.3])
    titre(("6. " if info["cycle"] == "primaire" else "5. ") + "Cantine scolaire (tickets payés)")
    if ind.get("cantine"):
        table(["Classe", "Élèves bénéficiaires", "Repas payés", "Montant (FCFA)"],
              [[x["classe"], x["eleves"], x["repas"], f"{x['montant']:,}".replace(",", " ")] for x in ind["cantine"]],
              [2, 1.3, 1.3, 1.3])
    else:
        R.t(30, y + 10, "Aucune donnée de cantine.", fs)


def generer_pdf(H, doc, annee, v, vierge=False, annexe=False, ind=None, entete=None):
    """PDF du document (même forme que le modèle). Retourne (bytes, clés lues).
    H = None et/ou entete fourni : rendu hors contexte d'école (CS / DDEMP), sans signature ni cachet locaux."""
    from reportlab.lib.pagesizes import A4
    from pdfs import GCanvas
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A4)
    c.setTitle(((entete or {}).get("titre", "") + " – " if (entete or {}).get("titre") else "")
               + DOCS[doc]["titre"] + f" {annee}")
    c.setAuthor("GESCOL")
    info = DOCS[doc]
    R = Rendu(c, v, vierge, info["moment"] == "fin", H, entete=entete)
    if info["cycle"] == "primaire":
        page1_ep(R, doc, annee)
        c.showPage()
        page2_ep(R, doc)
    else:
        page1_em(R, doc, annee)
        c.showPage()
        page2_em(R, doc)
    c.showPage()
    pages_personnel(R, doc, 3)
    if annexe and not vierge:
        c.showPage()
        page_annexe(R, doc, annee, ind or {})
    c.showPage()
    c.save()
    return buf.getvalue(), R.lus


# =====================================================================================================
# 6. EXCEL (même structure que le modèle)
# =====================================================================================================
def _api_doc(doc):
    if doc not in DOCS:
        raise ValueError(f"Document inconnu : {doc}")
    return doc


def valeurs_completes(doc, finales):
    """Dict COMPLET : toutes les cases du document (vides comprises) + cellules calculées."""
    v = {k: "" for k, _sp in champs_editables(doc, v=finales)}
    v.update({k: "" for k in tous_calculs(doc)})
    v.update({k: ("" if x is None else str(x)) for k, x in (finales or {}).items()})
    return valeurs_calculees(doc, v)


_ENTETE_RAPPORT = (("ecole", "nom_ecole"), ("nom", "nom_ecole"), ("cs", "cs"), ("departement", "departement"),
                   ("zone", "zone"), ("up", "up"), ("commune", "commune"), ("arrondissement", "arrondissement"),
                   ("localite", "village"), ("directeur", "directeur_nom"), ("directeur_nom", "directeur_nom"),
                   ("directeur_titre", "directeur_titre"), ("telephone", "telephone"), ("email", "email"))


def pdf_depuis_valeurs(doc, valeurs, annee, entete=None, vierge=False):
    """Rapport OFFICIEL (même forme que côté école : en-tête MEMP, NIP…) rempli avec des valeurs déjà calculées
    (H.rapports_valeurs, paquet de transmission, synthese_valeurs), hors contexte d'école.
    entete : identité {ecole, cs, departement, zone, commune, directeur, directeur_titre…} + options
    {titre, mention, synthese}. Renvoie les octets du PDF."""
    _api_doc(doc)
    e = dict(entete or {})
    e.setdefault("hors_ecole", True)
    v = dict(valeurs or {})
    if not e.get("synthese"):
        for src, k in _ENTETE_RAPPORT:
            if e.get(src) not in (None, "") and v.get(k) in (None, ""):
                v[k] = str(e[src])
        if v.get("directeur_titre") and not v.get("par_fonction"):
            v["par_fonction"] = v["directeur_titre"]
        if v.get("directeur_nom") and not v.get("par_nom"):
            v["par_nom"] = v["directeur_nom"]
        v = valeurs_calculees(doc, v)
    if vierge:
        e.pop("titre", None)
        e.pop("synthese", None)
    data, _lus = generer_pdf(None, doc, annee_valide(annee, annee), v, vierge=vierge, entete=e)
    return data


def lignes_personnel(doc, v):
    """Lignes renseignées de l'état nominatif : [{colonne: valeur}]."""
    out = []
    for i in range(1, PERS_MAX + 1):
        row = {c["c"]: v.get(f"pers.{i}.{c['c']}", "") for c in bloc_personnel(doc)["cols"]}
        if str(row.get("nom") or "").strip() not in ("", "-"):
            out.append(row)
    return out


IDENTITE_RAPPORT = {"nom_ecole", "annee_creation", "ref_creation", "annee_extension", "ref_extension", "initiative",
                    "fondateur", "directeur_titre", "directeur_nom", "zone", "up", "commune", "arrondissement",
                    "village", "bp", "telephone", "email", "adresse_postale", "contact_directeur", "cantine_raison",
                    "cp_zone_num", "cp_nom", "rup_nom", "par_nom", "par_fonction",
                    "chef_nom", "sig_dir", "cachet"}


def synthese_valeurs(doc, ecoles, titre="", infos=None):
    """Rapport consolidé d'une juridiction. ecoles : [(nom de l'école, valeurs)]. Nombres : somme ; choix : nombre
    d'écoles par réponse ; textes : valeur commune ; état nominatif : récapitulatif par statut.
    Renvoie {"valeurs", "controles", "personnel", "n"}."""
    import m_recensement as MR
    _api_doc(doc)
    infos = infos or {}
    liste = [(nom, v or {}) for nom, v in ecoles]
    calc = tous_calculs(doc)
    out, transmis = {}, {}
    for k, sp in champs_editables(doc, n_pers=0):
        if k.startswith("pers") or k in calc or k in IDENTITE_RAPPORT:
            continue   # identité propre à chaque école : sans objet dans une fiche consolidée
        vals = [str(v.get(k) or "").strip() for _n, v in liste]
        vals = [x for x in vals if x not in ("", "-")]
        t = sp.get("type", "texte")
        if t == "choix":
            cpt = {o: 0 for o in sp.get("options", [])}
            for x in vals:
                for o in cpt:
                    if normaliser(o) == normaliser(x):
                        cpt[o] += 1
            out[k] = cpt
        elif t in ("nombre", "pct") or (t == "texte" and vals and all(entier(x) is not None for x in vals)):
            nums = [entier(x) for x in vals if entier(x) is not None]
            if nums:
                out[k] = str(sum(nums))
        elif t == "annee":
            if vals:
                out[k] = max(set(vals), key=vals.count)
        elif vals and len(set(vals)) == 1 and t not in ("tel", "email"):
            out[k] = vals[0]
    for k in calc:
        nums = [entier(v.get(k)) for _n, v in liste if entier(v.get(k)) is not None]
        if nums:
            transmis[k] = sum(nums)
    # récapitulatif du personnel par statut
    pers = []
    for nom_e, v in liste:
        for row in lignes_personnel(doc, v):
            pers.append(dict(row, ecole=nom_e))
            cat = MR._categorie(row.get("statut"), MR.STATUTS_SYNTHESE)
            cols = ["t", "h" if row.get("sexe") == "M" else ("f" if row.get("sexe") == "F" else "")]
            cols += ["nip"] if str(row.get("nip") or "").strip() else []
            cols += ["dir"] if normaliser(row.get("fonction")).startswith("direct") else []
            dp = str(row.get("dprof") or "").upper()
            cols.append("ceap" if "CEAP" in dp else ("cap" if "CAP" in dp else ("dpa" if dp.strip() else "dpn")))
            for col in filter(None, cols):
                for kk in (f"pers_s.{cat}.{col}", f"pers_s.tot.{col}"):
                    out[kk] = str(int(out.get(kk) or 0) + 1)
    fv = valeurs_calculees(doc, out)
    alertes = []
    for k, tot in sorted(transmis.items()):
        if entier(fv.get(k)) is not None and entier(fv.get(k)) != tot:
            alertes.append(("danger", f"{k} : total transmis par les écoles {tot} ≠ total recalculé {fv.get(k)} "
                                      "(G + F = T ou somme des colonnes)."))
    fv.update({"nom_ecole": titre or "Synthèse", "date_remplissage": date.today().strftime("%d/%m/%Y"),
               "sig_dir": "Non", "cachet": "Non", "directeur_titre": "", "pers_n": "0"})
    for k in ("cs", "departement", "par_nom", "par_fonction", "chef_nom"):
        if infos.get(k):
            fv[k] = infos[k]
    ctrl = alertes + [x for x in controles(doc, {k: x for k, x in fv.items() if not isinstance(x, dict)})
                      if "État nominatif" not in x[1]]
    for nom_e, v in liste:
        ctrl += [(niv, f"{nom_e} – {m}") for niv, m in controles(doc, v)[:6]]
    return {"valeurs": fv, "controles": ctrl, "personnel": pers, "n": len(liste)}


def _txt(v):
    if isinstance(v, dict):
        return " · ".join(f"{o} : {x}" for o, x in v.items())
    return "" if v is None else str(v)


def vue_lecture(doc, v, synthese=False):
    """Rapport en lecture (même structure que m_recensement.vue_lecture) pour la page web et l'Excel."""
    _api_doc(doc)
    v = v or {}
    out = []
    for s in schema(doc):
        sec = {"titre": s["titre"], "champs": [], "tableaux": []}
        for b in s["blocs"]:
            if b["t"] == "champ" and b["type"] != "titre":
                sec["champs"].append((b.get("num", ""), b["lib"], _txt(v.get(b["k"]))))
            elif b["t"] == "tableau":
                sous = b.get("sous")
                ent = [[{"txt": "", "cs": 1, "rs": 2 if sous else 1}]]
                if sous:
                    ent.append([])
                cols = []
                for gr in b["groupes"]:
                    ent[0].append({"txt": gr["l"], "cs": len(sous) if sous else 1, "rs": 1})
                    for sc, sl in (sous or [(None, "")]):
                        if sous:
                            ent[1].append({"txt": sl, "cs": 1, "rs": 1})
                        cols.append((gr["c"] + (f"_{sc}" if sc else ""), f"{gr['l']} {sl}".strip()))
                lignes = [{"lib": llib, "st": "", "cells": [_txt(v.get(f"{b['k']}.{lc}.{c}")) for c, _l in cols]}
                          for lc, llib in b["lignes"]]
                sec["tableaux"].append({"titre": s["titre"], "entete": ent, "colonnes": [l for _c, l in cols],
                                        "lignes": lignes, "coin": ""})
            elif b["t"] == "structure_ep":
                cols = NIV_EP + ["Salles utilisées"]
                lignes = []
                for lig, lib in (("simple", "Simple"), ("multi", "Multigrade")):
                    lignes.append({"lib": lib, "st": "", "cells": [_txt(v.get(f"sp.{lig}.{n}")) for n in NIV_EP]
                                   + [_txt(v.get(f"sp.{lig}.salles"))]})
                jum = "; ".join(f"{lib} : {v.get(f'sp.jumelee.{c}')}" for c, lib in b["jumelees"] if v.get(f"sp.jumelee.{c}"))
                lignes.insert(1, {"lib": "Jumelée", "st": "", "cells": [jum] + [""] * 5 + [_txt(v.get("sp.jumelee.salles"))]})
                sec["tableaux"].append({"titre": b["titre"], "entete": [[{"txt": "", "cs": 1, "rs": 1}] +
                                        [{"txt": c, "cs": 1, "rs": 1} for c in cols]], "colonnes": cols,
                                        "lignes": lignes, "coin": ""})
            elif b["t"] == "personnel":
                if synthese:
                    cols = [l for _c, l in COLS_SYNTH_PERS]
                    lignes = [{"lib": lib, "st": "b" if k == "tot" else "",
                               "cells": [_txt(v.get(f"pers_s.{k}.{c}")) for c, _l in COLS_SYNTH_PERS]}
                              for k, lib in statuts_synthese() + [("tot", "Total")]]
                    coin = "Statut"
                else:
                    cols = [c["l"] for c in b["cols"]]
                    lignes = [{"lib": str(i), "st": "", "cells": [_txt(row.get(c["c"])) for c in b["cols"]]}
                              for i, row in enumerate(lignes_personnel(doc, v), 1)]
                    coin = "N°"
                sec["tableaux"].append({"titre": s["titre"], "entete": [[{"txt": coin, "cs": 1, "rs": 1}] +
                                        [{"txt": c, "cs": 1, "rs": 1} for c in cols]], "colonnes": cols,
                                        "lignes": lignes, "coin": coin})
        out.append(sec)
    return out


def generer_excel(doc, annee, v, origine_auto):
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    info = DOCS[doc]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rapport"
    fin_ = Side(style="thin", color="667085")
    bord = Border(top=fin_, bottom=fin_, left=fin_, right=fin_)
    ent = PatternFill("solid", fgColor="DCE6F2")
    centre = Alignment(horizontal="center", vertical="center", wrap_text=True)
    r = 1
    ws.cell(r, 1, "MINISTÈRE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE – RÉPUBLIQUE DU BENIN").font = Font(bold=True)
    r += 1
    ws.cell(r, 1, info["direction"]).font = Font(bold=True)
    r += 1
    ws.cell(r, 1, info["fiche"]).font = Font(bold=True, italic=True, size=13)
    r += 1
    ws.cell(r, 1, f"ANNEE SCOLAIRE : {annee}").font = Font(bold=True)
    r += 2
    largeur = 4
    for s in schema(doc):
        ws.cell(r, 1, s["titre"].upper()).font = Font(bold=True, size=11, color="1F4E79")
        r += 1
        for b in s["blocs"]:
            if b["t"] == "champ":
                if b["type"] == "titre":
                    ws.cell(r, 1, b["lib_titre"]).font = Font(italic=True)
                    r += 1
                    continue
                ws.cell(r, 1, b.get("num", ""))
                ws.cell(r, 2, b["lib"])
                ws.cell(r, 3, v.get(b["k"], ""))
                ws.cell(r, 3).font = Font(color="0B3A8C")
                r += 1
            elif b["t"] == "tableau":
                sous = b.get("sous")
                ncol = sum(len(sous) if sous else 1 for _ in b["groupes"])
                largeur = max(largeur, ncol + 1)
                j = 2
                for gr in b["groupes"]:
                    n = len(sous) if sous else 1
                    c_ = ws.cell(r, j, gr["l"])
                    c_.alignment, c_.fill, c_.font = centre, ent, Font(bold=True)
                    for jj in range(j, j + n):
                        ws.cell(r, jj).border = bord
                    if n > 1:
                        ws.merge_cells(start_row=r, start_column=j, end_row=r, end_column=j + n - 1)
                    if sous:
                        for i, (sc, sl) in enumerate(sous):
                            c2 = ws.cell(r + 1, j + i, sl)
                            c2.alignment, c2.fill, c2.border = centre, ent, bord
                    j += n
                r += 2 if sous else 1
                for lc, llib in b["lignes"]:
                    ws.cell(r, 1, llib).border = bord
                    ws.cell(r, 1).alignment = Alignment(wrap_text=True, vertical="center")
                    j = 2
                    for gr in b["groupes"]:
                        for sc in ([x for x, _ in sous] if sous else [None]):
                            k = f"{b['k']}.{lc}.{gr['c']}" + (f"_{sc}" if sc else "")
                            val = v.get(k, "")
                            n = entier(val)
                            cc = ws.cell(r, j, n if n is not None and str(n) == str(val) else val)
                            cc.border, cc.alignment = bord, centre
                            j += 1
                    r += 1
            elif b["t"] == "structure_ep":
                ws.cell(r, 1, b["titre"]).font = Font(italic=True)
                r += 1
                for j, h in enumerate(NIV_EP + ["Nombre de salles utilisées"], 2):
                    c_ = ws.cell(r, j, h)
                    c_.fill, c_.border, c_.alignment = ent, bord, centre
                r += 1
                jum = dict(b["jumelees"])
                for lig, lib in (("simple", "Simple"), ("jumelee", "Jumelée"), ("multi", "Multigrade")):
                    ws.cell(r, 1, lib).border = bord
                    if lig == "jumelee":
                        ws.cell(r, 2, "; ".join(f"{jum[c]} : {v.get(f'sp.jumelee.{c}')}" for c in jum
                                                if v.get(f"sp.jumelee.{c}")))
                        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
                    else:
                        for j, n in enumerate(NIV_EP, 2):
                            ws.cell(r, j, v.get(f"sp.{lig}.{n}", "")).border = bord
                    ws.cell(r, 8, v.get(f"sp.{lig}.salles", "")).border = bord
                    r += 1
            elif b["t"] == "personnel":
                n = nb_lignes_personnel(doc, v)
                cols = b["cols"]
                largeur = max(largeur, len(cols) + 1)
                ws.cell(r, 1, "N° d'ordre").border = bord
                for j, col in enumerate(cols, 2):
                    c_ = ws.cell(r, j, col["l"])
                    c_.fill, c_.border, c_.alignment, c_.font = ent, bord, centre, Font(bold=True)
                r += 1
                for i in range(1, n + 1):
                    ws.cell(r, 1, i).border = bord
                    for j, col in enumerate(cols, 2):
                        ws.cell(r, j, v.get(f"pers.{i}.{col['c']}", "")).border = bord
                    r += 1
        r += 1
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["C"].width = 22
    for j in range(4, largeur + 3):
        ws.column_dimensions[get_column_letter(j)].width = 11
    ws.oddFooter.center.text = "Conception : Maître Aimé FACHE"
    ws.oddFooter.center.size = 8
    # feuille « Données » : chaque case, son libellé, sa valeur et son origine
    wd = wb.create_sheet("Données")
    for j, h in enumerate(("Clé", "Libellé", "Valeur", "Origine"), 1):
        c_ = wd.cell(1, j, h)
        c_.font, c_.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E79")
    calc = tous_calculs(doc)
    r = 2
    libs = dict((k, sp["lib"]) for k, sp in champs_editables(doc, v=v))
    for s in schema(doc):
        for b in s["blocs"]:
            if b["t"] == "tableau":
                for k, lib in cles_tableau(b):
                    libs.setdefault(k, lib)
    for k, lib in libs.items():
        wd.cell(r, 1, k)
        wd.cell(r, 2, lib)
        wd.cell(r, 3, v.get(k, ""))
        wd.cell(r, 4, "calcul (somme)" if k in calc else origine_auto.get(k, ""))
        r += 1
    wd.column_dimensions["A"].width = 24
    wd.column_dimensions["B"].width = 60
    wd.column_dimensions["C"].width = 30
    wd.column_dimensions["D"].width = 22
    wd.oddFooter.center.text = "Conception : Maître Aimé FACHE"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# =====================================================================================================
# 7. ROUTES
# =====================================================================================================
def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config
    H.schema("""
    CREATE TABLE IF NOT EXISTS rapports_fichiers (      -- rapports officiels scannés/téléversés (archive par année)
        id INTEGER PRIMARY KEY,
        ecole_id INTEGER NOT NULL,
        annee TEXT NOT NULL,
        doc TEXT NOT NULL,
        nom_origine TEXT,
        chemin TEXT NOT NULL,
        taille INTEGER,
        mime TEXT,
        commentaire TEXT,
        televerse_le TEXT,
        televerse_par INTEGER
    );
    """)

    def dossier():
        d = os.path.join(config.INSTANCE_DIR, "rapports")
        os.makedirs(d, exist_ok=True)
        return d

    def annee_demandee():
        return annee_valide(request.values.get("annee", ""), config.ANNEE_ACTIVE)

    def doc_ou_404(doc):
        if doc not in DOCS:
            abort(404)
        return doc

    def fichiers(doc=None, annee=None):
        sql, args = "SELECT * FROM rapports_fichiers WHERE ecole_id=?", [H.eco()]
        if doc:
            sql += " AND doc=?"
            args.append(doc)
        if annee:
            sql += " AND annee=?"
            args.append(annee)
        return q(sql + " ORDER BY annee DESC, televerse_le DESC", args)

    def annees_proposees(annee):
        a0 = int(config.ANNEE_ACTIVE[:4])
        ans = {f"{y}-{y + 1}" for y in range(a0 - 3, a0 + 1)} | {annee}
        for r in q("SELECT cle FROM documents_modules WHERE cle LIKE ?", (f"e{H.eco()}:rapports:%",)):
            m = re.search(r":(\d{4}-\d{4})$", r["cle"])
            if m:
                ans.add(m.group(1))
        for r in q("SELECT DISTINCT annee FROM rapports_fichiers WHERE ecole_id=?", (H.eco(),)):
            ans.add(r["annee"])
        return sorted(ans, reverse=True)

    def rapports_valeurs(doc, annee=None):
        """Valeurs COMPLÈTES du document (calculées par GESCOL + corrigées) pour l'école courante (transmission)."""
        _api_doc(doc)
        an = annee_valide(annee or "", config.ANNEE_ACTIVE)
        return valeurs_completes(doc, donnees_document(H, doc, an)[3])
    H.rapports_valeurs = rapports_valeurs

    @app.context_processor
    def ctx_rapports():
        return {"RAPPORTS_DOCS": DOCS}

    # ------------------------------------------------------------ accueil
    @app.route("/rapports")
    @H.connexion_requise("recensement")
    def rapports_accueil():
        annee = annee_demandee()
        cartes = []
        niveaux = {c["niveau"] for c in H.classes_autorisees()}
        for doc, info in DOCS.items():
            st = lire_stock(H, doc, annee)
            cycle_present = bool(niveaux & set(NIV_EP if info["cycle"] == "primaire" else NIV_EM))
            cartes.append({"doc": doc, "info": info, "maj": st.get("maj"), "par": st.get("par"),
                           "corrections": len(st.get("valeurs") or {}), "fichiers": fichiers(doc, annee),
                           "cycle_present": cycle_present})
        return render_template("rapports_accueil.html", cartes=cartes, annee=annee, annees=annees_proposees(annee),
                               tous_fichiers=fichiers(), armoiries=os.path.exists(os.path.join(dossier(), "armoiries.png")))

    # ------------------------------------------------------------ formulaire (GET) / enregistrement (POST)
    @app.route("/rapports/<doc>", methods=["GET", "POST"])
    @H.connexion_requise("recensement")
    def rapports_formulaire(doc):
        doc = doc_ou_404(doc)
        annee = annee_demandee()
        auto, over, fusion, finales, ind, origine, stock = donnees_document(H, doc, annee)
        erreurs = []
        saisie = None
        if request.method == "POST":
            action = request.form.get("action", "sauver")
            cle = cle_stockage(H.eco(), doc, annee)
            if action == "reinit":
                H.doc_ecrire(cle, {"valeurs": {}, "instantane": valeurs_calculees(doc, auto), "maj": H.maintenant(),
                                   "par": g.user["nom"]})
                H.journal("rapport_reinitialise", f"{doc} {annee}")
                flash("Rapport réinitialisé : toutes les cases reprennent les valeurs calculées par GESCOL.", "success")
                return redirect(url_for("rapports_formulaire", doc=doc, annee=annee))
            try:
                n_pers = int(request.form.get("pers_n") or auto.get("pers_n") or 0)
            except ValueError:
                n_pers = 0
            n_pers = max(bloc_personnel(doc)["min"], min(PERS_MAX, n_pers))
            nouv, erreurs = {}, []
            for k, spec in champs_editables(doc, n_pers):
                brut = (request.form.get(k) or "").strip()
                if brut == "":
                    continue
                ok_, val, msg = valider_valeur(spec, brut)
                if not ok_:
                    erreurs.append(f"{spec['lib']} : {msg}")
                    continue
                if val != str(auto.get(k, "") or ""):
                    nouv[k] = val
            if erreurs:
                for e_ in erreurs[:12]:
                    flash(e_, "danger")
                if len(erreurs) > 12:
                    flash(f"… et {len(erreurs) - 12} autre(s) erreur(s).", "danger")
                flash("Rien n'a été enregistré : corrigez les cases signalées.", "warning")
                saisie = {k: (request.form.get(k) or "").strip() for k, _ in champs_editables(doc, n_pers)}
            else:
                fus = dict(auto)
                fus.update(nouv)
                H.doc_ecrire(cle, {"valeurs": nouv, "instantane": valeurs_calculees(doc, fus), "maj": H.maintenant(),
                                   "par": g.user["nom"]})
                H.journal("rapport_enregistre", f"{doc} {annee} ({len(nouv)} correction(s))")
                flash(f"Rapport enregistré ({len(nouv)} case(s) corrigée(s) à la main, le reste est calculé "
                      "automatiquement).", "success")
                if action == "pdf":
                    return redirect(url_for("rapports_pdf", doc=doc, annee=annee))
                if action == "pdf_annexe":
                    return redirect(url_for("rapports_pdf", doc=doc, annee=annee, annexe=1))
                return redirect(url_for("rapports_formulaire", doc=doc, annee=annee))
        if saisie is not None:  # ré-affichage après erreur : valeurs tapées conservées
            over = {k: val for k, val in saisie.items() if val}
            fusion = dict(auto)
            fusion.update(over)
            finales = valeurs_calculees(doc, fusion)
        n_pers = nb_lignes_personnel(doc, fusion)
        return render_template("rapports_formulaire.html", doc=doc, info=DOCS[doc], annee=annee,
                               annees=annees_proposees(annee), sections=schema(doc), auto=auto, over=over,
                               v=finales, calc=tous_calculs(doc), n_pers=n_pers, ind=ind, origine=origine,
                               stock=stock, controles=controles(doc, finales), fichiers=fichiers(doc, annee),
                               niv_ep=NIV_EP, soeur=SOEUR[doc], active=annee == config.ANNEE_ACTIVE,
                               statuts_agent=STATUTS_AGENT), 200

    # ------------------------------------------------------------ PDF / Excel
    @app.route("/rapports/<doc>/pdf")
    @H.connexion_requise("recensement")
    def rapports_pdf(doc):
        doc = doc_ou_404(doc)
        annee = annee_demandee()
        vierge = request.args.get("vierge") == "1"
        _, _, _, finales, ind, _, _ = donnees_document(H, doc, annee)
        data, _ = generer_pdf(H, doc, annee, finales, vierge=vierge, annexe=request.args.get("annexe") == "1", ind=ind)
        H.journal("rapport_pdf", f"{doc} {annee}{' vierge' if vierge else ''}")
        nom = f"{doc}_{'vierge' if vierge else annee}.pdf".replace("-", "_")
        return H.pdf_reponse(data, nom)

    @app.route("/rapports/<doc>/excel")
    @H.connexion_requise("recensement")
    def rapports_excel(doc):
        doc = doc_ou_404(doc)
        annee = annee_demandee()
        auto, over, _, finales, _, origine, _ = donnees_document(H, doc, annee)
        orig = {k: ("saisie manuelle" if k in over else (f"repris de {origine[k]}" if k in origine else "GESCOL"))
                for k in finales}
        try:
            buf = generer_excel(doc, annee, finales, orig)
        except ImportError:
            flash("Le composant Excel (openpyxl) n'est pas installé : export impossible.", "danger")
            return redirect(url_for("rapports_formulaire", doc=doc, annee=annee))
        H.journal("rapport_excel", f"{doc} {annee}")
        return send_file(buf, mimetype=H.xlsx.MIME_XLSX, as_attachment=True,
                         download_name=f"{doc}_{annee}.xlsx".replace("-", "_"))

    # ------------------------------------------------------------ téléversement du rapport officiel
    @app.route("/rapports/<doc>/televerser", methods=["POST"])
    @H.connexion_requise("recensement")
    def rapports_televerser(doc):
        doc = doc_ou_404(doc)
        annee = annee_demandee()
        f = request.files.get("fichier")
        retour = redirect(url_for("rapports_formulaire", doc=doc, annee=annee) + "#televersement")
        if not f or not f.filename:
            flash("Choisissez le fichier du rapport (PDF, JPG ou PNG).", "danger")
            return retour
        ext = os.path.splitext(f.filename)[1].lower()
        data = f.read()
        if ext not in EXT_OK or not data.startswith(EXT_OK[ext]):
            flash("Format refusé : seuls les fichiers PDF, JPG et PNG sont acceptés.", "danger")
            return retour
        if len(data) > 15 * 1024 * 1024:
            flash("Fichier trop volumineux (15 Mo au plus).", "danger")
            return retour
        rep = os.path.join(dossier(), f"e{H.eco()}", annee)
        os.makedirs(rep, exist_ok=True)
        nom = f"{doc}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
        with open(os.path.join(rep, nom), "wb") as out:
            out.write(data)
        mime = {".pdf": "application/pdf", ".png": "image/png"}.get(ext, "image/jpeg")
        ex("""INSERT INTO rapports_fichiers (ecole_id, annee, doc, nom_origine, chemin, taille, mime, commentaire,
              televerse_le, televerse_par) VALUES (?,?,?,?,?,?,?,?,?,?)""",
           (H.eco(), annee, doc, os.path.basename(f.filename)[:120], os.path.join(f"e{H.eco()}", annee, nom), len(data),
            mime, (request.form.get("commentaire") or "").strip()[:200], H.maintenant(), g.user["id"]))
        H.journal("rapport_televerse", f"{doc} {annee} {f.filename}")
        flash("Rapport officiel téléversé et archivé pour l'année " + annee + ".", "success")
        return retour

    def fichier_ou_404(fid):
        r = q("SELECT * FROM rapports_fichiers WHERE id=? AND ecole_id=?", (fid, H.eco()), un=True)
        if not r:
            abort(404)
        return r

    @app.route("/rapports/fichier/<int:fid>")
    @H.connexion_requise("recensement")
    def rapports_fichier(fid):
        r = fichier_ou_404(fid)
        chemin = os.path.normpath(os.path.join(dossier(), r["chemin"]))
        if not chemin.startswith(os.path.normpath(dossier())) or not os.path.exists(chemin):
            abort(404)
        return send_file(chemin, mimetype=r["mime"], as_attachment=request.args.get("telecharger") == "1",
                         download_name=r["nom_origine"] or os.path.basename(chemin))

    @app.route("/rapports/fichier/<int:fid>/supprimer", methods=["POST"])
    @H.connexion_requise("recensement")
    def rapports_fichier_supprimer(fid):
        r = fichier_ou_404(fid)
        chemin = os.path.normpath(os.path.join(dossier(), r["chemin"]))
        if chemin.startswith(os.path.normpath(dossier())) and os.path.exists(chemin):
            os.remove(chemin)
        ex("DELETE FROM rapports_fichiers WHERE id=?", (fid,))
        H.journal("rapport_fichier_supprime", f"{r['doc']} {r['annee']} {r['nom_origine']}")
        flash("Fichier supprimé de l'archive.", "success")
        suivant = request.form.get("suivant", "")
        return redirect(suivant if suivant.startswith("/") and not suivant.startswith("//") else url_for("rapports_accueil"))

    # ------------------------------------------------------------ armoiries (image de l'en-tête des PDF)
    @app.route("/rapports/armoiries", methods=["POST"])
    @H.connexion_requise("recensement")
    def rapports_armoiries():
        chemin = os.path.join(dossier(), "armoiries.png")
        if request.form.get("supprimer"):
            if os.path.exists(chemin):
                os.remove(chemin)
            flash("Armoiries retirées : l'emblème générique sera utilisé.", "success")
            return redirect(url_for("rapports_accueil"))
        f = request.files.get("image")
        data = f.read() if f else b""
        if not data.startswith((b"\x89PNG", b"\xff\xd8")):
            flash("Choisissez une image PNG ou JPG.", "danger")
            return redirect(url_for("rapports_accueil"))
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(data))
            im.thumbnail((600, 600))
            im.save(chemin, "PNG")
        except Exception:  # noqa: BLE001
            flash("Image illisible.", "danger")
            return redirect(url_for("rapports_accueil"))
        H.journal("rapport_armoiries", "")
        flash("Armoiries enregistrées : elles figureront en tête des rapports.", "success")
        return redirect(url_for("rapports_accueil"))
