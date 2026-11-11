# -*- coding: utf-8 -*-
"""v1.33 — Performances.

* Réponses compressées (gzip) : pages HTML, JSON, CSS, JavaScript et SVG de plus de 1 Ko, quand le navigateur l'accepte
  (Wi-Fi de l'école, téléphones, connexion mobile : 5 à 10 fois moins de données) ;
* index de la base sur les recherches les plus fréquentes (élèves d'une classe, notes d'une période, absences,
  paiements, journal) : les grosses écoles (1 000 élèves et plus) restent rapides ;
* QR codes des documents tracés directement (pdfs.dessiner_qr) : bulletins d'une classe entière deux fois plus vite ;
* corpus pédagogique préchargé en arrière-plan au démarrage (m_preparation).
"""
import gzip
import io

from flask import request

TYPES = ("text/html", "application/json", "text/css", "application/javascript", "text/javascript", "image/svg+xml", "text/plain",
         "text/csv")
MIN_OCTETS = 1024

INDEX = """
CREATE INDEX IF NOT EXISTS ix_eleves_classe ON eleves(classe_id, statut);
CREATE INDEX IF NOT EXISTS ix_eleves_annee ON eleves(annee, statut);
CREATE INDEX IF NOT EXISTS ix_notes_periode ON notes(annee, periode, matiere_id);
CREATE INDEX IF NOT EXISTS ix_presences_eleve ON presences(eleve_id, date);
CREATE INDEX IF NOT EXISTS ix_presences_date ON presences(date);
CREATE INDEX IF NOT EXISTS ix_paiements_eleve ON paiements(eleve_id, annee);
CREATE INDEX IF NOT EXISTS ix_journal_date ON journal(cree_le);
CREATE INDEX IF NOT EXISTS ix_classes_ecole ON classes(ecole_id, niveau);
CREATE INDEX IF NOT EXISTS ix_affectations_user ON affectations(user_id, classe_id);
"""


def compresser(r):
    """Compresse la réponse (gzip) si c'est utile et possible."""
    if (r.direct_passthrough or r.status_code < 200 or r.status_code >= 300 or r.status_code == 204
            or "Content-Encoding" in r.headers or "gzip" not in (request.headers.get("Accept-Encoding") or "").lower()):
        return r
    if (r.mimetype or "") not in TYPES:
        return r
    donnees = r.get_data()
    if len(donnees) < MIN_OCTETS:
        return r
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6, mtime=0) as z:
        z.write(donnees)
    r.set_data(buf.getvalue())
    r.headers["Content-Encoding"] = "gzip"
    r.headers["Content-Length"] = str(len(r.get_data()))
    vary = r.headers.get("Vary")
    r.headers["Vary"] = (vary + ", Accept-Encoding") if vary and "accept-encoding" not in vary.lower() else (vary or "Accept-Encoding")
    return r


def enregistrer(app, H):
    try:
        H.schema(INDEX)
    except Exception:  # noqa: BLE001 — une table absente dans une installation ancienne : on continue
        app.logger.exception("Index de la base")

    @app.after_request
    def _gzip(r):
        if app.config.get("TESTING") and not app.config.get("GZIP_TEST"):
            return r                      # les tests lisent les pages en clair
        try:
            return compresser(r)
        except Exception:  # noqa: BLE001
            app.logger.exception("Compression gzip")
            return r
