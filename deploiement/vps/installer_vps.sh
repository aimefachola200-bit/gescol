#!/bin/bash
# Installation de GESCOL sur un serveur VPS Ubuntu 22.04 / 24.04 (Contabo, Hostinger, OVH, DigitalOcean…)
# Utilisation (en root), depuis le dossier gescol décompressé sur le serveur :
#     sudo bash deploiement/vps/installer_vps.sh gescol.mon-ecole.bj
# Prérequis : le nom de domaine pointe vers l'adresse IP du serveur (enregistrement DNS de type A).
# Résultat : GESCOL en https (certificat gratuit automatique), redémarrage automatique, sauvegarde quotidienne.
set -euo pipefail
DOMAINE="${1:-}"
[ -n "$DOMAINE" ] || { echo "Indiquez le nom de domaine : sudo bash $0 gescol.mon-ecole.bj"; exit 1; }
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
APP=/opt/gescol
DATA=/var/lib/gescol

echo "==> Paquets système"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip debian-keyring debian-archive-keyring apt-transport-https curl gnupg ufw
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

echo "==> Utilisateur et dossiers"
id gescol >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin gescol
mkdir -p "$APP" "$DATA"
cp -r "$SRC"/. "$APP"/
rm -rf "$APP/instance" "$APP/venv"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --upgrade pip
"$APP/venv/bin/pip" install -r "$APP/requirements.txt"
chown -R gescol:gescol "$APP" "$DATA"

echo "==> Service GESCOL (démarre tout seul, redémarre en cas de panne)"
cat > /etc/systemd/system/gescol.service <<UNIT
[Unit]
Description=GESCOL - gestion d'établissement scolaire
After=network.target

[Service]
User=gescol
WorkingDirectory=$APP
Environment=GESCOL_EN_LIGNE=1
Environment=GESCOL_DATA=$DATA
ExecStart=$APP/venv/bin/waitress-serve --listen=127.0.0.1:8000 --threads=8 wsgi:application
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now gescol

echo "==> Caddy : https automatique pour $DOMAINE"
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAINE {
    encode gzip
    request_body {
        max_size 20MB
    }
    reverse_proxy 127.0.0.1:8000
}
CADDY
systemctl reload caddy || systemctl restart caddy

echo "==> Pare-feu"
ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw --force enable >/dev/null

echo
echo "GESCOL est en ligne : https://$DOMAINE"
echo "Connexion : admin / admin123 (un nouveau mot de passe est demandé tout de suite)."
echo "Données : $DATA (sauvegardes automatiques dans $DATA/sauvegardes)."
echo "Mise à jour : recopiez le nouveau dossier gescol puis relancez ce script (les données sont conservées)."
