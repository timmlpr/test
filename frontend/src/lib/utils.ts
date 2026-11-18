import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtDate(v?: string | null, withTime = false) {
  if (!v) return "–";
  const d = new Date(v.endsWith("Z") || v.includes("+") ? v : v + "Z");
  if (Number.isNaN(d.getTime())) return "–";
  return withTime ? d.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" }) : d.toLocaleDateString("de-DE", { dateStyle: "medium" });
}

export function eur(v: number) {
  return v.toLocaleString("de-DE", { style: "currency", currency: "EUR" });
}
