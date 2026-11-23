// maj-correctif-291.js : 2.9.1 - mise à jour automatique plus robuste (3 reprises, téléchargement repris où il s'est arrêté)
// usage (dans le dossier du dépôt gescol OU scolaris) :  node maj-correctif-291.js
const fs = require('fs');
const rd = f => fs.readFileSync(f, 'utf8').replace(/\r\n/g, '\n');
if (!fs.existsSync('maj_auto.py') || !fs.existsSync('config.py')) { console.error('ARRÊT : à lancer dans le dossier du dépôt (celui qui contient config.py).'); process.exit(1); }
if (rd('config.py').includes('VERSION = "2.9.1"')) { console.log('Déjà appliqué.'); process.exit(0); }
if (!rd('config.py').includes('VERSION = "2.9.0"')) { console.error('ARRÊT : le dépôt doit être en version 2.9.0 (git fetch origin && git reset --hard origin/main).'); process.exit(1); }
const NOUVEAU = `def _telecharger(zf, sha):
    """Télécharge MAJ-CODE.zip vers zf : jusqu'à 4 essais, reprise là où le téléchargement s'est arrêté,
    départ à zéro si l'empreinte SHA-256 ne correspond pas (fichier abîmé en route)."""
    derniere = ValueError("téléchargement impossible")
    for essai in range(4):
        if essai:
            time.sleep(3 * essai)
        try:
            n0 = os.path.getsize(zf) if os.path.isfile(zf) else 0
            rep = _http(_url("MAJ-CODE.zip"), 60, {"Range": "bytes=%d-" % n0}) if n0 else _http(_url("MAJ-CODE.zip"), 60)
            with rep:
                if n0 and getattr(rep, "status", 200) != 206:
                    n0 = 0                                              # le serveur n'a pas accepté la reprise
                n = n0
                with open(zf, "ab" if n0 else "wb") as f:
                    while True:
                        b = rep.read(65536)
                        if not b:
                            break
                        n += len(b)
                        if n > TAILLE_MAX:
                            raise ValueError("fichier trop gros")
                        f.write(b)
            h = hashlib.sha256()
            with open(zf, "rb") as f:
                for b in iter(lambda: f.read(65536), b""):
                    h.update(b)
            if h.hexdigest() == sha:
                return
            os.remove(zf)                                               # abîmé : on recommence de zéro
            derniere = ValueError("empreinte différente : téléchargement rejeté (après " + str(essai + 1) + " essai(s))")
        except urllib.error.HTTPError as e:
            if e.code == 416 and os.path.isfile(zf):
                os.remove(zf)
            derniere = e
        except (OSError, http.client.HTTPException) as e:              # coupure réseau : on garde le début et on reprend
            derniere = e
    raise derniere


def verifier(`;
const BLOC = `            h, n = hashlib.sha256(), 0
            with _http(_url("MAJ-CODE.zip"), 60) as rep, open(zf, "wb") as f:
                while True:
                    b = rep.read(65536)
                    if not b:
                        break
                    n += len(b)
                    if n > TAILLE_MAX:
                        raise ValueError("fichier trop gros")
                    h.update(b)
                    f.write(b)
            if h.hexdigest() != str(info.get("sha256", "")).lower():
                raise ValueError("empreinte différente : téléchargement rejeté")
`;
const H = [
  ['maj_auto.py', 'import hashlib\n', 'import hashlib\nimport http.client\n'],
  ['maj_auto.py', 'import urllib.request\n', 'import urllib.error\nimport urllib.request\n'],
  ['maj_auto.py', 'def _http(url, tmax=20):\n', 'def _http(url, tmax=20, plus=None):\n'],
  ['maj_auto.py', '    return urllib.request.urlopen(req, timeout=tmax)\n', '    for k, v in (plus or {}).items():\n        req.add_header(k, v)\n    return urllib.request.urlopen(req, timeout=tmax)\n'],
  ['maj_auto.py', 'def verifier(', NOUVEAU],
  ['maj_auto.py', BLOC, '            _telecharger(zf, str(info.get("sha256", "")).lower())\n'],
];
const R = [['config.py', /\nVERSION = "2\.9\.0"/, '\nVERSION = "2.9.1"'], ['amorcage.py', /\nBASE_VERSION = "2\.9\.0"/, '\nBASE_VERSION = "2.9.1"'],
  ['LISEZMOI.md', /\nVersion 2\.9\.0\. /, '\nVersion 2.9.1. '], ['.github/workflows/fabriquer.yml', /\n  VERSION: "2\.9\.0"\n/, '\n  VERSION: "2.9.1"\n']];
const iss = fs.readdirSync('packaging/windows').filter(x => x.endsWith('.iss')).map(x => 'packaging/windows/' + x);
for (const f of iss) { R.push([f, /\/DVersion=2\.9\.0 /, '/DVersion=2.9.1 ']); R.push([f, /#define Version "2\.9\.0"/, '#define Version "2.9.1"']); }
const txt = {}; let erreurs = 0;
for (const [f, a, b] of H) { txt[f] = txt[f] || rd(f); const n = txt[f].split(a).length - 1; if (n !== 1) { console.error('Ancre introuvable ou multiple (' + n + ') dans ' + f + ' : ' + a.slice(0, 60)); erreurs++; } else txt[f] = txt[f].replace(a, () => b); }
for (const [f, re, b] of R) { txt[f] = txt[f] || rd(f); if (!re.test(txt[f])) { console.error('Version 2.9.0 introuvable dans ' + f); erreurs++; } else txt[f] = txt[f].replace(re, b); }
if (erreurs) { console.error("ARRÊT : rien n'a été modifié."); process.exit(1); }
for (const f of Object.keys(txt)) fs.writeFileSync(f, txt[f]);
console.log('OK : correctif 2.9.1 appliqué (' + Object.keys(txt).length + ' fichiers)');