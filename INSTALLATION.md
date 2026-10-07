# Installer GESCOL (PC, Android, tablette)

GESCOL fonctionne avec **un serveur** qui garde toutes les données de l'école, et des **appareils** qui s'y
connectent : PC, tablettes et téléphones voient donc les mêmes élèves, notes et paiements.

| Où est le serveur | Avantages | Limites |
|---|---|---|
| **A. Un PC de l'école** | Gratuit, marche sans Internet | Accessible seulement depuis le Wi-Fi de l'école, le PC doit rester allumé |
| **B. En ligne** | Accessible partout, installation complète sur tous les appareils | Internet nécessaire, hébergement (offre gratuite limitée) |

Vous pouvez commencer par A et passer à B plus tard : on copie simplement la sauvegarde.

> **Écoles publiques :** l'application jumelle **GESCOL Public** s'installe de la même façon avec
> `GESCOL-Public.apk` (Android) et `GESCOL-Public-Installation.exe` (Windows). Voir `GESCOL_PUBLIC.md`.

---

## Étape 1 – Fabriquer les fichiers d'installation (une seule fois, ~15 min)

Les fichiers `GESCOL-Installation-1.4.0.exe` (Windows) et `GESCOL-1.4.0.apk` (Android) sont fabriqués
gratuitement par GitHub à partir du dossier `gescol`.

1. Créez un compte gratuit sur **github.com**.
2. Cliquez sur **+ → New repository**. Nom : `gescol`, cochez **Private**, puis **Create repository**.
3. Cliquez sur **uploading an existing file**, glissez **tout le contenu** du dossier `gescol` décompressé,
   puis **Commit changes**.
4. Vérifiez que le fichier `.github/workflows/fabriquer.yml` est bien présent dans le dépôt. Certains navigateurs
   ignorent les dossiers commençant par un point : dans ce cas, **Add file → Create new file**, nommez-le
   exactement `.github/workflows/fabriquer.yml`, collez le contenu du fichier et validez.
5. Onglet **Actions → Fabriquer GESCOL → Run workflow**. Attendez la coche verte (10 à 15 minutes).
6. En bas de la page, rubrique **Artifacts** : téléchargez **GESCOL-Windows** et **GESCOL-Android**
   (ce sont des .zip qui contiennent le .exe et le .apk).

> Sans GitHub : sur un PC Windows avec Python 3.11 et Inno Setup 6, double-cliquez sur
> `packaging\windows\construire_windows.bat`. Pour l'APK, ouvrez `packaging/android` dans Android Studio
> puis **Build → Build APK(s)**.

---

## Étape 2A – Installer le serveur sur un PC de l'école

Choisissez un PC qui reste allumé pendant les heures de cours (secrétariat, direction).

1. Lancez `GESCOL-Installation-1.4.0.exe`.
   Si Windows affiche « Windows a protégé votre ordinateur » : **Informations complémentaires → Exécuter quand même**
   (le programme n'a pas de signature commerciale payante).
2. Laissez cochés **Icône sur le bureau** et **Autoriser les tablettes et téléphones du Wi-Fi**.
   Cochez **Lancer GESCOL au démarrage de Windows** pour le PC serveur.
3. La fenêtre **GESCOL Serveur** s'ouvre : elle affiche l'adresse pour les tablettes (ex. `http://192.168.1.10:5000`)
   et un QR code. **Laissez-la ouverte** (vous pouvez la réduire).
4. Connectez-vous : **admin / admin123**, choisissez un nouveau mot de passe.
5. **Administration → Paramètres de l'établissement** : nom, sigle, adresse, directeur, année scolaire,
   trimestres ou semestres, logo, cachet et signature.
6. **Administration → Utilisateurs** : créez un compte par membre du personnel.

**Conseil important :** demandez à la personne qui gère votre box ou routeur de donner une **adresse IP fixe**
à ce PC (« réservation DHCP »). Sinon l'adresse peut changer après un redémarrage et il faudra la ressaisir
sur les tablettes.

Les données sont dans `%APPDATA%\GESCOL` : elles sont conservées lors d'une mise à jour ou d'une désinstallation.

## Étape 2B – Mettre GESCOL en ligne (accessible partout)

Suivez le guide **[EN_LIGNE.md](EN_LIGNE.md)** : PythonAnywhere (le plus simple), Render ou serveur VPS avec votre
nom de domaine. Les données du PC de l'école se reprennent en un clic (Administration → Mise en ligne et
sauvegardes → Restaurer une sauvegarde). Une seule installation en ligne peut gérer plusieurs écoles
(Administration → Écoles).

---

## Application Android AUTONOME (sans PC, sans Wi-Fi, sans Internet)

`GESCOL-Autonome-1.4.0.apk` contient **toute l'application** : elle fonctionne seule sur le téléphone ou la tablette.
Idéale pour un directeur ou un enseignant qui travaille seul, ou en attendant la mise en ligne.

1. Fabrication : même procédure que l'étape 1 (GitHub → Actions → Fabriquer GESCOL) ; le fichier est dans
   l'artifact **GESCOL-Android-Autonome**.
2. Copiez l'APK sur l'appareil (WhatsApp, câble, clé USB), ouvrez-le, autorisez l'installation.
3. Ouvrez **GESCOL Autonome** (premier démarrage : environ 10 secondes). Connexion : **admin / admin123**,
   puis choisissez votre mot de passe. Renseignez votre école (Administration → Écoles) et commencez.

À savoir :
- Les données restent **dans l'appareil** : deux téléphones autonomes ne partagent pas leurs données.
- **Sauvegardez souvent** : Administration → Mise en ligne et sauvegardes → Télécharger (fichier .zip dans
  « Téléchargements »). Si le téléphone est perdu ou désinstallé sans sauvegarde, les données sont perdues.
- **Transférer** : une sauvegarde de l'appareil se restaure sur le PC de l'école ou sur la version en ligne
  (et inversement) avec « Restaurer une sauvegarde ».
- L'application autonome et l'application « connectée » (GESCOL-1.4.0.apk) peuvent être installées ensemble.
- Sur un **autre PC** sans Wi-Fi commun, installez simplement `GESCOL-Installation-1.4.0.exe` : il fonctionne
  seul sur ce PC de la même manière.
- La conversion PDF → Excel n'est pas disponible dans l'application autonome (elle l'est sur PC et en ligne).

## Étape 3 – Installer sur les appareils

**Tablette ou téléphone Android – application GESCOL (APK)**
1. Copiez `GESCOL-1.4.0.apk` sur l'appareil (WhatsApp, câble, clé USB) et ouvrez-le.
2. Autorisez l'installation depuis cette source si Android le demande. Si Play Protect avertit :
   **Plus de détails → Installer quand même**.
3. Ouvrez **GESCOL** et saisissez l'adresse du serveur : celle de la fenêtre GESCOL Serveur
   (ex. `192.168.1.10:5000`) ou l'adresse en ligne (`https://NOM.pythonanywhere.com`).
4. Pour changer d'adresse plus tard : page de connexion ou **Compte → Changer de serveur**.

Les bulletins, reçus et certificats PDF s'enregistrent dans **Téléchargements** (notification en haut de l'écran).

**Sans APK (Android, iPhone, iPad, autres PC)** : ouvrez l'adresse du serveur dans Chrome, Edge ou Safari,
puis menu **⋮ → Installer l'application** (ou « Ajouter à l'écran d'accueil »). La page `/installer` de GESCOL
explique la manipulation pour chaque appareil.

---

## Étape 4 – Espace parents, paiement en ligne et messages

**Donner l'accès aux parents**
- Fiche d'un élève → **Créer l'accès parent** (le téléphone du parent doit être renseigné), ou
  **Parents → Comptes parents → Créer les accès d'une classe**.
- GESCOL affiche un code provisoire et un bouton **Envoyer par WhatsApp** avec l'adresse de l'espace parents.
- Le parent se connecte avec son numéro de téléphone, choisit son mot de passe, puis voit ses enfants :
  résultats et bulletins **publiés**, absences, reçus, reste à payer, messages de l'école.
- Les bulletins ne sont visibles qu'après **Notes → Résultats → Publier aux parents**.

**Paiement en ligne (Mobile Money, carte)**
1. L'école ouvre un compte marchand sur **fedapay.com** ou **kkiapay.me** (pièces de l'établissement).
2. **Administration → Paiement en ligne** : collez les clés **de test** (sandbox), cochez « Activer », enregistrez.
3. Déclarez l'adresse de notification indiquée sur cette page dans le tableau de bord du service.
4. Faites un paiement d'essai depuis un compte parent, puis passez aux clés réelles (live).
Le paiement en ligne ne fonctionne que si GESCOL est **en ligne** (étape 2B, en https) : un serveur installé
seulement sur le PC de l'école n'est pas joignable par le service de paiement.

**Messages WhatsApp et SMS**
- **Administration → Messages : WhatsApp et SMS** : choisissez quand prévenir les parents (absence,
  paiement reçu, bulletin publié).
- WhatsApp (gratuit) : les messages s'accumulent dans **Parents → Messages et WhatsApp → WhatsApp à envoyer** ;
  un clic ouvre WhatsApp avec le texte prêt, il suffit d'appuyer sur Envoyer.
- SMS (payant) : prenez un fournisseur de SMS en masse proposant une API HTTP, recopiez son adresse d'envoi
  dans les réglages, puis utilisez **Envoyer un SMS de test**.

## Sauvegardes et mises à jour

- **Sauvegarde** : Administration → **Sauvegarde** télécharge un .zip (base + photos + logo).
  Faites-le chaque semaine et gardez une copie hors du PC (clé USB, Google Drive).
- **Restaurer / passer du PC à la version en ligne** : arrêtez GESCOL, copiez le contenu du .zip dans le
  dossier de données (indiqué dans Paramètres), relancez.
- **Mettre à jour** : installez le nouveau `GESCOL-Installation-x.y.z.exe` par-dessus l'ancien, et le nouvel APK
  par-dessus l'ancien. Les données sont conservées.

## Sécurité

- Changez le mot de passe **admin** dès la première connexion et donnez à chacun son propre compte.
- L'APK est signé avec une clé fournie dans le projet (`packaging/android/app/gescol-release.keystore`),
  pratique pour installer directement sur les appareils. **Avant de publier sur le Play Store**, créez votre
  propre clé et ajoutez-la dans GitHub (Settings → Secrets → Actions : `ANDROID_KEYSTORE_B64`,
  `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`).

## En cas de problème

| Symptôme | Solution |
|---|---|
| La tablette affiche « Serveur injoignable » | Même Wi-Fi que le PC ? Fenêtre GESCOL Serveur ouverte ? Adresse IP inchangée ? |
| La tablette n'arrive toujours pas à se connecter | Pare-feu Windows : réinstallez GESCOL en laissant cochée l'option réseau |
| « GESCOL est déjà en marche » / rien ne s'ouvre | Il tourne déjà : icône GESCOL de la barre des tâches, ou ouvrez http://localhost:5000 |
| Mot de passe admin perdu | Un autre administrateur peut le réinitialiser (Administration → Utilisateurs) |
| Erreur au démarrage | Envoyez le fichier `gescol_serveur.log` du dossier de données |

---

*GESCOL — Conception : Maître Aimé FACHE*
