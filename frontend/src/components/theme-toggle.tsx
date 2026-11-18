"use client";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "./providers";
import { useT } from "@/lib/i18n";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const { t } = useT();
  const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  return (
    <button onClick={() => setTheme(next)} className="rounded-md p-2 hover:bg-muted" aria-label={`${t("theme.toggle")}: ${t(`theme.${theme}`)}`}
      title={`${t("theme.toggle")} (${t(`theme.${theme}`)})`}>
      <Icon className="h-5 w-5" />
    </button>
  );
}
