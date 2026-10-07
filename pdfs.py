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
    """« Conception : Maître Aimé FACHE » en bas de chaque page."""
    w = largeur or c._pagesize[0]
    c.saveState()
    c.setFillColor(colors.HexColor("#667085"))
    if c._pagesize[1] < 120 * mm:  # petit format (carte) : discret, en bas à droite
        c.setFont("Helvetica-Oblique", 5)
        c.drawRightString(w - 2.5 * mm, 1.6 * mm, f"Conception : {config.CONCEPTEUR}")
    else:
        c.setFont("Helvetica-Oblique", 6.5)
        c.drawCentredString(w / 2, 3.2 * mm, f"Conception : {config.CONCEPTEUR}")
    c.restoreState()


class GCanvas(canvas.Canvas):
    """Canvas GESCOL : ajoute la mention du concepteur sur chaque page."""

    def showPage(self):
        mention_concepteur(self)
        super().showPage()

    def save(self):
        if self._code:  # page en cours non terminée
            mention_concepteur(self)
        super().save()


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
    ca = config.ECOLE.get("_cachet")
    if ca:
        import cachet as _cachet
        _cachet.dessiner(c, cx, cy, rayon, *ca)
        return True
    img = _ecole_img("cachet.png")
    if img:
        c.drawImage(img, cx - rayon, cy - rayon, 2 * rayon, 2 * rayon, preserveAspectRatio=True, mask="auto")
        return True
    return False


def signature_directeur():
    return image_data_url(config.ECOLE.get("_sig_directeur")) or _ecole_img("signature.png")


def bloc_signature(c, x, y, titre, nom="", image=None, cachet=False, lieu_date=True, largeur=45 * mm):
    """Bloc de signature générique centré en x : [lieu, date] titre, signature (image), cachet, nom."""
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
            base = "http://localhost:5000"
    return f"{base.rstrip('/')}/verifier/{code}"


def _qr(c, code, x, y, taille=22 * mm, legende=True):
    w = QrCodeWidget(url_verif(code))
    b = w.getBounds()
    d = Drawing(taille, taille, transform=[taille / (b[2] - b[0]), 0, 0, taille / (b[3] - b[1]), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x, y)
    if legende:
        c.setFont("Helvetica", 6.5)
        c.setFillColor(colors.black)
        c.drawString(x + taille + 2 * mm, y + taille - 8, "Document vérifiable")
        c.drawString(x + taille + 2 * mm, y + taille - 17, f"Code : {code}")
        c.drawString(x + taille + 2 * mm, y + taille - 26, url_verif(code)[:60])


def _entete(c, cycle, titre, sous_titre=None, W=A4[0], H=A4[1], marge=15 * mm):
    """En-tête officiel. Retourne l'ordonnée sous l'en-tête."""
    haut = H - marge
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(marge, haut - 8, "RÉPUBLIQUE DU BÉNIN")
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(marge, haut - 18, "Fraternité – Justice – Travail")
    c.setFont("Helvetica", 7)
    min_txt = MINISTERE.get(cycle, "")
    if len(min_txt) > 60:
        coupe = min_txt.rfind(" ", 0, 60)
        c.drawString(marge, haut - 29, min_txt[:coupe])
        c.drawString(marge, haut - 37, min_txt[coupe + 1:])
    else:
        c.drawString(marge, haut - 29, min_txt)

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
    for i, t in enumerate(lignes):
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
    if config.ECOLE.get("directeur"):
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
    cachet = _ecole_img("cachet.png")
    if cachet:
        c.drawImage(cachet, W - m - 40 * mm, 12 * mm, 22 * mm, 22 * mm, preserveAspectRatio=True, mask="auto")
    c.showPage()
    _fin(c)
    return buf.getvalue()


# ---------------------------------------------------------------- carte d'élève
def carte(eleve, classe, annee, code, photo):
    W, H = 85.6 * mm, 54 * mm
    buf = io.BytesIO()
    c = GCanvas(buf, pagesize=(W, H))
    c.setTitle(f"Carte {eleve['matricule']}")
    c.setFillColor(BLEU)
    c.rect(0, H - 11 * mm, W, 11 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(3 * mm, H - 5 * mm, config.ECOLE["nom"][:44])
    c.setFont("Helvetica", 6.5)
    c.drawString(3 * mm, H - 9 * mm, f"CARTE D'ÉLÈVE – {annee}")
    logo = _ecole_img("logo.png")
    if logo:
        c.drawImage(logo, W - 11 * mm, H - 10.5 * mm, 9.5 * mm, 9.5 * mm, preserveAspectRatio=True, mask="auto")
    # photo
    px, py, pw, ph = 3 * mm, 9 * mm, 20 * mm, 25 * mm
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
    yy = H - 15 * mm
    for lab, val in lignes:
        c.setFont("Helvetica", 5.8)
        c.drawString(x, yy, lab)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x + 12 * mm, yy, str(val or "—")[:26])
        yy -= 4.3 * mm
    c.setFont("Helvetica", 5.5)
    urgence = f"{eleve['parent_nom'] or ''} {eleve['parent_telephone'] or ''}".strip()
    if urgence:
        c.drawString(3 * mm, 5 * mm, f"Urgence : {urgence}"[:60])
    _qr(c, code, W - 17 * mm, 2 * mm, taille=15 * mm, legende=False)
    c.showPage()
    _fin(c)
    return buf.getvalue()


# ---------------------------------------------------------------- certificats
TITRES = {
    "certificat_frequentation": "CERTIFICAT DE FRÉQUENTATION",
    "attestation_inscription": "ATTESTATION D'INSCRIPTION",
    "certificat_transfert": "CERTIFICAT DE TRANSFERT",
}


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
def fiche_cep(eleve, classe, annee, code, photo):
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
    """En-tête des documents du primaire : République, ministère, DDEMP, CS, école (colonne gauche) ; logo à droite."""
    y = H - marge
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(marge, y - 8, "RÉPUBLIQUE DU BÉNIN")
    c.setFont("Helvetica", 7)
    ministere = MINISTERE.get(cycle, MINISTERE["primaire"]).upper()
    if len(ministere) > 75:  # secondaire : sur deux lignes
        coupe = ministere.rfind(" ", 0, 60)
        c.drawString(marge, y - 17, ministere[:coupe])
        y -= 8
        c.drawString(marge, y - 17, ministere[coupe + 1:])
    else:
        c.drawString(marge, y - 17, ministere)
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
    logo = _ecole_img("logo.png")
    if logo:
        c.drawImage(logo, W - marge - 18 * mm, y - 18 * mm, 18 * mm, 18 * mm, preserveAspectRatio=True, mask="auto")
    return min(yy, y - 20 * mm) - 4


def document_tableau(titre, colonnes, lignes, sous_titre=None, infos=None, largeurs=None, paysage=False,
                     signatures=None, notes_bas=None, infos_haut=None, total=None, taille=7.5, avant=None, apres=None,
                     alignements=None, surlignes=None, cycle=None):
    """PDF d'un tableau (répété sur chaque page) avec en-tête officiel, bloc d'infos, signatures.
    colonnes : liste d'intitulés (ou liste de listes pour un en-tête sur plusieurs lignes)
    lignes : liste de listes ; total : ligne de total mise en gras
    infos : [(libellé, valeur)] affichés en grille sous le titre
    signatures : [(titre, nom, image_reader_ou_None, cachet_bool)]
    avant/apres : liste de flowables (Paragraph, Table) insérés avant/après le tableau
    surlignes : {indice_ligne: couleur_hex} pour colorer des lignes."""
    from reportlab.lib.pagesizes import landscape
    from reportlab.platypus import SimpleDocTemplate, Spacer, KeepTogether
    from reportlab.platypus.flowables import Flowable

    taille_page = landscape(A4) if paysage else A4
    W, Hh = taille_page
    marge = 12 * mm
    buf = io.BytesIO()
    st_c = ParagraphStyle("c", fontName="Helvetica", fontSize=taille, leading=taille + 1.6)
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=taille, leading=taille + 1.6, alignment=1,
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
        st_t = ParagraphStyle("t", parent=st_c, fontName="Helvetica-Bold")
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
    st_titre = ParagraphStyle("ti", fontName="Helvetica-Bold", fontSize=13, leading=16, alignment=1, textColor=BLEU,
                              spaceAfter=2)
    st_st = ParagraphStyle("st", fontName="Helvetica", fontSize=9.5, leading=12, alignment=1, spaceAfter=4)
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
            histoire.append(Paragraph(n, ParagraphStyle("nb", fontName="Helvetica", fontSize=7.5, leading=9.5)))
    if signatures:
        histoire.append(Spacer(1, 6))
        histoire.append(KeepTogether([_BlocSignatures(signatures, utile)]))

    haut_entete = [0]

    def deco(c, doc):
        y = _entete_primaire(c, W, Hh, marge, infos_haut, cycle)
        haut_entete[0] = Hh - y
        c.setFont("Helvetica", 6.5)
        c.setFillColor(colors.grey)
        c.drawString(marge, 7 * mm, f"GESCOL · {config.ECOLE.get('nom', '')} · {config.ANNEE_ACTIVE}")
        c.drawRightString(W - marge, 7 * mm, f"Page {doc.page} · imprimé le {date.today().strftime('%d/%m/%Y')}")
        c.setFillColor(colors.black)

    doc = SimpleDocTemplate(buf, pagesize=taille_page, leftMargin=marge, rightMargin=marge,
                            topMargin=marge + 30 * mm, bottomMargin=13 * mm, title=titre, author="GESCOL")
    doc.build(histoire, onFirstPage=deco, onLaterPages=deco, canvasmaker=GCanvas)
    return buf.getvalue()


from reportlab.platypus.flowables import Flowable as _Flowable  # noqa: E402


class _BlocSignatures(_Flowable):
    """Signatures côte à côte : (titre, nom, image, cachet)."""

    def __init__(self, signatures, largeur):
        super().__init__()
        self.sigs = signatures
        self.largeur = largeur
        self.height = 36 * mm

    def wrap(self, *_):
        return self.largeur, self.height

    def draw(self):
        c = self.canv
        n = len(self.sigs)
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
            if nom:
                c.setFont("Helvetica", 8.5)
                c.drawCentredString(x, y - 30.5 * mm, nom)


def paragraphe(texte, taille=8.5, gras=False, align=0, espace=3):
    return Paragraph(texte, ParagraphStyle("p", fontName="Helvetica-Bold" if gras else "Helvetica", fontSize=taille,
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
