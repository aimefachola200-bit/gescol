# -*- coding: utf-8 -*-
"""Finances de l'école publique : dépenses (surtout des fonds de cantine, saisies par jour), subventions et
recettes, frais de dépôt de dossier CEP, impayés de cantine, et indicateurs du tableau de bord.

* /depenses                     (depenses_accueil)   : journal des dépenses par jour / semaine / mois / année,
                                                        totaux par jour, récapitulatif par catégorie
* /depenses/nouvelle            (depense_nouvelle)   : saisie datée d'une dépense (+ pièce justificative)
* /depenses/<id>/annuler  POST  (depense_annuler)    : annulation motivée (jamais de suppression)
* /depenses/<id>/piece          (depense_piece)      : pièce justificative (photo ou PDF)
* /depenses/journal.pdf|.xlsx   (depenses_pdf / depenses_xlsx)
* /recettes                     (recettes_accueil)   : subventions, dons, cotisations APE… + solde d'ouverture
* /recettes/<id>/annuler  POST  (recette_annuler)
* /recettes/liste.pdf|.xlsx     (recettes_pdf / recettes_xlsx)
* /cep-frais                    (cep_frais)          : frais de dépôt de dossier CEP par candidat (CM2)
* /cep-frais/liste.pdf          (cep_frais_pdf)
* /cantine/impayes              (cantine_impayes)    : élèves n'ayant pas payé la cantine tel jour / telle semaine
* /cantine/impayes.pdf          (cantine_impayes_pdf)

Le module expose aussi, pour les autres modules :
* H.stats_publique()            : indicateurs du tableau de bord (fonds reçus, dépenses, solde en caisse)
* H.fp_operations(d1, d2)       : opérations de trésorerie issues de ces données (édition publique)
* H.fp_solde_ouverture(annee)   : solde d'ouverture saisi pour l'année scolaire
* H.fp_categories_tresorerie()  : catégories de trésorerie de l'édition publique
Toutes les données sont rattachées à l'école courante (H.eco()).
"""
import os
import secrets
from datetime import date, timedelta

from flask import abort, flash, g, redirect, render_template, request, send_file, url_for

import m_registre as R

CATEGORIES_DEPENSES = [
    "Cantine – vivres", "Cantine – condiments", "Cantine – combustible (bois, gaz)",
    "Cantine – cuisinières / motivation", "Cantine – ustensiles", "Fournitures", "Entretien", "Réparations",
    "Frais CEP", "Transport", "Eau et électricité", "Communication", "Autres dépenses",
]
ORIGINES_RECETTES = [
    "Subvention de l'État", "Subvention de la commune", "Dons et partenaires (PAM, ONG…)", "Cotisations APE",
    "Autres recettes",
]
CAT_CANTINE = "Cantine"                      # entrées de trésorerie : paiements de cantine des élèves
CAT_CEP = "Frais de dossier CEP"             # entrées de trésorerie : frais de dépôt de dossier CEP
PERIODES = {"jour": "Jour", "semaine": "Semaine", "mois": "Mois", "annee": "Année scolaire"}
PERIODES_IMPAYES = {"jour": "Jour", "semaine": "Semaine", "mois": "Mois"}
MONTANT_MAX = 100_000_000
PIECE_MAX = 8 * 1024 * 1024
PIECES = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
JOURS_COURTS = ["Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim."]


# ============================================================ outils (purs)
def milliers(n):
    """12500 -> « 12 500 »."""
    return f"{int(n or 0):,}".replace(",", " ")


def lire_montant(v, maxi=MONTANT_MAX):
    """« 12 500 » -> 12500 ; None si vide, invalide, nul ou trop grand."""
    s = str(v or "").replace(" ", "").replace("\xa0", "").replace(" ", "").replace(".", "").strip()
    if not s.isdigit():
        return None
    n = int(s)
    return n if 0 < n <= maxi else None


def lundi(d):
    return d - timedelta(days=d.weekday())


def bornes_periode(typ, d, annee_active):
    """(du, au, libellé, date précédente, date suivante) de la période contenant d."""
    if typ == "jour":
        return d, d, R.date_longue(d).capitalize(), d - timedelta(days=1), d + timedelta(days=1)
    if typ == "semaine":
        l = lundi(d)
        return (l, l + timedelta(days=6), f"Semaine du {l.strftime('%d/%m/%Y')} au {(l + timedelta(days=6)).strftime('%d/%m/%Y')}",
                l - timedelta(days=7), l + timedelta(days=7))
    if typ == "annee":
        y = int(R.annee_de(d)[:4])
        return (date(y, 9, 1), date(y + 1, 8, 31), f"Année scolaire {y}-{y + 1}", date(y - 1, 9, 1), date(y + 1, 9, 1))
    du, au = date(d.year, d.month, 1), R.fin_mois(d.year, d.month)
    return du, au, f"Mois de {R.MOIS[d.month - 1]} {d.year}", du - timedelta(days=1), au + timedelta(days=1)


def type_piece(contenu, ext):
    """Contrôle la signature du fichier (pas seulement l'extension)."""
    if ext == "pdf":
        return contenu[:4] == b"%PDF"
    if ext in ("jpg", "jpeg"):
        return contenu[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return contenu[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == "webp":
        return contenu[:4] == b"RIFF" and contenu[8:12] == b"WEBP"
    return False


# ============================================================ module
def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config

    H.schema("""
    CREATE TABLE IF NOT EXISTS fp_depenses (
        id INTEGER PRIMARY KEY,
        ecole_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        categorie TEXT NOT NULL,
        libelle TEXT NOT NULL,
        montant INTEGER NOT NULL,
        beneficiaire TEXT,
        mode TEXT,
        reference TEXT,
        piece TEXT,                  -- nom du fichier dans <INSTANCE_DIR>/archives
        piece_nom TEXT,              -- nom d'origine du fichier téléversé
        saisi_par INTEGER,
        cree_le TEXT,
        annule INTEGER NOT NULL DEFAULT 0,
        annule_motif TEXT,
        annule_par INTEGER,
        annule_le TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_fp_depenses ON fp_depenses(ecole_id, date);
    CREATE TABLE IF NOT EXISTS fp_recettes (
        id INTEGER PRIMARY KEY,
        ecole_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        origine TEXT NOT NULL,       -- catégorie (subvention de l'État, de la commune, dons, APE, autres)
        provenance TEXT,             -- précision : PAM, ONG X, mairie de…
        libelle TEXT NOT NULL,
        montant INTEGER NOT NULL,
        mode TEXT,
        reference TEXT,
        saisi_par INTEGER,
        cree_le TEXT,
        annule INTEGER NOT NULL DEFAULT 0,
        annule_motif TEXT,
        annule_par INTEGER,
        annule_le TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_fp_recettes ON fp_recettes(ecole_id, date);
    CREATE TABLE IF NOT EXISTS fp_parametres (
        ecole_id INTEGER NOT NULL,
        annee TEXT NOT NULL,
        solde_ouverture INTEGER NOT NULL DEFAULT 0,
        montant_cep INTEGER NOT NULL DEFAULT 0,
        maj TEXT,
        PRIMARY KEY (ecole_id, annee)
    );
    CREATE TABLE IF NOT EXISTS fp_cep_frais (      -- une ligne = frais de dossier payé
        eleve_id INTEGER NOT NULL,
        annee TEXT NOT NULL,
        ecole_id INTEGER NOT NULL,
        montant INTEGER NOT NULL,
        date TEXT NOT NULL,
        saisi_par INTEGER,
        maj TEXT,
        PRIMARY KEY (eleve_id, annee)
    );
    """)

    dossier_pieces = os.path.join(config.INSTANCE_DIR, "archives")   # sauvegardé avec les autres fichiers

    # -------------------------------------------------------------- lectures communes
    def parametres(annee=None):
        r = q("SELECT * FROM fp_parametres WHERE ecole_id=? AND annee=?", (H.eco(), annee or config.ANNEE_ACTIVE), un=True)
        return {"solde_ouverture": r["solde_ouverture"] if r else 0, "montant_cep": r["montant_cep"] if r else 0}

    def ecrire_parametre(col, valeur):
        assert col in ("solde_ouverture", "montant_cep")
        ex(f"""INSERT INTO fp_parametres (ecole_id, annee, {col}, maj) VALUES (?,?,?,?)
               ON CONFLICT(ecole_id, annee) DO UPDATE SET {col}=excluded.{col}, maj=excluded.maj""",
           (H.eco(), config.ANNEE_ACTIVE, valeur, H.maintenant()))

    def somme(sql, args):
        return q(sql, args, un=True)["s"] or 0

    def total_cantine(d1, d2):
        return somme("""SELECT SUM(p.montant) s FROM cantine_paiements p JOIN eleves e ON e.id=p.eleve_id
                        JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=? AND p.date BETWEEN ? AND ?""", (H.eco(), d1, d2))

    def total_recettes(d1, d2):
        return somme("SELECT SUM(montant) s FROM fp_recettes WHERE ecole_id=? AND annule=0 AND date BETWEEN ? AND ?",
                     (H.eco(), d1, d2))

    def total_cep(d1, d2):
        return somme("SELECT SUM(montant) s FROM fp_cep_frais WHERE ecole_id=? AND date BETWEEN ? AND ?", (H.eco(), d1, d2))

    def total_depenses(d1, d2):
        return somme("SELECT SUM(montant) s FROM fp_depenses WHERE ecole_id=? AND annule=0 AND date BETWEEN ? AND ?",
                     (H.eco(), d1, d2))

    def bilan_annee():
        """Totaux de l'année scolaire active (école courante)."""
        d1, d2 = H.bornes_annee()
        b = {"ouverture": parametres()["solde_ouverture"], "cantine": total_cantine(d1, d2),
             "recettes": total_recettes(d1, d2), "cep": total_cep(d1, d2), "depenses": total_depenses(d1, d2)}
        b["recu"] = b["cantine"] + b["recettes"] + b["cep"]
        b["solde"] = b["ouverture"] + b["recu"] - b["depenses"]
        return b

    def stats_publique():
        """Indicateurs du tableau de bord (édition publique)."""
        auj = date.today().isoformat()
        b = bilan_annee()
        return {"recu_annee": b["recu"],
                "recu_jour": total_cantine(auj, auj) + total_recettes(auj, auj) + total_cep(auj, auj),
                "depenses_annee": b["depenses"], "depenses_jour": total_depenses(auj, auj), "solde": b["solde"]}

    def operations_tresorerie(d1, d2):
        """Opérations de trésorerie (même format que m_tresorerie) : cantine, recettes, CEP (entrées), dépenses (sorties)."""
        ops = []
        for r in q("""SELECT p.date, c.id cid, c.nom, COUNT(*) n, SUM(p.montant) m FROM cantine_paiements p
                      JOIN eleves e ON e.id=p.eleve_id JOIN classes c ON c.id=e.classe_id
                      WHERE c.ecole_id=? AND p.date BETWEEN ? AND ? GROUP BY p.date, c.id""", (H.eco(), d1, d2)):
            ops.append({"date": r["date"], "type": "entree", "categorie": CAT_CANTINE,
                        "libelle": f"Paiements de cantine – {r['nom']} ({r['n']} repas)", "montant": r["m"],
                        "mode": "especes", "source": "cantine", "id": r["cid"], "reference": None})
        for r in q("SELECT * FROM fp_recettes WHERE ecole_id=? AND annule=0 AND date BETWEEN ? AND ?", (H.eco(), d1, d2)):
            ops.append({"date": r["date"], "type": "entree", "categorie": r["origine"],
                        "libelle": r["libelle"] + (f" – {r['provenance']}" if r["provenance"] else ""),
                        "montant": r["montant"], "mode": r["mode"], "source": "recette", "id": r["id"],
                        "reference": r["reference"]})
        for r in q("""SELECT date, COUNT(*) n, SUM(montant) m FROM fp_cep_frais WHERE ecole_id=? AND date BETWEEN ? AND ?
                      GROUP BY date""", (H.eco(), d1, d2)):
            ops.append({"date": r["date"], "type": "entree", "categorie": CAT_CEP,
                        "libelle": f"Frais de dépôt de dossier CEP ({r['n']} candidat(s))", "montant": r["m"],
                        "mode": "especes", "source": "cep", "id": 0, "reference": None})
        for r in q("SELECT * FROM fp_depenses WHERE ecole_id=? AND annule=0 AND date BETWEEN ? AND ?", (H.eco(), d1, d2)):
            ops.append({"date": r["date"], "type": "sortie", "categorie": r["categorie"],
                        "libelle": r["libelle"] + (f" – {r['beneficiaire']}" if r["beneficiaire"] else ""),
                        "montant": r["montant"], "mode": r["mode"], "source": "depense", "id": r["id"],
                        "reference": r["reference"]})
        return ops

    def categories_tresorerie(base):
        """Catégories de trésorerie de l'édition publique : celles de ce module, puis celles d'origine."""
        entree = [CAT_CANTINE] + ORIGINES_RECETTES + [CAT_CEP]
        sortie = list(CATEGORIES_DEPENSES)
        return {"entree": entree + [c for c in base["entree"] if c not in entree],
                "sortie": sortie + [c for c in base["sortie"] if c not in sortie]}

    H.stats_publique = stats_publique
    H.fp_operations = operations_tresorerie
    H.fp_solde_ouverture = lambda annee=None: parametres(annee)["solde_ouverture"]
    H.fp_categories_tresorerie = categories_tresorerie

    # -------------------------------------------------------------- outils de requête
    def date_demandee(nom="date"):
        return R.lire_date(request.args.get(nom)) or date.today()

    def lire_date_saisie(v):
        """Date de saisie : obligatoire, valide, pas dans le futur, pas avant 2000."""
        d = R.lire_date(v)
        if not d or d > date.today() or d.year < 2000:
            return None
        return d

    def modes():
        return {k: v for k, v in config.MODES_PAIEMENT.items() if k not in ("fedapay", "kkiapay")}

    def signatures_pdf(v):
        P = H.pdfs
        titre = f"{'La' if (v.get('directeur_titre') or '').startswith('Directrice') else 'Le'} {v.get('directeur_titre') or 'Directeur'}"
        return [("LE GESTIONNAIRE / COMPTABLE", "", None, False),
                (titre.upper(), v.get("directeur_nom", ""), P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)]

    def infos_haut(v):
        return [("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))]

    # ============================================================== DÉPENSES
    def journal_depenses(args):
        """Données du journal des dépenses pour la période demandée (page, PDF, Excel)."""
        typ = args.get("periode") if args.get("periode") in PERIODES else "mois"
        d = R.lire_date(args.get("date")) or date.today()
        du, au, titre, prec, suiv = bornes_periode(typ, d, config.ANNEE_ACTIVE)
        cat = args.get("categorie") if args.get("categorie") in CATEGORIES_DEPENSES else ""
        avec_annulees = args.get("annulees") == "1"
        sql = ("SELECT d.*, u.nom saisi_nom FROM fp_depenses d LEFT JOIN utilisateurs u ON u.id=d.saisi_par "
               "WHERE d.ecole_id=? AND d.date BETWEEN ? AND ?")
        params = [H.eco(), du.isoformat(), au.isoformat()]
        if cat:
            sql += " AND d.categorie=?"
            params.append(cat)
        if not avec_annulees:
            sql += " AND d.annule=0"
        lignes = [dict(r) for r in q(sql + " ORDER BY d.date, d.id", params)]
        # regroupement par jour avec sous-totaux (les dépenses annulées ne comptent pas)
        jours = []
        for l in lignes:
            if not jours or jours[-1]["date"] != l["date"]:
                jours.append({"date": l["date"], "lignes": [], "total": 0})
            jours[-1]["lignes"].append(l)
            if not l["annule"]:
                jours[-1]["total"] += l["montant"]
        valides = [l for l in lignes if not l["annule"]]
        total = sum(l["montant"] for l in valides)
        par_cat = {}
        for l in valides:
            par_cat[l["categorie"]] = par_cat.get(l["categorie"], 0) + l["montant"]
        recap = [{"cat": c, "montant": par_cat[c], "pct": round(100 * par_cat[c] / total, 1) if total else 0,
                  "n": sum(1 for l in valides if l["categorie"] == c)}
                 for c in CATEGORIES_DEPENSES if c in par_cat]
        cantine = sum(r["montant"] for r in recap if r["cat"].startswith("Cantine"))
        return {"periode": typ, "date": d.isoformat(), "du": du, "au": au, "titre": titre, "prec": prec.isoformat(),
                "suiv": suiv.isoformat(), "categorie": cat, "annulees": avec_annulees, "jours": jours,
                "lignes": lignes, "total": total, "nb": len(valides), "recap": recap, "cantine": cantine}

    @app.route("/depenses")
    @H.connexion_requise("depenses")
    def depenses_accueil():
        j = journal_depenses(request.args)
        b = bilan_annee()
        auj = date.today().isoformat()
        return render_template("depenses.html", j=j, b=b, periodes=PERIODES, categories=CATEGORIES_DEPENSES,
                               modes=modes(), milliers=milliers, jour_total=total_depenses(auj, auj))

    @app.route("/depenses/nouvelle", methods=["GET", "POST"])
    @H.connexion_requise("depenses")
    def depense_nouvelle():
        f = request.form
        if request.method == "POST":
            d = lire_date_saisie(f.get("date"))
            cat = f.get("categorie", "")
            lib = f.get("libelle", "").strip()[:200]
            montant = lire_montant(f.get("montant"))
            mode = f.get("mode") if f.get("mode") in modes() else "especes"
            erreurs = []
            if not d:
                erreurs.append("la date (obligatoire, pas dans le futur)")
            if cat not in CATEGORIES_DEPENSES:
                erreurs.append("la catégorie")
            if not lib:
                erreurs.append("le libellé")
            if not montant:
                erreurs.append(f"le montant (nombre entier positif, au plus {milliers(MONTANT_MAX)} FCFA)")
            piece = piece_nom = None
            fichier = request.files.get("piece")
            if not erreurs and fichier and fichier.filename:
                ext = fichier.filename.rsplit(".", 1)[-1].lower() if "." in fichier.filename else ""
                contenu = fichier.read(PIECE_MAX + 1)
                if ext not in PIECES or not type_piece(contenu, ext):
                    erreurs.append("la pièce justificative (photo JPG, PNG, WEBP ou fichier PDF uniquement)")
                elif len(contenu) > PIECE_MAX:
                    erreurs.append("la pièce justificative (8 Mo au maximum)")
                else:
                    os.makedirs(dossier_pieces, exist_ok=True)
                    piece = f"depense_e{H.eco()}_{secrets.token_hex(8)}.{ext}"
                    with open(os.path.join(dossier_pieces, piece), "wb") as out:
                        out.write(contenu)
                    piece_nom = os.path.basename(fichier.filename)[:120]
            if erreurs:
                flash("Dépense non enregistrée. Vérifiez " + ", ".join(erreurs) + ".", "danger")
                return render_template("depense_nouvelle.html", v=f, categories=CATEGORIES_DEPENSES, modes=modes(),
                                       milliers=milliers, du_jour=depenses_du_jour(R.lire_date(f.get("date")) or date.today()),
                                       aujourdhui=date.today().isoformat()), 400
            did = ex("""INSERT INTO fp_depenses (ecole_id, date, categorie, libelle, montant, beneficiaire, mode, reference,
                        piece, piece_nom, saisi_par, cree_le) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (H.eco(), d.isoformat(), cat, lib, montant, f.get("beneficiaire", "").strip()[:120] or None, mode,
                      f.get("reference", "").strip()[:100] or None, piece, piece_nom, g.user["id"], H.maintenant()))
            H.journal("depense", f"#{did} {d} {cat} {montant}")
            flash(f"Dépense enregistrée : {lib} – {milliers(montant)} FCFA ({H.pdfs.date_fr(d.isoformat())}).", "success")
            if f.get("suite") == "journal":
                return redirect(url_for("depenses_accueil", periode="jour", date=d.isoformat()))
            return redirect(url_for("depense_nouvelle", date=d.isoformat(), categorie=cat))
        d = date_demandee()
        if d > date.today():
            d = date.today()
        v = {"date": d.isoformat(), "categorie": request.args.get("categorie", ""), "mode": "especes"}
        return render_template("depense_nouvelle.html", v=v, categories=CATEGORIES_DEPENSES, modes=modes(),
                               milliers=milliers, du_jour=depenses_du_jour(d), aujourdhui=date.today().isoformat())

    def depenses_du_jour(d):
        lignes = q("SELECT * FROM fp_depenses WHERE ecole_id=? AND date=? ORDER BY id", (H.eco(), d.isoformat()))
        return {"date": d, "lignes": lignes, "total": sum(l["montant"] for l in lignes if not l["annule"])}

    def depense_ou_404(did):
        r = q("SELECT * FROM fp_depenses WHERE id=? AND ecole_id=?", (did, H.eco()), un=True)
        if not r:
            abort(404)
        return r

    @app.route("/depenses/<int:did>/annuler", methods=["POST"])
    @H.connexion_requise("depenses")
    def depense_annuler(did):
        r = depense_ou_404(did)
        motif = request.form.get("motif", "").strip()[:200]
        retour = R.retour_sur(request.form.get("retour"), url_for("depenses_accueil"))
        if r["annule"]:
            flash("Cette dépense est déjà annulée.", "info")
        elif not motif:
            flash("Indiquez le motif de l'annulation.", "danger")
        else:
            ex("UPDATE fp_depenses SET annule=1, annule_motif=?, annule_par=?, annule_le=? WHERE id=?",
               (motif, g.user["id"], H.maintenant(), did))
            H.journal("depense_annulee", f"#{did} {r['libelle']} {r['montant']} : {motif}")
            flash(f"Dépense annulée (elle reste visible dans le journal avec son motif) : {r['libelle']}.", "success")
        return redirect(retour)

    @app.route("/depenses/<int:did>/piece")
    @H.connexion_requise("depenses")
    def depense_piece(did):
        r = depense_ou_404(did)
        nom = os.path.basename(r["piece"] or "")
        chemin = os.path.join(dossier_pieces, nom)
        if not nom or not os.path.isfile(chemin):
            abort(404)
        ext = nom.rsplit(".", 1)[-1]
        return send_file(chemin, mimetype=PIECES.get(ext, "application/octet-stream"), as_attachment=False,
                         download_name=r["piece_nom"] or nom, max_age=0)

    @app.route("/depenses/journal.pdf")
    @H.connexion_requise("depenses")
    def depenses_pdf():
        j = journal_depenses(request.args)
        v = H.identification()
        P = H.pdfs
        cols = ["N°", "Date", "Catégorie", "Libellé", "Fournisseur / bénéficiaire", "Pièce", "Montant (FCFA)"]
        lignes, surl, n = [], {}, 0
        for jour in j["jours"]:
            for l in jour["lignes"]:
                n += 1
                lib = l["libelle"] + (f"\nANNULÉE : {l['annule_motif'] or ''}" if l["annule"] else "")
                lignes.append([n, P.date_fr(l["date"]), l["categorie"], lib, l["beneficiaire"] or "",
                               "Oui" if l["piece"] else "", ("(" + milliers(l["montant"]) + ")") if l["annule"] else milliers(l["montant"])])
                if l["annule"]:
                    surl[len(lignes) - 1] = "#FDE2E1"
            if j["periode"] != "jour":
                lignes.append(["", "", "", f"Total du {P.date_fr(jour['date'])}", "", "", milliers(jour["total"])])
                surl[len(lignes) - 1] = "#EEF2F6"
        if not lignes:
            lignes = [["", "", "", "Aucune dépense sur la période.", "", "", ""]]
        recap = [["Catégorie", "Nombre", "Montant (FCFA)", "%"]]
        recap += [[r["cat"], r["n"], milliers(r["montant"]), f"{r['pct']} %".replace(".", ",")] for r in j["recap"]]
        recap.append(["TOTAL", j["nb"], milliers(j["total"]), "100 %" if j["total"] else ""])
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Spacer
        apres = [Spacer(1, 6), KeepTogether([P.paragraphe("RÉCAPITULATIF PAR CATÉGORIE", 9, True),
                                             P.mini_tableau(recap, largeurs=[70 * mm, 20 * mm, 32 * mm, 18 * mm])])]
        pdf = P.document_tableau(
            "JOURNAL DES DÉPENSES", cols, lignes, total=["", "", "", "TOTAL DE LA PÉRIODE", "", "", milliers(j["total"])],
            sous_titre=j["titre"] + (f" — catégorie : {j['categorie']}" if j["categorie"] else ""),
            infos=[("École", v.get("ecole")), ("Année scolaire", config.ANNEE_ACTIVE),
                   ("Période", f"du {j['du'].strftime('%d/%m/%Y')} au {j['au'].strftime('%d/%m/%Y')}"),
                   ("Total des dépenses", f"{milliers(j['total'])} FCFA"),
                   ("dont fonds de cantine", f"{milliers(j['cantine'])} FCFA"), ("Nombre de dépenses", j["nb"])],
            infos_haut=infos_haut(v), largeurs=[6, 14, 26, 44, 26, 9, 18], taille=7.5, surlignes=surl, apres=apres,
            signatures=signatures_pdf(v),
            notes_bas=["Les dépenses annulées figurent entre parenthèses (sur fond rose) et ne sont pas comptées dans les totaux."])
        H.journal("depenses_pdf", j["titre"])
        return H.pdf_reponse(pdf, f"journal_depenses_{j['periode']}_{j['date']}.pdf")

    @app.route("/depenses/journal.xlsx")
    @H.connexion_requise("depenses")
    def depenses_xlsx():
        j = journal_depenses(request.args)
        v = H.identification()
        ent = ["N°", "Date", "Catégorie", "Libellé", "Fournisseur / bénéficiaire", "Mode", "Référence", "Pièce jointe",
               "Montant (FCFA)", "État", "Motif d'annulation"]
        lignes = []
        for i, l in enumerate(j["lignes"], 1):
            lignes.append([i, H.pdfs.date_fr(l["date"]), l["categorie"], l["libelle"], l["beneficiaire"] or "",
                           modes().get(l["mode"] or "", l["mode"] or ""), l["reference"] or "",
                           "Oui" if l["piece"] else "Non", l["montant"], "Annulée" if l["annule"] else "Valide",
                           l["annule_motif"] or ""])
        lignes.append(["", "", "", "TOTAL (hors annulées)", "", "", "", "", j["total"], "", ""])
        par_jour = [[H.pdfs.date_fr(x["date"]), sum(1 for l in x["lignes"] if not l["annule"]), x["total"]] for x in j["jours"]]
        par_jour.append(["TOTAL", j["nb"], j["total"]])
        recap = [[r["cat"], r["n"], r["montant"], r["pct"]] for r in j["recap"]] + [["TOTAL", j["nb"], j["total"], 100 if j["total"] else 0]]
        haut = [f"Journal des dépenses — {v.get('ecole')}", j["titre"] + (f" — {j['categorie']}" if j["categorie"] else "")]
        try:
            return H.xlsx.reponse_classeur(f"journal_depenses_{j['periode']}_{j['date']}.xlsx", [
                ("Journal", ent, lignes, {"titre_haut": haut}),
                ("Par jour", ["Date", "Nombre", "Total (FCFA)"], par_jour, {"titre_haut": haut}),
                ("Par catégorie", ["Catégorie", "Nombre", "Montant (FCFA)", "%"], recap, {"titre_haut": haut})])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("depenses_accueil", periode=j["periode"], date=j["date"]))

    # ============================================================== RECETTES / SUBVENTIONS
    def liste_recettes(args):
        d1, d2 = H.bornes_annee()
        origine = args.get("origine") if args.get("origine") in ORIGINES_RECETTES else ""
        avec_annulees = args.get("annulees") == "1"
        sql = ("SELECT r.*, u.nom saisi_nom FROM fp_recettes r LEFT JOIN utilisateurs u ON u.id=r.saisi_par "
               "WHERE r.ecole_id=? AND r.date BETWEEN ? AND ?")
        params = [H.eco(), d1, d2]
        if origine:
            sql += " AND r.origine=?"
            params.append(origine)
        if not avec_annulees:
            sql += " AND r.annule=0"
        lignes = q(sql + " ORDER BY r.date, r.id", params)
        par_origine = {}
        for r in q("SELECT origine, COUNT(*) n, SUM(montant) m FROM fp_recettes WHERE ecole_id=? AND annule=0 "
                   "AND date BETWEEN ? AND ? GROUP BY origine", (H.eco(), d1, d2)):
            par_origine[r["origine"]] = (r["n"], r["m"])
        return {"lignes": lignes, "origine": origine, "annulees": avec_annulees,
                "total": sum(l["montant"] for l in lignes if not l["annule"]), "par_origine": par_origine}

    @app.route("/recettes", methods=["GET", "POST"])
    @H.connexion_requise("depenses")
    def recettes_accueil():
        f = request.form
        if request.method == "POST":
            if f.get("action") == "ouverture":
                brut = str(f.get("solde_ouverture", "")).replace(" ", "").replace("\xa0", "")
                neg = brut.startswith("-")
                n = 0 if brut in ("", "0") else lire_montant(brut.lstrip("-"))
                if n is None:
                    flash("Solde d'ouverture invalide (nombre entier en FCFA).", "danger")
                else:
                    ecrire_parametre("solde_ouverture", -n if neg else n)
                    H.journal("solde_ouverture", f"{config.ANNEE_ACTIVE} : {-n if neg else n}")
                    flash(f"Solde d'ouverture {config.ANNEE_ACTIVE} enregistré : {milliers(-n if neg else n)} FCFA.", "success")
                return redirect(url_for("recettes_accueil"))
            d = lire_date_saisie(f.get("date"))
            origine = f.get("origine", "")
            lib = f.get("libelle", "").strip()[:200]
            montant = lire_montant(f.get("montant"))
            erreurs = []
            if not d:
                erreurs.append("la date (obligatoire, pas dans le futur)")
            if origine not in ORIGINES_RECETTES:
                erreurs.append("l'origine")
            if not lib:
                erreurs.append("le libellé")
            if not montant:
                erreurs.append("le montant")
            if erreurs:
                flash("Recette non enregistrée. Vérifiez " + ", ".join(erreurs) + ".", "danger")
            else:
                rid = ex("""INSERT INTO fp_recettes (ecole_id, date, origine, provenance, libelle, montant, mode, reference,
                            saisi_par, cree_le) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         (H.eco(), d.isoformat(), origine, f.get("provenance", "").strip()[:120] or None, lib, montant,
                          f.get("mode") if f.get("mode") in modes() else "especes",
                          f.get("reference", "").strip()[:100] or None, g.user["id"], H.maintenant()))
                H.journal("recette", f"#{rid} {d} {origine} {montant}")
                flash(f"Recette enregistrée : {lib} – {milliers(montant)} FCFA.", "success")
            return redirect(url_for("recettes_accueil"))
        r = liste_recettes(request.args)
        return render_template("recettes.html", r=r, b=bilan_annee(), p=parametres(), origines=ORIGINES_RECETTES,
                               modes=modes(), milliers=milliers, aujourdhui=date.today().isoformat())

    @app.route("/recettes/<int:rid>/annuler", methods=["POST"])
    @H.connexion_requise("depenses")
    def recette_annuler(rid):
        r = q("SELECT * FROM fp_recettes WHERE id=? AND ecole_id=?", (rid, H.eco()), un=True)
        if not r:
            abort(404)
        motif = request.form.get("motif", "").strip()[:200]
        if r["annule"]:
            flash("Cette recette est déjà annulée.", "info")
        elif not motif:
            flash("Indiquez le motif de l'annulation.", "danger")
        else:
            ex("UPDATE fp_recettes SET annule=1, annule_motif=?, annule_par=?, annule_le=? WHERE id=?",
               (motif, g.user["id"], H.maintenant(), rid))
            H.journal("recette_annulee", f"#{rid} {r['libelle']} {r['montant']} : {motif}")
            flash(f"Recette annulée : {r['libelle']}.", "success")
        return redirect(url_for("recettes_accueil"))

    def lignes_recettes_export(r):
        return [[i, H.pdfs.date_fr(l["date"]), l["origine"], l["provenance"] or "", l["libelle"], l["reference"] or "",
                 l["montant"], ("Annulée : " + (l["annule_motif"] or "")) if l["annule"] else ""]
                for i, l in enumerate(r["lignes"], 1)]

    @app.route("/recettes/liste.pdf")
    @H.connexion_requise("depenses")
    def recettes_pdf():
        r = liste_recettes(request.args)
        b = bilan_annee()
        v = H.identification()
        P = H.pdfs
        lignes, surl = [], {}
        for i, l in enumerate(lignes_recettes_export(r)):
            l[6] = ("(" + milliers(l[6]) + ")") if l[7] else milliers(l[6])
            lignes.append(l)
            if l[7]:
                surl[i] = "#FDE2E1"
        if not lignes:
            lignes = [["", "", "Aucune recette enregistrée.", "", "", "", "", ""]]
        synth = [["Rubrique", "Montant (FCFA)"], ["Solde d'ouverture de l'année", milliers(b["ouverture"])],
                 ["Subventions, dons et autres recettes", milliers(b["recettes"])],
                 ["Paiements de cantine des élèves", milliers(b["cantine"])],
                 ["Frais de dépôt de dossier CEP", milliers(b["cep"])], ["TOTAL DES FONDS REÇUS", milliers(b["recu"])],
                 ["Dépenses de l'année", milliers(b["depenses"])], ["SOLDE EN CAISSE", milliers(b["solde"])]]
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Spacer
        apres = [Spacer(1, 6), KeepTogether([P.paragraphe("SITUATION DE LA CAISSE", 9, True),
                                             P.mini_tableau(synth, largeurs=[80 * mm, 35 * mm])])]
        pdf = P.document_tableau(
            "SUBVENTIONS ET RECETTES", ["N°", "Date", "Origine", "Provenance", "Libellé", "Référence", "Montant (FCFA)", "Observation"],
            lignes, total=["", "", "", "", "TOTAL", "", milliers(r["total"]), ""], paysage=True,
            sous_titre=f"Année scolaire {config.ANNEE_ACTIVE}" + (f" — {r['origine']}" if r["origine"] else ""),
            infos=[("École", v.get("ecole")), ("Année scolaire", config.ANNEE_ACTIVE),
                   ("Total des recettes", f"{milliers(r['total'])} FCFA")],
            infos_haut=infos_haut(v), largeurs=[5, 12, 28, 22, 44, 18, 16, 22], surlignes=surl, apres=apres,
            signatures=signatures_pdf(v))
        H.journal("recettes_pdf", config.ANNEE_ACTIVE)
        return H.pdf_reponse(pdf, f"recettes_{config.ANNEE_ACTIVE}.pdf")

    @app.route("/recettes/liste.xlsx")
    @H.connexion_requise("depenses")
    def recettes_xlsx():
        r = liste_recettes(request.args)
        lignes = lignes_recettes_export(r) + [["", "", "", "", "TOTAL (hors annulées)", "", r["total"], ""]]
        try:
            return H.xlsx.reponse_xlsx(f"recettes_{config.ANNEE_ACTIVE}.xlsx",
                                       ["N°", "Date", "Origine", "Provenance", "Libellé", "Référence", "Montant (FCFA)", "Observation"],
                                       lignes, "Recettes", [f"Subventions et recettes — {H.identification().get('ecole')}",
                                                            f"Année scolaire {config.ANNEE_ACTIVE}"])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("recettes_accueil"))

    # ============================================================== FRAIS DE DOSSIER CEP
    def candidats_cep():
        """Élèves inscrits des classes de CM2 de l'école (autorisées pour l'utilisateur), avec leur paiement."""
        cls = [c for c in H.classes_autorisees() if (c["niveau"] or "").upper() == "CM2"]
        pay = {r["eleve_id"]: r for r in q("SELECT * FROM fp_cep_frais WHERE ecole_id=? AND annee=?",
                                           (H.eco(), config.ANNEE_ACTIVE))}
        groupes = []
        for c in cls:
            el = q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (c["id"],))
            groupes.append({"c": c, "eleves": [{"e": e, "p": pay.get(e["id"])} for e in el]})
        tous = [x for gr in groupes for x in gr["eleves"]]
        payes = [x for x in tous if x["p"]]
        return {"groupes": groupes, "nb": len(tous), "payes": len(payes), "total": sum(x["p"]["montant"] for x in payes),
                "filles": sum(1 for x in tous if x["e"]["sexe"] == "F"),
                "payes_f": sum(1 for x in payes if x["e"]["sexe"] == "F")}

    @app.route("/cep-frais", methods=["GET", "POST"])
    @H.connexion_requise("depenses")
    def cep_frais():
        p = parametres()
        if request.method == "POST":
            f = request.form
            if f.get("action") == "montant":
                m = lire_montant(f.get("montant_cep"), 1_000_000)
                if m is None:
                    flash("Montant par candidat invalide (nombre entier de 1 à 1 000 000 FCFA).", "danger")
                else:
                    ecrire_parametre("montant_cep", m)
                    H.journal("cep_frais_montant", f"{config.ANNEE_ACTIVE} : {m}")
                    flash(f"Montant du dossier CEP fixé à {milliers(m)} FCFA par candidat. Les paiements déjà "
                          "enregistrés gardent leur montant.", "success")
                return redirect(url_for("cep_frais"))
            if not p["montant_cep"]:
                flash("Fixez d'abord le montant du dossier CEP par candidat.", "danger")
                return redirect(url_for("cep_frais"))
            d1, d2 = H.bornes_annee()
            data = candidats_cep()
            existants = {x["e"]["id"]: x["p"] for gr in data["groupes"] for x in gr["eleves"]}
            ajout = retrait = modif = 0
            refus = []
            db = H.get_db()
            for eid, pay in existants.items():
                coche = f.get(f"p_{eid}") == "1"
                if coche:
                    d = lire_date_saisie(f.get(f"d_{eid}")) or (None if f.get(f"d_{eid}") else date.today())
                    if not d or not d1 <= d.isoformat() <= d2:
                        refus.append(eid)
                        continue
                    if not pay:
                        db.execute("INSERT INTO fp_cep_frais (eleve_id, annee, ecole_id, montant, date, saisi_par, maj) "
                                   "VALUES (?,?,?,?,?,?,?)", (eid, config.ANNEE_ACTIVE, H.eco(), p["montant_cep"],
                                                              d.isoformat(), g.user["id"], H.maintenant()))
                        ajout += 1
                    elif pay["date"] != d.isoformat():
                        db.execute("UPDATE fp_cep_frais SET date=?, saisi_par=?, maj=? WHERE eleve_id=? AND annee=?",
                                   (d.isoformat(), g.user["id"], H.maintenant(), eid, config.ANNEE_ACTIVE))
                        modif += 1
                elif pay:
                    db.execute("DELETE FROM fp_cep_frais WHERE eleve_id=? AND annee=?", (eid, config.ANNEE_ACTIVE))
                    retrait += 1
            db.commit()
            H.journal("cep_frais", f"+{ajout} / -{retrait} / ~{modif}")
            flash(f"Frais de dossier CEP enregistrés : {ajout} paiement(s) ajouté(s), {retrait} retiré(s), "
                  f"{modif} date(s) modifiée(s).", "success")
            if refus:
                flash(f"{len(refus)} paiement(s) non enregistré(s) : date invalide (dans le futur ou hors de l'année "
                      f"scolaire {config.ANNEE_ACTIVE}).", "warning")
            return redirect(url_for("cep_frais"))
        return render_template("cep_frais.html", d=candidats_cep(), p=p, milliers=milliers,
                               aujourdhui=date.today().isoformat())

    @app.route("/cep-frais/liste.pdf")
    @H.connexion_requise("depenses")
    def cep_frais_pdf():
        d = candidats_cep()
        p = parametres()
        v = H.identification()
        P = H.pdfs
        lignes, surl = [], {}
        filtre = request.args.get("filtre")      # payes | impayes | (tous)
        for gr in d["groupes"]:
            for x in gr["eleves"]:
                if (filtre == "payes" and not x["p"]) or (filtre == "impayes" and x["p"]):
                    continue
                e = x["e"]
                lignes.append([len(lignes) + 1, e["matricule"] or "", f"{e['nom']} {e['prenoms']}", e["sexe"], gr["c"]["nom"],
                               "PAYÉ" if x["p"] else "NON PAYÉ", P.date_fr(x["p"]["date"]) if x["p"] else "",
                               milliers(x["p"]["montant"]) if x["p"] else ""])
                if not x["p"]:
                    surl[len(lignes) - 1] = "#FEF0C7"
        if not lignes:
            lignes = [["", "", "Aucun candidat (aucun élève inscrit en CM2)." if not d["nb"] else "Aucun candidat dans cette liste.",
                       "", "", "", "", ""]]
        titre = {"payes": " — candidats ayant payé", "impayes": " — candidats n'ayant pas payé"}.get(filtre, "")
        pdf = P.document_tableau(
            "FRAIS DE DÉPÔT DE DOSSIER DU CEP", ["N°", "Matricule", "Nom et prénoms", "Sexe", "Classe", "Situation", "Date", "Montant (FCFA)"],
            lignes, total=["", "", "TOTAL ENCAISSÉ", "", "", f"{d['payes']} / {d['nb']}", "", milliers(d["total"])],
            sous_titre=f"Année scolaire {config.ANNEE_ACTIVE}{titre}", cycle="primaire",
            infos=[("École", v.get("ecole")), ("Montant par candidat", f"{milliers(p['montant_cep'])} FCFA"),
                   ("Candidats", f"{d['nb']} dont {d['filles']} filles"), ("Ont payé", f"{d['payes']} dont {d['payes_f']} filles"),
                   ("N'ont pas payé", d["nb"] - d["payes"]), ("Total encaissé", f"{milliers(d['total'])} FCFA")],
            infos_haut=infos_haut(v), largeurs=[6, 22, 50, 8, 14, 16, 16, 18], surlignes=surl, signatures=signatures_pdf(v))
        H.journal("cep_frais_pdf", filtre or "tous")
        return H.pdf_reponse(pdf, f"frais_dossier_cep_{config.ANNEE_ACTIVE}.pdf")

    # ============================================================== IMPAYÉS DE CANTINE
    def impayes(args):
        typ = args.get("periode") if args.get("periode") in PERIODES_IMPAYES else "semaine"
        d = R.lire_date(args.get("date")) or date.today()
        du, au, titre, prec, suiv = bornes_periode(typ, d, config.ANNEE_ACTIVE)
        auj = date.today()
        cal = R.Calendrier(H, H.eco())
        # jours de cantine : du lundi au vendredi, jours de classe du calendrier scolaire, jusqu'à aujourd'hui
        jours = [x for x in R.jours_entre(du, min(au, auj)) if x.weekday() < 5 and cal.demi(x) > 0]
        isos = [x.isoformat() for x in jours]
        cls = H.classes_autorisees()
        cid = args.get("classe", type=int)
        if cid:
            H.verifier_classe(cid)
            cls = [c for c in cls if c["id"] == cid]
        cfgs = {r["classe_id"]: r for r in q("SELECT * FROM cantine_config")}
        tous = args.get("tous") == "1"
        groupes, non_ouvertes = [], []
        for c in cls:
            cfg = cfgs.get(c["id"])
            if not (cfg and cfg["valide"] and cfg["montant_jour"] > 0):
                non_ouvertes.append(c)
                continue
            # paiements de la période entière (l'encaissé compte aussi un jour payé puis déclaré sans classe)
            payes = {(r["eleve_id"], r["date"]): r["montant"] for r in q(
                """SELECT p.eleve_id, p.date, p.montant FROM cantine_paiements p JOIN eleves e ON e.id=p.eleve_id
                   WHERE e.classe_id=? AND e.statut='inscrit' AND p.date BETWEEN ? AND ?""",
                (c["id"], du.isoformat(), au.isoformat()))}
            encaisse = sum(payes.values())
            eleves = []
            for e in q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (c["id"],)):
                cases = [(e["id"], j) in payes for j in isos]
                manque = [jours[i] for i, ok in enumerate(cases) if not ok]
                if manque or tous:
                    eleves.append({"e": e, "cases": cases, "manque": manque, "n": len(manque),
                                   "du": len(manque) * cfg["montant_jour"]})
            groupes.append({"c": c, "cfg": cfg, "eleves": eleves, "n": sum(x["n"] for x in eleves),
                            "du": sum(x["du"] for x in eleves), "concernes": sum(1 for x in eleves if x["n"]),
                            "encaisse": encaisse,
                            "semaine": lundi(eleves[0]["manque"][0] if eleves and eleves[0]["manque"] else (jours[0] if jours else du)).isoformat()})
        return {"periode": typ, "date": d.isoformat(), "du": du, "au": au, "titre": titre, "prec": prec.isoformat(),
                "suiv": suiv.isoformat(), "jours": jours, "cid": cid, "cls": H.classes_autorisees(), "tous": tous,
                "groupes": groupes, "non_ouvertes": non_ouvertes, "futur": au > auj,
                "n": sum(gr["n"] for gr in groupes), "du_total": sum(gr["du"] for gr in groupes),
                "concernes": sum(gr["concernes"] for gr in groupes), "encaisse": sum(gr["encaisse"] for gr in groupes)}

    @app.route("/cantine/impayes")
    @H.connexion_requise("cantine")
    def cantine_impayes():
        return render_template("cantine_impayes.html", r=impayes(request.args), periodes=PERIODES_IMPAYES,
                               milliers=milliers, jc=JOURS_COURTS, lundi=lundi)

    @app.route("/cantine/impayes.pdf")
    @H.connexion_requise("cantine")
    def cantine_impayes_pdf():
        r = impayes(request.args)
        v = H.identification()
        P = H.pdfs
        lignes = []
        for gr in r["groupes"]:
            for x in gr["eleves"]:
                e = x["e"]
                jours = ", ".join(f"{JOURS_COURTS[j.weekday()]} {j.strftime('%d/%m')}" for j in x["manque"]) or "—"
                lignes.append([len(lignes) + 1, f"{e['nom']} {e['prenoms']}", e["sexe"], gr["c"]["nom"],
                               milliers(gr["cfg"]["montant_jour"]), jours, x["n"], milliers(x["du"])])
        if not lignes:
            lignes = [["", "Aucun impayé sur la période." if r["groupes"] else "Aucune classe dont la cantine est validée.",
                       "", "", "", "", "", ""]]
        portee = next((c["nom"] for c in r["cls"] if c["id"] == r["cid"]), "Toutes les classes")
        pdf = P.document_tableau(
            "CANTINE SCOLAIRE — ÉLÈVES N'AYANT PAS PAYÉ",
            ["N°", "Nom et prénoms", "Sexe", "Classe", "Montant / jour", "Jours non payés", "Nb jours", "Montant dû (FCFA)"],
            lignes, total=["", "TOTAL", "", "", "", "", r["n"], milliers(r["du_total"])], cycle="primaire",
            sous_titre=f"{r['titre']} — {portee}",
            infos=[("École", v.get("ecole")), ("Année scolaire", config.ANNEE_ACTIVE),
                   ("Jours de cantine comptés", len(r["jours"])), ("Élèves concernés", r["concernes"]),
                   ("Montant dû", f"{milliers(r['du_total'])} FCFA"), ("Encaissé sur la période", f"{milliers(r['encaisse'])} FCFA")],
            infos_haut=infos_haut(v), largeurs=[6, 40, 8, 14, 13, 62, 10, 19], taille=7.5, signatures=signatures_pdf(v),
            notes_bas=["Jours comptés : du lundi au vendredi, jours de classe du calendrier scolaire, jusqu'à la date du jour. "
                       "Montant dû = montant par jour de la classe × nombre de jours non payés."])
        H.journal("cantine_impayes_pdf", r["titre"])
        return H.pdf_reponse(pdf, f"cantine_impayes_{r['periode']}_{r['date']}.pdf")
