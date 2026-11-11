# -*- coding: utf-8 -*-
"""v2.2 — Barre « Télécharger PDF · Télécharger Word · Imprimer » des pages de pédagogie et des pages qui n'avaient
qu'un bouton « Imprimer ».

Sur Android, le navigateur intégré ne sait pas enregistrer une page imprimée : on télécharge donc un vrai fichier.
* PDF : le PDF propre de la page quand il existe (fiche, résumé, épreuve, guide…), sinon le contenu de la page
  converti (export_doc.pdf, Times New Roman 14 pt) ;
* Word : vrai .docx (export_doc.docx), pour modifier le document sur l'ordinateur ou le téléphone ;
* Imprimer : impression du système (sur Android, gestionnaire d'impression du téléphone, voir MainActivity).

Routes : /exporter.pdf?page=/preparation/... et /exporter.docx?page=/preparation/... — la page est produite à nouveau
avec les droits de la personne connectée (mêmes cookies), puis son contenu principal est converti.
"""
import re
import urllib.parse

from flask import Response, abort, g, request, url_for
from werkzeug.test import EnvironBuilder

import config
import export_doc as E

# pages qui reçoivent la barre (préfixes d'adresse) — v2.2 : toute la préparation et les épreuves, le guide
PREFIXES = ("/preparation", "/epreuves", "/aide/guide",
            # v2.2 : documents à garder ou à modifier (rapports, comptes rendus, notes de service, bilans, tableaux)
            "/rapports", "/communication", "/inspection", "/uascep", "/examens", "/examen-blanc", "/cep-blanc", "/pilotage",
            "/sport", "/sante-scolaire", "/patrimoine-materiel", "/visites", "/bilan-annuel", "/maitre-semaine", "/themes-up",
            "/calendrier-scolaire", "/tableau-honneur", "/synthese", "/statistiques-evaluation", "/juridiction")
# pages qui reçoivent aussi la barre (avant : seulement « Imprimer »)
ENDPOINTS_EN_PLUS = {"impayes", "jur_tableau", "jur_fiches_tableaux", "jur_ecoles_struct", "jur_rubriques", "jur_cep_fiches",
                     "jur_infra", "jur_effectifs", "acces_parent"}
# pages de saisie (formulaires) : pas de barre
SANS_BARRE = {"prep_preparer", "prep_resume_modifier", "prep_epreuve_modifier", "epreuves_comite_import", "epreuves_membre",
              }


def _avec_args(endpoint, **en_plus):
    """Lien vers le PDF / Word propre de la page, avec les mêmes paramètres (classe, cours, filtres…)."""
    args = dict(request.view_args or {})
    for k, v in request.args.items(multi=False):
        args.setdefault(k, v)
    args.update(en_plus)
    try:
        return url_for(endpoint, **args)
    except Exception:  # noqa: BLE001
        return None


# endpoint de la page -> (endpoint du PDF propre, endpoint du Word propre)
DEDIES = {
    "prep_fiche": ("prep_fiche_pdf", "prep_fiche_doc"),
    "prep_ma_fiche": ("prep_ma_fiche_pdf", "prep_ma_fiche_doc"),
    "prep_epreuve": ("prep_epreuve_pdf", "prep_epreuve_doc"),
    "prep_guide": ("prep_guide_pdf", None),
    "prep_resume": ("prep_resume_pdf", "prep_resume_docx"),
    "prep_resumes": ("prep_resumes_pdf", "prep_resumes_docx"),
    "prep_revision": ("prep_revision_pdf", None),
    "prep_baremes_eps": ("prep_baremes_eps_pdf", None),
    "prep_planif": ("prep_planif_pdf", None),
    "mat_edt": ("mat_edt_pdf", None),
    "mat_grilles": ("mat_grilles_pdf", None),
    "guide_utilisation": ("guide_pdf", None),
    "epreuve_form": ("epreuve_pdf", None),
    "grille_form": ("grille_pdf", None),
    "epreuves_comite": ("epreuves_comite_pdf", None),
}


def avec_barre():
    ep = request.endpoint or ""
    if request.method != "GET" or not g.get("user") or ep in SANS_BARRE or ep.endswith(("_pdf", "_doc", "_xlsx")):
        return False
    regle = request.url_rule
    if regle is not None and "POST" in (regle.methods or ()) and ep not in DEDIES:   # pages de saisie : pas de barre
        return False
    return ep in ENDPOINTS_EN_PLUS or request.path.startswith(PREFIXES)


def liens_barre():
    """{"pdf": url, "word": url} de la page courante."""
    page = request.full_path.rstrip("?")
    ep = request.endpoint or ""
    pdf_dedie, word_dedie = DEDIES.get(ep, (None, None))
    if ep in ("prep_planif",) and not request.args.get("classe"):   # PDF propre : il faut une classe choisie
        pdf_dedie = None
    pdf = _avec_args(pdf_dedie, telecharger=1) if pdf_dedie else None
    word = _avec_args(word_dedie) if word_dedie else None
    return {"pdf": pdf or url_for("exporter_page", fmt="pdf", page=page),
            "word": word or url_for("exporter_page", fmt="docx", page=page)}


def nom_fichier(titre, ext):
    import unicodedata
    t = unicodedata.normalize("NFD", titre or "document")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")[:70]
    return f"{t or 'document'}.{ext}"


def reponse_fichier(contenu, nom, mimetype):
    """Fichier à télécharger : nom lisible (accents en UTF-8, RFC 5987) et version ASCII de secours."""
    ascii_nom = nom_fichier(nom.rsplit(".", 1)[0], nom.rsplit(".", 1)[-1]) if "." in nom else nom_fichier(nom, "bin")
    cd = f"attachment; filename=\"{ascii_nom}\"; filename*=UTF-8''{urllib.parse.quote(nom)}"
    return Response(contenu, mimetype=mimetype, headers={"Content-Disposition": cd, "Cache-Control": "no-store"})


def reponse_docx(contenu_html_ou_blocs, nom, titre="Document"):
    pied = f"Conception : {getattr(config, 'CONCEPTEUR', 'Maître Aimé FACHOLA')} — +229 01 96 51 03 33"
    if isinstance(contenu_html_ou_blocs, (bytes, bytearray)):
        d = bytes(contenu_html_ou_blocs)
    elif isinstance(contenu_html_ou_blocs, str):
        d = E.html_vers_docx(contenu_html_ou_blocs, titre, pied)
    else:
        d = E.docx(contenu_html_ou_blocs, titre, pied)
    if not nom.lower().endswith(".docx"):
        nom = re.sub(r"\.(doc|html?)$", "", nom, flags=re.I) + ".docx"
    return reponse_fichier(d, nom, E.KIT_DOCX)


def enregistrer(app, H):
    H.reponse_docx = reponse_docx
    H.reponse_fichier = reponse_fichier

    @app.context_processor
    def _ctx_export():
        try:
            if avec_barre():
                return {"EXPORT_BARRE": liens_barre()}
        except Exception:  # noqa: BLE001 — la barre ne doit jamais empêcher une page de s'afficher
            app.logger.exception("Barre d'export")
        return {"EXPORT_BARRE": None}

    def produire_page(chemin):
        """Rejoue la page demandée pour la personne connectée et renvoie son HTML."""
        u = urllib.parse.urlsplit(chemin)
        if u.scheme or u.netloc or not u.path.startswith("/") or u.path.startswith("//") or u.path.startswith("/exporter"):
            abort(400)
        en_tetes = {"Accept-Encoding": "identity", "Accept-Language": request.headers.get("Accept-Language", "fr")}
        if request.headers.get("Cookie"):
            en_tetes["Cookie"] = request.headers["Cookie"]
        env = EnvironBuilder(path=u.path, query_string=u.query, method="GET", headers=en_tetes,
                             base_url=request.host_url).get_environ()
        with app.app_context(), app.request_context(env):   # contexte neuf : g de la page rejouée séparé
            r = app.full_dispatch_request()
        if r.status_code != 200 or not (r.mimetype or "").startswith("text/html"):
            abort(404 if r.status_code in (301, 302, 303, 404) else r.status_code if r.status_code >= 400 else 404)
        return r.get_data(as_text=True)

    @app.after_request
    def _redirection_pour_fetch(r):
        """v2.2 — formulaire envoyé par JavaScript (applications Android) : la redirection est renvoyée en JSON, pour que la
        page suivante (et son message) s'ouvre normalement au lieu d'être lue par le script."""
        try:
            if request.headers.get("X-Scolaris-Fetch") == "1" and r.status_code in (301, 302, 303, 307, 308) and r.location:
                from flask import jsonify
                j = jsonify(redirection=r.location)
                for k, v in r.headers.items():
                    if k.lower() == "set-cookie":
                        j.headers.add(k, v)
                return j
        except Exception:  # noqa: BLE001
            pass
        return r

    @app.route("/exporter.<fmt>")
    @H.connexion_requise()
    def exporter_page(fmt):
        if fmt not in ("pdf", "docx"):
            abort(404)
        page = request.args.get("page") or "/"
        html = produire_page(page)
        titre = E.titre_page(html)
        b = E.blocs(E.contenu_principal(html))
        ecole = (config.ECOLE.get("nom") or "").strip() if isinstance(getattr(config, "ECOLE", None), dict) else ""
        pied = f"{ecole + ' · ' if ecole else ''}{getattr(config, 'NOMS_APPLI', {}).get(config.EDITION, 'SCOLARIS') if hasattr(config, 'NOMS_APPLI') else 'SCOLARIS'} {config.VERSION} · Conception : {config.CONCEPTEUR} — +229 01 96 51 03 33"
        H.journal("export_" + fmt, page[:200])
        if fmt == "pdf":
            return reponse_fichier(E.pdf(b, titre, pied), nom_fichier(titre, "pdf"), "application/pdf")
        return reponse_fichier(E.docx(b, titre, pied), nom_fichier(titre, "docx"), E.KIT_DOCX)
