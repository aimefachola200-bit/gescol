# GESCOL Circonscription et GESCOL DDEMP

Ce sont deux applications jumelles de GESCOL, faites pour l'administration scolaire :

| | GESCOL Circonscription | GESCOL DDEMP |
|---|---|---|
| Pour qui | Le CCS (ou l'inspecteur), les CP, les chefs de division et de service (CDS, RH, CDAP, CDAF, CDOSP) | Le directeur départemental et les services (SEC, SEMP, SRH, SPAF, cantines, statistiques, infrastructures) |
| Rassemble | Les écoles de la circonscription, par zone pédagogique | Les circonscriptions du département |
| Android | `GESCOL-Circonscription.apk` (pastille orange « C ») | `GESCOL-DDEMP.apk` (pastille violette « D ») |
| Windows | `GESCOL-Circonscription-Installation.exe` (http://localhost:5002) | `GESCOL-DDEMP-Installation.exe` (http://localhost:5003) |

Tout se télécharge sur la même page : https://aimefachola200-bit.github.io/gescol/

## Première utilisation
1. Connectez-vous avec **admin / admin123**, puis choisissez un nouveau mot de passe.
2. Choisissez le **département**, et pour la Circonscription, la **CS**. Les 118 circonscriptions du Bénin et leurs zones pédagogiques sont déjà enregistrées.
3. Allez dans **Administration**, puis **Utilisateurs**, pour créer les comptes. Les rôles possibles sont : Responsable (CCS ou directeur départemental), Conseiller pédagogique, Chef de division ou de service, Agent.

## Comment les données remontent

**École → Circonscription → DDEMP**

- **Envoi par l'école :** dans GESCOL ou GESCOL Public, l'école ouvre **Données**, puis **Transmission à la circonscription**.
  - Elle télécharge un **fichier .gescol** et l'envoie à la CS (WhatsApp, clé USB, e-mail).
  - Si la CS est en ligne, elle peut aussi cliquer **Envoyer à la CS**.
- **Réception par la CS :** **Transmissions**, puis **Recevoir**, pour importer les fichiers.
  - **Suivi des envois** montre les écoles en retard.
  - On y trouve aussi les **codes d'accès** pour l'envoi en ligne et le lien **WhatsApp de relance**.
- **Envoi de la CS à la DDEMP :** **Transmissions**, puis **Envoyer à la DDEMP** (par fichier ou en ligne).

Le fichier contient : les effectifs, le personnel avec sa carrière, les visites, le CEP, les fiches de recensement, les rapports de rentrée et de fin d'année, le patrimoine et la cantine.

## Nouveautés de la version 1.6

- **Tableau de bord** : en plus des indicateurs existants, le **nombre de classes par cours et par zone pédagogique** (DDEMP : par circonscription), avec détail par école, Excel et PDF.
- **Divisions, modules et attributions** (Services et documents) : chaque division ou service a sa **rubrique conforme à l'AOF** (article, autorité de rattachement, chef, attributions, source) et ses **lignes d'action** de l'année (générées depuis le texte de l'AOF, suivi : état, taux, échéance, responsable), avec les modules de l'application qui la concernent ; plan d'action de la structure, PDF, Excel, import. Les rubriques « rédigées par GESCOL » attendent la saisie du texte officiel (bouton « Saisir le texte de l'AOF »).
- **Unités pédagogiques (UP)** (Animation pédagogique) : nombre d'UP par zone (et par CS pour la DDEMP), RUP et Co-RUP, activités prévues / exécutées, dates, thèmes, pourcentage d'exécution ; Excel, PDF, import.
- **Conseillers pédagogiques** : par CP, nombre de visites opérées, couverture des écoles et des enseignants, synthèse par mois ; Excel, PDF.
- **Modules des écoles ouverts à la CS / DDEMP** : chaque école de la juridiction peut être **ouverte** (Juridiction → Écoles et modules) ; les menus Scolarité, Évaluation (comité d'évaluation, épreuves, statistiques, analyse, bilan annuel, synthèse), CEP (fiches, carte, examen blanc de l'école, **examen blanc CS / DDEMP** et **synthèse des examens par niveau**), Cantine (paiements et **vivres et stock**), Vie de la CS / DDEMP (carte d'identité : recensement et rapports, visites, patrimoine, documents de l'enseignant, **synthèse de l'évaluation CS / DDEMP**, tableau synoptique), Données (import / export, EducMaster maternel et primaire, conversion PDF), Secrétariat, Personnel et carrière, et l'Administration complète (écoles : ajout, modification, suppression ; paramètres ; mise en ligne et sauvegardes ; utilisateurs et affectations avec **comptes directeur et enseignant** ; paiement en ligne ; WhatsApp et SMS ; écoles / CS / DDEMP candidates ; journal) sont disponibles. Les rôles de la juridiction héritent des droits correspondants (responsable → administrateur, chef de division → directeur, CP → directeur hors finances, agent → secrétaire).
- **Cachets et signatures** : **griffe** (cachet rectangulaire du nom) préconçue pour le responsable et chaque service, apposée sur les attestations et certificats ; ligne **NIP** avant le nom sur tous les documents.
- **Tableau synoptique de la CS / DDEMP** (menu principal) : identité de la structure, services et agents, comités, réseau des écoles ; PDF et Excel. Le tableau synoptique de chaque école ouverte reste dans « Vie de la CS / DDEMP ».
- **Aucune école n'est ouverte d'office** : tant que l'utilisateur n'a pas choisi une école (Juridiction → Écoles et modules, ou le sélecteur du menu), les pages des modules d'école affichent « Choisissez une école à ouvrir » ; le bouton « Fermer l'école » referme l'école ouverte. Un compte directeur ou enseignant n'ouvre que son école.
- **Comptes des directeurs et enseignants** (groupe « Directeurs et enseignants », à la place du groupe « Parents » des éditions école) : page `/juridiction/comptes` — liste des comptes avec leur école, zone et classes affectées ; **création rapide d'un compte directeur** pour une école de la juridiction (identifiant proposé `dir-<code école>`, mot de passe provisoire à changer à la première connexion, école ouverte dans les modules si besoin) ; **compte enseignant** rattaché à une école puis affecté à ses classes (bouton « Classes ») ; réinitialisation du mot de passe ; désactivation ; **codes d'accès en PDF** (un bloc par compte) ; **Excel** ; **WhatsApp et SMS aux directeurs et enseignants**. Les pages parents (`/communication`, `/parents`, `/eleves/acces-eleves`) restent accessibles par leur adresse.
- **Le personnel de l'école au Service des Ressources Humaines (RH) de la CS** : l'ancien Service du Personnel et des Affaires financières (CSPAF) devient le **Service des Ressources Humaines** (sigle RH, toujours marqué « hors AOF » ; un service existant est renommé automatiquement) ; ses modules sont ceux du personnel de la juridiction (carrière, aptitude, retraite, agents, attestations) **et** du personnel de l'école ouverte (personnel, carrière, documents de l'enseignant, synoptique du personnel, comptes directeurs / enseignants, messages), comme le SRH de la DDEMP ; les affaires financières relèvent de la Division de l'Administration et des Finances (CDAF). Menus : « Ressources humaines (personnel, carrière) » et « Personnel de l'école (RH) ».
- **Financement** : le groupe « Finances de l'école » propose, quelle que soit l'édition de l'école ouverte, **subventions de l'État et recettes**, **cotisations de cantine** (paiements, impayés), dépenses, frais de dossier CEP, trésorerie, **bilan et budget**, vivres et stock (scolarité et paie seulement pour une école privée). Nouvelle page **Statistiques → Financement des écoles** (`/juridiction/financement`) : par école, par zone pédagogique (et par CS pour la DDEMP) et total — subventions de l'État reçues, autres recettes, cotisations de cantine encaissées et bénéficiaires, frais CEP, dépenses, solde ; budget prévu de l'année ; filtre par année ; Excel et PDF. Les montants viennent des données saisies dans les écoles ouvertes (source « école ouverte ») ou, pour une école non ouverte, de la section cantine du paquet transmis (source « transmission » : cotisations de l'année et bénéficiaires ; subventions et dépenses inconnues).
- **Accès de chaque division à son périmètre** : un compte **chef de service** ou **agent** rattaché à une division (champ « Division / service » du compte dans Administration → Utilisateurs, sinon la fiche agent liée au compte) n'accède qu'aux modules de sa division (Divisions, modules et attributions) et à leurs sous-pages, plus les pages communes (tableau de bord, choix et tableau de bord de l'école ouverte, tableau synoptique, messages aux directeurs et enseignants, divisions, mon compte, vérification) ; toute autre page répond « Hors du périmètre de votre division » et les liens hors périmètre disparaissent du menu. Sans division, le compte accède à toute l'application. Le responsable, l'administrateur, les CP et les comptes directeur / enseignant ne sont pas concernés. La fiche de chaque division montre les comptes rattachés et leur périmètre. Démo : `chef` (DOSP) et `rh` (Ressources humaines), mot de passe `demo1234`.
- La « Région pédagogique » (CRP) n'apparaît plus nulle part.

GESCOL Circonscription et GESCOL DDEMP restent **deux applications distinctes** (fichiers d'installation, dossiers de données et ports différents) ; elles ne sont pas installées ensemble.

- **Version 1.6 (suite)** : tableau synoptique de la CS / DDEMP (identité, personnel, réseau, divisions, comités, calendrier scolaire, thèmes d'UP) ; aucune école ouverte d'office (choisir une école pour utiliser ses modules) ; comptes des directeurs et enseignants (à la place des parents), service RH de la CS, financement (subventions de l'État, cotisations de cantine, bilan et budget, page consolidée), accès de chaque division limité à son périmètre ; calendrier scolaire officiel et thèmes d'UP / conférences / formations groupées (planning DIIP 2026-2027).

## Ce que contiennent les applications

- **Tableau de bord** de la juridiction :
  - nombre d'écoles primaires et maternelles, publiques et privées, et d'espaces enfance ;
  - effectifs par secteur, avec les taux par sexe et l'écart-type ;
  - enseignants : répartition par sexe, manque, surplus ;
  - CEP : taux par zone pédagogique (CS) ou par CS (DDEMP), et taux global ;
  - bilan des visites des CP et du CCS, et alertes.
- **Statistiques :** écoles, effectifs des apprenants (tableaux de la fiche de recensement), enseignants, classes par cours et par zone, **financement des écoles** (subventions de l'État, cotisations de cantine, dépenses, solde, budget).
- **Examens (CEP) :**
  - candidats présentés et admis, taux, et nombre d'écoles ayant présenté des candidats ;
  - écoles de plus de 35 candidats avec un fort taux, et écoles sous 50 % ;
  - **prévision de l'année suivante**, à partir des classes de CM1 ;
  - **frais de relevés**, avec le montant calculé automatiquement.
- **Ressources humaines (personnel et carrière) :**
  - modules : enseignants, directeurs et adjoints FE, directeurs et adjoints ACDPE, ACDPCTD (AME), directeurs et adjoints du privé, CP, CCS, personnel administratif, personnel de soutien ;
  - visites d'aptitude (notes et années), titulaires du CAP et du CEAP (EP / EM) ;
  - **départs à la retraite** à 60, 58 ou 55 ans selon le grade.
- **Animation pédagogique :** visites d'école et de classe, et bilan des activités des CP et du CCS.
- **Fiches des écoles :**
  - fiches de recensement, de rentrée et de fin d'année de chaque école, avec le NIP et l'en-tête du MEMP ;
  - **fiches consolidées** de la CS ou de la DDEMP.
- **Services et documents :**
  - services et attributions (articles 9 à 14), avec un bouton pour ajouter un service oublié ;
  - organigramme ;
  - **cachet et signature de chaque responsable** ;
  - attestations et certificats : présence au poste, travail, direction, prise et reprise de service, AME.

Partout, on peut ajouter, importer et exporter (Excel, PDF) comme dans les autres applications GESCOL.

---

*GESCOL — Conception : Maître Aimé FACHOLA*
