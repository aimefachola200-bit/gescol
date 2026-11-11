/* CS Pobè — examen blanc de la circonscription.
   Les matières, le seuil de maîtrise, le classement et les analyses de centre.
   Tout se calcule à partir des notes : rien n'est saisi deux fois. */
(function (global) {
  'use strict';

  /* Les neuf épreuves du relevé de centre, dans l'ordre du procès-verbal.
     La dictée compte pour elle-même, distincte de la communication écrite. */
  const MATIERES = [
    { cle: 'dictee', libelle: 'Dictée', abrege: 'DICT' },
    { cle: 'communication', libelle: 'Communication écrite', abrege: 'COMM' },
    { cle: 'comprehension', libelle: 'Compréhension de l’écrit', abrege: 'COMP' },
    { cle: 'maths', libelle: 'Mathématique', abrege: 'MATH' },
    { cle: 'est', libelle: 'EST', abrege: 'EST' },
    { cle: 'es', libelle: 'ES', abrege: 'ES' },
    { cle: 'ea_vivant', libelle: 'EA vivant', abrege: 'EA-V' },
    { cle: 'ea_artistique', libelle: 'EA artistique', abrege: 'EA-A' },
    { cle: 'eps', libelle: 'EPS', abrege: 'EPS' }
  ];

  /* Une épreuve est maîtrisée à partir de 10 sur 20. Le seuil de réussite
     demande six maîtrises sur les neuf épreuves — six sur huit lorsque le
     candidat est dispensé d'EPS. Le nombre de maîtrises exigées ne bouge pas :
     c'est le nombre d'épreuves composées qui change. */
  const SEUIL_MATIERE = 10;
  const MAITRISES_REQUISES = 6;

  const CENTRES = ['Centre de Pobè centre', 'Centre de Oké-Ola', 'Centre de Pobè/C',
    'Centre de Oké-Ata', 'Centre de Pobè-Nord', 'Centre de Onigbolo', 'Centre de Towé'];

  function note(candidat, cle) {
    const v = parseFloat(String(candidat[cle] === undefined ? '' : candidat[cle]).replace(',', '.'));
    return isNaN(v) ? null : v;
  }

  /** Total, moyenne, nombre de maîtrises et seuil atteint d'un candidat. */
  function resultat(candidat) {
    const notes = MATIERES.map(m => note(candidat, m.cle));
    const composees = notes.filter(n => n !== null);
    const total = composees.reduce((s, n) => s + n, 0);
    const maitrises = composees.filter(n => n >= SEUIL_MATIERE).length;
    /* Six maîtrises sont exigées dans tous les cas : sur neuf épreuves pour un
       candidat ordinaire, sur huit pour un dispensé d'EPS. */
    const requis = MAITRISES_REQUISES;
    return {
      notes: notes, composees: composees.length,
      aCompose: composees.length > 0,
      total: Math.round(total * 100) / 100,
      moyenne: composees.length ? Math.round(total / composees.length * 100) / 100 : null,
      maitrises: maitrises, requis: requis, admis: composees.length > 0 && maitrises >= requis
    };
  }

  /** Classe les candidats d'un centre, les ex æquo partageant le même rang. */
  function classer(candidats) {
    const avec = candidats.map(c => Object.assign({ candidat: c }, resultat(c)));
    const composants = avec.filter(x => x.aCompose)
      .sort((a, b) => b.total - a.total);
    let rang = 0, precedent = null, place = 0;
    composants.forEach(x => {
      place++;
      if (precedent === null || x.total < precedent) { rang = place; precedent = x.total; }
      x.rang = rang;
    });
    avec.filter(x => !x.aCompose).forEach(x => { x.rang = null; });
    return avec;
  }

  function ecartType(valeurs) {
    const v = valeurs.filter(x => typeof x === 'number' && !isNaN(x));
    if (v.length < 2) return 0;
    const m = v.reduce((s, x) => s + x, 0) / v.length;
    return Math.round(Math.sqrt(v.reduce((s, x) => s + (x - m) * (x - m), 0) / v.length) * 100) / 100;
  }

  /** Statistiques d'un centre : participation, réussite, épreuves, écarts. */
  function bilan(candidats) {
    const classes = classer(candidats);
    const compte = (filtre) => classes.filter(filtre).length;
    const parSexe = sexe => {
      const inscrits = compte(x => (x.candidat.sexe || '') === sexe);
      const composes = compte(x => (x.candidat.sexe || '') === sexe && x.aCompose);
      const admis = compte(x => (x.candidat.sexe || '') === sexe && x.admis);
      return {
        inscrits, composes, admis,
        taux: composes ? Math.round(admis / composes * 1000) / 10 : null
      };
    };

    const composants = classes.filter(x => x.aCompose);
    const matieres = MATIERES.map(m => {
      const notes = candidats.map(c => note(c, m.cle)).filter(n => n !== null);
      const moyenne = notes.length
        ? Math.round(notes.reduce((s, n) => s + n, 0) / notes.length * 100) / 100 : null;
      return {
        matiere: m, notes: notes.length, moyenne: moyenne,
        maitrises: notes.filter(n => n >= SEUIL_MATIERE).length,
        taux: notes.length
          ? Math.round(notes.filter(n => n >= SEUIL_MATIERE).length / notes.length * 1000) / 10 : null,
        ecartType: ecartType(notes)
      };
    }).filter(m => m.notes > 0);

    const classees = matieres.slice().sort((a, b) => (b.moyenne || 0) - (a.moyenne || 0));
    const g = parSexe('G'), f = parSexe('F');

    return {
      classes: classes,
      inscrits: classes.length,
      composes: composants.length,
      admis: composants.filter(x => x.admis).length,
      absents: classes.length - composants.length,
      taux: composants.length
        ? Math.round(composants.filter(x => x.admis).length / composants.length * 1000) / 10 : null,
      moyenneCentre: composants.length
        ? Math.round(composants.reduce((s, x) => s + (x.moyenne || 0), 0) / composants.length * 100) / 100
        : null,
      ecartTypeMoyennes: ecartType(composants.map(x => x.moyenne)),
      g: g, f: f,
      ecartGenre: (g.taux !== null && f.taux !== null)
        ? Math.round((f.taux - g.taux) * 10) / 10 : null,
      matieres: matieres,
      fortes: classees.slice(0, 3),
      faibles: classees.slice(-3).reverse()
    };
  }

  /** Recommandations tirées des chiffres, pas de formules toutes faites. */
  function recommandations(b) {
    const sortie = [];
    if (!b.composes) {
      sortie.push("Aucun candidat n'a composé : les notes ne sont pas encore saisies.");
      return sortie;
    }
    if (b.absents) {
      sortie.push(b.absents + ' candidat(s) inscrit(s) n’ont pas composé : en rechercher la '
        + 'cause avec les écoles concernées avant la session officielle.');
    }
    if (b.taux !== null && b.taux < 60) {
      sortie.push('Le taux de réussite au seuil s’établit à ' + b.taux + ' %, en deçà de 60 % : '
        + 'organiser une remédiation ciblée avant la session de juin.');
    } else if (b.taux !== null && b.taux >= 85) {
      sortie.push('Le taux de réussite atteint ' + b.taux + ' % : consolider les acquis et '
        + 'maintenir le rythme des révisions.');
    }
    b.faibles.filter(m => m.taux !== null && m.taux < 60).forEach(m => {
      sortie.push('En ' + m.matiere.libelle + ', ' + m.taux + ' % de maîtrise seulement '
        + '(moyenne ' + m.moyenne + '/20) : programmer une séance d’animation pédagogique '
        + 'sur cette épreuve.');
    });
    if (b.fortes.length && b.fortes[0].taux !== null && b.fortes[0].taux >= 80) {
      sortie.push('L’épreuve la mieux réussie est ' + b.fortes[0].matiere.libelle + ' ('
        + b.fortes[0].taux + ' %) : s’appuyer sur les pratiques des maîtres concernés.');
    }
    if (b.ecartGenre !== null && Math.abs(b.ecartGenre) >= 10) {
      sortie.push('L’écart de réussite entre filles et garçons atteint '
        + Math.abs(b.ecartGenre) + ' points au détriment des '
        + (b.ecartGenre < 0 ? 'filles' : 'garçons') + ' : en tenir compte dans '
        + "l'accompagnement.");
    }
    if (b.ecartTypeMoyennes >= 3) {
      sortie.push('Les moyennes s’étalent fortement (écart type de ' + b.ecartTypeMoyennes
        + ' points) : le centre réunit des niveaux très inégaux, un soutien individualisé '
        + 'est à prévoir.');
    }
    if (!sortie.length) sortie.push('Les résultats du centre n’appellent pas d’observation '
      + 'particulière.');
    return sortie;
  }

  global.ExamenBlanc = { MATIERES, CENTRES, SEUIL_MATIERE, MAITRISES_REQUISES,
    resultat, classer, bilan, recommandations, ecartType };
})(window);
