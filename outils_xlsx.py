# -*- coding: utf-8 -*-
"""Lecture et écriture de fichiers Excel (.xlsx) et CSV, communes à tous les modules.
openpyxl est importé à la demande : sans lui, GESCOL fonctionne mais l'import/export Excel affiche un message."""
import csv
import io
import re
import unicodedata

from flask import Response, send_file

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExcelIndisponible(RuntimeError):
    pass


def _openpyxl():
    try:
        import openpyxl
        return openpyxl
    except ImportError as e:  # pragma: no cover
        raise ExcelIndisponible("Le composant Excel (openpyxl) n'est pas installé : relancez GESCOL "
                                "avec Internet pour qu'il s'installe, ou utilisez un fichier CSV.") from e


def normaliser(texte):
    """« Prénom(s) de l'élève » -> « prenoms de l eleve » : pour reconnaître les colonnes quel que soit l'intitulé."""
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return t


def classeur(feuilles):
    """feuilles = [(titre, entetes, lignes, options)] -> bytes xlsx. options : {"titre_haut": [...lignes de titre]}"""
    openpyxl = _openpyxl()
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    fin = Side(style="thin", color="98A2B3")
    for titre, entetes, lignes, *opt in feuilles:
        opt = opt[0] if opt else {}
        ws = wb.create_sheet(re.sub(r"[\[\]:*?/\\]", "-", titre)[:31] or "Feuille")
        r0 = 1
        for t in opt.get("titre_haut", []):
            ws.cell(row=r0, column=1, value=t).font = Font(bold=True, size=12 if r0 == 1 else 10)
            r0 += 1
        if opt.get("titre_haut"):
            r0 += 1
        for j, h in enumerate(entetes, 1):
            c = ws.cell(row=r0, column=j, value=h)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E79")
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = Border(top=fin, bottom=fin, left=fin, right=fin)
        for i, ligne in enumerate(lignes, r0 + 1):
            for j, v in enumerate(ligne, 1):
                c = ws.cell(row=i, column=j, value=v)
                c.border = Border(top=fin, bottom=fin, left=fin, right=fin)
        for j, h in enumerate(entetes, 1):
            larg = max([len(str(h))] + [len(str(l[j - 1])) for l in lignes if j - 1 < len(l) and l[j - 1] is not None])
            ws.column_dimensions[get_column_letter(j)].width = min(max(8, larg + 2), 45)
        ws.freeze_panes = ws.cell(row=r0 + 1, column=1)
        ws.oddFooter.center.text = "Conception : Maître Aimé FACHE"
        ws.oddFooter.center.size = 8
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def reponse_xlsx(nom_fichier, entetes, lignes, titre="Liste", titre_haut=None):
    """Réponse Flask : un classeur d'une feuille. En l'absence d'openpyxl : CSV."""
    try:
        buf = classeur([(titre, entetes, lignes, {"titre_haut": titre_haut or []})])
    except ExcelIndisponible:
        return reponse_csv(nom_fichier.rsplit(".", 1)[0] + ".csv", entetes, lignes)
    return send_file(buf, mimetype=MIME_XLSX, as_attachment=True, download_name=nom_fichier)


def reponse_classeur(nom_fichier, feuilles):
    return send_file(classeur(feuilles), mimetype=MIME_XLSX, as_attachment=True, download_name=nom_fichier)


def reponse_csv(nom_fichier, entetes, lignes):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(entetes)
    w.writerows(lignes)
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={nom_fichier}"})


def lire_tableau(fichier, mots_entete=("nom",), max_lignes=5000):
    """Lit un fichier .xlsx / .xls(x) / .csv téléversé.
    Cherche automatiquement la ligne d'en-tête (première ligne contenant un des mots_entete).
    Retourne (entetes, lignes) où lignes = liste de listes (valeurs brutes)."""
    nom = (getattr(fichier, "filename", "") or "").lower()
    donnees = fichier.read()
    if nom.endswith(".csv") or nom.endswith(".txt"):
        texte = donnees.decode("utf-8-sig", errors="replace")
        sep = ";" if texte.count(";") >= texte.count(",") else ","
        brutes = list(csv.reader(io.StringIO(texte), delimiter=sep))
    else:
        openpyxl = _openpyxl()
        try:
            wb = openpyxl.load_workbook(io.BytesIO(donnees), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            raise ValueError("Fichier Excel illisible : enregistrez-le au format .xlsx (Excel 2007 ou plus récent).") from e
        brutes = []
        for ws in wb.worksheets:
            brutes = [list(r) for r in ws.iter_rows(values_only=True)]
            if any(any(v not in (None, "") for v in r) for r in brutes):
                break
    brutes = brutes[:max_lignes]
    mots = [normaliser(m) for m in mots_entete]
    idx = 0
    for i, r in enumerate(brutes[:40]):
        cellules = [normaliser(v) for v in r]
        if any(any(m and (c == m or c.startswith(m + " ") or (" " + m) in (" " + c)) for m in mots) for c in cellules if c):
            idx = i
            break
    entetes = [str(v).strip() if v is not None else "" for v in (brutes[idx] if brutes else [])]
    lignes = [r for r in brutes[idx + 1:] if any(v not in (None, "") for v in r)]
    return entetes, lignes


def colonne(entetes, *candidats):
    """Indice de la première colonne dont l'intitulé normalisé correspond à un des candidats (égal ou commence par)."""
    norm = [normaliser(h) for h in entetes]
    for cand in candidats:
        c = normaliser(cand)
        for i, h in enumerate(norm):
            if h == c:
                return i
    for cand in candidats:
        c = normaliser(cand)
        for i, h in enumerate(norm):
            if h.startswith(c) or c in h.split(" "):
                return i
    return None


def valeur(ligne, i):
    if i is None or i >= len(ligne) or ligne[i] is None:
        return ""
    v = ligne[i]
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v).strip()


def sexe(v):
    t = normaliser(v)
    if t in ("m", "g", "masculin", "garcon", "homme", "h", "1"):
        return "M"
    if t in ("f", "feminin", "fille", "femme", "2"):
        return "F"
    return ""


def date_iso(v):
    """Accepte 2014-05-03, 03/05/2014, 3-5-2014 ou une date Excel."""
    import datetime as _dt
    if not v:
        return ""
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return _dt.datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        n = float(s)
        if 1000 < n < 80000:
            return (_dt.date(1899, 12, 30) + _dt.timedelta(days=int(n))).strftime("%Y-%m-%d")
    except ValueError:
        pass
    return ""


def note(v):
    """Note sur 20 lue d'une cellule ; None si vide ; ValueError si invalide."""
    if v is None or str(v).strip() == "":
        return None
    x = float(str(v).replace(",", ".").strip())
    if not 0 <= x <= 20:
        raise ValueError(f"note hors limites : {v}")
    return round(x, 2)
