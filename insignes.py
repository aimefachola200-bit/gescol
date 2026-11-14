# -*- coding: utf-8 -*-
"""v2.5.1 : insignes (pastilles de couleur) qui différencient les applications jumelles : icône du bureau, de l'installateur, de l'application
installée (PWA) et pastille dans l'en-tête. Les applications du secondaire ont une pastille carrée aux angles arrondis, celles du primaire une
pastille ronde. Fonctions de dessin : utilisées par packaging/generer_insignes.py (Pillow) ; les icônes produites sont livrées dans static/icons/insignes."""
# clé : (lettre, couleur RVB, forme, libellé)
INSIGNES = {
    "privee": ("É", (200, 140, 0), "rond", "École privée"),
    "publique": ("P", (0, 135, 81), "rond", "École publique"),
    "cs": ("C", (191, 90, 0), "rond", "Circonscription scolaire"),
    "ddemp": ("D", (122, 31, 162), "rond", "Direction départementale"),
    "enseignant": ("E", (0, 121, 107), "rond", "Enseignant"),
    "sec_privee": ("S", (21, 71, 160), "carre", "Secondaire privé"),
    "sec_publique": ("S", (0, 105, 92), "carre", "Secondaire public"),
    "sec_cs": ("I", (106, 27, 154), "carre", "Secondaire : circonscription"),
    "sec_ddestfp": ("D", (183, 28, 28), "carre", "Secondaire : direction départementale"),
}
TAILLES = {"icon-192": 192, "icon-512": 512, "apple-touch-icon": 180, "favicon-32": 32}


def insigne_de(edition):
    return edition if edition in INSIGNES else "privee"


def dessiner(base_png, cle, taille=None):
    """Retourne l'image Pillow de l'icône de base avec la pastille de l'édition `cle` (en haut à droite : le nom GESCOL/SCOLARIS en bas reste lisible)."""
    from PIL import Image, ImageDraw, ImageFont
    lettre, rvb, forme, _lib = INSIGNES[cle]
    im = Image.open(base_png).convert("RGBA")
    if taille:
        im = im.resize((taille, taille), Image.LANCZOS)
    w = im.size[0]
    d = ImageDraw.Draw(im)
    r = max(8, int(w * 0.36))
    x0, y0 = w - r - max(1, w // 40), max(1, w // 40)
    boite = [x0, y0, x0 + r, y0 + r]
    bord = max(1, w // 40)
    if forme == "rond":
        d.ellipse(boite, fill=rvb + (255,), outline=(255, 255, 255, 255), width=bord)
    else:
        d.rounded_rectangle(boite, radius=max(2, r // 5), fill=rvb + (255,), outline=(255, 255, 255, 255), width=bord)
    police = None
    for chemin in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                   "C:/Windows/Fonts/arialbd.ttf"):
        try:
            police = ImageFont.truetype(chemin, int(r * 0.66))
            break
        except OSError:
            continue
    if police is None:
        try:
            police = ImageFont.load_default(size=int(r * 0.66))
        except TypeError:
            police = None
    d.text((x0 + r / 2, y0 + r / 2 + r * 0.03), lettre, fill="white", anchor="mm", font=police)
    return im


def cle_courante():
    """Insigne de l'application en cours (selon l'édition installée)."""
    import config
    if config.secondaire():
        return {"privee": "sec_privee", "publique": "sec_publique", "cs": "sec_cs", "ddemp": "sec_ddestfp"}.get(config.EDITION, "sec_privee")
    return insigne_de(config.EDITION)
