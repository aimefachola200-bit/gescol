# Contenu à coller dans le fichier « WSGI configuration file » de PythonAnywhere (onglet Web).
# Remplacez NOM par votre nom d'utilisateur PythonAnywhere.
import os
import sys

os.environ["SCOLARIS_EN_LIGNE"] = "1"
os.environ["SCOLARIS_DATA"] = "/home/NOM/scolaris-donnees"          # données hors du dossier du programme
# os.environ["SCOLARIS_ADMIN_MDP"] = "un-mot-de-passe-solide"     # mot de passe initial du compte admin (facultatif)

sys.path.insert(0, "/home/NOM/scolaris")
from app import app as application  # noqa: E402,F401
