# -*- coding: utf-8 -*-
"""Transmission des données de l'école à sa Circonscription scolaire (CS) — GESCOL / GESCOL Public.

L'école produit un « paquet de transmission » (format défini dans jur_format.py) :
* identité de l'école (code unique, type EP/EM/EE, secteur, département, CS, zone…) ;
* rubriques : effectifs (classes, âges au 31/12, redoublants, titulaires), personnel (+ carrière),
  visites des CP/CCS, CEP (candidats, résultats officiels saisis ici, liste nominative), fiches de
  recensement, rapports de rentrée / fin d'année, patrimoine, cantine.
Le paquet est soit téléchargé (fichier « .gescol » à remettre à la CS sur clé USB, WhatsApp, e-mail…),
soit envoyé EN LIGNE à l'application de la CS (POST <adresse>/api/transmission, en-tête X-Gescol-Code).

Routes (pages actives seulement dans les éditions école : privee / publique) :
* /transmission                       transmission_accueil    aperçu, identité, CEP, réglages, historique
* /transmission/identite        POST  transmission_identite   code (admin), type, secteur
* /transmission/cep             POST  transmission_cep        résultats officiels du CEP (admis G / F)
* /transmission/fichier               transmission_fichier    téléchargement du fichier .gescol
* /transmission/reglages        POST  transmission_reglages   adresse Internet de la CS + code d'accès
* /transmission/envoyer         POST  transmission_envoyer    envoi en ligne à la CS

Droit : « donnees » (admin, directeur, secrétaire). Le code de l'école ne se modifie que par l'administrateur.
Ce module expose aussi `envoyer_en_ligne(adresse, code, octets)` réutilisé par a_transmission (CS → DDEMP).
"""
import gzip
import json
import re
import secrets
import socket
import ssl
import unicodedata
import urllib.error
import urllib.request
import zlib
from datetime import datetime

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

import config
import jur_calc
import jur_format
from calcul import cycle_du_niveau

SCHEMA = """
CREATE TABLE IF NOT EXISTS trans_envois (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ecole_id INTEGER NOT NULL,
    annee TEXT NOT NULL,
    mode TEXT NOT NULL,                 -- fichier | en_ligne
    destination TEXT,                   -- adresse de la CS (envoi en ligne)
    nom_fichier TEXT,
    empreinte TEXT,
    taille INTEGER,
    nb_eleves INTEGER, nb_personnel INTEGER,
    rubriques TEXT,                     -- JSON : liste des rubriques transmises
    statut TEXT NOT NULL,               -- ok | erreur
    message TEXT,
    envoye_le TEXT,
    envoye_par TEXT
);
CREATE INDEX IF NOT EXISTS ix_trans_envois ON trans_envois(ecole_id, annee);
"""

NOMS_RUBRIQUES = {"effectifs": "Effectifs des élèves", "personnel": "Personnel", "visites": "Visites de classe (CP / CCS)",
                  "cep": "CEP (candidats et résultats)", "recensement": "Fiches de recensement",
                  "rapports": "Rapports de rentrée / fin d'année", "patrimoine": "Patrimoine et infrastructures",
                  "cantine": "Cantine scolaire"}
RE_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,30}$")
TIMEOUT = 20
LIMITE_DECOMPRESSION = 60 * 1024 * 1024


# ======================================================================== outils communs (aussi pour a_transmission)
def norm_code(t):
    """Texte → lettres/chiffres majuscules sans accents (base des codes)."""
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().upper()
    return "".join(ch for ch in t if ch.isalnum())


def decompresser(octets, limite=LIMITE_DECOMPRESSION):
    """Décompresse un .gescol (gzip) sans risque de « bombe » : au-delà de `limite`, PaquetInvalide."""
    if octets[:2] != b"\x1f\x8b":
        return octets
    try:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = d.decompress(octets, limite)
        if d.unconsumed_tail:
            raise jur_format.PaquetInvalide("Fichier trop volumineux une fois décompressé.")
        if not d.eof:
            raise zlib.error("flux incomplet")
        return out
    except zlib.error as e:
        raise jur_format.PaquetInvalide("Fichier abîmé : il ne peut pas être décompressé "
                                        "(téléchargement interrompu ?). Demandez un nouvel envoi.") from e


def lire_paquet(octets):
    """Octets reçus (fichier ou POST) → paquet vérifié (PaquetInvalide avec message clair sinon)."""
    if not octets:
        raise jur_format.PaquetInvalide("Fichier vide.")
    if len(octets) > jur_format.TAILLE_MAX:
        raise jur_format.PaquetInvalide("Fichier trop volumineux (15 Mo au maximum).")
    return jur_format.lire(decompresser(octets))


def rubriques_du_paquet(paquet):
    """Noms des rubriques présentes dans un paquet (toutes écoles confondues), dans l'ordre officiel."""
    noms = set()
    for item in paquet.get("ecoles") or []:
        noms |= {k for k, v in (item.get("sections") or {}).items() if v not in (None, [], {})}
    return [n for n in jur_format.SECTIONS_ECOLE if n in noms]


def normaliser_adresse(adresse):
    a = (adresse or "").strip().rstrip("/")
    if not a:
        return ""
    if not re.match(r"^https?://", a, re.I):
        a = "https://" + a
    if a.lower().endswith("/api/transmission"):
        a = a[: -len("/api/transmission")]
    return a


def envoyer_en_ligne(adresse, code, octets):
    """POST du paquet (fichier .gescol = JSON compressé gzip) vers <adresse>/api/transmission.
    Renvoie (ok: bool, message: str, reponse: dict). Messages d'erreur en français, compréhensibles."""
    url = normaliser_adresse(adresse)
    if not url:
        return False, "Indiquez d'abord l'adresse Internet de l'application destinataire.", {}
    if not (code or "").strip():
        return False, "Indiquez d'abord le code d'accès fourni par le destinataire.", {}
    req = urllib.request.Request(url + "/api/transmission", data=octets, method="POST", headers={
        "Content-Type": "application/gzip", "X-Gescol-Code": code.strip(),
        "User-Agent": f"GESCOL/{config.VERSION}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as r:
            corps = r.read(1_000_000)
            try:
                rep = json.loads(corps.decode("utf-8"))
            except ValueError:
                return False, ("L'adresse répond, mais ce n'est pas une application GESCOL de circonscription "
                               "ou de DDEMP. Vérifiez l'adresse."), {}
            if not rep.get("ok"):
                return False, rep.get("message") or "Envoi refusé par le destinataire.", rep
            return True, rep.get("message") or "Données reçues.", rep
    except urllib.error.HTTPError as e:
        try:
            rep = json.loads(e.read(100_000).decode("utf-8"))
        except Exception:  # noqa: BLE001
            rep = {}
        msg = rep.get("message")
        if e.code in (401, 403):
            return False, "Code d'accès refusé : " + (msg or "vérifiez le code fourni par le destinataire."), rep
        if e.code == 404:
            return False, ("Adresse incorrecte : aucune application GESCOL de circonscription ou de DDEMP "
                           "ne répond à cette adresse."), rep
        if e.code == 413:
            return False, "Les données sont trop volumineuses pour un envoi en ligne : utilisez le fichier.", rep
        if e.code == 429:
            return False, msg or "Trop d'essais refusés : réessayez dans une heure.", rep
        if e.code in (400, 409, 422):
            return False, "Données refusées : " + (msg or "fichier invalide."), rep
        return False, f"Le serveur destinataire a rencontré une erreur (code {e.code}). Réessayez plus tard.", rep
    except urllib.error.URLError as e:
        r = e.reason
        if isinstance(r, socket.timeout) or "timed out" in str(r):
            return False, ("Délai dépassé (20 s) : la connexion Internet est trop lente ou le serveur ne répond pas. "
                           "Réessayez plus tard ou envoyez le fichier."), {}
        if isinstance(r, ssl.SSLError):
            return False, "Connexion sécurisée impossible avec cette adresse (certificat invalide).", {}
        if isinstance(r, socket.gaierror):
            return False, ("Pas de connexion Internet, ou adresse introuvable. Vérifiez votre connexion "
                           "et l'adresse saisie."), {}
        if isinstance(r, ConnectionRefusedError):
            return False, "Le serveur destinataire est hors ligne (connexion refusée). Réessayez plus tard.", {}
        return False, f"Envoi impossible ({r}). Vérifiez la connexion Internet et l'adresse.", {}
    except (socket.timeout, TimeoutError):
        return False, ("Délai dépassé (20 s) : la connexion Internet est trop lente ou le serveur ne répond pas. "
                       "Réessayez plus tard ou envoyez le fichier."), {}
    except (ValueError, OSError) as e:
        return False, f"Envoi impossible : {e}", {}


def json_propre(obj):
    """Copie strictement JSON (dates, tuples, Row… convertis) : l'empreinte du paquet reste stable."""
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


# ======================================================================== module Flask
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)
    H.ajouter_colonne("ecoles", "code_ecole", "TEXT")
    H.schema("CREATE UNIQUE INDEX IF NOT EXISTS ux_ecoles_code_ecole ON ecoles(code_ecole);")

    def table_existe(nom):
        return bool(q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nom,), un=True))

    def colonnes(table):
        return {r[1] for r in H.get_db().execute(f"PRAGMA table_info({table})")}

    def ecole_courante():
        return q("SELECT * FROM ecoles WHERE id=?", (H.eco(),), un=True)

    def actif():
        if config.juridiction():
            abort(404)

    def cle(nom, annee=None):
        return f"e{H.eco()}:transmission:{nom}" + (f":{annee}" if annee else "")

    def reglages():
        r = H.doc_lire(cle("reglages"), None)
        return r if isinstance(r, dict) else {}

    # ------------------------------------------------------------------ identité
    def generer_code(e):
        """Code unique « <CS>-<6 caractères> », créé une seule fois (dès que la CS est renseignée)."""
        if e["code_ecole"] or not (e["cs"] or "").strip():
            return e["code_ecole"]
        base = norm_code(e["cs"])[:6] or "ECOLE"
        for _ in range(20):
            code = f"{base}-{secrets.token_hex(3).upper()}"
            if not q("SELECT 1 FROM ecoles WHERE code_ecole=?", (code,), un=True):
                ex("UPDATE ecoles SET code_ecole=? WHERE id=? AND (code_ecole IS NULL OR code_ecole='')", (code, e["id"]))
                H.journal("transmission_code", code)
                return code
        return None

    def classes_ecole():
        """Classes de l'école courante (avec cycle), hors secondaire séparé ensuite."""
        out = []
        for c in H.classes_autorisees():
            d = dict(c)
            d["cycle"] = cycle_du_niveau(d.get("niveau") or "")
            out.append(d)
        return out

    def type_deduit(classes):
        cyc = {c["cycle"] for c in classes}
        if "primaire" in cyc:
            return "EP"
        if "maternelle" in cyc:
            return "EM"
        return "EP"

    def identite(e, classes, r=None):
        r = r if r is not None else reglages()
        typ = r.get("type") if r.get("type") in jur_format.TYPES_ECOLE else type_deduit(classes)
        sect = r.get("secteur") if r.get("secteur") in jur_format.SECTEURS else \
            ("public" if config.publique() else "prive")
        ident = {
            "code": e["code_ecole"] or "", "nom": e["nom"] or "", "type": typ, "secteur": sect,
            "departement": e["departement"] or "", "cs": e["cs"] or "", "zone": e["zone"] or "",
            "commune": e["commune"] or "", "arrondissement": "", "localite": e["ville"] or "",
            "adresse": e["adresse"] or "", "telephone": e["telephone"] or "", "email": e["email"] or "",
            "directeur_titre": e["directeur_titre"] or "Directeur", "directeur_nom": e["directeur_nom"] or "",
            "directeur_tel": e["directeur_tel"] or "", "annee_creation": ""}
        return ident

    def controles(ident):
        """Erreurs bloquantes (liste de messages)."""
        err = []
        if not ident["departement"]:
            err.append("Le département (DDEMP) de l'école n'est pas renseigné.")
        if not ident["cs"]:
            err.append("La circonscription scolaire (CS) de l'école n'est pas renseignée.")
        if not ident["code"]:
            err.append("Le code de l'école n'est pas encore attribué (il est créé dès que la CS est renseignée).")
        return err

    # ------------------------------------------------------------------ rubriques
    def eleves_inscrits(classes):
        ids = [c["id"] for c in classes]
        if not ids:
            return []
        return q("SELECT * FROM eleves WHERE statut='inscrit' AND classe_id IN (" + ",".join("?" * len(ids)) + ") "
                 "ORDER BY nom, prenoms", ids)

    def personnel_lignes():
        """Personnel actif de l'école (+ fiche de carrière si le module carrière est présent)."""
        if table_existe("personnel_carriere"):
            sql = ("SELECT p.*, c.* FROM personnel p LEFT JOIN personnel_carriere c ON c.personnel_id=p.id "
                   "WHERE p.ecole_id=? AND p.actif=1 ORDER BY p.nom, p.prenoms")
        else:
            sql = "SELECT p.* FROM personnel p WHERE p.ecole_id=? AND p.actif=1 ORDER BY p.nom, p.prenoms"
        return [dict(r) for r in q(sql, (H.eco(),))]

    def role_de(fonction):
        f = norm_code(fonction).lower()
        if "adjoint" in f:
            return "adjoint"
        if "direct" in f:
            return "directeur"
        if any(m in f for m in ("enseign", "institut", "educat", "maitre", "maitresse", "professeur", "animat")):
            return "enseignant"
        if any(m in f for m in ("secret", "compta", "econom", "caiss", "administr")):
            return "administratif"
        return "soutien"

    def oui(v):
        return str(v or "").strip().lower() in ("oui", "1", "true", "o", "yes")

    def section_effectifs(classes, eleves, a0):
        prim = [c for c in classes if c["cycle"] in ("primaire", "maternelle")]
        if not prim:
            return None, {}
        ref = a0 + 1                     # âge au 31/12 de la 2e année scolaire
        par_cl = {c["id"]: {"g": 0, "f": 0, "rg": 0, "rf": 0} for c in prim}
        ages, inconnus, nouveaux_ci = {}, 0, [0, 0]
        niv = {c["id"]: c["niveau"] for c in prim}
        for e in eleves:
            if e["classe_id"] not in par_cl:
                continue
            fille = (e["sexe"] or "").upper() == "F"
            k = par_cl[e["classe_id"]]
            k["f" if fille else "g"] += 1
            red = bool(e["redoublant"]) if "redoublant" in e.keys() else False
            if red:
                k["rf" if fille else "rg"] += 1
            n = niv[e["classe_id"]]
            if n == "CI" and not red:
                nouveaux_ci[1 if fille else 0] += 1
            dn = (e["date_naissance"] or "")[:4]
            if dn.isdigit():
                d = ages.setdefault(n, {}).setdefault(str(ref - int(dn)), [0, 0])
                d[1 if fille else 0] += 1
            else:
                inconnus += 1
        sexes = {}
        for p in personnel_lignes():
            sexes[norm_code(f"{p.get('nom') or ''}{p.get('prenoms') or ''}")] = (p.get("sexe") or "").upper()[:1]
        lst = []
        for c in prim:
            k = par_cl[c["id"]]
            tit = (c.get("titulaire_nom") or "").strip()
            cle_t = norm_code(tit)
            sexe = sexes.get(cle_t, "")
            if not sexe and tit:
                tt = (c.get("titulaire_titre") or "").lower()
                sexe = "F" if tt.startswith("la ") or "maîtresse" in tt else ("M" if tt.startswith("le ") else "")
            lst.append({"nom": c["nom"], "niveau": c["niveau"], "garcons": k["g"], "filles": k["f"],
                        "redoublants_g": k["rg"], "redoublants_f": k["rf"], "titulaire_nom": tit,
                        "titulaire_sexe": sexe, "groupe": "simple"})
        sec = {"classes": lst, "ages": ages, "nouveaux_ci": nouveaux_ci}
        pat = patrimoine()
        if pat and isinstance(pat.get("salles_classe"), dict) and pat["salles_classe"].get("total"):
            sec["salles"] = pat["salles_classe"]["total"]
        return sec, {"ages_inconnus": inconnus}

    def section_personnel(classes, publique):
        titulaires = {}
        for c in classes:
            if c.get("titulaire_nom"):
                titulaires.setdefault(norm_code(c["titulaire_nom"]), c["nom"])
        out = []
        for p in personnel_lignes():
            nom_c = f"{p.get('nom') or ''} {p.get('prenoms') or ''}".strip()
            cle_n = norm_code(nom_c)
            cat = (p.get("categorie") or "").strip().upper()
            if not publique:
                cat = "PRIVE"
            elif cat not in jur_format.CATEGORIES:
                cat = "AUTRE" if cat else ""
            role = role_de(p.get("fonction"))
            nv = {}
            if p.get("id") and getattr(H, "nb_visites", None):
                try:
                    nv = H.nb_visites(p["id"], config.ANNEE_ACTIVE) or {}
                except Exception:  # noqa: BLE001
                    nv = {}
            out.append({
                "nom": p.get("nom") or "", "prenoms": p.get("prenoms") or "", "sexe": (p.get("sexe") or "").upper()[:1],
                "nip": p.get("nip") or "", "matricule": p.get("matricule") or "",
                "date_naissance": p.get("date_naissance") or "", "telephone": p.get("telephone") or "",
                "email": p.get("email") or "", "fonction": p.get("fonction") or "", "role": role,
                "categorie": cat, "grade": p.get("grade") or "",
                "indice_paye": "" if p.get("indice_paye") is None else str(p.get("indice_paye")),
                "indice_reel": "" if p.get("indice_reel") is None else str(p.get("indice_reel")),
                "date_premiere_ps": p.get("date_prise_service") or "",
                "date_ps_departement": p.get("date_service_dep") or "",
                "date_ps_commune": p.get("date_service_commune") or "",
                "date_ps_ecole": p.get("date_service_ecole") or p.get("date_embauche") or "",
                "diplome_academique": p.get("diplome_academique") or "",
                "annee_diplome": "" if p.get("diplome_academique_annee") is None else str(p.get("diplome_academique_annee")),
                "ceap": oui(p.get("ceap")), "annee_ceap": "" if p.get("ceap_annee") is None else str(p.get("ceap_annee")),
                "cap": oui(p.get("cap")), "annee_cap": "" if p.get("cap_annee") is None else str(p.get("cap_annee")),
                "type_cap": "", "visite_aptitude": oui(p.get("visite_aptitude")),
                "note_aptitude": "" if p.get("visite_aptitude_note") is None else p.get("visite_aptitude_note"),
                "annee_aptitude": "", "departement_a_servir": p.get("departement_servir") or "",
                "nb_visites_cp": p.get("visites_cp") if p.get("visites_cp") is not None else nv.get("CP", ""),
                "nb_visites_ccs": p.get("visites_ccs") if p.get("visites_ccs") is not None else nv.get("CCS", ""),
                "participation_up": "" if p.get("participation_up") is None else p.get("participation_up"),
                "gestion_collegiale": p.get("gestion_collegiale") or "",
                "note_evaluation": "" if p.get("note_evaluation") is None else p.get("note_evaluation"),
                "classe": titulaires.get(cle_n, ""), "actif": True})
        return out

    def section_visites(annee):
        if not table_existe("visites"):
            return None, "Module « Visites » non installé."
        nips = {}
        if "nip" in colonnes("personnel"):
            nips = {r["id"]: r["nip"] or "" for r in q("SELECT id, nip FROM personnel WHERE ecole_id=?", (H.eco(),))}
        out = []
        for v in q("SELECT * FROM visites WHERE ecole_id=? AND annee=? ORDER BY date", (H.eco(), annee)):
            out.append({"date": v["date"], "type": v["visiteur_qualite"] if v["visiteur_qualite"] in ("CP", "CCS") else "directeur",
                        "visiteur": v["visiteur_nom"] or "", "enseignant": v["enseignant_nom"] or "",
                        "enseignant_nip": nips.get(v["personnel_id"], ""), "classe": v["classe_nom"] or "",
                        "discipline": v["matiere"] or "", "sequence": v["sequence"] or v["sa"] or "",
                        "note": v["note"], "effectif_g": v["eff_g"], "effectif_f": v["eff_f"],
                        "recommandations": v["recommandations"] or "", "nature": v["type"]})
        return (out or None), (None if out else f"Aucune visite de CP ou de CCS enregistrée pour {annee}.")

    def resultats_cep(annee):
        r = H.doc_lire(cle("cep", annee), None)
        return r if isinstance(r, dict) else {}

    def candidats_cep(classes, eleves):
        """Candidats au CEP : élèves inscrits ayant une fiche CEP, sinon tous les élèves de CM2 inscrits."""
        cm2 = {c["id"] for c in classes if c["niveau"] == "CM2"}
        fiches = set()
        if table_existe("cep_fiches"):
            ids = [e["id"] for e in eleves]
            if ids:
                fiches = {r["eleve_id"] for r in q("SELECT eleve_id FROM cep_fiches WHERE eleve_id IN (" +
                                                    ",".join("?" * len(ids)) + ")", ids)}
        if fiches:
            return [e for e in eleves if e["id"] in fiches], "fiches CEP"
        return [e for e in eleves if e["classe_id"] in cm2], "élèves de CM2"

    def section_cep(classes, eleves, annee):
        if not any(c["niveau"] == "CM2" for c in classes):
            return None, "Pas de classe de CM2 : pas de candidats au CEP."
        cand, origine = candidats_cep(classes, eleves)
        cm1 = {c["id"] for c in classes if c["niveau"] == "CM1"}
        cm2 = {c["id"] for c in classes if c["niveau"] == "CM2"}
        f_ = lambda e: (e["sexe"] or "").upper() == "F"  # noqa: E731
        res = resultats_cep(annee)
        sec = {"session": str(int(annee[:4]) + 1),
               "candidats_g": sum(1 for e in cand if not f_(e)), "candidats_f": sum(1 for e in cand if f_(e)),
               "admis_g": res.get("admis_g"), "admis_f": res.get("admis_f"),
               "cm1_g": sum(1 for e in eleves if e["classe_id"] in cm1 and not f_(e)),
               "cm1_f": sum(1 for e in eleves if e["classe_id"] in cm1 and f_(e)),
               "cm2_g": sum(1 for e in eleves if e["classe_id"] in cm2 and not f_(e)),
               "cm2_f": sum(1 for e in eleves if e["classe_id"] in cm2 and f_(e)),
               "liste": [{"nom": e["nom"] or "", "prenoms": e["prenoms"] or "", "sexe": (e["sexe"] or "").upper(),
                          "date_naissance": e["date_naissance"] or "", "lieu_naissance": e["lieu_naissance"] or "",
                          "numero_table": (e["numero_table"] if "numero_table" in e.keys() else "") or "",
                          "admis": None} for e in cand]}
        note = f"{len(cand)} candidat(s) ({origine})."
        if sec["admis_g"] is None and sec["admis_f"] is None:
            note += " Résultats officiels non saisis (formulaire ci-dessous)."
        return sec, note

    def valeurs_doc(fonction, args, cle_doc):
        """Valeurs d'une fiche : fonction partagée si elle existe (valeurs calculées + saisies), sinon document stocké."""
        f = getattr(H, fonction, None)
        if callable(f):
            try:
                v = f(*args)
                if isinstance(v, dict) and isinstance(v.get("valeurs"), dict):
                    v = v["valeurs"]
                if isinstance(v, dict) and v:
                    return v
            except Exception:  # noqa: BLE001  (module en cours d'évolution : jamais de plantage)
                pass
        d = H.doc_lire(cle_doc, None)
        if isinstance(d, dict):
            v = dict(d.get("instantane") or {}) if isinstance(d.get("instantane"), dict) else {}
            v.update({k: x for k, x in (d.get("valeurs") or {}).items() if x not in (None, "")}
                     if isinstance(d.get("valeurs"), dict) else {})
            return v or None
        return None

    def section_recensement(classes, annee):
        cyc = {c["cycle"] for c in classes}
        out = {}
        for typ, c in (("primaire", "primaire"), ("maternelle", "maternelle")):
            if c not in cyc:
                continue
            v = valeurs_doc("recensement_valeurs", (typ, annee), f"e{H.eco()}:recensement:{typ}:{annee}")
            if v:
                out[typ] = {"annee": annee, "valeurs": v}
        return (out or None), (None if out else "Fiche de recensement non remplie pour cette année (menu Recensement).")

    def section_rapports(classes, annee):
        cyc = {c["cycle"] for c in classes}
        docs = (["rentree-ep", "fin-ep"] if "primaire" in cyc else []) + (["rentree-em", "fin-em"] if "maternelle" in cyc else [])
        out = {}
        for d in docs:
            v = valeurs_doc("rapports_valeurs", (d, annee), f"e{H.eco()}:rapports:{d}:{annee}")
            if v:
                out[d] = {"annee": annee, "valeurs": v}
        return (out or None), (None if out else "Aucun rapport de rentrée ou de fin d'année enregistré (menu Rapports).")

    def patrimoine():
        f = getattr(H, "patrimoine_synthese", None)
        if not callable(f):
            return None
        try:
            r = f(H.eco())
            return r if isinstance(r, dict) else None
        except Exception:  # noqa: BLE001
            return None

    def section_cantine(classes):
        if not table_existe("cantine_paiements"):
            return None, "Module « Cantine » non installé."
        ids = [c["id"] for c in classes]
        if not ids:
            return None, "Aucune classe."
        marque = ",".join("?" * len(ids))
        cfg = q(f"SELECT COUNT(*) n FROM cantine_config WHERE classe_id IN ({marque}) AND COALESCE(montant_jour,0)>0",
                ids, un=True)["n"] if table_existe("cantine_config") else 0
        d1, d2 = H.bornes_annee()
        r = q(f"""SELECT COUNT(DISTINCT p.eleve_id) n, COALESCE(SUM(p.montant),0) m FROM cantine_paiements p
                  JOIN eleves e ON e.id=p.eleve_id WHERE e.classe_id IN ({marque}) AND p.date BETWEEN ? AND ?""",
              ids + [d1, d2], un=True)
        if not cfg and not r["n"]:
            return None, "Cantine non configurée et aucun repas enregistré cette année."
        return {"existe": True, "beneficiaires": r["n"] or 0, "montant_annee": int(r["m"] or 0)}, None

    def construire(annee=None):
        """Paquet de l'école courante + aperçu (dict) pour l'écran."""
        annee = annee or config.ANNEE_ACTIVE
        a0 = int(annee[:4])
        e = ecole_courante()
        generer_code(e)
        e = ecole_courante()
        classes = classes_ecole()
        secondaire = [c for c in classes if c["cycle"] == "secondaire"]
        utiles = [c for c in classes if c["cycle"] in ("primaire", "maternelle")]
        r = reglages()
        ident = identite(e, classes, r)
        eleves = eleves_inscrits(utiles)
        secs, notes = {}, {}
        eff, info_eff = section_effectifs(utiles, eleves, a0)
        if eff:
            secs["effectifs"] = eff
        else:
            notes["effectifs"] = "Aucune classe de maternelle ou du primaire dans cette école."
        pers = section_personnel(utiles, config.publique() or ident["secteur"] == "public")
        if pers:
            secs["personnel"] = pers
        else:
            notes["personnel"] = "Aucun membre du personnel actif (menu Personnel)."
        for nom, (val, note) in (("visites", section_visites(annee)), ("cep", section_cep(utiles, eleves, annee)),
                                 ("recensement", section_recensement(utiles, annee)),
                                 ("rapports", section_rapports(utiles, annee)), ("cantine", section_cantine(utiles))):
            if val:
                secs[nom] = val
            if note:
                notes[nom] = note
        pat = patrimoine()
        if pat:
            secs["patrimoine"] = pat
        else:
            notes["patrimoine"] = "Module « Patrimoine » non disponible."
        # renseignements complémentaires de la fiche de recensement (année de création, arrondissement…)
        rec = (secs.get("recensement") or {})
        for typ in ("primaire", "maternelle"):
            v = (rec.get(typ) or {}).get("valeurs") or {}
            for k_id, k_rec in (("annee_creation", "annee_creation"), ("arrondissement", "arrondissement"),
                                ("localite", "village")):
                if not ident[k_id] and v.get(k_rec):
                    ident[k_id] = str(v[k_rec])[:80]
        p = jur_format.nouveau("ecole", ident["code"], ident["nom"], annee, ident["departement"], ident["cs"],
                               config.EDITION, f"GESCOL {config.VERSION}")
        p["genere_le"] = H.maintenant()
        p["ecoles"] = [{"ecole": ident, "sections": secs}]
        p = jur_format.sceller(json_propre(p))
        ens = jur_calc.enseignants(secs.get("personnel"))
        ef = jur_calc.effectifs(secs.get("effectifs"))
        apercu = {"ident": ident, "erreurs": controles(ident), "eleves": ef["t"], "g": ef["g"], "f": ef["f"],
                  "classes": ef["classes"], "enseignants": ens["t"], "personnel": len(secs.get("personnel") or []),
                  "rubriques": [(k, NOMS_RUBRIQUES[k], k in secs, notes.get(k)) for k in jur_format.SECTIONS_ECOLE],
                  "presentes": [k for k in jur_format.SECTIONS_ECOLE if k in secs],
                  "secondaire": [c["nom"] for c in secondaire], "ages_inconnus": (info_eff or {}).get("ages_inconnus", 0),
                  "type_deduit": type_deduit(classes), "cep": secs.get("cep"), "annee": annee,
                  "nom_fichier": f"transmission_{ident['code'] or 'SANS-CODE'}_{annee}.gescol"}
        return p, apercu

    def historiser(apercu, p, mode, statut, message, octets, destination=""):
        ex("INSERT INTO trans_envois (ecole_id, annee, mode, destination, nom_fichier, empreinte, taille, nb_eleves, "
           "nb_personnel, rubriques, statut, message, envoye_le, envoye_par) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (H.eco(), apercu["annee"], mode, destination, apercu["nom_fichier"], p.get("empreinte"), len(octets),
            apercu["eleves"], apercu["personnel"], json.dumps(apercu["presentes"]), statut, message[:500],
            H.maintenant(), g.user["nom"] if g.get("user") else ""))

    # ------------------------------------------------------------------ pages
    @app.route("/transmission")
    @H.connexion_requise("donnees")
    def transmission_accueil():
        actif()
        p, ap = construire()
        r = reglages()
        hist = q("SELECT * FROM trans_envois WHERE ecole_id=? ORDER BY id DESC LIMIT 30", (H.eco(),))
        hist = [dict(h, rub=json.loads(h["rubriques"] or "[]")) for h in hist]
        return render_template("transmission_accueil.html", ap=ap, r=r, hist=hist, e=ecole_courante(),
                               types=jur_format.TYPES_ECOLE, secteurs=jur_format.SECTEURS,
                               noms=NOMS_RUBRIQUES, cep=ap["cep"], res_cep=resultats_cep(ap["annee"]),
                               admin=H.peut("parametres"), taille=len(jur_format.vers_fichier(p)))

    @app.route("/transmission/identite", methods=["POST"])
    @H.connexion_requise("donnees")
    def transmission_identite():
        actif()
        f = request.form
        r = reglages()
        typ, sect = f.get("type", ""), f.get("secteur", "")
        r["type"] = typ if typ in jur_format.TYPES_ECOLE else ""
        r["secteur"] = sect if sect in jur_format.SECTEURS else ""
        H.doc_ecrire(cle("reglages"), r)
        code = f.get("code", "").strip().upper()
        e = ecole_courante()
        if code and code != (e["code_ecole"] or ""):
            if not H.peut("parametres"):
                flash("Seul l'administrateur peut modifier le code de l'école.", "danger")
                return redirect(url_for("transmission_accueil"))
            if not RE_CODE.match(code):
                flash("Code invalide : 4 à 31 caractères, lettres majuscules, chiffres et tirets (ex. POBE-3F9A2C).", "danger")
                return redirect(url_for("transmission_accueil"))
            if q("SELECT 1 FROM ecoles WHERE code_ecole=? AND id<>?", (code, e["id"]), un=True):
                flash("Ce code est déjà utilisé par une autre école de cette installation.", "danger")
                return redirect(url_for("transmission_accueil"))
            ex("UPDATE ecoles SET code_ecole=? WHERE id=?", (code, e["id"]))
            H.journal("transmission_code", f"{e['code_ecole'] or ''} → {code}")
            flash("Code de l'école modifié. Prévenez la circonscription : elle reconnaît l'école par ce code.", "warning")
        flash("Identité de transmission enregistrée.", "success")
        return redirect(url_for("transmission_accueil"))

    @app.route("/transmission/cep", methods=["POST"])
    @H.connexion_requise("donnees")
    def transmission_cep():
        actif()
        annee = config.ANNEE_ACTIVE
        _p, ap = construire(annee)
        cep = ap["cep"]
        if not cep:
            flash("Pas de candidats au CEP dans cette école.", "warning")
            return redirect(url_for("transmission_accueil"))
        vals, err = {}, []
        for k, lib, maxi in (("admis_g", "garçons", cep["candidats_g"]), ("admis_f", "filles", cep["candidats_f"])):
            v = request.form.get(k, "").strip()
            if v == "":
                vals[k] = None
                continue
            if not v.isdigit():
                err.append(f"Nombre d'admis ({lib}) invalide.")
            elif int(v) > maxi:
                err.append(f"Admis ({lib}) : {v} est supérieur au nombre de candidats ({maxi}).")
            else:
                vals[k] = int(v)
        if (vals.get("admis_g") is None) != (vals.get("admis_f") is None) and not err:
            err.append("Saisissez les admis garçons ET filles (0 si aucun), ou laissez les deux cases vides.")
        if err:
            for m in err:
                flash(m, "danger")
            return redirect(url_for("transmission_accueil") + "#cep")
        vals.update(session=cep["session"], maj=H.maintenant(), par=g.user["nom"])
        H.doc_ecrire(cle("cep", annee), vals)
        H.journal("transmission_cep", f"admis G={vals.get('admis_g')} F={vals.get('admis_f')}")
        flash("Résultats officiels du CEP enregistrés." if vals.get("admis_g") is not None
              else "Résultats du CEP effacés (résultats inconnus).", "success")
        return redirect(url_for("transmission_accueil") + "#cep")

    @app.route("/transmission/fichier")
    @H.connexion_requise("donnees")
    def transmission_fichier():
        actif()
        p, ap = construire()
        if ap["erreurs"]:
            for m in ap["erreurs"]:
                flash(m, "danger")
            return redirect(url_for("transmission_accueil"))
        octets = jur_format.vers_fichier(p)
        historiser(ap, p, "fichier", "ok", "Fichier téléchargé.", octets)
        H.journal("transmission_fichier", ap["nom_fichier"])
        return Response(octets, mimetype="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{ap["nom_fichier"]}"'})

    @app.route("/transmission/reglages", methods=["POST"])
    @H.connexion_requise("donnees")
    def transmission_reglages():
        actif()
        r = reglages()
        adr = normaliser_adresse(request.form.get("adresse", ""))
        if adr and not re.match(r"^https?://[\w.\-]+(:\d{1,5})?(/[\w.\-/~%]*)?$", adr):
            flash("Adresse Internet invalide (exemple : https://cs-pobe.gescol.bj).", "danger")
            return redirect(url_for("transmission_accueil") + "#en-ligne")
        r["adresse"] = adr
        code = request.form.get("code_acces", "").strip()
        if code:
            r["code_acces"] = code[:80]
        if request.form.get("effacer_code"):
            r["code_acces"] = ""
        H.doc_ecrire(cle("reglages"), r)
        H.journal("transmission_reglages", adr)
        flash("Réglages de l'envoi en ligne enregistrés.", "success")
        return redirect(url_for("transmission_accueil") + "#en-ligne")

    @app.route("/transmission/envoyer", methods=["POST"])
    @H.connexion_requise("donnees")
    def transmission_envoyer():
        actif()
        p, ap = construire()
        if ap["erreurs"]:
            for m in ap["erreurs"]:
                flash(m, "danger")
            return redirect(url_for("transmission_accueil"))
        r = reglages()
        octets = jur_format.vers_fichier(p)
        ok, msg, rep = envoyer_en_ligne(r.get("adresse"), r.get("code_acces"), octets)
        historiser(ap, p, "en_ligne", "ok" if ok else "erreur", msg, octets, r.get("adresse", ""))
        H.journal("transmission_en_ligne", ("OK " if ok else "ÉCHEC ") + msg[:200])
        flash(("Envoi réussi : " if ok else "Échec de l'envoi : ") + msg, "success" if ok else "danger")
        return redirect(url_for("transmission_accueil") + "#en-ligne")

    # utilisable par d'autres modules / tests
    H.transmission_paquet = lambda annee=None: construire(annee)[0]
