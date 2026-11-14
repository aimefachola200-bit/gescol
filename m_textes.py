# -*- coding: utf-8 -*-
"""v2.5.4 : textes officiels de référence (MEMP et MESTFP) intégrés aux archives de chaque application.
Les PDF numérisés fournis par l'utilisateur sont embarqués (static/textes_officiels) ; les résumés ne reprennent que ce qui a été lu."""
from flask import render_template, request

TEXTES = [
    {"fichier": "arrete_bepc_2024.pdf", "tutelle": "MESTFP (secondaire)", "cycle": "secondaire",
     "titre": "Arrêté n° 008/MESTFP/DC/SGM/IGPM/DESG/DEC/CJ/SA/005SGG24 (2024) portant réorganisation du BEPC",
     "points": [
         "Art. 2 : session unique chaque année ; session de remplacement pour le candidat malade dûment constaté par un médecin agréé.",
         "Art. 6 : inscription en deux étapes (en ligne sur EducMaster, puis dépôt d'un dossier physique) ; le candidat précise s'il compose en espagnol ou en allemand.",
         "Art. 7 : épreuves selon l'APC sur le programme de la classe de 3e : épreuves écrites, épreuve orale d'anglais, épreuve d'EPS.",
         "Art. 8 : épreuves écrites de 2 h chacune. Coefficients : Communication écrite 2, Lecture 2, Histoire-Géographie 2, Anglais 2, SVT 2, PCT 2, Allemand ou Espagnol 2, Mathématiques 3 ; oral d'anglais 2 ; EPS 1.",
         "Art. 9 à 11 : épreuves proposées par des professeurs ou conseillers pédagogiques, avec guide d'administration et grille de correction ; tri par une commission nationale.",
         "Art. 13 : notes de 0 à 20, affectées du coefficient.",
         "Art. 14 : admission aux épreuves orale et d'EPS à partir de 153 points sur 340 aux épreuves écrites.",
         "Art. 17 : admis définitivement avec au moins 200 points sur 400 (écrit, oral, EPS) ; candidat dispensé d'EPS : au moins 190 points (écrit et oral de langue).",
         "Art. 21 : calendrier sur trois jours (Communication écrite, Lecture, Histoire-Géographie ; Anglais, SVT, PCT ; Allemand ou Espagnol, Mathématiques).",
         "Art. 23, 24, 26, 27 : contrôle d'identité, exclusion du candidat qui arrive cinq minutes après le démarrage (décision du chef de centre), anonymat des copies, fraude y compris par réseaux sociaux ou intelligence artificielle.",
         "Art. 29 : composition des commissions de surveillance (suite aux pages 9 à 15 du document)."]},
    {"fichier": "arrete_075_2018.pdf", "tutelle": "MEMP (maternel et primaire)", "cycle": "primaire",
     "titre": "Arrêté n° 075/MEMP/DC/SGM/DAF/SA/086SGG18 du 3 août 2018 portant attributions et modalités de nomination des directeurs d'écoles maternelles et primaires publiques",
     "points": [
         "Définit les attributions du directeur d'école publique (maternelle ou primaire) et les conditions de sa nomination.",
         "Texte de 11 pages, chapitres I à III et suivants ; se reporter au PDF pour les articles et les barèmes."]},
    {"fichier": "arrete_103_2021.pdf", "tutelle": "MEMP (maternel et primaire)", "cycle": "primaire",
     "titre": "Arrêté n° 103/MEMP/DC/SGM/DAF/SA/066SGG21 du 26 novembre 2021 modifiant et complétant l'article 28 de l'arrêté 075",
     "points": [
         "Nouvel article 28 : nonobstant les articles 12 et 14 (1er tiret), peuvent être nommés directeurs d'école les enseignants titulaires du CAP reçus dans l'un des ordres nationaux du Bénin ;",
         "et, en cas d'insuffisance d'enseignants de la maternelle titulaires du CAP, les enseignants des écoles maternelles titulaires du CEAP."]},
    {"fichier": "cahiers_des_charges_rap_2006.pdf", "tutelle": "MEPS (primaire), août 2006", "cycle": "primaire",
     "titre": "Cahiers des charges des acteurs du réseau d'animation pédagogique (version révisée et finalisée, août 2006)",
     "points": [
         "Morale professionnelle : assiduité et ponctualité, devoir de réserve, respect des droits de l'enfant, formation continue, auto-évaluation.",
         "Cahier des charges de l'enseignant : horaires (présent au moins 15 min avant le début des activités ; l'enseignant de semaine 30 min avant), registre d'appel tenu à jour et visé chaque mois, tableau d'affichage, cahier de conseils pédagogiques.",
         "Cahier des charges du directeur d'école : plannings annuel, trimestriel et mensuel avec le conseiller pédagogique, cahiers et registres réglementaires, fiche statistique, contrôle de la ponctualité du personnel, archives, répartition des tâches en gestion collégiale, contrôle des documents pédagogiques, réunion du collectif des enseignants.",
         "Cahiers des charges du responsable d'unité pédagogique (RUP), du conseiller pédagogique et du chef de circonscription scolaire."]},
    {"fichier": "annale_cm2_2017.pdf", "tutelle": "MEMP (primaire), mai 2017", "cycle": "primaire",
     "titre": "Annale des épreuves et grilles de correction commentées, classes de CM2 (Porto-Novo, mai 2017)",
     "points": [
         "Document de la Direction de l'inspection et de l'innovation pédagogiques destiné à l'encadrement pédagogique des candidats du CM2.",
         "Sommaire : préface, guide de l'utilisateur, épreuves de 2012 à 2016, épreuves standardisées, recueil d'informations essentielles dans la pratique de la langue française.",
         "80 pages ; ouvrir le PDF pour les épreuves et les grilles."]},
]


CAHIERS = [
    {"fichier": "francais_ci.pdf", "titre": "Cahier d'activités de Français - Cours d'Initiation (CI)", "info": "MEMP / DIIP / INFRE, programme en vigueur (version 2024). 70 pages, image compressée."},
    {"fichier": "maths_cp.pdf", "titre": "Cahier d'activités de Mathématiques - Cours préparatoire (CP)", "info": "MEMP / DIIP / INFRE, édition 2022 (impression 2024). 98 pages, image compressée."},
]

# Acteurs de l'établissement et leurs périmètres. Répartition usuelle des tâches dans les établissements béninois :
# elle est donnée à titre d'aide-mémoire et doit être confrontée aux textes en vigueur (décret 2016-427, arrêté 075, règlement intérieur).
ACTEURS_SEC = [
    ("Chef d'établissement (proviseur, directeur)", "Dirige l'établissement, représente l'administration, préside le conseil d'administration et les conseils de classe ; garant de la discipline, de la gestion des personnels, des moyens et des examens."),
    ("Censeur (directeur des études)", "Organise la vie pédagogique : emplois du temps, répartition des classes et des services, suivi des programmes, des évaluations et des cahiers de textes, coordination des chefs de département et des professeurs principaux, préparation des conseils de classe."),
    ("Surveillant général", "Organise la vie scolaire : assiduité, ponctualité, discipline, sorties et entrées, coordination des surveillants, traitement des absences et des sanctions, relation avec les parents sur ces points."),
    ("Surveillants (éducateurs)", "Surveillent cours, couloirs et cour ; tiennent les cahiers d'appel et de présence, signalent retards, absences et incidents au surveillant général."),
    ("Professeur principal", "Anime l'équipe pédagogique de sa classe : suivi des résultats et du comportement, centralisation des notes, préparation et tenue du conseil de classe, remplissage des bulletins, lien avec les parents et la vie scolaire."),
    ("Chefs de département / animateurs pédagogiques", "Coordonnent les enseignants d'une discipline : harmonisation des progressions et des sujets, cellules pédagogiques, conseils aux jeunes enseignants."),
    ("Enseignants", "Préparent et dispensent les cours selon le programme (APC), évaluent, saisissent les notes dans les délais, tiennent le cahier de textes."),
    ("Intendant / économe", "Gère les finances et le matériel : recettes, dépenses, inventaire, budget de l'établissement."),
    ("Secrétaire / secrétariat", "Tient les dossiers des élèves et du personnel, le courrier, les archives, établit certificats et attestations."),
    ("Conseiller d'orientation / conseiller pédagogique", "Oriente et accompagne les élèves ; appuie la pédagogie et la préparation des examens."),
    ("Bibliothécaire / laborantin / responsable informatique", "Gèrent respectivement la bibliothèque, les laboratoires et les équipements numériques."),
    ("Délégués de classe et association des parents d'élèves", "Les délégués portent la voix des élèves ; l'association des parents participe à la vie de l'établissement et à son financement dans le cadre prévu."),
]
ACTEURS_PRIM = [
    ("Directeur d'école", "Attributions et modalités de nomination fixées par l'arrêté 075 du 3 août 2018 (modifié par l'arrêté 103 du 26 novembre 2021, art. 28) : voir le PDF dans les textes officiels."),
    ("Directeur d'école : cahier des charges (2006)", "Responsable de la vie de l'école et premier formateur des enseignants : élabore avec le conseiller pédagogique les plannings annuel, trimestriel et mensuel ; tient ou fait tenir les registres et cahiers réglementaires ; remplit la fiche statistique ; contrôle chaque mois la ponctualité et l'assiduité du personnel ; répartit les rôles en gestion collégiale ; contrôle les documents pédagogiques des classes ; réunit le collectif des enseignants."),
    ("Enseignant : cahier des charges (2006)", "Arrive au moins 15 minutes avant le début des activités (30 minutes pour l'enseignant de semaine) ; tient le registre d'appel, le tableau d'affichage et le cahier de conseils pédagogiques ; applique l'emploi du temps."),
    ("Responsable d'unité pédagogique (RUP), conseiller pédagogique, chef de circonscription scolaire", "Animent et contrôlent le réseau d'animation pédagogique à leur niveau ; voir leurs cahiers des charges dans le PDF de 2006."),
    ("Directeur adjoint", "Seconde le directeur selon la répartition qu'il fixe, et le remplace en cas d'absence."),
    ("Enseignants (maîtres)", "Préparent leurs fiches, enseignent selon le programme, évaluent, tiennent registre d'appel et cahier journal."),
    ("Conseiller pédagogique / inspecteur", "Visitent les classes, conseillent et inspectent ; relèvent de la circonscription scolaire."),
    ("Association des parents d'élèves et COGES", "Participent à la vie de l'école et à la gestion de ses ressources."),
]


def enregistrer(app, H):
    @app.route("/textes-officiels")
    @H.connexion_requise()
    def textes_officiels():
        return render_template("textes_officiels.html", textes=TEXTES, cahiers=CAHIERS, cp_lecons=__import__("cahier_cp_progression").LECONS)

    @app.route("/cahier-cp-francais.pdf")
    @H.connexion_requise()
    def cahier_cp_francais_pdf():
        import cahier_cp_original as CO
        corrige = request.args.get("corrige") == "1"
        return H.pdf_reponse(CO.pdf(corrige), "cahier_francais_cp_corrige.pdf" if corrige else "cahier_francais_cp.pdf")

    @app.route("/acteurs-etablissement")
    @H.connexion_requise()
    def acteurs_etablissement():
        return render_template("acteurs.html", sec=ACTEURS_SEC, prim=ACTEURS_PRIM)

    @app.route("/reperes-pedagogiques")
    @H.connexion_requise()
    def reperes_pedagogiques():
        import reperes as R
        return render_template("reperes.html", auteurs=R.AUTEURS, art=R.ART, lecture=R.LECTURE_CP)

    @app.route("/lectures-college")
    @H.connexion_requise()
    def lectures_college():
        import lectures as L
        return render_template("lectures.html", lectures=L.LECTURES)

    @app.route("/cahiers-langues")
    @H.connexion_requise()
    def cahiers_langues():
        import cahiers_langues as C
        return render_template("cahiers_langues.html", data=C.DATA, niveaux=C.NIVEAUX)

    @app.route("/cahiers-langues/<langue>/<niveau>/<qui>.pdf")
    @H.connexion_requise()
    def cahier_langue_pdf(langue, niveau, qui):
        import cahiers_langues as C
        from flask import abort, Response
        if langue not in C.DATA or niveau not in C.DATA[langue] or qui not in ("eleve", "enseignant"):
            abort(404)
        return Response(C.pdf(langue, niveau, qui == "enseignant"), mimetype="application/pdf",
                        headers={"Content-Disposition": f"inline; filename=breviaire_{langue.lower()}_{niveau}_{qui}.pdf"})

    @app.route("/schemas-fournis")
    @H.connexion_requise()
    def schemas_fournis():
        import schemas_fournis as S
        return render_template("schemas_fournis.html", cartes=S.CARTES, croquis=S.CROQUIS)

    @app.route("/poesies")
    @H.connexion_requise()
    def poesies():
        import poesies as P
        return render_template("poesies.html", poemes=P.POEMES, grille=P.GRILLE, conseils=P.CONSEILS)
