# -*- coding: utf-8 -*-
"""v1.8 — alertes de pilotage du CCS, des CP et de la DDEMP (applications Circonscription scolaire et DDEMP).

Une seule page, /juridiction/alertes, qui rassemble ce qui demande une action, du plus urgent au moins urgent :

* écoles qui n'ont jamais transmis leurs données cette année, ou plus depuis 30 jours ;
* écoles en manque d'enseignants, classes pléthoriques ;
* écoles sans aucune visite (CCS / CP) depuis le début du trimestre ;
* retard des CP et du CCS sur leur programmation du trimestre (visites de classes, séances d'UP, formations) ;
* séances d'unités pédagogiques prévues, date passée, non tenues.

Le résumé (nombre d'alertes hautes / moyennes) est aussi affiché sur le tableau de bord (fonction de gabarit
``alertes_pilotage()``).
"""
from datetime import date, timedelta

from flask import abort, g, render_template, request, url_for

import config
from db import q

JOURS_TRANSMISSION = 30
NIVEAUX = {"haute": 0, "moyenne": 1, "info": 2}
DROITS_ALERTES = ("jur_ecoles", "jur_visites", "jur_cp_bilan", "jur_transmission")


def periode_du_jour(jour=None):
    """(annee, période T1/T2/T3) de l'année scolaire en cours."""
    d = jour or date.today()
    a1 = d.year if d.month >= 9 else d.year - 1
    annee = f"{a1}-{a1 + 1}"
    if d.month >= 9:
        per = "T1"
    elif d.month <= 3:
        per = "T2"
    else:
        per = "T3"
    return annee, per


def bornes(annee, periode):
    a1, a2 = (int(x) for x in annee.split("-"))
    return {"T1": (f"{a1}-09-01", f"{a1}-12-31"), "T2": (f"{a2}-01-01", f"{a2}-03-31"),
            "T3": (f"{a2}-04-01", f"{a2}-08-31")}[periode]


def avancement(annee, periode, jour=None):
    """Part du trimestre écoulée (0 à 1). Le 3e trimestre s'arrête fin juin pour les activités pédagogiques."""
    d1, d2 = bornes(annee, periode)
    debut = date.fromisoformat(d1)
    fin = date.fromisoformat(d2)
    if periode == "T3":
        fin = date(fin.year, 6, 30)
    j = jour or date.today()
    if j <= debut:
        return 0.0
    if j >= fin:
        return 1.0
    return (j - debut).days / max(1, (fin - debut).days)


def ecart_programmation(prog, real, part):
    """Retard en points de pourcentage par rapport à l'avancement attendu (None : rien de programmé)."""
    if not prog:
        return None
    attendu = prog * part
    if attendu < 1:
        return None
    return round(100.0 * (attendu - (real or 0)) / prog, 1)


def enregistrer(app, H):
    import m_juridiction as J

    def autorise():
        return bool(g.get("user")) and any(H.peut(m) for m in DROITS_ALERTES)

    def calculer(annee, cs_id=None, jour=None):
        """Liste d'alertes {niveau, ico, titre, detail, lien, ecoles: [noms], cs_nom} triée par gravité."""
        jour = jour or date.today()
        annee_j, periode = periode_du_jour(jour)
        alertes = []
        ecs = list(J.ecoles(cs_id=cs_id))
        par_id = {e["id"]: e for e in ecs}
        ids = list(par_id)

        def noms(liste):
            return [f"{e['nom']}" + (f" ({e['zone_nom']})" if e["zone_nom"] else "") for e in liste]

        # 1. transmissions
        derniere = {}
        if ids:
            marque = ",".join("?" * len(ids))
            for r in q(f"SELECT ecole_id, MAX(maj) m FROM jur_sections WHERE annee=? AND ecole_id IN ({marque}) GROUP BY ecole_id",
                       [annee] + ids):
                derniere[r["ecole_id"]] = (r["m"] or "")[:10]
        jamais = [e for e in ecs if e["id"] not in derniere]
        limite = (jour - timedelta(days=JOURS_TRANSMISSION)).isoformat()
        anciennes = [e for e in ecs if e["id"] in derniere and derniere[e["id"]] and derniere[e["id"]] < limite]
        if jamais:
            alertes.append({"niveau": "haute", "ico": "courrier", "titre": f"{len(jamais)} école(s) sans aucune transmission en {annee}",
                            "detail": "Leurs effectifs, enseignants et résultats manquent dans les statistiques et les bilans.",
                            "lien": url_for("jur_transmissions") if "jur_transmissions" in app.view_functions else None,
                            "ecoles": noms(jamais)})
        if anciennes:
            alertes.append({"niveau": "moyenne", "ico": "sablier",
                            "titre": f"{len(anciennes)} école(s) sans transmission depuis plus de {JOURS_TRANSMISSION} jours",
                            "detail": "Relancer les directeurs pour une transmission à jour (appel, notes, effectifs).",
                            "lien": url_for("jur_transmissions") if "jur_transmissions" in app.view_functions else None,
                            "ecoles": [f"{n} – dernière le {derniere[e['id']][8:10]}/{derniere[e['id']][5:7]}/{derniere[e['id']][:4]}"
                                       for n, e in zip(noms(anciennes), anciennes)]})

        # 2. enseignants et classes (calculs du tableau de bord)
        try:
            import a_tableau
            lignes = a_tableau.donnees(annee, cs_id=cs_id)
        except Exception:  # noqa: BLE001
            lignes = []
        manque = [l for l in lignes if (l.get("besoin") or {}).get("manque")]
        if manque:
            total = sum(l["besoin"]["manque"] for l in manque)
            alertes.append({"niveau": "haute", "ico": "enseignant", "titre": f"Manque de {total} enseignant(s) dans {len(manque)} école(s)",
                            "detail": "Classes sans enseignant titulaire d'après les effectifs et le personnel transmis.",
                            "lien": url_for("jur_tableau") if "jur_tableau" in app.view_functions else None,
                            "ecoles": [f"{l['nom']} : {l['besoin']['manque']} manquant(s)" for l in
                                       sorted(manque, key=lambda x: -x["besoin"]["manque"])]})
        pleth = [l for l in lignes if l.get("plethoriques")]
        if pleth:
            alertes.append({"niveau": "moyenne", "ico": "groupe",
                            "titre": f"{sum(l['plethoriques'] for l in pleth)} classe(s) pléthorique(s) dans {len(pleth)} école(s)",
                            "detail": "Classes au-delà du seuil d'effectif : envisager un dédoublement ou une redistribution.",
                            "lien": url_for("jur_tableau") if "jur_tableau" in app.view_functions else None,
                            "ecoles": [f"{l['nom']} : {l['plethoriques']} classe(s) > {l['seuil']}" for l in pleth]})

        # 3. écoles non visitées depuis le début du trimestre (année en cours seulement)
        if annee == annee_j and ids:
            d1, _d2 = bornes(annee, periode)
            vues = {r["ecole_id"] for r in q("SELECT DISTINCT ecole_id FROM jur_visites WHERE annee=? AND date>=? AND date<=?",
                                              (annee, d1, jour.isoformat())) if r["ecole_id"]}
            non_vues = [e for e in ecs if e["id"] not in vues]
            part = avancement(annee, periode, jour)
            if non_vues and part >= .25:
                alertes.append({"niveau": "moyenne" if part >= .6 else "info", "ico": "rechercher",
                                "titre": f"{len(non_vues)} école(s) sur {len(ecs)} sans visite ce trimestre",
                                "detail": f"Aucune visite de classe ni d'école enregistrée depuis le {d1[8:10]}/{d1[5:7]}/{d1[:4]} "
                                          f"({round(part * 100)} % du trimestre écoulé).",
                                "lien": url_for("jur_visites") if "jur_visites" in app.view_functions else None,
                                "ecoles": noms(non_vues)})

        # 4. retard sur la programmation des CP et du CCS
        calc = getattr(H, "jur_cp_calculer", None)
        if callable(calc) and annee == annee_j:
            part = avancement(annee, periode, jour)
            for cs in ([J.cs_par_id(cs_id)] if cs_id else list(J.cs_liste())):
                if not cs:
                    continue
                try:
                    b = calc(annee, periode, cs["id"])
                except Exception:  # noqa: BLE001 — module CP non configuré
                    continue
                retards = []
                for a in b.get("acteurs") or []:
                    r = (b.get("s2") or {}).get(a["cle"]) or {}
                    for prog_k, real_k, lib in (("vc_prog_t", "vc_real_t", "visites de classes"),
                                                ("ve_prog_t", "ve_real_t", "visites d'écoles"),
                                                ("up_prog", "up_real", "séances d'UP"), ("fo_prog", "fo_real", "formations")):
                        e = ecart_programmation(r.get(prog_k), r.get(real_k), part)
                        if e is not None and e >= 25:
                            retards.append(f"{a['lib']}{' – ' + a['nom'] if a.get('nom') else ''} : {r.get(real_k) or 0} "
                                           f"{lib} réalisée(s) sur {r.get(prog_k)} programmée(s)")
                if retards:
                    alertes.append({"niveau": "moyenne", "ico": "calendrier",
                                    "titre": f"Retard sur la programmation du {periode[1]}{'er' if periode == 'T1' else 'e'} trimestre"
                                             + (f" – {cs['nom']}" if not cs_id else ""),
                                    "detail": f"{round(part * 100)} % du trimestre est écoulé ; les activités ci-dessous ont "
                                              "au moins 25 points de retard sur le rythme attendu.",
                                    "lien": url_for("jur_cp_bilan", annee=annee, periode=periode)
                                    if "jur_cp_bilan" in app.view_functions else None,
                                    "ecoles": retards})

        # 5. séances d'UP prévues et non tenues
        try:
            sql = ("SELECT a.date, a.theme, u.nom up_nom FROM jur_up_activites a JOIN jur_up u ON u.id=a.up_id "
                   "WHERE a.annee=? AND a.prevue=1 AND COALESCE(a.executee,0)=0 AND a.date IS NOT NULL AND a.date<?")
            args = [annee, jour.isoformat()]
            if cs_id:
                sql += " AND u.cs_id=?"
                args.append(cs_id)
            seances = q(sql + " ORDER BY a.date", args)
        except Exception:  # noqa: BLE001 — module des UP absent
            seances = []
        if seances:
            alertes.append({"niveau": "info", "ico": "groupe", "titre": f"{len(seances)} séance(s) d'UP prévue(s) et non tenue(s)",
                            "detail": "Date passée sans exécution enregistrée : reprogrammer ou mettre à jour le suivi des UP.",
                            "lien": url_for("jur_up") if "jur_up" in app.view_functions else None,
                            "ecoles": [f"{s['up_nom']} – {s['date'][8:10]}/{s['date'][5:7]}/{s['date'][:4]}"
                                       + (f" : {s['theme']}" if s["theme"] else "") for s in seances]})
        # v1.9 : directeurs injoignables sur WhatsApp (numéro absent ou invalide)
        sans_num = [e for e in ecs if not H.notif.normaliser_tel(e["directeur_tel"])]
        if sans_num:
            alertes.append({"niveau": "info", "ico": "message",
                            "titre": f"{len(sans_num)} directeur(s) sans numéro de téléphone valide",
                            "detail": "Ils ne peuvent pas être ajoutés au groupe WhatsApp des directeurs : compléter la fiche de l'école.",
                            "lien": url_for("groupes_whatsapp", groupe="directeurs", cs=cs_id or None) if "groupes_whatsapp" in app.view_functions else None,
                            "ecoles": noms(sans_num)})
        alertes.sort(key=lambda a: NIVEAUX[a["niveau"]])
        return alertes

    def cs_et_annee():
        annees = J.annees()
        annee = request.args.get("annee") or J.annee()
        if annee not in annees:
            annee = J.annee()
        if config.EDITION == "cs":
            c = J.cs_courante()
            cs_id = c["id"] if c else None
        else:
            try:
                cs_id = int(request.args.get("cs") or 0) or None
            except ValueError:
                cs_id = None
            if cs_id and not J.cs_par_id(cs_id):
                cs_id = None
        return annee, annees, cs_id

    @app.route("/juridiction/alertes")
    @H.connexion_requise()
    def jur_alertes():
        if not config.juridiction():
            abort(404)
        if not autorise():
            abort(403)
        annee, annees, cs_id = cs_et_annee()
        alertes = calculer(annee, cs_id)
        return render_template("jur_alertes.html", alertes=alertes, annee=annee, annees=annees, cs_id=cs_id,
                               cs=J.cs_liste(), nb={k: sum(1 for a in alertes if a["niveau"] == k) for k in NIVEAUX})

    def alertes_pilotage():
        """Résumé pour le tableau de bord : {"haute": n, "moyenne": n, "info": n, "premieres": [...]} ou None."""
        if not config.juridiction() or not autorise():
            return None
        try:
            annee, _a, cs_id = cs_et_annee()
            al = calculer(annee, cs_id)
        except Exception:  # noqa: BLE001 — le tableau de bord ne doit jamais tomber à cause des alertes
            return None
        return {**{k: sum(1 for a in al if a["niveau"] == k) for k in NIVEAUX}, "premieres": al[:3]}

    app.jinja_env.globals.update(alertes_pilotage=alertes_pilotage)
    H.jur_alertes_calculer = calculer
