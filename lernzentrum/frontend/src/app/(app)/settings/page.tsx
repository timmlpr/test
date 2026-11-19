"use client";
// Settings: connections health, API keys, timetable, Moodle, inbox channels, live-mode behaviour, quotas,
// appearance, privacy (export / delete-all), legal notes.
import { Activity, BookOpen, CalendarDays, Download, LogOut, RefreshCw, Shield, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { CalendarConnect, KeyField, MoodleConnect, type SecretInfo } from "@/components/connect";
import { useApp } from "@/components/providers";
import { Button, Card, CardTitle, Input, Label, Notice, Progress, Select, StatusDot, Toggle } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { passkeySupported, registerPasskey } from "@/lib/passkey";

interface Conn { key: string; label: string; status: string; detail: string; checked_at: string | null }
interface Quota { provider: string; metric: string; used: number; limit: number; reset_in_s: number; exhausted: boolean }
interface Cal { id: number; name: string; kind: string; url_hint: string; last_sync: string | null; last_status: string }

const PROVIDER_LABEL: Record<string, string> = { groq_stt: "Groq Whisper", gemini_lite: "Gemini Flash-Lite", gemini_flash: "Gemini Flash", gemini_embed: "Gemini Embeddings" };
const METRIC_LABEL: Record<string, string> = { rpm: "Anfragen/Min.", rpd: "Anfragen/Tag", audio_s_hour: "Audio-Sek./Std.", audio_s_day: "Audio-Sek./Tag" };

export default function SettingsPage() {
  const { user, reloadUser, toast, theme, setTheme, largeType, setLargeType, setUser } = useApp();
  const router = useRouter();
  const [conns, setConns] = useState<Conn[]>([]);
  const [secrets, setSecrets] = useState<SecretInfo[]>([]);
  const [quota, setQuota] = useState<Quota[]>([]);
  const [cals, setCals] = useState<Cal[]>([]);
  const [names, setNames] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [imap, setImap] = useState({ host: "", port: "993", username: "", folder: "INBOX", password: "" });
  const [dav, setDav] = useState({ url: "", username: "", password: "" });
  const [del, setDel] = useState({ password: "", confirm: "" });

  const load = useCallback(() => {
    api.get<Conn[]>("/health/connections").then(setConns);
    api.get<SecretInfo[]>("/secrets").then(setSecrets);
    api.get<Quota[]>("/quota").then(setQuota);
    api.get<Cal[]>("/calendars").then(setCals);
  }, []);
  useEffect(() => {
    load();
    setNames((user?.settings.call_names || []).join(", "));
  }, [load, user]);

  const saveSetting = async (patch: Record<string, unknown>) => {
    await api.patch("/settings", patch);
    await reloadUser();
    toast("Gespeichert", "ok");
  };
  const secret = (p: string) => secrets.find((s) => s.provider === p);
  const origin = typeof window !== "undefined" ? window.location.origin : "";

  return (
    <>
      <PageHeader title="Einstellungen" />
      <div className="mb-4 flex flex-wrap gap-2 lg:hidden">
        <Link href="/library"><Button variant="outline"><BookOpen className="h-4 w-4" /> Bibliothek</Button></Link>
        <Link href="/calendar"><Button variant="outline"><CalendarDays className="h-4 w-4" /> Kalender</Button></Link>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="lg:col-span-2">
          <CardTitle action={<Button size="sm" variant="ghost" onClick={load}><RefreshCw className="h-4 w-4" /> Prüfen</Button>}>
            <span className="flex items-center gap-2"><Activity className="h-5 w-5" /> Verbindungen</span>
          </CardTitle>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {conns.map((c) => (
              <li key={c.key} className="rounded-xl border border-border p-3">
                <div className="flex items-center justify-between gap-2"><span className="font-medium">{c.label}</span><StatusDot status={c.status} /></div>
                <p className="mt-1 text-sm text-muted">{c.detail}</p>
                {c.checked_at && <p className="text-xs text-muted">geprüft {fmtDateTime(c.checked_at + (c.checked_at.endsWith("Z") ? "" : "Z"))}</p>}
              </li>
            ))}
          </ul>
        </Card>

        <div className="space-y-4">
          <KeyField provider="groq" info={secret("groq")} onChange={load} />
          <KeyField provider="gemini" info={secret("gemini")} onChange={load} />
        </div>

        <div className="space-y-4">
          <Card>
            <CardTitle>Stundenplan</CardTitle>
            <ul className="mb-3 space-y-2">
              {cals.map((c) => (
                <li key={c.id} className="flex items-center gap-2 text-sm">
                  <span className="flex-1"><b>{c.name}</b> {c.kind === "moodle" && "(Moodle)"} <span className="text-muted">· {c.last_status || "–"}</span></span>
                  <Button size="sm" variant="ghost" onClick={() => api.post(`/calendars/${c.id}/sync`).then(() => { toast("Abgeglichen", "ok"); load(); }).catch((e) => toast(e.message, "error"))}>Sync</Button>
                  <Button size="sm" variant="ghost" onClick={() => api.del(`/calendars/${c.id}`).then(load)} aria-label="Kalender entfernen"><Trash2 className="h-4 w-4" /></Button>
                </li>
              ))}
            </ul>
            <CalendarConnect onAdded={load} />
          </Card>
          <Card>
            <CardTitle>Moodle</CardTitle>
            <MoodleConnect onLinked={load} />
          </Card>
        </div>

        <Card id="inbox" className="space-y-4">
          <CardTitle>Eingang</CardTitle>
          <div>
            <p className="font-medium">iPad/iPhone: Teilen-Menü</p>
            <p className="mb-2 text-sm text-muted">
              Safari unterstützt keine Web-App-Teilenziele. Erzeuge einen persönlichen Upload-Link und lege in der Kurzbefehle-App einen Kurzbefehl an:
              „Inhalte von URL abrufen“ → Methode POST → Formular → Feld <code>file</code> = Kurzbefehl-Eingabe → im Teilen-Blatt anzeigen. Danach erscheint „An Lernzentrum senden“ in GoodNotes, Dateien, Mail und Safari.
            </p>
            {token ? (
              <Notice tone="ok"><p className="break-all font-mono text-xs">{origin}/api/inbox/drop/{token}</p><p className="mt-1 text-xs">Nur jetzt sichtbar. Gleicher Link funktioniert als E-Mail-Webhook: …/api/inbox/mail/{"{token}"}</p></Notice>
            ) : (
              <Button variant="outline" onClick={() => api.post<{ token: string }>("/inbox/upload-token").then((r) => setToken(r.token))}>Upload-Link erzeugen</Button>
            )}
          </div>
          <div>
            <p className="mb-1 flex items-center justify-between font-medium">E-Mail-Postfach (IMAP) <StatusDot status={secret("imap")?.status || "missing"} /></p>
            <p className="mb-2 text-sm text-muted">Lege z. B. ein eigenes Postfach an und leite Mails mit Anhängen dorthin weiter. Nutze ein App-Passwort.</p>
            <div className="grid grid-cols-2 gap-2">
              <Input placeholder="imap.gmx.net" value={imap.host} onChange={(e) => setImap({ ...imap, host: e.target.value })} aria-label="IMAP-Server" />
              <Input placeholder="Benutzername" value={imap.username} onChange={(e) => setImap({ ...imap, username: e.target.value })} aria-label="IMAP-Benutzer" />
              <Input type="password" placeholder="App-Passwort" value={imap.password} onChange={(e) => setImap({ ...imap, password: e.target.value })} aria-label="IMAP-Passwort" />
              <Button variant="outline" disabled={!imap.host || !imap.username || !imap.password} onClick={() => api.put("/secrets/imap", { value: imap.password, meta: { host: imap.host, port: imap.port, username: imap.username, folder: imap.folder } }).then(() => { toast("Postfach gespeichert", "ok"); setImap({ ...imap, password: "" }); load(); }).catch((e) => toast(e.message, "error"))}>Verbinden</Button>
            </div>
          </div>
          <div>
            <p className="mb-1 flex items-center justify-between font-medium">Cloud-Ordner (WebDAV) <StatusDot status={secret("webdav")?.status || "missing"} /></p>
            <p className="mb-2 text-sm text-muted">z. B. Nextcloud-Ordner. iCloud hat keine öffentliche Schnittstelle; Google Drive/OneDrive brauchen eine eigene App-Registrierung (siehe ADAPTERS.md).</p>
            <div className="grid grid-cols-2 gap-2">
              <Input className="col-span-2" placeholder="https://cloud…/remote.php/dav/files/USER/Uni" value={dav.url} onChange={(e) => setDav({ ...dav, url: e.target.value })} aria-label="WebDAV-URL" />
              <Input placeholder="Benutzername" value={dav.username} onChange={(e) => setDav({ ...dav, username: e.target.value })} aria-label="WebDAV-Benutzer" />
              <Input type="password" placeholder="App-Passwort" value={dav.password} onChange={(e) => setDav({ ...dav, password: e.target.value })} aria-label="WebDAV-Passwort" />
              <Button variant="outline" className="col-span-2" disabled={!dav.url || !dav.username || !dav.password} onClick={() => api.put("/secrets/webdav", { value: dav.password, meta: { url: dav.url, username: dav.username } }).then(() => { toast("Ordner verbunden", "ok"); setDav({ ...dav, password: "" }); load(); }).catch((e) => toast(e.message, "error"))}>Verbinden</Button>
            </div>
          </div>
        </Card>

        <Card className="space-y-2">
          <CardTitle>Live-Modus</CardTitle>
          <Toggle checked={user?.settings.consent_reminder !== false} onChange={(v) => saveSetting({ consent_reminder: v })} label="Einwilligungs-Erinnerung" description="Vor jeder Aufnahme bestätigen, dass alle Anwesenden zustimmen (empfohlen)." />
          <Toggle checked={user?.settings.keep_audio !== false} onChange={(v) => saveSetting({ keep_audio: v })} label="Audio speichern" description="Aus: Audio wird nach der Transkription gelöscht." />
          <div>
            <Label>Standard-Antwortlänge</Label>
            <Select value={user?.settings.answer_mode || "short"} onChange={(e) => saveSetting({ answer_mode: e.target.value })}>
              <option value="short">Kurz (2–3 sprechbare Zeilen)</option>
              <option value="detailed">Ausführlich</option>
            </Select>
          </div>
          <div>
            <Label hint="kommagetrennt">Wie spricht dich der Dozent an?</Label>
            <div className="flex gap-2">
              <Input value={names} onChange={(e) => setNames(e.target.value)} placeholder="Herr Muster, Tim" />
              <Button variant="outline" onClick={() => saveSetting({ call_names: names.split(",").map((s) => s.trim()).filter(Boolean) })}>Speichern</Button>
            </div>
          </div>
          <p className="text-sm text-muted">Prüfungsmodus wird pro Modul in den Moduleinstellungen geschaltet.</p>
        </Card>

        <Card>
          <CardTitle>Kostenlose Kontingente (heute)</CardTitle>
          <ul className="space-y-2">
            {quota.filter((q) => q.metric !== "rpm").map((q) => (
              <li key={`${q.provider}-${q.metric}`} className="text-sm">
                <div className="flex justify-between"><span>{PROVIDER_LABEL[q.provider]} · {METRIC_LABEL[q.metric]}</span><span className={q.exhausted ? "font-semibold text-unsicher" : "text-muted"}>{q.used} / {q.limit}</span></div>
                <Progress value={q.used / q.limit} color={q.exhausted ? "var(--unsicher)" : undefined} />
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted">Grenzen: Groq laut offizieller Tabelle; Gemini veröffentlicht keine festen Free-Tier-Werte – beobachtete Werte, anpassbar. Ist ein Kontingent erschöpft, nimmt Lernzentrum weiter auf und arbeitet später nach.</p>
        </Card>

        <Card className="space-y-2">
          <CardTitle>Darstellung & Konto</CardTitle>
          <div>
            <Label>Farbschema</Label>
            <Select value={theme} onChange={(e) => setTheme(e.target.value as "system" | "light" | "dark")}>
              <option value="system">Wie System</option><option value="light">Hell</option><option value="dark">Dunkel</option>
            </Select>
          </div>
          <Toggle checked={largeType} onChange={setLargeType} label="Große Schrift" />
          {passkeySupported() && <Button variant="outline" onClick={() => registerPasskey().then(() => toast("Passkey gespeichert", "ok")).catch((e) => toast(e.message, "error"))}>Face ID / Passkey hinzufügen</Button>}
          <Button variant="ghost" onClick={async () => { await api.post("/auth/logout"); setUser(null); router.replace("/login"); }}><LogOut className="h-4 w-4" /> Abmelden</Button>
        </Card>

        <Card className="space-y-3">
          <CardTitle><span className="flex items-center gap-2"><Shield className="h-5 w-5" /> Datenschutz</span></CardTitle>
          <p className="text-sm text-muted">Deine Daten liegen verschlüsselt auf einem Server in Deutschland. Keine Analyse-Tools. An Groq/Gemini gehen nur die nötigen Audio- bzw. Textausschnitte.</p>
          <a href="/api/export"><Button variant="outline"><Download className="h-4 w-4" /> Alle Daten exportieren</Button></a>
          <details className="rounded-xl border border-unsicher/40 p-3">
            <summary className="cursor-pointer font-medium text-unsicher">Alles löschen</summary>
            <p className="my-2 text-sm">Löscht Konto, Dateien, Aufnahmen, Schlüssel unwiderruflich.</p>
            <div className="grid gap-2">
              <Input type="password" placeholder="Passwort" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} />
              <Input placeholder="LÖSCHEN eintippen" value={del.confirm} onChange={(e) => setDel({ ...del, confirm: e.target.value })} />
              <Button variant="danger" disabled={del.confirm !== "LÖSCHEN"} onClick={() => api.post("/delete-all", del).then(() => router.replace("/login")).catch((e) => toast(e.message, "error"))}><Trash2 className="h-4 w-4" /> Endgültig löschen</Button>
            </div>
          </details>
          <Notice>Aufnahmen nur mit Einverständnis von Lehrperson und Anwesenden. Lernzentrum darf in Prüfungen nicht verwendet werden.</Notice>
        </Card>
      </div>
    </>
  );
}
