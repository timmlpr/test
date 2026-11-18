"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { de } from "./de";
import { en } from "./en";
import { brand } from "../brand";

type Form = "du" | "sie";
type Locale = "de" | "en";
type Ctx = { t: (k: string, vars?: Record<string, string | number>) => string; locale: Locale; form: Form; setForm: (f: Form) => void; setLocale: (l: Locale) => void };

const I18n = createContext<Ctx | null>(null);

export function translate(key: string, locale: Locale, form: Form, vars?: Record<string, string | number>): string {
  const raw = (locale === "en" ? en[key] : undefined) ?? de[key];
  let s = raw === undefined ? key : typeof raw === "string" ? raw : raw[form];
  if (form === "sie" && locale === "de" && typeof raw === "string") s = toSie(s);
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}

/** Light automatic Du→Sie conversion for strings without an explicit variant. */
function toSie(s: string): string {
  const map: [RegExp, string][] = [
    [/\bdu\b/g, "Sie"], [/\bDu\b/g, "Sie"], [/\bdich\b/g, "sich"], [/\bdir\b/g, "Ihnen"], [/\bdein(e[mnrs]?)?\b/g, "Ihr$1"],
    [/\bDein(e[mnrs]?)?\b/g, "Ihr$1"], [/\bbist\b/g, "sind"], [/\bhast\b/g, "haben"], [/\bkannst\b/g, "können"], [/\bwillst\b/g, "wollen"],
    [/\bsiehst\b/g, "sehen"], [/\bbekommst\b/g, "bekommen"], [/\bbrauchst\b/g, "brauchen"], [/\bverschickst\b/g, "verschicken"],
    [/\bBestätige\b/g, "Bestätigen Sie"], [/\bStarte\b/g, "Starten Sie"], [/\bLege\b/g, "Legen Sie"], [/\bÄndere\b/g, "Ändern Sie"],
    [/\bErledige\b/g, "Erledigen Sie"], [/\bSchalte\b/g, "Schalten Sie"], [/\bPrüfe\b/g, "Prüfen Sie"], [/\bGib\b/g, "Geben Sie"],
    [/\bLade\b/g, "Laden Sie"], [/\bFrag\b/g, "Fragen Sie"], [/\bNotiere\b/g, "Notieren Sie"], [/\bZeige\b/g, "Zeigen Sie"],
    [/\bErstelle\b/g, "Erstellen Sie"], [/\bDurchsuche\b/g, "Durchsuchen Sie"], [/\bTrag dich\b/g, "Tragen Sie sich"], [/\bmelde dich\b/g, "melden Sie sich"],
    [/\bMelde dich\b/g, "Melden Sie sich"], [/\bFasse\b/g, "Fassen Sie"], [/\bLass\b/g, "Lassen Sie"], [/\bSag uns\b/g, "Sagen Sie uns"],
    [/\bglaubst\b/g, "glauben"], [/\bmöchtest\b/g, "möchten"], [/\bbehältst\b/g, "behalten"], [/\breist\b/g, "reisen"], [/\bfragst\b/g, "fragen"],
  ];
  return map.reduce((acc, [re, rep]) => acc.replace(re, rep), s);
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [form, setFormState] = useState<Form>((brand.default_address_form as Form) || "du");
  const [locale, setLocaleState] = useState<Locale>("de");
  useEffect(() => {
    try {
      const f = localStorage.getItem("fp_form") as Form | null;
      const l = localStorage.getItem("fp_locale") as Locale | null;
      if (f) setFormState(f);
      if (l) setLocaleState(l);
    } catch { /* storage unavailable */ }
  }, []);
  const setForm = useCallback((f: Form) => { setFormState(f); try { localStorage.setItem("fp_form", f); } catch {} }, []);
  const setLocale = useCallback((l: Locale) => { setLocaleState(l); try { localStorage.setItem("fp_locale", l); } catch {} ; document.documentElement.lang = l; }, []);
  const value = useMemo<Ctx>(() => ({ t: (k, v) => translate(k, locale, form, v), locale, form, setForm, setLocale }), [locale, form, setForm, setLocale]);
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

export function useT() {
  const c = useContext(I18n);
  if (!c) return { t: (k: string, v?: Record<string, string | number>) => translate(k, "de", "du", v), locale: "de" as Locale, form: "du" as Form, setForm: () => {}, setLocale: () => {} };
  return c;
}

export function errText(t: Ctx["t"], code?: string) {
  if (!code) return t("err.generic");
  const k = `err.${code}`;
  const s = t(k);
  return s === k ? t("err.generic") : s;
}
