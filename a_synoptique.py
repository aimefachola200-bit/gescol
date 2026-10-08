# -*- coding: utf-8 -*-
"""Tableau synoptique de la structure déconcentrée : circonscription scolaire (CS) ou direction départementale (DDEMP) (v1.6).

Demande du client : « ajouter le tableau synoptique de chaque CS et DDEMP », sur le modèle du tableau synoptique de
l'école (m_synoptique) mais pour la structure elle-même. Rubriques (onglets de la page /juridiction/synoptique) :

1. **Identité de la structure** (table `jur_synoptique_identite`, une seule ligne) :
   * CS : MEMP, DDEMP (département, nom du DDEMP), CS (nom, numéro, arrondissements, commune / ville), CCS (titre, nom
     et prénoms, grade, NIP, matricule, date de prise de fonction), année de création, adresse, BP, téléphone, e-mail ;
   * DDEMP : MEMP, département, DDEMP (titre, nom, grade, NIP, matricule, prise de fonction), année de création, adresse…
   Les nombres (zones pédagogiques, UP, écoles publiques / privées, EP / EM / EE, enseignants, agents, CS) sont CALCULÉS
   depuis le référentiel (jur_cs, jur_zones, jur_ecoles, jur_up, personnel transmis). Les valeurs connues de la structure
   (`jur_structure`, `jur_cs`) sont proposées par défaut ; à l'enregistrement, le titre et le nom du responsable,
   le téléphone, l'e-mail, l'adresse et la ville sont recopiés dans `jur_structure` (et, pour une CS, dans `jur_cs`)
   comme m_synoptique le fait pour la fiche école.
2. **Personnel de la structure** : agents de la CS / DDEMP (table `jur_agents`, colonnes + JSON `donnees`) avec les mêmes
   colonnes que le synoptique de l'école (matricule, NIP, nom et prénoms, promotion, catégorie, fonction / poste,
   service / division, grade, indices, anciennetés générale / département / structure, dates de prise de service,
   retraite, dernière formation, diplômes académique et professionnel, visite d'aptitude, note, contact). Les champs
   propres au synoptique (`promotion`, `date_derniere_formation`) sont rangés dans le JSON `donnees` (m_juridiction et
   a_personnel ne sont pas modifiés). Les anciennetés et la retraite sont calculées par m_carriere via a_personnel.fiche
   (jamais saisies) : anciennetés au 31/12 de la première année de l'année scolaire active, jour inclus ; retraite à
   60 ans (grade A), 58 ans (B), 55 ans (C), le 1er jour du trimestre qui suit le trimestre de naissance.
   Formulaire propre au synoptique (ajout / modification), retrait (actif = 0, fiche conservée), PDF paysage, Excel,
   import Excel (modèle téléchargeable).
3. **Réseau** : CS → zones pédagogiques (n°, nom, CP de zone, écoles, UP avec RUP et Co-RUP, enseignants) et écoles par
   zone (nom, type, secteur, directeur, téléphone, effectifs transmis) ; DDEMP → circonscriptions (n°, nom, CCS,
   téléphone, zones, UP, écoles, enseignants) puis zones et écoles.
4. **Divisions / services** : services actifs (`jur_services`) avec chef, sigle, article de l'AOF, nombre d'agents
   (données de a_divisions / a_structure, non modifiés).
5. **Comités / instances** (table `jur_synoptique_membres`) : conseil de direction (réunion des chefs de division),
   comité de gestion des cantines, jury / commission du CEP, autres instances (libellé libre) : membres (nom et prénoms,
   qualité, structure d'origine, contact, observations), PDF par comité.
6. **Import / export** : classeur Excel complet (feuilles Identité, Personnel, Zones ou Circonscriptions, UP, Écoles,
   Services, Comités), import des feuilles Personnel et Comités, modèle ; PDF complet paysage (en-tête DDEMP / CS,
   signature du responsable avec cachet et griffe de la structure).

Droits : lecture pour tout utilisateur connecté de la juridiction ; écriture avec le droit `jur_synoptique`
(admin, responsable, chef_service). Hors éditions cs / ddemp : 404. Chaque écriture est journalisée.
Exposé : H.jur_synoptique_identite() → dict de l'identité (valeurs + nombres calculés) ;
H.jur_synoptique_personnel() → fiches calculées des agents de la structure.
"""
import io
import json
import re
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

import a_personnel as AP
import config
import m_carriere as MC

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_synoptique_identite (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    memp TEXT, departement TEXT, ddemp_nom TEXT, cs_nom TEXT, cs_numero TEXT, arrondissements TEXT, commune TEXT,
    resp_titre TEXT, resp_nom TEXT, resp_grade TEXT, resp_nip TEXT, resp_matricule TEXT, resp_prise_fonction TEXT,
    annee_creation TEXT, adresse TEXT, bp TEXT, telephone TEXT, email TEXT,
    maj TEXT, maj_par INTEGER
);
CREATE TABLE IF NOT EXISTS jur_synoptique_membres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    annee TEXT,
    comite TEXT NOT NULL,                 -- conseil | cantine | cep | autre
    libelle TEXT,                         -- comité « autre » : intitulé de l'instance
    ordre INTEGER DEFAULT 0,
    nom_prenoms TEXT NOT NULL,
    qualite TEXT,
    origine TEXT,
    contact TEXT,
    observations TEXT,
    maj TEXT, maj_par INTEGER
);
CREATE INDEX IF NOT EXISTS i_jur_synoptique_membres ON jur_synoptique_membres (comite, ordre);
"""

MEMP_DEFAUT = "Ministère des Enseignements Maternel et Primaire"
# champs de l'identité : (clé, libellé, type) — type : texte | annee | date | grade | titre | tel
CHAMPS_IDENTITE = {
    "cs": [
        ("memp", "Nom du MEMP (ministère)", "texte"), ("departement", "Département (DDEMP)", "texte"),
        ("ddemp_nom", "Nom du DDEMP (directeur départemental)", "texte"),
        ("cs_nom", "Circonscription scolaire (nom)", "texte"), ("cs_numero", "N° de la circonscription", "texte"),
        ("arrondissements", "Arrondissements couverts", "texte"), ("commune", "Commune / ville", "texte"),
        ("resp_titre", "Titre du responsable (CCS)", "titre"), ("resp_nom", "Nom et prénoms du CCS", "texte"),
        ("resp_grade", "Grade du CCS", "grade"), ("resp_nip", "NIP du CCS", "texte"), ("resp_matricule", "Matricule du CCS", "texte"),
        ("resp_prise_fonction", "Date de prise de fonction du CCS", "date"),
        ("annee_creation", "Année de création de la CS", "annee"), ("adresse", "Adresse", "texte"), ("bp", "Boîte postale", "texte"),
        ("telephone", "Téléphone", "texte"), ("email", "E-mail", "texte"),
    ],
    "ddemp": [
        ("memp", "Nom du MEMP (ministère)", "texte"), ("departement", "Département", "texte"),
        ("commune", "Ville (siège de la direction)", "texte"),
        ("resp_titre", "Titre du responsable (DDEMP)", "titre"), ("resp_nom", "Nom et prénoms du DDEMP", "texte"),
        ("resp_grade", "Grade du DDEMP", "grade"), ("resp_nip", "NIP du DDEMP", "texte"), ("resp_matricule", "Matricule du DDEMP", "texte"),
        ("resp_prise_fonction", "Date de prise de fonction du DDEMP", "date"),
        ("annee_creation", "Année de création de la DDEMP", "annee"), ("adresse", "Adresse", "texte"), ("bp", "Boîte postale", "texte"),
        ("telephone", "Téléphone", "texte"), ("email", "E-mail", "texte"),
    ],
}
TOUTES_CLES = [k for k, _l, _t in CHAMPS_IDENTITE["cs"]]
TITRES = {"cs": ["Le Chef de la Circonscription Scolaire", "La Cheffe de la Circonscription Scolaire"],
          "ddemp": ["Le Directeur Départemental", "La Directrice Départementale"]}
# nombres calculés : (clé, libellé)
NOMBRES = {
    "cs": [("nb_zones", "Nombre de zones pédagogiques"), ("nb_up", "Nombre d'unités pédagogiques (UP)"),
           ("nb_ecoles", "Nombre d'écoles"), ("nb_ecoles_pub", "dont écoles publiques"), ("nb_ecoles_priv", "dont écoles privées"),
           ("nb_ep", "dont écoles primaires (EP)"), ("nb_em", "dont écoles maternelles (EM)"), ("nb_ee", "dont espaces enfance (EE)"),
           ("nb_enseignants", "Nombre d'enseignants (personnel transmis par les écoles)"), ("nb_agents", "Agents de la circonscription")],
    "ddemp": [("nb_cs", "Nombre de circonscriptions scolaires"), ("nb_zones", "Nombre de zones pédagogiques"),
              ("nb_up", "Nombre d'unités pédagogiques (UP)"), ("nb_ecoles", "Nombre d'écoles"),
              ("nb_ecoles_pub", "dont écoles publiques"), ("nb_ecoles_priv", "dont écoles privées"),
              ("nb_ep", "dont écoles primaires (EP)"), ("nb_em", "dont écoles maternelles (EM)"), ("nb_ee", "dont espaces enfance (EE)"),
              ("nb_enseignants", "Nombre d'enseignants (personnel transmis)"), ("nb_agents", "Agents de la direction départementale")],
}

# ---------------------------------------------------------------- personnel : colonnes (clé, libellé, libellé PDF, largeur PDF)
COLS_PERSONNEL = [
    ("matricule", "N° matricule", "Matri-\ncule", 9), ("nip", "NIP", "NIP", 10), ("nom_complet", "Nom et prénoms", "Nom et prénoms", 18),
    ("promotion", "Promotion", "Promo-\ntion", 7), ("categorie", "Catégorie (FE, ACDPE, ACDPCTD)", "Caté-\ngorie", 8),
    ("fonction", "Fonction / poste (CCS, CP, chef de division, secrétaire, agent…)", "Fonction /\nposte", 14),
    ("service", "Service / division", "Service /\ndivision", 13), ("grade", "Grade (A, B, C1-1 à 15)", "Grade", 7),
    ("indice_reel", "Indice réel", "Ind.\nréel", 6), ("indice_paye", "Indice payé", "Ind.\npayé", 6),
    ("anc_generale", "Ancienneté générale", "Anc.\ngén.", 8), ("anc_departement", "Ancienneté dans le département", "Anc.\ndép.", 8),
    ("anc_structure", "Ancienneté dans la structure", "Anc.\nstruct.", 8),
    ("date_prise_service", "Date de première prise de service", "1re prise\nde service", 11),
    ("date_service_dep", "Date de prise de service dans le département", "PS dépar-\ntement", 11),
    ("date_service_structure", "Date de prise de service dans la structure", "PS\nstructure", 11),
    ("retraite_txt", "Date de départ à la retraite", "Retraite", 11),
    ("date_derniere_formation", "Date de la dernière formation", "Dernière\nformation", 11),
    ("diplome_academique_txt", "Diplôme académique le plus élevé (année)", "Dipl.\nacad.", 11),
    ("diplome_pro_txt", "Diplôme professionnel CEAP / CAP (année)", "CEAP /\nCAP", 11),
    ("visite_aptitude", "Visite d'aptitude (oui/non)", "Apti-\ntude", 6), ("note_aptitude", "Note d'aptitude", "Note\napt.", 6),
    ("note_evaluation", "Note d'évaluation", "Note\néval.", 6), ("telephone", "Contact", "Contact", 11),
]
ENTETES_PERSONNEL = ["N°"] + [lib for _k, lib, _p, _w in COLS_PERSONNEL]
ENTETES_PERSONNEL_PDF = ["N°"] + [p for _k, _l, p, _w in COLS_PERSONNEL]
LARGEURS_PERSONNEL_PDF = [4] + [w for _k, _l, _p, w in COLS_PERSONNEL]
# champs du formulaire d'agent (clé, libellé, type) : ceux d'a_personnel + ceux du synoptique (JSON donnees)
CHAMPS_AGENT = [c for c in AP.CHAMPS_AGENT if c[0] != "actif"] + [
    ("promotion", "Promotion", "texte"), ("date_derniere_formation", "Date de la dernière formation", "date")]
LIB_CHAMP = {k: lib for k, lib, _t in CHAMPS_AGENT}
RE_NIP = re.compile(r"^\d{1,12}$")

COMITES = {"conseil": "Conseil de direction (réunion des chefs de division)", "cantine": "Comité de gestion des cantines scolaires",
           "cep": "Jury / commission du CEP", "autre": "Autres instances"}
COMITES_COURTS = {"conseil": "Conseil de direction", "cantine": "Comité de gestion des cantines", "cep": "Jury / commission CEP",
                  "autre": "Autre instance"}
QUALITES = ["Président(e)", "Vice-président(e)", "Secrétaire", "Rapporteur", "Trésorier(ère)", "Commissaire aux comptes",
            "Membre", "Personne ressource"]
ORIGINES = ["CS", "DDEMP", "Mairie / commune", "Direction d'école", "APE / parents d'élèves", "Enseignant(e)", "Partenaire",
            "Agent de santé", "Autre"]
ENT_MEMBRES = ["N°", "Comité", "Instance (si autre)", "Nom et prénoms", "Qualité / fonction", "Structure d'origine", "Contact", "Observations"]


def valeurs_personnel(f):
    """Fiche calculée (a_personnel.fiche) -> dict des valeurs texte des colonnes du tableau synoptique."""
    anc = lambda k: f["anc_txt"].get(k) or ""   # noqa: E731
    v = {k: "" for k, _l, _p, _w in COLS_PERSONNEL}
    v.update({
        "matricule": f.get("matricule") or "", "nip": f.get("nip") or "", "nom_complet": f["nom_complet"],
        "promotion": f.get("promotion") or "", "categorie": f["categorie_lib"], "fonction": f["fonction_txt"],
        "service": f.get("service_lib") or "", "grade": f["grade"], "indice_reel": AP.fmt_n(f.get("indice_reel")),
        "indice_paye": AP.fmt_n(f.get("indice_paye")), "anc_generale": anc("generale"), "anc_departement": anc("departement"),
        "anc_structure": anc("ecole"), "date_prise_service": f["ps_txt"]["generale"], "date_service_dep": f["ps_txt"]["departement"],
        "date_service_structure": f["ps_txt"]["ecole"], "retraite_txt": f["retraite_txt"],
        "date_derniere_formation": MC.fmt_date(AP.iso(f.get("date_derniere_formation"))),
        "diplome_academique_txt": AP._pdf_diplomes(f), "diplome_pro_txt": AP._pdf_pro(f), "visite_aptitude": f["apt_o"],
        "note_aptitude": AP.fmt_n(f["note_apt"]), "note_evaluation": AP.fmt_n(f["note_eval"]), "telephone": f.get("telephone") or "",
    })
    return v


def ligne_personnel(i, f):
    v = valeurs_personnel(f)
    return [i] + [v[k] for k, _l, _p, _w in COLS_PERSONNEL]


_H = None


# ================================================================ module Flask
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    def garde():
        if not config.juridiction():
            abort(404)

    def niveau():
        return config.EDITION if config.EDITION in ("cs", "ddemp") else "cs"

    def ddemp():
        return niveau() == "ddemp"

    def uid():
        return g.user["id"] if g.get("user") else None

    def peut_ecrire():
        return H.peut("jur_synoptique")

    def champs():
        return CHAMPS_IDENTITE[niveau()]

    def table_existe(nom):
        return bool(q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nom,), un=True))

    def cs_courante_id():
        c = H.jur_cs_courante() if niveau() == "cs" else None
        return c["id"] if c else None

    # ------------------------------------------------------------ référentiel : services, UP, personnel des écoles
    def services_dict():
        """{code: nom (sigle)} des services du niveau."""
        try:
            lst = H.jur_services()
        except Exception:  # noqa: BLE001
            lst = []
        out = {}
        for s in lst:
            out[s["code"]] = s["nom"] + (f" ({s['sigle']})" if s.get("sigle") and s["sigle"] not in (s["nom"] or "") else "")
        if not out:
            out = dict(AP.SERVICES_DEFAUT.get(niveau(), AP.SERVICES_DEFAUT["cs"]))
        return out

    def ups(cs_id=None):
        """UP actives (lignes dict) de la juridiction, ou d'une CS."""
        if not table_existe("jur_up"):
            return []
        sql, args = "SELECT * FROM jur_up WHERE actif=1", []
        if cs_id:
            sql += " AND cs_id=?"
            args.append(cs_id)
        return [dict(r) for r in q(sql + " ORDER BY zone_id, nom", tuple(args))]

    def enseignants_par_ecole():
        """{ecole_id: nombre d'enseignants (directeur, adjoints, enseignants) transmis}."""
        out = {}
        for p in H.jur_personnel(H.jur_annee(), inclure_agents=False):
            if p.get("role", "enseignant") in AP.ROLES_ENS and p.get("actif") is not False:
                out[p["ecole_id"]] = out.get(p["ecole_id"], 0) + 1
        return out

    def effectifs_par_ecole():
        """{ecole_id: (garçons, filles)} d'après la section « effectifs » transmise."""
        out = {}
        for eid, eff in H.jur_sections("effectifs").items():
            cl = (eff or {}).get("classes") or []
            out[eid] = (sum(int(c.get("garcons") or 0) for c in cl), sum(int(c.get("filles") or 0) for c in cl))
        return out

    # ------------------------------------------------------------ 1. identité
    def agent_responsable():
        """Agent de la structure occupant le poste de responsable (chef du service racine, sinon rôle ccs / poste DD)."""
        code = "ccs" if niveau() == "cs" else "direction"
        r = q("SELECT responsable_id FROM jur_services WHERE niveau=? AND code=? AND responsable_id IS NOT NULL", (niveau(), code), un=True)
        a = q("SELECT * FROM jur_agents WHERE id=? AND actif=1", (r["responsable_id"],), un=True) if r else None
        if not a:
            for row in q("SELECT * FROM jur_agents WHERE actif=1 ORDER BY id"):
                d = json.loads(row["donnees"] or "{}")
                poste = (row["poste"] or "").lower()
                if (niveau() == "cs" and (d.get("role") == "ccs" or poste.startswith("chef de la circonscription"))) or \
                        (niveau() == "ddemp" and poste.startswith("directeur départemental") and "adjoint" not in poste):
                    a = row
                    break
        return a

    def nombres():
        """Nombres calculés de l'identité (zones, UP, écoles, enseignants, agents, CS)."""
        cid = cs_courante_id()
        ecs = [dict(e) for e in H.jur_ecoles()]
        n = {"nb_cs": len(H.jur_cs_liste()), "nb_zones": len(H.jur_zones(cid) if cid else H.jur_zones()), "nb_up": len(ups(cid)),
             "nb_ecoles": len(ecs), "nb_ecoles_pub": sum(1 for e in ecs if e["secteur"] == "public"),
             "nb_ecoles_priv": sum(1 for e in ecs if e["secteur"] != "public"),
             "nb_ep": sum(1 for e in ecs if e["type"] == "EP"), "nb_em": sum(1 for e in ecs if e["type"] == "EM"),
             "nb_ee": sum(1 for e in ecs if e["type"] == "EE"), "nb_enseignants": sum(enseignants_par_ecole().values()),
             "nb_agents": len(agents_rows())}
        return n

    def identite(avec_nombres=True):
        """Identité du synoptique : valeurs enregistrées, complétées par jur_structure / jur_cs / agent responsable."""
        s = H.jur_structure() or {}
        c = H.jur_cs_courante() if niveau() == "cs" else None
        a = agent_responsable()
        da = json.loads(a["donnees"] or "{}") if a else {}
        defaut = {
            "memp": MEMP_DEFAUT, "departement": s.get("departement") or "", "ddemp_nom": "",
            "cs_nom": s.get("cs") or "", "cs_numero": str(c["numero"]) if c and c["numero"] else "",
            "arrondissements": (c["arrondissements"] if c else "") or "", "commune": s.get("ville") or "",
            "resp_titre": s.get("responsable_titre") or TITRES[niveau()][0], "resp_nom": s.get("responsable_nom") or "",
            "resp_grade": str(da.get("grade") or ""), "resp_nip": (a["nip"] if a else "") or "", "resp_matricule": (a["matricule"] if a else "") or "",
            "resp_prise_fonction": str(da.get("date_ps_ecole") or ""), "annee_creation": "", "adresse": s.get("adresse") or "",
            "bp": s.get("bp") or "", "telephone": s.get("telephone") or "", "email": s.get("email") or "",
        }
        r = q("SELECT * FROM jur_synoptique_identite WHERE id=1", un=True)
        d = dict(defaut)
        if r:
            for k in TOUTES_CLES:
                if r[k] not in (None, ""):
                    d[k] = r[k]
            d["maj"] = r["maj"]
        else:
            d["maj"] = None
        d["niveau"] = niveau()
        d["structure_nom"] = s.get("nom") or config.NOMS_APPLI.get(config.EDITION, "GESCOL")
        d["sigle"] = s.get("sigle") or ""
        d["resp_prise_fonction_txt"] = MC.fmt_date(AP.iso(d["resp_prise_fonction"])) if d["resp_prise_fonction"] else ""
        if avec_nombres:
            d.update(nombres())
        return d

    def enregistrer_identite(form):
        v = {k: (form.get(k) or "").strip()[:200] for k in TOUTES_CLES}
        err = []
        if v["annee_creation"] and not re.fullmatch(r"\d{4}", v["annee_creation"]):
            err.append("Année de création invalide (quatre chiffres).")
        if v["resp_nip"] and not RE_NIP.fullmatch(v["resp_nip"].replace(" ", "")):
            err.append("NIP du responsable : 12 chiffres au maximum.")
        v["resp_nip"] = v["resp_nip"].replace(" ", "")
        if v["resp_grade"]:
            v["resp_grade"] = v["resp_grade"].upper().replace(" ", "")
            if not AP.RE_GRADE.fullmatch(v["resp_grade"]):
                err.append("Grade du responsable invalide (exemples : A1-5, B2-12).")
        if v["resp_prise_fonction"]:
            try:
                v["resp_prise_fonction"] = MC.lire_date(v["resp_prise_fonction"][:10]) or ""
            except ValueError:
                err.append("Date de prise de fonction invalide (jj/mm/aaaa).")
        if v["cs_numero"] and not v["cs_numero"].isdigit():
            err.append("Le numéro de la circonscription est un nombre.")
        if err:
            return err
        ex(f"INSERT INTO jur_synoptique_identite (id, {', '.join(TOUTES_CLES)}, maj, maj_par) VALUES (1, {', '.join('?' * len(TOUTES_CLES))}, ?, ?) "
           "ON CONFLICT(id) DO UPDATE SET " + ", ".join(f"{k}=excluded.{k}" for k in TOUTES_CLES) + ", maj=excluded.maj, maj_par=excluded.maj_par",
           [v[k] for k in TOUTES_CLES] + [H.maintenant(), uid()])
        # cohérence avec la structure (comme m_synoptique avec la fiche école)
        ex("UPDATE jur_structure SET responsable_titre=COALESCE(NULLIF(?, ''), responsable_titre), "
           "responsable_nom=COALESCE(NULLIF(?, ''), responsable_nom), telephone=COALESCE(NULLIF(?, ''), telephone), "
           "email=COALESCE(NULLIF(?, ''), email), adresse=COALESCE(NULLIF(?, ''), adresse), bp=COALESCE(NULLIF(?, ''), bp), "
           "ville=COALESCE(NULLIF(?, ''), ville), maj=datetime('now','localtime') WHERE id=1",
           (v["resp_titre"], v["resp_nom"], v["telephone"], v["email"], v["adresse"], v["bp"], v["commune"]))
        cid = cs_courante_id()
        if cid:
            ex("UPDATE jur_cs SET ccs_titre=COALESCE(NULLIF(?, ''), ccs_titre), ccs_nom=COALESCE(NULLIF(?, ''), ccs_nom), "
               "numero=COALESCE(NULLIF(?, ''), numero), arrondissements=COALESCE(NULLIF(?, ''), arrondissements), "
               "telephone=COALESCE(NULLIF(?, ''), telephone), email=COALESCE(NULLIF(?, ''), email), adresse=COALESCE(NULLIF(?, ''), adresse) WHERE id=?",
               (v["resp_titre"], v["resp_nom"], v["cs_numero"], v["arrondissements"], v["telephone"], v["email"], v["adresse"], cid))
        H.journal("jur_synoptique", "identité de la structure modifiée")
        return []

    # ------------------------------------------------------------ 2. personnel de la structure
    def agents_rows(tous=False, aid=None):
        sql, args = "SELECT * FROM jur_agents WHERE 1=1", []
        cid = cs_courante_id()
        if cid:
            sql += " AND (cs_id IS NULL OR cs_id=?)"
            args.append(cid)
        else:
            sql += " AND cs_id IS NULL"
        if aid is not None:
            sql += " AND id=?"
            args.append(aid)
        elif not tous:
            sql += " AND actif=1"
        return q(sql + " ORDER BY actif DESC, service_code, nom, prenoms", tuple(args))

    ORDRE_ROLES = {"ccs": 0, "cp": 1, "chef_service": 2, "administratif": 3, "soutien": 4}

    def agent_valeurs(r):
        d = json.loads(r["donnees"] or "{}")
        for k in AP.COLONNES_TABLE:
            d[k] = r[k] or ""
        d["actif"] = bool(r["actif"])
        d["user_id"] = r["user_id"]
        return d

    def fiche_agent(r, svc=None, ref=None, auj=None):
        svc = svc if svc is not None else services_dict()
        d = agent_valeurs(r)
        f = AP.fiche(dict(d, source="agent", agent_id=r["id"], cs_nom="", zone_nom="", secteur="public"),
                     ref or AP.reference(H.jur_annee()), auj or date.today(), svc)
        f["id"] = r["id"]
        f["service_lib"] = svc.get(r["service_code"] or "", r["service_code"] or "")
        f["role_ordre"] = ORDRE_ROLES.get(f["role"], 9)
        return f

    def personnel(tous=False):
        """Agents de la structure (fiches calculées), responsable d'abord puis CP, chefs, administratifs, soutien."""
        svc, ref, auj = services_dict(), AP.reference(H.jur_annee()), date.today()
        lst = [fiche_agent(r, svc, ref, auj) for r in agents_rows(tous)]
        lst.sort(key=lambda f: (0 if f["actif"] else 1, f["role_ordre"], f["service_lib"], f["nom_complet"]))
        return lst

    def agent_ou_404(aid):
        rows = agents_rows(tous=True, aid=aid)
        if not rows:
            abort(404)
        return rows[0]

    def lire_agent(src, aid=None, auj=None):
        """Formulaire ou ligne Excel (dict clé → texte) -> (valeurs, erreurs). Mêmes règles qu'a_personnel."""
        auj = auj or date.today()
        v, err = {}, []
        txt = lambda k, n=150: str(src.get(k) if src.get(k) is not None else "").strip()[:n]   # noqa: E731
        codes_svc = set(services_dict())
        for k, lib, typ in CHAMPS_AGENT:
            brut = txt(k, 500 if k == "gestion_collegiale" else 150)
            val = brut
            if typ == "sexe":
                val = H.xlsx.sexe(brut) if brut else ""
                if brut and not val:
                    err.append("Sexe : indiquez M ou F.")
            elif typ == "nip":
                val = brut.replace(" ", "")
                if val and not RE_NIP.fullmatch(val):
                    err.append("NIP : 12 chiffres au maximum, sans lettres.")
            elif typ == "naissance":
                try:
                    val = MC.lire_naissance(brut[:10]) or ""
                except ValueError:
                    err.append("Date de naissance invalide (jj/mm/aaaa ou l'année seule).")
                    val = ""
            elif typ == "date":
                try:
                    val = MC.lire_date(brut[:10]) or ""
                except ValueError:
                    err.append(f"{lib} : date invalide (jj/mm/aaaa).")
                    val = ""
            elif typ == "service":
                if val and val not in codes_svc:
                    err.append("Service inconnu.")
            elif typ == "role":
                val = val or "administratif"
                if val not in AP.ROLES_AGENT:
                    err.append("Rôle invalide (ccs, cp, chef_service, administratif ou soutien).")
            elif typ == "categorie":
                val = val.upper()
                if val and val not in AP.CATEGORIES:
                    err.append("Catégorie invalide (FE, ACDPE, ACDPCTD, PRIVE ou AUTRE).")
            elif typ == "grade":
                val = val.upper().replace(" ", "")
                if val and not AP.RE_GRADE.fullmatch(val):
                    err.append("Grade invalide (exemples : A1-5, B2-12, C3-1).")
            elif typ in ("indice", "compte", "pct", "note"):
                maxi = {"indice": 9999, "compte": 99, "pct": 100, "note": 20}[typ]
                x = AP.nombre(brut)
                if brut and (x is None or not 0 <= x <= maxi):
                    err.append(f"{lib} : valeur invalide (0 à {maxi}).")
                    x = None
                val = "" if x is None else (int(x) if x.is_integer() and typ != "note" else x)
            elif typ == "annee":
                if val and not (re.fullmatch(r"\d{4}", val) and 1940 <= int(val) <= auj.year):
                    err.append(f"{lib} : année invalide.")
                    val = ""
            elif typ == "bool":
                e_ = AP.tri_etat(brut)
                val = True if e_ == "oui" else (False if e_ == "non" else "")
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
        n = v["date_naissance"]
        for k in ("date_premiere_ps", "date_ps_departement", "date_ps_commune", "date_ps_ecole"):
            if n and v[k] and v[k][:4] <= n[:4]:
                err.append(f"{LIB_CHAMP[k]} : antérieure ou égale à l'année de naissance.")
            if k != "date_premiere_ps" and v["date_premiere_ps"] and v[k] and v[k] < v["date_premiere_ps"]:
                err.append(f"{LIB_CHAMP[k]} : antérieure à la première prise de service.")
        for k in ("ceap", "cap"):
            if v[f"annee_{k}"] and v[k] == "":
                v[k] = True
        if (v["note_aptitude"] != "" or v["annee_aptitude"]) and v["visite_aptitude"] == "":
            v["visite_aptitude"] = True
        if v["matricule"]:
            autre = q("SELECT id FROM jur_agents WHERE matricule=? AND id<>? AND actif=1", (v["matricule"], aid or 0), un=True)
            if autre:
                err.append("Ce numéro matricule est déjà attribué à un autre agent.")
        return v, err

    def enregistrer_agent(v, aid=None):
        """Crée / met à jour jur_agents : colonnes de la table + JSON donnees (clés existantes conservées)."""
        existant = q("SELECT donnees FROM jur_agents WHERE id=?", (aid,), un=True) if aid else None
        donnees = json.loads(existant["donnees"] or "{}") if existant else {}
        donnees.update({k: v[k] for k, _l, _t in CHAMPS_AGENT if k not in AP.COLONNES_TABLE})
        donnees["actif"] = True
        cols = {k: v[k] for k in AP.COLONNES_TABLE}
        if aid:
            ex("UPDATE jur_agents SET " + ", ".join(f"{k}=?" for k in cols) + ", donnees=?, actif=1, maj=datetime('now','localtime') WHERE id=?",
               tuple(cols.values()) + (json.dumps(donnees, ensure_ascii=False), aid))
            return aid
        return ex("INSERT INTO jur_agents (cs_id, " + ", ".join(cols) + ", donnees, actif, maj) VALUES (?, " +
                  ", ".join("?" * len(cols)) + ", ?, 1, datetime('now','localtime'))",
                  (cs_courante_id(),) + tuple(cols.values()) + (json.dumps(donnees, ensure_ascii=False),))

    def valeurs_formulaire(r):
        v = agent_valeurs(r)
        for k in ("ceap", "cap", "visite_aptitude"):
            v[k] = AP.tri_etat(v.get(k))
        for k in ("date_naissance", "date_premiere_ps", "date_ps_departement", "date_ps_commune", "date_ps_ecole", "date_derniere_formation"):
            if len(str(v.get(k) or "")) == 10 and MC.en_date(v[k]):
                v[k] = MC.en_date(v[k]).strftime("%d/%m/%Y")
        return v

    # ------------------------------------------------------------ 3. réseau
    def reseau():
        """{"cs": [{cs, zones:[…], nb_*}], "zones": [...] } ; chaque zone : n°, nom, CP, écoles (liste), UP (liste), enseignants."""
        ens = enseignants_par_ecole()
        eff = effectifs_par_ecole()
        ecoles = [dict(e) for e in H.jur_ecoles()]
        for e in ecoles:
            e["enseignants"] = ens.get(e["id"], 0)
            e["effectif_g"], e["effectif_f"] = eff.get(e["id"], (None, None))
            e["effectif"] = (e["effectif_g"] or 0) + (e["effectif_f"] or 0) if e["id"] in eff else None
        tous_ups = ups()
        zones = []
        for z in H.jur_zones():
            ecs = [e for e in ecoles if e["zone_id"] == z["id"]]
            zu = [u for u in tous_ups if u["zone_id"] == z["id"]]
            zones.append({"id": z["id"], "cs_id": z["cs_id"], "cs_nom": z["cs_nom"], "numero": z["ordre"], "nom": z["nom"],
                          "cp_nom": z["cp_nom"] or "", "cp_tel": z["cp_telephone"] or "", "ecoles": ecs, "nb_ecoles": len(ecs),
                          "ups": zu, "nb_up": len(zu), "enseignants": sum(e["enseignants"] for e in ecs)})
        sans_zone = [e for e in ecoles if not e["zone_id"]]
        par_cs = []
        for c in H.jur_cs_liste():
            zc = [z for z in zones if z["cs_id"] == c["id"]]
            ecs = [e for e in ecoles if e["cs_id"] == c["id"]]
            hors = [e for e in sans_zone if e["cs_id"] == c["id"]]
            par_cs.append({"cs": dict(c), "zones": zc, "nb_zones": len(zc), "nb_up": sum(z["nb_up"] for z in zc) +
                           sum(1 for u in tous_ups if u["cs_id"] == c["id"] and not u["zone_id"]),
                           "nb_ecoles": len(ecs), "enseignants": sum(e["enseignants"] for e in ecs), "sans_zone": hors})
        return {"zones": zones, "cs": par_cs, "sans_zone": sans_zone, "nb_up": len(tous_ups), "nb_ecoles": len(ecoles),
                "enseignants": sum(e["enseignants"] for e in ecoles)}

    # ------------------------------------------------------------ 4. services / divisions
    def agents_par_service():
        out = {}
        for r in agents_rows():
            out[r["service_code"] or ""] = out.get(r["service_code"] or "", 0) + 1
        return out

    def services_liste():
        """Services actifs avec chef, sigle, article AOF, nombre d'agents (a_divisions si disponible, sinon a_structure)."""
        nb = agents_par_service()
        lst = []
        try:
            lst = H.jur_divisions(H.jur_annee(), avec_lignes=False)
        except Exception:  # noqa: BLE001
            lst = []
        if not lst:
            try:
                lst = H.jur_services()
            except Exception:  # noqa: BLE001
                lst = []
        out = []
        for d in lst:
            d = dict(d)
            d.setdefault("chef_nom", d.get("responsable_nom") or "")
            d.setdefault("chef_titre", "")
            d.setdefault("article", "")
            d.setdefault("source", "")
            d["nb_agents"] = nb.get(d["code"], 0)
            out.append(d)
        return out

    # ------------------------------------------------------------ 5. comités
    def membres(comite=None):
        sql, args = "SELECT * FROM jur_synoptique_membres", []
        if comite:
            sql += " WHERE comite=?"
            args.append(comite)
        return [dict(m) for m in q(sql + " ORDER BY comite, libelle, ordre, id", tuple(args))]

    def lire_membre(form, comite):
        v = {"nom_prenoms": (form.get("nom_prenoms") or "").strip()[:120], "qualite": (form.get("qualite") or "").strip()[:60],
             "origine": (form.get("origine") or "").strip()[:80], "contact": (form.get("contact") or "").strip()[:60],
             "observations": (form.get("observations") or "").strip()[:300], "libelle": (form.get("libelle") or "").strip()[:120]}
        brut = (form.get("ordre") or "").strip()
        v["ordre"] = int(brut) if brut.isdigit() else 0
        err = []
        if not v["nom_prenoms"]:
            err.append("Le nom et les prénoms du membre sont obligatoires.")
        if comite == "autre" and not v["libelle"]:
            err.append("Indiquez l'intitulé de l'instance (comité « autre »).")
        if comite != "autre":
            v["libelle"] = ""
        return v, err

    def comite_ou_404(comite):
        if comite not in COMITES:
            abort(404)
        return COMITES[comite]

    # ------------------------------------------------------------ exposé aux autres modules
    def jur_synoptique_identite():
        return identite()

    def jur_synoptique_personnel():
        return [valeurs_personnel(f) for f in personnel()]

    H.jur_synoptique_identite = jur_synoptique_identite
    H.jur_synoptique_personnel = jur_synoptique_personnel
    global _H
    _H = H

    # ------------------------------------------------------------ contexte des gabarits
    def ctx(onglet, **extra):
        return dict(onglet=onglet, ecrire=peut_ecrire(), ident=identite(avec_nombres=False), COMITES=COMITES,
                    COMITES_COURTS=COMITES_COURTS, ddemp=ddemp(), fmt_date=MC.fmt_date, **extra)

    # ============================================================ identité
    @app.route("/juridiction/synoptique")
    @H.connexion_requise()
    def jur_synoptique():
        garde()
        d = identite()
        comites = {c: q("SELECT COUNT(*) n FROM jur_synoptique_membres WHERE comite=?", (c,), un=True)["n"] for c in COMITES}
        return render_template("jur_synoptique_identite.html", **ctx("identite", d=d, champs=champs(), nombres=NOMBRES[niveau()],
                                                                      titres=TITRES[niveau()], grades=MC.GRADES, comites=comites,
                                                                      reference=MC.date_reference()))

    @app.route("/juridiction/synoptique/identite", methods=["POST"])
    @H.connexion_requise("jur_synoptique")
    def jur_synoptique_identite_post():
        garde()
        err = enregistrer_identite(request.form)
        for m in err:
            flash(m, "danger")
        if not err:
            flash("Identité de la structure enregistrée.", "success")
        return redirect(url_for("jur_synoptique"))

    # ============================================================ personnel
    @app.route("/juridiction/synoptique/personnel")
    @H.connexion_requise()
    def jur_synoptique_personnel():
        garde()
        tous = request.args.get("tous") == "1"
        lst = personnel(tous=tous)
        return render_template("jur_synoptique_personnel.html", **ctx("personnel", lst=lst, lignes=[(f, valeurs_personnel(f)) for f in lst],
                                                                       cols=COLS_PERSONNEL, tous=tous, reference=AP.reference(H.jur_annee()),
                                                                       ages=MC.AGES_RETRAITE))

    @app.route("/juridiction/synoptique/agent/<int:aid>", methods=["GET", "POST"])
    @H.connexion_requise("jur_synoptique")
    def jur_synoptique_agent(aid):
        garde()
        r = agent_ou_404(aid) if aid else None
        if request.method == "POST":
            v, err = lire_agent(request.form, aid or None)
            if err:
                for m in err:
                    flash(m, "danger")
                vals = dict(request.form)
            else:
                nouveau = enregistrer_agent(v, aid or None)
                H.journal("jur_synoptique", f"agent {'modifié' if aid else 'ajouté'} : {v['nom']} {v['prenoms']}")
                flash("Agent enregistré.", "success")
                if request.form.get("suivant"):
                    return redirect(url_for("jur_synoptique_agent", aid=0))
                return redirect(url_for("jur_synoptique_personnel", _anchor=f"agent-{nouveau}"))
        else:
            vals = valeurs_formulaire(r) if r else {"role": "administratif", "categorie": "FE",
                                                    "departement_a_servir": (H.jur_structure() or {}).get("departement", "")}
        f = fiche_agent(r) if r else None
        return render_template("jur_synoptique_agent_form.html",
                               **ctx("personnel", f=f, v=vals, aid=aid, services=list(services_dict().items()), roles=AP.ROLES_AGENT,
                                     postes=AP.POSTES.get(niveau(), []), categories=AP.CATEGORIES, grades=MC.GRADES, diplomes=MC.DIPLOMES,
                                     departements=MC.DEPARTEMENTS, lib=LIB_CHAMP, reference=AP.reference(H.jur_annee()),
                                     ages=MC.AGES_RETRAITE)), (400 if request.method == "POST" else 200)

    @app.route("/juridiction/synoptique/agent/<int:aid>/retirer", methods=["POST"])
    @H.connexion_requise("jur_synoptique")
    def jur_synoptique_agent_retirer(aid):
        garde()
        r = agent_ou_404(aid)
        ex("UPDATE jur_agents SET actif=0, user_id=NULL, maj=datetime('now','localtime') WHERE id=?", (aid,))
        H.journal("jur_synoptique", f"agent retiré du tableau : {r['nom']} {r['prenoms'] or ''}")
        flash(f"{r['nom']} {r['prenoms'] or ''} retiré(e) du tableau du personnel (fiche conservée, réactivable).", "warning")
        return redirect(url_for("jur_synoptique_personnel"))

    @app.route("/juridiction/synoptique/agent/<int:aid>/reactiver", methods=["POST"])
    @H.connexion_requise("jur_synoptique")
    def jur_synoptique_agent_reactiver(aid):
        garde()
        r = agent_ou_404(aid)
        ex("UPDATE jur_agents SET actif=1, maj=datetime('now','localtime') WHERE id=?", (aid,))
        H.journal("jur_synoptique", f"agent réactivé : {r['nom']} {r['prenoms'] or ''}")
        flash(f"{r['nom']} {r['prenoms'] or ''} de nouveau dans le tableau du personnel.", "success")
        return redirect(url_for("jur_synoptique_personnel", tous=1))

    # ============================================================ réseau, services
    @app.route("/juridiction/synoptique/reseau")
    @H.connexion_requise()
    def jur_synoptique_reseau():
        garde()
        return render_template("jur_synoptique_reseau.html", **ctx("reseau", r=reseau(), TYPES=H.jur_TYPES, SECTEURS=H.jur_SECTEURS))

    @app.route("/juridiction/synoptique/services")
    @H.connexion_requise()
    def jur_synoptique_services():
        garde()
        return render_template("jur_synoptique_services.html", **ctx("services", lst=services_liste()))

    # ============================================================ comités
    @app.route("/juridiction/synoptique/comites")
    @app.route("/juridiction/synoptique/comites/<comite>")
    @H.connexion_requise()
    def jur_synoptique_comites(comite="conseil"):
        garde()
        lib = comite_ou_404(comite)
        return render_template("jur_synoptique_comites.html", **ctx("comites", comite=comite, lib=lib, lst=membres(comite)))

    @app.route("/juridiction/synoptique/comites/<comite>/membre/<int:mid>", methods=["GET", "POST"])
    @H.connexion_requise("jur_synoptique")
    def jur_synoptique_membre(comite, mid):
        garde()
        lib = comite_ou_404(comite)
        m = None
        if mid:
            m = q("SELECT * FROM jur_synoptique_membres WHERE id=? AND comite=?", (mid, comite), un=True)
            if not m:
                abort(404)
            m = dict(m)
        if request.method == "POST":
            v, err = lire_membre(request.form, comite)
            if err:
                for e_ in err:
                    flash(e_, "danger")
                return render_template("jur_synoptique_membre_form.html", **ctx("comites", comite=comite, lib=lib, m=m, v=v,
                                                                                 qualites=QUALITES, origines=ORIGINES)), 400
            if mid:
                ex("UPDATE jur_synoptique_membres SET nom_prenoms=?, qualite=?, origine=?, contact=?, observations=?, libelle=?, ordre=?, "
                   "maj=?, maj_par=? WHERE id=?",
                   (v["nom_prenoms"], v["qualite"], v["origine"], v["contact"], v["observations"], v["libelle"], v["ordre"],
                    H.maintenant(), uid(), mid))
            else:
                ex("INSERT INTO jur_synoptique_membres (annee, comite, libelle, ordre, nom_prenoms, qualite, origine, contact, observations, maj, maj_par) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (config.ANNEE_ACTIVE, comite, v["libelle"], v["ordre"], v["nom_prenoms"], v["qualite"], v["origine"], v["contact"],
                    v["observations"], H.maintenant(), uid()))
            H.journal("jur_synoptique", f"{COMITES_COURTS[comite]} : membre {'modifié' if mid else 'ajouté'} ({v['nom_prenoms']})")
            flash("Membre enregistré.", "success")
            return redirect(url_for("jur_synoptique_comites", comite=comite))
        return render_template("jur_synoptique_membre_form.html", **ctx("comites", comite=comite, lib=lib, m=m, v=m or {},
                                                                         qualites=QUALITES, origines=ORIGINES))

    @app.route("/juridiction/synoptique/comites/<comite>/membre/<int:mid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_synoptique")
    def jur_synoptique_membre_supprimer(comite, mid):
        garde()
        comite_ou_404(comite)
        m = q("SELECT * FROM jur_synoptique_membres WHERE id=? AND comite=?", (mid, comite), un=True)
        if not m:
            abort(404)
        ex("DELETE FROM jur_synoptique_membres WHERE id=?", (mid,))
        H.journal("jur_synoptique", f"{COMITES_COURTS[comite]} : membre supprimé ({m['nom_prenoms']})")
        flash("Membre supprimé.", "warning")
        return redirect(url_for("jur_synoptique_comites", comite=comite))

    # ============================================================ PDF
    P = H.pdfs

    def infos_haut():
        s = H.jur_structure() or {}
        lignes = [("DDEMP", s.get("departement") or "—")]
        if niveau() == "cs":
            lignes.append(("CS", s.get("cs") or "—"))
        return lignes

    def bloc_signature(largeur):
        """Flowable : signature du responsable de la structure (titre, nom, image, cachet, griffe)."""
        from reportlab.lib.units import mm
        from reportlab.platypus.flowables import Flowable
        import cachet as _cachet
        titre, nom, sig = H.jur_signataire(None)
        image = P.image_data_url(sig)
        cach = H.jur_cachet(None) if getattr(H, "jur_cachet", None) else None
        griffe = H.jur_griffe(None) if getattr(H, "jur_griffe", None) else None
        ville = (H.jur_structure() or {}).get("ville") or ""

        class _Sig(Flowable):
            def wrap(self, *_):
                return largeur, 46 * mm

            def draw(self):
                c = self.canv
                x = largeur * 0.75
                y = 46 * mm - 8
                c.setFont("Helvetica", 8)
                c.drawCentredString(x, y, f"{ville}, le {date.today().strftime('%d/%m/%Y')}".lstrip(", "))
                c.setFont("Helvetica-Bold", 8.5)
                c.drawCentredString(x, y - 11, (titre or "").upper())
                if cach:
                    _cachet.dessiner(c, x - 24 * mm, y - 24 * mm, 11.5 * mm, *cach)
                if image is not None:
                    c.drawImage(image, x - 22 * mm, y - 30 * mm, 44 * mm, 17 * mm, preserveAspectRatio=True, mask="auto")
                if griffe:
                    _cachet.dessiner_nom(c, x, y - 38 * mm, griffe[0], griffe[1], 46 * mm)
                elif nom:
                    c.setFont("Helvetica-Bold", 8.5)
                    c.drawCentredString(x, y - 40 * mm, nom)
        return _Sig()

    def construire_pdf(titre, sections, paysage=True, signer=True):
        """Document multi-sections (une section par page) avec en-tête DDEMP / CS et signature du responsable."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer
        taille_page = landscape(A4) if paysage else A4
        W, Hh = taille_page
        marge = 12 * mm
        buf = io.BytesIO()
        s = H.jur_structure() or {}
        st_titre = ParagraphStyle("ti", fontName="Helvetica-Bold", fontSize=13, leading=16, alignment=1, textColor=P.BLEU, spaceAfter=2)
        st_sec = ParagraphStyle("se", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=P.BLEU, spaceBefore=4, spaceAfter=4)
        st_st = ParagraphStyle("st", fontName="Helvetica", fontSize=9, leading=11, alignment=1, spaceAfter=6)
        histoire = []
        for i, (ts, flows) in enumerate(sections):
            if i:
                histoire.append(PageBreak())
            histoire.append(Paragraph(titre, st_titre))
            histoire.append(Paragraph(f"{s.get('nom') or ''} — année scolaire {config.ANNEE_ACTIVE} — édité le "
                                      f"{date.today().strftime('%d/%m/%Y')}", st_st))
            if ts:
                histoire.append(Paragraph(ts, st_sec))
            histoire += list(flows)
        if signer:
            histoire.append(KeepTogether([Spacer(1, 8), bloc_signature(W - 2 * marge)]))

        def deco(c, doc):
            P._entete_primaire(c, W, Hh, marge, infos_haut())
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.grey)
            c.drawString(marge, 7 * mm, f"GESCOL · {s.get('nom') or ''} · {config.ANNEE_ACTIVE} · tableau synoptique")
            c.drawRightString(W - marge, 7 * mm, f"Page {doc.page} · imprimé le {date.today().strftime('%d/%m/%Y')}")
            c.setFillColor(colors.black)

        doc = SimpleDocTemplate(buf, pagesize=taille_page, leftMargin=marge, rightMargin=marge, topMargin=marge + 30 * mm,
                                bottomMargin=13 * mm, title=titre, author="GESCOL")
        doc.build(histoire, onFirstPage=deco, onLaterPages=deco, canvasmaker=P.GCanvas)
        return buf.getvalue()

    def tableau(entetes, lignes, largeurs=None, taille=7, paysage=True, surlignes=None):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Table, TableStyle
        W = (landscape(A4) if paysage else A4)[0]
        utile = W - 24 * mm
        st_c = ParagraphStyle("c", fontName="Helvetica", fontSize=taille, leading=taille + 1.6)
        st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=taille, leading=taille + 1.6, alignment=1, textColor=colors.white)

        def cell(v, st=st_c):
            return Paragraph("" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>"), st)

        data = [[cell(h, st_h) for h in entetes]] + [[cell(v) for v in l] for l in lignes]
        largeurs = largeurs or [1] * len(entetes)
        sm = sum(largeurs)
        t = Table(data, colWidths=[utile * x / sm for x in largeurs], repeatRows=1)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#667085")), ("BACKGROUND", (0, 0), (-1, 0), P.BLEU),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")])]
        for i, coul in (surlignes or {}).items():
            style.append(("BACKGROUND", (0, 1 + i), (-1, 1 + i), colors.HexColor(coul)))
        t.setStyle(TableStyle(style))
        return t

    def section_identite():
        d = identite()
        lignes = [[lib, (d["resp_prise_fonction_txt"] if k == "resp_prise_fonction" else d.get(k)) or "—"] for k, lib, _t in champs()]
        lignes += [[lib, d.get(k, 0)] for k, lib in NOMBRES[niveau()]]
        return [tableau(["Rubrique", "Renseignement"], lignes, [1, 2], taille=9)]

    def section_personnel(lst):
        corps = [ligne_personnel(i, f) for i, f in enumerate(lst, 1)] or [["", "Aucun agent"] + [""] * (len(COLS_PERSONNEL) - 1)]
        surl = {i: "#FDEAD7" for i, f in enumerate(lst) if f["alerte_retraite"]}
        notes = P.paragraphe(
            f"Anciennetés au {AP.reference(H.jur_annee()).strftime('%d/%m/%Y')} (jour inclus), en années (a) et mois (m), à partir de la "
            "prise de service dans chaque lieu. Retraite : 60 ans (grade A), 58 ans (B), 55 ans (C), départ le 1er jour du trimestre qui "
            "suit le trimestre de naissance. Lignes orangées : départ dans 2 ans ou moins. PS = prise de service.", 6.5)
        return [tableau(ENTETES_PERSONNEL_PDF, corps, LARGEURS_PERSONNEL_PDF, taille=5.6, surlignes=surl), notes]

    def lignes_zones(zones, avec_cs):
        out = []
        for z in zones:
            up_txt = "\n".join(f"{u['nom']} : RUP {u['rup_nom'] or '—'} ; Co-RUP {u['corup_nom'] or '—'}" for u in z["ups"]) or "—"
            cp = z["cp_nom"] + (f" ({z['cp_tel']})" if z["cp_tel"] else "")
            out.append(([z["cs_nom"]] if avec_cs else []) + [z["numero"], z["nom"], cp or "—", z["nb_ecoles"], z["nb_up"], up_txt, z["enseignants"]])
        return out

    ENT_ZONES = ["N°", "Zone pédagogique", "CP de zone (téléphone)", "Écoles", "UP", "Unités pédagogiques : RUP et Co-RUP", "Enseignants"]
    ENT_CS = ["N°", "Circonscription scolaire", "CCS", "Téléphone", "Zones", "UP", "Écoles", "Enseignants"]
    ENT_ECOLES = ["Zone", "École", "Type", "Secteur", "Directeur / directrice", "Téléphone", "Enseignants", "Garçons", "Filles", "Total"]

    def lignes_cs(r):
        return [[c["cs"]["numero"] or "", c["cs"]["nom"], c["cs"]["ccs_nom"] or "", c["cs"]["telephone"] or "", c["nb_zones"], c["nb_up"],
                 c["nb_ecoles"], c["enseignants"]] for c in r["cs"]]

    def lignes_ecoles(r, avec_cs):
        out = []
        for z in r["zones"]:
            for e in z["ecoles"]:
                out.append(([z["cs_nom"]] if avec_cs else []) + [z["nom"], e["nom"], e["type"], H.jur_SECTEURS.get(e["secteur"], e["secteur"]),
                           f"{e['directeur_titre'] or ''} {e['directeur_nom'] or ''}".strip(), e["directeur_tel"] or e["telephone"] or "",
                           e["enseignants"], e["effectif_g"] if e["effectif_g"] is not None else "", e["effectif_f"] if e["effectif_f"] is not None else "",
                           e["effectif"] if e["effectif"] is not None else ""])
        for e in r["sans_zone"]:
            out.append(([e["cs_nom"] or ""] if avec_cs else []) + ["Sans zone", e["nom"], e["type"], H.jur_SECTEURS.get(e["secteur"], e["secteur"]),
                       f"{e['directeur_titre'] or ''} {e['directeur_nom'] or ''}".strip(), e["directeur_tel"] or e["telephone"] or "",
                       e["enseignants"], "", "", ""])
        return out

    def sections_reseau(r):
        avec_cs = ddemp()
        secs = []
        if avec_cs:
            secs.append(("3. Circonscriptions scolaires du département", [tableau(ENT_CS, lignes_cs(r) or [["", "Aucune CS"] + [""] * 6],
                                                                                   [4, 20, 20, 12, 7, 7, 7, 9], taille=8)]))
        secs.append(("3. Zones pédagogiques, conseillers pédagogiques et unités pédagogiques",
                     [tableau((["CS"] if avec_cs else []) + ENT_ZONES, lignes_zones(r["zones"], avec_cs) or [[""] * (len(ENT_ZONES) + (1 if avec_cs else 0))],
                              ([12] if avec_cs else []) + [4, 16, 18, 7, 6, 40, 9], taille=7)]))
        secs.append(("3. Écoles par zone pédagogique",
                     [tableau((["CS"] if avec_cs else []) + ENT_ECOLES, lignes_ecoles(r, avec_cs) or [[""] * (len(ENT_ECOLES) + (1 if avec_cs else 0))],
                              ([12] if avec_cs else []) + [14, 26, 5, 8, 22, 12, 8, 7, 7, 7], taille=6.5)]))
        return secs

    ENT_SERVICES = ["N°", "Sigle", "Division / service", "Chef (nom et prénoms)", "Titre du chef", "Article AOF", "Rattachement", "Agents"]

    def lignes_services(lst):
        return [[i, d.get("sigle") or "", d["nom"], d.get("chef_nom") or "", d.get("chef_titre") or "", d.get("article") or "",
                 d.get("parent_nom") or "", d["nb_agents"]] for i, d in enumerate(lst, 1)]

    def section_services():
        lst = services_liste()
        return [tableau(ENT_SERVICES, lignes_services(lst) or [["", "", "Aucun service"] + [""] * 5], [4, 8, 28, 22, 22, 8, 18, 6], taille=7.5)]

    def section_comite(comite):
        lst = membres(comite)
        corps = [[i, (m["libelle"] or "") if comite == "autre" else None, m["nom_prenoms"], m["qualite"] or "", m["origine"] or "", m["contact"] or "",
                  m["observations"] or ""] for i, m in enumerate(lst, 1)]
        ent = ["N°", "Instance", "Nom et prénoms", "Qualité / fonction", "Structure d'origine", "Contact", "Observations"]
        larg = [1, 4, 6, 4, 4, 3, 5]
        if comite != "autre":
            corps = [[c[0]] + c[2:] for c in corps]
            ent, larg = ent[:1] + ent[2:], larg[:1] + larg[2:]
        corps = corps or [["", "Aucun membre enregistré"] + [""] * (len(ent) - 2)]
        return [tableau(ent, corps, larg, taille=8)]

    @app.route("/juridiction/synoptique/synoptique.pdf")
    @H.connexion_requise()
    def jur_synoptique_pdf():
        garde()
        d = identite(avec_nombres=False)
        sections = [("1. Identité de la structure", section_identite()),
                    ("2. Tableau synoptique du personnel de la structure", section_personnel(personnel()))]
        sections += sections_reseau(reseau())
        sections.append(("4. Divisions / services et chefs", section_services()))
        for c, lib in COMITES.items():
            sections.append((f"5. {lib}", section_comite(c)))
        titre = f"TABLEAU SYNOPTIQUE DE LA {'DDEMP' if ddemp() else 'CIRCONSCRIPTION SCOLAIRE'} — {d['sigle'] or d['structure_nom']}"
        H.journal("jur_synoptique_pdf", "PDF complet")
        return H.pdf_reponse(construire_pdf(titre, sections), "tableau_synoptique_structure.pdf")

    @app.route("/juridiction/synoptique/personnel.pdf")
    @H.connexion_requise()
    def jur_synoptique_personnel_pdf():
        garde()
        pdf = construire_pdf("TABLEAU SYNOPTIQUE DU PERSONNEL DE LA STRUCTURE",
                             [("", section_personnel(personnel(tous=request.args.get("tous") == "1")))])
        return H.pdf_reponse(pdf, "synoptique_personnel_structure.pdf")

    @app.route("/juridiction/synoptique/reseau.pdf")
    @H.connexion_requise()
    def jur_synoptique_reseau_pdf():
        garde()
        pdf = construire_pdf("RÉSEAU : ZONES PÉDAGOGIQUES, UP ET ÉCOLES", sections_reseau(reseau()))
        return H.pdf_reponse(pdf, "synoptique_reseau.pdf")

    @app.route("/juridiction/synoptique/services.pdf")
    @H.connexion_requise()
    def jur_synoptique_services_pdf():
        garde()
        pdf = construire_pdf("DIVISIONS / SERVICES ET CHEFS", [("", section_services())])
        return H.pdf_reponse(pdf, "synoptique_services.pdf")

    @app.route("/juridiction/synoptique/comites/<comite>.pdf")
    @H.connexion_requise()
    def jur_synoptique_comite_pdf(comite):
        garde()
        lib = comite_ou_404(comite)
        pdf = construire_pdf(lib.upper(), [("", section_comite(comite))], paysage=False)
        return H.pdf_reponse(pdf, f"comite_{comite}.pdf")

    # ============================================================ Excel : export, modèle, import
    ENT_UP = ["Circonscription","Zone pédagogique", "UP", "École siège", "RUP", "Téléphone RUP", "Co-RUP", "Téléphone Co-RUP", "Écoles membres"]

    def feuilles_export():
        d = identite()
        th = [f"{d['structure_nom']} — Tableau synoptique", f"Année scolaire {config.ANNEE_ACTIVE} · extrait le {date.today().strftime('%d/%m/%Y')}"]
        r = reseau()
        cs_noms = {c["id"]: c["nom"] for c in H.jur_cs_liste()}
        zones_noms = {z["id"]: z["nom"] for z in H.jur_zones()}
        lignes_id = [[lib, (d["resp_prise_fonction_txt"] if k == "resp_prise_fonction" else d.get(k)) or ""] for k, lib, _t in champs()]
        lignes_id += [[lib, d.get(k, 0)] for k, lib in NOMBRES[niveau()]]
        f = [("Identité", ["Rubrique", "Renseignement"], lignes_id, {"titre_haut": th}),
             ("Personnel", ENTETES_PERSONNEL, [ligne_personnel(i, x) for i, x in enumerate(personnel(), 1)], {"titre_haut": th})]
        if ddemp():
            f.append(("Circonscriptions", ENT_CS, lignes_cs(r), {"titre_haut": th}))
        f.append(("Zones", (["CS"] if ddemp() else []) + ENT_ZONES, lignes_zones(r["zones"], ddemp()), {"titre_haut": th}))
        f.append(("UP", ENT_UP, [[cs_noms.get(u["cs_id"], ""), zones_noms.get(u["zone_id"], ""), u["nom"], u["ecole_siege"] or "", u["rup_nom"] or "",
                                  u["rup_tel"] or "", u["corup_nom"] or "", u["corup_tel"] or "", u["nb_ecoles"] if u["nb_ecoles"] is not None else ""]
                                 for u in ups()], {"titre_haut": th}))
        f.append(("Écoles", (["CS"] if ddemp() else []) + ENT_ECOLES, lignes_ecoles(r, ddemp()), {"titre_haut": th}))
        f.append(("Services", ENT_SERVICES, lignes_services(services_liste()), {"titre_haut": th}))
        f.append(("Comités", ENT_MEMBRES, [[i, COMITES_COURTS.get(m["comite"], m["comite"]), m["libelle"] or "", m["nom_prenoms"], m["qualite"] or "",
                                           m["origine"] or "", m["contact"] or "", m["observations"] or ""] for i, m in enumerate(membres(), 1)],
                  {"titre_haut": th}))
        return f

    @app.route("/juridiction/synoptique/export.xlsx")
    @H.connexion_requise()
    def jur_synoptique_xlsx():
        garde()
        try:
            return H.xlsx.reponse_classeur("tableau_synoptique_structure.xlsx", feuilles_export())
        except H.xlsx.ExcelIndisponible:
            flash("Export Excel indisponible (module openpyxl absent).", "danger")
            return redirect(url_for("jur_synoptique"))

    @app.route("/juridiction/synoptique/personnel.xlsx")
    @H.connexion_requise()
    def jur_synoptique_personnel_xlsx():
        garde()
        d = identite(avec_nombres=False)
        return H.xlsx.reponse_xlsx("synoptique_personnel_structure.xlsx", ENTETES_PERSONNEL,
                                   [ligne_personnel(i, x) for i, x in enumerate(personnel(tous=request.args.get("tous") == "1"), 1)], "Personnel",
                                   [f"{d['structure_nom']} — personnel de la structure", f"Année scolaire {config.ANNEE_ACTIVE}"])

    # colonnes reconnues à l'import du personnel : clé -> intitulés possibles
    IMPORT_PERSONNEL = {
        "matricule": ("N° matricule", "matricule"), "nip": ("NIP",), "nom": ("Nom",), "prenoms": ("Prénoms", "prenom"),
        "nom_complet": ("Nom et prénoms", "nom et prenoms"), "sexe": ("Sexe",), "promotion": ("Promotion",),
        "categorie": ("Catégorie", "categorie"), "poste": ("Fonction / poste", "Fonction", "Poste"), "service_code": ("Service / division", "Service"),
        "role": ("Rôle", "role"), "grade": ("Grade",), "indice_reel": ("Indice réel",), "indice_paye": ("Indice payé",),
        "date_naissance": ("Date de naissance", "naissance"),
        "date_premiere_ps": ("Date de première prise de service", "premiere prise de service", "1re prise de service"),
        "date_ps_departement": ("Date de prise de service dans le département", "prise de service dans le departement", "PS departement"),
        "date_ps_commune": ("Prise de service dans la commune",),
        "date_ps_ecole": ("Date de prise de service dans la structure", "prise de service dans la structure", "PS structure",
                          "Prise de service au poste"),
        "date_derniere_formation": ("Date de la dernière formation", "derniere formation"),
        "diplome_academique": ("Diplôme académique le plus élevé", "diplome academique"), "annee_diplome": ("Année du diplôme académique",),
        "ceap": ("CEAP",), "annee_ceap": ("Année du CEAP",), "cap": ("CAP",), "annee_cap": ("Année du CAP",), "type_cap": ("Type de CAP",),
        "visite_aptitude": ("Visite d'aptitude",), "note_aptitude": ("Note d'aptitude", "Note de la visite d'aptitude", "Note"),
        "annee_aptitude": ("Année de la visite d'aptitude",), "note_evaluation": ("Note d'évaluation",),
        "nb_visites_cp": ("Visites du CP",), "nb_visites_ccs": ("Visites du CCS",), "participation_up": ("Participation à l'UP",),
        "gestion_collegiale": ("Gestion collégiale",), "departement_a_servir": ("Département à servir",),
        "telephone": ("Contact", "Téléphone"), "email": ("E-mail", "email"),
    }

    def lire_feuilles(fichier):
        """Classeur -> {nom de feuille normalisé: (entetes, lignes)} (ligne d'en-tête = première contenant « nom »)."""
        openpyxl = H.xlsx._openpyxl()
        try:
            wb = openpyxl.load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        except Exception as e_:  # noqa: BLE001
            raise ValueError("Fichier Excel illisible : enregistrez-le au format .xlsx.") from e_
        out = {}
        for ws in wb.worksheets:
            brutes = [list(r) for r in ws.iter_rows(values_only=True)][:5000]
            idx = next((i for i, r in enumerate(brutes[:40]) if any("nom" in H.xlsx.normaliser(v).split(" ") for v in r if v)), None)
            if idx is None:
                continue
            entetes = [str(v).strip() if v is not None else "" for v in brutes[idx]]
            lignes = [r for r in brutes[idx + 1:] if any(v not in (None, "") for v in r)]
            out[H.xlsx.normaliser(ws.title)] = (entetes, lignes)
        return out

    def annee_dans(txt):
        m = re.search(r"(19|20)\d{2}", txt or "")
        return m.group(0) if m else ""

    def importer_personnel(entetes, lignes):
        """Lignes Excel -> agents créés / mis à jour (rapprochement par matricule, NIP puis nom et prénoms)."""
        idx = {k: H.xlsx.colonne(entetes, *cands) for k, cands in IMPORT_PERSONNEL.items()}
        for k in ("nom", "prenoms"):        # « Nom et prénoms » ne doit pas être pris pour « Nom » ou « Prénoms »
            if idx["nom_complet"] is not None and idx[k] == idx["nom_complet"]:
                idx[k] = None
        if idx["nom"] is None and idx["nom_complet"] is None:
            raise ValueError("Colonne « Nom » (ou « Nom et prénoms ») introuvable dans la feuille Personnel.")
        svc = services_dict()
        par_nom = {H.xlsx.normaliser(n): c for c, n in svc.items()}
        crees = modifies = 0
        erreurs = []
        for n, l in enumerate(lignes, 1):
            val = lambda k: H.xlsx.valeur(l, idx[k])   # noqa: E731
            nom, prenoms = val("nom"), val("prenoms")
            if not nom and idx["nom_complet"] is not None:
                morceaux = val("nom_complet").split(" ", 1)
                nom, prenoms = morceaux[0], (morceaux[1] if len(morceaux) > 1 else prenoms)
            if not nom:
                continue
            form = {k: val(k) for k in IMPORT_PERSONNEL if k not in ("nom", "prenoms", "nom_complet")}
            form.update(nom=nom, prenoms=prenoms)
            code = form["service_code"]
            if code and code not in svc:
                form["service_code"] = par_nom.get(H.xlsx.normaliser(code), "") or next((c for c, lib in svc.items()
                                                                                        if H.xlsx.normaliser(code) in H.xlsx.normaliser(lib)), "")
            if not form["role"]:
                poste = (form["poste"] or "").lower()
                form["role"] = "ccs" if "circonscription" in poste else ("cp" if "conseiller" in poste else
                                                                          ("chef_service" if poste.startswith("chef") or "directeur" in poste else "administratif"))
            for k in ("ceap", "cap"):
                brut = form[k]
                form[k] = "oui" if brut.lower().startswith("oui") or (brut and not brut.lower().startswith("non") and annee_dans(brut)) else \
                    ("non" if brut.lower().startswith("non") else "")
                if not form[f"annee_{k}"]:
                    form[f"annee_{k}"] = annee_dans(brut)
            if idx["diplome_academique"] is not None and not form["annee_diplome"]:
                form["annee_diplome"] = annee_dans(form["diplome_academique"])
                form["diplome_academique"] = re.sub(r"\s*\((19|20)\d{2}\)\s*$", "", form["diplome_academique"])
            for k in ("date_naissance", "date_premiere_ps", "date_ps_departement", "date_ps_commune", "date_ps_ecole", "date_derniere_formation"):
                form[k] = H.xlsx.date_iso(form[k]) or form[k]
            # rapprochement avec un agent existant de la structure
            aid = None
            cid = cs_courante_id()
            perim = "(cs_id IS NULL OR cs_id=?)" if cid else "cs_id IS NULL"
            args = (cid,) if cid else ()
            if form["matricule"]:
                r = q(f"SELECT id FROM jur_agents WHERE matricule=? AND {perim}", (form["matricule"],) + args, un=True)
                aid = r["id"] if r else None
            if not aid and form["nip"]:
                r = q(f"SELECT id FROM jur_agents WHERE nip=? AND {perim}", (form["nip"].replace(" ", ""),) + args, un=True)
                aid = r["id"] if r else None
            if not aid:
                r = q(f"SELECT id FROM jur_agents WHERE UPPER(nom)=? AND LOWER(COALESCE(prenoms,''))=? AND {perim}",
                      (nom.upper(), (prenoms or "").lower()) + args, un=True)
                aid = r["id"] if r else None
            v, err = lire_agent(form, aid)
            if err:
                erreurs.append(f"Ligne {n} ({nom}) : " + " ".join(err))
                continue
            enregistrer_agent(v, aid)
            if aid:
                modifies += 1
            else:
                crees += 1
        return crees, modifies, erreurs

    COMITES_IMPORT = {H.xlsx.normaliser(v): k for k, v in list(COMITES.items()) + list(COMITES_COURTS.items())}
    COMITES_IMPORT.update({"conseil": "conseil", "cantine": "cantine", "cep": "cep", "autre": "autre", "conseil de direction": "conseil",
                           "comite de gestion des cantines scolaires": "cantine", "jury cep": "cep", "commission cep": "cep"})

    def importer_membres(entetes, lignes):
        idx = {"comite": H.xlsx.colonne(entetes, "Comité", "comite"), "libelle": H.xlsx.colonne(entetes, "Instance", "libelle"),
               "nom": H.xlsx.colonne(entetes, "Nom et prénoms", "nom"), "qualite": H.xlsx.colonne(entetes, "Qualité / fonction", "qualite", "fonction"),
               "origine": H.xlsx.colonne(entetes, "Structure d'origine", "origine", "structure"), "contact": H.xlsx.colonne(entetes, "Contact", "telephone"),
               "observations": H.xlsx.colonne(entetes, "Observations")}
        if idx["nom"] is None:
            return 0, 0
        n, refus = 0, 0
        for l in lignes:
            nom = H.xlsx.valeur(l, idx["nom"])
            if not nom:
                continue
            brut = H.xlsx.normaliser(H.xlsx.valeur(l, idx["comite"]))
            comite = COMITES_IMPORT.get(brut) or next((k for b, k in COMITES_IMPORT.items() if brut and (brut in b or b in brut)), None)
            if not comite:
                refus += 1
                continue
            v = {"nom_prenoms": nom[:120], "qualite": H.xlsx.valeur(l, idx["qualite"])[:60], "origine": H.xlsx.valeur(l, idx["origine"])[:80],
                 "contact": H.xlsx.valeur(l, idx["contact"])[:60], "observations": H.xlsx.valeur(l, idx["observations"])[:300],
                 "libelle": H.xlsx.valeur(l, idx["libelle"])[:120] if comite == "autre" else ""}
            existant = q("SELECT id FROM jur_synoptique_membres WHERE comite=? AND COALESCE(libelle,'')=? AND nom_prenoms=?",
                         (comite, v["libelle"], v["nom_prenoms"]), un=True)
            if existant:
                ex("UPDATE jur_synoptique_membres SET qualite=?, origine=?, contact=?, observations=?, maj=?, maj_par=? WHERE id=?",
                   (v["qualite"], v["origine"], v["contact"], v["observations"], H.maintenant(), uid(), existant["id"]))
            else:
                ex("INSERT INTO jur_synoptique_membres (annee, comite, libelle, ordre, nom_prenoms, qualite, origine, contact, observations, maj, maj_par) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (config.ANNEE_ACTIVE, comite, v["libelle"], n, v["nom_prenoms"], v["qualite"], v["origine"],
                                                     v["contact"], v["observations"], H.maintenant(), uid()))
            n += 1
        return n, refus

    @app.route("/juridiction/synoptique/import", methods=["GET", "POST"])
    @H.connexion_requise("jur_synoptique")
    def jur_synoptique_import():
        garde()
        if request.method == "POST":
            fichier = request.files.get("fichier")
            if not fichier or not fichier.filename:
                flash("Choisissez un fichier Excel (.xlsx).", "danger")
                return redirect(url_for("jur_synoptique_import"))
            try:
                feuilles = lire_feuilles(fichier)
            except (ValueError, H.xlsx.ExcelIndisponible) as e_:
                flash(str(e_), "danger")
                return redirect(url_for("jur_synoptique_import"))
            if not feuilles:
                flash("Aucune feuille exploitable : la ligne d'en-tête doit contenir une colonne « Nom ».", "danger")
                return redirect(url_for("jur_synoptique_import"))
            bilan = []
            cles = list(feuilles)
            feuille_perso = next((k for k in cles if k.startswith("personnel") or k.startswith("agents")), None)
            feuille_com = next((k for k in cles if k.startswith("comite")), None)
            if feuille_perso is None and feuille_com is None:
                feuille_perso = cles[0]        # un classeur d'une seule feuille = le personnel
            if feuille_perso is not None:
                try:
                    crees, modifies, erreurs = importer_personnel(*feuilles[feuille_perso])
                except ValueError as e_:
                    flash(str(e_), "danger")
                    return redirect(url_for("jur_synoptique_import"))
                bilan.append(f"Personnel : {crees} agent(s) ajouté(s), {modifies} mis à jour.")
                for e_ in erreurs[:15]:
                    flash(e_, "warning")
            if feuille_com is not None:
                n, refus = importer_membres(*feuilles[feuille_com])
                bilan.append(f"Comités : {n} membre(s) importé(s)" + (f", {refus} ligne(s) sans comité reconnu" if refus else "") + ".")
            H.journal("jur_synoptique", "import Excel : " + " ".join(bilan))
            flash("Import terminé. " + " ".join(bilan), "success")
            return redirect(url_for("jur_synoptique"))
        return render_template("jur_synoptique_import.html", **ctx("import", entetes=ENTETES_PERSONNEL, ent_membres=ENT_MEMBRES,
                                                                    services=list(services_dict().items())))

    @app.route("/juridiction/synoptique/modele.xlsx")
    @H.connexion_requise()
    def jur_synoptique_modele_xlsx():
        garde()
        svc = services_dict()
        code = "animation" if "animation" in svc else next(iter(svc), "")
        ex_ = [1, "123456", "123456789012", "AKPO Jean", "2005", "FE", "Conseiller pédagogique (CP)", code, "A1-5", 500, 480, "", "", "",
               "01/10/2005", "01/10/2010", "16/09/2022", "", "15/03/2024", "Licence (2003)", "CEAP oui (2008) / CAP oui (2012)", "oui", 15, 16,
               "97 00 00 00"]
        feuilles = [("Personnel", ENTETES_PERSONNEL, [ex_],
                     {"titre_haut": ["Modèle d'import du personnel de la structure — les anciennetés et la retraite sont calculées, laissez-les vides",
                                     "Service / division : code ou nom (" + ", ".join(f"{c} = {n}" for c, n in svc.items()) + ")"]}),
                    ("Comités", ENT_MEMBRES, [[1, "Conseil de direction", "", "HOUNGBO Pascal", "Président", "CS", "", ""],
                                              [2, "Comité de gestion des cantines", "", "DOSSOU Paul", "Membre", "Mairie / commune", "", ""],
                                              [3, "Autre instance", "Comité de suivi des constructions", "OLOU Rosine", "Rapporteur", "DDEMP", "", ""]])]
        try:
            return H.xlsx.reponse_classeur("modele_synoptique_structure.xlsx", feuilles)
        except H.xlsx.ExcelIndisponible:
            flash("Modèle Excel indisponible (module openpyxl absent).", "danger")
            return redirect(url_for("jur_synoptique_import"))
