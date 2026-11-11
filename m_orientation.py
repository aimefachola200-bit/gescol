# -*- coding: utf-8 -*-
"""v2.4.4 — Orientation et passage des élèves : choix de la série ou de l'option après le BEPC (3ème → 2nde) et, de même,
après les évaluations et devoirs pour toutes les autres classes.

* 3ème (après le BEPC) et 2nde : séries proposées d'après les moyennes par groupe de matières (lettres, mathématiques,
  physique-chimie, sciences de la vie) ; avis du conseil d'orientation et vœu de la famille enregistrés.
* Tle (après le Baccalauréat) : pistes de filières selon la série et la moyenne.
* Toutes les autres classes (maternelle exclue) : proposition de passage (≥ 10 admis ; 9 à 10 conseil de classe ; < 9 redoublement).
Les moyennes viennent des notes déjà saisies (devoirs et compositions) : on peut retenir toutes les évaluations de l'année ou seulement certaines.
Les propositions sont une aide ; la décision revient toujours au conseil de classe / d'orientation.

* /orientation                         orientation_accueil   choix de la classe
* /orientation/<cid>                   orientation_classe    tableau des élèves, propositions, décisions (POST : enregistrement)
* /orientation/<cid>/liste.pdf|.xlsx   liste d'orientation de la classe
* /orientation/eleve/<eid>.pdf         fiche d'orientation d'un élève
"""
import re
import unicodedata
from datetime import date

import config
from calcul import NIVEAUX_MATERNELLE, NIVEAUX_PRIMAIRE, NIVEAUX_SANS_COEF, NIVEAUX_SECONDAIRE
from flask import abort, flash, g, redirect, render_template, request, url_for

NOTE_PASSAGE = 10.0
SEUIL_CONSEIL = 9.0                      # entre ce seuil et 10 : examen par le conseil de classe

GROUPES = [("lettres", "Lettres et langues"), ("maths", "Mathématiques"), ("pct", "Physique-chimie"), ("svt", "Sciences de la vie")]

# Série : (conditions minimales par groupe, libellé). La proposition est « admissible » si toutes les conditions sont remplies.
SERIES_REGLES = [
    ("A1", {"lettres": 12}, "Lettres et langues"),
    ("A2", {"lettres": 12}, "Lettres et sciences humaines"),
    ("B", {"lettres": 11, "maths": 10}, "Économie et sciences sociales"),
    ("C", {"maths": 12, "pct": 12}, "Mathématiques et sciences physiques"),
    ("D", {"maths": 10, "svt": 12, "pct": 10}, "Sciences de la vie et de la terre"),
    ("E", {"maths": 11, "pct": 11}, "Mathématiques et technique"),
    ("F", {"maths": 10, "pct": 10}, "Technologies industrielles (F1 à F4)"),
    ("G", {"maths": 10, "lettres": 10}, "Gestion, comptabilité, secrétariat (G1 à G3)"),
]
SERIES_CHOIX = ["A1", "A2", "B", "C", "D", "E", "F1", "F2", "F3", "F4", "G1", "G2", "G3", "H", "Agriculture", "Enseignement technique et professionnel (CAP, BEP)", "Autre"]
DECISIONS = ["Admis en classe supérieure", "Présentation au baccalauréat", "Redoublement", "Conseil de classe", "Orienté", "Transféré", "Exclu"]
RESULTATS_EXAMEN = ["", "Admis", "Second tour", "Ajourné", "Absent"]

FILIERES_BAC = {
    "A": ["Lettres modernes", "Langues vivantes (anglais, allemand, espagnol)", "Droit", "Sciences humaines et sociales", "Communication et journalisme", "Enseignement"],
    "B": ["Économie et gestion", "Droit", "Sciences sociales", "Commerce et finance", "Statistique"],
    "C": ["Mathématiques et physique", "Informatique", "Sciences de l'ingénieur (classes préparatoires, écoles d'ingénieurs)", "Architecture", "Économie quantitative"],
    "D": ["Sciences de la vie et de la terre", "Santé (médecine, pharmacie, paramédical : sur concours)", "Agronomie", "Chimie et biologie", "Informatique"],
    "E": ["Génie civil", "Génie mécanique et électrique", "Technologie (IUT, écoles d'ingénieurs)"],
    "F": ["Technologies industrielles (BTS, licence professionnelle)", "Génie civil et bâtiment", "Électrotechnique et mécanique"],
    "G": ["Gestion et comptabilité (BTS, licence professionnelle)", "Secrétariat et administration", "Commerce et marketing"],
    "H": ["Informatique et numérique", "Génie logiciel", "Réseaux et télécommunications"],
}
AVERTISSEMENT_BAC = "Pistes indicatives : les conditions d'accès (concours, quotas, dossiers) sont fixées par chaque établissement d'enseignement supérieur."


def sans_accent(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def groupe_matiere(code, nom):
    """lettres | maths | pct | svt | None (autres matières : comptées seulement dans la moyenne générale)."""
    c = (code or "").upper()
    n = sans_accent(nom)
    if c.startswith("FR") or c in ("ANG", "ESP", "ALL", "HG", "PHILO"):
        return "lettres"
    if c == "MATH":
        return "maths"
    if c == "PCT":
        return "pct"
    if c == "SVT":
        return "svt"
    if "math" in n:
        return "maths"
    if "sport" in n or c == "EPS":
        return None
    if "physique" in n or "chimie" in n:
        return "pct"
    if "vie et de la terre" in n or "svt" in n or "biolog" in n:
        return "svt"
    if re.search(r"fran|lecture|dictee|redaction|expression|langue|anglais|espagnol|allemand|histoire|geograph|philo|ecriture|vocabul|grammaire|conjug|orthograph", n):
        return "lettres"
    return None


def moyenne_ponderee(couples):
    pts = tot = 0.0
    for v, c in couples:
        pts += v * c
        tot += c
    return round(pts / tot, 2) if tot else None


def profil_eleve(notes, niveau, periodes=None):
    """notes : [(periode, valeur, coefficient, code, nom)] → moyennes de l'élève.
    generale = moyenne des moyennes de chaque évaluation retenue ; groupes = moyenne de toutes les notes du groupe retenues."""
    sans_coef = niveau in NIVEAUX_SANS_COEF
    par_per, par_gr = {}, {}
    n = 0
    for per, val, coef, code, nom in notes:
        if val is None or (periodes and per not in periodes):
            continue
        c = 1.0 if sans_coef else (coef or 1.0)
        par_per.setdefault(per, []).append((val, c))
        gr = groupe_matiere(code, nom)
        if gr:
            par_gr.setdefault(gr, []).append((val, c))
        n += 1
    moy_per = {p: moyenne_ponderee(v) for p, v in par_per.items()}
    vals = [m for m in moy_per.values() if m is not None]
    return {"generale": round(sum(vals) / len(vals), 2) if vals else None, "periodes": moy_per, "nb_notes": n,
            "groupes": {g_: moyenne_ponderee(par_gr[g_]) if g_ in par_gr else None for g_, _l in GROUPES}}


def propose_series(profil):
    """[{serie, libelle, score, admissible, manque}] triées : admissibles d'abord, puis par score."""
    out = []
    gen = profil.get("generale")
    for serie, regle, lib in SERIES_REGLES:
        valeurs = [profil["groupes"].get(g_) for g_ in regle]
        inconnu = any(v is None for v in valeurs)
        manque = [f"{dict(GROUPES)[g_]} {profil['groupes'].get(g_) if profil['groupes'].get(g_) is not None else '—'} (min. {mini})"
                  for g_, mini in regle.items() if profil["groupes"].get(g_) is None or profil["groupes"][g_] < mini]
        score = round(sum(v for v in valeurs if v is not None) / max(len([v for v in valeurs if v is not None]), 1), 2) if valeurs else None
        adm = (not inconnu) and not manque and gen is not None and gen >= NOTE_PASSAGE
        out.append({"serie": serie, "libelle": lib, "score": score, "admissible": adm, "manque": manque})
    out.sort(key=lambda x: (not x["admissible"], -(x["score"] or 0)))
    return out


def decision_proposee(moyenne, niveau):
    if moyenne is None:
        return ""
    if niveau == "Tle":
        return "Présentation au baccalauréat" if moyenne >= NOTE_PASSAGE else "Conseil de classe"
    if moyenne >= NOTE_PASSAGE:
        return "Admis en classe supérieure"
    if moyenne >= SEUIL_CONSEIL:
        return "Conseil de classe"
    return "Redoublement"


def etape_de(niveau):
    """Nature de l'orientation selon le niveau."""
    if niveau == "3ème":
        return "apres_bepc"
    if niveau == "2nde":
        return "choix_serie"
    if niveau == "Tle":
        return "apres_bac"
    if niveau in NIVEAUX_MATERNELLE:
        return "aucune"
    return "passage"


LIBELLE_ETAPE = {"apres_bepc": "Choix de la série après le BEPC (entrée en 2nde)", "choix_serie": "Choix de la série pour la classe de 1ère",
                 "apres_bac": "Orientation après le baccalauréat", "passage": "Passage en classe supérieure", "aucune": "Pas d'orientation en maternelle"}


def serie_de_classe(nom):
    for mot in reversed(re.split(r"[\s\-_/]+", (nom or "").strip())):
        if re.fullmatch(r"[A-Ha-h][1-4]?", mot):
            return mot.upper()
    return ""


def filieres_pour(serie, moyenne):
    base = FILIERES_BAC.get((serie or "")[:1].upper(), [])
    if moyenne is not None and moyenne < 10:
        return base[:2]
    return base


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema("""
        CREATE TABLE IF NOT EXISTS orientation_decisions (
            id INTEGER PRIMARY KEY,
            eleve_id INTEGER NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
            annee TEXT NOT NULL,
            voeu TEXT,                 -- série ou filière souhaitée par l'élève / la famille
            avis TEXT,                 -- série ou filière retenue par le conseil d'orientation
            decision TEXT,
            resultat_examen TEXT,      -- BEPC / baccalauréat
            observation TEXT,
            date_decision TEXT,
            saisi_par INTEGER,
            UNIQUE(eleve_id, annee)
        );
    """)

    def classe_ou_404(cid):
        c = q("SELECT * FROM classes WHERE id=?", (cid,), un=True)
        if not c or c["niveau"] in NIVEAUX_MATERNELLE:
            abort(404)
        H.verifier_classe(cid)
        return c

    def lecture(c, annee, periodes):
        """[(élève, profil, proposition, décision enregistrée)] et la liste des évaluations disponibles."""
        eleves = q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (c["id"],))
        notes = {}
        dispo = []
        for r in q("SELECT n.eleve_id, n.periode, n.valeur, m.coefficient, m.code, m.nom FROM notes n JOIN matieres m ON m.id=n.matiere_id "
                   "JOIN eleves e ON e.id=n.eleve_id WHERE e.classe_id=? AND n.annee=? AND n.valeur IS NOT NULL AND n.dispense=0", (c["id"], annee)):
            notes.setdefault(r["eleve_id"], []).append((r["periode"], r["valeur"], r["coefficient"], r["code"], r["nom"]))
            if r["periode"] not in dispo:
                dispo.append(r["periode"])
        decisions = {r["eleve_id"]: r for r in q("SELECT * FROM orientation_decisions WHERE annee=?", (annee,))}
        etape = etape_de(c["niveau"])
        lignes = []
        for e in eleves:
            p = profil_eleve(notes.get(e["id"], []), c["niveau"], periodes)
            if etape in ("apres_bepc", "choix_serie"):
                prop = propose_series(p)
                proposition = next((x["serie"] for x in prop if x["admissible"]), "") if p["generale"] is not None else ""
                if p["generale"] is not None and p["generale"] < NOTE_PASSAGE and etape == "choix_serie":
                    proposition = ""
            elif etape == "apres_bac":
                prop = []
                proposition = ""
            else:
                prop = []
                proposition = decision_proposee(p["generale"], c["niveau"])
            lignes.append({"eleve": e, "profil": p, "series": prop, "proposition": proposition,
                           "enr": decisions.get(e["id"]), "filieres": filieres_pour(serie_de_classe(c["nom"]), p["generale"]) if etape == "apres_bac" else []})
        return lignes, sorted(dispo)

    def annee_et_periodes():
        annee = request.values.get("annee") or config.ANNEE_ACTIVE
        periodes = [p for p in request.values.getlist("periodes") if p]
        return annee, periodes

    @app.route("/orientation")
    @H.connexion_requise("notes")
    def orientation_accueil():
        classes = [c for c in H.classes_autorisees() if c["niveau"] not in NIVEAUX_MATERNELLE]
        cartes = []
        for c in classes:
            n = q("SELECT COUNT(*) n FROM eleves WHERE classe_id=? AND statut='inscrit'", (c["id"],), un=True)["n"]
            d = q("SELECT COUNT(*) n FROM orientation_decisions o JOIN eleves e ON e.id=o.eleve_id WHERE e.classe_id=? AND e.statut='inscrit' "
                  "AND o.annee=? AND COALESCE(o.decision,'')!=''", (c["id"], config.ANNEE_ACTIVE), un=True)["n"]
            cartes.append({"c": c, "n": n, "decides": d, "etape": LIBELLE_ETAPE[etape_de(c["niveau"])]})
        return render_template("orientation.html", mode="accueil", cartes=cartes, annee=config.ANNEE_ACTIVE)

    @app.route("/orientation/<int:cid>", methods=["GET", "POST"])
    @H.connexion_requise("notes")
    def orientation_classe(cid):
        c = classe_ou_404(cid)
        annee, periodes = annee_et_periodes()
        etape = etape_de(c["niveau"])
        if request.method == "POST":
            n = 0
            for e in q("SELECT id FROM eleves WHERE classe_id=? AND statut='inscrit'", (cid,)):
                k = str(e["id"])
                if f"decision_{k}" not in request.form and f"avis_{k}" not in request.form:
                    continue
                voeu = (request.form.get(f"voeu_{k}") or "").strip()[:80]
                avis = (request.form.get(f"avis_{k}") or "").strip()[:120]
                dec = (request.form.get(f"decision_{k}") or "").strip()
                if dec and dec not in DECISIONS:
                    dec = ""
                res = (request.form.get(f"resultat_{k}") or "").strip()
                res = res if res in RESULTATS_EXAMEN else ""
                obs = (request.form.get(f"obs_{k}") or "").strip()[:300]
                if not (voeu or avis or dec or res or obs):
                    ex("DELETE FROM orientation_decisions WHERE eleve_id=? AND annee=?", (e["id"], annee))
                    continue
                ex("INSERT INTO orientation_decisions (eleve_id, annee, voeu, avis, decision, resultat_examen, observation, date_decision, saisi_par) "
                   "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(eleve_id, annee) DO UPDATE SET voeu=excluded.voeu, avis=excluded.avis, "
                   "decision=excluded.decision, resultat_examen=excluded.resultat_examen, observation=excluded.observation, "
                   "date_decision=excluded.date_decision, saisi_par=excluded.saisi_par",
                   (e["id"], annee, voeu, avis, dec, res, obs, date.today().isoformat(), g.user["id"]))
                n += 1
            H.journal("orientation", f"{c['nom']} {annee} : {n} élève(s)")
            flash(f"Orientation enregistrée pour {n} élève(s).", "success")
            return redirect(url_for("orientation_classe", cid=cid, annee=annee, periodes=periodes))
        lignes, dispo = lecture(c, annee, periodes)
        synthese = {}
        for l in lignes:
            cle = (l["enr"]["avis"] if l["enr"] and l["enr"]["avis"] else "") or (l["enr"]["decision"] if l["enr"] and l["enr"]["decision"] else "") or "Non décidé"
            synthese[cle] = synthese.get(cle, 0) + 1
        return render_template("orientation.html", mode="classe", c=c, annee=annee, etape=etape, titre_etape=LIBELLE_ETAPE[etape], lignes=lignes,
                               dispo=dispo, periodes=periodes, GROUPES=GROUPES, SERIES_CHOIX=SERIES_CHOIX, DECISIONS=DECISIONS,
                               RESULTATS=RESULTATS_EXAMEN, synthese=sorted(synthese.items(), key=lambda x: -x[1]), serie_classe=serie_de_classe(c["nom"]),
                               avertissement_bac=AVERTISSEMENT_BAC, peut_saisir=True)

    def tableau_liste(c, annee, periodes):
        lignes, _d = lecture(c, annee, periodes)
        etape = etape_de(c["niveau"])
        cols = ["N°", "Nom et prénoms", "Sexe", "Moyenne", "Lettres", "Maths", "Phys.-chim.", "SVT", "Proposition", "Vœu", "Avis / décision", "Résultat examen"]
        rows = []
        f = lambda v: "" if v is None else f"{v:.2f}".replace(".", ",")
        for i, l in enumerate(lignes, 1):
            p, enr = l["profil"], l["enr"] or {}
            rows.append([i, f"{l['eleve']['nom']} {l['eleve']['prenoms']}", l["eleve"]["sexe"], f(p["generale"]), *[f(p["groupes"][g_]) for g_, _x in GROUPES],
                         l["proposition"], enr["voeu"] if enr else "", ((enr["avis"] or "") + (" — " if enr and enr["avis"] and enr["decision"] else "") + (enr["decision"] or "")) if enr else "",
                         enr["resultat_examen"] if enr else ""])
        return etape, cols, rows

    @app.route("/orientation/<int:cid>/liste.pdf")
    @H.connexion_requise("notes")
    def orientation_liste_pdf(cid):
        c = classe_ou_404(cid)
        annee, periodes = annee_et_periodes()
        etape, cols, rows = tableau_liste(c, annee, periodes)
        v = H.identification()
        titre_dir = v.get("directeur_titre") or "Directeur"
        sig = [("LE PROFESSEUR PRINCIPAL", "", None, False),
               (f"{'LA' if titre_dir.lower().startswith('directrice') else 'LE'} {titre_dir.upper()}", v.get("directeur_nom") or "",
                H.pdfs.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)]
        pdf = H.pdfs.document_tableau(
            "LISTE D'ORIENTATION", cols, rows or [["", "Aucun élève"] + [""] * 10], sous_titre=f"{c['nom']} — {LIBELLE_ETAPE[etape]} — {annee}",
            infos=[("École", v.get("ecole")), ("Évaluations retenues", ", ".join(periodes) if periodes else "toutes")],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[6, 34, 6, 9, 9, 9, 10, 9, 18, 14, 28, 12], paysage=True, taille=7.5, signatures=sig,
            notes_bas=["Les propositions découlent des moyennes ; la décision appartient au conseil de classe / d'orientation."])
        return H.pdf_reponse(pdf, f"orientation_{re.sub(r'[^A-Za-z0-9]+', '_', c['nom'])}_{annee}.pdf")

    @app.route("/orientation/<int:cid>/liste.xlsx")
    @H.connexion_requise("notes")
    def orientation_liste_xlsx(cid):
        c = classe_ou_404(cid)
        annee, periodes = annee_et_periodes()
        etape, cols, rows = tableau_liste(c, annee, periodes)
        v = H.identification()
        try:
            return H.xlsx.reponse_classeur(f"orientation_{re.sub(r'[^A-Za-z0-9]+', '_', c['nom'])}_{annee}.xlsx", [
                ("Orientation", cols, rows, {"titre_haut": [f"{v.get('ecole') or ''} — Liste d'orientation", f"{c['nom']} — {LIBELLE_ETAPE[etape]} — {annee}"]})])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("orientation_classe", cid=cid, annee=annee))

    @app.route("/orientation/eleve/<int:eid>.pdf")
    @H.connexion_requise("notes")
    def orientation_eleve_pdf(eid):
        e = q("SELECT e.*, c.nom classe_nom, c.niveau FROM eleves e JOIN classes c ON c.id=e.classe_id WHERE e.id=?", (eid,), un=True)
        if not e or e["niveau"] in NIVEAUX_MATERNELLE:
            abort(404)
        c = classe_ou_404(e["classe_id"])
        annee, periodes = annee_et_periodes()
        lignes, _d = lecture(c, annee, periodes)
        l = next(x for x in lignes if x["eleve"]["id"] == eid)
        p, enr = l["profil"], l["enr"]
        f = lambda v: "—" if v is None else f"{v:.2f}".replace(".", ",") + " / 20"
        rows = [["Moyenne générale", f(p["generale"])]] + [[lib, f(p["groupes"][k])] for k, lib in GROUPES]
        rows += [["Évaluations prises en compte", f"{len(p['periodes'])} ({p['nb_notes']} notes)"]]
        etape = etape_de(c["niveau"])
        if etape in ("apres_bepc", "choix_serie"):
            rows += [["Série proposée", l["proposition"] or "à examiner par le conseil"]]
            adm = [x["serie"] for x in l["series"] if x["admissible"]]
            rows += [["Séries accessibles d'après les moyennes", ", ".join(adm) or "aucune"]]
        elif etape == "apres_bac":
            rows += [["Pistes de filières", " ; ".join(l["filieres"]) or "—"], ["Remarque", AVERTISSEMENT_BAC]]
        else:
            rows += [["Proposition", l["proposition"] or "—"]]
        if enr:
            rows += [["Vœu de l'élève / de la famille", enr["voeu"] or ""], ["Avis du conseil", enr["avis"] or ""], ["Décision", enr["decision"] or ""],
                     ["Résultat à l'examen", enr["resultat_examen"] or ""], ["Observation", enr["observation"] or ""]]
        v = H.identification()
        titre_dir = v.get("directeur_titre") or "Directeur"
        pdf = H.pdfs.document_tableau(
            "FICHE D'ORIENTATION", ["Rubrique", "Valeur"], rows, sous_titre=f"{e['nom']} {e['prenoms']} — {c['nom']} — {annee}",
            infos=[("Matricule", e["matricule"] or ""), ("Étape", LIBELLE_ETAPE[etape])],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))], largeurs=[60, 120], taille=9,
            signatures=[("LES PARENTS / LE TUTEUR", "", None, False),
                        (f"{'LA' if titre_dir.lower().startswith('directrice') else 'LE'} {titre_dir.upper()}", v.get("directeur_nom") or "",
                         H.pdfs.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True)])
        return H.pdf_reponse(pdf, f"orientation_{e['matricule'] or eid}.pdf")
