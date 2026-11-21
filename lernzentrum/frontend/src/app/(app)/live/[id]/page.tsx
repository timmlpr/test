"use client";
// Live session (landscape iPad: answers on top, transcript below, context column right) and review of past
// recordings. Events arrive via SSE (with polling fallback) and are replayable after reconnects.
import {
  AlertTriangle, BookMarked, Calculator, EyeOff, FileText, Hand, Lightbulb, Loader2, Maximize2, MessageSquarePlus, Mic, Minimize2,
  Pause, Play, Send, Square, Star, Wifi, WifiOff, Zap,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnswerGroup, SourceSheet } from "@/components/answer-card";
import { TranscriptText } from "@/components/transcript-text";
import { useApp } from "@/components/providers";
import { Badge, Button, Card, cn, Input, ModuleChip, Notice, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDuration } from "@/lib/format";
import { LiveRecorder, flushQueue, pendingChunks, type RecorderState } from "@/lib/recorder";
import type { AnswerT, LiveEvent, Recording, Segment, SlideRef, Source } from "@/lib/types";

interface StatuteEv { key: string; label: string; found: boolean; title?: string; excerpt?: string; url?: string; demo?: boolean }
interface NumberEv { kind: string; value: string; context: string; at_s: number }
interface KeywordEv { cue: string; text: string; at_s: number }

export default function LiveSession() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const { toast, largeType, setLargeType, dim, setDim, user } = useApp();
  const [rec, setRec] = useState<Recording | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [groups, setGroups] = useState<Record<string, AnswerT[]>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [statutes, setStatutes] = useState<StatuteEv[]>([]);
  const [numbers, setNumbers] = useState<NumberEv[]>([]);
  const [keywords, setKeywords] = useState<KeywordEv[]>([]);
  const [slide, setSlide] = useState<SlideRef | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [status, setStatus] = useState<{ level: string; message: string } | null>(null);
  const [examGuard, setExamGuard] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [mode, setMode] = useState<"short" | "detailed">("short");
  const [alert, setAlert] = useState<KeywordEv | null>(null);
  const [rs, setRs] = useState<RecorderState | null>(null);
  const [connected, setConnected] = useState(true);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [demoRunning, setDemoRunning] = useState(false);
  const [src, setSrc] = useState<Source | null>(null);
  const [partCount, setPartCount] = useState(0);
  const [hasGroq, setHasGroq] = useState<boolean | null>(null);
  const lastId = useRef(0);
  const recorder = useRef<LiveRecorder | null>(null);
  const transcriptEnd = useRef<HTMLDivElement>(null);
  const demoStop = useRef(false);
  const isLive = rec?.status === "live";

  const apply = useCallback((events: LiveEvent[]) => {
    for (const e of events) {
      if (e.id <= lastId.current) continue;
      lastId.current = e.id;
      const p = e.payload as Record<string, unknown>;
      switch (e.kind) {
        case "transcript":
          setSegments((s) => [...s, p as unknown as Segment]);
          break;
        case "transcript_update":
          setSegments((s) => s.map((x) => (x.id === p.id ? { ...x, ...(p as unknown as Segment) } : x)));
          break;
        case "answer": {
          const ans = p.answers as AnswerT[];
          if (!ans.length) break;
          const g = ans[0].group_id;
          setGroups((x) => ({ ...x, [g]: ans }));
          setOrder((o) => [g, ...o.filter((y) => y !== g)]);
          break;
        }
        case "correction": {
          const gid = p.group_id as string;
          setGroups((x) => {
            const arr = x[gid];
            if (!arr) return x;
            return { ...x, [gid]: arr.map((a) => (a.id === p.answer_id ? { ...a, level: "UNSICHER", percent: Math.min(a.percent, 30), correction: p.correction as AnswerT["correction"] } : a)) };
          });
          setOrder((o) => [gid, ...o.filter((y) => y !== gid)]);
          break;
        }
        case "statute":
          setStatutes((s) => [p as unknown as StatuteEv, ...s.filter((x) => x.key !== p.key)].slice(0, 8));
          break;
        case "number":
          setNumbers((n) => [p as unknown as NumberEv, ...n].slice(0, 30));
          break;
        case "keyword": {
          const k = p as unknown as KeywordEv;
          setKeywords((x) => [k, ...x].slice(0, 20));
          if (lastId.current > 0) {
            setAlert(k);
            navigator.vibrate?.(60);
            setTimeout(() => setAlert(null), 5000);
          }
          break;
        }
        case "slide":
          setSlide(p as unknown as SlideRef);
          break;
        case "suggestions":
          setSuggestions(p.questions as string[]);
          break;
        case "status":
          setStatus(p as { level: string; message: string });
          break;
        case "exam_guard":
          setExamGuard(p.message as string);
          break;
        case "participation":
          setPartCount(p.count as number);
          break;
        case "gap":
          setStatus({ level: "info", message: p.message as string });
          break;
      }
    }
  }, []);

  // initial load: recording + full event replay
  useEffect(() => {
    let alive = true;
    (async () => {
      const r = await api.get<Recording>(`/recordings/${id}`);
      if (!alive) return;
      setRec(r);
      setMode(r.answer_mode);
      setPartCount(r.participation?.length || 0);
      const evs = await api.get<LiveEvent[]>(`/recordings/${id}/events`);
      apply(evs);
      api.get<{ provider: string; status: string }[]>("/secrets").then((s) => setHasGroq(s.some((x) => x.provider === "groq" && x.status !== "missing"))).catch(() => undefined);
    })().catch((e) => toast((e as Error).message, "error"));
    return () => {
      alive = false;
    };
  }, [id, apply, toast]);

  // live stream (SSE) with polling fallback
  useEffect(() => {
    if (!isLive) return;
    let es: EventSource | null = null;
    let poll: number | undefined;
    let errors = 0;
    let lastMsg = Date.now();
    // safety net: if the stream is quiet (proxy buffering, flaky Wi-Fi), catch up via polling
    const catchUp = window.setInterval(async () => {
      if (Date.now() - lastMsg < 5000) return;
      try {
        const evs = await api.get<LiveEvent[]>(`/recordings/${id}/events?after=${lastId.current}`);
        if (evs.length) lastMsg = Date.now();
        apply(evs);
        setConnected(true);
      } catch {
        setConnected(false);
      }
    }, 3000);
    const startPolling = () => {
      poll = window.setInterval(async () => {
        try {
          apply(await api.get<LiveEvent[]>(`/recordings/${id}/events?after=${lastId.current}`));
          setConnected(true);
        } catch {
          setConnected(false);
        }
      }, 2000);
    };
    try {
      es = new EventSource(`/api/recordings/${id}/stream?after=${lastId.current}`);
      const handler = (m: MessageEvent) => {
        lastMsg = Date.now();
        setConnected(true);
        apply([JSON.parse(m.data)]);
      };
      ["transcript", "transcript_update", "answer", "correction", "statute", "number", "keyword", "slide", "suggestions", "status", "exam_guard", "participation", "gap"].forEach((k) => es!.addEventListener(k, handler as EventListener));
      es.onerror = () => {
        setConnected(false);
        if (++errors > 3 && es) {
          es.close();
          startPolling();
        }
      };
    } catch {
      startPolling();
    }
    return () => {
      es?.close();
      if (poll) clearInterval(poll);
      clearInterval(catchUp);
    };
  }, [id, isLive, apply]);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [segments.length]);

  // jump-to from a source link (?t=seconds)
  useEffect(() => {
    const t = Number(search.get("t"));
    if (!t || !segments.length) return;
    const seg = segments.reduce((best, s) => (Math.abs(s.start_s - t) < Math.abs(best.start_s - t) ? s : best), segments[0]);
    document.getElementById(`seg-${seg.id}`)?.scrollIntoView({ block: "center" });
  }, [search, segments]);

  const startRecording = useCallback(async () => {
    if (recorder.current) return;
    const left = await pendingChunks(Number(id));
    if (left) await flushQueue();
    const r = new LiveRecorder(Number(id), setRs, Date.now() % 1_000_000, rec?.duration_s || 0);
    recorder.current = r;
    await r.start();
    if (r.state.error) {
      toast(r.state.error, "error");
      recorder.current = null;
    }
  }, [id, rec?.duration_s, toast]);

  useEffect(() => {
    if (isLive && search.get("autostart") === "1" && hasGroq) {
      startRecording();
      router.replace(`/live/${id}`);
    }
  }, [isLive, search, hasGroq, startRecording, router, id]);

  useEffect(() => () => {
    recorder.current?.stop();
    demoStop.current = true;
  }, []);

  const finish = async () => {
    demoStop.current = true;
    await recorder.current?.stop();
    recorder.current = null;
    const r = await api.post<Recording>(`/recordings/${id}/finish`);
    setRec(r);
    toast("Aufnahme beendet. Zusammenfassung und Karteikarten werden erstellt.", "ok");
  };

  const ask = async (q?: string) => {
    setAsking(true);
    try {
      await api.post(`/recordings/${id}/ask`, { question: q ?? question, mode });
      setQuestion("");
      if (!isLive || !connected) apply(await api.get<LiveEvent[]>(`/recordings/${id}/events?after=${lastId.current}`));
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setAsking(false);
    }
  };

  const switchMode = async (m: "short" | "detailed") => {
    setMode(m);
    api.patch(`/recordings/${id}`, { answer_mode: m }).catch(() => undefined);
  };

  const participate = async (kind: "asked" | "answered") => {
    const r = await api.post<{ count: number }>(`/recordings/${id}/participation`, { kind });
    setPartCount(r.count);
    toast(kind === "asked" ? "Frage gezählt" : "Wortmeldung gezählt", "ok");
  };

  const runDemo = async () => {
    const script = await api.get<{ sentences: string[] }>("/demo/script");
    setDemoRunning(true);
    demoStop.current = false;
    for (const s of script.sentences) {
      if (demoStop.current) break;
      await api.post(`/recordings/${id}/simulate`, { text: s });
      if (!connected) apply(await api.get<LiveEvent[]>(`/recordings/${id}/events?after=${lastId.current}`));
      await new Promise((r) => setTimeout(r, 2600));
    }
    setDemoRunning(false);
  };

  const typeTranscript = async () => {
    if (!question.trim()) return;
    await api.post(`/recordings/${id}/simulate`, { text: question });
    setQuestion("");
  };

  const answerGroups = useMemo(() => order.map((g) => groups[g]).filter(Boolean), [order, groups]);
  if (!rec) return <Spinner />;
  const recording = !!rs?.recording;

  return (
    <div className={cn("flex flex-col gap-3", isLive && "lg:h-[calc(100dvh-2rem)]")}>
      {/* control bar */}
      <div className="flex flex-wrap items-center gap-2">
        <ModuleChip short={rec.module_short} color={rec.color} />
        <h1 className="mr-auto truncate text-lg font-semibold">{rec.title}</h1>
        {isLive && (
          <span className="flex items-center gap-1.5 text-sm text-muted" aria-live="polite">
            {connected && (rs?.online ?? true) ? <Wifi className="h-4 w-4 text-sicher" /> : <WifiOff className="h-4 w-4 text-unsicher" />}
            {rs?.queued ? `${rs.queued} offline gespeichert` : connected ? "verbunden" : "offline"}
          </span>
        )}
        {recording && <span className="tabular-nums text-sm font-medium text-unsicher">● {fmtDuration(rs?.elapsed)}</span>}
        <Button variant={hidden ? "primary" : "outline"} size="sm" onClick={() => setHidden(!hidden)} aria-pressed={hidden}>
          <EyeOff className="h-4 w-4" /> {hidden ? "Einblenden" : "Ausblenden"}
        </Button>
        <Button variant="outline" size="sm" onClick={() => setLargeType(!largeType)} aria-pressed={largeType}>
          {largeType ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />} Groß
        </Button>
        <Button variant="outline" size="sm" onClick={() => setDim(!dim)} aria-pressed={dim}>Dimmen</Button>
        <Button variant={showOriginal ? "primary" : "outline"} size="sm" onClick={() => setShowOriginal(!showOriginal)} aria-pressed={showOriginal}>Original anzeigen</Button>
        <div className="flex rounded-xl border border-border p-0.5" role="group" aria-label="Antwortlänge">
          {(["short", "detailed"] as const).map((m) => (
            <button key={m} onClick={() => switchMode(m)} className={cn("h-9 rounded-lg px-3 text-sm font-medium", mode === m ? "bg-primary text-primary-fg" : "text-muted")}>
              {m === "short" ? "Kurz" : "Ausführlich"}
            </button>
          ))}
        </div>
      </div>

      {examGuard && <Notice tone="warn"><b>Prüfungsmodus:</b> {examGuard}</Notice>}
      {status && <Notice tone={status.level === "error" ? "error" : "info"}>{status.message}{status.level === "error" && <> · <Link className="underline" href="/settings">Einstellungen</Link></>}</Notice>}
      {rs?.hidden && recording && <Notice tone="warn">Die App war im Hintergrund – Safari nimmt dann nicht auf. Bitte im Vordergrund lassen.</Notice>}
      {rs && !rs.wakeLock && recording && <Notice tone="warn">Bildschirm-Sperre konnte nicht verhindert werden: Automatische Sperre in iPadOS bitte auf „Nie“ stellen.</Notice>}
      {alert && (
        <div className="flash flex items-center gap-2 rounded-xl border-2 border-pruefen bg-pruefen-bg px-3 py-2 font-semibold" role="status">
          <Star className="h-5 w-5 text-pruefen" /> {alert.cue}: „{alert.text}“
        </div>
      )}

      <div className={cn("grid min-h-0 flex-1 gap-3", isLive && "lg:grid-cols-[1fr_320px]")}>
        <div className="flex min-h-0 flex-col gap-3">
          {/* TOP: answers */}
          <section className={cn("min-h-[40dvh] overflow-y-auto rounded-2xl border border-border bg-surface p-3 lg:min-h-0 lg:flex-[3]")} aria-label="Antworten">
            {hidden ? (
              <div className="flex h-full min-h-[30dvh] items-center justify-center text-muted">
                <button onClick={() => setHidden(false)} className="rounded-xl px-4 py-3 text-sm">Antworten ausgeblendet – Aufnahme läuft weiter. Tippen zum Einblenden.</button>
              </div>
            ) : answerGroups.length === 0 ? (
              <div className="flex h-full min-h-[25dvh] flex-col items-center justify-center gap-2 text-center text-muted">
                <MessageSquarePlus className="h-8 w-8" />
                <p>Erkannte Fragen erscheinen hier mit Antwort, Ampel und Quelle.</p>
              </div>
            ) : (
              <div className="space-y-5">
                {answerGroups.map((g) => (
                  <AnswerGroup key={g[0].group_id} answers={g} mode={mode} big={largeType} onFeedback={() => undefined} />
                ))}
              </div>
            )}
          </section>

          {/* manual controls */}
          {(isLive || rec.status === "done") && (
            <div className="flex flex-wrap gap-2">
              {isLive && (
                <Button onClick={() => ask("")} loading={asking} variant="secondary">
                  <Zap className="h-4 w-4" /> Das beantworten
                </Button>
              )}
              <form className="flex min-w-[240px] flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); if (question.trim()) ask(question); }}>
                <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Eigene Frage oder Nachfrage …" aria-label="Eigene Frage" />
                <Button type="submit" size="icon" aria-label="Frage senden" disabled={!question.trim()} loading={asking}>
                  {!asking && <Send className="h-4 w-4" />}
                </Button>
              </form>
              {isLive && !hasGroq && (
                <Button variant="ghost" onClick={typeTranscript} disabled={!question.trim()} title="Text als Gesagtes einspeisen (ohne Spracherkennung)">
                  als Gesagtes
                </Button>
              )}
            </div>
          )}

          {/* BOTTOM: transcript */}
          <section className="max-h-[38dvh] min-h-[20dvh] overflow-y-auto rounded-2xl border border-border bg-surface p-3 lg:max-h-none lg:min-h-0 lg:flex-[2]" aria-label="Transkript" aria-live="polite">
            {segments.length === 0 ? (
              <p className="p-4 text-center text-muted">{isLive ? "Transkript erscheint hier …" : "Kein Transkript."}</p>
            ) : (
              <ol className="space-y-1.5">
                {segments.map((s) => (
                  <li key={s.id} id={`seg-${s.id}`} className={cn("flex gap-3 rounded-lg px-2 py-1", s.flags?.includes("keyword") && "bg-pruefen-bg", s.flags?.includes("question") && "border-l-4 border-primary")}>
                    <span className="w-12 shrink-0 pt-0.5 text-xs tabular-nums text-muted">{fmtDuration(s.start_s)}</span>
                    <span className={cn(largeType ? "text-lg" : "", s.flags?.includes("late") && "italic")}>
                      <TranscriptText seg={s} showOriginal={showOriginal} onChange={(n) => setSegments((all) => all.map((x) => (x.id === n.id ? n : x)))} />
                    </span>
                  </li>
                ))}
              </ol>
            )}
            <div ref={transcriptEnd} />
          </section>
        </div>

        {/* context column */}
        <aside className="flex min-h-0 flex-col gap-3 overflow-y-auto">
          {isLive && (
            <Card className="space-y-2">
              {!recording ? (
                <>
                  <Button size="lg" className="w-full bg-unsicher text-white" onClick={startRecording} disabled={hasGroq === false}>
                    <Mic className="h-5 w-5" /> Mikrofon starten
                  </Button>
                  {hasGroq === false && (
                    <Notice tone="warn">fehlt: Groq-Key für Spracherkennung. <Link className="underline" href="/settings">Key eingeben</Link> – oder Demo nutzen.</Notice>
                  )}
                  <Button variant="outline" className="w-full" onClick={demoRunning ? () => (demoStop.current = true) : runDemo}>
                    {demoRunning ? <><Pause className="h-4 w-4" /> Demo anhalten</> : <><Play className="h-4 w-4" /> Demo-Vorlesung abspielen</>}
                  </Button>
                </>
              ) : (
                <div className="flex items-center gap-3">
                  <span className="rec-pulse h-4 w-4 rounded-full bg-unsicher" />
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                    <div className="h-full bg-sicher transition-all" style={{ width: `${(rs?.level || 0) * 100}%` }} />
                  </div>
                  <span className="text-xs text-muted">{rs?.uploaded} ↑</span>
                </div>
              )}
              <Button variant="danger" className="w-full" onClick={finish}>
                <Square className="h-4 w-4" /> Beenden & nachbereiten
              </Button>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="flex-1" onClick={() => participate("answered")}>
                  <Hand className="h-4 w-4" /> Gemeldet
                </Button>
                <Button variant="outline" size="sm" className="flex-1" onClick={() => participate("asked")}>
                  Gefragt
                </Button>
                <Badge className="self-center">{partCount}×</Badge>
              </div>
            </Card>
          )}
          {!isLive && rec.status !== "live" && (
            <Card className="space-y-2">
              <p className="text-sm text-muted">Nachbereitung: {rec.package_status === "done" ? "fertig" : rec.package_status === "queued" ? <><Loader2 className="inline h-3 w-3 animate-spin" /> läuft</> : "—"}</p>
              {rec.module_id && <Link href={`/modules/${rec.module_id}?tab=lectures`} className="text-primary underline">Zusammenfassung & Karten im Modul</Link>}
              <p className="text-sm text-muted">Wortmeldungen: {partCount}</p>
            </Card>
          )}
          {slide && (
            <Card>
              <p className="mb-1 flex items-center gap-1.5 text-sm font-semibold"><FileText className="h-4 w-4" /> Aktuelle Folie</p>
              <button className="text-left" onClick={() => setSrc({ type: "material", label: slide.label, excerpt: slide.excerpt, document_id: slide.document_id, page: slide.page })}>
                <p className="text-sm font-medium text-primary">{slide.label}</p>
                <p className="line-clamp-4 text-sm text-muted">{slide.excerpt}</p>
              </button>
            </Card>
          )}
          {statutes.length > 0 && (
            <Card>
              <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><BookMarked className="h-4 w-4" /> Normen im Wortlaut</p>
              <ul className="space-y-2">
                {statutes.map((s) => (
                  <li key={s.key}>
                    <button className="w-full text-left" onClick={() => s.found && setSrc({ type: "statute", label: s.label, excerpt: s.excerpt || "", title: s.title, url: s.url, demo: s.demo })}>
                      <p className="text-sm font-medium">{s.label} {s.title ? `– ${s.title.replace(/^§\s*\S+\s*/, "")}` : ""}</p>
                      <p className="line-clamp-3 text-sm text-muted">{s.found ? s.excerpt : "Wortlaut nicht abrufbar (offline?)"}</p>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {suggestions.length > 0 && (
            <Card>
              <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><Lightbulb className="h-4 w-4" /> Fragen an den Dozenten</p>
              <ul className="space-y-1.5 text-sm">
                {suggestions.map((q) => <li key={q}>• {q}</li>)}
              </ul>
            </Card>
          )}
          {numbers.length > 0 && (
            <Card>
              <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><Calculator className="h-4 w-4" /> Zahlen & Fristen</p>
              <ul className="space-y-1 text-sm">
                {numbers.slice(0, 10).map((n, i) => (
                  <li key={i}><b>{n.value}</b> <span className="text-muted">– {n.context}</span></li>
                ))}
              </ul>
            </Card>
          )}
          {keywords.length > 0 && (
            <Card>
              <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><AlertTriangle className="h-4 w-4 text-pruefen" /> Klausurhinweise</p>
              <ul className="space-y-1 text-sm">
                {keywords.map((k, i) => (
                  <li key={i}><span className="tabular-nums text-muted">{fmtDuration(k.at_s)}</span> {k.text}</li>
                ))}
              </ul>
            </Card>
          )}
          {user?.is_demo && isLive && (
            <p className="px-1 text-xs text-muted">Demo: „Demo-Vorlesung abspielen“ speist ein Buchführungs-Skript ein, inklusive Anschlussfrage und Korrektur durch den Dozenten.</p>
          )}
        </aside>
      </div>
      <SourceSheet source={src} onClose={() => setSrc(null)} />
    </div>
  );
}
