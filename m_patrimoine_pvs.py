# -*- coding: utf-8 -*-
"""v1.27 — Patrimoine et matériel (spécification commune PVS, lot C), en complément du module Patrimoine de l'école.

Rubriques communes aux applications (même Excel) : bâtiments et salles, tables-bancs (besoin calculé), manuels scolaires
(manuels par élève), matériel didactique et sportif, besoins exprimés, dotations reçues avec procès-verbal de réception
signé (QR). « Reprendre l'inventaire » remplit les bâtiments depuis les locaux du module Patrimoine et propose les
effectifs par cours (tables-bancs, manuels) d'après les élèves inscrits.
"""
import math
from datetime import date

from flask import flash, g, redirect, request, url_for

import registres as R

COURS = ["Maternelle", "CI", "CP", "CE1", "CE2", "CM1", "CM2"]
MATIERES = ["Français", "Mathématiques", "Éducation scientifique et technologique", "Éducation sociale", "Éducation artistique",
            "Éducation physique et sportive", "Anglais", "Langue nationale", "Autre"]
NATURES = ["Salle de classe", "Bureau", "Magasin", "Bibliothèque", "Cantine / cuisine", "Latrines", "Logement", "Clôture", "Point d’eau", "Autre"]
# locaux du module Patrimoine (pat_locaux.type) -> nature commune
NATURE_DE = {"salle_classe": "Salle de classe", "salle_informatique": "Salle de classe", "salle": "Salle de classe", "bureau": "Bureau", "magasin": "Magasin", "bibliotheque": "Bibliothèque", "cuisine": "Cantine / cuisine",
             "cantine": "Cantine / cuisine", "latrines": "Latrines", "logement": "Logement", "cloture": "Clôture", "eau": "Point d’eau",
             "point_eau": "Point d’eau", "forage": "Point d’eau"}
ETAT_DE = {"bon": "Bon", "passable": "Passable", "mauvais": "Mauvais", "rehabiliter": "À réhabiliter", "inutilisable": "Inutilisable"}


def besoin_tables(eleves, bon, places=2):
    """max(0, ⌈élèves / places⌉ − tables en bon état)."""
    try:
        e, b, p = int(eleves or 0), int(bon or 0), int(places or 2) or 2
    except (TypeError, ValueError):
        return ""
    return max(0, math.ceil(e / p) - b)


def ratio_manuels(bon, eleves):
    try:
        return round(int(bon or 0) / int(eleves), 2) if int(eleves or 0) else ""
    except (TypeError, ValueError):
        return ""


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.DROITS["patrimoine_materiel"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent", "enseignant"}
    R.types_documents({"reg_patrimoine_dotations_pv": "Procès-verbal de réception de dotation"})
    G = R.Groupe(app, H, "patrimoine", "Patrimoine et matériel", "patrimoine_materiel", ico="patrimoine",
                 sous_titre="Bâtiments et salles, tables-bancs et besoins, manuels par cours et matière, matériel didactique et sportif, "
                            "besoins exprimés, dotations reçues avec PV de réception",
                 listes={"natures": NATURES, "materiaux": ["Définitif", "Semi-dur", "Provisoire / paillote"],
                         "etats_bat": ["Bon", "Passable", "Mauvais", "À réhabiliter", "Inutilisable"], "cours_tb": COURS + ["Toute l’école"],
                         "cours": COURS, "matieres": MATIERES, "cat_mat": ["Didactique", "Sportif", "Informatique", "Mobilier", "Hygiène", "Autre"],
                         "etats_mat": ["Bon", "Usagé", "À réparer", "Hors d’usage"], "origines": ["Achat", "Don", "Dotation", "Prêt"],
                         "cat_besoin": ["Construction", "Réhabilitation", "Mobilier", "Manuels", "Matériel didactique", "Matériel sportif",
                                        "Équipement", "Personnel", "Autre"], "priorites": ["Haute", "Moyenne", "Basse"],
                         "statuts_besoin": ["Exprimé", "Transmis", "Satisfait partiellement", "Satisfait"],
                         "sources": ["État", "Commune", "Partenaire / ONG", "Parents d’élèves", "Don privé"],
                         "etats_rec": ["Conforme", "Non conforme", "Incomplet"]})
    ecole = lambda: {"niveau": "ECOLE", "entite": R.entite_courante()[1]}   # noqa: E731
    struct = lambda: dict(zip(("niveau", "entite"), R.entite_courante()))   # noqa: E731

    G.registre("batiments", "Bâtiments et salles", [
        ("designation", "Désignation", "texte"), ("nature", "Nature", "choix:natures"), ("nombre", "Nombre", "entier"),
        ("materiaux", "Matériaux", "choix:materiaux"), ("anneeConstruction", "Année de construction", "entier"), ("etat", "État", "choix:etats_bat"),
        ("financement", "Financement", "texte"), ("observations", "Observations", "long")],
        unite="ouvrage", oblig="designation", ordre="nature, designation", portee="ecole", feuille="Bâtiments et salles", entite=True,
        niveaux=["ECOLE"], unique=("designation",), filtres=("nature", "etat"), totaux=("nombre",),
        defauts=lambda: dict(ecole(), nature="Salle de classe", nombre=1, materiaux="Définitif", etat="Bon"), doc="Bâtiments et salles",
        aide="« Reprendre l'inventaire » (onglet Inventaire) remplit cette liste depuis les locaux du module Patrimoine de l'école.")

    def effectif_cours(cours):
        try:
            sql = ("SELECT COUNT(*) n FROM eleves e JOIN classes c ON c.id=e.classe_id WHERE e.statut='inscrit' AND c.ecole_id=?"
                   + ("" if cours in ("", "Toute l’école") else " AND c.niveau=?"))
            return q(sql, (H.eco(),) + (() if cours in ("", "Toute l’école") else (cours,)), un=True)["n"]
        except Exception:  # noqa: BLE001
            return None

    def apres_effectif(table):
        def f(rid):
            x = q(f"SELECT * FROM {table} WHERE id=?", (rid,), un=True)
            if x and x["eleves"] in (None, ""):
                n = effectif_cours(x["cours"] or "")
                if n is not None:
                    ex(f"UPDATE {table} SET eleves=? WHERE id=?", (n, rid))
        return f

    G.registre("tables", "Tables-bancs", [
        ("cours", "Cours", "choix:cours_tb"), ("eleves", "Élèves", "entier"), ("tablesBon", "Tables-bancs en bon état", "entier"),
        ("tablesMauvais", "Tables-bancs en mauvais état", "entier"), ("places", "Places par table-banc", "entier")],
        unite="ligne", oblig="cours", ordre="id", portee="ecole", feuille="Tables-bancs", entite=True, niveaux=["ECOLE"], unique=("cours",),
        annee_lib="Année scolaire", totaux=("eleves", "tablesBon", "tablesMauvais"),
        calcul=lambda x: {"Besoin en tables-bancs": besoin_tables(x.get("eleves"), x.get("tablesBon"), x.get("places") or 2)},
        apres_enregistrer=apres_effectif("reg_patrimoine_tables"), defauts=lambda: dict(ecole(), places=2), doc="Tables-bancs et besoins",
        aide="Besoin = élèves ÷ places par table (arrondi au-dessus) − tables en bon état. Élèves laissés vides : effectif inscrit du cours.")
    G.registre("manuels", "Manuels scolaires", [
        ("cours", "Cours", "choix:cours"), ("matiere", "Matière", "choix:matieres"), ("titre", "Titre du manuel", "texte"), ("nombre", "Exemplaires", "entier"),
        ("bonEtat", "En bon état", "entier"), ("eleves", "Élèves du cours", "entier")],
        unite="manuel", oblig="cours", ordre="cours, matiere", portee="ecole", feuille="Manuels scolaires", entite=True, niveaux=["ECOLE"],
        unique=("cours", "matiere", "titre"), annee_lib="Année scolaire", filtres=("cours", "matiere"), totaux=("nombre", "bonEtat"),
        calcul=lambda x: {"Manuels par élève": ratio_manuels(x.get("bonEtat"), x.get("eleves"))},
        apres_enregistrer=apres_effectif("reg_patrimoine_manuels"), defauts=ecole, doc="Manuels scolaires",
        aide="Manuels par élève = exemplaires en bon état ÷ élèves du cours (effectif inscrit si laissé vide).")
    G.registre("materiel", "Matériel didactique et sportif", [
        ("designation", "Désignation", "texte"), ("categorie", "Catégorie", "choix:cat_mat"), ("quantite", "Quantité", "entier"),
        ("etat", "État", "choix:etats_mat"), ("origine", "Origine", "choix:origines"), ("date", "Date d’acquisition", "date"),
        ("valeur", "Valeur (FCFA)", "montant"), ("observations", "Observations", "long")],
        unite="article", oblig="designation", ordre="categorie, designation", portee="structure", feuille="Matériel didactique et sportif",
        onglet="Matériel", entite=True, unique=("designation", "categorie"), filtres=("categorie", "etat"), totaux=("quantite", "valeur"),
        defauts=lambda: dict(struct(), categorie="Didactique", etat="Bon"), doc="Matériel didactique et sportif")
    G.registre("besoins", "Besoins exprimés", [
        ("designation", "Désignation", "texte"), ("categorie", "Catégorie", "choix:cat_besoin"), ("quantite", "Quantité", "entier"),
        ("priorite", "Priorité", "choix:priorites"), ("coutEstime", "Coût estimé (FCFA)", "montant"), ("justification", "Justification", "long"),
        ("statut", "Statut", "choix:statuts_besoin")], unite="besoin", oblig="designation", ordre="priorite, designation", portee="structure",
        feuille="Besoins exprimés", entite=True, unique=("designation",), filtres=("categorie", "priorite", "statut"), totaux=("quantite", "coutEstime"),
        defauts=lambda: dict(struct(), categorie="Mobilier", priorite="Moyenne", statut="Exprimé"), doc="Besoins exprimés")

    def doc_pv(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        corps = [Paragraph(f"L'an {R.jjmmaaaa(x.get('date'))[-4:] or '……'}, le {R.jjmmaaaa(x.get('date'))}, il a été procédé à la réception de la "
                           f"dotation ci-après{' destinée à ' + R.esc(x['beneficiaire']) if x.get('beneficiaire') else ''}"
                           f"{', en provenance de : ' + R.esc(x['source']) if x.get('source') else ''}.", st["p"]), Spacer(1, 6),
                 R.tableau(["Désignation", "Quantité", "Unité", "État à la réception", "Observations"],
                           [[x.get("designation") or "", x.get("quantite") or "", x.get("unite") or "unité", x.get("etatReception") or "", x.get("observations") or ""]],
                           [2.6, 0.8, 0.8, 1.2, 2.2], R.largeur_utile(False)), Spacer(1, 8),
                 Paragraph(f"PV n° {R.esc(x.get('pvNumero') or '……')} — réceptionnaire : {R.esc(x.get('receptionnaire') or '……')}.", st["p"]),
                 Paragraph("En foi de quoi le présent procès-verbal est établi pour servir et valoir ce que de droit.", st["p"])]
        return "Procès-verbal de réception de dotation", corps, [R.signature_vide("Le réceptionnaire", x.get("receptionnaire") or ""),
                                                                 R.signature_vide("Le livreur"), R.signature_autorite("Visa de l'autorité")]

    G.registre("dotations", "Dotations reçues", [
        ("date", "Date de réception", "date"), ("designation", "Désignation", "texte"), ("quantite", "Quantité", "entier"), ("unite", "Unité", "texte"),
        ("source", "Source", "choix:sources"), ("beneficiaire", "École bénéficiaire", "ecole"), ("pvNumero", "N° du PV de réception", "texte"),
        ("receptionnaire", "Réceptionnaire", "texte"), ("etatReception", "État à la réception", "choix:etats_rec"), ("observations", "Observations", "long")],
        unite="dotation", oblig="designation", ordre="date DESC", portee="structure", feuille="Dotations reçues", entite=True,
        unique=("date", "designation"), filtres=("source", "etatReception"), totaux=("quantite",),
        fiches={"pv": ("PV de réception", "attestation", doc_pv)},
        defauts=lambda: dict(struct(), date=date.today().isoformat(), unite="unité", source="État", etatReception="Conforme"),
        doc="Dotations reçues")
    G.page("patrimoine_pvs_reprendre", "Inventaire", apres=True)

    @app.route("/patrimoine-materiel/reprendre", methods=["GET", "POST"])
    @H.connexion_requise("patrimoine_materiel")
    def patrimoine_pvs_reprendre():
        if request.method == "GET":
            from flask import render_template
            return render_template("patrimoine_pvs.html", G=G, ep_actif="patrimoine_pvs_reprendre",
                                   n_locaux=_n("SELECT COUNT(*) n FROM pat_locaux WHERE ecole_id=?"), peut_ecrire=G.peut_ecrire())
        if not G.peut_ecrire():
            flash("Écriture réservée.", "warning")
            return redirect(url_for("patrimoine_pvs_reprendre"))
        annee, p, ent = R.annee_active(), R.cle_portee("ecole"), R.entite_courante()[1]
        n = 0
        try:
            locaux = q("SELECT * FROM pat_locaux WHERE ecole_id=? ORDER BY type, designation", (H.eco(),))
        except Exception:  # noqa: BLE001
            locaux = []
        for l in locaux:
            if q("SELECT 1 FROM reg_patrimoine_batiments WHERE portee=? AND annee=? AND designation=?", (p, annee, l["designation"]), un=True):
                continue
            mat = (l["murs"] or "").lower()   # dur | semi_dur | banco | planche | paillote | sans_mur
            ex("INSERT INTO reg_patrimoine_batiments (portee, annee, niveau, entite, designation, nature, nombre, materiaux, anneeConstruction, etat, "
               "financement, observations, cree_le, cree_par, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (p, annee, "ECOLE", ent, l["designation"], NATURE_DE.get(l["type"], "Autre"), 1,
                "Semi-dur" if mat == "semi_dur" else ("Définitif" if mat in ("dur", "") else "Provisoire / paillote"),
                l["annee_service"], ETAT_DE.get((l["etat"] or "").lower(), l["etat"] or "Bon"), l["financement"] or "", l["observations"] or "",
                H.maintenant(), g.user["id"], H.maintenant()))
            n += 1
        m = 0
        for cours in COURS:
            eff = effectif_cours(cours)
            if not eff:
                continue
            if not q("SELECT 1 FROM reg_patrimoine_tables WHERE portee=? AND annee=? AND cours=?", (p, annee, cours), un=True):
                try:
                    bon = q("SELECT SUM(m.quantite) s FROM pat_mobilier m LEFT JOIN classes c ON c.id=m.classe_id WHERE m.ecole_id=? AND "
                            "m.categorie IN ('tb1','tb2','tb3','adapte') AND COALESCE(m.etat,'bon')='bon' AND c.niveau=?", (H.eco(), cours), un=True)["s"]
                except Exception:  # noqa: BLE001
                    bon = None
                ex("INSERT INTO reg_patrimoine_tables (portee, annee, niveau, entite, cours, eleves, tablesBon, places, cree_le, cree_par, maj) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (p, annee, "ECOLE", ent, cours, eff, bon, 2, H.maintenant(), g.user["id"], H.maintenant()))
                m += 1
        flash(f"Inventaire repris : {n} ouvrage(s), {m} ligne(s) de tables-bancs.", "success")
        return redirect(url_for("reg_page", gcle="patrimoine", rcle="batiments"))

    def _n(sql):
        try:
            return q(sql, (H.eco(),), un=True)["n"]
        except Exception:  # noqa: BLE001
            return 0
