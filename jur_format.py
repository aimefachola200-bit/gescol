# -*- coding: utf-8 -*-
"""Format du « paquet de transmission » SCOLARIS : école → Circonscription scolaire (CS) → DDEMP.

Un paquet est un document JSON (fichier « .scolaris », compressé gzip) ou le corps d'un POST en ligne.
Il est produit par l'école (module m_transmission) ou par la CS (a_transmission, à destination de la DDEMP)
et lu par m_juridiction.importer_paquet.

    paquet = {
      "format": "scolaris-transmission", "version": 1,
      "emetteur": {"type": "ecole" | "cs", "code": str, "nom": str, "departement": str, "cs": str,
                   "logiciel": "SCOLARIS 1.4.0", "edition": "privee" | "publique" | "cs"},
      "annee": "2026-2027", "genere_le": "2026-10-04 10:00:00",
      "ecoles": [ {"ecole": IDENTITE_ECOLE, "sections": {nom_section: donnees, ...}}, ... ],
      "cs": None | {"identite": IDENTITE_CS, "sections": {"agents": [...], "visites": [...], "cep": {...}, ...}},
      "empreinte": sha256 (voir empreinte())
    }

Une école envoie « ecoles » = [elle-même] et « cs » = None. Une CS envoie toutes ses écoles + sa partie « cs ».

IDENTITE_ECOLE (clés ; valeurs texte, "" si inconnu) :
    code, nom, type ("EP" primaire | "EM" maternelle | "EE" espace enfance), secteur ("public" | "prive"),
    departement, cs, zone, commune, arrondissement, localite, adresse, telephone, email,
    directeur_titre, directeur_nom, directeur_tel, annee_creation

IDENTITE_CS : departement, nom, ccs_titre, ccs_nom, telephone, email, adresse

SECTIONS DE L'ÉCOLE (toutes facultatives) :
  "effectifs": {
      "classes": [{"nom", "niveau" (CI…CM2, Maternelle 1/2…), "garcons": int, "filles": int,
                   "redoublants_g": int, "redoublants_f": int, "titulaire_nom", "titulaire_sexe" ("M"/"F"/""),
                   "groupe": "simple" | "jumele" | "multigrade"}],
      "ages": {niveau: {"<age>": [g, f]}},          # âges au 31/12 de la 2e année scolaire
      "nouveaux_ci": [g, f], "handicapes": [g, f], "salles": int }
  "personnel": [PERSONNE, ...]   (enseignants, directeur, adjoints, personnel de soutien de l'école)
  "visites":   [{"date", "type": "CP" | "CCS" | "directeur", "visiteur", "enseignant", "enseignant_nip",
                 "classe", "discipline", "sequence", "note": float|None, "effectif_g", "effectif_f",
                 "recommandations"}]
  "cep": {"session": "2027", "candidats_g", "candidats_f", "admis_g", "admis_f" (None = résultats inconnus),
          "cm1_g", "cm1_f", "cm2_g", "cm2_f",
          "liste": [{"nom", "prenoms", "sexe", "date_naissance", "lieu_naissance", "numero_table",
                     "admis": None|bool}]}
  "recensement": {"primaire": {"annee", "valeurs": {cle_champ: valeur}}, "maternelle": {...}}
  "rapports":    {"rentree-ep" | "fin-ep" | "rentree-em" | "fin-em": {"annee", "valeurs": {...}}}
  "patrimoine":  dict (H.patrimoine_synthese)
  "cantine":     {"existe": bool, "beneficiaires": int, "montant_annee": int}
  "pilotage":    {"evaluations": [{"type", "numero", "libelle", "niveau", "classes", "composes_g", "composes_f",
                                   "reussis_g", "reussis_f"}], "abandons": [g, f], "transferts": [g, f],
                  "sport": {"licences_g", "licences_f", "aptes", "competitions", "matchs", "matchs_joues"}, "sante": {...}}

PERSONNE (clés ; "" si inconnu) :
    nom, prenoms, sexe ("M"/"F"), nip, matricule, date_naissance (ISO ou "AAAA"), telephone, email,
    fonction (libellé libre), role ("directeur" | "adjoint" | "enseignant" | "soutien" | "administratif" |
    "cp" | "ccs" | "chef_service"), categorie ("FE" | "ACDPE" | "ACDPCTD" | "PRIVE" | "AUTRE"),
    grade (A1-1 … C3-15), indice_paye, indice_reel, date_premiere_ps, date_ps_departement, date_ps_commune,
    date_ps_ecole, diplome_academique, annee_diplome, ceap (bool), annee_ceap, cap (bool), annee_cap,
    type_cap ("EP" | "EM" | ""), visite_aptitude (bool), note_aptitude, annee_aptitude,
    departement_a_servir, nb_visites_cp, nb_visites_ccs, participation_up, gestion_collegiale,
    note_evaluation, classe, actif (bool)
"""
import gzip
import hashlib
import json

FORMAT = "scolaris-transmission"
FORMATS_ACCEPTES = (FORMAT, "gescol-transmission")  # LEGACY-GESCOL : anciens paquets .gescol
VERSION = 1
TYPES_ECOLE = {"EP": "École primaire", "EM": "École maternelle", "EE": "Espace enfance",
               "CEG": "Collège d'enseignement général", "LYC": "Lycée", "ETP": "Établissement technique et professionnel"}
SECTEURS = {"public": "Public", "prive": "Privé"}
SECTIONS_ECOLE = ("effectifs", "personnel", "visites", "cep", "recensement", "rapports", "patrimoine", "cantine",
                  "pilotage", "secondaire")   # v2.4.7 : section du secondaire (effectifs, examens…)   # v1.25 : évaluations (réussite G / F), abandons, transferts, sport, santé (m_pilotage)
SECTIONS_CS = ("agents", "visites", "cep", "structure", "frais_releves", "cp_bilans")  # v1.7 : bilans des CP
CATEGORIES = {"FE": "FE (fonctionnaire de l'État)", "ACDPE": "ACDPE", "ACDPCTD": "ACDPCTD (AME)",
              "PRIVE": "Enseignant du privé", "AUTRE": "Autre"}
ROLES_PERSONNE = {"directeur": "Directeur", "adjoint": "Adjoint", "enseignant": "Enseignant",
                  "soutien": "Personnel de soutien", "administratif": "Personnel administratif",
                  "cp": "Conseiller pédagogique", "ip": "Inspecteur pédagogique", "ccs": "Chef de circonscription", "chef_service": "Chef de service"}
CHAMPS_ECOLE = ("code", "nom", "type", "secteur", "departement", "cs", "zone", "commune", "arrondissement",
                "localite", "adresse", "telephone", "email", "directeur_titre", "directeur_nom", "directeur_tel",
                "annee_creation")
TAILLE_MAX = 15 * 1024 * 1024


class PaquetInvalide(ValueError):
    """Paquet illisible ou incohérent (message en français pour l'utilisateur)."""


def _canonique(paquet):
    p = {k: v for k, v in paquet.items() if k != "empreinte"}
    return json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def empreinte(paquet):
    """Empreinte SHA-256 du paquet (hors champ « empreinte ») : détecte un fichier abîmé ou retouché."""
    return hashlib.sha256(_canonique(paquet)).hexdigest()


def _sans_flottants_entiers(v):
    if isinstance(v, float) and v.is_integer() and abs(v) < 2 ** 53:
        return int(v)
    if isinstance(v, dict):
        return {k: _sans_flottants_entiers(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_sans_flottants_entiers(x) for x in v]
    return v


def sceller(paquet):
    # v2.3.1 : 12.0 -> 12 avant l'empreinte : le paquet joint à la synchronisation garde la même empreinte une fois signé
    # (la signature écrit les flottants entiers comme JavaScript, cf. sync_crypto.signer)
    for k in list(paquet):
        paquet[k] = _sans_flottants_entiers(paquet[k])
    paquet["format"], paquet["version"] = FORMAT, VERSION
    paquet["empreinte"] = empreinte(paquet)
    return paquet


def vers_fichier(paquet):
    """Octets du fichier .scolaris (JSON compressé)."""
    return gzip.compress(json.dumps(paquet, ensure_ascii=False, default=str).encode("utf-8"))


def lire(octets):
    """Fichier .scolaris (gzip) ou JSON brut → paquet vérifié. Lève PaquetInvalide."""
    if not octets:
        raise PaquetInvalide("Fichier vide.")
    if len(octets) > TAILLE_MAX * 4:
        raise PaquetInvalide("Fichier trop volumineux.")
    try:
        if octets[:2] == b"\x1f\x8b":
            octets = gzip.decompress(octets)
        paquet = json.loads(octets.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise PaquetInvalide("Ce fichier n'est pas un fichier de transmission SCOLARIS.") from e
    return verifier(paquet)


def verifier(paquet):
    if not isinstance(paquet, dict) or paquet.get("format") not in FORMATS_ACCEPTES:
        raise PaquetInvalide("Ce fichier n'est pas un fichier de transmission SCOLARIS.")
    if int(paquet.get("version") or 0) > VERSION:
        raise PaquetInvalide("Fichier produit par une version plus récente de SCOLARIS : mettez l'application à jour.")
    if paquet.get("empreinte") != empreinte(paquet):
        raise PaquetInvalide("Fichier abîmé ou modifié après sa création (empreinte incorrecte).")
    em = paquet.get("emetteur") or {}
    if em.get("type") not in ("ecole", "cs"):
        raise PaquetInvalide("Émetteur inconnu dans le fichier.")
    if not isinstance(paquet.get("ecoles"), list):
        raise PaquetInvalide("Liste des écoles absente du fichier.")
    for item in paquet["ecoles"]:
        e = (item or {}).get("ecole") or {}
        if not (e.get("code") or "").strip() or not (e.get("nom") or "").strip():
            raise PaquetInvalide("Une école du fichier n'a pas de code ou de nom.")
        if e.get("type") not in TYPES_ECOLE:
            raise PaquetInvalide(f"Type d'école inconnu pour « {e.get('nom')} » (attendu EP, EM, EE, CEG, LYC ou ETP).")
        if e.get("secteur") not in SECTEURS:
            raise PaquetInvalide(f"Secteur inconnu pour « {e.get('nom')} » (attendu public ou prive).")
    if not paquet.get("annee"):
        raise PaquetInvalide("Année scolaire absente du fichier.")
    return paquet


def nouveau(type_emetteur, code, nom, annee, departement="", cs="", edition="", logiciel="SCOLARIS"):
    """Squelette de paquet à remplir puis à sceller()."""
    return {"format": FORMAT, "version": VERSION,
            "emetteur": {"type": type_emetteur, "code": code, "nom": nom, "departement": departement, "cs": cs,
                         "logiciel": logiciel, "edition": edition},
            "annee": annee, "genere_le": "", "ecoles": [], "cs": None}
