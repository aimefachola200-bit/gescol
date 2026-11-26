# -*- coding: utf-8 -*-
"""v2.9.4 — Zone déshéritée : état des agents ayant droit à la prime de zone (postes « orange » et « rouge »).

Une seule liste pour toute la structure (école, circonscription scolaire, DDEMP, secondaire) :
* chaque agent est rangé sous son école ; le nom de l'école est écrit en tête de sa liste, le nombre d'ayants droit et le
  total de la prime figurent en bas, puis la liste continue avec l'école suivante, sur le même document ;
* le montant du rendement / de la gratification et celui de la prime de zone sont fixés une fois par couleur (onglet
  « Montants par couleur ») et proposés automatiquement ; ils restent modifiables ligne par ligne ;
* saisie à la main ou import Excel (mêmes colonnes) ; export Excel et PDF signé.
"""
from flask import redirect, render_template, request, url_for

import registres as R

COULEURS = ["Orange", "Rouge"]
STATUTS = ["Fonctionnaire (APE)", "Contractuel de l'État", "ACE", "Agent communal", "Enseignant communautaire", "Autre"]
FONCTIONS = ["Directeur", "Autre"]
COLONNES = ["Matricule", "Nom", "Prénoms", "Statut", "Poste actuel", "Poste déshérité", "Rendement / Gratification", "Prime de zone",
            "Code banque", "Banque", "N° de compte", "Fonction", "Observation"]


def enregistrer(app, H):
    H.DROITS["zone_desheritee"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent"}
    R.types_documents({"reg_zone_agents": "État des agents de zone déshéritée", "reg_zone_baremes": "Montants de la zone déshéritée"})
    G = R.Groupe(app, H, "zone", "Zone déshéritée", "zone_desheritee", ico="patrimoine",
                 ecriture_roles={"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent"},
                 sous_titre="Agents des postes orange et rouge : prime de zone, rendement / gratification, banque — par école",
                 listes={"couleurs_zone": COULEURS, "statuts_zone": STATUTS, "fonctions_zone": FONCTIONS})

    def defauts():
        try:
            if not R.juridiction():
                return {"ecole": (R.liste_ecoles() or [""])[0]}
        except Exception:  # noqa: BLE001
            pass
        return {}

    def montants():
        """{couleur: (rendement, prime)} fixés pour la structure."""
        out = {}
        try:
            for b in H.q("SELECT couleur, rendement, prime FROM reg_zone_baremes WHERE portee=?", (R.cle_portee("structure"),)):
                out[b["couleur"]] = (int(b["rendement"] or 0), int(b["prime"] or 0))
        except Exception:  # noqa: BLE001
            pass
        return out

    def remplir(rid):
        x = H.q("SELECT * FROM reg_zone_agents WHERE id=?", (rid,), un=True)
        if not x or x["poste_desherite"] not in COULEURS:
            return
        m = montants().get(x["poste_desherite"])
        if not m:
            return
        if not x["rendement"]:
            H.ex("UPDATE reg_zone_agents SET rendement=? WHERE id=?", (m[0], rid))
        if not x["prime_zone"]:
            H.ex("UPDATE reg_zone_agents SET prime_zone=? WHERE id=?", (m[1], rid))

    def sig(_l):
        return [R.signature_vide("Le responsable"), R.signature_autorite("Visa du Chef de la circonscription / du Directeur")]

    G.registre("agents", "Agents de zone déshéritée", [
        ("ecole", "École", "choix:ecoles"), ("matricule", "N° matricule", "texte"), ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"),
        ("statut", "Statut", "choix:statuts_zone"), ("poste_actuel", "Poste actuel", "texte"),
        ("poste_desherite", "Poste déshérité", "choix:couleurs_zone"), ("rendement", "Rendement / Gratification", "montant"),
        ("prime_zone", "Prime de zone", "montant"), ("code_banque", "Code banque", "texte"), ("banque", "Banque", "texte"),
        ("n_banque", "N° de compte bancaire", "texte"), ("fonction", "Fonction", "choix:fonctions_zone"), ("observation", "Observation", "long")],
        unite="agent", oblig="nom", ordre="ecole, nom", portee="structure", feuille="Zone déshéritée", onglet="Agents",
        filtres=("ecole", "poste_desherite", "fonction"), totaux=("rendement", "prime_zone"), defauts=defauts,
        colonnes=("ecole", "matricule", "nom", "prenoms", "statut", "poste_actuel", "poste_desherite", "rendement", "prime_zone", "fonction"),
        unique=("matricule",), apres_enregistrer=remplir, signataires=sig, doc="État des agents de zone déshéritée",
        aide="Choisissez Orange ou Rouge : le rendement et la prime de zone se remplissent d'après l'onglet « Montants par couleur » "
             "(modifiables). La liste par école, avec le nombre d'ayants droit, est dans l'onglet « Liste par école ».")
    G.registre("baremes", "Montants par couleur", [
        ("couleur", "Couleur du poste", "choix:couleurs_zone"), ("rendement", "Rendement / Gratification (FCFA)", "montant"),
        ("prime", "Prime de zone (FCFA)", "montant")],
        unite="montant", oblig="couleur", ordre="couleur", portee="structure", par_annee=False, onglet="Montants par couleur",
        unique=("couleur",), totaux=(), aide="Fixez une fois le montant de chaque couleur ; il est proposé à chaque nouvel agent.")

    # ------------------------------------------------------------------ liste par école
    def groupes(annee, couleur="", ecole=""):
        r = G.registres["agents"]
        lignes = G.lignes(r, annee, None, {"poste_desherite": couleur, "ecole": ecole})
        par = {}
        for x in lignes:
            par.setdefault((x.get("ecole") or "(École non précisée)").strip(), []).append(x)
        out = []
        for nom in sorted(par, key=lambda s: R._norm(s)):
            ag = sorted(par[nom], key=lambda x: (x.get("fonction") != "Directeur", R._norm(x.get("nom") or ""), R._norm(x.get("prenoms") or "")))
            out.append({"ecole": nom, "agents": ag, "n": sum(1 for a in ag if a.get("poste_desherite") in COULEURS) or len(ag),
                        "rendement": sum(int(a.get("rendement") or 0) for a in ag), "prime": sum(int(a.get("prime_zone") or 0) for a in ag)})
        tot = {"ecoles": len(out), "n": sum(g_["n"] for g_ in out), "rendement": sum(g_["rendement"] for g_ in out), "prime": sum(g_["prime"] for g_ in out)}
        return out, tot

    def ligne(i, x):
        return [i, x.get("matricule") or "", (x.get("nom") or "").upper(), x.get("prenoms") or "", x.get("statut") or "", x.get("poste_actuel") or "",
                x.get("poste_desherite") or "", int(x.get("rendement") or 0), int(x.get("prime_zone") or 0), x.get("code_banque") or "",
                x.get("banque") or "", x.get("n_banque") or "", x.get("fonction") or "", x.get("observation") or ""]

    def filtres_req():
        return (request.args.get("couleur") or "").strip(), (request.args.get("ecole") or "").strip()

    @app.route("/zone-desheritee/liste")
    @H.connexion_requise("zone_desheritee")
    def zone_liste():
        annee = request.args.get("annee") or R.annee_active()
        couleur, ecole = filtres_req()
        grp, tot = groupes(annee, couleur, ecole)
        return render_template("zone_liste.html", G=G, ep_actif="zone_liste", grp=grp, tot=tot, annee=annee, couleur=couleur, ecole=ecole,
                               couleurs=COULEURS, ecoles=sorted({(x.get("ecole") or "").strip() for x in G.lignes(G.registres["agents"], annee) if x.get("ecole")}),
                               montants=montants(), fcfa=R.fcfa, ligne=ligne, colonnes=COLONNES)
    G.page("zone_liste", "Liste par école", apres=False)

    @app.route("/zone-desheritee/liste.xlsx")
    @H.connexion_requise("zone_desheritee")
    def zone_xlsx():
        annee = request.args.get("annee") or R.annee_active()
        couleur, ecole = filtres_req()
        grp, tot = groupes(annee, couleur, ecole)
        ent = ["N° d'ordre"] + COLONNES
        rows = []
        for g_ in grp:
            rows.append(["ÉCOLE : " + g_["ecole"]] + [""] * (len(ent) - 1))
            rows += [ligne(i, x) for i, x in enumerate(g_["agents"], 1)]
            rows.append(["", "", f"Nombre d'ayants droit : {g_['n']}", "", "", "", "", "", g_["rendement"], g_["prime"]] + [""] * (len(ent) - 10))
            rows.append([""] * len(ent))
        rows.append(["", "", f"TOTAL GÉNÉRAL — {tot['n']} ayant(s) droit, {tot['ecoles']} école(s)", "", "", "", "", "", tot["rendement"], tot["prime"]]
                    + [""] * (len(ent) - 10))
        rec = [[g_["ecole"], g_["n"], g_["rendement"], g_["prime"]] for g_ in grp] + [["TOTAL", tot["n"], tot["rendement"], tot["prime"]]]
        return H.xlsx.reponse_classeur(f"zone_desheritee_{annee}.xlsx", [
            ("Liste par école", ent, rows, {}),
            ("Récapitulatif", ["École", "Ayants droit", "Rendement / Gratification", "Prime de zone"], rec, {})])

    @app.route("/zone-desheritee/liste.pdf")
    @H.connexion_requise("zone_desheritee")
    def zone_pdf():
        from reportlab.platypus import PageBreak, Paragraph, Spacer
        annee = request.args.get("annee") or R.annee_active()
        couleur, ecole = filtres_req()
        grp, tot = groupes(annee, couleur, ecole)
        st = R.styles()
        ent = ["N°"] + COLONNES
        larg = [3, 7, 10, 10, 8, 9, 6, 7, 7, 5, 8, 8, 6, 9]
        lu = R.largeur_utile(True)
        corps = []
        for k, g_ in enumerate(grp):
            if k:
                corps.append(PageBreak())
            corps.append(Paragraph(f"<b>ÉCOLE : {R.esc(g_['ecole'].upper())}</b>", st["t"]))
            rows = [[str(c) if c != "" else "" for c in (r[:7] + [R.fcfa(r[7]), R.fcfa(r[8])] + r[9:])] for r in (ligne(i, x) for i, x in enumerate(g_["agents"], 1))]
            corps.append(R.tableau(ent, rows, larg, lu, ["", "", f"Nombre d'ayants droit : {g_['n']}", "", "", "", "", R.fcfa(g_["rendement"]), R.fcfa(g_["prime"]),
                                                          "", "", "", "", ""], taille=7))
        corps.append(PageBreak())
        corps.append(Paragraph("<b>RÉCAPITULATIF PAR ÉCOLE</b>", st["t"]))
        corps.append(Spacer(1, 6))
        rec = [[i, g_["ecole"], g_["n"], R.fcfa(g_["rendement"]), R.fcfa(g_["prime"])] for i, g_ in enumerate(grp, 1)]
        corps.append(R.tableau(["N°", "École", "Ayants droit", "Rendement / Gratification", "Prime de zone"], rec, [4, 30, 10, 14, 14], lu,
                               ["", f"TOTAL GÉNÉRAL ({tot['ecoles']} école(s))", tot["n"], R.fcfa(tot["rendement"]), R.fcfa(tot["prime"])]))
        sigs = sig(None)
        code = R.code_document("reg_zone_agents", f"État des agents de zone déshéritée — {annee} ({tot['n']} ayant(s) droit)",
                               f"zone:{R.cle_portee('structure')}:{annee}:{couleur}:{ecole}:{tot['n']}:{tot['prime']}")
        sous = f"Année scolaire {annee}" + (f" · poste {couleur}" if couleur else "")
        return H.pdf_reponse(R.pdf_document("ÉTAT DES AGENTS DE ZONE DÉSHÉRITÉE", corps, sigs, code, True, sous, bandeau=G.bandeau() if G.bandeau else None),
                             f"zone_desheritee_{annee}.pdf")

    @app.route("/zone-desheritee")
    @H.connexion_requise("zone_desheritee")
    def zone_accueil():
        return redirect(url_for("zone_liste"))
