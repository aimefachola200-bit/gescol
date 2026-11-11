# -*- coding: utf-8 -*-
"""Prépare une application web (MEMP CP, CS Pobè, Mon école…) pour l'APK Android ou l'installateur Windows :
recopie l'application dans « www », fabrique les icônes et affiche la version.

  python preparer.py --source DOSSIER --cible android|windows [--exclure ecole,tools]
"""
import argparse
import datetime
import os
import re
import shutil

ICI = os.path.dirname(os.path.abspath(__file__))
TOUJOURS_EXCLUS = {".git", ".github", "tools", "node_modules", "serveur.js", "demarrer-windows.bat", "demarrer.sh"}


def version(source):
    try:  # application qui donne sa version dans version.txt (ÉduGestion Pro…)
        t = open(os.path.join(source, "version.txt"), encoding="utf-8").read().strip()
        if re.fullmatch(r"[0-9]+(\.[0-9]+)*", t):
            return t
    except OSError:
        pass
    try:
        t = open(os.path.join(source, "js", "config.js"), encoding="utf-8").read()
        m = re.search(r"version:\s*'([0-9.]+)'", t)
        if m:
            return m.group(1)
    except OSError:
        pass
    return datetime.date.today().strftime("%Y.%m.%d").replace(".0", ".")


def icones(source, cible):
    from PIL import Image
    src = None
    for nom in ("icons/icon-512.png", "icons/icon-maskable-512.png", "icons/icon-192.png"):
        p = os.path.join(source, nom)
        if os.path.exists(p):
            src = Image.open(p).convert("RGBA")
            break
    if src is None:
        return
    if cible == "android":
        for d, s in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
            dossier = os.path.join(ICI, "android", "app", "src", "main", "res", f"mipmap-{d}")
            os.makedirs(dossier, exist_ok=True)
            src.resize((s, s), Image.LANCZOS).save(os.path.join(dossier, "ic_launcher.png"))
    else:
        src.resize((256, 256), Image.LANCZOS).save(os.path.join(ICI, "windows", "memp_cp.ico"),
                                                   sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--cible", choices=["android", "windows"], required=True)
    ap.add_argument("--exclure", default="")
    a = ap.parse_args()
    exclus = TOUJOURS_EXCLUS | {x.strip() for x in a.exclure.split(",") if x.strip()}
    www = (os.path.join(ICI, "android", "app", "src", "main", "assets", "www") if a.cible == "android"
           else os.path.join(ICI, "windows", "www"))
    shutil.rmtree(www, ignore_errors=True)
    shutil.copytree(a.source, www, ignore=lambda d, noms: [n for n in noms if os.path.samefile(d, a.source) and (n in exclus or n.endswith(".zip"))
                                                            or n in (".git", ".github")])
    assert os.path.exists(os.path.join(www, "index.html")), "index.html absent"
    icones(a.source, a.cible)
    print(version(a.source))


if __name__ == "__main__":
    main()
