# -*- coding: utf-8 -*-
"""v2.4.9 : fabrique MAJ-CODE.zip + MAJ-CODE.json (mise à jour automatique des applications installées).

Contenu : code/ (modules .py + modeles/) et web/ (templates + static). Lancé par GitHub Actions avant la publication ;
les deux fichiers sont joints à la version « latest » : les applications installées les téléchargent seules."""
import glob
import hashlib
import json
import os
import re
import sys
import zipfile

RACINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SORTIE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RACINE, "sortie_maj")
EXCLUS = {"gescol_serveur.py", "scolaris_serveur.py", "wsgi.py", "demo.py", "amorcage.py"}


def version():
    m = re.search(r'^VERSION = "([^"]+)"', open(os.path.join(RACINE, "config.py"), encoding="utf-8").read(), re.M)
    return m.group(1)


def ajouter_dossier(z, src, dest):
    for dossier, _, fichiers in os.walk(src):
        if "__pycache__" in dossier:
            continue
        for f in fichiers:
            if f.endswith((".pyc", ".orig", ".avant")):
                continue
            p = os.path.join(dossier, f)
            z.write(p, os.path.join(dest, os.path.relpath(p, src)).replace(os.sep, "/"))


def main():
    os.makedirs(SORTIE, exist_ok=True)
    zp = os.path.join(SORTIE, "MAJ-CODE.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(glob.glob(os.path.join(RACINE, "*.py"))):
            if os.path.basename(f) not in EXCLUS:
                z.write(f, "code/" + os.path.basename(f))
        ajouter_dossier(z, os.path.join(RACINE, "modeles"), "code/modeles")
        ajouter_dossier(z, os.path.join(RACINE, "templates"), "web/templates")
        ajouter_dossier(z, os.path.join(RACINE, "static"), "web/static")
    h = hashlib.sha256(open(zp, "rb").read()).hexdigest()
    info = {"version": version(), "sha256": h, "taille": os.path.getsize(zp)}
    json.dump(info, open(os.path.join(SORTIE, "MAJ-CODE.json"), "w"), indent=1)
    print(info)


if __name__ == "__main__":
    main()
