# -*- coding: utf-8 -*-
"""v2.3 — CEP 2027 : centres et salles de composition (module Examens et concours).

Source : lettre de la DDEMP du Plateau « Dispositions a/s des centres d'examens CEP 2027 » (28/10/2026) : point des candidats
par centre et du nombre de salles de composition en bon état disponibles, pour repérer les centres dont l'effectif dépasse la
capacité d'accueil. Deux présentations, comme les modèles reçus :
* (A) tableau simple : N° · Nom des centres · Effectif des candidats · Nombre de salles de composition en bon état
  disponible · Observations ;
* (B) tableau détaillé : candidats officiels G / F / Total / Dont handicapés, candidats libres (idem), total (officiels +
  libres) (idem), salles disponibles, observations, ligne TOTAL ; légende G = Garçons ; F = Filles ; H = Handicapés.

Saisie : registre « examens:salles » (ajouter / modifier / supprimer / réinitialiser, Excel commun), éditions CS et DDEMP ;
action « Charger les centres de la CS de Pobè » ; pré-remplissage des candidats officiels G / F depuis le registre des
candidats (cases vides seulement). « Candidats par salle » de 30 à 40 (30 par défaut) : salles nécessaires =
arrondi supérieur (total / n), écart = salles disponibles − salles nécessaires, situation « Capacité suffisante » ou
« Capacité dépassée : N salle(s) manquante(s) » reprise dans les observations quand elles sont vides.
DDEMP : un bloc par CS (tableaux reçus par la synchronisation 2.0 ou par import Excel) et le total du département.
Éditions école : lecture seule du centre de l'école (copie descendue de la CS).
Téléchargements : PDF paysage signé (QR) et Excel (en-têtes fusionnés, formules vivantes) dans les deux présentations.
Routes : /examens/cep2027 · /examens/cep2027.pdf · /examens/cep2027.xlsx · POST /examens/cep2027/pobe · /examens/cep2027/pre-remplir
"""
import io
import math
import re
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, send_file, url_for

import registres as R

CENTRES_POBE = ["POBE-CENTRE", "POBE-NORD", "OKE-OLA", "OKE-ATA", "ONIGBOLO", "TOWE"]
N_MIN, N_MAX, N_DEFAUT = 30, 40, 30
CHAMPS_NUM = ("offG", "offF", "offH", "libG", "libF", "libH", "salles")
ROLES_SAISIE = {"admin", "fondateur", "responsable", "chef_service", "cp", "agent"}


def entier(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def saison_de(annee):
    """« 2026-2027 » -> « JUIN 2027 » (champ « saison » des tableaux CEP, commun aux applications)."""
    m = re.match(r"(\d{4})-(\d{4})", annee or "")
    return f"JUIN {m.group(2)}" if m else ""


def session_de(annee):
    """« 2026-2027 » -> « SESSION DE JUIN 2027 »."""
    m = re.match(r"(\d{4})-(\d{4})", annee or "")
    return f"SESSION DE JUIN {m.group(2) if m else ''}".strip()


def nom_court(t):
    """« Circonscription scolaire de Pobè » -> « POBÈ » ; « DDEMP du Plateau » -> « PLATEAU » (cartouche des modèles)."""
    t = (t or "").strip()
    if re.match(r"(?i)direction d[ée]partementale", t):
        m = re.search(r"(?i).*\b(?:du|de la|de l'|des)\s+(\S.*)$", t)
        if m:
            return m.group(1).upper()
    t2 = re.sub(r"(?i)^(circonscription scolaire|direction d[ée]partementale[^,]*?|ddemp|cs)\s*(de la |du |de l'|d'|de |des )?", "", t).strip(" -—")
    return (t2 or t).upper()


def calculer(x, n):
    """Ligne -> valeurs calculées (totaux, salles nécessaires, écart, situation, observation affichée)."""
    v = {k: entier(x.get(k)) for k in CHAMPS_NUM}
    z = {k: (v[k] or 0) for k in CHAMPS_NUM}
    saisi_off = any(v[k] is not None for k in ("offG", "offF"))
    saisi_lib = any(v[k] is not None for k in ("libG", "libF"))
    o = {"ot": z["offG"] + z["offF"] if saisi_off else None,
         "lt": z["libG"] + z["libF"] if saisi_lib else None}
    o["tg"] = z["offG"] + z["libG"] if (v["offG"] is not None or v["libG"] is not None) else None
    o["tf"] = z["offF"] + z["libF"] if (v["offF"] is not None or v["libF"] is not None) else None
    o["tt"] = (o["tg"] or 0) + (o["tf"] or 0) if (o["tg"] is not None or o["tf"] is not None) else None
    o["th"] = z["offH"] + z["libH"] if (v["offH"] is not None or v["libH"] is not None) else None
    o["necessaires"] = math.ceil(o["tt"] / n) if o["tt"] else (0 if o["tt"] == 0 else None)
    o["ecart"] = v["salles"] - o["necessaires"] if (v["salles"] is not None and o["necessaires"] is not None) else None
    if o["ecart"] is None or not o["tt"]:
        o["situation"] = ""
    elif o["ecart"] >= 0:
        o["situation"] = "Capacité suffisante"
    else:
        o["situation"] = f"Capacité dépassée : {-o['ecart']} salle(s) manquante(s)"
    o["depasse"] = o["ecart"] is not None and o["ecart"] < 0 and bool(o["tt"])
    obs = (x.get("observations") or "").strip()
    o["observation"] = obs or o["situation"]
    o["observation_saisie"] = bool(obs)
    o.update(v)
    return o


def totaliser(lignes):
    t = {}
    for k in CHAMPS_NUM + ("ot", "lt", "tg", "tf", "tt", "th", "necessaires"):
        vals = [l["c"][k] for l in lignes if l["c"].get(k) is not None]
        t[k] = sum(vals) if vals else None
    t["ecart"] = t["salles"] - t["necessaires"] if (t["salles"] is not None and t["necessaires"] is not None) else None
    t["manquantes"] = sum(-l["c"]["ecart"] for l in lignes if l["c"]["depasse"])
    t["centres_depasses"] = sum(1 for l in lignes if l["c"]["depasse"])
    return t


def enregistrer(app, H):
    q, ex = H.q, H.ex
    cfg = H.config
    G = R.GROUPES.get("examens")
    if G is None:
        return
    R.types_documents({"cep2027_centres": "CEP — tableau de synthèse des centres et salles"})

    def role_reel():
        return (g.get("role_reel") or g.user["role"]) if g.get("user") else None

    def peut_saisir():
        return bool(g.get("user")) and R.juridiction() and role_reel() in ROLES_SAISIE

    def ma_structure():
        return R.entite_courante()[1] if R.juridiction() and not g.get("ecole") else ""

    def niveau_struct():
        return "DDEMP" if cfg.EDITION == "ddemp" else "CS"

    def n_req():
        n = request.values.get("n", type=int)
        if n is None:
            d = H.doc_lire("cep2027:parametres", {}) or {}
            n = entier(d.get("n")) or N_DEFAUT
        return min(N_MAX, max(N_MIN, n))

    REG = G.registre("salles", "CEP — centres et salles de composition", [
        ("centre", "Nom du centre", "texte"), ("ordre", "N° d'ordre", "entier"),
        ("offG", "Candidats officiels — garçons", "entier"), ("offF", "Candidats officiels — filles", "entier"),
        ("offH", "Candidats officiels — dont handicapés", "entier"),
        ("libG", "Candidats libres — garçons", "entier"), ("libF", "Candidats libres — filles", "entier"),
        ("libH", "Candidats libres — dont handicapés", "entier"),
        ("salles", "Salles de composition en bon état disponibles", "entier"), ("observations", "Observations", "long")],
        unite="centre", oblig="centre", ordre="entite, ordre, centre", portee="structure", feuille="Centres CEP", onglet="Centres CEP (saisie)",
        entite=True, niveaux=["CS", "DDEMP"], unique=("entite", "centre"), annee_lib="Année scolaire", paysage=True, ecriture=peut_saisir,
        calcul=lambda x: (lambda c: {"Total": "" if c["tt"] is None else c["tt"], "Salles nécessaires (n = %d)" % N_DEFAUT:
                                     "" if c["necessaires"] is None else c["necessaires"], "Situation": c["situation"]})(calculer(x, N_DEFAUT)),
        colonnes=("entite", "ordre", "centre", "offG", "offF", "offH", "libG", "libF", "libH", "salles"),
        defauts=lambda: {"niveau": niveau_struct(), "entite": ma_structure(),
                         "ordre": (q(f"SELECT COALESCE(MAX(ordre),0)+1 n FROM reg_examens_salles WHERE portee=? AND annee=?",
                                     (R.cle_portee("structure"), R.annee_active()), un=True) or {"n": 1})["n"]},
        doc="Centres du CEP et salles de composition",
        aide="Un centre par ligne : candidats officiels et libres (garçons, filles, dont handicapés) et salles de composition en bon "
             "état disponibles. Totaux, salles nécessaires et situation : page « CEP — centres et salles ». Laissez « Observations » "
             "vide pour reprendre la situation calculée.")

    H.ajouter_colonne(REG.table, "sourceCandidats", "TEXT")
    H.ajouter_colonne(REG.table, "saison", "TEXT")                 # « JUIN 2027 » (commun aux applications)
    REG.apres_enregistrer = lambda rid: ex("UPDATE reg_examens_salles SET saison=? WHERE id=? AND COALESCE(saison,'')=''",
                                            (saison_de((q("SELECT annee FROM reg_examens_salles WHERE id=?", (rid,), un=True) or {"annee": ""})["annee"]), rid))        # v2.3.1 : provenance du pré-remplissage (écoles, date)

    # ------------------------------------------------------------------ données affichées
    def centres_ecole():
        """Centre(s) de composition de l'école : fiches d'inscription au CEP et registre des candidats."""
        noms = set()
        try:
            for r in q("SELECT DISTINCT centre FROM cep_fiches WHERE COALESCE(centre,'')<>''"):
                noms.add(R._norm(r["centre"]).strip())
        except Exception:  # noqa: BLE001
            pass
        try:
            for r in q("SELECT DISTINCT centre FROM reg_examens_candidats WHERE COALESCE(centre,'')<>''"):
                noms.add(R._norm(r["centre"]).strip())
        except Exception:  # noqa: BLE001
            pass
        return noms

    def lignes_brutes(annee):
        rows = [dict(x) for x in q("SELECT * FROM reg_examens_salles WHERE annee=? ORDER BY entite, ordre, centre", (annee,))]
        mien = R.cle_portee("structure")
        if R.juridiction() and cfg.EDITION == "cs" and not g.get("ecole"):
            rows = [x for x in rows if x["portee"] == mien]
        # une ligne par (CS, centre) : la plus récente (copies reçues plusieurs fois)
        par = {}
        for x in rows:
            k = (R._norm(x.get("entite")).strip(), R._norm(x.get("centre")).strip())
            if k not in par or (x.get("maj") or "") >= (par[k].get("maj") or ""):
                par[k] = x
        return list(par.values())

    def blocs(annee, n):
        rows = lignes_brutes(annee)
        note = ""
        if not R.juridiction():
            mes = centres_ecole()
            if mes:
                rows = [x for x in rows if R._norm(x.get("centre")).strip() in mes]
                if not rows:
                    note = "Le tableau de la circonscription n'a pas encore été reçu pour le centre de l'école (synchronisation)."
            else:
                rows = []
                note = "Centre de composition de l'école inconnu : renseignez-le dans les fiches d'inscription au CEP."
        groupes = {}
        for x in rows:
            groupes.setdefault((x.get("entite") or ma_structure() or "—").strip(), []).append(x)
        out = []
        for cs, xs in sorted(groupes.items(), key=lambda kv: R._norm(kv[0])):
            xs.sort(key=lambda x: (entier(x.get("ordre")) or 999, R._norm(x.get("centre"))))
            lignes = [{"x": x, "c": calculer(x, n)} for x in xs]
            out.append({"cs": cs, "lignes": lignes, "total": totaliser(lignes)})
        dep = totaliser([l for b in out for l in b["lignes"]]) if len(out) > 1 or cfg.EDITION == "ddemp" else None
        return out, dep, note

    def titre_structure():
        return (cfg.ECOLE.get("nom") or "").strip()

    # ------------------------------------------------------------------ page
    @app.route("/examens/cep2027", methods=["GET", "POST"])
    @H.connexion_requise("examens_pvs")
    def examens_cep2027():
        annee = (request.values.get("annee") or "").strip()
        annee = annee if re.fullmatch(r"\d{4}-\d{4}", annee) else R.annee_active()
        vue = "simple" if request.values.get("vue") == "simple" else "detaille"
        n = n_req()
        if request.method == "POST":
            if not peut_saisir():
                abort(403)
            H.doc_ecrire("cep2027:parametres", {"n": n})
            flash(f"Candidats par salle : {n}.", "success")
            return redirect(url_for("examens_cep2027", annee=annee, vue=vue, n=n))
        bl, dep, note = blocs(annee, n)
        return render_template("examens_cep2027.html", G=G, ep_actif="examens_cep2027", blocs=bl, dep=dep, note=note, annee=annee,
                               annees=R.annees_proposees([annee]), vue=vue, n=n, n_choix=list(range(N_MIN, N_MAX + 1)),
                               saisie=peut_saisir(), session=session_de(annee), ddemp=cfg.EDITION == "ddemp", jur=R.juridiction(),
                               structure=titre_structure())
    G.page("examens_cep2027", "CEP — centres et salles", apres=False)

    @app.route("/examens/cep2027/pobe", methods=["POST"])
    @H.connexion_requise("examens_pvs")
    def examens_cep2027_pobe():
        if not peut_saisir():
            abort(403)
        annee = R.annee_active()
        p = R.cle_portee("structure")
        ent = ma_structure() or "CS POBE"
        deja = {R._norm(x["centre"]).strip() for x in q("SELECT centre FROM reg_examens_salles WHERE portee=? AND annee=?", (p, annee))}
        n = 0
        for i, nom in enumerate(CENTRES_POBE, 1):
            if R._norm(nom) in deja:
                continue
            ex("INSERT INTO reg_examens_salles (portee, annee, niveau, entite, centre, ordre, saison, cree_le, cree_par, maj) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (p, annee, niveau_struct(), ent, nom, i, saison_de(annee), H.maintenant(), g.user["id"], H.maintenant()))
            n += 1
        H.journal("cep2027_centres_pobe", f"{n} centre(s)")
        flash(f"{n} centre(s) de la CS de Pobè ajouté(s)." if n else "Les centres de la CS de Pobè sont déjà dans le tableau.", "success")
        return redirect(url_for("examens_cep2027"))

    @app.route("/examens/cep2027/pre-remplir", methods=["POST"])
    @H.connexion_requise("examens_pvs")
    def examens_cep2027_pre_remplir():
        """Candidats officiels G / F par centre depuis le registre des candidats (cases vides seulement)."""
        if not peut_saisir():
            abort(403)
        annee = R.annee_active()
        p = R.cle_portee("structure")
        compte = {}
        try:
            for r in q("SELECT centre, sexe, COUNT(*) n FROM reg_examens_candidats WHERE annee=? AND COALESCE(statut,'Inscrit') NOT IN "
                       "('Abandon','Exclu') AND COALESCE(centre,'')<>'' GROUP BY centre, sexe", (annee,)):
                c = compte.setdefault(R._norm(r["centre"]).strip(), {"M": 0, "F": 0})
                c["F" if (r["sexe"] or "").upper().startswith("F") else "M"] += r["n"]
        except Exception:  # noqa: BLE001
            pass
        # v2.3.1 : CS — candidats transmis par les écoles (section « cep » : centre de chaque candidat), avec la source
        sources = {}
        if R.juridiction():
            try:
                lignes = q("SELECT s.ecole_id, s.donnees, s.maj, e.nom FROM jur_sections s JOIN jur_ecoles e ON e.id=s.ecole_id "
                           "WHERE s.section='cep' AND s.annee=? AND COALESCE(e.actif,1)=1", (annee,))
            except Exception:  # noqa: BLE001
                lignes = []
            import json as _json
            for r in lignes:
                try:
                    d = _json.loads(r["donnees"] or "{}")
                except ValueError:
                    continue
                for ce, gf in (d.get("par_centre") or {}).items():
                    k = R._norm(ce).strip()
                    if not k:
                        continue
                    c = compte.setdefault(k, {"M": 0, "F": 0})
                    c["M"] += int(gf.get("g") or 0)
                    c["F"] += int(gf.get("f") or 0)
                    so = sources.setdefault(k, {"nom": ce.strip().upper(), "ecoles": set(), "maj": ""})
                    so["ecoles"].add(r["nom"])
                    so["maj"] = max(so["maj"], (r["maj"] or "")[:10])
            connus = {R._norm(x["centre"]).strip() for x in q("SELECT centre FROM reg_examens_salles WHERE portee=? AND annee=?", (p, annee))}
            for k, so in sources.items():                  # centre déclaré par les écoles, absent du tableau : ajouté
                if k not in connus:
                    ex("INSERT INTO reg_examens_salles (portee, annee, niveau, entite, centre, saison, cree_le, cree_par, maj) VALUES (?,?,?,?,?,?,?,?,?)",
                       (p, annee, niveau_struct(), ma_structure(), so["nom"], saison_de(annee), H.maintenant(), g.user["id"], H.maintenant()))
        n = 0
        for x in q("SELECT * FROM reg_examens_salles WHERE portee=? AND annee=?", (p, annee)):
            c = compte.get(R._norm(x["centre"]).strip())
            if not c:
                continue
            maj = {}
            if x["offG"] is None:
                maj["offG"] = c["M"]
            if x["offF"] is None:
                maj["offF"] = c["F"]
            so = sources.get(R._norm(x["centre"]).strip())
            if so and maj:
                maj["sourceCandidats"] = f"{len(so['ecoles'])} école(s) ({', '.join(sorted(so['ecoles']))[:300]}) — transmis le {R.jjmmaaaa(so['maj'])}"
            if maj:
                ex("UPDATE reg_examens_salles SET " + ", ".join(f"{k}=?" for k in maj) + ", maj=? WHERE id=?",
                   tuple(maj.values()) + (H.maintenant(), x["id"]))
                n += 1
        H.journal("cep2027_pre_remplissage", f"{n} centre(s)")
        flash(f"{n} centre(s) pré-rempli(s) depuis les candidats inscrits." if n else
              "Aucun centre pré-rempli (candidats non saisis, centres différents ou cases déjà remplies).", "info")
        return redirect(url_for("examens_cep2027"))

    # ------------------------------------------------------------------ PDF
    def f0(v):
        return "" if v is None else str(v)

    def pdf_cep(annee, vue, n):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
        bl, dep, _note = blocs(annee, n)
        W = landscape(A4)[0] - 24 * 2.8346
        st = ParagraphStyle("c", fontName="Helvetica", fontSize=7.6, leading=9.2, alignment=1)
        stg = ParagraphStyle("cg", parent=st, alignment=0)
        sth = ParagraphStyle("h", parent=st, fontName="Helvetica-Bold")
        stb = ParagraphStyle("b", fontName="Helvetica-Bold", fontSize=9.5, leading=13)
        stl = ParagraphStyle("l", fontName="Helvetica-Oblique", fontSize=7.2, leading=9)

        def P(t, s=st):
            return Paragraph(R.esc(t), s)

        def cartouche(cs):
            lib = "DDEMP" if (cfg.EDITION == "ddemp" and cs == struct) or cs.upper().startswith(("DDEMP", "DIRECTION")) else "CS"
            t = Table([[Paragraph(f"<b>CEP : {R.esc(session_de(annee))}</b>", stb)], [Paragraph(f"<b>{lib} : {R.esc(nom_court(cs))}</b>", stb)]],
                      colWidths=[W * 0.36], hAlign="LEFT")
            t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
            return t

        def table_bloc(b, titre_total="TOTAL"):
            gris = colors.HexColor("#F2F4F7")
            rouge = colors.HexColor("#FDECEA")
            if vue == "simple":
                data = [[P("N°", sth), P("Nom des Centres", sth), P("Effectif des candidats", sth),
                         P("Nombre de salles de composition en bon état disponible", sth), P("Observations", sth)]]
                for i, l in enumerate(b["lignes"], 1):
                    c = l["c"]
                    data.append([P(str(i)), P(l["x"]["centre"] or ""), P(f0(c["tt"])), P(f0(c["salles"])), P(c["observation"], stg)])
                t = b["total"]
                data.append(["", P(titre_total, sth), P(f0(t["tt"]), sth), P(f0(t["salles"]), sth),
                             P(f"{t['centres_depasses']} centre(s) en dépassement, {t['manquantes']} salle(s) manquante(s)" if t["centres_depasses"] else "", stg)])
                lg = [0.05, 0.25, 0.15, 0.2, 0.35]
                tb = Table(data, colWidths=[W * 0.75 * x for x in lg], repeatRows=1, hAlign="LEFT")
                sty = [("GRID", (0, 0), (-1, -1), 0.6, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                       ("BACKGROUND", (0, -1), (-1, -1), gris)]
                rang = 1
            else:
                h1 = [P("N°", sth), P("Nom des Centres", sth), P("Effectif des candidats", sth)] + [""] * 11 + \
                     [P("Nombre de salles de composition en bon état disponible", sth), P("Observations", sth)]
                h2 = ["", "", P("Candidats officiels", sth), "", "", "", P("Candidats libres", sth), "", "", "",
                      P("Total (officiels + libres)", sth), "", "", "", "", ""]
                h3 = ["", ""] + [P(x, sth) for x in ("G", "F", "Total", "Dont H") * 3] + ["", ""]
                data = [h1, h2, h3]
                for i, l in enumerate(b["lignes"], 1):
                    c = l["c"]
                    data.append([P(str(i)), P(l["x"]["centre"] or "")] + [P(f0(c[k])) for k in ("offG", "offF", "ot", "offH",
                                 "libG", "libF", "lt", "libH", "tg", "tf", "tt", "th", "salles")] + [P(c["observation"], stg)])
                t = b["total"]
                data.append(["", P(titre_total, sth)] + [P(f0(t[k]), sth) for k in ("offG", "offF", "ot", "offH", "libG",
                             "libF", "lt", "libH", "tg", "tf", "tt", "th", "salles")] +
                            [P(f"{t['manquantes']} salle(s) manquante(s)" if t["manquantes"] else "", stg)])
                lg = [0.035, 0.115] + [0.045] * 12 + [0.09, 0.22]
                tb = Table(data, colWidths=[W * x for x in lg], repeatRows=3, hAlign="LEFT")
                sty = [("GRID", (0, 0), (-1, -1), 0.6, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                       ("SPAN", (0, 0), (0, 2)), ("SPAN", (1, 0), (1, 2)), ("SPAN", (2, 0), (13, 0)), ("SPAN", (14, 0), (14, 2)),
                       ("SPAN", (15, 0), (15, 2)), ("SPAN", (2, 1), (5, 1)), ("SPAN", (6, 1), (9, 1)), ("SPAN", (10, 1), (13, 1)),
                       ("BACKGROUND", (0, -1), (-1, -1), gris)]
                rang = 3
            for i, l in enumerate(b["lignes"]):
                if l["c"]["depasse"]:
                    sty.append(("BACKGROUND", (0, rang + i), (-1, rang + i), rouge))
            tb.setStyle(TableStyle(sty))
            return tb

        corps = []
        struct = titre_structure()
        if cfg.EDITION == "ddemp":
            for b in bl:
                corps += [cartouche(b["cs"]), Spacer(1, 6), table_bloc(b), Spacer(1, 12)]
            if dep is not None:
                corps += [cartouche(struct or "DDEMP"), Spacer(1, 6),
                          table_bloc({"lignes": [{"x": {"centre": "CS " + nom_court(b["cs"])}, "c": dict(b["total"], observation=(
                              f"Capacité dépassée : {b['total']['manquantes']} salle(s) manquante(s)" if b["total"]["manquantes"] else
                              ("Capacité suffisante" if b["total"]["tt"] else "")), depasse=bool(b["total"]["manquantes"]))} for b in bl],
                                      "total": dep}, "TOTAL DÉPARTEMENT")]
        else:
            b0 = bl[0] if bl else {"cs": struct, "lignes": [], "total": totaliser([])}
            corps += [cartouche(b0["cs"] or struct), Spacer(1, 8), table_bloc(b0)]
        corps += [Spacer(1, 4), Paragraph(f"G = Garçons ; F = Filles ; H = Handicapés. Salles nécessaires calculées à {n} candidats par salle "
                                          "(arrondi supérieur).", stl)]
        code = R.code_document("cep2027_centres", f"Centres et salles du CEP — {session_de(annee)} — {struct}"[:250],
                               f"cep2027:{annee}:{vue}:{n}")
        sig = R.signature_autorite("Le Directeur Départemental" if cfg.EDITION == "ddemp" else "Le Chef de la Circonscription Scolaire")
        return R.pdf_document("TABLEAU DE SYNTHESE DES STATISTIQUES", corps, [sig], code, paysage=True, nom_auteur="SCOLARIS")

    @app.route("/examens/cep2027.pdf")
    @H.connexion_requise("examens_pvs")
    def examens_cep2027_pdf():
        annee = request.args.get("annee") or R.annee_active()
        annee = annee if re.fullmatch(r"\d{4}-\d{4}", annee) else R.annee_active()
        vue = "simple" if request.args.get("vue") == "simple" else "detaille"
        data = pdf_cep(annee, vue, n_req())
        H.journal("cep2027_pdf", f"{annee} {vue}")
        return send_file(io.BytesIO(data), mimetype="application/pdf", as_attachment=True,
                         download_name=f"CEP_{annee[-4:]}_centres_et_salles_{'simple' if vue == 'simple' else 'detaille'}.pdf")

    # ------------------------------------------------------------------ Excel (même présentation que le modèle, formules vivantes)
    def excel_cep(annee, vue, n):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter as L
        bl, dep, _note = blocs(annee, n)
        wb = Workbook()
        fin = Side(style="thin")
        bord = Border(left=fin, right=fin, top=fin, bottom=fin)
        centre = Alignment(horizontal="center", vertical="center", wrap_text=True)
        gras = Font(bold=True)
        rouge = PatternFill("solid", fgColor="FDECEA")
        grisf = PatternFill("solid", fgColor="F2F4F7")
        struct = titre_structure()

        def feuille(ws, cs, b):
            detail = vue != "simple"
            der = "P" if detail else "E"
            ws.merge_cells(f"A1:{der}1")
            ws["A1"] = "TABLEAU DE SYNTHESE DES STATISTIQUES"
            ws["A1"].font = Font(bold=True, size=14)
            ws["A1"].alignment = Alignment(horizontal="center")
            ws.merge_cells("A3:D3" if detail else "A3:C3")
            ws.merge_cells("A4:D4" if detail else "A4:C4")
            ws["A3"] = f"CEP : {session_de(annee)}"
            ws["A4"] = f"{'DDEMP' if cs == struct and cfg.EDITION == 'ddemp' else 'CS'} : {nom_court(cs)}"
            ws["A3"].font = ws["A4"].font = gras
            cn = "O3" if detail else "D2"
            ws["N3" if detail else "C2"] = "Candidats par salle"
            ws[cn] = n
            ws[cn].font = gras
            ncell = "$" + re.sub(r"(\d+)", r"$\1", cn)
            premiere = 9 if detail else 7
            if detail:
                for rng, val in (("A6:A8", "N°"), ("B6:B8", "Nom des Centres"), ("C6:N6", "Effectif des candidats"),
                                 ("O6:O8", "Nombre de salles de composition en bon état disponible"), ("P6:P8", "Observations"),
                                 ("C7:F7", "Candidats officiels"), ("G7:J7", "Candidats libres"), ("K7:N7", "Total (officiels + libres)")):
                    ws.merge_cells(rng)
                    ws[rng.split(":")[0]] = val
                for i, lib in enumerate(("Garçons", "Filles", "Total", "Dont handicapés") * 3):
                    ws.cell(row=8, column=3 + i, value=lib)
                for r_ in range(6, 9):
                    for c_ in range(1, 17):
                        ws.cell(row=r_, column=c_).border = bord
                        ws.cell(row=r_, column=c_).alignment = centre
                        ws.cell(row=r_, column=c_).font = gras
                larg = {"A": 5, "B": 18, "O": 18, "P": 30}
                for c_ in range(3, 15):
                    larg[L(c_)] = 10
            else:
                for c_, val in enumerate(("N°", "Nom des Centres", "Effectif des candidats", "Nombre de salles de composition en bon état disponible",
                                          "Observations"), 1):
                    x = ws.cell(row=6, column=c_, value=val)
                    x.border, x.alignment, x.font = bord, centre, gras
                larg = {"A": 5, "B": 22, "C": 14, "D": 20, "E": 36}
            for k, v in larg.items():
                ws.column_dimensions[k].width = v
            r_ = premiere
            for i, l in enumerate(b["lignes"], 1):
                x, c = l["x"], l["c"]
                ws.cell(row=r_, column=1, value=i)
                ws.cell(row=r_, column=2, value=x.get("centre") or "")
                if detail:
                    for col, k in ((3, "offG"), (4, "offF"), (6, "offH"), (7, "libG"), (8, "libF"), (10, "libH"),
                                   (15, "salles")):
                        ws.cell(row=r_, column=col, value=c[k])
                    ws[f"E{r_}"] = f'=IF(COUNT(C{r_}:D{r_})=0,"",SUM(C{r_}:D{r_}))'
                    ws[f"I{r_}"] = f'=IF(COUNT(G{r_}:H{r_})=0,"",SUM(G{r_}:H{r_}))'
                    ws[f"K{r_}"] = f'=IF(COUNT(C{r_},G{r_})=0,"",SUM(C{r_},G{r_}))'
                    ws[f"L{r_}"] = f'=IF(COUNT(D{r_},H{r_})=0,"",SUM(D{r_},H{r_}))'
                    ws[f"M{r_}"] = f'=IF(COUNT(K{r_}:L{r_})=0,"",SUM(K{r_}:L{r_}))'
                    ws[f"N{r_}"] = f'=IF(COUNT(F{r_},J{r_})=0,"",SUM(F{r_},J{r_}))'
                    tot, sal, obs = f"M{r_}", f"O{r_}", f"P{r_}"
                else:
                    ws.cell(row=r_, column=3, value=c["tt"])
                    ws.cell(row=r_, column=4, value=c["salles"])
                    tot, sal, obs = f"C{r_}", f"D{r_}", f"E{r_}"
                if c["observation_saisie"]:
                    ws[obs] = x.get("observations")
                else:
                    ws[obs] = (f'=IF(OR({tot}="",{tot}=0,{sal}=""),"",IF({sal}>=ROUNDUP({tot}/{ncell},0),"Capacité suffisante",'
                               f'"Capacité dépassée : "&(ROUNDUP({tot}/{ncell},0)-{sal})&" salle(s) manquante(s)"))')
                for col in range(1, 17 if detail else 6):
                    ws.cell(row=r_, column=col).border = bord
                    ws.cell(row=r_, column=col).alignment = centre if col not in (2, 16 if detail else 5) else Alignment(vertical="center", wrap_text=True)
                    if c["depasse"]:
                        ws.cell(row=r_, column=col).fill = rouge
                r_ += 1
            dern = r_ - 1
            ws.cell(row=r_, column=2, value="TOTAL").font = gras
            cols = range(3, 16) if detail else (3, 4)
            for col in cols:
                lt = L(col)
                ws[f"{lt}{r_}"] = f"=SUM({lt}{premiere}:{lt}{dern})" if dern >= premiere else 0
                ws[f"{lt}{r_}"].font = gras
            for col in range(1, 17 if detail else 6):
                ws.cell(row=r_, column=col).border = bord
                ws.cell(row=r_, column=col).fill = grisf
                ws.cell(row=r_, column=col).alignment = centre
            ws.cell(row=r_ + 1, column=1, value="G = Garçons ; F = Filles ; H = Handicapés").font = Font(italic=True, size=8)
            ws.page_setup.orientation = "landscape"
            ws.page_setup.fitToWidth = 1
            ws.sheet_properties.pageSetUpPr.fitToPage = True

        ws0 = wb.active
        if not bl:
            ws0.title = "Synthèse"
            feuille(ws0, struct, {"lignes": [], "total": totaliser([])})
        for i, b in enumerate(bl):
            ws = ws0 if i == 0 else wb.create_sheet()
            ws.title = (re.sub(r"[\\/*?:\[\]]", " ", nom_court(b["cs"]))[:28] or "CS") if cfg.EDITION == "ddemp" else "Synthèse"
            feuille(ws, b["cs"], b)
        if cfg.EDITION == "ddemp" and bl:
            ws = wb.create_sheet("Département")
            lignes = [{"x": {"centre": "CS " + nom_court(b["cs"]), "observations": ""}, "c": dict(b["total"], observation="", observation_saisie=False,
                                                                            depasse=bool(b["total"]["manquantes"]),
                                                                            offG=b["total"]["offG"], salles=b["total"]["salles"])}
                      for b in bl]
            feuille(ws, struct or "DDEMP", {"lignes": lignes, "total": dep})
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    @app.route("/examens/cep2027.xlsx")
    @H.connexion_requise("examens_pvs")
    def examens_cep2027_xlsx():
        annee = request.args.get("annee") or R.annee_active()
        annee = annee if re.fullmatch(r"\d{4}-\d{4}", annee) else R.annee_active()
        vue = "simple" if request.args.get("vue") == "simple" else "detaille"
        data = excel_cep(annee, vue, n_req())
        H.journal("cep2027_excel", f"{annee} {vue}")
        return send_file(io.BytesIO(data), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True,
                         download_name=f"Tableau_synthese_statistiques_CEP_{annee[-4:]}{'' if vue == 'simple' else '_detaille'}.xlsx")

    H.cep2027_blocs = blocs
