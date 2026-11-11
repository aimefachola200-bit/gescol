# -*- coding: utf-8 -*-
"""Listes de classe — accès rapide (v2.3.3).

Demande : « présente dans les applications la rubrique liste des classes par cours sans être obligé d'aller dans la
rubrique inscription ; il faut un accès rapide ».

Page /listes-classe en LECTURE SEULE (les pages d'inscription ne changent pas) : cours (Maternelle 1 et 2, CI … CM2,
autres niveaux présents) → classe (ou toutes les classes du cours) → liste des élèves inscrits : N° d'ordre, nom,
prénoms, sexe, date et lieu de naissance, matricule / EducMaster, statut nouveau / redoublant, contact du parent ;
effectifs G / F / T, recherche, tri, lien vers la fiche de l'élève ; « Télécharger PDF » (en-tête officiel, Times
New Roman 14 pt), « Excel EducMaster (importation) » (modèle officiel, importable tel quel), « Excel liste de
classe (lisible) », « Imprimer ».

Périmètre : éditions école — l'école courante (H.eco()) ; l'enseignant ne voit que ses classes affectées
(table affectations, sans repli sur toute l'école) ; l'observateur national n'a pas accès aux listes nominatives.
Éditions CS / DDEMP — école → cours → classe, parmi les écoles accessibles au compte qui ont des élèves
(ecoles locales ouvertes depuis la juridiction) ; page de la structure (pas de page « Choisissez une école »).
Accès : menu principal (Scolarité / Ma classe / menu de la juridiction), tuile du tableau de bord, portail enseignant.
"""
import io
import unicodedata

from flask import Response, abort, g, render_template, request

import config
from calcul import NIVEAUX_MATERNELLE, NIVEAUX_PRIMAIRE, NIVEAUX_SECONDAIRE

ORDRE_NIVEAUX = NIVEAUX_MATERNELLE + ["Espace enfance"] + NIVEAUX_PRIMAIRE + NIVEAUX_SECONDAIRE
TRIS = {"nom": "Nom et prénoms", "sexe": "Sexe", "naissance": "Date de naissance", "matricule": "Matricule",
        "statut": "Statut (nouveau / redoublant)", "classe": "Classe"}
ROLES_EXCLUS = {"observateur"}
ENTETES = ["N°", "Nom", "Prénoms", "Sexe", "Date et lieu de naissance", "Matricule / EducMaster", "Statut",
           "Contact du parent"]


def _sans_accents(t):
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


def rang_niveau(n):
    return (ORDRE_NIVEAUX.index(n), n) if n in ORDRE_NIVEAUX else (len(ORDRE_NIVEAUX), n or "")


def statut_eleve(e):
    return "Redoublant" if (e.get("redoublant") or 0) else "Nouveau"


def matricules(e):
    m, em = (e.get("matricule") or "").strip(), (e.get("matricule_educmaster") or "").strip()
    return " / ".join(x for x in (m, em) if x) or "—"


def contact(e):
    nom, tel = (e.get("parent_nom") or "").strip(), (e.get("parent_telephone") or e.get("parent_whatsapp") or "").strip()
    return " — ".join(x for x in (nom, tel) if x) or "—"


def trier(eleves, tri):
    cle = {
        "sexe": lambda e: (e.get("sexe") or "", _sans_accents(e["nom"]), _sans_accents(e["prenoms"])),
        "naissance": lambda e: (e.get("date_naissance") or "9999", _sans_accents(e["nom"])),
        "matricule": lambda e: (e.get("matricule") or e.get("matricule_educmaster") or "~", _sans_accents(e["nom"])),
        "statut": lambda e: (statut_eleve(e), _sans_accents(e["nom"]), _sans_accents(e["prenoms"])),
        "classe": lambda e: (e.get("classe_nom") or "", _sans_accents(e["nom"]), _sans_accents(e["prenoms"])),
    }.get(tri) or (lambda e: (_sans_accents(e["nom"]), _sans_accents(e["prenoms"])))
    return sorted(eleves, key=cle)


def compter(eleves):
    gar = sum(1 for e in eleves if (e.get("sexe") or "").upper().startswith(("M", "G")))
    fil = sum(1 for e in eleves if (e.get("sexe") or "").upper().startswith("F"))
    return {"g": gar, "f": fil, "t": len(eleves)}


def enregistrer(app, H):
    q = H.q

    def ecoles_possibles():
        """Écoles de la page : école courante (éditions école) ; écoles accessibles ayant des élèves (CS / DDEMP)."""
        if not config.juridiction():
            r = q("SELECT * FROM ecoles WHERE id=?", (H.eco(),), un=True)
            return [dict(r) if r else {"id": H.eco(), "nom": config.ECOLE.get("nom", "")}]
        avec = {r["ecole_id"] for r in q("SELECT DISTINCT c.ecole_id FROM eleves e JOIN classes c ON c.id=e.classe_id "
                                         "WHERE e.statut='inscrit'")}
        return [dict(e) for e in H.ecoles_accessibles() if e["id"] in avec]

    def classes_de(eid):
        """Classes visibles dans l'école eid (enseignant : ses classes affectées seulement)."""
        if g.user["role"] == "enseignant":
            ids = [r["classe_id"] for r in q("SELECT DISTINCT classe_id FROM affectations WHERE user_id=?", (g.user["id"],))]
            if not ids:
                return []
            return [dict(c) for c in q(f"SELECT * FROM classes WHERE ecole_id=? AND id IN ({','.join('?' * len(ids))})",
                                         [eid] + ids)]
        return [dict(c) for c in q("SELECT * FROM classes WHERE ecole_id=?", (eid,))]

    def contexte():
        if g.user["role"] in ROLES_EXCLUS:
            abort(403)
        ecoles = ecoles_possibles()
        ids = [e["id"] for e in ecoles]
        eid = request.args.get("ecole", type=int)
        if eid is not None and eid not in ids:
            abort(403)
        if eid is None:
            cour = g.ecole["id"] if g.get("ecole") else None
            eid = cour if cour in ids else (ids[0] if len(ids) == 1 or not config.juridiction() else None)
        ecole = next((e for e in ecoles if e["id"] == eid), None)
        classes = classes_de(eid) if ecole else []
        cid_ok = {c["id"] for c in classes}
        effectifs = {}
        if classes:
            for r in q(f"SELECT classe_id, COUNT(*) n FROM eleves WHERE statut='inscrit' AND classe_id IN "
                       f"({','.join('?' * len(classes))}) GROUP BY classe_id", [c["id"] for c in classes]):
                effectifs[r["classe_id"]] = r["n"]
        for c in classes:
            c["effectif"] = effectifs.get(c["id"], 0)
        cours_dispo = sorted({c["niveau"] for c in classes}, key=rang_niveau)
        cours = request.args.get("cours", "").strip()
        brut = request.args.get("classe", "").strip()
        classe = int(brut) if brut.isdigit() else None
        if classe is not None and classe not in cid_ok:
            abort(403)
        if classe is not None:
            cours = next(c["niveau"] for c in classes if c["id"] == classe)
        if cours and cours not in cours_dispo:
            cours = ""
        if not cours and len(cours_dispo) == 1:
            cours = cours_dispo[0]
        du_cours = sorted([c for c in classes if c["niveau"] == cours], key=lambda c: _sans_accents(c["nom"]))
        if classe is None and len(du_cours) == 1:
            classe = du_cours[0]["id"]
        choisies = [c for c in du_cours if classe is None or c["id"] == classe]
        rech = request.args.get("q", "").strip()
        tri = request.args.get("tri", "nom")
        tri = tri if tri in TRIS else "nom"
        eleves = []
        if cours and choisies:
            noms = {c["id"]: c["nom"] for c in choisies}
            ids_c = list(noms)
            for e in q(f"SELECT * FROM eleves WHERE statut='inscrit' AND classe_id IN ({','.join('?' * len(ids_c))})", ids_c):
                d = dict(e)
                d["classe_nom"] = noms.get(d["classe_id"], "")
                eleves.append(d)
            if rech:
                r = _sans_accents(rech)
                eleves = [e for e in eleves if r in _sans_accents(" ".join(str(e.get(k) or "") for k in (
                    "nom", "prenoms", "matricule", "matricule_educmaster", "parent_nom", "parent_telephone", "lieu_naissance")))]
            eleves = trier(eleves, tri)
        return {"ecoles": ecoles, "ecole": ecole, "classes": classes, "cours_dispo": cours_dispo, "cours": cours,
                "du_cours": du_cours, "classe": classe, "choisies": choisies, "eleves": eleves, "rech": rech, "tri": tri,
                "compte": compter(eleves), "plusieurs": len(choisies) > 1,
                "par_cours": {n: sum(c["effectif"] for c in classes if c["niveau"] == n) for n in cours_dispo}}

    def titre_de(x):
        if x["classe"] is not None and len(x["choisies"]) == 1:
            return f"LISTE DE LA CLASSE {x['choisies'][0]['nom'].upper()}"
        return f"LISTE DES ÉLÈVES DU {x['cours'].upper()} (toutes les classes)"

    def lignes_de(x):
        out = []
        for i, e in enumerate(x["eleves"], 1):
            ln = [i, (e["nom"] or "").upper(), e["prenoms"] or "", e.get("sexe") or "",
                  " à ".join(v for v in (H.pdfs.date_fr(e.get("date_naissance")) if e.get("date_naissance") else "",
                                          e.get("lieu_naissance") or "") if v) or "—",
                  matricules(e), statut_eleve(e), contact(e)]
            if x["plusieurs"]:
                ln.insert(3, e["classe_nom"])
            out.append(ln)
        return out

    def entetes_de(x):
        h = list(ENTETES)
        if x["plusieurs"]:
            h.insert(3, "Classe")
        return h

    def args_de(x):
        a = {"cours": x["cours"], "tri": x["tri"]}
        if x["classe"] is not None:
            a["classe"] = x["classe"]
        if x["rech"]:
            a["q"] = x["rech"]
        if config.juridiction() and x["ecole"]:
            a["ecole"] = x["ecole"]["id"]
        return a

    @app.route("/listes-classe")
    @H.connexion_requise()
    def listes_classe():
        x = contexte()
        titulaires = {c["id"]: (c.get("titulaire_nom") or "") for c in x["choisies"]}
        # notes vers EducMaster : export existant « modèle officiel de notes rempli » (m_donnees, inchangé), primaire,
        # école ouverte, droit « données » ou enseignant de la classe
        notes_em = []
        if ("educmaster_modele_notes_rempli" in app.view_functions and x["cours"] in NIVEAUX_PRIMAIRE
                and (H.peut("donnees") or g.user["role"] == "enseignant")
                and (not config.juridiction() or (g.get("ecole") and x["ecole"] and g.ecole["id"] == x["ecole"]["id"]))):
            notes_em = x["choisies"]
        return render_template("listes_classe.html", x=x, notes_em=notes_em, educmaster=x["cours"] in getattr(H, "EDUCMASTER_NIVEAUX", set()), TRIS=TRIS, args=args_de(x), titre_liste=titre_de(x) if x["cours"] else "",
                               titulaires=titulaires, juridiction=config.juridiction(), entetes=entetes_de(x))

    def infos_de(x):
        c = x["compte"]
        inf = [("École", (x["ecole"] or {}).get("nom", "")), ("Année scolaire", config.ANNEE_ACTIVE), ("Cours", x["cours"])]
        if x["classe"] is not None and len(x["choisies"]) == 1 and x["choisies"][0].get("titulaire_nom"):
            inf.append(("Titulaire", x["choisies"][0]["titulaire_nom"]))
        inf.append(("Effectif", f"{c['t']} (garçons : {c['g']}, filles : {c['f']})"))
        return inf

    def nom_fichier(x, ext):
        base = (x["choisies"][0]["nom"] if x["classe"] is not None and len(x["choisies"]) == 1 else x["cours"]) or "classe"
        return "liste_" + "".join(ch if ch.isalnum() else "_" for ch in _sans_accents(base)).strip("_") + "." + ext

    @app.route("/listes-classe.pdf")
    @H.connexion_requise()
    def listes_classe_pdf():
        x = contexte()
        if not x["cours"]:
            abort(404)
        c = x["compte"]
        pdf = H.pdfs.document_tableau(
            titre_de(x), entetes_de(x), lignes_de(x), sous_titre=f"Année scolaire {config.ANNEE_ACTIVE}",
            infos=infos_de(x), paysage=True, taille=14 if not x["plusieurs"] else 13, police="serif",
            total=None, notes_bas=[f"Effectif : {c['t']} élève(s) — garçons : {c['g']}, filles : {c['f']}."],
            signatures=[("Le titulaire" if len(x["choisies"]) == 1 else "Le directeur",
                         (x["choisies"][0].get("titulaire_nom") or "") if len(x["choisies"]) == 1 else "", None, False)])
        return Response(pdf, mimetype="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename={nom_fichier(x, 'pdf')}"})

    @app.route("/listes-classe.xlsx")
    @H.connexion_requise()
    def listes_classe_xlsx():
        import outils_xlsx
        x = contexte()
        if not x["cours"]:
            abort(404)
        c = x["compte"]
        haut = [titre_de(x), f"{(x['ecole'] or {}).get('nom', '')} — année scolaire {config.ANNEE_ACTIVE}",
                f"Effectif : {c['t']} (garçons : {c['g']}, filles : {c['f']})"]
        data = outils_xlsx.classeur([("Liste", entetes_de(x), lignes_de(x), {"titre_haut": haut})])
        return Response(data, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename={nom_fichier(x, 'xlsx')}"})

    @app.route("/listes-classe/educmaster.xlsx")
    @H.connexion_requise()
    def listes_classe_educmaster():
        """Format d'IMPORTATION EducMaster : modèle officiel (modeles/educmaster_modele_classe.xlsx) rempli par
        m_donnees (même nom de feuille, ordre et intitulés des colonnes, date jj/mm/aaaa, sexe M / F, NPI en texte)."""
        x = contexte()
        if not x["cours"] or not hasattr(H, "educmaster_classe_xlsx"):
            abort(404)
        if x["cours"] not in getattr(H, "EDUCMASTER_NIVEAUX", set()):
            abort(404)        # EducMaster : maternelle et primaire seulement (une feuille par cours)
        data = H.educmaster_classe_xlsx({x["cours"]: x["eleves"]})
        return Response(data, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=EducMaster_" + nom_fichier(x, "xlsx").replace("liste_", "", 1)})

    H.listes_classe_contexte = contexte
