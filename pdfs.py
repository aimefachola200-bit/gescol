# -*- coding: utf-8 -*-
"""Génération des documents PDF (ReportLab) : bulletins, reçus, carte, certificats, fiche CEP.
Chaque document porte un QR code et un code de vérification."""
import io
import os
from datetime import date, datetime

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

import config

BLEU = colors.HexColor("#1F4E79")
GRIS = colors.HexColor("#F2F4F7")
VERT = colors.HexColor("#1B7F3B")
ROUGE = colors.HexColor("#B42318")

MINISTERE = {
    "maternelle": "Ministère des Enseignements Maternel et Primaire",
    "primaire": "Ministère des Enseignements Maternel et Primaire",
    "secondaire": "Ministère des Enseignements Secondaire, Technique et de la Formation Professionnelle",
}

ST_CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10)
ST_TEXTE = ParagraphStyle("texte", fontName="Helvetica", fontSize=11.5, leading=18, alignment=4)


# ---------------------------------------------------------------- utilitaires
def mention_concepteur(c, largeur=None):
    """v1.32 — documents administratifs : mention très discrète « Conception : Maître Aimé FACHOLA » (gris clair, 4,5 pt,
    marge basse à droite), sans téléphone."""
    w = largeur or c._pagesize[0]
    c.saveState()
    c.setFillColor(colors.HexColor("#C4C8CF"))
    c.setFont("Helvetica", 4.5 if c._pagesize[1] >= 120 * mm else 3.6)
    c.drawRightString(w - (6 if c._pagesize[1] >= 120 * mm else 2.5) * mm, 1.8 * mm, f"Conception : {config.CONCEPTEUR}")
    c.restoreState()


def mention_pedagogique(c, largeur=None):
    """v1.32 — fiches de préparation, résumés, épreuves, cahiers et guides : « Conception : Maître Aimé FACHOLA —
    +229 01 96 51 03 33 » en petit (7,5 pt, gris), centré en bas de chaque page."""
    w = largeur or c._pagesize[0]
    c.saveState()
    c.setFillColor(colors.HexColor("#98A2B3"))
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(w / 2, 3.4 * mm, f"Conception : {config.CONCEPTEUR} — {getattr(config, 'CONCEPTEUR_TEL', '')}".rstrip(" —"))
    c.restoreState()


class GCanvas(canvas.Canvas):
    """Canvas SCOLARIS : ajoute la mention (discrète) du concepteur sur chaque page."""
    mention = staticmethod(mention_concepteur)

    def showPage(self):
        self.mention(self)
        super().showPage()

    def save(self):
        if self._code:  # page en cours non terminée
            self.mention(self)
        super().save()


class GCanvasPeda(GCanvas):
    """Canvas des documents pédagogiques (fiches, résumés, épreuves, cahiers) : mention du concepteur avec téléphone."""
    mention = staticmethod(mention_pedagogique)


class GCanvasPedaNum(GCanvasPeda):
    """v1.32 — Fiches de préparation : « Page x / y » centré en bas (recto verso) en plus de la mention du concepteur."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._etats = []

    def showPage(self):
        self._etats.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._etats)
        for etat in self._etats:
            self.__dict__.update(etat)
            self.saveState()
            self.setFillColor(colors.HexColor("#344054"))
            self.setFont("Helvetica", 9)
            self.drawCentredString(self._pagesize[0] / 2, 8 * mm, f"Page {self._pageNumber} / {n}")
            self.restoreState()
            self.mention(self)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def fcfa(n):
    return f"{int(n):,}".replace(",", " ") + f" {config.DEVISE}"


def date_fr(iso):
    if not iso:
        return "—"
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(iso)


def ne_e(eleve):
    return "né" if eleve["sexe"] == "M" else "née"


def l_eleve(eleve):
    return "l'élève"


_U = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
      "onze", "douze", "treize", "quatorze", "quinze", "seize"]
_D = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante", 8: "quatre-vingt"}


def _m100(n):
    if n < 17:
        return _U[n]
    if n < 20:
        return "dix-" + _U[n - 10]
    d, u = divmod(n, 10)
    if d in (7, 9):
        base = "soixante" if d == 7 else "quatre-vingt"
        if d == 7 and u == 1:
            return "soixante et onze"
        return base + "-" + _m100(10 + u)
    base = _D[d]
    if u == 0:
        return base + ("s" if d == 8 else "")
    if u == 1 and d != 8:
        return base + " et un"
    return base + "-" + _U[u]


def _m1000(n):
    c, r = divmod(n, 100)
    if c == 0:
        return _m100(r)
    pre = "cent" if c == 1 else _U[c] + " cent"
    if r == 0:
        return pre + ("s" if c > 1 else "")
    return pre + " " + _m100(r)


def en_lettres(n):
    """Montant en toutes lettres (orthographe traditionnelle)."""
    n = int(n)
    if n == 0:
        return "zéro"
    parts = []
    for val, nom in ((10 ** 9, "milliard"), (10 ** 6, "million")):
        k, n = divmod(n, val)
        if k:
            parts.append(en_lettres(k) + " " + nom + ("s" if k > 1 else ""))
    k, n = divmod(n, 1000)
    if k:
        if k == 1:
            parts.append("mille")
        else:
            t = _m1000(k)
            if t.endswith("cents") or t.endswith("vingts"):
                t = t[:-1]  # « deux cent mille », « quatre-vingt mille »
            parts.append(t + " mille")
    if n:
        parts.append(_m1000(n))
    return " ".join(parts)


def _image(chemin):
    if chemin and os.path.exists(chemin):
        try:
            return ImageReader(chemin)
        except Exception:
            return None
    return None


# ---------------------------------------------------------------- en-tête officiel (v1.7)
# Armoiries de la République du Bénin et bloc « armoiries + MINISTÈRE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE +
# RÉPUBLIQUE DU BÉNIN » (images fournies dans static/), en tête des fiches et cartes des écoles.
def dossiers_static():
    """Dossiers « static » possibles : celui de l'application web (config.WEB_DIR — sur Android autonome, les fichiers
    web sont décompressés à part des modules Python), puis celui du code (exécution depuis les sources)."""
    out = []
    for d in (getattr(config, "WEB_DIR", None), getattr(config, "BASE_DIR", None),
              os.path.dirname(os.path.abspath(__file__))):
        if d and os.path.join(d, "static") not in out:
            out.append(os.path.join(d, "static"))
    return out


def fichier_static(nom):
    """Chemin d'un fichier de static/ (premier trouvé), ou None."""
    for d in dossiers_static():
        p = os.path.join(d, nom)
        if os.path.exists(p):
            return p
    return None


_OFFICIELLES = {}



_SERIF = {}


def police_serif():
    """v1.30 — Police des épreuves (« Times New Roman 14 pt ») : Liberation Serif (métriquement compatible avec Times New
    Roman, licence SIL OFL, fichiers static/fonts/LiberationSerif-*.ttf) enregistrée et incorporée au PDF ; à défaut, la
    Times-Roman intégrée à reportlab (codage WinAnsi : accents français, œ et Œ compris).
    Renvoie {"normal", "gras", "italique", "gras_italique", "nom"}."""
    if _SERIF:
        return _SERIF
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        noms = {}
        for cle, suffixe in (("normal", "Regular"), ("gras", "Bold"), ("italique", "Italic"), ("gras_italique", "BoldItalic")):
            f = fichier_static(f"fonts/LiberationSerif-{suffixe}.ttf")
            if not f:
                raise FileNotFoundError(suffixe)
            nom = f"LiberationSerif-{suffixe}"
            if nom not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(nom, f))
            noms[cle] = nom
        pdfmetrics.registerFontFamily("LiberationSerif", normal=noms["normal"], bold=noms["gras"], italic=noms["italique"], boldItalic=noms["gras_italique"])
        _SERIF.update(noms, nom="Liberation Serif (compatible Times New Roman)")
    except Exception:  # noqa: BLE001 — police absente : Times intégrée
        _SERIF.update(normal="Times-Roman", gras="Times-Bold", italique="Times-Italic", gras_italique="Times-BoldItalic", nom="Times-Roman")
    return _SERIF

def image_officielle(nom):
    """« armoiries » ou « memp » (static/docs_enseignant_<nom>.png), mise en cache (seulement si trouvée)."""
    if _OFFICIELLES.get(nom) is None:
        _OFFICIELLES[nom] = _image(fichier_static(f"docs_enseignant_{nom}.png"))
    return _OFFICIELLES[nom]


def armoiries(c, x, y_haut, hauteur, centre=False):
    """Armoiries (coin supérieur gauche en x, y_haut ; ou centrées sur x si centre). Retourne la largeur dessinée."""
    img = image_officielle("armoiries")
    if not img:
        return 0
    iw, ih = img.getSize()
    w = hauteur * iw / ih
    c.drawImage(img, x - w / 2 if centre else x, y_haut - hauteur, w, hauteur, mask="auto")
    return w


def bloc_memp(c, x, y_haut, hauteur):
    """Emblème du MEMP : armoiries + « MINISTÈRE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE » + bande tricolore +
    « RÉPUBLIQUE DU BÉNIN ». Retourne la largeur dessinée."""
    img = image_officielle("memp")
    if img:
        iw, ih = img.getSize()
        c.drawImage(img, x, y_haut - hauteur, hauteur * iw / ih, hauteur)
        return hauteur * iw / ih
    w = armoiries(c, x, y_haut, hauteur)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", hauteur / 6.5)
    for i, t in enumerate(("MINISTÈRE DES ENSEIGNEMENTS", "MATERNEL ET PRIMAIRE", "", "RÉPUBLIQUE DU BÉNIN")):
        c.drawString(x + w + 4, y_haut - (i + 1) * hauteur / 4.6, t)
    return w + 4 + c.stringWidth("MINISTÈRE DES ENSEIGNEMENTS", "Helvetica", hauteur / 6.5)


def entete_ministere(c, x, y_haut, cycle="primaire", hauteur=34):
    """Bloc ministère en haut à gauche d'un document : emblème du MEMP (maternelle, primaire) ou armoiries + nom du
    ministère du secondaire. Retourne (largeur, hauteur) occupées."""
    if (cycle or "primaire") != "secondaire":
        return bloc_memp(c, x, y_haut, hauteur), hauteur
    w = armoiries(c, x, y_haut, hauteur)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x + w + 5, y_haut - 9, "RÉPUBLIQUE DU BÉNIN")
    c.setFont("Helvetica", 6.6)
    for i, t in enumerate(("MINISTÈRE DES ENSEIGNEMENTS SECONDAIRE,", "TECHNIQUE ET DE LA FORMATION",
                           "PROFESSIONNELLE")):
        c.drawString(x + w + 5, y_haut - 19 - 8 * i, t)
    return w + 5 + c.stringWidth("MINISTÈRE DES ENSEIGNEMENTS SECONDAIRE,", "Helvetica", 6.6), hauteur


def _ecole_img(nom):
    if nom == "logo.png" and config.ECOLE.get("id"):
        propre = _image(os.path.join(config.ECOLE_DIR, f"logo_{config.ECOLE['id']}.png"))
        if propre:
            return propre
    return _image(os.path.join(config.ECOLE_DIR, nom))


def image_data_url(data_url):
    """ImageReader à partir d'une image « data:image/png;base64,... » (signatures digitales)."""
    if not data_url or not str(data_url).startswith("data:image/"):
        return None
    import base64
    try:
        return ImageReader(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1])))
    except Exception:  # noqa: BLE001
        return None


def cachet_ecole(c, cx, cy, rayon=15 * mm):
    """Cachet de l'école courante : cachet généré (texte en arc) sinon image cachet.png. Retourne True si dessiné."""
    import cachet as _cachet
    if _cachet.masques():   # v2.4.6 : bouton « Cachets »
        return False
    ca = config.ECOLE.get("_cachet")
    if ca:
        _cachet.dessiner(c, cx, cy, rayon, *ca)
        return True
    img = _ecole_img("cachet.png")
    if img:
        c.drawImage(img, cx - rayon, cy - rayon, 2 * rayon, 2 * rayon, preserveAspectRatio=True, mask="auto")
        return True
    return False


def signature_directeur():
    return image_data_url(config.ECOLE.get("_sig_directeur")) or _ecole_img("signature.png")


def griffe_ecole(c, cx, cy, largeur=38 * mm, griffe=None):
    """Griffe (cachet rectangulaire du nom du directeur) de l'école courante, centrée en (cx, cy).
    griffe = (lignes, couleur) pour un autre signataire. Retourne la hauteur dessinée (0 si inactive)."""
    gr = griffe if griffe is not None else config.ECOLE.get("_griffe")
    if not gr:
        return 0
    import cachet as _cachet
    return _cachet.dessiner_nom(c, cx, cy, gr[0], gr[1], largeur)


def bloc_signature(c, x, y, titre, nom="", image=None, cachet=False, lieu_date=True, largeur=45 * mm, griffe=None):
    """Bloc de signature générique centré en x : [lieu, date] titre, signature (image), cachet, nom.
    Quand la griffe de l'école est active (cachet=True) ou qu'une griffe (lignes, couleur) est donnée, elle remplace la
    ligne du nom (le nom y reste lisible), sous la signature et à droite du cachet rond."""
    c.saveState()
    c.setFillColor(colors.black)
    if lieu_date:
        c.setFont("Helvetica", 8.5)
        c.drawCentredString(x, y, f"{config.ECOLE.get('ville') or ''}, le {date.today().strftime('%d/%m/%Y')}")
        y -= 12
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x, y, titre)
    if cachet:
        cachet_ecole(c, x - 9 * mm, y - 15.5 * mm, 11 * mm)
    if image is not None:
        c.drawImage(image, x - largeur / 2, y - 23 * mm, largeur, 17 * mm, preserveAspectRatio=True, mask="auto")
    gr = griffe if griffe is not None else (config.ECOLE.get("_griffe") if cachet else None)
    if gr and nom:
        h = griffe_ecole(c, x + 4 * mm, y - 29 * mm, 36 * mm, gr)
        c.restoreState()
        return y - 29 * mm - h / 2
    if nom:
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(x, y - 30.5 * mm, nom)
    c.restoreState()
    return y - 30 * mm


def url_verif(code):
    """Adresse encodée dans le QR : l'adresse publique réglée, sinon celle par laquelle
    l'application est consultée en ce moment."""
    base = config.URL_PUBLIQUE
    if not base:
        try:
            from flask import request
            base = request.host_url
        except RuntimeError:
            base = "http://localhost:5100"
    if _adresse_locale(base):     # v2.2 : jamais « http://localhost/… » sur un document (adresse inutilisable ailleurs)
        return f"{getattr(config, 'NOMS_APPLI', {}).get(getattr(config, 'EDITION', ''), 'SCOLARIS') if hasattr(config, 'NOMS_APPLI') else 'SCOLARIS'} — code de vérification {code} — Vérifier dans l'application (menu Vérifier un document)"
    return f"{base.rstrip('/')}/verifier/{code}"


def _adresse_locale(base):
    import urllib.parse
    h = (urllib.parse.urlsplit(base or "").hostname or "").lower()
    return not h or h in ("localhost", "0.0.0.0", "::1") or h.startswith("127.")


def texte_verif(code):
    """v2.2 — ligne imprimée sous le QR : l'adresse de vérification, ou « Vérifier dans l'application » sans adresse publique."""
    u = url_verif(code)
    return u if u.startswith("http") else f"Vérifier dans l'application · code {code}"


_QR_CACHE = {}


def qr_modules(texte):
    """Matrice du QR code (niveau L, comme QrCodeWidget), gardée en cache."""
    m = _QR_CACHE.get(texte)
    if m is None:
        from reportlab.graphics.barcode import qrencoder
        qr = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.L)
        qr.addData(texte)
        qr.make()
        m = [[bool(v) for v in ligne] for ligne in qr.modules]
        if len(_QR_CACHE) > 2000:
            _QR_CACHE.clear()
        _QR_CACHE[texte] = m
    return m


def dessiner_qr(c, texte, x, y, taille, bord=4):
    """v1.33 : QR code tracé directement sur le canevas (un seul chemin) — même rendu que QrCodeWidget, bien plus
    rapide (bulletins d'une classe entière, cartes, attestations en série)."""
    m = qr_modules(texte)
    n = len(m)
    pas = taille / (n + 2.0 * bord)
    p = c.beginPath()
    for r, ligne in enumerate(m):
        col = 0
        while col < n:
            if ligne[col]:
                debut = col
                while col < n and ligne[col]:
                    col += 1
                p.rect(x + (debut + bord) * pas, y + taille - (r + bord + 1) * pas, (col - debut) * pas, pas)
            else:
                col += 1
    c.saveState()
    c.setFillColor(colors.black)
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def _qr(c, code, x, y, taille=22 * mm, legende=True):
    dessiner_qr(c, url_verif(code), x, y, taille)
    if legende:
        c.setFont("Helvetica", 6.5)
        c.setFillColor(colors.black)
        c.drawString(x + taille + 2 * mm, y + taille - 8, "Document vérifiable")
        c.drawString(x + taille + 2 * mm, y + taille - 17, f"Code : {code}")
        c.drawString(x + taille + 2 * mm, y + taille - 26, texte_verif(code)[:60])


def _entete(c, cycle, titre, sous_titre=None, W=A4[0], H=A4[1], marge=15 * mm):
    """En-tête officiel : emblème du ministère (armoiries + MEMP) à gauche, école et logo à droite.
    Retourne l'ordonnée sous l'en-tête."""
    haut = H - marge
    entete_ministere(c, marge, haut + 2, cycle or "primaire", hauteur=38)

    logo = _ecole_img("logo.png")
    if logo:
        c.drawImage(logo, W - marge - 20 * mm, haut - 20 * mm, 20 * mm, 20 * mm,
                    preserveAspectRatio=True, mask="auto")
    xd = W - marge - (23 * mm if logo else 0)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(xd, haut - 8, config.ECOLE["nom"])
    c.setFont("Helvetica", 7.5)
    lignes = [config.ECOLE["adresse"]]
    if config.ECOLE.get("telephone"):
        lignes.append("Tél. : " + config.ECOLE["telephone"])
    if config.ECOLE.get("email"):
        lignes.append(config.ECOLE["email"])
    if config.ECOLE.get("devise"):          # v1.32 : devise de l'école
        lignes.append("« " + config.ECOLE["devise"] + " »")
    for i, t in enumerate(lignes):
        if t.startswith("« "):
            c.setFont("Helvetica-Oblique", 7.5)
        c.drawRightString(xd, haut - 19 - 9 * i, t)

    y = haut - 50
    c.setStrokeColor(BLEU)
    c.setLineWidth(1.2)
    c.line(marge, y, W - marge, y)
    y -= 24
    c.setFillColor(BLEU)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(W / 2, y, titre)
    if sous_titre:
        y -= 15
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.black)
        c.drawCentredString(W / 2, y, sous_titre)
    c.setFillColor(colors.black)
    return y - 18


def _signature(c, x, y, titre="Le Directeur"):
    c.setFont("Helvetica", 9)
    c.drawCentredString(x, y, f"{config.ECOLE['ville']}, le {date.today().strftime('%d/%m/%Y')}")
    c.setFont("Helvetica-Bold", 10)
    if titre == "Le Directeur" and config.ECOLE.get("directeur_titre") == "Directrice":
        titre = "La Directrice"
    c.drawCentredString(x, y - 14, titre)
    sign = signature_directeur()
    cachet_ecole(c, x - 17 * mm, y - 35 * mm, 15 * mm)
    if sign:
        c.drawImage(sign, x - 20 * mm, y - 38 * mm, 40 * mm, 18 * mm, preserveAspectRatio=True, mask="auto")
    if config.ECOLE.get("_griffe"):
        griffe_ecole(c, x + 9 * mm, y - 58 * mm + 16, 38 * mm)
    elif config.ECOLE.get("directeur"):
        c.setFont("Helvetica", 9.5)
        c.drawCentredString(x, y - 58 * mm + 30, config.ECOLE["directeur"])


def _infos(c, x, y, largeur, couples, cols=2):
    """Bloc d'identité en grille label/valeur."""
    data, ligne = [], []
    for lab, val in couples:
        ligne += [lab, Paragraph(str(val or "—"), ST_CELL)]
        if len(ligne) == 2 * cols:
            data.append(ligne)
            ligne = []
    if ligne:
        data.append(ligne + [""] * (2 * cols - len(ligne)))
    lw = 26 * mm
    vw = largeur / cols - lw
    t = Table(data, colWidths=[lw, vw] * cols)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        *[("FONT", (2 * i, 0), (2 * i, -1), "Helvetica-Bold", 8.5) for i in range(cols)],
        ("BOX", (0, 0), (-1, -1), 0.6, BLEU),
        ("BACKGROUND", (0, 0), (-1, -1), GRIS),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    _, h = t.wrapOn(c, largeur, 500)
    t.drawOn(c, x, y - h)
    return y - h


def _fin(c):
    c.save()


# ---------------------------------------------------------------- bulletin
def _dessiner_bulletin(c, b):
    """b = dict(eleve, classe, periode, annee, resultat, stats, code)"""
    W, H = A4
    m = 15 * mm
    e, cl, r, st = b["eleve"], b["classe"], b["resultat"], b["stats"]
    if r.cycle == "maternelle":
        return _dessiner_livret(c, b)
    y = _entete(c, r.cycle, "BULLETIN DE NOTES", f"{b['periode']} – Année scolaire {b['annee']}")
    y = _infos(c, m, y, W - 2 * m, [
        ("Nom et prénoms", f"{e['nom']} {e['prenoms']}"), ("Matricule", e["matricule"]),
        ("Classe", cl["nom"]), ("Sexe", "Masculin" if e["sexe"] == "M" else "Féminin"),
        ("Né(e) le", f"{date_fr(e['date_naissance'])} à {e['lieu_naissance'] or '—'}"),
        ("Effectif", st["effectif"]),
    ])
    y -= 10

    sec = r.cycle == "secondaire"
    entetes = ["N°", "Matière"] + (["Coef.", "Note /20", "Note × coef."] if sec else ["Note /20"]) + ["Appréciation"]
    data = [entetes]
    # Au secondaire, une matière sans note (LV2 non choisie, matière absente du niveau) n'apparaît pas.
    lignes_aff = [l for l in r.lignes if not (sec and l.statut == "manquant")]
    for i, l in enumerate(lignes_aff, 1):
        nom = l.nom + (" *" if l.exclue_2_3 else "")
        if l.statut == "dispensé":
            note, pts, app = "Disp.", "—", "Dispensé(e)"
        elif l.statut == "manquant":
            note, pts, app = "—", "—", "Non évalué"
        else:
            note, pts, app = f"{l.note:.2f}", f"{l.points:.2f}", l.appreciation
        ligne = [str(i), Paragraph(nom, ST_CELL)]
        ligne += [f"{l.coefficient:g}", note, pts] if sec else [note]
        data.append(ligne + [app])
    if sec:
        d = r.details
        data.append(["", "TOTAL", f"{d.get('somme_coefficients', 0):g}", "", f"{d.get('somme_points', 0):.2f}", ""])
        cw = [9 * mm, 78 * mm, 15 * mm, 20 * mm, 24 * mm, W - 2 * m - 146 * mm]
    else:
        cw = [9 * mm, 95 * mm, 25 * mm, W - 2 * m - 129 * mm]
    t = Table(data, colWidths=cw, repeatRows=1)
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), BLEU),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")),
        ("ALIGN", (2, 1), (-2, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    note_col = 3 if sec else 2
    for i, l in enumerate(lignes_aff, 1):
        if l.note is not None and l.note < 10:
            style.append(("TEXTCOLOR", (note_col, i), (note_col, i), ROUGE))
    if sec:
        style += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5), ("BACKGROUND", (0, -1), (-1, -1), GRIS)]
    t.setStyle(TableStyle(style))
    _, h = t.wrapOn(c, W - 2 * m, 600)
    t.drawOn(c, m, y - h)
    y -= h + 6
    if not sec and any(l.exclue_2_3 for l in r.lignes):
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(m, y - 4, "* Matière comptée dans la moyenne mais non prise en compte dans la règle des 2/3.")
        y -= 12
    y -= 6

    # Bloc résultats
    moy = f"{r.moyenne:.2f} / 20" if r.moyenne is not None else "—"
    gauche = [["Moyenne", moy], ["Rang", r.rang_texte], ["Mention", r.mention]]
    if not sec and r.details.get("matieres_standard"):
        d = r.details
        gauche.append(["Règle des 2/3", f"{d['standard_reussies']} / {d['matieres_standard']} matières >= 10 (seuil : {d['seuil_2_3']})"])
    droite = [["Moyenne de la classe", f"{st['moyenne_classe']:.2f}" if st["moyenne_classe"] is not None else "—"],
              ["Plus forte moyenne", f"{st['plus_forte']:.2f}" if st["plus_forte"] is not None else "—"],
              ["Plus faible moyenne", f"{st['plus_faible']:.2f}" if st["plus_faible"] is not None else "—"]]
    lg = (W - 2 * m) / 2 - 3 * mm
    for bloc, x, lw in ((gauche, m, 30 * mm), (droite, m + lg + 6 * mm, 42 * mm)):
        tb = Table(bloc, colWidths=[lw, lg - lw])
        style_b = [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
            ("BOX", (0, 0), (-1, -1), 0.6, BLEU), ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D5DD")),
        ]
        if x == m:
            style_b.append(("FONT", (1, 0), (1, 0), "Helvetica-Bold", 11))
        tb.setStyle(TableStyle(style_b))
        _, hb = tb.wrapOn(c, lg, 200)
        tb.drawOn(c, x, y - hb)
        hmax = hb if x == m else max(hmax, hb)
    y -= hmax + 12

    # Décision
    couleur = VERT if r.admis else (ROUGE if r.decision in ("NON ADMIS", "NON MAÎTRISE") else colors.grey)
    c.setFillColor(couleur)
    c.roundRect(m, y - 22, 70 * mm, 22, 4, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(m + 35 * mm, y - 15, f"DÉCISION : {r.decision}")
    c.setFillColor(colors.black)
    if not sec and r.details.get("notes_manquantes"):
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(m + 74 * mm, y - 9, f"Attention : {len(r.details['notes_manquantes'])} matière(s) non évaluée(s),")
        c.drawString(m + 74 * mm, y - 18, "ignorée(s) dans le calcul.")
    _observation(c, m, y - 32, W - 2 * m, r, b)

    # Pied : QR + signatures
    base = 20 * mm
    _qr(c, b["code"], m, base)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(W / 2 + 5 * mm, base + 55 * mm, "Le Parent")
    _signature(c, W - m - 35 * mm, base + 55 * mm)


def _observation(c, x, y, largeur, r, b):
    """Cadre « Observations » (texte de l'enseignant) + absences de l'année."""
    texte = (r.details.get("observation") or "").strip()
    abs_txt = ""
    if b.get("absences") is not None:
        a = b["absences"]
        abs_txt = f"Absences depuis la rentrée : {a.get('absent', 0)} jour(s) dont {a.get('justifie', 0)} justifié(s) · retards : {a.get('retard', 0)}"
    lignes = [["Observations", Paragraph((texte or "…………………………………………………………………………………………") + (f"<br/><font size=7.5 color='#475467'>{abs_txt}</font>" if abs_txt else ""), ST_CELL)]]
    t = Table(lignes, colWidths=[30 * mm, largeur - 30 * mm])
    t.setStyle(TableStyle([("FONT", (0, 0), (0, 0), "Helvetica-Bold", 9), ("BOX", (0, 0), (-1, -1), 0.6, BLEU),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    _, h = t.wrapOn(c, largeur, 200)
    t.drawOn(c, x, y - h)
    return y - h


def _dessiner_livret(c, b):
    """Maternelle : livret d'évaluation (appréciation par domaine, pas de moyenne ni de rang)."""
    W, H = A4
    m = 15 * mm
    e, cl, r = b["eleve"], b["classe"], b["resultat"]
    y = _entete(c, "maternelle", "LIVRET D'ÉVALUATION", f"{b['periode']} – Année scolaire {b['annee']}")
    y = _infos(c, m, y, W - 2 * m, [
        ("Nom et prénoms", f"{e['nom']} {e['prenoms']}"), ("Matricule", e["matricule"]),
        ("Classe", cl["nom"]), ("Sexe", "Masculin" if e["sexe"] == "M" else "Féminin"),
        ("Né(e) le", f"{date_fr(e['date_naissance'])} à {e['lieu_naissance'] or '—'}"), ("Niveau", cl["niveau"]),
    ])
    y -= 12
    data = [["Domaine d'apprentissage", "Acquis", "En cours", "Non acquis"]]
    spans = []
    for l in r.lignes:
        if l.statut == "dispensé":
            data.append([Paragraph(l.nom, ST_CELL), "Dispensé(e)", "", ""])
            spans.append(("SPAN", (1, len(data) - 1), (3, len(data) - 1)))
            spans.append(("BACKGROUND", (1, len(data) - 1), (3, len(data) - 1), colors.HexColor("#F2F4F7")))
            spans.append(("FONT", (1, len(data) - 1), (3, len(data) - 1), "Helvetica-Oblique", 9))
            continue
        k = l.code_appreciation
        data.append([Paragraph(l.nom, ST_CELL), "X" if k == "A" else "", "X" if k == "ECA" else "", "X" if k == "NA" else ""])
    cw = [W - 2 * m - 3 * 30 * mm, 30 * mm, 30 * mm, 30 * mm]
    t = Table(data, colWidths=cw)
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
             ("BACKGROUND", (0, 0), (-1, 0), BLEU), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("FONT", (1, 1), (-1, -1), "Helvetica-Bold", 11),
             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
             ("BACKGROUND", (1, 1), (1, -1), colors.HexColor("#ECFDF3")),
             ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#FFFAEB")),
             ("BACKGROUND", (3, 1), (3, -1), colors.HexColor("#FEF3F2"))] + spans
    t.setStyle(TableStyle(style))
    _, h = t.wrapOn(c, W, H)
    t.drawOn(c, m, y - h)
    y -= h + 16
    comptes = r.details.get("comptes") or {}
    bilan = r.decision if r.details.get("evalues") else "Non évalué"
    c.setFillColor(VERT if r.admis else (colors.HexColor("#B54708") if r.details.get("evalues") else colors.grey))
    c.roundRect(m, y - 24, 95 * mm, 24, 4, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(m + 47.5 * mm, y - 16, f"BILAN : {bilan}")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(m + 100 * mm, y - 15, f"{comptes.get('A', 0)} acquis · {comptes.get('ECA', 0)} en cours · {comptes.get('NA', 0)} non acquis")
    _observation(c, m, y - 36, W - 2 * m, r, b)
    base = 20 * mm
    _qr(c, b["code"], m, base)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(W / 2 + 5 * mm, base + 55 * mm, "Le Parent")
    _signature(c, W - m - 35 * mm, base + 55 * mm, titre="L'Enseignant(e) / Le Directeur")


def bulletins(liste):
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A4)
    c.setTitle("Bulletins de notes")
    for b in liste:
        _dessiner_bulletin(c, b)
        c.showPage()
    _fin(c)
    return buf.getvalue()


# ---------------------------------------------------------------- reçu
def recu(p, eleve, classe, total_paye, total_du, caissier, code, mode_libelle):
    W, H = A5
    m = 12 * mm
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A5)
    c.setTitle(f"Reçu {p['numero_recu']}")
    y = _entete(c, "", "REÇU DE PAIEMENT", f"N° {p['numero_recu']}", W=W, H=H, marge=m)
    if p["annule"]:
        c.saveState()
        c.setFillColor(colors.Color(0.8, 0, 0, alpha=0.25))
        c.setFont("Helvetica-Bold", 60)
        c.translate(W / 2, H / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, "ANNULÉ")
        c.restoreState()
    y = _infos(c, m, y, W - 2 * m, [
        ("Élève", f"{eleve['nom']} {eleve['prenoms']}"), ("Matricule", eleve["matricule"]),
        ("Classe", classe["nom"] if classe else "—"), ("Année", p["annee"]),
    ])
    y -= 10
    reste = max(total_du - total_paye, 0)
    lignes = [
        ["Date", date_fr(p["date_paiement"]) + " " + str(p["date_paiement"])[11:16]],
        ["Motif", p["motif"] or "Frais de scolarité"],
        ["Mode de paiement", mode_libelle],
    ]
    if p["reference"]:
        lignes.append(["Réf. transaction", p["reference"]])
    if p["telephone"]:
        lignes.append(["Téléphone payeur", p["telephone"]])
    lignes += [
        ["MONTANT REÇU", fcfa(p["montant"])],
        ["En lettres", Paragraph(en_lettres(p["montant"]).capitalize() + " francs CFA", ST_CELL)],
        ["Total scolarité", fcfa(total_du)],
        ["Total déjà versé", fcfa(total_paye)],
        ["RESTE À PAYER", fcfa(reste) if reste else "SOLDÉ"],
    ]
    t = Table(lignes, colWidths=[36 * mm, W - 2 * m - 36 * mm])
    i_mont = [i for i, l in enumerate(lignes) if l[0] == "MONTANT REÇU"][0]
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")),
        ("BACKGROUND", (0, i_mont), (-1, i_mont), GRIS), ("FONT", (1, i_mont), (1, i_mont), "Helvetica-Bold", 12),
        ("FONT", (1, -1), (1, -1), "Helvetica-Bold", 10),
        ("TEXTCOLOR", (1, -1), (1, -1), VERT if not reste else ROUGE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    _, h = t.wrapOn(c, W - 2 * m, 400)
    t.drawOn(c, m, y - h)
    y -= h + 14
    c.setFont("Helvetica", 8.5)
    c.drawString(m, y, f"Reçu par : {caissier or '—'}")
    _qr(c, code, m, 12 * mm, taille=20 * mm)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(W - m - 22 * mm, 36 * mm, "Le Comptable")
    import cachet as _cachet
    cachet = None if _cachet.masques() else _ecole_img("cachet.png")
    if cachet:
        c.drawImage(cachet, W - m - 40 * mm, 12 * mm, 22 * mm, 22 * mm, preserveAspectRatio=True, mask="auto")
    c.showPage()
    _fin(c)
    return buf.getvalue()


# ---------------------------------------------------------------- carte d'élève
def carte(eleve, classe, annee, code, photo):
    """Carte d'identité scolaire de l'élève (format carte bancaire). v1.7 : en-tête officiel — armoiries à gauche,
    République du Bénin, MEMP et école au centre, logo de l'école à droite."""
    W, H = 85.6 * mm, 54 * mm
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=(W, H))
    c.setTitle(f"Carte {eleve['matricule']}")
    armoiries(c, 2.2 * mm, H - 1.6 * mm, 11.5 * mm)
    logo = _ecole_img("logo.png")
    if logo:
        c.drawImage(logo, W - 12 * mm, H - 12 * mm, 10 * mm, 10 * mm, preserveAspectRatio=True, mask="auto")
    cx = W / 2 + 0.5 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 5.6)
    c.drawCentredString(cx, H - 4 * mm, "RÉPUBLIQUE DU BÉNIN")
    c.setFont("Helvetica", 4.6)
    c.drawCentredString(cx, H - 6.4 * mm, "MINISTÈRE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE")
    for k, col in enumerate((colors.HexColor("#008751"), colors.HexColor("#FCD116"), colors.HexColor("#E8112D"))):
        c.setFillColor(col)
        c.rect(cx - 15 * mm + k * 10 * mm, H - 7.7 * mm, 10 * mm, 0.6 * mm, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawCentredString(cx, H - 10.4 * mm, (config.ECOLE["nom"] or "")[:46])
    c.setFillColor(BLEU)
    c.rect(0, H - 16.4 * mm, W, 4.6 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6.6)
    c.drawCentredString(W / 2, H - 15 * mm, f"CARTE D'IDENTITÉ SCOLAIRE  •  {annee}")
    # photo
    px, py, pw, ph = 3 * mm, 9 * mm, 20 * mm, 26.5 * mm
    img = _image(photo)
    if img:
        c.drawImage(img, px, py, pw, ph, preserveAspectRatio=True, anchor="c")
    else:
        c.setStrokeColor(colors.grey)
        c.rect(px, py, pw, ph)
        c.setFont("Helvetica", 6)
        c.setFillColor(colors.grey)
        c.drawCentredString(px + pw / 2, py + ph / 2, "PHOTO")
    c.setFillColor(colors.black)
    x = 26 * mm
    lignes = [
        ("Nom", eleve["nom"]), ("Prénoms", eleve["prenoms"]),
        ("Né(e) le", f"{date_fr(eleve['date_naissance'])}"),
        ("Classe", classe["nom"] if classe else "—"), ("Matricule", eleve["matricule"]),
    ]
    yy = H - 20.5 * mm
    for lab, val in lignes:
        c.setFont("Helvetica", 5.8)
        c.drawString(x, yy, lab)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x + 12 * mm, yy, str(val or "—")[:26])
        yy -= 4.1 * mm
    c.setFont("Helvetica", 5.5)
    urgence = f"{eleve['parent_nom'] or ''} {eleve['parent_telephone'] or ''}".strip()
    if urgence:
        c.drawString(3 * mm, 5 * mm, f"Urgence : {urgence}"[:60])
    _qr(c, code, W - 13.5 * mm, 4.4 * mm, taille=11.5 * mm, legende=False)
    c.showPage()
    _fin(c)
    return buf.getvalue()


# ---------------------------------------------------------------- certificats
TITRES = {
    "certificat_frequentation": "CERTIFICAT DE FRÉQUENTATION",
    "attestation_inscription": "ATTESTATION D'INSCRIPTION",
    "certificat_transfert": "CERTIFICAT DE TRANSFERT",
}


def lignes_identite(c, x, y, largeur, couples, taille=10.5, pas=16):
    """Lignes « Libellé : valeur………… » (pointillés jusqu'au bord quand la valeur est vide ou courte).
    Retourne l'ordonnée sous la dernière ligne."""
    c.saveState()
    c.setFillColor(colors.black)
    for lib, val in couples:
        c.setFont("Helvetica-Bold", taille)
        c.drawString(x, y, f"{lib} : ")
        x1 = x + c.stringWidth(f"{lib} : ", "Helvetica-Bold", taille)
        val = str(val or "").strip()
        if val:
            c.setFont("Helvetica-Bold", taille)
            c.drawString(x1, y, val)
            x1 += c.stringWidth(val, "Helvetica-Bold", taille) + 4
        c.setFont("Helvetica", taille)
        wp = c.stringWidth(".", "Helvetica", taille)
        if x + largeur - x1 > 3 * wp:
            c.drawString(x1, y, "." * int((x + largeur - x1) / wp))
        y -= pas
    c.restoreState()
    return y


def certificat(type_doc, eleve, classe, annee, code, situation_financiere=None, destination=""):
    W, H = A4
    m = 22 * mm
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A4)
    c.setTitle(TITRES[type_doc])
    cycle = classe["cycle"] if classe else ""
    y = _entete(c, cycle, TITRES[type_doc], f"N° {code}")
    y -= 25
    qui = config.ECOLE["directeur"] or "………………………………"
    nom = f"<b>{eleve['nom']} {eleve['prenoms']}</b>"
    naiss = f"{ne_e(eleve)} le <b>{date_fr(eleve['date_naissance'])}</b> à <b>{eleve['lieu_naissance'] or '—'}</b>"
    cl = f"<b>{classe['nom']}</b>" if classe else "—"
    ident = f"{l_eleve(eleve)} {nom}, {naiss}, matricule <b>{eleve['matricule']}</b>"

    if type_doc == "certificat_frequentation":
        corps = [f"Je soussigné(e), {qui}, Directeur(trice) de l'établissement <b>{config.ECOLE['nom']}</b>, "
                 f"certifie que {ident}, fréquente régulièrement notre établissement en classe de {cl} "
                 f"au titre de l'année scolaire <b>{annee}</b>."]
    elif type_doc == "attestation_inscription":
        corps = [f"Je soussigné(e), {qui}, Directeur(trice) de l'établissement <b>{config.ECOLE['nom']}</b>, "
                 f"atteste que {ident}, est inscrit(e) dans notre établissement en classe de {cl} "
                 f"pour l'année scolaire <b>{annee}</b>, depuis le <b>{date_fr(eleve['date_inscription'])}</b>."]
    else:
        dest = f" pour l'établissement <b>{destination}</b>" if destination else ""
        corps = [f"Je soussigné(e), {qui}, Directeur(trice) de l'établissement <b>{config.ECOLE['nom']}</b>, "
                 f"certifie que {ident}, a fréquenté notre établissement du <b>{date_fr(eleve['date_inscription'])}</b> "
                 f"au <b>{date.today().strftime('%d/%m/%Y')}</b>, en dernier lieu en classe de {cl}, "
                 f"et est autorisé(e) à poursuivre sa scolarité{dest}."]
        if situation_financiere is not None:
            corps.append("Situation financière : " + (
                "<b>à jour</b>." if situation_financiere <= 0 else f"reste dû <b>{fcfa(situation_financiere)}</b>."))
    corps.append("En foi de quoi, le présent document lui est délivré pour servir et valoir ce que de droit.")
    # lignes d'identification : NIP (Numéro d'Identification Personnel) avant la ligne du nom
    nip = (eleve["nip"] if "nip" in eleve.keys() else "") or ""
    y = lignes_identite(c, m, y, W - 2 * m, [("NIP", nip), ("Nom et prénoms", f"{eleve['nom']} {eleve['prenoms']}")])
    y -= 6
    for txt in corps:
        p = Paragraph(txt, ST_TEXTE)
        _, h = p.wrap(W - 2 * m, 400)
        p.drawOn(c, m, y - h)
        y -= h + 14
    _signature(c, W - m - 35 * mm, y - 25)
    _qr(c, code, m, 20 * mm)
    c.showPage()
    _fin(c)
    return buf.getvalue()


# ---------------------------------------------------------------- fiche CEP
def fiche_cep(eleve, classe, annee, code, photo, sig_parent=None):
    W, H = A4
    m = 18 * mm
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A4)
    c.setTitle("Fiche CEP")
    y = _entete(c, "primaire", "FICHE DE RENSEIGNEMENTS – CANDIDAT AU CEP",
                f"Certificat d'Études Primaires – Session {annee.split('-')[-1]}")
    img = _image(photo)
    pw, ph = 35 * mm, 45 * mm
    if img:
        c.drawImage(img, W - m - pw, y - ph, pw, ph, preserveAspectRatio=True, anchor="c")
    else:
        c.rect(W - m - pw, y - ph, pw, ph)
        c.setFont("Helvetica", 8)
        c.drawCentredString(W - m - pw / 2, y - ph / 2, "Photo d'identité")
    lignes = [
        ("Nom", eleve["nom"]), ("Prénoms", eleve["prenoms"]),
        ("Sexe", "Masculin" if eleve["sexe"] == "M" else "Féminin"),
        ("Date de naissance", date_fr(eleve["date_naissance"])),
        ("Lieu de naissance", eleve["lieu_naissance"]),
        ("Matricule", eleve["matricule"]), ("Classe", classe["nom"] if classe else "—"),
        ("École", config.ECOLE["nom"]),
        ("Parent / tuteur", eleve["parent_nom"]), ("Téléphone", eleve["parent_telephone"]),
        ("Adresse", eleve["adresse"]),
    ]
    data = [[a, Paragraph(str(b or "—"), ST_CELL)] for a, b in lignes]
    t = Table(data, colWidths=[40 * mm, W - 2 * m - pw - 45 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    _, h = t.wrapOn(c, W, H)
    t.drawOn(c, m, y - h)
    y -= h + 25
    c.setFont("Helvetica", 9)
    c.drawString(m, y, "Pièces à joindre : copie de l'acte de naissance, photos d'identité, certificat de scolarité.")
    c.drawString(m, y - 30, "Signature du parent / tuteur :")
    img_p = image_data_url(sig_parent) if sig_parent else None  # v1.7 : signature digitale du parent
    if img_p:
        c.drawImage(img_p, m + 48 * mm, y - 44, 45 * mm, 17 * mm, preserveAspectRatio=True, anchor="w", mask="auto")
    _signature(c, W - m - 35 * mm, y - 30)
    _qr(c, code, m, 20 * mm)
    c.showPage()
    _fin(c)
    return buf.getvalue()


# ---------------------------------------------------------------- bulletin de paie
def bulletin_paie(b, p, mois_txt, params, code):
    W, H = A4
    m = 18 * mm
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=A4)
    c.setTitle(f"Bulletin de paie {mois_txt}")
    y = _entete(c, "", "BULLETIN DE PAIE", f"Période : {mois_txt}")
    y = _infos(c, m, y, W - 2 * m, [
        ("Nom et prénoms", f"{p['nom']} {p['prenoms']}"), ("Matricule", p["matricule"]),
        ("Fonction", p["fonction"]), ("Contrat", p["type_contrat"]),
        ("N° CNSS", p["numero_cnss"] or "—"), ("Embauche", date_fr(p["date_embauche"])),
    ])
    y -= 14
    t_sal = params["paie_cnss_salarie"]
    t_pat = params["paie_cnss_patronal"]
    vac = p["type_contrat"] == "Vacataire"
    lignes = [["Rubrique", "Base", "Taux", "À payer", "À retenir"]]
    if vac:
        lignes.append(["Heures effectuées", f"{b['heures']:g} h", fcfa(p["taux_horaire"]) + " / h", fcfa(b["salaire_base"]), ""])
    else:
        lignes.append(["Salaire de base", "", "", fcfa(b["salaire_base"]), ""])
    if b["primes"]:
        lignes.append(["Primes et indemnités", "", "", fcfa(b["primes"]), ""])
    lignes.append(["SALAIRE BRUT", "", "", fcfa(b["brut"]), ""])
    if b["cnss_salarie"]:
        lignes.append(["Cotisation CNSS (part salariale)", fcfa(b["brut"]), f"{t_sal} %", "", fcfa(b["cnss_salarie"])])
    if b["its"]:
        lignes.append(["Impôt sur les traitements et salaires (ITS)", "", "barème", "", fcfa(b["its"])])
    if b["retenues"]:
        lignes.append(["Autres retenues", "", "", "", fcfa(b["retenues"])])
    if b["avances"]:
        lignes.append(["Avances sur salaire", "", "", "", fcfa(b["avances"])])
    lignes.append(["NET À PAYER", "", "", fcfa(b["net"]), ""])
    t = Table(lignes, colWidths=[62 * mm, 29 * mm, 19 * mm, 32 * mm, W - 2 * m - 142 * mm])
    i_brut = [i for i, l in enumerate(lignes) if l[0] == "SALAIRE BRUT"][0]
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("BACKGROUND", (0, 0), (-1, 0), BLEU), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONT", (0, i_brut), (-1, i_brut), "Helvetica-Bold", 9), ("BACKGROUND", (0, i_brut), (-1, i_brut), GRIS),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ECFDF3")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    _, h = t.wrapOn(c, W, H)
    t.drawOn(c, m, y - h)
    y -= h + 10
    c.setFont("Helvetica", 9)
    c.drawString(m, y, f"Net à payer en lettres : {en_lettres(max(b['net'], 0)).capitalize()} francs CFA")
    y -= 22
    c.setFont("Helvetica-Bold", 9)
    c.drawString(m, y, "Charges patronales (pour information)")
    c.setFont("Helvetica", 9)
    c.drawString(m, y - 13, f"CNSS part patronale ({t_pat} %) : {fcfa(b['cnss_patronal'])}      VPS ({params['paie_vps']} %) : {fcfa(b['vps'])}")
    etat = {"brouillon": "BROUILLON – non validé", "valide": "Validé, en attente de paiement", "paye": f"Payé le {date_fr(b['paye_le'])}"}
    c.drawString(m, y - 30, f"Statut : {etat.get(b['statut'], b['statut'])}")
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(m + 35 * mm, y - 60, "L'employé(e)")
    _signature(c, W - m - 35 * mm, y - 50, titre="L'Employeur")
    if b["statut"] == "brouillon":
        c.saveState()
        c.setFillColor(colors.Color(0.7, 0.1, 0.1, alpha=0.15))
        c.setFont("Helvetica-Bold", 70)
        c.translate(W / 2, H / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, "BROUILLON")
        c.restoreState()
    _qr(c, code, m, 18 * mm)
    c.showPage()
    _fin(c)
    return buf.getvalue()


# ---------------------------------------------------------------- documents tabulaires génériques (modules v1.3)
def _entete_primaire(c, W, H, marge, infos_haut=None, cycle=None):
    """En-tête des documents du primaire : emblème du MEMP (armoiries + ministère + République) puis DDEMP, CS,
    école (colonne gauche) ; logo de l'école à droite."""
    y = H - marge
    _, h_bloc = entete_ministere(c, marge, y + 2, cycle or "primaire", hauteur=32)
    y -= h_bloc - 13
    lignes = infos_haut if infos_haut is not None else [
        ("DDEMP", config.ECOLE.get("departement")), ("CS", config.ECOLE.get("cs")), ("ÉCOLE", config.ECOLE.get("nom"))]
    yy = y - 27
    for lab, val in lignes:
        if val:
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(marge, yy, f"{lab} :")
            c.setFont("Helvetica", 7.5)
            c.drawString(marge + c.stringWidth(f"{lab} : ", "Helvetica-Bold", 7.5), yy, str(val)[:70])
            yy -= 9
            if lab == "ÉCOLE" and config.ECOLE.get("devise"):     # v1.32 : devise sous le nom de l'école
                c.setFont("Helvetica-Oblique", 7)
                c.drawString(marge, yy, "« " + str(config.ECOLE["devise"])[:80] + " »")
                yy -= 9
    logo = _ecole_img("logo.png")
    if logo:
        c.drawImage(logo, W - marge - 18 * mm, y - 18 * mm, 18 * mm, 18 * mm, preserveAspectRatio=True, mask="auto")
    return min(yy, y - 20 * mm) - 4


# v1.15 : enregistrement des documents vérifiables (réglé par app.py : enregistrer_document) —
# (type, libellé, clé) -> code. Sans lui (hors requête, tests de pdfs seuls) : pas de QR.
ENREGISTREUR = None
TYPES_TABLEAU = {}   # titre en capitales (début) -> type de document vérifiable


def code_tableau(titre, sous_titre, infos, lignes, total, verif=None):
    """Code de vérification d'un document en tableau signé : même contenu = même code (clé = empreinte du contenu)."""
    if ENREGISTREUR is None:
        return None
    import hashlib
    import re as _re

    def txt(v):
        if isinstance(v, Paragraph):
            return v.getPlainText()
        return "" if v is None else str(v)
    try:
        if verif:
            type_doc, libelle = verif
        else:
            t = _re.sub(r"<[^>]+>", "", str(titre)).strip()
            type_doc = next((v for k, v in TYPES_TABLEAU.items() if k in t.upper()), "tableau")
            st = _re.sub(r"<[^>]+>", "", str(sous_titre or "")).strip()
            libelle = (t + (" – " + st if st else ""))[:200]
            ident = " · ".join(f"{a} {txt(b)}" for a, b in (infos or [])[:4] if txt(b))
            if ident:
                libelle = (libelle + " – " + ident)[:250]
        brut = "|".join([str(titre), str(sous_titre)] + [f"{a}={txt(b)}" for a, b in (infos or [])]
                        + ["\t".join(txt(x) for x in l) for l in (lignes or [])] + ["\t".join(txt(x) for x in (total or []))])
        cle = type_doc + "|" + hashlib.sha256(brut.encode("utf-8")).hexdigest()[:32]
        return ENREGISTREUR(type_doc, libelle, cle)
    except Exception:  # noqa: BLE001 — un document reste imprimable même sans code
        return None


def document_tableau(titre, colonnes, lignes, sous_titre=None, infos=None, largeurs=None, paysage=False,
                     signatures=None, notes_bas=None, infos_haut=None, total=None, taille=7.5, avant=None, apres=None,
                     alignements=None, surlignes=None, cycle=None, code=None, verif=None, qr_bloc=True, police=None, pedagogique=False):
    """PDF d'un tableau (répété sur chaque page) avec en-tête officiel, bloc d'infos, signatures.
    colonnes : liste d'intitulés (ou liste de listes pour un en-tête sur plusieurs lignes)
    lignes : liste de listes ; total : ligne de total mise en gras
    infos : [(libellé, valeur)] affichés en grille sous le titre
    signatures : [(titre, nom, image_reader_ou_None, cachet_bool)]
    avant/apres : liste de flowables (Paragraph, Table) insérés avant/après le tableau
    surlignes : {indice_ligne: couleur_hex} pour colorer des lignes.
    police : None (Helvetica) ou "serif" (v1.30, épreuves : Times New Roman — Liberation Serif incorporée)."""
    from reportlab.lib.pagesizes import landscape
    from reportlab.platypus import SimpleDocTemplate, Spacer, KeepTogether
    from reportlab.platypus.flowables import Flowable

    taille_page = landscape(A4) if paysage else A4
    W, Hh = taille_page
    marge = 12 * mm
    buf = io.BytesIO()
    if police == "serif":
        _ps = police_serif()
        FN, FB = _ps["normal"], _ps["gras"]
    else:
        FN, FB = "Helvetica", "Helvetica-Bold"
    st_c = ParagraphStyle("c", fontName=FN, fontSize=taille, leading=taille + 1.6)
    st_h = ParagraphStyle("h", fontName=FB, fontSize=taille, leading=taille + 1.6, alignment=1,
                          textColor=colors.white)

    def cell(v, style=st_c):
        if isinstance(v, Flowable):
            return v
        return Paragraph("" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>"), style)

    entetes = colonnes if colonnes and isinstance(colonnes[0], (list, tuple)) else [colonnes]
    nh = len(entetes)
    data = [[cell(h, st_h) if h is not None else "" for h in row] for row in entetes]
    data += [[cell(v) for v in l] for l in lignes]
    if total:
        st_t = ParagraphStyle("t", parent=st_c, fontName=FB)
        data.append([cell(v, st_t) for v in total])
    utile = W - 2 * marge
    if not largeurs:
        largeurs = [utile / max(1, len(entetes[-1]))] * len(entetes[-1])
    else:
        s = sum(largeurs)
        largeurs = [utile * x / s for x in largeurs]
    t = Table(data, colWidths=largeurs, repeatRows=nh)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#667085")),
        ("BACKGROUND", (0, 0), (-1, nh - 1), BLEU),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, nh), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
    ]
    for r, row in enumerate(entetes):  # cellules fusionnées : None = prolonge la cellule de gauche
        debut = None
        for j, h in enumerate(row + ["__fin__"]):
            if h is None and debut is not None:
                continue
            if debut is not None and j - 1 > debut:
                style.append(("SPAN", (debut, r), (j - 1, r)))
            debut = j
        for j, h in enumerate(row):  # "^" = prolonge la cellule du dessus
            if h == "^":
                data[r][j] = ""
                r0 = r - 1
                style.append(("SPAN", (j, r0), (j, r)))
    if total:
        style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E4ECF5")))
    for i, coul in (surlignes or {}).items():
        style.append(("BACKGROUND", (0, nh + i), (-1, nh + i), colors.HexColor(coul)))
    t.setStyle(TableStyle(style))

    histoire = []
    st_titre = ParagraphStyle("ti", fontName=FB, fontSize=13, leading=16, alignment=1, textColor=BLEU,
                              spaceAfter=2)
    st_st = ParagraphStyle("st", fontName=FN, fontSize=9.5, leading=12, alignment=1, spaceAfter=4)
    histoire.append(Paragraph(titre, st_titre))
    if sous_titre:
        histoire.append(Paragraph(sous_titre, st_st))
    if infos:
        cols = 3 if paysage else 2
        ligne, grille = [], []
        for lab, val in infos:
            ligne += [Paragraph(f"<b>{lab}</b>", st_c), cell(val if val not in (None, "") else "—")]
            if len(ligne) == 2 * cols:
                grille.append(ligne)
                ligne = []
        if ligne:
            grille.append(ligne + [""] * (2 * cols - len(ligne)))
        lw = 28 * mm
        ti = Table(grille, colWidths=[lw, utile / cols - lw] * cols)
        ti.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, BLEU), ("BACKGROUND", (0, 0), (-1, -1), GRIS),
                                ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
        histoire += [ti, Spacer(1, 5)]
    histoire += list(avant or [])
    histoire.append(t)
    histoire += list(apres or [])
    if notes_bas:
        histoire.append(Spacer(1, 4))
        for n in notes_bas:
            histoire.append(Paragraph(n, ParagraphStyle("nb", fontName=FN, fontSize=7.5, leading=9.5)))
    # v1.15 : document signé = document vérifiable (code + QR, page /verifier)
    if code is None and (signatures or verif):
        code = code_tableau(titre, sous_titre, infos, lignes, total, verif)
    if signatures:
        histoire.append(Spacer(1, 6))
        bloc = [_BlocSignatures(signatures, utile, code=code if len(signatures) <= 2 else None)]
        if code and len(signatures) > 2:
            bloc.append(_BlocQR(code, utile))
        histoire.append(KeepTogether(bloc))
    elif code and qr_bloc:
        histoire += [Spacer(1, 6), _BlocQR(code, utile)]

    haut_entete = [0]

    def deco(c, doc):
        y = _entete_primaire(c, W, Hh, marge, infos_haut, cycle)
        haut_entete[0] = Hh - y
        c.setFont("Helvetica", 6.5)
        c.setFillColor(colors.grey)
        c.drawString(marge, 7 * mm, f"SCOLARIS · {config.ECOLE.get('nom', '')} · {config.ANNEE_ACTIVE}")
        c.drawRightString(W - marge, 7 * mm, f"Page {doc.page} · imprimé le {date.today().strftime('%d/%m/%Y')}")
        if code:
            c.drawCentredString(W / 2, 7 * mm, f"Document vérifiable · code {code}")
        c.setFillColor(colors.black)

    doc = SimpleDocTemplate(buf, pagesize=taille_page, leftMargin=marge, rightMargin=marge,
                            topMargin=marge + 30 * mm, bottomMargin=13 * mm, title=titre, author="SCOLARIS")
    doc.build(histoire, onFirstPage=deco, onLaterPages=deco, canvasmaker=GCanvasPeda if pedagogique else GCanvas)
    return buf.getvalue()


from reportlab.platypus.flowables import Flowable as _Flowable  # noqa: E402


class _BlocQR(_Flowable):
    """QR de vérification + légende (code, adresse), sous les signatures."""

    def __init__(self, code, largeur, taille=20 * mm):
        super().__init__()
        self.code, self.largeur, self.taille = code, largeur, taille
        self.height = taille + 2

    def wrap(self, *_):
        return self.largeur, self.height

    def draw(self):
        _qr(self.canv, self.code, 0, 1, taille=self.taille)


class _BlocSignatures(_Flowable):
    """Signatures côte à côte : (titre, nom, image, cachet)."""

    def __init__(self, signatures, largeur, code=None):
        super().__init__()
        self.sigs = signatures
        self.largeur = largeur
        self.code = code   # v1.15 : QR de vérification entre les signatures (1 ou 2 signataires)
        self.height = 38 * mm

    def wrap(self, *_):
        return self.largeur, self.height

    def draw(self):
        c = self.canv
        n = len(self.sigs)
        if self.code:
            t = 19 * mm
            x0 = (self.largeur / 2 - t / 2) if n == 2 else 0
            _qr(c, self.code, x0, 6 * mm, taille=t, legende=False)
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.black)
            xc = x0 + t / 2
            c.drawCentredString(xc, 3.6 * mm, f"Document vérifiable · code {self.code}")
            c.drawCentredString(xc, 1 * mm, texte_verif(self.code)[:70])
        for i, s in enumerate(self.sigs):
            titre, nom, image, avec_cachet = (list(s) + [None, None, False])[:4]
            x = self.largeur * (i + 0.5) / n
            y = self.height - 8
            c.setFont("Helvetica-Bold", 8.5)
            c.drawCentredString(x, y, titre or "")
            if avec_cachet:
                cachet_ecole(c, x - 9 * mm, y - 15.5 * mm, 11 * mm)
            if image is not None:
                c.drawImage(image, x - 22 * mm, y - 24 * mm, 44 * mm, 17 * mm, preserveAspectRatio=True, mask="auto")
            if nom and avec_cachet and config.ECOLE.get("_griffe"):
                griffe_ecole(c, x + 4 * mm, y - 29.5 * mm, 34 * mm)
            elif nom:
                c.setFont("Helvetica", 8.5)
                c.drawCentredString(x, y - 30.5 * mm, nom)


def paragraphe(texte, taille=8.5, gras=False, align=0, espace=3, police=None):
    if police == "serif":
        ps = police_serif()
        fn = ps["gras"] if gras else ps["normal"]
    else:
        fn = "Helvetica-Bold" if gras else "Helvetica"
    return Paragraph(texte, ParagraphStyle("p", fontName=fn, fontSize=taille,
                                           leading=taille * 1.3, alignment=align, spaceBefore=espace, spaceAfter=espace))


def mini_tableau(data, largeurs=None, taille=7.5, entete=True):
    """Petit tableau (flowable) pour les rubriques de statistiques."""
    st = ParagraphStyle("m", fontName="Helvetica", fontSize=taille, leading=taille + 1.5)
    sth = ParagraphStyle("mh", parent=st, fontName="Helvetica-Bold")
    rows = [[Paragraph("" if v is None else str(v), sth if (entete and i == 0) else st) for v in r] for i, r in enumerate(data)]
    t = Table(rows, colWidths=largeurs)
    s = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
         ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
    if entete:
        s.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E4ECF5")))
    t.setStyle(TableStyle(s))
    return t


def pour_cycle(cycle):
    """document_tableau avec l'en-tête du bon ministère (primaire/maternelle : MEMP ; secondaire : MESTFP)."""
    import functools
    return functools.partial(document_tableau, cycle=cycle)
