"use client";
// Transcript text with Kontext-Korrektur markers: auto corrections subtle, "bitte prüfen" dotted, "unklar" wavy.
// Tap opens an inline panel (never covers the answer area): reason, original, undo/accept/other candidate/always.
import { useState } from "react";
import { api } from "@/lib/api";
import type { CorrectionEdit, Segment } from "@/lib/types";
import { cn } from "./ui";

export function TranscriptText({ seg, showOriginal, onChange }: { seg: Segment; showOriginal: boolean; onChange: (s: Segment) => void }) {
  const [open, setOpen] = useState<CorrectionEdit | null>(null);
  const original = seg.original ?? seg.text;
  const edits = (seg.edits || []).filter((e) => e.kind !== "norm").sort((a, b) => a.start - b.start);
  if (showOriginal || !edits.length) return <span>{showOriginal ? original : seg.text}</span>;

  const act = async (e: CorrectionEdit, action: string, to?: string) => {
    const r = await api.post<Segment>(`/segments/${seg.id}/edits/${e.id}`, { action, to });
    onChange({ ...seg, ...r });
    setOpen(null);
  };

  // rebuild from the original so markers sit exactly on the edited spans
  const parts: React.ReactNode[] = [];
  let last = 0;
  const norm = (seg.edits || []).filter((e) => e.kind === "norm" && ["applied", "check", "accepted"].includes(e.status));
  const plain = (a: number, b: number) => {
    let out = "", i = a;
    for (const n of norm.filter((n) => n.start >= a && n.end <= b)) {
      out += original.slice(i, n.start) + (n.to || "");
      i = n.end;
    }
    return out + original.slice(i, b);
  };
  for (const e of edits) {
    if (e.start < last) continue;
    parts.push(plain(last, e.start));
    const active = ["applied", "check", "accepted"].includes(e.status) && e.to;
    parts.push(
      <button key={e.id} onClick={() => setOpen(open?.id === e.id ? null : e)}
        className={cn("rounded px-0.5 underline-offset-4",
          e.status === "check" && "underline decoration-pruefen decoration-dotted decoration-2",
          e.status === "unclear" && "underline decoration-unsicher decoration-wavy",
          e.status === "applied" && "underline decoration-muted/30 decoration-dotted",
          e.status === "undone" && "line-through decoration-muted/40")}
        aria-label={`Korrektur: ${e.from} → ${e.to ?? "unklar"}`}>
        {active ? e.to : original.slice(e.start, e.end)}
      </button>,
    );
    last = e.end;
  }
  parts.push(plain(last, original.length));

  return (
    <span>
      {parts}
      {open && (
        <span className="mt-1 block rounded-lg border border-border bg-surface-2 p-2 text-sm">
          <span className="block"><b>{open.from}</b> → <b>{open.to ?? "?"}</b> · {open.confidence} %</span>
          <span className="block text-muted">{open.reason}</span>
          <span className="mt-1 flex flex-wrap gap-1.5">
            {["applied", "check", "accepted"].includes(open.status)
              ? <button className="rounded-md border border-border px-2 py-1" onClick={() => act(open, "undo")}>Rückgängig</button>
              : open.to && <button className="rounded-md border border-border px-2 py-1" onClick={() => act(open, "accept")}>Übernehmen</button>}
            {open.status === "check" && <button className="rounded-md border border-border px-2 py-1" onClick={() => act(open, "accept")}>Passt</button>}
            {(open.candidates || []).filter((c) => c.to !== open.to).map((c) => (
              <button key={c.to} className="rounded-md border border-border px-2 py-1" onClick={() => act(open, "choose", c.to)}>{c.to} ({c.confidence} %)</button>
            ))}
            {open.to && <button className="rounded-md border border-border px-2 py-1" onClick={() => act(open, "always")}>Immer so korrigieren</button>}
          </span>
        </span>
      )}
    </span>
  );
}
