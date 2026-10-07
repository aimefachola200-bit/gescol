# -*- coding: utf-8 -*-
"""Prépare l'application Android autonome avant la fabrication (GitHub Actions ou Android Studio).

1. recopie le code Python de GESCOL dans app/src/main/python ;
2. recopie les gabarits et fichiers statiques dans app/src/main/assets/gescol_web ;
3. ajoute les bibliothèques Python « pures » (Flask, ReportLab, openpyxl…) sans leurs parties compilées
   (elles fonctionnent sans : MarkupSafe et charset-normalizer ont une version Python de secours).
   Pillow, seule bibliothèque compilée nécessaire, est installée par Chaquopy (voir app/build.gradle).

Utilisation : python3 packaging/android_autonome/preparer.py      (depuis la racine du projet ou d'ailleurs)
Option --edition publique|cs|ddemp : applications jumelles GESCOL Public, Circonscription, DDEMP.
Option --local : prendre les bibliothèques déjà installées sur cet ordinateur au lieu de les télécharger.
"""
import glob
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.abspath(os.path.join(ICI, "..", ".."))
PY = os.path.join(ICI, "app", "src", "main", "python")
WEB = os.path.join(ICI, "app", "src", "main", "assets", "gescol_web")

# modules GESCOL à ne pas embarquer (lanceur Windows, démo, point d'entrée hébergeur)
EXCLUS = {"gescol_serveur.py", "demo.py", "wsgi.py"}
# bibliothèques pures (nom pip, nom du paquet importé)
LIBS = [("flask", "flask"), ("werkzeug", "werkzeug"), ("jinja2", "jinja2"), ("markupsafe", "markupsafe"),
        ("itsdangerous", "itsdangerous"), ("click", "click"), ("blinker", "blinker"),
        ("reportlab", "reportlab"), ("charset-normalizer", "charset_normalizer"),
        ("openpyxl", "openpyxl"), ("et-xmlfile", "et_xmlfile")]
GARDER = {"gescol_android.py"}


def nettoyer():
    for nom in os.listdir(PY):
        if nom in GARDER:
            continue
        p = os.path.join(PY, nom)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    shutil.rmtree(WEB, ignore_errors=True)


def copier_gescol():
    for f in sorted(glob.glob(os.path.join(RACINE, "*.py"))):
        if os.path.basename(f) not in EXCLUS:
            shutil.copy2(f, PY)
    for d in ("templates", "static"):
        shutil.copytree(os.path.join(RACINE, d), os.path.join(WEB, d),
                        ignore=shutil.ignore_patterns("__pycache__", "*.ico"))


def sans_compile(dossier):
    """Supprime les modules compilés (.so / .pyd) : versions Python de secours utilisées sur Android."""
    for motif in ("**/*.so", "**/*.pyd", "**/*.dylib"):
        for f in glob.glob(os.path.join(dossier, motif), recursive=True):
            os.remove(f)


def telecharger():
    tmp = tempfile.mkdtemp()
    cmd = [sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:", "--dest", tmp,
           "--python-version", "3.11", "--implementation", "cp", "--platform", "manylinux2014_x86_64",
           "--platform", "manylinux_2_17_x86_64", "--platform", "any"] + [n for n, _ in LIBS]
    subprocess.check_call(cmd)
    for whl in glob.glob(os.path.join(tmp, "*.whl")):
        with zipfile.ZipFile(whl) as z:
            z.extractall(PY)
    shutil.rmtree(tmp)


def copier_local():
    for _, mod in LIBS:
        spec = importlib.util.find_spec(mod)
        if spec is None or not spec.submodule_search_locations:
            raise SystemExit(f"Bibliothèque absente sur cet ordinateur : {mod}")
        src = list(spec.submodule_search_locations)[0]
        shutil.copytree(src, os.path.join(PY, mod), ignore=shutil.ignore_patterns("__pycache__"))


def ecrire_edition():
    """--edition publique : application jumelle « GESCOL Public » (écoles publiques).
    Sans option : édition choisie dans Administration > Paramètres (écoles privées par défaut)."""
    edition = ""
    if "--edition" in sys.argv:
        edition = sys.argv[sys.argv.index("--edition") + 1].lower()
        if edition not in ("privee", "publique", "cs", "ddemp"):
            raise SystemExit("--edition : privee, publique, cs ou ddemp")
    with open(os.path.join(PY, "gescol_edition.py"), "w", encoding="utf-8") as f:
        f.write(f'# Écrit par preparer.py\nEDITION = "{edition}"\n')
    if edition in MARQUES:
        marquer_icones(*MARQUES[edition])
    return edition


# pastille de l'icône : lettre et couleur de chaque application jumelle
MARQUES = {"publique": ("P", (0, 135, 81, 255)), "cs": ("C", (191, 90, 0, 255)), "ddemp": ("D", (122, 31, 162, 255))}


def marquer_icones(lettre="P", couleur=(0, 135, 81, 255)):
    """Pastille de couleur avec une lettre pour distinguer les applications jumelles sur l'écran du téléphone."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow absent : icône inchangée")
        return
    for f in glob.glob(os.path.join(ICI, "app", "src", "main", "res", "mipmap-*", "ic_launcher.png")):
        im = Image.open(f).convert("RGBA")
        w, h = im.size
        r = max(6, w * 7 // 20)   # pastille en haut à droite (le nom GESCOL reste lisible)
        d = ImageDraw.Draw(im)
        d.ellipse([w - r, 0, w - 1, r - 1], fill=couleur, outline=(255, 255, 255, 255), width=max(1, w // 48))
        try:
            from PIL import ImageFont
            police = ImageFont.load_default(size=int(r * 0.7))
        except TypeError:
            police = None
        try:
            d.text((w - r / 2, r / 2), lettre, fill="white", anchor="mm", font=police)
        except ValueError:  # ancienne police bitmap : pas d'ancrage
            d.text((w - r * 0.6, r * 0.3), lettre, fill="white")
        im.save(f)


def main():
    os.makedirs(PY, exist_ok=True)
    nettoyer()
    copier_gescol()
    print("Édition :", ecrire_edition() or "au choix (Paramètres)")
    if "--local" in sys.argv:
        copier_local()
    else:
        telecharger()
    sans_compile(PY)
    for p in glob.glob(os.path.join(PY, "**", "__pycache__"), recursive=True):
        shutil.rmtree(p, ignore_errors=True)
    n = sum(len(f) for _, _, f in os.walk(PY))
    print(f"Prêt : {n} fichiers Python dans {PY}, gabarits dans {WEB}")


if __name__ == "__main__":
    main()
