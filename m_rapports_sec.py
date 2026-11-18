# -*- coding: utf-8 -*-
"""v2.8 : situation statistique de l'établissement (collège, lycée, enseignement technique et agricole).

Une seule page, calculée à partir des données de l'application, prête à imprimer, à exporter en PDF ou en Word et à remettre à
l'inspection ou à la direction départementale : effectifs par classe (garçons, filles, redoublants), personnel par fonction et par sexe,
résultats par classe pour la période choisie, ferme-école (campagne en cours) si le registre est tenu.
Ce document est un état statistique de l'établissement : il ne reprend pas un formulaire officiel particulier."""
import config
from flask import abort, g, render_template, request

NIVEAUX_1ER_CYCLE = ("6e", "6ème", "5e", "5ème", "4e", "4ème", "3e", "3ème")


def enregistrer(app, H):
    from db import q

    def garde():
        if not config.secondaire():
            abort(404)

    @app.route("/rapport-etablissement")
    @H.connexion_requise("recensement")
    def rapport_etablissement():
        garde()
        import app as A
        classes = [c for c in q("SELECT * FROM classes ORDER BY nom") if c["id"] in {x["id"] for x in H.classes_autorisees()}]
        lignes, tot = [], dict(g=0, f=0, t=0, r=0)
        for c in classes:
            r = q("SELECT SUM(sexe='M') g, SUM(sexe='F') f, COUNT(*) t, SUM(COALESCE(redoublant,0)) r FROM eleves WHERE classe_id=? AND statut='inscrit'", (c["id"],), un=True)
            l = dict(nom=c["nom"], niveau=c["niveau"], g=r["g"] or 0, f=r["f"] or 0, t=r["t"] or 0, r=r["r"] or 0)
            lignes.append(l)
            for k in tot:
                tot[k] += l[k]
        per = q("SELECT fonction, SUM(sexe='M') h, SUM(sexe='F') f, COUNT(*) t FROM personnel WHERE actif=1 GROUP BY fonction ORDER BY fonction")
        periode = request.args.get("periode", 1, type=int)
        resultats = []
        for c in classes:
            try:
                cl = H.classe_ou_404(c["id"])
                st = A.resultats_classe(cl, periode)[4]
            except Exception:  # noqa: BLE001 — pas de notes : la ligne reste vide
                st = {}
            resultats.append(dict(nom=c["nom"], effectif=st.get("effectif", 0), classes=st.get("classes", 0), moyenne=st.get("moyenne_classe"),
                                  forte=st.get("plus_forte"), faible=st.get("plus_faible"), admis=st.get("admis", 0), taux=st.get("taux_reussite")))
        ferme = []
        try:
            for r in q("SELECT espece, SUM(effectif) e, SUM(morts) m FROM reg_sec_cheptel GROUP BY espece"):
                ferme.append(dict(espece=r["espece"], effectif=r["e"] or 0, morts=r["m"] or 0))
            sup = q("SELECT COUNT(*) n, SUM(superficie) s FROM reg_sec_parcelles", un=True)
            recettes = q("SELECT SUM(montant) m FROM reg_sec_production", un=True)
            ferme_t = dict(parcelles=sup["n"] or 0, ares=sup["s"] or 0, recettes=recettes["m"] or 0)
        except Exception:  # noqa: BLE001 — registres de la ferme-école absents ou vides
            ferme_t = None
        return render_template("rapport_etablissement.html", lignes=lignes, tot=tot, personnel=per, resultats=resultats, periode=periode,
                               periodes=config.PERIODES, ferme=ferme, ferme_t=ferme_t)
