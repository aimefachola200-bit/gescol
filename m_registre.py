# -*- coding: utf-8 -*-
"""Registre de présence par demi-journée, calendrier scolaire (jours de classe) et relevés mensuels
(« Tableau de relevés mensuels pour l'année scolaire », conforme au modèle officiel).

Règles :
* 2 demi-journées de classe du lundi au vendredi, sauf le mercredi (matin seulement : 1) ; 0 le samedi et le dimanche ;
* avant la date de rentrée et après la fin des cours : 0 ;
* exceptions par école dans la table jours_classe (congés, jours fériés, vacances, journée pédagogique = 0 ;
  rattrapage un samedi = 1 ou 2). Une exception l'emporte toujours sur la règle générale ;
* table registre : une ligne = une ABSENCE d'un élève sur une demi-journée (1 = matin, 2 = après-midi).
"""
import json
import re
from datetime import date, datetime, timedelta

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for

JOURS_COURTS = ["Lu", "Ma", "Me", "Je", "Ve", "Sa", "Di"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
# mois de l'année scolaire (décalage d'année, mois) et libellés du modèle officiel
MOIS_SCOLAIRES = [(0, 9), (0, 10), (0, 11), (0, 12), (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6)]
LIB_MOIS_RELEVE = {9: "SEPT.", 10: "OCT.", 11: "NOV.", 12: "DÉC.", 1: "JAN.", 2: "FÉV.", 3: "MARS", 4: "AVRIL",
                   5: "MAI", 6: "JUIN"}
# jours fériés fixes du Bénin (mois, jour, libellé)
FERIES_FIXES = [(11, 1, "Toussaint"), (12, 25, "Noël"), (1, 1, "Nouvel an"),
                (1, 10, "Fête des religions endogènes"), (5, 1, "Fête du Travail"),
                (8, 1, "Fête de l'Indépendance"), (8, 15, "Assomption")]
# motifs proposés (les fêtes mobiles sont à marquer à la main chaque année)
MOTIFS = ["Jour férié", "Lundi de Pâques", "Ascension", "Lundi de Pentecôte", "Aïd el-Fitr (Ramadan)",
          "Aïd el-Kébir (Tabaski)", "Maouloud", "Vacances de Noël", "Vacances de Pâques", "Congés de détente",
          "Journée pédagogique", "Grève", "Rattrapage", "Fête de l'école"]
# colonnes du relevé : code, intitulé exact du modèle, saisissable ?
COLONNES_RELEVE = [
    ("dj", "NOMBRE des demi-jours de classe du mois", True),
    ("eff", "TOTAL des élèves qui ont fréquenté la classe pendant le mois", True),
    ("poss", "TOTAL des présences possibles par demi-jours de classe", False),
    ("abs", "TOTAL des absences du mois", True),
    ("effe", "TOTAL des présences effectives", False),
    ("pct", "POURCENTAGE des présences effectives dans le mois", False),
    ("n4", "NOMBRE d'élèves n'ayant jamais manqué la classe ou n'ayant pas manqué plus de 4 fois", True),
    ("n5", "NOMBRE d'élèves ayant manqué plus de 4 fois", True),
    ("imp", "TOTAL des absences imputables aux élèves de la colonne précédente", True),
]
SAISIES = [c for c, _, s in COLONNES_RELEVE if s]
RE_ANNEE = re.compile(r"^(\d{4})-(\d{4})$")
ROLES_CALENDRIER = ("admin", "fondateur", "directeur", "secretaire")


# ============================================================ outils de dates
def annee_valide(a, defaut):
    m = RE_ANNEE.match(a or "")
    return a if m and int(m.group(2)) == int(m.group(1)) + 1 else defaut


def annee_de(d):
    """Année scolaire contenant la date (septembre → août)."""
    y = d.year if d.month >= 9 else d.year - 1
    return f"{y}-{y + 1}"


def mois_scolaires(annee):
    a = int(annee[:4])
    return [(a + dec, m) for dec, m in MOIS_SCOLAIRES]


def fin_mois(y, m):
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def jours_entre(d1, d2):
    d = d1
    while d <= d2:
        yield d
        d += timedelta(days=1)


def lire_date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def lire_mois(s, defaut):
    try:
        d = datetime.strptime(s or "", "%Y-%m").date()
        return d.year, d.month
    except ValueError:
        return defaut


def demi_defaut(d):
    """Règle générale : 2 demi-journées, 1 le mercredi, 0 le samedi et le dimanche."""
    return {0: 2, 1: 2, 2: 1, 3: 2, 4: 2}.get(d.weekday(), 0)


def date_longue(d):
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


def nb(v):
    """Nombre au format français (1 décimale, virgule)."""
    if v is None:
        return "—"
    if isinstance(v, int) or float(v).is_integer():
        return str(int(v))
    return f"{v:.1f}".replace(".", ",")


class Calendrier:
    """Jours de classe d'une école : règle générale + rentrée/fin des cours + exceptions (jours_classe)."""

    def __init__(self, H, ecole_id):
        self.H, self.eco, self._annees = H, ecole_id, {}

    def _annee(self, annee):
        if annee not in self._annees:
            a = int(annee[:4])
            p = parametres_calendrier(self.H, self.eco, annee)
            exc = {r["date"]: (r["demi_journees"], r["motif"] or "") for r in self.H.q(
                "SELECT date, demi_journees, motif FROM jours_classe WHERE ecole_id=? AND date BETWEEN ? AND ?",
                (self.eco, f"{a}-09-01", f"{a + 1}-08-31"))}
            self._annees[annee] = (lire_date(p["rentree"]) or date(a, 9, 1), lire_date(p["fin"]) or date(a + 1, 6, 30), exc)
        return self._annees[annee]

    def exception(self, d):
        return self._annee(annee_de(d))[2].get(d.isoformat())

    def info(self, d):
        """(nombre de demi-journées, motif, exception ?)"""
        rentree, fin, exc = self._annee(annee_de(d))
        e = exc.get(d.isoformat())
        if e:
            return e[0], e[1], True
        if d < rentree:
            return 0, "Avant la rentrée", False
        if d > fin:
            return 0, "Après la fin des cours", False
        n = demi_defaut(d)
        return n, ("" if n else ("Mercredi" if d.weekday() == 2 else "Week-end")), False

    def demi(self, d):
        return self.info(d)[0]

    def total(self, d1, d2):
        return sum(self.demi(d) for d in jours_entre(d1, d2))


def parametres_calendrier(H, ecole_id, annee):
    a = int(annee[:4])
    p = H.doc_lire(f"e{ecole_id}:registre:calendrier:{annee}", None) or {}
    return {"rentree": p.get("rentree") or f"{a}-09-01", "fin": p.get("fin") or f"{a + 1}-06-30"}


# ============================================================ élèves : ajout et import (partagés avec m_affichage)
def normaliser_nom(t):
    import outils_xlsx
    return outils_xlsx.normaliser(t)


def creer_eleve(H, classe, nom, prenoms, sexe, **extra):
    """Crée un élève inscrit dans la classe (champs minimaux) et lui attribue un matricule."""
    champs = ["nom", "prenoms", "sexe", "classe_id", "statut", "date_inscription", "annee"]
    vals = [nom.strip().upper()[:80], prenoms.strip()[:120], sexe, classe["id"], "inscrit", date.today().isoformat(),
            H.config.ANNEE_ACTIVE]
    for k in ("date_naissance", "annees_scolarite", "parent_telephone", "parent_nom", "lieu_naissance"):
        if extra.get(k) not in (None, ""):
            champs.append(k)
            vals.append(extra[k])
    eid = H.ex(f"INSERT INTO eleves ({', '.join(champs)}) VALUES ({', '.join('?' * len(champs))})", vals)
    cyc = {"maternelle": "M", "primaire": "P"}.get(classe.get("cycle"), "S")
    H.ex("UPDATE eleves SET matricule=? WHERE id=?", (f"{H.config.ECOLE.get('sigle') or 'EC'}-{H.config.ANNEE_ACTIVE[:4]}-{cyc}-{eid:04d}", eid))
    H.journal("eleve_inscrit", f"{nom} {prenoms} ({classe['nom']})")
    return eid


def lire_formulaire_eleve(form):
    """Contrôle du formulaire « Ajouter un élève ». Retourne (données, erreurs)."""
    import outils_xlsx as X
    d = {"nom": form.get("nom", "").strip(), "prenoms": form.get("prenoms", "").strip(),
         "sexe": X.sexe(form.get("sexe", "")), "date_naissance": "", "annees_scolarite": "",
         "parent_telephone": form.get("parent_telephone", "").strip()[:60]}
    err = []
    if not d["nom"] or not d["prenoms"]:
        err.append("Le nom et les prénoms sont obligatoires.")
    if not d["sexe"]:
        err.append("Choisissez le sexe (F ou M).")
    dn = form.get("date_naissance", "").strip()
    if dn:
        x = lire_date(dn)
        if not x or not date(1990, 1, 1) <= x <= date.today():
            err.append("Date de naissance invalide.")
        else:
            d["date_naissance"] = x.isoformat()
    sc = form.get("annees_scolarite", "").strip()
    if sc:
        if not sc.isdigit() or not 0 <= int(sc) <= 20:
            err.append("Années de scolarité : nombre entier entre 0 et 20.")
        else:
            d["annees_scolarite"] = int(sc)
    return d, err


def importer_eleves(H, classe, fichier):
    """Import Excel/CSV : colonnes nom, prénoms, sexe (+ facultatives : date de naissance, scolarité, contact).
    Crée les élèves absents de la classe ; complète les champs vides des élèves déjà présents.
    Retourne (créés, complétés, messages d'erreur)."""
    import outils_xlsx as X
    ent, lignes = X.lire_tableau(fichier, ("nom", "noms", "nom et prenoms"))
    i_nom = X.colonne(ent, "nom", "noms", "nom de famille")
    i_pre = X.colonne(ent, "prenoms", "prénom", "prenom")
    i_nomp = X.colonne(ent, "nom et prenoms", "nom et prénom", "nom prenoms")
    i_sexe = X.colonne(ent, "sexe", "genre", "s")
    i_dn = X.colonne(ent, "date de naissance", "ne le", "né(e) le", "naissance")
    i_sc = X.colonne(ent, "scolarite", "annees de scolarite", "scolarité")
    i_tel = X.colonne(ent, "contact des parents", "contact", "telephone", "téléphone", "contact parent")
    if i_nomp is not None and i_pre is None:
        i_nom = i_nomp
    if i_nom is None or i_sexe is None:
        raise ValueError("Colonnes « Nom », « Prénoms » et « Sexe » introuvables dans le fichier.")
    existants = {(normaliser_nom(e["nom"]), normaliser_nom(e["prenoms"])): e for e in H.q(
        "SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit'", (classe["id"],))}
    crees = completes = 0
    erreurs = []
    for n, l in enumerate(lignes, 2):
        nom, pre = X.valeur(l, i_nom), X.valeur(l, i_pre) if i_pre is not None else ""
        if i_pre is None and " " in nom:  # une seule colonne « Nom et prénoms »
            nom, pre = nom.split(" ", 1)
        sexe = X.sexe(X.valeur(l, i_sexe))
        if not nom:
            continue
        if not pre or not sexe:
            erreurs.append(f"Ligne {n} ({nom}) : prénoms ou sexe manquant — ignorée.")
            continue
        dn = X.date_iso(X.valeur(l, i_dn)) if i_dn is not None else ""
        sc = X.valeur(l, i_sc) if i_sc is not None else ""
        sc = int(sc) if str(sc).isdigit() and int(sc) <= 20 else ""
        tel = X.valeur(l, i_tel)[:60] if i_tel is not None else ""
        e = existants.get((normaliser_nom(nom), normaliser_nom(pre)))
        if e:
            maj = {k: v for k, v in (("date_naissance", dn), ("annees_scolarite", sc), ("parent_telephone", tel))
                   if v not in ("", None) and not e[k]}
            if maj:
                H.ex(f"UPDATE eleves SET {', '.join(k + '=?' for k in maj)} WHERE id=?", list(maj.values()) + [e["id"]])
                completes += 1
            continue
        creer_eleve(H, classe, nom, pre, sexe, date_naissance=dn, annees_scolarite=sc, parent_telephone=tel)
        existants[(normaliser_nom(nom), normaliser_nom(pre))] = {"id": 0}
        crees += 1
    return crees, completes, erreurs


def retour_sur(url, defaut):
    return url if url and url.startswith("/") and not url.startswith("//") else defaut


# ============================================================ calcul du relevé
def releve_auto(H, cal, classe, annee, aujourdhui=None):
    """Valeurs calculées à partir du calendrier et du registre, pour chaque mois (None = mois à venir)."""
    auj = aujourdhui or date.today()
    # élèves inscrits de la classe. NB : la date d'inscription n'est pas utilisée (elle vaut souvent la date de
    # saisie dans GESCOL, pas la date d'arrivée réelle) ; l'effectif d'un mois se corrige à la main si besoin.
    eleves = {e["id"] for e in H.q("SELECT id FROM eleves WHERE classe_id=? AND statut='inscrit'", (classe["id"],))}
    a = int(annee[:4])
    rows = H.q("""SELECT r.eleve_id, r.date, r.demi FROM registre r JOIN eleves e ON e.id=r.eleve_id
                  WHERE e.classe_id=? AND e.statut='inscrit' AND r.date BETWEEN ? AND ?""",
               (classe["id"], f"{a}-09-01", f"{a + 1}-06-30"))
    par_mois = {}
    for r in rows:
        d = lire_date(r["date"])
        if d and d <= auj and r["demi"] <= cal.demi(d):  # une absence n'est comptée que sur une demi-journée de classe
            par_mois.setdefault(d.month, {}).setdefault(r["eleve_id"], 0)
            par_mois[d.month][r["eleve_id"]] += 1
    res = {}
    for y, m in mois_scolaires(annee):
        d1 = date(y, m, 1)
        if d1 > auj:
            res[m] = None
            continue
        d2 = min(fin_mois(y, m), auj)
        presents = eleves
        abs_el = {eid: n for eid, n in par_mois.get(m, {}).items() if eid in presents}
        n5 = [v for v in abs_el.values() if v > 4]  # élèves ayant manqué plus de 4 fois
        res[m] = {"dj": cal.total(d1, d2), "eff": len(presents), "abs": sum(abs_el.values()),
                  "n4": len(presents) - len(n5), "n5": len(n5), "imp": sum(n5)}
    return res


def entier(v):
    s = str(v if v is not None else "").strip().replace(" ", "")
    return int(s) if s.isdigit() else None


def releve_final(auto, saisies, annee):
    """Fusionne calcul automatique et saisies manuelles ; ajoute colonnes calculées, TOTAL et MOYENNE GÉNÉRALE."""
    lignes = []
    tot = {c: 0 for c, _, _ in COLONNES_RELEVE}
    nmois = 0
    for y, m in mois_scolaires(annee):
        a = auto.get(m) or {}
        v = {}
        for c in SAISIES:
            s = entier(saisies.get(f"{c}_{m}"))
            v[c] = s if s is not None else a.get(c)
        vide = all(v[c] is None for c in SAISIES)
        if not vide:
            v = {c: (v[c] or 0) for c in SAISIES}
            v["poss"] = v["dj"] * v["eff"]
            v["effe"] = v["poss"] - v["abs"]
            v["pct"] = round(100 * v["effe"] / v["poss"], 1) if v["poss"] else None
            for c in SAISIES + ["poss", "effe"]:
                tot[c] += v[c]
            if v["dj"]:
                nmois += 1
        lignes.append({"mois": m, "lib": LIB_MOIS_RELEVE[m], "v": None if vide else v,
                       "manuel": {c for c in SAISIES if entier(saisies.get(f"{c}_{m}")) is not None}})
    tot["pct"] = round(100 * tot["effe"] / tot["poss"], 1) if tot["poss"] else None
    moy = {c: (round(tot[c] / nmois, 1) if nmois else 0.0) for c in SAISIES + ["poss", "effe"]}
    moy["pct"] = None
    return lignes, tot, moy, nmois


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex

    def calendrier():
        return Calendrier(H, H.eco())

    def peut_modifier_calendrier():
        return g.user["role"] in ROLES_CALENDRIER

    def classe_choisie():
        """Classe demandée (?classe=) contrôlée ; si une seule classe autorisée, elle est choisie d'office."""
        cls = H.classes_autorisees()
        cid = request.values.get("classe", type=int)
        if cid is None and len(cls) == 1:
            cid = cls[0]["id"]
        if cid is None:
            return cls, None
        H.verifier_classe(cid)
        return cls, H.classe_ou_404(cid)

    @app.context_processor
    def ctx_registre():
        return dict(nb_fr=nb)

    # -------------------------------------------------------------- registre : grille élève × demi-journées
    def periode_affichee(cal):
        """Lit mois / semaine / vue ; retourne dict (du, au, jours, navigation)."""
        auj = date.today()
        vue = "semaine" if request.args.get("vue") == "semaine" else "mois"
        y, m = lire_mois(request.args.get("mois"), (auj.year, auj.month))
        if vue == "semaine":
            s = lire_date(request.args.get("semaine")) or (auj if (auj.year, auj.month) == (y, m) else date(y, m, 1))
            du = s - timedelta(days=s.weekday())
            au = du + timedelta(days=6)
            y, m = (du + timedelta(days=3)).year, (du + timedelta(days=3)).month
            prec = {"vue": vue, "semaine": (du - timedelta(days=7)).isoformat()}
            suiv = {"vue": vue, "semaine": (du + timedelta(days=7)).isoformat()}
            titre = f"Semaine du {du.day} {MOIS[du.month - 1]} au {au.day} {MOIS[au.month - 1]} {au.year}"
        else:
            du, au = date(y, m, 1), fin_mois(y, m)
            pm = du - timedelta(days=1)
            sm = au + timedelta(days=1)
            prec = {"vue": vue, "mois": f"{pm.year}-{pm.month:02d}"}
            suiv = {"vue": vue, "mois": f"{sm.year}-{sm.month:02d}"}
            titre = f"{MOIS[m - 1].capitalize()} {y}"
        jours = []
        for d in jours_entre(du, au):
            n, motif, _ = cal.info(d)
            jours.append({"iso": d.isoformat(), "court": JOURS_COURTS[d.weekday()], "num": d.day, "n": n,
                          "motif": motif, "futur": d > auj, "auj": d == auj, "long": date_longue(d)})
        return {"vue": vue, "du": du, "au": au, "jours": jours, "prec": prec, "suiv": suiv, "titre": titre,
                "mois": f"{y}-{m:02d}", "semaine": du.isoformat() if vue == "semaine" else
                (auj - timedelta(days=auj.weekday())).isoformat() if (auj.year, auj.month) == (y, m)
                else (du - timedelta(days=du.weekday())).isoformat()}

    def absences_classe(cid, du, au):
        return {(r["eleve_id"], r["date"], r["demi"]) for r in q(
            """SELECT r.eleve_id, r.date, r.demi FROM registre r JOIN eleves e ON e.id=r.eleve_id
               WHERE e.classe_id=? AND r.date BETWEEN ? AND ?""", (cid, du.isoformat(), au.isoformat()))}

    def eleves_de(cid):
        return q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (cid,))

    @app.route("/registre")
    @H.connexion_requise("registre")
    def registre_accueil():
        cls, cl = classe_choisie()
        cal = calendrier()
        p = periode_affichee(cal)
        if not cl:
            d1, d2 = p["du"].isoformat(), p["au"].isoformat()
            resume = []
            for c in cls:
                eff = q("SELECT COUNT(*) n FROM eleves WHERE classe_id=? AND statut='inscrit'", (c["id"],), un=True)["n"]
                na = q("""SELECT COUNT(*) n FROM registre r JOIN eleves e ON e.id=r.eleve_id
                          WHERE e.classe_id=? AND e.statut='inscrit' AND r.date BETWEEN ? AND ?""", (c["id"], d1, d2), un=True)["n"]
                resume.append({"c": c, "eff": eff, "abs": na})
            return render_template("registre_accueil.html", cls=cls, cl=None, p=p, resume=resume)
        eleves = eleves_de(cl["id"])
        absn = absences_classe(cl["id"], p["du"], p["au"])
        # ne compter que les absences posées sur une demi-journée de classe
        valides = {j["iso"]: j["n"] for j in p["jours"]}
        absn = {a for a in absn if a[2] <= valides.get(a[1], 0)}
        dj = sum(j["n"] for j in p["jours"] if not j["futur"])
        poss = dj * len(eleves)
        return render_template("registre_accueil.html", cls=cls, cl=cl, p=p, eleves=eleves, absn=absn, dj=dj,
                               poss=poss, taux=round(100 * (poss - len(absn)) / poss, 1) if poss else None,
                               retour=request.full_path)

    def eleve_de_classe(eid, cid):
        e = q("SELECT * FROM eleves WHERE id=? AND classe_id=? AND statut='inscrit'", (eid, cid), un=True)
        if not e:
            abort(400)
        return e

    @app.route("/registre/presence", methods=["POST"])
    @H.connexion_requise("registre")
    def registre_presence():
        """Bascule présent/absent d'une case (AJAX, JSON {eleve_id, date, demi, absent})."""
        d = request.get_json(silent=True) or {}
        try:
            eid, demi = int(d.get("eleve_id")), int(d.get("demi"))
        except (TypeError, ValueError):
            return {"ok": False, "erreur": "Données invalides."}, 400
        jour = lire_date(d.get("date"))
        e = q("SELECT * FROM eleves WHERE id=? AND statut='inscrit'", (eid,), un=True)
        if not e or not e["classe_id"] or not jour or demi not in (1, 2):
            return {"ok": False, "erreur": "Données invalides."}, 400
        H.verifier_classe(e["classe_id"])
        if jour > date.today():
            return {"ok": False, "erreur": "On ne peut pas marquer une absence pour un jour futur."}, 400
        if demi > calendrier().demi(jour):
            return {"ok": False, "erreur": "Pas de classe sur cette demi-journée (voir le calendrier)."}, 400
        if d.get("absent"):
            ex("INSERT OR IGNORE INTO registre (eleve_id, date, demi) VALUES (?,?,?)", (eid, jour.isoformat(), demi))
        else:
            ex("DELETE FROM registre WHERE eleve_id=? AND date=? AND demi=?", (eid, jour.isoformat(), demi))
        return {"ok": True, "absent": bool(d.get("absent"))}

    def periode_post(d):
        du, au = lire_date(d.get("du")), lire_date(d.get("au"))
        if not du or not au or du > au or (au - du).days > 62:
            abort(400)
        return du, au

    @app.route("/registre/absences")
    @H.connexion_requise("registre")
    def registre_absences():
        """« Charger » : absences enregistrées de la classe sur la période."""
        cid = request.args.get("classe", type=int)
        H.verifier_classe(cid)
        du, au = periode_post(request.args)
        return jsonify({"ok": True, "absences": sorted([list(a) for a in absences_classe(cid, du, au)])})

    @app.route("/registre/sauvegarder", methods=["POST"])
    @H.connexion_requise("registre")
    def registre_sauvegarder():
        """« Sauvegarder » : enregistre d'un coup l'état de la grille affichée (utile après une coupure réseau)."""
        d = request.get_json(silent=True) or {}
        try:
            cid = int(d.get("classe"))
        except (TypeError, ValueError):
            return {"ok": False, "erreur": "Classe invalide."}, 400
        H.verifier_classe(cid)
        du, au = periode_post(d)
        cal = calendrier()
        ids = {e["id"] for e in eleves_de(cid)}
        propres = set()
        for a in d.get("absences") or []:
            try:
                eid, jour, demi = int(a[0]), lire_date(a[1]), int(a[2])
            except (TypeError, ValueError, IndexError):
                continue
            if eid in ids and jour and du <= jour <= au and jour <= date.today() and 1 <= demi <= cal.demi(jour):
                propres.add((eid, jour.isoformat(), demi))
        db = H.get_db()
        if ids:
            marque = ",".join("?" * len(ids))
            db.execute(f"DELETE FROM registre WHERE eleve_id IN ({marque}) AND date BETWEEN ? AND ?",
                       list(ids) + [du.isoformat(), au.isoformat()])
        db.executemany("INSERT OR IGNORE INTO registre (eleve_id, date, demi) VALUES (?,?,?)", sorted(propres))
        db.commit()
        H.journal("registre", f"classe {cid} {du}→{au} : {len(propres)} absence(s)")
        return {"ok": True, "n": len(propres)}

    @app.route("/registre/reinitialiser", methods=["POST"])
    @H.connexion_requise("registre")
    def registre_reinitialiser():
        cid = request.form.get("classe", type=int)
        H.verifier_classe(cid)
        du, au = periode_post(request.form)
        ids = [e["id"] for e in eleves_de(cid)]
        n = 0
        if ids:
            marque = ",".join("?" * len(ids))
            n = q(f"SELECT COUNT(*) n FROM registre WHERE eleve_id IN ({marque}) AND date BETWEEN ? AND ?",
                  ids + [du.isoformat(), au.isoformat()], un=True)["n"]
            ex(f"DELETE FROM registre WHERE eleve_id IN ({marque}) AND date BETWEEN ? AND ?", ids + [du.isoformat(), au.isoformat()])
        H.journal("registre_reinitialise", f"classe {cid} {du}→{au} : {n}")
        flash(f"{n} absence(s) effacée(s) du {du.strftime('%d/%m/%Y')} au {au.strftime('%d/%m/%Y')}.", "success")
        return redirect(retour_sur(request.form.get("retour"), url_for("registre_accueil", classe=cid)))

    @app.route("/registre/eleves/ajouter", methods=["POST"])
    @H.connexion_requise("registre")
    def registre_ajouter_eleve():
        cid = request.form.get("classe", type=int)
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        d, err = lire_formulaire_eleve(request.form)
        if err:
            for m in err:
                flash(m, "danger")
        else:
            creer_eleve(H, cl, d["nom"], d["prenoms"], d["sexe"], date_naissance=d["date_naissance"],
                        annees_scolarite=d["annees_scolarite"], parent_telephone=d["parent_telephone"])
            flash(f"Élève {d['nom'].upper()} {d['prenoms']} ajouté(e) en {cl['nom']}.", "success")
        return redirect(retour_sur(request.form.get("retour"), url_for("registre_accueil", classe=cid)))

    @app.route("/registre/eleves/importer", methods=["POST"])
    @H.connexion_requise("registre")
    def registre_importer():
        cid = request.form.get("classe", type=int)
        H.verifier_classe(cid)
        traiter_import(H.classe_ou_404(cid))
        return redirect(retour_sur(request.form.get("retour"), url_for("registre_accueil", classe=cid)))

    def traiter_import(cl):
        f = request.files.get("fichier")
        if not f or not f.filename:
            flash("Choisissez un fichier Excel (.xlsx) ou CSV.", "warning")
            return
        if not f.filename.lower().endswith((".xlsx", ".xlsm", ".csv", ".txt")):
            flash("Format non reconnu : utilisez un fichier .xlsx ou .csv.", "danger")
            return
        try:
            cr, co, err = importer_eleves(H, cl, f)
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return
        except ValueError as e:
            flash(str(e), "danger")
            return
        flash(f"Import terminé : {cr} élève(s) créé(s), {co} fiche(s) complétée(s).", "success" if cr or co else "info")
        for m in err[:10]:
            flash(m, "warning")

    app.traiter_import_eleves = traiter_import  # réutilisé par le tableau d'affichage

    @app.route("/registre/pdf")
    @H.connexion_requise("registre")
    def registre_pdf():
        cid = request.args.get("classe", type=int)
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        cal = calendrier()
        y, m = lire_mois(request.args.get("mois"), (date.today().year, date.today().month))
        du, au = date(y, m, 1), fin_mois(y, m)
        jours = [(d, cal.demi(d)) for d in jours_entre(du, au) if cal.demi(d) > 0]
        eleves = eleves_de(cid)
        absn = absences_classe(cid, du, au)
        v = entete_releve(cl, annee_de(du))
        h1, h2, larg = ["N°", "Nom et prénoms"], ["^", "^"], [6, 44]
        for d, n in jours:
            h1 += [f"{JOURS_COURTS[d.weekday()]} {d.day}"] + [None] * (n - 1)
            h2 += ["M", "S"][:n]
            larg += [5] * n
        h1.append("Abs.")
        h2.append("^")
        larg.append(9)
        nbc = sum(n for _, n in jours)
        taille = 6 if nbc > 30 else 7
        lignes, tot_col = [], [0] * nbc
        for i, e in enumerate(eleves, 1):
            cells, k, t = [], 0, 0
            for d, n in jours:
                for demi in range(1, n + 1):
                    a = (e["id"], d.isoformat(), demi) in absn
                    cells.append(centre('<font color="#B42318"><b>A</b></font>', taille) if a else "")
                    tot_col[k] += a
                    t += a
                    k += 1
            lignes.append([centre(i, taille), f"{e['nom']} {e['prenoms']}"] + cells + [centre(t or "", taille, True)])
        total = ["", "Absents"] + [centre(x or "", taille, True) for x in tot_col] + [centre(sum(tot_col), taille, True)]
        pdf = H.pdfs.pour_cycle(dict(cl).get("cycle"))(
            "REGISTRE DE PRÉSENCE", [h1, h2], lignes, total=total, paysage=True,
            sous_titre=f"{MOIS[m - 1].capitalize()} {y} — Année scolaire {annee_de(du)} — A = absent(e), case vide = présent(e) ; M = matin, S = soir (après-midi)",
            infos=[("Cours", v["cours"]), ("Titulaire", v["titulaire_nom"]),
                   ("Effectif", len(eleves)), ("Demi-journées", sum(n for _, n in jours)),
                   ("Absences du mois", sum(tot_col)), ("Année scolaire", v["annee"])],
            infos_haut=[("DDEMP", v["ddemp"]), ("CS", v["cs"]), ("ÉCOLE", v["ecole"])],
            largeurs=larg, taille=taille,
            signatures=signatures_pdf(cl, v))
        return H.pdf_reponse(pdf, f"registre_{cl['nom'].replace(' ', '_')}_{y}-{m:02d}.pdf")

    def centre(v, taille, gras=False):
        """Cellule de tableau PDF centrée (le texte passé est déjà sûr : nombres, « — », balises fixes)."""
        return H.pdfs.paragraphe(str(v), taille, gras, 1, 0)

    def signatures_pdf(cl, v):
        img_t = H.pdfs.image_data_url(H.signature(f"classe:{cl['id']}:titulaire"))
        img_d = H.pdfs.image_data_url(H.signature(f"ecole:{H.eco()}:directeur"))
        return [(f"{v.get('titulaire_titre') or 'Le titulaire'}".upper(), v.get("titulaire_nom", ""), img_t, False),
                (f"{'La' if (v.get('directeur_titre') or '').startswith('Directrice') else 'Le'} "
                 f"{v.get('directeur_titre') or 'Directeur'}".upper(), v.get("directeur_nom", ""), img_d, True)]

    # -------------------------------------------------------------- relevés mensuels
    def entete_releve(cl, annee):
        v = H.identification(cl, annee=annee)
        sauve = H.doc_lire(f"e{H.eco()}:releve:{cl['id']}:{annee}", None) or {}
        for k in ("ddemp", "cs", "ecole", "cours", "annee", "titulaire_titre", "titulaire_nom", "directeur_titre",
                  "directeur_nom"):
            if sauve.get(k):
                v[k] = sauve[k]
        return v

    @app.route("/releves")
    @H.connexion_requise("registre")
    def releve_mensuel():
        cls, cl = classe_choisie()
        annee = annee_valide(request.args.get("annee"), H.config.ANNEE_ACTIVE)
        if not cl:
            return render_template("releve_mensuel.html", cls=cls, cl=None, annee=annee)
        cal = calendrier()
        auto = releve_auto(H, cal, cl, annee)
        sauve = H.doc_lire(f"e{H.eco()}:releve:{cl['id']}:{annee}", None) or {}
        lignes, tot, moy, nmois = releve_final(auto, sauve, annee)
        return render_template("releve_mensuel.html", cls=cls, cl=cl, annee=annee, v=entete_releve(cl, annee),
                               auto=auto, sauve=sauve, lignes=lignes, tot=tot, moy=moy, nmois=nmois,
                               colonnes=COLONNES_RELEVE, auto_json=json.dumps(auto))

    @app.route("/releves/pdf", methods=["POST"])
    @H.connexion_requise("registre")
    def releve_pdf():
        """PDF conforme au modèle, à partir des valeurs du formulaire (saisies + calcul automatique)."""
        cid = request.args.get("classe", type=int)
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        annee = annee_valide(request.args.get("annee"), H.config.ANNEE_ACTIVE)
        f = request.form
        v = entete_releve(cl, annee)
        for k in list(v):  # un champ vidé (Réinitialiser) reprend la valeur par défaut
            if (f.get(k) or "").strip():
                v[k] = f.get(k).strip()[:120]
        auto = releve_auto(H, calendrier(), cl, annee)
        lignes, tot, moy, _ = releve_final(auto, f, annee)
        ordre = [c for c, _, _ in COLONNES_RELEVE]

        def fmt(val, c):
            if val is None:
                return "—"
            return (nb(val) + " %") if c == "pct" else nb(val)

        data = []
        for l in lignes:
            data.append([centre(l["lib"], 7.5, True)] + [centre(fmt(l["v"][c], c) if l["v"] else "—", 7.5, c == "pct")
                                                         for c in ordre])
        data.append([centre("TOTAL", 7.5, True)] + [centre(fmt(tot[c], c), 7.5, True) for c in ordre])
        total = [centre("MOYENNE GÉN.", 7.5, True)] + [centre("—" if c == "pct" else f"{moy[c]:.1f}".replace(".", ","), 7.5, True)
                                                    for c in ordre]
        entetes = ["Mois"] + [f"({i})\n{lib}" for i, (_, lib, _) in enumerate(COLONNES_RELEVE, 1)]
        pdf = H.pdfs.pour_cycle(dict(cl).get("cycle"))(
            "TABLEAU DE RELEVÉS MENSUELS POUR L'ANNÉE SCOLAIRE", entetes, data, total=total, paysage=True,
            sous_titre=f"Année scolaire : {v['annee'] or annee}",
            infos=[("DDEMP :", v["ddemp"]), ("CS :", v["cs"]), ("ÉCOLE :", v["ecole"]), ("COURS :", v["cours"]),
                   ("TITULAIRE :", f"{v['titulaire_nom']}"), ("ANNÉE :", v["annee"] or annee)],
            infos_haut=[("DDEMP", v["ddemp"]), ("CS", v["cs"]), ("ÉCOLE", v["ecole"])],
            largeurs=[14, 18, 22, 22, 15, 16, 19, 26, 19, 24], taille=7.5, surlignes={10: "#DCE6F2"},
            notes_bas=["Présences possibles = demi-jours de classe × élèves ayant fréquenté la classe ; "
                       "présences effectives = présences possibles − absences ; pourcentage = présences effectives / "
                       "présences possibles × 100. Moyenne générale = total / nombre de mois renseignés."],
            signatures=signatures_pdf(cl, v))
        H.journal("releve_pdf", f"{cl['nom']} {annee}")
        return H.pdf_reponse(pdf, f"releve_mensuel_{cl['nom'].replace(' ', '_')}_{annee}.pdf")

    # -------------------------------------------------------------- calendrier scolaire
    @app.route("/calendrier")
    @H.connexion_requise("registre")
    def calendrier_scolaire():
        auj = date.today()
        y, m = lire_mois(request.args.get("mois"), (auj.year, auj.month))
        annee = annee_de(date(y, m, 1))
        cal = calendrier()
        premier = date(y, m, 1)
        debut = premier - timedelta(days=premier.weekday())
        semaines, total = [], 0
        d = debut
        while d <= fin_mois(y, m) or d.weekday() != 0:
            if d.weekday() == 0:
                semaines.append([])
            n, motif, exc = cal.info(d)
            dans = d.month == m
            semaines[-1].append({"iso": d.isoformat(), "num": d.day, "dans": dans, "n": n, "motif": motif,
                                 "exc": exc, "defaut": demi_defaut(d), "auj": d == auj,
                                 "val": str(cal.exception(d)[0]) if exc else "auto",
                                 "motif_exc": cal.exception(d)[1] if exc else ""})
            if dans:
                total += n
            d += timedelta(days=1)
        # récapitulatif de l'année
        recap = []
        for yy, mm in mois_scolaires(annee):
            d1, d2 = date(yy, mm, 1), fin_mois(yy, mm)
            recap.append({"mois": f"{yy}-{mm:02d}", "lib": f"{MOIS[mm - 1].capitalize()} {yy}",
                          "dj": cal.total(d1, d2), "jours": sum(1 for x in jours_entre(d1, d2) if cal.demi(x) > 0)})
        exc = q("SELECT * FROM jours_classe WHERE ecole_id=? AND date BETWEEN ? AND ? ORDER BY date",
                (H.eco(), f"{annee[:4]}-09-01", f"{int(annee[:4]) + 1}-08-31"))
        pm, sm = premier - timedelta(days=1), fin_mois(y, m) + timedelta(days=1)
        return render_template("calendrier_scolaire.html", semaines=semaines, total=total, titre=f"{MOIS[m - 1].capitalize()} {y}",
                               mois=f"{y}-{m:02d}", prec=f"{pm.year}-{pm.month:02d}", suiv=f"{sm.year}-{sm.month:02d}",
                               annee=annee, recap=recap, exc=exc, motifs=MOTIFS, feries=FERIES_FIXES,
                               params=parametres_calendrier(H, H.eco(), annee), modifiable=peut_modifier_calendrier(),
                               date_longue=lambda iso: date_longue(lire_date(iso)))

    def exiger_modif_calendrier():
        if not peut_modifier_calendrier():
            abort(403)

    def poser_exception(d, n, motif):
        ex("""INSERT INTO jours_classe (ecole_id, date, demi_journees, motif) VALUES (?,?,?,?)
              ON CONFLICT(ecole_id, date) DO UPDATE SET demi_journees=excluded.demi_journees, motif=excluded.motif""",
           (H.eco(), d.isoformat(), n, (motif or "").strip()[:80] or None))

    @app.route("/calendrier/enregistrer", methods=["POST"])
    @H.connexion_requise("registre")
    def calendrier_enregistrer():
        """Enregistre les exceptions du mois affiché (auto = règle générale)."""
        exiger_modif_calendrier()
        y, m = lire_mois(request.form.get("mois"), (0, 0))
        if not y:
            abort(400)
        n_exc = 0
        for d in jours_entre(date(y, m, 1), fin_mois(y, m)):
            val = request.form.get(f"j_{d.isoformat()}", "auto")
            if val not in ("auto", "0", "1", "2"):
                flash(f"Valeur invalide pour le {d.strftime('%d/%m')}.", "danger")
                continue
            if val == "auto":
                ex("DELETE FROM jours_classe WHERE ecole_id=? AND date=?", (H.eco(), d.isoformat()))
            else:
                poser_exception(d, int(val), request.form.get(f"m_{d.isoformat()}", ""))
                n_exc += 1
        H.journal("calendrier", f"{y}-{m:02d} : {n_exc} exception(s)")
        flash(f"Calendrier de {MOIS[m - 1]} {y} enregistré ({n_exc} exception(s)).", "success")
        return redirect(url_for("calendrier_scolaire", mois=f"{y}-{m:02d}"))

    @app.route("/calendrier/feries", methods=["POST"])
    @H.connexion_requise("registre")
    def calendrier_feries():
        """Pré-remplit les jours fériés fixes du Bénin pour l'année scolaire (sans écraser une saisie existante)."""
        exiger_modif_calendrier()
        annee = annee_valide(request.form.get("annee"), H.config.ANNEE_ACTIVE)
        a = int(annee[:4])
        n = 0
        for mm, jj, lib in FERIES_FIXES:
            d = date(a if mm >= 9 else a + 1, mm, jj)
            if not q("SELECT 1 FROM jours_classe WHERE ecole_id=? AND date=?", (H.eco(), d.isoformat()), un=True):
                poser_exception(d, 0, lib)
                n += 1
        flash(f"{n} jour(s) férié(s) fixe(s) ajouté(s) pour {annee}. Marquez à la main les fêtes mobiles "
              "(Pâques, Ascension, Pentecôte, Tabaski, Ramadan, Maouloud).", "success")
        return redirect(retour_sur(request.form.get("retour"), url_for("calendrier_scolaire")))

    @app.route("/calendrier/periode", methods=["POST"])
    @H.connexion_requise("registre")
    def calendrier_periode():
        """Marque une période (vacances, congés…) : 0 demi-journée, ou retour à la règle générale."""
        exiger_modif_calendrier()
        du, au = lire_date(request.form.get("du")), lire_date(request.form.get("au"))
        val = request.form.get("valeur", "0")
        if not du or not au or du > au or (au - du).days > 120 or val not in ("0", "auto"):
            flash("Période invalide (dates obligatoires, 4 mois au maximum).", "danger")
            return redirect(retour_sur(request.form.get("retour"), url_for("calendrier_scolaire")))
        motif = request.form.get("motif", "").strip()[:80]
        n = 0
        for d in jours_entre(du, au):
            if val == "auto":
                ex("DELETE FROM jours_classe WHERE ecole_id=? AND date=?", (H.eco(), d.isoformat()))
            elif demi_defaut(d) > 0:  # on ne marque que les jours normalement travaillés
                poser_exception(d, 0, motif or "Vacances")
            n += 1
        flash(f"Période du {du.strftime('%d/%m/%Y')} au {au.strftime('%d/%m/%Y')} enregistrée ({n} jour(s)).", "success")
        return redirect(retour_sur(request.form.get("retour"), url_for("calendrier_scolaire", mois=du.strftime("%Y-%m"))))

    @app.route("/calendrier/parametres", methods=["POST"])
    @H.connexion_requise("registre")
    def calendrier_parametres():
        """Date de rentrée et date de fin des cours de l'année scolaire."""
        exiger_modif_calendrier()
        annee = annee_valide(request.form.get("annee"), H.config.ANNEE_ACTIVE)
        a = int(annee[:4])
        r, f = lire_date(request.form.get("rentree")), lire_date(request.form.get("fin"))
        if not r or not f or not (date(a, 8, 1) <= r < f <= date(a + 1, 8, 31)):
            flash(f"Dates invalides : la rentrée et la fin des cours doivent être dans l'année {annee}.", "danger")
        else:
            H.doc_ecrire(f"e{H.eco()}:registre:calendrier:{annee}", {"rentree": r.isoformat(), "fin": f.isoformat()})
            flash(f"Rentrée le {r.strftime('%d/%m/%Y')}, fin des cours le {f.strftime('%d/%m/%Y')}.", "success")
        return redirect(retour_sur(request.form.get("retour"), url_for("calendrier_scolaire")))
