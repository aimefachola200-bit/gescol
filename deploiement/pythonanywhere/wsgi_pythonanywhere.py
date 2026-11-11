# Contenu à coller dans le fichier « WSGI configuration file » de PythonAnywhere (onglet Web).
# Remplacez NOM par votre nom d'utilisateur PythonAnywhere.
import os
import sys

os.environ["GESCOL_EN_LIGNE"] = "1"
os.environ["GESCOL_DATA"] = "/home/NOM/gescol-donnees"          # données hors du dossier du programme
# os.environ["GESCOL_ADMIN_MDP"] = "un-mot-de-passe-solide"     # mot de passe initial du compte admin (facultatif)

sys.path.insert(0, "/home/NOM/gescol")
from app import app as application  # noqa: E402,F401
