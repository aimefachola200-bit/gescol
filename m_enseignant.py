# -*- coding: utf-8 -*-
"""v1.14 — SCOLARIS Enseignant : l'application de l'enseignant, limitée à son périmètre.

Deux usages, un seul module :

1. **Application personnelle** (édition ``enseignant`` : SCOLARIS-Enseignant.apk / SCOLARIS-Enseignant-Installation.exe).
   L'enseignant l'installe sur SON téléphone ou SON ordinateur, sans passer par l'application de l'école.
   Au premier lancement, un assistant (``/enseignant/premier-lancement``) enregistre :
   son profil (nom, prénoms, sexe, NIP, matricule, grade, catégorie / statut, date de naissance, dates de prise de
   service, diplômes), son école (nom, secteur public / privé, CS, DDEMP, directeur, téléphone) et sa ou ses classes.
   Il crée son compte (rôle « enseignant », classes affectées), sa fiche du personnel et sa fiche de carrière ;
   le compte « admin » de départ est désactivé. L'enseignant ajoute ou importe lui-même ses élèves et tient
   l'emploi du temps et la planification de ses niveaux (m_perimetre_enseignant, règles propres à cette édition).

2. **Portail enseignant des applications d'école** (SCOLARIS, SCOLARIS Public, Circonscription, DDEMP) :
   ``/enseignant`` = page de connexion « SCOLARIS Enseignant » (manifeste PWA propre : nom et adresse de départ),
   réservée aux comptes enseignant ; même menu réduit sur les données de l'école, sécurité inchangée
   (m_perimetre_enseignant).

Menu de l'enseignant (``_menu_enseignant.html``) : tableau de bord, ma classe (élèves, appel, registre, notes,
bulletins), emplois du temps, planifications annuelle et mensuelle, calendrier officiel, règlement intérieur,
thèmes d'UP, documents officiels et « Mes certificats » (PDF pré-remplis, m_docs_enseignant), ma carrière,
mon compte (mot de passe, question de secours, signature). Les modules du directeur et de l'école n'y figurent pas.
"""
import json
import re

from flask import Response, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from calcul import NIVEAUX_MATERNELLE, NIVEAUX_PRIMAIRE, NIVEAUX_SECONDAIRE

NIVEAUX = NIVEAUX_MATERNELLE + NIVEAUX_PRIMAIRE + NIVEAUX_SECONDAIRE
# catégorie : codes de la gestion de carrière (m_carriere.CATEGORIES) et autres situations
CATEGORIES = [("FE", "FE (fonctionnaire de l'État)"), ("ACDPE", "ACDPE (agent contractuel de droit public)"),
              ("ACDPCTD", "ACDPCTD (AME)"), ("Communautaire", "Enseignant communautaire"),
              ("Privé", "Enseignant du privé"), ("Autre", "Autre")]
STATUTS = ["Titulaire", "Stagiaire", "Contractuel", "Vacataire", "Communautaire", "Enseignant du privé"]
DIPLOMES_PRO = ["", "CEAP", "CAP", "CEAP et CAP", "Aucun"]
NB_CLASSES = 4
RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_IDENT = re.compile(r"^[A-Za-z0-9._-]{3,40}$")
# endpoints ouverts tant que l'application de l'enseignant n'est pas configurée
OUVERTS_AVANT = {"static", "ens_assistant", "ens_manifeste", "manifeste", "service_worker", "hors_ligne", "verifier"}

PROFIL = ("nom", "prenoms", "sexe", "nip", "matricule", "grade", "categorie", "statut", "date_naissance",
          "lieu_naissance", "telephone", "email", "date_prise_service", "date_service_ecole", "diplome_academique",
          "diplome_academique_annee", "diplome_pro", "diplome_pro_annee")
ECOLE = ("ecole_nom", "secteur", "cs", "departement", "commune", "directeur_nom", "directeur_tel", "ecole_telephone",
         "ccs_nom")


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config
    H.ajouter_colonne("personnel", "lieu_naissance", "TEXT")
    # grade et catégorie : dans personnel_carriere seulement (une colonne homonyme dans personnel masquerait la
    # valeur de la carrière dans les jointures « p.*, c.* » de m_carriere et m_synoptique)

    # ------------------------------------------------------------------ utilitaires
    def param(cle, defaut=""):
        r = q("SELECT valeur FROM parametres WHERE cle=?", (cle,), un=True)
        return r["valeur"] if r and r["valeur"] is not None else defaut

    def ecrire_param(cle, valeur):
        ex("INSERT INTO parametres (cle, valeur) VALUES (?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur",
           (cle, valeur))

    def configuree():
        return param("enseignant_configure") == "1"

    def menu_enseignant():
        """Le menu réduit de l'enseignant s'applique-t-il ? (application de l'enseignant, ou portail /enseignant)"""
        u = g.get("user")
        return bool(u) and u["role"] == "enseignant" and (config.enseignant() or session.get("portail") == "enseignant")

    def portail_enseignant():
        return config.enseignant() or session.get("portail") == "enseignant" or request.path.startswith("/enseignant")

    H.menu_enseignant = menu_enseignant
    H.enseignant_configure = configuree

    def mes_fiches():
        """Fiches du personnel liées au compte connecté (personnel.user_id)."""
        return q("SELECT * FROM personnel WHERE user_id=? ORDER BY id", (g.user["id"],))

    def carriere_de(pid):
        try:
            r = q("SELECT * FROM personnel_carriere WHERE personnel_id=?", (pid,), un=True)
        except Exception:  # noqa: BLE001 — table créée par m_carriere
            return {}
        return dict(r) if r else {}

    def exiger_enseignant():
        if not g.get("user") or g.user["role"] != "enseignant":
            abort(403)

    def exiger_application():
        """Pages réservées à l'application personnelle (dans une école, le profil et les classes relèvent du directeur)."""
        exiger_enseignant()
        if not config.enseignant():
            abort(404)

    def lire(champs):
        return {k: (request.form.get(k) or "").strip()[:200] for k in champs}

    def valider(f, avec_compte):
        err = []
        if not f["nom"] or not f["prenoms"]:
            err.append("Indiquez votre nom et vos prénoms.")
        if f["sexe"] not in ("M", "F"):
            err.append("Indiquez votre sexe.")
        for k in ("date_naissance", "date_prise_service", "date_service_ecole"):
            if f[k] and not RE_DATE.match(f[k]):
                err.append("Dates au format AAAA-MM-JJ.")
                break
        if not f["ecole_nom"]:
            err.append("Indiquez le nom de votre école.")
        if f["secteur"] not in ("publique", "privee"):
            err.append("Choisissez le secteur de l'école (public ou privé).")
        if avec_compte:
            if not RE_IDENT.match(f["identifiant"]) or f["identifiant"].lower() == "admin":
                err.append("Identifiant : 3 à 40 lettres, chiffres, points ou tirets (pas « admin »).")
            e_mdp = __import__("m_securite").erreur_mdp(f["mdp"], f["identifiant"])
            if e_mdp:
                err.append(e_mdp)
            elif f["mdp"] != f["confirmation"]:
                err.append("La confirmation du mot de passe ne correspond pas.")
        return err

    def lire_classes():
        out, err = [], []
        for i in range(1, NB_CLASSES + 1):
            nom = (request.form.get(f"classe_nom_{i}") or "").strip()[:60]
            niv = request.form.get(f"classe_niveau_{i}") or ""
            if not nom and not niv:
                continue
            if not nom or niv not in NIVEAUX:
                err.append(f"Classe {i} : indiquez le nom et le niveau.")
                continue
            if nom.lower() in {c[0].lower() for c in out}:
                err.append(f"Classe « {nom} » en double.")
                continue
            out.append((nom, niv))
        return out, err

    def enregistrer_ecole(f):
        """École n° 1 de la base (fiche de l'école) et paramètres d'en-tête des documents."""
        statut = "Publique" if f["secteur"] == "publique" else "Privée"
        ex("""UPDATE ecoles SET nom=?, statut=?, cs=?, departement=?, commune=?, ville=COALESCE(NULLIF(?, ''), ville),
              directeur_nom=?, directeur_tel=?, telephone=?, ccs_nom=? WHERE id=1""",
           (f["ecole_nom"], statut, f["cs"], f["departement"], f["commune"], f["commune"], f["directeur_nom"],
            f["directeur_tel"], f["ecole_telephone"], f["ccs_nom"]))
        sigle = "".join(m[0] for m in re.findall(r"[A-Za-zÀ-ÿ]+", f["ecole_nom"]) if len(m) > 2)[:8].upper() or "EPP"
        for cle, val in (("ecole_nom", f["ecole_nom"]), ("ecole_directeur", f["directeur_nom"]),
                         ("ecole_telephone", f["ecole_telephone"]), ("ecole_ville", f["commune"]),
                         ("secteur_enseignant", f["secteur"])):
            ecrire_param(cle, val)
        if not param("ecole_sigle") or param("ecole_sigle") == config.DEFAUTS["ecole_sigle"]:
            ecrire_param("ecole_sigle", sigle)

    def enregistrer_profil(f, uid, pid=None):
        """Fiche du personnel (personnel) et fiche de carrière (personnel_carriere) de l'enseignant."""
        valeurs = dict(nom=f["nom"].upper(), prenoms=f["prenoms"], sexe=f["sexe"], matricule=f["matricule"] or None,
                       telephone=f["telephone"], email=f["email"], date_embauche=f["date_service_ecole"] or f["date_prise_service"],
                       nip=f["nip"], date_naissance=f["date_naissance"], lieu_naissance=f["lieu_naissance"],
                       type_contrat=f["statut"] or "Titulaire")
        if pid:
            ex("UPDATE personnel SET " + ", ".join(f"{k}=?" for k in valeurs) + " WHERE id=?", list(valeurs.values()) + [pid])
        else:
            valeurs.update(fonction="Enseignante" if f["sexe"] == "F" else "Enseignant", user_id=uid, ecole_id=1, actif=1)
            pid = ex(f"INSERT INTO personnel ({', '.join(valeurs)}) VALUES ({', '.join('?' * len(valeurs))})",
                     list(valeurs.values()))
        pro = f["diplome_pro"]
        car = dict(categorie=f["categorie"], grade=f["grade"],
                   date_prise_service=f["date_prise_service"], date_service_ecole=f["date_service_ecole"],
                   diplome_academique=f["diplome_academique"],
                   diplome_academique_annee=int(f["diplome_academique_annee"]) if f["diplome_academique_annee"].isdigit() else None,
                   ceap="oui" if "CEAP" in pro else ("non" if pro == "Aucun" else ""),
                   cap="oui" if "CAP" in pro.replace("CEAP", "") else ("non" if pro == "Aucun" else ""),
                   maj=H.maintenant(), maj_par=uid)
        annee = int(f["diplome_pro_annee"]) if f["diplome_pro_annee"].isdigit() else None
        if "CAP" in pro.replace("CEAP", ""):
            car["cap_annee"] = annee
        elif "CEAP" in pro:
            car["ceap_annee"] = annee
        try:
            if q("SELECT 1 FROM personnel_carriere WHERE personnel_id=?", (pid,), un=True):
                ex("UPDATE personnel_carriere SET " + ", ".join(f"{k}=?" for k in car) + " WHERE personnel_id=?",
                   list(car.values()) + [pid])
            else:
                ex(f"INSERT INTO personnel_carriere (personnel_id, {', '.join(car)}) VALUES (?, {', '.join('?' * len(car))})",
                   [pid] + list(car.values()))
        except Exception:  # noqa: BLE001 — sans m_carriere, la fiche du personnel suffit
            pass
        return pid

    def creer_classe(nom, niveau, uid, titulaire):
        if q("SELECT 1 FROM classes WHERE ecole_id=1 AND lower(nom)=lower(?)", (nom,), un=True):
            return None
        cid = ex("INSERT INTO classes (nom, niveau, frais_scolarite, ecole_id, titulaire_nom, titulaire_titre) "
                 "VALUES (?,?,0,1,?,?)", (nom, niveau, titulaire, "Le titulaire"))
        ex("INSERT OR IGNORE INTO affectations (user_id, classe_id, matiere_id) VALUES (?,?,NULL)", (uid, cid))
        return cid

    def valeurs_profil():
        """Valeurs actuelles du profil et de l'école (formulaire « Mon profil et mon école »)."""
        fiches = mes_fiches()
        p = dict(fiches[0]) if fiches else {}
        car = carriere_de(p["id"]) if p else {}
        e = q("SELECT * FROM ecoles WHERE id=1", un=True)
        pro = " et ".join(x for x, k in (("CEAP", "ceap"), ("CAP", "cap")) if car.get(k) == "oui")
        v = {k: (p.get(k) or "") for k in ("nom", "prenoms", "sexe", "nip", "matricule",
                                           "date_naissance", "lieu_naissance", "telephone", "email")}
        v.update(statut=p.get("type_contrat") or "", grade=car.get("grade") or "", categorie=car.get("categorie") or "", date_prise_service=car.get("date_prise_service") or "",
                 date_service_ecole=car.get("date_service_ecole") or "", diplome_academique=car.get("diplome_academique") or "",
                 diplome_academique_annee=str(car.get("diplome_academique_annee") or ""),
                 diplome_pro=pro or ("Aucun" if car.get("cap") == "non" and car.get("ceap") == "non" else ""),
                 diplome_pro_annee=str(car.get("cap_annee") or car.get("ceap_annee") or ""),
                 ecole_nom=e["nom"] if e else "", secteur=config.SECTEUR_ENSEIGNANT, cs=(e["cs"] if e else "") or "",
                 departement=(e["departement"] if e else "") or "", commune=(e["commune"] if e else "") or "",
                 directeur_nom=(e["directeur_nom"] if e else "") or "", directeur_tel=(e["directeur_tel"] if e else "") or "",
                 ecole_telephone=(e["telephone"] if e else "") or "", ccs_nom=(e["ccs_nom"] if e else "") or "")
        return v, (p.get("id") if p else None)

    def listes():
        return dict(NIVEAUX=NIVEAUX, CATEGORIES=CATEGORIES, STATUTS=STATUTS, DIPLOMES_PRO=DIPLOMES_PRO, NB_CLASSES=NB_CLASSES)

    # ------------------------------------------------------------------ contexte des gabarits
    @app.context_processor
    def ctx_enseignant():
        d = dict(MENU_ENSEIGNANT=menu_enseignant, PORTAIL_ENSEIGNANT=portail_enseignant)
        try:
            if portail_enseignant():
                d["NOM_APPLI"] = config.NOM_PORTAIL_ENSEIGNANT if not config.enseignant() else config.NOMS_APPLI["enseignant"]
        except RuntimeError:  # hors requête
            pass
        return d

    # ------------------------------------------------------------------ application de l'enseignant : premier lancement
    @app.before_request
    def ens_garde():
        if not config.enseignant():
            return None
        ep = request.endpoint or ""
        if not configuree():
            if ep in OUVERTS_AVANT or ep.startswith("static"):
                return None
            return redirect(url_for("ens_assistant"))
        if ep == "login" and request.method == "GET":
            return redirect(url_for("ens_portail", suivant=request.args.get("suivant", "")))
        if ep == "ens_assistant":
            return redirect(url_for("ens_portail"))
        return None

    @app.route("/enseignant/premier-lancement", methods=["GET", "POST"])
    def ens_assistant():
        if not config.enseignant() or configuree():
            abort(404)
        f = {}
        if request.method == "POST":
            f = lire(PROFIL + ECOLE + ("identifiant",))
            f["mdp"], f["confirmation"] = request.form.get("mdp", ""), request.form.get("confirmation", "")
            classes, err_c = lire_classes()
            err = valider(f, True) + err_c
            if not classes and not err_c:
                err.append("Indiquez au moins une classe (nom et niveau).")
            if q("SELECT 1 FROM utilisateurs WHERE lower(identifiant)=lower(?)", (f["identifiant"],), un=True):
                err.append("Cet identifiant existe déjà.")
            if err:
                for e in err[:6]:
                    flash(e, "danger")
                return render_template("ens_assistant.html", f=f, classes=classes, **listes()), 400
            nom_complet = f"{f['nom'].upper()} {f['prenoms']}"
            uid = ex("INSERT INTO utilisateurs (identifiant, nom, role, mdp_hash, doit_changer_mdp, actif, ecole_id) "
                     "VALUES (?,?,?,?,0,1,1)", (f["identifiant"], nom_complet, "enseignant", generate_password_hash(f["mdp"])))
            enregistrer_ecole(f)
            enregistrer_profil(f, uid)
            titulaire = ("Mme " if f["sexe"] == "F" else "M. ") + nom_complet
            for nom, niv in classes:
                creer_classe(nom, niv, uid, titulaire)
            # le compte « admin » de départ ne sert plus : désactivé, mot de passe aléatoire
            import secrets
            ex("UPDATE utilisateurs SET actif=0, mdp_hash=? WHERE identifiant='admin'",
               (generate_password_hash(secrets.token_urlsafe(24)),))
            ecrire_param("enseignant_configure", "1")
            session.clear()
            session["uid"] = uid
            g.user = q("SELECT * FROM utilisateurs WHERE id=?", (uid,), un=True)
            H.journal("enseignant_configure", f"{nom_complet} — {f['ecole_nom']} — {len(classes)} classe(s)")
            flash("Bienvenue ! Votre application est prête : ajoutez ou importez maintenant vos élèves.", "success")
            return redirect(url_for("ens_tableau"))
        return render_template("ens_assistant.html", f=f, classes=[], **listes())

    # ------------------------------------------------------------------ portail : connexion de l'enseignant
    @app.route("/enseignant", methods=["GET", "POST"])
    def ens_portail():
        if g.get("user") and g.user["role"] == "enseignant" and request.method == "GET":
            session["portail"] = "enseignant"
            return redirect(url_for("ens_tableau"))
        if request.method == "POST":
            u = q("SELECT * FROM utilisateurs WHERE identifiant=?", (request.form.get("identifiant", "").strip(),), un=True)
            if u and u["actif"] and check_password_hash(u["mdp_hash"], request.form.get("mdp", "")):
                if u["role"] != "enseignant":
                    flash("Cette application est réservée aux enseignants : les autres comptes se connectent à "
                          "l'application de l'école.", "danger")
                    return render_template("ens_portail.html"), 403
                session.pop("pid", None)
                session["uid"] = u["id"]
                session["portail"] = "enseignant"
                g.user = u
                H.journal("connexion", "portail enseignant")
                suivant = request.args.get("suivant", "")
                if suivant.startswith("/") and not suivant.startswith("//"):
                    return redirect(suivant)
                return redirect(url_for("ens_tableau"))
            flash("Identifiant ou mot de passe incorrect.", "danger")
        return render_template("ens_portail.html")

    @app.route("/enseignant/manifest.webmanifest")
    def ens_manifeste():
        nom = config.NOMS_APPLI["enseignant"] if config.enseignant() else config.NOM_PORTAIL_ENSEIGNANT
        m = {
            "name": f"{nom} – {config.ECOLE['nom']}", "short_name": nom.replace("SCOLARIS ", "") if len(nom) > 12 else nom,
            "description": "Application de l'enseignant : ma classe, emplois du temps, planifications, documents "
                           "officiels et certificats.",
            "lang": "fr", "id": "/enseignant", "start_url": "/enseignant?source=app", "scope": "/", "display": "standalone",
            "orientation": "any", "background_color": "#F4F6F9", "theme_color": "#00796B",
            "icons": [
                {"src": url_for("static", filename="icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
                {"src": url_for("static", filename="icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
                {"src": url_for("static", filename="icons/maskable-512.png"), "sizes": "512x512",
                 "type": "image/png", "purpose": "maskable"},
            ],
        }
        return Response(json.dumps(m, ensure_ascii=False), mimetype="application/manifest+json")

    # ------------------------------------------------------------------ tableau de bord de l'enseignant
    @app.route("/enseignant/tableau")
    @H.connexion_requise()
    def ens_tableau():
        exiger_enseignant()
        if not config.enseignant():
            session["portail"] = "enseignant"
        classes = []
        for c in H.classes_autorisees():
            n = q("SELECT COUNT(*) n, SUM(sexe='F') f FROM eleves WHERE classe_id=? AND statut='inscrit'", (c["id"],), un=True)
            classes.append(dict(c, effectif=n["n"] or 0, filles=n["f"] or 0,
                                cle=(c["niveau"] or "").lower().replace(" ", "")))
        fiches = mes_fiches()
        p = dict(fiches[0]) if fiches else None
        car = carriere_de(p["id"]) if p else {}
        return render_template("ens_tableau.html", classes=classes, p=p, car=car,
                               ecole=q("SELECT * FROM ecoles WHERE id=?", (H.eco(),), un=True),
                               application=config.enseignant())

    # ------------------------------------------------------------------ mon profil et mon école (application)
    @app.route("/enseignant/profil", methods=["GET", "POST"])
    @H.connexion_requise()
    def ens_profil():
        exiger_enseignant()
        if not config.enseignant():
            # dans l'application de l'école, la fiche est tenue par le directeur : fiche de carrière en consultation
            return redirect(url_for("carriere_moi_fiche"))
        v, pid = valeurs_profil()
        if request.method == "POST":
            f = lire(PROFIL + ECOLE)
            err = valider(f, False)
            if err:
                for e in err[:6]:
                    flash(e, "danger")
                return render_template("ens_profil.html", f=f, **listes()), 400
            enregistrer_ecole(f)
            enregistrer_profil(f, g.user["id"], pid)
            ex("UPDATE utilisateurs SET nom=? WHERE id=?", (f"{f['nom'].upper()} {f['prenoms']}", g.user["id"]))
            H.journal("enseignant_profil", f"{f['nom']} {f['prenoms']}")
            flash("Profil et école enregistrés.", "success")
            return redirect(url_for("ens_tableau"))
        return render_template("ens_profil.html", f=v, **listes())

    # ------------------------------------------------------------------ mes classes (application)
    @app.route("/enseignant/classes", methods=["GET", "POST"])
    @H.connexion_requise()
    def ens_classes():
        exiger_application()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "ajouter":
                nom = (request.form.get("nom") or "").strip()[:60]
                niv = request.form.get("niveau") or ""
                if not nom or niv not in NIVEAUX:
                    flash("Indiquez le nom et le niveau de la classe.", "danger")
                elif creer_classe(nom, niv, g.user["id"], g.user["nom"]) is None:
                    flash("Une classe porte déjà ce nom.", "danger")
                else:
                    H.journal("enseignant_classe", f"classe ajoutée : {nom} ({niv})")
                    flash(f"Classe {nom} ajoutée.", "success")
            elif action == "supprimer":
                cid = request.form.get("cid", type=int)
                if not cid or cid not in {c["id"] for c in H.classes_autorisees()}:
                    abort(403)
                if q("SELECT 1 FROM eleves WHERE classe_id=? LIMIT 1", (cid,), un=True):
                    flash("Cette classe a des élèves : retirez-les d'abord.", "danger")
                else:
                    ex("DELETE FROM affectations WHERE classe_id=?", (cid,))
                    ex("DELETE FROM classes WHERE id=?", (cid,))
                    H.journal("enseignant_classe", f"classe supprimée #{cid}")
                    flash("Classe supprimée.", "success")
            return redirect(url_for("ens_classes"))
        classes = [dict(c, effectif=q("SELECT COUNT(*) n FROM eleves WHERE classe_id=?", (c["id"],), un=True)["n"])
                   for c in H.classes_autorisees()]
        return render_template("ens_classes.html", classes=classes, NIVEAUX=NIVEAUX)

    # ------------------------------------------------------------------ mes certificats et documents officiels
    @app.route("/enseignant/certificats")
    @H.connexion_requise()
    def ens_certificats():
        exiger_enseignant()
        try:
            import m_docs_enseignant as MD
        except ImportError:
            abort(404)
        docs = [(k, d) for k, d in MD.DOCS.items() if d["famille"] == "cert_agent"]
        fiches = mes_fiches()
        return render_template("ens_certificats.html", docs=docs, fiches=fiches,
                               eleves_docs=[(k, d) for k, d in MD.DOCS.items() if d["famille"] == "cert_eleve"],
                               application=config.enseignant())
