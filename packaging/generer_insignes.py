# -*- coding: utf-8 -*-
"""Génère static/icons/insignes/<edition>-<taille>.png et <edition>.ico à partir de static/icons/icon-1024.png.
Lancer depuis la racine :  python packaging/generer_insignes.py"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
import insignes as I  # noqa: E402

ICONES = os.path.join(RACINE, "static", "icons")
SORTIE = os.path.join(ICONES, "insignes")


def main():
    os.makedirs(SORTIE, exist_ok=True)
    base = os.path.join(ICONES, "icon-1024.png")
    for cle in I.INSIGNES:
        for nom, t in I.TAILLES.items():
            I.dessiner(base, cle, t).save(os.path.join(SORTIE, f"{cle}-{nom}.png"))
        grand = I.dessiner(base, cle, 256)
        grand.save(os.path.join(SORTIE, f"{cle}.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(len(I.INSIGNES), "insignes dans", SORTIE)


if __name__ == "__main__":
    main()
