# -*- coding: utf-8 -*-
"""Lycée agricole (enseignement technique agricole) : disciplines, épreuves APC, interrogations, devoirs, TP, fiches, thèmes d'exposés,
fiches de révision. Rédaction originale, contextualisée au Bénin ; les valeurs chiffrées (rendements, doses, prix) sont des ordres de grandeur
d'exercice : le professeur les adapte au programme de sa classe et aux pratiques de sa région. Aucun diplôme n'est affirmé ici."""
from epreuves_apc import E

MATIERES_AGRI = [
    ("AGRI_PV", "Productions végétales"), ("AGRI_PA", "Productions animales"), ("AGRI_SOL", "Pédologie et agronomie"),
    ("AGRI_PROT", "Protection des cultures et santé animale"), ("AGRI_MACH", "Machinisme et génie rural"),
    ("AGRI_TRANS", "Transformation et conservation des produits agricoles"),
    ("AGRI_ECO", "Économie rurale et gestion d'exploitation"), ("AGRI_TP", "Travaux pratiques agricoles")]
PV, PA, SOL, PROT, MACH, TRANS, ECO, TP = (m[1] for m in MATIERES_AGRI)
NIVEAUX = ["2nde", "1ère", "Tle"]

# ============================================================ ÉPREUVES APC (2 h, 18 points + 2 de perfectionnement)
EP = []
EP.append(E(SOL, "2nde", "2 h", "Traiter une situation relevant de la connaissance et de l'amélioration d'un sol cultivé.",
 "Le lycée agricole reçoit un champ-école jugé « fatigué » : les rendements de maïs baissent depuis trois campagnes. Les élèves prélèvent un échantillon de sol, le mélangent à de l'eau dans un bocal et laissent reposer 24 heures.",
 "Observation du bocal : au fond, une couche de sable grossier (6 cm) ; au-dessus, une couche de limon (3 cm) ; en surface, une fine couche d'argile (1 cm). Le pH mesuré est de 5,2. La couche de surface est claire et pauvre en débris végétaux.",
 "Tu es invité(e) à aider les élèves à poser un diagnostic et à proposer des solutions.",
 [("Définis le mot « sol » et cite ses quatre constituants.", 3, "Couche superficielle de la terre où poussent les plantes ; constituants : minéraux (sable, limon, argile), matière organique, eau, air."),
  ("Calcule le pourcentage de sable, de limon et d'argile de l'échantillon et indique la texture dominante.", 4, "Épaisseur totale 10 cm : sable 60 %, limon 30 %, argile 10 % ; sol sableux (léger)."),
  ("Indique deux avantages et deux inconvénients d'un sol sableux pour la culture.", 3, "Avantages : facile à travailler, bien aéré, bon drainage. Inconvénients : retient mal l'eau et les éléments nutritifs, se lessive vite."),
  ("Interprète la valeur du pH et dis ce qu'elle implique pour la culture du maïs.", 3, "pH 5,2 : sol acide, la disponibilité de certains éléments baisse ; apport de matière organique ou amendement calcique possible."),
  ("Propose trois pratiques pour restaurer la fertilité de ce sol et justifie-les.", 5, "Apport de fumier ou de compost (matière organique) ; rotation avec une légumineuse (niébé, arachide) qui fixe l'azote ; paillage et couverture du sol contre l'érosion ; fumure minérale raisonnée.")]))
EP.append(E(PV, "2nde", "2 h", "Traiter une situation relevant de la conduite d'une culture de maïs.",
 "Le chef de culture du lycée agricole veut semer 1 ha de maïs en début de grande saison des pluies. Il dispose de semences certifiées, d'engrais NPK et d'urée.",
 "Écartements retenus : 80 cm entre les lignes et 40 cm entre les poquets, 2 grains par poquet. Le taux de germination annoncé est de 90 %. Un hectare mesure 10 000 m².",
 "Tu es invité(e) à aider le chef de culture à planifier le semis et la fertilisation.",
 [("Calcule le nombre de poquets et le nombre de plants à l'hectare.", 4, "Surface par poquet 0,8 x 0,4 = 0,32 m² ; 10 000 : 0,32 = 31 250 poquets ; 2 plants par poquet = 62 500 plants."),
  ("Cite quatre opérations culturales du maïs, dans l'ordre, du labour à la récolte.", 4, "Préparation du sol (défrichage, labour), semis, démariage et sarclage, fertilisation (NPK puis urée), buttage, récolte, séchage."),
  ("Explique pourquoi on apporte le NPK au début et l'urée plus tard.", 3, "NPK (azote, phosphore, potassium) nourrit le jeune plant et l'enracinement ; l'urée (azote) répond au besoin de la phase de croissance rapide."),
  ("Indique deux critères de maturité du maïs et une condition de conservation de la récolte.", 3, "Spathes sèches, grains durs ; grains séchés à environ 13 % d'humidité, stockés à l'abri de l'humidité et des insectes."),
  ("Propose deux associations ou rotations utiles avec le maïs et dis pourquoi.", 4, "Maïs/niébé ou maïs-arachide : légumineuses qui enrichissent le sol en azote, couverture du sol, diversification des revenus.")]))
EP.append(E(PV, "1ère", "2 h", "Traiter une situation relevant de la production de manioc et de sa transformation en gari.",
 "Une coopérative d'élèves de la ferme-école cultive 0,5 ha de manioc. Elle veut estimer sa production et décider de la quantité à transformer en gari pour la vente.",
 "Rendement attendu : 15 tonnes de racines fraîches par hectare. Du manioc frais au gari, on retient environ 20 % de gari. Le gari se vend 450 F le kg.",
 "Tu es invité(e) à aider la coopérative à estimer sa production et son chiffre d'affaires.",
 [("Calcule la production attendue de racines fraîches sur 0,5 ha.", 3, "15 t x 0,5 = 7,5 t soit 7 500 kg."),
  ("Calcule la quantité de gari obtenue et le chiffre d'affaires de sa vente.", 4, "7 500 x 0,20 = 1 500 kg ; 1 500 x 450 = 675 000 F."),
  ("Cite dans l'ordre les étapes de la transformation du manioc en gari.", 4, "Épluchage, lavage, râpage, mise en sac et pressage-fermentation (2 à 3 jours), émiettage et tamisage, cuisson-séchage (torréfaction), tamisage final et emballage."),
  ("Justifie la nécessité de presser et de fermenter la pâte de manioc.", 4, "Éliminer l'eau et les composés cyanés (toxiques) du manioc amer, donner le goût et la texture du gari."),
  ("Propose trois règles d'hygiène pour obtenir un gari de qualité.", 3, "Matériel propre, personnel lavé les mains et bien habillé, séchage et stockage dans un emballage propre à l'abri de l'humidité.")]))
EP.append(E(PA, "2nde", "2 h", "Traiter une situation relevant de la conduite d'un élevage de poulets de chair.",
 "L'atelier d'aviculture du lycée agricole met en place une bande de 200 poussins de chair. À la fin de la bande, les élèves veulent calculer les performances techniques et économiques.",
 "Résultats : 190 poulets survivants ; poids moyen final 2 kg ; poids moyen initial du poussin 0,04 kg ; aliment consommé 700 kg ; prix de vente 2 800 F le poulet ; aliment 450 F le kg ; achat des poussins 500 F pièce.",
 "Tu es invité(e) à analyser les résultats de cette bande.",
 [("Calcule le taux de mortalité de la bande.", 3, "10 morts sur 200 : 10 / 200 = 5 %."),
  ("Calcule le gain de poids total de la bande.", 4, "Poids final 190 x 2 = 380 kg ; poids initial 200 x 0,04 = 8 kg ; gain 372 kg."),
  ("Calcule l'indice de consommation (aliment consommé divisé par gain de poids) et interprète-le.", 4, "700 / 372 = 1,88 ; il faut environ 1,9 kg d'aliment pour produire 1 kg de poids vif : plus l'indice est faible, meilleure est la performance."),
  ("Calcule la recette, le coût de l'aliment et du poussin, puis le bénéfice approximatif.", 4, "Recette 190 x 2 800 = 532 000 F ; aliment 700 x 450 = 315 000 F ; poussins 200 x 500 = 100 000 F ; marge 117 000 F avant autres charges."),
  ("Donne trois conditions d'une bonne conduite d'élevage (bâtiment, alimentation, prophylaxie).", 3, "Bâtiment propre, ventilé, à litière sèche ; aliment adapté et eau propre à volonté ; vaccinations et hygiène (vide sanitaire).")]))
EP.append(E(PA, "1ère", "2 h", "Traiter une situation relevant de l'élevage des ruminants.",
 "Un éleveur partenaire du lycée agricole engraisse des taurillons. Les élèves suivent le poids d'un animal pendant quatre mois.",
 "Poids mesuré au ruban : début 180 kg ; après 120 jours 240 kg. Ration journalière : 7 kg de fourrage vert et 1 kg de tourteau de coton. Une période de sécheresse approche.",
 "Tu es invité(e) à aider l'éleveur à évaluer la croissance et à préparer la saison sèche.",
 [("Définis le GMQ (gain moyen quotidien) et calcule-le pour ce taurillon.", 4, "GMQ = (poids final - poids initial) / nombre de jours = (240 - 180) / 120 = 0,5 kg soit 500 g par jour."),
  ("Calcule la quantité de fourrage vert nécessaire pour 10 taurillons pendant 30 jours.", 3, "7 x 10 x 30 = 2 100 kg."),
  ("Cite deux techniques de conservation des fourrages pour la saison sèche.", 3, "Fenaison (foin), ensilage, utilisation de résidus de culture (fanes d'arachide, de niébé)."),
  ("Explique le rôle du tourteau de coton dans la ration.", 4, "Complément riche en protéines (azote) qui améliore la croissance et la digestion des fourrages pauvres."),
  ("Propose quatre mesures de prophylaxie sanitaire du troupeau.", 4, "Vaccination, déparasitage, bain détiqueur, quarantaine des nouveaux animaux, eau propre.")]))
EP.append(E(PROT, "1ère", "2 h", "Traiter une situation relevant de la protection du maïs contre un ravageur.",
 "Dans le champ de maïs du lycée agricole, les élèves observent des feuilles trouées en rangées, des excréments de chenilles dans le cornet et des plants affaiblis. Le professeur les identifie comme une attaque de chenilles légionnaires.",
 "Fiche d'observation : 30 plants examinés sur une diagonale du champ, dont 12 portent au moins une chenille. Le seuil d'intervention retenu par le service de la protection des végétaux est de 20 % de plants attaqués.",
 "Tu es invité(e) à aider les élèves à décider de la conduite à tenir.",
 [("Calcule le pourcentage de plants attaqués et dis si le seuil est atteint.", 4, "12 / 30 = 40 % ; seuil de 20 % dépassé : intervention nécessaire."),
  ("Décris deux dégâts de ce ravageur sur le maïs.", 3, "Les chenilles dévorent les feuilles et le cornet, réduisent la photosynthèse, peuvent attaquer l'épi ; baisse du rendement."),
  ("Distingue lutte culturale, lutte biologique et lutte chimique en donnant un exemple de chacune.", 4, "Culturale : semis groupé, sarclage, rotation ; biologique : ennemis naturels, extraits de neem ; chimique : insecticide homologué utilisé à la bonne dose."),
  ("Énonce quatre consignes de sécurité pour une application de produit phytosanitaire.", 4, "Porter gants, masque, lunettes et vêtements couvrants ; respecter la dose et le délai avant récolte ; ne pas traiter par vent fort ni boire/manger ; laver le matériel loin des points d'eau."),
  ("Explique l'intérêt d'une lutte intégrée plutôt que d'un seul traitement chimique.", 3, "Combiner plusieurs méthodes limite le coût, la résistance du ravageur et les risques pour la santé et l'environnement.")]))
EP.append(E(PROT, "2nde", "2 h", "Traiter une situation relevant de la prévention des maladies de la volaille.",
 "Dans le poulailler du lycée agricole, plusieurs poules présentent une respiration difficile, des fientes verdâtres, une paralysie des pattes et une forte mortalité. Le vétérinaire évoque la maladie de Newcastle.",
 "Calendrier de la ferme : vaccin contre la maladie de Newcastle à 7 jours, rappel à 21 jours, puis tous les trois mois ; vaccin contre la maladie de Gumboro à 10 et 20 jours.",
 "Tu es invité(e) à aider les élèves à comprendre et à prévenir la maladie.",
 [("Dis ce qu'est la maladie de Newcastle (agent, transmission).", 4, "Maladie virale très contagieuse des oiseaux, transmise par contact, aliments, eau et matériel souillés, oiseaux sauvages."),
  ("Distingue prophylaxie sanitaire et prophylaxie médicale en donnant deux exemples de chacune.", 4, "Sanitaire : nettoyage, désinfection, vide sanitaire, pédiluve, isolement des malades ; médicale : vaccination, déparasitage."),
  ("Explique pourquoi on ne vaccine pas une volaille déjà gravement malade.", 3, "Le vaccin prévient mais ne guérit pas ; il protège les animaux sains ; il faut isoler et éliminer les malades."),
  ("Que faire des cadavres et du matériel contaminé ? Justifie.", 3, "Incinérer ou enfouir profondément avec de la chaux ; désinfecter le matériel pour stopper la propagation."),
  ("Propose quatre mesures de biosécurité à appliquer à l'entrée du poulailler.", 4, "Pédiluve, lavage des mains, tenue de travail, accès limité des visiteurs, séparation des bandes d'âges.")]))
EP.append(E(MACH, "1ère", "2 h", "Traiter une situation relevant du machinisme agricole et de l'irrigation d'un périmètre maraîcher.",
 "Le lycée agricole veut irriguer un périmètre maraîcher de 0,2 ha avec une motopompe. Les élèves mesurent le débit en remplissant un bidon de 200 litres en 40 secondes.",
 "Besoin des cultures : 5 mm d'eau par jour. 1 mm d'eau sur 1 m² représente 1 litre. La motopompe consomme 1,5 litre de carburant par heure.",
 "Tu es invité(e) à aider les élèves à dimensionner l'irrigation.",
 [("Calcule le débit de la pompe en litres par seconde puis en m³ par heure.", 4, "200 / 40 = 5 L/s ; 5 x 3 600 = 18 000 L/h soit 18 m³/h."),
  ("Calcule le volume d'eau nécessaire par jour pour le périmètre (0,2 ha = 2 000 m²).", 4, "2 000 m² x 5 mm = 10 000 L soit 10 m³."),
  ("Calcule la durée de fonctionnement quotidien de la pompe et la consommation de carburant correspondante.", 4, "10 m³ / 18 m³/h = 0,56 h soit environ 33 min ; carburant 1,5 x 0,56 = 0,83 L."),
  ("Compare l'arrosage à la raie et le goutte à goutte (un avantage de chacun).", 3, "Raie : peu coûteux, simple. Goutte à goutte : économise l'eau, apport ciblé, moins de maladies du feuillage."),
  ("Cite trois opérations d'entretien d'une motopompe.", 3, "Vérifier niveau d'huile et carburant, nettoyer le filtre à air et la crépine, vidanger et ranger à l'abri après usage.")]))
EP.append(E(ECO, "Tle", "2 h", "Traiter une situation relevant du calcul économique d'une exploitation agricole.",
 "Un jeune exploitant installé à l'issue de sa formation cultive 2 ha de maïs. Il veut connaître la rentabilité de son activité avant de demander un crédit.",
 "Rendement 2 000 kg/ha ; prix de vente 200 F/kg. Charges opérationnelles par hectare : semences 25 000 F ; engrais 60 000 F ; produits de traitement 15 000 F ; main-d'œuvre 80 000 F. Charges de structure annuelles : amortissement du matériel 40 000 F.",
 "Tu es invité(e) à calculer la marge brute et le résultat de l'exploitation.",
 [("Calcule le produit brut des 2 ha.", 3, "2 x 2 000 x 200 = 800 000 F."),
  ("Calcule les charges opérationnelles pour les 2 ha.", 3, "(25 000 + 60 000 + 15 000 + 80 000) x 2 = 360 000 F."),
  ("Calcule la marge brute et la marge brute par hectare.", 4, "800 000 - 360 000 = 440 000 F ; 220 000 F par hectare."),
  ("Calcule le résultat après charges de structure.", 3, "440 000 - 40 000 = 400 000 F."),
  ("Calcule le seuil de rentabilité en kg de maïs par hectare (charges opérationnelles par hectare divisées par le prix).", 3, "180 000 / 200 = 900 kg/ha."),
  ("Cite deux risques de l'activité agricole et deux moyens de les réduire.", 2, "Risques : aléas climatiques, baisse des prix ; moyens : diversification, stockage et vente groupée, assurance, appui-conseil.")]))
EP.append(E(ECO, "Tle", "2 h", "Traiter une situation relevant de l'organisation d'une coopérative agricole.",
 "Dix jeunes diplômés d'une filière agricole décident de créer une coopérative pour acheter des intrants et vendre leur production en commun. Chacun apporte une part sociale de 20 000 F.",
 "La coopérative achète 100 sacs d'engrais à 14 000 F le sac au lieu de 15 500 F pour un achat individuel. Elle vend ensuite 20 tonnes de maïs à 220 F le kg alors qu'un producteur isolé obtient 190 F.",
 "Tu es invité(e) à analyser l'intérêt de cette organisation.",
 [("Calcule le capital social de la coopérative.", 3, "10 x 20 000 = 200 000 F."),
  ("Calcule l'économie réalisée sur l'achat d'engrais.", 3, "(15 500 - 14 000) x 100 = 150 000 F."),
  ("Calcule le gain obtenu sur la vente groupée du maïs.", 4, "20 000 kg x (220 - 190) = 600 000 F."),
  ("Cite quatre principes de fonctionnement d'une coopérative.", 4, "Adhésion volontaire, un membre une voix, gestion démocratique, participation économique des membres, ristournes selon l'activité, éducation et formation."),
  ("Dis ce qui encadre juridiquement une société coopérative dans l'espace OHADA et nomme ses organes.", 4, "Acte uniforme de l'OHADA relatif au droit des sociétés coopératives ; assemblée générale, conseil d'administration, comité de surveillance.")]))

# ============================================================ INTERROGATIONS (45 min, 18 points + 2 de perfectionnement)
INT = []
def I(matiere, niveau, titre, situation, items, duree="45 min"):
    e = E(matiere, niveau, duree, "Mobiliser les savoirs de la leçon : " + titre + ".", situation, "", "Réponds aux consignes ci-dessous.", items)
    e["type"] = "Interrogation écrite"
    return e
INT.append(I(SOL, "2nde", "les constituants et la texture du sol", "Pour installer un jardin scolaire, on veut choisir le terrain le plus favorable.",
 [("Cite les quatre constituants du sol.", 4, "Éléments minéraux, matière organique, eau, air."),
  ("Définis la texture d'un sol et nomme les trois types de particules.", 4, "Proportion des particules ; sable, limon, argile."),
  ("Décris le test du bocal (trois étapes).", 5, "Prélever la terre, la délayer dans l'eau, agiter et laisser reposer 24 h ; observer et mesurer les couches."),
  ("Dis quel sol retient le mieux l'eau et pourquoi.", 5, "Le sol argileux : particules très fines, grande surface de contact ; il peut toutefois s'engorger.")]))
INT.append(I(PV, "2nde", "les travaux de préparation du sol", "Avant le semis du jardin scolaire, le chef de culture explique les travaux préparatoires.",
 [("Cite quatre outils manuels de préparation du sol.", 4, "Daba, houe, râteau, pioche, coupe-coupe, bêche."),
  ("Distingue défrichage, labour et planage.", 6, "Défrichage : enlever la végétation ; labour : retourner et ameublir ; planage : niveler."),
  ("Pourquoi vaut-il mieux éviter le brûlis ?", 4, "Détruit la matière organique et la vie du sol, expose le sol à l'érosion."),
  ("Propose deux façons de valoriser les herbes arrachées.", 4, "Compost, paillage.")]))
INT.append(I(PV, "2nde", "la pépinière et le repiquage de la tomate", "Les élèves préparent une planche de pépinière pour la tomate.",
 [("Définis pépinière et repiquage.", 4, "Pépinière : lieu où l'on élève les jeunes plants ; repiquage : transplanter le plant en place définitive."),
  ("Indique l'âge ou l'état du plant au repiquage.", 3, "Environ 3 à 4 semaines, 3 à 4 vraies feuilles."),
  ("Cite quatre soins à la pépinière.", 6, "Arrosage régulier, ombrage, désherbage, aération, protection contre les ravageurs."),
  ("Pourquoi repique-t-on de préférence le soir ou par temps frais ?", 5, "Pour limiter le stress hydrique et le flétrissement des plants.")]))
INT.append(I(PA, "2nde", "l'alimentation des volailles", "Le responsable de l'atelier prépare le programme d'alimentation d'une bande de poulets de chair.",
 [("Cite les grands groupes de nutriments d'un aliment.", 4, "Glucides, lipides, protéines, vitamines, minéraux, eau."),
  ("Distingue aliment démarrage, croissance et finition.", 6, "Aliments adaptés à l'âge : plus riche en protéines au démarrage, plus énergétique en finition."),
  ("Donne deux règles de distribution de l'aliment et de l'eau.", 4, "Eau propre à volonté, mangeoires en nombre suffisant, aliment sec, rationnement ajusté."),
  ("Pourquoi faut-il éviter l'aliment moisi ?", 4, "Toxines (mycotoxines) dangereuses pour les animaux et pour le consommateur.")]))
INT.append(I(PA, "1ère", "la reproduction et l'élevage des lapins", "Une cuniculture est installée à la ferme-école.",
 [("Donne la durée de gestation de la lapine.", 3, "Environ 30 jours."),
  ("Décris l'habitat idéal d'un lapin (trois conditions).", 5, "Cage propre et sèche, à l'ombre, ventilée, sans courant d'air, protégée des prédateurs."),
  ("Cite trois aliments du lapin.", 5, "Herbe, feuilles (légumineuses), granulés, son, résidus de légumes."),
  ("Propose deux critères de choix d'un reproducteur.", 5, "Bonne santé, croissance rapide, prolificité, bonne conformation.")]))
INT.append(I(PROT, "1ère", "les ravageurs et les maladies du niébé", "Dans le champ-école de niébé, les élèves observent des gousses percées et des feuilles enroulées.",
 [("Cite deux ravageurs du niébé.", 4, "Pucerons, Maruca (foreur des gousses), punaises, bruches au stockage."),
  ("Distingue ravageur et maladie.", 4, "Ravageur : animal qui se nourrit de la plante ; maladie : due à un micro-organisme (champignon, virus, bactérie)."),
  ("Propose deux méthodes de lutte non chimique.", 5, "Variétés tolérantes, semis précoce, extraits de neem, rotation, élimination des plants malades."),
  ("Comment protéger le niébé stocké contre les bruches ?", 5, "Séchage, sacs hermétiques (triple ensachage), cendres ou huile végétale, stockage propre.")]))
INT.append(I(TRANS, "1ère", "la conservation des produits agricoles", "La coopérative scolaire conserve ses récoltes de maïs, de tomate et d'igname.",
 [("Cite trois causes de détérioration des produits agricoles.", 5, "Humidité, chaleur, insectes et rongeurs, moisissures, mauvaise manutention."),
  ("Dis comment sécher et conserver le maïs en grains.", 5, "Séchage au soleil à 13 % d'humidité, nettoyage, stockage en sacs ou greniers aérés."),
  ("Pourquoi la tomate se conserve-t-elle mal frais ? Propose une transformation.", 4, "Forte teneur en eau, fragile ; séchage ou concentré."),
  ("Cite deux règles d'hygiène du magasin de stockage.", 4, "Nettoyer et désinsectiser, sacs sur palettes, ventilation, contrôle régulier.")]))
INT.append(I(MACH, "2nde", "les outils manuels et leur entretien", "À l'atelier, le moniteur présente les outils de la ferme-école.",
 [("Cite cinq outils manuels agricoles et leur usage.", 5, "Daba (travail du sol), houe, râteau (nivelage), serpe, arrosoir, sécateur, pulvérisateur."),
  ("Donne trois règles d'entretien d'un outil après usage.", 5, "Nettoyer, sécher, huiler les parties métalliques, aiguiser, ranger."),
  ("Cite deux équipements de protection individuelle et leur utilité.", 4, "Gants, bottes, lunettes, masque : éviter blessures et contacts avec produits."),
  ("Donne deux règles de sécurité pour le rangement et le transport des outils tranchants.", 4, "Protéger les lames, les porter dirigées vers le sol, ne pas les laisser par terre, les ranger au sec sur un support.")]))

# ============================================================ DEVOIRS (2 h, 18 points + 2 de perfectionnement)
DEV = []
def D(matiere, niveau, titre, situation, support, items, duree="2 h"):
    e = E(matiere, niveau, duree, "Mobiliser les savoirs et savoir-faire du chapitre : " + titre + ".", situation, support, "Réponds aux consignes ci-dessous.", items)
    e["type"] = "Devoir surveillé"
    return e
DEV.append(D(PV, "2nde", "le maraîchage", "Le lycée agricole installe une planche de culture maraîchère de 20 m x 10 m pour la tomate.",
 "Écartement de la tomate : 60 cm x 50 cm ; 1 plant par poquet. Un plant produit en moyenne 2 kg de fruits ; la tomate se vend 300 F le kg. Pertes estimées à 10 %.",
 [("Calcule la superficie de la planche.", 2, "20 x 10 = 200 m²."),
  ("Calcule le nombre de plants nécessaires (en négligeant les bordures).", 4, "0,6 x 0,5 = 0,30 m² ; 200 / 0,30 = environ 666 plants."),
  ("Calcule la production attendue et la recette après pertes.", 5, "666 x 2 = 1 332 kg ; pertes 10 % : 1 199 kg ; recette environ 359 700 F."),
  ("Cite quatre soins d'entretien de la tomate.", 4, "Arrosage, sarclage, tuteurage, paillage, fertilisation, traitement, taille."),
  ("Explique l'intérêt de la rotation des cultures au jardin.", 3, "Limiter maladies et ravageurs, utiliser des réserves différentes, entretenir la fertilité.")]))
DEV.append(D(SOL, "1ère", "la fertilisation", "Le chef de culture doit établir un plan de fumure pour 1 ha de maïs.",
 "Fumure de référence : 200 kg de NPK 15-15-15 et 100 kg d'urée (46 % d'azote) par hectare. Prix : NPK 24 000 F le sac de 50 kg ; urée 22 000 F le sac de 50 kg.",
 [("Explique ce que signifie « NPK 15-15-15 ».", 3, "15 % d'azote (N), 15 % de P2O5, 15 % de K2O."),
  ("Calcule la quantité d'azote apportée par le NPK puis par l'urée.", 4, "NPK : 200 x 0,15 = 30 kg ; urée : 100 x 0,46 = 46 kg ; total 76 kg."),
  ("Calcule le coût de la fumure à l'hectare.", 4, "NPK : 4 sacs = 96 000 F ; urée : 2 sacs = 44 000 F ; total 140 000 F."),
  ("Compare engrais organique et minéral (un avantage, un inconvénient).", 4, "Organique : améliore la structure, libération lente mais faible teneur ; minéral : action rapide, dosage précis mais coûteux, risque de lessivage."),
  ("Propose deux pratiques pour mieux utiliser l'engrais.", 3, "Enfouir ou localiser près du plant, fractionner les apports, éviter les fortes pluies.")]))
DEV.append(D(PA, "1ère", "l'élevage des petits ruminants", "La ferme-école démarre un élevage de 20 chèvres et de 1 bouc.",
 "Prolificité : 1,5 chevreau par mise bas ; 1,5 mise bas par chèvre et par an ; mortalité des chevreaux 15 %. Un chevreau sevré se vend 25 000 F.",
 [("Calcule le nombre de chevreaux nés par an.", 4, "20 x 1,5 x 1,5 = 45."),
  ("Calcule le nombre de chevreaux sevrés et la recette de vente.", 5, "45 x 0,85 = 38 ; 38 x 25 000 = 950 000 F."),
  ("Cite trois conditions d'un bon bâtiment pour caprins.", 4, "Sol sec et surélevé, ombragé, bien aéré, mangeoires et abreuvoirs, enclos."),
  ("Donne deux maladies fréquentes des petits ruminants et un moyen de prévention.", 3, "Peste des petits ruminants (vaccination), parasitoses (déparasitage)."),
  ("Indique deux intérêts de l'association élevage-agriculture.", 2, "Fumure animale pour les champs, résidus de culture pour l'alimentation.")]))
DEV.append(D(PROT, "Tle", "la lutte intégrée", "Dans un champ de tomate, les élèves relèvent des pucerons, une mouche blanche et des taches brunes sur les feuilles.",
 "Fiche de suivi : 20 plants suivis chaque semaine ; semaine 1 : 4 plants attaqués ; semaine 2 : 8 ; semaine 3 : 14. Seuil d'intervention : 30 % de plants atteints.",
 [("Calcule le taux d'attaque de chaque semaine.", 4, "20 %, 40 %, 70 %."),
  ("Dis à quelle semaine il fallait intervenir et justifie.", 3, "Dès la semaine 2 : 40 % dépasse le seuil de 30 %."),
  ("Définis la lutte intégrée et cite trois de ses composantes.", 4, "Combinaison de méthodes ; culturale, biologique, physique, chimique raisonnée, surveillance."),
  ("Cite quatre précautions à l'emploi d'un pesticide.", 4, "Équipement de protection, dose, délai avant récolte, stockage sécurisé, élimination des emballages."),
  ("Explique pourquoi l'usage répété d'un même produit est risqué.", 3, "Apparition de résistances, destruction des auxiliaires, résidus sur la récolte.")]))
DEV.append(D(ECO, "1ère", "les comptes d'une activité d'élevage", "Les élèves tiennent le cahier de comptes de l'atelier poulets de chair.",
 "Recettes : vente de 190 poulets à 2 800 F. Charges : poussins 100 000 F ; aliment 315 000 F ; médicaments 20 000 F ; eau et énergie 25 000 F ; main-d'œuvre 60 000 F.",
 [("Calcule le total des recettes et celui des charges.", 4, "Recettes 532 000 F ; charges 520 000 F."),
  ("Calcule le résultat et dis si l'activité est rentable.", 4, "12 000 F de bénéfice : faiblement rentable."),
  ("Calcule le coût de production d'un poulet et le prix de revient du kg de poids vif (poids moyen 2 kg).", 4, "520 000 / 190 = 2 737 F ; 2 737 / 2 = 1 368 F le kg."),
  ("Propose deux moyens d'améliorer le résultat.", 3, "Réduire la mortalité, améliorer l'indice de consommation, mieux négocier l'aliment et la vente."),
  ("Dis à quoi servent le cahier de comptes et le suivi d'une bande.", 3, "Connaître les coûts, décider, justifier le crédit, comparer les bandes.")]))
DEV.append(D(MACH, "Tle", "la topographie et l'aménagement d'un périmètre", "Les élèves lèvent le plan d'un terrain rectangulaire de 150 m sur 80 m pour le diviser en planches.",
 "Le terrain est divisé en parcelles égales de 1 are chacune (1 are = 100 m²) séparées par des allées de 1 m. Le piquetage se fait au décamètre et à la chaîne d'arpenteur.",
 [("Calcule la surface du terrain en m², en ares et en hectares.", 4, "12 000 m² = 120 ares = 1,2 ha."),
  ("Calcule le périmètre et la longueur de clôture si l'on ajoute un portail de 3 m.", 4, "P = 460 m ; clôture 457 m."),
  ("Explique comment tracer un angle droit sur le terrain avec le triangle 3-4-5.", 4, "Mesurer 3 m, 4 m et 5 m avec un cordeau pour former un triangle rectangle (réciproque de Pythagore)."),
  ("Cite deux instruments de topographie et leur usage.", 3, "Décamètre (longueurs), jalons, équerre optique, niveau (dénivelés)."),
  ("Pourquoi un drainage est-il utile sur un terrain plat à sol argileux ?", 3, "Évite l'engorgement et l'asphyxie des racines.")]))

# ============================================================ BIBLIOTHÈQUE : fonctions de fusion
EPREUVES_AGRI = EP + INT + DEV

# ============================================================ TRAVAUX PRATIQUES (fiches de TP agricoles)
CHAMPS_TP = ["matiere", "niveau", "filiere", "titre", "duree", "objectif", "prerequis", "materiel", "securite", "deroulement", "evaluation"]
_T = [
 (TP, "2nde", "Production végétale", "Installation d'une planche de pépinière", "3 heures",
  "Préparer une planche de pépinière, semer et entretenir des jeunes plants.", "Notions sur la germination et les types de sol.",
  "Daba, râteau, arrosoir, cordeau, graines de tomate ou de piment, compost bien décomposé, paille pour le paillage, piquets.",
  "Port de bottes et de gants ; se laver les mains après le travail ; ranger les outils tranchants.",
  "1. Choisir un emplacement plat, ensoleillé le matin et proche de l'eau. 2. Défricher, ameublir sur 20 cm et mélanger le compost. 3. Tracer une planche de 1 m de large et tracer des lignes espacées de 10 cm. 4. Semer à faible profondeur, recouvrir légèrement. 5. Pailler et arroser en pluie fine. 6. Poser un ombrage et noter la date.",
  "Planche propre et bien nivelée (4 pts) ; lignes régulières (4 pts) ; semis à la bonne profondeur (4 pts) ; arrosage et paillage corrects (4 pts) ; respect des consignes de sécurité et rangement (4 pts)."),
 (TP, "2nde", "Production végétale", "Semis et entretien d'une parcelle de maïs", "4 heures",
  "Semer le maïs selon l'écartement recommandé et réaliser le démariage et le sarclage.", "Calcul de la densité de semis.",
  "Cordeau, double décamètre, daba, semences certifiées, piquets, cahier de travaux.",
  "Ne pas manipuler les semences traitées sans gants ; se laver les mains ; ne pas porter les mains à la bouche.",
  "1. Tracer les lignes à 80 cm. 2. Marquer les poquets tous les 40 cm. 3. Semer 2 grains par poquet à 3-4 cm de profondeur. 4. Recouvrir. 5. Noter la date de semis. 6. À 10-15 jours : démarier à un plant par poquet. 7. Sarcler et butter. 8. Reporter les travaux sur le cahier de la ferme-école.",
  "Respect des écartements (5 pts) ; profondeur du semis (3 pts) ; démariage et sarclage (4 pts) ; renseignement du cahier (4 pts) ; sécurité et travail d'équipe (4 pts)."),
 (TP, "1ère", "Production végétale", "Compostage de résidus agricoles", "3 heures",
  "Fabriquer un tas de compost avec les résidus de la ferme et suivre sa température.", "Notions sur la matière organique et la décomposition.",
  "Fourche, brouette, résidus verts et secs, fumier, eau, thermomètre ou tige métallique, paille, bâche.",
  "Gants et bottes ; ne pas respirer la poussière ; se laver les mains après le travail.",
  "1. Choisir un endroit ombragé. 2. Poser en couches alternées : matières sèches, matières vertes, fumier. 3. Humidifier chaque couche. 4. Couvrir. 5. Retourner à 3 semaines. 6. Noter la température chaque semaine. 7. Récolter quand le compost est brun, friable et sans mauvaise odeur.",
  "Respect des couches (5 pts) ; humidité correcte (4 pts) ; suivi écrit (5 pts) ; propreté et sécurité (6 pts)."),
 (TP, "2nde", "Production animale", "Préparation d'un poulailler et mise en place des poussins", "3 heures",
  "Nettoyer, désinfecter et préparer le bâtiment puis accueillir les poussins.", "Notions d'hygiène et de prophylaxie.",
  "Balais, seaux, désinfectant, pédiluve, litière (copeaux ou balle de riz), mangeoires, abreuvoirs, éleveuse ou lampes, thermomètre.",
  "Gants et masque pour les désinfectants ; ne pas mélanger les produits ; bien aérer.",
  "1. Vider, balayer et laver le bâtiment. 2. Désinfecter et laisser reposer (vide sanitaire). 3. Installer la litière sèche. 4. Placer pédiluve, mangeoires et abreuvoirs. 5. Chauffer le bâtiment avant l'arrivée des poussins. 6. Accueillir et compter les poussins, noter la date et l'effectif. 7. Surveiller la température et le comportement.",
  "Nettoyage et désinfection (6 pts) ; installation du matériel (5 pts) ; accueil des poussins (5 pts) ; sécurité et cahier d'élevage (4 pts)."),
 (TP, "1ère", "Production animale", "Pesée et suivi de croissance d'un lot", "2 heures",
  "Peser des animaux, calculer le poids moyen, le gain de poids et l'indice de consommation.", "Calcul de moyennes et de rapports.",
  "Balance, seau ou panier de pesée, fiche de suivi, calculatrice, aliment pesé.",
  "Manipuler les animaux avec calme ; se laver les mains ; isoler tout animal malade.",
  "1. Peser un échantillon de 20 % du lot. 2. Calculer le poids moyen. 3. Comparer à la pesée précédente et calculer le gain. 4. Peser l'aliment distribué et calculer l'indice de consommation. 5. Noter les observations sanitaires.",
  "Pesées correctes (5 pts) ; calculs justes (6 pts) ; fiche remplie (4 pts) ; manipulation et hygiène (5 pts)."),
 (TP, "2nde", "Pisciculture", "Entretien et alimentation d'un étang piscicole", "3 heures",
  "Contrôler l'eau d'un étang, nourrir les poissons et noter les observations.", "Notions sur la qualité de l'eau et les besoins des poissons.",
  "Épuisette, seau, bâtons de marque, disque de Secchi ou bocal, aliment, cahier de pisciculture, gants.",
  "Ne pas se baigner dans l'étang ; surveiller les berges glissantes ; se laver les mains.",
  "1. Observer la couleur de l'eau et le comportement des poissons. 2. Mesurer la transparence. 3. Nettoyer les abords. 4. Distribuer l'aliment à heures fixes et peser la ration. 5. Retirer les poissons morts. 6. Noter température, aliment et mortalité.",
  "Observation (5 pts) ; alimentation (5 pts) ; cahier (5 pts) ; sécurité et rangement (5 pts)."),
 (TP, "1ère", "Transformation", "Transformation du manioc en gari", "4 heures",
  "Réaliser les étapes de fabrication du gari dans le respect de l'hygiène.", "Notions sur les composés cyanés du manioc et l'hygiène alimentaire.",
  "Racines de manioc, couteaux inox, râpe, sacs, presse, tamis, plat de torréfaction, balance, emballages.",
  "Attention aux brûlures ; blouse et charlotte ; mains propres ; ne jamais consommer la pâte non transformée.",
  "1. Éplucher, laver et râper. 2. Mettre la pâte en sac et presser en laissant fermenter 2 à 3 jours. 3. Émietter et tamiser. 4. Torréfier en remuant. 5. Tamiser, refroidir et emballer. 6. Peser et calculer le rendement.",
  "Respect des étapes (6 pts) ; hygiène (5 pts) ; rendement calculé (4 pts) ; qualité du produit (5 pts)."),
 (TP, "1ère", "Machinisme", "Entretien d'un pulvérisateur et réglage du débit", "3 heures",
  "Entretenir un pulvérisateur à dos et mesurer le débit pour traiter en toute sécurité.", "Notions sur les produits phytosanitaires.",
  "Pulvérisateur à dos, eau claire, seau gradué, chronomètre, clé, joints, équipement de protection.",
  "Toujours s'entraîner à l'eau claire ; ne jamais manipuler un produit sans équipement ; laver le matériel loin des points d'eau.",
  "1. Contrôler joints, filtre et buse. 2. Remplir d'eau claire et vérifier les fuites. 3. Mesurer le volume pulvérisé pendant une minute. 4. Régler la pression. 5. Calculer le volume par hectare. 6. Rincer et ranger.",
  "Contrôle du matériel (5 pts) ; mesure du débit (5 pts) ; calcul (5 pts) ; sécurité et rangement (5 pts)."),
]
TP_LISTE = [dict(zip(CHAMPS_TP, t)) for t in _T]

# ============================================================ FICHES DE PRÉPARATION (APC)
C = ["matiere", "niveau", "titre", "duree", "competence", "situation", "objectifs", "mise_en_situation", "recherche", "trace", "application", "prolongement"]
_F = [
 (SOL, "2nde", "Les constituants du sol et le test du bocal", "2 x 55 min",
  "Traiter une situation relevant de la connaissance d'un sol cultivé.",
  "Le champ-école de ton lycée donne de faibles rendements. Pour comprendre pourquoi, tu dois d'abord connaître le sol.",
  "Nommer les constituants du sol ; déterminer la texture par le test du bocal ; relier la texture aux usages agricoles.",
  "Le professeur présente trois échantillons de sol (sableux, limoneux, argileux) et demande aux élèves de les toucher et de dire ce qu'ils observent.",
  "En groupes, les élèves mélangent chaque échantillon à de l'eau dans un bocal, agitent, laissent reposer, puis mesurent les couches et calculent les pourcentages.",
  "Le sol comprend des éléments minéraux (sable, limon, argile), de la matière organique, de l'eau et de l'air. La texture dépend des proportions de sable, de limon et d'argile. Le sol sableux draine vite et retient peu ; le sol argileux retient l'eau mais peut s'engorger.",
  "Exercice : calculer la texture d'un échantillon (7 cm de sable, 2 cm de limon, 1 cm d'argile) et proposer une culture adaptée.",
  "Rapporter un échantillon de sol de la maison ou du champ familial pour le test."),
 (PV, "2nde", "La préparation du sol et le semis du maïs", "2 x 55 min",
  "Traiter une situation relevant de la conduite d'une culture de maïs.",
  "L'arrivée de la saison des pluies approche. Le champ-école doit être prêt à semer du maïs.",
  "Citer les opérations de préparation du sol ; semer selon un écartement donné ; calculer la densité.",
  "Les élèves observent une photo du champ avant et après labour et expliquent le rôle de chaque opération.",
  "Sur le terrain, ils tracent les lignes au cordeau (80 cm), marquent les poquets tous les 40 cm, sèment deux grains par poquet et calculent le nombre de poquets pour 1 are.",
  "Préparation : défrichage, labour, planage. Semis : écartement 80 x 40 cm, 2 grains par poquet à 3-4 cm, démariage à 1 plant. Densité : 1 poquet pour 0,32 m².",
  "Calculer le nombre de poquets et la quantité de semences pour 2 ha (environ 25 kg/ha).",
  "Observer la levée du maïs pendant deux semaines et noter le taux de levée."),
 (PV, "1ère", "La culture du manioc et sa transformation en gari", "2 x 55 min",
  "Traiter une situation relevant de la production et de la transformation du manioc.",
  "Une coopérative veut transformer sa récolte de manioc en gari. Il faut connaître les étapes et estimer le rendement.",
  "Citer les étapes de culture du manioc ; décrire la transformation en gari ; calculer un rendement.",
  "Dégustation commentée de gari : d'où vient-il ? comment est-il fabriqué ?",
  "En petits groupes, les élèves remettent dans l'ordre les étapes de fabrication à partir de vignettes, puis calculent un rendement.",
  "Culture : boutures de 20-25 cm, plantation au début des pluies, récolte à 9-12 mois. Transformation : épluchage, râpage, pressage-fermentation, tamisage, torréfaction.",
  "7 500 kg de racines donnent 20 % de gari : calculer la quantité et la recette à 450 F le kg.",
  "Interroger un transformateur du village sur son procédé."),
 (PA, "2nde", "L'élevage des poulets de chair : bâtiment et alimentation", "2 x 55 min",
  "Traiter une situation relevant de la conduite d'un élevage de poulets de chair.",
  "Le lycée agricole prépare l'arrivée d'une nouvelle bande de poussins.",
  "Décrire les qualités d'un poulailler ; établir un programme d'alimentation ; connaître les phases de croissance.",
  "Des photos de deux poulaillers sont présentées : l'un propre et aéré, l'autre sale et surpeuplé. Lequel choisir ?",
  "Les élèves relèvent les différences, calculent la densité (nombre de poulets par m²) puis classent les aliments démarrage, croissance et finition.",
  "Poulailler : propre, sec, ventilé, litière épaisse, densité de 10 à 12 sujets/m² ; eau propre à volonté. Aliment : démarrage riche en protéines, croissance, finition.",
  "Calculer la surface pour 200 poulets à 10 sujets/m² ; proposer un programme alimentaire.",
  "Tenir pendant une semaine un cahier d'élevage fictif (consommation et poids)."),
 (PA, "1ère", "Le calcul du GMQ et de l'indice de consommation", "2 x 55 min",
  "Évaluer les performances techniques d'un lot d'animaux.",
  "L'éleveur veut savoir si l'engraissement est rentable ; il faut mesurer la croissance et la consommation.",
  "Définir et calculer le GMQ et l'indice de consommation ; interpréter les résultats.",
  "Les élèves disposent de pesées d'un taurillon à trois dates et doivent dire s'il grandit bien.",
  "Ils calculent le gain de poids, le GMQ et l'indice de consommation ; ils comparent à des valeurs de référence données par le professeur.",
  "GMQ = (poids final - poids initial) / nombre de jours. Indice de consommation = aliment consommé / gain de poids. Plus l'indice est faible, meilleure est la performance.",
  "Calculer le GMQ et l'indice pour deux lots et conclure.",
  "Collecter les poids d'un animal de la maison et calculer son GMQ."),
 (PROT, "1ère", "Les ravageurs du maïs et la lutte intégrée", "2 x 55 min",
  "Traiter une situation relevant de la protection des cultures.",
  "Des dégâts de chenilles apparaissent dans le champ de maïs du lycée.",
  "Identifier les symptômes ; calculer un taux d'attaque ; choisir une méthode de lutte.",
  "Observation de feuilles de maïs trouées. Qui est responsable ?",
  "Les élèves examinent 30 plants et calculent le pourcentage de plants attaqués, comparent au seuil, puis classent les méthodes de lutte.",
  "Lutte intégrée : surveillance, méthodes culturales (semis groupé, sarclage), biologique (extraits de neem), chimique raisonnée avec protection de l'applicateur.",
  "Exercice : calculer le taux d'attaque et décider de la conduite à tenir.",
  "Rechercher les noms locaux d'un ravageur et d'un moyen de lutte traditionnel."),
 (MACH, "1ère", "L'irrigation d'un périmètre maraîcher", "2 x 55 min",
  "Dimensionner une irrigation simple.",
  "Le maraîchage de contre-saison exige un arrosage régulier.",
  "Mesurer un débit ; calculer le besoin en eau et la durée d'arrosage.",
  "Le professeur remplit un seau chronométré : combien de litres par seconde ?",
  "Les élèves mesurent le débit, calculent les besoins d'une planche et comparent arrosage manuel, à la raie et goutte à goutte.",
  "Débit = volume / temps. 1 mm sur 1 m² = 1 litre. Durée = besoin / débit.",
  "Calculer la durée d'arrosage de 500 m² avec un besoin de 5 mm/jour et un débit de 18 m³/h.",
  "Réaliser un schéma d'un système goutte à goutte de fortune."),
 (ECO, "Tle", "La marge brute d'une culture", "2 x 55 min",
  "Évaluer la rentabilité d'une production agricole.",
  "Un jeune agriculteur hésite entre le maïs et le soja. Il faut comparer les marges brutes.",
  "Distinguer produit et charges ; calculer la marge brute ; comparer deux cultures.",
  "Deux fiches de comptes sont distribuées : laquelle est la plus rentable ?",
  "Les élèves calculent produit brut, charges opérationnelles et marge brute pour chaque culture puis commentent.",
  "Marge brute = produit brut - charges opérationnelles. Seuil de rentabilité = charges / prix. Le résultat tient compte aussi des charges de structure.",
  "Comparer deux cultures à partir de données chiffrées et conseiller.",
  "Interroger un producteur sur ses coûts de production."),
]
FICHES_AGRI = [dict(zip(C, f)) for f in _F]

# ============================================================ THÈMES D'EXPOSÉS (matière, niveaux, titre, axes, consigne)
EXPOSES_AGRI = [
 (PV, "2nde–Tle", "Le maraîchage de contre-saison au Bénin", "Les cultures maraîchères (tomate, piment, gombo, légumes feuilles) ; l'irrigation ; les débouchés ; les difficultés", "Illustrer par une visite ou une enquête auprès d'un maraîcher."),
 (PV, "2nde–Tle", "La filière anacarde (noix de cajou) au Bénin", "La culture de l'anacardier ; la récolte et le séchage ; la transformation ; la commercialisation", "Présenter les atouts et les défis de la filière."),
 (PV, "2nde–Tle", "L'agroforesterie : associer arbres et cultures", "Définition et exemples ; intérêts (sol, ombre, revenus) ; limites ; exemples béninois (karité, néré)", "Proposer un schéma d'association pour une exploitation."),
 (PA, "2nde–Tle", "L'aviculture moderne : du poussin au marché", "Les types d'élevage ; la conduite d'une bande ; les maladies et vaccinations ; la rentabilité", "Calculer un exemple chiffré."),
 (PA, "2nde–Tle", "La pisciculture en étang : tilapia et silure", "Les espèces ; la construction de l'étang ; l'alimentation ; la récolte et la vente", "Dessiner un étang avec ses dimensions."),
 (PA, "2nde–Tle", "L'élevage des aulacodes et des lapins : élevages à cycle court", "Atouts ; habitat et alimentation ; reproduction ; commercialisation", "Comparer les deux élevages."),
 (SOL, "2nde–Tle", "La fertilité des sols et les pratiques de restauration", "Les causes de la dégradation ; la matière organique et le compost ; les légumineuses et la jachère ; la lutte antiérosive", "Proposer un plan de restauration pour un champ."),
 (PROT, "2nde–Tle", "Les produits phytosanitaires : bien les utiliser et protéger sa santé", "Les types de produits ; la dose et l'application ; les équipements de protection ; les alternatives (neem, lutte biologique)", "Rédiger une affiche de consignes de sécurité."),
 (PROT, "2nde–Tle", "La santé animale : prévenir plutôt que guérir", "Les maladies courantes ; vaccins et calendrier ; hygiène et biosécurité ; rôle du vétérinaire", "Construire un calendrier de vaccination."),
 (TRANS, "2nde–Tle", "La transformation des produits locaux : gari, huile de palme, jus", "Le gari ; l'huile de palme ; les jus de fruits ; l'hygiène et l'emballage", "Réaliser un schéma de chaîne de transformation."),
 (MACH, "2nde–Tle", "La mécanisation de l'agriculture familiale", "Les outils et machines ; la traction animale et motorisée ; les coûts ; l'entretien", "Comparer travail manuel et travail mécanisé."),
 (ECO, "2nde–Tle", "Les coopératives et groupements de producteurs", "Les principes ; les avantages ; le fonctionnement ; les limites", "Illustrer par une coopérative de la région."),
 (ECO, "2nde–Tle", "Du jeune diplômé à l'agri-entrepreneur : monter un projet agricole", "L'idée et l'étude de marché ; le budget et le financement ; le plan de production ; les risques", "Présenter un mini-projet chiffré."),
 (ECO, "2nde–Tle", "Les changements climatiques et l'agriculture béninoise", "Les constats ; les effets sur les cultures et les élevages ; l'adaptation ; les pratiques durables", "Proposer trois mesures d'adaptation."),
]

# ============================================================ FICHES DE RÉVISION (matière, niveau, titre, [points], méthode, pièges, [(question, réponse)])
REVISIONS_AGRI = [
 (SOL, "2nde", "Le sol et sa texture", [
   "Le sol est formé de minéraux (sable, limon, argile), de matière organique, d'eau et d'air.",
   "La texture dépend de la proportion de sable, de limon et d'argile ; le test du bocal permet de la déterminer.",
   "Sol sableux : léger, drainant, pauvre ; sol argileux : lourd, retient l'eau ; sol limoneux : intermédiaire.",
   "Le pH indique l'acidité du sol ; un sol acide peut limiter la disponibilité de certains éléments."],
  "Mesurer l'épaisseur de chaque couche, l'épaisseur totale, puis calculer le pourcentage de chaque constituant.",
  "Confondre texture (proportions des particules) et structure (agencement des agrégats) ; oublier de convertir en pourcentage.",
  [("Un bocal contient 6 cm de sable, 3 cm de limon et 1 cm d'argile. Donne la texture.", "60 % de sable, 30 % de limon, 10 % d'argile : sol sableux."),
   ("Cite deux moyens d'améliorer un sol sableux.", "Apport de compost ou de fumier ; paillage ; cultures de couverture.")]),
 (PV, "2nde", "La culture du maïs", [
   "Semis : 80 x 40 cm, 2 grains par poquet, au début des pluies.",
   "Entretien : démariage, sarclage, buttage, fertilisation (NPK puis urée).",
   "Récolte quand les spathes sont sèches ; séchage à environ 13 % d'humidité ; stockage à l'abri.",
   "Rotation avec les légumineuses (niébé, arachide) pour entretenir la fertilité."],
  "Pour calculer le nombre de plants : 10 000 m² divisés par la surface occupée par un poquet, puis multiplier par le nombre de plants par poquet.",
  "Confondre le nombre de poquets et le nombre de plants ; oublier de convertir l'hectare en m².",
  [("Combien de poquets à l'hectare pour un écartement de 80 x 40 cm ?", "10 000 / 0,32 = 31 250 poquets."),
   ("Pourquoi sarcler ?", "Éliminer la concurrence des herbes pour l'eau, la lumière et les éléments nutritifs.")]),
 (PA, "2nde", "Les performances d'un élevage de poulets de chair", [
   "Taux de mortalité = nombre de morts / effectif de départ x 100.",
   "Gain de poids = poids final - poids initial.",
   "Indice de consommation = aliment consommé / gain de poids ; plus il est faible, meilleur est l'élevage.",
   "Prophylaxie sanitaire (hygiène) et prophylaxie médicale (vaccins)."],
  "Faire d'abord un tableau avec les données, puis calculer chaque indicateur dans l'ordre.",
  "Diviser par le poids final au lieu du gain de poids ; oublier la mortalité dans l'effectif final.",
  [("Aliment consommé 700 kg, gain de poids 372 kg. Calcule l'indice de consommation.", "700 / 372 = 1,88."),
   ("Cite deux mesures de biosécurité.", "Pédiluve, accès limité, séparation des bandes.")]),
 (PA, "1ère", "Les ruminants : alimentation et croissance", [
   "GMQ = (poids final - poids initial) / nombre de jours.",
   "Les ruminants valorisent les fourrages grâce à la rumination et à la flore du rumen.",
   "En saison sèche : foin, ensilage, résidus de culture, compléments (tourteaux, sel, minéraux).",
   "Prophylaxie : vaccination, déparasitage, hygiène, eau propre."],
  "Toujours vérifier l'unité du GMQ (kg/j ou g/j) avant de conclure.",
  "Oublier de convertir en grammes ; confondre poids vif et poids carcasse.",
  [("Un animal passe de 180 à 240 kg en 120 jours. Quel est son GMQ ?", "0,5 kg/j soit 500 g/j."),
   ("Pourquoi complémenter en saison sèche ?", "Les pâturages sont pauvres ; le complément évite l'amaigrissement.")]),
 (PROT, "1ère", "La lutte contre les ravageurs", [
   "Taux d'attaque = plants attaqués / plants observés x 100.",
   "Lutte intégrée : surveillance + méthodes culturales + biologique + chimique raisonnée.",
   "Protection de l'applicateur : gants, masque, lunettes, vêtements couvrants.",
   "Respect de la dose et du délai avant récolte."],
  "Comparer le taux d'attaque au seuil d'intervention avant de décider de traiter.",
  "Traiter systématiquement sans observer ; ignorer les consignes de sécurité.",
  [("12 plants attaqués sur 30. Calcule le taux d'attaque.", "40 %."),
   ("Cite une méthode de lutte biologique.", "Utiliser des ennemis naturels ou des extraits de neem.")]),
 (ECO, "Tle", "La marge brute", [
   "Produit brut = quantité produite x prix de vente.",
   "Charges opérationnelles : semences, engrais, produits de traitement, main-d'œuvre saisonnière.",
   "Marge brute = produit brut - charges opérationnelles.",
   "Seuil de rentabilité = charges / prix de vente (en quantité)."],
  "Présenter un tableau Produits / Charges / Marge, calculer à l'hectare puis pour toute la surface.",
  "Oublier une charge ; confondre marge brute et bénéfice final.",
  [("Produit brut 800 000 F ; charges opérationnelles 360 000 F. Calcule la marge brute.", "440 000 F."),
   ("Quel est l'intérêt du seuil de rentabilité ?", "Savoir à partir de quel niveau de production l'activité couvre ses coûts.")]),
]


# ============================================================ intégration aux bibliothèques existantes (idempotente)
_FAIT = []


def integrer():
    """Ajoute le contenu agricole aux listes de la bibliothèque (épreuves APC, fiches, exposés, révisions). Les identifiants des
    épreuves sont les positions dans la liste, comme pour les épreuves existantes."""
    if _FAIT:
        return
    import epreuves_apc as AP
    import fiches_sec as FS
    import ressources_secondaire as R
    AP.EPREUVES.extend(EPREUVES_AGRI)
    for i, e in enumerate(AP.EPREUVES):
        e["id"] = i
    FS.FICHES.extend(FICHES_AGRI)
    R.EXPOSES.extend(EXPOSES_AGRI)
    R.REVISIONS.extend(REVISIONS_AGRI)
    _FAIT.append(1)
