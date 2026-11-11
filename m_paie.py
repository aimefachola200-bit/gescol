# -*- coding: utf-8 -*-
"""
Personnel et paie.

Taux par défaut (Bénin, à confirmer avec votre comptable ; tous réglables dans Paramètres de paie) :
  - CNSS part salariale 3,6 % ; part patronale 16,4 % (9 % prestations familiales, 6,4 % pensions,
    1 % risques professionnels — ce dernier taux varie de 1 à 4 % selon l'activité) ;
  - VPS (versement patronal sur salaires) 4 % ;
  - ITS mensuel progressif : 0 % jusqu'à 60 000, 10 % jusqu'à 150 000, 15 % jusqu'à 250 000,
    19 % jusqu'à 500 000, 30 % au-delà ; calculé après déduction de la CNSS salariale.
"""
import csv
import io
from datetime import date

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

TYPES_CONTRAT = ["CDI", "CDD", "Vacataire", "Stagiaire"]
FONCTIONS = ["Enseignant(e)", "Directeur / directrice", "Censeur", "Surveillant(e)", "Secrétaire", "Comptable",
             "Gardien", "Agent d'entretien", "Cuisinier(ère)", "Chauffeur", "Autre"]

PARAM_DEFAUTS = {
    "paie_cnss_salarie": "3.6",
    "paie_cnss_patronal": "16.4",
    "paie_vps": "4",
    "paie_its_bareme": "60000:0;150000:10;250000:15;500000:19;*:30",
    "paie_its_apres_cnss": "1",
    "paie_arrondi_its": "1",           # ITS arrondi à la dizaine inférieure
}


def lire_bareme(texte):
    """« 60000:0;150000:10;*:30 » -> [(60000, 0.0), (150000, 10.0), (None, 30.0)]"""
    out = []
    for morceau in (texte or "").split(";"):
        if ":" not in morceau:
            continue
        plafond, taux = morceau.split(":", 1)
        plafond = plafond.strip()
        out.append((None if plafond in ("*", "") else int(float(plafond)), float(taux.strip().replace(",", "."))))
    if not out or out[-1][0] is not None:
        raise ValueError("Le barème doit se terminer par « *:taux » (tranche sans plafond).")
    return out


def its_mensuel(base, bareme, arrondi=True):
    impot, bas = 0.0, 0
    for plafond, taux in bareme:
        haut = plafond if plafond is not None else float("inf")
        if base > bas:
            impot += (min(base, haut) - bas) * taux / 100
        bas = haut if plafond is not None else bas
        if plafond is None or base <= haut:
            break
    impot = int(impot)
    return impot - impot % 10 if arrondi else impot


def calculer_paie(brut, p, cnss=True, its=True, retenues=0, avances=0):
    """Retourne le détail d'un bulletin de paie à partir du brut. `p` = paramètres de paie."""
    t_sal = float(p["paie_cnss_salarie"]) / 100
    t_pat = float(p["paie_cnss_patronal"]) / 100
    t_vps = float(p["paie_vps"]) / 100
    cnss_sal = round(brut * t_sal) if cnss else 0
    base_its = brut - cnss_sal if p.get("paie_its_apres_cnss", "1") == "1" else brut
    impot = its_mensuel(base_its, lire_bareme(p["paie_its_bareme"]), p.get("paie_arrondi_its", "1") == "1") if its else 0
    net = brut - cnss_sal - impot - retenues - avances
    return {"brut": brut, "cnss_salarie": cnss_sal, "its": impot, "net": net,
            "cnss_patronal": round(brut * t_pat) if cnss else 0, "vps": round(brut * t_vps),
            "base_its": base_its}


def mois_long(m):
    noms = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    a, mm = m.split("-")
    return f"{noms[int(mm) - 1]} {a}"


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config

    def params():
        v = dict(PARAM_DEFAUTS)
        v.update({k: val for k, val in H.lire_parametres().items() if k.startswith("paie_")})
        return v

    def lire_mois(m):
        try:
            a, mm = m.split("-")
            if len(a) != 4 or not 1 <= int(mm) <= 12:
                raise ValueError
            return f"{int(a):04d}-{int(mm):02d}"
        except (ValueError, AttributeError):
            abort(404)

    @app.context_processor
    def ctx_paie():
        return dict(mois_long=mois_long)

    # ------------------------------------------------------------ personnel
    def car():
        """Édition publique : module carrière (m_carriere) chargé → H.carriere ; sinon None."""
        return getattr(H, "carriere", None) if config.publique() else None

    def droit_personnel():
        """Personnel : droit « paie » (école privée) ; « carriere » (école publique : directeur, admin)."""
        if not H.peut("carriere" if config.publique() else "paie"):
            abort(403)

    @app.route("/personnel")
    @H.connexion_requise()
    def personnel():
        droit_personnel()
        tous = request.args.get("tous") == "1"
        if car():
            # école publique : personnel de l'école courante avec sa situation de carrière
            lst = car().liste(tous=tous)
            return render_template("personnel.html", lst=lst, tous=tous, masse=0, carriere=True)
        lst = q("SELECT * FROM personnel " + ("" if tous else "WHERE actif=1 ") + "ORDER BY nom, prenoms")
        masse = sum(p["salaire_base"] for p in lst if p["actif"] and p["type_contrat"] != "Vacataire")
        return render_template("personnel.html", lst=lst, tous=tous, masse=masse)

    @app.route("/personnel/nouveau", methods=["GET", "POST"])
    @app.route("/personnel/<int:pid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise()
    def personnel_form(pid=None):
        droit_personnel()
        p = q("SELECT * FROM personnel WHERE id=?", (pid,), un=True) if pid else None
        if pid and not p:
            abort(404)
        if p and car() and p["ecole_id"] != H.eco():
            abort(404)                       # fiche d'une autre école
        extra = car().options() if car() else {}
        if request.method == "POST":
            f = {k: request.form.get(k, "").strip() for k in (
                "nom", "prenoms", "sexe", "fonction", "telephone", "email", "type_contrat", "date_embauche",
                "salaire_base", "taux_horaire", "numero_cnss", "numero_paiement")}
            f["nom"] = f["nom"].upper()
            erreurs = []
            if not f["nom"] or not f["prenoms"] or not f["fonction"]:
                erreurs.append("Nom, prénoms et fonction sont obligatoires.")
            if f["type_contrat"] not in TYPES_CONTRAT:
                erreurs.append("Type de contrat invalide.")
            for k in ("salaire_base", "taux_horaire"):
                try:
                    f[k] = int((f[k] or "0").replace(" ", ""))
                    if f[k] < 0:
                        raise ValueError
                except ValueError:
                    erreurs.append("Montants invalides.")
            if car():
                v_car, err_car = car().lire(request.form, pid)
                erreurs += err_car
                extra["car"] = {**v_car, "user_id": v_car.get("user_id") or request.form.get("user_id")}
            if erreurs:
                for m in erreurs:
                    flash(m, "danger")
                if car():
                    f["id"] = pid
                    # valeurs saisies (brutes) renvoyées dans le formulaire
                    extra["car"] = {**extra["car"], **{k: request.form.get(k, "") for k in request.form}}
                return render_template("personnel_form.html", p=f, types=TYPES_CONTRAT, fonctions=FONCTIONS, **extra), 400
            f["assujetti_cnss"] = 1 if request.form.get("assujetti_cnss") else 0
            f["assujetti_its"] = 1 if request.form.get("assujetti_its") else 0
            f["actif"] = 1 if "1" in request.form.getlist("actif") else 0
            champs = list(f.keys())
            if p:
                ex(f"UPDATE personnel SET {', '.join(k + '=?' for k in champs)} WHERE id=?", [f[k] for k in champs] + [pid])
                H.journal("personnel_modifie", p["matricule"])
            else:
                pid = ex(f"INSERT INTO personnel ({', '.join(champs)}) VALUES ({', '.join('?' * len(champs))})", [f[k] for k in champs])
                mat = f"{config.ECOLE['sigle']}-RH-{pid:04d}"
                ex("UPDATE personnel SET matricule=? WHERE id=?", (mat, pid))
                if getattr(H, "carriere", None):
                    H.carriere.rattacher(pid)          # agent rattaché à l'école courante
                H.journal("personnel_cree", mat)
            if car():
                car().enregistrer(pid, v_car)
            flash("Fiche enregistrée.", "success")
            return redirect(url_for("personnel"))
        if car():
            extra["car"] = car().valeurs(pid)
        return render_template("personnel_form.html", p=p or {"type_contrat": "CDI", "assujetti_cnss": 1, "assujetti_its": 1, "actif": 1},
                               types=TYPES_CONTRAT, fonctions=FONCTIONS, **extra)

    # ------------------------------------------------------------ paie
    def recalculer(bp_id):
        bp = q("SELECT b.*, p.type_contrat, p.taux_horaire, p.assujetti_cnss, p.assujetti_its FROM bulletins_paie b "
               "JOIN personnel p ON p.id=b.personnel_id WHERE b.id=?", (bp_id,), un=True)
        base = round(bp["heures"] * bp["taux_horaire"]) if bp["type_contrat"] == "Vacataire" else bp["salaire_base"]
        d = calculer_paie(base + bp["primes"], params(), bool(bp["assujetti_cnss"]), bool(bp["assujetti_its"]),
                          bp["retenues"], bp["avances"])
        ex("UPDATE bulletins_paie SET salaire_base=?, brut=?, cnss_salarie=?, its=?, net=?, cnss_patronal=?, vps=? WHERE id=?",
           (base, d["brut"], d["cnss_salarie"], d["its"], d["net"], d["cnss_patronal"], d["vps"], bp_id))

    @app.route("/paie")
    @H.connexion_requise("paie")
    def paie_accueil():
        mois = q("""SELECT mois, COUNT(*) n, SUM(net) net, SUM(brut) brut, SUM(cnss_salarie + cnss_patronal) cnss,
                           SUM(its) its, SUM(vps) vps, MIN(statut) statut_min, MAX(statut) statut_max
                    FROM bulletins_paie GROUP BY mois ORDER BY mois DESC LIMIT 24""")
        return render_template("paie_accueil.html", mois=mois, courant=date.today().strftime("%Y-%m"))

    @app.route("/paie/<mois>", methods=["GET", "POST"])
    @H.connexion_requise("paie")
    def paie_mois(mois):
        mois = lire_mois(mois)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "preparer":
                n = 0
                for p in q("SELECT * FROM personnel WHERE actif=1"):
                    if q("SELECT 1 FROM bulletins_paie WHERE personnel_id=? AND mois=?", (p["id"], mois), un=True):
                        continue
                    bid = ex("INSERT INTO bulletins_paie (personnel_id, mois, salaire_base) VALUES (?,?,?)",
                             (p["id"], mois, p["salaire_base"]))
                    recalculer(bid)
                    n += 1
                H.journal("paie_preparee", f"{mois} : {n}")
                flash(f"{n} bulletin(s) préparé(s). Vérifiez les heures (vacataires), primes et avances.", "success")
            elif action == "enregistrer":
                for b in q("SELECT * FROM bulletins_paie WHERE mois=? AND statut='brouillon'", (mois,)):
                    vals = []
                    for k in ("heures", "primes", "retenues", "avances"):
                        brut = request.form.get(f"{k}_{b['id']}", str(b[k])).replace(" ", "").replace(",", ".") or "0"
                        try:
                            v = float(brut) if k == "heures" else int(float(brut))
                            if v < 0:
                                raise ValueError
                        except ValueError:
                            v = b[k]
                        vals.append(v)
                    ex("UPDATE bulletins_paie SET heures=?, primes=?, retenues=?, avances=? WHERE id=?", vals + [b["id"]])
                    recalculer(b["id"])
                flash("Montants enregistrés et recalculés.", "success")
            elif action == "valider":
                if g.user["role"] not in ("admin", "directeur"):
                    abort(403)
                ex("UPDATE bulletins_paie SET statut='valide', valide_par=? WHERE mois=? AND statut='brouillon'", (g.user["id"], mois))
                H.journal("paie_validee", mois)
                flash("Paie validée : elle peut être payée.", "success")
            elif action == "payer":
                mode = request.form.get("mode") or "virement"
                aujourd = date.today().isoformat()
                for b in q("SELECT b.*, p.nom, p.prenoms FROM bulletins_paie b JOIN personnel p ON p.id=b.personnel_id "
                           "WHERE b.mois=? AND b.statut='valide'", (mois,)):
                    ex("UPDATE bulletins_paie SET statut='paye', paye_le=?, mode_paiement=? WHERE id=?", (H.maintenant(), mode, b["id"]))
                    ex("INSERT INTO tresorerie (date, type, categorie, libelle, montant, mode, source, source_id, saisi_par, cree_le) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (aujourd, "sortie", "Salaires", f"Salaire {mois_long(mois)} – {b['nom']} {b['prenoms']}", b["net"],
                        mode, "paie", b["id"], g.user["id"], H.maintenant()))
                H.journal("paie_payee", mois)
                flash("Salaires marqués payés et inscrits en trésorerie.", "success")
            elif action == "rouvrir":
                if g.user["role"] not in ("admin", "directeur"):
                    abort(403)
                ex("UPDATE bulletins_paie SET statut='brouillon', valide_par=NULL WHERE mois=? AND statut='valide'", (mois,))
                flash("Paie remise en brouillon.", "success")
            return redirect(url_for("paie_mois", mois=mois))
        lst = q("""SELECT b.*, p.nom, p.prenoms, p.fonction, p.type_contrat, p.taux_horaire, p.matricule, p.numero_paiement
                   FROM bulletins_paie b JOIN personnel p ON p.id=b.personnel_id WHERE b.mois=? ORDER BY p.nom""", (mois,))
        tot = {k: sum(b[k] for b in lst) for k in ("brut", "cnss_salarie", "its", "net", "cnss_patronal", "vps", "avances", "retenues")}
        manquants = q("""SELECT COUNT(*) n FROM personnel WHERE actif=1 AND id NOT IN
                         (SELECT personnel_id FROM bulletins_paie WHERE mois=?)""", (mois,), un=True)["n"]
        statuts = {b["statut"] for b in lst}
        return render_template("paie_mois.html", mois=mois, lst=lst, tot=tot, manquants=manquants, statuts=statuts,
                               modes=config.MODES_PAIEMENT)

    @app.route("/paie/<mois>/livre.csv")
    @H.connexion_requise("paie")
    def livre_paie(mois):
        mois = lire_mois(mois)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Matricule", "Nom", "Prénoms", "Fonction", "Contrat", "Heures", "Salaire de base", "Primes", "Brut",
                    "CNSS salarié", "ITS", "Retenues", "Avances", "Net à payer", "CNSS patronal", "VPS", "N° CNSS", "Statut"])
        for b in q("""SELECT b.*, p.* , b.salaire_base sb FROM bulletins_paie b JOIN personnel p ON p.id=b.personnel_id
                      WHERE b.mois=? ORDER BY p.nom""", (mois,)):
            w.writerow([b["matricule"], b["nom"], b["prenoms"], b["fonction"], b["type_contrat"], b["heures"], b["sb"], b["primes"],
                        b["brut"], b["cnss_salarie"], b["its"], b["retenues"], b["avances"], b["net"], b["cnss_patronal"],
                        b["vps"], b["numero_cnss"] or "", b["statut"]])
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=livre_de_paie_{mois}.csv"})

    @app.route("/paie/bulletin/<int:bid>.pdf")
    @H.connexion_requise("paie")
    def bulletin_paie_pdf(bid):
        b = q("SELECT * FROM bulletins_paie WHERE id=?", (bid,), un=True)
        if not b:
            abort(404)
        p = q("SELECT * FROM personnel WHERE id=?", (b["personnel_id"],), un=True)
        code = H.enregistrer_document("bulletin_paie", None, f"Bulletin de paie {mois_long(b['mois'])} – {p['nom']} {p['prenoms']}",
                                      cle=f"paie|{bid}")
        return H.pdf_reponse(H.pdfs.bulletin_paie(b, p, mois_long(b["mois"]), params(), code),
                             f"bulletin_paie_{p['matricule']}_{b['mois']}.pdf")

    @app.route("/paie/parametres", methods=["GET", "POST"])
    @H.connexion_requise("parametres")
    def paie_parametres():
        v = params()
        if request.method == "POST":
            nouv = {k: request.form.get(k, "").strip().replace(",", ".") for k in ("paie_cnss_salarie", "paie_cnss_patronal", "paie_vps", "paie_its_bareme")}
            nouv["paie_its_apres_cnss"] = "1" if request.form.get("paie_its_apres_cnss") else "0"
            nouv["paie_arrondi_its"] = "1" if request.form.get("paie_arrondi_its") else "0"
            try:
                for k in ("paie_cnss_salarie", "paie_cnss_patronal", "paie_vps"):
                    if not 0 <= float(nouv[k]) <= 50:
                        raise ValueError("Taux entre 0 et 50 %.")
                lire_bareme(nouv["paie_its_bareme"])
            except ValueError as err:
                flash(f"Paramètre invalide : {err}", "danger")
                return render_template("paie_parametres.html", v={**v, **nouv}, exemple=None)
            db = H.get_db()
            for k, val in nouv.items():
                db.execute("INSERT INTO parametres (cle, valeur) VALUES (?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", (k, val))
            db.commit()
            H.journal("paie_parametres")
            flash("Paramètres de paie enregistrés (s'appliquent aux prochains calculs).", "success")
            return redirect(url_for("paie_parametres"))
        return render_template("paie_parametres.html", v=v, exemple=calculer_paie(150000, v))
