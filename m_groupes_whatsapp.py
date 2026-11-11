# -*- coding: utf-8 -*-
"""v1.9 — Groupes WhatsApp des directeurs et des enseignants, pour partager les informations.

* École (SCOLARIS / SCOLARIS Public) : groupe des enseignants de l'école, groupe de tout le personnel.
* Circonscription scolaire : groupe des directeurs, des enseignants (toutes les écoles ou une zone), des CP.
* DDEMP : groupe des directeurs, des enseignants, des chefs de circonscription (CCS), des CP.

WhatsApp n'autorise aucune application à créer un groupe ni à y ajouter des membres à la place de son
administrateur. Le module fait donc tout le reste :
* il rassemble les numéros (personnel des écoles transmis à la CS / DDEMP, fiche de l'école, CP des zones…),
  les met au format international du Bénin (+229 01 XX XX XX XX) et signale les numéros invalides ;
* il produit le fichier de contacts (.vcf) : une fois les contacts importés dans le téléphone, l'écran
  « Nouveau groupe » de WhatsApp ne propose QUE ceux qui ont un compte WhatsApp — il suffit de tout cocher ;
* il envoie le lien d'invitation du groupe personne par personne (wa.me) et garde la trace des envois ;
* il prépare des messages prêts à l'emploi (convocation, visite, rappel, information…) à poster dans le groupe
  ou à envoyer personnellement, l'un après l'autre.
Les numéros restent dans la base de l'application.
"""
import json
import urllib.parse
from datetime import date

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

import config
from db import ex, q

SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_groupes (
    ecole_id INTEGER NOT NULL DEFAULT 0, cle TEXT NOT NULL, nom TEXT, lien TEXT, message TEXT, modele TEXT, serie TEXT,
    maj TEXT, PRIMARY KEY (ecole_id, cle));
CREATE TABLE IF NOT EXISTS wa_contacts (
    ecole_id INTEGER NOT NULL DEFAULT 0, groupe TEXT NOT NULL, personne TEXT NOT NULL, sans_whatsapp INTEGER DEFAULT 0,
    envoye_le TEXT, PRIMARY KEY (ecole_id, groupe, personne));
"""

ROLES_ECOLE = ("admin", "fondateur", "directeur")
ROLES_JUR = ("admin", "responsable", "chef_service", "cp")

AUDIENCES_ECOLE = {"enseignants": "Enseignants de l'école", "personnel": "Tout le personnel de l'école"}
AUDIENCES_CS = {"directeurs": "Directeurs des écoles", "enseignants": "Enseignants des écoles",
                "cp": "Conseillers pédagogiques"}
AUDIENCES_DDEMP = {"directeurs": "Directeurs des écoles", "enseignants": "Enseignants des écoles",
                   "ccs": "Chefs de circonscription (CCS)", "cp": "Conseillers pédagogiques"}

MODELES = {
    "convocation": ("Convocation (réunion, UP, formation)",
                    "*CONVOCATION — {emetteur}*\n\n{salut}{public} sont convoqués à {objet} le *{date}* à *{heure}* à {lieu}.\n"
                    "{precisions}\nPrésence obligatoire.\n\n{signataire}"),
    "visite": ("Annonce de visite de classe",
               "*VISITE PÉDAGOGIQUE — {emetteur}*\n\n{salut}{objet} est prévue le *{date}*{heure_a}.\n{precisions}\n"
               "Merci de préparer les documents pédagogiques (cahier journal, fiches, emploi du temps, registre d'appel).\n\n{signataire}"),
    "rappel": ("Rappel de document à rendre",
               "*RAPPEL — {emetteur}*\n\n{salut}{objet} est attendu au plus tard le *{date}*.\n{precisions}\n\n{signataire}"),
    "transmission": ("Demande de transmission des données",
                     "*{emetteur} — Transmission des données*\n\n{salut}Merci de transmettre les données de votre école avant le *{date}* "
                     "(application → Données → Transmission à la circonscription).\n{precisions}\n\n{signataire}"),
    "resultats": ("Résultats / statistiques", "*RÉSULTATS — {emetteur}*\n\n{salut}{objet}\n{precisions}\n\n{signataire}"),
    "information": ("Information générale", "*INFORMATION — {emetteur}*\n\n{salut}{objet}\n{precisions}\n\n{signataire}"),
    "libre": ("Message libre", "{salut}{precisions}"),
}
PUBLIC = {"directeurs": "Les directeurs et directrices", "enseignants": "Les enseignants et enseignantes",
          "personnel": "Tous les membres du personnel", "cp": "Les conseillers pédagogiques",
          "ccs": "Les chefs de circonscription scolaire"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]


def date_longue(iso):
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return ""
    return f"{JOURS[d.weekday()]} {d.day}{'er' if d.day == 1 else ''} {MOIS[d.month - 1]} {d.year}"


def texte_modele(m, emetteur, signataire, public, personne=None):
    """Texte d'un message prêt à l'emploi (personne : dict avec nom et ecole pour un envoi personnel)."""
    m = m or {}
    v = {k: str(m.get(k) or "").strip() for k in ("objet", "date", "heure", "lieu", "precisions")}
    gabarit = MODELES.get(m.get("type") or "convocation", MODELES["information"])[1]
    salut = ""
    if personne:
        qui = personne.get("nom") or "Madame, Monsieur"
        salut = f"Bonjour {qui}" + (f" ({personne['ecole']})" if personne.get("ecole") else "") + ",\n"
    t = (gabarit.replace("{salut}", salut).replace("{emetteur}", emetteur).replace("{signataire}", signataire)
         .replace("{public}", public).replace("{objet}", v["objet"] or "…").replace("{date}", date_longue(v["date"]) or "…")
         .replace("{heure_a}", f" à {v['heure']}" if v["heure"] else "").replace("{heure}", v["heure"] or "…")
         .replace("{lieu}", v["lieu"] or "…").replace("{precisions}", v["precisions"]))
    while "\n\n\n" in t:
        t = t.replace("\n\n\n", "\n\n")
    return t.strip()


def role_de(fonction):
    f = (fonction or "").lower()
    if "adjoint" in f:
        return "adjoint"
    if "direct" in f:
        return "directeur"
    if any(x in f for x in ("enseign", "institut", "educat", "éducat", "maitre", "maître", "professeur", "animat")):
        return "enseignant"
    return "autre"


def vcard(personnes, prefixe, org):
    def e(s):
        return str(s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    lignes = []
    for p in personnes:
        lignes += ["BEGIN:VCARD", "VERSION:3.0",
                   "FN:" + e(f"{prefixe} {p['nom']}" + (f" ({p['ecole']})" if p.get("ecole") else "")),
                   "N:" + e(p["nom"]) + ";" + e(prefixe) + ";;;", "ORG:" + e(org),
                   "TITLE:" + e(p.get("role_lib") or ""), "TEL;TYPE=CELL:+" + p["num"], "END:VCARD"]
    return "\r\n".join(lignes) + "\r\n"


# ======================================================================== module
def enregistrer(app, H):
    H.schema(SCHEMA)
    notif = H.notif

    def jur():
        return config.juridiction()

    def autorise():
        if not g.get("user"):
            return False
        role = g.get("role_reel") or g.user["role"]
        return role in (ROLES_JUR if jur() else ROLES_ECOLE)

    def cle_ecole():
        return 0 if jur() else H.eco()

    def audiences():
        if not jur():
            return AUDIENCES_ECOLE
        return AUDIENCES_DDEMP if H.jur_niveau() == "ddemp" else AUDIENCES_CS

    def emetteur_signataire():
        if jur():
            s = H.jur_structure()
            nom = (s["sigle"] or s["nom"]) if s else "Circonscription scolaire"
            sign = (s["responsable_titre"] or ("Le Chef de la Circonscription Scolaire" if H.jur_niveau() == "cs"
                                               else "Le Directeur Départemental")) if s else ""
            if g.user["role"] == "cp":
                sign = "Le Conseiller Pédagogique"
            return nom, sign
        e = g.get("ecole")
        nom = (e["nom"] if e else None) or config.ECOLE.get("nom") or "L'école"
        titre = (e["directeur_titre"] if e and "directeur_titre" in e.keys() else None) or "Le Directeur"
        if not titre.lower().startswith(("le ", "la ")):
            titre = ("La " if titre.lower().startswith("directrice") else "Le ") + titre
        return nom, titre

    def personne(cle, nom, tel, ecole="", zone="", cs="", role_lib=""):
        num = notif.normaliser_tel(tel)
        return {"cle": cle, "nom": (nom or "").strip(), "brut": tel or "", "num": num or "", "affiche": notif.affiche_tel(tel) if num else (tel or ""),
                "ecole": ecole or "", "zone": zone or "", "cs": cs or "", "role_lib": role_lib}

    def membres(groupe, cs_id=None, zone_id=None):
        out = []
        if not jur():
            for p in q("SELECT * FROM personnel WHERE actif=1 AND ecole_id=? ORDER BY nom, prenoms", (H.eco(),)):
                r = role_de(p["fonction"])
                if groupe == "enseignants" and r == "autre":
                    continue
                out.append(personne(f"P{p['id']}", f"{p['nom']} {p['prenoms'] or ''}", p["telephone"], role_lib=p["fonction"] or ""))
            return out
        ecs = H.jur_ecoles(cs_id=cs_id, zone_id=zone_id)
        if groupe == "directeurs":
            pers = {}
            for p in H.jur_personnel(cs_id=cs_id, zone_id=zone_id, inclure_agents=False):
                if (p.get("role") == "directeur" or role_de(p.get("fonction")) == "directeur") and p.get("telephone"):
                    pers.setdefault(p["ecole_id"], p)
            for e in ecs:
                p = pers.get(e["id"]) or {}
                nom = e["directeur_nom"] or " ".join(x for x in (p.get("nom"), p.get("prenoms")) if x)
                out.append(personne(f"E{e['id']}", nom, e["directeur_tel"] or p.get("telephone"), e["nom"], e["zone_nom"], e["cs_nom"],
                                    e["directeur_titre"] or "Directeur"))
        elif groupe == "enseignants":
            vus = set()
            for p in H.jur_personnel(cs_id=cs_id, zone_id=zone_id, inclure_agents=False):
                r = p.get("role") or role_de(p.get("fonction"))
                if r not in ("enseignant", "adjoint", "directeur"):
                    continue
                cle = "P" + (p.get("nip") or p.get("matricule") or f"{p['ecole_id']}-{p.get('nom')}-{p.get('prenoms')}")
                if cle in vus:
                    continue
                vus.add(cle)
                out.append(personne(cle, f"{p.get('nom') or ''} {p.get('prenoms') or ''}", p.get("telephone"), p.get("ecole_nom"),
                                    p.get("zone_nom"), p.get("cs_nom"), p.get("fonction") or r))
        elif groupe == "cp":
            sql = "SELECT z.*, c.nom cs_nom FROM jur_zones z JOIN jur_cs c ON c.id=z.cs_id WHERE 1=1"
            args = []
            if cs_id:
                sql += " AND z.cs_id=?"
                args.append(cs_id)
            if zone_id:
                sql += " AND z.id=?"
                args.append(zone_id)
            for z in q(sql + " ORDER BY c.numero, c.nom, z.ordre", tuple(args)):
                out.append(personne(f"Z{z['id']}", z["cp_nom"] or f"CP — {z['nom']}", z["cp_telephone"], "", z["nom"], z["cs_nom"],
                                    "Conseiller pédagogique"))
        elif groupe == "ccs":
            for c in H.jur_cs_liste():
                out.append(personne(f"C{c['id']}", c["ccs_nom"] or f"CCS {c['nom']}", c["telephone"], "", "", c["nom"],
                                    c["ccs_titre"] or "Chef de circonscription"))
        return out

    def reglage(groupe):
        r = q("SELECT * FROM wa_groupes WHERE ecole_id=? AND cle=?", (cle_ecole(), groupe), un=True)
        emetteur, _ = emetteur_signataire()
        d = {"nom": f"{audiences().get(groupe, 'Groupe')} — {emetteur}", "lien": "",
             "message": "Bonjour {nom}. {emetteur} vous invite à rejoindre le groupe WhatsApp « {groupe} » "
                        "pour partager les informations : {lien}", "modele": {"type": "convocation"}, "serie": {}}
        if r:
            d.update({k: r[k] for k in ("nom", "lien", "message") if r[k]})
            for k in ("modele", "serie"):
                try:
                    d[k] = json.loads(r[k]) if r[k] else d[k]
                except ValueError:
                    pass
        return d

    def sauver(groupe, **v):
        d = reglage(groupe)
        d.update(v)
        ex("INSERT INTO wa_groupes (ecole_id, cle, nom, lien, message, modele, serie, maj) VALUES (?,?,?,?,?,?,?,datetime('now','localtime')) "
           "ON CONFLICT(ecole_id, cle) DO UPDATE SET nom=excluded.nom, lien=excluded.lien, message=excluded.message, "
           "modele=excluded.modele, serie=excluded.serie, maj=excluded.maj",
           (cle_ecole(), groupe, d["nom"], d["lien"], d["message"], json.dumps(d["modele"], ensure_ascii=False),
            json.dumps(d["serie"], ensure_ascii=False)))

    def suivi(groupe):
        return {r["personne"]: r for r in q("SELECT * FROM wa_contacts WHERE ecole_id=? AND groupe=?", (cle_ecole(), groupe))}

    def contexte():
        auds = audiences()
        groupe = request.values.get("groupe") or next(iter(auds))
        if groupe not in auds:
            abort(404)
        cs_id = request.values.get("cs", type=int) if jur() else None
        zone_id = request.values.get("zone", type=int) if jur() else None
        if jur() and H.jur_niveau() == "cs" and not cs_id:
            c = H.jur_cs_courante()
            cs_id = c["id"] if c else None
        return groupe, cs_id, zone_id

    def liste(groupe, cs_id, zone_id):
        s = suivi(groupe)
        lst = membres(groupe, cs_id, zone_id)
        for p in lst:
            r = s.get(p["cle"])
            p["wa"] = not (r and r["sans_whatsapp"])
            p["envoye"] = (r["envoye_le"] if r else None) or ""
        return lst

    def retour(groupe, cs_id, zone_id):
        return redirect(url_for("groupes_whatsapp", groupe=groupe, cs=cs_id or None, zone=zone_id or None))

    def lien_invitation(p, d):
        emetteur, _ = emetteur_signataire()
        t = (d["message"] or "").replace("{nom}", p["nom"] or "").replace("{ecole}", p["ecole"] or "") \
            .replace("{groupe}", d["nom"] or "").replace("{lien}", d["lien"] or "").replace("{emetteur}", emetteur)
        return f"https://wa.me/{p['num']}?text={urllib.parse.quote(t)}"

    def marquer(groupe, personne_cle):
        ex("INSERT INTO wa_contacts (ecole_id, groupe, personne, envoye_le) VALUES (?,?,?,datetime('now','localtime')) "
           "ON CONFLICT(ecole_id, groupe, personne) DO UPDATE SET envoye_le=excluded.envoye_le", (cle_ecole(), groupe, personne_cle))

    @app.context_processor
    def ctx_groupes_whatsapp():
        return {"groupes_whatsapp_autorise": autorise}

    @app.route("/groupes-whatsapp")
    @H.connexion_requise()
    def groupes_whatsapp():
        if not autorise():
            abort(403)
        groupe, cs_id, zone_id = contexte()
        lst = liste(groupe, cs_id, zone_id)
        d = reglage(groupe)
        emetteur, signataire = emetteur_signataire()
        apercu = texte_modele(d["modele"], emetteur, signataire, PUBLIC.get(groupe, "Tous"))
        cs, zones = [], []
        if jur():
            cs = H.jur_cs_liste() if H.jur_niveau() == "ddemp" else []
            zones = H.jur_zones(cs_id) if cs_id else []
        prefixe = {"directeurs": "Dir", "enseignants": "Ens", "personnel": "Pers", "cp": "CP", "ccs": "CCS"}.get(groupe, "WA")
        return render_template("groupes_whatsapp.html", aud=groupe, audiences=audiences(), lst=lst, d=d, apercu=apercu,
                               lien_groupe="https://wa.me/?text=" + urllib.parse.quote(apercu), modeles=MODELES, cs=cs,
                               zones=zones, cs_id=cs_id, zone_id=zone_id, prefixe=prefixe, jur=jur(),
                               wa_nb={"total": len(lst), "valides": sum(1 for p in lst if p["num"]),
                                   "wa": sum(1 for p in lst if p["num"] and p["wa"]),
                                   "invites": sum(1 for p in lst if p["num"] and p["wa"] and p["envoye"])})

    @app.route("/groupes-whatsapp/reglages", methods=["POST"])
    @H.connexion_requise()
    def groupes_whatsapp_reglages():
        if not autorise():
            abort(403)
        groupe, cs_id, zone_id = contexte()
        f = request.form
        if "modele_type" in f:
            m = {"type": f.get("modele_type") if f.get("modele_type") in MODELES else "convocation"}
            m.update({k: f.get(k, "")[:600] for k in ("objet", "date", "heure", "lieu", "precisions")})
            sauver(groupe, modele=m)
            flash("Message prêt : vérifiez l'aperçu puis envoyez-le.", "success")
        else:
            lien = f.get("lien", "").strip()[:300]
            if lien and not lien.startswith("https://chat.whatsapp.com/"):
                flash("Le lien d'invitation d'un groupe commence par https://chat.whatsapp.com/ (WhatsApp → groupe → Inviter via un lien).", "warning")
            sauver(groupe, nom=f.get("nom", "").strip()[:120], lien=lien, message=f.get("message", "")[:1000])
            flash("Groupe enregistré.", "success")
        return retour(groupe, cs_id, zone_id)

    @app.route("/groupes-whatsapp/contact", methods=["POST"])
    @H.connexion_requise()
    def groupes_whatsapp_contact():
        if not autorise():
            abort(403)
        groupe, cs_id, zone_id = contexte()
        cle = request.form.get("personne", "")[:120]
        sans = 0 if request.form.get("wa") == "1" else 1
        ex("INSERT INTO wa_contacts (ecole_id, groupe, personne, sans_whatsapp) VALUES (?,?,?,?) "
           "ON CONFLICT(ecole_id, groupe, personne) DO UPDATE SET sans_whatsapp=excluded.sans_whatsapp", (cle_ecole(), groupe, cle, sans))
        return retour(groupe, cs_id, zone_id)

    @app.route("/groupes-whatsapp/inviter/<path:cle>")
    @H.connexion_requise()
    def groupes_whatsapp_inviter(cle):
        if not autorise():
            abort(403)
        groupe, cs_id, zone_id = contexte()
        p = next((x for x in membres(groupe, cs_id, zone_id) if x["cle"] == cle), None)
        if not p or not p["num"]:
            abort(404)
        marquer(groupe, cle)
        return redirect(lien_invitation(p, reglage(groupe)))

    @app.route("/groupes-whatsapp/suivant")
    @H.connexion_requise()
    def groupes_whatsapp_suivant():
        """Invitation suivante (personne joignable, pas encore invitée) ; « message=1 » : message prêt à l'emploi personnel."""
        if not autorise():
            abort(403)
        groupe, cs_id, zone_id = contexte()
        d = reglage(groupe)
        lst = [p for p in liste(groupe, cs_id, zone_id) if p["num"] and p["wa"]]
        if request.args.get("message"):
            cle_serie = json.dumps(d["modele"], sort_keys=True, ensure_ascii=False)
            serie = d["serie"] if d["serie"].get("cle") == cle_serie else {"cle": cle_serie, "faits": []}
            p = next((x for x in lst if x["cle"] not in serie["faits"]), None)
            if not p:
                flash("Le message a été ouvert pour toutes les personnes joignables de la liste.", "success")
                return retour(groupe, cs_id, zone_id)
            serie["faits"].append(p["cle"])
            sauver(groupe, serie=serie)
            emetteur, signataire = emetteur_signataire()
            t = texte_modele(d["modele"], emetteur, signataire, PUBLIC.get(groupe, "Tous"), p)
            return redirect(f"https://wa.me/{p['num']}?text={urllib.parse.quote(t)}")
        p = next((x for x in lst if not x["envoye"]), None)
        if not p:
            flash("Toutes les personnes joignables ont reçu l'invitation.", "success")
            return retour(groupe, cs_id, zone_id)
        marquer(groupe, p["cle"])
        return redirect(lien_invitation(p, d))

    @app.route("/groupes-whatsapp/remise-a-zero", methods=["POST"])
    @H.connexion_requise()
    def groupes_whatsapp_raz():
        if not autorise():
            abort(403)
        groupe, cs_id, zone_id = contexte()
        ex("UPDATE wa_contacts SET envoye_le=NULL WHERE ecole_id=? AND groupe=?", (cle_ecole(), groupe))
        sauver(groupe, serie={})
        flash("Suivi des envois remis à zéro.", "success")
        return retour(groupe, cs_id, zone_id)

    @app.route("/groupes-whatsapp/contacts.vcf")
    @H.connexion_requise()
    def groupes_whatsapp_vcf():
        if not autorise():
            abort(403)
        groupe, cs_id, zone_id = contexte()
        lst = [p for p in liste(groupe, cs_id, zone_id) if p["num"] and p["wa"]]
        if not lst:
            flash("Aucun numéro valide dans cette liste : complétez les numéros de téléphone.", "warning")
            return retour(groupe, cs_id, zone_id)
        emetteur, _ = emetteur_signataire()
        prefixe = {"directeurs": "Dir", "enseignants": "Ens", "personnel": "Pers", "cp": "CP", "ccs": "CCS"}.get(groupe, "WA")
        nom_f = f"contacts-whatsapp-{groupe}.vcf"
        return Response(vcard(lst, prefixe, emetteur), mimetype="text/vcard",
                        headers={"Content-Disposition": f'attachment; filename="{nom_f}"'})
