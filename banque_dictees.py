# -*- coding: utf-8 -*-
"""v1.30 — Banque de dictées (textes originaux adaptés au cours et à la période) avec questions au format INFRE (CE2 à
CM2 : questions de vocabulaire, de grammaire et de conjugaison sur le texte dicté) et barème des fautes.

DICTEES[cours][periode] = (titre, texte, [(question, réponse)…]) ; au CI, le « texte » est une liste d'éléments
(lettres, syllabes, mots, puis courte phrase) séparés par « / ».
"""

PERIODES_DICTEE = ["M1", "M2", "T1", "M3", "M4", "T2", "M5", "M6", "T3", "FA", "C1", "C2", "C3"]

D = {
    "CI": {
        "M1": ("Les voyelles", "a / i / o / u / e", []),
        "M2": ("Les lettres l et m", "l / m / a / i / o", []),
        "T1": ("Les syllabes", "la / li / lo / ma / mi / mo", []),
        "M3": ("Syllabes et petits mots", "pa / to / ami / lit / papa", []),
        "M4": ("Les mots de la maison", "maman / mur / natte / pot / riz", []),
        "T2": ("Les mots de l'école", "la table / le bic / la craie / un ami", []),
        "M5": ("Les mots du marché", "le sel / la tomate / le pagne / la pâte", []),
        "M6": ("Petites phrases", "Papa a un vélo. / Ali lit.", []),
        "T3": ("Phrases simples", "Maman pile le mil. / Le bébé dort.", []),
        "FA": ("Phrases de fin d'année", "Koffi va à l'école. / La poule a un œuf.", []),
    },
    "CP": {
        "M1": ("Le chat", "Le chat de Rémi dort sur la natte.", []),
        "M2": ("À l'école", "Le maître écrit au tableau. Les élèves lisent.", []),
        "T1": ("Au marché", "Maman achète des tomates et du piment au marché.", []),
        "M3": ("La pluie", "Il pleut fort. Les enfants rentrent vite à la maison.", []),
        "M4": ("Le repas", "Ce soir, nous mangeons de la pâte avec une sauce de gombo.", []),
        "T2": ("Mon village", "Mon village est petit. Il y a un puits, une école et un marché.", []),
        "M5": ("La fête", "Pour la fête, Awa porte une belle robe jaune et des sandales neuves.", []),
        "M6": ("Le jardin", "Papa arrose les salades du jardin. Je l'aide avec mon petit arrosoir.", []),
        "T3": ("Les animaux", "La chèvre mange de l'herbe. Le chien garde la maison pendant la nuit.", []),
        "FA": ("Les vacances", "Pendant les vacances, je vais chez ma grand-mère. Elle me raconte des contes.", []),
    },
    "CE1": {
        "M1": ("La rentrée", "C'est la rentrée. Les élèves arrivent avec des sacs neufs. Le maître les accueille dans la cour et leur montre la nouvelle classe.", []),
        "M2": ("Le puits", "Chaque matin, Sika va au puits avec sa bassine. Elle puise l'eau, puis elle rentre à la maison sans renverser une goutte.", []),
        "T1": ("Le marché du village", "Le marché du village se tient tous les cinq jours. Les femmes vendent du maïs, des ignames et des pagnes. Les enfants aident leurs mères à porter les paniers.", []),
        "M3": ("L'harmattan", "En janvier, l'harmattan souffle. Le matin, il fait froid et le ciel est gris. Les enfants portent des pulls pour aller à l'école.", []),
        "M4": ("Le football", "Après la classe, les garçons et les filles jouent au football dans la cour. Bio marque un beau but. Tous ses camarades applaudissent.", []),
        "T2": ("La maladie de Tobi", "Tobi a de la fièvre. Sa maman l'emmène au centre de santé. L'infirmier lui donne des médicaments et lui conseille de dormir sous la moustiquaire.", []),
        "M5": ("Le champ de papa", "Papa a un grand champ de maïs. Avec la houe, il enlève les mauvaises herbes. Le soir, il rentre fatigué mais content.", []),
        "M6": ("La lettre", "Rachida écrit une lettre à son oncle qui vit à Parakou. Elle lui donne des nouvelles de la famille et lui parle de ses bonnes notes.", []),
        "T3": ("La fête de l'école", "Pour la fête de l'école, les élèves chantent et dansent. Les parents sont venus nombreux. Le directeur remet des prix aux meilleurs élèves.", []),
        "FA": ("Les grandes vacances", "L'année scolaire est finie. Les enfants rangent leurs cahiers. Pendant les vacances, ils aideront leurs parents et liront de beaux livres.", []),
    },
    "CE2": {
        "M1": ("Le départ pour l'école", "Le soleil se lève à peine. Codjo se lave, met sa tenue kaki et prend son sac. Sa grande sœur lui donne une bouillie chaude. Ensemble, ils marchent sur le sentier qui mène à l'école.",
               [("Donne le contraire du mot « chaude ».", "froide"), ("Relève le sujet du verbe « donne ».", "sa grande sœur"), ("Écris la phrase « Codjo se lave » au futur simple.", "Codjo se lavera.")]),
        "M2": ("La récolte des arachides", "Les arachides sont mûres. Toute la famille part au champ de bonne heure. Les hommes arrachent les pieds, les femmes et les enfants les secouent pour enlever la terre. Le soir, les sacs sont pleins.",
               [("Donne un mot de la même famille que « champ ».", "champêtre"), ("Relève dans le texte un adjectif qualificatif.", "mûres (pleins)"), ("Mets « les sacs sont pleins » au singulier.", "Le sac est plein.")]),
        "T1": ("Le marchand ambulant", "Chaque après-midi, un marchand ambulant passe dans notre rue. Il pousse une petite charrette chargée de bonbons, de cahiers et de bics. Les enfants courent vers lui avec quelques pièces dans la main. Il sourit et sert tout le monde.",
               [("Que veut dire « ambulant » ?", "qui se déplace d'un endroit à l'autre pour vendre"), ("Relève le complément d'objet direct du verbe « pousse ».", "une petite charrette (chargée de bonbons…)"), ("Écris « Il sourit » au passé composé.", "Il a souri.")]),
        "M3": ("Le feu de brousse", "La saison sèche est là. Un paysan imprudent a allumé un feu pour nettoyer son champ. Le vent a poussé les flammes vers la forêt. Les arbres brûlent et les animaux s'enfuient. Les villageois arrivent avec des seaux d'eau.",
               [("Donne le contraire de « imprudent ».", "prudent"), ("Relève un verbe au passé composé.", "a allumé (a poussé)"), ("Écris « les animaux s'enfuient » au singulier.", "L'animal s'enfuit.")]),
        "M4": ("La pirogue", "Sur le lac Nokoué, les pêcheurs partent avant le lever du jour. Ils glissent sur l'eau calme dans leurs pirogues. Ils jettent leurs filets et attendent en silence. Au retour, les femmes achètent les poissons pour les fumer.",
               [("Que signifie « fumer » le poisson ?", "le sécher et le conserver à la fumée"), ("Relève le complément circonstanciel de lieu de la première phrase.", "sur le lac Nokoué"), ("Conjugue « partir » au présent avec « nous ».", "nous partons")]),
        "T2": ("La visite médicale", "Ce matin, un médecin est venu à l'école. Il a pesé et mesuré chaque élève. Il a regardé nos dents et nos yeux. À la fin, il nous a conseillé de nous laver les mains avant chaque repas et de dormir sous une moustiquaire.",
               [("Donne un mot de la même famille que « médecin ».", "médecine (médical, médicament)"), ("Relève les verbes au passé composé de la deuxième phrase.", "a pesé, (a) mesuré"), ("Écris « Il a regardé nos dents » au futur simple.", "Il regardera nos dents.")]),
        "M5": ("La tisserande", "Grand-mère est tisserande. Assise devant son métier, elle croise les fils de coton avec patience. Peu à peu, un beau pagne aux couleurs vives apparaît. Elle le vendra au marché de Kouandé.",
               [("Que fait une tisserande ?", "Elle fabrique des tissus (des pagnes) sur un métier à tisser."), ("Relève le sujet du verbe « apparaît ».", "un beau pagne aux couleurs vives"), ("À quel temps est le verbe « vendra » ?", "au futur simple")]),
        "M6": ("Le jardin scolaire", "Les élèves de CE2 entretiennent le jardin de l'école. Les uns arrosent les tomates, les autres arrachent les mauvaises herbes. Le maître leur explique comment faire du compost. Les légumes serviront à la cantine.",
               [("Que veut dire « entretenir » un jardin ?", "s'en occuper pour le garder en bon état"), ("Relève deux noms au pluriel.", "élèves, tomates (herbes, légumes)"), ("Écris « Le maître leur explique » à l'imparfait.", "Le maître leur expliquait.")]),
        "T3": ("La fête de l'igname", "Au mois d'août, le village célèbre la fête de l'igname nouvelle. Les tambours résonnent sur la place. Les femmes préparent de l'igname pilée et de la sauce d'arachide. Les anciens remercient la terre pour la bonne récolte.",
               [("Donne le synonyme de « résonnent ».", "retentissent"), ("Relève le complément d'objet direct du verbe « préparent ».", "de l'igname pilée et de la sauce d'arachide"), ("Conjugue « remercier » au présent avec « vous ».", "vous remerciez")]),
        "FA": ("La fin de l'année", "Les grandes vacances approchent. Les élèves ont rendu leurs livres et nettoyé leur classe. Le directeur a lu les résultats devant tout le monde. Ceux qui passent au CM1 sont fiers ; les autres promettent de mieux travailler.",
               [("Donne le contraire de « fiers ».", "honteux"), ("Relève le sujet du verbe « promettent ».", "les autres"), ("Écris « Les grandes vacances approchent » au futur simple.", "Les grandes vacances approcheront.")]),
    },
    "CM1": {
        "M1": ("Un matin au village", "Le coq a chanté depuis longtemps. Dans les concessions, les femmes balaient la cour et allument le feu. Les hommes affûtent leurs coupe-coupe avant de partir au champ. Les enfants, la tête chargée d'un seau, reviennent de la rivière en riant.",
               [("Que veut dire « affûter » ?", "rendre tranchant, aiguiser"), ("Relève le sujet du verbe « reviennent ».", "les enfants"), ("Écris la deuxième phrase à l'imparfait.", "Dans les concessions, les femmes balayaient la cour et allumaient le feu.")]),
        "M2": ("La mare", "Au fond de la vallée dort une petite mare entourée de roseaux. Les crapauds y coassent le soir et les hérons viennent y pêcher au lever du jour. En saison sèche, l'eau diminue et la mare se couvre d'une croûte de boue craquelée.",
               [("Donne le sens de « craquelée ».", "fendillée, couverte de petites fentes"), ("Relève le sujet inversé de la première phrase.", "une petite mare entourée de roseaux"), ("Conjugue « venir » au présent avec « ils ».", "ils viennent")]),
        "T1": ("Le vaccin", "Ce jeudi, les agents de santé sont venus vacciner les enfants du quartier contre la rougeole. Les mamans faisaient la queue devant la maternité, leurs bébés au dos. Certains enfants pleuraient, d'autres regardaient l'aiguille avec curiosité. Chacun est reparti avec son carnet rempli.",
               [("Donne un mot de la famille de « vacciner ».", "vaccin (vaccination)"), ("Relève un verbe à l'imparfait et donne son infinitif.", "faisaient → faire (pleuraient → pleurer ; regardaient → regarder)"), ("Quelle est la nature du mot « curiosité » ?", "un nom commun")]),
        "M3": ("Le zémidjan", "À Cotonou, les conducteurs de taxi-moto, appelés zémidjans, portent une chemise jaune. Ils se faufilent entre les voitures et transportent les passagers dans tous les quartiers. Le port du casque est obligatoire pour le conducteur comme pour le client.",
               [("Que veut dire « se faufiler » ?", "passer adroitement entre des obstacles"), ("Relève l'attribut du sujet dans la dernière phrase.", "obligatoire"), ("Écris « Ils transportent les passagers » au passé composé.", "Ils ont transporté les passagers.")]),
        "M4": ("La case de l'oncle", "Mon oncle a construit sa case avec de la terre de barre. Il a mélangé la terre et l'eau, puis il a façonné des briques qu'il a laissées sécher au soleil. Le toit est fait de tôles ondulées. À l'intérieur, il fait frais même pendant les grosses chaleurs.",
               [("Donne le contraire de « frais ».", "chaud"), ("Relève le complément d'objet direct du verbe « a façonné ».", "des briques"), ("Conjugue « construire » au futur simple avec « nous ».", "nous construirons")]),
        "T2": ("La coopérative scolaire", "Les élèves de notre école ont créé une coopérative. Chaque semaine, ils vendent des cahiers, des bics et des gommes à leurs camarades. Le trésorier note toutes les recettes dans un registre. Avec les bénéfices, la coopérative a acheté des livres pour la bibliothèque.",
               [("Qu'est-ce qu'un « trésorier » ?", "la personne qui garde l'argent et tient les comptes"), ("Relève deux compléments d'objet direct du verbe « vendent ».", "des cahiers, des bics et des gommes"), ("Mets « Le trésorier note toutes les recettes » au pluriel.", "Les trésoriers notent toutes les recettes.")]),
        "M5": ("La pêche à la ligne", "Assis sur la berge, Issa attendait depuis une heure. Soudain, le bouchon de sa ligne disparut sous l'eau. Il tira d'un coup sec et un gros poisson argenté apparut au bout du fil. Fier de sa prise, il courut la montrer à son père.",
               [("Relève deux verbes au passé simple.", "disparut, tira (apparut, courut)"), ("Donne l'infinitif de « disparut ».", "disparaître"), ("Remplace « Issa » par « Issa et son frère » dans la première phrase.", "Assis sur la berge, Issa et son frère attendaient depuis une heure.")]),
        "M6": ("Le conte du soir", "Le soir, autour du feu, grand-père raconte des contes. Il imite la voix du lièvre rusé et celle de l'hyène gourmande. Les enfants l'écoutent sans bouger, les yeux brillants. À la fin, il leur demande de trouver la morale de l'histoire.",
               [("Que veut dire « rusé » ?", "malin, habile à tromper"), ("Relève les adjectifs qualificatifs de la deuxième phrase.", "rusé, gourmande"), ("Écris « Grand-père raconte des contes » au passé composé.", "Grand-père a raconté des contes.")]),
        "T3": ("La journée de salubrité", "Le premier samedi du mois, tous les habitants du quartier participent à la journée de salubrité. On balaie les rues, on cure les caniveaux et on brûle les herbes sèches loin des maisons. Les enfants ramassent les sachets plastiques qui bouchent les égouts.",
               [("Que signifie « salubrité » ?", "la propreté qui protège la santé"), ("Relève le sujet du verbe « bouchent ».", "qui (mis pour les sachets plastiques)"), ("Conjugue « participer » à l'imparfait avec « nous ».", "nous participions")]),
        "FA": ("Le passage au CM2", "Les résultats de fin d'année sont affichés devant le bureau du directeur. Les élèves se bousculent pour lire leur nom. Kémi a obtenu une bonne moyenne : elle passe au CM2. L'an prochain, elle préparera le certificat d'études avec courage.",
               [("Donne un synonyme de « se bousculent ».", "se poussent"), ("Relève le complément circonstanciel de lieu de la première phrase.", "devant le bureau du directeur"), ("À quel temps est « préparera » ? Donne son infinitif.", "futur simple ; préparer")]),
    },
    "CM2": {
        "M1": ("Le retour des pluies", "Après plusieurs mois de sécheresse, de gros nuages noirs s'amoncellent à l'horizon. Un vent violent soulève la poussière et fait claquer les volets. Puis les premières gouttes tombent, lourdes et tièdes. Les enfants poussent des cris de joie tandis que les cultivateurs se réjouissent en silence.",
               [("Que veut dire « s'amoncellent » ?", "s'entassent, s'accumulent"), ("Relève le sujet du verbe « tombent ».", "les premières gouttes"), ("Écris la dernière phrase à l'imparfait.", "Les enfants poussaient des cris de joie tandis que les cultivateurs se réjouissaient en silence.")]),
        "M2": ("Le forgeron", "Au fond de son atelier sombre, le forgeron active le feu avec un soufflet de peau. Lorsque le fer devient rouge, il le saisit avec une longue pince et le frappe sur l'enclume. Les étincelles jaillissent. Peu à peu, la barre informe se change en une houe solide que le paysan viendra chercher demain.",
               [("Que signifie « informe » ?", "qui n'a pas de forme précise"), ("Relève une proposition subordonnée relative.", "que le paysan viendra chercher demain"), ("Donne la nature et la fonction de « solide ».", "adjectif qualificatif, épithète de « houe »")]),
        "T1": ("La route des pèlerins", "Chaque année, à Ouidah, des milliers de visiteurs parcourent la route des esclaves jusqu'à la porte du Non-retour. Ils écoutent les guides raconter l'histoire douloureuse des hommes et des femmes arrachés à leur terre. Ce lieu de mémoire nous rappelle que la liberté est un bien précieux.",
               [("Que veut dire « un lieu de mémoire » ?", "un endroit qui rappelle des événements importants du passé"), ("Relève le complément d'objet direct du verbe « parcourent ».", "la route des esclaves"), ("Écris « Ils écoutent les guides » au passé simple.", "Ils écoutèrent les guides.")]),
        "M3": ("L'école d'autrefois", "Grand-père se souvient de son école. Il y allait pieds nus, son ardoise sous le bras. La classe comptait plus de soixante élèves assis sur des bancs de bois. Le maître, très sévère, exigeait le silence absolu. Pourtant, grand-père garde un souvenir heureux de ces années où il a appris à lire.",
               [("Donne le contraire de « sévère ».", "indulgent (gentil, doux)"), ("Relève un complément circonstanciel de manière.", "pieds nus (son ardoise sous le bras)"), ("Conjugue « se souvenir » au présent avec « nous ».", "nous nous souvenons")]),
        "M4": ("Le reboisement", "Pour lutter contre l'avancée du désert, les élèves de notre école ont planté cent jeunes tecks au bord de la route. Chaque groupe est responsable de dix plants qu'il arrose et protège des chèvres. Si nous les entretenons bien, ces arbres donneront de l'ombre et du bois à nos enfants.",
               [("Que veut dire « l'avancée du désert » ?", "le désert qui gagne du terrain (la désertification)"), ("Relève la proposition subordonnée de condition.", "Si nous les entretenons bien"), ("Écris la première phrase au futur simple.", "Pour lutter contre l'avancée du désert, les élèves de notre école planteront cent jeunes tecks au bord de la route.")]),
        "T2": ("Le téléphone portable", "Aujourd'hui, presque chaque famille possède un téléphone portable. Il permet d'appeler un parent éloigné, d'envoyer de l'argent ou de s'informer. Mais mal utilisé, il peut devenir dangereux : certains enfants y passent des heures et négligent leurs leçons. Il faut donc s'en servir avec mesure.",
               [("Que signifie « avec mesure » ?", "sans excès, raisonnablement"), ("Relève les trois compléments du verbe « permet ».", "d'appeler un parent éloigné, d'envoyer de l'argent, de s'informer"), ("Remplace « certains enfants » par « mon frère » et récris la fin de la phrase.", "mon frère y passe des heures et néglige ses leçons")]),
        "M5": ("La pirogue de Ganvié", "Ganvié est un village bâti sur pilotis au milieu du lac Nokoué. Ici, pas de rues : on se déplace en pirogue. Les enfants pagaient pour aller à l'école, les femmes vendent leurs marchandises au marché flottant. Les touristes admirent ce village unique, que l'on surnomme parfois la Venise de l'Afrique.",
               [("Que veut dire « bâti sur pilotis » ?", "construit sur des pieux plantés dans l'eau"), ("Relève le complément circonstanciel de lieu de la première phrase.", "au milieu du lac Nokoué"), ("Donne la fonction de « unique ».", "épithète du nom « village »")]),
        "M6": ("La lettre du correspondant", "Mon correspondant vit à Natitingou, au pied de la chaîne de l'Atacora. Dans sa dernière lettre, il m'a décrit les collines, les cascades de Kota et les maisons en terre appelées tata. Il m'invite pendant les vacances. J'espère que mes parents accepteront, car je rêve de découvrir le Nord.",
               [("Qu'est-ce qu'un « correspondant » ?", "une personne avec qui on échange des lettres (des messages)"), ("Relève une proposition subordonnée introduite par « que ».", "que mes parents accepteront"), ("Écris « il m'a décrit les collines » au plus-que-parfait.", "il m'avait décrit les collines")]),
        "T3": ("Le jour de l'examen", "Le jour de l'examen est enfin arrivé. Dès sept heures, les candidats attendent devant le centre, leur convocation à la main. Certains révisent une dernière fois, d'autres plaisantent pour cacher leur peur. Quand le chef de centre appelle leur nom, ils entrent en silence et s'installent à leur place.",
               [("Donne un synonyme de « plaisantent ».", "blaguent (rient)"), ("Relève une proposition subordonnée de temps.", "Quand le chef de centre appelle leur nom"), ("Écris la dernière phrase au passé simple.", "Quand le chef de centre appela leur nom, ils entrèrent en silence et s'installèrent à leur place.")]),
    },
}

# CEP blancs : les trois dictées de 1.21 (banque_textes.DICTEES) reçoivent leurs questions
QUESTIONS_CEP = {
    "C1": [("Que veut dire « dès l'aube » ?", "très tôt le matin, au lever du jour"), ("Relève le sujet du verbe « déchargent ».", "les camions"), ("Écris « Les vendeuses installent leurs étalages » au passé composé.", "Les vendeuses ont installé leurs étalages.")],
    "C2": [("Donne un mot de la famille de « champs ».", "champêtre"), ("Relève une proposition subordonnée relative.", "qui attendaient ce moment depuis des semaines"), ("Écris « Les enfants courent dans les flaques » à l'imparfait.", "Les enfants couraient dans les flaques.")],
    "C3": [("Que veut dire « curer les caniveaux » ?", "nettoyer les caniveaux en enlevant ce qui les bouche"), ("Relève le complément d'objet direct du verbe « a remercié ».", "chacun"), ("Conjugue « se réunir » au présent avec « nous ».", "nous nous réunissons")],
}

BAREME_FAUTES = ["Faute grave (accord sujet-verbe ou nom-adjectif, conjugaison, mot outil, mot oublié ou ajouté) : − 1 point",
                 "Faute d'usage (orthographe d'un mot) : − ½ point",
                 "Accent, majuscule, cédille, trait d'union, ponctuation : − ¼ point",
                 "Une même faute répétée n'est comptée qu'une fois ; la note ne descend pas au-dessous de 0"]
BAREME_CI = ["Chaque élément (lettre, syllabe, mot) bien écrit : points répartis également",
             "Élément lisible mais mal formé : moitié des points", "Élément illisible ou absent : 0"]


def dictee(cours, per):
    """(titre, texte, questions) de la dictée du cours pour la période (repli : période la plus proche)."""
    if per in ("C1", "C2", "C3"):
        import banque_textes as BX
        t, x = BX.DICTEES[per]
        return t, x, QUESTIONS_CEP[per]
    banque = D[cours]
    if per in banque:
        return banque[per]
    return banque[next(p for p in reversed(PERIODES_DICTEE) if p in banque)]
