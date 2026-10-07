# -*- coding: utf-8 -*-
"""
Gestion de carrière des enseignants (édition « École publique ») et tableau de bord du directeur.

* Données : table `personnel_carriere` (une ligne par agent) + colonnes `personnel.nip`,
  `personnel.date_naissance` (« AAAA-MM-JJ » ou « AAAA » si seule l'année est connue) et
  `personnel.user_id` (compte utilisateur de l'agent, pour son espace « Mon espace »).
* Les renseignements sont saisis par le directeur dans la fiche du personnel (m_paie → personnel_form,
  qui appelle H.carriere en édition publique). L'enseignant consulte sa propre fiche et peut PROPOSER
  ses diplômes (académique, CEAP, CAP) : le directeur valide ou rejette la proposition.

Règles de calcul (documentées aussi à l'écran) :
* Date de référence des anciennetés : le 31 décembre de la PREMIÈRE année de l'année scolaire en cours
  (année active « 2026-2027 » → 31/12/2026 ; si l'année active est illisible : 31/12 de l'année civile courante).
* Anciennetés (générale, département, commune, école) : de la date de prise de service dans chaque lieu
  jusqu'à la date de référence, en années et mois révolus, en comptant le 31/12 inclus
  (du 01/01/2020 au 31/12/2026 = 7 ans 0 mois ; du 29/02/2024 = 2 ans 10 mois).
* Date de départ à la retraite : selon le grade et l'année de naissance — âge limite A = 60 ans, B = 58 ans,
  C = 55 ans (la lettre du grade donne la catégorie : A1-5 → A). Le départ a lieu le PREMIER JOUR DU MOIS
  DU TRIMESTRE QUI SUIT le trimestre de naissance : né(e) de janvier à mars → 1er avril ; d'avril à juin →
  1er juillet ; de juillet à septembre → 1er octobre ; d'octobre à décembre → 1er janvier de l'année suivante.
  Exemples : né(e) le 15/02/1967, grade A → 01/04/2027 ; né(e) le 28/02/1969, grade B → 01/04/2027 ;
  né(e) le 10/11/1970, grade C → 01/01/2026.
  Si seule l'année de naissance est connue, le trimestre est inconnu : on retient l'hypothèse la plus
  prudente, le 1er janvier de l'année (naissance + âge + 1), c'est-à-dire la date la plus tardive possible.
  Alerte si le départ intervient dans 2 ans ou moins (ou est déjà atteint).
"""
import json
import re
import types
from datetime import date, datetime, timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

import config

# ---------------------------------------------------------------- référentiels
CATEGORIES = [("FE", "FE"), ("ACDPE", "ACDPE"), ("ACDPCTD", "ACDPCTD (AME)")]
CATEGORIES_LIB = dict(CATEGORIES)
# grades : A1-1 … A3-15, B1-1 … B3-15, C1-1 … C3-15 (liste proposée ; la saisie reste libre)
GRADES = [f"{l}{n}-{e}" for l in "ABC" for n in (1, 2, 3) for e in range(1, 16)]
AGES_RETRAITE = {"A": 60, "B": 58, "C": 55}
DEPARTEMENTS = ["Alibori", "Atacora", "Atlantique", "Borgou", "Collines", "Couffo", "Donga", "Littoral",
                "Mono", "Ouémé", "Plateau", "Zou"]
DIPLOMES = ["CEP", "BEPC", "BAC", "DEUG", "DUT / BTS", "Licence", "Maîtrise", "Master", "Doctorat"]
# champs que l'enseignant peut proposer lui-même (validés ensuite par le directeur)
CHAMPS_ENSEIGNANT = ["diplome_academique", "diplome_academique_annee", "ceap", "ceap_annee", "cap", "cap_annee"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS personnel_carriere (
    personnel_id INTEGER PRIMARY KEY REFERENCES personnel(id),
    categorie TEXT,                       -- FE | ACDPE | ACDPCTD (AME)
    grade TEXT,                           -- ex. A1-5, B1-12, C1-3
    indice_paye INTEGER,
    indice_reel INTEGER,
    date_prise_service TEXT,              -- première prise de service (ISO)
    date_service_dep TEXT,                -- prise de service dans le département
    date_service_commune TEXT,
    date_service_ecole TEXT,
    diplome_academique TEXT,
    diplome_academique_annee INTEGER,
    ceap TEXT,                            -- oui | non | ''
    ceap_annee INTEGER,
    cap TEXT,
    cap_annee INTEGER,
    visite_aptitude TEXT,                 -- oui | non | ''
    visite_aptitude_note REAL,            -- /20
    departement_servir TEXT,
    visites_cp INTEGER,
    visites_ccs INTEGER,
    participation_up REAL,                -- pourcentage 0-100
    gestion_collegiale TEXT,
    note_evaluation REAL,                 -- /20
    propositions TEXT,                    -- JSON : diplômes proposés par l'enseignant, en attente
    propose_le TEXT,
    maj TEXT,
    maj_par INTEGER
);
"""

# libellés des champs (formulaire, fiche, dossiers incomplets)
LIBELLES = {
    "nip": "NIP", "categorie": "Catégorie", "grade": "Grade", "indice_paye": "Indice payé",
    "indice_reel": "Indice réel", "date_naissance": "Date de naissance",
    "date_prise_service": "Date de première prise de service",
    "date_service_dep": "Prise de service dans le département",
    "date_service_commune": "Prise de service dans la commune",
    "date_service_ecole": "Prise de service dans l'école",
    "diplome_academique": "Diplôme académique le plus élevé", "diplome_academique_annee": "Année du diplôme académique",
    "ceap": "CEAP", "ceap_annee": "Année du CEAP", "cap": "CAP", "cap_annee": "Année du CAP",
    "visite_aptitude": "Visite d'aptitude", "visite_aptitude_note": "Note de la visite d'aptitude",
    "departement_servir": "Département à servir", "visites_cp": "Visites de classe du CP",
    "visites_ccs": "Visites de classe du CCS", "participation_up": "Participation à l'UP (%)",
    "gestion_collegiale": "Gestion collégiale (responsabilités)", "note_evaluation": "Note d'évaluation du personnel",
}
# indispensables pour qu'un dossier soit « complet »
REQUIS = ["nip", "categorie", "grade", "date_naissance", "date_prise_service", "date_service_ecole",
          "diplome_academique"]
DATES = ["date_prise_service", "date_service_dep", "date_service_commune", "date_service_ecole"]
ANCIENNETES = [("generale", "date_prise_service", "Ancienneté générale"),
               ("departement", "date_service_dep", "Ancienneté dans le département"),
               ("commune", "date_service_commune", "Ancienneté dans la commune"),
               ("ecole", "date_service_ecole", "Ancienneté dans l'école")]


# ---------------------------------------------------------------- calculs (fonctions pures, testables)
def lire_date(txt):
    """« 15/09/2020 », « 15-09-2020 » ou « 2020-09-15 » -> '2020-09-15' ; '' -> None ; ValueError sinon."""
    txt = (txt or "").strip()
    if not txt:
        return None
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", txt)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    return date.fromisoformat(txt).isoformat()


def lire_naissance(txt):
    """Date complète (voir lire_date) ou année seule « 1968 » -> '1968'."""
    txt = (txt or "").strip()
    if re.fullmatch(r"\d{4}", txt):
        return txt
    return lire_date(txt)


def en_date(iso):
    try:
        return date.fromisoformat(iso) if iso and len(iso) == 10 else None
    except ValueError:
        return None


def annee_scolaire_debut(annee=None, auj=None):
    """« 2026-2027 » -> 2026 ; année illisible -> année civile de `auj` (aujourd'hui)."""
    m = re.match(r"\s*(\d{4})", str(annee if annee is not None else getattr(config, "ANNEE_ACTIVE", "") or ""))
    if m and 1990 <= int(m.group(1)) <= 2100:
        return int(m.group(1))
    return (auj or date.today()).year


def date_reference(auj=None, annee=None):
    """Anciennetés arrêtées au 31 décembre de la première année de l'année scolaire active
    (« 2026-2027 » -> 31/12/2026) ; si l'année active est illisible : 31/12 de l'année civile en cours."""
    return date(annee_scolaire_debut(annee, auj), 12, 31)


def mois_ecoules(debut, fin):
    """Nombre de mois révolus de `debut` (inclus) à `fin` (exclu)."""
    n = (fin.year - debut.year) * 12 + fin.month - debut.month
    if fin.day < debut.day:
        n -= 1
    return n


def anciennete(debut, ref):
    """(ans, mois) du `debut` au `ref` INCLUS ; None si inconnue ou postérieure à la référence."""
    debut = en_date(debut) if isinstance(debut, str) else debut
    if not debut or debut > ref:
        return None
    return divmod(mois_ecoules(debut, ref + timedelta(days=1)), 12)


def lettre_grade(grade):
    """« a1-5 » -> 'A' ; « B » -> 'B' ; grade inconnu -> None."""
    g_ = (grade or "").strip().upper()
    return g_[0] if g_ and g_[0] in AGES_RETRAITE else None


def date_retraite(naissance, grade):
    """Date de départ à la retraite (date) ou None.
    Année = année de naissance + âge du grade (A 60, B 58, C 55) ; jour = 1er jour du mois qui ouvre le
    trimestre SUIVANT le trimestre de naissance : janv–mars -> 1er avril, avril–juin -> 1er juillet,
    juil–sept -> 1er octobre, oct–déc -> 1er janvier de l'année suivante.
    Année de naissance seule (« 1968 ») : trimestre inconnu -> 1er janvier de (année + âge + 1)."""
    age = AGES_RETRAITE.get(lettre_grade(grade))
    if not age or not naissance:
        return None
    if isinstance(naissance, date):
        n = naissance
    elif re.fullmatch(r"\d{4}", naissance):
        return date(int(naissance) + age + 1, 1, 1)
    else:
        n = en_date(naissance)
    if not n:
        return None
    trimestre = (n.month - 1) // 3            # 0..3
    if trimestre == 3:
        return date(n.year + age + 1, 1, 1)
    return date(n.year + age, 3 * (trimestre + 1) + 1, 1)


def plus_ans(d, ans):
    try:
        return d.replace(year=d.year + ans)
    except ValueError:
        return d.replace(year=d.year + ans, day=28)


def fmt_duree(t, court=False):
    """(6, 3) -> « 6 ans 3 mois » (court : « 6 a 3 m »)."""
    if t is None:
        return "—"
    a, m = t
    if court:
        return f"{a} a {m} m"
    if not a and not m:
        return "moins d'un mois"
    morceaux = []
    if a:
        morceaux.append(f"{a} an{'s' if a > 1 else ''}")
    if m or not a:
        morceaux.append(f"{m} mois")
    return " ".join(morceaux)


def fmt_date(iso):
    if not iso:
        return ""
    if isinstance(iso, date):
        return iso.strftime("%d/%m/%Y")
    if re.fullmatch(r"\d{4}", iso):
        return f"(année) {iso}"
    d = en_date(iso)
    return d.strftime("%d/%m/%Y") if d else iso


def fmt_nombre(v, suffixe=""):
    if v is None or v == "":
        return ""
    if isinstance(v, float):
        v = int(v) if v.is_integer() else str(v).replace(".", ",")
    return f"{v}{suffixe}"


def calculer_fiche(ligne, auj=None):
    """Ligne personnel + personnel_carriere (dict) -> dict enrichi des valeurs calculées."""
    auj = auj or date.today()
    ref = date_reference(auj)
    f = dict(ligne)
    f["nom_complet"] = f"{f.get('nom') or ''} {f.get('prenoms') or ''}".strip()
    f["categorie_lib"] = CATEGORIES_LIB.get(f.get("categorie") or "", f.get("categorie") or "")
    f["reference"] = ref
    f["anc"], f["anc_txt"] = {}, {}
    for cle, champ, _lib in ANCIENNETES:
        t = anciennete(f.get(champ), ref)
        f["anc"][cle] = t
        f["anc_txt"][cle] = fmt_duree(t)
    lettre = lettre_grade(f.get("grade"))
    f["lettre_grade"] = lettre
    f["age_retraite"] = AGES_RETRAITE.get(lettre)
    ret = date_retraite(f.get("date_naissance"), f.get("grade"))
    f["retraite"] = ret
    f["retraite_txt"] = fmt_date(ret) if ret else ""
    f["retraite_atteinte"] = bool(ret and ret <= auj)
    f["alerte_retraite"] = bool(ret and ret <= plus_ans(auj, 2))
    if ret and not f["retraite_atteinte"]:
        f["restant"] = divmod(mois_ecoules(auj, ret), 12)
        f["restant_txt"] = fmt_duree(f["restant"])
    else:
        f["restant"] = None
        f["restant_txt"] = "départ atteint" if ret else ""
    if not ret:
        f["retraite_raison"] = ("grade non renseigné ou hors catégories A, B, C" if not lettre
                                else "date de naissance non renseignée")
    f["naissance_txt"] = fmt_date(f.get("date_naissance"))
    f["aptitude_manquante"] = (f.get("visite_aptitude") or "") != "oui"
    f["manquants"] = [LIBELLES[k] for k in REQUIS if f.get(k) in (None, "")]
    f["incomplet"] = bool(f["manquants"])
    try:
        f["propositions_d"] = json.loads(f["propositions"]) if f.get("propositions") else None
    except ValueError:
        f["propositions_d"] = None
    return f


def lire_formulaire(form, auj=None):
    """Champs de carrière d'un formulaire -> (valeurs, erreurs). Valeurs prêtes à enregistrer."""
    auj = auj or date.today()
    v, err = {}, []

    def texte(k, n=120):
        return (form.get(k) or "").strip()[:n]

    def entier(k, mini, maxi):
        brut = texte(k).replace(" ", "")
        if not brut:
            return None
        try:
            x = int(brut)
            if not mini <= x <= maxi:
                raise ValueError
            return x
        except ValueError:
            err.append(f"{LIBELLES[k]} : valeur invalide (entier de {mini} à {maxi}).")
            return None

    def decimal(k, mini, maxi):
        brut = texte(k).replace(" ", "").replace(",", ".").rstrip("%")
        if not brut:
            return None
        try:
            x = float(brut)
            if not mini <= x <= maxi:
                raise ValueError
            return x
        except ValueError:
            err.append(f"{LIBELLES[k]} : valeur invalide ({mini} à {maxi}).")
            return None

    v["nip"] = texte("nip", 30)
    v["categorie"] = texte("categorie", 20)
    if v["categorie"] and v["categorie"] not in CATEGORIES_LIB:
        err.append("Catégorie invalide : choisissez FE, ACDPE ou ACDPCTD (AME).")
    v["grade"] = texte("grade", 20).upper().replace(" ", "")
    if v["grade"] and not re.fullmatch(r"[A-Z][A-Z0-9-]{0,19}", v["grade"]):
        err.append("Grade invalide (exemples : A1-5, B1-12, C1-3).")
    v["indice_paye"] = entier("indice_paye", 0, 9999)
    v["indice_reel"] = entier("indice_reel", 0, 9999)
    try:
        v["date_naissance"] = lire_naissance(texte("date_naissance", 20))
    except ValueError:
        v["date_naissance"] = None
        err.append("Date de naissance invalide (jj/mm/aaaa, ou l'année seule).")
    for k in DATES:
        try:
            v[k] = lire_date(texte(k, 20))
        except ValueError:
            v[k] = None
            err.append(f"{LIBELLES[k]} : date invalide.")
            continue
        if v[k] and v[k] > plus_ans(auj, 1).isoformat():
            err.append(f"{LIBELLES[k]} : date trop lointaine dans l'avenir.")
    naiss = v["date_naissance"]
    if naiss:
        an = int(naiss[:4])
        if not 1930 <= an <= auj.year - 15:
            err.append("Date de naissance invalide (année hors limites).")
        for k in DATES:
            if v[k] and v[k][:4] <= naiss[:4]:
                err.append(f"{LIBELLES[k]} : antérieure à la naissance.")
    if v["date_prise_service"]:
        for k in DATES[1:]:
            if v[k] and v[k] < v["date_prise_service"]:
                err.append(f"{LIBELLES[k]} : antérieure à la première prise de service.")
    v.update(lire_diplomes(form, err, auj))
    v["visite_aptitude"] = texte("visite_aptitude", 3) if texte("visite_aptitude", 3) in ("oui", "non") else ""
    v["visite_aptitude_note"] = decimal("visite_aptitude_note", 0, 20)
    v["departement_servir"] = texte("departement_servir", 30)
    if v["departement_servir"] and v["departement_servir"] not in DEPARTEMENTS:
        err.append("Département à servir invalide.")
    v["visites_cp"] = entier("visites_cp", 0, 99)
    v["visites_ccs"] = entier("visites_ccs", 0, 99)
    v["participation_up"] = decimal("participation_up", 0, 100)
    v["gestion_collegiale"] = texte("gestion_collegiale", 500)
    v["note_evaluation"] = decimal("note_evaluation", 0, 20)
    return v, err


def lire_diplomes(form, err, auj=None):
    """Diplômes (partie modifiable aussi par l'enseignant)."""
    auj = auj or date.today()
    v = {"diplome_academique": str(form.get("diplome_academique") or "").strip()[:80]}
    for k in ("ceap", "cap"):
        v[k] = form.get(k) if form.get(k) in ("oui", "non") else ""
    for k in ("diplome_academique_annee", "ceap_annee", "cap_annee"):
        brut = str(form.get(k) or "").strip()
        v[k] = None
        if brut:
            if re.fullmatch(r"\d{4}", brut) and 1940 <= int(brut) <= auj.year:
                v[k] = int(brut)
            else:
                err.append(f"{LIBELLES[k]} : année invalide.")
    for k in ("ceap", "cap"):          # une année d'obtention vaut « oui »
        if v[f"{k}_annee"] and not v[k]:
            v[k] = "oui"
        if v[k] == "non" and v[f"{k}_annee"]:
            err.append(f"{LIBELLES[k]} : « non » avec une année d'obtention.")
    return v


# colonnes du tableau complet (Excel, PDF, tableau du directeur)
ENTETES = ["N°", "Nom et prénoms", "Sexe", "NIP", "Matricule", "Catégorie", "Fonction", "Grade", "Indice payé",
           "Indice réel", "Date de naissance", "1re prise de service", "Prise de service département",
           "Prise de service commune", "Prise de service école", "Ancienneté générale", "Ancienneté département",
           "Ancienneté commune", "Ancienneté école", "Retraite (date probable)", "Temps restant",
           "Diplôme académique", "Année", "CEAP", "CAP", "Visite d'aptitude", "Note aptitude", "Département à servir",
           "Visites CP", "Visites CCS", "Participation UP (%)", "Gestion collégiale", "Note d'évaluation"]
ENTETES_PDF = ["N°", "Nom et prénoms (sexe)", "NIP", "Caté-\ngorie", "Fonction", "Grade", "Ind.\npayé", "Ind.\nréel",
               "Naissance", "1re prise\nde service", "PS dépar-\ntement", "PS\ncommune", "PS école", "Anc.\ngén.",
               "Anc.\ndép.", "Anc.\ncom.", "Anc.\nécole", "Retraite\n(reste)", "Diplôme\nacadémique", "CEAP /\nCAP",
               "Apti-\ntude", "Dép. à\nservir", "Vis.\nCP/CCS", "UP\n%", "Gestion\ncollégiale", "Note\néval."]
# largeurs en mm (mises à l'échelle de la page A4 paysage par document_tableau)
LARGEURS_PDF = [5, 21, 13.5, 12, 14.5, 8, 6.5, 6.5, 13, 13, 13, 13, 13, 8, 8, 8, 8, 13, 13, 12, 8, 9, 10.5, 6, 10.5, 7]


def diplome_pro(f, k):
    if f.get(k) == "oui":
        return f"oui ({f[k + '_annee']})" if f.get(k + "_annee") else "oui"
    return f.get(k) or ""


def ligne_complete(i, f):
    """Ligne du tableau complet (valeurs texte, pour Excel)."""
    return [i, f["nom_complet"], f.get("sexe") or "", f.get("nip") or "", f.get("matricule") or "", f["categorie_lib"],
            f.get("fonction") or "", f.get("grade") or "", f.get("indice_paye"), f.get("indice_reel"), f["naissance_txt"],
            fmt_date(f.get("date_prise_service")), fmt_date(f.get("date_service_dep")),
            fmt_date(f.get("date_service_commune")), fmt_date(f.get("date_service_ecole")),
            fmt_duree(f["anc"]["generale"], True) if f["anc"]["generale"] else "",
            fmt_duree(f["anc"]["departement"], True) if f["anc"]["departement"] else "",
            fmt_duree(f["anc"]["commune"], True) if f["anc"]["commune"] else "",
            fmt_duree(f["anc"]["ecole"], True) if f["anc"]["ecole"] else "",
            f["retraite_txt"], f["restant_txt"], f.get("diplome_academique") or "", f.get("diplome_academique_annee"),
            diplome_pro(f, "ceap"), diplome_pro(f, "cap"), f.get("visite_aptitude") or "",
            f.get("visite_aptitude_note"), f.get("departement_servir") or "", f.get("visites_cp"), f.get("visites_ccs"),
            f.get("participation_up"), f.get("gestion_collegiale") or "", f.get("note_evaluation")]


def ligne_pdf(i, f):
    """Même contenu, condensé pour le PDF paysage."""
    c = lambda t: fmt_duree(t, True) if t else ""   # noqa: E731
    dip = f.get("diplome_academique") or ""
    if dip and f.get("diplome_academique_annee"):
        dip += f" ({f['diplome_academique_annee']})"
    apt = f.get("visite_aptitude") or ""
    if apt and f.get("visite_aptitude_note") is not None:
        apt += f" ({fmt_nombre(f['visite_aptitude_note'])})"
    pro = " / ".join(x for x in (("CEAP " + diplome_pro(f, "ceap")) if f.get("ceap") else "",
                                 ("CAP " + diplome_pro(f, "cap")) if f.get("cap") else "") if x)
    ret = f["retraite_txt"] + (f"\n({f['restant_txt']})" if f["restant_txt"] else "")
    vis = "" if f.get("visites_cp") is None and f.get("visites_ccs") is None else \
        f"{fmt_nombre(f.get('visites_cp')) or '—'} / {fmt_nombre(f.get('visites_ccs')) or '—'}"
    return [i, f["nom_complet"] + (f" ({f['sexe']})" if f.get("sexe") else ""), f.get("nip") or "", f["categorie_lib"],
            f.get("fonction") or "", f.get("grade") or "", fmt_nombre(f.get("indice_paye")), fmt_nombre(f.get("indice_reel")),
            f["naissance_txt"].replace("(année) ", ""), fmt_date(f.get("date_prise_service")),
            fmt_date(f.get("date_service_dep")), fmt_date(f.get("date_service_commune")),
            fmt_date(f.get("date_service_ecole")), c(f["anc"]["generale"]), c(f["anc"]["departement"]),
            c(f["anc"]["commune"]), c(f["anc"]["ecole"]), ret, dip, pro, apt, f.get("departement_servir") or "", vis,
            fmt_nombre(f.get("participation_up")), f.get("gestion_collegiale") or "", fmt_nombre(f.get("note_evaluation"))]


# ================================================================ module Flask
def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config

    H.schema(SCHEMA)
    H.ajouter_colonne("personnel", "nip", "TEXT")
    H.ajouter_colonne("personnel", "date_naissance", "TEXT")
    H.ajouter_colonne("personnel", "user_id", "INTEGER")

    COLS_CARRIERE = [k for k in LIBELLES if k not in ("nip", "date_naissance")]

    # ------------------------------------------------------------ accès aux données
    def lignes_personnel(tous=False, pid=None, user_id=None, toutes_ecoles=False):
        """Personnel de l'école courante (ou de toutes) joint à sa fiche de carrière, avec calculs."""
        sql = ("SELECT p.*, c.* FROM personnel p LEFT JOIN personnel_carriere c ON c.personnel_id=p.id "
               "WHERE (p.ecole_id=? OR ?)")
        args = [H.eco(), 1 if toutes_ecoles else 0]
        if pid is not None:
            sql += " AND p.id=?"
            args.append(pid)
        if user_id is not None:
            sql += " AND p.user_id=?"
            args.append(user_id)
        if not tous and pid is None:
            sql += " AND p.actif=1"
        sql += " ORDER BY p.nom, p.prenoms"
        return [calculer_fiche(r) for r in q(sql, args)]

    def fiche_ou_404(pid):
        """Fiche d'un agent de l'école courante ; l'agent lui-même retrouve la sienne quelle que soit l'école choisie."""
        lst = lignes_personnel(pid=pid)
        if not lst and g.get("user"):
            lst = [f for f in lignes_personnel(pid=pid, toutes_ecoles=True) if f.get("user_id") == g.user["id"]]
        if not lst:
            abort(404)
        return lst[0]

    def verifier_acces(f):
        """Le directeur (droit carriere) voit tout ; un agent ne voit que SA fiche (compte lié)."""
        if H.peut("carriere"):
            return
        if not (g.user and f.get("user_id") == g.user["id"]):
            abort(403)

    def comptes_liables():
        return q("""SELECT id, identifiant, nom, role FROM utilisateurs WHERE actif=1 AND (ecole_id IS NULL OR ecole_id=?)
                    ORDER BY nom""", (H.eco(),))

    def enregistrer_carriere(pid, v):
        """Enregistre les champs de carrière (v : sortie de lire_formulaire) pour l'agent pid."""
        ex("UPDATE personnel SET nip=?, date_naissance=? WHERE id=?", (v.get("nip") or None, v.get("date_naissance"), pid))
        if "user_id" in v:
            ex("UPDATE personnel SET user_id=? WHERE id=?", (v["user_id"], pid))
        vals = [v.get(k) for k in COLS_CARRIERE]
        ex(f"INSERT INTO personnel_carriere (personnel_id, {', '.join(COLS_CARRIERE)}, maj, maj_par) "
           f"VALUES (?, {', '.join('?' * len(COLS_CARRIERE))}, ?, ?) ON CONFLICT(personnel_id) DO UPDATE SET "
           + ", ".join(f"{k}=excluded.{k}" for k in COLS_CARRIERE) + ", maj=excluded.maj, maj_par=excluded.maj_par",
           [pid] + vals + [H.maintenant(), g.user["id"] if g.get("user") else None])

    # ---- interface utilisée par la fiche du personnel (m_paie.personnel_form) en édition publique
    def form_valeurs(pid):
        if not pid:
            return {}
        r = q("SELECT p.nip, p.date_naissance, p.user_id, c.* FROM personnel p LEFT JOIN personnel_carriere c "
              "ON c.personnel_id=p.id WHERE p.id=?", (pid,), un=True)
        return dict(r) if r else {}

    def form_options():
        return {"car_categories": CATEGORIES, "car_grades": GRADES, "car_departements": DEPARTEMENTS,
                "car_diplomes": DIPLOMES, "car_comptes": comptes_liables(), "car_reference": date_reference(),
                "car_ages": AGES_RETRAITE}

    def form_lire(form, pid=None):
        v, err = lire_formulaire(form)
        brut = (form.get("user_id") or "").strip()
        v["user_id"] = None
        if brut:
            try:
                uid = int(brut)
            except ValueError:
                uid = 0
            if uid not in {u["id"] for u in comptes_liables()}:
                err.append("Compte utilisateur invalide.")
            else:
                autre = q("SELECT nom, prenoms FROM personnel WHERE user_id=? AND id<>?", (uid, pid or 0), un=True)
                if autre:
                    err.append(f"Ce compte est déjà lié à la fiche de {autre['nom']} {autre['prenoms']}.")
                else:
                    v["user_id"] = uid
        return v, err

    def ecole_personnel(pid):
        """Rattache l'agent à l'école courante (création) — utilisé par m_paie."""
        ex("UPDATE personnel SET ecole_id=? WHERE id=?", (H.eco(), pid))

    H.carriere = types.SimpleNamespace(valeurs=form_valeurs, options=form_options, lire=form_lire,
                                       enregistrer=enregistrer_carriere, liste=lignes_personnel,
                                       rattacher=ecole_personnel, fmt_date=fmt_date, fmt_duree=fmt_duree)

    @app.context_processor
    def ctx_carriere():
        def carriere_moi():
            """Fiche de carrière de l'utilisateur connecté (compte lié) ou None."""
            if not g.get("user"):
                return None
            lst = lignes_personnel(tous=True, user_id=g.user["id"], toutes_ecoles=True)
            return lst[0] if lst else None
        return dict(carriere_moi=carriere_moi, car_fmt_date=fmt_date, car_fmt_nombre=fmt_nombre,
                    car_diplome_pro=diplome_pro, CAR_LIBELLES=LIBELLES, CAR_DIPLOMES=DIPLOMES)

    # ------------------------------------------------------------ liste « Gestion de carrière »
    FILTRES_ALERTE = {"retraite": "Départ à la retraite dans 2 ans ou moins", "aptitude": "Visite d'aptitude manquante",
                      "incomplet": "Dossier incomplet", "proposition": "Proposition de l'agent à valider"}

    def filtrer(lst, a):
        cat, lettre, alerte, texte = a.get("categorie", ""), a.get("lettre", ""), a.get("alerte", ""), a.get("q", "")
        texte = texte.strip().lower()
        out = []
        for f in lst:
            if cat and f.get("categorie") != cat:
                continue
            if lettre and f["lettre_grade"] != lettre:
                continue
            if alerte == "retraite" and not f["alerte_retraite"]:
                continue
            if alerte == "aptitude" and not f["aptitude_manquante"]:
                continue
            if alerte == "incomplet" and not f["incomplet"]:
                continue
            if alerte == "proposition" and not f["propositions_d"]:
                continue
            if texte and texte not in f"{f['nom_complet']} {f.get('nip') or ''} {f.get('matricule') or ''} {f.get('fonction') or ''}".lower():
                continue
            out.append(f)
        return out

    def args_filtres():
        return {k: request.args.get(k, "") for k in ("categorie", "lettre", "alerte", "q", "tous")}

    @app.route("/carriere")
    @H.connexion_requise("carriere")
    def carriere_accueil():
        a = args_filtres()
        tous = lignes_personnel(tous=a["tous"] == "1")
        lst = filtrer(tous, a)
        stats = {
            "total": len(tous),
            "retraite": sum(f["alerte_retraite"] for f in tous),
            "aptitude": sum(f["aptitude_manquante"] for f in tous),
            "incomplet": sum(f["incomplet"] for f in tous),
            "proposition": sum(bool(f["propositions_d"]) for f in tous),
            "categories": {c: sum(f.get("categorie") == c for f in tous) for c, _ in CATEGORIES},
        }
        return render_template("carriere_accueil.html", lst=lst, ensemble=tous, stats=stats, a=a, categories=CATEGORIES,
                               filtres_alerte=FILTRES_ALERTE, reference=date_reference(), ages=AGES_RETRAITE,
                               aujourdhui=date.today())

    def titre_haut(sous):
        e = H.identification()
        return [f"{e['ecole']} — {sous}", f"DDEMP : {e['ddemp'] or '—'} · CS : {e['cs'] or '—'} · Commune : "
                f"{e['commune'] or '—'} · Année scolaire {config.ANNEE_ACTIVE}",
                f"Anciennetés au {date_reference().strftime('%d/%m/%Y')} · extrait le {date.today().strftime('%d/%m/%Y')}"]

    @app.route("/carriere/export.xlsx")
    @H.connexion_requise("carriere")
    def carriere_xlsx():
        a = args_filtres()
        lst = filtrer(lignes_personnel(tous=a["tous"] == "1"), a)
        try:
            return H.xlsx.reponse_xlsx("carriere_enseignants.xlsx", ENTETES,
                                       [ligne_complete(i, f) for i, f in enumerate(lst, 1)], titre="Carrière",
                                       titre_haut=titre_haut("Gestion de carrière des enseignants"))
        except H.xlsx.ExcelIndisponible:
            flash("Export Excel indisponible (module openpyxl absent).", "danger")
            return redirect(url_for("carriere_accueil"))

    def signatures_directeur():
        e = H.identification()
        titre = (e["directeur_titre"] or "Directeur")
        titre = f"{'La' if titre.startswith('Directrice') else 'Le'} {titre}"
        return [(titre.upper(), e["directeur_nom"], H.pdfs.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)]

    def infos_haut():
        e = H.identification()
        return [("DDEMP", e["ddemp"] or "—"), ("CS", e["cs"] or "—"), ("ÉCOLE", e["ecole"] or "—")]

    NOTES_BAS = [
        "Anciennetés arrêtées au 31 décembre de la première année de l'année scolaire en cours (31/12 inclus), "
        "en années (a) et mois (m) révolus, à partir de la date de prise de service dans chaque lieu. PS = prise de service.",
        "Retraite : âge limite 60 ans (grade A), 58 ans (grade B), 55 ans (grade C) ; départ le 1er jour du trimestre "
        "qui suit le trimestre de naissance (né de janvier à mars : 1er avril ; avril–juin : 1er juillet ; "
        "juillet–septembre : 1er octobre ; octobre–décembre : 1er janvier suivant). Année de naissance seule : "
        "1er janvier de l'année (naissance + âge + 1). Lignes orangées : départ dans 2 ans ou moins.",
    ]

    def pdf_personnel(lst, titre, avant=None):
        corps = [ligne_pdf(i, f) for i, f in enumerate(lst, 1)]
        if not corps:
            corps = [[""] * len(ENTETES_PDF)]
            corps[0][1] = "Aucun agent (voir les filtres)"
        surl = {i: "#FDEAD7" for i, f in enumerate(lst) if f["alerte_retraite"]}
        return H.pdfs.document_tableau(
            titre, ENTETES_PDF, corps, paysage=True, taille=5.3, largeurs=LARGEURS_PDF, surlignes=surl,
            sous_titre=f"Année scolaire {config.ANNEE_ACTIVE} — situation au {date.today().strftime('%d/%m/%Y')}",
            infos_haut=infos_haut(), notes_bas=NOTES_BAS, signatures=signatures_directeur(), avant=avant)

    @app.route("/carriere/liste.pdf")
    @H.connexion_requise("carriere")
    def carriere_pdf():
        a = args_filtres()
        lst = filtrer(lignes_personnel(tous=a["tous"] == "1"), a)
        return H.pdf_reponse(pdf_personnel(lst, "GESTION DE CARRIÈRE DES ENSEIGNANTS"), "carriere_enseignants.pdf")

    # ------------------------------------------------------------ fiche individuelle
    @app.route("/carriere/moi")
    @H.connexion_requise()
    def carriere_moi_fiche():
        lst = lignes_personnel(tous=True, user_id=g.user["id"], toutes_ecoles=True)
        if not lst:
            flash("Votre compte n'est lié à aucune fiche du personnel : demandez au directeur de faire le lien "
                  "(fiche du personnel → « Compte utilisateur de l'agent »).", "warning")
            return redirect(url_for("espace_enseignant") if "espace_enseignant" in app.view_functions else url_for("accueil"))
        return redirect(url_for("carriere_fiche", pid=lst[0]["id"]))

    @app.route("/carriere/<int:pid>")
    @H.connexion_requise()
    def carriere_fiche(pid):
        f = fiche_ou_404(pid)
        verifier_acces(f)
        prop = f["propositions_d"] or {}
        return render_template("carriere_fiche.html", f=f, soi=bool(g.user and f.get("user_id") == g.user["id"]),
                               directeur=H.peut("carriere"), sections=sections_fiche(f),
                               prop_lignes=[(LIBELLES[k], f.get(k), prop.get(k)) for k in CHAMPS_ENSEIGNANT],
                               saisie={k: (prop[k] if k in prop else f.get(k)) for k in CHAMPS_ENSEIGNANT})

    def sections_fiche(f):
        """Rubriques de la fiche individuelle : [(titre, [(libellé, valeur)])]."""
        n = fmt_nombre
        dip = f.get("diplome_academique") or ""
        if dip and f.get("diplome_academique_annee"):
            dip += f" (obtenu en {f['diplome_academique_annee']})"
        apt = f.get("visite_aptitude") or ""
        if f.get("visite_aptitude_note") is not None:
            apt += f" — note : {n(f['visite_aptitude_note'])}/20"
        ret = f["retraite_txt"]
        if ret:
            ret += f" ({f['age_retraite']} ans, grade {f['lettre_grade']}) — " + (
                "départ atteint" if f["retraite_atteinte"] else f"reste {f['restant_txt']}")
        else:
            ret = f"non calculable : {f.get('retraite_raison')}"
        return [
            ("1. Identification", [
                ("Nom et prénoms", f["nom_complet"]), ("Sexe", {"M": "Masculin", "F": "Féminin"}.get(f.get("sexe") or "", "")),
                ("NIP", f.get("nip") or ""), ("Matricule GESCOL", f.get("matricule") or ""),
                ("Catégorie", f["categorie_lib"]), ("Date de naissance", f["naissance_txt"]),
                ("Téléphone", f.get("telephone") or ""), ("E-mail", f.get("email") or "")]),
            ("2. Situation administrative", [
                ("Fonction", f.get("fonction") or ""), ("Grade", f.get("grade") or ""),
                ("Indice payé", n(f.get("indice_paye"))), ("Indice réel", n(f.get("indice_reel"))),
                ("Date de première prise de service", fmt_date(f.get("date_prise_service"))),
                ("Prise de service dans le département", fmt_date(f.get("date_service_dep"))),
                ("Prise de service dans la commune", fmt_date(f.get("date_service_commune"))),
                ("Prise de service dans l'école", fmt_date(f.get("date_service_ecole"))),
                ("Département à servir", f.get("departement_servir") or "")]),
            (f"3. Anciennetés au {f['reference'].strftime('%d/%m/%Y')}", [
                (lib, f["anc_txt"][cle] if f["anc"][cle] else "—") for cle, _c, lib in ANCIENNETES]),
            ("4. Départ à la retraite", [("Date probable de départ", ret)]),
            ("5. Diplômes", [
                ("Diplôme académique le plus élevé", dip), ("CEAP", diplome_pro(f, "ceap")),
                ("CAP", diplome_pro(f, "cap"))]),
            ("6. Suivi pédagogique et évaluation", [
                ("Visite d'aptitude", apt), ("Visites de classe reçues du CP", n(f.get("visites_cp"))),
                ("Visites de classe reçues du CCS", n(f.get("visites_ccs"))),
                ("Participation à l'UP", n(f.get("participation_up"), " %")),
                ("Gestion collégiale (responsabilités)", f.get("gestion_collegiale") or ""),
                ("Note d'évaluation du personnel", (n(f.get("note_evaluation")) + " / 20") if f.get("note_evaluation") is not None else "")]),
        ]

    @app.route("/carriere/<int:pid>/fiche.pdf")
    @H.connexion_requise()
    def carriere_fiche_pdf(pid):
        f = fiche_ou_404(pid)
        verifier_acces(f)
        # deux rubriques par ligne (la fiche tient sur une page avec les signatures)
        lignes, surl = [], {}
        for titre, champs in sections_fiche(f):
            surl[len(lignes)] = "#DCE7F3"
            lignes.append([titre, "", "", ""])
            cases = [[lib, val or "……………………"] for lib, val in champs]
            for i in range(0, len(cases), 2):
                lignes.append(cases[i] + (cases[i + 1] if i + 1 < len(cases) else ["", ""]))
        notes = [f"Anciennetés au {f['reference'].strftime('%d/%m/%Y')} (31/12 de la première année de l'année scolaire, "
                 "jour inclus), en années et mois révolus. Retraite : 60 ans (grade A), 58 ans (B), 55 ans (C), départ le "
                 "1er jour du trimestre qui suit le trimestre de naissance (janv.–mars : 1er avril ; avril–juin : 1er juillet ; "
                 "juil.–sept. : 1er octobre ; oct.–déc. : 1er janvier suivant) ; année de naissance seule : 1er janvier "
                 "de l'année (naissance + âge + 1)."]
        if f["incomplet"]:
            notes.insert(0, "Renseignements manquants : " + ", ".join(f["manquants"]) + ".")
        sigs = [("L'AGENT", f["nom_complet"], None, False)] + signatures_directeur()
        pdf = H.pdfs.document_tableau(
            "FICHE INDIVIDUELLE DE CARRIÈRE", ["Rubrique", "Renseignement", "Rubrique", "Renseignement"], lignes,
            largeurs=[27, 23, 27, 23], taille=8.5,
            sous_titre=f"{f['nom_complet']} — année scolaire {config.ANNEE_ACTIVE}", infos_haut=infos_haut(),
            surlignes=surl, notes_bas=notes, signatures=sigs)
        return H.pdf_reponse(pdf, f"fiche_carriere_{re.sub(r'[^A-Za-z0-9]+', '_', f['nom_complet'])}.pdf")

    # ---- propositions de l'agent (diplômes) et validation par le directeur
    @app.route("/carriere/<int:pid>/proposer", methods=["POST"])
    @H.connexion_requise()
    def carriere_proposer(pid):
        f = fiche_ou_404(pid)
        if not (g.user and f.get("user_id") == g.user["id"]):
            abort(403)
        err = []
        v = lire_diplomes(request.form, err)
        if err:
            for m in err:
                flash(m, "danger")
            return redirect(url_for("carriere_fiche", pid=pid))
        if all(v.get(k) == f.get(k) or (v.get(k) in (None, "") and f.get(k) in (None, "")) for k in CHAMPS_ENSEIGNANT):
            flash("Aucune modification par rapport à votre fiche.", "info")
            return redirect(url_for("carriere_fiche", pid=pid))
        if not q("SELECT 1 FROM personnel_carriere WHERE personnel_id=?", (pid,), un=True):
            ex("INSERT INTO personnel_carriere (personnel_id) VALUES (?)", (pid,))
        ex("UPDATE personnel_carriere SET propositions=?, propose_le=? WHERE personnel_id=?",
           (json.dumps(v, ensure_ascii=False), H.maintenant(), pid))
        H.journal("carriere_proposition", f["nom_complet"])
        flash("Proposition envoyée : elle sera appliquée après validation par le directeur.", "success")
        return redirect(url_for("carriere_fiche", pid=pid))

    @app.route("/carriere/<int:pid>/valider", methods=["POST"])
    @H.connexion_requise("carriere")
    def carriere_valider(pid):
        f = fiche_ou_404(pid)
        prop = f["propositions_d"]
        if not prop:
            flash("Aucune proposition en attente.", "info")
        elif request.form.get("action") == "valider":
            err = []
            v = lire_diplomes(prop, err)
            if err:
                flash("Proposition invalide : " + " ".join(err), "danger")
                return redirect(url_for("carriere_fiche", pid=pid))
            ex("UPDATE personnel_carriere SET " + ", ".join(f"{k}=?" for k in CHAMPS_ENSEIGNANT) +
               ", propositions=NULL, propose_le=NULL, maj=?, maj_par=? WHERE personnel_id=?",
               [v[k] for k in CHAMPS_ENSEIGNANT] + [H.maintenant(), g.user["id"], pid])
            H.journal("carriere_validation", f["nom_complet"])
            flash("Proposition validée : la fiche est mise à jour.", "success")
        elif request.form.get("action") == "rejeter":
            ex("UPDATE personnel_carriere SET propositions=NULL, propose_le=NULL WHERE personnel_id=?", (pid,))
            H.journal("carriere_rejet", f["nom_complet"])
            flash("Proposition rejetée.", "warning")
        else:
            abort(400)
        return redirect(url_for("carriere_fiche", pid=pid))

    # ================================================================ tableau de bord du directeur
    def directeur_requis():
        if g.user["role"] not in ("fondateur", "admin", "directeur"):
            abort(403)

    def table_existe(nom):
        return bool(q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nom,), un=True))

    def donnees_directeur():
        eid = H.eco()
        d1, d2 = H.bornes_annee()
        auj = date.today()
        cantine = table_existe("cantine_paiements")
        classes = []
        for c in q("SELECT * FROM classes WHERE ecole_id=? ORDER BY nom", (eid,)):
            r = q("""SELECT COUNT(*) t, COALESCE(SUM(sexe='F'),0) f, COALESCE(SUM(sexe='M'),0) m,
                            COALESCE(SUM(redoublant=1),0) red FROM eleves WHERE classe_id=? AND statut='inscrit'""",
                  (c["id"],), un=True)
            ligne = {"c": c, "t": r["t"], "f": r["f"], "m": r["m"], "red": r["red"], "cantine": None}
            if cantine:
                ligne["cantine"] = q("""SELECT COALESCE(SUM(cp.montant),0) s FROM cantine_paiements cp JOIN eleves e
                                        ON e.id=cp.eleve_id WHERE e.classe_id=? AND cp.date BETWEEN ? AND ?""",
                                     (c["id"], d1, d2), un=True)["s"]
            classes.append(ligne)
        tot = {k: sum(l[k] for l in classes) for k in ("t", "f", "m", "red")}
        tot["cantine"] = sum(l["cantine"] or 0 for l in classes) if cantine else None
        synth = None
        if cantine:
            base = ("SELECT COALESCE(SUM(cp.montant),0) s, COUNT(*) n, COUNT(DISTINCT cp.eleve_id) el "
                    "FROM cantine_paiements cp JOIN eleves e ON e.id=cp.eleve_id JOIN classes c ON c.id=e.classe_id "
                    "WHERE c.ecole_id=? AND cp.date BETWEEN ? AND ?")
            an = q(base, (eid, d1, d2), un=True)
            mo = q(base, (eid, auj.replace(day=1).isoformat(), auj.isoformat()), un=True)
            jo = q(base, (eid, auj.isoformat(), auj.isoformat()), un=True)
            synth = {"annee": an["s"], "annee_n": an["n"], "annee_el": an["el"], "mois": mo["s"], "mois_n": mo["n"],
                     "jour": jo["s"], "jour_n": jo["n"]}
        publique = None
        if getattr(H, "stats_publique", None):
            try:
                publique = H.stats_publique()
            except Exception:           # module des finances publiques en cours d'évolution : ne pas bloquer
                publique = None
        personnel = lignes_personnel()
        return {"classes": classes, "tot": tot, "cantine": synth, "publique": publique, "personnel": personnel,
                "bornes": (d1, d2)}

    LIB_PUBLIQUE = {"recu_annee": "Fonds reçus de l'année (subventions, cantine…)", "recu_jour": "Fonds reçus aujourd'hui",
                    "depenses_annee": "Dépenses de l'année", "depenses_jour": "Dépenses du jour",
                    "solde": "Solde en caisse"}

    def lignes_publique(pub):
        """Valeurs de H.stats_publique affichables : [(libellé, montant)]."""
        out = []
        for k, v in (pub or {}).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append((LIB_PUBLIQUE.get(k, k.replace("_", " ").capitalize()), v))
        return out

    @app.route("/directeur")
    @H.connexion_requise()
    def directeur_tableau():
        directeur_requis()
        d = donnees_directeur()
        return render_template("directeur_tableau.html", d=d, pub=lignes_publique(d["publique"]),
                               reference=date_reference(), aujourdhui=date.today(),
                               retraites=sum(f["alerte_retraite"] for f in d["personnel"]))

    @app.route("/directeur/tableau.pdf")
    @H.connexion_requise()
    def directeur_tableau_pdf():
        directeur_requis()
        d = donnees_directeur()
        P = H.pdfs
        eff = [["Classe", "Cours", "Titulaire", "Garçons", "Filles", "Total", "dont redoublants"]
               + (["Cantine (année)"] if d["cantine"] else [])]
        for l in d["classes"]:
            eff.append([l["c"]["nom"], l["c"]["niveau"], l["c"]["titulaire_nom"] or "", l["m"], l["f"], l["t"], l["red"]]
                       + ([H.fcfa(l["cantine"])] if d["cantine"] else []))
        eff.append(["TOTAL", "", "", d["tot"]["m"], d["tot"]["f"], d["tot"]["t"], d["tot"]["red"]]
                   + ([H.fcfa(d["tot"]["cantine"])] if d["cantine"] else []))
        avant = [P.paragraphe("1. Effectifs des élèves par classe et par sexe", 9, True)]
        avant.append(P.mini_tableau(eff) if d["classes"] else P.paragraphe("Aucune classe."))
        fonds = []
        if d["cantine"]:
            c = d["cantine"]
            fonds += [["Cantine – année scolaire", H.fcfa(c["annee"]), f"{c['annee_n']} paiement(s), {c['annee_el']} élève(s)"],
                      ["Cantine – mois en cours", H.fcfa(c["mois"]), f"{c['mois_n']} paiement(s)"],
                      ["Cantine – aujourd'hui", H.fcfa(c["jour"]), f"{c['jour_n']} paiement(s)"]]
        fonds += [[lib, H.fcfa(v), "finances de l'école"] for lib, v in lignes_publique(d["publique"])]
        avant.append(P.paragraphe("2. Synthèse des fonds", 9, True))
        avant.append(P.mini_tableau([["Rubrique", "Montant", "Détail"]] + fonds) if fonds
                     else P.paragraphe("Aucune donnée de cantine ou de finances disponible."))
        avant.append(P.paragraphe(f"3. Personnel et carrière (anciennetés au {date_reference().strftime('%d/%m/%Y')})", 9, True))
        pdf = pdf_personnel(d["personnel"], "TABLEAU DE BORD DU DIRECTEUR", avant=avant)
        return H.pdf_reponse(pdf, "tableau_de_bord_directeur.pdf")

    @app.route("/directeur/tableau.xlsx")
    @H.connexion_requise()
    def directeur_tableau_xlsx():
        directeur_requis()
        d = donnees_directeur()
        eff = [[l["c"]["nom"], l["c"]["niveau"], l["c"]["titulaire_nom"] or "", l["m"], l["f"], l["t"], l["red"]]
               + ([l["cantine"]] if d["cantine"] else []) for l in d["classes"]]
        eff.append(["TOTAL", "", "", d["tot"]["m"], d["tot"]["f"], d["tot"]["t"], d["tot"]["red"]]
                   + ([d["tot"]["cantine"]] if d["cantine"] else []))
        fonds = []
        if d["cantine"]:
            c = d["cantine"]
            fonds += [["Cantine – année scolaire", c["annee"], c["annee_n"]], ["Cantine – mois en cours", c["mois"], c["mois_n"]],
                      ["Cantine – aujourd'hui", c["jour"], c["jour_n"]]]
        fonds += [[lib, v, ""] for lib, v in lignes_publique(d["publique"])]
        th = titre_haut("Tableau de bord du directeur")
        try:
            return H.xlsx.reponse_classeur("tableau_de_bord_directeur.xlsx", [
                ("Effectifs", ["Classe", "Cours", "Titulaire", "Garçons", "Filles", "Total", "dont redoublants"]
                 + (["Cantine (FCFA, année)"] if d["cantine"] else []), eff, {"titre_haut": th}),
                ("Personnel", ENTETES, [ligne_complete(i, f) for i, f in enumerate(d["personnel"], 1)], {"titre_haut": th}),
                ("Fonds", ["Rubrique", "Montant (FCFA)", "Nombre de paiements"], fonds, {"titre_haut": th}),
            ])
        except H.xlsx.ExcelIndisponible:
            flash("Export Excel indisponible (module openpyxl absent).", "danger")
            return redirect(url_for("directeur_tableau"))
