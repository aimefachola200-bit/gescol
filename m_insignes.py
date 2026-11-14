# -*- coding: utf-8 -*-
"""v2.5.1 : insigne de l'application (pastille de couleur) dans l'en-tête et icônes propres à chaque édition."""
import insignes


def enregistrer(app, H):
    @app.context_processor
    def _insigne():
        cle = insignes.cle_courante()
        lettre, rvb, forme, lib = insignes.INSIGNES[cle]
        return {"INSIGNE": cle, "INSIGNE_LETTRE": lettre, "INSIGNE_LIB": lib, "INSIGNE_FORME": forme, "INSIGNE_COULEUR": "#%02x%02x%02x" % rvb}
