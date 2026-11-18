import { SiteFooter, SiteHeader, CookieBanner } from "@/components/site";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-card focus:p-2">Zum Inhalt springen</a>
      <SiteHeader />
      <main id="main">{children}</main>
      <SiteFooter />
      <CookieBanner />
    </>
  );
}
