# -*- coding: utf-8 -*-
"""Inscriptions et espaces (GESCOL v1.3).

* Page Élèves : modèle Excel, export Excel (tous les champs de la carte scolaire), import Excel/CSV avec aperçu,
  prise de photo rapide pour toute une classe.
* Espace élève : comptes (identifiant = matricule), connexion, résultats publiés, absences, carte scolaire.
* Espace enseignant : mes classes, raccourcis, signatures.
* Tableau de bord du fondateur : indicateurs consolidés de toutes les écoles actives.
"""
import secrets
from datetime import date, datetime, timedelta
from functools import wraps

from flask import abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import evaluations_core as EC
from calcul import cycle_du_niveau

# ---------------------------------------------------------------- champs de la fiche d'inscription
# (clé, intitulé Excel, intitulés reconnus à l'import — du plus précis au plus général)
CHAMPS = [
    ("matricule", "Matricule", ("matricule", "matricule ecole", "n matricule", "numero matricule", "mle")),
    ("matricule_educmaster", "Matricule EducMaster",
     ("matricule educmaster", "educmaster", "matricule em", "id educmaster", "identifiant educmaster")),
    ("nip", "NIP", ("nip", "numero d identification personnel", "n i p")),
    ("nom", "Nom", ("nom", "nom de famille", "noms", "nom de l eleve")),
    ("prenoms", "Prénoms", ("prenoms", "prenom", "prenom s", "prenoms de l eleve")),
    ("sexe", "Sexe (M/F)", ("sexe", "sexe m f", "genre", "g f", "s")),
    ("date_naissance", "Date de naissance",
     ("date de naissance", "ne e le", "ne le", "nee le", "date naiss", "date naissance", "ddn", "naissance")),
    ("lieu_naissance", "Lieu de naissance", ("lieu de naissance", "lieu naissance", "ne e a", "ne a", "lieu")),
    ("classe", "Classe", ("classe", "cours", "classe actuelle", "niveau")),
    ("parent_nom", "Nom du parent / tuteur",
     ("nom du parent tuteur", "nom du parent", "nom parent", "parent tuteur", "parent", "tuteur", "pere mere tuteur")),
    ("parent_telephone", "Téléphone du parent",
     ("telephone du parent", "telephone parent", "telephone", "tel parent", "tel", "contact", "numero de telephone")),
    ("parent_whatsapp", "WhatsApp du parent", ("whatsapp du parent", "whatsapp", "numero whatsapp")),
    ("adresse", "Adresse / quartier", ("adresse quartier", "adresse", "quartier", "domicile")),
    ("numero_table", "N° de table", ("n de table", "numero de table", "no de table", "num table", "table")),
    ("centre_examen", "Centre d'examen", ("centre d examen", "centre examen", "centre de composition", "centre")),
    ("annees_scolarite", "Années de scolarité",
     ("annees de scolarite", "nombre d annees de scolarite", "nb annees", "annees scolarite", "scolarite")),
    ("redoublant", "Redoublant (O/N)", ("redoublant o n", "redoublant", "redouble", "redoublement")),
    ("statut", "Statut", ("statut", "situation")),
]
LIBELLES = {k: lib for k, lib, _ in CHAMPS}
# ordre de reconnaissance souple : les intitulés les plus précis d'abord (évite que « Nom » prenne « Nom du parent »,
# ou « Date de naissance » prenne « Lieu de naissance »)
ORDRE_SOUPLE = ["matricule_educmaster", "matricule", "parent_whatsapp", "parent_telephone", "parent_nom",
                "lieu_naissance", "date_naissance", "numero_table", "centre_examen", "annees_scolarite",
                "redoublant", "prenoms", "nom", "nip", "sexe", "classe", "adresse", "statut"]
NOM_COMPLET = ("nom et prenoms", "noms et prenoms", "nom prenoms", "nom et prenom", "nom complet",
               "nom et prenoms de l eleve", "eleve")
STATUTS = {"inscrit": "inscrit", "inscrite": "inscrit", "transfere": "transfere", "transferee": "transfere",
           "sorti": "sorti", "sortie": "sorti", "abandon": "sorti"}
LIB_STATUT = {"inscrit": "Inscrit", "transfere": "Transféré", "sorti": "Sorti"}
EXT_IMPORT = (".xlsx", ".xlsm", ".csv", ".txt")
MAX_LIGNES = 2000
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sans O/0, I/1, L : lisible par les enfants

_tentatives = {}  # anti-force brute de la connexion élève : clé -> [horodatages]


def _trop_de_tentatives(cle):
    now = datetime.now()
    lst = [t for t in _tentatives.get(cle, []) if now - t < timedelta(minutes=15)]
    _tentatives[cle] = lst
    return len(lst) >= 8


def mdp_provisoire():
    return "".join(secrets.choice(ALPHABET) for _ in range(6))


def enregistrer(app, H):
    q, ex, config = H.q, H.ex, H.config
    X = H.xlsx

    H.schema("""
    CREATE TABLE IF NOT EXISTS comptes_eleves (      -- accès à l'espace élève (mot de passe dans eleves.mdp_hash)
        eleve_id INTEGER PRIMARY KEY REFERENCES eleves(id) ON DELETE CASCADE,
        doit_changer INTEGER NOT NULL DEFAULT 1,
        actif INTEGER NOT NULL DEFAULT 1,
        cree_le TEXT,
        cree_par INTEGER,
        dernier_acces TEXT
    );
    """)

    # ============================================================ utilitaires communs
    def classes_ecole():
        """Classes autorisées (école courante ; enseignant : ses classes) en dict avec le cycle."""
        out = []
        for c in H.classes_autorisees():
            d = dict(c)
            d["cycle"] = cycle_du_niveau(c["niveau"])
            out.append(d)
        return out

    def matricule_auto(eid, classe):
        cyc = {"maternelle": "M", "primaire": "P"}.get(cycle_du_niveau(classe["niveau"]), "S")
        return f"{config.ECOLE['sigle']}-{config.ANNEE_ACTIVE[:4]}-{cyc}-{eid:04d}"

    def oui_non(v):
        t = X.normaliser(v)
        if t in ("o", "oui", "1", "x", "r", "vrai", "yes", "y", "redoublant", "redoublante"):
            return 1
        if t in ("", "n", "non", "0", "faux", "no", "nouveau", "nouvelle", "nv", "passant"):
            return 0
        return None

    def retrouver_classe(texte, classes):
        """« CM2 A », « cm2a », ou « CM2 » (si une seule classe de ce niveau) -> classe ; sinon None."""
        t = X.normaliser(texte).replace(" ", "")
        if not t:
            return None
        for c in classes:
            if X.normaliser(c["nom"]).replace(" ", "") == t:
                return c
        meme_niveau = [c for c in classes if X.normaliser(c["niveau"]).replace(" ", "") == t]
        return meme_niveau[0] if len(meme_niveau) == 1 else None

    # ============================================================ modèle et export Excel
    ENTETES_EXPORT = ["N°"] + [lib for _, lib, _ in CHAMPS] + ["Niveau", "Date d'inscription"]

    def ligne_export(i, e):
        dn = None
        if e["date_naissance"]:
            try:
                dn = datetime.strptime(e["date_naissance"], "%Y-%m-%d").date()
            except ValueError:
                dn = e["date_naissance"]
        vals = {
            "matricule": e["matricule"], "matricule_educmaster": e["matricule_educmaster"], "nip": e["nip"],
            "nom": e["nom"], "prenoms": e["prenoms"], "sexe": e["sexe"], "date_naissance": dn,
            "lieu_naissance": e["lieu_naissance"], "classe": e["classe_nom"], "parent_nom": e["parent_nom"],
            "parent_telephone": e["parent_telephone"], "parent_whatsapp": e["parent_whatsapp"], "adresse": e["adresse"],
            "numero_table": e["numero_table"], "centre_examen": e["centre_examen"],
            "annees_scolarite": e["annees_scolarite"], "redoublant": "Oui" if e["redoublant"] else "Non",
            "statut": LIB_STATUT.get(e["statut"], e["statut"]),
        }
        return [i] + [vals[k] for k, _, _ in CHAMPS] + [e["niveau"], e["date_inscription"]]

    @app.route("/eleves/modele.xlsx")
    @H.connexion_requise("eleves")
    def eleves_modele_xlsx():
        """Modèle vierge : une feuille « Élèves » (en-têtes seuls) et une feuille de consignes."""
        entetes = [lib for k, lib, _ in CHAMPS if k != "statut"]
        classes = ", ".join(c["nom"] for c in classes_ecole()) or "(aucune classe créée)"
        consignes = [
            ["Nom, Prénoms, Sexe", "Obligatoires. Sexe : M ou F (G, garçon, fille… sont aussi acceptés)."],
            ["Matricule", "Laisser vide pour un nouvel élève : GESCOL l'attribue automatiquement. "
                          "Rempli : l'élève existant est mis à jour."],
            ["Matricule EducMaster", "Si le matricule EducMaster existe déjà, la fiche de l'élève est mise à jour."],
            ["Date de naissance", "Format date Excel, ou 03/05/2015, ou 2015-05-03."],
            ["Classe", f"Nom exact de la classe ({classes}). Vide : la classe choisie lors de l'import."],
            ["Redoublant", "O ou N (Oui / Non)."],
            ["Années de scolarité", "Nombre entier (ex. 6)."],
            ["Colonnes", "L'ordre des colonnes est libre et les intitulés peuvent varier (« Prénom(s) », "
                         "« Né(e) le », « Tél. »…). Une colonne « Nom et prénoms » unique est aussi acceptée."],
        ]
        exemple = [["", "", "", "DOSSOU", "Grâce Fifamè", "F", "03/05/2015", "Cotonou",
                    (classes_ecole() or [{"nom": "CM2 A"}])[0]["nom"], "DOSSOU Marcel", "01 97 00 00 00",
                    "01 97 00 00 00", "Akpakpa", "", "", "6", "N"]]
        buf_titre = [f"{config.ECOLE['nom']} — modèle d'inscription des élèves ({config.ANNEE_ACTIVE})"]
        H.journal("eleves_modele_xlsx")
        try:
            return X.reponse_classeur("modele_inscription_eleves.xlsx", [
                ("Élèves", entetes, []),
                ("Consignes", ["Champ", "Consigne"], consignes, {"titre_haut": buf_titre}),
                ("Exemple", entetes, exemple),
            ])
        except X.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("eleves"))

    def eleves_filtres():
        """Même filtre que la page Élèves (recherche, classe, statut), école courante."""
        rech = request.args.get("q", "").strip()
        cid = request.args.get("classe", type=int)
        statut = request.args.get("statut", "inscrit")
        sql = ("SELECT e.*, c.nom classe_nom, c.niveau FROM eleves e JOIN classes c ON c.id=e.classe_id "
               "WHERE c.ecole_id=?")
        args = [H.eco()]
        if statut != "tous":
            sql += " AND e.statut=?"
            args.append(statut)
        if rech:
            sql += " AND (e.nom LIKE ? OR e.prenoms LIKE ? OR e.matricule LIKE ? OR e.parent_telephone LIKE ?)"
            args += [f"%{rech}%"] * 4
        if cid:
            sql += " AND e.classe_id=?"
            args.append(cid)
        return q(sql + " ORDER BY c.nom, e.nom, e.prenoms", args), cid, statut

    @app.route("/eleves/export.xlsx")
    @H.connexion_requise("eleves")
    def eleves_export_xlsx():
        lst, cid, statut = eleves_filtres()
        lignes = [ligne_export(i, e) for i, e in enumerate(lst, 1)]
        cl = next((c for c in classes_ecole() if c["id"] == cid), None)
        titre = [f"{config.ECOLE['nom']} — liste des élèves {config.ANNEE_ACTIVE}",
                 (f"Classe : {cl['nom']} · " if cl else "") + f"{len(lignes)} élève(s) · extrait le "
                 f"{datetime.now().strftime('%d/%m/%Y à %H:%M')}"]
        H.journal("eleves_export_xlsx", f"{len(lignes)} élève(s)")
        nom = f"eleves_{cl['nom']}.xlsx" if cl else "eleves.xlsx"
        return X.reponse_xlsx(nom.replace(" ", "_"), ENTETES_EXPORT, lignes, titre="Élèves", titre_haut=titre)

    # ============================================================ import Excel / CSV
    def reconnaitre_colonnes(entetes):
        """{champ: indice} — intitulés exacts d'abord, puis reconnaissance souple sur les colonnes restantes."""
        norm = [X.normaliser(h) for h in entetes]
        pris, idx = set(), {}
        for i, h in enumerate(norm):                       # « Nom et prénoms » dans une seule colonne
            if h in NOM_COMPLET:
                idx["nom_complet"] = i
                pris.add(i)
                break
        for k, _, cands in CHAMPS:                          # 1) égalité exacte
            for cand in cands:
                c = X.normaliser(cand)
                i = next((j for j, h in enumerate(norm) if h == c and j not in pris), None)
                if i is not None:
                    idx[k] = i
                    pris.add(i)
                    break
        cands_de = {k: cands for k, _, cands in CHAMPS}
        for k in ORDRE_SOUPLE:                               # 2) reconnaissance souple (H.xlsx.colonne)
            if k in idx:
                continue
            masque = [h if j not in pris else "" for j, h in enumerate(entetes)]
            i = X.colonne(masque, *[c for c in cands_de[k] if len(X.normaliser(c)) > 2])
            if i is not None and masque[i]:
                idx[k] = i
                pris.add(i)
        return idx

    def couper_nom_complet(texte):
        """« DOSSOU Grâce Fifamè » -> (« DOSSOU », « Grâce Fifamè ») : les mots en MAJUSCULES forment le nom."""
        mots = texte.split()
        n = 0
        while n < len(mots) - 1 and mots[n].isupper():
            n += 1
        n = max(n, 1)
        return " ".join(mots[:n]), " ".join(mots[n:])

    def lire_fichier(fichier):
        """-> (colonnes reconnues {champ: intitulé}, lignes [{"n": n° de ligne, "v": {champ: texte}}])."""
        entetes, lignes = X.lire_tableau(fichier, ("prenoms", "prenom", "sexe", "matricule", "nom et prenoms"),
                                         max_lignes=MAX_LIGNES + 60)
        idx = reconnaitre_colonnes(entetes)
        # « n » = numéro d'ordre de la ligne d'élève sous la ligne d'en-têtes (les lignes vides sont ignorées)
        out = []
        for j, brute in enumerate(lignes[:MAX_LIGNES]):
            v = {k: X.valeur(brute, i)[:200] for k, i in idx.items()}
            if "nom_complet" in v:
                nc = v.pop("nom_complet")
                if nc and not v.get("nom") and not v.get("prenoms"):
                    v["nom"], v["prenoms"] = couper_nom_complet(nc)
            if not any(v.values()):
                continue
            out.append({"n": j + 1, "v": v})
        colonnes = {k: entetes[i] for k, i in idx.items()}
        return colonnes, out, len(lignes) > MAX_LIGNES

    def analyser(v, classes, defaut, vus, n):
        """Contrôle d'une ligne. Retourne dict(action creer|maj|erreur, eleve, classe, valeurs, erreurs, avert)."""
        err, avert = [], []
        val = {}
        val["nom"] = " ".join((v.get("nom") or "").split()).upper()
        val["prenoms"] = " ".join((v.get("prenoms") or "").split())
        if not val["nom"] or not val["prenoms"]:
            err.append("nom et prénoms obligatoires")
        s = v.get("sexe", "")
        val["sexe"] = X.sexe(s)
        if not val["sexe"]:
            err.append(f"sexe « {s} » non reconnu (M ou F)" if s else "sexe manquant (M ou F)")
        brut = v.get("date_naissance", "")
        val["date_naissance"] = X.date_iso(brut) if brut else ""
        if brut and not val["date_naissance"]:
            err.append(f"date de naissance « {brut} » illisible (ex. 03/05/2015)")
        elif val["date_naissance"]:
            if val["date_naissance"] > date.today().isoformat():
                err.append("date de naissance dans le futur")
            elif val["date_naissance"] < "1950-01-01":
                err.append(f"date de naissance improbable ({brut})")
        for k in ("lieu_naissance", "parent_nom", "parent_telephone", "parent_whatsapp", "adresse",
                  "matricule_educmaster", "nip", "numero_table", "centre_examen"):
            val[k] = " ".join((v.get(k) or "").split())
        a = (v.get("annees_scolarite") or "").strip()
        val["annees_scolarite"] = None
        if a:
            if a.isdigit() and 0 <= int(a) <= 20:
                val["annees_scolarite"] = int(a)
            else:
                avert.append(f"années de scolarité « {a} » ignorées")
        r = v.get("redoublant", "")
        val["redoublant"] = oui_non(r)
        if val["redoublant"] is None:
            avert.append(f"redoublant « {r} » non compris (O/N) : ignoré")
        st = X.normaliser(v.get("statut", "")).replace(" ", "")
        val["statut"] = STATUTS.get(st)
        if st and not val["statut"]:
            avert.append(f"statut « {v.get('statut')} » ignoré")
        # élève existant ?
        eleve, mat = None, (v.get("matricule") or "").strip()
        if mat:
            eleve = q("SELECT * FROM eleves WHERE matricule=? COLLATE NOCASE", (mat,), un=True)
            if eleve and eleve["classe_id"] and not q("SELECT 1 FROM classes WHERE id=? AND ecole_id=?",
                                                        (eleve["classe_id"], H.eco()), un=True):
                err.append(f"le matricule {mat} appartient à un élève d'une autre école")
                eleve = None
        if not eleve and val["matricule_educmaster"]:
            eleve = q("""SELECT e.* FROM eleves e JOIN classes c ON c.id=e.classe_id AND c.ecole_id=?
                         WHERE e.matricule_educmaster=?""", (H.eco(), val["matricule_educmaster"]), un=True)
        if not eleve and not mat and val["nom"] and val["prenoms"] and val["date_naissance"]:
            eleve = q("""SELECT e.* FROM eleves e JOIN classes c ON c.id=e.classe_id AND c.ecole_id=?
                         WHERE e.nom=? AND e.prenoms=? COLLATE NOCASE AND e.date_naissance=?""",
                      (H.eco(), val["nom"], val["prenoms"], val["date_naissance"]), un=True)
            if eleve:
                avert.append(f"déjà inscrit(e) sous le matricule {eleve['matricule']} : fiche mise à jour")
        val["matricule"] = mat if (mat and not eleve) else ""
        # classe
        cl_txt = (v.get("classe") or "").strip()
        classe = retrouver_classe(cl_txt, classes) if cl_txt else None
        if cl_txt and not classe:
            if defaut:
                avert.append(f"classe « {cl_txt} » inconnue : classe par défaut {defaut['nom']}")
                classe = defaut
            else:
                err.append(f"classe « {cl_txt} » inconnue dans cette école")
        if not classe:
            if eleve:
                classe = next((c for c in classes if c["id"] == eleve["classe_id"]), None)
                if classe is None:
                    err.append("la classe actuelle de cet élève ne vous est pas accessible")
            elif defaut:
                classe = defaut
            elif not cl_txt:
                err.append("classe manquante : indiquez-la ou choisissez une classe par défaut")
        if eleve and classe and eleve["classe_id"] != classe["id"] and \
                eleve["classe_id"] not in {c["id"] for c in classes}:
            err.append("cet élève est dans une classe qui ne vous est pas accessible")
        # doublons dans le fichier
        cles = []
        if eleve:
            cles.append(("id", eleve["id"]))
        if mat:
            cles.append(("mat", mat.upper()))
        if val["matricule_educmaster"]:
            cles.append(("em", val["matricule_educmaster"]))
        if val["nom"] and val["date_naissance"]:
            cles.append(("nom", val["nom"], val["prenoms"].lower(), val["date_naissance"]))
        for c in cles:
            if c in vus:
                err.append(f"doublon de la ligne {vus[c]}")
                break
        if not err:
            for c in cles:
                vus[c] = n
        action = "erreur" if err else ("maj" if eleve else "creer")
        return {"action": action, "eleve": eleve, "classe": classe, "valeurs": val, "erreurs": err, "avert": avert}

    def cle_import():
        return f"e{H.eco()}:insc:import:u{g.user['id']}"

    def cle_rapport():
        return f"e{H.eco()}:insc:rapport:u{g.user['id']}"

    def ligne_rapport(r, resultat, matricule, message):
        """Ligne du rapport d'import (affichée et téléchargeable en Excel)."""
        v = r["valeurs"]
        return {"n": r["n"], "nom": v.get("nom") or r["brut"].get("nom", ""),
                "prenoms": v.get("prenoms") or r["brut"].get("prenoms", ""),
                "classe": r["classe"]["nom"] if r.get("classe") else (r["brut"].get("classe") or ""),
                "matricule": matricule or "", "resultat": resultat, "message": message}

    def classe_defaut(classes):
        cid = request.form.get("classe_defaut", type=int)
        return next((c for c in classes if c["id"] == cid), None)

    def analyser_tout(donnees, classes):
        defaut = next((c for c in classes if c["id"] == donnees.get("classe_defaut")), None)
        vus, res = {}, []
        for ligne in donnees["lignes"]:
            r = analyser(ligne["v"], classes, defaut, vus, ligne["n"])
            r["n"] = ligne["n"]
            r["brut"] = ligne["v"]
            res.append(r)
        return res, defaut

    def appliquer(r):
        """Crée ou met à jour l'élève d'une ligne analysée. Retourne (eid, matricule, action)."""
        val, cl, e = r["valeurs"], r["classe"], r["eleve"]
        simples = ("lieu_naissance", "parent_nom", "parent_telephone", "parent_whatsapp", "adresse",
                   "matricule_educmaster", "nip", "numero_table", "centre_examen")
        if e:
            champs = {"nom": val["nom"], "prenoms": val["prenoms"], "sexe": val["sexe"], "classe_id": cl["id"]}
            for k in simples + ("date_naissance",):
                if val[k]:
                    champs[k] = val[k]           # une cellule vide n'efface pas la donnée existante
            for k in ("annees_scolarite", "redoublant", "statut"):
                if val[k] is not None:
                    champs[k] = val[k]
            cols = list(champs)
            ex(f"UPDATE eleves SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
               [champs[c] for c in cols] + [e["id"]])
            return e["id"], e["matricule"], "maj"
        champs = {k: (val[k] or None) for k in simples + ("date_naissance",)}
        champs.update(nom=val["nom"], prenoms=val["prenoms"], sexe=val["sexe"], classe_id=cl["id"],
                      statut=val["statut"] or "inscrit", annees_scolarite=val["annees_scolarite"],
                      redoublant=val["redoublant"] or 0, date_inscription=date.today().isoformat(),
                      annee=config.ANNEE_ACTIVE)
        cols = list(champs)
        eid = ex(f"INSERT INTO eleves ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                 [champs[c] for c in cols])
        mat = val["matricule"]
        if not mat or q("SELECT 1 FROM eleves WHERE matricule=? COLLATE NOCASE AND id<>?", (mat, eid), un=True):
            mat = matricule_auto(eid, cl)
        ex("UPDATE eleves SET matricule=? WHERE id=?", (mat, eid))
        return eid, mat, "creer"

    @app.route("/eleves/import", methods=["GET", "POST"])
    @H.connexion_requise("eleves")
    def eleves_import():
        classes = classes_ecole()
        if not classes:
            flash("Créez d'abord au moins une classe.", "warning")
            return redirect(url_for("classes"))
        action = request.form.get("action", "")
        if request.method == "POST" and action == "analyser":
            f = request.files.get("fichier")
            nom = (f.filename or "").lower() if f else ""
            if not nom:
                flash("Choisissez un fichier Excel (.xlsx) ou CSV.", "danger")
                return render_template("insc_import.html", classes=classes, etape="choix"), 400
            if not nom.endswith(EXT_IMPORT):
                flash("Format non pris en charge : enregistrez le fichier au format Excel .xlsx "
                      "(Fichier › Enregistrer sous) ou CSV.", "danger")
                return render_template("insc_import.html", classes=classes, etape="choix"), 400
            try:
                colonnes, lignes, tronque = lire_fichier(f)
            except X.ExcelIndisponible as e:
                flash(str(e), "danger")
                return render_template("insc_import.html", classes=classes, etape="choix"), 400
            except ValueError as e:
                flash(str(e), "danger")
                return render_template("insc_import.html", classes=classes, etape="choix"), 400
            if "nom" not in colonnes and "prenoms" not in colonnes and "nom_complet" not in colonnes:
                flash("Aucune colonne « Nom » / « Prénoms » n'a été reconnue dans ce fichier. "
                      "Téléchargez le modèle Excel pour voir les intitulés attendus.", "danger")
                return render_template("insc_import.html", classes=classes, etape="choix"), 400
            if not lignes:
                flash("Le fichier ne contient aucune ligne d'élève sous les en-têtes.", "warning")
                return render_template("insc_import.html", classes=classes, etape="choix"), 400
            if tronque:
                flash(f"Seules les {MAX_LIGNES} premières lignes sont prises en compte.", "warning")
            defaut = classe_defaut(classes)
            donnees = {"fichier": f.filename[:120], "classe_defaut": defaut["id"] if defaut else None,
                       "colonnes": colonnes, "lignes": lignes, "cree": H.maintenant()}
            H.doc_ecrire(cle_import(), donnees)
            res, defaut = analyser_tout(donnees, classes)
            return render_template("insc_import.html", classes=classes, etape="apercu", res=res, d=donnees,
                                   defaut=defaut, LIBELLES=LIBELLES)
        if request.method == "POST" and action == "valider":
            donnees = H.doc_lire(cle_import())
            if not donnees or not donnees.get("lignes"):
                flash("Aucun import en attente : choisissez à nouveau le fichier.", "warning")
                return redirect(url_for("eleves_import"))
            choisis = set(request.form.getlist("lignes", type=int))
            res, defaut = analyser_tout(donnees, classes)  # nouvelle vérification au moment de valider
            crees, maj, ignores = [], [], []
            for r in res:
                if r["action"] == "erreur":
                    ignores.append((r, "; ".join(r["erreurs"])))
                elif r["n"] not in choisis:
                    ignores.append((r, "ligne décochée"))
                else:
                    eid, mat, act = appliquer(r)
                    (crees if act == "creer" else maj).append((r, eid, mat))
            H.doc_ecrire(cle_import(), {})
            rapport = ([ligne_rapport(r, "Inscrit", mat, "; ".join(r["avert"])) for r, _, mat in crees]
                       + [ligne_rapport(r, "Mis à jour", mat, "; ".join(r["avert"])) for r, _, mat in maj]
                       + [ligne_rapport(r, "Ignoré", r["eleve"]["matricule"] if r["eleve"] else "", raison)
                          for r, raison in ignores])
            rapport.sort(key=lambda x: x["n"])
            H.doc_ecrire(cle_rapport(), {"fichier": donnees.get("fichier"), "fait_le": H.maintenant(),
                                         "lignes": rapport})
            H.journal("eleves_import", f"{donnees.get('fichier')} : {len(crees)} créé(s), {len(maj)} mis à jour, "
                                       f"{len(ignores)} ignoré(s)")
            flash(f"Import terminé : {len(crees)} élève(s) inscrit(s), {len(maj)} fiche(s) mise(s) à jour, "
                  f"{len(ignores)} ligne(s) ignorée(s).", "success" if not ignores else "warning")
            return render_template("insc_import.html", classes=classes, etape="rapport", crees=crees, maj=maj,
                                   ignores=ignores, d=donnees)
        if request.method == "POST" and action == "annuler":
            H.doc_ecrire(cle_import(), {})
            flash("Import annulé.", "info")
            return redirect(url_for("eleves_import"))
        return render_template("insc_import.html", classes=classes, etape="choix",
                               cid=request.args.get("classe", type=int),
                               rapport_dispo=bool((H.doc_lire(cle_rapport()) or {}).get("lignes")))

    @app.route("/eleves/import/rapport.xlsx")
    @H.connexion_requise("eleves")
    def eleves_import_rapport():
        """Rapport du dernier import (une ligne par ligne du fichier : inscrit, mis à jour ou ignoré + motif)."""
        rap = H.doc_lire(cle_rapport()) or {}
        if not rap.get("lignes"):
            flash("Aucun rapport d'import disponible.", "warning")
            return redirect(url_for("eleves_import"))
        lignes = [[x["n"], x["resultat"], x["nom"], x["prenoms"], x["classe"], x["matricule"], x["message"]]
                  for x in rap["lignes"]]
        return X.reponse_xlsx("rapport_import_eleves.xlsx",
                              ["Ligne", "Résultat", "Nom", "Prénoms", "Classe", "Matricule", "Observation / erreur"],
                              lignes, titre="Rapport d'import",
                              titre_haut=[f"{config.ECOLE['nom']} — rapport d'import des élèves",
                                          f"Fichier : {rap.get('fichier') or '?'} · importé le {rap.get('fait_le', '')}"])

    # ============================================================ photos rapides (caméra) pour une classe
    @app.route("/eleves/photos-camera", methods=["GET"])
    @app.route("/eleves/<int:eid>/photo-camera", methods=["GET", "POST"])
    @H.connexion_requise("eleves")
    def insc_photo(eid=None):
        classes = classes_ecole()
        e = None
        if eid:
            e = H.eleve_ou_404(eid)
            if e["classe_id"] not in {c["id"] for c in classes}:
                abort(403)
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            img = data.get("image") or request.form.get("photo_data", "")
            if not H.enregistrer_photo_data(eid, img):
                return {"ok": False, "erreur": "Photo invalide ou trop lourde."}, 400
            H.journal("photo_camera", e["matricule"] or str(eid))
            return {"ok": True, "url": url_for("eleve_photo", eid=eid, v=secrets.token_hex(3))}
        cid = e["classe_id"] if e else request.args.get("classe", type=int)
        cl = next((c for c in classes if c["id"] == cid), None)
        tous = request.args.get("tous") == "1"
        eleves = []
        if cl:
            eleves = q("SELECT * FROM eleves WHERE classe_id=? AND statut='inscrit' ORDER BY nom, prenoms", (cl["id"],))
        avec = {x["id"] for x in eleves if H.chemin_photo(x)}
        visibles = [x for x in eleves if tous or x["id"] not in avec or (e and x["id"] == e["id"])]
        return render_template("insc_photo.html", classes=classes, cl=cl, eleves=visibles, avec=avec,
                               total=len(eleves), tous=tous, ouvrir=e["id"] if e else None)

    # ============================================================ comptes élèves (côté école)
    def url_espace_eleve():
        base = config.URL_PUBLIQUE or request.host_url
        return base.rstrip("/") + url_for("eleve_login")

    def eleves_de_classe(cid):
        return q("""SELECT e.*, k.doit_changer, k.actif compte_actif, k.dernier_acces, k.cree_le compte_cree
                    FROM eleves e LEFT JOIN comptes_eleves k ON k.eleve_id=e.id
                    WHERE e.classe_id=? AND e.statut='inscrit' ORDER BY e.nom, e.prenoms""", (cid,))

    def donner_acces(e):
        mdp = mdp_provisoire()
        ex("UPDATE eleves SET mdp_hash=? WHERE id=?", (generate_password_hash(mdp), e["id"]))
        ex("""INSERT INTO comptes_eleves (eleve_id, doit_changer, actif, cree_le, cree_par) VALUES (?,1,1,?,?)
              ON CONFLICT(eleve_id) DO UPDATE SET doit_changer=1, actif=1, cree_le=excluded.cree_le,
              cree_par=excluded.cree_par""", (e["id"], H.maintenant(), g.user["id"]))
        return mdp

    @app.route("/eleves/acces-eleves", methods=["GET", "POST"])
    @H.connexion_requise("eleves")
    def espace_eleves_acces():
        classes = classes_ecole()
        cid = request.values.get("classe", type=int)
        cl = next((c for c in classes if c["id"] == cid), None)
        if request.method == "POST":
            if not cl:
                abort(403)
            act = request.form.get("action")
            eleves = eleves_de_classe(cl["id"])
            choisis = set(request.form.getlist("eleves", type=int))
            lignes = []
            sans_mat = 0
            if act == "creer":
                for e in eleves:
                    if not e["mdp_hash"] or not e["compte_actif"]:
                        if not e["matricule"]:          # le matricule sert d'identifiant de connexion
                            sans_mat += 1
                            continue
                        lignes.append((e, donner_acces(e)))
            elif act == "reinit":
                for e in eleves:
                    if e["id"] in choisis:
                        if not e["matricule"]:
                            sans_mat += 1
                            continue
                        lignes.append((e, donner_acces(e)))
            elif act == "retirer":
                n = 0
                for e in eleves:
                    if e["id"] in choisis:
                        ex("UPDATE eleves SET mdp_hash=NULL WHERE id=?", (e["id"],))
                        ex("DELETE FROM comptes_eleves WHERE eleve_id=?", (e["id"],))
                        n += 1
                H.journal("eleves_acces_retires", f"{cl['nom']} : {n}")
                flash(f"{n} accès retiré(s).", "success")
                return redirect(url_for("espace_eleves_acces", classe=cl["id"]))
            else:
                abort(400)
            if sans_mat:
                flash(f"{sans_mat} élève(s) sans matricule n'ont pas reçu d'accès : complétez leur fiche.", "warning")
            if not lignes:
                flash("Aucun accès créé : " + ("tous les élèves de la classe ont déjà un accès."
                                               if act == "creer" else "cochez au moins un élève."), "warning")
                return redirect(url_for("espace_eleves_acces", classe=cl["id"]))
            H.journal("eleves_acces", f"{cl['nom']} : {len(lignes)} accès ({act})")
            return render_template("espace_eleve_codes.html", cl=cl, lignes=lignes, url=url_espace_eleve())
        eleves = eleves_de_classe(cl["id"]) if cl else []
        nb_comptes = sum(1 for e in eleves if e["mdp_hash"] and e["compte_actif"])
        return render_template("espace_eleve_acces.html", classes=classes, cl=cl, eleves=eleves,
                               nb_comptes=nb_comptes, url=url_espace_eleve())

    @app.route("/eleves/acces-eleves/codes.pdf", methods=["POST"])
    @H.connexion_requise("eleves")
    def espace_eleves_codes_pdf():
        """Liste imprimable des codes d'accès. Les mots de passe provisoires sont renvoyés par la page qui vient
        de les créer et VÉRIFIÉS contre l'empreinte en base : impossible d'imprimer un faux code."""
        autorisees = {c["id"]: c for c in classes_ecole()}
        lignes = []
        for eid, mdp in zip(request.form.getlist("eid", type=int), request.form.getlist("mdp")):
            e = q("SELECT e.*, k.doit_changer FROM eleves e JOIN comptes_eleves k ON k.eleve_id=e.id WHERE e.id=?",
                  (eid,), un=True)
            if not e or e["classe_id"] not in autorisees or not e["mdp_hash"] or not e["doit_changer"]:
                continue
            if check_password_hash(e["mdp_hash"], mdp):
                lignes.append((e, autorisees[e["classe_id"]], mdp))
        if not lignes:
            flash("Codes expirés ou déjà modifiés par les élèves : réinitialisez les accès pour les imprimer.", "warning")
            return redirect(url_for("espace_eleves_acces"))
        classes_noms = sorted({cl["nom"] for _, cl, _ in lignes})
        pdf = H.pdfs.document_tableau(
            "CODES D'ACCÈS À L'ESPACE ÉLÈVE",
            ["N°", "Nom et prénoms", "Classe", "Identifiant (matricule)", "Mot de passe provisoire", "Émargement"],
            [[i, f"{e['nom']} {e['prenoms']}", cl["nom"], e["matricule"], mdp, ""]
             for i, (e, cl, mdp) in enumerate(lignes, 1)],
            sous_titre=f"Classe(s) : {', '.join(classes_noms)} — année {config.ANNEE_ACTIVE}",
            infos=[("Adresse de l'espace élève", url_espace_eleve())],
            largeurs=[10, 58, 22, 40, 34, 26], taille=9,
            notes_bas=["À la première connexion, l'élève choisit son propre mot de passe (6 caractères au moins).",
                       "Découpez ou recopiez chaque ligne pour la remettre à l'élève. Ne pas afficher cette liste."])
        H.journal("eleves_codes_pdf", f"{len(lignes)} code(s)")
        return H.pdf_reponse(pdf, "codes_acces_eleves.pdf")

    # ============================================================ espace élève (côté élève)
    @app.before_request
    def charger_eleve_connecte():
        g.eleve_session = None
        eid = session.get("eid_eleve")
        if eid:
            e = q("""SELECT e.*, k.doit_changer, k.dernier_acces FROM eleves e
                     JOIN comptes_eleves k ON k.eleve_id=e.id AND k.actif=1
                     WHERE e.id=? AND e.statut='inscrit' AND e.mdp_hash IS NOT NULL""", (eid,), un=True)
            if e:
                g.eleve_session = e
            else:
                session.pop("eid_eleve", None)

    def eleve_requis(f):
        @wraps(f)
        def wrap(*a, **k):
            if not g.get("eleve_session"):
                return redirect(url_for("eleve_login", suivant=request.path))
            if g.eleve_session["doit_changer"] and request.endpoint not in ("eleve_mdp", "eleve_logout"):
                flash("Choisissez votre mot de passe personnel.", "warning")
                return redirect(url_for("eleve_mdp"))
            return f(*a, **k)
        return wrap

    H.eleve_requis = eleve_requis

    def moi():
        return g.eleve_session

    def ma_classe():
        return H.classe_de(moi())

    def periodes_publiees(cid):
        return {r["periode"] for r in q("SELECT periode FROM publications WHERE classe_id=? AND annee=?",
                                        (cid, config.ANNEE_ACTIVE))}

    @app.route("/eleve/connexion", methods=["GET", "POST"])
    def eleve_login():
        if request.method == "POST":
            ident = (request.form.get("identifiant") or "").strip()[:60]
            cle = f"{ident.upper()}|{request.remote_addr}"
            if _trop_de_tentatives(cle):
                flash("Trop de tentatives. Réessayez dans 15 minutes.", "danger")
                return render_template("espace_eleve_login.html"), 429
            e = q("""SELECT e.*, c.ecole_id FROM eleves e JOIN comptes_eleves k ON k.eleve_id=e.id AND k.actif=1
                     LEFT JOIN classes c ON c.id=e.classe_id
                     WHERE e.matricule=? COLLATE NOCASE AND e.statut='inscrit' AND e.mdp_hash IS NOT NULL""",
                  (ident,), un=True) if ident else None
            if e and check_password_hash(e["mdp_hash"], request.form.get("mdp", "")):
                session.pop("uid", None)
                session.pop("pid", None)
                session["eid_eleve"] = e["id"]
                if e["ecole_id"]:
                    session["ecole_id"] = e["ecole_id"]
                session.permanent = True
                ex("UPDATE comptes_eleves SET dernier_acces=? WHERE eleve_id=?", (H.maintenant(), e["id"]))
                suivant = request.args.get("suivant", "")
                return redirect(suivant if suivant.startswith("/eleve/") or suivant == "/eleve"
                                else url_for("eleve_accueil"))
            _tentatives.setdefault(cle, []).append(datetime.now())
            flash("Identifiant (matricule) ou mot de passe incorrect.", "danger")
        return render_template("espace_eleve_login.html")

    @app.route("/eleve/deconnexion")
    def eleve_logout():
        session.pop("eid_eleve", None)
        return redirect(url_for("eleve_login"))

    @app.route("/eleve/mot-de-passe", methods=["GET", "POST"])
    @eleve_requis
    def eleve_mdp():
        if request.method == "POST":
            ancien, nouveau, conf = (request.form.get(k, "") for k in ("ancien", "nouveau", "confirmation"))
            if not check_password_hash(moi()["mdp_hash"], ancien):
                flash("Mot de passe actuel incorrect.", "danger")
            elif len(nouveau) < 6:
                flash("Le nouveau mot de passe doit faire au moins 6 caractères.", "danger")
            elif nouveau != conf:
                flash("La confirmation ne correspond pas.", "danger")
            elif nouveau == ancien:
                flash("Choisissez un mot de passe différent du code provisoire.", "danger")
            else:
                ex("UPDATE eleves SET mdp_hash=? WHERE id=?", (generate_password_hash(nouveau), moi()["id"]))
                ex("UPDATE comptes_eleves SET doit_changer=0 WHERE eleve_id=?", (moi()["id"],))
                flash("Mot de passe enregistré.", "success")
                return redirect(url_for("eleve_accueil"))
        return render_template("espace_eleve_mdp.html")

    def resume_absences(eid):
        d1, d2 = H.bornes_annee()
        pres = q("SELECT * FROM presences WHERE eleve_id=? AND date BETWEEN ? AND ? ORDER BY date DESC", (eid, d1, d2))
        reg = q("SELECT date, GROUP_CONCAT(demi) demis, COUNT(*) n FROM registre WHERE eleve_id=? "
                "AND date BETWEEN ? AND ? GROUP BY date ORDER BY date DESC", (eid, d1, d2))
        return pres, reg

    @app.route("/eleve")
    @eleve_requis
    def eleve_accueil():
        e, cl = moi(), ma_classe()
        pres, reg = resume_absences(e["id"])
        nb_pub = len(periodes_publiees(cl["id"])) if cl else 0
        return render_template("espace_eleve_accueil.html", e=e, cl=cl, a_photo=bool(H.chemin_photo(e)),
                               nb_abs=sum(1 for p in pres if p["statut"] == "absent"),
                               nb_ret=sum(1 for p in pres if p["statut"] == "retard"),
                               nb_demi=sum(r["n"] for r in reg), nb_pub=nb_pub)

    @app.route("/eleve/photo")
    @eleve_requis
    def eleve_ma_photo():
        from flask import send_file
        p = H.chemin_photo(moi())
        if not p:
            abort(404)
        return send_file(p, max_age=0)

    @app.route("/eleve/resultats")
    @eleve_requis
    def eleve_resultats():
        e, cl = moi(), ma_classe()
        bulletins, evals = [], []
        if cl:
            pub = periodes_publiees(cl["id"])
            for i, per in enumerate(config.PERIODES, 1):
                if per in pub:
                    _, _, _, res, stats = H.resultats_classe(cl, per)
                    if e["id"] in res:
                        bulletins.append((i, per, res[e["id"]], stats))
            for ev in EC.evaluations_classe(cl["id"]):
                if ev["libelle"] not in pub:        # seules les évaluations publiées sont visibles
                    continue
                matieres, lignes = EC.resultats(ev, cl)
                ma = next((l for l in lignes if l["eleve"]["id"] == e["id"]), None)   # uniquement SA ligne
                if ma and any(l["compose"] for l in lignes):
                    evals.append({"ev": ev, "matieres": matieres, "l": ma})
        return render_template("espace_eleve_resultats.html", e=e, cl=cl, bulletins=bulletins, evals=evals)

    @app.route("/eleve/bulletin/<int:p>.pdf")
    @eleve_requis
    def eleve_bulletin(p):
        e, cl = moi(), ma_classe()
        per = H.periode_de(p)
        if not cl or per not in periodes_publiees(cl["id"]):
            abort(404)
        _, _, _, res, stats = H.resultats_classe(cl, per)
        if e["id"] not in res:
            abort(404)
        return H.pdf_reponse(H.pdfs.bulletins([app.bulletin_data(cl, per, e, res[e["id"]], stats)]),
                             f"bulletin_{e['matricule']}_{per}.pdf")

    @app.route("/eleve/absences")
    @eleve_requis
    def eleve_absences():
        e = moi()
        pres, reg = resume_absences(e["id"])
        return render_template("espace_eleve_absences.html", e=e, pres=pres, reg=reg,
                               stats=H.absences_eleve(e["id"]))

    @app.route("/eleve/carte")
    @eleve_requis
    def eleve_carte():
        return render_template("espace_eleve_carte.html", e=moi(), cl=ma_classe(), a_photo=bool(H.chemin_photo(moi())))

    @app.route("/eleve/carte.pdf")
    @eleve_requis
    def eleve_carte_pdf():
        e, cl = moi(), ma_classe()
        if not cl:
            flash("Vous n'êtes inscrit(e) dans aucune classe : adressez-vous au secrétariat.", "warning")
            return redirect(url_for("eleve_carte"))
        a = config.ANNEE_ACTIVE
        code = H.enregistrer_document("carte", e["id"], f"Carte d'élève – {e['nom']} {e['prenoms']} ({a})",
                                      cle=f"{e['id']}|{a}")
        return H.pdf_reponse(H.pdfs.carte(e, cl, a, code, H.chemin_photo(e)), f"carte_{e['matricule']}.pdf")

    # ============================================================ espace enseignant
    @app.route("/mon-espace")
    @H.connexion_requise()
    def espace_enseignant():
        u = g.user
        if not any(H.peut(d) for d in ("notes", "evaluations", "registre", "appel")):
            abort(403)                                  # ex. comptable : aucune classe à tenir
        affect = q("SELECT * FROM affectations WHERE user_id=?", (u["id"],))
        noms_mat = {m["id"]: m["nom"] for m in q("SELECT id, nom FROM matieres")}
        mats = {}
        for a in affect:
            mats.setdefault(a["classe_id"], set())
            if a["matiere_id"]:
                mats[a["classe_id"]].add(noms_mat.get(a["matiere_id"], "?"))
        lignes = []
        for c in classes_ecole():
            eff = q("""SELECT COUNT(*) n, SUM(sexe='F') f, SUM(sexe='M') m FROM eleves
                       WHERE classe_id=? AND statut='inscrit'""", (c["id"],), un=True)
            nb_ev = q("SELECT COUNT(*) n FROM evaluations WHERE classe_id=? AND annee=?",
                      (c["id"], config.ANNEE_ACTIVE), un=True)["n"]
            lignes.append({"c": c, "n": eff["n"] or 0, "f": eff["f"] or 0, "m": eff["m"] or 0, "nb_ev": nb_ev,
                           "matieres": sorted(mats.get(c["id"], []))})
        return render_template("espace_ens_accueil.html", lignes=lignes, affecte=bool(affect),
                               aujourdhui=date.today().isoformat(),
                               peut_signer=u["role"] != "comptable")

    # ============================================================ tableau de bord du fondateur
    def fondateur_requis():
        if g.user["role"] not in ("fondateur", "admin"):
            abort(403)

    def indicateurs_ecoles():
        a = config.ANNEE_ACTIVE
        auj = date.today().isoformat()
        lignes = []
        for ec in q("SELECT * FROM ecoles WHERE actif=1 ORDER BY nom"):
            i = ec["id"]
            el = q("""SELECT COUNT(*) n, SUM(e.sexe='F') f, SUM(e.sexe='M') m, COALESCE(SUM(c.frais_scolarite),0) du
                      FROM eleves e JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=? AND e.statut='inscrit'""",
                   (i,), un=True)
            # impayés : reste dû par élève inscrit (frais de la classe − paiements non annulés de l'année)
            imp = q("""SELECT COALESCE(SUM(MAX(du - paye, 0)),0) reste, COALESCE(SUM(du > paye),0) nb FROM (
                         SELECT COALESCE(c.frais_scolarite,0) du,
                                (SELECT COALESCE(SUM(p.montant),0) FROM paiements p
                                 WHERE p.eleve_id=e.id AND p.annee=? AND p.annule=0) paye
                         FROM eleves e JOIN classes c ON c.id=e.classe_id
                         WHERE c.ecole_id=? AND e.statut='inscrit')""", (a, i), un=True)
            enc = q("""SELECT COALESCE(SUM(p.montant),0) s FROM paiements p JOIN eleves e ON e.id=p.eleve_id
                       JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=? AND p.annee=? AND p.annule=0""",
                    (i, a), un=True)["s"]
            nb_cl = q("SELECT COUNT(*) n FROM classes WHERE ecole_id=?", (i,), un=True)["n"]
            absents = q("""SELECT COUNT(DISTINCT e.id) n FROM eleves e JOIN classes c ON c.id=e.classe_id
                           WHERE c.ecole_id=? AND e.statut='inscrit' AND (
                             e.id IN (SELECT eleve_id FROM presences WHERE date=? AND statut='absent')
                             OR e.id IN (SELECT eleve_id FROM registre WHERE date=?))""", (i, auj, auj), un=True)["n"]
            appels = q("""SELECT COUNT(DISTINCT cid) n FROM (
                            SELECT a.classe_id cid FROM appels a JOIN classes c ON c.id=a.classe_id
                            WHERE c.ecole_id=? AND a.date=?
                            UNION SELECT e.classe_id FROM registre r JOIN eleves e ON e.id=r.eleve_id
                            JOIN classes c ON c.id=e.classe_id WHERE c.ecole_id=? AND r.date=?)""",
                       (i, auj, i, auj), un=True)["n"]
            ens = q("""SELECT COUNT(*) n FROM utilisateurs u WHERE u.role='enseignant' AND u.actif=1 AND (
                         u.id IN (SELECT a.user_id FROM affectations a JOIN classes c ON c.id=a.classe_id
                                  WHERE c.ecole_id=?))""", (i,), un=True)["n"]
            n = el["n"] or 0
            lignes.append({"ecole": ec, "eleves": n, "f": el["f"] or 0, "m": el["m"] or 0, "classes": nb_cl,
                           "attendu": el["du"] or 0, "encaisse": enc, "impaye": imp["reste"], "nb_impayes": imp["nb"],
                           "taux": round(100 * enc / el["du"], 1) if el["du"] else 0.0,
                           "absents": absents, "presents": max(n - absents, 0), "appels": appels,
                           "enseignants": ens})
        tot = {k: sum(l[k] for l in lignes) for k in ("eleves", "f", "m", "classes", "attendu", "encaisse", "impaye",
                                                      "nb_impayes", "absents", "presents", "appels", "enseignants")}
        tot["taux"] = round(100 * tot["encaisse"] / tot["attendu"], 1) if tot["attendu"] else 0.0
        return lignes, tot

    ENTETES_F = ["École", "Élèves", "Filles", "Garçons", "Classes", "Attendu (FCFA)", "Encaissé (FCFA)",
                 "Impayés (FCFA)", "Élèves débiteurs", "Recouvrement (%)", "Présents", "Absents", "Classes appelées",
                 "Enseignants affectés"]

    # mêmes colonnes, intitulés coupés pour tenir dans l'en-tête du PDF (paysage)
    ENTETES_PDF = ["École", "Élèves", "Filles", "Garçons", "Classes", "Attendu\n(FCFA)", "Encaissé\n(FCFA)",
                   "Impayés\n(FCFA)", "Élèves\ndébiteurs", "Recouvre-\nment (%)", "Présents", "Absents",
                   "Classes\nappelées", "Ensei-\ngnants"]

    def lignes_f(lignes, tot, texte=False):
        fm = H.fcfa if texte else (lambda v: v)
        out = [[l["ecole"]["nom"], l["eleves"], l["f"], l["m"], l["classes"], fm(l["attendu"]), fm(l["encaisse"]),
                fm(l["impaye"]), l["nb_impayes"], (f"{l['taux']:.1f}".replace(".", ",") if texte else l["taux"]), l["presents"], l["absents"],
                f"{l['appels']}/{l['classes']}", l["enseignants"]] for l in lignes]
        total = ["TOTAL", tot["eleves"], tot["f"], tot["m"], tot["classes"], fm(tot["attendu"]), fm(tot["encaisse"]),
                 fm(tot["impaye"]), tot["nb_impayes"], (f"{tot['taux']:.1f}".replace(".", ",") if texte else tot["taux"]), tot["presents"], tot["absents"],
                 f"{tot['appels']}/{tot['classes']}", tot["enseignants"]]
        return out, total

    @app.route("/fondateur")
    @H.connexion_requise()
    def fondateur_tableau():
        fondateur_requis()
        lignes, tot = indicateurs_ecoles()
        return render_template("fondateur_tableau.html", lignes=lignes, tot=tot, aujourdhui=date.today().isoformat())

    @app.route("/fondateur/tableau.pdf")
    @H.connexion_requise()
    def fondateur_pdf():
        fondateur_requis()
        lignes, tot = indicateurs_ecoles()
        corps, total = lignes_f(lignes, tot, texte=True)
        pdf = H.pdfs.document_tableau(
            "TABLEAU DE BORD DU FONDATEUR", ENTETES_PDF, corps, total=total, paysage=True, taille=8,
            sous_titre=f"Année scolaire {config.ANNEE_ACTIVE} — situation au {date.today().strftime('%d/%m/%Y')}",
            infos_haut=[("Promoteur", "Toutes les écoles actives"), ("Écoles", str(len(lignes)))],
            largeurs=[60, 15, 15, 18, 17, 30, 30, 30, 19, 21, 19, 18, 19, 18],
            notes_bas=["Encaissé : paiements de scolarité non annulés de l'année. Attendu : frais de scolarité des "
                       "classes × élèves inscrits. Impayés : reste dû des élèves inscrits (élèves débiteurs = nombre "
                       "d'élèves concernés).", "Présents / absents : registre d'appel et registre de présence "
                       "du jour ; « Classes appelées » = classes dont l'appel a été fait aujourd'hui."])
        H.journal("fondateur_pdf")
        return H.pdf_reponse(pdf, f"tableau_fondateur_{date.today().isoformat()}.pdf")

    @app.route("/fondateur/tableau.xlsx")
    @H.connexion_requise()
    def fondateur_xlsx():
        fondateur_requis()
        lignes, tot = indicateurs_ecoles()
        corps, total = lignes_f(lignes, tot)
        H.journal("fondateur_xlsx")
        return X.reponse_xlsx(f"tableau_fondateur_{date.today().isoformat()}.xlsx", ENTETES_F, corps + [total],
                              titre="Tableau de bord",
                              titre_haut=[f"Tableau de bord du fondateur — {config.ANNEE_ACTIVE}",
                                          f"Situation au {date.today().strftime('%d/%m/%Y')}"])
