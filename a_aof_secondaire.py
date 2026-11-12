# -*- coding: utf-8 -*-
"""v2.5.0 : structure des autorités du secondaire d'après le décret n° 2016-427 du 20 juillet 2016 portant attributions, organisation et
fonctionnement du Ministère des Enseignements Secondaire, Technique et de la Formation Professionnelle (MESTFP).

Dans les applications du secondaire (éditions « sec_… »), les services par défaut des deux niveaux de supervision viennent de ce décret :
  - DDESTFP (niveau « ddemp ») : Directeur départemental (art. 80, 82, 84) + Secrétariat, Service de l'enseignement secondaire, de la
    formation technique et professionnelle, Service des examens et concours, Service de l'administration et des finances (art. 83)
    + Inspection pédagogique déléguée (art. 85, 86) ;
  - Inspection de l'enseignement secondaire (niveau « cs ») : l'Inspecteur pédagogique délégué et son pool d'inspecteurs (art. 85, 86), qui rendent
    compte au Directeur de l'inspection pédagogique, de l'innovation et de la qualité (art. 74 à 79).
Les codes de service restent ceux du primaire (ccs, cp, secretariat, personnel, animation, administration, direction, sec…) : rien d'autre ne change."""
import config

DECRET = "Décret n° 2016-427 du 20 juillet 2016 (MESTFP)"
SOURCE = DECRET + " – article {n}"

_IPD = ("L'Inspection pédagogique déléguée appuie la Direction départementale dans sa mission d'assurance qualité dans le département. Elle est chargée de :\n"
        "- contribuer à élaborer la stratégie de mise en place d'une chaîne de redevabilité claire, de l'échelon local d'enseignement à l'échelon central ;\n"
        "- contrôler la qualité, l'adéquation des plans et objectifs de formation et la mise en œuvre des programmes avec les objectifs pédagogiques initiaux ;\n"
        "- contribuer à élaborer et à exécuter les plans d'inspection et de contrôle qualité pédagogique du personnel enseignant et des établissements ;\n"
        "- définir les objectifs et les modalités de l'animation pédagogique, en liaison avec les directions concernées ;\n"
        "- promouvoir les innovations pédagogiques et évaluer la qualité de la production des matériels pédagogiques des apprenants et à l'intention des enseignants ;\n"
        "- veiller à l'organisation, à la qualité et à la certification des programmes d'études, en liaison avec les structures compétentes.\n"
        "L'Inspecteur pédagogique délégué travaille en étroite collaboration avec le Directeur départemental et rend compte au Directeur de l'inspection "
        "pédagogique, de l'innovation et de la qualité.")

_DD = ("Le Directeur départemental des enseignements secondaire, technique et de la formation professionnelle dirige la Direction départementale, "
       "démembrement territorial du Ministère responsable de la mise en œuvre, dans le département, de la politique de l'enseignement secondaire, de la "
       "formation technique et professionnelle. Il assure aussi l'assistance technique et l'appui-conseil aux Communes dans son domaine. Il est chargé, "
       "en fonction des critères approuvés par le Ministre, de :\n"
       "- mettre en œuvre les plans sectoriels de formation continue et d'animation pédagogique, et veiller à l'orientation optimale des élèves et apprenants ;\n"
       "- organiser avec la population locale des forums citoyens pour le suivi de la qualité et de la mise en œuvre des stratégies d'animation pédagogique ;\n"
       "- participer à la surveillance des programmes de formation dans les établissements privés ;\n"
       "- proposer la carte scolaire du département ;\n"
       "- promouvoir la scolarisation, les activités culturelles et sportives pour tous, notamment les enfants à besoins spécifiques ;\n"
       "- prononcer les affectations du personnel mis à sa disposition et procéder aux mutations intra-départementales.\n"
       "Il relève du Secrétaire général du ministère ; dans le département, il est placé sous l'autorité du Préfet et participe à la conférence "
       "administrative départementale. Il est nommé par décret en Conseil des ministres parmi les Inspecteurs de l'enseignement du second degré "
       "ayant au moins trois ans d'ancienneté.")

SERVICES = {
    "ddemp": [
        ("direction", "Directeur départemental des enseignements secondaire, technique et de la formation professionnelle", "DDESTFP", 1, "", "Article 80",
         _DD, "Source : " + DECRET + ", articles 80, 82 et 84.", "Le Directeur Départemental"),
        ("secretariat", "Secrétariat", "SEC.", 2, "direction", "Article 83",
         "Le Secrétariat reçoit, enregistre et ventile le courrier, met en forme et expédie les correspondances de la Direction départementale et tient son agenda.",
         "Le décret (art. 83) crée le Secrétariat sans en détailler les tâches : attributions rédigées par GESCOL.", "Le Chef du Secrétariat"),
        ("sestfp", "Service de l'enseignement secondaire, de la formation technique et professionnelle", "SESTFP", 3, "direction", "Article 83",
         "Le Service de l'enseignement secondaire, de la formation technique et professionnelle est chargé de :\n"
         "- suivre le fonctionnement pédagogique et administratif des établissements secondaires, techniques et professionnels, publics et privés ;\n"
         "- tenir la carte scolaire et proposer l'ouverture, le regroupement ou la fermeture d'établissements ;\n"
         "- suivre les effectifs, les orientations et l'organisation de la rentrée ;\n"
         "- participer à la surveillance des programmes de formation dans les établissements privés.",
         "Le décret (art. 83, 82) crée le service ; ses tâches sont tirées de l'article 82 et complétées par GESCOL.", "Le Chef du Service de l'enseignement secondaire, technique et professionnel"),
        ("sec", "Service des examens et concours", "SEC", 4, "direction", "Article 83",
         "Le Service des examens et concours est chargé de :\n"
         "- organiser, avec les établissements, le BEPC, le baccalauréat, les examens de la formation technique et professionnelle et les concours ;\n"
         "- recenser les candidats, constituer les centres d'examen et désigner les chefs de centre ;\n"
         "- assurer la sécurité des épreuves, la correction, les délibérations et la proclamation des résultats ;\n"
         "- établir les statistiques des examens et délivrer les relevés de notes et attestations de réussite.",
         "Le décret (art. 83) crée le service sans en détailler les tâches : attributions rédigées par GESCOL.", "Le Chef du Service des examens et concours"),
        ("administration", "Service de l'administration et des finances", "SAF", 5, "direction", "Article 83",
         "Le Service de l'administration et des finances gère le personnel mis à la disposition de la Direction départementale (affectations, mutations "
         "intra-départementales, dossiers), le budget, le matériel et le patrimoine, et prépare les états financiers.",
         "Le décret (art. 83, 82) crée le service ; attributions tirées de l'article 82 et complétées par GESCOL.", "Le Chef du Service de l'administration et des finances"),
        ("ipd", "Inspection pédagogique déléguée", "IPD", 6, "direction", "Article 85", _IPD,
         "L'Inspection pédagogique déléguée est instituée dans chaque Direction départementale : un Inspecteur pédagogique délégué (rang de Chef de service, nommé par "
         "arrêté du Ministre) et un pool d'Inspecteurs.", "L'Inspecteur Pédagogique Délégué"),
    ],
    "cs": [
        ("ccs", "Inspecteur pédagogique délégué (chef de l'Inspection)", "IPD", 1, "", "Article 85", _IPD,
         "L'Inspecteur pédagogique délégué a rang de Chef de service ; il est nommé par arrêté du Ministre sur proposition du Directeur de l'inspection pédagogique, "
         "de l'innovation et de la qualité (art. 86).", "L'Inspecteur Pédagogique Délégué"),
        ("cp", "Inspecteurs pédagogiques (pool)", "IP", 2, "ccs", "Article 85",
         "Les Inspecteurs, placés sous la direction de l'Inspecteur pédagogique délégué, sont chargés de :\n"
         "- inspecter les enseignants (visites de classe, de conseil et d'inspection) et contrôler la gestion pédagogique des établissements publics et privés ;\n"
         "- animer les cellules et regroupements pédagogiques par discipline ;\n"
         "- contrôler la mise en œuvre des programmes d'études et l'évaluation des apprentissages ;\n"
         "- rendre compte à l'Inspecteur pédagogique délégué (rapports d'inspection, bilans).",
         "Tâches tirées des articles 75 et 85 du décret.", "L'Inspecteur Pédagogique"),
        ("secretariat", "Secrétariat de l'Inspection", "SEC.", 3, "ccs", "", "Le Secrétariat reçoit et expédie le courrier de l'Inspection, tient l'agenda et les dossiers des inspections.",
         "Rédigé par GESCOL (non prévu par le décret).", "Le Secrétaire de l'Inspection"),
        ("personnel", "Suivi du personnel des établissements", "RH", 4, "ccs", "", "Suit le personnel enseignant et administratif des établissements de la zone d'inspection (effectifs, absences, mouvements) et prépare les états à transmettre à la Direction départementale.",
         "Rédigé par GESCOL (non prévu par le décret).", "Le Responsable du suivi du personnel"),
        ("animation", "Animation pédagogique", "AP", 5, "ccs", "Article 85",
         "Définit, avec la Direction départementale, les objectifs et modalités de l'animation pédagogique ; organise les formations continues, les journées pédagogiques "
         "et la diffusion des innovations pédagogiques.", "Tâches tirées des articles 75 et 85 du décret.", "Le Responsable de l'animation pédagogique"),
        ("administration", "Administration et soutien", "ADM", 6, "ccs", "", "Gère le matériel, les déplacements et l'intendance de l'Inspection.",
         "Rédigé par GESCOL (non prévu par le décret).", "Le Responsable de l'administration"),
    ],
}

SERVICES_PERSONNEL = {
    "cs": [("ccs", "Inspecteur pédagogique délégué"), ("cp", "Inspecteurs pédagogiques (pool)"), ("secretariat", "Secrétariat de l'Inspection"),
           ("personnel", "Suivi du personnel des établissements"), ("animation", "Animation pédagogique"), ("administration", "Administration et soutien")],
    "ddemp": [("direction", "Directeur départemental (DDESTFP)"), ("secretariat", "Secrétariat"),
              ("sestfp", "Service de l'enseignement secondaire, technique et professionnel (SESTFP)"),
              ("sec", "Service des examens et concours (SEC)"), ("administration", "Service de l'administration et des finances (SAF)"),
              ("ipd", "Inspection pédagogique déléguée (IPD)")],
}
POSTES = {
    "cs": ["Inspecteur pédagogique délégué", "Inspecteur pédagogique", "Secrétaire", "Agent d'entretien", "Gardien", "Chauffeur", "Planton"],
    "ddemp": ["Directeur Départemental (DDESTFP)", "Directeur Départemental Adjoint", "Inspecteur pédagogique délégué", "Inspecteur pédagogique",
              "Chef du Service de l'enseignement secondaire, technique et professionnel", "Chef du Service des examens et concours",
              "Chef du Service de l'administration et des finances", "Secrétaire", "Agent d'entretien", "Gardien", "Chauffeur", "Planton"],
}


def appliquer_structure(S):
    if not config.secondaire():
        return
    S.SERVICES_DEFAUT.update(SERVICES)
    S.AOF = DECRET + " portant attributions, organisation et fonctionnement du Ministère des Enseignements Secondaire, Technique et de la Formation Professionnelle"
    S.SOURCE_AOF = SOURCE


def appliquer_personnel(P):
    if not config.secondaire():
        return
    P.SERVICES_DEFAUT.update(SERVICES_PERSONNEL)
    P.POSTES.update(POSTES)
