# -*- coding: utf-8 -*-
"""Application CP (MEMP — République du Bénin) pour Windows.

L'application web est embarquée (dossier « www ») et servie sur l'ordinateur lui-même (http://127.0.0.1:PORT) ;
elle s'ouvre dans une fenêtre d'application de Microsoft Edge (ou Chrome), avec un profil propre à MEMP CP :
les données restent sur le PC et fonctionnent sans Internet. Conception : Maître Aimé FACHOLA."""
import functools
import json
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
WWW = os.path.join(BASE, "www")
try:
    with open(os.path.join(BASE, "variante.json"), encoding="utf-8") as f:
        VARIANTE = json.load(f)
except OSError:
    VARIANTE = {}
NOM = VARIANTE.get("nom", "MEMP CP")
PORT = int(VARIANTE.get("port", 8871))
DONNEES = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), NOM.replace(" ", "_"))


DERNIER_SIGNE = [time.time()]
SIGNE_JS = (b"<script>(function(){function v(){fetch('/__vivant',{cache:'no-store'}).catch(function(){});}"
            b"v();setInterval(v,30000);})();</script>")


class Gestion(SimpleHTTPRequestHandler):
    extensions_map = dict(SimpleHTTPRequestHandler.extensions_map, **{
        ".js": "text/javascript", ".mjs": "text/javascript", ".webmanifest": "application/manifest+json",
        ".json": "application/json", ".svg": "image/svg+xml", ".wasm": "application/wasm"})

    def do_GET(self):
        DERNIER_SIGNE[0] = time.time()
        chemin = self.path.split("?")[0]
        if chemin == "/__vivant":                      # la fenêtre de l'application est ouverte
            self.send_response(204)
            self.end_headers()
            return
        if chemin.endswith("/") or chemin.endswith(".html"):   # toute page (accueil, espace intégré…) : signal « fenêtre ouverte »
            fichier = self.translate_path(chemin)
            if os.path.isdir(fichier):
                fichier = os.path.join(fichier, "index.html")
            try:
                with open(fichier, "rb") as f:
                    corps = f.read()
                corps = corps.replace(b"</body>", SIGNE_JS + b"</body>", 1) if b"</body>" in corps else corps + SIGNE_JS
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)
                return
            except OSError:
                pass
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass


class Serveur(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):   # programme sans console : aucune sortie d'erreur
        pass


def port_libre(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def navigateur():
    """Edge ou Chrome (mode application) ; None si aucun n'est trouvé."""
    candidats = []
    for racine in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if racine:
            candidats += [os.path.join(racine, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(racine, "Google", "Chrome", "Application", "chrome.exe")]
    return next((c for c in candidats if os.path.exists(c)), None)


def main():
    adresse = f"http://127.0.0.1:{PORT}/index.html"
    serveur = None
    if port_libre(PORT):
        serveur = Serveur(("127.0.0.1", PORT), functools.partial(Gestion, directory=WWW))
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
    exe = navigateur()
    if exe:
        os.makedirs(DONNEES, exist_ok=True)
        subprocess.Popen([exe, f"--app={adresse}", f"--user-data-dir={os.path.join(DONNEES, 'navigateur')}",
                          "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"])
    else:
        webbrowser.open(adresse)
    if not serveur:          # déjà lancé : la fenêtre s'ouvre sur le serveur existant
        return
    # Le serveur reste actif tant que la fenêtre de l'application est ouverte (signal toutes les 30 s) ;
    # il s'arrête 30 minutes après la fermeture de la dernière fenêtre (relancer l'icône le redémarre).
    # (Edge rend la main tout de suite à son lanceur : on ne peut pas attendre la fin de son processus.)
    while time.time() - DERNIER_SIGNE[0] < 1800:
        time.sleep(10)
    serveur.shutdown()


if __name__ == "__main__":
    main()
