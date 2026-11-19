"use client";
// shadcn-style primitives written in-repo (see PLAN.md). Touch targets ≥ 44 px.
import { cva, type VariantProps } from "class-variance-authority";
import { clsx, type ClassValue } from "clsx";
import { Loader2, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none select-none",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-fg hover:opacity-90 active:opacity-80",
        secondary: "bg-surface-2 text-text hover:bg-border/60 border border-border",
        ghost: "text-text hover:bg-surface-2",
        danger: "bg-unsicher text-white hover:opacity-90",
        outline: "border border-border bg-surface text-text hover:bg-surface-2",
      },
      size: {
        sm: "h-9 px-3 text-sm",
        md: "h-11 px-4 text-[0.95rem]",
        lg: "h-14 px-6 text-lg",
        icon: "h-11 w-11",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export function Button({
  className, variant, size, loading, children, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & { loading?: boolean }) {
  return (
    <button className={cn(buttonVariants({ variant, size }), className)} disabled={loading || props.disabled} {...props}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Card({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-border bg-surface p-4 shadow-[0_1px_2px_rgba(0,0,0,0.04)]", className)} {...props}>
      {children}
    </div>
  );
}

export function CardTitle({ children, className, action }: { children: ReactNode; className?: string; action?: ReactNode }) {
  return (
    <div className={cn("mb-3 flex items-center justify-between gap-2", className)}>
      <h2 className="text-[1.05rem] font-semibold tracking-tight">{children}</h2>
      {action}
    </div>
  );
}

export function Badge({ children, className, color, style }: { children: ReactNode; className?: string; color?: string; style?: React.CSSProperties }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs font-medium", className)}
      style={color ? { borderColor: color, color, ...style } : style}
    >
      {children}
    </span>
  );
}

export function ModuleChip({ short, color }: { short?: string | null; color?: string | null }) {
  if (!short) return null;
  return (
    <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-semibold text-white" style={{ background: color || "var(--primary)" }}>
      {short}
    </span>
  );
}

export const Input = ({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) => (
  <input
    className={cn("h-11 w-full rounded-xl border border-border bg-surface px-3 text-[1rem] outline-none placeholder:text-muted focus:border-primary", className)}
    {...props}
  />
);

export const Textarea = ({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea
    className={cn("min-h-28 w-full rounded-xl border border-border bg-surface p-3 text-[1rem] outline-none placeholder:text-muted focus:border-primary", className)}
    {...props}
  />
);

export const Select = ({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cn("h-11 w-full rounded-xl border border-border bg-surface px-3 text-[1rem] outline-none focus:border-primary", className)} {...props}>
    {children}
  </select>
);

export function Label({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="mb-1 block text-sm font-medium">
      {children}
      {hint && <span className="ml-1 font-normal text-muted">{hint}</span>}
    </label>
  );
}

export function Progress({ value, className, color }: { value: number; className?: string; color?: string }) {
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-surface-2", className)} role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full transition-all" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: color || "var(--primary)" }} />
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-muted">
      <Loader2 className="h-5 w-5 animate-spin" /> {label || "Lädt …"}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-muted">
      {icon}
      <p className="font-medium text-text">{title}</p>
      {children && <div className="max-w-md text-sm">{children}</div>}
    </div>
  );
}

export function Notice({ tone = "info", children, className }: { tone?: "info" | "warn" | "error" | "ok"; children: ReactNode; className?: string }) {
  const tones = {
    info: "border-primary/30 bg-primary/5",
    warn: "border-pruefen/40 bg-pruefen-bg",
    error: "border-unsicher/40 bg-unsicher-bg",
    ok: "border-sicher/40 bg-sicher-bg",
  } as const;
  return <div className={cn("rounded-xl border px-3 py-2 text-sm", tones[tone], className)}>{children}</div>;
}

export function Tabs<T extends string>({ tabs, value, onChange, className }: { tabs: { id: T; label: string; count?: number }[]; value: T; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={cn("scrollbar-thin -mx-1 flex gap-1 overflow-x-auto px-1 pb-1", className)} role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cn(
            "h-10 shrink-0 rounded-xl px-3 text-sm font-medium transition-colors",
            value === t.id ? "bg-primary text-primary-fg" : "bg-surface-2 text-text hover:bg-border/60",
          )}
        >
          {t.label}
          {t.count ? <span className="ml-1.5 rounded-full bg-black/10 px-1.5 text-xs">{t.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Sheet({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div
        className={cn("safe-bottom max-h-[90dvh] w-full overflow-y-auto rounded-t-2xl bg-surface p-5 shadow-xl sm:rounded-2xl", wide ? "sm:max-w-4xl" : "sm:max-w-xl")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{title}</h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Schließen">
            <X className="h-5 w-5" />
          </Button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Toggle({ checked, onChange, label, description }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string }) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center justify-between gap-4 py-1">
      <span>
        <span className="block font-medium">{label}</span>
        {description && <span className="block text-sm text-muted">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn("relative h-7 w-12 shrink-0 rounded-full transition-colors", checked ? "bg-primary" : "bg-border")}
      >
        <span className={cn("absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-all", checked ? "left-[22px]" : "left-0.5")} />
      </button>
    </label>
  );
}

export function StatusDot({ status }: { status: string }) {
  const color = status === "ok" ? "var(--sicher)" : status === "error" ? "var(--unsicher)" : status === "missing" ? "var(--muted)" : "var(--pruefen)";
  const label = status === "ok" ? "verbunden" : status === "error" ? "Fehler" : status === "missing" ? "fehlt" : "ungetestet";
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} aria-hidden />
      {label}
    </span>
  );
}
