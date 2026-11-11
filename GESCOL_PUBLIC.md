# GESCOL Public : l'application jumelle pour les écoles publiques

GESCOL existe en deux applications jumelles qui partagent le même programme :

| | GESCOL (écoles privées) | GESCOL Public (écoles publiques) |
|---|---|---|
| Android autonome | `GESCOL-Autonome.apk` | `GESCOL-Public.apk` (icône avec un « P » vert) |
| Windows | `GESCOL-Installation.exe` | `GESCOL-Public-Installation.exe` |
| Adresse sur le PC | http://localhost:5000 | http://localhost:5001 |
| Données sur le PC | dossier `GESCOL` | dossier `GESCOL_Public` |

Les deux peuvent être installées sur le même téléphone ou le même PC sans se gêner.
Elles se téléchargent sur la même page : https://aimefachola200-bit.github.io/gescol/

**Passer une installation existante en édition publique :** ouvrez **Administration**, puis **Paramètres**, puis **Édition**, choisissez « École publique » et enregistrez.

## Ce qui change dans GESCOL Public

- **Tableau de bord :**
  - les indicateurs deviennent « Fonds reçus – subventions et cantine » et « Solde en caisse » ;
  - à côté de « Enregistrer un paiement (cantine) », un bouton « Enregistrer une dépense » est ajouté.
- **Tableau de bord du directeur** (il remplace le tableau du fondateur) :
  - effectifs par classe et par sexe ;
  - fonds de cantine par jour, par mois et par année ;
  - tableau synoptique du personnel ;
  - export PDF et Excel.
- **Finances :**
  - paiements de cantine, impayés de cantine, dépenses et recettes (subventions…), frais de dépôt CEP ;
  - la trésorerie et le bilan sont calculés à partir de ces données ;
  - le paiement en ligne reste disponible pour un autre recouvrement, si besoin.
- **Personnel et gestion de carrière** (elle remplace la paie) :
  - les champs suivants sont ajoutés : NIP, catégorie, grade, indices, dates de prise de service, diplômes, visite d'aptitude, visites CP/CCS, UP, gestion collégiale, note d'évaluation ;
  - les anciennetés sont calculées au 31 décembre ;
  - la date de retraite est calculée à 60 ans pour le grade A, 58 ans pour le B et 55 ans pour le C ;
  - fiche individuelle en PDF ; l'enseignant voit sa carrière dans « Mon espace ».
- **Périmètre de l'enseignant** (éditions privée et publique) : avec son identifiant et son mot de passe, chaque enseignant accède à ses classes (affectations) — élèves, appel, registre, relevés, affichage, évaluations, notes, synthèse, CEP (CM2), cantine, messages aux parents, comptes élèves, épreuves, visites, documents de l'enseignant, sa fiche de carrière — et à sa signature digitale (« Mon espace ») apposée sur les documents qu'il émet ; le domaine du directeur (tableau de bord, tableau synoptique, finances, administration, recensement, données, secrétariat, suppression d'élèves) lui est refusé.
- **Vie de l'école :**
  - **Carte d'identité de l'école :** fiches de recensement primaire et maternelle, rapports de rentrée et de fin d'année EP et EM. Elles sont remplies automatiquement, se corrigent, s'impriment au format officiel (PDF rempli ou vierge), s'exportent en Excel et acceptent le téléversement du scan signé.
  - **Maître de semaine :** planning, journal du jour, visa du directeur, rapport hebdomadaire PDF.
  - **Visites de classe et d'école (CP, CCS) :** fiche de visite, récapitulatif par enseignant.
  - **Patrimoine et ressources :** infrastructures, mobilier, matériel didactique, mouvements, inventaire.
  - **Documents de l'enseignant :**
    - fiches d'évaluation du personnel ;
    - certificats de présence au poste, de prise de service, de travail et de prise en charge ;
    - attestation de direction ;
    - certificat de scolarité.
    - Tous sont pré-remplis.
- **Version 1.6 :** tableau synoptique de l'école (avant le tableau de bord), vivres et stock de la cantine, comité d'évaluation et épreuves, EducMaster maternelle et modèles officiels, suppression des inscrits et des cartes, ligne NIP et griffe sur les certificats, nouvelle règle de retraite (1er jour du trimestre suivant le trimestre de naissance) : voir le [README](README.md).
- **Inchangés :** Scolarité, Évaluations, Examens (CEP), Cantine, Parents, Données, Secrétariat, Administration et « Vérifier un document ».

---

*GESCOL — Conception : Maître Aimé FACHOLA*
