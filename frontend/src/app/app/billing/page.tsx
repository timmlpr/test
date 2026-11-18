"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, Dialog } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";
import { Pricing } from "@/components/pricing";
import { ErrorNotice } from "@/components/notice";
import { useAuth } from "@/components/providers";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { fmtDate } from "@/lib/utils";

function Billing() {
  const { t } = useT();
  const { user, refresh } = useAuth();
  const status = useSearchParams().get("status");
  const st = useApi<any>("/billing/status");
  const ref = useApi<any>("/billing/referral");
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [voucher, setVoucher] = useState("");
  const { run, busy, error } = useAction();
  const active = st.data?.subscriptions.find((s: any) => ["active", "trialing", "past_due"].includes(s.status));
  return (
    <div className="space-y-6">
      <PageHeader title={t("bill.title")} explain={t("bill.explain")}
        next={active ? { label: t("bill.referral"), href: "#referral" } : { label: t("gate.cta"), href: "#plans" }} />
      {status === "success" && <Alert kind="ok">Danke! Dein Tarif wird aktiviert, sobald die Zahlung bestätigt ist (meist sofort).</Alert>}
      {msg && <Alert kind="ok">{msg}</Alert>}
      <Card>
        <CardHeader><CardTitle className="text-base">{t("bill.current")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xl font-semibold">{t(`plan.${user?.plan ?? "free"}`)} {user?.tier === "premium" && <Badge>{t("common.premium")}</Badge>}</p>
          {active && <p className="text-sm text-muted-foreground">Status: {active.status} · {active.cancel_at_period_end ? "endet" : "nächste Verlängerung"} am {fmtDate(active.current_period_end)}</p>}
          {!!st.data?.free_months_credit && <p className="text-sm">Guthaben: {st.data.free_months_credit} Gratis-Monat(e) – wird beim nächsten Abschluss angerechnet.</p>}
          <div className="flex flex-wrap gap-2">
            {active && !active.cancel_at_period_end && <Button variant="destructive" onClick={() => setConfirm(true)}>{t("bill.cancel")}</Button>}
            {st.data?.stripe && <Button variant="outline" onClick={() => run(async () => { location.href = (await api<any>("/billing/portal", { method: "POST" })).url; })}>{t("bill.portal")}</Button>}
          </div>
          <ErrorNotice error={error} />
        </CardContent>
      </Card>
      <Dialog open={confirm} onClose={() => setConfirm(false)} title={t("bill.cancel")}>
        <p className="mb-4 text-sm">{t("bill.cancelConfirm")}</p>
        <div className="flex gap-2">
          <Button variant="destructive" disabled={busy} onClick={() => run(async () => { await api("/billing/cancel", { method: "POST" }); setConfirm(false); setMsg(t("bill.canceled")); st.reload(); refresh(); })}>{t("bill.cancel")}</Button>
          <Button variant="outline" onClick={() => setConfirm(false)}>{t("common.back")}</Button>
        </div>
      </Dialog>
      <section id="plans"><Pricing /></section>
      <div className="grid gap-4 md:grid-cols-2">
        <Card id="referral">
          <CardHeader><CardTitle className="text-base">{t("bill.referral")}</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>{t("bill.referralText", { n: ref.data?.free_months ?? 1 })}</p>
            {ref.data && <div className="flex gap-2"><Input readOnly value={ref.data.link} aria-label="Einladungslink" />
              <Button variant="outline" size="icon" aria-label={t("common.copy")} onClick={() => navigator.clipboard.writeText(ref.data.link)}><Copy className="h-4 w-4" /></Button></div>}
            {ref.data && <p className="text-muted-foreground">Eingeladen: {ref.data.invited} · belohnt: {ref.data.rewarded}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">{t("bill.voucher")}</CardTitle></CardHeader>
          <CardContent>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { const r = await api<any>("/billing/voucher", { body: { code: voucher } }); setMsg(`+${r.added} Gratis-Monat(e)`); setVoucher(""); st.reload(); }); }}>
              <Input value={voucher} onChange={(e) => setVoucher(e.target.value)} placeholder="CODE" aria-label={t("bill.voucher")} />
              <Button disabled={!voucher || busy}>{t("common.save")}</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
export default function Page() { return <Suspense><Billing /></Suspense>; }
