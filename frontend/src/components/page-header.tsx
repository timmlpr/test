"use client";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Badge } from "./ui/badge";
import { buttonVariants } from "./ui/button";
import { useT } from "@/lib/i18n";

/** Every screen: title, a one–two sentence explanation, and exactly one recommended next step. */
export function PageHeader({ title, explain, next, premium, demo }: {
  title: string; explain: string; next?: { label: string; href?: string; onClick?: () => void }; premium?: boolean; demo?: boolean;
}) {
  const { t } = useT();
  return (
    <header className="mb-6 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-bold sm:text-3xl">{title}</h1>
        {premium && <Badge>{t("common.premium")}</Badge>}
        {demo && <Badge variant="warn">{t("common.demo")}</Badge>}
      </div>
      <p className="max-w-2xl text-muted-foreground">{explain}</p>
      {next && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-primary/20 bg-primary/5 p-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-primary">{t("common.nextStep")}</span>
          {next.href ? (
            <Link href={next.href} className={buttonVariants({ size: "sm", className: "h-auto whitespace-normal py-2 text-left" })}>{next.label}<ArrowRight className="h-4 w-4" /></Link>
          ) : (
            <button onClick={next.onClick} className={buttonVariants({ size: "sm", className: "h-auto whitespace-normal py-2 text-left" })}>{next.label}<ArrowRight className="h-4 w-4" /></button>
          )}
        </div>
      )}
    </header>
  );
}
