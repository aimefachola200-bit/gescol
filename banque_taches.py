# -*- coding: utf-8 -*-
"""v1.21 — Banque d'épreuves : situations d'EXPRESSION ÉCRITE, d'ÉDUCATION ARTISTIQUE et d'EPS (rédaction originale SCOLARIS ;
trimestres et fin d'année du CE1 au CM2 : reformulations des situations des épreuves standardisées de l'INFRE).
Expression écrite : (contexte, tâche, consignes, genre) ; le genre choisit les indicateurs de la grille de correction."""

E = {}


def _e(cours, per, genre, contexte, tache, *consignes, infre=None):
    E[(cours, per)] = {"genre": genre, "contexte": contexte, "tache": tache, "consignes": list(consignes), "infre": infre}


# ---------------------------------------------------------------------------- CI / CP (graphisme, copie, phrase)
for per, mot, phrase in [("M1", "ami", "Ali est mon ami."), ("M2", "papa", "Voici papa."), ("M3", "ballon", "Koffi a un ballon."),
                         ("M4", "pain", "Maman achète du pain."), ("M5", "pluie", "Il pleut."), ("M6", "chat", "Le chat boit."),
                         ("T1", "craie", "J'ai une craie."), ("T2", "mains", "Je lave mes mains."), ("T3", "fête", "C'est la fête."),
                         ("FA", "jardin", "J'arrose le jardin.")]:
    _e("CI", per, "copie", "Le maître veut afficher les plus belles écritures de la classe au tableau d'honneur.",
       "Tu es invité à écrire proprement pour que ta page soit affichée.",
       f"Trace une ligne de boucles puis une ligne de ponts.", f"Recopie trois fois le mot « {mot} ».", f"Recopie la phrase : « {phrase} »",
       "Écris ton prénom en bas de la page.")
for per, theme, mots, debut in [("M1", "l'école", "école, maître, ardoise, craie", "Je vais à l'…"),
                                ("M2", "la famille", "papa, maman, frère, sœur", "Voici mon …"),
                                ("M3", "la route", "casque, moto, route, prudent", "Papa porte un …"),
                                ("M4", "l'eau", "puits, eau, seau, propre", "Je puise l'…"),
                                ("M5", "le marché", "marché, maïs, orange, acheter", "Maman va au …"),
                                ("M6", "le drapeau", "drapeau, vert, jaune, rouge", "Le drapeau est …"),
                                ("T1", "le vélo", "vélo, cour, rouler, bleu", "Tobi a un …"),
                                ("T2", "la pluie", "pluie, livre, maison, lire", "Il pleut, je reste à la …"),
                                ("T3", "le jardin", "jardin, tomates, arroser, semer", "Nous semons des …"),
                                ("FA", "les congés", "congés, village, grand-mère, conte", "Pendant les congés, je vais au …")]:
    _e("CP", per, "phrases", f"Ton maître prépare un petit livre de la classe sur {theme}.",
       "Tu es invité à écrire des phrases pour le livre de la classe.",
       f"Complète la phrase : « {debut} »", f"Écris une phrase avec un de ces mots : {mots}.",
       "Remets les mots dans l'ordre pour faire une phrase (le maître écrit trois étiquettes au tableau).",
       "Commence chaque phrase par une majuscule et termine-la par un point.")

# ---------------------------------------------------------------------------- CE1 (T1–FA d'après INFRE 2016)
_e("CE1", "M1", "phrases", "Ta classe décore le coin lecture.", "Tu es invité à écrire trois phrases pour présenter ton livre préféré.",
   "Écris le titre de ton livre.", "Dis en une phrase de quoi il parle.", "Dis pourquoi tu l'aimes.")
_e("CE1", "M2", "affiche", "Les moustiques sont nombreux près de l'école.", "Tu es invité à réaliser une petite affiche contre le paludisme.",
   "Dessine une moustiquaire.", "Écris un message de deux phrases sous le dessin.")
_e("CE1", "M3", "lettre", "Ton ami Bio ne va pas à l'école.", "Tu es invité à lui écrire un petit mot pour l'encourager à venir à l'école.",
   "Commence par « Cher Bio ».", "Écris trois phrases.", "Termine par ton prénom.")
_e("CE1", "M4", "recit", "Samedi, ta classe a nettoyé la cour.", "Tu es invité à raconter ce que vous avez fait.",
   "Écris quatre phrases dans l'ordre : avant, pendant, après.", "Soigne ton écriture.")
_e("CE1", "M5", "description", "Une fête a lieu dans ta localité.", "Tu es invité à décrire cette fête.",
   "Dis le nom de la fête.", "Écris trois phrases pour dire ce que tu as vu.")
_e("CE1", "M6", "invitation", "Le chef de quartier organise une réunion.", "Tu es invité à rédiger le message qui invite les habitants.",
   "Dis le jour, l'heure et le lieu.", "Dis pourquoi on se réunit.")
_e("CE1", "T1", "texte_a_trous", "C'est la rentrée. Avec ton maître, vous décidez d'embellir la classe avec des dessins et des guirlandes. Tu veux proposer la même chose à tes amis d'une autre école.",
   "Tu es invité à écrire un petit texte cohérent avec les mots proposés par le maître.",
   "Remplace les pointillés par les mots qui conviennent (attention : un mot est en trop) : décorer, dessins, rentrée, classe, mur, marmite.",
   "Texte : « Chers amis, c'est la … . Unissez-vous pour … votre … en collant des … au … . À bientôt ! »", infre="2016")
_e("CE1", "T2", "invitation", "Ta petite sœur fête bientôt ses sept ans. Tes parents organisent une fête et tu veux inviter tes camarades.",
   "Tu es invité à réaliser une carte d'invitation.", "Dessine la carte.", "Écris le message d'invitation sur la carte (jour, heure, lieu).", infre="2016")
_e("CE1", "T3", "recit", "Cette semaine, ta famille a célébré un mariage. Tu as suivi toute la cérémonie et tu veux la raconter à tes camarades.",
   "Tu es invité à faire le récit de cette fête.", "Rédige ton récit.", "Écris dans l'ordre les différents moments de la fête.", infre="2016")
_e("CE1", "FA", "affiche", "Dans ton quartier, des enfants travaillent toute la journée au lieu d'aller à l'école. Cela te rend triste. Tu décides de le dénoncer par une affiche.",
   "Tu es invité à réaliser une affiche contre le travail des enfants.", "Réalise ton affiche.", "Écris un message pour dénoncer ce que tu as observé.",
   "Donne un conseil aux parents.", infre="2016")

# ---------------------------------------------------------------------------- CE2 (T1–FA d'après INFRE 2015)
_e("CE2", "M1", "lettre", "Ton cousin a été vacciné et il a eu peur.", "Tu es invité à lui écrire une lettre pour le rassurer.",
   "Respecte la structure d'une lettre personnelle.", "Écris au moins cinq phrases.", "Veille aux accords.")
_e("CE2", "M2", "affiche", "Des inconnus coupent les arbres près de l'école.", "Tu es invité à réaliser une affiche pour protéger les arbres.",
   "Trouve un titre accrocheur.", "Écris un message court.", "Respecte les caractéristiques d'une affiche.")
_e("CE2", "M3", "description", "Ton oncle t'a offert un appareil (radio, téléphone, montre…).", "Tu es invité à décrire cet appareil et son utilité.",
   "Dis sa forme, sa couleur et ses parties.", "Dis à quoi il sert.", "Écris au moins six phrases.")
_e("CE2", "M4", "dialogue", "Le père d'une camarade veut la retirer de l'école.", "Tu es invité à écrire le dialogue où ton maître le convainc.",
   "Fais parler les deux personnages à tour de rôle.", "Utilise les tirets et la ponctuation du dialogue.")
_e("CE2", "M5", "compte_rendu", "Ta classe a visité un musée ou un site.", "Tu es invité à faire le compte rendu de la visite.",
   "Dis où, quand et avec qui.", "Raconte ce que vous avez vu.", "Donne ton avis.")
_e("CE2", "M6", "lettre", "Tu veux un acte de naissance pour ton frère.", "Tu es invité à écrire la demande au chef d'arrondissement.",
   "Respecte la forme d'une lettre de demande.", "Sois poli et précis.")
_e("CE2", "T1", "lettre", "Depuis la rentrée, ta grande sœur, admise au CEP, est partie au collège en ville. Votre grand-mère est malade et tu veux l'en informer.",
   "Tu es invité à rédiger une lettre.", "Rédige ta lettre.", "Respecte la structure d'une lettre personnelle.", "Fais attention aux accords.",
   "Présente une copie propre et lisible.", infre="2015")
_e("CE2", "T2", "affiche", "Un ami est venu passer les congés chez toi. En vous promenant, vous voyez des caniveaux bouchés par les ordures. Tu veux sensibiliser les habitants.",
   "Tu es invité à réaliser une affiche pour dire aux habitants comment garder le quartier propre.", "Rédige ton affiche.",
   "Fais passer ton message par les différentes parties de l'affiche.", "Respecte les caractéristiques d'une affiche.", "Présente bien ta copie.", infre="2015")
_e("CE2", "T3", "lettre", "Une ancienne camarade de classe vient de perdre son grand-père. Tu ne peux pas aller la voir.",
   "Tu es invité à lui écrire une lettre de condoléances.", "Rédige ta lettre de condoléances.", "Respecte les caractéristiques d'une lettre personnelle.",
   "Ordonne tes idées.", "Veille aux accords.", "Présente une copie propre et lisible.", infre="2015")
_e("CE2", "FA", "recit", "Ton grand frère s'est marié. Toute la famille a participé à la cérémonie. Tu racontes la fête à ceux qui n'étaient pas là.",
   "Tu es invité à faire le récit du déroulement de la cérémonie.", "Raconte les événements dans l'ordre.", "Respecte les caractéristiques d'un récit.",
   "Veille à la cohérence des idées.", "Tiens compte des accords.", "Présente une copie propre et lisible.", infre="2015")

# ---------------------------------------------------------------------------- CM1 (T1–FA d'après INFRE 2014)
_e("CM1", "M1", "article", "Une épidémie de choléra touche un quartier voisin.", "Tu es invité à écrire un court article pour le journal de l'école.",
   "Donne un titre et un chapeau.", "Explique les causes et les moyens de prévention.", "Écris huit phrases au moins.")
_e("CM1", "M2", "lettre", "La lagune de ta ville est envahie par les déchets.", "Tu es invité à écrire au maire pour proposer des solutions.",
   "Respecte la forme d'une lettre administrative.", "Présente le problème et deux solutions.")
_e("CM1", "M3", "description", "Ton école vient de recevoir des panneaux solaires.", "Tu es invité à décrire l'installation et ses avantages.",
   "Décris ce que tu vois.", "Explique à quoi cela sert.", "Utilise des mots précis.")
_e("CM1", "M4", "dialogue", "Une camarade de treize ans doit être mariée de force.", "Tu es invité à écrire le dialogue où tu la conseilles.",
   "Fais au moins six répliques.", "Utilise la ponctuation du dialogue.", "Cite un droit de l'enfant.")
_e("CM1", "M5", "compte_rendu", "Tu as assisté à une fête traditionnelle.", "Tu es invité à en faire le compte rendu.",
   "Dis où, quand, qui, quoi.", "Décris les moments importants.", "Termine par ton avis.")
_e("CM1", "M6", "discours", "Tu es candidat au conseil des élèves.", "Tu es invité à écrire ton discours de candidature.",
   "Présente-toi.", "Dis trois propositions.", "Termine par un appel au vote.")
_e("CM1", "T1", "article", "On parle beaucoup en ce moment de la rougeole qui touche les enfants non vaccinés. Tu veux partager ce que tu sais avec la population à travers le journal de ta commune.",
   "Tu es invité à écrire un article de journal pour sensibiliser la population sur une maladie évitable par la vaccination.",
   "Choisis une maladie que tu connais bien.", "Parle de ses manifestations.", "Donne des conseils pour la prévenir ou la soigner.",
   "Respecte les caractéristiques d'un article de journal.", "Rédige une dizaine de phrases.", infre="2014")
_e("CM1", "T2", "recit", "Pour récompenser tes bons résultats, ton oncle t'a emmené découvrir une ville que tu ne connaissais pas. Tu as voyagé en car et tu as passé de très bons moments.",
   "Tu es invité à raconter par écrit ce voyage.", "Produis un texte narratif d'au moins dix phrases.", "Respecte l'ordre chronologique des faits.",
   "Précise la ville visitée et le moyen de transport.", "Respecte les caractéristiques du récit.", infre="2014")
_e("CM1", "T3", "affiche", "Malgré les lois qui protègent les enfants, certains sont encore battus ou privés d'école dans ta localité. Tu veux sensibiliser la population.",
   "Tu es invité à réaliser une affiche contre la maltraitance des enfants.", "Produis ton message en cinq phrases au plus.", "Réalise ton affiche.",
   "Respecte les caractéristiques de l'affiche.", infre="2014")
_e("CM1", "FA", "lettre", "Ton école est jumelée avec une école d'un autre pays. Un concours récompense la meilleure lettre présentant une manifestation culturelle du Bénin.",
   "Tu es invité à écrire au directeur de l'école partenaire pour lui présenter une manifestation culturelle de ton pays.",
   "Écris ta lettre.", "Précise la manifestation choisie et décris-la.", "Respecte la forme d'une lettre administrative à forme personnelle.", infre="2014")

# ---------------------------------------------------------------------------- CM2 (T1–FA d'après INFRE 2014 ; C1–C3 : CEP blanc)
_e("CM2", "M1", "article", "Une campagne de dépistage gratuite aura lieu dans ta commune.", "Tu es invité à écrire l'article qui l'annonce.",
   "Donne un titre et un chapeau.", "Réponds aux questions qui, quoi, où, quand, pourquoi.", "Écris dix phrases au moins.")
_e("CM2", "M2", "plaidoyer", "La forêt voisine est menacée par les coupes.", "Tu es invité à écrire un texte pour convaincre les villageois de la protéger.",
   "Donne trois arguments.", "Utilise des mots de liaison.", "Termine par un appel.")
_e("CM2", "M3", "lettre", "Tu veux t'inscrire à un concours en ligne.", "Tu es invité à écrire au responsable pour demander des informations.",
   "Respecte la forme d'une lettre administrative.", "Pose trois questions précises.")
_e("CM2", "M4", "recit", "Une fille de ton âge a été retirée d'un travail dangereux.", "Tu es invité à raconter son histoire.",
   "Présente la situation de départ, l'événement et la fin.", "Écris douze phrases au moins.")
_e("CM2", "M5", "compte_rendu", "Ta classe a visité un lieu de mémoire.", "Tu es invité à faire le compte rendu de la visite.",
   "Présente la visite.", "Décris ce que vous avez appris.", "Donne ton avis.")
_e("CM2", "M6", "discours", "Le maire visite ton école.", "Tu es invité à rédiger le mot de bienvenue lu par un élève.",
   "Salue le maire et présente l'école.", "Expose deux besoins.", "Remercie.")
_e("CM2", "T1", "conte", "Le soir, au clair de lune, les enfants aiment écouter les contes. Ton école organise un concours du meilleur conte écrit.",
   "Tu es invité à écrire un conte qui enseigne la prudence.", "Commence par une formule d'ouverture.", "Respecte les étapes du conte.",
   "Termine par une morale.", "Écris quinze phrases au moins.", infre="2014")
_e("CM2", "T2", "lettre", "Les ordures envahissent le marché de ta localité et menacent la santé de tous.",
   "Tu es invité à écrire au maire pour lui exposer le problème et proposer des solutions.", "Respecte la forme d'une lettre administrative.",
   "Expose clairement le problème.", "Propose au moins deux solutions.", infre="2014")
_e("CM2", "T3", "affiche", "La rentrée prochaine, de nombreux enfants ne seront pas inscrits à l'école dans ta commune.",
   "Tu es invité à réaliser une affiche pour encourager les parents à scolariser tous leurs enfants.", "Trouve un titre accrocheur.",
   "Écris un message court et convaincant.", "Respecte les caractéristiques de l'affiche.", infre="2014")
_e("CM2", "FA", "recit", "Tu vas quitter l'école primaire. Tu veux laisser un souvenir écrit à tes cadets.",
   "Tu es invité à raconter le meilleur souvenir de ta scolarité au primaire.", "Respecte l'ordre chronologique.", "Exprime tes sentiments.",
   "Écris quinze phrases au moins.", infre="2014")
_e("CM2", "C1", "lettre", "Ton ami qui vit à l'étranger veut connaître ton village.", "Tu es invité à lui écrire une lettre pour lui présenter ton village.",
   "Respecte la forme d'une lettre personnelle.", "Présente le village, ses activités et une fête.", "Écris quinze phrases au moins.")
_e("CM2", "C2", "article", "Ton école a organisé une journée de salubrité.", "Tu es invité à écrire l'article pour le journal de la commune.",
   "Donne un titre et un chapeau.", "Raconte l'événement et ses résultats.", "Écris quinze phrases au moins.")
_e("CM2", "C3", "recit", "Un événement heureux a marqué ta famille cette année.", "Tu es invité à le raconter.",
   "Présente les personnages, le lieu et le moment.", "Raconte dans l'ordre.", "Exprime tes sentiments.", "Écris quinze phrases au moins.")

# ---------------------------------------------------------------------------- indicateurs par genre (grille de correction)
INDICATEURS = {
    "copie": ["les lettres ont la bonne forme et la bonne taille", "les mots sont recopiés sans erreur", "la page est propre"],
    "phrases": ["chaque phrase a un sens et parle du thème", "la phrase commence par une majuscule et finit par un point", "les mots sont bien orthographiés"],
    "texte_a_trous": ["chaque pointillé reçoit le mot qui convient", "l'intrus n'est pas utilisé", "le texte complété a un sens"],
    "lettre": ["lieu et date, formule d'appel, corps, formule finale, signature", "le message répond à la situation", "les idées s'enchaînent"],
    "affiche": ["un titre / slogan accrocheur", "une image ou un dessin en rapport", "un message court, lisible de loin"],
    "recit": ["les faits sont racontés dans l'ordre", "les personnages, le lieu et le moment sont présentés", "les temps du récit sont respectés"],
    "description": ["l'objet / le lieu est nommé", "des détails précis sont donnés (forme, couleur, parties)", "le vocabulaire est varié"],
    "invitation": ["le jour, l'heure et le lieu sont indiqués", "le motif est précisé", "une formule de politesse est utilisée"],
    "dialogue": ["tirets et ponctuation du dialogue", "chaque personnage parle à son tour", "les répliques font avancer l'échange"],
    "compte_rendu": ["qui, quoi, où, quand sont précisés", "les faits sont rapportés fidèlement", "un avis personnel termine le texte"],
    "article": ["titre, chapeau, corps du texte", "réponses aux questions de l'information", "informations exactes et utiles"],
    "discours": ["salutations et présentation", "propositions claires", "formule de clôture / appel"],
    "plaidoyer": ["au moins trois arguments", "mots de liaison", "appel final à agir"],
    "conte": ["formule d'ouverture et de clôture", "étapes du conte (situation initiale, péripéties, fin)", "une morale"],
}

# ---------------------------------------------------------------------------- Éducation artistique (par trimestre / fin d'année)
EA = {
    "CI": [("Dessin", "C'est bientôt Noël. Tu veux offrir un joli dessin à maman.", "Tu es invité à dessiner et colorier un fruit.", ["Dessine une orange.", "Colorie-la sans dépasser.", "Écris ton prénom."]),
           ("Chant — poème — conte", "La classe prépare une matinée récréative.", "Tu es invité à dire une comptine ou à chanter un chant appris.", ["Annonce le titre.", "Chante ou dis la comptine.", "Accompagne de gestes."]),
           ("Travaux manuels", "Tu veux décorer ta classe.", "Tu es invité à faire un collage.", ["Découpe des morceaux de papier.", "Colle-les pour former une fleur.", "Soigne ton travail."]),
           ("Dessin", "C'est la fin de l'année.", "Tu es invité à dessiner ta maison.", ["Dessine la maison.", "Ajoute un arbre.", "Colorie proprement."])],
    "CP": [("Dessin", "Tu veux offrir une carte à un ami.", "Tu es invité à dessiner un ballon et à le colorier.", ["Trace un cercle.", "Décore-le de bandes.", "Colorie sans dépasser."]),
           ("Chant — poème — conte", "La classe organise une veillée.", "Tu es invité à dire un poème ou un conte appris.", ["Annonce le titre.", "Dis-le de mémoire.", "Mets le ton."]),
           ("Travaux manuels", "Le jardin de l'école a besoin d'étiquettes.", "Tu es invité à fabriquer une étiquette en carton.", ["Découpe un rectangle.", "Écris le nom d'une plante.", "Décore-la."]),
           ("Dessin", "C'est la fête de fin d'année.", "Tu es invité à dessiner un drapeau du Bénin.", ["Trace le rectangle.", "Place les trois couleurs.", "Colorie proprement."])],
    "CE1": [("Travaux manuels", "La fête approche et ton groupe n'a pas de masques pour danser.", "Tu es invité à fabriquer un masque en papier.", ["Fabrique le masque.", "Colorie-le.", "Écris ton nom en haut du masque."]),
            ("Chant — poème — conte", "Tes amis répètent pour une matinée récréative.", "Tu es invité à exécuter un chant, un poème ou un conte de ton choix.", ["Dis ce que tu as choisi.", "Exécute-le correctement.", "Accompagne-le de gestes ou de mimiques."]),
            ("Dessin", "Tu veux remercier ton maître.", "Tu es invité à réaliser une carte de remerciement.", ["Trace un rectangle de 12 cm sur 8 cm.", "Dessine une fleur.", "Écris « Merci maître »."]),
            ("Travaux manuels", "La classe prépare une exposition.", "Tu es invité à tresser une petite natte en bandes de papier.", ["Découpe six bandes.", "Tresse-les.", "Colle les bouts."])],
    "CE2": [("Dessin", "Ton village organise la fête de l'igname.", "Tu es invité à dessiner une calebasse décorée.", ["Dessine la calebasse.", "Décore-la de motifs.", "Colorie."]),
            ("Couture", "Ta poupée a besoin d'un mouchoir.", "Tu es invité à réaliser un ourlet au point de devant.", ["Découpe un carré de tissu de 10 cm.", "Replie les bords.", "Couds au point de devant."]),
            ("Chant — poème — conte", "La classe présente un spectacle aux parents.", "Tu es invité à dire un conte du milieu.", ["Commence par la formule d'ouverture.", "Raconte avec expression.", "Dis la morale."]),
            ("Dessin", "C'est la fin de l'année scolaire.", "Tu es invité à illustrer un proverbe.", ["Écris le proverbe.", "Dessine une scène qui l'illustre.", "Colorie."])],
    "CM1": [("Dessin", "C'est bientôt les fêtes de fin d'année. Tu veux envoyer tes vœux à un parent.", "Tu es invité à réaliser une carte de vœux.", ["Trace au centre de ta feuille un rectangle de 15 cm sur 10 cm.", "Trace une bordure de 1 cm coloriée à ton choix.", "Inscris ton vœu en écriture script majuscule.", "Veille à la bonne gestion de l'espace."]),
            ("Couture", "Ta petite sœur veut une jupe pour sa poupée.", "Tu es invité à assembler deux pièces de tissu au point de piqûre.", ["Découpe deux pièces de 10 cm sur 5 cm.", "Assemble-les dans le sens de la longueur.", "Utilise le point de piqûre.", "Fixe ta production à la feuille."]),
            ("Dessin (illustration)", "Le travail des enfants est encore courant.", "Tu es invité à réaliser un dessin pour combattre le travail des enfants.", ["Réalise le dessin.", "Écris un message de sensibilisation au bas du dessin."]),
            ("Chant — poème — conte", "Ton école organise la fête de fin d'année.", "Tu es invité à exécuter un chant patriotique ou un poème.", ["Annonce le titre et l'auteur.", "Exécute avec justesse.", "Soigne la posture."])],
    "CM2": [("Dessin", "La commune lance une campagne de reboisement.", "Tu es invité à réaliser une affiche publicitaire pour le reboisement.", ["Trace le cadre de l'affiche.", "Dessine un plant protégé.", "Écris un slogan en lettres calligraphiées."]),
            ("Calligraphie", "C'est la fête de Pâques ou de Tabaski.", "Tu es invité à calligraphier un message de fête.", ["Trace les lignes guides.", "Calligraphie « Bonne fête à tous ».", "Décore les initiales."]),
            ("Dessin", "Les droits de l'enfant doivent être connus de tous.", "Tu es invité à réaliser une affiche sur un droit de l'enfant.", ["Choisis un droit.", "Illustre-le.", "Écris un message."]),
            ("Couture", "Tu offres un cadeau à ta maîtresse.", "Tu es invité à broder ses initiales au point de tige.", ["Trace les initiales sur le tissu.", "Brode au point de tige.", "Fais un ourlet."])],
}

# ---------------------------------------------------------------------------- EPS (épreuve pratique ; barèmes indicatifs filles / garçons)
EPS = {
    "CI": ("Course de vitesse sur 20 m et sauts à pieds joints", "20 m", [("Moins de 6 s", 10), ("6 à 8 s", 7), ("Plus de 8 s", 4)]),
    "CP": ("Course de vitesse sur 30 m et roulade avant", "30 m", [("Moins de 7 s", 10), ("7 à 9 s", 7), ("Plus de 9 s", 4)]),
    "CE1": ("Course de vitesse sur 40 m et gymnastique (saut en extension, roulade avant, chute arrière)", "40 m", [("Moins de 8 s", 10), ("8 à 10 s", 7), ("Plus de 10 s", 4)]),
    "CE2": ("Course de vitesse sur 50 m et mini-enchaînement gymnique", "50 m", [("Moins de 9 s", 10), ("9 à 11 s", 7), ("Plus de 11 s", 4)]),
    "CM1": ("Course de vitesse sur 60 m et saut en longueur après course d'élan", "60 m", [("Moins de 10 s", 10), ("10 à 12 s", 7), ("Plus de 12 s", 4)]),
    "CM2": ("Course de vitesse sur 80 m et enchaînement gymnique", "80 m", [("Moins de 12 s", 10), ("12 à 14 s", 7), ("Plus de 14 s", 4)]),
}
