# -*- coding: utf-8 -*-
"""Comité d'évaluation, élaboration des épreuves et grilles (APC, Bénin). Toutes éditions ; données par école.

* /epreuves                                  epreuves_accueil         liste des épreuves (filtres : année, type, niveau,
                                                                      matière, statut) ; onglets Comité · Épreuves · Grilles
* /epreuves/<id>                  GET/POST   epreuve_form             nouvelle épreuve (id 0) / modification : métadonnées,
                                                                      situation, consignes, items (barème = Σ items)
* /epreuves/<id>/supprimer             POST  epreuve_supprimer
* /epreuves/<id>/dupliquer             POST  epreuve_dupliquer        copie (brouillon) avec ses items
* /epreuves/<id>/statut                POST  epreuve_statut           brouillon → validée → administrée (et retour)
* /epreuves/<id>.pdf[?corrige=1]             epreuve_pdf              sujet (en-tête école, situation, consignes, items
                                                                      numérotés avec barème) ; variante corrigé
* /epreuves/<id>/bareme.pdf                  epreuve_bareme_pdf       barème / grille de correction de l'épreuve
* /epreuves/<id>/items/import          POST  epreuve_items_import     import Excel des items
* /epreuves/items-modele.xlsx                epreuve_items_modele_xlsx
* /epreuves/liste.xlsx                       epreuves_xlsx            export de la liste
* /epreuves/comite                           epreuves_comite          membres du comité d'évaluation de l'année
* /epreuves/comite/<id>           GET/POST   epreuves_membre          fiche membre (id 0 = nouveau)
* /epreuves/comite/<id>/supprimer      POST  epreuves_membre_supprimer
* /epreuves/comite.pdf | .xlsx               epreuves_comite_pdf / epreuves_comite_xlsx
* /epreuves/comite/import         GET/POST   epreuves_comite_import   import Excel (modèle : epreuves_comite_modele_xlsx)
* /epreuves/grilles                          epreuves_grilles         grilles de correction / d'évaluation / d'observation
* /epreuves/grilles/<id>          GET/POST   grille_form              nouvelle (id 0, ?modele=…) / modification
* /epreuves/grilles/<id>/supprimer     POST  grille_supprimer
* /epreuves/grilles/<id>/dupliquer     POST  grille_dupliquer
* /epreuves/grilles/<id>.pdf                 grille_pdf
* /epreuves/grilles.xlsx                     grilles_xlsx

Interface : H.epreuves_liste(ecole_id, annee) -> [dict épreuve + "items" (liste) + "bareme_items"].
Droits : lecture pour tout utilisateur connecté ; écriture « epreuves » (admin, directeur, enseignant).

Règles
* Types d'évaluation : ceux du moteur des évaluations (diagnostique, formative, sommative d'étape, certificative)
  + examen blanc. Niveaux : maternelle, CI…CM2, 6ème…Tle. Matières : table « matieres » (code + libellé copiés).
* Barème d'une épreuve = somme des barèmes de ses items ; si un barème total différent a été déclaré, une alerte
  est affichée (le total déclaré n'est jamais corrigé automatiquement).
* Statuts : brouillon (modifiable) → validée (par le comité) → administrée (passée en classe). Une épreuve validée ou
  administrée reste modifiable par les ayants droit, mais la page le signale.
* Grilles types APC (chargeables puis adaptables) : production écrite (pertinence 3, cohérence 3, correction de la
  langue 2, perfectionnement 2), mathématiques (compréhension, démarche, résultat, présentation), sciences / EST
  (pertinence, démarche, exactitude, communication), maternelle (grille d'observation : Acquis / En cours
  d'acquisition / Non acquis par indicateur, sans barème).
"""
import json
from datetime import date, datetime

from flask import abort, flash, g, redirect, render_template, request, url_for

import evaluations_core as EC
from calcul import NIVEAUX_MATERNELLE, NIVEAUX_PRIMAIRE, NIVEAUX_SECONDAIRE, cycle_du_niveau

TYPES_EVAL = dict(EC.TYPES, examen_blanc="Examen blanc")
NIVEAUX = NIVEAUX_MATERNELLE + NIVEAUX_PRIMAIRE + NIVEAUX_SECONDAIRE
STATUTS = {"brouillon": "Brouillon", "validee": "Validée", "administree": "Administrée"}
QUALITES = ["Directeur / directrice", "Enseignant(e)", "Conseiller pédagogique (CP)", "Chef de circonscription (CCS)",
            "Parent d'élève", "Autre"]
FONCTIONS = ["Président(e)", "Vice-président(e)", "Rapporteur", "Membre", "Secrétaire", "Personne ressource"]
CRITERES = ["Pertinence de la production", "Cohérence de la production", "Correction de la langue",
            "Perfectionnement / originalité", "Compréhension de la situation", "Démarche / raisonnement",
            "Exactitude du résultat", "Présentation / soin", "Communication des résultats", "Autre critère"]
TYPES_GRILLE = {"correction": "Grille de correction", "evaluation": "Grille d'évaluation",
                "observation": "Grille d'observation (maternelle)"}
MAX_ITEMS = 100
MAX_LIGNES_GRILLE = 40
ENT_COMITE = ["Nom et prénoms", "Qualité", "Qualification (diplôme / grade / spécialité)", "Fonction dans le comité",
              "Classe ou niveau", "Contact", "Actif"]
ENT_ITEMS = ["N°", "Intitulé (question / consigne)", "Critère", "Indicateur", "Barème", "Réponse attendue"]
ENT_EPREUVES = ["N°", "Année", "Titre", "Type", "Numéro", "Niveau", "Matière", "Durée (min)", "Barème déclaré",
                "Barème des items", "Nb items", "Date prévue", "Auteur", "Statut"]
# modèles de grilles APC : code -> (titre, type, [(critère, [indicateurs], barème, observations)])
GRILLES_TYPES = {
    "production_ecrite": ("Grille de correction — production écrite (APC)", "correction", [
        ("Pertinence de la production", ["Respect du type de texte et de la consigne", "Prise en compte de la situation",
                                         "Idées en rapport avec le sujet"], 3, ""),
        ("Cohérence de la production", ["Enchaînement logique des idées", "Emploi des connecteurs", "Structure du texte (début, développement, fin)"], 3, ""),
        ("Correction de la langue", ["Orthographe d'usage et grammaticale", "Syntaxe et conjugaison", "Ponctuation"], 2, ""),
        ("Perfectionnement", ["Originalité des idées", "Richesse du vocabulaire", "Présentation et lisibilité"], 2, "")]),
    "mathematiques": ("Grille de correction — mathématiques (résolution de situation-problème)", "correction", [
        ("Compréhension de la situation", ["Identifie les données utiles", "Reformule la tâche ou la question"], 2, ""),
        ("Démarche / raisonnement", ["Choisit une démarche adaptée", "Enchaîne correctement les étapes", "Utilise les outils mathématiques appropriés"], 4, ""),
        ("Exactitude du résultat", ["Calculs justes", "Résultat conforme à la question", "Unité correcte"], 3, ""),
        ("Présentation / soin", ["Travail lisible et ordonné", "Réponse rédigée"], 1, "")]),
    "sciences": ("Grille de correction — éducation scientifique et technologique", "correction", [
        ("Pertinence", ["Réponses en rapport avec la question", "Mobilise les connaissances attendues"], 3, ""),
        ("Démarche", ["Observe, compare, classe", "Formule une hypothèse ou une explication"], 3, ""),
        ("Exactitude", ["Faits et vocabulaire scientifiques corrects"], 2, ""),
        ("Communication", ["Expression claire", "Schéma ou tableau lisible"], 2, "")]),
    "maternelle": ("Grille d'observation — maternelle (A / ECA / NA)", "observation", [
        ("Langage et communication", ["S'exprime en phrases simples", "Comprend une consigne", "Récite une comptine"], None, "A = acquis ; ECA = en cours d'acquisition ; NA = non acquis"),
        ("Éveil mathématique", ["Compte jusqu'à 10", "Compare des quantités", "Reconnaît les formes"], None, ""),
        ("Pré-lecture et pré-écriture", ["Reconnaît son prénom", "Tient correctement l'outil scripteur", "Trace des graphismes"], None, ""),
        ("Activités motrices et artistiques", ["Coordonne ses mouvements", "Participe aux activités de groupe"], None, "")]),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_comite (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL, annee TEXT NOT NULL,
    nom_prenoms TEXT NOT NULL, qualite TEXT, qualification TEXT, fonction_comite TEXT, classe_ou_niveau TEXT,
    contact TEXT, actif INTEGER NOT NULL DEFAULT 1, ordre INTEGER DEFAULT 0, cree_le TEXT, maj TEXT
);
CREATE TABLE IF NOT EXISTS epreuves (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL, annee TEXT NOT NULL,
    titre TEXT NOT NULL, type_evaluation TEXT NOT NULL, numero INTEGER DEFAULT 1, niveau TEXT, matiere_code TEXT,
    matiere TEXT, duree_minutes INTEGER, bareme_total REAL, date_prevue TEXT, situation TEXT, consignes TEXT,
    auteur TEXT, statut TEXT NOT NULL DEFAULT 'brouillon', cree_par INTEGER, cree_le TEXT, maj TEXT
);
CREATE TABLE IF NOT EXISTS epreuves_items (
    id INTEGER PRIMARY KEY, epreuve_id INTEGER NOT NULL REFERENCES epreuves(id) ON DELETE CASCADE,
    ordre INTEGER NOT NULL DEFAULT 1, intitule TEXT NOT NULL, critere TEXT, indicateur TEXT, bareme REAL,
    reponse_attendue TEXT
);
CREATE INDEX IF NOT EXISTS ix_epreuves_items ON epreuves_items(epreuve_id, ordre);
CREATE TABLE IF NOT EXISTS grilles (
    id INTEGER PRIMARY KEY, ecole_id INTEGER NOT NULL, annee TEXT NOT NULL,
    titre TEXT NOT NULL, niveau TEXT, matiere_code TEXT, matiere TEXT, type TEXT NOT NULL DEFAULT 'correction',
    contenu TEXT NOT NULL DEFAULT '{}', epreuve_id INTEGER, cree_le TEXT, maj TEXT
);
"""


# ============================================================ outils purs
def lire_reel(v, maxi=1000):
    s = str(v if v is not None else "").replace(",", ".").replace(" ", "").strip()
    if not s:
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return x if 0 <= x <= maxi else None


def lire_entier(v, maxi=100000):
    s = str(v if v is not None else "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return int(s) if s.isdigit() and int(s) <= maxi else None


def lire_date(v):
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    return None


def num(x):
    """3.0 -> « 3 », 2.5 -> « 2,5 »."""
    if x is None:
        return ""
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def lire_items(f):
    """Lignes d'items du formulaire (it_<i>_…) -> (liste de dict ordonnés, erreurs). Les lignes sans intitulé sont ignorées."""
    n = min(lire_entier(f.get("nb_items"), MAX_ITEMS) or 0, MAX_ITEMS)
    items, erreurs = [], []
    for i in range(n):
        intitule = (f.get(f"it_{i}_intitule") or "").strip()[:1000]
        if not intitule:
            continue
        brut = (f.get(f"it_{i}_bareme") or "").strip()
        bareme = lire_reel(brut)
        if brut and bareme is None:
            erreurs.append(f"Item {len(items) + 1} : barème invalide « {brut} ».")
        items.append({"ordre": len(items) + 1, "intitule": intitule, "critere": (f.get(f"it_{i}_critere") or "").strip()[:120],
                      "indicateur": (f.get(f"it_{i}_indicateur") or "").strip()[:300], "bareme": bareme,
                      "reponse_attendue": (f.get(f"it_{i}_reponse") or "").strip()[:1000]})
    return items, erreurs


def total_items(items):
    return round(sum(float(i["bareme"] or 0) for i in items), 2)


def lire_lignes_grille(f):
    """Lignes d'une grille (lg_<i>_…) -> liste [{critere, indicateurs: [...], bareme, observations}]."""
    n = min(lire_entier(f.get("nb_lignes"), MAX_LIGNES_GRILLE) or 0, MAX_LIGNES_GRILLE)
    lignes = []
    for i in range(n):
        critere = (f.get(f"lg_{i}_critere") or "").strip()[:200]
        if not critere:
            continue
        ind = [x.strip()[:200] for x in (f.get(f"lg_{i}_indicateurs") or "").splitlines() if x.strip()]
        lignes.append({"critere": critere, "indicateurs": ind[:20], "bareme": lire_reel(f.get(f"lg_{i}_bareme")),
                       "observations": (f.get(f"lg_{i}_observations") or "").strip()[:300]})
    return lignes


def grille_modele(code):
    titre, typ, lignes = GRILLES_TYPES[code]
    return {"titre": titre, "type": typ,
            "lignes": [{"critere": c, "indicateurs": list(ind), "bareme": b, "observations": o} for c, ind, b, o in lignes]}


def total_grille(lignes):
    return round(sum(float(l["bareme"] or 0) for l in lignes), 2)


def esc(t):
    return str("" if t is None else t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ============================================================ module
def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema(SCHEMA)

    # -------------------------------------------------------------- données
    def annee_choisie():
        a = (request.args.get("annee") or request.form.get("annee") or "").strip()
        return a if len(a) == 9 and a[:4].isdigit() and a[4] == "-" else H.config.ANNEE_ACTIVE

    def annees_disponibles(eid):
        a = {r["annee"] for r in q("SELECT DISTINCT annee FROM epreuves WHERE ecole_id=?", (eid,))}
        a |= {r["annee"] for r in q("SELECT DISTINCT annee FROM eval_comite WHERE ecole_id=?", (eid,))}
        a.add(H.config.ANNEE_ACTIVE)
        return sorted(a, reverse=True)

    def matieres():
        """Matières de tous les cycles, groupées pour la liste déroulante."""
        rows = q("SELECT * FROM matieres WHERE actif=1 ORDER BY cycle, ordre, nom")
        return [{"val": f"{m['code']}|{m['nom']}", "code": m["code"], "nom": m["nom"], "cycle": m["cycle"]} for m in rows]

    def membres(annee, tous=False):
        return q("SELECT * FROM eval_comite WHERE ecole_id=? AND annee=?" + ("" if tous else " AND actif=1") + " ORDER BY ordre, nom_prenoms",
                 (H.eco(), annee))

    def items_de(eid):
        return [dict(r) for r in q("SELECT * FROM epreuves_items WHERE epreuve_id=? ORDER BY ordre, id", (eid,))]

    def epreuve_ou_404(eid):
        e = q("SELECT * FROM epreuves WHERE id=? AND ecole_id=?", (eid, H.eco()), un=True)
        if not e:
            abort(404)
        return dict(e)

    def grille_ou_404(gid):
        gr = q("SELECT * FROM grilles WHERE id=? AND ecole_id=?", (gid, H.eco()), un=True)
        if not gr:
            abort(404)
        d = dict(gr)
        try:
            d["lignes"] = json.loads(gr["contenu"] or "{}").get("lignes", [])
        except ValueError:
            d["lignes"] = []
        return d

    def membre_ou_404(mid):
        m = q("SELECT * FROM eval_comite WHERE id=? AND ecole_id=?", (mid, H.eco()), un=True)
        if not m:
            abort(404)
        return m

    def ecrire_items(eid, items):
        db = H.get_db()
        db.execute("DELETE FROM epreuves_items WHERE epreuve_id=?", (eid,))
        db.executemany("INSERT INTO epreuves_items (epreuve_id, ordre, intitule, critere, indicateur, bareme, reponse_attendue) VALUES (?,?,?,?,?,?,?)",
                       [(eid, i["ordre"], i["intitule"], i["critere"] or None, i["indicateur"] or None, i["bareme"], i["reponse_attendue"] or None)
                        for i in items])
        db.commit()

    def ctx(onglet, **k):
        annee = annee_choisie()
        return dict(onglet=onglet, annee=annee, annees=annees_disponibles(H.eco()), modifiable=H.peut("epreuves"),
                    TYPES_EVAL=TYPES_EVAL, NIVEAUX=NIVEAUX, STATUTS=STATUTS, QUALITES=QUALITES, FONCTIONS=FONCTIONS,
                    CRITERES=CRITERES, TYPES_GRILLE=TYPES_GRILLE, GRILLES_TYPES=GRILLES_TYPES, num=num,
                    aujourdhui=date.today().isoformat(), **k)

    def signatures(v, auteur=None):
        P = H.pdfs
        titre_dir = v.get("directeur_titre") or "Directeur"
        titre_dir = f"{'LA' if titre_dir.lower().startswith('directrice') else 'LE'} {titre_dir.upper()}"
        sigs = []
        if auteur:
            sigs.append(("L'AUTEUR / LE COMITÉ", auteur, None, False))
        sigs.append((titre_dir, v.get("directeur_nom") or "", P.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")), True))
        return sigs

    # -------------------------------------------------------------- interface exposée
    def epreuves_liste(ecole_id, annee=None):
        annee = annee or H.config.ANNEE_ACTIVE
        res = []
        for e in q("SELECT * FROM epreuves WHERE ecole_id=? AND annee=? ORDER BY niveau, type_evaluation, numero, titre", (ecole_id, annee)):
            d = dict(e)
            d["items"] = items_de(e["id"])
            d["bareme_items"] = total_items(d["items"])
            d["type_libelle"] = TYPES_EVAL.get(e["type_evaluation"], e["type_evaluation"])
            res.append(d)
        return res

    H.epreuves_liste = epreuves_liste

    # -------------------------------------------------------------- épreuves : liste
    def filtre_epreuves(a):
        annee = annee_choisie()
        sql, params = "SELECT * FROM epreuves WHERE ecole_id=? AND annee=?", [H.eco(), annee]
        f = {"type": a.get("type", ""), "niveau": a.get("niveau", ""), "matiere": a.get("matiere", ""), "statut": a.get("statut", "")}
        if f["type"] in TYPES_EVAL:
            sql += " AND type_evaluation=?"
            params.append(f["type"])
        if f["niveau"]:
            sql += " AND niveau=?"
            params.append(f["niveau"])
        if f["matiere"]:
            sql += " AND matiere_code=?"
            params.append(f["matiere"])
        if f["statut"] in STATUTS:
            sql += " AND statut=?"
            params.append(f["statut"])
        liste = []
        for e in q(sql + " ORDER BY COALESCE(date_prevue, ''), niveau, titre", params):
            d = dict(e)
            d["items"] = items_de(e["id"])
            d["bareme_items"] = total_items(d["items"])
            liste.append(d)
        return liste, f, annee

    @app.route("/epreuves")
    @H.connexion_requise()
    def epreuves_accueil():
        liste, f, annee = filtre_epreuves(request.args)
        mats = sorted({(e["matiere_code"], e["matiere"]) for e in q("SELECT matiere_code, matiere FROM epreuves WHERE ecole_id=? AND matiere_code IS NOT NULL", (H.eco(),))})
        nb_comite = len(membres(annee))
        nb_grilles = q("SELECT COUNT(*) n FROM grilles WHERE ecole_id=? AND annee=?", (H.eco(), annee), un=True)["n"]
        return render_template("epreuves_accueil.html", **ctx("epreuves", liste=liste, f=f, mats=mats, nb_comite=nb_comite, nb_grilles=nb_grilles))

    # -------------------------------------------------------------- épreuves : fiche
    @app.route("/epreuves/<int:eid>", methods=["GET", "POST"])
    @H.connexion_requise("epreuves")
    def epreuve_form(eid):
        e = epreuve_ou_404(eid) if eid else None
        annee = e["annee"] if e else annee_choisie()
        if request.method == "POST":
            f = request.form
            titre = (f.get("titre") or "").strip()[:200]
            typ = f.get("type_evaluation") if f.get("type_evaluation") in TYPES_EVAL else None
            niveau = (f.get("niveau") or "").strip()[:40]
            code, _, lib = (f.get("matiere") or "").partition("|")
            duree = lire_entier(f.get("duree_minutes"), 600)
            bareme = lire_reel(f.get("bareme_total"), 1000)
            dp = lire_date(f.get("date_prevue"))
            items, erreurs = lire_items(f)
            if not titre:
                erreurs.append("Le titre de l'épreuve est obligatoire.")
            if not typ:
                erreurs.append("Choisissez le type d'évaluation.")
            if (f.get("duree_minutes") or "").strip() and duree is None:
                erreurs.append("Durée invalide (minutes, nombre entier).")
            if (f.get("bareme_total") or "").strip() and bareme is None:
                erreurs.append("Barème total invalide.")
            if (f.get("date_prevue") or "").strip() and not dp:
                erreurs.append("Date prévue invalide.")
            vals = {"titre": titre, "type_evaluation": typ, "numero": lire_entier(f.get("numero"), 99) or 1, "niveau": niveau or None,
                    "matiere_code": code.strip()[:20] or None, "matiere": lib.strip()[:120] or (code.strip()[:120] or None),
                    "duree_minutes": duree, "bareme_total": bareme, "date_prevue": dp.isoformat() if dp else None,
                    "situation": (f.get("situation") or "").strip()[:20000] or None, "consignes": (f.get("consignes") or "").strip()[:10000] or None,
                    "auteur": (f.get("auteur") or "").strip()[:120] or None,
                    "statut": f.get("statut") if f.get("statut") in STATUTS else (e["statut"] if e else "brouillon")}
            if erreurs:
                for x in erreurs:
                    flash(x, "danger")
                v = dict(vals, annee=annee, matiere_val=f.get("matiere", ""))
                return render_template("epreuves_form.html", **ctx("epreuves", v=v, obj=e, items=items, matieres=matieres(),
                                                                   membres=membres(annee), total=total_items(items))), 400
            cles = list(vals)
            if e:
                ex(f"UPDATE epreuves SET {', '.join(k + '=?' for k in cles)}, maj=? WHERE id=?", [vals[k] for k in cles] + [H.maintenant(), eid])
                flash(f"Épreuve « {titre} » mise à jour ({len(items)} item(s), barème {num(total_items(items))}).", "success")
            else:
                eid = ex(f"INSERT INTO epreuves (ecole_id, annee, {', '.join(cles)}, cree_par, cree_le, maj) VALUES ({', '.join('?' * (len(cles) + 5))})",
                         [H.eco(), annee] + [vals[k] for k in cles] + [g.user["id"], H.maintenant(), H.maintenant()])
                flash(f"Épreuve « {titre} » créée ({len(items)} item(s), barème {num(total_items(items))}).", "success")
            ecrire_items(eid, items)
            if bareme is not None and abs(bareme - total_items(items)) > 0.001:
                flash(f"Attention : barème déclaré {num(bareme)} ≠ somme des items {num(total_items(items))}.", "warning")
            H.journal("epreuve", f"#{eid} {titre}")
            return redirect(url_for("epreuve_form", eid=eid))
        if e:
            v = dict(e, matiere_val=f"{e['matiere_code']}|{e['matiere']}" if e["matiere_code"] else "")
            items = items_de(eid)
        else:
            v = {"annee": annee, "type_evaluation": request.args.get("type", "sommative"), "numero": 1, "statut": "brouillon",
                 "niveau": request.args.get("niveau", ""), "matiere_val": "", "bareme_total": 10,
                 "auteur": f"{g.user['nom']}" if g.get("user") else ""}
            items = []
        return render_template("epreuves_form.html", **ctx("epreuves", v=v, obj=e, items=items, matieres=matieres(),
                                                           membres=membres(annee), total=total_items(items)))

    @app.route("/epreuves/<int:eid>/supprimer", methods=["POST"])
    @H.connexion_requise("epreuves")
    def epreuve_supprimer(eid):
        e = epreuve_ou_404(eid)
        ex("DELETE FROM epreuves_items WHERE epreuve_id=?", (eid,))
        ex("DELETE FROM epreuves WHERE id=?", (eid,))
        ex("UPDATE grilles SET epreuve_id=NULL WHERE epreuve_id=?", (eid,))
        H.journal("epreuve_suppression", f"#{eid} {e['titre']}")
        flash(f"Épreuve « {e['titre']} » supprimée.", "warning")
        return redirect(url_for("epreuves_accueil", annee=e["annee"]))

    @app.route("/epreuves/<int:eid>/dupliquer", methods=["POST"])
    @H.connexion_requise("epreuves")
    def epreuve_dupliquer(eid):
        e = epreuve_ou_404(eid)
        cles = ["type_evaluation", "numero", "niveau", "matiere_code", "matiere", "duree_minutes", "bareme_total", "situation", "consignes", "auteur"]
        nid = ex(f"INSERT INTO epreuves (ecole_id, annee, titre, statut, {', '.join(cles)}, cree_par, cree_le, maj) VALUES ({', '.join('?' * (len(cles) + 7))})",
                 [H.eco(), annee_choisie() if request.form.get("annee") else e["annee"], f"{e['titre']} (copie)"[:200], "brouillon"]
                 + [e[k] for k in cles] + [g.user["id"], H.maintenant(), H.maintenant()])
        ecrire_items(nid, items_de(eid))
        H.journal("epreuve_duplication", f"#{eid} -> #{nid}")
        flash("Épreuve dupliquée (brouillon) : modifiez la copie.", "success")
        return redirect(url_for("epreuve_form", eid=nid))

    @app.route("/epreuves/<int:eid>/statut", methods=["POST"])
    @H.connexion_requise("epreuves")
    def epreuve_statut(eid):
        e = epreuve_ou_404(eid)
        st = request.form.get("statut")
        if st not in STATUTS:
            abort(400)
        if st == "validee" and not items_de(eid):
            flash("Impossible de valider une épreuve sans item.", "danger")
            return redirect(url_for("epreuve_form", eid=eid))
        ex("UPDATE epreuves SET statut=?, maj=? WHERE id=?", (st, H.maintenant(), eid))
        H.journal("epreuve_statut", f"#{eid} {e['statut']} -> {st}")
        flash(f"Épreuve « {e['titre']} » : {STATUTS[st].lower()}.", "success")
        return redirect(url_for("epreuve_form", eid=eid))

    # -------------------------------------------------------------- épreuves : PDF
    def entete_epreuve(e, v, items, corrige=False):
        return [("Type", f"{TYPES_EVAL.get(e['type_evaluation'], e['type_evaluation'])} n° {e['numero'] or 1}"),
                ("Niveau / cours", e["niveau"] or "—"), ("Matière", e["matiere"] or "—"),
                ("Durée", f"{e['duree_minutes']} min" if e["duree_minutes"] else "—"),
                ("Barème", f"{num(e['bareme_total'])} pts" if e["bareme_total"] is not None else f"{num(total_items(items))} pts"),
                ("Date", H.pdfs.date_fr(e["date_prevue"]) if e["date_prevue"] else "—"),
                ("École", v.get("ecole")), ("Année scolaire", e["annee"]),
                ("Statut", STATUTS.get(e["statut"], e["statut"]) + (" — CORRIGÉ" if corrige else ""))]

    @app.route("/epreuves/<int:eid>.pdf")
    @H.connexion_requise()
    def epreuve_pdf(eid):
        e = epreuve_ou_404(eid)
        items = items_de(eid)
        corrige = request.args.get("corrige") == "1"
        v = H.identification()
        P = H.pdfs
        from reportlab.platypus import Spacer
        avant = []
        if e["situation"]:
            avant += [P.paragraphe("SITUATION / TEXTE D'AMORCE", 9.5, True), P.paragraphe(esc(e["situation"]).replace("\n", "<br/>"), 9), Spacer(1, 4)]
        if e["consignes"]:
            avant += [P.paragraphe("CONSIGNES", 9.5, True), P.paragraphe(esc(e["consignes"]).replace("\n", "<br/>"), 9), Spacer(1, 4)]
        avant.append(P.paragraphe("ITEMS / TÂCHES", 9.5, True))
        if corrige:
            cols = ["N°", "Consigne / question", "Critère", "Barème", "Réponse attendue"]
            lignes = [[i["ordre"], esc(i["intitule"]), esc(i["critere"] or ""), num(i["bareme"]) if i["bareme"] is not None else "",
                       esc(i["reponse_attendue"] or "")] for i in items]
            largeurs = [6, 44, 20, 10, 40]
        else:
            cols = ["N°", "Consigne / question", "Barème"]
            lignes = [[i["ordre"], esc(i["intitule"]), num(i["bareme"]) if i["bareme"] is not None else ""] for i in items]
            largeurs = [6, 80, 14]
        total = ["", "TOTAL", "", num(total_items(items)), ""] if corrige else ["", "TOTAL", num(total_items(items))]
        titre = f"{'CORRIGÉ — ' if corrige else ''}{esc(e['titre']).upper()}"
        pdf = P.pour_cycle(cycle_du_niveau(e["niveau"] or ""))(
            titre, cols, lignes or [["", "Aucun item", ""] + ([""] * 2 if corrige else [])], total=total,
            sous_titre=f"{TYPES_EVAL.get(e['type_evaluation'], '')} n° {e['numero'] or 1} — {e['niveau'] or ''} — {e['matiere'] or ''}",
            infos=entete_epreuve(e, v, items, corrige),
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=largeurs, taille=8.5, avant=avant, signatures=signatures(v, e["auteur"]),
            notes_bas=None if corrige else ["Nom et prénoms de l'élève : ………………………………………………………………  Classe : ……………  Note : ……… / " + num(e["bareme_total"] if e["bareme_total"] is not None else total_items(items))])
        H.journal("epreuve_pdf", f"#{eid} {'corrigé' if corrige else 'sujet'}")
        return H.pdf_reponse(pdf, f"epreuve_{eid}{'_corrige' if corrige else ''}.pdf")

    @app.route("/epreuves/<int:eid>/bareme.pdf")
    @H.connexion_requise()
    def epreuve_bareme_pdf(eid):
        e = epreuve_ou_404(eid)
        items = items_de(eid)
        v = H.identification()
        lignes = [[i["ordre"], esc(i["intitule"]), esc(i["critere"] or ""), esc(i["indicateur"] or ""),
                   num(i["bareme"]) if i["bareme"] is not None else "", ""] for i in items]
        pdf = H.pdfs.document_tableau(
            f"BARÈME ET GRILLE DE CORRECTION — {esc(e['titre']).upper()}",
            ["N°", "Item / consigne", "Critère", "Indicateur", "Barème", "Note obtenue"],
            lignes or [["", "Aucun item", "", "", "", ""]], total=["", "TOTAL", "", "", num(total_items(items)), ""],
            sous_titre=f"{TYPES_EVAL.get(e['type_evaluation'], '')} n° {e['numero'] or 1} — {e['niveau'] or ''} — {e['matiere'] or ''}",
            infos=entete_epreuve(e, v, items), infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[6, 40, 22, 30, 10, 14], taille=8, paysage=True, signatures=signatures(v, e["auteur"]),
            notes_bas=["Critères APC : pertinence, cohérence, correction de la langue, perfectionnement (ou compréhension, démarche, "
                       "résultat, présentation en mathématiques)."])
        H.journal("epreuve_bareme_pdf", f"#{eid}")
        return H.pdf_reponse(pdf, f"epreuve_{eid}_bareme.pdf")

    # -------------------------------------------------------------- épreuves : Excel
    @app.route("/epreuves/liste.xlsx")
    @H.connexion_requise()
    def epreuves_xlsx():
        liste, f, annee = filtre_epreuves(request.args)
        v = H.identification()
        lignes = [[i, e["annee"], e["titre"], TYPES_EVAL.get(e["type_evaluation"], e["type_evaluation"]), e["numero"], e["niveau"] or "",
                   e["matiere"] or "", e["duree_minutes"], e["bareme_total"], e["bareme_items"], len(e["items"]),
                   H.pdfs.date_fr(e["date_prevue"]) if e["date_prevue"] else "", e["auteur"] or "", STATUTS.get(e["statut"], e["statut"])]
                  for i, e in enumerate(liste, 1)]
        items = [[e["titre"], i["ordre"], i["intitule"], i["critere"] or "", i["indicateur"] or "", i["bareme"], i["reponse_attendue"] or ""]
                 for e in liste for i in e["items"]]
        haut = [f"{v.get('ecole') or ''} — Épreuves d'évaluation", f"Année scolaire {annee}"]
        try:
            return H.xlsx.reponse_classeur(f"epreuves_{annee}.xlsx", [
                ("Épreuves", ENT_EPREUVES, lignes, {"titre_haut": haut}),
                ("Items", ["Épreuve"] + ENT_ITEMS, items, {"titre_haut": haut})])
        except H.xlsx.ExcelIndisponible as e_:
            flash(str(e_), "danger")
            return redirect(url_for("epreuves_accueil"))

    @app.route("/epreuves/items-modele.xlsx")
    @H.connexion_requise()
    def epreuve_items_modele_xlsx():
        try:
            return H.xlsx.reponse_classeur("modele_items_epreuve.xlsx", [
                ("Items", ENT_ITEMS, [[1, "Lis le texte puis réponds : qui est le personnage principal ?", "Pertinence de la production", "Identifie le personnage", 2, "Le fermier"],
                                      [2, "Écris trois phrases pour raconter la fin de l'histoire.", "Cohérence de la production", "Phrases enchaînées", 3, ""],
                                      [3, "Souligne les verbes conjugués.", "Correction de la langue", "Verbes repérés", 2, "mange, court, dort"]],
                 {"titre_haut": ["Modèle d'import des items d'une épreuve — les items importés REMPLACENT ceux de l'épreuve"]})])
        except H.xlsx.ExcelIndisponible as e_:
            flash(str(e_), "danger")
            return redirect(url_for("epreuves_accueil"))

    @app.route("/epreuves/<int:eid>/items/import", methods=["POST"])
    @H.connexion_requise("epreuves")
    def epreuve_items_import(eid):
        e = epreuve_ou_404(eid)
        fichier = request.files.get("fichier")
        if not fichier or not fichier.filename:
            flash("Choisissez un fichier Excel (.xlsx) ou CSV.", "danger")
            return redirect(url_for("epreuve_form", eid=eid))
        X = H.xlsx
        try:
            entetes, lignes = X.lire_tableau(fichier, mots_entete=("intitule", "question", "consigne", "item"))
        except (ValueError, X.ExcelIndisponible) as e_:
            flash(str(e_), "danger")
            return redirect(url_for("epreuve_form", eid=eid))
        i_int = X.colonne(entetes, "intitule", "question", "consigne", "item")
        i_cri, i_ind = X.colonne(entetes, "critere"), X.colonne(entetes, "indicateur")
        i_bar, i_rep = X.colonne(entetes, "bareme", "points", "note"), X.colonne(entetes, "reponse attendue", "reponse", "corrige")
        if i_int is None:
            flash("Colonne « Intitulé » (ou Question / Consigne) introuvable.", "danger")
            return redirect(url_for("epreuve_form", eid=eid))
        items = []
        for l in lignes:
            intitule = X.valeur(l, i_int)[:1000]
            if not intitule:
                continue
            items.append({"ordre": len(items) + 1, "intitule": intitule, "critere": X.valeur(l, i_cri)[:120],
                          "indicateur": X.valeur(l, i_ind)[:300], "bareme": lire_reel(X.valeur(l, i_bar)),
                          "reponse_attendue": X.valeur(l, i_rep)[:1000]})
            if len(items) >= MAX_ITEMS:
                break
        if not items:
            flash("Aucun item trouvé dans le fichier.", "danger")
            return redirect(url_for("epreuve_form", eid=eid))
        ecrire_items(eid, items)
        ex("UPDATE epreuves SET maj=? WHERE id=?", (H.maintenant(), eid))
        H.journal("epreuve_items_import", f"#{eid} {len(items)} item(s)")
        flash(f"{len(items)} item(s) importé(s) dans « {e['titre']} » (barème {num(total_items(items))}).", "success")
        return redirect(url_for("epreuve_form", eid=eid))

    # -------------------------------------------------------------- comité d'évaluation
    @app.route("/epreuves/comite")
    @H.connexion_requise()
    def epreuves_comite():
        annee = annee_choisie()
        return render_template("epreuves_comite.html", **ctx("comite", liste=membres(annee, tous=True)))

    CHAMPS_MEMBRE = ("nom_prenoms", "qualite", "qualification", "fonction_comite", "classe_ou_niveau", "contact", "ordre", "actif")

    def lire_membre(f):
        vals = {"nom_prenoms": (f.get("nom_prenoms") or "").strip()[:120], "qualite": (f.get("qualite") or "").strip()[:60] or None,
                "qualification": (f.get("qualification") or "").strip()[:200] or None,
                "fonction_comite": (f.get("fonction_comite") or "").strip()[:60] or None,
                "classe_ou_niveau": (f.get("classe_ou_niveau") or "").strip()[:60] or None,
                "contact": (f.get("contact") or "").strip()[:60] or None, "ordre": lire_entier(f.get("ordre"), 999) or 0,
                "actif": 0 if f.get("actif") == "0" else 1}
        return vals, ([] if vals["nom_prenoms"] else ["Le nom et les prénoms sont obligatoires."])

    @app.route("/epreuves/comite/<int:mid>", methods=["GET", "POST"])
    @H.connexion_requise("epreuves")
    def epreuves_membre(mid):
        m = membre_ou_404(mid) if mid else None
        annee = m["annee"] if m else annee_choisie()
        if request.method == "POST":
            vals, erreurs = lire_membre(request.form)
            if erreurs:
                for x in erreurs:
                    flash(x, "danger")
                return render_template("epreuves_membre_form.html", **ctx("comite", v=dict(request.form), obj=m)), 400
            if m:
                ex(f"UPDATE eval_comite SET {', '.join(k + '=?' for k in CHAMPS_MEMBRE)}, maj=? WHERE id=?",
                   [vals[k] for k in CHAMPS_MEMBRE] + [H.maintenant(), mid])
                flash(f"Membre « {vals['nom_prenoms']} » mis à jour.", "success")
            else:
                mid = ex(f"INSERT INTO eval_comite (ecole_id, annee, {', '.join(CHAMPS_MEMBRE)}, cree_le, maj) VALUES ({', '.join('?' * (len(CHAMPS_MEMBRE) + 4))})",
                         [H.eco(), annee] + [vals[k] for k in CHAMPS_MEMBRE] + [H.maintenant(), H.maintenant()])
                flash(f"Membre « {vals['nom_prenoms']} » ajouté au comité d'évaluation {annee}.", "success")
            H.journal("eval_comite", f"#{mid} {vals['nom_prenoms']}")
            if request.form.get("suivant"):
                return redirect(url_for("epreuves_membre", mid=0, annee=annee))
            return redirect(url_for("epreuves_comite", annee=annee))
        v = dict(m) if m else {"annee": annee, "actif": 1, "fonction_comite": "Membre"}
        return render_template("epreuves_membre_form.html", **ctx("comite", v=v, obj=m))

    @app.route("/epreuves/comite/<int:mid>/supprimer", methods=["POST"])
    @H.connexion_requise("epreuves")
    def epreuves_membre_supprimer(mid):
        m = membre_ou_404(mid)
        ex("DELETE FROM eval_comite WHERE id=?", (mid,))
        H.journal("eval_comite_suppression", f"#{mid} {m['nom_prenoms']}")
        flash(f"Membre « {m['nom_prenoms']} » retiré du comité.", "warning")
        return redirect(url_for("epreuves_comite", annee=m["annee"]))

    def lignes_comite(liste):
        return [[i, m["nom_prenoms"], m["qualite"] or "", m["qualification"] or "", m["fonction_comite"] or "",
                 m["classe_ou_niveau"] or "", m["contact"] or ""] for i, m in enumerate(liste, 1)]

    @app.route("/epreuves/comite.pdf")
    @H.connexion_requise()
    def epreuves_comite_pdf():
        annee = annee_choisie()
        liste = membres(annee)
        v = H.identification()
        pdf = H.pdfs.document_tableau(
            "COMITÉ D'ÉVALUATION — LISTE DES MEMBRES",
            ["N°", "Nom et prénoms", "Qualité", "Qualification", "Fonction dans le comité", "Classe / niveau", "Contact"],
            [[esc(x) for x in l] for l in lignes_comite(liste)] or [["", "Aucun membre", "", "", "", "", ""]],
            sous_titre=f"Année scolaire {annee}",
            infos=[("École", v.get("ecole")), ("Année scolaire", annee), ("Membres", len(liste)),
                   ("Président(e)", next((m["nom_prenoms"] for m in liste if (m["fonction_comite"] or "").lower().startswith("président")), "—"))],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=[6, 32, 22, 30, 24, 18, 18], taille=8, signatures=signatures(v))
        H.journal("eval_comite_pdf", annee)
        return H.pdf_reponse(pdf, f"comite_evaluation_{annee}.pdf")

    @app.route("/epreuves/comite.xlsx")
    @H.connexion_requise()
    def epreuves_comite_xlsx():
        annee = annee_choisie()
        v = H.identification()
        lignes = [l[1:] + ["oui" if m["actif"] else "non"] for l, m in zip(lignes_comite(membres(annee, tous=True)), membres(annee, tous=True))]
        try:
            return H.xlsx.reponse_classeur(f"comite_evaluation_{annee}.xlsx", [
                ("Comité", ENT_COMITE, lignes, {"titre_haut": [f"{v.get('ecole') or ''} — Comité d'évaluation", f"Année scolaire {annee}"]})])
        except H.xlsx.ExcelIndisponible as e_:
            flash(str(e_), "danger")
            return redirect(url_for("epreuves_comite"))

    @app.route("/epreuves/comite/modele.xlsx")
    @H.connexion_requise()
    def epreuves_comite_modele_xlsx():
        try:
            return H.xlsx.reponse_classeur("modele_comite_evaluation.xlsx", [
                ("Comité", ENT_COMITE, [["AKPO Jean", "Directeur / directrice", "CAP, A1-5", "Président(e)", "Toute l'école", "97 00 00 00", "oui"],
                                        ["DOSSOU Marie", "Enseignant(e)", "CEAP, B1-12", "Rapporteur", "CM2", "", "oui"]],
                 {"titre_haut": ["Modèle d'import du comité d'évaluation — un membre par ligne"]})])
        except H.xlsx.ExcelIndisponible as e_:
            flash(str(e_), "danger")
            return redirect(url_for("epreuves_comite_import"))

    @app.route("/epreuves/comite/import", methods=["GET", "POST"])
    @H.connexion_requise("epreuves")
    def epreuves_comite_import():
        annee = annee_choisie()
        if request.method == "POST":
            fichier = request.files.get("fichier")
            if not fichier or not fichier.filename:
                flash("Choisissez un fichier Excel (.xlsx) ou CSV.", "danger")
                return redirect(url_for("epreuves_comite_import", annee=annee))
            X = H.xlsx
            try:
                entetes, lignes = X.lire_tableau(fichier, mots_entete=("nom",))
            except (ValueError, X.ExcelIndisponible) as e_:
                flash(str(e_), "danger")
                return redirect(url_for("epreuves_comite_import", annee=annee))
            i_nom = X.colonne(entetes, "nom et prenoms", "nom")
            if i_nom is None:
                flash("Colonne « Nom et prénoms » introuvable.", "danger")
                return redirect(url_for("epreuves_comite_import", annee=annee))
            idx = {"qualite": X.colonne(entetes, "qualite"), "qualification": X.colonne(entetes, "qualification", "diplome", "grade"),
                   "fonction_comite": X.colonne(entetes, "fonction dans le comite", "fonction"),
                   "classe_ou_niveau": X.colonne(entetes, "classe ou niveau", "classe", "niveau"), "contact": X.colonne(entetes, "contact", "telephone"),
                   "actif": X.colonne(entetes, "actif")}
            existants = {m["nom_prenoms"].lower(): m["id"] for m in membres(annee, tous=True)}
            crees = maj = 0
            for i, l in enumerate(lignes, 1):
                nom = X.valeur(l, i_nom)[:120]
                if not nom:
                    continue
                vals = {k: (X.valeur(l, j)[:200] or None) if k != "actif" else (0 if X.normaliser(X.valeur(l, j)) in ("non", "0") else 1)
                        for k, j in idx.items()}
                if nom.lower() in existants:
                    ex("UPDATE eval_comite SET qualite=?, qualification=?, fonction_comite=?, classe_ou_niveau=?, contact=?, actif=?, maj=? WHERE id=?",
                       (vals["qualite"], vals["qualification"], vals["fonction_comite"], vals["classe_ou_niveau"], vals["contact"], vals["actif"],
                        H.maintenant(), existants[nom.lower()]))
                    maj += 1
                else:
                    ex("INSERT INTO eval_comite (ecole_id, annee, nom_prenoms, qualite, qualification, fonction_comite, classe_ou_niveau, contact, ordre, actif, cree_le, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (H.eco(), annee, nom, vals["qualite"], vals["qualification"], vals["fonction_comite"], vals["classe_ou_niveau"], vals["contact"],
                        i, vals["actif"], H.maintenant(), H.maintenant()))
                    crees += 1
            H.journal("eval_comite_import", f"{annee} : {crees} ajouté(s), {maj} mis à jour")
            flash(f"Import terminé : {crees} membre(s) ajouté(s), {maj} mis à jour.", "success")
            return redirect(url_for("epreuves_comite", annee=annee))
        return render_template("epreuves_comite_import.html", **ctx("comite", ent=ENT_COMITE))

    # -------------------------------------------------------------- grilles
    @app.route("/epreuves/grilles")
    @H.connexion_requise()
    def epreuves_grilles():
        annee = annee_choisie()
        liste = []
        for gr in q("SELECT * FROM grilles WHERE ecole_id=? AND annee=? ORDER BY type, niveau, titre", (H.eco(), annee)):
            d = grille_ou_404(gr["id"])
            d["total"] = total_grille(d["lignes"])
            liste.append(d)
        return render_template("epreuves_grilles.html", **ctx("grilles", liste=liste))

    @app.route("/epreuves/grilles/<int:gid>", methods=["GET", "POST"])
    @H.connexion_requise("epreuves")
    def grille_form(gid):
        gr = grille_ou_404(gid) if gid else None
        annee = gr["annee"] if gr else annee_choisie()
        epreuves = q("SELECT id, titre, niveau FROM epreuves WHERE ecole_id=? AND annee=? ORDER BY titre", (H.eco(), annee))
        if request.method == "POST":
            f = request.form
            titre = (f.get("titre") or "").strip()[:200]
            typ = f.get("type") if f.get("type") in TYPES_GRILLE else "correction"
            code, _, lib = (f.get("matiere") or "").partition("|")
            lignes = lire_lignes_grille(f)
            ep = lire_entier(f.get("epreuve_id"), 10 ** 9) or None
            if ep and not q("SELECT 1 FROM epreuves WHERE id=? AND ecole_id=?", (ep, H.eco()), un=True):
                ep = None
            erreurs = [] if titre else ["Le titre de la grille est obligatoire."]
            if not lignes:
                erreurs.append("Saisissez au moins une ligne (critère).")
            vals = {"titre": titre, "niveau": (f.get("niveau") or "").strip()[:40] or None, "matiere_code": code.strip()[:20] or None,
                    "matiere": lib.strip()[:120] or (code.strip()[:120] or None), "type": typ,
                    "contenu": json.dumps({"lignes": lignes}, ensure_ascii=False), "epreuve_id": ep}
            if erreurs:
                for x in erreurs:
                    flash(x, "danger")
                v = dict(vals, lignes=lignes, annee=annee, matiere_val=f.get("matiere", ""))
                return render_template("epreuves_grille_form.html", **ctx("grilles", v=v, obj=gr, matieres=matieres(), epreuves=epreuves,
                                                                          total=total_grille(lignes))), 400
            cles = list(vals)
            if gr:
                ex(f"UPDATE grilles SET {', '.join(k + '=?' for k in cles)}, maj=? WHERE id=?", [vals[k] for k in cles] + [H.maintenant(), gid])
                flash(f"Grille « {titre} » mise à jour ({len(lignes)} critère(s)).", "success")
            else:
                gid = ex(f"INSERT INTO grilles (ecole_id, annee, {', '.join(cles)}, cree_le, maj) VALUES ({', '.join('?' * (len(cles) + 4))})",
                         [H.eco(), annee] + [vals[k] for k in cles] + [H.maintenant(), H.maintenant()])
                flash(f"Grille « {titre} » créée ({len(lignes)} critère(s)).", "success")
            H.journal("grille", f"#{gid} {titre}")
            return redirect(url_for("epreuves_grilles", annee=annee))
        if gr:
            v = dict(gr, matiere_val=f"{gr['matiere_code']}|{gr['matiere']}" if gr["matiere_code"] else "")
        else:
            modele = request.args.get("modele")
            base = grille_modele(modele) if modele in GRILLES_TYPES else {"titre": "", "type": "correction", "lignes": []}
            v = dict(base, annee=annee, niveau=request.args.get("niveau", "Maternelle 1" if modele == "maternelle" else ""),
                     matiere_val="", epreuve_id=request.args.get("epreuve", type=int))
        return render_template("epreuves_grille_form.html", **ctx("grilles", v=v, obj=gr, matieres=matieres(), epreuves=epreuves,
                                                                  total=total_grille(v["lignes"])))

    @app.route("/epreuves/grilles/<int:gid>/supprimer", methods=["POST"])
    @H.connexion_requise("epreuves")
    def grille_supprimer(gid):
        gr = grille_ou_404(gid)
        ex("DELETE FROM grilles WHERE id=?", (gid,))
        H.journal("grille_suppression", f"#{gid} {gr['titre']}")
        flash(f"Grille « {gr['titre']} » supprimée.", "warning")
        return redirect(url_for("epreuves_grilles", annee=gr["annee"]))

    @app.route("/epreuves/grilles/<int:gid>/dupliquer", methods=["POST"])
    @H.connexion_requise("epreuves")
    def grille_dupliquer(gid):
        gr = grille_ou_404(gid)
        nid = ex("INSERT INTO grilles (ecole_id, annee, titre, niveau, matiere_code, matiere, type, contenu, epreuve_id, cree_le, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (H.eco(), gr["annee"], f"{gr['titre']} (copie)"[:200], gr["niveau"], gr["matiere_code"], gr["matiere"], gr["type"], gr["contenu"],
                  None, H.maintenant(), H.maintenant()))
        H.journal("grille_duplication", f"#{gid} -> #{nid}")
        flash("Grille dupliquée : modifiez la copie.", "success")
        return redirect(url_for("grille_form", gid=nid))

    def lignes_grille_pdf(gr):
        res = []
        for i, l in enumerate(gr["lignes"], 1):
            ind = "<br/>".join("• " + esc(x) for x in l.get("indicateurs") or [])
            if gr["type"] == "observation":
                res.append([i, esc(l["critere"]), ind, "", "", "", esc(l.get("observations") or "")])
            else:
                res.append([i, esc(l["critere"]), ind, num(l.get("bareme")) if l.get("bareme") is not None else "", "", esc(l.get("observations") or "")])
        return res

    @app.route("/epreuves/grilles/<int:gid>.pdf")
    @H.connexion_requise()
    def grille_pdf(gid):
        gr = grille_ou_404(gid)
        v = H.identification()
        ep = q("SELECT titre FROM epreuves WHERE id=?", (gr["epreuve_id"],), un=True) if gr["epreuve_id"] else None
        if gr["type"] == "observation":
            cols = ["N°", "Domaine / critère", "Indicateurs", "A", "ECA", "NA", "Observations"]
            largeurs, total = [6, 30, 60, 8, 8, 8, 30], None
        else:
            cols = ["N°", "Critère", "Indicateurs", "Barème", "Note", "Observations"]
            largeurs, total = [6, 34, 60, 12, 12, 30], ["", "TOTAL", "", num(total_grille(gr["lignes"])), "", ""]
        pdf = H.pdfs.pour_cycle(cycle_du_niveau(gr["niveau"] or ""))(
            esc(gr["titre"]).upper(), cols, lignes_grille_pdf(gr) or [[""] * len(cols)], total=total,
            sous_titre=f"{TYPES_GRILLE.get(gr['type'], '')} — {gr['niveau'] or ''} {('— ' + gr['matiere']) if gr['matiere'] else ''}",
            infos=[("École", v.get("ecole")), ("Année scolaire", gr["annee"]), ("Niveau", gr["niveau"] or "—"), ("Matière", gr["matiere"] or "—"),
                   ("Épreuve liée", ep["titre"] if ep else "—"), ("Type", TYPES_GRILLE.get(gr["type"], gr["type"]))],
            infos_haut=[("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))],
            largeurs=largeurs, taille=8, signatures=signatures(v),
            notes_bas=["Élève : ………………………………………………………  Classe : ……………  Date : ……/……/………"]
            + (["A = acquis ; ECA = en cours d'acquisition ; NA = non acquis."] if gr["type"] == "observation" else []))
        H.journal("grille_pdf", f"#{gid}")
        return H.pdf_reponse(pdf, f"grille_{gid}.pdf")

    @app.route("/epreuves/grilles.xlsx")
    @H.connexion_requise()
    def grilles_xlsx():
        annee = annee_choisie()
        v = H.identification()
        lignes = []
        for gr in q("SELECT * FROM grilles WHERE ecole_id=? AND annee=? ORDER BY type, niveau, titre", (H.eco(), annee)):
            d = grille_ou_404(gr["id"])
            for i, l in enumerate(d["lignes"], 1):
                lignes.append([d["titre"], TYPES_GRILLE.get(d["type"], d["type"]), d["niveau"] or "", d["matiere"] or "", i, l["critere"],
                               "\n".join(l.get("indicateurs") or []), l.get("bareme"), l.get("observations") or ""])
        try:
            return H.xlsx.reponse_classeur(f"grilles_{annee}.xlsx", [
                ("Grilles", ["Grille", "Type", "Niveau", "Matière", "N°", "Critère", "Indicateurs", "Barème", "Observations"], lignes,
                 {"titre_haut": [f"{v.get('ecole') or ''} — Grilles de correction, d'évaluation et d'observation", f"Année scolaire {annee}"]})])
        except H.xlsx.ExcelIndisponible as e_:
            flash(str(e_), "danger")
            return redirect(url_for("epreuves_grilles"))
