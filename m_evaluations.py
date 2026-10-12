# -*- coding: utf-8 -*-
"""Saisie des notes par évaluation (diagnostique, formative, sommative d'étape, certificative).

* /evaluations                          : choix de la classe, liste des évaluations de l'année
* /evaluations/nouvelle, /<id>/modifier : type, numéro, date, matières cochées, seuil de maîtrise
* /evaluations/<id>/saisie              : en-tête institutionnel + grille élèves × matières (calculs en direct),
                                          Sauvegarder / Charger / Réinitialiser, Excel, PDF, signatures digitales
Les notes sont rangées dans la table ``notes`` avec ``periode = evaluations.libelle`` (ex. « Formative 1 »).
Règle du primaire : MAÎTRISE = au moins ``seuil`` matières à 10/20 (2/3 des matières par défaut) ; c'est la seule
condition de réussite, la moyenne ne sert qu'au rang (voir evaluations_core.py).
"""
import io
import json
import re
from datetime import date, datetime

from flask import abort, flash, g, jsonify, redirect, render_template, request, session, url_for

import evaluations_core as EC
from calcul import APPRECIATIONS, NIVEAUX_SANS_COEF, appreciation_note, cycle_du_niveau

# Champs d'en-tête enregistrés avec l'évaluation (M.identification + titre de l'évaluation)
CHAMPS_ENTETE = ("ddemp", "cs", "ecole", "cours", "annee", "admin_titre", "admin_nom",
                 "directeur_titre", "directeur_nom")
# Champs communs à toute l'école, recopiés d'une évaluation à l'autre (pas le cours)
CHAMPS_ECOLE = ("ddemp", "cs", "ecole", "annee", "admin_titre", "admin_nom", "directeur_titre", "directeur_nom")


def _num(v):
    """12.0 -> « 12 », 12.5 -> « 12,5 » (affichage à la française)."""
    if v is None:
        return ""
    return (f"{v:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


def _moy(v):
    return "—" if v is None else f"{v:.2f}".replace(".", ",")


def _titre_signataire(titre, defaut):
    """« Directrice » -> « La Directrice » ; « Administrateur » -> « L'Administrateur »."""
    t = (titre or defaut).strip()
    if t.lower().startswith(("le ", "la ", "l'", "l’")):
        return t
    if t[:1].upper() in "AEIOUÉÈ":
        return "L'" + t
    return ("La " if t.endswith(("trice", "rice", "e")) and not t.endswith("eur") else "Le ") + t


def _dessiner_signature(c, pdfs, x, y, titre, nom="", image=None, cachet=False, largeur=44):
    """Bloc de signature centré en x (y = ligne du titre) : titre, cachet de l'école (légèrement à gauche),
    signature digitale par-dessus, nom EN DESSOUS du cachet (jamais recouvert). Hauteur totale : 33 mm."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    c.saveState()
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(x, y, titre or "")
    if cachet:
        pdfs.cachet_ecole(c, x - 9 * mm, y - 15.5 * mm, 11 * mm)
    if image is not None:
        l = largeur * mm
        c.drawImage(image, x - l / 2, y - 23 * mm, l, 18 * mm, preserveAspectRatio=True, mask="auto")
    if nom:
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x, y - 30.5 * mm, nom)
    c.restoreState()


def _flowable_signatures(pdfs, signatures, largeur):
    """Flowable ReportLab : signatures côte à côte [(titre, nom, image, cachet)] (sans chevauchement du nom)."""
    from reportlab.lib.units import mm
    from reportlab.platypus.flowables import Flowable

    class Signatures(Flowable):
        def wrap(self, *_):
            return largeur, 36 * mm

        def draw(self):
            n = max(1, len(signatures))
            for i, (titre, nom, image, cachet) in enumerate(signatures):
                _dessiner_signature(self.canv, pdfs, largeur * (i + 0.5) / n, 36 * mm - 8, titre, nom, image, cachet)

    return Signatures()


def enregistrer(app, H):
    q, ex = H.q, H.ex

    # ------------------------------------------------------------------ outils
    def cle_entete(ev_id):
        return f"e{H.eco()}:evaluations:ev{ev_id}"

    def cle_entete_ecole():
        return f"e{H.eco()}:evaluations:entete"

    def charger(ev_id):
        """Évaluation + classe, avec contrôle d'accès (école courante, classes de l'enseignant)."""
        ev = EC.evaluation(ev_id)
        if not ev:
            abort(404)
        cl = H.classe_ou_404(ev["classe_id"])
        H.verifier_classe(cl["id"])
        return ev, cl

    def entete(ev, cl):
        """En-tête institutionnel : valeurs par défaut de l'école, puis dernier en-tête de l'école, puis celui
        enregistré pour cette évaluation."""
        d = H.identification(cl)
        commun = H.doc_lire(cle_entete_ecole(), {}) or {}
        d.update({k: v for k, v in commun.items() if k in CHAMPS_ECOLE and v})
        propre = H.doc_lire(cle_entete(ev["id"]), {}) or {}
        d.update({k: v for k, v in propre.items() if k in CHAMPS_ENTETE})
        d["evaluation"] = ev["titre"]
        return d

    def ecrire_entete(ev, form):
        d = {k: (form.get(k) or "").strip()[:150] for k in CHAMPS_ENTETE}
        H.doc_ecrire(cle_entete(ev["id"]), d)
        H.doc_ecrire(cle_entete_ecole(), {k: d[k] for k in CHAMPS_ECOLE})
        return d

    def modifiables(cl, matieres):
        """Ids des matières que l'utilisateur peut saisir (professeur du secondaire : ses matières)."""
        aut = H.matieres_autorisees(cl["id"])
        return {m["id"] for m in matieres if aut is None or m["id"] in aut}

    def lire_saisie(brut, maternelle):
        """Valeur saisie -> (valeur, dispense, appreciation). '' = pas de note. ValueError si invalide."""
        s = ("" if brut is None else str(brut)).strip()
        if isinstance(brut, float) and brut.is_integer():
            s = str(int(brut))
        if s == "":
            return None, False, None
        if s.upper() in ("D", "DISP", "DISPENSE", "DISPENSÉ"):
            return None, True, None
        if maternelle:
            if s.upper() in APPRECIATIONS:
                return None, False, s.upper()
            raise ValueError
        v = float(s.replace(",", ".").replace(" ", ""))
        if not 0 <= v <= 20:
            raise ValueError
        return round(v, 2), False, None

    def enregistrer_notes(ev, cl, saisies, effacer_vides=True):
        """saisies : {(eleve_id, matiere_id): texte}. Écrit dans la table notes (periode = libellé).
        Retourne (nb_modifications, [erreurs], {(eleve_id, matiere_id): texte refusé})."""
        matieres = EC.matieres_de(ev, cl)
        permis = modifiables(cl, matieres)
        eleves = {e["id"]: e for e in EC.eleves_classe(cl["id"])}
        noms_mat = {m["id"]: m["nom"] for m in matieres}
        maternelle = cl["cycle"] == "maternelle"
        anciens = {}
        if eleves:
            marque = ",".join("?" * len(eleves))
            for n in q(f"SELECT * FROM notes WHERE periode=? AND annee=? AND eleve_id IN ({marque})",
                       [ev["libelle"], ev["annee"]] + list(eleves)):
                anciens[(n["eleve_id"], n["matiere_id"])] = n
        db = H.get_db()
        modifs, erreurs, rejets = 0, [], {}
        for (eid, mid), brut in saisies.items():
            if eid not in eleves or mid not in permis:
                continue
            e = eleves[eid]
            try:
                val, disp, app_ = lire_saisie(brut, maternelle)
            except (ValueError, TypeError):
                attendu = "A, ECA, NA ou D" if maternelle else "une note de 0 à 20, ou D"
                erreurs.append(f"{e['nom']} {e['prenoms']} – {noms_mat[mid]} : « {brut} » n'est pas valide ({attendu}).")
                rejets[(eid, mid)] = str(brut)[:10]
                continue
            ancien = anciens.get((eid, mid))
            if val is None and not disp and app_ is None:
                if ancien and effacer_vides:
                    db.execute("DELETE FROM notes WHERE id=?", (ancien["id"],))
                    modifs += 1
                continue
            if ancien and ancien["valeur"] == val and bool(ancien["dispense"]) == disp \
                    and (ancien["appreciation"] or None) == app_:
                continue
            db.execute("""INSERT INTO notes (eleve_id, matiere_id, periode, annee, valeur, dispense, appreciation,
                                             saisi_par, modifie_le) VALUES (?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(eleve_id, matiere_id, periode, annee)
                          DO UPDATE SET valeur=excluded.valeur, dispense=excluded.dispense,
                                        appreciation=excluded.appreciation, saisi_par=excluded.saisi_par,
                                        modifie_le=excluded.modifie_le""",
                       (eid, mid, ev["libelle"], ev["annee"], val, int(disp), app_, g.user["id"], H.maintenant()))
            modifs += 1
        db.commit()
        return modifs, erreurs, rejets

    def valeur_cellule(l, m, maternelle):
        """Texte d'une cellule pour la grille / l'Excel : note, « D » ou appréciation."""
        if m["id"] in l["dispenses"]:
            return "D"
        if maternelle:
            return l["appreciations"].get(m["id"], "")
        return _num(l["notes"].get(m["id"]))

    def total_points(l, matieres, cl):
        coef = cl["cycle"] == "secondaire" and cl["niveau"] not in NIVEAUX_SANS_COEF
        v = [(l["notes"][m["id"]], m["coefficient"] if coef else 1) for m in matieres if l["notes"].get(m["id"]) is not None]
        return round(sum(n * c for n, c in v), 2) if v else None

    def seuil_texte(ev, n):
        if ev.get("seuil"):
            return f"≥ 10/20 dans {EC.seuil_de(ev, n)} matière(s) au moins sur {n}"
        return f"≥ 10/20 dans {EC.seuil_de(ev, n)} matière(s) au moins sur {n} (2/3 automatique)"

    # ------------------------------------------------------------------ accueil
    @app.route("/evaluations")
    @H.connexion_requise("evaluations")
    def eval_accueil():
        classes = H.classes_autorisees()
        cid = request.args.get("classe", type=int)
        if cid is None and len(classes) == 1:
            cid = classes[0]["id"]
        cl, lst = None, []
        if cid:
            H.verifier_classe(cid)
            cl = H.classe_ou_404(cid)
            eleves = EC.eleves_classe(cid)
            for ev in EC.evaluations_classe(cid):
                matieres, lignes = EC.resultats(ev, cl, eleves)
                nb_notes = sum(l["nb_notes"] + len(l["dispenses"]) for l in lignes)
                composes = sum(1 for l in lignes if l["compose"])
                maitrise = sum(1 for l in lignes if l["compose"] and l["maitrise"])
                lst.append({"ev": ev, "nb_matieres": len(matieres), "nb_notes": nb_notes, "composes": composes,
                            "seuil": EC.seuil_de(ev, len(matieres)), "seuil_auto": not ev.get("seuil"),
                            "taux": round(100 * maitrise / composes, 1) if composes else None,
                            "maitrise": maitrise, "effectif": len(lignes)})
        return render_template("eval_accueil.html", classes=classes, cid=cid, cl=cl, lst=lst)

    # ------------------------------------------------------------------ création / modification
    @app.route("/evaluations/nouvelle", methods=["GET", "POST"])
    @app.route("/evaluations/<int:ev_id>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("evaluations")
    def eval_form(ev_id=None):
        if ev_id:
            ev, cl = charger(ev_id)
        else:
            ev = None
            cid = request.values.get("classe", type=int)
            if not cid:
                flash("Choisissez d'abord une classe.", "warning")
                return redirect(url_for("eval_accueil"))
            H.verifier_classe(cid)
            cl = H.classe_ou_404(cid)
        toutes = EC.matieres_cycle(cl["cycle"])
        existantes = EC.evaluations_classe(cl["id"])
        if request.method == "POST":
            f = request.form
            type_ = f.get("type", "")
            erreurs = []
            if type_ not in EC.TYPES:
                erreurs.append("Type d'évaluation inconnu.")
            try:
                numero = int(f.get("numero", ""))
                if not 1 <= numero <= 50:
                    raise ValueError
            except ValueError:
                numero = 1
                erreurs.append("Le numéro doit être un nombre entier entre 1 et 50.")
            d = (f.get("date") or "").strip()
            if d:
                try:
                    d = datetime.strptime(d, "%Y-%m-%d").date().isoformat()
                except ValueError:
                    erreurs.append("Date invalide.")
            ids_valides = {m["id"] for m in toutes}
            mats = [int(x) for x in f.getlist("matieres") if x.isdigit() and int(x) in ids_valides]
            if not mats:
                erreurs.append("Cochez au moins une matière évaluée.")
            seuil = (f.get("seuil") or "").strip()
            if seuil:
                if not seuil.isdigit() or not 1 <= int(seuil) <= max(1, len(mats)):
                    erreurs.append(f"Le seuil doit être un nombre de matières entre 1 et {max(1, len(mats))} "
                                   "(laissez vide pour 2/3 automatique).")
                seuil = int(seuil) if seuil.isdigit() else None
            else:
                seuil = None
            if cl["cycle"] == "maternelle":
                seuil = None
            lib = EC.libelle(type_, numero) if type_ in EC.TYPES else ""
            if lib and any(x["libelle"] == lib and x["id"] != ev_id for x in existantes):
                erreurs.append(f"L'évaluation « {EC.TYPES[type_]} N° {numero} » existe déjà pour {cl['nom']} "
                               f"en {H.config.ANNEE_ACTIVE}. Choisissez un autre numéro.")
            if erreurs:
                for m in erreurs:
                    flash(m, "danger")
                val = {"type": type_, "numero": numero, "date": d, "seuil": seuil, "matieres_ids": mats}
                return render_template("eval_form.html", ev=ev, val=val, cl=cl, toutes=toutes,
                                       TYPES=EC.TYPES), 400
            mjson = json.dumps(mats)
            if ev:
                db = H.get_db()
                if lib != ev["libelle"]:
                    # le libellé est la clé des notes : on renomme les notes de cette classe
                    db.execute("""UPDATE notes SET periode=? WHERE periode=? AND annee=?
                                  AND eleve_id IN (SELECT id FROM eleves WHERE classe_id=?)""",
                               (lib, ev["libelle"], ev["annee"], cl["id"]))
                db.execute("UPDATE evaluations SET type=?, numero=?, libelle=?, date=?, matieres=?, seuil=? WHERE id=?",
                           (type_, numero, lib, d or None, mjson, seuil, ev["id"]))
                db.commit()
                H.journal("evaluation_modifiee", f"{cl['nom']} {lib}")
                flash(f"Évaluation « {lib} » modifiée.", "success")
                return redirect(url_for("eval_saisie", ev_id=ev["id"]))
            nid = ex("""INSERT INTO evaluations (classe_id, annee, type, numero, libelle, date, matieres, seuil, cree_le)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                     (cl["id"], H.config.ANNEE_ACTIVE, type_, numero, lib, d or None, mjson, seuil, H.maintenant()))
            H.journal("evaluation_creee", f"{cl['nom']} {lib}")
            flash(f"Évaluation « {lib} » créée : vous pouvez saisir les notes.", "success")
            return redirect(url_for("eval_saisie", ev_id=nid))
        if ev:
            val = dict(ev)
        else:
            # proposition : type formative, numéro suivant, toutes les matières cochées
            nums = [x["numero"] for x in existantes if x["type"] == "formative"]
            val = {"type": "formative", "numero": (max(nums) + 1) if nums else 1, "date": date.today().isoformat(),
                   "seuil": None, "matieres_ids": [m["id"] for m in toutes]}
            if request.args.get("type") in EC.TYPES:
                val["type"] = request.args["type"]
        return render_template("eval_form.html", ev=ev, val=val, cl=cl, toutes=toutes, TYPES=EC.TYPES)

    @app.route("/evaluations/<int:ev_id>/supprimer", methods=["POST"])
    @H.connexion_requise("evaluations")
    def eval_supprimer(ev_id):
        ev, cl = charger(ev_id)
        if H.matieres_autorisees(cl["id"]) is not None:
            abort(403)  # un professeur limité à ses matières ne supprime pas les notes des collègues
        db = H.get_db()
        n = db.execute("""DELETE FROM notes WHERE periode=? AND annee=?
                          AND eleve_id IN (SELECT id FROM eleves WHERE classe_id=?)""",
                       (ev["libelle"], ev["annee"], cl["id"])).rowcount
        db.execute("DELETE FROM evaluations WHERE id=?", (ev_id,))
        db.execute("DELETE FROM documents_modules WHERE cle=?", (cle_entete(ev_id),))
        db.commit()
        H.journal("evaluation_supprimee", f"{cl['nom']} {ev['libelle']} ({n} note(s))")
        flash(f"Évaluation « {ev['libelle']} » supprimée avec ses {n} note(s).", "success")
        return redirect(url_for("eval_accueil", classe=cl["id"]))

    # ------------------------------------------------------------------ saisie
    def donnees_grille(ev, cl):
        matieres, lignes = EC.resultats(ev, cl)
        maternelle = cl["cycle"] == "maternelle"
        return matieres, lignes, {str(l["eleve"]["id"]): {str(m["id"]): valeur_cellule(l, m, maternelle)
                                                          for m in matieres} for l in lignes}

    @app.route("/evaluations/<int:ev_id>/saisie", methods=["GET", "POST"])
    @H.connexion_requise("evaluations")
    def eval_saisie(ev_id):
        ev, cl = charger(ev_id)
        if request.method == "POST":
            saisies = {}
            brut_json = request.form.get("notes_json")
            if brut_json:  # la page envoie la grille en un seul champ JSON (grandes classes)
                try:
                    for eid, cols in (json.loads(brut_json) or {}).items():
                        for mid, v in cols.items():
                            saisies[(int(eid), int(mid))] = v
                except (ValueError, TypeError, AttributeError):
                    flash("Données de la grille illisibles : rechargez la page.", "danger")
                    return redirect(url_for("eval_saisie", ev_id=ev_id))
            for k, v in request.form.items():  # sans JavaScript : un champ par case
                m = re.match(r"^n_(\d+)_(\d+)$", k)
                if m:
                    saisies[(int(m.group(1)), int(m.group(2)))] = v
            ecrire_entete(ev, request.form)
            modifs, erreurs, rejets = enregistrer_notes(ev, cl, saisies)
            # Les valeurs refusées sont gardées (session) pour être réaffichées en rouge : rien n'est perdu.
            if rejets:
                session[f"ev_rejets_{ev_id}"] = [[eid, mid, v] for (eid, mid), v in list(rejets.items())[:300]]
            H.journal("evaluation_notes", f"{cl['nom']} {ev['libelle']} : {modifs} modification(s)")
            if erreurs:
                for m in erreurs[:12]:
                    flash(m, "danger")
                if len(erreurs) > 12:
                    flash(f"… et {len(erreurs) - 12} autre(s) erreur(s).", "danger")
                flash(f"{modifs} note(s) enregistrée(s) ; {len(erreurs)} valeur(s) refusée(s) : elles sont réaffichées "
                      "en rouge dans la grille, corrigez-les puis cliquez de nouveau sur « Sauvegarder ».", "warning")
            else:
                flash(f"Notes et en-tête sauvegardés ({modifs} modification(s)).", "success")
            return redirect(url_for("eval_saisie", ev_id=ev_id))
        matieres, lignes, valeurs = donnees_grille(ev, cl)
        permis = modifiables(cl, matieres)
        rejets = 0
        for eid, mid, v in session.pop(f"ev_rejets_{ev_id}", None) or []:
            if str(eid) in valeurs and str(mid) in valeurs[str(eid)]:
                valeurs[str(eid)][str(mid)] = v
                rejets += 1
        coef = cl["cycle"] == "secondaire" and cl["niveau"] not in NIVEAUX_SANS_COEF
        config_js = {
            "cycle": cl["cycle"], "seuil": ev.get("seuil"), "coef": coef,
            "matieres": [{"id": m["id"], "nom": m["nom"], "code": m["code"],
                          "coef": m["coefficient"] if coef else 1} for m in matieres],
            "eleves": [{"id": l["eleve"]["id"], "nom": f"{l['eleve']['nom']} {l['eleve']['prenoms']}",
                        "sexe": l["eleve"]["sexe"]} for l in lignes],
            "url_donnees": url_for("eval_donnees", ev_id=ev_id), "rejets": rejets,
        }
        return render_template("eval_saisie.html", ev=ev, cl=cl, matieres=matieres, lignes=lignes, valeurs=valeurs,
                               permis=permis, v=entete(ev, cl), evs=EC.evaluations_classe(cl["id"]),
                               config_js=config_js, APPRECIATIONS=APPRECIATIONS,
                               seuil_txt=seuil_texte(ev, len(matieres)),
                               restreint=H.matieres_autorisees(cl["id"]) is not None,
                               publie=bool(H.q("SELECT 1 FROM publications WHERE classe_id=? AND periode=? AND annee=?",
                                               (cl["id"], ev["libelle"], ev["annee"]), un=True)))

    @app.route("/evaluations/<int:ev_id>/donnees.json")
    @H.connexion_requise("evaluations")
    def eval_donnees(ev_id):
        """« Charger » : notes et en-tête tels qu'enregistrés en base."""
        ev, cl = charger(ev_id)
        _, lignes, valeurs = donnees_grille(ev, cl)
        maj = q("""SELECT MAX(n.modifie_le) m FROM notes n JOIN eleves e ON e.id=n.eleve_id
                   WHERE n.periode=? AND n.annee=? AND e.classe_id=?""", (ev["libelle"], ev["annee"], cl["id"]), un=True)
        return jsonify(notes=valeurs, entete={k: v for k, v in entete(ev, cl).items() if k in CHAMPS_ENTETE},
                       maj=maj["m"] if maj else None)

    @app.route("/evaluations/<int:ev_id>/effacer", methods=["POST"])
    @H.connexion_requise("evaluations")
    def eval_effacer(ev_id):
        """Efface en base les notes de l'évaluation (seulement les matières que l'utilisateur peut saisir)."""
        ev, cl = charger(ev_id)
        matieres = EC.matieres_de(ev, cl)
        permis = sorted(modifiables(cl, matieres))
        n = 0
        if permis:
            marque = ",".join("?" * len(permis))
            db = H.get_db()
            n = db.execute(f"""DELETE FROM notes WHERE periode=? AND annee=? AND matiere_id IN ({marque})
                               AND eleve_id IN (SELECT id FROM eleves WHERE classe_id=?)""",
                           [ev["libelle"], ev["annee"]] + permis + [cl["id"]]).rowcount
            db.commit()
        H.journal("evaluation_notes_effacees", f"{cl['nom']} {ev['libelle']} : {n} note(s)")
        flash(f"{n} note(s) effacée(s) pour « {ev['titre']} ».", "success")
        return redirect(url_for("eval_saisie", ev_id=ev_id))

    # ------------------------------------------------------------------ Excel
    def titre_haut(ev, cl, v):
        return [f"{ev['titre']} — {cl['nom']} ({cl['niveau']})",
                f"DDEMP : {v.get('ddemp') or '—'}    CS : {v.get('cs') or '—'}    École : {v.get('ecole') or '—'}",
                f"Année scolaire : {v.get('annee') or ev['annee']}    Date : {H.pdfs.date_fr(ev['date']) if ev.get('date') else '—'}"
                + ("" if cl["cycle"] == "maternelle" else f"    Seuil de maîtrise : {seuil_texte(ev, len(EC.matieres_de(ev, cl)))}"),
                "Saisie : note de 0 à 20 (virgule acceptée), D = dispensé, case vide = pas de note"
                if cl["cycle"] != "maternelle" else "Saisie : A = acquis, ECA = en cours d'acquisition, NA = non acquis, D = dispensé"]

    def entetes_excel(matieres):
        return ["N°", "Matricule", "Nom", "Prénoms", "Sexe"] + [m["nom"] for m in matieres]

    def nom_fichier(ev, cl, suffixe, ext):
        base = re.sub(r"[^A-Za-z0-9]+", "_", H.xlsx.normaliser(f"{cl['nom']} {ev['libelle']}")).strip("_")
        return f"{base}_{suffixe}.{ext}"

    @app.route("/evaluations/<int:ev_id>/modele.xlsx")
    @H.connexion_requise("evaluations")
    def eval_modele_excel(ev_id):
        ev, cl = charger(ev_id)
        matieres = EC.matieres_de(ev, cl)
        lignes = [[i, e["matricule"], e["nom"], e["prenoms"], e["sexe"]] + [""] * len(matieres)
                  for i, e in enumerate(EC.eleves_classe(cl["id"]), 1)]
        try:
            return H.xlsx.reponse_xlsx(nom_fichier(ev, cl, "modele", "xlsx"), entetes_excel(matieres), lignes,
                                       titre=ev["libelle"], titre_haut=titre_haut(ev, cl, entete(ev, cl)))
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("eval_saisie", ev_id=ev_id))

    @app.route("/evaluations/<int:ev_id>/export.xlsx")
    @H.connexion_requise("evaluations")
    def eval_export_excel(ev_id):
        ev, cl = charger(ev_id)
        matieres, lignes = EC.resultats(ev, cl)
        maternelle = cl["cycle"] == "maternelle"
        ent = entetes_excel(matieres) + (["Bilan"] if maternelle else ["Total", "Moyenne", "Matières ≥ 10", "Décision", "Rang"])
        rows = []
        for i, l in enumerate(lignes, 1):
            e = l["eleve"]
            r = [i, e["matricule"], e["nom"], e["prenoms"], e["sexe"]]
            for m in matieres:
                if m["id"] in l["dispenses"]:
                    r.append("D")
                elif maternelle:
                    r.append(l["appreciations"].get(m["id"], ""))
                else:
                    r.append(l["notes"].get(m["id"]))
            if maternelle:
                r.append(l["decision"])
            else:
                r += [total_points(l, matieres, cl), l["moyenne"], l["reussies"] if l["compose"] else None,
                      l["decision"], l["rang_texte"]]
            rows.append(r)
        try:
            return H.xlsx.reponse_xlsx(nom_fichier(ev, cl, "notes", "xlsx"), ent, rows, titre=ev["libelle"],
                                       titre_haut=titre_haut(ev, cl, entete(ev, cl)))
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("eval_saisie", ev_id=ev_id))

    @app.route("/evaluations/<int:ev_id>/import", methods=["POST"])
    @H.connexion_requise("evaluations")
    def eval_import_excel(ev_id):
        ev, cl = charger(ev_id)
        f = request.files.get("fichier")
        if not f or not f.filename:
            flash("Choisissez un fichier Excel (.xlsx) ou CSV à importer.", "warning")
            return redirect(url_for("eval_saisie", ev_id=ev_id))
        if not f.filename.lower().endswith((".xlsx", ".xlsm", ".csv", ".txt")):
            flash("Format non reconnu : utilisez un fichier .xlsx (ou .csv).", "danger")
            return redirect(url_for("eval_saisie", ev_id=ev_id))
        X = H.xlsx
        try:
            entetes, lignes = X.lire_tableau(f, ("matricule", "prenoms", "prenom"))
        except X.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("eval_saisie", ev_id=ev_id))
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("eval_saisie", ev_id=ev_id))
        matieres = EC.matieres_de(ev, cl)
        permis = modifiables(cl, matieres)
        i_mat, i_nom, i_pre = X.colonne(entetes, "matricule"), X.colonne(entetes, "nom"), X.colonne(entetes, "prenoms", "prenom")
        if i_mat is None and (i_nom is None or i_pre is None):
            flash("Colonnes « Matricule » ou « Nom » + « Prénoms » introuvables : partez du « Modèle Excel ».", "danger")
            return redirect(url_for("eval_saisie", ev_id=ev_id))
        # colonnes des matières : par nom complet ou par code
        cols = {}
        for j, h in enumerate(entetes):
            hn = X.normaliser(h)
            if not hn or j in (i_mat, i_nom, i_pre):
                continue
            for m in matieres:
                if hn in (X.normaliser(m["nom"]), X.normaliser(m["code"])) or hn.endswith(" " + X.normaliser(m["code"])):
                    cols[j] = m
                    break
        if not cols:
            flash("Aucune colonne de matière reconnue (les intitulés doivent être le nom ou le code des matières "
                  "cochées de l'évaluation).", "danger")
            return redirect(url_for("eval_saisie", ev_id=ev_id))
        eleves = EC.eleves_classe(cl["id"])
        par_mat = {(e["matricule"] or "").strip().upper(): e for e in eleves if e["matricule"]}
        par_nom = {(X.normaliser(e["nom"]), X.normaliser(e["prenoms"])): e for e in eleves}
        saisies, erreurs, ignorees = {}, [], 0
        maternelle = cl["cycle"] == "maternelle"
        for num, ligne in enumerate(lignes, 1):
            mat = X.valeur(ligne, i_mat).upper()
            e = par_mat.get(mat) if mat else None
            if e is None and i_nom is not None:
                e = par_nom.get((X.normaliser(X.valeur(ligne, i_nom)), X.normaliser(X.valeur(ligne, i_pre))))
            qui = " ".join(x for x in (X.valeur(ligne, i_nom), X.valeur(ligne, i_pre)) if x) or mat or "?"
            if e is None:
                erreurs.append(f"Ligne {num} ({qui}) : élève introuvable dans {cl['nom']}.")
                continue
            for j, m in cols.items():
                brut = ligne[j] if j < len(ligne) else None
                if brut is None or str(brut).strip() == "":
                    continue
                if m["id"] not in permis:
                    ignorees += 1
                    continue
                try:
                    lire_saisie(brut, maternelle)
                except (ValueError, TypeError):
                    erreurs.append(f"Ligne {num} ({qui}) – {m['nom']} : « {brut} » n'est pas "
                                   + ("une appréciation valide (A, ECA, NA, D)." if maternelle else "une note valide (0 à 20, ou D)."))
                    continue
                saisies[(e["id"], m["id"])] = brut
        modifs, err2, _ = enregistrer_notes(ev, cl, saisies, effacer_vides=False)
        erreurs += err2
        importees = len(saisies) - len(err2)
        H.journal("evaluation_import", f"{cl['nom']} {ev['libelle']} : {importees} note(s), {len(erreurs)} erreur(s)")
        for m in erreurs[:15]:
            flash(m, "danger")
        if len(erreurs) > 15:
            flash(f"… et {len(erreurs) - 15} autre(s) erreur(s).", "danger")
        msg = f"Import terminé : {importees} note(s) importée(s), {len(erreurs)} erreur(s)."
        if ignorees:
            msg += f" {ignorees} note(s) ignorée(s) (matières qui ne vous sont pas affectées)."
        flash(msg, "warning" if erreurs else "success")
        return redirect(url_for("eval_saisie", ev_id=ev_id))

    # ------------------------------------------------------------------ PDF
    def signatures_ecole(v, avec_cachet_admin=False):
        pdfs = H.pdfs
        eid = H.eco()
        s_admin = pdfs.image_data_url(H.signature(f"ecole:{eid}:admin"))
        s_dir = pdfs.image_data_url(H.signature(f"ecole:{eid}:directeur")) or pdfs.signature_directeur()
        return [(_titre_signataire(v.get("admin_titre"), "Administrateur"), v.get("admin_nom") or "", s_admin, avec_cachet_admin),
                (_titre_signataire(v.get("directeur_titre"), "Directeur"), v.get("directeur_nom") or "", s_dir, True)]

    def infos_haut(v, cl):
        """En-tête gauche des PDF : DDEMP / CS / ÉCOLE (maternelle, primaire) ; département / établissement (secondaire)."""
        if cl["cycle"] == "secondaire":
            return [("DÉPARTEMENT", v.get("ddemp")), ("ÉTABLISSEMENT", v.get("ecole"))]
        return [("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))]

    @app.route("/evaluations/<int:ev_id>/publier", methods=["POST"])
    @H.connexion_requise("evaluations")
    def eval_publier(ev_id):
        """Rendre les résultats visibles (ou les masquer) dans les espaces élèves et parents."""
        ev, cl = charger(ev_id)
        if H.q("SELECT 1 FROM publications WHERE classe_id=? AND periode=? AND annee=?",
               (cl["id"], ev["libelle"], ev["annee"]), un=True):
            H.ex("DELETE FROM publications WHERE classe_id=? AND periode=? AND annee=?", (cl["id"], ev["libelle"], ev["annee"]))
            H.journal("evaluation_depubliee", f"{cl['nom']} {ev['libelle']}")
            flash("Résultats masqués aux élèves et aux parents.", "info")
        else:
            H.ex("INSERT OR IGNORE INTO publications (classe_id, periode, annee, publie_le, publie_par) VALUES (?,?,?,?,?)",
                 (cl["id"], ev["libelle"], ev["annee"], H.maintenant(), g.user["id"]))
            H.journal("evaluation_publiee", f"{cl['nom']} {ev['libelle']}")
            flash("Résultats publiés : visibles dans les espaces élèves et parents.", "success")
        return redirect(url_for("eval_saisie", ev_id=ev_id))

    @app.route("/evaluations/<int:ev_id>/rapport.pdf")
    @H.connexion_requise("evaluations")
    def eval_rapport_pdf(ev_id):
        ev, cl = charger(ev_id)
        pdfs = H.pdfs
        v = entete(ev, cl)
        matieres, lignes = EC.resultats(ev, cl)
        st = EC.statistiques(matieres, lignes)
        maternelle = cl["cycle"] == "maternelle"
        primaire = cl["cycle"] == "primaire"
        n = len(matieres)
        colonnes = [["N°", "Nom et prénoms", "Sexe", "Notes /20" if not maternelle else "Appréciations"]
                    + [None] * (n - 1) + (["Bilan"] if maternelle else ["Total", "Moy.", "≥ 10", "Décision", "Rang"]),
                    ["^", "^", "^"] + [m["code"] for m in matieres] + (["^"] if maternelle else ["^"] * 5)]
        rows, surl = [], {}
        for i, l in enumerate(lignes, 1):
            e = l["eleve"]
            r = [i, f"{e['nom']} {e['prenoms']}", e["sexe"]] + [valeur_cellule(l, m, maternelle) or "—" for m in matieres]
            if maternelle:
                r.append(l["decision"])
            else:
                r += [_num(total_points(l, matieres, cl)) or "—", _moy(l["moyenne"]),
                      f"{l['reussies']}/{n - len(l['dispenses'])}" if l["compose"] else "—", l["decision"], l["rang_texte"]]
            rows.append(r)
            if l["compose"] and l["maitrise"] is False:
                surl[i - 1] = "#FEF3F2"
        # largeur des colonnes de notes selon la longueur du code (évite « COM.O / R » coupé en deux)
        largeurs = [5, 34, 6] + [max(7, 1.25 * len(m["code"] or "") + 1.5) for m in matieres] \
            + ([22] if maternelle else [8, 8, 7, 18, 11])
        # statistiques résumées
        mot = "maîtrise" if primaire else ("réussite" if not maternelle else "progrès satisfaisants")
        t_stats = [["", "Garçons", "Filles", "Total"],
                   ["Inscrits"] + [st["inscrits"][k] for k in "GFT"],
                   ["Ont composé"] + [st["composes"][k] for k in "GFT"],
                   ["Absents"] + [st["absents"][k] for k in "GFT"],
                   [f"Ont la {mot}" if primaire else "Progrès satisfaisants" if maternelle else "Admis"] + [st["reussis"][k] for k in "GFT"],
                   [f"Taux de {mot} (%)" if not maternelle else "Taux (%)"] + [_num(st["taux_reussite"][k]) for k in "GFT"]]
        if not maternelle:
            t_stats.append(["Moyenne de la classe"] + [_moy(st["moyenne"][k]) for k in "GFT"])
        apres = [pdfs.paragraphe("<b>STATISTIQUES</b>", 9, espace=6)]
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle
        bloc_g = pdfs.mini_tableau(t_stats, [45 * mm, 20 * mm, 20 * mm, 20 * mm])
        sigs = signatures_ecole(v)
        petite = False
        if not maternelle:
            extra = [["Indicateur", "Valeur"],
                     ["Plus forte moyenne", _moy(st["plus_forte_moyenne"])],
                     ["Plus faible moyenne", _moy(st["plus_faible_moyenne"])],
                     ["Matière la mieux réussie", f"{st['forte']['T']['matiere']} ({_moy(st['forte']['T']['moyenne'])})" if st["forte"]["T"] else "—"],
                     ["Matière la moins réussie", f"{st['faible']['T']['matiere']} ({_moy(st['faible']['T']['moyenne'])})" if st["faible"]["T"] else "—"],
                     ["Règle appliquée", seuil_texte(ev, n) if primaire else ("Moyenne pondérée ≥ 10" if cl["niveau"] not in NIVEAUX_SANS_COEF else "Moyenne ≥ 10")]]
            bloc_d = pdfs.mini_tableau(extra, [38 * mm, 67 * mm])
            ordre = EC.ordre_de_merite(lignes)
            t_om = None
            if ordre:
                om = [["Rang", "Nom et prénoms", "Sexe", "Moyenne", "Matières ≥ 10", "Décision"]]
                om += [[l["rang_texte"], f"{l['eleve']['nom']} {l['eleve']['prenoms']}", l["eleve"]["sexe"],
                        _moy(l["moyenne"]), f"{l['reussies']}/{n - len(l['dispenses'])}", l["decision"]] for l in ordre]
                t_om = pdfs.mini_tableau(om, [18 * mm, 60 * mm, 12 * mm, 17 * mm, 22 * mm, 30 * mm])
            if t_om is not None and len(ordre) <= 14:
                petite = len(ordre) <= 8
                # petite classe : statistiques à gauche, ordre de mérite à droite (tient sur la même page)
                gauche = Table([[bloc_g], [Spacer(1, 4)], [bloc_d]], colWidths=[108 * mm])
                gauche.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0)]))
                droite = [t_om]
                if petite:  # les signatures prennent place sous l'ordre de mérite : tout tient sur une page
                    droite += [Spacer(1, 8), _flowable_signatures(pdfs, sigs, 160 * mm)]
                duo = Table([[pdfs.paragraphe("<b>STATISTIQUES</b>", 9, espace=0),
                              pdfs.paragraphe("<b>ORDRE DE MÉRITE</b>", 9, espace=0)], [gauche, droite]],
                            colWidths=[112 * mm, 162 * mm])
                duo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
                apres = [Spacer(1, 6), duo]
            else:
                duo = Table([[bloc_g, bloc_d]], colWidths=[110 * mm, 130 * mm])
                duo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
                apres.append(duo)
                if t_om is not None:  # grande classe : l'ordre de mérite peut s'étendre sur plusieurs pages
                    t_om.repeatRows = 1
                    apres += [Spacer(1, 4), pdfs.paragraphe("<b>ORDRE DE MÉRITE</b>", 9, espace=6), t_om]
        else:
            apres.append(bloc_g)
        notes_bas = ["<b>Matières :</b> " + " ; ".join(f"{m['code']} = {m['nom']}" + (f" (coef. {m['coefficient']:g})"
                     if cl["cycle"] == "secondaire" and cl["niveau"] not in NIVEAUX_SANS_COEF else "") for m in matieres)]
        if primaire:
            notes_bas.append("<b>Règle :</b> l'élève a la MAÎTRISE s'il obtient au moins 10/20 dans le nombre de matières "
                             "exigé (seuil) ; c'est la seule condition de réussite. La moyenne sert uniquement au classement.")
        if maternelle:
            notes_bas.append("A = acquis, ECA = en cours d'acquisition, NA = non acquis, D = dispensé.")
        infos = [("Cours", v.get("cours") or cl["niveau"]), ("Classe", cl["nom"]), ("Année scolaire", v.get("annee") or ev["annee"]),
                 ("Évaluation", ev["titre"]), ("Date", pdfs.date_fr(ev["date"]) if ev.get("date") else "—"),
                 ("Matières évaluées", n)]
        contenu = pdfs.pour_cycle(dict(cl).get("cycle"))(
            f"RÉSULTATS DE L'{ev['titre'].upper()}", colonnes, rows,
            sous_titre=f"{cl['nom']} – Année scolaire {v.get('annee') or ev['annee']}",
            infos=infos, largeurs=largeurs, paysage=True, infos_haut=infos_haut(v, cl), taille=7.5 if n < 12 else 6.5,
            apres=apres + [Spacer(1, 4)] + [pdfs.paragraphe(t, 7.5, espace=1) for t in notes_bas]
            + ([] if petite else [Spacer(1, 6), KeepTogether([_flowable_signatures(pdfs, sigs, 270 * mm)])]),
            signatures=None, surlignes=surl)
        H.journal("evaluation_rapport", f"{cl['nom']} {ev['libelle']}")
        return H.pdf_reponse(contenu, nom_fichier(ev, cl, "rapport", "pdf"))

    # --- bulletin d'évaluation (GCanvas)
    def dessiner_bulletin(c, ev, cl, v, l, matieres, st):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Table, TableStyle
        pdfs = H.pdfs
        W, Hp = A4
        m_ = 14 * mm
        e = l["eleve"]
        maternelle = cl["cycle"] == "maternelle"
        secondaire = cl["cycle"] == "secondaire"
        coef = secondaire and cl["niveau"] not in NIVEAUX_SANS_COEF
        # En-tête officiel (gauche : République, ministère, DDEMP, CS, école ; droite : logo)
        y = Hp - m_
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(m_, y - 8, "RÉPUBLIQUE DU BÉNIN")
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(m_, y - 17, "Fraternité – Justice – Travail")
        c.setFont("Helvetica", 7)
        c.drawString(m_, y - 26, pdfs.MINISTERE.get(cl["cycle"], "").upper()[:95])
        yy = y - 36
        if secondaire:
            lignes_id = [("Département", v.get("ddemp")), ("ÉTABLISSEMENT", v.get("ecole"))]
        else:
            lignes_id = [("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))]
        for lab, val in lignes_id:
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(m_, yy, f"{lab} :")
            c.setFont("Helvetica", 7.5)
            c.drawString(m_ + c.stringWidth(f"{lab} : ", "Helvetica-Bold", 7.5), yy, str(val or "—")[:70])
            yy -= 9
        logo = pdfs._ecole_img("logo.png")
        if logo:
            c.drawImage(logo, W - m_ - 20 * mm, y - 20 * mm, 20 * mm, 20 * mm, preserveAspectRatio=True, mask="auto")
        c.setFont("Helvetica", 8)
        c.drawRightString(W - m_ - (23 * mm if logo else 0), y - 8, f"Année scolaire : {v.get('annee') or ev['annee']}")
        y = min(yy, y - 22 * mm) - 4
        c.setStrokeColor(pdfs.BLEU)
        c.setLineWidth(1.2)
        c.line(m_, y, W - m_, y)
        y -= 20
        c.setFillColor(pdfs.BLEU)
        titre = f"BULLETIN DE L'{ev['titre'].upper()}"
        c.setFont("Helvetica-Bold", 14 if len(titre) < 55 else 12)
        c.drawCentredString(W / 2, y, titre)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        y -= 13
        c.drawCentredString(W / 2, y, f"{v.get('cours') or cl['niveau']} – {cl['nom']}"
                            + (f" – évaluation du {pdfs.date_fr(ev['date'])}" if ev.get("date") else ""))
        y -= 8
        y = pdfs._infos(c, m_, y, W - 2 * m_, [
            ("Nom et prénoms", f"{e['nom']} {e['prenoms']}"), ("Matricule", e["matricule"]),
            ("Sexe", "Masculin" if e["sexe"] == "M" else "Féminin"),
            ("Né(e) le", f"{pdfs.date_fr(e['date_naissance'])} à {e['lieu_naissance'] or '—'}" if e["date_naissance"] else "—"),
            ("Classe", cl["nom"]), ("Effectif", f"{st['inscrits']['T']} inscrit(s), {st['composes']['T']} ont composé")])
        y -= 10
        # Tableau des matières
        st_c = pdfs.ST_CELL
        if maternelle:
            data = [["N°", "Domaine / matière", "Appréciation", "Signification"]]
            cw = [9 * mm, 95 * mm, 26 * mm, W - 2 * m_ - 130 * mm]
        elif coef:
            data = [["N°", "Matière", "Coef.", "Note /20", "Note × coef.", "Appréciation"]]
            cw = [9 * mm, 78 * mm, 15 * mm, 20 * mm, 24 * mm, W - 2 * m_ - 146 * mm]
        else:
            data = [["N°", "Matière", "Note /20", "Appréciation"]]
            cw = [9 * mm, 100 * mm, 25 * mm, W - 2 * m_ - 134 * mm]
        rouges = []
        for i, mt in enumerate(matieres, 1):
            ligne = [str(i), Paragraph(mt["nom"], st_c)]
            disp = mt["id"] in l["dispenses"]
            if maternelle:
                a = l["appreciations"].get(mt["id"])
                ligne += ["D" if disp else (a or "—"), "Dispensé(e)" if disp else APPRECIATIONS.get(a, "Non évalué")]
            else:
                n_ = l["notes"].get(mt["id"])
                note_txt = "Disp." if disp else (_num(n_) if n_ is not None else "—")
                app_txt = "Dispensé(e)" if disp else (appreciation_note(n_) if n_ is not None else "Non évalué")
                if coef:
                    ligne += [f"{mt['coefficient']:g}", note_txt, _num(n_ * mt["coefficient"]) if n_ is not None else "—", app_txt]
                else:
                    ligne += [note_txt, app_txt]
                if n_ is not None and n_ < 10:
                    rouges.append(i)
            data.append(ligne)
        if not maternelle:
            tot = total_points(l, matieres, cl)
            data.append(["", "TOTAL"] + (["", "", _num(tot) or "—", ""] if coef else [_num(tot) or "—", ""]))
        t = Table(data, colWidths=cw, repeatRows=1)
        note_col = 3 if coef else 2
        style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
                 ("BACKGROUND", (0, 0), (-1, 0), pdfs.BLEU), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                 ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#98A2B3")), ("ALIGN", (2, 1), (-2, -1), "CENTER"),
                 ("ALIGN", (0, 0), (0, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, pdfs.GRIS]),
                 ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
        for i in rouges:
            style.append(("TEXTCOLOR", (note_col, i), (note_col, i), pdfs.ROUGE))
        if not maternelle:
            style += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E4ECF5"))]
        t.setStyle(TableStyle(style))
        _, h = t.wrapOn(c, W - 2 * m_, 600)
        t.drawOn(c, m_, y - h)
        y -= h + 10
        # Résultats
        n_eval = len(matieres) - len(l["dispenses"])
        if maternelle:
            comptes = {k: list(l["appreciations"].values()).count(k) for k in APPRECIATIONS}
            gauche = [["Acquis (A)", comptes["A"]], ["En cours (ECA)", comptes["ECA"]], ["Non acquis (NA)", comptes["NA"]]]
            droite = [["Domaines évalués", f"{len(l['appreciations'])} sur {len(matieres)}"],
                      ["Bilan", l["decision"]]]
        else:
            gauche = [["Moyenne", f"{_moy(l['moyenne'])} / 20" if l["moyenne"] is not None else "—"],
                      ["Rang", f"{l['rang_texte']} sur {l['effectif']}" if l["rang"] else "—"]]
            if not secondaire:
                gauche.insert(0, ["Matières ≥ 10/20", f"{l['reussies']} sur {n_eval}" if l["compose"] else "—"])
                gauche.append(["Seuil de maîtrise", f"{l['seuil']} matière(s) ≥ 10/20 sur {n_eval}"])
            else:
                gauche.append(["Mention", l["mention"]])
            droite = [["Moyenne de la classe", _moy(st["moyenne"]["T"])],
                      ["Plus forte moyenne", _moy(st["plus_forte_moyenne"])],
                      ["Plus faible moyenne", _moy(st["plus_faible_moyenne"])]]
        lg = (W - 2 * m_) / 2 - 3 * mm
        hmax = 0
        for bloc, x, lw in ((gauche, m_, 34 * mm), (droite, m_ + lg + 6 * mm, 40 * mm)):
            tb = Table([[a, Paragraph(str(b), st_c)] for a, b in bloc], colWidths=[lw, lg - lw])
            tb.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                                    ("BOX", (0, 0), (-1, -1), 0.6, pdfs.BLEU),
                                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D5DD")),
                                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            _, hb = tb.wrapOn(c, lg, 200)
            tb.drawOn(c, x, y - hb)
            hmax = max(hmax, hb)
        y -= hmax + 12
        # Décision
        dec = l["decision"]
        couleur = pdfs.VERT if l["maitrise"] else (pdfs.ROUGE if l["maitrise"] is False else colors.grey)
        c.setFillColor(couleur)
        largeur_dec = max(80 * mm, c.stringWidth(f"DÉCISION : {dec}", "Helvetica-Bold", 11) + 12 * mm)
        c.roundRect(m_, y - 22, largeur_dec, 22, 4, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(m_ + largeur_dec / 2, y - 15, f"DÉCISION : {dec}")
        c.setFillColor(colors.black)
        if cl["cycle"] == "primaire":
            c.setFont("Helvetica-Oblique", 7.5)
            c.drawString(m_ + largeur_dec + 4 * mm, y - 9, "La maîtrise est acquise avec au moins le nombre de matières")
            c.drawString(m_ + largeur_dec + 4 * mm, y - 18, "exigé à 10/20 ; la moyenne ne sert qu'au classement.")
        # Signatures (parent, titulaire, administrateur/administratrice, directeur/directrice + cachet) + QR
        base = 16 * mm
        ys = base + 57 * mm  # ligne des titres ; les noms sont 30,5 mm plus bas, au-dessus du QR
        if y - 22 < ys + 20:  # très longue liste de matières : les signatures passent sur une page suivante
            c.showPage()
        code = H.enregistrer_document("bulletin", e["id"], f"Bulletin {ev['titre']} {ev['annee']} – {cl['nom']}",
                                      cle=f"eval|{e['id']}|{ev['id']}|{ev['annee']}")
        pdfs._qr(c, code, m_, base)
        eid = H.eco()
        tit = pdfs.image_data_url(H.signature_titulaire(cl["id"]))
        s_adm = pdfs.image_data_url(H.signature(f"ecole:{eid}:admin"))
        s_dir = pdfs.image_data_url(H.signature(f"ecole:{eid}:directeur")) or pdfs.signature_directeur()
        blocs = [("Le Parent", "", None, False),
                 (cl["titulaire_titre"] or "Le titulaire", cl["titulaire_nom"] or "", tit, False),
                 (_titre_signataire(v.get("admin_titre"), "Administrateur"), v.get("admin_nom") or "", s_adm, False),
                 (_titre_signataire(v.get("directeur_titre"), "Directeur"), v.get("directeur_nom") or "", s_dir, True)]
        larg = W - 2 * m_
        c.setFont("Helvetica", 8)
        c.drawRightString(W - m_, ys + 12, f"{H.config.ECOLE.get('ville') or ''}, le {date.today().strftime('%d/%m/%Y')}")
        for i, (titre_s, nom_s, img, cachet) in enumerate(blocs):
            _dessiner_signature(c, pdfs, m_ + larg * (i + 0.5) / 4, ys, titre_s, nom_s, img, cachet, largeur=40)

    def bulletins_pdf(ev, cl, ids=None):
        from pdfs import GCanvas
        from reportlab.lib.pagesizes import A4
        v = entete(ev, cl)
        matieres, lignes = EC.resultats(ev, cl)
        st = EC.statistiques(matieres, lignes)
        buf = io.BytesIO()
        c = GCanvas(buf, pagesize=A4)
        c.setTitle(f"Bulletins – {ev['titre']} – {cl['nom']}")
        c.setAuthor("GESCOL")
        for l in lignes:
            if ids is not None and l["eleve"]["id"] not in ids:
                continue
            dessiner_bulletin(c, ev, cl, v, l, matieres, st)
            c.showPage()
        c.save()
        return buf.getvalue()

    @app.route("/evaluations/<int:ev_id>/bulletins.pdf")
    @H.connexion_requise("evaluations")
    def eval_bulletins_classe(ev_id):
        ev, cl = charger(ev_id)
        if not EC.eleves_classe(cl["id"]):
            flash("Aucun élève inscrit dans cette classe : pas de bulletin à produire.", "warning")
            return redirect(url_for("eval_saisie", ev_id=ev_id))
        H.journal("evaluation_bulletins", f"{cl['nom']} {ev['libelle']}")
        return H.pdf_reponse(bulletins_pdf(ev, cl), nom_fichier(ev, cl, "bulletins", "pdf"))

    @app.route("/evaluations/<int:ev_id>/bulletin.pdf")
    @H.connexion_requise("evaluations")
    def eval_bulletin_eleve(ev_id):
        ev, cl = charger(ev_id)
        eid = request.args.get("eleve", type=int)
        e = q("SELECT * FROM eleves WHERE id=? AND classe_id=? AND statut='inscrit'", (eid, cl["id"]), un=True) if eid else None
        if not e:
            flash("Choisissez un élève de la classe pour imprimer son bulletin.", "warning")
            return redirect(url_for("eval_saisie", ev_id=ev_id))
        nom = re.sub(r"[^A-Za-z0-9]+", "_", H.xlsx.normaliser(f"bulletin {e['nom']} {e['prenoms']} {ev['libelle']}"))
        return H.pdf_reponse(bulletins_pdf(ev, cl, {e["id"]}), f"{nom}.pdf")
