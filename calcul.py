# -*- coding: utf-8 -*-
"""
Moteur de calcul des notes – GESCOL / CPFA
Indépendant de la base de données et de Flask : testable seul.

PRIMAIRE
  * Moyenne = moyenne simple de toutes les matières notées (non dispensées).
  * Décision = règle des 2/3 : l'élève est ADMIS si le nombre de matières
    « standard » avec une note >= 10 atteint le seuil ceil(2/3 x nb standard).
  * Les matières en mode « exclu_2_3 » (Arts plastiques, Arts vivants, EPS)
    comptent dans la moyenne mais PAS dans la règle des 2/3.

SECONDAIRE
  * Moyenne pondérée Somme(note x coef) / Somme(coef).
  * Coefficients ignorés (tous à 1) en 6ème et 5ème.
  * Décision : ADMIS si moyenne >= 10. Pas de règle des 2/3.

Une matière sans note (None) et non dispensée est ignorée du calcul
et signalée comme « note manquante ».
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

NOTE_PASSAGE = 10.0
NOTE_MAX = 20.0

NIVEAUX_MATERNELLE = ["Maternelle 1", "Maternelle 2"]
NIVEAUX_PRIMAIRE = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]
NIVEAUX_SECONDAIRE = ["6ème", "5ème", "4ème", "3ème", "2nde", "1ère", "Tle"]
NIVEAUX_SANS_COEF = {"6ème", "5ème"}

MODES_CALCUL = {
    "standard": "Standard (compte dans la règle des 2/3)",
    "exclu_2_3": "Compte dans la moyenne, exclue de la règle des 2/3",
}


# Maternelle : pas de note chiffrée, une appréciation par domaine
APPRECIATIONS = {"A": "Acquis", "ECA": "En cours d'acquisition", "NA": "Non acquis"}


def cycle_du_niveau(niveau: str) -> str:
    if niveau in NIVEAUX_MATERNELLE:
        return "maternelle"
    if niveau in NIVEAUX_PRIMAIRE:
        return "primaire"
    if niveau in NIVEAUX_SECONDAIRE:
        return "secondaire"
    raise ValueError(f"Niveau inconnu : {niveau}")


def mention(moyenne: Optional[float]) -> str:
    if moyenne is None:
        return "—"
    if moyenne >= 18: return "Excellent"
    if moyenne >= 16: return "Très bien"
    if moyenne >= 14: return "Bien"
    if moyenne >= 12: return "Assez bien"
    if moyenne >= 10: return "Passable"
    if moyenne >= 8:  return "Insuffisant"
    return "Très insuffisant"


def appreciation_note(note: Optional[float]) -> str:
    if note is None:
        return ""
    if note >= 16: return "Très bien"
    if note >= 14: return "Bien"
    if note >= 12: return "Assez bien"
    if note >= 10: return "Passable"
    if note >= 8:  return "Insuffisant"
    return "Faible"


def seuil_deux_tiers(n: int) -> int:
    """Plafond entier de 2n/3, calculé en entiers (pas d'erreur d'arrondi flottant)."""
    return (2 * n + 2) // 3


@dataclass
class LigneNote:
    code: str
    nom: str
    coefficient: float
    mode: str               # standard | exclu_2_3
    valeur: Optional[float] # None = pas encore noté
    dispense: bool = False
    appreciation: Optional[str] = None  # maternelle : A / ECA / NA


@dataclass
class LigneResultat:
    code: str
    nom: str
    coefficient: float      # coefficient réellement appliqué
    note: Optional[float]
    points: Optional[float] # note x coefficient
    statut: str             # "noté" | "dispensé" | "manquant"
    exclue_2_3: bool
    appreciation: str
    code_appreciation: Optional[str] = None


@dataclass
class Resultat:
    cycle: str
    niveau: str
    lignes: List[LigneResultat] = field(default_factory=list)
    moyenne: Optional[float] = None
    decision: str = "NON DÉTERMINÉ"
    mention: str = "—"
    details: Dict = field(default_factory=dict)
    rang: Optional[int] = None
    ex_aequo: bool = False
    effectif: int = 0

    @property
    def admis(self) -> bool:
        return self.decision in ("ADMIS", "MAÎTRISE", "Progrès très satisfaisants", "Progrès satisfaisants")

    @property
    def rang_texte(self) -> str:
        if self.rang is None:
            return "—"
        suffixe = "er" if self.rang == 1 else "e"
        txt = f"{self.rang}{suffixe}"
        if self.ex_aequo:
            txt += " ex æquo"
        return f"{txt} / {self.effectif}"


def _verifier(valeur: Optional[float]):
    if valeur is not None and not (0 <= valeur <= NOTE_MAX):
        raise ValueError(f"Note hors limites : {valeur}")


def calculer_maternelle(niveau: str, lignes: List[LigneNote]) -> Resultat:
    """Maternelle : bilan qualitatif (pas de moyenne ni de rang)."""
    res = Resultat(cycle="maternelle", niveau=niveau)
    for l in lignes:
        code = l.appreciation if l.appreciation in APPRECIATIONS else None
        statut = "dispensé" if l.dispense else ("noté" if code else "manquant")
        res.lignes.append(LigneResultat(
            code=l.code, nom=l.nom, coefficient=1, note=None, points=None, statut=statut, exclue_2_3=False,
            appreciation=APPRECIATIONS.get(code, "Dispensé(e)" if l.dispense else ""), code_appreciation=code))
    ev = [r for r in res.lignes if r.statut == "noté"]
    comptes = {k: sum(1 for r in ev if r.code_appreciation == k) for k in APPRECIATIONS}
    res.details = {"notes_manquantes": [r.nom for r in res.lignes if r.statut == "manquant"],
                   "dispenses": [r.nom for r in res.lignes if r.statut == "dispensé"],
                   "comptes": comptes, "evalues": len(ev)}
    if not ev:
        res.details["explication"] = "Aucun domaine évalué."
        return res
    score = (2 * comptes["A"] + comptes["ECA"]) / (2 * len(ev))
    res.details["score"] = round(score, 3)
    if score >= 0.75:
        res.decision = res.mention = "Progrès très satisfaisants"
    elif score >= 0.5:
        res.decision = res.mention = "Progrès satisfaisants"
    else:
        res.decision = res.mention = "Progrès à renforcer"
    res.details["explication"] = (f"{comptes['A']} acquis, {comptes['ECA']} en cours, {comptes['NA']} non acquis "
                                  f"sur {len(ev)} domaine(s) évalué(s).")
    return res


def calculer(niveau: str, lignes: List[LigneNote], seuil_impose: Optional[int] = None) -> Resultat:
    """seuil_impose (primaire) : nombre de matières à 10/20 exigé, fixé par l'évaluation ; sinon 2/3 automatique."""
    cycle = cycle_du_niveau(niveau)
    if cycle == "maternelle":
        return calculer_maternelle(niveau, lignes)
    res = Resultat(cycle=cycle, niveau=niveau)
    coef_actifs = cycle == "secondaire" and niveau not in NIVEAUX_SANS_COEF
    manquantes = []

    for l in lignes:
        _verifier(l.valeur)
        coef = l.coefficient if coef_actifs else 1.0
        if l.dispense:
            statut, note, pts = "dispensé", None, None
        elif l.valeur is None:
            statut, note, pts = "manquant", None, None
            manquantes.append(l.nom)
        else:
            statut, note, pts = "noté", float(l.valeur), round(float(l.valeur) * coef, 2)
        res.lignes.append(LigneResultat(
            code=l.code, nom=l.nom, coefficient=coef, note=note, points=pts,
            statut=statut,
            exclue_2_3=(cycle == "primaire" and l.mode == "exclu_2_3"),
            appreciation=appreciation_note(note),
        ))

    notees = [r for r in res.lignes if r.statut == "noté"]
    res.details["notes_manquantes"] = manquantes
    res.details["dispenses"] = [r.nom for r in res.lignes if r.statut == "dispensé"]
    if not notees:
        res.details["explication"] = "Aucune note saisie."
        return res

    if cycle == "primaire":
        res.moyenne = round(sum(r.note for r in notees) / len(notees), 2)
        standard = [r for r in notees if not r.exclue_2_3]
        n_std = len(standard)
        seuil = min(seuil_impose, n_std) if seuil_impose else seuil_deux_tiers(n_std)
        reussies = sum(1 for r in standard if r.note >= NOTE_PASSAGE)
        if n_std == 0:
            res.decision = "NON DÉTERMINÉ"
        else:
            # Primaire : la MAÎTRISE (2/3 des matières à 10/20 au moins) est la seule condition de réussite ;
            # la moyenne ne sert qu'au classement.
            res.decision = "MAÎTRISE" if reussies >= seuil else "NON MAÎTRISE"
        res.details.update({
            "regle": "2/3",
            "matieres_notees": len(notees),
            "matieres_standard": n_std,
            "seuil_2_3": seuil,
            "standard_reussies": reussies,
            "exclues_2_3": [r.nom for r in notees if r.exclue_2_3],
            "explication": (f"{reussies} matière(s) sur {n_std} ont au moins 10/20 "
                            f"(seuil de maîtrise : {seuil}). La moyenne ({res.moyenne}) sert uniquement au rang."),
        })
    else:
        somme_pts = sum(r.points for r in notees)
        somme_coef = sum(r.coefficient for r in notees)
        res.moyenne = round(somme_pts / somme_coef, 2)
        res.decision = "ADMIS" if res.moyenne >= NOTE_PASSAGE else "NON ADMIS"
        res.details.update({
            "regle": "moyenne_ponderee",
            "coefficients_actifs": coef_actifs,
            "somme_points": round(somme_pts, 2),
            "somme_coefficients": somme_coef,
            "explication": (f"Somme(note x coef) / Somme(coef) = {round(somme_pts, 2)} / "
                            f"{somme_coef:g} = {res.moyenne}"
                            + ("" if coef_actifs else " (coefficients non appliqués en 6ème/5ème)")),
        })

    res.mention = mention(res.moyenne)
    return res


def classer(moyennes: Dict[int, Optional[float]]) -> Dict[int, Tuple[Optional[int], bool]]:
    """Rang « olympique » : deux élèves à égalité ont le même rang, le suivant saute.
    Retourne {id: (rang, ex_aequo)} ; rang None si pas de moyenne."""
    classes = sorted(((i, m) for i, m in moyennes.items() if m is not None),
                     key=lambda x: x[1], reverse=True)
    compte = {}
    for _, m in classes:
        compte[m] = compte.get(m, 0) + 1
    out, rang_prec, moy_prec = {}, 0, None
    for pos, (i, m) in enumerate(classes, start=1):
        rang = rang_prec if m == moy_prec else pos
        out[i] = (rang, compte[m] > 1)
        rang_prec, moy_prec = rang, m
    for i, m in moyennes.items():
        if m is None:
            out[i] = (None, False)
    return out


def statistiques(resultats: List[Resultat]) -> Dict:
    moys = [r.moyenne for r in resultats if r.moyenne is not None]
    admis = sum(1 for r in resultats if r.admis)
    return {
        "effectif": len(resultats),
        "classes": len(moys),
        "moyenne_classe": round(sum(moys) / len(moys), 2) if moys else None,
        "plus_forte": max(moys) if moys else None,
        "plus_faible": min(moys) if moys else None,
        "admis": admis,
        "taux_reussite": round(100 * admis / len(moys), 1) if moys else None,
    }
