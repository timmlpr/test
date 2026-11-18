import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-2xl font-bold">Seite nicht gefunden</h1>
      <p className="text-muted-foreground">Diese Seite gibt es nicht (mehr).</p>
      <Link href="/" className="text-primary underline">Zur Startseite</Link>
    </main>
  );
}
