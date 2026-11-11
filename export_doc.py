# -*- coding: utf-8 -*-
"""v2.2 — Télécharger en PDF ou en Word (.docx) le contenu d'une page, sans dépendance extérieure.

Sur Android, « Imprimer » du navigateur intégré n'enregistre pas de fichier : chaque page de pédagogie (et les pages
qui n'avaient qu'un bouton « Imprimer ») propose donc « Télécharger PDF » et « Télécharger Word ».

* ``blocs(html)``       : découpe un fragment HTML simple (titres, paragraphes, listes, tableaux, gras / italique /
  souligné, sauts de page) en blocs ;
* ``docx(blocs, …)``     : écrit un vrai document Word (.docx, WordprocessingML) avec ``zipfile`` seul — pas de
  python-docx ni de lxml, qui ne s'installent pas dans l'application Android autonome ;
* ``pdf(blocs, …)``      : même contenu en PDF (ReportLab, police Times New Roman 14 pt) ;
* ``html_vers_docx(html)`` : conversion directe des anciens fichiers « .doc » (HTML) en .docx.
"""
import html as _html
import io
import re
import zipfile
from html.parser import HTMLParser
from xml.sax.saxutils import escape as _x

# éléments ignorés avec tout leur contenu (boutons, formulaires, menus, scripts)
_IGNORES = {"script", "style", "nav", "button", "select", "textarea", "form", "svg", "noscript", "template", "head",
            "dialog", "iframe", "object", "canvas", "video", "audio"}
# classes d'éléments à ne pas exporter (mêmes règles que l'impression)
_CLASSES_IGNOREES = {"no-print", "noprint", "ev-noprint", "actions", "retour-ligne", "btn", "btn-retour", "flash",
                     "export-barre", "filtres", "pagination", "onglets", "prep-onglets", "aide-sec", "bandeau"}
_VIDES = {"br", "img", "hr", "input", "meta", "link", "col", "area", "base", "source", "wbr"}
_TITRES = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}


class _Analyse(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocs = []
        self.runs = None          # paragraphe en cours : [(texte, gras, italique, souligne)]
        self.genre = ("p",)
        self.pile_style = []      # (balise, gras, italique, souligne)
        self.ignore = 0
        self.pile = []            # balises ouvertes (pour savoir lesquelles ferment un élément ignoré)
        self.listes = []          # "ul" / "ol" + compteur
        self.table = None         # [[cellule]] ; cellule = {"runs": [...], "th": bool}
        self.cellule = None
        self.saut = False

    # -- style courant
    def _style(self):
        g = i = s = False
        for _b, bg, bi, bs in self.pile_style:
            g, i, s = g or bg, i or bi, s or bs
        return g, i, s

    def _flush(self):
        if self.cellule is not None:
            return
        if self.runs and "".join(r[0] for r in self.runs).strip():
            self.blocs.append({"type": self.genre[0], "niveau": self.genre[1] if len(self.genre) > 1 else 0,
                               "runs": _nettoyer(self.runs), "saut": self.saut,
                               "puce": self.genre[2] if len(self.genre) > 2 else None})
            self.saut = False
        self.runs = None

    def _texte(self, t):
        if self.cellule is not None:
            self.cellule["runs"].append((t,) + self._style())
            return
        if self.runs is None:
            self.runs = []
        self.runs.append((t,) + self._style())

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        style = (a.get("style") or "").replace(" ", "").lower()
        if tag not in _VIDES:
            self.pile.append(tag)
        if self.ignore:
            if tag not in _VIDES:
                self.ignore += 1
            return
        if tag in _IGNORES or classes & _CLASSES_IGNOREES or "display:none" in style or a.get("hidden") is not None \
                or a.get("aria-hidden") == "true":
            if tag not in _VIDES:
                self.ignore = 1
            return
        if "page-break-before:always" in style or "break-before:page" in style:
            self._flush()
            self.saut = True
        if tag in _TITRES:
            self._flush()
            self.genre = ("h", _TITRES[tag])
        elif tag in ("p", "div", "section", "article", "header", "footer", "blockquote", "figure", "figcaption",
                     "details", "summary", "dt", "dd", "pre", "address", "fieldset", "legend", "label", "main"):
            self._flush()
            self.genre = ("p",)
        elif tag in ("ul", "ol"):
            self._flush()
            self.listes.append([tag, 0])
        elif tag == "li":
            self._flush()
            if self.listes:
                self.listes[-1][1] += 1
                lst = self.listes[-1]
                self.genre = ("li", len(self.listes), f"{lst[1]}." if lst[0] == "ol" else "•")
            else:
                self.genre = ("li", 1, "•")
        elif tag == "table":
            self._flush()
            self.table = {"lignes": [], "saut": self.saut}
            self.saut = False
        elif tag == "tr" and self.table is not None:
            self.table["lignes"].append([])
        elif tag in ("td", "th") and self.table is not None:
            if not self.table["lignes"]:
                self.table["lignes"].append([])
            self.cellule = {"runs": [], "th": tag == "th",
                            "colspan": int(a.get("colspan") or 1) if str(a.get("colspan") or "1").isdigit() else 1}
            self.table["lignes"][-1].append(self.cellule)
        elif tag == "br":
            if "page-break-before:always" in style:
                return
            self._texte("\n")
        elif tag == "hr":
            self._flush()
        elif tag in ("b", "strong", "th"):
            self.pile_style.append((tag, True, False, False))
        elif tag in ("i", "em", "cite"):
            self.pile_style.append((tag, False, True, False))
        elif tag == "u":
            self.pile_style.append((tag, False, False, True))
        elif tag == "img":
            alt = a.get("alt")
            if alt and len(alt) < 60 and self.cellule is not None:
                self._texte(alt)

    def handle_endtag(self, tag):
        if tag in _VIDES:
            return
        # retrouver la balise ouverte correspondante (HTML parfois mal fermé)
        if tag in self.pile:
            while self.pile:
                t = self.pile.pop()
                if self.ignore:
                    self.ignore -= 1
                    if t == tag:
                        return
                    continue
                self._fermer(t)
                if t == tag:
                    break

    def _fermer(self, tag):
        if tag in _TITRES or tag in ("p", "div", "section", "article", "header", "footer", "blockquote", "li",
                                      "figure", "figcaption", "details", "summary", "dt", "dd", "pre", "address",
                                      "fieldset", "legend", "label", "main"):
            self._flush()
            self.genre = ("p",)
        elif tag in ("ul", "ol"):
            self._flush()
            if self.listes:
                self.listes.pop()
        elif tag in ("td", "th"):
            if self.cellule is not None:
                self.cellule["runs"] = _nettoyer(self.cellule["runs"])
            self.cellule = None
        elif tag == "table" and self.table is not None:
            lignes = [l for l in self.table["lignes"] if l]
            if lignes:
                self.blocs.append({"type": "table", "lignes": lignes, "saut": self.table["saut"]})
            self.table = None
        if self.pile_style and self.pile_style[-1][0] == tag:
            self.pile_style.pop()
        elif tag in ("b", "strong", "i", "em", "cite", "u", "th"):
            for k in range(len(self.pile_style) - 1, -1, -1):
                if self.pile_style[k][0] == tag:
                    del self.pile_style[k]
                    break

    def handle_data(self, data):
        if self.ignore:
            return
        if self.table is not None and self.cellule is None:
            return  # espaces entre cellules
        self._texte(data)

    def close(self):
        super().close()
        self._flush()


def _nettoyer(runs):
    """Espaces multiples réduits, retours à la ligne gardés (balise <br>)."""
    out = []
    for t, g, i, s in runs:
        parties = t.split("\n")
        t2 = "\n".join(re.sub(r"[ \t\r\f\v]+", " ", p) for p in parties)
        if t2:
            out.append((t2, g, i, s))
    # pas d'espace en début ni en fin de bloc
    if out:
        out[0] = (out[0][0].lstrip(" "),) + out[0][1:]
        out[-1] = (out[-1][0].rstrip(" "),) + out[-1][1:]
    return [r for r in out if r[0]]


def blocs(html):
    """Blocs d'un fragment HTML : titres, paragraphes, éléments de liste, tableaux."""
    a = _Analyse()
    a.feed(html or "")
    a.close()
    return a.blocs


def contenu_principal(page_html):
    """Le contenu de <main> d'une page complète de l'application (sans en-tête, menu ni pied)."""
    m = re.search(r"<main\b[^>]*>(.*)</main>", page_html or "", re.S | re.I)
    return m.group(1) if m else (page_html or "")


def titre_page(page_html):
    """Titre de la page : le titre de l'onglet (« Fiches de préparation – sigle » -> « Fiches de préparation »), sinon h1."""
    def propre(t):
        return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", t))).strip()
    m = re.search(r"<title>(.*?)</title>", page_html or "", re.S | re.I)
    if m:
        t = propre(m.group(1)).split(" – ")[0].strip()
        if t and t.upper() not in ("SCOLARIS", "GESCOL"):
            return t
    m = re.search(r"<h1\b[^>]*>(.*?)</h1>", page_html or "", re.S | re.I)
    return propre(m.group(1)) if m else "Document"


def texte_runs(runs):
    return "".join(r[0] for r in runs)


# ------------------------------------------------------------------ Word (.docx)
_POLICE = "Times New Roman"


def _run_xml(t, g, i, s, taille=28):
    rpr = f'<w:rFonts w:ascii="{_POLICE}" w:hAnsi="{_POLICE}" w:cs="{_POLICE}"/>' + ("<w:b/>" if g else "") + \
          ("<w:i/>" if i else "") + ('<w:u w:val="single"/>' if s else "") + f'<w:sz w:val="{taille}"/><w:szCs w:val="{taille}"/>'
    morceaux = t.split("\n")
    xml = []
    for k, m in enumerate(morceaux):
        if k:
            xml.append("<w:br/>")
        if m:
            xml.append(f'<w:t xml:space="preserve">{_x(m)}</w:t>')
    return f"<w:r><w:rPr>{rpr}</w:rPr>{''.join(xml)}</w:r>" if xml else ""


def _para_xml(runs, style=None, centre=False, saut=False, retrait=0, puce=None, taille=28, gras=False):
    ppr = ""
    if style:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if saut:
        ppr += "<w:pageBreakBefore/>"
    ppr += '<w:spacing w:after="80"/>'
    if retrait:
        ppr += f'<w:ind w:left="{retrait}" w:hanging="280"/>'
    if centre:
        ppr += '<w:jc w:val="center"/>'
    corps = ""
    if puce:
        corps += _run_xml(puce + " ", False, False, False, taille)
    corps += "".join(_run_xml(t, g or gras, i, s, taille) for t, g, i, s in runs)
    return f"<w:p><w:pPr>{ppr}</w:pPr>{corps}</w:p>"


def _table_xml(lignes, taille=24):
    ncol = max(sum(c.get("colspan", 1) for c in l) for l in lignes)
    largeur = 9638  # 17 cm en vingtièmes de point
    w = largeur // max(ncol, 1)
    grille = "".join(f'<w:gridCol w:w="{w}"/>' for _ in range(ncol))
    bord = '<w:{0} w:val="single" w:sz="4" w:space="0" w:color="666666"/>'
    tblpr = ('<w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>' + "".join(bord.format(b) for b in
             ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders><w:tblLayout w:type="autofit"/></w:tblPr>')
    lignes_xml = []
    for l in lignes:
        cells = []
        for c in l:
            span = c.get("colspan", 1)
            tcpr = f'<w:tcW w:w="{w * span}" w:type="dxa"/>' + (f'<w:gridSpan w:val="{span}"/>' if span > 1 else "") + \
                   ('<w:shd w:val="clear" w:color="auto" w:fill="E4ECF5"/>' if c.get("th") else "")
            paras = _para_xml(c["runs"], taille=taille, gras=c.get("th"))
            cells.append(f"<w:tc><w:tcPr>{tcpr}</w:tcPr>{paras}</w:tc>")
        manque = ncol - sum(c.get("colspan", 1) for c in l)
        for _ in range(max(manque, 0)):
            cells.append(f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/></w:tcPr><w:p/></w:tc>')
        entete = '<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>' if l and all(c.get("th") for c in l) else '<w:trPr><w:cantSplit/></w:trPr>'
        lignes_xml.append(f"<w:tr>{entete}{''.join(cells)}</w:tr>")
    return f"<w:tbl>{tblpr}<w:tblGrid>{grille}</w:tblGrid>{''.join(lignes_xml)}</w:tbl><w:p/>"


def docx(liste_blocs, titre="Document", pied=None):
    """Document Word (.docx) : Times New Roman 14 pt, titres en gras, tableaux bordés, en-têtes de tableau répétés."""
    corps = []
    deja_titre = any(b["type"] == "h" and b.get("niveau") == 1 for b in liste_blocs)
    if not deja_titre and titre:
        corps.append(_para_xml([(titre, True, False, False)], centre=True, taille=32))
    for b in liste_blocs:
        if b["type"] == "h":
            n = b.get("niveau", 2)
            taille = {1: 32, 2: 30, 3: 28}.get(n, 28)
            corps.append(_para_xml(b["runs"], style=f"Titre{min(n, 3)}", centre=n == 1, saut=b.get("saut"), taille=taille, gras=True))
        elif b["type"] == "li":
            corps.append(_para_xml(b["runs"], saut=b.get("saut"), retrait=360 * b.get("niveau", 1), puce=b.get("puce") or "•"))
        elif b["type"] == "table":
            if b.get("saut"):
                corps.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
            corps.append(_table_xml(b["lignes"]))
        else:
            corps.append(_para_xml(b["runs"], saut=b.get("saut")))
    pied_xml = ""
    rel_pied = ""
    ct_pied = ""
    fichiers = {}
    if pied:
        fichiers["word/footer1.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            + _para_xml([(pied, False, False, False)], centre=True, taille=15) + "</w:ftr>")
        pied_xml = '<w:footerReference w:type="default" r:id="rIdPied"/>'
        rel_pied = ('<Relationship Id="rIdPied" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
                    'Target="footer1.xml"/>')
        ct_pied = '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
    sect = (f'<w:sectPr>{pied_xml}<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="454" w:gutter="0"/></w:sectPr>')
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f"<w:body>{''.join(corps)}{sect}</w:body></w:document>")
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{_POLICE}" w:hAnsi="{_POLICE}" w:cs="{_POLICE}" w:eastAsia="{_POLICE}"/>'
              '<w:sz w:val="28"/><w:szCs w:val="28"/><w:lang w:val="fr-FR"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="259" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              + "".join(f'<w:style w:type="paragraph" w:styleId="Titre{n}"><w:name w:val="heading {n}"/><w:basedOn w:val="Normal"/>'
                        f'<w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/>'
                        f'<w:outlineLvl w:val="{n - 1}"/></w:pPr><w:rPr><w:b/><w:color w:val="1F4E79"/></w:rPr></w:style>' for n in (1, 2, 3))
              + "</w:styles>")
    rels_doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                f"{rel_pied}</Relationships>")
    types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
             '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
             f"{ct_pied}</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            "</Relationships>")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + _x(titre or "") + "</dc:title><dc:language>fr-FR</dc:language></cp:coreProperties>")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/_rels/document.xml.rels", rels_doc)
        for nom, contenu in fichiers.items():
            z.writestr(nom, contenu)
    return out.getvalue()


def html_vers_docx(html, titre="Document", pied=None):
    m = re.search(r"<body\b[^>]*>(.*)</body>", html or "", re.S | re.I)
    return docx(blocs(m.group(1) if m else html), titre, pied)


# ------------------------------------------------------------------ PDF
def pdf(liste_blocs, titre="Document", pied=None):
    """Même contenu en PDF A4 : Times New Roman 14 pt (Liberation Serif), tableaux bordés, en-têtes répétés."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    import pdfs
    f = pdfs.police_serif()
    base = ParagraphStyle("n", fontName=f["normal"], fontSize=14, leading=18, spaceAfter=4)
    cel = ParagraphStyle("c", parent=base, fontSize=11.5, leading=14, spaceAfter=0)
    tit = {1: ParagraphStyle("h1", parent=base, fontName=f["gras"], fontSize=17, leading=21, alignment=TA_CENTER,
                             textColor=colors.HexColor("#1F4E79"), spaceAfter=8),
           2: ParagraphStyle("h2", parent=base, fontName=f["gras"], fontSize=15.5, leading=19, textColor=colors.HexColor("#1F4E79"),
                             spaceBefore=6),
           3: ParagraphStyle("h3", parent=base, fontName=f["gras"], fontSize=14.5, leading=18, spaceBefore=4)}

    def markup(runs):
        out = []
        for t, g, i, s in runs:
            e = _x(t).replace("\n", "<br/>")
            if s:
                e = f"<u>{e}</u>"
            if i:
                e = f"<i>{e}</i>"
            if g:
                e = f"<b>{e}</b>"
            out.append(e)
        return "".join(out) or "&nbsp;"

    histoire = []
    if titre and not any(b["type"] == "h" and b.get("niveau") == 1 for b in liste_blocs):
        histoire.append(Paragraph(_x(titre), tit[1]))
    largeur = A4[0] - 3.4 * cm
    for b in liste_blocs:
        if b.get("saut") and histoire:
            histoire.append(PageBreak())
        if b["type"] == "h":
            histoire.append(Paragraph(markup(b["runs"]), tit.get(min(b.get("niveau", 2), 3))))
        elif b["type"] == "li":
            st = ParagraphStyle("li", parent=base, leftIndent=14 * b.get("niveau", 1), bulletIndent=14 * b.get("niveau", 1) - 10)
            histoire.append(Paragraph(markup(b["runs"]), st, bulletText=b.get("puce") or "•"))
        elif b["type"] == "table":
            ncol = max(sum(c.get("colspan", 1) for c in l) for l in b["lignes"])
            data, styles = [], [("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#666666")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
            for r, l in enumerate(b["lignes"]):
                ligne, col = [], 0
                for c in l:
                    st = ParagraphStyle("th", parent=cel, fontName=f["gras"]) if c.get("th") else cel
                    ligne.append(Paragraph(markup(c["runs"]), st))
                    span = c.get("colspan", 1)
                    if c.get("th"):
                        styles.append(("BACKGROUND", (col, r), (col + span - 1, r), colors.HexColor("#E4ECF5")))
                    if span > 1:
                        styles.append(("SPAN", (col, r), (col + span - 1, r)))
                        ligne.extend([""] * (span - 1))
                    col += span
                ligne.extend([""] * (ncol - len(ligne)))
                data.append(ligne[:ncol])
            rep = 1 if b["lignes"] and all(c.get("th") for c in b["lignes"][0]) else 0
            t = Table(data, colWidths=[largeur / ncol] * ncol, repeatRows=rep, splitByRow=1)
            t.setStyle(TableStyle(styles))
            histoire.append(t)
            histoire.append(Spacer(1, 6))
        else:
            histoire.append(Paragraph(markup(b["runs"]), base))
    if not histoire:
        histoire.append(Paragraph("(page vide)", base))

    def page(c, doc):
        c.saveState()
        c.setFont(f["normal"], 8)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawRightString(A4[0] - 1.7 * cm, 1.0 * cm, f"Page {doc.page}")
        if pied:
            c.drawString(1.7 * cm, 1.0 * cm, pied[:140])
        c.restoreState()

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=1.7 * cm, rightMargin=1.7 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title=titre or "Document")
    try:
        doc.build(histoire, onFirstPage=page, onLaterPages=page)
    except Exception:  # noqa: BLE001 — très gros tableau : on retombe sur du texte simple
        simple = [Paragraph(_x(titre or "Document"), tit[1])]
        for b in liste_blocs:
            if b["type"] == "table":
                for l in b["lignes"]:
                    simple.append(Paragraph(_x(" | ".join(texte_runs(c["runs"]) for c in l)), cel))
            else:
                simple.append(Paragraph(markup(b["runs"]), base))
        out = io.BytesIO()
        SimpleDocTemplate(out, pagesize=A4, title=titre or "Document").build(simple, onFirstPage=page, onLaterPages=page)
    return out.getvalue()


KIT_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
