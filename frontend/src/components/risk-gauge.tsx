"use client";
import { useT } from "@/lib/i18n";

const COLORS = { green: "hsl(var(--ok))", yellow: "hsl(var(--warn))", red: "hsl(var(--bad))" } as const;

/** Large score ring + three-light traffic light (colour is never the only signal: label text is shown too). */
export function RiskGauge({ score, light, size = 180 }: { score: number; light: "green" | "yellow" | "red"; size?: number }) {
  const { t } = useT();
  const r = 70, c = 2 * Math.PI * r;
  return (
    <div className="flex items-center gap-6">
      <svg width={size} height={size} viewBox="0 0 180 180" role="img" aria-label={`${t("home.score")}: ${score} / 100, ${t(`light.${light}`)}`}>
        <circle cx="90" cy="90" r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth="16" />
        <circle cx="90" cy="90" r={r} fill="none" stroke={COLORS[light]} strokeWidth="16" strokeLinecap="round"
          strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 90 90)" />
        <text x="90" y="88" textAnchor="middle" className="fill-foreground" style={{ fontSize: 44, fontWeight: 700 }}>{score}</text>
        <text x="90" y="114" textAnchor="middle" className="fill-muted-foreground" style={{ fontSize: 14 }}>von 100</text>
      </svg>
      <TrafficLight light={light} />
    </div>
  );
}

export function TrafficLight({ light, big = false }: { light: "green" | "yellow" | "red"; big?: boolean }) {
  const { t } = useT();
  const dot = big ? "h-10 w-10" : "h-6 w-6";
  return (
    <div className="flex flex-col items-center gap-2" aria-hidden="false">
      <div className="flex flex-col gap-2 rounded-full bg-foreground/90 p-2 dark:bg-muted">
        {(["red", "yellow", "green"] as const).map((l) => (
          <span key={l} className={`${dot} rounded-full`} style={{ background: COLORS[l], opacity: l === light ? 1 : 0.18 }} />
        ))}
      </div>
      <span className="text-sm font-semibold">{t(`light.${light}`)}</span>
    </div>
  );
}
