# -*- coding: utf-8 -*-
"""v1.26 — Communication et alertes (spécification commune PVS, lot B).

* Notes de service, circulaires et convocations : émises par l'école, l'UP, la zone, la CS ou la DDEMP vers les entités
  inférieures (niveau des destinataires + liste ; vide = toutes les entités de ce niveau), note signée (QR) et état des
  accusés de réception ;
* boîte de réception : notes adressées à l'entité du compte (école ouverte depuis la CS comprise, ou notes reçues par
  import Excel d'un autre appareil), bouton « Accuser réception » (ligne de la feuille « Accusés de réception ») ;
* échéances et rappels (rapports, statistiques, examens…), agenda partagé, messages aux parents (WhatsApp, SMS, copie) ;
* alertes : échéances en retard ou proches, notes non lues, convocations des 7 prochains jours, élèves en alerte de
  décrochage, licences « Non examiné » / « Inapte », stocks de cantine épuisés (modules Santé et Sport).

Moteur commun : registres.py (ajouter, modifier, supprimer, réinitialiser, Excel export / modèle / import avec clé
d'unicité, liste certifiée PDF signée avec QR, en-têtes de tableau fixes).
"""
from datetime import date, timedelta
from urllib.parse import quote

from flask import flash, g, redirect, render_template, request, url_for

import registres as R

TYPES_NOTE = ["Note de service", "Circulaire", "Convocation", "Communiqué", "Lettre", "Message"]
TYPES_ECH = ["Rapport", "Statistiques", "Examen", "Réunion", "Formation", "Compétition", "Paiement", "Autre"]
STATUTS_ECH = ["À faire", "En cours", "Fait"]
CANAUX = ["WhatsApp", "SMS", "Affichage", "Réunion des parents", "Crieur public", "Radio communautaire"]
TYPES_AGENDA = ["Réunion", "Formation", "Animation pédagogique", "Visite", "Compétition", "Examen", "Cérémonie", "Autre"]
NIV_DEST = ["ECOLE", "UP", "ZONE", "CS"]


def libelle_note(x):
    ref = (x.get("reference") or "").strip()
    return f"{ref} — {x.get('objet') or ''}".strip(" —") if ref else (x.get("objet") or "")


def etat_echeance(x, jour=None):
    jour = jour or date.today()
    if (x.get("statut") or "") == "Fait":
        return "Fait"
    try:
        d = date.fromisoformat((x.get("dateLimite") or "")[:10])
    except ValueError:
        return ""
    n = (d - jour).days
    rappel = x.get("rappelJours")
    rappel = 7 if rappel in (None, "") else int(rappel)
    if n < 0:
        return f"En retard ({-n} j)"
    if n <= rappel:
        return f"À rappeler (J-{n})"
    return "À venir"


def _liste_dest(x):
    return [d.strip() for d in (x.get("destinataires") or "").replace(",", ";").split(";") if d.strip()]


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.DROITS["notes_service"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent", "enseignant"}
    R.types_documents({"reg_communication_notes": "Note de service / circulaire / convocation",
                       "reg_communication_notes_note": "Note de service / circulaire / convocation",
                       "reg_communication_notes_accuses": "État des accusés de réception",
                       "reg_communication_agenda": "Agenda des activités", "reg_communication_echeances": "Échéances et rappels",
                       "reg_communication_messages": "Messages aux parents", "reg_communication_lectures": "Accusés de réception"})

    G = R.Groupe(app, H, "communication", "Communication et alertes", "notes_service", ico="annonce",
                 sous_titre="Notes de service, circulaires et convocations avec accusé de réception, échéances et rappels, alertes, "
                            "messages aux parents (WhatsApp, SMS), agenda partagé",
                 listes={"types_note": TYPES_NOTE, "niv_dest": NIV_DEST, "types_ech": TYPES_ECH, "statuts_ech": STATUTS_ECH,
                         "canaux": CANAUX, "types_agenda": TYPES_AGENDA, "dest_parents": ["Tous les parents d’élèves"]},
                 onglets_avant=[("liaison_boite", "Boîte de réception", {}), ])

    # ------------------------------------------------------------------ registres
    def dest_effectif(x):
        lst = _liste_dest(x)
        if lst:
            return len(lst)
        niv = x.get("destNiveau") or "ECOLE"
        f = {"ECOLE": R.liste_ecoles, "UP": R.liste_up, "ZONE": R.liste_zones}.get(niv)
        n = len(f()) if f else 0
        return n or 1

    def accuses_de(x):
        lib = libelle_note(x)
        return [dict(a) for a in q(f"SELECT * FROM reg_communication_lectures WHERE note=? ORDER BY date", (lib,))]

    def calc_note(x):
        a = len({(y.get("niveau"), R._norm(y.get("entite"))) for y in accuses_de(x)})
        return {"Accusés de réception": f"{a} / {dest_effectif(x)}"}

    def sig_note(x):
        s = R.signature_autorite()
        if (x.get("signataire") or "").strip():
            s = dict(s, titre=x["signataire"].strip())
        return [s]

    def doc_note(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        corps = []
        ent = [["Type", x.get("type") or ""], ["Référence", x.get("reference") or ""], ["Date", R.jjmmaaaa(x.get("date"))],
               ["Émetteur", f"{R.NIVEAUX_LIB.get(x.get('niveau') or '', x.get('niveau') or '')} — {x.get('entite') or ''}".strip(" —")],
               ["Destinataires", "; ".join(_liste_dest(x)) or f"Toutes les entités du niveau « {R.NIVEAUX_LIB.get(x.get('destNiveau') or 'ECOLE')} »"],
               ["Objet", x.get("objet") or ""]]
        if x.get("type") == "Convocation" or x.get("dateReunion"):
            ent += [["Lieu", x.get("lieuReunion") or ""], ["Date de la réunion", R.jjmmaaaa(x.get("dateReunion"))], ["Heure", x.get("heureReunion") or ""]]
        if x.get("echeance"):
            ent.append(["Réponse attendue le", R.jjmmaaaa(x.get("echeance"))])
        corps.append(R.tableau(["Rubrique", "Renseignement"], [r for r in ent if r[1]], [1, 3], R.largeur_utile(False)))
        corps.append(Spacer(1, 10))
        for par in (x.get("texte") or "").split("\n"):
            if par.strip():
                corps.append(Paragraph(R.esc(par.strip()), st["p"]))
        if (x.get("pieces") or "").strip():
            corps += [Spacer(1, 6), Paragraph("<b>Pièces jointes / ampliations :</b> " + R.esc(x["pieces"]), st["petit"])]
        return (x.get("type") or "Note de service"), corps, sig_note(x)

    def doc_accuses(x):
        lst = accuses_de(x)
        dest = _liste_dest(x)
        lignes, vus = [], set()
        for a in lst:
            lignes.append([R.NIVEAUX_LIB.get(a.get("niveau") or "", a.get("niveau") or ""), a.get("entite") or "", R.jjmmaaaa(a.get("date")),
                           a.get("lecteur") or "", a.get("observations") or ""])
            vus.add(R._norm(a.get("entite")))
        for d in dest:
            if R._norm(d) not in vus:
                lignes.append([R.NIVEAUX_LIB.get(x.get("destNiveau") or "ECOLE"), d, "non reçu", "", ""])
        corps = [R.tableau(["N°", "Niveau", "Entité", "Accusé le", "Lecteur", "Observations"], [[i] + l for i, l in enumerate(lignes, 1)],
                           [0.4, 1.2, 2.2, 1, 1.6, 2], R.largeur_utile(False))]
        from reportlab.platypus import Paragraph, Spacer
        corps = [Paragraph(f"<b>{R.esc(libelle_note(x))}</b> — {R.esc(x.get('type') or '')} du {R.jjmmaaaa(x.get('date'))} : "
                           f"{len(vus)} accusé(s) sur {dest_effectif(x)} destinataire(s).", R.styles()["p"]), Spacer(1, 6)] + corps
        return "État des accusés de réception", corps, sig_note(x)

    G.registre("notes", "Notes, circulaires et convocations", [
        ("type", "Type", "choix:types_note"), ("reference", "Référence (n°)", "texte"), ("date", "Date", "date"), ("objet", "Objet", "texte"),
        ("destNiveau", "Niveau des destinataires", "choix:niv_dest"), ("destinataires", "Destinataires", "texte"), ("texte", "Texte", "long"),
        ("lieuReunion", "Lieu (convocation)", "texte"), ("dateReunion", "Date de la réunion (convocation)", "date"),
        ("heureReunion", "Heure (convocation)", "heure"), ("echeance", "Échéance (réponse attendue le)", "date"),
        ("pieces", "Pièces jointes / ampliations", "long"), ("signataire", "Signataire (nom et qualité)", "texte")],
        unite="note", oblig="objet", ordre="date DESC, id DESC", portee="structure", feuille="Notes, circulaires et convocations",
        onglet="Notes et convocations", doc="Registre des notes, circulaires et convocations", entite=True, unique=("reference", "objet"),
        calcul=calc_note, filtres=("type",), colonnes=("niveau", "entite", "type", "reference", "date", "objet", "destNiveau", "destinataires", "echeance"),
        fiches={"note": ("Note signée", "document", doc_note), "accuses": ("État des accusés de réception", "valider-cercle", doc_accuses)},
        defauts=lambda: dict(zip(("niveau", "entite"), R.entite_courante()), type="Note de service", destNiveau="ECOLE", date=date.today().isoformat()),
        aide="Destinataires : libellés séparés par « ; » — vide = toutes les entités du niveau choisi dans votre périmètre. "
             "Les notes reçues d'une autre application s'importent par Excel (même feuille) et apparaissent dans la boîte de réception.")
    G.registre("echeances", "Échéances et rappels", [
        ("objet", "Objet", "texte"), ("type", "Type", "choix:types_ech"), ("dateLimite", "Date limite", "date"), ("rappelJours", "Rappel (jours avant)", "entier"),
        ("responsable", "Responsable", "texte"), ("statut", "Statut", "choix:statuts_ech"), ("observations", "Observations", "long")],
        unite="échéance", oblig="objet", ordre="dateLimite, id", portee="structure", feuille="Échéances et rappels", entite=True,
        unique=("objet", "dateLimite"), calcul=lambda x: {"État": etat_echeance(x)}, filtres=("type", "statut"),
        defauts=lambda: dict(zip(("niveau", "entite"), R.entite_courante()), type="Rapport", rappelJours=7, statut="À faire"),
        doc="Échéances et rappels")

    def actions_message(x):
        t = f"{x.get('objet') or ''} — {x.get('texte') or ''}".strip(" —")
        return [("https://wa.me/?text=" + quote(t), "WhatsApp", "message"), ("sms:?body=" + quote(t), "SMS", "telephone"),
                ("copier:" + t, "Copier", "presse-papiers")]

    G.registre("messages", "Messages aux parents", [
        ("date", "Date", "date"), ("objet", "Objet", "texte"), ("texte", "Message", "long"), ("destinataires", "Destinataires", "liste:dest_parents"),
        ("canal", "Canal", "choix:canaux"), ("envoye", "Envoyé", "oui_non")],
        unite="message", oblig="objet", ordre="date DESC, id DESC", portee="structure", feuille="Messages aux parents", entite=True,
        niveaux=["ECOLE", "UP", "ZONE", "CS"], unique=("date", "objet"), actions=actions_message, filtres=("canal",),
        defauts=lambda: dict(zip(("niveau", "entite"), R.entite_courante()), date=date.today().isoformat(), canal="WhatsApp",
                             destinataires="Tous les parents d’élèves", envoye="Non"),
        doc="Messages aux parents",
        aide="WhatsApp et SMS ouvrent le message prêt à envoyer (« objet — message ») ; la diffusion aux comptes parents reste dans "
             "Communication › Parents.")
    G.registre("agenda", "Agenda partagé", [
        ("date", "Date", "date"), ("heureDebut", "Heure de début", "heure"), ("heureFin", "Heure de fin", "heure"), ("objet", "Objet", "texte"),
        ("type", "Type", "choix:types_agenda"), ("lieu", "Lieu", "texte"), ("participants", "Participants", "long"), ("organisateur", "Organisateur", "texte")],
        unite="activité", oblig="objet", ordre="date, heureDebut", portee="structure", feuille="Agenda partagé", entite=True,
        unique=("date", "objet"), filtres=("type",), doc="Agenda des activités",
        defauts=lambda: dict(zip(("niveau", "entite"), R.entite_courante()), type="Réunion"))
    G.registre("lectures", "Accusés de réception", [
        ("note", "Note", "texte"), ("date", "Date", "date"), ("lecteur", "Lecteur", "texte"), ("observations", "Observations", "long")],
        unite="accusé", oblig="note", ordre="date DESC, id DESC", portee="structure", feuille="Accusés de réception", entite=True,
        unique=("note", "niveau", "entite"), doc="Accusés de réception")
    G.page("liaison_alertes", "Alertes")

    # ------------------------------------------------------------------ boîte de réception
    def portees_visibles():
        p = {R.cle_portee("structure")}
        if R.juridiction() and g.get("ecole"):
            p.add(0)
        return p

    def notes_recues(annee=None):
        niv, ent = R.entite_courante()
        en = R._norm(ent)
        out = []
        ps = sorted(portees_visibles())
        rows = q(f"SELECT * FROM reg_communication_notes WHERE portee IN ({','.join('?' * len(ps))})" + (" AND annee=?" if annee else "")
                 + " ORDER BY date DESC, id DESC", tuple(ps) + ((annee,) if annee else ()))
        for x in rows:
            x = dict(x)
            if (x.get("niveau") or "") == niv:
                continue                                   # note émise à ce niveau (par l'entité elle-même)
            if (x.get("destNiveau") or "ECOLE") != niv:
                continue
            dest = [R._norm(d) for d in _liste_dest(x)]
            if dest and en not in dest:
                continue
            out.append(x)
        return out

    def lue(x):
        niv, ent = R.entite_courante()
        return bool(q("SELECT 1 FROM reg_communication_lectures WHERE note=? AND niveau=? AND lower(entite)=lower(?)",
                      (libelle_note(x), niv, ent), un=True))

    @app.route("/liaison/boite")
    @H.connexion_requise("notes_service")
    def liaison_boite():
        annee = (request.args.get("annee") or "").strip() or None
        notes = [dict(x, lue=lue(x), lib=libelle_note(x)) for x in notes_recues(annee)]
        return render_template("liaison_boite.html", G=G, ep_actif="liaison_boite", notes=notes, entite=R.entite_courante(),
                               NIV=R.NIVEAUX_LIB, jj=R.jjmmaaaa, annee=annee)

    @app.route("/liaison/accuser/<int:nid>", methods=["POST"])
    @H.connexion_requise("notes_service")
    def liaison_accuser(nid):
        ps = sorted(portees_visibles())
        x = q(f"SELECT * FROM reg_communication_notes WHERE id=? AND portee IN ({','.join('?' * len(ps))})", (nid,) + tuple(ps), un=True)
        if not x or x["id"] not in {n["id"] for n in notes_recues()}:
            flash("Note introuvable dans votre boîte de réception.", "warning")
            return redirect(url_for("liaison_boite"))
        x = dict(x)
        niv, ent = R.entite_courante()
        if not lue(x):
            nom = (g.user["nom"] or "").strip() or g.user["identifiant"]
            ex("INSERT INTO reg_communication_lectures (portee, annee, niveau, entite, note, date, lecteur, observations, cree_le, cree_par, maj) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (R.cle_portee("structure"), x.get("annee") or R.annee_active(), niv, ent, libelle_note(x),
                                                  date.today().isoformat(), nom, (request.form.get("observations") or "").strip()[:400],
                                                  H.maintenant(), g.user["id"], H.maintenant()))
            H.journal("note_accusee", libelle_note(x))
        flash("Réception accusée.", "success")
        return redirect(url_for("liaison_boite"))

    # ------------------------------------------------------------------ alertes
    def alertes(jour=None):
        jour = jour or date.today()
        out = []
        ps = sorted(portees_visibles())
        for x in q(f"SELECT * FROM reg_communication_echeances WHERE portee IN ({','.join('?' * len(ps))}) AND COALESCE(statut,'')<>'Fait'", tuple(ps)):
            e = etat_echeance(dict(x), jour)
            if e.startswith(("En retard", "À rappeler")):
                out.append(("echeance", e, f"{x['objet']} — date limite {R.jjmmaaaa(x['dateLimite'])}",
                            url_for("reg_page", gcle="communication", rcle="echeances", annee=x["annee"])))
        for x in notes_recues():
            if not lue(x):
                out.append(("note", "Note non lue", f"{x.get('type') or 'Note'} : {libelle_note(x)} ({x.get('entite') or ''})", url_for("liaison_boite")))
        vus = set()
        for x in list(notes_recues()) + [dict(y) for y in q(f"SELECT * FROM reg_communication_notes WHERE portee IN ({','.join('?' * len(ps))})", tuple(ps))]:
            if x["id"] in vus or not x.get("dateReunion"):
                continue
            vus.add(x["id"])
            try:
                n = (date.fromisoformat(x["dateReunion"][:10]) - jour).days
            except ValueError:
                continue
            if 0 <= n <= 7:
                out.append(("convocation", "Convocation", f"{libelle_note(x)} — {R.jjmmaaaa(x['dateReunion'])} {x.get('heureReunion') or ''} "
                                                         f"{x.get('lieuReunion') or ''}".strip(), url_for("liaison_boite")))
        for f in (getattr(H, "sante_alertes", None), getattr(H, "sport_alertes", None), getattr(H, "territoire_alertes", None)):
            if callable(f):
                try:
                    out += f() or []
                except Exception:  # noqa: BLE001
                    pass
        return out
    H.liaison_alertes = alertes
    G.alertes = lambda: (len(alertes()), url_for("liaison_alertes"))

    @app.route("/liaison/alertes")
    @H.connexion_requise("notes_service")
    def liaison_alertes():
        return render_template("liaison_alertes.html", G=G, ep_actif="liaison_alertes", alertes=alertes())

    # ---- licences « Non examiné » / « Inapte » (sport scolaire)
    def sport_alertes():
        out = []
        try:
            p = R.cle_portee("structure")
            sql = "SELECT aptitude, COUNT(*) n FROM reg_sport_licences WHERE portee=? AND annee=? AND aptitude IN ('Non examiné','Inapte')"
            args = [p, R.annee_active()]
            if R.juridiction() and g.get("ecole"):
                niv, ent = R.entite_courante()
                sql += " AND lower(COALESCE(ecole,''))=lower(?)"
                args.append(ent)
            for x in q(sql + " GROUP BY aptitude", tuple(args)):
                out.append(("licence", "Licences", f"{x['n']} licence(s) « {x['aptitude']} »",
                            url_for("reg_page", gcle="sport", rcle="licences", f_aptitude=x["aptitude"])))
        except Exception:  # noqa: BLE001
            pass
        return out
    if not getattr(H, "sport_alertes", None):
        H.sport_alertes = sport_alertes
