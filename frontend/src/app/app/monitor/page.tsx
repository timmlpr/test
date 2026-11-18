"use client";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { ErrorNotice, PremiumGate } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

const b64ToU8 = (s: string) => Uint8Array.from(atob((s + "===".slice((s.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

export default function Monitor() {
  const { t } = useT();
  const { user } = useAuth();
  const { data } = useApi<any>("/monitor/settings");
  const [s, setS] = useState<any>(null);
  const [res, setRes] = useState<any>(null);
  const [saved, setSaved] = useState(false);
  const { run, busy, error } = useAction();
  useEffect(() => { if (data) setS(data); }, [data]);
  if (user?.tier !== "premium") return <div><PageHeader title={t("mon.title")} explain={t("mon.explain")} premium /><PremiumGate /></div>;
  if (!s) return null;
  const save = () => run(async () => { const { vapid_public_key, last_run, ...body } = s; await api("/monitor/settings", { method: "PUT", body }); setSaved(true); });
  const enablePush = () => run(async () => {
    if (!("serviceWorker" in navigator) || !data.vapid_public_key) throw new Error("push_unavailable");
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return;
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(data.vapid_public_key) as BufferSource });
    const j = sub.toJSON();
    await api("/push/subscribe", { body: { endpoint: j.endpoint, keys: j.keys } });
    await api("/profile/consent", { body: { kind: "push", granted: true } });
  });
  return (
    <div className="space-y-6">
      <PageHeader title={t("mon.title")} explain={t("mon.explain")} premium next={!s.enabled ? { label: t("mon.enabled"), onClick: () => setS({ ...s, enabled: true }) } : { label: t("mon.run"), onClick: () => run(async () => setRes(await api("/monitor/run", { method: "POST" }))) }} />
      <Card><CardContent className="space-y-4 pt-5">
        <Switch checked={s.enabled} onChange={(v) => setS({ ...s, enabled: v })} label={t("mon.enabled")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("mon.frequency")} htmlFor="mf"><Select id="mf" value={s.frequency} onChange={(e) => setS({ ...s, frequency: e.target.value })}><option value="daily">{t("mon.daily")}</option><option value="weekly">{t("mon.weekly")}</option></Select></Field>
          <Field label={t("mon.severity")} htmlFor="ms"><Select id="ms" value={s.min_severity} onChange={(e) => setS({ ...s, min_severity: e.target.value })}>{["low", "medium", "high"].map((r) => <option key={r} value={r}>{t(`risk.${r}`)}</option>)}</Select></Field>
          <Field label={`${t("mon.quiet")} – von (Uhr)`} htmlFor="qs"><Input id="qs" type="number" min={0} max={23} value={s.quiet_start} onChange={(e) => setS({ ...s, quiet_start: +e.target.value })} /></Field>
          <Field label="bis (Uhr)" htmlFor="qe"><Input id="qe" type="number" min={0} max={23} value={s.quiet_end} onChange={(e) => setS({ ...s, quiet_end: +e.target.value })} /></Field>
        </div>
        <Switch checked={s.email} onChange={(v) => setS({ ...s, email: v })} label={t("mon.email")} />
        <Switch checked={s.push} onChange={(v) => setS({ ...s, push: v })} label={t("mon.push")} />
        {s.push && data.vapid_public_key && <Button variant="outline" size="sm" onClick={enablePush}>{t("mon.pushEnable")}</Button>}
        {s.push && !data.vapid_public_key && <p className="text-xs text-muted-foreground">Push ist auf diesem Server noch nicht eingerichtet (VAPID-Schlüssel fehlen). E-Mail funktioniert.</p>}
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={save} disabled={busy}>{t("common.save")}</Button>
          <Button variant="outline" disabled={busy} onClick={() => run(async () => setRes(await api("/monitor/run", { method: "POST" })))}>{t("mon.run")}</Button>
          <span className="text-sm text-muted-foreground">{t("mon.last")}: {fmtDate(s.last_run, true)}</span>
        </div>
        {saved && <Alert kind="ok">Gespeichert.</Alert>}
        {res && <Alert kind="ok">{res.new} neue Funde, {res.alerted} Benachrichtigung(en).</Alert>}
        <ErrorNotice error={error} />
      </CardContent></Card>
    </div>
  );
}
