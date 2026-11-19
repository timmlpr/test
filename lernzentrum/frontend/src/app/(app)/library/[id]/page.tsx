"use client";
// Document view: page texts with jump-to page, original file, assignment, notes enhancer.
import { ExternalLink, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useApp } from "@/components/providers";
import { Badge, Button, Card, CardTitle, cn, Label, Notice, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtBytes, fmtDate, fmtDuration, KIND_LABEL } from "@/lib/format";
import type { Doc, Module } from "@/lib/types";

interface Full extends Doc { text: string; page_texts: { page: number; text: string }[] }

function DocInner() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const { toast } = useApp();
  const [doc, setDoc] = useState<Full | null>(null);
  const [mods, setMods] = useState<Module[]>([]);
  const [adds, setAdds] = useState<{ recording_id: number; start_s: number; text: string; important: boolean }[] | null>(null);
  const page = Number(search.get("page") || 0);

  useEffect(() => {
    api.get<Full>(`/documents/${id}`).then(setDoc).catch((e) => toast(e.message, "error"));
    api.get<Module[]>("/modules").then(setMods);
  }, [id, toast]);
  useEffect(() => {
    if (page && doc) document.getElementById(`page-${page}`)?.scrollIntoView({ block: "start" });
  }, [page, doc]);
  if (!doc) return <Spinner />;

  const assign = async (patch: Record<string, unknown>) => {
    const d = await api.patch<Doc>(`/documents/${id}`, patch);
    setDoc({ ...doc, ...d });
    toast("Zuordnung gespeichert", "ok");
  };
  const enhance = async () => setAdds((await api.get<{ additions: typeof adds }>(`/learn/notes/${id}/enhance`)).additions);
  const remove = async () => {
    if (!confirm("Dokument löschen?")) return;
    await api.del(`/documents/${id}`);
    router.replace("/library");
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto min-w-0 truncate text-xl font-bold">{doc.title}</h1>
        <a href={`/api/documents/${id}/file`} target="_blank" rel="noreferrer"><Button variant="outline" size="sm"><ExternalLink className="h-4 w-4" /> Original</Button></a>
        <Button variant="outline" size="sm" onClick={() => api.post(`/documents/${id}/reprocess`).then(() => toast("Wird neu verarbeitet", "ok"))}><RefreshCw className="h-4 w-4" /> Neu einlesen</Button>
        <Button variant="ghost" size="sm" onClick={remove} aria-label="Löschen"><Trash2 className="h-4 w-4" /></Button>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <Card className="min-w-0">
          {doc.page_texts.length === 0 ? (
            <p className="whitespace-pre-line text-sm leading-relaxed">{doc.text || "Kein Text erkannt."}</p>
          ) : (
            <ol className="space-y-4">
              {doc.page_texts.map((p) => (
                <li key={p.page} id={`page-${p.page}`} className={cn("scroll-mt-4 rounded-xl border p-3", p.page === page ? "border-primary bg-primary/5" : "border-border")}>
                  <p className="mb-1 text-xs font-semibold text-muted">{doc.kind === "slides" ? "Folie" : "Seite"} {p.page}</p>
                  <p className="whitespace-pre-line text-[0.95rem] leading-relaxed">{p.text}</p>
                </li>
              ))}
            </ol>
          )}
        </Card>
        <div className="space-y-4">
          <Card className="space-y-3">
            <CardTitle>Zuordnung</CardTitle>
            {doc.needs_review && <Notice tone="warn">{doc.review_reason}</Notice>}
            <div>
              <Label>Modul</Label>
              <Select value={doc.module_id ?? ""} onChange={(e) => assign({ module_id: e.target.value ? Number(e.target.value) : 0 })}>
                <option value="">– keins –</option>
                {mods.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </Select>
            </div>
            <div>
              <Label>Art</Label>
              <Select value={doc.kind} onChange={(e) => assign({ kind: e.target.value })}>
                {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
            </div>
            <dl className="grid grid-cols-2 gap-1 text-sm">
              <dt className="text-muted">Datum</dt><dd>{fmtDate(doc.doc_date) || "–"}</dd>
              <dt className="text-muted">Seiten</dt><dd>{doc.pages}</dd>
              <dt className="text-muted">Größe</dt><dd>{fmtBytes(doc.size)}</dd>
              <dt className="text-muted">Version</dt><dd>{doc.version}</dd>
              <dt className="text-muted">Erkennung</dt><dd>{String(doc.meta.extract || "–")}</dd>
              <dt className="text-muted">Original</dt><dd className="truncate">{doc.original_name}</dd>
            </dl>
            {doc.status_detail && <Notice>{doc.status_detail}</Notice>}
            {doc.recording_id && <Link href={`/live/${doc.recording_id}`} className="text-sm text-primary underline">Zur Aufnahme</Link>}
          </Card>
          {(doc.kind === "notes" || doc.kind === "photo") && (
            <Card className="space-y-2">
              <CardTitle>Notizen ergänzen</CardTitle>
              <p className="text-sm text-muted">Zeigt, was in der Vorlesung gesagt wurde, aber in deinen Notizen fehlt.</p>
              <Button variant="outline" onClick={enhance}><Sparkles className="h-4 w-4" /> Ergänzungen finden</Button>
              {adds && (adds.length === 0 ? <p className="text-sm text-muted">Nichts Fehlendes gefunden.</p> : (
                <ul className="space-y-2 text-sm">
                  {adds.map((a, i) => (
                    <li key={i} className={cn("rounded-lg p-2", a.important ? "bg-pruefen-bg" : "bg-surface-2")}>
                      <Link className="text-primary" href={`/live/${a.recording_id}?t=${Math.floor(a.start_s)}`}>{fmtDuration(a.start_s)}</Link> {a.text}
                      {a.important && <Badge className="ml-1">wichtig</Badge>}
                    </li>
                  ))}
                </ul>
              ))}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DocPage() {
  return <Suspense><DocInner /></Suspense>;
}
