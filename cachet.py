# -*- coding: utf-8 -*-
"""Cachet officiel circulaire, tel qu'utilisé dans les écoles :
texte en arc supérieur ★ texte en arc inférieur ★, texte central, bleu ou rouge.
Deux rendus identiques : SVG (écran) et ReportLab (PDF)."""
import math
from html import escape

COULEURS = {"bleu": "#1E3A8A", "rouge": "#B91C1C"}


ANGLE_MAX = 150  # degrés occupés au maximum par chaque texte en arc


def _angles(texte, rayon, taille):
    """Taille de police ajustée et angle (degrés) de chaque caractère, proportionnel à sa largeur réelle."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    esp = taille * 0.08  # léger espacement entre lettres
    larg = [stringWidth(ch, "Helvetica-Bold", taille) + esp for ch in texte]
    total = math.degrees(sum(larg) / rayon)
    if total > ANGLE_MAX:
        f = ANGLE_MAX / total
        taille *= f
        larg = [w * f for w in larg]
    return taille, [math.degrees(w / rayon) for w in larg]


def svg(sup="", inf="", centre="", couleur="bleu", taille=180):
    col = COULEURS.get(couleur, couleur or COULEURS["bleu"])
    r = taille / 2
    rt = r * 0.74          # rayon du texte
    fs = r * 0.17          # taille de police des arcs
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {taille} {taille}" width="{taille}" height="{taille}" '
             f'role="img" aria-label="Cachet : {escape(sup)} {escape(centre)} {escape(inf)}">',
             f'<g fill="none" stroke="{col}" opacity="0.92">'
             f'<circle cx="{r}" cy="{r}" r="{r - 3}" stroke-width="3.2"/>'
             f'<circle cx="{r}" cy="{r}" r="{r - 8}" stroke-width="1"/>'
             f'<circle cx="{r}" cy="{r}" r="{r * 0.56}" stroke-width="1.4"/></g>',
             f'<g fill="{col}" font-family="Arial, Helvetica, sans-serif" font-weight="700" opacity="0.92">']

    def arc(texte, haut):
        texte = (texte or "").upper()
        if not texte:
            return
        t, angs = _angles(texte, rt, fs)
        total = sum(angs)
        cumul = 0
        for ch, pas in zip(texte, angs):
            milieu = cumul + pas / 2
            cumul += pas
            if haut:
                a = 90 + total / 2 - milieu
                rot = 90 - a
            else:
                a = 270 - total / 2 + milieu
                rot = 270 - a
            x = r + rt * math.cos(math.radians(a))
            y = r - rt * math.sin(math.radians(a))
            parts.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{t:.2f}" text-anchor="middle" dominant-baseline="central" '
                         f'transform="rotate({rot:.2f} {x:.2f} {y:.2f})">{escape(ch)}</text>')

    arc(sup, True)
    arc(inf, False)
    for a in (0, 180):
        x = r + rt * math.cos(math.radians(a))
        parts.append(f'<text x="{x:.2f}" y="{r:.2f}" font-size="{fs * 1.1:.2f}" text-anchor="middle" dominant-baseline="central">★</text>')
    lignes = [l for l in (centre or "").upper().split("|") if l.strip()] or [""]
    fc = _taille_centre([l.strip() for l in lignes], r)
    y0 = r - (len(lignes) - 1) * fc * 0.6
    for k, l in enumerate(lignes):
        parts.append(f'<text x="{r}" y="{y0 + k * fc * 1.2:.2f}" font-size="{fc:.2f}" text-anchor="middle" '
                     f'dominant-baseline="central">{escape(l.strip())}</text>')
    parts.append("</g></svg>")
    return "".join(parts)


def dessiner(c, cx, cy, rayon, sup="", inf="", centre="", couleur="bleu"):
    """Dessine le cachet sur un canvas ReportLab (centre cx, cy ; rayon en points)."""
    from reportlab.lib import colors
    col = colors.HexColor(COULEURS.get(couleur, COULEURS["bleu"]))
    c.saveState()
    c.setStrokeColor(col)
    c.setFillColor(col)
    c.setLineWidth(max(1.2, rayon * 0.035))
    c.circle(cx, cy, rayon - 1.5, stroke=1, fill=0)
    c.setLineWidth(0.5)
    c.circle(cx, cy, rayon * 0.9, stroke=1, fill=0)
    c.setLineWidth(0.7)
    c.circle(cx, cy, rayon * 0.56, stroke=1, fill=0)
    rt = rayon * 0.74
    fs = rayon * 0.17

    def arc(texte, haut):
        texte = (texte or "").upper()
        if not texte:
            return
        t, angs = _angles(texte, rt, fs)
        total = sum(angs)
        c.setFont("Helvetica-Bold", t)
        cumul = 0
        for ch, pas in zip(texte, angs):
            milieu = cumul + pas / 2
            cumul += pas
            if haut:
                a = 90 + total / 2 - milieu
                rot = a - 90
            else:
                a = 270 - total / 2 + milieu
                rot = a - 270
            x = cx + rt * math.cos(math.radians(a))
            y = cy + rt * math.sin(math.radians(a))
            c.saveState()
            c.translate(x, y)
            c.rotate(rot)
            c.drawCentredString(0, -t * 0.35, ch)
            c.restoreState()

    arc(sup, True)
    arc(inf, False)
    # étoiles (dessinées : la police standard n'a pas le caractère ★)
    for a in (0, 180):
        x = cx + rt * math.cos(math.radians(a))
        _etoile(c, x, cy, fs * 0.55)
    lignes = [l.strip() for l in (centre or "").upper().split("|") if l.strip()] or [""]
    fc = _taille_centre(lignes, rayon)
    c.setFont("Helvetica-Bold", fc)
    y0 = cy + (len(lignes) - 1) * fc * 0.6
    for k, l in enumerate(lignes):
        c.drawCentredString(cx, y0 - k * fc * 1.2 - fc * 0.35, l)
    c.restoreState()


def _etoile(c, x, y, r):
    p = c.beginPath()
    for k in range(10):
        ang = math.radians(90 + k * 36)
        rr = r if k % 2 == 0 else r * 0.45
        px, py = x + rr * math.cos(ang), y + rr * math.sin(ang)
        if k == 0:
            p.moveTo(px, py)
        else:
            p.lineTo(px, py)
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def _taille_centre(lignes, rayon):
    """Taille du texte central : tient dans le cercle intérieur (diamètre ~ 1,0 x rayon)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    fc = rayon * 0.2
    plus_large = max(stringWidth(l, "Helvetica-Bold", fc) for l in lignes) or 1
    if plus_large > rayon * 0.98:
        fc *= rayon * 0.98 / plus_large
    return min(fc, rayon * 0.9 / (1.2 * len(lignes)))
