# -*- coding: utf-8 -*-
"""v1.26 — Santé, cantine et inclusion (spécification commune PVS, lot B ; registres tenus par école).

* Visites médicales : IMC calculé, aptitude sportive reportée sur la licence du sport scolaire (même école, saison,
  nom et prénoms sans accents ni casse), certificat d'aptitude et fiche de visite signés (QR) ;
* infirmerie et incidents ; cantine : journal des repas (servis G / F) et stocks (soldes par denrée, alerte si épuisé) —
  la caisse de la cantine (paiements) et le suivi détaillé des vivres restent dans le module Cantine ;
* élèves à besoins spécifiques (fiche de suivi), scolarisation des filles (indice de parité), absences et décrochage :
  absences des 30 derniers jours tirées de l'appel (demi-journées), seuil d'alerte modifiable, « Créer la fiche ».

Adresses propres : /sante-scolaire/… (l'adresse /sante est le contrôle de santé du serveur).
"""
from datetime import date, timedelta

from flask import flash, g, redirect, render_template, request, url_for

import registres as R

COURS = ["Maternelle", "CI", "CP", "CE1", "CE2", "CM1", "CM2"]
APTITUDES = ["Apte", "Apte avec réserve", "Inapte"]
SEUIL = 6


def imc(poids, taille_cm):
    try:
        p, t = float(poids), float(taille_cm) / 100
        return round(p / (t * t), 1) if p > 0 and t > 0 else ""
    except (TypeError, ValueError):
        return ""


def soldes(lignes):
    """Σ entrées − Σ sorties par (denrée, unité)."""
    out = {}
    for x in lignes:
        k = (x.get("denree") or "", x.get("unite") or "kg")
        qte = float(x.get("quantite") or 0)
        out[k] = out.get(k, 0) + (qte if (x.get("mouvement") or "") == "Entrée" else -qte)
    return {k: round(v, 3) for k, v in out.items()}


def enregistrer(app, H):
    q, ex = H.q, H.ex
    H.DROITS["sante_scolaire"] = {"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp", "agent", "enseignant"}
    R.types_documents({"reg_sante_visites_aptitude": "Certificat d'aptitude à la pratique sportive scolaire",
                       "reg_sante_visites_fiche": "Fiche de visite médicale scolaire",
                       "reg_sante_besoins_inclusion": "Fiche de suivi d'un élève à besoins spécifiques",
                       "reg_sante_decrochage_signalement": "Fiche de signalement d'absentéisme / décrochage",
                       "reg_sante_stocks": "État du stock de la cantine scolaire", "reg_sante_cantine": "Journal de la cantine scolaire"})
    LISTES = {"cours": COURS, "sexe": ["M", "F"], "aptitudes": APTITUDES, "etat3": ["Normale", "À surveiller", "Déficiente"],
              "dentition": ["Bonne", "Caries", "À soigner"], "vaccination": ["À jour", "Incomplète", "Inconnue"],
              "nature_inf": ["Maladie", "Blessure", "Accident", "Malaise", "Morsure / piqûre", "Conflit / violence", "Autre"],
              "orient_inf": ["Retour en classe", "Renvoyé(e) à la maison", "Centre de santé", "Hôpital"],
              "repas": ["Petit-déjeuner", "Déjeuner", "Collation"],
              "denrees": ["Riz", "Maïs", "Haricot / niébé", "Huile", "Sel", "Sucre", "Poisson / sardine", "Farine enrichie", "Gari", "Légumes", "Autre"],
              "mouvements": ["Entrée", "Sortie"], "unites": ["kg", "litre", "sac de 50 kg", "sac de 25 kg", "boîte", "carton"],
              "besoins": ["Handicap moteur", "Handicap visuel", "Handicap auditif", "Déficience intellectuelle", "Troubles des apprentissages",
                          "Maladie chronique", "Albinisme", "Orphelin / vulnérable", "Autre"],
              "statut_besoin": ["En cours", "Pris en charge", "Orienté", "Clos"],
              "motifs": ["Maladie", "Travaux domestiques", "Travail des enfants", "Mariage / grossesse précoce", "Migration / déménagement",
                         "Éloignement de l’école", "Difficultés scolaires", "Manque de moyens", "Inconnu", "Autre"],
              "statut_decr": ["Signalé", "En suivi", "Réintégré", "Abandon définitif"]}
    G = R.Groupe(app, H, "sante", "Santé, cantine et inclusion", "sante_scolaire", ico="sante",
                 ecriture_roles={"admin", "fondateur", "directeur", "secretaire", "responsable", "chef_service", "cp"},
                 sous_titre="Visites médicales et aptitude sportive, infirmerie et incidents, cantine (repas, stocks), élèves à besoins "
                            "spécifiques, scolarisation des filles, absences et décrochage",
                 listes=LISTES)

    def ent_ecole():
        return {"niveau": "ECOLE", "entite": R.entite_courante()[1]}

    def sig_ecole(examinateur_titre, nom=""):
        return [R.signature_vide(examinateur_titre, nom), R.signature_autorite("Visa du Directeur / de la Directrice")]

    # ---- visites médicales
    def apres_visite(rid):
        x = q("SELECT * FROM reg_sante_visites WHERE id=?", (rid,), un=True)
        f = getattr(H, "sport_aptitude", None)
        if x and callable(f) and x["aptitude"]:
            try:
                f(x["nom"], x["prenoms"], x["aptitude"], x["dateVisite"], x["examinateur"] or "", ecole=x["entite"] or "", saison=x["annee"])
            except TypeError:
                f(x["nom"], x["prenoms"], x["aptitude"], x["dateVisite"], x["examinateur"] or "")

    def doc_aptitude(x):
        from reportlab.platypus import Paragraph, Spacer
        st = R.styles()
        ap = x.get("aptitude") or ""
        txt = (f"Je soussigné(e), {R.esc(x.get('examinateur') or '……………………')}, agent de santé, certifie avoir examiné le "
               f"{R.jjmmaaaa(x.get('dateVisite'))} l'élève <b>{R.esc((x.get('nom') or '') + ' ' + (x.get('prenoms') or ''))}</b>"
               f"{', né(e) le ' + R.jjmmaaaa(x.get('dateNaissance')) if x.get('dateNaissance') else ''}"
               f"{', du cours ' + R.esc(x['cours']) if x.get('cours') else ''}, de l'école {R.esc(x.get('entite') or '')}, et l'avoir "
               f"trouvé(e) <b>{R.esc(ap.lower() if ap else '………')}</b> à la pratique des activités physiques et sportives scolaires "
               f"pour la saison {R.esc(x.get('annee') or '')}.")
        corps = [Paragraph(txt, st["p"])]
        if (x.get("reserve") or "").strip():
            corps += [Spacer(1, 4), Paragraph("<b>Réserves / contre-indications :</b> " + R.esc(x["reserve"]), st["p"])]
        return "Certificat d'aptitude à la pratique sportive scolaire", corps, sig_ecole("L'examinateur (agent de santé)", x.get("examinateur") or "")

    def doc_fiche_sante(x):
        r = G.registres["visites"]
        titre, corps, _s = R.fiche_simple(G, r, x, "Fiche de visite médicale scolaire", exclure=("niveau",))
        corps.insert(0, R.tableau(["IMC"], [[imc(x.get("poids"), x.get("taille"))]], [1], R.largeur_utile(False) / 3))
        return titre, corps, sig_ecole("L'examinateur (agent de santé)", x.get("examinateur") or "")

    G.registre("visites", "Visites médicales", [
        ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"), ("sexe", "Sexe", "choix:sexe"), ("dateNaissance", "Date de naissance", "date"),
        ("cours", "Cours", "choix:cours"), ("dateVisite", "Date de la visite", "date"), ("examinateur", "Examinateur (agent de santé)", "texte"),
        ("poids", "Poids (kg)", "decimal"), ("taille", "Taille (cm)", "decimal"), ("vue", "Vue", "choix:etat3"), ("audition", "Audition", "choix:etat3"),
        ("dentition", "Dentition", "choix:dentition"), ("vaccination", "Vaccination", "choix:vaccination"), ("aptitude", "Aptitude sportive", "choix:aptitudes"),
        ("reserve", "Réserves / contre-indications", "texte"), ("orientation", "Orientation / soins conseillés", "long")],
        unite="visite", oblig="nom", ordre="dateVisite DESC, nom", portee="ecole", feuille="Visites médicales", entite=True, niveaux=["ECOLE"],
        unique=("nom", "prenoms", "dateVisite"), calcul=lambda x: {"IMC": imc(x.get("poids"), x.get("taille"))}, apres_enregistrer=apres_visite,
        filtres=("cours", "aptitude"), colonnes=("nom", "prenoms", "sexe", "cours", "dateVisite", "examinateur", "poids", "taille", "vue", "audition", "aptitude"),
        fiches={"aptitude": ("Certificat d'aptitude sportive", "valider-cercle", doc_aptitude), "fiche": ("Fiche de visite médicale", "sante", doc_fiche_sante)},
        defauts=lambda: dict(ent_ecole(), dateVisite=date.today().isoformat()), doc="Registre des visites médicales scolaires",
        aide="L'aptitude sportive est reportée sur la licence de l'élève (Sport scolaire › Licences) : même nom et prénoms, même saison.")
    G.registre("infirmerie", "Infirmerie et incidents", [
        ("date", "Date", "date"), ("heure", "Heure", "heure"), ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"), ("sexe", "Sexe", "choix:sexe"),
        ("cours", "Cours", "choix:cours"), ("nature", "Nature", "choix:nature_inf"), ("circonstances", "Circonstances", "long"),
        ("soins", "Premiers soins", "long"), ("orientation", "Orientation", "choix:orient_inf"), ("parentInforme", "Parent informé", "oui_non"),
        ("suivi", "Suivi", "long")], unite="passage", oblig="nom", ordre="date DESC, heure DESC", portee="ecole", feuille="Infirmerie et incidents",
        entite=True, niveaux=["ECOLE"], unique=("date", "heure", "nom", "prenoms"), filtres=("nature", "orientation"),
        defauts=lambda: dict(ent_ecole(), date=date.today().isoformat()), doc="Registre de l'infirmerie et des incidents")
    G.registre("cantine", "Cantine : journal des repas", [
        ("date", "Date", "date"), ("repas", "Repas", "choix:repas"), ("prevusG", "Bénéficiaires prévus G", "entier"), ("prevusF", "Bénéficiaires prévus F", "entier"),
        ("servisG", "Repas servis G", "entier"), ("servisF", "Repas servis F", "entier"), ("menu", "Menu", "texte"),
        ("cuisinieres", "Cuisinières / cuisiniers", "entier"), ("observations", "Observations", "long")],
        unite="journée", oblig="date", ordre="date DESC", portee="ecole", feuille="Cantine : journal des repas", onglet="Cantine : repas",
        entite=True, niveaux=["ECOLE"], unique=("date", "repas"), totaux=("prevusG", "prevusF", "servisG", "servisF"),
        calcul=lambda x: {"Total servis": (x.get("servisG") or 0) + (x.get("servisF") or 0)},
        signataires=lambda _l: sig_ecole("Le / la gestionnaire de la cantine"),
        defauts=lambda: dict(ent_ecole(), date=date.today().isoformat(), repas="Déjeuner"), doc="Journal de la cantine scolaire",
        aide="Les paiements de la cantine et le suivi détaillé des vivres restent dans le module Cantine.")
    G.registre("stocks", "Cantine : stocks", [
        ("date", "Date", "date"), ("denree", "Denrée", "choix:denrees"), ("mouvement", "Mouvement", "choix:mouvements"), ("quantite", "Quantité", "decimal"),
        ("unite", "Unité", "choix:unites"), ("provenance", "Provenance / destination", "texte"), ("piece", "N° de bordereau / pièce", "texte"),
        ("observations", "Observations", "long")], unite="mouvement", oblig="denree", ordre="date DESC, id DESC", portee="ecole",
        feuille="Cantine : stocks", onglet="Cantine : stocks", entite=True, niveaux=["ECOLE"], unique=("date", "denree", "mouvement", "piece"),
        filtres=("denree", "mouvement"), signataires=lambda _l: sig_ecole("Le / la gestionnaire de la cantine"),
        defauts=lambda: dict(ent_ecole(), date=date.today().isoformat(), unite="kg", mouvement="Entrée"), doc="État du stock de la cantine scolaire",
        aide="Solde par denrée = entrées − sorties (même unité) : voir l'onglet « Soldes des stocks » ; alerte si le solde est nul ou négatif.")

    def doc_inclusion(x):
        r = G.registres["besoins"]
        titre, corps, _s = R.fiche_simple(G, r, x, "Fiche de suivi d'un élève à besoins spécifiques", exclure=("niveau",))
        return titre, corps, sig_ecole("L'enseignant(e) titulaire")

    G.registre("besoins", "Élèves à besoins spécifiques", [
        ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"), ("sexe", "Sexe", "choix:sexe"), ("cours", "Cours", "choix:cours"),
        ("type", "Type de besoin", "choix:besoins"), ("description", "Description", "long"), ("amenagements", "Aménagements pédagogiques", "long"),
        ("partenaire", "Partenaire / prise en charge", "texte"), ("statut", "Suivi", "choix:statut_besoin")],
        unite="élève", oblig="nom", ordre="cours, nom", portee="ecole", feuille="Élèves à besoins spécifiques", onglet="Besoins spécifiques",
        entite=True, niveaux=["ECOLE"], unique=("nom", "prenoms", "type"), filtres=("type", "statut"),
        fiches={"inclusion": ("Fiche de suivi", "accessibilite", doc_inclusion)},
        defauts=lambda: dict(ent_ecole(), statut="En cours"), doc="Élèves à besoins spécifiques")

    def indice(x):
        try:
            return {"Indice de parité (F/G)": round((x.get("inscrites") or 0) / x["garcons"], 2) if x.get("garcons") else ""}
        except (TypeError, ZeroDivisionError):
            return {"Indice de parité (F/G)": ""}

    G.registre("filles", "Scolarisation des filles", [
        ("inscrites", "Filles inscrites", "entier"), ("garcons", "Garçons inscrits", "entier"), ("nouvellesCI", "Nouvelles inscrites au CI", "entier"),
        ("abandons", "Abandons de filles", "entier"), ("fillesCM2", "Filles au CM2", "entier"), ("admisesCEP", "Filles admises au CEP", "entier"),
        ("mentorat", "Mentorat / marrainage", "oui_non"), ("club", "Club des filles", "oui_non"), ("actions", "Actions menées", "long"),
        ("obstacles", "Obstacles relevés", "long")], unite="bilan", oblig="inscrites", ordre="id DESC", portee="ecole", feuille="Scolarisation des filles",
        entite=True, niveaux=["ECOLE"], calcul=indice, defauts=lambda: dict(ent_ecole(), **effectifs_gf()), doc="Scolarisation des filles",
        aide="Effectifs proposés d'après les élèves inscrits de l'école.")

    def doc_decrochage(x):
        r = G.registres["decrochage"]
        titre, corps, _s = R.fiche_simple(G, r, x, "Fiche de signalement d'absentéisme / décrochage", exclure=("niveau",))
        return titre, corps, sig_ecole("L'enseignant(e) titulaire")

    G.registre("decrochage", "Absences et décrochage", [
        ("nom", "Nom", "texte"), ("prenoms", "Prénoms", "texte"), ("sexe", "Sexe", "choix:sexe"), ("cours", "Cours", "choix:cours"),
        ("absences", "Demi-journées d’absence", "entier"), ("periode", "Période", "texte"), ("dateSignalement", "Date du signalement", "date"),
        ("motif", "Motif", "choix:motifs"), ("actions", "Actions (visite, entretien, médiation…)", "long"), ("statut", "Statut", "choix:statut_decr"),
        ("observations", "Observations", "long")], unite="signalement", oblig="nom", ordre="dateSignalement DESC, nom", portee="ecole",
        feuille="Absences et décrochage", onglet="Décrochage : fiches", entite=True, niveaux=["ECOLE"], unique=("nom", "prenoms", "dateSignalement"),
        filtres=("statut", "motif"), fiches={"signalement": ("Fiche de signalement", "alerte", doc_decrochage)},
        defauts=lambda: dict(ent_ecole(), dateSignalement=date.today().isoformat(), statut="Signalé"), doc="Absences et décrochage")
    G.page("sante_scolaire_stocks", "Soldes des stocks")
    G.page("sante_scolaire_absences", "Absences (30 jours)")

    # ------------------------------------------------------------------ données de l'école
    def effectifs_gf():
        try:
            x = q("SELECT SUM(e.sexe='F') f, SUM(e.sexe='M') m FROM eleves e JOIN classes c ON c.id=e.classe_id WHERE e.statut='inscrit' AND c.ecole_id=?",
                  (H.eco(),), un=True)
            return {"inscrites": x["f"] or 0, "garcons": x["m"] or 0}
        except Exception:  # noqa: BLE001
            return {}

    def absences(ecole_id=None, jours=30, jour=None):
        """Absences des `jours` derniers jours (appel) : [{nom, prenoms, sexe, cours, classe, absences (demi-journées)}]."""
        jour = jour or date.today()
        d1 = (jour - timedelta(days=jours)).isoformat()
        try:
            rows = q("""SELECT e.id, e.nom, e.prenoms, e.sexe, c.nom classe, c.niveau cours, COUNT(p.id) n
                        FROM presences p JOIN eleves e ON e.id=p.eleve_id JOIN classes c ON c.id=e.classe_id
                        WHERE p.statut='absent' AND p.date BETWEEN ? AND ? AND c.ecole_id=? AND e.statut='inscrit'
                        GROUP BY e.id ORDER BY n DESC, e.nom""", (d1, jour.isoformat(), ecole_id or H.eco()))
        except Exception:  # noqa: BLE001
            return []
        return [{"id": x["id"], "nom": x["nom"], "prenoms": x["prenoms"] or "", "sexe": x["sexe"] or "", "classe": x["classe"] or "",
                 "cours": x["cours"] if x["cours"] in COURS else "", "absences": 2 * (x["n"] or 0)} for x in rows]
    H.absences_30j = absences

    def soldes_ecole(annee=None):
        rows = [dict(x) for x in q("SELECT * FROM reg_sante_stocks WHERE portee=?" + (" AND annee=?" if annee else ""),
                                   (R.cle_portee("ecole"),) + ((annee,) if annee else ()))]
        return soldes(rows)

    def sante_alertes():
        if R.juridiction() and not g.get("ecole"):
            return []
        out = []
        try:
            for (den, un), v in soldes_ecole().items():
                if v <= 0:
                    out.append(("stock", "Stock épuisé", f"{den} : solde {str(v).replace('.', ',')} {un}", url_for("sante_scolaire_stocks")))
        except Exception:  # noqa: BLE001
            pass
        deja = {(R._norm(x["nom"]), R._norm(x["prenoms"])) for x in q(
            "SELECT nom, prenoms FROM reg_sante_decrochage WHERE portee=? AND COALESCE(statut,'') IN ('Signalé','En suivi')", (R.cle_portee("ecole"),))}
        for e in absences():
            if e["absences"] >= SEUIL:
                suivi = (R._norm(e["nom"]), R._norm(e["prenoms"])) in deja
                out.append(("decrochage", "Décrochage", f"{e['nom']} {e['prenoms']} ({e['classe']}) : {e['absences']} demi-journées d'absence en 30 jours"
                            + (" — fiche ouverte" if suivi else ""), url_for("sante_scolaire_absences")))
        return out
    H.sante_alertes = sante_alertes
    G.alertes = lambda: (len(sante_alertes()) + len((getattr(H, "sport_alertes", None) or (lambda: []))()),
                         url_for("liaison_alertes") if "liaison_alertes" in app.view_functions else url_for("sante_scolaire_absences"))

    def sante_synthese(annee=None):
        """Synthèse pour le tableau de bord du pilotage (école courante)."""
        annee = annee or R.annee_active()
        p = R.cle_portee("ecole")
        try:
            v = q("SELECT COUNT(*) n, SUM(aptitude='Apte' OR aptitude='Apte avec réserve') a, SUM(aptitude='Inapte') i FROM reg_sante_visites "
                  "WHERE portee=? AND annee=?", (p, annee), un=True)
            c = q("SELECT SUM(COALESCE(servisG,0)+COALESCE(servisF,0)) s FROM reg_sante_cantine WHERE portee=? AND annee=?", (p, annee), un=True)
            return {"visites": v["n"] or 0, "aptes": v["a"] or 0, "inaptes": v["i"] or 0,
                    "incidents": q("SELECT COUNT(*) n FROM reg_sante_infirmerie WHERE portee=? AND annee=?", (p, annee), un=True)["n"],
                    "repas_servis": c["s"] or 0,
                    "besoins_specifiques": q("SELECT COUNT(*) n FROM reg_sante_besoins WHERE portee=? AND annee=?", (p, annee), un=True)["n"],
                    "decrochage": q("SELECT COUNT(*) n FROM reg_sante_decrochage WHERE portee=? AND annee=?", (p, annee), un=True)["n"]}
        except Exception:  # noqa: BLE001
            return {}
    H.sante_synthese = sante_synthese

    # ------------------------------------------------------------------ pages
    @app.route("/sante-scolaire/stocks")
    @H.connexion_requise("sante_scolaire")
    def sante_scolaire_stocks():
        annee = (request.args.get("annee") or "").strip() or None
        s = soldes_ecole(annee)
        return render_template("sante_stocks.html", G=G, ep_actif="sante_scolaire_stocks", soldes=sorted(s.items()), annee=annee)

    @app.route("/sante-scolaire/absences", methods=["GET", "POST"])
    @H.connexion_requise("sante_scolaire")
    def sante_scolaire_absences():
        seuil = request.values.get("seuil", type=int) or SEUIL
        if request.method == "POST":
            if not G.peut_ecrire(G.registres["decrochage"]):
                flash("Écriture réservée à la direction.", "warning")
                return redirect(url_for("sante_scolaire_absences", seuil=seuil))
            eid = request.form.get("eleve", type=int)
            e = next((x for x in absences() if x["id"] == eid), None)
            if e:
                jour = date.today()
                if not q("SELECT 1 FROM reg_sante_decrochage WHERE portee=? AND nom=? AND COALESCE(prenoms,'')=? AND dateSignalement=?",
                         (R.cle_portee("ecole"), e["nom"], e["prenoms"], jour.isoformat()), un=True):
                    ex("INSERT INTO reg_sante_decrochage (portee, annee, niveau, entite, nom, prenoms, sexe, cours, absences, periode, dateSignalement, "
                       "statut, cree_le, cree_par, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (R.cle_portee("ecole"), R.annee_active(), "ECOLE", R.entite_courante()[1], e["nom"], e["prenoms"], e["sexe"], e["cours"],
                        e["absences"], f"du {R.jjmmaaaa((jour - timedelta(days=30)).isoformat())} au {R.jjmmaaaa(jour.isoformat())}",
                        jour.isoformat(), "Signalé", H.maintenant(), g.user["id"], H.maintenant()))
                    H.journal("decrochage_fiche", f"{e['nom']} {e['prenoms']}")
                flash("Fiche de signalement créée.", "success")
            return redirect(url_for("reg_page", gcle="sante", rcle="decrochage"))
        lst = absences()
        return render_template("sante_absences.html", G=G, ep_actif="sante_scolaire_absences", eleves=lst, seuil=seuil,
                               peut_ecrire=G.peut_ecrire(G.registres["decrochage"]))
