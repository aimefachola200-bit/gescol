# -*- coding: utf-8 -*-
"""
GESCOL Serveur – lanceur Windows (petite fenêtre de contrôle).

Démarre GESCOL sur ce PC et affiche l'adresse (avec QR code) que les tablettes,
téléphones et autres PC de l'école ouvrent par le Wi-Fi. Fermer la fenêtre arrête GESCOL.
"""
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

def _port_defaut():
    """5000 GESCOL (privé), 5001 GESCOL Public, 5002 Circonscription, 5003 DDEMP : tous peuvent tourner sur le même PC."""
    try:
        import config
        return str(config.PORTS.get(config.EDITION_IMPOSEE, 5000))
    except Exception:  # noqa: BLE001
        return "5000"


PORT = int(os.environ.get("GESCOL_PORT") or _port_defaut())


def ip_locale():
    """Adresse IP de ce PC sur le réseau local (sans envoyer de données)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def port_occupe(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def matrice_qr(texte):
    from reportlab.graphics.barcode.qrencoder import QRCode, QRErrorCorrectLevel
    q = QRCode(None, QRErrorCorrectLevel.M)
    q.addData(texte)
    q.make()
    n = q.getModuleCount()
    return [[q.isDark(r, c) for c in range(n)] for r in range(n)]


def main():
    # Exécutable sans console : stdout/stderr n'existent pas, on les redirige.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    import tkinter as tk
    from tkinter import messagebox

    # Déjà lancé ? On ouvre simplement le navigateur.
    if port_occupe(PORT):
        webbrowser.open(f"http://localhost:{PORT}")
        return

    import config
    os.makedirs(config.INSTANCE_DIR, exist_ok=True)
    logging.basicConfig(filename=os.path.join(config.INSTANCE_DIR, "gescol_serveur.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("gescol")

    erreur = {"msg": None}

    def demarrer_serveur():
        try:
            import app as application
            application.servir(host="0.0.0.0", port=PORT)
        except Exception as e:  # noqa: BLE001
            log.exception("Arrêt du serveur")
            erreur["msg"] = str(e)

    threading.Thread(target=demarrer_serveur, daemon=True).start()

    ip = ip_locale()
    url_locale = f"http://localhost:{PORT}"
    url_reseau = f"http://{ip}:{PORT}"

    BLEU, FOND, TXT, GRIS, VERT, ROUGE = "#1F4E79", "#F4F6F9", "#1D2939", "#667085", "#1B7F3B", "#B42318"
    fen = tk.Tk()
    fen.title("GESCOL Serveur")
    fen.configure(bg=FOND)
    fen.resizable(False, False)
    ico = os.path.join(config.BASE_DIR, "static", "icons", "gescol.ico")
    if os.path.exists(ico):
        try:
            fen.iconbitmap(ico)
        except tk.TclError:
            pass

    entete = tk.Frame(fen, bg=BLEU)
    entete.pack(fill="x")
    tk.Label(entete, text="GESCOL Serveur", bg=BLEU, fg="white", font=("Segoe UI", 15, "bold"),
             padx=18, pady=10).pack(side="left")
    tk.Label(entete, text=f"v{config.VERSION}", bg=BLEU, fg="#DCE6F2", font=("Segoe UI", 9), padx=12).pack(side="right")

    corps = tk.Frame(fen, bg=FOND, padx=18, pady=14)
    corps.pack(fill="both")
    etat = tk.Label(corps, text="● Démarrage…", bg=FOND, fg=GRIS, font=("Segoe UI", 11, "bold"), anchor="w")
    etat.grid(row=0, column=0, columnspan=2, sticky="w")

    gauche = tk.Frame(corps, bg=FOND)
    gauche.grid(row=1, column=0, sticky="nw", pady=(10, 0))
    tk.Label(gauche, text="Sur ce PC :", bg=FOND, fg=GRIS, font=("Segoe UI", 9)).pack(anchor="w")
    tk.Label(gauche, text=url_locale, bg=FOND, fg=TXT, font=("Consolas", 11)).pack(anchor="w")
    tk.Label(gauche, text="Tablettes, téléphones, autres PC\n(même Wi-Fi que ce PC) :", justify="left",
             bg=FOND, fg=GRIS, font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))
    tk.Label(gauche, text=url_reseau, bg=FOND, fg=BLEU, font=("Consolas", 13, "bold")).pack(anchor="w")
    tk.Label(gauche, text="Scannez le QR code avec l'appareil photo\nde la tablette, ou tapez cette adresse\ndans Chrome ou dans l'application GESCOL.",
             justify="left", bg=FOND, fg=GRIS, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))

    # QR code de l'adresse réseau
    mat = matrice_qr(url_reseau)
    n = len(mat)
    case = max(3, 150 // (n + 8))
    taille = (n + 8) * case
    can = tk.Canvas(corps, width=taille, height=taille, bg="white", highlightthickness=1, highlightbackground="#D0D5DD")
    can.grid(row=1, column=1, padx=(18, 0), pady=(10, 0), sticky="ne")
    for r in range(n):
        for c in range(n):
            if mat[r][c]:
                x, y = (c + 4) * case, (r + 4) * case
                can.create_rectangle(x, y, x + case, y + case, fill="black", outline="black")

    boutons = tk.Frame(fen, bg=FOND, padx=18, pady=12)
    boutons.pack(fill="x")

    def ouvrir():
        webbrowser.open(url_locale)

    def copier():
        fen.clipboard_clear()
        fen.clipboard_append(url_reseau)
        etat_copie.config(text="Adresse copiée.")
        fen.after(2500, lambda: etat_copie.config(text=""))

    def dossier():
        if sys.platform.startswith("win"):
            os.startfile(config.INSTANCE_DIR)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", config.INSTANCE_DIR])

    def quitter():
        if messagebox.askyesno("Arrêter GESCOL",
                               "Arrêter GESCOL ?\n\nLes tablettes et les autres PC ne pourront plus se connecter "
                               "tant que GESCOL n'est pas relancé."):
            log.info("Arrêt demandé par l'utilisateur")
            fen.destroy()
            os._exit(0)

    style = dict(font=("Segoe UI", 10), padx=12, pady=5, relief="flat", cursor="hand2", bd=0)
    tk.Button(boutons, text="Ouvrir GESCOL", command=ouvrir, bg=BLEU, fg="white", activebackground="#2E6DA4",
              activeforeground="white", **style).pack(side="left")
    tk.Button(boutons, text="Copier l'adresse", command=copier, bg="white", fg=BLEU, **style).pack(side="left", padx=6)
    tk.Button(boutons, text="Dossier des données", command=dossier, bg="white", fg=BLEU, **style).pack(side="left")
    tk.Button(boutons, text="Arrêter", command=quitter, bg="white", fg=ROUGE, **style).pack(side="right")
    etat_copie = tk.Label(fen, text="", bg=FOND, fg=VERT, font=("Segoe UI", 9))
    etat_copie.pack(anchor="w", padx=18)
    tk.Label(fen, text="Laissez cette fenêtre ouverte (vous pouvez la réduire) : la fermer arrête GESCOL.",
             bg=FOND, fg=GRIS, font=("Segoe UI", 8), padx=18, pady=6).pack(anchor="w")
    tk.Label(fen, text=f"Conception : {config.CONCEPTEUR}", bg=FOND, fg=GRIS,
             font=("Segoe UI", 8, "italic"), pady=4).pack()
    fen.protocol("WM_DELETE_WINDOW", quitter)

    debut = time.time()
    ouvert = {"fait": False}

    def surveiller():
        if erreur["msg"]:
            etat.config(text="● Erreur : " + erreur["msg"][:80], fg=ROUGE)
            return
        if port_occupe(PORT):
            etat.config(text="● GESCOL est en marche", fg=VERT)
            if not ouvert["fait"]:
                ouvert["fait"] = True
                log.info("Serveur prêt sur %s", url_reseau)
                if "--sans-navigateur" not in sys.argv:
                    ouvrir()
        elif time.time() - debut > 30:
            etat.config(text="● Le serveur ne répond pas (voir gescol_serveur.log)", fg=ROUGE)
        fen.after(1500, surveiller)

    fen.after(800, surveiller)
    fen.mainloop()


if __name__ == "__main__":
    main()
