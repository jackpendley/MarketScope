import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "MarketScope", template: "%s · MarketScope" },
  description: "NFL sportsbook market intelligence: compare, replay, investigate, test.",
};

// Only built features are links; planned sections are shown as clearly unavailable.
const NAV: { label: string; href?: string }[] = [
  { label: "Odds Board", href: "/nfl" },
  { label: "Market Replay" },
  { label: "Signal Lab" },
  { label: "Research" },
  { label: "ML Lab" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3">
            <Link href="/nfl" className="font-semibold tracking-tight">
              Market<span className="text-accent">Scope</span>
            </Link>
            <nav aria-label="Primary" className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
              {NAV.map((item) =>
                item.href ? (
                  <Link key={item.label} href={item.href} className="text-fg hover:text-accent">
                    {item.label}
                  </Link>
                ) : (
                  <span
                    key={item.label}
                    className="cursor-default text-subtle"
                    title="Planned, not built yet"
                  >
                    {item.label} <span className="text-xs">(soon)</span>
                  </span>
                ),
              )}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
