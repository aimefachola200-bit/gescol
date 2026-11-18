# -*- coding: utf-8 -*-
"""v2.6 — Espace de l'enseignant du secondaire (général et technique) : « Mes cours » par classe et par matière,
fiches de préparation, devoirs et fiches de travaux pratiques MODIFIABLES dans l'application, copiés ou non de la bibliothèque,
avec logo et en-tête de l'établissement, signature de l'enseignant, griffe/cachet du professeur (devoirs) ; sur les fiches : nom du
professeur en filigrane, pas de cachet. Les exports PDF/Word passent par la barre d'export (m_export)."""
import json
from datetime import datetime

from flask import abort, flash, g, redirect, render_template, request, url_for

import config
import ens_mode as EM
import epreuves_apc as AP
import agri_sec as AGRI
import fiches_sec as FS

TYPES_DEVOIR = ["Devoir surveillé", "Devoir à la maison", "Interrogation écrite", "Composition", "Évaluation diagnostique", "Épreuve pratique"]
# (clé, libellé, 'l' ligne | 'z' zone de texte)
CHAMPS = {
    "fiche": ("Fiche de préparation", [
        ("matiere", "Discipline", "l"), ("niveau", "Classe / niveau", "l"), ("duree", "Durée", "l"), ("titre", "Titre de la leçon", "l"),
        ("competence", "Compétence disciplinaire", "z"), ("situation", "Situation d'apprentissage", "z"), ("objectifs", "Objectifs d'apprentissage", "z"),
        ("mise_en_situation", "1. Mise en situation", "z"), ("recherche", "2. Recherche et exploration", "z"),
        ("trace", "3. Mise en commun et structuration (trace écrite)", "z"), ("application", "4. Application et évaluation", "z"),
        ("prolongement", "5. Prolongement", "z"), ("observations", "Observations du professeur", "z")]),
    "devoir": ("Devoir / épreuve", [
        ("type", "Type", "t"), ("matiere", "Discipline", "l"), ("niveau", "Classe / niveau", "l"), ("duree", "Durée", "l"), ("total", "Barème total", "l"),
        ("titre", "Intitulé", "l"), ("competence", "Compétence évaluée", "z"), ("situation", "Situation", "z"), ("tache", "Tâche", "z"),
        ("consignes", "Consignes (une par ligne : texte | points)", "z"), ("corrige", "Corrigé et barème détaillé", "z"),
        ("visa", "Visa de l'administration (signature + griffe)", "v")]),
    "tp": ("Fiche de travaux pratiques (enseignement technique)", [
        ("filiere", "Filière / spécialité", "l"), ("matiere", "Discipline", "l"), ("niveau", "Classe / niveau", "l"), ("duree", "Durée", "l"),
        ("titre", "Titre du TP", "l"), ("objectif", "Objectif(s)", "z"), ("prerequis", "Prérequis", "z"), ("materiel", "Matériel, outillage et matières d'œuvre", "z"),
        ("securite", "Consignes de sécurité", "z"), ("deroulement", "Déroulement (étapes)", "z"), ("evaluation", "Évaluation (critères)", "z"),
        ("observations", "Observations", "z")]),
}


_NIV = {"6ème": "6e", "5ème": "5e", "4ème": "4e", "3ème": "3e"}
_ALIAS = {"svt": "sciences de la vie et de la terre", "pct": "physique, chimie et technologie", "eps": "éducation physique et sportive",
          "hg": "histoire et géographie", "histoire-géographie": "histoire et géographie"}


# disciplines de l'enseignement technique et professionnel (ajoutées une fois aux établissements secondaires, modifiables ensuite)
MATIERES_TECHNIQUES = [
    ("TECH_ATELIER", "Atelier / travaux pratiques"), ("TECH_DESSIN", "Dessin technique"), ("TECH_TECHNO", "Technologie et technique professionnelle"),
    ("TECH_MECA", "Mécanique générale"), ("TECH_ELEC", "Électricité – Électronique"), ("TECH_BAT", "Bâtiment et travaux publics"),
    ("TECH_MENUI", "Menuiserie – Ébénisterie"), ("TECH_COMPTA", "Comptabilité et gestion"), ("TECH_SECR", "Techniques administratives et secrétariat"),
    ("TECH_INFO", "Informatique"), ("TECH_AGRI", "Agriculture – Élevage"), ("TECH_COUT", "Couture – Habillement"),
    ("TECH_HOTEL", "Hôtellerie – Restauration"), ("TECH_EFS", "Économie familiale et sociale")] + AGRI.MATIERES_AGRI


def niv_biblio(niveau):
    """Les niveaux de la bibliothèque s'écrivent 6e, 5e… ; ceux des classes 6ème, 5ème…"""
    return _NIV.get(niveau, niveau)


def meme_matiere(a, b):
    def n(t):
        t = (t or "").split(" – ")[0].strip().lower()
        return _ALIAS.get(t, t)
    return bool(a) and n(a) == n(b)


import m_signatures as MS

AGRI.integrer()


def enregistrer(app, H):
    from db import ex, q

    fait = {"matieres": False}

    @app.before_request
    def assurer_matieres_techniques():
        if fait["matieres"] or not (config.secondaire() or config.enseignant()) or request.endpoint in (None, "static"):
            return
        try:
            for ordre, (code, nom) in enumerate(MATIERES_TECHNIQUES, 100):
                if not q("SELECT 1 FROM matieres WHERE code=?", (code,)):
                    ex("INSERT INTO matieres (code, nom, cycle, coefficient, mode_calcul, ordre) VALUES (?,?,?,?,?,?)",
                       (code, nom, "secondaire", 2, "standard", ordre))
            fait["matieres"] = True
        except Exception:  # noqa: BLE001 — base pas encore prête : on réessaiera à la requête suivante
            pass

    def garde():
        if not EM.prof_actif():
            abort(404)

    def moi():
        return g.user["id"]

    def est_ens():
        return g.user["role"] == "enseignant"

    def mes_cours():
        """[{cid, mid, classe, niveau, matiere}] : une carte par classe et par matière enseignée (matières techniques comprises)."""
        res = []
        if est_ens():
            mats = q("SELECT * FROM matieres WHERE cycle='secondaire' AND actif=1 ORDER BY ordre")
            for a in q("SELECT a.classe_id, a.matiere_id, c.nom classe, c.niveau FROM affectations a JOIN classes c ON c.id=a.classe_id "
                       "WHERE a.user_id=? ORDER BY c.nom", (moi(),)):
                if config.enseignant() and not a["matiere_id"]:
                    continue   # application personnelle : le professeur désigne lui-même ses matières
                if a["matiere_id"]:
                    m = q("SELECT nom FROM matieres WHERE id=?", (a["matiere_id"],), un=True)
                    res.append(dict(cid=a["classe_id"], mid=a["matiere_id"], classe=a["classe"], niveau=a["niveau"], matiere=m["nom"] if m else ""))
                else:
                    res += [dict(cid=a["classe_id"], mid=m["id"], classe=a["classe"], niveau=a["niveau"], matiere=m["nom"]) for m in mats]
        else:
            for c in q("SELECT id, nom, niveau FROM classes ORDER BY nom"):
                if c["id"] in {x["id"] for x in H.classes_autorisees()}:
                    res.append(dict(cid=c["id"], mid=0, classe=c["nom"], niveau=c["niveau"], matiere="Toutes les matières"))
        return res

    def mon_doc(did):
        d = q("SELECT * FROM docs_sec WHERE id=?", (did,), un=True)
        if not d or (d["user_id"] != moi() and g.user["role"] not in ("admin", "directeur", "proviseur", "censeur", "surveillant general")):
            abort(404)
        return d

    def valeurs(d):
        try:
            return json.loads(d["donnees"] or "{}")
        except ValueError:
            return {}

    def lire_form(kind):
        return {c: (request.form.get(c) or "").strip()[:6000] for c, _, _ in CHAMPS[kind][1]}

    def nom_matiere(mid):
        m = q("SELECT nom FROM matieres WHERE id=?", (mid,), un=True) if mid else None
        return m["nom"] if m else ""

    def lier(d_kind, cid, mid, v):
        return v | {"matiere": v.get("matiere") or nom_matiere(mid)}

    # ---------------------------------------------------------------- accueil
    @app.route("/ens-sec")
    @H.connexion_requise("epreuves")
    def ens_sec():
        garde()
        cours = mes_cours()
        nb = {r["kind"]: r["n"] for r in q("SELECT kind, COUNT(*) n FROM docs_sec WHERE user_id=? GROUP BY kind", (moi(),))}
        return render_template("ens_sec_accueil.html", cours=cours, nbdocs=nb, CH=CHAMPS, uid=moi())

    @app.route("/ens-sec/cours/<int:cid>/<int:mid>")
    @H.connexion_requise("epreuves")
    def ens_sec_cours(cid, mid):
        garde()
        H.verifier_classe(cid)
        cl = H.classe_ou_404(cid)
        docs = q("SELECT * FROM docs_sec WHERE user_id=? AND classe_id=? AND matiere_id IS ? ORDER BY maj_le DESC", (moi(), cid, mid or None))
        mat = nom_matiere(mid)
        modeles = [(i, f) for i, f in enumerate(FS.FICHES) if meme_matiere(mat, f["matiere"]) and f["niveau"] == niv_biblio(cl["niveau"])][:12]
        apc = [(i, e) for i, e in enumerate(AP.EPREUVES) if meme_matiere(mat, e["matiere"]) and e["niveau"] == niv_biblio(cl["niveau"])][:12]
        tps = [(i, t) for i, t in enumerate(AGRI.TP_LISTE) if meme_matiere(mat, t["matiere"]) and t["niveau"] == niv_biblio(cl["niveau"])]
        eff = q("SELECT COUNT(*) n FROM eleves WHERE classe_id=? AND statut='inscrit'", (cid,), un=True)["n"]
        from m_ressources_sec import _etendre
        import ressources_secondaire as RS
        themes = [(i, e) for i, e in enumerate(RS.EXPOSES) if meme_matiere(mat, e[0]) and niv_biblio(cl["niveau"]) in _etendre(e[1])][:15]
        exposes = q("SELECT x.*, (SELECT COUNT(*) FROM exposes_groupes WHERE expose_id=x.id) ng FROM exposes_sec x WHERE x.classe_id=? AND x.matiere_id IS ? AND x.user_id=? ORDER BY x.id DESC",
                    (cid, mid or None, moi()))
        return render_template("ens_sec_cours.html", cl=cl, mid=mid, mat=mat, docs=docs, modeles=modeles, apc=apc, tps=tps, eff=eff, CH=CHAMPS, themes=themes, exposes=exposes)

    # ---------------------------------------------------------------- création / modification
    def formulaire(kind, d=None, cid=None, mid=None, pre=None):
        if kind not in CHAMPS:
            abort(404)
        v = valeurs(d) if d else dict(pre or {})
        if request.method == "POST":
            v = lire_form(kind)
            titre = v.get("titre") or "Sans titre"
            if d:
                ex("UPDATE docs_sec SET titre=?, donnees=?, maj_le=? WHERE id=?",
                   (titre, json.dumps(v, ensure_ascii=False), datetime.now().isoformat(" ", "seconds"), d["id"]))
                did = d["id"]
            else:
                did = ex("INSERT INTO docs_sec (user_id, kind, classe_id, matiere_id, titre, donnees, source) VALUES (?,?,?,?,?,?,?)",
                         (moi(), kind, cid or None, mid or None, titre, json.dumps(v, ensure_ascii=False), request.args.get("source")))
            H.journal("ens_sec_" + kind, titre[:80])
            flash("Enregistré.", "success")
            return redirect(url_for("ens_sec_voir", kind=kind, did=did))
        return render_template("ens_sec_form.html", FONCTIONS=MS.FONCTIONS, kind=kind, nom=CHAMPS[kind][0], champs=CHAMPS[kind][1], v=v, d=d, cid=cid, mid=mid, TYPES=TYPES_DEVOIR)

    @app.route("/ens-sec/nouveau/<kind>", methods=["GET", "POST"])
    @H.connexion_requise("epreuves")
    def ens_sec_nouveau(kind):
        garde()
        cid, mid = request.args.get("cid", type=int), request.args.get("mid", type=int)
        pre = {}
        if cid:
            H.verifier_classe(cid)
            cl = H.classe_ou_404(cid)
            pre = {"niveau": cl["niveau"], "matiere": nom_matiere(mid)}
        return formulaire(kind, None, cid, mid, pre)

    @app.route("/ens-sec/<kind>/<int:did>/modifier", methods=["GET", "POST"])
    @H.connexion_requise("epreuves")
    def ens_sec_modifier(kind, did):
        garde()
        d = mon_doc(did)
        if d["kind"] != kind:
            abort(404)
        return formulaire(kind, d, d["classe_id"], d["matiere_id"])

    @app.route("/ens-sec/<kind>/<int:did>")
    @H.connexion_requise("epreuves")
    def ens_sec_voir(kind, did):
        garde()
        d = mon_doc(did)
        if d["kind"] != kind:
            abort(404)
        v = valeurs(d)
        cl = H.classe_ou_404(d["classe_id"]) if d["classe_id"] else None
        prof = q("SELECT id, nom FROM utilisateurs WHERE id=?", (d["user_id"],), un=True)
        sans_sig = request.args.get("sans_sig") == "1"
        sig = H.signature(f"enseignant:{d['user_id']}") if not sans_sig else None
        griffe = None
        if kind == "devoir" and prof and not sans_sig:
            griffe = {"titre": "Le Professeur", "nom": prof["nom"], "ligne3": v.get("matiere", "")}
        visa = None
        if kind == "devoir" and not sans_sig and v.get("visa") in MS.TITRES:
            gv = H.griffe_fonction(v["visa"])
            visa = {"cle": f"ecole:{H.eco()}:{v['visa']}", "griffe": gv, "titre": MS.TITRES[v["visa"]],
                    "signe": bool(H.signature(f"ecole:{H.eco()}:{v['visa']}"))}
        consignes = []
        if kind == "devoir":
            for ligne in (v.get("consignes") or "").splitlines():
                if ligne.strip():
                    t, _, p = ligne.partition("|")
                    consignes.append((t.strip(), p.strip()))
        return render_template("ens_sec_doc.html", d=d, kind=kind, nom=CHAMPS[kind][0], champs=CHAMPS[kind][1], v=v, cl=cl, prof=prof,
                               ident=H.identification(), sig=bool(sig), griffe=griffe, visa=visa, sans_sig=sans_sig,
                               avec_sig=not sans_sig and (kind == "devoir" or bool(sig)), consignes=consignes,
                               filigrane=(prof["nom"] if kind != "devoir" and prof else ""))

    @app.route("/ens-sec/<kind>/<int:did>/dupliquer", methods=["POST"])
    @H.connexion_requise("epreuves")
    def ens_sec_dupliquer(kind, did):
        garde()
        d = mon_doc(did)
        nid = ex("INSERT INTO docs_sec (user_id, kind, classe_id, matiere_id, titre, donnees, source) VALUES (?,?,?,?,?,?,?)",
                 (moi(), d["kind"], d["classe_id"], d["matiere_id"], (d["titre"] + " (copie)")[:200], d["donnees"], d["source"]))
        flash("Copie créée : vous pouvez la modifier.", "success")
        return redirect(url_for("ens_sec_modifier", kind=d["kind"], did=nid))

    @app.route("/ens-sec/<kind>/<int:did>/supprimer", methods=["POST"])
    @H.connexion_requise("epreuves")
    def ens_sec_supprimer(kind, did):
        garde()
        d = mon_doc(did)
        ex("DELETE FROM docs_sec WHERE id=?", (did,))
        H.journal("ens_sec_suppr", d["titre"][:80])
        flash("Document supprimé.", "success")
        return redirect(url_for("ens_sec_cours", cid=d["classe_id"], mid=d["matiere_id"] or 0) if d["classe_id"] else url_for("ens_sec"))

    # ---------------------------------------------------------------- copier un modèle de la bibliothèque pour le modifier
    @app.route("/ens-sec/copier/<src>/<int:i>", methods=["POST"])
    @H.connexion_requise("epreuves")
    def ens_sec_copier(src, i):
        garde()
        cid, mid = request.form.get("cid", type=int), request.form.get("mid", type=int)
        if cid:
            H.verifier_classe(cid)
        if src == "fiche" and 0 <= i < len(FS.FICHES):
            kind, v = "fiche", {k: FS.FICHES[i].get(k, "") for k, _, _ in CHAMPS["fiche"][1]}
        elif src == "apc" and 0 <= i < len(AP.EPREUVES):
            e = AP.EPREUVES[i]
            items = e.get("items") or []
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except ValueError:
                    items = []
            kind, v = "devoir", {"type": e.get("type", "Devoir surveillé"), "matiere": e["matiere"], "niveau": e["niveau"], "duree": e.get("duree", ""),
                                 "total": str(e.get("total", "20")), "titre": f"{e['matiere']} {e['niveau']}", "competence": e.get("competence", ""),
                                 "situation": e.get("situation", ""), "tache": e.get("tache", ""),
                                 "consignes": "\n".join(f"{x.get('consigne', '')} | {x.get('points', '')}" for x in items if isinstance(x, dict)),
                                 "corrige": "\n".join(f"{n}. {x.get('correction') or x.get('corrige') or ''}" for n, x in enumerate(items, 1) if isinstance(x, dict) and (x.get("correction") or x.get("corrige")))}
        elif src == "tp" and 0 <= i < len(AGRI.TP_LISTE):
            kind, v = "tp", {k: AGRI.TP_LISTE[i].get(k, "") for k, _, _ in CHAMPS["tp"][1]}
        elif src == "epreuve":
            from m_ressources_sec import banque
            e = next((x for x in banque() if x["id"] == i), None)
            if not e:
                abort(404)
            kind, v = "devoir", {"type": "Devoir surveillé", "matiere": e["matiere"], "niveau": e["niveau"], "titre": f"{e['matiere']} {e['niveau']}",
                                 "tache": e["texte"][:6000]}
        else:
            abort(404)
        nid = ex("INSERT INTO docs_sec (user_id, kind, classe_id, matiere_id, titre, donnees, source) VALUES (?,?,?,?,?,?,?)",
                 (moi(), kind, cid or None, mid or None, v.get("titre") or "Sans titre", json.dumps(v, ensure_ascii=False), f"{src}:{i}"))
        H.journal("ens_sec_copie", f"{src}:{i}")
        flash("Modèle copié dans vos documents : modifiez-le ci-dessous.", "success")
        return redirect(url_for("ens_sec_modifier", kind=kind, did=nid))

    app.jinja_env.globals["ens_sec_actif"] = lambda: EM.prof_actif()
