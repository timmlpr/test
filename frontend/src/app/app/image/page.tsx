"use client";
import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

export default function ImageCheck() {
  const { t } = useT();
  const [file, setFile] = useState<File | null>(null);
  const [own, setOwn] = useState(false);
  const [r, setR] = useState<any>(null);
  const { run, busy, error } = useAction();
  const form = () => { const f = new FormData(); f.append("file", file!); f.append("own_image", String(own)); return f; };
  const strip = () => run(async () => {
    const res = await api<Response>("/image/strip", { form: form(), raw: true });
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a"); a.href = url; a.download = "ohne-metadaten" + (file!.type === "image/png" ? ".png" : ".jpg"); a.click();
  });
  return (
    <div className="space-y-6">
      <PageHeader title={t("img.title")} explain={t("img.explain")} next={r?.has_gps ? { label: t("img.strip"), onClick: strip } : undefined} />
      <Card><CardContent className="space-y-4 pt-5">
        <input type="file" accept="image/jpeg,image/png,image/webp,image/heic" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setR(null); }} aria-label={t("img.upload")}
          className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-primary-foreground" />
        <Checkbox checked={own} onChange={(e) => setOwn(e.target.checked)} label={t("img.own")} />
        <div className="flex flex-wrap gap-2">
          <Button disabled={!file || !own || busy} onClick={() => run(async () => setR(await api("/image/analyze", { form: form() })))}>{t("img.analyze")}</Button>
          <Button variant="outline" disabled={!file || !own || busy} onClick={strip}>{t("img.strip")}</Button>
        </div>
        <ErrorNotice error={error} />
      </CardContent></Card>
      {r && (
        <div className="grid gap-4 md:grid-cols-2">
          {r.has_gps && <Alert kind="warn" className="md:col-span-2">{t("img.gps")} ({r.exif.GPS.lat}, {r.exif.GPS.lon})</Alert>}
          <Card><CardHeader><CardTitle className="text-base">{t("img.exif")}</CardTitle></CardHeader><CardContent>
            {Object.keys(r.exif).length === 0 ? <p className="text-sm text-muted-foreground">Keine Metadaten gefunden.</p> :
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">{Object.entries(r.exif).flatMap(([k, v]: any) => [<dt key={`${k}-t`} className="font-mono text-xs text-muted-foreground">{k}</dt>, <dd key={`${k}-d`} className="break-all">{typeof v === "object" ? JSON.stringify(v) : v}</dd>])}</dl>}
          </CardContent></Card>
          <Card><CardHeader><CardTitle className="text-base">{t("img.ela")}</CardTitle></CardHeader><CardContent className="space-y-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={r.ela_image} alt="Fehlerstufen-Analyse: helle Bereiche wurden anders komprimiert" className="w-full rounded-md border" />
            <p className="text-xs text-muted-foreground">Helle Flächen wurden anders komprimiert als der Rest. Das kann auf Bearbeitung hindeuten – oder einfach auf Kanten und Text.</p>
          </CardContent></Card>
          <Card><CardHeader><CardTitle className="text-base">{t("img.ai")}</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
            <ul className="list-disc pl-5">{r.ai_hints.map((h: any, i: number) => <li key={i}>{h.signal} <span className="text-xs text-muted-foreground">({h.weight === "strong" ? "starker Hinweis" : "schwacher Hinweis"})</span></li>)}</ul>
            <p className="text-xs text-muted-foreground">{r.uncertainty}</p>
          </CardContent></Card>
          <Card><CardHeader><CardTitle className="text-base">{t("img.reverse")}</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
            <p className="text-muted-foreground">{t("img.reverseHint")}</p>
            <div className="flex flex-wrap gap-2">{r.reverse_search.map((l: any) => <a key={l.name} href={l.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary underline">{l.name}<ExternalLink className="h-3 w-3" /></a>)}</div>
          </CardContent></Card>
        </div>
      )}
    </div>
  );
}
