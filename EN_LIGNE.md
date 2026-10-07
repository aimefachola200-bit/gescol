# Mettre GESCOL en ligne (accessible partout, sans le Wi-Fi de l'école)

Une fois en ligne, GESCOL s'ouvre avec une adresse Internet sécurisée, par exemple `https://gescol-cpfa.pythonanywhere.com`.
Directeurs, enseignants, parents et élèves l'utilisent depuis n'importe où : école, maison, téléphone. Il suffit d'avoir Internet.

Le PC de l'école peut rester en **secours**, sans Internet. Voir « Garder le PC de l'école en secours » plus bas.

## Choisir l'hébergeur

| | PythonAnywhere | Render | Serveur VPS |
|---|---|---|---|
| Difficulté | ★ facile | ★★ moyenne | ★★★ technique |
| Coût indicatif | gratuit pour essayer, puis environ 5 $/mois | environ 7 $/mois + disque (carte bancaire) | environ 5 à 10 $/mois |
| Adresse | `nom.pythonanywhere.com` (votre domaine en payant) | `nom.onrender.com` ou votre domaine | votre domaine (`gescol.mon-ecole.bj`) |
| Mise à jour | envoyer les fichiers + « Reload » | automatique à chaque envoi sur GitHub | recopier + relancer le script |
| Conseillé pour | démarrer, une ou deux écoles | plusieurs écoles, mises à jour fréquentes | réseau d'écoles, meilleures performances |

> Les tarifs changent : vérifiez-les sur le site de l'hébergeur avant de payer.
> Le paiement en ligne des parents (FedaPay, KkiaPay) fonctionne seulement quand GESCOL est en ligne en https.

---

## Option 1 : PythonAnywhere (le plus simple)

1. Créez un compte sur **pythonanywhere.com**. L'offre gratuite « Beginner » suffit pour essayer.
   Le nom d'utilisateur choisi donne l'adresse : `https://NOM.pythonanywhere.com`.
2. Onglet **Files** : cliquez sur **Upload a file** et envoyez `gescol.zip`.
3. Onglet **Consoles**, puis **Bash**, et tapez :
   ```
   unzip -o gescol.zip
   mkdir -p ~/gescol-donnees
   pip3.12 install --user -r gescol/requirements.txt
   ```
4. Onglet **Web**, puis **Add a new web app**, **Manual configuration** et **Python 3.12**.
5. Sur la page Web :
   - *Source code* : `/home/NOM/gescol`
   - Cliquez sur le lien *WSGI configuration file*. Remplacez tout son contenu par celui de
     `deploiement/pythonanywhere/wsgi_pythonanywhere.py`, en remplaçant **NOM** par votre nom d'utilisateur.
   - *Static files* : URL `/static/`, dossier `/home/NOM/gescol/static/`
   - Activez **Force HTTPS**, puis cliquez sur **Reload**.
6. Ouvrez `https://NOM.pythonanywhere.com`, connectez-vous avec **admin / admin123** et choisissez tout de suite un nouveau mot de passe.

Avec l'offre gratuite, cliquez tous les 3 mois sur « Run until 3 months from today » dans l'onglet Web, sinon le site s'arrête.

**Mettre à jour :** envoyez le nouveau `gescol.zip`, puis tapez `unzip -o gescol.zip` dans la console Bash, puis cliquez sur **Reload**.
Les données sont dans `gescol-donnees` et sont conservées.

---

## Option 2 : Render (mise à jour automatique depuis GitHub)

1. Mettez le dossier `gescol` dans un dépôt GitHub **privé** (voir INSTALLATION.md, étape 1).
2. Sur **render.com**, cliquez sur **New +**, puis **Blueprint**, puis choisissez le dépôt.
   Le fichier `render.yaml` règle tout : un disque de 1 Go pour les données, le https et le contrôle `/sante`.
3. Validez l'offre proposée. Il faut une offre payante : un disque est obligatoire pour garder les données.
4. Récupérez le mot de passe initial du compte **admin** : service **gescol**, onglet **Environment**,
   variable `GESCOL_ADMIN_MDP`. Connectez-vous avec **admin** et ce mot de passe, puis changez-le.
5. Adresse : `https://gescol-xxxx.onrender.com`. Vous pouvez y relier votre domaine dans **Settings**, rubrique **Custom Domains**.

**Mettre à jour :** envoyez les nouveaux fichiers sur GitHub. Render redéploie tout seul et les données restent sur le disque.

---

## Option 3 : Serveur VPS (votre domaine, le plus puissant)

1. Louez un VPS **Ubuntu 22.04 ou 24.04** avec 1 Go de mémoire au minimum (Contabo, Hostinger, OVH, DigitalOcean…).
2. Chez votre fournisseur de domaine, créez un enregistrement **A** : `gescol.mon-ecole.bj` vers l'adresse IP du VPS.
3. Envoyez `gescol.zip` sur le serveur (WinSCP ou `scp`). Connectez-vous en SSH, puis tapez :
   ```
   unzip gescol.zip && cd gescol
   sudo bash deploiement/vps/installer_vps.sh gescol.mon-ecole.bj
   ```
   Le script installe tout :
   - Python ;
   - le service GESCOL, qui redémarre tout seul ;
   - Caddy, pour le **https automatique et gratuit** ;
   - le pare-feu.
4. Ouvrez `https://gescol.mon-ecole.bj`, connectez-vous avec **admin / admin123** et changez le mot de passe.

Les données sont dans `/var/lib/gescol`, avec une sauvegarde automatique chaque jour dans `/var/lib/gescol/sauvegardes`.

**Mettre à jour :** envoyez le nouveau `gescol.zip`, décompressez-le, puis relancez la même commande. Les données sont conservées.

> Autre possibilité : avec Docker, le `Dockerfile` fourni fonctionne chez tout hébergeur qui accepte Docker.
> Montez un volume sur `/data`.

---

## Reprendre les données du PC de l'école

1. Sur le PC de l'école, ouvrez **Administration**, puis **Mise en ligne et sauvegardes**, puis **Créer une sauvegarde maintenant**, puis **Télécharger**.
2. Sur la version en ligne, connectez-vous en admin et ouvrez la même page. Dans **Restaurer une sauvegarde**, choisissez le fichier, tapez `RESTAURER` et validez.
   Élèves, classes, notes, paiements, photos, logo, cachets, signatures et comptes sont repris.
3. Reconnectez-vous avec les comptes du PC (mêmes identifiants et mêmes mots de passe).

## Changer d'adresse sur les appareils

- **Téléphones, tablettes, autres PC :** ouvrez l'adresse en ligne dans Chrome ou Edge, puis choisissez **Installer l'application**.
- **Application Android (APK) :** sur l'écran de connexion, touchez **Changer de serveur** et saisissez l'adresse `https://…`.
- **Parents et élèves :** envoyez-leur la nouvelle adresse, par exemple depuis la page Parents avec WhatsApp.
- **Paramètres :** dans **Administration**, puis **Paramètres**, indiquez l'adresse publique. Les QR codes des documents seront alors vérifiables de partout.

## Garder le PC de l'école en secours

La version en ligne devient la **version principale**. Le PC de l'école reste utilisable sans Internet, par exemple en cas de coupure.
Ses données sont **séparées** : ce qui est saisi sur le PC n'apparaît pas en ligne, et l'inverse non plus.

- Pour mettre le PC à jour, téléchargez une sauvegarde depuis la version en ligne et restaurez-la sur le PC, par exemple chaque semaine.
- Ce qui a été saisi sur le PC pendant une coupure (appel, paiements…) doit être ressaisi en ligne quand Internet revient.
  Évitez de restaurer une sauvegarde du PC en ligne après cette date : les saisies faites en ligne entre-temps seraient perdues.

## Sécurité en ligne (déjà en place)

- **Connexion chiffrée :** https, avec des cookies de session sécurisés.
- **Blocage des essais :** 15 minutes de blocage après 10 mots de passe faux.
- **Mots de passe :** chaque personne a son propre compte et le mot de passe **admin** doit être changé à la première connexion.
- **Sauvegardes :** une sauvegarde automatique chaque jour (les 14 dernières sont gardées). Téléchargez-en une copie chaque semaine.

---

*GESCOL — Conception : Maître Aimé FACHE*
