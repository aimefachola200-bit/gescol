# -*- coding: utf-8 -*-
"""v2.7 : développement complet des thèmes d'exposé de la bibliothèque (plan détaillé, introduction, développement
axe par axe, conclusion, sources). Le canevas est construit à partir de l'intitulé et des axes de chaque thème,
avec la méthode propre à la discipline."""
import re

ORDINAUX = ["I", "II", "III", "IV", "V", "VI"]

METHODE = {
    "Français": {
        "accroche": "une citation de l'œuvre ou de l'auteur, ou une question sur la place du thème dans la société d'aujourd'hui",
        "contexte": "l'auteur, l'œuvre (date, genre, contexte historique et culturel) et le passage du programme concerné",
        "axe": ["Rappelle brièvement les faits ou la situation dans l'œuvre.",
                "Cite au moins deux passages précis (entre guillemets, avec la page).",
                "Explique ce que le passage révèle (personnages, point de vue, procédés d'écriture).",
                "Termine par une phrase qui répond à la question de l'axe et annonce l'axe suivant."],
        "ouverture": "relier à un autre texte, à la société béninoise actuelle ou à un autre auteur africain",
        "sources": ["L'œuvre au programme (édition de la classe)", "Manuel de Français de la classe", "Encyclopédie ou dictionnaire (définitions et biographie)", "Entretien avec le professeur de lettres"],
    },
    "Histoire-Géographie": {
        "accroche": "un fait marquant, une date, une carte ou une image qui résume le sujet",
        "contexte": "le cadre dans le temps et dans l'espace (dates, lieux, acteurs) et les causes de départ",
        "axe": ["Situe l'axe dans le temps et dans l'espace (dates et lieux exacts).",
                "Présente les acteurs, les faits ou les phénomènes, dans l'ordre.",
                "Explique les causes, puis les conséquences.",
                "Appuie-toi sur un document : carte, frise, tableau ou témoignage."],
        "ouverture": "montrer ce qui reste aujourd'hui de ce passé au Bénin et en Afrique de l'Ouest",
        "sources": ["Manuel d'Histoire-Géographie de la classe", "Atlas et cartes du Bénin et de l'Afrique", "Archives, musée ou personne ressource (témoignage)", "Site officiel de l'institution concernée"],
    },
    "SVT": {
        "accroche": "une observation de la vie courante (un repas, une maladie, un paysage) qui pose la question",
        "contexte": "les notions du programme à connaître et les définitions des mots-clés",
        "axe": ["Définis les termes scientifiques de l'axe.",
                "Décris le phénomène : observation, schéma légendé, résultat d'expérience.",
                "Explique le mécanisme et ses conséquences pour l'être vivant ou le milieu.",
                "Donne un exemple concret de ton environnement."],
        "ouverture": "prévention, hygiène, protection de l'environnement ou gestes à adopter au quotidien",
        "sources": ["Manuel de SVT de la classe", "Documents du ministère de la Santé ou de l'environnement", "Enquête ou observation réalisée par le groupe", "Livre ou encyclopédie scientifique du CDI"],
    },
    "Physique-Chimie": {
        "accroche": "un objet ou une situation de la vie courante (lampe, pile, eau, aliment) qui pose le problème",
        "contexte": "les grandeurs, unités et lois du programme nécessaires",
        "axe": ["Énonce la définition ou la loi, avec l'unité.",
                "Présente l'expérience ou le schéma (matériel, protocole, résultat).",
                "Fais un calcul ou une application numérique.",
                "Indique la règle de sécurité ou l'usage pratique."],
        "ouverture": "économies d'énergie, sécurité, métiers ou technologies liés au thème",
        "sources": ["Manuel de Physique-Chimie de la classe", "Notice de sécurité ou fiche technique", "Expérience réalisée en classe ou au laboratoire", "Site éducatif ou encyclopédie scientifique"],
    },
    "Mathématiques": {
        "accroche": "un problème concret à résoudre (mesurer, partager, calculer) qui motive les notions",
        "contexte": "les définitions, les notations et les propriétés à connaître",
        "axe": ["Énonce la propriété ou le théorème avec ses hypothèses.",
                "Donne la démonstration ou la justification, étape par étape.",
                "Traite un exemple numérique complet.",
                "Propose une application concrète ou un exercice corrigé."],
        "ouverture": "d'autres applications (métiers, construction, mesure) ou un prolongement du programme",
        "sources": ["Manuel de Mathématiques de la classe", "Cahier d'exercices et corrigés du professeur", "Mesures ou activité menées par le groupe", "Site éducatif de référence"],
    },
    "Philosophie": {
        "accroche": "une situation, une citation ou un paradoxe qui fait naître la question",
        "contexte": "les mots-clés à définir, leurs sens courants et philosophiques",
        "axe": ["Pose la question de l'axe et définis les notions.",
                "Expose une thèse et l'auteur qui la défend.",
                "Présente un argument et un exemple.",
                "Discute une objection puis conclus l'axe."],
        "ouverture": "une question voisine ou une situation actuelle au Bénin",
        "sources": ["Manuel ou textes d'auteurs de la classe", "Dictionnaire de philosophie", "Œuvre citée (extraits)", "Entretien avec le professeur de philosophie"],
    },
}
METHODE_DEFAUT = {
    "accroche": "une situation concrète, un chiffre ou une question qui introduit le sujet",
    "contexte": "les définitions et notions du programme nécessaires pour comprendre le sujet",
    "axe": ["Définis les mots-clés de l'axe.", "Explique le point principal avec des faits précis.",
            "Illustre par un exemple local ou un document.", "Conclus l'axe par une phrase et annonce le suivant."],
    "ouverture": "ce que le sujet change dans la vie quotidienne ou dans un autre domaine",
    "sources": ["Manuel de la discipline", "Livres du CDI ou de la bibliothèque", "Entretien avec un spécialiste ou le professeur", "Site éducatif ou officiel (cité avec la date de consultation)"],
}


def _axes(txt):
    return [a.strip(" .") for a in re.split(r"\s*[;\n]\s*", txt or "") if a.strip(" .")]


def _maj(t):
    return t[:1].upper() + t[1:] if t else t


def canevas(e):
    """e = (matière, niveaux, titre, axes, consigne) -> dict(plan, introduction, developpement[], conclusion, sources)."""
    mat, _niv, titre, axes_txt, consigne = e[:5]
    m = METHODE.get(mat, METHODE_DEFAUT)
    ax = _axes(axes_txt) or [titre]
    plan = ["Introduction"] + [f"{ORDINAUX[i]}. {_maj(a)}" for i, a in enumerate(ax[:6])] + ["Conclusion", "Sources"]
    nb = len(ax[:6])
    intro = [f"Accroche : commence par {m['accroche']}.",
             f"Présentation du sujet : « {titre} ». Rappelle {m['contexte']}.",
             f"Problématique : formule une seule question qui relie les axes (exemple : « {titre} : quels en sont les enjeux ? »).",
             "Annonce du plan : « Nous verrons d'abord " + ax[0][:1].lower() + ax[0][1:]
             + (", puis " + ", puis ".join(a[:1].lower() + a[1:] for a in ax[1:6]) if nb > 1 else "") + ". »"]
    dev = []
    for i, a in enumerate(ax[:6]):
        dev.append({"titre": f"{ORDINAUX[i]}. {_maj(a)}",
                    "etapes": [s for s in m["axe"]] + ([f"Conseil du professeur : {consigne}"] if consigne and i == 0 else [])})
    concl = ["Bilan : réponds à la problématique en 3 ou 4 phrases, un point par axe (" + " ; ".join(a[:1].lower() + a[1:] for a in ax[:6]) + ").",
             f"Ouverture : propose {m['ouverture']}.",
             "Termine par une phrase de remerciement ou une question pour la classe."]
    return {"plan": plan, "introduction": intro, "developpement": dev, "conclusion": concl, "sources": list(m["sources"]),
            "mots": "Durée conseillée : 10 minutes à l'oral ; 3 à 5 pages à l'écrit."}


def texte_plan(c):
    return "\n".join(c["plan"])


def texte_guide(c, cle):
    """Texte à placer dans une section (guide de rédaction)."""
    if cle == "plan":
        return texte_plan(c)
    if cle == "introduction":
        return "\n".join(c["introduction"])
    if cle == "conclusion":
        return "\n".join(c["conclusion"])
    if cle == "sources":
        return "\n".join("– " + s for s in c["sources"])
    return "\n\n".join(d["titre"] + "\n" + "\n".join("– " + s for s in d["etapes"]) for d in c["developpement"])
