"use client";
import Link from "next/link";
import { Lock } from "lucide-react";
import { Alert } from "./ui/misc";
import { buttonVariants } from "./ui/button";
import { ApiError } from "@/lib/api";
import { errText, useT } from "@/lib/i18n";
import { plans } from "@/lib/brand";
import { eur } from "@/lib/utils";

export function ErrorNotice({ error }: { error: ApiError | null | undefined }) {
  const { t } = useT();
  if (!error) return null;
  if (error.code === "premium_required" || error.code === "purchase_required") return <PremiumGate />;
  const msg = (error.data as any)?.message_de || errText(t, error.code);
  return <Alert kind="bad">{msg}</Alert>;
}

export function PremiumGate() {
  const { t } = useT();
  return (
    <div className="rounded-lg border border-primary/30 bg-primary/5 p-6 text-center">
      <Lock className="mx-auto mb-2 h-6 w-6 text-primary" aria-hidden />
      <h2 className="font-semibold">{t("gate.title")}</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{t("gate.text", { price: eur(plans.plans.premium.price_month) })}</p>
      <Link href="/app/billing" className={buttonVariants({ className: "mt-4" })}>{t("gate.cta")}</Link>
    </div>
  );
}
