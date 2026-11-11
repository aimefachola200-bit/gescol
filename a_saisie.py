# -*- coding: utf-8 -*-
"""Saisie manuelle dans les applications « SCOLARIS Circonscription » (CS) et « SCOLARIS DDEMP » (v1.11).

Demande du client : « il manque l'onglet où l'on peut manuellement remplir les différents renseignements si l'on ne
veut pas importer les fichiers Excel, selon les différentes fiches, et le remplissage des noms des personnels,
administratifs et directeurs ».

Jusqu'ici, les fiches des écoles et leur personnel n'arrivaient dans la CS / DDEMP que par les paquets de transmission
(ou un import). Ce module ajoute la SAISIE DIRECTE, école par école :

* jur_saisie (/juridiction/saisie) : écoles × fiches (recensement EP / EM, rentrée EP / EM, fin d'année EP / EM) avec
  leur état, et pour chaque école le nombre d'agents saisis ; boutons « Saisir » ;
* jur_saisie_fiche (/juridiction/saisie/<école>/<fiche>) : la fiche OFFICIELLE au complet, mêmes rubriques, mêmes
  tableaux, mêmes totaux automatiques que le formulaire de l'école (gabarits recensement_fiche.html et
  rapports_formulaire.html, réutilisés tels quels) ; l'enregistrement écrit la fiche dans la section
  « recensement » / « rapports » de l'école (source « saisie ») : elle est alors exploitée comme une fiche
  transmise par tous les modules (fiches, synthèse, rubriques, effectifs par âge, infrastructures, CEP…) ;
* jur_saisie_personnel (/juridiction/saisie/<école>/personnel) : état nominatif du personnel de l'école
  (directeur, adjoints, enseignants, administratifs, personnel de soutien) ; écrit la section « personnel »
  (exploitée par Ressources humaines, gestion de carrière, retraites, aptitude, synoptique…) ; le directeur saisi
  devient le directeur de l'école dans la liste des écoles ;
* jur_saisie_directeurs (/juridiction/saisie/directeurs) : noms, titres et téléphones des directeurs de toutes
  les écoles, en un seul tableau.
Les agents de la structure (administratifs de la CS / DDEMP) se saisissent dans « Agents de la structure »
(jur_agents), lié depuis cette page.
"""
import json
import re

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for

import config
import m_juridiction as J
import m_rapports as MRA
import m_recensement as MRE
from db import q, ex

FICHES = (("recensement-primaire", "recensement", "primaire", ("EP",), "Recensement EP"),
          ("recensement-maternelle", "recensement", "maternelle", ("EM", "EE"), "Recensement EM"),
          ("rentree-ep", "rapports", "rentree-ep", ("EP",), "Rentrée EP"),
          ("fin-ep", "rapports", "fin-ep", ("EP",), "Fin d'année EP"),
          ("rentree-em", "rapports", "rentree-em", ("EM", "EE"), "Rentrée EM"),
          ("fin-em", "rapports", "fin-em", ("EM", "EE"), "Fin d'année EM"))
FICHES_D = {f[0]: f for f in FICHES}
FONCTIONS = ["Directeur / directrice", "Adjoint(e)", "Enseignant(e)", "Éducateur / éducatrice (maternelle)", "Secrétaire",
             "Comptable", "Personnel administratif", "Gardien", "Agent d'entretien", "Cuisinier(e)", "Autre"]
CATEGORIES = ["FE", "ACDPE", "ACDPCTD", "PRIVE", "AUTRE"]
# colonnes de l'état nominatif (mêmes clés que la section « personnel » des paquets de transmission)
COLONNES = [("nom", "Nom", 140), ("prenoms", "Prénoms", 150), ("sexe", "Sexe", 50), ("fonction", "Fonction", 170),
            ("categorie", "Catégorie", 90), ("grade", "Grade", 70), ("matricule", "Matricule", 90), ("nip", "NIP / NPI", 100),
            ("date_naissance", "Date de naissance", 120), ("telephone", "Téléphone", 110),
            ("date_premiere_ps", "1re prise de service", 120), ("date_ps_ecole", "Prise de service dans l'école", 120),
            ("diplome_academique", "Diplôme académique", 110), ("ceap", "CEAP (oui/non)", 70), ("cap", "CAP (oui/non)", 70),
            ("classe", "Classe tenue", 80)]


def role_de(fonction):
    f = re.sub(r"[^a-z]", " ", (fonction or "").lower().replace("é", "e").replace("è", "e"))
    if "adjoint" in f:
        return "adjoint"
    if "direct" in f:
        return "directeur"
    if any(m in f for m in ("enseign", "institut", "educat", "maitre", "professeur", "animat")):
        return "enseignant"
    if any(m in f for m in ("secret", "compta", "econom", "caiss", "administr")):
        return "administratif"
    return "soutien"


def enregistrer(app, H):

    def garde():
        if not config.juridiction():
            abort(404)

    def annee_req():
        a = request.values.get("annee") or J.annee()
        return a if re.match(r"^\d{4}-\d{4}$", a) else J.annee()

    def ecole_ou_404(eid):
        e = J.ecole(eid)
        if not e:
            abort(404)
        return e

    def entier(nom):
        try:
            return int(request.args.get(nom) or 0) or None
        except ValueError:
            return None

    def fiche_stockee(eid, sec, cle, annee):
        d = J.section(eid, sec, annee) or {}
        f = d.get(cle) if isinstance(d, dict) else None
        return f if isinstance(f, dict) else {}

    def ecrire_fiche(eid, sec, cle, annee, contenu):
        d = J.section(eid, sec, annee) or {}
        if not isinstance(d, dict):
            d = {}
        d[cle] = contenu
        J.ecrire_section(eid, sec, d, annee, source="saisie")

    # ------------------------------------------------------------------ hub
    @app.route("/juridiction/saisie")
    @H.connexion_requise("jur_fiches")
    def jur_saisie():
        garde()
        annee = annee_req()
        cs_id = entier("cs")
        if config.EDITION == "cs" and not cs_id:
            c = J.cs_courante()
            cs_id = c["id"] if c else None
        zone_id = entier("zone")
        texte = (request.args.get("q") or "").strip().lower()
        ecoles = [e for e in J.ecoles(cs_id=cs_id, zone_id=zone_id) if not texte or texte in (e["nom"] or "").lower()]
        secs = {}
        for r in q("SELECT ecole_id, section, donnees, source, maj FROM jur_sections WHERE annee=? AND section IN "
                   "('recensement','rapports','personnel')", (annee,)):
            try:
                secs.setdefault(r["ecole_id"], {})[r["section"]] = (json.loads(r["donnees"]), r["source"], r["maj"])
            except ValueError:
                pass
        lignes = []
        for e in ecoles:
            s = secs.get(e["id"], {})
            etats = {}
            for code, sec, cle, types, _l in FICHES:
                if e["type"] not in types:
                    etats[code] = None
                    continue
                d = (s.get(sec) or ({}, "", ""))[0]
                f = d.get(cle) if isinstance(d, dict) else None
                v = f.get("valeurs") if isinstance(f, dict) else None
                etats[code] = ("saisie" if isinstance(f, dict) and f.get("source") == "saisie" else "recue") if v else "absente"
            pers = (s.get("personnel") or ([], "", ""))[0] or []
            lignes.append({"e": e, "etats": etats, "n_pers": len(pers) if isinstance(pers, list) else 0})
        return render_template("jur_saisie.html", lignes=lignes, FICHES=FICHES, annee=annee, annees=J.annees(),
                               cs=J.cs_liste(), zones=J.zones(cs_id), cs_id=cs_id, zone_id=zone_id, q=texte)

    # ------------------------------------------------------------------ une fiche officielle
    def urls(eid, code, annee):
        return {"retour": url_for("jur_saisie", annee=annee), "enregistrer": url_for("jur_saisie_fiche", eid=eid, code=code, annee=annee),
                "pdf": url_for("jur_fiche_pdf", ecole_id=eid, fiche=code, annee=annee),
                "pdf_vierge": url_for("jur_fiche_pdf", ecole_id=eid, fiche=code, annee=annee, vierge=1),
                "soeur": url_for("jur_saisie_fiche", eid=eid, code=MRA.SOEUR.get(code, code), annee=annee),
                "doc_url": lambda d: url_for("jur_saisie_fiche", eid=eid, code=d, annee=annee)}

    def saisies_recensement(typ, stock):
        """Valeurs de départ du formulaire : les saisies enregistrées, à défaut la fiche transmise par l'école
        (sans les cases calculées, que le formulaire recalcule)."""
        if isinstance(stock.get("saisies"), dict):
            return dict(stock["saisies"])
        v = dict(stock.get("valeurs") or {})
        if not v:
            return {}
        schema = MRE.SCHEMAS[typ]
        dyn = MRE.nb_lignes_dyn(schema, v, {})
        _eff, calc, _orig, _al = MRE.evaluer(schema, v, {}, dyn)
        return {k: x for k, x in v.items() if k not in calc and not MRE.vide(x)}

    def contexte_recensement(typ, saisies, annee, stock):
        schema = MRE.SCHEMAS[typ]
        auto = {}
        dyn = MRE.nb_lignes_dyn(schema, saisies, auto)
        MRE.completer_auto(schema, auto, dyn)
        eff, calc, orig, al = MRE.evaluer(schema, saisies, auto, dyn)
        return {"schema": schema, "typ": typ, "annee": annee, "saisies": saisies, "auto": auto, "infos": [],
                "dyn": dyn, "eff": eff, "calc": calc, "orig": orig, "ctrl": MRE.controles(typ, eff, al),
                "par": stock.get("par"), "maj": stock.get("maj"),
                "n_saisis": sum(1 for v in orig.values() if v == "saisie"), "n_calcules": sum(1 for v in orig.values() if v == "calculée"),
                "n_rempli": sum(1 for v in eff.values() if not MRE.vide(v)), "n_total": len(eff)}

    def identification(e, doc):
        """Bloc 1 (identification) pré-rempli d'après la fiche de l'école dans la juridiction ; modifiable."""
        e = dict(e)
        em = doc.endswith("-em")
        statut = "Privé" if (e.get("secteur") or "").lower().startswith("priv") else "Public"
        brut = {"nom_ecole": e.get("nom"), "statut": statut, "cs": e.get("cs_nom"), "zone": e.get("zone_nom"),
                "departement": e.get("departement"), "commune": e.get("commune"), "arrondissement": e.get("arrondissement"),
                "village": e.get("localite"), "telephone": e.get("telephone"), "email": e.get("email"),
                "annee_creation": e.get("annee_creation"), "directeur_nom": e.get("directeur_nom"),
                "directeur_titre": e.get("directeur_titre")}
        if em:
            brut["contact_directeur"] = e.get("directeur_tel") or e.get("telephone")
            brut["adresse_postale"] = e.get("adresse")
        else:
            brut["bp"] = e.get("adresse")
        specs = dict(MRA.champs_editables(doc, 1))
        sortie = {}
        for k, val in brut.items():
            if k not in specs or val in (None, ""):
                continue
            val = str(val).strip()
            if k == "directeur_titre":
                val = "Directrice" if "trice" in val.lower() else "Directeur"
            ok_, propre, _m = MRA.valider_valeur(specs[k], val)
            if ok_:
                sortie[k] = propre
        return sortie

    @app.route("/juridiction/saisie/<int:eid>/<code>", methods=["GET", "POST"])
    @H.connexion_requise("jur_fiches")
    def jur_saisie_fiche(eid, code):
        garde()
        if code not in FICHES_D:
            abort(404)
        if g.get("user") and g.user["role"] == "cp" and request.method == "POST":
            abort(403)
        e = ecole_ou_404(eid)
        annee = annee_req()
        _c, sec, cle, _types, lib = FICHES_D[code]
        stock = fiche_stockee(eid, sec, cle, annee)
        J_ = urls(eid, code, annee)
        if sec == "recensement":
            if request.method == "POST":
                donnees = request.get_json(silent=True) or {}
                brut = donnees.get("valeurs") if isinstance(donnees.get("valeurs"), dict) else {}
                propres, erreurs, _inc = MRE.valider_saisies(cle, brut)
                if erreurs:
                    return jsonify(ok=False, erreurs=erreurs[:20], n=len(erreurs)), 400
                ctx = contexte_recensement(cle, propres, annee, stock)
                ecrire_fiche(eid, sec, cle, annee, {"annee": annee, "valeurs": dict(ctx["eff"]), "saisies": propres, "source": "saisie",
                                                    "par": g.user["nom"] if g.get("user") else "", "maj": H.maintenant()})
                H.journal("jur_saisie_fiche", f"{e['code']} {code} {annee} ({len(propres)} valeurs)")
                return jsonify(ok=True, n=len(propres))
            ctx = contexte_recensement(cle, saisies_recensement(cle, stock), annee, stock)
            schema = ctx["schema"]
            tables = {t["k"]: MRE.vue_tableau(t, ctx["dyn"], ctx["saisies"], ctx["calc"], ctx["orig"]) for _s, t in MRE.tableaux(schema)}
            schema = dict(schema, titre_court=f"{schema['titre_court']} — {e['nom']}")
            ctx["schema"] = schema
            return render_template("recensement_fiche.html", **ctx, tables=tables, sections=MRE.sections(schema),
                                   annees=J.annees() or [annee], OUINON=MRE.OUINON, TYPES=MRE.TYPES, J=J_)
        # rapports de rentrée / de fin d'année
        doc = cle
        over = dict(stock.get("saisies") or {})
        if not over and stock.get("valeurs"):
            calc = set(MRA.tous_calculs(doc))
            over = {k: v for k, v in stock["valeurs"].items() if k not in calc and str(v or "").strip() not in ("",)}
        if not over and request.method == "GET":
            over = identification(e, doc)   # fiche vierge : identification reprise de la liste des écoles
        if request.method == "POST":
            action = request.form.get("action", "sauver")
            if action == "reinit":
                ecrire_fiche(eid, sec, cle, annee, {"annee": annee, "valeurs": {}, "saisies": {}, "source": "saisie", "maj": H.maintenant()})
                flash("Fiche vidée.", "success")
                return redirect(J_["enregistrer"])
            try:
                n_pers = int(request.form.get("pers_n") or 0)
            except ValueError:
                n_pers = 0
            n_pers = max(MRA.bloc_personnel(doc)["min"], min(MRA.PERS_MAX, n_pers or MRA.nb_lignes_personnel(doc, over)))
            nouv, erreurs = {}, []
            for k, spec in MRA.champs_editables(doc, n_pers):
                brut = (request.form.get(k) or "").strip()
                if brut == "":
                    continue
                ok_, val, msg = MRA.valider_valeur(spec, brut)
                if not ok_:
                    erreurs.append(f"{spec['lib']} : {msg}")
                    continue
                nouv[k] = val
            if erreurs:
                for m in erreurs[:12]:
                    flash(m, "danger")
                flash("Rien n'a été enregistré : corrigez les cases signalées.", "warning")
                over = nouv
            else:
                finales = MRA.valeurs_calculees(doc, nouv)
                ecrire_fiche(eid, sec, cle, annee, {"annee": annee, "valeurs": MRA.valeurs_completes(doc, finales), "saisies": nouv,
                                                    "source": "saisie", "par": g.user["nom"] if g.get("user") else "", "maj": H.maintenant()})
                H.journal("jur_saisie_fiche", f"{e['code']} {code} {annee} ({len(nouv)} valeurs)")
                flash(f"{lib} de « {e['nom']} » enregistrée ({len(nouv)} case(s) saisie(s) ; les totaux sont calculés).", "success")
                if action == "pdf":
                    return redirect(J_["pdf"])
                return redirect(J_["enregistrer"])
        finales = MRA.valeurs_calculees(doc, over)
        info = dict(MRA.DOCS[doc], titre=f"{MRA.DOCS[doc]['titre']} — {e['nom']}")
        return render_template("rapports_formulaire.html", doc=doc, info=info, annee=annee, annees=J.annees() or [annee],
                               sections=MRA.schema(doc), auto={}, over=over, v=finales, calc=MRA.tous_calculs(doc),
                               n_pers=MRA.nb_lignes_personnel(doc, over), ind={"inactive": True}, origine={},
                               stock={"maj": stock.get("maj")}, controles=MRA.controles(doc, finales), fichiers=[],
                               niv_ep=MRA.NIV_EP, soeur=MRA.SOEUR[doc], active=True, statuts_agent=MRA.STATUTS_AGENT, J=J_)

    # ------------------------------------------------------------------ état nominatif du personnel d'une école
    @app.route("/juridiction/saisie/<int:eid>/personnel", methods=["GET", "POST"])
    @H.connexion_requise("jur_personnel")
    def jur_saisie_personnel(eid):
        garde()
        e = ecole_ou_404(eid)
        annee = annee_req()
        actuels = J.section(eid, "personnel", annee) or []
        if request.method == "POST":
            lignes = []
            n = int(request.form.get("n") or 0)
            for i in range(min(n, 400)):
                d = {k: (request.form.get(f"{k}_{i}") or "").strip() for k, _l, _w in COLONNES}
                if not d["nom"]:
                    continue
                d["sexe"] = d["sexe"].upper()[:1]
                d["categorie"] = d["categorie"].upper() if d["categorie"].upper() in CATEGORIES else ("PRIVE" if e["secteur"] == "prive" else "")
                d["role"] = role_de(d["fonction"])
                d["ceap"] = d["ceap"].lower() in ("oui", "o", "1", "x")
                d["cap"] = d["cap"].lower() in ("oui", "o", "1", "x")
                anc = next((p for p in actuels if (p.get("nom"), p.get("prenoms")) == (d["nom"], d["prenoms"])), {})
                lignes.append({**anc, **d, "actif": True, "source": "saisie"})
            J.ecrire_section(eid, "personnel", lignes, annee, source="saisie")
            dirs = [p for p in lignes if p["role"] == "directeur"]
            if dirs:
                ex("UPDATE jur_ecoles SET directeur_nom=?, directeur_tel=COALESCE(NULLIF(?, ''), directeur_tel) WHERE id=?",
                   (f"{dirs[0]['nom']} {dirs[0]['prenoms']}".strip(), dirs[0].get("telephone") or "", eid))
            H.journal("jur_saisie_personnel", f"{e['code']} {annee} ({len(lignes)} agents)")
            flash(f"État nominatif de « {e['nom']} » enregistré : {len(lignes)} agent(s).", "success")
            return redirect(url_for("jur_saisie_personnel", eid=eid, annee=annee))
        lignes = [dict(p) for p in actuels if isinstance(p, dict)]
        for p in lignes:
            p["ceap"] = "oui" if p.get("ceap") is True or str(p.get("ceap")).lower() in ("oui", "1", "true") else ""
            p["cap"] = "oui" if p.get("cap") is True or str(p.get("cap")).lower() in ("oui", "1", "true") else ""
        if not lignes:
            lignes = [{"fonction": "Directeur / directrice"}] + [{"fonction": "Adjoint(e)"} for _ in range(5)]
        return render_template("jur_saisie_personnel.html", e=e, lignes=lignes, COLONNES=COLONNES, FONCTIONS=FONCTIONS,
                               CATEGORIES=CATEGORIES, annee=annee, annees=J.annees())

    # ------------------------------------------------------------------ directeurs de toutes les écoles
    @app.route("/juridiction/saisie/directeurs", methods=["GET", "POST"])
    @H.connexion_requise("jur_ecoles")
    def jur_saisie_directeurs():
        garde()
        cs_id = entier("cs")
        if config.EDITION == "cs" and not cs_id:
            c = J.cs_courante()
            cs_id = c["id"] if c else None
        ecoles = J.ecoles(cs_id=cs_id)
        if request.method == "POST":
            n = 0
            for e in ecoles:
                nom = request.form.get(f"nom_{e['id']}")
                if nom is None:
                    continue
                ex("UPDATE jur_ecoles SET directeur_titre=?, directeur_nom=?, directeur_tel=?, telephone=COALESCE(NULLIF(?, ''), telephone) WHERE id=?",
                   ((request.form.get(f"titre_{e['id']}") or "").strip(), nom.strip(), (request.form.get(f"tel_{e['id']}") or "").strip(),
                    (request.form.get(f"telecole_{e['id']}") or "").strip(), e["id"]))
                n += 1
            H.journal("jur_saisie_directeurs", f"{n} école(s)")
            flash(f"Directeurs enregistrés ({n} école(s)).", "success")
            return redirect(url_for("jur_saisie_directeurs", cs=cs_id or ""))
        return render_template("jur_saisie_directeurs.html", ecoles=ecoles, cs=J.cs_liste(), cs_id=cs_id)
