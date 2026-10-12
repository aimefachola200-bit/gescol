# -*- coding: utf-8 -*-
"""Espace parents (portail), comptes parents, messagerie école <-> parents, diffusion
WhatsApp / SMS, publication des bulletins."""
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import notif

_tentatives = {}  # anti-force brute sur la connexion parent : clé -> [horodatages]


def _trop_de_tentatives(cle):
    now = datetime.now()
    lst = [t for t in _tentatives.get(cle, []) if now - t < timedelta(minutes=15)]
    _tentatives[cle] = lst
    return len(lst) >= 8


def _echec(cle):
    _tentatives.setdefault(cle, []).append(datetime.now())


def mdp_provisoire():
    return f"{secrets.randbelow(10 ** 6):06d}"


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config

    # ------------------------------------------------------------ utilitaires parents
    @app.before_request
    def charger_parent():
        g.parent = None
        pid = session.get("pid")
        if pid:
            p = q("SELECT * FROM parents WHERE id=? AND actif=1", (pid,), un=True)
            if p:
                g.parent = p
            else:
                session.pop("pid", None)

    def parent_requis(f):
        @wraps(f)
        def wrap(*a, **k):
            if not g.parent:
                return redirect(url_for("parent_login", suivant=request.path))
            if g.parent["doit_changer_mdp"] and request.endpoint not in ("parent_mdp", "parent_logout"):
                flash("Choisissez votre mot de passe personnel.", "warning")
                return redirect(url_for("parent_mdp"))
            return f(*a, **k)
        return wrap

    H.parent_requis = parent_requis

    def enfants_du_parent(pid):
        return q("""SELECT e.*, c.nom classe_nom, c.niveau FROM eleves e LEFT JOIN classes c ON c.id=e.classe_id
                    WHERE e.parent_id=? AND e.statut='inscrit' ORDER BY e.nom, e.prenoms""", (pid,))

    def enfant_du_parent(eid):
        e = q("SELECT * FROM eleves WHERE id=? AND parent_id=?", (eid, g.parent["id"]), un=True)
        if not e:
            abort(404)
        return e

    H.enfant_du_parent = enfant_du_parent

    def periodes_publiees(classe_id):
        return {r["periode"] for r in q("SELECT periode FROM publications WHERE classe_id=? AND annee=?",
                                         (classe_id, config.ANNEE_ACTIVE))}

    @app.context_processor
    def contexte_parents():
        def compte_parent(eleve):
            if eleve and eleve["parent_id"]:
                return q("SELECT * FROM parents WHERE id=?", (eleve["parent_id"],), un=True)
            return None

        def messages_non_lus():
            if g.get("user") and H.peut("communication"):
                return q("SELECT COUNT(*) n FROM messages WHERE sens='parent' AND lu=0", un=True)["n"]
            return 0

        def whatsapp_en_attente():
            if g.get("user") and H.peut("communication"):
                return q("SELECT COUNT(*) n FROM notifications WHERE canal='whatsapp' AND statut='a_envoyer'", un=True)["n"]
            return 0

        def classes_select():
            return q("SELECT id, nom FROM classes ORDER BY nom")

        return dict(compte_parent=compte_parent, lien_wa=notif.lien_whatsapp, affiche_tel=notif.affiche_tel,
                    classes_select=classes_select,
                    messages_non_lus=messages_non_lus, whatsapp_en_attente=whatsapp_en_attente,
                    EVENEMENTS=notif.EVENEMENTS)

    def url_espace():
        base = config.URL_PUBLIQUE or request.host_url
        return base.rstrip("/") + url_for("parent_login")

    def message_identifiants(parent, mdp):
        return (f"Bonjour {parent['nom']}, voici votre accès à l'espace parents de {config.ECOLE['nom']} : "
                f"{url_espace()} — identifiant : {notif.affiche_tel(parent['telephone'])} — mot de passe provisoire : {mdp}. "
                "Vous choisirez votre mot de passe à la première connexion.")

    # ============================================================ côté école
    @app.route("/eleves/<int:eid>/acces-parent", methods=["POST"])
    @H.connexion_requise("parents")
    def acces_parent(eid):
        e = H.eleve_ou_404(eid)
        tel = notif.normaliser_tel(request.form.get("telephone") or e["parent_telephone"])
        if not tel:
            flash("Renseignez d'abord un numéro de téléphone valide pour le parent (fiche de l'élève).", "danger")
            return redirect(url_for("eleve_detail", eid=eid))
        nom = (request.form.get("nom") or e["parent_nom"] or f"Parent de {e['prenoms']}").strip()
        p = q("SELECT * FROM parents WHERE telephone=?", (tel,), un=True)
        mdp = None
        if not p:
            mdp = mdp_provisoire()
            pid = ex("INSERT INTO parents (nom, telephone, whatsapp, mdp_hash, cree_le) VALUES (?,?,?,?,?)",
                     (nom, tel, notif.normaliser_tel(e["parent_whatsapp"]) or tel, generate_password_hash(mdp), H.maintenant()))
            p = q("SELECT * FROM parents WHERE id=?", (pid,), un=True)
            H.journal("parent_cree", f"{tel} pour {e['matricule']}")
        elif request.form.get("reinitialiser"):
            mdp = mdp_provisoire()
            ex("UPDATE parents SET mdp_hash=?, doit_changer_mdp=1, actif=1 WHERE id=?", (generate_password_hash(mdp), p["id"]))
            H.journal("parent_reinit", tel)
        ex("UPDATE eleves SET parent_id=? WHERE id=?", (p["id"], eid))
        # les frères et sœurs inscrits avec le même numéro sont rattachés au même compte
        for autre in q("SELECT id, parent_telephone FROM eleves WHERE parent_id IS NULL AND parent_telephone IS NOT NULL"):
            if notif.normaliser_tel(autre["parent_telephone"]) == tel:
                ex("UPDATE eleves SET parent_id=? WHERE id=?", (p["id"], autre["id"]))
        enfants = enfants_du_parent(p["id"])
        if mdp is None:
            flash(f"{e['prenoms']} est rattaché(e) au compte parent existant ({notif.affiche_tel(tel)}).", "success")
            return redirect(url_for("eleve_detail", eid=eid))
        texte = message_identifiants(p, mdp)
        return render_template("parent_acces.html", p=p, mdp=mdp, enfants=enfants, texte=texte,
                               wa=notif.lien_whatsapp(p["whatsapp"] or p["telephone"], texte), url=url_espace(), e=e)

    @app.route("/parents")
    @H.connexion_requise("parents")
    def parents_liste():
        rech = request.args.get("q", "").strip()
        sql = """SELECT p.*, GROUP_CONCAT(e.prenoms || ' ' || e.nom, ', ') enfants, COUNT(e.id) nb
                 FROM parents p LEFT JOIN eleves e ON e.parent_id=p.id AND e.statut='inscrit'"""
        args = []
        if rech:
            sql += " WHERE p.nom LIKE ? OR p.telephone LIKE ? OR e.nom LIKE ?"
            chiffres = "".join(c for c in rech if c.isdigit())
            args = [f"%{rech}%", f"%{chiffres or rech}%", f"%{rech}%"]
        lst = q(sql + " GROUP BY p.id ORDER BY p.nom LIMIT 500", args)
        sans = q("""SELECT COUNT(*) n FROM eleves WHERE statut='inscrit' AND parent_id IS NULL""", un=True)["n"]
        return render_template("parents.html", lst=lst, rech=rech, sans=sans)

    @app.route("/parents/<int:pid>/action", methods=["POST"])
    @H.connexion_requise("parents")
    def parent_action(pid):
        p = q("SELECT * FROM parents WHERE id=?", (pid,), un=True)
        if not p:
            abort(404)
        act = request.form.get("action")
        if act == "basculer":
            ex("UPDATE parents SET actif=1-actif WHERE id=?", (pid,))
            H.journal("parent_actif", p["telephone"])
            flash("Compte mis à jour.", "success")
        elif act == "reinit":
            mdp = mdp_provisoire()
            ex("UPDATE parents SET mdp_hash=?, doit_changer_mdp=1, actif=1 WHERE id=?", (generate_password_hash(mdp), pid))
            H.journal("parent_reinit", p["telephone"])
            p = q("SELECT * FROM parents WHERE id=?", (pid,), un=True)
            texte = message_identifiants(p, mdp)
            return render_template("parent_acces.html", p=p, mdp=mdp, enfants=enfants_du_parent(pid), texte=texte,
                                   wa=notif.lien_whatsapp(p["whatsapp"] or p["telephone"], texte), url=url_espace(), e=None)
        return redirect(url_for("parents_liste"))

    @app.route("/parents/creer-acces-classe/<int:cid>", methods=["POST"])
    @H.connexion_requise("parents")
    def acces_parents_classe(cid):
        """Crée en une fois les accès des parents d'une classe (ceux qui ont un numéro valide)."""
        cl = H.classe_ou_404(cid)
        crees, lignes = 0, []
        for e in q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' AND parent_id IS NULL", (cid,)):
            tel = notif.normaliser_tel(e["parent_telephone"])
            if not tel:
                continue
            p = q("SELECT * FROM parents WHERE telephone=?", (tel,), un=True)
            if p:
                ex("UPDATE eleves SET parent_id=? WHERE id=?", (p["id"], e["id"]))
                continue
            mdp = mdp_provisoire()
            pid = ex("INSERT INTO parents (nom, telephone, whatsapp, mdp_hash, cree_le) VALUES (?,?,?,?,?)",
                     (e["parent_nom"] or f"Parent de {e['prenoms']}", tel,
                      notif.normaliser_tel(e["parent_whatsapp"]) or tel, generate_password_hash(mdp), H.maintenant()))
            ex("UPDATE eleves SET parent_id=? WHERE id=?", (pid, e["id"]))
            p = q("SELECT * FROM parents WHERE id=?", (pid,), un=True)
            texte = message_identifiants(p, mdp)
            lignes.append((p, e, mdp, notif.lien_whatsapp(p["whatsapp"] or tel, texte)))
            crees += 1
        H.journal("parents_classe", f"{cl['nom']} : {crees} accès")
        return render_template("parent_acces_classe.html", cl=cl, lignes=lignes, url=url_espace())

    @app.route("/notes/<int:cid>/<int:p>/publier", methods=["POST"])
    @H.connexion_requise("parents")
    def publier_bulletins(cid, p):
        cl, per = H.classe_ou_404(cid), H.periode_de(p)
        if request.form.get("action") == "retirer":
            ex("DELETE FROM publications WHERE classe_id=? AND periode=? AND annee=?", (cid, per, config.ANNEE_ACTIVE))
            H.journal("bulletins_retires", f"{cl['nom']} {per}")
            flash("Les bulletins ne sont plus visibles par les parents.", "success")
        else:
            ex("INSERT OR IGNORE INTO publications (classe_id, periode, annee, publie_le, publie_par) VALUES (?,?,?,?,?)",
               (cid, per, config.ANNEE_ACTIVE, H.maintenant(), g.user["id"]))
            n = 0
            doc = "livret" if cl["cycle"] == "maternelle" else "bulletin"
            for e in q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit'", (cid,)):
                n += notif.notifier_eleve(e, "bulletin", f"{doc.capitalize()} du {per}",
                                          f"Le {doc} du {per} de {e['prenoms']} {e['nom']} est disponible dans votre espace parents.")
            H.journal("bulletins_publies", f"{cl['nom']} {per}")
            flash(f"Bulletins publiés. {n} message(s) préparé(s) pour les parents"
                  + (" — pensez à envoyer les WhatsApp (menu Communication)." if n else "."), "success")
        return redirect(url_for("resultats", cid=cid, p=p))

    # ------------------------------------------------------------ communication
    def filtre_enseignant():
        """Périmètre de l'enseignant : (clause SQL, paramètres) limitant aux élèves de ses classes (parents de ses élèves)."""
        if g.user["role"] != "enseignant":
            return "", []
        ids = [c["id"] for c in H.classes_autorisees()] or [0]
        marque = ",".join("?" * len(ids))
        return (f" AND (e.classe_id IN ({marque}) OR (e.id IS NULL AND p.id IN "
                f"(SELECT parent_id FROM eleves WHERE classe_id IN ({marque}) AND parent_id IS NOT NULL)))"), ids + ids

    @app.route("/communication")
    @H.connexion_requise("communication")
    def communication():
        cl_sql, cl_args = filtre_enseignant()
        recus = q(f"""SELECT m.*, p.nom parent_nom, p.telephone, e.prenoms, e.nom eleve_nom FROM messages m
                      LEFT JOIN parents p ON p.id=m.parent_id LEFT JOIN eleves e ON e.id=m.eleve_id
                      WHERE m.sens='parent'{cl_sql} ORDER BY m.lu, m.id DESC LIMIT 100""", cl_args)
        wa = q(f"""SELECT n.*, p.nom parent_nom, e.prenoms, e.nom eleve_nom FROM notifications n
                   LEFT JOIN parents p ON p.id=n.parent_id LEFT JOIN eleves e ON e.id=n.eleve_id
                   WHERE n.canal='whatsapp' AND n.statut='a_envoyer'{cl_sql} ORDER BY n.id LIMIT 300""", cl_args)
        histo = q(f"""SELECT n.*, e.prenoms, e.nom eleve_nom FROM notifications n LEFT JOIN eleves e ON e.id=n.eleve_id
                      LEFT JOIN parents p ON p.id=n.parent_id
                      WHERE n.statut!='a_envoyer'{cl_sql} ORDER BY n.id DESC LIMIT 100""", cl_args)
        classes = H.classes_autorisees() if g.user["role"] == "enseignant" else q("SELECT * FROM classes ORDER BY nom")
        return render_template("communication.html", recus=recus, wa=wa, histo=histo, classes=classes,
                               p=notif.params(), onglet=request.args.get("onglet", "ecrire"))

    @app.route("/communication/diffuser", methods=["POST"])
    @H.connexion_requise("communication")
    def diffuser():
        cible = request.form.get("cible", "")
        sujet = request.form.get("sujet", "").strip()[:150]
        texte = request.form.get("texte", "").strip()[:1000]
        canaux = {c for c in request.form.getlist("canaux") if c in ("portail", "whatsapp", "sms")}
        if not sujet or not texte or not canaux:
            flash("Indiquez un sujet, un message et au moins un canal.", "danger")
            return redirect(url_for("communication"))
        if cible.startswith("classe:"):
            if g.user["role"] == "enseignant":
                H.verifier_classe(int(cible[7:] or 0))     # périmètre : une de ses classes
            eleves = q("SELECT * FROM eleves WHERE statut='inscrit' AND classe_id=?", (int(cible[7:] or 0),))
        elif g.user["role"] == "enseignant":
            flash("Choisissez une de vos classes : la diffusion à toute l'école relève de la direction.", "danger")
            return redirect(url_for("communication"))
        else:
            eleves = q("SELECT * FROM eleves WHERE statut='inscrit'")
        vus, n = set(), 0
        maint = H.maintenant()
        ecole = config.ECOLE.get("sigle") or config.ECOLE.get("nom")
        p = notif.params()
        for e in eleves:
            for parent_id, tel, wa in notif.destinataires_eleve(e):
                cle = parent_id or notif.normaliser_tel(tel) or notif.normaliser_tel(wa)
                if not cle or cle in vus:
                    continue
                vus.add(cle)
                if "portail" in canaux and parent_id:
                    ex("INSERT INTO messages (parent_id, sens, sujet, texte, auteur_id, cree_le) VALUES (?,?,?,?,?,?)",
                       (parent_id, "ecole", sujet, texte, g.user["id"], maint))
                    n += 1
                if "whatsapp" in canaux and notif.normaliser_tel(wa):
                    ex("INSERT INTO notifications (parent_id, eleve_id, telephone, canal, evenement, texte, cree_le) VALUES (?,?,?,?,?,?,?)",
                       (parent_id, e["id"], notif.normaliser_tel(wa), "whatsapp", "diffusion", f"{ecole} : {texte}", maint))
                    n += 1
                if "sms" in canaux and notif.normaliser_tel(tel):
                    ok, msg = notif.envoyer_sms(tel, f"{ecole} : {texte}", p)
                    ex("INSERT INTO notifications (parent_id, eleve_id, telephone, canal, evenement, texte, statut, erreur, cree_le, envoye_le) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)", (parent_id, e["id"], notif.normaliser_tel(tel), "sms", "diffusion",
                                                        f"{ecole} : {texte}", "envoye" if ok else "echec", None if ok else msg,
                                                        maint, maint if ok else None))
                    n += 1
        H.journal("diffusion", f"{cible or 'tous'} : {sujet} ({n})")
        flash(f"{n} message(s) créé(s) pour {len(vus)} famille(s)."
              + (" Les WhatsApp sont dans l'onglet « WhatsApp à envoyer »." if "whatsapp" in canaux else ""), "success")
        return redirect(url_for("communication", onglet="whatsapp" if "whatsapp" in canaux else "ecrire"))

    @app.route("/communication/whatsapp/<int:nid>", methods=["POST"])
    @H.connexion_requise("communication")
    def whatsapp_envoye(nid):
        cl_sql, cl_args = filtre_enseignant()
        if cl_sql and not q(f"""SELECT 1 FROM notifications n LEFT JOIN parents p ON p.id=n.parent_id
                                LEFT JOIN eleves e ON e.id=n.eleve_id WHERE n.id=?{cl_sql}""", [nid] + cl_args, un=True):
            abort(403)                                  # périmètre de l'enseignant : parents de ses élèves
        statut = "envoye" if request.form.get("action") != "ignorer" else "echec"
        ex("UPDATE notifications SET statut=?, envoye_le=?, erreur=? WHERE id=? AND canal='whatsapp'",
           (statut, H.maintenant(), None if statut == "envoye" else "ignoré", nid))
        if request.headers.get("X-Requested-With") == "fetch":
            return {"ok": True}
        return redirect(url_for("communication", onglet="whatsapp"))

    @app.route("/communication/message/<int:mid>", methods=["POST"])
    @H.connexion_requise("communication")
    def repondre_parent(mid):
        m = q("SELECT * FROM messages WHERE id=? AND sens='parent'", (mid,), un=True)
        if not m:
            abort(404)
        cl_sql, cl_args = filtre_enseignant()
        if cl_sql and not q(f"""SELECT 1 FROM messages m LEFT JOIN parents p ON p.id=m.parent_id
                                LEFT JOIN eleves e ON e.id=m.eleve_id WHERE m.id=?{cl_sql}""", [mid] + cl_args, un=True):
            abort(403)                                  # périmètre de l'enseignant : parents de ses élèves
        ex("UPDATE messages SET lu=1 WHERE id=?", (mid,))
        rep = request.form.get("reponse", "").strip()[:1000]
        if rep:
            ex("INSERT INTO messages (parent_id, eleve_id, sens, sujet, texte, auteur_id, cree_le) VALUES (?,?,?,?,?,?,?)",
               (m["parent_id"], m["eleve_id"], "ecole", "Re : " + m["sujet"], rep, g.user["id"], H.maintenant()))
            flash("Réponse envoyée dans l'espace du parent.", "success")
        return redirect(url_for("communication", onglet="recus"))

    @app.route("/communication/reglages", methods=["GET", "POST"])
    @H.connexion_requise("parametres")
    def reglages_messages():
        if request.method == "POST":
            db = H.get_db()
            for k in notif.PARAM_DEFAUTS:
                if k.startswith("notif_"):
                    v = "1" if request.form.get(k) else "0"
                else:
                    v = request.form.get(k, "").strip()[:500]
                db.execute("INSERT INTO parametres (cle, valeur) VALUES (?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", (k, v))
            db.commit()
            H.journal("reglages_messages")
            if request.form.get("tester"):
                ok, msg = notif.envoyer_sms(request.form.get("tel_test"), "Test GESCOL : la passerelle SMS fonctionne.")
                flash(("SMS de test envoyé. Réponse : " if ok else "Échec du SMS de test : ") + msg, "success" if ok else "danger")
            else:
                flash("Réglages enregistrés.", "success")
            return redirect(url_for("reglages_messages"))
        return render_template("reglages_messages.html", p=notif.params())

    # ============================================================ côté parents
    @app.route("/parent/connexion", methods=["GET", "POST"])
    def parent_login():
        if request.method == "POST":
            tel = notif.normaliser_tel(request.form.get("telephone"))
            cle = f"{tel}|{request.remote_addr}"
            if _trop_de_tentatives(cle):
                flash("Trop de tentatives. Réessayez dans 15 minutes.", "danger")
                return render_template("parent_login.html"), 429
            p = q("SELECT * FROM parents WHERE telephone=?", (tel,), un=True) if tel else None
            if p and p["actif"] and check_password_hash(p["mdp_hash"], request.form.get("mdp", "")):
                session.pop("uid", None)
                session["pid"] = p["id"]
                session.permanent = True
                ex("UPDATE parents SET dernier_acces=? WHERE id=?", (H.maintenant(), p["id"]))
                suivant = request.args.get("suivant", "")
                return redirect(suivant if suivant.startswith("/parent") else url_for("parent_accueil"))
            _echec(cle)
            flash("Numéro ou mot de passe incorrect.", "danger")
        return render_template("parent_login.html")

    @app.route("/parent/deconnexion")
    def parent_logout():
        session.pop("pid", None)
        return redirect(url_for("parent_login"))

    @app.route("/parent/mot-de-passe", methods=["GET", "POST"])
    @parent_requis
    def parent_mdp():
        if request.method == "POST":
            ancien, nouveau, conf = (request.form.get(k, "") for k in ("ancien", "nouveau", "confirmation"))
            if not check_password_hash(g.parent["mdp_hash"], ancien):
                flash("Mot de passe actuel incorrect.", "danger")
            elif len(nouveau) < 6:
                flash("Le nouveau mot de passe doit faire au moins 6 caractères.", "danger")
            elif nouveau != conf:
                flash("La confirmation ne correspond pas.", "danger")
            else:
                ex("UPDATE parents SET mdp_hash=?, doit_changer_mdp=0 WHERE id=?", (generate_password_hash(nouveau), g.parent["id"]))
                flash("Mot de passe enregistré.", "success")
                return redirect(url_for("parent_accueil"))
        return render_template("parent_mdp.html")

    def resume_enfant(e):
        cl = H.classe_de(e)
        du, paye, reste = H.situation(e)
        dernier = None
        if cl:
            pub = periodes_publiees(cl["id"])
            for i, per in enumerate(config.PERIODES, 1):
                if per in pub:
                    _, _, _, res, stats = H.resultats_classe(cl, per)
                    r = res.get(e["id"])
                    if r:
                        dernier = (i, per, r, stats)
        return dict(e=e, cl=cl, du=du, paye=paye, reste=reste, dernier=dernier, absences=H.absences_eleve(e["id"]))

    @app.route("/parent")
    @parent_requis
    def parent_accueil():
        enfants = [resume_enfant(e) for e in enfants_du_parent(g.parent["id"])]
        non_lus = q("SELECT COUNT(*) n FROM messages WHERE parent_id=? AND sens='ecole' AND lu=0", (g.parent["id"],), un=True)["n"]
        return render_template("parent_accueil.html", enfants=enfants, non_lus=non_lus,
                               paiement_actif=H.paiement_en_ligne_actif())

    @app.route("/parent/enfant/<int:eid>")
    @parent_requis
    def parent_enfant(eid):
        e = enfant_du_parent(eid)
        info = resume_enfant(e)
        cl = info["cl"]
        resultats = []
        if cl:
            pub = periodes_publiees(cl["id"])
            for i, per in enumerate(config.PERIODES, 1):
                if per in pub:
                    _, _, _, res, stats = H.resultats_classe(cl, per)
                    if e["id"] in res:
                        resultats.append((i, per, res[e["id"]], stats))
        d1, d2 = H.bornes_annee()
        absences = q("SELECT * FROM presences WHERE eleve_id=? AND date BETWEEN ? AND ? ORDER BY date DESC", (eid, d1, d2))
        paiements = q("SELECT * FROM paiements WHERE eleve_id=? AND annee=? AND annule=0 ORDER BY id DESC", (eid, config.ANNEE_ACTIVE))
        return render_template("parent_enfant.html", i=info, resultats=resultats, absences=absences, paiements=paiements,
                               paiement_actif=H.paiement_en_ligne_actif())

    @app.route("/parent/enfant/<int:eid>/bulletin/<int:p>.pdf")
    @parent_requis
    def parent_bulletin(eid, p):
        e = enfant_du_parent(eid)
        cl, per = H.classe_de(e), H.periode_de(p)
        if not cl or per not in periodes_publiees(cl["id"]):
            abort(404)
        _, _, _, res, stats = H.resultats_classe(cl, per)
        if eid not in res:
            abort(404)
        return H.pdf_reponse(H.pdfs.bulletins([app.bulletin_data(cl, per, e, res[eid], stats)]),
                             f"bulletin_{e['matricule']}_{per}.pdf")

    @app.route("/parent/recu/<int:pid>.pdf")
    @parent_requis
    def parent_recu(pid):
        pa = q("SELECT * FROM paiements WHERE id=?", (pid,), un=True)
        if not pa:
            abort(404)
        enfant_du_parent(pa["eleve_id"])
        return app.view_functions["recu"].__wrapped__(pid) if hasattr(app.view_functions["recu"], "__wrapped__") \
            else app.view_functions["recu"](pid)

    @app.route("/parent/messages", methods=["GET", "POST"])
    @parent_requis
    def parent_messages():
        enfants = enfants_du_parent(g.parent["id"])
        if request.method == "POST":
            sujet = request.form.get("sujet", "").strip()[:150]
            texte = request.form.get("texte", "").strip()[:1500]
            eid = request.form.get("eleve_id", type=int)
            if eid and eid not in {e["id"] for e in enfants}:
                abort(403)
            if not sujet or not texte:
                flash("Indiquez un sujet et un message.", "danger")
            else:
                ex("INSERT INTO messages (parent_id, eleve_id, sens, sujet, texte, cree_le) VALUES (?,?,?,?,?,?)",
                   (g.parent["id"], eid, "parent", sujet, texte, H.maintenant()))
                flash("Message envoyé à l'école.", "success")
                return redirect(url_for("parent_messages"))
        msgs = q("""SELECT m.*, e.prenoms FROM messages m LEFT JOIN eleves e ON e.id=m.eleve_id
                    WHERE m.parent_id=? ORDER BY m.id DESC LIMIT 100""", (g.parent["id"],))
        ex("UPDATE messages SET lu=1 WHERE parent_id=? AND sens='ecole' AND lu=0", (g.parent["id"],))
        return render_template("parent_messages.html", msgs=msgs, enfants=enfants)
