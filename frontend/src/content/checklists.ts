// M-09 security checklist and M-11 social privacy steps (self-reported). Plain language, per-OS instructions.
export type Item = { key: string; title: string; why: string; steps: Record<string, string[]> };

export const security: Item[] = [
  { key: "two_factor", title: "Zwei-Faktor-Anmeldung für E-Mail und Bank", why: "Ein gestohlenes Passwort allein reicht dann nicht mehr.",
    steps: { Allgemein: ["Öffne die Sicherheitseinstellungen deines E-Mail-Kontos.", "Wähle „Bestätigung in zwei Schritten“ oder „2FA“.", "Nutze eine Authenticator-App oder einen Passkey.", "Bewahre die Wiederherstellungscodes sicher auf."] } },
  { key: "password_manager", title: "Passwort-Manager nutzen", why: "Jedes Konto bekommt ein eigenes, starkes Passwort.",
    steps: { iPhone: ["Einstellungen → Passwörter (App „Passwörter“).", "Bei neuen Konten das vorgeschlagene starke Passwort übernehmen."],
      Android: ["Einstellungen → Google → Autofill → Google Passwortmanager.", "Passwort-Check im Manager starten."], Windows: ["Im Browser (Edge/Chrome/Firefox) den Passwortmanager aktivieren oder eine eigenständige App installieren."] } },
  { key: "screen_lock", title: "Bildschirmsperre mit PIN oder Biometrie", why: "Schützt deine Daten, wenn das Gerät verloren geht.",
    steps: { iPhone: ["Einstellungen → Face ID & Code → Code aktivieren (6-stellig oder länger)."], Android: ["Einstellungen → Sicherheit → Displaysperre → PIN oder Passwort."],
      Windows: ["Einstellungen → Konten → Anmeldeoptionen → Windows Hello PIN.", "Automatische Sperre nach wenigen Minuten einstellen."] } },
  { key: "updates", title: "Automatische Updates einschalten", why: "Updates schließen bekannte Sicherheitslücken.",
    steps: { iPhone: ["Einstellungen → Allgemein → Softwareupdate → Automatische Updates."], Android: ["Einstellungen → System → Softwareupdate; Play Store → Apps automatisch aktualisieren."],
      Windows: ["Einstellungen → Windows Update → Erweiterte Optionen → Updates automatisch erhalten."] } },
  { key: "app_permissions", title: "App-Berechtigungen prüfen", why: "Viele Apps brauchen keinen Standort, kein Mikrofon und keine Kontakte.",
    steps: { iPhone: ["Einstellungen → Datenschutz & Sicherheit → Ortungsdienste/Mikrofon/Kontakte durchgehen."], Android: ["Einstellungen → Datenschutz → Berechtigungsmanager."],
      Windows: ["Einstellungen → Datenschutz und Sicherheit → App-Berechtigungen."] } },
  { key: "backup", title: "Regelmäßiges Backup", why: "Schützt vor Datenverlust und Erpressungs-Software.",
    steps: { iPhone: ["Einstellungen → [Name] → iCloud → iCloud-Backup aktivieren, oder Backup am Computer."], Android: ["Einstellungen → Google → Backup → Backup aktivieren."],
      Windows: ["Externe Festplatte: Einstellungen → System → Speicher → Sicherungsoptionen.", "Wichtig: Backup-Laufwerk danach trennen."] } },
  { key: "router_password", title: "Router-Passwort und WLAN-Schlüssel ändern", why: "Standard-Passwörter sind oft bekannt oder schwach.",
    steps: { Allgemein: ["Router-Oberfläche öffnen (z. B. fritz.box oder 192.168.0.1).", "Admin-Passwort ändern.", "WLAN-Verschlüsselung WPA2 oder WPA3 wählen.", "Firmware-Updates aktivieren."] } },
  { key: "browser_extensions", title: "Browser-Erweiterungen aufräumen", why: "Erweiterungen können alles mitlesen, was du im Browser tust.",
    steps: { Allgemein: ["Erweiterungen-Seite öffnen (chrome://extensions oder about:addons).", "Alles entfernen, was du nicht kennst oder nicht brauchst."] } },
];

export const socialLabels: Record<string, string> = {
  instagram: "Instagram", tiktok: "TikTok", facebook: "Facebook", x: "X (Twitter)", linkedin: "LinkedIn", youtube: "YouTube", snapchat: "Snapchat", whatsapp: "WhatsApp",
};

export const social: Record<string, Record<string, { title: string; how: string }>> = {
  instagram: {
    private_account: { title: "Privates Konto", how: "Profil → Menü → Kontoprivatsphäre → Privates Konto einschalten." },
    location_off: { title: "Keine Standorte in Beiträgen", how: "Beim Posten keinen Ort hinzufügen; Kamera-Standort im Handy deaktivieren." },
    tag_review: { title: "Markierungen manuell freigeben", how: "Einstellungen → Markierungen und Erwähnungen → Markierungen manuell genehmigen." },
    contacts_sync_off: { title: "Kontakte-Synchronisierung aus", how: "Einstellungen → Kontensynchronisierung → Kontakte synchronisieren ausschalten." },
    story_close_friends: { title: "Storys nur für enge Freunde", how: "Beim Teilen der Story „Enge Freunde“ auswählen." },
    activity_status: { title: "Aktivitätsstatus aus", how: "Einstellungen → Nachrichten und Story-Antworten → Aktivitätsstatus anzeigen ausschalten." },
  },
  tiktok: {
    private_account: { title: "Privates Konto", how: "Profil → Menü → Einstellungen und Datenschutz → Datenschutz → Privates Konto." },
    suggest_account_off: { title: "Konto nicht anderen vorschlagen", how: "Datenschutz → Dein Konto anderen vorschlagen → alles aus." },
    duet_stitch_limit: { title: "Duett/Stitch einschränken", how: "Datenschutz → Duett und Stitch → Nur ich oder Freunde." },
    downloads_off: { title: "Downloads deiner Videos aus", how: "Datenschutz → Downloads → aus." },
    contacts_sync_off: { title: "Kontakte nicht synchronisieren", how: "Datenschutz → Kontakte und Facebook-Freunde synchronisieren → aus." },
  },
  facebook: {
    profile_audience: { title: "Wer sieht dein Profil?", how: "Einstellungen → Profil-Sperre bzw. Zielgruppe für Beiträge auf „Freunde“." },
    search_engine_off: { title: "Nicht in Suchmaschinen", how: "Einstellungen → Privatsphäre → Suchmaschinen außerhalb von Facebook → aus." },
    find_by_phone: { title: "Nicht per Telefonnummer auffindbar", how: "Privatsphäre → Wer kann dich anhand deiner Telefonnummer finden? → Nur ich." },
    tag_review: { title: "Markierungen prüfen", how: "Profil und Markierung → Markierungen überprüfen → an." },
    past_posts_limit: { title: "Alte Beiträge einschränken", how: "Privatsphäre → Vergangene Beiträge einschränken." },
    off_facebook_activity: { title: "Aktivitäten außerhalb von Facebook", how: "Kontenübersicht → Deine Informationen → Aktivitäten außerhalb von Meta → trennen." },
  },
  x: {
    protect_posts: { title: "Posts schützen", how: "Einstellungen → Datenschutz und Sicherheit → Zielgruppe → Posts schützen." },
    location_off: { title: "Standort aus", how: "Datenschutz → Standortinformationen → aus." },
    discoverability_phone: { title: "Nicht per Telefonnummer auffindbar", how: "Datenschutz → Auffindbarkeit und Kontakte → Telefonnummer aus." },
    discoverability_email: { title: "Nicht per E-Mail auffindbar", how: "Auffindbarkeit und Kontakte → E-Mail aus." },
    dm_settings: { title: "Direktnachrichten einschränken", how: "Datenschutz → Direktnachrichten → nur von Personen, denen du folgst." },
  },
  linkedin: {
    profile_visibility: { title: "Profil-Sichtbarkeit", how: "Einstellungen → Sichtbarkeit → Sichtbarkeit des Profils." },
    public_profile_edit: { title: "Öffentliches Profil einschränken", how: "Sichtbarkeit → Öffentliches Profil bearbeiten → Angaben abwählen." },
    contact_info: { title: "Kontaktdaten verbergen", how: "Sichtbarkeit → Wer kann deine E-Mail-Adresse sehen → Nur 1. Grades oder Nur ich." },
    discover_by_phone: { title: "Nicht per Telefonnummer auffindbar", how: "Sichtbarkeit → Profil-Auffindbarkeit über Telefonnummer → Nur ich." },
    data_for_ai_off: { title: "Daten nicht für KI-Training", how: "Datenschutz → Daten zur Verbesserung generativer KI → aus." },
  },
  youtube: {
    subscriptions_private: { title: "Abos privat", how: "YouTube Studio bzw. Einstellungen → Datenschutz → Abos privat halten." },
    playlists_private: { title: "Playlists privat", how: "Bibliothek → Playlists → Sichtbarkeit auf Privat." },
    liked_private: { title: "Gefällt-mir privat", how: "Datenschutz → Gespeicherte Playlists privat halten." },
    channel_info: { title: "Kanal-Infos prüfen", how: "Kanal anpassen → Basisinfo → Wohnort und Kontakt entfernen." },
  },
  snapchat: {
    snap_map_ghost: { title: "Snap Map: Geistmodus", how: "Karte öffnen → Einstellungen → Geistmodus an." },
    contact_me_friends: { title: "Kontakt nur von Freunden", how: "Einstellungen → Wer darf mich kontaktieren → Freunde." },
    quick_add_off: { title: "Quick Add aus", how: "Einstellungen → Mich in Quick Add anzeigen → aus." },
    story_audience: { title: "Story-Publikum", how: "Einstellungen → Wer darf meine Story sehen → Freunde." },
  },
  whatsapp: {
    last_seen: { title: "Zuletzt online verbergen", how: "Einstellungen → Datenschutz → Zuletzt online → Meine Kontakte oder Niemand." },
    profile_photo_contacts: { title: "Profilbild nur Kontakte", how: "Datenschutz → Profilbild → Meine Kontakte." },
    about_contacts: { title: "Info nur Kontakte", how: "Datenschutz → Info → Meine Kontakte." },
    groups_contacts: { title: "Gruppeneinladungen einschränken", how: "Datenschutz → Gruppen → Meine Kontakte." },
    read_receipts: { title: "Lesebestätigung nach Wunsch", how: "Datenschutz → Lesebestätigungen." },
    silence_unknown: { title: "Unbekannte Anrufer stummschalten", how: "Datenschutz → Anrufe → Unbekannte Anrufer stummschalten." },
  },
};
