# -*- coding: utf-8 -*-
"""Vivres et stock de la cantine scolaire : liste des vivres (riz, maïs, haricot, huile, sel…), mouvements
(entrées, sorties, pertes, inventaires), qualité et péremption, alertes, valorisation en FCFA, « sortie du jour »
avec le nombre de rationnaires, récapitulatif mensuel, PDF, Excel, import Excel et réinitialisation.
Toutes éditions ; données par école (ecole_id) ; mouvements rattachés à l'année scolaire de leur date.

* /cantine/stock                              stock_accueil              état du stock (KPI, alertes, boutons)
* /cantine/stock/vivres                       stock_vivres               liste des vivres
* /cantine/stock/vivres/<id>       GET/POST   stock_vivre                fiche (id 0 = nouveau)
* /cantine/stock/vivres/<id>/supprimer  POST  stock_vivre_supprimer      refusée s'il existe des mouvements (→ désactivation)
* /cantine/stock/vivres/liste-type      POST  stock_vivres_type          charge la liste type des vivres (PNASI)
* /cantine/stock/mouvements                   stock_mouvements           journal filtrable (vivre, type, période)
* /cantine/stock/mouvements/<id>   GET/POST   stock_mouvement            saisie / modification (id 0 = nouveau, ?type=entree…)
* /cantine/stock/mouvements/<id>/supprimer POST stock_mouvement_supprimer
* /cantine/stock/sortie-jour       GET/POST   stock_sortie_jour          sortie en bloc : date, rationnaires, une quantité par vivre
* /cantine/stock/recap                        stock_recap                récapitulatif par mois et par vivre, consommation, autonomie
* /cantine/stock/etat.pdf|.xlsx               stock_pdf / stock_xlsx     état du stock
* /cantine/stock/mouvements.pdf|.xlsx         stock_mouvements_pdf / stock_mouvements_xlsx
* /cantine/stock/recap.pdf|.xlsx              stock_recap_pdf / stock_recap_xlsx
* /cantine/stock/import            GET/POST   stock_import               import Excel (feuilles Vivres et Mouvements)
* /cantine/stock/modele.xlsx                  stock_modele_xlsx          modèle d'import
* /cantine/stock/reinitialiser          POST  stock_reinitialiser        supprime tous les mouvements de l'année

Interface pour les autres modules : H.stock_cantine_synthese(ecole_id, annee) -> dict
{"vivres": n, "alertes": n, "valeur": FCFA, "lignes": [{vivre, categorie, unite, stock, qualite, peremption,
 alertes:[…], valeur, dernier}], "mouvements": {"entree", "sortie", "perte", "inventaire"} (quantités de l'année)}.

Droits : lecture pour tout utilisateur connecté ; écriture « stock » (admin, directeur, comptable, secrétaire).

Règles de calcul
* Stock courant d'un vivre = Σ entrées − Σ sorties − Σ pertes, dans l'ordre chronologique, recalé par chaque
  « inventaire » : à partir d'un inventaire, on repart de la quantité constatée (les mouvements antérieurs ne
  comptent plus). Le stock se calcule sur TOUS les mouvements du vivre (le stock se reporte d'une année sur l'autre) ;
  les journaux, récapitulatifs et la réinitialisation portent sur l'année scolaire choisie.
* Qualité du stock = qualité du dernier mouvement d'entrée ou d'inventaire qui l'a renseignée.
* Péremption = date de péremption la plus proche parmi les entrées postérieures au dernier inventaire (ou toutes).
* Alertes : stock ≤ seuil d'alerte du vivre (dès qu'un mouvement existe) ; stock négatif ; qualité « mauvaise » ou « avariée » ; péremption
  dépassée ou dans moins de 30 jours.
* Valeur = stock × dernier prix unitaire saisi sur une entrée (FCFA par unité) ; sans prix : non valorisé.
* Consommation moyenne par jour = Σ sorties de la période ÷ nombre de jours de sortie distincts ; par rationnaire =
  Σ sorties ÷ Σ rationnaires des jours où ce nombre est connu ; autonomie (jours) = stock ÷ consommation par jour.
* Rationnaires d'un jour : nombre de paiements de cantine de ce jour (module Cantine), proposé par défaut et
  modifiable à la saisie.
"""
import io
from datetime import date, datetime, timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

import m_registre as R

CATEGORIES = {"cereale": "Céréale", "legumineuse": "Légumineuse", "huile": "Huile", "condiment": "Condiment",
              "proteine": "Protéine", "autre": "Autre"}
UNITES = ["kg", "litre", "sac de 25 kg", "sac de 50 kg", "bidon", "carton", "boîte", "pièce"]
TYPES = {"entree": "Entrée", "sortie": "Sortie", "perte": "Perte", "inventaire": "Inventaire"}
QUALITES = {"bonne": "Bonne", "acceptable": "Acceptable", "mauvaise": "Mauvaise", "avariee": "Avariée"}
QUALITES_ALERTE = ("mauvaise", "avariee")
ORIGINES = ["PNASI", "APE", "Achat école", "Don", "Autre"]
JOURS_PEREMPTION = 30
QUANTITE_MAX = 1_000_000
PRIX_MAX = 10_000_000
# liste type des vivres d'une cantine scolaire (nom, catégorie, unité, seuil d'alerte)
VIVRES_TYPE = [
    ("Riz", "cereale", "kg", 50), ("Maïs", "cereale", "kg", 50), ("Haricot (niébé)", "legumineuse", "kg", 25),
    ("Soja", "legumineuse", "kg", 10), ("Gari", "cereale", "kg", 25), ("Huile végétale", "huile", "litre", 10),
    ("Sel", "condiment", "kg", 5), ("Tomate concentrée", "condiment", "boîte", 10), ("Sucre", "condiment", "kg", 5),
    ("Sardine", "proteine", "boîte", 20), ("Poisson fumé", "proteine", "kg", 5), ("Viande", "proteine", "kg", 0),
    ("Oignon", "condiment", "kg", 5), ("Piment", "condiment", "kg", 1), ("Bois de chauffe", "autre", "pièce", 0),
    ("Gaz", "autre", "bidon", 1),
]
ENT_VIVRES = ["Nom du vivre", "Catégorie", "Unité", "Seuil d'alerte", "Actif"]
ENT_MOUVEMENTS = ["Date", "Vivre", "Type", "Quantité", "Qualité", "Origine", "Fournisseur", "N° de bon",
                  "Prix unitaire (FCFA)", "Date de péremption", "Rationnaires", "Observations"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS cantine_vivres (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL,
    nom TEXT NOT NULL, categorie TEXT, unite TEXT NOT NULL DEFAULT 'kg', seuil_alerte REAL,
    actif INTEGER NOT NULL DEFAULT 1, ordre INTEGER DEFAULT 0, cree_le TEXT, maj TEXT
);
CREATE TABLE IF NOT EXISTS cantine_stock_mouvements (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL, vivre_id INTEGER NOT NULL,
    annee TEXT NOT NULL, date TEXT NOT NULL,
    type TEXT NOT NULL,                 -- entree | sortie | perte | inventaire
    quantite REAL NOT NULL,
    qualite TEXT,                       -- bonne | acceptable | mauvaise | avariee
    origine TEXT, fournisseur TEXT, bon_numero TEXT,
    prix_unitaire INTEGER,              -- FCFA par unité (entrées) : valorisation du stock
    date_peremption TEXT,
    rationnaires INTEGER,               -- sorties : nombre de rationnaires du jour
    depense_id INTEGER,                 -- dépense (fp_depenses) liée à l'achat, sans doublon
    observations TEXT, cree_par INTEGER, cree_le TEXT, maj TEXT
);
CREATE INDEX IF NOT EXISTS ix_cantine_stock_mvt ON cantine_stock_mouvements(ecole_id, vivre_id, date);
"""


# ============================================================ outils purs
def lire_date(v):
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    return None


def lire_reel(v, maxi=QUANTITE_MAX):
    """« 12,5 » -> 12.5 ; None si vide ou invalide (0 ≤ x ≤ maxi)."""
    s = str(v if v is not None else "").replace(",", ".").replace(" ", "").replace("\xa0", "").strip()
    if not s:
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return x if 0 <= x <= maxi else None


def lire_entier(v, maxi=PRIX_MAX):
    s = str(v if v is not None else "").replace(" ", "").replace("\xa0", "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return int(s) if s.isdigit() and int(s) <= maxi else None


def qte(x):
    """12.0 -> « 12 », 12.5 -> « 12,5 »."""
    if x is None:
        return ""
    return f"{x:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")


def milliers(n):
    return f"{int(round(n or 0)):,}".replace(",", " ")


def calculer_stock(mouvements):
    """Stock d'un vivre d'après ses mouvements (dicts : date, id, type, quantite), dans l'ordre chronologique.
    Un inventaire remplace le stock par la quantité constatée."""
    stock = 0.0
    for m in sorted(mouvements, key=lambda m: (m["date"], m["id"])):
        t, qv = m["type"], float(m["quantite"] or 0)
        if t == "inventaire":
            stock = qv
        elif t == "entree":
            stock += qv
        elif t in ("sortie", "perte"):
            stock -= qv
    return round(stock, 3)


def etat_vivre(vivre, mouvements, auj=None):
    """Situation d'un vivre : stock, qualité, péremption, prix, valeur, alertes, dernier mouvement."""
    auj = auj or date.today()
    mv = sorted(mouvements, key=lambda m: (m["date"], m["id"]))
    stock = calculer_stock(mv)
    qualite = prix = None
    dernier_inv = None
    for m in mv:
        if m["type"] in ("entree", "inventaire") and m["qualite"] in QUALITES:
            qualite = m["qualite"]
        if m["type"] == "entree" and m["prix_unitaire"]:
            prix = m["prix_unitaire"]
        if m["type"] == "inventaire":
            dernier_inv = (m["date"], m["id"])
    entrees = [m for m in mv if m["type"] == "entree" and m["date_peremption"]
               and (dernier_inv is None or (m["date"], m["id"]) > dernier_inv)]
    if not entrees:
        entrees = [m for m in mv if m["type"] == "entree" and m["date_peremption"]]
    peremption = min((lire_date(m["date_peremption"]) for m in entrees if lire_date(m["date_peremption"])), default=None)
    alertes = []
    seuil = vivre["seuil_alerte"]
    if stock < 0:
        alertes.append("Stock négatif : vérifiez les sorties ou faites un inventaire")
    elif seuil is not None and stock <= seuil and mv:      # un vivre sans aucun mouvement n'est pas en alerte
        alertes.append(f"Stock au niveau du seuil d'alerte ({qte(seuil)} {vivre['unite']})")
    if qualite in QUALITES_ALERTE:
        alertes.append(f"Qualité {QUALITES[qualite].lower()}")
    if peremption:
        reste = (peremption - auj).days
        if reste < 0:
            alertes.append(f"Péremption dépassée depuis le {peremption.strftime('%d/%m/%Y')}")
        elif reste < JOURS_PEREMPTION:
            alertes.append(f"Périme dans {reste} jour(s) ({peremption.strftime('%d/%m/%Y')})")
    return {"vivre": dict(vivre), "stock": stock, "qualite": qualite, "peremption": peremption, "prix": prix,
            "valeur": int(round(stock * prix)) if prix and stock > 0 else None, "alertes": alertes,
            "dernier": mv[-1] if mv else None, "nb_mouvements": len(mv)}


def consommation(mouvements, stock):
    """Consommation moyenne par jour et par rationnaire + autonomie, d'après les sorties (dicts date, quantite,
    rationnaires)."""
    sorties = [m for m in mouvements if m["type"] == "sortie"]
    par_jour = {}
    for m in sorties:
        j = par_jour.setdefault(m["date"], {"q": 0.0, "r": None})
        j["q"] += float(m["quantite"] or 0)
        if m["rationnaires"]:
            j["r"] = max(j["r"] or 0, int(m["rationnaires"]))
    total = sum(j["q"] for j in par_jour.values())
    jours = len(par_jour)
    q_rat = sum(j["q"] for j in par_jour.values() if j["r"])
    rations = sum(j["r"] for j in par_jour.values() if j["r"])
    par_jour_moy = round(total / jours, 3) if jours else None
    return {"total": total, "jours": jours, "par_jour": par_jour_moy,
            "par_rationnaire": round(q_rat / rations, 4) if rations else None, "rations": rations,
            "autonomie": int(stock / par_jour_moy) if par_jour_moy and stock > 0 else None}


def mois_annee(annee):
    """[(« 2026-09 », « Septembre 2026 »), …] de l'année scolaire."""
    y = int(annee[:4])
    return [(f"{y + (m < 9)}-{m:02d}", f"{R.MOIS[m - 1].capitalize()} {y + (m < 9)}") for m in (9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8)]


def esc(t):
    return str("" if t is None else t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    # -------------------------------------------------------------- données
    def annee_choisie():
        a = (request.args.get("annee") or request.form.get("annee") or "").strip()
        return a if len(a) == 9 and a[:4].isdigit() and a[4] == "-" else H.config.ANNEE_ACTIVE

    def annees_disponibles(eid):
        a = {r["annee"] for r in q("SELECT DISTINCT annee FROM cantine_stock_mouvements WHERE ecole_id=?", (eid,))}
        a.add(H.config.ANNEE_ACTIVE)
        return sorted(a, reverse=True)

    def vivres(eid, tous=False):
        return q("SELECT * FROM cantine_vivres WHERE ecole_id=?" + ("" if tous else " AND actif=1") + " ORDER BY ordre, nom", (eid,))

    def vivre_ou_404(vid):
        v = q("SELECT * FROM cantine_vivres WHERE id=? AND ecole_id=?", (vid, H.eco()), un=True)
        if not v:
            abort(404)
        return v

    def mouvement_ou_404(mid):
        m = q("SELECT * FROM cantine_stock_mouvements WHERE id=? AND ecole_id=?", (mid, H.eco()), un=True)
        if not m:
            abort(404)
        return m

    def mouvements_par_vivre(eid):
        res = {}
        for m in q("SELECT * FROM cantine_stock_mouvements WHERE ecole_id=? ORDER BY date, id", (eid,)):
            res.setdefault(m["vivre_id"], []).append(dict(m))
        return res

    def exiger_droit():
        if not H.peut("stock"):
            abort(403)

    def rationnaires_du(d):
        """Nombre de paiements de cantine du jour (module Cantine), pour l'école courante."""
        try:
            r = q("""SELECT COUNT(*) n FROM cantine_paiements p JOIN eleves e ON e.id=p.eleve_id
                     JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=? AND p.date=?""", (H.eco(), d.isoformat()), un=True)
            return r["n"] or 0
        except Exception:  # noqa: BLE001 - table absente dans une installation réduite
            return 0

    def depenses_cantine(annee):
        """Dépenses « Cantine – vivres / condiments » de l'année (module Dépenses) : liaison sans doublon."""
        try:
            d1, d2 = H.bornes_annee(annee)
            return q("""SELECT * FROM fp_depenses WHERE ecole_id=? AND annule=0 AND categorie LIKE 'Cantine – %'
                        AND date BETWEEN ? AND ? ORDER BY date DESC, id DESC LIMIT 300""", (H.eco(), d1, d2))
        except Exception:  # noqa: BLE001
            return []

    # -------------------------------------------------------------- synthèse (exposée)
    def stock_cantine_synthese(ecole_id, annee=None):
        annee = annee or H.config.ANNEE_ACTIVE
        mv = mouvements_par_vivre(ecole_id)
        lignes = []
        for v in vivres(ecole_id):
            e = etat_vivre(v, mv.get(v["id"], []))
            lignes.append({"vivre": v["nom"], "vivre_id": v["id"], "categorie": CATEGORIES.get(v["categorie"], v["categorie"] or ""),
                           "unite": v["unite"], "stock": e["stock"], "qualite": e["qualite"],
                           "peremption": e["peremption"].isoformat() if e["peremption"] else None, "alertes": e["alertes"],
                           "valeur": e["valeur"], "dernier": e["dernier"]["date"] if e["dernier"] else None})
        tot = {k: 0.0 for k in TYPES}
        for r in q("SELECT type, SUM(quantite) s FROM cantine_stock_mouvements WHERE ecole_id=? AND annee=? GROUP BY type",
                   (ecole_id, annee)):
            tot[r["type"]] = r["s"] or 0
        return {"annee": annee, "vivres": len(lignes), "alertes": sum(1 for l in lignes if l["alertes"]),
                "valeur": sum(l["valeur"] or 0 for l in lignes), "lignes": lignes, "mouvements": tot}

    H.stock_cantine_synthese = stock_cantine_synthese

    def etats(eid):
        mv = mouvements_par_vivre(eid)
        return [etat_vivre(v, mv.get(v["id"], [])) for v in vivres(eid)]

    def ctx(onglet, **k):
        annee = annee_choisie()
        return dict(onglet=onglet, annee=annee, annees=annees_disponibles(H.eco()), modifiable=H.peut("stock"),
                    TYPES=TYPES, QUALITES=QUALITES, CATEGORIES=CATEGORIES, UNITES=UNITES, ORIGINES=ORIGINES,
                    qte=qte, milliers=milliers, aujourdhui=date.today().isoformat(), **k)

    # -------------------------------------------------------------- état du stock
    @app.route("/cantine/stock")
    @H.connexion_requise()
    def stock_accueil():
        s = stock_cantine_synthese(H.eco(), annee_choisie())
        lignes = etats(H.eco())
        derniers = q("""SELECT m.*, v.nom vivre_nom, v.unite FROM cantine_stock_mouvements m JOIN cantine_vivres v ON v.id=m.vivre_id
                        WHERE m.ecole_id=? AND m.annee=? ORDER BY m.date DESC, m.id DESC LIMIT 8""", (H.eco(), s["annee"]))
        return render_template("stock_accueil.html", **ctx("accueil", s=s, lignes=lignes, derniers=derniers,
                                                           vide=not q("SELECT 1 FROM cantine_vivres WHERE ecole_id=? LIMIT 1", (H.eco(),), un=True)))

    # -------------------------------------------------------------- vivres
    @app.route("/cantine/stock/vivres")
    @H.connexion_requise()
    def stock_vivres():
        mv = mouvements_par_vivre(H.eco())
        liste = [dict(v, nb=len(mv.get(v["id"], [])), stock=calculer_stock(mv.get(v["id"], []))) for v in vivres(H.eco(), tous=True)]
        return render_template("stock_vivres.html", **ctx("vivres", liste=liste))

    @app.route("/cantine/stock/vivres/<int:vid>", methods=["GET", "POST"])
    @H.connexion_requise("stock")
    def stock_vivre(vid):
        v = vivre_ou_404(vid) if vid else None
        if request.method == "POST":
            f = request.form
            nom = (f.get("nom") or "").strip()[:80]
            cat = f.get("categorie") if f.get("categorie") in CATEGORIES else "autre"
            unite = (f.get("unite") or "").strip()[:30] or "kg"
            seuil = lire_reel(f.get("seuil_alerte"))
            ordre = lire_entier(f.get("ordre"), 9999) or 0
            actif = 1 if f.get("actif", "1") == "1" else 0
            erreurs = []
            if not nom:
                erreurs.append("Le nom du vivre est obligatoire.")
            if (f.get("seuil_alerte") or "").strip() and seuil is None:
                erreurs.append("Seuil d'alerte invalide (nombre positif).")
            doublon = q("SELECT id FROM cantine_vivres WHERE ecole_id=? AND lower(nom)=lower(?) AND id<>?", (H.eco(), nom, vid), un=True)
            if doublon:
                erreurs.append(f"Un vivre nommé « {nom} » existe déjà.")
            if erreurs:
                for e in erreurs:
                    flash(e, "danger")
                return render_template("stock_vivre_form.html", **ctx("vivres", v=dict(f), obj=v)), 400
            if v:
                ex("UPDATE cantine_vivres SET nom=?, categorie=?, unite=?, seuil_alerte=?, ordre=?, actif=?, maj=? WHERE id=?",
                   (nom, cat, unite, seuil, ordre, actif, H.maintenant(), vid))
                flash(f"Vivre « {nom} » mis à jour.", "success")
            else:
                vid = ex("INSERT INTO cantine_vivres (ecole_id, nom, categorie, unite, seuil_alerte, ordre, actif, cree_le, maj) VALUES (?,?,?,?,?,?,?,?,?)",
                         (H.eco(), nom, cat, unite, seuil, ordre, actif, H.maintenant(), H.maintenant()))
                flash(f"Vivre « {nom} » ajouté.", "success")
            H.journal("stock_vivre", f"#{vid} {nom}")
            if f.get("suivant"):
                return redirect(url_for("stock_vivre", vid=0))
            return redirect(url_for("stock_vivres"))
        val = dict(v) if v else {"unite": "kg", "categorie": "cereale", "actif": 1}
        return render_template("stock_vivre_form.html", **ctx("vivres", v=val, obj=v))

    @app.route("/cantine/stock/vivres/<int:vid>/supprimer", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_vivre_supprimer(vid):
        v = vivre_ou_404(vid)
        n = q("SELECT COUNT(*) n FROM cantine_stock_mouvements WHERE vivre_id=?", (vid,), un=True)["n"]
        if n and request.form.get("desactiver"):
            ex("UPDATE cantine_vivres SET actif=0, maj=? WHERE id=?", (H.maintenant(), vid))
            H.journal("stock_vivre_desactive", f"#{vid} {v['nom']}")
            flash(f"« {v['nom']} » désactivé : il n'apparaît plus dans le stock, ses {n} mouvement(s) sont conservés.", "warning")
        elif n:
            flash(f"Suppression refusée : « {v['nom']} » a {n} mouvement(s). Vous pouvez le désactiver (bouton « Désactiver ») "
                  "ou supprimer d'abord ses mouvements.", "danger")
        else:
            ex("DELETE FROM cantine_vivres WHERE id=?", (vid,))
            H.journal("stock_vivre_suppression", f"#{vid} {v['nom']}")
            flash(f"Vivre « {v['nom']} » supprimé.", "warning")
        return redirect(url_for("stock_vivres"))

    @app.route("/cantine/stock/vivres/<int:vid>/reactiver", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_vivre_reactiver(vid):
        v = vivre_ou_404(vid)
        ex("UPDATE cantine_vivres SET actif=1, maj=? WHERE id=?", (H.maintenant(), vid))
        H.journal("stock_vivre_reactive", f"#{vid} {v['nom']}")
        flash(f"« {v['nom']} » réactivé.", "success")
        return redirect(url_for("stock_vivres"))

    @app.route("/cantine/stock/vivres/liste-type", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_vivres_type():
        existants = {r["nom"].lower() for r in q("SELECT nom FROM cantine_vivres WHERE ecole_id=?", (H.eco(),))}
        n = 0
        for i, (nom, cat, unite, seuil) in enumerate(VIVRES_TYPE, 1):
            if nom.lower() in existants:
                continue
            ex("INSERT INTO cantine_vivres (ecole_id, nom, categorie, unite, seuil_alerte, ordre, actif, cree_le, maj) VALUES (?,?,?,?,?,?,1,?,?)",
               (H.eco(), nom, cat, unite, seuil or None, i, H.maintenant(), H.maintenant()))
            n += 1
        H.journal("stock_vivres_type", f"{n} vivre(s)")
        flash(f"Liste type chargée : {n} vivre(s) ajouté(s). Adaptez les unités et les seuils d'alerte à votre école.", "success")
        return redirect(url_for("stock_vivres"))

    # -------------------------------------------------------------- mouvements
    def lire_mouvement(f, m=None):
        """Formulaire -> (valeurs, erreurs)."""
        erreurs = []
        d = lire_date(f.get("date"))
        typ = f.get("type") if f.get("type") in TYPES else None
        vid = f.get("vivre_id", type=int) if hasattr(f, "get") else None
        v = q("SELECT * FROM cantine_vivres WHERE id=? AND ecole_id=?", (vid, H.eco()), un=True) if vid else None
        quantite = lire_reel(f.get("quantite"))
        if not d or d > date.today() + timedelta(days=1):
            erreurs.append("Date invalide (pas dans le futur).")
        if not typ:
            erreurs.append("Choisissez le type de mouvement.")
        if not v:
            erreurs.append("Choisissez le vivre.")
        if quantite is None or (quantite <= 0 and typ != "inventaire"):
            erreurs.append("Quantité invalide (nombre positif, ex. 25 ou 12,5).")
        qualite = f.get("qualite") if f.get("qualite") in QUALITES else None
        prix = lire_entier(f.get("prix_unitaire"))
        if (f.get("prix_unitaire") or "").strip() and prix is None:
            erreurs.append("Prix unitaire invalide (nombre entier de FCFA).")
        per = lire_date(f.get("date_peremption"))
        if (f.get("date_peremption") or "").strip() and not per:
            erreurs.append("Date de péremption invalide.")
        rat = lire_entier(f.get("rationnaires"), 100000)
        if (f.get("rationnaires") or "").strip() and rat is None:
            erreurs.append("Nombre de rationnaires invalide.")
        dep = lire_entier(f.get("depense_id"), 10 ** 9) or None
        if dep:
            deja = q("SELECT id FROM cantine_stock_mouvements WHERE depense_id=? AND ecole_id=? AND id<>?",
                     (dep, H.eco(), m["id"] if m else 0), un=True)
            if deja:
                erreurs.append(f"Cette dépense est déjà rattachée au mouvement n° {deja['id']}.")
        vals = {"date": d.isoformat() if d else None, "annee": R.annee_de(d) if d else None, "type": typ,
                "vivre_id": v["id"] if v else None, "quantite": quantite, "qualite": qualite,
                "origine": (f.get("origine") or "").strip()[:60] or None, "fournisseur": (f.get("fournisseur") or "").strip()[:120] or None,
                "bon_numero": (f.get("bon_numero") or "").strip()[:60] or None, "prix_unitaire": prix,
                "date_peremption": per.isoformat() if per else None, "rationnaires": rat, "depense_id": dep,
                "observations": (f.get("observations") or "").strip()[:500] or None}
        return vals, erreurs, v

    CHAMPS_MVT = ("date", "annee", "type", "vivre_id", "quantite", "qualite", "origine", "fournisseur", "bon_numero",
                  "prix_unitaire", "date_peremption", "rationnaires", "depense_id", "observations")

    @app.route("/cantine/stock/mouvements/<int:mid>", methods=["GET", "POST"])
    @H.connexion_requise("stock")
    def stock_mouvement(mid):
        m = mouvement_ou_404(mid) if mid else None
        liste = vivres(H.eco())
        if request.method == "POST":
            vals, erreurs, v = lire_mouvement(request.form, m)
            if erreurs:
                for e in erreurs:
                    flash(e, "danger")
                return render_template("stock_mouvement_form.html", **ctx("mouvements", v=dict(request.form), obj=m, vivres=liste,
                                                                           depenses=depenses_cantine(annee_choisie()))), 400
            if m:
                ex(f"UPDATE cantine_stock_mouvements SET {', '.join(k + '=?' for k in CHAMPS_MVT)}, maj=? WHERE id=?",
                   [vals[k] for k in CHAMPS_MVT] + [H.maintenant(), mid])
                flash(f"{TYPES[vals['type']]} de {qte(vals['quantite'])} {v['unite']} de {v['nom']} mise à jour.", "success")
            else:
                mid = ex(f"INSERT INTO cantine_stock_mouvements (ecole_id, {', '.join(CHAMPS_MVT)}, cree_par, cree_le, maj) "
                         f"VALUES ({', '.join('?' * (len(CHAMPS_MVT) + 4))})",
                         [H.eco()] + [vals[k] for k in CHAMPS_MVT] + [g.user["id"], H.maintenant(), H.maintenant()])
                flash(f"{TYPES[vals['type']]} enregistrée : {qte(vals['quantite'])} {v['unite']} de {v['nom']} "
                      f"(stock : {qte(calculer_stock(mouvements_par_vivre(H.eco()).get(v['id'], [])))} {v['unite']}).", "success")
            H.journal("stock_mouvement", f"#{mid} {vals['type']} {vals['quantite']} {v['nom']} {vals['date']}")
            if request.form.get("suivant"):
                return redirect(url_for("stock_mouvement", mid=0, type=vals["type"], date=vals["date"]))
            return redirect(url_for("stock_mouvements", annee=vals["annee"]))
        if m:
            val = dict(m)
        else:
            typ = request.args.get("type") if request.args.get("type") in TYPES else "entree"
            d = lire_date(request.args.get("date")) or date.today()
            val = {"type": typ, "date": d.isoformat(), "qualite": "bonne", "vivre_id": request.args.get("vivre", type=int),
                   "rationnaires": rationnaires_du(d) or "" if typ == "sortie" else ""}
        return render_template("stock_mouvement_form.html", **ctx("mouvements", v=val, obj=m, vivres=liste,
                                                                   depenses=depenses_cantine(annee_choisie())))

    @app.route("/cantine/stock/mouvements/<int:mid>/supprimer", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_mouvement_supprimer(mid):
        m = mouvement_ou_404(mid)
        ex("DELETE FROM cantine_stock_mouvements WHERE id=?", (mid,))
        H.journal("stock_mouvement_suppression", f"#{mid} {m['type']} {m['quantite']} vivre {m['vivre_id']} {m['date']}")
        flash("Mouvement supprimé ; le stock est recalculé.", "warning")
        return redirect(url_for("stock_mouvements", annee=m["annee"]))

    @app.route("/cantine/stock/sortie-jour", methods=["GET", "POST"])
    @H.connexion_requise("stock")
    def stock_sortie_jour():
        liste = vivres(H.eco())
        mv = mouvements_par_vivre(H.eco())
        if request.method == "POST":
            f = request.form
            d = lire_date(f.get("date"))
            if not d or d > date.today() + timedelta(days=1):
                flash("Date invalide.", "danger")
                return redirect(url_for("stock_sortie_jour"))
            rat = lire_entier(f.get("rationnaires"), 100000)
            obs = (f.get("observations") or "").strip()[:300] or None
            n, erreurs = 0, []
            for v in liste:
                brut = (f.get(f"q_{v['id']}") or "").strip()
                if not brut:
                    continue
                x = lire_reel(brut)
                if x is None or x <= 0:
                    erreurs.append(f"{v['nom']} : quantité invalide « {brut} ».")
                    continue
                ex("""INSERT INTO cantine_stock_mouvements (ecole_id, vivre_id, annee, date, type, quantite, rationnaires, bon_numero,
                      observations, cree_par, cree_le, maj) VALUES (?,?,?,?,'sortie',?,?,?,?,?,?,?)""",
                   (H.eco(), v["id"], R.annee_de(d), d.isoformat(), x, rat, "Sortie du jour", obs, g.user["id"], H.maintenant(), H.maintenant()))
                n += 1
            for e in erreurs:
                flash(e, "danger")
            if n:
                H.journal("stock_sortie_jour", f"{d} {n} vivre(s), {rat or 0} rationnaires")
                flash(f"Sortie du {d.strftime('%d/%m/%Y')} enregistrée : {n} vivre(s), {rat or 0} rationnaire(s).", "success")
            elif not erreurs:
                flash("Aucune quantité saisie.", "warning")
            return redirect(url_for("stock_sortie_jour", date=d.isoformat()))
        d = lire_date(request.args.get("date")) or date.today()
        lignes = [dict(v, stock=calculer_stock(mv.get(v["id"], []))) for v in liste]
        deja = q("""SELECT m.*, v.nom vivre_nom, v.unite FROM cantine_stock_mouvements m JOIN cantine_vivres v ON v.id=m.vivre_id
                    WHERE m.ecole_id=? AND m.date=? AND m.type='sortie' ORDER BY v.ordre, v.nom""", (H.eco(), d.isoformat()))
        return render_template("stock_sortie_jour.html", **ctx("mouvements", d=d, lignes=lignes, deja=deja,
                                                               rationnaires=rationnaires_du(d)))

    def filtre_mouvements(a):
        annee = annee_choisie()
        sql = """SELECT m.*, v.nom vivre_nom, v.unite, u.nom saisi_nom FROM cantine_stock_mouvements m
                 JOIN cantine_vivres v ON v.id=m.vivre_id LEFT JOIN utilisateurs u ON u.id=m.cree_par
                 WHERE m.ecole_id=? AND m.annee=?"""
        params = [H.eco(), annee]
        f = {"vivre": a.get("vivre", type=int), "type": a.get("type", ""), "du": a.get("du", ""), "au": a.get("au", "")}
        if f["vivre"]:
            sql += " AND m.vivre_id=?"
            params.append(f["vivre"])
        if f["type"] in TYPES:
            sql += " AND m.type=?"
            params.append(f["type"])
        if lire_date(f["du"]):
            sql += " AND m.date>=?"
            params.append(lire_date(f["du"]).isoformat())
        if lire_date(f["au"]):
            sql += " AND m.date<=?"
            params.append(lire_date(f["au"]).isoformat())
        return q(sql + " ORDER BY m.date DESC, m.id DESC LIMIT 2000", params), f, annee

    @app.route("/cantine/stock/mouvements")
    @H.connexion_requise()
    def stock_mouvements():
        liste, f, annee = filtre_mouvements(request.args)
        return render_template("stock_mouvements.html", **ctx("mouvements", liste=liste, f=f, vivres=vivres(H.eco(), tous=True)))

    def lignes_mouvements(liste):
        return [[H.pdfs.date_fr(m["date"]), m["vivre_nom"], TYPES.get(m["type"], m["type"]), qte(m["quantite"]), m["unite"],
                 QUALITES.get(m["qualite"], ""), m["origine"] or "", m["fournisseur"] or "", m["bon_numero"] or "",
                 milliers(m["prix_unitaire"]) if m["prix_unitaire"] else "", H.pdfs.date_fr(m["date_peremption"]) if m["date_peremption"] else "",
                 m["rationnaires"] or "", m["observations"] or ""] for m in sorted(liste, key=lambda x: (x["date"], x["id"]))]

    @app.route("/cantine/stock/mouvements.pdf")
    @H.connexion_requise()
    def stock_mouvements_pdf():
        liste, f, annee = filtre_mouvements(request.args)
        v = H.identification()
        pdf = H.pdfs.document_tableau(
            "CANTINE SCOLAIRE — JOURNAL DES MOUVEMENTS DE STOCK",
            ["Date", "Vivre", "Type", "Qté", "Unité", "Qualité", "Origine", "Fournisseur", "N° bon", "P.U.", "Péremption", "Rationnaires", "Observations"],
            [[esc(x) for x in l] for l in lignes_mouvements(liste)] or [["", "Aucun mouvement"] + [""] * 11],
            sous_titre=f"Année scolaire {annee}" + (f" — {TYPES[f['type']]}s" if f["type"] in TYPES else ""),
            infos=[("École", v.get("ecole")), ("Année scolaire", annee), ("Mouvements", len(liste))],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[16, 26, 14, 11, 12, 14, 14, 22, 14, 13, 16, 14, 36], paysage=True, taille=7,
            signatures=signatures(v))
        H.journal("stock_mouvements_pdf", annee)
        return H.pdf_reponse(pdf, f"stock_mouvements_{annee}.pdf")

    @app.route("/cantine/stock/mouvements.xlsx")
    @H.connexion_requise()
    def stock_mouvements_xlsx():
        liste, f, annee = filtre_mouvements(request.args)
        v = H.identification()
        try:
            return H.xlsx.reponse_classeur(f"stock_mouvements_{annee}.xlsx", [
                ("Mouvements", ENT_MOUVEMENTS[:4] + ["Unité"] + ENT_MOUVEMENTS[4:],
                 [[l[0], l[1], l[2], float(m["quantite"] or 0)] + l[4:]
                  for l, m in zip(lignes_mouvements(liste), sorted(liste, key=lambda x: (x["date"], x["id"])))],
                 {"titre_haut": [f"{v.get('ecole') or ''} — Journal des mouvements de stock de la cantine", f"Année scolaire {annee}"]})])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("stock_mouvements"))

    # -------------------------------------------------------------- état du stock : PDF / Excel
    def signatures(v):
        P = H.pdfs
        titre_dir = v.get("directeur_titre") or "Directeur"
        titre_dir = f"{'LA' if titre_dir.lower().startswith('directrice') else 'LE'} {titre_dir.upper()}"
        return [("LE GESTIONNAIRE DE LA CANTINE", "", None, False),
                (titre_dir, v.get("directeur_nom") or "", P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)]

    def lignes_etat(lignes):
        res = []
        for i, e in enumerate(lignes, 1):
            vv = e["vivre"]
            res.append([i, vv["nom"], CATEGORIES.get(vv["categorie"], vv["categorie"] or ""), qte(e["stock"]), vv["unite"],
                        qte(vv["seuil_alerte"]) if vv["seuil_alerte"] is not None else "", QUALITES.get(e["qualite"], ""),
                        e["peremption"].strftime("%d/%m/%Y") if e["peremption"] else "",
                        milliers(e["prix"]) if e["prix"] else "", milliers(e["valeur"]) if e["valeur"] else "",
                        H.pdfs.date_fr(e["dernier"]["date"]) + " (" + TYPES[e["dernier"]["type"]] + ")" if e["dernier"] else "",
                        " ; ".join(e["alertes"])])
        return res

    @app.route("/cantine/stock/etat.pdf")
    @H.connexion_requise()
    def stock_pdf():
        annee = annee_choisie()
        lignes = etats(H.eco())
        s = stock_cantine_synthese(H.eco(), annee)
        v = H.identification()
        rouges = {i: "#FEE4E2" for i, e in enumerate(lignes) if e["alertes"]}
        pdf = H.pdfs.document_tableau(
            "CANTINE SCOLAIRE — ÉTAT DU STOCK DE VIVRES",
            ["N°", "Vivre", "Catégorie", "Stock", "Unité", "Seuil", "Qualité", "Péremption", "P.U. (FCFA)", "Valeur (FCFA)", "Dernier mouvement", "Alertes"],
            [[esc(x) for x in l] for l in lignes_etat(lignes)] or [["", "Aucun vivre enregistré"] + [""] * 10],
            sous_titre=f"Situation au {date.today().strftime('%d/%m/%Y')} — année scolaire {annee}",
            infos=[("École", v.get("ecole")), ("Vivres suivis", s["vivres"]), ("Vivres en alerte", s["alertes"]),
                   ("Valeur du stock", f"{milliers(s['valeur'])} FCFA" if s["valeur"] else "non valorisé"),
                   ("Entrées de l'année", qte(s["mouvements"]["entree"])), ("Sorties de l'année", qte(s["mouvements"]["sortie"]))],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[6, 26, 16, 12, 12, 10, 14, 16, 14, 16, 26, 40], paysage=True, taille=7, surlignes=rouges,
            signatures=signatures(v),
            notes_bas=["Stock = entrées − sorties − pertes, recalé par le dernier inventaire. Lignes surlignées : vivre en alerte "
                       f"(seuil atteint, qualité mauvaise ou avariée, péremption dépassée ou à moins de {JOURS_PEREMPTION} jours)."])
        H.journal("stock_pdf", annee)
        return H.pdf_reponse(pdf, f"stock_cantine_{date.today().isoformat()}.pdf")

    @app.route("/cantine/stock/etat.xlsx")
    @H.connexion_requise()
    def stock_xlsx():
        annee = annee_choisie()
        lignes = etats(H.eco())
        v = H.identification()
        haut = [f"{v.get('ecole') or ''} — État du stock de vivres de la cantine", f"Situation au {date.today().strftime('%d/%m/%Y')} — année scolaire {annee}"]
        lst = [[l[0], l[1], l[2], e["stock"], l[4], e["vivre"]["seuil_alerte"], l[6], l[7], e["prix"], e["valeur"], l[10], l[11]]
               for l, e in zip(lignes_etat(lignes), lignes)]
        try:
            return H.xlsx.reponse_classeur(f"stock_cantine_{date.today().isoformat()}.xlsx", [
                ("État du stock", ["N°", "Vivre", "Catégorie", "Stock", "Unité", "Seuil d'alerte", "Qualité", "Péremption",
                                   "Prix unitaire (FCFA)", "Valeur (FCFA)", "Dernier mouvement", "Alertes"], lst, {"titre_haut": haut}),
                ("Vivres", ENT_VIVRES, [[x["nom"], CATEGORIES.get(x["categorie"], x["categorie"] or ""), x["unite"], x["seuil_alerte"],
                                        "oui" if x["actif"] else "non"] for x in vivres(H.eco(), tous=True)], {"titre_haut": haut})])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("stock_accueil"))

    # -------------------------------------------------------------- récapitulatif mensuel
    def recap(annee):
        """Par vivre : lignes mensuelles (entrées, sorties, pertes, inventaire, stock fin de mois), consommation, autonomie."""
        mv = mouvements_par_vivre(H.eco())
        mois = mois_annee(annee)
        d1, d2 = H.bornes_annee(annee)
        res = []
        for v in vivres(H.eco()):
            tous = mv.get(v["id"], [])
            de_l_annee = [m for m in tous if d1 <= m["date"] <= d2]
            lignes = []
            for cle, lib in mois:
                du_mois = [m for m in de_l_annee if m["date"][:7] == cle]
                t = {k: sum(float(m["quantite"] or 0) for m in du_mois if m["type"] == k) for k in TYPES}
                fin = calculer_stock([m for m in tous if m["date"][:7] <= cle])
                lignes.append({"cle": cle, "lib": lib, "entree": t["entree"], "sortie": t["sortie"], "perte": t["perte"],
                               "inventaire": t["inventaire"] if any(m["type"] == "inventaire" for m in du_mois) else None,
                               "fin": fin, "vide": not du_mois})
            stock = calculer_stock(tous)
            tot = {k: sum(l[k] for l in lignes) for k in ("entree", "sortie", "perte")}
            res.append({"vivre": v, "lignes": lignes, "stock": stock, "tot": tot, "conso": consommation(de_l_annee, stock)})
        return res

    @app.route("/cantine/stock/recap")
    @H.connexion_requise()
    def stock_recap():
        annee = annee_choisie()
        return render_template("stock_recap.html", **ctx("recap", r=recap(annee), mois=mois_annee(annee)))

    def tableau_recap(annee):
        """Tableau synthétique (une ligne par vivre) + tableaux mensuels par vivre."""
        r = recap(annee)
        synth = [[v["vivre"]["nom"], v["vivre"]["unite"], qte(v["tot"]["entree"]), qte(v["tot"]["sortie"]), qte(v["tot"]["perte"]),
                  qte(v["stock"]), qte(v["conso"]["par_jour"]) if v["conso"]["par_jour"] is not None else "—",
                  f"{v['conso']['par_rationnaire']:.3f}".replace(".", ",") if v["conso"]["par_rationnaire"] is not None else "—",
                  v["conso"]["autonomie"] if v["conso"]["autonomie"] is not None else "—"] for v in r]
        return r, synth

    @app.route("/cantine/stock/recap.pdf")
    @H.connexion_requise()
    def stock_recap_pdf():
        annee = annee_choisie()
        r, synth = tableau_recap(annee)
        v = H.identification()
        P = H.pdfs
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Spacer
        apres = []
        for x in r:
            data = [["Mois", "Entrées", "Sorties", "Pertes", "Inventaire", "Stock fin de mois"]]
            data += [[l["lib"], qte(l["entree"]), qte(l["sortie"]), qte(l["perte"]),
                      qte(l["inventaire"]) if l["inventaire"] is not None else "", qte(l["fin"])] for l in x["lignes"] if not l["vide"]]
            if len(data) == 1:
                continue
            apres += [Spacer(1, 5), KeepTogether([P.paragraphe(f"{esc(x['vivre']['nom'].upper())} ({esc(x['vivre']['unite'])})", 9, True),
                                                  P.mini_tableau(data, largeurs=[40 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 30 * mm])])]
        pdf = P.document_tableau(
            "CANTINE SCOLAIRE — RÉCAPITULATIF ANNUEL DU STOCK DE VIVRES",
            ["Vivre", "Unité", "Entrées", "Sorties", "Pertes", "Stock actuel", "Conso. / jour", "Conso. / rationnaire", "Autonomie (jours)"],
            [[esc(c) for c in l] for l in synth] or [["Aucun vivre"] + [""] * 8],
            sous_titre=f"Année scolaire {annee} — situation au {date.today().strftime('%d/%m/%Y')}",
            infos=[("École", v.get("ecole")), ("Année scolaire", annee)],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[30, 14, 14, 14, 14, 16, 16, 20, 18], taille=7.5, apres=apres, signatures=signatures(v),
            notes_bas=["Consommation par jour = sorties ÷ jours de sortie ; par rationnaire = sorties ÷ rationnaires déclarés ; "
                       "autonomie = stock actuel ÷ consommation par jour."])
        H.journal("stock_recap_pdf", annee)
        return H.pdf_reponse(pdf, f"stock_recap_{annee}.pdf")

    @app.route("/cantine/stock/recap.xlsx")
    @H.connexion_requise()
    def stock_recap_xlsx():
        annee = annee_choisie()
        r, synth = tableau_recap(annee)
        v = H.identification()
        haut = [f"{v.get('ecole') or ''} — Récapitulatif du stock de vivres", f"Année scolaire {annee}"]
        mensuel = [[x["vivre"]["nom"], x["vivre"]["unite"], l["lib"], l["entree"], l["sortie"], l["perte"], l["inventaire"], l["fin"]]
                   for x in r for l in x["lignes"]]
        try:
            return H.xlsx.reponse_classeur(f"stock_recap_{annee}.xlsx", [
                ("Synthèse", ["Vivre", "Unité", "Entrées", "Sorties", "Pertes", "Stock actuel", "Consommation / jour",
                              "Consommation / rationnaire", "Autonomie (jours)"], synth, {"titre_haut": haut}),
                ("Par mois", ["Vivre", "Unité", "Mois", "Entrées", "Sorties", "Pertes", "Inventaire", "Stock fin de mois"], mensuel,
                 {"titre_haut": haut})])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("stock_recap"))

    # -------------------------------------------------------------- import Excel / modèle
    def lire_feuilles(fichier):
        """Classeur -> {nom normalisé: (entetes, lignes)} ; CSV -> {"csv": …}."""
        nom = (getattr(fichier, "filename", "") or "").lower()
        if nom.endswith((".csv", ".txt")):
            return {"csv": H.xlsx.lire_tableau(fichier, mots_entete=("vivre", "nom", "date"))}
        openpyxl = H.xlsx._openpyxl()
        try:
            wb = openpyxl.load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        except Exception as e_:  # noqa: BLE001
            raise ValueError("Fichier Excel illisible : enregistrez-le au format .xlsx.") from e_
        out = {}
        for ws in wb.worksheets:
            brutes = [list(r) for r in ws.iter_rows(values_only=True)][:5000]
            idx = next((i for i, r in enumerate(brutes[:40])
                        if any(H.xlsx.normaliser(c) in ("nom du vivre", "vivre", "nom", "date") for c in r if c)), None)
            if idx is None:
                continue
            entetes = [str(c).strip() if c is not None else "" for c in brutes[idx]]
            lignes = [r for r in brutes[idx + 1:] if any(c not in (None, "") for c in r)]
            out[H.xlsx.normaliser(ws.title)] = (entetes, lignes)
        return out

    def importer_vivres(entetes, lignes):
        X = H.xlsx
        i_nom, i_cat = X.colonne(entetes, "nom du vivre", "vivre", "nom"), X.colonne(entetes, "categorie")
        i_unite, i_seuil, i_actif = X.colonne(entetes, "unite"), X.colonne(entetes, "seuil d alerte", "seuil"), X.colonne(entetes, "actif")
        if i_nom is None:
            raise ValueError("Feuille Vivres : colonne « Nom du vivre » introuvable.")
        cats = {X.normaliser(lib): k for k, lib in CATEGORIES.items()}
        crees = maj = 0
        for i, l in enumerate(lignes, 1):
            nom = X.valeur(l, i_nom)[:80]
            if not nom:
                continue
            cat = cats.get(X.normaliser(X.valeur(l, i_cat)), "autre")
            unite = X.valeur(l, i_unite)[:30] or "kg"
            seuil = lire_reel(X.valeur(l, i_seuil))
            actif = 0 if X.normaliser(X.valeur(l, i_actif)) in ("non", "0", "inactif") else 1
            ex_ = q("SELECT id FROM cantine_vivres WHERE ecole_id=? AND lower(nom)=lower(?)", (H.eco(), nom), un=True)
            if ex_:
                ex("UPDATE cantine_vivres SET categorie=?, unite=?, seuil_alerte=?, actif=?, maj=? WHERE id=?",
                   (cat, unite, seuil, actif, H.maintenant(), ex_["id"]))
                maj += 1
            else:
                ex("INSERT INTO cantine_vivres (ecole_id, nom, categorie, unite, seuil_alerte, ordre, actif, cree_le, maj) VALUES (?,?,?,?,?,?,?,?,?)",
                   (H.eco(), nom, cat, unite, seuil, i, actif, H.maintenant(), H.maintenant()))
                crees += 1
        return crees, maj

    def importer_mouvements(entetes, lignes):
        X = H.xlsx
        idx = {k: X.colonne(entetes, *c) for k, c in {
            "date": ("date",), "vivre": ("vivre", "nom du vivre", "nom"), "type": ("type", "mouvement"), "quantite": ("quantite", "qte"),
            "qualite": ("qualite",), "origine": ("origine", "source"), "fournisseur": ("fournisseur",), "bon": ("n de bon", "bon", "numero de bon"),
            "prix": ("prix unitaire", "prix"), "peremption": ("date de peremption", "peremption"), "rationnaires": ("rationnaires",),
            "obs": ("observations", "observation")}.items()}
        if idx["date"] is None or idx["vivre"] is None or idx["quantite"] is None:
            raise ValueError("Feuille Mouvements : colonnes « Date », « Vivre » et « Quantité » obligatoires.")
        types = {X.normaliser(lib): k for k, lib in TYPES.items()}
        types.update({"entrees": "entree", "sorties": "sortie", "pertes": "perte", "e": "entree", "s": "sortie", "p": "perte", "i": "inventaire"})
        quals = {X.normaliser(lib): k for k, lib in QUALITES.items()}
        viv = {v["nom"].lower(): v for v in vivres(H.eco(), tous=True)}
        n, erreurs = 0, []
        for i, l in enumerate(lignes, 1):
            d = lire_date(X.date_iso(l[idx["date"]] if idx["date"] < len(l) else None) or X.valeur(l, idx["date"]))
            nom = X.valeur(l, idx["vivre"])
            v = viv.get(nom.lower())
            if not nom and not d:
                continue
            if not v:
                # vivre inconnu : créé automatiquement
                vid = ex("INSERT INTO cantine_vivres (ecole_id, nom, categorie, unite, actif, cree_le, maj) VALUES (?,?,?,?,1,?,?)",
                         (H.eco(), nom[:80], "autre", "kg", H.maintenant(), H.maintenant()))
                v = viv[nom.lower()] = q("SELECT * FROM cantine_vivres WHERE id=?", (vid,), un=True)
            typ = types.get(X.normaliser(X.valeur(l, idx["type"])) or "entree", None)
            x = lire_reel(X.valeur(l, idx["quantite"]))
            if not d or not typ or x is None:
                erreurs.append(f"Ligne {i} : date, type (Entrée, Sortie, Perte, Inventaire) ou quantité invalide.")
                continue
            per = X.date_iso(l[idx["peremption"]] if idx["peremption"] is not None and idx["peremption"] < len(l) else None) or None
            ex("""INSERT INTO cantine_stock_mouvements (ecole_id, vivre_id, annee, date, type, quantite, qualite, origine, fournisseur,
                  bon_numero, prix_unitaire, date_peremption, rationnaires, observations, cree_par, cree_le, maj)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (H.eco(), v["id"], R.annee_de(d), d.isoformat(), typ, x, quals.get(X.normaliser(X.valeur(l, idx["qualite"]))),
                X.valeur(l, idx["origine"])[:60] or None, X.valeur(l, idx["fournisseur"])[:120] or None, X.valeur(l, idx["bon"])[:60] or None,
                lire_entier(X.valeur(l, idx["prix"])), per, lire_entier(X.valeur(l, idx["rationnaires"]), 100000),
                X.valeur(l, idx["obs"])[:500] or None, g.user["id"], H.maintenant(), H.maintenant()))
            n += 1
        return n, erreurs

    @app.route("/cantine/stock/import", methods=["GET", "POST"])
    @H.connexion_requise("stock")
    def stock_import():
        if request.method == "POST":
            fichier = request.files.get("fichier")
            if not fichier or not fichier.filename:
                flash("Choisissez un fichier Excel (.xlsx).", "danger")
                return redirect(url_for("stock_import"))
            try:
                feuilles = lire_feuilles(fichier)
                bilan = []
                f_v = next((k for k in feuilles if k.startswith("vivre")), None)
                f_m = next((k for k in feuilles if k.startswith("mouvement")), None)
                if f_v is None and f_m is None and feuilles:
                    k = next(iter(feuilles))
                    ent = [H.xlsx.normaliser(h) for h in feuilles[k][0]]
                    f_m, f_v = (k, None) if "date" in ent else (None, k)
                if f_v:
                    c, m = importer_vivres(*feuilles[f_v])
                    bilan.append(f"Vivres : {c} ajouté(s), {m} mis à jour.")
                if f_m:
                    n, erreurs = importer_mouvements(*feuilles[f_m])
                    bilan.append(f"Mouvements : {n} importé(s).")
                    for e in erreurs[:15]:
                        flash(e, "warning")
                if not bilan:
                    raise ValueError("Aucune feuille exploitable : il faut une feuille « Vivres » (colonne Nom du vivre) ou « Mouvements » (colonne Date).")
            except (ValueError, H.xlsx.ExcelIndisponible) as e:
                flash(str(e), "danger")
                return redirect(url_for("stock_import"))
            H.journal("stock_import", " ".join(bilan))
            flash("Import terminé. " + " ".join(bilan), "success")
            return redirect(url_for("stock_accueil"))
        return render_template("stock_import.html", **ctx("import", ent_vivres=ENT_VIVRES, ent_mouvements=ENT_MOUVEMENTS))

    @app.route("/cantine/stock/modele.xlsx")
    @H.connexion_requise()
    def stock_modele_xlsx():
        auj = date.today().strftime("%d/%m/%Y")
        feuilles = [("Vivres", ENT_VIVRES, [[n, CATEGORIES[c], u, s or "", "oui"] for n, c, u, s in VIVRES_TYPE[:6]],
                     {"titre_haut": ["Modèle d'import — feuille Vivres (catégories : " + ", ".join(CATEGORIES.values()) + ")"]}),
                    ("Mouvements", ENT_MOUVEMENTS,
                     [[auj, "Riz", "Entrée", 100, "Bonne", "PNASI", "", "BL 001", 450, "", "", "dotation du trimestre"],
                      [auj, "Riz", "Sortie", 12.5, "", "", "", "", "", "", 250, "repas du jour"],
                      [auj, "Huile végétale", "Inventaire", 18, "Acceptable", "", "", "", "", "", "", "stock constaté"]],
                     {"titre_haut": ["Modèle d'import — feuille Mouvements (types : Entrée, Sortie, Perte, Inventaire ; qualité : "
                                     + ", ".join(QUALITES.values()) + ")"]})]
        try:
            return H.xlsx.reponse_classeur("modele_stock_cantine.xlsx", feuilles)
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("stock_import"))

    # -------------------------------------------------------------- réinitialisation
    @app.route("/cantine/stock/reinitialiser", methods=["POST"])
    @H.connexion_requise("stock")
    def stock_reinitialiser():
        annee = annee_choisie()
        if request.form.get("confirmation") != "REINITIALISER":
            flash("Réinitialisation annulée : tapez REINITIALISER dans la case de confirmation.", "danger")
            return redirect(url_for("stock_accueil", annee=annee))
        n = q("SELECT COUNT(*) n FROM cantine_stock_mouvements WHERE ecole_id=? AND annee=?", (H.eco(), annee), un=True)["n"]
        ex("DELETE FROM cantine_stock_mouvements WHERE ecole_id=? AND annee=?", (H.eco(), annee))
        H.journal("stock_reinitialisation", f"{annee} : {n} mouvement(s) supprimé(s)")
        flash(f"Stock de l'année {annee} réinitialisé : {n} mouvement(s) supprimé(s). La liste des vivres est conservée.", "warning")
        return redirect(url_for("stock_accueil", annee=annee))
