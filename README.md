# GESCOL – Gestion d'établissement scolaire (CPFA)

> **Installer sur PC, Android ou tablette : voir [INSTALLATION.md](INSTALLATION.md).**
> **Mettre en ligne (accessible partout par Internet) : voir [EN_LIGNE.md](EN_LIGNE.md).**
> Ce README décrit le fonctionnement et le lancement en mode développement.

Application web Python (Flask + SQLite) utilisable sur le réseau de l'école.
Modules : élèves et inscriptions, classes, saisie des notes et bulletins,
paiements et reçus, documents officiels avec QR code de vérification.

## Nouveautés de la version 1.10

- **Concepteur, fiches, logo de l'école, guide d'utilisation** (v1.32.0) : concepteur Maître Aimé FACHOLA (+229 01 96 51 03 33) en petit en bas des fiches de préparation, résumés, épreuves et cahiers, et très discret sur les documents administratifs ; fiche de préparation imprimée en Times New Roman 14 pt, aux couleurs de la matière avec ses dessins, nom du titulaire en filigrane oblique, prévue pour le recto verso (marges alternées, « Page x / y », chaque fiche sur un recto) ; logo de l'école créé automatiquement (rond ou écusson, symbole, initiales, couleurs) et devise sur les documents et dans l'en-tête ; guide d'utilisation par rôle (page avec recherche, PDF LISEZ-MOI, LISEZMOI.md) ; barèmes d'EPS proposés (vitesse, endurance, sauts, lancer, gymnastique, jeux) avec dispenses et adaptations ; guides officiels français CE1 / CM2 / CP 2022 et mathématiques CI, cahier d'activités et planches du CI ; aucun émoji.
- **Robustesse** (v1.33.0) : examen blanc du CEP en un seul module à deux onglets (commun CS à 9 épreuves, libre de l'école) avec reprise d'une session libre ; mots de passe d'au moins 8 caractères avec lettres et chiffres, changement imposé d'un mot de passe de départ ou faible, blocage d'un compte 15 minutes après 5 essais, fin de session après inactivité ; sauvegardes vérifiées (empreintes SHA-256), rappel après 7 jours sans copie, dossier de secours (clé USB), téléchargement en un clic ; épreuves, fiches et résumés partagés dans l'école avec historique et proposition à la CS / DDEMP ; pages compressées, index de la base, bulletins plus rapides.
- **Synchronisation entre niveaux** (v2.0.0) : école → CS → DDEMP, hors ligne d'abord (protocole commun à toutes les applications) : paquets signés Ed25519 par appareil (clé épinglée au niveau supérieur, nouvelle clé à accepter), incrémentaux (seulement ce qui a changé, suppressions comprises), par fichier .scsync (clé USB, WhatsApp, e-mail) ou en ligne (/sync/push, /sync/pull avec le code d'accès de l'école), inscription par code QR ; montent la transmission (effectifs, personnel, CEP, recensement, rapports…), les bureaux UASCEP et leur vie, l'examen blanc, les licences et officiels du sport, les candidats et concours, les besoins, les accusés de réception, les indicateurs et les épreuves proposées ; descendent les notes de service, circulaires, convocations, échéances, agenda et épreuves proposées ; la CS relaie vers la DDEMP ; conflits champ par champ (le niveau le plus élevé l'emporte, liste à revoir) ; page « Synchronisation » (état, historique, conflits) et « Entités inscrites » (codes QR, fichiers descendants).
- **Maternelle et programme en vigueur d'ES / EPS** (v2.1.0) : les mesures correctives d'Éducation sociale et d'EPS (MEMP / DIP) deviennent le programme du CI au CM2 (84 SA, plus de 600 séquences avec connaissances, techniques et matériel ; fiches, résumés et révisions rattachés ; bandeau « Programme en vigueur : mesures correctives ») ; école maternelle dans la préparation de classe : section des petits / des grands, cinq domaines de développement, progression 2026-2027 (grands d'après la CS Cotonou II, petits proposée), 281 fiches d'activités conçues, emplois du temps, grilles d'observation, repères pour l'éducateur, planification du jour, de la semaine et du mois, classeurs PDF ; « Cette semaine » des classes de maternelle ; inventaire du lot dans docs/inventaire_lot_2026-10-29.md.
- **Déroulements lisibles, Word en .docx** (v2.2.1) : cases du déroulement des fiches importées réparées (deux colonnes du PDF mêlées -> activité APC reconstituée, lignes doublées, textes coupés en fin de case, titres aux mots collés) ; documents Word servis et nommés « .docx » (anciens liens « .doc » redirigés).
- **Petit et grand magasin de la cantine** (v2.4.1) : onglet « Petit et grand magasin » de Vivres et stock ; rations en grammes par élève et par jour (maïs, riz, haricot, huile, sel…), prélèvement hebdomadaire = ration × effectif moyen par jour × 5 jours ouvrables (en kg), consommation calculée jour par jour, retour automatique du reste au grand magasin avant le prélèvement de la semaine suivante ; cahier des menus hebdomadaires, fiche de stock par vivre, bilans journalier, hebdomadaire, mensuel et annuel (écran, PDF, Excel) ; test tests/test_v241.py.
- **v2.5.0** : liste officielle des 9 217 écoles maternelles et primaires du Bénin (département → commune → arrondissement → école, circonscription déduite, chargement par CS/DDEMP sans doublon) ; services du secondaire d'après le décret 2016-427 (DDESTFP, Inspection pédagogique déléguée) ; « Ressources du secondaire » : banque d'épreuves nettoyée et dédoublonnée, thèmes d'exposés (4ᵉ→Tle, romans du programme), fiches de révision.
- **v2.4.9** : mise à jour automatique des applications installées (Windows et Android autonome) : le code est téléchargé en arrière-plan (MAJ-CODE.zip publié avec chaque version), vérifié (SHA-256), puis activé au lancement suivant, sans réinstaller ; retour à l'ancienne version si la nouvelle ne démarre pas ; « Cette semaine » ne reste plus vide quand la SA du jour n'a pas de fiche. Modules `amorcage.py`, `maj_auto.py`, `packaging/fabriquer_maj.py` ; test `tests/test_v249.py`.
- **v2.4.8** : le test `test_v119` (« Cette semaine » du CM1) ne dépend plus du jour du mois ; il bloquait la fabrication des installateurs entre le 8 et le 21 de chaque mois.
- **Hiérarchie du secondaire** (v2.4.7) : éditions `sec_cs` (« Inspection Secondaire ») et `sec_ddestfp` (« DDESTFP »), jumelles de la Circonscription et de la DDEMP : réception des transmissions des collèges, lycées et ETP, effectifs par niveau, examens BEPC/BAC, personnel, exports PDF/Excel ; les applications « Secondaire » transmettent classes, séries, redoublants, orientation et résultats d'examens.
- **Annonces aux enseignants par WhatsApp / SMS** (v2.4.7) : un clic par enseignant, suivi des envois, SMS groupé si une passerelle est configurée.
- **Bouton « Cachets »** (v2.4.6) : dans la barre du haut, à côté du thème : masque les cachets (ronds et griffes) dans tous les PDF téléchargés ou imprimés ; choix mémorisé sur l'appareil.
- **Applications jumelles du secondaire** (v2.4.5) : éditions `sec_privee` et `sec_publique` (variable d'environnement ou `edition.txt`) : « Secondaire » (privé) et « Secondaire Public », avec leurs propres données, port (5005 / 5006, +100 pour SCOLARIS) et fichiers (`*-Secondaire*.apk`, `*-Secondaire*-Installation.exe`). Classes limitées de la 6ème à la Terminale, menus maternelle/primaire, CEP et préparation de classe masqués.
- **Orientation et annonces au personnel** (v2.4.4) : menu Évaluations → « Orientation des élèves » : choix de la série après le BEPC (3ème) et pour la 1ère (2nde), pistes de filières après le baccalauréat, proposition de passage pour les autres classes, d'après les devoirs et compositions saisis (évaluations retenues au choix) ; vœu, avis du conseil, décision, résultat à l'examen ; liste PDF/Excel et fiche d'orientation PDF. « Annonces au personnel » : la direction écrit aux enseignants depuis Communication (destinataire « Enseignants ») ; tests/test_v244.py.
- **Mode sombre et graphiques d'accueil** (v2.4.3) : bouton « ◐ Auto / Clair / Sombre » (mémorisé sur l'appareil, impressions et PDF restent clairs) ; tableau de bord avec effectifs par classe, encaissements mensuels (édition privée) et présences de la semaine ; test tests/test_v243.py.
- **Préparation par classe** (v2.4.2) : onglet « Par classe », de la maternelle au CM2 ; pour chaque classe, par matière, les fiches de préparation (rangées par unité / SA / séance), les résumés, les évaluations et épreuves, les guides et les programmes, avec une recherche unique ; test tests/test_v242.py.
- **Établissement secondaire** (v2.4.0) : collège, lycée et enseignement technique et professionnel, écoles publiques et privées (menu « Établissement secondaire », visible dès que l'école a une classe de la 6ème à la Tle) ; programme (matières, coefficients et volumes horaires par niveau et par série, gabarit à ajuster), professeurs, conseils de classe (moyennes calculées depuis les notes, procès-verbal signé), discipline et sanctions, emplois du temps (conflits de professeur, de salle et de classe, grille) ; examens BEPC / BAC / CAP / BT (centres, candidats, numéros de table, mention et décision proposées, décision du jury, statistiques par série, sexe et centre, convocation signée) ; identité de l'établissement et tableau synoptique (PDF, Excel) pour la direction départementale ; filières, ateliers et stages (attestation signée) ; test tests/test_v235.py.
- **Contrôle et correctifs** (v2.3.4) : dans les applications de circonscription et de DDEMP, « Télécharger PDF / Word » d'une page (pilotage, tableau de bord, sport, synoptique…) donnait la page « Choisissez une école » au lieu du fichier pour les comptes CP, chef de division, directeur et enseignant sans école ouverte : corrigé ; le tableau de bord du pilotage (circonscription, DDEMP) n'échoue plus quand une école transmet ses salles, son mobilier ou ses latrines sous forme de nombre ; test tests/test_v234.py.
- **Listes de classe — accès rapide, exports EducMaster** (v2.3.3) : rubrique « Listes de classe » dans le menu principal, en tuile du tableau de bord et dans le portail de l'enseignant (ses classes seulement), sans passer par les inscriptions : cours (maternelle, CI … CM2) → classe ou toutes les classes du cours → élèves (N° d'ordre, nom, prénoms, sexe, date et lieu de naissance, matricule / EducMaster, nouveau / redoublant, contact du parent), effectifs G / F / T, recherche, tri, lien vers la fiche ; « Télécharger PDF » (en-tête officiel, Times New Roman), « Excel EducMaster (importation) » (modèle officiel des élèves par classe, importable tel quel sur EducMaster), « Excel liste de classe (lisible) », « Imprimer » ; accès rapide aux exports EducMaster existants des notes (par classe) et des agents (liste du personnel) ; CS / DDEMP : école → cours → classe ; lecture seule ; test tests/test_v233.py.
- **Interopérabilité avec les applications JS** (v2.3.2) : paquets de synchronisation vérifiés dans les deux sens avec « Mon école » / CS Pobè (centres et salles du CEP, référentiel des structures, décisions, fiche de rentrée, courrier, fiche signalétique) ; nombres entiers écrits comme en JavaScript (signatures identiques) ; ligne d'école échangée avec le code de l'école et son nom ; fiche signalétique synchronisée (registre « territoire:signaletique ») ; test tests/test_interop_js.py. Le concentrateur de la CS **accepte et convertit le paquet d'école de Mon école** (« POBE-PAQUET-ECOLE » joint aux paquets montants) : effectifs par cours (ou par section en maternelle), salles de classe, personnel, visites, candidats au CEP et compléments des fiches sont repris dans les données de l'école ; les collections et champs sans équivalent sont listés dans le compte rendu d'import (module jur_pobe.py, test tests/test_v232.py).
- **Classes ouvertes : jumelées et multigrades, fiches remplies automatiquement** (v2.3.1) : une classe jumelée (2 cours) ou multigrade (3 cours et plus) compte pour une classe ; classes ouvertes = simples + jumelées + multigrades (regrouper / séparer dans « Classes ») ; recensement, rapports, fiche de rentrée (avec classes autorisées), pilotage et paquets transmis comptent les classes ouvertes ; « Autre combinaison » (ex. CI-CE1) dans les rapports ; fiches et rapports remplis depuis les données, « Télécharger la fiche remplie » (PDF, Excel) ; fiche signalétique remontée, référentiel des structures descendu ; la CS reçoit les classes et les centres CEP des écoles (source et date) ; noms de champs communs avec les applications JS.
- **Territoire et suivi administratif, CEP 2027 — centres et salles** (v2.3.0) : fiche statistique de rentrée (Brouillon → Transmise → Validée CS → Validée département → Clôturée, renvoi motivé) ; courrier administratif entre structures (accusé de lecture, non-lus) ; statut et prochaine visite des visites de classe ; présence du personnel ; fiche signalétique (GPS, autorisation, agrément) ; incidents de discipline ; référentiel des structures ; niveau national en lecture seule et /api/stats.json par jeton ; CEP : point des candidats par centre et des salles de composition (tableau simple et détaillé, 30 à 40 candidats par salle, capacité dépassée), PDF signé et Excel à formules, DDEMP : un bloc par CS.
- **Fiches sur deux pages au plus, anciennetés au 31/12 de la seconde année, filigranes éclatés** (v2.2.2) : anciennetés du personnel calculées au 31 décembre de la seconde année de l'année scolaire (« 2026-2027 » → 31/12/2027) partout ; aucune fiche de préparation ne dépasse une feuille recto verso (14 pt sur une page, puis 14 → 12 pt, déroulement dès la page 1 jusqu'à 10 pt, déroulement resserré jusqu'à 9 pt) ; fiches abîmées du guide CP 2022 allégées ; derniers morceaux d'un filigrane d'auteur tiers retirés ; tests des 150 fiches les plus longues.
- **Tableau de bord CS / DDEMP — programmation et bilan des activités pédagogiques** : pour le trimestre choisi
  (ou le bilan annuel), les **chefs de circonscription (CCS) en premier**, puis les **conseillers pédagogiques** en
  second plan : réalisé / programmé et taux de réalisation (visites de classes et d'écoles, suivis de directeurs,
  séances d'UP, formations, concertations). À la DDEMP : bilan transmis par chaque CS, sinon calcul sur les données reçues.
- **Module « Effectifs »** (Statistiques) : apprenants EP / EM (fiche de recensement), enseignants et directeurs,
  catégories FE, ACDPE, ACDPCTD (AME), Éducateur, Privé, titulaires du CAP (EP, EM) et du CEAP (EP, EM), par sexe ;
  **diplômes académiques et universitaires** (CEP, BEPC, BAC, BAC + 2, Licence, Maîtrise, Master / DEA / DESS,
  Doctorat) ; le **secteur privé à part** (v1.10.2) : les rubriques 1 à 5 ne comptent que le public, et une
  rubrique propre au privé donne écoles, apprenants, enseignants, directeurs, CAP / CEAP des écoles privées ;
  les **catégories d'âge** des apprenants du primaire (v1.10.3), de « moins de 5 ans » à « 16 ans et plus »,
  par sexe et par cours (CI … CM2), avec pourcentages, âge moyen et écart type (public, et privé à part) ;
  les **écoles maternelles par section** (v1.10.4), section des petits (SP) et des grands (SG), par sexe : tableau 3
  de la fiche de recensement (catégories d'âge, pourcentages, âge moyen, écart type), rapport de rentrée EM et fiche
  de fin d'année EM (début, fin, besoin spécifique, abandons), public et privé à part ;
  par circonscription (DDEMP), par zone pédagogique (CS) ou par école ; une **courbe** par tableau ; Excel.
  Rattaché aux divisions des statistiques / de l'organisation scolaire et des ressources humaines.
- **Saisie manuelle sans Excel** (v1.11.0, CS et DDEMP) : onglet « Saisie manuelle (sans Excel) » — les six fiches
  officielles de chaque école remplies à la main (mêmes calculs, contrôles et PDF) ; état nominatif du personnel
  (directeur, adjoints, enseignants, administratifs, soutien) repris dans la gestion de carrière ; directeurs des écoles.
- **Caméra avant / arrière fiable** (v1.10.10) : bascule par choix de l'appareil (avant / arrière d'après son nom).
- **Correctif PC (v1.10.9)** : l'installateur Windows embarque tous les modules (page d'accueil en « Internal Server
  Error » sur PC depuis la 1.8) ; dernier filet d'erreurs en français.
- **Erreurs et diagnostic** (v1.10.8) : page d'erreur en français (au lieu de « Internal Server Error ») avec envoi
  du rapport par WhatsApp, fichier erreurs.log, page /diagnostic ; Android : cache vidé après chaque mise à jour.
- **CEP : candidats et réussite selon les fiches** (v1.10.7) : rubrique 9 du recensement, annexe CEP de la fin
  d'année ou module CEP ; candidats par sexe et %, parité, présence, réussite par sexe, écart type des écoles ;
  par CS, zone ou école ; public et privé à part.
- **Rubriques des fiches consolidées** (v1.10.6) : toutes les rubriques des fiches (recensement, rentrée, fin
  d'année), Oui / Non, choix, nombres avec moyenne et écart type ; par CS, zone ou école ; public et privé à part.
- **Graphiques au choix** (v1.10.6) : courbe, histogramme, barres empilées, aires ou points.
- **Module « Écoles : nombre, structure pédagogique et équipements »** (v1.10.6) : classes autorisées / ouvertes,
  simples / jumelées / multigrades, moyennes et écarts types, eau (dont puits), électricité et autres équipements ;
  par CS, zone ou école ; public et privé à part ; courbes ; Excel.
- **Module « Infrastructures et mobilier »** (v1.10.5) : salles de classe par état, commodités, mobilier du primaire
  avec places assises et déficit, mobilier de la maternelle, manuels par élève ; recensement, rentrée ou fin d'année ;
  par CS, zone ou école ; public et privé à part ; courbes ; Excel.
- **Tableaux globaux des fiches** (Fiches des écoles) : pour la fiche de recensement (EP, EM) et les rapports de
  rentrée et de fin d'année (EP, EM), chaque rubrique chiffrée (infrastructures, locaux, mobilier, équipements,
  effectifs, finances…) avec une colonne par CS (DDEMP) ou par zone (CS) et le total ; Excel de toutes les rubriques.

## Nouveautés de la version 1.9.2

- Le **code d'accès personnel** est **désactivé pour le moment** : l'application s'ouvre comme avant, sans code ni
  bandeau. Le mécanisme reste prêt (acces.py : ACTIF = True, ou variable d'environnement CODES_ACCES=1, pour le réactiver).

## Nouveautés de la version 1.9.1

- **Garde-fou de la saisie des notes** (saisie des évaluations et notes par période) : chaque matière se saisit en
  deux cases, la **note principale** et la **note de performance** (case « P », sur 2) ; la note retenue est leur
  somme. Le perfectionnement n'est accordé qu'à partir de 10 (en dessous, la note reste telle quelle, performance 0) ;
  la somme ne dépasse jamais 20 (19 → performance 1 au plus). La case passe au **rouge** dès que la note principale
  atteint 20 (20/20 n'est possible qu'avec la performance), qu'une performance accompagne une note inférieure à 10,
  que la performance dépasse 2 ou que la somme dépasse 20 ; ces valeurs sont refusées à l'enregistrement.
- **Code d'accès personnel** : chaque compte doit saisir, une fois, le code délivré par le concepteur (Maître Aimé
  FACHOLA, +229 01 96 51 03 33). Le code est lié au compte et à l'installation, n'expire pas, et se demande en un toucher par WhatsApp depuis
  la page « Code d'accès » ; l'administrateur ou le directeur envoie toutes les demandes et colle tous les codes en une
  fois (« Codes d'accès »). Délai de 15 jours après la mise à jour, puis blocage des comptes sans code. Le code est
  une signature numérique : seul le générateur du concepteur, qui n'est pas publié, peut le produire.

## Nouveautés de la version 1.9

- **Groupes WhatsApp** (menu « Groupes WhatsApp ») pour partager les informations :
  - école : groupe des enseignants, groupe de tout le personnel ;
  - circonscription scolaire : directeurs, enseignants (toute la CS ou une zone pédagogique), conseillers pédagogiques ;
  - DDEMP : directeurs, enseignants, chefs de circonscription, conseillers pédagogiques (filtre par CS et par zone).
  
  Les numéros (fiche de l'école, personnel transmis par les écoles, CP des zones) sont mis au format +229 01 XX XX XX XX ;
  le fichier de contacts (.vcf) fait apparaître dans « Nouveau groupe » de WhatsApp les seules personnes qui ont un
  compte ; le lien d'invitation est envoyé personne par personne avec suivi ; messages prêts à l'emploi (convocation,
  visite de classe, rappel, demande de transmission, résultats, information) à poster dans le groupe ou à envoyer
  à chacun, l'un après l'autre. WhatsApp n'autorise aucune application à créer le groupe à la place de son
  administrateur : la page guide les trois gestes à faire dans WhatsApp.

## Nouveautés de la version 1.8

- **Accueil par rôle** : grandes tuiles des actions principales du rôle connecté (directeur, secrétariat, comptabilité,
  fondateur ; CCS, CP et chefs de service dans les applications CS et DDEMP), avec l'état des sauvegardes.
- **« Ma classe »** (enseignant, ouvert directement à la connexion) : appel du jour, absences de la semaine, dernière
  évaluation (taux de réussite, notes manquantes), prochaines évaluations, élèves à suivre (absences répétées,
  non-maîtrise), boutons « Faire l'appel », « Saisir les notes », « Groupes de remédiation ».
- **Appel rapide** : un toucher sur le nom fait passer présent → absent → retard ; compteurs en direct, « Tous présents ».
- **Saisies hors ligne** : l'appel et les notes enregistrés sans réseau sont gardés sur l'appareil et envoyés
  automatiquement au retour de la connexion (badge « saisie(s) gardée(s) »). Les pages de classe restent consultables
  hors ligne.
- **Mise à jour depuis l'application** : un bandeau signale la nouvelle version publiée sur GitHub et propose le
  téléchargement de l'installateur ou de l'APK de la bonne édition.
- **Groupes de remédiation** après chaque évaluation (/evaluations/<n>/remediation, PDF, Excel) : par matière,
  soutien intensif (< 7), consolidation (7 à < 10), maîtrise (10 à < 15), approfondissement / tuteurs (≥ 15) ;
  maternelle : NA / ECA / A ; activités proposées par discipline, élèves en non-maîtrise, matières à renforcer.
- **Alertes de pilotage** (CS / DDEMP, /juridiction/alertes et résumé au tableau de bord) : écoles sans transmission
  ou sans transmission depuis 30 jours, manque d'enseignants, classes pléthoriques, écoles non visitées ce trimestre,
  retard des CP / CCS sur leur programmation, séances d'UP prévues et non tenues.

## Nouveautés de la version 1.7

| Menu | Contenu |
|---|---|
| **En-tête officiel** (GESCOL Autonome et GESCOL Public) | Emblème du MEMP (armoiries, « Ministère des Enseignements Maternel et Primaire », République du Bénin) en tête de la fiche d'inscription au CEP, des certificats et attestations, des bulletins, des fiches et listes de l'école ; **armoiries à la place du logo** sur la carte scolaire du candidat ; **carte d'identité scolaire** de l'élève refaite avec l'en-tête officiel |
| **Communes et villages** | Référentiel des unités administratives locales : 12 départements, 77 communes, 546 arrondissements, **5 290 villages et quartiers de ville** ; listes en cascade dans les formulaires (département → commune → arrondissement → village, lieu de naissance, résidence des parents, adresse de l'école) |
| **CEP** | **Signature digitale du parent** (au doigt ou à la souris) imprimée sur la fiche d'inscription au CEP et sur la fiche de renseignements |
| **Appareil photo** | Caméra avant / arrière sur toutes les prises de vue ; dans les applications Android, le bouton photo propose l'appareil photo (avant ou arrière) ou la galerie, y compris dans l'application légère GESCOL.apk |
| **Conseillers pédagogiques** (GESCOL Circonscription et DDEMP) | CP par zone ; programmation trimestrielle des activités ; journal des activités (suivis des directeurs, séances d'UP, formations groupées, conférences, concertations, autres activités) ; **bilan trimestriel et annuel des activités pédagogiques, niveau zone et niveau CS**, selon le canevas (1. réseau d'animation pédagogique, 2. activités menées, 3. concertations et autres activités, 4. taux de couverture, 5. résultats de l'évaluation d'étape, 6. analyse et problèmes majeurs, 7. commentaires), chiffres calculés et modifiables, analyse proposée ; Enregistrer, Valider, **Charger** (Excel), **Télécharger** (PDF avec en-tête officiel, signature et cachet ; Excel), Recalculer, **Réinitialiser**, **Supprimer** ; bilans envoyés à la DDEMP avec le paquet de la CS |

## Nouveautés de la version 1.6

| Menu | Contenu |
|---|---|
| **Tableau synoptique de l'école** (avant le tableau de bord, éditions privée et publique) | Identité (MEMP, DDEMP, CCS, EPP, CP de zone, zone pédagogique n°, UP, RUP, Co-RUP, année de création, dirigé par, grade et nom du directeur) ; **tableau du personnel enseignant** (matricule, NIP, promotion, catégorie FE / ACDPE / ACDPCTD, fonction, grade A-B-C, indices, cours tenus, anciennetés générale / département / école, dates de prise de service, retraite, dernière formation, diplômes académique et professionnel (CEAP, CAP), visite d'aptitude, note, visites CP/CCS et du directeur, participation à l'UP, gestion collégiale, contact) ; **comité de santé, bureau APE, comité de direction, comités de classe** ; **emplois du temps** officiels (MEMP 2016, CI → CM2, maternelle) modifiables ; **planification annuelle** par cours ; **règlement intérieur** officiel des écoles primaires (préambule, titres, 63 articles) modifiable ; import / export Excel et PDF |
| **Règles de calcul** | Anciennetés au 31 décembre de la seconde année de l'année scolaire en cours (« 2026-2027 » → 31/12/2027) ; retraite à 60 ans (grade A), 58 (B), 55 (C), départ le 1er jour du trimestre qui suit le trimestre de naissance (né de janvier à mars → 1er avril, etc.) |
| **Données → EducMaster** | Onglet **maternelle** (appréciations), **modèles officiels EducMaster** servis tels quels et remplis par GESCOL : modèle d'importation des notes (primaire, 4 feuilles), modèle des élèves par classe (CM2 → maternelle 1, avec NPI et nationalité), modèle des agents ; import de ces modèles |
| **Scolarité / CEP** | Bouton **Supprimer** (ou Retirer) sur les inscrits, suppression par sélection ; suppression de la carte scolaire / carte d'identité |
| **Cantine → Vivres et stock** | Vivres (quantité, qualité, péremption, seuils), entrées / sorties / pertes / inventaires, sortie du jour, récapitulatifs, alertes, PDF, Excel, charger, réinitialiser |
| **Évaluations → Comité d'évaluation, épreuves et grilles** | Membres et qualifications, élaboration des épreuves (situation, consignes, items et barème, PDF sujet et corrigé), grilles de correction / d'évaluation / d'observation |
| **Certificats et cachets** | Ligne **NIP** avant la ligne du nom sur tous les certificats et attestations ; **griffe** (cachet rectangulaire du nom, préconçue à partir du titre et du nom) sur les documents signés ; la « Région pédagogique » (CRP) disparaît de toutes les fiches, seule la Circonscription scolaire reste |
| **Calendrier scolaire officiel** (onglet du tableau synoptique, et menu Scolarité) | Calendrier 2026-2027 de l'arrêté interministériel du 28 juillet 2026 prérempli (pré-rentrée, trimestres, congés, fériés, grandes vacances), modifiable au fil des années : ajouter, modifier, supprimer, recharger, réinitialiser, préparer l'année suivante, import / export Excel, PDF, vue des 12 mois, application au registre des jours de classe |
| **Thèmes d'UP, conférences pédagogiques et formations groupées** (onglet du synoptique, menu Évaluations) | Planning officiel DIIP 2026-2027 (12 thèmes maternelle, 12 primaire, 5 conférences, 5 formations groupées) avec axes, dates et suivi d'exécution ; ajouter, modifier, supprimer, recharger, réinitialiser, Excel, import, PDF |
| **Planification mensuelle (CE-CM)** (onglet du synoptique) | Grille officielle par classe et par mois (français par semaine, dictée, mathématiques, éducation sociale, EST, éducation artistique, EPS), dupliquer le mois précédent, PDF au modèle officiel signé par le titulaire et le directeur, Excel, import |
| **Périmètre de l'enseignant** | Chaque enseignant se connecte avec son identifiant et son mot de passe et accède à **ses classes** : élèves, appel, registres, notes et bulletins, évaluations, CEP, cantine, synthèse, épreuves, emplois du temps et planifications, règlement, calendrier, thèmes d'UP, documents, carrière, messages aux parents ; le domaine du directeur (tableau de bord, synoptique, finances, administration, recensement, données, secrétariat) lui est fermé ; sa **signature digitale** (Mon espace) est apposée sur les documents qu'il émet |
| **Caméra** | Capture photo avec bascule caméra avant / arrière et choix de l'appareil |
| **GESCOL Circonscription / DDEMP** | Voir [GESCOL_ADMINISTRATION.md](GESCOL_ADMINISTRATION.md) : classes par cours et par zone, divisions (rubriques AOF, lignes d'action), unités pédagogiques, conseillers pédagogiques, et tous les modules des écoles ouverts aux applications d'administration |

## Nouveautés de la version 1.3

| Menu | Contenu |
|---|---|
| **Interface** | Menu latéral fixe + zone de travail ; la barre du haut et les indicateurs restent visibles au défilement |
| **Administration → Écoles** | Plusieurs écoles (DDEMP, CS parmi les 118 circonscriptions, UP, zone, directeur/directrice, CCS), cachet officiel généré (arcs, étoiles, bleu ou rouge), signatures digitales ; rôle **fondateur** et tableau consolidé ; affectation des enseignants à leurs classes (et matières au secondaire) |
| **Scolarité** | Inscription complète (EducMaster, NIP, n° de table, centre d'examen, photo fichier ou caméra), import/export Excel des élèves, **registre de présence** par demi-journée, **calendrier** des jours de classe (mercredi = 1 demi-journée), **relevés mensuels de présence** (septembre → juin), **tableau d'affichage** (âges et scolarités par sexe) |
| **Évaluations** | Évaluations diagnostiques / formatives / sommatives d'étape / certificatives, matières cochées, seuil de **maîtrise** (primaire : seule condition de réussite, la moyenne sert au rang), bulletins, rapport, Excel, publication ; **statistiques**, **analyse et rapport**, **tableau d'honneur**, **bilan annuel** (M = (M_O + E_D)/2), **synthèse École / UP / CS** |
| **Examens (CEP)** | Fiche d'inscription au CEP (modèle officiel), **carte scolaire du candidat** recto/verso, **examen blanc CEP** et relevés de notes |
| **Cantine** | Montant par jour et par classe, paiements de la semaine, statistiques par genre, récapitulatifs jour/semaine/mois/année |
| **Données** | Import/export, **EducMaster** (primaire, secondaire), **conversion PDF → Excel/CSV** |
| **Espaces** | Espace élève (`/eleve`), espace enseignant (`/mon-espace`), espace parents (`/parent`), tableau du fondateur (`/fondateur`) |

Non réalisable dans un navigateur : la reconnaissance d'empreinte digitale.

## Modules (version 1.2)

| Menu | Contenu |
|---|---|
| **Scolarité** | Élèves (maternelle, primaire, secondaire), classes, **registre d'appel** (absences, retards, justifications), statistiques d'absences |
| **Notes** | Saisie des notes ou des appréciations (maternelle : Acquis / En cours / Non acquis), observations, résultats, bulletins et livrets PDF, publication aux parents |
| **Finances** | Paiements au guichet et reçus, impayés, **paiements en ligne** (FedaPay, KkiaPay), **trésorerie** (journal de caisse, bilan, budget), **personnel et paie** (CNSS, ITS, VPS, bulletins de paie) |
| **Parents** | Comptes parents, **espace parents** (notes, bulletins, absences, reçus, paiement en ligne, messages), messages WhatsApp en 1 clic et SMS automatiques |
| **Secrétariat** | Registre du courrier arrivé / départ, archives de documents numérisés |
| **Administration** | Paramètres de l'école, utilisateurs, réglages paiement en ligne, WhatsApp/SMS, taux de paie, sauvegarde, journal |

Espace parents : `/parent` (identifiant = numéro de téléphone du parent).

## Installation (Windows)

1. Installez **Python 3.10 ou plus** depuis python.org (cochez « Add Python to PATH »).
2. Décompressez le dossier `gescol`, puis double-cliquez sur **`lancer.bat`**.
   La première fois, il installe Flask et ReportLab (connexion Internet nécessaire).
3. Le navigateur s'ouvre sur http://localhost:5000.
   Connexion : **admin / admin123** – un nouveau mot de passe est demandé tout de suite.

Pour essayer avec des données fictives : `venv\Scripts\python demo.py` **avant** toute vraie saisie
(2 classes, 12 élèves, notes du trimestre 1, paiements).

## Utilisation en réseau

Les autres postes de l'école (et les téléphones) se connectent à `http://ADRESSE-IP-DU-PC:5000`.
Pour que les QR codes imprimés pointent vers ce serveur, définissez l'adresse dans `config.py`
(`URL_PUBLIQUE`) ou dans la variable d'environnement `GESCOL_URL`.
Autorisez le port 5000 dans le pare-feu Windows si nécessaire.

## Paramétrage

Dans l'application : **Administration → Paramètres de l'établissement** (nom, année, périodes, logo,
cachet, signature). `config.py` ne contient que les valeurs par défaut.

### Valeurs par défaut — `config.py`

- `ECOLE` : nom, sigle, adresse, téléphone, nom du directeur, ville (en-têtes de tous les documents).
- `ANNEE_ACTIVE` : année scolaire en cours (ex. `2026-2027`).
- `PERIODES` : `Trimestre 1/2/3` par défaut (remplacez par `Semestre 1/2` si besoin).
- `MODES_PAIEMENT` : Espèces, MTN MoMo, Moov Money, Celtiis Cash, Virement.

Dans `static/ecole/`, déposez éventuellement **`logo.png`**, **`cachet.png`** et **`signature.png`** :
ils apparaissent automatiquement sur les documents.

## Règles de calcul (fichier `calcul.py`)

**Primaire** (CI → CM2)
- Moyenne = moyenne simple des matières notées (le coefficient n'est pas utilisé).
- Décision = règle des 2/3 sur les matières « standard » : ADMIS si le nombre de notes ≥ 10
  atteint ⌈2/3 × nombre de matières standard notées⌉.
- Arts plastiques, Arts vivants et EPS comptent dans la moyenne mais **pas** dans la règle des 2/3
  (modifiable dans la page *Matières*).

**Secondaire** (6ème → Tle)
- Moyenne pondérée Σ(note × coef) / Σ(coef) ; coefficients non appliqués en 6ème et 5ème.
- ADMIS si moyenne ≥ 10.
- Une matière sans note (LV2 non choisie, Philosophie en 4ème…) est ignorée et n'apparaît pas sur le bulletin.

**Saisie** : note de 0 à 20 (virgule acceptée), `D` = dispensé (exclu du calcul), vide = pas encore évalué.
**Rangs** : les élèves à égalité partagent le même rang (« 2e ex æquo »), le suivant est 4e.

Tests : `python -m unittest discover tests`

## Rôles

| Rôle | Accès |
|---|---|
| Administrateur | Tout, dont comptes utilisateurs, matières et journal |
| Directeur | Tout sauf l'administration ; peut annuler un reçu |
| Secrétaire | Élèves, classes, documents officiels |
| Comptable | Paiements, reçus, impayés |
| Enseignant | Son périmètre = ses classes (affectations) : élèves (fiches, photos), appel, registre, relevés, affichage, évaluations, notes et bulletins, synthèse, CEP (CM2), cantine, messages aux parents, comptes élèves, épreuves, visites, documents de l'enseignant, sa carrière, sa signature digitale (« Mon espace », `/mon-espace`) ; le domaine du directeur (tableau de bord, synoptique, finances, administration, données, secrétariat, suppression d'élèves) lui est refusé (403) — module `m_perimetre_enseignant` |

## Documents et vérification

Carte d'élève, certificat de fréquentation, attestation d'inscription, certificat de transfert,
fiche CEP (CM2), bulletins (individuels ou toute la classe en un PDF), reçus.
Chaque document porte un **code unique + QR code**. La page publique `/verifier/CODE` indique
si le document est authentique (un reçu annulé est signalé comme tel).

## Inscription des écoles intéressées

La page publique **`/rejoindre`** (sans connexion) permet à une école de demander à utiliser GESCOL :
établissement, département, effectif, contact, modules souhaités. Un lien y mène depuis la page de connexion.
L'administrateur suit les demandes dans **Écoles candidates** (statut, note interne, export CSV).
Protection anti-robots : champ piège invisible et 5 envois maximum par heure et par adresse IP.
Pour que des écoles extérieures y accèdent, l'application doit être hébergée sur un serveur joignable
depuis Internet (hébergeur Python, ou VPS avec nom de domaine et HTTPS).

## Sauvegarde

Administration → **Sauvegarde** télécharge un .zip complet (base, photos, logo).
En mode développement les données sont dans `instance/` ; dans la version installée, dans `%APPDATA%\GESCOL`.

## Limites de cette version

- Paiement en ligne : nécessite un compte marchand FedaPay ou KkiaPay au nom de l'école et une version
  de GESCOL accessible sur Internet (https). Au guichet, les paiements Mobile Money restent saisis à la main.
- WhatsApp : message pré-rempli, envoyé en 1 clic par le secrétariat (l'envoi 100 % automatique exige
  l'API WhatsApp Business de Meta, non incluse). SMS automatiques : via la passerelle HTTP de votre fournisseur.
- Paie : taux CNSS / ITS / VPS par défaut du Bénin, à faire confirmer par votre comptable (réglables).
- Pas encore de moyenne annuelle ; un enseignant sans aucune affectation voit toutes les classes (affectez-le à ses classes).

---

*GESCOL — Conception : Maître Aimé FACHOLA — +229 01 96 51 03 33*
