// German formatting helpers.

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

export function fmtDate(iso: string | null | undefined, withWeekday = false): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("de-DE", {
    weekday: withWeekday ? "short" : undefined,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return `${fmtDate(iso, true)}, ${fmtTime(iso)}`;
}

export function fmtDuration(seconds: number | null | undefined): string {
  const s = Math.max(0, Math.round(seconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function relDays(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const day = new Date(d);
  day.setHours(0, 0, 0, 0);
  const diff = Math.round((day.getTime() - today.getTime()) / 86400000);
  if (diff === 0) return "heute";
  if (diff === 1) return "morgen";
  if (diff === -1) return "gestern";
  if (diff > 1 && diff < 7) return `in ${diff} Tagen`;
  if (diff < 0) return `vor ${-diff} Tagen`;
  return fmtDate(iso);
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export const KIND_LABEL: Record<string, string> = {
  slides: "Folien",
  script: "Skript",
  exercise: "Übung",
  notes: "Notizen",
  transcript: "Transkript",
  audio: "Aufnahme",
  photo: "Foto",
  other: "Dokument",
};

export const CHANNEL_LABEL: Record<string, string> = {
  upload: "Hochgeladen",
  share: "Geteilt",
  mail: "E-Mail",
  webdav: "Cloud-Ordner",
  moodle: "Moodle",
  import: "Import",
  demo: "Demo",
};
