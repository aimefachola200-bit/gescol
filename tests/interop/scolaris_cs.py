"""Côté SCOLARIS (édition cs) : export d'un paquet descendant réel vers « EPP Interop » / import d'un paquet montant JS."""
import gzip, json, os, subprocess, sys
mode, D, fichier = sys.argv[1], sys.argv[2], sys.argv[3]
P = os.environ.get("PREFIXE", "SCOLARIS")
os.environ.update({P + "_EDITION": "cs", P + "_DATA": D})
if mode == "export":
    subprocess.run([sys.executable, "demo_juridiction.py"], check=True, stdout=subprocess.DEVNULL)
sys.path.insert(0, os.getcwd())
from app import app, ex, q
import config, flask, registres, sync_crypto as SC
app.config["TESTING"] = True
H = registres._H
CODE, NOM = "POBE-INTEROP01", "EPP Interop"  # école fictive de test
c = app.test_client()
assert c.post("/login", data={"identifiant": "responsable", "mdp": "demo1234"}).status_code == 302
if mode == "export":
    with app.app_context():
        cs = q("SELECT id FROM jur_cs LIMIT 1", un=True)
        rid = ex("INSERT INTO jur_ecoles (code, nom, type, secteur, cs_id, actif, jeton) VALUES (?,?,?,?,?,1,?)", (CODE, NOM, "EP", "public", cs["id"] if cs else None, "JETON-INTEROP-1"))
    assert c.post("/examens/cep2027/pobe").status_code == 302
    with app.app_context():
        ex("UPDATE reg_examens_salles SET offG=150, offF=140, offH=1, libG=3, libF=2, salles=8, observations='' WHERE centre='POBE-CENTRE'")
        ex("UPDATE reg_examens_salles SET offG=60, offF=55, salles=5 WHERE centre='POBE-NORD'")
        fid = ex("INSERT INTO reg_territoire_rentree (portee, annee, niveau, entite, effG, effF, effT, statut, dateTransmission) VALUES (7,?,?,?,?,?,?,?,?)",
                 (config.ANNEE_ACTIVE, "ECOLE", NOM, 10, 12, 22, "TRANSMISE", "2026-11-01"))
    assert c.post("/territoire/structures/arbre").status_code == 302
    c.post(f"/territoire/rentree/{fid}/decider", data={"statut": "Renvoyée", "motif": "Compléter les salles"})
    with app.test_request_context():
        flask.g.user = q("SELECT * FROM utilisateurs WHERE identifiant='responsable'", un=True)
        p = H.sync_paquet_descendant("ecole", rid)
    types = {}
    for o in p["objets"]:
        types[o["type"]] = types.get(o["type"], 0) + 1
    open(fichier, "wb").write(gzip.compress(json.dumps(p, ensure_ascii=False).encode()))
    print(json.dumps({"types": types, "signature_ok": SC.verifier(p)}))
else:
    p = json.loads(gzip.decompress(open(fichier, "rb").read()) if open(fichier, "rb").read(2) == b"\x1f\x8b" else open(fichier, encoding="utf-8").read())
    out = {"signature_ok": SC.verifier(p), "types": sorted({o["type"] for o in p["objets"]})}
    with app.test_request_context():
        flask.g.user = q("SELECT * FROM utilisateurs WHERE identifiant='responsable'", un=True)
        res = H.sync_hub_recevoir(p)
    out["message"] = res["message"]
    with app.app_context():
        out["rentree"] = [dict(x) for x in q("SELECT entite, effG, effF, statut, dateTransmission FROM reg_territoire_rentree WHERE entite=?", (NOM,))]
        out["courrier"] = [dict(x) for x in q("SELECT entite, type, reference, objet, destNiveau, statut FROM reg_communication_courrier WHERE portee<>0")]
        out["signaletique"] = [dict(x) for x in q("SELECT entite, latitude, longitude, numeroAgrement FROM reg_territoire_signaletique")]
        e = q("SELECT id FROM jur_ecoles WHERE code=?", (CODE,), un=True)
        out["sections"] = {r["section"]: json.loads(r["donnees"]) for r in q("SELECT section, donnees FROM jur_sections WHERE ecole_id=?", (e["id"],))}
    h = c.get("/territoire/courrier").data.decode()
    out["courrier_page"] = "Rapport de rentrée (JS)" in h
    h = c.get("/territoire/rentree/suivi").data.decode()
    out["suivi_page"] = NOM in h
    print(json.dumps(out, ensure_ascii=False, default=str))
