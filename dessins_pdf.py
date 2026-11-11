# -*- coding: utf-8 -*-
"""v1.32 — Dessins au trait (même jeu que les applications web : outils/icones/icones.js) pour les documents PDF :
fiches de préparation (matière, rubriques), sans émoji ni image tierce. Tracés dans une grille 24 × 24 :
chemins SVG séparés par « | », « c:cx,cy,r » cercle, « r:x,y,l,h,rayon » rectangle arrondi."""
import logo_ecole as _LE

DESSINS = {
    "livre": "M4 5h5a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H4z|M20 5h-5a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h6z",
    "calcul": "r:5,3,14,18,2|r:8,6,8,4,0.5|M8.5 13.5h.01|M12 13.5h.01|M15.5 13.5h.01|M8.5 17h.01|M12 17h.01|M15.5 17h.01",
    "monde": "c:12,12,9|M3 12h18|M12 3c3 3.5 3 14.5 0 18|M12 3c-3 3.5-3 14.5 0 18",
    "science": "M9 3h6|M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3|M7.5 15h9",
    "ballon": "c:12,12,9|M12 8l3.3 2.4-1.3 3.9h-4l-1.3-3.9z|M12 3v5|M21 10l-5.7.4|M3 10l5.7.4|M16.8 19.3l-2.8-5|M7.2 19.3l2.8-5",
    "image": "r:3,4,18,16,1.5|c:9,9.5,1.8|M3 17l5-5 4 4 3-3 6 6",
    "etiquette": "M3 12V4h8l10 10-8 8z|c:7.5,8.5,1.5",
    "dossier": "M3 6h6l2 2h10v11H3z",
    "classeur": "M3 8h18v12H3z|M5 8V5h5l2 3|M7 12h10|M7 16h6",
    "horloge": "c:12,12,9|M12 7v5l3 2",
    "cible": "c:12,12,9|c:12,12,5|c:12,12,1.2",
    "puzzle": "M4 8h4a2 2 0 1 1 4 0h4v4a2 2 0 1 1 0 4v4h-4a2 2 0 1 0-4 0H4v-4a2 2 0 1 0 0-4z",
    "groupe": "c:9,8,3|M3.5 19c.6-3.4 3-5 5.5-5s4.9 1.6 5.5 5|c:16.5,9,2.5|M15 14c3 0 5 1.5 5.5 4.5",
    "outils": "M14.5 6.5a4 4 0 0 1-5 5L4 17l3 3 5.5-5.5a4 4 0 0 0 5-5l-2.5 2.5-2-2z",
    "valider-cercle": "c:12,12,9|M7.5 12.3l3 3 6-6.3",
    "fleche-droite": "M4 12h15|M13 6l6 6-6 6",
    "cerveau": "M12 5a3 3 0 0 0-5.5 1.5A3 3 0 0 0 4 11a3 3 0 0 0 1.5 5.5A3 3 0 0 0 12 19z|M12 5a3 3 0 0 1 5.5 1.5A3 3 0 0 1 20 11a3 3 0 0 1-1.5 5.5A3 3 0 0 1 12 19|M12 5v14",
    "voir": "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z|c:12,12,3",
    "document": "M6 3h8l4 4v14H6z|M14 3v4h4|M9 12h6|M9 16h6",
    "etoile": "M12 3l2.6 5.6 6.1.6-4.6 4.1 1.3 6L12 16.4l-5.4 2.9 1.3-6-4.6-4.1 6.1-.6z",
}
# couleurs et dessin par matière (spécification commune « Fiches, logos, lis-moi »)
MATIERES = {"francais": ("#1F4E79", "livre"), "maths": ("#B54708", "calcul"), "es": ("#067647", "monde"),
            "est": ("#6941C6", "science"), "eps": ("#C11574", "ballon"), "ea": ("#0E7090", "image")}
RUBRIQUES = {"intitule": "etiquette", "sous_matiere": "dossier", "unite": "classeur", "duree": "horloge", "cd": "cible", "ct": "puzzle",
             "contenus": "livre", "objectifs": "cible", "strategies": "groupe", "materiel": "outils", "deroulement": "horloge",
             "evaluation": "valider-cercle", "projection": "fleche-droite", "je_retiens": "cerveau", "observations": "voir"}


def couleur_matiere(m):
    return MATIERES.get(m or "", ("#1F4E79", "document"))[0]


def dessin_matiere(m):
    return MATIERES.get(m or "", ("#1F4E79", "document"))[1]


def dessiner(c, nom, x, y, taille, couleur="#1F4E79", epaisseur=1.7):
    """Dessin « nom » sur le canevas ReportLab, coin inférieur gauche (x, y), carré de « taille » points."""
    from reportlab.lib import colors
    d = DESSINS.get(nom)
    if not d:
        return
    k = taille / 24.0
    c.saveState()
    c.translate(x, y + taille)
    c.scale(k, -k)
    c.setStrokeColor(colors.HexColor(couleur))
    c.setLineWidth(epaisseur)
    c.setLineCap(1)
    c.setLineJoin(1)
    for t in d.split("|"):
        if t.startswith("c:"):
            a, b, r = (float(v) for v in t[2:].split(","))
            c.circle(a, b, r, stroke=1, fill=0)
        elif t.startswith("r:"):
            v = [float(z) for z in t[2:].split(",")]
            c.roundRect(v[0], v[1], v[2], v[3], v[4] if len(v) > 4 else 0, stroke=1, fill=0)
        else:
            for poly in _LE.chemin_points(t):
                if len(poly) < 2:
                    continue
                p = c.beginPath()
                p.moveTo(*poly[0])
                for pt in poly[1:]:
                    p.lineTo(*pt)
                c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


def flowable(nom, taille=12, couleur="#1F4E79"):
    from reportlab.platypus import Flowable

    class _D(Flowable):
        def wrap(self, *_):
            return taille, taille

        def draw(self):
            dessiner(self.canv, nom, 0, 0, taille, couleur)
    return _D()
