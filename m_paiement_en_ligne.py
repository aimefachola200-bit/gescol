# -*- coding: utf-8 -*-
"""
Paiement en ligne de la scolarité par les parents (MTN MoMo, Moov Money, Celtiis Cash, carte)
via FedaPay ou KkiaPay. Le paiement n'est enregistré qu'après vérification auprès du
fournisseur, côté serveur (jamais sur la seule parole du navigateur).

FedaPay : https://docs.fedapay.com  —  KkiaPay : https://docs.kkiapay.me
"""
import json
import secrets
import urllib.error
import urllib.request
from datetime import datetime

from flask import abort, flash, g, redirect, render_template, request, url_for

import notif

FEDAPAY_API = {"sandbox": "https://sandbox-api.fedapay.com/v1", "live": "https://api.fedapay.com/v1"}
KKIAPAY_API = {True: "https://api-sandbox.kkiapay.me", False: "https://api.kkiapay.me"}

PARAM_DEFAUTS = {
    "pel_fedapay_actif": "0", "pel_fedapay_mode": "sandbox", "pel_fedapay_cle_secrete": "",
    "pel_kkiapay_actif": "0", "pel_kkiapay_sandbox": "1", "pel_kkiapay_cle_publique": "",
    "pel_kkiapay_cle_privee": "", "pel_kkiapay_secret": "",
}
SECRETS = {"pel_fedapay_cle_secrete", "pel_kkiapay_cle_privee", "pel_kkiapay_secret"}


class ErreurFournisseur(Exception):
    pass


def _http(methode, url, entetes=None, corps=None, timeout=25):
    """Appel HTTP JSON. Isolé pour pouvoir être simulé dans les tests."""
    data = json.dumps(corps).encode("utf-8") if corps is not None else None
    h = {"Accept": "application/json", "User-Agent": "GESCOL"}
    if data is not None:
        h["Content-Type"] = "application/json"
    h.update(entetes or {})
    req = urllib.request.Request(url, data=data, headers=h, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, {"message": txt[:300]}
    except Exception as e:  # noqa: BLE001
        raise ErreurFournisseur(f"Connexion impossible au service de paiement : {e}") from e


def _objet_transaction(rep):
    """FedaPay enveloppe l'objet dans « v1/transaction » ; on accepte aussi l'objet nu."""
    if isinstance(rep, dict):
        for k in ("v1/transaction", "transaction"):
            if isinstance(rep.get(k), dict):
                return rep[k]
    return rep or {}


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config

    def reglages():
        v = dict(PARAM_DEFAUTS)
        v.update({k: val for k, val in H.lire_parametres().items() if k.startswith("pel_")})
        return v

    def fournisseurs_actifs(v=None):
        v = v or reglages()
        out = []
        if v["pel_fedapay_actif"] == "1" and v["pel_fedapay_cle_secrete"]:
            out.append("fedapay")
        if v["pel_kkiapay_actif"] == "1" and v["pel_kkiapay_cle_publique"] and v["pel_kkiapay_cle_privee"]:
            out.append("kkiapay")
        return out

    H.paiement_en_ligne_actif = lambda: bool(fournisseurs_actifs())
    config.MODES_PAIEMENT.setdefault("fedapay", "En ligne – FedaPay")
    config.MODES_PAIEMENT.setdefault("kkiapay", "En ligne – KkiaPay")

    def base_publique():
        return (config.URL_PUBLIQUE or request.host_url).rstrip("/")

    # ------------------------------------------------------------ FedaPay
    def fedapay(methode, chemin, corps=None):
        v = reglages()
        base = FEDAPAY_API.get(v["pel_fedapay_mode"], FEDAPAY_API["sandbox"])
        code, rep = _http(methode, base + chemin, {"Authorization": "Bearer " + v["pel_fedapay_cle_secrete"]}, corps)
        if code >= 400:
            msg = rep.get("message") if isinstance(rep, dict) else str(rep)
            raise ErreurFournisseur(f"FedaPay a refusé la demande ({code}) : {msg}")
        return rep

    def fedapay_statut(transaction_id):
        t = _objet_transaction(fedapay("GET", f"/transactions/{transaction_id}"))
        return t.get("status"), int(t.get("amount") or 0), t

    # ------------------------------------------------------------ KkiaPay
    def kkiapay_statut(transaction_id):
        v = reglages()
        base = KKIAPAY_API[v["pel_kkiapay_sandbox"] == "1"]
        code, rep = _http("POST", base + "/api/v1/transactions/status",
                          {"X-API-KEY": v["pel_kkiapay_cle_publique"], "X-PRIVATE-KEY": v["pel_kkiapay_cle_privee"],
                           "X-SECRET-KEY": v["pel_kkiapay_secret"]}, {"transactionId": transaction_id})
        if code >= 400:
            raise ErreurFournisseur(f"KkiaPay a refusé la vérification ({code}) : {rep}")
        return rep.get("status"), int(float(rep.get("amount") or 0)), rep

    # ------------------------------------------------------------ enregistrement du paiement
    def finaliser(pel, details=None):
        """Transforme un paiement en ligne vérifié en paiement de scolarité + reçu. Idempotent."""
        db = H.get_db()
        cur = db.execute("UPDATE paiements_en_ligne SET statut='approuve', maj_le=?, details=? WHERE id=? AND statut!='approuve'",
                         (H.maintenant(), json.dumps(details or {}, ensure_ascii=False)[:4000], pel["id"]))
        db.commit()
        if cur.rowcount != 1:
            return q("SELECT paiement_id FROM paiements_en_ligne WHERE id=?", (pel["id"],), un=True)["paiement_id"]
        e = H.eleve_ou_404(pel["eleve_id"])
        pid = ex("INSERT INTO paiements (eleve_id, annee, montant, mode, reference, telephone, motif, date_paiement, saisi_par) "
                 "VALUES (?,?,?,?,?,?,?,?,?)",
                 (e["id"], config.ANNEE_ACTIVE, pel["montant"], pel["fournisseur"], pel["transaction_id"],
                  pel["telephone"], "Frais de scolarité (paiement en ligne)", H.maintenant(), None))
        num = f"REC-{config.ANNEE_ACTIVE[:4]}-{pid:05d}"
        ex("UPDATE paiements SET numero_recu=? WHERE id=?", (num, pid))
        ex("UPDATE paiements_en_ligne SET paiement_id=? WHERE id=?", (pid, pel["id"]))
        ex("INSERT INTO journal (user_id, action, details, cree_le) VALUES (?,?,?,?)",
           (None, "paiement_en_ligne", f"{num} {pel['reference']} {pel['fournisseur']} {pel['montant']}", H.maintenant()))
        reste = H.situation(e)[2]
        try:
            notif.notifier_eleve(e, "paiement", "Paiement reçu",
                                 f"Paiement en ligne de {H.fcfa(pel['montant'])} reçu pour {e['prenoms']} {e['nom']} "
                                 f"(reçu {num}). Reste à payer : {H.fcfa(reste)}.")
        except Exception:  # noqa: BLE001
            pass
        return pid

    def marquer_echec(pel, statut_fournisseur):
        ex("UPDATE paiements_en_ligne SET statut='echoue', maj_le=?, details=? WHERE id=? AND statut='en_attente'",
           (H.maintenant(), json.dumps({"statut": statut_fournisseur}), pel["id"]))

    def verifier(pel):
        """Interroge le fournisseur et met à jour le paiement. Retourne 'approuve' | 'echoue' | 'en_attente'."""
        if pel["statut"] == "approuve":
            return "approuve"
        if not pel["transaction_id"]:
            return pel["statut"]
        if pel["fournisseur"] == "fedapay":
            statut, montant, brut = fedapay_statut(pel["transaction_id"])
            if statut in ("approved", "transferred") and montant >= pel["montant"]:
                finaliser(pel, {"statut": statut, "montant": montant})
                return "approuve"
            if statut in ("declined", "canceled", "refunded", "expired"):
                marquer_echec(pel, statut)
                return "echoue"
            return "en_attente"
        statut, montant, brut = kkiapay_statut(pel["transaction_id"])
        if str(statut).upper() == "SUCCESS" and montant >= pel["montant"]:
            finaliser(pel, {"statut": statut, "montant": montant})
            return "approuve"
        if str(statut).upper() in ("FAILED", "INSUFFICIENT_FUND", "TRANSACTION_NOT_ELIGIBLE", "INVALID_TRANSACTION"):
            marquer_echec(pel, statut)
            return "echoue"
        return "en_attente"

    H.verifier_paiement_en_ligne = verifier

    # ============================================================ côté parent
    @app.route("/parent/payer/<int:eid>", methods=["GET", "POST"])
    @H.parent_requis
    def parent_payer(eid):
        e = H.enfant_du_parent(eid)
        cl = H.classe_de(e)
        du, paye, reste = H.situation(e)
        v = reglages()
        fournisseurs = fournisseurs_actifs(v)
        if not fournisseurs:
            flash("Le paiement en ligne n'est pas encore activé par l'école.", "warning")
            return redirect(url_for("parent_enfant", eid=eid))
        if reste <= 0:
            flash("La scolarité est déjà soldée. Merci !", "success")
            return redirect(url_for("parent_enfant", eid=eid))
        if request.method == "POST":
            try:
                montant = int(request.form.get("montant", "0").replace(" ", ""))
            except ValueError:
                montant = 0
            fournisseur = request.form.get("fournisseur") if request.form.get("fournisseur") in fournisseurs else fournisseurs[0]
            tel = notif.normaliser_tel(request.form.get("telephone")) or g.parent["telephone"]
            if montant < 100 or montant > reste:
                flash(f"Indiquez un montant entre 100 et {H.fcfa(reste)}.", "danger")
                return redirect(url_for("parent_payer", eid=eid))
            ref = f"PEL-{datetime.now():%Y%m%d}-{secrets.token_hex(4).upper()}"
            pel_id = ex("INSERT INTO paiements_en_ligne (reference, eleve_id, parent_id, montant, fournisseur, telephone, cree_le) "
                        "VALUES (?,?,?,?,?,?,?)", (ref, eid, g.parent["id"], montant, fournisseur, tel, H.maintenant()))
            description = f"Scolarité {e['prenoms']} {e['nom']} ({e['matricule']}) – {config.ECOLE['nom']}"[:200]
            if fournisseur == "fedapay":
                nom = (g.parent["nom"] or "Parent").split()
                numero_local = tel[3:] if tel.startswith("229") else tel
                corps = {
                    "description": description, "amount": montant, "currency": {"iso": "XOF"},
                    "callback_url": f"{base_publique()}{url_for('retour_fedapay')}?ref={ref}",
                    "custom_metadata": {"reference_gescol": ref, "matricule": e["matricule"]},
                    "customer": {"firstname": nom[-1] if len(nom) > 1 else nom[0], "lastname": nom[0],
                                 "phone_number": {"number": numero_local, "country": "bj"}},
                }
                if g.parent["email"]:
                    corps["customer"]["email"] = g.parent["email"]
                try:
                    t = _objet_transaction(fedapay("POST", "/transactions", corps))
                    tid = t.get("id")
                    if not tid:
                        raise ErreurFournisseur("réponse FedaPay sans identifiant de transaction")
                    ex("UPDATE paiements_en_ligne SET transaction_id=? WHERE id=?", (str(tid), pel_id))
                    jeton = fedapay("POST", f"/transactions/{tid}/token")
                    url = jeton.get("url") or jeton.get("link")
                    if not url:
                        raise ErreurFournisseur("réponse FedaPay sans lien de paiement")
                except ErreurFournisseur as err:
                    marquer_echec({"id": pel_id}, "erreur_creation")
                    flash(f"Le paiement n'a pas pu démarrer : {err}", "danger")
                    return redirect(url_for("parent_enfant", eid=eid))
                return redirect(url)
            # KkiaPay : le widget s'ouvre dans la page, la vérification se fait ensuite côté serveur
            pel = q("SELECT * FROM paiements_en_ligne WHERE id=?", (pel_id,), un=True)
            return render_template("parent_kkiapay.html", e=e, pel=pel, cle=v["pel_kkiapay_cle_publique"],
                                   sandbox=v["pel_kkiapay_sandbox"] == "1", tel=tel[3:] if tel.startswith("229") else tel)
        return render_template("parent_payer.html", e=e, cl=cl, du=du, paye=paye, reste=reste, fournisseurs=fournisseurs,
                               sandbox=(v["pel_fedapay_mode"] != "live") if fournisseurs == ["fedapay"] else v["pel_kkiapay_sandbox"] == "1")

    @app.route("/paiement/fedapay/retour")
    def retour_fedapay():
        pel = q("SELECT * FROM paiements_en_ligne WHERE reference=? AND fournisseur='fedapay'", (request.args.get("ref", ""),), un=True)
        if not pel:
            abort(404)
        try:
            statut = verifier(pel)
        except ErreurFournisseur as err:
            statut = "en_attente"
            flash(str(err), "warning")
        return _page_resultat(pel["reference"], statut)

    @app.route("/parent/payer/kkiapay/confirmer", methods=["POST"])
    @H.parent_requis
    def confirmer_kkiapay():
        pel = q("SELECT * FROM paiements_en_ligne WHERE reference=? AND parent_id=? AND fournisseur='kkiapay'",
                (request.form.get("ref", ""), g.parent["id"]), un=True)
        tid = (request.form.get("transaction_id") or "").strip()[:100]
        if not pel or not tid:
            abort(400)
        if not pel["transaction_id"]:
            ex("UPDATE paiements_en_ligne SET transaction_id=? WHERE id=?", (tid, pel["id"]))
            pel = q("SELECT * FROM paiements_en_ligne WHERE id=?", (pel["id"],), un=True)
        try:
            statut = verifier(pel)
        except ErreurFournisseur as err:
            statut = "en_attente"
            flash(str(err), "warning")
        return _page_resultat(pel["reference"], statut)

    def _page_resultat(ref, statut):
        pel = q("SELECT * FROM paiements_en_ligne WHERE reference=?", (ref,), un=True)
        e = q("SELECT * FROM eleves WHERE id=?", (pel["eleve_id"],), un=True)
        return render_template("parent_paiement_resultat.html", pel=pel, e=e, statut=statut)

    # ------------------------------------------------------------ webhooks (appelés par les fournisseurs)
    @app.route("/webhooks/fedapay", methods=["POST"])
    def webhook_fedapay():
        data = request.get_json(silent=True) or {}
        entite = data.get("entity") or data.get("object") or data
        tid = str(entite.get("id") or "") if isinstance(entite, dict) else ""
        pel = q("SELECT * FROM paiements_en_ligne WHERE transaction_id=? AND fournisseur='fedapay'", (tid,), un=True) if tid else None
        if pel:
            try:
                verifier(pel)  # on ne croit pas le contenu reçu : on redemande le statut à FedaPay
            except ErreurFournisseur:
                return {"ok": False}, 502
        return {"ok": True}

    @app.route("/webhooks/kkiapay", methods=["POST"])
    def webhook_kkiapay():
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        tid = str(data.get("transactionId") or "")
        pel = q("SELECT * FROM paiements_en_ligne WHERE transaction_id=? AND fournisseur='kkiapay'", (tid,), un=True) if tid else None
        if not pel and tid:
            ref = str(data.get("stateData") or data.get("data") or "")
            pel = q("SELECT * FROM paiements_en_ligne WHERE reference=? AND fournisseur='kkiapay' AND transaction_id IS NULL",
                    (ref,), un=True)
            if pel:
                ex("UPDATE paiements_en_ligne SET transaction_id=? WHERE id=?", (tid, pel["id"]))
                pel = q("SELECT * FROM paiements_en_ligne WHERE id=?", (pel["id"],), un=True)
        if pel:
            try:
                verifier(pel)
            except ErreurFournisseur:
                return {"ok": False}, 502
        return {"ok": True}

    # ============================================================ côté école
    @app.route("/paiements/en-ligne", methods=["GET", "POST"])
    @H.connexion_requise("paiements")
    def paiements_en_ligne():
        if request.method == "POST":
            pel = q("SELECT * FROM paiements_en_ligne WHERE id=?", (request.form.get("id", type=int),), un=True)
            if pel:
                try:
                    statut = verifier(pel)
                    flash({"approuve": "Paiement confirmé et enregistré.", "echoue": "Paiement échoué ou annulé.",
                           "en_attente": "Toujours en attente chez le fournisseur."}[statut], "success" if statut == "approuve" else "info")
                except ErreurFournisseur as err:
                    flash(str(err), "danger")
            return redirect(url_for("paiements_en_ligne"))
        lst = q("""SELECT pl.*, e.nom, e.prenoms, e.matricule, p.numero_recu FROM paiements_en_ligne pl
                   JOIN eleves e ON e.id=pl.eleve_id LEFT JOIN paiements p ON p.id=pl.paiement_id
                   ORDER BY pl.id DESC LIMIT 300""")
        return render_template("paiements_en_ligne.html", lst=lst, actifs=fournisseurs_actifs())

    @app.route("/paiements/en-ligne/reglages", methods=["GET", "POST"])
    @H.connexion_requise("parametres")
    def reglages_paiement_en_ligne():
        v = reglages()
        if request.method == "POST":
            db = H.get_db()
            for k in PARAM_DEFAUTS:
                if k.endswith("_actif") or k == "pel_kkiapay_sandbox":
                    val = "1" if request.form.get(k) else "0"
                else:
                    val = request.form.get(k, "").strip()[:300]
                    if k in SECRETS and not val:
                        continue  # champ laissé vide = clé inchangée
                db.execute("INSERT INTO parametres (cle, valeur) VALUES (?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", (k, val))
            db.commit()
            H.journal("reglages_paiement_en_ligne")
            flash("Réglages du paiement en ligne enregistrés.", "success")
            return redirect(url_for("reglages_paiement_en_ligne"))
        masque = {k: (("•" * 8 + v[k][-4:]) if v[k] else "") for k in SECRETS}
        return render_template("reglages_paiement.html", v=v, masque=masque, base=base_publique(),
                               actifs=fournisseurs_actifs(v))
