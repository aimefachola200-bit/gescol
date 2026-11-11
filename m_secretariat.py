# -*- coding: utf-8 -*-
"""Secrétariat : registre du courrier (arrivée / départ) et archives de documents."""
import os
import secrets
from datetime import date, datetime

from flask import abort, flash, g, redirect, render_template, request, send_file, url_for

EXT_AUTORISEES = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".txt"}
TYPES_ARCHIVE = ["Acte de naissance", "Ancien bulletin", "Certificat / attestation", "Décision", "Correspondance",
                 "Pièce d'identité du parent", "Dossier du personnel", "Procès-verbal", "Autre"]
STATUTS_COURRIER = {"a_traiter": "À traiter", "traite": "Traité", "classe": "Classé"}


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config
    dossier = os.path.join(config.INSTANCE_DIR, "archives")
    os.makedirs(dossier, exist_ok=True)

    def sauver_fichier(fichier):
        """Enregistre un fichier téléversé ; retourne (nom_stocké, nom_original) ou (None, message d'erreur)."""
        if not fichier or not fichier.filename:
            return None, None
        ext = os.path.splitext(fichier.filename)[1].lower()
        if ext not in EXT_AUTORISEES:
            return None, "Format non accepté (PDF, image, Word, Excel)."
        nom = f"{datetime.now():%Y%m%d}_{secrets.token_hex(6)}{ext}"
        fichier.save(os.path.join(dossier, nom))
        return nom, os.path.basename(fichier.filename)[:150]

    @app.context_processor
    def ctx_secr():
        return dict(STATUTS_COURRIER=STATUTS_COURRIER)

    @app.route("/secretariat/courrier", methods=["GET", "POST"])
    @H.connexion_requise("secretariat")
    def courrier():
        if request.method == "POST":
            if request.form.get("action") == "maj":
                cid = request.form.get("id", type=int)
                st = request.form.get("statut")
                if st in STATUTS_COURRIER:
                    ex("UPDATE courriers SET statut=?, suite=? WHERE id=?", (st, request.form.get("suite", "").strip()[:500] or None, cid))
                    flash("Courrier mis à jour.", "success")
                return redirect(url_for("courrier", sens=request.args.get("sens", "")))
            sens = request.form.get("sens")
            d = request.form.get("date") or date.today().isoformat()
            corr = request.form.get("correspondant", "").strip()[:200]
            objet = request.form.get("objet", "").strip()[:300]
            if sens not in ("arrivee", "depart") or not corr or not objet:
                flash("Sens, correspondant et objet sont obligatoires.", "danger")
                return redirect(url_for("courrier"))
            fichier, info = sauver_fichier(request.files.get("fichier"))
            if fichier is None and info:
                flash(info, "danger")
                return redirect(url_for("courrier"))
            cid = ex("INSERT INTO courriers (sens, date, correspondant, objet, reference, fichier, saisi_par, cree_le) "
                     "VALUES (?,?,?,?,?,?,?,?)", (sens, d, corr, objet, request.form.get("reference", "").strip()[:100] or None,
                                                  fichier, g.user["id"], H.maintenant()))
            annee = d[:4]
            rang = q("SELECT COUNT(*) n FROM courriers WHERE sens=? AND substr(date,1,4)=? AND id<=?", (sens, annee, cid), un=True)["n"]
            num = f"{'A' if sens == 'arrivee' else 'D'}-{annee}-{rang:04d}"
            ex("UPDATE courriers SET numero=? WHERE id=?", (num, cid))
            H.journal("courrier", f"{num} {objet}")
            flash(f"Courrier enregistré sous le n° {num}.", "success")
            return redirect(url_for("courrier", sens=sens))
        sens = request.args.get("sens", "")
        statut = request.args.get("statut", "")
        rech = request.args.get("q", "").strip()
        sql, args = "SELECT * FROM courriers WHERE 1=1", []
        if sens in ("arrivee", "depart"):
            sql += " AND sens=?"
            args.append(sens)
        if statut in STATUTS_COURRIER:
            sql += " AND statut=?"
            args.append(statut)
        if rech:
            sql += " AND (objet LIKE ? OR correspondant LIKE ? OR numero LIKE ?)"
            args += [f"%{rech}%"] * 3
        lst = q(sql + " ORDER BY date DESC, id DESC LIMIT 500", args)
        a_traiter = q("SELECT COUNT(*) n FROM courriers WHERE statut='a_traiter'", un=True)["n"]
        return render_template("courrier.html", lst=lst, sens=sens, statut=statut, rech=rech, a_traiter=a_traiter,
                               aujourdhui=date.today().isoformat())

    @app.route("/secretariat/archives", methods=["GET", "POST"])
    @H.connexion_requise("secretariat")
    def archives():
        if request.method == "POST":
            typ = request.form.get("type")
            titre = request.form.get("titre", "").strip()[:200]
            mat = request.form.get("matricule", "").strip()
            eleve = q("SELECT id FROM eleves WHERE matricule=?", (mat,), un=True) if mat else None
            if typ not in TYPES_ARCHIVE or not titre:
                flash("Type et titre sont obligatoires.", "danger")
                return redirect(url_for("archives"))
            if mat and not eleve:
                flash(f"Aucun élève avec le matricule {mat}.", "danger")
                return redirect(url_for("archives"))
            fichier, info = sauver_fichier(request.files.get("fichier"))
            if not fichier:
                flash(info or "Choisissez un fichier.", "danger")
                return redirect(url_for("archives"))
            ex("INSERT INTO archives (type, titre, eleve_id, annee, fichier, nom_original, saisi_par, cree_le) VALUES (?,?,?,?,?,?,?,?)",
               (typ, titre, eleve["id"] if eleve else None, config.ANNEE_ACTIVE, fichier, info, g.user["id"], H.maintenant()))
            H.journal("archive", titre)
            flash("Document archivé.", "success")
            return redirect(url_for("archives"))
        rech = request.args.get("q", "").strip()
        typ = request.args.get("type", "")
        sql = """SELECT a.*, e.nom, e.prenoms, e.matricule FROM archives a LEFT JOIN eleves e ON e.id=a.eleve_id WHERE 1=1"""
        args = []
        if rech:
            sql += " AND (a.titre LIKE ? OR e.nom LIKE ? OR e.matricule LIKE ?)"
            args += [f"%{rech}%"] * 3
        if typ in TYPES_ARCHIVE:
            sql += " AND a.type=?"
            args.append(typ)
        return render_template("archives.html", lst=q(sql + " ORDER BY a.id DESC LIMIT 500", args), types=TYPES_ARCHIVE,
                               rech=rech, typ=typ)

    @app.route("/secretariat/fichier/<quoi>/<int:i>")
    @H.connexion_requise("secretariat")
    def fichier_secretariat(quoi, i):
        if quoi == "courrier":
            r = q("SELECT fichier, objet nom FROM courriers WHERE id=?", (i,), un=True)
        elif quoi == "archive":
            r = q("SELECT fichier, nom_original nom FROM archives WHERE id=?", (i,), un=True)
        else:
            abort(404)
        if not r or not r["fichier"]:
            abort(404)
        chemin = os.path.join(dossier, os.path.basename(r["fichier"]))
        if not os.path.exists(chemin):
            abort(404)
        nom = r["nom"] if quoi == "archive" and r["nom"] else os.path.basename(r["fichier"])
        return send_file(chemin, as_attachment=False, download_name=nom)
