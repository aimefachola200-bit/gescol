# -*- coding: utf-8 -*-
"""Ouverture des modules des écoles dans GESCOL Circonscription (CS) et GESCOL DDEMP — v1.6.

Dans les éditions « cs » et « ddemp », tous les modules des écoles (Scolarité, Évaluations, CEP, Cantine, Vie de
l'école, Données, Secrétariat, Personnel, Administration…) sont déjà chargés : ils travaillent sur « l'école
courante » (table ``ecoles``, ``g.ecole``). Ce module les ouvre à la CS / DDEMP :

1. Droits : ``app.peut()`` fait hériter aux rôles de juridiction les droits « école » du rôle équivalent
   (``EQUIV_ROLES_JUR`` : responsable → admin, chef_service → directeur, cp → directeur sauf finances,
   agent → secrétaire) ; les comptes « directeur » et « enseignant » existent aussi dans la CS / DDEMP.
2. École ouverte : chaque école de la juridiction (``jur_ecoles``, reçue par transmission ou saisie) peut être
   ouverte comme école locale : ``assurer_ecole_locale(jur_id)`` crée / retrouve la ligne ``ecoles`` liée par
   ``ecoles.jur_ecole_id`` (nom, statut public / privé, département, CS, zone, commune, directeur…).
   Inversement, une école créée dans Administration → Écoles est inscrite dans ``jur_ecoles`` (``H.jur_lier_ecole``).
   Page /juridiction/ecoles-modules : liste des écoles, bouton « Ouvrir cette école », modules disponibles.
   Sur les pages des modules d'école, l'identité de l'école ouverte (et non celle de la structure) alimente
   ``config.ECOLE`` (en-têtes, matricules) ; ``g.publique_ecole`` dit si l'école ouverte est publique.
3. Tableau de bord de l'école ouverte : /juridiction/ecole (mêmes indicateurs que l'accueil de GESCOL).
4. Examen blanc CS / DDEMP (/juridiction/cep-blanc) : une session regroupe les résultats de toutes les écoles ;
   import du canevas Excel de chaque école (même format que l'examen blanc de l'école : N° table, Nom, Prénoms,
   Sexe (M/F), École de provenance, puis une colonne par matière) ou saisie manuelle par école ; règle du primaire
   (m_cep) : MAÎTRISE = au moins « seuil » matières à 10/20 (2/3 des matières par défaut), la moyenne ne sert
   qu'au rang. Résultats par école, par zone, par CS (DDEMP), classement des écoles ; PDF et Excel.
   Synthèse des examens par niveau (/juridiction/cep-blanc/synthese) : examen blanc (par niveau et session)
   comparé au CEP officiel (a_cep : ``H.jur_cep_stats``), par zone / CS et total.
5. Synthèse de l'évaluation niveau CS / DDEMP (/juridiction/synthese-evaluation) : agrège, pour un type et un
   numéro d'évaluation, les synthèses École / UP / CS enregistrées dans chaque école locale (m_synthese :
   ``calculer_fiche``, ``synthese_niveaux``, ``analyse``) par zone pédagogique et au total ; PDF et Excel.

Tables : ``jur_cep_blanc_sessions`` (id, annee, numero, nom, date, niveau, matieres JSON, seuil, cree_le) et
``jur_cep_blanc_resultats`` (id, session_id, ecole_id → jur_ecoles, zone, numero_table, nom, prenoms, sexe,
notes JSON {matière: note}, total, moyenne, admis 0/1, maj). Colonne ajoutée : ``ecoles.jur_ecole_id``.
"""
import json
import re
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, session, url_for

import config
import evaluations_core as EC
import m_cep as MC
import m_juridiction as J
import m_synthese as MS

SCHEMA = """
CREATE TABLE IF NOT EXISTS jur_cep_blanc_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    annee TEXT NOT NULL, numero INTEGER DEFAULT 1, nom TEXT, date TEXT, niveau TEXT DEFAULT 'CM2',
    matieres TEXT, seuil INTEGER, cree_le TEXT);
CREATE TABLE IF NOT EXISTS jur_cep_blanc_resultats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES jur_cep_blanc_sessions(id) ON DELETE CASCADE,
    ecole_id INTEGER NOT NULL,
    zone TEXT, numero_table TEXT, nom TEXT NOT NULL, prenoms TEXT, sexe TEXT,
    notes TEXT DEFAULT '{}', total REAL, moyenne REAL, admis INTEGER, maj TEXT);
CREATE INDEX IF NOT EXISTS i_jur_cbr_session ON jur_cep_blanc_resultats(session_id, ecole_id);
"""

# pages communes (structure) : tout autre endpoint hors « jur_* » est une page de module d'école
ENDPOINTS_COMMUNS = {
    "accueil", "login", "logout", "mon_compte", "static", "verifier", "utilisateurs", "journal_page", "parametres",
    "image_ecole", "sauvegarde", "en_ligne_page", "demandes_ecoles", "demandes_ecoles_csv", "reglages_messages",
    "reglages_paiement_en_ligne", "affectations", "manifeste", "service_worker", "hors_ligne", "installer",
    "referentiel_js", "rejoindre", "signature_png", "signature_enregistrer", "cachet_svg", "ecoles", "ecole_form",
    "ecole_choisir", "ecole_basculer", "ecole_supprimer", "ecole_logo", "interdit", "introuvable",
}
# modules proposés sur la page « écoles et modules » : (endpoint, libellé, droit)
MODULES_ECOLE = [
    ("jur_ecole_accueil", "Tableau de bord de l'école", None),
    ("eleves", "Élèves et inscriptions", None), ("classes", "Classes", None),
    ("appel_accueil", "Registre d'appel", "appel"), ("registre_accueil", "Registre de présence", "registre"),
    ("eval_accueil", "Évaluations (saisie des notes)", "evaluations"), ("eval_statistiques", "Statistiques", "evaluations"),
    ("eval_analyse", "Analyse et rapport", "evaluations"), ("bilan_annuel", "Bilan annuel et décision", "evaluations"),
    ("epreuves_accueil", "Comité d'évaluation, épreuves et grilles", "epreuves"),
    ("synthese_accueil", "Synthèse École / UP / CS", "synthese"), ("notes_accueil", "Notes par période (bulletins)", "notes"),
    ("cep_accueil", "Fiches d'inscription au CEP", "cep"), ("carte_editeur", "Carte scolaire du candidat", "cep"),
    ("cep_blanc_accueil", "Examen blanc CEP (école)", "cep"),
    ("cantine_accueil", "Cantine (paiements)", "cantine"), ("stock_accueil", "Vivres et stock", "stock"),
    ("recensement_accueil", "Carte d'identité de l'école (recensement, rapports)", "recensement"),
    ("rapports_accueil", "Rapports de rentrée / fin d'année", "recensement"),
    ("maitre_semaine_accueil", "Maître de semaine", "maitre_semaine"), ("visites_accueil", "Visites de classe et d'école", "visites"),
    ("patrimoine_accueil", "Ressources et patrimoine", "patrimoine"),
    ("docs_enseignant_accueil", "Documents de l'enseignant", "docs_enseignant"),
    ("synoptique_accueil", "Tableau synoptique", "synoptique"),
    ("personnel", "Personnel", "paie"), ("carriere_accueil", "Gestion de carrière", "carriere"),
    ("depenses_accueil", "Dépenses", "depenses"), ("recettes_accueil", "Subventions et recettes", "depenses"),
    ("paiements", "Paiements de scolarité", "paiements"), ("tresorerie", "Trésorerie", "tresorerie"),
    ("donnees_accueil", "Données : import / export", "donnees"), ("educmaster_accueil", "EducMaster", "donnees"),
    ("conversion_pdf", "Conversion PDF → Excel / CSV", "donnees"),
    ("courrier", "Secrétariat : courrier", "secretariat"), ("archives", "Secrétariat : archives", "secretariat"),
    ("communication", "Parents : messages et WhatsApp", "communication"),
]
ORDRES_TYPE = {"EP": "Primaire", "EM": "Maternelle", "EE": "Maternelle"}
MAX_LIGNES_SAISIE = 300


def sigle_de(nom):
    mots = [m for m in re.split(r"[^A-Za-zÀ-ÿ0-9]+", nom or "") if m]
    s = "".join(m[0] for m in mots).upper()
    return (s or "ECO")[:8]


def fr(v, dec=2):
    return MS._fr(v, dec)


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    def garde():
        if not config.juridiction():
            abort(404)

    def ddemp():
        return config.EDITION == "ddemp"

    def nom_niveau():
        return "DDEMP" if ddemp() else "CS"

    # ================================================================ 2. écoles locales ↔ écoles de la juridiction
    def ecoles_locales():
        return q("SELECT * FROM ecoles WHERE actif=1 ORDER BY nom")

    def locales_par_jur():
        """{jur_ecole_id: ligne ecoles} pour les écoles locales liées."""
        return {r["jur_ecole_id"]: r for r in q("SELECT * FROM ecoles WHERE jur_ecole_id IS NOT NULL")}

    def _ecole1_vierge():
        """L'école n° 1 créée par défaut, encore jamais utilisée : on la réutilise pour la première école ouverte."""
        e = q("SELECT * FROM ecoles WHERE id=1", un=True)
        if not e or e["jur_ecole_id"] or e["nom"] != config.DEFAUTS["ecole_nom"]:
            return None
        if q("SELECT 1 FROM classes WHERE ecole_id=1 LIMIT 1", un=True):
            return None
        return e

    def valeurs_depuis_jur(je):
        c = H.jur_cs(je["cs_id"]) if je["cs_id"] else None
        s = H.jur_structure() or {}
        return {
            "nom": je["nom"], "sigle": sigle_de(je["nom"]),
            "statut": "Publique" if je["secteur"] == "public" else "Privée", "ordre": ORDRES_TYPE.get(je["type"], "Primaire"),
            "departement": (c["departement"] if c else "") or s.get("departement") or "",
            "cs": (c["nom"] if c else "") or s.get("cs") or "", "zone": je["zone_nom"] or "",
            "commune": je["commune"] or "", "ville": je["localite"] or je["commune"] or "", "adresse": je["adresse"] or "",
            "telephone": je["telephone"] or "", "email": je["email"] or "",
            "directeur_titre": je["directeur_titre"] or "Directeur", "directeur_nom": je["directeur_nom"] or "",
            "directeur_tel": je["directeur_tel"] or "",
            "ccs_titre": (c["ccs_titre"] if c and c["ccs_titre"] else "") or "Le CCS",
            "ccs_nom": (c["ccs_nom"] if c and c["ccs_nom"] else "") or (s.get("responsable_nom") if not ddemp() else "") or "",
        }

    def assurer_ecole_locale(jid):
        """Crée ou retrouve l'école locale (table ecoles) liée à l'école jur_ecoles n° jid. Renvoie son id."""
        je = H.jur_ecole(jid)
        if not je:
            abort(404)
        r = q("SELECT * FROM ecoles WHERE jur_ecole_id=?", (jid,), un=True)
        if r:
            if not r["actif"]:
                ex("UPDATE ecoles SET actif=1 WHERE id=?", (r["id"],))
            return r["id"]
        v = valeurs_depuis_jur(je)
        cols = list(v)
        e1 = _ecole1_vierge()
        if e1:
            ex("UPDATE ecoles SET " + ", ".join(f"{k}=?" for k in cols) + ", jur_ecole_id=?, actif=1 WHERE id=1",
               [v[k] for k in cols] + [jid])
            eid = 1
        else:
            eid = ex(f"INSERT INTO ecoles ({', '.join(cols)}, jur_ecole_id, actif, cree_le) VALUES "
                     f"({', '.join('?' * len(cols))}, ?, 1, ?)", [v[k] for k in cols] + [jid, H.maintenant()])
        H.journal("jur_ecole_ouverte", f"{je['nom']} → école locale n° {eid}")
        return eid

    def jur_lier_ecole(eid):
        """École créée dans Administration → Écoles : l'inscrit dans jur_ecoles (code généré, CS courante, zone)."""
        e = q("SELECT * FROM ecoles WHERE id=?", (eid,), un=True)
        if not e or e["jur_ecole_id"]:
            return e["jur_ecole_id"] if e else None
        s = H.jur_structure()
        if not s:
            return None
        if ddemp():
            c = J._trouver_cs(s["departement"], e["cs"] or "", creer=bool(e["cs"]))
        else:
            c = H.jur_cs_courante()
        cs_id = c["id"] if c else None
        zid = J._trouver_zone(cs_id, e["zone"] or "") if cs_id else None
        typ = "EM" if (e["ordre"] or "").startswith("Maternelle") and "primaire" not in (e["ordre"] or "").lower() else "EP"
        ident = {"code": J.nouveau_code(e["nom"], c["nom"] if c else ""), "nom": e["nom"], "type": typ,
                 "secteur": "public" if (e["statut"] or "") == "Publique" else "prive",
                 "commune": e["commune"] or "", "arrondissement": "", "localite": e["ville"] or "", "adresse": e["adresse"] or "",
                 "telephone": e["telephone"] or "", "email": e["email"] or "",
                 "directeur_titre": e["directeur_titre"] or "Directeur", "directeur_nom": e["directeur_nom"] or "",
                 "directeur_tel": e["directeur_tel"] or "", "annee_creation": ""}
        jid, _ = H.jur_enregistrer_ecole(ident, cs_id, zid)
        ex("UPDATE ecoles SET jur_ecole_id=? WHERE id=?", (jid, eid))
        H.journal("jur_ecole_liee", f"{e['nom']} (jur n° {jid})")
        return jid

    H.assurer_ecole_locale = assurer_ecole_locale
    H.jur_lier_ecole = jur_lier_ecole
    H.ecoles_locales = ecoles_locales

    def publique_ecole():
        e = g.get("ecole")
        return bool(e) and (e["statut"] or "") == "Publique"

    @app.before_request
    def integration_contexte():
        """Pages des modules d'école : l'identité de l'école ouverte remplace celle de la structure."""
        if not config.juridiction():
            return
        ep = request.endpoint or ""
        g.page_ecole = bool(ep) and not ep.startswith("jur_") and ep not in ENDPOINTS_COMMUNS
        g.publique_ecole = publique_ecole()
        if g.page_ecole and g.get("ecole") and getattr(H, "appliquer_identite_ecole", None):
            H.appliquer_identite_ecole(g.ecole)
        # rôle de juridiction → rôle d'école équivalent pour les modules d'école (dont les contrôles « directs »
        # de rôle : tableau du directeur, visa du maître de semaine, configuration de la cantine…)
        if g.page_ecole and g.get("user") and g.user["role"] in H.EQUIV_ROLES_JUR:
            g.role_reel = g.user["role"]
            u = dict(g.user)
            u["role"] = H.EQUIV_ROLES_JUR[g.role_reel]
            g.user = u

    @app.context_processor
    def ctx_integration():
        if not config.juridiction():
            return {}
        return dict(PAGE_ECOLE=g.get("page_ecole", False), PUBLIQUE_ECOLE=g.get("publique_ecole", False))

    def structure_infos():
        s = H.jur_structure() or {}
        return s

    def signature_responsable():
        s = structure_infos()
        titre = s.get("responsable_titre") or ("Le Directeur Départemental" if ddemp() else "Le Chef de la Circonscription Scolaire")
        return [(titre.upper(), s.get("responsable_nom") or "", H.pdfs.image_data_url(H.signature("jur:structure:responsable")), False)]

    def infos_haut():
        s = structure_infos()
        return [("DDEMP", s.get("departement") or "")] + ([] if ddemp() else [("CS", s.get("cs") or "")])

    # ---------------------------------------------------------------- page « écoles et modules »
    @app.route("/juridiction/ecoles-modules")
    @H.connexion_requise()
    def jur_ecoles_modules():
        garde()
        f = request.args
        cs_id = int(f.get("cs") or 0) or None
        liste = H.jur_ecoles(cs_id=cs_id, recherche=f.get("q") or None)
        locales = locales_par_jur()
        comptes = {r["ecole_id"]: r for r in q("""SELECT c.ecole_id, COUNT(DISTINCT c.id) nb_classes, COUNT(e.id) nb_eleves
                                                 FROM classes c LEFT JOIN eleves e ON e.classe_id=c.id AND e.statut='inscrit'
                                                 GROUP BY c.ecole_id""")}
        lignes = []
        for je in liste:
            loc = locales.get(je["id"])
            cpt = comptes.get(loc["id"]) if loc else None
            lignes.append({"j": je, "loc": loc, "nb_classes": cpt["nb_classes"] if cpt else 0,
                           "nb_eleves": cpt["nb_eleves"] if cpt else 0,
                           "courante": bool(loc and g.get("ecole") and g.ecole["id"] == loc["id"])})
        non_liees = [e for e in ecoles_locales() if not e["jur_ecole_id"]]
        modules = [(ep, lib) for ep, lib, droit in MODULES_ECOLE
                   if ep in app.view_functions and (droit is None or H.peut(droit))]
        return render_template("jur_ecoles_modules.html", lignes=lignes, non_liees=non_liees, modules=modules,
                               cs=H.jur_cs_liste(), f=f, nb_liees=len(locales))

    @app.route("/juridiction/ecoles-modules/<int:jid>/ouvrir", methods=["POST"])
    @H.connexion_requise("ecoles")
    def jur_ecole_ouvrir(jid):
        garde()
        eid = assurer_ecole_locale(jid)
        if g.user["ecole_id"] and g.user["ecole_id"] != eid and g.user["role"] not in ("admin", "fondateur", "responsable"):
            abort(403)
        session["ecole_id"] = eid
        suivant = request.form.get("suivant", "")
        flash(f"École ouverte : {H.jur_ecole(jid)['nom']}.", "success")
        return redirect(suivant if suivant.startswith("/") and not suivant.startswith("//") else url_for("jur_ecole_accueil"))

    @app.route("/juridiction/ecoles-modules/tout-ouvrir", methods=["POST"])
    @H.connexion_requise("parametres")
    def jur_ecoles_tout_ouvrir():
        garde()
        n = 0
        deja = locales_par_jur()
        for je in H.jur_ecoles():
            if je["id"] not in deja:
                assurer_ecole_locale(je["id"])
                n += 1
        flash(f"{n} école(s) de la juridiction ajoutée(s) aux écoles locales.", "success")
        return redirect(url_for("jur_ecoles_modules"))

    @app.route("/juridiction/ecoles-modules/lier/<int:eid>", methods=["POST"])
    @H.connexion_requise("parametres")
    def jur_ecole_lier(eid):
        garde()
        jid = jur_lier_ecole(eid)
        flash("École inscrite dans la liste de la juridiction." if jid else "Configurez d'abord la structure.", "success" if jid else "danger")
        return redirect(url_for("jur_ecoles_modules"))

    # ================================================================ 3. tableau de bord de l'école ouverte
    @app.route("/juridiction/ecole")
    @H.connexion_requise()
    def jur_ecole_accueil():
        garde()
        if not g.get("ecole"):
            flash("Ouvrez d'abord une école.", "warning")
            return redirect(url_for("jur_ecoles_modules"))
        stats, par_classe, derniers = H.stats_accueil(H.eco(), publique=publique_ecole())
        return render_template("accueil.html", s=stats, par_classe=par_classe, derniers=derniers, PUBLIQUE=publique_ecole())

    # ================================================================ 4. examen blanc CS / DDEMP
    def matieres_defaut():
        rows = q("SELECT nom FROM matieres WHERE cycle='primaire' AND actif=1 AND mode_calcul='standard' ORDER BY ordre, nom")
        return [r["nom"] for r in rows][:MC.MAX_MATIERES] or ["Français", "Mathématiques", "Éducation scientifique",
                                                              "Éducation sociale"]

    def session_ou_404(sid):
        s = q("SELECT * FROM jur_cep_blanc_sessions WHERE id=?", (sid,), un=True)
        if not s:
            abort(404)
        d = MC.session_dict(s)
        d["nom"] = d.get("nom") or f"Examen blanc {nom_niveau()} N° {d['numero']}"
        return d

    def sessions_liste(annee=None):
        sql = "SELECT * FROM jur_cep_blanc_sessions"
        args = ()
        if annee:
            sql += " WHERE annee=?"
            args = (annee,)
        out = []
        for s in q(sql + " ORDER BY annee DESC, numero DESC, id DESC", args):
            d = MC.session_dict(s)
            d["nom"] = d.get("nom") or f"Examen blanc {nom_niveau()} N° {d['numero']}"
            d["nb"] = q("SELECT COUNT(*) n FROM jur_cep_blanc_resultats WHERE session_id=?", (s["id"],), un=True)["n"]
            d["nb_ecoles"] = q("SELECT COUNT(DISTINCT ecole_id) n FROM jur_cep_blanc_resultats WHERE session_id=?", (s["id"],), un=True)["n"]
            out.append(d)
        return out

    def candidats_session(s, ecole_id=None):
        """Candidats (dict : colonnes + ecole, zone_id, zone_nom, cs_id, cs_nom) de la session."""
        sql = """SELECT r.*, e.nom ecole_nom, e.code ecole_code, e.zone_id, e.cs_id, e.secteur, z.nom zone_nom, c.nom cs_nom
                 FROM jur_cep_blanc_resultats r JOIN jur_ecoles e ON e.id=r.ecole_id
                 LEFT JOIN jur_zones z ON z.id=e.zone_id LEFT JOIN jur_cs c ON c.id=e.cs_id WHERE r.session_id=?"""
        args = [s["id"]]
        if ecole_id:
            sql += " AND r.ecole_id=?"
            args.append(ecole_id)
        return [dict(r, ecole=r["ecole_nom"]) for r in q(sql + " ORDER BY c.numero, c.nom, z.ordre, z.nom, e.nom, r.nom, r.prenoms", args)]

    def resultats(s, ecole_id=None):
        return MC.resultats_blanc(s, candidats_session(s, ecole_id))

    def agreger(lignes):
        st = MC.stats_blanc(lignes)
        moys = [l["moyenne"] for l in lignes if l["moyenne"] is not None]
        return {"inscrits": st["inscrits"], "presents": st["presents"], "maitrise": st["maitrise"], "taux": st["taux"],
                "moyenne": round(sum(moys) / len(moys), 2) if moys else None}

    def tableau_ecoles(s, lignes):
        """Lignes d'école (triées CS → zone → école) + sous-totaux de zone, (DDEMP) totaux de CS, total et classement."""
        par_ecole = {}
        for l in lignes:
            c = l["c"]
            par_ecole.setdefault(c["ecole_id"], {"ecole_id": c["ecole_id"], "nom": c["ecole"], "code": c["ecole_code"],
                                                 "secteur": c["secteur"], "cs_id": c["cs_id"], "cs_nom": c["cs_nom"] or "",
                                                 "zone_id": c["zone_id"], "zone_nom": c["zone_nom"] or "Sans zone pédagogique",
                                                 "lignes": []})["lignes"].append(l)
        ecoles = []
        for d in par_ecole.values():
            d.update(agreger(d["lignes"]))
            ecoles.append(d)
        # classement par taux de maîtrise puis moyenne puis présents
        cls = sorted([e for e in ecoles if e["presents"]["T"]], key=lambda e: (-e["taux"]["T"], -(e["moyenne"] or 0), -e["presents"]["T"]))
        rang = 0
        prec = None
        for i, e in enumerate(cls, 1):
            cle = (e["taux"]["T"], e["moyenne"])
            if cle != prec:
                rang = i
            prec = cle
            e["rang"] = rang
        for e in ecoles:
            e.setdefault("rang", None)
        rangees, zone_cour, cs_cour = [], None, None
        zones, css = {}, {}
        for e in ecoles:
            zones.setdefault((e["cs_id"], e["zone_id"]), {"cs_nom": e["cs_nom"], "zone_nom": e["zone_nom"], "lignes": []})["lignes"] += e["lignes"]
            css.setdefault(e["cs_id"], {"cs_nom": e["cs_nom"] or "Sans circonscription", "lignes": []})["lignes"] += e["lignes"]
        for k in zones:
            zones[k].update(agreger(zones[k]["lignes"]), nb_ecoles=sum(1 for e in ecoles if (e["cs_id"], e["zone_id"]) == k))
        for k in css:
            css[k].update(agreger(css[k]["lignes"]), nb_ecoles=sum(1 for e in ecoles if e["cs_id"] == k))

        def fermer_zone():
            if zone_cour is not None:
                z = zones[zone_cour]
                rangees.append({"genre": "zone", "libelle": f"Sous-total {z['zone_nom']}" + (f" – CS {z['cs_nom']}" if ddemp() else ""), "d": z})

        def fermer_cs():
            if ddemp() and cs_cour is not None:
                rangees.append({"genre": "cs", "libelle": f"Total CS {css[cs_cour]['cs_nom']}", "d": css[cs_cour]})

        n = 0
        for e in ecoles:
            k = (e["cs_id"], e["zone_id"])
            if k != zone_cour:
                fermer_zone()
                if e["cs_id"] != cs_cour:
                    fermer_cs()
                    cs_cour = e["cs_id"]
                zone_cour = k
            n += 1
            rangees.append({"genre": "ecole", "n": n, "libelle": e["nom"], "d": e})
        fermer_zone()
        fermer_cs()
        glob = agreger(lignes)
        glob["nb_ecoles"] = len(ecoles)
        if ecoles:
            rangees.append({"genre": "total", "libelle": "TOTAL GÉNÉRAL", "d": glob})
        return {"ecoles": ecoles, "rangees": rangees, "zones": zones, "cs": css, "global": glob,
                "classement": cls}

    def ecoles_juridiction():
        return H.jur_ecoles(type_="EP")

    @app.route("/juridiction/cep-blanc")
    @H.connexion_requise("cep")
    def jur_cep_blanc():
        garde()
        return render_template("jur_cep_blanc.html", sessions=sessions_liste(), matieres=matieres_defaut(),
                               annee=config.ANNEE_ACTIVE)

    def lire_entete(f, s=None):
        err = []
        mats = []
        for m in (f.get("matieres") or "").splitlines():
            m = MC.txt(m, 60)
            if m and m.lower() not in [x.lower() for x in mats]:
                mats.append(m)
        if not mats:
            mats = s["mats"] if s else matieres_defaut()
            if s:
                err.append("Indiquez au moins une matière (une par ligne).")
        mats = mats[:MC.MAX_MATIERES]
        seuil = (f.get("seuil") or "").strip()
        if seuil:
            if not seuil.isdigit() or not 1 <= int(seuil) <= len(mats):
                err.append(f"Seuil de maîtrise : nombre entier entre 1 et {len(mats)} (vide = 2/3 des matières).")
                seuil = s["seuil"] if s else None
            else:
                seuil = int(seuil)
        else:
            seuil = None
        an = MC.txt(f.get("annee"), 9)
        if not re.match(r"^\d{4}-\d{4}$", an):
            an = (s["annee"] if s else None) or config.ANNEE_ACTIVE
        dt = (f.get("date") or "").strip()
        if dt and not MC.lire_date(dt):
            err.append("Date invalide.")
            dt = s["date"] if s else ""
        numero = f.get("numero", type=int) or (s["numero"] if s else 1) or 1
        niveau = MC.txt(f.get("niveau"), 20) or (s["niveau"] if s else "CM2") or "CM2"
        return {"annee": an, "numero": max(1, min(numero, 99)), "nom": MC.txt(f.get("nom"), 120), "date": dt,
                "niveau": niveau, "matieres": mats, "seuil": seuil}, err

    @app.route("/juridiction/cep-blanc/nouvelle", methods=["POST"])
    @H.connexion_requise("jur_cep")
    def jur_cep_blanc_nouvelle():
        garde()
        d, err = lire_entete(request.form)
        for m in err:
            flash(m, "danger")
        prec = q("SELECT numero FROM jur_cep_blanc_sessions WHERE annee=? ORDER BY numero DESC LIMIT 1", (d["annee"],), un=True)
        if not request.form.get("numero") and prec:
            d["numero"] = min(99, (prec["numero"] or 0) + 1)
        sid = ex("INSERT INTO jur_cep_blanc_sessions (annee, numero, nom, date, niveau, matieres, seuil, cree_le) VALUES (?,?,?,?,?,?,?,?)",
                 (d["annee"], d["numero"], d["nom"] or f"Examen blanc {nom_niveau()} N° {d['numero']}", d["date"] or date.today().isoformat(),
                  d["niveau"], json.dumps(d["matieres"], ensure_ascii=False), d["seuil"], H.maintenant()))
        H.journal("jur_cep_blanc_session", f"N° {d['numero']} ({d['annee']})")
        flash(f"Examen blanc {nom_niveau()} N° {d['numero']} créé : importez le canevas de chaque école ou saisissez les candidats.", "success")
        return redirect(url_for("jur_cep_blanc_session", sid=sid))

    @app.route("/juridiction/cep-blanc/<int:sid>/entete", methods=["POST"])
    @H.connexion_requise("jur_cep")
    def jur_cep_blanc_entete(sid):
        garde()
        s = session_ou_404(sid)
        d, err = lire_entete(request.form, s)
        for m in err:
            flash(m, "danger")
        anciennes = s["mats"]
        if anciennes != d["matieres"] and len(anciennes) == len(d["matieres"]):
            corresp = dict(zip(anciennes, d["matieres"]))
            for r in q("SELECT id, notes FROM jur_cep_blanc_resultats WHERE session_id=?", (sid,)):
                try:
                    n = json.loads(r["notes"] or "{}")
                except ValueError:
                    n = {}
                ex("UPDATE jur_cep_blanc_resultats SET notes=? WHERE id=?",
                   (json.dumps({corresp.get(k, k): x for k, x in n.items()}, ensure_ascii=False), r["id"]))
        ex("UPDATE jur_cep_blanc_sessions SET annee=?, numero=?, nom=?, date=?, niveau=?, matieres=?, seuil=? WHERE id=?",
           (d["annee"], d["numero"], d["nom"] or s["nom"], d["date"], d["niveau"], json.dumps(d["matieres"], ensure_ascii=False), d["seuil"], sid))
        recalculer(session_ou_404(sid))
        flash("En-tête de l'examen blanc enregistré.", "success")
        return redirect(url_for("jur_cep_blanc_session", sid=sid))

    def recalculer(s, ecole_id=None):
        """Met à jour total / moyenne / admis enregistrés (pour les exports et les statistiques)."""
        for l in resultats(s, ecole_id):
            ex("UPDATE jur_cep_blanc_resultats SET total=?, moyenne=?, admis=?, zone=? WHERE id=?",
               (l["total"], l["moyenne"], None if l["maitrise"] is None else int(l["maitrise"]), l["c"]["zone_nom"] or "", l["c"]["id"]))

    @app.route("/juridiction/cep-blanc/<int:sid>")
    @H.connexion_requise("cep")
    def jur_cep_blanc_session(sid):
        garde()
        s = session_ou_404(sid)
        vue = request.args.get("vue") or "resultats"
        jid = request.args.get("ecole", type=int)
        if vue not in ("resultats", "candidats", "saisie", "import"):
            vue = "resultats"
        ecole = H.jur_ecole(jid) if jid else None
        if jid and not ecole:
            abort(404)
        lignes = resultats(s)
        tab = tableau_ecoles(s, lignes)
        export = request.args.get("export")
        if export in ("pdf", "xlsx"):
            return exporter_session(s, lignes, tab, vue, ecole, export)
        tri = request.args.get("tri", "merite")
        cands = MC.trier_blanc([l for l in lignes if not jid or l["c"]["ecole_id"] == jid], tri)
        saisie = []
        if vue == "saisie" and ecole:
            saisie = MC.trier_blanc([l for l in lignes if l["c"]["ecole_id"] == jid], "nom")
        return render_template("jur_cep_blanc_session.html", s=s, vue=vue, ecole=ecole, tab=tab, cands=cands, tri=tri,
                               saisie=saisie, ecoles=ecoles_juridiction(), st=MC.stats_blanc(lignes), fr=fr,
                               autres=sessions_liste(), nb_vides=8 if saisie else 15)

    @app.route("/juridiction/cep-blanc/<int:sid>/supprimer", methods=["POST"])
    @H.connexion_requise("jur_cep")
    def jur_cep_blanc_supprimer(sid):
        garde()
        s = session_ou_404(sid)
        ex("DELETE FROM jur_cep_blanc_resultats WHERE session_id=?", (sid,))
        ex("DELETE FROM jur_cep_blanc_sessions WHERE id=?", (sid,))
        H.journal("jur_cep_blanc_supprime", f"N° {s['numero']} ({s['annee']})")
        flash(f"Examen blanc N° {s['numero']} supprimé.", "success")
        return redirect(url_for("jur_cep_blanc"))

    @app.route("/juridiction/cep-blanc/<int:sid>/canevas.xlsx")
    @H.connexion_requise("cep")
    def jur_cep_blanc_canevas(sid):
        """Même format que le canevas de l'examen blanc de l'école (m_cep) : une colonne par matière."""
        garde()
        s = session_ou_404(sid)
        jid = request.args.get("ecole", type=int)
        ecole = H.jur_ecole(jid) if jid else None
        entetes = ["N° table", "Nom", "Prénoms", "Sexe (M/F)", "École de provenance"] + s["mats"]
        lignes = []
        if ecole:   # candidats déjà enregistrés pour cette école (pour compléter les notes)
            for l in MC.trier_blanc(resultats(s, jid), "nom"):
                c = l["c"]
                lignes.append([c["numero_table"] or "", c["nom"], c["prenoms"] or "", c["sexe"] or "", c["ecole"]]
                              + [v if v is not None else "" for v in l["notes"]])
        nom = f"canevas_examen_blanc_{nom_niveau()}_{s['numero']}" + (f"_{H.xlsx.normaliser(ecole['nom']).replace(' ', '_')}" if ecole else "")
        return H.xlsx.reponse_xlsx(nom + ".xlsx", entetes, lignes, titre="Candidats",
                                   titre_haut=[f"EXAMEN BLANC {nom_niveau()} N° {s['numero']} – {s['annee']} – {s['nom']}"
                                               + (f" – École : {ecole['nom']}" if ecole else ""),
                                               "Une ligne par candidat ; les notes (0 à 20) sont facultatives. "
                                               "Indiquez le nom exact de l'école dans « École de provenance »."])

    def trouver_ecole_jur(nom_ou_code, index):
        """École de la juridiction d'après son code ou son nom ; None si inconnue, "ambigu" si plusieurs écoles
        portent ce nom (DDEMP : même village dans deux circonscriptions)."""
        n = H.jur_norm(nom_ou_code)
        if not n or n not in index:
            return None
        lst = index[n]
        return lst[0] if len(lst) == 1 else "ambigu"

    def index_ecoles():
        idx = {}
        for e in H.jur_ecoles():
            idx.setdefault(H.jur_norm(e["code"]), []).append(e)
            if H.jur_norm(e["nom"]) != H.jur_norm(e["code"]):
                idx.setdefault(H.jur_norm(e["nom"]), []).append(e)
        return idx

    @app.route("/juridiction/cep-blanc/<int:sid>/importer", methods=["POST"])
    @H.connexion_requise("jur_cep")
    def jur_cep_blanc_importer(sid):
        """Import du canevas Excel (ou CSV) d'une école : colonnes N° table, Nom, Prénoms, Sexe, École de provenance,
        matières. L'école est celle choisie dans le formulaire, sinon celle de la colonne « École de provenance »."""
        garde()
        s = session_ou_404(sid)
        jid = request.form.get("ecole", type=int)
        ecole = H.jur_ecole(jid) if jid else None
        retour = redirect(url_for("jur_cep_blanc_session", sid=sid, vue="import"))
        fich = request.files.get("fichier")
        if not fich or not fich.filename:
            flash("Choisissez un fichier Excel (.xlsx) ou CSV.", "warning")
            return retour
        if not fich.filename.lower().endswith((".xlsx", ".xlsm", ".csv", ".txt")):
            flash("Format non reconnu : utilisez un fichier .xlsx ou .csv.", "danger")
            return retour
        X = H.xlsx
        try:
            ent, lignes = X.lire_tableau(fich, ("nom", "noms", "nom et prenoms"))
        except (X.ExcelIndisponible, ValueError) as e:
            flash(str(e), "danger")
            return retour
        i_tab = X.colonne(ent, "n table", "n° table", "numero de table", "num table", "table", "n de table")
        i_nom = X.colonne(ent, "nom", "noms", "nom de famille")
        i_pre = X.colonne(ent, "prenoms", "prénom", "prenom")
        i_nomp = X.colonne(ent, "nom et prenoms", "nom et prénom", "nom prenoms")
        i_sexe = X.colonne(ent, "sexe", "sexe m f", "genre")
        i_eco = X.colonne(ent, "ecole de provenance", "ecole", "etablissement", "école")
        if i_nomp is not None and i_pre is None:
            i_nom = i_nomp
        if i_nom is None:
            flash("Colonne « Nom » introuvable. Utilisez le canevas Excel proposé.", "danger")
            return retour
        norm_ent = [X.normaliser(h) for h in ent]
        i_mats = {}
        for m in s["mats"]:
            nm = X.normaliser(m)
            for j, h in enumerate(norm_ent):
                if h and h == nm and j not in (i_tab, i_nom, i_pre, i_sexe, i_eco):
                    i_mats[m] = j
        idx = index_ecoles()
        existants = {(c["ecole_id"], X.normaliser(c["nom"]), X.normaliser(c["prenoms"])): c for c in candidats_session(s)}
        crees = maj = 0
        erreurs, inconnues = [], set()
        for n, l in enumerate(lignes, 2):
            nom, pre = X.valeur(l, i_nom), X.valeur(l, i_pre) if i_pre is not None else ""
            if i_pre is None and " " in str(nom or ""):
                nom, pre = str(nom).split(" ", 1)
            nom = MC.txt(nom, 80).upper()
            if not nom:
                continue
            e = ecole
            if e is None:
                brut_eco = str(X.valeur(l, i_eco) if i_eco is not None else "") or ""
                e = trouver_ecole_jur(brut_eco, idx)
                if e is None or e == "ambigu":
                    inconnues.add((brut_eco or "(vide)") + (" (plusieurs écoles portent ce nom)" if e == "ambigu" else ""))
                    continue
            notes = {}
            for m, j in i_mats.items():
                try:
                    v = X.note(X.valeur(l, j))
                except ValueError:
                    erreurs.append(f"Ligne {n} ({nom}) : note de {m} invalide — ignorée.")
                    continue
                if v is not None:
                    notes[m] = v
            table = MC.txt(X.valeur(l, i_tab), 20) if i_tab is not None else ""
            sexe = X.sexe(X.valeur(l, i_sexe)) if i_sexe is not None else ""
            cle = (e["id"], X.normaliser(nom), X.normaliser(pre))
            c = existants.get(cle)
            if c:
                try:
                    anciennes = json.loads(c["notes"] or "{}")
                except ValueError:
                    anciennes = {}
                anciennes.update(notes)
                ex("""UPDATE jur_cep_blanc_resultats SET numero_table=COALESCE(NULLIF(?,''), numero_table),
                      sexe=COALESCE(NULLIF(?,''), sexe), notes=?, maj=? WHERE id=?""",
                   (table, sexe, json.dumps(anciennes, ensure_ascii=False), H.maintenant(), c["id"]))
                maj += 1
            else:
                ex("""INSERT INTO jur_cep_blanc_resultats (session_id, ecole_id, zone, numero_table, nom, prenoms, sexe, notes, maj)
                      VALUES (?,?,?,?,?,?,?,?,?)""",
                   (sid, e["id"], e["zone_nom"] or "", table, nom, MC.txt(pre, 120), sexe or None,
                    json.dumps(notes, ensure_ascii=False), H.maintenant()))
                existants[cle] = {"id": 0, "notes": "{}"}
                crees += 1
        recalculer(s)
        H.journal("jur_cep_blanc_import", f"session {sid} : {crees} créé(s), {maj} mis à jour")
        flash(f"Import terminé : {crees} candidat(s) ajouté(s), {maj} mis à jour"
              + (f", notes lues pour {len(i_mats)} matière(s)." if i_mats else "."), "success" if crees or maj else "info")
        if inconnues:
            flash("École(s) de provenance inconnue(s) dans la juridiction (lignes ignorées) : " + ", ".join(sorted(inconnues)[:10])
                  + ". Choisissez l'école dans la liste ou corrigez la colonne « École de provenance ».", "warning")
        for m in erreurs[:10]:
            flash(m, "warning")
        return retour

    @app.route("/juridiction/cep-blanc/<int:sid>/ecole/<int:jid>/sauvegarder", methods=["POST"])
    @H.connexion_requise("jur_cep")
    def jur_cep_blanc_sauvegarder(sid, jid):
        """Saisie manuelle des candidats et des notes d'une école (ajouts, modifications, suppressions)."""
        garde()
        s = session_ou_404(sid)
        e = H.jur_ecole(jid)
        if not e:
            abort(404)
        f = request.form
        existants = {c["id"]: c for c in candidats_session(s, jid)}
        suppr = {int(x) for x in f.getlist("suppr") if x.isdigit()}
        ids, tables, noms = f.getlist("cid"), f.getlist("table"), f.getlist("nom")
        prenoms, sexes = f.getlist("prenoms"), f.getlist("sexe")
        colonnes = [f.getlist(f"n{j}") for j in range(len(s["mats"]))]
        n_maj = n_new = 0
        mauvaises = []
        for i in range(min(len(noms), MAX_LIGNES_SAISIE)):
            def val(lst):
                return lst[i] if i < len(lst) else ""
            cid = int(val(ids)) if val(ids).isdigit() else None
            if cid and (cid not in existants or cid in suppr):
                continue
            nom = MC.txt(val(noms), 80).upper()
            if not nom:
                continue
            notes = {}
            if cid:
                try:
                    notes = {k: x for k, x in json.loads(existants[cid]["notes"] or "{}").items() if k in s["mats"]}
                except ValueError:
                    notes = {}
            for j, m in enumerate(s["mats"]):
                brut = val(colonnes[j]) if j < len(colonnes) else ""
                try:
                    n = H.xlsx.note(brut)
                except ValueError:
                    mauvaises.append(f"{nom} – {m} : « {brut} »")
                    continue
                if n is None:
                    notes.pop(m, None)
                else:
                    notes[m] = n
            vals = (MC.txt(val(tables), 20), nom, MC.txt(val(prenoms), 120), H.xlsx.sexe(val(sexes)) or None,
                    json.dumps(notes, ensure_ascii=False), H.maintenant())
            if cid:
                ex("UPDATE jur_cep_blanc_resultats SET numero_table=?, nom=?, prenoms=?, sexe=?, notes=?, maj=? WHERE id=? AND session_id=?",
                   vals + (cid, sid))
                n_maj += 1
            else:
                ex("INSERT INTO jur_cep_blanc_resultats (numero_table, nom, prenoms, sexe, notes, maj, session_id, ecole_id, zone) "
                   "VALUES (?,?,?,?,?,?,?,?,?)", vals + (sid, jid, e["zone_nom"] or ""))
                n_new += 1
        for cid in suppr:
            if cid in existants:
                ex("DELETE FROM jur_cep_blanc_resultats WHERE id=? AND session_id=?", (cid, sid))
        recalculer(s, jid)
        if mauvaises:
            flash(f"{len(mauvaises)} note(s) invalide(s) non enregistrée(s) (0 à 20) : " + " ; ".join(mauvaises[:6]), "warning")
        nb_suppr = len(suppr & set(existants))
        H.journal("jur_cep_blanc_saisie", f"session {sid} école {jid} : {n_maj} modifié(s), {n_new} ajouté(s), {nb_suppr} supprimé(s)")
        flash(f"{e['nom']} : {n_maj} candidat(s) mis à jour, {n_new} ajouté(s), {nb_suppr} supprimé(s).", "success")
        return redirect(url_for("jur_cep_blanc_session", sid=sid, vue="saisie", ecole=jid))

    @app.route("/juridiction/cep-blanc/<int:sid>/ecole/<int:jid>/vider", methods=["POST"])
    @H.connexion_requise("jur_cep")
    def jur_cep_blanc_vider(sid, jid):
        garde()
        session_ou_404(sid)
        ex("DELETE FROM jur_cep_blanc_resultats WHERE session_id=? AND ecole_id=?", (sid, jid))
        H.journal("jur_cep_blanc_vide", f"session {sid} école {jid}")
        flash("Candidats de cette école retirés de l'examen blanc.", "success")
        return redirect(url_for("jur_cep_blanc_session", sid=sid))

    def cellules_agregat(d):
        return [d["presents"]["G"], d["presents"]["F"], d["presents"]["T"], d["maitrise"]["G"], d["maitrise"]["F"], d["maitrise"]["T"],
                fr(d["taux"]["G"]), fr(d["taux"]["F"]), fr(d["taux"]["T"]), fr(d["moyenne"])]

    def exporter_session(s, lignes, tab, vue, ecole, export):
        titre = f"EXAMEN BLANC {nom_niveau()} N° {s['numero']} – {s['niveau']}"
        infos = [("Année scolaire", s["annee"]), ("Examen blanc", s["nom"]), ("Date", MC.date_fr(s["date"]) or ""),
                 ("Seuil de maîtrise", f"{s['seuil_eff']} matière(s) sur {len(s['mats'])} à 10/20")]
        if vue in ("candidats", "saisie"):
            if ecole:
                lignes = [l for l in lignes if l["c"]["ecole_id"] == ecole["id"]]
                infos.append(("École", ecole["nom"]))
            lignes = MC.trier_blanc(lignes, "merite")
            abrev = [m if len(m) <= 14 else m[:12] + "." for m in s["mats"]]
            cols = ["N° table", "Nom", "Prénoms", "S.", "École", "Zone"] + abrev + ["Total", "Moy.", "Nb ≥ 10", "Décision", "Rang"]
            data = [[l["c"]["numero_table"] or "", l["c"]["nom"], l["c"]["prenoms"] or "", l["c"]["sexe"] or "", l["c"]["ecole"],
                     l["c"]["zone_nom"] or ""] + [MC.num(v) if export == "pdf" else (v if v is not None else "") for v in l["notes"]]
                    + [MC.num(l["total"]) if export == "pdf" else (l["total"] if l["total"] is not None else ""),
                       MC.num(l["moyenne"]) if export == "pdf" else (l["moyenne"] if l["moyenne"] is not None else ""),
                       f"{l['reussies']}/{len(s['mats'])}" if l["nb"] else "", l["decision"], l["rang_txt"]] for l in lignes]
            st = MC.stats_blanc(lignes)
            note = (f"Inscrits : {st['inscrits']['T']} – présents : {st['presents']['T']} – ont la MAÎTRISE : {st['maitrise']['T']} "
                    f"(G {st['maitrise']['G']}, F {st['maitrise']['F']}) – taux : {fr(st['taux']['T'])} %.")
            sous = "Liste des candidats (ordre de mérite)"
            n = len(s["mats"])
            largeurs = [9, 22, 24, 5, 28, 18] + [9] * n + [9, 8, 8, 16, 10]
            nom_f = f"examen_blanc_{nom_niveau()}_{s['numero']}_candidats"
        else:
            cols = [["École", "Secteur", "Présents", None, None, "Maîtrise", None, None, "Taux de maîtrise (%)", None, None, "Moyenne", "Rang"],
                    ["^", "^", "G", "F", "T", "G", "F", "T", "G", "F", "T", "^", "^"]]
            data = []
            surl = {}
            for r in tab["rangees"]:
                d = r["d"]
                if r["genre"] == "ecole":
                    data.append([f"{r['n']}. {r['libelle']}", J.SECTEURS.get(d["secteur"], d["secteur"])] + cellules_agregat(d) + [d["rang"] or "—"])
                elif r["genre"] != "total":
                    data.append([r["libelle"], f"{d['nb_ecoles']} école(s)"] + cellules_agregat(d) + [""])
                    surl[len(data) - 1] = "#EEF3FA" if r["genre"] == "zone" else "#D9E4F2"
            g_ = tab["global"]
            total = ["TOTAL GÉNÉRAL", f"{g_['nb_ecoles']} école(s)"] + cellules_agregat(g_) + [""]
            note = (f"Présents : {g_['presents']['T']} – ont la MAÎTRISE : {g_['maitrise']['T']} – taux : {fr(g_['taux']['T'])} %. "
                    f"Règle : MAÎTRISE = au moins {s['seuil_eff']} matière(s) à 10/20 ; la moyenne ne sert qu'au rang.")
            sous = f"Résultats par école, par zone pédagogique{' et par circonscription' if ddemp() else ''}"
            largeurs = [60, 18] + [11] * 9 + [14, 12]
            nom_f = f"examen_blanc_{nom_niveau()}_{s['numero']}_resultats"
        if export == "xlsx":
            if isinstance(cols[0], list):   # en-tête sur deux lignes → « Présents G », « Présents F »…
                ent, courant = [], ""
                for a, b in zip(cols[0], cols[1]):
                    courant = a or courant
                    ent.append(courant if b == "^" else f"{courant} {b}")
                data = data + [total]
            else:
                ent = list(cols)
            H.journal("jur_cep_blanc_excel", f"session {s['id']}")
            return H.xlsx.reponse_xlsx(nom_f + ".xlsx", ent, data, titre="Examen blanc",
                                       titre_haut=[config.ECOLE.get("nom", ""), titre, " · ".join(f"{a} : {b}" for a, b in infos), note])
        pdf = H.pdfs.document_tableau(titre, cols, data, paysage=True, sous_titre=sous, infos=infos, infos_haut=infos_haut(),
                                      largeurs=largeurs, taille=6.5 if vue in ("candidats", "saisie") and len(s["mats"]) > 8 else 7,
                                      total=None if vue in ("candidats", "saisie") else total,
                                      surlignes=None if vue in ("candidats", "saisie") else surl,
                                      notes_bas=[note, f"Fait à {structure_infos().get('ville') or ''}, le {date.today().strftime('%d/%m/%Y')}"],
                                      signatures=signature_responsable())
        H.journal("jur_cep_blanc_pdf", f"session {s['id']}")
        return H.pdf_reponse(pdf, nom_f + ".pdf")

    # ---------------------------------------------------------------- synthèse des examens par niveau
    def synthese_examens(annee):
        """Examen blanc (par niveau et session) et CEP officiel (a_cep) : par zone / CS et total."""
        cep = H.jur_cep_stats(annee) if getattr(H, "jur_cep_stats", None) else None
        sessions = sessions_liste(annee)
        blocs = []
        for s in sessions:
            lignes = resultats(s)
            tab = tableau_ecoles(s, lignes)
            blocs.append({"s": s, "tab": tab})
        # par niveau : une ligne par session (examen blanc) + le CEP officiel
        par_niveau = []
        for b in blocs:
            g_ = b["tab"]["global"]
            par_niveau.append({"niveau": b["s"]["niveau"], "libelle": f"{b['s']['nom']} (examen blanc)", "ecoles": g_["nb_ecoles"],
                               "presentes": g_["presents"], "admis": g_["maitrise"], "taux": g_["taux"], "sid": b["s"]["id"]})
        if cep:
            G = cep["global"]
            par_niveau.append({"niveau": "CM2", "libelle": f"CEP officiel – session {cep['session']}", "ecoles": G["nb_presentes"],
                               "presentes": {"G": G["candidats_g"], "F": G["candidats_f"], "T": G["candidats"]},
                               "admis": {"G": G["admis_g"], "F": G["admis_f"], "T": G["admis"]},
                               "taux": {"G": G["taux_g"], "F": G["taux_f"], "T": G["taux"]}, "sid": None})
        # comparaison par zone (CS) ou par CS (DDEMP) : dernier examen blanc de l'année vs CEP officiel
        comparaison = []
        ref = blocs[0] if blocs else None
        groupes = {}
        if ref:
            for (cs_id, zone_id), z in ref["tab"]["zones"].items():
                cle = cs_id if ddemp() else zone_id
                lib = f"CS {z['cs_nom']}" if ddemp() else z["zone_nom"]
                d = groupes.setdefault(cle, {"libelle": lib, "blanc": {"presents": {"G": 0, "F": 0, "T": 0}, "maitrise": {"G": 0, "F": 0, "T": 0}}, "cep": None})
                for k in "GFT":
                    d["blanc"]["presents"][k] += z["presents"][k]
                    d["blanc"]["maitrise"][k] += z["maitrise"][k]
        if cep:
            source = cep["par_cs"] if ddemp() else cep["par_zone"]
            for cle, a in source.items():
                lib = f"CS {a['cs_nom']}" if ddemp() else a["zone_nom"]
                d = groupes.setdefault(cle, {"libelle": lib, "blanc": None, "cep": None})
                d["cep"] = {"presents": {"G": a["candidats_g"], "F": a["candidats_f"], "T": a["candidats"]},
                            "admis": {"G": a["admis_g"], "F": a["admis_f"], "T": a["admis"]},
                            "taux": {"G": a["taux_g"], "F": a["taux_f"], "T": a["taux"]}}
        for d in groupes.values():
            if d["blanc"]:
                p, m = d["blanc"]["presents"], d["blanc"]["maitrise"]
                d["blanc"]["taux"] = {k: (round(100 * m[k] / p[k], 2) if p[k] else None) for k in "GFT"}
            tb = d["blanc"]["taux"]["T"] if d["blanc"] else None
            tc = d["cep"]["taux"]["T"] if d["cep"] else None
            d["ecart"] = round(tc - tb, 2) if tb is not None and tc is not None else None
            comparaison.append(d)
        comparaison.sort(key=lambda d: d["libelle"])
        tot = {"libelle": "TOTAL", "blanc": None, "cep": None}
        if ref:
            g_ = ref["tab"]["global"]
            tot["blanc"] = {"presents": g_["presents"], "maitrise": g_["maitrise"], "taux": g_["taux"]}
        if cep:
            G = cep["global"]
            tot["cep"] = {"presents": {"G": G["candidats_g"], "F": G["candidats_f"], "T": G["candidats"]},
                          "admis": {"G": G["admis_g"], "F": G["admis_f"], "T": G["admis"]},
                          "taux": {"G": G["taux_g"], "F": G["taux_f"], "T": G["taux"]}}
        tb = tot["blanc"]["taux"]["T"] if tot["blanc"] else None
        tc = tot["cep"]["taux"]["T"] if tot["cep"] else None
        tot["ecart"] = round(tc - tb, 2) if tb is not None and tc is not None else None
        return {"annee": annee, "sessions": sessions, "blocs": blocs, "par_niveau": par_niveau, "comparaison": comparaison,
                "total": tot, "cep": cep, "reference": ref["s"] if ref else None}

    @app.route("/juridiction/cep-blanc/synthese")
    @H.connexion_requise("cep")
    def jur_cep_blanc_synthese():
        garde()
        annee = request.args.get("annee") or config.ANNEE_ACTIVE
        if not re.match(r"^\d{4}-\d{4}$", annee):
            annee = config.ANNEE_ACTIVE
        sy = synthese_examens(annee)
        annees = sorted({r["annee"] for r in q("SELECT DISTINCT annee FROM jur_cep_blanc_sessions")} | set(H.jur_annees()) | {annee}, reverse=True)
        export = request.args.get("export")
        if export in ("pdf", "xlsx"):
            return exporter_synthese_examens(sy, export)
        return render_template("jur_cep_blanc_synthese.html", sy=sy, annee=annee, annees=annees, fr=fr)

    def exporter_synthese_examens(sy, export):
        def tri(d, k):
            return [d[k]["G"] if d else "", d[k]["F"] if d else "", d[k]["T"] if d else ""]

        def taux3(d):
            return [fr(d["taux"]["G"]) if d else "—", fr(d["taux"]["F"]) if d else "—", fr(d["taux"]["T"]) if d else "—"]
        cols1 = ["Niveau", "Examen", "Écoles", "Présentés G", "F", "T", "Admis / maîtrise G", "F", "T", "Taux G (%)", "F", "T"]
        d1 = [[n["niveau"], n["libelle"], n["ecoles"]] + tri(n, "presentes") + tri(n, "admis") + taux3(n) for n in sy["par_niveau"]]
        lib_g = "Circonscription" if ddemp() else "Zone pédagogique"
        cols2 = [lib_g, "Examen blanc : présents", "Maîtrise", "Taux (%)", "CEP officiel : présentés", "Admis", "Taux (%)", "Écart CEP − blanc (points)"]
        d2 = [[c["libelle"], c["blanc"]["presents"]["T"] if c["blanc"] else "", c["blanc"]["maitrise"]["T"] if c["blanc"] else "",
               fr(c["blanc"]["taux"]["T"]) if c["blanc"] else "—", c["cep"]["presents"]["T"] if c["cep"] else "",
               c["cep"]["admis"]["T"] if c["cep"] and c["cep"]["admis"]["T"] is not None else "", fr(c["cep"]["taux"]["T"]) if c["cep"] else "—",
               ("+" if (c["ecart"] or 0) > 0 else "") + fr(c["ecart"]) if c["ecart"] is not None else "—"] for c in sy["comparaison"]]
        t = sy["total"]
        tot2 = ["TOTAL", t["blanc"]["presents"]["T"] if t["blanc"] else "", t["blanc"]["maitrise"]["T"] if t["blanc"] else "",
                fr(t["blanc"]["taux"]["T"]) if t["blanc"] else "—", t["cep"]["presents"]["T"] if t["cep"] else "",
                t["cep"]["admis"]["T"] if t["cep"] and t["cep"]["admis"]["T"] is not None else "", fr(t["cep"]["taux"]["T"]) if t["cep"] else "—",
                ("+" if (t["ecart"] or 0) > 0 else "") + fr(t["ecart"]) if t["ecart"] is not None else "—"]
        titre = f"SYNTHÈSE DES EXAMENS PAR NIVEAU – {nom_niveau()} – {sy['annee']}"
        haut = [config.ECOLE.get("nom", ""), titre]
        if export == "xlsx":
            H.journal("jur_cep_blanc_synthese_excel", sy["annee"])
            return H.xlsx.reponse_classeur(f"synthese_examens_{sy['annee']}.xlsx",
                                           [("Par niveau", cols1, d1, {"titre_haut": haut}),
                                            ("Examen blanc vs CEP", cols2, d2 + [tot2], {"titre_haut": haut})])
        pdfs = H.pdfs
        avant = [pdfs.paragraphe("<b>1. RÉSULTATS PAR NIVEAU (examens blancs et CEP officiel)</b>", 9, espace=4),
                 pdfs.mini_tableau([cols1] + d1, None) if d1 else pdfs.paragraphe("Aucun examen blanc enregistré pour cette année.", 8),
                 pdfs.paragraphe(f"<b>2. EXAMEN BLANC{' (' + sy['reference']['nom'] + ')' if sy['reference'] else ''} ET CEP OFFICIEL PAR {lib_g.upper()}</b>", 9, espace=6)]
        pdf = pdfs.document_tableau(titre, cols2, d2, paysage=True, sous_titre="Présentés, admis (maîtrise), taux par " + lib_g.lower() + " et total",
                                    infos=[("Année scolaire", sy["annee"]), ("Examens blancs", len(sy["sessions"]))], infos_haut=infos_haut(),
                                    largeurs=[55, 24, 24, 20, 26, 20, 20, 30], total=tot2, avant=avant, signatures=signature_responsable(),
                                    notes_bas=["Examen blanc : MAÎTRISE = au moins « seuil » matières à 10/20. CEP officiel : résultats transmis "
                                               "par les écoles ou importés (Examens › Candidats et résultats)."])
        H.journal("jur_cep_blanc_synthese_pdf", sy["annee"])
        return H.pdf_reponse(pdf, f"synthese_examens_{sy['annee']}.pdf")

    # ================================================================ 5. synthèse de l'évaluation CS / DDEMP
    def zone_de_locale(e, jur_par_id):
        je = jur_par_id.get(e["jur_ecole_id"]) if e["jur_ecole_id"] else None
        if je:
            return (je["cs_nom"] or "", je["zone_nom"] or "Sans zone pédagogique")
        return (e["cs"] or "", e["zone"] or "Sans zone pédagogique")

    def synthese_evaluation(type_, numero, annee):
        jur_par_id = {je["id"]: je for je in H.jur_ecoles(actif=False)}
        ecoles_rows, calculs_tous = [], []
        groupes = {}
        for e in ecoles_locales():
            doc = H.doc_lire(f"e{e['id']}:synthese:{annee}:{type_}{numero}", None)
            if not doc or not doc.get("fiches"):
                continue
            calculs = []
            for f in doc["fiches"]:
                f = dict(f)
                if not (f.get("ecole") or "").strip():
                    f["ecole"] = e["nom"]
                calculs.append(MS.calculer_fiche(f))
            niveaux, total = MS.synthese_niveaux(calculs, doc.get("observations"))
            cs_nom, zone = zone_de_locale(e, jur_par_id)
            cle = (cs_nom, zone) if ddemp() else zone
            lib = f"CS {cs_nom} – {zone}" if ddemp() else zone
            groupes.setdefault(cle, {"libelle": lib, "calculs": [], "ecoles": 0})
            groupes[cle]["calculs"] += calculs
            groupes[cle]["ecoles"] += 1
            calculs_tous += calculs
            ecoles_rows.append({"e": e, "zone": lib, "fiches": len(calculs), "niveaux": niveaux, "total": total,
                                "maj": doc.get("maj"), "publique": (e["statut"] or "") == "Publique"})
        zones = []
        for cle in sorted(groupes, key=lambda k: str(k)):
            gr = groupes[cle]
            niveaux, total = MS.synthese_niveaux(gr["calculs"])
            zones.append({"libelle": gr["libelle"], "ecoles": gr["ecoles"], "niveaux": niveaux, "total": total})
        niveaux, total = MS.synthese_niveaux(calculs_tous)
        return {"ecoles": ecoles_rows, "zones": zones, "niveaux": niveaux, "total": total,
                "analyse": MS.analyse(niveaux, total, calculs_tous), "nb_fiches": len(calculs_tous)}

    def selection_eval():
        v = request.args
        type_ = v.get("type") if v.get("type") in EC.TYPES else "sommative"
        try:
            numero = min(50, max(1, int(v.get("numero") or 1)))
        except ValueError:
            numero = 1
        annee = v.get("annee") or config.ANNEE_ACTIVE
        if not re.match(r"^\d{4}-\d{4}$", annee):
            annee = config.ANNEE_ACTIVE
        return type_, numero, annee

    @app.route("/juridiction/synthese-evaluation")
    @H.connexion_requise("synthese")
    def jur_synthese_eval():
        garde()
        type_, numero, annee = selection_eval()
        sy = synthese_evaluation(type_, numero, annee)
        export = request.args.get("export")
        if export in ("pdf", "xlsx"):
            return exporter_synthese_eval(sy, type_, numero, annee, export)
        annees = sorted(set(H.jur_annees()) | {annee}, reverse=True)
        return render_template("jur_synthese_eval.html", sy=sy, type_=type_, numero=numero, annee=annee, annees=annees,
                               TYPES=EC.TYPES, fr=fr, TAUX_REFERENCE=MS.TAUX_REFERENCE, titre_ev=f"{EC.TYPES[type_]} N° {numero}",
                               nb_ecoles=len(ecoles_locales()))

    def exporter_synthese_eval(sy, type_, numero, annee, export):
        def gft(d):
            return [d["g"], d["f"], d["t"]]

        def tx(d):
            return [fr(d["g"]), fr(d["f"]), fr(d["t"])]
        titre = f"SYNTHÈSE DE L'{EC.TYPES[type_].upper()} N° {numero} – NIVEAU {nom_niveau()}"
        lib_g = "Zone pédagogique" + (" (CS)" if ddemp() else "")
        # 1. par école
        cols_e = ["École", lib_g, "Fiches", "Inscrits G", "F", "T", "Ont composé G", "F", "T", "Ont réussi G", "F", "T",
                  "Taux G (%)", "F", "T", "À renforcer"]
        d_e = []
        for r in sy["ecoles"]:
            T = r["total"]
            d_e.append([r["e"]["nom"], r["zone"], r["fiches"]] + gft(T["inscrits"]) + gft(T["composes"]) + gft(T["reussis"]) + tx(T["taux"])
                       + [", ".join(T["renforcer"]) or "—"])
        # 2. par zone et niveau
        cols_z = [lib_g, "Niveau", "Écoles / classes", "Inscrits G", "F", "T", "Ont composé G", "F", "T", "Ont réussi G", "F", "T",
                  "Taux G (%)", "F", "T", "À renforcer", "Observation"]
        d_z = []
        for z in sy["zones"]:
            for n in z["niveaux"]:
                d_z.append([z["libelle"], n["niveau"], f"{len(n['ecoles'])} école(s), {len(n['classes'])} classe(s)"] + gft(n["inscrits"])
                           + gft(n["composes"]) + gft(n["reussis"]) + tx(n["taux"]) + [", ".join(n["renforcer"]) or "—", n["observation"]])
            if z["total"]:
                T = z["total"]
                d_z.append([z["libelle"], "TOTAL", f"{z['ecoles']} école(s)"] + gft(T["inscrits"]) + gft(T["composes"]) + gft(T["reussis"])
                           + tx(T["taux"]) + [", ".join(T["renforcer"]) or "—", T["observation"]])
        # 3. total par niveau
        cols_n = [["Niveau", "Écoles / classes", "Inscrits", None, None, "Ont composé", None, None, "Ont réussi (seuil)", None, None,
                   "Taux de réussite (%)", None, None, "À renforcer", "Observation"],
                  ["^", "^", "G", "F", "T", "G", "F", "T", "G", "F", "T", "G", "F", "T", "^", "^"]]
        d_n = [[n["niveau"], f"{len(n['ecoles'])} école(s), {len(n['classes'])} classe(s)"] + gft(n["inscrits"]) + gft(n["composes"])
               + gft(n["reussis"]) + tx(n["taux"]) + [", ".join(n["renforcer"]) or "—", n["observation"]] for n in sy["niveaux"]]
        total = None
        if sy["total"]:
            T = sy["total"]
            total = ["TOTAL", f"{len(sy['ecoles'])} école(s), {sy['nb_fiches']} classe(s)"] + gft(T["inscrits"]) + gft(T["composes"]) \
                + gft(T["reussis"]) + tx(T["taux"]) + [", ".join(T["renforcer"]) or "—", T["observation"]]
        A = sy["analyse"]
        haut = [config.ECOLE.get("nom", ""), titre, f"Année scolaire : {annee}"]
        if export == "xlsx":
            H.journal("jur_synthese_eval_excel", f"{type_} {numero} {annee}")
            ent_n = ["Niveau", "Écoles / classes"] + [f"{a} {s}" for a in ("Inscrits", "Ont composé", "Ont réussi", "Taux %") for s in "GFT"] + ["À renforcer", "Observation"]
            return H.xlsx.reponse_classeur(f"synthese_evaluation_{nom_niveau()}_{type_}{numero}_{annee}.xlsx", [
                ("Synthèse par niveau", ent_n, d_n + ([total] if total else []), {"titre_haut": haut}),
                ("Par zone", cols_z, d_z, {"titre_haut": haut}),
                ("Par école", cols_e, d_e, {"titre_haut": haut}),
                ("Analyse", ["Analyse des résultats"], [["1. Analyse quantitative"]] + [[t] for t in A["quantitative"]] + [[""], ["2. Analyse qualitative"]]
                 + [[t] for t in A["qualitative"]] + [[""], ["3. Écarts de genre"]] + [[t] for t in A["genre"]], {"titre_haut": haut})])
        pdfs = H.pdfs
        from reportlab.lib.units import mm
        avant = [pdfs.paragraphe("<b>1. RÉSULTATS PAR ÉCOLE</b>", 9, espace=4)]
        avant.append(pdfs.mini_tableau([["École", lib_g, "Fiches", "Inscrits", "Composé", "Réussi", "Taux (%)", "À renforcer"]]
                                       + [[r[0], r[1], r[2], r[5], r[8], r[11], r[14], r[15]] for r in d_e], None)
                     if d_e else pdfs.paragraphe("Aucune synthèse enregistrée dans les écoles pour cette évaluation.", 8))
        avant.append(pdfs.paragraphe(f"<b>2. RÉSULTATS PAR {lib_g.upper()} ET PAR NIVEAU</b>", 9, espace=6))
        if d_z:
            avant.append(pdfs.mini_tableau([[lib_g, "Niveau", "Écoles / classes", "Inscrits", "Composé", "Réussi", "Taux (%)", "À renforcer"]]
                                           + [[r[0], r[1], r[2], r[5], r[8], r[11], r[14], r[15]] for r in d_z], None))
        avant.append(pdfs.paragraphe("<b>3. SYNTHÈSE GÉNÉRALE PAR NIVEAU DE CLASSE</b>", 9, espace=6))
        apres = [pdfs.paragraphe("<b>ANALYSE DES RÉSULTATS</b>", 9.5, espace=4), pdfs.paragraphe("<b>1. Analyse quantitative</b>", 8.5)]
        apres += [pdfs.paragraphe("• " + x, 8) for x in A["quantitative"]]
        apres += [pdfs.paragraphe("<b>2. Analyse qualitative</b>", 8.5)] + [pdfs.paragraphe("• " + x, 8) for x in A["qualitative"]]
        apres += [pdfs.paragraphe("<b>3. Écarts de genre</b>", 8.5)]
        if A["genre_lignes"]:
            apres.append(pdfs.mini_tableau([["Niveau", "Garçons (%)", "Filles (%)", "Écart (F − G)"]]
                                           + [[x["niveau"], fr(x["g"]), fr(x["f"]), "—" if x["ecart"] is None else (("+" if x["ecart"] > 0 else "") + fr(x["ecart"]))]
                                              for x in A["genre_lignes"]], [40 * mm, 28 * mm, 28 * mm, 40 * mm]))
        apres += [pdfs.paragraphe("• " + x, 8) for x in A["genre"]]
        pdf = pdfs.document_tableau(titre, cols_n, d_n, paysage=True, sous_titre=f"Niveau {nom_niveau()} – année scolaire {annee}",
                                    infos=[("Évaluation", f"{EC.TYPES[type_]} N° {numero}"), ("Année scolaire", annee),
                                           ("Écoles", len(sy["ecoles"])), ("Fiches de classe", sy["nb_fiches"])],
                                    infos_haut=infos_haut(), largeurs=[18, 34, 9, 9, 9, 9, 9, 9, 9, 9, 9, 11, 11, 11, 35, 40], taille=7,
                                    total=total, avant=avant, apres=apres, signatures=signature_responsable(),
                                    notes_bas=["Réussite = élèves ayant atteint le SEUIL de maîtrise de l'évaluation ; « à renforcer » = matière "
                                               f"à moins de {MS.TAUX_REFERENCE} % de réussite. Données : synthèses École / UP / CS enregistrées "
                                               "dans chaque école ouverte."])
        H.journal("jur_synthese_eval_pdf", f"{type_} {numero} {annee}")
        return H.pdf_reponse(pdf, f"synthese_evaluation_{nom_niveau()}_{type_}{numero}_{annee}.pdf")

    # ================================================================== WhatsApp et SMS : directeurs et enseignants
    @app.route("/juridiction/messages", methods=["GET", "POST"])
    @H.connexion_requise()
    def jur_messages():
        """Messages WhatsApp / SMS aux directeurs et aux enseignants de la juridiction (liens en 1 clic, comme les
        messages aux parents dans GESCOL) : destinataires filtrés par CS, zone, école, fonction ; texte commun."""
        garde()
        import m_juridiction as J
        import notif
        annee = config.ANNEE_ACTIVE
        f = {k: (request.values.get(k) or "").strip() for k in ("cs", "zone", "ecole", "qui", "texte", "recherche")}
        qui = f["qui"] or "directeurs"
        try:
            cs_id = int(f["cs"]) if f["cs"] else None
            zone_id = int(f["zone"]) if f["zone"] else None
            ecole_id = int(f["ecole"]) if f["ecole"] else None
        except ValueError:
            cs_id = zone_id = ecole_id = None
        if not ddemp():
            c = J.cs_courante()
            cs_id = c["id"] if c else cs_id
        dest = []
        if qui in ("directeurs", "tous"):
            for e in J.ecoles(cs_id=cs_id, zone_id=zone_id):
                if ecole_id and e["id"] != ecole_id:
                    continue
                dest.append({"nom": e["directeur_nom"] or "", "tel": e["directeur_tel"] or e["telephone"] or "",
                             "fonction": e["directeur_titre"] or "Directeur", "ecole": e["nom"], "zone": e["zone_nom"] or "",
                             "cs": e["cs_nom"] or "", "type": "directeur"})
        if qui in ("enseignants", "tous"):
            for p in J.personnel(annee, cs_id, zone_id, inclure_agents=False):
                if ecole_id and p.get("ecole_id") != ecole_id:
                    continue
                if (p.get("role") or "").lower() == "directeur" and qui == "tous":
                    continue   # déjà listé comme directeur
                dest.append({"nom": f"{p.get('nom') or ''} {p.get('prenoms') or ''}".strip(), "tel": p.get("telephone") or "",
                             "fonction": p.get("fonction") or "Enseignant(e)", "ecole": p.get("ecole_nom") or "",
                             "zone": p.get("zone_nom") or "", "cs": p.get("cs_nom") or "", "type": "enseignant"})
        if f["recherche"]:
            r = J.norm(f["recherche"])
            dest = [d for d in dest if r in J.norm(f"{d['nom']} {d['ecole']}")]
        dest.sort(key=lambda d: (d["cs"], d["zone"], d["ecole"], d["nom"]))
        s = J.structure() or {}
        texte = f["texte"] or (f"Bonjour, message de la {s.get('nom') or ('Circonscription scolaire' if not ddemp() else 'DDEMP')} : ")
        for d in dest:
            d["whatsapp"] = notif.lien_whatsapp(d["tel"], texte.replace("{nom}", d["nom"]))
            n = notif.normaliser_tel(d["tel"]) if d["tel"] else ""
            d["sms"] = f"sms:+{n}?body={__import__('urllib.parse').parse.quote(texte.replace('{nom}', d['nom']))}" if n else None
        if request.method == "POST":
            H.journal("jur_messages", f"{qui} : {len(dest)} destinataire(s)")
        return render_template("jur_messages.html", f=f, qui=qui, dest=dest, texte=texte, annee=annee,
                               cs_liste=J.cs_liste() if ddemp() else [], zones=J.zones(cs_id) if cs_id else J.zones(),
                               ecoles=J.ecoles(cs_id=cs_id, zone_id=zone_id), DDEMP=ddemp(),
                               sans_tel=sum(1 for d in dest if not d["tel"]))
