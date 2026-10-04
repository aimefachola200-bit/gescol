# GESCOL Circonscription et GESCOL DDEMP

Ce sont deux applications jumelles de GESCOL, faites pour l'administration scolaire :

| | GESCOL Circonscription | GESCOL DDEMP |
|---|---|---|
| Pour qui | Le CCS (ou l'inspecteur), les CP, les chefs de division (CDS, CSPAF, CDAP, CDOSP) | Le directeur départemental et les services (SEC, SEMP, SRH, SPAF, cantines, statistiques, infrastructures) |
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

## Ce que contiennent les applications

- **Tableau de bord** de la juridiction :
  - nombre d'écoles primaires et maternelles, publiques et privées, et d'espaces enfance ;
  - effectifs par secteur, avec les taux par sexe et l'écart-type ;
  - enseignants : répartition par sexe, manque, surplus ;
  - CEP : taux par zone pédagogique (CS) ou par CS (DDEMP), et taux global ;
  - bilan des visites des CP et du CCS, et alertes.
- **Statistiques :** écoles, effectifs des apprenants (tableaux de la fiche de recensement) et enseignants.
- **Examens (CEP) :**
  - candidats présentés et admis, taux, et nombre d'écoles ayant présenté des candidats ;
  - écoles de plus de 35 candidats avec un fort taux, et écoles sous 50 % ;
  - **prévision de l'année suivante**, à partir des classes de CM1 ;
  - **frais de relevés**, avec le montant calculé automatiquement.
- **Personnel et carrière :**
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

*GESCOL — Conception : Maître Aimé FACHE*
