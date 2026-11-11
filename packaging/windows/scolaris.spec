# -*- mode: python ; coding: utf-8 -*-
# PyInstaller : fabrique dist/SCOLARIS/SCOLARIS.exe (dossier complet, démarrage rapide).
# Lancer depuis la racine du projet :  pyinstaller packaging/windows/scolaris.spec --noconfirm
import os
import glob
from PyInstaller.utils.hooks import collect_submodules

RACINE = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
# v1.10.9 : TOUS les modules Python du projet (app.py les charge par leur nom : PyInstaller ne les voit pas seul).
# Une liste écrite à la main oubliait les modules ajoutés depuis la 1.8 (m_acces, a_effectifs…) : page « Internal
# Server Error » sur PC.
MODULES_PROJET = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(RACINE, "*.py"))
                        if os.path.basename(f) not in ("scolaris_serveur.py", "wsgi.py"))

a = Analysis(
    [os.path.join(RACINE, "scolaris_serveur.py")],
    pathex=[RACINE],
    datas=[
        (os.path.join(RACINE, "templates"), "templates"),
        (os.path.join(RACINE, "static"), "static"),
        (os.path.join(RACINE, "modeles"), "modeles"),       # modèles officiels EducMaster (v1.6)
    ],
    hiddenimports=MODULES_PROJET + ["app", "db", "pdfs", "calcul", "config", "notif", "cachet", "referentiel_benin", "outils_xlsx",
                   "evaluations_core", "m_en_ligne", "m_ecoles", "m_parents", "m_paiement_en_ligne", "m_appel", "m_paie",
                   "m_tresorerie", "m_secretariat", "m_inscriptions", "m_evaluations", "m_resultats", "m_registre",
                   "m_affichage", "m_cep", "m_synthese", "m_cantine", "m_donnees", "m_finances_publiques", "m_carriere", "m_maitre_semaine",
                   "m_visites", "m_patrimoine", "m_recensement", "m_docs_enseignant", "m_rapports", "m_transmission",
                   "m_juridiction", "jur_format", "jur_calc", "a_transmission", "a_tableau", "a_cep", "a_personnel",
                   "a_structure", "a_visites", "a_fiches",
                   "m_synoptique", "m_stock_cantine", "m_epreuves", "m_calendrier_officiel", "m_themes_up", "a_divisions", "a_up",
                   "a_integration", "a_synoptique", "m_perimetre_enseignant", "waitress", "openpyxl", "pdfplumber", "pypdf"]
    + collect_submodules("reportlab.graphics.barcode")
    + collect_submodules("openpyxl")
    + collect_submodules("pdfplumber")
    + collect_submodules("pypdf")
    + collect_submodules("pdfminer")
    + collect_submodules("waitress"),
    excludes=["pytest", "IPython", "matplotlib", "numpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SCOLARIS",
    icon=os.path.join(RACINE, "static", "icons", "scolaris.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SCOLARIS", upx=False)
