"use client";
// Connection widgets shared by the setup wizard and the settings page:
// API key fields with TEST button, calendar link with preview, Moodle connect (auto-detected path), upload zone.
import { CheckCircle2, ExternalLink, KeyRound, Link2, UploadCloud, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useApp } from "./providers";
import { Button, Card, cn, Input, Label, Notice, Progress, StatusDot } from "./ui";

export interface SecretInfo {
  provider: string;
  label: string;
  url: string;
  configured: boolean;
  status: string;
  hint: string;
  detail: string;
  meta?: Record<string, unknown>;
}

const KEY_HELP: Record<string, { what: string; steps: string; placeholder: string }> = {
  groq: {
    what: "Spracherkennung (Whisper) für Live-Transkript und den Import alter Sprachmemos.",
    steps: "Bei console.groq.com anmelden → „API Keys“ → „Create API Key“ → Key kopieren.",
    placeholder: "gsk_…",
  },
  gemini: {
    what: "Formulierte Antworten, Zusammenfassungen, Karteikarten und Handschrift-Erkennung.",
    steps: "In Google AI Studio anmelden → „Get API key“ → „Create API key“ → Key kopieren.",
    placeholder: "AIza…",
  },
};

export function KeyField({ provider, info, onChange }: { provider: "groq" | "gemini"; info?: SecretInfo; onChange?: () => void }) {
  const { toast } = useApp();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const help = KEY_HELP[provider];

  const save = async () => {
    setBusy(true);
    setResult(null);
    try {
      const r = await api.put<SecretInfo>(`/secrets/${provider}`, { value });
      setValue("");
      setResult({ ok: r.status === "ok", message: r.detail || (r.status === "ok" ? "Verbunden." : "Test fehlgeschlagen.") });
      onChange?.();
    } catch (e) {
      setResult({ ok: false, message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  const test = async () => {
    setBusy(true);
    try {
      setResult(await api.post<{ ok: boolean; message: string }>(`/secrets/${provider}/test`));
      onChange?.();
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    await api.del(`/secrets/${provider}`);
    toast("Key gelöscht", "ok");
    setResult(null);
    onChange?.();
  };

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold"><KeyRound className="h-5 w-5 text-primary" /> {info?.label || provider}</p>
        <StatusDot status={info?.status || "missing"} />
      </div>
      <p className="text-sm text-muted">{help.what}</p>
      <p className="text-sm">{help.steps}{" "}
        {info?.url && (
          <a href={info.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-primary underline">
            Key holen <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </p>
      {info?.configured && <p className="text-sm">Gespeichert: <code className="rounded bg-surface-2 px-1.5">{info.hint}</code></p>}
      <div className="flex flex-wrap gap-2">
        <Input className="min-w-[200px] flex-1" type="password" autoComplete="off" placeholder={info?.configured ? "Neuen Key einfügen …" : help.placeholder} value={value} onChange={(e) => setValue(e.target.value)} aria-label={`${provider} API-Key`} />
        <Button onClick={save} disabled={value.trim().length < 8} loading={busy}>Speichern & testen</Button>
        {info?.configured && <Button variant="outline" onClick={test} loading={busy}>Testen</Button>}
        {info?.configured && <Button variant="ghost" onClick={remove}>Entfernen</Button>}
      </div>
      {result && (
        <p className={cn("flex items-center gap-1.5 text-sm font-medium", result.ok ? "text-sicher" : "text-unsicher")}>
          {result.ok ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />} {result.message}
        </p>
      )}
      <p className="text-xs text-muted">Der Key wird verschlüsselt auf dem Server gespeichert und nie wieder vollständig angezeigt.</p>
    </Card>
  );
}

export function CalendarConnect({ onAdded }: { onAdded?: () => void }) {
  const { toast } = useApp();
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState<{ ok: boolean; message?: string; events: { title: string; start: string; location: string }[] } | null>(null);
  const [busy, setBusy] = useState(false);

  const test = async () => {
    setBusy(true);
    try {
      setPreview(await api.get(`/calendars/preview?url=${encodeURIComponent(url)}`));
    } finally {
      setBusy(false);
    }
  };
  const add = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ events: number }>("/calendars", { url, name: "Stundenplan" });
      toast(`Kalender verbunden: ${r.events} Termine`, "ok");
      setUrl("");
      setPreview(null);
      onAdded?.();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">
        iPad/iPhone: Kalender-App → Kalender → (i) neben dem Stundenplan → „Öffentlicher Kalender“ → Link teilen. Oder den
        Abo-Link (webcal://…) aus dem THM-Stundenplan kopieren.
      </p>
      <div className="flex flex-wrap gap-2">
        <Input className="min-w-[220px] flex-1" placeholder="webcal://… oder https://….ics" value={url} onChange={(e) => setUrl(e.target.value)} aria-label="Kalender-Link" />
        <Button variant="outline" onClick={test} disabled={!url} loading={busy}>Testen</Button>
        <Button onClick={add} disabled={!url || (preview !== null && !preview.ok)} loading={busy}><Link2 className="h-4 w-4" /> Verbinden</Button>
      </div>
      {preview && (preview.ok ? (
        <Notice tone="ok">
          <p className="mb-1 font-medium">Nächste Termine:</p>
          <ul>{preview.events.map((e, i) => <li key={i}>{fmtDateTime(e.start)} – {e.title}{e.location ? ` (${e.location})` : ""}</li>)}</ul>
          {preview.events.length === 0 && <p>Keine Termine in den nächsten 60 Tagen.</p>}
        </Notice>
      ) : <Notice tone="error">{preview.message}</Notice>)}
    </div>
  );
}

interface Detect { site: string; method: "password" | "sso" | "ics"; sitename: string; explain: string; launch_url?: string; keys_url?: string }

export function MoodleConnect({ onLinked }: { onLinked?: () => void }) {
  const { toast } = useApp();
  const [site, setSite] = useState("https://moodle.thm.de");
  const [det, setDet] = useState<Detect | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [ics, setIcs] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ linked: boolean; sitename?: string; fullname?: string; last_sync?: string; status?: string; detail?: string } | null>(null);

  const load = useCallback(() => api.get<typeof status>("/moodle/status").then(setStatus), []);
  useEffect(() => {
    load();
  }, [load]);

  const detect = async () => {
    setBusy(true);
    try {
      setDet(await api.post<Detect>("/moodle/detect", { site }));
    } finally {
      setBusy(false);
    }
  };
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      toast(ok, "ok");
      setPassword("");
      setToken("");
      await load();
      onLinked?.();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
      setPassword("");
    }
  };

  if (status?.linked) {
    return (
      <div className="space-y-3">
        <Notice tone={status.status === "error" ? "error" : "ok"}>
          Verbunden mit <b>{status.sitename}</b> als {status.fullname}. {status.last_sync ? `Letzter Abgleich: ${fmtDateTime(status.last_sync)}` : "Erster Abgleich läuft …"}
          {status.status === "error" && <> – {status.detail}</>}
        </Notice>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => run(() => api.post("/moodle/sync"), "Abgleich gestartet")} loading={busy}>Jetzt abgleichen</Button>
          <Button variant="ghost" onClick={() => run(() => api.del("/moodle/link"), "Moodle getrennt – Token gelöscht")}>Trennen</Button>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Input className="min-w-[220px] flex-1" value={site} onChange={(e) => setSite(e.target.value)} aria-label="Moodle-Adresse" />
        <Button variant="outline" onClick={detect} loading={busy}>Prüfen</Button>
      </div>
      {det && <Notice>{det.sitename ? <b>{det.sitename}: </b> : null}{det.explain}</Notice>}
      {det?.method === "password" && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run(() => api.post("/moodle/link/password", { site: det.site, username, password }), "Moodle verbunden"); }}>
          <div className="grid gap-2 sm:grid-cols-2">
            <div><Label>Moodle-Benutzername</Label><Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" /></div>
            <div><Label>Passwort</Label><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" /></div>
          </div>
          <Button type="submit" loading={busy} disabled={!username || !password}>Verbinden</Button>
          <p className="text-xs text-muted">Das Passwort wird nur einmal an Moodle geschickt, um einen Zugangs-Token zu erhalten, und danach verworfen. Gespeichert wird nur der Token (verschlüsselt).</p>
        </form>
      )}
      {det?.method === "sso" && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {det.launch_url && <a className="inline-flex h-11 items-center rounded-xl border border-border px-4 font-medium" href={det.launch_url} target="_blank" rel="noreferrer">1. Bei Moodle anmelden</a>}
            {det.keys_url && <a className="inline-flex h-11 items-center rounded-xl border border-border px-4 font-medium" href={det.keys_url} target="_blank" rel="noreferrer">2. Sicherheitsschlüssel öffnen</a>}
          </div>
          <Input placeholder="Schlüssel „Moodle mobile web service“ oder moodlemobile://token=…" value={token} onChange={(e) => setToken(e.target.value)} />
          <Button onClick={() => run(() => api.post("/moodle/link/token", { site: det.site, token }), "Moodle verbunden")} disabled={!token} loading={busy}>Verbinden</Button>
        </div>
      )}
      {det && (
        <details className="rounded-xl border border-border p-3" open={det.method === "ics"}>
          <summary className="cursor-pointer font-medium">Alternative: Moodle-Kalender (ICS) verbinden</summary>
          <p className="my-2 text-sm text-muted">Moodle → Kalender → „Kalender exportieren“ → „Alle Kurse“ → „Kalender-URL abrufen“ → Link kopieren. Dateien lädst du dann im Eingang hoch.</p>
          <div className="flex gap-2">
            <Input value={ics} onChange={(e) => setIcs(e.target.value)} placeholder="https://moodle…/calendar/export_execute.php?…" />
            <Button onClick={() => run(() => api.post("/moodle/link/ics", { url: ics }), "Moodle-Kalender verbunden")} disabled={!ics} loading={busy}>Verbinden</Button>
          </div>
        </details>
      )}
    </div>
  );
}

export function UploadZone({ moduleId, channel = "upload", accept, label, onDone }: { moduleId?: number; channel?: string; accept?: string; label?: string; onDone?: (batch: string) => void }) {
  const { toast } = useApp();
  const ref = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    // upload in batches of 5 so very large imports show progress and stay within request limits
    let batch = "";
    for (let i = 0; i < list.length; i += 5) {
      const part = list.slice(i, i + 5);
      const fd = new FormData();
      part.forEach((f) => fd.append("files", f));
      fd.append("last_modified", part.map((f) => f.lastModified).join(","));
      fd.append("channel", channel);
      if (moduleId) fd.append("module_id", String(moduleId));
      setProgress(i / list.length);
      try {
        const r = await api.form<{ batch: string }>("/documents/upload", fd);
        batch = batch || r.batch;
      } catch (e) {
        toast((e as Error).message, "error");
      }
    }
    setProgress(null);
    toast(`${list.length} Datei(en) im Eingang – werden sortiert`, "ok");
    onDone?.(batch);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files); }}
      className={cn("flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed p-6 text-center transition-colors", drag ? "border-primary bg-primary/5" : "border-border")}
    >
      <UploadCloud className="h-8 w-8 text-primary" />
      <p className="font-medium">{label || "Dateien hierher ziehen oder auswählen"}</p>
      <p className="text-sm text-muted">PDF, GoodNotes-Export, Word, PowerPoint, Fotos, Sprachmemos (m4a, mp3, wav) – auch viele auf einmal</p>
      <input ref={ref} type="file" multiple accept={accept} className="hidden" onChange={(e) => e.target.files && upload(e.target.files)} />
      <Button onClick={() => ref.current?.click()} variant="secondary">Dateien auswählen</Button>
      {progress !== null && <Progress value={progress} className="mt-2 max-w-xs" />}
    </div>
  );
}
