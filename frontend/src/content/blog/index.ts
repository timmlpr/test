// 10 starter articles (factual drafts). Each lists source notes; verify before publishing.
export type Post = { slug: string; title: string; description: string; date: string; minutes: number; body: string; sources: string[] };

export const posts: Post[] = [
  {
    slug: "eigene-daten-im-netz-finden", title: "Was das Netz über dich weiß – und wie du es herausfindest", date: "2026-11-01", minutes: 5,
    description: "Eine einfache Anleitung, um die eigenen Spuren im Internet zu finden – ohne Panik und ohne Spezialwissen.",
    body: `Viele Menschen wissen nicht, welche ihrer Daten öffentlich auffindbar sind. Das ist normal. Mit ein paar Schritten bekommst du einen guten Überblick.

## 1. Such nach deinem Namen – mit Anführungszeichen
Gib deinen vollen Namen in Anführungszeichen in eine Suchmaschine ein, z. B. "Alex Beispiel". Ergänze deinen Wohnort. So findest du Vereinsseiten, alte Ergebnislisten oder Kommentare.

## 2. Prüfe deine E-Mail-Adressen auf Datenlecks
Dienste wie Have I Been Pwned oder XposedOrNot zeigen, ob eine Adresse in bekannten Datenlecks vorkommt. Prüfe nur deine eigenen Adressen.

## 3. Schau in alte Konten
Foren, Shops und Apps, die du nicht mehr nutzt, speichern oft noch Daten. Notiere sie – später kannst du die Löschung beantragen.

## 4. Mach eine Liste – und fang mit dem Wichtigsten an
Adresse, Telefonnummer und Geburtsdatum sind sensibler als ein Benutzername. Fang dort an.

> Tipp: Fadeprint erledigt die Schritte 1 bis 4 für deine bestätigten Angaben und sortiert die Funde nach Wirkung.`,
    sources: ["https://haveibeenpwned.com/", "https://xposedornot.com/", "https://www.bfdi.bund.de/"],
  },
  {
    slug: "loeschanfrage-dsgvo-art-17", title: "Löschanfrage nach Art. 17 DSGVO: So geht’s", date: "2026-11-03", minutes: 6,
    description: "Wann du ein Recht auf Löschung hast, wie die Anfrage aussieht und welche Frist gilt.",
    body: `Die DSGVO gibt dir das Recht, die Löschung deiner personenbezogenen Daten zu verlangen (Art. 17). Das gilt zum Beispiel, wenn die Daten für den ursprünglichen Zweck nicht mehr nötig sind oder du deine Einwilligung widerrufst.

## Was in die Anfrage gehört
- Wer du bist und wie man dich erreicht
- Welche Daten oder Fundstellen betroffen sind (am besten mit Link)
- Die klare Bitte um Löschung nach Art. 17 DSGVO
- Die Bitte, Empfänger der Daten zu informieren (Art. 19 DSGVO)

## Welche Frist gilt?
Das Unternehmen muss **unverzüglich, spätestens innerhalb eines Monats** antworten (Art. 12 Abs. 3 DSGVO). In komplexen Fällen kann die Frist um zwei Monate verlängert werden – das muss dir aber mitgeteilt werden.

## Und wenn nichts passiert?
Du kannst dich bei der Datenschutz-Aufsichtsbehörde beschweren (Art. 77 DSGVO). In Deutschland ist meist die Behörde des Bundeslands zuständig, in dem das Unternehmen sitzt.

## Grenzen
Manche Daten müssen aufbewahrt werden, z. B. Rechnungen (Aufbewahrungspflichten nach HGB/AO). Dann kannst du verlangen, dass die Verarbeitung eingeschränkt wird (Art. 18 DSGVO).

*Hinweis: Dieser Artikel ist keine Rechtsberatung.*`,
    sources: ["https://eur-lex.europa.eu/eli/reg/2016/679/oj", "https://www.datenschutzkonferenz-online.de/"],
  },
  {
    slug: "auskunft-art-15", title: "Auskunft nach Art. 15: Erfahre, was Firmen über dich speichern", date: "2026-11-05", minutes: 4,
    description: "Mit einer Auskunftsanfrage bekommst du eine Kopie deiner Daten – kostenlos.",
    body: `Mit dem Auskunftsrecht (Art. 15 DSGVO) fragst du ein Unternehmen, ob und welche Daten es über dich verarbeitet.

## Was du bekommst
- eine Kopie der Daten (die erste ist kostenlos)
- Zwecke der Verarbeitung und Empfänger
- geplante Speicherdauer
- Herkunft der Daten, wenn sie nicht von dir stammen

## Wann lohnt sich das?
Wenn du Werbung von Firmen bekommst, bei denen du nie Kunde warst – oder wenn du wissen willst, was eine App über dich gespeichert hat.

## Frist
Auch hier gilt: grundsätzlich ein Monat (Art. 12 Abs. 3 DSGVO).

*Keine Rechtsberatung.*`,
    sources: ["https://eur-lex.europa.eu/eli/reg/2016/679/oj"],
  },
  {
    slug: "datenleck-was-tun", title: "Deine E-Mail steckt in einem Datenleck – was jetzt?", date: "2026-11-06", minutes: 4,
    description: "Ruhig bleiben, Passwort ändern, Zwei-Faktor einschalten: die wichtigsten Schritte.",
    body: `Ein Datenleck heißt nicht, dass jemand gerade in dein Konto einbricht. Es heißt: Deine Daten sind irgendwo aufgetaucht. Jetzt geht es darum, sie wertlos zu machen.

## Die drei wichtigsten Schritte
1. **Passwort ändern** – beim betroffenen Dienst und überall, wo du dasselbe Passwort nutzt.
2. **Zwei-Faktor-Anmeldung einschalten** – dann reicht ein geleaktes Passwort nicht mehr.
3. **Auf Betrugsmails achten** – Angreifer nutzen geleakte Namen und Adressen für glaubwürdige Nachrichten.

## Wenn Bankdaten betroffen sind
Prüfe deine Kontoauszüge. Bei unbekannten Abbuchungen: Bank kontaktieren und Lastschrift zurückbuchen lassen (bei SEPA-Lastschrift meist bis zu 8 Wochen).

## Wenn Ausweisdaten betroffen sind
Achte auf unbekannte Verträge oder Bestellungen in deinem Namen. Eine Selbstauskunft bei Auskunfteien (z. B. nach Art. 15 DSGVO) kann helfen.`,
    sources: ["https://www.bsi.bund.de/dok/datenleck", "https://www.verbraucherzentrale.de/"],
  },
  {
    slug: "passwort-manager", title: "Passwort-Manager: Ein Passwort merken statt hundert", date: "2026-11-08", minutes: 4,
    description: "Warum ein Passwort-Manager sicherer ist als jede Merkregel – und wie du startest.",
    body: `Das größte Risiko ist nicht ein schwaches Passwort, sondern ein **wiederverwendetes**. Leakt es bei einem Dienst, probieren Angreifer es überall.

## Was ein Passwort-Manager macht
Er erzeugt für jedes Konto ein zufälliges, langes Passwort und füllt es automatisch aus. Du merkst dir nur noch ein starkes Hauptpasswort.

## So startest du
1. Wähle einen Manager (eingebaut in Browser/Betriebssystem oder eigenständig).
2. Lege ein langes Hauptpasswort fest – ein Satz aus mehreren Wörtern ist ideal.
3. Ändere zuerst die Passwörter von E-Mail, Bank und Online-Shopping.

## Und Passkeys?
Passkeys ersetzen Passwörter ganz. Sie sind an dein Gerät gebunden und gegen Phishing geschützt. Wo verfügbar: nutzen.`,
    sources: ["https://www.bsi.bund.de/DE/Themen/Verbraucherinnen-und-Verbraucher/Informationen-und-Empfehlungen/Cyber-Sicherheitsempfehlungen/Accountschutz/Sichere-Passwoerter-erstellen/sichere-passwoerter-erstellen_node.html", "https://fidoalliance.org/passkeys/"],
  },
  {
    slug: "zwei-faktor-anmeldung", title: "Zwei-Faktor-Anmeldung in 10 Minuten einrichten", date: "2026-11-10", minutes: 3,
    description: "Der wirksamste Schutz für deine Konten – einfach erklärt.",
    body: `Bei der Zwei-Faktor-Anmeldung (2FA) brauchst du neben dem Passwort einen zweiten Nachweis, z. B. einen Code aus einer App.

## Reihenfolge
1. E-Mail-Konto (darüber lassen sich alle anderen Passwörter zurücksetzen)
2. Online-Banking und Bezahldienste
3. Soziale Netzwerke und Shopping

## Welche Methode?
- **Passkey oder Sicherheitsschlüssel**: am sichersten
- **Authenticator-App**: sehr gut
- **SMS**: besser als nichts

Bewahre die Wiederherstellungscodes sicher auf – zum Beispiel ausgedruckt.`,
    sources: ["https://www.bsi.bund.de/DE/Themen/Verbraucherinnen-und-Verbraucher/Informationen-und-Empfehlungen/Cyber-Sicherheitsempfehlungen/Accountschutz/Zwei-Faktor-Authentisierung/zwei-faktor-authentisierung_node.html"],
  },
  {
    slug: "phishing-erkennen", title: "Phishing erkennen: 7 Warnzeichen", date: "2026-11-11", minutes: 4,
    description: "Paket-SMS, Bank-Mail, „Hallo Mama“: So erkennst du typische Maschen.",
    body: `Betrugsnachrichten werden besser. Diese Warnzeichen bleiben aber gleich:

1. **Zeitdruck** („innerhalb von 24 Stunden“, „Konto gesperrt“)
2. **Frage nach Passwort, PIN oder TAN** – seriöse Firmen fragen das nie per Nachricht
3. **Ungewöhnliche Bezahlwege** wie Gutscheinkarten oder Krypto
4. **Link-Adresse passt nicht zum Absender** (z. B. paypal.com.sicher-login.xyz)
5. **Unpersönliche Anrede**
6. **Unerwarteter Gewinn**
7. **Neue Nummer von Familienmitgliedern** – ruf die alte Nummer an

Im Zweifel: nicht klicken. Öffne die App oder Website des Anbieters selbst.

Verdächtige Nachrichten kannst du an die Verbraucherzentrale (Phishing-Radar) weiterleiten.`,
    sources: ["https://www.verbraucherzentrale.de/phishing-radar", "https://www.bsi.bund.de/DE/Themen/Verbraucherinnen-und-Verbraucher/Cyber-Sicherheitslage/Methoden-der-Cyber-Kriminalitaet/Spam-Phishing-Co/Passwortdiebstahl-durch-Phishing/passwortdiebstahl-durch-phishing_node.html"],
  },
  {
    slug: "fotos-metadaten-entfernen", title: "Fotos teilen ohne Standort: Metadaten entfernen", date: "2026-11-12", minutes: 3,
    description: "Viele Fotos speichern den genauen Aufnahmeort. So entfernst du ihn.",
    body: `Smartphones speichern in Fotos oft Zusatzinfos (EXIF): Kamera, Uhrzeit – und manchmal den GPS-Ort.

## Wo ist das ein Problem?
Wenn du Fotos von zu Hause öffentlich teilst oder per E-Mail verschickst. Viele soziale Netzwerke entfernen den Ort beim Hochladen, Messenger und E-Mail oft nicht.

## So gehst du vor
- **iPhone**: Beim Teilen auf „Optionen“ tippen und „Ort“ ausschalten.
- **Android**: In der Kamera-App die Standort-Speicherung deaktivieren.
- **Windows**: Rechtsklick → Eigenschaften → Details → „Eigenschaften und persönliche Informationen entfernen“.

Oder nutze den Bild-Check in Fadeprint: Er zeigt die Metadaten und entfernt sie mit einem Klick.`,
    sources: ["https://support.apple.com/de-de/guide/iphone/iph3d110f84/ios"],
  },
  {
    slug: "personensuchmaschinen", title: "Personensuchmaschinen: Einträge löschen lassen", date: "2026-11-14", minutes: 5,
    description: "Wie du Profile auf Personensuchseiten findest und entfernen lässt.",
    body: `Personensuchmaschinen sammeln öffentlich zugängliche Angaben zu Namen. In der EU müssen sie die DSGVO einhalten.

## Schritte
1. Suche nach deinem Namen auf der jeweiligen Seite.
2. Prüfe, ob der Eintrag wirklich dich betrifft (gleicher Name heißt nicht gleiche Person).
3. Nutze das Lösch-Formular der Seite oder schicke eine Anfrage nach Art. 17 DSGVO.
4. Beantrage zusätzlich die **Auslistung** bei Suchmaschinen, wenn der Eintrag dort erscheint.

## Auslistung bei Suchmaschinen
Seit dem EuGH-Urteil C-131/12 („Google Spain“) kannst du die Auslistung bestimmter Ergebnisse zu deinem Namen verlangen. Die großen Suchmaschinen bieten dafür Formulare an.`,
    sources: ["https://curia.europa.eu/juris/liste.jsf?num=C-131/12", "https://reportcontent.google.com/forms/rtbf"],
  },
  {
    slug: "kinder-online-privatsphaere", title: "Kinder und Privatsphäre im Netz: Ein Leitfaden für Eltern", date: "2026-11-16", minutes: 5,
    description: "Was Eltern über Fotos, Apps und Einwilligung von Kindern wissen sollten.",
    body: `Kinder wachsen mit dem Netz auf – ihre Daten verdienen besonderen Schutz.

## Fotos von Kindern
Überlege vor dem Posten: Würde mein Kind das mit 16 noch okay finden? Teile Fotos lieber in privaten Gruppen als öffentlich.

## Apps und Einwilligung
Nach Art. 8 DSGVO dürfen Kinder in Deutschland erst ab **16 Jahren** selbst in die Verarbeitung ihrer Daten bei Online-Diensten einwilligen. Darunter braucht es die Zustimmung der Eltern.

## Gemeinsam statt heimlich
Sprecht über Einstellungen wie private Profile oder Standortfreigabe. Heimliches Überwachen schadet dem Vertrauen – und ist bei älteren Kindern oft auch rechtlich problematisch.

## Gute Startpunkte
- Klicksafe (EU-Initiative) mit Ratgebern für Eltern
- Die Sicherheits-Checkliste in Fadeprint, die ihr gemeinsam durchgeht`,
    sources: ["https://www.klicksafe.de/", "https://eur-lex.europa.eu/eli/reg/2016/679/oj"],
  },
];

export const postBySlug = (slug: string) => posts.find((p) => p.slug === slug);
