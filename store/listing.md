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
- on a full-screen field, with a course profile: the checkpoint after that and when you'll get there

It learns how fast you go on every slope, from steep descents to steep climbs, and keeps learning during the race. It corrects for how your day is going and for your watch measuring more distance than the course map.

Optional: paste two texts into the settings to make it accurate from the first kilometre: your pace from past races, and the course profile with every climb and descent between checkpoints. There you can also add points of your own to count down to: the top and bottom of every big climb, huts and villages. The website explains how, step by step, in English, Italian, French and German.

Works without a phone or signal during the race. Time spent stopped at aid stations is not counted.

Free and open source. Not affiliated with Garmin.

#ultratrail #trailrunning #ultrarunning #skyrunning #mountainrunning

## What's new (0.2.0)

Counts down to points you add (climb tops and bottoms, huts, villages); copes with courses whose checkpoints differ from the course profile; on full-screen fields, the checkpoint after the next; the time shown only as precisely as it's known; the field and its settings in Italian, French and German.

## What's new (0.1.0, beta)

First version: next checkpoint, time to it and arrival time; learns your pace by slope; optional speed model and course profile in the settings.

## Links

- Website: https://howfar-garmin.github.io/howfar/
- Source: https://github.com/howfar-garmin/howfar

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
- su un campo a schermo intero, con il profilo del percorso: il checkpoint successivo e quando ci arriverai

Impara quanto vai veloce su ogni pendenza, dalle discese ripide alle salite ripide, e continua a imparare durante la gara. Tiene conto di come sta andando la tua giornata e del fatto che l'orologio misura più distanza della mappa del percorso.

Facoltativo: incolla due testi nelle impostazioni per renderlo preciso dal primo chilometro: il tuo passo dalle gare passate e il profilo del percorso con ogni salita e discesa tra i checkpoint. Lì puoi anche aggiungere punti tuoi a cui fare il conto alla rovescia: la cima e il fondo di ogni salita importante, rifugi e paesi. Il sito spiega come, passo per passo, anche in italiano.

Funziona senza telefono e senza segnale durante la gara. Il tempo fermo ai ristori non viene contato.

Gratuito e open source. Non affiliato a Garmin.

### Français

**Description courte :** Le temps jusqu'au prochain point de contrôle de ton parcours, appris de ta façon de monter et de descendre.

**Description :**

Combien de fois as-tu voulu savoir combien de temps il reste jusqu'au prochain point de contrôle ? Tu as demandé à un bénévole, puis tu t'es énervé de voir à quel point il se trompait.

HowFar te donne la réponse au poignet. Pendant que tu suis un parcours, il affiche :
- le nom du prochain point de contrôle
- le temps pour y arriver, tant que tu avances
- l'heure à laquelle tu y seras
- sur un champ en plein écran, avec le profil du parcours : le point de contrôle suivant et quand tu y seras

Il apprend ta vitesse sur chaque pente, des descentes raides aux montées raides, et continue d'apprendre pendant la course. Il tient compte de la façon dont se passe ta journée et du fait que ta montre mesure plus de distance que la carte du parcours.

Facultatif : colle deux textes dans les réglages pour le rendre précis dès le premier kilomètre : ton allure tirée de tes courses passées, et le profil du parcours avec chaque montée et chaque descente entre les points de contrôle. Tu peux aussi y ajouter tes propres points vers lesquels faire le compte à rebours : le haut et le bas de chaque grosse montée, les refuges et les villages. Le site explique comment, étape par étape, aussi en français.

Fonctionne sans téléphone ni réseau pendant la course. Le temps passé à l'arrêt aux ravitaillements n'est pas compté.

Gratuit et open source. Non affilié à Garmin.

### Deutsch

**Kurzbeschreibung:** Die Zeit bis zum nächsten Kontrollpunkt deiner Strecke, gelernt daraus, wie du bergauf und bergab läufst.

**Beschreibung:**

Wie oft wolltest du schon wissen, wie lange es noch bis zum nächsten Kontrollpunkt dauert? Du hast einen Helfer gefragt und dich dann geärgert, wie weit er danebenlag.

HowFar bringt dir die Antwort ans Handgelenk. Während du einer Strecke folgst, zeigt es:
- den Namen des nächsten Kontrollpunkts
- die Zeit bis dorthin, solange du in Bewegung bleibst
- die Uhrzeit, zu der du ankommst
- auf einem Feld im Vollbild, mit Streckenprofil: den Kontrollpunkt danach und wann du dort bist

Es lernt, wie schnell du auf jeder Steigung bist, von steilen Abstiegen bis zu steilen Anstiegen, und lernt im Rennen weiter. Es berücksichtigt, wie dein Tag läuft, und dass deine Uhr mehr Strecke misst als die Streckenkarte.

Optional: Füge zwei Texte in die Einstellungen ein, damit es ab dem ersten Kilometer genau ist: dein Tempo aus früheren Rennen und das Streckenprofil mit jedem Anstieg und jeder Abfahrt zwischen den Kontrollpunkten. Dort kannst du auch eigene Punkte hinzufügen, auf die heruntergezählt wird: den höchsten und den tiefsten Punkt jedes großen Anstiegs, Hütten und Dörfer. Die Website erklärt Schritt für Schritt, wie es geht, auch auf Deutsch.

Funktioniert während des Rennens ohne Handy und ohne Empfang. Die Zeit an Verpflegungsstationen wird nicht mitgezählt.

Kostenlos und Open Source. Nicht mit Garmin verbunden.

