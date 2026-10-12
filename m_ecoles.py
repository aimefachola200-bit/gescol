# -*- coding: utf-8 -*-
"""Écoles (ajout, modification, école courante), référentiel DDEMP/CS, signatures digitales,
cachet officiel, griffe (cachet rectangulaire du nom du directeur : colonnes ecoles.griffe_actif / griffe_ligne3 /
griffe_couleur, composée automatiquement depuis directeur_titre et directeur_nom, aperçu /ecoles/<id>/griffe.svg,
exposée par H.griffe_ecole(ecole_id) et config.ECOLE["_griffe"]), affectations des enseignants."""
import base64
import json
import re

from flask import Response, abort, flash, g, redirect, render_template, request, session, url_for

import cachet
import referentiel_benin as RB

CHAMPS_ECOLE = ["nom", "sigle", "statut", "ordre", "departement", "cs", "up", "zone", "commune", "ville", "adresse", "bp",
                "telephone", "email", "directeur_titre", "directeur_nom", "directeur_tel", "admin_titre", "admin_nom",
                "ccs_titre", "ccs_nom", "cachet_sup", "cachet_inf", "cachet_centre", "cachet_couleur",
                "griffe_actif", "griffe_ligne3", "griffe_couleur"]
ORDRES = ["Maternelle", "Primaire", "Maternelle et primaire", "Secondaire (collège)", "Secondaire (collège et lycée)",
          "Complexe (maternelle, primaire, secondaire)", "Enseignement technique"]
RE_CLE_SIGNATURE = re.compile(r"^(ecole:\d+:(directeur|admin|ccs)|classe:\d+:titulaire|eleve:\d+|cep:\d+:chef"
                              r"|enseignant:\d+"      # v1.6 : signature personnelle d'un compte enseignant (utilisateurs.id)
                              r"|jur:(service|agent|cs):\d+|jur:structure:responsable)$")


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config
    # v1.6 : lien d'une école locale avec l'école de la juridiction (jur_ecoles) dans GESCOL Circonscription / DDEMP
    H.ajouter_colonne("ecoles", "jur_ecole_id", "INTEGER")
    # v1.6 : griffe (cachet rectangulaire du nom du directeur), composée automatiquement depuis directeur_titre / _nom
    H.ajouter_colonne("ecoles", "griffe_actif", "INTEGER DEFAULT 1")
    H.ajouter_colonne("ecoles", "griffe_ligne3", "TEXT")
    H.ajouter_colonne("ecoles", "griffe_couleur", "TEXT")

    # ------------------------------------------------------------ école courante
    def ecole_exemple_vide():
        """Applications CS / DDEMP : l'école n° 1 créée par défaut au premier démarrage (« Établissement Scolaire
        CPFA ») n'est qu'un exemple tant qu'elle n'est ni reliée à la juridiction (jur_ecole_id), ni renommée,
        ni utilisée (classes, élèves). Elle est alors cachée du sélecteur et des listes d'écoles (sans être
        supprimée : les paramètres de l'application s'y réfèrent) et sert de première école ouverte
        (a_integration : ``_ecole1_vierge``). Renvoie la ligne ``ecoles`` ou None."""
        if not config.juridiction():
            return None
        e = q("SELECT * FROM ecoles WHERE id=1", un=True)
        if not e or e["jur_ecole_id"] or e["nom"] != config.DEFAUTS["ecole_nom"]:
            return None
        if q("SELECT 1 FROM classes WHERE ecole_id=1 LIMIT 1", un=True):
            return None
        if q("SELECT 1 FROM eleves x JOIN classes c ON c.id=x.classe_id WHERE c.ecole_id=1 LIMIT 1", un=True):
            return None
        return e

    H.ecole_exemple_vide = ecole_exemple_vide

    def sans_exemple(liste):
        """Retire l'école d'exemple n° 1 d'une liste d'écoles (applications CS / DDEMP)."""
        if config.juridiction() and ecole_exemple_vide():
            return [e for e in liste if e["id"] != 1]
        return liste

    H.ecoles_sans_exemple = sans_exemple

    def ecoles_accessibles():
        if not g.get("user"):
            return sans_exemple(q("SELECT * FROM ecoles WHERE actif=1 ORDER BY id"))
        if g.user["role"] in ("admin", "fondateur") or not g.user["ecole_id"]:
            return sans_exemple(q("SELECT * FROM ecoles WHERE actif=1 ORDER BY nom"))
        return q("SELECT * FROM ecoles WHERE id=? AND actif=1", (g.user["ecole_id"],))

    def ecole_courante():
        return g.get("ecole")

    def ecole_id():
        return g.ecole["id"] if g.get("ecole") else 1

    H.ecole_id = ecole_id
    H.ecoles_accessibles = ecoles_accessibles

    def signature(cle):
        r = q("SELECT image FROM signatures WHERE cle=?", (cle,), un=True)
        return r["image"] if r else None

    H.signature = signature

    def signature_enseignant(user_id):
        """Signature digitale personnelle d'un compte enseignant (clé « enseignant:<user_id> »), ou None."""
        return signature(f"enseignant:{int(user_id)}") if user_id else None

    def signature_titulaire(cid):
        """Signature du titulaire d'une classe pour les documents de la classe (bulletins, relevés, fiches…) :
        la signature « classe:<id>:titulaire » si elle existe ; sinon la signature personnelle de l'enseignant
        connecté s'il est affecté à la classe ; sinon celle du seul enseignant affecté à la classe."""
        img = signature(f"classe:{int(cid)}:titulaire")
        if img:
            return img
        u = g.get("user")
        if u and u["role"] == "enseignant" and q("SELECT 1 FROM affectations WHERE user_id=? AND classe_id=?",
                                                 (u["id"], cid), un=True):
            return signature_enseignant(u["id"])
        ens = q("""SELECT DISTINCT a.user_id FROM affectations a JOIN utilisateurs u ON u.id=a.user_id
                   WHERE a.classe_id=? AND u.role='enseignant' AND u.actif=1""", (cid,))
        return signature_enseignant(ens[0]["user_id"]) if len(ens) == 1 else None

    def signature_agent(personnel_id):
        """Signature personnelle de l'enseignant dont la fiche du personnel (personnel.user_id) est reliée à son compte."""
        if not personnel_id:
            return None
        try:
            r = q("SELECT user_id FROM personnel WHERE id=?", (personnel_id,), un=True)
        except Exception:  # noqa: BLE001 — colonne absente tant que le module carrière n'est pas installé
            return None
        return signature_enseignant(r["user_id"]) if r and r["user_id"] else None

    H.signature_enseignant = signature_enseignant
    H.signature_titulaire = signature_titulaire
    H.signature_agent = signature_agent

    def griffe_de(e, ligne3=None, couleur=None, titre=None, nom=None):
        """(lignes, couleur) de la griffe d'une école (ligne de la table ecoles) : « LE DIRECTEUR / LA DIRECTRICE »,
        « NOM Prénoms », ligne 3 facultative. None si la griffe est désactivée ou si le nom n'est pas renseigné."""
        if e is None:
            return None
        ks = e.keys() if hasattr(e, "keys") else ()
        actif = e["griffe_actif"] if "griffe_actif" in ks else 1
        if actif is not None and int(actif or 0) == 0:
            return None
        nom = (nom if nom is not None else (e["directeur_nom"] or "")).strip()
        if not nom:
            return None
        titre = titre if titre is not None else (e["directeur_titre"] or "Directeur")
        titre = {"directrice": "La Directrice", "directeur": "Le Directeur"}.get(titre.strip().lower(), titre)
        l3 = ligne3 if ligne3 is not None else ((e["griffe_ligne3"] or "") if "griffe_ligne3" in ks else "")
        coul = couleur if couleur is not None else ((e["griffe_couleur"] or "") if "griffe_couleur" in ks else "")
        return [titre, nom, l3], (coul if coul in cachet.COULEURS else (e["cachet_couleur"] if "cachet_couleur" in ks and e["cachet_couleur"] in cachet.COULEURS else "bleu"))

    def griffe_ecole(eid=None):
        """(lignes, couleur) de la griffe de l'école (par défaut l'école courante), ou None."""
        e = g.get("ecole") if (eid is None or (g.get("ecole") and g.ecole["id"] == eid)) else None
        if e is None and eid is not None:
            e = q("SELECT * FROM ecoles WHERE id=?", (eid,), un=True)
        return griffe_de(e)

    H.griffe_ecole = griffe_ecole

    def appliquer_identite_ecole(e):
        """Recopie la fiche de l'école dans config.ECOLE (en-têtes des documents, matricules…)."""
        if e:
            config.ECOLE.update({
                "id": e["id"], "nom": e["nom"], "sigle": e["sigle"] or "", "adresse": e["adresse"] or "",
                "telephone": e["telephone"] or "", "email": e["email"] or "", "ville": e["ville"] or e["commune"] or "",
                "directeur": e["directeur_nom"] or "", "directeur_titre": e["directeur_titre"] or "Directeur",
                "statut": e["statut"] or "", "departement": e["departement"] or "", "cs": e["cs"] or "",
                "commune": e["commune"] or "", "up": e["up"] or "", "zone": e["zone"] or "", "bp": e["bp"] or "",
                "admin_titre": e["admin_titre"] or "", "admin_nom": e["admin_nom"] or "",
                "ccs_titre": e["ccs_titre"] or "", "ccs_nom": e["ccs_nom"] or "",
                "_cachet": (e["cachet_sup"] or "", e["cachet_inf"] or "", e["cachet_centre"] or "", e["cachet_couleur"] or "bleu")
                if (e["cachet_sup"] or e["cachet_centre"]) else None,
                "_sig_directeur": signature(f"ecole:{e['id']}:directeur"),
                "_griffe": griffe_de(e),
            })

    H.appliquer_identite_ecole = appliquer_identite_ecole

    def effacer_identite_ecole():
        """Applications CS / DDEMP sans école ouverte : config.ECOLE ne garde rien d'une école ouverte lors d'une
        requête précédente (cachet, griffe, signature, directeur…) ; l'identité affichée (nom, sigle, adresse…)
        est celle de la structure, posée par m_juridiction (jur_entete)."""
        config.ECOLE.update({"id": None, "directeur": "", "directeur_titre": "Directeur", "statut": "", "up": "",
                             "zone": "", "bp": "", "commune": "", "admin_titre": "", "admin_nom": "", "ccs_titre": "",
                             "ccs_nom": "", "_cachet": None, "_sig_directeur": None, "_griffe": None})

    @app.before_request
    def charger_ecole():
        """École courante (g.ecole). Éditions école : l'école choisie (session), sinon la première accessible.
        Applications CS / DDEMP : aucune école n'est ouverte tant que l'utilisateur n'en a pas choisi une
        (session["ecole_id"]) ; un compte directeur / enseignant rattaché à une école (utilisateurs.ecole_id)
        ouvre d'office son école. Sans école ouverte, g.ecole = None (a_integration affiche la page de choix
        sur les modules d'école)."""
        liste = ecoles_accessibles()
        choix = session.get("ecole_id")
        e = next((x for x in liste if x["id"] == choix), None)
        if config.juridiction():
            if e is None and g.get("user") and g.user["ecole_id"]:
                e = next((x for x in liste if x["id"] == g.user["ecole_id"]), None)
            if e is None and choix:
                session.pop("ecole_id", None)
        else:
            e = e or (liste[0] if liste else None)
            if e is None:
                e = q("SELECT * FROM ecoles ORDER BY id", un=True)
        g.ecole = e
        g.ecoles = liste
        if e is not None:
            appliquer_identite_ecole(e)
        else:
            effacer_identite_ecole()

    @app.context_processor
    def ctx_ecoles():
        return dict(DEPARTEMENTS=RB.DEPARTEMENTS, ECOLE_COURANTE=g.get("ecole"), ECOLES=g.get("ecoles") or [],
                    signature_de=signature)

    def modifier_ecole_depuis_parametres(nouv):
        """La page Paramètres modifie aussi la fiche de l'école courante (pas dans les applications CS / DDEMP :
        les paramètres y décrivent la structure, pas l'école ouverte)."""
        if config.juridiction():
            return
        ex("""UPDATE ecoles SET nom=?, sigle=?, adresse=?, ville=?, telephone=?, email=?, directeur_nom=? WHERE id=?""",
           (nouv.get("ecole_nom"), nouv.get("ecole_sigle"), nouv.get("ecole_adresse"), nouv.get("ecole_ville"),
            nouv.get("ecole_telephone"), nouv.get("ecole_email"), nouv.get("ecole_directeur"), ecole_id()))

    app.apres_parametres = modifier_ecole_depuis_parametres

    # ------------------------------------------------------------ référentiel (listes en cascade)
    @app.route("/referentiel.js")
    def referentiel_js():
        data = {d: [c["cs"] for c in lst] for d, lst in RB.CIRCONSCRIPTIONS.items()}
        js = "window.CS_PAR_DEP=" + json.dumps(data, ensure_ascii=False) + ";"
        return Response(js, mimetype="application/javascript", headers={"Cache-Control": "max-age=86400"})

    # ------------------------------------------------------------ écoles
    @app.route("/ecoles")
    @H.connexion_requise("ecoles")
    def ecoles():
        lst = q("""SELECT e.*, (SELECT COUNT(*) FROM classes c WHERE c.ecole_id=e.id) nb_classes,
                   (SELECT COUNT(*) FROM eleves x JOIN classes c ON c.id=x.classe_id WHERE c.ecole_id=e.id AND x.statut='inscrit') nb_eleves
                   FROM ecoles e WHERE ? OR e.id IN (SELECT id FROM ecoles WHERE id=?) ORDER BY e.actif DESC, e.nom""",
                (H.peut("parametres"), ecole_id()))
        return render_template("ecoles.html", lst=sans_exemple(lst))

    @app.route("/ecoles/nouvelle", methods=["GET", "POST"])
    @app.route("/ecoles/<int:eid>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("ecoles")
    def ecole_form(eid=None):
        # le directeur modifie la fiche de son école ; l'administrateur / le fondateur crée et modifie toutes les écoles
        if not H.peut("parametres") and (eid is None or eid != ecole_id()):
            abort(403)
        e = q("SELECT * FROM ecoles WHERE id=?", (eid,), un=True) if eid else None
        if eid and not e:
            abort(404)
        if request.method == "POST":
            f = {k: request.form.get(k, "").strip()[:200] for k in CHAMPS_ECOLE}
            if not f["nom"]:
                flash("Le nom de l'école est obligatoire.", "danger")
                return render_template("ecole_form.html", e=f, ordres=ORDRES, edition=bool(eid)), 400
            if f["cachet_couleur"] not in cachet.COULEURS:
                f["cachet_couleur"] = "bleu"
            if f["griffe_couleur"] not in cachet.COULEURS:
                f["griffe_couleur"] = ""
            f["griffe_actif"] = 1 if f["griffe_actif"] == "1" else 0
            f["sigle"] = f["sigle"].upper()
            if eid:
                ex(f"UPDATE ecoles SET {', '.join(k + '=?' for k in CHAMPS_ECOLE)} WHERE id=?",
                   [f[k] for k in CHAMPS_ECOLE] + [eid])
                H.journal("ecole_modifiee", f["nom"])
            else:
                eid = ex(f"INSERT INTO ecoles ({', '.join(CHAMPS_ECOLE)}, cree_le) VALUES ({', '.join('?' * len(CHAMPS_ECOLE))}, ?)",
                         [f[k] for k in CHAMPS_ECOLE] + [H.maintenant()])
                H.journal("ecole_creee", f["nom"])
                session["ecole_id"] = eid
                # applications CS / DDEMP : l'école apparaît aussi dans la liste des écoles de la juridiction
                if config.juridiction() and getattr(H, "jur_lier_ecole", None):
                    H.jur_lier_ecole(eid)
            logo = request.files.get("logo")
            if logo and logo.filename:
                try:
                    from PIL import Image
                    import os
                    img = Image.open(logo.stream)
                    img.thumbnail((600, 600))
                    img.save(os.path.join(config.ECOLE_DIR, f"logo_{eid}.png"), "PNG")
                except Exception:  # noqa: BLE001
                    flash("Logo illisible (PNG ou JPG).", "danger")
            flash("École enregistrée.", "success")
            return redirect(url_for("ecoles"))
        return render_template("ecole_form.html", e=e or {"statut": "Privée", "directeur_titre": "Directeur",
                                                          "admin_titre": "Administrateur", "ccs_titre": "Le CCS",
                                                          "cachet_couleur": "bleu", "griffe_actif": 1},
                               ordres=ORDRES, edition=bool(eid))

    @app.route("/ecoles/<int:eid>/choisir", methods=["POST"])
    @H.connexion_requise()
    def ecole_choisir(eid):
        if eid not in {e["id"] for e in ecoles_accessibles()}:
            abort(403)
        session["ecole_id"] = eid
        suivant = request.form.get("suivant", "")
        return redirect(suivant if suivant.startswith("/") and not suivant.startswith("//") else url_for("accueil"))

    @app.route("/ecoles/<int:eid>/supprimer", methods=["POST"])
    @H.connexion_requise("parametres")
    def ecole_supprimer(eid):
        """Supprime une école sans élèves ni classes (sinon : la désactiver). Dans les applications CS / DDEMP,
        l'école liée de la juridiction est retirée de la liste (actif=0, données conservées)."""
        e = q("SELECT * FROM ecoles WHERE id=?", (eid,), un=True)
        if not e:
            abort(404)
        if eid == 1 and not config.juridiction():
            flash("L'école principale ne peut pas être supprimée.", "warning")
            return redirect(url_for("ecoles"))
        nb_classes = q("SELECT COUNT(*) n FROM classes WHERE ecole_id=?", (eid,), un=True)["n"]
        nb_eleves = q("SELECT COUNT(*) n FROM eleves x JOIN classes c ON c.id=x.classe_id WHERE c.ecole_id=?", (eid,), un=True)["n"]
        if nb_classes or nb_eleves:
            flash(f"« {e['nom']} » a {nb_classes} classe(s) et {nb_eleves} élève(s) : elle ne peut pas être supprimée. "
                  "Désactivez-la (ses données sont conservées) ou supprimez d'abord ses classes.", "danger")
            return redirect(url_for("ecoles"))
        if q("SELECT COUNT(*) n FROM ecoles", un=True)["n"] <= 1:
            flash("Impossible de supprimer la dernière école.", "warning")
            return redirect(url_for("ecoles"))
        ex("DELETE FROM ecoles WHERE id=?", (eid,))
        ex("UPDATE utilisateurs SET ecole_id=NULL WHERE ecole_id=?", (eid,))
        if config.juridiction() and e["jur_ecole_id"]:
            ex("UPDATE jur_ecoles SET actif=0, maj=datetime('now','localtime') WHERE id=?", (e["jur_ecole_id"],))
        if session.get("ecole_id") == eid:
            session.pop("ecole_id", None)
        H.journal("ecole_supprimee", e["nom"])
        flash(f"École « {e['nom']} » supprimée.", "success")
        return redirect(url_for("ecoles"))

    @app.route("/ecoles/<int:eid>/basculer", methods=["POST"])
    @H.connexion_requise("parametres")
    def ecole_basculer(eid):
        if eid == 1 and not config.juridiction():
            flash("L'école principale ne peut pas être désactivée.", "warning")
        else:
            ex("UPDATE ecoles SET actif=1-actif WHERE id=?", (eid,))
        return redirect(url_for("ecoles"))

    @app.route("/cachet.svg")
    def cachet_svg():
        """Aperçu du cachet (paramètres dans l'adresse, ou école courante)."""
        e = g.get("ecole") or {}
        a = request.args
        s = cachet.svg(a.get("sup", e["cachet_sup"] if e else ""), a.get("inf", e["cachet_inf"] if e else ""),
                       a.get("centre", e["cachet_centre"] if e else ""), a.get("couleur", e["cachet_couleur"] if e else "bleu"),
                       int(a.get("taille", 180)))
        return Response(s, mimetype="image/svg+xml", headers={"Cache-Control": "no-cache"})

    @app.route("/ecoles/griffe.svg")
    @app.route("/ecoles/<int:eid>/griffe.svg")
    @H.connexion_requise()
    def ecole_griffe_svg(eid=None):
        """Aperçu de la griffe (cachet rectangulaire du nom) : école donnée ou courante ; les paramètres titre, nom,
        ligne3 et couleur de l'adresse permettent l'aperçu instantané pendant la saisie."""
        e = q("SELECT * FROM ecoles WHERE id=?", (eid,), un=True) if eid else g.get("ecole")
        if eid and not e:
            abort(404)
        a = request.args
        gr = griffe_de(e, ligne3=a.get("ligne3"), couleur=a.get("couleur"), titre=a.get("titre"), nom=a.get("nom")) \
            if (e is not None or a.get("nom")) else None
        if gr is None and a.get("nom"):
            gr = [a.get("titre") or "Le Directeur", a.get("nom"), a.get("ligne3") or ""], a.get("couleur") or "bleu"
        lignes, couleur = gr if gr else (["Le Directeur", "NOM Prénoms (à renseigner)"], "bleu")
        largeur = int(a.get("largeur") or 260) if (a.get("largeur") or "").isdigit() else 260
        return Response(cachet.svg_nom(lignes, couleur, max(120, min(largeur, 600))), mimetype="image/svg+xml",
                        headers={"Cache-Control": "no-cache"})

    @app.route("/ecoles/<int:eid>/logo.png")
    @H.connexion_requise()
    def ecole_logo(eid):
        import os
        from flask import send_file
        p = os.path.join(config.ECOLE_DIR, f"logo_{eid}.png")
        if not os.path.exists(p):
            p = os.path.join(config.ECOLE_DIR, "logo.png")
        if not os.path.exists(p):
            abort(404)
        return send_file(p, max_age=0)

    # ------------------------------------------------------------ signatures digitales
    @app.route("/signatures/<cle>.png")
    @H.connexion_requise()
    def signature_png(cle):
        img = signature(cle)
        if not img or not img.startswith("data:image/png;base64,"):
            abort(404)
        return Response(base64.b64decode(img.split(",", 1)[1]), mimetype="image/png", headers={"Cache-Control": "no-cache"})

    @app.route("/signatures/<cle>", methods=["POST"])
    @H.connexion_requise()
    def signature_enregistrer(cle):
        if not RE_CLE_SIGNATURE.match(cle) or g.user["role"] == "comptable":
            abort(403)
        if cle.startswith("ecole:") and g.user["role"] not in ("admin", "fondateur", "directeur", "responsable", "chef_service"):
            abort(403)
        if cle.startswith("jur:") and g.user["role"] not in ("admin", "fondateur", "responsable", "chef_service", "cp"):
            abort(403)
        if cle.startswith("enseignant:") and g.user["role"] == "enseignant" and cle != f"enseignant:{g.user['id']}":
            abort(403)                      # un enseignant ne signe que pour lui-même
        if g.user["role"] == "enseignant" and (cle.startswith(("eleve:", "cep:")) or (
                cle.startswith("classe:") and int(cle.split(":")[1]) not in {c["id"] for c in classes_autorisees()})):
            abort(403)                      # … et pour les classes qui lui sont affectées
        data = request.get_json(silent=True) or {}
        img = data.get("image")
        if data.get("effacer"):
            ex("DELETE FROM signatures WHERE cle=?", (cle,))
            H.journal("signature_effacee", cle)
            return {"ok": True}
        if not img or not img.startswith("data:image/png;base64,") or len(img) > 400_000:
            return {"ok": False, "erreur": "Signature invalide."}, 400
        ex("INSERT INTO signatures (cle, image, maj) VALUES (?,?,?) ON CONFLICT(cle) DO UPDATE SET image=excluded.image, maj=excluded.maj",
           (cle, img, H.maintenant()))
        H.journal("signature", cle)
        return {"ok": True}

    # ------------------------------------------------------------ affectations des enseignants
    @app.route("/utilisateurs/<int:uid>/affectations", methods=["GET", "POST"])
    @H.connexion_requise("parametres")
    def affectations(uid):
        u = q("SELECT * FROM utilisateurs WHERE id=?", (uid,), un=True)
        if not u:
            abort(404)
        if request.method == "POST":
            ex("DELETE FROM affectations WHERE user_id=?", (uid,))
            for v in request.form.getlist("aff"):
                cid, _, mid = v.partition(":")
                ex("INSERT OR IGNORE INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,?)",
                   (uid, int(cid), int(mid) if mid else None))
            eco = request.form.get("ecole_id", type=int)
            ex("UPDATE utilisateurs SET ecole_id=? WHERE id=?", (eco or None, uid))
            H.journal("affectations", u["identifiant"])
            flash("Affectations enregistrées.", "success")
            return redirect(url_for("utilisateurs"))
        classes = q("SELECT c.*, e.nom ecole_nom FROM classes c LEFT JOIN ecoles e ON e.id=c.ecole_id ORDER BY e.nom, c.nom")
        mats = q("SELECT * FROM matieres WHERE cycle='secondaire' AND actif=1 ORDER BY ordre")
        actuelles = {(a["classe_id"], a["matiere_id"]) for a in q("SELECT * FROM affectations WHERE user_id=?", (uid,))}
        return render_template("affectations.html", u=u, classes=classes, mats=mats, actuelles=actuelles,
                               ecoles_toutes=q("SELECT * FROM ecoles ORDER BY nom"))

    def classes_autorisees():
        """Classes que l'utilisateur peut gérer (école courante ; enseignant : ses classes affectées)."""
        eid = ecole_id()
        if g.get("user") and g.user["role"] == "enseignant":
            ids = [r["classe_id"] for r in q("SELECT DISTINCT classe_id FROM affectations WHERE user_id=?", (g.user["id"],))]
            if ids:
                marque = ",".join("?" * len(ids))
                return q(f"SELECT * FROM classes WHERE id IN ({marque}) AND ecole_id=? ORDER BY nom", ids + [eid])
        return q("SELECT * FROM classes WHERE ecole_id=? ORDER BY nom", (eid,))

    def verifier_classe(cid):
        if cid not in {c["id"] for c in classes_autorisees()}:
            abort(403)

    def matieres_autorisees(cid):
        """None = toutes ; sinon ensemble des matières affectées à l'enseignant pour cette classe."""
        if g.get("user") and g.user["role"] == "enseignant":
            rows = q("SELECT matiere_id FROM affectations WHERE user_id=? AND classe_id=?", (g.user["id"], cid))
            if rows and all(r["matiere_id"] for r in rows):
                return {r["matiere_id"] for r in rows}
        return None

    H.classes_autorisees = classes_autorisees
    H.verifier_classe = verifier_classe
    H.matieres_autorisees = matieres_autorisees

    # ------------------------------------------------------------ en-têtes et données sauvegardées des modules
    RE_CLE_DOC = re.compile(r"^[a-z_]{2,30}(:[\w.-]{1,60}){0,4}$")

    def doc_lire(cle, defaut=None):
        r = q("SELECT donnees, maj FROM documents_modules WHERE cle=?", (cle,), un=True)
        if not r:
            return defaut
        try:
            return json.loads(r["donnees"])
        except ValueError:
            return defaut

    def doc_ecrire(cle, donnees):
        ex("INSERT INTO documents_modules (cle, donnees, maj, maj_par) VALUES (?,?,?,?) "
           "ON CONFLICT(cle) DO UPDATE SET donnees=excluded.donnees, maj=excluded.maj, maj_par=excluded.maj_par",
           (cle, json.dumps(donnees, ensure_ascii=False), H.maintenant(), g.user["id"] if g.get("user") else None))

    H.doc_lire = doc_lire
    H.doc_ecrire = doc_ecrire

    @app.route("/documents-modules/<path:cle>", methods=["GET", "POST"])
    @H.connexion_requise()
    def document_module(cle):
        """Sauvegarder / Charger d'un formulaire d'en-tête. La clé est préfixée par l'école courante."""
        if not RE_CLE_DOC.match(cle):
            abort(400)
        # en-têtes liés à une classe : un enseignant ne peut écrire/lire que ceux de ses classes
        m_cl = re.match(r"^(releve|affichage|cantine|registre|resultats_entete|bilan|eval)[a-z_]*:(\d+)", cle)
        if m_cl:
            verifier_classe(int(m_cl.group(2)))
        cle_reelle = f"e{ecole_id()}:{cle}"
        if request.method == "POST":
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or len(json.dumps(data)) > 500_000:
                return {"ok": False, "erreur": "Données invalides."}, 400
            doc_ecrire(cle_reelle, data)
            return {"ok": True}
        r = q("SELECT donnees, maj FROM documents_modules WHERE cle=?", (cle_reelle,), un=True)
        return {"donnees": json.loads(r["donnees"]) if r else None, "maj": r["maj"] if r else None}

    def identification(classe=None, **extra):
        """Valeurs par défaut des en-têtes (DDEMP, CS, école, cours, année, titulaire, directeur…)."""
        e = g.get("ecole") or {}
        d = {
            "departement": e["departement"] if e else "", "ddemp": e["departement"] if e else "",
            "cs": e["cs"] if e else "", "up": e["up"] if e else "", "zone": e["zone"] if e else "",
            "commune": e["commune"] if e else "", "ecole": e["nom"] if e else "",
            "annee": config.ANNEE_ACTIVE,
            "directeur_titre": (e["directeur_titre"] if e else "") or "Directeur",
            "directeur_nom": e["directeur_nom"] if e else "",
            "admin_titre": (e["admin_titre"] if e else "") or "Administrateur",
            "admin_nom": e["admin_nom"] if e else "",
            "ccs_titre": (e["ccs_titre"] if e else "") or "Le CCS", "ccs_nom": e["ccs_nom"] if e else "",
            "cours": "", "classe": "", "titulaire_titre": "Le titulaire", "titulaire_nom": "",
        }
        if classe:
            d.update(cours=classe["niveau"], classe=classe["nom"],
                     titulaire_titre=classe["titulaire_titre"] or "Le titulaire", titulaire_nom=classe["titulaire_nom"] or "")
        d.update(extra)
        return d

    H.identification = identification
    import outils_xlsx
    H.xlsx = outils_xlsx
