# -*- coding: utf-8 -*-
"""Transmissions reçues et envoyées par la Circonscription scolaire (CS) et la DDEMP.

* La CS reçoit les paquets de ses écoles (fichiers .gescol ou envoi en ligne) et envoie SON paquet à la DDEMP.
* La DDEMP reçoit les paquets des CS de son département.

Routes (actives seulement dans les éditions cs / ddemp) :
* /juridiction/transmissions                 jur_transmissions          import de fichiers + paquets reçus
* /juridiction/transmissions/<id>            jur_transmission_detail    détail d'un paquet reçu
* /juridiction/transmissions/suivi           jur_transmission_suivi     état de réception, codes d'accès, relances
                                                                        (?export=xlsx | pdf)
* /juridiction/transmissions/envoi           jur_transmission_envoi     paquet de la CS vers la DDEMP (CS seulement)
* /api/transmission                  POST    api_transmission           réception en ligne (sans session,
                                                                        en-tête X-Gescol-Code)

Droits : lecture = tout utilisateur connecté ; import / envoi = « jur_transmission » ;
codes d'accès = « jur_ecoles » (admin, responsable, chef de service).
"""
import json
import secrets
import threading
import time
from urllib.parse import quote

from flask import Response, abort, flash, g, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import RequestEntityTooLarge

import config
import jur_calc
import jur_format
import m_transmission as MT

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_trans_envois (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    annee TEXT NOT NULL,
    mode TEXT NOT NULL,                   -- fichier | en_ligne
    destination TEXT, nom_fichier TEXT, empreinte TEXT, taille INTEGER,
    nb_ecoles INTEGER, nb_ecoles_donnees INTEGER, nb_agents INTEGER,
    statut TEXT NOT NULL,                 -- ok | erreur
    message TEXT, envoye_le TEXT, envoye_par TEXT
);
"""

# rubriques attendues pour calculer la complétude d'une école
ATTENDUES = {"EP": ("effectifs", "personnel", "cep", "recensement", "rapports"),
             "EM": ("effectifs", "personnel", "recensement", "rapports"),
             "EE": ("effectifs", "personnel", "recensement", "rapports")}
COURTS = {"effectifs": "Effectifs", "personnel": "Personnel", "visites": "Visites", "cep": "CEP",
          "recensement": "Recensement", "rapports": "Rapports", "patrimoine": "Patrimoine", "cantine": "Cantine"}
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sans O/0, I/1/L : code facile à dicter
ECHECS_MAX, FENETRE = 20, 3600
_echecs = {}
_verrou = threading.Lock()


def nouveau_jeton():
    """Code d'accès lisible : XXXX-XXXX-XXXX (≈ 59 bits)."""
    brut = "".join(secrets.choice(ALPHABET) for _ in range(12))
    return f"{brut[:4]}-{brut[4:8]}-{brut[8:]}"


def numero_whatsapp(tel):
    """Téléphone béninois → format international sans « + » (wa.me). None si inutilisable."""
    chiffres = "".join(ch for ch in str(tel or "") if ch.isdigit())
    if chiffres.startswith("00"):
        chiffres = chiffres[2:]
    if chiffres.startswith("229") and len(chiffres) >= 11:
        return chiffres
    if len(chiffres) in (8, 10):
        return "229" + chiffres
    return chiffres if len(chiffres) >= 11 else None


def _echecs_recents(ip):
    now = time.time()
    lst = [t for t in _echecs.get(ip, []) if now - t < FENETRE]
    _echecs[ip] = lst
    return lst


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    def actif():
        if not config.juridiction():
            abort(404)

    def struct():
        return H.jur_structure() or {}

    def cle_reglages():
        return "jur:transmission:ddemp"

    def reglages():
        r = H.doc_lire(cle_reglages(), None)
        return r if isinstance(r, dict) else {}

    def annee_choisie():
        a = request.values.get("annee", "")
        return a if a in H.jur_annees() or (len(a) == 9 and a[4] == "-" and a[:4].isdigit()) else H.jur_annee()

    def infos_haut():
        s = struct()
        if config.EDITION == "cs":
            return [("DDEMP", s.get("departement")), ("CS", s.get("cs"))]
        return [("DDEMP", s.get("departement"))]

    # ------------------------------------------------------------------ état de réception (calculs)
    def rubriques_ecoles(annee):
        """{ecole_id: {section: (source, maj)}} pour l'année."""
        out = {}
        for r in q("SELECT ecole_id, section, source, maj FROM jur_sections WHERE annee=?", (annee,)):
            out.setdefault(r["ecole_id"], {})[r["section"]] = (r["source"], r["maj"])
        return out

    def lignes_ecoles(annee, cs_id=None):
        rub = rubriques_ecoles(annee)
        derniers = {r["ecole_id"]: r for r in q(
            "SELECT ecole_id, MAX(recu_le) recu_le, mode FROM jur_paquets WHERE annee=? AND ecole_id IS NOT NULL "
            "GROUP BY ecole_id", (annee,))}
        lignes = []
        for e in H.jur_ecoles(cs_id=cs_id):
            secs = rub.get(e["id"], {})
            trans = {k: v for k, v in secs.items() if v[0] == "transmission"}
            att = ATTENDUES.get(e["type"], ATTENDUES["EP"])
            pres = [k for k in jur_format.SECTIONS_ECOLE if k in secs]
            p = derniers.get(e["id"])
            date_ = (p["recu_le"] if p else None) or (max(v[1] or "" for v in trans.values()) if trans else None)
            lignes.append({"e": e, "recue": bool(trans) or bool(p), "date": date_ or "",
                           "mode": (p["mode"] if p else ("via CS" if trans else "")), "presentes": pres,
                           "taux": jur_calc.taux(sum(1 for k in att if k in secs), len(att), 0) or 0,
                           "manquantes": [k for k in att if k not in secs]})
        return lignes

    def lignes_cs(annee):
        """DDEMP : une ligne par CS (paquet reçu, écoles, complétude moyenne, rubriques)."""
        ecs = lignes_ecoles(annee)
        recus = {r["cs_id"]: r for r in q(
            "SELECT cs_id, MAX(recu_le) recu_le, COUNT(*) n FROM jur_paquets WHERE annee=? AND emetteur_type='cs' "
            "GROUP BY cs_id", (annee,))}
        out = []
        for c in H.jur_cs_liste():
            mes = [l for l in ecs if l["e"]["cs_id"] == c["id"]]
            p = recus.get(c["id"])
            rub = {k: sum(1 for l in mes if k in l["presentes"]) for k in jur_format.SECTIONS_ECOLE}
            out.append({"c": c, "recue": bool(p), "date": p["recu_le"] if p else "", "envois": p["n"] if p else 0,
                        "nb_ecoles": len(mes), "avec_donnees": sum(1 for l in mes if l["presentes"]),
                        "taux": round(sum(l["taux"] for l in mes) / len(mes), 0) if mes else 0, "rub": rub})
        return out

    def message_relance(nom, annee, cs=True):
        s = struct()
        if cs:
            return (f"Bonjour, la Circonscription scolaire de {s.get('cs', '').title()} n'a pas encore reçu toutes les "
                    f"données de « {nom} » pour l'année scolaire {annee}. Merci de les transmettre depuis GESCOL "
                    f"(menu Données → Transmission à la circonscription), par fichier ou en ligne. Merci.")
        return (f"Bonjour, la DDEMP du {s.get('departement', '')} n'a pas encore reçu la transmission de la "
                f"Circonscription scolaire de {nom.title()} pour l'année scolaire {annee}. Merci de l'envoyer depuis "
                f"GESCOL Circonscription (menu Transmissions → Envoyer à la DDEMP). Merci.")

    def lien_wa(tel, texte):
        n = numero_whatsapp(tel)
        return f"https://wa.me/{n}?text={quote(texte)}" if n else None

    # ------------------------------------------------------------------ réception de fichiers
    @app.route("/juridiction/transmissions", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_transmissions():
        actif()
        resultats = []
        if request.method == "POST":
            if not H.peut("jur_transmission"):
                abort(403)
            fichiers = [f for f in request.files.getlist("fichiers") if f and f.filename]
            if not fichiers:
                flash("Choisissez au moins un fichier de transmission (.gescol).", "danger")
            for f in fichiers[:200]:
                nom = f.filename
                r = {"nom": nom, "ok": False}
                try:
                    octets = f.read(jur_format.TAILLE_MAX + 1)
                    paquet = MT.lire_paquet(octets)
                    r["emetteur"] = (paquet.get("emetteur") or {}).get("nom") or ""
                    r["annee"] = paquet.get("annee")
                    r["rubriques"] = MT.rubriques_du_paquet(paquet)
                    r["nb_ecoles"] = len(paquet.get("ecoles") or [])
                    res = H.jur_importer_paquet(paquet, "fichier", g.user["nom"], len(octets))
                    r.update(ok=True, resume=res)
                    H.journal("jur_transmission_import", f"{nom} : {res.get('ecoles_creees')} créée(s), "
                                                         f"{res.get('ecoles_maj')} mise(s) à jour")
                except jur_format.PaquetInvalide as e:
                    r["erreur"] = str(e)
                except Exception as e:  # noqa: BLE001
                    r["erreur"] = f"Import impossible : {e}"
                resultats.append(r)
            nb_ok = sum(1 for r in resultats if r["ok"])
            if resultats:
                flash(f"{nb_ok} fichier(s) importé(s) sur {len(resultats)}.", "success" if nb_ok == len(resultats) else "warning")
        f = request.args
        sql = ("SELECT p.*, e.nom ecole_nom, c.nom cs_nom FROM jur_paquets p LEFT JOIN jur_ecoles e ON e.id=p.ecole_id "
               "LEFT JOIN jur_cs c ON c.id=COALESCE(p.cs_id, e.cs_id) WHERE 1=1")
        args = []
        if f.get("annee"):
            sql += " AND p.annee=?"
            args.append(f["annee"])
        if f.get("mode") in ("fichier", "en_ligne"):
            sql += " AND p.mode=?"
            args.append(f["mode"])
        if f.get("type") in ("ecole", "cs"):
            sql += " AND p.emetteur_type=?"
            args.append(f["type"])
        if f.get("cs", "").isdigit():
            sql += " AND COALESCE(p.cs_id, e.cs_id)=?"
            args.append(int(f["cs"]))
        if f.get("q"):
            sql += " AND (p.emetteur_nom LIKE ? OR p.emetteur_code LIKE ?)"
            args += [f"%{f['q']}%"] * 2
        paquets = q(sql + " ORDER BY p.id DESC LIMIT 300", tuple(args))
        paquets = [dict(p, res=json.loads(p["resume"] or "{}")) for p in paquets]
        return render_template("jur_transmission_recevoir.html", resultats=resultats, paquets=paquets, f=f,
                               annees=H.jur_annees(), cs=H.jur_cs_liste(), noms=COURTS)

    @app.route("/juridiction/transmissions/<int:pid>")
    @H.connexion_requise()
    def jur_transmission_detail(pid):
        actif()
        p = q("SELECT * FROM jur_paquets WHERE id=?", (pid,), un=True) or abort(404)
        res = json.loads(p["resume"] or "{}")
        ecole = H.jur_ecole(p["ecole_id"]) if p["ecole_id"] else None
        cs = H.jur_cs(p["cs_id"]) if p["cs_id"] else None
        secs = {}
        if ecole:
            secs = {r["section"]: r for r in q("SELECT section, source, maj, length(donnees) taille FROM jur_sections "
                                                "WHERE ecole_id=? AND annee=?", (ecole["id"], p["annee"]))}
        ecoles_cs = []
        if cs:
            ecoles_cs = [l for l in lignes_ecoles(p["annee"], cs["id"])]
        cs_secs = []
        if cs:
            cs_secs = q("SELECT section, maj, length(donnees) taille FROM jur_cs_sections WHERE cs_id=? AND annee=?",
                        (cs["id"], p["annee"]))
        return render_template("jur_transmission_detail.html", p=p, res=res, ecole=ecole, cs=cs, secs=secs,
                               ecoles_cs=ecoles_cs, cs_secs=cs_secs, noms=COURTS,
                               noms_longs=MT.NOMS_RUBRIQUES)

    # ------------------------------------------------------------------ suivi des envois
    @app.route("/juridiction/transmissions/suivi", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_transmission_suivi():
        actif()
        annee = annee_choisie()
        ddemp = config.EDITION == "ddemp"
        if request.method == "POST":
            if not H.peut("jur_ecoles"):
                abort(403)
            act = request.form.get("action")
            if act == "jeton_ecole" and not ddemp:
                e = H.jur_ecole(int(request.form.get("ecole_id") or 0)) or abort(404)
                j = nouveau_jeton()
                ex("UPDATE jur_ecoles SET jeton=? WHERE id=?", (j, e["id"]))
                H.journal("jur_jeton_ecole", e["nom"])
                flash(f"Nouveau code d'accès de « {e['nom']} » : {j} — communiquez-le au directeur "
                      "(l'ancien code ne fonctionne plus).", "success")
            elif act == "jeton_cs" and ddemp:
                c = H.jur_cs(int(request.form.get("cs_id") or 0)) or abort(404)
                j = nouveau_jeton()
                ex("UPDATE jur_cs SET jeton=? WHERE id=?", (j, c["id"]))
                H.journal("jur_jeton_cs", c["nom"])
                flash(f"Nouveau code d'accès de la CS {c['nom']} : {j} — communiquez-le au chef de circonscription "
                      "(l'ancien code ne fonctionne plus).", "success")
            else:
                abort(400)
            return redirect(url_for("jur_transmission_suivi", annee=annee, cs=request.form.get("cs") or None))
        cs_arg = request.args.get("cs", "")
        cs_id = int(cs_arg) if ddemp and cs_arg.isdigit() and H.jur_cs(int(cs_arg)) else None
        voir_codes = H.peut("jur_ecoles")
        export = request.args.get("export")
        if ddemp and not cs_id:
            lignes = lignes_cs(annee)
            for l in lignes:
                l["wa"] = None if l["recue"] else lien_wa(l["c"]["telephone"], message_relance(l["c"]["nom"], annee, cs=False))
            kpi = {"total": len(lignes), "recues": sum(1 for l in lignes if l["recue"]),
                   "ecoles": sum(l["nb_ecoles"] for l in lignes), "avec": sum(l["avec_donnees"] for l in lignes)}
            kpi["taux"] = jur_calc.taux(kpi["recues"], kpi["total"])
            kpi["completude"] = round(sum(l["taux"] for l in lignes) / len(lignes), 0) if lignes else None
            if export in ("xlsx", "pdf"):
                ent = ["N°", "Circonscription", "Paquet reçu", "Date de réception", "Écoles", "Écoles avec données",
                       "Complétude moyenne (%)"] + [COURTS[k] for k in jur_format.SECTIONS_ECOLE]
                rows = [[i, l["c"]["nom"], "Oui" if l["recue"] else "Non", (l["date"] or "")[:16], l["nb_ecoles"],
                         l["avec_donnees"], l["taux"]] + [f"{l['rub'][k]}/{l['nb_ecoles']}" for k in jur_format.SECTIONS_ECOLE]
                        for i, l in enumerate(lignes, 1)]
                return exporter(export, "Réception des transmissions des circonscriptions", annee, ent, rows, kpi,
                                largeurs=[4, 16, 7, 12, 6, 8, 9] + [7] * len(jur_format.SECTIONS_ECOLE))
            return render_template("jur_transmission_suivi.html", mode="cs", lignes=lignes, kpi=kpi, annee=annee,
                                   annees=H.jur_annees(), voir_codes=voir_codes, noms=COURTS, cs_sel=None,
                                   sections=jur_format.SECTIONS_ECOLE, cs=H.jur_cs_liste())
        lignes = lignes_ecoles(annee, cs_id)
        for l in lignes:
            l["wa"] = None if (l["recue"] and not l["manquantes"]) else \
                lien_wa(l["e"]["directeur_tel"] or l["e"]["telephone"], message_relance(l["e"]["nom"], annee))
        kpi = {"total": len(lignes), "recues": sum(1 for l in lignes if l["recue"])}
        kpi["taux"] = jur_calc.taux(kpi["recues"], kpi["total"])
        kpi["completude"] = round(sum(l["taux"] for l in lignes) / len(lignes), 0) if lignes else None
        kpi["completes"] = sum(1 for l in lignes if l["recue"] and not l["manquantes"])
        if export in ("xlsx", "pdf"):
            ent = ["N°"] + (["CS"] if ddemp else []) + ["Zone", "École", "Type", "Secteur", "Directeur", "Téléphone",
                                                        "Reçue", "Date", "Rubriques présentes", "Manquantes", "Complétude (%)"]
            rows = [[i] + ([l["e"]["cs_nom"] or ""] if ddemp else []) +
                    [l["e"]["zone_nom"] or "", l["e"]["nom"], l["e"]["type"], jur_format.SECTEURS.get(l["e"]["secteur"], ""),
                     l["e"]["directeur_nom"] or "", l["e"]["directeur_tel"] or "", "Oui" if l["recue"] else "Non",
                     (l["date"] or "")[:16], ", ".join(COURTS[k] for k in l["presentes"]),
                     ", ".join(COURTS[k] for k in l["manquantes"]), l["taux"]] for i, l in enumerate(lignes, 1)]
            titre = "Réception des transmissions des écoles"
            if cs_id:
                titre += f" – CS {H.jur_cs(cs_id)['nom']}"
            return exporter(export, titre, annee, ent, rows, kpi,
                            largeurs=[4] + ([9] if ddemp else []) + [10, 20, 5, 6, 14, 10, 5, 10, 22, 16, 7])
        return render_template("jur_transmission_suivi.html", mode="ecole", lignes=lignes, kpi=kpi, annee=annee,
                               annees=H.jur_annees(), voir_codes=voir_codes and not ddemp, noms=COURTS,
                               cs_sel=H.jur_cs(cs_id) if cs_id else None, sections=jur_format.SECTIONS_ECOLE,
                               cs=H.jur_cs_liste())

    def exporter(fmt, titre, annee, ent, rows, kpi, largeurs=None):
        s = struct()
        nom = f"etat_reception_{annee}.{fmt}"
        if fmt == "xlsx":
            return H.xlsx.reponse_xlsx(nom, ent, rows, "Réception", [s.get("nom", ""), f"{titre} – {annee}"])
        infos = [("Année scolaire", annee), ("Reçues", f"{kpi['recues']} / {kpi['total']}"),
                 ("Taux de réception", f"{kpi['taux']} %" if kpi.get("taux") is not None else "—"),
                 ("Complétude moyenne", f"{kpi['completude']} %" if kpi.get("completude") is not None else "—")]
        sig = H.pdfs.image_data_url(H.signature("jur:structure:responsable")) if hasattr(H, "signature") else None
        pdf = H.pdfs.document_tableau(
            titre.upper(), ent, rows, sous_titre=s.get("nom", ""), infos=infos, largeurs=largeurs, paysage=True,
            infos_haut=infos_haut(), taille=7,
            surlignes={i: "#FDECEC" for i, r in enumerate(rows) if "Non" in r},
            notes_bas=["Complétude : part des rubriques attendues reçues (EP : effectifs, personnel, CEP, recensement, "
                       "rapports ; EM / EE : effectifs, personnel, recensement, rapports).",
                       f"État arrêté le {H.maintenant()[:16]}."],
            signatures=[(s.get("responsable_titre") or "Le Responsable", s.get("responsable_nom") or "", sig, False)])
        return H.pdf_reponse(pdf, nom)

    # ------------------------------------------------------------------ envoi CS → DDEMP
    @app.route("/juridiction/transmissions/envoi", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_transmission_envoi():
        actif()
        if config.EDITION != "cs":
            abort(404)
        annee = annee_choisie()
        r = reglages()
        if request.method == "POST":
            if not H.peut("jur_transmission"):
                abort(403)
            act = request.form.get("action")
            if act == "reglages":
                adr = MT.normaliser_adresse(request.form.get("adresse", ""))
                r["adresse"] = adr
                if request.form.get("code_acces", "").strip():
                    r["code_acces"] = request.form["code_acces"].strip()[:80]
                if request.form.get("effacer_code"):
                    r["code_acces"] = ""
                H.doc_ecrire(cle_reglages(), r)
                H.journal("jur_transmission_reglages", adr)
                flash("Réglages de l'envoi à la DDEMP enregistrés.", "success")
            elif act == "envoyer":
                try:
                    p = H.jur_exporter_paquet_cs(annee)
                except jur_format.PaquetInvalide as e:
                    flash(str(e), "danger")
                    return redirect(url_for("jur_transmission_envoi", annee=annee))
                octets = jur_format.vers_fichier(p)
                ok, msg, _rep = MT.envoyer_en_ligne(r.get("adresse"), r.get("code_acces"), octets)
                historiser(p, annee, "en_ligne", ok, msg, octets, r.get("adresse", ""))
                H.journal("jur_transmission_envoi", ("OK " if ok else "ÉCHEC ") + msg[:200])
                flash(("Envoi réussi : " if ok else "Échec de l'envoi : ") + msg, "success" if ok else "danger")
            return redirect(url_for("jur_transmission_envoi", annee=annee))
        if request.args.get("telecharger"):
            if not H.peut("jur_transmission"):
                abort(403)
            p = H.jur_exporter_paquet_cs(annee)
            octets = jur_format.vers_fichier(p)
            nom = f"transmission_{p['emetteur']['code']}_{annee}.gescol"
            historiser(p, annee, "fichier", True, "Fichier téléchargé.", octets, nom_fichier=nom)
            H.journal("jur_transmission_fichier", nom)
            return Response(octets, mimetype="application/octet-stream",
                            headers={"Content-Disposition": f'attachment; filename="{nom}"'})
        try:
            p = H.jur_exporter_paquet_cs(annee)
            erreur = None
        except jur_format.PaquetInvalide as e:
            p, erreur = None, str(e)
        apercu = None
        if p:
            avec = [it for it in p["ecoles"] if it.get("sections")]
            eff = jur_calc.cumul([jur_calc.effectifs(it["sections"].get("effectifs")) for it in avec], ("g", "f", "t"))
            apercu = {"ecoles": len(p["ecoles"]), "avec": len(avec), "sans": [it["ecole"]["nom"] for it in p["ecoles"]
                                                                              if not it.get("sections")],
                      "eleves": eff.get("t") or 0, "g": eff.get("g") or 0, "f": eff.get("f") or 0,
                      "enseignants": sum(jur_calc.enseignants(it["sections"].get("personnel"))["t"] for it in avec),
                      "agents": len(((p.get("cs") or {}).get("sections") or {}).get("agents") or []),
                      "cs_sections": [k for k in ((p.get("cs") or {}).get("sections") or {})],
                      "rub": {k: sum(1 for it in avec if k in it["sections"]) for k in jur_format.SECTIONS_ECOLE},
                      "taille": len(jur_format.vers_fichier(p)),
                      "nom": f"transmission_{p['emetteur']['code']}_{annee}.gescol"}
        hist = q("SELECT * FROM jur_trans_envois ORDER BY id DESC LIMIT 30")
        return render_template("jur_transmission_envoi.html", apercu=apercu, erreur=erreur, r=r, hist=hist, annee=annee,
                               annees=H.jur_annees(), noms=COURTS, sections=jur_format.SECTIONS_ECOLE)

    def historiser(p, annee, mode, ok, message, octets, destination="", nom_fichier=""):
        ex("INSERT INTO jur_trans_envois (annee, mode, destination, nom_fichier, empreinte, taille, nb_ecoles, "
           "nb_ecoles_donnees, nb_agents, statut, message, envoye_le, envoye_par) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (annee, mode, destination, nom_fichier, p.get("empreinte"), len(octets), len(p["ecoles"]),
            sum(1 for it in p["ecoles"] if it.get("sections")),
            len(((p.get("cs") or {}).get("sections") or {}).get("agents") or []), "ok" if ok else "erreur",
            message[:500], H.maintenant(), g.user["nom"] if g.get("user") else ""))

    # ------------------------------------------------------------------ API de réception en ligne
    def refus(code_http, message, ip, compter=True):
        if compter:
            with _verrou:
                _echecs_recents(ip).append(time.time())
        try:
            H.journal("api_transmission_refus", f"{ip} : {message[:200]}")
        except Exception:  # noqa: BLE001
            pass
        return jsonify(ok=False, message=message, resume=None), code_http

    @app.route("/api/transmission", methods=["POST"])
    def api_transmission():
        """Réception en ligne d'un paquet (école → CS, ou CS → DDEMP). Pas de session : authentification par
        l'en-tête X-Gescol-Code (code d'accès de l'école ou de la CS émettrice, généré dans « Suivi des envois »)."""
        if not config.juridiction():
            return jsonify(ok=False, message="Cette application ne reçoit pas de transmissions.", resume=None), 404
        ip = request.remote_addr or "?"
        with _verrou:
            if len(_echecs_recents(ip)) >= ECHECS_MAX:
                return jsonify(ok=False, message="Trop d'essais refusés depuis votre connexion : réessayez dans une heure.",
                               resume=None), 429
        s = struct()
        if not s:
            return refus(503, "Application destinataire non configurée.", ip, compter=False)
        if (request.content_length or 0) > jur_format.TAILLE_MAX:
            return refus(413, "Données trop volumineuses (15 Mo au maximum) : envoyez le fichier.", ip, compter=False)
        code = (request.headers.get("X-Gescol-Code") or "").strip().upper()
        if not code:
            return refus(403, "Code d'accès manquant.", ip)
        # recherche de l'émetteur par comparaison à temps constant
        if s["niveau"] == "cs":
            candidats = q("SELECT id, code, nom, jeton FROM jur_ecoles WHERE actif=1 AND jeton IS NOT NULL AND jeton<>''")
        else:
            candidats = q("SELECT id, nom, departement, jeton FROM jur_cs WHERE jeton IS NOT NULL AND jeton<>''")
        emetteur = None
        for c in candidats:
            if secrets.compare_digest(c["jeton"].strip().upper().encode(), code.encode()):
                emetteur = c
        if not emetteur:
            return refus(403, "Code d'accès incorrect ou désactivé : demandez un nouveau code.", ip)
        try:
            octets = request.get_data(cache=False)
        except RequestEntityTooLarge:
            return refus(413, "Données trop volumineuses (15 Mo au maximum) : envoyez le fichier.", ip, compter=False)
        try:
            paquet = MT.lire_paquet(octets)
        except jur_format.PaquetInvalide as e:
            return refus(400, str(e), ip)
        em = paquet.get("emetteur") or {}
        if s["niveau"] == "cs":
            if em.get("type") != "ecole" or len(paquet["ecoles"]) != 1:
                return refus(403, "Ce code d'accès est celui d'une école : le paquet doit venir de cette seule école.", ip)
            code_p = paquet["ecoles"][0]["ecole"]["code"].strip()
            if code_p != emetteur["code"]:
                autre = q("SELECT id, nom FROM jur_ecoles WHERE code=? AND id<>?", (code_p, emetteur["id"]), un=True)
                if autre:
                    return refus(409, f"Le code d'école {code_p} appartient à une autre école ({autre['nom']}) : "
                                      "contactez la circonscription.", ip)
                # 1re transmission d'une école saisie à la main par la CS : son code provisoire devient celui de l'école
                ex("UPDATE jur_ecoles SET code=? WHERE id=?", (code_p, emetteur["id"]))
                H.journal("jur_code_ecole", f"{emetteur['nom']} : {emetteur['code']} → {code_p}")
        else:
            ident = (paquet.get("cs") or {}).get("identite") or {}
            if em.get("type") != "cs" or H.jur_norm(ident.get("nom") or em.get("cs")) != H.jur_norm(emetteur["nom"]) \
                    or (ident.get("departement") and H.jur_norm(ident["departement"]) != H.jur_norm(emetteur["departement"])):
                return refus(403, f"Ce code d'accès est celui de la CS {emetteur['nom']} : le paquet reçu vient "
                                  f"d'un autre émetteur ({em.get('nom') or '?'}).", ip)
        try:
            res = H.jur_importer_paquet(paquet, "en_ligne", f"en ligne ({ip})", len(octets))
        except jur_format.PaquetInvalide as e:
            return refus(422, str(e), ip, compter=False)
        with _verrou:
            _echecs.pop(ip, None)
        H.journal("api_transmission", f"{em.get('nom')} ({paquet['annee']}) : {res.get('sections')} rubrique(s)")
        nb = res.get("ecoles_creees", 0) + res.get("ecoles_maj", 0)
        msg = (f"Données de {paquet['annee']} reçues par {s.get('nom') or 'la structure'} : {nb} école(s), "
               f"{res.get('sections', 0)} rubrique(s).")
        return jsonify(ok=True, message=msg, resume=res), 200
