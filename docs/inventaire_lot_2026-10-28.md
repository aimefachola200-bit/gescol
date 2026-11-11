# Inventaire du lot du 28/10/2026 (version 1.31.0)

Deux envois : manuels, mesures correctives et résumés (lot `2026-10-28`), puis guides de l'enseignant (lot `2026-10-28b`, 19 PDF).
Règle appliquée : les documents officiels MEMP/INFRE servent de sources (citées, courtes citations seulement) ; les documents de tiers (auteur, téléphone, filigrane, éditeur commercial) sont **référence seulement** : aucun texte repris, filigranes non retirés, contenu réécrit de façon originale.

## 1. Documents utilisés (lot 2026-10-28)

| Document | Cours | Matière | Statut | Usage dans 1.31.0 |
|---|---|---|---|---|
| Manuel de français CE1 (MEMP 2008) | CE1 | Lecture | Officiel | 49 textes rattachés aux séances (titre, page) ; 49 résumés de lecture réécrits |
| « Je lis tout seul » — manuel de français CE2 (INFRE 2004) | CE2 | Lecture | Officiel | 49 textes (numéro de texte, scans en double page) ; 49 résumés |
| Manuel de français CM2 (INFRE/DEP 2004) | CM2 | Lecture | Officiel | 36 textes (titre, page) ; 36 résumés |
| Manuel de mathématiques CE1 (MEMP 2008) | CE1 | Maths | Officiel | 126 fiches reliées aux dossiers/SA/pages |
| Manuel de mathématiques CE2 (INFRE 2004) | CE2 | Maths | Officiel | 141 fiches reliées aux dossiers/SA (pages non lisibles sur le scan) |
| Manuel de mathématiques CM1 (INFRE 2004) | CM1 | Maths | Officiel | 72 fiches reliées aux dossiers/SA/pages |
| Manuel de mathématiques CM2 (INFRE 2004) | CM2 | Maths | Officiel | 79 fiches reliées (pages partielles) |
| Mesures correctives Français-Maths (MEMP 2011) | CI-CM2 | FR, MA | Officiel | Comparaison avec les progressions, voir § 3 |
| Mesures correctives ES-EPS (MEMP 2011) | CI-CM2 | ES, EPS | Officiel (marque en relief d'un détenteur : contenu seulement) | Activité préliminaire, planification EPS |
| Mesures correctives EST-EA (MEMP 2011) | CI-CM2 | EST, EA | Officiel | Activité préliminaire EST, planification EA |
| Fiche « Diphtongues CE1 » | CE1 | Français | Tiers (filigrane) — référence | Seul le tableau officiel des 32 séries (mesures correctives) a servi ; fiches réécrites |
| Résumés CE2 : civisme, morale, histoire, EST (CamScanner, auteur inconnu) | CE2 | ES, EST | Tiers — référence | Notions manquantes repérées ; 17 résumés originaux ajoutés |
| « 100 succès au CEP » (MN Educ Services) | CM2 | Toutes | Tiers — référence | Format des questions type CEP observé ; rien repris |

**Manque :** aucun manuel de français CM1 dans le lot. Les résumés de lecture du CM1 restent les résumés génériques actuels.

Les autres fichiers du dossier du lot (fiches CI à CM2, épreuves standardisées, guides CM1, fichier de mathématiques 2026, etc.) proviennent d'envois antérieurs et sont déjà intégrés au corpus.

## 2. Guides du lot 2026-10-28b : dédoublonnage

Comparaison par empreinte md5 avec les lots précédents, puis comparaison du contenu avec les guides du corpus.

| Fichier | Décision |
|---|---|
| GUIDE_EPS_CI | **Nouveau** → `g-memp-eps-ci` (12 SA) |
| GUIDE_EPS_CP | **Nouveau** → `g-memp-eps-cp` (13 SA) |
| GUIDE_EPS_CE1-CE2 | **Nouveau** → `g-memp-eps-ce` (CE1 : 6 SA, CE2 : 5 SA) |
| GUIDE_ES_CM1 | **Nouveau** → `g-memp-es-cm1` (8 SA, identiques au corpus) |
| GUIDE_EST_CE1_ET_CE2 | **Nouveau** → `g-memp-est-ce` (CE1 : 8 SA, CE2 : 9 SA, identiques au corpus) |
| GUIDE_MATH_CE1 | **Nouveau** → `g-memp-ma-ce1` (tableau des dossiers) |
| GUIDE_MATH_CE2 | **Nouveau** → `g-memp-ma-ce2` (a complété les titres des SA du manuel CE2) |
| GUIDE_MATHÉMATIQUE_CM2 | **Nouveau** → `g-memp-ma-cm2` |
| GUIDE_FRANÇAIS_CE1 | **Nouveau** → `g-memp-fr-ce1` |
| GUIDE_FRANÇAIS_CE2 (MEMP) | **Nouveau** → `g-memp-fr-ce2` |
| Guide français CI (INFRE 2021) | Déjà cité par les fiches CI ; ajouté à l'onglet Guides → `g-memp-fr-ci` |
| GUIDE_FRANÇAIS_CM1, GUIDE_EST_CM1, GUIDE_MATHÉMATIQUE_CM1, GUIDE_EPS_CM1 | Doublons exacts (md5) — déjà au corpus |
| GUIDE_MATHÉMATIQUES_CP_2022 | Même guide officiel que `g-memp-ma-cp` — non réintégré |
| « Réussir en français au CE2 » (LAHA Éditions) | Commercial — référence seulement |
| « Réussir en mathématique au CE1 » (LAHA Éditions) | Commercial — référence seulement |
| « 100 dictées CM2 » | Anonyme — référence seulement |

## 3. Mesures correctives : modifications

Les mesures correctives priment sur les progressions et sur les guides.

| Domaine | Mesure | Modification |
|---|---|---|
| Français CE1 | Période de révision des diphtongues et doubles consonnes | **Ajout** : 32 fiches et 32 résumés « Unité 0 » (4 semaines × 8 séries), placés en septembre-octobre avant l'unité 1 |
| Français CE1 | Lecture oralisée assistée | **Ajout** : consigne sur les séances de lecture des unités 1 à 6 |
| Français CE1-CE2 | Gestion d'une unité de français | Déjà présent ; guide étendu au CE1/CE2 |
| Français | Exercices structuraux, appareil pédagogique de la lecture | Déjà présents |
| Maths | Calcul mental, planification des dossiers | Déjà présent ; **ajout** du rattachement des fiches aux dossiers et SA des manuels |
| ES, EST | Démarche avec activité préliminaire | **Ajout** sur 1408 fiches d'ES, d'EST, d'EA et d'EPS |
| EA | Planification par renvois | Notée dans le guide `g-mc-2011` |
| EPS | Planification des SA | **Ajout** au guide ; SA des guides officiels reportées dans les programmes |

## 4. Contrôle des SA par les guides

| Cours-matière | SA du guide | Résultat |
|---|---|---|
| CI EPS | 12 | 12 SA ajoutées aux programmes ; 48 fiches alignées, 12 à vérifier |
| CP EPS | 13 | 3 identiques ; 10 titres remplacés par ceux du guide ; 43 fiches alignées, 29 à vérifier |
| CE1 EPS | 6 | 6 SA ajoutées ; 10 fiches alignées |
| CE2 EPS | 5 | 5 SA ajoutées ; 14 fiches alignées, 1 à vérifier |
| CM1 ES, CE1 EST, CE2 EST | 8 / 8 / 9 | Identiques au corpus |

Les guides d'EPS ne donnent pas de barèmes : les barèmes des épreuves d'EPS sont inchangés. Une fiche « à vérifier » porte la mention du titre de SA du guide.

## 5. Cahiers de révision des disciplines d'éveil (originaux)

PDF en Times (Liberation Serif) 14 pt, mise en page compacte, onglet Révisions d'éveil, lien depuis le module CEP, inclus dans le pack.

| Cahier | Sections (ES / EST) | Questions-réponses | Exercices corrigés | Sujets type CEP (barème sur 20) |
|---|---|---|---|---|
| CM2 | 14 (9 / 5) | 80 | 28 | 4 |
| CM1 | 14 (7 / 7) | 70 | 28 | 2 |

Faits d'actualité à la date du 27/10/2026 (président Romuald Wadagni, 109 députés, Sénat, CEDEAO à 12 membres, centrale solaire d'Illoulofin…).
