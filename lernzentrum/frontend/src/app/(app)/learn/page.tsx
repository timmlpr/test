"use client";
// Learning hub across modules.
import { BookMarked, CheckCircle2, Scale, Search, XCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AnswerGroup, LevelBadge } from "@/components/answer-card";
import { PageHeader } from "@/components/app-shell";
import { FlashcardReview } from "@/components/learn";
import { useApp } from "@/components/providers";
import { Badge, Button, Card, CardTitle, cn, Empty, Input, Label, Notice, Select, Spinner, Tabs, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { AnswerT, Level, Module } from "@/lib/types";

type Tab = "cards" | "ask" | "case" | "statutes" | "plan" | "stats" | "history";

function LearnInner() {
  const search = useSearchParams();
  const [tab, setTab] = useState<Tab>((search.get("tab") as Tab) || "cards");
  const [mods, setMods] = useState<Module[]>([]);
  useEffect(() => {
    api.get<Module[]>("/modules").then(setMods);
  }, []);
  return (
    <>
      <PageHeader title="Lernen" subtitle="Karteikarten, Fälle, Gesetze, Lernplan und Statistik." />
      <Tabs<Tab> className="mb-4" value={tab} onChange={setTab} tabs={[
        { id: "cards", label: "Karteikarten" }, { id: "ask", label: "Frag dein Material" }, { id: "case", label: "Fallübung" },
        { id: "statutes", label: "Gesetzesfinder" }, { id: "plan", label: "Lernplan" }, { id: "stats", label: "Statistik" }, { id: "history", label: "Antwortverlauf" },
      ]} />
      {tab === "cards" && <FlashcardReview />}
      {tab === "ask" && <Ask mods={mods} />}
      {tab === "case" && <CasePractice mods={mods} />}
      {tab === "statutes" && <StatuteFinder />}
      {tab === "plan" && <Plan />}
      {tab === "stats" && <Stats />}
      {tab === "history" && <History mods={mods} />}
    </>
  );
}

export default function LearnPage() {
  return <Suspense><LearnInner /></Suspense>;
}

function Ask({ mods }: { mods: Module[] }) {
  const { toast } = useApp();
  const [q, setQ] = useState("");
  const [mid, setMid] = useState<string>("");
  const [mode, setMode] = useState<"short" | "detailed">("detailed");
  const [res, setRes] = useState<AnswerT[] | null>(null);
  const [busy, setBusy] = useState(false);
  const ask = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ answers: AnswerT[] }>("/ask", { question: q, module_id: mid ? Number(mid) : null, mode });
      setRes(r.answers);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-4">
      <Card className="space-y-3">
        <p className="text-sm text-muted">Antworten nur aus deinen Unterlagen, Aufnahmen und amtlichen Gesetzestexten – mit Ampel und Fundstelle.</p>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <Input className="min-w-[260px] flex-[3]" placeholder="z. B. Was hat der Dozent zu § 15 EStG gesagt?" value={q} onChange={(e) => setQ(e.target.value)} />
          <Select className="min-w-[160px] flex-1" value={mid} onChange={(e) => setMid(e.target.value)}>
            <option value="">Alle Module</option>
            {mods.map((m) => <option key={m.id} value={m.id}>{m.short} – {m.name}</option>)}
          </Select>
          <Select className="w-36" value={mode} onChange={(e) => setMode(e.target.value as "short" | "detailed")}>
            <option value="short">Kurz</option><option value="detailed">Ausführlich</option>
          </Select>
          <Button type="submit" loading={busy} disabled={!q.trim()}>Fragen</Button>
        </form>
      </Card>
      {res && <AnswerGroup answers={res} mode={mode} />}
    </div>
  );
}

function CasePractice({ mods }: { mods: Module[] }) {
  const [cases, setCases] = useState<{ title: string; case: string }[]>([]);
  const [c, setC] = useState("");
  const [sol, setSol] = useState("");
  const [mid, setMid] = useState("");
  const [res, setRes] = useState<{ checks: { step: string; ok: boolean }[]; score: number; tips: string[]; norms: { label: string; found: boolean; excerpt: string }[]; llm_feedback: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get<typeof cases>("/learn/cases").then((x) => {
      setCases(x);
      if (x[0]) setC(x[0].case);
    });
  }, []);
  const grade = async () => {
    setBusy(true);
    setRes(await api.post<NonNullable<typeof res>>("/learn/case", { case: c, solution: sol, module_id: mid ? Number(mid) : null }).finally(() => setBusy(false)));
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="space-y-3">
        <CardTitle>Fall im Gutachtenstil</CardTitle>
        <div className="flex flex-wrap gap-2">
          {cases.map((x) => <Button key={x.title} size="sm" variant={c === x.case ? "primary" : "outline"} onClick={() => setC(x.case)}>{x.title}</Button>)}
        </div>
        <div><Label>Sachverhalt</Label><Textarea value={c} onChange={(e) => setC(e.target.value)} /></div>
        <div><Label>Deine Lösung</Label><Textarea className="min-h-56" value={sol} onChange={(e) => setSol(e.target.value)} placeholder="V könnte gegen K einen Anspruch auf … aus § … haben. Dazu müsste … Hier … Somit …" /></div>
        <Select value={mid} onChange={(e) => setMid(e.target.value)}>
          <option value="">Modul (für Statistik)</option>
          {mods.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </Select>
        <Button onClick={grade} loading={busy} disabled={sol.trim().length < 20}>Feedback erhalten</Button>
      </Card>
      <Card>
        <CardTitle>Feedback</CardTitle>
        {!res ? <p className="text-muted">Schreibe eine Lösung: Obersatz – Definition – Subsumtion – Ergebnis.</p> : (
          <div className="space-y-3">
            <ul className="space-y-1">
              {res.checks.map((x) => (
                <li key={x.step} className="flex items-center gap-2">{x.ok ? <CheckCircle2 className="h-5 w-5 text-sicher" /> : <XCircle className="h-5 w-5 text-unsicher" />} {x.step}</li>
              ))}
            </ul>
            {res.tips.length > 0 && <Notice tone="warn"><ul className="list-disc pl-4">{res.tips.map((t) => <li key={t}>{t}</li>)}</ul></Notice>}
            {res.norms.map((n) => (
              <div key={n.label} className="rounded-xl bg-surface-2 p-3 text-sm"><b>{n.label}</b>: {n.found ? n.excerpt : "Normtext nicht abrufbar"}</div>
            ))}
            {res.llm_feedback ? <div className="whitespace-pre-line text-sm">{res.llm_feedback}</div> : <p className="text-xs text-muted">Ausführliches Feedback mit Gemini-Key.</p>}
          </div>
        )}
      </Card>
    </div>
  );
}

function StatuteFinder() {
  const { toast } = useApp();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ direct: { label: string; title: string; text: string; url: string; demo: boolean }[]; results: { label: string; title: string; text: string; url: string; score: number }[]; loaded_laws: string[]; hint: string | null } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const find = async () => setRes(await api.post("/learn/statutes/find", { question: q }));
  const load = async () => {
    await api.post("/learn/statutes/load", { laws: ["bgb", "hgb", "estg", "ao", "ustg"] });
    toast("Gesetze werden geladen (läuft im Hintergrund).", "ok");
  };
  return (
    <div className="space-y-4">
      <Card>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); find(); }}>
          <Input placeholder="Frage oder Norm, z. B. „Wann verjährt ein Kaufpreisanspruch?“ oder „§ 238 HGB“" value={q} onChange={(e) => setQ(e.target.value)} />
          <Button type="submit" disabled={!q.trim()}><Search className="h-4 w-4" /> Finden</Button>
        </form>
        <p className="mt-2 text-xs text-muted">Quelle: ausschließlich gesetze-im-internet.de (amtliche Fassung).</p>
      </Card>
      {res?.hint && <Notice>{res.hint} <button className="font-medium text-primary underline" onClick={load}>Jetzt laden</button></Notice>}
      {res && [...res.direct.map((x) => ({ ...x, score: 1 })), ...res.results].map((r, i) => (
        <Card key={i}>
          <button className="w-full text-left" onClick={() => setOpen(open === `${i}` ? null : `${i}`)}>
            <p className="flex items-center gap-2 font-semibold"><Scale className="h-4 w-4 text-primary" /> {r.title || r.label} <Badge>{Math.round(r.score * 100)} %</Badge></p>
            <p className={cn("mt-1 whitespace-pre-line text-sm", open !== `${i}` && "line-clamp-3")}>{r.text}</p>
          </button>
          {r.url && <a className="mt-2 inline-block text-sm text-primary underline" href={r.url} target="_blank" rel="noreferrer">Amtlicher Text</a>}
        </Card>
      ))}
      {res && res.direct.length + res.results.length === 0 && <Empty icon={<BookMarked />} title="Nichts gefunden">Lade ganze Gesetze für die Volltextsuche.</Empty>}
    </div>
  );
}

function Plan() {
  const [plan, setPlan] = useState<{ date: string; module: string; color: string; task: string; minutes: number; deadline?: boolean }[] | null>(null);
  useEffect(() => {
    api.get<typeof plan>("/learn/plan?days=14").then(setPlan);
  }, []);
  if (!plan) return <Spinner />;
  const days = Array.from(new Set(plan.map((p) => p.date)));
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {days.map((d) => (
        <Card key={d}>
          <p className="mb-2 font-semibold">{new Date(d).toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "short" })}</p>
          <ul className="space-y-1.5 text-sm">
            {plan.filter((p) => p.date === d).map((p, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: p.color }} />
                <span className={cn("flex-1", p.deadline && "font-semibold text-unsicher")}>{p.task}</span>
                {p.minutes > 0 && <span className="text-muted">{p.minutes} min</span>}
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

function Stats() {
  const [s, setS] = useState<{ modules: { short: string; color: string; study_minutes: number; lecture_minutes: number; accuracy: number | null }[]; per_day: { date: string; minutes: number }[]; answers: Record<string, number>; strengths: string[]; weaknesses: string[] } | null>(null);
  useEffect(() => {
    api.get<typeof s>("/learn/stats").then(setS);
  }, []);
  if (!s) return <Spinner />;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardTitle>Lernzeit pro Modul (Minuten)</CardTitle>
        <div className="h-64">
          <ResponsiveContainer>
            <BarChart data={s.modules}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="short" stroke="var(--muted)" />
              <YAxis stroke="var(--muted)" />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }} />
              <Bar dataKey="study_minutes" name="Lernen" fill="var(--primary)" radius={[6, 6, 0, 0]} />
              <Bar dataKey="lecture_minutes" name="Vorlesung" fill="var(--accent)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card>
        <CardTitle>Stärken & Schwächen</CardTitle>
        <ul className="space-y-2">
          {s.modules.map((m) => (
            <li key={m.short} className="flex items-center gap-2">
              <span className="w-14 font-semibold" style={{ color: m.color }}>{m.short}</span>
              <span className="flex-1 text-sm text-muted">{m.accuracy == null ? "noch keine Übungen" : `${Math.round(m.accuracy * 100)} % richtig`}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-sm">Stark: {s.strengths.join(", ") || "–"} · Ausbauen: {s.weaknesses.join(", ") || "–"}</p>
        <p className="mt-3 text-sm text-muted">Antworten im Live-Modus: {Object.entries(s.answers).map(([k, v]) => `${k} ${v}`).join(" · ") || "noch keine"}</p>
      </Card>
      <Card className="lg:col-span-2">
        <CardTitle>Lernminuten pro Tag</CardTitle>
        <div className="h-48">
          <ResponsiveContainer>
            <BarChart data={s.per_day}>
              <XAxis dataKey="date" stroke="var(--muted)" tickFormatter={(d) => d.slice(5)} />
              <YAxis stroke="var(--muted)" />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }} />
              <Bar dataKey="minutes" fill="var(--primary)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}

function History({ mods }: { mods: Module[] }) {
  const [list, setList] = useState<AnswerT[] | null>(null);
  const [level, setLevel] = useState<string>("");
  const [mid, setMid] = useState<string>("");
  useEffect(() => {
    api.get<AnswerT[]>(`/answers?${level ? `level=${encodeURIComponent(level)}&` : ""}${mid ? `module_id=${mid}` : ""}`).then(setList);
  }, [level, mid]);
  const [open, setOpen] = useState<number | null>(null);
  const modById = Object.fromEntries(mods.map((m) => [m.id, m]));
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Select value={level} onChange={(e) => setLevel(e.target.value)} className="w-44"><option value="">Alle Stufen</option><option>SICHER</option><option>PRÜFEN</option><option>UNSICHER</option></Select>
        <Select value={mid} onChange={(e) => setMid(e.target.value)} className="w-56"><option value="">Alle Module</option>{mods.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</Select>
      </div>
      {!list ? <Spinner /> : list.length === 0 ? <Empty title="Noch keine Antworten" /> : list.map((a) => (
        <Card key={a.id}>
          <button className="flex w-full items-start gap-3 text-left" onClick={() => setOpen(open === a.id ? null : a.id)}>
            <LevelBadge level={a.level as Level} percent={a.percent} />
            <div className="min-w-0 flex-1">
              <p className="font-medium">{a.question}</p>
              <p className="text-xs text-muted">{a.module_id && modById[a.module_id]?.short} · {fmtDateTime(a.created_at ? a.created_at + "Z" : null)} {a.correction && "· vom Dozenten korrigiert"} {a.feedback && `· ${a.feedback}`}</p>
            </div>
          </button>
          {open === a.id && <div className="mt-3"><AnswerGroup answers={[a]} mode="detailed" /></div>}
        </Card>
      ))}
    </div>
  );
}
