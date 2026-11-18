"use client";
import { Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { Tabs } from "./ui/misc";
import { ErrorNotice } from "./notice";
import { useAuth } from "./providers";
import { plans, brand } from "@/lib/brand";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { eur } from "@/lib/utils";
import { useT } from "@/lib/i18n";

/** Family price per person shown transparently. Numbers come only from config/plans.json. */
export function familyPrice(persons: number, interval: "month" | "year") {
  const f = plans.plans.family;
  const monthly = f.price_month + f.extra_person_month * (persons - f.included_persons);
  const total = interval === "month" ? monthly : monthly * f.annual_months_charged;
  return { total: Math.round(total * 100) / 100, perPerson: Math.round((total / persons) * 100) / 100 };
}

const FREE = ["Basis-Scan (Name + E-Mail-Lecks)", "Leck-Check 1× pro Monat", "Passwort-Check", "Sicherheits- und Social-Media-Checkliste",
  "Betrugs- und Domain-Check (Tageslimit)", "Lösch-Anfragen als Text", "Report-Vorschau"];
const PREMIUM = ["Alles aus Kostenlos", "Überwachung mit Benachrichtigung", "Tiefen-Scan", "KI-Assistent (anonymisiert)", "Lösch-Anfragen als PDF + Fristen-Tracker",
  "Abo-Wächter", "Dokumenten-Scanner", "Digitaler Nachlass (Ende-zu-Ende verschlüsselt)", "Daten-Netz", "Vollständige Reports (PDF/Excel)"];

export function Pricing() {
  const { t } = useT();
  const { user } = useAuth();
  const router = useRouter();
  const [interval, setInterval] = useState<"month" | "year">("month");
  const [persons, setPersons] = useState(plans.plans.family.included_persons);
  const { run, busy, error } = useAction();
  const fam = familyPrice(persons, interval);
  const prem = interval === "month" ? plans.plans.premium.price_month : plans.plans.premium.price_year;
  const per = interval === "month" ? t("bill.month") : t("bill.year");

  const buy = (product: string) => {
    if (!user) return router.push(`/register?plan=${product}`);
    run(async () => {
      const r = await api<{ url: string }>("/billing/checkout", { body: { product, interval, persons } });
      location.href = r.url;
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-center"><div className="w-64"><Tabs value={interval} onChange={(v) => setInterval(v as "month" | "year")}
        tabs={[{ id: "month", label: "Monatlich" }, { id: "year", label: "Jährlich (2 Monate gratis)" }]} /></div></div>
      <ErrorNotice error={error} />
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <PlanCard title={t("plan.free")} price={eur(0)} per={per} items={FREE} cta={user ? "Aktiv" : t("landing.hero.cta")} onClick={() => router.push(user ? "/app" : "/register")} />
        <PlanCard title={t("plan.premium")} price={eur(prem)} per={per} items={PREMIUM} highlight={plans.most_popular === "premium"}
          note={t("bill.trial", { n: plans.trial_days })} cta={t("bill.choose")} onClick={() => buy("premium")} busy={busy} />
        <PlanCard title={t("plan.family")} price={eur(fam.total)} per={per} highlight={plans.most_popular === "family"}
          items={[`${eur(fam.perPerson)} ${t("bill.perPerson")} bei ${persons} Personen`, "Alles aus Premium für jede Person", "Jede Person mit eigenem Login", "Kinderprofile mit Elternzustimmung"]}
          note={t("bill.trial", { n: plans.trial_days })} cta={t("bill.choose")} onClick={() => buy("family")} busy={busy}>
          <label className="block text-sm">
            <span className="mb-1 block">{t("bill.persons")}: <strong>{persons}</strong></span>
            <input type="range" min={plans.plans.family.included_persons} max={plans.plans.family.max_persons} value={persons}
              onChange={(e) => setPersons(+e.target.value)} className="w-full accent-[hsl(var(--primary))]" aria-label={t("bill.persons")} />
          </label>
        </PlanCard>
        <PlanCard title={t("plan.onetime")} price={eur(plans.one_time_report.price)} per="einmalig"
          items={["Vollständiger Report als PDF", "Auffindbarkeit, Lecks, Risiko-Wert", "Lösch-Plan nach Wirkung sortiert", "Nur deine eigenen Daten", "Kein Abo"]}
          cta={t("bill.choose")} onClick={() => buy("one_time_report")} busy={busy} />
      </div>
      <p className="text-center text-xs text-muted-foreground">
        {plans.prices_include_vat ? t("bill.inclVat") : ""} {brand.operator.small_business ? t("bill.smallBusiness") : ""} Kündigung jederzeit mit einem Klick.
      </p>
    </div>
  );
}

function PlanCard({ title, price, per, items, cta, onClick, highlight, note, busy, children }: {
  title: string; price: string; per: string; items: string[]; cta: string; onClick: () => void; highlight?: boolean; note?: string; busy?: boolean; children?: React.ReactNode;
}) {
  return (
    <Card className={highlight ? "border-primary ring-2 ring-primary/30" : ""}>
      <CardHeader>
        <div className="flex items-center justify-between"><CardTitle>{title}</CardTitle>{highlight && <Badge>Am beliebtesten</Badge>}</div>
        <p className="text-3xl font-bold">{price}<span className="text-sm font-normal text-muted-foreground"> / {per}</span></p>
        {note && <CardDescription>{note}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-4">
        {children}
        <ul className="space-y-2 text-sm">{items.map((i) => <li key={i} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />{i}</li>)}</ul>
        <Button className="w-full" variant={highlight ? "default" : "outline"} onClick={onClick} disabled={busy}>{cta}</Button>
      </CardContent>
    </Card>
  );
}
