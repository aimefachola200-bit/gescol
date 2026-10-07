# -*- coding: utf-8 -*-
"""Examens (CEP) : fiche d'inscription au CEP, carte scolaire du candidat, examen blanc du CEP.

1. Fiches d'inscription au CEP (/cep)
   * liste des élèves de CM2 (classes autorisées) avec l'état de leur fiche ;
   * formulaire des champs propres à l'examen (table ``cep_fiches``), prérempli depuis l'inscription de l'élève
     et la fiche de l'école ; paramètres communs à la classe (session, centre, DDEMP…) ;
   * PDF individuel ou groupé conforme au modèle Word officiel de la DDEMP (photo, cachet, signatures) ;
   * export Excel de la liste des candidats.
2. Carte scolaire du candidat (/carte) : éditeur (aperçu recto/verso en direct), PDF au format carte bancaire
   (85,6 × 54 mm, recto + verso) et planche A4 (10 cartes par page) pour toute une classe. QR code de vérification.
   « Supprimer la carte » (POST /carte/<eid>/supprimer) efface les corrections propres à la carte, les documents de
   vérification de type carte et, sur demande, la photo — sans toucher à l'inscription de l'élève.
3. Examen blanc du CEP (/cep-blanc) : sessions de centre (tables ``cep_blanc_sessions`` / ``cep_blanc_candidats``),
   import Excel ou depuis les CM2 de l'école, saisie des notes, maîtrise et rang, Excel, PDF, relevés de notes.
   Règle du primaire : MAÎTRISE = au moins ``seuil`` matières à 10/20 (2/3 des matières par défaut) ; la moyenne
   ne sert qu'au rang.
"""
import io
import json
import os
import re
from datetime import date, datetime

from flask import Response, abort, flash, g, jsonify, redirect, render_template, request, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from calcul import appreciation_note, classer, seuil_deux_tiers

# ---------------------------------------------------------------- constantes
OPTIONS = ["CEP + entrée en 6è", "CEP seul"]
LIENS = ["Père", "Mère", "Tuteur", "Tutrice", "Oncle", "Tante", "Grand-père", "Grand-mère", "Frère", "Sœur"]
# couleurs du modèle Word de la fiche CEP
VERT_F = colors.HexColor("#194730")
OR_F = colors.HexColor("#A3780D")
OR_CLAIR = colors.HexColor("#C9962B")
BORD = colors.HexColor("#BAC4BA")
TEXTE = colors.HexColor("#1C1A14")
GRIS_T = colors.HexColor("#6B6553")
FOND_AGENT = colors.HexColor("#FAF5ED")
# couleurs du drapeau du Bénin
DRAP_VERT = colors.HexColor("#008751")
DRAP_JAUNE = colors.HexColor("#FCD116")
DRAP_ROUGE = colors.HexColor("#E8112D")
NOTES_IMPORTANT = [
    "Les Directeurs d'écoles doivent remplir les fiches d'inscription conformément aux informations telles "
    "qu'inscrites sur les actes de naissance. Ils doivent collationner les différentes listes envoyées par la DDEMP "
    "afin que la liste d'inscription porte la bonne graphie des noms et prénoms, date et lieu de naissance, sexe et "
    "école de provenance des candidats.",
    "Les Directeurs doivent s'assurer que sur les listes d'inscription, le nom de leur école est exclusivement porté "
    "devant chacun de leurs candidats afin de garantir la fiabilité des statistiques des résultats par école.",
    "Les Directeurs doivent associer les parents d'élèves aux choix des établissements d'accueil de l'enseignement "
    "secondaire en cas de succès.",
]
RE_EDUCMASTER = re.compile(r"^[A-Za-z0-9./ -]{0,30}$")
MAX_MATIERES = 15


# ---------------------------------------------------------------- petits outils
def txt(v, n=120):
    """Texte nettoyé et tronqué (champ de formulaire)."""
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def lire_date(s):
    try:
        return datetime.strptime(str(s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def date_fr(iso):
    d = lire_date(iso)
    return d.strftime("%d/%m/%Y") if d else ""


def titre_directeur(titre, majuscule=True):
    """« Directrice » -> « LA DIRECTRICE » ; sinon « LE DIRECTEUR »."""
    t = "La Directrice" if (titre or "").lower().startswith("directrice") else "Le Directeur"
    return t.upper() if majuscule else t


def num(v):
    """Note à la française : 12.5 -> « 12,5 »."""
    if v is None:
        return ""
    return (f"{v:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


def cle_tri_table(v):
    """Tri naturel des numéros de table (« 2 » avant « 10 »)."""
    s = str(v or "").strip()
    if not s:
        return (1, [])  # sans numéro : en fin de liste
    return (0, [(0, int(x), "") if x.isdigit() else (1, 0, x.lower()) for x in re.split(r"(\d+)", s) if x])


def image_reader(src):
    """ImageReader depuis un chemin de fichier ou une data URL ; None si impossible."""
    if not src:
        return None
    try:
        if str(src).startswith("data:image/"):
            import base64
            return ImageReader(io.BytesIO(base64.b64decode(str(src).split(",", 1)[1])))
        return ImageReader(src)
    except Exception:  # noqa: BLE001
        return None


def ajuster(c, texte, police, taille, largeur, mini=5):
    """Taille de police réduite pour que le texte tienne dans la largeur."""
    while taille > mini and c.stringWidth(texte, police, taille) > largeur:
        taille -= 0.25
    return taille


def texte_ajuste(c, x, y, texte, police, taille, largeur, align="g"):
    texte = str(texte or "")
    t = ajuster(c, texte, police, taille, largeur)
    c.setFont(police, t)
    if c.stringWidth(texte, police, t) > largeur:  # encore trop long : on coupe
        while texte and c.stringWidth(texte + "…", police, t) > largeur:
            texte = texte[:-1]
        texte += "…"
    if align == "c":
        c.drawCentredString(x, y, texte)
    elif align == "d":
        c.drawRightString(x, y, texte)
    else:
        c.drawString(x, y, texte)


# ---------------------------------------------------------------- dessins communs (emblème, drapeau)
def dessiner_embleme(c, cx, cy, r):
    """Emblème GÉNÉRIQUE de l'éducation (cercle, livre ouvert, étoile, ruban tricolore) — ce n'est pas une
    reproduction des armoiries officielles."""
    c.saveState()
    c.setLineWidth(max(0.4, r * 0.07))
    c.setStrokeColor(DRAP_VERT)
    c.setFillColor(colors.white)
    c.circle(cx, cy, r, stroke=1, fill=1)
    c.setLineWidth(max(0.25, r * 0.025))
    c.setStrokeColor(OR_CLAIR)
    c.circle(cx, cy, r * 0.84, stroke=1, fill=0)
    # étoile dorée
    import math
    p = c.beginPath()
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5
        rr = r * (0.2 if i % 2 == 0 else 0.085)
        x, y = cx + rr * math.cos(a), cy + r * 0.38 + rr * math.sin(a)
        (p.moveTo if i == 0 else p.lineTo)(x, y)
    p.close()
    c.setFillColor(OR_CLAIR)
    c.drawPath(p, stroke=0, fill=1)
    # livre ouvert
    c.setFillColor(colors.white)
    c.setStrokeColor(VERT_F)
    c.setLineWidth(max(0.3, r * 0.05))
    for s in (-1, 1):
        p = c.beginPath()
        p.moveTo(cx, cy - r * 0.28)
        p.lineTo(cx + s * r * 0.55, cy - r * 0.18)
        p.lineTo(cx + s * r * 0.55, cy + r * 0.14)
        p.lineTo(cx, cy + r * 0.05)
        p.close()
        c.drawPath(p, stroke=1, fill=1)
    c.line(cx, cy - r * 0.28, cx, cy + r * 0.05)
    # ruban tricolore
    bw = r * 0.95
    y0 = cy - r * 0.58
    for i, col in enumerate((DRAP_VERT, DRAP_JAUNE, DRAP_ROUGE)):
        c.setFillColor(col)
        c.rect(cx - bw / 2 + i * bw / 3, y0, bw / 3, r * 0.16, stroke=0, fill=1)
    c.restoreState()


def dessiner_drapeau(c, x, y, w, h):
    """Drapeau du Bénin : bande verte verticale à gauche, jaune (haut) et rouge (bas) à droite."""
    c.saveState()
    c.setFillColor(DRAP_VERT)
    c.rect(x, y, w * 0.4, h, stroke=0, fill=1)
    c.setFillColor(DRAP_JAUNE)
    c.rect(x + w * 0.4, y + h / 2, w * 0.6, h / 2, stroke=0, fill=1)
    c.setFillColor(DRAP_ROUGE)
    c.rect(x + w * 0.4, y, w * 0.6, h / 2, stroke=0, fill=1)
    c.setStrokeColor(colors.HexColor("#98A2B3"))
    c.setLineWidth(0.2)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.restoreState()


def bande_tricolore(c, x, y, w, h):
    for i, col in enumerate((DRAP_VERT, DRAP_JAUNE, DRAP_ROUGE)):
        c.setFillColor(col)
        c.rect(x + i * w / 3, y, w / 3, h, stroke=0, fill=1)


# ================================================================ 1. FICHE D'INSCRIPTION AU CEP (PDF)
def _fiche_page(c, d, pdfs):
    """Dessine une fiche d'inscription (page A4) fidèle au modèle Word. d : dict de valeurs (voir donnees_fiche)."""
    W, Hp = A4

    def T(y):  # ordonnée « depuis le haut » (le modèle est mesuré en points depuis le haut)
        return Hp - y

    def lab(x, y, texte, taille=7.6, coul=VERT_F, police="Times-Bold"):
        c.setFillColor(coul)
        c.setFont(police, taille)
        c.drawString(x, T(y), texte)
        return x + c.stringWidth(texte, police, taille)

    def champ(x1, x2, y, valeur="", taille=9, police="Times-Roman"):
        """Ligne pointillée de x1 à x2 + valeur écrite dessus."""
        c.setStrokeColor(BORD)
        c.setLineWidth(0.6)
        c.setDash(1, 1.2)
        c.line(x1, T(y) - 1.8, x2, T(y) - 1.8)
        c.setDash()
        if valeur:
            c.setFillColor(TEXTE)
            texte_ajuste(c, x1 + 2, T(y), valeur, police, taille, x2 - x1 - 4)

    def case(x, y, coche, libelle):
        c.setStrokeColor(TEXTE)
        c.setLineWidth(0.6)
        c.rect(x, T(y) - 1, 7, 7, stroke=1, fill=0)
        if coche:
            c.setFillColor(TEXTE)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(x + 3.5, T(y) + 0.2, "X")
        c.setFillColor(TEXTE)
        c.setFont("Times-Bold" if coche else "Times-Roman", 8.5)
        c.drawString(x + 10, T(y), libelle)

    def section(y1, y2, titre):
        """Bandeau vert (titre de section) + cadre."""
        c.setStrokeColor(BORD)
        c.setLineWidth(0.7)
        c.rect(28, T(y2), 523, y2 - y1 - 15, stroke=1, fill=0)
        c.setFillColor(VERT_F)
        c.roundRect(28, T(y1 + 15), 523, 15, 2.5, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Times-Bold", 8.3)
        c.drawString(39, T(y1 + 10.5), titre)

    # ---------------- en-tête ministère
    dessiner_embleme(c, 52, T(24), 17)
    c.setFillColor(TEXTE)
    c.setFont("Helvetica", 6.3)
    for i, t in enumerate(("MINISTÈRE", "DES ENSEIGNEMENTS", "MATERNEL ET PRIMAIRE")):
        c.drawString(84, T(9 + 8 * i), t)
    bande_tricolore(c, 84, T(33), 82, 1.6)
    c.setFillColor(TEXTE)
    c.drawString(84, T(42), "RÉPUBLIQUE DU BÉNIN")
    c.setFillColor(GRIS_T)
    c.setFont("Helvetica", 6.4)
    c.drawRightString(552, T(10), "01 BP 10 Porto-Novo")
    c.drawRightString(552, T(20), "Tél : +229 20 21 52 22  •  Fax : +229 20 21 52 22")
    c.drawRightString(552, T(29), "E-mail : mempmatprim@gmail.com")
    c.setStrokeColor(OR_CLAIR)
    c.setLineWidth(1.4)
    c.line(27, T(55), 552, T(55))
    # ---------------- direction départementale (gauche) + cadre titre (droite)
    c.setFillColor(TEXTE)
    c.setFont("Times-Bold", 8.3)
    c.drawCentredString(157, T(80), "Direction Départementale des Enseignements")
    texte_ajuste(c, 157, T(91), f"Maternel et Primaire : {d['ddemp']}", "Times-Bold", 8.3, 250, "c")
    c.setFont("Times-Roman", 8.3)
    c.drawCentredString(157, T(107), "Service des Examens et Concours")
    c.setFillColor(VERT_F)
    c.roundRect(287, T(121), 264, 54, 5, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Times-Bold", 11.5)
    c.drawCentredString(419, T(84), "FICHE D'INSCRIPTION À L'EXAMEN DU")
    c.drawCentredString(419, T(97), "CERTIFICAT D'ÉTUDES PRIMAIRES (CEP)")
    c.setFillColor(OR_CLAIR)
    c.setFont("Times-Roman", 6.8)
    opt = "OPTION : CEP + entrée en 6è"
    c.drawCentredString(419, T(108), opt)
    if d["option"] == "CEP seul":  # « rayer la mention inutile »
        w = c.stringWidth(opt, "Times-Roman", 6.8)
        x_plus = 419 - w / 2 + c.stringWidth("OPTION : CEP ", "Times-Roman", 6.8)
        c.setStrokeColor(colors.white)
        c.setLineWidth(0.8)
        c.line(x_plus, T(105.8), 419 + w / 2, T(105.8))
    c.setFillColor(colors.HexColor("#E3E8E3"))
    c.setFont("Times-Italic", 5)
    c.drawCentredString(419, T(116), "(Rayer la mention inutile)")
    # ---------------- session / centre
    lab(178, 139, "SESSION DE :", 8.3, TEXTE)
    champ(244, 363, 139, d["session"], 8.5, "Times-Bold")
    lab(178, 153, "CENTRE DE :", 8.3, TEXTE)
    champ(244, 385, 153, d["centre"], 8.5, "Times-Bold")

    # ---------------- école de provenance
    section(168, 286, "ÉCOLE DE PROVENANCE")
    x = lab(36, 201, "COMMUNE DE :")
    champ(x + 4, 270, 201, d["commune"])
    x = lab(284, 201, "CIRCONSCRIPTION SCOLAIRE DE :")
    champ(x + 4, 543, 201, d["cs"])
    x = lab(36, 219, "NOM DE L'ÉCOLE :")
    champ(x + 4, 543, 219, d["ecole"])
    lab(36, 237, "STATUT DE L'ÉCOLE :")
    statut = (d["statut"] or "").lower()
    case(134, 237, statut.startswith("pub"), "Publique")
    case(195, 237, statut.startswith("priv"), "Privée")
    x = lab(36, 255, "NOM ET PRÉNOM DU DIRECTEUR OU DE LA DIRECTRICE :")
    champ(x + 4, 543, 255, d["directeur"])
    x = lab(36, 273, "CONTACT TÉLÉPHONIQUE DU DIRECTEUR OU DE LA DIRECTRICE :")
    champ(x + 4, 543, 273, d["directeur_tel"])

    # ---------------- candidat
    section(293, 592, "CANDIDAT (E)")
    c.setStrokeColor(VERT_F)
    c.setLineWidth(0.9)
    c.setFillColor(colors.HexColor("#EDF5ED"))
    c.roundRect(468, T(403), 76, 85, 4, stroke=1, fill=1)
    photo = image_reader(d.get("photo"))
    if photo:
        c.drawImage(photo, 470, T(401), 72, 81, preserveAspectRatio=True, anchor="c", mask="auto")
    c.setFillColor(GRIS_T)
    c.setFont("Times-Italic", 5.2)
    c.drawCentredString(506, T(411), "Photo du candidat")
    x = lab(36, 328, "NOM :")
    champ(x + 4, 457, 328, (d["nom"] or "").upper(), 9.5, "Times-Bold")
    lab(38, 338.5, "(À écrire en lettres capitales)", 5, GRIS_T, "Times-Italic")
    x = lab(36, 350, "PRÉNOMS :")
    champ(x + 4, 457, 350, d["prenoms"], 9.5)
    lab(38, 359.5, "(Écrire tous les prénoms sans abréviation suivant l'ordre et l'orthographe de la pièce d'état civil)",
        5, GRIS_T, "Times-Italic")
    x = lab(36, 371, "SEXE :")
    champ(x + 4, 197, 371, d["sexe"])
    x = lab(210, 371, "DATE ET LIEU DE NAISSANCE :")
    champ(x + 4, 457, 371, d["naissance"])
    x = lab(36, 390, "NUMÉRO EDUCMASTER :")
    champ(x + 4, 457, 390, d["educmaster"])
    x = lab(36, 408, "ÉTABLISSEMENTS CHOISIS")
    lab(x + 8, 408, "(trois établissements par ordre de préférence, sans abréviation)", 5.4, GRIS_T, "Times-Italic")
    for i in range(3):
        y = 422 + 15.5 * i
        lab(36, y, f"{i + 1} -", 7.6, TEXTE)
        champ(56, 457, y, d["etab"][i])
    x = lab(36, 475, "RÉSIDENCE DES PARENTS :")
    champ(x + 4, 543, 475, d["residence"])
    lab(36, 493, "DISPENSE D'ÂGE :")
    case(118, 493, d["dispense_age"], "Oui")
    case(157, 493, not d["dispense_age"], "Non")
    lab(215, 493, "DISPENSE DE SPORT :")
    case(312, 493, d["dispense_sport"], "Oui")
    case(351, 493, not d["dispense_sport"], "Non")
    lab(36, 509, "Je certifie exacts les renseignements ci-dessus.", 7.8, TEXTE, "Times-Italic")
    lab(154, 525, "Fait à", 7.8, TEXTE, "Times-Roman")
    champ(185, 298, 525, d["fait_a"])
    lab(311, 525, "le", 7.8, TEXTE, "Times-Roman")
    champ(325, 430, 525, d["fait_le"])
    x = lab(36, 542, "NOM, PRÉNOM ET SIGNATURE DU PARENT :")
    champ(x + 4, 543, 542, d["parent_nom"])
    x = lab(36, 561, "CONTACT TÉLÉPHONIQUE DU PARENT :")
    champ(x + 4, 543, 561, d["parent_contact"])
    lab(38, 571.5, "(Préciser le degré de parenté)", 5, GRIS_T, "Times-Italic")
    x = lab(36, 582, "SIGNATURE DU (DE LA) CANDIDAT (E) :")
    champ(x + 4, 543, 582, "")
    sig_c = d.get("sig_candidat")
    if sig_c is not None:
        c.drawImage(sig_c, x + 30, T(584), 70, 17, preserveAspectRatio=True, mask="auto")

    # ---------------- très important
    c.setFillColor(TEXTE)
    c.setFont("Times-Bold", 8.3)
    c.drawString(28, T(605), "TRÈS IMPORTANT :")
    c.setLineWidth(0.5)
    c.setStrokeColor(TEXTE)
    c.line(28, T(606.5), 28 + c.stringWidth("TRÈS IMPORTANT :", "Times-Bold", 8.3), T(606.5))
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    st = ParagraphStyle("imp", fontName="Times-Roman", fontSize=6.4, leading=7.3, textColor=TEXTE, leftIndent=8,
                        firstLineIndent=-8)
    y = 610
    for i, n in enumerate(NOTES_IMPORTANT, 1):
        p = Paragraph(f"{i}. {n}", st)
        _, h = p.wrap(525, 100)
        p.drawOn(c, 28, T(y) - h)
        y += h + 0.5
    # ---------------- certifié à … le
    y_cert = max(668, y + 10)
    lab(375, y_cert, "Certifié à", 8, TEXTE, "Times-Roman")
    champ(413, 470, y_cert, d["certifie_a"], 8)
    lab(470, y_cert, ", le", 8, TEXTE, "Times-Roman")
    champ(486, 551, y_cert, d["certifie_le"], 8)
    # ---------------- agent de la DDEMP (laissé vide : rempli par la DDEMP)
    c.setFillColor(FOND_AGENT)
    c.setStrokeColor(colors.HexColor("#DED6BF"))
    c.setLineWidth(0.7)
    c.rect(28, T(769), 280, 60, stroke=1, fill=1)
    c.setFillColor(OR_F)
    c.roundRect(28, T(710), 280, 16, 3, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Times-Bold", 8.3)
    c.drawString(39, T(705), "AGENT DE LA DDEMP")
    for i, t in enumerate(("DOSSIER ÉTUDIÉ PAR :", "CODE :", "COLLATIONNÉ PAR :")):
        yy = 726 + 18 * i
        x = lab(36, yy, t, 7)
        champ(x + 4, 300, yy)
    # ---------------- le directeur
    c.setFillColor(TEXTE)
    c.setFont("Times-Bold", 8.3)
    c.drawCentredString(358, T(714), d["titre_directeur"])
    c.setFillColor(GRIS_T)
    c.setFont("Times-Italic", 5.5)
    c.drawCentredString(358, T(735), "(Nom, prénom, signature et")
    c.drawCentredString(358, T(743), "cachet du Directeur)")
    pdfs.cachet_ecole(c, 440, T(728), 25)
    if d.get("sig_directeur") is not None:
        c.drawImage(d["sig_directeur"], 418, T(748), 110, 40, preserveAspectRatio=True, mask="auto")
    c.setStrokeColor(BORD)
    c.setLineWidth(0.6)
    c.line(397, T(750), 551, T(750))
    c.setFillColor(TEXTE)
    texte_ajuste(c, 474, T(760), d["directeur_nom"], "Times-Bold", 8.3, 150, "c")


def pdf_fiches(liste, pdfs, titre="Fiches CEP"):
    """liste de dicts (donnees_fiche) -> bytes PDF (une page par candidat)."""
    buf = io.BytesIO()
    c = pdfs.GCanvas(buf, pagesize=A4)
    c.setTitle(titre)
    c.setAuthor("GESCOL")
    for d in liste:
        _fiche_page(c, d, pdfs)
        c.showPage()
    c.save()
    return buf.getvalue()


# ================================================================ 2. CARTE SCOLAIRE DU CANDIDAT (PDF)
CW, CH = 85.6 * mm, 54 * mm


def _bordure(c, x, y):
    """Bordure aux couleurs du drapeau : vert à gauche, jaune au milieu, rouge à droite."""
    e = 1.3 * mm
    c.saveState()
    p = c.beginPath()
    p.roundRect(x, y, CW, CH, 2.5 * mm)
    c.clipPath(p, stroke=0, fill=0)
    for i, col in enumerate((DRAP_VERT, DRAP_JAUNE, DRAP_ROUGE)):
        c.setFillColor(col)
        c.rect(x + i * CW / 3, y, CW / 3 + 0.5, CH, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.roundRect(x + e, y + e, CW - 2 * e, CH - 2 * e, 1.6 * mm, stroke=0, fill=1)
    c.restoreState()


def carte_recto(c, x, y, k, pdfs):
    """Recto de la carte (coin inférieur gauche en x, y). k : dict (voir donnees_carte)."""
    import cachet as C
    _bordure(c, x, y)
    c.saveState()
    c.translate(x, y)
    # --- en-tête
    dessiner_embleme(c, 8 * mm, CH - 8.6 * mm, 4.6 * mm)
    dessiner_drapeau(c, CW - 14.2 * mm, CH - 11 * mm, 10.2 * mm, 6.8 * mm)
    c.setFillColor(colors.HexColor("#1C1A14"))
    c.setFont("Helvetica", 4.6)
    c.drawCentredString(CW / 2, CH - 4.4 * mm, "RÉPUBLIQUE DU BÉNIN")
    c.setFont("Helvetica-Bold", 4.9)
    c.drawCentredString(CW / 2, CH - 6.6 * mm, "MINISTÈRE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE")
    c.setFillColor(VERT_F)
    c.setFont("Helvetica-Bold", 7.6)
    c.drawCentredString(CW / 2, CH - 9.8 * mm, "CARTE SCOLAIRE DU CANDIDAT(E)")
    c.setFillColor(VERT_F)
    c.roundRect(CW / 2 - 15 * mm, CH - 14.1 * mm, 30 * mm, 3.2 * mm, 1.6 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 4.8)
    c.drawCentredString(CW / 2, CH - 13.1 * mm, f"ANNÉE SCOLAIRE  {k['annee']}")
    c.setStrokeColor(OR_CLAIR)
    c.setLineWidth(0.5)
    c.line(3 * mm, CH - 15.4 * mm, CW - 3 * mm, CH - 15.4 * mm)
    # --- photo
    px, py, pw, ph = 3.4 * mm, 14.6 * mm, 14.6 * mm, 18.6 * mm
    c.setStrokeColor(VERT_F)
    c.setLineWidth(0.6)
    c.setFillColor(colors.HexColor("#EDF1EE"))
    c.roundRect(px, py, pw, ph, 1 * mm, stroke=1, fill=1)
    photo = image_reader(k.get("photo"))
    if photo:
        c.drawImage(photo, px + 0.4 * mm, py + 0.4 * mm, pw - 0.8 * mm, ph - 0.8 * mm, preserveAspectRatio=True,
                    anchor="c", mask="auto")
    else:
        c.setFillColor(colors.HexColor("#98A2B3"))
        c.setFont("Helvetica", 4.5)
        c.drawCentredString(px + pw / 2, py + ph / 2, "Photo élève")
    # --- champs
    champs = [("N° DE TABLE", k["numero_table"]), ("MATRICULE", k["matricule_educmaster"]), ("NIP", k["nip"]),
              ("NOM", (k["nom"] or "").upper()), ("PRÉNOM(S)", k["prenoms"]), ("SEXE", k["sexe"]),
              ("DATE DE NAISSANCE", date_fr(k["date_naissance"]) or k["date_naissance"]),
              ("LIEU DE NAISSANCE", k["lieu_naissance"]), ("CENTRE D'EXAMEN", k["centre_examen"]),
              ("CLASSE", k["classe"])]
    yy = CH - 18 * mm
    for lib, val in champs:
        c.setFillColor(VERT_F)
        c.setFont("Helvetica-Bold", 3.9)
        c.drawString(20.2 * mm, yy, lib)
        c.drawString(35.2 * mm, yy, ":")
        c.setFillColor(colors.HexColor("#111827"))
        texte_ajuste(c, 36.3 * mm, yy, val or "", "Helvetica-Bold", 5, 21.8 * mm)
        c.setStrokeColor(colors.HexColor("#E4E7EC"))
        c.setLineWidth(0.2)
        c.line(20.2 * mm, yy - 0.7 * mm, 58.3 * mm, yy - 0.7 * mm)
        yy -= 2.28 * mm
    # --- informations administratives
    bx, by, bw, bh = 59.6 * mm, 12.6 * mm, 22.8 * mm, 24.6 * mm
    c.setStrokeColor(VERT_F)
    c.setLineWidth(0.5)
    c.setFillColor(colors.white)
    c.roundRect(bx, by, bw, bh, 1.2 * mm, stroke=1, fill=1)
    c.setFillColor(VERT_F)
    c.roundRect(bx + 0.8 * mm, by + bh - 4.6 * mm, bw - 1.6 * mm, 3.8 * mm, 0.8 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 3.5)
    c.drawCentredString(bx + bw / 2, by + bh - 2.5 * mm, "INFORMATIONS")
    c.drawCentredString(bx + bw / 2, by + bh - 3.9 * mm, "ADMINISTRATIVES")
    yy = by + bh - 7 * mm
    for lib, val in (("DDEMP", k["ddemp"]), ("CS", k["cs"]), ("ÉCOLE", k["ecole"]), ("CLASSE", k["classe"])):
        c.setFillColor(OR_F)
        c.setFont("Helvetica-Bold", 3.7)
        c.drawString(bx + 1.5 * mm, yy, lib)
        c.setFillColor(colors.HexColor("#111827"))
        texte_ajuste(c, bx + 1.5 * mm, yy - 1.9 * mm, ": " + (val or ""), "Helvetica-Bold", 4.4, bw - 2.5 * mm, )
        yy -= 4.4 * mm
    # --- pied : signature élève, QR, cachet, directeur
    c.setStrokeColor(colors.HexColor("#D0D5DD"))
    c.setLineWidth(0.3)
    c.line(3 * mm, 12.1 * mm, CW - 3 * mm, 12.1 * mm)
    c.setFillColor(colors.HexColor("#344054"))
    c.setFont("Helvetica-Bold", 3.8)
    c.drawCentredString(19 * mm, 10.6 * mm, "Signature de l'élève")
    if k.get("sig_eleve") is not None:
        c.drawImage(k["sig_eleve"], 12 * mm, 6.9 * mm, 14 * mm, 3.4 * mm, preserveAspectRatio=True, mask="auto")
    c.line(11.6 * mm, 6.8 * mm, 26.4 * mm, 6.8 * mm)
    if k.get("code"):  # QR assez grand pour être lu par un téléphone
        pdfs._qr(c, k["code"], 2.6 * mm, 1.8 * mm, taille=8.4 * mm, legende=False)
    c.setFont("Helvetica-Bold", 3.4)
    c.setFillColor(VERT_F)
    c.drawString(11.8 * mm, 4.4 * mm, "Carte sécurisée")
    if k.get("code"):
        c.setFont("Helvetica", 2.8)
        c.drawString(11.8 * mm, 3.1 * mm, f"Code : {k['code']}")
    C.dessiner(c, 44 * mm, 6.4 * mm, 5.2 * mm, k["cachet_sup"], k["cachet_inf"], k["cachet_centre"],
               k["cachet_couleur"])
    c.setFillColor(colors.HexColor("#344054"))
    c.setFont("Helvetica-Bold", 3.9)
    c.drawCentredString(69 * mm, 10.6 * mm, titre_directeur(k["directeur_titre"], False))
    if k.get("sig_dir") is not None:
        c.drawImage(k["sig_dir"], 60 * mm, 6.1 * mm, 18 * mm, 4 * mm, preserveAspectRatio=True, mask="auto")
    c.line(59 * mm, 6 * mm, 79 * mm, 6 * mm)
    c.setFillColor(colors.HexColor("#111827"))
    texte_ajuste(c, 69 * mm, 3.9 * mm, k["directeur_nom"], "Helvetica-Bold", 4.3, 24 * mm, "c")
    c.restoreState()


def carte_verso(c, x, y, k, pdfs):
    """Verso : données et logo de l'école, consignes, contact d'urgence."""
    _bordure(c, x, y)
    c.saveState()
    c.translate(x, y)
    c.setFillColor(VERT_F)
    c.roundRect(2.6 * mm, CH - 13.4 * mm, CW - 5.2 * mm, 10.8 * mm, 1.2 * mm, stroke=0, fill=1)
    logo = k.get("logo")
    tx = 5 * mm
    if logo is not None:
        c.setFillColor(colors.white)
        c.circle(9.2 * mm, CH - 8 * mm, 4.6 * mm, stroke=0, fill=1)
        c.drawImage(logo, 5.4 * mm, CH - 11.8 * mm, 7.6 * mm, 7.6 * mm, preserveAspectRatio=True, mask="auto")
        tx = 15.4 * mm
    c.setFillColor(colors.white)
    texte_ajuste(c, tx, CH - 7 * mm, (k["ecole"] or "").upper(), "Helvetica-Bold", 7, CW - tx - 4 * mm)
    c.setFont("Helvetica", 4.3)
    sous = " · ".join(v for v in (k.get("ecole_statut"), k.get("ecole_ville")) if v)
    c.drawString(tx, CH - 10.6 * mm, sous[:80])
    lignes = [("Adresse", k.get("ecole_adresse")), ("Boîte postale", k.get("ecole_bp")),
              ("Téléphone", k.get("ecole_tel")), ("E-mail", k.get("ecole_email")),
              ("DDEMP / CS", " / ".join(v for v in (k["ddemp"], k["cs"]) if v)),
              ("Commune", k.get("commune")), ("Centre d'examen", k["centre_examen"])]
    yy = CH - 17.4 * mm
    for lib, val in lignes:
        if not val:
            continue
        c.setFillColor(VERT_F)
        c.setFont("Helvetica-Bold", 4.2)
        c.drawString(5 * mm, yy, lib)
        c.setFillColor(colors.HexColor("#111827"))
        texte_ajuste(c, 24 * mm, yy, ": " + str(val), "Helvetica", 4.8, CW - 30 * mm)
        yy -= 2.9 * mm
    # consignes
    c.setStrokeColor(OR_CLAIR)
    c.setLineWidth(0.4)
    c.line(4 * mm, 13.6 * mm, CW - 4 * mm, 13.6 * mm)
    c.setFillColor(colors.HexColor("#344054"))
    c.setFont("Helvetica-Oblique", 4.1)
    for i, t in enumerate(_decouper(k.get("verso_note") or "", c, "Helvetica-Oblique", 4.1, CW - 10 * mm)[:3]):
        c.drawString(5 * mm, 10.9 * mm - i * 1.9 * mm, t)
    if k.get("urgence"):
        c.setFont("Helvetica-Bold", 4.2)
        c.setFillColor(DRAP_ROUGE)
        texte_ajuste(c, 5 * mm, 4.5 * mm, "En cas d'urgence : " + k["urgence"], "Helvetica-Bold", 4.2, CW - 22 * mm)
    dessiner_drapeau(c, CW - 12.5 * mm, 3.4 * mm, 7.5 * mm, 5 * mm)
    c.restoreState()


def _decouper(texte, c, police, taille, largeur):
    """Coupe un texte en lignes tenant dans la largeur."""
    lignes, cour = [], ""
    for mot in str(texte).split():
        essai = (cour + " " + mot).strip()
        if c.stringWidth(essai, police, taille) <= largeur:
            cour = essai
        else:
            if cour:
                lignes.append(cour)
            cour = mot
    if cour:
        lignes.append(cour)
    return lignes


def pdf_carte(k, pdfs):
    """Carte au format 85,6 × 54 mm : page 1 = recto, page 2 = verso."""
    buf = io.BytesIO()
    c = pdfs.GCanvas(buf, pagesize=(CW, CH))
    c.setTitle(f"Carte scolaire du candidat – {k['nom']} {k['prenoms']}")
    carte_recto(c, 0, 0, k, pdfs)
    c.showPage()
    carte_verso(c, 0, 0, k, pdfs)
    c.showPage()
    c.save()
    return buf.getvalue()


def pdf_planche(cartes, pdfs, titre="Cartes scolaires"):
    """Planche A4 : 10 cartes par page (2 × 5), recto puis verso (colonnes inversées pour l'impression recto-verso)
    et traits de coupe."""
    buf = io.BytesIO()
    c = pdfs.GCanvas(buf, pagesize=A4)
    c.setTitle(titre)
    W, Hp = A4
    mx = (W - 2 * CW - 4 * mm) / 2
    my = (Hp - 5 * CH - 4 * 3 * mm) / 2 + 3 * mm

    def pos(i, inverse):
        col, lig = i % 2, i // 2
        if inverse:
            col = 1 - col
        return mx + col * (CW + 4 * mm), Hp - my - (lig + 1) * CH - lig * 3 * mm

    for debut in range(0, len(cartes), 10):
        lot = cartes[debut:debut + 10]
        for face, fn in (("RECTO", carte_recto), ("VERSO", carte_verso)):
            c.setFont("Helvetica", 7)
            c.setFillColor(colors.HexColor("#667085"))
            c.drawString(mx, Hp - 8 * mm, f"{titre} — {face} — page {debut // 10 + 1} "
                                          f"(imprimer en recto-verso, bord long)")
            for i, k in enumerate(lot):
                x, y = pos(i, face == "VERSO")
                fn(c, x, y, k, pdfs)
                c.setStrokeColor(colors.HexColor("#D0D5DD"))
                c.setLineWidth(0.25)
                for (x1, y1, x2, y2) in ((x - 3 * mm, y, x - 1 * mm, y), (x, y - 3 * mm, x, y - 1 * mm),
                                         (x + CW + 1 * mm, y + CH, x + CW + 3 * mm, y + CH),
                                         (x + CW, y + CH + 1 * mm, x + CW, y + CH + 3 * mm)):
                    c.line(x1, y1, x2, y2)
            c.showPage()
    c.save()
    return buf.getvalue()


# ================================================================ 3. EXAMEN BLANC : calculs
def session_dict(s):
    d = dict(s)
    try:
        d["mats"] = [str(m) for m in json.loads(s["matieres"] or "[]")][:MAX_MATIERES]
    except (TypeError, ValueError):
        d["mats"] = []
    n = len(d["mats"])
    d["seuil_eff"] = (max(1, min(int(d["seuil"]), n)) if d.get("seuil") else seuil_deux_tiers(n)) if n else 0
    return d


def resultats_blanc(sess, candidats):
    """Liste de dicts par candidat : notes (liste alignée sur les matières), total, moyenne, reussies, maitrise,
    decision, rang. Règle du primaire : MAÎTRISE = au moins seuil matières à 10/20."""
    mats = sess["mats"]
    lignes = []
    for cd in candidats:
        try:
            brut = json.loads(cd["notes"] or "{}")
        except (TypeError, ValueError):
            brut = {}
        notes = []
        for m in mats:
            v = brut.get(m)
            notes.append(float(v) if isinstance(v, (int, float)) and 0 <= v <= 20 else None)
        vals = [v for v in notes if v is not None]
        l = {"c": cd, "notes": notes, "nb": len(vals), "total": round(sum(vals), 2) if vals else None,
             "moyenne": round(sum(vals) / len(vals), 2) if vals else None,
             "reussies": sum(1 for v in vals if v >= 10), "seuil": sess["seuil_eff"]}
        if not vals:
            l["maitrise"], l["decision"] = None, "ABSENT"
        else:
            l["maitrise"] = l["reussies"] >= l["seuil"]
            l["decision"] = "MAÎTRISE" if l["maitrise"] else "NON MAÎTRISE"
        lignes.append(l)
    rangs = classer({l["c"]["id"]: l["moyenne"] for l in lignes})
    effectif = sum(1 for l in lignes if l["nb"])
    for l in lignes:
        l["rang"], l["ex_aequo"] = rangs[l["c"]["id"]]
        l["effectif"] = effectif
        l["rang_txt"] = ("—" if l["rang"] is None else
                         f"{l['rang']}{'er' if l['rang'] == 1 else 'e'}{' ex æquo' if l['ex_aequo'] else ''}")
    return lignes


def trier_blanc(lignes, tri):
    if tri == "merite":
        return sorted(lignes, key=lambda l: (l["rang"] is None, l["rang"] or 0, (l["c"]["nom"] or "").lower()))
    if tri == "ecole":
        return sorted(lignes, key=lambda l: ((l["c"]["ecole"] or "").lower(), (l["c"]["nom"] or "").lower(),
                                             (l["c"]["prenoms"] or "").lower()))
    if tri == "nom":
        return sorted(lignes, key=lambda l: ((l["c"]["nom"] or "").lower(), (l["c"]["prenoms"] or "").lower()))
    return sorted(lignes, key=lambda l: (cle_tri_table(l["c"]["numero_table"]), (l["c"]["nom"] or "").lower()))


def stats_blanc(lignes):
    """Présents, maîtrise, taux par sexe (G/F/T)."""
    def compte(f):
        d = {"G": sum(1 for l in lignes if l["c"]["sexe"] == "M" and f(l)),
             "F": sum(1 for l in lignes if l["c"]["sexe"] == "F" and f(l))}
        d["T"] = sum(1 for l in lignes if f(l))
        return d
    inscrits = compte(lambda l: True)
    presents = compte(lambda l: l["nb"] > 0)
    maitrise = compte(lambda l: l["maitrise"])
    taux = {k: (round(100 * maitrise[k] / presents[k], 2) if presents[k] else 0.0) for k in presents}
    return {"inscrits": inscrits, "presents": presents, "maitrise": maitrise, "taux": taux}


# ================================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.ajouter_colonne("cep_blanc_sessions", "chef_titre", "TEXT")
    import pdfs

    @app.context_processor
    def ctx_cep():
        return dict(cep_num=num, cep_date_fr=date_fr)

    # ------------------------------------------------------------ accès
    def classes_cm2():
        return [c for c in H.classes_autorisees() if c["niveau"] == "CM2"]

    def eleve_autorise(eid, cm2=False):
        """Élève inscrit d'une classe autorisée (et de CM2 si demandé)."""
        e = H.eleve_ou_404(eid)
        if not e["classe_id"]:
            abort(404)
        H.verifier_classe(e["classe_id"])
        cl = H.classe_ou_404(e["classe_id"])
        if cm2 and cl["niveau"] != "CM2":
            abort(404)
        return e, cl

    def eleves_de(cid):
        return q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (cid,))

    def ecole():
        return g.get("ecole") or {}

    def ecole_val(k):
        e = ecole()
        try:
            return (e[k] or "") if e else ""
        except (KeyError, IndexError):
            return ""

    def retour_sur(url, defaut):
        return url if url and url.startswith("/") and not url.startswith("//") else defaut

    # ============================================================ 1. FICHES D'INSCRIPTION AU CEP
    def cle_param(cid):
        return f"e{H.eco()}:cep:fiche:{cid}"

    def params_classe(cl):
        """Paramètres communs d'une classe : session, centre, DDEMP, commune, CS, fait à, certifié à."""
        an = H.config.ANNEE_ACTIVE
        p = {"session": f"JUIN {an[-4:]}", "centre": "", "ddemp": ecole_val("departement"),
             "commune": ecole_val("commune"), "cs": ecole_val("cs"),
             "fait_a": ecole_val("ville") or ecole_val("commune"), "certifie_a": ecole_val("ville") or ecole_val("commune"),
             "option": OPTIONS[0]}
        sauve = H.doc_lire(cle_param(cl["id"]), {}) or {}
        p.update({k: v for k, v in sauve.items() if k in p and v})
        return p

    def fiche_brute(eid):
        r = q("SELECT * FROM cep_fiches WHERE eleve_id=?", (eid,), un=True)
        return dict(r) if r else None

    def valeurs_fiche(e, cl):
        """Valeurs du formulaire : fiche enregistrée, sinon paramètres communs / inscription."""
        p = params_classe(cl)
        f = fiche_brute(e["id"]) or {}
        return {
            "session": f.get("session") or p["session"], "centre": f.get("centre") or e["centre_examen"] or p["centre"],
            "option": f.get("option") or p["option"], "etab1": f.get("etab1") or "", "etab2": f.get("etab2") or "",
            "etab3": f.get("etab3") or "", "residence_parents": f.get("residence_parents") or e["adresse"] or "",
            "dispense_age": bool(f.get("dispense_age")), "dispense_sport": bool(f.get("dispense_sport")),
            "parent_lien": f.get("parent_lien") or "", "fait_a": f.get("fait_a") or p["fait_a"],
            "fait_le": f.get("fait_le") or "", "maj": f.get("maj"), "existe": bool(f),
        }

    def manquants(e, v):
        m = []
        if not H.chemin_photo(e):
            m.append("photo")
        if not e["matricule_educmaster"]:
            m.append("n° EducMaster")
        if not e["date_naissance"] or not e["lieu_naissance"]:
            m.append("date/lieu de naissance")
        if not v["centre"]:
            m.append("centre")
        if not v["etab1"]:
            m.append("établissement choisi")
        if not v["residence_parents"]:
            m.append("résidence des parents")
        if not e["parent_telephone"]:
            m.append("contact du parent")
        return m

    def donnees_fiche(e, cl):
        """Toutes les valeurs de la fiche PDF."""
        v = valeurs_fiche(e, cl)
        p = params_classe(cl)
        naiss = date_fr(e["date_naissance"])
        if e["lieu_naissance"]:
            naiss = f"{naiss} à {e['lieu_naissance']}".strip()
        contact = e["parent_telephone"] or ""
        if v["parent_lien"]:
            contact = f"{contact} ({v['parent_lien']})".strip()
        fait_le = date_fr(v["fait_le"]) or date.today().strftime("%d/%m/%Y")
        dir_nom = ecole_val("directeur_nom") or H.config.ECOLE.get("directeur") or ""
        return {
            "ddemp": p["ddemp"], "session": v["session"], "centre": v["centre"], "option": v["option"],
            "commune": p["commune"], "cs": p["cs"], "ecole": ecole_val("nom") or H.config.ECOLE.get("nom", ""),
            "statut": ecole_val("statut"), "directeur": dir_nom,
            "directeur_tel": ecole_val("directeur_tel") or ecole_val("telephone"),
            "nom": e["nom"], "prenoms": e["prenoms"], "sexe": "Masculin" if e["sexe"] == "M" else "Féminin",
            "naissance": naiss, "educmaster": e["matricule_educmaster"] or "",
            "etab": [v["etab1"], v["etab2"], v["etab3"]], "residence": v["residence_parents"],
            "dispense_age": v["dispense_age"], "dispense_sport": v["dispense_sport"],
            "fait_a": v["fait_a"], "fait_le": fait_le, "parent_nom": e["parent_nom"] or "", "parent_contact": contact,
            "photo": H.chemin_photo(e), "sig_candidat": pdfs.image_data_url(H.signature(f"eleve:{e['id']}")),
            "sig_directeur": pdfs.signature_directeur(), "certifie_a": p["certifie_a"], "certifie_le": fait_le,
            "titre_directeur": titre_directeur(ecole_val("directeur_titre")), "directeur_nom": dir_nom,
        }

    @app.route("/cep")
    @H.connexion_requise("cep")
    def cep_accueil():
        cls = classes_cm2()
        cid = request.args.get("classe", type=int)
        if cid is None and cls:
            cid = cls[0]["id"]
        if cid is None:
            return render_template("cep_accueil.html", cls=cls, cl=None)
        if cid not in {c["id"] for c in cls}:
            H.verifier_classe(cid)
            abort(404)  # classe autorisée mais pas de CM2
        cl = H.classe_ou_404(cid)
        lignes = []
        for e in eleves_de(cid):
            v = valeurs_fiche(e, cl)
            m = manquants(e, v)
            lignes.append({"e": e, "v": v, "manque": m,
                           "etat": "complete" if v["existe"] and not m else ("incomplete" if v["existe"] else "vide")})
        nb = {k: sum(1 for l in lignes if l["etat"] == k) for k in ("complete", "incomplete", "vide")}
        return render_template("cep_accueil.html", cls=cls, cl=cl, lignes=lignes, nb=nb, p=params_classe(cl),
                               options=OPTIONS)

    @app.route("/cep/classe/<int:cid>/parametres", methods=["POST"])
    @H.connexion_requise("cep")
    def cep_fiche_parametres(cid):
        """Paramètres communs de la classe ; « appliquer » recopie session/centre/option/fait à dans chaque fiche."""
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        f = request.form
        p = {k: txt(f.get(k), 80) for k in ("session", "centre", "ddemp", "commune", "cs", "fait_a", "certifie_a")}
        p["option"] = f.get("option") if f.get("option") in OPTIONS else OPTIONS[0]
        H.doc_ecrire(cle_param(cid), p)
        n = 0
        if f.get("appliquer"):
            for e in eleves_de(cid):
                ex("""INSERT INTO cep_fiches (eleve_id, session, centre, option, fait_a, maj) VALUES (?,?,?,?,?,?)
                      ON CONFLICT(eleve_id) DO UPDATE SET session=excluded.session, centre=excluded.centre,
                      option=excluded.option, fait_a=excluded.fait_a, maj=excluded.maj""",
                   (e["id"], p["session"], p["centre"], p["option"], p["fait_a"], H.maintenant()))
                n += 1
        H.journal("cep_parametres", f"{cl['nom']} : {p['session']} / {p['centre']}")
        flash("Paramètres enregistrés." + (f" Appliqués à {n} fiche(s)." if n else ""), "success")
        return redirect(url_for("cep_accueil", classe=cid))

    @app.route("/cep/fiche/<int:eid>", methods=["GET", "POST"])
    @H.connexion_requise("cep")
    def cep_fiche(eid):
        e, cl = eleve_autorise(eid, cm2=True)
        if request.method == "POST":
            f = request.form
            err = []
            option = f.get("option") if f.get("option") in OPTIONS else OPTIONS[0]
            fait_le = ""
            if f.get("fait_le", "").strip():
                d = lire_date(f.get("fait_le"))
                if not d or not date(2000, 1, 1) <= d <= date(2100, 12, 31):
                    err.append("Date « Fait le » invalide.")
                else:
                    fait_le = d.isoformat()
            em = txt(f.get("matricule_educmaster"), 30)
            if not RE_EDUCMASTER.match(em):
                err.append("Numéro EducMaster invalide (lettres, chiffres, tirets ; 30 caractères au plus).")
            if err:
                for m in err:
                    flash(m, "danger")
                return render_template("cep_fiche.html", e=e, cl=cl, v=dict(valeurs_fiche(e, cl), **{
                    k: f.get(k, "") for k in ("session", "centre", "etab1", "etab2", "etab3", "residence_parents",
                                              "parent_lien", "fait_a", "fait_le")}), options=OPTIONS, liens=LIENS,
                    d=donnees_fiche(e, cl)), 400
            ex("""INSERT INTO cep_fiches (eleve_id, session, centre, option, etab1, etab2, etab3, residence_parents,
                  dispense_age, dispense_sport, parent_lien, fait_a, fait_le, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(eleve_id) DO UPDATE SET session=excluded.session, centre=excluded.centre,
                  option=excluded.option, etab1=excluded.etab1, etab2=excluded.etab2, etab3=excluded.etab3,
                  residence_parents=excluded.residence_parents, dispense_age=excluded.dispense_age,
                  dispense_sport=excluded.dispense_sport, parent_lien=excluded.parent_lien, fait_a=excluded.fait_a,
                  fait_le=excluded.fait_le, maj=excluded.maj""",
               (eid, txt(f.get("session"), 40), txt(f.get("centre"), 80), option, txt(f.get("etab1"), 120),
                txt(f.get("etab2"), 120), txt(f.get("etab3"), 120), txt(f.get("residence_parents"), 120),
                1 if f.get("dispense_age") == "1" else 0, 1 if f.get("dispense_sport") == "1" else 0,
                txt(f.get("parent_lien"), 30), txt(f.get("fait_a"), 60), fait_le, H.maintenant()))
            ex("UPDATE eleves SET matricule_educmaster=? WHERE id=?", (em or None, eid))
            if f.get("photo_data"):
                if not H.enregistrer_photo_data(eid, f.get("photo_data")):
                    flash("Photo non enregistrée (image invalide ou trop lourde).", "warning")
            H.journal("cep_fiche", f"{e['nom']} {e['prenoms']}")
            flash(f"Fiche CEP de {e['nom']} {e['prenoms']} enregistrée.", "success")
            if f.get("suite") == "pdf":
                return redirect(url_for("cep_fiche_pdf", eid=eid))
            if f.get("suite") == "suivant":
                ids = [x["id"] for x in eleves_de(cl["id"])]
                i = ids.index(eid) if eid in ids else -1
                if 0 <= i < len(ids) - 1:
                    return redirect(url_for("cep_fiche", eid=ids[i + 1]))
            return redirect(url_for("cep_accueil", classe=cl["id"]))
        eleves = eleves_de(cl["id"])
        ids = [x["id"] for x in eleves]
        i = ids.index(eid)
        return render_template("cep_fiche.html", e=e, cl=cl, v=valeurs_fiche(e, cl), options=OPTIONS, liens=LIENS,
                               d=donnees_fiche(e, cl), prec=ids[i - 1] if i > 0 else None,
                               suiv=ids[i + 1] if i < len(ids) - 1 else None, rang=i + 1, total=len(ids))

    @app.route("/cep/fiche/<int:eid>/pdf")
    @H.connexion_requise("cep")
    def cep_fiche_pdf(eid):
        e, cl = eleve_autorise(eid, cm2=True)
        pdf = pdf_fiches([donnees_fiche(e, cl)], pdfs, f"Fiche CEP – {e['nom']} {e['prenoms']}")
        H.journal("cep_fiche_pdf", f"{e['nom']} {e['prenoms']}")
        return H.pdf_reponse(pdf, f"fiche_cep_{e['nom']}_{e['prenoms']}.pdf".replace(" ", "_"))

    @app.route("/cep/classe/<int:cid>/fiches.pdf")
    @H.connexion_requise("cep")
    def cep_fiches_classe_pdf(cid):
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        if cl["niveau"] != "CM2":
            abort(404)
        ids = set(request.args.getlist("eleve", type=int))
        eleves = [e for e in eleves_de(cid) if not ids or e["id"] in ids]
        if not eleves:
            flash("Aucun élève à imprimer dans cette classe.", "warning")
            return redirect(url_for("cep_accueil", classe=cid))
        pdf = pdf_fiches([donnees_fiche(e, cl) for e in eleves], pdfs, f"Fiches CEP – {cl['nom']}")
        H.journal("cep_fiches_pdf", f"{cl['nom']} : {len(eleves)} fiche(s)")
        return H.pdf_reponse(pdf, f"fiches_cep_{cl['nom'].replace(' ', '_')}.pdf")

    @app.route("/cep/classe/<int:cid>/candidats.xlsx")
    @H.connexion_requise("cep")
    def cep_candidats_excel(cid):
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        if cl["niveau"] != "CM2":
            abort(404)
        p = params_classe(cl)
        lignes = []
        for i, e in enumerate(eleves_de(cid), 1):
            v = valeurs_fiche(e, cl)
            m = manquants(e, v)
            lignes.append([i, e["nom"], e["prenoms"], e["sexe"], date_fr(e["date_naissance"]), e["lieu_naissance"] or "",
                           e["matricule_educmaster"] or "", v["option"], v["etab1"], v["etab2"], v["etab3"],
                           v["residence_parents"], "Oui" if v["dispense_age"] else "Non",
                           "Oui" if v["dispense_sport"] else "Non", e["parent_nom"] or "", e["parent_telephone"] or "",
                           v["parent_lien"], v["centre"],
                           ("Complète" if v["existe"] and not m else "À compléter : " + ", ".join(m) if m else "Complète")])
        entetes = ["N°", "Nom", "Prénoms", "Sexe", "Date de naissance", "Lieu de naissance", "N° EducMaster", "Option",
                   "Établissement 1", "Établissement 2", "Établissement 3", "Résidence des parents", "Dispense d'âge",
                   "Dispense de sport", "Parent", "Contact du parent", "Lien de parenté", "Centre", "État de la fiche"]
        H.journal("cep_excel", cl["nom"])
        return H.xlsx.reponse_xlsx(f"candidats_cep_{cl['nom'].replace(' ', '_')}.xlsx", entetes, lignes,
                                   titre="Candidats CEP", titre_haut=[
                                       f"LISTE DES CANDIDATS AU CEP – SESSION {p['session']}",
                                       f"École : {ecole_val('nom')} – Classe : {cl['nom']} – DDEMP : {p['ddemp']} – "
                                       f"CS : {p['cs']} – Centre : {p['centre']}"])

    # ============================================================ 2. CARTE SCOLAIRE DU CANDIDAT
    CHAMPS_ELEVE = ("numero_table", "matricule_educmaster", "nip", "nom", "prenoms", "sexe", "date_naissance",
                    "lieu_naissance", "centre_examen", "classe")
    CHAMPS_COMMUNS = ("ddemp", "cs", "ecole", "annee", "directeur_titre", "directeur_nom", "cachet_couleur",
                      "cachet_sup", "cachet_inf", "cachet_centre", "verso_note")
    VERSO_DEFAUT = ("Cette carte est strictement personnelle. Elle doit être présentée à chaque épreuve de "
                    "l'examen. En cas de perte, la rapporter à l'école ou au centre d'examen.")

    def cle_carte_commun():
        return f"e{H.eco()}:carte:commun"

    def cle_carte_eleve(eid):
        return f"e{H.eco()}:carte:eleve:{eid}"

    def communs_defaut():
        nom = ecole_val("nom") or H.config.ECOLE.get("nom", "")
        return {"ddemp": ecole_val("departement"), "cs": ecole_val("cs"), "ecole": nom,
                "annee": H.config.ANNEE_ACTIVE, "directeur_titre": ecole_val("directeur_titre") or "Directeur",
                "directeur_nom": ecole_val("directeur_nom") or H.config.ECOLE.get("directeur") or "",
                "cachet_couleur": ecole_val("cachet_couleur") or "bleu",
                "cachet_sup": ecole_val("cachet_sup") or nom.upper()[:40],
                "cachet_inf": ecole_val("cachet_inf") or (ecole_val("ville") or ecole_val("commune")).upper(),
                "cachet_centre": ecole_val("cachet_centre") or "LA DIRECTION", "verso_note": VERSO_DEFAUT}

    def eleve_defaut(e, cl):
        return {"numero_table": e["numero_table"] or "", "matricule_educmaster": e["matricule_educmaster"] or "",
                "nip": e["nip"] or "", "nom": e["nom"] or "", "prenoms": e["prenoms"] or "", "sexe": e["sexe"] or "",
                "date_naissance": e["date_naissance"] or "", "lieu_naissance": e["lieu_naissance"] or "",
                "centre_examen": e["centre_examen"] or "", "classe": cl["nom"] if cl else ""}

    def valeurs_carte(e, cl):
        """(valeurs actuelles enregistrées, valeurs par défaut issues de l'inscription et de l'école)."""
        defaut = dict(communs_defaut(), **eleve_defaut(e, cl))
        v = dict(defaut)
        v.update({k: x for k, x in (H.doc_lire(cle_carte_commun(), {}) or {}).items() if k in CHAMPS_COMMUNS})
        v.update({k: x for k, x in (H.doc_lire(cle_carte_eleve(e["id"]), {}) or {}).items() if k in CHAMPS_ELEVE})
        return v, defaut

    def lire_form_carte(f):
        """Champs de l'éditeur, nettoyés. Retourne (valeurs, erreurs)."""
        v = {k: txt(f.get(k), 120) for k in CHAMPS_ELEVE + CHAMPS_COMMUNS}
        v["verso_note"] = txt(f.get("verso_note"), 300)
        err = []
        v["sexe"] = H.xlsx.sexe(v["sexe"]) if v["sexe"] else ""
        if v["date_naissance"]:
            d = lire_date(v["date_naissance"])
            if not d or not date(1990, 1, 1) <= d <= date.today():
                err.append("Date de naissance invalide.")
                v["date_naissance"] = ""
        if v["cachet_couleur"] not in ("bleu", "rouge"):
            v["cachet_couleur"] = "bleu"
        if v["directeur_titre"] not in ("Directeur", "Directrice"):
            v["directeur_titre"] = "Directeur"
        if not RE_EDUCMASTER.match(v["matricule_educmaster"]):
            err.append("Matricule EducMaster invalide.")
            v["matricule_educmaster"] = ""
        for k in ("numero_table", "nip"):
            v[k] = v[k][:30]
        return v, err

    def code_carte(e, annee):
        return H.enregistrer_document("carte_candidat", e["id"], f"Carte scolaire du candidat {annee}",
                                      cle=f"carte_cep|{e['id']}|{annee}")

    def donnees_carte(e, cl, v, photo=None, avec_code=True):
        """Dict complet pour le dessin (valeurs + images + école)."""
        k = dict(v)
        k["photo"] = photo or H.chemin_photo(e)
        k["sig_eleve"] = pdfs.image_data_url(H.signature(f"eleve:{e['id']}"))
        k["sig_dir"] = pdfs.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")) or pdfs.signature_directeur()
        k["logo"] = pdfs._ecole_img("logo.png")
        k.update(ecole_statut=ecole_val("statut"), ecole_ville=ecole_val("ville"), ecole_adresse=ecole_val("adresse"),
                 ecole_bp=ecole_val("bp"), ecole_tel=ecole_val("telephone"), ecole_email=ecole_val("email"),
                 commune=ecole_val("commune"))
        urg = f"{e['parent_nom'] or ''} {e['parent_telephone'] or ''}".strip()
        k["urgence"] = urg
        k["code"] = code_carte(e, v["annee"] or H.config.ANNEE_ACTIVE) if avec_code else ""
        return k

    @app.route("/carte")
    @H.connexion_requise("cep")
    def carte_editeur():
        cls = H.classes_autorisees()
        cid = request.args.get("classe", type=int)
        eid = request.args.get("eleve", type=int)
        e = cl = None
        if eid:
            e, cl = eleve_autorise(eid)
            cid = cl["id"]
        if cid is None:
            cm2 = [c for c in cls if c["niveau"] == "CM2"]
            cid = (cm2 or cls or [{"id": None}])[0]["id"]
        if cid is not None and not cl:
            H.verifier_classe(cid)
            cl = H.classe_ou_404(cid)
        eleves = eleves_de(cid) if cid else []
        if not e and eleves:
            e = eleves[0]
        if not e:
            return render_template("carte_editeur.html", cls=cls, cl=cl, e=None, eleves=eleves)
        v, defaut = valeurs_carte(e, cl)
        return render_template("carte_editeur.html", cls=cls, cl=cl, e=e, eleves=eleves, v=v,
                               defaut_json=json.dumps(defaut, ensure_ascii=False), code=code_carte(e, v["annee"]),
                               photo=bool(H.chemin_photo(e)))

    @app.route("/carte/<int:eid>/enregistrer", methods=["POST"])
    @H.connexion_requise("cep")
    def carte_enregistrer(eid):
        e, cl = eleve_autorise(eid)
        v, err = lire_form_carte(request.form)
        for m in err:
            flash(m, "warning")
        # champs propres à l'examen : dans la fiche de l'élève
        ex("UPDATE eleves SET numero_table=?, matricule_educmaster=?, nip=?, centre_examen=? WHERE id=?",
           (v["numero_table"] or None, v["matricule_educmaster"] or None, v["nip"] or None, v["centre_examen"] or None,
            eid))
        # nom, prénoms, date… : corrections propres à la carte (l'inscription n'est pas modifiée)
        base = eleve_defaut(H.eleve_ou_404(eid), cl)
        # (une valeur vide ou invalide n'écrase pas : la donnée de l'inscription reste affichée)
        H.doc_ecrire(cle_carte_eleve(eid), {k: v[k] for k in ("nom", "prenoms", "sexe", "date_naissance",
                                                               "lieu_naissance", "classe") if v[k] and v[k] != base[k]})
        H.doc_ecrire(cle_carte_commun(), {k: v[k] for k in CHAMPS_COMMUNS})
        if request.form.get("photo_data"):
            if not H.enregistrer_photo_data(eid, request.form.get("photo_data")):
                flash("Photo non enregistrée (image invalide ou trop lourde).", "warning")
        H.journal("carte_candidat", f"{e['nom']} {e['prenoms']}")
        flash(f"Carte de {v['nom']} {v['prenoms']} enregistrée.", "success")
        return redirect(url_for("carte_editeur", eleve=eid))

    @app.route("/carte/<int:eid>/donnees")
    @H.connexion_requise("cep")
    def carte_donnees(eid):
        """« Charger » : valeurs enregistrées (JSON)."""
        e, cl = eleve_autorise(eid)
        v, _ = valeurs_carte(e, cl)
        return jsonify({"ok": True, "valeurs": v})

    @app.route("/carte/<int:eid>/reinitialiser", methods=["POST"])
    @H.connexion_requise("cep")
    def carte_reinitialiser(eid):
        """Efface les corrections propres à la carte de l'élève (retour aux données de l'inscription)."""
        e, cl = eleve_autorise(eid)
        ex("DELETE FROM documents_modules WHERE cle=?", (cle_carte_eleve(eid),))
        H.journal("carte_reinitialisee", f"{e['nom']} {e['prenoms']}")
        flash("Carte réinitialisée : données de l'inscription rétablies.", "success")
        return redirect(url_for("carte_editeur", eleve=eid))

    @app.route("/carte/<int:eid>/supprimer", methods=["POST"])
    @H.connexion_requise("cep")
    def carte_supprimer(eid):
        """Supprime la carte enregistrée de l'élève (sans toucher à son inscription) : corrections propres à la carte,
        documents officiels de type carte (code de vérification : le QR code d'une carte déjà imprimée devient invalide)
        et, si demandé (case « photo »), la photo de l'élève."""
        e, cl = eleve_autorise(eid)
        db = H.get_db()
        db.execute("DELETE FROM documents_modules WHERE cle=?", (cle_carte_eleve(eid),))
        n_docs = db.execute("DELETE FROM documents WHERE eleve_id=? AND type IN ('carte_candidat', 'carte')", (eid,)).rowcount
        db.commit()
        photo = False
        if request.form.get("photo"):
            p = H.chemin_photo(e)
            if p:
                try:
                    os.remove(p)
                    photo = True
                except OSError:
                    pass
            ex("UPDATE eleves SET photo=NULL WHERE id=?", (eid,))
        H.journal("carte_supprimee", f"{e['nom']} {e['prenoms']} ({n_docs} document(s)" + (", photo" if photo else "") + ")")
        flash(f"Carte de {e['nom']} {e['prenoms']} supprimée" + (" avec sa photo" if photo else "")
              + ". L'élève reste inscrit ; un nouveau code de vérification sera attribué à la prochaine carte.", "success")
        return redirect(url_for("carte_editeur", classe=cl["id"]))

    @app.route("/carte/<int:eid>/pdf", methods=["GET", "POST"])
    @H.connexion_requise("cep")
    def carte_pdf(eid):
        """PDF de la carte (recto + verso). POST : valeurs du formulaire (même non enregistrées)."""
        e, cl = eleve_autorise(eid)
        v, _ = valeurs_carte(e, cl)
        photo = None
        if request.method == "POST":
            vf, _err = lire_form_carte(request.form)
            for k in ("nom", "prenoms", "sexe", "date_naissance", "lieu_naissance", "classe"):
                if not vf[k]:
                    vf[k] = v[k]  # champ vidé ou invalide : valeur enregistrée
            v = vf
            pd = request.form.get("photo_data", "")
            if pd.startswith("data:image/") and len(pd) < 3_000_000:
                photo = pd
        pdf = pdf_carte(donnees_carte(e, cl, v, photo), pdfs)
        H.journal("carte_pdf", f"{e['nom']} {e['prenoms']}")
        return H.pdf_reponse(pdf, f"carte_candidat_{e['nom']}_{e['prenoms']}.pdf".replace(" ", "_"))

    @app.route("/carte/classe/<int:cid>/planche.pdf")
    @H.connexion_requise("cep")
    def carte_planche(cid):
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        eleves = eleves_de(cid)
        if not eleves:
            flash("Aucun élève inscrit dans cette classe.", "warning")
            return redirect(url_for("carte_editeur", classe=cid))
        cartes = [donnees_carte(e, cl, valeurs_carte(e, cl)[0]) for e in eleves]
        pdf = pdf_planche(cartes, pdfs, f"Cartes scolaires – {cl['nom']}")
        H.journal("carte_planche", f"{cl['nom']} : {len(cartes)} carte(s)")
        return H.pdf_reponse(pdf, f"cartes_candidats_{cl['nom'].replace(' ', '_')}.pdf")

    @app.route("/carte/<int:eid>/qr.svg")
    @H.connexion_requise("cep")
    def carte_qr(eid):
        """QR code de vérification (aperçu de l'éditeur)."""
        e, cl = eleve_autorise(eid)
        v, _ = valeurs_carte(e, cl)
        from reportlab.graphics import renderSVG
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        w = QrCodeWidget(pdfs.url_verif(code_carte(e, v["annee"])))
        b = w.getBounds()
        t = 120
        d = Drawing(t, t, transform=[t / (b[2] - b[0]), 0, 0, t / (b[3] - b[1]), 0, 0])
        d.add(w)
        return Response(renderSVG.drawToString(d), mimetype="image/svg+xml", headers={"Cache-Control": "no-cache"})

    # ============================================================ 3. EXAMEN BLANC DU CEP
    def session_ou_404(sid):
        s = q("SELECT * FROM cep_blanc_sessions WHERE id=? AND ecole_id=?", (sid, H.eco()), un=True)
        if not s:
            abort(404)
        return session_dict(s)

    def candidats_de(sid):
        return q("SELECT * FROM cep_blanc_candidats WHERE session_id=?", (sid,))

    def matieres_defaut():
        rows = q("SELECT nom FROM matieres WHERE cycle='primaire' AND actif=1 AND mode_calcul='standard' ORDER BY ordre, nom")
        return [r["nom"] for r in rows][:MAX_MATIERES] or ["Français", "Mathématiques", "Éducation scientifique",
                                                           "Éducation sociale"]

    @app.route("/cep-blanc")
    @H.connexion_requise("cep")
    def cep_blanc_accueil():
        sessions = []
        for s in q("SELECT * FROM cep_blanc_sessions WHERE ecole_id=? ORDER BY annee DESC, numero DESC, id DESC",
                   (H.eco(),)):
            d = session_dict(s)
            d["nb"] = q("SELECT COUNT(*) n FROM cep_blanc_candidats WHERE session_id=?", (s["id"],), un=True)["n"]
            sessions.append(d)
        v = H.identification()
        return render_template("cep_blanc_accueil.html", sessions=sessions, v=v, matieres=matieres_defaut())

    @app.route("/cep-blanc/nouvelle", methods=["POST"])
    @H.connexion_requise("cep")
    def cep_blanc_nouvelle():
        v = H.identification()
        precedent = q("SELECT * FROM cep_blanc_sessions WHERE ecole_id=? ORDER BY id DESC LIMIT 1", (H.eco(),), un=True)
        numero = request.form.get("numero", type=int) or ((precedent["numero"] or 0) + 1 if precedent else 1)
        numero = max(1, min(numero, 99))
        # reprend le centre / chef centre de la session précédente, sinon la fiche de l'école
        base = dict(precedent) if precedent else {}
        mats = json.loads(base.get("matieres") or "null") if base else None
        sid = ex("""INSERT INTO cep_blanc_sessions (ecole_id, annee, departement, ddemp, cs, commune, centre, chef_centre,
                    chef_titre, numero, date_signature, matieres, seuil, cree_le) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (H.eco(), H.config.ANNEE_ACTIVE, base.get("departement") or v["departement"],
                  base.get("ddemp") or v["ddemp"], base.get("cs") or v["cs"], base.get("commune") or v["commune"],
                  base.get("centre") or v["ecole"], base.get("chef_centre") or "", base.get("chef_titre") or "Chef centre",
                  numero, date.today().isoformat(), json.dumps(mats or matieres_defaut(), ensure_ascii=False),
                  base.get("seuil"), H.maintenant()))
        H.journal("cep_blanc_session", f"N° {numero}")
        flash(f"Examen blanc CEP N° {numero} créé. Importez ou saisissez la liste des candidats.", "success")
        return redirect(url_for("cep_blanc_session", sid=sid))

    @app.route("/cep-blanc/<int:sid>")
    @H.connexion_requise("cep")
    def cep_blanc_session(sid):
        s = session_ou_404(sid)
        tri = request.args.get("tri", "table")
        lignes = trier_blanc(resultats_blanc(s, candidats_de(sid)), tri)
        autres = q("SELECT id, numero, annee, centre FROM cep_blanc_sessions WHERE ecole_id=? ORDER BY id DESC",
                   (H.eco(),))
        ecoles = sorted({l["c"]["ecole"] for l in lignes if l["c"]["ecole"]})
        return render_template("cep_blanc_session.html", s=s, lignes=lignes, tri=tri, st=stats_blanc(lignes),
                               autres=autres, ecoles=ecoles, cm2=classes_cm2(),
                               v=dict(H.identification(), departement=s["departement"] or "", ddemp=s["ddemp"] or "",
                                      cs=s["cs"] or "", commune=s["commune"] or "", annee=s["annee"] or "",
                                      chef_titre=s.get("chef_titre") or "Chef centre", chef_nom=s["chef_centre"] or ""))

    def lire_entete_session(f, s):
        """Lit l'en-tête (centre, matières, seuil) ; retourne (dict, erreurs)."""
        err = []
        mats = []
        for m in (f.get("matieres") or "").splitlines():
            m = txt(m, 60)
            if m and m.lower() not in [x.lower() for x in mats]:
                mats.append(m)
        if not mats:
            err.append("Indiquez au moins une matière (une par ligne).")
            mats = s["mats"]
        if len(mats) > MAX_MATIERES:
            err.append(f"{MAX_MATIERES} matières au maximum.")
            mats = mats[:MAX_MATIERES]
        seuil = f.get("seuil", "").strip()
        if seuil:
            if not seuil.isdigit() or not 1 <= int(seuil) <= len(mats):
                err.append(f"Seuil de maîtrise : nombre entier entre 1 et {len(mats)} (vide = 2/3 des matières).")
                seuil = s["seuil"]
            else:
                seuil = int(seuil)
        else:
            seuil = None
        ds = f.get("date_signature", "").strip()
        if ds and not lire_date(ds):
            err.append("Date de signature invalide.")
            ds = s["date_signature"]
        numero = f.get("numero", type=int) or s["numero"] or 1
        an = txt(f.get("annee"), 9)
        if not re.match(r"^\d{4}-\d{4}$", an):
            an = s["annee"] or H.config.ANNEE_ACTIVE
        d = {"departement": txt(f.get("departement"), 60), "ddemp": txt(f.get("ddemp"), 60), "cs": txt(f.get("cs"), 80),
             "annee": an, "commune": txt(f.get("commune"), 60), "centre": txt(f.get("centre"), 100),
             "chef_centre": txt(f.get("chef_nom"), 100),
             "chef_titre": f.get("chef_titre") if f.get("chef_titre") in ("Chef centre", "Cheffe centre") else "Chef centre",
             "numero": max(1, min(int(numero), 99)), "date_signature": lire_date(ds).isoformat() if ds else "",
             "matieres": mats, "seuil": seuil}
        return d, err

    def ecrire_entete_session(s, d):
        """Enregistre l'en-tête ; si des matières sont renommées (même nombre), les notes suivent la position."""
        anciennes = s["mats"]
        if anciennes != d["matieres"] and len(anciennes) == len(d["matieres"]):
            corresp = dict(zip(anciennes, d["matieres"]))
            for cd in candidats_de(s["id"]):
                try:
                    n = json.loads(cd["notes"] or "{}")
                except ValueError:
                    n = {}
                ex("UPDATE cep_blanc_candidats SET notes=? WHERE id=?",
                   (json.dumps({corresp.get(k, k): x for k, x in n.items()}, ensure_ascii=False), cd["id"]))
        ex("""UPDATE cep_blanc_sessions SET departement=?, ddemp=?, cs=?, annee=?, commune=?, centre=?, chef_centre=?,
              chef_titre=?, numero=?, date_signature=?, matieres=?, seuil=? WHERE id=?""",
           (d["departement"], d["ddemp"], d["cs"], d["annee"], d["commune"], d["centre"], d["chef_centre"],
            d["chef_titre"], d["numero"], d["date_signature"], json.dumps(d["matieres"], ensure_ascii=False),
            d["seuil"], s["id"]))

    @app.route("/cep-blanc/<int:sid>/sauvegarder", methods=["POST"])
    @H.connexion_requise("cep")
    def cep_blanc_sauvegarder(sid):
        """Enregistre l'en-tête, les candidats (ajouts, modifications, suppressions) et les notes du tableau."""
        s = session_ou_404(sid)
        f = request.form
        d, err = lire_entete_session(f, s)
        ecrire_entete_session(s, d)
        mats_form = s["mats"]  # le tableau affiché correspond aux matières AVANT la modification de l'en-tête
        corresp = dict(zip(s["mats"], d["matieres"])) if len(s["mats"]) == len(d["matieres"]) else {}
        existants = {c["id"]: c for c in candidats_de(sid)}
        suppr = {int(x) for x in f.getlist("suppr") if x.isdigit()}
        ids, tables, noms = f.getlist("cid"), f.getlist("table"), f.getlist("nom")
        prenoms, sexes, ecoles = f.getlist("prenoms"), f.getlist("sexe"), f.getlist("ecole")
        colonnes = [f.getlist(f"n{j}") for j in range(len(mats_form))]
        n_maj = n_new = 0
        mauvaises = []
        for i in range(len(noms)):
            def val(lst):
                return lst[i] if i < len(lst) else ""
            cid = int(val(ids)) if val(ids).isdigit() else None
            if cid and (cid not in existants or cid in suppr):
                continue
            nom = txt(val(noms), 80).upper()
            if not nom:
                continue
            ancien = {}
            if cid:
                try:
                    ancien = json.loads(existants[cid]["notes"] or "{}")
                except ValueError:
                    ancien = {}
                ancien = {corresp.get(k, k): x for k, x in ancien.items()}
            notes = {k: x for k, x in ancien.items() if k in d["matieres"]}
            for j, m in enumerate(mats_form):
                brut = val(colonnes[j]) if j < len(colonnes) else ""
                cible = corresp.get(m, m)
                if cible not in d["matieres"]:
                    continue
                try:
                    n = H.xlsx.note(brut)
                except ValueError:
                    mauvaises.append(f"{nom} – {cible} : « {brut} »")
                    continue
                if n is None:
                    notes.pop(cible, None)
                else:
                    notes[cible] = n
            vals = (txt(val(tables), 20), nom, txt(val(prenoms), 120), H.xlsx.sexe(val(sexes)) or None,
                    txt(val(ecoles), 120), json.dumps(notes, ensure_ascii=False))
            if cid:
                ex("""UPDATE cep_blanc_candidats SET numero_table=?, nom=?, prenoms=?, sexe=?, ecole=?, notes=?
                      WHERE id=? AND session_id=?""", vals + (cid, sid))
                n_maj += 1
            else:
                ex("""INSERT INTO cep_blanc_candidats (numero_table, nom, prenoms, sexe, ecole, notes, session_id)
                      VALUES (?,?,?,?,?,?,?)""", vals + (sid,))
                n_new += 1
        for cid in suppr:
            if cid in existants:
                ex("DELETE FROM cep_blanc_candidats WHERE id=? AND session_id=?", (cid, sid))
        for m in err:
            flash(m, "danger")
        if mauvaises:
            flash(f"{len(mauvaises)} note(s) invalide(s) non enregistrée(s) (0 à 20) : " + " ; ".join(mauvaises[:6]),
                  "warning")
        H.journal("cep_blanc_sauvegarde", f"session {sid} : {n_maj} modifié(s), {n_new} ajouté(s), "
                                          f"{len(suppr & set(existants))} supprimé(s)")
        flash(f"Enregistré : {n_maj} candidat(s) mis à jour, {n_new} ajouté(s), "
              f"{len(suppr & set(existants))} supprimé(s).", "success")
        return redirect(url_for("cep_blanc_session", sid=sid, tri=request.args.get("tri") or None))

    @app.route("/cep-blanc/<int:sid>/reinitialiser", methods=["POST"])
    @H.connexion_requise("cep")
    def cep_blanc_reinitialiser(sid):
        s = session_ou_404(sid)
        quoi = request.form.get("quoi")
        if quoi == "tout":
            ex("DELETE FROM cep_blanc_candidats WHERE session_id=?", (sid,))
            flash("Liste des candidats vidée.", "success")
        else:
            ex("UPDATE cep_blanc_candidats SET notes='{}' WHERE session_id=?", (sid,))
            flash("Toutes les notes ont été effacées (les candidats sont conservés).", "success")
        H.journal("cep_blanc_reinitialise", f"session {sid} ({quoi or 'notes'}) N° {s['numero']}")
        return redirect(url_for("cep_blanc_session", sid=sid))

    @app.route("/cep-blanc/<int:sid>/supprimer", methods=["POST"])
    @H.connexion_requise("cep")
    def cep_blanc_supprimer(sid):
        s = session_ou_404(sid)
        ex("DELETE FROM cep_blanc_candidats WHERE session_id=?", (sid,))
        ex("DELETE FROM cep_blanc_sessions WHERE id=?", (sid,))
        H.journal("cep_blanc_supprime", f"N° {s['numero']} ({s['annee']})")
        flash(f"Examen blanc N° {s['numero']} supprimé.", "success")
        return redirect(url_for("cep_blanc_accueil"))

    @app.route("/cep-blanc/<int:sid>/canevas.xlsx")
    @H.connexion_requise("cep")
    def cep_blanc_canevas(sid):
        s = session_ou_404(sid)
        entetes = ["N° table", "Nom", "Prénoms", "Sexe (M/F)", "École de provenance"] + s["mats"]
        return H.xlsx.reponse_xlsx(f"canevas_cep_blanc_{s['numero']}.xlsx", entetes, [], titre="Candidats",
                                   titre_haut=[f"EXAMEN BLANC CEP N° {s['numero']} – {s['annee']} – Centre : {s['centre'] or ''}",
                                               "Une ligne par candidat ; les notes (0 à 20) sont facultatives."])

    @app.route("/cep-blanc/<int:sid>/importer", methods=["POST"])
    @H.connexion_requise("cep")
    def cep_blanc_importer(sid):
        s = session_ou_404(sid)
        fich = request.files.get("fichier")
        if not fich or not fich.filename:
            flash("Choisissez un fichier Excel (.xlsx) ou CSV.", "warning")
            return redirect(url_for("cep_blanc_session", sid=sid))
        if not fich.filename.lower().endswith((".xlsx", ".xlsm", ".csv", ".txt")):
            flash("Format non reconnu : utilisez un fichier .xlsx ou .csv.", "danger")
            return redirect(url_for("cep_blanc_session", sid=sid))
        X = H.xlsx
        try:
            ent, lignes = X.lire_tableau(fich, ("nom", "noms", "nom et prenoms"))
        except X.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("cep_blanc_session", sid=sid))
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("cep_blanc_session", sid=sid))
        i_tab = X.colonne(ent, "n table", "n° table", "numero de table", "num table", "table", "n de table")
        i_nom = X.colonne(ent, "nom", "noms", "nom de famille")
        i_pre = X.colonne(ent, "prenoms", "prénom", "prenom")
        i_nomp = X.colonne(ent, "nom et prenoms", "nom et prénom", "nom prenoms")
        i_sexe = X.colonne(ent, "sexe", "sexe m f", "genre")
        i_eco = X.colonne(ent, "ecole de provenance", "ecole", "etablissement", "école")
        if i_nomp is not None and i_pre is None:
            i_nom = i_nomp
        if i_nom is None:
            flash("Colonne « Nom » introuvable. Utilisez le canevas Excel proposé.", "danger")
            return redirect(url_for("cep_blanc_session", sid=sid))
        norm_ent = [X.normaliser(h) for h in ent]
        i_mats = {}
        for m in s["mats"]:
            nm = X.normaliser(m)
            for j, h in enumerate(norm_ent):
                if h and h == nm and j not in (i_tab, i_nom, i_pre, i_sexe, i_eco):
                    i_mats[m] = j
        existants = {(X.normaliser(c["nom"]), X.normaliser(c["prenoms"])): c for c in candidats_de(sid)}
        crees = maj = 0
        erreurs = []
        for n, l in enumerate(lignes, 2):
            nom, pre = X.valeur(l, i_nom), X.valeur(l, i_pre) if i_pre is not None else ""
            if i_pre is None and " " in nom:
                nom, pre = nom.split(" ", 1)
            nom = txt(nom, 80).upper()
            if not nom:
                continue
            notes = {}
            for m, j in i_mats.items():
                try:
                    v = X.note(X.valeur(l, j))
                except ValueError:
                    erreurs.append(f"Ligne {n} ({nom}) : note de {m} invalide — ignorée.")
                    continue
                if v is not None:
                    notes[m] = v
            table = txt(X.valeur(l, i_tab), 20) if i_tab is not None else ""
            sexe = X.sexe(X.valeur(l, i_sexe)) if i_sexe is not None else ""
            eco = txt(X.valeur(l, i_eco), 120) if i_eco is not None else ""
            c = existants.get((X.normaliser(nom), X.normaliser(pre)))
            if c:
                try:
                    anciennes = json.loads(c["notes"] or "{}")
                except ValueError:
                    anciennes = {}
                anciennes.update(notes)
                ex("""UPDATE cep_blanc_candidats SET numero_table=COALESCE(NULLIF(?,''), numero_table),
                      sexe=COALESCE(NULLIF(?,''), sexe), ecole=COALESCE(NULLIF(?,''), ecole), notes=? WHERE id=?""",
                   (table, sexe, eco, json.dumps(anciennes, ensure_ascii=False), c["id"]))
                maj += 1
            else:
                ex("""INSERT INTO cep_blanc_candidats (session_id, numero_table, nom, prenoms, sexe, ecole, notes)
                      VALUES (?,?,?,?,?,?,?)""",
                   (sid, table, nom, txt(pre, 120), sexe or None, eco, json.dumps(notes, ensure_ascii=False)))
                existants[(X.normaliser(nom), X.normaliser(pre))] = {"id": 0, "notes": "{}"}
                crees += 1
        H.journal("cep_blanc_import", f"session {sid} : {crees} créé(s), {maj} mis à jour")
        flash(f"Import terminé : {crees} candidat(s) ajouté(s), {maj} mis à jour"
              + (f", notes lues pour {len(i_mats)} matière(s)." if i_mats else "."), "success" if crees or maj else "info")
        for m in erreurs[:10]:
            flash(m, "warning")
        return redirect(url_for("cep_blanc_session", sid=sid))

    @app.route("/cep-blanc/<int:sid>/importer-cm2", methods=["POST"])
    @H.connexion_requise("cep")
    def cep_blanc_importer_cm2(sid):
        """Ajoute les élèves inscrits d'une classe de CM2 de l'école (sans doublon)."""
        s = session_ou_404(sid)
        cid = request.form.get("classe", type=int)
        if cid not in {c["id"] for c in classes_cm2()}:
            abort(403)
        deja = {c["eleve_id"] for c in candidats_de(sid) if c["eleve_id"]}
        nom_ecole = ecole_val("nom") or H.config.ECOLE.get("nom", "")
        n = 0
        for e in eleves_de(cid):
            if e["id"] in deja:
                continue
            ex("""INSERT INTO cep_blanc_candidats (session_id, numero_table, nom, prenoms, sexe, ecole, notes, eleve_id)
                  VALUES (?,?,?,?,?,?,?,?)""",
               (sid, e["numero_table"] or "", e["nom"], e["prenoms"], e["sexe"], nom_ecole, "{}", e["id"]))
            n += 1
        H.journal("cep_blanc_import_cm2", f"session {sid} N° {s['numero']} : {n}")
        flash(f"{n} élève(s) de CM2 ajouté(s)." if n else "Tous les élèves de cette classe sont déjà dans la liste.",
              "success" if n else "info")
        return redirect(url_for("cep_blanc_session", sid=sid))

    @app.route("/cep-blanc/<int:sid>/numeroter", methods=["POST"])
    @H.connexion_requise("cep")
    def cep_blanc_numeroter(sid):
        """Attribue les numéros de table dans l'ordre alphabétique (préfixe facultatif)."""
        session_ou_404(sid)
        prefixe = txt(request.form.get("prefixe"), 10)
        debut = request.form.get("debut", type=int) or 1
        cands = sorted(candidats_de(sid), key=lambda c: ((c["nom"] or "").lower(), (c["prenoms"] or "").lower()))
        for i, c in enumerate(cands):
            ex("UPDATE cep_blanc_candidats SET numero_table=? WHERE id=?", (f"{prefixe}{debut + i:03d}", c["id"]))
        flash(f"{len(cands)} numéro(s) de table attribué(s).", "success")
        return redirect(url_for("cep_blanc_session", sid=sid))

    def entete_xlsx(s):
        return [f"EXAMEN BLANC DU CEP N° {s['numero']} – ANNÉE SCOLAIRE {s['annee']}",
                f"Département : {s['departement'] or ''} – DDEMP : {s['ddemp'] or ''} – CS : {s['cs'] or ''} – "
                f"Commune : {s['commune'] or ''} – Centre : {s['centre'] or ''}",
                f"Seuil de maîtrise : {s['seuil_eff']} matière(s) sur {len(s['mats'])} à 10/20 au moins"]

    @app.route("/cep-blanc/<int:sid>/excel")
    @H.connexion_requise("cep")
    def cep_blanc_excel(sid):
        s = session_ou_404(sid)
        lignes = trier_blanc(resultats_blanc(s, candidats_de(sid)), request.args.get("tri", "table"))
        entetes = ["N° table", "Nom", "Prénoms", "Sexe", "École de provenance"] + s["mats"] + [
            "Total", "Moyenne", f"Matières ≥ 10 (seuil {s['seuil_eff']})", "Décision", "Rang"]
        data = [[l["c"]["numero_table"] or "", l["c"]["nom"], l["c"]["prenoms"] or "", l["c"]["sexe"] or "",
                 l["c"]["ecole"] or ""] + [v if v is not None else "" for v in l["notes"]] +
                [l["total"] if l["total"] is not None else "", l["moyenne"] if l["moyenne"] is not None else "",
                 l["reussies"] if l["nb"] else "", l["decision"], l["rang_txt"]] for l in lignes]
        H.journal("cep_blanc_excel", f"session {sid}")
        return H.xlsx.reponse_xlsx(f"cep_blanc_{s['numero']}_{s['annee']}.xlsx", entetes, data, titre="Résultats",
                                   titre_haut=entete_xlsx(s))

    def signature_chef(s):
        return (f"{'La' if (s.get('chef_titre') or '').startswith('Cheffe') else 'Le'} "
                f"{s.get('chef_titre') or 'Chef centre'}").upper(), s["chef_centre"] or "", \
            pdfs.image_data_url(H.signature(f"cep:{s['id']}:chef"))

    @app.route("/cep-blanc/<int:sid>/pdf")
    @H.connexion_requise("cep")
    def cep_blanc_pdf(sid):
        s = session_ou_404(sid)
        tri = request.args.get("tri", "table")
        lignes = trier_blanc(resultats_blanc(s, candidats_de(sid)), tri)
        abrev = [m if len(m) <= 14 else m[:12] + "." for m in s["mats"]]
        cols = ["N° table", "Nom", "Prénoms", "S.", "École de provenance"] + abrev + ["Total", "Moy.", "Nb >= 10", "Décision", "Rang"]
        data, surl = [], {}
        for i, l in enumerate(lignes):
            data.append([l["c"]["numero_table"] or "", l["c"]["nom"], l["c"]["prenoms"] or "", l["c"]["sexe"] or "",
                         l["c"]["ecole"] or ""] + [num(v) for v in l["notes"]] +
                        [num(l["total"]), num(l["moyenne"]), f"{l['reussies']}/{len(s['mats'])}" if l["nb"] else "",
                         l["decision"], l["rang_txt"]])
            if l["maitrise"] is False:
                surl[i] = "#FDECEC"
        st = stats_blanc(lignes)
        t, nom_chef, img = signature_chef(s)
        n = len(s["mats"])
        pdf = H.pdfs.document_tableau(
            f"EXAMEN BLANC DU CEP N° {s['numero']} – RÉSULTATS", cols, data, paysage=True,
            sous_titre=f"Année scolaire {s['annee']} – {'ordre de mérite' if tri == 'merite' else 'liste des candidats'}",
            infos=[("Département", s["departement"]), ("DDEMP", s["ddemp"]), ("CS", s["cs"]), ("Commune", s["commune"]),
                   ("Centre", s["centre"]), ("Seuil de maîtrise", f"{s['seuil_eff']} matière(s) sur {n} à 10/20")],
            infos_haut=[("DDEMP", s["ddemp"]), ("CS", s["cs"]), ("CENTRE", s["centre"])],
            largeurs=[9, 24, 26, 5, 30] + [10] * n + [9, 8, 8, 17, 11], taille=6.5 if n > 8 else 7, surlignes=surl,
            notes_bas=[f"Inscrits : {st['inscrits']['T']} (G {st['inscrits']['G']}, F {st['inscrits']['F']}) – "
                       f"présents : {st['presents']['T']} – ont la MAÎTRISE : {st['maitrise']['T']} "
                       f"(G {st['maitrise']['G']}, F {st['maitrise']['F']}) – taux : "
                       f"{str(st['taux']['T']).replace('.', ',')} %. Règle : MAÎTRISE = au moins {s['seuil_eff']} "
                       f"matière(s) à 10/20 ; la moyenne ne sert qu'au rang.",
                       f"Fait à {s['commune'] or s['centre'] or ''}, le {date_fr(s['date_signature']) or date.today().strftime('%d/%m/%Y')}"],
            signatures=[(t, nom_chef, img, False)])
        H.journal("cep_blanc_pdf", f"session {sid}")
        return H.pdf_reponse(pdf, f"cep_blanc_{s['numero']}_{s['annee']}.pdf")

    @app.route("/cep-blanc/<int:sid>/releves.pdf")
    @H.connexion_requise("cep")
    def cep_blanc_releves(sid):
        """Relevés de notes : ?candidat=<id> (un seul), ?ecole=<nom> (une école de provenance), sinon tous."""
        s = session_ou_404(sid)
        toutes = resultats_blanc(s, candidats_de(sid))
        lignes = trier_blanc(toutes, "table")
        cand = request.args.get("candidat", type=int)
        eco = request.args.get("ecole")
        if cand:
            lignes = [l for l in lignes if l["c"]["id"] == cand]
            if not lignes:
                abort(404)
        elif eco:
            lignes = trier_blanc([l for l in lignes if (l["c"]["ecole"] or "") == eco], "nom")
        if not lignes:
            flash("Aucun candidat à imprimer.", "warning")
            return redirect(url_for("cep_blanc_session", sid=sid))
        pdf = pdf_releves(s, lignes)
        H.journal("cep_blanc_releves", f"session {sid} : {len(lignes)}")
        nom = f"releve_{lignes[0]['c']['nom']}" if cand else (f"releves_{eco}" if eco else "releves")
        return H.pdf_reponse(pdf, f"{nom}_cep_blanc_{s['numero']}.pdf".replace(" ", "_"))

    def pdf_releves(s, lignes):
        """Un relevé de notes (A4) par candidat, présenté comme un bulletin."""
        from reportlab.platypus import Table, TableStyle
        W, Hp = A4
        m = 18 * mm
        buf = io.BytesIO()
        c = pdfs.GCanvas(buf, pagesize=A4)
        c.setTitle(f"Relevés de notes – examen blanc CEP N° {s['numero']}")
        titre_chef, nom_chef, img_chef = signature_chef(s)
        for l in lignes:
            cd = l["c"]
            # en-tête
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(m, Hp - m, "RÉPUBLIQUE DU BÉNIN")
            c.setFont("Helvetica", 7.5)
            c.drawString(m, Hp - m - 10, "MINISTÈRE DES ENSEIGNEMENTS MATERNEL ET PRIMAIRE")
            yy = Hp - m - 22
            for lib, val in (("DDEMP", s["ddemp"] or s["departement"]), ("CS", s["cs"]), ("Commune", s["commune"])):
                if val:
                    c.setFont("Helvetica-Bold", 8)
                    c.drawString(m, yy, f"{lib} :")
                    c.setFont("Helvetica", 8)
                    c.drawString(m + 48, yy, str(val)[:60])
                    yy -= 10
            dessiner_embleme(c, W / 2, Hp - m - 14, 14)
            c.setFont("Helvetica-Bold", 8)
            c.drawRightString(W - m, Hp - m, f"Année scolaire : {s['annee']}")
            c.setFont("Helvetica", 8)
            texte_ajuste(c, W - m, Hp - m - 11, f"Centre : {s['centre'] or '—'}", "Helvetica", 8, 70 * mm, "d")
            bande_tricolore(c, m, Hp - m - 58, W - 2 * m, 2)
            # titre
            c.setFillColor(VERT_F)
            c.roundRect(m + 25 * mm, Hp - m - 92, W - 2 * m - 50 * mm, 28, 5, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 13)
            c.drawCentredString(W / 2, Hp - m - 76, "RELEVÉ DE NOTES")
            c.setFont("Helvetica", 8.5)
            c.drawCentredString(W / 2, Hp - m - 87, f"EXAMEN BLANC DU CERTIFICAT D'ÉTUDES PRIMAIRES N° {s['numero']}")
            # identité
            y = Hp - m - 105
            ident = [["N° de table", cd["numero_table"] or "—", "Sexe", {"M": "Masculin", "F": "Féminin"}.get(cd["sexe"], "—")],
                     ["Nom", cd["nom"], "Prénoms", cd["prenoms"] or ""],
                     ["École de provenance", cd["ecole"] or "—", "Centre", s["centre"] or "—"]]
            t = Table(ident, colWidths=[37 * mm, 52 * mm, 22 * mm, W - 2 * m - 111 * mm])
            t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                                   ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9), ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9),
                                   ("FONT", (1, 1), (1, 1), "Helvetica-Bold", 10),
                                   ("BOX", (0, 0), (-1, -1), 0.8, VERT_F), ("INNERGRID", (0, 0), (-1, -1), 0.3, BORD),
                                   ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EDF5ED")),
                                   ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EDF5ED")),
                                   ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            _, h = t.wrapOn(c, W, Hp)
            t.drawOn(c, m, y - h)
            y -= h + 14
            # notes
            data = [["N°", "Matière", "Note / 20", "Appréciation", "Matière maîtrisée"]]
            for i, (mat, v) in enumerate(zip(s["mats"], l["notes"]), 1):
                data.append([i, mat, num(v) if v is not None else "—", appreciation_note(v) if v is not None else "—",
                             "—" if v is None else ("Oui" if v >= 10 else "Non")])
            data.append(["", "TOTAL DES POINTS", num(l["total"]) or "—", "", ""])
            data.append(["", "MOYENNE (pour le rang)", num(l["moyenne"]) or "—", "", ""])
            t = Table(data, colWidths=[10 * mm, 72 * mm, 22 * mm, 32 * mm, W - 2 * m - 136 * mm], repeatRows=1)
            stl = [("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                   ("BACKGROUND", (0, 0), (-1, 0), VERT_F), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                   ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")), ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                   ("ALIGN", (0, 0), (0, -1), "CENTER"), ("FONT", (0, -2), (-1, -1), "Helvetica-Bold", 9),
                   ("BACKGROUND", (0, -2), (-1, -1), colors.HexColor("#F2F4F7")),
                   ("SPAN", (2, -2), (4, -2)), ("SPAN", (2, -1), (4, -1)),
                   ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
            for i, v in enumerate(l["notes"], 1):
                if v is not None and v < 10:
                    stl.append(("TEXTCOLOR", (2, i), (2, i), colors.HexColor("#B42318")))
            t.setStyle(TableStyle(stl))
            _, h = t.wrapOn(c, W, Hp)
            t.drawOn(c, m, y - h)
            y -= h + 14
            # décision
            ok = l["maitrise"]
            coul = colors.HexColor("#1B7F3B") if ok else (colors.HexColor("#B42318") if ok is False else colors.grey)
            res = [["Matières à 10/20 et plus", f"{l['reussies']} / {len(s['mats'])}" if l["nb"] else "—",
                    "Seuil de maîtrise", f"{l['seuil']} matière(s)"],
                   ["Rang", f"{l['rang_txt']} sur {l['effectif']}" if l["rang"] else "—", "DÉCISION", l["decision"]]]
            t = Table(res, colWidths=[45 * mm, 35 * mm, 38 * mm, W - 2 * m - 118 * mm])
            t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9.5),
                                   ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9.5), ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9.5),
                                   ("FONT", (3, 1), (3, 1), "Helvetica-Bold", 12), ("TEXTCOLOR", (3, 1), (3, 1), coul),
                                   ("BOX", (0, 0), (-1, -1), 0.8, VERT_F), ("INNERGRID", (0, 0), (-1, -1), 0.3, BORD),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            _, h = t.wrapOn(c, W, Hp)
            t.drawOn(c, m, y - h)
            y -= h + 8
            c.setFillColor(colors.HexColor("#475467"))
            c.setFont("Helvetica-Oblique", 7.5)
            c.drawString(m, y, f"MAÎTRISE = au moins {l['seuil']} matière(s) à 10/20 sur {len(s['mats'])} ; "
                               "la moyenne ne sert qu'au classement.")
            # signature du chef centre
            y -= 26
            x = W - m - 40 * mm
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 9)
            lieu = s["commune"] or s["centre"] or ""
            c.drawCentredString(x, y, f"Fait à {lieu}, le {date_fr(s['date_signature']) or date.today().strftime('%d/%m/%Y')}")
            c.setFont("Helvetica-Bold", 9.5)
            c.drawCentredString(x, y - 14, titre_chef)
            if img_chef is not None:
                c.drawImage(img_chef, x - 25 * mm, y - 14 - 24 * mm, 50 * mm, 20 * mm, preserveAspectRatio=True, mask="auto")
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(x, y - 14 - 30 * mm, nom_chef)
            c.showPage()
        c.save()
        return buf.getvalue()
