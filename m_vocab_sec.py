# -*- coding: utf-8 -*-
"""v2.5.5 : vocabulaire du secondaire. Dans les éditions secondaires, les termes propres au primaire affichés dans les pages
(CEP, maître de semaine, ...) sont remplacés à l'affichage par ceux du collège (BEPC, professeur ou délégué de semaine).
Seul le texte visible est modifié : balises, attributs, scripts et styles ne sont jamais touchés."""
import re

from flask import request

import config

_REMPL = [
    (re.compile(r"Certificat d['’]Études Primaires"), "Brevet d'Études du Premier Cycle"),
    (re.compile(r"Certificat d['’]Etudes Primaires"), "Brevet d'Études du Premier Cycle"),
    (re.compile(r"(?<![A-Za-zÀ-ÿ])CEP(?![A-Za-zÀ-ÿ])"), "BEPC"),
    (re.compile(r"MAÎTRES DE SEMAINE"), "PROFESSEURS OU DÉLÉGUÉS DE SEMAINE"),
    (re.compile(r"MAÎTRE DE SEMAINE"), "PROFESSEUR OU DÉLÉGUÉ DE SEMAINE"),
    (re.compile(r"Maîtres de semaine"), "Professeurs ou délégués de semaine"),
    (re.compile(r"Maître de semaine"), "Professeur ou délégué de semaine"),
    (re.compile(r"maîtres de semaine"), "professeurs ou délégués de semaine"),
    (re.compile(r"maître de semaine"), "professeur ou délégué de semaine"),
    (re.compile(r"Maître-de-semaine"), "Professeur ou délégué de semaine"),
]
_BLOC_SANS_TEXTE = re.compile(r"(<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->)", re.S | re.I)
_TEXTE = re.compile(r">([^<>]+)<")


def adapter_texte(t):
    for rx, r in _REMPL:
        t = rx.sub(r, t)
    return t


def adapter_html(html):
    parts = _BLOC_SANS_TEXTE.split(html)
    for i in range(0, len(parts), 2):          # les indices pairs sont hors script / style / commentaire
        parts[i] = _TEXTE.sub(lambda m: ">" + adapter_texte(m.group(1)) + "<", parts[i])
    return "".join(parts)


def _brancher_pdf():
    """Mêmes remplacements dans les PDF produits directement par reportlab (textes dessinés et paragraphes)."""
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import Paragraph
    if getattr(Canvas, "_vocab_sec", False):
        return

    def _a(t):
        return adapter_texte(t) if isinstance(t, str) and ("CEP" in t or "ertificat" in t or "semaine" in t.lower()) else t
    for nom in ("drawString", "drawCentredString", "drawRightString"):
        orig = getattr(Canvas, nom)

        def f(self, x, y, text, *a, _o=orig, **k):
            return _o(self, x, y, _a(text), *a, **k)
        setattr(Canvas, nom, f)
    init = Paragraph.__init__

    def pinit(self, text, *a, **k):
        return init(self, _a(text), *a, **k)
    Paragraph.__init__ = pinit
    Canvas._vocab_sec = True


def enregistrer(app, H):
    if config.secondaire():
        try:
            _brancher_pdf()
        except Exception:  # noqa: BLE001
            pass
    @app.after_request
    def _vocabulaire_secondaire(r):
        try:
            if (config.secondaire() and r.status_code == 200 and not request.path.startswith('/textes-officiels') and not r.direct_passthrough
                    and (r.mimetype or "") == "text/html"):
                r.set_data(adapter_html(r.get_data(as_text=True)))
        except Exception:  # noqa: BLE001
            pass
        return r
