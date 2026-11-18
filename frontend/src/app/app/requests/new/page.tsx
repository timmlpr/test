"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice } from "@/components/notice";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";

function NewRequest() {
  const { t } = useT();
  const router = useRouter();
  const fid = useSearchParams().get("finding");
  const tpl = useApi<any>("/requests/templates");
  const findings = useApi<any>(fid ? "/findings?status=all" : null);
  const f = findings.data?.items.find((x: any) => x.id === fid);
  const [form, setForm] = useState({ kind: "art17", recipient: "", recipient_email: "", template: "generic", url: "", days: 30 });
  const { run, busy, error } = useAction();
  useEffect(() => {
    if (!f) return;
    let host = "";
    try { host = f.url ? new URL(f.url).hostname : ""; } catch {}
    setForm((s) => ({ ...s, recipient: f.details?.service || host || s.recipient, url: f.url || "", template: f.module === "breach_check" ? "breach" : "generic" }));
  }, [f]);
  return (
    <div>
      <PageHeader title={t("req.new")} explain={t("req.explain")} />
      {f && <Alert className="mb-4">Für den Fund: <strong>{f.title}</strong></Alert>}
      <form className="max-w-xl space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => {
        const r = await api<any>("/requests", { body: { ...form, recipient_email: form.recipient_email || null, url: form.url || null, finding_id: fid } });
        router.push(`/app/requests?id=${r.id}`);
      }); }}>
        <Field label={t("req.kind")} htmlFor="k"><Select id="k" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
          <option value="art17">{t("req.art17")}</option><option value="art15">{t("req.art15")}</option><option value="art16">{t("req.art16")}</option></Select></Field>
        <Field label={t("req.template")} htmlFor="tp"><Select id="tp" value={form.template} onChange={(e) => setForm({ ...form, template: e.target.value })}>
          {Object.entries(tpl.data?.templates ?? {}).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}</Select></Field>
        <Field label={t("req.recipient")} htmlFor="rc"><Input id="rc" required value={form.recipient} onChange={(e) => setForm({ ...form, recipient: e.target.value })} /></Field>
        <Field label={t("req.recipientEmail")} htmlFor="re" hint="Steht meist in der Datenschutzerklärung der Website."><Input id="re" type="email" value={form.recipient_email} onChange={(e) => setForm({ ...form, recipient_email: e.target.value })} /></Field>
        <Field label={t("req.url")} htmlFor="u"><Input id="u" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></Field>
        <Field label={`${t("req.due")} (Tage)`} htmlFor="d" hint="Gesetzlich gilt grundsätzlich ein Monat (Art. 12 Abs. 3 DSGVO)."><Input id="d" type="number" min={7} max={90} value={form.days} onChange={(e) => setForm({ ...form, days: +e.target.value })} /></Field>
        <ErrorNotice error={error} />
        <Button disabled={busy}>{t("req.create")}</Button>
        <p className="text-xs text-muted-foreground">{t("req.disclaimer")}</p>
      </form>
    </div>
  );
}
export default function Page() { return <Suspense><NewRequest /></Suspense>; }
