# -*- coding: utf-8 -*-
"""v1.25 — Moteur commun des registres (sport scolaire, pilotage, communication, santé, inspection, patrimoine, examens).

Un registre se déclare en quelques lignes (rubriques, libellés, listes) ; le moteur fournit, pour chacun :
* la page (onglets du module, filtres année / recherche, tableau à en-têtes fixes, formulaire  Ajouter /  Modifier) ;
*  Supprimer,  Réinitialiser (l'année affichée),  Excel (export), modèle Excel et  import (mêmes colonnes) ;
*  PDF signé du registre (signature et cachet de l'autorité, code de vérification et QR, page /verifier) et, si demandé,
  une fiche individuelle signée par ligne.

Portée des lignes : « ecole » (école courante : H.eco(), y compris une école ouverte depuis la CS / DDEMP) ou
« structure » (la CS / la DDEMP, ou l'école elle-même dans les éditions école).

Types de rubriques : texte, long, date, heure, entier, decimal, montant, oui_non, choix:<liste>, liste:<liste>
(saisie libre proposée), eleve (élève de l'école), classe, ecole (écoles de la juridiction ou de la liste).
Les listes peuvent être dynamiques (fonction appelée à chaque affichage).
"""
import io
import re
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

TYPES_NUM = ("entier", "decimal", "montant")
NIVEAUX = ["ECOLE", "UP", "ZONE", "CS", "DDEMP"]
NIVEAUX_LIB = {"ECOLE": "École", "UP": "Unité pédagogique", "ZONE": "Zone pédagogique", "CS": "Circonscription scolaire",
               "DDEMP": "Direction départementale"}
GROUPES = {}          # cle -> Groupe
_H = None


def jjmmaaaa(iso):
    if not iso:
        return ""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2}).*", str(iso))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(iso)


def iso(v):
    import outils_xlsx as X
    if v in (None, ""):
        return ""
    return X.date_iso(v) or str(v)


def nombre(v, typ="entier"):
    if v in (None, ""):
        return None
    s = re.sub(r"[\s  ]", "", str(v)).replace(",", ".")
    if typ != "decimal":
        s = s.split(".")[0] if re.fullmatch(r"-?\d+(\.0+)?", s) else s.replace(".", "")
    try:
        return float(s) if typ == "decimal" else int(s)
    except ValueError:
        return None


def fcfa(n):
    return f"{int(n or 0):,}".replace(",", " ") + " F"


def annee_active():
    return _H.config.ANNEE_ACTIVE


def annees_proposees(extra=()):
    a = int(annee_active()[:4])
    return sorted({f"{x}-{x + 1}" for x in range(a - 3, a + 2)} | set(e for e in extra if e), reverse=True)


def juridiction():
    return _H.config.EDITION in ("cs", "ddemp")


def niveau_code(v):
    """Niveau saisi (code ou libellé) -> code commun."""
    n = _norm(v).strip()
    for k, l in NIVEAUX_LIB.items():
        if n in (k.lower(), _norm(l)) or (n and _norm(l).startswith(n)):
            return k
    return "ECOLE" if n.startswith("ecole") else (str(v or "").strip().upper() or "")


def entite_courante():
    """(niveau, libellé) de l'entité du compte : l'école (ou l'école ouverte depuis la structure), sinon la CS / la DDEMP."""
    E = _H.config.ECOLE or {}
    if not juridiction():
        return "ECOLE", E.get("nom") or ""
    if g.get("ecole"):
        try:
            x = _H.q("SELECT nom FROM ecoles WHERE id=?", (_H.eco(),), un=True)
            return "ECOLE", (x["nom"] if x else "") or ""
        except Exception:  # noqa: BLE001
            return "ECOLE", ""
    return ("DDEMP" if _H.config.EDITION == "ddemp" else "CS"), E.get("nom") or ""


def portee_ecole():
    return _H.eco()


def cle_portee(portee):
    """Clé de rangement : id de l'école (portée école) ; 0 pour la structure (CS / DDEMP) ou -id d'école (édition école)."""
    if portee == "ecole":
        return _H.eco()
    return 0 if juridiction() else -_H.eco()


# ------------------------------------------------------------------ signatures (autorité du compte)
def signature_autorite(titre=None):
    """{titre, nom, image, cachet} : directeur de l'école (éditions école, école ouverte) ou responsable de la CS / DDEMP."""
    pdfs = _H.pdfs
    cfg = _H.config
    if juridiction() and not g.get("ecole"):
        t, nom, sig = ("Le Chef de la circonscription scolaire" if cfg.EDITION == "cs" else "Le Directeur départemental"), "", None
        try:
            if getattr(_H, "jur_signataire", None):
                t2, nom, sig = _H.jur_signataire()
                t = t2 or t
        except Exception:  # noqa: BLE001
            pass
        ca = None
        try:
            c = _H.jur_cachet() if getattr(_H, "jur_cachet", None) else None
            ca = ("rond",) + tuple(c) if c else None
        except Exception:  # noqa: BLE001
            ca = None
        return {"titre": titre or t, "nom": nom or "", "image": pdfs.image_data_url(sig) if sig else None, "cachet": ca}
    return {"titre": titre or "Le Directeur / La Directrice", "nom": cfg.ECOLE.get("directeur") or "",
            "image": pdfs.signature_directeur(), "cachet": ("ecole",)}


def signature_vide(titre, nom=""):
    return {"titre": titre, "nom": nom, "image": None, "cachet": None}


def code_document(type_doc, libelle, cle):
    try:
        return _H.enregistrer_document(type_doc, None, libelle[:250], cle=cle)
    except Exception:  # noqa: BLE001
        return None


def pdf_document(titre, histoire_corps, sigs, code, paysage=False, sous_titre=None, nom_auteur="SCOLARIS", bandeau=None):
    """PDF avec en-tête officiel, corps (flowables), bloc de signatures (cachets) et QR de vérification."""
    import pdfs
    from m_uascep import bloc_signatures
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer
    W, Hh = landscape(A4) if paysage else A4
    marge = 12 * mm
    st = styles()
    h = []
    if bandeau and getattr(_H, "uascep", None):    # (niveau, entité, libellé) : bandeau « logo UASCEP »
        try:
            h.append(_H.uascep.bandeau_logo(bandeau[0], bandeau[1], bandeau[2] if len(bandeau) > 2 else None, W - 2 * marge))
        except Exception:  # noqa: BLE001
            pass
    h.append(Paragraph(esc(titre), st["t"]))
    if sous_titre:
        h.append(Paragraph(esc(sous_titre), st["s"]))
    h.append(Spacer(1, 5))
    h += list(histoire_corps)
    if sigs or code:
        h += [Spacer(1, 8), KeepTogether([bloc_signatures(sigs or [], W - 2 * marge, code)])]

    def deco(c, doc):
        pdfs._entete_primaire(c, W, Hh, marge, None, None)
        from reportlab.lib import colors
        c.setFont("Helvetica", 6.5)
        c.setFillColor(colors.grey)
        c.drawString(marge, 7 * mm, f"{_H.config.NOMS_APPLI.get(_H.config.EDITION, 'SCOLARIS') if hasattr(_H.config, 'NOMS_APPLI') else 'SCOLARIS'} · "
                                    f"{_H.config.ECOLE.get('nom', '')} · {annee_active()}")
        c.drawRightString(W - marge, 7 * mm, f"Page {doc.page} · imprimé le {date.today().strftime('%d/%m/%Y')}")
        if code:
            c.drawCentredString(W / 2, 7 * mm, f"Document vérifiable · code {code}")
        c.setFillColor(colors.black)
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=(W, Hh), leftMargin=marge, rightMargin=marge, topMargin=marge + 30 * mm, bottomMargin=13 * mm,
                      title=titre, author=nom_auteur).build(h, onFirstPage=deco, onLaterPages=deco, canvasmaker=pdfs.GCanvas)
    return buf.getvalue()


def esc(t):
    return str("" if t is None else t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def styles():
    import pdfs
    from reportlab.lib.styles import ParagraphStyle
    st = ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13.5, spaceAfter=4)
    return {"p": st, "petit": ParagraphStyle("pp", parent=st, fontSize=7.6, leading=9.4, spaceAfter=0),
            "gras": ParagraphStyle("pg", parent=st, fontName="Helvetica-Bold"),
            "h2": ParagraphStyle("h2", parent=st, fontName="Helvetica-Bold", fontSize=10.5, textColor=pdfs.BLEU, spaceBefore=6),
            "t": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=13, alignment=1, textColor=pdfs.BLEU, leading=16, spaceAfter=4),
            "s": ParagraphStyle("s", parent=st, alignment=1, fontSize=9)}


def tableau(entetes, lignes, largeurs=None, largeur_totale=None, total=None, taille=7.6):
    """Table ReportLab (en-tête répété, grille) ; largeurs relatives."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle
    st = ParagraphStyle("c", fontName="Helvetica", fontSize=taille, leading=taille + 1.8)
    sth = ParagraphStyle("h", parent=st, fontName="Helvetica-Bold")
    data = [[Paragraph(esc(x), sth) for x in entetes]] + [[Paragraph(esc(x), st) for x in r] for r in lignes]
    if total:
        data.append([Paragraph(esc(x), sth) for x in total])
    if len(data) == 1:
        data.append([Paragraph("—", st)] + [Paragraph("", st) for _ in entetes[1:]])
    lt = largeur_totale or (A4[0] - 24 * mm)
    lg = largeurs or [1] * len(entetes)
    s = sum(lg)
    tb = Table(data, colWidths=[lt * x / s for x in lg], repeatRows=1)
    sty = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E4ECF5")),
           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]
    if total:
        sty.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F4F7")))
    tb.setStyle(TableStyle(sty))
    return tb


def largeur_utile(paysage=False):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    return (landscape(A4)[0] if paysage else A4[0]) - 24 * mm


def types_documents(types):
    """Libellés des types de documents pour la page /verifier."""
    import sys
    for nom_mod in ("app", "__main__"):
        td = getattr(sys.modules.get(nom_mod), "TYPES_DOCS", None)
        if isinstance(td, dict):
            for k, v in types.items():
                td.setdefault(k, v)


# ------------------------------------------------------------------ listes dynamiques communes
def liste_classes():
    try:
        return [r["nom"] for r in _H.q("SELECT nom FROM classes WHERE ecole_id=? ORDER BY niveau, nom", (_H.eco(),))]
    except Exception:  # noqa: BLE001
        return []


def liste_ecoles():
    try:
        if juridiction():
            return [r["nom"] for r in _H.q("SELECT nom FROM jur_ecoles WHERE COALESCE(actif,1)=1 ORDER BY nom")]
        return [_H.config.ECOLE.get("nom") or "École"]
    except Exception:  # noqa: BLE001
        return []


def liste_zones():
    try:
        if juridiction():
            return [r["nom"] for r in _H.q("SELECT nom FROM jur_zones ORDER BY ordre, nom")]
    except Exception:  # noqa: BLE001
        pass
    return []


def liste_up():
    try:
        if juridiction():
            return [r["nom"] for r in _H.q("SELECT nom FROM jur_up WHERE COALESCE(actif,1)=1 ORDER BY nom")]
    except Exception:  # noqa: BLE001
        pass
    return []


def eleves_ecole():
    """[(id, libellé « NOM Prénoms (classe) »)] des élèves inscrits de l'école courante."""
    try:
        rows = _H.q("SELECT e.id, e.nom, e.prenoms, c.nom classe FROM eleves e JOIN classes c ON c.id=e.classe_id AND c.ecole_id=? "
                    "WHERE e.statut='inscrit' ORDER BY c.niveau, c.nom, e.nom, e.prenoms", (_H.eco(),))
    except Exception:  # noqa: BLE001
        return []
    return [(r["id"], f"{r['nom']} {r['prenoms'] or ''}".strip() + (f" ({r['classe']})" if r["classe"] else "")) for r in rows]


LISTES_COMMUNES = {"niveaux": NIVEAUX, "classes": liste_classes, "ecoles": liste_ecoles, "zones": liste_zones, "up": liste_up,
                   "oui_non": ["Oui", "Non"], "sexe": ["M", "F"],
                   "niveaux_cours": ["CI", "CP", "CE1", "CE2", "CM1", "CM2", "Maternelle 1", "Maternelle 2"]}


# ------------------------------------------------------------------ définitions
class Registre:
    def __init__(self, groupe, cle, titre, champs, unite="ligne", oblig=None, ordre="id DESC", portee="ecole", feuille=None,
                 doc=None, signataires=None, paysage=True, colonnes=None, par_annee=True, aide="", fiche=None, apres_enregistrer=None,
                 ecriture=None, calcul=None, filtres=(), onglet=None, totaux=(), prefixe=None, defauts=None, fiches=None, actions=None,
                 unique=(), entite=False, niveaux=None, annee_lib=None):
        self.groupe, self.cle, self.titre, self.unite = groupe, cle, titre, unite
        champs = list(champs)
        self.entite = entite                    # v1.26 : rubriques « niveau » et « entite » (colonnes Niveau · Entité de l'Excel commun)
        if entite:
            champs = [("niveau", "Niveau", "choix:niveaux"), ("entite", "Entité", "texte")] + champs
        self.champs = [tuple(c) + (None,) * (3 - len(c)) if len(c) < 3 else tuple(c) for c in champs]
        self.fiches = dict(fiches or {})        # v1.26 : {code: (libellé du bouton, icône, fonction(ligne) -> (titre, flowables, sigs[, paysage]))}
        self.actions = actions                  # v1.26 : fonction(ligne) -> [(url, libellé, icône)] : boutons de ligne
        self.unique = tuple(unique)             # v1.26 : clé d'unicité (import : mise à jour au lieu d'ajout)
        self.niveaux = list(niveaux or NIVEAUX)
        self.annee_lib = annee_lib or ("Année scolaire" if cle in ("indicateurs", "filles") else "Saison")
        self.oblig = oblig or self.champs[0][0]
        self.ordre, self.portee, self.paysage = ordre, portee, paysage
        self.feuille = (feuille or titre)[:31]
        self.doc = doc or titre
        self.signataires = signataires          # fonction(lignes) -> [sig] ; défaut : autorité
        self.colonnes = colonnes                # clés affichées dans le tableau (défaut : toutes sauf « long » au-delà de 2)
        self.par_annee = par_annee
        self.aide = aide
        self.fiche = fiche                      # fonction(ligne) -> (titre, flowables, sigs) : fiche individuelle signée
        self.apres_enregistrer = apres_enregistrer
        self.ecriture = ecriture                # fonction() -> bool ; défaut : rôles d'écriture du groupe
        self.calcul = calcul                    # fonction(dict ligne) -> dict colonnes calculées {libellé: valeur}
        self.filtres = list(filtres)            # clés de rubriques proposées en filtre (choix)
        self.onglet = onglet or titre
        self.totaux = set(totaux)
        self.defauts = defauts                  # fonction() -> {rubrique: valeur} proposées dans le formulaire d'ajout
        self.prefixe = prefixe                  # fonction(ligne) -> (niveau, entité) : colonnes « Niveau · Entité · Saison » de l'Excel commun
        self.table = f"reg_{groupe.cle}_{cle}"
        if entite and prefixe is None:
            self.prefixe = lambda x: (x.get("niveau") or entite_courante()[0], x.get("entite") or entite_courante()[1])
        if entite and defauts is None:
            self.defauts = lambda: {"niveau": entite_courante()[0], "entite": entite_courante()[1]}

    def champs_excel(self):
        return [c for c in self.champs if not (self.entite and c[0] in ("niveau", "entite"))]

    @property
    def lib(self):
        return {k: l for k, l, _t in self.champs}

    @property
    def typ(self):
        return {k: t or "texte" for k, _l, t in self.champs}

    def cols_table(self):
        if self.colonnes:
            return [c for c in self.champs if c[0] in self.colonnes]
        out, longs = [], 0
        for c in self.champs:
            if (c[2] or "texte") == "long":
                longs += 1
                if longs > 2:
                    continue
            out.append(c)
        return out[:14]


class Groupe:
    """Un module (onglets) : ses registres et ses pages propres."""

    def __init__(self, app, H, cle, titre, droit, ecriture_roles=None, sous_titre="", listes=None, onglets_avant=(), ico=""):
        global _H
        _H = H
        self.app, self.H, self.cle, self.titre, self.droit, self.sous_titre, self.ico = app, H, cle, titre, droit, sous_titre, ico
        self.ecriture_roles = set(ecriture_roles or {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp"})
        self.registres = {}
        self.bandeau = None                     # fonction() -> (niveau, entité, libellé) : bandeau « logo UASCEP » des PDF
        self.alertes = None                     # v1.26 : fonction() -> (nombre, url) : bandeau d'alertes en tête des onglets
        self.pages = list(onglets_avant)        # [(endpoint, titre, kwargs)] : pages propres (avant les registres)
        self.pages_apres = []
        self.listes = dict(LISTES_COMMUNES)
        self.listes.update(listes or {})
        GROUPES[cle] = self
        _installer_routes(app, H)

    def peut_ecrire(self, reg=None):
        if not g.get("user"):
            return False
        if reg is not None and reg.ecriture is not None:
            return bool(reg.ecriture())
        role = g.user["role"]
        if _H.config.EDITION == "enseignant" and role == "enseignant":
            return False
        return role in self.ecriture_roles or (role == "fondateur" and "admin" in self.ecriture_roles)

    def registre(self, cle, titre, champs, **kw):
        r = Registre(self, cle, titre, champs, **kw)
        self.registres[cle] = r
        cols = ", ".join(f"{k} {'REAL' if t == 'decimal' else 'INTEGER' if t in TYPES_NUM or t == 'eleve' else 'TEXT'}"
                         for k, _l, t in r.champs)
        self.H.schema(f"CREATE TABLE IF NOT EXISTS {r.table} (id INTEGER PRIMARY KEY, portee INTEGER NOT NULL DEFAULT 0, annee TEXT, "
                      f"{cols}, cree_le TEXT, cree_par INTEGER, maj TEXT);\n"
                      f"CREATE INDEX IF NOT EXISTS ix_{r.table} ON {r.table}(portee, annee);")
        for k, _l, t in r.champs:
            self.H.ajouter_colonne(r.table, k, "REAL" if t == "decimal" else "INTEGER" if t in TYPES_NUM or t == "eleve" else "TEXT")
        return r

    def page(self, endpoint, titre, apres=True, **kw):
        (self.pages_apres if apres else self.pages).append((endpoint, titre, kw))

    def bandeau_alertes(self):
        if not self.alertes:
            return None
        try:
            n, u = self.alertes()
            return (n, u) if n else None
        except Exception:  # noqa: BLE001
            return None

    def onglets(self):
        out = [(url_for(e, **kw), t, e) for e, t, kw in self.pages]
        out += [(url_for("reg_page", gcle=self.cle, rcle=r.cle), r.onglet, "reg:" + r.cle) for r in self.registres.values()]
        out += [(url_for(e, **kw), t, e) for e, t, kw in self.pages_apres]
        return out

    def liste(self, nom):
        v = self.listes.get(nom, [])
        try:
            return list(v() if callable(v) else v)
        except Exception:  # noqa: BLE001
            return []

    # ---- accès aux données
    def lignes(self, r, annee=None, recherche=None, filtres=None, toutes_annees=False):
        sql = f"SELECT * FROM {r.table} WHERE portee=?"
        args = [cle_portee(r.portee)]
        if r.par_annee and not toutes_annees:
            sql += " AND annee=?"
            args.append(annee or annee_active())
        for k, v in (filtres or {}).items():
            if v:
                sql += f" AND {k}=?"
                args.append(v)
        rows = [dict(x) for x in self.H.q(sql + f" ORDER BY {r.ordre}", tuple(args))]
        if recherche:
            n = _norm(recherche)
            rows = [x for x in rows if n in _norm(" ".join(str(v) for v in x.values() if v is not None) + " " + self.libelle_eleve(r, x))]
        return rows

    def ligne(self, r, rid):
        x = self.H.q(f"SELECT * FROM {r.table} WHERE id=? AND portee=?", (rid, cle_portee(r.portee)), un=True)
        if not x:
            abort(404)
        return dict(x)

    def libelle_eleve(self, r, x):
        out = []
        for k, _l, t in r.champs:
            if t == "eleve" and x.get(k):
                out.append(self.nom_eleve(x[k]))
        return " ".join(out)

    def nom_eleve(self, eid):
        try:
            e = self.H.q("SELECT e.nom, e.prenoms, c.nom classe FROM eleves e LEFT JOIN classes c ON c.id=e.classe_id WHERE e.id=?", (eid,), un=True)
        except Exception:  # noqa: BLE001
            e = None
        return (f"{e['nom']} {e['prenoms'] or ''}".strip() + (f" ({e['classe']})" if e["classe"] else "")) if e else ""

    def valeur_affichee(self, r, x, k):
        t = r.typ.get(k, "texte")
        v = x.get(k)
        if v is None or v == "":
            return ""
        if t == "date":
            return jjmmaaaa(v)
        if t == "montant":
            return fcfa(v)
        if t == "decimal":
            return (f"{v:.2f}".rstrip("0").rstrip(".")).replace(".", ",")
        if t == "eleve":
            return self.nom_eleve(v)
        return v

    def lire_formulaire(self, r, f):
        d = {}
        for k, _l, t in r.champs:
            t = t or "texte"
            v = f.get(k)
            if t.startswith("multi"):
                v = ", ".join(x for x in f.getlist(k) if x) if hasattr(f, "getlist") else (v or "")
            v = (v or "").strip() if isinstance(v, str) else v
            if t in TYPES_NUM:
                d[k] = nombre(v, "decimal" if t == "decimal" else "entier")
            elif t == "eleve":
                d[k] = nombre(v) if v not in (None, "") else None
            elif t == "date":
                d[k] = iso(v) if v else ""
            else:
                d[k] = (str(v) if v is not None else "")[:6000 if t == "long" else 400]
        return d


def _norm(t):
    import unicodedata
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


# ------------------------------------------------------------------ routes génériques
_ROUTES = [False]


def _installer_routes(app, H):
    if _ROUTES[0]:
        return
    _ROUTES[0] = True
    _route_fiches(app, H)

    def groupe_reg(gcle, rcle):
        G = GROUPES.get(gcle)
        if not G or rcle not in G.registres:
            abort(404)
        if not H.peut(G.droit):
            abort(403)
        r = G.registres[rcle]
        if r.portee == "ecole" and juridiction() and not g.get("ecole"):
            flash("Ouvrez d'abord une école : ce registre est tenu par école.", "warning")
            abort(redirect(url_for("jur_ecoles_modules") if "jur_ecoles_modules" in app.view_functions else url_for("accueil")))
        return G, r

    def annee_req():
        v = (request.values.get("annee") or "").strip()
        return v if re.fullmatch(r"\d{4}-\d{4}", v) else annee_active()

    def exiger(G, r):
        if not G.peut_ecrire(r):
            abort(403)

    @app.route("/reg/<gcle>/<rcle>")
    @H.connexion_requise()
    def reg_page(gcle, rcle):
        G, r = groupe_reg(gcle, rcle)
        annee = annee_req()
        rech = (request.args.get("q") or "").strip()
        filtres = {k: (request.args.get("f_" + k) or "").strip() for k in r.filtres}
        lignes = G.lignes(r, annee, rech, filtres)
        edit = None
        if request.args.get("modifier", type=int):
            edit = G.ligne(r, request.args.get("modifier", type=int))
        elif request.args.get("dupliquer", type=int):
            edit = dict(G.ligne(r, request.args.get("dupliquer", type=int)), id=None)
        elif r.defauts:
            try:
                edit = dict(r.defauts(), id=None)
            except Exception:  # noqa: BLE001
                edit = None
        listes = {}
        for k, _l, t in r.champs:
            if t and ":" in t:
                listes[t.split(":", 1)[1]] = G.liste(t.split(":", 1)[1])
            elif t == "classe":
                listes["classes"] = G.liste("classes")
            elif t == "ecole":
                listes["ecoles"] = G.liste("ecoles")
        calc = {x["id"]: r.calcul(x) for x in lignes} if r.calcul else {}
        totaux = {k: sum((x.get(k) or 0) for x in lignes) for k in r.totaux}
        annees = annees_proposees([annee] + [x["annee"] for x in H.q(f"SELECT DISTINCT annee FROM {r.table} WHERE portee=?", (cle_portee(r.portee),))])
        return render_template("registre.html", G=G, r=r, lignes=lignes, edit=edit, listes=listes, annee=annee, annees=annees, rech=rech,
                               filtres=filtres, peut_ecrire=G.peut_ecrire(r), eleves=eleves_ecole() if "eleve" in r.typ.values() else [],
                               aff=lambda x, k: G.valeur_affichee(r, x, k), calc=calc, totaux=totaux, fcfa=fcfa,
                               ep_actif="reg:" + r.cle, pdf_args={"f_" + k: v for k, v in filtres.items() if v})

    @app.route("/reg/<gcle>/<rcle>/<int:rid>", methods=["POST"])
    @H.connexion_requise()
    def reg_enregistrer(gcle, rcle, rid):
        G, r = groupe_reg(gcle, rcle)
        exiger(G, r)
        annee = annee_req()
        d = G.lire_formulaire(r, request.form)
        if d.get(r.oblig) in (None, ""):
            flash(f"« {r.lib.get(r.oblig, r.oblig)} » est obligatoire.", "danger")
            return redirect(url_for("reg_page", gcle=gcle, rcle=rcle, annee=annee, modifier=rid or None))
        ks = list(d)
        if rid:
            G.ligne(r, rid)
            H.ex(f"UPDATE {r.table} SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), rid))
        else:
            rid = H.ex(f"INSERT INTO {r.table} (portee, annee, " + ", ".join(ks) + ", cree_le, cree_par, maj) VALUES (?,?," + ",".join("?" * len(ks)) + ",?,?,?)",
                       (cle_portee(r.portee), annee) + tuple(d[k] for k in ks) + (H.maintenant(), g.user["id"], H.maintenant()))
        if r.apres_enregistrer:
            try:
                r.apres_enregistrer(rid)
            except Exception:  # noqa: BLE001
                pass
        H.journal(r.table, f"{r.unite} {rid}")
        flash(f"{r.unite[:1].upper() + r.unite[1:]} enregistré(e).", "success")
        return redirect(url_for("reg_page", gcle=gcle, rcle=rcle, annee=annee))

    @app.route("/reg/<gcle>/<rcle>/<int:rid>/supprimer", methods=["POST"])
    @H.connexion_requise()
    def reg_supprimer(gcle, rcle, rid):
        G, r = groupe_reg(gcle, rcle)
        exiger(G, r)
        G.ligne(r, rid)
        H.ex(f"DELETE FROM {r.table} WHERE id=?", (rid,))
        H.journal(r.table + "_supprime", str(rid))
        flash(f"{r.unite[:1].upper() + r.unite[1:]} supprimé(e).", "success")
        return redirect(url_for("reg_page", gcle=gcle, rcle=rcle, annee=annee_req()))

    @app.route("/reg/<gcle>/<rcle>/reinitialiser", methods=["POST"])
    @H.connexion_requise()
    def reg_reinitialiser(gcle, rcle):
        G, r = groupe_reg(gcle, rcle)
        exiger(G, r)
        annee = annee_req()
        if r.par_annee:
            H.ex(f"DELETE FROM {r.table} WHERE portee=? AND annee=?", (cle_portee(r.portee), annee))
        else:
            H.ex(f"DELETE FROM {r.table} WHERE portee=?", (cle_portee(r.portee),))
        H.journal(r.table + "_reinitialise", annee)
        flash(f"« {r.titre} » réinitialisé" + (f" pour {annee}." if r.par_annee else "."), "success")
        return redirect(url_for("reg_page", gcle=gcle, rcle=rcle, annee=annee))

    def lignes_excel(G, r, lignes):
        ent = (["Niveau", "Entité", r.annee_lib] if r.prefixe else []) + [l for _k, l, _t in r.champs_excel()]
        calc_ent = list(r.calcul(lignes[0]).keys()) if (r.calcul and lignes) else []
        rows = []
        for x in lignes:
            ligne = (list(r.prefixe(x)) + [x.get("annee") or ""]) if r.prefixe else []
            for k, _l, t in r.champs_excel():
                v = x.get(k)
                ligne.append(jjmmaaaa(v) if t == "date" else G.nom_eleve(v) if (t == "eleve" and v) else ("" if v is None else v))
            if calc_ent:
                cv = r.calcul(x)
                ligne += [cv.get(c, "") for c in calc_ent]
            rows.append(ligne)
        return ent + calc_ent, rows

    @app.route("/reg/<gcle>/<rcle>.xlsx")
    @H.connexion_requise()
    def reg_xlsx(gcle, rcle):
        G, r = groupe_reg(gcle, rcle)
        annee = annee_req()
        ent, rows = lignes_excel(G, r, G.lignes(r, annee, toutes_annees=bool(request.args.get("tout"))))
        if request.args.get("tout") and not r.prefixe:
            ent, rows = ["Année scolaire"] + ent, [[x["annee"]] + l for x, l in zip(G.lignes(r, toutes_annees=True), rows)]
        return H.xlsx.reponse_classeur(f"{r.cle}_{annee}.xlsx", [(r.feuille, ent, rows, {})])

    @app.route("/reg/<gcle>/<rcle>/modele.xlsx")
    @H.connexion_requise()
    def reg_modele(gcle, rcle):
        G, r = groupe_reg(gcle, rcle)
        ent = (["Niveau", "Entité", r.annee_lib] if r.prefixe else []) + [l for _k, l, _t in r.champs_excel()]
        return H.xlsx.reponse_classeur(f"modele_{r.cle}.xlsx", [(r.feuille, ent, [], {})])

    @app.route("/reg/<gcle>/<rcle>/import", methods=["POST"])
    @H.connexion_requise()
    def reg_import(gcle, rcle):
        import outils_xlsx as X
        G, r = groupe_reg(gcle, rcle)
        exiger(G, r)
        annee = annee_req()
        fichier = request.files.get("fichier")
        if not fichier or not fichier.filename:
            flash("Choisissez un fichier Excel (.xlsx).", "warning")
            return redirect(url_for("reg_page", gcle=gcle, rcle=rcle, annee=annee))
        try:
            wb = X._openpyxl().load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            flash("Fichier illisible : utilisez le modèle Excel.", "danger")
            return redirect(url_for("reg_page", gcle=gcle, rcle=rcle, annee=annee))
        ws = next((w for w in wb.worksheets if X.normaliser(w.title) == X.normaliser(r.feuille)), wb.worksheets[0])
        rows = [list(x) for x in ws.iter_rows(values_only=True)]
        libs = {X.normaliser(l): k for k, l, _t in r.champs_excel()}
        i0 = next((i for i, x in enumerate(rows[:15]) if x and sum(1 for v in x if X.normaliser(v) in libs) >= 2), None)
        if i0 is None:
            flash("En-têtes introuvables : utilisez le modèle Excel du registre.", "danger")
            return redirect(url_for("reg_page", gcle=gcle, rcle=rcle, annee=annee))
        idx = {libs[X.normaliser(v)]: j for j, v in enumerate(rows[i0]) if X.normaliser(v) in libs}
        j_annee = next((j for j, v in enumerate(rows[i0]) if X.normaliser(v) in ("annee scolaire", "saison")), None)
        j_entite = next((j for j, v in enumerate(rows[i0]) if X.normaliser(v) == "entite"), None)
        j_niveau = next((j for j, v in enumerate(rows[i0]) if X.normaliser(v) == "niveau"), None)
        maj_n = 0
        eleves = {_norm(lib.split(" (")[0]): eid for eid, lib in eleves_ecole()} if "eleve" in r.typ.values() else {}
        n, refus = 0, 0
        for x in rows[i0 + 1:]:
            if not x or not any(v not in (None, "") for v in x) or X.normaliser(x[0]) == "total":
                continue
            brut = {}
            for k, j in idx.items():
                v = X.valeur(x, j)
                t = r.typ[k]
                if t == "eleve":
                    v = eleves.get(_norm(str(v).split(" (")[0]), "")
                elif t == "date" and v:
                    v = iso(v)
                brut[k] = v
            if r.prefixe and "ecole" in r.typ and not brut.get("ecole") and j_entite is not None:
                brut["ecole"] = X.valeur(x, j_entite)
            if r.entite:
                brut["niveau"] = niveau_code(X.valeur(x, j_niveau)) if j_niveau is not None else ""
                brut["entite"] = X.valeur(x, j_entite) if j_entite is not None else ""
                if not brut["niveau"] and not brut["entite"]:
                    brut["niveau"], brut["entite"] = entite_courante()
            d = G.lire_formulaire(r, brut)
            if d.get(r.oblig) in (None, ""):
                refus += 1
                continue
            a = X.valeur(x, j_annee) if j_annee is not None else ""
            a = a if re.fullmatch(r"\d{4}-\d{4}", a or "") else annee
            ks = list(d)
            if r.unique:
                w = " AND ".join(f"COALESCE({k},'')=COALESCE(?,'')" for k in r.unique)
                old = H.q(f"SELECT id FROM {r.table} WHERE portee=? AND annee=? AND {w}", (cle_portee(r.portee), a) + tuple(d.get(k) for k in r.unique), un=True)
                if old:
                    H.ex(f"UPDATE {r.table} SET " + ", ".join(f"{k}=?" for k in ks) + ", maj=? WHERE id=?", tuple(d[k] for k in ks) + (H.maintenant(), old["id"]))
                    if r.apres_enregistrer:
                        try:
                            r.apres_enregistrer(old["id"])
                        except Exception:  # noqa: BLE001
                            pass
                    maj_n += 1
                    continue
            H.ex(f"INSERT INTO {r.table} (portee, annee, " + ", ".join(ks) + ", cree_le, cree_par, maj) VALUES (?,?," + ",".join("?" * len(ks)) + ",?,?,?)",
                 (cle_portee(r.portee), a) + tuple(d[k] for k in ks) + (H.maintenant(), g.user["id"], H.maintenant()))
            if r.apres_enregistrer:
                try:
                    r.apres_enregistrer(H.q(f"SELECT MAX(id) m FROM {r.table}", un=True)["m"])
                except Exception:  # noqa: BLE001
                    pass
            n += 1
        H.journal(r.table + "_import", f"{n} ligne(s), {refus} refus")
        flash(f"Import : {n} ligne(s) ajoutée(s)" + (f", {maj_n} mise(s) à jour" if maj_n else "") + (f", {refus} refusée(s) (rubrique obligatoire vide)" if refus else "") + ".",
              "success" if not refus else "warning")
        return redirect(url_for("reg_page", gcle=gcle, rcle=rcle, annee=annee))

    @app.route("/reg/<gcle>/<rcle>.pdf")
    @H.connexion_requise()
    def reg_pdf(gcle, rcle):
        G, r = groupe_reg(gcle, rcle)
        annee = annee_req()
        filtres = {k: (request.args.get("f_" + k) or "").strip() for k in r.filtres}
        lignes = G.lignes(r, annee, (request.args.get("q") or "").strip(), filtres)
        cols = r.cols_table()
        ent = ["N°"] + [l for _k, l, _t in cols]
        calc_ent = list(r.calcul(lignes[0]).keys()) if (r.calcul and lignes) else []
        rows = [[i] + [G.valeur_affichee(r, x, k) for k, _l, _t in cols] + ([r.calcul(x).get(c, "") for c in calc_ent]) for i, x in enumerate(lignes, 1)]
        tot = None
        if r.totaux:
            tot = ["Total"] + [(fcfa(sum(x.get(k) or 0 for x in lignes)) if r.typ.get(k) == "montant" else sum(x.get(k) or 0 for x in lignes))
                               if k in r.totaux else "" for k, _l, _t in cols] + [""] * len(calc_ent)
        larg = [5] + [26 if (t or "") == "long" else 14 for _k, _l, t in cols] + [12] * len(calc_ent)
        lu = largeur_utile(r.paysage)
        corps = [tableau(ent + calc_ent, rows, larg, lu, tot)]
        sigs = r.signataires(lignes) if r.signataires else [signature_autorite()]
        filt = ", ".join(f"{r.lib[k]} : {v}" for k, v in filtres.items() if v)
        code = code_document(r.table, f"{r.doc} — {annee}{' — ' + filt if filt else ''} ({len(lignes)} ligne(s))",
                             f"reg:{r.cle}:{cle_portee(r.portee)}:{annee}:{filt}:{len(lignes)}:{max([x.get('maj') or '' for x in lignes] or [''])}")
        sous = f"{_H.config.ECOLE.get('nom', '') if not juridiction() or g.get('ecole') else ''} · année scolaire {annee}" + (f" · {filt}" if filt else "")
        return H.pdf_reponse(pdf_document(r.doc.upper(), corps, sigs, code, r.paysage, sous.strip(" ·"), bandeau=G.bandeau() if G.bandeau else None),
                             f"{r.cle}_{annee}.pdf")

    @app.route("/reg/<gcle>/<rcle>/<int:rid>.pdf")
    @H.connexion_requise()
    def reg_fiche_pdf(gcle, rcle, rid):
        G, r = groupe_reg(gcle, rcle)
        if not r.fiche:
            abort(404)
        x = G.ligne(r, rid)
        titre, corps, sigs, paysage = (list(r.fiche(x)) + [False])[:4]
        code = code_document(r.table + "_fiche", f"{titre} — {r.titre} n° {rid}", f"reg:{r.cle}:fiche:{rid}:{x.get('maj') or ''}")
        return H.pdf_reponse(pdf_document(titre.upper(), corps, sigs, code, paysage, bandeau=G.bandeau() if G.bandeau else None), f"{r.cle}_{rid}.pdf")


def _route_fiches(app, H):
    @app.route("/reg/<gcle>/<rcle>/<int:rid>/<doc>.pdf")
    @H.connexion_requise()
    def reg_doc_pdf(gcle, rcle, rid, doc):
        G = GROUPES.get(gcle)
        if not G or rcle not in G.registres or not H.peut(G.droit):
            abort(404)
        r = G.registres[rcle]
        if doc not in r.fiches:
            abort(404)
        x = G.ligne(r, rid)
        titre, corps, sigs, paysage = (list(r.fiches[doc][2](x)) + [False])[:4]
        code = code_document(r.table + "_" + doc, f"{titre} — {r.titre} n° {rid}", f"reg:{r.cle}:{doc}:{rid}:{x.get('maj') or ''}")
        return H.pdf_reponse(pdf_document(titre.upper(), corps, sigs, code, paysage, bandeau=G.bandeau() if G.bandeau else None), f"{r.cle}_{doc}_{rid}.pdf")


def fiche_simple(G, r, x, titre=None, sigs=None, exclure=()):
    """Fiche individuelle : toutes les rubriques en tableau (libellé / valeur)."""
    st = styles()
    lignes = [[l, G.valeur_affichee(r, x, k)] for k, l, _t in r.champs if k not in exclure and x.get(k) not in (None, "")]
    corps = [tableau(["Rubrique", "Renseignement"], lignes, [1, 2.6], largeur_utile(False))]
    _ = st
    return titre or r.unite.capitalize(), corps, sigs or [signature_autorite()]
