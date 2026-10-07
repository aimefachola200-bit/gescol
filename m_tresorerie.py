# -*- coding: utf-8 -*-
"""Trésorerie : journal de caisse (scolarité + salaires + opérations saisies), budget, bilan mensuel.

Édition publique : le journal et le bilan intègrent en plus les données du module m_finances_publiques
(paiements de cantine, subventions et recettes, frais de dossier CEP en entrées ; dépenses en sorties) et le solde
d'ouverture de l'année. En édition privée, rien ne change."""
import csv
import io
from datetime import date, datetime

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

CATEGORIES = {
    "entree": ["Frais de scolarité", "Frais d'inscription", "Cantine", "Transport scolaire", "Tenues et fournitures",
               "Dons et subventions", "Autres recettes"],
    "sortie": ["Salaires", "CNSS et impôts", "Loyer", "Eau et électricité", "Internet et téléphone",
               "Fournitures et matériel", "Entretien et réparations", "Transport", "Cantine", "Examens et concours",
               "Frais bancaires et Mobile Money", "Autres dépenses"],
}
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config

    def publique():
        """Édition publique avec le module des finances publiques chargé."""
        return config.publique() and getattr(H, "fp_operations", None) is not None

    def categories():
        return H.fp_categories_tresorerie(CATEGORIES) if publique() else CATEGORIES

    def lire_mois(m):
        try:
            return datetime.strptime(m, "%Y-%m").strftime("%Y-%m")
        except (TypeError, ValueError):
            return date.today().strftime("%Y-%m")

    def operations(d1, d2):
        """Toutes les opérations entre deux dates : scolarité (table paiements) + trésorerie."""
        ops = []
        for p in q("""SELECT p.*, e.nom, e.prenoms FROM paiements p JOIN eleves e ON e.id=p.eleve_id
                      WHERE p.annule=0 AND date(p.date_paiement) BETWEEN ? AND ?""", (d1, d2)):
            ops.append({"date": p["date_paiement"][:10], "type": "entree", "categorie": "Frais de scolarité",
                        "libelle": f"{p['numero_recu']} – {p['nom']} {p['prenoms']}", "montant": p["montant"],
                        "mode": p["mode"], "source": "scolarite", "id": p["id"], "reference": p["reference"]})
        for t in q("SELECT * FROM tresorerie WHERE annule=0 AND date BETWEEN ? AND ?", (d1, d2)):
            ops.append({"date": t["date"], "type": t["type"], "categorie": t["categorie"], "libelle": t["libelle"],
                        "montant": t["montant"], "mode": t["mode"], "source": t["source"], "id": t["id"],
                        "reference": t["reference"]})
        if publique():  # cantine, subventions/recettes, frais CEP, dépenses
            ops += H.fp_operations(d1, d2)
        ops.sort(key=lambda o: (o["date"], o["source"], o["id"]))
        return ops

    def solde_avant(d):
        """Solde cumulé depuis le début de l'année scolaire jusqu'à la veille de d."""
        debut, _ = H.bornes_annee()
        base = H.fp_solde_ouverture() if publique() else 0   # édition publique : solde d'ouverture saisi
        if d <= debut:
            return base
        ops = operations(debut, (datetime.strptime(d, "%Y-%m-%d").date().fromordinal(
            datetime.strptime(d, "%Y-%m-%d").date().toordinal() - 1)).isoformat())
        return base + sum(o["montant"] if o["type"] == "entree" else -o["montant"] for o in ops)

    @app.route("/tresorerie", methods=["GET", "POST"])
    @H.connexion_requise("tresorerie")
    def tresorerie():
        mois = lire_mois(request.args.get("mois"))
        if request.method == "POST":
            if request.form.get("action") == "annuler":
                t = q("SELECT * FROM tresorerie WHERE id=? AND source='manuel'", (request.form.get("id", type=int),), un=True)
                if t:
                    ex("UPDATE tresorerie SET annule=1 WHERE id=?", (t["id"],))
                    H.journal("tresorerie_annulee", f"#{t['id']} {t['libelle']}")
                    flash("Opération annulée.", "success")
                return redirect(url_for("tresorerie", mois=mois))
            typ = request.form.get("type")
            cat = request.form.get("categorie", "")
            lib = request.form.get("libelle", "").strip()[:200]
            d = request.form.get("date") or date.today().isoformat()
            try:
                montant = int(request.form.get("montant", "0").replace(" ", ""))
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                montant = 0
            cats = categories()
            if typ not in cats or cat not in cats[typ] or not lib or montant <= 0:
                flash("Vérifiez le type, la catégorie, le libellé et le montant.", "danger")
            elif typ == "entree" and cat == "Frais de scolarité":
                flash("La scolarité s'enregistre dans Paiements (avec reçu), pas ici.", "warning")
            else:
                ex("INSERT INTO tresorerie (date, type, categorie, libelle, montant, mode, reference, saisi_par, cree_le) "
                   "VALUES (?,?,?,?,?,?,?,?,?)", (d, typ, cat, lib, montant, request.form.get("mode") or None,
                                                  request.form.get("reference", "").strip()[:100] or None, g.user["id"], H.maintenant()))
                H.journal("tresorerie", f"{typ} {cat} {montant}")
                flash("Opération enregistrée.", "success")
            return redirect(url_for("tresorerie", mois=d[:7]))
        a, m = map(int, mois.split("-"))
        d1 = f"{mois}-01"
        d2 = f"{a + (m == 12)}-{(m % 12) + 1:02d}-01"
        d2 = (datetime.strptime(d2, "%Y-%m-%d").date().fromordinal(datetime.strptime(d2, "%Y-%m-%d").date().toordinal() - 1)).isoformat()
        ops = operations(d1, d2)
        ouverture = solde_avant(d1)
        solde = ouverture
        for o in ops:
            solde += o["montant"] if o["type"] == "entree" else -o["montant"]
            o["solde"] = solde
        entrees = sum(o["montant"] for o in ops if o["type"] == "entree")
        sorties = sum(o["montant"] for o in ops if o["type"] == "sortie")
        if request.args.get("format") == "csv":
            buf = io.StringIO()
            w = csv.writer(buf, delimiter=";")
            w.writerow(["Date", "Type", "Catégorie", "Libellé", "Mode", "Référence", "Entrée", "Sortie", "Solde"])
            w.writerow(["", "", "", "Solde d'ouverture", "", "", "", "", ouverture])
            for o in ops:
                w.writerow([o["date"], o["type"], o["categorie"], o["libelle"], config.MODES_PAIEMENT.get(o["mode"] or "", o["mode"] or ""),
                            o["reference"] or "", o["montant"] if o["type"] == "entree" else "",
                            o["montant"] if o["type"] == "sortie" else "", o["solde"]])
            return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                            headers={"Content-Disposition": f"attachment; filename=journal_caisse_{mois}.csv"})
        return render_template("tresorerie.html", mois=mois, ops=ops, ouverture=ouverture, solde=solde, entrees=entrees,
                               sorties=sorties, categories=categories(), aujourdhui=date.today().isoformat())

    @app.route("/tresorerie/bilan")
    @H.connexion_requise("tresorerie")
    def tresorerie_bilan():
        debut, fin = H.bornes_annee()
        ops = operations(debut, fin)
        mois = []
        a0 = int(debut[:4])
        for i in range(12):
            m = 9 + i
            cle = f"{a0 + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}"
            mois.append({"cle": cle, "nom": MOIS_COURTS[(m - 1) % 12], "entrees": 0, "sorties": 0})
        idx = {m["cle"]: m for m in mois}
        par_cat = {"entree": {}, "sortie": {}}
        for o in ops:
            m = idx.get(o["date"][:7])
            if m:
                m["entrees" if o["type"] == "entree" else "sorties"] += o["montant"]
            par_cat[o["type"]][o["categorie"]] = par_cat[o["type"]].get(o["categorie"], 0) + o["montant"]
        maxi = max([1] + [max(m["entrees"], m["sorties"]) for m in mois])
        budget = {(b["type"], b["categorie"]): b["montant"] for b in q("SELECT * FROM budget WHERE annee=?", (config.ANNEE_ACTIVE,))}
        tot_e = sum(m["entrees"] for m in mois)
        tot_s = sum(m["sorties"] for m in mois)
        # recettes attendues (scolarité) pour comparaison
        attendu = q("""SELECT COALESCE(SUM(c.frais_scolarite),0) s FROM eleves e JOIN classes c ON c.id=e.classe_id
                       WHERE e.statut='inscrit'""", un=True)["s"]
        return render_template("tresorerie_bilan.html", mois=mois, maxi=maxi, par_cat=par_cat, budget=budget,
                               categories=categories(), tot_e=tot_e, tot_s=tot_s, attendu=attendu)

    @app.route("/tresorerie/budget", methods=["GET", "POST"])
    @H.connexion_requise("tresorerie")
    def tresorerie_budget():
        if request.method == "POST":
            if g.user["role"] not in ("admin", "directeur"):
                abort(403)
            db = H.get_db()
            for typ, cats in categories().items():
                for i, cat in enumerate(cats):
                    brut = request.form.get(f"b_{typ}_{i}", "").replace(" ", "")
                    try:
                        v = int(brut or 0)
                    except ValueError:
                        v = 0
                    db.execute("INSERT INTO budget (annee, type, categorie, montant) VALUES (?,?,?,?) "
                               "ON CONFLICT(annee, type, categorie) DO UPDATE SET montant=excluded.montant",
                               (config.ANNEE_ACTIVE, typ, cat, max(v, 0)))
            db.commit()
            H.journal("budget", config.ANNEE_ACTIVE)
            flash("Budget enregistré.", "success")
            return redirect(url_for("tresorerie_bilan"))
        budget = {(b["type"], b["categorie"]): b["montant"] for b in q("SELECT * FROM budget WHERE annee=?", (config.ANNEE_ACTIVE,))}
        return render_template("tresorerie_budget.html", budget=budget, categories=categories())
