# -*- coding: utf-8 -*-
"""v2.0 — Clés et signatures de la synchronisation entre niveaux (Ed25519, RFC 8032, Python pur).

* une paire de clés par installation, créée au premier besoin et gardée dans ``<dossier des données>/sync_cle.json``
  (hors de la base : une sauvegarde restaurée sur un autre appareil ne copie pas l'identité de l'installation) ;
* ``empreinte_canonique(obj)`` : JSON trié, sans espaces, UTF-8 (identique à la version JavaScript du protocole) ;
* ``signer`` / ``verifier`` : signature Ed25519 de l'empreinte canonique.
Aucune bibliothèque supplémentaire : le même code fonctionne sur le PC, le serveur et l'application Android.
"""
import hashlib
import json
import os
import secrets
import threading
import uuid

import acces as A
import config

_VERROU = threading.Lock()


def empreinte_canonique(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(obj):
    return hashlib.sha256(obj if isinstance(obj, bytes) else empreinte_canonique(obj)).hexdigest()


def _cle_depuis_graine(graine):
    h = hashlib.sha512(graine).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:], A._encoder(A._multiplier(a, A._BASE))


def signer_octets(graine, message):
    a, prefixe, pub = _cle_depuis_graine(graine)
    r = int.from_bytes(hashlib.sha512(prefixe + message).digest(), "little") % A._L
    R = A._encoder(A._multiplier(r, A._BASE))
    k = int.from_bytes(hashlib.sha512(R + pub + message).digest(), "little") % A._L
    return R + ((r + k * a) % A._L).to_bytes(32, "little")


def cle_publique(graine):
    return _cle_depuis_graine(graine)[2]


def chemin_cle():
    return os.path.join(config.INSTANCE_DIR, "sync_cle.json")


def identite():
    """{installation, graine (octets), cle (hex)} de cette installation (créée au premier appel)."""
    with _VERROU:
        p = chemin_cle()
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            graine = bytes.fromhex(d["graine"])
            if len(graine) != 32:
                raise ValueError
        except (OSError, ValueError, KeyError):
            graine = secrets.token_bytes(32)
            d = {"installation": str(uuid.uuid4()), "graine": graine.hex()}
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, p)
        return {"installation": d["installation"], "graine": graine, "cle": cle_publique(graine).hex()}


def sans_flottants_entiers(v):
    """1.0 -> 1 (récursif) : JavaScript écrit les flottants entiers sans « .0 » ; sans cela la signature d'un paquet
    SCOLARIS ne se vérifie pas dans les applications JS (spec.md, § 8, « Nombres »)."""
    if isinstance(v, float) and v.is_integer() and abs(v) < 2 ** 53:
        return int(v)
    if isinstance(v, dict):
        return {k: sans_flottants_entiers(x) for k, x in v.items()}
    if isinstance(v, list):
        return [sans_flottants_entiers(x) for x in v]
    return v


def signer(paquet):
    """Ajoute la signature Ed25519 de l'installation au paquet (dict) et le renvoie (flottants entiers écrits en entiers)."""
    for k in list(paquet):
        paquet[k] = sans_flottants_entiers(paquet[k])
    ident = identite()
    corps = {k: v for k, v in paquet.items() if k != "signature"}
    paquet["signature"] = signer_octets(ident["graine"], empreinte_canonique(corps)).hex()
    return paquet


def verifier(paquet, cle_hex=None):
    """True si la signature du paquet est valide pour ``cle_hex`` (par défaut : la clé annoncée par l'émetteur)."""
    try:
        cle = bytes.fromhex(cle_hex or (paquet.get("emetteur") or {}).get("cle") or "")
        sig = bytes.fromhex(paquet.get("signature") or "")
    except ValueError:
        return False
    if len(cle) != 32 or len(sig) != 64:
        return False
    corps = {k: v for k, v in paquet.items() if k != "signature"}
    return A.verifier_signature(cle, empreinte_canonique(corps), sig)
