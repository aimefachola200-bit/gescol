# -*- coding: utf-8 -*-
"""Visites de classe et d'école des conseillers pédagogiques (CP) et des chefs de circonscription scolaire (CCS).

* /visites                               visites_accueil         liste filtrable (enseignant, visiteur, type, période)
* /visites/nouvelle           GET/POST   visite_nouvelle         saisie d'une visite
* /visites/<id>               GET/POST   visite_modifier         consultation / modification
* /visites/<id>/supprimer         POST   visite_supprimer        suppression (direction)
* /visites/<id>/fiche.pdf                visite_fiche_pdf        fiche de la visite
* /visites/fiche-vierge.pdf              visite_fiche_vierge     fiche vierge imprimable
* /visites/recapitulatif                 visites_recap           récapitulatif par enseignant (CP / CCS)
* /visites/recapitulatif.pdf             visites_recap_pdf
* /visites/recapitulatif.xlsx            visites_recap_xlsx

Interface pour les autres modules (module carrière) :
    H.nb_visites(personnel_id, annee=None) -> {"CP": n, "CCS": m}
    (visites de classe ET d'école rattachées à cet enseignant ; annee = « 2026-2027 » ou None pour toutes).

Droits : « visites » (admin, directeur, enseignant). La direction saisit, modifie et supprime toutes les visites.
Un enseignant consulte les visites de ses classes ; s'il est relié à sa fiche du personnel (personnel.user_id,
module carrière), il voit aussi ses propres visites et peut enregistrer / compléter celles qui le concernent.
"""
import json
import re
from datetime import date, datetime

from flask import abort, flash, g, redirect, render_template, request, url_for

TYPES = {"classe": "Visite de classe", "ecole": "Visite d'école"}
QUALITES = {"CP": "Conseiller pédagogique (CP)", "CCS": "Chef de circonscription scolaire (CCS)"}
RE_HEURE = re.compile(r"^([01]?\d|2[0-3])[:hH]([0-5]\d)$")
TEXTES = {"visiteur_nom": 120, "enseignant_nom": 120, "matiere": 120, "unite": 200, "dossier": 200, "sa": 300,
          "sequence": 300, "constats": 4000, "recommandations": 4000, "appreciation": 120, "suites": 4000}
ROLES_DIRECTION = ("admin", "fondateur", "directeur")
EFFECTIF_MAX = 300

SCHEMA = """
CREATE TABLE IF NOT EXISTS visites (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL,
    annee TEXT NOT NULL,                 -- année scolaire déduite de la date
    type TEXT NOT NULL,                  -- classe | ecole
    visiteur_qualite TEXT NOT NULL,      -- CP | CCS
    visiteur_nom TEXT,
    date TEXT NOT NULL,
    personnel_id INTEGER,                -- enseignant visité (table personnel)
    enseignant_nom TEXT,                 -- nom affiché (copie ou saisie libre)
    classe_id INTEGER, classe_nom TEXT,
    matiere TEXT, unite TEXT, dossier TEXT, sa TEXT, sequence TEXT,
    heure_debut TEXT, heure_fin TEXT,
    eff_g INTEGER, eff_f INTEGER, eff_t INTEGER,   -- effectif présent
    ins_g INTEGER, ins_f INTEGER,                  -- effectif inscrit au jour de la saisie
    constats TEXT, recommandations TEXT, note REAL, appreciation TEXT, suites TEXT,
    cree_par INTEGER, cree_le TEXT, maj TEXT
);
CREATE INDEX IF NOT EXISTS ix_visites_personnel ON visites(personnel_id, annee);
CREATE INDEX IF NOT EXISTS ix_visites_ecole ON visites(ecole_id, date);
"""


# ============================================================ outils purs
def lire_date(v):
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def annee_de(d):
    return f"{d.year}-{d.year + 1}" if d.month >= 9 else f"{d.year - 1}-{d.year}"


def lire_heure(v):
    s = str(v or "").strip()
    if not s:
        return ""
    m = RE_HEURE.match(s)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def lire_note(v):
    """Note sur 20 (virgule acceptée) ; vide -> None ; ValueError si hors 0–20."""
    s = str(v or "").strip().replace(",", ".")
    if not s:
        return None
    n = float(s)
    if not 0 <= n <= 20:
        raise ValueError(s)
    return round(n, 2)


def lire_effectif(v):
    s = str(v or "").strip()
    if not s:
        return None
    if not s.isdigit() or int(s) > EFFECTIF_MAX:
        raise ValueError(s)
    return int(s)


def nom_complet(p):
    return f"{(p['nom'] or '').upper()} {p['prenoms'] or ''}".strip() if p else ""


def note_txt(n):
    if n is None:
        return ""
    return (f"{n:.2f}".rstrip("0").rstrip(".")).replace(".", ",") + "/20"


def compter(visites):
    """Nombre de visites par qualité du visiteur : {"CP": n, "CCS": m}."""
    res = {"CP": 0, "CCS": 0}
    for v in visites:
        if v["visiteur_qualite"] in res:
            res[v["visiteur_qualite"]] += 1
    return res


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    # -------------------------------------------------------------- interface exposée aux autres modules
    def nb_visites(personnel_id, annee=None):
        """Nombre de visites (de classe et d'école) reçues par un membre du personnel : {"CP": n, "CCS": m}.
        annee : année scolaire « AAAA-AAAA » (None = toutes les années)."""
        sql = "SELECT visiteur_qualite, COUNT(*) n FROM visites WHERE personnel_id=?"
        params = [personnel_id]
        if annee:
            sql += " AND annee=?"
            params.append(annee)
        res = {"CP": 0, "CCS": 0}
        for r in q(sql + " GROUP BY visiteur_qualite", params):
            if r["visiteur_qualite"] in res:
                res[r["visiteur_qualite"]] = r["n"]
        return res

    H.nb_visites = nb_visites

    # -------------------------------------------------------------- droits et données de référence
    def direction():
        return g.user["role"] in ROLES_DIRECTION

    def mon_personnel_id():
        """Fiche du personnel reliée au compte de l'enseignant connecté (colonne personnel.user_id), sinon None."""
        if g.user["role"] != "enseignant":
            return None
        try:
            r = q("SELECT id FROM personnel WHERE user_id=?", (g.user["id"],), un=True)
        except Exception:  # noqa: BLE001 — colonne absente tant que le module carrière n'est pas installé
            return None
        return r["id"] if r else None

    def peut_saisir(v=None):
        if direction():
            return True
        pid = mon_personnel_id()
        return bool(pid) and (v is None or v["personnel_id"] == pid)

    def personnel():
        try:
            rows = q("SELECT * FROM personnel WHERE actif=1 AND ecole_id=? ORDER BY nom, prenoms", (H.eco(),))
        except Exception:  # noqa: BLE001
            rows = q("SELECT * FROM personnel WHERE actif=1 ORDER BY nom, prenoms")
        cle = lambda p: 0 if re.search(r"nseign|irect|a[iî]tre|nstitut", p["fonction"] or "", re.I) else 1  # noqa: E731
        return sorted(rows, key=cle)

    def classes():
        return H.classes_autorisees()

    def effectifs():
        """{classe_id: {"g": n, "f": m, "t": total}} des élèves inscrits (classes visibles)."""
        res = {}
        for c in classes():
            r = q("""SELECT SUM(sexe='F') f, SUM(sexe<>'F') gg, COUNT(*) t FROM eleves
                     WHERE classe_id=? AND statut='inscrit'""", (c["id"],), un=True)
            res[c["id"]] = {"g": r["gg"] or 0, "f": r["f"] or 0, "t": r["t"] or 0}
        return res

    def filtre_acces():
        """Clause SQL limitant les visites visibles (enseignant : ses classes ou ses propres visites)."""
        if g.user["role"] != "enseignant":
            return "", []
        ids = [c["id"] for c in classes()]
        pid = mon_personnel_id()
        morceaux, params = [], []
        if ids:
            morceaux.append(f"v.classe_id IN ({','.join('?' * len(ids))})")
            params += ids
        if pid:
            morceaux.append("v.personnel_id=?")
            params.append(pid)
        if not morceaux:
            return " AND 0", []
        return " AND (" + " OR ".join(morceaux) + ")", params

    def visite_ou_404(vid):
        acces, params = filtre_acces()
        v = q(f"SELECT v.* FROM visites v WHERE v.id=? AND v.ecole_id=?{acces}", [vid, H.eco()] + params, un=True)
        if not v:
            abort(404)
        return v

    def matieres():
        try:
            return [r["nom"] for r in q("SELECT DISTINCT nom FROM matieres WHERE actif=1 ORDER BY cycle, ordre")]
        except Exception:  # noqa: BLE001
            return []

    def filtres(args):
        """Visites de l'école selon les filtres de la liste."""
        acces, params = filtre_acces()
        sql = "SELECT v.* FROM visites v WHERE v.ecole_id=?" + acces
        params = [H.eco()] + params
        f = {"enseignant": args.get("enseignant", type=int), "qualite": args.get("qualite", ""),
             "visiteur": (args.get("visiteur") or "").strip()[:60], "type": args.get("type", ""),
             "du": args.get("du", ""), "au": args.get("au", ""), "annee": args.get("annee", "")}
        if f["enseignant"]:
            sql += " AND v.personnel_id=?"
            params.append(f["enseignant"])
        if f["qualite"] in QUALITES:
            sql += " AND v.visiteur_qualite=?"
            params.append(f["qualite"])
        if f["visiteur"]:
            sql += " AND v.visiteur_nom LIKE ?"
            params.append(f"%{f['visiteur']}%")
        if f["type"] in TYPES:
            sql += " AND v.type=?"
            params.append(f["type"])
        if lire_date(f["du"]):
            sql += " AND v.date>=?"
            params.append(lire_date(f["du"]).isoformat())
        if lire_date(f["au"]):
            sql += " AND v.date<=?"
            params.append(lire_date(f["au"]).isoformat())
        if re.match(r"^\d{4}-\d{4}$", f["annee"]):
            sql += " AND v.annee=?"
            params.append(f["annee"])
        return q(sql + " ORDER BY v.date DESC, v.heure_debut DESC", params), f

    # -------------------------------------------------------------- liste
    @app.route("/visites")
    @H.connexion_requise("visites")
    def visites_accueil():
        liste, f = filtres(request.args)
        n = compter(liste)
        annees = [r["annee"] for r in q("SELECT DISTINCT annee FROM visites WHERE ecole_id=? ORDER BY annee DESC", (H.eco(),))]
        return render_template("visites_accueil.html", liste=liste, f=f, n=n, pers=personnel(), TYPES=TYPES,
                               QUALITES=QUALITES, annees=annees, saisie=peut_saisir(), direction=direction(),
                               note_txt=note_txt, nom_complet=nom_complet,
                               nb_classe=sum(1 for v in liste if v["type"] == "classe"))

    # -------------------------------------------------------------- saisie / modification
    def lire_formulaire(f, ancienne=None):
        """(valeurs, erreurs, avertissements) à partir du formulaire."""
        err, avert = [], []
        d = lire_date(f.get("date"))
        if not d:
            err.append("Date de la visite invalide.")
        elif d > date.today():
            err.append("La date de la visite ne peut pas être dans le futur.")
        typ = f.get("type") if f.get("type") in TYPES else None
        if not typ:
            err.append("Choisissez le type de visite.")
        qual = f.get("visiteur_qualite") if f.get("visiteur_qualite") in QUALITES else None
        if not qual:
            err.append("Précisez si le visiteur est un CP ou le CCS.")
        v = {k: (f.get(k) or "").strip()[:m] for k, m in TEXTES.items()}
        if not v["visiteur_nom"]:
            err.append("Indiquez le nom du visiteur.")
        pers = {p["id"]: p for p in personnel()}
        pid = f.get("personnel_id", "")
        pid = int(pid) if pid.isdigit() and int(pid) in pers else None
        moi = mon_personnel_id()
        if not direction():
            pid = moi  # un enseignant n'enregistre que ses propres visites
        if pid:
            v["enseignant_nom"] = nom_complet(pers.get(pid)) or v["enseignant_nom"]
        cls = {c["id"]: c for c in classes()}
        cid = f.get("classe_id", "")
        cid = int(cid) if cid.isdigit() else None
        if cid is not None and cid not in cls:
            err.append("Classe non autorisée.")
            cid = None
        if typ == "classe":
            if not (pid or v["enseignant_nom"]):
                err.append("Une visite de classe concerne un enseignant : choisissez-le (ou saisissez son nom).")
            if not cid:
                err.append("Choisissez la classe visitée.")
        hd, hf = lire_heure(f.get("heure_debut")), lire_heure(f.get("heure_fin"))
        if hd is None or hf is None:
            err.append("Heures invalides (format 08:30).")
        elif hd and hf and hf <= hd:
            err.append("L'heure de fin doit être après l'heure de début.")
        eff = {}
        try:
            eff = {k: lire_effectif(f.get(k)) for k in ("eff_g", "eff_f")}
        except ValueError:
            err.append(f"Effectifs présents invalides (nombres entiers de 0 à {EFFECTIF_MAX}).")
        try:
            note = lire_note(f.get("note"))
        except ValueError:
            err.append("La note doit être comprise entre 0 et 20.")
            note = None
        ins = {"g": None, "f": None}
        if cid:
            r = q("SELECT SUM(sexe='F') f, SUM(sexe<>'F') gg FROM eleves WHERE classe_id=? AND statut='inscrit'",
                  (cid,), un=True)
            ins = {"g": r["gg"] or 0, "f": r["f"] or 0}
            if eff.get("eff_g") is None and eff.get("eff_f") is None and ancienne is None:
                eff = {"eff_g": ins["g"], "eff_f": ins["f"]}  # pré-remplissage si non saisi
            if (eff.get("eff_g") or 0) > ins["g"] or (eff.get("eff_f") or 0) > ins["f"]:
                avert.append(f"Attention : l'effectif présent dépasse l'effectif inscrit de la classe "
                             f"({ins['g']} G / {ins['f']} F).")
        total = None
        if eff.get("eff_g") is not None or eff.get("eff_f") is not None:
            total = (eff.get("eff_g") or 0) + (eff.get("eff_f") or 0)
        val = dict(v, type=typ, visiteur_qualite=qual, date=d.isoformat() if d else "", annee=annee_de(d) if d else "",
                   personnel_id=pid, classe_id=cid, classe_nom=cls[cid]["nom"] if cid in cls else None,
                   heure_debut=hd or "", heure_fin=hf or "", eff_g=eff.get("eff_g"), eff_f=eff.get("eff_f"),
                   eff_t=total, ins_g=ins["g"], ins_f=ins["f"], note=note)
        return val, err, avert

    CHAMPS = ("annee", "type", "visiteur_qualite", "visiteur_nom", "date", "personnel_id", "enseignant_nom", "classe_id",
              "classe_nom", "matiere", "unite", "dossier", "sa", "sequence", "heure_debut", "heure_fin", "eff_g", "eff_f",
              "eff_t", "ins_g", "ins_f", "constats", "recommandations", "note", "appreciation", "suites")

    def rendu_form(v, visite=None, code=200):
        return render_template("visite_form.html", v=v, visite=visite, pers=personnel(), cls=classes(),
                               eff_json=json.dumps(effectifs()), TYPES=TYPES, QUALITES=QUALITES, mats=matieres(),
                               saisie=peut_saisir(visite), direction=direction(), moi=mon_personnel_id(),
                               nom_complet=nom_complet, aujourdhui=date.today().isoformat(),
                               ccs_nom=H.identification().get("ccs_nom") or ""), code

    @app.route("/visites/nouvelle", methods=["GET", "POST"])
    @H.connexion_requise("visites")
    def visite_nouvelle():
        if not peut_saisir():
            flash("La saisie des visites est réservée à la direction (ou à l'enseignant concerné, lorsque son compte "
                  "est relié à sa fiche du personnel).", "warning")
            return redirect(url_for("visites_accueil"))
        if request.method == "POST":
            val, err, avert = lire_formulaire(request.form)
            if err:
                for e in err:
                    flash(e, "danger")
                return rendu_form(dict(request.form.items()))
            vid = ex(f"INSERT INTO visites (ecole_id, {', '.join(CHAMPS)}, cree_par, cree_le, maj) "
                     f"VALUES ({', '.join('?' * (len(CHAMPS) + 4))})",
                     [H.eco()] + [val[k] for k in CHAMPS] + [g.user["id"], H.maintenant(), H.maintenant()])
            for a in avert:
                flash(a, "warning")
            H.journal("visite_ajout", f"{val['visiteur_qualite']} {val['date']} {val['enseignant_nom']}")
            flash("Visite enregistrée.", "success")
            return redirect(url_for("visite_modifier", vid=vid))
        v = {"date": date.today().isoformat(), "type": request.args.get("type") or "classe",
             "visiteur_qualite": "CP", "personnel_id": mon_personnel_id() or request.args.get("enseignant", type=int)}
        return rendu_form(v)

    @app.route("/visites/<int:vid>", methods=["GET", "POST"])
    @H.connexion_requise("visites")
    def visite_modifier(vid):
        visite = visite_ou_404(vid)
        if request.method == "POST":
            if not peut_saisir(visite):
                abort(403)
            val, err, avert = lire_formulaire(request.form, visite)
            if err:
                for e in err:
                    flash(e, "danger")
                return rendu_form(dict(request.form.items()), visite)
            ex(f"UPDATE visites SET {', '.join(k + '=?' for k in CHAMPS)}, maj=? WHERE id=?",
               [val[k] for k in CHAMPS] + [H.maintenant(), vid])
            for a in avert:
                flash(a, "warning")
            H.journal("visite_modif", str(vid))
            flash("Visite mise à jour.", "success")
            return redirect(url_for("visite_modifier", vid=vid))
        return rendu_form(dict(visite), visite)

    @app.route("/visites/<int:vid>/supprimer", methods=["POST"])
    @H.connexion_requise("visites")
    def visite_supprimer(vid):
        if not direction():
            abort(403)
        v = visite_ou_404(vid)
        ex("DELETE FROM visites WHERE id=?", (vid,))
        H.journal("visite_suppression", f"{vid} {v['date']}")
        flash("Visite supprimée.", "warning")
        return redirect(url_for("visites_accueil"))

    # -------------------------------------------------------------- fiche PDF (remplie ou vierge)
    def fiche_pdf(v):
        P = H.pdfs
        ide = H.identification()
        vierge = v is None
        v = v or {}
        cl = H.classe_ou_404(v["classe_id"]) if v.get("classe_id") and q(
            "SELECT 1 FROM classes WHERE id=?", (v["classe_id"],), un=True) else None
        blanc = "\n\n"

        def val(k, defaut=""):
            x = v.get(k)
            return blanc if vierge else ("" if x is None else str(x)) or defaut

        eff = ("G : ……   F : ……   Total : ……" if vierge else
               f"G : {v.get('eff_g') if v.get('eff_g') is not None else '—'}   "
               f"F : {v.get('eff_f') if v.get('eff_f') is not None else '—'}   "
               f"Total : {v.get('eff_t') if v.get('eff_t') is not None else '—'}"
               + (f"   (inscrits : {v.get('ins_g') or 0} G / {v.get('ins_f') or 0} F)" if v.get("ins_g") is not None else ""))
        heures = "de ……h…… à ……h……" if vierge else (
            f"de {v.get('heure_debut') or '—'} à {v.get('heure_fin') or '—'}")
        lignes = [
            ["Unité / dossier", val("unite") + (" — " + v["dossier"] if not vierge and v.get("dossier") else "")],
            ["Situation d'apprentissage (SA)", val("sa")],
            ["Séquence", val("sequence")],
            ["Horaire de la séance", heures],
            ["Effectif présent", eff],
            ["Constats", "\n" * 8 if vierge else val("constats", "—")],
            ["Recommandations et conseils", "\n" * 8 if vierge else val("recommandations", "—")],
            ["Note / appréciation", "……… / 20      Appréciation : ……………………" if vierge else
             " — ".join(x for x in (note_txt(v.get("note")), v.get("appreciation") or "") if x) or "—"],
            ["Suites données", "\n" * 4 if vierge else val("suites", "—")],
        ]
        if not vierge and v.get("type") == "ecole" and not (v.get("personnel_id") or v.get("enseignant_nom")):
            lignes = [l for l in lignes if l[0] not in ("Situation d'apprentissage (SA)", "Séquence", "Effectif présent")]
        typ = "VISITE DE CLASSE / VISITE D'ÉCOLE" if vierge else TYPES[v["type"]].upper()
        qual = v.get("visiteur_qualite")
        titre_vis = ("LE VISITEUR (CP / CCS)" if vierge else
                     ("LE CONSEILLER PÉDAGOGIQUE" if qual == "CP" else "LE CHEF DE CIRCONSCRIPTION SCOLAIRE"))
        img_vis = P.image_data_url(H.signature(f"ecole:{H.eco()}:ccs")) if qual == "CCS" else None
        # signature digitale de l'enseignant visité : son compte relié à sa fiche du personnel (enseignant:<uid>),
        # sinon la signature du titulaire de la classe visitée quand c'est bien lui
        img_ens = P.image_data_url(H.signature_agent(v.get("personnel_id"))) if not vierge else None
        if img_ens is None and cl and v.get("enseignant_nom") and cl.get("titulaire_nom") and \
                cl["titulaire_nom"].strip().lower() in v["enseignant_nom"].lower():
            img_ens = P.image_data_url(H.signature_titulaire(cl["id"]))
        titre_dir = ide.get("directeur_titre") or "Directeur"
        titre_dir = f"{'LA' if titre_dir.lower().startswith('directrice') else 'LE'} {titre_dir.upper()}"
        sigs = [(titre_vis, "" if vierge else v.get("visiteur_nom") or "", img_vis, False),
                ("L'ENSEIGNANT(E) VISITÉ(E)", "" if vierge else v.get("enseignant_nom") or "", img_ens, False),
                (titre_dir, ide.get("directeur_nom") or "",
                 None if vierge else P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)]
        date_txt = "……/……/…………" if vierge else P.date_fr(v.get("date"))
        infos = [("Type de visite", "[  ] Visite de classe    [  ] Visite d'école" if vierge else TYPES[v["type"]]),
                 ("Date", date_txt),
                 ("Visiteur", "[  ] CP   [  ] CCS   Nom : ……………………" if vierge else f"{qual} — {v.get('visiteur_nom') or ''}"),
                 ("Enseignant(e) visité(e)", "……………………………" if vierge else v.get("enseignant_nom") or "—"),
                 ("Classe", "……………………" if vierge else v.get("classe_nom") or "—"),
                 ("Matière visitée", "……………………" if vierge else v.get("matiere") or "—"),
                 ("Année scolaire", ide.get("annee") if vierge else v.get("annee")),
                 ("École", ide.get("ecole"))]
        return P.pour_cycle(cl["cycle"] if cl else "primaire")(
            f"FICHE DE {typ}", ["Rubrique", "Renseignements"], lignes,
            sous_titre="Visite du conseiller pédagogique (CP) ou du chef de circonscription scolaire (CCS)",
            infos=infos, infos_haut=[("DDEMP", ide.get("ddemp")), ("CS", ide.get("cs")), ("ÉCOLE", ide.get("ecole"))],
            largeurs=[28, 72], taille=9, signatures=sigs)

    @app.route("/visites/<int:vid>/fiche.pdf")
    @H.connexion_requise("visites")
    def visite_fiche_pdf(vid):
        v = dict(visite_ou_404(vid))
        H.journal("visite_fiche_pdf", str(vid))
        return H.pdf_reponse(fiche_pdf(v), f"visite_{v['date']}_{vid}.pdf")

    @app.route("/visites/fiche-vierge.pdf")
    @H.connexion_requise("visites")
    def visite_fiche_vierge():
        return H.pdf_reponse(fiche_pdf(None), "fiche_visite_vierge.pdf")

    # -------------------------------------------------------------- récapitulatif par enseignant
    def recap(args):
        annee = args.get("annee")
        if annee != "toutes" and not re.match(r"^\d{4}-\d{4}$", annee or ""):
            annee = H.config.ANNEE_ACTIVE
        acces, params = filtre_acces()
        sql = "SELECT v.* FROM visites v WHERE v.ecole_id=?" + acces
        params = [H.eco()] + params
        if annee != "toutes":
            sql += " AND v.annee=?"
            params.append(annee)
        visites = q(sql + " ORDER BY v.date", params)
        groupes = {}
        pers = {p["id"]: p for p in personnel()}
        if direction():  # la direction voit aussi les enseignants jamais visités
            for p in pers.values():
                if re.search(r"nseign|irect|a[iî]tre|nstitut", p["fonction"] or "", re.I):
                    groupes[("p", p["id"])] = {"nom": nom_complet(p), "fonction": p["fonction"], "visites": []}
        for v in visites:
            if not (v["personnel_id"] or v["enseignant_nom"]):
                continue  # visite d'école sans enseignant désigné : comptée à part
            cle = ("p", v["personnel_id"]) if v["personnel_id"] else ("n", (v["enseignant_nom"] or "").upper())
            if cle not in groupes:
                p = pers.get(v["personnel_id"])
                groupes[cle] = {"nom": nom_complet(p) if p else v["enseignant_nom"],
                                "fonction": p["fonction"] if p else "", "visites": []}
            groupes[cle]["visites"].append(v)
        lignes = []
        for cle, gr in groupes.items():
            vs = gr["visites"]
            n = compter(vs)
            notes = [v["note"] for v in vs if v["note"] is not None]
            lignes.append({"pid": cle[1] if cle[0] == "p" else None, "nom": gr["nom"], "fonction": gr["fonction"] or "",
                           "classes": ", ".join(sorted({v["classe_nom"] for v in vs if v["classe_nom"]})),
                           "cp": n["CP"], "ccs": n["CCS"], "total": n["CP"] + n["CCS"],
                           "cp_classe": sum(1 for v in vs if v["visiteur_qualite"] == "CP" and v["type"] == "classe"),
                           "ccs_classe": sum(1 for v in vs if v["visiteur_qualite"] == "CCS" and v["type"] == "classe"),
                           "derniere": max((v["date"] for v in vs), default=""),
                           "moyenne": round(sum(notes) / len(notes), 2) if notes else None})
        lignes.sort(key=lambda x: (-x["total"], x["nom"]))
        ecole = [v for v in visites if not (v["personnel_id"] or v["enseignant_nom"])]
        tot = compter(visites)
        return {"annee": annee, "lignes": lignes, "tot": tot, "total": len(visites), "ecole": compter(ecole),
                "jamais": sum(1 for l in lignes if not l["total"])}

    def annees_dispo():
        a = [r["annee"] for r in q("SELECT DISTINCT annee FROM visites WHERE ecole_id=? ORDER BY annee DESC", (H.eco(),))]
        if H.config.ANNEE_ACTIVE not in a:
            a.insert(0, H.config.ANNEE_ACTIVE)
        return a

    @app.route("/visites/recapitulatif")
    @H.connexion_requise("visites")
    def visites_recap():
        r = recap(request.args)
        return render_template("visites_recap.html", r=r, annees=annees_dispo(), note_txt=note_txt)

    @app.route("/visites/recapitulatif.pdf")
    @H.connexion_requise("visites")
    def visites_recap_pdf():
        r = recap(request.args)
        P = H.pdfs
        v = H.identification()
        cols = [["N°", "Enseignant(e)", "Fonction", "Classe(s)", "Nombre de visites", None, None, "Dernière visite",
                 "Note moy."], ["^", "^", "^", "^", "CP", "CCS", "Total", "^", "^"]]
        lignes = [[i, l["nom"], l["fonction"], l["classes"], l["cp"], l["ccs"], l["total"],
                   P.date_fr(l["derniere"]) if l["derniere"] else "—", note_txt(l["moyenne"]) or "—"]
                  for i, l in enumerate(r["lignes"], 1)]
        if not lignes:
            lignes = [["", "Aucune visite enregistrée pour cette période.", "", "", "", "", "", "", ""]]
        tot = ["", "TOTAL", "", "", sum(l["cp"] for l in r["lignes"]), sum(l["ccs"] for l in r["lignes"]),
               sum(l["total"] for l in r["lignes"]), "", ""]
        periode = "toutes les années" if r["annee"] == "toutes" else f"année scolaire {r['annee']}"
        titre_dir = v.get("directeur_titre") or "Directeur"
        titre_dir = f"{'LA' if titre_dir.lower().startswith('directrice') else 'LE'} {titre_dir.upper()}"
        pdf = P.document_tableau(
            "RÉCAPITULATIF DES VISITES DE CLASSE PAR ENSEIGNANT", cols, lignes, total=tot,
            sous_titre=f"Visites des conseillers pédagogiques (CP) et du CCS — {periode}",
            infos=[("École", v.get("ecole")), ("Période", periode), ("Visites (total)", r["total"]),
                   ("dont CP / CCS", f"{r['tot']['CP']} / {r['tot']['CCS']}"),
                   ("Visites d'école sans enseignant", r["ecole"]["CP"] + r["ecole"]["CCS"]),
                   ("Enseignants jamais visités", r["jamais"])],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[6, 40, 24, 22, 10, 10, 10, 18, 13], taille=8,
            signatures=[(titre_dir, v.get("directeur_nom") or "",
                         P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)],
            notes_bas=["Nombre de visites = visites de classe et visites d'école rattachées à l'enseignant."])
        H.journal("visites_recap_pdf", r["annee"])
        return H.pdf_reponse(pdf, f"recapitulatif_visites_{r['annee']}.pdf")

    @app.route("/visites/recapitulatif.xlsx")
    @H.connexion_requise("visites")
    def visites_recap_xlsx():
        r = recap(request.args)
        v = H.identification()
        entetes = ["N°", "Enseignant(e)", "Fonction", "Classe(s)", "Visites CP", "Visites CCS", "Total",
                   "dont visites de classe CP", "dont visites de classe CCS", "Dernière visite", "Note moyenne /20"]
        lignes = [[i, l["nom"], l["fonction"], l["classes"], l["cp"], l["ccs"], l["total"], l["cp_classe"],
                   l["ccs_classe"], H.pdfs.date_fr(l["derniere"]) if l["derniere"] else "", l["moyenne"]]
                  for i, l in enumerate(r["lignes"], 1)]
        lignes.append(["", "TOTAL", "", "", sum(l["cp"] for l in r["lignes"]), sum(l["ccs"] for l in r["lignes"]),
                       sum(l["total"] for l in r["lignes"]), "", "", "", ""])
        periode = "toutes les années" if r["annee"] == "toutes" else f"Année scolaire {r['annee']}"
        H.journal("visites_recap_xlsx", r["annee"])
        return H.xlsx.reponse_xlsx(f"recapitulatif_visites_{r['annee']}.xlsx", entetes, lignes, titre="Visites",
                                   titre_haut=[f"{v.get('ecole') or ''} — Récapitulatif des visites par enseignant",
                                               f"{periode} — DDEMP {v.get('ddemp') or ''} — CS {v.get('cs') or ''}"])
