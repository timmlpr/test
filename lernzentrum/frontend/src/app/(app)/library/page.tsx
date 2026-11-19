"use client";
// Library: full-text + semantic search across everything with jump-to location, document list with filters.
import { BookMarked, FileText, Mic, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { SourceSheet } from "@/components/answer-card";
import { PageHeader } from "@/components/app-shell";
import { UploadZone } from "@/components/connect";
import { Badge, Button, Card, Empty, Input, ModuleChip, Select, Spinner } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { fmtDate, KIND_LABEL, CHANNEL_LABEL } from "@/lib/format";
import type { Doc, Module, Source } from "@/lib/types";

interface Hit extends Source { module: string | null; color: string | null; score: number }

export default function LibraryPage() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{ hits: Hit[]; statutes: Source[] } | null>(null);
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [mods, setMods] = useState<Module[]>([]);
  const [mid, setMid] = useState("");
  const [kind, setKind] = useState("");
  const [src, setSrc] = useState<Source | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<Module[]>("/modules").then(setMods);
  }, []);
  useEffect(() => {
    api.get<Doc[]>(`/documents${qs({ module_id: mid, kind })}`).then(setDocs);
  }, [mid, kind]);
  const modById = Object.fromEntries(mods.map((m) => [m.id, m]));

  const doSearch = async () => {
    setBusy(true);
    try {
      setResults(await api.get(`/search${qs({ q, module_id: mid })}`));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Bibliothek" subtitle="Alles durchsuchbar – Folien, Skripte, Notizen (auch Handschrift) und Aufnahmen." />
      <Card className="mb-4">
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim()) doSearch(); }}>
          <Input className="min-w-[240px] flex-[3]" placeholder="z. B. Was hat der Dozent über § 15 EStG gesagt?" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Suche" />
          <Select className="min-w-[150px] flex-1" value={mid} onChange={(e) => setMid(e.target.value)}>
            <option value="">Alle Module</option>
            {mods.map((m) => <option key={m.id} value={m.id}>{m.short} – {m.name}</option>)}
          </Select>
          <Button type="submit" loading={busy}><Search className="h-4 w-4" /> Suchen</Button>
        </form>
      </Card>
      {results && (
        <Card className="mb-6">
          <p className="mb-2 font-semibold">{results.hits.length} Treffer</p>
          {results.statutes.map((s, i) => (
            <button key={`s${i}`} onClick={() => setSrc(s)} className="mb-2 flex w-full items-start gap-3 rounded-xl bg-surface-2 p-3 text-left">
              <BookMarked className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
              <div><p className="font-medium">{s.label}</p><p className="line-clamp-2 text-sm text-muted">{s.excerpt}</p></div>
            </button>
          ))}
          <ul className="divide-y divide-border">
            {results.hits.map((h) => (
              <li key={h.chunk_id as unknown as number}>
                <button onClick={() => setSrc(h)} className="flex w-full items-start gap-3 py-3 text-left">
                  {h.start_s != null ? <Mic className="mt-0.5 h-5 w-5 shrink-0 text-muted" /> : <FileText className="mt-0.5 h-5 w-5 shrink-0 text-muted" />}
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 font-medium"><ModuleChip short={h.module} color={h.color} /><span className="truncate">{h.label}</span></p>
                    <p className="line-clamp-2 text-sm text-muted">{h.excerpt}</p>
                  </div>
                  <span className="text-xs text-muted">{Math.round(h.score * 100)} %</span>
                </button>
              </li>
            ))}
          </ul>
          {results.hits.length === 0 && results.statutes.length === 0 && <p className="text-muted">Nichts gefunden.</p>}
        </Card>
      )}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-lg font-semibold">Dokumente</h2>
        <Select className="w-44" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Alle Arten</option>
          {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </div>
      {!docs ? <Spinner /> : docs.length === 0 ? (
        <Card><Empty title="Noch keine Dokumente"><UploadZone /></Empty></Card>
      ) : (
        <Card>
          <ul className="divide-y divide-border">
            {docs.map((d) => (
              <li key={d.id}>
                <Link href={`/library/${d.id}`} className="flex items-center gap-3 py-2.5">
                  {d.kind === "audio" || d.kind === "transcript" ? <Mic className="h-5 w-5 text-muted" /> : <FileText className="h-5 w-5 text-muted" />}
                  <ModuleChip short={d.module_id ? modById[d.module_id]?.short : null} color={d.module_id ? modById[d.module_id]?.color : null} />
                  <span className="min-w-0 flex-1 truncate">{d.title}</span>
                  <span className="hidden text-sm text-muted md:inline">{fmtDate(d.doc_date)}</span>
                  <Badge>{KIND_LABEL[d.kind] || d.kind}</Badge>
                  <span className="hidden text-xs text-muted lg:inline">{CHANNEL_LABEL[d.source] || d.source}</span>
                  {d.needs_review && <Badge color="var(--pruefen)">prüfen</Badge>}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <SourceSheet source={src} onClose={() => setSrc(null)} />
    </>
  );
}
