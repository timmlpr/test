import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badge = cva("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "bg-primary/10 text-primary",
      muted: "bg-muted text-muted-foreground",
      ok: "bg-ok/15 text-ok",
      warn: "bg-warn/15 text-warn",
      bad: "bg-bad/15 text-bad",
      outline: "border",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Badge({ className, variant, ...p }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ variant }), className)} {...p} />;
}

export function RiskBadge({ risk, label }: { risk: string; label: string }) {
  return <Badge variant={risk === "high" ? "bad" : risk === "medium" ? "warn" : "ok"}>{label}</Badge>;
}
