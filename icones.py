# -*- coding: utf-8 -*-
"""v1.25 — Icônes au trait (dessins originaux, SVG 24 × 24, trait = couleur du texte) : remplacent les émojis dans
toutes les pages (règle : « pas d'émojis, des dessins d'art »).

Emploi dans les gabarits : {{ icone('telecharger') }} ou {{ icone('ecole', 18, 'École') }} (libellé accessible).
Noms alignés sur le jeu commun des applications JS (outils/icones/icones.js) ; un nom inconnu donne une pastille neutre.
"""
import re

from markupsafe import Markup, escape

# éléments SVG (repère 24 × 24), dessinés au trait : fill="none" stroke="currentColor" (sauf mention fill)
D = {
    "document": '<path d="M6 2.8h8l4 4V21.2H6z"/><path d="M14 2.8v4h4"/><path d="M9 12h6M9 15.5h6M9 9h3"/>',
    "telecharger": '<path d="M12 3.5v11"/><path d="M7.5 10.5 12 15l4.5-4.5"/><path d="M4.5 16.5v3.5h15v-3.5"/>',
    "importer": '<path d="M12 15V4"/><path d="M7.5 8.5 12 4l4.5 4.5"/><path d="M4.5 16.5v3.5h15v-3.5"/>',
    "enregistrer": '<path d="M4 4h12.5L20 7.5V20H4z"/><path d="M8 4v5h7V4"/><rect x="7.5" y="13" width="9" height="7"/>',
    "graphique": '<path d="M4 20h16"/><path d="M6.5 20v-6M11 20V9M15.5 20v-9M20 20V5"/>',
    "progression": '<path d="M4 20h16"/><path d="M4.5 16 9 11l3.5 3L19 7"/><path d="M15 7h4v4"/>',
    "supprimer": '<path d="M4.5 6.5h15"/><path d="M9.5 6.5V4h5v2.5"/><path d="M6.5 6.5 7.5 20h9l1-13.5"/><path d="M10 10v7M14 10v7"/>',
    "ecole": '<path d="M3 10.5 12 4l9 6.5"/><path d="M5 9.5V20h14V9.5"/><path d="M10 20v-5h4v5"/><path d="M12 4V1.8h3"/>',
    "ajouter": '<circle cx="12" cy="12" r="8.5"/><path d="M12 8v8M8 12h8"/>',
    "modifier": '<path d="M4 20l1-4.5L16 4.5l3.5 3.5L8.5 19z"/><path d="M14 7l3.5 3.5"/>',
    "dossier": '<path d="M3 6.5h6l2 2h10V19H3z"/><path d="M3 10h18"/>',
    "valider": '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.3l2.7 2.7L16.2 9"/>',
    "coche": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "reinitialiser": '<path d="M5 12a7 7 0 1 0 2.1-5"/><path d="M4.5 3.8v4.2h4.2"/>',
    "actualiser": '<path d="M19 9a7.5 7.5 0 0 0-13.2-2"/><path d="M5 15a7.5 7.5 0 0 0 13.2 2"/><path d="M5.5 3.5V7h3.5M18.5 20.5V17H15"/>',
    "message": '<path d="M4 5h16v11H9.5L5 20v-4H4z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "etoile": '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z"/>',
    "groupe": '<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19c.5-3.5 2.6-5.5 5.5-5.5s5 2 5.5 5.5"/><circle cx="16.5" cy="9.5" r="2.4"/><path d="M15.5 13.6c2.6 0 4.4 1.8 5 4.9"/>',
    "personne": '<circle cx="12" cy="8" r="3.6"/><path d="M5 20c.7-4 3.3-6.3 7-6.3s6.3 2.3 7 6.3"/>',
    "eleve": '<circle cx="12" cy="9" r="3.3"/><path d="M6 20c.6-3.4 2.9-5.4 6-5.4s5.4 2 6 5.4"/><path d="M7.5 5.5 12 3.5l4.5 2-4.5 2z"/>',
    "enseignant": '<circle cx="8" cy="8" r="3"/><path d="M3 20c.5-3.6 2.4-5.6 5-5.6 1.6 0 3 .7 3.9 2"/><path d="M12 4h9v8h-6"/><path d="M14.5 12l3 4"/>',
    "puce": '<rect x="9" y="9" width="6" height="6" fill="currentColor" stroke="none"/>',
    "diplome": '<path d="M2.5 9 12 4.5 21.5 9 12 13.5z"/><path d="M6.5 11v4.5c1.5 1.5 3.5 2.2 5.5 2.2s4-.7 5.5-2.2V11"/><path d="M20 10v5.5"/>',
    "imprimer": '<path d="M7 9V3.5h10V9"/><rect x="3.5" y="9" width="17" height="7.5" rx="1.5"/><path d="M7 14h10v6.5H7z"/>',
    "echanger": '<path d="M4 8h15"/><path d="M15.5 4.5 19 8l-3.5 3.5"/><path d="M20 16H5"/><path d="M8.5 12.5 5 16l3.5 3.5"/>',
    "note": '<path d="M5 3.5h14v17H5z"/><path d="M8.5 8h7M8.5 11.5h7M8.5 15h4"/>',
    "liste": '<path d="M9 6.5h11M9 12h11M9 17.5h11"/><circle cx="5" cy="6.5" r="1" fill="currentColor"/><circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="5" cy="17.5" r="1" fill="currentColor"/>',
    "presse_papiers": '<rect x="5" y="4.5" width="14" height="16" rx="1.5"/><path d="M9 4.5V3h6v1.5"/><path d="M8.5 10h7M8.5 13.5h7M8.5 17h4"/>',
    "attention": '<path d="M12 3.5 21 19.5H3z"/><path d="M12 9.5v4.5"/><circle cx="12" cy="16.8" r=".9" fill="currentColor"/>',
    "calendrier": '<rect x="3.5" y="5" width="17" height="15" rx="1.5"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/><path d="M7.5 13h2M11 13h2M14.5 13h2M7.5 16.5h2M11 16.5h2"/>',
    "suivant": '<path d="M9 5.5 15.5 12 9 18.5"/>',
    "precedent": '<path d="M15 5.5 8.5 12l6.5 6.5"/>',
    "envoyer": '<path d="M3.5 11.5 20.5 4l-6.5 16.5-2.8-6.7z"/><path d="M11.2 13.8 20.5 4"/>',
    "recevoir": '<path d="M3.5 13.5h5l1.5 2.5h4l1.5-2.5h5"/><path d="M3.5 13.5 6 6h12l2.5 7.5V20h-17z"/><path d="M12 3v7M9.5 7.5 12 10l2.5-2.5"/>',
    "classeur": '<rect x="4" y="3.5" width="16" height="17" rx="1"/><path d="M4 9.2h16M4 14.8h16"/><path d="M10.5 6.4h3M10.5 12h3M10.5 17.6h3"/>',
    "cle": '<circle cx="8" cy="12" r="4"/><path d="M12 12h8.5M17 12v3M20 12v2.5"/>',
    "rechercher": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/>',
    "retour": '<path d="M9 7 4.5 11.5 9 16"/><path d="M4.5 11.5H15a5 5 0 0 1 0 10h-2"/>',
    "signature": '<path d="M3 17c2.5-6 4.5-9 6-9 2.5 0-1.5 8 1 8 1.4 0 2.3-3 3.6-3 1 0 .8 2 1.9 2 .8 0 1.5-.7 2.5-1.5"/><path d="M3 20.5h18"/>',
    "menu": '<path d="M4 6.5h16M4 12h16M4 17.5h16"/>',
    "livre": '<path d="M12 6.5C10 5 7 4.5 3.5 5v13.5c3.5-.5 6.5 0 8.5 1.5 2-1.5 5-2 8.5-1.5V5c-3.5-.5-6.5 0-8.5 1.5z"/><path d="M12 6.5V20"/>',
    "reglages": '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.8 1.8M16.7 16.7l1.8 1.8M5.5 18.5l1.8-1.8M16.7 7.3l1.8-1.8"/>',
    "trophee": '<path d="M7.5 4h9v5a4.5 4.5 0 0 1-9 0z"/><path d="M7.5 6H4.5c0 3 1.2 4.3 3.3 4.6M16.5 6h3c0 3-1.2 4.3-3.3 4.6"/><path d="M12 13.5V17M8.5 20.5h7M9.5 17h5v3.5h-5z"/>',
    "medaille": '<path d="M8 3h3l1 5M16 3h-3l-1 5"/><circle cx="12" cy="14.5" r="5.5"/><path d="M12 11.8l.9 1.8 2 .3-1.4 1.4.3 2L12 16.4l-1.8.9.3-2-1.4-1.4 2-.3z"/>',
    "fiche": '<rect x="3" y="5" width="18" height="14" rx="1.5"/><circle cx="8.5" cy="11" r="2.2"/><path d="M5.5 16.5c.5-1.8 1.6-2.8 3-2.8s2.5 1 3 2.8"/><path d="M14 9.5h4.5M14 12.5h4.5M14 15.5h3"/>',
    "photo": '<path d="M3.5 8h4l1.5-2.5h6L16.5 8h4v11.5h-17z"/><circle cx="12" cy="13.5" r="3.5"/>',
    "institution": '<path d="M3 9 12 4l9 5z"/><path d="M5 9.5v8M9.5 9.5v8M14.5 9.5v8M19 9.5v8"/><path d="M3 20.5h18M4 17.5h16"/>',
    "deverrouiller": '<rect x="5" y="11" width="14" height="9.5" rx="1.5"/><path d="M8.5 11V7.5a3.5 3.5 0 0 1 6.8-1.2"/><path d="M12 14.5v2.5"/>',
    "verrou": '<rect x="5" y="11" width="14" height="9.5" rx="1.5"/><path d="M8.5 11V7.5a3.5 3.5 0 0 1 7 0V11"/><path d="M12 14.5v2.5"/>',
    "alerte": '<path d="M12 3.5a6 6 0 0 1 6 6v4.5l1.8 3H4.2L6 14V9.5a6 6 0 0 1 6-6z"/><path d="M9.8 20a2.3 2.3 0 0 0 4.4 0"/>',
    "accueil": '<path d="M3.5 11 12 4l8.5 7"/><path d="M6 9.5V20h12V9.5"/><path d="M10 20v-5.5h4V20"/>',
    "telephone": '<rect x="7" y="2.8" width="10" height="18.4" rx="2"/><path d="M10.5 18h3"/>',
    "lieu": '<path d="M12 21s6.5-6.2 6.5-11a6.5 6.5 0 0 0-13 0c0 4.8 6.5 11 6.5 11z"/><circle cx="12" cy="10" r="2.4"/>',
    "piece_jointe": '<path d="M19 11.5l-7.2 7.2a4.5 4.5 0 0 1-6.4-6.4l7.6-7.6a3 3 0 0 1 4.3 4.3l-7.4 7.4a1.5 1.5 0 0 1-2.1-2.1l6.8-6.8"/>',
    "calcul": '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M8 7h8v3H8z"/><path d="M8.5 13.5h1M11.5 13.5h1M14.5 13.5h1M8.5 17h1M11.5 17h1M14.5 17h1"/>',
    "horloge": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>',
    "sablier": '<path d="M6.5 3.5h11M6.5 20.5h11"/><path d="M7.5 3.5c0 4.5 4.5 5.5 4.5 8.5s-4.5 4-4.5 8.5M16.5 3.5c0 4.5-4.5 5.5-4.5 8.5s4.5 4 4.5 8.5"/>',
    "cantine": '<path d="M4 12h16a8 8 0 0 1-16 0z"/><path d="M3 12h18"/><path d="M9 4.5c-1 1.3 1 2.2 0 3.5M12.5 4.5c-1 1.3 1 2.2 0 3.5M16 4.5c-1 1.3 1 2.2 0 3.5"/>',
    "argent": '<rect x="3" y="6.5" width="18" height="11" rx="1.5"/><circle cx="12" cy="12" r="2.8"/><path d="M6 9.5v5M18 9.5v5"/>',
    "voir": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    "annonce": '<path d="M3.5 10v4h3l7 4.5V5.5L6.5 10z"/><path d="M17 9a4 4 0 0 1 0 6M19.5 6.5a7.5 7.5 0 0 1 0 11"/>',
    "image": '<rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/><circle cx="9" cy="9.5" r="1.8"/><path d="M3.5 17l5-4.5 3.5 3 3-2.5 5.5 4.5"/>',
    "cible": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    "balance": '<path d="M12 4v16M7 20.5h10M5 7h14"/><path d="M5 7l-2.5 6h5zM19 7l-2.5 6h5z"/>',
    "courrier": '<rect x="3" y="5.5" width="18" height="13" rx="1.5"/><path d="M3.5 6.5 12 13l8.5-6.5"/>',
    "nombres": '<path d="M4 8.5l2-1.5v10M3.5 17h5"/><path d="M10.5 9a2 2 0 0 1 4 0c0 2-4 4-4 8h4"/><path d="M17 8h3.5l-2 3a2.5 2.5 0 1 1-2 4.5"/>',
    "proposer": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
    "sante": '<path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 7.5 3c0 5.4-7.5 10-7.5 10z"/><path d="M12 10v5M9.5 12.5h5"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r=".9" fill="currentColor"/>',
    "boussole": '<circle cx="12" cy="12" r="8.5"/><path d="M15.5 8.5 13.5 13.5 8.5 15.5 10.5 10.5z"/>',
    "chantier": '<path d="M4 20.5h16"/><path d="M6 20.5V9h12v11.5"/><path d="M6 13h12M6 17h12M10 9v11.5M14 9v11.5"/><path d="M9 9V5h6v4"/>',
    "recu": '<path d="M6 3h12v18l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5L6 21z"/><path d="M9 8h6M9 11.5h6M9 15h4"/>',
    "module": '<path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/>',
    "partenariat": '<path d="M2.5 11 7 6.5l3.5 1.5 3-1.5 3.5 1 4.5 4.5"/><path d="M7.5 13l3.5 3.5a1.4 1.4 0 0 0 2-2M10 12.5l3.5 3.5a1.4 1.4 0 0 0 2-2L12 10.5"/><path d="M2.5 11l3 3M21.5 11l-3 3"/>',
    "fermer": '<path d="M6 6l12 12M18 6 6 18"/>',
    "archives": '<rect x="3.5" y="4" width="17" height="4.5" rx="1"/><path d="M5 8.5V20h14V8.5"/><path d="M10 12h4"/>',
    "texte": '<path d="M5 6V4.5h14V6M12 4.5V19.5M9 19.5h6"/>',
    "monde": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.5 3.5 5.5 3.5 8.5s-1 6-3.5 8.5c-2.5-2.5-3.5-5.5-3.5-8.5s1-6 3.5-8.5z"/>',
    "attestation": '<path d="M5 3.5h14v13.5H5z"/><path d="M8 7.5h8M8 10.5h8M8 13.5h4"/><circle cx="15.5" cy="17.5" r="2.5"/><path d="M14.3 19.6 13.5 22l2-1 2 1-.8-2.4"/>',
    "licence": '<rect x="2.5" y="5" width="19" height="14" rx="2"/><circle cx="8" cy="11" r="2.4"/><path d="M5 16.5c.6-2 1.6-3 3-3s2.4 1 3 3"/><path d="M14 9.5h5M14 12.5h5M14 15.5h3"/>',
    "tirage": '<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="8.5" cy="8.5" r="1.1" fill="currentColor"/><circle cx="15.5" cy="15.5" r="1.1" fill="currentColor"/><circle cx="12" cy="12" r="1.1" fill="currentColor"/><circle cx="15.5" cy="8.5" r="1.1" fill="currentColor"/><circle cx="8.5" cy="15.5" r="1.1" fill="currentColor"/>',
    "epingle": '<path d="M9 3.5h6l-1 5 3 3H7l3-3z"/><path d="M12 11.5v9"/>',
    "case": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "case_cochee": '<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M8.5 12.2l2.5 2.5 4.5-5"/>',
    "interdit": '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
    "carte": '<path d="M3.5 6.5 9 4.5l6 2 5.5-2v13l-5.5 2-6-2-5.5 2z"/><path d="M9 4.5v13M15 6.5v13"/>',
    "nouveau": '<path d="M12 3l2.2 3.8 4.3-.7-1.6 4 3.1 2.9-4.2 1.2.2 4.3-4-1.8-4 1.8.2-4.3L4 13l3.1-2.9-1.6-4 4.3.7z"/>',
    "sport": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5l3.8 2.8-1.5 4.4H9.7l-1.5-4.4z"/><path d="M12 3.5v4M20.2 9.6l-4.4.7M17.2 19.3l-2.9-4.6M6.8 19.3l2.9-4.6M3.8 9.6l4.4.7"/>',
    "pilotage": '<path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l4-5.5"/><circle cx="12" cy="17" r="1.3" fill="currentColor"/><path d="M6.5 13.5l1 .6M12 9v1M17.5 13.5l-1 .6"/>',
    "verifier": '<path d="M12 3 19.5 6v5.5c0 4.5-3.2 8-7.5 9.5-4.3-1.5-7.5-5-7.5-9.5V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "structure": '<rect x="9" y="3" width="6" height="4.5"/><rect x="3" y="16.5" width="6" height="4.5"/><rect x="15" y="16.5" width="6" height="4.5"/><path d="M12 7.5v4.5M6 16.5V12h12v4.5"/>',
    "saisie": '<rect x="3" y="6" width="18" height="12" rx="1.5"/><path d="M6.5 9.5h1M9.5 9.5h1M12.5 9.5h1M15.5 9.5h1M7.5 14.5h9"/>',
    "transmission": '<path d="M7 4v14"/><path d="M3.5 7.5 7 4l3.5 3.5"/><path d="M17 20V6"/><path d="M13.5 16.5 17 20l3.5-3.5"/>',
    "statistiques": '<path d="M4 20h16"/><rect x="5.5" y="12" width="3" height="8"/><rect x="10.5" y="7" width="3" height="13"/><rect x="15.5" y="10" width="3" height="10"/>',
    "tableau": '<rect x="3.5" y="4.5" width="17" height="15" rx="1"/><path d="M3.5 9h17M3.5 14h17M9 4.5v15M14.5 4.5v15"/>',
    "dupliquer": '<rect x="8" y="8" width="12" height="12" rx="1.5"/><path d="M16 8V4H4v12h4"/>',
    "lecture": '<path d="M3 5.5c3-1 6-.5 9 1.5 3-2 6-2.5 9-1.5v13c-3-1-6-.5-9 1.5-3-2-6-2.5-9-1.5z"/>',
    "pointeur": '<path d="M5.5 3.5 18 11l-5.5 1.8L10 18.5z"/>',
}
# jeu commun (outils/lots/spec.md § Icônes, outils/icones/icones.js) : mêmes noms, même ordre, mêmes tracés
COMMUN = [
    ('accueil', 'M3 11l9-7 9 7|M5 10v10h14V10|M10 20v-6h4v6'),
    ('ajouter', 'M12 5v14|M5 12h14'),
    ('fermer', 'M6 6l12 12|M18 6L6 18'),
    ('valider', 'M5 12.5l4.5 4.5L19 7.5'),
    ('valider-cercle', 'c:12,12,9|M7.5 12.3l3 3 6-6.3'),
    ('supprimer', 'M4 7h16|M9 7V4h6v3|M6 7l1 13h10l1-13|M10 11v6|M14 11v6'),
    ('modifier', 'M4 20l1-4L16 5l3 3L8 19z|M14 7l3 3'),
    ('enregistrer', 'M5 4h11l3 3v13H5z|M8 4v5h7V4|r:8,13,8,7,0.5'),
    ('imprimer', 'M7 9V4h10v5|r:4,9,16,7,1.5|M7 14h10v6H7z|M17 12h.01'),
    ('telecharger', 'M12 4v11|M7 10l5 5 5-5|M5 20h14'),
    ('televerser', 'M12 20V9|M7 14l5-5 5 5|M5 4h14'),
    ('importer', 'M4 14v5h16v-5|M12 4v10|M8 10l4 4 4-4'),
    ('exporter', 'M4 14v5h16v-5|M12 14V4|M8 8l4-4 4 4'),
    ('document', 'M6 3h8l4 4v14H6z|M14 3v4h4|M9 12h6|M9 16h6'),
    ('fiche', 'M6 3h9l3 3v15H6z|M9 9h6|M9 13h4|M12.5 19l1-3 4-4 2 2-4 4z'),
    ('presse-papiers', 'r:5,5,14,16,1.5|M9 3h6v4H9z|M8.5 12h7|M8.5 16h5'),
    ('bloc-notes', 'r:5,4,14,17,1.5|M8 2v4|M12 2v4|M16 2v4|M8 11h8|M8 15h6'),
    ('classeur', 'M3 8h18v12H3z|M5 8V5h5l2 3|M7 12h10|M7 16h6'),
    ('fichier', 'r:3,6,18,13,1.5|M7 6V4h10v2|c:9,12.5,2|M13 11h4|M13 14h4|M6.5 17c.6-1.5 4.4-1.5 5 0'),
    ('dossier', 'M3 6h6l2 2h10v11H3z'),
    ('dossier-ouvert', 'M3 6h6l2 2h8v3|M3 6v13h15l3-8H7l-4 8'),
    ('graphique', 'M4 20h16|M6 20v-6|M10 20V8|M14 20v-9|M18 20V5'),
    ('courbe', 'M4 20h16|M4 4v16|M6 16l4-5 3 3 6-7|M15 7h4v4'),
    ('calendrier', 'r:3,5,18,16,1.5|M3 10h18|M8 3v4|M16 3v4|M7 14h2|M11 14h2|M15 14h2|M7 17h2|M11 17h2'),
    ('horloge', 'c:12,12,9|M12 7v5l3 2'),
    ('sablier', 'M7 3h10|M7 21h10|M8 3c0 5 8 6 8 9s-8 4-8 9|M16 3c0 5-8 6-8 9s8 4 8 9'),
    ('reveil', 'c:12,13,7|M12 10v3l2 1.5|M5 4L3 6|M19 4l2 2'),
    ('chrono', 'c:12,14,7|M12 14v-3|M10 3h4|M12 3v4|M18 7l1.5-1.5'),
    ('groupe', 'c:9,8,3|M3.5 19c.6-3.4 3-5 5.5-5s4.9 1.6 5.5 5|c:16.5,9,2.5|M15 14c3 0 5 1.5 5.5 4.5'),
    ('personne', 'c:12,8,4|M5 20c.8-4 3.7-6 7-6s6.2 2 7 6'),
    ('enseignant', 'c:7,8,2.6|M2.8 19c.4-3 2.2-4.6 4.2-4.6S10.8 16 11.2 19|r:12,4,9,8,0.8|M12 16l4-4|M14 12h7'),
    ('eleve', 'c:12,7,3.2|M7 21v-4c0-2.8 2.2-5 5-5s5 2.2 5 5v4|M9 21v-3|M15 21v-3'),
    ('diplome', 'M2 9l10-5 10 5-10 5z|M6 11v5c3 2.5 9 2.5 12 0v-5|M21 9v6'),
    ('cartable', 'M6 8h12a2 2 0 0 1 2 2v9H4v-9a2 2 0 0 1 2-2z|M9 8V5h6v3|M4 13h16|M11 13v2h2v-2'),
    ('ecole', 'M3 21h18|M5 21V10l7-5 7 5v11|M10 21v-5h4v5|M12 5V2h3|c:12,11,1.6'),
    ('institution', 'M3 21h18|M4 18h16|M4 9h16|M12 3l9 5H3z|M6 9v9|M10 9v9|M14 9v9|M18 9v9'),
    ('batiment', 'r:5,3,14,18,1|M9 7h2|M13 7h2|M9 11h2|M13 11h2|M9 15h2|M13 15h2|M11 21v-3h2v3'),
    ('quartier', 'M2 21h20|M3 21v-8l5-4 5 4v8|M13 21v-6h8v6|M7 21v-4h2v4|M16 11l3-3 3 3'),
    ('chantier', 'M4 21h16|M7 21V5|M7 5h12|M7 8l4-3|M17 5v5|r:15.5,10,3,3,0.5|M10 21v-5h4v5'),
    ('stade', 'M2 12c0-4 4.5-6 10-6s10 2 10 6-4.5 6-10 6S2 16 2 12z|M6 12c0-2 2.6-3 6-3s6 1 6 3-2.6 3-6 3-6-1-6-3z|M12 6v3|M12 15v3'),
    ('chaise', 'M7 3v9h10|M7 12v9|M17 12v9|M7 16h10|M7 3h3'),
    ('signature', 'M3 17c3-1 4-9 6-9s1 8 3 8 2-5 4-5 1 3 2 3h3|M3 21h18'),
    ('rechercher', 'c:10.5,10.5,6.5|M15.5 15.5L21 21'),
    ('carte-identite', 'r:3,5,18,14,1.8|c:8.5,11,2.2|M5.5 16c.6-1.8 5.4-1.8 6 0|M14 10h4|M14 13h4|M14 16h2'),
    ('repere', 'M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11z|c:12,10,2.3'),
    ('epingle', 'M9 3h6|M10 3v6l-3 4h10l-3-4V3|M12 13v8'),
    ('cible', 'c:12,12,9|c:12,12,5|c:12,12,1.2'),
    ('attestation', 'M6 4h11a2 2 0 0 1 2 2v12|M6 4a2 2 0 0 0-2 2v1h3|M7 6v12a2 2 0 0 1-2 2h11a2 2 0 0 0 2-2|M10 9h6|M10 12h6|M10 15h3'),
    ('livre', 'M4 5h5a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H4z|M20 5h-5a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h6z'),
    ('livres', 'r:3,4,4,16,0.8|r:8,4,4,16,0.8|M14 6l3.8-1 4 14.6-3.8 1z|M3 8h4|M8 8h4'),
    ('cle', 'c:8,14,4|M11 11l9-9|M17 5l2 2|M15 7l2 2'),
    ('cadenas', 'r:5,10,14,11,1.8|M8 10V7a4 4 0 0 1 8 0v3|M12 14v3'),
    ('deverrouiller', 'r:5,10,14,11,1.8|M8 10V7a4 4 0 0 1 7.6-1.8|M12 14v3'),
    ('message', 'M4 5h16v11H9l-5 4z|M8 9h8|M8 12h5'),
    ('interdit', 'c:12,12,9|M5.6 5.6l12.8 12.8'),
    ('retour', 'M9 14l-5-5 5-5|M4 9h10a6 6 0 0 1 0 12h-3'),
    ('precedent', 'M15 5l-7 7 7 7'),
    ('suivant', 'M9 5l7 7-7 7'),
    ('fleche-droite', 'M4 12h15|M13 6l6 6-6 6'),
    ('ouvrir', 'M14 4h6v6|M20 4l-9 9|M18 14v6H4V6h6'),
    ('photo', 'M4 8h3l2-3h6l2 3h3v12H4z|c:12,13.5,3.5'),
    ('suggestion', 'M12 3v4|M12 17v4|M3 12h4|M17 12h4|M12 9l1 2 2 1-2 1-1 2-1-2-2-1 2-1z|M18 4l.5 1.5L20 6l-1.5.5L18 8l-.5-1.5L16 6l1.5-.5z'),
    ('menu', 'M4 6h16|M4 12h16|M4 18h16'),
    ('balance', 'M12 4v16|M8 20h8|M5 7h14|M5 7l-3 7h6z|M19 7l-3 7h6z|c:12,4,1'),
    ('calcul', 'r:5,3,14,18,2|r:8,6,8,4,0.5|M8.5 13.5h.01|M12 13.5h.01|M15.5 13.5h.01|M8.5 17h.01|M12 17h.01|M15.5 17h.01'),
    ('alerte', 'M12 3l10 18H2z|M12 10v5|M12 18h.01'),
    ('boussole', 'c:12,12,9|M15.5 8.5l-2 5-5 2 2-5z'),
    ('voir', 'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z|c:12,12,3'),
    ('accord', 'M3 11l4-4 5 3 5-3 4 4|M7 7l-4 5 6 6 2-2|M17 7l4 5-6 6-3-3|M10 13l2 2|M12 11l3 3'),
    ('telephone', 'r:7,2,10,20,2|M11 18h2'),
    ('image', 'r:3,4,18,16,1.5|c:9,9.5,1.8|M3 17l5-5 4 4 3-3 6 6'),
    ('insigne', 'c:12,9,6|c:12,9,2.5|M8.5 14L7 22l5-2.5 5 2.5-1.5-8'),
    ('carte', 'M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z|M9 4v14|M15 6v14'),
    ('monde', 'c:12,12,9|M3 12h18|M12 3c3 3.5 3 14.5 0 18|M12 3c-3 3.5-3 14.5 0 18'),
    ('balai', 'M14 3l-4 9|M7 12h7l3 9H4z|M8 16l-1 5|M12 16v5'),
    ('recu', 'M6 3h12v18l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5L6 21z|M9 8h6|M9 12h6|M9 16h3'),
    ('trophee', 'M8 4h8v5a4 4 0 0 1-8 0z|M8 6H4v1a4 4 0 0 0 4 4|M16 6h4v1a4 4 0 0 1-4 4|M12 13v4|M8 21h8|M9 17h6v4H9z'),
    ('medaille', 'M8 3l4 7 4-7|M6 3h4|M14 3h4|c:12,15,5|M12 12.5l.8 1.6 1.7.2-1.2 1.2.3 1.7-1.6-.8-1.6.8.3-1.7-1.2-1.2 1.7-.2z'),
    ('argent', 'r:3,6,18,12,1.5|c:12,12,3|M6 9h.01|M18 15h.01'),
    ('courrier', 'r:3,5,18,14,1.5|M3 7l9 6 9-6'),
    ('annonce', 'M3 10v4h3l7 4V6L6 10z|M16 9a4 4 0 0 1 0 6|M19 6a8 8 0 0 1 0 12'),
    ('reglages', 'c:12,12,3|M12 2v3|M12 19v3|M2 12h3|M19 12h3|M4.9 4.9L7 7|M17 17l2.1 2.1|M4.9 19.1L7 17|M17 7l2.1-2.1'),
    ('outils', 'M14.5 6.5a4 4 0 0 1-5 5L4 17l3 3 5.5-5.5a4 4 0 0 0 5-5l-2.5 2.5-2-2z'),
    ('lien', 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1|M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1'),
    ('puzzle', 'M4 8h4a2 2 0 1 1 4 0h4v4a2 2 0 1 1 0 4v4h-4a2 2 0 1 0-4 0H4v-4a2 2 0 1 0 0-4z'),
    ('cloche', 'M6 16V11a6 6 0 0 1 12 0v5l2 2H4z|M10 20a2 2 0 0 0 4 0'),
    ('etiquette', 'M3 12V4h8l10 10-8 8z|c:7.5,8.5,1.5'),
    ('echange', 'M4 9h16|M16 5l4 4-4 4|M20 15H4|M8 11l-4 4 4 4'),
    ('actualiser', 'M20 11a8 8 0 0 0-14.6-4.5L3 9|M3 4v5h5|M4 13a8 8 0 0 0 14.6 4.5L21 15|M21 20v-5h-5'),
    ('melanger', 'M3 7h4l10 10h4|M3 17h4l3-3|M14 10l3-3h4|M18 4l3 3-3 3|M18 14l3 3-3 3'),
    ('eclair', 'M13 2L5 14h6l-1 8 8-12h-6z'),
    ('repas', 'M4 13h16a8 8 0 0 1-16 0z|M2 21h20|M8 9c0-2 2-2 2-4|M12 9c0-2 2-2 2-4'),
    ('nouveau', 'M12 3l2.4 5.2 5.6.6-4.2 3.8 1.2 5.5L12 15.3 7 18.1l1.2-5.5L4 8.8l5.6-.6z'),
    ('etoile', 'M12 3l2.6 5.6 6.1.6-4.6 4.1 1.3 6L12 16.4l-5.4 2.9 1.3-6-4.6-4.1 6.1-.6z'),
    ('nuage', 'M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9z'),
    ('science', 'M9 3h6|M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3|M7.5 15h9'),
    ('trombone', 'M8 12l6-6a3 3 0 0 1 4.2 4.2l-7.5 7.5a5 5 0 0 1-7-7L11 3.5'),
    ('regle', 'M3 17L17 3l4 4L7 21z|M7 13l2 2|M10 10l2 2|M13 7l2 2'),
    ('camion', 'M2 6h11v10H2z|M13 9h4l4 4v3h-8|c:6,18,2|c:17,18,2'),
    ('brique', 'r:3,5,18,14,0.5|M3 9.7h18|M3 14.3h18|M9 5v4.7|M15 5v4.7|M6 9.7v4.6|M12 9.7v4.6|M18 9.7v4.6|M9 14.3V19|M15 14.3V19'),
    ('cerveau', 'M12 5a3 3 0 0 0-5.5 1.5A3 3 0 0 0 4 11a3 3 0 0 0 1.5 5.5A3 3 0 0 0 12 19z|M12 5a3 3 0 0 1 5.5 1.5A3 3 0 0 1 20 11a3 3 0 0 1-1.5 5.5A3 3 0 0 1 12 19|M12 5v14'),
    ('enfants', 'c:8,6,2.2|c:16,7,1.8|M5 21l1-5-2-3 4-4 3 3|M14 21v-4l-1-3 3-3 3 3|M2 21h20'),
    ('bienvenue', 'c:12,12,9|M8.5 14a4 4 0 0 0 7 0|M9 9.5h.01|M15 9.5h.01'),
    ('confrontation', 'M4 4l10 10|M14 18l4-4|M16 16l4 4|M20 4L10 14|M10 18l-4-4|M8 16l-4 4'),
    ('securite', 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z|M9 12l2 2 4-4'),
    ('feu-tricolore', 'r:8,2,8,20,2|c:12,7,1.6|c:12,12,1.6|c:12,17,1.6'),
    ('pause', 'M9 5v14|M15 5v14'),
    ('vacances', 'M12 22V10|M12 10C8 6 4 7 3 9|M12 10c4-4 8-3 9-1|M12 10c-2-3-1-6 1-7|M4 22h16'),
    ('drapeau', 'M5 21V4|M5 4h14v10H5|M10 4v10|M10 9h9'),
    ('eau', 'M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11z|M9 15a3 3 0 0 0 3 3'),
    ('colis', 'M3 7l9-4 9 4v10l-9 4-9-4z|M3 7l9 4 9-4|M12 11v10|M7.5 5l9 4'),
    ('accessibilite', 'c:12,4,1.8|M8 8h8|M12 8v6h4l2 5|M9.5 11.5a5 5 0 1 0 6 6.5'),
    ('urne', 'M4 11h16v10H4z|M8 11V5h8v6|M10 8h4|M9 15h6'),
    ('cadeau', 'r:3,9,18,4,0.5|M5 13v8h14v-8|M12 9v12|M12 9c-2-4-6-4-6-1s4 1 6 1c2 0 6 2 6-1s-4-3-6 1'),
    ('ordinateur', 'r:4,4,16,11,1.2|M2 19h20|M9 15l-1 4|M15 15l1 4'),
    ('case', 'r:4,4,16,16,2'),
    ('porte', 'M5 21V3h11v18|M3 21h18|M13 12h.01|M16 6l3 1v14'),
    ('texte', 'M4 18L9 5l5 13|M5.5 14h7|M15 10h6|M15 14h5|M15 18h6'),
    ('monter', 'M6 15l6-6 6 6|M6 9l6-6 6 6'),
    ('point', 'c:12,12,5'),
    ('ballon', 'c:12,12,9|M12 8l3.3 2.4-1.3 3.9h-4l-1.3-3.9z|M12 3v5|M21 10l-5.7.4|M3 10l5.7.4|M16.8 19.3l-2.8-5|M7.2 19.3l2.8-5'),
    ('de', 'r:4,4,16,16,3|M8.5 8.5h.01|M15.5 8.5h.01|M12 12h.01|M8.5 15.5h.01|M15.5 15.5h.01'),
    ('prevision', 'c:12,10,7|M7 21h10|M9 17l-1 4|M15 17l1 4|M9.5 8a3 3 0 0 1 3-2'),
    ('info', 'c:12,12,9|M12 11v6|M12 7.5h.01'),
    ('extincteur', 'r:8,8,8,13,2|M10 8V5h4v3|M14 5h3l2 2|M12 3v2'),
    ('adn', 'M7 3c0 6 10 6 10 12s-10 6-10 6|M17 3c0 6-10 6-10 12s10 6 10 6|M8 7h8|M8 17h8|M9.5 12h5'),
    ('inscription', 'r:4,3,16,18,1.5|M8 8h8|M8 12h8|M8 16l2 2 4-4'),
    ('sante', 'r:3,7,18,13,1.5|M9 7V4h6v3|M12 10.5v6|M9 13.5h6'),
    ('infirmerie', 'M12 21s-8-5-8-11a4.5 4.5 0 0 1 8-3 4.5 4.5 0 0 1 8 3c0 6-8 11-8 11z|M12 9v6|M9 12h6'),
    ('formation', 'r:3,4,18,12,1|M7 20l3-4|M17 20l-3-4|M7 9h6|M7 12h10'),
    ('inspection', 'r:5,3,12,17,1.5|M8 8h6|M8 11h4|c:16,16,3|M18.2 18.2L21 21'),
    ('patrimoine', 'M3 21h18|M5 21V9l7-4 7 4v12|M9 13h6v8H9z|M9 17h6'),
    ('examen', 'M6 3h12v18H6z|M9 7h6|M9 11h6|M9 15l1.5 1.5L14 13'),
]


def _corps(trace):
    out = []
    for el in trace.split("|"):
        if el.startswith("c:"):
            cx, cy, r = el[2:].split(",")
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}"/>')
        elif el.startswith("r:"):
            x, y, l, h, rx = el[2:].split(",")
            out.append(f'<rect x="{x}" y="{y}" width="{l}" height="{h}" rx="{rx}"/>')
        else:
            out.append(f'<path d="{el}"/>')
    return "".join(out)


NOMS = [n for n, _ in COMMUN]
D.update({n: _corps(t) for n, t in COMMUN})


def code(nom):
    """Marque U+E000 + rang (convention commune) ; retirée ou dessinée à l'affichage."""
    return chr(0xE000 + NOMS.index(nom))


def retirer_codes(texte):
    return re.sub("[\uE000-\uF8FF]", "", texte or "")


ALIAS = {"pdf": "document", "excel": "graphique", "export": "telecharger", "import": "importer", "edit": "modifier", "valide": "valider",
         "rapport": "livre", "programme": "livre", "visite": "rechercher", "cachet": "signature", "parametres": "reglages",
         "calendrier_jour": "calendrier", "whatsapp": "message", "sms": "message", "parents": "groupe", "notes": "note",
         "examens": "diplome", "finances": "argent", "classe": "ecole", "eleves": "groupe"}

def svg(nom, taille=16, libelle=""):
    nom = ALIAS.get(nom, nom)
    if isinstance(nom, str) and len(nom) == 1 and 0xE000 <= ord(nom) < 0xE000 + len(NOMS):
        nom = NOMS[ord(nom) - 0xE000]
    corps = D.get(nom) or '<circle cx="12" cy="12" r="4"/>'
    aria = f' role="img" aria-label="{escape(libelle)}"' if libelle else ' aria-hidden="true"'
    return (f'<svg class="icone ic-{escape(nom)}" width="{int(taille)}" height="{int(taille)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" focusable="false"{aria}>{corps}</svg>')


def icone(nom, taille=16, libelle=""):
    """Markup de l'icône (pour les gabarits Jinja)."""
    if not nom:
        return Markup("")
    return Markup(svg(nom, taille, libelle))


def installer(app):
    app.jinja_env.globals["icone"] = icone
    app.jinja_env.globals["ICONES"] = sorted(D)
