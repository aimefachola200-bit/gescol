# -*- coding: utf-8 -*-
"""Cantine scolaire : configuration du montant journalier par classe, paiements par élève et par jour
(du lundi au vendredi, mercredi compris), statistiques par genre et récapitulatifs (jour, semaine, mois, année,
total général) téléchargeables en PDF.

* /cantine                                   : vue d'ensemble des classes (configuration, semaine en cours)
* /cantine/classe/<cid>?semaine=AAAA-MM-JJ   : grille élèves × jours de la semaine (cases à cocher), totaux,
                                               statistiques, Sauvegarder / Charger / Réinitialiser / PDF
* /cantine/classe/<cid>/enregistrer  (POST)  : enregistre l'en-tête et les paiements de la semaine affichée
* /cantine/classe/<cid>/pdf      (GET/POST)  : fiche PDF de la semaine
* /cantine/config                (GET/POST)  : montant par jour + « Validation de configuration »
* /cantine/recap, /cantine/recap.pdf         : récapitulatifs par jour / semaine / mois / année / total général

Règles : un paiement n'est possible que pour une classe dont la configuration est validée (montant > 0) ;
modifier le montant d'une configuration validée l'invalide jusqu'à nouvelle validation. Chaque paiement garde le
montant du jour au moment de la saisie (table cantine_paiements, UNIQUE(eleve_id, date)).
"""
from datetime import date, timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

import m_registre as R

CHAMPS_ENTETE = ("ddemp", "cs", "ecole", "cours", "annee", "titulaire_titre", "titulaire_nom",
                 "directeur_titre", "directeur_nom")
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
MOIS = [m.capitalize() for m in R.MOIS]
ROLES_CONFIG = ("admin", "fondateur", "directeur", "comptable")
MONTANT_MAX = 100_000
TYPES_RECAP = {"jour": "Par jour", "semaine": "Par semaine", "mois": "Par mois", "annee": "Par année scolaire",
               "total": "Total général"}


# ============================================================ outils (purs)
def lundi(d):
    return d - timedelta(days=d.weekday())


def jours_semaine(lun):
    return [lun + timedelta(days=i) for i in range(5)]


def milliers(n):
    """12500 -> « 12 500 »."""
    return f"{int(n or 0):,}".replace(",", " ")


def lire_montant(v):
    s = str(v or "").replace(" ", "").replace(" ", "").replace("\xa0", "").strip()
    return int(s) if s.isdigit() else None


def periode_recap(typ, args, annee_active):
    """(du, au, libellé, (params précédent), (params suivant)) selon le type de récapitulatif."""
    auj = date.today()
    if typ == "jour":
        d = R.lire_date(args.get("date")) or auj
        return (d, d, f"Journée du {R.date_longue(d)}", {"date": (d - timedelta(days=1)).isoformat()},
                {"date": (d + timedelta(days=1)).isoformat()})
    if typ == "semaine":
        l = lundi(R.lire_date(args.get("date")) or auj)
        v = l + timedelta(days=4)
        return (l, l + timedelta(days=6), f"Semaine du {l.strftime('%d/%m/%Y')} au {v.strftime('%d/%m/%Y')}",
                {"date": (l - timedelta(days=7)).isoformat()}, {"date": (l + timedelta(days=7)).isoformat()})
    if typ == "mois":
        y, m = R.lire_mois(args.get("mois"), (auj.year, auj.month))
        du, au = date(y, m, 1), R.fin_mois(y, m)
        p, s = du - timedelta(days=1), au + timedelta(days=1)
        return (du, au, f"Mois de {R.MOIS[m - 1]} {y}", {"mois": f"{p.year}-{p.month:02d}"},
                {"mois": f"{s.year}-{s.month:02d}"})
    if typ == "annee":
        a = R.annee_valide(args.get("annee"), annee_active)
        y = int(a[:4])
        return (date(y, 9, 1), date(y + 1, 8, 31), f"Année scolaire {a}", {"annee": f"{y - 1}-{y}"},
                {"annee": f"{y + 1}-{y + 2}"})
    return None, None, "Total général (depuis le début)", None, None


def decoupage(typ, du, au, paiements):
    """Lignes du récapitulatif : [{lib, f, g, t, montant}] selon la granularité adaptée au type."""
    cles = []
    if typ == "semaine":
        cles = [(d.isoformat(), f"{JOURS[i]} {d.strftime('%d/%m')}") for i, d in enumerate(jours_semaine(du))]
        cle_de = lambda d: d.isoformat()  # noqa: E731
    elif typ == "mois":
        l = lundi(du)
        while l <= au:
            deb, fin = max(l, du), min(l + timedelta(days=6), au)
            cles.append((l.isoformat(), f"Semaine du {deb.strftime('%d/%m')} au {fin.strftime('%d/%m')}"))
            l += timedelta(days=7)
        cle_de = lambda d: lundi(d).isoformat()  # noqa: E731
    elif typ == "annee":
        y = du.year
        cles = [(f"{y + (m < 9)}-{m:02d}", f"{MOIS[m - 1]} {y + (m < 9)}") for m in (9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8)]
        cle_de = lambda d: f"{d.year}-{d.month:02d}"  # noqa: E731
    elif typ == "total":
        annees = sorted({R.annee_de(p["jour"]) for p in paiements})
        cles = [(a, f"Année scolaire {a}") for a in annees]
        cle_de = R.annee_de
    else:  # jour : une seule ligne
        cles = [(du.isoformat(), R.date_longue(du).capitalize())]
        cle_de = lambda d: d.isoformat()  # noqa: E731
    lignes = {k: {"lib": lib, "f": 0, "g": 0, "t": 0, "montant": 0} for k, lib in cles}
    for p in paiements:
        l = lignes.get(cle_de(p["jour"]))
        if l is None:
            continue
        l["f" if p["sexe"] == "F" else "g"] += 1
        l["t"] += 1
        l["montant"] += p["montant"]
    return list(lignes.values())


def total_lignes(lignes):
    return {k: sum(l[k] for l in lignes) for k in ("f", "g", "t", "montant")}


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex

    def config_classe(cid):
        return q("SELECT * FROM cantine_config WHERE classe_id=?", (cid,), un=True)

    def ouverte(cfg):
        """Paiements autorisés : configuration validée avec un montant positif."""
        return bool(cfg and cfg["valide"] and cfg["montant_jour"] > 0)

    def peut_configurer():
        return g.user["role"] in ROLES_CONFIG

    def cle_entete(cid):
        return f"e{H.eco()}:cantine:c{cid}"

    def entete(cl):
        v = H.identification(cl)
        sauve = H.doc_lire(cle_entete(cl["id"]), None) or {}
        v.update({k: sauve[k] for k in CHAMPS_ENTETE if sauve.get(k)})
        return v

    def eleves_de(cid):
        return q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (cid,))

    def semaine_demandee():
        return lundi(R.lire_date(request.values.get("semaine")) or date.today())

    def classe_controlee(cid):
        H.verifier_classe(cid)
        return H.classe_ou_404(cid)

    def paiements_semaine(cid, lun):
        """{(eleve_id, date iso): montant} pour les élèves inscrits de la classe."""
        return {(r["eleve_id"], r["date"]): r["montant"] for r in q(
            """SELECT p.eleve_id, p.date, p.montant FROM cantine_paiements p JOIN eleves e ON e.id=p.eleve_id
               WHERE e.classe_id=? AND e.statut='inscrit' AND p.date BETWEEN ? AND ?""",
            (cid, lun.isoformat(), (lun + timedelta(days=4)).isoformat()))}

    def fermes(jours):
        """Jours marqués sans classe dans le calendrier scolaire (congés, fériés) : {iso: motif}."""
        return {r["date"]: r["motif"] or "Pas de classe" for r in q(
            "SELECT date, motif FROM jours_classe WHERE ecole_id=? AND demi_journees=0 AND date BETWEEN ? AND ?",
            (H.eco(), jours[0].isoformat(), jours[-1].isoformat()))}

    def grille(cl, lun):
        """Données de la fiche hebdomadaire (partagées par la page et le PDF)."""
        jours = jours_semaine(lun)
        isos = [d.isoformat() for d in jours]
        eleves = eleves_de(cl["id"])
        pay = paiements_semaine(cl["id"], lun)
        lignes = []
        for e in eleves:
            cases = [pay.get((e["id"], j)) for j in isos]
            lignes.append({"e": e, "cases": cases, "n": sum(1 for c in cases if c is not None),
                           "total": sum(c or 0 for c in cases)})
        par_jour = []
        for i, j in enumerate(isos):
            f = sum(1 for l in lignes if l["cases"][i] is not None and l["e"]["sexe"] == "F")
            gg = sum(1 for l in lignes if l["cases"][i] is not None and l["e"]["sexe"] != "F")
            par_jour.append({"iso": j, "lib": f"{JOURS[i]} {jours[i].strftime('%d/%m')}", "f": f, "g": gg,
                             "t": f + gg, "montant": sum(l["cases"][i] or 0 for l in lignes)})
        inscrits = {"f": sum(1 for e in eleves if e["sexe"] == "F")}
        inscrits.update(g=len(eleves) - inscrits["f"], t=len(eleves))
        payeurs = {"f": sum(1 for l in lignes if l["n"] and l["e"]["sexe"] == "F")}
        payeurs["t"] = sum(1 for l in lignes if l["n"])
        payeurs["g"] = payeurs["t"] - payeurs["f"]
        return {"jours": jours, "isos": isos, "lignes": lignes, "par_jour": par_jour, "inscrits": inscrits,
                "payeurs": payeurs, "total": sum(l["total"] for l in lignes),
                "repas": sum(l["n"] for l in lignes), "fermes": fermes(jours)}

    def signatures(cl, v, titulaire=True):
        P = H.pdfs
        titre_dir = f"{'La' if (v.get('directeur_titre') or '').startswith('Directrice') else 'Le'} {v.get('directeur_titre') or 'Directeur'}"
        sigs = []
        if titulaire and cl:
            sigs.append(((v.get("titulaire_titre") or "Le titulaire").upper(), v.get("titulaire_nom", ""),
                         P.image_data_url(H.signature_titulaire(cl["id"])), False))
        sigs.append((titre_dir.upper(), v.get("directeur_nom", ""),
                     P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True))
        return sigs

    # -------------------------------------------------------------- vue d'ensemble
    @app.route("/cantine")
    @H.connexion_requise("cantine")
    def cantine_accueil():
        cid = request.args.get("classe", type=int)
        if cid:
            return redirect(url_for("cantine_classe", cid=cid))
        cls = H.classes_autorisees()
        lun = semaine_demandee()
        cfgs = {r["classe_id"]: r for r in q("SELECT * FROM cantine_config")}
        resume = []
        for c in cls:
            eff = q("SELECT COUNT(*) n FROM eleves WHERE classe_id=? AND statut='inscrit'", (c["id"],), un=True)["n"]
            s = q("""SELECT COUNT(*) n, COALESCE(SUM(p.montant),0) m FROM cantine_paiements p JOIN eleves e ON e.id=p.eleve_id
                     WHERE e.classe_id=? AND p.date BETWEEN ? AND ?""",
                  (c["id"], lun.isoformat(), (lun + timedelta(days=4)).isoformat()), un=True)
            resume.append({"c": c, "eff": eff, "cfg": cfgs.get(c["id"]), "ouverte": ouverte(cfgs.get(c["id"])),
                           "repas": s["n"], "montant": s["m"]})
        return render_template("cantine_accueil.html", resume=resume, lun=lun, ven=lun + timedelta(days=4),
                               prec=(lun - timedelta(days=7)).isoformat(), suiv=(lun + timedelta(days=7)).isoformat(),
                               milliers=milliers, total=sum(r["montant"] for r in resume),
                               repas=sum(r["repas"] for r in resume))

    # -------------------------------------------------------------- fiche hebdomadaire d'une classe
    @app.route("/cantine/classe/<int:cid>")
    @H.connexion_requise("cantine")
    def cantine_classe(cid):
        cl = classe_controlee(cid)
        lun = semaine_demandee()
        cfg = config_classe(cid)
        return render_template("cantine_classe.html", cl=cl, cls=H.classes_autorisees(), cfg=cfg,
                               ouverte=ouverte(cfg), v=entete(cl), d=grille(cl, lun), lun=lun,
                               prec=(lun - timedelta(days=7)).isoformat(), suiv=(lun + timedelta(days=7)).isoformat(),
                               cette_semaine=lundi(date.today()).isoformat(), milliers=milliers,
                               peut_configurer=peut_configurer(), jours_noms=JOURS)

    @app.route("/cantine/classe/<int:cid>/enregistrer", methods=["POST"])
    @H.connexion_requise("cantine")
    def cantine_enregistrer(cid):
        """« Sauvegarder » : en-tête + état des cases de la semaine (case cochée = jour payé)."""
        cl = classe_controlee(cid)
        if not R.lire_date(request.form.get("semaine")):
            # sans semaine valide, on risquerait d'effacer les paiements de la semaine en cours
            flash("Semaine invalide : rien n'a été enregistré. Rechargez la page et recommencez.", "danger")
            return redirect(url_for("cantine_classe", cid=cid))
        lun = semaine_demandee()
        f = request.form
        H.doc_ecrire(cle_entete(cid), {k: f.get(k, "").strip()[:120] for k in CHAMPS_ENTETE})
        cfg = config_classe(cid)
        if not ouverte(cfg):
            flash("Paiements refusés : la configuration de la cantine de cette classe n'est pas validée "
                  "(menu Cantine › Configuration). Seul l'en-tête a été enregistré.", "danger")
            return redirect(url_for("cantine_classe", cid=cid, semaine=lun.isoformat()))
        isos = {d.isoformat() for d in jours_semaine(lun)}
        ids = {e["id"] for e in eleves_de(cid)}
        coches = set()
        for val in f.getlist("p"):
            eid, _, jour = val.partition("_")
            if eid.isdigit() and int(eid) in ids and jour in isos:
                coches.add((int(eid), jour))
        existants = set(paiements_semaine(cid, lun))
        db = H.get_db()
        ajout = sorted(coches - existants)
        retrait = sorted(existants - coches)
        db.executemany("INSERT OR IGNORE INTO cantine_paiements (eleve_id, date, montant, saisi_par, cree_le) VALUES (?,?,?,?,?)",
                       [(e, j, cfg["montant_jour"], g.user["id"], H.maintenant()) for e, j in ajout])
        db.executemany("DELETE FROM cantine_paiements WHERE eleve_id=? AND date=?", retrait)
        db.commit()
        H.journal("cantine", f"{cl['nom']} semaine du {lun} : +{len(ajout)} / -{len(retrait)}")
        flash(f"Semaine enregistrée : {len(ajout)} paiement(s) ajouté(s), {len(retrait)} retiré(s).", "success")
        return redirect(url_for("cantine_classe", cid=cid, semaine=lun.isoformat()))

    @app.route("/cantine/classe/<int:cid>/pdf", methods=["GET", "POST"])
    @H.connexion_requise("cantine")
    def cantine_classe_pdf(cid):
        cl = classe_controlee(cid)
        lun = semaine_demandee()
        v = entete(cl)
        if request.method == "POST":
            v.update({k: request.form.get(k, "").strip()[:120] for k in CHAMPS_ENTETE if k in request.form})
        d = grille(cl, lun)
        cfg = config_classe(cid)
        P = H.pdfs
        h = ["N°", "Nom et prénoms", "Sexe"] + [f"{JOURS[i][:3]}. {j.strftime('%d/%m')}" for i, j in enumerate(d["jours"])] \
            + ["Jours", "Montant"]
        lignes = [[i, f"{l['e']['nom']} {l['e']['prenoms']}", l["e"]["sexe"]]
                  + [milliers(c) if c is not None else "" for c in l["cases"]] + [l["n"] or "", milliers(l["total"])]
                  for i, l in enumerate(d["lignes"], 1)]
        total = ["", "TOTAL PAR JOUR", ""] + [milliers(p["montant"]) for p in d["par_jour"]] + [d["repas"], milliers(d["total"])]
        stats = [["Jour", "Filles", "Garçons", "Total", "Montant (FCFA)"]]
        stats += [[p["lib"], p["f"], p["g"], p["t"], milliers(p["montant"])] for p in d["par_jour"]]
        stats.append(["Semaine", sum(p["f"] for p in d["par_jour"]), sum(p["g"] for p in d["par_jour"]), d["repas"],
                      milliers(d["total"])])
        ins, pay = d["inscrits"], d["payeurs"]
        genre = [["", "Filles", "Garçons", "Total"], ["Inscrits", ins["f"], ins["g"], ins["t"]],
                 ["Ont payé dans la semaine", pay["f"], pay["g"], pay["t"]]]
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Spacer
        apres = [Spacer(1, 5), KeepTogether([P.paragraphe("STATISTIQUES PAR GENRE", 9, True),
                                             P.mini_tableau(genre, largeurs=[48 * mm, 22 * mm, 22 * mm, 22 * mm]),
                                             P.paragraphe("PAIEMENTS ENREGISTRÉS PAR JOUR ET PAR GENRE", 9, True),
                                             P.mini_tableau(stats, largeurs=[36 * mm, 20 * mm, 20 * mm, 20 * mm, 30 * mm])])]
        pdf = P.pour_cycle(dict(cl).get("cycle"))(
            "CANTINE SCOLAIRE — FICHE HEBDOMADAIRE DES PAIEMENTS", h, lignes, total=total,
            sous_titre=f"Semaine du {d['jours'][0].strftime('%d/%m/%Y')} au {d['jours'][-1].strftime('%d/%m/%Y')} — "
                       f"montant par jour : {milliers(cfg['montant_jour']) if cfg else '—'} FCFA",
            infos=[("Cours", v.get("cours")), ("Classe", cl["nom"]),
                   ("Titulaire", f"{v.get('titulaire_titre') or ''} {v.get('titulaire_nom') or ''}".strip()),
                   ("Directeur", f"{v.get('directeur_titre') or ''} {v.get('directeur_nom') or ''}".strip()),
                   ("Année", v.get("annee")), ("Total semaine", f"{milliers(d['total'])} FCFA")],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[6, 44, 7, 12, 12, 12, 12, 12, 8, 14], taille=8, apres=apres, signatures=signatures(cl, v),
            notes_bas=["Montant inscrit dans la case = jour payé (FCFA) ; case vide = non payé."])
        H.journal("cantine_pdf", f"{cl['nom']} {lun}")
        return H.pdf_reponse(pdf, f"cantine_{cl['nom'].replace(' ', '_')}_{lun.isoformat()}.pdf")

    # -------------------------------------------------------------- configuration
    @app.route("/cantine/config", methods=["GET", "POST"])
    @H.connexion_requise("cantine")
    def cantine_config():
        if request.method == "POST":
            if not peut_configurer():
                abort(403)
            cid = request.form.get("classe", type=int)
            cl = classe_controlee(cid)
            action = request.form.get("action", "enregistrer")
            cfg = config_classe(cid)
            m = lire_montant(request.form.get("montant"))
            if action == "devalider":
                if cfg:
                    ex("UPDATE cantine_config SET valide=0, valide_le=NULL WHERE classe_id=?", (cid,))
                flash(f"Configuration de {cl['nom']} remise en attente : les paiements sont suspendus.", "warning")
            elif m is None or not 0 < m <= MONTANT_MAX:
                flash(f"{cl['nom']} : montant par jour invalide (nombre entier de 1 à {milliers(MONTANT_MAX)} FCFA).", "danger")
            else:
                valider = action == "valider"
                # changer le montant d'une configuration validée l'invalide (sauf validation explicite)
                valide = 1 if valider else (1 if cfg and cfg["valide"] and cfg["montant_jour"] == m else 0)
                valide_le = H.maintenant() if valider else (cfg["valide_le"] if valide and cfg else None)
                ex("""INSERT INTO cantine_config (classe_id, montant_jour, valide, valide_le) VALUES (?,?,?,?)
                      ON CONFLICT(classe_id) DO UPDATE SET montant_jour=excluded.montant_jour, valide=excluded.valide,
                      valide_le=excluded.valide_le""", (cid, m, valide, valide_le))
                H.journal("cantine_config", f"{cl['nom']} : {m} F/jour, {'validée' if valide else 'non validée'}")
                if valider:
                    flash(f"Configuration de {cl['nom']} validée : {milliers(m)} FCFA par jour. Les paiements sont ouverts.", "success")
                elif valide:
                    flash(f"Configuration de {cl['nom']} inchangée ({milliers(m)} FCFA par jour, validée).", "info")
                else:
                    flash(f"Montant de {cl['nom']} enregistré ({milliers(m)} FCFA par jour). Cliquez sur « Validation de "
                          "configuration » pour ouvrir les paiements.", "warning")
            return redirect(url_for("cantine_config"))
        cls = H.classes_autorisees()
        cfgs = {r["classe_id"]: r for r in q("SELECT * FROM cantine_config")}
        eff = {r["classe_id"]: r["n"] for r in q(
            "SELECT classe_id, COUNT(*) n FROM eleves WHERE statut='inscrit' GROUP BY classe_id")}
        return render_template("cantine_config.html", cls=cls, cfgs=cfgs, eff=eff, milliers=milliers,
                               modifiable=peut_configurer(), max=MONTANT_MAX)

    # -------------------------------------------------------------- récapitulatifs
    def recap(args):
        typ = args.get("type") if args.get("type") in TYPES_RECAP else "semaine"
        cls = H.classes_autorisees()
        cid = args.get("classe", type=int)
        if cid:
            H.verifier_classe(cid)
            choisies = [c for c in cls if c["id"] == cid]
        else:
            choisies = list(cls)
        du, au, titre, prec, suiv = periode_recap(typ, args, H.config.ANNEE_ACTIVE)
        paiements = []
        ids = [c["id"] for c in choisies]
        if ids:
            marque = ",".join("?" * len(ids))
            sql = f"""SELECT p.date, p.montant, e.sexe, e.classe_id FROM cantine_paiements p JOIN eleves e ON e.id=p.eleve_id
                      WHERE e.classe_id IN ({marque})"""
            params = list(ids)
            if du:
                sql += " AND p.date BETWEEN ? AND ?"
                params += [du.isoformat(), au.isoformat()]
            for r in q(sql, params):
                j = R.lire_date(r["date"])
                if j:
                    paiements.append({"jour": j, "montant": r["montant"], "sexe": r["sexe"], "classe_id": r["classe_id"]})
        lignes = decoupage(typ, du, au, paiements)
        # par classe : inscrits, élèves distincts ayant payé, repas et montant
        par_classe = []
        for c in choisies:
            el = q("SELECT id, sexe FROM eleves WHERE classe_id=? AND statut='inscrit'", (c["id"],))
            pc = [p for p in paiements if p["classe_id"] == c["id"]]
            par_classe.append({"c": c, "if": sum(1 for e in el if e["sexe"] == "F"), "it": len(el),
                               "f": sum(1 for p in pc if p["sexe"] == "F"), "t": len(pc),
                               "montant": sum(p["montant"] for p in pc)})
        for r in par_classe:
            r["ig"], r["g"] = r["it"] - r["if"], r["t"] - r["f"]
        tot_classes = {k: sum(r[k] for r in par_classe) for k in ("if", "ig", "it", "f", "g", "t", "montant")}
        return {"type": typ, "cls": cls, "cid": cid, "du": du, "au": au, "titre": titre, "prec": prec, "suiv": suiv,
                "lignes": lignes, "tot": total_lignes(lignes), "par_classe": par_classe, "tot_classes": tot_classes,
                "date": (du or date.today()).isoformat(), "mois": (du or date.today()).strftime("%Y-%m"),
                "annee": R.annee_de(du) if du else H.config.ANNEE_ACTIVE,
                "portee": choisies[0]["nom"] if cid and choisies else "Toutes les classes"}

    @app.route("/cantine/recap")
    @H.connexion_requise("cantine")
    def cantine_recap():
        r = recap(request.args)
        return render_template("cantine_recap.html", r=r, types=TYPES_RECAP, milliers=milliers)

    @app.route("/cantine/recap.pdf")
    @H.connexion_requise("cantine")
    def cantine_recap_pdf():
        r = recap(request.args)
        P = H.pdfs
        v = H.identification()
        lib_col = {"jour": "Jour", "semaine": "Jour", "mois": "Semaine", "annee": "Mois", "total": "Année scolaire"}[r["type"]]
        cols = [[lib_col, "Repas payés", None, None, "Montant (FCFA)"], ["^", "Filles", "Garçons", "Total", "^"]]
        lignes = [[l["lib"], l["f"], l["g"], l["t"], milliers(l["montant"])] for l in r["lignes"]]
        t = r["tot"]
        total = ["TOTAL", t["f"], t["g"], t["t"], milliers(t["montant"])]
        pc = [["Classe", "Inscrits F", "Inscrits G", "Inscrits", "Repas F", "Repas G", "Repas", "Montant (FCFA)"]]
        pc += [[x["c"]["nom"], x["if"], x["ig"], x["it"], x["f"], x["g"], x["t"], milliers(x["montant"])]
               for x in r["par_classe"]]
        tc = r["tot_classes"]
        pc.append(["TOTAL", tc["if"], tc["ig"], tc["it"], tc["f"], tc["g"], tc["t"], milliers(tc["montant"])])
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Spacer
        apres = [Spacer(1, 6), KeepTogether([P.paragraphe("RÉPARTITION PAR CLASSE", 9, True),
                                             P.mini_tableau(pc, largeurs=[40 * mm] + [17 * mm] * 6 + [28 * mm])])]
        pdf = P.document_tableau(
            f"CANTINE SCOLAIRE — RÉCAPITULATIF {TYPES_RECAP[r['type']].upper()}", cols, lignes, total=total,
            sous_titre=f"{r['titre']} — {r['portee']}",
            infos=[("École", v.get("ecole")), ("Année scolaire", r["annee"]), ("Portée", r["portee"]),
                   ("Total encaissé", f"{milliers(t['montant'])} FCFA")],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[50, 18, 18, 18, 30], taille=8.5, apres=apres, signatures=signatures(None, v, titulaire=False),
            notes_bas=["Repas payés = nombre de paiements journaliers enregistrés (un par élève et par jour)."])
        H.journal("cantine_recap_pdf", f"{r['type']} {r['titre']}")
        return H.pdf_reponse(pdf, f"cantine_recap_{r['type']}_{r['date']}.pdf")
