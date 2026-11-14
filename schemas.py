# -*- coding: utf-8 -*-
"""Bibliothèque de schémas et de cartes (SVG vectoriels, rédaction originale) pour le primaire et le secondaire.
Les cartes du Bénin sont schématiques (contour simplifié, positions approximatives) : elles servent à l'apprentissage, pas à la mesure."""
import math

INK, FILL, ACC, ACC2, SOFT = "#1f3a5f", "#f4f7fb", "#0f7b4a", "#c0392b", "#e8eef6"
_ST = f'font-family="Arial,Helvetica,sans-serif" font-size="13" fill="{INK}"'


def svg(w, h, corps, titre):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="{titre}" {_ST} '
            f'style="max-width:100%;height:auto;background:#fff">{corps}</svg>')


def t(x, y, s, anchor="middle", size=13, bold=False, col=INK):
    gras = ' font-weight="bold"' if bold else ""
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" fill="{col}"{gras}>{s}</text>'


def ln(x1, y1, x2, y2, col=INK, w=1.5, dash=""):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{w}"' + (f' stroke-dasharray="{dash}"' if dash else "") + "/>"


def ci(x, y, r, fill=FILL, col=INK, w=1.5):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{col}" stroke-width="{w}"/>'


def el(x, y, rx, ry, fill=FILL, col=INK, w=1.5):
    return f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{col}" stroke-width="{w}"/>'


def rc(x, y, w, h, fill=FILL, col=INK, sw=1.5, r=0):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{col}" stroke-width="{sw}"/>'


def pg(pts, fill=FILL, col=INK, w=1.5):
    return f'<polygon points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="{fill}" stroke="{col}" stroke-width="{w}" stroke-linejoin="round"/>'


def pa(d, fill="none", col=INK, w=1.5):
    return f'<path d="{d}" fill="{fill}" stroke="{col}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>'


def lab(x, y, s, tx, ty, anchor="start"):
    """Légende avec trait : point (x, y) relié au texte (tx, ty)."""
    return ln(x, y, tx, ty, w=1) + t(tx + (4 if anchor == "start" else -4), ty + 4, s, anchor)


# ---------------------------------------------------------------- carte du Bénin
# (longitude, latitude) : contour simplifié, sens horaire depuis l'embouchure à l'ouest
BENIN = [(1.62, 6.25), (1.60, 6.60), (1.62, 7.00), (1.64, 7.50), (1.66, 8.00), (1.66, 8.50), (1.50, 9.05), (1.30, 9.55), (1.12, 9.95),
         (0.92, 10.35), (0.78, 10.70), (0.78, 10.98), (0.95, 11.07), (1.20, 11.35), (1.55, 11.60), (1.95, 11.85), (2.20, 12.05), (2.40, 12.40),
         (2.75, 12.36), (3.05, 12.28), (3.30, 12.12), (3.55, 11.82), (3.62, 11.50), (3.68, 11.15), (3.80, 10.75), (3.85, 10.30), (3.78, 9.95),
         (3.60, 9.55), (3.35, 9.15), (3.08, 8.70), (2.85, 8.30), (2.74, 7.95), (2.76, 7.50), (2.78, 7.20), (2.72, 6.90), (2.72, 6.60), (2.71, 6.40),
         (2.45, 6.35), (2.10, 6.30), (1.85, 6.26)]
VILLES = {  # chefs-lieux de département
    "Kandi": (2.94, 11.13, "Alibori"), "Natitingou": (1.38, 10.30, "Atacora"), "Parakou": (2.63, 9.34, "Borgou"), "Djougou": (1.67, 9.71, "Donga"),
    "Dassa-Zoumè": (2.18, 7.75, "Collines"), "Abomey": (1.99, 7.18, "Zou"), "Pobè": (2.67, 6.98, "Plateau"), "Porto-Novo": (2.63, 6.50, "Ouémé"),
    "Allada": (2.15, 6.67, "Atlantique"), "Cotonou": (2.43, 6.37, "Littoral"), "Lokossa": (1.72, 6.64, "Mono"), "Aplahoué": (1.68, 6.94, "Couffo")}
W0, H0, K = 90, 60, 90


def P(lon, lat):
    return ((lon - 0.5) * K + 60, (12.6 - lat) * K * 0.99 + 44)


def contour(fill=FILL):
    return pg([P(a, b) for a, b in BENIN], fill=fill, col=INK, w=2)


def carte_base(titre, corps, fill=FILL, notes=""):
    w, h = 480, 700
    fond = (f'<rect width="{w}" height="{h}" fill="#fff"/>' + contour(fill) + corps +
            t(240, 24, titre, size=16, bold=True) + t(240, 692, "Carte schématique : contour et positions approximatifs." + notes, size=10, col="#667"))
    return svg(w, h, fond + _rose(430, 90), titre)


def _rose(x, y):
    return (ln(x, y + 22, x, y - 22, col=INK, w=2) + pg([(x, y - 30), (x - 6, y - 16), (x + 6, y - 16)], fill=INK) + t(x, y - 36, "N", bold=True) +
            ln(x - 16, y, x + 16, y, w=1))


def carte_departements():
    c = ""
    for n, (lo, la, dep) in VILLES.items():
        x, y = P(lo, la)
        c += ci(x, y, 4, fill=ACC if n != "Porto-Novo" and n != "Cotonou" else ACC2, col=INK, w=1)
        gauche = dep in ("Mono", "Couffo", "Atacora", "Donga", "Zou", "Atlantique")
        dy = {"Mono": 10, "Couffo": 2, "Zou": -4, "Atlantique": 44, "Ouémé": -10, "Littoral": 16}.get(dep, 4)
        c += t(x + (-8 if gauche else 8), y + dy, f"{dep} ({n})", anchor="end" if gauche else "start", size=11)
    c += t(300, 672, "Océan Atlantique (golfe de Guinée)", size=12, col="#2a6fa8")
    return carte_base("Le Bénin : les 12 départements et leurs chefs-lieux", c, notes=" Rouge : Porto-Novo, Cotonou.")


def carte_voisins():
    c = (t(60, 300, "TOGO", size=15, bold=True) + t(420, 330, "NIGÉRIA", size=15, bold=True) + t(330, 100, "NIGER", size=15, bold=True) +
         t(130, 120, "BURKINA FASO", size=14, bold=True) + t(240, 665, "OCÉAN ATLANTIQUE", size=14, bold=True, col="#2a6fa8") +
         t(240, 360, "BÉNIN", size=20, bold=True, col=ACC))
    for n in ("Porto-Novo", "Cotonou"):
        x, y = P(*VILLES[n][:2]); c += ci(x, y, 4, fill=ACC2, w=1)
    x, y = P(*VILLES["Porto-Novo"][:2]); c += t(x + 8, y - 6, "Porto-Novo", anchor="start", size=11)
    return carte_base("Le Bénin et ses pays voisins", c, fill="#eef6ee")


def carte_climats():
    c = ""
    bandes = [(12.5, 10.2, "Climat soudanien : une saison sèche et une saison des pluies", "#f6e7b8"), (10.2, 7.9, "Climat soudano-guinéen", "#dbeab4"),
              (7.9, 6.2, "Climat subéquatorial (deux saisons des pluies)", "#bfe0c4")]
    clip = '<clipPath id="cl">' + pg([P(a, b) for a, b in BENIN]).replace('fill="' + FILL + '"', "") + "</clipPath>"
    c += clip
    for a, b, lab_, col in bandes:
        y1, y2 = P(1, a)[1], P(1, b)[1]
        c += f'<rect x="0" y="{y1:.0f}" width="480" height="{y2 - y1:.0f}" fill="{col}" clip-path="url(#cl)"/>'
    c += contour("none")
    c += t(250, 160, "Climat soudanien", size=12, bold=True) + t(250, 175, "(savane sèche, 1 saison des pluies)", size=10)
    c += t(250, 330, "Climat soudano-guinéen", size=12, bold=True) + t(250, 345, "(savane arborée)", size=10)
    c += t(250, 560, "Climat subéquatorial", size=12, bold=True) + t(250, 575, "(forêts et cultures, 2 saisons des pluies)", size=10)
    return carte_base("Les grandes zones climatiques du Bénin", c, fill="none")


def carte_parcs():
    zones = [("Parc national de la Pendjari", 1.35, 10.95, 22, 40), ("Parc national du W", 2.55, 11.85, 28, 26), ("Forêt classée de la Lama", 2.28, 6.95, 16, 10),
             ("Parc de Kandi-Segbana (zone cynégétique)", 3.35, 10.95, 22, 22)]
    c = ""
    for n, lo, la, rx, ry in zones:
        x, y = P(lo, la); c += el(x, y, rx, ry, fill="#9fd3a6", w=1.2) + t(x, y + 4, {"Pendjari": "Pendjari", "W": "W", "Lama": "Lama", "Kandi": "Segbana"}[n.split()[-1] if n.split()[-1] in ("Pendjari", "W", "Lama") else "Kandi"], size=10, bold=True)
    for n in ("Cotonou", "Porto-Novo", "Parakou", "Natitingou", "Kandi", "Djougou", "Abomey"):
        x, y = P(*VILLES[n][:2]); c += ci(x, y, 3, fill=ACC2, w=1) + t(x + 6, y + 4, n, anchor="start", size=10)
    return carte_base("Parcs et grandes villes du Bénin", c)


def carte_relief():
    c = ""
    x, y = P(1.45, 10.3)
    c += pa(f"M{x-25:.0f},{y+30:.0f} L{x:.0f},{y-20:.0f} L{x+22:.0f},{y+10:.0f} L{x+40:.0f},{y+35:.0f} Z", fill="#d9c9a8") + t(x + 60, y + 60, "Chaîne de l'Atacora", size=11, bold=True)
    x2, y2 = P(2.2, 8.2)
    c += t(x2 + 10, y2, "Collines du centre", size=11, bold=True)
    x3, y3 = P(2.3, 7.0)
    c += t(x3 + 20, y3 + 22, "Plateau", size=11, bold=True)
    x4, y4 = P(2.2, 6.45)
    c += t(x4 + 70, y4 + 36, "Côte : lagunes et cordon sableux", size=10, col="#2a6fa8")
    xn, yn = P(3.0, 11.9)
    c += t(xn + 10, yn - 6, "Fleuve Niger (frontière nord)", size=11, col="#2a6fa8", anchor="middle")
    xo, yo = P(2.58, 7.5)
    c += pa(f"M{P(2.5,9.0)[0]:.0f},{P(2.5,9.0)[1]:.0f} Q{xo+10:.0f},{yo:.0f} {P(2.6,6.7)[0]:.0f},{P(2.6,6.7)[1]:.0f}", col="#2a6fa8", w=2) + t(xo + 14, yo, "Fleuve Ouémé", anchor="start", size=11, col="#2a6fa8")
    xm, ym = P(1.68, 7.0)
    c += pa(f"M{P(1.65,8.2)[0]:.0f},{P(1.65,8.2)[1]:.0f} Q{xm:.0f},{ym:.0f} {P(1.62,6.3)[0]:.0f},{P(1.62,6.3)[1]:.0f}", col="#2a6fa8", w=2) + t(xm - 6, ym, "Mono", anchor="end", size=11, col="#2a6fa8")
    return carte_base("Relief et cours d'eau du Bénin (schématique)", c)


# ---------------------------------------------------------------- schémas du primaire et du secondaire
def plante():
    c = (rc(0, 0, 480, 360, fill="#fff", col="#fff", sw=0) + rc(0, 285, 480, 75, fill="#c8a272", col="#c8a272", sw=0) + ln(240, 285, 240, 120, col="#2a8a3c", w=6) +
         pa("M240,230 Q300,200 330,215 Q300,250 240,245", fill="#6cc27a") + pa("M240,190 Q180,160 150,175 Q180,210 240,205", fill="#6cc27a") +
         ci(240, 95, 22, fill="#f3d24a") + "".join(el(240 + 36 * math.cos(a * math.pi / 3), 95 + 36 * math.sin(a * math.pi / 3), 14, 10, fill="#f08fb0") for a in range(6)) +
         pa("M240,285 Q215,320 195,345 M240,285 Q240,325 240,350 M240,285 Q268,320 290,345", col="#7a4b1c", w=3) +
         lab(240, 95, "Fleur", 330, 60) + lab(330, 215, "Feuille", 400, 205) + lab(240, 170, "Tige", 70, 140, "end") + lab(240, 320, "Racines", 345, 330) + lab(240, 300, "Sol", 70, 300, "end"))
    return svg(480, 360, c, "Les parties d'une plante")


def cycle_eau():
    c = (rc(0, 200, 480, 150, fill="#bcd9f2", col="#bcd9f2", sw=0) + pg([(0, 200), (120, 140), (230, 200)], fill="#a98f6b") + pg([(230, 200), (330, 160), (480, 200)], fill="#8aa26b") +
         ci(420, 50, 24, fill="#f7d94a", col="#e0b400") + el(150, 70, 55, 25, fill="#dfe6ee") + el(190, 60, 45, 22, fill="#dfe6ee") +
         ln(90, 195, 90, 120, col=ACC2, w=2) + pg([(90, 112), (84, 124), (96, 124)], fill=ACC2) + ln(290, 180, 290, 110, col=ACC2, w=2) + pg([(290, 100), (284, 112), (296, 112)], fill=ACC2) +
         ln(150, 100, 150, 140, col="#2a6fa8", w=2) + pg([(150, 150), (144, 138), (156, 138)], fill="#2a6fa8") + ln(175, 95, 175, 135, col="#2a6fa8", w=2) +
         t(300, 90, "1. Évaporation", anchor="start", bold=True) + t(30, 240, "2. Condensation : les nuages se forment", anchor="start", bold=True) + t(30, 40, "3. Précipitations (pluie)", anchor="start", bold=True) +
         t(30, 330, "4. Ruissellement et infiltration vers les cours d'eau et la mer", anchor="start", bold=True))
    return svg(480, 360, c, "Le cycle de l'eau")


def rose_vents():
    c = ci(240, 180, 110, fill="#fff") + ln(240, 60, 240, 300, w=2) + ln(120, 180, 360, 180, w=2) + pg([(240, 55), (230, 85), (250, 85)], fill=ACC2)
    for x, y, s in ((240, 40, "Nord (N)"), (240, 322, "Sud (S)"), (390, 185, "Est (E)"), (90, 185, "Ouest (O)")):
        c += t(x, y, s, bold=True)
    c += t(240, 350, "Le soleil se lève à l'Est et se couche à l'Ouest.", size=12)
    return svg(480, 360, c, "Les points cardinaux")


def drapeau():
    c = rc(100, 80, 280, 190, fill="#fff", col=INK) + rc(100, 80, 112, 190, fill="#008751", col=INK) + rc(212, 80, 168, 95, fill="#fcd116", col=INK) + rc(212, 175, 168, 95, fill="#e8112d", col=INK)
    return svg(480, 340, c + t(240, 310, "Drapeau du Bénin : vert, jaune, rouge", size=13, bold=True), "Le drapeau du Bénin")


def fractions():
    c = ""
    for i, (n, d) in enumerate(((1, 2), (1, 4), (3, 4), (2, 3))):
        cx, cy = 80 + i * 115, 110
        c += ci(cx, cy, 45, fill="#fff")
        for k in range(d):
            a0, a1 = -math.pi / 2 + 2 * math.pi * k / d, -math.pi / 2 + 2 * math.pi * (k + 1) / d
            x0, y0, x1, y1 = cx + 45 * math.cos(a0), cy + 45 * math.sin(a0), cx + 45 * math.cos(a1), cy + 45 * math.sin(a1)
            c += pa(f"M{cx},{cy} L{x0:.1f},{y0:.1f} A45,45 0 {1 if a1-a0 > math.pi else 0},1 {x1:.1f},{y1:.1f} Z", fill="#f6b26b" if k < n else "#fff", w=1.2)
        c += t(cx, 195, f"{n}/{d}", size=18, bold=True)
    c += t(240, 240, "numérateur = parts prises ; dénominateur = parts égales du tout", size=12)
    return svg(480, 260, c, "Les fractions")


def figures():
    c = (pg([(40, 140), (120, 140), (120, 60), (40, 60)], fill="#cfe3f7") + t(80, 170, "Carré", bold=True) + rc(150, 70, 110, 70, fill="#f7d9cf") + t(205, 170, "Rectangle", bold=True) +
         pg([(290, 140), (350, 140), (320, 60)], fill="#d9f0d0") + t(320, 170, "Triangle", bold=True) + ci(430, 100, 40, fill="#f3e6a0") + t(430, 170, "Cercle", bold=True))
    return svg(480, 200, c, "Les figures géométriques")


def numeration():
    c = ""
    for i, (nom, v) in enumerate((("Centaines", "C"), ("Dizaines", "D"), ("Unités", "U"))):
        c += rc(60 + i * 120, 60, 110, 120, fill=SOFT) + t(115 + i * 120, 50, nom, bold=True) + t(115 + i * 120, 130, ("3", "5", "7")[i], size=44, bold=True)
    c += t(240, 215, "357 = 3 centaines + 5 dizaines + 7 unités", size=13) + t(240, 235, "300 + 50 + 7", size=13)
    return svg(480, 250, c, "Centaines, dizaines et unités")


def circuit():
    c = (rc(100, 60, 280, 150, fill="none") + rc(170, 50, 24, 20, fill="#fff", col="#fff", sw=0) + ln(176, 48, 176, 72, w=3) + ln(188, 56, 188, 66, w=3) + t(182, 38, "Pile", bold=True) +
         ci(380, 135, 22, fill="#fff") + ln(366, 121, 394, 149) + ln(394, 121, 366, 149) + t(380, 180, "Lampe", bold=True) +
         ln(100, 145, 100, 120, col="#fff", w=6) + ln(100, 125, 125, 105, w=2) + ci(100, 130, 3, fill=INK) + t(70, 150, "Interrupteur", size=11, anchor="end") +
         t(240, 250, "Le courant circule de la borne + vers la borne - : le circuit doit être fermé.", size=12))
    return svg(480, 270, c, "Un circuit électrique simple")


def chaine_alimentaire():
    c = ""
    for i, (nom, col) in enumerate((("Herbe", "#9bd08a"), ("Criquet", "#d7e08a"), ("Lézard", "#c8d9a0"), ("Aigle", "#c9b49a"))):
        x = 20 + i * 115
        c += rc(x, 80, 95, 60, fill=col, r=8) + t(x + 47, 116, nom, bold=True)
        if i < 3: c += ln(x + 96, 110, x + 112, 110, w=2) + pg([(x + 118, 110), (x + 108, 104), (x + 108, 116)], fill=INK)
    c += t(240, 180, "producteur  →  consommateur 1  →  consommateur 2  →  consommateur 3", size=11) + t(240, 200, "La flèche signifie « est mangé par ».", size=12)
    return svg(480, 220, c, "Une chaîne alimentaire de savane")


def corps_humain():
    c = (ci(240, 50, 28, fill="#f2d3b3") + rc(205, 80, 70, 110, fill="#cfe3f7", r=14) + rc(150, 85, 50, 20, fill="#f2d3b3", r=8) + rc(280, 85, 50, 20, fill="#f2d3b3", r=8) +
         rc(212, 192, 24, 90, fill="#f2d3b3", r=8) + rc(244, 192, 24, 90, fill="#f2d3b3", r=8) +
         lab(240, 40, "Tête", 360, 30) + lab(240, 85, "Cou", 360, 70) + lab(240, 130, "Tronc", 360, 130) + lab(330, 95, "Bras", 400, 100) + lab(224, 245, "Jambe", 90, 260, "end") +
         lab(176, 95, "Main", 90, 100, "end"))
    return svg(480, 300, c, "Le corps humain : segments principaux")


def cellules():
    c = (el(130, 130, 90, 70, fill="#fdf1d6") + ci(130, 130, 22, fill="#e6a8c8") + lab(130, 130, "Noyau", 300, 80) + lab(100, 100, "Cytoplasme", 300, 125) + lab(200, 130, "Membrane", 300, 170) +
         t(130, 225, "Cellule animale", bold=True) +
         rc(20, 250, 220, 120, fill="#e9f5df", sw=3) + rc(26, 256, 208, 108, fill="#f5fbe9", sw=1) + ci(100, 310, 18, fill="#e6a8c8") + el(180, 285, 14, 8, fill="#5fbf6a") + el(185, 335, 14, 8, fill="#5fbf6a") +
         rc(130, 295, 38, 30, fill="#d6ecf7") + lab(100, 310, "Noyau", 300, 270) + lab(150, 310, "Vacuole", 300, 310) + lab(185, 285, "Chloroplaste", 300, 350) + lab(234, 362, "Paroi", 300, 392, "start") +
         t(130, 392, "Cellule végétale", bold=True))
    return svg(480, 410, c, "Cellule animale et cellule végétale")


def digestif():
    c = (pa("M240,40 L240,90", w=6) + t(300, 50, "Bouche et œsophage", anchor="start", size=11) + pa("M240,90 C300,100 300,150 250,160", fill="#f2c2c2", w=2) + t(320, 130, "Estomac", anchor="start", size=11) +
         pa("M250,160 C190,170 190,200 250,205 C310,210 300,240 240,245 C190,250 200,275 250,280", w=8, col="#e0a070") + t(110, 215, "Intestin grêle", anchor="end", size=11) +
         pa("M320,170 L320,290 L180,290", w=10, col="#b88a60") + t(340, 235, "Gros intestin", anchor="start", size=11) +
         el(190, 120, 30, 18, fill="#c9835c") + t(110, 125, "Foie", anchor="end", size=11) + t(240, 330, "Le trajet des aliments : bouche → œsophage → estomac → intestin grêle → gros intestin", size=11))
    return svg(480, 350, c, "L'appareil digestif (schéma simplifié)")


def repere():
    c = ln(60, 220, 440, 220, w=2) + ln(240, 30, 240, 250, w=2)
    for i in range(-5, 6):
        x = 240 + 30 * i
        c += ln(x, 214, x, 226, w=1) + (t(x, 240, str(i), size=10) if i else "")
        y = 220 - 30 * i
        c += ln(234, y, 246, y, w=1) + (t(228, y + 4, str(i), size=10, anchor="end") if i else "")
    c += ln(90, 310 - 100, 390, 130 - 100, col=ACC, w=2.5) + t(380, 108, "y = ax + b", col=ACC, anchor="end", bold=True) + ci(240, 190, 4, fill=ACC2) + t(256, 188, "(0 ; b)", size=11, anchor="start")
    return svg(480, 270, c + t(240, 265, "Droite de fonction affine dans un repère orthonormé", size=11), "Repère cartésien et droite")


def thales():
    A, B, C, M, N = (240, 40), (80, 250), (400, 250), (160, 145), (320, 145)
    c = pg([A, B, C], fill="#eef6ff") + ln(*M, *N, col=ACC2, w=2.5) + "".join(ci(p[0], p[1], 3.5, fill=INK) + t(p[0] + dx, p[1] + dy, s, bold=True) for p, s, dx, dy in
        ((A, "A", 0, -10), (B, "B", -12, 12), (C, "C", 12, 12), (M, "M", -14, 4), (N, "N", 14, 4)))
    return svg(480, 300, c + t(240, 285, "(MN) // (BC)  alors  AM/AB = AN/AC = MN/BC", size=12, bold=True), "Théorème de Thalès")


def pythagore():
    c = pg([(150, 220), (150, 100), (270, 220)], fill="#eef6ff") + pg([(150, 220), (150, 100), (30, 100), (30, 220)], fill="#d9f0d0") + pg([(150, 220), (270, 220), (270, 340), (150, 340)], fill="#f7d9cf")
    c += pg([(150, 100), (270, 220), (350, 140), (230, 20)], fill="#f6efc0") + t(90, 165, "AB²") + t(210, 285, "AC²") + t(250, 120, "BC²") + rc(150, 205, 15, 15, fill="none", sw=1.2)
    return svg(480, 360, c + t(300, 270, "BC² = AB² + AC²", bold=True, anchor="start") + t(300, 290, "(triangle rectangle en A)", size=11, anchor="start"), "Théorème de Pythagore")


def systeme_solaire():
    c = ci(40, 110, 32, fill="#f7d94a", col="#e0b400") + t(40, 160, "Soleil", size=10)
    x = 80
    for nom, r, col in (("Mercure", 4, "#aaa"), ("Vénus", 7, "#e6c27a"), ("Terre", 8, "#4a90d9"), ("Mars", 6, "#c0623e"), ("Jupiter", 20, "#d9b38c"), ("Saturne", 17, "#e0cf9a"), ("Uranus", 11, "#9fd6df"), ("Neptune", 11, "#4a6fd9")):
        x += r + 14
        c += ci(x, 110, r, fill=col) + t(x, 150 + (16 if nom in ("Vénus", "Mars", "Saturne", "Neptune") else 0), nom, size=10)
        x += r
    return svg(480, 200, c + t(240, 30, "Le Soleil et les huit planètes (tailles et distances non à l'échelle)", size=11), "Le système solaire")


def photosynthese():
    c = (pa("M240,300 L240,150", w=6, col="#2a8a3c") + pa("M240,200 Q330,150 380,190 Q330,240 240,225", fill="#6cc27a") + pa("M240,170 Q160,120 110,160 Q160,200 240,195", fill="#6cc27a") +
         ln(60, 40, 150, 120, col="#e0b400", w=3) + t(60, 30, "Lumière du soleil", anchor="start") + ln(400, 70, 330, 160, w=2) + t(410, 65, "CO2 (air)", anchor="start") +
         ln(240, 340, 240, 305, w=2, col="#2a6fa8") + t(240, 355, "Eau et sels minéraux (par les racines)", size=11) + ln(380, 205, 440, 240, col=ACC, w=2) + t(444, 255, "O2", anchor="end") +
         t(240, 390, "Eau + CO2 + lumière → glucose + O2", bold=True))
    return svg(480, 410, c, "La photosynthèse")


def coeur():
    c = (rc(180, 80, 120, 140, fill="#f7d3d3", r=40) + ln(240, 80, 240, 220, w=2) + ln(180, 150, 300, 150, w=2) + t(210, 120, "OD", size=11) + t(270, 120, "OG", size=11) + t(210, 190, "VD", size=11) + t(270, 190, "VG", size=11) +
         t(240, 245, "O : oreillette ; V : ventricule ; D : droite ; G : gauche", size=11) + t(380, 100, "Sang riche en O2 →", size=11, col=ACC2, anchor="start") + t(40, 100, "← Sang pauvre en O2", size=11, col="#2a6fa8", anchor="start"))
    return svg(480, 270, c, "Le cœur et la circulation du sang")


# (id, titre, cycle, matière, légende, fonction)
SCHEMAS = [
    ("carte-departements", "Le Bénin : départements et chefs-lieux", "Primaire et secondaire", "Histoire-Géographie", "Retrouver chaque département et son chef-lieu ; la capitale est Porto-Novo, la capitale économique Cotonou.", carte_departements),
    ("carte-voisins", "Le Bénin et ses pays voisins", "Primaire et secondaire", "Histoire-Géographie", "Au nord : Niger et Burkina Faso ; à l'ouest : Togo ; à l'est : Nigéria ; au sud : océan Atlantique.", carte_voisins),
    ("carte-climats", "Climats et végétation du Bénin", "Secondaire", "Histoire-Géographie", "Trois grandes zones climatiques du sud au nord, avec savane et forêts.", carte_climats),
    ("carte-parcs", "Parcs nationaux et villes principales", "Primaire et secondaire", "Histoire-Géographie", "Pendjari et W, deux réserves de la biosphère ; quelques villes repères.", carte_parcs),
    ("carte-relief", "Relief et cours d'eau", "Secondaire", "Histoire-Géographie", "Chaîne de l'Atacora, plateaux, côte lagunaire, fleuves Ouémé, Mono et Niger.", carte_relief),
    ("drapeau", "Le drapeau du Bénin", "Primaire", "Éducation sociale", "Vert (espérance), jaune (richesses), rouge (courage).", drapeau),
    ("rose-vents", "Les points cardinaux", "Primaire", "Géographie", "S'orienter avec le soleil : Est (lever), Ouest (coucher).", rose_vents),
    ("plante", "Les parties d'une plante", "Primaire", "Sciences d'observation", "Racines, tige, feuilles, fleur.", plante),
    ("cycle-eau", "Le cycle de l'eau", "Primaire et secondaire", "Sciences", "Évaporation, condensation, précipitations, ruissellement.", cycle_eau),
    ("corps", "Le corps humain", "Primaire", "Sciences d'observation", "Tête, cou, tronc, membres.", corps_humain),
    ("chaine", "Une chaîne alimentaire de savane", "Primaire et secondaire", "Sciences", "Qui mange qui : producteur et consommateurs.", chaine_alimentaire),
    ("circuit", "Un circuit électrique simple", "Primaire et secondaire", "Sciences", "Pile, interrupteur et lampe dans un circuit fermé.", circuit),
    ("fractions", "Les fractions", "Primaire", "Mathématiques", "Représenter 1/2, 1/4, 3/4, 2/3.", fractions),
    ("numeration", "Centaines, dizaines et unités", "Primaire", "Mathématiques", "Décomposer un nombre.", numeration),
    ("figures", "Les figures géométriques", "Primaire", "Mathématiques", "Carré, rectangle, triangle, cercle.", figures),
    ("systeme-solaire", "Le système solaire", "Secondaire", "Sciences", "Le Soleil et les huit planètes.", systeme_solaire),
    ("cellules", "Cellule animale et cellule végétale", "Secondaire", "SVT", "Comparer les deux cellules.", cellules),
    ("digestif", "L'appareil digestif", "Secondaire", "SVT", "Le trajet des aliments.", digestif),
    ("coeur", "Le cœur", "Secondaire", "SVT", "Quatre cavités : deux oreillettes, deux ventricules.", coeur),
    ("photosynthese", "La photosynthèse", "Secondaire", "SVT", "Comment la plante fabrique sa matière.", photosynthese),
    ("repere", "Repère et droite d'une fonction affine", "Secondaire", "Mathématiques", "y = ax + b, ordonnée à l'origine b.", repere),
    ("thales", "Le théorème de Thalès", "Secondaire", "Mathématiques", "Configuration du triangle avec une droite parallèle.", thales),
    ("pythagore", "Le théorème de Pythagore", "Secondaire", "Mathématiques", "Les carrés construits sur les côtés d'un triangle rectangle.", pythagore),
]
