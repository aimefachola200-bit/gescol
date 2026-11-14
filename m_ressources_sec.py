# -*- coding: utf-8 -*-
"""v2.5.0 : « Ressources du secondaire » : banque d'épreuves nettoyée et sans doublon, thèmes d'exposés (4ᵉ → Tle), fiches de révision."""
import json
import os

import config
import epreuves_apc as AP
import fiches_sec as FS
import ressources_secondaire as R
from flask import abort, render_template, request

_BANQUE = None


def banque():
    global _BANQUE
    if _BANQUE is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "banque_secondaire.json")
        with open(p, encoding="utf-8") as f:
            _BANQUE = json.load(f)["epreuves"]
    return _BANQUE


def enregistrer(app, H):
    def garde():
        if not config.secondaire():
            abort(404)

    @app.route("/ressources-secondaire")
    @H.connexion_requise("epreuves")
    def ress_sec():
        garde()
        vue = request.args.get("vue", "epreuves")
        niv, mat, qs = request.args.get("niveau", ""), request.args.get("matiere", ""), (request.args.get("q") or "").strip().lower()
        ep = banque()
        if vue == "exposes":
            lignes = [e for e in R.EXPOSES if (not mat or e[0] == mat) and (not niv or niv in _etendre(e[1])) and (not qs or qs in " ".join(e[:4]).lower())]
            mats = sorted({e[0] for e in R.EXPOSES})
        elif vue == "revisions":
            lignes = [(i, e) for i, e in enumerate(R.REVISIONS) if (not mat or e[0] == mat) and (not niv or e[1] == niv) and (not qs or qs in " ".join(e[:3]).lower())]
            mats = sorted({e[0] for e in R.REVISIONS})
        elif vue == "apc":
            lignes = [e for e in AP.EPREUVES if (not mat or e["matiere"] == mat) and (not niv or e["niveau"] == niv) and (not qs or qs in (e["matiere"] + e["situation"]).lower())]
            mats = sorted({e["matiere"] for e in AP.EPREUVES})
        elif vue == "fiches":
            lignes = [(i, f) for i, f in enumerate(FS.FICHES) if (not mat or f["matiere"] == mat) and (not niv or f["niveau"] == niv) and (not qs or qs in (f["titre"] + f["matiere"]).lower())]
            mats = sorted({f["matiere"] for f in FS.FICHES})
        else:
            vue = "epreuves"
            lignes = [e for e in ep if (not mat or e["matiere"] == mat) and (not niv or e["niveau"] == niv) and (not qs or qs in (e["matiere"] + e["texte"]).lower())]
            mats = sorted({e["matiere"] for e in ep})
        return render_template("ress_sec.html", vue=vue, lignes=lignes, mats=mats, niveaux=["6e", "5e"] + R.NIVEAUX + ["BEPC", "BAC"], niv=niv, mat=mat, q=qs,
                               nb=dict(epreuves=len(ep), exposes=len(R.EXPOSES), revisions=len(R.REVISIONS), fiches=len(FS.FICHES), apc=len(AP.EPREUVES)))

    @app.route("/ressources-secondaire/epreuve/<int:i>")
    @H.connexion_requise("epreuves")
    def ress_sec_epreuve(i):
        garde()
        e = next((x for x in banque() if x["id"] == i), None)
        if not e:
            abort(404)
        return render_template("ress_sec_epreuve.html", e=e)

    @app.route("/ressources-secondaire/apc/<int:i>")
    @H.connexion_requise("epreuves")
    def ress_sec_apc(i):
        garde()
        if not 0 <= i < len(AP.EPREUVES):
            abort(404)
        return render_template("ress_sec_apc.html", e=AP.EPREUVES[i], grille=AP.GRILLE, corrige=request.args.get("corrige") == "1", ident=H.identification())

    @app.route("/ressources-secondaire/fiche/<int:i>")
    @H.connexion_requise("epreuves")
    def ress_sec_fiche(i):
        garde()
        if not 0 <= i < len(FS.FICHES):
            abort(404)
        return render_template("ress_sec_fiche.html", f=FS.FICHES[i], i=i, ident=H.identification())

    @app.route("/ressources-secondaire/revision/<int:i>")
    @H.connexion_requise("epreuves")
    def ress_sec_revision(i):
        garde()
        if not 0 <= i < len(R.REVISIONS):
            abort(404)
        return render_template("ress_sec_revision.html", r=R.REVISIONS[i])


_ORDRE = ["4e", "3e", "2nde", "1ère", "Tle"]


def _etendre(plage):
    """« 3e–Tle » → {3e, 2nde, 1ère, Tle} ; « 4e » → {4e}."""
    p = plage.replace("—", "–").split("–")
    if len(p) == 1:
        return {p[0]}
    try:
        return set(_ORDRE[_ORDRE.index(p[0]):_ORDRE.index(p[1]) + 1])
    except ValueError:
        return set(p)
