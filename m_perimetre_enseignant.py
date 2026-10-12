# -*- coding: utf-8 -*-
"""Périmètre de l'enseignant (GESCOL / GESCOL Public, v1.6).

Demande du client : « chaque enseignant accède à son périmètre avec tout ce qui est sur l'application sauf ce qui
appartient au domaine du directeur (tableau de bord, synoptique, budget…) ; tout le reste par classe, avec sa signature
digitale, son identifiant et son mot de passe ».

Mise en œuvre CENTRALE, sans refonte des modules : un ``before_request`` actif seulement pour un compte de rôle
« enseignant » (éditions privée et publique ; dans GESCOL Circonscription / DDEMP, les comptes enseignant d'une école
créés par a_integration gardent le même périmètre sur les modules d'école, sans la redirection de « / »). Il s'exécute
après ceux d'app.py (g.user) et de m_ecoles (g.ecole) car le module est chargé en dernier (fin de MODULES).

Règles, dans l'ordre :
1. ``/`` (endpoint ``accueil``) → redirection vers « Mon espace » (``/mon-espace``).
2. ``INTERDITS`` : préfixes d'endpoints du domaine du directeur → 403 « Hors de votre périmètre d'enseignant »
   (tableaux de bord, finances, administration, personnel des autres, recensement et rapports, données, secrétariat,
   création / suppression / import / export d'élèves, comptes parents, classes, calendrier des jours de classe en
   écriture, patrimoine en écriture, composition du comité d'évaluation, suppression de la synthèse…).
3. Modules en LECTURE SEULE (``LECTURE_SEULE``) : tableau synoptique (seulement emplois du temps, planification et
   comité de classe de SES niveaux, règlement intérieur), calendrier scolaire officiel, thèmes d'UP, stock de vivres,
   patrimoine : toute requête POST → 403, et seuls les endpoints de consultation sont ouverts. Exception : la
   planification mensuelle (CE-CM) d'une classe (``synoptique_planification_mensuelle*``) est tenue par l'enseignant
   de la classe (GET + POST), la classe étant contrôlée par ``cid`` (règle 4).
4. Routes portant un identifiant de classe (``cid``) ou d'élève (``eid`` sous /eleves/, /cep/fiche/, /carte/) :
   l'objet doit appartenir à SES classes (``H.classes_autorisees()``, table ``affectations``) → 403 sinon.
   Même contrôle sur le paramètre ``classe`` (GET ou POST) des pages de liste et des formulaires.
5. Règles particulières : ``eleve_form`` sans ``eid`` (inscription) → 403 ; synthèse École / UP / CS : écriture
   seulement pour une de ses classes ; épreuves et grilles : écriture seulement sur les siennes (``cree_par``) ;
   examen blanc CEP : réservé aux enseignants d'une classe de CM2.

Les pages de liste des modules filtrent déjà par ``H.classes_autorisees()`` (élèves, classes, appel, registre,
relevés, affichage, évaluations, notes, cantine, impayés, CEP, cartes, visites, documents de l'enseignant, messages
aux parents, comptes élèves) ; les filtres manquants ont été ajoutés dans les modules (voir le compte rendu).

Signature digitale : clé « enseignant:<user_id> » (m_ecoles.RE_CLE_SIGNATURE), exposée par ``H.signature_enseignant``
et utilisée par ``H.signature_titulaire(cid)`` (bulletins, relevés, fiches de classe), ``H.signature_agent(pid)``
(documents de l'enseignant, visites, journal du maître de semaine) et les épreuves de l'auteur.

Expose : ``H.perimetre_enseignant()`` (bool : la requête courante est soumise au périmètre), ``H.niveaux_enseignant()``
(clés de niveau du synoptique : « cm2 », « maternelle1 »…), ``H.classe_dans_perimetre(cid)``.
"""
from flask import abort, g, redirect, request, url_for

MESSAGE_403 = "Hors de votre périmètre d'enseignant : cette page relève du directeur de l'école (ou d'une autre classe)."

# ---------------------------------------------------------------- 1. domaine du directeur : préfixes d'endpoints refusés
INTERDITS = (
    # tableaux de bord (du fondateur, du directeur) — le tableau de bord « / » redirige vers Mon espace
    "fondateur_", "directeur_tableau",
    # finances : scolarité, impayés, reçus, trésorerie, bilan / budget, dépenses, recettes, frais CEP, paie, paiement en ligne
    "paiement", "impayes", "recu", "tresorerie", "depense", "recette", "cep_frais", "paie_", "bulletin_paie_pdf",
    "livre_paie", "reglages_",
    # administration : écoles, paramètres, utilisateurs et affectations, mise en ligne, sauvegardes, journal, candidates
    "ecoles", "ecole_form", "ecole_supprimer", "ecole_basculer", "parametres", "utilisateurs", "affectations",
    "en_ligne_page", "restaurer", "sauvegarde", "journal_page", "demandes_ecoles",
    # personnel des autres et gestion de carrière (la fiche de l'enseignant reste accessible : carriere_moi_fiche,
    # carriere_fiche, carriere_fiche_pdf, carriere_proposer — contrôlées par m_carriere)
    "personnel", "carriere_accueil", "carriere_xlsx", "carriere_pdf", "carriere_valider",
    # recensement et rapports
    "recensement_", "rapports_",
    # données : import / export, EducMaster (sauf le modèle de notes de SES classes), conversion, transmission
    "donnees_", "educmaster_", "conversion_", "transmission_",
    # secrétariat
    "courrier", "archives", "fichier_secretariat",
    # élèves : suppression, import, export de toute l'école (la création est traitée à part : eleve_form sans eid)
    "eleve_supprimer", "eleves_supprimer_selection", "eleves_import", "eleves_modele_xlsx", "eleves_export",
    # comptes parents (secrétariat) — les messages aux parents de ses élèves restent ouverts (communication)
    "parents_liste", "parent_action", "acces_parent", "acces_parents_classe",
    # classes : création / modification, liste CEP (CSV) du secrétariat
    "classe_form", "liste_cep",
    # calendrier des jours de classe : écriture
    "calendrier_enregistrer", "calendrier_feries", "calendrier_periode", "calendrier_parametres",
    # examen blanc du CEP : suppression et réinitialisation d'une session
    "cep_blanc_supprimer", "cep_blanc_reinitialiser",
    # comité d'évaluation : composition (membres, import)
    "epreuves_membre", "epreuves_comite_import",
    # synthèse École / UP / CS : suppression
    "synthese_supprimer",
    # patrimoine : fiches, suppressions, annulation de mouvements (lecture seule)
    "patrimoine_local", "patrimoine_meuble", "patrimoine_materiel", "patrimoine_supprimer", "patrimoine_mouvement_annuler",
    # maître de semaine : suppression d'un journal (direction)
    "maitre_semaine_supprimer",
)
# endpoints ouverts bien qu'un préfixe ci-dessus les couvre
EXCEPTIONS = {"educmaster_modele_notes_rempli"}

# ---------------------------------------------------------------- 3. modules en lecture seule
LECTURE_SEULE = ("synoptique_", "calendrier_officiel", "themes_up", "stock_", "patrimoine_")
# synoptique : la planification mensuelle (CE-CM) d'une classe est tenue par son enseignant (GET + POST) ; elle échappe
# à la lecture seule du tableau synoptique et m_synoptique contrôle lui-même la classe (404 hors de ses classes)
SYNOPTIQUE_CLASSE = ("synoptique_planification_mensuelle",)
# consultation ouverte dans ces modules (les autres endpoints du préfixe sont refusés)
SYNOPTIQUE_LECTURE = {"synoptique_edt", "synoptique_edt_pdf", "synoptique_edt_xlsx",
                      "synoptique_planification", "synoptique_planification_pdf", "synoptique_planification_xlsx",
                      "synoptique_comites", "synoptique_comite_pdf", "synoptique_reglement", "synoptique_reglement_pdf"}
CALENDRIER_LECTURE = {"calendrier_officiel", "calendrier_officiel_pdf", "calendrier_officiel_xlsx"}
# mots marquant une page d'écriture dans un module dont les endpoints ne sont pas connus à l'avance (thèmes d'UP)
MOTS_ECRITURE = ("form", "modifier", "nouveau", "nouvelle", "ajouter", "supprimer", "import", "reinit", "meta",
                 "preparer", "recharger", "retablir", "valider", "enregistrer")

# préfixes de routes où <int:eid> désigne un élève (ailleurs : école, épreuve…)
ROUTES_ELEVE = ("/eleves/", "/cep/fiche/", "/carte/")

# épreuves et grilles : écriture réservée à l'auteur (colonne cree_par)
EPREUVE_ECRITURE = {"epreuve_form", "epreuve_supprimer", "epreuve_statut", "epreuve_items_import"}
GRILLE_ECRITURE = {"grille_form", "grille_supprimer"}


def cle_niveau(niveau):
    """Clé de niveau du tableau synoptique : « Maternelle 1 » → « maternelle1 », « CM2 » → « cm2 »."""
    return (niveau or "").lower().replace(" ", "")


def est_interdit(ep):
    return ep not in EXCEPTIONS and ep.startswith(INTERDITS)


def enregistrer(app, H):
    q, config = H.q, H.config

    def actif():
        """La requête courante est-elle soumise au périmètre de l'enseignant ? Comptes de rôle « enseignant » des
        éditions école ; dans GESCOL Circonscription / DDEMP, les comptes enseignant d'une école (a_integration)
        gardent le même périmètre sur les modules d'école (seule la redirection de « / » leur est épargnée)."""
        u = g.get("user")
        return bool(u) and u["role"] == "enseignant"

    def mes_classes_ids():
        return {c["id"] for c in H.classes_autorisees()}

    def niveaux_enseignant():
        return [cle_niveau(c["niveau"]) for c in H.classes_autorisees()]

    def classe_dans_perimetre(cid):
        return cid in mes_classes_ids()

    def refuser():
        g.message_403 = MESSAGE_403
        abort(403)

    def exiger_classe(cid):
        if cid is None or not classe_dans_perimetre(int(cid)):
            refuser()

    def exiger_eleve(eid):
        e = H.eleve_ou_404(eid)
        exiger_classe(e["classe_id"])

    def auteur_ou_403(table, oid):
        if not oid:
            return                      # création
        r = q(f"SELECT cree_par FROM {table} WHERE id=?", (oid,), un=True)
        if r and r["cree_par"] != g.user["id"]:
            refuser()

    H.perimetre_enseignant = actif
    H.niveaux_enseignant = niveaux_enseignant
    H.classe_dans_perimetre = classe_dans_perimetre

    @app.context_processor
    def ctx_perimetre():
        return dict(perimetre_enseignant=actif,
                    classes_enseignant_cm2=lambda: "cm2" in niveaux_enseignant(),
                    niveaux_enseignant=niveaux_enseignant)

    @app.before_request
    def perimetre():
        if not actif():
            return None
        ep = request.endpoint or ""
        if not ep or ep == "static" or request.url_rule is None:
            return None
        va = request.view_args or {}
        # 1. tableau de bord → Mon espace (CS / DDEMP : a_integration ouvre l'école du compte)
        if ep == "accueil":
            if config.juridiction() or "espace_enseignant" not in app.view_functions:
                return None
            return redirect(url_for("espace_enseignant"))
        # 2. domaine du directeur
        if est_interdit(ep):
            refuser()
        if ep == "eleve_form" and not va.get("eid"):
            refuser()                                   # inscription d'un élève
        # 3. modules en lecture seule (sauf la planification mensuelle de ses classes : règle 4)
        if ep.startswith(LECTURE_SEULE) and not ep.startswith(SYNOPTIQUE_CLASSE):
            if request.method != "GET":
                refuser()
            if ep.startswith("synoptique_"):
                if ep not in SYNOPTIQUE_LECTURE:
                    refuser()
                niveaux = niveaux_enseignant()
                if "niveau" in va:
                    if va["niveau"] not in niveaux:
                        refuser()
                elif ep in ("synoptique_edt", "synoptique_planification"):
                    if not niveaux:
                        refuser()
                    return redirect(url_for(ep, niveau=niveaux[0]))     # ses niveaux plutôt que le CI par défaut
                if ep.startswith("synoptique_comite"):
                    if va.get("comite") is None:
                        return redirect(url_for("synoptique_comites", comite="classe"))
                    if va["comite"] != "classe":
                        refuser()
            elif ep.startswith("calendrier_officiel") and ep not in CALENDRIER_LECTURE:
                refuser()
            elif ep.startswith("themes_up") and any(m in ep[len("themes_up"):] for m in MOTS_ECRITURE):
                refuser()
        # 4. objets : classe, élève, paramètre « classe »
        eleve = "eid" in va and request.url_rule.rule.startswith(ROUTES_ELEVE)
        if ep.startswith(SYNOPTIQUE_CLASSE):
            return None                                 # m_synoptique contrôle lui-même la classe (404 hors périmètre)
        if "cid" in va:
            exiger_classe(va["cid"])
        if eleve:
            exiger_eleve(va["eid"])
        brut = request.values.get("classe", "")
        if brut.isdigit() and int(brut) and "cid" not in va and not eleve:
            exiger_classe(int(brut))        # paramètre « classe » des listes et formulaires (identifiant de classe)
        # 5. règles particulières
        if ep == "synthese_accueil" and request.method == "POST" and not brut.isdigit():
            refuser()                                   # document de toute l'école : directeur
        if ep in EPREUVE_ECRITURE and request.method == "POST":
            auteur_ou_403("epreuves", va.get("eid"))
        if ep in GRILLE_ECRITURE and request.method == "POST":
            auteur_ou_403("grilles", va.get("gid"))
        if ep.startswith("cep_blanc") and "cm2" not in niveaux_enseignant():
            refuser()                                   # examen blanc : enseignants de CM2
        return None
