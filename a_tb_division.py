# -*- coding: utf-8 -*-
"""Tableau de bord et tableau synoptique de chaque division / chef de service (v2.5.2).

Une seule application sert toutes les divisions : le périmètre d'accès de chaque compte (chef de service, agent) est
déjà borné à sa division (a_integration.perimetre_utilisateur). Ce module ajoute, pour chaque division :

* un TABLEAU DE BORD : indicateurs de la division (agents, comptes, modules, plan d'action, retards, échéances à venir)
  et indicateurs de terrain propres à son métier (écoles, visites, UP, CEP, transmissions…), tirés des données déjà
  saisies dans l'application ;
* un TABLEAU SYNOPTIQUE : identité (article de l'AOF, rattachement, chef), agents, attributions avec responsable,
  modules, échéance, état et taux, comptes rattachés et périmètre d'accès (modules ouverts) ;
* un TABLEAU SYNOPTIQUE DE TOUTES LES DIVISIONS (une ligne par division) avec exports PDF et Excel ;
* « Mon tableau de bord » : renvoie le compte connecté vers le tableau de bord de sa division.

    jur_division_mon      /juridiction/mon-tableau-de-bord                   GET
    jur_division_tb       /juridiction/divisions/<code>/tableau-de-bord      GET
    jur_division_synop    /juridiction/divisions/<code>/synoptique           GET
    jur_division_synop_pdf  /juridiction/divisions/<code>/synoptique.pdf     GET
    jur_divisions_synop   /juridiction/divisions/synoptique                  GET   toutes les divisions
    jur_divisions_synop_pdf / _xlsx                                           GET

Accès : tout utilisateur connecté de la juridiction, sauf les comptes à périmètre (chef de service, agent) qui ne
voient que LEUR division ; le tableau de toutes les divisions est réservé aux comptes sans périmètre.
Les noms d'endpoints commencent par « jur_division » : ils sont communs à toutes les divisions (a_integration).
"""
import re
from datetime import date, timedelta

from flask import abort, g, redirect, render_template, request, url_for

import a_divisions as D
import a_structure as S
import config

ROLES_LIB = {"responsable": "Responsable (CCS / Directeur départemental)", "cp": "Conseiller pédagogique",
             "chef_service": "Chef de division / de service", "agent": "Agent", "admin": "Administrateur",
             "directeur": "Directeur", "enseignant": "Enseignant", "observateur": "Observateur"}
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# groupes d'indicateurs de terrain : code de division → familles d'indicateurs
FAMILLES = {
    "ecoles": {"ccs", "direction", "semp", "organisation", "statistiques", "infrastructures"},
    "peda": {"cp", "animation", "ccs", "direction", "semp", "organisation"},
    "cep": {"sec", "organisation", "statistiques", "ccs", "direction"},
    "rh": {"personnel", "srh", "administration", "spaf", "ccs", "direction"},
    "transmission": {"secretariat", "organisation", "statistiques", "sec", "semp", "direction", "ccs"},
}


def _pct(v):
    return D.pct(v)


def _date_iso(texte):
    t = (texte or "").strip()
    return t if _ISO.match(t) else ""


def enregistrer(app, H):
    q = H.q

    def juridiction_ou_404():
        if not config.juridiction():
            abort(404)

    def annee_demandee(args):
        a = (args.get("annee") or "").strip()
        return a if re.match(r"^\d{4}-\d{4}$", a) else config.ANNEE_ACTIVE

    def sans_perimetre():
        """True si le compte n'est limité à aucune division (responsable, admin, CP, directeur…)."""
        return H.perimetre_utilisateur() is None

    def division_autorisee(code):
        per = H.perimetre_utilisateur()
        if per is None:
            return True
        return g.get("division_code") == code

    def n(sql, args=()):
        try:
            r = q(sql, args, un=True)
            return int(r[0]) if r and r[0] is not None else 0
        except Exception:  # noqa: BLE001 — table absente dans cette application : indicateur masqué
            return None

    # ---------------------------------------------------------------- indicateurs de terrain
    def indicateurs(code, annee):
        """[{libelle, valeur, aide, ep}] propres au métier de la division (valeur None = non disponible)."""
        out = []

        def ajouter(libelle, valeur, aide="", ep=""):
            if valeur is not None:
                out.append({"libelle": libelle, "valeur": valeur, "aide": aide, "ep": ep if ep in app.view_functions else ""})

        if code in FAMILLES["ecoles"]:
            ajouter("Écoles actives", n("SELECT COUNT(*) FROM jur_ecoles WHERE actif=1"), "écoles de la juridiction", "jur_ecoles")
            ajouter("Écoles ayant transmis", n("SELECT COUNT(*) FROM jur_ecoles WHERE actif=1 AND derniere_transmission IS NOT NULL "
                                                "AND derniere_transmission<>''"), "au moins un envoi reçu", "jur_transmission_suivi")
        if code in FAMILLES["peda"]:
            ajouter("Visites enregistrées", n("SELECT COUNT(*) FROM jur_visites WHERE annee=?", (annee,)), f"année {annee}", "jur_visites")
            ajouter("Unités pédagogiques actives", n("SELECT COUNT(*) FROM jur_up WHERE actif=1"), "UP de la juridiction", "jur_up")
            prevues = n("SELECT COUNT(*) FROM jur_up_activites WHERE annee=? AND prevue=1", (annee,))
            faites = n("SELECT COUNT(*) FROM jur_up_activites WHERE annee=? AND executee=1", (annee,))
            if prevues is not None and faites is not None:
                ajouter("Activités d'UP exécutées", f"{faites} / {prevues}", "exécutées / prévues", "jur_up")
        if code in FAMILLES["cep"]:
            ajouter("Écoles avec résultats CEP", n("SELECT COUNT(*) FROM jur_cep_saisies WHERE annee=?", (annee,)), f"année {annee}", "jur_cep")
            cand = n("SELECT COALESCE(SUM(COALESCE(candidats_g,0)+COALESCE(candidats_f,0)),0) FROM jur_cep_saisies WHERE annee=?", (annee,))
            ajouter("Candidats au CEP saisis", cand, "corrections et imports", "jur_cep")
        if code in FAMILLES["rh"]:
            ajouter("Agents de la structure", n("SELECT COUNT(*) FROM jur_agents WHERE actif=1 AND cs_id IS NULL"), "fiches agents actives", "jur_agents")
        if code in FAMILLES["transmission"]:
            ajouter("Paquets reçus des écoles", n("SELECT COUNT(*) FROM jur_paquets WHERE annee=?", (annee,)), f"année {annee}", "jur_transmissions")
            ajouter("Envois vers l'autorité supérieure", n("SELECT COUNT(*) FROM jur_trans_envois WHERE annee=? AND statut='ok'", (annee,)),
                    "envois réussis", "jur_transmission_suivi")
        return out

    # ---------------------------------------------------------------- calculs sur les lignes d'action
    def analyse_lignes(lignes):
        """Retards, échéances proches et répartition par état d'une liste de lignes d'action."""
        auj = date.today().isoformat()
        proche = (date.today() + timedelta(days=30)).isoformat()
        retards, proches = [], []
        for l in lignes:
            e = _date_iso(l.get("echeance"))
            if not e or (l.get("etat") or "") == "réalisée":
                continue
            if e < auj:
                retards.append(dict(l, echeance_iso=e))
            elif e <= proche:
                proches.append(dict(l, echeance_iso=e))
        retards.sort(key=lambda x: x["echeance_iso"])
        proches.sort(key=lambda x: x["echeance_iso"])
        par_etat = {et: 0 for et in D.ETATS}
        for l in lignes:
            et = l.get("etat") or "prévue"
            par_etat[et if et in par_etat else "prévue"] += 1
        return retards, proches, par_etat

    def comptes_lisibles(d):
        out = []
        for u in d.get("comptes", []):
            out.append({"nom": u["nom"], "identifiant": u["identifiant"], "role": u["role"],
                        "role_lib": H_roles().get(u["role"], u["role"]),
                        "limite": bool(u.get("limite")), "origine": u.get("origine", "")})
        return out

    def H_roles():
        return ROLES_LIB

    def donnees_division(code, annee):
        d = H.jur_division(code, annee)
        d["retards"], d["proches"], d["par_etat"] = analyse_lignes(d["lignes"])
        d["indicateurs"] = indicateurs(code, annee)
        d["comptes_lib"] = comptes_lisibles(d)
        d["nb_modules_ok"] = sum(1 for m in d["modules"] if m["acces"])
        return d

    def verifier(code):
        juridiction_ou_404()
        if not division_autorisee(code):
            abort(403)

    # ---------------------------------------------------------------- pages
    @app.route("/juridiction/mon-tableau-de-bord")
    @H.connexion_requise()
    def jur_division_mon():
        juridiction_ou_404()
        u = g.get("user")
        code = H.code_division_utilisateur(u) if u else None
        annee = annee_demandee(request.args)
        if code and S.service_par_code(code):
            return redirect(url_for("jur_division_tb", code=code, annee=annee))
        return redirect(url_for("jur_divisions_synop", annee=annee))

    @app.route("/juridiction/divisions/<code>/tableau-de-bord")
    @H.connexion_requise()
    def jur_division_tb(code):
        verifier(code)
        annee = annee_demandee(request.args)
        d = donnees_division(code, annee)
        return render_template("jur_division_tb.html", d=d, annee=annee, annees=H.jur_annees_div(), s=S.structure(),
                               pct=_pct, ETATS=D.ETATS, global_ok=sans_perimetre())

    @app.route("/juridiction/divisions/<code>/synoptique")
    @H.connexion_requise()
    def jur_division_synop(code):
        verifier(code)
        annee = annee_demandee(request.args)
        d = donnees_division(code, annee)
        return render_template("jur_division_synop.html", d=d, annee=annee, annees=H.jur_annees_div(), s=S.structure(),
                               pct=_pct, global_ok=sans_perimetre())

    def ligne_synoptique(d):
        sy = d["synthese"]
        return {"code": d["code"], "sigle": d["sigle"] or d["code"].upper(), "nom": d["nom"], "article": d["article"] or "",
                "parent": d["parent_nom"] or "", "chef": d["chef_nom"] or "non désigné",
                "agents": len(d["agents"]), "comptes": len(d["comptes_lib"]),
                "modules": len(d["modules"]), "lignes": sy["total"], "realisees": sy["realisees"], "en_cours": sy["en_cours"],
                "taux": sy["taux"], "retards": len(d["retards"])}

    def toutes_divisions(annee):
        return [donnees_division(x["code"], annee) for x in S.services()]

    @app.route("/juridiction/divisions/synoptique")
    @H.connexion_requise()
    def jur_divisions_synop():
        juridiction_ou_404()
        if not sans_perimetre():
            return redirect(url_for("jur_division_mon"))
        annee = annee_demandee(request.args)
        divs = toutes_divisions(annee)
        lignes = [ligne_synoptique(d) for d in divs]
        toutes = D.synthese_lignes([l for d in divs for l in d["lignes"]])
        return render_template("jur_divisions_synop.html", lignes=lignes, toutes=toutes, annee=annee, annees=H.jur_annees_div(),
                               s=S.structure(), pct=_pct)

    # ---------------------------------------------------------------- PDF et Excel
    def infos_haut():
        s = S.structure() or {}
        out = [("DDEMP", s.get("departement") or "")]
        if config.EDITION == "cs":
            out.append(("CS", s.get("cs") or ""))
        return out

    def signatures_pdf(code=None):
        titre, nom, sig = S.jur_signataire(code)
        return (titre or "").upper(), nom or "", H.pdfs.image_data_url(sig) if sig else None

    @app.route("/juridiction/divisions/<code>/synoptique.pdf")
    @H.connexion_requise()
    def jur_division_synop_pdf(code):
        verifier(code)
        annee = annee_demandee(request.args)
        d = donnees_division(code, annee)
        P = H.pdfs
        ent = ["N°", "Attribution / ligne d'action", "Responsable", "Modules", "Échéance", "État", "Taux"]
        rows = [[l["ordre"] or i + 1, l["libelle"], l["responsable"] or "", "\n".join(l["modules_libelles"]), l["echeance"] or "",
                 l["etat"] or "prévue", _pct(l["taux_effectif"])] for i, l in enumerate(d["lignes"])]
        if not rows:
            rows = [["", "Aucune ligne d'action pour cette année.", "", "", "", "", ""]]
        sy = d["synthese"]
        agents = [["Agent", "Poste", "Téléphone"]] + [
            [S.nom_agent(a), a["poste"] or "", a["telephone"] or ""] for a in d["agents"]] if d["agents"] else \
            [["Agent", "Poste", "Téléphone"], ["Aucun agent affecté", "", ""]]
        comptes = [["Compte", "Rôle", "Périmètre"]] + [
            [c["nom"], c["role_lib"], "limité à la division" if c["limite"] else "toute l'application"] for c in d["comptes_lib"]] \
            if d["comptes_lib"] else [["Compte", "Rôle", "Périmètre"], ["Aucun compte rattaché", "", ""]]
        modules = [["Modules du périmètre d'accès", "Accès"]] + [[m["libelle"], "écriture" if m["acces"] else "lecture"] for m in d["modules"]]
        apres = [P.paragraphe("Agents de la division", 9.5, True, espace=6), P.mini_tableau(agents, taille=7.5),
                 P.paragraphe("Comptes rattachés et périmètre d'accès", 9.5, True, espace=6), P.mini_tableau(comptes, taille=7.5),
                 P.paragraphe("Modules ouverts à la division", 9.5, True, espace=6), P.mini_tableau(modules, taille=7)]
        infos = [("Division", f"{d['sigle'] or ''} – {d['nom']}"), ("Article de l'AOF", d["article"] or "—"),
                 ("Rattachement", d["parent_nom"] or "—"), ("Chef", d["chef_nom"] or "non désigné"),
                 ("Lignes d'action", sy["total"]), ("Réalisées", sy["realisees"]), ("Taux de réalisation", _pct(sy["taux"])),
                 ("Lignes en retard", len(d["retards"]))]
        titre_s, nom, img = signatures_pdf(None)
        sigs = [(titre_s, nom, img, True)]
        if code not in S.RACINE.values():
            t2, n2, i2 = signatures_pdf(code)
            sigs.insert(0, (t2, n2, i2, False))
        s = S.structure() or {}
        pdf = P.document_tableau("TABLEAU SYNOPTIQUE DE LA DIVISION", ent, rows, paysage=True, taille=7.5,
                                 largeurs=[5, 42, 18, 24, 11, 10, 8], infos=infos, infos_haut=infos_haut(), apres=apres,
                                 sous_titre=f"{d['sigle'] or ''} – {d['nom']} — {s.get('nom') or ''} — année scolaire {annee}",
                                 signatures=sigs)
        H.journal("jur_division_synop_pdf", f"{code} {annee}")
        return H.pdf_reponse(pdf, f"synoptique_{code}_{annee}.pdf")

    ENT_SYNOP = ["Division", "Article AOF", "Rattachement", "Chef", "Agents", "Comptes", "Modules", "Lignes d'action",
                 "Réalisées", "En cours", "Taux (%)", "En retard"]

    def lignes_xlsx(lignes):
        return [[f"{l['sigle']} – {l['nom']}", l["article"], l["parent"], l["chef"], l["agents"], l["comptes"], l["modules"],
                 l["lignes"], l["realisees"], l["en_cours"], l["taux"] if l["taux"] is not None else "", l["retards"]] for l in lignes]

    @app.route("/juridiction/divisions/synoptique.pdf")
    @H.connexion_requise()
    def jur_divisions_synop_pdf():
        juridiction_ou_404()
        if not sans_perimetre():
            abort(403)
        annee = annee_demandee(request.args)
        divs = toutes_divisions(annee)
        lignes = [ligne_synoptique(d) for d in divs]
        toutes = D.synthese_lignes([l for d in divs for l in d["lignes"]])
        rows = [[f"{l['sigle']} – {l['nom']}", l["article"] or "—", l["chef"], l["agents"], l["comptes"], l["modules"], l["lignes"],
                 l["realisees"], _pct(l["taux"]), l["retards"]] for l in lignes]
        total = ["TOTAL STRUCTURE", "", "", sum(l["agents"] for l in lignes), sum(l["comptes"] for l in lignes), "",
                 toutes["total"], toutes["realisees"], _pct(toutes["taux"]), sum(l["retards"] for l in lignes)]
        P = H.pdfs
        titre_s, nom, img = signatures_pdf(None)
        s = S.structure() or {}
        pdf = P.document_tableau("TABLEAU SYNOPTIQUE DES DIVISIONS",
                                 ["Division", "Art. AOF", "Chef", "Agents", "Comptes", "Modules", "Lignes", "Réalisées", "Taux", "Retards"],
                                 rows, total=total, paysage=True, taille=7.5, largeurs=[44, 8, 26, 8, 9, 9, 8, 10, 8, 8],
                                 infos=[("Divisions", len(lignes)), ("Lignes d'action", toutes["total"]), ("Réalisées", toutes["realisees"]),
                                        ("Taux de réalisation", _pct(toutes["taux"]))],
                                 infos_haut=infos_haut(), sous_titre=f"{s.get('nom') or ''} — année scolaire {annee}",
                                 signatures=[(titre_s, nom, img, True)])
        H.journal("jur_divisions_synop_pdf", annee)
        return H.pdf_reponse(pdf, f"synoptique_divisions_{annee}.pdf")

    @app.route("/juridiction/divisions/synoptique.xlsx")
    @H.connexion_requise()
    def jur_divisions_synop_xlsx():
        juridiction_ou_404()
        if not sans_perimetre():
            abort(403)
        annee = annee_demandee(request.args)
        divs = toutes_divisions(annee)
        lignes = [ligne_synoptique(d) for d in divs]
        s = S.structure() or {}
        H.journal("jur_divisions_synop_xlsx", annee)
        return H.xlsx.reponse_classeur(f"synoptique_divisions_{annee}.xlsx",
                                       [("Synoptique", ENT_SYNOP, lignes_xlsx(lignes),
                                         {"titre_haut": ["Tableau synoptique des divisions", f"{s.get('nom') or ''} — année scolaire {annee}"]})])

    H.jur_division_tb_donnees = donnees_division
