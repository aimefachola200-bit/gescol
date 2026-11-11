# -*- coding: utf-8 -*-
"""v1.21 — Banque d'épreuves : supports de COMPRÉHENSION DE L'ÉCRIT (rédaction originale SCOLARIS) et dictées du CEP blanc.

Clé : (cours, période). Périodes : M1 … M6 (évaluations mensuelles d'octobre, novembre, janvier, février, avril, mai),
T1, T2, T3 (sommatives trimestrielles), FA (fin d'année / évaluation de passage), C1 … C3 (examens blancs du CEP, CM2).
Les épreuves trimestrielles et de fin d'année du CE1 au CM2 sont des REFORMULATIONS des épreuves standardisées de
l'INFRE (mêmes compétences, même difficulté, contextes et supports nouveaux) ; toutes les autres sont des créations.
Chaque entrée : titre, contexte (mise en situation), texte (support), items = [[(question, réponse attendue), …], …]
(Item 1 compréhension, Item 2 fonctionnement de la langue, Item 3 appréciation / réaction, Item 4 prolongement au
CE2 → CM2). « RP : » = réponse personnelle, à apprécier selon l'indicateur donné.
"""

T = {}


def _t(cours, per, titre, contexte, texte, *items, infre=None):
    T[(cours, per)] = {"titre": titre, "contexte": contexte, "texte": texte, "items": [list(i) for i in items], "infre": infre}


# ===================================================================================== CI (lecture d'images, de mots, de phrases courtes)
_t("CI", "M1", "Bonjour maître", "À l'école, on salue le maître et les camarades.",
   "Ali arrive à l'école. Il dit : « Bonjour maître ! »",
   [("Qui arrive à l'école ?", "Ali"), ("Que dit Ali ?", "Bonjour maître !")],
   [("Entoure le mot « Ali » dans la phrase.", "Le mot Ali est entouré."), ("Combien de mots compte la phrase « Ali arrive à l'école » ?", "4 mots")],
   [("Et toi, que dis-tu au maître le matin ?", "RP : une formule de salutation correcte (Bonjour maître / maîtresse).")])
_t("CI", "M2", "Ma famille", "Chaque enfant vit avec sa famille.",
   "Voici papa. Voici maman. Voici bébé Lola.",
   [("Cite les personnes de la famille.", "papa, maman, bébé Lola"), ("Comment s'appelle le bébé ?", "Lola")],
   [("Recopie le mot « papa ».", "papa (copie correcte)"), ("Quelle lettre entends-tu au début de « maman » ?", "m")],
   [("Dessine une personne de ta famille et dis son nom.", "RP : dessin et nom d'un membre de la famille.")])
_t("CI", "M3", "Le ballon", "Pendant la récréation, les enfants jouent.",
   "Koffi a un ballon. Il joue avec Awa dans la cour.",
   [("Qui a un ballon ?", "Koffi"), ("Avec qui joue-t-il ?", "avec Awa"), ("Où jouent-ils ?", "dans la cour")],
   [("Entoure la lettre « a » dans « ballon ».", "ball(a)on : le a est entouré"), ("Écris la syllabe « la ».", "la")],
   [("Aimes-tu jouer avec tes camarades ? Pourquoi ?", "RP : réponse simple et justifiée (oui, parce que c'est amusant…).")])
_t("CI", "M4", "Au marché", "Maman va souvent au marché.",
   "Maman va au marché. Elle achète des tomates et du pain.",
   [("Où va maman ?", "au marché"), ("Qu'achète-t-elle ?", "des tomates et du pain")],
   [("Lis les mots : maman — marché — pain.", "Lecture correcte des trois mots"), ("Quel mot commence comme « maman » : pain ou marché ?", "marché")],
   [("Qu'achèterais-tu au marché ?", "RP : un ou deux produits du marché.")])
_t("CI", "M5", "La pluie", "En saison des pluies, il pleut souvent.",
   "Il pleut. Fati prend son parapluie. Elle va à l'école.",
   [("Quel temps fait-il ?", "Il pleut."), ("Que prend Fati ?", "son parapluie")],
   [("Combien de phrases y a-t-il dans le texte ?", "3"), ("Recopie le mot « pluie ».", "pluie (copie correcte)")],
   [("Que fais-tu quand il pleut ?", "RP : un comportement adapté (je m'abrite, je prends mon parapluie…).")])
_t("CI", "M6", "Le chat", "Beaucoup de maisons ont un chat.",
   "Le chat de Rémi est petit. Il boit du lait.",
   [("À qui est le chat ?", "à Rémi"), ("Que boit le chat ?", "du lait")],
   [("Entoure les mots « le chat ».", "les mots sont entourés"), ("Écris un mot qui commence par « l ».", "lait (ou tout autre mot correct)")],
   [("As-tu un animal à la maison ? Lequel ?", "RP : nom d'un animal domestique.")])
_t("CI", "T1", "La rentrée", "C'est la rentrée des classes.",
   "C'est la rentrée. Sika a un cahier, une ardoise et une craie.",
   [("Qui fait la rentrée ?", "Sika"), ("Cite les objets de Sika.", "un cahier, une ardoise, une craie")],
   [("Lis : cahier — ardoise — craie.", "lecture correcte"), ("Quel objet sert à écrire au tableau ?", "la craie")],
   [("Quel objet préfères-tu ? Pourquoi ?", "RP : un objet scolaire et une raison simple.")])
_t("CI", "T2", "Le repas", "Toute la famille mange ensemble.",
   "Papa, maman et les enfants mangent. Ils se lavent les mains avant le repas.",
   [("Qui mange ?", "papa, maman et les enfants"), ("Que font-ils avant le repas ?", "Ils se lavent les mains.")],
   [("Entoure le mot « mains ».", "le mot est entouré"), ("Écris la première lettre du mot « repas ».", "r")],
   [("Pourquoi faut-il se laver les mains avant de manger ?", "RP : pour être propre, pour ne pas tomber malade.")])
_t("CI", "T3", "La fête", "À la fin de l'année, l'école fait une fête.",
   "C'est la fête à l'école. Les enfants chantent et dansent.",
   [("Où est la fête ?", "à l'école"), ("Que font les enfants ?", "Ils chantent et dansent.")],
   [("Lis : fête — chantent — dansent.", "lecture correcte"), ("Combien de mots dans « Les enfants chantent » ?", "3")],
   [("Aimes-tu chanter ? Dis le titre d'un chant.", "RP : titre d'un chant connu.")])
_t("CI", "FA", "Le petit jardin", "À l'école, les élèves ont un jardin.",
   "Les élèves arrosent le jardin. Les fleurs sont jolies. Le maître est content.",
   [("Que font les élèves ?", "Ils arrosent le jardin."), ("Comment sont les fleurs ?", "jolies"), ("Qui est content ?", "le maître")],
   [("Entoure les mots qui commencent par « j ».", "jardin, jolies"), ("Recopie la phrase « Les fleurs sont jolies. »", "copie correcte avec la majuscule et le point")],
   [("Que faut-il faire pour avoir de jolies fleurs ?", "RP : les arroser, en prendre soin.")])

# ===================================================================================== CP
_t("CP", "M1", "À l'école", "Le matin, les élèves vont à l'école.",
   "Lola va à l'école avec son ami Tobi. Ils arrivent tôt. Le maître les salue.",
   [("Avec qui Lola va-t-elle à l'école ?", "avec son ami Tobi"), ("Qui salue les enfants ?", "le maître")],
   [("Découpe en syllabes : école.", "é-co-le"), ("Écris le mot « ami » au pluriel : des …", "des amis")],
   [("Pourquoi faut-il arriver tôt à l'école ?", "RP : pour ne pas être en retard, pour bien suivre.")])
_t("CP", "M2", "Le bébé de tata", "Tata a un bébé. Toute la famille est contente.",
   "Tata a un joli bébé. Il a des petits pieds et une petite main. Maman le porte au dos.",
   [("Qui a un bébé ?", "Tata"), ("Qui porte le bébé au dos ?", "Maman")],
   [("Relève le mot qui contient le son [é].", "bébé"), ("Complète : un pied, des …", "des pieds")],
   [("Comment faut-il prendre soin d'un bébé ?", "RP : le laver, le nourrir, le protéger.")])
_t("CP", "M3", "La moto de papa", "Papa a acheté une moto.",
   "Papa a une moto rouge. Il porte un casque. Il roule doucement sur la route.",
   [("De quelle couleur est la moto ?", "rouge"), ("Que porte papa ?", "un casque")],
   [("Relève un mot qui commence par le son [r].", "rouge (ou roule, route)"), ("Combien de phrases compte le texte ?", "3")],
   [("Pourquoi papa porte-t-il un casque ?", "RP : pour protéger sa tête en cas d'accident.")])
_t("CP", "M4", "Le puits", "Au village, on va chercher l'eau.",
   "Rémi et sa sœur vont au puits. Ils puisent de l'eau propre. Ils la couvrent bien.",
   [("Où vont Rémi et sa sœur ?", "au puits"), ("Que font-ils de l'eau ?", "Ils la couvrent bien.")],
   [("Relève le mot qui contient le son [ou].", "couvrent"), ("Mets au pluriel : la sœur → les …", "les sœurs")],
   [("Pourquoi faut-il couvrir l'eau ?", "RP : pour qu'elle reste propre, pour éviter les maladies.")])
_t("CP", "M5", "Le marché du samedi", "Le samedi, c'est jour de marché.",
   "Le samedi, Awa va au marché avec sa mère. Elles achètent du maïs, des oranges et du poisson.",
   [("Quel jour Awa va-t-elle au marché ?", "le samedi"), ("Cite deux produits achetés.", "du maïs, des oranges (ou du poisson)")],
   [("Relève le mot qui contient le son [on].", "poisson (ou oranges)"), ("Écris le contraire de « avec » : …", "sans")],
   [("Aimes-tu aller au marché ? Pourquoi ?", "RP : réponse justifiée.")])
_t("CP", "M6", "Le drapeau", "Chaque lundi, on lève les couleurs.",
   "Le lundi, les élèves se mettent en rang. Ils chantent l'hymne national. Le drapeau monte.",
   [("Quel jour lève-t-on les couleurs ?", "le lundi"), ("Que chantent les élèves ?", "l'hymne national")],
   [("Relève le mot qui contient le son [an].", "rang (ou chantent)"), ("Remets en ordre : monte / drapeau / Le", "Le drapeau monte.")],
   [("Comment te tiens-tu pendant le lever des couleurs ?", "RP : debout, au garde-à-vous, en silence.")])
_t("CP", "T1", "Le petit vélo", "Les enfants aiment jouer après l'école.",
   "Tobi a un petit vélo bleu. Il roule dans la cour. Il ne va pas sur la route.",
   [("Comment est le vélo de Tobi ?", "petit et bleu"), ("Où roule Tobi ?", "dans la cour")],
   [("Découpe en syllabes : vélo.", "vé-lo"), ("Relève le mot qui dit le contraire de « grand ».", "petit")],
   [("Pourquoi Tobi ne va-t-il pas sur la route ?", "RP : parce que c'est dangereux.")])
_t("CP", "T2", "Le jour de pluie", "En saison des pluies, il faut se protéger.",
   "Il pleut beaucoup. Lola reste à la maison. Elle lit un joli livre avec son frère.",
   [("Pourquoi Lola reste-t-elle à la maison ?", "parce qu'il pleut beaucoup"), ("Que fait-elle ?", "Elle lit un livre avec son frère.")],
   [("Relève le mot qui contient le son [i].", "livre (ou lit, joli)"), ("Mets au pluriel : un livre → des …", "des livres")],
   [("Que fais-tu à la maison quand il pleut ?", "RP : activité calme et adaptée.")])
_t("CP", "T3", "Le jardin de l'école", "L'école a un jardin potager.",
   "Les élèves du CP sèment des tomates. Chaque matin, ils arrosent. Bientôt, ils vont récolter.",
   [("Que sèment les élèves ?", "des tomates"), ("Que font-ils chaque matin ?", "Ils arrosent.")],
   [("Relève le mot qui contient le son [o].", "tomates"), ("Complète : je sème, tu …", "tu sèmes")],
   [("Pourquoi faut-il arroser les plantes ?", "RP : parce qu'elles ont besoin d'eau pour pousser.")])
_t("CP", "FA", "La visite chez grand-mère", "Pendant les congés, on rend visite à la famille.",
   "Pendant les congés, Sika va chez sa grand-mère au village. Elle l'aide à balayer la cour et à porter l'eau. Le soir, grand-mère raconte un conte.",
   [("Où va Sika pendant les congés ?", "chez sa grand-mère au village"), ("Comment aide-t-elle sa grand-mère ?", "Elle balaie la cour et porte l'eau."), ("Que fait grand-mère le soir ?", "Elle raconte un conte.")],
   [("Relève le mot qui contient le son [on].", "conte"), ("Écris la phrase « Sika aide sa grand-mère » avec « Sika et Ali » : Sika et Ali …", "Sika et Ali aident leur grand-mère.")],
   [("Aimes-tu écouter les contes ? Pourquoi ?", "RP : réponse justifiée.")])

# ===================================================================================== CE1 (T1–FA : d'après INFRE 2016, reformulées)
_t("CE1", "M1", "Le cahier propre", "Un bon élève prend soin de ses affaires.",
   "Akim couvre son cahier avec du papier bleu. Il écrit son nom sur l'étiquette. Il ne fait pas de taches. Le maître le félicite.",
   [("Avec quoi Akim couvre-t-il son cahier ?", "avec du papier bleu"), ("Qu'écrit-il sur l'étiquette ?", "son nom"), ("Pourquoi le maître le félicite-t-il ?", "parce que son cahier est propre / il ne fait pas de taches")],
   [("Relève le verbe de la phrase : « Il écrit son nom. »", "écrit"), ("Donne l'infinitif du verbe « couvre ».", "couvrir"), ("Découpe en syllabes : étiquette.", "é-ti-quet-te")],
   [("Comment prends-tu soin de tes cahiers ?", "RP : au moins deux gestes (couvrir, ne pas salir, ranger…).")])
_t("CE1", "M2", "La moustiquaire", "Le paludisme est une maladie dangereuse.",
   "Chaque soir, maman installe la moustiquaire sur le lit des enfants. Elle dit : « Les moustiques donnent le paludisme. Dormez bien sous la moustiquaire. »",
   [("Que fait maman chaque soir ?", "Elle installe la moustiquaire sur le lit des enfants."), ("Quelle maladie donnent les moustiques ?", "le paludisme")],
   [("Relève le nom commun au pluriel dans : « Les moustiques donnent le paludisme. »", "moustiques"), ("Mets au singulier : les enfants dorment → l'enfant …", "l'enfant dort"), ("Trouve le contraire de « soir ».", "matin")],
   [("Que fais-tu pour ne pas avoir le paludisme ?", "RP : dormir sous moustiquaire imprégnée, vider les eaux stagnantes…")])
_t("CE1", "M3", "Le droit d'aller à l'école", "Tous les enfants ont le droit d'aller à l'école.",
   "Fati a huit ans. Elle va à l'école chaque matin. Le soir, elle aide sa mère puis elle apprend ses leçons. Elle veut devenir sage-femme.",
   [("Quel âge a Fati ?", "huit ans"), ("Que fait-elle le soir ?", "Elle aide sa mère puis apprend ses leçons."), ("Quel métier veut-elle faire ?", "sage-femme")],
   [("Relève les verbes de la phrase : « Elle aide sa mère puis elle apprend ses leçons. »", "aide, apprend"), ("Mets au futur : « Fati va à l'école. »", "Fati ira à l'école.")],
   [("Pourquoi est-il important d'aller à l'école ?", "RP : pour apprendre, avoir un métier…")])
_t("CE1", "M4", "La cour propre", "Une école propre est une école agréable.",
   "Le lundi, les élèves balaient la cour. Ils ramassent les sachets et les mettent dans la poubelle. L'école est propre et belle.",
   [("Quel jour les élèves balaient-ils la cour ?", "le lundi"), ("Où mettent-ils les sachets ?", "dans la poubelle")],
   [("Relève l'adjectif qualificatif dans : « L'école est propre et belle. »", "propre, belle"), ("Mets au passé composé : « Ils ramassent les sachets. »", "Ils ont ramassé les sachets.")],
   [("Pourquoi faut-il garder l'école propre ?", "RP : pour la santé, pour la beauté de l'école.")])
_t("CE1", "M5", "La fête de l'igname", "Chaque année, des fêtes réunissent les habitants.",
   "Au village de mon grand-père, on fête la nouvelle igname. Les tam-tams résonnent. Les femmes préparent de l'igname pilée pour tous les invités.",
   [("Que fête-t-on au village ?", "la nouvelle igname"), ("Que préparent les femmes ?", "de l'igname pilée")],
   [("Relève le sujet du verbe « préparent ».", "Les femmes"), ("Écris au pluriel : un invité → des …", "des invités")],
   [("Connais-tu une fête de ta localité ? Dis son nom.", "RP : nom d'une fête locale.")])
_t("CE1", "M6", "Le chef du village", "Chaque village a un chef.",
   "Le chef du village réunit les habitants sous le grand arbre. Il annonce la construction d'un nouveau puits. Tout le monde applaudit.",
   [("Où le chef réunit-il les habitants ?", "sous le grand arbre"), ("Qu'annonce-t-il ?", "la construction d'un nouveau puits")],
   [("Relève le verbe conjugué de : « Tout le monde applaudit. »", "applaudit"), ("Donne le contraire de « nouveau ».", "ancien / vieux")],
   [("Pourquoi les habitants applaudissent-ils ?", "RP : parce qu'ils sont contents d'avoir de l'eau.")])
_t("CE1", "T1", "Je suis grande maintenant",
   "Quand l'enfant est petit, les parents font tout pour lui. En grandissant, il apprend à faire beaucoup de choses seul. Dans le texte suivant, une fillette raconte ce qu'elle sait faire.",
   "Quand j'étais bébé, maman me lavait et me portait au dos. Maintenant, je m'habille seule. Je range ma natte et je balaie la cour. À l'école, je fais mes exercices et j'aide mes camarades. Sur la route, je marche à gauche. Moi, Ayaba, je suis vraiment grande !",
   [("Relève le nom de celle qui parle.", "Ayaba"), ("Cite une chose qu'elle fait à la maison.", "Elle s'habille seule / range sa natte / balaie la cour."), ("Cite une chose qu'elle fait à l'école.", "Elle fait ses exercices / aide ses camarades.")],
   [("Recopie la deuxième phrase du texte.", "Maintenant, je m'habille seule."), ("Découpe en syllabes le mot « camarades ».", "ca-ma-ra-des"), ("Donne l'infinitif du verbe « balaie ».", "balayer")],
   [("Relève la phrase qui montre qu'Ayaba a grandi.", "Moi, Ayaba, je suis vraiment grande ! (ou Maintenant, je m'habille seule.)"), ("Dis une chose qu'Ayaba ne peut pas encore faire seule.", "RP : une activité d'adulte (conduire, faire le marché seule…).")],
   infre="2016")
_t("CE1", "T2", "La trottinette de Codjo",
   "Un dimanche, Codjo veut essayer la trottinette de son cousin. Lis le texte pour savoir ce qui lui est arrivé et en tirer une leçon.",
   "Codjo emprunte la trottinette de son cousin. Il fait quelques tours devant la maison. Il se sent fort. Il descend alors la pente qui mène au marché. Il roule de plus en plus vite. Soudain, une moto sort d'une ruelle. Codjo prend peur et tombe. Le conducteur freine à temps. Codjo se relève avec une bosse au front et le genou écorché.",
   [("Cite les personnages du texte.", "Codjo, son cousin, le conducteur de moto"), ("« Codjo se sent fort » veut dire : il a confiance en lui / il est malade. Choisis.", "il a confiance en lui"), ("La moto a renversé Codjo. Vrai ou faux ?", "Faux : Codjo est tombé de peur ; le conducteur a freiné à temps.")],
   [("« La pente est raide. » Donne la nature du mot « raide ».", "adjectif qualificatif"), ("« Il roule vite. » À quel temps est conjugué le verbe ?", "au présent de l'indicatif"), ("Mets au futur simple : « Codjo prend peur. »", "Codjo prendra peur.")],
   [("Qu'est-ce qui a provoqué la chute de Codjo ?", "la vitesse / la peur quand la moto est sortie"), ("Qu'a fait le conducteur pour éviter l'accident ?", "Il a freiné à temps."), ("Donne un conseil à Codjo.", "RP : ne pas rouler vite, ne pas jouer près de la route…")],
   infre="2016")
_t("CE1", "T3", "La kermesse de l'école",
   "Avant les grandes vacances, certaines écoles organisent une kermesse. Voici un texte qui en parle.",
   "L'année scolaire s'achève. La directrice a décidé d'organiser une kermesse le dernier samedi de juin. Les élèves les plus méritants recevront des livres. L'association des parents d'élèves offre des ballons et le chef d'arrondissement apporte des cahiers.",
   [("Dis qui a décidé d'organiser la kermesse.", "la directrice"), ("Dis quand elle aura lieu.", "le dernier samedi de juin"), ("Dis ce que recevront les élèves méritants.", "des livres")],
   [("Dans « Le chef d'arrondissement apporte des cahiers », relève le verbe conjugué.", "apporte"), ("Mets au présent : « La directrice a décidé d'organiser une kermesse. »", "La directrice décide d'organiser une kermesse."), ("Remplace « s'achève » par une expression de même sens.", "se termine / touche à sa fin")],
   [("Que dois-tu faire pour être récompensé ?", "RP : bien travailler, être assidu et sage."), ("Donne deux raisons pour lesquelles les élèves aiment les vacances.", "RP : se reposer, jouer, voyager…")],
   infre="2016")
_t("CE1", "FA", "Le travail de Bio",
   "Tous les enfants ont droit à l'éducation, mais certains ne vont pas à l'école. Le texte suivant te le montre.",
   "Bio a dix ans. Il ne va pas à l'école. Dès l'aube, il conduit les bœufs de son oncle au pâturage. À midi, il mange un peu de pâte froide. Le soir, il rentre fatigué, puis il va chercher du bois et de l'eau. Bio est petit, mais il travaille comme un adulte.",
   [("Relève la phrase qui montre que Bio ne va pas à l'école.", "Il ne va pas à l'école."), ("Cite les personnages du texte.", "Bio, son oncle"), ("Relève les travaux que Bio fait le soir.", "Il va chercher du bois et de l'eau.")],
   [("Relève les verbes de la phrase : « Bio est petit, mais il travaille comme un adulte. »", "est, travaille"), ("Écris au passé composé : « Il conduit les bœufs. »", "Il a conduit les bœufs."), ("« Dès l'aube » veut dire : très tôt le matin / le soir. Choisis.", "très tôt le matin")],
   [("Bio ne va pas à l'école : est-ce une bonne chose ?", "Non."), ("Dis pourquoi.", "RP : il a droit à l'éducation, il ne pourra pas apprendre…"), ("Donne deux conseils à l'oncle de Bio.", "RP : l'inscrire à l'école, ne pas le faire travailler comme un adulte.")],
   infre="2016")

# ===================================================================================== CE2 (T1–FA : d'après INFRE 2015, reformulées)
_t("CE2", "M1", "La visite médicale", "À l'école, les élèves reçoivent la visite de l'infirmier.",
   "Ce matin, l'infirmier du centre de santé est venu à l'école. Il a pesé les élèves et vérifié leurs carnets de vaccination. Il a rappelé qu'il faut se laver les mains au savon et dormir sous une moustiquaire.",
   [("Qui est venu à l'école ?", "l'infirmier du centre de santé"), ("Qu'a-t-il vérifié ?", "les carnets de vaccination"), ("Cite un conseil donné.", "se laver les mains au savon / dormir sous moustiquaire")],
   [("Relève le verbe conjugué de : « Il a pesé les élèves. » Donne son infinitif.", "a pesé — peser"), ("Mets au présent : « Il a rappelé les règles d'hygiène. »", "Il rappelle les règles d'hygiène."), ("Trouve un mot de la même famille que « santé ».", "sain, assainir, sanitaire…")],
   [("Pourquoi faut-il se faire vacciner ?", "RP : pour se protéger des maladies.")],
   [("Imagine ce qui arrive à un enfant qui ne se lave jamais les mains.", "RP : il peut tomber malade (diarrhée, vers…).")])
_t("CE2", "M2", "L'arbre de la cour", "Les arbres sont utiles à l'homme.",
   "Dans la cour de notre école, un vieux manguier nous donne de l'ombre. Pendant la récréation, nous nous asseyons sous ses branches. Hier, des inconnus voulaient le couper pour faire du charbon. Le directeur s'y est opposé.",
   [("Quel arbre se trouve dans la cour ?", "un vieux manguier"), ("Que voulaient faire les inconnus ?", "le couper pour faire du charbon"), ("Qui s'y est opposé ?", "le directeur")],
   [("Relève le complément de lieu dans : « Nous nous asseyons sous ses branches. »", "sous ses branches"), ("Donne le contraire de « vieux ».", "jeune"), ("Mets au futur simple : « Le manguier nous donne de l'ombre. »", "Le manguier nous donnera de l'ombre.")],
   [("Le directeur a-t-il eu raison ? Justifie.", "Oui : l'arbre donne de l'ombre et des fruits, il protège l'environnement.")],
   [("Propose une action pour protéger les arbres de ton école.", "RP : arroser, protéger, planter, interdire la coupe.")])
_t("CE2", "M3", "Le téléphone de tonton", "Les appareils modernes nous rendent service.",
   "Tonton Rachad habite à Parakou. Chaque dimanche, il appelle maman sur son téléphone portable. Grâce à l'appareil, ils se voient et se parlent comme s'ils étaient ensemble. Maman dit que c'est une belle invention.",
   [("Où habite tonton Rachad ?", "à Parakou"), ("Quand appelle-t-il maman ?", "chaque dimanche"), ("Que permet le téléphone ?", "de se voir et de se parler à distance")],
   [("Relève le pronom personnel sujet dans : « Il appelle maman. »", "Il"), ("Donne la nature de « belle ».", "adjectif qualificatif"), ("Mets au passé composé : « Ils se parlent. »", "Ils se sont parlé.")],
   [("Le téléphone est-il toujours utile ? Justifie.", "RP : oui pour communiquer, mais il ne faut pas en abuser.")],
   [("Imagine un appareil qui t'aiderait à l'école.", "RP : invention décrite simplement.")])
_t("CE2", "M4", "Le droit d'Aïcha", "Les filles et les garçons ont les mêmes droits.",
   "Aïcha est la meilleure élève de sa classe. Son père veut la retirer de l'école pour qu'elle vende au marché. Son maître explique au père que sa fille a le droit d'étudier comme ses frères. Le père accepte enfin qu'elle continue.",
   [("Qui est la meilleure élève de la classe ?", "Aïcha"), ("Que voulait faire le père ?", "la retirer de l'école pour qu'elle vende au marché"), ("Qui a convaincu le père ?", "le maître")],
   [("Relève le complément d'objet direct dans : « Son père veut la retirer. »", "la"), ("Écris au féminin : le meilleur élève → la …", "la meilleure élève"), ("Trouve un synonyme de « étudier ».", "apprendre")],
   [("Que penses-tu de la décision du père au début ?", "RP : elle est injuste, Aïcha a droit à l'éducation.")],
   [("Imagine ce que deviendra Aïcha plus tard.", "RP : métier ou réussite décrite.")])
_t("CE2", "M5", "Le musée d'Abomey", "Les musées gardent les traces du passé.",
   "Pendant les congés, notre classe a visité le musée historique d'Abomey. Le guide nous a montré les trônes des rois, les récades et les tentures. Il nous a dit que ces objets racontent l'histoire du royaume du Danxomè.",
   [("Quel musée la classe a-t-elle visité ?", "le musée historique d'Abomey"), ("Cite deux objets montrés par le guide.", "les trônes, les récades (ou les tentures)"), ("De quel royaume parlent ces objets ?", "du royaume du Danxomè")],
   [("Relève le verbe et donne son temps : « Notre classe a visité le musée. »", "a visité — passé composé"), ("Mets au pluriel : « Le guide montre le trône. »", "Les guides montrent les trônes."), ("Donne le sens de « congés ».", "jours de repos / vacances")],
   [("Pourquoi faut-il protéger les musées ?", "RP : ils gardent notre histoire, notre patrimoine.")],
   [("Quel objet aimerais-tu voir au musée ? Pourquoi ?", "RP : objet et raison.")])
_t("CE2", "M6", "La mairie", "La mairie rend des services aux habitants.",
   "Papa est allé à la mairie pour déclarer la naissance de ma petite sœur. L'agent de l'état civil a écrit son nom dans le registre et lui a remis un acte de naissance. Papa l'a rangé avec soin.",
   [("Pourquoi papa est-il allé à la mairie ?", "pour déclarer la naissance de la petite sœur"), ("Qui a écrit le nom dans le registre ?", "l'agent de l'état civil"), ("Quel document papa a-t-il reçu ?", "un acte de naissance")],
   [("Relève le sujet du verbe « a écrit ».", "L'agent de l'état civil"), ("Mets au présent : « Papa l'a rangé avec soin. »", "Papa le range avec soin."), ("Trouve un mot de la famille de « naissance ».", "naître, natal…")],
   [("Pourquoi faut-il garder l'acte de naissance ?", "RP : il prouve l'identité ; il sert pour l'école, les examens.")],
   [("Cite un autre service rendu par la mairie.", "RP : marchés, mariages, assainissement…")])
_t("CE2", "T1", "La grande inondation",
   "L'eau est indispensable, mais quand elle est trop abondante, elle peut causer de grands dégâts. Le texte suivant te parle d'une pluie qui a tout inondé.",
   "Cette année-là, il avait plu sans arrêt pendant trois jours sur le village de Hêtin. Le fleuve Ouémé était sorti de son lit. L'eau avait envahi les champs et les maisons basses. Les habitants avaient grimpé sur les toits ou s'étaient réfugiés à l'école, construite sur une colline. Les barques allaient et venaient pour secourir les familles.",
   [("Nomme le fleuve sorti de son lit.", "l'Ouémé"), ("Relève où les habitants se sont réfugiés.", "sur les toits / à l'école construite sur une colline"), ("Trouve un autre mot pour remplacer « secourir ».", "aider / sauver")],
   [("Dans « Les barques allaient et venaient », relève les verbes conjugués.", "allaient, venaient"), ("Indique ce que remplace « son » dans « sorti de son lit ».", "le fleuve (l'Ouémé)"), ("Mets au présent : « L'eau avait envahi les champs. »", "L'eau envahit les champs.")],
   [("Les pluies ont-elles fait du bien ou du mal aux habitants ? Justifie.", "du mal : maisons et champs inondés, familles en danger.")],
   [("Imagine ce que les habitants feront quand l'eau baissera.", "RP : nettoyer, reconstruire, ressemer…")],
   infre="2015")
_t("CE2", "T2", "Une baignade imprudente",
   "« Il faut réfléchir avant d'agir », dit-on. Le texte ci-dessous montre ce qui arrive quand on oublie ce conseil.",
   "Un samedi, Tanko, Issa et Rachidi gardent les moutons près du fleuve. Il fait très chaud. Issa propose de se baigner, malgré l'interdiction des parents. Tanko surveille les moutons pendant que les deux autres plongent. Mais le courant est fort. Rachidi est emporté. Tanko crie au secours. Un pêcheur arrive avec sa pirogue et le tire de l'eau, à moitié noyé. Pendant ce temps, les moutons se sont dispersés dans les champs.",
   [("Dis le rôle de Tanko et celui d'Issa dans ce récit.", "Tanko surveille les moutons et appelle au secours ; Issa propose la baignade et plonge."), ("Dis ce qui est arrivé aux moutons.", "Ils se sont dispersés dans les champs.")],
   [("« Le courant est fort. » Mets cette phrase au passé composé.", "Le courant a été fort."), ("Agrandis la phrase « Tanko crie » en ajoutant un complément.", "Tanko crie au secours (de toutes ses forces…)."), ("Justifie l'écriture de « sont » dans « les moutons se sont dispersés ».", "auxiliaire être au présent, 3e personne du pluriel (sujet « les moutons »)")],
   [("Pourquoi les enfants n'auraient-ils pas dû se baigner ? Choisis et justifie : les parents l'avaient interdit / il n'y avait pas d'eau.", "les parents l'avaient interdit ; le courant était dangereux.")],
   [("Imagine ce que diront les parents en apprenant l'accident.", "RP : réaction cohérente (reproches, conseils, soulagement).")],
   infre="2015")
_t("CE2", "T3", "La chèvre de la discorde",
   "Face à un conflit, il faut garder son calme pour ne pas poser d'actes regrettables. Le texte suivant illustre ce conseil.",
   "La chèvre de Mama Kouléra est entrée dans le jardin de Baba Sèhou et a mangé ses jeunes plants de piment. Furieux, Baba Sèhou prend un bâton pour aller frapper la voisine. Son fils lui conseille d'en parler au chef de quartier. Arrivé devant la maison de la voisine, Baba Sèhou la trouve en train de soigner sa propre fille, blessée en jouant. Touché, il pose son bâton. Le lendemain, Mama Kouléra lui offre des plants neufs et ils se réconcilient.",
   [("Dis pourquoi Baba Sèhou est en colère.", "La chèvre de la voisine a mangé ses plants de piment."), ("Nomme celui qui lui a donné un bon conseil.", "son fils"), ("Que fait Mama Kouléra le lendemain ?", "Elle offre des plants neufs.")],
   [("Relève le passage qui dit le conseil du fils.", "Son fils lui conseille d'en parler au chef de quartier."), ("« Il pose son bâton. » Relève le verbe, son temps et sa personne.", "pose — présent de l'indicatif — 3e personne du singulier"), ("Donne la nature de « voisine » et écris-le au masculin.", "nom commun — voisin")],
   [("Baba Sèhou pose son bâton : parce qu'il a peur / parce qu'il est touché par la voisine qui soigne sa fille. Choisis.", "parce qu'il est touché"), ("Que retiens-tu de la réconciliation ?", "RP : il vaut mieux dialoguer et pardonner.")],
   [("Que se serait-il passé si Baba Sèhou avait frappé sa voisine ?", "RP : blessure, plainte, prison, haine entre voisins.")],
   infre="2015")
_t("CE2", "FA", "L'histoire de la pirogue",
   "Pour mieux vivre, l'homme améliore sans cesse ses outils et ses moyens de transport. L'histoire de la pirogue en est un exemple.",
   "Autrefois, les pêcheurs de nos lagunes se déplaçaient sur des troncs d'arbres attachés ensemble. C'était le radeau. Plus tard, ils ont appris à creuser un gros tronc avec la hache et le feu : la pirogue était née. On la faisait avancer avec une perche ou une pagaie. Aujourd'hui, beaucoup de pirogues portent un moteur. Elles vont plus vite et transportent plus de marchandises.",
   [("Donne le nom du tout premier moyen de déplacement sur l'eau.", "le radeau"), ("Comment fabriquait-on la pirogue ?", "en creusant un gros tronc avec la hache et le feu"), ("Avec quoi la faisait-on avancer ?", "avec une perche ou une pagaie")],
   [("« Elles vont plus vite. » Donne la nature du mot « vont ».", "verbe (aller)"), ("Mets au passé composé : « Ils creusent un tronc. »", "Ils ont creusé un tronc."), ("Trouve dans le texte une expression plus simple pour « moyens de déplacement sur l'eau ».", "pirogue / radeau / embarcation")],
   [("Entre la pirogue à pagaie et la pirogue à moteur, laquelle préfères-tu ? Justifie.", "RP : choix justifié (vitesse, coût, bruit, pollution…).")],
   [("Les hommes d'aujourd'hui sont-ils plus intelligents que ceux d'autrefois ? Justifie.", "RP : réponse nuancée et justifiée.")],
   infre="2015")

# ===================================================================================== CM1 (T1–FA : d'après INFRE 2014, reformulées)
_t("CM1", "M1", "Le choléra au quartier", "Les maladies liées à l'eau sale menacent les quartiers mal assainis.",
   "Depuis une semaine, plusieurs habitants du quartier Ahouansori souffrent de diarrhées et de vomissements. Les agents de santé parlent d'une épidémie de choléra. Ils distribuent des comprimés pour purifier l'eau et demandent à chacun de laver les fruits, de couvrir les aliments et d'utiliser les latrines.",
   [("De quelle maladie souffrent les habitants ?", "du choléra"), ("Cite deux signes de la maladie.", "diarrhées, vomissements"), ("Relève deux conseils donnés par les agents de santé.", "laver les fruits / couvrir les aliments / utiliser les latrines / purifier l'eau")],
   [("Décompose en propositions : « Les agents parlent d'une épidémie et ils distribuent des comprimés. »", "deux propositions indépendantes coordonnées par « et »"), ("Trouve le contraire de « propre ».", "sale"), ("Mets au passé simple : « Ils distribuent des comprimés. »", "Ils distribuèrent des comprimés.")],
   [("Que penses-tu des habitants qui ne suivent pas ces conseils ?", "RP : ils mettent leur vie et celle des autres en danger.")],
   [("Dis ce que fait ta famille pour avoir une eau saine.", "RP : bouillir, filtrer, couvrir, javelliser…")])
_t("CM1", "M2", "La lagune malade", "Les déchets menacent nos plans d'eau.",
   "Grand-père Dossou est pêcheur depuis quarante ans sur la lagune de Porto-Novo. Autrefois, ses filets se remplissaient de poissons. Aujourd'hui, ils ramènent surtout des sachets plastiques et des boîtes vides. « La lagune est malade de nos ordures », soupire-t-il.",
   [("Quel est le métier de grand-père Dossou ?", "pêcheur"), ("Que ramènent ses filets aujourd'hui ?", "des sachets plastiques et des boîtes vides"), ("Que veut-il dire par « la lagune est malade » ?", "elle est polluée par les ordures")],
   [("Relève l'adverbe de temps dans : « Autrefois, ses filets se remplissaient de poissons. »", "Autrefois"), ("Donne la nature et la fonction de « pêcheur » dans « Grand-père Dossou est pêcheur ».", "nom commun, attribut du sujet"), ("Mets au futur simple : « La lagune est malade. »", "La lagune sera malade.")],
   [("Qui est responsable de la pollution de la lagune ?", "les habitants qui jettent leurs ordures")],
   [("Propose deux actions pour sauver la lagune.", "RP : ne plus jeter de déchets, collecter, sensibiliser, nettoyer.")])
_t("CM1", "M3", "Le panneau solaire", "L'énergie solaire éclaire de plus en plus de villages.",
   "Au village de Kpébiè, il n'y avait pas d'électricité. Les élèves révisaient à la lampe à pétrole. Grâce à la coopérative, l'école a reçu des panneaux solaires. Désormais, le soir, les salles de classe s'allument et les enfants y apprennent leurs leçons.",
   [("Comment les élèves révisaient-ils avant ?", "à la lampe à pétrole"), ("Qu'a reçu l'école ?", "des panneaux solaires"), ("Que font les enfants le soir maintenant ?", "Ils apprennent leurs leçons dans les classes éclairées.")],
   [("Relève le complément circonstanciel de temps dans la dernière phrase.", "le soir / désormais"), ("Mets à l'imparfait : « Les salles s'allument. »", "Les salles s'allumaient."), ("Trouve un mot de la famille de « soleil ».", "solaire, ensoleillé")],
   [("L'énergie solaire est-elle utile aux élèves ? Justifie.", "Oui : elle permet d'étudier le soir sans danger ni fumée.")],
   [("Imagine un autre usage de l'énergie solaire au village.", "RP : pompe à eau, recharge des téléphones, réfrigérateur du centre de santé…")])
_t("CM1", "M4", "Pas de mariage pour Sika", "La loi protège les enfants contre le mariage précoce.",
   "Sika a treize ans. Un soir, elle surprend une conversation : son oncle veut la donner en mariage à un riche commerçant. Effrayée, elle se confie à sa maîtresse. Celle-ci alerte le chef d'arrondissement et le service des affaires sociales. Le mariage est annulé et Sika reste à l'école.",
   [("Quel âge a Sika ?", "treize ans"), ("Que voulait faire son oncle ?", "la donner en mariage à un commerçant"), ("À qui Sika s'est-elle confiée ?", "à sa maîtresse")],
   [("Donne la nature de « Celle-ci » et dis ce qu'il remplace.", "pronom démonstratif ; il remplace « sa maîtresse »"), ("Mets la phrase « Le mariage est annulé » à la forme active.", "On annule le mariage."), ("Trouve le sens de « se confier ».", "dire un secret à quelqu'un en qui on a confiance")],
   [("Sika a-t-elle bien fait de parler à sa maîtresse ? Justifie.", "Oui : elle s'est protégée, la loi interdit le mariage des enfants.")],
   [("Que dirais-tu à l'oncle de Sika ?", "RP : arguments sur les droits de l'enfant et la loi.")])
_t("CM1", "M5", "La fête des masques", "Les masques font partie de notre patrimoine.",
   "À Kétou, la fête des masques guèlèdè attire chaque année des visiteurs venus de loin. Les danseurs portent des masques sculptés et colorés. Par leurs chants, ils honorent les mères et donnent des conseils à la communauté. L'UNESCO a reconnu cette tradition comme patrimoine de l'humanité.",
   [("Où se déroule la fête des masques guèlèdè ?", "à Kétou"), ("Que font les danseurs par leurs chants ?", "Ils honorent les mères et donnent des conseils."), ("Quelle organisation a reconnu cette tradition ?", "l'UNESCO")],
   [("Relève deux adjectifs qualificatifs qui décrivent les masques.", "sculptés, colorés"), ("Décompose en propositions : « Les danseurs portent des masques qui sont colorés. »", "principale + subordonnée relative « qui sont colorés »"), ("Mets au passé composé : « Les visiteurs viennent de loin. »", "Les visiteurs sont venus de loin.")],
   [("Pourquoi faut-il conserver ces traditions ?", "RP : elles transmettent des valeurs, font connaître notre culture.")],
   [("Présente en deux phrases une fête de ta localité.", "RP : nom, période, déroulement.")])
_t("CM1", "M6", "Le conseil des élèves", "À l'école aussi, on apprend la démocratie.",
   "Pour améliorer la vie de l'école, les élèves de l'EPP Agbokou ont élu un conseil. Chaque classe a présenté deux candidats. Le jour du vote, chacun a déposé son bulletin dans l'urne, en secret. Le dépouillement s'est fait devant tout le monde et les élus ont promis de servir leurs camarades.",
   [("Pourquoi les élèves ont-ils élu un conseil ?", "pour améliorer la vie de l'école"), ("Combien de candidats chaque classe a-t-elle présentés ?", "deux"), ("Comment s'est fait le vote ?", "chacun a déposé son bulletin dans l'urne, en secret")],
   [("Trouve le sens de « dépouillement ».", "le comptage des bulletins de vote"), ("Relève le COD de : « Chacun a déposé son bulletin dans l'urne. »", "son bulletin"), ("Mets au futur simple : « Les élus servent leurs camarades. »", "Les élus serviront leurs camarades.")],
   [("Pourquoi le vote doit-il être secret ?", "pour que chacun choisisse librement")],
   [("Si tu étais élu, que ferais-tu pour ton école ?", "RP : deux propositions concrètes.")])
_t("CM1", "T1", "Le carnet de vaccination de Bilal",
   "Beaucoup de maladies graves peuvent être évitées. Pour cela, il faut connaître les moyens de prévention. Le texte suivant t'aidera à mieux te protéger.",
   "Le petit Bilal tousse depuis plusieurs jours. Il a de la fièvre et respire mal. Sa grande sœur Nafissa veut l'emmener au centre de santé. Mais leur grand-mère affirme : « Ce n'est rien ; une tisane de feuilles suffira. » Nafissa insiste : « Au centre, ils vérifieront son carnet de vaccination. À l'école, on nous a appris que la rougeole et la coqueluche peuvent tuer les enfants non vaccinés. » Finalement, la grand-mère accepte. L'infirmière soigne Bilal et lui donne le vaccin qui lui manquait.",
   [("De quoi souffre Bilal ?", "Il tousse, a de la fièvre et respire mal."), ("Quel remède propose la grand-mère ?", "une tisane de feuilles"), ("Relève deux maladies citées par Nafissa.", "la rougeole, la coqueluche")],
   [("Décompose en propositions : « Il a de la fièvre et respire mal. » et donne leur nature.", "deux propositions indépendantes coordonnées par « et »"), ("Trouve le contraire de « grave ».", "bénin / léger"), ("Mets au passé simple puis au passé composé : « L'infirmière soigne Bilal. »", "L'infirmière soigna Bilal. / L'infirmière a soigné Bilal.")],
   [("Que penses-tu du comportement de la grand-mère au début ?", "RP : il est dangereux ; elle néglige la santé de l'enfant."), ("Nafissa avait-elle raison de s'inquiéter ? Dis pourquoi.", "Oui : la maladie peut être grave ; il faut consulter et vacciner.")],
   [("As-tu déjà été vacciné ? Dis ce que tu as ressenti.", "RP : récit court et cohérent.")],
   infre="2014")
_t("CM1", "T2", "La pintade, le canard et le chacal",
   "Dans la vie, il faut être vigilant et se méfier de ceux qui cachent leurs mauvaises intentions. Le conte suivant te met en garde.",
   "La pintade et le canard sont deux amis inséparables. Un matin, ils vont ensemble ramasser des graines au bord du marigot. Le chacal, caché derrière les herbes, les observe. « Mes amis, dit-il d'une voix douce, venez chercher des graines près de mon terrier, il y en a beaucoup. » Le canard se prépare à le suivre. Mais la pintade remarque que le chacal se lèche les babines. Elle dit : « Va devant, nous te rejoignons. » Dès que le chacal s'éloigne, elle entraîne son ami sur l'eau, où le chacal ne peut les atteindre. Depuis ce jour, le chacal guette les volailles autour des cases.",
   [("Nomme les personnages du texte.", "la pintade, le canard, le chacal"), ("Que vont faire les deux amis au bord du marigot ?", "ramasser des graines"), ("Lequel des deux amis a compris le piège ?", "la pintade")],
   [("Explique : « le chacal se lèche les babines ».", "il a envie de manger, il pense à les dévorer"), ("Dans « deux amis inséparables », relève l'adjectif qualificatif et analyse-le.", "inséparables : adjectif qualificatif, épithète de « amis »"), ("Mets au plus-que-parfait : « La pintade entraîne son ami sur l'eau. »", "La pintade avait entraîné son ami sur l'eau.")],
   [("Que penses-tu du comportement de la pintade ?", "RP : elle est prudente et intelligente, elle sauve son ami."), ("Comment la pintade a-t-elle compris l'intention du chacal ?", "elle l'a vu se lécher les babines"), ("Aurais-tu suivi le chacal ? Justifie.", "RP : refus justifié par la prudence.")],
   [("Imagine la réaction du chacal quand il comprend qu'il a été trompé.", "RP : réaction cohérente (colère, ruse, menace…).")],
   infre="2014")
_t("CM1", "T3", "Semer aujourd'hui pour récolter demain",
   "Pour réussir demain, il faut aimer l'effort au lieu de chercher toujours la facilité. Le texte qui suit t'en parle.",
   "Le vieux Akowé répétait souvent à ses petits-enfants : « L'avenir ne tombe pas du ciel ; on le construit chaque jour. » Il leur rappelait que le champ ne donne rien à celui qui dort pendant la saison des semailles. « Seul celui qui a peiné sous le soleil savoure le repos du soir. Plantez un palmier dans votre jeunesse : il vous nourrira dans votre vieillesse, et vous n'aurez pas à quémander l'huile du voisin. »",
   [("Relève deux conseils du vieux Akowé pour préparer l'avenir.", "construire l'avenir chaque jour / travailler pendant les semailles / planter un palmier dans sa jeunesse"), ("Pourquoi faut-il planter un palmier dans sa jeunesse ?", "pour qu'il nous nourrisse dans la vieillesse"), ("Qui peut savourer le repos du soir ?", "celui qui a peiné sous le soleil")],
   [("Associe chaque mot à son sens : savourer — quémander — peiner (demander avec insistance ; goûter avec plaisir ; faire de gros efforts).", "savourer : goûter avec plaisir ; quémander : demander avec insistance ; peiner : faire de gros efforts"), ("Comment est formé le mot « jeunesse » ? Trouve un mot formé de la même façon.", "jeune + suffixe -esse ; vieillesse, sagesse…"), ("Dans « On construit l'avenir », relève le verbe, donne son infinitif et son groupe ; mets la phrase au plus-que-parfait.", "construit — construire — 3e groupe ; On avait construit l'avenir.")],
   [("Que penses-tu du conseil « Plantez un palmier dans votre jeunesse » ?", "RP : il invite à prévoir et à travailler tôt."), ("Que faut-il faire pour qu'un arbre planté grandisse ?", "l'arroser, le protéger des animaux, le désherber")],
   [("Dis en deux phrases comment tu prépares ton avenir.", "RP : deux phrases cohérentes (travailler à l'école, apprendre un métier…).")],
   infre="2014")
_t("CM1", "FA", "Le serpent dans le grenier",
   "Les jours de repos, certains enfants s'éloignent des parents et s'exposent à des dangers. Le récit suivant raconte un jeu dangereux dont tu dois tirer leçon.",
   "Kodjo adorait grimper partout. Ce jour-là, pendant que ses parents étaient au champ, il décida de fouiller le grenier pour y chercher des arachides. Il appuya une vieille échelle contre le mur et monta. Dans la pénombre, il plongea la main dans un panier. Aussitôt, quelque chose de froid glissa sur son bras : une vipère ! Terrifié, Kodjo lâcha tout et sauta. Il atterrit sur un tas de paille qui amortit sa chute. Le serpent, lui, disparut entre les tiges de mil.",
   [("Dis ce que Kodjo est allé chercher dans le grenier.", "des arachides"), ("Nomme l'animal qu'il a rencontré.", "une vipère"), ("Relève le passage qui montre que Kodjo a eu très peur.", "Terrifié, Kodjo lâcha tout et sauta.")],
   [("Donne le sens de « dans la pénombre ».", "dans une faible lumière, presque dans le noir"), ("Dans « Kodjo décida de fouiller le grenier », relève le verbe conjugué, son infinitif et son temps.", "décida — décider — passé simple"), ("Analyse la phrase : « Il appuya l'échelle contre le mur et monta. »", "deux propositions indépendantes coordonnées par « et »")],
   [("Kodjo a été imprudent. Vrai ou faux ?", "Vrai"), ("Était-il raisonnable de monter seul au grenier ? Justifie.", "Non : il pouvait tomber ou être mordu ; il aurait dû attendre les parents.")],
   [("Imagine ce qui aurait pu arriver de plus grave à Kodjo.", "RP : morsure, fracture… et conséquences.")],
   infre="2014")

# ===================================================================================== CM2 (T1–FA : d'après INFRE 2014, reformulées ; C1–C3 : CEP blanc)
_t("CM2", "M1", "Hépatite : le dépistage", "Certaines maladies se soignent mieux si elles sont dépistées tôt.",
   "Lors d'une campagne de dépistage gratuite organisée à la mairie, Mathieu, vingt ans, apprend qu'il est porteur du virus de l'hépatite B. Le médecin le rassure : grâce au suivi et au traitement, il peut mener une vie normale. Il lui conseille aussi de faire vacciner ses frères et sœurs.",
   [("Où s'est déroulée la campagne de dépistage ?", "à la mairie"), ("Quelle maladie a-t-on découverte chez Mathieu ?", "l'hépatite B"), ("Quel conseil le médecin lui donne-t-il pour sa famille ?", "faire vacciner ses frères et sœurs")],
   [("Décompose en propositions : « Le médecin le rassure parce qu'il peut être soigné. »", "principale + subordonnée conjonctive de cause"), ("Donne la nature et la fonction de « gratuite ».", "adjectif qualificatif, épithète de « campagne »"), ("Mets au passé simple : « Mathieu apprend la nouvelle. »", "Mathieu apprit la nouvelle.")],
   [("Que penses-tu de l'intérêt du dépistage ?", "RP : il permet de se soigner tôt et de protéger les autres.")],
   [("Que feras-tu pour te protéger des maladies évitables ?", "RP : vaccination, hygiène, dépistage.")])
_t("CM2", "M2", "La forêt de Lama", "Les forêts protégées sont un trésor pour le pays.",
   "La forêt classée de la Lama abrite des singes à ventre rouge que l'on ne trouve presque nulle part ailleurs. Autrefois menacée par les coupes et les feux, elle est aujourd'hui surveillée par des agents forestiers. Les villageois des environs participent à sa protection et vivent de l'écotourisme.",
   [("Quel animal rare vit dans la forêt de la Lama ?", "le singe à ventre rouge"), ("Qu'est-ce qui menaçait la forêt autrefois ?", "les coupes et les feux"), ("Comment vivent aujourd'hui les villageois des environs ?", "de l'écotourisme")],
   [("Trouve le sens de « forêt classée ».", "forêt protégée par la loi"), ("Relève une proposition subordonnée relative et son antécédent.", "« que l'on ne trouve presque nulle part ailleurs » — antécédent : singes"), ("Mets au futur antérieur : « Les agents surveillent la forêt. »", "Les agents auront surveillé la forêt.")],
   [("La participation des villageois est-elle importante ? Justifie.", "Oui : ils protègent la forêt et en tirent des revenus.")],
   [("Propose deux règles pour protéger une forêt.", "RP : interdire les feux, reboiser, ne pas chasser…")])
_t("CM2", "M3", "Le guichet numérique", "Le numérique change la vie des citoyens.",
   "Pour obtenir l'acte de naissance de sa fille, Mme Houngbo n'a pas fait la queue à la mairie. Elle a rempli sa demande sur un service en ligne, depuis le cybercafé du quartier. Quelques jours plus tard, elle a reçu un message l'invitant à retirer le document. « Que de temps gagné ! », s'exclame-t-elle.",
   [("Quel document Mme Houngbo voulait-elle obtenir ?", "l'acte de naissance de sa fille"), ("D'où a-t-elle fait sa demande ?", "depuis le cybercafé, sur un service en ligne"), ("Quel avantage a-t-elle trouvé ?", "elle a gagné du temps")],
   [("De quel type est la phrase « Que de temps gagné ! » ?", "phrase exclamative"), ("Relève les verbes conjugués de la deuxième phrase et donne leur infinitif.", "a rempli — remplir"), ("Mets au plus-que-parfait : « Elle reçoit un message. »", "Elle avait reçu un message.")],
   [("Le service en ligne est-il accessible à tous ? Justifie.", "RP : pas encore à tous (internet, savoir lire…) ; réponse justifiée.")],
   [("Imagine un autre service que l'on pourrait faire en ligne.", "RP : inscription scolaire, paiement, rendez-vous…")])
_t("CM2", "M4", "Les droits de Bénédicte", "La loi protège les enfants qui travaillent dans des conditions difficiles.",
   "Bénédicte, douze ans, a été placée chez une commerçante de Cotonou. Elle se lève avant l'aube pour vendre de l'eau glacée et ne va pas à l'école. Une ONG de protection de l'enfance, alertée par des voisins, a saisi la brigade de protection des mineurs. Bénédicte a été rendue à ses parents et inscrite à l'école.",
   [("Où Bénédicte avait-elle été placée ?", "chez une commerçante de Cotonou"), ("Que faisait-elle chaque jour ?", "Elle vendait de l'eau glacée avant l'aube."), ("Qui a alerté l'ONG ?", "des voisins")],
   [("Donne le sens de « saisir la brigade ».", "porter l'affaire devant la brigade, lui demander d'agir"), ("Mets à la voix active : « Bénédicte a été rendue à ses parents. »", "On a rendu Bénédicte à ses parents."), ("Relève un complément circonstanciel de temps.", "avant l'aube")],
   [("Les voisins ont-ils eu raison d'alerter ? Justifie.", "Oui : les droits de l'enfant étaient violés.")],
   [("Que dirais-tu aux parents qui placent leurs enfants ?", "RP : arguments sur l'école et les dangers.")])
_t("CM2", "M5", "Ouidah, la mémoire", "Certains lieux nous rappellent des drames de l'histoire.",
   "Chaque année, des visiteurs du monde entier parcourent la Route des esclaves à Ouidah. Ils marchent depuis la place des enchères jusqu'à la Porte du Non-Retour, au bord de l'océan. Les guides rappellent que des milliers d'Africains furent embarqués de force vers les Amériques.",
   [("Dans quelle ville se trouve la Route des esclaves ?", "à Ouidah"), ("Où se termine la Route ?", "à la Porte du Non-Retour, au bord de l'océan"), ("Vers quel continent les captifs étaient-ils emmenés ?", "les Amériques")],
   [("Relève le verbe au passé simple et donne son infinitif.", "furent (embarqués) — être"), ("Analyse : « Les guides rappellent que des milliers d'Africains furent embarqués. »", "principale + subordonnée conjonctive complément d'objet"), ("Mets au passé composé : « Ils parcourent la Route. »", "Ils ont parcouru la Route.")],
   [("Pourquoi faut-il garder la mémoire de la traite ?", "RP : pour ne pas oublier, pour que cela ne recommence pas.")],
   [("Rédige un message à écrire sur la Porte du Non-Retour.", "RP : message court et respectueux.")])
_t("CM2", "M6", "Le Sénat", "Nos institutions évoluent avec la Constitution.",
   "Depuis le 30 juillet 2026, le Bénin compte une seconde chambre du Parlement : le Sénat. Ses vingt-cinq membres veillent à l'unité nationale et donnent leur avis avant la promulgation de certaines lois. L'Assemblée nationale, elle, continue de voter les lois et le budget de l'État.",
   [("Depuis quand le Bénin a-t-il un Sénat ?", "depuis le 30 juillet 2026"), ("Combien de membres compte le Sénat ?", "vingt-cinq"), ("Quel est le rôle de l'Assemblée nationale cité dans le texte ?", "voter les lois et le budget de l'État")],
   [("Écris en chiffres : vingt-cinq.", "25"), ("Relève le sujet du verbe « veillent ».", "Ses vingt-cinq membres"), ("Mets à l'imparfait : « L'Assemblée vote les lois. »", "L'Assemblée votait les lois.")],
   [("Pourquoi un pays a-t-il besoin d'institutions ?", "RP : pour organiser la vie commune, faire et appliquer les lois.")],
   [("Si tu étais député, quelle loi proposerais-tu pour les enfants ?", "RP : proposition justifiée.")])
_t("CM2", "T1", "L'imprudence de Romaric",
   "Par ignorance ou par imprudence, l'homme pose parfois des actes qui mettent sa vie en danger. Le texte suivant t'invite à en tirer des leçons.",
   "Après son apprentissage de mécanicien, Romaric avait ouvert un atelier au bord de la route. Travailleur et souriant, il avait beaucoup de clients. Le soir, il buvait avec ses amis et rentrait à moto sans casque. Sa mère le suppliait d'être prudent ; il répondait en riant : « Les accidents, c'est pour les autres ! » Une nuit, ivre, il heurta une charrette sans éclairage. Il passa deux mois à l'hôpital. Ses amis et sa famille l'entourèrent et l'aidèrent à payer les soins. Aujourd'hui, Romaric ne monte plus jamais sans casque et ne boit plus avant de conduire.",
   [("Indique les personnages de ce texte.", "Romaric, sa mère, ses amis, sa famille"), ("Propose un titre à ce texte.", "RP : titre en rapport avec l'imprudence / l'accident."), ("Relève ce que Romaric disait des accidents.", "« Les accidents, c'est pour les autres ! »")],
   [("Donne le sens de « apprentissage ».", "formation à un métier auprès d'un patron"), ("De quel type est la phrase « Sa mère le suppliait d'être prudent » ? Décompose-la en propositions.", "phrase simple déclarative (une seule proposition)"), ("Relève les verbes conjugués de « Ses amis l'entourèrent et l'aidèrent » et donne leur infinitif.", "entourèrent — entourer ; aidèrent — aider")],
   [("Que penses-tu du comportement de Romaric avant l'accident ?", "RP : il était imprudent et irresponsable."), ("Romaric regrette-t-il son comportement ? Justifie.", "Oui : il ne monte plus sans casque et ne boit plus avant de conduire.")],
   [("Dis ce que tu feras pour éviter les accidents de la route.", "RP : casque, respect du code, prudence.")],
   infre="2014")
_t("CM2", "T2", "L'eau, l'air et le sol",
   "L'environnement est notre cadre de vie, mais il peut nous rendre malades s'il n'est pas bien entretenu. Le texte ci-dessous t'invite à mieux le gérer.",
   "Sans le sol, l'eau et l'air, aucune vie ne serait possible. Le sol nourrit les plantes qui, à leur tour, nourrissent les animaux et les hommes. Mais là où les arbres ont été abattus, la pluie emporte la bonne terre : le sol devient pauvre. L'eau, indispensable, peut aussi transmettre des maladies graves comme le choléra quand elle est souillée. Quant à l'air des grandes villes, il est chargé de la fumée des véhicules et des déchets que l'on brûle.",
   [("Relève les trois éléments indispensables à la vie cités dans le texte.", "le sol, l'eau, l'air"), ("Cite deux effets néfastes de la destruction de l'environnement.", "sol pauvre, maladies (choléra), air pollué"), ("Cite une maladie causée par l'eau souillée.", "le choléra")],
   [("Trouve le contraire de : pauvre, souillée, indispensable.", "riche, propre, inutile"), ("Donne la nature et la fonction de « plantes » dans « Le sol nourrit les plantes ».", "nom commun, complément d'objet direct de « nourrit »"), ("Mets au passé simple et au passé composé : « La pluie emporte la bonne terre. »", "La pluie emporta la bonne terre. / La pluie a emporté la bonne terre.")],
   [("Lequel des trois éléments te paraît le plus important ? Justifie.", "RP : choix justifié."), ("Selon toi, pourquoi la bonne terre disparaît-elle ?", "à cause de l'abattage des arbres et de l'érosion")],
   [("Dis la leçon que tu tires de ce texte.", "RP : il faut protéger l'environnement.")],
   infre="2014")
_t("CM2", "T3", "L'éléphant de la Pendjari",
   "L'amour d'une mère pour son enfant est plus fort que la peur. Lis le texte pour comprendre ce qui est arrivé à une mère courageuse.",
   "Près du parc de la Pendjari, à Tanguiéta, un éléphant égaré entra un matin dans les champs. Les paysans, terrorisés, s'enfuirent en criant. Dans la panique, une femme laissa tomber son petit garçon qui se mit à pleurer au milieu du sentier. L'éléphant s'avança vers lui. La mère revint aussitôt, se plaça entre l'animal et l'enfant et agita son pagne en chantant doucement. L'éléphant s'arrêta, la regarda longuement puis repartit vers la brousse sans toucher à l'enfant.",
   [("Dis où se passe cette histoire.", "près du parc de la Pendjari, à Tanguiéta"), ("Cite les personnages du texte.", "l'éléphant, les paysans, la femme, son petit garçon"), ("Relève le passage qui prouve que l'éléphant n'a pas fait de mal à l'enfant.", "il repartit vers la brousse sans toucher à l'enfant")],
   [("Relie chaque mot à son sens : terrorisé — égaré — panique (perdu ; affolé de peur ; peur collective).", "terrorisé : affolé de peur ; égaré : perdu ; panique : peur collective"), ("Décompose en propositions : « Une femme laissa tomber son garçon qui se mit à pleurer. »", "principale + subordonnée relative « qui se mit à pleurer »"), ("Réécris à l'imparfait : « L'éléphant s'arrêta et la regarda. »", "L'éléphant s'arrêtait et la regardait.")],
   [("Pourquoi la femme est-elle revenue sur ses pas ?", "pour sauver son enfant"), ("Comment a-t-elle sauvé son enfant ?", "Elle s'est placée devant l'éléphant, a agité son pagne en chantant.")],
   [("Dis en quelques lignes ce que tu penses du comportement de l'éléphant.", "RP : avis argumenté.")],
   infre="2014")
_t("CM2", "FA", "Le jugement du crocodile",
   "« La raison du plus fort est toujours la meilleure », dit-on. Les plus faibles subissent souvent l'injustice. Voici une histoire qui t'aidera à réfléchir à ce qu'il faut faire.",
   "Une étrange maladie frappait depuis des semaines les animaux du marigot. Le crocodile, roi des eaux, réunit ses sujets : « Ce mal menace notre peuple et mon trône. Que l'on trouve le coupable ! » La tortue, patiente et sage, mena l'enquête de rive en rive. Elle découvrit que le fils du roi avait jeté des cadavres de poissons dans la source où tous buvaient. Lors de l'assemblée, elle révéla la vérité. Furieux d'être contredit, le crocodile accusa la tortue de mensonge et la fit enfermer sous une grosse pierre.",
   [("Dis où se passe cette histoire.", "au marigot"), ("Indique le héros du texte.", "la tortue"), ("Relève deux mots qui montrent les relations entre le roi et les animaux.", "roi, sujets (peuple, trône)")],
   [("Trouve le sens de : enquête, contredit.", "enquête : recherche de la vérité ; contredit : quand on dit le contraire de ce qu'il pense"), ("Fais l'analyse logique de : « Elle découvrit que le fils du roi avait jeté des cadavres. »", "principale + subordonnée conjonctive complément d'objet direct"), ("Mets aux autres temps simples de l'indicatif : « La tortue mène l'enquête. »", "menait (imparfait), mena (passé simple), mènera (futur simple)")],
   [("Selon toi, quelle faute a commise le fils du roi ?", "Il a pollué la source commune."), ("Le roi a-t-il eu raison d'enfermer la tortue ? Justifie.", "Non : elle a dit la vérité ; c'est une injustice."), ("Comment trouves-tu la tortue ?", "RP : courageuse, honnête, sage.")],
   [("Si tu étais le fils du roi, que ferais-tu ?", "RP : reconnaître sa faute, faire libérer la tortue…")],
   infre="2014")
_t("CM2", "C1", "Le forage du village", "Avoir de l'eau potable change la vie d'un village.",
   "Pendant longtemps, les femmes de Gbéroubouè marchaient six kilomètres pour puiser l'eau du marigot. Les enfants souffraient de vers et de diarrhées. L'an dernier, la commune a fait construire un forage équipé d'une pompe solaire. Un comité de gestion, élu par les habitants, collecte une petite somme pour l'entretien. Depuis, les filles arrivent à l'heure à l'école et le centre de santé reçoit moins de malades.",
   [("Quelle distance les femmes parcouraient-elles pour chercher l'eau ?", "six kilomètres"), ("Qu'a fait construire la commune ?", "un forage équipé d'une pompe solaire"), ("Cite deux changements depuis la construction du forage.", "les filles arrivent à l'heure à l'école ; moins de malades au centre de santé")],
   [("Donne la nature et la fonction de « élu » dans « Un comité de gestion, élu par les habitants ».", "participe passé employé comme adjectif, épithète détachée de « comité »"), ("Fais l'analyse logique de la dernière phrase.", "deux propositions indépendantes coordonnées par « et »"), ("Mets la troisième phrase au plus-que-parfait.", "La commune avait fait construire un forage.")],
   [("Pourquoi faut-il un comité de gestion ?", "pour entretenir le forage et le faire durer")],
   [("Propose deux règles d'utilisation du forage.", "RP : propreté, horaires, paiement, pas de gaspillage.")])
_t("CM2", "C2", "La caravane de sensibilisation", "Les élèves peuvent agir pour leur communauté.",
   "Pour la journée mondiale de l'environnement, les élèves du CM2 de l'EPP Sèmè ont organisé une caravane. Munis de pancartes, ils ont parcouru le marché en chantant contre les sachets plastiques. Ils ont distribué des paniers tressés offerts par les artisanes du quartier. Le maire, venu les féliciter, a promis d'installer des poubelles à chaque entrée du marché.",
   [("Pour quelle occasion la caravane a-t-elle été organisée ?", "la journée mondiale de l'environnement"), ("Qu'ont distribué les élèves ?", "des paniers tressés"), ("Qu'a promis le maire ?", "installer des poubelles à chaque entrée du marché")],
   [("Relève le complément circonstanciel de moyen dans : « Munis de pancartes, ils ont parcouru le marché. »", "munis de pancartes"), ("Écris au passé simple : « Ils ont distribué des paniers. »", "Ils distribuèrent des paniers."), ("Donne un mot de la même famille que « environnement ».", "environner, environnemental")],
   [("Les paniers tressés sont-ils une bonne solution ? Justifie.", "Oui : ils remplacent les sachets, se réutilisent et font travailler les artisanes.")],
   [("Rédige le slogan que tu aurais écrit sur ta pancarte.", "RP : slogan court et pertinent.")])
_t("CM2", "C3", "Le rêve de Rachida", "Avec du courage, on peut réaliser ses rêves.",
   "Rachida est née dans un petit village de l'Atacora. Sa mère vendait du karité et son père cultivait le sorgho. Chaque soir, à la lueur d'une lampe, elle révisait ses leçons après les travaux ménagers. Admise au CEP avec mention, elle obtint une bourse pour le collège. Vingt ans plus tard, elle revint au village comme médecin et ouvrit le premier cabinet de consultation de la commune.",
   [("Dans quel département Rachida est-elle née ?", "l'Atacora"), ("Comment révisait-elle ses leçons ?", "le soir, à la lueur d'une lampe, après les travaux ménagers"), ("Quel métier exerce-t-elle vingt ans plus tard ?", "médecin")],
   [("Fais l'analyse logique de : « Sa mère vendait du karité et son père cultivait le sorgho. »", "deux propositions indépendantes coordonnées"), ("Relève un participe passé employé seul et accorde-le.", "admise (féminin singulier, se rapporte à Rachida)"), ("Mets au futur simple : « Elle ouvrit un cabinet. »", "Elle ouvrira un cabinet.")],
   [("Quelles qualités Rachida a-t-elle montrées ?", "RP : courage, persévérance, sens du travail.")],
   [("Dis ce que tu veux devenir et comment tu y arriveras.", "RP : projet cohérent.")])

# ===================================================================================== Dictées du CEP blanc (CM2)
DICTEES = {
    "C1": ("Le marché de Dantokpa", "Le marché de Dantokpa s'étend au bord de la lagune de Cotonou. Dès l'aube, les camions déchargent des sacs de maïs, "
           "des régimes de bananes et des caisses de tomates. Les vendeuses installent leurs étalages sous des parasols multicolores. On y entend toutes "
           "les langues du pays. Malgré la foule et le bruit, chacun trouve ce qu'il cherche : un pagne, une marmite ou un remède."),
    "C2": ("La saison des pluies", "Les premières pluies sont arrivées. Les paysans, qui attendaient ce moment depuis des semaines, ont repris le chemin des "
           "champs. Ils labourent la terre encore humide et sèment le maïs et l'arachide. Les enfants, pieds nus, courent dans les flaques. Le soir, "
           "les grenouilles chantent près du marigot et l'air sent la terre mouillée."),
    "C3": ("Une journée de solidarité", "Samedi dernier, les habitants du quartier se sont réunis pour curer les caniveaux bouchés par les ordures. Munis de pelles "
           "et de brouettes, les jeunes ont travaillé toute la matinée. Les femmes ont préparé un repas pour tous. À midi, le chef de quartier a remercié "
           "chacun et a rappelé que la propreté est l'affaire de tous."),
}
