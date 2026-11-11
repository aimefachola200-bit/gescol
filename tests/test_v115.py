# -*- coding: utf-8 -*-
"""Tests de la version 1.15 : documents vérifiables (code + QR + signatures) pour le registre d'appel, les relevés
mensuels, le tableau d'affichage, les statistiques (présences, évaluations), les résultats d'évaluation, la synthèse et le
bilan annuel ; import du modèle de notes EducMaster (aller-retour). Lancer : python3 -m unittest tests.test_v115"""
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXE = "GESCOL" if os.path.exists(os.path.join(RACINE, "GESCOL_PUBLIC.md")) else "SCOLARIS"
SCRIPT = r'''
import html, io, json, os, sys, tempfile
P=os.environ["PREFIXE_SCRIPT"]; os.environ[P+"_EDITION"]=sys.argv[1]; os.environ[P+"_DATA"]=tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import config, openpyxl, pdfplumber
from app import app, q, ex
from werkzeug.security import generate_password_hash
app.config["TESTING"]=True
A=config.ANNEE_ACTIVE
with app.app_context():
    ex("UPDATE utilisateurs SET mdp_hash=?, doit_changer_mdp=0 WHERE identifiant='admin'", (generate_password_hash("admin123"),))
    eco=q("SELECT id FROM ecoles ORDER BY id LIMIT 1",un=True)
    eco=eco["id"] if eco else 1
    cl=ex("INSERT INTO classes (nom, niveau, ecole_id, titulaire_nom) VALUES ('CM2 A','CM2',?, 'AGBO Pierre')",(eco,))
    def eleve(n,p,s,em):
        return ex("""INSERT INTO eleves (nom, prenoms, sexe, date_naissance, classe_id, statut, matricule, matricule_educmaster,
                     date_inscription, annee) VALUES (?,?,?,'2014-01-01',?,'inscrit',?,?,'2026-09-15',?)""",(n,p,s,cl,"M-"+em,em,A))
    e1=eleve("DOSSOU","Grâce","F","EM0001"); e2=eleve("HOUNGBO","Marc","M","EM0002"); e3=eleve("AKPO","Jean","M","")
    mats={m["code"]:m["id"] for m in q("SELECT id, code FROM matieres WHERE cycle='primaire'")}
    ev=ex("""INSERT INTO evaluations (classe_id, annee, type, numero, libelle, date, matieres, cree_le)
             VALUES (?,?,'formative',1,'Formative 1','2026-10-20',?,'2026-10-20')""",(cl,A,json.dumps([mats["DIC"],mats["MATH"],mats["EPS"]])))
    for eid,code,v in ((e1,"DIC",14),(e1,"MATH",12.5),(e2,"DIC",9),(e2,"EPS",16),(e3,"MATH",11)):
        ex("INSERT INTO notes (eleve_id, matiere_id, periode, annee, valeur) VALUES (?,?,?,?,?)",(eid,mats[code],"Formative 1",A,v))
    j="2026-10-12"
    ex("INSERT INTO appels (classe_id, date, fait_par, fait_le) VALUES (?,?,1,?)",(cl,j,j))
    ex("INSERT INTO presences (eleve_id, date, statut, justifie, saisi_par, cree_le) VALUES (?,?,'absent',1,1,?)",(e1,j,j))
    ex("INSERT INTO presences (eleve_id, date, statut, justifie, saisi_par, cree_le) VALUES (?,?,'retard',0,1,?)",(e2,j,j))
c=app.test_client()
def ok(r,code=200):
    assert r.status_code==code,(r.request.path,r.status_code,r.data[-600:]); return r
ok(c.post("/login",data={"identifiant":"admin","mdp":"admin123"}),302)
def verif_pdf(r, type_doc, mot):
    """PDF avec « Document vérifiable · code X » ; X enregistré avec le bon type ; /verifier/X l'authentifie."""
    ok(r); assert r.data[:4]==b"%PDF",(r.request.path, r.data[:80])
    with pdfplumber.open(io.BytesIO(r.data)) as pdf:
        texte="\n".join((p.extract_text() or "") for p in pdf.pages)
    assert "Document vérifiable" in texte,(r.request.path, texte[-400:])
    import re
    code=re.search(r"code ([0-9A-F]{10})",texte).group(1)
    with app.app_context():
        d=q("SELECT * FROM documents WHERE code=?",(code,),un=True)
    assert d and d["type"]==type_doc,(r.request.path,dict(d) if d else None)
    t=html.unescape(ok(c.get("/verifier/"+code)).data.decode())
    assert "Document authentique" in t and mot in t and "Émis et signé par" in t,(code,t[-900:])
    return code
mois="2026-10"
k1=verif_pdf(c.get(f"/registre/pdf?classe={cl}&mois={mois}"),"registre","Registre")
k2=verif_pdf(c.get(f"/registre/pdf?classe={cl}&mois={mois}"),"registre","Registre")
assert k1==k2, "même contenu = même code"
verif_pdf(c.post(f"/releves/pdf?classe={cl}&annee={A}",data={}),"releve","relevés")
verif_pdf(c.get(f"/affichage/pdf?classe={cl}"),"affichage","affichage")
verif_pdf(c.get(f"/evaluations/{ev}/rapport.pdf"),"evaluation","Résultats")
verif_pdf(c.get(f"/statistiques-evaluation/pdf?classe={cl}&ev={ev}"),"statistiques","Statistiques")
verif_pdf(c.get(f"/appel/statistiques/pdf?classe={cl}"),"statistiques","présence")
verif_pdf(c.get("/appel/statistiques/pdf"),"statistiques","présence")
t=html.unescape(ok(c.get(f"/appel/statistiques?classe={cl}")).data.decode()); assert "Évolution mensuelle" in t and "appel/statistiques/pdf" in t
verif_pdf(c.get(f"/bilan-annuel/pdf?classe={cl}&ev={ev}"),"bilan","Bilan")
verif_pdf(c.get(f"/synthese/pdf?type=formative&numero=1&classe={cl}"),"synthese","Synthèse")
# ---- EducMaster : modèle de notes rempli -> import (aller-retour)
r=ok(c.get(f"/educmaster/modeles/notes-primaire/{cl}.xlsx")); assert r.data[:2]==b"PK"
wb=openpyxl.load_workbook(io.BytesIO(r.data))
with app.app_context():
    avant={(n["eleve_id"],n["matiere_id"]):n["valeur"] for n in q("SELECT * FROM notes WHERE periode='Formative 1'")}
    ex("DELETE FROM notes")
ws=wb["Évaluation sommative 1"]
ws.cell(row=3,column=4,value=17)            # 1re ligne (AKPO, sans matricule) : dictée
ws.cell(row=4,column=4,value="25")          # note hors barème : refusée
ws.cell(row=40,column=1,value="EM9999"); ws.cell(row=40,column=2,value="INCONNU"); ws.cell(row=40,column=4,value=8)
buf=io.BytesIO(); wb.save(buf)
def importer(simuler=False, creer=True):
    d={"fichier":(io.BytesIO(buf.getvalue()),"notes.xlsx")}
    if simuler: d["simuler"]="1"
    if creer: d["creer"]="1"
    return ok(c.post(f"/educmaster/modeles/notes-primaire/{cl}/importer",data=d,content_type="multipart/form-data"),302)
importer(simuler=True)
with app.app_context(): assert q("SELECT COUNT(*) n FROM notes",un=True)["n"]==0, "simulation : rien d'écrit"
importer()
with app.app_context():
    apres={(n["eleve_id"],n["matiere_id"]):n["valeur"] for n in q("SELECT * FROM notes WHERE periode='Formative 1'")}
    assert apres==avant,(apres,avant)
    s1=q("SELECT * FROM evaluations WHERE classe_id=? AND type='sommative' AND numero=1",(cl,),un=True)
    assert s1, "évaluation sommative 1 créée"
    n=q("SELECT * FROM notes WHERE periode=? AND eleve_id=?",(s1["libelle"],e3),un=True); assert n and n["valeur"]==17
    assert not q("SELECT 1 FROM notes WHERE periode=? AND valeur=25",(s1["libelle"],),un=True)
t=html.unescape(ok(c.get("/educmaster")).data.decode())
assert "Import du modèle de notes" in t and "INCONNU" in t and "25" in t, t[-1500:]
importer()   # deuxième import : inchangé
t=html.unescape(ok(c.get("/educmaster")).data.decode()); assert "inchangé" in t
print("OK")
'''


def lancer(edition):
    env = dict(os.environ, PREFIXE_SCRIPT=PREFIXE)
    r = subprocess.run([sys.executable, "-c", SCRIPT, edition], cwd=RACINE, env=env, capture_output=True, text=True,
                       timeout=600)
    return r.returncode, r.stdout + r.stderr


class TestDocumentsVerifiables(unittest.TestCase):
    def test_privee(self):
        code, out = lancer("privee")
        self.assertEqual(code, 0, out[-3000:])
        self.assertIn("OK", out)

    def test_publique(self):
        code, out = lancer("publique")
        self.assertEqual(code, 0, out[-3000:])
        self.assertIn("OK", out)


if __name__ == "__main__":
    unittest.main()
