# -*- coding: utf-8 -*-
"""Cœur des applications « GESCOL Circonscription » (CS) et « GESCOL DDEMP ».

Hiérarchie : DDEMP (département) → Circonscriptions scolaires (CS) → zones pédagogiques → écoles.
* La CS rassemble les écoles de sa juridiction : elle reçoit leurs paquets de transmission (fichier .gescol
  ou envoi en ligne), qui alimentent ses tableaux de bord, ses statistiques et ses fiches.
* La DDEMP rassemble les CS du département : elle reçoit les paquets des CS (toutes leurs écoles + leurs
  données propres : agents, visites des CP…).

Ce module fournit les tables communes, la configuration de la structure, le référentiel (CS, zones),
la liste des écoles (ajout, modification, import / export Excel) et les fonctions d'accès aux données
(H.jur_*) utilisées par les autres modules a_*.
"""
import json
import secrets

from flask import abort, flash, g, redirect, render_template, request, url_for

import config
import jur_format
import referentiel_benin as RB
from db import ex, q

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_structure (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    niveau TEXT NOT NULL,                 -- cs | ddemp
    departement TEXT, cs TEXT, nom TEXT, sigle TEXT, adresse TEXT, bp TEXT, telephone TEXT, email TEXT,
    ville TEXT, responsable_titre TEXT, responsable_nom TEXT, maj TEXT);
CREATE TABLE IF NOT EXISTS jur_cs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    departement TEXT NOT NULL, nom TEXT NOT NULL, numero INTEGER, arrondissements TEXT, nb_zones INTEGER,
    ccs_titre TEXT, ccs_nom TEXT, telephone TEXT, email TEXT, adresse TEXT, jeton TEXT,
    actif INTEGER DEFAULT 1, UNIQUE(departement, nom));
CREATE TABLE IF NOT EXISTS jur_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cs_id INTEGER NOT NULL, nom TEXT NOT NULL, ordre INTEGER DEFAULT 0, cp_nom TEXT, cp_telephone TEXT,
    UNIQUE(cs_id, nom));
CREATE TABLE IF NOT EXISTS jur_ecoles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE, nom TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'EP',      -- EP | EM | EE
    secteur TEXT NOT NULL DEFAULT 'public',
    cs_id INTEGER, zone_id INTEGER, commune TEXT, arrondissement TEXT, localite TEXT, adresse TEXT,
    telephone TEXT, email TEXT, directeur_titre TEXT, directeur_nom TEXT, directeur_tel TEXT,
    annee_creation TEXT, jeton TEXT, actif INTEGER DEFAULT 1, derniere_transmission TEXT, cree_le TEXT, maj TEXT);
CREATE TABLE IF NOT EXISTS jur_sections (
    ecole_id INTEGER NOT NULL, annee TEXT NOT NULL, section TEXT NOT NULL, donnees TEXT NOT NULL,
    source TEXT, maj TEXT, PRIMARY KEY (ecole_id, annee, section));
CREATE TABLE IF NOT EXISTS jur_cs_sections (
    cs_id INTEGER NOT NULL, annee TEXT NOT NULL, section TEXT NOT NULL, donnees TEXT NOT NULL,
    source TEXT, maj TEXT, PRIMARY KEY (cs_id, annee, section));
CREATE TABLE IF NOT EXISTS jur_paquets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emetteur_type TEXT, emetteur_code TEXT, emetteur_nom TEXT, ecole_id INTEGER, cs_id INTEGER,
    annee TEXT, mode TEXT, empreinte TEXT, taille INTEGER, resume TEXT, recu_le TEXT, recu_par TEXT);
CREATE TABLE IF NOT EXISTS jur_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    niveau TEXT NOT NULL, code TEXT NOT NULL, nom TEXT NOT NULL, sigle TEXT, attributions TEXT, ordre INTEGER DEFAULT 0,
    responsable_id INTEGER, cachet_sup TEXT, cachet_inf TEXT, cachet_centre TEXT, cachet_couleur TEXT,
    actif INTEGER DEFAULT 1, UNIQUE(niveau, code));
CREATE TABLE IF NOT EXISTS jur_agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cs_id INTEGER,                         -- NULL = agent de la structure elle-même
    service_code TEXT, poste TEXT, nom TEXT NOT NULL, prenoms TEXT, sexe TEXT, nip TEXT, matricule TEXT,
    telephone TEXT, email TEXT, donnees TEXT, user_id INTEGER, actif INTEGER DEFAULT 1, maj TEXT);
CREATE INDEX IF NOT EXISTS i_jur_ecoles_cs ON jur_ecoles(cs_id, zone_id);
"""

TYPES = jur_format.TYPES_ECOLE
SECTEURS = jur_format.SECTEURS


# ======================================================================== accès aux données
def norm(t):
    """Comparaison souple de noms (accents, casse, tirets)."""
    import unicodedata
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(t.replace("-", " ").replace("'", " ").split())


def structure():
    r = q("SELECT * FROM jur_structure WHERE id=1", un=True)
    return dict(r) if r else None


def niveau():
    return config.EDITION if config.juridiction() else None


def annee():
    return config.ANNEE_ACTIVE


def cs_liste(actif=True):
    """CS de la juridiction (une seule pour une CS ; toutes celles du département pour la DDEMP)."""
    return q("SELECT * FROM jur_cs" + (" WHERE actif=1" if actif else "") + " ORDER BY numero, nom")


def cs_par_id(cid):
    return q("SELECT * FROM jur_cs WHERE id=?", (cid,), un=True)


def cs_courante():
    """Pour l'application CS : la ligne jur_cs de la circonscription elle-même."""
    s = structure()
    if not s or s["niveau"] != "cs":
        return None
    return q("SELECT * FROM jur_cs WHERE departement=? AND nom=?", (s["departement"], s["cs"]), un=True)


def zones(cs_id=None):
    if cs_id:
        return q("SELECT z.*, c.nom cs_nom FROM jur_zones z JOIN jur_cs c ON c.id=z.cs_id WHERE z.cs_id=? "
                 "ORDER BY z.ordre, z.nom", (cs_id,))
    return q("SELECT z.*, c.nom cs_nom FROM jur_zones z JOIN jur_cs c ON c.id=z.cs_id ORDER BY c.numero, c.nom, z.ordre, z.nom")


def ecoles(cs_id=None, zone_id=None, type_=None, secteur=None, actif=True, recherche=None):
    """Écoles de la juridiction (Row avec cs_nom, zone_nom)."""
    sql = ("SELECT e.*, c.nom cs_nom, c.departement, z.nom zone_nom FROM jur_ecoles e "
           "LEFT JOIN jur_cs c ON c.id=e.cs_id LEFT JOIN jur_zones z ON z.id=e.zone_id WHERE 1=1")
    args = []
    if actif:
        sql += " AND e.actif=1"
    for col, v in (("e.cs_id", cs_id), ("e.zone_id", zone_id), ("e.type", type_), ("e.secteur", secteur)):
        if v:
            sql += f" AND {col}=?"
            args.append(v)
    if recherche:
        sql += " AND (e.nom LIKE ? OR e.code LIKE ? OR e.directeur_nom LIKE ? OR e.localite LIKE ?)"
        args += [f"%{recherche}%"] * 4
    return q(sql + " ORDER BY c.numero, c.nom, z.ordre, z.nom, e.type, e.nom", tuple(args))


def ecole(eid):
    return q("SELECT e.*, c.nom cs_nom, c.departement, z.nom zone_nom FROM jur_ecoles e LEFT JOIN jur_cs c ON c.id=e.cs_id "
             "LEFT JOIN jur_zones z ON z.id=e.zone_id WHERE e.id=?", (eid,), un=True)


def section(ecole_id, nom, annee_=None):
    r = q("SELECT donnees FROM jur_sections WHERE ecole_id=? AND annee=? AND section=?",
          (ecole_id, annee_ or annee(), nom), un=True)
    return json.loads(r["donnees"]) if r else None


def sections(nom, annee_=None, ecole_ids=None):
    """{ecole_id: données} pour une section et une année (écoles actives)."""
    rows = q("SELECT s.ecole_id, s.donnees FROM jur_sections s JOIN jur_ecoles e ON e.id=s.ecole_id AND e.actif=1 "
             "WHERE s.annee=? AND s.section=?", (annee_ or annee(), nom))
    out = {r["ecole_id"]: json.loads(r["donnees"]) for r in rows}
    if ecole_ids is not None:
        ids = set(ecole_ids)
        out = {k: v for k, v in out.items() if k in ids}
    return out


def ecrire_section(ecole_id, nom, donnees, annee_=None, source="saisie"):
    ex("INSERT INTO jur_sections (ecole_id, annee, section, donnees, source, maj) VALUES (?,?,?,?,?,datetime('now','localtime')) "
       "ON CONFLICT(ecole_id, annee, section) DO UPDATE SET donnees=excluded.donnees, source=excluded.source, maj=excluded.maj",
       (ecole_id, annee_ or annee(), nom, json.dumps(donnees, ensure_ascii=False, default=str), source))


def cs_section(cs_id, nom, annee_=None):
    r = q("SELECT donnees FROM jur_cs_sections WHERE cs_id=? AND annee=? AND section=?", (cs_id, annee_ or annee(), nom), un=True)
    return json.loads(r["donnees"]) if r else None


def ecrire_cs_section(cs_id, nom, donnees, annee_=None, source="saisie"):
    ex("INSERT INTO jur_cs_sections (cs_id, annee, section, donnees, source, maj) VALUES (?,?,?,?,?,datetime('now','localtime')) "
       "ON CONFLICT(cs_id, annee, section) DO UPDATE SET donnees=excluded.donnees, source=excluded.source, maj=excluded.maj",
       (cs_id, annee_ or annee(), nom, json.dumps(donnees, ensure_ascii=False, default=str), source))


def annees():
    """Années scolaires pour lesquelles des données existent (+ l'année active)."""
    a = {r["annee"] for r in q("SELECT DISTINCT annee FROM jur_sections")} | {annee()}
    return sorted(a, reverse=True)


def personnel(annee_=None, cs_id=None, zone_id=None, inclure_agents=True):
    """Tout le personnel de la juridiction : personnel des écoles (section « personnel » des paquets)
    + agents de la CS / DDEMP (table jur_agents). Chaque élément = dict PERSONNE + ecole_id, ecole_nom,
    ecole_type, secteur, cs_id, cs_nom, zone_nom, source ("ecole" | "agent"), agent_id."""
    lst = []
    ecs = {e["id"]: e for e in ecoles(cs_id=cs_id, zone_id=zone_id)}
    for eid, pers in sections("personnel", annee_).items():
        e = ecs.get(eid)
        if not e:
            continue
        for p in pers or []:
            d = dict(p)
            d.update(ecole_id=eid, ecole_nom=e["nom"], ecole_type=e["type"], secteur=e["secteur"], cs_id=e["cs_id"],
                     cs_nom=e["cs_nom"], zone_nom=e["zone_nom"], source="ecole", agent_id=None)
            lst.append(d)
    if inclure_agents and not zone_id:
        sql, args = "SELECT a.*, c.nom cs_nom FROM jur_agents a LEFT JOIN jur_cs c ON c.id=a.cs_id WHERE a.actif=1", []
        if cs_id:
            sql += " AND a.cs_id=?"
            args.append(cs_id)
        for a in q(sql, tuple(args)):
            d = json.loads(a["donnees"] or "{}")
            d.update(nom=a["nom"], prenoms=a["prenoms"] or "", sexe=a["sexe"] or "", nip=a["nip"] or "",
                     matricule=a["matricule"] or "", telephone=a["telephone"] or "", email=a["email"] or "",
                     service_code=a["service_code"] or "", poste=a["poste"] or "")
            d.setdefault("role", "administratif")
            d.update(ecole_id=None, ecole_nom="", ecole_type="", secteur="public", cs_id=a["cs_id"],
                     cs_nom=a["cs_nom"] or "", zone_nom="", source="agent", agent_id=a["id"])
            lst.append(d)
    return lst


# ======================================================================== import des paquets
def _trouver_cs(departement, nom_cs, creer=True):
    s = structure() or {}
    dep = departement or s.get("departement") or ""
    n = norm(nom_cs)
    for c in q("SELECT * FROM jur_cs"):
        if norm(c["nom"]) == n and (not dep or norm(c["departement"]) == norm(dep)):
            return c
    if not creer or not nom_cs:
        return None
    cid = ex("INSERT INTO jur_cs (departement, nom, nb_zones) VALUES (?,?,0)", (dep, nom_cs.strip().upper()))
    return cs_par_id(cid)


def _trouver_zone(cs_id, nom_zone):
    if not cs_id or not (nom_zone or "").strip():
        return None
    n = norm(nom_zone)
    for z in q("SELECT * FROM jur_zones WHERE cs_id=?", (cs_id,)):
        if norm(z["nom"]) == n:
            return z["id"]
    # « 2 », « Zone 2 », « ZP 2 » → « Zone pédagogique 2 »
    import re
    m = re.search(r"(\d+)\s*$", nom_zone.strip())
    if m:
        for z in q("SELECT * FROM jur_zones WHERE cs_id=?", (cs_id,)):
            m2 = re.search(r"(\d+)\s*$", z["nom"])
            if m2 and m2.group(1) == m.group(1):
                return z["id"]
    ordre = (q("SELECT COALESCE(MAX(ordre),0) m FROM jur_zones WHERE cs_id=?", (cs_id,), un=True)["m"] or 0) + 1
    return ex("INSERT INTO jur_zones (cs_id, nom, ordre) VALUES (?,?,?)", (cs_id, nom_zone.strip(), ordre))


def enregistrer_ecole(e, cs_id=None, zone_id=None):
    """Crée ou met à jour une école à partir d'une IDENTITE_ECOLE (dict). Renvoie (id, créée?)."""
    code = (e.get("code") or "").strip()
    ex_ = q("SELECT id FROM jur_ecoles WHERE code=?", (code,), un=True)
    vals = {k: (str(e.get(k)) if e.get(k) is not None else "") for k in
            ("nom", "type", "secteur", "commune", "arrondissement", "localite", "adresse", "telephone", "email",
             "directeur_titre", "directeur_nom", "directeur_tel", "annee_creation")}
    vals["type"] = vals["type"] if vals["type"] in TYPES else "EP"
    vals["secteur"] = vals["secteur"] if vals["secteur"] in SECTEURS else "public"
    cols = list(vals) + ["cs_id", "zone_id"]
    args = [vals[k] for k in vals] + [cs_id, zone_id]
    if ex_:
        ex("UPDATE jur_ecoles SET " + ", ".join(f"{c}=?" for c in cols) + ", actif=1, maj=datetime('now','localtime') WHERE id=?",
           tuple(args + [ex_["id"]]))
        return ex_["id"], False
    eid = ex("INSERT INTO jur_ecoles (code, " + ", ".join(cols) + ", cree_le, maj) VALUES (?," + ",".join("?" * len(cols)) +
             ",datetime('now','localtime'),datetime('now','localtime'))", tuple([code] + args))
    return eid, True


def importer_paquet(paquet, mode="fichier", par="", taille=0, controle_perimetre=True):
    """Enregistre un paquet vérifié (jur_format.verifier). Renvoie un résumé (dict) :
    {"ecoles_creees", "ecoles_maj", "sections", "ignorees": [messages], "cs": nom|None, "paquet_id"}.
    Une CS n'accepte que les écoles de sa circonscription ; la DDEMP que celles de son département."""
    jur_format.verifier(paquet)
    s = structure()
    if not s:
        raise jur_format.PaquetInvalide("Configurez d'abord la structure (Paramètres de la juridiction).")
    a = paquet["annee"]
    em = paquet.get("emetteur") or {}
    res = {"ecoles_creees": 0, "ecoles_maj": 0, "sections": 0, "ignorees": [], "cs": None, "annee": a}
    if em.get("type") == "cs" and s["niveau"] != "ddemp":
        raise jur_format.PaquetInvalide("Ce fichier vient d'une circonscription : il doit être importé dans l'application DDEMP.")
    cs_paquet = None
    if paquet.get("cs"):
        ident = paquet["cs"].get("identite") or {}
        dep = ident.get("departement") or em.get("departement") or ""
        if controle_perimetre and s["niveau"] == "ddemp" and norm(dep) != norm(s["departement"]):
            raise jur_format.PaquetInvalide(f"Cette circonscription ({ident.get('nom')}) n'est pas du département {s['departement']}.")
        cs_paquet = _trouver_cs(dep, ident.get("nom") or em.get("cs") or em.get("nom"))
        for k in ("ccs_titre", "ccs_nom", "telephone", "email", "adresse"):
            if ident.get(k):
                ex(f"UPDATE jur_cs SET {k}=? WHERE id=?", (ident[k], cs_paquet["id"]))
        for nom, donnees in (paquet["cs"].get("sections") or {}).items():
            if nom in jur_format.SECTIONS_CS:
                ecrire_cs_section(cs_paquet["id"], nom, donnees, a, source="transmission")
                res["sections"] += 1
        res["cs"] = cs_paquet["nom"]
    derniere_ecole = None
    for item in paquet["ecoles"]:
        e = item["ecole"]
        dep = e.get("departement") or em.get("departement") or s["departement"]
        if s["niveau"] == "cs":
            if controle_perimetre and e.get("cs") and norm(e["cs"]) != norm(s["cs"]):
                res["ignorees"].append(f"{e['nom']} : école de la CS {e['cs']}, pas de {s['cs']}.")
                continue
            c = cs_courante()
        else:
            if controle_perimetre and dep and norm(dep) != norm(s["departement"]):
                res["ignorees"].append(f"{e['nom']} : école du département {dep}, pas de {s['departement']}.")
                continue
            c = cs_paquet or _trouver_cs(dep, e.get("cs"))
            if not c:
                res["ignorees"].append(f"{e['nom']} : circonscription scolaire non indiquée.")
                continue
        zid = _trouver_zone(c["id"], e.get("zone")) if c else None
        eid, cree = enregistrer_ecole(e, c["id"] if c else None, zid)
        res["ecoles_creees" if cree else "ecoles_maj"] += 1
        for nom, donnees in (item.get("sections") or {}).items():
            if nom in jur_format.SECTIONS_ECOLE and donnees is not None:
                ecrire_section(eid, nom, donnees, a, source="transmission")
                res["sections"] += 1
        ex("UPDATE jur_ecoles SET derniere_transmission=datetime('now','localtime') WHERE id=?", (eid,))
        derniere_ecole = eid
    if not res["ecoles_creees"] and not res["ecoles_maj"] and not cs_paquet:
        raise jur_format.PaquetInvalide("Aucune école de votre juridiction dans ce fichier. " + " ".join(res["ignorees"]))
    res["paquet_id"] = ex(
        "INSERT INTO jur_paquets (emetteur_type, emetteur_code, emetteur_nom, ecole_id, cs_id, annee, mode, empreinte, taille, "
        "resume, recu_le, recu_par) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'),?)",
        (em.get("type"), em.get("code"), em.get("nom"), derniere_ecole if em.get("type") == "ecole" else None,
         cs_paquet["id"] if cs_paquet else None, a, mode, paquet.get("empreinte"), taille,
         json.dumps(res, ensure_ascii=False), par))
    return res


def exporter_paquet_cs(annee_=None):
    """Paquet de la CS vers la DDEMP : toutes ses écoles (identité + sections de l'année) + sections propres."""
    s = structure()
    if not s or s["niveau"] != "cs":
        raise jur_format.PaquetInvalide("Seule une application de circonscription peut produire ce fichier.")
    a = annee_ or annee()
    c = cs_courante()
    p = jur_format.nouveau("cs", f"CS-{norm(s['departement'])}-{norm(s['cs'])}".replace(" ", "_"), s["nom"], a,
                           s["departement"], s["cs"], config.EDITION, f"GESCOL {config.VERSION}")
    p["genere_le"] = _maintenant()
    for e in ecoles():
        ident = {k: (e[k] if k in e.keys() else "") or "" for k in jur_format.CHAMPS_ECOLE}
        ident.update(departement=s["departement"], cs=s["cs"], zone=e["zone_nom"] or "")
        secs = {r["section"]: json.loads(r["donnees"]) for r in
                q("SELECT section, donnees FROM jur_sections WHERE ecole_id=? AND annee=?", (e["id"], a))}
        p["ecoles"].append({"ecole": ident, "sections": secs})
    secs_cs = {r["section"]: json.loads(r["donnees"]) for r in
               q("SELECT section, donnees FROM jur_cs_sections WHERE cs_id=? AND annee=?", (c["id"], a))} if c else {}
    agents = [dict(json.loads(r["donnees"] or "{}"), nom=r["nom"], prenoms=r["prenoms"] or "", sexe=r["sexe"] or "",
                   nip=r["nip"] or "", matricule=r["matricule"] or "", telephone=r["telephone"] or "",
                   service_code=r["service_code"] or "", poste=r["poste"] or "")
              for r in q("SELECT * FROM jur_agents WHERE actif=1 AND (cs_id IS NULL OR cs_id=?)", (c["id"] if c else 0,))]
    secs_cs["agents"] = agents
    p["cs"] = {"identite": {"departement": s["departement"], "nom": s["cs"], "ccs_titre": s["responsable_titre"] or "",
                            "ccs_nom": s["responsable_nom"] or "", "telephone": s["telephone"] or "",
                            "email": s["email"] or "", "adresse": s["adresse"] or ""},
               "sections": secs_cs}
    return jur_format.sceller(p)


def _maintenant():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ======================================================================== configuration de la structure
def configurer(niveau_, departement, cs="", **infos):
    """Crée / met à jour la structure et le référentiel (CS du département, zones pédagogiques)."""
    nom = infos.get("nom") or (f"Circonscription scolaire de {cs.title()}" if niveau_ == "cs"
                               else f"Direction départementale des Enseignements Maternel et Primaire du {departement}")
    sigle = infos.get("sigle") or (f"CS {cs}" if niveau_ == "cs" else f"DDEMP {departement}")
    ex("INSERT INTO jur_structure (id, niveau, departement, cs, nom, sigle, adresse, bp, telephone, email, ville, "
       "responsable_titre, responsable_nom, maj) VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime')) "
       "ON CONFLICT(id) DO UPDATE SET niveau=excluded.niveau, departement=excluded.departement, cs=excluded.cs, "
       "nom=excluded.nom, sigle=excluded.sigle, adresse=excluded.adresse, bp=excluded.bp, telephone=excluded.telephone, "
       "email=excluded.email, ville=excluded.ville, responsable_titre=excluded.responsable_titre, "
       "responsable_nom=excluded.responsable_nom, maj=excluded.maj",
       (niveau_, departement, cs, nom, sigle, infos.get("adresse", ""), infos.get("bp", ""), infos.get("telephone", ""),
        infos.get("email", ""), infos.get("ville", ""), infos.get("responsable_titre", ""), infos.get("responsable_nom", "")))
    liste = RB.CIRCONSCRIPTIONS.get(departement, [])
    if niveau_ == "cs":
        liste = [c for c in liste if c["cs"] == cs] or [{"n": None, "cs": cs, "arrondissements": "", "zones": 3}]
    for c in liste:
        r = q("SELECT id FROM jur_cs WHERE departement=? AND nom=?", (departement, c["cs"]), un=True)
        cid = r["id"] if r else ex("INSERT INTO jur_cs (departement, nom, numero, arrondissements, nb_zones) VALUES (?,?,?,?,?)",
                                   (departement, c["cs"], c["n"], c["arrondissements"], c["zones"]))
        if not q("SELECT 1 FROM jur_zones WHERE cs_id=? LIMIT 1", (cid,), un=True):
            for i in range(1, (c["zones"] or 0) + 1):
                ex("INSERT OR IGNORE INTO jur_zones (cs_id, nom, ordre) VALUES (?,?,?)", (cid, f"Zone pédagogique {i}", i))
    if niveau_ == "cs" and infos.get("responsable_nom"):
        ex("UPDATE jur_cs SET ccs_titre=?, ccs_nom=? WHERE departement=? AND nom=?",
           (infos.get("responsable_titre", ""), infos["responsable_nom"], departement, cs))


def nouveau_code(nom, cs_nom=""):
    """Code provisoire unique pour une école saisie à la main (remplacé par celui de l'école à sa 1re transmission)."""
    base = "".join(ch for ch in norm(cs_nom)[:6] if ch.isalnum()) or "CS"
    return f"{base}-{secrets.token_hex(3).upper()}"


# ======================================================================== enregistrement Flask
def enregistrer(app, H):
    H.schema(SCHEMA)
    # accès pour les autres modules
    H.jur_structure, H.jur_niveau, H.jur_annee, H.jur_annees = structure, niveau, annee, annees
    H.jur_cs_liste, H.jur_cs, H.jur_cs_courante, H.jur_zones = cs_liste, cs_par_id, cs_courante, zones
    H.jur_ecoles, H.jur_ecole, H.jur_section, H.jur_sections = ecoles, ecole, section, sections
    H.jur_ecrire_section, H.jur_cs_section, H.jur_ecrire_cs_section = ecrire_section, cs_section, ecrire_cs_section
    H.jur_personnel, H.jur_importer_paquet, H.jur_exporter_paquet_cs = personnel, importer_paquet, exporter_paquet_cs
    H.jur_enregistrer_ecole, H.jur_norm, H.jur_format = enregistrer_ecole, norm, jur_format
    H.jur_TYPES, H.jur_SECTEURS = TYPES, SECTEURS

    @app.before_request
    def jur_entete():
        """En-tête de l'application : nom de la circonscription ou de la DDEMP."""
        if not config.juridiction():
            return
        s = structure()
        if s:
            config.ECOLE.update(nom=s["nom"] or "", sigle=s["sigle"] or "", departement=s["departement"] or "",
                                cs=s["cs"] or "", adresse=s["adresse"] or "", telephone=s["telephone"] or "",
                                email=s["email"] or "", ville=s["ville"] or "")
        else:
            config.ECOLE.update(nom=config.NOMS_APPLI.get(config.EDITION, "GESCOL"), sigle="", cs="")
            ep = request.endpoint or ""
            if g.get("user") and ep not in ("jur_structure", "logout", "mon_compte", "static", "referentiel_js",
                                            "manifeste", "sw", "signature_png") and not ep.startswith("api_"):
                if g.user["role"] in ("admin", "fondateur", "responsable"):
                    return redirect(url_for("jur_structure"))

    @app.context_processor
    def jur_contexte():
        if not config.juridiction():
            return {}
        s = structure() or {}
        return dict(JUR=s, JUR_NIVEAU=config.EDITION, JUR_TYPES=TYPES, JUR_SECTEURS=SECTEURS)

    # ------------------------------------------------------------------ structure
    @app.route("/juridiction/structure", methods=["GET", "POST"])
    @H.connexion_requise("jur_structure")
    def jur_structure():
        if not config.juridiction():
            abort(404)
        s = structure() or {}
        if request.method == "POST":
            f = request.form
            dep = f.get("departement", "").strip()
            cs = f.get("cs", "").strip().upper()
            erreurs = []
            if dep not in RB.DEPARTEMENTS:
                erreurs.append("Choisissez le département.")
            if config.EDITION == "cs" and not cs:
                erreurs.append("Choisissez la circonscription scolaire.")
            if s and (s.get("departement") != dep or (config.EDITION == "cs" and s.get("cs") != cs)) \
                    and q("SELECT 1 FROM jur_ecoles LIMIT 1", un=True) and f.get("confirmer") != "1":
                erreurs.append("Des écoles sont déjà enregistrées : cochez la confirmation pour changer de juridiction.")
            if erreurs:
                for m in erreurs:
                    flash(m, "danger")
                return render_template("jur_structure.html", s=dict(f), departements=RB.DEPARTEMENTS,
                                       cs_par_dep={d: RB.cs_du_departement(d) for d in RB.DEPARTEMENTS}), 400
            configurer(config.EDITION, dep, cs if config.EDITION == "cs" else "",
                       **{k: f.get(k, "").strip() for k in ("nom", "sigle", "adresse", "bp", "telephone", "email",
                                                            "ville", "responsable_titre", "responsable_nom")})
            H.journal("jur_structure", f"{config.EDITION} {dep} {cs}")
            flash("Structure enregistrée.", "success")
            return redirect(url_for("jur_structure"))
        return render_template("jur_structure.html", s=s, departements=RB.DEPARTEMENTS,
                               cs_par_dep={d: RB.cs_du_departement(d) for d in RB.DEPARTEMENTS})

    # ------------------------------------------------------------------ circonscriptions et zones
    @app.route("/juridiction/zones", methods=["GET", "POST"])
    @H.connexion_requise("jur_ecoles")
    def jur_zones():
        if not config.juridiction():
            abort(404)
        if request.method == "POST":
            act = request.form.get("action")
            if act == "zone_ajouter":
                cid = int(request.form.get("cs_id") or 0)
                nom = request.form.get("nom", "").strip()
                if not cs_par_id(cid) or not nom:
                    flash("Indiquez la circonscription et le nom de la zone.", "danger")
                else:
                    ordre = (q("SELECT COALESCE(MAX(ordre),0) m FROM jur_zones WHERE cs_id=?", (cid,), un=True)["m"] or 0) + 1
                    ex("INSERT OR IGNORE INTO jur_zones (cs_id, nom, ordre) VALUES (?,?,?)", (cid, nom, ordre))
                    flash("Zone ajoutée.", "success")
            elif act == "zone_modifier":
                zid = int(request.form.get("zone_id") or 0)
                nom = request.form.get("nom", "").strip()
                if nom:
                    ex("UPDATE jur_zones SET nom=?, cp_nom=?, cp_telephone=? WHERE id=?",
                       (nom, request.form.get("cp_nom", "").strip(), request.form.get("cp_telephone", "").strip(), zid))
                    flash("Zone modifiée.", "success")
            elif act == "zone_supprimer":
                zid = int(request.form.get("zone_id") or 0)
                if q("SELECT 1 FROM jur_ecoles WHERE zone_id=? AND actif=1 LIMIT 1", (zid,), un=True):
                    flash("Cette zone contient des écoles : déplacez-les d'abord.", "danger")
                else:
                    ex("DELETE FROM jur_zones WHERE id=?", (zid,))
                    flash("Zone supprimée.", "success")
            elif act == "cs_modifier":
                cid = int(request.form.get("cs_id") or 0)
                ex("UPDATE jur_cs SET ccs_titre=?, ccs_nom=?, telephone=?, email=?, adresse=? WHERE id=?",
                   tuple(request.form.get(k, "").strip() for k in ("ccs_titre", "ccs_nom", "telephone", "email", "adresse")) + (cid,))
                flash("Circonscription modifiée.", "success")
            elif act == "cs_ajouter" and config.EDITION == "ddemp":
                nom = request.form.get("nom", "").strip().upper()
                s = structure()
                if nom and s:
                    ex("INSERT OR IGNORE INTO jur_cs (departement, nom, nb_zones) VALUES (?,?,0)", (s["departement"], nom))
                    flash("Circonscription ajoutée.", "success")
            return redirect(url_for("jur_zones"))
        liste = []
        for c in cs_liste():
            nbz = {r["zone_id"]: r["n"] for r in q("SELECT zone_id, COUNT(*) n FROM jur_ecoles WHERE cs_id=? AND actif=1 "
                                                  "GROUP BY zone_id", (c["id"],))}
            liste.append({"cs": c, "zones": [dict(z, nb=nbz.get(z["id"], 0)) for z in zones(c["id"])],
                          "nb_ecoles": q("SELECT COUNT(*) n FROM jur_ecoles WHERE cs_id=? AND actif=1", (c["id"],), un=True)["n"]})
        return render_template("jur_zones.html", liste=liste)

    # ------------------------------------------------------------------ écoles
    @app.route("/juridiction/ecoles")
    @H.connexion_requise()
    def jur_ecoles():
        if not config.juridiction():
            abort(404)
        f = request.args
        cs_id = int(f.get("cs") or 0) or None
        zone_id = int(f.get("zone") or 0) or None
        liste = ecoles(cs_id, zone_id, f.get("type") or None, f.get("secteur") or None, recherche=f.get("q") or None)
        a = annee()
        recus = {r["ecole_id"]: r["n"] for r in q("SELECT ecole_id, COUNT(*) n FROM jur_sections WHERE annee=? GROUP BY ecole_id", (a,))}
        compte = {}
        for e in liste:
            compte[(e["type"], e["secteur"])] = compte.get((e["type"], e["secteur"]), 0) + 1
        if f.get("export") == "xlsx":
            ent = ["Code", "Nom", "Type", "Secteur", "Circonscription", "Zone pédagogique", "Commune", "Arrondissement",
                   "Localité", "Directeur (titre)", "Directeur (nom)", "Téléphone directeur", "Téléphone école", "E-mail",
                   "Année de création", "Dernière transmission"]
            lignes = [[e["code"], e["nom"], e["type"], e["secteur"], e["cs_nom"] or "", e["zone_nom"] or "", e["commune"] or "",
                       e["arrondissement"] or "", e["localite"] or "", e["directeur_titre"] or "", e["directeur_nom"] or "",
                       e["directeur_tel"] or "", e["telephone"] or "", e["email"] or "", e["annee_creation"] or "",
                       e["derniere_transmission"] or ""] for e in liste]
            return H.xlsx.reponse_xlsx("ecoles_juridiction.xlsx", ent, lignes, "Écoles",
                                       [config.ECOLE.get("nom", ""), f"Liste des écoles – {a}"])
        return render_template("jur_ecoles.html", ecoles=liste, recus=recus, compte=compte, cs=cs_liste(),
                               zones=zones(cs_id) if cs_id else zones(), f=f)

    def _form_ecole(e=None):
        f = request.form
        donnees = {k: f.get(k, "").strip() for k in ("nom", "type", "secteur", "commune", "arrondissement", "localite",
                                                     "adresse", "telephone", "email", "directeur_titre", "directeur_nom",
                                                     "directeur_tel", "annee_creation")}
        cs_id = int(f.get("cs_id") or 0) or None
        zone_id = int(f.get("zone_id") or 0) or None
        erreurs = []
        if not donnees["nom"]:
            erreurs.append("Le nom de l'école est obligatoire.")
        if donnees["type"] not in TYPES:
            erreurs.append("Type d'école invalide.")
        if donnees["secteur"] not in SECTEURS:
            erreurs.append("Secteur invalide.")
        if not cs_id or not cs_par_id(cs_id):
            erreurs.append("Choisissez la circonscription scolaire.")
        if zone_id and not q("SELECT 1 FROM jur_zones WHERE id=? AND cs_id=?", (zone_id, cs_id), un=True):
            erreurs.append("La zone pédagogique ne correspond pas à la circonscription.")
        a_c = donnees["annee_creation"]
        if a_c and not (a_c.isdigit() and 1850 <= int(a_c) <= 2100):
            erreurs.append("Année de création invalide (ex. 1995).")
        code = f.get("code", "").strip().upper()
        if code and q("SELECT 1 FROM jur_ecoles WHERE code=? AND id<>?", (code, e["id"] if e else 0), un=True):
            erreurs.append("Ce code est déjà utilisé par une autre école.")
        return donnees, cs_id, zone_id, code, erreurs

    @app.route("/juridiction/ecoles/nouvelle", methods=["GET", "POST"])
    @app.route("/juridiction/ecoles/<int:eid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("jur_ecoles")
    def jur_ecole_form(eid=None):
        if not config.juridiction():
            abort(404)
        e = ecole(eid) if eid else None
        if eid and not e:
            abort(404)
        if request.method == "POST":
            donnees, cs_id, zone_id, code, erreurs = _form_ecole(e)
            if erreurs:
                for m in erreurs:
                    flash(m, "danger")
                return render_template("jur_ecole_form.html", e=dict(request.form), eid=eid, cs=cs_liste(), zones=zones()), 400
            if e:
                ex("UPDATE jur_ecoles SET " + ", ".join(f"{k}=?" for k in donnees) + ", cs_id=?, zone_id=?, code=?, "
                   "maj=datetime('now','localtime') WHERE id=?", tuple(donnees.values()) + (cs_id, zone_id, code or e["code"], eid))
                H.journal("jur_ecole_modifiee", donnees["nom"])
            else:
                cs_nom = cs_par_id(cs_id)["nom"]
                eid = ex("INSERT INTO jur_ecoles (code, " + ", ".join(donnees) + ", cs_id, zone_id, cree_le, maj) VALUES (?," +
                         ",".join("?" * len(donnees)) + ",?,?,datetime('now','localtime'),datetime('now','localtime'))",
                         (code or nouveau_code(donnees["nom"], cs_nom),) + tuple(donnees.values()) + (cs_id, zone_id))
                H.journal("jur_ecole_ajoutee", donnees["nom"])
            flash("École enregistrée.", "success")
            return redirect(url_for("jur_ecole_fiche", eid=eid))
        vals = dict(e) if e else {"type": "EP", "secteur": "public", "directeur_titre": "Directeur",
                                  "cs_id": (cs_courante() or {"id": None})["id"] if config.EDITION == "cs" else None}
        return render_template("jur_ecole_form.html", e=vals, eid=eid, cs=cs_liste(), zones=zones())

    @app.route("/juridiction/ecoles/<int:eid>")
    @H.connexion_requise()
    def jur_ecole_fiche(eid):
        if not config.juridiction():
            abort(404)
        e = ecole(eid)
        if not e:
            abort(404)
        a = request.args.get("annee") or annee()
        secs = {r["section"]: r for r in q("SELECT section, source, maj, length(donnees) taille FROM jur_sections "
                                            "WHERE ecole_id=? AND annee=?", (eid, a))}
        eff = section(eid, "effectifs", a) or {}
        g_ = sum(int(c.get("garcons") or 0) for c in eff.get("classes", []))
        f_ = sum(int(c.get("filles") or 0) for c in eff.get("classes", []))
        pers = section(eid, "personnel", a) or []
        paquets = q("SELECT * FROM jur_paquets WHERE ecole_id=? ORDER BY id DESC LIMIT 10", (eid,))
        return render_template("jur_ecole_fiche.html", e=e, secs=secs, annee=a, annees=annees(), eff=eff, g_=g_, f_=f_,
                               pers=pers, paquets=paquets, noms_sections=NOMS_SECTIONS)

    @app.route("/juridiction/ecoles/<int:eid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_ecoles")
    def jur_ecole_supprimer(eid):
        e = ecole(eid) or abort(404)
        ex("UPDATE jur_ecoles SET actif=0, maj=datetime('now','localtime') WHERE id=?", (eid,))
        H.journal("jur_ecole_retiree", e["nom"])
        flash(f"« {e['nom']} » retirée de la liste (ses données sont conservées).", "success")
        return redirect(url_for("jur_ecoles"))

    @app.route("/juridiction/ecoles/import", methods=["GET", "POST"])
    @H.connexion_requise("jur_ecoles")
    def jur_ecoles_import():
        if not config.juridiction():
            abort(404)
        if request.args.get("modele"):
            ent = ["Code", "Nom", "Type (EP/EM/EE)", "Secteur (public/prive)", "Circonscription", "Zone pédagogique",
                   "Commune", "Arrondissement", "Localité", "Directeur (nom)", "Téléphone directeur", "Année de création"]
            s = structure() or {}
            ex_ = [["", "EPP Exemple", "EP", "public", s.get("cs") or "", "Zone pédagogique 1", "", "", "", "", "", ""]]
            return H.xlsx.reponse_xlsx("modele_ecoles.xlsx", ent, ex_, "Écoles")
        if request.method == "POST":
            fic = request.files.get("fichier")
            if not fic or not fic.filename.lower().endswith(".xlsx"):
                flash("Choisissez un fichier Excel (.xlsx).", "danger")
                return redirect(url_for("jur_ecoles_import"))
            try:
                ent, lignes = H.xlsx.lire_tableau(fic, ("nom",))
            except H.xlsx.ExcelIndisponible as e_:
                flash(str(e_), "danger")
                return redirect(url_for("jur_ecoles_import"))
            except Exception:  # noqa: BLE001
                flash("Fichier Excel illisible.", "danger")
                return redirect(url_for("jur_ecoles_import"))
            col = lambda *n: H.xlsx.colonne(ent, *n)  # noqa: E731
            i_nom, i_code, i_type, i_sect = col("nom"), col("code"), col("type"), col("secteur")
            i_cs, i_zone, i_com, i_arr = col("circonscription", "cs"), col("zone"), col("commune"), col("arrondissement")
            i_loc, i_dir, i_tel, i_an = col("localite", "localité"), col("directeur"), col("telephone directeur", "téléphone"), col("creation")
            if i_nom is None:
                flash("Colonne « Nom » introuvable.", "danger")
                return redirect(url_for("jur_ecoles_import"))
            s = structure()
            nb, erreurs = 0, []
            for n, l in enumerate(lignes, start=2):
                v = lambda i: (str(H.xlsx.valeur(l, i)).strip() if i is not None and H.xlsx.valeur(l, i) is not None else "")  # noqa: E731
                nom = v(i_nom)
                if not nom:
                    continue
                typ = v(i_type).upper()[:2] or "EP"
                sect = H.xlsx.normaliser(v(i_sect)).replace("é", "e")
                sect = "prive" if sect.startswith("priv") else "public"
                if typ not in TYPES:
                    erreurs.append(f"Ligne {n} : type « {v(i_type)} » inconnu (EP, EM ou EE).")
                    continue
                c = cs_courante() if s["niveau"] == "cs" else _trouver_cs(s["departement"], v(i_cs), creer=False)
                if not c:
                    erreurs.append(f"Ligne {n} : circonscription « {v(i_cs)} » introuvable.")
                    continue
                ident = {"code": v(i_code).upper() or None, "nom": nom, "type": typ, "secteur": sect,
                         "commune": v(i_com), "arrondissement": v(i_arr), "localite": v(i_loc),
                         "directeur_titre": "Directeur", "directeur_nom": v(i_dir), "directeur_tel": v(i_tel),
                         "annee_creation": v(i_an)}
                if not ident["code"]:
                    r = q("SELECT code FROM jur_ecoles WHERE nom=? AND cs_id=?", (nom, c["id"]), un=True)
                    ident["code"] = r["code"] if r else nouveau_code(nom, c["nom"])
                enregistrer_ecole(ident, c["id"], _trouver_zone(c["id"], v(i_zone)))
                nb += 1
            for m in erreurs[:15]:
                flash(m, "warning")
            flash(f"{nb} école(s) importée(s) ou mise(s) à jour.", "success" if nb else "warning")
            H.journal("jur_ecoles_import", str(nb))
            return redirect(url_for("jur_ecoles"))
        return render_template("jur_ecoles_import.html")

    @app.route("/juridiction/zones.json")
    @H.connexion_requise()
    def jur_zones_json():
        cid = int(request.args.get("cs") or 0)
        return {"zones": [{"id": z["id"], "nom": z["nom"]} for z in zones(cid)]} if cid else {"zones": []}


NOMS_SECTIONS = {"effectifs": "Effectifs des élèves", "personnel": "Personnel", "visites": "Visites de classe",
                 "cep": "CEP (candidats, résultats)", "recensement": "Fiches de recensement",
                 "rapports": "Rapports de rentrée / fin d'année", "patrimoine": "Patrimoine et infrastructures",
                 "cantine": "Cantine scolaire"}
