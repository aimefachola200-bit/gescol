# GESCOL – Gestion d'établissement scolaire (CPFA)

> **Installer sur PC, Android ou tablette : voir [INSTALLATION.md](INSTALLATION.md).**
> **Mettre en ligne (accessible partout par Internet) : voir [EN_LIGNE.md](EN_LIGNE.md).**
> Ce README décrit le fonctionnement et le lancement en mode développement.

Application web Python (Flask + SQLite) utilisable sur le réseau de l'école.
Modules : élèves et inscriptions, classes, saisie des notes et bulletins,
paiements et reçus, documents officiels avec QR code de vérification.

## Nouveautés de la version 1.6

| Menu | Contenu |
|---|---|
| **Tableau synoptique de l'école** (avant le tableau de bord, éditions privée et publique) | Identité (MEMP, DDEMP, CCS, EPP, CP de zone, zone pédagogique n°, UP, RUP, Co-RUP, année de création, dirigé par, grade et nom du directeur) ; **tableau du personnel enseignant** (matricule, NIP, promotion, catégorie FE / ACDPE / ACDPCTD, fonction, grade A-B-C, indices, cours tenus, anciennetés générale / département / école, dates de prise de service, retraite, dernière formation, diplômes académique et professionnel (CEAP, CAP), visite d'aptitude, note, visites CP/CCS et du directeur, participation à l'UP, gestion collégiale, contact) ; **comité de santé, bureau APE, comité de direction, comités de classe** ; **emplois du temps** officiels (MEMP 2016, CI → CM2, maternelle) modifiables ; **planification annuelle** par cours ; **règlement intérieur** officiel des écoles primaires (préambule, titres, 63 articles) modifiable ; import / export Excel et PDF |
| **Règles de calcul** | Anciennetés au 31 décembre de la première année de l'année scolaire en cours ; retraite à 60 ans (grade A), 58 (B), 55 (C), départ le 1er jour du trimestre qui suit le trimestre de naissance (né de janvier à mars → 1er avril, etc.) |
| **Données → EducMaster** | Onglet **maternelle** (appréciations), **modèles officiels EducMaster** servis tels quels et remplis par GESCOL : modèle d'importation des notes (primaire, 4 feuilles), modèle des élèves par classe (CM2 → maternelle 1, avec NPI et nationalité), modèle des agents ; import de ces modèles |
| **Scolarité / CEP** | Bouton **Supprimer** (ou Retirer) sur les inscrits, suppression par sélection ; suppression de la carte scolaire / carte d'identité |
| **Cantine → Vivres et stock** | Vivres (quantité, qualité, péremption, seuils), entrées / sorties / pertes / inventaires, sortie du jour, récapitulatifs, alertes, PDF, Excel, charger, réinitialiser |
| **Évaluations → Comité d'évaluation, épreuves et grilles** | Membres et qualifications, élaboration des épreuves (situation, consignes, items et barème, PDF sujet et corrigé), grilles de correction / d'évaluation / d'observation |
| **Certificats et cachets** | Ligne **NIP** avant la ligne du nom sur tous les certificats et attestations ; **griffe** (cachet rectangulaire du nom, préconçue à partir du titre et du nom) sur les documents signés ; la « Région pédagogique » (CRP) disparaît de toutes les fiches, seule la Circonscription scolaire reste |
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
| Enseignant | Saisie des notes, résultats, bulletins |

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
- Pas encore de moyenne annuelle ; un enseignant peut saisir les notes de toutes les classes.

---

*GESCOL — Conception : Maître Aimé FACHE*
