# -*- coding: utf-8 -*-
"""v1.32 — Logo et devise de l'école, créés automatiquement (même dessin que le module commun des applications web :
outils/lots/logo-ecole.js, LogoEcole.svg ; spécification outils/lots/spec.md, « Fiches, logos, lis-moi »).

Deux formes :
  * « rond » : disque c1, filet c2, nom de l'école en majuscules sur l'arc du haut (blanc), devise sur l'arc du bas (c2),
    disque blanc au centre avec un symbole au trait (c1) et les initiales (c3) ;
  * « ecusson » : écusson c1 bordé c2, bandeau c2 portant le nom (c1), médaillon blanc (symbole + initiales), ruban blanc
    portant la devise.
Symboles originaux dessinés au trait : livre, plume, soleil, épi, palmier, colombe, globe, flambeau, étoile, mains unies,
ou les initiales seules. Trois rendus du même dessin : SVG, PDF (ReportLab) et PNG (Pillow) — aucune dépendance de plus.
"""
import json
import math
import re
from xml.sax.saxutils import escape

import logo_uascep as LU

COULEURS = {"c1": "#1F4E79", "c2": "#E8B10E", "c3": "#1B8A3C"}
SYMBOLES = {
    "livre": ("Livre ouvert", "M3 6c3-1.5 6-1.5 9 .5c3-2 6-2 9-.5v12c-3-1.5-6-1.5-9 .5c-3-2-6-2-9-.5z|M12 6.5v12"),
    "plume": ("Plume", "M19 4c-7 1-11 6-12 13|M19 4c-1 5-4 9-9 11|M7 17l-2 3|M11 9l3 1|M9 12l3 1"),
    "soleil": ("Soleil levant", "M4 17h16|M7 17a5 5 0 0 1 10 0|M12 8V5|M6.5 10.5L4.5 8.5|M17.5 10.5l2-2|M3 13.5h2|M19 13.5h2"),
    "epi": ("Épi de maïs", "M12 21V8|M12 8c-2-2-2-4 0-6c2 2 2 4 0 6|M12 12c-3-1-4-3-4-5|M12 12c3-1 4-3 4-5|M12 16c-3-1-5-3-5-5|M12 16c3-1 5-3 5-5"),
    "palmier": ("Palmier", "M12 21c0-5 .5-9 1-12|M13 9c-2-3-5-4-8-3|M13 9c2-3 5-4 8-3|M13 9c-3-1-6 0-8 3|M13 9c3-1 6 0 8 3|M13 9c0-3-1-5-3-6|M8 21h9"),
    "colombe": ("Colombe", "M4 13c3 0 5-1 7-4c1 3 4 5 9 5c-2 3-5 5-9 5c-3 0-5-2-7-6z|M11 9c-1-3 0-5 2-6c0 2 1 4 3 5|M20 14l2-1|M8 16l-2 3"),
    "globe": ("Globe", "c:12,12,8.5|M3.5 12h17|M12 3.5c-3 3-3 14 0 17|M12 3.5c3 3 3 14 0 17|M5.5 7.5h13|M5.5 16.5h13"),
    "flambeau": ("Flambeau du savoir", "M10 21h4l1-9H9z|M8 12h8|M12 10c-3-2-2-5 0-8c1 2 3 3 3 5s-1 3-3 3z"),
    "etoile": ("Étoile", "M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z"),
    "mains": ("Mains unies", "M3 14l4-4 3 2 3-3 3 2 5-3|M3 14l5 5h6l7-7|M10 12l3 3|M13 9l4 4"),
}
DEVISES = ["Travail – Discipline – Réussite", "Savoir – Discipline – Excellence", "Apprendre pour servir", "Union – Travail – Progrès",
           "L'excellence par l'effort", "Éduquer pour bâtir l'avenir", "Lire, écrire, compter, réussir",
           "Ensemble pour la réussite de chaque enfant", "Discipline – Travail – Succès", "Le savoir, notre richesse"]
MOTS_VIDES = {"EPP", "EPM", "EPV", "EP", "EM", "EMP", "EPRIV", "ECOLE", "ÉCOLE", "COMPLEXE", "SCOLAIRE", "GROUPE", "CS", "DE", "DU",
              "DES", "LA", "LE", "LES", "L", "D", "ET", "PRIMAIRE", "MATERNELLE", "PUBLIQUE", "PRIVEE", "PRIVÉE", "SAINT", "SAINTE"}
FORMES = ("rond", "ecusson")


def initiales_de(nom):
    mots = [m for m in re.split(r"\s+", re.sub(r"[’'/().,-]", " ", str(nom or ""))) if m and m.upper() not in MOTS_VIDES]
    base = mots or str(nom or "École").split()
    return ("".join(m[0] for m in base[:3]).upper() or "É")[:4]


def lire_cfg(valeur):
    if isinstance(valeur, dict):
        return dict(valeur)
    try:
        v = json.loads(valeur or "{}")
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def params(nom, devise="", cfg=None):
    """Paramètres complets du logo à partir du nom, de la devise et du réglage enregistré (logo_cfg)."""
    cfg = lire_cfg(cfg)
    c = dict(COULEURS)
    for k in ("c1", "c2", "c3"):
        v = (cfg.get("couleurs") or {}).get(k) if isinstance(cfg.get("couleurs"), dict) else cfg.get(k)
        if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            c[k] = v
    sym = cfg.get("symbole")
    sym = sym if sym in SYMBOLES or sym == "initiales" else "livre"
    ini = re.sub(r"[^A-Za-zÀ-ÿ0-9]", "", str(cfg.get("initiales") or "")).upper()[:4] or initiales_de(nom)
    dev = "" if cfg.get("devise_sur_logo") is False else str(devise or "")
    return {"nom": str(nom or "École").upper(), "devise": dev, "initiales": ini, "symbole": sym,
            "forme": cfg.get("forme") if cfg.get("forme") in FORMES else "rond", **c}


# ------------------------------------------------------------------ tracés des symboles (chemins SVG -> polylignes)
def _jetons(d):
    return re.findall(r"[MmLlHhVvCcSsQqAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?", d)


def _arc(x1, y1, rx, ry, phi, fa, fs, x2, y2, n=14):
    """Arc elliptique SVG -> points (conversion standard centre / angles)."""
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p ** 2) / rx ** 2 + (y1p ** 2) / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2
    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a
    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    out = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        out.append((cx + rx * math.cos(t) * cp - ry * math.sin(t) * sp, cy + rx * math.cos(t) * sp + ry * math.sin(t) * cp))
    return out


def chemin_points(d, n=10):
    """Chemin SVG (M L H V C S Q A Z, absolu ou relatif) -> liste de polylignes [(x, y), …]."""
    tj = _jetons(d)
    polys, cur, x, y, sx, sy, cmd, prev_c = [], [], 0.0, 0.0, 0.0, 0.0, None, None
    i = 0

    def num():
        nonlocal i
        v = float(tj[i])
        i += 1
        return v
    while i < len(tj):
        if re.fullmatch(r"[A-Za-z]", tj[i]):
            cmd = tj[i]
            i += 1
            if cmd in "Zz":
                if cur:
                    cur.append((sx, sy))
                x, y = sx, sy
                prev_c = None
                continue
        rel = cmd.islower()
        C = cmd.upper()
        if C == "M":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            if len(cur) > 1:
                polys.append(cur)
            cur, sx, sy = [(x, y)], x, y
            cmd = "l" if rel else "L"
            prev_c = None
        elif C == "L":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            cur.append((x, y))
            prev_c = None
        elif C == "H":
            v = num()
            x = x + v if rel else v
            cur.append((x, y))
            prev_c = None
        elif C == "V":
            v = num()
            y = y + v if rel else v
            cur.append((x, y))
            prev_c = None
        elif C in "CS":
            if C == "C":
                a = [num() for _ in range(6)]
                if rel:
                    a = [a[0] + x, a[1] + y, a[2] + x, a[3] + y, a[4] + x, a[5] + y]
                x1, y1, x2, y2, x3, y3 = a
            else:
                a = [num() for _ in range(4)]
                if rel:
                    a = [a[0] + x, a[1] + y, a[2] + x, a[3] + y]
                x1, y1 = (2 * x - prev_c[0], 2 * y - prev_c[1]) if prev_c else (x, y)
                x2, y2, x3, y3 = a
            for k in range(1, n + 1):
                t = k / n
                u = 1 - t
                cur.append((u ** 3 * x + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3,
                            u ** 3 * y + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3))
            prev_c = (x2, y2)
            x, y = x3, y3
        elif C == "Q":
            a = [num() for _ in range(4)]
            if rel:
                a = [a[0] + x, a[1] + y, a[2] + x, a[3] + y]
            x1, y1, x2, y2 = a
            for k in range(1, n + 1):
                t = k / n
                u = 1 - t
                cur.append((u * u * x + 2 * u * t * x1 + t * t * x2, u * u * y + 2 * u * t * y1 + t * t * y2))
            x, y = x2, y2
            prev_c = None
        elif C == "A":
            rx, ry, phi, fa, fs, nx, ny = (num() for _ in range(7))
            if rel:
                nx, ny = x + nx, y + ny
            cur += _arc(x, y, rx, ry, phi, int(fa), int(fs), nx, ny)
            x, y = nx, ny
            prev_c = None
        else:
            i += 1
    if len(cur) > 1:
        polys.append(cur)
    return polys


def symbole_traits(sym, couleur, cx, cy, r):
    """Traits du symbole (grille 24 × 24) placés dans le médaillon de centre (cx, cy) et de rayon r."""
    if sym not in SYMBOLES:
        return [], []
    ox, oy, k = cx - r * 0.62, cy - r * 0.78, r * 1.24 / 24
    traits, cercles = [], []
    for t in SYMBOLES[sym][1].split("|"):
        if t.startswith("c:"):
            a, b, rr = (float(v) for v in t[2:].split(","))
            cercles.append((ox + a * k, oy + b * k, rr * k, None, couleur, 1.6 * k))
            continue
        for poly in chemin_points(t):
            traits.append((couleur, 1.6 * k, [(ox + px * k, oy + py * k) for px, py in poly], 1.0))
    return traits, cercles


# ------------------------------------------------------------------ SVG
def _svg_symbole(p, cx, cy, r):
    ini = escape(p["initiales"])
    if p["symbole"] in SYMBOLES:
        d = "".join(f'<circle cx="{t[2:].split(",")[0]}" cy="{t[2:].split(",")[1]}" r="{t[2:].split(",")[2]}"/>' if t.startswith("c:")
                    else f'<path d="{t}"/>' for t in SYMBOLES[p["symbole"]][1].split("|"))
        return (f'<g transform="translate({cx - r * 0.62:.1f} {cy - r * 0.78:.1f}) scale({r * 1.24 / 24:.3f})"><g fill="none" stroke="{p["c1"]}" '
                f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{d}</g></g>'
                f'<text x="{cx}" y="{cy + r * 0.78:.1f}" text-anchor="middle" font-family="Arial Black,Arial,sans-serif" font-weight="900" '
                f'font-size="{r * 0.36:.1f}" fill="{p["c3"]}">{ini}</text>')
    fs = r * (0.66 if len(p["initiales"]) > 2 else 0.86)
    return (f'<text x="{cx}" y="{cy + r * 0.3:.1f}" text-anchor="middle" font-family="Arial Black,Arial,sans-serif" font-weight="900" '
            f'font-size="{fs:.1f}" fill="{p["c1"]}">{ini}</text>')


def taille_nom(nom, forme="rond"):
    if forme == "ecusson":   # le nom tient dans le bandeau (236 unités de large)
        base = max(16.0, min(34.0, 520 / max(8, len(nom))))
        w = LU._largeur(nom, "Helvetica-Bold", 1.0) or 1
        return max(11.0, min(base, 236 / w))
    return max(18.0, min(40.0, 760 / max(10, len(nom))))


def taille_devise(devise, forme="rond"):
    if forme == "ecusson":
        return max(11.0, min(17.0, 420 / max(10, len(devise))))
    return max(12.0, min(24.0, 640 / max(12, len(devise))))


ECUSSON = "M60 40h280v150c0 95-70 150-140 180C130 340 60 285 60 190z"
ECUSSON_FILET = "M75 55h250v135c0 82-60 130-125 157C135 320 75 272 75 190z"
RUBAN = "M40 300q160 40 320 0v34q-160 40-320 0z"


def svg(p, taille=400):
    nom, dev = p["nom"], p["devise"]
    aria = escape(f"Logo {nom}")
    if p["forme"] == "ecusson":
        fs = taille_nom(nom, "ecusson")
        rub = ""
        if dev:
            rub = (f'<path d="{RUBAN}" fill="#fff" stroke="{p["c2"]}" stroke-width="3"/><path id="rub" d="M48 322q152 36 304 0" fill="none"/>'
                   f'<text font-family="Arial,sans-serif" font-weight="700" font-size="{taille_devise(dev, "ecusson"):.1f}" fill="{p["c1"]}" '
                   f'text-anchor="middle"><textPath href="#rub" startOffset="50%">{escape(dev)}</textPath></text>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="{taille}" height="{taille}" role="img" aria-label="{aria}">'
                f'<path d="{ECUSSON}" fill="{p["c1"]}"/><path d="{ECUSSON_FILET}" fill="none" stroke="{p["c2"]}" stroke-width="5"/>'
                f'<rect x="75" y="62" width="250" height="52" fill="{p["c2"]}"/>'
                f'<text x="200" y="{88 + fs * 0.36:.1f}" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="{fs:.1f}" '
                f'fill="{p["c1"]}">{escape(nom)}</text><circle cx="200" cy="205" r="72" fill="#fff" stroke="{p["c2"]}" stroke-width="5"/>'
                f'{_svg_symbole(p, 200, 205, 66)}{rub}</svg>')
    fsn = taille_nom(nom)
    bas = (f'<text font-family="Arial,sans-serif" font-weight="700" font-size="{taille_devise(dev):.1f}" fill="{p["c2"]}" text-anchor="middle">'
           f'<textPath href="#arcB" startOffset="50%">{escape(dev.upper())}</textPath></text>') if dev else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="{taille}" height="{taille}" role="img" aria-label="{aria}">'
            '<defs><path id="arcH" d="M52 200A148 148 0 0 1 348 200"/><path id="arcB" d="M44 200A156 156 0 0 0 356 200"/></defs>'
            f'<circle cx="200" cy="200" r="196" fill="{p["c1"]}"/><circle cx="200" cy="200" r="186" fill="none" stroke="{p["c2"]}" stroke-width="4"/>'
            f'<circle cx="200" cy="200" r="104" fill="#fff" stroke="{p["c2"]}" stroke-width="6"/>'
            f'<text font-family="Arial,sans-serif" font-weight="700" font-size="{fsn:.1f}" letter-spacing="2" fill="#fff" text-anchor="middle">'
            f'<textPath href="#arcH" startOffset="50%">{escape(nom)}</textPath></text>{bas}'
            f'<circle cx="34" cy="200" r="6" fill="{p["c2"]}"/><circle cx="366" cy="200" r="6" fill="{p["c2"]}"/>'
            f'{_svg_symbole(p, 200, 200, 96)}</svg>')


# ------------------------------------------------------------------ primitives communes (PDF, PNG)
def _texte_droit(texte, police, taille, cx, y, couleur):
    """Lettres d'un texte horizontal centré sur cx (ligne de base y, repère SVG)."""
    larg = [LU._largeur(ch, police, taille) for ch in texte]
    x = cx - sum(larg) / 2
    out = []
    for ch, w in zip(texte, larg):
        out.append((police, taille, ch, x + w / 2, y, 0.0, couleur))
        x += w
    return out


def _lettres_ruban(texte, police, taille, couleur):
    """Devise sur la courbe du ruban (quadratique M48 322 q152 36 304 0)."""
    pts = [((1 - t) ** 2 * 48 + 2 * (1 - t) * t * 200 + t * t * 352, (1 - t) ** 2 * 322 + 2 * (1 - t) * t * 358 + t * t * 322)
           for t in (i / 200 for i in range(201))]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    larg = [LU._largeur(ch, police, taille) for ch in texte]
    s = (cum[-1] - sum(larg)) / 2
    out = []
    for ch, w in zip(texte, larg):
        m = s + w / 2
        j = next((k for k, v in enumerate(cum) if v >= m), len(cum) - 1)
        j = max(1, j)
        (x0, y0), (x1, y1) = pts[j - 1], pts[j]
        rot = math.degrees(math.atan2(y1 - y0, x1 - x0))
        out.append((police, taille, ch, x1, y1 + taille * 0.35, rot, couleur))
        s += w
    return out


def primitives(p):
    prim = {"cercles": [], "traits": [], "lettres": [], "surfaces": []}
    ini = p["initiales"]
    if p["forme"] == "ecusson":
        prim["surfaces"].append((chemin_points(ECUSSON)[0], p["c1"], None, 0))
        prim["surfaces"].append((chemin_points(ECUSSON_FILET)[0], None, p["c2"], 5))
        prim["surfaces"].append(([(75, 62), (325, 62), (325, 114), (75, 114)], p["c2"], None, 0))
        fs = taille_nom(p["nom"], "ecusson")
        prim["lettres"] += _texte_droit(p["nom"], "Helvetica-Bold", fs, 200, 88 + fs * 0.36, p["c1"])
        prim["cercles"].append((200, 205, 72, "#FFFFFF", p["c2"], 5))
        cx, cy, r = 200, 205, 66
        if p["devise"]:
            prim["surfaces"].append((chemin_points(RUBAN)[0], "#FFFFFF", p["c2"], 3))
            prim["lettres"] += _lettres_ruban(p["devise"], "Helvetica-Bold", taille_devise(p["devise"], "ecusson"), p["c1"])
    else:
        prim["cercles"] += [(200, 200, 196, p["c1"], None, 0), (200, 200, 186, None, p["c2"], 4), (200, 200, 104, "#FFFFFF", p["c2"], 6),
                            (34, 200, 6, p["c2"], None, 0), (366, 200, 6, p["c2"], None, 0)]
        fsn = taille_nom(p["nom"])
        prim["lettres"] += [("Helvetica-Bold", fsn) + x for x in LU._lettres_arc(p["nom"], ["#FFFFFF"] * len(p["nom"]), "Helvetica-Bold", fsn, 2,
                                                                                (148, 180.0, -1))]
        if p["devise"]:
            d = p["devise"].upper()
            fd = taille_devise(d)
            prim["lettres"] += [("Helvetica-Bold", fd) + x for x in LU._lettres_arc(d, [p["c2"]] * len(d), "Helvetica-Bold", fd, 0, (156, 180.0, 1))]
        cx, cy, r = 200, 200, 96
    if p["symbole"] in SYMBOLES:
        tr, ce = symbole_traits(p["symbole"], p["c1"], cx, cy, r)
        prim["traits"] += tr
        prim["cercles"] += ce
        prim["lettres"] += _texte_droit(ini, "Helvetica-Bold", r * 0.36, cx, cy + r * 0.78, p["c3"])
    else:
        prim["lettres"] += _texte_droit(ini, "Helvetica-Bold", r * (0.66 if len(ini) > 2 else 0.86), cx, cy + r * 0.3, p["c1"])
    return prim


def dessiner(c, x, y, taille, p):
    """Logo sur un canevas ReportLab, (x, y) = coin inférieur gauche."""
    from reportlab.lib import colors
    pr = primitives(p)
    e = taille / 400.0
    c.saveState()
    c.translate(x, y + taille)
    c.scale(e, -e)
    c.setLineCap(1)
    c.setLineJoin(1)
    for pts, fond, trait, w in pr["surfaces"]:
        pth = c.beginPath()
        pth.moveTo(*pts[0])
        for pt in pts[1:]:
            pth.lineTo(*pt)
        pth.close()
        if fond:
            c.setFillColor(colors.HexColor(fond))
        if trait:
            c.setStrokeColor(colors.HexColor(trait))
            c.setLineWidth(w)
        c.drawPath(pth, stroke=1 if trait else 0, fill=1 if fond else 0)
    for cx, cy, r, fond, trait, w in pr["cercles"]:
        if fond:
            c.setFillColor(colors.HexColor(fond))
        if trait:
            c.setStrokeColor(colors.HexColor(trait))
            c.setLineWidth(w)
        c.circle(cx, cy, r, stroke=1 if trait else 0, fill=1 if fond else 0)
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
        c.scale(1, -1)
        c.setFillColor(colors.HexColor(coul))
        c.setFont(police, tl)
        c.drawCentredString(0, 0, ch)
        c.restoreState()
    c.restoreState()


def png(p, taille=600):
    """PNG (octets) du logo, rendu avec Pillow (suréchantillonné puis réduit)."""
    import io
    from PIL import Image, ImageDraw
    pr = primitives(p)
    sur = 2
    T = taille * sur
    e = T / 400.0
    im = Image.new("RGBA", (T, T), (255, 255, 255, 0))
    for pts, fond, trait, w in pr["surfaces"]:
        dr = ImageDraw.Draw(im)
        pp = [(px * e, py * e) for px, py in pts]
        if fond:
            dr.polygon(pp, fill=fond)
        if trait:
            dr.line(pp + [pp[0]], fill=trait, width=max(1, int(round(w * e))), joint="curve")
    dr = ImageDraw.Draw(im)
    for cx, cy, r, fond, trait, w in pr["cercles"]:
        box = [(cx - r) * e, (cy - r) * e, (cx + r) * e, (cy + r) * e]
        dr.ellipse(box, fill=fond, outline=trait, width=max(1, int(round(w * e))) if trait else 0)
    for coul, w, pts, op in pr["traits"]:
        ww = max(1, int(round(w * e)))
        pp = [(px * e, py * e) for px, py in pts]
        dr.line(pp, fill=coul, width=ww, joint="curve")
        for px, py in (pp[0], pp[-1]):
            dr.ellipse([px - ww / 2, py - ww / 2, px + ww / 2, py + ww / 2], fill=coul)
    for police, tl, ch, lx, ly, rot, coul in pr["lettres"]:
        if ch == " ":
            continue
        f = LU._police_png(tl * e)
        bb = f.getbbox(ch)
        w_, h_ = bb[2] - bb[0] + 4, int(tl * e * 1.4)
        lettre = Image.new("RGBA", (max(1, w_), max(1, h_)), (0, 0, 0, 0))
        ImageDraw.Draw(lettre).text((w_ / 2, h_ * 0.72), ch, font=f, fill=coul, anchor="ms")
        lettre = lettre.rotate(-rot, resample=Image.BICUBIC, expand=True)
        dy = h_ * 0.72 - h_ / 2
        a = math.radians(rot)
        ox, oy = -dy * math.sin(a), dy * math.cos(a)
        im.alpha_composite(lettre, (int(lx * e - lettre.width / 2 - ox), int(ly * e - lettre.height / 2 - oy)))
    im = im.resize((taille, taille), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
