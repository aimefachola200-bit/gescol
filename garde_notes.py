# -*- coding: utf-8 -*-
"""v1.9 — Garde-fou de la saisie des notes : note principale + note de performance.

Chaque note chiffrée se saisit en deux cases : la note principale et la note de performance (sur 2).
* la note principale doit rester STRICTEMENT inférieure à 20 : 20/20 n'est possible qu'avec la note de performance ;
* la note de performance va de 0 à 2, et seulement à partir de 10 de note principale : en dessous de la moyenne,
  pas de perfectionnement (performance 0 ou vide) ;
* la note retenue (principale + performance) ne dépasse jamais 20 : 19 → performance 1 au plus, 18 → 2 au plus.
Une case hors de ces règles est affichée en rouge à la saisie et refusée à l'enregistrement.
La note retenue est rangée dans notes.valeur (moyennes, rangs, bulletins inchangés) et la note de performance
dans notes.performance.
"""

PERF_MAX = 2.0
NOTE_MAX = 20.0
DISPENSE = ("D", "DISP", "DISPENSE", "DISPENSÉ")


class NoteRefusee(ValueError):
    """Valeur refusée ; le message dit pourquoi."""


def _nombre(s):
    s = ("" if s is None else str(s)).strip().replace(",", ".").replace(" ", "")
    if isinstance(s, float):
        return s
    return float(s)


def lire(brut_note, brut_perf=None):
    """(note principale, note de performance) saisies -> (valeur retenue | None, dispense, performance | None).
    Lève NoteRefusee(message) si une règle n'est pas respectée."""
    if isinstance(brut_note, float) and brut_note.is_integer():
        brut_note = str(int(brut_note))
    s = ("" if brut_note is None else str(brut_note)).strip()
    p = ("" if brut_perf is None else str(brut_perf)).strip()
    if s.upper() in DISPENSE:
        return None, True, None
    if s == "":
        if p:
            raise NoteRefusee("note de performance sans note principale")
        return None, False, None
    try:
        v = _nombre(s)
    except ValueError:
        raise NoteRefusee(f"« {s} » n'est pas une note") from None
    if v < 0:
        raise NoteRefusee("note négative")
    if v >= NOTE_MAX:
        raise NoteRefusee(f"note principale {s} : elle doit rester inférieure à 20 (20/20 n'est possible qu'avec la note de performance)")
    perf = None
    if p:
        try:
            perf = _nombre(p)
        except ValueError:
            raise NoteRefusee(f"« {p} » n'est pas une note de performance") from None
        if not 0 <= perf <= PERF_MAX:
            raise NoteRefusee(f"note de performance {p} : elle va de 0 à 2")
        if v < 10 and perf > 0:
            raise NoteRefusee(f"note principale {s} inférieure à 10 : pas de note de performance (0 ou vide)")
        if v + perf > NOTE_MAX:
            raise NoteRefusee(f"note principale {s} : la note de performance ne peut pas dépasser {max(0, NOTE_MAX - v):g} (somme limitée à 20)")
    total = round(v + (perf or 0), 2)
    return total, False, (round(perf, 2) if perf is not None else None)


def separer(saisie):
    """« 12|1,5 » (forme envoyée par la grille) -> ("12", "1,5") ; « 12 » -> ("12", "")."""
    s = "" if saisie is None else str(saisie)
    if "|" in s:
        a, b = s.split("|", 1)
        return a, b
    return s, ""


def afficher(valeur, performance):
    """Valeurs à réafficher dans les deux cases : (principale, performance) en texte."""
    def f(x):
        return "" if x is None else (f"{x:.2f}".rstrip("0").rstrip("."))
    if valeur is None:
        return "", ""
    if performance is None:
        return f(valeur), ""
    return f(round(valeur - performance, 2)), f(performance)


# Script commun aux grilles : règles identiques côté navigateur (cases en rouge pendant la saisie)
JS = r"""
window.GardeNotes = (function(){
  function nb(s){ s = String(s || '').trim().replace(',', '.'); return /^\d{1,2}(\.\d{1,2})?$/.test(s) ? parseFloat(s) : NaN; }
  /* principale, performance (textes) -> {vide|disp|note, perf, errN, errP, msg} */
  function lire(a, b){
    a = String(a || '').trim(); b = String(b || '').trim();
    if (a.toUpperCase() === 'D') return {disp: true};
    if (a === '' && b === '') return {vide: true};
    var r = {}, v = nb(a), p = b === '' ? 0 : nb(b);
    if (a === '') { r.errP = true; r.msg = 'note de performance sans note principale'; return r; }
    if (isNaN(v) || v < 0) { r.errN = true; r.msg = 'note invalide'; }
    else if (v >= 20) { r.errN = true; r.msg = 'la note principale doit rester inférieure à 20 (20/20 seulement avec la performance)'; }
    if (b !== '' && (isNaN(p) || p < 0 || p > 2)) { r.errP = true; r.msg = 'la note de performance va de 0 à 2'; }
    else if (!r.errN && v < 10 && p > 0) { r.errP = true; r.msg = 'note inférieure à 10 : pas de note de performance (0 ou vide)'; }
    else if (!r.errN && v + p > 20) { r.errP = true; r.msg = 'performance limitée à ' + (Math.round((20 - v) * 100) / 100) + ' pour une note principale de ' + a; }
    if (!r.errN && !r.errP) r.note = Math.round((v + p) * 100) / 100;
    return r;
  }
  return {lire: lire};
})();
"""
