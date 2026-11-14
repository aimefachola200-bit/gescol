# -*- coding: utf-8 -*-
"""Cahier d'exercices de Français CP (original, 70 leçons) qui suit la progression du cahier d'activités officiel (édition 2022).
Les exercices, mots et phrases sont écrits pour GESCOL / Scolaris : ils ne reprennent pas le texte du cahier officiel.
Chaque leçon : 1 entoure · 2 copie · 3 associe les syllabes et lis · 4 écris le mot · 5 dictée (ou exercice de grammaire)."""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from cahier_cp_progression import LECONS

# n : (sons à entourer, [mots syllabés])
SONS = {
    1: (["a", "o", "l"], ["a-la", "lo-la", "la-o", "a-lo", "la-la", "o-la"]),
    3: (["e", "u", "j"], ["ju-pe", "lu-ne", "re-pas", "ju-lo", "lu-ne", "pu-ce"]),
    4: (["é", "i", "t"], ["é-té", "té-lé", "ti-ti", "é-lu", "pé-ti", "li-té"]),
    5: (["e", "t", "d", "s"], ["li-t", "ni-d", "ta-pis", "ra-t", "pi-le", "é-co-le"]),
    6: (["è", "ê"], ["tê-te", "fê-te", "é-lè-ve", "mè-re", "rê-ve", "pè-re"]),
    7: (["m", "n"], ["mo-to", "ma-ma", "na-ne", "a-na-nas", "mu-le", "ni-d"]),
    9: (["b", "d"], ["ba-na-ne", "bé-bé", "da-te", "do-mi-no", "bu-lle", "dé-bu-t"]),
    10: (["p", "q"], ["pa-pa", "pa-ta-te", "co-q", "pi-pe", "é-qui-pe", "pa-ni-er"]),
    12: (["s", "r"], ["sa-la-de", "ra-di-o", "ro-be", "sa-me-di", "ra-pi-de", "si-rop"]),
    13: (["a", "o", "l", "e", "u", "j", "é", "i", "t"], ["mo-to", "a-na-nas", "lu-ne", "té-lé", "ju-pe", "o-li-ve"]),
    14: (["m", "n", "b", "d", "p", "q", "s", "r"], ["pa-ta-te", "pé-da-le", "sa-la-de", "mi-di", "mo-to", "ra-di-o"]),
    15: (["f", "v"], ["fê-te", "fa-ri-ne", "vé-lo", "vi-te", "vi-dé-o", "fu-sée"]),
    17: (["c", "k"], ["ca-fé", "ké-pi", "co-co", "é-co-le", "ka-ri-té", "cu-lo-te"]),
    18: (["qu"], ["é-qui-pe", "mas-que", "nu-que", "qui-ni-ne", "qua-tre", "ma-qui"]),
    20: (["g", "gu"], ["ga-ri", "fa-got", "gui-ta-re", "guê-pe", "ga-re", "gui-de"]),
    21: (["y", "w", "z"], ["pa-pa-ye", "yo-ga", "zé-bu", "ki-wi", "zè-le", "Wa-bi"]),
    23: (["ou"], ["bou-bou", "sou-ris", "pou-le", "sou-pe", "cou-de", "bou-le"]),
    24: (["eu"], ["feu", "jeu", "meu-le", "neu-ve", "jeu-di", "veu-ve"]),
    26: (["on", "om"], ["mou-ton", "co-ton", "gom-bo", "pom-pe", "me-lon", "ron-de"]),
    27: (["f", "v", "c", "k", "qu", "g", "gu"], ["ga-ri", "vé-lo", "ké-pi", "co-la", "fê-te", "gui-ta-re"]),
    28: (["y", "w", "z", "ou", "eu", "on", "om"], ["mou-ton", "pom-pe", "zé-bu", "bou-bou", "meu-le", "yo-ga"]),
    29: (["au", "eau"], ["cau-ris", "jau-ne", "ca-deau", "ri-deau", "au-to", "ba-teau"]),
    31: (["ai", "ei"], ["ba-lai", "mai-re", "sei-ze", "rei-ne", "gai-té", "lai-t"]),
    32: (["g (= /j/)"], ["pa-ge", "ge-nou", "ca-ge", "sa-ge", "rou-ge", "bou-gie"]),
    34: (["pl", "bl", "cl", "gl", "fl"], ["ta-ble", "rè-gle", "fla-con", "sa-ble", "clé", "pla-t"]),
    35: (["gr", "fr", "tr", "dr", "cr"], ["gra-ve", "fro-ma-ge", "tri-cot", "dra-peau", "cra-be", "pou-dre"]),
    37: (["in", "ein", "ain"], ["la-pin", "pain", "pein-tre", "sin-ge", "ma-tin", "de-main"]),
    38: (["an", "en"], ["pan-ta-lon", "tan-te", "dent", "men-ton", "en-fant", "dan-se"]),
    40: (["h", "ch"], ["hou-e", "ha-bit", "che-val", "chat", "cha-peau", "va-che"]),
    41: (["au", "eau", "ai", "ei", "g (= /j/)", "pl", "bl", "cl", "gl", "fl"], ["ta-ble", "cau-ris", "ba-lai", "cla-ve", "fla-con", "ca-deau"]),
    42: (["gr", "fr", "tr", "dr", "cr", "in", "ein", "ain", "an", "en", "h", "ch"], ["la-pin", "gran-d", "pan-ta-lon", "cha-t", "pein-tre", "ha-bit"]),
    43: (["ph"], ["pho-to", "pha-re", "é-lé-phant", "si-phon", "So-phie", "al-pha"]),
    45: (["oi"], ["voi-le", "toit", "joie", "voi-tu-re", "froid", "noi-re"]),
    46: (["gn"], ["i-gna-me", "pa-gne", "pei-gne", "si-gnal", "ga-gne", "li-gne"]),
    48: (["s (= /z/)"], ["oi-seau", "va-se", "ca-se", "ti-sa-ne", "va-li-se", "ro-se"]),
    49: (["oir", "oire"], ["mi-roir", "ra-soir", "ar-moi-re", "dé-voir", "glo-i-re", "sa-voir"]),
    51: (["x"], ["ta-xi", "bo-xe", "si-xiè-me", "deu-xiè-me", "Xa-vier", "ex-pli-quer"]),
    52: (["ç", "c (= /s/)"], ["gar-çon", "le-çon", "ci-tron", "fa-ce", "re-çu", "ma-çon"]),
    54: (["eur"], ["cou-leur", "fleur", "chan-teur", "dan-seur", "jou-eur", "pe-ur"]),
    55: (["ph", "oi", "gn", "s (= /z/)"], ["pho-to", "voi-le", "pa-gne", "va-se", "pha-re", "i-gna-me"]),
    56: (["oir", "oire", "ç", "c (= /s/)", "eur", "x"], ["mi-roir", "ar-moi-re", "gar-çon", "cou-leur", "ta-xi", "ci-tron"]),
    57: (["oin"], ["coin", "soin", "be-soin", "poin-te", "té-moin", "loin"]),
    59: (["ille"], ["fi-lle", "bi-lle", "fa-mi-lle", "co-qui-lle", "gen-ti-lle", "len-ti-lle"]),
    60: (["ail", "aille"], ["por-tail", "tra-vail", "mé-dai-lle", "vo-lai-lle", "bé-tail", "é-ven-tail"]),
    62: (["ien"], ["chien", "bien", "rien", "gar-dien", "com-bien", "Da-mien"]),
    63: (["er", "ez"], ["pa-nier", "nez", "dan-ser", "sau-ter", "chez", "ve-nez"]),
    65: (["y (= /i/)", "y (= /ii/)"], ["py-ja-ma", "sty-lo", "cra-yon", "tuyau", "go-ya-ve", "es-sa-yer"]),
    66: (["tion"], ["o-pé-ra-tion", "ac-tion", "ra-tion", "por-tion", "na-tion", "ad-di-tion"]),
    68: (["eil", "eille"], ["so-leil", "ré-veil", "a-beil-le", "bou-teil-le", "or-teil", "cor-beil-le"]),
    69: (["oin", "ille", "ail", "aille", "ien"], ["poin-te", "fa-mil-le", "por-tail", "chien", "mé-dail-le", "coin"]),
    70: (["er", "ez", "y", "tion", "eil", "eille"], ["a-beil-le", "so-leil", "py-ja-ma", "ac-tion", "ve-nez", "dan-ser"]),
}

# leçons de grammaire / écriture : (consigne, [(phrase à trous, réponse)])
GRAM = {
    2: ("Écris le, la ou l' devant chaque nom.", [("____ vélo", "le"), ("____ règle", "la"), ("____ ananas", "l'"), ("____ moto", "la")]),
    8: ("Écris un, une ou des devant chaque nom.", [("____ balai", "un"), ("____ robe", "une"), ("____ livres", "des"), ("____ vélo", "un")]),
    11: ("Mets un point à la fin de chaque phrase. Recopie la phrase.", [("Lola va à l'école", "."), ("Awa a une robe", "."), ("La moto est jolie", ".")]),
    16: ("Écris le, la ou les devant chaque nom.", [("____ sac", "le"), ("____ radio", "la"), ("____ livres", "les"), ("____ règles", "les")]),
    19: ("Complète par suis, es ou est.", [("Je ____ à l'école.", "suis"), ("Tu ____ un élève.", "es"), ("Elle ____ contente.", "est")]),
    22: ("Complète par sommes, êtes ou sont.", [("Nous ____ des élèves.", "sommes"), ("Vous ____ à l'école.", "êtes"), ("Ils ____ contents.", "sont")]),
    25: ("Complète par ai, as ou a.", [("J' ____ un sac.", "ai"), ("Tu ____ un sac.", "as"), ("Il ____ un sac.", "a")]),
    30: ("Complète par avons, avez ou ont.", [("Nous ____ une télé.", "avons"), ("Vous ____ une télé.", "avez"), ("Elles ____ une télé.", "ont")]),
    33: ("Complète par un point (.) ou une virgule (,).", [("Le dimanche je ne vais pas à l'école ___", "."), ("À l'école___ Toni lit ___", ", puis .")]),
    36: ("Complète par ? ou !.", [("Qui est Wabi ___", "?"), ("Oh ___ Il est beau.", "!"), ("Bravo Wabi ___", "!")]),
    39: ("Complète par mon, ton ou son.", [("Je lave ____ vélo.", "mon"), ("Tu as mis ____ chapeau.", "ton"), ("Il prend ____ livre.", "son")]),
    44: ("Complète par ma, ta ou sa.", [("Je porte ____ jupe.", "ma"), ("Tu portes ____ tenue.", "ta"), ("Elle lave ____ robe.", "sa")]),
    47: ("Complète par mes, tes ou ses.", [("Je lave ____ mains.", "mes"), ("Tu ranges ____ livres.", "tes"), ("Il appelle ____ amis.", "ses")]),
    50: ("Complète le verbe manger.", [("Je ____ du riz.", "mange"), ("Tu ____ du riz.", "manges"), ("Elle ____ du riz.", "mange")]),
    53: ("Écris la phrase négative avec ne ... pas ou n' ... pas.", [("Toto joue dans la rue. Toto ____ joue ____ dans la rue.", "ne ... pas"),
                                                                     ("Pipo ira à la fête. Pipo ____ ira ____ à la fête.", "n' ... pas")]),
    58: ("Écris il ou elle.", [("Ali a faim, ____ mange.", "il"), ("Fèmi a soif, ____ boit de l'eau.", "elle"), ("Lili va à l'école, ____ pédale vite.", "elle")]),
    61: ("Complète par lui.", [("Maman ____ donne de l'eau.", "lui"), ("Papa ____ donne un cadeau.", "lui")]),
    64: ("Complète par grand, grande, petit ou petite.", [("Papa est ____.", "grand"), ("Maman est ____.", "grande"), ("Fèmi est ____.", "petite")]),
    67: ("Complète par vais, vas ou va.", [("Je ____ à l'école.", "vais"), ("Tu ____ à l'école.", "vas"), ("Elle ____ à l'école.", "va")]),
}


def _mot(syllabes):
    return syllabes.replace("-", "")


def _lignes(c, x, y, largeur, n=1, hauteur=8 * mm):
    c.setLineWidth(0.4)
    c.setDash(1, 2)
    for i in range(n):
        yy = y - i * hauteur
        c.line(x, yy, x + largeur, yy)
    c.setDash()


def _entete(c, num, titre, avec_reponses):
    c.setFont("Helvetica-Bold", 15)
    c.setFillGray(0.1)
    c.drawString(20 * mm, 277 * mm, f"Leçon {num} : {titre}")
    c.setLineWidth(1)
    c.line(20 * mm, 274 * mm, 190 * mm, 274 * mm)
    c.setFont("Helvetica", 8)
    c.drawRightString(190 * mm, 283 * mm, "Cahier d'exercices de Français CP" + (" — Corrigé de l'enseignant" if avec_reponses else ""))
    c.drawString(20 * mm, 283 * mm, "Nom : ______________________   Date : ______________")


def _page_son(c, num, titre, sons, mots, corrige):
    y = 266 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "1. Entoure le(s) son(s) de la leçon dans les mots :")
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 22)
    c.drawString(24 * mm, y - 4 * mm, "   ".join(sons)[:46])
    y -= 14 * mm
    c.setFont("Helvetica", 16)
    for i, m in enumerate(mots):
        c.drawString(24 * mm + (i % 3) * 56 * mm, y - (i // 3) * 10 * mm, _mot(m))
    y -= 26 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "2. Copie les sons et les mots :")
    y -= 9 * mm
    for s in sons[:2]:
        c.setFont("Helvetica", 18)
        c.drawString(24 * mm, y + 1 * mm, s)
        _lignes(c, 40 * mm, y, 140 * mm)
        y -= 10 * mm
    for m in mots[:2]:
        c.setFont("Helvetica", 18)
        c.drawString(24 * mm, y + 1 * mm, _mot(m))
        _lignes(c, 72 * mm, y, 108 * mm)
        y -= 10 * mm
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "3. Associe les syllabes et lis :")
    y -= 9 * mm
    for m in mots[:4]:
        c.setFont("Helvetica", 16)
        c.drawString(24 * mm, y, "  +  ".join(m.split("-")) + "  =")
        if corrige:
            c.setFillGray(0.35); c.drawString(110 * mm, y, _mot(m)); c.setFillGray(0.1)
        else:
            _lignes(c, 110 * mm, y - 1 * mm, 70 * mm)
        y -= 10 * mm
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "4. Lis puis écris les mots en séparant les syllabes :")
    y -= 9 * mm
    for m in mots[4:6]:
        c.setFont("Helvetica", 16)
        c.drawString(24 * mm, y, _mot(m) + "  =")
        if corrige:
            c.setFillGray(0.35); c.drawString(80 * mm, y, " – ".join(m.split("-"))); c.setFillGray(0.1)
        else:
            _lignes(c, 80 * mm, y - 1 * mm, 100 * mm)
        y -= 10 * mm
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "5. Écris sous la dictée :")
    y -= 9 * mm
    _lignes(c, 20 * mm, y, 170 * mm, 2, 10 * mm)
    if corrige:
        c.setFont("Helvetica", 9); c.setFillGray(0.35)
        c.drawString(20 * mm, y - 24 * mm, "Dictée proposée : " + ", ".join(_mot(m) for m in mots[:4]) + ".")
        c.setFillGray(0.1)


def _page_gram(c, num, titre, consigne, items, corrige):
    y = 266 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "1. " + consigne)
    y -= 12 * mm
    for ph, rep in items:
        c.setFont("Helvetica", 15)
        c.drawString(24 * mm, y, ph.replace("___", "...") if corrige is False else ph)
        if corrige:
            c.setFillGray(0.35); c.setFont("Helvetica-Bold", 11); c.drawString(24 * mm, y - 6 * mm, "Réponse : " + rep); c.setFillGray(0.1)
            y -= 6 * mm
        y -= 12 * mm
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "2. Recopie chaque phrase complète :")
    y -= 10 * mm
    _lignes(c, 20 * mm, y, 170 * mm, 3, 10 * mm)
    y -= 38 * mm
    c.drawString(20 * mm, y, "3. Écris sous la dictée :")
    y -= 10 * mm
    _lignes(c, 20 * mm, y, 170 * mm, 3, 10 * mm)


def pdf(corrige=False):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Cahier d'exercices de Français CP")
    # page de garde
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(105 * mm, 200 * mm, "Cahier d'exercices")
    c.drawCentredString(105 * mm, 188 * mm, "de Français — CP")
    c.setFont("Helvetica", 12)
    c.drawCentredString(105 * mm, 170 * mm, "70 leçons : lettres, sons, mots, phrases, dictées")
    c.drawCentredString(105 * mm, 162 * mm, "Progression alignée sur le cahier d'activités officiel du CP (édition 2022)")
    if corrige:
        c.setFont("Helvetica-Bold", 14); c.drawCentredString(105 * mm, 140 * mm, "Corrigé de l'enseignant")
    c.setFont("Helvetica", 9)
    c.drawCentredString(105 * mm, 30 * mm, "Exercices originaux GESCOL / Scolaris. Ils accompagnent le livre de lecture décodable et le cahier officiel.")
    c.showPage()
    for num, titre, _page in LECONS:
        _entete(c, num, titre, corrige)
        if num in GRAM:
            cons, items = GRAM[num]
            _page_gram(c, num, titre, cons, items, corrige)
        else:
            sons, mots = SONS[num]
            _page_son(c, num, titre, sons, mots, corrige)
        c.setFont("Helvetica", 8)
        c.drawCentredString(105 * mm, 10 * mm, f"CP – Français – leçon {num}")
        c.showPage()
    c.save()
    return buf.getvalue()
