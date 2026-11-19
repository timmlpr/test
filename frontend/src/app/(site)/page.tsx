import Link from "next/link";
import { ArrowRight, BadgeCheck, Ban, Bell, FileText, Fingerprint, Globe, Image as ImageIcon, KeyRound, Lock, Mail, Radar, Server, Shield, ShieldAlert, Sparkles, Users } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Pricing } from "@/components/pricing";
import { Waitlist } from "./waitlist";
import { brand } from "@/lib/brand";
import { LandingText as T } from "./landing-text";

const features = [
  [Radar, "Privatsphäre-Scan", "Wo bist du mit Name, E-Mail oder Benutzername auffindbar?"],
  [ShieldAlert, "Datenleck-Check", "Steckt deine E-Mail in bekannten Lecks? Mit konkreten Schritten."],
  [Mail, "Lösch-Anfragen", "Fertige Texte nach DSGVO, als Mail oder PDF. Mit Fristen-Erinnerung."],
  [Shield, "Betrugs-Check", "Links, Shops und SMS prüfen – mit Ampel und Begründung."],
  [Globe, "Domain-Check", "Alter, Impressum, Zertifikat und Sicherheit einer Website."],
  [ImageIcon, "Bild-Check", "GPS-Ort und Metadaten deiner Fotos zeigen und entfernen."],
  [KeyRound, "Passwort-Check", "Geprüft im Browser. Nichts verlässt dein Gerät im Klartext."],
  [Fingerprint, "Sicherheits-Checkliste", "2FA, Updates, Backups – Schritt für Schritt für iPhone, Android, Windows."],
  [Bell, "Überwachung", "Regelmäßige Prüfung. Du hörst nur von uns, wenn es etwas Neues gibt."],
  [FileText, "Reports", "Alles auf einen Blick, als PDF und Excel. Mit Vorher-nachher-Vergleich."],
  [Sparkles, "Assistent", "Fragt man „Was ist mein größtes Risiko?“, antwortet er mit Quelle und nächstem Schritt."],
  [Users, "Familie", "Jede Person mit eigenem Login. Kinderprofile nur mit Elternzustimmung."],
] as const;

const faq = [
  ["Sucht Tracelow auch nach anderen Personen?", "Nein. Gesucht wird ausschließlich nach deinen eigenen, bestätigten Angaben. Eine freie Personensuche gibt es nicht – technisch nicht und auch nicht für Admins."],
  ["Woher kommen die Daten?", "Aus erlaubten öffentlichen Quellen und offiziellen Schnittstellen, z. B. Datenleck-Datenbanken, Wikipedia oder Such-Schnittstellen. Wir umgehen keine Logins, Captchas oder Paywalls."],
  ["Löscht Tracelow meine Daten automatisch?", "Wir erstellen fertige Lösch-Anfragen nach DSGVO. Versenden tust du sie selbst – so behältst du die Kontrolle, und es ist rechtlich eindeutig, dass die Anfrage von dir kommt."],
  ["Was kostet das?", "Der Basis-Check ist kostenlos. Premium kostet 3,99 € im Monat und ist monatlich kündbar – mit einem Klick."],
  ["Wo liegen meine Daten?", "Auf Servern in Deutschland. Sensible Angaben speichern wir verschlüsselt. Du kannst alles jederzeit exportieren oder löschen."],
  ["Ist das eine Rechtsberatung?", "Nein. Die Vorlagen helfen dir, deine Rechte wahrzunehmen, ersetzen aber keine anwaltliche Beratung."],
];

export default function Landing() {
  const ld = {
    "@context": "https://schema.org", "@graph": [
      { "@type": "SoftwareApplication", name: brand.name, applicationCategory: "SecurityApplication", operatingSystem: "Web, iOS, Android, Windows",
        offers: { "@type": "Offer", price: "0", priceCurrency: "EUR" }, description: brand.tagline_de },
      { "@type": "FAQPage", mainEntity: faq.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })) },
    ],
  };
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ld) }} />
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-gradient-to-br from-primary/10 via-background to-accent/10" />
        <div className="container grid items-center gap-10 py-16 md:grid-cols-2 md:py-24">
          <div className="space-y-6">
            <p className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium"><Server className="h-3.5 w-3.5" /> Gehostet in Deutschland · DSGVO</p>
            <h1 className="text-4xl font-bold leading-tight sm:text-5xl"><T k="landing.hero.title" /></h1>
            <p className="text-lg text-muted-foreground"><T k="landing.hero.sub" /></p>
            <div className="flex flex-wrap gap-3">
              <Link href="/register" className={buttonVariants({ size: "lg" })}><T k="landing.hero.cta" /><ArrowRight className="h-4 w-4" /></Link>
              <Link href="#warteliste" className={buttonVariants({ size: "lg", variant: "outline" })}><T k="landing.hero.cta2" /></Link>
            </div>
            <p className="text-sm text-muted-foreground"><T k="landing.hero.note" /></p>
          </div>
          <HeroIllustration />
        </div>
      </section>

      <section className="container py-16" aria-labelledby="steps">
        <h2 id="steps" className="mb-8 text-center text-3xl font-bold"><T k="landing.steps.title" /></h2>
        <ol className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map((n) => (
            <li key={n} className="rounded-lg border bg-card p-6">
              <span className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-primary text-lg font-bold text-primary-foreground">{n}</span>
              <h3 className="font-semibold"><T k={`landing.steps.${n}.t`} /></h3>
              <p className="mt-1 text-sm text-muted-foreground"><T k={`landing.steps.${n}.d`} /></p>
            </li>
          ))}
        </ol>
      </section>

      <section className="bg-card py-16" aria-labelledby="diff">
        <div className="container">
          <h2 id="diff" className="mb-8 text-center text-3xl font-bold"><T k="landing.diff.title" /></h2>
          <div className="grid gap-6 md:grid-cols-2">
            {[BadgeCheck, Sparkles, Lock, Server].map((Icon, i) => (
              <div key={i} className="flex gap-4 rounded-lg border p-6">
                <Icon className="h-8 w-8 shrink-0 text-accent" aria-hidden />
                <div><h3 className="font-semibold"><T k={`landing.diff.${i + 1}.t`} /></h3><p className="mt-1 text-sm text-muted-foreground"><T k={`landing.diff.${i + 1}.d`} /></p></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="funktionen" className="container py-16" aria-labelledby="feat">
        <h2 id="feat" className="mb-8 text-center text-3xl font-bold"><T k="landing.features.title" /></h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map(([Icon, title, text]) => (
            <div key={title} className="rounded-lg border bg-card p-5">
              <Icon className="mb-3 h-6 w-6 text-primary" aria-hidden />
              <h3 className="font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="preise" className="bg-card py-16" aria-labelledby="price">
        <div className="container">
          <h2 id="price" className="text-center text-3xl font-bold"><T k="landing.pricing.title" /></h2>
          <p className="mb-8 mt-2 text-center text-muted-foreground"><T k="landing.pricing.sub" /></p>
          <Pricing />
        </div>
      </section>

      <section className="container py-16" aria-labelledby="trust">
        <h2 id="trust" className="mb-8 text-center text-3xl font-bold"><T k="landing.trust.title" /></h2>
        <ul className="mx-auto grid max-w-3xl gap-3">
          {[1, 2, 3, 4, 5].map((n) => (
            <li key={n} className="flex items-start gap-3 rounded-lg border bg-card p-4">
              {n === 2 ? <Ban className="mt-0.5 h-5 w-5 shrink-0 text-accent" /> : <BadgeCheck className="mt-0.5 h-5 w-5 shrink-0 text-accent" />}
              <span><T k={`landing.trust.${n}`} /></span>
            </li>
          ))}
        </ul>
      </section>

      <section id="faq" className="bg-card py-16" aria-labelledby="faqh">
        <div className="container max-w-3xl">
          <h2 id="faqh" className="mb-8 text-center text-3xl font-bold"><T k="landing.faq.title" /></h2>
          <div className="space-y-3">
            {faq.map(([q, a]) => (
              <details key={q} className="group rounded-lg border bg-background p-4">
                <summary className="cursor-pointer list-none font-medium">{q}</summary>
                <p className="mt-2 text-sm text-muted-foreground">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section id="warteliste" className="container py-16"><Waitlist /></section>
    </>
  );
}

function HeroIllustration() {
  return (
    <div className="relative mx-auto w-full max-w-md" aria-hidden="true">
      <div className="rounded-2xl border bg-card p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between"><span className="text-sm font-semibold">Dein Risiko-Wert</span><span className="rounded-full bg-warn/15 px-2 py-0.5 text-xs font-medium text-warn">Beispiel</span></div>
        <div className="flex items-center gap-6">
          <svg viewBox="0 0 120 120" className="h-28 w-28"><circle cx="60" cy="60" r="48" fill="none" stroke="hsl(var(--muted))" strokeWidth="12" />
            <circle cx="60" cy="60" r="48" fill="none" stroke="hsl(var(--warn))" strokeWidth="12" strokeLinecap="round" strokeDasharray="150 302" transform="rotate(-90 60 60)" />
            <text x="60" y="68" textAnchor="middle" style={{ fontSize: 28, fontWeight: 700 }} className="fill-foreground">49</text></svg>
          <div className="space-y-2 text-sm"><p>14 Funde</p><p>3 mit hohem Risiko</p><p>2 Datenlecks</p></div>
        </div>
        <div className="mt-5 rounded-md border border-primary/20 bg-primary/5 p-3 text-sm"><span className="font-semibold text-primary">Nächster Schritt:</span> Lösch-Anfrage an die Vereinsseite senden.</div>
      </div>
    </div>
  );
}
