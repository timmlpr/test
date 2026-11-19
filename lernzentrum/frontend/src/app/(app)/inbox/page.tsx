"use client";
// Inbox: intake (upload / share / mail / cloud), automatic sorting with confidence, review list for low-confidence
// items and unmatched timetable events, duplicates, and the import queue with progress.
import { CalendarX, Copy, FileText, Loader2, Mic, Share2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { UploadZone } from "@/components/connect";
import { useApp } from "@/components/providers";
import { Badge, Button, Card, CardTitle, Empty, ModuleChip, Notice, Progress, Select, Tabs } from "@/components/ui";
import { api } from "@/lib/api";
import { CHANNEL_LABEL, fmtDate, fmtDateTime, KIND_LABEL } from "@/lib/format";
import type { Doc, Job, Module } from "@/lib/types";

interface Item { id: number; status: string; channel: string; note: string; suggestion: { module_id?: number; module_confidence?: number; reason?: string; module_reason?: string; date?: string; date_source?: string; lecture_id?: number }; created_at: string; document: Doc }
interface Review { items: Item[]; events: { event_id: number; title: string; count: number; next: string; location: string; score: number }[]; lectures: { id: number; module_id: number; title: string; start: string }[] }
type Tab = "all" | "review" | "duplicates" | "queue";

function InboxInner() {
  const search = useSearchParams();
  const { toast } = useApp();
  const [tab, setTab] = useState<Tab>((search.get("tab") as Tab) || "all");
  const [items, setItems] = useState<Item[]>([]);
  const [review, setReview] = useState<Review | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [mods, setMods] = useState<Module[]>([]);
  const [choice, setChoice] = useState<Record<number, { module_id?: number; lecture_id?: number }>>({});

  const load = useCallback(() => {
    api.get<Item[]>("/inbox").then(setItems);
    api.get<Review>("/review").then(setReview);
    api.get<Job[]>("/jobs").then(setJobs);
  }, []);
  useEffect(() => {
    load();
    api.get<Module[]>("/modules").then(setMods);
  }, [load]);
  useEffect(() => {
    const active = jobs.some((j) => ["queued", "running"].includes(j.status));
    if (!active) return;
    const t = setTimeout(load, 2500);
    return () => clearTimeout(t);
  }, [jobs, load]);
  useEffect(() => {
    const shared = search.get("shared");
    if (shared) toast(`${shared} geteilte Datei(en) empfangen`, "ok");
  }, [search, toast]);

  const modById = Object.fromEntries(mods.map((m) => [m.id, m]));
  const confirm = async (it: Item) => {
    const c = choice[it.id] || {};
    const module_id = c.module_id ?? it.suggestion.module_id;
    if (!module_id) return toast("Bitte Modul wählen", "error");
    await api.post(`/inbox/${it.id}/confirm`, { module_id, lecture_id: c.lecture_id ?? it.suggestion.lecture_id ?? null });
    toast("Zugeordnet", "ok");
    load();
  };
  const dismiss = async (it: Item) => {
    await api.post(`/inbox/${it.id}/dismiss`);
    load();
  };
  const matchEvent = async (eventId: number, moduleId: number | null) => {
    await api.post(`/events/${eventId}/module`, { module_id: moduleId });
    toast(moduleId ? "Termin-Serie zugeordnet" : "Als „kein Modul“ markiert", "ok");
    load();
  };

  const reviewCount = (review?.items.length || 0) + (review?.events.length || 0);
  const dups = items.filter((i) => i.status === "duplicate");
  const active = jobs.filter((j) => j.status !== "done");

  return (
    <>
      <PageHeader title="Eingang" subtitle="Alles landet hier, wird automatisch sortiert, benannt und durchsuchbar." />
      <div className="mb-4 grid gap-4 lg:grid-cols-[1fr_320px]">
        <UploadZone onDone={() => setTimeout(load, 800)} />
        <Card className="space-y-2 text-sm">
          <p className="flex items-center gap-2 font-semibold"><Share2 className="h-4 w-4" /> Weitere Wege in den Eingang</p>
          <p>• <b>iPad Teilen-Menü:</b> Kurzbefehl „An Lernzentrum senden“ (Einstellungen → Eingang).</p>
          <p>• <b>E-Mail:</b> Postfach verbinden – Anhänge werden importiert.</p>
          <p>• <b>Cloud-Ordner:</b> WebDAV (z. B. Nextcloud) wird regelmäßig abgeglichen.</p>
          <p>• <b>Moodle:</b> Kursdateien kommen automatisch.</p>
          <Link href="/settings#inbox" className="font-medium text-primary">Einrichten →</Link>
        </Card>
      </div>
      <Tabs<Tab> className="mb-4" value={tab} onChange={setTab} tabs={[
        { id: "all", label: "Alle", count: items.length }, { id: "review", label: "Bitte prüfen", count: reviewCount },
        { id: "duplicates", label: "Duplikate", count: dups.length }, { id: "queue", label: "Verarbeitung", count: active.length },
      ]} />

      {tab === "all" && (
        <Card>
          {items.length === 0 ? <Empty title="Eingang ist leer" /> : (
            <ul className="divide-y divide-border">
              {items.map((it) => (
                <li key={it.id} className="flex items-center gap-3 py-2.5">
                  {it.document.kind === "audio" ? <Mic className="h-5 w-5 text-muted" /> : <FileText className="h-5 w-5 text-muted" />}
                  <ModuleChip short={it.document.module_id ? modById[it.document.module_id]?.short : null} color={it.document.module_id ? modById[it.document.module_id]?.color : null} />
                  <Link href={`/library/${it.document.id}`} className="min-w-0 flex-1">
                    <p className="truncate font-medium">{it.document.title}</p>
                    <p className="truncate text-xs text-muted">{it.document.original_name} · {CHANNEL_LABEL[it.channel] || it.channel} · {fmtDateTime(it.created_at + "Z")}{it.note ? ` · ${it.note}` : ""}</p>
                  </Link>
                  <Badge>{KIND_LABEL[it.document.kind] || it.document.kind}</Badge>
                  {it.status === "processing" ? <Loader2 className="h-4 w-4 animate-spin text-muted" /> :
                    it.status === "review" ? <Badge color="var(--pruefen)">prüfen</Badge> :
                      it.status === "duplicate" ? <Badge>Duplikat</Badge> :
                        <Badge color="var(--sicher)">{Math.round((it.document.confidence || 1) * 100)} %</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === "review" && review && (
        <div className="space-y-4">
          {reviewCount === 0 && <Card><Empty title="Nichts zu prüfen">Alle Dateien und Termine sind sicher zugeordnet.</Empty></Card>}
          {review.items.map((it) => {
            const sel = choice[it.id]?.module_id ?? it.suggestion.module_id;
            const lectures = review.lectures.filter((l) => !sel || l.module_id === sel);
            return (
              <Card key={it.id} className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  {it.document.kind === "audio" ? <Mic className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
                  <p className="mr-auto font-semibold">{it.document.original_name}</p>
                  <Badge color="var(--pruefen)">{Math.round((it.suggestion.module_confidence || 0) * 100)} % sicher</Badge>
                </div>
                <p className="text-sm text-muted">
                  {it.document.review_reason || it.suggestion.reason}
                  {it.suggestion.date && ` · Datum ${fmtDate(it.suggestion.date)}${it.suggestion.date_source ? ` (aus ${it.suggestion.date_source})` : ""}`}
                </p>
                <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto_auto]">
                  <Select value={sel ?? ""} onChange={(e) => setChoice({ ...choice, [it.id]: { ...choice[it.id], module_id: Number(e.target.value) || undefined } })} aria-label="Modul">
                    <option value="">Modul wählen …</option>
                    {mods.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </Select>
                  {it.document.kind === "audio" ? (
                    <Select value={choice[it.id]?.lecture_id ?? it.suggestion.lecture_id ?? ""} onChange={(e) => setChoice({ ...choice, [it.id]: { ...choice[it.id], lecture_id: Number(e.target.value) || undefined } })} aria-label="Vorlesung">
                      <option value="">Vorlesung (optional)</option>
                      {lectures.slice(0, 60).map((l) => <option key={l.id} value={l.id}>{fmtDateTime(l.start)} – {modById[l.module_id]?.short}</option>)}
                    </Select>
                  ) : <span />}
                  <Button onClick={() => confirm(it)}>Bestätigen</Button>
                  <Button variant="ghost" onClick={() => dismiss(it)}>Verwerfen</Button>
                </div>
              </Card>
            );
          })}
          {review.events.length > 0 && (
            <Card>
              <CardTitle><span className="flex items-center gap-2"><CalendarX className="h-5 w-5" /> Termine ohne Modul</span></CardTitle>
              <ul className="divide-y divide-border">
                {review.events.map((e) => (
                  <li key={e.event_id} className="flex flex-wrap items-center gap-2 py-2.5">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{e.title}</p>
                      <p className="text-xs text-muted">{e.count}× · nächster {fmtDateTime(e.next)} {e.location && `· ${e.location}`}</p>
                    </div>
                    <Select className="w-56" defaultValue="" onChange={(ev) => ev.target.value && matchEvent(e.event_id, ev.target.value === "none" ? null : Number(ev.target.value))} aria-label={`Modul für ${e.title}`}>
                      <option value="">Zuordnen …</option>
                      {mods.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                      <option value="none">Kein Modul (ignorieren)</option>
                    </Select>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}

      {tab === "duplicates" && (
        <Card>
          {dups.length === 0 ? <Empty icon={<Copy />} title="Keine Duplikate" /> : (
            <ul className="divide-y divide-border">
              {dups.map((it) => (
                <li key={it.id} className="flex items-center gap-3 py-2.5">
                  <span className="min-w-0 flex-1 truncate">{it.document.original_name} <span className="text-sm text-muted">– {it.note}</span></span>
                  <Button size="sm" variant="outline" onClick={() => dismiss(it)}>Entfernen</Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === "queue" && (
        <Card>
          {jobs.length === 0 ? <Empty title="Keine laufenden Aufgaben" /> : (
            <ul className="space-y-3">
              {jobs.map((j) => (
                <li key={j.id}>
                  <div className="mb-1 flex items-center gap-2 text-sm">
                    <span className="flex-1 truncate">{j.label || j.kind}</span>
                    <Badge color={j.status === "error" ? "var(--unsicher)" : j.status === "waiting" ? "var(--pruefen)" : j.status === "done" ? "var(--sicher)" : undefined}>
                      {{ queued: "wartet", running: "läuft", done: "fertig", error: "Fehler", waiting: "pausiert" }[j.status] || j.status}
                    </Badge>
                    {(j.status === "error" || j.status === "waiting") && <Button size="sm" variant="ghost" onClick={() => api.post(`/jobs/${j.id}/retry`).then(load)}>Erneut</Button>}
                  </div>
                  <Progress value={j.status === "done" ? 1 : j.progress} />
                  {j.error && <Notice tone={j.status === "error" ? "error" : "warn"} className="mt-1">{j.error}</Notice>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </>
  );
}

export default function InboxPage() {
  return <Suspense><InboxInner /></Suspense>;
}
