# -*- coding: utf-8 -*-
"""Bréviaires originaux de français (CE2 à la 3e), d'anglais, d'allemand et d'espagnol (4e à la terminale) : cahier de l'élève et cahier de l'enseignant (PDF).
Exercices rédigés pour l'application ; aucun exercice des recueils d'autres auteurs n'est repris."""
import io

L = "Réponse libre (critères : pertinence, correction, cohérence)."
# DATA[langue][niveau] = (situations, evaluation) ; situations = [(titre, consigne, [(énoncé, réponse)])] ; evaluation = [(énoncé, réponse)]
DATA = {
"Anglais": {
 "4e": ([("Le prétérit (past simple)", "Write the verbs in the past simple.",
          [("Yesterday I (go) to the market.", "went"), ("She (watch) TV last night.", "watched"), ("They (not / play) football on Sunday.", "did not play"),
           ("(you / see) Kofi last week?", "Did you see"), ("We (buy) rice two days ago.", "bought")]),
         ("Comparatifs et superlatifs", "Complete with the correct form of the adjective.",
          [("Cotonou is (big) ___ than Porto-Novo.", "bigger"), ("This book is (interesting) ___ than that one.", "more interesting"),
           ("Kilimanjaro is the (high) ___ mountain in Africa.", "highest"), ("Awa is the (good) ___ student in the class.", "best"),
           ("English is (easy) ___ than Mathematics for me.", "easier")])],
        [("Last year, my family (travel) to Ouidah.", "travelled"), ("A bus is (fast) ___ than a bicycle.", "faster"),
         ("Answer: Where did you spend your last holidays?", "Réponse libre, par exemple : I spent my holidays in Abomey."), ("Write three sentences about your best friend.", L)]),
 "3e": ([("Le present perfect", "Complete with the present perfect or for / since.",
          [("I (live) here since 2015.", "have lived"), ("She (not / see) him for two years.", "has not seen"), ("They (already / finish) the work.", "have already finished"),
           ("He has worked here ___ 2019. (for / since)", "since"), ("We have waited ___ three hours. (for / since)", "for")]),
         ("Condition (type 1) et passif", "Complete or transform.",
          [("If it rains, we (stay) at home.", "will stay"), ("If you (study), you will pass.", "study"), ("If she (come), I will tell her.", "comes"),
           ("The teacher corrects the exercises. (passive)", "The exercises are corrected by the teacher."), ("They built this school in 1990. (passive)", "This school was built in 1990.")])],
        [("Rice (grow) in Benin.", "is grown"), ("If I (have) money, I will buy a car.", "have"), ("They (live) here for ten years.", "have lived"),
         ("Write four sentences about the protection of the environment.", L)]),
 "2nde": ([("Le discours rapporté", "Report the sentences.",
           [("\"I am tired,\" he said.", "He said (that) he was tired."), ("\"We will come tomorrow,\" they said.", "They said they would come the next day."),
            ("\"I live in Parakou,\" she said.", "She said she lived in Parakou."), ("\"Where do you live?\" he asked me.", "He asked me where I lived."),
            ("\"Open the door,\" the teacher said.", "The teacher told us to open the door.")]),
          ("Les relatives", "Complete with who, which, whose or where.",
           [("The man ___ lives next door is a doctor.", "who"), ("The book ___ I bought is interesting.", "which"), ("The girl ___ bag was stolen cried.", "whose"),
            ("Cotonou is the city ___ I was born.", "where"), ("This is the teacher ___ taught me English.", "who")])],
         [("\"I will call you,\" she said. (report)", "She said she would call me."), ("The boy ___ father is a farmer is my friend.", "whose"),
          ("The film ___ we saw yesterday was boring.", "which (ou that)"), ("Write a short text (five lines) about your school.", L)]),
 "1ère": ([("Le past perfect", "Put the verbs in the past perfect.",
           [("When I arrived, the film (already / start).", "had already started"), ("She told me she (never / visit) Lagos.", "had never visited"),
            ("After he (eat), he went out.", "had eaten"), ("They (not / finish) when we came.", "had not finished"), ("I was late because the bus (leave).", "had left")]),
          ("Conditionnels (types 2 et 3) et souhaits", "Complete with the right form.",
           [("If I (be) rich, I would travel.", "were"), ("If she had studied, she (pass).", "would have passed"), ("I wish I (know) the answer.", "knew"),
            ("If we (leave) earlier, we wouldn't have missed the train.", "had left"), ("If he (have) time, he would help us.", "had")])],
         [("When he came, we (already / eat).", "had already eaten"), ("If I (be) you, I would study harder.", "were"), ("I wish I (can) speak German.", "could"),
          ("Write five lines: If I were president of my country...", L)]),
 "Tle": ([("Les modaux du passé", "Complete with a modal perfect (should have, must have, can't have, may have, ought to have).",
          [("You failed. You (should / study) harder.", "should have studied"), ("He is not here. He (must / forget) the date.", "must have forgotten"),
           ("The door was locked. The thief (can't / enter) by it.", "can't have entered"), ("She (may / miss) the bus.", "may have missed"), ("They (ought to / tell) us.", "ought to have told")]),
         ("Connecteurs logiques", "Choose although, despite, however or because of.",
          [("___ the rain, we played.", "Despite"), ("___ he was ill, he went to school.", "Although"), ("He was ill; ___, he went to school.", "however"),
           ("The match was cancelled ___ the storm.", "because of"), ("She passed ___ she had not worked hard.", "although")])],
        [("He is late. He (must / miss) the train.", "must have missed"), ("___ the traffic, she arrived on time.", "Despite"),
         ("Rewrite: Although it was cold, we went out. (Despite...)", "Despite the cold, we went out."), ("Write an argumentative paragraph on social media and young people.", L)]),
},
"Allemand": {
 "4e": ([("Articles au nominatif", "Écris der, die ou das.",
          [("___ Tisch", "Der"), ("___ Schule", "Die"), ("___ Heft", "Das"), ("___ Lehrer", "Der"), ("___ Mädchen", "Das")]),
         ("Le présent des verbes réguliers", "Conjugue le verbe entre parenthèses.",
          [("Ich (spielen) Fußball.", "spiele"), ("Du (wohnen) in Cotonou.", "wohnst"), ("Er (lernen) Deutsch.", "lernt"), ("Wir (gehen) zur Schule.", "gehen"), ("Ihr (kommen) heute.", "kommt")])],
        [("Ich ___ dreizehn Jahre alt. (sein)", "bin"), ("Wir ___ einen Hund. (haben)", "haben"), ("Réponds : Wie alt bist du ?", "Réponse libre, par exemple : Ich bin zwölf Jahre alt."),
         ("Présente ta famille en quatre phrases.", L)]),
 "3e": ([("Le Perfekt", "Mets les phrases au Perfekt.",
          [("Ich spiele Fußball.", "Ich habe Fußball gespielt."), ("Wir gehen nach Hause.", "Wir sind nach Hause gegangen."), ("Er lernt Deutsch.", "Er hat Deutsch gelernt."),
           ("Sie kaufen Brot.", "Sie haben Brot gekauft."), ("Du isst einen Apfel.", "Du hast einen Apfel gegessen.")]),
         ("Les verbes de modalité", "Complète avec la forme correcte.",
          [("Ich ___ gut schwimmen. (können)", "kann"), ("Du ___ lernen. (müssen)", "musst"), ("Er ___ ins Kino gehen. (wollen)", "will"), ("Wir ___ helfen. (können)", "können"),
           ("Ihr ___ pünktlich sein. (müssen)", "müsst")])],
        [("Gestern ___ ich Fußball ___. (spielen, Perfekt)", "habe ... gespielt"), ("Wir ___ Hausaufgaben machen. (müssen)", "müssen"),
         ("Er geht nach Hause. (Perfekt)", "Er ist nach Hause gegangen."), ("Écris cinq phrases : ce que tu veux faire plus tard.", L)]),
 "2nde": ([("Accusatif et datif", "Complète avec l'article correct.",
           [("Ich sehe ___ Mann. (der)", "den"), ("Er gibt ___ Frau ein Buch. (die)", "der"), ("Wir helfen ___ Kind. (das)", "dem"), ("Ich kaufe ___ Heft. (das)", "das"),
            ("Sie schenkt ___ Bruder ein Buch. (der)", "dem")]),
          ("Le prétérit de sein et haben", "Complète avec war / hatte et leurs formes.",
           [("Gestern ___ ich krank. (sein)", "war"), ("Er ___ keine Zeit. (haben)", "hatte"), ("Wir ___ in Berlin. (sein)", "waren"), ("Du ___ Hunger. (haben)", "hattest"),
            ("Sie ___ müde. (sein, pluriel)", "waren")])],
         [("Ich sehe ___ Lehrer. (der)", "den"), ("Er hilft ___ Freundin. (die)", "der"), ("Als Kind ___ ich viele Freunde. (haben)", "hatte"), ("Décris ta ville en cinq phrases.", L)]),
 "1ère": ([("Propositions subordonnées (weil, dass)", "Relie les deux phrases avec la conjonction indiquée.",
           [("Ich bleibe zu Hause. Ich bin krank. (weil)", "Ich bleibe zu Hause, weil ich krank bin."), ("Er sagt. Er kommt morgen. (dass)", "Er sagt, dass er morgen kommt."),
            ("Ich weiß. Sie hat keine Zeit. (dass)", "Ich weiß, dass sie keine Zeit hat."), ("Wir lernen. Wir wollen die Prüfung bestehen. (weil)", "Wir lernen, weil wir die Prüfung bestehen wollen."),
            ("Sie hofft. Er ruft an. (dass)", "Sie hofft, dass er anruft.")]),
          ("Le futur (werden + infinitif)", "Mets les phrases au futur.",
           [("Ich lerne.", "Ich werde lernen."), ("Du gehst.", "Du wirst gehen."), ("Er kommt.", "Er wird kommen."), ("Wir arbeiten.", "Wir werden arbeiten."), ("Ihr reist.", "Ihr werdet reisen.")])],
         [("Ich lerne Deutsch. Es ist interessant. (weil)", "Ich lerne Deutsch, weil es interessant ist."), ("Er hofft. Sie kommt. (dass)", "Er hofft, dass sie kommt."),
          ("Wir fahren nach Berlin. (Futur)", "Wir werden nach Berlin fahren."), ("Écris cinq phrases sur tes projets d'avenir.", L)]),
 "Tle": ([("Le passif", "Mets les phrases au passif.",
           [("Der Lehrer korrigiert die Hefte.", "Die Hefte werden vom Lehrer korrigiert."), ("Man baut ein Haus.", "Ein Haus wird gebaut."),
            ("Die Schüler lesen den Text.", "Der Text wird von den Schülern gelesen."), ("Man spricht Deutsch in Österreich.", "In Österreich wird Deutsch gesprochen."),
            ("Der Koch kocht das Essen.", "Das Essen wird vom Koch gekocht.")]),
          ("Le Konjunktiv II", "Complète avec la forme correcte.",
           [("Wenn ich reich ___, würde ich reisen. (sein)", "wäre"), ("Wenn ich Zeit ___, würde ich helfen. (haben)", "hätte"), ("Ich ___ gern ein Eis. (mögen)", "möchte"),
            ("Wenn ich du ___, würde ich lernen. (sein)", "wäre"), ("Wenn er mehr ___, würde er bestehen. (lernen)", "lernte (ou lernen würde)")])],
         [("Die Mutter kocht das Essen. (Passiv)", "Das Essen wird von der Mutter gekocht."), ("Wenn ich Geld ___, würde ich ein Haus kaufen. (haben)", "hätte"),
          ("Ich wäre gern ... Termine la phrase.", "Réponse libre, par exemple : Ich wäre gern Arzt."), ("Rédige un texte de huit lignes sur l'avenir de la jeunesse africaine.", L)]),
},
"Espagnol": {
 "4e": ([("Ser et estar", "Complète avec ser ou estar.",
          [("Mi hermano ___ alto.", "es"), ("Nosotros ___ en la escuela.", "estamos"), ("Yo ___ de Benín.", "soy"), ("Tú ___ cansado.", "estás"), ("Ellos ___ profesores.", "son")]),
         ("Le présent des verbes réguliers", "Conjugue au présent.",
          [("Yo (hablar) español.", "hablo"), ("Tú (comer) arroz.", "comes"), ("Ella (vivir) en Cotonou.", "vive"), ("Nosotros (estudiar) mucho.", "estudiamos"), ("Ellos (escribir) cartas.", "escriben")])],
        [("Mi madre ___ comerciante. (ser)", "es"), ("Hoy yo ___ contento. (estar)", "estoy"), ("Présente-toi en quatre phrases (Me llamo...).", L), ("Décris ta maison en cinq phrases.", L)]),
 "3e": ([("Le prétérit (pretérito indefinido)", "Conjugue au prétérit.",
          [("Ayer yo (comer) arroz.", "comí"), ("Tú (hablar) con él.", "hablaste"), ("Ella (vivir) en Lomé.", "vivió"), ("Nosotros (ir) al mercado.", "fuimos"), ("Ellos (escribir) una carta.", "escribieron")]),
         ("Le futur proche (ir a + infinitif)", "Complète avec la forme de ir.",
          [("Mañana yo ___ a estudiar.", "voy"), ("Tú ___ a viajar.", "vas"), ("Nosotros ___ a comer.", "vamos"), ("Ellos ___ a jugar.", "van"), ("Ella ___ a cantar.", "va")])],
        [("Ayer nosotros (ver) una película.", "vimos"), ("El año pasado ella (viajar) a Accra.", "viajó"), ("Mañana yo ___ a visitar a mi abuela.", "voy"), ("Écris cinq phrases sur ton week-end.", L)]),
 "2nde": ([("L'imparfait", "Conjugue à l'imparfait.",
           [("De niño yo (jugar) mucho.", "jugaba"), ("Nosotros (vivir) en el pueblo.", "vivíamos"), ("Ella (ser) alegre.", "era"), ("Tú (comer) siempre aquí.", "comías"), ("Ellos (ir) al río.", "iban")]),
          ("La comparaison", "Complète la comparaison.",
           [("Mi casa es ___ grande que la tuya. (supériorité)", "más"), ("Esta película es ___ que la otra. (bueno)", "mejor"), ("Él es tan alto ___ su padre.", "como"),
            ("Hoy hace ___ calor que ayer. (supériorité)", "más"), ("Mi hermano es ___ joven que yo. (infériorité)", "menos")])],
         [("Cuando yo era niño, (jugar) en la calle.", "jugaba"), ("Mi casa es ___ pequeña que la tuya. (infériorité)", "menos"),
          ("Mientras yo (leer), mi madre (llegar).", "leía, llegó"), ("Raconte un souvenir d'enfance en six phrases.", L)]),
 "1ère": ([("Le présent du subjonctif", "Conjugue au subjonctif présent.",
           [("Quiero que tú (venir).", "vengas"), ("Es importante que nosotros (estudiar).", "estudiemos"), ("Espero que ella (comer) bien.", "coma"), ("Dudo que él (saber) la respuesta.", "sepa"),
            ("Ojalá que (llover) mañana.", "llueva")]),
          ("Le conditionnel", "Conjugue au conditionnel.",
           [("Yo (comprar) una casa.", "compraría"), ("Tú (viajar) mucho.", "viajarías"), ("Ella (hablar) con él.", "hablaría"), ("Nosotros (vivir) allí.", "viviríamos"), ("Ellos (ser) felices.", "serían")])],
         [("Quiero que ellos (venir).", "vengan"), ("Yo (comprar) un coche.", "compraría"), ("Si tuviera tiempo, (ir) a verte.", "iría"), ("Rédige huit lignes : Si fuera presidente...", L)]),
 "Tle": ([("Le passé composé (pretérito perfecto)", "Conjugue au pretérito perfecto.",
          [("Yo (comer) ya.", "he comido"), ("Tú (hacer) la tarea.", "has hecho"), ("Ella (ver) la película.", "ha visto"), ("Nosotros (escribir) la carta.", "hemos escrito"), ("Ellos (decir) la verdad.", "han dicho")]),
         ("Por et para", "Complète avec por ou para.",
          [("Este regalo es ___ ti.", "para"), ("Gracias ___ tu ayuda.", "por"), ("Estudio ___ ser médico.", "para"), ("Viajo ___ el norte de Benín.", "por"), ("Salgo ___ Cotonou mañana.", "para")])],
        [("Aún no (yo / terminar) la tarea.", "he terminado"), ("Este libro es ___ mi hermano.", "para"), ("Ella (volver) hoy a casa.", "ha vuelto"), ("Rédige un commentaire de huit lignes sur l'importance des langues vivantes.", L)]),
}}
DATA["Français"] = {
 "CE2": ([("Le présent des verbes du 1er groupe", "Écris le verbe au présent.",
           [("Les enfants (chanter) en classe.", "chantent"), ("Je (manger) du riz.", "mange"), ("Nous (parler) fort.", "parlons"), ("Tu (jouer) au ballon.", "joues"), ("Vous (regarder) la télévision.", "regardez")]),
          ("Le pluriel des noms", "Mets les noms au pluriel.",
           [("un oiseau", "des oiseaux"), ("un cheval", "des chevaux"), ("un bijou", "des bijoux"), ("un journal", "des journaux"), ("un chapeau", "des chapeaux")])],
         [("Les filles sont ___ . (content)", "contentes"), ("Tu (finir) ton travail.", "finis"), ("un animal", "des animaux"), ("Écris trois phrases pour décrire ta classe.", L)]),
 "CM1": ([("L'imparfait de l'indicatif", "Écris le verbe à l'imparfait.",
           [("Autrefois, nous (jouer) dans la cour.", "jouions"), ("Il (finir) son devoir.", "finissait"), ("Tu (avoir) peur.", "avais"), ("Elles (être) joyeuses.", "étaient"), ("J'(aller) au marché.", "allais")]),
          ("a / à, et / est, on / ont", "Choisis la bonne écriture.",
           [("Il ___ un livre. (a / à)", "a"), ("Il va ___ l'école. (a / à)", "à"), ("Awa ___ Kofi sont amis. (et / est)", "et"), ("Elle ___ gentille. (et / est)", "est"), ("Ils ___ fini. (on / ont)", "ont")])],
         [("Hier, nous (manger) du riz. (passé composé)", "avons mangé"), ("Quand j'étais petit, je (jouer) dehors.", "jouais"), ("Il ___ mal ___ la tête.", "a ... à"), ("Écris quatre phrases à l'imparfait sur ton village.", L)]),
 "CM2": ([("Le passé composé et l'accord du participe passé", "Conjugue au passé composé.",
           [("Les enfants (arriver) hier.", "sont arrivés"), ("Elle (manger) une mangue.", "a mangé"), ("Les lettres que j'(écrire)...", "ai écrites"), ("Nous (partir) tôt. (garçons)", "sommes partis"), ("Elles (tomber) dans la cour.", "sont tombées")]),
          ("Les fonctions dans la phrase", "Donne la fonction du groupe en gras (sujet, COD, COI, attribut du sujet, complément circonstanciel).",
           [("Kofi mange une mangue. (une mangue)", "COD"), ("Awa parle à sa mère. (à sa mère)", "COI"), ("Le chat dort. (le chat)", "sujet"), ("Il est malade. (malade)", "attribut du sujet"), ("Il travaille ce soir. (ce soir)", "complément circonstanciel de temps")])],
         [("Demain, je (finir) mon travail.", "finirai"), ("Les fleurs que tu as (cueillir) sont belles.", "cueillies"), ("Il mange du riz. (fonction de « du riz »)", "COD"), ("Rédige cinq lignes sur ta journée d'hier.", L)]),
 "6e": ([("Types de phrases", "Donne le type de la phrase (déclarative, interrogative, exclamative, injonctive).",
          [("Viens ici !", "injonctive"), ("Il pleut.", "déclarative"), ("Où vas-tu ?", "interrogative"), ("Quel beau temps !", "exclamative"), ("Ne cours pas.", "injonctive")]),
         ("Le passé simple (3e personne)", "Écris le verbe au passé simple.",
          [("Il (chanter)", "chanta"), ("Ils (finir)", "finirent"), ("Elle (aller)", "alla"), ("Ils (avoir)", "eurent"), ("Il (être)", "fut")])],
        [("Mets à la forme négative : Il mange.", "Il ne mange pas."), ("Mets à l'impératif : Tu viens.", "Viens."), ("Elle (parler)", "parla"), ("Rédige un petit récit de cinq lignes (imparfait et passé simple).", L)]),
 "5e": ([("L'accord du participe passé avec avoir", "Accorde le participe passé si nécessaire.",
          [("Les mangues que j'ai (manger).", "mangées"), ("Elle a (voir) ses amis.", "vu"), ("Les lettres qu'il a (écrire).", "écrites"), ("Quelle chanson as-tu (entendre) ?", "entendue"), ("Ils ont (finir).", "fini")]),
         ("La nature des mots", "Donne la nature du mot en gras.",
          [("Elle chante joliment. (joliment)", "adverbe"), ("Une fille intelligente. (intelligente)", "adjectif qualificatif"), ("Il court vite. (vite)", "adverbe"), ("Mon frère travaille. (mon)", "déterminant (adjectif possessif)"), ("Nous partons. (nous)", "pronom personnel")])],
        [("Les photos que nous avons (prendre).", "prises"), ("Une fille intelligente : nature de « intelligente ».", "adjectif qualificatif"), ("Si j'avais le temps, je (venir).", "viendrais"), ("Rédige cinq lignes : Si j'étais ministre de l'Éducation...", L)]),
 "4e": ([("Imparfait et passé simple dans le récit", "Conjugue les verbes au temps qui convient.",
          [("Il (marcher) quand la pluie (commencer).", "marchait, commença"), ("Le soleil (briller) et les oiseaux (chanter).", "brillait, chantaient"), ("Soudain, la porte (s'ouvrir).", "s'ouvrit"),
           ("Il (être) fatigué, il (s'asseoir).", "était, s'assit"), ("Quand il (arriver), il (pleuvoir) déjà.", "arriva, pleuvait")]),
         ("La proposition relative", "Complète avec qui, que, où ou dont.",
          [("Le livre ___ je lis est intéressant.", "que"), ("La fille ___ parle est ma sœur.", "qui"), ("Le village ___ je suis né est loin.", "où"), ("L'ami ___ je parle est malade.", "dont"), ("Voici la maison ___ mon père a construite.", "que")])],
        [("Nous (marcher) depuis une heure quand il (commencer) à pleuvoir.", "marchions, commença"), ("La maison ___ il parle est vieille.", "dont"),
         ("Il faut que tu (venir).", "viennes"), ("Écris un court récit de cinq lignes en alternant imparfait et passé simple.", L)]),
 "3e": ([("Le subjonctif présent", "Conjugue au subjonctif présent.",
          [("Il faut que je (finir).", "finisse"), ("Il faut que tu (être) patient.", "sois"), ("Je veux qu'ils (venir).", "viennent"), ("Il faut que nous (avoir) du courage.", "ayons"), ("Bien qu'il (pleuvoir), nous sortons.", "pleuve")]),
         ("La cause et la conséquence", "Complète avec le mot qui convient.",
          [("Il est absent ___ il est malade. (car / donc)", "car"), ("Il est malade, ___ il est absent. (car / donc)", "donc"), ("___ la pluie, nous sommes restés. (À cause de / Pour)", "À cause de"),
           ("Il a travaillé ___ réussir. (pour / parce que)", "pour"), ("Il a réussi ___ il a beaucoup travaillé. (pour / parce qu')", "parce qu'")])],
        [("Il faut que vous (aller) à l'école.", "alliez"), ("Il a échoué, ___ il n'avait pas révisé. (car / donc)", "car"), ("Il faut que nous (faire) nos devoirs.", "fassions"),
         ("Rédige un paragraphe argumenté de huit lignes sur le rôle de l'école.", L)]),
}
NIVEAUX = ["4e", "3e", "2nde", "1ère", "Tle"]


def pdf(langue, niveau, enseignant):
    from xml.sax.saxutils import escape as e
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak
    sit, ev = DATA[langue][niveau]
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=17)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.HexColor("#0b4f6c"))
    cr = ParagraphStyle("cr", parent=ss["BodyText"], fontSize=10.5, leading=15)
    rep = ParagraphStyle("rep", parent=cr, textColor=colors.HexColor("#14532d"), fontName="Helvetica-Oblique", leftIndent=14)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Bréviaire {langue} {niveau}")
    qui = "Cahier de l'enseignant (avec corrigés)" if enseignant else "Cahier de l'élève"
    h = [Paragraph(f"Bréviaire de {e(langue.lower())} - {e(niveau)}", h1), Paragraph(qui, ss["Heading3"]),
         Paragraph("Nom et prénoms : ______________________________   Classe : ________   Date : ____________" if not enseignant else
                   "Exercices de consolidation par situation d'apprentissage et évaluation (20 points : 5 points par question).", cr), Spacer(1, 6)]
    n = 0
    for i, (titre, cons, items) in enumerate(sit, 1):
        h.append(Paragraph(f"Situation d'apprentissage {i} : {e(titre)}", h2))
        h.append(Paragraph(f"<i>{e(cons)}</i>", cr))
        for q, a in items:
            n += 1
            h.append(Paragraph(f"{n}. {e(q)}" + ("" if enseignant else "  ______________________"), cr))
            if enseignant:
                h.append(Paragraph("Corrigé : " + e(a), rep))
        h.append(Spacer(1, 6))
    h.append(Paragraph("Évaluation (20 points)", h2))
    for j, (q, a) in enumerate(ev, 1):
        h.append(Paragraph(f"{j}. {e(q)} <b>(5 pts)</b>" + ("" if enseignant else "<br/>______________________________________________"), cr))
        if enseignant:
            h.append(Paragraph("Corrigé : " + e(a), rep))
    doc.build(h)
    return buf.getvalue()
