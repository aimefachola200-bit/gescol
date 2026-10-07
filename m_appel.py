# -*- coding: utf-8 -*-
"""Registre d'appel : présences, absences et retards par classe et par jour, alerte aux parents."""
from datetime import date, datetime, timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

import notif

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def date_longue(iso):
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


def enregistrer(app, H):
    q, ex = H.q, H.ex

    @app.context_processor
    def ctx_appel():
        return dict(date_longue=date_longue)

    def lire_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
        except (TypeError, ValueError):
            abort(404)

    @app.route("/appel")
    @H.connexion_requise("appel")
    def appel_accueil():
        jour = request.args.get("date") or date.today().isoformat()
        jour = lire_date(jour)
        classes = q("""SELECT c.*, COUNT(e.id) effectif,
                        (SELECT fait_le FROM appels a WHERE a.classe_id=c.id AND a.date=?) fait_le,
                        (SELECT COUNT(*) FROM presences p JOIN eleves x ON x.id=p.eleve_id
                          WHERE x.classe_id=c.id AND p.date=? AND p.statut='absent') absents,
                        (SELECT COUNT(*) FROM presences p JOIN eleves x ON x.id=p.eleve_id
                          WHERE x.classe_id=c.id AND p.date=? AND p.statut='retard') retards
                       FROM classes c LEFT JOIN eleves e ON e.classe_id=c.id AND e.statut='inscrit'
                       GROUP BY c.id ORDER BY c.nom""", (jour, jour, jour))
        d = datetime.strptime(jour, "%Y-%m-%d").date()
        return render_template("appel_accueil.html", jour=jour, classes=classes,
                               veille=(d - timedelta(days=1)).isoformat(), lendemain=(d + timedelta(days=1)).isoformat())

    @app.route("/appel/<int:cid>/<jour>", methods=["GET", "POST"])
    @H.connexion_requise("appel")
    def appel_classe(cid, jour):
        jour = lire_date(jour)
        if jour > date.today().isoformat():
            flash("On ne peut pas faire l'appel d'un jour futur.", "warning")
            return redirect(url_for("appel_accueil"))
        cl = H.classe_ou_404(cid)
        eleves = q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (cid,))
        avant = {p["eleve_id"]: p for p in q(
            "SELECT p.* FROM presences p JOIN eleves e ON e.id=p.eleve_id WHERE e.classe_id=? AND p.date=?", (cid, jour))}
        if request.method == "POST":
            db = H.get_db()
            nouveaux = []
            for e in eleves:
                st = request.form.get(f"s_{e['id']}", "present")
                motif = request.form.get(f"m_{e['id']}", "").strip()[:200] or None
                just = 1 if request.form.get(f"j_{e['id']}") else 0
                if st not in ("present", "absent", "retard"):
                    st = "present"
                if st == "present":
                    db.execute("DELETE FROM presences WHERE eleve_id=? AND date=?", (e["id"], jour))
                    continue
                db.execute("""INSERT INTO presences (eleve_id, date, statut, motif, justifie, saisi_par, cree_le)
                              VALUES (?,?,?,?,?,?,?) ON CONFLICT(eleve_id, date)
                              DO UPDATE SET statut=excluded.statut, motif=excluded.motif, justifie=excluded.justifie,
                                            saisi_par=excluded.saisi_par""",
                           (e["id"], jour, st, motif, just, g.user["id"], H.maintenant()))
                if e["id"] not in avant or avant[e["id"]]["statut"] != st:
                    nouveaux.append((e, st))
            db.execute("INSERT INTO appels (classe_id, date, fait_par, fait_le) VALUES (?,?,?,?) "
                       "ON CONFLICT(classe_id, date) DO UPDATE SET fait_par=excluded.fait_par, fait_le=excluded.fait_le",
                       (cid, jour, g.user["id"], H.maintenant()))
            db.commit()
            n = 0
            if request.form.get("prevenir") == "1":
                for e, st in nouveaux:
                    quoi = "absent(e)" if st == "absent" else "arrivé(e) en retard"
                    n += notif.notifier_eleve(e, "absence", "Absence" if st == "absent" else "Retard",
                                              f"{e['prenoms']} {e['nom']} ({cl['nom']}) a été {quoi} le {date_longue(jour)}. "
                                              "Merci de contacter l'école si besoin.")
            H.journal("appel", f"{cl['nom']} {jour} : {len(nouveaux)} changement(s)")
            nb_abs = sum(1 for e in eleves if request.form.get(f"s_{e['id']}") == "absent")
            flash(f"Appel enregistré : {len(eleves) - nb_abs} présent(s), {nb_abs} absent(s)."
                  + (f" {n} message(s) préparé(s) pour les parents." if n else ""), "success")
            return redirect(url_for("appel_accueil", date=jour))
        fait = q("SELECT * FROM appels WHERE classe_id=? AND date=?", (cid, jour), un=True)
        return render_template("appel_classe.html", cl=cl, jour=jour, eleves=eleves, avant=avant, fait=fait)

    @app.route("/appel/statistiques")
    @H.connexion_requise("appel")
    def appel_stats():
        d1, d2 = H.bornes_annee()
        cid = request.args.get("classe", type=int)
        sql = """SELECT e.id, e.nom, e.prenoms, e.matricule, c.nom classe_nom,
                        SUM(p.statut='absent') absences, SUM(p.statut='absent' AND p.justifie=1) justifiees,
                        SUM(p.statut='retard') retards, MAX(p.date) derniere
                 FROM eleves e JOIN classes c ON c.id=e.classe_id
                 LEFT JOIN presences p ON p.eleve_id=e.id AND p.date BETWEEN ? AND ?
                 WHERE e.statut='inscrit'"""
        args = [d1, d2]
        if cid:
            sql += " AND e.classe_id=?"
            args.append(cid)
        lst = q(sql + " GROUP BY e.id HAVING absences > 0 OR retards > 0 ORDER BY absences DESC, retards DESC, e.nom", args)
        jours_appel = q("SELECT COUNT(DISTINCT date) n FROM appels WHERE date BETWEEN ? AND ?", (d1, d2), un=True)["n"]
        return render_template("appel_stats.html", lst=lst, classes=q("SELECT * FROM classes ORDER BY nom"),
                               cid=cid, jours_appel=jours_appel)

    @app.route("/eleves/<int:eid>/absences", methods=["GET", "POST"])
    @H.connexion_requise("appel")
    def absences_eleve_page(eid):
        e = H.eleve_ou_404(eid)
        if request.method == "POST":
            pid = request.form.get("id", type=int)
            ex("UPDATE presences SET justifie=?, motif=? WHERE id=? AND eleve_id=?",
               (1 if request.form.get("justifie") else 0, request.form.get("motif", "").strip()[:200] or None, pid, eid))
            flash("Absence mise à jour.", "success")
            return redirect(url_for("absences_eleve_page", eid=eid))
        d1, d2 = H.bornes_annee()
        lst = q("SELECT * FROM presences WHERE eleve_id=? AND date BETWEEN ? AND ? ORDER BY date DESC", (eid, d1, d2))
        return render_template("absences_eleve.html", e=e, lst=lst, tot=H.absences_eleve(eid))
