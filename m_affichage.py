# -*- coding: utf-8 -*-
"""Tableau d'affichage : liste de classe à afficher (N°, nom, prénoms, sexe, âge, scolarité, contact des parents),
répartition par sexe, récapitulatifs statistiques (scolarité × sexe, âge × sexe) avec graphiques SVG, signatures
digitales du titulaire et du directeur, PDF A4 officiel.

* /affichage                       : choix de la classe puis tableau complet (en-tête, liste, statistiques)
* /affichage/enregistrer   (POST)  : « Sauvegarder » — en-tête + scolarité et contact de chaque élève (en base)
* /affichage/reinitialiser (POST)  : « Réinitialiser » — en-tête ramené aux valeurs de la fiche de l'école
* /affichage/eleve         (POST)  : « Ajouter élève » — vrai élève inscrit dans la classe (matricule attribué)
* /affichage/importer      (POST)  : « Importer Excel » — élèves créés / fiches complétées
* /affichage/modele.xlsx           : modèle Excel vierge pour l'import
* /affichage/pdf       (GET/POST)  : PDF A4 (POST = valeurs d'en-tête affichées à l'écran, non enregistrées)

Âge : âge révolu au 31 décembre de la première année de l'année scolaire (ex. 31/12/2026 pour 2026-2027),
convention des statistiques scolaires ; l'utilisateur peut choisir l'âge à la date du jour (?age=jour).
Les fonctions d'ajout / import d'élèves sont partagées avec le registre de présence (m_registre).
"""
from datetime import date

from flask import flash, g, redirect, render_template, request, url_for
from markupsafe import Markup, escape

import m_registre as R

# Champs d'en-tête enregistrés (M.identification)
CHAMPS_ENTETE = ("ddemp", "cs", "ecole", "cours", "annee", "titulaire_titre", "titulaire_nom",
                 "directeur_titre", "directeur_nom")
COUL_F, COUL_G = "#C2185B", "#1F4E79"
NON_RENSEIGNE = "Non renseigné"


# ============================================================ calculs (purs, testables)
def age_au(date_naissance, ref):
    """Âge révolu (années entières) à la date ref ; None si la date de naissance est absente ou invalide."""
    dn = R.lire_date(date_naissance)
    if not dn or dn > ref:
        return None
    return ref.year - dn.year - ((ref.month, ref.day) < (dn.month, dn.day))


def date_reference(annee, mode):
    """31 décembre de la première année scolaire (défaut) ou date du jour."""
    if mode == "jour":
        return date.today()
    return date(int(annee[:4]), 12, 31)


def pct(n, total):
    return round(100 * n / total, 1) if total else 0.0


def repartition(eleves):
    """Filles / garçons en nombre et en % (les deux pourcentages totalisent exactement 100 %)."""
    n = len(eleves)
    f = sum(1 for e in eleves if e["sexe"] == "F")
    pf = pct(f, n)
    return {"f": f, "g": n - f, "total": n, "pf": pf, "pg": round(100 - pf, 1) if n else 0.0}


def tableau_croise(valeurs):
    """valeurs : liste de (clé ou None, sexe). Retourne lignes [{cle, f, g, t, pct}] triées + total.
    Les clés None sont regroupées en fin de tableau (« Non renseigné »)."""
    compte = {}
    for cle, sexe in valeurs:
        c = compte.setdefault(cle, {"f": 0, "g": 0})
        c["f" if sexe == "F" else "g"] += 1
    n = len(valeurs)
    lignes = []
    for cle in sorted((k for k in compte if k is not None)) + ([None] if None in compte else []):
        c = compte[cle]
        lignes.append({"cle": cle, "lib": NON_RENSEIGNE if cle is None else str(cle), "f": c["f"], "g": c["g"],
                       "t": c["f"] + c["g"], "pct": pct(c["f"] + c["g"], n)})
    tot = {"f": sum(l["f"] for l in lignes), "g": sum(l["g"] for l in lignes), "t": n, "pct": 100.0 if n else 0.0}
    return lignes, tot


def pct_fr(v):
    return (f"{v:.1f}".replace(".", ",").replace(",0", "")) + " %"


def svg_barres(lignes, titre, unite=""):
    """Graphique SVG en barres groupées Filles / Garçons (sans bibliothèque externe)."""
    if not lignes:
        return Markup('<p class="aide">Aucune donnée à représenter.</p>')
    n = len(lignes)
    vmax = max(max(l["f"], l["g"]) for l in lignes) or 1
    larg_groupe = 58
    g0, haut, bas = 34, 150, 44  # marge gauche, hauteur utile, marge basse
    W = max(g0 + n * larg_groupe + 10, 200)  # largeur mini : la légende Filles / Garçons doit tenir
    Hs = haut + bas + 26
    y0 = 20 + haut  # ligne de base
    pas = max(1, -(-vmax // 5))
    out = [f'<svg viewBox="0 0 {W} {Hs}" width="{W}" height="{Hs}" role="img" aria-label="{escape(titre)}" '
           f'class="aff-svg" xmlns="http://www.w3.org/2000/svg" font-family="system-ui,Arial,sans-serif" font-size="11">',
           f'<title>{escape(titre)}</title>']
    # graduations
    v = 0
    while v <= vmax:
        y = y0 - haut * v / vmax
        out.append(f'<line x1="{g0}" y1="{y:.1f}" x2="{W - 6}" y2="{y:.1f}" stroke="#E4E7EC"/>'
                   f'<text x="{g0 - 5}" y="{y + 4:.1f}" text-anchor="end" fill="#667085">{v}</text>')
        v += pas
    out.append(f'<line x1="{g0}" y1="{y0}" x2="{W - 6}" y2="{y0}" stroke="#667085"/>')
    for i, l in enumerate(lignes):
        x = g0 + i * larg_groupe + 8
        for j, (val, coul, lib) in enumerate(((l["f"], COUL_F, "Filles"), (l["g"], COUL_G, "Garçons"))):
            h = haut * val / vmax
            xx = x + j * 21
            out.append(f'<rect x="{xx}" y="{y0 - h:.1f}" width="19" height="{h:.1f}" fill="{coul}" rx="2">'
                       f'<title>{escape(l["lib"])}{escape(unite)} – {lib} : {val}</title></rect>')
            if val:
                out.append(f'<text x="{xx + 9.5}" y="{y0 - h - 3:.1f}" text-anchor="middle" fill="#344054" '
                           f'font-size="10">{val}</text>')
        lib = l["lib"] if l["cle"] is None else f'{l["lib"]}{unite}'
        out.append(f'<text x="{x + 20}" y="{y0 + 14}" text-anchor="middle" fill="#344054">'
                   f'{escape(lib if len(lib) <= 9 else "N. R.")}</text>')
    # légende
    ly = Hs - 10
    out.append(f'<rect x="{g0}" y="{ly - 9}" width="11" height="11" fill="{COUL_F}"/><text x="{g0 + 15}" y="{ly}">Filles</text>'
               f'<rect x="{g0 + 70}" y="{ly - 9}" width="11" height="11" fill="{COUL_G}"/><text x="{g0 + 85}" y="{ly}">Garçons</text>')
    out.append("</svg>")
    return Markup("".join(out))


def graphique_pdf(lignes, titre, unite=""):
    """Même graphique pour le PDF (ReportLab graphics, flowable Drawing)."""
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    d = Drawing(250, 125)
    d.add(String(125, 115, titre, fontName="Helvetica-Bold", fontSize=8, textAnchor="middle"))
    if not lignes:
        d.add(String(125, 70, "Aucune donnée", fontName="Helvetica", fontSize=8, textAnchor="middle"))
        return d
    bc = VerticalBarChart()
    bc.x, bc.y, bc.height = 28, 28, 76
    bc.width = min(212, 26 + 34 * len(lignes))  # barres de largeur raisonnable même avec une seule catégorie
    bc.data = [[l["f"] for l in lignes], [l["g"] for l in lignes]]
    bc.categoryAxis.categoryNames = [("N. R." if l["cle"] is None else f'{l["lib"]}{unite}') for l in lignes]
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.fontName = "Helvetica"
    bc.valueAxis.labels.fontName = "Helvetica"
    bc.barLabels.fontName = "Helvetica"
    bc.valueAxis.valueMin = 0
    vmax = max(max(l["f"], l["g"]) for l in lignes) or 1
    bc.valueAxis.valueMax = vmax
    bc.valueAxis.valueStep = max(1, -(-vmax // 5))
    bc.valueAxis.labels.fontSize = 7
    bc.bars[0].fillColor = colors.HexColor(COUL_F)
    bc.bars[1].fillColor = colors.HexColor(COUL_G)
    bc.barLabelFormat = "%d"
    bc.barLabels.fontSize = 6.5
    bc.barLabels.nudge = 5
    bc.groupSpacing = 6
    d.add(bc)
    d.add(Rect(60, 5, 7, 7, fillColor=colors.HexColor(COUL_F), strokeColor=None))
    d.add(String(70, 6, "Filles", fontName="Helvetica", fontSize=7.5))
    d.add(Rect(120, 5, 7, 7, fillColor=colors.HexColor(COUL_G), strokeColor=None))
    d.add(String(130, 6, "Garçons", fontName="Helvetica", fontSize=7.5))
    return d


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex

    def cle_entete(cid):
        return f"e{H.eco()}:affichage:c{cid}"

    def entete(cl):
        """Valeurs par défaut (fiche école + classe) remplacées par l'en-tête enregistré pour la classe."""
        v = H.identification(cl)
        sauve = H.doc_lire(cle_entete(cl["id"]), None) or {}
        v.update({k: sauve[k] for k in CHAMPS_ENTETE if sauve.get(k)})
        return v

    def eleves_de(cid):
        return q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (cid,))

    def mode_age():
        return "jour" if request.values.get("age") == "jour" else "31dec"

    def donnees(cl, v, mode):
        """Liste avec âges + répartition + récapitulatifs (partagés par la page et le PDF)."""
        annee = R.annee_valide(v.get("annee"), H.config.ANNEE_ACTIVE)
        ref = date_reference(annee, mode)
        lignes = []
        for e in eleves_de(cl["id"]):
            sc = str(e["annees_scolarite"] if e["annees_scolarite"] is not None else "").strip()
            lignes.append({"e": e, "age": age_au(e["date_naissance"], ref), "sc": int(sc) if sc.isdigit() else None})
        rep = repartition([l["e"] for l in lignes])
        sco, sco_tot = tableau_croise([(l["sc"], l["e"]["sexe"]) for l in lignes])
        ages, ages_tot = tableau_croise([(l["age"], l["e"]["sexe"]) for l in lignes])
        return {"lignes": lignes, "rep": rep, "sco": sco, "sco_tot": sco_tot, "ages": ages, "ages_tot": ages_tot,
                "ref": ref, "annee": annee}

    def classe_choisie():
        cls = H.classes_autorisees()
        cid = request.values.get("classe", type=int)
        if cid is None and len(cls) == 1:
            cid = cls[0]["id"]
        if cid is None:
            return cls, None
        H.verifier_classe(cid)
        return cls, H.classe_ou_404(cid)

    def retour(cid):
        return redirect(url_for("affichage_accueil", classe=cid, age=request.values.get("age") or None))

    def classe_post():
        cid = request.form.get("classe", type=int)
        H.verifier_classe(cid)
        return H.classe_ou_404(cid)

    # -------------------------------------------------------------- page principale
    @app.route("/affichage")
    @H.connexion_requise("affichage")
    def affichage_accueil():
        cls, cl = classe_choisie()
        if not cl:
            eff = {r["classe_id"]: r for r in q(
                "SELECT classe_id, COUNT(*) n, SUM(sexe='F') f FROM eleves WHERE statut='inscrit' GROUP BY classe_id")}
            return render_template("affichage_accueil.html", cls=cls, cl=None, eff=eff)
        v = entete(cl)
        mode = mode_age()
        d = donnees(cl, v, mode)
        return render_template(
            "affichage_accueil.html", cls=cls, cl=cl, v=v, mode=mode, d=d, pct_fr=pct_fr,
            svg_sco=svg_barres(d["sco"], "Répartition des élèves par années de scolarité et par sexe", " an(s)"),
            svg_age=svg_barres(d["ages"], "Répartition des élèves par âge et par sexe", " ans"),
            sig_dir=g.user["role"] in ("admin", "fondateur", "directeur"))

    # -------------------------------------------------------------- Sauvegarder / Réinitialiser
    @app.route("/affichage/enregistrer", methods=["POST"])
    @H.connexion_requise("affichage")
    def affichage_enregistrer():
        """En-tête (documents_modules) + scolarité et contact des élèves (table eleves)."""
        cl = classe_post()
        f = request.form
        H.doc_ecrire(cle_entete(cl["id"]), {k: f.get(k, "").strip()[:120] for k in CHAMPS_ENTETE})
        n, erreurs = 0, []
        for e in eleves_de(cl["id"]):
            if f"sc_{e['id']}" not in f:
                continue
            sc = f.get(f"sc_{e['id']}", "").strip()
            if sc and (not sc.isdigit() or int(sc) > 20):  # contrôle : entier de 0 à 20
                erreurs.append(f"{e['nom']} {e['prenoms']} : scolarité invalide (entier de 0 à 20) — non modifiée.")
                sc = e["annees_scolarite"]
            else:
                sc = int(sc) if sc else None
            tel = f.get(f"tel_{e['id']}", e["parent_telephone"] or "").strip()[:60] or None
            if sc != e["annees_scolarite"] or tel != e["parent_telephone"]:
                ex("UPDATE eleves SET annees_scolarite=?, parent_telephone=? WHERE id=?", (sc, tel, e["id"]))
                n += 1
        for m in erreurs[:10]:
            flash(m, "warning")
        H.journal("affichage", f"{cl['nom']} : en-tête + {n} élève(s) mis à jour")
        flash(f"Tableau d'affichage enregistré ({n} fiche(s) d'élève mise(s) à jour).", "success")
        return retour(cl["id"])

    @app.route("/affichage/reinitialiser", methods=["POST"])
    @H.connexion_requise("affichage")
    def affichage_reinitialiser():
        """Efface l'en-tête enregistré : on revient aux valeurs de la fiche de l'école et de la classe."""
        cl = classe_post()
        ex("DELETE FROM documents_modules WHERE cle=?", (cle_entete(cl["id"]),))
        H.journal("affichage_reinit", cl["nom"])
        flash("En-tête réinitialisé (valeurs de la fiche de l'école). Les élèves ne sont pas modifiés.", "info")
        return retour(cl["id"])

    # -------------------------------------------------------------- ajout / import d'élèves
    @app.route("/affichage/eleve", methods=["POST"])
    @H.connexion_requise("affichage")
    def affichage_ajouter_eleve():
        cl = classe_post()
        d, err = R.lire_formulaire_eleve(request.form)
        if err:
            for m in err:
                flash(m, "danger")
        else:
            R.creer_eleve(H, cl, d["nom"], d["prenoms"], d["sexe"], date_naissance=d["date_naissance"],
                          annees_scolarite=d["annees_scolarite"], parent_telephone=d["parent_telephone"])
            flash(f"Élève {d['nom'].upper()} {d['prenoms']} ajouté(e) en {cl['nom']}.", "success")
        return retour(cl["id"])

    @app.route("/affichage/importer", methods=["POST"])
    @H.connexion_requise("affichage")
    def affichage_importer():
        cl = classe_post()
        fch = request.files.get("fichier")
        if not fch or not fch.filename:
            flash("Choisissez un fichier Excel (.xlsx) ou CSV.", "warning")
        elif not fch.filename.lower().endswith((".xlsx", ".xlsm", ".csv", ".txt")):
            flash("Format non reconnu : utilisez un fichier .xlsx ou .csv.", "danger")
        else:
            try:
                cr, co, err = R.importer_eleves(H, cl, fch)
            except (H.xlsx.ExcelIndisponible, ValueError) as e:
                flash(str(e), "danger")
            else:
                flash(f"Import terminé : {cr} élève(s) créé(s), {co} fiche(s) complétée(s).",
                      "success" if cr or co else "info")
                for m in err[:10]:
                    flash(m, "warning")
                H.journal("affichage_import", f"{cl['nom']} : {cr} créé(s), {co} complété(s)")
        return retour(cl["id"])

    @app.route("/affichage/modele.xlsx")
    @H.connexion_requise("affichage")
    def affichage_modele():
        return H.xlsx.reponse_xlsx(
            "modele_liste_eleves.xlsx",
            ["Nom", "Prénoms", "Sexe", "Date de naissance", "Scolarité", "Contact des parents"],
            [["DOSSOU", "Afi Reine", "F", "2015-03-12", 6, "01 97 00 00 00"]], titre="Élèves",
            titre_haut=["Modèle d'import — une ligne par élève (Sexe : F ou M ; date : AAAA-MM-JJ ou JJ/MM/AAAA)"])

    # -------------------------------------------------------------- PDF
    @app.route("/affichage/pdf", methods=["GET", "POST"])
    @H.connexion_requise("affichage")
    def affichage_pdf():
        cid = request.values.get("classe", type=int)
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        v = entete(cl)
        if request.method == "POST":  # valeurs affichées à l'écran (même non enregistrées)
            v.update({k: request.form.get(k, "").strip()[:120] for k in CHAMPS_ENTETE if k in request.form})
        mode = mode_age()
        d = donnees(cl, v, mode)
        P = H.pdfs
        lignes = [[i, l["e"]["nom"], l["e"]["prenoms"], l["e"]["sexe"], "" if l["age"] is None else l["age"],
                   "" if l["sc"] is None else l["sc"], l["e"]["parent_telephone"] or ""]
                  for i, l in enumerate(d["lignes"], 1)]
        rep = d["rep"]
        base_age = (f"au 31/12/{d['annee'][:4]}" if mode != "jour" else f"au {d['ref'].strftime('%d/%m/%Y')}")

        def mini(rows, tot, lib):
            data = [[lib, "F", "G", "Total", "%"]]
            data += [[r["lib"], r["f"], r["g"], r["t"], pct_fr(r["pct"])] for r in rows]
            data.append(["TOTAL", tot["f"], tot["g"], tot["t"], pct_fr(tot["pct"])])
            return P.mini_tableau(data, largeurs=[26 * mm, 12 * mm, 12 * mm, 14 * mm, 17 * mm])

        from reportlab.lib.units import mm
        from reportlab.platypus import Spacer, Table, TableStyle
        from reportlab.platypus.flowables import KeepTogether

        def colonne(titre, rows, tot, lib, gtitre, unite):
            return [P.paragraphe(titre, 9, True), mini(rows, tot, lib), graphique_pdf(rows, gtitre, unite)]

        rep_tab = P.mini_tableau([["", "Filles", "Garçons", "Total"],
                                  ["Effectif", rep["f"], rep["g"], rep["total"]],
                                  ["Pourcentage", pct_fr(rep["pf"]), pct_fr(rep["pg"]), "100 %" if rep["total"] else "0 %"]],
                                 largeurs=[28 * mm, 22 * mm, 22 * mm, 22 * mm])
        recap = Table([[colonne("RÉCAPITULATIF : SCOLARITÉ PAR SEXE", d["sco"], d["sco_tot"], "Scolarité (ans)",
                                "Scolarités par sexe", " an(s)"),
                        colonne(f"RÉCAPITULATIF : ÂGE PAR SEXE ({base_age})", d["ages"], d["ages_tot"], "Âge",
                                "Âges par sexe", " ans")]], colWidths=[93 * mm, 93 * mm])
        recap.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        apres = [Spacer(1, 5), KeepTogether([P.paragraphe("RÉPARTITION PAR SEXE", 9, True), rep_tab]),
                 Spacer(1, 3), KeepTogether([recap])]
        titre_dir = f"{'La' if (v.get('directeur_titre') or '').startswith('Directrice') else 'Le'} {v.get('directeur_titre') or 'Directeur'}"
        sigs = [((v.get("titulaire_titre") or "Le titulaire").upper(), v.get("titulaire_nom", ""),
                 P.image_data_url(H.signature(f"classe:{cl['id']}:titulaire")), False),
                (titre_dir.upper(), v.get("directeur_nom", ""),
                 P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)]
        pdf = P.pour_cycle(dict(cl).get("cycle"))(
            "LISTE DES ÉLÈVES — TABLEAU D'AFFICHAGE", ["N°", "Nom", "Prénoms", "Sexe", "Âge", "Scolarité", "Contact parents"],
            lignes, sous_titre=f"Année scolaire {v.get('annee') or d['annee']} — Âge calculé {base_age}",
            infos=[("Cours", v.get("cours")), ("Classe", cl["nom"]), ("Titulaire",
                    f"{v.get('titulaire_titre') or ''} {v.get('titulaire_nom') or ''}".strip()),
                   ("Directeur", f"{v.get('directeur_titre') or ''} {v.get('directeur_nom') or ''}".strip()),
                   ("Effectif", f"{rep['total']} (F : {rep['f']} – G : {rep['g']})"), ("Année", v.get("annee"))],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[7, 30, 40, 9, 9, 13, 32], taille=8.5, apres=apres, signatures=sigs,
            notes_bas=(["Aucun élève inscrit dans cette classe."] if not lignes else [])
            + ["Scolarité : nombre d'années de scolarité de l'élève. Âge : âge révolu " + base_age + "."])
        H.journal("affichage_pdf", cl["nom"])
        return H.pdf_reponse(pdf, f"tableau_affichage_{cl['nom'].replace(' ', '_')}.pdf")
