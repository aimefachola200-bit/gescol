# -*- coding: utf-8 -*-
"""v2.0 — Synchronisation entre niveaux (école → UP → zone → CS → DDEMP), hors ligne d'abord.

Protocole commun à toutes les applications : /home/claude/outils/sync/spec.md (paquets .scsync signés Ed25519,
incrémentaux avec curseur ``seq`` et tombes, transport par fichier ou HTTP, inscription par QR code, conflits champ
par champ avec priorité au niveau le plus élevé).

* Éditions école (privée, publique) : CLIENT de la CS — montant (transmission + objets suivis), descendant (notes de
  service, circulaires, convocations, échéances, agenda, versions proposées).
* Édition cs : HUB de ses écoles (/sync/push, /sync/pull, fichiers) et CLIENT de la DDEMP (relaie les objets de ses
  écoles et redescend ceux de la DDEMP).
* Édition ddemp : HUB des CS.

Pages : /synchronisation (état, synchroniser, fichiers, rejoindre, historique, conflits) ;
/synchronisation/entites (hub : entités inscrites, QR d'inscription, fichiers descendants, nouvelle clé).
"""
import gzip
import hashlib
import io
import json
import re
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid
import zlib
from datetime import datetime

from flask import Response, abort, flash, g, jsonify, redirect, render_template, request, url_for

import config
import jur_pobe as JP
import sync_crypto as SC

FORMAT, V = "memp-sync", 1
TAILLE_MAX = 15 * 1024 * 1024
DECOMP_MAX = 60 * 1024 * 1024
TIMEOUT = 25
RANG = {"ECOLE": 0, "UP": 1, "ZONE": 2, "CS": 3, "DDEMP": 4}
REG_MONTANT = [("sport", "licences"), ("sport", "officiels"), ("sport", "sites"), ("examens", "candidats"), ("examens", "concours"),
               ("examens", "participants"), ("patrimoine", "besoins"), ("communication", "lectures"), ("pilotage", "indicateurs"),
               ("territoire", "rentree"), ("communication", "courrier"), ("examens", "salles"),
               ("territoire", "signaletique")]   # v2.3
REG_DESCENDANT = [("communication", "notes"), ("communication", "echeances"), ("communication", "agenda"), ("territoire", "retours"),
                  ("territoire", "structures")]          # v2.3.2 : le référentiel des structures descend (comme les applications JS)
# v2.3 : registres qui montent ET descendent (copie descendante sous le type « reg:<g>:<r>@bas ») : centres du CEP 2027
# (la CS les envoie à la DDEMP et à ses écoles, qui les consultent en lecture seule)
REG_AUSSI_DESCENDANT = [("examens", "salles")]
LIBELLES = {"uascep_bureaux": "Bureaux UASCEP", "uascep_membres": "Membres UASCEP", "uascep_rapports": "Rapports de saison UASCEP",
            "eb_centres": "Examen blanc : centres", "eb_candidats": "Examen blanc : candidats et notes", "version": "Versions proposées",
            "reg:communication:notes": "Notes, circulaires, convocations", "reg:communication:echeances": "Échéances et rappels",
            "reg:communication:agenda": "Agenda", "reg:communication:lectures": "Accusés de réception",
            "reg:sport:licences": "Licences sportives", "reg:sport:officiels": "Officiels du sport", "reg:sport:sites": "Sites sportifs",
            "reg:examens:candidats": "Candidats (examens)", "reg:examens:concours": "Concours scolaires",
            "reg:examens:participants": "Participants aux concours", "reg:patrimoine:besoins": "Besoins exprimés",
            "reg:pilotage:indicateurs": "Indicateurs du pilotage", "reg:territoire:rentree": "Fiches statistiques de rentrée",
            "reg:communication:courrier": "Courrier administratif", "reg:territoire:retours": "Décisions (fiches de rentrée, courrier)",
            "reg:examens:salles": "CEP : centres et salles", "reg:territoire:structures": "Référentiel des structures", "reg:territoire:signaletique": "Fiches signalétiques", "reg:examens:salles@bas": "CEP : centres et salles (copie des écoles)"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_ids (type TEXT NOT NULL, local_id INTEGER NOT NULL, uuid TEXT NOT NULL, scope INTEGER NOT NULL DEFAULT 0,
    empreinte TEXT, seq INTEGER, origine TEXT NOT NULL DEFAULT 'local', base TEXT, supprime INTEGER NOT NULL DEFAULT 0, maj TEXT,
    PRIMARY KEY (type, local_id));
CREATE UNIQUE INDEX IF NOT EXISTS ux_sync_ids_uuid ON sync_ids(type, uuid);
CREATE INDEX IF NOT EXISTS ix_sync_ids_seq ON sync_ids(scope, seq);
CREATE TABLE IF NOT EXISTS sync_compteur (id INTEGER PRIMARY KEY CHECK (id = 1), seq INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sync_client (ecole_id INTEGER PRIMARY KEY, adresse TEXT, code TEXT, hub_cle TEXT, hub_nom TEXT, hub_niveau TEXT,
    accuse_seq INTEGER NOT NULL DEFAULT 0, desc_seq INTEGER NOT NULL DEFAULT 0, dernier_paquet_recu TEXT, dernier_envoi TEXT,
    derniere_reception TEXT, dernier_message TEXT);
CREATE TABLE IF NOT EXISTS sync_sources (cle TEXT PRIMARY KEY, kind TEXT NOT NULL, ref_id INTEGER NOT NULL, nom TEXT, code TEXT,
    installation TEXT, cle_publique TEXT, cle_attente TEXT, accuse_seq INTEGER NOT NULL DEFAULT 0, dernier_paquet TEXT,
    desc_accuse INTEGER NOT NULL DEFAULT 0, derniere_reception TEXT, nb_objets INTEGER NOT NULL DEFAULT 0, dernier_message TEXT);
CREATE TABLE IF NOT EXISTS sync_historique (id INTEGER PRIMARY KEY, quand TEXT, ecole_id INTEGER, sens TEXT, mode TEXT, paquet TEXT,
    partenaire TEXT, nb INTEGER, statut TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS sync_conflits (id INTEGER PRIMARY KEY, quand TEXT, ecole_id INTEGER, type TEXT, uuid TEXT, local_id INTEGER,
    champ TEXT, valeur_locale TEXT, valeur_recue TEXT, retenue TEXT, source TEXT, resolu INTEGER NOT NULL DEFAULT 0);
"""
_VERROU = threading.Lock()
_echecs = {}


class PaquetRefuse(Exception):
    def __init__(self, message, code=422):
        super().__init__(message)
        self.code = code


def maintenant_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def lire_octets(octets):
    """Octets .scsync (gzip ou JSON) → dict, avec limites de taille (pas de « bombe » de décompression)."""
    if not octets:
        raise PaquetRefuse("Fichier vide.")
    if len(octets) > TAILLE_MAX:
        raise PaquetRefuse("Paquet trop volumineux (15 Mo au maximum).", 413)
    if octets[:2] == b"\x1f\x8b":
        try:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            brut = d.decompress(octets, DECOMP_MAX)
            if d.unconsumed_tail or not d.eof:
                raise PaquetRefuse("Paquet abîmé ou trop volumineux une fois décompressé.")
        except zlib.error as e:
            raise PaquetRefuse("Paquet abîmé : impossible de le décompresser.") from e
    else:
        brut = octets
    try:
        p = json.loads(brut.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise PaquetRefuse("Ce fichier n'est pas un paquet de synchronisation.") from e
    if not isinstance(p, dict) or p.get("format") != FORMAT or p.get("v") != V:
        raise PaquetRefuse("Ce fichier n'est pas un paquet de synchronisation (format inconnu).")
    for k in ("id", "sens", "emetteur", "objets", "signature"):
        if k not in p:
            raise PaquetRefuse(f"Paquet incomplet (« {k} » manquant).")
    if p["sens"] not in ("montant", "descendant") or not isinstance(p["objets"], list):
        raise PaquetRefuse("Paquet invalide.")
    if not SC.verifier(p):
        raise PaquetRefuse("Signature invalide : le paquet a été modifié ou ne vient pas de l'émetteur annoncé.", 403)
    return p


def vers_octets(p):
    return gzip.compress(json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), compresslevel=6, mtime=0)


def ouvrir(url, donnees=None, entetes=None, methode="GET"):
    """Requête HTTP(S) ; sur le réseau local (127.x, 10.x, 192.168.x, 172.16-31.x, .local) sans proxy."""
    hote = urllib.parse.urlparse(url).hostname or ""
    local = hote in ("localhost",) or hote.endswith(".local") or re.match(r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", hote)
    gestionnaires = [urllib.request.ProxyHandler({})] if local else []
    if url.startswith("https://"):
        gestionnaires.append(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    op = urllib.request.build_opener(*gestionnaires)
    req = urllib.request.Request(url, data=donnees, method=methode, headers=dict({"User-Agent": f"GESCOL/{config.VERSION}"}, **(entetes or {})))
    return op.open(req, timeout=TIMEOUT)


def lien_inscription(adresse, code, entite_code, nom):
    return "memp-sync:1?" + urllib.parse.urlencode({"u": adresse, "c": code, "e": entite_code or "", "n": nom or ""})


def lire_lien(t):
    t = (t or "").strip()
    if not t.startswith("memp-sync:1?"):
        return None
    d = dict(urllib.parse.parse_qsl(t.split("?", 1)[1]))
    return {"adresse": d.get("u", ""), "code": d.get("c", ""), "entite": d.get("e", ""), "nom": d.get("n", "")}


def svg_qr(texte, taille=180):
    import pdfs
    m = pdfs.qr_modules(texte)
    n = len(m)
    b = 4
    rects = "".join(f'<rect x="{c + b}" y="{r + b}" width="1" height="1"/>' for r, ligne in enumerate(m) for c, v in enumerate(ligne) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n + 2 * b} {n + 2 * b}" width="{taille}" height="{taille}" '
            f'role="img" aria-label="Code QR d\'inscription" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/>'
            f'<g fill="#000">{rects}</g></svg>')


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)
    H.DROITS["synchronisation"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service"}
    import m_transmission as MT

    # ================================================================== contexte
    def juridiction():
        return config.juridiction()

    def niveau_hub():
        return "DDEMP" if config.EDITION == "ddemp" else "CS"

    def est_hub():
        return juridiction()

    def est_client():
        return config.EDITION != "ddemp"

    def scope_client():
        """Clé de rangement de l'état client : l'école courante (éditions école) ou 0 (la CS cliente de la DDEMP)."""
        return 0 if juridiction() else H.eco()

    def ecole_code(eid):
        r = q("SELECT code_ecole FROM ecoles WHERE id=?", (eid,), un=True) if eid else None
        return (r["code_ecole"] if r else None) or None

    def ecole_code_assure(eid):
        """Code unique de l'école (créé comme le fait la transmission si besoin)."""
        c = ecole_code(eid)
        if c:
            return c
        e = q("SELECT * FROM ecoles WHERE id=?", (eid,), un=True)
        base = MT.norm_code((e["cs"] if e and "cs" in e.keys() else "") or "")[:6] or "ECOLE"
        for _ in range(20):
            code = f"{base}-{secrets.token_hex(3).upper()}"
            if not q("SELECT 1 FROM ecoles WHERE code_ecole=?", (code,), un=True):
                ex("UPDATE ecoles SET code_ecole=? WHERE id=? AND (code_ecole IS NULL OR code_ecole='')", (code, eid))
                return code
        return None

    def emetteur():
        ident = SC.identite()
        if juridiction():
            s = H.jur_structure() or {}
            nom = s.get("nom") or (config.ECOLE or {}).get("nom") or ""
            return {"installation": ident["installation"], "cle": ident["cle"], "application": config.NOMS_APPLI.get(config.EDITION, "GESCOL"),
                    "version": config.VERSION, "edition": config.EDITION, "niveau": niveau_hub(), "code": H.jur_norm(nom) if nom else "",
                    "nom": nom, "cs": s.get("cs") or nom, "departement": s.get("departement") or ""}
        e = q("SELECT * FROM ecoles WHERE id=?", (H.eco(),), un=True)
        return {"installation": ident["installation"], "cle": ident["cle"], "application": config.NOMS_APPLI.get(config.EDITION, "GESCOL"),
                "version": config.VERSION, "edition": config.EDITION, "niveau": "ECOLE", "code": ecole_code_assure(H.eco()) or "",
                "nom": (e["nom"] if e else "") or "", "cs": (e["cs"] if e and "cs" in e.keys() else "") or "",
                "departement": (e["departement"] if e and "departement" in e.keys() else "") or ""}

    def prochain_seq():
        with _VERROU:
            r = q("SELECT seq FROM sync_compteur WHERE id=1", un=True)
            n = (r["seq"] if r else 0) + 1
            ex("INSERT INTO sync_compteur (id, seq) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET seq=excluded.seq", (n,))
            return n

    def historiser(sens, mode, paquet, partenaire, nb, statut, message, eid=None):
        ex("INSERT INTO sync_historique (quand, ecole_id, sens, mode, paquet, partenaire, nb, statut, message) VALUES (?,?,?,?,?,?,?,?,?)",
           (H.maintenant(), scope_client() if eid is None else eid, sens, mode, paquet, (partenaire or "")[:200], nb, statut, (message or "")[:500]))

    def table_existe(t):
        return bool(q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,), un=True))

    def colonnes(t):
        return [r[1] for r in H.get_db().execute(f"PRAGMA table_info({t})")]

    # ================================================================== objets suivis
    # Chaque type : lister(cible) -> [(local_id, donnees, liens, ecole_code)], lire(local_id), inserer(d, liens, ecole_code),
    # maj(local_id, d, liens, ecole_code), supprimer(local_id). cible = "montant" (client) | "descendant" (hub) | "hub" (réception)
    TYPES = {}

    def portee_de_code(code):
        """Hub : école locale (table ecoles) de l'école de code `code` ; 0 = structure."""
        if not code:
            return 0
        r = q("SELECT id FROM ecoles WHERE code_ecole=?", (code,), un=True)
        if r:
            return r["id"]
        je = q("SELECT id FROM jur_ecoles WHERE code=?", (code,), un=True) if table_existe("jur_ecoles") else None
        if je and hasattr(H, "assurer_ecole_locale"):
            try:
                eid = H.assurer_ecole_locale(je["id"])
                if not ecole_code(eid):
                    ex("UPDATE ecoles SET code_ecole=? WHERE id=? AND (code_ecole IS NULL OR code_ecole='')", (code, eid))
                return eid
            except Exception:  # noqa: BLE001
                return 0
        return 0

    def code_de_portee(p):
        if not p:
            return None
        return ecole_code(abs(p))

    def type_table(nom, table, exclure=(), scope_sql=None, apres_lecture=None, avant_ecriture=None, lien=None, cle_adoption=None):
        """Type générique adossé à une table. lien = (colonne, type lié, clé de liens)."""
        def cols():
            return [c for c in colonnes(table) if c not in ("id",) + tuple(exclure) and (not lien or c != lien[0])]

        def lire(lid):
            r = q(f"SELECT * FROM {table} WHERE id=?", (lid,), un=True)
            if not r:
                return None
            d = {c: r[c] for c in cols()}
            return apres_lecture(d, r) if apres_lecture else d

        def liens_de(r):
            if not lien:
                return {}
            u = uuid_de(lien[1], r[lien[0]]) if r[lien[0]] else None
            return {lien[2]: u} if u else {}

        def lister(cible):
            if not table_existe(table):
                return []
            where, args, code = scope_sql(cible) if scope_sql else ("1=1", (), None)
            out = []
            for r in q(f"SELECT * FROM {table} WHERE {where}", args):
                d = {c: r[c] for c in cols()}
                if apres_lecture:
                    d = apres_lecture(d, r)
                out.append((r["id"], d, liens_de(r), code(r) if callable(code) else code))
            return out

        def ecrire(lid, d, liens, code):
            d = {k: v for k, v in d.items() if k in cols()}
            if avant_ecriture:
                d = avant_ecriture(dict(d), code)
            if lien:
                cible = local_de(lien[1], (liens or {}).get(lien[2]))
                if not cible:
                    raise PaquetRefuse(f"Objet lié introuvable ({lien[1]}).")
                d[lien[0]] = cible
            d = {k: v for k, v in d.items() if k in colonnes(table)}
            if lid:
                if d:
                    ex(f"UPDATE {table} SET {', '.join(k + '=?' for k in d)} WHERE id=?", tuple(d.values()) + (lid,))
                return lid
            if cle_adoption:
                r = cle_adoption(d)
                if r:
                    ex(f"UPDATE {table} SET {', '.join(k + '=?' for k in d)} WHERE id=?", tuple(d.values()) + (r,))
                    return r
            return ex(f"INSERT INTO {table} ({', '.join(d)}) VALUES ({','.join('?' * len(d))})", tuple(d.values()))

        def supprimer(lid):
            ex(f"DELETE FROM {table} WHERE id=?", (lid,))

        TYPES[nom] = {"lister": lister, "lire": lire, "ecrire": ecrire, "supprimer": supprimer, "table": table}

    # ---- UASCEP
    def scope_bureaux(cible):
        if juridiction():
            return "ecole_id IS NULL", (), None
        return "COALESCE(ecole_id,0)=?", (H.eco(),), ecole_code(H.eco())

    def bureaux_ecrire(d, code):
        d["ecole_id"] = None if juridiction() else H.eco()
        return d

    def adopter_bureau(d):
        r = q("SELECT b.id FROM uascep_bureaux b LEFT JOIN sync_ids s ON s.type='uascep_bureaux' AND s.local_id=b.id "
              "WHERE COALESCE(b.ecole_id,0)=COALESCE(?,0) AND b.niveau=? AND b.entite=? AND b.statut='actif' AND s.uuid IS NULL",
              (d.get("ecole_id"), d.get("niveau"), d.get("entite")), un=True)
        return r["id"] if r else None

    type_table("uascep_bureaux", "uascep_bureaux", exclure=("ecole_id",), scope_sql=scope_bureaux, avant_ecriture=bureaux_ecrire,
               cle_adoption=lambda d: adopter_bureau(d))

    def scope_lie(table_parent, col, scope_parent):
        def f(cible):
            w, a, code = scope_parent(cible)
            return f"{col} IN (SELECT id FROM {table_parent} WHERE {w})", a, code
        return f

    def sans_images(d, r):
        return {k: v for k, v in d.items() if k not in ("signature", "cachet_image", "cachetImage", "signature_image", "photo")}

    type_table("uascep_membres", "uascep_membres", scope_sql=scope_lie("uascep_bureaux", "bureau_id", scope_bureaux),
               lien=("bureau_id", "uascep_bureaux", "bureau"), apres_lecture=sans_images)
    try:
        import m_uascep as MU
        for coll in MU.COLL:
            type_table(f"uascep_vie:{coll}", f"uascep_{coll}", scope_sql=scope_lie("uascep_bureaux", "bureau_id", scope_bureaux),
                       lien=("bureau_id", "uascep_bureaux", "bureau"))
    except Exception:  # noqa: BLE001
        pass
    type_table("uascep_rapports", "uascep_rapports", scope_sql=scope_lie("uascep_bureaux", "bureau_id", scope_bureaux),
               lien=("bureau_id", "uascep_bureaux", "bureau"))

    # ---- examen blanc commun
    def scope_eb(cible):
        if juridiction():
            return "portee=0", (), None
        return "portee=?", (-H.eco(),), ecole_code(H.eco())

    def eb_ecrire(d, code):
        d["portee"] = 0 if juridiction() else -H.eco()
        return d

    type_table("eb_centres", "eb_centres", exclure=("portee",), scope_sql=scope_eb, avant_ecriture=eb_ecrire)
    type_table("eb_candidats", "eb_candidats", scope_sql=scope_lie("eb_centres", "centre_id", scope_eb), lien=("centre_id", "eb_centres", "centre"))

    # ---- registres (champs de l'Excel commun ; identifiants d'élèves et d'utilisateurs retirés)
    def type_registre(g_, r_, sens, nom=None):
        table = f"reg_{g_}_{r_}"
        champs_eleve = set()
        try:
            import registres as RG
            reg = RG.GROUPES[g_].registres[r_]
            champs_eleve = {k for k, _l, t in reg.champs if t == "eleve"}
        except Exception:  # noqa: BLE001
            pass

        def scope(cible):
            if cible == "descendant":
                return "portee=0", (), None
            if not juridiction() and (g_, r_) in REG_AUSSI_DESCENDANT:      # copie reçue de la CS : ne remonte pas
                return "0=1", (), ecole_code(H.eco())
            if juridiction():
                return "1=1", (), (lambda r: code_de_portee(r["portee"]))
            return "portee IN (?, ?)", (H.eco(), -H.eco()), ecole_code(H.eco())

        def ecrire(d, code):
            # v2.3.1 : ligne d'école échangée comme dans les applications JS — « entite » = code de l'école, « _ecoleNom » = son nom ;
            # rangée ici sous le nom de l'école (nom de la juridiction quand le code est connu)
            nom_ec = d.pop("_ecoleNom", None)
            if (d.get("niveau") or "") == "ECOLE" and (nom_ec or d.get("entite")):
                cd = str(d.get("entite") or code or "")
                trouve = None
                if juridiction() and cd and table_existe("jur_ecoles"):
                    x = q("SELECT nom FROM jur_ecoles WHERE code=?", (cd.replace("NOM:", ""),), un=True)
                    trouve = x["nom"] if x else None
                d["entite"] = trouve or nom_ec or d.get("entite")
            if juridiction():
                d["portee"] = portee_de_code(code) if code else 0
            else:
                d["portee"] = -H.eco()
            return d

        def lecture(d, r):
            d = {k: v for k, v in d.items() if k not in champs_eleve}
            if (d.get("niveau") or "") == "ECOLE" and d.get("entite"):
                try:
                    cd = code_de_portee(r["portee"]) if juridiction() else ecole_code(H.eco())
                except Exception:  # noqa: BLE001
                    cd = None
                if cd:
                    d["_ecoleNom"], d["entite"] = d["entite"], cd
            return d

        nom = nom or f"reg:{g_}:{r_}"
        type_table(nom, table, exclure=("portee", "cree_par") + tuple(champs_eleve), scope_sql=scope, avant_ecriture=ecrire,
                   apres_lecture=lecture)
        TYPES[nom]["sens"] = sens

    for g_, r_ in REG_MONTANT:
        type_registre(g_, r_, "montant")
    for g_, r_ in REG_DESCENDANT:
        type_registre(g_, r_, "descendant")
    for g_, r_ in REG_AUSSI_DESCENDANT:
        type_registre(g_, r_, "descendant", nom=f"reg:{g_}:{r_}@bas")

    # ---- versions proposées (épreuves, fiches, résumés)
    def scope_versions(cible):
        if juridiction() or cible == "descendant":
            return "proposee=1", (), (lambda r: code_de_portee(r["ecole_id"]) if r["ecole_id"] else None)
        return "proposee=1 AND ecole_id=?", (H.eco(),), ecole_code(H.eco())

    def versions_lecture(d, r):
        out = {k: d.get(k) for k in ("type", "cle", "titre", "auteur_nom", "cree_le", "note", "origine")}
        try:
            out["contenu"] = json.loads(r["donnees"])
        except ValueError:
            out["contenu"] = r["donnees"]
        return out

    def versions_ecrire(d, code):
        c = d.pop("contenu", None)
        d["donnees"] = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False, sort_keys=True)
        d["ecole_id"] = (portee_de_code(code) if code else 0) if juridiction() else H.eco()
        d["proposee"] = 0
        d.setdefault("cree_le", H.maintenant())
        d["maj"] = H.maintenant()
        if not d.get("uuid"):
            d["uuid"] = str(_uuid.uuid4())
        return d

    type_table("version", "partage_versions", exclure=("ecole_id", "auteur_id", "proposee", "proposee_le", "maj", "uuid", "donnees"),
               scope_sql=scope_versions, apres_lecture=versions_lecture, avant_ecriture=versions_ecrire)
    # la colonne « donnees » est exclue de la lecture (remplacée par « contenu ») mais doit être écrite
    _ecrire_v = TYPES["version"]["ecrire"]

    def ecrire_version(lid, d, liens, code):
        d2 = versions_ecrire(dict(d), code)
        d2["origine"] = d.get("_origine_lib") or d.get("origine") or "reçue"
        d2.pop("_origine_lib", None)
        cols_ = set(colonnes("partage_versions"))
        d2 = {k: v for k, v in d2.items() if k in cols_ and k != "id"}
        if lid:
            d2.pop("proposee", None)
            ex(f"UPDATE partage_versions SET {', '.join(k + '=?' for k in d2)} WHERE id=?", tuple(d2.values()) + (lid,))
            return lid
        return ex(f"INSERT INTO partage_versions ({', '.join(d2)}) VALUES ({','.join('?' * len(d2))})", tuple(d2.values()))
    TYPES["version"]["ecrire"] = ecrire_version

    ORDRE = (["uascep_bureaux", "uascep_membres"] + [t for t in TYPES if t.startswith("uascep_vie:")] + ["uascep_rapports", "eb_centres",
             "eb_candidats"] + [f"reg:{a}:{b}" for a, b in REG_DESCENDANT + REG_MONTANT] + [f"reg:{a}:{b}@bas" for a, b in REG_AUSSI_DESCENDANT]
             + ["version"])
    MONTANT = [t for t in ORDRE if not (t.startswith("reg:") and TYPES[t].get("sens") == "descendant")]
    DESCENDANT = [f"reg:{a}:{b}" for a, b in REG_DESCENDANT] + [f"reg:{a}:{b}@bas" for a, b in REG_AUSSI_DESCENDANT] + ["version"]

    # ================================================================== correspondances uuid
    def uuid_de(typ, lid):
        r = q("SELECT uuid FROM sync_ids WHERE type=? AND local_id=?", (typ, lid), un=True)
        if r:
            return r["uuid"]
        u = str(_uuid.uuid4())
        ex("INSERT INTO sync_ids (type, local_id, uuid, scope, origine, maj) VALUES (?,?,?,?,?,?)", (typ, lid, u, scope_client(), "local", H.maintenant()))
        return u

    def local_de(typ, u):
        if not u:
            return None
        r = q("SELECT local_id FROM sync_ids WHERE type=? AND uuid=? AND supprime=0", (typ, u), un=True)
        return r["local_id"] if r else None

    def empreinte(d, liens, code):
        return SC.sha256_hex({"d": d, "l": liens or {}, "e": code})

    def balayer(types, cible, scope):
        """Attribue un nouveau seq aux objets nouveaux ou modifiés, des tombes aux objets disparus (dans le périmètre)."""
        for typ in types:
            T = TYPES[typ]
            vus = set()
            for lid, d, liens, code in T["lister"](cible):
                vus.add(lid)
                emp = empreinte(d, liens, code)
                r = q("SELECT * FROM sync_ids WHERE type=? AND local_id=?", (typ, lid), un=True)
                if not r:
                    ex("INSERT INTO sync_ids (type, local_id, uuid, scope, empreinte, seq, origine, maj) VALUES (?,?,?,?,?,?,?,?)",
                       (typ, lid, str(_uuid.uuid4()), scope, emp, prochain_seq(), "local", H.maintenant()))
                elif r["empreinte"] != emp or r["supprime"]:
                    ex("UPDATE sync_ids SET empreinte=?, seq=?, supprime=0, scope=?, maj=? WHERE type=? AND local_id=?",
                       (emp, prochain_seq(), scope if r["origine"] == "local" else r["scope"], H.maintenant(), typ, lid))
            for r in q("SELECT * FROM sync_ids WHERE type=? AND scope=? AND supprime=0", (typ, scope)):
                if r["local_id"] not in vus and not T["lire"](r["local_id"]):
                    ex("UPDATE sync_ids SET supprime=1, seq=?, maj=? WHERE type=? AND local_id=?", (prochain_seq(), H.maintenant(), typ, r["local_id"]))

    def objets_depuis(types, cible, scope, depuis, exclure_origine=None, inclure_scope_libre=False):
        out = []
        ph = ",".join("?" * len(types))
        sql = f"SELECT * FROM sync_ids WHERE type IN ({ph}) AND seq>?"
        args = list(types) + [depuis]
        if not inclure_scope_libre:
            sql += " AND scope=?"
            args.append(scope)
        if exclure_origine:
            sql += " AND origine<>?"
            args.append(exclure_origine)
        listes = {}
        for r in q(sql + " ORDER BY seq", tuple(args)):
            typ = r["type"]
            if r["supprime"]:
                out.append({"type": typ, "uuid": r["uuid"], "seq": r["seq"], "maj": r["maj"], "supprime": True, "ecole": None, "donnees": {}, "liens": {}})
                continue
            if typ not in listes:
                listes[typ] = {lid: (d, liens, code) for lid, d, liens, code in TYPES[typ]["lister"](cible)}
            x = listes[typ].get(r["local_id"])
            if not x:
                continue
            d, liens, code = x
            out.append({"type": typ, "uuid": r["uuid"], "seq": r["seq"], "maj": r["maj"], "supprime": False, "ecole": code,
                        "donnees": json.loads(json.dumps(d, default=str)), "liens": liens})
        rang = {t: i for i, t in enumerate(ORDRE)}
        out.sort(key=lambda o: (rang.get(o["type"], 99), o["seq"]))
        return out

    # ================================================================== application des objets reçus
    def appliquer(objets, source, niveau_source, eid_conflit):
        """Applique les objets d'un paquet. Renvoie (nb appliqués, nb conflits, messages)."""
        n, nconf, msgs = 0, 0, []
        rang = {t: i for i, t in enumerate(ORDRE)}
        for o in sorted(objets, key=lambda o: (rang.get(o.get("type"), 99), o.get("seq") or 0)):
            typ = o.get("type")
            if typ not in TYPES:
                msgs.append(f"Type inconnu ignoré : {typ}.")
                continue
            T = TYPES[typ]
            u = str(o.get("uuid") or "")[:64]
            if not u:
                continue
            r = q("SELECT * FROM sync_ids WHERE type=? AND uuid=?", (typ, u), un=True)
            if r and r["origine"] == "local":
                continue                            # notre propre objet revenu (relais) : le propriétaire l'emporte
            try:
                if o.get("supprime"):
                    if r and not r["supprime"]:
                        T["supprimer"](r["local_id"])
                        ex("UPDATE sync_ids SET supprime=1, seq=?, maj=? WHERE type=? AND uuid=?", (prochain_seq(), H.maintenant(), typ, u))
                        n += 1
                    continue
                d = dict(o.get("donnees") or {})
                if typ == "version":
                    d["_origine_lib"] = f"{niveau_source} {source[1]}".strip()
                liens, code = o.get("liens") or {}, o.get("ecole")
                if r and not r["supprime"] and T["lire"](r["local_id"]) is not None:
                    actuel = T["lire"](r["local_id"])
                    base = json.loads(r["base"]) if r["base"] else None
                    if base is not None and typ != "version":
                        fusion = {}
                        for k, v in d.items():
                            loc = actuel.get(k)
                            if base.get(k) != loc and base.get(k) != v and loc != v:
                                gagne_recu = RANG.get(niveau_source, 0) > RANG.get(niveau_local(), 0)
                                retenu = v if gagne_recu else loc
                                ex("INSERT INTO sync_conflits (quand, ecole_id, type, uuid, local_id, champ, valeur_locale, valeur_recue, retenue, source) "
                                   "VALUES (?,?,?,?,?,?,?,?,?,?)", (H.maintenant(), eid_conflit, typ, u, r["local_id"], k, str(loc)[:500], str(v)[:500],
                                                                   "reçue" if gagne_recu else "locale", source[1]))
                                nconf += 1
                                fusion[k] = retenu
                            elif base.get(k) != loc and base.get(k) == v:
                                fusion[k] = loc                 # modifié ici seulement : on garde
                            else:
                                fusion[k] = v
                        d = fusion
                    lid = T["ecrire"](r["local_id"], d, liens, code)
                else:
                    lid = T["ecrire"](None, d, liens, code)
                cour = T["lire"](lid) or {}
                emp = empreinte(cour, liens, code)
                base_txt = json.dumps(cour, default=str, sort_keys=True)
                if r:
                    ex("UPDATE sync_ids SET local_id=?, empreinte=?, seq=?, base=?, supprime=0, maj=? WHERE type=? AND uuid=?",
                       (lid, emp, prochain_seq(), base_txt, H.maintenant(), typ, u))
                else:
                    ex("DELETE FROM sync_ids WHERE type=? AND local_id=?", (typ, lid))     # objet adopté (même entité, même niveau)
                    ex("INSERT INTO sync_ids (type, local_id, uuid, scope, empreinte, seq, origine, base, maj) VALUES (?,?,?,?,?,?,?,?,?)",
                       (typ, lid, u, scope_client() if source[0] == "hub" else 0, emp, prochain_seq(),
                        "hub" if source[0] == "hub" else f"src:{source[2]}", base_txt, H.maintenant()))
                n += 1
            except PaquetRefuse as e:
                msgs.append(f"{LIBELLES.get(typ, typ)} : {e}")
            except Exception as e:  # noqa: BLE001
                app.logger.exception("Synchronisation : objet %s", typ)
                msgs.append(f"{LIBELLES.get(typ, typ)} : {type(e).__name__}")
        return n, nconf, msgs

    def niveau_local():
        return niveau_hub() if juridiction() else "ECOLE"

    # ================================================================== client
    def client_etat():
        sc = scope_client()
        r = q("SELECT * FROM sync_client WHERE ecole_id=?", (sc,), un=True)
        if not r:
            # reprise des réglages de la transmission (adresse et code d'accès de la CS / de la DDEMP)
            try:
                reg = H.doc_lire("jur:transmission:ddemp" if juridiction() else f"e{H.eco()}:transmission:reglages", None) or {}
            except Exception:  # noqa: BLE001
                reg = {}
            ex("INSERT OR IGNORE INTO sync_client (ecole_id, adresse, code) VALUES (?,?,?)", (sc, reg.get("adresse") or "", reg.get("code_acces") or ""))
            r = q("SELECT * FROM sync_client WHERE ecole_id=?", (sc,), un=True)
        return dict(r)

    def client_maj(**k):
        ex(f"UPDATE sync_client SET {', '.join(c + '=?' for c in k)} WHERE ecole_id=?", tuple(k.values()) + (scope_client(),))

    def transmission_courante():
        try:
            if juridiction():
                return H.jur_exporter_paquet_cs() if config.EDITION == "cs" else None
            return H.transmission_paquet() if hasattr(H, "transmission_paquet") else None
        except Exception as e:  # noqa: BLE001
            g.sync_note_transmission = str(e)
            return None

    def paquet_montant(complet=False, avec_transmission=True):
        if not est_client():
            abort(404)
        c = client_etat()
        sc = scope_client()
        balayer(MONTANT, "montant", sc)
        depuis = 0 if complet else c["accuse_seq"]
        objets = objets_depuis(MONTANT, "montant", sc, depuis, exclure_origine="hub")
        p = {"format": FORMAT, "v": V, "id": str(_uuid.uuid4()), "cree_le": maintenant_iso(), "sens": "montant", "emetteur": emetteur(),
             "destinataire": {"niveau": c.get("hub_niveau") or ("DDEMP" if juridiction() else "CS"), "nom": c.get("hub_nom") or ""},
             "curseur": {"de": depuis + 1, "a": max([o["seq"] for o in objets] + [depuis]), "complet": bool(complet)},
             "accuse": {"paquet": c.get("dernier_paquet_recu"), "seq": c["desc_seq"]}, "objets": objets}
        if avec_transmission:
            t = transmission_courante()
            if t:
                p["transmission"] = t
        return SC.signer(p)

    def client_recevoir(p, mode):
        """Applique un paquet descendant du hub (fichier ou réponse de /sync/pull)."""
        if p["sens"] != "descendant":
            raise PaquetRefuse("Ce paquet est destiné au niveau supérieur, pas à cet appareil.")
        c = client_etat()
        em = p["emetteur"]
        if c.get("hub_cle") and c["hub_cle"] != em.get("cle"):
            raise PaquetRefuse("Ce paquet est signé par une autre clé que celle de votre circonscription / DDEMP : refusé. "
                               "Si votre CS a changé d'appareil, effacez la clé du hub dans les réglages.", 409)
        attendu = "DDEMP" if juridiction() else "CS"
        if em.get("niveau") != attendu:
            raise PaquetRefuse(f"Ce paquet vient d'un niveau « {em.get('niveau')} » : attendu « {attendu} ».")
        n, nconf, msgs = appliquer(p["objets"], ("hub", em.get("nom") or "", "hub"), em.get("niveau") or attendu, scope_client())
        acc = p.get("accuse") or {}
        maj = {"hub_cle": em.get("cle"), "hub_nom": em.get("nom") or "", "hub_niveau": em.get("niveau"), "dernier_paquet_recu": p["id"],
               "derniere_reception": H.maintenant(), "desc_seq": max(c["desc_seq"], int((p.get("curseur") or {}).get("a") or 0))}
        if acc.get("seq") is not None:
            maj["accuse_seq"] = max(c["accuse_seq"], int(acc.get("seq") or 0))
        client_maj(**maj)
        msg = f"{n} élément(s) reçu(s) de {em.get('nom') or 'la structure'}" + (f", {nconf} conflit(s) à revoir" if nconf else "") + "."
        if msgs:
            msg += " " + " ".join(msgs[:5])
        historiser("descendant", mode, p["id"], em.get("nom"), n, "ok", msg)
        return n, nconf, msg

    def client_synchroniser(complet=False):
        c = client_etat()
        adr = MT.normaliser_adresse(c.get("adresse") or "")
        if not adr or not c.get("code"):
            return False, "Rejoignez d'abord votre circonscription (adresse et code d'accès), ou passez par les fichiers."
        p = paquet_montant(complet)
        octets = vers_octets(p)
        try:
            with ouvrir(adr + "/sync/push", octets, {"Content-Type": "application/gzip", "X-Sync-Code": c["code"].strip(), "X-Gescol-Code": c["code"].strip(),
                                                    "Accept": "application/json"}, "POST") as r:
                rep = json.loads(r.read(2_000_000).decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                rep = json.loads(e.read(100_000).decode("utf-8"))
            except Exception:  # noqa: BLE001
                rep = {}
            msg = rep.get("message") or f"Erreur {e.code} du serveur."
            client_maj(dernier_message=msg)
            historiser("montant", "en_ligne", p["id"], adr, len(p["objets"]), "erreur", msg)
            return False, msg
        except (urllib.error.URLError, OSError, ValueError) as e:
            msg = f"Connexion impossible avec {adr} ({getattr(e, 'reason', e)}). Vérifiez Internet ou passez par le fichier."
            client_maj(dernier_message=msg)
            historiser("montant", "en_ligne", p["id"], adr, len(p["objets"]), "erreur", msg)
            return False, msg
        if not rep.get("ok"):
            msg = rep.get("message") or "Paquet refusé."
            client_maj(dernier_message=msg)
            historiser("montant", "en_ligne", p["id"], adr, len(p["objets"]), "erreur", msg)
            return False, msg
        acc = rep.get("accuse") or {}
        client_maj(accuse_seq=max(c["accuse_seq"], int(acc.get("seq") or 0)), dernier_envoi=H.maintenant(), dernier_message=rep.get("message") or "")
        historiser("montant", "en_ligne", p["id"], adr, len(p["objets"]), "ok", rep.get("message") or "")
        # descendant
        try:
            with ouvrir(adr + f"/sync/pull?depuis={client_etat()['desc_seq']}", None, {"X-Sync-Code": c["code"].strip(), "X-Gescol-Code": c["code"].strip()}) as r:
                pd = lire_octets(r.read(TAILLE_MAX + 1))
            _n, _c, msg2 = client_recevoir(pd, "en_ligne")
        except (urllib.error.URLError, OSError) as e:
            msg2 = f"réception impossible ({getattr(e, 'reason', e)})"
        except PaquetRefuse as e:
            msg2 = f"réception refusée : {e}"
        msg = f"Envoyé : {rep.get('message') or 'ok'} Reçu : {msg2}"
        client_maj(dernier_message=msg[:500])
        return True, msg

    # ================================================================== hub
    def sources_candidats():
        if config.EDITION == "cs":
            return [("ecole", r["id"], r["nom"], r["code"], r["jeton"]) for r in q("SELECT id, nom, code, jeton FROM jur_ecoles WHERE actif=1")]
        return [("cs", r["id"], r["nom"], H.jur_norm(r["nom"]), r["jeton"]) for r in q("SELECT id, nom, jeton FROM jur_cs")]

    def source_par_jeton(code):
        code = (code or "").strip().upper()
        trouve = None
        for kind, rid, nom, ecode, jeton in sources_candidats():
            if jeton and secrets.compare_digest(jeton.strip().upper().encode(), code.encode()):
                trouve = (kind, rid, nom, ecode)
        return trouve

    def source_par_emetteur(em):
        kind = "ecole" if config.EDITION == "cs" else "cs"
        if (em.get("niveau") or "") != ("ECOLE" if kind == "ecole" else "CS"):
            raise PaquetRefuse(f"Ce paquet vient d'un niveau « {em.get('niveau')} » : cette application reçoit les "
                               f"{'écoles' if kind == 'ecole' else 'circonscriptions'}.", 403)
        for k, rid, nom, ecode, _j in sources_candidats():
            if (k == "ecole" and ecode and ecode == em.get("code")) or (k == "cs" and H.jur_norm(nom) == H.jur_norm(em.get("nom") or "")):
                return (k, rid, nom, ecode)
        return None

    def source_ligne(src):
        kind, rid, nom, ecode = src
        cle = f"{kind}:{rid}"
        ex("INSERT OR IGNORE INTO sync_sources (cle, kind, ref_id, nom, code) VALUES (?,?,?,?,?)", (cle, kind, rid, nom, ecode))
        return dict(q("SELECT * FROM sync_sources WHERE cle=?", (cle,), un=True))

    def hub_recevoir(p, src, mode, taille):
        if not est_hub():
            raise PaquetRefuse("Cette application ne reçoit pas de paquets de synchronisation.", 404)
        if p["sens"] != "montant":
            raise PaquetRefuse("Ce paquet est un paquet descendant : il s'importe dans l'application d'une école ou d'une CS.")
        em = p["emetteur"]
        attendu = "ECOLE" if config.EDITION == "cs" else "CS"
        if em.get("niveau") != attendu:
            raise PaquetRefuse(f"Ce paquet vient d'un niveau « {em.get('niveau')} » : attendu « {attendu} ».", 403)
        S = source_ligne(src)
        if src[0] == "ecole" and src[3] and em.get("code") and em.get("code") != src[3]:
            raise PaquetRefuse(f"Ce code d'accès est celui de l'école {src[2]} : le paquet vient d'une autre école ({em.get('nom')}).", 403)
        if S["cle_publique"] and S["cle_publique"] != em.get("cle"):
            ex("UPDATE sync_sources SET cle_attente=?, dernier_message=? WHERE cle=?",
               (em.get("cle"), "Paquet signé par une nouvelle clé : à accepter si l'entité a changé d'appareil.", S["cle"]))
            raise PaquetRefuse("Ce paquet est signé par une autre clé que celle enregistrée pour cette entité (changement d'appareil ?) : "
                               "la circonscription doit accepter la nouvelle clé dans « Synchronisation › Entités ».", 409)
        if not S["cle_publique"]:
            ex("UPDATE sync_sources SET cle_publique=?, installation=? WHERE cle=?", (em.get("cle"), em.get("installation"), S["cle"]))
        res_t, note_t = None, ""
        if p.get("transmission"):
            try:
                tp = p["transmission"]                  # contrôlé (empreinte, format) par jur_importer_paquet
                libres, cr_pobe = {}, None
                if JP.est_paquet_pobe(tp):              # paquet d'école de « Mon école » (CS Pobè) : converti ici
                    if src[0] != "ecole":
                        raise PaquetRefuse("Un paquet d'école Mon école ne peut venir que d'une école.", 403)
                    st = H.jur_structure() or {}
                    tp, libres, cr_pobe = JP.convertir(tp, src[3] or em.get("code") or "", src[2] or em.get("nom") or "",
                                                       st.get("departement") or "", st.get("cs") or "")
                if src[0] == "ecole":
                    code_p = ((tp.get("ecoles") or [{}])[0].get("ecole") or {}).get("code", "").strip()
                    if code_p and src[3] and code_p != src[3]:
                        raise PaquetRefuse("La transmission jointe vient d'une autre école.", 403)
                res_t = H.jur_importer_paquet(tp, "sync", f"synchronisation ({mode})", taille)
                note_t = f" Transmission : {res_t.get('sections', 0)} rubrique(s)."
                if cr_pobe is not None:
                    r_e = q("SELECT id FROM jur_ecoles WHERE code=?", (tp["ecoles"][0]["ecole"]["code"],), un=True)
                    eid = r_e["id"] if r_e else src[1]
                    for nom_l, d_l in libres.items():
                        if eid:
                            H.jur_ecrire_section(eid, nom_l, d_l, tp["annee"], source="sync")
                    if eid:
                        H.jur_ecrire_section(eid, "import_mon_ecole", dict(cr_pobe, recu_le=H.maintenant()), tp["annee"], source="sync")
                    note_t = f" Paquet Mon école converti — {JP.resume(cr_pobe)}."
            except PaquetRefuse:
                raise
            except Exception as e:  # noqa: BLE001
                note_t = f" Transmission non reprise : {e}."
        acc = p.get("accuse") or {}
        n, nconf, msgs = appliquer(p["objets"], (src[0], src[2], f"{src[0]}:{src[1]}"), em.get("niveau"), 0)
        a = int((p.get("curseur") or {}).get("a") or 0)
        ex("UPDATE sync_sources SET accuse_seq=?, dernier_paquet=?, desc_accuse=?, derniere_reception=?, nb_objets=nb_objets+?, dernier_message=?, nom=? WHERE cle=?",
           (max(S["accuse_seq"], a), p["id"], max(S["desc_accuse"], int(acc.get("seq") or 0)), H.maintenant(), n,
            (f"{n} élément(s), {nconf} conflit(s)." + note_t)[:500], src[2], S["cle"]))
        if src[0] == "ecole":
            try:
                ex("UPDATE jur_ecoles SET derniere_transmission=? WHERE id=?", (H.maintenant(), src[1]))
            except Exception:  # noqa: BLE001
                pass
        msg = f"{n} élément(s) reçu(s) de {src[2]}" + (f", {nconf} conflit(s) à revoir" if nconf else "") + "." + note_t
        if msgs:
            msg += " " + " ".join(msgs[:5])
        historiser("montant", mode, p["id"], src[2], n, "ok", msg, eid=0)
        H.journal("sync_reception", msg[:200])
        return {"ok": True, "message": msg, "accuse": {"paquet": p["id"], "seq": max(S["accuse_seq"], a)}, "conflits": nconf, "objets": n}

    def paquet_descendant(src, depuis=None):
        S = source_ligne(src)
        balayer(DESCENDANT, "descendant", 0)
        dep = S["desc_accuse"] if depuis is None else int(depuis)
        objets = objets_depuis(DESCENDANT, "descendant", 0, dep, inclure_scope_libre=True)
        objets = [o for o in objets if not (o["type"] == "version" and q("SELECT 1 FROM sync_ids WHERE type='version' AND uuid=? AND origine=?",
                                                                          (o["uuid"], f"src:{S['cle']}"), un=True))]
        kind = src[0]
        p = {"format": FORMAT, "v": V, "id": str(_uuid.uuid4()), "cree_le": maintenant_iso(), "sens": "descendant", "emetteur": emetteur(),
             "destinataire": {"niveau": "ECOLE" if kind == "ecole" else "CS", "code": src[3], "nom": src[2]},
             "curseur": {"de": dep + 1, "a": max([o["seq"] for o in objets] + [dep]), "complet": dep == 0},
             "accuse": {"paquet": S["dernier_paquet"], "seq": S["accuse_seq"]}, "objets": objets}
        return SC.signer(p)

    def code_requete():
        """Code d'accès : en-tête commun X-Sync-Code (toutes les applications) ou X-Gescol-Code (transmission)."""
        return request.headers.get("X-Sync-Code") or request.headers.get("X-Gescol-Code")

    def refus_json(code, message, compter=True):
        if compter:
            ip = request.remote_addr or "?"
            with _VERROU:
                _echecs.setdefault(ip, []).append(time.time())
        return jsonify(ok=False, message=message), code

    def trop_essais():
        ip = request.remote_addr or "?"
        with _VERROU:
            l = [t for t in _echecs.get(ip, []) if time.time() - t < 3600]
            _echecs[ip] = l
            return len(l) >= 20

    # ================================================================== API HTTP
    # CORS limité aux routes /sync/* : les applications JS (pages github.io, APK) appellent le hub depuis une autre origine ;
    # l'authentification reste le code d'accès + la signature des paquets (aucun cookie n'est accepté ici).
    CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-Sync-Code, X-Gescol-Code, X-Gescol-Code", "Access-Control-Max-Age": "86400"}

    @app.before_request
    def sync_preflight():
        if request.method == "OPTIONS" and request.path.startswith("/sync/"):
            r = Response("", status=204)
            r.headers.update(CORS)
            return r
        return None

    @app.after_request
    def sync_cors(r):
        if request.path.startswith("/sync/"):
            r.headers.update(CORS)
        return r

    @app.route("/sync/info")
    def sync_info():
        if not est_hub():
            return jsonify(ok=False, message="Cette application n'est pas un hub de synchronisation."), 404
        em = emetteur()
        return jsonify(ok=True, application=em["application"], version=config.VERSION, niveau=em["niveau"], nom=em["nom"], cle=em["cle"])

    @app.route("/sync/push", methods=["POST"])
    def sync_push():
        if not est_hub():
            return jsonify(ok=False, message="Cette application ne reçoit pas de paquets de synchronisation."), 404
        if trop_essais():
            return jsonify(ok=False, message="Trop d'essais refusés : réessayez dans une heure."), 429
        if (request.content_length or 0) > TAILLE_MAX:
            return refus_json(413, "Paquet trop volumineux (15 Mo au maximum) : passez par le fichier.", False)
        src = source_par_jeton(code_requete())
        if not src:
            return refus_json(403, "Code d'accès incorrect ou désactivé : demandez un nouveau code à la circonscription.")
        octets = request.get_data(cache=False)
        try:
            p = lire_octets(octets)
            rep = hub_recevoir(p, src, "en_ligne", len(octets))
        except PaquetRefuse as e:
            return refus_json(e.code, str(e), e.code in (401, 403))
        return jsonify(rep), 200

    @app.route("/sync/pull")
    def sync_pull():
        if not est_hub():
            return jsonify(ok=False, message="Cette application n'est pas un hub de synchronisation."), 404
        if trop_essais():
            return jsonify(ok=False, message="Trop d'essais refusés : réessayez dans une heure."), 429
        src = source_par_jeton(code_requete())
        if not src:
            return refus_json(403, "Code d'accès incorrect ou désactivé.")
        depuis = request.args.get("depuis", type=int)
        p = paquet_descendant(src, depuis)
        ex("UPDATE sync_sources SET desc_accuse=MAX(desc_accuse, ?) WHERE cle=?", (depuis or 0, f"{src[0]}:{src[1]}"))
        historiser("descendant", "en_ligne", p["id"], src[2], len(p["objets"]), "ok", f"{len(p['objets'])} élément(s) envoyé(s).", eid=0)
        return Response(vers_octets(p), mimetype="application/gzip")

    # ================================================================== pages
    def exiger():
        if not H.peut("synchronisation"):
            abort(403)

    @app.route("/synchronisation", methods=["GET", "POST"])
    @H.connexion_requise("synchronisation")
    def sync_page():
        if request.method == "POST":
            act = request.form.get("action")
            if act == "rejoindre" and est_client():
                lien = lire_lien(request.form.get("lien"))
                adr = MT.normaliser_adresse((lien or {}).get("adresse") or request.form.get("adresse") or "")
                code = ((lien or {}).get("code") or request.form.get("code") or "").strip()[:80]
                if adr and not re.match(r"^https?://[\w.\-]+(:\d{1,5})?(/[\w.\-/~%]*)?$", adr):
                    flash("Adresse invalide (exemple : https://cs-pobe.gescol.bj).", "danger")
                    return redirect(url_for("sync_page"))
                client_etat()
                client_maj(adresse=adr, code=code)
                try:   # même réglage que la transmission
                    cle = "jur:transmission:ddemp" if juridiction() else f"e{H.eco()}:transmission:reglages"
                    reg = H.doc_lire(cle, None) or {}
                    reg.update({"adresse": adr, "code_acces": code})
                    H.doc_ecrire(cle, reg)
                except Exception:  # noqa: BLE001
                    pass
                H.journal("sync_rejoindre", adr)
                flash("Réglages enregistrés : « Synchroniser maintenant » envoie et reçoit les données.", "success")
            elif act == "oublier_cle" and est_client():
                client_maj(hub_cle=None)
                flash("Clé du niveau supérieur effacée : elle sera reprise au prochain paquet reçu.", "warning")
            elif act == "synchroniser" and est_client():
                ok, msg = client_synchroniser(bool(request.form.get("complet")))
                flash(msg, "success" if ok else "danger")
            elif act == "importer":
                f = request.files.get("fichier")
                try:
                    if not f or not f.filename:
                        raise PaquetRefuse("Choisissez un fichier .scsync.")
                    octets = f.read(TAILLE_MAX + 1)
                    p = lire_octets(octets)
                    if p["sens"] == "descendant":
                        if not est_client():
                            raise PaquetRefuse("Ce paquet est destiné à une école ou une CS.")
                        _n, _c, msg = client_recevoir(p, "fichier")
                    else:
                        src = source_par_emetteur(p["emetteur"]) if est_hub() else None
                        if not src:
                            raise PaquetRefuse("Émetteur inconnu : inscrivez d'abord cette école (ou cette CS) dans vos entités.")
                        msg = hub_recevoir(p, src, "fichier", len(octets))["message"]
                    flash(msg, "success")
                except PaquetRefuse as e:
                    historiser("?", "fichier", None, f.filename if f else "", 0, "erreur", str(e))
                    flash(f"Fichier refusé : {e}", "danger")
            elif act == "conflit":
                cid = request.form.get("cid", type=int)
                c = q("SELECT * FROM sync_conflits WHERE id=?", (cid,), un=True)
                if c and request.form.get("garder") in ("locale", "recue"):
                    garder = request.form["garder"]
                    T = TYPES.get(c["type"])
                    if T and garder != c["retenue"].replace("reçue", "recue"):
                        val = c["valeur_locale"] if garder == "locale" else c["valeur_recue"]
                        tbl = T["table"]
                        if c["champ"] in colonnes(tbl):
                            ex(f"UPDATE {tbl} SET {c['champ']}=? WHERE id=?", (None if val == "None" else val, c["local_id"]))
                    ex("UPDATE sync_conflits SET resolu=1, retenue=? WHERE id=?", ("locale" if garder == "locale" else "reçue", cid))
                    flash("Conflit réglé.", "success")
            return redirect(url_for("sync_page"))
        c = client_etat() if est_client() else None
        attente = {}
        if c is not None:
            balayer(MONTANT, "montant", scope_client())
            for r in q("SELECT type, COUNT(*) n FROM sync_ids WHERE scope=? AND seq>? AND origine<>'hub' GROUP BY type",
                       (scope_client(), c["accuse_seq"])):
                attente[LIBELLES.get(r["type"], r["type"])] = r["n"]
        hist = [dict(r) for r in q("SELECT * FROM sync_historique WHERE ecole_id IN (?, 0) ORDER BY id DESC LIMIT 40", (scope_client(),))]
        conflits = [dict(r) for r in q("SELECT * FROM sync_conflits WHERE resolu=0 ORDER BY id DESC LIMIT 100")]
        return render_template("sync.html", c=c, attente=attente, hist=hist, conflits=conflits, em=emetteur(), est_hub=est_hub(),
                               est_client=est_client(), LIBELLES=LIBELLES, note_t=g.get("sync_note_transmission"))

    @app.route("/synchronisation/fichier")
    @H.connexion_requise("synchronisation")
    def sync_fichier():
        p = paquet_montant(bool(request.args.get("complet")))
        em = p["emetteur"]
        nom = f"sync_{re.sub(r'[^A-Za-z0-9-]+', '_', em.get('code') or 'entite')}_{datetime.now():%Y%m%d-%H%M}.scsync"
        historiser("montant", "fichier", p["id"], nom, len(p["objets"]), "ok", f"Fichier préparé ({len(p['objets'])} élément(s)).")
        client_maj(dernier_envoi=H.maintenant())
        H.journal("sync_fichier", nom)
        return Response(vers_octets(p), mimetype="application/gzip", headers={"Content-Disposition": f"attachment; filename={nom}"})

    @app.route("/synchronisation/entites", methods=["GET", "POST"])
    @H.connexion_requise("synchronisation")
    def sync_entites():
        if not est_hub():
            abort(404)
        if request.method == "POST":
            cle = request.form.get("cle") or ""
            S = q("SELECT * FROM sync_sources WHERE cle=?", (cle,), un=True)
            if S and request.form.get("action") == "accepter_cle" and S["cle_attente"]:
                ex("UPDATE sync_sources SET cle_publique=cle_attente, cle_attente=NULL, dernier_message=? WHERE cle=?",
                   ("Nouvelle clé acceptée.", cle))
                H.journal("sync_nouvelle_cle", cle)
                flash(f"Nouvelle clé acceptée pour {S['nom']}.", "success")
            return redirect(url_for("sync_entites"))
        adr = (config.URL_PUBLIQUE or request.host_url).rstrip("/")
        lignes = []
        for kind, rid, nom, ecode, jeton in sources_candidats():
            S = q("SELECT * FROM sync_sources WHERE cle=?", (f"{kind}:{rid}",), un=True)
            lien = lien_inscription(adr, jeton, ecode, nom) if jeton else ""
            lignes.append({"kind": kind, "id": rid, "nom": nom, "code": ecode, "jeton": bool(jeton), "S": dict(S) if S else None,
                           "lien": lien, "qr": svg_qr(lien, 150) if lien and request.args.get("qr") == f"{kind}:{rid}" else None})
        return render_template("sync_entites.html", lignes=lignes, adresse=adr, em=emetteur(), qr_ouvert=request.args.get("qr"))

    @app.route("/synchronisation/descendant/<kind>/<int:rid>")
    @H.connexion_requise("synchronisation")
    def sync_descendant_fichier(kind, rid):
        if not est_hub():
            abort(404)
        src = next(((k, i, n, c) for k, i, n, c, _j in sources_candidats() if k == kind and i == rid), None)
        if not src:
            abort(404)
        p = paquet_descendant(src)
        nom = f"sync_vers_{re.sub(r'[^A-Za-z0-9-]+', '_', src[3] or src[2])}_{datetime.now():%Y%m%d-%H%M}.scsync"
        historiser("descendant", "fichier", p["id"], src[2], len(p["objets"]), "ok", f"Fichier descendant préparé ({len(p['objets'])} élément(s)).", eid=0)
        return Response(vers_octets(p), mimetype="application/gzip", headers={"Content-Disposition": f"attachment; filename={nom}"})

    # outils pour les autres modules et les tests
    H.sync_paquet_montant = paquet_montant
    H.sync_paquet_descendant = lambda kind, rid, depuis=None: paquet_descendant(
        next((k, i, n, c) for k, i, n, c, _j in sources_candidats() if k == kind and i == rid), depuis)
    H.sync_client_recevoir = client_recevoir
    H.sync_hub_recevoir = lambda p, mode="fichier": hub_recevoir(p, source_par_emetteur(p["emetteur"]), mode, 0)
    H.sync_synchroniser = client_synchroniser
    H.sync_types = TYPES
