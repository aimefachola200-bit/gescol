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
                       WHERE c.ecole_id=? GROUP BY c.id ORDER BY c.nom""", (jour, jour, jour, H.eco()))
        if g.user["role"] == "enseignant":   # périmètre de l'enseignant : ses classes
            mes = {c["id"] for c in H.classes_autorisees()}
            classes = [c for c in classes if c["id"] in mes]
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
        H.verifier_classe(cid)
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
            # registre d'appel par demi-journée : l'absence du jour y est reportée, ou retirée si l'élève est présent
            import m_registre
            for e in eleves:
                if request.form.get(f"s_{e['id']}", "present") != "absent":
                    m_registre.retirer_appel(H, e["id"], jour)
            m_registre.reporter_appels(H, cid, jour, jour)
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
        classes = H.classes_autorisees()          # école courante ; enseignant : ses classes
        if cid:
            H.verifier_classe(cid)
            sql += " AND e.classe_id=?"
            args.append(cid)
        else:
            ids = [c["id"] for c in classes] or [0]
            sql += f" AND e.classe_id IN ({','.join('?' * len(ids))})"
            args += ids
        lst = q(sql + " GROUP BY e.id HAVING absences > 0 OR retards > 0 ORDER BY absences DESC, retards DESC, e.nom", args)
        jours_appel = q("SELECT COUNT(DISTINCT date) n FROM appels WHERE date BETWEEN ? AND ?", (d1, d2), un=True)["n"]
        return render_template("appel_stats.html", lst=lst, classes=classes, cid=cid, jours_appel=jours_appel,
                               mois=par_mois(cid, classes))

    def par_mois(cid, classes):
        """Absences et retards par mois de l'année scolaire (courbe) pour la classe choisie ou toutes les classes."""
        d1, d2 = H.bornes_annee()
        ids = [cid] if cid else ([c["id"] for c in classes] or [0])
        rows = q(f"""SELECT substr(p.date,1,7) m, SUM(p.statut='absent') a, SUM(p.statut='retard') r,
                            SUM(p.statut='absent' AND p.justifie=1) j
                     FROM presences p JOIN eleves e ON e.id=p.eleve_id
                     WHERE p.date BETWEEN ? AND ? AND e.classe_id IN ({','.join('?' * len(ids))}) GROUP BY m""",
                 [d1, d2] + ids)
        par = {r["m"]: r for r in rows}
        y0 = int(d1[:4])
        out = []
        for k in range(10):   # septembre → juin
            y, m = (y0, 9 + k) if k < 4 else (y0 + 1, k - 3)
            cle = f"{y}-{m:02d}"
            r = par.get(cle)
            out.append({"cle": cle, "lib": MOIS[m - 1][:4] + ".", "a": (r["a"] or 0) if r else 0,
                        "r": (r["r"] or 0) if r else 0, "j": (r["j"] or 0) if r else 0})
        return out

    @app.route("/appel/statistiques/pdf")
    @H.connexion_requise("appel")
    def appel_stats_pdf():
        """Statistiques d'assiduité : tableau des élèves, courbe mensuelle, signatures, cachet et QR de vérification."""
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
        from reportlab.graphics.shapes import Drawing, String
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        d1, d2 = H.bornes_annee()
        cid = request.args.get("classe", type=int)
        classes = H.classes_autorisees()
        cl = None
        if cid:
            H.verifier_classe(cid)
            cl = H.classe_ou_404(cid)
        ids = [cid] if cid else ([c["id"] for c in classes] or [0])
        lst = q(f"""SELECT e.nom, e.prenoms, e.sexe, c.nom classe_nom,
                        SUM(p.statut='absent') absences, SUM(p.statut='absent' AND p.justifie=1) justifiees,
                        SUM(p.statut='retard') retards, MAX(p.date) derniere
                 FROM eleves e JOIN classes c ON c.id=e.classe_id
                 LEFT JOIN presences p ON p.eleve_id=e.id AND p.date BETWEEN ? AND ?
                 WHERE e.statut='inscrit' AND e.classe_id IN ({','.join('?' * len(ids))})
                 GROUP BY e.id HAVING absences > 0 OR retards > 0 ORDER BY absences DESC, retards DESC, e.nom""",
                [d1, d2] + ids)
        effectif = q(f"SELECT COUNT(*) n FROM eleves WHERE statut='inscrit' AND classe_id IN ({','.join('?' * len(ids))})",
                     ids, un=True)["n"]
        jours_appel = q(f"SELECT COUNT(DISTINCT date) n FROM appels WHERE date BETWEEN ? AND ? "
                        f"AND classe_id IN ({','.join('?' * len(ids))})", [d1, d2] + ids, un=True)["n"]
        mois = par_mois(cid, classes)
        # courbe : absences, dont justifiées, retards
        dw, dh = 172 * mm, 50 * mm
        dr = Drawing(dw, dh)
        ch = HorizontalLineChart()
        ch.x, ch.y, ch.width, ch.height = 14 * mm, 9 * mm, dw - 60 * mm, dh - 16 * mm
        ch.data = [[m["a"] for m in mois], [m["j"] for m in mois], [m["r"] for m in mois]]
        ch.categoryAxis.categoryNames = [m["lib"] for m in mois]
        ch.categoryAxis.labels.fontSize = 7
        ch.valueAxis.valueMin = 0
        ch.valueAxis.labels.fontSize = 7
        mx = max([1] + [max(x) for x in ch.data])
        ch.valueAxis.valueMax = mx + max(1, mx // 5)
        coul = [colors.HexColor("#B42318"), colors.HexColor("#1B7F3B"), colors.HexColor("#B54708")]
        for i, c_ in enumerate(coul):
            ch.lines[i].strokeColor = c_
            ch.lines[i].strokeWidth = 1.6
        dr.add(ch)
        for i, (lib, c_) in enumerate(zip(("Absences", "dont justifiées", "Retards"), coul)):
            dr.add(String(dw - 42 * mm, dh - 14 * mm - i * 11, "— " + lib, fontSize=8, fillColor=c_))
        dr.add(String(14 * mm, dh - 5, "Évolution mensuelle (septembre → juin)", fontSize=8.5, fontName="Helvetica-Bold"))
        P = H.pdfs
        lignes = [[i, f"{e['nom']} {e['prenoms']}", e["sexe"], e["classe_nom"], e["absences"] or 0, e["justifiees"] or 0,
                   e["retards"] or 0, P.date_fr(e["derniere"]) if e["derniere"] else "—"] for i, e in enumerate(lst, 1)]
        tot_a = sum(m["a"] for m in mois)
        total = ["", "TOTAL", "", "", tot_a, sum(m["j"] for m in mois), sum(m["r"] for m in mois), ""]
        v = H.identification(cl) if cl else H.identification()
        img_d = P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur"))
        sigs = []
        if cl:
            sigs.append(((v.get("titulaire_titre") or "Le titulaire").upper(), v.get("titulaire_nom", ""),
                         P.image_data_url(H.signature_titulaire(cl["id"])), False))
        dt = v.get("directeur_titre") or "Directeur"
        sigs.append(((("La " if dt.startswith("Directrice") else "Le ") + dt).upper(), v.get("directeur_nom", ""), img_d, True))
        possibles = jours_appel * 2 * effectif
        taux = f"{100 - (tot_a / possibles * 100):.1f} %".replace(".", ",") if possibles else "—"
        tm = [["Mois", "Absences", "dont just.", "Retards"]] + [[m["lib"], m["a"], m["j"], m["r"]] for m in mois] \
            + [["Total", tot_a, sum(m["j"] for m in mois), sum(m["r"] for m in mois)]]
        from reportlab.platypus import Spacer, Table, TableStyle
        duo = Table([[dr, P.mini_tableau(tm, [18 * mm, 18 * mm, 18 * mm, 16 * mm], taille=6.5)]],
                    colWidths=[dw + 4 * mm, 74 * mm])
        duo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        pdf = P.pour_cycle(dict(cl).get("cycle") if cl else None)(
            "STATISTIQUES DE PRÉSENCE : ABSENCES ET RETARDS", ["N°", "Nom et prénoms", "Sexe", "Classe", "Absences",
                                                               "dont justifiées", "Retards", "Dernière absence"],
            lignes, total=total, paysage=True,
            sous_titre=f"{cl['nom'] if cl else 'Toutes les classes'} — Année scolaire {H.config.ANNEE_ACTIVE}",
            infos=[("Classe(s)", cl["nom"] if cl else f"{len(classes)} classe(s)"), ("Effectif", effectif),
                   ("Jours d'appel", jours_appel), ("Absences", tot_a), ("Taux d'assiduité estimé", taux),
                   ("Année scolaire", H.config.ANNEE_ACTIVE)],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[6, 46, 7, 18, 12, 14, 11, 18], taille=8,
            avant=[duo, Spacer(1, 4)],
            notes_bas=["Taux d'assiduité estimé = 100 − absences (demi-journées) / (jours d'appel × 2 × effectif) × 100."],
            signatures=sigs,
            verif=("statistiques", f"Statistiques de présence {H.config.ANNEE_ACTIVE} – {cl['nom'] if cl else 'toutes les classes'}"
                                   f" ({tot_a} absences)"))
        H.journal("appel_stats_pdf", cl["nom"] if cl else "toutes")
        return H.pdf_reponse(pdf, f"statistiques_presence_{(cl['nom'] if cl else 'ecole').replace(' ', '_')}.pdf")

    @app.route("/eleves/<int:eid>/absences", methods=["GET", "POST"])
    @H.connexion_requise("appel")
    def absences_eleve_page(eid):
        e = H.eleve_ou_404(eid)
        if e["classe_id"]:
            H.verifier_classe(e["classe_id"])
        if request.method == "POST":
            pid = request.form.get("id", type=int)
            ex("UPDATE presences SET justifie=?, motif=? WHERE id=? AND eleve_id=?",
               (1 if request.form.get("justifie") else 0, request.form.get("motif", "").strip()[:200] or None, pid, eid))
            flash("Absence mise à jour.", "success")
            return redirect(url_for("absences_eleve_page", eid=eid))
        d1, d2 = H.bornes_annee()
        lst = q("SELECT * FROM presences WHERE eleve_id=? AND date BETWEEN ? AND ? ORDER BY date DESC", (eid, d1, d2))
        return render_template("absences_eleve.html", e=e, lst=lst, tot=H.absences_eleve(eid))
