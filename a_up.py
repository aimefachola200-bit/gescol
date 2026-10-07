# -*- coding: utf-8 -*-
"""Unités pédagogiques (UP) des applications « GESCOL Circonscription » (CS) et « GESCOL DDEMP » (v1.6).

Le client demande « le module des activités de l'unité pédagogique : nombre d'UP par zone pédagogique et total CS
et DDEMP, avec les noms et prénoms des responsables UP (RUP) et Co-RUP, le nombre d'activités prévues, exécutées,
les dates des UP dans la CS, les thèmes, pourcentage ».

Tables
    jur_up            une UP : circonscription (cs_id), zone pédagogique (zone_id), nom / numéro, école siège
                      (texte libre + jur_ecoles.id si connue), RUP et Co-RUP (nom, prénoms, téléphone), nombre
                      d'écoles membres, actif.
    jur_up_activites  une activité d'UP : up_id, année scolaire, date, thème, type (animation pédagogique, leçon
                      modèle, atelier…), prévue (1/0), exécutée (1/0), participants, taux de participation (%),
                      observations.

Règles de calcul (par UP, puis totaux par zone, par CS et général, pour l'année choisie)
    prévues   = nombre d'activités de l'année marquées « prévue »
    exécutées = nombre d'activités de l'année marquées « exécutée » (qu'elles aient été prévues ou non)
    taux d'exécution (%) = 100 × exécutées ÷ prévues, arrondi à 1 décimale ; « — » si aucune activité prévue
    dates = dates des activités de l'année (ordre chronologique) ; thèmes = thèmes de ces activités.
L'année scolaire d'une activité est déduite de sa date (septembre → août) ; à défaut de date, c'est l'année
indiquée à la saisie.

Pour la DDEMP : les paquets des CS (jur_format) ne transportent pas les UP ; la DDEMP saisit ses UP
(circonscription par circonscription) ou les importe par Excel (modèle téléchargeable : « Import » ; le fichier
exporté par une CS se réimporte tel quel). Fonctions exposées : H.jur_up_liste(annee, cs_id=None) → données du
tableau ; H.jur_up_export(annee, cs_id=None) → (feuilles Excel) ; H.jur_up_import(entetes, lignes, cs_id=None)
→ (nb_up, nb_activites, erreurs).

Routes (édition cs / ddemp)
    jur_up                    /juridiction/up                              tableau par zone (CS) ou par CS puis zone (DDEMP)
    jur_up_form               /juridiction/up/nouvelle | /up/<id>/modifier  GET/POST  (droit jur_up)
    jur_up_supprimer          /juridiction/up/<id>/supprimer               POST      (droit jur_up)
    jur_up_fiche              /juridiction/up/<id>                         fiche de l'UP et ses activités de l'année
    jur_up_activite_form      /juridiction/up/<id>/activites/nouvelle | /up/activites/<aid>/modifier   (droit jur_up)
    jur_up_activite_supprimer /juridiction/up/activites/<aid>/supprimer    POST      (droit jur_up)
    jur_up_import             /juridiction/up/import  (GET : page, ?modele=1 : modèle Excel ; POST : fichier)
    jur_up_xlsx               /juridiction/up.xlsx
    jur_up_pdf                /juridiction/up.pdf      (paysage, en-tête officiel, signé par le responsable)
"""
import re
from datetime import date, datetime

from flask import abort, flash, redirect, render_template, request, url_for

import config
import jur_calc as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_up (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cs_id INTEGER, zone_id INTEGER,
    nom TEXT NOT NULL,                    -- nom ou numéro de l'UP (ex. « UP 3 », « UP de Towé »)
    ecole_siege TEXT, ecole_id INTEGER,   -- école siège (texte) et, si connue, jur_ecoles.id
    rup_nom TEXT, rup_tel TEXT, corup_nom TEXT, corup_tel TEXT,
    nb_ecoles INTEGER, observations TEXT,
    actif INTEGER DEFAULT 1, cree_le TEXT, maj TEXT);
CREATE INDEX IF NOT EXISTS i_jur_up ON jur_up(cs_id, zone_id);
CREATE TABLE IF NOT EXISTS jur_up_activites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    up_id INTEGER NOT NULL, annee TEXT NOT NULL, date TEXT, theme TEXT, type TEXT,
    prevue INTEGER DEFAULT 1, executee INTEGER DEFAULT 0,
    participants INTEGER, taux_participation REAL, observations TEXT, maj TEXT);
CREATE INDEX IF NOT EXISTS i_jur_up_act ON jur_up_activites(up_id, annee);
"""

TYPES_ACTIVITE = ["Animation pédagogique", "Leçon modèle", "Atelier", "Formation", "Évaluation harmonisée",
                  "Journée pédagogique", "Autre"]
RE_ANNEE = re.compile(r"^\d{4}-\d{4}$")


# ======================================================================== outils purs
def lire_date(v):
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    return None


def annee_de(d):
    return f"{d.year}-{d.year + 1}" if d.month >= 9 else f"{d.year - 1}-{d.year}"


def oui(v):
    t = str(v if v is not None else "").strip().lower()
    return t in ("1", "oui", "o", "x", "vrai", "true", "yes", "y", "✓")


def taux_execution(prevues, executees):
    """100 × exécutées ÷ prévues (1 décimale) ; None sans activité prévue."""
    return round(100.0 * executees / prevues, 1) if prevues else None


def date_fr(iso):
    d = lire_date(iso)
    return d.strftime("%d/%m/%Y") if d else (iso or "")


def pct(v):
    return "—" if v is None else (f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " %")


# ======================================================================== module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    def juridiction_ou_404():
        if not config.juridiction():
            abort(404)

    def cs_courante_id():
        c = H.jur_cs_courante() if config.EDITION == "cs" else None
        return c["id"] if c else None

    def annee_demandee(args):
        a = (args.get("annee") or "").strip()
        return a if RE_ANNEE.match(a) else H.jur_annee()

    def annees_dispo():
        a = set(H.jur_annees()) | {r["annee"] for r in q("SELECT DISTINCT annee FROM jur_up_activites")}
        return sorted(a, reverse=True)

    def cs_filtre(args):
        if config.EDITION == "cs":
            return cs_courante_id()
        cid = args.get("cs", type=int)
        return cid if cid and H.jur_cs(cid) else None

    # ------------------------------------------------------------------ données
    def up_rows(cs_id=None, actif=True):
        sql = ("SELECT u.*, c.nom cs_nom, c.numero cs_numero, z.nom zone_nom, z.ordre zone_ordre FROM jur_up u "
               "LEFT JOIN jur_cs c ON c.id=u.cs_id LEFT JOIN jur_zones z ON z.id=u.zone_id WHERE 1=1")
        args = []
        if actif:
            sql += " AND u.actif=1"
        if cs_id:
            sql += " AND u.cs_id=?"
            args.append(cs_id)
        return q(sql + " ORDER BY c.numero, c.nom, z.ordre, z.nom, u.nom", tuple(args))

    def up_ou_404(uid):
        r = q("SELECT u.*, c.nom cs_nom, z.nom zone_nom FROM jur_up u LEFT JOIN jur_cs c ON c.id=u.cs_id "
              "LEFT JOIN jur_zones z ON z.id=u.zone_id WHERE u.id=?", (uid,), un=True)
        if not r:
            abort(404)
        cid = cs_courante_id()
        if cid and r["cs_id"] and r["cs_id"] != cid:
            abort(404)
        return r

    def activites(annee, up_ids=None):
        """{up_id: [activités de l'année, par date]}"""
        rows = q("SELECT * FROM jur_up_activites WHERE annee=? ORDER BY date, id", (annee,))
        out = {}
        for r in rows:
            if up_ids is not None and r["up_id"] not in up_ids:
                continue
            out.setdefault(r["up_id"], []).append(dict(r))
        return out

    def stats_up(acts):
        prev = sum(1 for a in acts if a["prevue"])
        exe = sum(1 for a in acts if a["executee"])
        return {"activites": len(acts), "prevues": prev, "executees": exe, "taux": taux_execution(prev, exe),
                "dates": [a["date"] for a in acts if a["date"]],
                "themes": [a["theme"] for a in acts if a["theme"]],
                "participants": sum(C.entier(a["participants"]) for a in acts)}

    def cumul(lignes):
        prev = sum(l["prevues"] for l in lignes)
        exe = sum(l["executees"] for l in lignes)
        return {"up": len(lignes), "activites": sum(l["activites"] for l in lignes), "prevues": prev, "executees": exe,
                "taux": taux_execution(prev, exe), "participants": sum(l["participants"] for l in lignes),
                "ecoles": sum(C.entier(l["nb_ecoles"]) for l in lignes)}

    def liste(annee, cs_id=None):
        """Données du tableau : {"annee", "ups": [UP + stats], "zones": [{cs_id, cs_nom, zone_id, zone, ups, tot}],
        "cs": [{cs_id, cs_nom, zones, tot}] (DDEMP), "tot": totaux généraux}."""
        ups = [dict(r) for r in up_rows(cs_id)]
        acts = activites(annee, {u["id"] for u in ups})
        for u in ups:
            u.update(stats_up(acts.get(u["id"], [])))
            u["acts"] = acts.get(u["id"], [])
        zones_ref = {z["id"]: z for z in H.jur_zones()}
        # zones de la juridiction (même sans UP) pour que le « nombre d'UP par zone » soit complet
        zones = []
        cles = {}
        for z in H.jur_zones(cs_id) if cs_id else H.jur_zones():
            d = {"cs_id": z["cs_id"], "cs_nom": z["cs_nom"], "zone_id": z["id"], "zone": z["nom"], "ups": []}
            cles[(z["cs_id"], z["id"])] = d
            zones.append(d)
        for u in ups:
            k = (u["cs_id"], u["zone_id"])
            if k not in cles:
                d = {"cs_id": u["cs_id"], "cs_nom": u["cs_nom"] or "", "zone_id": u["zone_id"],
                     "zone": (zones_ref.get(u["zone_id"]) or {"nom": "Sans zone pédagogique"})["nom"] if u["zone_id"]
                     else "Sans zone pédagogique", "ups": []}
                cles[k] = d
                zones.append(d)
            cles[k]["ups"].append(u)
        for d in zones:
            d["tot"] = cumul(d["ups"])
        par_cs = []
        if config.EDITION == "ddemp":
            for c in H.jur_cs_liste():
                if cs_id and c["id"] != cs_id:
                    continue
                zc = [d for d in zones if d["cs_id"] == c["id"]]
                par_cs.append({"cs_id": c["id"], "cs_nom": c["nom"], "zones": zc,
                               "tot": cumul([u for d in zc for u in d["ups"]])})
            orphelines = [d for d in zones if not any(d["cs_id"] == c["cs_id"] for c in par_cs)]
            if orphelines:
                par_cs.append({"cs_id": None, "cs_nom": "Sans circonscription", "zones": orphelines,
                               "tot": cumul([u for d in orphelines for u in d["ups"]])})
        return {"annee": annee, "ups": ups, "zones": zones, "cs": par_cs, "tot": cumul(ups)}

    H.jur_up_liste = liste

    # ------------------------------------------------------------------ droits
    def saisie():
        return H.peut("jur_up")

    def exiger_saisie():
        if not saisie():
            abort(403)

    # ------------------------------------------------------------------ tableau
    @app.route("/juridiction/up")
    @H.connexion_requise()
    def jur_up():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        cs_id = cs_filtre(request.args)
        d = liste(annee, cs_id)
        return render_template("jur_up.html", d=d, annee=annee, annees=annees_dispo(), cs=H.jur_cs_liste(), cs_id=cs_id,
                               saisie=saisie(), pct=pct, date_fr=date_fr)

    # ------------------------------------------------------------------ fiche d'une UP
    @app.route("/juridiction/up/<int:uid>")
    @H.connexion_requise()
    def jur_up_fiche(uid):
        juridiction_ou_404()
        u = dict(up_ou_404(uid))
        annee = annee_demandee(request.args)
        acts = activites(annee, {uid}).get(uid, [])
        u.update(stats_up(acts))
        toutes = {r["annee"] for r in q("SELECT DISTINCT annee FROM jur_up_activites WHERE up_id=?", (uid,))}
        return render_template("jur_up_fiche.html", u=u, acts=acts, annee=annee, annees=sorted(set(annees_dispo()) | toutes, reverse=True),
                               saisie=saisie(), pct=pct, date_fr=date_fr)

    # ------------------------------------------------------------------ saisie d'une UP
    def lire_form_up(f, u=None):
        err = []
        d = {k: (f.get(k) or "").strip()[:150] for k in ("nom", "ecole_siege", "rup_nom", "rup_tel", "corup_nom", "corup_tel")}
        d["observations"] = (f.get("observations") or "").strip()[:2000]
        if not d["nom"]:
            err.append("Indiquez le nom ou le numéro de l'UP.")
        if config.EDITION == "cs":
            cs_id = cs_courante_id()
        else:
            cs_id = f.get("cs_id", type=int)
            if not cs_id or not H.jur_cs(cs_id):
                err.append("Choisissez la circonscription scolaire.")
                cs_id = None
        zone_id = f.get("zone_id", type=int) or None
        if zone_id and cs_id and not q("SELECT 1 FROM jur_zones WHERE id=? AND cs_id=?", (zone_id, cs_id), un=True):
            err.append("La zone pédagogique ne correspond pas à la circonscription.")
        ecole_id = f.get("ecole_id", type=int) or None
        if ecole_id:
            e = H.jur_ecole(ecole_id)
            if not e or (cs_id and e["cs_id"] != cs_id):
                err.append("École siège inconnue dans cette circonscription.")
                ecole_id = None
            elif not d["ecole_siege"]:
                d["ecole_siege"] = e["nom"]
        nb = (f.get("nb_ecoles") or "").strip()
        if nb and not nb.isdigit():
            err.append("Nombre d'écoles : nombre entier attendu.")
        d.update(cs_id=cs_id, zone_id=zone_id, ecole_id=ecole_id, nb_ecoles=int(nb) if nb.isdigit() else None)
        if cs_id and d["nom"] and q("SELECT 1 FROM jur_up WHERE cs_id=? AND actif=1 AND lower(nom)=lower(?) AND id<>?",
                                    (cs_id, d["nom"], u["id"] if u else 0), un=True):
            err.append(f"Une UP « {d['nom']} » existe déjà dans cette circonscription.")
        return d, err

    CHAMPS_UP = ("cs_id", "zone_id", "nom", "ecole_siege", "ecole_id", "rup_nom", "rup_tel", "corup_nom", "corup_tel",
                 "nb_ecoles", "observations")

    def rendu_form_up(v, u=None, code=200):
        cid = v.get("cs_id") or cs_courante_id()
        return render_template("jur_up_form.html", v=v, u=u, cs=H.jur_cs_liste(), zones=H.jur_zones(cid) if cid else H.jur_zones(),
                               ecoles=H.jur_ecoles(cs_id=cid) if cid else H.jur_ecoles()), code

    @app.route("/juridiction/up/nouvelle", methods=["GET", "POST"])
    @app.route("/juridiction/up/<int:uid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("jur_up")
    def jur_up_form(uid=None):
        juridiction_ou_404()
        u = up_ou_404(uid) if uid else None
        if request.method == "POST":
            d, err = lire_form_up(request.form, u)
            if err:
                for m in err:
                    flash(m, "danger")
                return rendu_form_up(dict(request.form.items(), cs_id=d["cs_id"]), u, 400)
            if u:
                ex("UPDATE jur_up SET " + ", ".join(f"{k}=?" for k in CHAMPS_UP) + ", maj=? WHERE id=?",
                   tuple(d[k] for k in CHAMPS_UP) + (H.maintenant(), uid))
                H.journal("jur_up_modif", f"{uid} {d['nom']}")
                flash("Unité pédagogique mise à jour.", "success")
            else:
                uid = ex("INSERT INTO jur_up (" + ", ".join(CHAMPS_UP) + ", actif, cree_le, maj) VALUES (" +
                         ",".join("?" * len(CHAMPS_UP)) + ",1,?,?)", tuple(d[k] for k in CHAMPS_UP) + (H.maintenant(), H.maintenant()))
                H.journal("jur_up_ajout", f"{uid} {d['nom']}")
                flash("Unité pédagogique enregistrée.", "success")
            return redirect(url_for("jur_up_fiche", uid=uid))
        if u:
            return rendu_form_up(dict(u), u)
        v = {"cs_id": cs_courante_id() if config.EDITION == "cs" else request.args.get("cs", type=int),
             "zone_id": request.args.get("zone", type=int)}
        return rendu_form_up(v)

    @app.route("/juridiction/up/<int:uid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_up")
    def jur_up_supprimer(uid):
        juridiction_ou_404()
        u = up_ou_404(uid)
        ex("DELETE FROM jur_up_activites WHERE up_id=?", (uid,))
        ex("DELETE FROM jur_up WHERE id=?", (uid,))
        H.journal("jur_up_suppression", f"{uid} {u['nom']}")
        flash(f"UP « {u['nom']} » supprimée avec ses activités.", "warning")
        return redirect(url_for("jur_up", cs=u["cs_id"] if config.EDITION == "ddemp" else None))

    # ------------------------------------------------------------------ activités
    def lire_form_act(f, annee_defaut):
        err = []
        d = {"theme": (f.get("theme") or "").strip()[:300], "type": (f.get("type") or "").strip()[:80],
             "observations": (f.get("observations") or "").strip()[:2000],
             "prevue": 1 if f.get("prevue") else 0, "executee": 1 if f.get("executee") else 0}
        dt = (f.get("date") or "").strip()
        if dt:
            dd = lire_date(dt)
            if not dd:
                err.append("Date invalide (format AAAA-MM-JJ).")
                dd = None
            d["date"] = dd.isoformat() if dd else ""
            d["annee"] = annee_de(dd) if dd else annee_defaut
        else:
            d["date"], d["annee"] = "", (f.get("annee") or "").strip() if RE_ANNEE.match((f.get("annee") or "").strip()) else annee_defaut
        if not d["theme"] and not d["date"]:
            err.append("Indiquez au moins la date ou le thème de l'activité.")
        if not d["prevue"] and not d["executee"]:
            err.append("Cochez « prévue » et/ou « exécutée ».")
        p = (f.get("participants") or "").strip()
        if p and not p.isdigit():
            err.append("Participants : nombre entier attendu.")
        d["participants"] = int(p) if p.isdigit() else None
        t = (f.get("taux_participation") or "").strip().replace(",", ".")
        try:
            d["taux_participation"] = round(float(t), 1) if t else None
            if d["taux_participation"] is not None and not 0 <= d["taux_participation"] <= 100:
                raise ValueError(t)
        except ValueError:
            err.append("Taux de participation : nombre entre 0 et 100.")
            d["taux_participation"] = None
        return d, err

    CHAMPS_ACT = ("annee", "date", "theme", "type", "prevue", "executee", "participants", "taux_participation", "observations")

    def act_ou_404(aid):
        a = q("SELECT * FROM jur_up_activites WHERE id=?", (aid,), un=True)
        if not a:
            abort(404)
        return a

    @app.route("/juridiction/up/<int:uid>/activites/nouvelle", methods=["GET", "POST"])
    @app.route("/juridiction/up/activites/<int:aid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("jur_up")
    def jur_up_activite_form(uid=None, aid=None):
        juridiction_ou_404()
        a = act_ou_404(aid) if aid else None
        u = up_ou_404(a["up_id"] if a else uid)
        annee = annee_demandee(request.args)
        if request.method == "POST":
            d, err = lire_form_act(request.form, annee)
            if err:
                for m in err:
                    flash(m, "danger")
                return render_template("jur_up_activite_form.html", u=u, a=a, v=dict(request.form.items()), annee=annee,
                                       TYPES=TYPES_ACTIVITE, aujourdhui=date.today().isoformat()), 400
            if a:
                ex("UPDATE jur_up_activites SET " + ", ".join(f"{k}=?" for k in CHAMPS_ACT) + ", maj=? WHERE id=?",
                   tuple(d[k] for k in CHAMPS_ACT) + (H.maintenant(), aid))
                H.journal("jur_up_activite_modif", f"{aid} {u['nom']} {d['date']} {d['theme']}")
                flash("Activité mise à jour.", "success")
            else:
                aid = ex("INSERT INTO jur_up_activites (up_id, " + ", ".join(CHAMPS_ACT) + ", maj) VALUES (?," +
                         ",".join("?" * len(CHAMPS_ACT)) + ",?)", (u["id"],) + tuple(d[k] for k in CHAMPS_ACT) + (H.maintenant(),))
                H.journal("jur_up_activite_ajout", f"{aid} {u['nom']} {d['date']} {d['theme']}")
                flash("Activité enregistrée.", "success")
            return redirect(url_for("jur_up_fiche", uid=u["id"], annee=d["annee"]))
        v = dict(a) if a else {"date": "", "prevue": 1, "executee": 0, "annee": annee, "type": TYPES_ACTIVITE[0]}
        return render_template("jur_up_activite_form.html", u=u, a=a, v=v, annee=annee, TYPES=TYPES_ACTIVITE,
                               aujourdhui=date.today().isoformat())

    @app.route("/juridiction/up/activites/<int:aid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_up")
    def jur_up_activite_supprimer(aid):
        juridiction_ou_404()
        a = act_ou_404(aid)
        u = up_ou_404(a["up_id"])
        ex("DELETE FROM jur_up_activites WHERE id=?", (aid,))
        H.journal("jur_up_activite_suppression", f"{aid} {u['nom']} {a['date']} {a['theme']}")
        flash("Activité supprimée.", "warning")
        return redirect(url_for("jur_up_fiche", uid=u["id"], annee=a["annee"]))

    # ------------------------------------------------------------------ Excel : export / modèle / import
    ENT_UP = ["Circonscription", "Zone pédagogique", "UP", "École siège", "RUP (nom et prénoms)", "Téléphone RUP",
              "Co-RUP (nom et prénoms)", "Téléphone Co-RUP", "Nombre d'écoles", "Activités prévues", "Activités exécutées",
              "Taux d'exécution (%)", "Dates", "Thèmes", "Observations"]
    ENT_ACT = ["Circonscription", "Zone pédagogique", "UP", "Date", "Thème", "Type", "Prévue (oui/non)", "Exécutée (oui/non)",
               "Participants", "Taux de participation (%)", "Observations"]

    def feuilles_export(annee, cs_id=None):
        d = liste(annee, cs_id)
        s = H.jur_structure() or {}
        haut = [s.get("nom") or "", f"Unités pédagogiques – activités de l'année {annee}"]
        l_up = [[u["cs_nom"] or "", u["zone_nom"] or "", u["nom"], u["ecole_siege"] or "", u["rup_nom"] or "", u["rup_tel"] or "",
                 u["corup_nom"] or "", u["corup_tel"] or "", u["nb_ecoles"], u["prevues"], u["executees"], u["taux"],
                 ", ".join(date_fr(x) for x in u["dates"]), " ; ".join(u["themes"]), u["observations"] or ""] for u in d["ups"]]
        t = d["tot"]
        l_up.append(["TOTAL", "", f"{t['up']} UP", "", "", "", "", "", t["ecoles"], t["prevues"], t["executees"], t["taux"], "", "", ""])
        l_act = [[u["cs_nom"] or "", u["zone_nom"] or "", u["nom"], a["date"] or "", a["theme"] or "", a["type"] or "",
                  "oui" if a["prevue"] else "non", "oui" if a["executee"] else "non", a["participants"], a["taux_participation"],
                  a["observations"] or ""] for u in d["ups"] for a in u["acts"]]
        l_z = [[z["cs_nom"], z["zone"], z["tot"]["up"], z["tot"]["ecoles"], z["tot"]["prevues"], z["tot"]["executees"], z["tot"]["taux"]]
               for z in d["zones"]]
        l_z.append(["TOTAL", "", t["up"], t["ecoles"], t["prevues"], t["executees"], t["taux"]])
        return [("Unités pédagogiques", ENT_UP, l_up, {"titre_haut": haut}),
                ("Activités", ENT_ACT, l_act, {"titre_haut": haut}),
                ("Par zone", ["Circonscription", "Zone pédagogique", "UP", "Écoles", "Prévues", "Exécutées", "Taux (%)"], l_z,
                 {"titre_haut": haut})]

    H.jur_up_export = feuilles_export

    @app.route("/juridiction/up.xlsx")
    @H.connexion_requise()
    def jur_up_xlsx():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        H.journal("jur_up_xlsx", annee)
        return H.xlsx.reponse_classeur(f"unites_pedagogiques_{annee}.xlsx", feuilles_export(annee, cs_filtre(request.args)))

    def importer(ent, lignes, cs_id=None, annee_defaut=None):
        """Import Excel : une ligne = une UP (créée ou mise à jour : même CS + même nom) + éventuellement une activité
        (colonnes Date / Thème…). Renvoie (nb_up, nb_activites, erreurs)."""
        col = lambda *n: H.xlsx.colonne(ent, *n)  # noqa: E731
        i_cs, i_zone, i_up = col("circonscription", "cs"), col("zone"), col("up", "unite pedagogique", "unité pédagogique", "nom")
        i_siege, i_rup, i_rupt = col("ecole siege", "école siège", "siege"), col("rup (nom", "rup", "responsable"), col("telephone rup", "tel rup")
        i_corup, i_corupt, i_nb = col("co-rup (nom", "co-rup", "corup"), col("telephone co-rup", "tel co-rup"), col("nombre d'ecoles", "nb ecoles", "ecoles")
        i_date, i_theme, i_type = col("date"), col("theme", "thème"), col("type")
        i_prev, i_exe, i_part = col("prevue", "prévue"), col("executee", "exécutée"), col("participants")
        i_taux, i_obs = col("taux de participation", "taux"), col("observations")
        if col("activites prevues", "activités prévues") is not None:
            # feuille de synthèse (export « Unités pédagogiques ») : colonnes « Dates » / « Thèmes » = listes, pas une activité
            i_date = i_theme = i_type = i_prev = i_exe = i_part = i_taux = None
        if i_up is None:
            return 0, 0, ["Colonne « UP » introuvable."]
        s = H.jur_structure() or {}
        import m_juridiction as J
        nb_up, nb_act, err = 0, 0, []
        annee_defaut = annee_defaut or H.jur_annee()
        for n, l in enumerate(lignes, start=2):
            v = lambda i: H.xlsx.valeur(l, i)  # noqa: E731
            nom = v(i_up)
            if not nom or nom.upper() == "TOTAL":
                continue
            if config.EDITION == "cs":
                cid = cs_courante_id()
            else:
                c = J._trouver_cs(s.get("departement"), v(i_cs), creer=False) if v(i_cs) else (H.jur_cs(cs_id) if cs_id else None)
                if not c:
                    err.append(f"Ligne {n} : circonscription « {v(i_cs)} » introuvable.")
                    continue
                cid = c["id"]
            zid = J._trouver_zone(cid, v(i_zone)) if v(i_zone) else None
            r = q("SELECT id FROM jur_up WHERE cs_id=? AND lower(nom)=lower(?)", (cid, nom), un=True)
            ecole_id = None
            if v(i_siege):
                for e in H.jur_ecoles(cs_id=cid):
                    if J.norm(e["nom"]) == J.norm(v(i_siege)) or (e["code"] and e["code"].upper() == v(i_siege).upper()):
                        ecole_id = e["id"]
                        break
            nb = v(i_nb)
            vals = {"cs_id": cid, "zone_id": zid, "nom": nom[:150], "ecole_siege": v(i_siege)[:150], "ecole_id": ecole_id,
                    "rup_nom": v(i_rup)[:150], "rup_tel": v(i_rupt)[:40], "corup_nom": v(i_corup)[:150], "corup_tel": v(i_corupt)[:40],
                    "nb_ecoles": int(float(nb)) if re.match(r"^\d+(\.0+)?$", nb) else None,
                    "observations": v(i_obs)[:2000] if i_date is None else ""}
            if r:
                uid = r["id"]
                sets = {k: x for k, x in vals.items() if x not in ("", None) or k in ("zone_id", "ecole_id")}
                ex("UPDATE jur_up SET " + ", ".join(f"{k}=?" for k in sets) + ", actif=1, maj=? WHERE id=?",
                   tuple(sets.values()) + (H.maintenant(), uid))
            else:
                uid = ex("INSERT INTO jur_up (" + ", ".join(vals) + ", actif, cree_le, maj) VALUES (" + ",".join("?" * len(vals)) + ",1,?,?)",
                         tuple(vals.values()) + (H.maintenant(), H.maintenant()))
            nb_up += 1
            dt, theme = (v(i_date) if i_date is not None else ""), (v(i_theme) if i_theme is not None else "")
            if dt or theme:
                dd = lire_date(dt)
                if dt and not dd:
                    err.append(f"Ligne {n} : date « {dt} » invalide.")
                    continue
                iso = dd.isoformat() if dd else ""
                an = annee_de(dd) if dd else annee_defaut
                if q("SELECT 1 FROM jur_up_activites WHERE up_id=? AND annee=? AND date=? AND lower(theme)=lower(?)",
                     (uid, an, iso, theme), un=True):
                    continue
                prev = oui(v(i_prev)) if i_prev is not None and v(i_prev) else 1
                exe = oui(v(i_exe)) if i_exe is not None else 0
                part = v(i_part)
                taux = v(i_taux).replace(",", ".")
                ex("INSERT INTO jur_up_activites (up_id, annee, date, theme, type, prevue, executee, participants, taux_participation, "
                   "observations, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (uid, an, iso, theme[:300], v(i_type)[:80], 1 if prev else 0, 1 if exe else 0,
                    int(float(part)) if re.match(r"^\d+(\.0+)?$", part) else None,
                    round(float(taux), 1) if re.match(r"^\d+(\.\d+)?$", taux) else None, v(i_obs)[:2000], H.maintenant()))
                nb_act += 1
        return nb_up, nb_act, err

    H.jur_up_import = importer

    @app.route("/juridiction/up/import", methods=["GET", "POST"])
    @H.connexion_requise("jur_up")
    def jur_up_import():
        juridiction_ou_404()
        s = H.jur_structure() or {}
        if request.args.get("modele"):
            cs_nom = s.get("cs") or (H.jur_cs_liste()[0]["nom"] if H.jur_cs_liste() else "")
            ex_ = [[cs_nom, "Zone pédagogique 1", "UP 1", "EPP Exemple", "KOUTON Basile", "0197000000", "OLOU Rosine", "",
                    6, "2026-10-15", "Planification des SA en mathématiques", "Animation pédagogique", "oui", "non", "", "", ""],
                   [cs_nom, "Zone pédagogique 1", "UP 1", "", "", "", "", "", "", "2026-11-12", "Leçon modèle de lecture au CI",
                    "Leçon modèle", "oui", "oui", 14, 87.5, ""]]
            return H.xlsx.reponse_xlsx("modele_unites_pedagogiques.xlsx", ENT_UP[:9] + ENT_ACT[3:], ex_, "UP et activités",
                                       ["Modèle d'import des unités pédagogiques : une ligne par activité (les lignes d'une même UP "
                                        "répètent son nom) ; une UP sans activité = une ligne sans date ni thème."])
        if request.method == "POST":
            fic = request.files.get("fichier")
            if not fic or not fic.filename.lower().endswith((".xlsx", ".csv")):
                flash("Choisissez un fichier Excel (.xlsx).", "danger")
                return redirect(url_for("jur_up_import"))
            try:
                ent, lignes = H.xlsx.lire_tableau(fic, ("up", "unité pédagogique", "unite pedagogique"))
            except H.xlsx.ExcelIndisponible as e_:
                flash(str(e_), "danger")
                return redirect(url_for("jur_up_import"))
            except Exception:  # noqa: BLE001
                flash("Fichier Excel illisible.", "danger")
                return redirect(url_for("jur_up_import"))
            nb_up, nb_act, err = importer(ent, lignes, request.form.get("cs_id", type=int), annee_demandee(request.form))
            for m in err[:15]:
                flash(m, "warning")
            flash(f"{nb_up} ligne(s) d'UP traitée(s), {nb_act} activité(s) ajoutée(s).", "success" if nb_up else "warning")
            H.journal("jur_up_import", f"{nb_up} UP, {nb_act} activités")
            return redirect(url_for("jur_up"))
        return render_template("jur_up_import.html", cs=H.jur_cs_liste(), annee=H.jur_annee(), annees=annees_dispo())

    # ------------------------------------------------------------------ PDF
    def signataire():
        s = H.jur_structure() or {}
        titre = (s.get("responsable_titre") or ("Le Chef de la Circonscription Scolaire" if config.EDITION == "cs"
                                                 else "Le Directeur Départemental")).upper()
        return titre, s.get("responsable_nom") or "", H.pdfs.image_data_url(H.signature("jur:structure:responsable"))

    @app.route("/juridiction/up.pdf")
    @H.connexion_requise()
    def jur_up_pdf():
        juridiction_ou_404()
        annee = annee_demandee(request.args)
        cs_id = cs_filtre(request.args)
        d = liste(annee, cs_id)
        s = H.jur_structure() or {}
        P = H.pdfs
        ddemp = config.EDITION == "ddemp"
        ent = (["CS"] if ddemp else []) + ["Zone pédagogique", "UP", "École siège", "RUP", "Co-RUP", "Écoles", "Prévues",
                                           "Exécutées", "Taux", "Dates des activités", "Thèmes"]
        rows = []
        for u in d["ups"]:
            rows.append(([u["cs_nom"] or ""] if ddemp else []) +
                        [u["zone_nom"] or "—", u["nom"], u["ecole_siege"] or "", u["rup_nom"] or "", u["corup_nom"] or "",
                         u["nb_ecoles"] if u["nb_ecoles"] is not None else "", u["prevues"], u["executees"], pct(u["taux"]),
                         "\n".join(date_fr(x) for x in u["dates"]), "\n".join(u["themes"])])
        if not rows:
            rows = [[""] * len(ent)]
            rows[0][1] = "Aucune unité pédagogique enregistrée."
        t = d["tot"]
        total = ([""] if ddemp else []) + ["TOTAL", f"{t['up']} UP", "", "", "", t["ecoles"], t["prevues"], t["executees"], pct(t["taux"]), "", ""]
        apres = [P.paragraphe("Nombre d'UP et activités par zone pédagogique", 9.5, True, espace=6),
                 P.mini_tableau([(["CS"] if ddemp else []) + ["Zone pédagogique", "UP", "Écoles", "Prévues", "Exécutées", "Taux"]] +
                                [([z["cs_nom"]] if ddemp else []) + [z["zone"], z["tot"]["up"], z["tot"]["ecoles"], z["tot"]["prevues"],
                                                                      z["tot"]["executees"], pct(z["tot"]["taux"])] for z in d["zones"]] +
                                [([""] if ddemp else []) + ["TOTAL", t["up"], t["ecoles"], t["prevues"], t["executees"], pct(t["taux"])]],
                                taille=7.5)]
        if d["cs"]:
            apres.insert(0, P.paragraphe("Total par circonscription scolaire", 9.5, True, espace=6))
            apres.insert(1, P.mini_tableau([["Circonscription", "Zones", "UP", "Écoles", "Prévues", "Exécutées", "Taux"]] +
                                           [[c["cs_nom"], len(c["zones"]), c["tot"]["up"], c["tot"]["ecoles"], c["tot"]["prevues"],
                                             c["tot"]["executees"], pct(c["tot"]["taux"])] for c in d["cs"]] +
                                           [["TOTAL DDEMP", len(d["zones"]), t["up"], t["ecoles"], t["prevues"], t["executees"], pct(t["taux"])]],
                                           taille=7.5))
        titre, nom, img = signataire()
        infos_haut = [("DDEMP", s.get("departement") or "")]
        if config.EDITION == "cs":
            infos_haut.append(("CS", s.get("cs") or ""))
        elif cs_id and H.jur_cs(cs_id):
            infos_haut.append(("CS", H.jur_cs(cs_id)["nom"]))
        larg = ([16] if ddemp else []) + [22, 14, 26, 27, 27, 9, 11, 13, 10, 22, 44]
        if ddemp:
            larg[-1] -= 16
        pdf = P.document_tableau(
            "UNITÉS PÉDAGOGIQUES : RESPONSABLES ET ACTIVITÉS", ent, rows, total=total, paysage=True, taille=7, largeurs=larg,
            sous_titre=f"Animation pédagogique — {s.get('nom') or ''} — année scolaire {annee}",
            infos=[("Unités pédagogiques", t["up"]), ("Zones pédagogiques", len(d["zones"])),
                   ("Activités prévues / exécutées", f"{t['prevues']} / {t['executees']}"), ("Taux d'exécution", pct(t["taux"])),
                   ("Écoles membres", t["ecoles"])],
            infos_haut=infos_haut, apres=apres, signatures=[(titre, nom, img, True)],
            notes_bas=["Taux d'exécution = activités exécutées ÷ activités prévues de l'année. RUP : responsable d'unité "
                       "pédagogique ; Co-RUP : co-responsable."])
        H.journal("jur_up_pdf", annee)
        return H.pdf_reponse(pdf, f"unites_pedagogiques_{annee}.pdf")
