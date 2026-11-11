# -*- coding: utf-8 -*-
"""v1.33 — Versions partagées des contenus pédagogiques (épreuves, fiches de préparation, résumés).

Chaque enregistrement d'une épreuve modifiée, d'une fiche de préparation ou d'un résumé adapté par l'école est gardé
dans la base de l'école (table ``partage_versions``) avec son auteur et sa date : tous les comptes de l'école voient
la même version (plus de version « propre à un appareil »), l'historique permet de revenir à n'importe quelle
version précédente, et une version peut être « proposée » au niveau supérieur (CS / DDEMP) : elle part avec le
paquet de synchronisation (v2.0) et devient une « épreuve proposée » pour les autres écoles.

Les modules déclarent leurs types par ``H.partage_type(type, libelle, url, restaurer)`` et notent chaque
enregistrement par ``H.partage_noter(type, cle, titre, donnees)``.
"""
import json

from flask import abort, flash, g, redirect, render_template, request, url_for

GARDER = 30          # versions gardées par élément


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema("""CREATE TABLE IF NOT EXISTS partage_versions (
                    id INTEGER PRIMARY KEY, uuid TEXT, ecole_id INTEGER NOT NULL, type TEXT NOT NULL, cle TEXT NOT NULL, titre TEXT,
                    donnees TEXT NOT NULL, auteur_id INTEGER, auteur_nom TEXT, cree_le TEXT NOT NULL, note TEXT,
                    proposee INTEGER NOT NULL DEFAULT 0, proposee_le TEXT, origine TEXT DEFAULT 'ecole', maj TEXT);
                CREATE INDEX IF NOT EXISTS ix_partage_versions ON partage_versions(ecole_id, type, cle, id);""")
    TYPES = {}

    def partage_type(t, libelle, url, restaurer):
        TYPES[t] = {"libelle": libelle, "url": url, "restaurer": restaurer}

    def partage_noter(t, cle, titre, donnees, note=""):
        """Ajoute une version (sauf si elle est identique à la dernière)."""
        try:
            txt = donnees if isinstance(donnees, str) else json.dumps(donnees, ensure_ascii=False, sort_keys=True)
            der = q("SELECT donnees FROM partage_versions WHERE ecole_id=? AND type=? AND cle=? ORDER BY id DESC LIMIT 1",
                    (H.eco(), t, cle), un=True)
            if der and der["donnees"] == txt:
                return None
            u = g.get("user")
            import uuid as _uuid
            vid = ex("INSERT INTO partage_versions (uuid, ecole_id, type, cle, titre, donnees, auteur_id, auteur_nom, cree_le, note, maj) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (str(_uuid.uuid4()), H.eco(), t, cle, (titre or "")[:300], txt, u["id"] if u else None, (u["nom"] if u else "")[:120],
                      H.maintenant(), (note or "")[:300], H.maintenant()))
            vieux = q("SELECT id FROM partage_versions WHERE ecole_id=? AND type=? AND cle=? AND proposee=0 ORDER BY id DESC LIMIT -1 OFFSET ?",
                      (H.eco(), t, cle, GARDER))
            for r in vieux:
                ex("DELETE FROM partage_versions WHERE id=?", (r["id"],))
            return vid
        except Exception:  # noqa: BLE001 — l'historique ne doit jamais empêcher l'enregistrement
            app.logger.exception("Historique des versions")
            return None

    H.partage_type = partage_type
    H.partage_noter = partage_noter

    def peut_gerer():
        return g.user["role"] in ("enseignant", "directeur", "admin", "fondateur", "cp", "responsable", "chef_service")

    def peut_proposer():
        return g.user["role"] in ("directeur", "admin", "fondateur", "cp", "responsable", "chef_service")

    def type_ou_404(t):
        if t not in TYPES:
            abort(404)
        return TYPES[t]

    @app.route("/partage")
    @H.connexion_requise("preparation")
    def partage_accueil():
        t = request.args.get("type") or ""
        sql = ("SELECT v.* FROM partage_versions v JOIN (SELECT type, cle, MAX(id) mid FROM partage_versions WHERE ecole_id=? GROUP BY type, cle) d "
               "ON d.mid=v.id")
        a = [H.eco()]
        if t in TYPES:
            sql += " WHERE v.type=?"
            a.append(t)
        rows = [dict(r) for r in q(sql + " ORDER BY v.id DESC LIMIT 300", tuple(a))]
        for r in rows:
            r["n"] = q("SELECT COUNT(*) n FROM partage_versions WHERE ecole_id=? AND type=? AND cle=?", (H.eco(), r["type"], r["cle"]), un=True)["n"]
            try:
                r["url"] = TYPES[r["type"]]["url"](r["cle"]) if r["type"] in TYPES else None
            except Exception:  # noqa: BLE001
                r["url"] = None
        proposees = [dict(r) for r in q("SELECT * FROM partage_versions WHERE ecole_id=? AND proposee=1 ORDER BY proposee_le DESC LIMIT 200", (H.eco(),))]
        recues = [dict(r) for r in q("SELECT * FROM partage_versions WHERE origine NOT IN ('ecole') ORDER BY id DESC LIMIT 200")]
        return render_template("partage.html", rows=rows, TYPES=TYPES, t=t, proposees=proposees, recues=recues)

    @app.route("/partage/<t>/<path:cle>", methods=["GET", "POST"])
    @H.connexion_requise("preparation")
    def partage_historique(t, cle):
        T = type_ou_404(t)
        if request.method == "POST":
            if not peut_gerer():
                abort(403)
            vid = request.form.get("version", type=int)
            v = q("SELECT * FROM partage_versions WHERE id=? AND ecole_id=? AND type=? AND cle=?", (vid, H.eco(), t, cle), un=True)
            if not v:
                abort(404)
            act = request.form.get("action")
            if act == "restaurer":
                T["restaurer"](cle, json.loads(v["donnees"]))
                partage_noter(t, cle, v["titre"], v["donnees"], f"rétablie depuis la version du {v['cree_le']}")
                H.journal("partage_version_retablie", f"{t} {cle} v{vid}")
                flash(f"Version du {v['cree_le']} ({v['auteur_nom'] or '?'}) rétablie pour toute l'école.", "success")
            elif act in ("proposer", "retirer"):
                if not peut_proposer():
                    abort(403)
                ex("UPDATE partage_versions SET proposee=?, proposee_le=?, maj=? WHERE id=?",
                   (1 if act == "proposer" else 0, H.maintenant() if act == "proposer" else None, H.maintenant(), vid))
                H.journal("partage_version_" + act, f"{t} {cle} v{vid}")
                flash("Version proposée au niveau supérieur : elle partira avec la prochaine synchronisation." if act == "proposer"
                      else "Proposition retirée.", "success")
            return redirect(url_for("partage_historique", t=t, cle=cle))
        versions = [dict(r) for r in q("SELECT * FROM partage_versions WHERE ecole_id=? AND type=? AND cle=? ORDER BY id DESC", (H.eco(), t, cle))]
        try:
            url = T["url"](cle)
        except Exception:  # noqa: BLE001
            url = None
        return render_template("partage_historique.html", versions=versions, T=T, t=t, cle=cle, url=url,
                               peut_gerer=peut_gerer(), peut_proposer=peut_proposer())
