# -*- coding: utf-8 -*-
"""v2.5.0 : budget prévisionnel et compte rendu d'exécution de budget de l'école (modèles officiels des EM / EPP).

Rubrique Finances → « Budget prévisionnel ». Trois vues : saisie, budget prévisionnel (état des recettes, état des dépenses, récapitulation,
arrêtés en lettres, signatures) et compte rendu d'exécution (dépenses prévues, exécutées, reste, pourcentage). La subvention de l'État
(ligne I-2), la participation des collectivités (I-3) et les dons (II-3) sont comparées aux recettes déjà enregistrées dans « Subventions et
recettes ». Chaque vue se télécharge en PDF ou en Word (barre d'export)."""
import config
from flask import abort, flash, redirect, render_template, request, url_for

# (type, chapitre, code, intitulé, groupe)   type : R recette, D dépense
RECETTES = [
    ("R", "I", "I-1", "Solde de l'exercice antérieur", "RECETTES ORDINAIRES"),
    ("R", "I", "I-1-1", "Espèces en caisse", "RECETTES ORDINAIRES"),
    ("R", "I", "I-1-2", "Avoirs en banque, CCP ou CLCAM", "RECETTES ORDINAIRES"),
    ("R", "I", "I-1-3", "Avoirs dans les autres institutions financières", "RECETTES ORDINAIRES"),
    ("R", "I", "I-2", "Subvention de l'État", "RECETTES ORDINAIRES"),
    ("R", "I", "I-3", "Participation des collectivités", "RECETTES ORDINAIRES"),
    ("R", "II", "II-1", "Droits de place des vendeuses", "RECETTES EXTRAORDINAIRES"),
    ("R", "II", "II-2-1", "Vente d'essences forestières", "RECETTES EXTRAORDINAIRES"),
    ("R", "II", "II-2-2", "Vente de produits maraîchers", "RECETTES EXTRAORDINAIRES"),
    ("R", "II", "II-2-3", "Autres produits divers", "RECETTES EXTRAORDINAIRES"),
    ("R", "II", "II-3", "Dons et legs", "RECETTES EXTRAORDINAIRES"),
    ("R", "III", "III-1", "Produits sur exercice antérieur", "COMPTE DE RÉGULARISATION"),
]
DEPENSES = [
    ("D", "I", "I-1", "Traitement et salaire des gardiens", "PERSONNEL"),
    ("D", "I", "I-2-1", "Assistance financière (1/100)", "PERSONNEL"),
    ("D", "I", "I-2-2", "Soins médicaux (soins d'urgence à l'école)", "PERSONNEL"),
    ("D", "II", "II-1", "Fournitures de bureau", "FOURNITURES"),
    ("D", "II", "II-2", "Fournitures scolaires", "FOURNITURES"),
    ("D", "II", "II-3", "Petits outillages (houe, balai, râteau, seau d'eau…)", "FOURNITURES"),
    ("D", "III", "III-1", "Matériel pédagogique", "MATÉRIEL ET MOBILIER"),
    ("D", "III", "III-2", "Autres matériels", "MATÉRIEL ET MOBILIER"),
    ("D", "III", "III-3", "Mobilier scolaire", "MATÉRIEL ET MOBILIER"),
    ("D", "IV", "IV-1", "Équipements pédagogiques", "ÉQUIPEMENTS"),
    ("D", "IV", "IV-2", "Équipements culturels et sportifs", "ÉQUIPEMENTS"),
    ("D", "IV", "IV-3", "Équipements sanitaires", "ÉQUIPEMENTS"),
    ("D", "V", "V-1", "Consommation d'eau (en cas de coupure)", "CONSOMMATION DE SERVICES EXTÉRIEURS"),
    ("D", "V", "V-2", "Consommation d'électricité", "CONSOMMATION DE SERVICES EXTÉRIEURS"),
    ("D", "V", "V-3", "Consommation de téléphone (crédit, forfait internet…)", "CONSOMMATION DE SERVICES EXTÉRIEURS"),
    ("D", "V", "V-4", "Frais de poste", "CONSOMMATION DE SERVICES EXTÉRIEURS"),
    ("D", "V", "V-5", "Frais de tenue et d'ouverture de compte", "CONSOMMATION DE SERVICES EXTÉRIEURS"),
    ("D", "VI", "VI-1", "Déplacement du directeur et des autres acteurs de l'école", "TRANSPORTS ET DÉPLACEMENT"),
    ("D", "VI", "VI-2", "Transport de matériel", "TRANSPORTS ET DÉPLACEMENT"),
    ("D", "VII", "VII", "Frais d'entretien du directeur et des autres acteurs de l'école (vote du budget, étude des dossiers…)", "FRAIS D'ENTRETIEN"),
    ("D", "VIII", "VIII-1", "Fête de fin d'année scolaire pour récompenser les meilleurs élèves", "FÊTES ET RÉCEPTIONS"),
    ("D", "VIII", "VIII-2", "Fête de la journée mondiale des enseignants", "FÊTES ET RÉCEPTIONS"),
    ("D", "IX", "IX-1", "Entretien des bâtiments, des mobiliers et autres", "TRAVAUX D'ENTRETIEN SOMMAIRE"),
    ("D", "IX", "IX-2", "Maintenance des équipements", "TRAVAUX D'ENTRETIEN SOMMAIRE"),
    ("D", "X", "X-1", "UASCEP", "DÉPENSES DE TRANSFERT"),
    ("D", "X", "X-2", "APE", "DÉPENSES DE TRANSFERT"),
    ("D", "XI", "XI-1", "Photocopie des épreuves pour les évaluations", "AUTRES PRESTATIONS DE SERVICES"),
    ("D", "XI", "XI-2", "Autres (cahiers d'activités, extraits des guides, examen blanc, renforcement CEP…)", "AUTRES PRESTATIONS DE SERVICES"),
    ("D", "XII", "XII-1", "Investissement", "INVESTISSEMENT"),
    ("D", "XIII", "XIII-1", "Charges sur exercice antérieur (arriérés de dépenses)", "COMPTE DE RÉGULARISATION"),
]
LIGNES = RECETTES + DEPENSES
CODES = {(t, c) for t, _ch, c, _i, _g in LIGNES}
SOUS_LIGNES = {"I-1"}        # I-1 est la somme de I-1-1, I-1-2 et I-1-3 ; II-2-x somment « Vente de produits divers »
FILS = {("R", "I-1"): ["I-1-1", "I-1-2", "I-1-3"]}
# recettes déjà enregistrées (« Subventions et recettes ») qui correspondent à une ligne du budget
CORRESPOND = {"I-2": "Subvention de l'État", "I-3": "Subvention de la commune", "II-3": "Dons et partenaires (PAM, ONG…)"}
CHAP_LIB = {"R": {"I": "Chapitre I – Recettes ordinaires", "II": "Chapitre II – Recettes extraordinaires", "III": "Chapitre III – Compte de régularisation"}}

_U = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
      "dix-sept", "dix-huit", "dix-neuf"]
_D = ["", "", "vingt", "trente", "quarante", "cinquante", "soixante"]


def _cent(n):
    if n < 20:
        return _U[n]
    if n < 70:
        d, u = divmod(n, 10)
        return _D[d] + ("" if u == 0 else (" et un" if u == 1 else "-" + _U[u]))
    if n < 80:
        r = n - 60
        return "soixante" + (" et onze" if r == 11 else "-" + _U[r])
    r = n - 80
    return "quatre-vingt" + ("s" if r == 0 else "-" + _U[r])


def _mille(n):
    c, r = divmod(n, 100)
    s = ""
    if c:
        s = ("cent" if c == 1 else _U[c] + " cent") + ("s" if (c > 1 and r == 0) else "")
    if r:
        s += (" " if s else "") + _cent(r)
    return s


def en_lettres(n):
    """12500 -> « douze mille cinq cents »."""
    n = int(n or 0)
    if n == 0:
        return "zéro"
    out = []
    for val, nom in ((1_000_000_000, "milliard"), (1_000_000, "million")):
        q, n = divmod(n, val)
        if q:
            out.append(_mille(q) + " " + nom + ("s" if q > 1 else ""))
    q, n = divmod(n, 1000)
    if q:
        out.append("mille" if q == 1 else _mille(q) + " mille")
    if n:
        out.append(_mille(n))
    return " ".join(out).replace("quatre-vingts mille", "quatre-vingt mille")


def milliers(n):
    return f"{int(n or 0):,}".replace(",", " ")


def totaux(valeurs, type_):
    """valeurs {code: montant} -> ({chapitre: total}, total général). I-1 est la somme de ses trois sous-lignes."""
    v = dict(valeurs)
    if type_ == "R":
        v["I-1"] = sum(v.get(c, 0) for c in FILS[("R", "I-1")])
    par = {}
    for t, ch, c, _i, _g in LIGNES:
        if t != type_ or c in FILS[("R", "I-1")] and False:
            continue
        if t == "R" and c in FILS[("R", "I-1")]:
            continue                      # déjà comptées dans I-1
        par[ch] = par.get(ch, 0) + v.get(c, 0)
    return par, sum(par.values())


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.schema("""
    CREATE TABLE IF NOT EXISTS be_budget (
        ecole_id INTEGER NOT NULL,
        annee TEXT NOT NULL,
        type TEXT NOT NULL,
        code TEXT NOT NULL,
        prevu INTEGER NOT NULL DEFAULT 0,
        execute INTEGER NOT NULL DEFAULT 0,
        observation TEXT,
        PRIMARY KEY (ecole_id, annee, type, code)
    );""")

    def garde():
        if config.secondaire() or config.juridiction() or getattr(H, "fp_operations", None) is None:
            abort(404)

    def lire(annee):
        return {(r["type"], r["code"]): r for r in q("SELECT * FROM be_budget WHERE ecole_id=? AND annee=?", (H.eco(), annee))}

    def deja_enregistre(annee):
        out = {}
        for code, origine in CORRESPOND.items():
            r = q("SELECT COALESCE(SUM(montant),0) s FROM fp_recettes WHERE ecole_id=? AND annule=0 AND origine=?", (H.eco(), origine), un=True)
            out[code] = r["s"] if r else 0
        return out

    @app.route("/budget-previsionnel", methods=["GET", "POST"])
    @H.connexion_requise("depenses")
    def budget_ecole():
        garde()
        annee = config.ANNEE_ACTIVE
        if request.method == "POST":
            n = 0
            for t, _ch, c, _i, _g in LIGNES:
                def num(nom):
                    s = str(request.form.get(f"{nom}_{t}_{c}", "")).replace(" ", "").replace("\xa0", "").strip()
                    return int(s) if s.isdigit() and int(s) <= 10_000_000_000 else 0
                p, e, o = num("p"), num("e"), (request.form.get(f"o_{t}_{c}") or "").strip()[:200]
                ex("""INSERT INTO be_budget (ecole_id, annee, type, code, prevu, execute, observation) VALUES (?,?,?,?,?,?,?)
                      ON CONFLICT(ecole_id, annee, type, code) DO UPDATE SET prevu=excluded.prevu, execute=excluded.execute, observation=excluded.observation""",
                   (H.eco(), annee, t, c, p, e, o))
                n += 1
            H.journal("budget_ecole", f"{annee} : {n} lignes")
            flash("Budget enregistré.", "success")
            return redirect(url_for("budget_ecole", vue=request.form.get("vue") or "saisie"))
        vue = request.args.get("vue", "saisie")
        if vue not in ("saisie", "previsionnel", "compte-rendu"):
            vue = "saisie"
        r = lire(annee)
        prevu = {k: v["prevu"] for k, v in r.items()}
        exec_ = {k: v["execute"] for k, v in r.items()}
        obs = {k: v["observation"] for k, v in r.items()}
        pr_r, pr_rt = totaux({c: prevu.get(("R", c), 0) for t, _a, c, _i, _g in RECETTES}, "R")
        pr_d, pr_dt = totaux({c: prevu.get(("D", c), 0) for t, _a, c, _i, _g in DEPENSES}, "D")
        ex_d, ex_dt = totaux({c: exec_.get(("D", c), 0) for t, _a, c, _i, _g in DEPENSES}, "D")
        i1 = sum(prevu.get(("R", c), 0) for c in FILS[("R", "I-1")])
        return render_template("budget_ecole.html", vue=vue, annee=annee, RECETTES=RECETTES, DEPENSES=DEPENSES, prevu=prevu, exec_=exec_, obs=obs,
                               pr_r=pr_r, pr_rt=pr_rt, pr_d=pr_d, pr_dt=pr_dt, ex_d=ex_d, ex_dt=ex_dt, i1=i1, deja=deja_enregistre(annee),
                               ident=H.identification(), lettres=en_lettres, m=milliers, equilibre=(pr_rt == pr_dt))
