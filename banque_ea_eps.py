# -*- coding: utf-8 -*-
"""v1.30 — Épreuves d'Éducation artistique (A : dessin / arts plastiques ; B : couture / travaux manuels) et d'EPS
(épreuves pratiques : course de vitesse + saut, lancer ou jeu ; barèmes filles / garçons par âge, fiche de notation).

Rédaction originale (aucune reprise de document marqué) — barèmes indicatifs, à adapter par le conseil des maîtres.
"""

GROUPE = {"CI": "P", "CP": "P", "CE1": "E", "CE2": "E", "CM1": "M", "CM2": "M"}

# ------------------------------------------------------------------ EA : (titre, contexte, tâche, matériel, consignes, indicateur technique)
DESSIN = {
    "P": [("Dessin — un fruit", "La classe prépare un panier de fruits pour la fête.", "Tu es invité à dessiner et à colorier une mangue.", "feuille de dessin, crayon, crayons de couleur",
           ["Dessine une grosse mangue au milieu de la feuille.", "Colorie-la en jaune et en vert sans dépasser.", "Écris ton prénom en bas."], "le contour est fermé et le coloriage est régulier"),
          ("Dessin — ma maison", "Tu veux montrer ta maison à ton correspondant.", "Tu es invité à dessiner ta maison.", "feuille, crayon, crayons de couleur",
           ["Dessine la maison avec une porte et une fenêtre.", "Ajoute un arbre à côté.", "Colorie proprement."], "les formes (carré, triangle) sont reconnaissables"),
          ("Dessin — le drapeau", "C'est la fête de l'indépendance.", "Tu es invité à dessiner le drapeau du Bénin.", "feuille, règle, crayon, crayons vert, jaune, rouge",
           ["Trace un rectangle à la règle.", "Place la bande verte à gauche, le jaune en haut, le rouge en bas.", "Colorie sans dépasser."], "les trois couleurs sont à la bonne place"),
          ("Dessin — un animal", "Le maître affiche les animaux de la ferme.", "Tu es invité à dessiner une poule.", "feuille, crayon, crayons de couleur",
           ["Dessine la poule avec son bec, ses pattes et sa queue.", "Dessine deux œufs à côté.", "Colorie ton dessin."], "les parties de l'animal sont présentes"),
          ("Arts plastiques — frise", "Tu veux décorer le bord de ton cahier.", "Tu es invité à réaliser une frise de formes.", "bande de papier, crayon, crayons de couleur",
           ["Dessine une suite : rond, carré, rond, carré…", "Colorie les ronds en rouge et les carrés en bleu.", "Continue jusqu'au bout de la bande."], "la suite est respectée sans erreur"),
          ("Dessin — le soleil et la pluie", "C'est la saison des pluies.", "Tu es invité à dessiner un ciel avec un nuage et la pluie.", "feuille, crayon, crayons de couleur",
           ["Dessine un nuage et des gouttes de pluie.", "Dessine un enfant sous un parapluie.", "Colorie ton dessin."], "les éléments demandés sont présents et lisibles")],
    "E": [("Dessin — la calebasse décorée", "Ton village organise la fête de l'igname.", "Tu es invité à dessiner une calebasse décorée.", "feuille de dessin, crayon, gomme, crayons de couleur",
           ["Dessine une calebasse de 10 cm de large.", "Décore-la de motifs géométriques (triangles, losanges).", "Colorie avec trois couleurs au moins."], "les motifs sont réguliers et bien répartis"),
          ("Dessin — carte de remerciement", "Tu veux remercier ton maître.", "Tu es invité à réaliser une carte de remerciement.", "carton, règle, crayon, crayons de couleur",
           ["Trace un rectangle de 12 cm sur 8 cm.", "Dessine une fleur au centre.", "Écris « Merci maître » en lettres capitales."], "les mesures sont respectées ; l'écriture est lisible"),
          ("Arts plastiques — motif symétrique", "La classe décore le mur de l'exposition.", "Tu es invité à réaliser un motif symétrique.", "papier quadrillé, crayon, règle, crayons de couleur",
           ["Trace un axe au milieu de la feuille.", "Dessine un motif d'un côté de l'axe.", "Reproduis son symétrique de l'autre côté et colorie."], "le symétrique est exact (même distance à l'axe)"),
          ("Dessin — un objet de la classe", "Le maître demande de dessiner d'après nature.", "Tu es invité à dessiner la cruche de la classe d'après nature.", "feuille, crayon, gomme",
           ["Observe la cruche posée sur la table.", "Dessine-la en respectant sa forme et ses proportions.", "Ombre le côté qui n'est pas éclairé."], "les proportions et l'ombre sont justes"),
          ("Dessin — l'illustration d'un proverbe", "C'est la semaine de la culture.", "Tu es invité à illustrer le proverbe « Petit à petit, l'oiseau fait son nid ».", "feuille, crayon, crayons de couleur",
           ["Écris le proverbe en haut de la feuille.", "Dessine une scène qui l'illustre.", "Colorie ton dessin."], "la scène correspond au sens du proverbe"),
          ("Arts plastiques — affiche de propreté", "L'école lance une campagne de propreté.", "Tu es invité à réaliser une petite affiche.", "feuille, règle, crayon, crayons de couleur",
           ["Trace un cadre à 1 cm du bord.", "Dessine un enfant qui jette un papier dans la poubelle.", "Écris un slogan court en lettres capitales."], "le dessin et le slogan transmettent le message")],
    "M": [("Dessin — carte de vœux", "C'est bientôt les fêtes de fin d'année. Tu veux envoyer tes vœux à un parent.", "Tu es invité à réaliser une carte de vœux.", "carton, règle, crayon, crayons de couleur ou gouaches",
           ["Trace au centre de ta feuille un rectangle de 15 cm sur 10 cm.", "Trace une bordure de 1 cm coloriée à ton choix.", "Inscris ton vœu en écriture script majuscule.", "Veille à la bonne gestion de l'espace."], "mesures exactes, bordure régulière, lettrage soigné"),
          ("Dessin — affiche de reboisement", "La commune lance une campagne de reboisement.", "Tu es invité à réaliser une affiche pour le reboisement.", "feuille de dessin, règle, crayon, crayons de couleur",
           ["Trace le cadre de l'affiche (20 cm sur 15 cm).", "Dessine un jeune plant protégé par un tuteur.", "Écris un slogan en lettres calligraphiées."], "composition équilibrée ; slogan lisible et pertinent"),
          ("Dessin — un droit de l'enfant", "Les droits de l'enfant doivent être connus de tous.", "Tu es invité à réaliser un dessin sur un droit de l'enfant.", "feuille, crayon, crayons de couleur",
           ["Choisis un droit de l'enfant et écris-le en titre.", "Illustre-le par une scène de la vie courante.", "Écris un message de sensibilisation au bas du dessin."], "la scène illustre clairement le droit choisi"),
          ("Dessin — nature morte", "Le club d'arts prépare une exposition.", "Tu es invité à dessiner d'après nature une nature morte (un canari et deux fruits).", "feuille, crayon HB, gomme",
           ["Observe la disposition des objets.", "Dessine-les en respectant les proportions et les plans.", "Indique les ombres par des hachures."], "proportions, plans et ombres justes"),
          ("Arts plastiques — motif d'appliqué", "Les tentures d'Abomey racontent l'histoire des rois.", "Tu es invité à créer un motif inspiré des tentures appliquées.", "papier de couleur, ciseaux, colle, feuille de fond",
           ["Dessine un animal symbole sur le papier de couleur.", "Découpe-le et colle-le sur le fond.", "Ajoute une bordure de triangles découpés."], "découpage précis et collage propre"),
          ("Calligraphie — message de fête", "C'est la fête de Pâques ou de Tabaski.", "Tu es invité à calligraphier un message de fête.", "feuille, règle, crayon, feutres",
           ["Trace des lignes guides de 2 cm.", "Calligraphie « Bonne fête à tous ».", "Décore les initiales."], "lettres régulières, alignées et décorées")],
}
TRAVAUX = {
    "P": [("Travaux manuels — collage", "Tu veux décorer ta classe.", "Tu es invité à faire un collage en forme de fleur.", "papiers de couleur, colle, feuille de fond",
           ["Déchire des petits morceaux de papier.", "Colle-les pour former une fleur.", "Colle une tige verte."], "les morceaux sont collés sans débordement"),
          ("Travaux manuels — pliage", "La classe fabrique des chapeaux pour la fête.", "Tu es invité à plier un chapeau en papier.", "feuille de papier journal",
           ["Plie la feuille en deux.", "Rabats les deux coins vers le milieu.", "Replie les bandes du bas."], "les plis sont nets et le chapeau tient"),
          ("Modelage — fruits en argile", "Le maître prépare un marché pour jouer.", "Tu es invité à modeler deux fruits.", "argile ou pâte à modeler, planchette",
           ["Modèle une orange (boule).", "Modèle une banane (boudin courbé).", "Pose-les sur la planchette."], "les formes sont reconnaissables et lisses"),
          ("Travaux manuels — étiquette", "Le jardin de l'école a besoin d'étiquettes.", "Tu es invité à fabriquer une étiquette en carton.", "carton, ciseaux, crayon, ficelle",
           ["Découpe un rectangle.", "Écris le nom d'une plante.", "Perce un trou et passe la ficelle."], "découpage droit ; écriture lisible"),
          ("Travaux manuels — natte de papier", "La classe prépare une exposition.", "Tu es invité à tresser une petite natte en bandes de papier.", "bandes de papier de deux couleurs, colle",
           ["Prends trois bandes de chaque couleur.", "Tresse-les en passant dessus, dessous.", "Colle les bouts."], "le tressage dessus-dessous est régulier"),
          ("Enfilage — collier de perles", "Tu veux offrir un cadeau à maman.", "Tu es invité à enfiler un collier.", "perles ou graines percées, fil",
           ["Enfile une perle rouge, puis une perle jaune.", "Continue la suite jusqu'au bout du fil.", "Noue les deux bouts avec l'aide du maître."], "la suite des couleurs est respectée")],
    "E": [("Couture — ourlet au point de devant", "Ta poupée a besoin d'un mouchoir.", "Tu es invité à réaliser un ourlet au point de devant.", "carré de tissu de 10 cm, aiguille, fil, ciseaux",
           ["Découpe un carré de tissu de 10 cm.", "Replie deux fois les bords de 0,5 cm.", "Couds au point de devant, à petits points réguliers."], "points réguliers et alignés ; ourlet plat"),
          ("Couture — coudre un bouton", "Le bouton de ta chemise est tombé.", "Tu es invité à coudre un bouton sur un morceau de tissu.", "morceau de tissu, bouton à deux trous, aiguille, fil",
           ["Enfile l'aiguille et fais un nœud.", "Place le bouton et couds en passant six fois dans chaque trou.", "Arrête le fil par un nœud sur l'envers."], "bouton solide, bien centré, nœud d'arrêt"),
          ("Vannerie — petit panier", "La coopérative vend des objets fabriqués par les élèves.", "Tu es invité à tresser un petit panier en raphia ou en feuilles de palmier.", "raphia ou feuilles de palmier, ciseaux",
           ["Prépare huit brins de même longueur.", "Croise-les et tresse le fond.", "Relève les brins et tresse le bord."], "tressage serré et régulier"),
          ("Modelage — un canari", "Tu découvres le travail des potières.", "Tu es invité à modeler un petit canari en argile.", "argile, eau, planchette",
           ["Modèle une boule et creuse-la avec les pouces.", "Monte les bords avec un colombin.", "Lisse la surface et décore au bâtonnet."], "forme régulière, parois d'épaisseur égale"),
          ("Couture — point arrière", "Tu répares la poche d'un pantalon.", "Tu es invité à assembler deux morceaux de tissu au point arrière.", "deux morceaux de tissu, aiguille, fil, épingles",
           ["Épingle les deux morceaux endroit contre endroit.", "Couds une ligne droite au point arrière à 1 cm du bord.", "Retourne et repasse avec la main."], "couture droite, points serrés et réguliers"),
          ("Travaux manuels — boîte en carton", "Tu veux ranger tes crayons.", "Tu es invité à fabriquer une boîte à crayons à partir d'un patron.", "carton, règle, crayon, ciseaux, colle",
           ["Trace le patron d'un pavé (faces de 6 cm et 4 cm).", "Découpe-le et marque les plis.", "Plie et colle les languettes."], "patron exact ; arêtes nettes ; collage propre")],
    "M": [("Couture — assemblage au point de piqûre", "Ta petite sœur veut une jupe pour sa poupée.", "Tu es invité à assembler deux pièces de tissu au point de piqûre.", "deux pièces de tissu, aiguille, fil, ciseaux, épingles",
           ["Découpe deux pièces de 10 cm sur 5 cm.", "Assemble-les dans le sens de la longueur.", "Utilise le point de piqûre.", "Fixe ta production à la feuille."], "points de piqûre serrés, réguliers, en ligne droite"),
          ("Broderie — initiales au point de tige", "Tu offres un cadeau à ta maîtresse.", "Tu es invité à broder ses initiales au point de tige.", "tissu, aiguille, fil à broder, crayon",
           ["Trace les initiales sur le tissu.", "Brode au point de tige.", "Fais un ourlet autour du tissu."], "tracé suivi exactement ; points réguliers"),
          ("Couture — porte-monnaie", "La coopérative prépare la kermesse.", "Tu es invité à coudre un petit porte-monnaie.", "tissu de 20 cm sur 10 cm, aiguille, fil, bouton",
           ["Plie le tissu pour former une poche de 8 cm de haut.", "Couds les côtés au point arrière.", "Couds un bouton et fais une boutonnière simple."], "côtés solides ; fermeture fonctionnelle"),
          ("Vannerie — dessous-de-plat", "Ta mère a besoin d'un dessous-de-plat.", "Tu es invité à tresser un dessous-de-plat en raphia.", "raphia, aiguille à grand chas, ciseaux",
           ["Tresse une longue natte de raphia.", "Enroule-la en spirale.", "Couds les rangs entre eux."], "spirale plate et régulière ; coutures invisibles"),
          ("Travaux manuels — maquette", "La classe étudie l'habitat du Bénin.", "Tu es invité à construire la maquette d'une case.", "carton, paille, colle, ciseaux, règle",
           ["Trace et découpe les murs (patron d'un cylindre ou d'un pavé).", "Assemble les murs.", "Fabrique un toit de paille et pose-le."], "proportions respectées ; assemblage solide"),
          ("Couture — point de croix", "Tu décores un napperon pour la table.", "Tu es invité à broder un motif au point de croix.", "tissu à trame, aiguille, fil de deux couleurs",
           ["Compte les carreaux et repère le centre.", "Brode un motif de 10 croix sur 10.", "Termine par une bordure au point de devant."], "croix régulières, toutes dans le même sens")],
}


def ea(cours, k):
    """Épreuve d'EA en deux parties (A : dessin / arts plastiques ; B : couture / travaux manuels) pour la période de rang k."""
    gpe = GROUPE[cours]
    a = DESSIN[gpe][k % len(DESSIN[gpe])]
    b = TRAVAUX[gpe][(k + 2) % len(TRAVAUX[gpe])]
    return a, b


def grille_ea(partie, entree, pts=10):
    titre, _c, _t, _m, consignes, technique = entree
    return [{"critere": f"{partie} — Respect des consignes", "indicateurs": consignes, "points": 3 * pts / 10},
            {"critere": f"{partie} — Maîtrise de la technique", "indicateurs": [technique], "points": 3 * pts / 10},
            {"critere": f"{partie} — Propreté et finition", "indicateurs": ["travail propre, sans tache ni rature", "réalisation achevée dans le temps"], "points": 2 * pts / 10},
            {"critere": f"{partie} — Créativité et originalité", "indicateurs": ["touche personnelle", "choix harmonieux (couleurs, matériaux)"], "points": 2 * pts / 10}]


# ------------------------------------------------------------------ EPS
AGE = {"CI": 6, "CP": 7, "CE1": 8, "CE2": 9, "CM1": 10, "CM2": 11}
COURSE = {"CI": 20, "CP": 30, "CE1": 40, "CE2": 50, "CM1": 60, "CM2": 60}
VITESSE = {"CI": 4.0, "CP": 4.3, "CE1": 4.6, "CE2": 4.9, "CM1": 5.2, "CM2": 5.5}          # m/s, garçon d'âge normal, note 10
SAUT = {"CI": 1.10, "CP": 1.20, "CE1": 2.20, "CE2": 2.50, "CM1": 2.80, "CM2": 3.10}       # m (CI, CP : pieds joints sans élan)
LANCER = {"CI": 8, "CP": 10, "CE1": 13, "CE2": 16, "CM1": 19, "CM2": 22}                  # m (balle de 150 g)
JEUX = {"P": ("Jeu de l'épervier", "Les « éperviers » au centre du terrain essaient de toucher les « oiseaux » qui traversent ; l'oiseau touché devient épervier."),
        "E": ("Relais navette 4 × 20 m", "Par équipes de quatre, chacun parcourt 20 m et touche la main du suivant ; on observe la vitesse et la transmission."),
        "M": ("Mini-handball (2 × 5 min)", "Deux équipes de cinq ; marquer en lançant le ballon dans le but adverse, sans contact ni marcher avec le ballon.")}
NOTES = [10, 8, 6, 4, 2]


def _f(x, unite):
    s = f"{x:.1f}".replace(".", ",") if unite == "s" else f"{x:.2f}".replace(".", ",")
    return s + (" s" if unite == "s" else " m")


def _lignes(base, pas, unite, plus_petit_mieux):
    """base : performance pour la note 10 ; pas : écart entre deux notes."""
    out = []
    for i, n in enumerate(NOTES):
        if plus_petit_mieux:
            v = base + pas * i
            out.append("≤ " + _f(v, unite) if i < 4 else "> " + _f(base + pas * 3, unite))
        else:
            v = base - pas * i
            out.append("≥ " + _f(v, unite) if i < 4 else "< " + _f(base - pas * 3, unite))
    return out


def bareme(titre, unite, g_norm, pas, plus_petit_mieux, fille, plus_age):
    """Tableau note / garçons (âge normal, âge + 2) / filles (âge normal, âge + 2)."""
    cols = []
    for sexe in (1.0, fille):
        for age in (1.0, plus_age):
            b = g_norm * sexe * age if not plus_petit_mieux else g_norm / sexe / age
            cols.append(_lignes(b, pas * (1 / sexe if plus_petit_mieux else sexe), unite, plus_petit_mieux))
    return {"titre": titre, "unite": unite, "lignes": [[n] + [c[i] for c in cols] for i, n in enumerate(NOTES)]}


def eps(cours, k):
    """(épreuves, barèmes) : course de vitesse + (saut | lancer | jeu) selon la période de rang k."""
    d = COURSE[cours]
    t10 = d / VITESSE[cours]
    course = bareme(f"Course de vitesse — {d} m (temps)", "s", t10, 0.6 * d / 40, True, 0.93, 1.06)
    deux = ["saut", "lancer", "jeu"][k % 3]
    if deux == "saut":
        lib = "Saut à pieds joints sans élan" if cours in ("CI", "CP") else "Saut en longueur avec élan"
        b2 = bareme(f"{lib} (meilleur de 3 essais)", "m", SAUT[cours], SAUT[cours] * 0.08, False, 0.90, 1.08)
        e2 = (lib, "Trois essais ; on mesure du bord de la planche (ou de la ligne) à la trace la plus proche ; on garde le meilleur.")
    elif deux == "lancer":
        lib = "Lancer de balle (150 g)"
        b2 = bareme(f"{lib} (meilleur de 3 essais)", "m", LANCER[cours], LANCER[cours] * 0.12, False, 0.80, 1.10)
        e2 = (lib, "Trois lancers à une main derrière la ligne ; on mesure la distance du premier point de chute ; on garde le meilleur.")
    else:
        lib, regle = JEUX[GROUPE[cours]]
        b2 = {"titre": f"{lib} — grille d'observation", "unite": "", "lignes": [
            ["Participation active", "2,5", "", "", ""], ["Respect des règles et de l'arbitre", "2,5", "", "", ""],
            ["Coopération avec les partenaires", "2,5", "", "", ""], ["Efficacité (déplacements, passes, buts, vitesse)", "2,5", "", "", ""]],
            "observation": True}
        e2 = (lib, regle)
    return {"course": (f"Course de vitesse sur {d} m", f"Départ debout au signal ; chaque élève court seul ou par deux dans son couloir ; temps au chronomètre."),
            "deux": e2, "type2": deux, "baremes": [course, b2], "age": AGE[cours]}


FICHE_COLONNES = ["N°", "Nom et prénoms", "Sexe", "Âge", "Course (temps)", "Note /10", "Épreuve 2 (perf.)", "Note /10", "Total /20"]


# ------------------------------------------------------------------ v1.32 : référentiel des barèmes EPS proposés (CI → CM2)
# Barèmes originaux « proposés — à valider » (conseil des maîtres, conseiller pédagogique d'EPS) : performance attendue pour la
# note 10 d'un garçon d'âge normal du cours, puis paliers de 2 points ; colonnes filles et élèves plus âgés (âge + 2 ans et plus)
# ajustées. Ils restent cohérents avec les SA d'EPS des guides officiels (course, sauts, lancers, gymnastique, jeux).
MENTION_BAREME = "Barème proposé — à valider par le conseil des maîtres et le conseiller pédagogique d'EPS."
ENDURANCE = {"CI": 300, "CP": 400, "CE1": 500, "CE2": 600, "CM1": 800, "CM2": 1000}                 # m
ENDURANCE_VITESSE = {"CI": 2.6, "CP": 2.75, "CE1": 2.9, "CE2": 3.0, "CM1": 3.1, "CM2": 3.2}         # m/s, note 10
HAUTEUR = {"CE1": 0.75, "CE2": 0.85, "CM1": 0.95, "CM2": 1.05}                                     # m (saut en hauteur, ciseau)
ADAPTATIONS = [
    "Élève dispensé (certificat médical ou avis écrit des parents vu par le directeur) : l'épreuve n'est pas notée ; la note d'EPS "
    "est calculée sur les épreuves passées, ou remplacée par une épreuve écrite courte sur les règles et la santé (hygiène, échauffement).",
    "Dispense partielle (asthme, blessure récente…) : l'élève passe seulement les épreuves autorisées ; la note est ramenée sur 20.",
    "Élève en situation de handicap moteur ou sensoriel : distance réduite d'un quart, temps majoré d'un tiers, aide humaine ou matériel "
    "adapté (balle sonore, repères visuels) ; à défaut, notation sur la grille d'observation (participation, effort, progrès, sécurité).",
    "Élève de petite taille ou en surpoids : on retient le meilleur de trois essais et on note aussi le progrès depuis l'évaluation précédente.",
    "Sécurité : échauffement d'au moins 10 minutes, eau à disposition, épreuves de vitesse et d'endurance aux heures fraîches (avant 10 h ou après 16 h).",
]


def _mmss(s):
    s = int(round(s))
    return f"{s // 60} min {s % 60:02d} s"


def _bareme_temps_long(titre, t10, pas, fille=0.92, plus_age=1.06):
    """Course d'endurance : temps en minutes et secondes (plus petit = mieux)."""
    cols = []
    for sexe in (1.0, fille):
        for age in (1.0, plus_age):
            b = t10 / sexe / age
            p = pas / sexe
            cols.append([("≤ " + _mmss(b + p * i)) if i < 4 else ("> " + _mmss(b + p * 3)) for i in range(5)])
    return {"titre": titre, "unite": "min", "lignes": [[n] + [c[i] for c in cols] for i, n in enumerate(NOTES)]}


def grille_gym(cours):
    """Gymnastique au sol : grille critériée sur 10."""
    elements = ("roulade avant, équilibre sur un pied 3 s, saut groupé" if GROUPE[cours] == "P" else
                "roulade avant et arrière, équilibre (chandelle 3 s), saut extension, enchaînement de 3 éléments" if GROUPE[cours] == "E" else
                "enchaînement libre de 5 éléments (roulades, équilibres, saut, roue) présenté au jury")
    return {"titre": f"Gymnastique au sol — {elements} (grille d'observation)", "unite": "", "observation": True, "lignes": [
        ["Exécution correcte des éléments", "4", "", "", ""], ["Enchaînement fluide, sans arrêt", "2", "", "", ""],
        ["Tenue du corps (jambes tendues, pieds joints)", "2", "", "", ""], ["Sécurité et respect des consignes", "2", "", "", ""]]}


def grille_jeu(cours):
    lib, _regle = JEUX[GROUPE[cours]]
    return {"titre": f"Jeux collectifs — {lib} (grille d'observation)", "unite": "", "observation": True, "lignes": [
        ["Participation active", "2,5", "", "", ""], ["Respect des règles, de l'arbitre et des adversaires", "2,5", "", "", ""],
        ["Coopération avec les partenaires", "2,5", "", "", ""], ["Efficacité (déplacements, passes, buts, vitesse)", "2,5", "", "", ""]]}


def referentiel(cours):
    """Tous les barèmes EPS proposés pour un cours : [(épreuve, consigne, barème)]."""
    d = COURSE[cours]
    t10 = d / VITESSE[cours]
    out = [(f"Course de vitesse sur {d} m", "Départ debout au signal, couloirs séparés, temps au chronomètre (deux essais, meilleur temps).",
            bareme(f"Course de vitesse — {d} m (temps)", "s", t10, 0.6 * d / 40, True, 0.93, 1.06))]
    de = ENDURANCE[cours]
    out.append((f"Course d'endurance sur {de} m", "Allure régulière, sans marcher ; on note le temps ; un élève qui marche termine et reçoit au plus 4/10.",
                _bareme_temps_long(f"Course d'endurance — {de} m (temps)", de / ENDURANCE_VITESSE[cours], de / ENDURANCE_VITESSE[cours] * 0.09)))
    lib = "Saut à pieds joints sans élan" if cours in ("CI", "CP") else "Saut en longueur avec élan"
    out.append((lib, "Trois essais ; mesure du bord de la planche (ou de la ligne) à la trace la plus proche ; meilleur essai.",
                bareme(f"{lib} (meilleur de 3 essais)", "m", SAUT[cours], SAUT[cours] * 0.08, False, 0.90, 1.08)))
    if cours in HAUTEUR:
        out.append(("Saut en hauteur (ciseau)", "Élastique ou barre souple, montée de 5 cm en 5 cm ; trois essais par hauteur ; tapis ou sable obligatoire.",
                    bareme("Saut en hauteur — ciseau (hauteur franchie)", "m", HAUTEUR[cours], 0.05, False, 0.92, 1.06)))
    out.append(("Lancer de balle (150 g)", "Trois lancers à une main derrière la ligne ; mesure du premier point de chute ; meilleur essai.",
                bareme("Lancer de balle 150 g (meilleur de 3 essais)", "m", LANCER[cours], LANCER[cours] * 0.12, False, 0.80, 1.10)))
    out.append(("Gymnastique au sol", "Sur tapis ; présentation devant deux observateurs.", grille_gym(cours)))
    out.append(("Jeux collectifs", JEUX[GROUPE[cours]][1], grille_jeu(cours)))
    return out
