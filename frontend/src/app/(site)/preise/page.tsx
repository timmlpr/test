import type { Metadata } from "next";
import { Pricing } from "@/components/pricing";

export const metadata: Metadata = { title: "Preise", description: "Kostenlos starten. Premium 3,99 €/Monat, Familie ab 5,99 €/Monat, Einmal-Report 9 €. Monatlich kündbar." };

export default function Preise() {
  return (
    <div className="container py-12">
      <h1 className="text-center text-3xl font-bold">Preise</h1>
      <p className="mx-auto mb-8 mt-2 max-w-xl text-center text-muted-foreground">Starte kostenlos. Wenn du mehr brauchst, wähle Premium oder Familie. Alle Preise inkl. MwSt., keine versteckten Kosten.</p>
      <Pricing />
    </div>
  );
}
