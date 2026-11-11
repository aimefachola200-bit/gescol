# -*- coding: utf-8 -*-
"""v1.21 — Banque d'épreuves (outil pur, sans Flask) : organigramme des épreuves (INFRE), périodes de l'année,
générateur des épreuves APC (sujet + corrigé type + grille de correction) d'après la progression des planifications.

Organigramme (relevé dans les épreuves standardisées de l'INFRE / SRE : CE1 2016, CE2 2015, CM1-CM2 2014) :
  CE1 : Compréhension de l'écrit (1 h), Expression écrite (1 h), Mathématique (1 h), EST (1 h), ES (1 h),
        Éducation artistique (travaux manuels ; chant-poème-conte) (1 h), EPS (vitesse + gymnastique).
  CE2 : Compréhension de l'écrit (45 min, 4 items), Expression écrite (45 min), Mathématique, EST, ES, EA, EPS (1 h).
  CM1, CM2 : Expression écrite, Compréhension de l'écrit (lecture, 4 items), Mathématique, EST, ES, EA, EPS (1 h).
  Chaque épreuve : COURS / PÉRIODE / DURÉE ; mise en contexte ; Tâche « Tu es invité à … » ; support ; consigne en items
  numérotés (a, b, c). Périodes : premier, deuxième, troisième trimestre, fin d'année.
  CI et CP (pas de modèle INFRE) : même organigramme que le CE1, durées réduites (30 à 45 min), items simplifiés.
"""
import hashlib
import random
import re

import banque_dictees as BD
import banque_ea_eps as BE
import banque_taches as BT
import banque_textes as BX

MENTION = "Épreuve conçue selon l'APC — à valider par le conseiller pédagogique"
COURS = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]

# (code, libellé, type, mois de l'année scolaire jusqu'auquel porte la progression, mois civil d'administration)
PERIODES = [("M1", "Évaluation mensuelle — octobre", "mensuelle", 10), ("M2", "Évaluation mensuelle — novembre", "mensuelle", 11),
            ("T1", "Premier trimestre", "trimestrielle", 12), ("M3", "Évaluation mensuelle — janvier", "mensuelle", 1),
            ("M4", "Évaluation mensuelle — février", "mensuelle", 2), ("T2", "Deuxième trimestre", "trimestrielle", 3),
            ("M5", "Évaluation mensuelle — avril", "mensuelle", 4), ("M6", "Évaluation mensuelle — mai", "mensuelle", 5),
            ("T3", "Troisième trimestre", "trimestrielle", 6), ("FA", "Fin d'année — évaluation de passage", "passage", 6),
            ("C1", "Examen blanc du CEP n° 1", "cep_blanc", 2), ("C2", "Examen blanc du CEP n° 2", "cep_blanc", 4),
            ("C3", "Examen blanc du CEP n° 3", "cep_blanc", 5)]
PER = {p[0]: p for p in PERIODES}
TYPES = {"mensuelle": "Évaluation mensuelle", "trimestrielle": "Évaluation sommative trimestrielle",
         "passage": "Évaluation de fin d'année (passage)", "cep_blanc": "Examen blanc du CEP"}
TYPE_EVAL = {"mensuelle": "formative", "trimestrielle": "sommative", "passage": "certificative", "cep_blanc": "certificative"}
MOIS_SCO = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6]
MOIS_LIB = {1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"}


def periodes_du_cours(cours):
    return [p for p in PERIODES if (p[2] != "cep_blanc" or cours == "CM2") and (p[2] != "passage" or cours != "CM2")]


# ------------------------------------------------------------------------------------------------ organigramme
def _dur(cours, code):
    if cours in ("CI", "CP") and code != "dictee":
        return {"comp": "30 min", "expr": "30 min", "math": "45 min", "eps": "selon le guide d'administration"}.get(code, "30 min")
    if cours == "CE2" and code in ("comp", "expr"):
        return "45 minutes"
    if code == "dictee":
        return "20 min" if cours in ("CI", "CP") else "30 min" if cours in ("CE1", "CE2") else "45 min"
    if code == "eps":
        return "selon le guide d'administration"
    return "01 heure"


def organigramme(cours, type_=None):
    """Liste ordonnée des épreuves d'un cours (et d'un type d'évaluation). v1.30 : dictée, EA et EPS à toutes les
    évaluations (mensuelles comprises) ; CEP blanc dans l'ordre du procès-verbal du CEP (dictée, communication écrite,
    compréhension de l'écrit, mathématique, EST, ES, EA, EPS)."""
    fr = [("comp", "Français — Compréhension de l'écrit", "COMP.EC", "francais"), ("expr", "Français — Expression écrite", "EXP.EC", "francais")]
    if cours in ("CM1", "CM2"):
        fr = fr[::-1]                                    # au CM, l'INFRE place l'expression écrite en tête
    dic = ("dictee", "Français — Dictée" + (" et questions" if cours in ("CE2", "CM1", "CM2") else ""), "DIC", "francais")
    reste = [("math", "Mathématique", "MATH", "maths"), ("est", "Éducation scientifique et technologique", "ED.SCI", "est"),
             ("es", "Éducation sociale", "ED.SOC", "es"), ("ea", "Éducation artistique", "ART.P", "ea"),
             ("eps", "Éducation physique et sportive", "EPS", "eps")]
    if type_ == "cep_blanc":
        base = [dic, fr[0] if fr[0][0] == "expr" else fr[1], fr[1] if fr[0][0] == "expr" else fr[0]] + reste
    else:
        base = fr + [dic] + reste
    return [{"code": c, "discipline": d, "matiere_code": mc, "matiere": m, "duree": _dur(cours, c), "ordre": i + 1}
            for i, (c, d, mc, m) in enumerate(base)]


def organigramme_tableau():
    """Pour l'affichage « Organigramme des épreuves (INFRE) » : cours -> [(discipline, durée, structure)]."""
    struct = {"comp": "contexte · tâche · texte support · Items 1 à {n} (compréhension, langue, appréciation{x})",
              "expr": "contexte · tâche « Tu es invité à … » · consignes numérotées · grille (pertinence, cohérence, correction, perfectionnement)",
              "math": "situation-problème · tâche · Items 1 à 3 (numération / calcul, géométrie / mesure, résolution)",
              "est": "support · tâche · Items 1 à 3", "es": "support · tâche · Items 1 à 3",
              "ea": "A : dessin / arts plastiques · B : couture / travaux manuels · matériel · consignes · grille critériée",
              "eps": "guide d'administration · course + saut, lancer ou jeu · barèmes filles / garçons par âge · fiche de notation",
              "dictee": "texte dicté · barème des fautes{q}"}
    out = {}
    for c in COURS:
        n = 4 if c in ("CE2", "CM1", "CM2") else 3
        out[c] = [(e["discipline"], e["duree"], struct[e["code"]].format(n=n, x=", prolongement" if n == 4 else "",
                                                                        q=" · questions (vocabulaire, grammaire, conjugaison)" if n == 4 else "")) for e in organigramme(c)]
    return out


# ------------------------------------------------------------------------------------------------ outils
def _rng(*cle):
    return random.Random(int(hashlib.sha1("|".join(map(str, cle)).encode()).hexdigest()[:12], 16))


def nb(n):
    """12345 -> « 12 345 » ; 2,5 -> « 2,5 »."""
    if isinstance(n, float) and not n.is_integer():
        return f"{n:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    s = f"{int(n):,}".replace(",", " ")
    return s


def repartir(total, n):
    """Répartit total points sur n questions (demi-points), somme exacte."""
    if n <= 0:
        return []
    base = int(total / n * 2) / 2
    out = [base] * n
    out[-1] = round(total - base * (n - 1), 1)
    return out


def items(blocs, totaux):
    out = []
    for i, (qs, tot) in enumerate(zip(blocs, totaux), 1):
        pts = repartir(tot, len(qs))
        out.append({"titre": f"Item {i}", "questions": [{"q": q, "r": r, "pts": p} for (q, r), p in zip(qs, pts)]})
    return out


def presentation():
    return {"titre": "Présentation", "questions": [{"q": "Présentation de la copie (propreté, lisibilité).", "r": "Copie propre et lisible.", "pts": 2}]}


# ------------------------------------------------------------------------------------------------ mathématiques (générateur)
NOMS = ["Koffi", "Awa", "Sika", "Bio", "Rachida", "Tobi", "Akim", "Nafissa", "Codjo", "Ayaba", "Issa", "Mariam"]
LIEUX = ["Pobè", "Kétou", "Dassa", "Parakou", "Lokossa", "Abomey", "Natitingou", "Bohicon", "Savalou", "Kandi"]


def maths(cours, per, k):
    """k : rang de la période dans l'année (0 = octobre … 9 = fin d'année)."""
    r = _rng("math", cours, per)
    n1, n2 = r.choice(NOMS), r.choice(NOMS)
    lieu = r.choice(LIEUX)
    if cours == "CI":
        a, b = r.randint(2, 4 + k // 2), r.randint(1, 3 + k // 3)
        ctx = f"{n1} range des bâtonnets avec son camarade {n2}. Il en a {a} ; {n2} lui en donne {b}."
        blocs = [[(f"Dessine {a} bâtonnets.", f"{a} bâtonnets dessinés"), (f"Écris en chiffres le nombre de bâtonnets de {n1} au départ.", str(a))],
                 [(f"Combien {n1} a-t-il de bâtonnets en tout ?", f"{a} + {b} = {a + b}"), (f"Compare {a} et {b} avec < ou >.", f"{a} {'>' if a > b else '<' if a < b else '='} {b}")],
                 [("Colorie le rond et entoure le carré (figures données).", "rond colorié, carré entouré"), ("Qui est devant toi ? Qui est derrière toi ?", "RP : se repérer devant / derrière")]]
    elif cours == "CP":
        a, b = r.randint(12 + 6 * k, 30 + 6 * k), r.randint(5, 9 + 2 * k)
        prix = r.choice([25, 50, 100])
        ctx = f"Au marché de {lieu}, {n1} vend des oranges. Le matin, elle a {a} oranges. Elle en vend {b}. Une orange coûte {prix} F."
        blocs = [[(f"Écris en lettres le nombre {a}.", f"{a} en lettres"), (f"Décompose {a} en dizaines et unités.", f"{a // 10} dizaines et {a % 10} unités")],
                 [(f"Combien d'oranges reste-t-il ?", f"{a} − {b} = {a - b}"), (f"Combien {n1} gagne-t-elle pour 2 oranges ?", f"{prix} + {prix} = {2 * prix} F")],
                 [("Mesure le trait tracé au tableau avec ta règle et écris sa longueur en cm.", "longueur exacte en cm"), ("Range du plus petit au plus grand : " + ", ".join(map(str, sorted({a, b, a - b}, reverse=True))) + ".", ", ".join(map(str, sorted({a, b, a - b}))))]]
    elif cours == "CE1":
        a = r.randint(120 + 60 * k, 300 + 80 * k)
        b, c = r.randint(80, 250), r.randint(60, 200)
        t = r.choice([2, 3, 4, 5])
        ctx = f"Pour la fête de l'école de {lieu}, le directeur reçoit {b} cahiers rouges et {c} cahiers bleus. L'école compte {a} élèves."
        blocs = [[(f"Décompose le nombre {a}.", f"{a // 100} centaines {a // 10 % 10} dizaines {a % 10} unités"), (f"Range par ordre croissant : {b} ; {c} ; {a}.", " < ".join(map(str, sorted([a, b, c]))))],
                 [("Calcule le nombre total de cahiers reçus.", f"{b} + {c} = {b + c}"), (f"Chaque élève de CE1 reçoit {t} cahiers ; il y a 30 élèves. Combien de cahiers faut-il ?", f"30 × {t} = {30 * t}")],
                 [(f"Y a-t-il assez de cahiers pour donner un cahier à chacun des {a} élèves ? Justifie.", ("Oui" if b + c >= a else "Non") + f" : {b + c} {'≥' if b + c >= a else '<'} {a}"), ("Trace un carré de 4 cm de côté.", "carré de 4 cm tracé à la règle")]]
    elif cours == "CE2":
        a = r.randint(2000 + 3000 * k, 6000 + 4000 * k)
        p, q_ = r.randint(12, 35), r.randint(150, 450)
        l, lg = r.randint(8, 20), r.randint(21, 40)
        ctx = f"La coopérative de {lieu} a récolté {nb(a)} kg de maïs. Elle vend des sacs de {p} kg à {nb(q_ * 10)} F le sac. Son champ rectangulaire mesure {lg} m de long sur {l} m de large."
        sacs, reste = divmod(a, p)
        blocs = [[(f"Écris en lettres : {nb(a)}.", f"{nb(a)} en lettres"), (f"Donne la valeur du chiffre des milliers de {nb(a)}.", f"{a // 1000 % 10} milliers")],
                 [(f"Combien de sacs pleins peut-on remplir ? Reste-t-il du maïs ?", f"{nb(a)} ÷ {p} = {nb(sacs)} sacs, reste {reste} kg"), (f"Combien la coopérative gagne-t-elle pour 12 sacs ?", f"12 × {nb(q_ * 10)} = {nb(12 * q_ * 10)} F")],
                 [("Calcule le périmètre du champ.", f"({lg} + {l}) × 2 = {(lg + l) * 2} m"), ("Convertis 3 kg 250 g en grammes.", "3 250 g")]]
    elif cours == "CM1":
        a = r.randint(1_200_000 + 800_000 * k, 3_000_000 + 900_000 * k)
        frac_n, frac_d = r.choice([(1, 4), (2, 5), (3, 4), (3, 5), (2, 3)])
        tot = r.choice([1200, 1500, 1800, 2400, 3000])
        L, lb = r.randint(25, 60), r.randint(12, 24)
        ctx = (f"Un groupement de producteurs de {lieu} a vendu sa récolte de riz pour {nb(a)} F. Il possède un champ rectangulaire de {L} m sur {lb} m "
               f"et un stock de {nb(tot)} kg dont les {frac_n}/{frac_d} sont destinés à la vente.")
        blocs = [[(f"Écris {nb(a)} en lettres.", f"{nb(a)} en lettres"), (f"Arrondis {nb(a)} à la centaine de mille près.", nb(round(a, -5)))],
                 [(f"Calcule la masse destinée à la vente.", f"{nb(tot)} × {frac_n} ÷ {frac_d} = {nb(tot * frac_n // frac_d)} kg"),
                  ("Écris sous forme décimale : 3/4 ; 7/10.", "0,75 ; 0,7")],
                 [("Calcule l'aire du champ en m².", f"{L} × {lb} = {nb(L * lb)} m²"), ("Trace un triangle rectangle de 6 cm et 4 cm de côtés de l'angle droit.", "triangle rectangle tracé avec l'équerre")]]
    else:   # CM2 (mensuelles, trimestres, CEP blancs)
        prix = r.choice([45000, 60000, 75000, 90000, 120000])
        pct = r.choice([10, 15, 20, 25])
        d_km, h = r.choice([(120, 2), (150, 3), (180, 3), (200, 4), (90, 2)])
        ech = r.choice([10000, 25000, 50000])
        cm = r.randint(4, 12)
        L, l, hh = r.randint(3, 8), r.randint(2, 5), r.randint(1, 3)
        ctx = (f"Pour le voyage d'études des élèves de CM2 de {lieu}, l'école loue un car à {nb(prix)} F ; la mairie prend en charge {pct} % du prix. "
               f"Le car parcourt {d_km} km en {h} h. Sur la carte à l'échelle 1/{nb(ech)}, l'itinéraire mesure {cm} cm. À l'arrivée, on remplit une citerne "
               f"de {L} m sur {l} m sur {hh} m.")
        blocs = [[("Calcule la part payée par la mairie.", f"{nb(prix)} × {pct} ÷ 100 = {nb(prix * pct // 100)} F"), ("Calcule la somme restant à payer par l'école.", f"{nb(prix)} − {nb(prix * pct // 100)} = {nb(prix - prix * pct // 100)} F")],
                 [("Calcule la vitesse moyenne du car.", f"{d_km} ÷ {h} = {nb(d_km / h if d_km % h else d_km // h)} km/h"), ("Calcule la distance réelle représentée sur la carte (en km).", f"{cm} × {nb(ech)} = {nb(cm * ech)} cm = {nb(cm * ech / 100000)} km")],
                 [("Calcule le volume de la citerne en m³ puis en litres.", f"{L} × {l} × {hh} = {L * l * hh} m³ = {nb(L * l * hh * 1000)} L"), ("Construis le symétrique d'un triangle par rapport à une droite.", "figure symétrique correcte (vérification par pliage)")]]
    tache = "Tu es invité à lire le texte ci-dessus et à résoudre les items suivants."
    return ctx, tache, items(blocs, [6, 6, 6]) + [presentation()]


# ------------------------------------------------------------------------------------------------ ES / EST (d'après la progression)
CTX = {"es": "Pendant la semaine culturelle de ton école, le maître organise un jeu de questions sur ce que la classe a appris en éducation sociale. "
             "Ton équipe veut gagner.",
       "est": "Le club scientifique de ton école prépare une exposition pour les parents. Tu dois expliquer ce que la classe a découvert en "
              "éducation scientifique et technologique."}


def _phrases(t, n=2):
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    morceaux = re.split(r"(?<=[.!?])\s+", t)
    return " ".join(morceaux[:n])


def es_est(cours, per, mat, sas, fiches_par_sa):
    """sas : [(num, titre)] des SA étudiées pendant la période ; fiches_par_sa : {num: [fiche…]}."""
    r = _rng(mat, cours, per)
    choix = [s for s in sas if fiches_par_sa.get(s[0])] or sas
    choix = choix[-3:] if len(choix) >= 3 else choix
    blocs = []
    for num, titre in choix[:3]:
        fs = fiches_par_sa.get(num) or []
        f = fs[r.randrange(len(fs))] if fs else None
        sujet = (f or {}).get("titre") or titre
        attendu = _phrases((f or {}).get("je_retiens") or (f or {}).get("contenus") or titre, 2)
        blocs.append([(f"Dis ce que tu as retenu sur : « {sujet} ».", attendu or "Réponse conforme à la synthèse de la séance."),
                      (f"Donne un exemple de ton milieu en rapport avec « {sujet} ».", "RP : exemple pertinent tiré du milieu."),
                      ("Propose un comportement à adopter ou une action à mener." if mat == "es" else "Explique comment tu vérifierais ou appliquerais cela.",
                       "RP : comportement / démarche cohérent avec la leçon.")])
    while len(blocs) < 3:
        blocs.append([("Cite deux choses apprises ce mois-ci dans cette matière.", "RP : deux notions de la progression."),
                      ("Explique l'une d'elles à un camarade.", "RP : explication correcte.")])
    if cours in ("CI", "CP"):
        blocs = [b[:2] for b in blocs]
    tache = "Tu es invité à lire le texte et à répondre aux items ci-dessous."
    return CTX[mat], tache, items(blocs, [6, 6, 6]) + [presentation()], [f"SA {n} : {t}" for n, t in choix]


# ------------------------------------------------------------------------------------------------ grilles
GRILLE_EXPR = [("CM1 — Pertinence", 6, "la production répond à la tâche et à la consigne ; le type de texte est respecté"),
               ("CM2 — Cohérence", 6, "les idées s'enchaînent logiquement ; elles ne se contredisent pas"),
               ("CM3 — Correction de la langue", 4, "orthographe, accords, conjugaison, ponctuation"),
               ("CP — Perfectionnement", 4, "originalité, vocabulaire riche, présentation soignée")]


def grille_items(consignes, critere="Exactitude des réponses"):
    return [{"critere": f"{it['titre']} — {critere if it['titre'] != 'Présentation' else 'Présentation'}",
             "indicateurs": [q["r"] for q in it["questions"]][:4], "points": sum(q["pts"] for q in it["questions"])} for it in consignes]


# ------------------------------------------------------------------------------------------------ assemblage d'une épreuve
def generer(cours, per, e, prog):
    """cours, période, entrée d'organigramme, progression {matiere: {"sas": [(n, titre)], "fiches": {n: [f]}, "refs": str}}.
    Renvoie le dict de l'épreuve (sujet + corrigé + grille)."""
    code, libp, typ, _m = PER[per]
    k = [p[0] for p in PERIODES if p[2] in ("mensuelle", "trimestrielle", "passage")].index(per) if per in [p[0] for p in PERIODES if p[2] != "cep_blanc"] else {"C1": 5, "C2": 6, "C3": 7}[per]
    d = {"cle": f"{cours}-{per}-{e['code']}", "cours": cours, "type": typ, "type_lib": TYPES[typ], "periode": per, "periode_lib": libp,
         "code": e["code"], "discipline": e["discipline"], "matiere_code": e["matiere_code"], "matiere": e["matiere"],
         "duree": e["duree"], "bareme": 20, "ordre": e["ordre"], "support_titre": "", "support": "", "progression": [], "infre": None,
         "mention": MENTION, "source": "Création SCOLARIS d'après la progression de la planification annuelle 2026-2027"}
    c = e["code"]
    if c == "comp":
        t = BX.T.get((cours, per)) or BX.T.get((cours, {"C1": "M4", "C2": "M5", "C3": "M6"}.get(per, per)))
        n_items = len(t["items"])
        tot = [7, 7, 4] if n_items == 3 else [6, 6, 4, 2]
        d.update(contexte=t["contexte"], tache="Tu es invité à lire silencieusement le texte et à répondre aux items de la consigne.",
                 support_titre=t["titre"], support=t["texte"], consignes=items(t["items"], tot[:n_items]) + [presentation()], infre=t.get("infre"))
        d["grille"] = grille_items(d["consignes"])
        d["progression"] = [prog.get("francais", {}).get("refs", "")]
    elif c == "expr":
        t = BT.E[(cours, per)]
        d.update(contexte=t["contexte"], tache=t["tache"], consignes=[{"titre": "Consigne", "questions": [{"q": f"{i}- {x}", "r": "", "pts": None} for i, x in enumerate(t["consignes"], 1)]}],
                 infre=t.get("infre"))
        ind = BT.INDICATEURS.get(t["genre"], [])
        d["grille"] = [{"critere": cr, "indicateurs": ([dsc] + (ind if i == 0 else [])), "points": p} for i, (cr, p, dsc) in enumerate(GRILLE_EXPR)]
        d["corrige_note"] = ("Production personnelle : le correcteur applique la grille (critères minimaux CM1 à CM3 et critère de perfectionnement). "
                             f"Indicateurs du genre « {t['genre'].replace('_', ' ')} » : " + " ; ".join(ind) + ".")
        d["progression"] = [prog.get("francais", {}).get("refs", "")]
    elif c == "math":
        ctx, tache, cons = maths(cours, per, k)
        d.update(contexte=ctx, tache=tache, consignes=cons)
        d["grille"] = grille_items(cons, "Démarche et résultat (raisonnement 50 %, calcul exact 50 %)")
        d["progression"] = [prog.get("maths", {}).get("refs", "")]
    elif c in ("est", "es"):
        p = prog.get(e["matiere"], {})
        ctx, tache, cons, choix = es_est(cours, per, e["matiere"], p.get("sas") or [], p.get("fiches") or {})
        d.update(contexte=ctx, tache=tache, consignes=cons, progression=choix)
        d["grille"] = grille_items(cons, "Exactitude et pertinence des réponses")
    elif c == "ea":
        pa, pb = BE.ea(cours, k)
        d.update(contexte=f"Partie A — {pa[1]} Partie B — {pb[1]}", tache=f"Tu es invité à réaliser les deux travaux : A. {pa[2][len('Tu es invité à '):]} B. {pb[2][len('Tu es invité à '):]}",
                 support_titre=f"A. {pa[0]} · B. {pb[0]}", support=f"Matériel — A : {pa[3]}. B : {pb[3]}.",
                 parties_ea=[{"partie": "A", "titre": pa[0], "contexte": pa[1], "tache": pa[2], "materiel": pa[3]},
                             {"partie": "B", "titre": pb[0], "contexte": pb[1], "tache": pb[2], "materiel": pb[3]}],
                 consignes=[{"titre": f"Partie A — {pa[0]}", "questions": [{"q": f"{i}- {x}", "r": "", "pts": None} for i, x in enumerate(pa[4], 1)]},
                            {"titre": f"Partie B — {pb[0]}", "questions": [{"q": f"{i}- {x}", "r": "", "pts": None} for i, x in enumerate(pb[4], 1)]}])
        d["grille"] = BE.grille_ea("A", pa) + BE.grille_ea("B", pb)
        d["corrige_note"] = ("Épreuve pratique en deux parties notées chacune sur 10 : le correcteur observe la réalisation et applique la grille "
                             "critériée (respect des consignes, maîtrise de la technique, propreté et finition, créativité).")
    elif c == "eps":
        x = BE.eps(cours, k)
        (t1, r1), (t2, r2) = x["course"], x["deux"]
        d.update(contexte="Ton école organise une séance d'évaluation en éducation physique et sportive. Le maître veut connaître le niveau de chacun.",
                 tache=f"Tu es invité à réaliser deux épreuves : {t1.lower()} et {t2[0].lower() + t2[1:]}.", support_titre="Guide d'administration",
                 support=("Avant : nettoyer et tracer le terrain (couloirs, aire de saut ou de lancer), vérifier le matériel (chronomètre, décamètre, balles, "
                          "sifflet), préparer la fiche de notation. Pendant : appel, échauffement de dix minutes, rappel des consignes de sécurité "
                          f"(rester dans son couloir, ne pas lancer quand un camarade est dans l'aire). {t1} : {r1} {t2} : {r2} Après : traduire chaque "
                          "performance en note avec le barème du sexe et de l'âge de l'élève, puis reporter sur la fiche de notation."),
                 consignes=[{"titre": "Consigne", "questions": [{"q": f"1- {t1} : cours le plus vite possible dans ton couloir jusqu'à la ligne d'arrivée.", "r": "", "pts": 10},
                                                                {"q": f"2- {t2} : réalise l'épreuve selon les règles données par le maître.", "r": "", "pts": 10}]}],
                 baremes=x["baremes"], fiche_notation={"colonnes": BE.FICHE_COLONNES, "lignes": 22}, age_normal=x["age"])
        d["grille"] = [{"critere": f"Épreuve 1 — {t1} : performance traduite par le barème (sexe, âge)", "indicateurs": [x["baremes"][0]["titre"]], "points": 10},
                       {"critere": f"Épreuve 2 — {t2} : " + ("grille d'observation" if x["type2"] == "jeu" else "performance traduite par le barème (sexe, âge)"),
                        "indicateurs": [x["baremes"][1]["titre"]], "points": 10}]
        d["corrige_note"] = (f"Épreuve pratique. Âge normal au {cours} : {x['age']} ans ; la colonne « âge + 2 » s'applique aux élèves de deux ans de plus "
                             "ou davantage. Un élève dispensé (certificat médical) n'est pas noté. Barèmes indicatifs, à adapter par le conseil des maîtres.")
    elif c == "dictee":
        titre, texte, qs = BD.dictee(cours, per)
        if cours == "CI":
            elems = [x.strip() for x in texte.split("/") if x.strip()]
            d.update(contexte="Le maître dit chaque élément deux fois, en articulant bien ; l'élève l'écrit sur la ligne.",
                     tache="Tu es invité à écrire ce que le maître dicte.", support_titre=titre, support=" / ".join(elems),
                     consignes=[{"titre": "Consigne", "questions": [{"q": f"Écris l'élément n° {i} dicté par le maître.", "r": x, "pts": p}
                                                                    for i, (x, p) in enumerate(zip(elems, repartir(20, len(elems))), 1)]}])
            d["grille"] = [{"critere": "Exactitude de l'écriture", "indicateurs": BD.BAREME_CI, "points": 20}]
        else:
            pd = 20 if not qs else 14
            cons = [{"titre": "Dictée", "questions": [{"q": "Écris le texte dicté.", "r": texte, "pts": pd}]}]
            if qs:
                cons.append({"titre": "Questions", "questions": [{"q": q_, "r": r_, "pts": 2} for q_, r_ in qs]})
            d.update(contexte="Le maître lit d'abord tout le texte, puis le dicte par groupes de mots, enfin le relit ; l'élève se relit avant de rendre sa copie.",
                     tache="Tu es invité à écrire le texte sous la dictée" + (" puis à répondre aux questions." if qs else "."), support_titre=titre, support=texte,
                     consignes=cons, mots=len(texte.split()))
            d["grille"] = [{"critere": f"Dictée (sur {pd})", "indicateurs": BD.BAREME_FAUTES, "points": pd}]
            if qs:
                d["grille"].append({"critere": "Questions (3 × 2 points)", "indicateurs": [r_ for _q, r_ in qs], "points": 6})
        d["progression"] = [prog.get("francais", {}).get("refs", "")]
    if d.get("infre"):
        d["source"] = f"D'après les épreuves standardisées INFRE ({d['infre']}) — reformulée (contexte et support nouveaux)"
    return d


def jeu_complet(cours, per, prog):
    _c, _l, typ, _m = PER[per]
    return [generer(cours, per, e, prog) for e in organigramme(cours, typ)]


def total_bareme(d):
    return round(sum(q["pts"] or 0 for it in d.get("consignes", []) for q in it["questions"]) or sum(g["points"] for g in d.get("grille", [])), 1)
