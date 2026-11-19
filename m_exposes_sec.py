# -*- coding: utf-8 -*-
"""v2.7 — Exposés du secondaire par cours et par matière.
Le professeur propose un exposé à sa classe (thème de la bibliothèque ou libre) ; les élèves, depuis leur espace, forment leur groupe,
rédigent et remettent ; la PAGE DE GARDE porte l'établissement, la matière, le thème, les NOMS DES ÉLÈVES, la classe et le professeur —
jamais le nom du concepteur. Exports PDF et Word. Le professeur lit, note et peut rouvrir un exposé."""
import json
import exposes_canevas as CV
from datetime import datetime

from flask import abort, flash, g, redirect, render_template, request, url_for

import config
import ens_mode as EM
import export_doc as E
import ressources_secondaire as R

SECTIONS = [("plan", "Plan de l'exposé"), ("introduction", "Introduction"), ("developpement", "Développement"),
            ("conclusion", "Conclusion"), ("sources", "Sources et bibliographie")]
ROLES_VOIR = ("admin", "directeur", "proviseur", "censeur", "surveillant general")


def enregistrer(app, H):
    from db import ex, q

    def garde():
        if not EM.bibliotheque_ouverte():
            abort(404)

    def js(t, defaut):
        try:
            return json.loads(t or "")
        except ValueError:
            return defaut

    def classe_mienne(cid):
        if not any(c["id"] == cid for c in H.classes_autorisees()):
            abort(404)

    def expose_prof(xid):
        x = q("SELECT * FROM exposes_sec WHERE id=?", (xid,), un=True)
        if not x:
            abort(404)
        if x["user_id"] != g.user["id"] and g.user["role"] not in ROLES_VOIR:
            abort(404)
        return x

    def membres(gr):
        ids = js(gr["eleve_ids"], [])
        if not ids:
            return []
        rows = q(f"SELECT id, nom, prenoms FROM eleves WHERE id IN ({','.join('?' * len(ids))}) ORDER BY nom, prenoms", tuple(ids))
        return [dict(r) for r in rows]

    def garde_data(gr):
        x = q("SELECT * FROM exposes_sec WHERE id=?", (gr["expose_id"],), un=True)
        cl = H.classe_ou_404(x["classe_id"])
        prof = q("SELECT nom FROM utilisateurs WHERE id=?", (x["user_id"],), un=True)
        return x, cl, (prof["nom"] if prof else ""), membres(gr)

    # ------------------------------------------------ document (page de garde + contenu) -> PDF / Word
    def blocs_expose(gr):
        x, cl, prof, mem = garde_data(gr)
        ident = H.identification()
        run = lambda t, gras=False: [(t, gras, False, False)]
        b = [{"type": "h", "niveau": 1, "runs": run(ident["ecole"] if ident and ident.get("ecole") else "")},
             {"type": "p", "runs": run(f"Année scolaire {ident['annee']}" if ident and ident.get("annee") else "")},
             {"type": "p", "runs": run("")}, {"type": "h", "niveau": 1, "runs": run("EXPOSÉ")},
             {"type": "h", "niveau": 1, "runs": run(x["matiere"])}, {"type": "p", "runs": run("")},
             {"type": "h", "niveau": 1, "runs": run(x["titre"])}, {"type": "p", "runs": run("")},
             {"type": "p", "runs": run("Présenté par :", True)}]
        b += [{"type": "li", "niveau": 1, "puce": "–", "runs": run(f"{m['nom'].upper()} {m['prenoms']}")} for m in mem]
        b += [{"type": "p", "runs": run("")}, {"type": "p", "runs": run(f"Classe : {cl['nom']}")}]
        if prof:
            b.append({"type": "p", "runs": run(f"Professeur : {prof}")})
        if x["remise"]:
            b.append({"type": "p", "runs": run(f"Date de remise : {x['remise']}")})
        c = js(gr["contenu"], {})
        premier = True
        for cle, lib in SECTIONS:
            if (c.get(cle) or "").strip():
                b.append({"type": "h", "niveau": 2, "runs": run(lib), "saut": premier})
                premier = False
                b += [{"type": "p", "runs": run(par)} for par in c[cle].strip().split("\n") if par.strip()]
        return b, f"Exposé – {x['titre']}"

    def reponse_doc(gr, fmt):
        b, titre = blocs_expose(gr)
        nom = "expose_" + "".join(ch if ch.isalnum() else "_" for ch in titre[8:48])
        if fmt == "pdf":
            return H.pdf_reponse(E.pdf(b, titre, None), nom + ".pdf")
        from flask import Response
        return Response(E.docx(b, titre, None), mimetype=E.KIT_DOCX, headers={"Content-Disposition": f"attachment; filename={nom}.docx"})

    # ================================================================ PROFESSEUR
    @app.route("/ens-sec/expose/nouveau", methods=["GET", "POST"])
    @H.connexion_requise("epreuves")
    def ens_sec_expose_nouveau():
        garde()
        cid, mid = request.args.get("cid", type=int), request.args.get("mid", type=int) or None
        if not cid:
            abort(404)
        classe_mienne(cid)
        cl = H.classe_ou_404(cid)
        m = q("SELECT nom FROM matieres WHERE id=?", (mid,), un=True) if mid else None
        pre = {"matiere": m["nom"] if m else "", "titre": "", "axes": "", "consigne": "", "remise": "", "taille_max": 4}
        t = request.args.get("theme", type=int)
        src = None
        if t is not None and 0 <= t < len(R.EXPOSES):
            e = R.EXPOSES[t]
            pre |= {"matiere": pre["matiere"] or e[0], "titre": e[2], "axes": e[3], "consigne": e[4]}
            src = f"theme:{t}"
        if request.method == "POST":
            f = request.form
            titre = (f.get("titre") or "").strip()
            if not titre:
                flash("Indiquez le thème de l'exposé.", "danger")
            else:
                xid = ex("INSERT INTO exposes_sec (user_id, classe_id, matiere_id, matiere, titre, axes, consigne, remise, taille_max, source) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (g.user["id"], cid, mid, (f.get("matiere") or "")[:120], titre[:300], (f.get("axes") or "")[:3000], (f.get("consigne") or "")[:3000],
                          (f.get("remise") or "")[:20], max(1, min(10, f.get("taille_max", type=int) or 4)), request.args.get("source") or src))
                H.journal("expose_propose", titre[:80])
                flash("Exposé proposé à la classe : les élèves le voient dans leur espace.", "success")
                return redirect(url_for("ens_sec_expose", xid=xid))
        return render_template("expose_form.html", cl=cl, mid=mid, v=pre, themes=R.EXPOSES, d=None)

    @app.route("/ens-sec/expose/<int:xid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("epreuves")
    def ens_sec_expose_modifier(xid):
        garde()
        x = expose_prof(xid)
        if request.method == "POST":
            f = request.form
            ex("UPDATE exposes_sec SET matiere=?, titre=?, axes=?, consigne=?, remise=?, taille_max=?, ouvert=? WHERE id=?",
               ((f.get("matiere") or "")[:120], (f.get("titre") or x["titre"])[:300], (f.get("axes") or "")[:3000], (f.get("consigne") or "")[:3000],
                (f.get("remise") or "")[:20], max(1, min(10, f.get("taille_max", type=int) or 4)), 1 if f.get("ouvert") else 0, xid))
            flash("Exposé modifié.", "success")
            return redirect(url_for("ens_sec_expose", xid=xid))
        return render_template("expose_form.html", cl=H.classe_ou_404(x["classe_id"]), mid=x["matiere_id"], v=dict(x), themes=None, d=x)

    @app.route("/ens-sec/expose/<int:xid>")
    @H.connexion_requise("epreuves")
    def ens_sec_expose(xid):
        garde()
        x = expose_prof(xid)
        cl = H.classe_ou_404(x["classe_id"])
        gr = [dict(r) | {"membres": membres(r)} for r in q("SELECT * FROM exposes_groupes WHERE expose_id=? ORDER BY id", (xid,))]
        pris = {m["id"] for r in gr for m in r["membres"]}
        sans = [e for e in q("SELECT id, nom, prenoms FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (x["classe_id"],)) if e["id"] not in pris]
        return render_template("expose_prof.html", x=x, cl=cl, groupes=gr, sans=sans)

    @app.route("/ens-sec/expose/<int:xid>/supprimer", methods=["POST"])
    @H.connexion_requise("epreuves")
    def ens_sec_expose_supprimer(xid):
        garde()
        x = expose_prof(xid)
        ex("DELETE FROM exposes_groupes WHERE expose_id=?", (xid,))
        ex("DELETE FROM exposes_sec WHERE id=?", (xid,))
        flash("Exposé supprimé.", "success")
        return redirect(url_for("ens_sec_cours", cid=x["classe_id"], mid=x["matiere_id"] or 0))

    def groupe_prof(gid):
        gr = q("SELECT * FROM exposes_groupes WHERE id=?", (gid,), un=True)
        if not gr:
            abort(404)
        expose_prof(gr["expose_id"])
        return gr

    @app.route("/ens-sec/expose/groupe/<int:gid>")
    @H.connexion_requise("epreuves")
    def ens_sec_expose_groupe(gid):
        garde()
        gr = groupe_prof(gid)
        x, cl, prof, mem = garde_data(gr)
        return render_template("expose_lecture.html", gr=gr, x=x, cl=cl, prof=prof, mem=mem, c=js(gr["contenu"], {}), S=SECTIONS,
                               ident=H.identification(), eleve=False)

    @app.route("/ens-sec/expose/groupe/<int:gid>.<fmt>")
    @H.connexion_requise("epreuves")
    def ens_sec_expose_groupe_doc(gid, fmt):
        garde()
        if fmt not in ("pdf", "docx"):
            abort(404)
        return reponse_doc(groupe_prof(gid), fmt)

    @app.route("/ens-sec/expose/groupe/<int:gid>/noter", methods=["POST"])
    @H.connexion_requise("epreuves")
    def ens_sec_expose_noter(gid):
        garde()
        gr = groupe_prof(gid)
        act = request.form.get("action")
        if act == "rouvrir":
            ex("UPDATE exposes_groupes SET statut='brouillon' WHERE id=?", (gid,))
            flash("Exposé rouvert : le groupe peut le modifier.", "success")
        else:
            ex("UPDATE exposes_groupes SET note=?, appreciation=? WHERE id=?",
               ((request.form.get("note") or "")[:10], (request.form.get("appreciation") or "")[:600], gid))
            flash("Note et appréciation enregistrées.", "success")
        return redirect(url_for("ens_sec_expose", xid=gr["expose_id"]))

    # ================================================================ ÉLÈVE
    ev = H.eleve_requis

    def moi():
        return g.eleve_session

    def canevas_de(x):
        """Canevas développé si l'exposé vient d'un thème de la bibliothèque (source « theme:N »)."""
        src = x["source"] or ""
        if src.startswith("theme:") and src[6:].isdigit() and int(src[6:]) < len(R.EXPOSES):
            return CV.canevas(R.EXPOSES[int(src[6:])])
        return None

    def guide_de(x):
        cv = canevas_de(x)
        return {cle: CV.texte_guide(cv, cle) for cle, _ in SECTIONS} if cv else {}

    def expose_eleve(xid):
        x = q("SELECT * FROM exposes_sec WHERE id=? AND classe_id=?", (xid, moi()["classe_id"]), un=True)
        if not x:
            abort(404)
        return x

    def mon_groupe(xid):
        for r in q("SELECT * FROM exposes_groupes WHERE expose_id=?", (xid,)):
            if moi()["id"] in js(r["eleve_ids"], []):
                return r
        return None

    @app.route("/eleve/exposes")
    @ev
    def eleve_exposes():
        garde()
        liste = []
        for x in q("SELECT * FROM exposes_sec WHERE classe_id=? ORDER BY ouvert DESC, id DESC", (moi()["classe_id"],)):
            liste.append((x, mon_groupe(x["id"])))
        return render_template("expose_eleve_liste.html", liste=liste)

    @app.route("/eleve/exposes/<int:xid>", methods=["GET", "POST"])
    @ev
    def eleve_expose(xid):
        garde()
        x = expose_eleve(xid)
        gr = mon_groupe(xid)
        if request.method == "POST" and not gr:                     # constitution du groupe
            if not x["ouvert"]:
                flash("Cet exposé est fermé.", "danger")
                return redirect(url_for("eleve_expose", xid=xid))
            choisis = {moi()["id"]}
            for v in request.form.getlist("membres"):
                if v.isdigit():
                    choisis.add(int(v))
            deja = {i for r in q("SELECT eleve_ids FROM exposes_groupes WHERE expose_id=?", (xid,)) for i in js(r["eleve_ids"], [])}
            valides = {e["id"] for e in q("SELECT id FROM eleves WHERE classe_id=? AND statut='inscrit'", (x["classe_id"],))}
            if choisis & deja or not choisis <= valides:
                flash("Un camarade choisi est déjà dans un autre groupe.", "danger")
            elif len(choisis) > x["taille_max"]:
                flash(f"Un groupe compte au plus {x['taille_max']} élève(s).", "danger")
            else:
                pre = {}
                cv = canevas_de(x)
                if cv:
                    pre = {"plan": CV.texte_plan(cv)}
                ex("INSERT INTO exposes_groupes (expose_id, eleve_ids, contenu) VALUES (?,?,?)", (xid, json.dumps(sorted(choisis)), json.dumps(pre, ensure_ascii=False)))
                flash("Groupe créé. Vous pouvez rédiger l'exposé.", "success")
            return redirect(url_for("eleve_expose", xid=xid))
        pris = {i for r in q("SELECT eleve_ids FROM exposes_groupes WHERE expose_id=?", (xid,)) for i in js(r["eleve_ids"], [])}
        libres = [e for e in q("SELECT id, nom, prenoms FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (x["classe_id"],))
                  if e["id"] not in pris and e["id"] != moi()["id"]] if not gr else []
        prof = q("SELECT nom FROM utilisateurs WHERE id=?", (x["user_id"],), un=True)
        return render_template("expose_eleve.html", x=x, gr=gr, mem=membres(gr) if gr else [], c=js(gr["contenu"], {}) if gr else {}, S=SECTIONS,
                               libres=libres, prof=prof["nom"] if prof else "", guide=guide_de(x))

    @app.route("/eleve/exposes/groupe/<int:gid>/enregistrer", methods=["POST"])
    @ev
    def eleve_expose_enregistrer(gid):
        garde()
        gr = q("SELECT * FROM exposes_groupes WHERE id=?", (gid,), un=True)
        if not gr or moi()["id"] not in js(gr["eleve_ids"], []):
            abort(404)
        if gr["statut"] == "remis":
            flash("Exposé déjà remis : demandez à votre professeur de le rouvrir pour le modifier.", "warning")
            return redirect(url_for("eleve_expose", xid=gr["expose_id"]))
        contenu = {cle: (request.form.get(cle) or "")[:20000] for cle, _ in SECTIONS}
        statut = "remis" if request.form.get("action") == "remettre" else "brouillon"
        ex("UPDATE exposes_groupes SET contenu=?, statut=?, maj_le=? WHERE id=?",
           (json.dumps(contenu, ensure_ascii=False), statut, datetime.now().isoformat(" ", "seconds"), gid))
        flash("Exposé remis au professeur." if statut == "remis" else "Brouillon enregistré.", "success")
        return redirect(url_for("eleve_expose", xid=gr["expose_id"]))

    def groupe_eleve(gid):
        gr = q("SELECT * FROM exposes_groupes WHERE id=?", (gid,), un=True)
        if not gr or moi()["id"] not in js(gr["eleve_ids"], []):
            abort(404)
        return gr

    @app.route("/eleve/exposes/groupe/<int:gid>/garde")
    @ev
    def eleve_expose_garde(gid):
        garde()
        gr = groupe_eleve(gid)
        x, cl, prof, mem = garde_data(gr)
        return render_template("expose_garde.html", x=x, cl=cl, prof=prof, mem=mem, ident=H.identification())

    @app.route("/eleve/exposes/groupe/<int:gid>.<fmt>")
    @ev
    def eleve_expose_doc(gid, fmt):
        garde()
        if fmt not in ("pdf", "docx"):
            abort(404)
        return reponse_doc(groupe_eleve(gid), fmt)

    @app.route("/ens-sec/expose/groupe/<int:gid>/garde")
    @H.connexion_requise("epreuves")
    def ens_sec_expose_garde(gid):
        garde()
        gr = groupe_prof(gid)
        x, cl, prof, mem = garde_data(gr)
        return render_template("expose_garde.html", x=x, cl=cl, prof=prof, mem=mem, ident=H.identification())
