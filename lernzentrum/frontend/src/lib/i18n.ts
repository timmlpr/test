// i18n structure (UI is German; add other locales by adding a dictionary with the same keys).
const de = {
  nav: {
    home: "Heute",
    live: "Live",
    modules: "Module",
    learn: "Lernen",
    library: "Bibliothek",
    inbox: "Eingang",
    calendar: "Kalender",
    settings: "Einstellungen",
  },
  common: { save: "Speichern", cancel: "Abbrechen", test: "Testen", delete: "Löschen", back: "Zurück", next: "Weiter", skip: "Überspringen" },
} as const;

type Dict = typeof de;
const dictionaries: Record<string, Dict> = { de };

export function t(): Dict {
  return dictionaries.de;
}
