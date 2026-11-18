"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type SimulationNodeDatum } from "d3-force";
import { Download, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input, Select } from "@/components/ui/input";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

type N = SimulationNodeDatum & { id: string; label: string; type: string; risk?: string; url?: string };
type E = { source: string | N; target: string | N; label: string };
const COLOR: Record<string, string> = { me: "#2563eb", email: "#0ea5e9", name: "#6366f1", phone: "#8b5cf6", city: "#14b8a6", username: "#06b6d4", domain: "#0891b2",
  breach: "#dc2626", source: "#f59e0b", family: "#10b981" };
const W = 800, H = 560;
const TYPE_DE: Record<string, string> = { me: "Ich", email: "E-Mail", name: "Name", phone: "Telefon", city: "Wohnort", username: "Benutzername", domain: "Domain", breach: "Datenleck", source: "Fundstelle", family: "Familie" };

export default function Graph() {
  const { t } = useT();
  const { data, error, reload } = useApi<{ nodes: N[]; edges: E[] }>("/graph");
  const [types, setTypes] = useState<Record<string, boolean>>({});
  const [target, setTarget] = useState("");
  const [pos, setPos] = useState<Record<string, { x: number; y: number }>>({});
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const [fam, setFam] = useState({ label: "", relation: "partner", consent_confirmed: false });
  const tree = useApi<any[]>("/graph/family");
  const { run, error: e2 } = useAction();

  const visible = useMemo(() => {
    if (!data) return { nodes: [] as N[], edges: [] as E[] };
    const nodes = data.nodes.filter((n) => types[n.type] !== false);
    const ids = new Set(nodes.map((n) => n.id));
    return { nodes, edges: data.edges.filter((e) => ids.has(e.source as string) && ids.has(e.target as string)) };
  }, [data, types]);

  useEffect(() => {
    const nodes = visible.nodes.map((n) => ({ ...n }));
    const edges = visible.edges.map((e) => ({ ...e }));
    const sim = forceSimulation(nodes).force("link", forceLink<N, any>(edges).id((d) => d.id).distance(90))
      .force("charge", forceManyBody().strength(-260)).force("center", forceCenter(W / 2, H / 2)).force("collide", forceCollide(28)).stop();
    for (let i = 0; i < 250; i++) sim.tick();
    setPos(Object.fromEntries(nodes.map((n) => [n.id, { x: n.x!, y: n.y! }])));
  }, [visible]);

  // Path search (BFS) from "me" to the chosen node: "which source holds which data".
  const path = useMemo(() => {
    if (!target) return new Set<string>();
    const adj: Record<string, string[]> = {};
    visible.edges.forEach((e) => { const a = e.source as string, b = e.target as string; (adj[a] ||= []).push(b); (adj[b] ||= []).push(a); });
    const prev: Record<string, string> = {}; const q = ["me"]; const seen = new Set(q);
    while (q.length) { const c = q.shift()!; if (c === target) break; for (const n of adj[c] ?? []) if (!seen.has(n)) { seen.add(n); prev[n] = c; q.push(n); } }
    const out = new Set<string>(); let c: string | undefined = target;
    while (c) { out.add(c); c = prev[c]; }
    return out.has("me") ? out : new Set<string>();
  }, [target, visible]);

  const exportPng = () => {
    const s = new XMLSerializer().serializeToString(svg.current!);
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas"); c.width = W * 2; c.height = H * 2;
      const ctx = c.getContext("2d")!; ctx.fillStyle = getComputedStyle(document.body).backgroundColor; ctx.fillRect(0, 0, c.width, c.height); ctx.drawImage(img, 0, 0, c.width, c.height);
      const a = document.createElement("a"); a.download = "daten-netz.png"; a.href = c.toDataURL("image/png"); a.click();
    };
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(s);
  };

  if (error) return <div><PageHeader title={t("graph.title")} explain={t("graph.explain")} premium /><ErrorNotice error={error} /></div>;
  const allTypes = [...new Set((data?.nodes ?? []).map((n) => n.type))];
  return (
    <div className="space-y-6">
      <PageHeader title={t("graph.title")} explain={t("graph.explain")} premium next={{ label: t("graph.export"), onClick: exportPng }} />
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">{t("graph.filter")}:</span>
        {allTypes.map((ty) => <Checkbox key={ty} checked={types[ty] !== false} onChange={(e) => setTypes({ ...types, [ty]: e.target.checked })}
          label={<span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-full" style={{ background: COLOR[ty] ?? "#64748b" }} />{TYPE_DE[ty] ?? ty}</span>} />)}
        <Select value={target} onChange={(e) => setTarget(e.target.value)} className="w-56" aria-label={t("graph.path")}>
          <option value="">{t("graph.path")} …</option>{visible.nodes.filter((n) => n.id !== "me").map((n) => <option key={n.id} value={n.id}>{n.label.slice(0, 40)}</option>)}
        </Select>
        <Button size="sm" variant="outline" onClick={exportPng}><Download className="h-4 w-4" />PNG</Button>
        <Button size="sm" variant="ghost" onClick={() => setView({ k: 1, x: 0, y: 0 })}>Ansicht zurücksetzen</Button>
      </div>
      <Card className="overflow-hidden">
        <svg ref={svg} viewBox={`0 0 ${W} ${H}`} className="h-[60vh] w-full touch-none cursor-grab select-none" role="img" aria-label="Daten-Netz: deine Angaben und die Quellen, die sie kennen"
          onWheel={(e) => { const k = Math.min(3, Math.max(0.4, view.k * (e.deltaY < 0 ? 1.1 : 0.9))); setView({ ...view, k }); }}
          onPointerDown={(e) => (drag.current = { x: e.clientX, y: e.clientY })} onPointerUp={() => (drag.current = null)} onPointerLeave={() => (drag.current = null)}
          onPointerMove={(e) => { if (!drag.current) return; setView((v) => ({ ...v, x: v.x + e.clientX - drag.current!.x, y: v.y + e.clientY - drag.current!.y })); drag.current = { x: e.clientX, y: e.clientY }; }}>
          <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`} style={{ transformOrigin: "center" }}>
            {visible.edges.map((e, i) => { const a = pos[e.source as string], b = pos[e.target as string]; if (!a || !b) return null;
              const on = path.has(e.source as string) && path.has(e.target as string);
              return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={on ? "#2563eb" : "#94a3b8"} strokeWidth={on ? 3 : 1.2} strokeOpacity={on ? 1 : 0.6}><title>{e.label}</title></line>; })}
            {visible.nodes.map((n) => { const p = pos[n.id]; if (!p) return null;
              return (
                <g key={n.id} transform={`translate(${p.x} ${p.y})`} opacity={path.size && !path.has(n.id) ? 0.35 : 1}>
                  <circle r={n.id === "me" ? 18 : 12} fill={COLOR[n.type] ?? "#64748b"} stroke="#fff" strokeWidth={2} />
                  <text y={n.id === "me" ? 32 : 26} textAnchor="middle" style={{ fontSize: 11 }} fill="currentColor" className="fill-foreground">{n.label.length > 26 ? n.label.slice(0, 25) + "…" : n.label}</text>
                  <title>{n.label}{n.url ? `\n${n.url}` : ""}</title>
                </g>); })}
          </g>
        </svg>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">{t("graph.family")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("graph.familyHint")}</p>
          <form className="grid gap-2 sm:grid-cols-[1fr_160px_auto]" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/graph/family", { body: fam }); setFam({ label: "", relation: "partner", consent_confirmed: false }); tree.reload(); reload(); }); }}>
            <Input value={fam.label} onChange={(e) => setFam({ ...fam, label: e.target.value })} required placeholder="Name" aria-label="Name" />
            <Select value={fam.relation} onChange={(e) => setFam({ ...fam, relation: e.target.value })} aria-label="Beziehung">
              {[["parent", "Elternteil"], ["child", "Kind"], ["sibling", "Geschwister"], ["partner", "Partner:in"], ["grandparent", "Großelternteil"], ["grandchild", "Enkel"], ["other", "Andere"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Button disabled={!fam.consent_confirmed}>{t("profile.add")}</Button>
            <div className="sm:col-span-3"><Checkbox checked={fam.consent_confirmed} onChange={(e) => setFam({ ...fam, consent_confirmed: e.target.checked })} label={t("graph.familyConsent")} /></div>
          </form>
          <ErrorNotice error={e2} />
          <ul className="space-y-1 text-sm">{(tree.data ?? []).map((p) => (
            <li key={p.id} className="flex items-center gap-2">{p.label} <span className="text-muted-foreground">({p.relation})</span>
              <button className="ml-auto rounded p-1 hover:bg-muted" aria-label={`${t("common.delete")}: ${p.label}`} onClick={() => run(async () => { await api(`/graph/family/${p.id}`, { method: "DELETE" }); tree.reload(); reload(); })}><Trash2 className="h-4 w-4" /></button></li>))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
