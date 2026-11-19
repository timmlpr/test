"use client";
// Module workspace: dashboard, material, lectures (+ generated packages), flashcards, quiz, mock exam,
// exam radar / gaps / contradictions, glossary, lecturer profile, settings (exam date, exam guard, retention).
import { AlertTriangle, BookOpen, CheckCircle2, FileText, Mic, Radar, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { UploadZone } from "@/components/connect";
import { FlashcardReview, MockExam, Quiz } from "@/components/learn";
import { useApp } from "@/components/providers";
import { Badge, Button, Card, CardTitle, Empty, Input, Label, Notice, Progress, Spinner, Tabs, Textarea, Toggle } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtDuration, KIND_LABEL, relDays } from "@/lib/format";
import type { Deadline, Module } from "@/lib/types";

type Tab = "overview" | "material" | "lectures" | "cards" | "quiz" | "mock" | "radar" | "glossary" | "profile" | "settings";

interface Dash {
  module: Module;
  progress: number;
  exam_in_days: number | null;
  cards: { total: number; due: number; known: number };
  lectures: { past: number; total: number; next: { start: string; title: string } | null };
  recordings: { id: number; title: string; started_at: string; duration_s: number; status: string; package_status: string }[];
  documents: { id: number; title: string; kind: string; pages: number; status: string; doc_date: string | null }[];
  open_questions: { id: number; title: string }[];
  gaps: Gap[];
  gap_count: number;
  deadlines: Deadline[];
  announcements: { id: number; title: string; body: string; author: string; posted_at: string; read: boolean }[];
  next_tasks: string[];
}
interface Gap { source: { label: string; document_id: number; page: number }; coverage: number; excerpt: string; missing: string[] }
interface Item { id: number; kind: string; title: string; body: string; recording_id: number | null; source: { start_s?: number; recording_id?: number }; done: boolean }

function ModuleInner() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const { toast } = useApp();
  const [tab, setTab] = useState<Tab>((search.get("tab") as Tab) || "overview");
  const [d, setD] = useState<Dash | null>(null);
  const load = useCallback(() => api.get<Dash>(`/modules/${id}/dashboard`).then(setD).catch((e) => toast(e.message, "error")), [id, toast]);
  useEffect(() => {
    load();
  }, [load]);
  if (!d) return <Spinner />;
  const m = d.module;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span className="rounded-lg px-2.5 py-1 text-lg font-bold text-white" style={{ background: m.color }}>{m.short}</span>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-bold tracking-tight">{m.name}</h1>
          <p className="text-muted">{m.lecturer}{m.exam_date ? ` · Prüfung ${fmtDate(m.exam_date)}${d.exam_in_days != null && d.exam_in_days >= 0 ? ` (in ${d.exam_in_days} Tagen)` : ""}` : ""}</p>
        </div>
        {m.exam_mode && <Badge color="var(--pruefen)">Prüfungsmodus aktiv</Badge>}
      </div>
      <Tabs<Tab>
        className="mb-4"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "overview", label: "Übersicht" },
          { id: "material", label: "Material", count: d.documents.length },
          { id: "lectures", label: "Vorlesungen", count: d.recordings.length },
          { id: "cards", label: "Karteikarten", count: d.cards.due },
          { id: "quiz", label: "Quiz" },
          { id: "mock", label: "Probeklausur" },
          { id: "radar", label: "Radar & Lücken", count: d.gap_count },
          { id: "glossary", label: "Glossar" },
          { id: "profile", label: "Dozent" },
          { id: "settings", label: "Einstellungen" },
        ]}
      />
      {tab === "overview" && <Overview d={d} setTab={setTab} />}
      {tab === "material" && (
        <div className="space-y-4">
          <UploadZone moduleId={m.id} onDone={() => setTimeout(load, 1500)} />
          <Card>
            {d.documents.length === 0 ? <Empty title="Noch kein Material" /> : (
              <ul className="divide-y divide-border">
                {d.documents.map((doc) => (
                  <li key={doc.id}>
                    <Link href={`/library/${doc.id}`} className="flex items-center gap-3 py-2.5">
                      <FileText className="h-5 w-5 text-muted" />
                      <span className="flex-1 truncate">{doc.title}</span>
                      <Badge>{KIND_LABEL[doc.kind] || doc.kind}</Badge>
                      {doc.status === "waiting" && <Badge color="var(--pruefen)">wartet</Badge>}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
      {tab === "lectures" && <Lectures d={d} />}
      {tab === "cards" && <FlashcardReview moduleId={m.id} />}
      {tab === "quiz" && <Quiz moduleId={m.id} />}
      {tab === "mock" && <MockExam moduleId={m.id} />}
      {tab === "radar" && <RadarTab moduleId={m.id} />}
      {tab === "glossary" && <Glossary moduleId={m.id} />}
      {tab === "profile" && <Profile moduleId={m.id} />}
      {tab === "settings" && <ModuleSettings m={m} onSaved={load} />}
    </>
  );
}

export default function ModulePage() {
  return <Suspense><ModuleInner /></Suspense>;
}

function Overview({ d, setTab }: { d: Dash; setTab: (t: Tab) => void }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card>
        <CardTitle>Fortschritt</CardTitle>
        <p className="mb-2 text-3xl font-bold">{Math.round(d.progress * 100)} %</p>
        <Progress value={d.progress} color={d.module.color} />
        <p className="mt-3 text-sm text-muted">{d.lectures.past}/{d.lectures.total} Vorlesungen · {d.cards.known}/{d.cards.total} Karten sicher</p>
        {d.lectures.next && <p className="mt-1 text-sm">Nächste VL: {fmtDateTime(d.lectures.next.start)}</p>}
      </Card>
      <Card>
        <CardTitle>Nächste Aufgaben</CardTitle>
        {d.next_tasks.length === 0 ? <p className="text-muted">Alles erledigt.</p> : (
          <ul className="space-y-2">
            {d.next_tasks.map((t) => <li key={t} className="flex gap-2"><Sparkles className="h-4 w-4 shrink-0 text-primary" />{t}</li>)}
          </ul>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {d.cards.due > 0 && <Button size="sm" onClick={() => setTab("cards")}>Karten lernen</Button>}
          <Button size="sm" variant="outline" onClick={() => setTab("mock")}>Probeklausur</Button>
        </div>
      </Card>
      <Card>
        <CardTitle>Fristen</CardTitle>
        {d.deadlines.length === 0 ? <p className="text-muted">Keine Fristen.</p> : (
          <ul className="space-y-1.5 text-sm">
            {d.deadlines.map((x) => <li key={x.id}><b>{relDays(x.due)}</b> – {x.title}</li>)}
          </ul>
        )}
      </Card>
      <Card className="lg:col-span-2">
        <CardTitle action={d.gap_count > 0 ? <button className="text-sm text-primary" onClick={() => setTab("radar")}>alle {d.gap_count}</button> : undefined}>Offene Lücken</CardTitle>
        {d.gaps.length === 0 ? <p className="text-muted">Keine Lücken gefunden (oder noch keine Aufnahmen).</p> : (
          <ul className="space-y-2 text-sm">
            {d.gaps.map((g, i) => (
              <li key={i}><Link href={`/library/${g.source.document_id}?page=${g.source.page}`} className="font-medium text-primary">{g.source.label}</Link> – in keiner Vorlesung besprochen: {g.missing.slice(0, 4).join(", ")}</li>
            ))}
          </ul>
        )}
        {d.open_questions.length > 0 && (
          <>
            <p className="mb-1 mt-4 font-semibold">Offene Fragen</p>
            <ul className="list-disc pl-5 text-sm">{d.open_questions.map((q) => <li key={q.id}>{q.title}</li>)}</ul>
          </>
        )}
      </Card>
      <Card>
        <CardTitle>Ankündigungen</CardTitle>
        {d.announcements.length === 0 ? <p className="text-muted">Keine.</p> : (
          <ul className="space-y-3">
            {d.announcements.map((a) => (
              <li key={a.id}>
                <p className="font-medium">{a.title}</p>
                <p className="text-sm text-muted">{a.body}</p>
                <p className="text-xs text-muted">{a.author} · {fmtDate(a.posted_at)}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Lectures({ d }: { d: Dash }) {
  const [items, setItems] = useState<Item[]>([]);
  useEffect(() => {
    api.get<Item[]>(`/learn/items?module_id=${d.module.id}`).then(setItems);
  }, [d.module.id]);
  return (
    <div className="space-y-4">
      {d.recordings.length === 0 && <Empty icon={<Mic />} title="Noch keine Aufnahmen" />}
      {d.recordings.map((r) => {
        const its = items.filter((i) => i.recording_id === r.id);
        const summary = its.find((i) => i.kind === "summary");
        const passages = its.filter((i) => i.kind === "exam_passage");
        return (
          <Card key={r.id}>
            <CardTitle action={<Link href={`/live/${r.id}`} className="text-sm text-primary">Transkript</Link>}>
              {r.title} <span className="text-sm font-normal text-muted">· {fmtDuration(r.duration_s)}</span>
            </CardTitle>
            {summary ? <p className="whitespace-pre-line text-sm">{summary.body}</p> : <p className="text-sm text-muted">Nachbereitung: {r.package_status === "queued" ? "läuft …" : "noch nicht erstellt"}</p>}
            {passages.length > 0 && (
              <div className="mt-3">
                <p className="mb-1 flex items-center gap-1.5 text-sm font-semibold"><AlertTriangle className="h-4 w-4 text-pruefen" /> Klausurrelevante Stellen</p>
                <ul className="space-y-1 text-sm">
                  {passages.map((p) => (
                    <li key={p.id}><Link className="text-primary" href={`/live/${r.id}?t=${Math.floor(p.source.start_s || 0)}`}>{fmtDuration(p.source.start_s)}</Link> {p.body}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

function RadarTab({ moduleId }: { moduleId: number }) {
  const [radar, setRadar] = useState<{ topic: string; score: number }[] | null>(null);
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [contra, setContra] = useState<{ material: { text: string; label: string; document_id: number; page: number }; lecturer: { text: string; label: string; recording_id: number; start_s: number }; unit: string }[]>([]);
  useEffect(() => {
    api.get<typeof radar>(`/learn/radar/${moduleId}`).then(setRadar);
    api.get<Gap[]>(`/learn/gaps/${moduleId}`).then(setGaps);
    api.get<typeof contra>(`/learn/contradictions/${moduleId}`).then(setContra);
  }, [moduleId]);
  if (!radar) return <Spinner />;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardTitle><span className="flex items-center gap-2"><Radar className="h-5 w-5" /> Klausur-Radar</span></CardTitle>
        <p className="mb-3 text-sm text-muted">Themen, die der Dozent betont („klausurrelevant“, „merken“) oder mehrfach behandelt.</p>
        {radar.length === 0 ? <p className="text-muted">Noch keine Daten – nimm Vorlesungen auf.</p> : (
          <ul className="space-y-2">
            {radar.map((r) => (
              <li key={r.topic} className="flex items-center gap-3">
                <span className="w-40 truncate text-sm font-medium">{r.topic}</span>
                <Progress value={r.score} />
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <CardTitle>Widersprüche</CardTitle>
        <p className="mb-3 text-sm text-muted">Folie/Skript sagt etwas anderes als der Dozent.</p>
        {contra.length === 0 ? <p className="flex items-center gap-2 text-sicher"><CheckCircle2 className="h-4 w-4" /> Keine gefunden.</p> : (
          <ul className="space-y-3 text-sm">
            {contra.map((c, i) => (
              <li key={i} className="rounded-xl border border-pruefen/50 bg-pruefen-bg p-3">
                <p><b>Material</b> ({c.material.label}): {c.material.text}</p>
                <p className="mt-1"><b>Dozent</b> (<Link className="text-primary" href={`/live/${c.lecturer.recording_id}?t=${Math.floor(c.lecturer.start_s || 0)}`}>{c.lecturer.label}</Link>): {c.lecturer.text}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card className="lg:col-span-2">
        <CardTitle>Lückenfinder</CardTitle>
        <p className="mb-3 text-sm text-muted">Folien und Skriptseiten, die in keiner Aufnahme besprochen wurden.</p>
        {gaps.length === 0 ? <p className="text-muted">Keine Lücken (oder noch keine Aufnahmen).</p> : (
          <ul className="divide-y divide-border">
            {gaps.map((g, i) => (
              <li key={i} className="py-2.5 text-sm">
                <Link href={`/library/${g.source.document_id}?page=${g.source.page}`} className="font-medium text-primary">{g.source.label}</Link>
                <span className="text-muted"> · {Math.round(g.coverage * 100)} % besprochen</span>
                <p className="text-muted">{g.excerpt}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Glossary({ moduleId }: { moduleId: number }) {
  const { toast } = useApp();
  const [terms, setTerms] = useState<{ id: number; term: string; definition: string; source: { label?: string } }[] | null>(null);
  const [q, setQ] = useState("");
  const load = useCallback(() => api.get<typeof terms>(`/learn/glossary?module_id=${moduleId}`).then(setTerms), [moduleId]);
  useEffect(() => {
    load();
  }, [load]);
  const build = async () => {
    const r = await api.post<{ found: number }>(`/learn/glossary/${moduleId}/build`);
    toast(`${r.found} Definitionen gefunden`, "ok");
    load();
  };
  if (!terms) return <Spinner />;
  const list = terms.filter((t) => !q || t.term.toLowerCase().includes(q.toLowerCase()));
  return (
    <Card>
      <div className="mb-3 flex gap-2">
        <Input placeholder="Begriff suchen" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button variant="outline" onClick={build}><BookOpen className="h-4 w-4" /> Aus Material erzeugen</Button>
      </div>
      {list.length === 0 ? <Empty title="Noch keine Fachbegriffe" /> : (
        <dl className="divide-y divide-border">
          {list.map((t) => (
            <div key={t.id} className="py-2.5">
              <dt className="font-semibold">{t.term}</dt>
              <dd className="text-sm">{t.definition}</dd>
              {t.source?.label && <dd className="text-xs text-muted">Quelle: {t.source.label}</dd>}
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

function Profile({ moduleId }: { moduleId: number }) {
  const { toast } = useApp();
  const [p, setP] = useState<{ notes: string; terms: string[]; corrections: { question: string; said: string; at: string }[]; lectures: number; lecturer: string } | null>(null);
  useEffect(() => {
    api.get<typeof p>(`/modules/${moduleId}/profile`).then(setP);
  }, [moduleId]);
  if (!p) return <Spinner />;
  const save = async () => {
    setP(await api.put(`/modules/${moduleId}/profile`, { notes: p.notes, terms: p.terms }));
    toast("Steckbrief gespeichert", "ok");
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="space-y-3">
        <CardTitle>Dozenten-Steckbrief {p.lecturer && `· ${p.lecturer}`}</CardTitle>
        <p className="text-sm text-muted">Lernt aus {p.lectures} Aufnahme(n) und Korrekturen. Wird bei Antworten als Kontext genutzt (nie als Quelle).</p>
        <div>
          <Label>Notizen (Schwerpunkte, typische Formulierungen)</Label>
          <Textarea value={p.notes} onChange={(e) => setP({ ...p, notes: e.target.value })} />
        </div>
        <div>
          <Label hint="kommagetrennt">Typische Begriffe</Label>
          <Textarea className="min-h-20" value={p.terms.join(", ")} onChange={(e) => setP({ ...p, terms: e.target.value.split(",").map((s) => s.trim()) })} />
        </div>
        <Button onClick={save}>Speichern</Button>
      </Card>
      <Card>
        <CardTitle>Korrekturen durch den Dozenten</CardTitle>
        {p.corrections.length === 0 ? <p className="text-muted">Noch keine.</p> : (
          <ul className="space-y-2 text-sm">
            {p.corrections.slice().reverse().map((c, i) => <li key={i}><b>{c.question}</b><br /><span className="text-muted">Dozent: „{c.said}“</span></li>)}
          </ul>
        )}
      </Card>
    </div>
  );
}

function ModuleSettings({ m, onSaved }: { m: Module; onSaved: () => void }) {
  const { toast } = useApp();
  const [f, setF] = useState({ name: m.name, short: m.short, lecturer: m.lecturer, color: m.color, exam_date: m.exam_date?.slice(0, 10) || "", exam_mode: m.exam_mode, retention_days: m.retention_days ?? "", aliases: m.aliases.join(", "), ects: m.ects });
  const save = async () => {
    await api.patch(`/modules/${m.id}`, {
      name: f.name, short: f.short, lecturer: f.lecturer, color: f.color, exam_mode: f.exam_mode, ects: Number(f.ects),
      exam_date: f.exam_date ? `${f.exam_date}T09:00:00` : undefined, clear_exam_date: !f.exam_date,
      retention_days: f.retention_days === "" ? undefined : Number(f.retention_days),
      aliases: f.aliases.split(",").map((s) => s.trim()).filter(Boolean),
    });
    toast("Gespeichert", "ok");
    onSaved();
  };
  return (
    <Card className="max-w-2xl space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div><Label>Name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
        <div><Label>Kürzel</Label><Input value={f.short} onChange={(e) => setF({ ...f, short: e.target.value })} /></div>
        <div><Label>Dozent/in</Label><Input value={f.lecturer} onChange={(e) => setF({ ...f, lecturer: e.target.value })} /></div>
        <div><Label>Farbe</Label><Input type="color" value={f.color} onChange={(e) => setF({ ...f, color: e.target.value })} className="p-1" /></div>
        <div><Label>Prüfungstermin</Label><Input type="date" value={f.exam_date} onChange={(e) => setF({ ...f, exam_date: e.target.value })} /></div>
        <div><Label>ECTS</Label><Input type="number" value={f.ects} onChange={(e) => setF({ ...f, ects: Number(e.target.value) })} /></div>
        <div className="sm:col-span-2"><Label hint="für Kalender-/Moodle-Zuordnung, kommagetrennt">Andere Bezeichnungen</Label><Input value={f.aliases} onChange={(e) => setF({ ...f, aliases: e.target.value })} /></div>
        <div><Label hint="leer = unbegrenzt">Audio löschen nach (Tagen)</Label><Input type="number" value={f.retention_days} onChange={(e) => setF({ ...f, retention_days: e.target.value === "" ? "" : Number(e.target.value) })} /></div>
      </div>
      <Toggle checked={f.exam_mode} onChange={(v) => setF({ ...f, exam_mode: v })} label="Prüfungsmodus" description="Schaltet Live-Antworten für dieses Modul ab." />
      {f.exam_mode && <Notice tone="warn">Lernzentrum darf während Prüfungen nicht benutzt werden – auch nicht zum Aufnehmen.</Notice>}
      <Button onClick={save}>Speichern</Button>
    </Card>
  );
}
