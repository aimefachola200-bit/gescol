# -*- coding: utf-8 -*-
"""Petit magasin et grand magasin de la cantine scolaire (v2.4.1).

* GRAND MAGASIN = le stock de vivres du module « Vivres et stock » (entrées de dotation ANAN / PNASI, achats, dons).
* PETIT MAGASIN = le prélèvement de la semaine, fait dans le grand magasin pour cinq jours ouvrables.

Règles de calcul (toutes automatiques)
* Ration : grammes par élève et par jour, pour chaque vivre (maïs, haricot, riz, huile, sel…). Valeurs proposées, à ajuster.
* Prélèvement de la semaine d'un vivre (kg) = ration (g) × effectif moyen par jour de l'école × 5 jours ouvrables ÷ 1 000.
  L'effectif moyen est proposé d'après les semaines précédentes (moyenne des effectifs journaliers saisis) ou, à défaut,
  d'après les élèves inscrits ; il reste modifiable (garçons et filles).
* Le prélèvement devient une « Sortie » du grand magasin (référence « Prélèvement petit magasin »).
* Consommation d'un jour (kg) = ration (g) × effectif du jour (garçons + filles) ÷ 1 000, retirée du petit magasin.
* Reste du petit magasin = prélevé − consommé. À la clôture de la semaine — ou automatiquement avant le prélèvement
  de la semaine suivante — le reste est RETOURNÉ au grand magasin (« Entrée » référence « Retour petit magasin »).
  Si la consommation dépasse le prélèvement, le manque est signalé (rien n'est retourné).
* Bilans journalier, hebdomadaire, mensuel et annuel (écran, PDF, Excel) ; fiche de stock par vivre au modèle du cahier
  (date, stock initial, entrée dotation, stock disponible, sortie, stock restant, référence, observations) ;
  cahier des menus hebdomadaires (PDF) au modèle du cahier de la cantine.
* Les quantités du petit magasin sont en kilogrammes ; pour un vivre suivi en litres, 1 litre est compté pour 1 kg
  (approximation) ; pour un sac de 25 ou 50 kg, la conversion est exacte. Autres unités : vivre non géré ici.

Routes (noms en « stock_mag_* » : même menu, mêmes droits que « Vivres et stock » : lecture pour tous, écriture « stock »)
* /cantine/stock/magasins                          stock_mag_accueil
* /cantine/stock/magasins/rations   GET/POST       stock_mag_rations
* /cantine/stock/magasins/semaine/nouvelle  POST   stock_mag_semaine_nouvelle
* /cantine/stock/magasins/semaine/<id>             stock_mag_semaine
* …/semaine/<id>/jours  POST ; /cloturer ; /rouvrir ; /supprimer ; /cahier.pdf
* /cantine/stock/magasins/bilan (.pdf, .xlsx)      stock_mag_bilan, stock_mag_bilan_pdf, stock_mag_bilan_xlsx
* /cantine/stock/magasins/fiche (.pdf, .xlsx)      stock_mag_fiche, stock_mag_fiche_pdf, stock_mag_fiche_xlsx
"""
from datetime import date, datetime, timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

import m_registre as R
from m_stock_cantine import calculer_stock, esc, lire_date, lire_entier, lire_reel, mois_annee, qte

JOURS_OUVRABLES = 5
BON_PRELEVEMENT = "Prélèvement petit magasin"
BON_RETOUR = "Retour petit magasin"
JOURS_NOMS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
FACTEUR_KG = {"kg": 1.0, "litre": 1.0, "sac de 25 kg": 25.0, "sac de 50 kg": 50.0}
# rations proposées (grammes par élève et par jour) : à ajuster selon la dotation (ANAN / PNASI)
RATIONS_TYPE = [("mais", 150), ("riz", 150), ("haricot", 40), ("huile", 10), ("sel", 3)]
RATION_MAX = 2000
EFFECTIF_MAX = 100000
PERIODES = {"jour": "Journalier", "semaine": "Hebdomadaire", "mois": "Mensuel", "annee": "Annuel"}


# ============================================================ outils purs (testés sans base)
def facteur_kg(unite):
    """kg par unité de comptage du vivre (None si l'unité n'est pas gérée)."""
    return FACTEUR_KG.get((unite or "").strip().lower())


def ration_proposee(nom):
    """Ration type d'après le nom du vivre (« Maïs », « Haricot (niébé) », « Huile végétale »…) ; None si inconnue."""
    n = (nom or "").lower().replace("ï", "i").replace("é", "e").replace("è", "e")
    for mot, g_ in RATIONS_TYPE:
        if n.split(" ")[0].startswith(mot):
            return g_
    return None


def quantite_semaine(ration_g, effectif_moyen, jours=JOURS_OUVRABLES):
    """Prélèvement hebdomadaire en kg = ration (g) × effectif moyen par jour × jours ouvrables ÷ 1000."""
    return round(float(ration_g or 0) * float(effectif_moyen or 0) * jours / 1000.0, 3)


def quantite_jour(ration_g, effectif):
    """Consommation d'un jour en kg = ration (g) × effectif du jour ÷ 1000."""
    return round(float(ration_g or 0) * float(effectif or 0) / 1000.0, 3)


def lundi_de(d):
    return d - timedelta(days=d.weekday())


def bilan_vivre_semaine(preleve, consomme):
    """(reste, manque) en kg : le reste est retourné au grand magasin ; le manque est une consommation non couverte."""
    reste = round((preleve or 0) - (consomme or 0), 3)
    return (reste, 0.0) if reste >= 0 else (0.0, -reste)


def etat_grand(mouvements, facteur, d1, d2):
    """Mouvements d'un vivre (dicts date, id, type, quantite, bon_numero) -> situation du grand magasin sur [d1, d2] (ISO),
    en kg : stock initial, entrées (dotation, achats, dons), retours du petit magasin, prélèvements, autres sorties,
    pertes, écart d'inventaire, stock final."""
    f = facteur or 1.0
    avant = [m for m in mouvements if m["date"] < d1]
    jusque = [m for m in mouvements if m["date"] <= d2]
    r = {"initial": calculer_stock(avant) * f, "entrees": 0.0, "retours": 0.0, "prelevements": 0.0, "sorties": 0.0, "pertes": 0.0}
    for m in mouvements:
        if not (d1 <= m["date"] <= d2):
            continue
        x = float(m["quantite"] or 0) * f
        if m["type"] == "entree":
            r["retours" if m.get("bon_numero") == BON_RETOUR else "entrees"] += x
        elif m["type"] == "sortie":
            r["prelevements" if m.get("bon_numero") == BON_PRELEVEMENT else "sorties"] += x
        elif m["type"] == "perte":
            r["pertes"] += x
    r["final"] = calculer_stock(jusque) * f
    attendu = r["initial"] + r["entrees"] + r["retours"] - r["prelevements"] - r["sorties"] - r["pertes"]
    r["ecart_inventaire"] = r["final"] - attendu
    return {k: round(v, 3) for k, v in r.items()}


def fiche_stock(mouvements, facteur, d1, d2):
    """Lignes de la fiche de stock d'un vivre sur [d1, d2] : (date, initial, entrée, disponible, sortie, restant, réf, obs), en kg."""
    f = facteur or 1.0
    courant = calculer_stock([m for m in mouvements if m["date"] < d1]) * f
    lignes = []
    for m in sorted([m for m in mouvements if d1 <= m["date"] <= d2], key=lambda m: (m["date"], m["id"])):
        x = float(m["quantite"] or 0) * f
        initial, entree, sortie = courant, 0.0, 0.0
        if m["type"] == "entree":
            entree = x
        elif m["type"] in ("sortie", "perte"):
            sortie = x
        elif m["type"] == "inventaire":
            courant = x
            lignes.append((m["date"], round(initial, 3), 0.0, round(initial, 3), 0.0, round(x, 3), m.get("bon_numero") or "Inventaire",
                           ("Inventaire : stock constaté" + (" — " + m["observations"] if m.get("observations") else ""))))
            continue
        disponible = initial + entree
        courant = disponible - sortie
        obs = m.get("observations") or ""
        if m["type"] == "perte":
            obs = ("Perte" + (" — " + obs if obs else ""))
        elif m["type"] == "entree" and m.get("origine"):
            obs = (m["origine"] + (" — " + obs if obs else ""))
        lignes.append((m["date"], round(initial, 3), round(entree, 3), round(disponible, 3), round(sortie, 3), round(courant, 3),
                       m.get("bon_numero") or "", obs))
    return lignes


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    if "icone" not in app.jinja_env.globals:          # lignées plus anciennes (1.x) : pas d'icônes dans les gabarits
        app.jinja_env.globals["icone"] = lambda *_a, **_k: ""
    H.schema("""
CREATE TABLE IF NOT EXISTS cantine_rations (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL, vivre_id INTEGER NOT NULL,
    ration_g REAL NOT NULL DEFAULT 0, UNIQUE(ecole_id, vivre_id)
);
CREATE TABLE IF NOT EXISTS cantine_semaines (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL, annee TEXT NOT NULL, debut TEXT NOT NULL,
    garcons INTEGER NOT NULL DEFAULT 0, filles INTEGER NOT NULL DEFAULT 0,
    statut TEXT NOT NULL DEFAULT 'ouverte',      -- ouverte | cloturee
    cree_le TEXT, cloture_le TEXT, UNIQUE(ecole_id, debut)
);
CREATE TABLE IF NOT EXISTS cantine_petit_prelevements (
    id INTEGER PRIMARY KEY, semaine_id INTEGER NOT NULL, vivre_id INTEGER NOT NULL,
    ration_g REAL NOT NULL, quantite_kg REAL NOT NULL, mouvement_id INTEGER
);
CREATE TABLE IF NOT EXISTS cantine_petit_jours (
    id INTEGER PRIMARY KEY, semaine_id INTEGER NOT NULL, date TEXT NOT NULL, menu TEXT,
    garcons INTEGER NOT NULL DEFAULT 0, filles INTEGER NOT NULL DEFAULT 0, UNIQUE(semaine_id, date)
);
CREATE TABLE IF NOT EXISTS cantine_petit_sorties (
    id INTEGER PRIMARY KEY, jour_id INTEGER NOT NULL, vivre_id INTEGER NOT NULL, quantite_kg REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cantine_petit_retours (
    id INTEGER PRIMARY KEY, semaine_id INTEGER NOT NULL, vivre_id INTEGER NOT NULL,
    quantite_kg REAL NOT NULL, manque_kg REAL NOT NULL DEFAULT 0, mouvement_id INTEGER
);
""")

    # ---------------------------------------------------------- données
    def annee_choisie():
        a = (request.args.get("annee") or request.form.get("annee") or "").strip()
        return a if len(a) == 9 and a[:4].isdigit() and a[4] == "-" else H.config.ANNEE_ACTIVE

    def vivres_gerables():
        """Vivres actifs dont l'unité est convertible en kg, avec leur ration (g/élève/jour)."""
        res = []
        for v in q("SELECT * FROM cantine_vivres WHERE ecole_id=? AND actif=1 ORDER BY ordre, nom", (H.eco(),)):
            f = facteur_kg(v["unite"])
            if f is None:
                continue
            r = q("SELECT ration_g FROM cantine_rations WHERE ecole_id=? AND vivre_id=?", (H.eco(), v["id"]), un=True)
            res.append(dict(v, facteur=f, ration_g=(r["ration_g"] if r else 0.0)))
        return res

    def mouvements_de(eid, vivre_id=None):
        res = {}
        sql = "SELECT * FROM cantine_stock_mouvements WHERE ecole_id=?" + (" AND vivre_id=?" if vivre_id else "") + " ORDER BY date, id"
        for m in q(sql, (eid, vivre_id) if vivre_id else (eid,)):
            res.setdefault(m["vivre_id"], []).append(dict(m))
        return res

    def semaine_ou_404(sid):
        s = q("SELECT * FROM cantine_semaines WHERE id=? AND ecole_id=?", (sid, H.eco()), un=True)
        if not s:
            abort(404)
        return s

    def exiger_droit():
        if not H.peut("stock"):
            abort(403)

    def effectif_propose():
        """(garçons, filles) : moyenne des effectifs journaliers saisis (20 derniers jours), sinon élèves inscrits."""
        lst = q("""SELECT j.garcons g, j.filles f FROM cantine_petit_jours j JOIN cantine_semaines s ON s.id=j.semaine_id
                   WHERE s.ecole_id=? AND (j.garcons+j.filles)>0 ORDER BY j.date DESC LIMIT 20""", (H.eco(),))
        if lst:
            return round(sum(x["g"] for x in lst) / len(lst)), round(sum(x["f"] for x in lst) / len(lst)), "moyenne des jours déjà saisis"
        gar = fil = 0
        try:
            for r in q("""SELECT UPPER(SUBSTR(e.sexe,1,1)) s, COUNT(*) n FROM eleves e JOIN classes c ON c.id=e.classe_id
                          WHERE c.ecole_id=? AND e.statut='inscrit' GROUP BY s""", (H.eco(),)):
                if r["s"] == "F":
                    fil += r["n"]
                else:
                    gar += r["n"]
        except Exception:  # noqa: BLE001 - installation réduite
            pass
        return gar, fil, "élèves inscrits de l'école"

    def sorties_semaine(sid):
        """{vivre_id: kg consommés} et liste des jours de la semaine."""
        tot = {}
        for r in q("""SELECT s.vivre_id, SUM(s.quantite_kg) k FROM cantine_petit_sorties s JOIN cantine_petit_jours j ON j.id=s.jour_id
                      WHERE j.semaine_id=? GROUP BY s.vivre_id""", (sid,)):
            tot[r["vivre_id"]] = r["k"] or 0.0
        return tot

    def etat_semaine(s):
        """Tableau du petit magasin d'une semaine : par vivre (prélevé, consommé, reste, retourné, manque) + jours."""
        prel = {p["vivre_id"]: dict(p) for p in q("SELECT * FROM cantine_petit_prelevements WHERE semaine_id=?", (s["id"],))}
        cons = sorties_semaine(s["id"])
        ret = {r["vivre_id"]: dict(r) for r in q("SELECT * FROM cantine_petit_retours WHERE semaine_id=?", (s["id"],))}
        noms = {v["id"]: v for v in q("SELECT * FROM cantine_vivres WHERE ecole_id=?", (H.eco(),))}
        lignes = []
        for vid, p in prel.items():
            v = noms.get(vid)
            if not v:
                continue
            reste, manque = bilan_vivre_semaine(p["quantite_kg"], cons.get(vid, 0.0))
            lignes.append({"vivre_id": vid, "nom": v["nom"], "ration_g": p["ration_g"], "preleve": p["quantite_kg"],
                           "consomme": round(cons.get(vid, 0.0), 3), "reste": reste, "manque": manque,
                           "retourne": (ret.get(vid) or {}).get("quantite_kg"), "ordre": v["ordre"] or 0})
        lignes.sort(key=lambda l: (l["ordre"], l["nom"]))
        jours = [dict(j) for j in q("SELECT * FROM cantine_petit_jours WHERE semaine_id=? ORDER BY date", (s["id"],))]
        par_jour = {}
        for r in q("""SELECT s.jour_id, s.vivre_id, s.quantite_kg FROM cantine_petit_sorties s
                      JOIN cantine_petit_jours j ON j.id=s.jour_id WHERE j.semaine_id=?""", (s["id"],)):
            par_jour.setdefault(r["jour_id"], {})[r["vivre_id"]] = r["quantite_kg"]
        for j in jours:
            j["sorties"] = par_jour.get(j["id"], {})
            j["total"] = (j["garcons"] or 0) + (j["filles"] or 0)
        return {"lignes": lignes, "jours": jours}

    # ---------------------------------------------------------- opérations
    def retourner_reste(s, quand):
        """Retourne au grand magasin le reste du petit magasin d'une semaine ; la clôture est idempotente."""
        if s["statut"] == "cloturee":
            return 0
        info = etat_semaine(s)
        ex("DELETE FROM cantine_petit_retours WHERE semaine_id=?", (s["id"],))
        n = 0
        for l in info["lignes"]:
            v = q("SELECT * FROM cantine_vivres WHERE id=?", (l["vivre_id"],), un=True)
            f = facteur_kg(v["unite"]) or 1.0
            mid = None
            if l["reste"] > 0.0005:
                mid = ex("""INSERT INTO cantine_stock_mouvements (ecole_id, vivre_id, annee, date, type, quantite, origine, bon_numero,
                            observations, cree_par, cree_le, maj) VALUES (?,?,?,?,'entree',?,?,?,?,?,?,?)""",
                         (H.eco(), l["vivre_id"], R.annee_de(quand), quand.isoformat(), round(l["reste"] / f, 3), "Retour petit magasin",
                          BON_RETOUR, f"Reste de la semaine du {H.pdfs.date_fr(s['debut'])}", g.user["id"], H.maintenant(), H.maintenant()))
                n += 1
            ex("INSERT INTO cantine_petit_retours (semaine_id, vivre_id, quantite_kg, manque_kg, mouvement_id) VALUES (?,?,?,?,?)",
               (s["id"], l["vivre_id"], l["reste"] if l["reste"] > 0.0005 else 0.0, l["manque"], mid))
        ex("UPDATE cantine_semaines SET statut='cloturee', cloture_le=? WHERE id=?", (H.maintenant(), s["id"]))
        return n

    def annuler_retours(s):
        for r in q("SELECT mouvement_id FROM cantine_petit_retours WHERE semaine_id=?", (s["id"],)):
            if r["mouvement_id"]:
                ex("DELETE FROM cantine_stock_mouvements WHERE id=? AND ecole_id=?", (r["mouvement_id"], H.eco()))
        ex("DELETE FROM cantine_petit_retours WHERE semaine_id=?", (s["id"],))

    def recalculer_sorties(s):
        """Consommations de chaque jour de la semaine = ration du prélèvement × effectif du jour."""
        prel = q("SELECT * FROM cantine_petit_prelevements WHERE semaine_id=?", (s["id"],))
        for j in q("SELECT * FROM cantine_petit_jours WHERE semaine_id=?", (s["id"],)):
            ex("DELETE FROM cantine_petit_sorties WHERE jour_id=?", (j["id"],))
            for p in prel:
                ex("INSERT INTO cantine_petit_sorties (jour_id, vivre_id, quantite_kg) VALUES (?,?,?)",
                   (j["id"], p["vivre_id"], quantite_jour(p["ration_g"], (j["garcons"] or 0) + (j["filles"] or 0))))

    # ---------------------------------------------------------- pages
    def ctx(**k):
        annee = annee_choisie()
        mv = q("SELECT DISTINCT annee FROM cantine_stock_mouvements WHERE ecole_id=?", (H.eco(),))
        annees = sorted({r["annee"] for r in mv} | {H.config.ANNEE_ACTIVE}, reverse=True)
        return dict(onglet="magasins", annee=annee, annees=annees, modifiable=H.peut("stock"), qte=qte,
                    aujourdhui=date.today().isoformat(), JOURS_NOMS=JOURS_NOMS, JOURS=JOURS_OUVRABLES, **k)

    @app.route("/cantine/stock/magasins")
    @H.connexion_requise()
    def stock_mag_accueil():
        eid = H.eco()
        liste = vivres_gerables()
        mv = mouvements_de(eid)
        grand = [{"nom": v["nom"], "unite": v["unite"], "ration_g": v["ration_g"],
                  "stock_kg": round(calculer_stock(mv.get(v["id"], [])) * v["facteur"], 3)} for v in liste]
        semaines = [dict(s) for s in q("SELECT * FROM cantine_semaines WHERE ecole_id=? AND annee=? ORDER BY debut DESC",
                                       (eid, annee_choisie()))]
        ouverte = next((s for s in semaines if s["statut"] == "ouverte"), None)
        petit = etat_semaine(ouverte) if ouverte else None
        gar, fil, source = effectif_propose()
        prochain = lundi_de(date.today())
        if ouverte and lire_date(ouverte["debut"]) >= prochain:
            prochain = lundi_de(lire_date(ouverte["debut"]) + timedelta(days=7))
        ignores = [v["nom"] for v in q("SELECT nom, unite FROM cantine_vivres WHERE ecole_id=? AND actif=1", (eid,))
                   if facteur_kg(v["unite"]) is None]
        return render_template("stock_magasins.html", **ctx(grand=grand, semaines=semaines, ouverte=ouverte, petit=petit,
                               prop_g=gar, prop_f=fil, prop_source=source, prochain=prochain.isoformat(), ignores=ignores,
                               sans_ration=[v["nom"] for v in liste if not v["ration_g"]]))

    @app.route("/cantine/stock/magasins/rations", methods=["GET", "POST"])
    @H.connexion_requise("stock")
    def stock_mag_rations():
        liste = vivres_gerables()
        if request.method == "POST":
            n = 0
            for v in liste:
                brut = (request.form.get(f"r_{v['id']}") or "").strip()
                x = lire_reel(brut, RATION_MAX) if brut else 0.0
                if x is None:
                    flash(f"{v['nom']} : ration invalide « {brut} » (grammes par élève et par jour).", "danger")
                    continue
                ex("""INSERT INTO cantine_rations (ecole_id, vivre_id, ration_g) VALUES (?,?,?)
                      ON CONFLICT(ecole_id, vivre_id) DO UPDATE SET ration_g=excluded.ration_g""", (H.eco(), v["id"], x))
                n += 1
            H.journal("mag_rations", f"{n} ration(s)")
            flash("Rations enregistrées. Elles s'appliquent aux prochains prélèvements (une semaine déjà prélevée garde les siennes).", "success")
            return redirect(url_for("stock_mag_rations"))
        if request.args.get("proposer"):
            for v in liste:
                if not v["ration_g"]:
                    v["ration_g"] = ration_proposee(v["nom"]) or 0
        return render_template("stock_mag_rations.html", **ctx(vivres=liste, proposees=bool(request.args.get("proposer"))))

    @app.route("/cantine/stock/magasins/semaine/nouvelle", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_mag_semaine_nouvelle():
        f = request.form
        d = lire_date(f.get("debut"))
        gar, fil = lire_entier(f.get("garcons"), EFFECTIF_MAX), lire_entier(f.get("filles"), EFFECTIF_MAX)
        if not d or (gar or 0) + (fil or 0) <= 0:
            flash("Indiquez la semaine et l'effectif moyen par jour (garçons et filles).", "danger")
            return redirect(url_for("stock_mag_accueil"))
        d = lundi_de(d)
        if q("SELECT id FROM cantine_semaines WHERE ecole_id=? AND debut=?", (H.eco(), d.isoformat()), un=True):
            flash("Cette semaine a déjà été prélevée.", "warning")
            return redirect(url_for("stock_mag_accueil"))
        liste = [v for v in vivres_gerables() if v["ration_g"] > 0]
        if not liste:
            flash("Aucune ration définie : renseignez d'abord les rations (grammes par élève et par jour).", "danger")
            return redirect(url_for("stock_mag_rations", proposer=1))
        # 1. le reste du petit magasin des semaines précédentes retourne au grand magasin AVANT le nouveau prélèvement
        retournees = 0
        for s in q("SELECT * FROM cantine_semaines WHERE ecole_id=? AND statut='ouverte' AND debut<? ORDER BY debut", (H.eco(), d.isoformat())):
            retournees += 1 if retourner_reste(s, d) is not None else 0
        # 2. prélèvement : une sortie du grand magasin par vivre
        mv = mouvements_de(H.eco())
        effectif = (gar or 0) + (fil or 0)
        sid = ex("INSERT INTO cantine_semaines (ecole_id, annee, debut, garcons, filles, statut, cree_le) VALUES (?,?,?,?,?,'ouverte',?)",
                 (H.eco(), R.annee_de(d), d.isoformat(), gar or 0, fil or 0, H.maintenant()))
        manques = []
        for v in liste:
            kg = quantite_semaine(v["ration_g"], effectif)
            if kg <= 0:
                continue
            stock_kg = calculer_stock(mv.get(v["id"], [])) * v["facteur"]
            if stock_kg + 0.0005 < kg:
                manques.append(f"{v['nom']} : il faut {qte(kg)} kg, le grand magasin n'a que {qte(round(max(stock_kg, 0), 3))} kg")
            mid = ex("""INSERT INTO cantine_stock_mouvements (ecole_id, vivre_id, annee, date, type, quantite, rationnaires, bon_numero,
                        observations, cree_par, cree_le, maj) VALUES (?,?,?,?,'sortie',?,?,?,?,?,?,?)""",
                     (H.eco(), v["id"], R.annee_de(d), d.isoformat(), round(kg / v["facteur"], 3), effectif, BON_PRELEVEMENT,
                      f"Semaine du {H.pdfs.date_fr(d.isoformat())} : {qte(v['ration_g'])} g × {effectif} élèves × {JOURS_OUVRABLES} jours",
                      g.user["id"], H.maintenant(), H.maintenant()))
            ex("INSERT INTO cantine_petit_prelevements (semaine_id, vivre_id, ration_g, quantite_kg, mouvement_id) VALUES (?,?,?,?,?)",
               (sid, v["id"], v["ration_g"], kg, mid))
        H.journal("mag_prelevement", f"semaine du {d} : {effectif} élèves/jour")
        if retournees:
            flash(f"Le reste du petit magasin de la semaine précédente a été retourné au grand magasin ({retournees} semaine(s) clôturée(s)).", "info")
        for m in manques:
            flash("Stock insuffisant — " + m + ".", "warning")
        flash(f"Petit magasin de la semaine du {d.strftime('%d/%m/%Y')} prélevé ({effectif} élèves par jour × {JOURS_OUVRABLES} jours).", "success")
        return redirect(url_for("stock_mag_semaine", sid=sid))

    @app.route("/cantine/stock/magasins/semaine/<int:sid>")
    @H.connexion_requise()
    def stock_mag_semaine(sid):
        s = semaine_ou_404(sid)
        debut = lire_date(s["debut"])
        info = etat_semaine(s)
        jours = {j["date"]: j for j in info["jours"]}
        grille = []
        for i in range(JOURS_OUVRABLES):
            dj = (debut + timedelta(days=i)).isoformat()
            grille.append({"date": dj, "nom": JOURS_NOMS[i], "j": jours.get(dj)})
        return render_template("stock_mag_semaine.html", **ctx(s=s, debut=debut, info=info, grille=grille,
                               effectif=(s["garcons"] or 0) + (s["filles"] or 0), ouverte=s["statut"] == "ouverte"))

    @app.route("/cantine/stock/magasins/semaine/<int:sid>/jours", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_mag_jours(sid):
        s = semaine_ou_404(sid)
        if s["statut"] != "ouverte":
            flash("Semaine clôturée : rouvrez-la pour modifier les jours.", "warning")
            return redirect(url_for("stock_mag_semaine", sid=sid))
        debut = lire_date(s["debut"])
        f = request.form
        n, erreurs = 0, []
        for i in range(JOURS_OUVRABLES):
            dj = (debut + timedelta(days=i)).isoformat()
            gar_b, fil_b = (f.get(f"g_{dj}") or "").strip(), (f.get(f"f_{dj}") or "").strip()
            menu = (f.get(f"menu_{dj}") or "").strip()[:200] or None
            if not gar_b and not fil_b:
                ex("DELETE FROM cantine_petit_sorties WHERE jour_id IN (SELECT id FROM cantine_petit_jours WHERE semaine_id=? AND date=?)", (sid, dj))
                ex("DELETE FROM cantine_petit_jours WHERE semaine_id=? AND date=?", (sid, dj))
                continue
            gar, fil = lire_entier(gar_b or "0", EFFECTIF_MAX), lire_entier(fil_b or "0", EFFECTIF_MAX)
            if gar is None or fil is None:
                erreurs.append(f"{JOURS_NOMS[i]} : effectif invalide.")
                continue
            ex("""INSERT INTO cantine_petit_jours (semaine_id, date, menu, garcons, filles) VALUES (?,?,?,?,?)
                  ON CONFLICT(semaine_id, date) DO UPDATE SET menu=excluded.menu, garcons=excluded.garcons, filles=excluded.filles""",
               (sid, dj, menu, gar, fil))
            n += 1
        recalculer_sorties(s)
        for e in erreurs:
            flash(e, "danger")
        info = etat_semaine(s)
        for l in info["lignes"]:
            if l["manque"] > 0:
                flash(f"{l['nom']} : la consommation dépasse le prélèvement de {qte(l['manque'])} kg (le petit magasin est vide).", "warning")
        H.journal("mag_jours", f"semaine {s['debut']} : {n} jour(s)")
        flash(f"{n} jour(s) de cantine enregistré(s) ; consommations calculées.", "success")
        return redirect(url_for("stock_mag_semaine", sid=sid))

    @app.route("/cantine/stock/magasins/semaine/<int:sid>/cloturer", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_mag_cloturer(sid):
        s = semaine_ou_404(sid)
        if s["statut"] == "ouverte":
            retourner_reste(s, date.today())
            H.journal("mag_cloture", s["debut"])
            flash("Semaine clôturée : le reste du petit magasin est retourné au grand magasin.", "success")
        return redirect(url_for("stock_mag_semaine", sid=sid))

    @app.route("/cantine/stock/magasins/semaine/<int:sid>/rouvrir", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_mag_rouvrir(sid):
        s = semaine_ou_404(sid)
        if q("SELECT id FROM cantine_semaines WHERE ecole_id=? AND debut>?", (H.eco(), s["debut"]), un=True):
            flash("Une semaine plus récente a déjà été prélevée : cette semaine ne peut plus être rouverte.", "danger")
        elif s["statut"] == "cloturee":
            annuler_retours(s)
            ex("UPDATE cantine_semaines SET statut='ouverte', cloture_le=NULL WHERE id=?", (sid,))
            H.journal("mag_rouvrir", s["debut"])
            flash("Semaine rouverte : le retour au grand magasin est annulé.", "success")
        return redirect(url_for("stock_mag_semaine", sid=sid))

    @app.route("/cantine/stock/magasins/semaine/<int:sid>/supprimer", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_mag_supprimer(sid):
        s = semaine_ou_404(sid)
        if s["statut"] != "ouverte":
            flash("Rouvrez la semaine avant de la supprimer.", "danger")
            return redirect(url_for("stock_mag_semaine", sid=sid))
        for p in q("SELECT mouvement_id FROM cantine_petit_prelevements WHERE semaine_id=?", (sid,)):
            if p["mouvement_id"]:
                ex("DELETE FROM cantine_stock_mouvements WHERE id=? AND ecole_id=?", (p["mouvement_id"], H.eco()))
        ex("DELETE FROM cantine_petit_sorties WHERE jour_id IN (SELECT id FROM cantine_petit_jours WHERE semaine_id=?)", (sid,))
        for t in ("cantine_petit_jours", "cantine_petit_prelevements", "cantine_petit_retours"):
            ex(f"DELETE FROM {t} WHERE semaine_id=?", (sid,))
        ex("DELETE FROM cantine_semaines WHERE id=?", (sid,))
        H.journal("mag_supprimer", s["debut"])
        flash("Semaine supprimée : le prélèvement est remis dans le grand magasin.", "success")
        return redirect(url_for("stock_mag_accueil"))

    # ---------------------------------------------------------- documents
    def signatures_pdf(v):
        P = H.pdfs
        titre_dir = v.get("directeur_titre") or "Directeur"
        titre_dir = f"{'LA' if titre_dir.lower().startswith('directrice') else 'LE'} {titre_dir.upper()}"
        return [("LE MAÎTRE CANTINE", "", None, False),
                (titre_dir, v.get("directeur_nom") or "", P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)]

    def entete_pdf():
        v = H.identification()
        return v, [("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))]

    @app.route("/cantine/stock/magasins/semaine/<int:sid>/cahier.pdf")
    @H.connexion_requise()
    def stock_mag_cahier_pdf(sid):
        """Cahier des menus hebdomadaires : jours, menu, ration par élève, effectif G / F / T, quantités à sortir, solde."""
        s = semaine_ou_404(sid)
        debut = lire_date(s["debut"])
        info = etat_semaine(s)
        par_date = {j["date"]: j for j in info["jours"]}
        lignes, reste = [], {l["vivre_id"]: l["preleve"] for l in info["lignes"]}
        for i in range(JOURS_OUVRABLES):
            dj = (debut + timedelta(days=i)).isoformat()
            j = par_date.get(dj)
            premiere = True
            for l in info["lignes"]:
                x = (j["sorties"].get(l["vivre_id"], 0.0) if j else 0.0)
                reste[l["vivre_id"]] = round(reste[l["vivre_id"]] - x, 3)
                jour_txt = f"{JOURS_NOMS[i]} {(debut + timedelta(days=i)).strftime('%d/%m')}" if premiere else ""
                lignes.append([jour_txt,
                               (esc(j["menu"]) if j and premiere else ""), esc(l["nom"]), qte(l["ration_g"]),
                               (j["garcons"] if j and premiere else ""), (j["filles"] if j and premiere else ""),
                               (j["total"] if j and premiere else ""), esc(l["nom"]) if j else "", qte(x) if j else "",
                               qte(max(reste[l["vivre_id"]], 0))])
                premiere = False
        v, haut = entete_pdf()
        total_prel = [[esc(l["nom"]), qte(l["preleve"]), qte(l["consomme"]), qte(l["reste"]), qte(l["retourne"]) if l["retourne"] is not None else ""]
                      for l in info["lignes"]]
        pdf = H.pdfs.document_tableau(
            "CAHIER DES MENUS HEBDOMADAIRES",
            ["Jours de cantine", "Menu", "Vivre", "Ration par élève (g)", "G", "F", "T", "Vivres à sortir", "Qté (kg)", "Solde du petit magasin (kg)"],
            lignes or [["", "Aucun vivre prélevé"] + [""] * 8],
            sous_titre=f"Semaine du {debut.strftime('%d/%m/%Y')} au {(debut + timedelta(days=4)).strftime('%d/%m/%Y')}",
            infos=[("École", v.get("ecole")), ("Effectif moyen prélevé", f"{(s['garcons'] or 0) + (s['filles'] or 0)} élèves par jour "
                                              f"(G {s['garcons'] or 0}, F {s['filles'] or 0})"),
                   ("Prélèvement", "ration × effectif moyen × 5 jours"), ("Statut", "clôturée" if s["statut"] == "cloturee" else "ouverte")],
            infos_haut=haut, largeurs=[18, 30, 24, 20, 9, 9, 9, 28, 16, 26], paysage=True, taille=7.5,
            signatures=signatures_pdf(v),
            notes_bas=["Prélevé / consommé / reste (kg) : " + " ; ".join(f"{t[0]} {t[1]} / {t[2]} / {t[3]}" for t in total_prel) +
                       ". Le reste du petit magasin est retourné au grand magasin avant le prélèvement de la semaine suivante."])
        return H.pdf_reponse(pdf, f"cahier_menus_{s['debut']}.pdf")

    # ---------------------------------------------------------- bilans
    def bornes_periode(periode, ref, annee):
        """(d1, d2, titre) ISO pour jour | semaine | mois | annee."""
        if periode == "jour":
            d = lire_date(ref) or date.today()
            return d.isoformat(), d.isoformat(), f"Journée du {d.strftime('%d/%m/%Y')}"
        if periode == "semaine":
            d = lundi_de(lire_date(ref) or date.today())
            return d.isoformat(), (d + timedelta(days=6)).isoformat(), f"Semaine du {d.strftime('%d/%m/%Y')} au {(d + timedelta(days=4)).strftime('%d/%m/%Y')}"
        if periode == "mois":
            ym = (ref or "")[:7]
            try:
                d = datetime.strptime(ym + "-01", "%Y-%m-%d").date()
            except ValueError:
                d = date.today().replace(day=1)
            fin = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            return d.isoformat(), fin.isoformat(), f"{R.MOIS[d.month - 1].capitalize()} {d.year}"
        d1, d2 = H.bornes_annee(annee)
        return d1, d2, f"Année scolaire {annee}"

    def conso_periode(eid, d1, d2):
        """{vivre_id: kg consommés au petit magasin}, nombre de jours de cantine, effectifs (G, F) cumulés sur [d1, d2]."""
        cons = {}
        for r in q("""SELECT s.vivre_id, SUM(s.quantite_kg) k FROM cantine_petit_sorties s JOIN cantine_petit_jours j ON j.id=s.jour_id
                      JOIN cantine_semaines w ON w.id=j.semaine_id WHERE w.ecole_id=? AND j.date BETWEEN ? AND ? GROUP BY s.vivre_id""",
                   (eid, d1, d2)):
            cons[r["vivre_id"]] = r["k"] or 0.0
        jr = q("""SELECT COUNT(*) n, COALESCE(SUM(j.garcons),0) g, COALESCE(SUM(j.filles),0) f FROM cantine_petit_jours j
                  JOIN cantine_semaines w ON w.id=j.semaine_id WHERE w.ecole_id=? AND j.date BETWEEN ? AND ? AND (j.garcons+j.filles)>0""",
              (eid, d1, d2), un=True)
        return cons, jr["n"] or 0, jr["g"] or 0, jr["f"] or 0

    def reste_petit(eid, vivre_id, d):
        """Reste du petit magasin du vivre à la fin de la journée d (kg) ; None si aucune semaine ne couvre ce jour."""
        s = q("SELECT * FROM cantine_semaines WHERE ecole_id=? AND debut<=? ORDER BY debut DESC LIMIT 1", (eid, d), un=True)
        if not s or lire_date(d) > lire_date(s["debut"]) + timedelta(days=6):
            return None
        p = q("SELECT quantite_kg FROM cantine_petit_prelevements WHERE semaine_id=? AND vivre_id=?", (s["id"], vivre_id), un=True)
        if not p:
            return None
        c = q("""SELECT COALESCE(SUM(x.quantite_kg),0) k FROM cantine_petit_sorties x JOIN cantine_petit_jours j ON j.id=x.jour_id
                 WHERE j.semaine_id=? AND x.vivre_id=? AND j.date<=?""", (s["id"], vivre_id, d), un=True)
        return round(p["quantite_kg"] - c["k"], 3)

    def construire_bilan(periode, ref, annee):
        """-> (titre, colonnes, lignes, notes) du bilan ; lignes = listes de textes prêts pour l'écran, le PDF et l'Excel."""
        eid = H.eco()
        liste = vivres_gerables()
        mv = mouvements_de(eid)
        d1, d2, titre = bornes_periode(periode, ref, annee)
        cons, njours, sg, sf = conso_periode(eid, d1, d2)
        moy = round((sg + sf) / njours) if njours else 0
        lignes = []
        if periode == "jour":
            cols = ["Vivre", "Ration (g/élève)", "Élèves (G + F)", "Consommé (kg)", "Reste du petit magasin (kg)",
                    "Grand magasin : entrées (kg)", "Grand magasin : prélèvements et sorties (kg)", "Grand magasin : stock en fin de jour (kg)"]
            jr = q("""SELECT j.* FROM cantine_petit_jours j JOIN cantine_semaines w ON w.id=j.semaine_id WHERE w.ecole_id=? AND j.date=?""", (eid, d1), un=True)
            eff = f"{jr['garcons']} + {jr['filles']} = {jr['garcons'] + jr['filles']}" if jr else "—"
            for v in liste:
                e = etat_grand(mv.get(v["id"], []), v["facteur"], d1, d1)
                rp = reste_petit(eid, v["id"], d1)
                lignes.append([v["nom"], qte(v["ration_g"]), eff, qte(round(cons.get(v["id"], 0.0), 3)),
                               qte(rp) if rp is not None else "—", qte(round(e["entrees"] + e["retours"], 3)),
                               qte(round(e["prelevements"] + e["sorties"] + e["pertes"], 3)), qte(e["final"])])
            notes = ["Reste du petit magasin = prélevé de la semaine − consommé jusqu'à ce jour. « — » : aucune semaine prélevée pour ce jour."]
        elif periode == "semaine":
            cols = ["Vivre", "Ration (g/élève)", "Prélevé (kg)", "Consommé (kg)", "Reste (kg)", "Retourné au grand magasin (kg)",
                    "Manque (kg)", "Grand magasin : stock après prélèvement (kg)"]
            s = q("SELECT * FROM cantine_semaines WHERE ecole_id=? AND debut=?", (eid, d1), un=True)
            info = etat_semaine(s) if s else {"lignes": []}
            vv = {v["id"]: v for v in liste}
            for l in info["lignes"]:
                e = etat_grand(mv.get(l["vivre_id"], []), (vv.get(l["vivre_id"]) or {"facteur": 1.0})["facteur"], d1, d2)
                lignes.append([l["nom"], qte(l["ration_g"]), qte(l["preleve"]), qte(l["consomme"]), qte(l["reste"]),
                               qte(l["retourne"]) if l["retourne"] is not None else "à retourner", qte(l["manque"]) if l["manque"] else "",
                               qte(e["final"])])
            notes = [f"{njours} jour(s) de cantine saisi(s), effectif moyen réel {moy} élève(s) par jour."
                     + ("" if s else " Aucun prélèvement pour cette semaine.")]
        else:
            cols = ["Vivre", "Stock initial (kg)", "Entrées : dotation, achats (kg)", "Retours du petit magasin (kg)",
                    "Prélèvements et sorties (kg)", "Pertes (kg)", "Écart d'inventaire (kg)", "Stock final (kg)",
                    "Consommé au petit magasin (kg)", "Consommation moyenne (g/élève/jour)"]
            blocs = [(d1, d2, None)]
            if periode == "annee":
                blocs = [(m + "-01", None, lib) for m, lib in mois_annee(annee)]
            for v in liste:
                moyg = (cons.get(v["id"], 0.0) * 1000.0 / (sg + sf)) if (sg + sf) else 0.0
                if periode == "mois":
                    e = etat_grand(mv.get(v["id"], []), v["facteur"], d1, d2)
                    lignes.append([v["nom"], qte(e["initial"]), qte(e["entrees"]), qte(e["retours"]), qte(round(e["prelevements"] + e["sorties"], 3)),
                                   qte(e["pertes"]), qte(e["ecart_inventaire"]), qte(e["final"]), qte(round(cons.get(v["id"], 0.0), 3)),
                                   qte(round(moyg, 1))])
                else:
                    tot = {"entrees": 0.0, "retours": 0.0, "sorties": 0.0, "pertes": 0.0, "cons": 0.0}
                    for debut_m, _, lib in blocs:
                        dm = lire_date(debut_m)
                        fin = ((dm.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).isoformat()
                        e = etat_grand(mv.get(v["id"], []), v["facteur"], debut_m, fin)
                        c, _, gg, ff = conso_periode(eid, debut_m, fin)
                        ck = c.get(v["id"], 0.0)
                        for k, x in (("entrees", e["entrees"]), ("retours", e["retours"]), ("sorties", e["prelevements"] + e["sorties"]),
                                     ("pertes", e["pertes"]), ("cons", ck)):
                            tot[k] += x
                        lignes.append([f"{v['nom']} — {lib}", qte(e["initial"]), qte(e["entrees"]), qte(e["retours"]),
                                       qte(round(e["prelevements"] + e["sorties"], 3)), qte(e["pertes"]), qte(e["ecart_inventaire"]),
                                       qte(e["final"]), qte(round(ck, 3)), qte(round(ck * 1000.0 / (gg + ff), 1)) if (gg + ff) else ""])
                    e = etat_grand(mv.get(v["id"], []), v["facteur"], d1, d2)
                    lignes.append([f"TOTAL {v['nom']}", qte(e["initial"]), qte(round(tot["entrees"], 3)), qte(round(tot["retours"], 3)),
                                   qte(round(tot["sorties"], 3)), qte(round(tot["pertes"], 3)), qte(e["ecart_inventaire"]), qte(e["final"]),
                                   qte(round(tot["cons"], 3)), qte(round(moyg, 1)) if (sg + sf) else ""])
            notes = [f"{njours} jour(s) de cantine, effectif moyen {moy} élève(s) par jour.",
                     "Stock final = stock initial + entrées + retours − prélèvements et sorties − pertes ± inventaire. "
                     "Les retours et les prélèvements s'annulent entre petit et grand magasin."]
        return titre, cols, lignes, notes, (d1, d2)

    def bilan_params():
        periode = request.args.get("periode") if request.args.get("periode") in PERIODES else "semaine"
        ref = request.args.get("date") or date.today().isoformat()
        return periode, ref, annee_choisie()

    @app.route("/cantine/stock/magasins/bilan")
    @H.connexion_requise()
    def stock_mag_bilan():
        periode, ref, annee = bilan_params()
        titre, cols, lignes, notes, _ = construire_bilan(periode, ref, annee)
        return render_template("stock_mag_bilan.html", **ctx(periode=periode, ref=ref, titre=titre, cols=cols, lignes=lignes,
                                                             notes=notes, PERIODES=PERIODES, mois=mois_annee(annee)))

    @app.route("/cantine/stock/magasins/bilan.pdf")
    @H.connexion_requise()
    def stock_mag_bilan_pdf():
        periode, ref, annee = bilan_params()
        titre, cols, lignes, notes, _ = construire_bilan(periode, ref, annee)
        v, haut = entete_pdf()
        gras = {i: "#E4ECF7" for i, l in enumerate(lignes) if str(l[0]).startswith("TOTAL")}
        pdf = H.pdfs.document_tableau(
            f"CANTINE SCOLAIRE — BILAN {PERIODES[periode].upper()} DES VIVRES", cols,
            [[esc(x) for x in l] for l in lignes] or [["Aucun vivre"] + [""] * (len(cols) - 1)], sous_titre=titre,
            infos=[("École", v.get("ecole")), ("Année scolaire", annee)], infos_haut=haut, paysage=True, taille=7.5,
            surlignes=gras, signatures=signatures_pdf(v), notes_bas=notes)
        H.journal("mag_bilan_pdf", f"{periode} {ref}")
        return H.pdf_reponse(pdf, f"bilan_vivres_{periode}_{ref[:10]}.pdf")

    @app.route("/cantine/stock/magasins/bilan.xlsx")
    @H.connexion_requise()
    def stock_mag_bilan_xlsx():
        periode, ref, annee = bilan_params()
        titre, cols, lignes, notes, _ = construire_bilan(periode, ref, annee)
        v = H.identification()
        try:
            return H.xlsx.reponse_classeur(f"bilan_vivres_{periode}_{ref[:10]}.xlsx", [
                (PERIODES[periode], cols, lignes, {"titre_haut": [f"{v.get('ecole') or ''} — Bilan {PERIODES[periode].lower()} des vivres", titre] + notes})])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("stock_mag_bilan", periode=periode, date=ref))

    # ---------------------------------------------------------- fiche de stock par vivre (modèle du cahier)
    def fiche_params():
        annee = annee_choisie()
        liste = vivres_gerables()
        try:
            vid = int(request.args.get("vivre") or 0)
        except ValueError:
            vid = 0
        v = next((x for x in liste if x["id"] == vid), liste[0] if liste else None)
        return annee, liste, v

    def fiche_lignes(v, annee):
        d1, d2 = H.bornes_annee(annee)
        mv = mouvements_de(H.eco(), v["id"]).get(v["id"], [])
        return fiche_stock(mv, v["facteur"], d1, d2)

    @app.route("/cantine/stock/magasins/fiche")
    @H.connexion_requise()
    def stock_mag_fiche():
        annee, liste, v = fiche_params()
        lignes = fiche_lignes(v, annee) if v else []
        return render_template("stock_mag_fiche.html", **ctx(liste=liste, v=v, lignes=lignes, H=H))

    @app.route("/cantine/stock/magasins/fiche.pdf")
    @H.connexion_requise()
    def stock_mag_fiche_pdf():
        annee, liste, v = fiche_params()
        if not v:
            abort(404)
        lignes = fiche_lignes(v, annee)
        vi, haut = entete_pdf()
        pdf = H.pdfs.document_tableau(
            f"FICHE DE STOCK — {v['nom'].upper()}",
            ["DATE", "STOCK INITIAL (ancien stock) (kg)", "ENTRÉE DOTATION ANAN (kg)", "STOCK DISPONIBLE (kg)", "SORTIE (kg)",
             "STOCK RESTANT (kg)", "Réf", "OBSERVATIONS"],
            [[H.pdfs.date_fr(l[0]), qte(l[1]), qte(l[2]) if l[2] else "", qte(l[3]), qte(l[4]) if l[4] else "", qte(l[5]), esc(l[6]), esc(l[7])]
             for l in lignes] or [["", "", "", "", "", "", "", "Aucun mouvement cette année"]],
            sous_titre=f"Grand magasin — année scolaire {annee}", infos=[("École", vi.get("ecole")), ("Vivre", v["nom"])],
            infos_haut=haut, largeurs=[16, 24, 24, 22, 18, 22, 22, 50], paysage=True, taille=8, signatures=signatures_pdf(vi),
            notes_bas=["Stock disponible = stock initial + entrée ; stock restant = stock disponible − sortie. Quantités en kg."])
        return H.pdf_reponse(pdf, f"fiche_stock_{v['nom'].lower().replace(' ', '_')}_{annee}.pdf")

    @app.route("/cantine/stock/magasins/fiche.xlsx")
    @H.connexion_requise()
    def stock_mag_fiche_xlsx():
        annee, liste, v = fiche_params()
        if not v:
            abort(404)
        vi = H.identification()
        try:
            return H.xlsx.reponse_classeur(f"fiche_stock_{v['nom'].lower().replace(' ', '_')}_{annee}.xlsx", [
                (v["nom"][:28], ["Date", "Stock initial (kg)", "Entrée dotation ANAN (kg)", "Stock disponible (kg)", "Sortie (kg)",
                                 "Stock restant (kg)", "Réf", "Observations"],
                 [list(l) for l in fiche_lignes(v, annee)],
                 {"titre_haut": [f"{vi.get('ecole') or ''} — Fiche de stock : {v['nom']}", f"Année scolaire {annee}"]})])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("stock_mag_fiche", vivre=v["id"]))
