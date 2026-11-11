# -*- coding: utf-8 -*-
"""v1.28 — Examen blanc du CEP, modèle commun (CS Pobè, MEMP-CP, DOSP ; outils/examen-blanc/examen.js, objet ExamenBlanc).

* 9 épreuves dans l'ordre du PV (dictée, communication écrite, compréhension de l'écrit, mathématique, EST, ES, EA vivant,
  EA artistique, EPS), notes sur 20 au quart de point ; une épreuve vide n'est pas composée (elle ne compte pas zéro) ;
* maîtrise = note ≥ 10 ; seuil atteint = au moins 6 maîtrises (sur 9, ou sur 8 pour un dispensé d'EPS) ; total, moyenne,
  classement au total décroissant avec ex æquo ; bilan d'un centre (G / F, écart filles − garçons, moyenne et écart type,
  épreuves fortes et faibles) et recommandations automatiques (mêmes règles et mêmes textes que le module JS) ;
* centres (nom, chef de centre, date, session, entité organisatrice) dans le périmètre de l'édition : l'école (ses candidats)
  ou la CS / la DDEMP (centres de ses écoles) ; candidats (saisie, reprise des candidats au CEP, Excel « Candidats à
  l'examen blanc » import / export), saisie des notes, PV de centre, relevé de centre et résultats signés (QR), Excel.

Calculs purs en tête de fichier : arrondis identiques à Math.round du JavaScript (demi vers le haut).
L'examen blanc « libre » de l'école (/cep-blanc, matières au choix) est l'onglet « Examen blanc libre (école) » du même module
(v1.33) ; une session libre peut être reprise dans l'examen blanc commun (/examen-blanc/reprendre-libre/<sid>).
"""
import io
import json
import math
import re

from flask import abort, flash, g, redirect, render_template, request, url_for

import registres as R

MATIERES = [("dictee", "Dictée", "DICT"), ("communication", "Communication écrite", "COMM"), ("comprehension", "Compréhension de l’écrit", "COMP"),
            ("maths", "Mathématique", "MATH"), ("est", "EST", "EST"), ("es", "ES", "ES"), ("ea_vivant", "EA vivant", "EA-V"),
            ("ea_artistique", "EA artistique", "EA-A"), ("eps", "EPS", "EPS")]
SEUIL_MATIERE = 10
MAITRISES_REQUISES = 6
CENTRES_POBE = ["Centre de Pobè centre", "Centre de Oké-Ola", "Centre de Pobè/C", "Centre de Oké-Ata", "Centre de Pobè-Nord",
                "Centre de Onigbolo", "Centre de Towé"]
ENT_IMPORT = ["N° d’ordre", "Nom et prénoms", "Sexe", "École de provenance"] + [l for _k, l, _a in MATIERES]
ENT_EXPORT = ENT_IMPORT + ["Total", "Moyenne", "Nombre de maîtrises", "Seuil atteint", "Rang"]
ALIAS = {"nom": "Nom et prénoms", "candidat": "Nom et prénoms", "nom et prenoms": "Nom et prénoms", "noms et prenoms": "Nom et prénoms",
         "ecole": "École de provenance", "ecole de provenance": "École de provenance", "expression ecrite": "Communication écrite",
         "communication": "Communication écrite", "comprehension": "Compréhension de l’écrit", "comprehension de l'ecrit": "Compréhension de l’écrit",
         "maths": "Mathématique", "mathematiques": "Mathématique", "mathematique": "Mathématique", "ea plastique": "EA artistique",
         "ea artistique": "EA artistique", "ea vivant": "EA vivant", "education scientifique et technologique": "EST", "education sociale": "ES",
         "dictee": "Dictée", "n° d'ordre": "N° d’ordre", "n°": "N° d’ordre", "sexe": "Sexe"}


def js_round(x, nd=2):
    """Math.round(x * 10^nd) / 10^nd du JavaScript."""
    f = 10 ** nd
    return math.floor(x * f + 0.5) / f


def js_txt(x):
    """Écriture d'un nombre comme la concaténation JavaScript (12, 12.5)."""
    if x is None:
        return "null"
    return str(int(x)) if float(x) == int(x) else repr(float(x))


def note(c, cle):
    v = (c.get("notes") or {}).get(cle) if isinstance(c.get("notes"), dict) else c.get(cle)
    try:
        return float(str("" if v is None else v).replace(",", "."))
    except ValueError:
        return None


def resultat(c):
    notes = [note(c, k) for k, _l, _a in MATIERES]
    comp = [n for n in notes if n is not None]
    total = sum(comp)
    maitrises = sum(1 for n in comp if n >= SEUIL_MATIERE)
    return {"notes": notes, "composees": len(comp), "aCompose": bool(comp), "total": js_round(total), "moyenne": js_round(total / len(comp)) if comp else None,
            "maitrises": maitrises, "requis": MAITRISES_REQUISES, "admis": bool(comp) and maitrises >= MAITRISES_REQUISES}


def classer(candidats):
    avec = [dict(resultat(c), candidat=c) for c in candidats]
    comp = sorted([x for x in avec if x["aCompose"]], key=lambda x: -x["total"])
    rang, prec = 0, None
    for place, x in enumerate(comp, 1):
        if prec is None or x["total"] < prec:
            rang, prec = place, x["total"]
        x["rang"] = rang
    for x in avec:
        if not x["aCompose"]:
            x["rang"] = None
    return avec


def ecart_type(valeurs):
    v = [x for x in valeurs if isinstance(x, (int, float))]
    if len(v) < 2:
        return 0
    m = sum(v) / len(v)
    return js_round(math.sqrt(sum((x - m) ** 2 for x in v) / len(v)))


def bilan(candidats):
    cl = classer(candidats)

    def par_sexe(s):
        ins = sum(1 for x in cl if (x["candidat"].get("sexe") or "") == s)
        comp = sum(1 for x in cl if (x["candidat"].get("sexe") or "") == s and x["aCompose"])
        adm = sum(1 for x in cl if (x["candidat"].get("sexe") or "") == s and x["admis"])
        return {"inscrits": ins, "composes": comp, "admis": adm, "taux": js_round(adm / comp * 100, 1) if comp else None}
    comp = [x for x in cl if x["aCompose"]]
    mats = []
    for k, l, a in MATIERES:
        ns = [n for n in (note(c, k) for c in candidats) if n is not None]
        if not ns:
            continue
        mats.append({"cle": k, "libelle": l, "abrege": a, "notes": len(ns), "moyenne": js_round(sum(ns) / len(ns)),
                     "maitrises": sum(1 for n in ns if n >= SEUIL_MATIERE), "taux": js_round(sum(1 for n in ns if n >= SEUIL_MATIERE) / len(ns) * 100, 1),
                     "ecartType": ecart_type(ns)})
    classees = sorted(mats, key=lambda m: -(m["moyenne"] or 0))
    gg, ff = par_sexe("G"), par_sexe("F")
    adm = sum(1 for x in comp if x["admis"])
    return {"classes": cl, "inscrits": len(cl), "composes": len(comp), "admis": adm, "absents": len(cl) - len(comp),
            "taux": js_round(adm / len(comp) * 100, 1) if comp else None,
            "moyenneCentre": js_round(sum(x["moyenne"] or 0 for x in comp) / len(comp)) if comp else None,
            "ecartTypeMoyennes": ecart_type([x["moyenne"] for x in comp]), "g": gg, "f": ff,
            "ecartGenre": js_round(ff["taux"] - gg["taux"], 1) if gg["taux"] is not None and ff["taux"] is not None else None,
            "matieres": mats, "fortes": classees[:3], "faibles": list(reversed(classees[-3:]))}


def recommandations(b):
    s = []
    if not b["composes"]:
        return ["Aucun candidat n'a composé : les notes ne sont pas encore saisies."]
    if b["absents"]:
        s.append(f"{b['absents']} candidat(s) inscrit(s) n’ont pas composé : en rechercher la cause avec les écoles concernées avant la session officielle.")
    if b["taux"] is not None and b["taux"] < 60:
        s.append(f"Le taux de réussite au seuil s’établit à {js_txt(b['taux'])} %, en deçà de 60 % : organiser une remédiation ciblée avant la session de juin.")
    elif b["taux"] is not None and b["taux"] >= 85:
        s.append(f"Le taux de réussite atteint {js_txt(b['taux'])} % : consolider les acquis et maintenir le rythme des révisions.")
    for m in b["faibles"]:
        if m["taux"] is not None and m["taux"] < 60:
            s.append(f"En {m['libelle']}, {js_txt(m['taux'])} % de maîtrise seulement (moyenne {js_txt(m['moyenne'])}/20) : programmer une séance "
                     "d’animation pédagogique sur cette épreuve.")
    if b["fortes"] and b["fortes"][0]["taux"] is not None and b["fortes"][0]["taux"] >= 80:
        s.append(f"L’épreuve la mieux réussie est {b['fortes'][0]['libelle']} ({js_txt(b['fortes'][0]['taux'])} %) : s’appuyer sur les pratiques "
                 "des maîtres concernés.")
    if b["ecartGenre"] is not None and abs(b["ecartGenre"]) >= 10:
        s.append(f"L’écart de réussite entre filles et garçons atteint {js_txt(abs(b['ecartGenre']))} points au détriment des "
                 f"{'filles' if b['ecartGenre'] < 0 else 'garçons'} : en tenir compte dans l'accompagnement.")
    if b["ecartTypeMoyennes"] >= 3:
        s.append(f"Les moyennes s’étalent fortement (écart type de {js_txt(b['ecartTypeMoyennes'])} points) : le centre réunit des niveaux très "
                 "inégaux, un soutien individualisé est à prévoir.")
    return s or ["Les résultats du centre n’appellent pas d’observation particulière."]


def sexe_de(v):
    t = R._norm(v).strip()
    if t in ("m", "g", "masculin", "garcon", "homme"):
        return "G"
    if t in ("f", "feminin", "fille", "femme"):
        return "F"
    return ""


def num_txt(x):
    return "" if x is None else (str(int(x)) if float(x) == int(x) else f"{x:g}".replace(".", ","))


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.DROITS["examen_blanc"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent", "enseignant"}
    R.types_documents({"examen_blanc_pv": "Procès-verbal d'examen blanc du centre", "examen_blanc_releve": "Relevé de notes du centre (examen blanc)",
                       "examen_blanc_resultats": "Résultats de l'examen blanc"})
    H.schema("""CREATE TABLE IF NOT EXISTS eb_centres (id INTEGER PRIMARY KEY, portee INTEGER NOT NULL, session TEXT, nom TEXT NOT NULL, chef TEXT,
                date TEXT, niveau TEXT, entite TEXT, cree_le TEXT, maj TEXT);
                CREATE TABLE IF NOT EXISTS eb_candidats (id INTEGER PRIMARY KEY, centre_id INTEGER NOT NULL REFERENCES eb_centres(id) ON DELETE CASCADE,
                ordre INTEGER, nom TEXT NOT NULL, sexe TEXT, ecole_cle TEXT, ecole TEXT, notes TEXT, maj TEXT);
                CREATE INDEX IF NOT EXISTS ix_eb_centres ON eb_centres(portee, session);""")

    def portee():
        return R.cle_portee("structure")

    def peut_ecrire():
        role = g.user["role"]
        return role in ("admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp") and not (
            H.config.EDITION == "enseignant" and role == "enseignant")

    def session_req():
        v = (request.values.get("session") or "").strip()
        return v if re.fullmatch(r"\d{4}-\d{4}", v) else R.annee_active()

    def centres(session):
        return [dict(c) for c in q("SELECT * FROM eb_centres WHERE portee=? AND session=? ORDER BY nom", (portee(), session))]

    def centre(cid):
        c = q("SELECT * FROM eb_centres WHERE id=? AND portee=?", (cid, portee()), un=True)
        if not c:
            abort(404)
        return dict(c)

    def candidats(cid):
        out = []
        for x in q("SELECT * FROM eb_candidats WHERE centre_id=? ORDER BY COALESCE(ordre, 9999), nom", (cid,)):
            d = dict(x)
            try:
                d["notes"] = json.loads(d["notes"] or "{}")
            except ValueError:
                d["notes"] = {}
            out.append(d)
        return out

    def exiger():
        if not peut_ecrire():
            abort(403)

    def ecoles_perimetre():
        if not R.juridiction():
            return [R.entite_courante()[1]]
        return R.liste_ecoles()

    @app.route("/examen-blanc", methods=["GET", "POST"])
    @H.connexion_requise("examen_blanc")
    def examen_blanc():
        s = session_req()
        if request.method == "POST":
            exiger()
            act = request.form.get("action")
            niv, ent = R.entite_courante()
            if act == "proposer" and not centres(s):
                noms = CENTRES_POBE if (niv == "CS" and "pob" in R._norm(ent)) else [f"Centre de {ent}" if ent else "Centre d'examen blanc"]
                for n in noms:
                    ex("INSERT INTO eb_centres (portee, session, nom, niveau, entite, cree_le, maj) VALUES (?,?,?,?,?,?,?)",
                       (portee(), s, n, niv, ent, H.maintenant(), H.maintenant()))
                flash(f"{len(noms)} centre(s) proposé(s) : renommez-les ou complétez le chef de centre et la date.", "success")
            elif act == "centre":
                cid = request.form.get("cid", type=int)
                d = {k: (request.form.get(k) or "").strip()[:200] for k in ("nom", "chef", "date")}
                if not d["nom"]:
                    flash("Le nom du centre est obligatoire.", "danger")
                elif cid:
                    centre(cid)
                    ex("UPDATE eb_centres SET nom=?, chef=?, date=?, maj=? WHERE id=?", (d["nom"], d["chef"], d["date"], H.maintenant(), cid))
                    flash("Centre modifié.", "success")
                else:
                    ex("INSERT INTO eb_centres (portee, session, nom, chef, date, niveau, entite, cree_le, maj) VALUES (?,?,?,?,?,?,?,?,?)",
                       (portee(), s, d["nom"], d["chef"], d["date"], niv, ent, H.maintenant(), H.maintenant()))
                    flash("Centre ajouté.", "success")
            elif act == "supprimer":
                cid = request.form.get("cid", type=int)
                centre(cid)
                ex("DELETE FROM eb_candidats WHERE centre_id=?", (cid,))
                ex("DELETE FROM eb_centres WHERE id=?", (cid,))
                flash("Centre supprimé.", "success")
            return redirect(url_for("examen_blanc", session=s))
        lignes = []
        for c in centres(s):
            b = bilan(candidats(c["id"]))
            lignes.append((c, b))
        return render_template("examen_blanc.html", s=s, lignes=lignes, annees=R.annees_proposees([s]), peut_ecrire=peut_ecrire(),
                               editer=request.args.get("modifier", type=int), num=num_txt, R=R)

    @app.route("/examen-blanc/centre/<int:cid>", methods=["GET", "POST"])
    @H.connexion_requise("examen_blanc")
    def examen_blanc_centre(cid):
        c = centre(cid)
        if request.method == "POST":
            exiger()
            act = request.form.get("action")
            if act == "notes":
                for x in candidats(cid):
                    d = {}
                    for k, _l, _a in MATIERES:
                        v = (request.form.get(f"n_{x['id']}_{k}") or "").strip().replace(",", ".")
                        if v:
                            try:
                                f = float(v)
                            except ValueError:
                                continue
                            if 0 <= f <= 20:
                                d[k] = round(f * 4) / 4          # au quart de point
                    ex("UPDATE eb_candidats SET notes=?, maj=? WHERE id=?", (json.dumps(d), H.maintenant(), x["id"]))
                flash("Notes enregistrées.", "success")
            elif act == "candidat":
                nom = (request.form.get("nom") or "").strip()
                if not nom:
                    flash("Nom et prénoms obligatoires.", "danger")
                else:
                    n = q("SELECT COALESCE(MAX(ordre),0)+1 n FROM eb_candidats WHERE centre_id=?", (cid,), un=True)["n"]
                    ex("INSERT INTO eb_candidats (centre_id, ordre, nom, sexe, ecole, notes, maj) VALUES (?,?,?,?,?,?,?)",
                       (cid, n, nom, sexe_de(request.form.get("sexe")), (request.form.get("ecole") or "").strip(), "{}", H.maintenant()))
                    flash("Candidat ajouté.", "success")
            elif act == "supprimer":
                ex("DELETE FROM eb_candidats WHERE id=? AND centre_id=?", (request.form.get("candidat", type=int), cid))
                flash("Candidat supprimé.", "success")
            elif act == "reinitialiser":
                ex("DELETE FROM eb_candidats WHERE centre_id=?", (cid,))
                flash("Liste des candidats du centre réinitialisée.", "success")
            elif act == "cep":
                n = reprendre_cep(c, (request.form.get("session_cep") or "").strip(), (request.form.get("centre_cep") or "").strip())
                flash(f"{n} candidat(s) repris de la liste du CEP.", "success" if n else "warning")
            return redirect(url_for("examen_blanc_centre", cid=cid))
        cands = candidats(cid)
        b = bilan(cands)
        try:
            sessions_cep = [x["session"] for x in q("SELECT DISTINCT session FROM reg_examens_candidats WHERE portee=? AND session IS NOT NULL", (portee(),))]
            centres_cep = [x["centre"] for x in q("SELECT DISTINCT centre FROM reg_examens_candidats WHERE portee=? AND COALESCE(centre,'')<>''", (portee(),))]
        except Exception:  # noqa: BLE001
            sessions_cep, centres_cep = [], []
        return render_template("examen_blanc_centre.html", c=c, b=b, recos=recommandations(b), MATIERES=MATIERES, peut_ecrire=peut_ecrire(),
                               num=num_txt, sessions_cep=sessions_cep, centres_cep=centres_cep, ecoles=ecoles_perimetre())

    def cle_de_matiere(nom):
        """Matière de l'examen blanc libre -> épreuve du modèle commun (None si aucune correspondance sûre)."""
        t = R._norm(nom).strip()
        for k, lib, abr in MATIERES:
            if t in (R._norm(lib).strip(), R._norm(abr).strip(), k):
                return k
        alias = ALIAS.get(t)
        if alias:
            for k, lib, _a in MATIERES:
                if lib == alias:
                    return k
        regles = [(r"dict", "dictee"), (r"compr", "comprehension"), (r"expr|redac|communic", "communication"), (r"math|calcul", "maths"),
                  (r"scien|\best\b", "est"), (r"social|histoire|geo|\bes\b|civi|moral", "es"), (r"\beps\b|physique", "eps"),
                  (r"chant|poes|conte|vivant", "ea_vivant"), (r"dessin|couture|plast|artist", "ea_artistique")]
        for motif, k in regles:
            if re.search(motif, t):
                return k
        return None

    @app.route("/examen-blanc/reprendre-libre/<int:sid>", methods=["POST"])
    @H.connexion_requise("examen_blanc")
    def examen_blanc_reprendre_libre(sid):
        """v1.33 : verse une session de l'examen blanc libre de l'école dans un centre de l'examen blanc commun
        (candidats et notes des matières reconnues ; la session libre est conservée telle quelle)."""
        exiger()
        s = q("SELECT * FROM cep_blanc_sessions WHERE id=? AND ecole_id=?", (sid, H.eco()), un=True)
        if not s:
            abort(404)
        try:
            mats = [str(m) for m in json.loads(s["matieres"] or "[]")]
        except ValueError:
            mats = []
        corr = {m: cle_de_matiere(m) for m in mats}
        niv, ent = R.entite_courante()
        session_cible = s["annee"] if re.fullmatch(r"\d{4}-\d{4}", s["annee"] or "") else R.annee_active()
        nom = f"{s['centre'] or ent or 'Centre'} — examen blanc libre n° {s['numero'] or 1}"
        cid = ex("INSERT INTO eb_centres (portee, session, nom, chef, date, niveau, entite, cree_le, maj) VALUES (?,?,?,?,?,?,?,?,?)",
                 (portee(), session_cible, nom[:200], s["chef_centre"] or "", s["date_signature"] or "", niv, ent, H.maintenant(), H.maintenant()))
        n = 0
        for x in q("SELECT * FROM cep_blanc_candidats WHERE session_id=? ORDER BY COALESCE(numero_table,''), nom", (sid,)):
            try:
                brut = json.loads(x["notes"] or "{}")
            except ValueError:
                brut = {}
            notes = {}
            for m, v in brut.items():
                k = corr.get(m) or cle_de_matiere(m)
                if k and isinstance(v, (int, float)) and 0 <= v <= 20 and k not in notes:
                    notes[k] = round(float(v) * 4) / 4
            n += 1
            ex("INSERT INTO eb_candidats (centre_id, ordre, nom, sexe, ecole, notes, maj) VALUES (?,?,?,?,?,?,?)",
               (cid, n, f"{x['nom']} {x['prenoms'] or ''}".strip(), sexe_de(x["sexe"]), x["ecole"] or "", json.dumps(notes), H.maintenant()))
        ignorees = [m for m, k in corr.items() if not k]
        H.journal("examen_blanc_reprise_libre", f"session {sid} -> centre {cid} ({n} candidats)")
        flash(f"{n} candidat(s) repris dans l'examen blanc commun (centre « {nom} »)."
              + (f" Matières sans équivalent, non reprises : {', '.join(ignorees)}." if ignorees else ""), "success")
        return redirect(url_for("examen_blanc_centre", cid=cid))

    def reprendre_cep(c, session_cep, centre_cep):
        sql, a = "SELECT * FROM reg_examens_candidats WHERE portee=?", [portee()]
        if session_cep:
            sql += " AND session=?"
            a.append(session_cep)
        if centre_cep:
            sql += " AND lower(COALESCE(centre,''))=lower(?)"
            a.append(centre_cep)
        try:
            rows = q(sql + " ORDER BY entite, nom, prenoms", tuple(a))
        except Exception:  # noqa: BLE001
            return 0
        deja = {R._norm(x["nom"]).strip() for x in q("SELECT nom FROM eb_candidats WHERE centre_id=?", (c["id"],))}
        n = q("SELECT COALESCE(MAX(ordre),0) n FROM eb_candidats WHERE centre_id=?", (c["id"],), un=True)["n"]
        k = 0
        for x in rows:
            nom = f"{x['nom']} {x['prenoms'] or ''}".strip()
            if R._norm(nom).strip() in deja:
                continue
            n += 1
            ex("INSERT INTO eb_candidats (centre_id, ordre, nom, sexe, ecole, notes, maj) VALUES (?,?,?,?,?,?,?)",
               (c["id"], n, nom, sexe_de(x["sexe"]), x["entite"] or "", "{}", H.maintenant()))
            deja.add(R._norm(nom).strip())
            k += 1
        return k

    # ------------------------------------------------------------------ Excel
    def lignes_export(cands, b):
        rows = []
        for i, x in enumerate(b["classes"], 1):
            cd = x["candidat"]
            rows.append([cd.get("ordre") or i, cd["nom"], cd.get("sexe") or "", cd.get("ecole") or ""] + [("" if n is None else n) for n in x["notes"]]
                        + [x["total"] if x["aCompose"] else "", x["moyenne"] if x["moyenne"] is not None else "", x["maitrises"] if x["aCompose"] else "",
                           ("oui" if x["admis"] else "non") if x["aCompose"] else "absent", x["rang"] or ""])
        return rows

    def feuille_matieres(b):
        return [[m["libelle"], m["notes"], m["moyenne"], m["maitrises"], m["taux"], m["ecartType"]] for m in b["matieres"]]

    def ligne_synthese(c, b):
        return [c["nom"], b["g"]["inscrits"], b["f"]["inscrits"], b["inscrits"], b["composes"], b["admis"], b["g"]["taux"] if b["g"]["taux"] is not None else "",
                b["f"]["taux"] if b["f"]["taux"] is not None else "", b["taux"] if b["taux"] is not None else "",
                b["moyenneCentre"] if b["moyenneCentre"] is not None else "", b["ecartTypeMoyennes"]]
    ENT_MAT = ["Épreuve", "Composé", "Moyenne", "Maîtrises", "Taux (%)", "Écart type"]
    ENT_SYN = ["Centre", "Inscrits G", "Inscrits F", "Inscrits", "Ont composé", "Ont atteint le seuil", "Taux G (%)", "Taux F (%)", "Taux (%)", "Moyenne", "Écart type"]

    @app.route("/examen-blanc/centre/<int:cid>.xlsx")
    @H.connexion_requise("examen_blanc")
    def examen_blanc_xlsx(cid):
        c = centre(cid)
        cands = candidats(cid)
        b = bilan(cands)
        return H.xlsx.reponse_classeur(f"examen_blanc_{re.sub(r'[^A-Za-z0-9]+', '_', R._norm(c['nom']))}.xlsx",
                                       [("Candidats à l'examen blanc", ENT_EXPORT, lignes_export(cands, b), {}),
                                        ("Résultats par épreuve", ENT_MAT, feuille_matieres(b), {}), ("Synthèse des centres", ENT_SYN, [ligne_synthese(c, b)], {})])

    @app.route("/examen-blanc.xlsx")
    @H.connexion_requise("examen_blanc")
    def examen_blanc_tous_xlsx():
        s = session_req()
        syn = [ligne_synthese(c, bilan(candidats(c["id"]))) for c in centres(s)]
        return H.xlsx.reponse_classeur(f"examen_blanc_{s}.xlsx", [("Synthèse des centres", ENT_SYN, syn, {})])

    @app.route("/examen-blanc/centre/<int:cid>/modele.xlsx")
    @H.connexion_requise("examen_blanc")
    def examen_blanc_modele(cid):
        centre(cid)
        return H.xlsx.reponse_classeur("candidats_examen_blanc.xlsx", [("Candidats à l'examen blanc", ENT_IMPORT, [], {})])

    @app.route("/examen-blanc/centre/<int:cid>/import", methods=["POST"])
    @H.connexion_requise("examen_blanc")
    def examen_blanc_import(cid):
        import outils_xlsx as X
        exiger()
        centre(cid)
        f = request.files.get("fichier")
        try:
            wb = X._openpyxl().load_workbook(io.BytesIO(f.read()), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            flash("Fichier illisible : utilisez le modèle « Candidats à l'examen blanc ».", "danger")
            return redirect(url_for("examen_blanc_centre", cid=cid))
        ws = next((w for w in wb.worksheets if X.normaliser(w.title).startswith("candidats")), wb.worksheets[0])
        rows = [list(x) for x in ws.iter_rows(values_only=True)]
        canon = {X.normaliser(l): l for l in ENT_EXPORT}
        canon.update({k: v for k, v in ALIAS.items()})

        def tete(v):
            n = X.normaliser(v)
            return canon.get(n) or canon.get(n.replace("’", "'"))
        i0 = next((i for i, x in enumerate(rows[:12]) if x and sum(1 for v in x if tete(v)) >= 3), None)
        if i0 is None:
            flash("En-têtes introuvables : utilisez le modèle « Candidats à l'examen blanc ».", "danger")
            return redirect(url_for("examen_blanc_centre", cid=cid))
        idx = {tete(v): j for j, v in enumerate(rows[i0]) if tete(v)}
        exist = {R._norm(x["nom"]).strip(): x for x in candidats(cid)}
        n_aj, n_maj = 0, 0
        for x in rows[i0 + 1:]:
            if not x or not any(v not in (None, "") for v in x):
                continue
            nom = str(X.valeur(x, idx.get("Nom et prénoms")) or "").strip() if "Nom et prénoms" in idx else ""
            if not nom:
                continue
            notes = {}
            for k, l, _a in MATIERES:
                if l in idx:
                    v = X.valeur(x, idx[l])
                    try:
                        fv = float(str(v).replace(",", ".")) if v not in (None, "") else None
                    except ValueError:
                        fv = None
                    if fv is not None and 0 <= fv <= 20:
                        notes[k] = round(fv * 4) / 4
            sexe = sexe_de(X.valeur(x, idx["Sexe"])) if "Sexe" in idx else ""
            ecole = str(X.valeur(x, idx.get("École de provenance")) or "").strip() if "École de provenance" in idx else ""
            ordre = X.valeur(x, idx["N° d’ordre"]) if "N° d’ordre" in idx else None
            try:
                ordre = int(float(ordre)) if ordre not in (None, "") else None
            except ValueError:
                ordre = None
            old = exist.get(R._norm(nom).strip())
            if old:
                ex("UPDATE eb_candidats SET ordre=COALESCE(?, ordre), sexe=COALESCE(NULLIF(?,''), sexe), ecole=COALESCE(NULLIF(?,''), ecole), notes=?, maj=? WHERE id=?",
                   (ordre, sexe, ecole, json.dumps(dict(old["notes"], **notes)), H.maintenant(), old["id"]))
                n_maj += 1
            else:
                if ordre is None:
                    ordre = q("SELECT COALESCE(MAX(ordre),0)+1 n FROM eb_candidats WHERE centre_id=?", (cid,), un=True)["n"]
                ex("INSERT INTO eb_candidats (centre_id, ordre, nom, sexe, ecole, notes, maj) VALUES (?,?,?,?,?,?,?)",
                   (cid, ordre, nom, sexe, ecole, json.dumps(notes), H.maintenant()))
                n_aj += 1
        flash(f"Import : {n_aj} candidat(s) ajouté(s), {n_maj} mis à jour.", "success")
        return redirect(url_for("examen_blanc_centre", cid=cid))

    # ------------------------------------------------------------------ documents signés
    def sigs_centre(c):
        return [R.signature_vide("Le chef de centre", c.get("chef") or ""), R.signature_autorite("Visa de l'autorité")]

    def table_notes(b, avec_resultats=True):
        ent = ["N°", "Nom et prénoms", "S", "École"] + [a for _k, _l, a in MATIERES] + (["Total", "Moy.", "Maît.", "Seuil", "Rang"] if avec_resultats else [])
        rows = []
        for i, x in enumerate(sorted(b["classes"], key=lambda x: (x["rang"] is None, x["rang"] or 0, R._norm(x["candidat"]["nom"]))), 1):
            cd = x["candidat"]
            rows.append([i, cd["nom"], cd.get("sexe") or "", cd.get("ecole") or ""] + [num_txt(n) for n in x["notes"]]
                        + ([num_txt(x["total"]) if x["aCompose"] else "", num_txt(x["moyenne"]), x["maitrises"] if x["aCompose"] else "",
                            ("oui" if x["admis"] else "non") if x["aCompose"] else "absent", x["rang"] or ""] if avec_resultats else []))
        larg = [0.4, 2.6, 0.3, 1.8] + [0.55] * 9 + ([0.6, 0.6, 0.45, 0.6, 0.45] if avec_resultats else [])
        return R.tableau(ent, rows, larg, R.largeur_utile(True), taille=6.4)

    def participation(b):
        return R.tableau(["", "Garçons", "Filles", "Total"], [["Inscrits", b["g"]["inscrits"], b["f"]["inscrits"], b["inscrits"]],
                                                              ["Ont composé", b["g"]["composes"], b["f"]["composes"], b["composes"]],
                                                              ["Ont atteint le seuil", b["g"]["admis"], b["f"]["admis"], b["admis"]],
                                                              ["Taux (%)", num_txt(b["g"]["taux"]), num_txt(b["f"]["taux"]), num_txt(b["taux"])]],
                         [1.6, 1, 1, 1], R.largeur_utile(True) / 2)

    @app.route("/examen-blanc/centre/<int:cid>/<doc>.pdf")
    @H.connexion_requise("examen_blanc")
    def examen_blanc_pdf(cid, doc):
        from reportlab.platypus import Paragraph, Spacer
        if doc not in ("pv", "releve"):
            abort(404)
        c = centre(cid)
        cands = candidats(cid)
        b = bilan(cands)
        st = R.styles()
        tete = Paragraph(f"<b>{R.esc(c['nom'])}</b> — session {R.esc(c['session'] or '')}{' — chef de centre : ' + R.esc(c['chef']) if c.get('chef') else ''}"
                         f"{' — composition du ' + R.esc(c['date']) if c.get('date') else ''}", st["p"])
        rappel = Paragraph(f"Maîtrise : note ≥ {SEUIL_MATIERE}/20. Seuil atteint : au moins {MAITRISES_REQUISES} épreuves maîtrisées sur 9 "
                           "(sur 8 pour un candidat dispensé d'EPS). Une épreuve non composée ne compte pas zéro.", st["petit"])
        if doc == "pv":
            corps = [tete, Spacer(1, 4), table_notes(b), Spacer(1, 6), Paragraph("Participation et réussite", st["h2"]), participation(b), Spacer(1, 4), rappel,
                     Paragraph("Recommandations", st["h2"])] + [Paragraph("– " + R.esc(t), st["p"]) for t in recommandations(b)]
            titre = "PROCÈS-VERBAL D'EXAMEN BLANC"
        else:
            mats = R.tableau(["Épreuve", "Composé", "Moyenne", "Maîtrises", "Taux (%)", "Écart type"],
                             [[m["libelle"], m["notes"], num_txt(m["moyenne"]), m["maitrises"], num_txt(m["taux"]), num_txt(m["ecartType"])] for m in b["matieres"]],
                             [2, 1, 1, 1, 1, 1], R.largeur_utile(True) * 0.7)
            corps = [tete, Spacer(1, 4), table_notes(b), Spacer(1, 6), Paragraph("Résultats par épreuve", st["h2"]), mats,
                     Paragraph("Épreuves fortes : " + R.esc(", ".join(f"{m['libelle']} ({num_txt(m['moyenne'])})" for m in b["fortes"])) + " — épreuves faibles : "
                               + R.esc(", ".join(f"{m['libelle']} ({num_txt(m['moyenne'])})" for m in b["faibles"])), st["p"]), rappel]
            titre = "RELEVÉ DE NOTES DU CENTRE — EXAMEN BLANC"
        contenu = json.dumps([c["nom"], c["session"], [(x["nom"], x.get("sexe"), x.get("ecole"), x["notes"]) for x in cands]], ensure_ascii=False, sort_keys=True)
        import hashlib
        code = R.code_document("examen_blanc_" + doc, f"{titre.title()} — {c['nom']} ({b['inscrits']} candidat(s))",
                               "eb:" + doc + ":" + hashlib.sha1(contenu.encode()).hexdigest())
        return H.pdf_reponse(R.pdf_document(titre, corps, sigs_centre(c), code, True), f"examen_blanc_{doc}_{cid}.pdf")

    @app.route("/examen-blanc/resultats.pdf")
    @H.connexion_requise("examen_blanc")
    def examen_blanc_resultats_pdf():
        from reportlab.platypus import Paragraph
        s = session_req()
        lignes, tous = [], []
        for c in centres(s):
            cands = candidats(c["id"])
            tous += cands
            b = bilan(cands)
            lignes.append([c["nom"]] + [num_txt(v) if isinstance(v, float) else v for v in ligne_synthese(c, b)[1:]])
        bt = bilan(tous)
        lignes.append(["Ensemble", bt["g"]["inscrits"], bt["f"]["inscrits"], bt["inscrits"], bt["composes"], bt["admis"], num_txt(bt["g"]["taux"]),
                       num_txt(bt["f"]["taux"]), num_txt(bt["taux"]), num_txt(bt["moyenneCentre"]), num_txt(bt["ecartTypeMoyennes"])])
        corps = [Paragraph(f"Session {R.esc(s)} — {len(lignes) - 1} centre(s), {bt['inscrits']} candidat(s).", R.styles()["p"]),
                 R.tableau(ENT_SYN, lignes, [2.4] + [0.8] * 10, R.largeur_utile(True))]
        contenu = json.dumps([[c["nom"] for c in centres(s)], [(x["nom"], x["notes"]) for x in tous]], ensure_ascii=False, sort_keys=True)
        import hashlib
        code = R.code_document("examen_blanc_resultats", f"Résultats de l'examen blanc — {s}", "ebr:" + hashlib.sha1(contenu.encode()).hexdigest())
        return H.pdf_reponse(R.pdf_document("RÉSULTATS DE L'EXAMEN BLANC", corps, [R.signature_autorite()], code, True), f"examen_blanc_resultats_{s}.pdf")

    # ------------------------------------------------------------------ tableau de bord du pilotage
    def synthese_ecoles(annee=None):
        """{école de provenance: {"ebComposes", "ebAdmis", "ebTaux"}} pour les centres de l'année."""
        out = {}
        for c in centres(annee or R.annee_active()):
            for x in classer(candidats(c["id"])):
                e = out.setdefault(x["candidat"].get("ecole") or "—", {"ebComposes": 0, "ebAdmis": 0})
                e["ebComposes"] += 1 if x["aCompose"] else 0
                e["ebAdmis"] += 1 if x["admis"] else 0
        for e in out.values():
            e["ebTaux"] = js_round(e["ebAdmis"] / e["ebComposes"] * 100, 1) if e["ebComposes"] else None
        return out
    H.examen_blanc_synthese = synthese_ecoles
