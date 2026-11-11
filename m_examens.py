# -*- coding: utf-8 -*-
"""v1.27 — Examens et concours (spécification commune PVS, lot C), en complément des fiches d'inscription au CEP.

CEP de bout en bout, par session (« CEP AAAA ») : épreuves (« Épreuves par défaut »), centres, jurys, candidats (repris des
élèves de CM2 et de leurs fiches CEP), numéros de table et salles par centre, saisie des notes (écran et feuille Excel
« Notes », absent = ABS), délibération (moyenne /20, seuil et repêchage, rangs ex aequo), validation, statistiques par
école et par sexe, convocations, relevés de notes, procès-verbal de délibération et liste des admis signés (QR).
Concours scolaires (dictée, calcul mental, culture générale, génies en herbe, dessin, chant…) : participants, notes,
rangs, palmarès et diplômes de lauréat (rangs 1 à 3).
"""
import io
import json
import re
from datetime import date

from flask import flash, g, redirect, render_template, request, url_for

import registres as R

EPREUVES_DEFAUT = ["Communication écrite (rédaction)", "Lecture", "Mathématiques", "Éducation scientifique et technologique",
                   "Éducation sociale", "Éducation physique et sportive", "Éducation artistique"]
ECOLE_DE = " de l'école "
DECISIONS = ("Admis", "Admis (repêché)", "Ajourné", "Absent")


def session_defaut(annee=None):
    a = (annee or "")[5:9]
    return f"CEP {a or date.today().year + (1 if date.today().month >= 9 else 0)}"


def lire_note(v):
    if v in (None, ""):
        return None
    s = str(v).strip().upper()
    if s in ("ABS", "ABSENT", "A"):
        return "ABS"
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def notes_de(x):
    try:
        d = json.loads(x.get("notes") or "{}")
        return {str(k): v for k, v in d.items()} if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def deliberer(candidats, epreuves, seuil=10.0, repechage=None):
    """[{id, total, moyenne, decision, rang}] — total = Σ note × coef ; moyenne = total × 20 / Σ (barème × coef) des épreuves notées."""
    res = []
    for c in candidats:
        n = notes_de(c)
        tot, base = 0.0, 0.0
        for e in epreuves:
            v = n.get(str(e["id"]))
            if isinstance(v, (int, float)):
                coef = float(e.get("coefficient") or 1)
                tot += float(v) * coef
                base += float(e.get("bareme") or 20) * coef
        absent = (c.get("statut") or "Inscrit") in ("Absent", "Abandon", "Exclu") or base == 0
        moy = round(tot * 20 / base + 1e-9, 2) if base else None
        if absent:
            dec = "Absent"
        elif moy >= seuil:
            dec = "Admis"
        elif repechage not in (None, "") and moy >= float(repechage):
            dec = "Admis (repêché)"
        else:
            dec = "Ajourné"
        res.append({"id": c["id"], "total": round(tot, 2), "moyenne": None if absent else moy, "decision": dec, "rang": None})
    ordre = sorted([r for r in res if r["moyenne"] is not None], key=lambda r: -r["moyenne"])
    prec, rang = None, 0
    for i, r in enumerate(ordre, 1):
        if r["moyenne"] != prec:
            rang, prec = i, r["moyenne"]
        r["rang"] = rang
    return res


def numeroter(candidats, centre):
    """[(id, numéro, salle)] pour les candidats d'un centre : tri école, nom, prénoms ; « <code>-<n° sur 4 chiffres> »."""
    lst = sorted(candidats, key=lambda c: (R._norm(c.get("entite")), R._norm(c.get("nom")), R._norm(c.get("prenoms"))))
    cap = int(centre.get("capacite") or 30) or 30
    code = (centre.get("code") or "").strip() or re.sub(r"[^A-Z0-9]", "", R._norm(centre.get("centre")).upper())[:6] or "C"
    return [(c["id"], f"{code}-{i:04d}", f"Salle {(i - 1) // cap + 1}") for i, c in enumerate(lst, 1)]


def rangs_concours(participants):
    """{id: rang} : rang saisi, sinon par points décroissants (ex aequo = même rang)."""
    out = {p["id"]: int(p["rang"]) for p in participants if p.get("rang") not in (None, "")}
    libres = sorted([p for p in participants if p.get("rang") in (None, "") and p.get("points") not in (None, "")], key=lambda p: -float(p["points"]))
    prec, rang = None, 0
    for i, p in enumerate(libres, 1):
        if float(p["points"]) != prec:
            rang, prec = i, float(p["points"])
        out[p["id"]] = rang
    return out


def stats(candidats, res):
    """Par école et par sexe : inscrits, présents, admis, taux (admis / présents)."""
    d = {r["id"]: r for r in res}
    out = {}
    for c in candidats:
        for cle in (c.get("entite") or "—", "Ensemble"):
            s = out.setdefault(cle, {"G": [0, 0, 0], "F": [0, 0, 0]})
            k = "F" if (c.get("sexe") or "").upper().startswith("F") else "G"
            r = d.get(c["id"]) or {}
            s[k][0] += 1
            if r.get("decision") != "Absent":
                s[k][1] += 1
            if (r.get("decision") or "").startswith("Admis"):
                s[k][2] += 1
    for s in out.values():
        t = [s["G"][i] + s["F"][i] for i in range(3)]
        s["T"] = t
        for k in ("G", "F", "T"):
            s[k + "taux"] = round(100 * s[k][2] / s[k][1], 1) if s[k][1] else None
    return out


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.DROITS["examens_pvs"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent", "enseignant"}
    R.types_documents({"reg_examens_candidats_convocation": "Convocation du candidat", "reg_examens_candidats_releve": "Relevé de notes",
                       "examens_pv": "Procès-verbal de délibération", "examens_admis": "Liste des candidats admis",
                       "reg_examens_concours_palmares": "Palmarès du concours", "reg_examens_participants_prix": "Diplôme de lauréat (concours)"})
    G = R.Groupe(app, H, "examens", "Examens et concours", "examens_pvs", ico="examen",
                 sous_titre="CEP de bout en bout (épreuves, centres, jurys, candidats, numéros de table, notes, délibération, résultats, relevés) "
                            "et concours scolaires (palmarès, diplômes)",
                 listes={"sexe": ["M", "F"], "statuts_cand": ["Inscrit", "Absent", "Abandon", "Exclu"],
                         "types_concours": ["Dictée", "Calcul mental", "Culture générale", "Génies en herbe", "Lecture", "Dessin", "Chant / poésie",
                                            "Rédaction", "Autre"], "statuts_concours": ["Programmé", "Réalisé", "Annulé"],
                         "cours": ["Maternelle", "CI", "CP", "CE1", "CE2", "CM1", "CM2"]},
                 onglets_avant=[("examens_session", "Session CEP", {})])
    S0 = lambda: session_defaut(R.annee_active())   # noqa: E731
    struct = lambda: dict(zip(("niveau", "entite"), R.entite_courante()))   # noqa: E731

    G.registre("epreuves", "Épreuves", [("session", "Session", "texte"), ("epreuve", "Épreuve", "texte"), ("coefficient", "Coefficient", "decimal"),
                                       ("bareme", "Noté sur", "decimal"), ("ordre", "Ordre", "entier")],
               unite="épreuve", oblig="epreuve", ordre="session, ordre, id", portee="structure", feuille="Épreuves", entite=True,
               niveaux=["CS", "ZONE", "DDEMP", "ECOLE", "UP"], unique=("session", "epreuve"),
               defauts=lambda: dict(struct(), session=S0(), coefficient=1, bareme=20), doc="Épreuves de l'examen")
    G.registre("centres", "Centres", [("session", "Session", "texte"), ("centre", "Centre", "texte"), ("code", "Code du centre", "texte"),
                                     ("ecoleSiege", "École siège", "ecole"), ("chefCentre", "Chef de centre", "texte"), ("salles", "Salles", "entier"),
                                     ("capacite", "Places par salle", "entier")],
               unite="centre", oblig="centre", ordre="session, centre", portee="structure", feuille="Centres", entite=True,
               unique=("session", "centre"), defauts=lambda: dict(struct(), session=S0(), salles=1, capacite=30), doc="Centres d'examen",
               aide="Code du centre : préfixe des numéros de table (ex. POB1).")
    G.registre("jurys", "Jurys", [("session", "Session", "texte"), ("centre", "Centre", "texte"), ("president", "Président(e) du jury", "texte"),
                                 ("vicePresident", "Vice-président(e)", "texte"), ("secretaire", "Secrétaire", "texte"),
                                 ("membres", "Membres (un par ligne)", "long"), ("date", "Date de délibération", "date")],
               unite="jury", oblig="centre", ordre="session, centre", portee="structure", feuille="Jurys", entite=True,
               unique=("session", "centre"), defauts=lambda: dict(struct(), session=S0()), doc="Jurys")

    def jury_de(session, centre):
        x = q("SELECT * FROM reg_examens_jurys WHERE portee=? AND session=? AND lower(centre)=lower(?)",
              (R.cle_portee("structure"), session, centre or ""), un=True)
        return dict(x) if x else {}

    def centre_de(session, centre):
        x = q("SELECT * FROM reg_examens_centres WHERE portee=? AND session=? AND lower(centre)=lower(?)",
              (R.cle_portee("structure"), session, centre or ""), un=True)
        return dict(x) if x else {}

    def epreuves_de(session):
        return [dict(e) for e in q("SELECT * FROM reg_examens_epreuves WHERE portee=? AND session=? ORDER BY COALESCE(ordre, 999), id",
                                   (R.cle_portee("structure"), session))]

    def candidats_de(session, centre=None):
        sql, a = "SELECT * FROM reg_examens_candidats WHERE portee=? AND session=?", [R.cle_portee("structure"), session]
        if centre:
            sql += " AND lower(COALESCE(centre,''))=lower(?)"
            a.append(centre)
        return [dict(c) for c in q(sql + " ORDER BY COALESCE(numeroTable,''), entite, nom, prenoms", tuple(a))]

    def doc_convocation(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        ce = centre_de(x.get("session"), x.get("centre"))
        corps = [Paragraph(f"Session : <b>{R.esc(x.get('session') or '')}</b>", st["p"]),
                 R.tableau(["Rubrique", "Renseignement"], [r for r in [
                     ["N° de table", x.get("numeroTable") or ""], ["Nom et prénoms", f"{x.get('nom') or ''} {x.get('prenoms') or ''}"],
                     ["Sexe", x.get("sexe") or ""], ["Né(e) le / à", f"{R.jjmmaaaa(x.get('dateNaissance'))} {('à ' + x['lieuNaissance']) if x.get('lieuNaissance') else ''}"],
                     ["École", x.get("entite") or ""], ["Centre d'examen", x.get("centre") or ""], ["Salle", x.get("salle") or ""],
                     ["École siège du centre", ce.get("ecoleSiege") or ""]] if r[1].strip()], [1, 3], R.largeur_utile(False)), Spacer(1, 8),
                 Paragraph("Le candidat se présente au centre muni de la présente convocation et d'une pièce d'identité ou de sa carte "
                           "scolaire, une demi-heure avant le début des épreuves.", st["p"])]
        return "Convocation du candidat", corps, [R.signature_vide("Le chef de centre", ce.get("chefCentre") or ""), R.signature_autorite("Visa de l'autorité")]

    def doc_releve(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        ep = epreuves_de(x.get("session"))
        n = notes_de(x)
        res = {r["id"]: r for r in deliberer([x], ep, float(param("seuil") or 10), param("repechage") or None)}.get(x["id"], {})
        lignes = [[e["epreuve"], (str(n.get(str(e["id"]))).replace(".", ",") if n.get(str(e["id"])) not in (None, "") else "—"),
                   f"{e.get('bareme') or 20:g}", f"{e.get('coefficient') or 1:g}"] for e in ep]
        corps = [Paragraph(f"<b>{R.esc((x.get('nom') or '') + ' ' + (x.get('prenoms') or ''))}</b> — n° de table {R.esc(x.get('numeroTable') or '—')} — "
                           f"{R.esc(x.get('entite') or '')} — centre {R.esc(x.get('centre') or '')} — {R.esc(x.get('session') or '')}", st["p"]), Spacer(1, 4),
                 R.tableau(["Épreuve", "Note", "Sur", "Coefficient"], lignes, [3, 1, 0.8, 1], R.largeur_utile(False),
                           total=["Moyenne sur 20", "" if res.get("moyenne") is None else str(res["moyenne"]).replace(".", ","), "", res.get("decision") or ""])]
        j = jury_de(x.get("session"), x.get("centre"))
        return "Relevé de notes", corps, [R.signature_vide("Le président du jury", j.get("president") or ""), R.signature_autorite("Visa de l'autorité")]

    def calc_cand(x):
        m = x.get("moyenne")
        return {"Moyenne": "" if m in (None, "") else m, "Décision": x.get("decision") or ""}

    r = G.registre("candidats", "Candidats", [
        ("session", "Session", "texte"), ("numeroTable", "N° de table", "texte"), ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"),
        ("sexe", "Sexe", "choix:sexe"), ("dateNaissance", "Date de naissance", "date"), ("lieuNaissance", "Lieu de naissance", "texte"),
        ("centre", "Centre", "texte"), ("salle", "Salle", "texte"), ("statut", "Statut", "choix:statuts_cand")],
        unite="candidat", oblig="nom", ordre="session, numeroTable, entite, nom, prenoms", portee="structure", feuille="Candidats", entite=True,
        niveaux=["ECOLE"], unique=("session", "nom", "prenoms", "dateNaissance"), calcul=calc_cand, filtres=("statut",),
        fiches={"convocation": ("Convocation du candidat", "carte-identite", doc_convocation), "releve": ("Relevé de notes", "document", doc_releve)},
        defauts=lambda: {"niveau": "ECOLE", "entite": R.entite_courante()[1] if R.entite_courante()[0] == "ECOLE" else "", "session": S0(), "statut": "Inscrit"},
        doc="Liste des candidats", aide="Entité = école du candidat. Notes, moyenne, rang et décision : onglets Session CEP, Notes et Délibération.")
    for k, t in (("notes", "TEXT"), ("moyenne", "REAL"), ("rang", "INTEGER"), ("decision", "TEXT")):
        H.ajouter_colonne(r.table, k, t)

    def doc_palmares(x):
        ps = participants_de(x)
        rg = rangs_concours(ps)
        lignes = sorted([[rg.get(p["id"], ""), f"{p.get('nom') or ''} {p.get('prenoms') or ''}", p.get("sexe") or "", p.get("ecole") or "",
                          p.get("cours") or "", "" if p.get("points") in (None, "") else f"{p['points']:g}"] for p in ps],
                        key=lambda l: (l[0] == "", l[0] if l[0] != "" else 0))
        from reportlab.platypus import Paragraph
        corps = [Paragraph(f"<b>{R.esc(x.get('intitule') or '')}</b> — {R.esc(x.get('type') or '')}{' — ' + R.esc(x['cours']) if x.get('cours') else ''} — "
                           f"{R.jjmmaaaa(x.get('date'))} {R.esc(x.get('lieu') or '')} (noté sur {x.get('bareme') or 20:g})", R.styles()["p"]),
                 R.tableau(["Rang", "Nom et prénoms", "Sexe", "École", "Cours", "Points"], lignes, [0.6, 2.6, 0.5, 2, 0.7, 0.8], R.largeur_utile(False))]
        return "Palmarès du concours", corps, [R.signature_vide("L'organisateur", x.get("organisateur") or ""), R.signature_autorite()]

    G.registre("concours", "Concours scolaires", [
        ("intitule", "Intitulé", "texte"), ("type", "Type", "choix:types_concours"), ("cours", "Cours / catégorie", "texte"), ("date", "Date", "date"),
        ("lieu", "Lieu", "texte"), ("organisateur", "Organisateur", "texte"), ("bareme", "Noté sur", "decimal"), ("statut", "Statut", "choix:statuts_concours")],
        unite="concours", oblig="intitule", ordre="date DESC, intitule", portee="structure", feuille="Concours scolaires", entite=True,
        unique=("intitule",), filtres=("type", "statut"), fiches={"palmares": ("Palmarès du concours", "trophee", doc_palmares)},
        defauts=lambda: dict(struct(), type="Dictée", bareme=20, statut="Programmé"), doc="Concours scolaires")

    def participants_de(cx):
        return [dict(p) for p in q("SELECT * FROM reg_examens_participants WHERE portee=? AND lower(concours)=lower(?)",
                                   (R.cle_portee("structure"), cx.get("intitule") or ""))]

    def doc_prix(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        cx = q("SELECT * FROM reg_examens_concours WHERE portee=? AND lower(intitule)=lower(?)", (R.cle_portee("structure"), x.get("concours") or ""), un=True)
        cx = dict(cx) if cx else {"intitule": x.get("concours")}
        rg = rangs_concours(participants_de(cx)).get(x["id"])
        place = {1: "1er prix", 2: "2e prix", 3: "3e prix"}.get(rg, f"{rg}e rang" if rg else "participation")
        corps = [Spacer(1, 30), Paragraph("DIPLÔME DE LAURÉAT", st["t"]), Spacer(1, 14),
                 Paragraph(f"décerné à <b>{R.esc((x.get('nom') or '') + ' ' + (x.get('prenoms') or ''))}</b>"
                           f"{', élève du ' + R.esc(x['cours']) if x.get('cours') else ''}{ECOLE_DE + R.esc(x['ecole']) if x.get('ecole') else ''}, "
                           f"<b>{place}</b> du concours « {R.esc(cx.get('intitule') or '')} »"
                           f"{' (' + R.esc(cx['type']) + ')' if cx.get('type') else ''}{', le ' + R.jjmmaaaa(cx['date']) if cx.get('date') else ''}"
                           f"{' — ' + str(x['points']).replace('.', ',') + ' points' if x.get('points') not in (None, '') else ''}.", st["s"])]
        return "Diplôme de lauréat", corps, [R.signature_autorite()]

    G.registre("participants", "Participants et notes", [
        ("concours", "Concours", "texte"), ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"), ("sexe", "Sexe", "choix:sexe"),
        ("ecole", "École", "ecole"), ("cours", "Cours", "choix:cours"), ("points", "Note / points", "decimal"), ("rang", "Rang", "entier")],
        unite="participant", oblig="nom", ordre="concours, rang, points DESC", portee="structure", feuille="Participants et notes",
        onglet="Participants", entite=True, unique=("concours", "nom", "prenoms"),
        calcul=lambda x: {"Rang retenu": rangs_concours([y for y in [dict(p) for p in q("SELECT * FROM reg_examens_participants WHERE portee=? AND "
                                                                     "lower(concours)=lower(?)", (R.cle_portee("structure"), x.get("concours") or ""))]]).get(x["id"], "")},
        fiches={"prix": ("Diplôme / prix", "medaille", doc_prix)}, defauts=struct, doc="Participants et notes",
        aide="Rang laissé vide : calculé d'après les points (ex aequo = même rang) ; diplômes de lauréat pour les rangs 1 à 3.")
    G.page("examens_notes", "Notes", apres=False)
    G.page("examens_deliberation", "Délibération et résultats", apres=False)
    # ordre des onglets : Session CEP · Notes · Délibération · registres
    G.pages = [p for p in G.pages if p[0] == "examens_session"] + [p for p in G.pages if p[0] != "examens_session"]

    # ------------------------------------------------------------------ paramètres de délibération (par session)
    H.schema("CREATE TABLE IF NOT EXISTS examens_param (portee INTEGER, session TEXT, cle TEXT, valeur TEXT, PRIMARY KEY (portee, session, cle));")

    def session_req():
        return (request.values.get("session") or "").strip() or S0()

    def param(cle, session=None):
        x = q("SELECT valeur FROM examens_param WHERE portee=? AND session=? AND cle=?", (R.cle_portee("structure"), session or session_req(), cle), un=True)
        return x["valeur"] if x else ""

    def sessions():
        out = {S0()}
        for t in ("reg_examens_epreuves", "reg_examens_candidats", "reg_examens_centres"):
            out |= {x["session"] for x in q(f"SELECT DISTINCT session FROM {t} WHERE portee=? AND session IS NOT NULL", (R.cle_portee("structure"),))}
        return sorted(x for x in out if x)

    def exiger():
        if not G.peut_ecrire():
            flash("Écriture réservée.", "warning")
            return False
        return True

    # ------------------------------------------------------------------ session
    @app.route("/examens/session", methods=["GET", "POST"])
    @H.connexion_requise("examens_pvs")
    def examens_session():
        s = session_req()
        p = R.cle_portee("structure")
        if request.method == "POST" and exiger():
            act = request.form.get("action")
            if act == "epreuves" and not epreuves_de(s):
                niv, ent = R.entite_courante()
                for i, e in enumerate(EPREUVES_DEFAUT, 1):
                    ex("INSERT INTO reg_examens_epreuves (portee, annee, niveau, entite, session, epreuve, coefficient, bareme, ordre, cree_le, cree_par, maj) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (p, R.annee_active(), niv, ent, s, e, 1, 20, i, H.maintenant(), g.user["id"], H.maintenant()))
                flash(f"{len(EPREUVES_DEFAUT)} épreuves créées (coefficient 1, sur 20 — à adapter aux instructions de la session).", "success")
            elif act == "epreuves":
                flash("La session a déjà ses épreuves.", "warning")
            elif act == "candidats":
                n = reprendre_candidats(s)
                flash(f"{n} candidat(s) repris des élèves de CM2.", "success" if n else "warning")
            elif act == "numeros":
                n = 0
                for ce in [dict(c) for c in q("SELECT * FROM reg_examens_centres WHERE portee=? AND session=?", (p, s))]:
                    for cid, num, salle in numeroter(candidats_de(s, ce["centre"]), ce):
                        ex("UPDATE reg_examens_candidats SET numeroTable=?, salle=?, maj=? WHERE id=?", (num, salle, H.maintenant(), cid))
                        n += 1
                flash(f"{n} numéro(s) de table attribué(s).", "success" if n else "warning")
            elif act == "param":
                for k in ("seuil", "repechage"):
                    v = (request.form.get(k) or "").strip().replace(",", ".")
                    ex("INSERT OR REPLACE INTO examens_param (portee, session, cle, valeur) VALUES (?,?,?,?)", (p, s, k, v))
                flash("Paramètres enregistrés.", "success")
            return redirect(url_for("examens_session", session=s))
        cands = candidats_de(s)
        centres = [dict(c) for c in q("SELECT * FROM reg_examens_centres WHERE portee=? AND session=? ORDER BY centre", (p, s))]
        par_centre = {c["centre"]: sum(1 for x in cands if R._norm(x.get("centre")) == R._norm(c["centre"])) for c in centres}
        return render_template("examens_session.html", G=G, ep_actif="examens_session", s=s, sessions=sessions(), epreuves=epreuves_de(s),
                               centres=centres, par_centre=par_centre, n_cand=len(cands), sans_centre=sum(1 for x in cands if not x.get("centre")),
                               sans_num=sum(1 for x in cands if not x.get("numeroTable")), seuil=param("seuil") or "10", repechage=param("repechage"),
                               peut_ecrire=G.peut_ecrire(), ecole_ouverte=not R.juridiction() or bool(g.get("ecole")))

    def reprendre_candidats(s):
        if R.juridiction() and not g.get("ecole"):
            return 0
        p, ent = R.cle_portee("structure"), R.entite_courante()[1]
        try:
            rows = q("""SELECT e.id, e.nom, e.prenoms, e.sexe, e.date_naissance, e.lieu_naissance, f.centre FROM eleves e
                        JOIN classes c ON c.id=e.classe_id LEFT JOIN cep_fiches f ON f.eleve_id=e.id
                        WHERE e.statut='inscrit' AND c.niveau='CM2' AND c.ecole_id=? ORDER BY e.nom, e.prenoms""", (H.eco(),))
        except Exception:  # noqa: BLE001
            return 0
        n = 0
        for e in rows:
            if q("SELECT 1 FROM reg_examens_candidats WHERE portee=? AND session=? AND nom=? AND COALESCE(prenoms,'')=? AND COALESCE(dateNaissance,'')=?",
                 (p, s, e["nom"], e["prenoms"] or "", e["date_naissance"] or ""), un=True):
                continue
            ex("INSERT INTO reg_examens_candidats (portee, annee, niveau, entite, session, nom, prenoms, sexe, dateNaissance, lieuNaissance, centre, statut, "
               "cree_le, cree_par, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (p, R.annee_active(), "ECOLE", ent, s, e["nom"], e["prenoms"] or "", (e["sexe"] or "").upper()[:1], e["date_naissance"] or "",
                e["lieu_naissance"] or "", e["centre"] or "", "Inscrit", H.maintenant(), g.user["id"], H.maintenant()))
            n += 1
        return n

    # ------------------------------------------------------------------ notes
    @app.route("/examens/notes", methods=["GET", "POST"])
    @H.connexion_requise("examens_pvs")
    def examens_notes():
        s = session_req()
        centre = (request.values.get("centre") or "").strip()
        ep = epreuves_de(s)
        cands = candidats_de(s, centre or None)
        if request.method == "POST" and exiger():
            n = 0
            for c in cands:
                d = notes_de(c)
                ch = False
                for e in ep:
                    k = f"n_{c['id']}_{e['id']}"
                    if k in request.form:
                        v = lire_note(request.form.get(k))
                        if v is None:
                            ch |= d.pop(str(e["id"]), None) is not None
                        elif d.get(str(e["id"])) != v:
                            d[str(e["id"])] = v
                            ch = True
                if ch:
                    ex("UPDATE reg_examens_candidats SET notes=?, maj=? WHERE id=?", (json.dumps(d), H.maintenant(), c["id"]))
                    n += 1
            flash(f"Notes enregistrées ({n} candidat(s) modifié(s)).", "success")
            return redirect(url_for("examens_notes", session=s, centre=centre or None))
        centres = sorted({c["centre"] for c in candidats_de(s) if c.get("centre")})
        return render_template("examens_notes.html", G=G, ep_actif="examens_notes", s=s, sessions=sessions(), centre=centre, centres=centres,
                               epreuves=ep, cands=[dict(c, n=notes_de(c)) for c in cands], peut_ecrire=G.peut_ecrire())

    @app.route("/examens/notes.xlsx")
    @H.connexion_requise("examens_pvs")
    def examens_notes_xlsx():
        s = session_req()
        centre = (request.args.get("centre") or "").strip()
        ep = epreuves_de(s)
        ent = ["N° de table", "Nom", "Prénoms", "Sexe", "École"] + [e["epreuve"] for e in ep]
        rows = []
        for c in candidats_de(s, centre or None):
            n = notes_de(c)
            rows.append([c.get("numeroTable") or "", c["nom"], c.get("prenoms") or "", c.get("sexe") or "", c.get("entite") or ""]
                        + [("" if n.get(str(e["id"])) is None else n.get(str(e["id"]))) for e in ep])
        return H.xlsx.reponse_classeur(f"notes_{re.sub(r'[^A-Za-z0-9]+', '_', s)}.xlsx", [("Notes", ent, rows, {})])

    @app.route("/examens/notes/import", methods=["POST"])
    @H.connexion_requise("examens_pvs")
    def examens_notes_import():
        import outils_xlsx as X
        s = session_req()
        if not exiger():
            return redirect(url_for("examens_notes", session=s))
        f = request.files.get("fichier")
        try:
            wb = X._openpyxl().load_workbook(io.BytesIO(f.read()), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            flash("Fichier illisible : utilisez la feuille Excel « Notes ».", "danger")
            return redirect(url_for("examens_notes", session=s))
        ws = next((w for w in wb.worksheets if X.normaliser(w.title) == "notes"), wb.worksheets[0])
        rows = [list(x) for x in ws.iter_rows(values_only=True)]
        if not rows:
            return redirect(url_for("examens_notes", session=s))
        tete = [X.normaliser(v) for v in rows[0]]
        ep = epreuves_de(s)
        j_ep = {e["id"]: tete.index(X.normaliser(e["epreuve"])) for e in ep if X.normaliser(e["epreuve"]) in tete}
        jn, jnom, jpre = (tete.index(k) if k in tete else None for k in ("n° de table", "nom", "prenoms"))
        cands = candidats_de(s)
        par_num = {c["numeroTable"]: c for c in cands if c.get("numeroTable")}
        par_nom = {(R._norm(c["nom"]), R._norm(c.get("prenoms"))): c for c in cands}
        n, refus = 0, 0
        for x in rows[1:]:
            if not x or not any(v not in (None, "") for v in x):
                continue
            c = par_num.get(str(X.valeur(x, jn)).strip()) if jn is not None else None
            if not c and jnom is not None:
                c = par_nom.get((R._norm(X.valeur(x, jnom)), R._norm(X.valeur(x, jpre) if jpre is not None else "")))
            if not c:
                refus += 1
                continue
            d = notes_de(c)
            for eid, j in j_ep.items():
                v = lire_note(x[j] if j < len(x) else None)
                if v is not None:
                    d[str(eid)] = v
            ex("UPDATE reg_examens_candidats SET notes=?, maj=? WHERE id=?", (json.dumps(d), H.maintenant(), c["id"]))
            c["notes"] = json.dumps(d)
            n += 1
        flash(f"Notes importées : {n} candidat(s)" + (f", {refus} ligne(s) sans candidat correspondant" if refus else "") + ".",
              "success" if not refus else "warning")
        return redirect(url_for("examens_notes", session=s))

    # ------------------------------------------------------------------ délibération
    def resultats(s, centre=None):
        cands = candidats_de(s, centre)
        seuil = float(param("seuil", s) or 10)
        rep = param("repechage", s) or None
        res = deliberer(cands, epreuves_de(s), seuil, rep)
        d = {r["id"]: r for r in res}
        return cands, res, [dict(c, **{"r_" + k: v for k, v in d[c["id"]].items()}) for c in cands], seuil, rep

    @app.route("/examens/deliberation", methods=["GET", "POST"])
    @H.connexion_requise("examens_pvs")
    def examens_deliberation():
        s = session_req()
        centre = (request.values.get("centre") or "").strip() or None
        cands, res, lignes, seuil, rep = resultats(s, centre)
        if request.method == "POST" and exiger():
            for r in res:
                ex("UPDATE reg_examens_candidats SET moyenne=?, rang=?, decision=?, maj=? WHERE id=?",
                   (r["moyenne"], r["rang"], r["decision"], H.maintenant(), r["id"]))
            H.journal("examens_deliberation", f"{s} {centre or ''} : {len(res)} candidat(s)")
            flash(f"Délibération validée : {sum(1 for r in res if r['decision'].startswith('Admis'))} admis sur {len(res)} candidat(s).", "success")
            return redirect(url_for("examens_deliberation", session=s, centre=centre))
        lignes.sort(key=lambda c: (c["r_rang"] is None, c["r_rang"] or 0, R._norm(c["nom"])))
        centres = sorted({c["centre"] for c in candidats_de(s) if c.get("centre")})
        return render_template("examens_deliberation.html", G=G, ep_actif="examens_deliberation", s=s, sessions=sessions(), centre=centre or "",
                               centres=centres, lignes=lignes, st=stats(cands, res), seuil=seuil, repechage=rep, peut_ecrire=G.peut_ecrire())

    def sigs_jury(s, centre, roles=("president", "vicePresident", "secretaire")):
        j = jury_de(s, centre) if centre else {}
        t = {"president": "Le président du jury", "vicePresident": "Le vice-président", "secretaire": "Le secrétaire"}
        return [R.signature_vide(t[k], j.get(k) or "") for k in roles] + [R.signature_autorite("Visa de l'autorité")]

    @app.route("/examens/deliberation.pdf")
    @H.connexion_requise("examens_pvs")
    def examens_pv_pdf():
        from reportlab.platypus import Paragraph, Spacer
        s = session_req()
        centre = (request.args.get("centre") or "").strip() or None
        cands, res, lignes, seuil, rep = resultats(s, centre)
        lignes.sort(key=lambda c: (c["r_rang"] is None, c["r_rang"] or 0, R._norm(c["nom"])))
        st = R.styles()
        ep = epreuves_de(s)
        tb = [[c.get("numeroTable") or "", f"{c['nom']} {c.get('prenoms') or ''}", c.get("sexe") or "", c.get("entite") or ""]
              + [("" if notes_de(c).get(str(e["id"])) is None else str(notes_de(c).get(str(e["id"]))).replace(".", ",")) for e in ep]
              + ["" if c["r_moyenne"] is None else str(c["r_moyenne"]).replace(".", ","), c["r_rang"] or "", c["r_decision"]] for c in lignes]
        larg = [1.1, 2.4, 0.4, 1.8] + [0.8] * len(ep) + [0.8, 0.5, 1.2]
        sta = stats(cands, res).get("Ensemble", {"T": [0, 0, 0], "Ttaux": None})
        j = jury_de(s, centre) if centre else {}
        corps = [Paragraph(f"Session <b>{R.esc(s)}</b>{' — centre ' + R.esc(centre) if centre else ''}. Délibération"
                           f"{' du ' + R.jjmmaaaa(j['date']) if j.get('date') else ''} : seuil d'admission {seuil:g} / 20"
                           f"{', repêchage à partir de ' + str(rep).replace('.', ',') if rep else ''}.", st["p"]),
                 Paragraph(f"Inscrits : {sta['T'][0]} — présents : {sta['T'][1]} — admis : {sta['T'][2]}"
                           f"{' — taux de réussite : ' + str(sta['Ttaux']).replace('.', ',') + ' %' if sta.get('Ttaux') is not None else ''}.", st["p"]),
                 Spacer(1, 4), R.tableau(["N° table", "Nom et prénoms", "S", "École"] + [e["epreuve"][:18] for e in ep] + ["Moy.", "Rang", "Décision"],
                                         tb, larg, R.largeur_utile(True), taille=6.6)]
        if (j.get("membres") or "").strip():
            corps += [Spacer(1, 4), Paragraph("Membres du jury : " + R.esc("; ".join(l.strip() for l in j["membres"].splitlines() if l.strip())), st["petit"])]
        code = R.code_document("examens_pv", f"Procès-verbal de délibération — {s}{' — ' + centre if centre else ''} ({len(res)} candidat(s))",
                               f"pv:{s}:{centre}:{len(res)}:{max([c.get('maj') or '' for c in cands] or [''])}")
        return H.pdf_reponse(R.pdf_document("PROCÈS-VERBAL DE DÉLIBÉRATION", corps, sigs_jury(s, centre), code, True), "pv_deliberation.pdf")

    @app.route("/examens/admis.pdf")
    @H.connexion_requise("examens_pvs")
    def examens_admis_pdf():
        from reportlab.platypus import Paragraph
        s = session_req()
        centre = (request.args.get("centre") or "").strip() or None
        cands, res, lignes, seuil, rep = resultats(s, centre)
        adm = sorted([c for c in lignes if (c["r_decision"] or "").startswith("Admis")], key=lambda c: (R._norm(c.get("entite")), R._norm(c["nom"])))
        tb = [[i, c.get("numeroTable") or "", f"{c['nom']} {c.get('prenoms') or ''}", c.get("sexe") or "", c.get("entite") or "",
               str(c["r_moyenne"]).replace(".", ","), c["r_decision"]] for i, c in enumerate(adm, 1)]
        corps = [Paragraph(f"Session <b>{R.esc(s)}</b>{' — centre ' + R.esc(centre) if centre else ''} : {len(adm)} admis sur "
                           f"{sum(1 for r in res if r['decision'] != 'Absent')} présent(s).", R.styles()["p"]),
                 R.tableau(["N°", "N° table", "Nom et prénoms", "Sexe", "École", "Moyenne", "Décision"], tb, [0.4, 1.1, 2.6, 0.5, 2, 0.8, 1.2],
                           R.largeur_utile(False))]
        code = R.code_document("examens_admis", f"Liste des admis — {s}{' — ' + centre if centre else ''} ({len(adm)})",
                               f"admis:{s}:{centre}:{len(adm)}:{max([c.get('maj') or '' for c in cands] or [''])}")
        return H.pdf_reponse(R.pdf_document("LISTE DES CANDIDATS ADMIS", corps, sigs_jury(s, centre, ("president",)), code, False), "liste_admis.pdf")
