# -*- coding: utf-8 -*-
"""v1.13 — Modifier, supprimer, réinitialiser (écoles privées surtout) : corriger une saisie sans tout recommencer.

* Paiements de scolarité (contribution des familles) :  Modifier (montant, date, mode, référence, téléphone, motif ;
  le reçu garde son numéro),  Supprimer (reçu supprimé, journalisé),  Réinitialiser les paiements d'un élève pour
  l'année (confirmation écrite « REINITIALISER »).
* Journal de caisse (trésorerie) :  Modifier et  Supprimer une opération saisie à la main.
* Cantine :  Réinitialiser la contribution d'une classe (montant journalier et validation effacés) et, si on le demande,
  supprimer les paiements de cantine de la classe pour l'année.
Droits : administrateur, fondateur, directeur (et comptable pour la trésorerie et la cantine). Tout est journalisé
avec l'ancienne valeur.
"""
from datetime import datetime

from flask import abort, flash, g, redirect, render_template, request, url_for

ROLES_CORRIGER = ("admin", "fondateur", "directeur")
ROLES_CAISSE = ("admin", "fondateur", "directeur", "comptable")


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config

    def exiger(roles):
        if not g.get("user") or g.user["role"] not in roles:
            abort(403)

    def entier(v):
        try:
            return int(str(v or "").replace(" ", "").replace(" ", "").replace("\xa0", ""))
        except ValueError:
            return None

    def date_ok(d):
        try:
            datetime.strptime(d, "%Y-%m-%d")
            return True
        except (TypeError, ValueError):
            return False

    # ------------------------------------------------------------------ paiements de scolarité
    @app.route("/paiements/<int:pid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("paiements")
    def paiement_modifier(pid):
        exiger(ROLES_CORRIGER)
        p = q("SELECT * FROM paiements WHERE id=?", (pid,), un=True)
        if not p:
            abort(404)
        e = H.eleve_ou_404(p["eleve_id"])
        if request.method == "POST":
            f = request.form
            montant, d, mode = entier(f.get("montant")), (f.get("date") or "")[:10], f.get("mode", "")
            if not montant or montant <= 0 or not date_ok(d) or mode not in config.MODES_PAIEMENT:
                flash("Vérifiez le montant (entier positif), la date et le mode de paiement.", "danger")
            else:
                ancien = f"{p['montant']} F, {p['date_paiement'][:10]}, {p['mode']}, {p['reference'] or ''}, {p['motif'] or ''}"
                heure = p["date_paiement"][10:] if len(p["date_paiement"] or "") > 10 else ""
                ex("UPDATE paiements SET montant=?, date_paiement=?, mode=?, reference=?, telephone=?, motif=? WHERE id=?",
                   (montant, d + heure, mode, (f.get("reference") or "").strip()[:100] or None,
                    (f.get("telephone") or "").strip()[:30] or None, (f.get("motif") or "").strip()[:150] or "Frais de scolarité", pid))
                H.journal("paiement_modifie", f"{p['numero_recu']} : {ancien} → {montant} F, {d}, {mode}")
                flash(f"Reçu {p['numero_recu']} modifié.", "success")
                return redirect(url_for("eleve_detail", eid=e["id"]))
        return render_template("correction_paiement.html", p=p, e=e, MODES=config.MODES_PAIEMENT)

    @app.route("/paiements/<int:pid>/supprimer", methods=["POST"])
    @H.connexion_requise("paiements")
    def paiement_supprimer(pid):
        exiger(ROLES_CORRIGER)
        p = q("SELECT * FROM paiements WHERE id=?", (pid,), un=True)
        if not p:
            abort(404)
        ex("DELETE FROM paiements WHERE id=?", (pid,))
        H.journal("paiement_supprime", f"{p['numero_recu']} : {p['montant']} F du {p['date_paiement'][:10]} ({p['mode']})")
        flash(f"Reçu {p['numero_recu']} supprimé.", "success")
        return redirect(url_for("eleve_detail", eid=p["eleve_id"]))

    @app.route("/eleves/<int:eid>/paiements/reinitialiser", methods=["POST"])
    @H.connexion_requise("paiements")
    def paiements_reinitialiser(eid):
        exiger(ROLES_CORRIGER)
        e = H.eleve_ou_404(eid)
        if (request.form.get("confirmation") or "").strip().upper() != "REINITIALISER":
            flash("Tapez REINITIALISER pour confirmer la suppression de tous les paiements de l'année de cet élève.", "danger")
            return redirect(url_for("eleve_detail", eid=eid))
        a = config.ANNEE_ACTIVE
        lst = q("SELECT numero_recu, montant FROM paiements WHERE eleve_id=? AND annee=?", (eid, a))
        ex("DELETE FROM paiements WHERE eleve_id=? AND annee=?", (eid, a))
        H.journal("paiements_reinitialises", f"{e['nom']} {e['prenoms']} ({a}) : {len(lst)} reçu(s) — "
                  + ", ".join(f"{r['numero_recu']} {r['montant']} F" for r in lst)[:900])
        flash(f"Paiements {a} de {e['nom']} {e['prenoms']} réinitialisés ({len(lst)} reçu(s) supprimé(s)).", "success")
        return redirect(url_for("eleve_detail", eid=eid))

    # ------------------------------------------------------------------ journal de caisse
    @app.route("/tresorerie/<int:tid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("tresorerie")
    def tresorerie_modifier(tid):
        exiger(ROLES_CAISSE)
        t = q("SELECT * FROM tresorerie WHERE id=? AND source='manuel'", (tid,), un=True)
        if not t:
            abort(404)
        import m_tresorerie as MT
        cats = MT.CATEGORIES
        if request.method == "POST":
            f = request.form
            typ, cat, lib, d, m = f.get("type"), f.get("categorie", ""), (f.get("libelle") or "").strip()[:200], (f.get("date") or "")[:10], entier(f.get("montant"))
            if typ not in ("entree", "sortie") or not lib or not m or m <= 0 or not date_ok(d) or not cat:
                flash("Vérifiez le type, la catégorie, le libellé, la date et le montant.", "danger")
            else:
                ex("UPDATE tresorerie SET date=?, type=?, categorie=?, libelle=?, montant=?, mode=?, reference=? WHERE id=?",
                   (d, typ, cat, lib, m, f.get("mode") or None, (f.get("reference") or "").strip()[:100] or None, tid))
                H.journal("tresorerie_modifiee", f"#{tid} {t['libelle']} {t['montant']} F → {lib} {m} F")
                flash("Opération modifiée.", "success")
                return redirect(url_for("tresorerie", mois=d[:7]))
        return render_template("correction_tresorerie.html", t=t, cats=cats, MODES=config.MODES_PAIEMENT)

    @app.route("/tresorerie/<int:tid>/supprimer", methods=["POST"])
    @H.connexion_requise("tresorerie")
    def tresorerie_supprimer(tid):
        exiger(ROLES_CAISSE)
        t = q("SELECT * FROM tresorerie WHERE id=? AND source='manuel'", (tid,), un=True)
        if not t:
            abort(404)
        ex("DELETE FROM tresorerie WHERE id=?", (tid,))
        H.journal("tresorerie_supprimee", f"#{tid} {t['date']} {t['type']} {t['categorie']} {t['libelle']} {t['montant']} F")
        flash("Opération supprimée.", "success")
        return redirect(url_for("tresorerie", mois=(t["date"] or "")[:7]))

    # ------------------------------------------------------------------ cantine : contribution d'une classe
    @app.route("/cantine/config/<int:cid>/reinitialiser", methods=["POST"])
    @H.connexion_requise("cantine")
    def cantine_reinitialiser(cid):
        exiger(ROLES_CAISSE)
        cl = H.classe_ou_404(cid)
        ancien = q("SELECT * FROM cantine_config WHERE classe_id=?", (cid,), un=True)
        ex("DELETE FROM cantine_config WHERE classe_id=?", (cid,))
        n = 0
        if request.form.get("paiements") == "1":
            a = config.ANNEE_ACTIVE
            d1, d2 = f"{a[:4]}-08-01", f"{a[5:9]}-07-31"
            n = q("SELECT COUNT(*) n FROM cantine_paiements WHERE date BETWEEN ? AND ? AND eleve_id IN "
                  "(SELECT id FROM eleves WHERE classe_id=?)", (d1, d2, cid), un=True)["n"]
            ex("DELETE FROM cantine_paiements WHERE date BETWEEN ? AND ? AND eleve_id IN (SELECT id FROM eleves WHERE classe_id=?)",
               (d1, d2, cid))
        H.journal("cantine_reinitialisee", f"{cl['nom']} : contribution {ancien['montant_jour'] if ancien else 0} F/jour effacée"
                  + (f", {n} paiement(s) de cantine supprimé(s)" if n else ""))
        flash(f"Contribution de cantine de {cl['nom']} réinitialisée" + (f" ; {n} paiement(s) supprimé(s)" if n else "") + ".", "success")
        return redirect(url_for("cantine_config"))
