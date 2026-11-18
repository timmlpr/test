"use client";
import { useT } from "@/lib/i18n";

/** Client text node so landing copy follows the Du/Sie switch and locale. */
export function LandingText({ k }: { k: string }) {
  const { t } = useT();
  return <>{t(k)}</>;
}
