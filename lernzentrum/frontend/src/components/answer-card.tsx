"use client";
// Answer card: 3-level color scale + percentage + "why" + exact source locations, correction state and
// candidate readings for ambiguous questions.
import { AlertTriangle, BookMarked, Check, FileText, Mic, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDuration } from "@/lib/format";
import type { AnswerT, Level, Source } from "@/lib/types";
import { Badge, Button, cn, Sheet } from "./ui";

export const LEVEL_STYLE: Record<Level, { color: string; bg: string; label: string }> = {
  SICHER: { color: "var(--sicher)", bg: "var(--sicher-bg)", label: "SICHER" },
  PRÜFEN: { color: "var(--pruefen)", bg: "var(--pruefen-bg)", label: "PRÜFEN" },
  UNSICHER: { color: "var(--unsicher)", bg: "var(--unsicher-bg)", label: "UNSICHER" },
};

export function LevelBadge({ level, percent, big }: { level: Level; percent: number; big?: boolean }) {
  const s = LEVEL_STYLE[level];
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 rounded-full font-bold text-white", big ? "px-3 py-1 text-base" : "px-2 py-0.5 text-xs")}
      style={{ background: s.color }}
    >
      {s.label} {percent} %
    </span>
  );
}

function stripCites(t: string) {
  return t.replace(/\s*\[S\d+(?:,\s*S\d+)*\]/g, "");
}

export function SourceChip({ s, onOpen }: { s: Source; onOpen: (s: Source) => void }) {
  const Icon = s.type === "statute" ? BookMarked : s.start_s != null ? Mic : FileText;
  return (
    <button
      onClick={() => onOpen(s)}
      className="inline-flex min-h-9 max-w-full items-center gap-1.5 rounded-lg border border-border bg-surface px-2 py-1 text-left text-sm hover:bg-surface-2"
    >
      <Icon className="h-4 w-4 shrink-0 text-muted" aria-hidden />
      <span className="truncate">{s.label}</span>
    </button>
  );
}

export function SourceSheet({ source, onClose }: { source: Source | null; onClose: () => void }) {
  if (!source) return null;
  return (
    <Sheet open={!!source} onClose={onClose} title={source.label} wide>
      {source.type === "statute" ? (
        <div className="space-y-3">
          {source.title && <p className="font-semibold">{source.title}</p>}
          <p className="whitespace-pre-line leading-relaxed">{source.excerpt}</p>
          {source.demo && <p className="text-sm text-muted">Demo-Auszug – wird bei Internetverbindung durch den amtlichen Text ersetzt.</p>}
          {source.url && (
            <a className="text-primary underline" href={source.url} target="_blank" rel="noreferrer">
              Amtlicher Text auf gesetze-im-internet.de
            </a>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <p className="rounded-xl bg-surface-2 p-3 leading-relaxed">{source.excerpt}</p>
          {source.start_s != null && source.recording_id ? (
            <a className="inline-flex h-11 items-center rounded-xl bg-primary px-4 font-medium text-primary-fg" href={`/live/${source.recording_id}?t=${Math.floor(source.start_s)}`}>
              Zur Stelle {fmtDuration(source.start_s)} in der Aufnahme springen
            </a>
          ) : source.document_id ? (
            <a className="inline-flex h-11 items-center rounded-xl bg-primary px-4 font-medium text-primary-fg" href={`/library/${source.document_id}${source.page ? `?page=${source.page}` : ""}`}>
              Dokument öffnen{source.page ? ` (Seite ${source.page})` : ""}
            </a>
          ) : null}
        </div>
      )}
    </Sheet>
  );
}

export function AnswerGroup({ answers, mode = "short", big, onFeedback }: { answers: AnswerT[]; mode?: "short" | "detailed"; big?: boolean; onFeedback?: (a: AnswerT) => void }) {
  const [src, setSrc] = useState<Source | null>(null);
  const multiple = answers.length > 1;
  return (
    <div className="space-y-3">
      {multiple && (
        <p className="text-sm font-medium text-muted">
          Mehrdeutig: {answers.map((a) => `„${a.reading}“ (${Math.round(a.probability * 100)} %)`).join(" oder ")}
        </p>
      )}
      <div className={cn("grid gap-3", multiple && "lg:grid-cols-2")}>
        {answers.map((a) => (
          <AnswerCard key={a.id} a={a} mode={mode} big={big} onSource={setSrc} showReading={multiple} onFeedback={onFeedback} />
        ))}
      </div>
      <SourceSheet source={src} onClose={() => setSrc(null)} />
    </div>
  );
}

export function AnswerCard({ a, mode, big, onSource, showReading, onFeedback }: { a: AnswerT; mode: "short" | "detailed"; big?: boolean; onSource: (s: Source) => void; showReading?: boolean; onFeedback?: (a: AnswerT) => void }) {
  const s = LEVEL_STYLE[a.level];
  const [fb, setFb] = useState(a.feedback);
  const text = stripCites(mode === "detailed" ? a.detailed || a.short : a.short);
  const send = async (f: string) => {
    setFb(f);
    const updated = await api.post<AnswerT>(`/answers/${a.id}/feedback`, { feedback: f }).catch(() => null);
    if (updated) onFeedback?.(updated);
  };
  return (
    <article
      className={cn("rounded-2xl border-2 p-4 transition-colors", a.correction && "flash")}
      style={{ borderColor: a.correction ? "var(--unsicher)" : s.color, background: s.bg }}
      aria-label={`Antwort ${s.label} ${a.percent} Prozent`}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <LevelBadge level={a.level} percent={a.percent} big={big} />
        {showReading && <Badge>Lesart {Math.round(a.probability * 100)} %</Badge>}
        {a.engine === "extractive" && <Badge>aus Quellen zusammengestellt</Badge>}
        <span className="ml-auto text-xs text-muted">{a.at_s != null ? fmtDuration(a.at_s) : ""}</span>
      </div>
      <p className={cn("mb-1 text-sm text-muted", big && "text-base")}>
        {showReading ? a.reading : a.question}
      </p>
      <p className={cn("leading-snug", big ? "text-[1.6rem] font-semibold" : "text-lg font-medium")}>{text}</p>
      {a.correction && (
        <div className="mt-3 rounded-xl border border-unsicher/50 bg-surface p-3">
          <p className="flex items-center gap-1.5 font-semibold text-unsicher">
            <AlertTriangle className="h-4 w-4" /> Dozent sagt gerade: „{a.correction.statement}“
          </p>
          <p className="mt-1 text-sm text-muted">{a.correction.reason}</p>
          <p className="mt-2 font-medium">Korrigiert: {a.correction.corrected}</p>
        </div>
      )}
      <p className="mt-2 text-sm text-muted">Warum: {a.why}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {a.sources.length === 0 ? <Badge className="text-unsicher">keine Quelle</Badge> : a.sources.map((src, i) => <SourceChip key={i} s={src} onOpen={onSource} />)}
      </div>
      {onFeedback !== undefined && (
        <div className="mt-3 flex gap-2">
          <Button size="sm" variant={fb === "used" ? "primary" : "outline"} onClick={() => send("used")}>
            <Check className="h-4 w-4" /> Gesagt
          </Button>
          <Button size="sm" variant={fb === "correct" ? "primary" : "ghost"} onClick={() => send("correct")} aria-label="Antwort war richtig">
            <ThumbsUp className="h-4 w-4" />
          </Button>
          <Button size="sm" variant={fb === "wrong" ? "danger" : "ghost"} onClick={() => send("wrong")} aria-label="Antwort war falsch">
            <ThumbsDown className="h-4 w-4" />
          </Button>
        </div>
      )}
    </article>
  );
}
