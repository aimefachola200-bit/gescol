# -*- coding: utf-8 -*-
"""v2.4.3 — Graphiques du tableau de bord d'accueil : effectifs par classe, encaissements mensuels (édition privée)
et présences de la semaine. Dessinés en SVG, sans bibliothèque ; couleurs par variables CSS (mode clair et sombre).

Fournit au gabarit la fonction globale ``graphiques_accueil()`` ; accueil.html l'utilise s'il existe.
"""
from datetime import date, timedelta

import config

MOIS = ["Sept", "Oct", "Nov", "Déc", "Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil"]


def mois_annee(annee):
    """[(clé 'AAAA-MM', libellé)] de septembre à juillet pour une année scolaire « 2026-2027 »."""
    try:
        a = int(str(annee)[:4])
    except ValueError:
        a = date.today().year
    cles = [(a, 9), (a, 10), (a, 11), (a, 12)] + [(a + 1, m) for m in range(1, 8)]
    return [(f"{y}-{m:02d}", lib) for (y, m), lib in zip(cles, MOIS)]


def barres(valeurs, haut=120):
    """[(libellé, valeur)] → [(libellé, valeur, hauteur_px, x)] ; hauteur proportionnelle au plus grand."""
    mx = max([v for _l, v in valeurs] + [0])
    n = max(len(valeurs), 1)
    pas = 100.0 / n
    return [(l, v, round(haut * v / mx, 1) if mx else 0, round(i * pas + pas / 2, 2)) for i, (l, v) in enumerate(valeurs)]


def semaine_presences(q, e_):
    """Taux de présence (%) des 5 derniers jours ouvrables ayant un appel : [(jj/mm, taux)]."""
    out, j = [], date.today()
    for _ in range(14):
        if j.weekday() < 5:
            r = q("SELECT COUNT(*) n, SUM(CASE WHEN p.statut='absent' THEN 1 ELSE 0 END) a FROM presences p JOIN eleves e ON e.id=p.eleve_id "
                  "JOIN classes c ON c.id=e.classe_id AND c.ecole_id=? WHERE p.date=?", (e_, j.isoformat()), un=True)
            if r and r["n"]:
                out.append((j.strftime("%d/%m"), round(100.0 * (r["n"] - (r["a"] or 0)) / r["n"], 1)))
        j -= timedelta(days=1)
        if len(out) == 5:
            break
    return list(reversed(out))


def enregistrer(app, H):
    q = H.q

    def graphiques_accueil():
        e_ = H.eco()
        a = config.ANNEE_ACTIVE
        classes = q("SELECT c.nom, COUNT(e.id) n FROM classes c LEFT JOIN eleves e ON e.classe_id=c.id AND e.statut='inscrit' "
                    "WHERE c.ecole_id=? GROUP BY c.id ORDER BY c.nom", (e_,))
        eff = [(c["nom"], c["n"]) for c in classes if c["n"]]
        recettes = None
        if not config.publique() and H.peut("paiements"):
            par = {r["m"]: r["s"] for r in q(
                "SELECT substr(p.date_paiement,1,7) m, SUM(p.montant) s FROM paiements p JOIN eleves e ON e.id=p.eleve_id "
                "JOIN classes c ON c.id=e.classe_id AND c.ecole_id=? WHERE p.annule=0 AND p.annee=? GROUP BY m", (e_, a))}
            recettes = barres([(lib, par.get(cle, 0)) for cle, lib in mois_annee(a)])
        return {"effectifs": eff, "effectif_max": max([n for _c, n in eff] + [1]), "recettes": recettes,
                "recettes_total": sum(v for _l, v, _h, _x in recettes) if recettes else 0, "presences": semaine_presences(q, e_)}

    app.jinja_env.globals["graphiques_accueil"] = graphiques_accueil
