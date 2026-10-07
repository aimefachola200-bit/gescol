# -*- coding: utf-8 -*-
"""
Messages aux parents : espace parent (toujours), WhatsApp (lien pré-rempli, envoi en 1 clic
par le secrétariat) et SMS automatiques via la passerelle HTTP de votre fournisseur.
"""
import json
import urllib.parse
import urllib.request

H = None  # renseigné par configurer()

EVENEMENTS = {
    "absence": "Absence ou retard",
    "paiement": "Paiement reçu",
    "bulletin": "Bulletin disponible",
    "diffusion": "Message de l'école",
}

PARAM_DEFAUTS = {
    "notif_whatsapp": "1",
    "notif_sms": "0",
    "notif_absence": "1",
    "notif_paiement": "1",
    "notif_bulletin": "1",
    "sms_methode": "GET",           # GET | POST_JSON | POST_FORM
    "sms_url": "",
    "sms_corps": "",
    "sms_entete": "",               # ex. « Authorization: Bearer XXXXX »
    "sms_expediteur": "",
}


def configurer(h):
    global H
    H = h


def params():
    v = dict(PARAM_DEFAUTS)
    v.update({k: val for k, val in H.lire_parametres().items() if k in PARAM_DEFAUTS or k.startswith("notif_")})
    return v


def normaliser_tel(tel):
    """Numéro béninois au format international sans « + » : 229 01 XX XX XX XX.
    Les anciens numéros à 8 chiffres reçoivent le préfixe 01 (réforme de novembre 2024)."""
    if not tel:
        return None
    ch = "".join(c for c in str(tel) if c.isdigit())
    if ch.startswith("00"):
        ch = ch[2:]
    if ch.startswith("229"):
        reste = ch[3:]
        if len(reste) == 8:
            reste = "01" + reste
        return "229" + reste if len(reste) == 10 else None
    if len(ch) == 10 and ch.startswith("01"):
        return "229" + ch
    if len(ch) == 8:
        return "22901" + ch
    if 9 <= len(ch) <= 15:  # numéro étranger déjà en format international
        return ch
    return None


def affiche_tel(tel):
    n = normaliser_tel(tel)
    if not n:
        return tel or ""
    if n.startswith("229") and len(n) == 13:
        r = n[3:]
        return "+229 " + " ".join([r[0:2], r[2:4], r[4:6], r[6:8], r[8:10]])
    return "+" + n


def lien_whatsapp(tel, texte):
    n = normaliser_tel(tel)
    if not n:
        return None
    return f"https://wa.me/{n}?text={urllib.parse.quote(texte)}"


# ---------------------------------------------------------------- SMS
def envoyer_sms(tel, texte, p=None):
    """Envoie un SMS par la passerelle configurée. Retourne (ok, message)."""
    p = p or params()
    n = normaliser_tel(tel)
    if not n:
        return False, "numéro invalide"
    if not p.get("sms_url"):
        return False, "passerelle SMS non configurée"
    valeurs = {"telephone": n, "telephone_plus": "+" + n, "message": texte, "expediteur": p.get("sms_expediteur", "")}
    methode = (p.get("sms_methode") or "GET").upper()
    entetes = {"User-Agent": "GESCOL"}
    if p.get("sms_entete") and ":" in p["sms_entete"]:
        k, v = p["sms_entete"].split(":", 1)
        entetes[k.strip()] = v.strip()
    try:
        if methode == "GET":
            url = p["sms_url"]
            for k, v in valeurs.items():
                url = url.replace("{" + k + "}", urllib.parse.quote(str(v)))
            req = urllib.request.Request(url, headers=entetes)
        else:
            corps = p.get("sms_corps") or ""
            if methode == "POST_JSON":
                for k, v in valeurs.items():
                    corps = corps.replace("{" + k + "}", json.dumps(str(v))[1:-1])
                entetes["Content-Type"] = "application/json"
            else:
                for k, v in valeurs.items():
                    corps = corps.replace("{" + k + "}", urllib.parse.quote_plus(str(v)))
                entetes["Content-Type"] = "application/x-www-form-urlencoded"
            req = urllib.request.Request(p["sms_url"], data=corps.encode("utf-8"), headers=entetes, method="POST")
        with urllib.request.urlopen(req, timeout=15) as rep:
            code = rep.status
            contenu = rep.read(500).decode("utf-8", "replace")
        if 200 <= code < 300:
            return True, contenu[:200]
        return False, f"HTTP {code} {contenu[:150]}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:200]


# ---------------------------------------------------------------- envoi aux parents
def destinataires_eleve(eleve):
    """[(parent_id ou None, telephone, whatsapp)] pour un élève (compte parent lié ou téléphone de la fiche)."""
    out = []
    if eleve["parent_id"]:
        p = H.q("SELECT * FROM parents WHERE id=? AND actif=1", (eleve["parent_id"],), un=True)
        if p:
            out.append((p["id"], p["telephone"], p["whatsapp"] or p["telephone"]))
    if not out and (eleve["parent_telephone"] or eleve["parent_whatsapp"]):
        out.append((None, eleve["parent_telephone"], eleve["parent_whatsapp"] or eleve["parent_telephone"]))
    return out


def notifier_eleve(eleve, evenement, sujet, texte, forcer=False, canaux=None):
    """Prévient les parents d'un élève. `canaux` : sous-ensemble de {'portail','whatsapp','sms'} ;
    par défaut, selon les paramètres de l'école. Retourne le nombre de messages créés."""
    p = params()
    if not forcer and p.get("notif_" + evenement, "1") != "1":
        return 0
    if canaux is None:
        canaux = {"portail"}
        if p.get("notif_whatsapp") == "1":
            canaux.add("whatsapp")
        if p.get("notif_sms") == "1":
            canaux.add("sms")
    n = 0
    maint = H.maintenant()
    ecole = H.config.ECOLE.get("sigle") or H.config.ECOLE.get("nom")
    texte_court = f"{ecole} : {texte}"
    for parent_id, tel, wa in destinataires_eleve(eleve):
        if "portail" in canaux and parent_id:
            H.ex("INSERT INTO messages (parent_id, eleve_id, sens, sujet, texte, auteur_id, cree_le) VALUES (?,?,?,?,?,?,?)",
                 (parent_id, eleve["id"], "ecole", sujet, texte, _auteur(), maint))
            n += 1
        if "whatsapp" in canaux and normaliser_tel(wa):
            H.ex("INSERT INTO notifications (parent_id, eleve_id, telephone, canal, evenement, texte, cree_le) "
                 "VALUES (?,?,?,?,?,?,?)", (parent_id, eleve["id"], normaliser_tel(wa), "whatsapp", evenement, texte_court, maint))
            n += 1
        if "sms" in canaux and normaliser_tel(tel):
            ok, msg = envoyer_sms(tel, texte_court, p)
            H.ex("INSERT INTO notifications (parent_id, eleve_id, telephone, canal, evenement, texte, statut, erreur, cree_le, envoye_le) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (parent_id, eleve["id"], normaliser_tel(tel), "sms", evenement, texte_court,
                  "envoye" if ok else "echec", None if ok else msg, maint, maint if ok else None))
            n += 1
    return n


def _auteur():
    try:
        from flask import g
        return g.user["id"] if g.get("user") else None
    except Exception:  # noqa: BLE001
        return None
