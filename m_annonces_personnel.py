# -*- coding: utf-8 -*-
"""v2.4.4 — Annonces au personnel : la direction écrit aux enseignants (ou à tout le personnel) ; chacun les lit dans « Annonces ».

* /annonces                     annonces_accueil      liste (marque les annonces comme lues) ; la direction y publie
* /annonces/nouvelle  POST      annonces_nouvelle     publication (direction, secrétariat : droit « communication »)
* /annonces/<id>/supprimer POST annonces_supprimer
Depuis Communication → Écrire, le destinataire « Enseignants (annonce interne) » publie ici.
Fonction de gabarit : ``annonces_non_lues()`` (pastille du menu).
"""
from flask import abort, flash, g, redirect, render_template, request, url_for

CIBLES = {"enseignants": "Enseignants", "tous": "Tout le personnel"}


def lisible_par(role, cible):
    """Un enseignant lit les annonces « enseignants » et « tout le personnel » ; les autres rôles lisent tout."""
    return True if role != "enseignant" else cible in ("enseignants", "tous")


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema("""
        CREATE TABLE IF NOT EXISTS annonces_personnel (
            id INTEGER PRIMARY KEY,
            ecole_id INTEGER,
            sujet TEXT NOT NULL,
            texte TEXT NOT NULL,
            cible TEXT NOT NULL DEFAULT 'enseignants',
            auteur_id INTEGER,
            cree_le TEXT
        );
        CREATE TABLE IF NOT EXISTS annonces_lues (
            annonce_id INTEGER NOT NULL REFERENCES annonces_personnel(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (annonce_id, user_id)
        );
    """)

    def visibles():
        role = g.user["role"]
        sql = "SELECT a.*, u.nom auteur FROM annonces_personnel a LEFT JOIN utilisateurs u ON u.id=a.auteur_id WHERE a.ecole_id=?"
        args = [H.eco()]
        if role == "enseignant":
            sql += " AND a.cible IN ('enseignants','tous')"
        return q(sql + " ORDER BY a.id DESC LIMIT 200", args)

    def publier(sujet, texte, cible):
        sujet, texte = (sujet or "").strip()[:150], (texte or "").strip()[:1000]
        if not sujet or not texte or cible not in CIBLES:
            return False
        aid = ex("INSERT INTO annonces_personnel (ecole_id, sujet, texte, cible, auteur_id, cree_le) VALUES (?,?,?,?,?,?)",
                 (H.eco(), sujet, texte, cible, g.user["id"], H.maintenant()))
        H.journal("annonce_personnel", f"{cible} : {sujet}")
        return aid or True

    H.publier_annonce_personnel = publier

    def non_lues():
        try:
            if not g.get("user"):
                return 0
            ids = [a["id"] for a in visibles()]
            if not ids:
                return 0
            lues = {r["annonce_id"] for r in q("SELECT annonce_id FROM annonces_lues WHERE user_id=?", (g.user["id"],))}
            return len([i for i in ids if i not in lues])
        except Exception:  # noqa: BLE001 - une pastille ne doit jamais casser une page
            return 0

    app.jinja_env.globals["annonces_non_lues"] = non_lues

    def peut_publier():
        return g.user["role"] != "enseignant" and H.peut("communication")

    @app.route("/annonces")
    @H.connexion_requise()
    def annonces_accueil():
        lst = visibles()
        lues = {r["annonce_id"] for r in q("SELECT annonce_id FROM annonces_lues WHERE user_id=?", (g.user["id"],))}
        nouvelles = {a["id"] for a in lst if a["id"] not in lues}
        for i in nouvelles:
            ex("INSERT OR IGNORE INTO annonces_lues (annonce_id, user_id) VALUES (?,?)", (i, g.user["id"]))
        return render_template("annonces.html", annonces=lst, nouvelles=nouvelles, CIBLES=CIBLES, peut_publier=peut_publier())

    @app.route("/annonces/nouvelle", methods=["POST"])
    @H.connexion_requise("communication")
    def annonces_nouvelle():
        if not peut_publier():
            abort(403)
        aid = publier(request.form.get("sujet"), request.form.get("texte"), request.form.get("cible", "enseignants"))
        if aid:
            canaux = [c for c in request.form.getlist("canaux") if c in ("whatsapp", "sms")]
            if canaux and aid is not True:
                flash("Annonce publiée. Envoyez-la maintenant par WhatsApp ou SMS.", "success")
                return redirect(url_for("annonces_diffuser", aid=aid))
            flash("Annonce publiée : les enseignants la verront dans « Annonces ».", "success")
        else:
            flash("Indiquez un sujet et un message.", "danger")
        return redirect(url_for("annonces_accueil"))

    # ------------------------------------------------------------------ v2.4.7 : diffusion WhatsApp / SMS aux enseignants
    H.schema("""
        CREATE TABLE IF NOT EXISTS annonces_envois (
            annonce_id INTEGER NOT NULL, personnel_id INTEGER NOT NULL, canal TEXT NOT NULL, date TEXT,
            PRIMARY KEY (annonce_id, personnel_id, canal));
    """)

    def est_enseignant(fonction):
        f = (fonction or "").lower()
        return any(m in f for m in ("enseign", "professeur", "instit", "educat", "éducat", "maitre", "maître", "animat", "pcem", "pcet"))

    def destinataires(a):
        out = []
        for p in q("SELECT id, nom, prenoms, fonction, telephone FROM personnel WHERE ecole_id=? AND actif=1 ORDER BY nom, prenoms", (H.eco(),)):
            if a["cible"] == "enseignants" and not est_enseignant(p["fonction"]):
                continue
            out.append(p)
        return out

    def texte_message(a):
        ecole = (H.identification() or {}).get("ecole") or ""
        return (f"{ecole} - " if ecole else "") + f"{a['sujet']}\n{a['texte']}"

    def annonce_ou_404(aid):
        a = q("SELECT * FROM annonces_personnel WHERE id=? AND ecole_id=?", (aid, H.eco()), un=True)
        if not a:
            abort(404)
        return a

    @app.route("/annonces/<int:aid>/diffuser")
    @H.connexion_requise("communication")
    def annonces_diffuser(aid):
        if not peut_publier():
            abort(403)
        import notif
        a = annonce_ou_404(aid)
        envoyes = {(r["personnel_id"], r["canal"]) for r in q("SELECT * FROM annonces_envois WHERE annonce_id=?", (aid,))}
        lignes = [{"p": p, "tel": notif.normaliser_tel(p["telephone"]), "affiche": notif.affiche_tel(p["telephone"]),
                   "wa": (p["id"], "whatsapp") in envoyes, "sms": (p["id"], "sms") in envoyes} for p in destinataires(a)]
        return render_template("annonce_diffusion.html", a=a, lignes=lignes, texte=texte_message(a), CIBLES=CIBLES,
                               sms_ok=bool(notif.params().get("sms_url")))

    @app.route("/annonces/<int:aid>/envoi/<int:pid>/<canal>")
    @H.connexion_requise("communication")
    def annonces_envoi(aid, pid, canal):
        if not peut_publier() or canal not in ("whatsapp", "sms"):
            abort(403)
        import urllib.parse
        import notif
        a = annonce_ou_404(aid)
        p = q("SELECT id, telephone FROM personnel WHERE id=? AND ecole_id=?", (pid, H.eco()), un=True)
        tel = notif.normaliser_tel(p["telephone"]) if p else None
        if not tel:
            flash("Numéro de téléphone absent ou invalide.", "danger")
            return redirect(url_for("annonces_diffuser", aid=aid))
        ex("INSERT OR REPLACE INTO annonces_envois (annonce_id, personnel_id, canal, date) VALUES (?,?,?,?)", (aid, pid, canal, H.maintenant()))
        texte = texte_message(a)
        if canal == "whatsapp":
            return redirect(notif.lien_whatsapp(tel, texte))
        return redirect("sms:+" + tel + "?body=" + urllib.parse.quote(texte))

    @app.route("/annonces/<int:aid>/sms-groupe", methods=["POST"])
    @H.connexion_requise("communication")
    def annonces_sms_groupe(aid):
        if not peut_publier():
            abort(403)
        import notif
        a = annonce_ou_404(aid)
        p_ = notif.params()
        if not p_.get("sms_url"):
            flash("Passerelle SMS non configurée (Réglages WhatsApp / SMS) : utilisez les liens SMS ci-dessous.", "danger")
            return redirect(url_for("annonces_diffuser", aid=aid))
        deja = {r["personnel_id"] for r in q("SELECT personnel_id FROM annonces_envois WHERE annonce_id=? AND canal='sms'", (aid,))}
        ok = ko = 0
        for p in destinataires(a):
            if p["id"] in deja or not notif.normaliser_tel(p["telephone"]):
                continue
            reussi, _ = notif.envoyer_sms(p["telephone"], texte_message(a), p_)
            if reussi:
                ex("INSERT OR REPLACE INTO annonces_envois (annonce_id, personnel_id, canal, date) VALUES (?,?,'sms',?)", (aid, p["id"], H.maintenant()))
                ok += 1
            else:
                ko += 1
        flash(f"SMS envoyés : {ok}" + (f" ; échecs : {ko}" if ko else "") + ".", "success" if ok and not ko else "danger")
        return redirect(url_for("annonces_diffuser", aid=aid))

    @app.route("/annonces/<int:aid>/supprimer", methods=["POST"])
    @H.connexion_requise("communication")
    def annonces_supprimer(aid):
        if not peut_publier():
            abort(403)
        ex("DELETE FROM annonces_lues WHERE annonce_id=?", (aid,))
        ex("DELETE FROM annonces_personnel WHERE id=? AND ecole_id=?", (aid, H.eco()))
        H.journal("annonce_personnel_suppr", str(aid))
        flash("Annonce supprimée.", "success")
        return redirect(url_for("annonces_accueil"))
