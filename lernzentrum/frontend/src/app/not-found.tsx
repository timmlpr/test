import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center">
      <img src="/logo.svg" alt="" className="h-14 w-14" />
      <h1 className="text-2xl font-bold">Seite nicht gefunden</h1>
      <Link href="/" className="text-primary underline">Zur Startseite</Link>
    </main>
  );
}
