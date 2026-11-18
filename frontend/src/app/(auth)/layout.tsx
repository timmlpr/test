import Link from "next/link";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-br from-primary/5 via-background to-accent/5">
      <header className="container flex h-16 items-center justify-between"><Link href="/"><Logo /></Link><ThemeToggle /></header>
      <main id="main" className="flex flex-1 items-start justify-center px-4 py-8 sm:items-center">
        <div className="w-full max-w-md rounded-2xl border bg-card p-6 shadow-sm sm:p-8">{children}</div>
      </main>
    </div>
  );
}
