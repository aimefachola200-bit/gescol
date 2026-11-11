# -*- coding: utf-8 -*-
"""v1.32 — « Guide d'utilisation » (LISEZ-MOI) de GESCOL : rubriques par rôle (administrateur, directeur, enseignant,
conseiller pédagogique, circonscription, DDEMP), premiers pas, chaque module en quelques étapes, sauvegarde, hors ligne,
impression, codes QR, questions fréquentes. Même plan que le guide des applications web (outils/lots/guide-contenus.mjs).

Trois sorties du même contenu : page de l'application (/aide/guide, avec recherche), PDF « LISEZ-MOI » (Times New Roman
14 pt) et fichier LISEZMOI.md (python3 guide_utilisation.py, depuis le dossier de l'application).
"""
import io
import os

ROLES = [("tous", "Tout le monde"), ("admin", "Administrateur / fondateur"), ("directeur", "Directeur / directrice"),
         ("enseignant", "Enseignant(e)"), ("cp", "Conseiller pédagogique"), ("cs", "Circonscription scolaire"), ("ddemp", "DDEMP")]
CONTACT = "Maître Aimé FACHOLA, +229 01 96 51 03 33 (appel ou WhatsApp)"

SECTIONS = [
    {"id": "premiers-pas", "titre": "Premiers pas", "roles": ["tous"],
     "intro": "{appli} gère l'école au quotidien : élèves, présences, notes et bulletins, préparation de classe, examens, "
              "personnel, sport scolaire (UASCEP), santé, cantine, patrimoine et documents officiels vérifiables.",
     "etapes": ["Ouvrez l'application et connectez-vous avec l'identifiant et le mot de passe reçus (au premier démarrage : admin / admin123, à changer aussitôt).",
                "Saisissez une fois le code d'accès personnel demandé (page « Code d'accès », demande par WhatsApp au concepteur).",
                "Remplissez la fiche de l'école : nom, circonscription, directeur, cachet, signature, devise et logo.",
                "Créez les classes (niveau CI à CM2, titulaire), puis les comptes des enseignants dans « Utilisateurs ».",
                "Inscrivez les élèves (un par un, ou par importation Excel / EducMaster)."],
     "conseils": ["Le menu à gauche (ou le bouton « Menu » sur téléphone) donne accès à tous les modules autorisés pour votre compte.",
                  "Les tableaux gardent leur ligne d'en-tête visible quand vous faites défiler la page."]},
    {"id": "ecole", "titre": "Fiche de l'école, logo et devise", "roles": ["admin", "directeur"],
     "etapes": ["Menu « Écoles » puis « Modifier » sur votre école.",
                "Écrivez la devise (ou choisissez-en une dans la liste : « Travail – Discipline – Réussite »…).",
                "Dans « Logo », choisissez « Créer le logo automatiquement », puis la forme (rond ou écusson), le symbole (livre, plume, soleil, épi, palmier, colombe, globe…), les initiales et les couleurs ; l'aperçu se met à jour.",
                "Ou importez votre propre logo (PNG ou JPG). « Pas de logo » le retire.",
                "Réglez le cachet et la griffe, ajoutez les signatures du directeur et de l'administrateur, puis « Enregistrer »."],
     "conseils": ["Le logo et la devise figurent en tête des documents de l'école (bulletins, certificats, listes, fiches).",
                  "Les liens « Télécharger le logo automatique (SVG / PNG) » donnent le logo en fichier pour d'autres usages."]},
    {"id": "eleves", "titre": "Élèves, classes et présences", "roles": ["admin", "directeur", "enseignant"],
     "etapes": ["« Élèves » : inscrire, modifier, transférer ; « Importer » pour une liste Excel ou EducMaster.",
                "« Faire l'appel » chaque demi-journée ; les absences alimentent le registre de présence et les alertes de décrochage.",
                "« Registre de présence » et « Relevés mensuels » s'impriment en PDF signé avec code QR."],
     "conseils": ["L'enseignant ne voit que ses classes ; le directeur voit toute l'école."]},
    {"id": "notes", "titre": "Évaluations, notes et bulletins", "roles": ["admin", "directeur", "enseignant"],
     "etapes": ["« Saisie des notes » : choisissez la classe, la période et la matière, saisissez puis enregistrez.",
                "« Statistiques » et « Analyse et rapport » : moyennes, taux de réussite, courbes, comparaison des classes.",
                "« Notes par période (bulletins) » : bulletins individuels et listes, signés avec code QR.",
                "« Bilan annuel et décision » : passage, redoublement, tableau d'honneur."]},
    {"id": "preparation", "titre": "Préparation de classe : fiches, résumés, épreuves", "roles": ["enseignant", "directeur", "cp", "admin"],
     "etapes": ["« Cette semaine » : pour chaque classe, les fiches de la semaine d'après la planification ; « Voir les fiches » ou « Fiches de la semaine (PDF) ».",
                "« Fiches de préparation (bibliothèque) » : filtrez par cours, matière, SA et séance ; ouvrez une fiche, puis PDF, Word ou « Adapter pour ma classe ».",
                "« Préparer une fiche » : partez d'une fiche du corpus ou d'une fiche vierge, complétez, enregistrez (« Mes fiches »).",
                "« Résumés » : l'essentiel de chaque séance, version enseignant ou version élève ; cahiers de résumés par cours et matière.",
                "« Évaluations et épreuves » : sujets et corrigés (mensuelles, trimestrielles, passage, CEP blancs), onglet « Modifier » pour adapter un sujet.",
                "« Planification et classeurs » : vues jour, semaine, mois ; classeur des fiches à imprimer."],
     "conseils": ["La fiche imprimée porte le nom du titulaire de la classe en filigrane oblique : renseignez le titulaire dans la fiche de la classe.",
                  "Les fiches longues sont prévues pour le recto verso : choisissez « recto verso » dans les réglages de l'imprimante ; chaque page est numérotée « Page x / y ».",
                  "Les contenus conçus selon l'APC portent la mention « à valider par le conseiller pédagogique »."]},
    {"id": "examens", "titre": "CEP, examen blanc et concours", "roles": ["admin", "directeur", "enseignant", "cs"],
     "etapes": ["« Session CEP » : candidats, centres, jurys, numéros de table.",
                "« Saisie des notes » puis « Délibération et résultats » : statistiques par école et par sexe, PV, listes, relevés.",
                "« Examen blanc du CEP » : neuf épreuves, seuil de six maîtrises sur neuf (six sur huit pour un dispensé d'EPS), classement et recommandations.",
                "Le même module a deux onglets : « Examen blanc commun (CS, 9 épreuves) » et « Examen blanc libre (école) », aux matières choisies par l'école ; « Reprendre dans l'examen blanc commun » y verse une session libre (candidats et notes).",
                "« Révisions d'éveil » (CM1, CM2) : cahiers de révision et sujets type CEP avec corrigé et barème."]},
    {"id": "uascep", "titre": "Bureaux UASCEP et sport scolaire", "roles": ["tous"],
     "etapes": ["« Bureaux UASCEP », onglet « Ajouter un membre » : niveau (école, UP, zone, CS, DDEMP), entité, puis les renseignements du membre ; le bureau se crée avec le premier membre.",
                "Pour chaque responsable : signature (dessinée ou importée) et cachet (généré ou importé).",
                "Onglet « Documents » : composition du bureau, PV d'élection et d'installation, attestations, liste des bureaux, signés avec code QR.",
                "Onglet « Vie du bureau » : activités, réunions (rapporteur), caisse et budget (trésorier), matériel, rapport de fin de saison.",
                "« Sport scolaire » : licences, compétitions, feuilles de match, classements, palmarès, records et diplômes."]},
    {"id": "suivi", "titre": "Santé, cantine, communication, inspection, patrimoine", "roles": ["admin", "directeur", "cp", "cs", "ddemp"],
     "etapes": ["Santé : visites médicales (aptitude sportive), infirmerie, élèves à besoins spécifiques, gescolation des filles, décrochage.",
                "Cantine : journal des repas et stocks (alerte de rupture).",
                "Communication : notes de service, circulaires et convocations avec accusé de lecture, échéances, messages aux parents, agenda.",
                "Inspection et formation : visites de classe (grille APC), suivi des recommandations, plans de formation, animations pédagogiques.",
                "Patrimoine : bâtiments, tables-bancs, manuels, matériel, besoins et dotations.",
                "Personnel et carrière : les anciennetés se calculent au 31 décembre de la seconde année de l'année scolaire (« 2026-2027 » : 31/12/2027), jour inclus ; la date de départ à la retraite selon le grade et la date de naissance. Ces valeurs ne se saisissent pas."]},
    {"id": "pilotage", "titre": "Tableau de bord du pilotage", "roles": ["admin", "directeur", "cp", "cs", "ddemp"],
     "etapes": ["Menu « Tableau de bord du pilotage » : effectifs, ratios élèves / maître et élèves / classe, réussite, CEP, abandons, personnel, sport.",
                "Choisissez le niveau et l'année ; comparez les entités et les années ; exportez en PDF ou Excel."]},
    {"id": "juridiction", "titre": "Circonscription (CS) et DDEMP", "roles": ["cs", "ddemp", "cp"],
     "etapes": ["Au premier démarrage, renseignez la structure (circonscription ou direction départementale), ses zones et UP, ses services.",
                "Ajoutez les écoles de la juridiction ou importez leurs données transmises (Excel, transmission).",
                "Les tableaux de synthèse, statistiques et documents se calculent à partir des écoles."]},
    {"id": "classes-ouvertes", "titre": "Classes jumelées et multigrades", "roles": ["admin", "directeur"],
     "etapes": ["Gardez une classe par cours dans « Classes » (les effectifs restent comptés par cours).",
                "Pour une classe jumelée (ex. CI-CP) ou multigrade (ex. CI-CE2-CM1) tenue dans une salle par un maître : cochez ses cours puis « Regrouper les cours cochés » ; « Séparer » les remet en classes simples.",
                "Le nombre de classes ouvertes (simples + jumelées + multigrades) est repris partout : recensement, rapports, fiche de rentrée, pilotage, tableau de bord ; les classes autorisées restent un chiffre à part (l'écart est montré)."]},
    {"id": "cep2027", "titre": "CEP : centres et salles de composition", "roles": ["cs", "ddemp", "admin", "directeur"],
     "etapes": ["Examens et concours › « CEP — centres et salles » : « Charger les centres de la CS de Pobè » (ou ajoutez vos centres), puis saisissez par centre les candidats officiels et libres (garçons, filles, dont handicapés) et les salles de composition en bon état disponibles.",
                "« Pré-remplir les candidats officiels » reprend les candidats inscrits par centre (cases vides seulement).",
                "Choisissez « Candidats par salle » (30 à 40) : salles nécessaires, écart et « Capacité suffisante » ou « Capacité dépassée : N salle(s) manquante(s) » s'affichent ; une observation saisie remplace la situation calculée.",
                "Onglets « Tableau simple » (modèle officiel) et « Tableau détaillé » ; « Télécharger PDF » (signé, QR) ou « Télécharger Excel » (formules) pour l'envoi à la DDEMP.",
                "La DDEMP voit un bloc par circonscription (tableaux reçus par la synchronisation ou importés) et le total du département ; l'école voit son centre en lecture seule."]},
    {"id": "territoire", "titre": "Territoire et suivi : fiche de rentrée, courrier, présence du personnel", "roles": ["admin", "directeur", "cs", "ddemp", "cp"],
     "etapes": ["Menu « Territoire et suivi » › « Fiche statistique de rentrée » : les effectifs, le personnel, le patrimoine et la fiche signalétique sont proposés ; vérifiez, enregistrez, puis « Transmettre ». La fiche part avec la synchronisation.",
                "La circonscription ouvre « Suivi des fiches de rentrée » : « Valider » ou « Renvoyer » (motif obligatoire) ; la DDEMP valide à son tour puis « Clôturer ». La décision redescend vers l'école ; une fiche renvoyée se corrige puis se retransmet.",
                "« Fiche signalétique de l'école » : coordonnées GPS (bouton « Position actuelle » sur le téléphone, dans la cour de l'école), statut juridique, numéros d'autorisation et d'agrément (écoles privées), eau, latrines, électricité, salles.",
                "Communication › « Courrier administratif » : rapport, demande ou compte rendu vers la CS ou la DDEMP ; « Envoyer » l'inscrit au registre « départ » du secrétariat. Le destinataire l'ouvre dans « Courrier reçu » (accusé de lecture daté, registre « arrivée »), puis le marque « Traité » ou l'archive.",
                "« Présence du personnel » : appel du jour (présent, absent, retard, congé, mission, formation, maladie) et statistiques du mois avec le taux de présence de chaque agent.",
                "« Incidents de discipline » : date, description, sanction, décision, information des parents ; ces données d'élèves restent dans l'école.",
                "Inspection › Visites de classe : « Statut de la visite » (planifiée, réalisée, rapport rédigé, validée) et « Date de la prochaine visite » ; les visites en retard et les prochaines visites apparaissent dans les alertes.",
                "CS / DDEMP : « Référentiel des structures » (arbre ministère → DDEMP → services → CS → divisions, modifiable) ; « Niveau national » : agrégats en lecture seule pour un compte « Observateur » et adresse /api/stats.json protégée par un jeton (créé par le responsable, à noter à sa création)."]},
    {"id": "impression", "titre": "Télécharger en PDF ou en Word, imprimer", "roles": ["tous"],
     "etapes": ["En haut de chaque page de pédagogie (fiches, résumés, épreuves, guides, programmes, révisions…) : « Télécharger PDF », « Télécharger Word » ou « Imprimer ».",
                "Dans les listes de fiches et de résumés, chaque ligne a ses boutons PDF et Word ; cochez plusieurs lignes (ou gardez le filtre) puis « Un PDF (livret) », « Un document Word » ou « ZIP (un Word par fiche) ».",
                "Sur téléphone ou tablette Android, le fichier va dans « Téléchargements / GESCOL » : touchez « Ouvrir » ou « Partager » (WhatsApp, e-mail…). « Imprimer » ouvre l'impression d'Android (imprimante ou « Enregistrer au format PDF »).",
                "Une fiche de préparation tient sur une feuille recto verso : page 1, en-tête et éléments de planification ; page 2, déroulement et évaluation.",
                "Une épreuve courte s'imprime deux fois par feuille A4 avec une ligne de coupe."]},
    {"id": "verification", "titre": "Code QR et vérification des documents", "roles": ["tous"],
     "etapes": ["Les documents officiels portent un code de vérification et un code QR.",
                "Scannez le code QR avec un téléphone, ou ouvrez « Vérifier un document » et saisissez le code.",
                "La page indique si le document est authentique et à quoi il correspond."]},
    {"id": "sauvegarde", "titre": "Sauvegarde, restauration et transmission", "roles": ["admin", "directeur"],
     "etapes": ["L'application fait seule une sauvegarde chaque jour sur l'appareil (Administration › Mise en ligne et sauvegardes) ; le nombre gardé se règle.",
                "« Télécharger une sauvegarde maintenant » crée une archive à jour (base, photos, logo, cachet, signatures) et la télécharge : gardez-la hors de l'appareil (clé USB, ordinateur, envoi à soi-même).",
                "Un bandeau rappelle de le faire quand aucune copie hors de l'appareil n'a été faite depuis 7 jours.",
                "Sur ordinateur, indiquez un « dossier de secours » (clé USB, disque externe) : chaque sauvegarde y est aussi copiée quand il est branché.",
                "« Vérifier » contrôle une sauvegarde sans rien remplacer (empreintes de chaque fichier, état de la base).",
                "« Restaurer » remet une sauvegarde en place : elle est vérifiée d'abord, et refusée si elle est abîmée ou modifiée.",
                "« Transmettre » envoie les données attendues à la circonscription."],
     "conseils": ["Téléchargez une sauvegarde au moins une fois par semaine et toujours avant une mise à jour ou un changement d'appareil."]},
    {"id": "synchronisation", "titre": "Synchronisation avec la circonscription et la DDEMP", "roles": ["admin", "directeur", "cs", "ddemp"],
     "etapes": ["La CS ouvre « Synchronisation › Entités inscrites » et affiche le code QR de l'école (il contient l'adresse de la CS et le code d'accès de l'école).",
                "À l'école, « Synchronisation › Rejoindre » : collez le texte du code QR (ou l'adresse et le code d'accès), puis « Enregistrer ».",
                "« Synchroniser maintenant » envoie ce qui a changé (effectifs, personnel, résultats, bureaux UASCEP, examen blanc, licences, accusés de réception, épreuves proposées) et reçoit les notes de service, circulaires, convocations, échéances, agenda et épreuves proposées par la CS.",
                "Sans Internet : « Préparer le fichier à remettre » (clé USB, WhatsApp, e-mail) ; la CS l'importe et prépare en retour le « Fichier pour elle », que l'école importe.",
                "Chaque paquet est signé par l'appareil : un paquet modifié ou venant d'un autre appareil est refusé. Après un changement d'appareil, la CS accepte la nouvelle clé dans « Entités inscrites ».",
                "La CS se synchronise de la même façon avec la DDEMP ; elle relaie les données de ses écoles et redescend celles de la DDEMP.",
                "« Conflits à revoir » liste les rubriques modifiées des deux côtés : la valeur du niveau le plus élevé est gardée, et chacun peut choisir l'autre."],
     "conseils": ["Les dossiers de santé, les besoins spécifiques des élèves, les parents, les paiements et les mots de passe ne quittent jamais l'école."]},
    {"id": "maternelle", "titre": "École maternelle et programme en vigueur d'ES / EPS", "roles": ["enseignant", "directeur", "admin", "cs"],
     "etapes": ["« Préparation de classe › École maternelle » : choisissez la section (petits ou grands), puis le domaine, la composante, le mois et la semaine ; chaque activité ouvre sa fiche (Times 14, imprimable).",
                "La progression des grands vient de la planification 2025-2026 de la CS Cotonou II, reprise pour 2026-2027 ; celle des petits est « proposée » : adaptez-la en conseil des maîtres.",
                "Les vues « Mois », « Semaine » et « Jour » placent les activités dans l'emploi du temps de la section ; « Planification (PDF) » et « Classeur (PDF) » impriment la planification et les fiches de la semaine ou du mois.",
                "« Grilles d'observation » : une grille par composante (acquis, en cours d'acquisition, non acquis), avec la liste des enfants de la classe choisie ; pas d'épreuves écrites à la maternelle.",
                "« Je retiens (éducateur) » donne les repères de chaque composante. Les classes « Maternelle 1 » et « Maternelle 2 » voient les activités de la semaine dans « Cette semaine ».",
                "Éducation sociale et EPS : « Programmes et progressions » affiche « Programme en vigueur : mesures correctives » ; chaque SA donne ses séquences, connaissances et techniques et matériel, et les fiches y sont rattachées."],
     "conseils": ["Les fiches de la maternelle sont des fiches conçues : faites-les valider par le conseiller pédagogique avant de les diffuser."]},
    {"id": "securite", "titre": "Mots de passe et sécurité des comptes", "roles": ["tous"],
     "etapes": ["Un mot de passe compte au moins 8 caractères, avec au moins une lettre et un chiffre ; il ne contient pas l'identifiant et n'est pas un mot de passe trop connu (admin123, 12345678…).",
                "Si vous vous connectez avec un mot de passe de départ ou trop faible, l'application vous demande aussitôt d'en choisir un nouveau.",
                "Après 5 essais faux sur un compte, ce compte est bloqué 15 minutes : utilisez « Mot de passe oublié ? » si besoin.",
                "Sans activité pendant 2 heures (8 heures sur l'application du téléphone), la session se ferme : reconnectez-vous."]},
    {"id": "partage", "titre": "Versions partagées des épreuves, fiches et résumés", "roles": ["enseignant", "directeur", "cp", "admin"],
     "etapes": ["Une épreuve modifiée, un résumé « adapté pour l'école » ou une fiche « partagée avec l'école » est le même pour tous les comptes de l'école.",
                "« Historique » montre chaque version (auteur, date) ; « Rétablir » remet une version précédente pour toute l'école.",
                "Une fiche partagée par un collègue se lit et se copie dans ses propres fiches (« Copier dans mes fiches »).",
                "Le directeur ou le CP peut « Proposer à la CS / DDEMP » une version : elle part avec la synchronisation."]},
    {"id": "hors-ligne", "titre": "Hors ligne, téléphone et tablette", "roles": ["tous"],
     "etapes": ["Les applications Android autonomes (GESCOL, Public, Enseignant…) fonctionnent sans internet ni ordinateur : installez-les avec le code QR de la fiche d'installation.",
                "Sur ordinateur, l'application Windows sert aussi les téléphones du même réseau Wi-Fi (adresse affichée au démarrage).",
                "Sur téléphone, les listes de choix s'ouvrent en plein écran avec une recherche."]},
]
FAQ = [
    ("Une page affiche « Une erreur est survenue ».", "Touchez « Envoyer le rapport par WhatsApp » : le concepteur reçoit le détail. Mettez l'application à jour (dernière version)."),
    ("La préparation de classe ne s'ouvre pas.", "Installez la version 1.31.1 ou plus récente, qui corrige l'ouverture des fiches depuis une classe."),
    ("Je ne retrouve pas mes données sur un autre appareil.", "Chaque appareil a ses données : faites une sauvegarde sur le premier, restaurez-la sur le second."),
    ("La synchronisation dit « autre clé ».", "L'appareil a changé (ou a été réinstallé) : la CS doit accepter la nouvelle clé dans « Synchronisation › Entités inscrites »."),
    ("Mon compte est bloqué.", "Après 5 mots de passe faux, attendez 15 minutes ou utilisez « Mot de passe oublié ? »."),
    ("L'application me demande de changer mon mot de passe.", "Votre mot de passe était celui de départ ou trop faible : choisissez-en un de 8 caractères au moins, avec lettres et chiffres."),
    ("Le logo n'apparaît pas sur les documents.", "Fiche de l'école : choisissez « Créer le logo automatiquement » ou importez un logo, puis « Enregistrer »."),
    ("J'ai oublié mon mot de passe.", "Sur l'écran de connexion, « Mot de passe oublié » : l'administrateur ou le directeur reçoit la demande et vous donne un nouveau mot de passe."),
    ("Qui contacter ?", "Le concepteur : " + CONTACT + "."),
]


def sections_pour(role=None):
    if not role or role == "tous":
        return SECTIONS
    return [s for s in SECTIONS if "tous" in s["roles"] or role in s["roles"]]


def texte(t, appli):
    return t.replace("{appli}", appli)


def markdown(appli="GESCOL", version=""):
    out = [f"# {appli} — Guide d'utilisation (LISEZ-MOI)", "",
           f"Version {version}. " if version else "",
           "Ce guide explique, en quelques étapes simples, comment utiliser chaque partie de l'application. "
           "Chaque rubrique indique pour qui elle est utile.", ""]
    lib = dict(ROLES)
    for s in SECTIONS:
        out += [f"## {s['titre']}", "", "*Pour : " + ", ".join(lib[r] for r in s["roles"]) + "*", ""]
        if s.get("intro"):
            out += [texte(s["intro"], appli), ""]
        out += [f"{i}. {texte(e, appli)}" for i, e in enumerate(s["etapes"], 1)] + [""]
        for c in s.get("conseils") or []:
            out.append(f"- Conseil : {texte(c, appli)}")
        if s.get("conseils"):
            out.append("")
    out += ["## Questions fréquentes et dépannage", ""]
    for qq, r in FAQ:
        out += [f"**{qq}**", "", r, ""]
    out += ["---", "", f"Conception : {CONTACT}", ""]
    return "\n".join(x for x in out if x is not None)


def pdf(appli="GESCOL", version="", role=None):
    """PDF « LISEZ-MOI » (Times New Roman 14 pt, titres en couleur)."""
    import pdfs
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape
    S = pdfs.police_serif()
    bleu = colors.HexColor("#1F4E79")
    st = {"t": ParagraphStyle("t", fontName=S["gras"], fontSize=20, leading=24, textColor=bleu, alignment=1, spaceAfter=6),
          "s": ParagraphStyle("s", fontName=S["normal"], fontSize=13, leading=17, alignment=1, spaceAfter=10),
          "h": ParagraphStyle("h", fontName=S["gras"], fontSize=16, leading=20, textColor=bleu, spaceBefore=10, spaceAfter=4),
          "r": ParagraphStyle("r", fontName=S["italique"], fontSize=11, leading=14, textColor=colors.HexColor("#475467"), spaceAfter=4),
          "p": ParagraphStyle("p", fontName=S["normal"], fontSize=14, leading=18, spaceAfter=4),
          "e": ParagraphStyle("e", fontName=S["normal"], fontSize=14, leading=18, leftIndent=16, bulletIndent=2, spaceAfter=3),
          "c": ParagraphStyle("c", fontName=S["italique"], fontSize=13, leading=17, leftIndent=16, textColor=colors.HexColor("#067647"), spaceAfter=3)}
    lib = dict(ROLES)
    h = [Paragraph(escape(f"{appli} — Guide d'utilisation"), st["t"]),
         Paragraph(escape(("Version " + version + " · ") if version else "") + "LISEZ-MOI" + (f" · {lib.get(role, '')}" if role and role != "tous" else ""), st["s"])]
    for s in sections_pour(role):
        bloc = [Paragraph(escape(s["titre"]), st["h"]), Paragraph(escape("Pour : " + ", ".join(lib[r] for r in s["roles"])), st["r"])]
        if s.get("intro"):
            bloc.append(Paragraph(escape(texte(s["intro"], appli)), st["p"]))
        h.append(KeepTogether(bloc + [Paragraph(escape(texte(s["etapes"][0], appli)), st["e"], bulletText="1.")]))
        h += [Paragraph(escape(texte(e, appli)), st["e"], bulletText=f"{i}.") for i, e in enumerate(s["etapes"][1:], 2)]
        h += [Paragraph(escape("Conseil : " + texte(c, appli)), st["c"]) for c in s.get("conseils") or []]
    h.append(Paragraph("Questions fréquentes et dépannage", st["h"]))
    for qq, r in FAQ:
        h.append(KeepTogether([Paragraph("<b>" + escape(qq) + "</b>", st["p"]), Paragraph(escape(r), st["e"])]))
    h += [Spacer(1, 8), Paragraph(escape("Conception : " + CONTACT), st["r"])]
    buf = io.BytesIO()

    def pied(c, doc):
        c.saveState()
        c.setFont(S["normal"], 9)
        c.setFillColor(colors.HexColor("#667085"))
        c.drawRightString(A4[0] - 18 * mm, 8 * mm, f"Page {doc.page}")
        c.restoreState()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                      title=f"{appli} — Guide d'utilisation", author="GESCOL").build(h, onFirstPage=pied, onLaterPages=pied,
                                                                                       canvasmaker=pdfs.GCanvasPeda)
    return buf.getvalue()


def enregistrer(app, H):
    from flask import render_template, request

    @app.route("/aide/guide")
    @H.connexion_requise()
    def guide_utilisation():
        role = request.args.get("role") or ""
        return render_template("guide_utilisation.html", sections=sections_pour(role), faq=FAQ, roles=ROLES, role=role,
                               lib=dict(ROLES), texte=texte)

    @app.route("/aide/lisez-moi.pdf")
    @H.connexion_requise()
    def guide_pdf():
        import config
        return H.pdf_reponse(pdf(config.NOMS_APPLI.get(config.EDITION, "GESCOL") if hasattr(config, "NOMS_APPLI") else "GESCOL",
                                 config.VERSION, request.args.get("role")), "LISEZ-MOI.pdf")


if __name__ == "__main__":
    import config
    ici = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(ici, "LISEZMOI.md"), "w", encoding="utf-8") as f:
        f.write(markdown(config.NOMS_APPLI.get("privee", "GESCOL") if hasattr(config, "NOMS_APPLI") else "GESCOL", config.VERSION))
    print("LISEZMOI.md écrit")
