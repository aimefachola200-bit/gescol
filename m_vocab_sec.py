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
    # ---- v2.5.2 : le reste du vocabulaire du primaire, remplacé à l'affichage dans les éditions du secondaire
    (re.compile(r"Calendrier scolaire officiel \(MEMP\)"), "Calendrier scolaire officiel (MESTFP)"),
    (re.compile(r"Synthèse École / UP / (?:Inspection|CS)"), "Synthèse Établissement / Inspection"),
    (re.compile(r"EducMaster \(maternelle, primaire, secondaire\)"), "EducMaster (secondaire)"),
    (re.compile(r"\(CM2 … Maternelle 1\)"), "(Tle … 6e)"),
    (re.compile(r"Nom de votre école primaire"), "Nom de votre établissement"),
    (re.compile(r"Union des associations scolaires et culturelles des écoles primaires"), "Union des associations scolaires et culturelles du secondaire"),
    (re.compile(r"par école, unité pédagogique, zone pédagogique, inspection"), "par établissement, inspection"),
    (re.compile(r"[ée]coles? maternelles? et primaires?|Écoles maternelles et primaires", re.I), "établissements secondaires"),
    (re.compile(r"Maternelle et primaire"), "Collège et lycée"),
    (re.compile(r"Établissement primaire / maternelle \(mention à barrer\)"), "Établissement secondaire"),
    (re.compile(r"Établissement primaire \(barrer « maternelle »\)"), "Établissement secondaire"),
    (re.compile(r"Établissement \(barrer « primaire »\)"), "Établissement secondaire"),
    (re.compile(r"Elève-instituteur \(trice\)"), "Élève-professeur (e)"),
    (re.compile(r"Instituteur \(trice\) adjoint\(e\)"), "Professeur adjoint (e)"),
    (re.compile(r"Instituteur \(trice\)"), "Professeur (e)"),
    (re.compile(r"Téléphone du CP"), "Téléphone de l'inspecteur pédagogique"),
    (re.compile(r"Zones, UP et établissements"), "Zones pédagogiques et établissements"),
    (re.compile(r"Unités pédagogiques \(UP\) : responsables, activités, taux d'exécution"), "Animation pédagogique : responsables, activités, taux d'exécution"),
    (re.compile(r", simples / jumelées / multigrades"), ""),
    (re.compile(r"\(établissement primaire\)"), "(établissement secondaire)"),
    (re.compile(r"CP Zone pédagogique"), "Inspecteur Zone pédagogique"),
    (re.compile(r"Séance d'unité pédagogique \(UP\)"), "Séance d'animation pédagogique"),
    (re.compile(r"visas CP / directeur / AP[E]?"), "visas inspecteur / chef d'établissement"),
    (re.compile(r"Fiche de recensement – (?:primaire|maternelle)"), "Fiche de recensement – établissement"),
    (re.compile(r"^(\s*)CP ([A-Z])(\s*)$"), r"\1Inspecteur \2\3"),
    (re.compile(r"^(\s*)UP (\d+)(\s*)$"), r"\1Zone \2\3"),
    (re.compile(r"\(chef d'inspection, CP, chef de division"), "(chef d'inspection, inspecteur pédagogique, chef de division"),
    (re.compile(r"Traitement et salaire des gardiens"), "Traitement et salaire des gardiens et du personnel d'appui"),
    (re.compile(r"Soins médicaux \(soins d'urgence à l'école\)"), "Soins médicaux (soins d'urgence à l'établissement)"),
    (re.compile(r"Petits outillages \(houe, balai, râteau, seau d'eau…\)"), "Petits outillages et produits d'entretien"),
    (re.compile(r"Déplacement du directeur et des autres acteurs de l'école"), "Déplacement du chef d'établissement et des autres acteurs"),
    (re.compile(r"Frais d'entretien du directeur et des autres acteurs de l'école"), "Frais d'entretien du chef d'établissement et des autres acteurs"),
    (re.compile(r"Fête de la journée mondiale des enseignants"), "Fête de la journée mondiale des enseignants"),
    (re.compile(r"cahiers d'activités, extraits des guides, examen blanc, renforcement CEP…"), "examens blancs, renforcement BEPC et baccalauréat…"),
    (re.compile(r"^(\s*)UASCEP(\s*)$"), r"\1UASCES\2"),
    (re.compile(r"^(\s*)APE(\s*)$"), r"\1APE / COGES\2"),
    (re.compile(r"\(CP, chef d'inspection, DDESTFP\)"), "(inspecteurs pédagogiques, chef d'inspection, DDESTFP)"),
    (re.compile(r"Participation à l'UP \(%\)"), "Participation aux animations pédagogiques (%)"),
    (re.compile(r"Visites de classe reçues : CP"), "Visites de classe reçues : inspecteur pédagogique"),
    (re.compile(r"Visites du CP"), "Visites de l'inspecteur pédagogique"),
    (re.compile(r"Visites de classe \(CP / chef d'inspection\)"), "Visites de classe (inspecteur pédagogique / chef d'inspection)"),
    (re.compile(r"Fonction / poste \(chef d'inspection, CP, chef de division"), "Fonction / poste (chef d'inspection, inspecteur pédagogique, chef de division"),
    (re.compile(r"^(\s*)Établissement primaire(\s*)$"), r"\1Établissement secondaire\2"),
    (re.compile(r"^(\s*)Instituteur(\s*)$"), r"\1Professeur\2"),
    (re.compile(r"Participation à l’UP"), "Participation aux animations"),
    (re.compile(r"Techniques d'animation de la maternelle"), "Techniques d'animation pédagogique"),
    (re.compile(r"^(\s*)UP(\s*)$"), r"\1Zone\2"),
    (re.compile(r"^(\s*)CP(\s*)$"), r"\1Inspecteur pédagogique\2"),
    (re.compile(r"Les classes « Maternelle 1 » et « Maternelle 2 » voient les activités de la semaine"), "Les classes voient les activités de la semaine"),
    (re.compile(r"[^.<]*(?:simples \+ jumelées \+ multigrades|multigrade \(ex\. CI-CE2-CM1\))[^.<]*\.\s*"), ""),
    (re.compile(r"Classes à effectif partagé et multigrades"), "Classes et groupes pédagogiques"),
    (re.compile(r"[^.<]*Grilles d'observation[^.<]*(?:acquis, en cours d'acquisition, non acquis)[^.<]*\.\s*"), ""),
    (re.compile(r"niveau \(école, UP, zone, Inspection, DDESTFP\)"), "niveau (établissement, zone, Inspection, DDESTFP)"),
    (re.compile(r"choisissez le niveau \(école, UP, zone, Inspection, DDESTFP\)"), "choisissez le niveau (établissement, zone, Inspection, DDESTFP)"),
    (re.compile(r"Niveau : École, Unité pédagogique, Zone pédagogique, Inspection secondaire ou DDESTFP ; Entité : nom de l'école, de l'UP…"), "Niveau : Établissement, Zone pédagogique, Inspection secondaire ou DDESTFP ; Entité : nom de l'établissement…"),
    (re.compile(r"visites des CP et du chef d'inspection"), "visites des inspecteurs pédagogiques et du chef d'inspection"),
    (re.compile(r"Français \(CE2 à la 3e\)"), "Français (6e à la terminale)"),
    (re.compile(r"Apprendre à lire au CP"), "Apprendre à lire et à comprendre"),
    (re.compile(r"le maître observe et guide"), "le professeur observe et guide"),
    (re.compile(r"relation maître-élève"), "relation professeur-élève"),
    (re.compile(r"\bBureaux UASCES\b"), "Bureaux UASCES"),
    (re.compile(r"\(école, UP, zone, Inspection, DDESTFP\)"), "(établissement, zone, Inspection, DDESTFP)"),
    (re.compile(r"Niveau : École, Unité pédagogique, Zone pédagogique, Inspection secondaire ou DDESTFP ; Entité : nom de l'école, de l'UP…"), "Niveau : Établissement, Zone pédagogique, Inspection secondaire ou DDESTFP ; Entité : nom de l'établissement…"),
    (re.compile(r"Colonnes : Niveau, Entité, N° d'ordre, Nom, Prénoms, Sexe, École, UP, Zone"), "Colonnes : Niveau, Entité, N° d'ordre, Nom, Prénoms, Sexe, Établissement, Zone"),
    (re.compile(r"\bUnité pédagogique \(UP\)"), "Zone pédagogique"),
    (re.compile(r"ses zones et UP, ses services"), "ses zones, ses services"),
    (re.compile(r"Écoles Primaires"), "Établissements Secondaires"),
    (re.compile(r"\(CP / RUP\)"), ""),
    (re.compile(r"le inspecteur pédagogique"), "l'inspecteur pédagogique"),
    (re.compile(r"par le inspecteur pédagogique"), "par l'inspecteur pédagogique"),
    (re.compile(r"Le directeur ou le CP peut"), "Le directeur ou l'inspecteur pédagogique peut"),
    (re.compile(r"Les fiches de la maternelle sont des fiches conçues"), "Les fiches sont des fiches conçues"),
    (re.compile(r"visites des CP et du chef d'inspection"), "visites des inspecteurs pédagogiques et du chef d'inspection"),
    (re.compile(r"Classes jumelées et multigrades"), "Classes et groupes pédagogiques"),
    (re.compile(r"Classes jumelées"), "Classes à effectif partagé"),
    (re.compile(r"Classes multigrades"), "Classes à groupes multiples"),
    (re.compile(r"Nouvelles inscrites au CI"), "Nouvelles inscrites en 6ème"),
    (re.compile(r"Filles au CM2"), "Filles en 3ème"),
    (re.compile(r"Enseignants du CI / CP"), "Professeurs de 6ème / 5ème"),
    (re.compile(r"Éducatrices / éducateurs \(maternelle\)"), "Professeurs principaux"),
    (re.compile(r"\bmaternelle \(A / ECA / NA\)"), "secondaire (A / ECA / NA)"),
    (re.compile(r"\s*\(CCS\)"), ""),
    (re.compile(r"\s*\(CP\)"), ""),
    (re.compile(r"\bCP et CCS\b"), "Inspecteurs pédagogiques et chef d'inspection"),
    (re.compile(r"\bPar un CP\b"), "Par un inspecteur pédagogique"),
    (re.compile(r"\bPar le CCS\b"), "Par le chef d'inspection"),
    (re.compile(r"\b0 CP · 0 CCS"), "0 inspecteur(s) pédagogique(s) · 0 chef(s) d'inspection"),
    (re.compile(r"\bdélivré(e)? par le CCS"), lambda m: "délivré" + (m.group(1) or "") + " par le chef d'inspection"),
    (re.compile(r"\bDélivrée par le CCS au directeur / à la directrice d['’]école"), "Délivrée par le chef d'inspection au chef d'établissement"),
    (re.compile(r"\bLe CCS\b"), "Le chef d'inspection"),
    (re.compile(r"\bLa CCS\b"), "Le chef d'inspection"),
    (re.compile(r"\bCCS\b"), "chef d'inspection"),
    (re.compile(r"modèle MEMP / DAF"), "modèle MESTFP"),
    (re.compile(r"calendrier publié par le MEMP"), "calendrier publié par le MESTFP"),
    (re.compile(r"EPP Akpakpa Centre / Groupe A"), "CEG Akpakpa Centre"),
    (re.compile(r"EPP AKPAKPA CENTRE"), "CEG AKPAKPA CENTRE"),
    (re.compile(r"Instituteur, Inspecteur pédagogique…"), "Professeur certifié, Inspecteur pédagogique…"),
    (re.compile(r"\bLe maître\b"), "Le professeur principal"),
    (re.compile(r"\bLa maîtresse\b"), "La professeure principale"),
    (re.compile(r"(Mobilier|Bureau|Guide) du maître"), lambda m: m.group(1) + " du professeur"),
    (re.compile(r"Guide du maître"), "Guide du professeur"),
    (re.compile(r"Enseignants \(maîtres\)"), "Enseignants"),
    (re.compile(r"Manuel de français CE1"), "Manuel de français 6e"),
    (re.compile(r"Circonscription scolaire de Cotonou"), "Inspection secondaire de Cotonou"),
    (re.compile(r"ex\. Circonscription scolaire"), "ex. Inspection secondaire"),
    (re.compile(r"Complexe \(primaire \+ secondaire\)"), "Complexe (collège + lycée)"),
    (re.compile(r"École maternelle"), "Établissement"),
    (re.compile(r"Rapport de rentrée – écoles maternelles"), "Rapport de rentrée – établissements"),
    (re.compile(r"Fiche de fin d['’]année – écoles maternelles"), "Fiche de fin d'année – établissements"),
    (re.compile(r"MEMP \(maternel et primaire\)"), "MESTFP (secondaire)"),
    (re.compile(r"Arrêtés du MEMP et du MESTFP"), "Arrêtés du MESTFP"),
    (re.compile(r"Maternel et primaire"), "Secondaire"),
    (re.compile(r"Examen blanc du CEP"), "Examen blanc du BEPC"),
    (re.compile(r"Reprendre les élèves de CM2"), "Reprendre les élèves de 3ème"),
    (re.compile(r"Animation pédagogique d[’']UP"), "Animation pédagogique d'établissement"),
    (re.compile(r"Convocation \(réunion, UP, formation\)"), "Convocation (réunion, formation)"),
    (re.compile(r"Créez les classes \(niveau CI à CM2, titulaire\)"), "Créez les classes (niveau 6ème à Tle, titulaire)"),
    (re.compile(r"« Révisions d['’]éveil » \(CM1, CM2\)"), "« Révisions d'éveil » (6ème à 3ème)"),
    (re.compile(r"Classes jumelées et multigrades"), "Classes et groupes pédagogiques"),
    (re.compile(r"[^.<]*classe jumelée[^.<]*\.\s*"), ""),
    (re.compile(r"Ajoutez le directeur, les enseignants, le CP…"), "Ajoutez le directeur, les professeurs…"),
    (re.compile(r"écoles primaires"), "établissements secondaires"),
    (re.compile(r"fiches officielles EP \(primaire\) et EM \(maternelle\)"), "fiches officielles du secondaire"),
    (re.compile(r"· Primaire et secondaire"), "· Secondaire"),
    (re.compile(r"l['’]art d['’]enseigner et la lecture au CP"), "l'art d'enseigner et la lecture"),
    (re.compile(r"Guides du maître"), "Guides du professeur"),
    (re.compile(r"[Cc]onseil des maîtres"), lambda m: ("Conseil" if m.group(0)[0] == "C" else "conseil") + " des professeurs"),
    (re.compile(r"ton maître / professeur principal"), "ton professeur principal"),
    (re.compile(r"Ajoutez le directeur, les enseignants, le CP…"), "Ajoutez le directeur, les professeurs, l'inspecteur pédagogique…"),
    (re.compile(r"conseillers pédagogiques \(CP\) et du chef d['’]inspection secondaire \(CCS\)"), "inspecteurs pédagogiques et du chef d'inspection secondaire"),
    (re.compile(r"Conseiller pédagogique / inspecteur"), "Inspecteur pédagogique"),
    (re.compile(r"Conseillers pédagogiques"), "Inspecteurs pédagogiques"),
    (re.compile(r"conseillers pédagogiques"), "inspecteurs pédagogiques"),
    (re.compile(r"Conseiller pédagogique"), "Inspecteur pédagogique"),
    (re.compile(r"conseiller pédagogique"), "inspecteur pédagogique"),
    (re.compile(r"ratios élèves / maître"), "ratios élèves / professeur"),
    (re.compile(r"\bUP\b(?= maternelle| primaire)"), "UP"),
    (re.compile(r"Le niveau détermine le mode de calcul : appréciations \(acquis / en cours / non acquis\) en maternelle, règle des 2/3 au primaire, moyenne pondérée au secondaire \(sans coefficients en 6ème et 5ème\)\."),
     "Le niveau détermine le mode de calcul : moyenne pondérée (sans coefficient en 6ème et 5ème)."),
    (re.compile(r"Au primaire le coefficient n['’]est pas utilisé \(moyenne simple\)\. Au secondaire, une matière"), "Une matière"),
]
_BLOC_SANS_TEXTE = re.compile(r"(<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->)", re.S | re.I)
_TEXTE = re.compile(r">([^<>]+)<")


def adapter_texte(t):
    for rx, r in _REMPL:
        t = rx.sub(r, t)
    return t


_ATTR = re.compile(r'(\b(?:placeholder|title|aria-label)=")([^"]*)(")')


def adapter_html(html):
    parts = _BLOC_SANS_TEXTE.split(html)
    for i in range(0, len(parts), 2):          # les indices pairs sont hors script / style / commentaire
        parts[i] = _TEXTE.sub(lambda m: ">" + adapter_texte(m.group(1).replace("&#39;", "'")) + "<", parts[i])
        parts[i] = _ATTR.sub(lambda m: m.group(1) + adapter_texte(m.group(2).replace("&#39;", "'")) + m.group(3), parts[i])
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


# Modules propres au primaire : inutiles (et trompeurs) dans l'application d'un collège ou d'un lycée
BLOQUES = ("/juridiction/up", "/juridiction/themes-up", "/preparation", "/synoptique", "/themes-up", "/recensement", "/maitre-semaine", "/poesies", "/cep",
           "/examens/cep2027")


def est_bloque(chemin):
    return any(chemin == p or chemin.startswith(p + "/") or (p == "/cep" and chemin.startswith("/cep-")) for p in BLOQUES)


def _bloque_en_juridiction(chemin):
    """Dans les éditions d'inspection / de direction du secondaire, seules les unités pédagogiques (UP) et leurs thèmes sont masquées."""
    return any(chemin == p or chemin.startswith(p + "/") for p in ("/juridiction/up", "/juridiction/themes-up", "/themes-up"))


def _niveaux_secondaire():
    try:
        import m_uascep
        m_uascep.NIVEAUX[:] = [x for x in m_uascep.NIVEAUX if x[0] != "UP"]
    except Exception:  # noqa: BLE001
        pass
    """Dans les éditions du secondaire, les listes de « cours » des modules deviennent les niveaux 6e à Tle."""
    from calcul import NIVEAUX_SECONDAIRE
    for nom in ("m_inspection", "m_patrimoine_pvs", "m_sante_scolaire", "m_sport"):
        try:
            mod = __import__(nom)
            if isinstance(getattr(mod, "COURS", None), list):
                mod.COURS[:] = list(NIVEAUX_SECONDAIRE)
        except Exception:  # noqa: BLE001
            pass
    try:
        import m_ecoles
        m_ecoles.ORDRES[:] = ["Secondaire (collège)", "Secondaire (collège et lycée)", "Enseignement technique"]
    except Exception:  # noqa: BLE001
        pass
    try:
        import m_epreuves
        m_epreuves.NIVEAUX[:] = list(NIVEAUX_SECONDAIRE) if isinstance(m_epreuves.NIVEAUX, list) else m_epreuves.NIVEAUX
    except Exception:  # noqa: BLE001
        pass


def enregistrer(app, H):
    if config.secondaire():
        try:
            _brancher_pdf()
        except Exception:  # noqa: BLE001
            pass
        try:
            _niveaux_secondaire()
        except Exception:  # noqa: BLE001
            pass
        if True:
            from flask import flash, redirect

            @app.before_request
            def _modules_du_primaire():
                if est_bloque(request.path) and not (config.juridiction() and not _bloque_en_juridiction(request.path)):
                    flash("Ce module est réservé au primaire : il n'existe pas dans l'application du secondaire.")
                    return redirect("/")
    @app.after_request
    def _vocabulaire_secondaire(r):
        try:
            if (config.secondaire() and r.status_code == 200 and not r.direct_passthrough
                    and (r.mimetype or "") == "text/html"):
                r.set_data(adapter_html(r.get_data(as_text=True)))
        except Exception:  # noqa: BLE001
            pass
        return r
