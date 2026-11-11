# -*- coding: utf-8 -*-
"""Calendrier scolaire officiel (MEMP) — toutes éditions (GESCOL, GESCOL Public, CS, DDEMP) — v1.6.

Le calendrier de l'année scolaire (pré-rentrée, trimestres, congés, jours fériés, grandes vacances…) est inséré
dans le tableau synoptique de l'école (onglet « Calendrier scolaire » de m_synoptique) et dans celui de la
structure (a_synoptique) ; il est aussi accessible par le menu (Vie de l'école / Animation pédagogique).

* Table ``calendrier_officiel`` : une ligne par période (id, ecole_id, annee, ordre, type, libelle, date_debut,
  date_fin, precision, duree, observations, officiel 1/0, maj, maj_par). ``ecole_id`` = école (``H.eco()``) ;
  0 = calendrier commun de la structure (CS / DDEMP sans école ouverte, ou onglet du synoptique de la structure).
  Table ``calendrier_officiel_meta`` (ecole_id, annee, reference_arrete, source, maj) : référence du texte.
* Types : pre_rentree, trimestre, conges, ferie, vacances, evenement, autre.
* Préremplissage : à la première ouverture d'une année dont on connaît le calendrier officiel
  (``CALENDRIERS_OFFICIELS`` : 2026-2027, arrêté interministériel n° 017/MEMP/MES/MESRS-FT/… du 28 juillet 2026),
  les lignes officielles (``officiel = 1``) sont insérées : pré-rentrée, 3 trimestres, 3 congés (fin du 1er
  trimestre, détente, fin du 2e trimestre), 3 lignes de jours fériés (« jeudi 07 et vendredi 08 janvier 2027 »
  = UNE ligne du 07 au 08 ; Ascension ; lundi de Pentecôte), grandes vacances : 10 lignes. Les autres jours
  fériés (déclarés par le Ministre chargé de la Fonction publique) sont ajoutés par l'utilisateur.
* Boutons : Ajouter / Modifier / Supprimer (lignes), Recharger (remet seulement les lignes officielles, garde
  les lignes ajoutées par l'utilisateur), Réinitialiser (supprime tout pour l'année puis remet l'officiel),
  Préparer l'année suivante (copie les lignes en décalant d'un an, à corriger ensuite), Excel, Import (modèle
  téléchargeable ; l'import REMPLACE les lignes de l'année), PDF (portrait, en-tête école ou CS / DDEMP,
  référence de l'arrêté en bas), vue « calendrier » (12 mois septembre → août, jours colorés par type).

Règles de calcul (fonctions pures, testées) :
* un jour de classe = un jour du lundi au vendredi compris dans un trimestre et hors période de congés, de
  vacances ou jour férié ;
* une période de congés / vacances dont la précision contient « après les cours » commence EFFECTIVEMENT le
  lendemain de sa date de début (le jour indiqué reste un jour de classe : « du vendredi 18 décembre après les
  cours ») ; la date de fin est toujours incluse ;
* semaines de classe = jours de classe ÷ 5 (« 14 semaines », « 10 semaines 3 jours ») ; le calcul tient compte
  des jours fériés saisis, la durée officielle du texte est affichée telle quelle à côté.

Passerelle avec le registre (m_registre, calendrier des jours de classe) : « Appliquer au registre » écrit, pour
l'école ouverte, la rentrée (début du 1er trimestre) et la fin des cours (fin du dernier trimestre) dans le document
``e<ecole>:registre:calendrier:<annee>`` (H.doc_ecrire, même format que m_registre.calendrier_parametres) et, dans
la table ``jours_classe`` (ecole_id, date, demi_journees = 0, motif), chaque jour normalement travaillé des
congés, vacances et jours fériés (même format que m_registre.calendrier_periode). Les saisies du registre hors de
ces périodes ne sont pas touchées.

Exposé : ``H.calendrier_officiel(annee, ecole_id)`` (liste de dicts) et ``H.calendrier_jours_classe(annee, ecole_id)``
(set de dates ISO). Droits : lecture pour tout utilisateur connecté ; écriture avec le droit ``calendrier_officiel``.
"""
import re
from datetime import date, datetime, timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

import config

TYPES = [("pre_rentree", "Pré-rentrée"), ("trimestre", "Trimestre"), ("conges", "Congés"), ("ferie", "Jour férié"),
         ("vacances", "Grandes vacances"), ("evenement", "Événement"), ("autre", "Autre")]
TYPES_LIB = dict(TYPES)
# types pendant lesquels il n'y a pas classe
TYPES_SANS_CLASSE = ("conges", "ferie", "vacances")
COULEURS = {"pre_rentree": "#FDE68A", "trimestre": "#D1FAE5", "conges": "#FECACA", "ferie": "#FCA5A5",
            "vacances": "#E9D5FF", "evenement": "#BFDBFE", "autre": "#E5E7EB", "classe": "#D1FAE5", "weekend": "#F3F4F6"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
JOURS_COURTS = ["Lu", "Ma", "Me", "Je", "Ve", "Sa", "Di"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]
RE_ANNEE = re.compile(r"^(\d{4})-(\d{4})$")
ENTETES_XLSX = ["Type", "Libellé", "Date de début", "Date de fin", "Précision", "Durée", "Observations", "Officiel"]

REFERENCE_2026 = ("Arrêté interministériel année 2026 n° 017/MEMP/MES/MESRS-FT/DC/SGM/DIIP/DEP/DEM/DEC/IGPM/DESG/"
                  "DESTFP/SA 015SGG26 fixant le calendrier de l'année scolaire 2026-2027 (articles 1 à 7)")
SOURCE_2026 = "MEMP / MES / MESRS-FT, Cotonou, le 28 juillet 2026"

# calendriers officiels connus : année → (référence, source, lignes (type, libellé, début, fin, précision, durée, observations))
CALENDRIERS_OFFICIELS = {
    "2026-2027": (REFERENCE_2026, SOURCE_2026, [
        ("pre_rentree", "Pré-rentrée scolaire", "2026-09-07", "2026-09-11", "", "1 semaine", "Article 1"),
        ("trimestre", "Premier trimestre", "2026-09-14", "2026-12-18", "après les cours de l'après-midi",
         "14 semaines de travail", "Article 2"),
        ("conges", "Congés de fin du premier trimestre", "2026-12-18", "2027-01-03", "après les cours ; dimanche 03 janvier inclus",
         "2 semaines", "Article 2"),
        ("trimestre", "Deuxième trimestre", "2027-01-04", "2027-03-24", "après les cours", "10 semaines 3 jours de travail",
         "Article 3"),
        ("conges", "Congés de détente", "2027-02-19", "2027-02-28", "après les cours ; dimanche 28 février inclus", "1 semaine",
         "Article 3"),
        ("conges", "Congés de fin du deuxième trimestre", "2027-03-24", "2027-04-07", "après les cours ; mercredi 07 avril inclus",
         "2 semaines", "Article 3"),
        ("trimestre", "Troisième trimestre", "2027-04-08", "2027-06-25", "après les cours", "11 semaines 2 jours", "Article 4"),
        ("vacances", "Grandes vacances", "2027-06-25", "2027-09-12", "après les cours ; reprise des activités pédagogiques le lundi 13 septembre 2027",
         "", "Article 5"),
        ("ferie", "Fête des cultes et traditions du Bénin", "2027-01-07", "2027-01-08", "jeudi 07 et vendredi 08 janvier 2027", "2 jours",
         "Article 6"),
        ("ferie", "Ascension", "2027-05-06", "2027-05-06", "jeudi", "1 jour", "Article 6"),
        ("ferie", "Lundi de Pentecôte", "2027-05-17", "2027-05-17", "lundi", "1 jour",
         "Article 6 — les autres jours fériés sont déclarés par le Ministre chargé de la Fonction publique"),
    ]),
}
NB_LIGNES_OFFICIELLES = {a: len(v[2]) for a, v in CALENDRIERS_OFFICIELS.items()}   # 2026-2027 : 11 lignes

SCHEMA = """
CREATE TABLE IF NOT EXISTS calendrier_officiel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ecole_id INTEGER NOT NULL DEFAULT 0,
    annee TEXT NOT NULL,
    ordre INTEGER DEFAULT 0,
    type TEXT NOT NULL DEFAULT 'autre',
    libelle TEXT NOT NULL,
    date_debut TEXT NOT NULL,
    date_fin TEXT NOT NULL,
    precision TEXT,
    duree TEXT,
    observations TEXT,
    officiel INTEGER NOT NULL DEFAULT 0,
    maj TEXT, maj_par INTEGER
);
CREATE INDEX IF NOT EXISTS i_calendrier_officiel ON calendrier_officiel(ecole_id, annee, date_debut);
CREATE TABLE IF NOT EXISTS calendrier_officiel_meta (
    ecole_id INTEGER NOT NULL DEFAULT 0,
    annee TEXT NOT NULL,
    reference_arrete TEXT,
    source TEXT,
    maj TEXT,
    PRIMARY KEY (ecole_id, annee)
);
"""


# ============================================================ fonctions pures
def annee_valide(a, defaut=None):
    m = RE_ANNEE.match((a or "").strip())
    return a.strip() if m and int(m.group(2)) == int(m.group(1)) + 1 else defaut


def annee_suivante(annee):
    a = int(annee[:4])
    return f"{a + 1}-{a + 2}"


def bornes_annee(annee):
    """(1er septembre, 31 août) de l'année scolaire."""
    a = int(annee[:4])
    return date(a, 9, 1), date(a + 1, 8, 31)


def lire_date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def date_longue(d):
    d = lire_date(d) if not isinstance(d, date) else d
    return f"{JOURS[d.weekday()]} {d.day:02d} {MOIS[d.month - 1]} {d.year}" if d else ""


def date_courte(d):
    d = lire_date(d) if not isinstance(d, date) else d
    return d.strftime("%d/%m/%Y") if d else ""


def decaler_un_an(iso):
    """Même jour, même mois, un an plus tard (29 février → 28 février)."""
    d = lire_date(iso)
    if not d:
        return iso
    try:
        return d.replace(year=d.year + 1).isoformat()
    except ValueError:
        return d.replace(year=d.year + 1, day=28).isoformat()


def jours_entre(d1, d2):
    d = d1
    while d <= d2:
        yield d
        d += timedelta(days=1)


def debut_effectif(ligne):
    """Premier jour SANS classe d'une période de congés / vacances : le lendemain de la date de début si la
    précision contient « après les cours » (le jour indiqué est encore un jour de classe)."""
    d = lire_date(ligne.get("date_debut"))
    if d and ligne.get("type") in ("conges", "vacances") and "après les cours" in (ligne.get("precision") or "").lower():
        return d + timedelta(days=1)
    return d


def jours_sans_classe(lignes):
    """Set des dates ISO couvertes par les congés, vacances et jours fériés (début effectif, fin incluse)."""
    out = set()
    for l in lignes:
        if l.get("type") not in TYPES_SANS_CLASSE:
            continue
        d1, d2 = debut_effectif(l), lire_date(l.get("date_fin"))
        if d1 and d2 and d1 <= d2:
            out.update(d.isoformat() for d in jours_entre(d1, d2))
    return out


def jours_classe(lignes):
    """Set des dates ISO des jours de classe : lundi → vendredi dans un trimestre, hors congés / vacances / fériés."""
    sans = jours_sans_classe(lignes)
    out = set()
    for l in lignes:
        if l.get("type") != "trimestre":
            continue
        d1, d2 = lire_date(l.get("date_debut")), lire_date(l.get("date_fin"))
        if not d1 or not d2:
            continue
        for d in jours_entre(d1, d2):
            if d.weekday() < 5 and d.isoformat() not in sans:
                out.add(d.isoformat())
    return out


def semaines_texte(n_jours):
    """14 jours → « 2 semaines 4 jours » ; 70 → « 14 semaines » ; 3 → « 3 jours »."""
    s, j = divmod(int(n_jours or 0), 5)
    parts = []
    if s:
        parts.append(f"{s} semaine{'s' if s > 1 else ''}")
    if j:
        parts.append(f"{j} jour{'s' if j > 1 else ''}")
    return " ".join(parts) or "0 jour"


def stats_trimestres(lignes):
    """Pour chaque trimestre : jours et semaines de classe calculés (hors congés et fériés saisis)."""
    sans = jours_sans_classe(lignes)
    out = []
    for l in lignes:
        if l.get("type") != "trimestre":
            continue
        d1, d2 = lire_date(l.get("date_debut")), lire_date(l.get("date_fin"))
        n = sum(1 for d in jours_entre(d1, d2) if d.weekday() < 5 and d.isoformat() not in sans) if d1 and d2 else 0
        out.append({"libelle": l.get("libelle"), "du": d1, "au": d2, "jours": n, "semaines": semaines_texte(n),
                    "duree_officielle": l.get("duree") or ""})
    return out


def types_par_jour(lignes):
    """Dict date ISO → type dominant (ferie > conges > vacances > pre_rentree > evenement > trimestre > autre)."""
    prio = {"ferie": 7, "conges": 6, "vacances": 5, "pre_rentree": 4, "evenement": 3, "trimestre": 2, "autre": 1}
    out = {}
    for l in sorted(lignes, key=lambda x: prio.get(x.get("type"), 0)):
        d1 = debut_effectif(l)
        d2 = lire_date(l.get("date_fin"))
        if not d1 or not d2 or d1 > d2 or (d2 - d1).days > 400:
            continue
        for d in jours_entre(d1, d2):
            out[d.isoformat()] = (l.get("type"), l.get("libelle"))
    return out


def grille_mois(annee, lignes):
    """Les 12 mois de l'année scolaire (septembre → août) : semaines de 7 cases {num, iso, dans, classe, type, titre}."""
    a = int(annee[:4])
    par_jour = types_par_jour(lignes)
    classe = jours_classe(lignes)
    mois = []
    for i in range(12):
        y, m = (a, 9 + i) if i < 4 else (a + 1, i - 3)
        premier = date(y, m, 1)
        dernier = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        d = premier - timedelta(days=premier.weekday())
        semaines, nb_classe = [], 0
        while d <= dernier or d.weekday() != 0:
            if d.weekday() == 0:
                semaines.append([])
            iso = d.isoformat()
            dans = d.month == m
            typ, titre = par_jour.get(iso, (None, ""))
            est_classe = iso in classe
            if est_classe and dans:
                nb_classe += 1
            if est_classe:
                css = "classe"
            elif typ in TYPES_SANS_CLASSE or typ in ("pre_rentree", "evenement"):
                css = typ
            elif d.weekday() >= 5:
                css = "weekend"
            else:
                css = typ or ""
            semaines[-1].append({"num": d.day, "iso": iso, "dans": dans, "classe": est_classe, "type": typ or "",
                                 "css": css if dans else "", "titre": titre if dans else ""})
            d += timedelta(days=1)
        mois.append({"titre": f"{MOIS[m - 1].capitalize()} {y}", "semaines": semaines, "classe": nb_classe})
    return mois


def lignes_officielles(annee):
    """Lignes officielles d'une année connue (liste de dicts, sans id) ; [] sinon."""
    ref = CALENDRIERS_OFFICIELS.get(annee)
    if not ref:
        return []
    return [{"ordre": (i + 1) * 10, "type": t, "libelle": lib, "date_debut": d1, "date_fin": d2, "precision": prec,
             "duree": dur, "observations": obs, "officiel": 1} for i, (t, lib, d1, d2, prec, dur, obs) in enumerate(ref[2])]


def type_depuis_texte(t):
    """Code de type à partir d'un libellé (import Excel) : « Congés » → conges, « Jour férié » → ferie…"""
    s = (t or "").strip().lower()
    s = s.replace("é", "e").replace("è", "e").replace("ê", "e").replace("-", "_").replace(" ", "_")
    if s in TYPES_LIB:
        return s
    for code, lib in TYPES:
        if s == lib.lower().replace("é", "e").replace("è", "e").replace("ê", "e").replace("-", "_").replace(" ", "_"):
            return code
    if "feri" in s:
        return "ferie"
    if "cong" in s:
        return "conges"
    if "vacan" in s:
        return "vacances"
    if "trim" in s:
        return "trimestre"
    if "rentr" in s:
        return "pre_rentree"
    if "even" in s or "evèn" in s:
        return "evenement"
    return "autre"


def lire_ligne(form):
    """Contrôle d'une ligne (formulaire ou import). Retourne (valeurs, erreurs)."""
    v = {"type": form.get("type") if form.get("type") in TYPES_LIB else "autre",
         "libelle": (form.get("libelle") or "").strip()[:200],
         "date_debut": lire_date(form.get("date_debut")), "date_fin": lire_date(form.get("date_fin") or form.get("date_debut")),
         "precision": (form.get("precision") or "").strip()[:200], "duree": (form.get("duree") or "").strip()[:80],
         "observations": (form.get("observations") or "").strip()[:500]}
    brut = (form.get("ordre") or "").strip()
    v["ordre"] = int(brut) if brut.isdigit() else 0
    err = []
    if not v["libelle"]:
        err.append("Le libellé est obligatoire.")
    if not v["date_debut"]:
        err.append("Date de début invalide (jj/mm/aaaa).")
    if not v["date_fin"]:
        err.append("Date de fin invalide.")
    if v["date_debut"] and v["date_fin"]:
        if v["date_fin"] < v["date_debut"]:
            err.append("La date de fin est antérieure à la date de début.")
        elif (v["date_fin"] - v["date_debut"]).days > 400:
            err.append("Période trop longue (plus d'un an).")
    if not err:
        v["date_debut"], v["date_fin"] = v["date_debut"].isoformat(), v["date_fin"].isoformat()
    return v, err


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    def uid():
        return g.user["id"] if g.get("user") else None

    def peut_modifier():
        return H.peut("calendrier_officiel")

    def ecriture():
        if not peut_modifier():
            abort(403)

    def retour_choisi():
        r = request.values.get("retour") or ""
        return r if r in ("synoptique", "jur_synoptique") else ""

    def ecole_cible():
        """École dont on affiche le calendrier : l'école courante ; 0 = calendrier commun de la structure
        (CS / DDEMP sans école ouverte, onglet du synoptique de la structure, ou ?portee=structure)."""
        if config.juridiction():
            if retour_choisi() == "jur_synoptique" or request.values.get("portee") == "structure" or not g.get("ecole"):
                return 0
        return H.eco()

    def annee_choisie():
        return annee_valide(request.values.get("annee"), config.ANNEE_ACTIVE)

    def params_retour(**extra):
        p = {"annee": annee_choisie()}
        if retour_choisi():
            p["retour"] = retour_choisi()
        if request.values.get("portee") == "structure":
            p["portee"] = "structure"
        p.update(extra)
        return p

    def url_liste(**extra):
        return url_for("calendrier_officiel", **params_retour(**extra))

    # ------------------------------------------------------------ données
    def lignes(annee, ecole_id):
        return [dict(r) for r in q("SELECT * FROM calendrier_officiel WHERE ecole_id=? AND annee=? ORDER BY date_debut, ordre, id",
                                   (ecole_id, annee))]

    def inserer(ecole_id, annee, l, officiel=None):
        return ex("INSERT INTO calendrier_officiel (ecole_id, annee, ordre, type, libelle, date_debut, date_fin, precision, duree, "
                  "observations, officiel, maj, maj_par) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (ecole_id, annee, l.get("ordre") or 0, l["type"], l["libelle"], l["date_debut"], l["date_fin"],
                   l.get("precision") or "", l.get("duree") or "", l.get("observations") or "",
                   int(l.get("officiel") or 0) if officiel is None else officiel, H.maintenant(), uid()))

    def ecrire_meta(ecole_id, annee, reference, source):
        ex("INSERT INTO calendrier_officiel_meta (ecole_id, annee, reference_arrete, source, maj) VALUES (?,?,?,?,?) "
           "ON CONFLICT(ecole_id, annee) DO UPDATE SET reference_arrete=excluded.reference_arrete, source=excluded.source, maj=excluded.maj",
           (ecole_id, annee, reference, source, H.maintenant()))

    def meta(ecole_id, annee):
        r = q("SELECT * FROM calendrier_officiel_meta WHERE ecole_id=? AND annee=?", (ecole_id, annee), un=True)
        return dict(r) if r else {"reference_arrete": "", "source": ""}

    def remettre_officiel(ecole_id, annee):
        """Insère les lignes officielles de l'année (si connue) ; retourne le nombre inséré."""
        offi = lignes_officielles(annee)
        for l in offi:
            inserer(ecole_id, annee, l, officiel=1)
        if offi:
            ref = CALENDRIERS_OFFICIELS[annee]
            ecrire_meta(ecole_id, annee, ref[0], ref[1])
        return len(offi)

    def lignes_preremplies(annee, ecole_id):
        """Lignes de l'année ; le calendrier officiel est inséré à la première ouverture d'une année connue."""
        lst = lignes(annee, ecole_id)
        if not lst and annee in CALENDRIERS_OFFICIELS and g.get("user"):
            remettre_officiel(ecole_id, annee)
            lst = lignes(annee, ecole_id)
        return lst

    def annees_disponibles(ecole_id):
        pres = {r["annee"] for r in q("SELECT DISTINCT annee FROM calendrier_officiel WHERE ecole_id=?", (ecole_id,))}
        pres |= {config.ANNEE_ACTIVE, annee_suivante(config.ANNEE_ACTIVE)} | set(CALENDRIERS_OFFICIELS)
        return sorted(pres)

    def ligne_ou_404(lid, annee, ecole_id):
        r = q("SELECT * FROM calendrier_officiel WHERE id=? AND ecole_id=? AND annee=?", (lid, ecole_id, annee), un=True)
        if not r:
            abort(404)
        return dict(r)

    # ---- exposé aux autres modules
    def calendrier_officiel_api(annee, ecole_id):
        lst = lignes(annee, ecole_id)
        return lst or lignes_officielles(annee)

    def calendrier_jours_classe_api(annee, ecole_id):
        return jours_classe(calendrier_officiel_api(annee, ecole_id))

    H.calendrier_officiel = calendrier_officiel_api
    H.calendrier_jours_classe = calendrier_jours_classe_api

    # ------------------------------------------------------------ contexte des gabarits
    def identite_synoptique(ecole_id):
        f = getattr(H, "synoptique_identite", None)
        d = {x["cle"]: x["valeur"] for x in f(ecole_id)} if f else {}
        e = q("SELECT * FROM ecoles WHERE id=?", (ecole_id,), un=True)
        d.setdefault("epp", (e["nom"] if e else "") or "")
        d["cs"] = (e["cs"] if e else "") or ""
        return d

    def nom_cible(ecole_id):
        if ecole_id == 0:
            s = H.jur_structure() if getattr(H, "jur_structure", None) and config.juridiction() else None
            return (s or {}).get("nom") or ("DDEMP" if config.EDITION == "ddemp" else "Circonscription scolaire")
        e = q("SELECT nom FROM ecoles WHERE id=?", (ecole_id,), un=True)
        return (e["nom"] if e else "") or config.ECOLE.get("nom", "")

    def ctx(annee, ecole_id, **extra):
        retour = retour_choisi()
        d = dict(annee=annee, ecole_id=ecole_id, retour=retour, portee=request.values.get("portee") or "",
                 modifiable=peut_modifier(), TYPES=TYPES, TYPES_LIB=TYPES_LIB, COULEURS=COULEURS,
                 date_longue=date_longue, date_courte=date_courte, nom_cible=nom_cible(ecole_id),
                 structure=(ecole_id == 0), ecole_ouverte=bool(g.get("ecole")), juridiction=config.juridiction(),
                 annees=annees_disponibles(ecole_id), annee_suiv=annee_suivante(annee),
                 officiel_connu=annee in CALENDRIERS_OFFICIELS, meta=meta(ecole_id, annee), params=params_retour())
        if retour == "synoptique":
            d.update(onglet="calendrier", ident=identite_synoptique(ecole_id), ecrire=H.peut("synoptique"))
        elif retour == "jur_synoptique" and getattr(H, "jur_synoptique_identite", None):
            d.update(onglet="calendrier", ident=H.jur_synoptique_identite(), ecrire=H.peut("jur_synoptique"),
                     ddemp=config.EDITION == "ddemp")
        else:
            d["retour"] = ""
        d.update(extra)
        return d

    # adresses : préfixe « /juridiction » d'abord dans les applications CS / DDEMP (adresse de la structure,
    # accessible sans école ouverte) ; les deux adresses existent dans toutes les éditions
    def routes(suffixe, **k):
        chemins = ["/calendrier-scolaire" + suffixe, "/juridiction/calendrier-scolaire" + suffixe]
        if config.juridiction():
            chemins.reverse()

        def deco(f):
            for c in chemins:
                f = app.route(c, **k)(f)
            return f
        return deco

    # ============================================================ pages
    @routes("")
    @H.connexion_requise()
    def calendrier_officiel():
        annee, eid = annee_choisie(), ecole_cible()
        lst = lignes_preremplies(annee, eid)
        vue = "calendrier" if request.args.get("vue") == "calendrier" else "liste"
        stats = stats_trimestres(lst)
        total = len(jours_classe(lst))
        return render_template("calendrier_officiel.html", **ctx(annee, eid, lst=lst, vue=vue, stats=stats, total=total,
                                                                  total_txt=semaines_texte(total),
                                                                  mois=grille_mois(annee, lst) if vue == "calendrier" else []))

    @routes("/ligne/<int:lid>", methods=["GET", "POST"])
    @H.connexion_requise("calendrier_officiel")
    def calendrier_officiel_form(lid):
        annee, eid = annee_choisie(), ecole_cible()
        l = ligne_ou_404(lid, annee, eid) if lid else None
        if request.method == "POST":
            v, err = lire_ligne(request.form)
            if err:
                for e in err:
                    flash(e, "danger")
                return render_template("calendrier_officiel_form.html", **ctx(annee, eid, l=l, v=v)), 400
            if l:
                ex("UPDATE calendrier_officiel SET ordre=?, type=?, libelle=?, date_debut=?, date_fin=?, precision=?, duree=?, "
                   "observations=?, maj=?, maj_par=? WHERE id=?",
                   (v["ordre"], v["type"], v["libelle"], v["date_debut"], v["date_fin"], v["precision"], v["duree"], v["observations"],
                    H.maintenant(), uid(), l["id"]))
                H.journal("calendrier_officiel", f"{annee} : ligne modifiée « {v['libelle']} »")
                flash("Période modifiée.", "success")
            else:
                inserer(eid, annee, v, officiel=0)
                H.journal("calendrier_officiel", f"{annee} : ligne ajoutée « {v['libelle']} »")
                flash("Période ajoutée.", "success")
            return redirect(url_liste())
        v = dict(l) if l else {"type": "ferie", "date_debut": "", "date_fin": ""}
        return render_template("calendrier_officiel_form.html", **ctx(annee, eid, l=l, v=v))

    @routes("/ligne/<int:lid>/supprimer", methods=["POST"])
    @H.connexion_requise("calendrier_officiel")
    def calendrier_officiel_supprimer(lid):
        annee, eid = annee_choisie(), ecole_cible()
        l = ligne_ou_404(lid, annee, eid)
        ex("DELETE FROM calendrier_officiel WHERE id=?", (l["id"],))
        H.journal("calendrier_officiel", f"{annee} : ligne supprimée « {l['libelle']} »")
        flash("Période supprimée.", "warning")
        return redirect(url_liste())

    @routes("/recharger", methods=["POST"])
    @H.connexion_requise("calendrier_officiel")
    def calendrier_officiel_recharger():
        """Remet les lignes officielles de l'année (les lignes ajoutées par l'utilisateur sont conservées)."""
        annee, eid = annee_choisie(), ecole_cible()
        if annee not in CALENDRIERS_OFFICIELS:
            flash(f"Le calendrier officiel {annee} n'est pas connu de GESCOL : saisissez-le ou importez-le.", "danger")
            return redirect(url_liste())
        ex("DELETE FROM calendrier_officiel WHERE ecole_id=? AND annee=? AND officiel=1", (eid, annee))
        n = remettre_officiel(eid, annee)
        H.journal("calendrier_officiel", f"{annee} : calendrier officiel rechargé ({n} lignes)")
        flash(f"Calendrier officiel {annee} rechargé ({n} lignes officielles ; vos ajouts sont conservés).", "success")
        return redirect(url_liste())

    @routes("/reinitialiser", methods=["POST"])
    @H.connexion_requise("calendrier_officiel")
    def calendrier_officiel_reinitialiser():
        """Supprime toutes les lignes de l'année puis remet le calendrier officiel (s'il est connu)."""
        annee, eid = annee_choisie(), ecole_cible()
        ex("DELETE FROM calendrier_officiel WHERE ecole_id=? AND annee=?", (eid, annee))
        n = remettre_officiel(eid, annee)
        if not n:
            ex("DELETE FROM calendrier_officiel_meta WHERE ecole_id=? AND annee=?", (eid, annee))
        H.journal("calendrier_officiel", f"{annee} : calendrier réinitialisé ({n} lignes officielles)")
        flash(f"Calendrier {annee} réinitialisé" + (f" : {n} lignes officielles remises." if n else " (année sans calendrier officiel connu : vide)."),
              "success")
        return redirect(url_liste())

    @routes("/preparer", methods=["POST"])
    @H.connexion_requise("calendrier_officiel")
    def calendrier_officiel_preparer():
        """Prépare l'année suivante : copie des lignes de l'année affichée décalées d'un an (à corriger ensuite)."""
        annee, eid = annee_choisie(), ecole_cible()
        suiv = annee_suivante(annee)
        if lignes(suiv, eid):
            flash(f"L'année {suiv} contient déjà des lignes : réinitialisez-la d'abord si vous voulez la refaire.", "danger")
            return redirect(url_liste(annee=suiv))
        src = lignes(annee, eid)
        for l in src:
            c = dict(l, date_debut=decaler_un_an(l["date_debut"]), date_fin=decaler_un_an(l["date_fin"]),
                     precision=re.sub(r"\b(20\d\d)\b", lambda m: str(int(m.group(1)) + 1), l.get("precision") or ""))
            inserer(eid, suiv, c, officiel=0)
        ecrire_meta(eid, suiv, f"À compléter : calendrier {suiv} préparé à partir de {annee} (dates décalées d'un an)", "")
        H.journal("calendrier_officiel", f"{suiv} préparé à partir de {annee} ({len(src)} lignes)")
        flash(f"Année {suiv} préparée à partir de {annee} ({len(src)} lignes, dates décalées d'un an) : "
              "corrigez les jours (lundi, vendredi…) et la référence de l'arrêté dès sa parution.", "success")
        return redirect(url_liste(annee=suiv))

    @routes("/meta", methods=["POST"])
    @H.connexion_requise("calendrier_officiel")
    def calendrier_officiel_meta():
        annee, eid = annee_choisie(), ecole_cible()
        ecrire_meta(eid, annee, (request.form.get("reference_arrete") or "").strip()[:400], (request.form.get("source") or "").strip()[:200])
        H.journal("calendrier_officiel", f"{annee} : référence du texte modifiée")
        flash("Référence enregistrée.", "success")
        return redirect(url_liste())

    # ============================================================ passerelle avec le registre (jours de classe)
    @routes("/appliquer-registre", methods=["POST"])
    @H.connexion_requise("calendrier_officiel")
    def calendrier_officiel_registre():
        """Écrit le calendrier dans le calendrier des jours de classe du registre de l'école ouverte (m_registre) :
        rentrée / fin des cours (document registre:calendrier) et jours sans classe (table jours_classe, 0 demi-journée)."""
        annee, eid = annee_choisie(), ecole_cible()
        if not g.get("ecole") or not getattr(H, "doc_ecrire", None):
            flash("Aucune école ouverte : le registre des présences est propre à une école.", "danger")
            return redirect(url_liste())
        cible = H.eco()
        lst = lignes(annee, eid)
        trimestres = sorted([l for l in lst if l["type"] == "trimestre"], key=lambda l: l["date_debut"])
        if not trimestres:
            flash("Aucun trimestre dans le calendrier : rien à appliquer.", "danger")
            return redirect(url_liste())
        rentree, fin = lire_date(trimestres[0]["date_debut"]), lire_date(trimestres[-1]["date_fin"])
        H.doc_ecrire(f"e{cible}:registre:calendrier:{annee}", {"rentree": rentree.isoformat(), "fin": fin.isoformat()})
        n = 0
        for l in lst:
            if l["type"] not in TYPES_SANS_CLASSE:
                continue
            d1, d2 = debut_effectif(l), lire_date(l["date_fin"])
            for d in jours_entre(max(d1, rentree), min(d2, fin)):
                if d.weekday() < 5:     # on ne marque que les jours normalement travaillés (règle de m_registre)
                    ex("INSERT INTO jours_classe (ecole_id, date, demi_journees, motif) VALUES (?,?,?,?) "
                       "ON CONFLICT(ecole_id, date) DO UPDATE SET demi_journees=excluded.demi_journees, motif=excluded.motif",
                       (cible, d.isoformat(), 0, l["libelle"][:80]))
                    n += 1
        H.journal("calendrier_officiel", f"{annee} : appliqué au registre de l'école {cible} ({n} jours sans classe)")
        flash(f"Calendrier appliqué au registre : rentrée le {date_courte(rentree)}, fin des cours le {date_courte(fin)}, "
              f"{n} jour(s) sans classe marqué(s).", "success")
        return redirect(url_liste())

    # ============================================================ Excel
    def lignes_xlsx(lst):
        return [[TYPES_LIB.get(l["type"], l["type"]), l["libelle"], l["date_debut"], l["date_fin"], l.get("precision") or "",
                 l.get("duree") or "", l.get("observations") or "", "Oui" if l.get("officiel") else "Non"] for l in lst]

    @routes("/export.xlsx")
    @H.connexion_requise()
    def calendrier_officiel_xlsx():
        import outils_xlsx as X
        annee, eid = annee_choisie(), ecole_cible()
        lst = lignes_preremplies(annee, eid)
        m = meta(eid, annee)
        titre = [f"Calendrier scolaire {annee} — {nom_cible(eid)}", m.get("reference_arrete") or ""]
        st = [["Trimestre", "Du", "Au", "Jours de classe", "Semaines (calcul)", "Durée officielle"]] + [
            [s["libelle"], s["du"].isoformat() if s["du"] else "", s["au"].isoformat() if s["au"] else "", s["jours"], s["semaines"],
             s["duree_officielle"]] for s in stats_trimestres(lst)]
        feuilles = [("Calendrier", ENTETES_XLSX, lignes_xlsx(lst), {"titre_haut": titre}),
                    ("Jours de classe", st[0], st[1:], {"titre_haut": [f"Jours de classe {annee} (lundi–vendredi hors congés et fériés)"]})]
        return X.reponse_classeur(f"calendrier_scolaire_{annee}.xlsx", feuilles)

    @routes("/modele.xlsx")
    @H.connexion_requise()
    def calendrier_officiel_modele_xlsx():
        import outils_xlsx as X
        annee = annee_choisie()
        exemple = lignes_officielles("2026-2027")[:4]
        return X.reponse_xlsx(f"modele_calendrier_scolaire.xlsx", ENTETES_XLSX, lignes_xlsx(exemple), titre="Calendrier",
                              titre_haut=[f"Modèle d'import du calendrier scolaire ({annee})",
                                          "Types : " + ", ".join(l for _c, l in TYPES) + " — dates au format jj/mm/aaaa ou aaaa-mm-jj"])

    @routes("/import", methods=["GET", "POST"])
    @H.connexion_requise("calendrier_officiel")
    def calendrier_officiel_import():
        import outils_xlsx as X
        annee, eid = annee_choisie(), ecole_cible()
        if request.method == "POST":
            f = request.files.get("fichier")
            if not f or not f.filename:
                flash("Choisissez un fichier Excel.", "danger")
                return redirect(url_for("calendrier_officiel_import", **params_retour()))
            try:
                entetes, brutes = X.lire_tableau(f, mots_entete=("libelle", "libellé", "type"))
            except (ValueError, X.ExcelIndisponible) as e:
                flash(str(e), "danger")
                return redirect(url_for("calendrier_officiel_import", **params_retour()))
            c = {k: X.colonne(entetes, *cands) for k, cands in {
                "type": ("type",), "libelle": ("libelle", "libellé", "periode", "période"), "date_debut": ("date de debut", "debut", "du"),
                "date_fin": ("date de fin", "fin", "au"), "precision": ("precision", "précision"), "duree": ("duree", "durée"),
                "observations": ("observations", "observation"), "officiel": ("officiel",)}.items()}
            if c["libelle"] is None or c["date_debut"] is None:
                flash("Colonnes « Libellé » et « Date de début » introuvables : utilisez le modèle.", "danger")
                return redirect(url_for("calendrier_officiel_import", **params_retour()))
            nouvelles, erreurs = [], []
            for i, r in enumerate(brutes, 1):
                v, err = lire_ligne({
                    "type": type_depuis_texte(X.valeur(r, c["type"])), "libelle": X.valeur(r, c["libelle"]),
                    "date_debut": X.date_iso(r[c["date_debut"]] if c["date_debut"] < len(r) else ""),
                    "date_fin": X.date_iso(r[c["date_fin"]] if c["date_fin"] is not None and c["date_fin"] < len(r) else "") or
                    X.date_iso(r[c["date_debut"]] if c["date_debut"] < len(r) else ""),
                    "precision": X.valeur(r, c["precision"]), "duree": X.valeur(r, c["duree"]),
                    "observations": X.valeur(r, c["observations"]), "ordre": str(i * 10)})
                if err:
                    erreurs.append(f"ligne {i} ({v['libelle'] or '?'}) : {' '.join(err)}")
                    continue
                v["officiel"] = 1 if X.valeur(r, c["officiel"]).strip().lower() in ("oui", "1", "x", "o") else 0
                nouvelles.append(v)
            if erreurs:
                for e in erreurs[:10]:
                    flash(e, "danger")
                flash("Import annulé : corrigez le fichier.", "danger")
                return redirect(url_for("calendrier_officiel_import", **params_retour()))
            if not nouvelles:
                flash("Aucune ligne à importer.", "danger")
                return redirect(url_for("calendrier_officiel_import", **params_retour()))
            ex("DELETE FROM calendrier_officiel WHERE ecole_id=? AND annee=?", (eid, annee))
            for v in nouvelles:
                inserer(eid, annee, v)
            ref = (request.form.get("reference_arrete") or "").strip()[:400]
            if ref:
                ecrire_meta(eid, annee, ref, (request.form.get("source") or "").strip()[:200])
            H.journal("calendrier_officiel", f"{annee} : import Excel ({len(nouvelles)} lignes)")
            flash(f"{len(nouvelles)} ligne(s) importée(s) pour {annee} (les lignes précédentes ont été remplacées).", "success")
            return redirect(url_liste())
        return render_template("calendrier_officiel_import.html", **ctx(annee, eid, entetes=ENTETES_XLSX))

    # ============================================================ PDF
    @routes("/calendrier.pdf")
    @H.connexion_requise()
    def calendrier_officiel_pdf():
        P = H.pdfs
        annee, eid = annee_choisie(), ecole_cible()
        lst = lignes_preremplies(annee, eid)
        m = meta(eid, annee)
        lignes_pdf = [[TYPES_LIB.get(l["type"], l["type"]), l["libelle"], date_longue(l["date_debut"]),
                       date_longue(l["date_fin"]) if l["date_fin"] != l["date_debut"] else "—",
                       l.get("precision") or "", l.get("duree") or "", l.get("observations") or ""] for l in lst]
        surl = {i: COULEURS.get(l["type"], "#FFFFFF") for i, l in enumerate(lst) if l["type"] in TYPES_SANS_CLASSE or l["type"] == "pre_rentree"}
        total = len(jours_classe(lst))
        apres = [P.paragraphe("<b>Jours de classe calculés</b> (lundi → vendredi dans les trimestres, hors congés et jours fériés saisis) :", 8, espace=4)]
        apres.append(P.mini_tableau([["Trimestre", "Du", "Au", "Jours", "Semaines (calcul)", "Durée officielle"]] + [
            [s["libelle"], date_courte(s["du"]), date_courte(s["au"]), str(s["jours"]), s["semaines"], s["duree_officielle"]]
            for s in stats_trimestres(lst)] + [["Total", "", "", str(total), semaines_texte(total), ""]], taille=7.5))
        infos_haut = None
        if eid == 0 and config.juridiction():
            s = H.jur_structure() or {}
            infos_haut = [("DDEMP", s.get("departement") or "—")] + ([] if config.EDITION == "ddemp" else [("CS", s.get("cs") or "—")])
        notes = [f"Référence : {m.get('reference_arrete')}" if m.get("reference_arrete") else "Référence du texte : à compléter."]
        if m.get("source"):
            notes.append(f"Source : {m['source']}")
        notes.append("Les lignes colorées sont les périodes sans classe (congés, jours fériés, vacances) et la pré-rentrée. "
                     "Les autres jours fériés déclarés par le Ministre chargé de la Fonction publique sont à ajouter.")
        pdf = P.document_tableau(f"CALENDRIER DE L'ANNÉE SCOLAIRE {annee}", ["Type", "Période", "Du", "Au", "Précision", "Durée", "Observations"],
                                 lignes_pdf, sous_titre=f"{nom_cible(eid)} — édité le {date.today().strftime('%d/%m/%Y')}",
                                 largeurs=[14, 30, 24, 24, 30, 16, 26], paysage=False, taille=7.2, surlignes=surl, apres=apres,
                                 notes_bas=notes, infos_haut=infos_haut)
        H.journal("calendrier_officiel", f"{annee} : PDF")
        return H.pdf_reponse(pdf, f"calendrier_scolaire_{annee}.pdf")
