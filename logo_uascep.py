# -*- coding: utf-8 -*-
"""v1.25 — Logo de l'UASCEP (même dessin que le module commun : outils/uascep/uascep.js, UASCEP.logoSvg ; référence
livrables/logo_uascep/fabriquer.py).

Anneau extérieur (couleur c1) : « UASCEP » sur l'arc du haut ; sous le sigle, sur un petit arc, la définition
(« UNION DES ASSOCIATIONS SPORTIVES ET CULTURELLES DES ÉCOLES PRIMAIRES », initiales U A S C E P en couleur c2) ;
sur l'arc du bas, le texte modifiable (commune, zone, école…) en c2 ; cercle intérieur blanc (filet c2) avec un
coureur d'endurance (silhouette c1, traits de vitesse c2) sur une piste (c3).

Trois rendus du même dessin : SVG (texte sur arc), PDF (ReportLab, lettre par lettre) et PNG (Pillow, police Vera de
ReportLab) — aucune dépendance supplémentaire.
"""
import math
import os
import re
from xml.sax.saxutils import escape

DEFINITION = "Union des Associations Sportives et Culturelles des Écoles Primaires"
DEFAUT = {"haut": "UASCEP", "definition": DEFINITION, "bas": "", "c1": "#1F4E79", "c2": "#E8B10E", "c3": "#1B8A3C"}
PETITS_MOTS = {"des", "de", "du", "et", "la", "le", "les", "d", "l", "à", "au", "aux", "en"}
# arcs (repère SVG 400 × 400, y vers le bas) : (rayon, angle de départ, sens) ; angles en degrés, 0 = droite, 90 = haut
ARC_HAUT = (150, 180.0, -1)       # M 50 200 A 150 150 0 0 1 350 200 (par le haut)
ARC_DEF = (122, 200.0, -1)        # M 85.4 241.7 A 122 122 0 1 1 314.6 241.7 (grand arc par le haut)
ARC_DEF_LONG = 240.0              # longueur angulaire de l'arc de la définition
ARC_BAS = (160, 180.0, 1)         # M 40 200 A 160 160 0 0 0 360 200 (par le bas)
SEGMENTS = [  # coureur (repère du groupe, avant la mise à l'échelle 0,86 centrée)
    ("c1", 20, [(206, 140), (190, 196)]), ("c1", 11, [(204, 148), (228, 168), (248, 156)]), ("c1", 11, [(200, 150), (178, 166), (162, 154)]),
    ("c1", 13, [(190, 196), (218, 214), (214, 248)]), ("c1", 13, [(190, 196), (170, 226), (140, 230)]), ("c1", 8, [(214, 248), (230, 250)]),
    ("c2", 5, [(150, 140), (130, 140)]), ("c2", 5, [(146, 160), (120, 160)]), ("c2", 5, [(150, 180), (132, 180)])]


def params(d=None):
    p = dict(DEFAUT)
    for k, v in (d or {}).items():
        if v not in (None, "") and k in p:
            p[k] = str(v)
    for k in ("c1", "c2", "c3"):
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", p[k]):
            p[k] = DEFAUT[k]
    return p


def texte_bas(niveau, libelle):
    """Texte de l'arc du bas pré-rempli d'après l'entité (même règle que UASCEP.texteLogo)."""
    lib = (libelle or "").strip()
    if niveau == "ZONE":
        m = re.search(r"(\d+)", lib)
        return f"ZONE PÉDAGOGIQUE {m.group(1)}" if m else lib.upper()
    if niveau == "UP":
        return (lib if lib.upper().startswith("UP") else "UP " + lib).upper()
    if niveau == "CS":
        nom = re.sub(r"(?i)^(circonscription scolaire|cs)\s*(de|d')?\s*", "", lib).strip() or lib
        return f"COMMUNE DE {nom.upper()}"
    return lib.upper()


def initiales(definition):
    """[(mot, initiale en couleur ?)] : initiale colorée pour les mots « pleins » (pas des, de, et…)."""
    out = []
    for m in (definition or "").split():
        out.append((m.upper(), m.strip("'’").lower() not in PETITS_MOTS))
    return out


# ------------------------------------------------------------------ SVG
def _def_svg(definition, c2):
    parts = []
    for mot, plein in initiales(definition):
        parts.append(f'<tspan fill="{c2}" font-weight="900">{escape(mot[0])}</tspan>{escape(mot[1:])}' if plein else escape(mot))
    return " ".join(parts)


def _piste_points(x0, y0, cx, cy, x1, y1, n=24):
    return [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1)
            for t in (i / n for i in range(n + 1))]


def taille_bas(bas):
    n = len(bas or "")
    return 30 if n <= 18 else 26 if n <= 24 else 22


def svg(d=None, taille=400):
    p = params(d)
    fb = taille_bas(p["bas"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="{taille}" height="{taille}" role="img" aria-label="Logo UASCEP {escape(p['bas'])}">
<defs>
 <path id="arcH" d="M 50 200 A 150 150 0 0 1 350 200"/>
 <path id="arcD" d="M 85.4 241.7 A 122 122 0 1 1 314.6 241.7"/>
 <path id="arcB" d="M 40 200 A 160 160 0 0 0 360 200"/>
</defs>
<circle cx="200" cy="200" r="196" fill="{p['c1']}"/>
<circle cx="200" cy="200" r="186" fill="none" stroke="{p['c2']}" stroke-width="4"/>
<circle cx="200" cy="200" r="100" fill="#fff" stroke="{p['c2']}" stroke-width="6"/>
<text font-family="Arial Black, Arial, sans-serif" font-weight="900" font-size="52" letter-spacing="8" fill="#fff" text-anchor="middle"><textPath href="#arcH" startOffset="50%">{escape(p['haut'])}</textPath></text>
<text font-family="Arial, sans-serif" font-weight="700" font-size="10.6" letter-spacing="0.3" fill="#fff" text-anchor="middle"><textPath href="#arcD" startOffset="50%">{_def_svg(p['definition'], p['c2'])}</textPath></text>
<text font-family="Arial, sans-serif" font-weight="700" font-size="{fb}" letter-spacing="3" fill="{p['c2']}" text-anchor="middle"><textPath href="#arcB" startOffset="50%">{escape(p['bas'])}</textPath></text>
<circle cx="38" cy="200" r="7" fill="{p['c2']}"/><circle cx="362" cy="200" r="7" fill="{p['c2']}"/>
<g transform="translate(200 200) scale(0.86) translate(-200 -196)">
<path d="M 118 262 Q 200 238 284 262" fill="none" stroke="{p['c3']}" stroke-width="7" stroke-linecap="round"/>
<path d="M 128 276 Q 200 256 274 276" fill="none" stroke="{p['c3']}" stroke-width="4" stroke-linecap="round" opacity=".6"/>
<g fill="none" stroke="{p['c1']}" stroke-linecap="round" stroke-linejoin="round">
 <circle cx="214" cy="118" r="15" fill="{p['c1']}" stroke="none"/>
 <path d="M 206 140 L 190 196" stroke-width="20"/>
 <path d="M 204 148 L 228 168 L 248 156" stroke-width="11"/>
 <path d="M 200 150 L 178 166 L 162 154" stroke-width="11"/>
 <path d="M 190 196 L 218 214 L 214 248" stroke-width="13"/>
 <path d="M 190 196 L 170 226 L 140 230" stroke-width="13"/>
 <path d="M 214 248 L 230 250" stroke-width="8"/>
</g>
<path d="M 150 140 L 130 140 M 146 160 L 120 160 M 150 180 L 132 180" stroke="{p['c2']}" stroke-width="5" stroke-linecap="round"/>
</g>
</svg>'''


# ------------------------------------------------------------------ géométrie commune (PDF, PNG)
def _largeur(txt, police, taille):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(txt, police, taille)


def _lettres_arc(texte, couleurs, police, taille, espacement, arc, longueur_arc=None):
    """[(car, x, y, rotation en degrés (sens horaire, repère SVG), couleur)] — texte centré sur l'arc."""
    rayon, depart, sens = arc
    larg = [_largeur(ch, police, taille) + espacement for ch in texte]
    total = sum(larg) - espacement
    long_arc = math.radians(longueur_arc if longueur_arc else 180.0) * rayon
    s = (long_arc - total) / 2
    out = []
    for ch, w, coul in zip(texte, larg, couleurs):
        mil = s + (w - espacement) / 2
        phi = math.radians(depart) + sens * mil / rayon     # angle mathématique (y vers le haut)
        x = 200 + rayon * math.cos(phi)
        y = 200 - rayon * math.sin(phi)
        # tangente dans le sens de lecture : haut (sens -1) -> lettre tournée de (90° - φ) ; bas (sens +1) -> (270° - φ)
        rot = (90 - math.degrees(phi)) if sens < 0 else (270 - math.degrees(phi))
        out.append((ch, x, y, rot, coul))
        s += w
    return out


def primitives(d=None):
    """Description du logo en primitives (repère SVG) : cercles, traits, lettres."""
    p = params(d)
    k = 0.86

    def g(x, y):
        return 200 + k * (x - 200), 200 + k * (y - 196)
    prim = {"cercles": [(200, 200, 196, p["c1"], None, 0), (200, 200, 186, None, p["c2"], 4), (200, 200, 100, "#FFFFFF", p["c2"], 6),
                        (38, 200, 7, p["c2"], None, 0), (362, 200, 7, p["c2"], None, 0)],
            "traits": [], "lettres": []}
    for (x0, y0, cx, cy, x1, y1, w, op) in ((118, 262, 200, 238, 284, 262, 7, 1.0), (128, 276, 200, 256, 274, 276, 4, 0.6)):
        prim["traits"].append((p["c3"], w * k, [g(*pt) for pt in _piste_points(x0, y0, cx, cy, x1, y1)], op))
    tx, ty = g(214, 118)
    prim["cercles"].append((tx, ty, 15 * k, p["c1"], None, 0))
    for coul, w, pts in SEGMENTS:
        prim["traits"].append((p[coul], w * k, [g(*pt) for pt in pts], 1.0))
    h = p["haut"]
    prim["lettres"] += [("Helvetica-Bold", 52) + x for x in _lettres_arc(h, ["#FFFFFF"] * len(h), "Helvetica-Bold", 52, 8, ARC_HAUT)]
    dtxt, dcoul = [], []
    for i, (mot, plein) in enumerate(initiales(p["definition"])):
        if i:
            dtxt.append(" ")
            dcoul.append("#FFFFFF")
        for j, ch in enumerate(mot):
            dtxt.append(ch)
            dcoul.append(p["c2"] if (plein and j == 0) else "#FFFFFF")
    prim["lettres"] += [("Helvetica-Bold", 10.6) + x for x in _lettres_arc("".join(dtxt), dcoul, "Helvetica-Bold", 10.6, 0.3, ARC_DEF, ARC_DEF_LONG)]
    fb = taille_bas(p["bas"])
    prim["lettres"] += [("Helvetica-Bold", fb) + x for x in _lettres_arc(p["bas"], [p["c2"]] * len(p["bas"]), "Helvetica-Bold", fb, 3, ARC_BAS)]
    return prim


def dessiner(c, x, y, taille, d=None):
    """Dessine le logo sur un canevas ReportLab : (x, y) = coin inférieur gauche, taille en points."""
    from reportlab.lib import colors
    pr = primitives(d)
    e = taille / 400.0
    c.saveState()
    c.translate(x, y + taille)
    c.scale(e, -e)                      # repère SVG (y vers le bas)
    for cx, cy, r, fond, trait, w in pr["cercles"]:
        if fond:
            c.setFillColor(colors.HexColor(fond))
        if trait:
            c.setStrokeColor(colors.HexColor(trait))
            c.setLineWidth(w)
        c.circle(cx, cy, r, stroke=1 if trait else 0, fill=1 if fond else 0)
    c.setLineCap(1)
    c.setLineJoin(1)
    for coul, w, pts, op in pr["traits"]:
        c.setStrokeColor(colors.HexColor(coul), alpha=op)
        c.setLineWidth(w)
        pth = c.beginPath()
        pth.moveTo(*pts[0])
        for pt in pts[1:]:
            pth.lineTo(*pt)
        c.drawPath(pth, stroke=1, fill=0)
    for police, tl, ch, lx, ly, rot, coul in pr["lettres"]:
        if ch == " ":
            continue
        c.saveState()
        c.translate(lx, ly)
        c.rotate(rot)
        c.scale(1, -1)                  # lettres à l'endroit
        c.setFillColor(colors.HexColor(coul))
        c.setFont(police, tl)
        c.drawCentredString(0, 0, ch)
        c.restoreState()
    c.restoreState()


def flowable(d=None, taille=60, image=None):
    """Flowable ReportLab du logo (image importée si fournie : ImageReader)."""
    from reportlab.platypus import Flowable

    class _Logo(Flowable):
        def wrap(self, *_):
            return taille, taille

        def draw(self):
            if image is not None:
                self.canv.drawImage(image, 0, 0, taille, taille, preserveAspectRatio=True, mask="auto")
            else:
                dessiner(self.canv, 0, 0, taille, d)
    return _Logo()


def _police_png(taille):
    from PIL import ImageFont
    try:
        import reportlab
        chemin = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "VeraBd.ttf")
        return ImageFont.truetype(chemin, int(round(taille)))
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def png(d=None, taille=800):
    """PNG (octets) du logo, rendu avec Pillow (suréchantillonné puis réduit)."""
    import io
    from PIL import Image, ImageDraw
    pr = primitives(d)
    sur = 2
    T = taille * sur
    e = T / 400.0
    im = Image.new("RGBA", (T, T), (255, 255, 255, 0))
    dr = ImageDraw.Draw(im)
    for cx, cy, r, fond, trait, w in pr["cercles"]:
        box = [(cx - r) * e, (cy - r) * e, (cx + r) * e, (cy + r) * e]
        dr.ellipse(box, fill=fond, outline=trait, width=int(round(w * e)) if trait else 0)
    for coul, w, pts, op in pr["traits"]:
        rgb = tuple(int(coul[i:i + 2], 16) for i in (1, 3, 5))
        col = rgb + (int(255 * op),)
        calque = Image.new("RGBA", im.size, (0, 0, 0, 0))
        dl = ImageDraw.Draw(calque)
        ww = max(1, int(round(w * e)))
        pp = [(x * e, y * e) for x, y in pts]
        dl.line(pp, fill=col, width=ww, joint="curve")
        for x, y in (pp[0], pp[-1]):
            dl.ellipse([x - ww / 2, y - ww / 2, x + ww / 2, y + ww / 2], fill=col)
        im = Image.alpha_composite(im, calque)
    for police, tl, ch, lx, ly, rot, coul in pr["lettres"]:
        if ch == " ":
            continue
        f = _police_png(tl * e)
        bb = f.getbbox(ch)
        w_, h_ = bb[2] - bb[0] + 4, int(tl * e * 1.4)
        lettre = Image.new("RGBA", (w_, h_), (0, 0, 0, 0))
        ImageDraw.Draw(lettre).text((w_ / 2, h_ * 0.72), ch, font=f, fill=coul, anchor="ms")
        lettre = lettre.rotate(-rot, resample=Image.BICUBIC, expand=True)
        # point d'ancrage (ligne de base) : centre de l'image tournée, décalé vers la ligne de base
        dy = h_ * 0.72 - h_ / 2
        a = math.radians(rot)
        ox, oy = -dy * math.sin(a), dy * math.cos(a)
        im.alpha_composite(lettre, (int(lx * e - lettre.width / 2 - ox), int(ly * e - lettre.height / 2 - oy)))
    im = im.resize((taille, taille), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
