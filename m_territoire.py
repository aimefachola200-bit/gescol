# -*- coding: utf-8 -*-
"""v2.3 — Territoire et suivi administratif (compléments repris du prototype « GESCOL Territoire »).

Ajouts seulement : aucune page, URL, table ni donnée existante n'est modifiée (colonnes et tables nouvelles,
registres nouveaux du moteur commun registres.py, rubriques ajoutées en fin de registre).

1. Fiche statistique de rentrée (/reg/territoire/rentree) : l'école la remplit (valeurs proposées depuis ses effectifs, son
   personnel, son patrimoine et sa fiche signalétique), puis la transmet ; la CS la valide ou la renvoie, la DDEMP la valide à
   son tour puis la clôture. Statuts : Brouillon → Transmise → Validée CS → Validée département → Clôturée (Renvoyée : à
   corriger puis retransmettre). Suivi de toutes les écoles : /territoire/rentree/suivi (CS, DDEMP).
   La fiche monte avec la synchronisation 2.0 (registre « territoire:rentree ») ; les décisions de la CS et de la DDEMP
   descendent (registre « territoire:retours ») et mettent à jour la fiche de l'école.
2. Courrier administratif entre structures (/reg/communication/courrier) : rapport, demande, compte rendu… de l'école vers la
   CS, de la CS vers la DDEMP ; statuts Brouillon → Envoyé → Reçu (accusé de lecture daté) → Traité → Archivé ; courrier reçu
   et compteur des non-lus (/territoire/courrier, alertes). Les notes de service descendantes restent dans « Notes,
   circulaires et convocations ».
3. Visites de classe (registre d'inspection existant) : rubriques ajoutées « Statut de la visite » (Planifiée → Réalisée →
   Rapport rédigé → Validée) et « Date de la prochaine visite » ; alertes (visite planifiée dépassée, prochaine visite).
4. Présence du personnel (/reg/presences/agents) : présent, absent, retard, congé, mission, formation, maladie par jour ;
   appel du jour (/territoire/presences/appel) et statistiques du mois (/territoire/presences/mois).
5. Fiche signalétique de l'école (/territoire/ecole) : coordonnées GPS (bouton « position actuelle »), statut juridique,
   numéros et dates d'autorisation d'ouverture et d'agrément (écoles privées), indicateurs eau / latrines / électricité /
   salles (proposés depuis le patrimoine).
6. Incidents de discipline des élèves (/reg/discipline/incidents) : date, description, sanction, décidé par, parents
   informés, suivi (données d'élèves : jamais synchronisées).
7. Référentiel des structures administratives (/reg/territoire/structures, arbre : /territoire/structures/arbre) :
   ministère → directions → DDEMP → services → CS → divisions, modifiable comme des données.
8. Niveau national (CS / DDEMP) : rôle « observateur » en lecture seule (/territoire/national, agrégats sans données
   nominatives) et /api/stats.json protégé par un jeton (empreinte SHA-256 seule conservée).
Les actions sensibles sont inscrites au journal (H.journal).
"""
import hashlib
import json
import re
import secrets
from datetime import date, timedelta

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for

import registres as R

STATUTS_RENTREE = ["Brouillon", "Transmise", "Validée CS", "Validée département", "Clôturée", "Renvoyée"]
CODES_RENTREE = {"Brouillon": "BROUILLON", "Transmise": "TRANSMISE", "Validée CS": "VALIDEE_CS",
                 "Validée département": "VALIDEE_DEPARTEMENT", "Clôturée": "CLOTUREE", "Renvoyée": "RENVOYEE"}
STATUTS_COURRIER = ["Brouillon", "Envoyé", "Reçu", "Traité", "Archivé"]
TYPES_COURRIER = ["Rapport", "Demande", "Compte rendu", "Note de service", "Circulaire", "Convocation", "Décision", "Lettre", "Autre"]
NIV_COURRIER = ["CS", "DDEMP", "ZONE", "UP", "ECOLE"]
STATUTS_VISITE = ["Planifiée", "Réalisée", "Rapport rédigé", "Validée"]
STATUTS_PRESENCE = ["Présent", "Absent", "Retard", "Congé", "Mission", "Formation", "Maladie"]
SANCTIONS = ["Avertissement oral", "Avertissement écrit", "Travail d'intérêt scolaire", "Convocation des parents",
             "Exclusion temporaire (décision du conseil des maîtres)", "Aucune", "Autre"]
TYPES_STRUCT = ["Ministère", "Direction centrale", "Direction départementale", "Service", "Circonscription scolaire", "Division",
                "Zone pédagogique", "Autre"]
ORDRES = ["Maternel et primaire", "Secondaire", "Technique et professionnel", "Tous"]
STATUTS_JUR = ["Public", "Privé laïc", "Privé confessionnel", "Communautaire"]
CHAMPS_SIGNALETIQUE = [("latitude", "Latitude (degrés décimaux)"), ("longitude", "Longitude (degrés décimaux)"),
                       ("statutJuridique", "Statut juridique"), ("numeroAutorisation", "N° de l'autorisation d'ouverture"),
                       ("dateAutorisation", "Date de l'autorisation"), ("numeroAgrement", "N° de l'agrément"),
                       ("dateAgrement", "Date de l'agrément"), ("salles", "Salles de classe"), ("pointEau", "Point d'eau"),
                       ("latrines", "Latrines (cabines)"), ("electricite", "Électricité")]
ROLES_ECOLE_DECIDE = {"admin", "fondateur", "directeur", "secretaire"}
ROLES_JUR_DECIDE = {"admin", "fondateur", "responsable", "chef_service"}
INDICATEURS_API = ("ecoles", "classes", "g", "f", "t", "pct_f", "ip", "ratio", "moy_classe", "plethoriques", "redoublants",
                   "taux_redoublement", "abandons", "taux_abandon", "eleves_salle", "licences", "cantine", "tables_bancs")


def norm(t):
    """Clé normalisée commune aux applications (pvs.js normCle) : accents retirés, minuscules, espaces simples."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t if t is not None else ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t.lower()).strip()


def enregistrer(app, H):
    q, ex = H.q, H.ex
    cfg = H.config
    H.DROITS["territoire"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent", "enseignant"}
    H.DROITS["territoire_national"] = {"admin", "fondateur", "responsable", "chef_service", "observateur"}
    R.types_documents({"reg_territoire_rentree": "Fiches statistiques de rentrée", "reg_territoire_structures": "Référentiel des structures",
                       "reg_presences_agents": "Présence du personnel", "reg_discipline_incidents": "Incidents de discipline",
                       "reg_communication_courrier": "Courrier administratif", "reg_territoire_retours": "Décisions transmises"})

    def role_reel():
        return (g.get("role_reel") or g.user["role"]) if g.get("user") else None

    def edition():
        return cfg.EDITION

    def niveau_compte():
        return R.entite_courante()[0]

    # ------------------------------------------------------------------ listes dynamiques
    def noms_personnel():
        try:
            if R.juridiction() and not g.get("ecole"):
                rows = q("SELECT nom, prenoms FROM jur_agents WHERE cs_id IS NULL AND COALESCE(actif,1)=1 ORDER BY nom, prenoms")
            else:
                rows = q("SELECT nom, prenoms FROM personnel WHERE actif=1 ORDER BY nom, prenoms")
            return [f"{r['nom']} {r['prenoms'] or ''}".strip() for r in rows]
        except Exception:  # noqa: BLE001
            return []

    def noms_structures():
        try:
            return [r["nom"] for r in q("SELECT nom FROM reg_territoire_structures WHERE portee=? ORDER BY nom", (R.cle_portee("structure"),))]
        except Exception:  # noqa: BLE001
            return []

    # ================================================================== 1. fiche statistique de rentrée
    G = R.Groupe(app, H, "territoire", "Territoire et suivi administratif", "territoire", ico="structure",
                 sous_titre="Fiche statistique de rentrée (transmission et validations), suivi des écoles, référentiel des structures, "
                            "niveau national",
                 listes={"statuts_rentree": STATUTS_RENTREE, "types_struct": TYPES_STRUCT, "ordres": ORDRES, "structures": noms_structures,
                         "oui_non_vide": ["Oui", "Non"]})

    def signaletique(eco=None):
        return H.doc_lire(f"signaletique:e{eco or H.eco()}", {}) or {}

    def propose_rentree():
        """Valeurs proposées : effectifs inscrits, classes, enseignants, patrimoine, fiche signalétique."""
        eco = H.eco()
        d = {"niveau": "ECOLE", "entite": R.entite_courante()[1]}
        try:
            r = q("SELECT SUM(e.sexe='M') g, SUM(e.sexe='F') f, COUNT(*) t FROM eleves e JOIN classes c ON c.id=e.classe_id "
                  "WHERE c.ecole_id=? AND e.statut='inscrit'", (eco,), un=True)
            d.update(effG=r["g"] or 0, effF=r["f"] or 0, effT=r["t"] or 0)
            co = H.classes_ouvertes(eco)                 # v2.3.1 : jumelée / multigrade = une classe
            d.update(classes=co["total"], classesSimples=co["simples"], classesJumelees=co["jumelees"], classesMultigrades=co["multigrades"])
        except Exception:  # noqa: BLE001
            pass
        try:
            rec = H.doc_lire(f"e{eco}:recensement:primaire:{R.annee_active()}", {}) or {}
            if str(rec.get("classes_autorisees") or "").strip().isdigit():
                d["classesAutorisees"] = int(rec["classes_autorisees"])
        except Exception:  # noqa: BLE001
            pass
        try:
            if not R.juridiction():
                d["ensPoste"] = q("SELECT COUNT(*) n FROM personnel WHERE actif=1 AND lower(fonction) LIKE '%enseign%'", un=True)["n"]
        except Exception:  # noqa: BLE001
            pass
        try:
            import m_pilotage
            pat = H.patrimoine_synthese(eco)
            i = m_pilotage.infra(pat)
            d.update(salles=(pat.get("salles_classe") or {}).get("utilisees") or i["salles"], latrines=i["cabines"],
                     pointEau="Oui" if i["eau"] else "Non", electricite="Oui" if i["electricite"] else "Non",
                     manuels=(pat.get("didactique") or {}).get("manuels_total") or 0,
                     tablesBancs=sum(v.get("quantite") or 0 for k, v in ((pat.get("mobilier") or {}).get("par_categorie") or {}).items()
                                     if "table" in k))
        except Exception:  # noqa: BLE001
            pass
        s = signaletique()
        for k_s, k_f in (("latitude", "latitude"), ("longitude", "longitude")):
            if s.get(k_s) not in (None, ""):
                d[k_f] = s[k_s]
        for k_s, k_f in (("salles", "salles"), ("latrines", "latrines"), ("pointEau", "pointEau"), ("electricite", "electricite")):
            if s.get(k_s) not in (None, ""):
                d[k_f] = s[k_s]
        return d

    def peut_ecrire_rentree():
        if not g.get("user") or edition() == "enseignant":
            return False
        r_ = role_reel()
        return (r_ in ROLES_ECOLE_DECIDE) or (R.juridiction() and g.get("ecole") and r_ in ROLES_JUR_DECIDE)

    def statut_de(x):
        return lib_rentree(x.get("statut"))

    def actions_rentree(x):
        out = []
        st = statut_de(x)
        if not R.juridiction() and st in ("Brouillon", "Renvoyée") and peut_ecrire_rentree():
            out.append(("post:" + url_for("territoire_rentree_transmettre", rid=x["id"]), "Transmettre", "envoyer"))
        return out

    RENTREE = G.registre("rentree", "Fiche statistique de rentrée", [
        ("effG", "Effectif garçons", "entier"), ("effF", "Effectif filles", "entier"), ("effT", "Effectif total", "entier"),
        ("classes", "Classes (groupes pédagogiques)", "entier"), ("ensPoste", "Enseignants en poste", "entier"),
        ("ensManquants", "Enseignants manquants", "entier"), ("salles", "Salles de classe utilisables", "entier"),
        ("tablesBancs", "Tables-bancs", "entier"), ("manuels", "Manuels", "entier"), ("pointEau", "Point d'eau", "choix:oui_non_vide"),
        ("latrines", "Latrines (cabines)", "entier"), ("electricite", "Électricité", "choix:oui_non_vide"),
        ("latitude", "Latitude", "decimal"), ("longitude", "Longitude", "decimal"), ("observations", "Observations", "long"),
        # v2.3.1 : classes ouvertes = simples + jumelées + multigrades ; autorisées à part (peut être inférieur)
        ("classesSimples", "Classes simples", "entier"), ("classesJumelees", "Classes jumelées", "entier"),
        ("classesMultigrades", "Classes multigrades", "entier"), ("classesAutorisees", "Classes autorisées", "entier")],
        unite="fiche", oblig="entite", ordre="entite", portee="ecole", feuille="Fiche statistique de rentrée", onglet="Fiche de rentrée",
        entite=True, niveaux=["ECOLE"], unique=("entite",), paysage=True, ecriture=peut_ecrire_rentree, annee_lib="Année scolaire",
        calcul=lambda x: {"Statut": statut_de(x), "Transmise le": R.jjmmaaaa(x.get("dateTransmission")),
                          "Décision": " ".join(v for v in (x.get("validePar") or "", R.jjmmaaaa(x.get("dateValidation"))) if v)},
        colonnes=("entite", "effG", "effF", "effT", "classes", "ensPoste", "ensManquants", "salles"),
        actions=actions_rentree, defauts=propose_rentree, doc="Fiches statistiques de rentrée",
        aide="Valeurs proposées depuis les élèves inscrits, le personnel, le patrimoine et la fiche signalétique : à vérifier puis "
             "« Transmettre ». La CS valide (ou renvoie avec un motif), puis la DDEMP valide et clôture. Une fiche transmise ne se "
             "modifie plus à l'école, sauf si elle est renvoyée.")
    for col in ("statut", "dateTransmission", "validePar", "dateValidation", "motifRenvoi"):
        H.ajouter_colonne(RENTREE.table, col, "TEXT")

    G.registre("retours", "Décisions transmises", [
        ("objet", "Objet", "texte"), ("cle", "Clé", "texte"), ("destinataire", "Destinataire", "texte"), ("statut", "Statut", "texte"),
        ("date", "Date", "date"), ("decidePar", "Décidé par", "texte"), ("motif", "Motif / observations", "long")],
        unite="décision", oblig="cle", ordre="date DESC, id DESC", portee="structure", feuille="Décisions transmises", onglet="Décisions transmises",
        unique=("cle", "statut", "date"), ecriture=lambda: bool(g.get("user")) and role_reel() in ("admin", "fondateur"),
        doc="Décisions transmises (fiches de rentrée, courrier)",
        aide="Décisions de la CS et de la DDEMP (validation, renvoi, réception, traitement) : elles descendent avec la synchronisation "
             "et mettent à jour la fiche de rentrée ou le courrier de l'école concernée.")

    def ajouter_retour(objet, cle, ecole, statut, motif=""):
        niv, ent = R.entite_courante()
        ex("INSERT INTO reg_territoire_retours (portee, annee, objet, cle, destinataire, statut, date, decidePar, motif, cree_le, cree_par, maj) "
           "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (R.cle_portee("structure"), R.annee_active(), objet, cle, ecole, statut, date.today().isoformat(),
                                                f"{R.NIVEAUX_LIB.get(niv, niv)} — {ent}".strip(" —"), motif, H.maintenant(),
                                                g.user["id"] if g.get("user") else None, H.maintenant()))

    def cle_rentree(x):
        return f"rentree|{norm(x.get('entite'))}|{x.get('annee') or ''}"

    def appliquer_retours():
        """Applique aux fiches de rentrée et au courrier de ce poste les décisions reçues (ordre : date, rang du statut)."""
        try:
            rets = [dict(x) for x in q("SELECT * FROM reg_territoire_retours ORDER BY date, id")]
        except Exception:  # noqa: BLE001
            return 0
        n = 0
        rang = {s: i for i, s in enumerate(STATUTS_RENTREE)}
        rets.sort(key=lambda x: (x.get("date") or "", rang.get(lib_rentree(x.get("statut")) if x.get("objet") == "Fiche de rentrée" else "", 0)))
        fiches = {cle_rentree(dict(x)): dict(x) for x in q(f"SELECT * FROM {RENTREE.table}")}
        cour = {}
        try:
            for x in q("SELECT * FROM reg_communication_courrier"):
                cour[cle_courrier(dict(x))] = dict(x)
        except Exception:  # noqa: BLE001
            pass
        for d in rets:
            if d.get("objet") == "Fiche de rentrée" and d.get("cle") in fiches:
                f = fiches[d["cle"]]
                if (d.get("date") or "") < (f.get("dateTransmission") or "") or lib_rentree(f.get("statut")) == lib_rentree(d.get("statut")):
                    continue
                if lib_rentree(f.get("statut")) == "Clôturée":
                    continue
                ex(f"UPDATE {RENTREE.table} SET statut=?, validePar=?, dateValidation=?, motifRenvoi=?, maj=? WHERE id=?",
                   (code_rentree(d["statut"]), d.get("decidePar"), d.get("date"),
                    d.get("motif") if lib_rentree(d["statut"]) == "Renvoyée" else f.get("motifRenvoi"), H.maintenant(), f["id"]))
                f["statut"] = code_rentree(d["statut"])
                n += 1
            elif d.get("objet") == "Courrier" and d.get("cle") in cour:
                c = cour[d["cle"]]
                rc = {s: i for i, s in enumerate(STATUTS_COURRIER)}
                if rc.get(d.get("statut"), 0) <= rc.get(c.get("statut") or "Brouillon", 0):
                    continue
                champ = "dateLecture" if d["statut"] == "Reçu" else "dateTraitement"
                ex(f"UPDATE reg_communication_courrier SET statut=?, {champ}=?, maj=? WHERE id=?", (d["statut"], d.get("date"), H.maintenant(), c["id"]))
                c["statut"] = d["statut"]
                n += 1
        return n
    H.territoire_appliquer_retours = appliquer_retours

    @app.before_request
    def _territoire_avant():
        ep = request.endpoint or ""
        if not g.get("user"):
            return None
        # rôle « observateur » (niveau national) : lecture seule, pages nationales uniquement
        if g.user["role"] == "observateur":
            libres = {"territoire_national", "logout", "login", "mon_compte", "static", "api_stats"}
            if ep not in libres:
                return redirect(url_for("territoire_national"))
            if request.method != "GET" and ep not in ("logout", "login", "mon_compte"):
                abort(403)
            return None
        va = request.view_args or {}
        if ep == "reg_page" and va.get("gcle") in ("territoire", "communication") and va.get("rcle") in ("rentree", "courrier"):
            appliquer_retours()
        # fiche de rentrée transmise : plus de modification à l'école (sauf renvoi)
        if ep in ("reg_enregistrer", "reg_supprimer") and va.get("gcle") == "territoire" and va.get("rcle") == "rentree" and va.get("rid"):
            x = q(f"SELECT statut FROM {RENTREE.table} WHERE id=?", (va["rid"],), un=True)
            if x and lib_rentree(x["statut"]) not in ("Brouillon", "Renvoyée") and not R.juridiction():
                flash("Fiche déjà transmise : elle ne se modifie plus (demandez un renvoi à la circonscription).", "warning")
                return redirect(url_for("reg_page", gcle="territoire", rcle="rentree"))
        if ep in ("reg_enregistrer", "reg_supprimer") and va.get("gcle") == "communication" and va.get("rcle") == "courrier" and va.get("rid"):
            x = q("SELECT statut FROM reg_communication_courrier WHERE id=?", (va["rid"],), un=True)
            if x and (x["statut"] or "Brouillon") != "Brouillon":
                flash("Courrier déjà envoyé : il ne se modifie plus.", "warning")
                return redirect(url_for("reg_page", gcle="communication", rcle="courrier"))
        return None

    @app.route("/territoire/rentree/<int:rid>/transmettre", methods=["POST"])
    @H.connexion_requise("territoire")
    def territoire_rentree_transmettre(rid):
        if not peut_ecrire_rentree():
            abort(403)
        x = q(f"SELECT * FROM {RENTREE.table} WHERE id=? AND portee=?", (rid, R.cle_portee("ecole")), un=True)
        if not x:
            abort(404)
        if lib_rentree(x["statut"]) not in ("Brouillon", "Renvoyée"):
            flash("Cette fiche est déjà transmise.", "info")
        else:
            ex(f"UPDATE {RENTREE.table} SET statut='TRANSMISE', dateTransmission=?, maj=? WHERE id=?", (date.today().isoformat(), H.maintenant(), rid))
            H.journal("rentree_transmise", f"{x['entite']} {x['annee']}")
            flash("Fiche transmise à la circonscription (elle part à la prochaine synchronisation).", "success")
        return redirect(url_for("reg_page", gcle="territoire", rcle="rentree", annee=x["annee"]))

    def peut_decider_jur():
        return R.juridiction() and g.get("user") and role_reel() in ROLES_JUR_DECIDE

    def fiches_juridiction(annee):
        rows = [dict(x) for x in q(f"SELECT * FROM {RENTREE.table} WHERE annee=? ORDER BY entite", (annee,))]
        try:
            ecoles = [dict(x) for x in q("SELECT id, nom, code FROM jur_ecoles WHERE COALESCE(actif,1)=1 ORDER BY nom")]
        except Exception:  # noqa: BLE001
            ecoles = []
        vus = {norm(x["entite"]) for x in rows}
        manquantes = [e for e in ecoles if norm(e["nom"]) not in vus]
        # v2.3.1 : écoles sans fiche — valeurs pré-remplies depuis leur dernière transmission (effectifs par cours, classes
        # ouvertes simples / jumelées / multigrades), avec la source et la date
        try:
            import jur_calc
            ids = [e["id"] for e in manquantes]
            if ids:
                secs = {r["ecole_id"]: r for r in q("SELECT ecole_id, donnees, maj FROM jur_sections WHERE section='effectifs' AND annee=? AND ecole_id IN ("
                                                    + ",".join("?" * len(ids)) + ")", (annee, *ids))}
                for e in manquantes:
                    r = secs.get(e["id"])
                    if not r:
                        continue
                    ef = jur_calc.effectifs(json.loads(r["donnees"] or "{}"))
                    e["transmis"] = {"g": ef["g"], "f": ef["f"], "t": ef["t"], "classes": ef["classes"], "simples": ef.get("classes_simples"),
                                     "jumelees": ef.get("classes_jumelees"), "multigrades": ef.get("classes_multigrades"),
                                     "source": "transmission de l'école", "maj": (r["maj"] or "")[:10]}
        except Exception:  # noqa: BLE001
            pass
        return rows, manquantes

    def transitions_jur(x):
        st = statut_de(x)
        if not peut_decider_jur():
            return []
        if edition() == "cs":
            return [("Validée CS", "Valider")] if st == "Transmise" else []
        if st == "Validée CS":
            return [("Validée département", "Valider (département)")]
        if st == "Validée département":
            return [("Clôturée", "Clôturer")]
        return []

    @app.route("/territoire/rentree/suivi")
    @H.connexion_requise("territoire")
    def territoire_rentree_suivi():
        if not R.juridiction():
            return redirect(url_for("reg_page", gcle="territoire", rcle="rentree"))
        appliquer_retours()
        annee = (request.args.get("annee") or "").strip() or R.annee_active()
        rows, manquantes = fiches_juridiction(annee)
        compte = {s: 0 for s in STATUTS_RENTREE}
        for x in rows:
            compte[statut_de(x)] = compte.get(statut_de(x), 0) + 1
        return render_template("territoire_rentree_suivi.html", G=G, ep_actif="territoire_rentree_suivi", rows=rows, manquantes=manquantes,
                               compte=compte, annee=annee, annees=R.annees_proposees([annee]), transitions=transitions_jur,
                               statut_de=statut_de, jj=R.jjmmaaaa, renvoi_possible=lambda x: peut_decider_jur()
                               and statut_de(x) in ("Transmise", "Validée CS", "Validée département"))
    G.page("territoire_rentree_suivi", "Suivi des fiches (juridiction)", apres=False)

    @app.route("/territoire/rentree/<int:rid>/decider", methods=["POST"])
    @H.connexion_requise("territoire")
    def territoire_rentree_decider(rid):
        if not peut_decider_jur():
            abort(403)
        x = q(f"SELECT * FROM {RENTREE.table} WHERE id=?", (rid,), un=True)
        if not x:
            abort(404)
        x = dict(x)
        cible = request.form.get("statut") or ""
        motif = (request.form.get("motif") or "").strip()[:600]
        permis = [s for s, _l in transitions_jur(x)]
        if cible == "Renvoyée":
            if statut_de(x) not in ("Transmise", "Validée CS", "Validée département") or not motif:
                flash("Renvoi : indiquez le motif (ce qui est à corriger).", "danger")
                return redirect(url_for("territoire_rentree_suivi", annee=x["annee"]))
        elif cible not in permis:
            flash("Décision impossible pour le statut actuel de la fiche.", "warning")
            return redirect(url_for("territoire_rentree_suivi", annee=x["annee"]))
        niv, ent = R.entite_courante()
        auteur = f"{R.NIVEAUX_LIB.get(niv, niv)} — {ent}".strip(" —")
        ex(f"UPDATE {RENTREE.table} SET statut=?, validePar=?, dateValidation=?, motifRenvoi=?, maj=? WHERE id=?",
           (code_rentree(cible), auteur, date.today().isoformat(), motif if cible == "Renvoyée" else x.get("motifRenvoi"), H.maintenant(), rid))
        ajouter_retour("Fiche de rentrée", cle_rentree(x), x["entite"], code_rentree(cible), motif)
        H.journal("rentree_" + CODES_RENTREE.get(cible, cible).lower(), f"{x['entite']} {x['annee']}")
        flash(f"Fiche de {x['entite']} : {cible.lower()}.", "success")
        return redirect(url_for("territoire_rentree_suivi", annee=x["annee"]))

    # ------------------------------------------------------------------ 7. référentiel des structures
    STRUCT = G.registre("structures", "Référentiel des structures administratives", [
        ("nom", "Nom de la structure", "texte"), ("sigle", "Sigle / code", "texte"), ("type", "Type", "choix:types_struct"),
        ("ordre", "Ordre d'enseignement", "choix:ordres"), ("rattachement", "Structure de rattachement", "liste:structures"),
        ("departement", "Département", "texte"), ("commune", "Commune", "texte"), ("responsable", "Responsable", "texte"),
        ("telephone", "Téléphone", "texte"), ("active", "Active", "oui_non")],
        unite="structure", oblig="nom", ordre="type, nom", portee="structure", par_annee=False, feuille="Structures administratives",
        onglet="Référentiel des structures", unique=("nom",), filtres=("type",),
        colonnes=("nom", "sigle", "type", "ordre", "rattachement", "departement", "commune", "responsable", "active"),
        defauts=lambda: {"type": "Service", "ordre": "Maternel et primaire", "active": "Oui"}, doc="Référentiel des structures administratives",
        aide="Arbre des structures (ministère → directions → DDEMP → services → CS → divisions) : les noms sont des données, à ajuster "
             "selon le texte officiel des attributions. Le rattachement se choisit parmi les structures déjà saisies.")

    def amorcer_structures():
        """Premier affichage de l'arbre (CS / DDEMP) : ministère, la structure du compte et ses services (une seule fois)."""
        p = R.cle_portee("structure")
        if not R.juridiction() or q("SELECT 1 FROM reg_territoire_structures WHERE portee=? LIMIT 1", (p,), un=True):
            return
        nom = (cfg.ECOLE.get("nom") or "").strip() or ("Direction départementale" if edition() == "ddemp" else "Circonscription scolaire")
        lignes = [("Ministère des Enseignements Maternel et Primaire", "MEMP", "Ministère", "Tous", "")]
        lignes.append((nom, cfg.ECOLE.get("sigle") or "", "Direction départementale" if edition() == "ddemp" else "Circonscription scolaire",
                       "Maternel et primaire", lignes[0][0]))
        try:
            for s in q("SELECT nom, sigle FROM jur_services WHERE COALESCE(actif,1)=1 ORDER BY ordre, nom"):
                lignes.append((s["nom"], s["sigle"] or "", "Service" if edition() == "ddemp" else "Division", "Maternel et primaire", nom))
        except Exception:  # noqa: BLE001
            pass
        vus = set()
        for n_, sg, ty, od, par in lignes:
            if norm(n_) in vus:
                continue
            vus.add(norm(n_))
            ex("INSERT INTO reg_territoire_structures (portee, annee, nom, sigle, type, ordre, rattachement, active, cree_le, cree_par, maj) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (p, R.annee_active(), n_, sg, ty, od, par, "Oui", H.maintenant(), g.user["id"], H.maintenant()))

    def arbre():
        rows, vus_ = [], set()
        for x in q("SELECT * FROM reg_territoire_structures WHERE portee=? ORDER BY maj DESC, nom", (R.cle_portee("structure"),)):
            if norm(x["nom"]) not in vus_:                 # structure reçue de la DDEMP et saisie ici : une seule fois
                vus_.add(norm(x["nom"]))
                rows.append(dict(x))
        par_nom = {norm(x["nom"]): x for x in rows}
        enfants = {}
        racines = []
        for x in rows:
            p = norm(x.get("rattachement"))
            if p and p in par_nom and p != norm(x["nom"]):
                enfants.setdefault(p, []).append(x)
            else:
                racines.append(x)
        ordre = {t: i for i, t in enumerate(TYPES_STRUCT)}

        def noeud(x, prof, vus):
            k = norm(x["nom"])
            if k in vus or prof > 12:
                return {"x": x, "enfants": []}
            vus = vus | {k}
            ff = sorted(enfants.get(k, []), key=lambda y: (ordre.get(y.get("type"), 99), y["nom"]))
            return {"x": x, "enfants": [noeud(y, prof + 1, vus) for y in ff]}
        return [noeud(x, 0, set()) for x in sorted(racines, key=lambda y: (ordre.get(y.get("type"), 99), y["nom"]))]

    @app.route("/territoire/structures/arbre", methods=["GET", "POST"])
    @H.connexion_requise("territoire")
    def territoire_arbre():
        if request.method == "POST":
            if not G.peut_ecrire(STRUCT):
                abort(403)
            amorcer_structures()
            H.journal("structures_amorcees", "")
            return redirect(url_for("territoire_arbre"))
        return render_template("territoire_arbre.html", G=G, ep_actif="territoire_arbre", arbre=arbre(), jur=R.juridiction(),
                               peut_ecrire=G.peut_ecrire(STRUCT))
    G.page("territoire_arbre", "Arbre des structures")

    # ------------------------------------------------------------------ 8. niveau national (lecture seule) et API
    def agregats(annee):
        out = {"annee": annee, "structure": cfg.ECOLE.get("nom") or "", "edition": edition(), "genere_le": H.maintenant()}
        try:
            calc = H.pilotage_calculer(annee, "cs" if edition() == "ddemp" else "zone", {})
            ind = calc.get("ind") or {}
            out["indicateurs"] = {k: ind.get(k) for k in INDICATEURS_API if k in ind}
            out["infrastructures"] = ind.get("infra") or {}
            out["par_groupe"] = [{"nom": n, "ecoles": i.get("ecoles"), "t": i.get("t"), "f": i.get("f")} for n, i in calc.get("groupes") or []]
            out["nb_ecoles"] = calc.get("nb_ecoles")
        except Exception:  # noqa: BLE001
            out["indicateurs"] = {}
        rows, manquantes = fiches_juridiction(annee) if R.juridiction() else ([], [])
        st = {s: 0 for s in STATUTS_RENTREE}
        for x in rows:
            st[statut_de(x)] = st.get(statut_de(x), 0) + 1
        out["fiches_rentree"] = {CODES_RENTREE[k]: v for k, v in st.items()}
        out["fiches_rentree"]["NON_RECUE"] = len(manquantes)
        try:
            vis = q("SELECT COALESCE(statutVisite,'') s, COUNT(*) n FROM reg_inspection_visites WHERE annee=? GROUP BY COALESCE(statutVisite,'')", (annee,))
            out["visites"] = {(x["s"] or "Non précisé"): x["n"] for x in vis}
        except Exception:  # noqa: BLE001
            out["visites"] = {}
        try:
            c = q("SELECT COALESCE(statut,'Brouillon') s, COUNT(*) n FROM reg_communication_courrier WHERE annee=? GROUP BY 1", (annee,))
            out["courrier"] = {x["s"]: x["n"] for x in c}
        except Exception:  # noqa: BLE001
            out["courrier"] = {}
        return out

    def jeton_ok(j):
        h = (q("SELECT valeur FROM parametres WHERE cle='api_stats_jeton'", un=True) or {"valeur": ""})["valeur"] or ""
        return bool(h and j) and secrets.compare_digest(h, hashlib.sha256(j.encode()).hexdigest())

    @app.route("/territoire/national", methods=["GET", "POST"])
    @H.connexion_requise("territoire_national")
    def territoire_national():
        if not R.juridiction():
            abort(404)
        nouveau = None
        if request.method == "POST":
            if g.user["role"] not in ("admin", "fondateur", "responsable"):
                abort(403)
            if request.form.get("action") == "retirer":
                ex("DELETE FROM parametres WHERE cle='api_stats_jeton'")
                H.journal("api_stats_jeton_retire", "")
                flash("Jeton retiré : /api/stats.json est fermé.", "success")
            else:
                nouveau = secrets.token_urlsafe(24)
                ex("INSERT INTO parametres (cle, valeur) VALUES ('api_stats_jeton', ?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur",
                   (hashlib.sha256(nouveau.encode()).hexdigest(),))
                H.journal("api_stats_jeton_cree", "")
        annee = (request.args.get("annee") or "").strip() or R.annee_active()
        actif = bool((q("SELECT valeur FROM parametres WHERE cle='api_stats_jeton'", un=True) or {"valeur": ""})["valeur"])
        return render_template("territoire_national.html", G=G, ep_actif="territoire_national", a=agregats(annee), annee=annee,
                               annees=R.annees_proposees([annee]), nouveau=nouveau, jeton_actif=actif,
                               admin=g.user["role"] in ("admin", "fondateur", "responsable"), observateur=g.user["role"] == "observateur",
                               libs=dict(STATUTS_RENTREE_LIB))
    G.page("territoire_national", "Niveau national")

    @app.route("/api/stats.json")
    def api_stats():
        j = request.headers.get("X-Jeton") or request.args.get("jeton") or ""
        if not R.juridiction() or not jeton_ok(j):
            return jsonify({"erreur": "jeton manquant ou invalide"}), 401
        annee = request.args.get("annee") or R.annee_active()
        if not re.fullmatch(r"\d{4}-\d{4}", annee):
            annee = R.annee_active()
        H.journal("api_stats", annee)
        return jsonify(agregats(annee))

    # ================================================================== 2. courrier administratif (module Communication)
    Gc = R.GROUPES.get("communication")

    def cle_courrier(x):
        return f"courrier|{norm(x.get('entite'))}|{norm(x.get('reference'))}|{norm(x.get('objet'))}|{x.get('date') or ''}"

    if Gc is not None:
        Gc.listes.update({"types_courrier": TYPES_COURRIER, "niv_courrier": NIV_COURRIER})

        def actions_courrier(x):
            if (x.get("statut") or "Brouillon") == "Brouillon" and x.get("portee") == R.cle_portee("structure") and Gc.peut_ecrire():
                return [("post:" + url_for("territoire_courrier_envoyer", cid=x["id"]), "Envoyer", "envoyer")]
            return []

        COUR = Gc.registre("courrier", "Courrier administratif", [
            ("type", "Type", "choix:types_courrier"), ("reference", "Référence (n°)", "texte"), ("date", "Date", "date"),
            ("objet", "Objet", "texte"), ("destNiveau", "Niveau du destinataire", "choix:niv_courrier"),
            ("destinataire", "Destinataire", "texte"), ("texte", "Texte", "long"), ("pieces", "Pièces jointes / ampliations", "long"),
            ("signataire", "Signataire (nom et qualité)", "texte")],
            unite="courrier", oblig="objet", ordre="date DESC, id DESC", portee="structure", feuille="Courrier administratif",
            onglet="Courrier envoyé", entite=True, unique=("reference", "objet"), filtres=("type", "destNiveau"),
            colonnes=("niveau", "entite", "type", "reference", "date", "objet", "destNiveau", "destinataire"),
            calcul=lambda x: {"Statut": x.get("statut") or "Brouillon", "Lu le": R.jjmmaaaa(x.get("dateLecture")),
                              "Traité le": R.jjmmaaaa(x.get("dateTraitement"))},
            actions=actions_courrier,
            defauts=lambda: dict(zip(("niveau", "entite"), R.entite_courante()), type="Rapport", date=date.today().isoformat(),
                                 destNiveau="DDEMP" if edition() == "cs" else "CS"),
            doc="Courrier administratif",
            aide="Courrier de l'école vers la CS, de la CS vers la DDEMP (rapports, demandes, comptes rendus…). « Envoyer » le fait partir "
                 "à la prochaine synchronisation ; le destinataire l'ouvre (accusé de lecture daté), puis le traite ou l'archive. "
                 "Les notes de service vers les écoles restent dans « Notes, circulaires et convocations ».")
        for col in ("statut", "dateEnvoi", "dateLecture", "lecteur", "dateTraitement", "traitePar"):
            H.ajouter_colonne(COUR.table, col, "TEXT")

        def inscrire_secretariat(sens, correspondant, objet, reference):
            """Registre du courrier du secrétariat (arrivée / départ, numérotation A-AAAA-0001 / D-AAAA-0001) : même numérotation."""
            try:
                d = date.today().isoformat()
                cid = ex("INSERT INTO courriers (sens, date, correspondant, objet, reference, fichier, saisi_par, cree_le) VALUES (?,?,?,?,?,?,?,?)",
                         (sens, d, (correspondant or "—")[:200], (objet or "")[:300], (reference or None) and reference[:100], None,
                          g.user["id"], H.maintenant()))
                rang = q("SELECT COUNT(*) n FROM courriers WHERE sens=? AND substr(date,1,4)=? AND id<=?", (sens, d[:4], cid), un=True)["n"]
                ex("UPDATE courriers SET numero=? WHERE id=?", (f"{'A' if sens == 'arrivee' else 'D'}-{d[:4]}-{rang:04d}", cid))
            except Exception:  # noqa: BLE001
                pass

        def courrier_recu():
            niv, _ent = R.entite_courante()
            mien = R.cle_portee("structure")
            try:
                rows = [dict(x) for x in q("SELECT * FROM reg_communication_courrier WHERE portee<>? AND COALESCE(statut,'Brouillon')<>'Brouillon' "
                                           "ORDER BY date DESC, id DESC", (mien,))]
            except Exception:  # noqa: BLE001
                return []
            return [x for x in rows if (x.get("destNiveau") or "CS") == niv]

        def non_lus():
            return [x for x in courrier_recu() if (x.get("statut") or "") == "Envoyé"]
        H.territoire_courrier_non_lus = non_lus

        @app.route("/territoire/courrier/<int:cid>/envoyer", methods=["POST"])
        @H.connexion_requise("notes_service")
        def territoire_courrier_envoyer(cid):
            if not Gc.peut_ecrire():
                abort(403)
            x = q("SELECT * FROM reg_communication_courrier WHERE id=? AND portee=?", (cid, R.cle_portee("structure")), un=True)
            if not x:
                abort(404)
            if (x["statut"] or "Brouillon") == "Brouillon":
                ex("UPDATE reg_communication_courrier SET statut='Envoyé', dateEnvoi=?, maj=? WHERE id=?", (date.today().isoformat(), H.maintenant(), cid))
                H.journal("courrier_envoye", f"{x['reference'] or ''} {x['objet']}")
                inscrire_secretariat("depart", " ".join(v for v in (x["destNiveau"] or "", x["destinataire"] or "") if v), x["objet"], x["reference"])
                flash("Courrier envoyé (il part à la prochaine synchronisation).", "success")
            return redirect(url_for("reg_page", gcle="communication", rcle="courrier", annee=x["annee"]))

        @app.route("/territoire/courrier")
        @H.connexion_requise("notes_service")
        def territoire_courrier_recu():
            appliquer_retours()
            return render_template("territoire_courrier.html", G=Gc, ep_actif="territoire_courrier_recu", rows=courrier_recu(),
                                   jj=R.jjmmaaaa, NIV=R.NIVEAUX_LIB, peut_ec=Gc.peut_ecrire(), detail=None)
        Gc.page("territoire_courrier_recu", "Courrier reçu")

        @app.route("/territoire/courrier/<int:cid>", methods=["GET", "POST"])
        @H.connexion_requise("notes_service")
        def territoire_courrier_detail(cid):
            x = next((c for c in courrier_recu() if c["id"] == cid), None)
            if not x:
                abort(404)
            nom = (g.user["nom"] or "").strip() or g.user["identifiant"]
            if request.method == "POST":
                if not Gc.peut_ecrire():
                    abort(403)
                cible = request.form.get("statut")
                if cible in ("Traité", "Archivé"):
                    ex("UPDATE reg_communication_courrier SET statut=?, dateTraitement=?, traitePar=?, maj=? WHERE id=?",
                       (cible, date.today().isoformat(), nom, H.maintenant(), cid))
                    ajouter_retour("Courrier", cle_courrier(x), x.get("entite") or "", cible, (request.form.get("observations") or "")[:400])
                    H.journal("courrier_" + ("traite" if cible == "Traité" else "archive"), f"{x.get('reference') or ''} {x['objet']}")
                    flash(f"Courrier {cible.lower()}.", "success")
                return redirect(url_for("territoire_courrier_recu"))
            if (x.get("statut") or "") == "Envoyé":                    # accusé de lecture daté
                ex("UPDATE reg_communication_courrier SET statut='Reçu', dateLecture=?, lecteur=?, maj=? WHERE id=?",
                   (date.today().isoformat(), nom, H.maintenant(), cid))
                ajouter_retour("Courrier", cle_courrier(x), x.get("entite") or "", "Reçu")
                H.journal("courrier_lu", f"{x.get('reference') or ''} {x['objet']}")
                inscrire_secretariat("arrivee", x.get("entite") or "", x.get("objet"), x.get("reference"))
                x.update(statut="Reçu", dateLecture=date.today().isoformat(), lecteur=nom)
            return render_template("territoire_courrier.html", G=Gc, ep_actif="territoire_courrier_recu", rows=[], detail=x,
                                   jj=R.jjmmaaaa, NIV=R.NIVEAUX_LIB, peut_ec=Gc.peut_ecrire())

    # ================================================================== 3. visites de classe : statut et prochaine visite
    Gi = R.GROUPES.get("inspection")
    if Gi is not None and "visites" in Gi.registres:
        rv = Gi.registres["visites"]
        Gi.listes["statuts_visite"] = STATUTS_VISITE
        if not any(c[0] == "statutVisite" for c in rv.champs):
            rv.champs += [("statutVisite", "Statut de la visite", "choix:statuts_visite"), ("prochaineVisite", "Date de la prochaine visite", "date")]
        for col in ("statutVisite", "prochaineVisite"):
            H.ajouter_colonne(rv.table, col, "TEXT")
        if rv.colonnes:
            rv.colonnes = tuple(rv.colonnes) + ("statutVisite", "prochaineVisite")
        if "statutVisite" not in rv.filtres:
            rv.filtres.append("statutVisite")
        _def = rv.defauts
        rv.defauts = lambda: dict(_def() if _def else {}, statutVisite="Réalisée")
        _act = rv.actions

        def actions_visite(x):
            out = list(_act(x) if _act else [])
            if (x.get("statutVisite") or "") == "Rapport rédigé" and R.juridiction() and g.get("user") and role_reel() in ROLES_JUR_DECIDE | {"cp"}:
                out.append(("post:" + url_for("territoire_visite_valider", vid=x["id"]), "Valider", "valider"))
            return out
        rv.actions = actions_visite

        @app.route("/territoire/visites/<int:vid>/valider", methods=["POST"])
        @H.connexion_requise("inspection_ped")
        def territoire_visite_valider(vid):
            if not (R.juridiction() and role_reel() in ROLES_JUR_DECIDE | {"cp"}):
                abort(403)
            x = q(f"SELECT * FROM {rv.table} WHERE id=? AND portee=?", (vid, R.cle_portee("ecole")), un=True)
            if not x:
                abort(404)
            if (x["statutVisite"] or "") == "Rapport rédigé":
                ex(f"UPDATE {rv.table} SET statutVisite='Validée', maj=? WHERE id=?", (H.maintenant(), vid))
                H.journal("visite_validee", f"{x['enseignant']} {x['date']}")
                flash("Visite validée.", "success")
            return redirect(url_for("reg_page", gcle="inspection", rcle="visites", annee=x["annee"]))

    def alertes_territoire():
        out = []
        auj = date.today()
        try:
            if Gi is not None and "visites" in Gi.registres:
                rv_ = Gi.registres["visites"]
                for x in q(f"SELECT * FROM {rv_.table} WHERE portee=?", (R.cle_portee("ecole"),)):
                    x = dict(x)
                    if x.get("statutVisite") == "Planifiée" and (x.get("date") or "9999") < auj.isoformat():
                        out.append(("visite", "Visite planifiée dépassée", f"{x.get('enseignant')} — prévue le {R.jjmmaaaa(x.get('date'))}",
                                    url_for("reg_page", gcle="inspection", rcle="visites", annee=x["annee"])))
                    pv = x.get("prochaineVisite") or ""
                    if pv and auj.isoformat() <= pv <= (auj + timedelta(days=14)).isoformat():
                        out.append(("visite", "Prochaine visite", f"{x.get('enseignant')} — le {R.jjmmaaaa(pv)}",
                                    url_for("reg_page", gcle="inspection", rcle="visites", annee=x["annee"])))
        except Exception:  # noqa: BLE001
            pass
        try:
            n = len(H.territoire_courrier_non_lus()) if getattr(H, "territoire_courrier_non_lus", None) else 0
            if n:
                out.append(("courrier", "Courrier non lu", f"{n} courrier(s) reçu(s) non lu(s)", url_for("territoire_courrier_recu")))
        except Exception:  # noqa: BLE001
            pass
        try:
            if not R.juridiction():
                for x in q(f"SELECT * FROM {RENTREE.table} WHERE portee=? AND statut IN ('RENVOYEE', 'Renvoyée')", (R.cle_portee("ecole"),)):
                    out.append(("rentree", "Fiche de rentrée renvoyée", f"{x['annee']} — {x['motifRenvoi'] or ''}",
                                url_for("reg_page", gcle="territoire", rcle="rentree", annee=x["annee"])))
        except Exception:  # noqa: BLE001
            pass
        return out
    H.territoire_alertes = alertes_territoire

    # ================================================================== 4. présence du personnel
    Gp = R.Groupe(app, H, "presences", "Présence du personnel", "territoire", ico="personne",
                  sous_titre="Présence quotidienne des agents (présent, absent, retard, congé, mission, formation, maladie), appel du jour, "
                             "statistiques du mois",
                  listes={"statuts_presence": STATUTS_PRESENCE, "personnel": noms_personnel})
    PRES = Gp.registre("agents", "Présence du personnel", [
        ("date", "Date", "date"), ("agent", "Agent", "liste:personnel"), ("fonction", "Fonction", "texte"),
        ("statut", "Statut", "choix:statuts_presence"), ("motif", "Motif / justificatif", "long")],
        unite="pointage", oblig="agent", ordre="date DESC, agent", portee="structure", feuille="Présence du personnel", onglet="Registre",
        unique=("date", "agent"), filtres=("statut",), doc="Registre de présence du personnel",
        defauts=lambda: {"date": date.today().isoformat(), "statut": "Présent"})

    def fonction_de():
        out = {}
        try:
            if R.juridiction() and not g.get("ecole"):
                for r in q("SELECT nom, prenoms, poste FROM jur_agents WHERE cs_id IS NULL AND COALESCE(actif,1)=1"):
                    out[f"{r['nom']} {r['prenoms'] or ''}".strip()] = r["poste"] or ""
            else:
                for r in q("SELECT nom, prenoms, fonction FROM personnel WHERE actif=1"):
                    out[f"{r['nom']} {r['prenoms'] or ''}".strip()] = r["fonction"] or ""
        except Exception:  # noqa: BLE001
            pass
        return out

    @app.route("/territoire/presences/appel", methods=["GET", "POST"])
    @H.connexion_requise("territoire")
    def territoire_presence_appel():
        jour = (request.values.get("date") or "").strip()[:10] or date.today().isoformat()
        try:
            date.fromisoformat(jour)
        except ValueError:
            jour = date.today().isoformat()
        p = R.cle_portee("structure")
        agents = noms_personnel()
        fonctions = fonction_de()
        if request.method == "POST":
            if not Gp.peut_ecrire(PRES):
                abort(403)
            n = 0
            for i, a in enumerate(agents):
                st = request.form.get(f"s{i}")
                if st not in STATUTS_PRESENCE:
                    continue
                motif = (request.form.get(f"m{i}") or "").strip()[:300]
                x = q("SELECT id FROM reg_presences_agents WHERE portee=? AND date=? AND agent=?", (p, jour, a), un=True)
                if x:
                    ex("UPDATE reg_presences_agents SET statut=?, motif=?, fonction=?, maj=? WHERE id=?", (st, motif, fonctions.get(a, ""), H.maintenant(), x["id"]))
                else:
                    ex("INSERT INTO reg_presences_agents (portee, annee, date, agent, fonction, statut, motif, cree_le, cree_par, maj) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)", (p, R.annee_active(), jour, a, fonctions.get(a, ""), st, motif, H.maintenant(), g.user["id"], H.maintenant()))
                n += 1
            H.journal("presence_personnel", f"{jour} : {n} agent(s)")
            flash(f"Appel du {R.jjmmaaaa(jour)} enregistré ({n} agent(s)).", "success")
            return redirect(url_for("territoire_presence_appel", date=jour))
        deja = {x["agent"]: dict(x) for x in q("SELECT * FROM reg_presences_agents WHERE portee=? AND date=?", (p, jour))}
        return render_template("territoire_presence_appel.html", G=Gp, ep_actif="territoire_presence_appel", jour=jour, agents=agents,
                               deja=deja, fonctions=fonctions, statuts=STATUTS_PRESENCE, peut_ec=Gp.peut_ecrire(PRES), jj=R.jjmmaaaa)
    Gp.page("territoire_presence_appel", "Appel du jour", apres=False)

    def stats_mois(mois):
        p = R.cle_portee("structure")
        rows = q("SELECT agent, statut, COUNT(*) n FROM reg_presences_agents WHERE portee=? AND substr(date,1,7)=? GROUP BY agent, statut", (p, mois))
        par = {}
        for r in rows:
            par.setdefault(r["agent"], {s: 0 for s in STATUTS_PRESENCE})[r["statut"] if r["statut"] in STATUTS_PRESENCE else "Absent"] += r["n"]
        lignes = []
        tot = {s: 0 for s in STATUTS_PRESENCE}
        for a in sorted(par):
            c = par[a]
            j = sum(c.values())
            pres = c["Présent"] + c["Retard"]
            lignes.append({"agent": a, "c": c, "jours": j, "taux": round(100.0 * pres / j, 1) if j else None})
            for s in STATUTS_PRESENCE:
                tot[s] += c[s]
        tj = sum(tot.values())
        return lignes, tot, (round(100.0 * (tot["Présent"] + tot["Retard"]) / tj, 1) if tj else None)

    @app.route("/territoire/presences/mois")
    @H.connexion_requise("territoire")
    def territoire_presence_mois():
        mois = (request.args.get("mois") or "").strip()[:7]
        if not re.fullmatch(r"\d{4}-\d{2}", mois):
            mois = date.today().strftime("%Y-%m")
        lignes, tot, taux = stats_mois(mois)
        return render_template("territoire_presence_mois.html", G=Gp, ep_actif="territoire_presence_mois", mois=mois, lignes=lignes,
                               tot=tot, taux=taux, statuts=STATUTS_PRESENCE)
    Gp.page("territoire_presence_mois", "Statistiques du mois")
    H.territoire_stats_presence = stats_mois

    # ================================================================== 6. incidents de discipline
    Gd = R.Groupe(app, H, "discipline", "Discipline des élèves", "territoire", ico="attention",
                  sous_titre="Incidents de discipline : date, description, sanction, décision, information des parents, suivi",
                  listes={"sanctions": SANCTIONS})
    Gd.registre("incidents", "Incidents de discipline", [
        ("eleve", "Élève", "eleve"), ("date", "Date de l'incident", "date"), ("lieu", "Lieu", "texte"), ("description", "Description", "long"),
        ("sanction", "Sanction", "liste:sanctions"), ("decidePar", "Décidé par", "texte"), ("parents", "Parents informés (Oui/Non)", "oui_non"),
        ("suivi", "Suivi / observations", "long")],
        unite="incident", oblig="eleve", ordre="date DESC, id DESC", portee="ecole", feuille="Incidents de discipline", onglet="Incidents",
        filtres=("sanction",), doc="Registre des incidents de discipline",
        defauts=lambda: {"date": date.today().isoformat(), "parents": "Non"},
        aide="Données d'élèves (mineurs) : elles restent dans l'école (jamais envoyées à la CS). Sanctions conformes au règlement "
             "intérieur ; les châtiments corporels sont interdits.")

    # ================================================================== 5. fiche signalétique de l'école
    def peut_signaletique():
        r_ = role_reel()
        return bool(g.get("user")) and edition() != "enseignant" and (r_ in ROLES_ECOLE_DECIDE or (R.juridiction() and g.get("ecole") and r_ in ROLES_JUR_DECIDE))

    def lire_coord(v, lim):
        v = (v or "").strip().replace(",", ".")
        if not v:
            return ""
        try:
            f = float(v)
        except ValueError:
            return None
        return round(f, 6) if -lim <= f <= lim else None

    @app.route("/territoire/ecole", methods=["GET", "POST"])
    @H.connexion_requise("territoire")
    def territoire_ecole():
        if R.juridiction() and not g.get("ecole"):
            flash("Ouvrez d'abord une école de la juridiction.", "info")
            return redirect(url_for("territoire_arbre"))
        s = signaletique()
        if request.method == "POST":
            if not peut_signaletique():
                abort(403)
            nv = {k: (request.form.get(k) or "").strip()[:120] for k, _l in CHAMPS_SIGNALETIQUE}
            lat, lon = lire_coord(nv["latitude"], 90), lire_coord(nv["longitude"], 180)
            if lat is None or lon is None:
                flash("Coordonnées invalides : latitude entre -90 et 90, longitude entre -180 et 180 (degrés décimaux, ex. 7.3637 et 2.6086).", "danger")
                return redirect(url_for("territoire_ecole"))
            nv.update(latitude=lat, longitude=lon)
            if nv["statutJuridique"] not in STATUTS_JUR + [""]:
                nv["statutJuridique"] = ""
            for k in ("salles", "latrines"):
                nv[k] = int(nv[k]) if nv[k].isdigit() else ""
            for k in ("pointEau", "electricite"):
                nv[k] = nv[k] if nv[k] in ("Oui", "Non") else ""
            for k in ("dateAutorisation", "dateAgrement"):
                if nv[k] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", nv[k]):
                    nv[k] = ""
            H.doc_ecrire(f"signaletique:e{H.eco()}", nv)
            try:
                miroir_signaletique(nv)
            except Exception:  # noqa: BLE001
                pass
            H.journal("signaletique_ecole", f"école {H.eco()}")
            flash("Fiche signalétique enregistrée.", "success")
            return redirect(url_for("territoire_ecole"))
        calc = {}
        try:
            import m_pilotage
            pat = H.patrimoine_synthese(H.eco())
            i = m_pilotage.infra(pat)
            calc = {"salles": i["salles"], "latrines": i["cabines"], "pointEau": "Oui" if i["eau"] else "Non",
                    "electricite": "Oui" if i["electricite"] else "Non"}
        except Exception:  # noqa: BLE001
            pass
        return render_template("territoire_ecole.html", G=G, ep_actif="territoire_ecole", s=s, calc=calc, champs=CHAMPS_SIGNALETIQUE,
                               statuts_jur=STATUTS_JUR, peut_ec=peut_signaletique(), prive=(edition() == "privee"))
    G.page("territoire_ecole", "Fiche signalétique de l'école", apres=False)

    # ------------------------------------------------------------------ besoins de l'école : catégories ajoutées (registre existant)
    Gb = R.GROUPES.get("patrimoine")
    if Gb is not None and isinstance(Gb.listes.get("cat_besoin"), list):
        for c in ("Enseignant", "Infrastructure", "Eau, hygiène et assainissement"):
            if c not in Gb.listes["cat_besoin"]:
                Gb.listes["cat_besoin"].insert(len(Gb.listes["cat_besoin"]) - 1, c)

    # ------------------------------------------------------------------ fiche signalétique : registre « territoire:signaletique » (montant),
    # comme les applications JS (même nom de type et mêmes champs) ; la page de l'école l'écrit à chaque enregistrement
    SIGN = G.registre("signaletique", "Fiche signalétique des écoles", [
        ("latitude", "Latitude", "decimal"), ("longitude", "Longitude", "decimal"), ("statutJuridique", "Statut juridique", "texte"),
        ("numeroAutorisation", "N° d’autorisation", "texte"), ("dateAutorisation", "Date d’autorisation", "date"),
        ("numeroAgrement", "N° d’agrément", "texte"), ("dateAgrement", "Date d’agrément", "date"), ("salles", "Salles", "entier"),
        ("latrines", "Latrines", "entier"), ("pointEau", "Point d’eau", "texte"), ("electricite", "Électricité", "texte")],
        unite="fiche", oblig="entite", ordre="entite", portee="ecole", par_annee=False, feuille="Fiche signalétique", onglet="Signalétique (reçues)",
        entite=True, niveaux=["ECOLE"], unique=("entite",), ecriture=lambda: False, doc="Fiches signalétiques des écoles",
        aide="Fiches signalétiques reçues des écoles (synchronisation) ; chaque école remplit la sienne dans « Fiche signalétique de l'école ».")

    def miroir_signaletique(nv):
        p_ = R.cle_portee("ecole")
        ent = R.entite_courante()[1]
        cols = [k for k, _l, _t in SIGN.champs if k not in ("niveau", "entite")]
        vals = [nv.get(k) if nv.get(k) not in ("",) else None for k in cols]
        x = q("SELECT id FROM reg_territoire_signaletique WHERE portee=?", (p_,), un=True)
        if x:
            ex("UPDATE reg_territoire_signaletique SET entite=?, " + ", ".join(f"{k}=?" for k in cols) + ", maj=? WHERE id=?",
               (ent, *vals, H.maintenant(), x["id"]))
        else:
            ex("INSERT INTO reg_territoire_signaletique (portee, annee, niveau, entite, " + ", ".join(cols) + ", cree_le, cree_par, maj) VALUES (?,?,?,?,"
               + ",".join("?" * len(cols)) + ",?,?,?)", (p_, R.annee_active(), "ECOLE", ent, *vals, H.maintenant(), g.user["id"], H.maintenant()))

    # ------------------------------------------------------------------ v2.3.2 : la fiche signalétique monte (paquet de transmission)
    def section_signaletique(annee):
        if R.juridiction() and not g.get("ecole"):
            return None, None
        s_ = {k: v for k, v in signaletique().items() if v not in (None, "")}
        return (s_ or None), (None if s_ else "Fiche signalétique non remplie (menu Territoire et suivi).")
    if isinstance(getattr(H, "sections_extra", None), dict):
        H.sections_extra["signaletique"] = section_signaletique
    try:
        import m_transmission
        m_transmission.NOMS_RUBRIQUES.setdefault("signaletique", "Fiche signalétique (GPS, autorisation, agrément, eau, latrines)")
    except Exception:  # noqa: BLE001
        pass

    # ------------------------------------------------------------------ CS / DDEMP : pages de la structure (sans école ouverte)
    try:
        import a_integration as AI
        if "/territoire" not in AI.PREFIXES_STRUCTURE:
            AI.PREFIXES_STRUCTURE = tuple(AI.PREFIXES_STRUCTURE) + ("/territoire",)
        if "territoire_" not in AI.PREFIXES_EP_COMMUNS:
            AI.PREFIXES_EP_COMMUNS = tuple(AI.PREFIXES_EP_COMMUNS) + ("territoire_",)
    except Exception:  # noqa: BLE001
        pass

    # ------------------------------------------------------------------ export PDF / Word des pages du module
    try:
        import m_export
        if "/territoire" not in m_export.PREFIXES:
            m_export.PREFIXES = tuple(m_export.PREFIXES) + ("/territoire",)
    except Exception:  # noqa: BLE001
        pass


STATUTS_RENTREE_LIB = [(v, k) for k, v in CODES_RENTREE.items()]
LIB_RENTREE = {v: k for k, v in CODES_RENTREE.items()}


def lib_rentree(v):
    """Statut stocké (code commun aux applications : BROUILLON, TRANSMISE…) ou libellé -> libellé affiché."""
    v = (v or "").strip()
    return LIB_RENTREE.get(v, v) or "Brouillon"


def code_rentree(v):
    """Libellé ou code -> code stocké et échangé (BROUILLON, TRANSMISE, VALIDEE_CS, VALIDEE_DEPARTEMENT, CLOTUREE, RENVOYEE)."""
    v = (v or "").strip()
    return CODES_RENTREE.get(v, v if v in LIB_RENTREE else "BROUILLON")
