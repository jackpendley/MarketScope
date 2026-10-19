import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { SignOutButton } from "@/components/sign-out-button";
import { getAuth } from "@/lib/server/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "MarketScope", template: "%s · MarketScope" },
  description: "NFL sportsbook market intelligence: compare, replay, investigate, test.",
};

// Only built features are links; planned sections are shown as clearly unavailable.
const NAV: { label: string; href?: string }[] = [
  { label: "Odds Board", href: "/nfl" },
  { label: "Market Replay", href: "/replay" },
  { label: "Ratings", href: "/ratings" },
  { label: "Matchups", href: "/matchups" },
  { label: "Projections", href: "/projections" },
  { label: "Signal Lab", href: "/signals" },
  { label: "Data", href: "/data" },
  { label: "Research", href: "/research" },
  { label: "ML Lab" },
];

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // The proxy already requires a session for every page except /login; here it only decides
  // whether to show the navigation and who is signed in.
  const requestHeaders = await headers(); // first: marks the page dynamic before any auth code runs
  const session = await getAuth().api.getSession({ headers: requestHeaders });
  const user = session?.user as
    { username?: string; displayUsername?: string; email: string } | undefined;
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded focus:bg-surface-raised focus:px-3 focus:py-2 focus:text-fg"
        >
          Skip to main content
        </a>
        {user && (
          <header className="border-b border-line bg-surface">
            <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3">
              <Link href="/nfl" className="font-semibold tracking-tight">
                Market<span className="text-accent">Scope</span>
              </Link>
              {user && (
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
              )}
              {user && (
                <div className="ml-auto flex items-center gap-4 text-sm">
                  <Link href="/account" className="text-fg hover:text-accent">
                    {user.displayUsername ?? user.username ?? user.email}
                  </Link>
                  <SignOutButton />
                </div>
              )}
            </div>
          </header>
        )}
        <main id="main" tabIndex={-1} className="mx-auto max-w-7xl px-4 py-6 outline-none">
          {children}
        </main>
        <footer className="mx-auto max-w-7xl space-y-1 px-4 pb-8 pt-4 text-xs text-subtle">
          <p>
            MarketScope is an analytics and education project. It is not betting advice and does not
            take or place wagers. Odds are periodic snapshots from The Odds API (history before
            2026-10-16 is derived from OddsPapi line-move data) and may be outdated; confirm prices
            with the sportsbook. Sportsbook names identify data sources only; MarketScope is not
            affiliated with or endorsed by any sportsbook.
          </p>
          <p>
            Football data: schedules, results, play-by-play, injury reports and snap counts (Pro
            Football Reference) via{" "}
            <a href="https://github.com/nflverse" className="underline hover:text-muted">
              nflverse
            </a>{" "}
            (CC-BY 4.0). Weather forecasts by{" "}
            <a href="https://open-meteo.com/" className="underline hover:text-muted">
              Open-Meteo
            </a>{" "}
            (CC-BY 4.0). Coaching staff from Wikipedia and cited news reports.
          </p>
          <p>
            Gamble responsibly. 21+ where legal. If you or someone you know has a gambling problem,
            call 1-800-GAMBLER.
          </p>
        </footer>
      </body>
    </html>
  );
}
