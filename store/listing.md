# Connect IQ Store listing

Text to paste into the Connect IQ developer site when uploading, and how to upload.

## Two packages

| Package | App ID | Store visibility | Review |
|---|---|---|---|
| `HowFar-beta.iq` (build with `beta.jungle`) | its own (`manifest-beta.xml`) | only the developer's account | none |
| `HowFar.iq` (build with `monkey.jungle`) | the public one (`manifest.xml`) | everyone, once approved | Garmin reviews it |

A beta must use a different app ID from the public app; that is what keeps it private. Keep the product lists of the two manifests the same.

```bash
SDK="$(cat "$HOME/Library/Application Support/Garmin/ConnectIQ/current-sdk.cfg")"
"$SDK/bin/monkeyc" -e -f beta.jungle -o bin/release/HowFar-beta.iq -y developer_key -r
"$SDK/bin/monkeyc" -e -f monkey.jungle -o bin/release/HowFar.iq -y developer_key -r
```

## Upload the private beta

1. Sign in at https://apps.garmin.com/developer/upload with your Garmin account and upload `HowFar-beta.iq`.
2. Mark it as a beta app. Garmin validates the package; a beta is not reviewed.
3. Add the description below. A beta has no public page, so screenshots are optional.
4. Install it from your developer dashboard at apps.garmin.com: open the app and use its download/install button. It reaches the watch at the next sync of the Garmin Connect app, with no file copying.
5. Its Settings then appear in the Garmin Connect app (your watch → Connect IQ apps → HowFar beta → Settings).

## Submit the public app (later)

Upload `HowFar.iq` the same way, without the beta option. While Garmin reviews it, it stays out of the store but you can preview and download it for testing; once approved it appears publicly. See https://developer.garmin.com/connect-iq/submit-an-app/ and Garmin's App Review Guidelines.

## App name

HowFar

## Category

Data fields

## Short description

Time to the next checkpoint of your course, learned from how you climb and descend.

## Description

How many times have you wanted to know how long to the next checkpoint? You asked a volunteer, then got angry at how far off they were.

HowFar puts the answer on your wrist. While you follow a course, it shows:
- the name of the next checkpoint
- the time to get there, while you keep moving
- the time of day you'll arrive
- on a full data screen, with a course profile: the points before and after it, in the order you meet them

Nothing to set up: it learns how fast you go on every slope while you run, from steep descents to steep climbs, and keeps learning all race long. It remembers your past runs, follows you when you slow down or pick up again, and corrects for your watch measuring more distance than the course map.

Before the race, take a few minutes on the race prep page of the website. From your race's course file it makes a course profile to paste into HowFar's settings, so HowFar knows every climb and descent between checkpoints and can show the points around the next one. There you can also add points: the top and bottom of every climb and named huts and villages, found for you, or your own. Make each one main, to count down to it, or minor, to see it on the way. It's optional, and the website explains it step by step in English, Italian, French and German.

Made for trail runs of 25 km or more with real climbs and descents. Works without a phone or signal during the race. Time spent stopped at aid stations is not counted.

Feedback, problems, ideas: https://github.com/howfar-garmin/howfar/issues/new?template=feedback.yml (or Contact Developer on this page).

Free and open source. Not affiliated with Garmin.

#ultratrail #trailrunning #ultrarunning #skyrunning #mountainrunning

## What's new (0.3.0)

Learns on the run, with no pace to paste: the "pace from past races" setting is gone, past runs count less as the race goes on, and slopes not yet run are filled in from the nearest ones. Main and minor points: count down to the race's checkpoints and see climb tops, huts, villages or points of your own on the way. On a full data screen, the points ahead in the order you meet them; on a smaller field, the countdown. Later checkpoints show their leg's moving time, a coloured dot says how far off each time may be, and times are rounded only as precisely as they can be known. Copes with courses whose checkpoints differ from the course profile, and with loop courses. The field and its settings in Italian, French and German.

## What's new (0.1.0, beta)

First version: next checkpoint, time to it and arrival time; learns your pace by slope; optional speed model and course profile in the settings.

## Links

- Website: https://howfar-garmin.github.io/howfar/
- Source: https://github.com/howfar-garmin/howfar
- Feedback: https://github.com/howfar-garmin/howfar/issues/new?template=feedback.yml

## Translations

The store takes a description per language. The app name stays **HowFar**.

### Italiano

**Descrizione breve:** Il tempo al prossimo checkpoint del tuo percorso, imparato da come sali e scendi.

**Descrizione:**

Quante volte hai voluto sapere quanto manca al prossimo checkpoint? L'hai chiesto a un volontario e poi ti sei arrabbiato per quanto si sbagliava.

HowFar ti mette la risposta al polso. Mentre segui un percorso mostra:
- il nome del prossimo checkpoint
- il tempo per arrivarci, finché continui a muoverti
- l'ora a cui arriverai
- a schermo intero, con il profilo del percorso: i punti prima e dopo, nell'ordine in cui li incontri

Niente da impostare: impara quanto vai veloce su ogni pendenza mentre corri, dalle discese ripide alle salite ripide, e continua a imparare per tutta la gara. Ricorda le tue corse passate, ti segue quando rallenti o riprendi, e tiene conto del fatto che l'orologio misura più distanza della mappa del percorso.

Prima della gara, dedica qualche minuto alla pagina di preparazione del sito. Dal file del percorso della gara crea un profilo del percorso da incollare nelle impostazioni di HowFar, così HowFar conosce ogni salita e discesa tra i checkpoint e può mostrare i punti intorno al prossimo. Lì puoi anche aggiungere punti: l'inizio e la cima di ogni salita e rifugi e paesi con un nome, trovati per te, o punti tuoi. Rendi ognuno principale, per il conto alla rovescia, o secondario, per vederlo lungo la strada. È facoltativo, e il sito lo spiega passo per passo, anche in italiano.

Pensato per trail di 25 km o più, con salite e discese vere. Funziona senza telefono e senza segnale durante la gara. Il tempo fermo ai ristori non viene contato.

Commenti, problemi, idee: https://github.com/howfar-garmin/howfar/issues/new?template=feedback.yml (oppure Contatta lo sviluppatore in questa pagina).

Gratuito e open source. Non affiliato a Garmin.

### Français

**Description courte :** Le temps jusqu'au prochain point de contrôle de ton parcours, appris de ta façon de monter et de descendre.

**Description :**

Combien de fois as-tu voulu savoir combien de temps il reste jusqu'au prochain point de contrôle ? Tu as demandé à un bénévole, puis tu t'es énervé de voir à quel point il se trompait.

HowFar te donne la réponse au poignet. Pendant que tu suis un parcours, il affiche :
- le nom du prochain point de contrôle
- le temps pour y arriver, tant que tu avances
- l'heure à laquelle tu y seras
- en plein écran, avec le profil du parcours : les points avant et après, dans l'ordre où tu les rencontres

Rien à régler : il apprend ta vitesse sur chaque pente pendant que tu cours, des descentes raides aux montées raides, et continue d'apprendre toute la course. Il se souvient de tes sorties passées, te suit quand tu ralentis ou repars, et tient compte du fait que ta montre mesure plus de distance que la carte du parcours.

Avant la course, prends quelques minutes sur la page de préparation du site. À partir du fichier du parcours de ta course, elle crée un profil du parcours à coller dans les réglages de HowFar : HowFar connaît alors chaque montée et descente entre les points de contrôle et peut afficher les points autour du prochain. Tu peux aussi y ajouter des points : le bas et le haut de chaque montée et les refuges et villages qui ont un nom, trouvés pour toi, ou les tiens. Rends chacun principal, pour un compte à rebours, ou secondaire, pour le voir sur le chemin. C'est facultatif, et le site l'explique étape par étape, aussi en français.

Conçu pour les trails de 25 km ou plus, avec de vraies montées et descentes. Fonctionne sans téléphone ni réseau pendant la course. Le temps passé à l'arrêt aux ravitaillements n'est pas compté.

Avis, problèmes, idées : https://github.com/howfar-garmin/howfar/issues/new?template=feedback.yml (ou Contacter le développeur sur cette page).

Gratuit et open source. Non affilié à Garmin.

### Deutsch

**Kurzbeschreibung:** Die Zeit bis zum nächsten Kontrollpunkt deiner Strecke, gelernt daraus, wie du bergauf und bergab läufst.

**Beschreibung:**

Wie oft wolltest du schon wissen, wie lange es noch bis zum nächsten Kontrollpunkt dauert? Du hast einen Helfer gefragt und dich dann geärgert, wie weit er danebenlag.

HowFar bringt dir die Antwort ans Handgelenk. Während du einer Strecke folgst, zeigt es:
- den Namen des nächsten Kontrollpunkts
- die Zeit bis dorthin, solange du in Bewegung bleibst
- die Uhrzeit, zu der du ankommst
- im Vollbild, mit Streckenprofil: die Punkte davor und danach, in der Reihenfolge, in der du sie erreichst

Nichts einzustellen: Es lernt, während du läufst, wie schnell du auf jeder Steigung bist, von steilen Abstiegen bis zu steilen Anstiegen, und lernt das ganze Rennen über weiter. Es merkt sich deine früheren Läufe, folgt dir, wenn du langsamer wirst oder wieder zulegst, und berücksichtigt, dass deine Uhr mehr Strecke misst als die Streckenkarte.

Nimm dir vor dem Rennen ein paar Minuten für die Vorbereitungsseite der Website. Aus der Streckendatei deines Rennens erstellt sie ein Streckenprofil, das du in die Einstellungen von HowFar einfügst: Dann kennt HowFar jeden Anstieg und Abstieg zwischen den Kontrollpunkten und kann die Punkte rund um den nächsten zeigen. Dort kannst du auch Punkte hinzufügen: Fuß und Gipfel jedes Anstiegs und benannte Hütten und Dörfer, für dich gefunden, oder eigene. Mach jeden zum Hauptpunkt, um herunterzuzählen, oder zum Nebenpunkt, um ihn auf dem Weg zu sehen. Es ist optional, und die Website erklärt es Schritt für Schritt, auch auf Deutsch.

Gemacht für Trailläufe ab 25 km mit echten Anstiegen und Abstiegen. Funktioniert während des Rennens ohne Handy und ohne Empfang. Die Zeit an Verpflegungsstationen wird nicht mitgezählt.

Feedback, Probleme, Ideen: https://github.com/howfar-garmin/howfar/issues/new?template=feedback.yml (oder Entwickler kontaktieren auf dieser Seite).

Kostenlos und Open Source. Nicht mit Garmin verbunden.

