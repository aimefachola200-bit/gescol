// Côté JS : Mon école (build CS Pobè, /home/claude/cs-pobe/ecole) importe le paquet descendant SCOLARIS, puis prépare un paquet montant.
const { chromium } = require('playwright');
const fs = require('fs');
const [, , base, fDesc, fMont] = process.argv;
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  const erreurs = []; p.on('pageerror', e => erreurs.push(e.message));
  await p.goto(base + '/ecole/index.html'); await p.waitForFunction(() => window.SyncCS && window.SyncCS.client && window.AppBridge && window.PvsCS, null, { timeout: 30000 });
  const oct = [...fs.readFileSync(fDesc)];
  const r = await p.evaluate(async (oct) => {
    const A = window.AppBridge, D = A.data;
    D.ecoles = D.ecoles || [];
    if (!D.ecoles.find(e => e.code === 'POBE-INTEROP01')) D.ecoles.push({ id: 'e-interop', nom: 'EPP Interop', code: 'POBE-INTEROP01', posteLocal: true, zone: '' });
    await A.saveData();
    const out = {};
    try { out.import = await window.SyncCS.client.importerOctets(new Uint8Array(oct), 'fichier'); delete out.import.emetteur; } catch (e) { out.erreurImport = e.message; }
    const P = await window.PvsCS.adaptateur().charger();
    out.cepSalles = (P.cepSalles || []).map(x => ({ centre: x.centre, saison: x.saison, offG: x.offG, offF: x.offF, offH: x.offH, libG: x.libG, salles: x.salles, entite: x.entite }));
    out.structures = (P.structures || []).map(x => ({ nom: x.nom, type: x.type, rattachement: x.rattachement, active: x.active }));
    out.retours = (P.retours || []).map(x => ({ objet: x.objet, cle: x.cle, destinataire: x.destinataire, statut: x.statut, decidePar: x.decidePar, motif: x.motif }));
    // données de l'école qui montent
    const an = '2026-2027', id = (p) => p + Math.random().toString(36).slice(2, 8);
    P.rentree = (P.rentree || []).concat([{ id: id('r'), niveau: 'ECOLE', entite: 'e-interop', annee: an, effG: 31, effF: 29, classes: 3, classesSimples: 1, classesJumelees: 2, classesMultigrades: 0,
      classesAutorisees: 4, ensPoste: 3, salles: 3, latitude: 7.3637, longitude: 2.6086, statut: 'TRANSMISE', dateTransmission: '2026-11-02' }]);
    P.courrier = (P.courrier || []).concat([{ id: id('c'), niveau: 'ECOLE', entite: 'e-interop', annee: an, type: 'Rapport', reference: 'R-JS-1', date: '2026-11-02', objet: 'Rapport de rentrée (JS)', destNiveau: 'CS', texte: 'Texte', statut: 'Envoyé', dateEnvoi: '2026-11-02' }]);
    P.signaletique = (P.signaletique || []).concat([{ id: id('s'), niveau: 'ECOLE', entite: 'e-interop', latitude: 7.3637, longitude: 2.6086, statutJuridique: 'Public', numeroAgrement: 'AG-JS-7', salles: 3, latrines: 4, pointEau: 'Oui', electricite: 'Non' }]);
    await window.PvsCS.adaptateur().enregistrer(P);
    // paquet d'école Mon école (POBE-PAQUET-ECOLE) joint au paquet montant : données fictives de test
    const E = 'e-interop', ec = D.ecoles.find(e => e.id === E); Object.assign(ec, { type: 'EPP', classes_autorisees: 4, annee_creation: '1998', zone_ped: 'Zone test' });
    const ajoute = (c, o) => { D[c] = D[c] || []; D[c].push(Object.assign({ id: id(c[0]), ecoleId: E, _interop: true }, o)); };
    ajoute('effectifs', { annee: an, c_ci_G: 12, c_ci_F: 10, c_cp_G: 9, c_cp_F: 11, c_cm2_G: 7, c_cm2_F: 6, totalG: 28, totalF: 27, total: 55, handicapes: 2, redoublants: 3, sansActe: 1 });
    ajoute('personnel', { nom: 'TESTEUR Alpha', sexe: 'M', matricule: 'T-0001', dateNaissance: '1985-04-01', categorie: 'Enseignant', fonction: 'Directeur', statut: 'FE', grade: 'A1-4', diplomePro: 'CAP', note2025: '15.5', lieuNaiss: 'Ville fictive', cours: 'CM2' });
    ajoute('personnel', { nom: 'ESSAI Beta', sexe: 'F', matricule: 'T-0002', dateNaissance: '1990-09-12', categorie: 'Enseignant', fonction: 'Adjoint', statut: 'ACDPE', grade: 'B1-2', cours: 'CI' });
    ajoute('visites', { type: 'VISITE_CLASSE', date: '2026-10-20', enseignantNom: 'ESSAI Beta', cours: 'CI', matiere: 'Français', sequence: 'Lecture', note: '14', presents: '20' });
    ajoute('cep', { nom: 'FICTIF', prenoms: 'Gamma', sexe: 'F', dateNaiss: '2014-02-02', lieuNaiss: 'Ville fictive', session: '2027', pere: 'Parent fictif' });
    ajoute('infrastructures', { typeLocal: 'Salle de classe', etat: 'Bon', superficie: '56' });
    ajoute('infrastructures', { typeLocal: 'Salle de classe', etat: 'Acceptable' });
    ajoute('fiches', { annee: an, nb_latrines: '4', point_eau: 'Forage' });
    ajoute('mobilier', { designation: 'Table-banc', quantite: '30' });
    await A.saveData();
    const pq = await window.SyncCS.client.preparer({ sens: 'montant', complet: true });
    out.montantTypes = [...new Set(pq.objets.map(o => o.type))];
    out.transmission = pq.transmission ? { format: pq.transmission.format, collections: Object.keys(pq.transmission.collections || {}).sort() } : null;
    out.paquet = JSON.stringify(pq);
    return out;
  }, oct);
  fs.writeFileSync(fMont, r.paquet); delete r.paquet;
  r.erreursPage = erreurs.slice(0, 5);
  console.log(JSON.stringify(r, null, 1));
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
