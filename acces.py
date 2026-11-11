# -*- coding: utf-8 -*-
"""v1.9 — Codes d'accès personnels (autorisation d'utiliser l'application), délivrés par le concepteur.

Chaque compte (directeur, enseignant, secrétaire, CCS, CP…) doit, en plus de son mot de passe, avoir reçu un
code d'accès personnel. Le code est la signature numérique (Ed25519) du message
« <APPLICATION>|<identifiant de l'installation>|<identifiant du compte> » : seul le concepteur, qui détient la clé
privée (générateur de codes, jamais publié), peut le produire ; l'application ne contient que la clé publique et
vérifie le code hors ligne. Un code ne sert que pour ce compte, sur cette installation, et n'expire pas.

La vérification Ed25519 est écrite ici en Python pur (RFC 8032), sans bibliothèque supplémentaire : elle fonctionne
aussi dans les applications Android autonomes.
"""
import base64
import hashlib
import re
import secrets

# Clé publique du concepteur (la clé privée correspondante n'est PAS dans le code source)
CLE_PUBLIQUE = bytes.fromhex("35ff091ac3d0bc50f6935d2611321087898e7ef5b90ce401bb40cb73afcbacf7")
DELAI_GRACE_JOURS = 15
# Contrôle des codes d'accès : désactivé pour le moment (demande du concepteur, 19/10/2026).
# Mettre True (ou la variable d'environnement CODES_ACCES=1) pour l'activer de nouveau : rien d'autre à changer.
ACTIF = False
TEL_CONCEPTEUR = "2290196510333"   # Maître Aimé FACHOLA — +229 01 96 51 03 33

# ------------------------------------------------------------------ Ed25519 (vérification seule, RFC 8032)
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _inv(x):
    return pow(x, _P - 2, _P)


def _ajouter(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A = (y1 - x1) * (y2 - x2) % _P
    B = (y1 + x1) * (y2 + x2) % _P
    C = t1 * 2 * _D * t2 % _P
    D = z1 * 2 * z2 % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return E * F % _P, G * H % _P, F * G % _P, E * H % _P


def _multiplier(s, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _ajouter(q, pt)
        pt = _ajouter(pt, pt)
        s >>= 1
    return q


def _x_depuis_y(y, signe):
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if signe else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != signe:
        x = _P - x
    return x


def _decoder(b):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    signe = y >> 255
    y &= (1 << 255) - 1
    if y >= _P:
        return None
    x = _x_depuis_y(y, signe)
    if x is None:
        return None
    return x, y, 1, x * y % _P


def _encoder(pt):
    x, y, z, _ = pt
    zi = _inv(z)
    x, y = x * zi % _P, y * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


_BY = 4 * _inv(5) % _P
_BX = _x_depuis_y(_BY, 0)
_BASE = (_BX, _BY, 1, _BX * _BY % _P)


def verifier_signature(cle_publique, message, signature):
    """True si `signature` (64 octets) est une signature Ed25519 valide de `message` par `cle_publique`."""
    if len(signature) != 64:
        return False
    a = _decoder(cle_publique)
    r = _decoder(signature[:32])
    if a is None or r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + cle_publique + message).digest(), "little") % _L
    return _encoder(_multiplier(s, _BASE)) == _encoder(_ajouter(r, _multiplier(h, a)))


# ------------------------------------------------------------------ codes d'accès
def nouvel_identifiant_installation():
    """Identifiant d'installation lisible : 3 groupes de 4 caractères (ex. K7QM-2HXA-P9TD)."""
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    brut = "".join(secrets.choice(alpha) for _ in range(12))
    return "-".join(brut[i:i + 4] for i in range(0, 12, 4))


def message(appli, installation, identifiant):
    return f"{appli.upper()}|{installation.upper()}|{(identifiant or '').strip().lower()}"


def demande(appli, installation, identifiant):
    """Ligne de demande à envoyer au concepteur (la même que le message signé)."""
    return message(appli, installation, identifiant)


def normaliser_code(code):
    return re.sub(r"[^A-Z2-7]", "", (code or "").upper())


def presenter_code(signature):
    b = base64.b32encode(signature).decode().rstrip("=")
    return "-".join(b[i:i + 5] for i in range(0, len(b), 5))


_cache = {}


def code_valide(appli, installation, identifiant, code):
    """True si le code d'accès correspond à ce compte sur cette installation."""
    c = normaliser_code(code)
    if len(c) != 103:
        return False
    cle = (c, appli, installation, (identifiant or "").lower())
    if cle not in _cache:
        try:
            sig = base64.b32decode(c + "=" * ((-len(c)) % 8))
        except ValueError:
            _cache[cle] = False
        else:
            _cache[cle] = verifier_signature(CLE_PUBLIQUE, message(appli, installation, identifiant).encode("utf-8"), sig)
        if len(_cache) > 5000:
            _cache.clear()
    return _cache[cle]
