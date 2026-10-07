# -*- coding: utf-8 -*-
"""Exploitation des évaluations (GESCOL v1.3) :
* Statistiques d'une évaluation (par sexe, tranches, matières, graphiques SVG, PDF, Excel) ;
* Analyse et rapport (texte rédigé automatiquement à partir des statistiques, modifiable, PDF signé) ;
* Tableau d'honneur (par évaluation ou bilan annuel) et certificats individuels d'honneur ;
* Bilan annuel et décision : M = (M_O + E_D) / 2, passage si maîtrise aux 2/3 des évaluations composées.

Ce module ne dépend PAS du module de saisie (m_evaluations) : il lit directement les tables
``evaluations`` et ``notes`` au moyen du moteur commun ``evaluations_core``."""
import hashlib
import io
import re

from flask import abort, flash, g, redirect, render_template, request, url_for
from markupsafe import Markup, escape

import evaluations_core as EC

# Couleurs des séries (palette catégorielle validée : bleu, orange, vert d'eau)
COUL = {"G": "#2a78d6", "F": "#eb6834", "T": "#1baf7a"}
SEXES = (("G", "Garçons"), ("F", "Filles"), ("T", "Total"))
# Champs d'en-tête produits par M.identification et repris sur les PDF
CHAMPS_ID = ("ddemp", "cs", "ecole", "cours", "annee", "titulaire_titre", "titulaire_nom", "directeur_titre",
             "directeur_nom")
RE_ANNEE = re.compile(r"^\d{4}-\d{4}$")


def titre_directeur(t):
    """« Directrice » → « La Directrice » ; sinon « Le Directeur »."""
    return "La Directrice" if "trice" in (t or "").lower() else "Le Directeur"


# ================================================================== mise en forme
def nb(v, d=2):
    """Nombre à la française : 12,50 ; « — » si absent."""
    if v is None or v == "":
        return "—"
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    try:
        return f"{float(v):.{d}f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(v)


def pc(v):
    return "—" if v is None else nb(v) + " %"


def esc(t):
    """Échappement pour les Paragraph ReportLab (mini_tableau n'échappe pas lui-même)."""
    return "" if t is None else str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rang_txt(rang, sexe=None, ex_aequo=False):
    if not rang:
        return "—"
    suf = ("re" if sexe == "F" else "er") if rang == 1 else "e"
    return f"{rang}{suf}{' ex æquo' if ex_aequo else ''}"


def vocab(cl):
    """Vocabulaire officiel selon le cycle : « maîtrise » au primaire, « admis » au secondaire."""
    if cl["cycle"] == "secondaire":
        return {"ok": "Admis (moy. ≥ 10)", "ko": "Non admis", "reussite": "réussite", "taux": "Taux de réussite",
                "regle": "moyenne pondérée ≥ 10/20", "ont": "sont admis"}
    if cl["cycle"] == "maternelle":
        return {"ok": "Progrès satisfaisants", "ko": "Progrès à renforcer", "reussite": "réussite",
                "taux": "Taux de réussite", "regle": "appréciations A / ECA / NA", "ont": "progressent de façon satisfaisante"}
    return {"ok": "Maîtrise", "ko": "Non-maîtrise", "reussite": "maîtrise", "taux": "Taux de maîtrise (réussite)",
            "regle": "au moins le seuil de matières à 10/20", "ont": "ont la maîtrise"}


# ================================================================== graphiques SVG (sans bibliothèque)
def _barre_arrondie(x, y, w, h, base):
    """Barre dont seul le haut est arrondi (4 px), ancrée sur la ligne de base."""
    r = max(0.0, min(4.0, w / 2, h))
    return (f'<path d="M{x:.1f},{base:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} H{x + w - r:.1f} '
            f'Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{base:.1f} Z"')


def _max_arrondi(v):
    if v <= 5:
        return 5
    for pas in (10, 20, 25, 50, 100, 200, 500, 1000):
        if v <= pas:
            return pas
    return v


def svg_barres(categories, series, titre="", maxi=None, suffixe=" %", largeur=560, hauteur=240):
    """Barres verticales groupées. series = [(nom, couleur, [valeur par catégorie])]."""
    if not categories or not series:
        return Markup("")
    mg, md, mh, mb = 38, 8, 14, 40
    leg = 24 if len(series) > 1 else 0
    ph = hauteur - mh - mb - leg
    pw = largeur - mg - md
    vals = [v for s in series for v in s[2] if v is not None]
    vmax = maxi or _max_arrondi(max(vals + [1]))
    base = mh + leg + ph
    o = [f'<svg viewBox="0 0 {largeur} {hauteur}" class="chart res-chart" role="img" aria-label="{escape(titre)}">',
         f"<title>{escape(titre)}</title>"]
    for k in range(5):  # grille discrète
        v = vmax * k / 4
        y = base - ph * k / 4
        o.append(f'<line x1="{mg}" x2="{largeur - md}" y1="{y:.1f}" y2="{y:.1f}" stroke="#EAECF0"/>')
        o.append(f'<text x="{mg - 5}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10" fill="#667085">'
                 f'{escape(nb(v, 0) if float(v).is_integer() else nb(v, 1))}</text>')
    if leg:
        x = mg
        for nom, coul, _ in series:
            o.append(f'<rect x="{x}" y="4" width="11" height="11" rx="2" fill="{coul}"/>'
                     f'<text x="{x + 15}" y="13.5" font-size="11" fill="#344054">{escape(nom)}</text>')
            x += 22 + 7 * len(nom)
    n = len(series)
    gw = pw / len(categories)
    bw = min(34.0, (gw * 0.72 - 2 * (n - 1)) / n)
    for i, cat in enumerate(categories):
        x0 = mg + i * gw + (gw - (n * bw + 2 * (n - 1))) / 2
        for j, (nom, coul, valeurs) in enumerate(series):
            v = valeurs[i]
            x = x0 + j * (bw + 2)
            h = ph * (v or 0) / vmax if vmax else 0
            o.append(f'<g class="barre-svg"><title>{escape(cat)} – {escape(nom)} : {escape(nb(v))}{escape(suffixe)}</title>')
            o.append(f'<rect x="{x - 1:.1f}" y="{mh + leg}" width="{bw + 2:.1f}" height="{ph}" fill="transparent"/>')
            if h > 0:
                o.append(_barre_arrondie(x, base - h, bw, h, base) + f' fill="{coul}"/>')
            if v is not None:
                o.append(f'<text x="{x + bw / 2:.1f}" y="{base - h - 4:.1f}" text-anchor="middle" font-size="9.5" '
                         f'fill="#344054">{escape(nb(v, 0 if float(v).is_integer() else 1))}</text>')
            o.append("</g>")
        lib = str(cat)
        lib = lib if len(lib) <= 16 else lib[:15] + "…"
        o.append(f'<text x="{mg + i * gw + gw / 2:.1f}" y="{base + 15}" text-anchor="middle" font-size="10.5" '
                 f'fill="#344054">{escape(lib)}</text>')
    o.append(f'<line x1="{mg}" x2="{largeur - md}" y1="{base}" y2="{base}" stroke="#98A2B3"/>')
    o.append("</svg>")
    return Markup("".join(o))


def svg_barres_h(libelles, series, titre="", maxi=100, ref=None, suffixe=" %", largeur=620):
    """Barres horizontales groupées (une ligne par libellé) ; ref = ligne verticale de référence (ex. 50 %)."""
    if not libelles or not series:
        return Markup("")
    n = len(series)
    bh = 9 if n > 1 else 14
    rang_h = n * (bh + 2) + 10
    mg, md, mh = 200, 44, 26 if n > 1 else 8
    hauteur = mh + rang_h * len(libelles) + 22
    pw = largeur - mg - md
    o = [f'<svg viewBox="0 0 {largeur} {hauteur}" class="chart res-chart" role="img" aria-label="{escape(titre)}">',
         f"<title>{escape(titre)}</title>"]
    if n > 1:
        x = mg
        for nom, coul, _ in series:
            o.append(f'<rect x="{x}" y="6" width="11" height="11" rx="2" fill="{coul}"/>'
                     f'<text x="{x + 15}" y="15.5" font-size="11" fill="#344054">{escape(nom)}</text>')
            x += 22 + 7 * len(nom)
    bas = mh + rang_h * len(libelles)
    for k in range(5):
        x = mg + pw * k / 4
        o.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{mh}" y2="{bas}" stroke="#EAECF0"/>'
                 f'<text x="{x:.1f}" y="{bas + 13}" text-anchor="middle" font-size="10" fill="#667085">'
                 f'{escape(nb(maxi * k / 4, 0))}</text>')
    for i, lib in enumerate(libelles):
        y0 = mh + i * rang_h + 5
        court = lib if len(lib) <= 32 else lib[:31] + "…"
        o.append(f'<text x="{mg - 6}" y="{y0 + (n * (bh + 2)) / 2 + 3:.1f}" text-anchor="end" font-size="10.5" '
                 f'fill="#344054"><title>{escape(lib)}</title>{escape(court)}</text>')
        for j, (nom, coul, valeurs) in enumerate(series):
            v = valeurs[i]
            y = y0 + j * (bh + 2)
            w = pw * min(v or 0, maxi) / maxi if maxi else 0
            r = min(4, bh / 2, w)
            o.append(f'<g><title>{escape(lib)} – {escape(nom)} : {escape(nb(v))}{escape(suffixe)}</title>'
                     f'<rect x="{mg}" y="{y - 1}" width="{pw}" height="{bh + 2}" fill="transparent"/>')
            if w > 0:
                o.append(f'<path d="M{mg},{y} H{mg + w - r:.1f} Q{mg + w:.1f},{y} {mg + w:.1f},{y + r:.1f} '
                         f'V{y + bh - r:.1f} Q{mg + w:.1f},{y + bh} {mg + w - r:.1f},{y + bh} H{mg} Z" fill="{coul}"/>')
            if v is not None:
                o.append(f'<text x="{mg + w + 4:.1f}" y="{y + bh - 1}" font-size="9.5" fill="#344054">'
                         f'{escape(nb(v, 0 if float(v).is_integer() else 1))}</text>')
            o.append("</g>")
    if ref is not None:
        x = mg + pw * ref / maxi
        o.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{mh - 4}" y2="{bas}" stroke="#B42318" stroke-dasharray="4 3"/>'
                 f'<text x="{x + 3:.1f}" y="{mh - 6 if mh > 12 else bas + 13}" font-size="9.5" fill="#B42318">'
                 f'seuil {escape(nb(ref, 0))}{escape(suffixe)}</text>')
    o.append(f'<line x1="{mg}" x2="{mg}" y1="{mh}" y2="{bas}" stroke="#98A2B3"/></svg>')
    return Markup("".join(o))


def pdf_barres(categories, series, largeur, hauteur=48 * 2.835 * 1.0, maxi=100, titre=""):
    """Petit graphique en barres pour les PDF (Drawing ReportLab)."""
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib import colors
    d = Drawing(largeur, hauteur)
    mg, mb, mh = 24, 16, 22
    ph, pw = hauteur - mb - mh, largeur - mg - 6
    vals = [v for s in series for v in s[2] if v is not None]
    vmax = maxi or _max_arrondi(max(vals + [1]))
    d.add(String(mg, hauteur - 9, titre, fontName="Helvetica-Bold", fontSize=8))
    x = largeur - 6
    for nom, coul, _ in reversed(series):
        x -= 8 + 4.2 * len(nom) + 12
        d.add(Rect(x, hauteur - 10, 7, 7, fillColor=colors.HexColor(coul), strokeColor=None))
        d.add(String(x + 9, hauteur - 9.5, nom, fontName="Helvetica", fontSize=7))
    for k in range(5):
        y = mb + ph * k / 4
        d.add(Line(mg, y, mg + pw, y, strokeColor=colors.HexColor("#EAECF0"), strokeWidth=0.5))
        d.add(String(mg - 3, y - 2.5, nb(vmax * k / 4, 0), fontName="Helvetica", fontSize=6.5, textAnchor="end"))
    n = len(series)
    gw = pw / max(1, len(categories))
    bw = min(16, (gw * 0.7 - 1.5 * (n - 1)) / n)
    for i, cat in enumerate(categories):
        x0 = mg + i * gw + (gw - (n * bw + 1.5 * (n - 1))) / 2
        for j, (nom, coul, valeurs) in enumerate(series):
            v = valeurs[i] or 0
            h = ph * min(v, vmax) / vmax if vmax else 0
            if h > 0:
                d.add(Rect(x0 + j * (bw + 1.5), mb, bw, h, fillColor=colors.HexColor(coul), strokeColor=None))
            d.add(String(x0 + j * (bw + 1.5) + bw / 2, mb + h + 2, nb(v, 0 if float(v).is_integer() else 1),
                         fontName="Helvetica", fontSize=6, textAnchor="middle"))
        lib = str(cat) if len(str(cat)) <= 14 else str(cat)[:13] + "…"
        d.add(String(mg + i * gw + gw / 2, mb - 9, lib, fontName="Helvetica", fontSize=6.5, textAnchor="middle"))
    d.add(Line(mg, mb, mg + pw, mb, strokeColor=colors.HexColor("#98A2B3"), strokeWidth=0.7))
    return d


# ================================================================== analyse rédigée automatiquement
def _niveau_taux(t):
    if t >= 75:
        return "très satisfaisant"
    if t >= 50:
        return "satisfaisant"
    if t >= 25:
        return "faible"
    return "très faible"


def _liste(noms):
    noms = list(noms)
    if not noms:
        return ""
    return noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]


def rediger(cl, ev, matieres, lignes, s):
    """Texte automatique : profil de la classe, analyse psychopédagogique, recommandations.
    Règles explicites (seuils affichés dans l'aide de la page) :
    * niveau du taux de maîtrise : ≥ 75 % très satisfaisant, ≥ 50 % satisfaisant, ≥ 25 % faible, sinon très faible ;
    * écart filles/garçons significatif à partir de 5 points ; matière à renforcer si taux < 50 % ;
    * dispersion (écart-type) : < 2 homogène, 2 à 3,5 modérée, > 3,5 forte ; absentéisme préoccupant > 10 %."""
    V = vocab(cl)
    ins, comp, abs_ = s["inscrits"], s["composes"], s["absents"]
    tx = s["taux_reussite"]
    nom_ev = ev["titre"]
    if not ins["T"]:
        vide = f"La classe de {cl['nom']} ne compte aucun élève inscrit : aucune analyse n'est possible."
        return {"profil": vide, "analyse": vide, "recommandations": "- Inscrire les élèves puis saisir les notes."}
    if not comp["T"]:
        t = (f"La classe de {cl['nom']} compte {ins['T']} élève(s) inscrit(s) ({ins['G']} garçon(s), {ins['F']} fille(s)). "
             f"Aucune note n'a encore été saisie pour l'{nom_ev.lower()} : les statistiques ne sont pas disponibles.")
        return {"profil": t, "analyse": "Analyse impossible tant que les notes ne sont pas saisies.",
                "recommandations": "- Saisir les notes de l'évaluation, puis revenir sur cette page."}

    # ---------------------------------------------------------- 1. profil
    p = [f"La classe de {cl['nom']} ({cl['niveau']}) compte {ins['T']} élève(s) inscrit(s) : {ins['G']} garçon(s) "
         f"et {ins['F']} fille(s). À l'{nom_ev.lower()}, {comp['T']} élève(s) ont composé, soit un taux de "
         f"participation de {pc(s['participation']['T'])}"
         + (f" ; {abs_['T']} absent(s) ({abs_['G']} G, {abs_['F']} F)." if abs_["T"] else " ; aucun absent.")]
    p.append(f"{s['reussis']['T']} élève(s) {V['ont']} ({V['regle']}), soit un taux de {V['reussite']} de "
             f"{pc(tx['T'])} (garçons : {pc(tx['G'])} ; filles : {pc(tx['F'])}). Ce résultat est "
             f"{_niveau_taux(tx['T'])}.")
    if s["moyenne"]["T"] is not None:
        p.append(f"La moyenne générale de la classe est de {nb(s['moyenne']['T'])}/20 (garçons : "
                 f"{nb(s['moyenne']['G'])} ; filles : {nb(s['moyenne']['F'])}), avec un écart-type de "
                 f"{nb(s['ecart_type']['T'])}. La plus forte moyenne est {nb(s['plus_forte_moyenne'])} et la plus "
                 f"faible {nb(s['plus_faible_moyenne'])}.")
        tr = {t["libelle"]: t for t in s["tranches"]}
        p.append(f"Répartition : {tr['≥ 15']['T']} élève(s) à 15 et plus, {tr['12 à 14,99']['T']} entre 12 et 14,99, "
                 f"{tr['10 à 11,99']['T']} entre 10 et 11,99, {tr['< 10']['T']} en dessous de 10 dont "
                 f"{tr['dont < 8']['T']} en dessous de 8.")
    profil = "\n".join(p)

    # ---------------------------------------------------------- 2. analyse psychopédagogique
    a = []
    renf = EC.a_renforcer(s)
    et = s["ecart_type"]["T"]
    if et is not None and s["moyenne"]["T"] is not None:
        if et < 2:
            a.append(f"La classe est homogène (écart-type {nb(et)} < 2) : les élèves progressent à un rythme voisin.")
        elif et <= 3.5:
            a.append(f"La dispersion des moyennes est modérée (écart-type {nb(et)}) : un noyau d'élèves suit "
                     "bien, tandis qu'un groupe avance plus lentement.")
        else:
            a.append(f"La classe est très hétérogène (écart-type {nb(et)} > 3,5) : les rythmes d'apprentissage "
                     "sont très différents, ce qui appelle une pédagogie différenciée.")
    if comp["G"] and comp["F"]:
        ecart = round(tx["F"] - tx["G"], 2)
        if abs(ecart) < 5:
            a.append(f"Les filles et les garçons réussissent de manière comparable (écart de {nb(abs(ecart))} "
                     "point(s)) : la parité est atteinte.")
        else:
            qui, autre = ("filles", "garçons") if ecart > 0 else ("garçons", "filles")
            a.append(f"Les {qui} réussissent mieux que les {autre} (écart de {nb(abs(ecart))} points) : il faut "
                     f"rechercher les causes (participation en classe, confiance en soi, conditions d'étude à la "
                     f"maison) et soutenir davantage les {autre}.")
        grands = [d["matiere"]["nom"] for d in s["par_matiere"]
                  if d["G"]["composes"] and d["F"]["composes"] and abs(d["G"]["taux"] - d["F"]["taux"]) >= 25]
        if grands:
            a.append(f"Écarts importants entre filles et garçons (25 points ou plus) en : {_liste(grands)}.")
    else:
        a.append("La comparaison filles / garçons n'est pas possible : un des deux groupes n'a pas composé.")
    fo, fa = s["forte"]["T"], s["faible"]["T"]
    if fo and fa and fo["matiere"] != fa["matiere"]:
        a.append(f"Les apprentissages sont les mieux consolidés en {fo['matiere']} (moyenne {nb(fo['moyenne'])}, "
                 f"{pc(fo['taux'])} de réussite) ; les difficultés se concentrent en {fa['matiere']} "
                 f"(moyenne {nb(fa['moyenne'])}, {pc(fa['taux'])} de réussite).")
    if renf:
        a.append(f"Matière(s) à renforcer (moins de 50 % de réussite) : {_liste(renf)}.")
    elif any(d["T"]["composes"] for d in s["par_matiere"]):
        a.append("Aucune matière n'a un taux de réussite inférieur à 50 %.")
    tr8 = next((t for t in s["tranches"] if t["libelle"] == "dont < 8"), None)
    if tr8 and tr8["T"]:
        a.append(f"{tr8['T']} élève(s) ont une moyenne inférieure à 8/20 : ils sont en grande difficulté et "
                 "risquent le découragement ; un accompagnement individualisé est nécessaire.")
    taux_abs = 100 * abs_["T"] / ins["T"]
    if taux_abs > 10:
        a.append(f"L'absentéisme est préoccupant ({nb(taux_abs)} % d'absents) : il traduit souvent un manque de "
                 "motivation ou des difficultés familiales et compromet la continuité des apprentissages.")
    elif abs_["T"]:
        a.append(f"L'absentéisme reste limité ({nb(taux_abs)} % d'absents).")
    analyse = "\n".join(a)

    # ---------------------------------------------------------- 3. recommandations
    r = []
    for m in renf:
        r.append(f"- Organiser des séances de remédiation en {m} : reprise des notions de base, exercices gradués, "
                 "travail en petits groupes de besoin.")
    if et is not None and et > 3.5:
        r.append("- Pratiquer une pédagogie différenciée : groupes de niveau, tutorat entre pairs, consignes adaptées.")
    if tr8 and tr8["T"]:
        r.append(f"- Mettre en place un suivi individualisé des {tr8['T']} élève(s) ayant moins de 8/20 et rencontrer "
                 "leurs parents.")
    if comp["G"] and comp["F"] and abs(tx["F"] - tx["G"]) >= 5:
        moins = "garçons" if tx["F"] > tx["G"] else "filles"
        r.append(f"- Veiller à la participation des {moins} : questionnement équitable, encouragements, "
                 "responsabilités dans la classe.")
    if taux_abs > 10:
        r.append("- Sensibiliser les parents à l'assiduité et suivre les absences au registre d'appel.")
    if tx["T"] >= 75:
        r.append("- Maintenir le rythme de travail et proposer des activités d'approfondissement aux meilleurs élèves.")
    elif tx["T"] < 50:
        r.append("- Revoir la programmation : consolider les acquis avant d'aborder de nouvelles notions ; "
                 "multiplier les évaluations formatives courtes.")
    r.append("- Informer les parents des résultats (bulletins, réunion) et en débattre en conseil des maîtres.")
    return {"profil": profil, "analyse": analyse, "recommandations": "\n".join(r)}


def paragraphes_pdf(H, texte):
    """Texte multi-lignes -> Paragraphs (les lignes « - » deviennent des puces)."""
    out = []
    for ligne in (texte or "").replace("\r", "").split("\n"):
        ligne = ligne.strip()
        if not ligne:
            continue
        if ligne[:1] in "-•":
            out.append(H.pdfs.paragraphe("• " + esc(ligne[1:].strip()), 8.5, espace=1))
        else:
            out.append(H.pdfs.paragraphe(esc(ligne), 8.5, align=4, espace=2))
    return out


# ================================================================== enregistrement du module
def enregistrer(app, H):
    q = H.q
    app.add_template_filter(nb, "res_nb")
    app.add_template_filter(pc, "res_pc")

    # ------------------------------------------------------------ sélection classe / évaluation
    def choisir(avec_ev=True):
        """Lit ?classe= et ?ev= (GET ou POST). Retourne (classes, classe, evaluations, evaluation)."""
        classes = H.classes_autorisees()
        cid = request.values.get("classe", type=int)
        if not cid and len(classes) == 1:
            cid = classes[0]["id"]
        cl, evs, ev = None, [], None
        if cid:
            H.verifier_classe(cid)
            cl = H.classe_ou_404(cid)
            evs = EC.evaluations_classe(cid)
            if avec_ev:
                brut = request.values.get("ev", "")
                if brut.isdigit():
                    ev = next((e for e in evs if e["id"] == int(brut)), None)
                    if ev is None:
                        abort(404)
                elif evs:  # par défaut : la plus récente ayant des notes (sinon la plus récente)
                    notees = {r["periode"] for r in q(
                        "SELECT DISTINCT n.periode FROM notes n JOIN eleves e ON e.id = n.eleve_id "
                        "WHERE e.classe_id=? AND n.annee=?", (cid, H.config.ANNEE_ACTIVE))}
                    ev = next((e for e in reversed(evs) if e["libelle"] in notees), evs[-1])
        return classes, cl, evs, ev

    def calculer(ev, cl):
        matieres, lignes = EC.resultats(ev, cl)
        return matieres, lignes, EC.statistiques(matieres, lignes)

    # ------------------------------------------------------------ en-têtes (M.identification) et signatures
    def cle_entete(cl):
        """Clé (sans préfixe école) de l'en-tête enregistré par la barre « Sauvegarder » des pages du module."""
        return f"resultats_entete:{cl['id']}"

    def ident(cl):
        """Valeurs d'en-tête : défauts de l'école/classe (H.identification), puis en-tête enregistré pour la
        classe, puis valeurs envoyées par le formulaire (GET ou POST)."""
        v = H.identification(cl)
        enr = H.doc_lire(f"e{H.eco()}:{cle_entete(cl)}") or {}
        sources = [enr, request.values]
        for src in sources:
            for k in CHAMPS_ID:
                val = src.get(k)
                if isinstance(val, str) and val.strip():
                    v[k] = val.strip()[:120]
        if not RE_ANNEE.match(v.get("annee") or ""):
            v["annee"] = H.config.ANNEE_ACTIVE
        return v

    def haut_pdf(v):
        """Colonne gauche de l'en-tête des PDF tabulaires."""
        return [("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))]

    def img_titulaire(cl):
        return H.pdfs.image_data_url(H.signature(f"classe:{cl['id']}:titulaire"))

    def img_directeur():
        return H.pdfs.image_data_url(H.signature(f"ecole:{H.eco()}:directeur")) or H.pdfs.signature_directeur()

    def signatures_std(cl, v, avec_titulaire=True):
        """Signatures titulaire (image digitale éventuelle) + directeur(trice) avec cachet de l'école."""
        sig = []
        if avec_titulaire and cl:
            sig.append((v.get("titulaire_titre") or "Le titulaire", v.get("titulaire_nom") or "", img_titulaire(cl), False))
        sig.append((titre_directeur(v.get("directeur_titre")), v.get("directeur_nom") or "", img_directeur(), True))
        return sig

    def infos_ev(cl, ev, v):
        seuil = "—"
        if cl["cycle"] == "primaire":
            n = len(EC.matieres_de(ev, cl))
            seuil = f"{EC.seuil_de(ev, n)} matière(s) sur {n} à 10/20"
        elif cl["cycle"] == "secondaire":
            seuil = "moyenne ≥ 10/20"
        else:
            seuil = "appréciations A / ECA / NA"
        return [("Classe", f"{cl['nom']} ({v.get('cours') or cl['niveau']})"), ("Évaluation", ev["titre"]),
                ("Date", H.pdfs.date_fr(ev["date"]) if ev.get("date") else "—"), ("Année scolaire", v["annee"]),
                ("Seuil de réussite", seuil),
                ("Titulaire", f"{v.get('titulaire_titre') or ''} {v.get('titulaire_nom') or '—'}".strip())]

    # ================================================================ A. STATISTIQUES
    def fmt(brut):
        """(format nombre, format pourcentage) : à la française pour l'écran et le PDF, bruts pour Excel."""
        if brut:
            return (lambda v: v), (lambda v: v)
        return nb, pc

    def lignes_indicateurs(s, cl, brut=False):
        f_nb, f_pc = fmt(brut)
        V = vocab(cl)
        L = [("Inscrits", "inscrits", False), ("Ont composé", "composes", False), ("Absents", "absents", False),
             ("Taux de participation", "participation", True), (f"Ont réussi ({V['ok'].lower()})", "reussis", False),
             ("Échecs", "echecs", False), (V["taux"], "taux_reussite", True), ("Taux d'échec", "taux_echec", True)]
        out = []
        for lib, cle, est_pct in L:
            out.append([lib] + [f_pc(s[cle][k]) if est_pct else s[cle][k] for k, _ in SEXES])
        if cl["cycle"] != "maternelle":
            out.append(["Moyenne de la classe"] + [f_nb(s["moyenne"][k]) for k, _ in SEXES])
            out.append(["Écart-type"] + [f_nb(s["ecart_type"][k]) for k, _ in SEXES])
        return out

    def lignes_tranches(s, brut=False):
        _, f_pc = fmt(brut)
        return [[t["libelle"]] + sum(([t[k], f_pc(t["pct"][k])] for k, _ in SEXES), []) for t in s["tranches"]]

    def lignes_extremes(s, brut=False):
        f_nb, _ = fmt(brut)
        vide = None if brut else "—"
        out = []
        for k, lib in (("T", "Ensemble de la classe"), ("G", "Garçons"), ("F", "Filles")):
            fo, fa = s["forte"][k], s["faible"][k]
            out.append([lib, fo["matiere"] if fo else vide, f_nb(fo["moyenne"]) if fo else vide,
                        fa["matiere"] if fa else vide, f_nb(fa["moyenne"]) if fa else vide])
        return out

    ENT_MATIERES = ["Matière", "Ont composé G", "Ont composé F", "Ont composé T", "% particip. G", "% particip. F",
                    "% particip. T", "Ont réussi G", "Ont réussi F", "Ont réussi T", "% réussite G", "% réussite F",
                    "% réussite T", "Moyenne G", "Moyenne F", "Moyenne T", "Observation"]

    def lignes_matieres(s, brut=False):
        """Participation et réussite (note ≥ 10) par matière et par sexe."""
        f_nb, f_pc = fmt(brut)
        vide = None if brut else "—"
        renf = set(EC.a_renforcer(s))
        ins = s["inscrits"]
        out = []
        for d in s["par_matiere"]:
            out.append([d["matiere"]["nom"]] + [d[k]["composes"] for k, _ in SEXES]
                       + [f_pc(EC._pct(d[k]["composes"], ins[k])) if ins[k] else vide for k, _ in SEXES]
                       + [d[k]["reussis"] for k, _ in SEXES]
                       + [f_pc(d[k]["taux"]) if d[k]["composes"] else vide for k, _ in SEXES]
                       + [f_nb(d[k]["moyenne"]) for k, _ in SEXES]
                       + ["À renforcer" if d["matiere"]["nom"] in renf else ""])
        return out

    def repartition_maternelle(matieres, lignes):
        """Maternelle : nombre d'appréciations A / ECA / NA par domaine et par sexe."""
        out = []
        for m in matieres:
            d = {"matiere": m}
            for k, sx in (("G", "M"), ("F", "F"), ("T", None)):
                ap = [l["appreciations"].get(m["id"]) for l in lignes if sx is None or l["eleve"]["sexe"] == sx]
                ap = [a for a in ap if a]
                d[k] = {a: ap.count(a) for a in ("A", "ECA", "NA")}
                d[k]["n"] = len(ap)
                d[k]["pct_A"] = EC._pct(d[k]["A"], len(ap))
            out.append(d)
        return out

    ENT_MATERNELLE = ["Domaine", "A (G)", "ECA (G)", "NA (G)", "A (F)", "ECA (F)", "NA (F)", "A (T)", "ECA (T)",
                      "NA (T)", "% A (T)"]

    def lignes_maternelle(rep, brut=False):
        _, f_pc = fmt(brut)
        return [[d["matiere"]["nom"]] + [d[k][a] for k in "GFT" for a in ("A", "ECA", "NA")]
                + [f_pc(d["T"]["pct_A"]) if d["T"]["n"] else (None if brut else "—")] for d in rep]

    def graphiques(s, rep=None):
        cats = ["Garçons", "Filles", "Ensemble"]
        g1 = svg_barres(cats, [("Réussite", COUL["T"], [s["taux_reussite"][k] for k in "GFT"]),
                               ("Échec", "#98A2B3", [s["taux_echec"][k] for k in "GFT"])],
                        titre="Taux de réussite et d'échec par sexe (%)", maxi=100)
        tr = s["tranches"]
        g2 = svg_barres([t["libelle"] for t in tr], [("Garçons", COUL["G"], [t["G"] for t in tr]),
                                                     ("Filles", COUL["F"], [t["F"] for t in tr])],
                        titre="Répartition des élèves par tranche de moyenne (effectifs)", suffixe=" élève(s)")
        pm = [d for d in s["par_matiere"] if d["T"]["composes"]]
        g3 = svg_barres_h([d["matiere"]["nom"] for d in pm],
                          [("Garçons", COUL["G"], [d["G"]["taux"] if d["G"]["composes"] else None for d in pm]),
                           ("Filles", COUL["F"], [d["F"]["taux"] if d["F"]["composes"] else None for d in pm]),
                           ("Total", COUL["T"], [d["T"]["taux"] for d in pm])],
                          titre="Taux de réussite par matière (%)", ref=50)
        g4 = svg_barres_h([d["matiere"]["nom"] for d in pm],
                          [("Garçons", COUL["G"], [d["G"]["moyenne"] for d in pm]),
                           ("Filles", COUL["F"], [d["F"]["moyenne"] for d in pm]),
                           ("Total", COUL["T"], [d["T"]["moyenne"] for d in pm])],
                          titre="Moyenne par matière et par sexe (/20)", maxi=20, ref=10, suffixe="/20")
        g5 = Markup("")
        if rep:
            rr = [d for d in rep if d["T"]["n"]]
            g5 = svg_barres_h([d["matiere"]["nom"] for d in rr],
                              [("A (acquis)", COUL["T"], [EC._pct(d["T"]["A"], d["T"]["n"]) for d in rr]),
                               ("ECA", "#E0A526", [EC._pct(d["T"]["ECA"], d["T"]["n"]) for d in rr]),
                               ("NA", "#98A2B3", [EC._pct(d["T"]["NA"], d["T"]["n"]) for d in rr])],
                              titre="Appréciations par domaine (%)")
        return {"sexe": g1, "tranches": g2, "matieres": g3, "moyennes": g4, "maternelle": g5}

    @app.route("/statistiques-evaluation")
    @H.connexion_requise("evaluations")
    def eval_statistiques():
        classes, cl, evs, ev = choisir()
        ctx = dict(classes=classes, cl=cl, evs=evs, ev=ev, SEXES=SEXES)
        if cl:
            ctx.update(v=ident(cl), cle_entete=cle_entete(cl))
        if cl and ev:
            matieres, lignes, s = calculer(ev, cl)
            rep = repartition_maternelle(matieres, lignes) if cl["cycle"] == "maternelle" else None
            ctx.update(matieres=matieres, lignes=lignes, s=s, V=vocab(cl), renf=EC.a_renforcer(s),
                       graph=graphiques(s, rep), merite=EC.ordre_de_merite(lignes),
                       ind=lignes_indicateurs(s, cl), tranches=lignes_tranches(s), extremes=lignes_extremes(s),
                       par_mat=lignes_matieres(s), rep=rep, lignes_mat=lignes_maternelle(rep) if rep else None,
                       ENT_MATERNELLE=ENT_MATERNELLE, infos=infos_ev(cl, ev, ctx["v"]))
        return render_template("resultats_eval_statistiques.html", **ctx)

    def exiger_ev():
        classes, cl, evs, ev = choisir()
        if not cl or not ev:
            flash("Choisissez d'abord une classe et une évaluation.", "warning")
            return None
        return cl, ev

    @app.route("/statistiques-evaluation/pdf")
    @H.connexion_requise("evaluations")
    def eval_statistiques_pdf():
        r = exiger_ev()
        if not r:
            return redirect(url_for("eval_statistiques"))
        cl, ev = r
        v = ident(cl)
        matieres, lignes, s = calculer(ev, cl)
        P = H.pdfs
        from reportlab.lib.units import mm
        from reportlab.platypus import Spacer, Table
        m = lambda data, larg: P.mini_tableau([[esc(x) for x in row] for row in data], larg)  # noqa: E731
        ind = m([["Indicateur", "Garçons", "Filles", "Total"]] + lignes_indicateurs(s, cl), [64 * mm, 28 * mm, 28 * mm, 28 * mm])
        mat = cl["cycle"] == "maternelle"
        gr1 = pdf_barres(["Garçons", "Filles", "Ensemble"],
                         [("Réussite", COUL["T"], [s["taux_reussite"][k] for k in "GFT"]),
                          ("Échec", "#98A2B3", [s["taux_echec"][k] for k in "GFT"])],
                         120 * mm, 45 * mm, 100, "Taux de réussite / d'échec (%)")
        if mat:
            rep = repartition_maternelle(matieres, lignes)
            cote = Table([[ind, gr1]], colWidths=[160 * mm, 110 * mm])
            cote.setStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])
            avant = [P.paragraphe("1. Participation et progrès des élèves", 9.5, True), cote,
                     P.paragraphe("2. Appréciations par domaine (A = acquis, ECA = en cours d'acquisition, "
                                  "NA = non acquis)", 9.5, True)]
            cols = [["Domaine", "Garçons", None, None, "Filles", None, None, "Total", None, None, "% A"],
                    ["^", "A", "ECA", "NA", "A", "ECA", "NA", "A", "ECA", "NA", "^"]]
            corps, larg = lignes_maternelle(rep), [60] + [12] * 9 + [16]
            notes = ["Maternelle : pas de moyenne chiffrée ; progrès satisfaisants si au moins la moitié des points "
                     "(A = 2, ECA = 1, NA = 0). Absent = aucune appréciation saisie."]
        else:
            tra = m([["Tranche de moyenne", "G", "% G", "F", "% F", "Total", "% T"]] + lignes_tranches(s),
                    [26 * mm] + [14 * mm] * 6)
            ext = m([["", "Matière la plus forte", "Moy.", "Matière la plus faible", "Moy."]] + lignes_extremes(s),
                    [40 * mm, 62 * mm, 16 * mm, 62 * mm, 16 * mm])
            gr2 = pdf_barres([t["libelle"] for t in s["tranches"]],
                             [("Garçons", COUL["G"], [t["G"] for t in s["tranches"]]),
                              ("Filles", COUL["F"], [t["F"] for t in s["tranches"]])], 120 * mm, 45 * mm, None,
                             "Répartition par tranches (effectifs)")
            cote = Table([[ind, tra]], colWidths=[155 * mm, 115 * mm])
            cote.setStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])
            graphes = Table([[gr1, gr2]], colWidths=[135 * mm, 135 * mm])
            avant = [P.paragraphe("1. Participation, réussite, moyennes et répartition par tranches", 9.5, True), cote,
                     Spacer(1, 4), graphes,
                     P.paragraphe("2. Matière la plus forte et matière la plus faible", 9.5, True), ext,
                     P.paragraphe("3. Participation et réussite par matière et par sexe (réussite = note ≥ 10/20)",
                                  9.5, True)]
            cols = [["Matière", "Ont composé", None, None, "% participation", None, None, "Ont réussi", None, None,
                     "% de réussite", None, None, "Moyenne", None, None, "Obs."],
                    ["^"] + ["G", "F", "T"] * 5 + ["^"]]
            corps, larg = lignes_matieres(s), [44] + [9] * 3 + [12] * 3 + [9] * 3 + [12] * 3 + [11] * 3 + [18]
            renf = EC.a_renforcer(s)
            notes = [f"Matière(s) à renforcer (réussite &lt; 50 %) : {esc(_liste(renf)) or 'aucune'}.",
                     f"Réussite de l'évaluation : {esc(vocab(cl)['regle'])}. Absent = aucune note saisie. "
                     "% participation = élèves notés / inscrits."]
        pdf = P.pour_cycle(dict(cl).get("cycle"))(
            f"STATISTIQUES DE L'{ev['titre'].upper()}", cols, corps,
            sous_titre=f"Classe : {cl['nom']} — Année scolaire {v['annee']}", infos=infos_ev(cl, ev, v),
            infos_haut=haut_pdf(v), largeurs=larg, paysage=True, avant=avant, notes_bas=notes,
            signatures=signatures_std(cl, v), taille=7)
        H.journal("stats_evaluation_pdf", f"{cl['nom']} {ev['libelle']}")
        return H.pdf_reponse(pdf, f"statistiques_{cl['nom']}_{ev['libelle']}.pdf".replace(" ", "_"))

    @app.route("/statistiques-evaluation/excel")
    @H.connexion_requise("evaluations")
    def eval_statistiques_xlsx():
        r = exiger_ev()
        if not r:
            return redirect(url_for("eval_statistiques"))
        cl, ev = r
        v = ident(cl)
        matieres, lignes, s = calculer(ev, cl)
        haut = [f"{v['ecole']} — Statistiques de l'{ev['titre'].lower()}",
                f"Classe : {cl['nom']} — Année scolaire {v['annee']} — DDEMP : {v['ddemp'] or '—'} — CS : {v['cs'] or '—'}"]
        mat = cl["cycle"] == "maternelle"
        eleves = []
        for l in sorted(lignes, key=lambda l: (l["rang"] is None, l["rang"] or 0, l["eleve"]["nom"], l["eleve"]["prenoms"])):
            vals = ([l["appreciations"].get(m["id"]) for m in matieres] if mat else [l["notes"].get(m["id"]) for m in matieres])
            eleves.append([l["rang_texte"], l["eleve"]["nom"], l["eleve"]["prenoms"], l["eleve"]["sexe"], l["moyenne"],
                           f"{l['reussies']}/{l['nb_notes']}" if not mat else l["nb_notes"], l["decision"]] + vals)
        feuilles = [("Indicateurs", ["Indicateur", "Garçons", "Filles", "Total"], lignes_indicateurs(s, cl, True),
                     {"titre_haut": haut})]
        if mat:
            feuilles.append(("Domaines", ENT_MATERNELLE, lignes_maternelle(repartition_maternelle(matieres, lignes), True),
                             {"titre_haut": haut}))
        else:
            feuilles += [
                ("Tranches", ["Tranche", "G", "% G", "F", "% F", "Total", "% T"], lignes_tranches(s, True), {"titre_haut": haut}),
                ("Forte-faible", ["", "Matière la plus forte", "Moyenne", "Matière la plus faible", "Moyenne"],
                 lignes_extremes(s, True), {"titre_haut": haut}),
                ("Par matière", ENT_MATIERES, lignes_matieres(s, True), {"titre_haut": haut})]
        feuilles.append(("Élèves", ["Rang", "Nom", "Prénoms", "Sexe", "Moyenne",
                                    "Appréciations saisies" if mat else "Matières ≥ 10", "Décision"]
                         + [m["nom"] for m in matieres], eleves, {"titre_haut": haut}))
        try:
            return H.xlsx.reponse_classeur(f"statistiques_{cl['nom']}_{ev['libelle']}.xlsx".replace(" ", "_"), feuilles)
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return redirect(url_for("eval_statistiques", classe=cl["id"], ev=ev["id"]))

    # ================================================================ B. ANALYSE ET RAPPORT
    def cle_analyse(cl, ev):
        return f"resultats_analyse:{cl['id']}:{ev['id']}"

    @app.route("/analyse-evaluation")
    @H.connexion_requise("evaluations")
    def eval_analyse():
        classes, cl, evs, ev = choisir()
        ctx = dict(classes=classes, cl=cl, evs=evs, ev=ev)
        if cl and ev:
            matieres, lignes, s = calculer(ev, cl)
            cle = cle_analyse(cl, ev)
            auto = rediger(cl, ev, matieres, lignes, s)
            enr = H.doc_lire(f"e{H.eco()}:{cle}") or {}
            ligne_enr = q("SELECT maj FROM documents_modules WHERE cle=?", (f"e{H.eco()}:{cle}",), un=True)
            textes = dict(auto)
            regenere = bool(request.args.get("auto"))
            if not regenere:  # texte déjà retouché et enregistré : on le reprend
                for k in textes:
                    if isinstance(enr.get(k), str) and enr[k].strip():
                        textes[k] = enr[k]
            v = ident(cl)
            for k in CHAMPS_ID:
                if isinstance(enr.get(k), str) and enr[k].strip() and k not in request.args:
                    v[k] = enr[k].strip()[:120]
            if regenere and enr:
                flash("Texte automatique régénéré à partir des statistiques actuelles. Cliquez sur « Sauvegarder » "
                      "pour remplacer le texte enregistré.", "info")
            ctx.update(s=s, V=vocab(cl), textes=textes, auto=auto, cle=cle, repris=(textes != auto),
                       enregistre=ligne_enr["maj"] if ligne_enr else None, v=v, renf=EC.a_renforcer(s),
                       graph=graphiques(s))
        return render_template("resultats_eval_analyse.html", **ctx)

    @app.route("/analyse-evaluation/pdf", methods=["POST"])
    @H.connexion_requise("evaluations")
    def eval_analyse_pdf():
        r = exiger_ev()
        if not r:
            return redirect(url_for("eval_analyse"))
        cl, ev = r
        v = ident(cl)
        matieres, lignes, s = calculer(ev, cl)
        auto = rediger(cl, ev, matieres, lignes, s)
        f = request.form
        textes = {k: (f.get(k) or "").strip()[:20000] or auto[k] for k in ("profil", "analyse", "recommandations")}
        P = H.pdfs
        from reportlab.lib.units import mm
        apres = [pdf_barres(["Garçons", "Filles", "Ensemble"],
                            [("Réussite", COUL["T"], [s["taux_reussite"][k] for k in "GFT"]),
                             ("Échec", "#98A2B3", [s["taux_echec"][k] for k in "GFT"])],
                            110 * mm, 40 * mm, 100, "Taux de réussite / d'échec par sexe (%)")]
        for titre, k in (("1. Profil de la classe", "profil"), ("2. Analyse psychopédagogique", "analyse"),
                         ("3. Recommandations pédagogiques", "recommandations")):
            apres.append(P.paragraphe(titre, 10, True, espace=5))
            apres += paragraphes_pdf(H, textes[k])
        pdf = P.pour_cycle(dict(cl).get("cycle"))(
            "ANALYSE ET RAPPORT DES RÉSULTATS", ["Indicateur", "Garçons", "Filles", "Total"],
            lignes_indicateurs(s, cl), sous_titre=f"{ev['titre']} — Classe : {cl['nom']} — {v['annee']}",
            infos=infos_ev(cl, ev, v), infos_haut=haut_pdf(v), largeurs=[60, 20, 20, 20], apres=apres,
            signatures=signatures_std(cl, v), taille=8)
        H.journal("analyse_evaluation_pdf", f"{cl['nom']} {ev['libelle']}")
        return H.pdf_reponse(pdf, f"rapport_{cl['nom']}_{ev['libelle']}.pdf".replace(" ", "_"))

    # ================================================================ D. BILAN ANNUEL (défini avant C : le tableau
    # d'honneur « bilan » réutilise la sélection enregistrée)
    def cle_bilan(cid):
        return f"e{H.eco()}:bilan:{cid}:{H.config.ANNEE_ACTIVE}"

    def selection_enregistree(cl, evs):
        d = H.doc_lire(cle_bilan(cl["id"])) or {}
        ids = set(d.get("evaluations") or [])
        return [e for e in evs if e["id"] in ids], d

    def selection_demandee(evs):
        ids = {int(x) for x in request.values.getlist("ev") if str(x).isdigit()}
        return [e for e in evs if e["id"] in ids]  # ordre chronologique de la classe : la dernière = E_D

    def tri_bilan(res):
        return sorted(res, key=lambda o: (o["rang"] is None, o["rang"] or 0, o["eleve"]["nom"], o["eleve"]["prenoms"]))

    def lignes_bilan(res, sel):
        out = []
        for o in tri_bilan(res):
            out.append([rang_txt(o["rang"], o["eleve"]["sexe"], o["ex_aequo"]),
                        f"{o['eleve']['nom']} {o['eleve']['prenoms']}", o["eleve"]["sexe"]]
                       + [nb(m) + ("" if not l or not l["compose"] else (" ✓" if l["maitrise"] else " ✗"))
                          for m, l in zip(o["moyennes"], o["lignes"])]
                       + [nb(o["M_O"]), nb(o["E_D"]), nb(o["M"]), f"{o['validees']}/{o['composees']} (requis {o['requis']})",
                          o["decision"]])
        return out

    def stats_bilan(res):
        S = {"G": "M", "F": "F"}
        d = {}
        for k, sx in list(S.items()) + [("T", None)]:
            grp = [o for o in res if sx is None or o["eleve"]["sexe"] == sx]
            comp = [o for o in grp if o["composees"]]
            adm = [o for o in comp if o["admis"]]
            ms = [o["M"] for o in comp if o["M"] is not None]
            d[k] = {"effectif": len(grp), "evalues": len(comp), "admis": len(adm), "non_admis": len(comp) - len(adm),
                    "taux": round(100 * len(adm) / len(comp), 2) if comp else 0.0,
                    "moyenne": round(sum(ms) / len(ms), 2) if ms else None}
        return d

    @app.route("/bilan-annuel")
    @H.connexion_requise("evaluations")
    def bilan_annuel():
        classes, cl, evs, _ = choisir(avec_ev=False)
        ctx = dict(classes=classes, cl=cl, evs=evs, sel_ids=set(), res=None, calcule=False, nb=None)
        if cl:
            ctx.update(v=ident(cl), cle_entete=cle_entete(cl), V=vocab(cl))
            enr_sel, enr = selection_enregistree(cl, evs)
            ctx["enr"] = enr if enr.get("evaluations") else None
            nb_ev = request.args.get("nb", type=int)
            if request.args.get("charger"):
                if not enr_sel:
                    flash("Aucun bilan enregistré pour cette classe.", "warning")
                else:
                    flash(f"Bilan enregistré le {enr.get('calcule_le', '—')} rechargé (recalculé avec les notes "
                          "actuelles).", "info")
                sel = enr_sel
                ctx["calcule"] = bool(sel)
            elif request.args.get("vider"):
                sel = []
                flash("Sélection réinitialisée : cochez les évaluations à prendre en compte.", "info")
            elif "ev" in request.args or request.args.get("calculer"):
                sel = selection_demandee(evs)
                ctx["calcule"] = True
                if not sel:
                    flash("Cochez au moins une évaluation.", "warning")
                elif nb_ev and nb_ev != len(sel):
                    flash(f"Vous avez indiqué {nb_ev} évaluation(s) mais coché {len(sel)} : le bilan porte sur les "
                          f"{len(sel)} évaluation(s) cochée(s).", "warning")
            elif nb_ev is not None:  # « nombre d'évaluations » : on coche les N dernières
                sel = evs[-nb_ev:] if nb_ev > 0 else []
            else:
                sel = list(evs)
            ctx["sel_ids"] = {e["id"] for e in sel}
            ctx["nb"] = len(sel)
            if ctx["calcule"] and sel:
                res = EC.bilan_annuel(cl, sel)
                ctx.update(res=res, sel=sel, lignes=lignes_bilan(res, sel), st=stats_bilan(res),
                           tries=tri_bilan(res))
        return render_template("bilan_annuel.html", **ctx)

    def exiger_bilan():
        classes, cl, evs, _ = choisir(avec_ev=False)
        if not cl:
            abort(404)
        sel = selection_demandee(evs)
        if not sel:
            flash("Cochez au moins une évaluation pour le bilan annuel.", "warning")
            return cl, None, None
        return cl, sel, EC.bilan_annuel(cl, sel)

    def retour_bilan(cl):
        return redirect(url_for("bilan_annuel", classe=cl["id"]))

    @app.route("/bilan-annuel/sauvegarder", methods=["POST"])
    @H.connexion_requise("evaluations")
    def bilan_sauver():
        cl, sel, res = exiger_bilan()
        if not sel:
            return retour_bilan(cl)
        H.doc_ecrire(cle_bilan(cl["id"]), {
            "evaluations": [e["id"] for e in sel], "libelles": [e["libelle"] for e in sel],
            "calcule_le": H.maintenant(), "par": g.user["nom"],
            "decisions": {str(o["eleve"]["id"]): {"M_O": o["M_O"], "E_D": o["E_D"], "M": o["M"], "rang": o["rang"],
                                                  "validees": o["validees"], "composees": o["composees"],
                                                  "decision": o["decision"]} for o in res}})
        # l'en-tête saisi (DDEMP, CS, école…) est enregistré avec, pour les prochains documents de la classe
        entete = {k: request.form.get(k, "").strip()[:120] for k in CHAMPS_ID if request.form.get(k, "").strip()}
        if entete:
            anc = H.doc_lire(f"e{H.eco()}:{cle_entete(cl)}") or {}
            anc.update(entete)
            H.doc_ecrire(f"e{H.eco()}:{cle_entete(cl)}", anc)
        H.journal("bilan_annuel_sauvegarde", f"{cl['nom']} : {', '.join(e['libelle'] for e in sel)}")
        flash(f"Bilan annuel enregistré ({len(sel)} évaluation(s), {sum(1 for o in res if o['admis'])} admis).", "success")
        return redirect(url_for("bilan_annuel", classe=cl["id"], charger=1))

    @app.route("/bilan-annuel/pdf")
    @H.connexion_requise("evaluations")
    def bilan_pdf():
        cl, sel, res = exiger_bilan()
        if not sel:
            return retour_bilan(cl)
        v = ident(cl)
        st = stats_bilan(res)
        P = H.pdfs
        from reportlab.lib.units import mm
        n = len(sel)
        cols = [["Rang", "Nom et prénoms", "Sexe", "Moyennes des évaluations"] + [None] * (n - 1)
                + ["M_O", "E_D", "M annuelle", "Évaluations validées", "Décision"],
                ["^", "^", "^"] + [e["libelle"] for e in sel] + ["^"] * 5]
        synth = P.mini_tableau(
            [["", "Garçons", "Filles", "Total"]]
            + [[lib] + [esc(f(st[k])) for k in "GFT"] for lib, f in (
                ("Effectif", lambda d: d["effectif"]), ("Évalués", lambda d: d["evalues"]),
                ("Admis", lambda d: d["admis"]), ("Non admis", lambda d: d["non_admis"]),
                ("Taux d'admission", lambda d: pc(d["taux"])), ("Moyenne annuelle", lambda d: nb(d["moyenne"])))],
            [45 * mm, 25 * mm, 25 * mm, 25 * mm])
        V = vocab(cl)
        notes = [f"Formule : M = (M_O + E_D) / 2 ; M_O = moyenne des évaluations antérieures "
                 f"({esc(', '.join(e['libelle'] for e in sel[:-1])) or 'aucune'}) ; E_D = dernière évaluation "
                 f"({esc(sel[-1]['libelle'])}). ✓ = {esc(V['ok'].lower())}, ✗ = {esc(V['ko'].lower())}.",
                 f"Décision : ADMIS(E) si l'élève a validé ({esc(V['reussite'])}) au moins les 2/3 des évaluations "
                 "qu'il a composées ; sinon NON ADMIS(E) (redouble)."]
        corps = lignes_bilan(res, sel)
        surl = {i: "#ECFDF3" for i, row in enumerate(corps) if row[-1] == "ADMIS(E)"}
        pdf = P.pour_cycle(dict(cl).get("cycle"))(
            "BILAN ANNUEL ET DÉCISION DE FIN D'ANNÉE", cols, corps,
            sous_titre=f"Classe : {cl['nom']} ({v.get('cours') or cl['niveau']}) — Année scolaire {v['annee']}",
            infos_haut=haut_pdf(v),
            infos=[("Titulaire", f"{v['titulaire_titre']} {v['titulaire_nom'] or '—'}"),
                   ("Évaluations", f"{n} : " + ", ".join(e["libelle"] for e in sel)),
                   ("Admis", f"{st['T']['admis']} / {st['T']['evalues']} ({pc(st['T']['taux'])})")],
            largeurs=[12, 50, 8] + [14] * n + [12, 12, 14, 24, 22], paysage=True, notes_bas=notes,
            apres=[P.paragraphe("Synthèse", 9.5, True), synth], surlignes=surl, signatures=signatures_std(cl, v))
        H.journal("bilan_annuel_pdf", cl["nom"])
        return H.pdf_reponse(pdf, f"bilan_annuel_{cl['nom']}.pdf".replace(" ", "_"))

    @app.route("/bilan-annuel/excel")
    @H.connexion_requise("evaluations")
    def bilan_xlsx():
        cl, sel, res = exiger_bilan()
        if not sel:
            return retour_bilan(cl)
        v = ident(cl)
        entetes = ["Rang", "Nom et prénoms", "Sexe"] + [e["libelle"] for e in sel] + [
            "M_O", "E_D", "M annuelle", "Validées", "Composées", "Requis (2/3)", "Décision"]
        lignes = []
        for o in tri_bilan(res):
            lignes.append([rang_txt(o["rang"], o["eleve"]["sexe"], o["ex_aequo"]),
                           f"{o['eleve']['nom']} {o['eleve']['prenoms']}", o["eleve"]["sexe"]] + list(o["moyennes"])
                          + [o["M_O"], o["E_D"], o["M"], o["validees"], o["composees"], o["requis"], o["decision"]])
        try:
            return H.xlsx.reponse_xlsx(f"bilan_annuel_{cl['nom']}.xlsx".replace(" ", "_"), entetes, lignes, "Bilan annuel",
                                       [f"{v['ecole']} — Bilan annuel et décision",
                                        f"Classe : {cl['nom']} — {v['annee']} — M = (M_O + E_D) / 2"])
        except H.xlsx.ExcelIndisponible as e:
            flash(str(e), "danger")
            return retour_bilan(cl)

    @app.route("/bilan-annuel/bulletins")
    @H.connexion_requise("evaluations")
    def bilan_bulletins():
        cl, sel, res = exiger_bilan()
        if not sel:
            return retour_bilan(cl)
        if not res:
            flash("Aucun élève dans cette classe.", "warning")
            return retour_bilan(cl)
        seul = request.args.get("eleve", type=int)
        if seul:
            res = [o for o in res if o["eleve"]["id"] == seul] or abort(404)
        v = ident(cl)
        pdf = bulletins_annuels(H, cl, sel, res, v, img_titulaire(cl), img_directeur())
        H.journal("bulletins_annuels", f"{cl['nom']} ({len(res)})")
        return H.pdf_reponse(pdf, f"bulletins_annuels_{cl['nom']}.pdf".replace(" ", "_"))

    # ================================================================ C. TABLEAU D'HONNEUR
    MSG_DEFAUT = ("La Direction de l'école adresse ses vives et chaleureuses félicitations aux élèves ci-après, qui se "
                  "sont distingués par leur travail, leur assiduité et leur bonne conduite. Qu'ils persévèrent dans "
                  "cette voie et soient un exemple pour leurs camarades !")

    def params_honneur():
        seuil_brut = request.values.get("seuil", "12")
        try:
            seuil = float(seuil_brut.replace(",", ".")) if seuil_brut.strip() else None
            if seuil is not None and not 0 <= seuil <= 20:
                raise ValueError
        except ValueError:
            flash("Seuil de moyenne invalide (0 à 20) : seuil ignoré.", "warning")
            seuil = None
        n = request.values.get("n", type=int)
        if n is not None and n < 1:
            n = None
        msg = (request.values.get("msg") or "").strip()[:600] or MSG_DEFAUT
        return seuil, n, msg

    def honneur(cl, evs, choix, seuil, n):
        """Retourne (libellé de la source, liste retenue, nombre de candidats ayant réussi)."""
        if choix == "bilan":
            sel, _ = selection_enregistree(cl, evs)
            sel = sel or list(evs)
            if not sel:
                return None, [], 0
            res = EC.bilan_annuel(cl, sel)
            source = "Bilan annuel (" + ", ".join(e["libelle"] for e in sel) + ")"
            cand = [{"eleve": o["eleve"], "moyenne": o["M"], "rang": o["rang"], "ex_aequo": o["ex_aequo"],
                     "ok": o["admis"], "detail": f"{o['validees']}/{o['composees']} évaluation(s) validée(s)"} for o in res]
        else:
            ev = next((e for e in evs if str(e["id"]) == str(choix)), None) or (evs[-1] if evs else None)
            if not ev:
                return None, [], 0
            _, lignes = EC.resultats(ev, cl)
            source = ev["titre"]
            cand = [{"eleve": l["eleve"], "moyenne": l["moyenne"], "rang": l["rang"], "ex_aequo": l["ex_aequo"],
                     "ok": bool(l["maitrise"]), "detail": f"{l['reussies']}/{l['nb_notes']} matière(s) ≥ 10"}
                    for l in lignes]
        ok = [c for c in cand if c["ok"] and c["moyenne"] is not None]
        retenus = [c for c in ok if (seuil is None or c["moyenne"] >= seuil) and (n is None or c["rang"] <= n)]
        from calcul import mention
        for c in retenus:
            c["mention"] = mention(c["moyenne"])
            c["rang_txt"] = rang_txt(c["rang"], c["eleve"]["sexe"], c["ex_aequo"])
        retenus.sort(key=lambda c: (c["rang"], c["eleve"]["nom"], c["eleve"]["prenoms"]))
        return source, retenus, len(ok)

    @app.route("/tableau-honneur")
    @H.connexion_requise("evaluations")
    def honneur_accueil():
        classes, cl, evs, _ = choisir(avec_ev=False)
        seuil, n, msg = params_honneur()
        choix = request.args.get("ev") or (str(evs[-1]["id"]) if evs else "")
        ctx = dict(classes=classes, cl=cl, evs=evs, choix=choix, seuil=seuil, n=n, msg=msg, msg_defaut=MSG_DEFAUT,
                   modele=request.args.get("modele", "certificat"))
        if cl:
            ctx.update(v=ident(cl), cle_entete=cle_entete(cl), V=vocab(cl))
        if cl and evs:
            source, retenus, nb_ok = honneur(cl, evs, choix, seuil, n)
            ctx.update(source=source, retenus=retenus, nb_ok=nb_ok,
                       bilan_enr=bool(selection_enregistree(cl, evs)[0]))
        return render_template("honneur_accueil.html", **ctx)

    def exiger_honneur():
        classes, cl, evs, _ = choisir(avec_ev=False)
        if not cl:
            abort(404)
        if not evs:
            flash("Aucune évaluation pour cette classe : créez-en une et saisissez les notes.", "warning")
            return cl, None, None, None, None, None
        seuil, n, msg = params_honneur()
        choix = request.args.get("ev") or str(evs[-1]["id"])
        source, retenus, _ = honneur(cl, evs, choix, seuil, n)
        return cl, source, retenus, msg, seuil, n

    @app.route("/tableau-honneur/pdf")
    @H.connexion_requise("evaluations")
    def honneur_pdf():
        cl, source, retenus, msg, seuil, n = exiger_honneur()
        if source is None:
            return redirect(url_for("honneur_accueil", classe=cl["id"]))
        crit = []
        if seuil is not None:
            crit.append(f"moyenne ≥ {nb(seuil)}")
        if n:
            crit.append(f"{n} premier(s)")
        v = ident(cl)
        pdf = pdf_tableau_honneur(H, cl, source, retenus, msg, " ; ".join(crit), v, img_titulaire(cl), img_directeur())
        H.journal("tableau_honneur_pdf", f"{cl['nom']} {source}")
        return H.pdf_reponse(pdf, f"tableau_honneur_{cl['nom']}.pdf".replace(" ", "_"))

    @app.route("/tableau-honneur/certificats")
    @H.connexion_requise("evaluations")
    def honneur_certificats():
        cl, source, retenus, msg, _, _ = exiger_honneur()
        if source is None:
            return redirect(url_for("honneur_accueil", classe=cl["id"]))
        eid = request.args.get("eleve", type=int)
        if eid:
            retenus = [c for c in retenus if c["eleve"]["id"] == eid]
        if not retenus:
            flash("Aucun élève retenu pour un certificat d'honneur.", "warning")
            return redirect(url_for("honneur_accueil", classe=cl["id"]))
        modele = "diplome" if request.args.get("modele") == "diplome" else "certificat"
        pdf = pdf_certificats(H, cl, source, retenus, ident(cl), img_titulaire(cl), img_directeur(), modele)
        H.journal("certificats_honneur", f"{cl['nom']} ({len(retenus)})")
        return H.pdf_reponse(pdf, f"{modele}s_honneur_{cl['nom']}.pdf".replace(" ", "_"))


# ================================================================== PDF sur canevas libre
def _cadre(c, W, Hh, m=10):
    """Double cadre décoratif (bleu + or) avec coins ornés."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    or_ = colors.HexColor("#B8860B")
    bleu = colors.HexColor("#1F4E79")
    c.saveState()
    c.setStrokeColor(bleu)
    c.setLineWidth(3)
    c.rect(m * mm, m * mm, W - 2 * m * mm, Hh - 2 * m * mm)
    c.setStrokeColor(or_)
    c.setLineWidth(1)
    c.rect((m + 2.5) * mm, (m + 2.5) * mm, W - 2 * (m + 2.5) * mm, Hh - 2 * (m + 2.5) * mm)
    c.setFillColor(or_)
    for x, y in ((m, m), (m, None), (None, m), (None, None)):
        cx = (x + 2.5) * mm if x else W - (m + 2.5) * mm
        cy = (y + 2.5) * mm if y else Hh - (m + 2.5) * mm
        c.circle(cx, cy, 2.2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.circle(cx, cy, 1.1 * mm, stroke=0, fill=1)
        c.setFillColor(or_)
    c.restoreState()


def _entete_officiel(H, c, W, Hh, cl, v, marge=18):
    """En-tête officiel : République, ministère, DDEMP / CS / école (valeurs de M.identification) à gauche ;
    logo (ou nom de l'école) et année scolaire à droite. Retourne l'ordonnée disponible sous l'en-tête."""
    from reportlab.lib.units import mm
    P = H.pdfs
    x = marge * mm
    y = Hh - (marge + 2) * mm
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, "RÉPUBLIQUE DU BÉNIN")
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(x, y - 10, "Fraternité – Justice – Travail")
    c.setFont("Helvetica", 7.5)
    mini = P.MINISTERE.get(cl["cycle"], "").upper()
    if len(mini) > 60:
        coupe = mini.rfind(" ", 0, 60)
        c.drawString(x, y - 20, mini[:coupe])
        c.drawString(x, y - 29, mini[coupe + 1:])
        yy = y - 39
    else:
        c.drawString(x, y - 20, mini)
        yy = y - 30
    for lab, val in (("DDEMP", v.get("ddemp")), ("CS", v.get("cs")), ("ÉCOLE", v.get("ecole"))):
        if val:
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(x, yy, f"{lab} : ")
            c.setFont("Helvetica", 7.5)
            c.drawString(x + c.stringWidth(f"{lab} : ", "Helvetica-Bold", 7.5), yy, str(val)[:60])
            yy -= 9
    logo = P._ecole_img("logo.png")
    xd = W - marge * mm
    if logo:
        c.drawImage(logo, xd - 20 * mm, y - 20 * mm, 20 * mm, 20 * mm, preserveAspectRatio=True, mask="auto")
        c.setFont("Helvetica", 7.5)
        c.drawRightString(xd, y - 26 * mm, f"Année scolaire {v.get('annee')}")
    else:
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(xd, y, str(v.get("ecole") or "")[:60])
        c.setFont("Helvetica", 7.5)
        c.drawRightString(xd, y - 10, f"Année scolaire {v.get('annee')}")
    return min(yy, y - 27 * mm) - 4


def _signatures_canevas(H, c, W, ys, cl, v, img_tit, img_dir, x_tit=0.28, x_dir=0.72):
    """Titulaire (gauche) et directeur(trice) avec cachet de l'école (droite)."""
    P = H.pdfs
    P.bloc_signature(c, W * x_tit, ys - 12, v.get("titulaire_titre") or "Le titulaire", v.get("titulaire_nom") or "",
                     img_tit, False, lieu_date=False)
    # cachet décalé à gauche pour ne pas masquer le nom du directeur (bloc_signature le centre sur le nom)
    from reportlab.lib.units import mm
    P.cachet_ecole(c, W * x_dir - 27 * mm, ys - 26 * mm, 12 * mm)
    P.bloc_signature(c, W * x_dir, ys, titre_directeur(v.get("directeur_titre")), v.get("directeur_nom") or "",
                     img_dir, False)


def pdf_tableau_honneur(H, cl, source, retenus, msg, criteres, v, img_tit, img_dir):
    """Tableau d'honneur à afficher (A4 portrait, cadre décoratif), pagination automatique."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle
    P = H.pdfs
    W, Hh = A4
    buf = io.BytesIO()
    c = P.GCanvas(buf, pagesize=A4)
    c.setTitle("Tableau d'honneur")
    or_ = colors.HexColor("#B8860B")
    bleu = colors.HexColor("#1F4E79")
    st_msg = ParagraphStyle("m", fontName="Helvetica-Oblique", fontSize=10.5, leading=15, alignment=4,
                            textColor=colors.HexColor("#344054"))
    st = ParagraphStyle("c", fontName="Helvetica", fontSize=9.5, leading=11.5)
    stb = ParagraphStyle("cb", parent=st, fontName="Helvetica-Bold")
    sth = ParagraphStyle("h", parent=st, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    medailles = {1: "#F5D76E", 2: "#D9D9D9", 3: "#E6B98A"}
    entete = [Paragraph(t, sth) for t in ("Rang", "Nom et prénoms", "Sexe", "Moyenne", "Mention")]
    restants = list(retenus)
    bas = 20 * mm
    premiere = True
    while True:
        _cadre(c, W, Hh)
        y = _entete_officiel(H, c, W, Hh, cl, v)
        if premiere:
            y -= 16
            c.setFillColor(or_)
            c.setFont("Helvetica-Bold", 30)
            c.drawCentredString(W / 2, y, "TABLEAU D'HONNEUR")
            c.setStrokeColor(or_)
            c.setLineWidth(1.2)
            c.line(W / 2 - 60 * mm, y - 8, W / 2 + 60 * mm, y - 8)
            c.setFillColor(bleu)
            c.setFont("Helvetica-Bold", 12)
            y -= 26
            c.drawCentredString(W / 2, y, f"Classe : {cl['nom']}  —  {source}"[:95])
            c.setFont("Helvetica", 10)
            y -= 14
            c.setFillColor(colors.black)
            c.drawCentredString(W / 2, y, f"Année scolaire {v.get('annee')}" + (f"  ·  Critères : {criteres}" if criteres else ""))
            p = Paragraph(esc(msg), st_msg)
            _, h = p.wrap(W - 50 * mm, 200)
            y -= 10 + h
            p.drawOn(c, 25 * mm, y)
            y -= 10
        else:
            y -= 10
            c.setFillColor(bleu)
            c.setFont("Helvetica-Bold", 13)
            c.drawCentredString(W / 2, y, f"TABLEAU D'HONNEUR (suite) — {cl['nom']}")
            y -= 12
        if restants:
            data = [entete]
            for cnd in restants:
                e = cnd["eleve"]
                data.append([Paragraph(cnd["rang_txt"], stb), Paragraph(f"<b>{esc(e['nom'])}</b> {esc(e['prenoms'])}", st),
                             Paragraph(e["sexe"] or "", st), Paragraph(f"<b>{nb(cnd['moyenne'])}</b>", st),
                             Paragraph(esc(cnd["mention"]), st)])
            t = Table(data, colWidths=[24 * mm, 80 * mm, 14 * mm, 22 * mm, 30 * mm], repeatRows=1)
            styles = [("BACKGROUND", (0, 0), (-1, 0), bleu), ("GRID", (0, 0), (-1, -1), 0.5, or_),
                      ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                      ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                      ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFBEA"), colors.white])]
            for i, cnd in enumerate(restants, start=1):
                if cnd["rang"] in medailles:
                    styles.append(("BACKGROUND", (0, i), (0, i), colors.HexColor(medailles[cnd["rang"]])))
            t.setStyle(TableStyle(styles))
            parts = t.split(170 * mm, y - bas)
            if not parts:  # pas même une ligne : page suivante
                c.showPage()
                premiere = False
                continue
            morceau = parts[0]
            _, h = morceau.wrapOn(c, W, Hh)
            morceau.drawOn(c, (W - 170 * mm) / 2, y - h)
            y -= h
            restants = restants[len(morceau._cellvalues) - 1:]
        elif premiere:
            c.setFont("Helvetica-Oblique", 11)
            y -= 30
            c.drawCentredString(W / 2, y, "Aucun élève ne remplit les critères retenus.")
        if restants:
            c.showPage()
            premiere = False
            continue
        # signatures : titulaire (gauche), directeur(trice) + cachet (droite)
        ys = min(y - 14, 80 * mm)
        if ys < 58 * mm:  # pas la place : nouvelle page
            c.showPage()
            _cadre(c, W, Hh)
            ys = _entete_officiel(H, c, W, Hh, cl, v) - 20
        _signatures_canevas(H, c, W, ys, cl, v, img_tit, img_dir)
        c.showPage()
        break
    c.save()
    return buf.getvalue()


def pdf_certificats(H, cl, source, retenus, v, img_tit, img_dir, modele="certificat"):
    """Un certificat (ou diplôme) d'honneur par élève : A4 paysage, cadre, QR de vérification, cachet et signatures."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph
    P = H.pdfs
    W, Hh = landscape(A4)
    buf = io.BytesIO()
    c = P.GCanvas(buf, pagesize=(W, Hh))
    titre = "DIPLÔME D'HONNEUR" if modele == "diplome" else "CERTIFICAT D'HONNEUR"
    c.setTitle(titre.capitalize())
    or_ = colors.HexColor("#B8860B")
    bleu = colors.HexColor("#1F4E79")
    st = ParagraphStyle("t", fontName="Helvetica", fontSize=13, leading=20, alignment=1)
    for cnd in retenus:
        e = cnd["eleve"]
        fem = e["sexe"] == "F"
        _cadre(c, W, Hh, 8)
        y = _entete_officiel(H, c, W, Hh, cl, v, marge=16)
        c.setFillColor(or_)
        c.setFont("Helvetica-Bold", 34)
        c.drawCentredString(W / 2, y - 18, titre)
        c.setFillColor(bleu)
        c.setFont("Helvetica", 13)
        c.drawCentredString(W / 2, y - 42, "décerné à")
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(W / 2, y - 72, f"{e['nom']} {e['prenoms']}"[:48])
        c.setStrokeColor(or_)
        c.line(W / 2 - 80 * mm, y - 80, W / 2 + 80 * mm, y - 80)
        naiss = f", {'née' if fem else 'né'} le {P.date_fr(e['date_naissance'])}" if e["date_naissance"] else ""
        txt = (f"élève de la classe de <b>{esc(cl['nom'])}</b>{esc(naiss)}, classé{'e' if fem else ''} "
               f"<b>{esc(cnd['rang_txt'])}</b> avec une moyenne de <b>{nb(cnd['moyenne'])}/20</b> "
               f"(mention <b>{esc(cnd['mention'])}</b>) à l'issue de : {esc(source)}, année scolaire "
               f"{esc(v.get('annee'))}, pour son travail remarquable, son assiduité et sa bonne conduite. "
               "<br/><b>Toutes nos félicitations !</b>")
        c.setFillColor(colors.black)
        p = Paragraph(txt, st)
        _, h = p.wrap(W - 70 * mm, 200)
        p.drawOn(c, 35 * mm, y - 92 - h)
        code = H.enregistrer_document(
            "certificat_honneur", e["id"], f"{titre.capitalize()} – {e['nom']} {e['prenoms']} ({cl['nom']}, {source})"[:250],
            cle="honneur:" + hashlib.sha1(f"{cl['id']}|{source}|{e['id']}|{cnd['moyenne']}".encode()).hexdigest()[:20])
        P._qr(c, code, 20 * mm, 17 * mm, 20 * mm)
        _signatures_canevas(H, c, W, 62 * mm, cl, v, img_tit, img_dir, x_tit=0.47, x_dir=0.78)
        c.showPage()
    c.save()
    return buf.getvalue()


def bulletins_annuels(H, cl, sel, res, v, img_tit, img_dir):
    """Un bulletin annuel (A4) par élève : notes par matière et par évaluation, M_O, E_D, M, rang, décision."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle
    P = H.pdfs
    W, Hh = A4
    buf = io.BytesIO()
    c = P.GCanvas(buf, pagesize=A4)
    c.setTitle("Bulletins annuels")
    bleu = colors.HexColor("#1F4E79")
    mat_cycle = cl["cycle"] == "maternelle"
    # matières évaluées au moins une fois (ordre officiel)
    toutes = EC.matieres_cycle(EC.cycle_du_niveau(cl["niveau"]))
    par_ev = [{m["id"] for m in EC.matieres_de(ev, cl)} for ev in sel]
    vues = set().union(*par_ev) if par_ev else set()
    matieres = [m for m in toutes if m["id"] in vues]
    st = ParagraphStyle("c", fontName="Helvetica", fontSize=7.5, leading=9)
    stb = ParagraphStyle("cb", parent=st, fontName="Helvetica-Bold")
    sth = ParagraphStyle("h", parent=st, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    stc = ParagraphStyle("cc", parent=st, alignment=1)
    effectif = sum(1 for o in res if o["composees"])
    V = vocab(cl)
    signature_cle = "|".join(str(e["id"]) for e in sel)
    for o in res:
        e = o["eleve"]
        y = _entete_officiel(H, c, W, Hh, cl, v, marge=15)
        c.setStrokeColor(bleu)
        c.setLineWidth(1.2)
        c.line(15 * mm, y, W - 15 * mm, y)
        y -= 20
        c.setFillColor(bleu)
        c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(W / 2, y, "BULLETIN ANNUEL DE NOTES")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9.5)
        y -= 14
        c.drawCentredString(W / 2, y, f"Année scolaire {v.get('annee')} — Bilan annuel et décision de fin d'année")
        y = P._infos(c, 15 * mm, y - 8, W - 30 * mm, [
            ("Nom et prénoms", f"{e['nom']} {e['prenoms']}"), ("Classe", f"{cl['nom']} ({v.get('cours') or cl['niveau']})"),
            ("Sexe", "Féminin" if e["sexe"] == "F" else "Masculin"), ("Matricule", e["matricule"] or "—"),
            ("Né(e) le", P.date_fr(e["date_naissance"]) if e["date_naissance"] else "—"),
            ("Effectif évalué", effectif)]) - 6
        data = [[Paragraph("Matières", sth)] + [Paragraph(esc(ev["libelle"]), sth) for ev in sel]]
        for m in matieres:
            row = [Paragraph(esc(m["nom"]), st)]
            for ids, l in zip(par_ev, o["lignes"]):
                if m["id"] not in ids:
                    row.append(Paragraph("·", stc))
                elif l and m["id"] in l["dispenses"]:
                    row.append(Paragraph("Disp.", stc))
                elif mat_cycle:
                    row.append(Paragraph(esc((l["appreciations"].get(m["id"]) if l else None) or "—"), stc))
                else:
                    val = l["notes"].get(m["id"]) if l else None
                    row.append(Paragraph("—" if val is None else
                                         f"<font color='{'#B42318' if val < 10 else '#000000'}'>{nb(val)}</font>", stc))
            data.append(row)
        nfin = 2
        if not mat_cycle:
            data.append([Paragraph("Moyenne", stb)] + [Paragraph(f"<b>{nb(mo)}</b>", stc) for mo in o["moyennes"]])
            nfin += 1
        if cl["cycle"] == "primaire":
            data.append([Paragraph("Matières ≥ 10 / seuil", stb)] +
                        [Paragraph(f"{l['reussies']}/{l['seuil']}" if l and l["compose"] else "—", stc) for l in o["lignes"]])
            nfin += 1
        data.append([Paragraph("Résultat", stb)] +
                    [Paragraph(esc(l["decision"]) if l else "—", stc) for l in o["lignes"]])
        data.append([Paragraph("Rang", stb)] + [Paragraph(esc(l["rang_texte"]) if l else "—", stc) for l in o["lignes"]])
        larg_m = 62 * mm
        reste = (W - 30 * mm - larg_m) / max(1, len(sel))
        t = Table(data, colWidths=[larg_m] + [reste] * len(sel), repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), bleu), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#667085")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
            ("BACKGROUND", (0, len(data) - nfin), (-1, -1), colors.HexColor("#EEF4FA"))]))
        _, h = t.wrapOn(c, W, Hh)
        t.drawOn(c, 15 * mm, y - h)
        y -= h + 8
        # synthèse annuelle
        admis = o["admis"]
        synth = [
            ["M_O (moyenne des évaluations antérieures)", nb(o["M_O"])],
            [f"E_D (dernière évaluation : {sel[-1]['libelle']})", nb(o["E_D"])],
            ["Moyenne annuelle M = (M_O + E_D) / 2", nb(o["M"])],
            [f"Évaluations validées ({V['reussite']}) / composées", f"{o['validees']} / {o['composees']} (requis : {o['requis']})"],
            ["Rang annuel", f"{rang_txt(o['rang'], e['sexe'], o['ex_aequo'])} sur {effectif}"],
        ]
        ts = Table([[Paragraph(esc(a), stb), Paragraph(esc(b), st)] for a, b in synth], colWidths=[85 * mm, 45 * mm])
        ts.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, bleu), ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#98A2B3")),
                                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F4F7")),
                                ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        _, h2 = ts.wrapOn(c, W, Hh)
        ts.drawOn(c, 15 * mm, y - h2)
        # cadre de décision
        xd = 15 * mm + 135 * mm
        vert, rouge = colors.HexColor("#1B7F3B"), colors.HexColor("#B42318")
        c.setStrokeColor(vert if admis else rouge)
        c.setLineWidth(1.5)
        c.roundRect(xd, y - h2, W - 15 * mm - xd, h2, 4)
        cx = xd + (W - 15 * mm - xd) / 2
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawCentredString(cx, y - 12, "DÉCISION DE FIN D'ANNÉE")
        c.setFillColor(vert if admis else rouge)
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(cx, y - h2 / 2 - 2, o["decision"])
        c.setFont("Helvetica", 8)
        suite = ("Passe en classe supérieure" if admis else ("Redouble" if o["composees"] else "Non évalué(e)"))
        c.drawCentredString(cx, y - h2 / 2 - 14, suite)
        c.setFillColor(colors.black)
        y -= h2 + 10
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(15 * mm, y, f"Règle : l'élève est admis(e) s'il/si elle a validé ({V['reussite']}) au moins les 2/3 "
                                 "des évaluations qu'il/elle a composées. M = (M_O + E_D) / 2 sert au rang.")
        y -= 8
        # signatures + QR
        ys = min(y - 10, 75 * mm)
        _signatures_canevas(H, c, W, ys, cl, v, img_tit, img_dir, x_tit=0.3, x_dir=0.74)
        code = H.enregistrer_document("bulletin_annuel", e["id"],
                                      f"Bulletin annuel {v.get('annee')} – {e['nom']} {e['prenoms']} ({cl['nom']}) : "
                                      f"M = {nb(o['M'])}, {o['decision']}",
                                      cle="bilan:" + hashlib.sha1(f"{cl['id']}|{signature_cle}|{e['id']}|{o['M']}|{o['decision']}".encode()).hexdigest()[:20])
        P._qr(c, code, 15 * mm, 12 * mm, 18 * mm)
        c.showPage()
    c.save()
    return buf.getvalue()
