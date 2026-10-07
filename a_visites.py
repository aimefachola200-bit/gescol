# -*- coding: utf-8 -*-
"""Animation pédagogique des applications « Circonscription scolaire » (CS) et « DDEMP » :
visites d'école, de classe et d'inspection des conseillers pédagogiques (CP) et des chefs de circonscription
scolaire (CCS), et bilan de leurs activités.

Routes (pages actives seulement en édition cs / ddemp) :
* /juridiction/visites                         jur_visites            liste filtrable + indicateurs + export Excel/PDF
* /juridiction/visites/nouvelle      GET/POST  jur_visite_form        saisie d'une visite
* /juridiction/visites/<id>          GET/POST  jur_visite_form        consultation / modification
* /juridiction/visites/<id>/supprimer    POST  jur_visite_supprimer
* /juridiction/visites/<id>/fiche.pdf          jur_visite_pdf         fiche officielle de la visite
* /juridiction/visites/fiche-vierge.pdf        jur_visite_vierge      fiche vierge imprimable
* /juridiction/bilan-activites                 jur_bilan_activites    bilan des CP et CCS (+ ?export=xlsx|pdf)

Sources des visites (réunies, puis dédoublonnées : même date + même enseignant + même visiteur) :
1. la table jur_visites (saisies de la structure elle-même : CS ou DDEMP) ;
2. à la DDEMP : la section « visites » des paquets des CS (jur_cs_sections) ;
3. la section « visites » transmise par chaque école (jur_sections), en lecture seule.
Dans l'application CS, chaque enregistrement recopie la liste des visites de l'année dans la section CS
« visites » (H.jur_ecrire_cs_section) : elle part ainsi vers la DDEMP avec le paquet de la CS.

Interface pour les autres modules :
    H.jur_bilan_visites(annee, cs_id=None) -> [{visiteur, fonction, cs_nom, visites_classe, visites_ecole,
        ecoles, enseignants, note_moyenne, ...}]   (visites_classe comprend les visites d'inspection)
"""
import json
import re
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime

from flask import abort, flash, g, redirect, render_template, request, url_for
from markupsafe import Markup, escape

import config
import jur_calc as C

TYPES = {"classe": "Visite de classe", "ecole": "Visite d'école", "inspection": "Visite d'inspection"}
QUALITES = {"CP": "Conseiller pédagogique (CP)", "CCS": "Chef de circonscription scolaire (CCS)"}
QUALITES_FILTRE = {"CP": "CP", "CCS": "CCS", "directeur": "Directeur d'école"}
FONCTIONS = {"CP": "Conseiller pédagogique", "CCS": "Chef de circonscription scolaire", "directeur": "Directeur d'école"}
SOURCES = {"cs": "Saisie de la CS", "ddemp": "Saisie de la DDEMP", "transmise": "Transmise par la CS",
           "ecole": "Déclarée par l'école"}
DISCIPLINES = ["Français", "Mathématiques", "Éducation scientifique et technologique", "Éducation sociale",
               "Éducation artistique", "Éducation physique et sportive", "Anglais", "Activités de la maternelle",
               "Gestion administrative et pédagogique de l'école"]
MOIS = [(9, "sept."), (10, "oct."), (11, "nov."), (12, "déc."), (1, "janv."), (2, "févr."), (3, "mars"),
        (4, "avr."), (5, "mai"), (6, "juin"), (7, "juil."), (8, "août")]
RE_HEURE = re.compile(r"^([01]?\d|2[0-3])[:hH]([0-5]\d)$")
EFFECTIF_MAX = 300
TEXTES = {"enseignant_nom": 120, "enseignant_nip": 20, "classe_nom": 60, "discipline": 120, "unite": 200,
          "dossier": 200, "sa": 300, "sequence": 300, "appreciation": 120, "observations": 4000,
          "points_forts": 4000, "insuffisances": 4000, "recommandations": 4000, "conseils": 4000, "suites": 4000}
ROLES_TOUT = ("admin", "fondateur", "responsable")
# couleurs des séries (palette catégorielle validée : bleu, orange, aqua — ordre fixe)
COUL = {"classe": "#2a78d6", "ecole": "#eb6834", "inspection": "#1baf7a"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_visites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    niveau TEXT,                          -- cs | ddemp (application qui a saisi)
    cs_id INTEGER, ecole_id INTEGER, ecole_code TEXT, ecole_nom TEXT,
    annee TEXT NOT NULL,                  -- année scolaire déduite de la date
    type TEXT NOT NULL,                   -- classe | ecole | inspection
    date TEXT NOT NULL, heure_debut TEXT, heure_fin TEXT,
    visiteur_cle TEXT, visiteur_qualite TEXT NOT NULL, visiteur_nom TEXT NOT NULL, visiteur_fonction TEXT,
    visiteur_agent_id INTEGER, visiteur_user_id INTEGER,
    enseignant_nom TEXT, enseignant_nip TEXT, classe_nom TEXT,
    eff_g INTEGER, eff_f INTEGER, eff_t INTEGER, ins_g INTEGER, ins_f INTEGER,
    discipline TEXT, unite TEXT, dossier TEXT, sa TEXT, sequence TEXT, note REAL, appreciation TEXT,
    observations TEXT, points_forts TEXT, insuffisances TEXT, recommandations TEXT, conseils TEXT, suites TEXT,
    cree_par INTEGER, cree_le TEXT, maj TEXT);
CREATE INDEX IF NOT EXISTS i_jur_visites ON jur_visites(annee, cs_id, ecole_id);
"""


# ======================================================================== outils purs
def lire_date(v):
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    return None


def annee_de(d):
    return f"{d.year}-{d.year + 1}" if d.month >= 9 else f"{d.year - 1}-{d.year}"


def lire_heure(v):
    s = str(v or "").strip()
    if not s:
        return ""
    m = RE_HEURE.match(s)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def lire_note(v):
    """Note sur 20 (virgule acceptée) ; vide -> None ; ValueError hors 0–20."""
    s = str(v if v is not None else "").strip().replace(",", ".")
    if not s:
        return None
    n = float(s)
    if not 0 <= n <= 20:
        raise ValueError(s)
    return round(n, 2)


def note_souple(v):
    """Note venant d'un paquet : None si absente ou invalide."""
    try:
        return lire_note(v)
    except (TypeError, ValueError):
        return None


def lire_effectif(v):
    s = str(v if v is not None else "").strip()
    if not s:
        return None
    if not s.isdigit() or int(s) > EFFECTIF_MAX:
        raise ValueError(s)
    return int(s)


def note_txt(n):
    if n is None:
        return ""
    return (f"{n:.2f}".rstrip("0").rstrip(".")).replace(".", ",") + "/20"


def num(v, dec=1):
    """Nombre au format français (virgule) ; « — » si None."""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{dec}f}".rstrip("0").rstrip(".").replace(".", ",") if dec else str(round(v))
    return str(v)


def pct(v):
    return "—" if v is None else f"{num(float(v))} %"


def norm(t):
    import unicodedata
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(t.replace("-", " ").replace("'", " ").replace(".", " ").split())


def cle_personne(nom):
    """Clé d'une personne insensible à l'ordre nom / prénoms, aux accents et à la casse."""
    return " ".join(sorted(norm(nom).split()))


def mois_de(iso):
    d = lire_date(iso)
    return d.month if d else None


# ======================================================================== graphiques SVG (côté serveur)
def svg_barres_empilees(categories, series, hauteur=190, titre=""):
    """Barres verticales empilées. categories : [libellé] ; series : [(nom, couleur, [valeurs])].
    Info-bulles natives (<title>) ; total affiché au-dessus de chaque barre non vide."""
    n = len(categories)
    if not n:
        return Markup("")
    totaux = [sum(s[2][i] for s in series) for i in range(n)]
    vmax = max(totaux + [1])
    lw = max(46, 7 * max(len(c) for c in categories) + 10)   # largeur d'une colonne (libellés lisibles)
    g_, h0 = 30, hauteur - 26
    largeur = 34 + n * lw
    out = [f'<svg viewBox="0 0 {largeur} {hauteur}" width="{largeur}" height="{hauteur}" class="graphe" role="img" '
           f'aria-label="{escape(titre)}" preserveAspectRatio="xMinYMin meet">']
    for k in range(0, 5):  # grille légère
        y = h0 - (h0 - g_) * k / 4
        val = vmax * k / 4
        out.append(f'<line x1="30" x2="{largeur}" y1="{y:.1f}" y2="{y:.1f}" stroke="#E4E7EC" stroke-width="1"/>')
        out.append(f'<text x="26" y="{y + 3:.1f}" text-anchor="end" font-size="9" fill="#667085">{round(val)}</text>')
    for i, cat in enumerate(categories):
        x = 34 + i * lw + 8
        y = h0
        for nom, coul, vals in series:
            v = vals[i]
            if not v:
                continue
            h = (h0 - g_) * v / vmax
            out.append(f'<rect x="{x}" y="{y - h + 1:.1f}" width="{lw - 16}" height="{max(h - 2, 1):.1f}" rx="3" '
                       f'fill="{coul}"><title>{escape(cat)} – {escape(nom)} : {v}</title></rect>')
            y -= h
        if totaux[i]:
            out.append(f'<text x="{x + (lw - 16) / 2}" y="{y - 4:.1f}" text-anchor="middle" font-size="10" '
                       f'font-weight="600" fill="#1D2939">{totaux[i]}</text>')
        out.append(f'<text x="{x + (lw - 16) / 2}" y="{hauteur - 8}" text-anchor="middle" font-size="10" '
                   f'fill="#475467">{escape(cat)}</text>')
    out.append(f'<line x1="30" x2="{largeur}" y1="{h0}" y2="{h0}" stroke="#98A2B3" stroke-width="1"/></svg>')
    return Markup("".join(out))


def svg_barres_h(items, couleur="#2a78d6", maxi=None, suffixe="", titre=""):
    """Barres horizontales : items = [(libellé, valeur, info-bulle)] ; maxi = échelle (100 pour un taux)."""
    if not items:
        return Markup("")
    vmax = maxi or max([v or 0 for _, v, _ in items] + [1])
    lh, lab, larg = 24, 190, 560
    out = [f'<svg viewBox="0 0 {larg} {len(items) * lh + 6}" width="{larg}" height="{len(items) * lh + 6}" '
           f'class="graphe" role="img" aria-label="{escape(titre)}">']
    for i, (lib, v, bulle) in enumerate(items):
        y = 4 + i * lh
        w = (larg - lab - 60) * (v or 0) / vmax if vmax else 0
        court = lib if len(lib) <= 30 else lib[:29] + "…"
        out.append(f'<text x="{lab - 6}" y="{y + 14}" text-anchor="end" font-size="11" fill="#344054">{escape(court)}'
                   f'<title>{escape(lib)}</title></text>')
        out.append(f'<rect x="{lab}" y="{y + 3}" width="{larg - lab - 60}" height="15" rx="3" fill="#F2F4F7"/>')
        if w > 0:
            out.append(f'<rect x="{lab}" y="{y + 3}" width="{max(w, 3):.1f}" height="15" rx="3" fill="{couleur}">'
                       f'<title>{escape(bulle)}</title></rect>')
        out.append(f'<text x="{lab + max(w, 0) + 5:.1f}" y="{y + 14}" font-size="11" font-weight="600" '
                   f'fill="#1D2939">{escape(num(v) if v is not None else "—")}{suffixe if v is not None else ""}</text>')
    out.append("</svg>")
    return Markup("".join(out))


# ======================================================================== module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    def juridiction_ou_404():
        if not config.juridiction():
            abort(404)

    # -------------------------------------------------------------- référentiels
    def ecoles_juridiction(cs_id=None):
        return {e["id"]: e for e in H.jur_ecoles(cs_id=cs_id)}

    def cs_courante_id():
        c = H.jur_cs_courante() if config.EDITION == "cs" else None
        return c["id"] if c else None

    def annees_dispo():
        a = set(H.jur_annees()) | {r["annee"] for r in q("SELECT DISTINCT annee FROM jur_visites")}
        return sorted(a, reverse=True)

    def annee_demandee(args):
        a = (args.get("annee") or "").strip()
        return a if re.match(r"^\d{4}-\d{4}$", a) else H.jur_annee()

    # -------------------------------------------------------------- réunion des visites (3 sources)
    def depuis_paquet(item, source, e, ecoles_code=None, cs=None):
        """Élément « visites » d'un paquet (école ou CS) → visite unifiée (lecture seule)."""
        it = item or {}
        if e is None and ecoles_code is not None and it.get("ecole_code"):
            e = ecoles_code.get(it.get("ecole_code"))
        qual = it.get("type") if it.get("type") in QUALITES_FILTRE else "CP"
        nature = it.get("nature") or it.get("type_visite")
        ens = str(it.get("enseignant") or "").strip()
        if nature not in TYPES:
            nature = "classe" if (ens or it.get("classe")) else "ecole"
        eg, ef = C.entier(it.get("effectif_g")), C.entier(it.get("effectif_f"))
        eff_connu = it.get("effectif_g") not in (None, "") or it.get("effectif_f") not in (None, "")
        return {
            "id": None, "source": source, "date": str(it.get("date") or "")[:10], "type": nature, "qualite": qual,
            "visiteur": str(it.get("visiteur") or "").strip() or "(visiteur non indiqué)",
            "ecole_id": e["id"] if e else None, "ecole_nom": e["nom"] if e else (it.get("ecole_nom") or "—"),
            "cs_id": e["cs_id"] if e else (cs["id"] if cs else None),
            "cs_nom": e["cs_nom"] if e else (cs["nom"] if cs else ""),
            "zone_id": e["zone_id"] if e else None, "zone_nom": (e["zone_nom"] if e else "") or "",
            "enseignant": ens, "nip": str(it.get("enseignant_nip") or ""), "classe": str(it.get("classe") or ""),
            "discipline": str(it.get("discipline") or "").strip(), "sequence": str(it.get("sequence") or ""),
            "note": note_souple(it.get("note")) if nature != "ecole" else None,
            "eff_g": eg if eff_connu else None, "eff_f": ef if eff_connu else None,
            "eff_t": eg + ef if eff_connu else None, "recommandations": str(it.get("recommandations") or ""),
            "heure_debut": str(it.get("heure_debut") or ""), "heure_fin": str(it.get("heure_fin") or ""),
            "cree_par": None, "visiteur_user_id": None, "visiteur_agent_id": None, "aussi_ecole": False}

    def depuis_table(r, e):
        return {
            "id": r["id"], "source": r["niveau"] or "cs", "date": r["date"], "type": r["type"],
            "qualite": r["visiteur_qualite"], "visiteur": r["visiteur_nom"],
            "ecole_id": r["ecole_id"], "ecole_nom": (e["nom"] if e else r["ecole_nom"]) or "—",
            "cs_id": e["cs_id"] if e else r["cs_id"], "cs_nom": (e["cs_nom"] if e else "") or "",
            "zone_id": e["zone_id"] if e else None, "zone_nom": (e["zone_nom"] if e else "") or "",
            "enseignant": r["enseignant_nom"] or "", "nip": r["enseignant_nip"] or "", "classe": r["classe_nom"] or "",
            "discipline": r["discipline"] or "", "sequence": r["sequence"] or r["sa"] or "", "note": r["note"],
            "eff_g": r["eff_g"], "eff_f": r["eff_f"], "eff_t": r["eff_t"], "recommandations": r["recommandations"] or "",
            "heure_debut": r["heure_debut"] or "", "heure_fin": r["heure_fin"] or "", "cree_par": r["cree_par"],
            "visiteur_user_id": r["visiteur_user_id"], "visiteur_agent_id": r["visiteur_agent_id"], "aussi_ecole": False}

    def cle_doublon(v):
        ens = cle_personne(v["enseignant"]) or f"ECOLE:{v['ecole_id'] or norm(v['ecole_nom'])}"
        return (v["date"], ens, cle_personne(v["visiteur"]))

    def collecter(annee, cs_id=None):
        """Toutes les visites de l'année (périmètre : la CS demandée ou toute la juridiction), dédoublonnées."""
        ecs = ecoles_juridiction(cs_id)
        tous = {e["id"]: e for e in H.jur_ecoles(actif=False)}
        sql, args = "SELECT * FROM jur_visites WHERE annee=?", [annee]
        if cs_id:
            sql += " AND cs_id=?"
            args.append(cs_id)
        brut = [depuis_table(r, tous.get(r["ecole_id"])) for r in q(sql + " ORDER BY date, heure_debut", tuple(args))]
        if config.EDITION == "ddemp":
            par_code = {e["code"]: e for e in tous.values()}
            for c in H.jur_cs_liste():
                if cs_id and c["id"] != cs_id:
                    continue
                for it in H.jur_cs_section(c["id"], "visites", annee) or []:
                    if isinstance(it, dict):
                        brut.append(depuis_paquet(it, "transmise", None, par_code, c))
        for eid, lst in H.jur_sections("visites", annee).items():
            e = ecs.get(eid)
            if not e:
                continue
            for it in lst or []:
                if isinstance(it, dict):
                    brut.append(depuis_paquet(it, "ecole", e))
        vues, out = {}, []
        for v in brut:
            k = cle_doublon(v)
            if k in vues:
                if v["source"] == "ecole":
                    vues[k]["aussi_ecole"] = True
                continue
            vues[k] = v
            out.append(v)
        out.sort(key=lambda v: (v["date"], v["heure_debut"]), reverse=True)
        return out

    def filtrer(visites, f):
        res = []
        for v in visites:
            if f.get("zone") and v["zone_id"] != f["zone"]:
                continue
            if f.get("ecole") and v["ecole_id"] != f["ecole"]:
                continue
            if f.get("visiteur") and cle_personne(v["visiteur"]) != f["visiteur"]:
                continue
            if f.get("type") in TYPES and v["type"] != f["type"]:
                continue
            if f.get("qualite") in QUALITES_FILTRE and v["qualite"] != f["qualite"]:
                continue
            if f.get("source") == "ecole" and v["source"] != "ecole":
                continue
            if f.get("source") == "structure" and v["source"] == "ecole":
                continue
            res.append(v)
        return res

    def indicateurs(visites):
        notes = [v["note"] for v in visites if v["note"] is not None]
        ens = {v["nip"] or cle_personne(v["enseignant"]) for v in visites if v["enseignant"]}
        return {"total": len(visites),
                "classe": sum(1 for v in visites if v["type"] == "classe"),
                "ecole": sum(1 for v in visites if v["type"] == "ecole"),
                "inspection": sum(1 for v in visites if v["type"] == "inspection"),
                "cp": sum(1 for v in visites if v["qualite"] == "CP"),
                "ccs": sum(1 for v in visites if v["qualite"] == "CCS"),
                "declarees": sum(1 for v in visites if v["source"] == "ecole"),
                "ecoles": len({v["ecole_id"] or v["ecole_nom"] for v in visites}),
                "enseignants": len(ens), "note": C.moyenne(notes), "nb_notes": len(notes)}

    # -------------------------------------------------------------- droits
    def responsable():
        return g.user["role"] in ROLES_TOUT

    def peut_modifier(r=None):
        """Saisie : droit jur_visites ; un CP ne modifie que ses propres visites."""
        if not g.get("user") or not H.peut("jur_visites"):
            return False
        if r is None or responsable():
            return True
        uid = g.user["id"]
        if r["cree_par"] == uid or r["visiteur_user_id"] == uid:
            return True
        if r["visiteur_agent_id"]:
            a = q("SELECT user_id FROM jur_agents WHERE id=?", (r["visiteur_agent_id"],), un=True)
            return bool(a and a["user_id"] == uid)
        return False

    # -------------------------------------------------------------- visiteurs possibles
    def visiteurs_possibles():
        """Options du champ « visiteur » : {cle, nom, qualite, fonction, agent_id, user_id, cs_id}."""
        opts = []
        s = H.jur_structure() or {}
        if config.EDITION == "cs" and s.get("responsable_nom"):
            opts.append({"cle": "r", "nom": s["responsable_nom"], "qualite": "CCS",
                         "fonction": "Chef de la circonscription scolaire", "agent_id": None, "user_id": None,
                         "cs_id": cs_courante_id()})
        if config.EDITION == "ddemp":
            for c in H.jur_cs_liste():
                if c["ccs_nom"]:
                    opts.append({"cle": f"c:{c['id']}", "nom": c["ccs_nom"], "qualite": "CCS",
                                 "fonction": f"Chef de la CS de {c['nom']}", "agent_id": None, "user_id": None,
                                 "cs_id": c["id"]})
        sql, args = "SELECT * FROM jur_agents WHERE actif=1", ()
        if config.EDITION == "cs":
            sql += " AND (cs_id IS NULL OR cs_id=?)"
            args = (cs_courante_id() or 0,)
        for a in q(sql + " ORDER BY nom, prenoms", args):
            try:
                d = json.loads(a["donnees"] or "{}")
            except ValueError:
                d = {}
            p = norm(a["poste"])
            if d.get("role") == "ccs" or ("CHEF" in p and "CIRCONSCRIPTION" in p):
                qual = "CCS"
            elif d.get("role") == "cp" or "CONSEILLER PEDAGOGIQUE" in p:
                qual = "CP"
            else:
                continue
            nom = f"{(a['nom'] or '').upper()} {a['prenoms'] or ''}".strip()
            if any(cle_personne(o["nom"]) == cle_personne(nom) and o["qualite"] == qual for o in opts):
                continue
            opts.append({"cle": f"a:{a['id']}", "nom": nom, "qualite": qual, "fonction": a["poste"] or FONCTIONS[qual],
                         "agent_id": a["id"], "user_id": a["user_id"], "cs_id": a["cs_id"]})
        for u in q("SELECT id, nom FROM utilisateurs WHERE role='cp' AND actif=1 ORDER BY nom"):
            if any(o["user_id"] == u["id"] for o in opts):
                continue
            opts.append({"cle": f"u:{u['id']}", "nom": u["nom"], "qualite": "CP",
                         "fonction": "Conseiller pédagogique", "agent_id": None, "user_id": u["id"], "cs_id": None})
        if g.get("user") and g.user["role"] == "cp":   # un CP ne saisit que ses propres visites
            uid = g.user["id"]
            opts = [o for o in opts if o["user_id"] == uid] or [
                {"cle": f"u:{uid}", "nom": g.user["nom"], "qualite": "CP", "fonction": "Conseiller pédagogique",
                 "agent_id": None, "user_id": uid, "cs_id": None}]
        return opts

    def cle_signature(r):
        cle = r["visiteur_cle"] or ""
        if cle.startswith("a:"):
            return f"jur:agent:{cle[2:]}"
        if cle == "r":
            return "jur:structure:responsable"
        if cle.startswith("c:"):
            return f"jur:cs:{cle[2:]}"
        return None

    # -------------------------------------------------------------- données des écoles pour le formulaire
    def donnees_ecole(eid, annee):
        """{"ens": [{n, nip, c}], "cl": [{n, g, f}]} : personnel enseignant et classes transmis par l'école."""
        pers = C.enseignants(H.jur_section(eid, "personnel", annee) or [])["liste"]
        ens = [{"n": f"{(p.get('nom') or '').upper()} {p.get('prenoms') or ''}".strip(), "nip": p.get("nip") or "",
                "c": p.get("classe") or ""} for p in pers]
        eff = H.jur_section(eid, "effectifs", annee) or {}
        cl = [{"n": c.get("nom") or c.get("niveau") or "", "g": C.entier(c.get("garcons")),
               "f": C.entier(c.get("filles"))} for c in (eff.get("classes") or [])]
        return {"ens": ens, "cl": cl}

    def inscrits_classe(eid, annee, classe_nom):
        for c in donnees_ecole(eid, annee)["cl"]:
            if norm(c["n"]) == norm(classe_nom):
                return c
        return None

    # -------------------------------------------------------------- recopie vers la section CS « visites »
    def vers_paquet(r):
        """Ligne jur_visites → élément de la section « visites » (format jur_format + compléments)."""
        return {"date": r["date"], "type": r["visiteur_qualite"], "nature": r["type"], "visiteur": r["visiteur_nom"],
                "visiteur_fonction": r["visiteur_fonction"] or "", "enseignant": r["enseignant_nom"] or "",
                "enseignant_nip": r["enseignant_nip"] or "", "classe": r["classe_nom"] or "",
                "discipline": r["discipline"] or "", "sequence": r["sequence"] or "", "note": r["note"],
                "effectif_g": r["eff_g"], "effectif_f": r["eff_f"], "recommandations": r["recommandations"] or "",
                "ecole_code": r["ecole_code"] or "", "ecole_nom": r["ecole_nom"] or "",
                "heure_debut": r["heure_debut"] or "", "heure_fin": r["heure_fin"] or "", "unite": r["unite"] or "",
                "dossier": r["dossier"] or "", "sa": r["sa"] or "", "appreciation": r["appreciation"] or "",
                "observations": r["observations"] or "", "points_forts": r["points_forts"] or "",
                "insuffisances": r["insuffisances"] or "", "conseils": r["conseils"] or "", "suites": r["suites"] or ""}

    def synchroniser(*annees):
        """Application CS : recopie les visites de l'année dans la section CS « visites » (envoi à la DDEMP)."""
        if config.EDITION != "cs":
            return
        cid = cs_courante_id()
        if not cid:
            return
        for a in {x for x in annees if x}:
            rows = q("SELECT * FROM jur_visites WHERE annee=? AND (cs_id=? OR cs_id IS NULL) ORDER BY date, heure_debut",
                     (a, cid))
            H.jur_ecrire_cs_section(cid, "visites", [vers_paquet(r) for r in rows], a)

    # -------------------------------------------------------------- bilan
    def bilan(annee, cs_id=None):
        visites = [v for v in collecter(annee, cs_id) if v["qualite"] in ("CP", "CCS")]
        ecs = ecoles_juridiction(cs_id)
        pers = H.jur_sections("personnel", annee, list(ecs))
        nb_ens = {eid: C.enseignants(pers.get(eid))["t"] for eid in ecs}
        zones = list(H.jur_zones(cs_id))
        zones_cp = {}
        for z in zones:
            if z["cp_nom"]:
                zones_cp.setdefault(cle_personne(z["cp_nom"]), set()).add(z["id"])

        def ens_cle(v):
            return v["nip"] or cle_personne(v["enseignant"])

        # ---- par visiteur
        groupes = {}
        for v in visites:
            groupes.setdefault(cle_personne(v["visiteur"]), []).append(v)
        par_visiteur = []
        for k, vs in groupes.items():
            qual = Counter(v["qualite"] for v in vs).most_common(1)[0][0]
            nom = Counter(v["visiteur"] for v in vs).most_common(1)[0][0]
            cs_ids = {v["cs_id"] for v in vs if v["cs_id"]}
            cs_noms = sorted({v["cs_nom"] for v in vs if v["cs_nom"]})
            if qual == "CP" and k in zones_cp:
                perim = {e for e, x in ecs.items() if x["zone_id"] in zones_cp[k]}
                perim_lib = ", ".join(z["nom"] for z in zones if z["id"] in zones_cp[k])
            else:
                perim = {e for e, x in ecs.items() if x["cs_id"] in cs_ids}
                perim_lib = ("Circonscription" if qual == "CCS" else "Circonscription (zone du CP non renseignée)")
            couvertes = {v["ecole_id"] for v in vs if v["ecole_id"]}
            ens_vis = {ens_cle(v) for v in vs if v["enseignant"]}
            ens_vis_perim = {ens_cle(v) for v in vs if v["enseignant"] and v["ecole_id"] in perim}
            ens_perim = sum(nb_ens.get(e, 0) for e in perim)
            notes = [v["note"] for v in vs if v["note"] is not None]
            par_mois = Counter(mois_de(v["date"]) for v in vs)
            par_visiteur.append({
                "cle": k, "visiteur": nom, "qualite": qual, "fonction": FONCTIONS[qual], "cs_nom": ", ".join(cs_noms),
                "visites_classe": sum(1 for v in vs if v["type"] in ("classe", "inspection")),
                "visites_inspection": sum(1 for v in vs if v["type"] == "inspection"),
                "visites_ecole": sum(1 for v in vs if v["type"] == "ecole"), "total": len(vs),
                "ecoles": len(couvertes), "ecoles_perimetre": len(perim), "perimetre": perim_lib,
                "ecoles_perimetre_visitees": len(couvertes & perim), "enseignants_perimetre_visites": min(len(ens_vis_perim), ens_perim),
                "taux_ecoles": C.taux(len(couvertes & perim), len(perim)),
                "enseignants": len(ens_vis), "enseignants_perimetre": ens_perim,
                "taux_enseignants": C.taux(min(len(ens_vis_perim), ens_perim), ens_perim),
                "note_moyenne": C.moyenne(notes), "nb_notes": len(notes),
                "declarees": sum(1 for v in vs if v["source"] == "ecole"),
                "mois": [par_mois.get(m, 0) for m, _ in MOIS],
                "disciplines": dict(Counter(v["discipline"] or "Non précisée" for v in vs
                                            if v["type"] != "ecole"))})
        par_visiteur.sort(key=lambda x: (0 if x["qualite"] == "CCS" else 1, -x["total"], x["visiteur"]))

        # ---- par zone pédagogique
        par_zone = []
        for z in zones:
            ez = {e for e, x in ecs.items() if x["zone_id"] == z["id"]}
            vz = [v for v in visites if v["ecole_id"] in ez]
            ens_t = sum(nb_ens.get(e, 0) for e in ez)
            ens_v = len({ens_cle(v) for v in vz if v["enseignant"]})
            par_zone.append({"zone": z["nom"], "cs_nom": z["cs_nom"], "cp": z["cp_nom"] or "", "ecoles": len(ez),
                             "ecoles_visitees": len({v["ecole_id"] for v in vz}),
                             "taux_ecoles": C.taux(len({v["ecole_id"] for v in vz}), len(ez)),
                             "enseignants": ens_t, "enseignants_visites": min(ens_v, ens_t) if ens_t else ens_v,
                             "taux_enseignants": C.taux(min(ens_v, ens_t), ens_t),
                             "visites_classe": sum(1 for v in vz if v["type"] in ("classe", "inspection")),
                             "visites_ecole": sum(1 for v in vz if v["type"] == "ecole"),
                             "note": C.moyenne([v["note"] for v in vz if v["note"] is not None])})

        # ---- par CS (DDEMP)
        par_cs = []
        if config.EDITION == "ddemp":
            for c in H.jur_cs_liste():
                if cs_id and c["id"] != cs_id:
                    continue
                ec = {e for e, x in ecs.items() if x["cs_id"] == c["id"]}
                vc = [v for v in visites if v["cs_id"] == c["id"]]
                ens_t = sum(nb_ens.get(e, 0) for e in ec)
                ens_v = len({ens_cle(v) for v in vc if v["enseignant"] and v["ecole_id"] in ec})
                par_cs.append({"cs_id": c["id"], "cs_nom": c["nom"],
                               "saisies": sum(1 for v in vc if v["source"] != "ecole"),
                               "transmises_cs": sum(1 for v in vc if v["source"] == "transmise"),
                               "declarees": sum(1 for v in vc if v["source"] == "ecole"), "total": len(vc),
                               "visites_classe": sum(1 for v in vc if v["type"] in ("classe", "inspection")),
                               "visites_ecole": sum(1 for v in vc if v["type"] == "ecole"),
                               "visiteurs": len({cle_personne(v["visiteur"]) for v in vc}),
                               "ecoles": len(ec), "ecoles_visitees": len({v["ecole_id"] for v in vc if v["ecole_id"] in ec}),
                               "taux_ecoles": C.taux(len({v["ecole_id"] for v in vc if v["ecole_id"] in ec}), len(ec)),
                               "enseignants": ens_t, "enseignants_visites": ens_v,
                               "taux_enseignants": C.taux(min(ens_v, ens_t), ens_t),
                               "note": C.moyenne([v["note"] for v in vc if v["note"] is not None])})

        # ---- totaux, mois, disciplines
        ens_total = sum(nb_ens.values())
        ens_v = len({ens_cle(v) for v in visites if v["enseignant"] and v["ecole_id"] in ecs})
        couv = len({v["ecole_id"] for v in visites if v["ecole_id"] in ecs})
        mois = {t: [0] * len(MOIS) for t in TYPES}
        idx = {m: i for i, (m, _) in enumerate(MOIS)}
        for v in visites:
            m = mois_de(v["date"])
            if m in idx:
                mois[v["type"]][idx[m]] += 1
        disc = {}
        for v in visites:
            if v["type"] == "ecole":
                continue
            d = disc.setdefault(v["discipline"] or "Non précisée", {"n": 0, "notes": []})
            d["n"] += 1
            if v["note"] is not None:
                d["notes"].append(v["note"])
        disciplines = sorted(({"discipline": k, "n": d["n"], "note": C.moyenne(d["notes"])} for k, d in disc.items()),
                             key=lambda x: (-x["n"], x["discipline"]))
        tot = indicateurs(visites)
        tot.update(ecoles_total=len(ecs), ecoles_visitees=couv, taux_ecoles=C.taux(couv, len(ecs)),
                   enseignants_total=ens_total, enseignants_visites=min(ens_v, ens_total) if ens_total else ens_v,
                   taux_enseignants=C.taux(min(ens_v, ens_total), ens_total), visiteurs=len(par_visiteur))
        return {"annee": annee, "visiteurs": par_visiteur, "zones": par_zone, "cs": par_cs, "mois": mois,
                "disciplines": disciplines, "tot": tot}

    def jur_bilan_visites(annee=None, cs_id=None):
        """Bilan par visiteur (CP / CCS) pour les tableaux de bord : liste de dict
        {visiteur, fonction, cs_nom, visites_classe, visites_ecole, ecoles, enseignants, note_moyenne}
        (+ qualite, total, taux_ecoles, taux_enseignants, visites_inspection)."""
        b = bilan(annee or H.jur_annee(), cs_id)
        cles = ("visiteur", "fonction", "cs_nom", "visites_classe", "visites_ecole", "ecoles", "enseignants",
                "note_moyenne", "qualite", "total", "taux_ecoles", "taux_enseignants", "visites_inspection")
        return [{k: v[k] for k in cles} for v in b["visiteurs"]]

    H.jur_bilan_visites = jur_bilan_visites

    # -------------------------------------------------------------- PDF : en-tête, signataire, cachet
    def infos_haut(ecole_nom=None, cs_nom=None):
        s = H.jur_structure() or {}
        lst = [("DDEMP", s.get("departement") or "")]
        cs = s.get("cs") if config.EDITION == "cs" else cs_nom
        if cs:
            lst.append(("CS", cs))
        if ecole_nom:
            lst.append(("ÉCOLE", ecole_nom))
        return lst

    def signataire():
        """(titre, nom, image) du responsable de la structure (CCS ou Directeur départemental)."""
        s = H.jur_structure() or {}
        titre = (s.get("responsable_titre") or ("Le Chef de la Circonscription Scolaire" if config.EDITION == "cs"
                                                 else "Le Directeur Départemental")).upper()
        return titre, s.get("responsable_nom") or "", H.pdfs.image_data_url(H.signature("jur:structure:responsable"))

    @contextmanager
    def cachet_structure():
        """Le cachet dessiné par document_tableau est celui de config.ECOLE["_cachet"] : on y met, le temps
        du PDF, le cachet de la structure (service de direction configuré, sinon cachet généré)."""
        s = H.jur_structure() or {}
        ca = None
        try:
            r = q("SELECT * FROM jur_services WHERE niveau=? AND actif=1 AND (cachet_sup<>'' OR cachet_centre<>'') "
                  "ORDER BY CASE WHEN code IN ('direction','ccs','responsable') THEN 0 ELSE 1 END, ordre LIMIT 1",
                  (config.EDITION,), un=True)
            if r:
                ca = (r["cachet_sup"] or "", r["cachet_inf"] or "", r["cachet_centre"] or "", r["cachet_couleur"] or "bleu")
        except Exception:  # noqa: BLE001
            ca = None
        if not ca and s:
            if config.EDITION == "cs":
                ca = (f"CIRCONSCRIPTION SCOLAIRE DE {s.get('cs') or ''}", f"DDEMP {s.get('departement') or ''}",
                      "LE CHEF|CS", "bleu")
            else:
                ca = (f"DDEMP {s.get('departement') or ''}", "MEMP – RÉPUBLIQUE DU BÉNIN", "LE DIRECTEUR|DÉPARTEMENTAL",
                      "bleu")
        ancien = config.ECOLE.get("_cachet")
        config.ECOLE["_cachet"] = ca
        try:
            yield
        finally:
            config.ECOLE["_cachet"] = ancien

    # -------------------------------------------------------------- liste
    def filtres_liste(args):
        cs_id = args.get("cs", type=int) if config.EDITION == "ddemp" else None
        return {"annee": annee_demandee(args), "cs": cs_id, "zone": args.get("zone", type=int),
                "ecole": args.get("ecole", type=int), "visiteur": (args.get("visiteur") or "").strip(),
                "type": args.get("type", ""), "qualite": args.get("qualite", ""), "source": args.get("source", "")}

    @app.route("/juridiction/visites")
    @H.connexion_requise()
    def jur_visites():
        juridiction_ou_404()
        f = filtres_liste(request.args)
        toutes = collecter(f["annee"], f["cs"])
        liste = filtrer(toutes, f)
        ind = indicateurs(liste)
        if request.args.get("export") in ("xlsx", "pdf"):
            return exporter_liste(liste, ind, f, request.args["export"])
        visiteurs = sorted({cle_personne(v["visiteur"]): v["visiteur"] for v in toutes}.items(), key=lambda x: x[1])
        for v in liste:
            v["modifiable"] = bool(v["id"]) and peut_modifier(v)
        return render_template("jur_visites.html", liste=liste, ind=ind, f=f, annees=annees_dispo(),
                               cs=H.jur_cs_liste(), zones=H.jur_zones(f["cs"]), ecoles=H.jur_ecoles(cs_id=f["cs"]),
                               visiteurs=visiteurs, TYPES=TYPES, QUALITES_FILTRE=QUALITES_FILTRE, SOURCES=SOURCES,
                               saisie=H.peut("jur_visites"), note_txt=note_txt, num=num,
                               args={k: v for k, v in request.args.items() if k != "export"})

    def exporter_liste(liste, ind, f, fmt):
        s = H.jur_structure() or {}
        lignes = [[i, H.pdfs.date_fr(v["date"]), TYPES.get(v["type"], v["type"]),
                   f"{v['visiteur']} ({QUALITES_FILTRE.get(v['qualite'], v['qualite'])})", v["ecole_nom"],
                   v["zone_nom"], v["enseignant"] or "—", v["classe"], v["discipline"],
                   v["eff_t"] if v["eff_t"] is not None else "", v["note"] if fmt == "xlsx" else note_txt(v["note"]),
                   SOURCES.get(v["source"], v["source"])] for i, v in enumerate(liste, 1)]
        ent = ["N°", "Date", "Type", "Visiteur", "École", "Zone", "Enseignant(e)", "Classe", "Discipline", "Présents",
               "Note /20", "Source"]
        if config.EDITION == "ddemp":
            ent.insert(5, "CS")
            for l, v in zip(lignes, liste):
                l.insert(5, v["cs_nom"])
        H.journal("jur_visites_export", f"{fmt} {f['annee']}")
        if fmt == "xlsx":
            return H.xlsx.reponse_xlsx(f"visites_{f['annee']}.xlsx", ent, lignes, "Visites",
                                       [s.get("nom") or "", f"Visites d'école et de classe – {f['annee']}"])
        if not lignes:
            lignes = [[""] * len(ent)]
            lignes[0][1] = "Aucune visite pour ces critères."
        larg = [5, 13, 14, 30, 30, 18, 26, 10, 22, 9, 9, 18]
        if config.EDITION == "ddemp":
            larg.insert(5, 14)
        pdf = H.pdfs.document_tableau(
            "LISTE DES VISITES D'ÉCOLE ET DE CLASSE", ent, lignes, paysage=True, largeurs=larg, taille=7,
            sous_titre=f"Conseillers pédagogiques (CP) et chefs de circonscription (CCS) — année scolaire {f['annee']}",
            infos=[("Structure", s.get("nom")), ("Visites", ind["total"]),
                   ("Classe / école / inspection", f"{ind['classe']} / {ind['ecole']} / {ind['inspection']}"),
                   ("Par CP / par CCS", f"{ind['cp']} / {ind['ccs']}"), ("Écoles visitées", ind["ecoles"]),
                   ("Note moyenne", note_txt(ind["note"]) or "—")],
            infos_haut=infos_haut(),
            notes_bas=["Les visites « déclarées par l'école » proviennent des fichiers de transmission des écoles ; "
                       "une visite déclarée aussi saisie par la structure n'est comptée qu'une fois."])
        return H.pdf_reponse(pdf, f"visites_{f['annee']}.pdf")

    # -------------------------------------------------------------- saisie
    def lire_formulaire(f, ancienne=None):
        err, avert = [], []
        d = lire_date(f.get("date"))
        if not d:
            err.append("Date de la visite invalide.")
        elif d > date.today():
            err.append("La date de la visite ne peut pas être dans le futur.")
        typ = f.get("type") if f.get("type") in TYPES else None
        if not typ:
            err.append("Choisissez le type de visite.")
        val = {k: (f.get(k) or "").strip()[:m] for k, m in TEXTES.items()}
        # école
        eid = f.get("ecole_id", "")
        e = H.jur_ecole(int(eid)) if eid.isdigit() else None
        if not e or (not e["actif"] and not (ancienne and ancienne["ecole_id"] == e["id"])):
            err.append("Choisissez l'école visitée.")
            e = None
        elif config.EDITION == "cs" and cs_courante_id() and e["cs_id"] != cs_courante_id():
            err.append("Cette école n'est pas de la circonscription.")
            e = None
        # visiteur
        opts = {o["cle"]: o for o in visiteurs_possibles()}
        cle = f.get("visiteur", "")
        if cle in opts:
            o = opts[cle]
            vis = {"visiteur_cle": cle, "visiteur_nom": o["nom"], "visiteur_qualite": o["qualite"],
                   "visiteur_fonction": o["fonction"], "visiteur_agent_id": o["agent_id"], "visiteur_user_id": o["user_id"]}
        elif cle == "autre" and responsable():
            nom = (f.get("visiteur_nom") or "").strip()[:120]
            qual = f.get("visiteur_qualite") if f.get("visiteur_qualite") in QUALITES else None
            if not nom or not qual:
                err.append("Visiteur hors liste : indiquez son nom et précisez CP ou CCS.")
            vis = {"visiteur_cle": "autre", "visiteur_nom": nom, "visiteur_qualite": qual or "CP",
                   "visiteur_fonction": FONCTIONS.get(qual or "CP"), "visiteur_agent_id": None, "visiteur_user_id": None}
        else:
            err.append("Choisissez le visiteur (CP ou CCS).")
            vis = {"visiteur_cle": "", "visiteur_nom": "", "visiteur_qualite": "CP", "visiteur_fonction": "",
                   "visiteur_agent_id": None, "visiteur_user_id": None}
        if val["enseignant_nip"] and not val["enseignant_nip"].isdigit():
            err.append("Le NIP de l'enseignant ne contient que des chiffres.")
        if typ in ("classe", "inspection"):
            if not val["enseignant_nom"]:
                err.append("Une visite de classe ou d'inspection concerne un enseignant : indiquez-le.")
            if not val["classe_nom"]:
                err.append("Indiquez la classe visitée.")
        hd, hf = lire_heure(f.get("heure_debut")), lire_heure(f.get("heure_fin"))
        if hd is None or hf is None:
            err.append("Heures invalides (format 08:30).")
        elif hd and hf and hf <= hd:
            err.append("L'heure de fin doit être après l'heure de début.")
        eff = {}
        try:
            eff = {k: lire_effectif(f.get(k)) for k in ("eff_g", "eff_f")}
        except ValueError:
            err.append(f"Effectifs présents invalides (nombres entiers de 0 à {EFFECTIF_MAX}).")
        try:
            note = lire_note(f.get("note"))
        except ValueError:
            err.append("La note doit être comprise entre 0 et 20.")
            note = None
        if note is not None and typ == "ecole":
            err.append("La note sur 20 ne concerne que les visites de classe ou d'inspection.")
        ins = None
        if e and val["classe_nom"] and d:
            ins = inscrits_classe(e["id"], annee_de(d), val["classe_nom"]) or \
                inscrits_classe(e["id"], H.jur_annee(), val["classe_nom"])
        if ins:
            if eff.get("eff_g") is None and eff.get("eff_f") is None and ancienne is None:
                eff = {"eff_g": ins["g"], "eff_f": ins["f"]}   # pré-remplissage si non saisi
            if (eff.get("eff_g") or 0) > ins["g"] or (eff.get("eff_f") or 0) > ins["f"]:
                avert.append(f"Attention : l'effectif présent dépasse l'effectif inscrit transmis par l'école "
                             f"({ins['g']} G / {ins['f']} F).")
        total = None
        if eff.get("eff_g") is not None or eff.get("eff_f") is not None:
            total = (eff.get("eff_g") or 0) + (eff.get("eff_f") or 0)
        val.update(vis, type=typ, date=d.isoformat() if d else "", annee=annee_de(d) if d else "",
                   heure_debut=hd or "", heure_fin=hf or "", eff_g=eff.get("eff_g"), eff_f=eff.get("eff_f"), eff_t=total,
                   ins_g=ins["g"] if ins else None, ins_f=ins["f"] if ins else None, note=note,
                   ecole_id=e["id"] if e else None, ecole_code=e["code"] if e else "", ecole_nom=e["nom"] if e else "",
                   cs_id=e["cs_id"] if e else None, niveau=config.EDITION)
        return val, err, avert

    CHAMPS = ("niveau", "cs_id", "ecole_id", "ecole_code", "ecole_nom", "annee", "type", "date", "heure_debut",
              "heure_fin", "visiteur_cle", "visiteur_qualite", "visiteur_nom", "visiteur_fonction", "visiteur_agent_id",
              "visiteur_user_id", "enseignant_nom", "enseignant_nip", "classe_nom", "eff_g", "eff_f", "eff_t", "ins_g",
              "ins_f", "discipline", "unite", "dossier", "sa", "sequence", "note", "appreciation", "observations",
              "points_forts", "insuffisances", "recommandations", "conseils", "suites")

    def rendu_form(v, visite=None, code=200):
        a = (v.get("annee") if isinstance(v, dict) else None) or H.jur_annee()
        ecs = list(H.jur_ecoles(cs_id=cs_courante_id()))
        if visite and visite["ecole_id"] and all(e["id"] != visite["ecole_id"] for e in ecs):
            e = H.jur_ecole(visite["ecole_id"])
            if e:
                ecs.append(e)
        data = {e["id"]: donnees_ecole(e["id"], a) for e in ecs}
        if not any(d["ens"] or d["cl"] for d in data.values()) and a != H.jur_annee():
            data = {e["id"]: donnees_ecole(e["id"], H.jur_annee()) for e in ecs}
        groupes = {}
        for e in ecs:   # écoles regroupées par zone (par CS et zone à la DDEMP), dans l'ordre de la liste
            lib = (f"{e['cs_nom']} – " if config.EDITION == "ddemp" else "") + (e["zone_nom"] or "Sans zone")
            groupes.setdefault(lib, []).append(e)
        return render_template("jur_visite_form.html", v=v, visite=visite, ecoles=ecs, groupes=groupes,
                               ecoles_json=json.dumps(data, ensure_ascii=False), visiteurs=visiteurs_possibles(),
                               TYPES=TYPES, QUALITES=QUALITES, DISCIPLINES=DISCIPLINES, saisie=peut_modifier(visite),
                               responsable=responsable(), aujourdhui=date.today().isoformat(),
                               supprimable=bool(visite) and peut_modifier(visite)), code

    @app.route("/juridiction/visites/nouvelle", methods=["GET", "POST"])
    @app.route("/juridiction/visites/<int:vid>", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_visite_form(vid=None):
        juridiction_ou_404()
        visite = None
        if vid:
            visite = q("SELECT * FROM jur_visites WHERE id=?", (vid,), un=True)
            if not visite:
                abort(404)
            cs = cs_courante_id()
            if cs and visite["cs_id"] and visite["cs_id"] != cs:
                abort(404)
        elif not H.peut("jur_visites"):
            abort(403)
        if request.method == "POST":
            if not peut_modifier(visite):
                abort(403)
            val, err, avert = lire_formulaire(request.form, visite)
            if err:
                for m in err:
                    flash(m, "danger")
                return rendu_form(dict(request.form.items()), visite, 400)
            if visite:
                ex(f"UPDATE jur_visites SET {', '.join(k + '=?' for k in CHAMPS)}, maj=? WHERE id=?",
                   tuple(val[k] for k in CHAMPS) + (H.maintenant(), vid))
                H.journal("jur_visite_modif", f"{vid} {val['date']} {val['visiteur_nom']}")
                synchroniser(val["annee"], visite["annee"])
                flash("Visite mise à jour.", "success")
            else:
                vid = ex(f"INSERT INTO jur_visites ({', '.join(CHAMPS)}, cree_par, cree_le, maj) "
                         f"VALUES ({', '.join('?' * (len(CHAMPS) + 3))})",
                         tuple(val[k] for k in CHAMPS) + (g.user["id"], H.maintenant(), H.maintenant()))
                H.journal("jur_visite_ajout", f"{val['date']} {val['visiteur_nom']} {val['ecole_nom']}")
                synchroniser(val["annee"])
                flash("Visite enregistrée.", "success")
            for m in avert:
                flash(m, "warning")
            return redirect(url_for("jur_visite_form", vid=vid))
        if visite:
            return rendu_form(dict(visite), visite)
        opts = visiteurs_possibles()
        v = {"date": date.today().isoformat(), "type": request.args.get("type") if request.args.get("type") in TYPES
             else "classe", "ecole_id": request.args.get("ecole", type=int),
             "visiteur_cle": opts[0]["cle"] if g.user["role"] == "cp" and opts else ""}
        return rendu_form(v)

    @app.route("/juridiction/visites/<int:vid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_visites")
    def jur_visite_supprimer(vid):
        juridiction_ou_404()
        v = q("SELECT * FROM jur_visites WHERE id=?", (vid,), un=True)
        if not v:
            abort(404)
        if not peut_modifier(v):
            abort(403)
        ex("DELETE FROM jur_visites WHERE id=?", (vid,))
        synchroniser(v["annee"])
        H.journal("jur_visite_suppression", f"{vid} {v['date']} {v['visiteur_nom']}")
        flash("Visite supprimée.", "warning")
        return redirect(url_for("jur_visites", annee=v["annee"]))

    # -------------------------------------------------------------- fiche PDF
    def fiche_pdf(r):
        P = H.pdfs
        vierge = r is None
        r = dict(r or {})
        s = H.jur_structure() or {}
        e = H.jur_ecole(r["ecole_id"]) if r.get("ecole_id") else None
        blanc = "\n\n"

        def val(k, defaut="—"):
            x = r.get(k)
            return blanc if vierge else (("" if x is None else str(x)) or defaut)

        eff = ("G : ……   F : ……   Total : ……" if vierge else
               f"G : {r['eff_g'] if r.get('eff_g') is not None else '—'}   "
               f"F : {r['eff_f'] if r.get('eff_f') is not None else '—'}   "
               f"Total : {r['eff_t'] if r.get('eff_t') is not None else '—'}"
               + (f"   (inscrits : {r['ins_g']} G / {r['ins_f']} F)" if r.get("ins_g") is not None else ""))
        heures = "de ……h…… à ……h……" if vierge else f"de {r.get('heure_debut') or '—'} à {r.get('heure_fin') or '—'}"
        lignes = [
            ["Enseignant(e) visité(e)", "……………………………………   NIP : ……………………" if vierge else
             (r.get("enseignant_nom") or "—") + (f"   (NIP : {r['enseignant_nip']})" if r.get("enseignant_nip") else "")],
            ["Classe", val("classe_nom")],
            ["Discipline / matière", val("discipline")],
            ["Unité / dossier", blanc if vierge else " — ".join(x for x in (r.get("unite"), r.get("dossier")) if x) or "—"],
            ["Situation d'apprentissage (SA)", val("sa")],
            ["Séquence", val("sequence")],
            ["Horaire de la séance", heures],
            ["Effectif présent", eff],
            ["Observations", "\n" * 4 if vierge else val("observations")],
            ["Points forts", "\n" * 3 if vierge else val("points_forts")],
            ["Insuffisances", "\n" * 3 if vierge else val("insuffisances")],
            ["Recommandations", "\n" * 3 if vierge else val("recommandations")],
            ["Conseils", "\n" * 3 if vierge else val("conseils")],
            ["Note / appréciation", "……… / 20      Appréciation : ……………………" if vierge else
             " — ".join(x for x in (note_txt(r.get("note")), r.get("appreciation") or "") if x) or "—"],
            ["Suites à donner", "\n" * 2 if vierge else val("suites")],
        ]
        if not vierge and r.get("type") == "ecole":
            retirer = {"Situation d'apprentissage (SA)", "Séquence", "Note / appréciation"}
            if not r.get("enseignant_nom"):
                retirer |= {"Enseignant(e) visité(e)", "Classe", "Effectif présent", "Discipline / matière",
                            "Unité / dossier", "Horaire de la séance"}
            lignes = [l for l in lignes if l[0] not in retirer]
        qual = r.get("visiteur_qualite")
        titre_vis = ("LE VISITEUR (CP / CCS)" if vierge else
                     "LE CONSEILLER PÉDAGOGIQUE" if qual == "CP" else "LE CHEF DE CIRCONSCRIPTION SCOLAIRE")
        cle_sig = None if vierge else cle_signature(r)
        img_vis = P.image_data_url(H.signature(cle_sig)) if cle_sig else None
        dir_titre = (e["directeur_titre"] if e and e["directeur_titre"] else "Directeur")
        dir_titre = f"{'LA' if dir_titre.lower().startswith('directrice') else 'LE'} {dir_titre.upper()}"
        sigs = [(titre_vis, "" if vierge else r.get("visiteur_nom") or "", img_vis, cle_sig == "jur:structure:responsable"),
                ("L'ENSEIGNANT(E) VISITÉ(E)", "" if vierge else r.get("enseignant_nom") or "", None, False),
                (dir_titre, "" if vierge else (e["directeur_nom"] if e else "") or "", None, False)]
        if not vierge and r.get("type") == "ecole" and not r.get("enseignant_nom"):
            sigs.pop(1)   # visite d'école sans enseignant désigné
        if config.EDITION == "cs" and (vierge or cle_sig != "jur:structure:responsable"):
            t, n, img = signataire()
            sigs.append((f"VISA : {t}" if len(t) < 32 else "VISA DU CHEF DE LA CS", n, None if vierge else img, not vierge))
        typ = "VISITE DE CLASSE / D'ÉCOLE / D'INSPECTION" if vierge else TYPES.get(r.get("type"), "").upper()
        infos = [("Type de visite", "[  ] Classe   [  ] École   [  ] Inspection" if vierge else TYPES.get(r["type"])),
                 ("Date", "……/……/…………" if vierge else P.date_fr(r.get("date"))),
                 ("Visiteur", "[  ] CP   [  ] CCS   Nom : ……………………" if vierge else
                  f"{qual} — {r.get('visiteur_nom') or ''}"),
                 ("Fonction", "……………………" if vierge else r.get("visiteur_fonction") or FONCTIONS.get(qual, "")),
                 ("École", "……………………………" if vierge else r.get("ecole_nom") or "—"),
                 ("Zone pédagogique", "……………………" if vierge else (e["zone_nom"] if e else "") or "—"),
                 ("Circonscription", (s.get("cs") or "……………………") if config.EDITION == "cs" or vierge
                  else (e["cs_nom"] if e else "—")),
                 ("Année scolaire", H.jur_annee() if vierge else r.get("annee"))]
        with cachet_structure():
            return P.document_tableau(
                f"FICHE DE {typ}", ["Rubrique", "Renseignements"], lignes,
                sous_titre="Animation pédagogique — visite du conseiller pédagogique (CP) ou du chef de "
                           "circonscription scolaire (CCS)",
                infos=infos, infos_haut=infos_haut(None if vierge else r.get("ecole_nom"),
                                                   e["cs_nom"] if e else None),
                largeurs=[28, 72], taille=9, signatures=sigs)

    @app.route("/juridiction/visites/<int:vid>/fiche.pdf")
    @H.connexion_requise()
    def jur_visite_pdf(vid):
        juridiction_ou_404()
        r = q("SELECT * FROM jur_visites WHERE id=?", (vid,), un=True)
        if not r:
            abort(404)
        H.journal("jur_visite_pdf", str(vid))
        return H.pdf_reponse(fiche_pdf(r), f"fiche_visite_{r['date']}_{vid}.pdf")

    @app.route("/juridiction/visites/fiche-vierge.pdf")
    @H.connexion_requise()
    def jur_visite_vierge():
        juridiction_ou_404()
        return H.pdf_reponse(fiche_pdf(None), "fiche_visite_vierge.pdf")

    # -------------------------------------------------------------- bilan des activités
    @app.route("/juridiction/bilan-activites")
    @H.connexion_requise()
    def jur_bilan_activites():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        cs_id = request.args.get("cs", type=int) if config.EDITION == "ddemp" else None
        b = bilan(annee, cs_id)
        fmt = request.args.get("export")
        if fmt == "xlsx":
            return bilan_xlsx(b, cs_id)
        if fmt == "pdf":
            return bilan_pdf(b, cs_id)
        cats = [lib for _, lib in MOIS]
        g_mois = svg_barres_empilees(cats, [(TYPES[t], COUL[t], b["mois"][t]) for t in TYPES], titre="Visites par mois")
        g_disc = svg_barres_h([(d["discipline"], d["n"], f"{d['discipline']} : {d['n']} visite(s)"
                                + (f", note moyenne {note_txt(d['note'])}" if d["note"] is not None else ""))
                               for d in b["disciplines"][:12]], COUL["classe"], titre="Visites par discipline")
        g_couv = svg_barres_h([(v["visiteur"], v["taux_ecoles"], f"{v['visiteur']} : {v['ecoles']} école(s) visitée(s) "
                                f"sur {v['ecoles_perimetre']} ({pct(v['taux_ecoles'])})") for v in b["visiteurs"]],
                              COUL["classe"], maxi=100, suffixe=" %", titre="Taux de couverture des écoles")
        g_cs = None
        if b["cs"]:
            g_cs = svg_barres_empilees([c["cs_nom"][:12] for c in b["cs"]],
                                       [("Saisies par la CS / DDEMP", COUL["classe"], [c["saisies"] for c in b["cs"]]),
                                        ("Déclarées par les écoles", COUL["ecole"], [c["declarees"] for c in b["cs"]])],
                                       titre="Visites par circonscription")
        return render_template("jur_bilan_activites.html", b=b, annee=annee, annees=annees_dispo(), cs=H.jur_cs_liste(),
                               cs_id=cs_id, MOIS=MOIS, TYPES=TYPES, COUL=COUL, g_mois=g_mois, g_disc=g_disc,
                               g_couv=g_couv, g_cs=g_cs, note_txt=note_txt, pct=pct, num=num)

    def titre_perimetre(cs_id):
        s = H.jur_structure() or {}
        if config.EDITION == "cs":
            return f"Circonscription scolaire de {s.get('cs') or ''}"
        if cs_id:
            c = H.jur_cs(cs_id)
            return f"DDEMP {s.get('departement') or ''} — CS de {c['nom'] if c else ''}"
        return f"DDEMP {s.get('departement') or ''} — toutes les circonscriptions"

    def bilan_xlsx(b, cs_id):
        ent_v = ["N°", "Visiteur", "Fonction", "Circonscription", "Visites de classe (dont inspection)",
                 "dont inspections", "Visites d'école", "Total", "Écoles visitées", "Écoles du périmètre", "Périmètre",
                 "Taux couverture écoles (%)", "Enseignants visités", "Enseignants du périmètre",
                 "Taux couverture enseignants (%)", "Note moyenne /20", "dont déclarées par les écoles"] + \
                [lib for _, lib in MOIS]
        l_v = [[i, v["visiteur"], v["fonction"], v["cs_nom"], v["visites_classe"], v["visites_inspection"],
                v["visites_ecole"], v["total"], v["ecoles"], v["ecoles_perimetre"], v["perimetre"], v["taux_ecoles"],
                v["enseignants"], v["enseignants_perimetre"], v["taux_enseignants"], v["note_moyenne"], v["declarees"]]
               + v["mois"] for i, v in enumerate(b["visiteurs"], 1)]
        t = b["tot"]
        l_v.append(["", "TOTAL", "", "", t["classe"] + t["inspection"], t["inspection"], t["ecole"], t["total"],
                    t["ecoles_visitees"], t["ecoles_total"], "", t["taux_ecoles"], t["enseignants_visites"],
                    t["enseignants_total"], t["taux_enseignants"], t["note"], t["declarees"]]
                   + [sum(b["mois"][x][i] for x in TYPES) for i in range(len(MOIS))])
        haut = {"titre_haut": [f"Bilan des activités des CP et CCS — {b['annee']}", titre_perimetre(cs_id)]}
        feuilles = [("Par visiteur", ent_v, l_v, haut)]
        if b["cs"]:
            feuilles.append(("Par CS", ["Circonscription", "Visites saisies (CS/DDEMP)", "dont reçues des CS",
                                        "Déclarées par les écoles", "Total", "Visites de classe", "Visites d'école",
                                        "Visiteurs", "Écoles", "Écoles visitées", "Taux écoles (%)", "Enseignants",
                                        "Enseignants visités", "Taux enseignants (%)", "Note moyenne"],
                             [[c["cs_nom"], c["saisies"], c["transmises_cs"], c["declarees"], c["total"],
                               c["visites_classe"], c["visites_ecole"], c["visiteurs"], c["ecoles"], c["ecoles_visitees"],
                               c["taux_ecoles"], c["enseignants"], c["enseignants_visites"], c["taux_enseignants"],
                               c["note"]] for c in b["cs"]], haut))
        feuilles.append(("Par zone", ["Circonscription", "Zone pédagogique", "CP de la zone", "Écoles", "Écoles visitées",
                                      "Taux écoles (%)", "Enseignants", "Enseignants visités", "Taux enseignants (%)",
                                      "Visites de classe", "Visites d'école", "Note moyenne"],
                         [[z["cs_nom"], z["zone"], z["cp"], z["ecoles"], z["ecoles_visitees"], z["taux_ecoles"],
                           z["enseignants"], z["enseignants_visites"], z["taux_enseignants"], z["visites_classe"],
                           z["visites_ecole"], z["note"]] for z in b["zones"]], haut))
        feuilles.append(("Par mois", ["Mois"] + list(TYPES.values()) + ["Total"],
                         [[lib] + [b["mois"][x][i] for x in TYPES] + [sum(b["mois"][x][i] for x in TYPES)]
                          for i, (_, lib) in enumerate(MOIS)], haut))
        feuilles.append(("Par discipline", ["Discipline", "Visites de classe / inspection", "Note moyenne /20"],
                         [[d["discipline"], d["n"], d["note"]] for d in b["disciplines"]], haut))
        H.journal("jur_bilan_xlsx", b["annee"])
        return H.xlsx.reponse_classeur(f"bilan_activites_cp_ccs_{b['annee']}.xlsx", feuilles)

    def bilan_pdf(b, cs_id):
        P = H.pdfs
        t = b["tot"]
        cols = [["N°", "Visiteur", "Fonction", "Visites", None, None, "Écoles", None, None, "Enseignants", None, None,
                 "Note moy."],
                ["^", "^", "^", "Classe*", "École", "Total", "Visitées", "Périmètre", "Taux", "Visités", "Périmètre",
                 "Taux", "^"]]
        lignes = [[i, v["visiteur"] + (f"\n{v['cs_nom']}" if config.EDITION == "ddemp" else ""),
                   f"{v['qualite']}\n{v['perimetre']}", v["visites_classe"], v["visites_ecole"], v["total"],
                   f"{v['ecoles_perimetre_visitees']}" + (f"\n({v['ecoles']} au total)" if v["ecoles"] != v["ecoles_perimetre_visitees"] else ""),
                   v["ecoles_perimetre"], pct(v["taux_ecoles"]),
                   f"{v['enseignants_perimetre_visites']}" + (f"\n({v['enseignants']} au total)" if v["enseignants"] != v["enseignants_perimetre_visites"] else ""),
                   v["enseignants_perimetre"],
                   pct(v["taux_enseignants"]), note_txt(v["note_moyenne"]) or "—"] for i, v in enumerate(b["visiteurs"], 1)]
        if not lignes:
            lignes = [["", "Aucune visite de CP ou de CCS pour cette année.", "", "", "", "", "", "", "", "", "", "", ""]]
        total = ["", "TOTAL", "", t["classe"] + t["inspection"], t["ecole"], t["total"], t["ecoles_visitees"],
                 t["ecoles_total"], pct(t["taux_ecoles"]), t["enseignants_visites"], t["enseignants_total"],
                 pct(t["taux_enseignants"]), note_txt(t["note"]) or "—"]
        apres = []
        if b["cs"]:
            apres.append(P.paragraphe("Bilan par circonscription scolaire", 9.5, True, espace=6))
            apres.append(P.mini_tableau(
                [["CS", "Saisies CS/DDEMP", "Déclarées écoles", "Total", "Classe", "École", "Visiteurs", "Écoles visitées",
                  "Taux écoles", "Ens. visités", "Taux ens.", "Note moy."]] +
                [[c["cs_nom"], c["saisies"], c["declarees"], c["total"], c["visites_classe"], c["visites_ecole"],
                  c["visiteurs"], f"{c['ecoles_visitees']} / {c['ecoles']}", pct(c["taux_ecoles"]),
                  f"{c['enseignants_visites']} / {c['enseignants']}", pct(c["taux_enseignants"]),
                  note_txt(c["note"]) or "—"] for c in b["cs"]], taille=7.5))
        if b["zones"] and (config.EDITION == "cs" or cs_id):
            apres.append(P.paragraphe("Bilan par zone pédagogique", 9.5, True, espace=6))
            apres.append(P.mini_tableau(
                [["Zone pédagogique", "CP de la zone", "Écoles visitées", "Taux écoles", "Enseignants visités",
                  "Taux ens.", "Visites de classe", "Visites d'école", "Note moy."]] +
                [[z["zone"], z["cp"] or "—", f"{z['ecoles_visitees']} / {z['ecoles']}", pct(z["taux_ecoles"]),
                  f"{z['enseignants_visites']} / {z['enseignants']}", pct(z["taux_enseignants"]), z["visites_classe"],
                  z["visites_ecole"], note_txt(z["note"]) or "—"] for z in b["zones"]], taille=7.5))
        apres.append(P.paragraphe("Répartition des visites par mois", 9.5, True, espace=6))
        apres.append(P.mini_tableau([["Type"] + [lib for _, lib in MOIS] + ["Total"]] +
                                    [[TYPES[x]] + b["mois"][x] + [sum(b["mois"][x])] for x in TYPES], taille=7.5))
        if b["disciplines"]:
            apres.append(P.paragraphe("Visites de classe par discipline", 9.5, True, espace=6))
            apres.append(P.mini_tableau([["Discipline", "Visites", "Note moyenne"]] +
                                        [[d["discipline"], d["n"], note_txt(d["note"]) or "—"] for d in b["disciplines"]],
                                        taille=7.5))
        titre, nom, img = signataire()
        with cachet_structure():
            pdf = P.document_tableau(
                "BILAN DES ACTIVITÉS DES CONSEILLERS PÉDAGOGIQUES ET DES CHEFS DE CIRCONSCRIPTION", cols, lignes,
                total=total, paysage=True, taille=7.5, largeurs=[5, 34, 30, 9, 9, 9, 10, 11, 10, 10, 11, 10, 11],
                sous_titre=f"Animation pédagogique — {titre_perimetre(cs_id)} — année scolaire {b['annee']}",
                infos=[("Visites (CP / CCS)", f"{t['total']} ({t['cp']} / {t['ccs']})"),
                       ("Classe / école / inspection", f"{t['classe']} / {t['ecole']} / {t['inspection']}"),
                       ("Déclarées par les écoles", t["declarees"]),
                       ("Écoles visitées", f"{t['ecoles_visitees']} / {t['ecoles_total']} ({pct(t['taux_ecoles'])})"),
                       ("Enseignants visités", f"{t['enseignants_visites']} / {t['enseignants_total']} "
                                               f"({pct(t['taux_enseignants'])})"),
                       ("Note moyenne", note_txt(t["note"]) or "—")],
                infos_haut=infos_haut(None, H.jur_cs(cs_id)["nom"] if cs_id and H.jur_cs(cs_id) else None),
                apres=apres, signatures=[(titre, nom, img, True)],
                notes_bas=["* Visites de classe, y compris les visites d'inspection. Périmètre d'un CP : sa zone "
                           "pédagogique (Zones pédagogiques › CP de la zone), sinon la circonscription ; d'un CCS : sa "
                           "circonscription. Visites saisies par la structure et déclarées par les écoles réunies, "
                           "sans double compte (même date, même enseignant, même visiteur)."])
        H.journal("jur_bilan_pdf", b["annee"])
        return H.pdf_reponse(pdf, f"bilan_activites_cp_ccs_{b['annee']}.pdf")
