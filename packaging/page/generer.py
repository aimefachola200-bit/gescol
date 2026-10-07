# -*- coding: utf-8 -*-
"""Page de téléchargement GESCOL (GitHub Pages) : un lien simple + QR codes pour installer sur Android, tablette et PC.

Les liens pointent vers la dernière version publiée (« releases/latest ») : ils ne changent jamais.
Utilisation : GITHUB_REPOSITORY=proprietaire/depot python packaging/page/generer.py site"""
import base64
import html
import os
import shutil
import sys

from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.abspath(os.path.join(ICI, "..", ".."))
sys.path.insert(0, RACINE)
import config  # noqa: E402

DEPOT = os.environ.get("GITHUB_REPOSITORY", "proprietaire/gescol")
PROPRIO, NOM = DEPOT.split("/", 1)
BASE = f"https://github.com/{DEPOT}/releases/latest/download"
PAGE = f"https://{PROPRIO.lower()}.github.io/{NOM}/"
GROUPES = [
    ("GESCOL — écoles privées", "Scolarité, paiements des parents, paie du personnel…", [
        ("autonome", "GESCOL-Autonome.apk", "Android autonome", "Fonctionne seul sur le téléphone ou la tablette, sans PC, sans Wi-Fi, sans Internet. Les données restent sur l'appareil."),
        ("connecte", "GESCOL.apk", "Android connecté", "Se connecte au serveur GESCOL de l'école (Wi-Fi) ou à la version en ligne : tout le monde partage les mêmes données. Convient aussi à GESCOL Public."),
        ("windows", "GESCOL-Installation.exe", "Windows (PC)", "Installe GESCOL sur un PC : il fonctionne seul et peut servir les tablettes du Wi-Fi."),
    ]),
    ("GESCOL Public — écoles publiques", "Cantine et subventions, dépenses, gestion de carrière, maître de semaine, visites de classe, "
     "patrimoine, fiches de recensement, rapports de rentrée et de fin d'année, documents de l'enseignant.", [
        ("autonome", "GESCOL-Public.apk", "Android autonome – GESCOL Public", "Application jumelle pour les écoles publiques, sans PC ni Internet. Elle s'installe à côté de GESCOL sans le remplacer."),
        ("windows", "GESCOL-Public-Installation.exe", "Windows (PC) – GESCOL Public", "Installe GESCOL Public sur un PC (données séparées de GESCOL, adresse http://localhost:5001)."),
    ]),
    ("Administration scolaire — Circonscription et DDEMP", "Tableaux de bord de la juridiction, statistiques des apprenants et des enseignants, "
     "CEP (taux par zone et par CS, prévisions, frais de relevés), carrière et retraites, visites des CP et CCS, fiches "
     "de recensement et rapports consolidés, attestations et certificats, transmissions des écoles.", [
        ("autonome", "GESCOL-Circonscription.apk", "Android – GESCOL Circonscription", "Pour le CCS, les CP et les chefs de division : reçoit les fichiers des écoles de la circonscription."),
        ("windows", "GESCOL-Circonscription-Installation.exe", "Windows – GESCOL Circonscription", "Installe l'application de la circonscription scolaire sur un PC (adresse http://localhost:5002)."),
        ("autonome", "GESCOL-DDEMP.apk", "Android – GESCOL DDEMP", "Pour la Direction départementale : rassemble les circonscriptions du département."),
        ("windows", "GESCOL-DDEMP-Installation.exe", "Windows – GESCOL DDEMP", "Installe l'application de la DDEMP sur un PC (adresse http://localhost:5003)."),
    ]),
]


def qr_svg(texte, taille=170):
    w = QrCodeWidget(texte)
    x0, y0, x1, y1 = w.getBounds()
    d = Drawing(taille, taille, transform=[taille / (x1 - x0), 0, 0, taille / (y1 - y0), 0, 0])
    d.add(w)
    svg = renderSVG.drawToString(d)
    return svg[svg.index("<svg"):]


def main(sortie):
    os.makedirs(sortie, exist_ok=True)
    shutil.copy(os.path.join(RACINE, "static", "icons", "icon-192.png"), os.path.join(sortie, "icone.png"))
    blocs = []
    for titre_groupe, texte_groupe, fichiers in GROUPES:
        cartes = []
        for cle, fichier, titre, texte in fichiers:
            lien = f"{BASE}/{fichier}"
            cartes.append(f"""
  <section class="carte{' principale' if cle == 'autonome' else ''}">
    <h2>{html.escape(titre)}</h2>
    <p>{html.escape(texte)}</p>
    <a class="bouton" href="{lien}">Télécharger</a>
    <details><summary>QR code</summary><div class="qr">{qr_svg(lien)}</div></details>
  </section>""")
        blocs.append(f"""<h2 class="groupe">{html.escape(titre_groupe)}</h2><p class="sous">{html.escape(texte_groupe)}</p>
<div class="grille">{''.join(cartes)}
</div>""")
    page = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Installer GESCOL</title><link rel="icon" href="icone.png">
<meta property="og:title" content="Installer GESCOL"><meta property="og:description" content="Gestion d'établissement scolaire – Android, tablette, PC">
<style>
:root{{--bleu:#1F4E79;--fond:#F4F6F9}}*{{box-sizing:border-box}}
body{{margin:0;font-family:"Segoe UI",Roboto,Arial,sans-serif;background:var(--fond);color:#1D2939}}
header{{background:var(--bleu);color:#fff;padding:28px 16px;text-align:center}}header img{{width:72px;height:72px;border-radius:16px}}
h1{{margin:10px 0 4px;font-size:26px}}header p{{margin:0;opacity:.85}}
main{{max-width:900px;margin:0 auto;padding:20px 16px 40px}}
.grille{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}}
.carte{{background:#fff;border:1px solid #D0D5DD;border-radius:14px;padding:18px}}.carte.principale{{border:2px solid var(--bleu)}}
.carte h2{{margin:0 0 6px;font-size:19px;color:var(--bleu)}}.carte p{{margin:0 0 14px;line-height:1.45}}
.bouton{{display:block;text-align:center;background:var(--bleu);color:#fff;text-decoration:none;padding:14px;border-radius:10px;font-weight:600;font-size:17px}}
details{{margin-top:10px}}summary{{cursor:pointer;color:var(--bleu)}}.qr{{text-align:center;padding-top:8px}}.qr svg{{max-width:170px;height:auto;shape-rendering:crispEdges}}.qr svg *{{shape-rendering:crispEdges;stroke:none}}
.etapes{{background:#fff;border:1px solid #D0D5DD;border-radius:14px;padding:6px 18px;margin-top:18px;line-height:1.55}}
h2.groupe{{color:var(--bleu);font-size:21px;margin:22px 0 2px}}p.sous{{margin:0 0 12px;color:#475467}}
.astuce{{background:#FFF8E6;border:1px solid #F5C451;border-radius:10px;padding:10px 14px}}
.partage{{margin-top:18px;text-align:center}}.partage .qr svg{{max-width:200px}}
footer{{text-align:center;color:#667085;font-size:13px;padding:0 16px 30px}}
</style></head><body>
<header><img src="icone.png" alt=""><h1>Installer GESCOL</h1><p>Gestion d'établissement scolaire · version {config.VERSION}</p></header>
<main>
{''.join(blocs)}
<div class="etapes">
  <h2 style="color:var(--bleu);font-size:18px">Installer sur Android ou tablette</h2>
  <ol>
    <li>Appuyez sur <b>Télécharger</b> (GESCOL ou GESCOL Public).</li>
    <li>Ouvrez le fichier téléchargé avec le <b>Gestionnaire de fichiers</b> (dossier « Téléchargements »).</li>
    <li>Si Android le demande : <b>Paramètres → Autoriser cette source</b>, puis revenez et appuyez sur <b>Installer</b>.
        Si Play Protect avertit : <b>Plus de détails → Installer quand même</b>.</li>
    <li>Ouvrez <b>GESCOL</b>. Première connexion : <b>admin / admin123</b>, puis choisissez votre mot de passe.</li>
  </ol>
  <p class="astuce"><b>Tecno, Infinix, itel :</b> si le fichier s'ouvre avec Word ou une autre application,
  ouvrez le <b>Gestionnaire de fichiers</b> → <b>Téléchargements</b>, appuyez longuement sur le fichier .apk →
  <b>Ouvrir avec</b> → <b>Programme d'installation</b>.</p>
  <p>Mise à jour : téléchargez à nouveau depuis cette page et installez par-dessus ; les données sont conservées.</p>
</div>
<div class="partage"><p>Partagez cette page : <b>{html.escape(PAGE)}</b></p><div class="qr">{qr_svg(PAGE, 200)}</div></div>
</main>
<footer>GESCOL {config.VERSION} — Conception : {html.escape(config.CONCEPTEUR)}</footer>
</body></html>"""
    with open(os.path.join(sortie, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print("Page générée :", os.path.join(sortie, "index.html"), "->", PAGE)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site")
