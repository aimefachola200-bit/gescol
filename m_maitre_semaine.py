# -*- coding: utf-8 -*-
"""Maître de semaine : planning des maîtres de semaine, journal quotidien des activités de l'école,
rapport hebdomadaire PDF, historique et recherche (édition publique ; module chargé dans les deux éditions).

NB : ce journal est celui de la VIE DE L'ÉCOLE (tenu par le maître de semaine). Le « Journal d'activité »
technique de l'administration (table journal, /journal) n'est pas concerné.

* /maitre-semaine?semaine=AAAA-MM-JJ              maitre_semaine_accueil         semaine en cours (ou demandée)
* /maitre-semaine/planning             GET/POST   maitre_semaine_planning        planning annuel + rotation automatique
* /maitre-semaine/planning.pdf                    maitre_semaine_planning_pdf    planning imprimable
* /maitre-semaine/journal?date=        GET/POST   maitre_semaine_journal         fiche d'une journée
* /maitre-semaine/journal/<id>/viser       POST   maitre_semaine_viser           visa (ou retrait) du directeur
* /maitre-semaine/journal/<id>/supprimer   POST   maitre_semaine_supprimer       suppression (direction)
* /maitre-semaine/semaine?semaine=     GET/POST   maitre_semaine_semaine         vue hebdomadaire, observations, signature
* /maitre-semaine/semaine/viser            POST   maitre_semaine_viser_semaine   visa de tous les jours de la semaine
* /maitre-semaine/rapport.pdf?semaine=            maitre_semaine_rapport_pdf     rapport hebdomadaire
* /maitre-semaine/historique                      maitre_semaine_historique      historique des semaines + recherche

Droits : « maitre_semaine » (admin, directeur, secrétaire, enseignant). Le planning est modifié par la direction et
le secrétariat ; le visa, le retrait de visa et la suppression sont réservés à la direction. Un jour visé ne peut
plus être modifié que par la direction.
"""
import json
import re
from datetime import date, datetime, timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
ETATS = {"bon": "Bon", "passable": "Passable", "mauvais": "Mauvais"}
SALUT = {"fait": "Effectué", "non_fait": "Non effectué", "sans_objet": "Sans objet"}
ACTIVITES = {"sport": "Sport / EPS", "cooperative": "Coopérative scolaire", "assainissement": "Assainissement",
             "cantine": "Cantine", "jardin": "Jardin / champ scolaire", "sante": "Santé / hygiène",
             "culture": "Activités culturelles", "reunion": "Réunion / conseil des maîtres", "autre": "Autre"}
TEXTES = ("discipline", "retards_ens", "absences_ens", "eleves_details", "visites", "incidents",
          "activites_details", "observations")
ROLES_PLANNING = ("admin", "fondateur", "directeur", "secretaire")
ROLES_VISA = ("admin", "fondateur", "directeur")
RE_HEURE = re.compile(r"^([01]?\d|2[0-3])[:hH]([0-5]\d)$")
MAX_TEXTE = 2000

SCHEMA = """
CREATE TABLE IF NOT EXISTS ms_planning (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL,
    annee TEXT,
    lundi TEXT NOT NULL,                 -- lundi de la semaine (AAAA-MM-JJ)
    personnel_id INTEGER,                -- maître de semaine (table personnel)
    maitre_nom TEXT,                     -- nom au moment de la désignation (ou saisi librement)
    observations TEXT,                   -- observations générales de la semaine (rapport)
    signature_maitre TEXT,               -- signature digitale du maître de semaine (data URL PNG)
    cree_le TEXT, maj TEXT,
    UNIQUE (ecole_id, lundi)
);
CREATE TABLE IF NOT EXISTS ms_journal (
    id INTEGER PRIMARY KEY,
    ecole_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    lundi TEXT NOT NULL,
    personnel_id INTEGER, maitre_nom TEXT,
    heure_arrivee TEXT, heure_couleurs TEXT, salut_couleurs TEXT,
    proprete_cour TEXT, proprete_classes TEXT, discipline_etat TEXT, discipline TEXT,
    retards_ens TEXT, absences_ens TEXT,
    eleves_abs_g INTEGER, eleves_abs_f INTEGER, eleves_ret_g INTEGER, eleves_ret_f INTEGER, eleves_details TEXT,
    visites TEXT, incidents TEXT, activites TEXT, activites_details TEXT, observations TEXT,
    visa_le TEXT, visa_par INTEGER, visa_nom TEXT,
    saisi_par INTEGER, cree_le TEXT, maj TEXT,
    UNIQUE (ecole_id, date)
);
CREATE INDEX IF NOT EXISTS ix_ms_journal_lundi ON ms_journal(ecole_id, lundi);
"""


# ============================================================ outils purs
def lire_date(v):
    """« AAAA-MM-JJ » ou « JJ/MM/AAAA » -> date, sinon None."""
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def lundi_de(d):
    return d - timedelta(days=d.weekday())


def date_longue(d):
    return f"{JOURS[d.weekday()].lower()} {d.day} {MOIS[d.month - 1]} {d.year}"


def lire_heure(v):
    """« 7h30 », « 07:30 » -> « 07:30 » ; vide -> "" ; invalide -> None."""
    s = str(v or "").strip()
    if not s:
        return ""
    m = RE_HEURE.match(s)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def lire_entier(v, maxi=5000):
    """Entier positif (vide -> None) ; ValueError si invalide."""
    s = str(v or "").strip()
    if not s:
        return None
    if not s.isdigit() or int(s) > maxi:
        raise ValueError(s)
    return int(s)


def semaines_annee(annee):
    """Lundis des semaines de l'année scolaire (de la semaine du 1er septembre à celle du 31 juillet)."""
    a = int(annee[:4])
    l, fin = lundi_de(date(a, 9, 1)), date(a + 1, 7, 31)
    res = []
    while l <= fin:
        res.append(l)
        l += timedelta(days=7)
    return res


def annee_de(d):
    return f"{d.year}-{d.year + 1}" if d.month >= 9 else f"{d.year - 1}-{d.year}"


def rotation(lundis, personnes, deja, remplacer=False, fermees=()):
    """Rotation automatique : attribue les personnes (dans l'ordre, en boucle) aux semaines.
    deja : {lundi_iso: personnel_id} existants ; les semaines déjà attribuées sont conservées sauf si remplacer ;
    fermees : lundis sans classe (congés) sautés. La rotation reprend après le dernier maître déjà désigné.
    Retourne {lundi_iso: personnel_id} des semaines à (ré)attribuer."""
    if not personnes:
        return {}
    res, i = {}, 0
    for l in lundis:
        cle = l.isoformat()
        if cle in fermees:
            continue
        if cle in deja and deja[cle] and not remplacer:
            if deja[cle] in personnes:  # on continue la rotation après ce maître
                i = personnes.index(deja[cle]) + 1
            continue
        res[cle] = personnes[i % len(personnes)]
        i += 1
    return res


def nom_complet(p):
    return f"{(p['nom'] or '').upper()} {p['prenoms'] or ''}".strip() if p else ""


def resume_ligne(j):
    """Texte court d'une journée pour la recherche / l'historique."""
    for k in ("incidents", "observations", "visites", "discipline", "activites_details"):
        if j[k]:
            return j[k][:140]
    return ""


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    def est_direction():
        return g.user["role"] in ROLES_VISA

    def peut_planning():
        return g.user["role"] in ROLES_PLANNING

    def personnel():
        """Personnel actif de l'école courante (enseignants et direction d'abord)."""
        try:
            rows = q("SELECT * FROM personnel WHERE actif=1 AND ecole_id=? ORDER BY nom, prenoms", (H.eco(),))
        except Exception:  # noqa: BLE001 — base ancienne sans ecole_id
            rows = q("SELECT * FROM personnel WHERE actif=1 ORDER BY nom, prenoms")
        cle = lambda p: (0 if re.search(r"nseign|irect|a[iî]tre|nstitut", p["fonction"] or "", re.I) else 1)  # noqa: E731
        return sorted(rows, key=cle)

    def enseignants_ids():
        return [p["id"] for p in personnel() if re.search(r"nseign|irect|a[iî]tre|nstitut", p["fonction"] or "", re.I)]

    def personne(pid):
        if not pid:
            return None
        return q("SELECT * FROM personnel WHERE id=?", (pid,), un=True)

    def planning_de(lun):
        return q("SELECT * FROM ms_planning WHERE ecole_id=? AND lundi=?", (H.eco(), lun.isoformat()), un=True)

    def journaux_semaine(lun):
        return {r["date"]: r for r in q("SELECT * FROM ms_journal WHERE ecole_id=? AND lundi=? ORDER BY date",
                                         (H.eco(), lun.isoformat()))}

    def jours_fermes(du, au):
        """Jours sans classe du calendrier scolaire : {iso: motif}."""
        try:
            return {r["date"]: r["motif"] or "Pas de classe" for r in q(
                "SELECT date, motif FROM jours_classe WHERE ecole_id=? AND demi_journees=0 AND date BETWEEN ? AND ?",
                (H.eco(), du.isoformat(), au.isoformat()))}
        except Exception:  # noqa: BLE001
            return {}

    def semaine_demandee():
        return lundi_de(lire_date(request.values.get("semaine")) or date.today())

    def suggestions(d):
        """Données déjà connues dans GESCOL pour un jour : absences/retards d'élèves (registre d'appel) et visites."""
        iso = d.isoformat()
        s = {"abs_g": 0, "abs_f": 0, "ret_g": 0, "ret_f": 0, "visites": ""}
        abs_ids = {}
        for r in q("""SELECT DISTINCT e.id, e.sexe FROM registre r JOIN eleves e ON e.id=r.eleve_id
                      JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=? AND r.date=?""", (H.eco(), iso)):
            abs_ids[r["id"]] = r["sexe"]
        for r in q("""SELECT DISTINCT e.id, e.sexe, p.statut FROM presences p JOIN eleves e ON e.id=p.eleve_id
                      JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=? AND p.date=?""", (H.eco(), iso)):
            if r["statut"] == "absent":
                abs_ids[r["id"]] = r["sexe"]
            elif r["statut"] == "retard":
                s["ret_f" if r["sexe"] == "F" else "ret_g"] += 1
        for sexe in abs_ids.values():
            s["abs_f" if sexe == "F" else "abs_g"] += 1
        try:  # visites de classe / d'école enregistrées ce jour (module Visites)
            vs = q("""SELECT v.*, c.nom classe_nom FROM visites v LEFT JOIN classes c ON c.id=v.classe_id
                      WHERE v.ecole_id=? AND v.date=? ORDER BY v.heure_debut""", (H.eco(), iso))
            s["visites"] = "\n".join(
                f"{'Visite de classe' if v['type'] == 'classe' else 'Visite d’école'} — {v['visiteur_qualite']} "
                f"{v['visiteur_nom'] or ''}{(' (' + v['classe_nom'] + ')') if v['classe_nom'] else ''}".strip()
                for v in vs)
        except Exception:  # noqa: BLE001 — module Visites absent
            pass
        return s

    def libelle_activites(j):
        try:
            codes = json.loads(j["activites"] or "[]")
        except ValueError:
            codes = []
        return [ACTIVITES[c] for c in codes if c in ACTIVITES]

    # -------------------------------------------------------------- accueil (semaine)
    @app.route("/maitre-semaine")
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_accueil():
        lun = semaine_demandee()
        pl = planning_de(lun)
        jx = journaux_semaine(lun)
        fermes = jours_fermes(lun, lun + timedelta(days=5))
        jours = []
        for i in range(6):
            d = lun + timedelta(days=i)
            j = jx.get(d.isoformat())
            if i == 5 and not j:
                continue  # samedi affiché seulement s'il a été renseigné
            jours.append({"d": d, "lib": JOURS[i], "j": j, "ferme": fermes.get(d.isoformat())})
        prochaines = q("""SELECT * FROM ms_planning WHERE ecole_id=? AND lundi>? ORDER BY lundi LIMIT 4""",
                       (H.eco(), lun.isoformat()))
        stats = {"saisis": len(jx), "vises": sum(1 for j in jx.values() if j["visa_le"]),
                 "incidents": sum(1 for j in jx.values() if (j["incidents"] or "").strip()),
                 "abs": sum((j["eleves_abs_g"] or 0) + (j["eleves_abs_f"] or 0) for j in jx.values())}
        return render_template("maitre_semaine_accueil.html", lun=lun, ven=lun + timedelta(days=4), pl=pl,
                               maitre=personne(pl["personnel_id"]) if pl else None, jours=jours, stats=stats,
                               prec=(lun - timedelta(days=7)).isoformat(), suiv=(lun + timedelta(days=7)).isoformat(),
                               prochaines=prochaines, aujourdhui=date.today(), direction=est_direction(),
                               peut_planning=peut_planning(), date_longue=date_longue, ETATS=ETATS)

    # -------------------------------------------------------------- planning
    @app.route("/maitre-semaine/planning", methods=["GET", "POST"])
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_planning():
        annee = request.values.get("annee") or H.config.ANNEE_ACTIVE
        if not re.match(r"^\d{4}-\d{4}$", annee):
            annee = H.config.ANNEE_ACTIVE
        lundis = semaines_annee(annee)
        pers = {p["id"]: p for p in personnel()}
        existants = {r["lundi"]: r for r in q("SELECT * FROM ms_planning WHERE ecole_id=? AND annee=?", (H.eco(), annee))}
        if request.method == "POST":
            if not peut_planning():
                abort(403)
            action = request.form.get("action", "enregistrer")
            maintenant = H.maintenant()
            if action == "rotation":
                choisis = [int(x) for x in request.form.getlist("rot") if x.isdigit() and int(x) in pers]
                du = lire_date(request.form.get("du")) or lundis[0]
                au = lire_date(request.form.get("au")) or lundis[-1]
                if not choisis:
                    flash("Rotation : cochez au moins un enseignant.", "danger")
                    return redirect(url_for("maitre_semaine_planning", annee=annee))
                if au < du:
                    flash("Rotation : la date de fin précède la date de début.", "danger")
                    return redirect(url_for("maitre_semaine_planning", annee=annee))
                cibles = [l for l in lundis if lundi_de(du) <= l <= au]
                # semaines entièrement fermées (congés saisis dans le calendrier scolaire) : sautées
                fermes = jours_fermes(lundis[0], lundis[-1] + timedelta(days=4))
                fermees = {l.isoformat() for l in cibles
                           if all((l + timedelta(days=i)).isoformat() in fermes for i in range(5))}
                deja = {k: r["personnel_id"] for k, r in existants.items()}
                attrib = rotation(cibles, choisis, deja, bool(request.form.get("remplacer")), fermees)
                for cle, pid in attrib.items():
                    ex("""INSERT INTO ms_planning (ecole_id, annee, lundi, personnel_id, maitre_nom, cree_le, maj)
                          VALUES (?,?,?,?,?,?,?) ON CONFLICT(ecole_id, lundi) DO UPDATE SET
                          personnel_id=excluded.personnel_id, maitre_nom=excluded.maitre_nom, maj=excluded.maj""",
                       (H.eco(), annee, cle, pid, nom_complet(pers[pid]), maintenant, maintenant))
                H.journal("maitre_semaine_rotation", f"{annee} : {len(attrib)} semaine(s)")
                msg = f"Rotation proposée : {len(attrib)} semaine(s) attribuée(s)"
                if fermees:
                    msg += f", {len(fermees)} semaine(s) de congé sautée(s)"
                flash(msg + ". Vous pouvez modifier chaque semaine ci-dessous.", "success")
                return redirect(url_for("maitre_semaine_planning", annee=annee))
            # enregistrement du tableau (une liste par semaine)
            nb = 0
            for l in lundis:
                cle = l.isoformat()
                if f"p_{cle}" not in request.form:
                    continue
                v = request.form.get(f"p_{cle}", "")
                pid = int(v) if v.isdigit() and int(v) in pers else None
                ancien = existants.get(cle)
                if (ancien["personnel_id"] if ancien else None) == pid:
                    continue
                if pid is None:
                    if ancien:
                        ex("UPDATE ms_planning SET personnel_id=NULL, maitre_nom=NULL, maj=? WHERE id=?",
                           (maintenant, ancien["id"]))
                        nb += 1
                    continue
                ex("""INSERT INTO ms_planning (ecole_id, annee, lundi, personnel_id, maitre_nom, cree_le, maj)
                      VALUES (?,?,?,?,?,?,?) ON CONFLICT(ecole_id, lundi) DO UPDATE SET
                      personnel_id=excluded.personnel_id, maitre_nom=excluded.maitre_nom, maj=excluded.maj""",
                   (H.eco(), annee, cle, pid, nom_complet(pers[pid]), maintenant, maintenant))
                nb += 1
            H.journal("maitre_semaine_planning", f"{annee} : {nb} modification(s)")
            flash(f"Planning enregistré ({nb} semaine(s) modifiée(s)).", "success")
            return redirect(url_for("maitre_semaine_planning", annee=annee))
        fermes = jours_fermes(lundis[0], lundis[-1] + timedelta(days=4))
        lignes = []
        for l in lundis:
            r = existants.get(l.isoformat())
            ferme = all((l + timedelta(days=i)).isoformat() in fermes for i in range(5))
            lignes.append({"l": l, "v": l + timedelta(days=4), "r": r, "ferme": ferme,
                           "motif": fermes.get(l.isoformat()) if ferme else "",
                           "courante": l == lundi_de(date.today())})
        a = int(annee[:4])
        return render_template("maitre_semaine_planning.html", annee=annee, lignes=lignes, pers=list(pers.values()),
                               defaut_rot=set(enseignants_ids()), modifiable=peut_planning(), nom_complet=nom_complet,
                               annees=[f"{y}-{y + 1}" for y in (a - 1, a, a + 1)],
                               nb_attribuees=sum(1 for x in lignes if x["r"] and x["r"]["personnel_id"]))

    @app.route("/maitre-semaine/planning.pdf")
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_planning_pdf():
        annee = request.args.get("annee") or H.config.ANNEE_ACTIVE
        if not re.match(r"^\d{4}-\d{4}$", annee):
            annee = H.config.ANNEE_ACTIVE
        existants = {r["lundi"]: r for r in q("SELECT * FROM ms_planning WHERE ecole_id=? AND annee=?", (H.eco(), annee))}
        lignes, n = [], 0
        for l in semaines_annee(annee):
            r = existants.get(l.isoformat())
            if not r or not r["personnel_id"]:
                continue
            n += 1
            p = personne(r["personnel_id"])
            lignes.append([n, f"du {l.strftime('%d/%m/%Y')} au {(l + timedelta(days=4)).strftime('%d/%m/%Y')}",
                           r["maitre_nom"] or nom_complet(p), (p["fonction"] if p else "") or "", ""])
        if not lignes:
            lignes = [["", "Aucune semaine attribuée pour cette année scolaire.", "", "", ""]]
        v = H.identification()
        pdf = H.pdfs.document_tableau(
            "PLANNING DES MAÎTRES DE SEMAINE", ["N°", "Semaine", "Maître de semaine", "Fonction", "Émargement"], lignes,
            sous_titre=f"Année scolaire {annee}",
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[7, 38, 50, 30, 25], taille=8.5, signatures=[signature_directeur(v, True)],
            notes_bas=["Le maître de semaine veille à la montée des couleurs, à la propreté, à la discipline et tient "
                       "le journal quotidien de l'école."])
        H.journal("maitre_semaine_planning_pdf", annee)
        return H.pdf_reponse(pdf, f"planning_maitres_semaine_{annee}.pdf")

    def signature_directeur(v, avec_image):
        titre = v.get("directeur_titre") or "Directeur"
        titre = f"{'LA' if titre.lower().startswith('directrice') else 'LE'} {titre.upper()}"
        img = H.pdfs.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")) if avec_image else None
        return (titre, v.get("directeur_nom") or "", img, True)

    # -------------------------------------------------------------- journal quotidien
    @app.route("/maitre-semaine/journal", methods=["GET", "POST"])
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_journal():
        d = lire_date(request.values.get("date")) or date.today()
        lun = lundi_de(d)
        j = q("SELECT * FROM ms_journal WHERE ecole_id=? AND date=?", (H.eco(), d.isoformat()), un=True)
        pl = planning_de(lun)
        pers = {p["id"]: p for p in personnel()}
        if request.method == "POST":
            if not lire_date(request.form.get("date")):
                flash("Date invalide : rien n'a été enregistré.", "danger")
                return redirect(url_for("maitre_semaine_journal"))
            if d.weekday() == 6:
                flash("Le dimanche n'est pas un jour de classe : choisissez une autre date.", "danger")
                return redirect(url_for("maitre_semaine_journal", date=d.isoformat()))
            if d > date.today() + timedelta(days=1):
                flash("On ne peut pas renseigner le journal d'un jour futur.", "danger")
                return redirect(url_for("maitre_semaine_journal", date=d.isoformat()))
            if j and j["visa_le"] and not est_direction():
                flash("Cette journée a été visée par la direction : elle ne peut plus être modifiée.", "warning")
                return redirect(url_for("maitre_semaine_journal", date=d.isoformat()))
            f = request.form
            erreurs = []
            heures = {}
            for k, lib in (("heure_arrivee", "heure d'arrivée"), ("heure_couleurs", "heure de montée des couleurs")):
                h = lire_heure(f.get(k))
                if h is None:
                    erreurs.append(f"{lib.capitalize()} invalide (format 07:30).")
                heures[k] = h or ""
            nombres = {}
            for k in ("eleves_abs_g", "eleves_abs_f", "eleves_ret_g", "eleves_ret_f"):
                try:
                    nombres[k] = lire_entier(f.get(k))
                except ValueError:
                    erreurs.append("Les nombres d'élèves absents / en retard doivent être des entiers positifs.")
                    break
            if erreurs:
                for e in dict.fromkeys(erreurs):
                    flash(e, "danger")
                return render_template("maitre_semaine_journal.html", **contexte_journal(d, lun, j, pl, pers, f))
            v = {k: (f.get(k) or "").strip()[:MAX_TEXTE] for k in TEXTES}
            choix = {k: (f.get(k) if f.get(k) in ETATS else None) for k in ("proprete_cour", "proprete_classes", "discipline_etat")}
            salut = f.get("salut_couleurs") if f.get("salut_couleurs") in SALUT else None
            acts = json.dumps([a for a in f.getlist("activites") if a in ACTIVITES])
            pid = f.get("personnel_id", "")
            pid = int(pid) if pid.isdigit() and int(pid) in pers else (pl["personnel_id"] if pl else None)
            nom = nom_complet(pers.get(pid)) if pid in pers else ((pl["maitre_nom"] if pl else "") or "")
            valeurs = (pid, nom, heures["heure_arrivee"], heures["heure_couleurs"], salut, choix["proprete_cour"],
                       choix["proprete_classes"], choix["discipline_etat"], v["discipline"], v["retards_ens"],
                       v["absences_ens"], nombres["eleves_abs_g"], nombres["eleves_abs_f"], nombres["eleves_ret_g"],
                       nombres["eleves_ret_f"], v["eleves_details"], v["visites"], v["incidents"], acts,
                       v["activites_details"], v["observations"], g.user["id"], H.maintenant())
            if j:
                ex("""UPDATE ms_journal SET personnel_id=?, maitre_nom=?, heure_arrivee=?, heure_couleurs=?, salut_couleurs=?,
                      proprete_cour=?, proprete_classes=?, discipline_etat=?, discipline=?, retards_ens=?, absences_ens=?,
                      eleves_abs_g=?, eleves_abs_f=?, eleves_ret_g=?, eleves_ret_f=?, eleves_details=?, visites=?,
                      incidents=?, activites=?, activites_details=?, observations=?, saisi_par=?, maj=? WHERE id=?""",
                   valeurs + (j["id"],))
            else:
                ex("""INSERT INTO ms_journal (personnel_id, maitre_nom, heure_arrivee, heure_couleurs, salut_couleurs,
                      proprete_cour, proprete_classes, discipline_etat, discipline, retards_ens, absences_ens,
                      eleves_abs_g, eleves_abs_f, eleves_ret_g, eleves_ret_f, eleves_details, visites, incidents,
                      activites, activites_details, observations, saisi_par, maj, ecole_id, date, lundi, cree_le)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   valeurs + (H.eco(), d.isoformat(), lun.isoformat(), H.maintenant()))
            H.journal("maitre_semaine_journal", d.isoformat())
            flash(f"Journal du {date_longue(d)} enregistré.", "success")
            return redirect(url_for("maitre_semaine_journal", date=d.isoformat()))
        return render_template("maitre_semaine_journal.html", **contexte_journal(d, lun, j, pl, pers, None))

    def contexte_journal(d, lun, j, pl, pers, form):
        """Valeurs du formulaire : saisie en cours (form), sinon journal enregistré, sinon suggestions GESCOL."""
        sug = suggestions(d)
        if form is not None:
            v = {k: form.get(k, "") for k in form}
            v["activites"] = form.getlist("activites")
        elif j:
            v = dict(j)
            try:
                v["activites"] = json.loads(j["activites"] or "[]")
            except ValueError:
                v["activites"] = []
        else:
            v = {"personnel_id": pl["personnel_id"] if pl else "", "eleves_abs_g": sug["abs_g"] or "",
                 "eleves_abs_f": sug["abs_f"] or "", "eleves_ret_g": sug["ret_g"] or "",
                 "eleves_ret_f": sug["ret_f"] or "", "visites": sug["visites"], "activites": [],
                 "salut_couleurs": "fait"}
        visa_user = q("SELECT nom FROM utilisateurs WHERE id=?", (j["visa_par"],), un=True) if j and j["visa_par"] else None
        verrou = bool(j and j["visa_le"] and not est_direction())
        return dict(d=d, lun=lun, j=j, pl=pl, pers=list(pers.values()), v=v, sug=sug, ETATS=ETATS, SALUT=SALUT,
                    ACTIVITES=ACTIVITES, date_longue=date_longue, direction=est_direction(), verrou=verrou,
                    visa_user=visa_user, nom_complet=nom_complet, prec=(d - timedelta(days=1 if d.weekday() else 3)).isoformat(),
                    suiv=(d + timedelta(days=3 if d.weekday() == 4 else 1)).isoformat(),
                    ferme=jours_fermes(d, d).get(d.isoformat()), futur=d > date.today())

    @app.route("/maitre-semaine/journal/<int:jid>/viser", methods=["POST"])
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_viser(jid):
        if not est_direction():
            abort(403)
        j = q("SELECT * FROM ms_journal WHERE id=? AND ecole_id=?", (jid, H.eco()), un=True)
        if not j:
            abort(404)
        if request.form.get("action") == "annuler":
            ex("UPDATE ms_journal SET visa_le=NULL, visa_par=NULL, visa_nom=NULL WHERE id=?", (jid,))
            flash("Visa retiré : la journée peut de nouveau être modifiée.", "warning")
        else:
            ex("UPDATE ms_journal SET visa_le=?, visa_par=?, visa_nom=? WHERE id=?",
               (H.maintenant(), g.user["id"], g.user["nom"], jid))
            flash("Journée visée par la direction.", "success")
        H.journal("maitre_semaine_visa", f"{j['date']} {request.form.get('action') or 'viser'}")
        retour = request.form.get("retour")
        if retour == "semaine":
            return redirect(url_for("maitre_semaine_semaine", semaine=j["lundi"]))
        return redirect(url_for("maitre_semaine_journal", date=j["date"]))

    @app.route("/maitre-semaine/journal/<int:jid>/supprimer", methods=["POST"])
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_supprimer(jid):
        if not est_direction():
            abort(403)
        j = q("SELECT * FROM ms_journal WHERE id=? AND ecole_id=?", (jid, H.eco()), un=True)
        if not j:
            abort(404)
        ex("DELETE FROM ms_journal WHERE id=?", (jid,))
        H.journal("maitre_semaine_suppression", j["date"])
        flash(f"Journal du {date_longue(lire_date(j['date']))} supprimé.", "warning")
        return redirect(url_for("maitre_semaine_semaine", semaine=j["lundi"]))

    # -------------------------------------------------------------- semaine (vue + observations + signature)
    def donnees_semaine(lun):
        jx = journaux_semaine(lun)
        fermes = jours_fermes(lun, lun + timedelta(days=5))
        jours = []
        for i in range(6):
            d = lun + timedelta(days=i)
            j = jx.get(d.isoformat())
            if i == 5 and not j:
                continue
            jours.append({"d": d, "lib": JOURS[i], "j": j, "ferme": fermes.get(d.isoformat()),
                          "acts": libelle_activites(j) if j else []})
        tot = {k: sum((j[k] or 0) for j in jx.values()) for k in ("eleves_abs_g", "eleves_abs_f", "eleves_ret_g", "eleves_ret_f")}
        return {"jours": jours, "jx": jx, "tot": tot, "tous_vises": bool(jx) and all(j["visa_le"] for j in jx.values())}

    @app.route("/maitre-semaine/semaine", methods=["GET", "POST"])
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_semaine():
        lun = semaine_demandee()
        pl = planning_de(lun)
        if request.method == "POST":
            if not lire_date(request.form.get("semaine")):
                flash("Semaine invalide.", "danger")
                return redirect(url_for("maitre_semaine_semaine"))
            obs = (request.form.get("observations") or "").strip()[:MAX_TEXTE]
            sig = request.form.get("signature_maitre") or ""
            if sig and (not sig.startswith("data:image/png;base64,") or len(sig) > 400_000):
                sig = pl["signature_maitre"] if pl else ""
            if not sig and pl and pl["personnel_id"] and g.user["role"] == "enseignant":
                # signature digitale personnelle de l'enseignant connecté quand il est le maître de semaine désigné
                try:
                    moi = q("SELECT 1 FROM personnel WHERE id=? AND user_id=?", (pl["personnel_id"], g.user["id"]), un=True)
                except Exception:  # noqa: BLE001 — colonne user_id absente sans le module carrière
                    moi = None
                if moi:
                    sig = H.signature_enseignant(g.user["id"]) or ""
            if pl:
                ex("UPDATE ms_planning SET observations=?, signature_maitre=?, maj=? WHERE id=?",
                   (obs, sig or None, H.maintenant(), pl["id"]))
            else:
                ex("""INSERT INTO ms_planning (ecole_id, annee, lundi, observations, signature_maitre, cree_le, maj)
                      VALUES (?,?,?,?,?,?,?)""", (H.eco(), annee_de(lun), lun.isoformat(), obs, sig or None,
                                                  H.maintenant(), H.maintenant()))
            H.journal("maitre_semaine_semaine", lun.isoformat())
            flash("Observations et signature de la semaine enregistrées.", "success")
            return redirect(url_for("maitre_semaine_semaine", semaine=lun.isoformat()))
        dsem = donnees_semaine(lun)
        return render_template("maitre_semaine_semaine.html", lun=lun, ven=lun + timedelta(days=4), pl=pl,
                               maitre=personne(pl["personnel_id"]) if pl else None, s=dsem, ETATS=ETATS, SALUT=SALUT,
                               prec=(lun - timedelta(days=7)).isoformat(), suiv=(lun + timedelta(days=7)).isoformat(),
                               direction=est_direction(), date_longue=date_longue, nom_complet=nom_complet)

    @app.route("/maitre-semaine/semaine/viser", methods=["POST"])
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_viser_semaine():
        if not est_direction():
            abort(403)
        lun = semaine_demandee()
        n = H.get_db().execute(
            "UPDATE ms_journal SET visa_le=?, visa_par=?, visa_nom=? WHERE ecole_id=? AND lundi=? AND visa_le IS NULL",
            (H.maintenant(), g.user["id"], g.user["nom"], H.eco(), lun.isoformat())).rowcount
        H.get_db().commit()
        H.journal("maitre_semaine_visa_semaine", f"{lun} : {n} jour(s)")
        flash(f"{n} journée(s) visée(s)." if n else "Aucune journée à viser dans cette semaine.", "success" if n else "info")
        return redirect(url_for("maitre_semaine_semaine", semaine=lun.isoformat()))

    # -------------------------------------------------------------- rapport hebdomadaire PDF
    @app.route("/maitre-semaine/rapport.pdf")
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_rapport_pdf():
        lun = semaine_demandee()
        pl = planning_de(lun)
        maitre = personne(pl["personnel_id"]) if pl else None
        s = donnees_semaine(lun)
        v = H.identification()
        P = H.pdfs

        def cpl(*parts):
            return "\n".join(p for p in parts if p)

        lignes = []
        for x in s["jours"]:
            j, d = x["j"], x["d"]
            lib = f"{x['lib']}\n{d.strftime('%d/%m/%Y')}"
            if not j:
                lignes.append([lib, x["ferme"] or "Non renseigné", "", "", "", "", "", "", "", "", "", ""])
                continue
            lignes.append([
                lib,
                cpl(f"Arrivée : {j['heure_arrivee']}" if j["heure_arrivee"] else "",
                    f"Couleurs : {j['heure_couleurs']}" if j["heure_couleurs"] else ""),
                SALUT.get(j["salut_couleurs"], ""),
                cpl(f"Cour : {ETATS.get(j['proprete_cour'], '—')}", f"Classes : {ETATS.get(j['proprete_classes'], '—')}"),
                cpl(ETATS.get(j["discipline_etat"], ""), j["discipline"]),
                cpl(f"Retards : {j['retards_ens']}" if j["retards_ens"] else "",
                    f"Absences : {j['absences_ens']}" if j["absences_ens"] else ""),
                cpl(f"Abs. {j['eleves_abs_g'] or 0} G / {j['eleves_abs_f'] or 0} F",
                    f"Ret. {j['eleves_ret_g'] or 0} G / {j['eleves_ret_f'] or 0} F", j["eleves_details"]),
                j["visites"] or "", j["incidents"] or "",
                cpl(", ".join(x["acts"]), j["activites_details"]),
                j["observations"] or "",
                f"Visé le {j['visa_le'][8:10]}/{j['visa_le'][5:7]}" if j["visa_le"] else "",
            ])
        t = s["tot"]
        total = ["Semaine", "", "", "", "", "",
                 f"Abs. {t['eleves_abs_g']} G / {t['eleves_abs_f']} F\nRet. {t['eleves_ret_g']} G / {t['eleves_ret_f']} F",
                 "", "", "", "", f"{sum(1 for j in s['jx'].values() if j['visa_le'])}/{len(s['jx'])} visé(s)"]
        nom_maitre = (pl["maitre_nom"] if pl else "") or nom_complet(maitre)
        apres = []
        if pl and (pl["observations"] or "").strip():
            obs = (pl["observations"] or "").replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")
            apres += [P.paragraphe("OBSERVATIONS GÉNÉRALES DE LA SEMAINE", 9, True), P.paragraphe(obs, 8.5)]
        # signature saisie pour la semaine, sinon signature digitale du compte enseignant du maître de semaine désigné
        sig_maitre = P.image_data_url((pl["signature_maitre"] or H.signature_agent(pl["personnel_id"])) if pl else None)
        pdf = P.document_tableau(
            "RAPPORT HEBDOMADAIRE DU MAÎTRE DE SEMAINE",
            ["Jour", "Arrivée / couleurs", "Salut aux couleurs", "Propreté", "Discipline",
             "Enseignants : retards / absences", "Élèves absents / retards", "Visites reçues", "Incidents",
             "Activités", "Observations", "Visa"], lignes, total=total,
            sous_titre=f"Semaine du {lun.strftime('%d/%m/%Y')} au {(lun + timedelta(days=4)).strftime('%d/%m/%Y')}",
            infos=[("Maître de semaine", nom_maitre or "—"), ("Fonction", (maitre["fonction"] if maitre else "") or "—"),
                   ("Année scolaire", annee_de(lun)), ("Jours renseignés", len(s["jx"]))],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[13, 14, 12, 14, 18, 20, 17, 18, 18, 18, 22, 10], paysage=True, taille=7, apres=apres,
            signatures=[("LE MAÎTRE DE SEMAINE", nom_maitre, sig_maitre, False),
                        signature_directeur(v, s["tous_vises"])],
            notes_bas=["G = garçons, F = filles. Propreté et discipline : Bon / Passable / Mauvais. "
                       "La signature du directeur est apposée lorsque toutes les journées sont visées."])
        H.journal("maitre_semaine_rapport_pdf", lun.isoformat())
        return H.pdf_reponse(pdf, f"rapport_maitre_semaine_{lun.isoformat()}.pdf")

    # -------------------------------------------------------------- historique et recherche
    @app.route("/maitre-semaine/historique")
    @H.connexion_requise("maitre_semaine")
    def maitre_semaine_historique():
        a = request.args
        du, au = lire_date(a.get("du")), lire_date(a.get("au"))
        pid = a.get("maitre", type=int)
        texte = (a.get("q") or "").strip()[:80]
        cond, params = ["ecole_id=?"], [H.eco()]
        if du:
            cond.append("lundi>=?")
            params.append(lundi_de(du).isoformat())
        if au:
            cond.append("lundi<=?")
            params.append(au.isoformat())
        w = " AND ".join(cond)
        # semaines = planning ∪ semaines ayant un journal
        pls = {r["lundi"]: r for r in q(f"SELECT * FROM ms_planning WHERE {w}", params)}
        stats = {r["lundi"]: r for r in q(
            f"""SELECT lundi, COUNT(*) n, SUM(visa_le IS NOT NULL) vises,
                       SUM(COALESCE(TRIM(incidents),'')<>'') incidents,
                       SUM(COALESCE(eleves_abs_g,0)+COALESCE(eleves_abs_f,0)) abs,
                       MAX(personnel_id) pid, MAX(maitre_nom) nom
                FROM ms_journal WHERE {w} GROUP BY lundi""", params)}
        semaines = []
        for l in sorted(set(pls) | set(stats), reverse=True):
            pr, st = pls.get(l), stats.get(l)
            p_id = (pr["personnel_id"] if pr else None) or (st["pid"] if st else None)
            if pid and p_id != pid:
                continue
            if not st and l > date.today().isoformat():
                continue  # semaines futures sans journal : visibles dans le planning
            semaines.append({"lundi": lire_date(l), "nom": (pr["maitre_nom"] if pr else None) or (st["nom"] if st else ""),
                             "n": st["n"] if st else 0, "vises": st["vises"] if st else 0,
                             "incidents": st["incidents"] if st else 0, "abs": st["abs"] if st else 0,
                             "obs": bool(pr and pr["observations"])})
        resultats = []
        if texte:
            motif = f"%{texte}%"
            champs = ("discipline", "retards_ens", "absences_ens", "eleves_details", "visites", "incidents",
                      "activites_details", "observations", "maitre_nom")
            clause = " OR ".join(f"{c} LIKE ?" for c in champs)
            sql = f"SELECT * FROM ms_journal WHERE {w} AND ({clause})"
            params2 = params + [motif] * len(champs)
            if pid:
                sql += " AND personnel_id=?"
                params2.append(pid)
            for j in q(sql + " ORDER BY date DESC LIMIT 200", params2):
                extrait = ""
                for c in champs:
                    val = j[c] or ""
                    k = val.lower().find(texte.lower())
                    if k >= 0:
                        extrait = ("…" if k > 40 else "") + val[max(0, k - 40):k + 100]
                        break
                resultats.append({"j": j, "d": lire_date(j["date"]), "extrait": extrait})
        return render_template("maitre_semaine_historique.html", semaines=semaines, resultats=resultats,
                               pers=personnel(), f={"du": a.get("du", ""), "au": a.get("au", ""), "maitre": pid,
                                                    "q": texte}, date_longue=date_longue, nom_complet=nom_complet)
